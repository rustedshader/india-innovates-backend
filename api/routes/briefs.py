"""Policy briefs API routes.

Endpoints:
    POST /api/briefs/generate          — Generate a brief on a topic/domain
    GET  /api/briefs                   — List all generated briefs
    GET  /api/briefs/{id}              — Retrieve a specific brief
    GET  /api/briefs/sitrep            — Today's auto-generated situation report
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, desc

from models.database import SessionLocal
from models.policy_brief import PolicyBrief
from agents.policy_brief import PolicyBriefAgent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/briefs", tags=["briefs"])

_IST = timezone(timedelta(hours=5, minutes=30))

VALID_BRIEF_TYPES = ["intelligence_summary", "policy_brief", "options_memo", "sitrep"]
VALID_DOMAINS = [
    "geopolitics", "defense", "economics", "technology",
    "energy", "health", "climate", "diplomacy",
]


class BriefRequest(BaseModel):
    brief_type: str = "intelligence_summary"
    domain: str = "geopolitics"
    topic: Optional[str] = None


class BriefSummary(BaseModel):
    id: int
    brief_type: str
    domain: Optional[str]
    topic: Optional[str]
    created_at: str


class BriefDetail(BaseModel):
    id: int
    brief_type: str
    domain: Optional[str]
    topic: Optional[str]
    markdown_content: Optional[str]
    entities: Optional[list]
    created_at: str


@router.post(
    "/generate",
    response_model=BriefDetail,
    summary="Generate a policy brief on a topic or domain",
)
def generate_brief(request: BriefRequest):
    """Generate an intelligence document. Runs synchronously (~10-30s LLM call).

    Brief types:
    - **intelligence_summary**: 1-page BLUF format, last 48h data
    - **policy_brief**: 2-3 page with policy options, last 7 days data
    - **sitrep**: Auto daily situation report across all domains
    """
    if request.brief_type not in VALID_BRIEF_TYPES:
        raise HTTPException(422, f"brief_type must be one of: {VALID_BRIEF_TYPES}")
    if request.brief_type != "sitrep" and request.domain not in VALID_DOMAINS:
        raise HTTPException(422, f"domain must be one of: {VALID_DOMAINS}")

    agent = PolicyBriefAgent()
    try:
        if request.brief_type == "sitrep":
            result = agent.generate_sitrep(hours=24)
        elif request.brief_type == "intelligence_summary":
            result = agent.generate_intelligence_summary(request.domain, request.topic)
        else:
            # Both 'policy_brief' and 'options_memo' use the policy_brief generator.
            # options_memo produces the same 3-option analysis format.
            result = agent.generate_policy_brief(request.domain, request.topic)
    finally:
        agent.close()

    return BriefDetail(
        id=result.get("id", 0),
        brief_type=result["brief_type"],
        domain=result.get("domain"),
        topic=result.get("topic"),
        markdown_content=result.get("markdown_content"),
        entities=result.get("entities", []),
        created_at=result.get("created_at", datetime.now(_IST).isoformat()),
    )


@router.get(
    "/sitrep",
    response_model=BriefDetail,
    summary="Today's auto-generated situation report",
)
def get_sitrep(hours: int = Query(24, ge=1, le=168, description="Lookback window in hours")):
    """Generate (or return cached) the daily situation report.

    Checks if a sitrep was generated in the last 2 hours; returns it if so.
    Otherwise generates a fresh one.
    """
    db = SessionLocal()
    try:
        # Check for recent sitrep
        cutoff = datetime.now(_IST) - timedelta(hours=2)
        existing = db.scalars(
            select(PolicyBrief).where(
                PolicyBrief.brief_type == "sitrep",
                PolicyBrief.created_at >= cutoff,
            ).order_by(desc(PolicyBrief.created_at)).limit(1)
        ).first()

        if existing:
            return BriefDetail(
                id=existing.id,
                brief_type=existing.brief_type,
                domain=existing.domain,
                topic=existing.topic,
                markdown_content=existing.markdown_content,
                entities=existing.entities,
                created_at=existing.created_at.isoformat() if existing.created_at else "",
            )
    finally:
        db.close()

    # Generate fresh
    agent = PolicyBriefAgent()
    try:
        result = agent.generate_sitrep(hours=hours)
    finally:
        agent.close()

    return BriefDetail(
        id=result.get("id", 0),
        brief_type=result["brief_type"],
        domain=result.get("domain"),
        topic=result.get("topic"),
        markdown_content=result.get("markdown_content"),
        entities=result.get("entities", []),
        created_at=result.get("created_at", datetime.now(_IST).isoformat()),
    )


@router.get(
    "",
    response_model=list[BriefSummary],
    summary="List all generated briefs",
)
def list_briefs(
    brief_type: Optional[str] = Query(None),
    domain: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    db = SessionLocal()
    try:
        query = select(PolicyBrief)
        if brief_type:
            query = query.where(PolicyBrief.brief_type == brief_type)
        if domain:
            query = query.where(PolicyBrief.domain == domain)
        query = query.order_by(desc(PolicyBrief.created_at)).limit(limit)
        rows = db.scalars(query).all()
        return [
            BriefSummary(
                id=r.id,
                brief_type=r.brief_type,
                domain=r.domain,
                topic=r.topic,
                created_at=r.created_at.isoformat() if r.created_at else "",
            )
            for r in rows
        ]
    finally:
        db.close()


@router.get(
    "/{brief_id}",
    response_model=BriefDetail,
    summary="Retrieve a specific brief by ID",
)
def get_brief(brief_id: int):
    db = SessionLocal()
    try:
        brief = db.get(PolicyBrief, brief_id)
        if not brief:
            raise HTTPException(404, f"Brief {brief_id} not found")
        return BriefDetail(
            id=brief.id,
            brief_type=brief.brief_type,
            domain=brief.domain,
            topic=brief.topic,
            markdown_content=brief.markdown_content,
            entities=brief.entities,
            created_at=brief.created_at.isoformat() if brief.created_at else "",
        )
    finally:
        db.close()
