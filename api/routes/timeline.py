"""Timeline API routes — entity state history and graph snapshots.

Endpoints:
    GET  /api/timeline/{entity}          — Full state history for an entity
    GET  /api/timeline/{entity}/diff     — State changes between two dates
    GET  /api/snapshot                   — Graph state at a specific point in time
    POST /api/timeline                   — Manually ingest an entity state record
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import select

from agents.temporal import TemporalAgent
from models.database import SessionLocal
from models.entity_state import EntityState

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["timeline"])

# Lazy-init agent (shares the same Neo4j driver lifecycle as the app)
_agent: Optional[TemporalAgent] = None


def _get_agent() -> TemporalAgent:
    global _agent
    if _agent is None:
        _agent = TemporalAgent()
    return _agent


def close_agent():
    global _agent
    if _agent:
        _agent.close()
        _agent = None


# ── Response models ───────────────────────────────────────────────────────────

class StateRecord(BaseModel):
    id: int
    entity_name: str
    entity_type: str
    attribute: str
    value: str
    temporal_marker: Optional[str]
    confidence: float
    valid_from: Optional[str]
    valid_to: Optional[str]
    is_current: bool
    source_article_url: Optional[str]
    source_article_title: Optional[str]


class TimelineResponse(BaseModel):
    entity_name: str
    total: int
    states: list[StateRecord]


class SnapshotRecord(BaseModel):
    entity_name: str
    entity_type: str
    attribute: str
    value: str
    valid_from: Optional[str]
    valid_to: Optional[str]
    confidence: float
    source_article_url: Optional[str]


class SnapshotResponse(BaseModel):
    at: str
    total_entities: int
    states: list[SnapshotRecord]


class CreateStateRequest(BaseModel):
    """Request body to manually inject an entity state record."""
    entity_name: str
    entity_type: str = "Entity"
    attribute: str
    value: str
    temporal_marker: Optional[str] = None
    confidence: float = 1.0
    valid_from: Optional[str] = None   # ISO date, defaults to now
    source_article_url: Optional[str] = None
    source_article_title: Optional[str] = None

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("confidence must be between 0.0 and 1.0")
        return v


class StateDiff(BaseModel):
    entity_name: str
    from_date: str
    to_date: str
    new_states: list[dict]
    retired_states: list[dict]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get(
    "/timeline/{entity_name}",
    response_model=TimelineResponse,
    summary="Get temporal state history for an entity",
)
def get_entity_timeline(
    entity_name: str,
    from_date: Optional[str] = Query(
        None,
        description="ISO date string, e.g. '2025-01-01'. Filters states valid from this date.",
    ),
    to_date: Optional[str] = Query(
        None,
        description="ISO date string. Filters states valid until this date.",
    ),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of state records to return"),
):
    """Return the full temporal state history for a named entity.

    Each record represents a detected state (attribute=value) for the entity
    during a specific time window, backed by a source article.
    """
    from_dt = _parse_date(from_date, "from_date") if from_date else None
    to_dt = _parse_date(to_date, "to_date") if to_date else None

    agent = _get_agent()
    states = agent.get_entity_timeline(entity_name, from_dt=from_dt, to_dt=to_dt, limit=limit)

    return TimelineResponse(
        entity_name=entity_name,
        total=len(states),
        states=[StateRecord(**s) for s in states],
    )


@router.get(
    "/timeline/{entity_name}/diff",
    response_model=StateDiff,
    summary="Get state changes for an entity between two dates",
)
def get_entity_diff(
    entity_name: str,
    from_date: str = Query(..., description="Start date (ISO format, e.g. '2025-01-01')"),
    to_date: str = Query(..., description="End date (ISO format, e.g. '2025-03-01')"),
):
    """Return new states that appeared and old states that were retired for an entity
    within the specified date window. Useful for detecting what changed about an
    entity over a period.
    """
    from_dt = _parse_date(from_date, "from_date")
    to_dt = _parse_date(to_date, "to_date")

    if from_dt >= to_dt:
        raise HTTPException(status_code=422, detail="from_date must be before to_date")

    agent = _get_agent()
    diff = agent.get_state_diff(entity_name, from_dt, to_dt)

    return StateDiff(
        entity_name=diff["entity_name"],
        from_date=diff["from"],
        to_date=diff["to"],
        new_states=diff["new_states"],
        retired_states=diff["retired_states"],
    )


@router.get(
    "/snapshot",
    response_model=SnapshotResponse,
    summary="Get the full graph state at a specific point in time",
)
def get_graph_snapshot(
    at: Optional[str] = Query(
        None,
        description="ISO date string for the snapshot point. Defaults to now (current state).",
    ),
    entity_name: Optional[str] = Query(
        None,
        description="Optional: filter snapshot to a single entity.",
    ),
):
    """Return all known entity–attribute–value states at a given moment.

    Uses Postgres entity_states table (valid_from ≤ at < valid_to, or valid_to is null).
    This enables historical playback — rewind the knowledge graph to any past date.
    """
    at_dt = _parse_date(at, "at") if at else datetime.now(timezone(timedelta(hours=5, minutes=30)))

    agent = _get_agent()
    all_states = agent.get_snapshot(at_dt)

    if entity_name:
        all_states = [s for s in all_states if s["entity_name"] == entity_name]

    return SnapshotResponse(
        at=at_dt.isoformat(),
        total_entities=len({s["entity_name"] for s in all_states}),
        states=[SnapshotRecord(**s) for s in all_states],
    )


@router.post(
    "/timeline",
    response_model=StateRecord,
    status_code=201,
    summary="Manually ingest an entity state record",
)
def create_entity_state(request: CreateStateRequest):
    """Manually add an entity state record to the temporal database.

    Useful for injecting human-intelligence data or correcting states that
    the automated scraping pipeline missed. The record is written directly
    to the `entity_states` Postgres table. If a current state exists for
    the same (entity, attribute) pair, it is retired (valid_to set to now)
    before the new record is inserted.
    """
    now = datetime.now(_IST)
    valid_from_dt = _parse_date(request.valid_from, "valid_from") if request.valid_from else now

    db = SessionLocal()
    try:
        # Retire any current state for this (entity, attribute) pair
        existing_current = db.scalars(
            select(EntityState).where(
                EntityState.entity_name == request.entity_name,
                EntityState.attribute == request.attribute,
                EntityState.valid_to.is_(None),
            )
        ).all()
        for old in existing_current:
            old.valid_to = valid_from_dt

        state = EntityState(
            entity_name=request.entity_name,
            entity_type=request.entity_type,
            attribute=request.attribute,
            value=request.value,
            temporal_marker=request.temporal_marker,
            confidence=request.confidence,
            valid_from=valid_from_dt,
            valid_to=None,
            source_article_url=request.source_article_url,
            source_article_title=request.source_article_title,
        )
        db.add(state)
        db.commit()
        db.refresh(state)
        logger.info(f"Manual entity state created: {state.entity_name}.{state.attribute}={state.value!r}")
        return StateRecord(
            id=state.id,
            entity_name=state.entity_name,
            entity_type=state.entity_type,
            attribute=state.attribute,
            value=state.value,
            temporal_marker=state.temporal_marker,
            confidence=state.confidence,
            valid_from=state.valid_from.isoformat() if state.valid_from else None,
            valid_to=state.valid_to.isoformat() if state.valid_to else None,
            is_current=state.is_current,
            source_article_url=state.source_article_url,
            source_article_title=state.source_article_title,
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create entity state: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

_IST = timezone(timedelta(hours=5, minutes=30))


def _parse_date(value: str, field: str) -> datetime:
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d", "%Y-%m"):
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_IST)
            return dt
        except ValueError:
            continue
    raise HTTPException(
        status_code=422,
        detail=f"Invalid date format for '{field}': {value!r}. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS+HH:MM",
    )
