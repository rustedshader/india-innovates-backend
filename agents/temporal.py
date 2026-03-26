"""Temporal Agent — attaches time dimension to entities and relationships.

Runs after entity resolution. Uses article pub_date + temporal markers
from extraction to create EntityState records in Postgres and update
Neo4j relationship `current` flags.

Design:
  - Detects when a new extraction implies a NEW state for an entity attribute
  - Retires the old state row (sets valid_to) instead of overwriting
  - Creates State nodes in Neo4j as: (Entity)-[:HAS_STATE]->(State {value, attribute})
  - Marks stale RELATES_TO edges as current=false when contradicted
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from neo4j import GraphDatabase
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select, update

from config import NEO4J_URI, NEO4J_AUTH
from graphs.schemas import ArticleExtraction, ExtractedRelation
from models.database import SessionLocal
from models.entity_state import EntityState

logger = logging.getLogger(__name__)

# IST offset
_IST = timezone(timedelta(hours=5, minutes=30))

# ── Attribute inference heuristics ───────────────────────────────────────────
# Maps (relation_type) → attribute name for the source entity.
# When we see a RELATES_TO edge, we infer what "attribute" of the source changed.
_RELATION_TO_ATTRIBUTE: dict[str, str] = {
    "leads":               "leadership",
    "founded":             "founder",
    "member_of":           "membership",
    "sanctions":           "sanctions_status",
    "allied_with":         "alliance_status",
    "opposes":             "opposition_stance",
    "invaded":             "military_engagement",
    "trades_with":         "trade_partner",
    "develops":            "development_focus",
    "exports_to":          "export_target",
    "imports_from":        "import_source",
    "cooperates_with":     "cooperation_status",
    "competes_with":       "competition_stance",
    "attacks":             "conflict_action",
    "deployed_to":         "deployment_location",
    "signed_agreement_with": "diplomatic_agreement",
    "negotiates_with":     "negotiation_status",
    "funds":               "funding_relationship",
    "threatens":           "threat_posture",
    "supports":            "support_relationship",
    "blocks":              "blockade_status",
    "disrupts":            "disruption_target",
    "acquired":            "ownership",
    "manufactures":        "production_focus",
    "supplies_to":         "supply_relationship",
    "located_in":          "location",
}

# Attributes where a new value definitively replaces the old (mutually exclusive)
_EXCLUSIVE_ATTRIBUTES = {
    "leadership", "owner", "location", "membership",
    "sanctions_status", "alliance_status",
}


def _parse_pub_date(pub_date_str: str) -> datetime:
    """Parse article pub_date string into a UTC datetime, falling back to now()."""
    if not pub_date_str:
        return datetime.now(_IST)
    # Try common formats
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(pub_date_str.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_IST)
            return dt
        except ValueError:
            continue
    return datetime.now(_IST)


class TemporalAgent:
    """Attaches temporal metadata to extractions and persists state history.

    For each article batch:
    1. Infer entity attribute–value pairs from relations
    2. Compare against current state in Postgres
    3. Retire old states (set valid_to) if contradicted
    4. Insert new state rows
    5. Update Neo4j: create State nodes + mark stale edges as current=false
    """

    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
        logger.info("TemporalAgent initialized")

    def close(self):
        self.driver.close()

    # ── Core processing ───────────────────────────────────────────────────────

    def process(
        self, extractions: list[tuple[object, ArticleExtraction]]
    ) -> list[tuple[object, ArticleExtraction]]:
        """Process a batch of extractions, recording state changes.

        Args:
            extractions: List of (Article, ArticleExtraction) pairs (post-resolution).

        Returns:
            Same list, unchanged (state recording is a side-effect).
        """
        if not extractions:
            return extractions

        new_states: list[dict] = []
        neo4j_states: list[dict] = []
        stale_edges: list[dict] = []

        for article, extraction in extractions:
            article_dt = _parse_pub_date(getattr(article, "pub_date", ""))
            article_url = getattr(article, "url", "")
            article_title = getattr(article, "title", "")

            for rel in extraction.relations:
                attr = _RELATION_TO_ATTRIBUTE.get(rel.relation)
                if not attr:
                    continue

                new_states.append({
                    "entity_name": rel.source,
                    "entity_type": self._get_entity_type(rel.source, extraction),
                    "attribute": attr,
                    "value": rel.target,
                    "temporal_marker": rel.temporal,
                    "confidence": rel.confidence,
                    "valid_from": article_dt,
                    "source_article_url": article_url,
                    "source_article_title": article_title,
                })

                neo4j_states.append({
                    "entity_name": rel.source,
                    "attribute": attr,
                    "value": rel.target,
                    "from_date": article_dt.isoformat(),
                    "article_url": article_url,
                })

                # Track edges that may need to be marked stale
                if attr in _EXCLUSIVE_ATTRIBUTES:
                    stale_edges.append({
                        "entity": rel.source,
                        "relation": rel.relation,
                        "new_target": rel.target,
                    })

        if new_states:
            self._persist_states(new_states)
        if neo4j_states:
            self._update_neo4j_states(neo4j_states, stale_edges)

        temporal_rels = sum(
            1 for _, ext in extractions
            for rel in ext.relations if rel.temporal
        )
        events = sum(len(ext.events) for _, ext in extractions)
        logger.info(
            f"Temporal: {len(new_states)} state records, "
            f"{temporal_rels} relations with markers, "
            f"{events} events across {len(extractions)} articles"
        )

        return extractions

    # ── Postgres persistence ──────────────────────────────────────────────────

    def _persist_states(self, new_states: list[dict]) -> None:
        """Retire contradicted states and insert new ones into Postgres."""
        db = SessionLocal()
        try:
            for s in new_states:
                if s["attribute"] in _EXCLUSIVE_ATTRIBUTES:
                    # Check if there's a current state with a different value
                    existing = db.scalars(
                        select(EntityState).where(
                            EntityState.entity_name == s["entity_name"],
                            EntityState.attribute == s["attribute"],
                            EntityState.valid_to.is_(None),
                            EntityState.value != s["value"],
                        )
                    ).all()
                    # Retire old states
                    for old in existing:
                        old.valid_to = s["valid_from"]

                # Insert new state row (upsert: skip if identical current state exists)
                stmt = (
                    pg_insert(EntityState)
                    .values(
                        entity_name=s["entity_name"],
                        entity_type=s["entity_type"],
                        attribute=s["attribute"],
                        value=s["value"],
                        temporal_marker=s.get("temporal_marker"),
                        confidence=s["confidence"],
                        valid_from=s["valid_from"],
                        valid_to=None,
                        source_article_url=s.get("source_article_url"),
                        source_article_title=s.get("source_article_title"),
                    )
                    .on_conflict_do_nothing()
                )
                db.execute(stmt)

            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"TemporalAgent Postgres persist failed: {e}")
        finally:
            db.close()

    # ── Neo4j State nodes ─────────────────────────────────────────────────────

    def _update_neo4j_states(
        self,
        neo4j_states: list[dict],
        stale_edges: list[dict],
    ) -> None:
        """Create State nodes in Neo4j and retire stale edges."""
        try:
            with self.driver.session() as session:
                # Create/update HAS_STATE relationships
                if neo4j_states:
                    session.run("""
                        UNWIND $rows AS row
                        MATCH (e:Entity {name: row.entity_name})
                        MERGE (s:State {
                            entity_name: row.entity_name,
                            attribute: row.attribute,
                            value: row.value
                        })
                        ON CREATE SET
                            s.from_date = row.from_date,
                            s.current = true,
                            s.source_url = row.article_url
                        ON MATCH SET
                            s.from_date = CASE
                                WHEN s.from_date > row.from_date THEN row.from_date
                                ELSE s.from_date
                            END
                        MERGE (e)-[:HAS_STATE]->(s)
                    """, rows=neo4j_states)

                # Mark old states for exclusive attributes as not current
                if stale_edges:
                    session.run("""
                        UNWIND $rows AS row
                        MATCH (e:Entity {name: row.entity})-[:HAS_STATE]->(s:State {attribute: row.attribute})
                        WHERE s.value <> row.new_target AND s.current = true
                        SET s.current = false
                    """, rows=stale_edges)

                    # Also mark the underlying RELATES_TO edges as not current
                    session.run("""
                        UNWIND $rows AS row
                        MATCH (src:Entity {name: row.entity})-[r:RELATES_TO {type: row.relation}]->(old_tgt:Entity)
                        WHERE old_tgt.name <> row.new_target AND r.current = true
                        SET r.current = false
                    """, rows=stale_edges)

        except Exception as e:
            logger.error(f"TemporalAgent Neo4j update failed: {e}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _get_entity_type(name: str, extraction: ArticleExtraction) -> str:
        """Look up entity type from the extraction's entity list."""
        for e in extraction.entities:
            if e.name == name:
                return e.type
        return ""

    # ── Public query helpers (used by timeline API) ───────────────────────────

    def get_entity_timeline(
        self,
        entity_name: str,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[dict]:
        """Return state history for an entity from Postgres."""
        db = SessionLocal()
        try:
            query = select(EntityState).where(
                EntityState.entity_name == entity_name
            )
            if from_dt:
                query = query.where(EntityState.valid_from >= from_dt)
            if to_dt:
                query = query.where(EntityState.valid_from <= to_dt)
            query = query.order_by(EntityState.valid_from.desc()).limit(limit)
            rows = db.scalars(query).all()
            return [
                {
                    "id": r.id,
                    "entity_name": r.entity_name,
                    "entity_type": r.entity_type,
                    "attribute": r.attribute,
                    "value": r.value,
                    "temporal_marker": r.temporal_marker,
                    "confidence": r.confidence,
                    "valid_from": r.valid_from.isoformat() if r.valid_from else None,
                    "valid_to": r.valid_to.isoformat() if r.valid_to else None,
                    "is_current": r.is_current,
                    "source_article_url": r.source_article_url,
                    "source_article_title": r.source_article_title,
                }
                for r in rows
            ]
        finally:
            db.close()

    def get_snapshot(self, at_dt: datetime) -> list[dict]:
        """Return all current entity states at a given point in time."""
        db = SessionLocal()
        try:
            query = select(EntityState).where(
                EntityState.valid_from <= at_dt,
                (EntityState.valid_to > at_dt) | (EntityState.valid_to.is_(None)),
            ).order_by(EntityState.entity_name, EntityState.attribute)
            rows = db.scalars(query).all()
            return [
                {
                    "entity_name": r.entity_name,
                    "entity_type": r.entity_type,
                    "attribute": r.attribute,
                    "value": r.value,
                    "valid_from": r.valid_from.isoformat() if r.valid_from else None,
                    "valid_to": r.valid_to.isoformat() if r.valid_to else None,
                    "confidence": r.confidence,
                    "source_article_url": r.source_article_url,
                }
                for r in rows
            ]
        finally:
            db.close()

    def get_state_diff(
        self, entity_name: str, from_dt: datetime, to_dt: datetime
    ) -> dict:
        """Return state changes between two dates for an entity."""
        db = SessionLocal()
        try:
            # States that started in the window
            started = db.scalars(
                select(EntityState).where(
                    EntityState.entity_name == entity_name,
                    EntityState.valid_from >= from_dt,
                    EntityState.valid_from <= to_dt,
                ).order_by(EntityState.valid_from)
            ).all()

            # States that ended in the window (retirements)
            ended = db.scalars(
                select(EntityState).where(
                    EntityState.entity_name == entity_name,
                    EntityState.valid_to >= from_dt,
                    EntityState.valid_to <= to_dt,
                ).order_by(EntityState.valid_to)
            ).all()

            return {
                "entity_name": entity_name,
                "from": from_dt.isoformat(),
                "to": to_dt.isoformat(),
                "new_states": [
                    {
                        "attribute": r.attribute,
                        "new_value": r.value,
                        "started_at": r.valid_from.isoformat() if r.valid_from else None,
                        "source": r.source_article_title,
                    }
                    for r in started
                ],
                "retired_states": [
                    {
                        "attribute": r.attribute,
                        "old_value": r.value,
                        "retired_at": r.valid_to.isoformat() if r.valid_to else None,
                        "source": r.source_article_title,
                    }
                    for r in ended
                ],
            }
        finally:
            db.close()
