"""Explainable Predictions API routes.

Endpoints:
    GET  /api/predictions              — Active predictions with confidence scores
    GET  /api/predictions/{id}/explain — Full reasoning chain + source attribution
    GET  /api/predictions/calibration  — Prediction accuracy tracking
    POST /api/predictions/verify       — Mark a prediction's outcome
    POST /api/predictions/create       — Manually submit a prediction (analyst-generated)
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, desc, func

from models.database import SessionLocal
from models.prediction import Prediction

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/predictions", tags=["predictions"])

_IST = timezone(timedelta(hours=5, minutes=30))


class PredictionOut(BaseModel):
    id: int
    prediction_text: str
    domain: Optional[str]
    confidence: float
    confidence_components: Optional[dict]
    entities: Optional[list]
    created_at: str
    expires_at: Optional[str]
    outcome: Optional[str]


class PredictionExplain(BaseModel):
    id: int
    prediction_text: str
    confidence: float
    confidence_components: Optional[dict]
    source_articles: Optional[list]
    reasoning_chain: Optional[list]
    graph_path: Optional[str]
    entities: Optional[list]
    created_at: str


class OutcomeRequest(BaseModel):
    prediction_id: int
    outcome: str         # "correct" | "incorrect" | "partial"
    notes: Optional[str] = None


class CreatePredictionRequest(BaseModel):
    prediction_text: str
    domain: Optional[str] = None
    confidence: float
    confidence_components: Optional[dict] = None
    entities: Optional[list] = None
    horizon: Optional[str] = None           # e.g. "30d", "6m", "1y"
    source_articles: Optional[list] = None
    reasoning_chain: Optional[list] = None
    graph_path: Optional[str] = None
    expires_days: Optional[int] = None      # default: 30 days


class CalibrationBucket(BaseModel):
    confidence_min: float
    confidence_max: float
    total: int
    correct: int
    accuracy: float


@router.get(
    "",
    response_model=list[PredictionOut],
    summary="Active predictions with confidence scores",
)
def list_predictions(
    domain: Optional[str] = Query(None),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
    outcome: Optional[str] = Query(None, description="Filter by outcome: correct/incorrect/partial/null"),
    limit: int = Query(50, ge=1, le=200),
):
    """List active predictions, optionally filtered by domain and confidence."""
    db = SessionLocal()
    try:
        now = datetime.now(_IST)
        query = select(Prediction).where(
            (Prediction.expires_at > now) | Prediction.expires_at.is_(None),
            Prediction.confidence >= min_confidence,
        )
        if domain:
            query = query.where(Prediction.domain == domain)
        if outcome is not None:
            if outcome == "null":
                query = query.where(Prediction.outcome.is_(None))
            else:
                query = query.where(Prediction.outcome == outcome)
        query = query.order_by(desc(Prediction.confidence)).limit(limit)
        rows = db.scalars(query).all()
        return [
            PredictionOut(
                id=r.id,
                prediction_text=r.prediction_text,
                domain=r.domain,
                confidence=r.confidence,
                confidence_components=r.confidence_components,
                entities=r.entities,
                created_at=r.created_at.isoformat() if r.created_at else "",
                expires_at=r.expires_at.isoformat() if r.expires_at else None,
                outcome=r.outcome,
            )
            for r in rows
        ]
    finally:
        db.close()


@router.get(
    "/calibration",
    response_model=list[CalibrationBucket],
    summary="Prediction accuracy calibration report",
)
def get_calibration():
    """Return accuracy by confidence bucket.

    A well-calibrated system has ~60% accuracy for 60%-confidence predictions.
    This endpoint allows auditing whether the engine is trustworthy.
    """
    db = SessionLocal()
    try:
        buckets = []
        for low in [0.0, 0.2, 0.4, 0.6, 0.8]:
            high = low + 0.2
            predictions = db.scalars(
                select(Prediction).where(
                    Prediction.confidence >= low,
                    Prediction.confidence < high,
                    Prediction.outcome.is_not(None),
                )
            ).all()
            total = len(predictions)
            correct = sum(1 for p in predictions if p.outcome == "correct")
            buckets.append(CalibrationBucket(
                confidence_min=low,
                confidence_max=high,
                total=total,
                correct=correct,
                accuracy=round(correct / total, 3) if total > 0 else 0.0,
            ))
        return buckets
    finally:
        db.close()


@router.get(
    "/{prediction_id}/explain",
    response_model=PredictionExplain,
    summary="Full reasoning chain and source attribution for a prediction",
)
def explain_prediction(prediction_id: int):
    """Return the full explainability package for a prediction.

    Includes:
    - Decomposed confidence scores (data, causal, temporal, source_diversity)
    - Source articles with provenance
    - Graph reasoning chain (entity → relation → entity path)
    - Neo4j Cypher path that produced the prediction
    """
    db = SessionLocal()
    try:
        p = db.get(Prediction, prediction_id)
        if not p:
            raise HTTPException(404, f"Prediction {prediction_id} not found")
        return PredictionExplain(
            id=p.id,
            prediction_text=p.prediction_text,
            confidence=p.confidence,
            confidence_components=p.confidence_components,
            source_articles=p.source_articles,
            reasoning_chain=p.reasoning_chain,
            graph_path=p.graph_path,
            entities=p.entities,
            created_at=p.created_at.isoformat() if p.created_at else "",
        )
    finally:
        db.close()


@router.post(
    "/verify",
    summary="Mark a prediction's real-world outcome for calibration tracking",
)
def verify_prediction(request: OutcomeRequest):
    """Record whether a prediction came true.

    Valid outcomes: 'correct', 'incorrect', 'partial'.
    Used to compute calibration curves over time.
    """
    if request.outcome not in ("correct", "incorrect", "partial"):
        raise HTTPException(422, "outcome must be 'correct', 'incorrect', or 'partial'")

    db = SessionLocal()
    try:
        p = db.get(Prediction, request.prediction_id)
        if not p:
            raise HTTPException(404, f"Prediction {request.prediction_id} not found")
        p.outcome = request.outcome
        p.outcome_notes = request.notes
        p.outcome_verified_at = datetime.now(_IST)
        db.commit()
        return {"status": "ok", "prediction_id": request.prediction_id, "outcome": request.outcome}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(500, str(e))
    finally:
        db.close()


@router.post(
    "/create",
    response_model=PredictionOut,
    status_code=201,
    summary="Manually submit an analyst-generated prediction",
)
def create_prediction(request: CreatePredictionRequest):
    """Persist a manually-authored prediction for calibration tracking.

    Useful for analyst-submitted forecasts that should be tracked alongside
    auto-generated predictions. Confidence must be 0.0–1.0.
    The prediction will expire after `expires_days` days (default 30).
    """
    if not (0.0 <= request.confidence <= 1.0):
        raise HTTPException(422, "confidence must be between 0.0 and 1.0")

    now = datetime.now(_IST)
    expires_at = now + timedelta(days=request.expires_days or 30)

    db = SessionLocal()
    try:
        pred = Prediction(
            prediction_text=request.prediction_text,
            domain=request.domain,
            confidence=request.confidence,
            confidence_components=request.confidence_components,
            entities=request.entities,
            horizon=request.horizon,
            source_articles=request.source_articles,
            reasoning_chain=request.reasoning_chain,
            graph_path=request.graph_path,
            created_at=now,
            expires_at=expires_at,
        )
        db.add(pred)
        db.commit()
        db.refresh(pred)
        logger.info(f"Manual prediction created: id={pred.id} conf={pred.confidence:.2f}")
        return PredictionOut(
            id=pred.id,
            prediction_text=pred.prediction_text,
            domain=pred.domain,
            confidence=pred.confidence,
            confidence_components=pred.confidence_components,
            entities=pred.entities,
            created_at=pred.created_at.isoformat() if pred.created_at else "",
            expires_at=pred.expires_at.isoformat() if pred.expires_at else None,
            outcome=pred.outcome,
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create prediction: {e}")
        raise HTTPException(500, str(e))
    finally:
        db.close()
