"""India entity discovery service.

Dynamically discovers India-related entities from the Neo4j knowledge graph
and stores them in the PostgreSQL database for fast lookup.
"""

import logging
from typing import Set, List, Dict, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select, update, delete
from neo4j import GraphDatabase

from models.india_seed_entity import IndiaSeedEntity
from config import NEO4J_URI, NEO4J_AUTH

logger = logging.getLogger(__name__)


class IndiaEntityService:
    """
    Manages India-related entity discovery and storage.

    Discovers entities connected to India via Neo4j graph traversal
    and maintains them in the PostgreSQL database for performance.
    """

    def __init__(self, db_session: Session, neo4j_driver=None):
        self.db = db_session
        if neo4j_driver:
            self.driver = neo4j_driver
        else:
            self.driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
        self._cache: Optional[Set[str]] = None

    def get_india_entities(
        self,
        min_relevance_score: float = 0.3,
        include_non_core: bool = True,
    ) -> Set[str]:
        """
        Get India-related entities from database.

        Args:
            min_relevance_score: Minimum relevance score threshold (0-1)
            include_non_core: Whether to include non-core entities

        Returns:
            Set of entity names
        """
        # Check cache first
        if self._cache is not None:
            logger.debug(f"Returning {len(self._cache)} cached India entities")
            return self._cache.copy()

        # Query database
        query = select(IndiaSeedEntity).where(
            IndiaSeedEntity.relevance_score >= min_relevance_score
        )

        if not include_non_core:
            query = query.where(IndiaSeedEntity.is_core == True)

        results = self.db.execute(query).scalars().all()

        entities = {entity.entity_name for entity in results}

        # Cache the results
        self._cache = entities.copy()

        logger.info(f"Retrieved {len(entities)} India entities from database")
        return entities

    def discover_from_graph(
        self,
        max_hops: int = 3,
        min_connection_count: int = 2,
        max_entities: int = 500,
    ) -> List[Dict]:
        """
        Discover India-related entities from Neo4j graph.

        Args:
            max_hops: Maximum number of hops from India node
            min_connection_count: Minimum connections to be considered
            max_entities: Maximum entities to return

        Returns:
            List of dicts with keys: entity_name, entity_type, connection_count, rel_types
        """
        logger.info(f"Discovering India entities from graph (max_hops={max_hops})")

        entities = []

        with self.driver.session() as session:
            result = session.run(
                f"""
                MATCH (india:Entity)
                WHERE lower(india.name) = 'india'
                MATCH path = (india)-[*1..{max_hops}]-(connected:Entity)
                WITH connected,
                     count(DISTINCT path) as connection_count,
                     collect(DISTINCT type(last(relationships(path)))) as rel_types,
                     collect(DISTINCT labels(connected)[0]) as entity_labels
                WHERE connection_count >= {min_connection_count}
                RETURN
                    connected.name as entity_name,
                    entity_labels[0] as entity_type,
                    connection_count,
                    rel_types
                ORDER BY connection_count DESC
                LIMIT {max_entities}
                """
            )

            for record in result:
                entities.append({
                    "entity_name": record["entity_name"],
                    "entity_type": record["entity_type"],
                    "connection_count": record["connection_count"],
                    "rel_types": record["rel_types"],
                })

        logger.info(f"Discovered {len(entities)} India-connected entities from graph")
        return entities

    def refresh_database(
        self,
        max_hops: int = 3,
        min_connection_count: int = 2,
        mark_core_threshold: int = 10,
    ) -> Dict:
        """
        Refresh the India entities database from graph traversal.

        Args:
            max_hops: Maximum hops from India
            min_connection_count: Minimum connections to include
            mark_core_threshold: Connection count to mark as core entity

        Returns:
            Dict with refresh statistics
        """
        logger.info("Starting India entity database refresh")

        try:
            # Discover entities from graph
            discovered = self.discover_from_graph(
                max_hops=max_hops,
                min_connection_count=min_connection_count,
            )

            if not discovered:
                logger.warning("No entities discovered from graph")
                return {
                    "status": "no_entities",
                    "added": 0,
                    "updated": 0,
                    "total": 0,
                }

            # Clear existing non-manual entities
            deleted = self.db.execute(
                delete(IndiaSeedEntity).where(
                    IndiaSeedEntity.discovered_via == "graph_traversal"
                )
            )
            deleted_count = deleted.rowcount if hasattr(deleted, 'rowcount') else 0

            # Insert new entities
            added = 0
            updated = 0

            for entity_data in discovered:
                # Calculate relevance score (based on connection count)
                # Normalize by max connection count in the batch
                max_connections = max(e["connection_count"] for e in discovered)
                relevance_score = min(
                    entity_data["connection_count"] / max_connections,
                    1.0
                )

                # Determine if core entity
                is_core = entity_data["connection_count"] >= mark_core_threshold

                # Check if exists (manual entry)
                existing = self.db.execute(
                    select(IndiaSeedEntity).where(
                        IndiaSeedEntity.entity_name == entity_data["entity_name"]
                    )
                ).scalar_one_or_none()

                if existing and existing.discovered_via == "manual":
                    # Update but preserve manual flag
                    existing.connection_count = entity_data["connection_count"]
                    existing.relevance_score = max(existing.relevance_score, relevance_score)
                    existing.last_seen = datetime.now(timezone.utc)
                    updated += 1
                else:
                    # Create new entity
                    new_entity = IndiaSeedEntity(
                        entity_name=entity_data["entity_name"],
                        entity_type=entity_data["entity_type"],
                        relevance_score=relevance_score,
                        connection_count=entity_data["connection_count"],
                        is_core=is_core,
                        discovered_via="graph_traversal",
                    )
                    self.db.add(new_entity)
                    added += 1

            self.db.commit()

            # Clear cache
            self._cache = None

            total = added + updated
            logger.info(
                f"India entity refresh complete: {added} added, {updated} updated, "
                f"{deleted_count} removed, {total} total"
            )

            return {
                "status": "success",
                "added": added,
                "updated": updated,
                "deleted": deleted_count,
                "total": total,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            self.db.rollback()
            logger.error(f"India entity refresh failed: {e}")
            raise

    def add_manual_entity(
        self,
        entity_name: str,
        entity_type: Optional[str] = None,
        relevance_score: float = 1.0,
        is_core: bool = True,
    ) -> None:
        """
        Manually add an India-related entity.

        Args:
            entity_name: Name of the entity
            entity_type: Type of entity (optional)
            relevance_score: Relevance score (0-1)
            is_core: Whether this is a core entity
        """
        # Check if exists
        existing = self.db.execute(
            select(IndiaSeedEntity).where(
                IndiaSeedEntity.entity_name == entity_name
            )
        ).scalar_one_or_none()

        if existing:
            logger.warning(f"Entity '{entity_name}' already exists, updating")
            existing.entity_type = entity_type or existing.entity_type
            existing.relevance_score = relevance_score
            existing.is_core = is_core
            existing.discovered_via = "manual"
            existing.last_seen = datetime.now(timezone.utc)
        else:
            new_entity = IndiaSeedEntity(
                entity_name=entity_name,
                entity_type=entity_type,
                relevance_score=relevance_score,
                connection_count=0,  # Manual entries don't have connection count
                is_core=is_core,
                discovered_via="manual",
            )
            self.db.add(new_entity)

        self.db.commit()
        self._cache = None  # Clear cache

        logger.info(f"Manually added India entity: {entity_name}")

    def get_statistics(self) -> Dict:
        """Get statistics about India entities."""
        total = self.db.execute(select(IndiaSeedEntity)).scalars().all()

        stats = {
            "total": len(total),
            "core": sum(1 for e in total if e.is_core),
            "non_core": sum(1 for e in total if not e.is_core),
            "by_discovery_method": {},
            "by_entity_type": {},
            "avg_relevance_score": sum(e.relevance_score for e in total) / len(total) if total else 0,
            "avg_connection_count": sum(e.connection_count for e in total) / len(total) if total else 0,
        }

        # Count by discovery method
        for entity in total:
            method = entity.discovered_via or "unknown"
            stats["by_discovery_method"][method] = stats["by_discovery_method"].get(method, 0) + 1

        # Count by entity type
        for entity in total:
            etype = entity.entity_type or "unknown"
            stats["by_entity_type"][etype] = stats["by_entity_type"].get(etype, 0) + 1

        return stats

    def clear_cache(self) -> None:
        """Clear the in-memory cache."""
        self._cache = None
        logger.debug("India entity cache cleared")

    def close(self):
        """Close Neo4j driver connection."""
        if self.driver:
            self.driver.close()
