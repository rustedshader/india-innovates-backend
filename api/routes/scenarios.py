"""Scenario simulation and domain stability API routes.

Endpoints:
    POST /api/scenarios/simulate     — Submit a hypothetical scenario, get graph-grounded predictions
    GET  /api/stability              — Current domain instability scores + trend
    GET  /api/stability/{domain}     — Detailed instability breakdown for a domain
    POST /api/stability/record       — Persist current stability scores for historical trend tracking
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from neo4j import GraphDatabase
from pydantic import BaseModel
from sqlalchemy import select, desc
from langchain_groq import ChatGroq

class ScenarioExtraction(BaseModel):
    key_entities: list[str]

from config import NEO4J_URI, NEO4J_AUTH
from models.database import SessionLocal
from models.domain_stability import DomainStability
from models.scraped_article import ScrapedArticle
from agents.impact_direction_classifier import ImpactDirectionClassifier

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["scenarios"])

# Initialize impact direction classifier
_impact_classifier = ImpactDirectionClassifier(enable_llm=True)

# Shared Neo4j driver for scenario simulation (avoids per-request reconnect)
_driver = None


def _get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    return _driver

_IST = timezone(timedelta(hours=5, minutes=30))

# Domain → entity type weights for instability scoring
_DOMAIN_ENTITY_WEIGHTS = {
    "geopolitics":  {"Country": 1.0, "Person": 0.8, "Organization": 0.6, "Policy": 0.9},
    "defense":      {"Military_Asset": 1.0, "Country": 0.8, "Organization": 0.5},
    "economics":    {"Economic_Indicator": 1.0, "Organization": 0.7, "Country": 0.6},
    "technology":   {"Technology": 1.0, "Organization": 0.7, "Person": 0.4},
    "climate":      {"Resource": 1.0, "Location": 0.6, "Country": 0.4},
}

STANDARD_DOMAINS = [
    "geopolitics", "defense", "economics", "technology",
    "energy", "health", "climate", "diplomacy",
]


# ── Pydantic models ──────────────────────────────────────────────────────────

class ScenarioRequest(BaseModel):
    scenario: str
    entities: Optional[list[str]] = None   # Seed entities (optional, auto-discovered if not set)
    max_hops: int = 3
    domain_filter: Optional[str] = None


class AffectedNode(BaseModel):
    name: str
    type: str
    hop_distance: int
    via_relation: str
    impact_direction: str   # "risk" | "opportunity" | "neutral"
    confidence: float


class ScenarioResult(BaseModel):
    scenario: str
    seed_entities: list[str]
    affected_nodes: list[AffectedNode]
    india_implications: list[str]
    confidence_overall: float
    graph_paths: list[str]
    generated_at: str


class StabilityScore(BaseModel):
    domain: str
    score: float
    components: dict
    staleness_penalty: float
    data_age_hours: float
    computed_at: str
    trend: Optional[str] = None  # "rising" | "falling" | "stable"


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post(
    "/scenarios/simulate",
    response_model=ScenarioResult,
    summary="Simulate a what-if scenario against the live knowledge graph",
)
def simulate_scenario(request: ScenarioRequest):
    """Submit a scenario hypothesis and get graph-grounded impact predictions.

    The engine:
    1. Identifies seed entities from the scenario text or the provided list
    2. Traces 1–N hop RELATES_TO paths through the knowledge graph
    3. Scores affected entities by confidence × evidence × hop_distance_decay
    4. Extracts India-specific implications from affected nodes

    This is NOT a multi-agent simulation — all predictions are grounded in
    the actual ontology graph, giving full provenance and auditability.
    """
    driver = _get_driver()
    seed_entities = request.entities or []
    affected: list[dict] = []
    graph_paths: list[str] = []

    try:
        with driver.session() as session:
            # Auto-discover seed entities using Groq LLM extraction
            if not seed_entities and request.scenario:
                try:
                    # Extract entities from the scenario text
                    llm = ChatGroq(model_name="llama-3.3-70b-versatile", temperature=0.1).with_structured_output(ScenarioExtraction)
                    extraction = llm.invoke(f"Extract 1 to 5 key entity names (like countries, organizations, people, or resources) from this scenario. Output only the most important keywords. Scenario: {request.scenario}")
                    extracted_keywords = extraction.key_entities if extraction and hasattr(extraction, 'key_entities') else [request.scenario.split()[0]]
                except Exception as e:
                    logger.error(f"Groq scenario extraction failed: {e}")
                    extracted_keywords = [request.scenario.split()[0]]

                if extracted_keywords:
                    result = session.run("""
                        UNWIND $keywords AS kw
                        MATCH (e:Entity)
                        WHERE lower(e.name) CONTAINS lower(kw)
                        RETURN DISTINCT e.name AS name, e.type AS type
                        LIMIT 10
                    """, keywords=extracted_keywords)
                    seed_entities = [r["name"] for r in result]

            if not seed_entities:
                raise HTTPException(
                    status_code=422,
                    detail="Could not identify any relevant entities. Try providing 'entities' explicitly."
                )

            # BFS impact propagation
            hops = min(request.max_hops, 4)
            result = session.run(f"""
                MATCH path = (seed:Entity)-[:RELATES_TO*1..{hops}]->(affected:Entity)
                WHERE seed.name IN $seeds
                  AND NOT affected.name IN $seeds
                WITH path, seed, affected,
                     length(path) AS hops,
                     [r IN relationships(path) | r.type] AS rels,
                     reduce(c = 1.0, r IN relationships(path) |
                         c * coalesce(r.confidence, 0.7)) AS path_conf
                ORDER BY path_conf / hops DESC
                LIMIT 50
                RETURN affected.name AS name,
                       affected.type AS type,
                       hops,
                       rels[-1] AS via_relation,
                       path_conf,
                       [n IN nodes(path) | n.name] AS path_nodes
            """, seeds=seed_entities)

            for r in result:
                affected.append({
                    "name": r["name"],
                    "type": r["type"],
                    "hop_distance": r["hops"],
                    "via_relation": r["via_relation"] or "relates_to",
                    "confidence": round(r["path_conf"], 3),
                    "path_nodes": r["path_nodes"],
                })
                path_str = " → ".join(r["path_nodes"])
                if path_str not in graph_paths:
                    graph_paths.append(path_str)

        # India implications: filter for India-connected nodes
        india_keywords = {
            "India", "Indian", "Modi", "Delhi", "Mumbai", "ISRO",
            "DRDO", "RBI", "Rupee", "BSE", "NSE",
        }
        india_paths = [
            a for a in affected
            if any(kw in a["name"] for kw in india_keywords)
        ]
        india_implications = [
            f"{a['name']} ({a['type']}) affected via {a['via_relation']} at {a['hop_distance']} hops"
            for a in india_paths[:5]
        ]

        overall_conf = (
            sum(a["confidence"] for a in affected) / len(affected)
            if affected else 0.0
        )

        # Classify impact direction for each affected node
        affected_with_direction = []
        for a in affected[:30]:
            impact_direction = _impact_classifier.classify(
                entity_name=a["name"],
                entity_type=a["type"],
                domain=request.domain_filter,  # Use domain filter if provided
                relation_type=a.get("via_relation"),
                scenario_context=request.scenario,
            )
            affected_with_direction.append(
                AffectedNode(
                    name=a["name"],
                    type=a["type"],
                    hop_distance=a["hop_distance"],
                    via_relation=a["via_relation"],
                    impact_direction=impact_direction,
                    confidence=a["confidence"],
                )
            )

        return ScenarioResult(
            scenario=request.scenario,
            seed_entities=seed_entities,
            affected_nodes=affected_with_direction,
            india_implications=india_implications,
            confidence_overall=round(overall_conf, 3),
            graph_paths=graph_paths[:10],
            generated_at=datetime.now(_IST).isoformat(),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Scenario simulation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/stability",
    response_model=list[StabilityScore],
    summary="Current domain instability scores",
)
def get_stability_scores(
    domains: Optional[str] = Query(
        None, description="Comma-separated domain list. Defaults to all standard domains."
    )
):
    """Return instability scores for all (or specified) domains.

    Scores are computed freshly from article recency + entity volatility.
    A domain with no recent data gets a staleness penalty to prevent
    falsely optimistic readings (WorldMonitor pattern).
    """
    domain_list = (
        [d.strip() for d in domains.split(",")]
        if domains else STANDARD_DOMAINS
    )
    return [_compute_domain_stability(d) for d in domain_list]


@router.get(
    "/stability/{domain}",
    response_model=StabilityScore,
    summary="Detailed instability breakdown for a single domain",
)
def get_domain_stability(domain: str):
    """Return detailed instability score and component breakdown for a domain."""
    if domain not in STANDARD_DOMAINS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown domain '{domain}'. Valid: {', '.join(STANDARD_DOMAINS)}"
        )
    return _compute_domain_stability(domain)


@router.post(
    "/stability/record",
    summary="Persist current stability scores to the database for trend tracking",
)
def record_stability_scores(
    domains: Optional[str] = Query(
        None, description="Comma-separated domain list. Defaults to all standard domains."
    )
):
    """Compute and persist stability scores to the `domain_stability` table.

    This enables the trend field in GET /api/stability to show historical data
    (rising / falling / stable) rather than always returning null.
    Designed to be called by a scheduler (e.g. every 6 hours) or manually.
    """
    domain_list = (
        [d.strip() for d in domains.split(",")]
        if domains else STANDARD_DOMAINS
    )

    db = SessionLocal()
    saved = []
    try:
        for domain_name in domain_list:
            score = _compute_domain_stability(domain_name)
            record = DomainStability(
                domain=domain_name,
                score=score.score,
                components=score.components,
                staleness_penalty=score.staleness_penalty,
                data_age_hours=score.data_age_hours,
            )
            db.add(record)
            saved.append({"domain": domain_name, "score": score.score})
        db.commit()
        logger.info(f"Recorded stability scores for {len(saved)} domains")
        return {"status": "ok", "recorded": saved}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to record stability scores: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


# ── Internal scoring ──────────────────────────────────────────────────────────

def _compute_domain_stability(domain: str) -> StabilityScore:
    """Compute instability score for a domain from recent article data."""
    db = SessionLocal()
    now = datetime.now(_IST)
    try:
        # Recent high-importance articles in this domain (last 48h)
        cutoff_48h = now - timedelta(hours=48)
        recent_articles = db.scalars(
            select(ScrapedArticle).where(
                ScrapedArticle.domain == domain,
                ScrapedArticle.scraped_at >= cutoff_48h,
                ScrapedArticle.importance_score >= 5.0,
            )
        ).all()

        # 7-day articles for baseline
        cutoff_7d = now - timedelta(days=7)
        week_count = len(db.scalars(
            select(ScrapedArticle.id).where(
                ScrapedArticle.domain == domain,
                ScrapedArticle.scraped_at >= cutoff_7d,
            )
        ).all())

        # Compute components
        recent_count = len(recent_articles)
        avg_score = (
            sum(a.importance_score or 0 for a in recent_articles) / recent_count
            if recent_count else 0.0
        )

        # Data age: hours since most recent article in this domain
        most_recent = max(
            (a.scraped_at for a in recent_articles if a.scraped_at),
            default=None
        )
        data_age_hours = (
            (now - most_recent).total_seconds() / 3600 if most_recent else 48.0
        )

        # Staleness penalty: ramps up after 6h of no new data
        staleness_penalty = min(data_age_hours / 48.0, 0.5) if data_age_hours > 6 else 0.0

        # Volume volatility: deviation from weekly average
        daily_avg = max(week_count / 7, 1)
        volume_score = min(recent_count / 2 / daily_avg, 1.0)  # 48h vs daily avg

        # Importance-weighted instability
        importance_score = min(avg_score / 10.0, 1.0)

        # Composite (0-10)
        raw_score = (volume_score * 0.4 + importance_score * 0.6) * 10
        final_score = min(raw_score + staleness_penalty * 10, 10.0)

        components = {
            "volume_factor": round(volume_score, 3),
            "importance_factor": round(importance_score, 3),
            "recent_article_count": recent_count,
            "weekly_article_count": week_count,
            "avg_importance_score": round(avg_score, 2),
        }

        return StabilityScore(
            domain=domain,
            score=round(final_score, 2),
            components=components,
            staleness_penalty=round(staleness_penalty, 3),
            data_age_hours=round(data_age_hours, 1),
            computed_at=now.isoformat(),
            trend=None,  # Historical trend requires DomainStability table population
        )
    finally:
        db.close()
