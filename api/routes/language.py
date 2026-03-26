"""Language analysis API routes — Indic NLP layer.

Endpoints:
    POST /api/language/analyze         — Analyze text for language, sentiment, entities
    GET  /api/language/stats           — Language distribution of recent articles
    GET  /api/language/sentiment/{entity} — Entity sentiment over time in Indic media
    POST /api/language/batch           — Batch-analyze multiple texts in one call
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, desc

from agents.indic_nlp import IndicNLPAgent
from models.database import SessionLocal
from models.scraped_article import ScrapedArticle

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/language", tags=["language"])

_IST = timezone(timedelta(hours=5, minutes=30))

# Lazy singleton — model loads once
_agent: Optional[IndicNLPAgent] = None


def _get_agent() -> IndicNLPAgent:
    global _agent
    if _agent is None:
        _agent = IndicNLPAgent()
    return _agent


# ── Pydantic models ───────────────────────────────────────────────────────────

class TextAnalysisRequest(BaseModel):
    text: str
    include_entities: bool = True


class TextAnalysisResponse(BaseModel):
    text_preview: str
    language: str
    language_name: str
    is_indic: bool
    script: Optional[str]
    sentiment: str
    sentiment_score: float
    sentiment_model: str
    entities: list[dict]
    transliterated: Optional[str]


class LanguageStats(BaseModel):
    window_hours: int
    total_articles: int
    indic_count: int
    indic_fraction: float
    language_breakdown: dict  # {lang_code: count}


class EntitySentimentResponse(BaseModel):
    entity: str
    sample_count: int
    avg_sentiment_score: Optional[float]
    dominant_sentiment: str
    analyzed_at: str


class BatchAnalysisRequest(BaseModel):
    texts: list[str]
    include_entities: bool = True


class BatchAnalysisResponse(BaseModel):
    total: int
    indic_count: int
    results: list[TextAnalysisResponse]


# —— Routes ————————————————————————————————————————————————────────────────────────────────────────────────────────────────────

@router.post(
    "/analyze",
    response_model=TextAnalysisResponse,
    summary="Analyze text for language, sentiment, and entities (12 Indian languages supported)",
)
def analyze_text(request: TextAnalysisRequest):
    """Detect language and run sentiment + NER on any text.

    Supports: Hindi, Marathi, Bengali, Punjabi, Gujarati, Odia, Tamil,
    Telugu, Kannada, Malayalam, Urdu, and English.

    For English text, language detection is instant (no model). For Indic
    text, IndicBERT is used if installed, with rule-based fallback.
    """
    agent = _get_agent()
    result = agent.analyze(request.text)
    return TextAnalysisResponse(
        text_preview=request.text[:100] + ("..." if len(request.text) > 100 else ""),
        language=result.language,
        language_name=result.language_name,
        is_indic=result.is_indic,
        script=result.script,
        sentiment=result.sentiment,
        sentiment_score=result.sentiment_score,
        sentiment_model=result.sentiment_model,
        entities=result.entities if request.include_entities else [],
        transliterated=result.transliterated,
    )


@router.get(
    "/stats",
    response_model=LanguageStats,
    summary="Language distribution of recently ingested articles",
)
def get_language_stats(
    hours: int = Query(24, ge=1, le=168, description="Lookback window in hours"),
    limit: int = Query(500, ge=50, le=2000),
):
    """Sample recent articles and compute the fraction of Indic-language content.

    Uses fast script detection (no ML model needed).
    """
    db = SessionLocal()
    try:
        cutoff = datetime.now(_IST) - timedelta(hours=hours)
        articles = db.scalars(
            select(ScrapedArticle.title).where(
                ScrapedArticle.scraped_at >= cutoff,
                ScrapedArticle.title.is_not(None),
            ).limit(limit)
        ).all()

        agent = _get_agent()
        lang_counts: dict[str, int] = {}
        indic_count = 0

        for title in articles:
            if not title:
                continue
            lang, _ = agent.detect_language(title)
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
            if lang != "en":
                indic_count += 1

        total = len(articles)
        return LanguageStats(
            window_hours=hours,
            total_articles=total,
            indic_count=indic_count,
            indic_fraction=round(indic_count / total, 3) if total else 0.0,
            language_breakdown=lang_counts,
        )
    finally:
        db.close()


@router.get(
    "/sentiment/{entity_name}",
    response_model=EntitySentimentResponse,
    summary="Entity sentiment in Indic-language articles over a time window",
)
def get_entity_sentiment_indic(
    entity_name: str,
    hours: int = Query(48, ge=1, le=720, description="Lookback window in hours"),
    limit: int = Query(100, ge=10, le=500),
):
    """Compute average sentiment about an entity in Indic-language articles.

    Searches for articles mentioning the entity name (case-insensitive) in
    their title or description, filters to Indic-language ones, then runs
    IndicBERT sentiment analysis.
    """
    db = SessionLocal()
    try:
        cutoff = datetime.now(_IST) - timedelta(hours=hours)
        rows = db.scalars(
            select(ScrapedArticle).where(
                ScrapedArticle.scraped_at >= cutoff,
                (
                    ScrapedArticle.title.ilike(f"%{entity_name}%") |
                    ScrapedArticle.description.ilike(f"%{entity_name}%")
                ),
            ).order_by(desc(ScrapedArticle.scraped_at)).limit(limit)
        ).all()
    finally:
        db.close()

    texts = [r.title or r.description or "" for r in rows if r.title or r.description]
    agent = _get_agent()
    result = agent.sentiment_batch_for_entity(entity_name, texts)

    return EntitySentimentResponse(
        entity=entity_name,
        sample_count=result["sample_count"],
        avg_sentiment_score=result["avg_sentiment_score"],
        dominant_sentiment=result["dominant_sentiment"],
        analyzed_at=datetime.now(_IST).isoformat(),
    )


@router.post(
    "/batch",
    response_model=BatchAnalysisResponse,
    summary="Batch-analyze multiple texts for language, sentiment, and entities",
)
def analyze_texts_batch(request: BatchAnalysisRequest):
    """Analyze up to 50 texts in a single call.

    Internally routes Indic texts through IndicBERT in a single batched
    inference call, making this far more efficient than multiple individual
    /analyze calls for bulk processing (e.g. article pipelines, ETL jobs).

    Returns per-text results plus aggregate counts of Indic vs. English texts.
    """
    if len(request.texts) > 50:
        raise HTTPException(
            status_code=422,
            detail="Maximum 50 texts per batch request.",
        )
    if not request.texts:
        return BatchAnalysisResponse(total=0, indic_count=0, results=[])

    agent = _get_agent()
    raw_results = agent.analyze_batch(request.texts)

    out = []
    indic_count = 0
    for r in raw_results:
        if r.is_indic:
            indic_count += 1
        out.append(TextAnalysisResponse(
            text_preview=r.text[:100] + ("..." if len(r.text) > 100 else ""),
            language=r.language,
            language_name=r.language_name,
            is_indic=r.is_indic,
            script=r.script,
            sentiment=r.sentiment,
            sentiment_score=r.sentiment_score,
            sentiment_model=r.sentiment_model,
            entities=r.entities if request.include_entities else [],
            transliterated=r.transliterated,
        ))

    return BatchAnalysisResponse(
        total=len(out),
        indic_count=indic_count,
        results=out,
    )
