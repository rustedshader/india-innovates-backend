"""Extraction Pipeline Benchmark.

Compares three extraction strategies on a sample of real articles:
  A) LLM-only NER + relation extraction
  B) GLiNER2 + LLM (the hybrid pipeline used by this system)
  C) GLiNER2 alone (local model, no LLM)

Metrics measured:
  - Extraction time per article
  - Entity count per article
  - Hallucination rate (entities not substring-matched in source text)
  - Estimated API token usage
  - Relation count per article

Usage:
    cd backend
    python -m scripts.benchmark_extraction [--articles N] [--output results.json]
"""

import argparse
import json
import logging
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from statistics import mean, stdev
from typing import Optional

from sqlalchemy import select, desc

from models.database import SessionLocal
from models.scraped_article import ScrapedArticle

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class ExtractionResult:
    article_url: str
    article_len_chars: int
    method: str
    duration_ms: float
    entity_count: int
    relation_count: int
    hallucinated_entity_count: int
    estimated_tokens: int
    entities: list[dict] = field(default_factory=list)
    error: Optional[str] = None

@dataclass
class BenchmarkSummary:
    method: str
    n_articles: int
    avg_duration_ms: float
    std_duration_ms: float
    avg_entity_count: float
    avg_relation_count: float
    hallucination_rate_pct: float
    avg_tokens: float
    total_errors: int


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_hallucinated(entity_name: str, source_text: str) -> bool:
    """Return True if entity_name (or any 3+ char word in it) doesn't appear in source."""
    lower_text = source_text.lower()
    for part in entity_name.lower().split():
        if len(part) >= 3 and part in lower_text:
            return False
    return True


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~1 token per 4 chars."""
    return len(text) // 4


# ── Method A: LLM-only extraction ─────────────────────────────────────────────

def _extract_llm_only(text: str, url: str) -> ExtractionResult:
    """Extraction using Groq LLM only (no local model)."""
    from groq import Groq
    from config import GROQ_API_KEY
    import os

    start = time.perf_counter()
    error = None
    entities = []
    relations = []

    prompt = f"""Extract all named entities and their relationships from the following news article.

Return JSON in this exact format:
{{
  "entities": [{{"name": "...", "type": "PERSON|COUNTRY|ORGANIZATION|EVENT|POLICY|TECHNOLOGY|WEAPON|TREATY", "confidence": 0.0}}],
  "relations": [{{"source": "...", "target": "...", "type": "..."}}]
}}

Article:
{text[:3000]}"""

    try:
        client = Groq(api_key=GROQ_API_KEY or os.getenv("GROQ_API_KEY", ""))
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        raw = json.loads(resp.choices[0].message.content or "{}")
        entities = raw.get("entities", [])
        relations = raw.get("relations", [])
    except Exception as e:
        error = str(e)
        logger.warning(f"LLM-only extraction failed: {e}")

    duration_ms = (time.perf_counter() - start) * 1000
    hallucinated = sum(1 for e in entities if _is_hallucinated(e.get("name", ""), text))
    tokens = _estimate_tokens(prompt) + _estimate_tokens(json.dumps({"entities": entities, "relations": relations}))

    return ExtractionResult(
        article_url=url,
        article_len_chars=len(text),
        method="llm_only",
        duration_ms=duration_ms,
        entity_count=len(entities),
        relation_count=len(relations),
        hallucinated_entity_count=hallucinated,
        estimated_tokens=tokens,
        entities=entities,
        error=error,
    )


# ── Method B: GLiNER2 + LLM hybrid ────────────────────────────────────────────

def _extract_hybrid(text: str, url: str) -> ExtractionResult:
    """Hybrid extraction: GLiNER2 for spans, LLM for canonicalization."""
    from agents.extraction import ExtractionAgent
    from scrapers.news_rss import Article as NewsArticle

    start = time.perf_counter()
    error = None
    entities = []
    relations = []

    try:
        # ExtractionAgent.extract() requires an Article object, not a raw string
        article_obj = NewsArticle(url=url, title="", source="benchmark", full_text=text, is_content_extracted=True)
        agent = ExtractionAgent()
        result = agent.extract(article_obj)
        if result:
            # ExtractedEntity has .name, .type, .confidence (not .entity_type)
            entities = [{"name": e.name, "type": e.type, "confidence": e.confidence}
                        for e in (result.entities or [])]
            # ExtractedRelation has .source, .target, .relation (not .relation_type)
            relations = [{"source": r.source, "target": r.target, "type": r.relation}
                         for r in (result.relations or [])]
    except Exception as e:
        error = str(e)
        logger.warning(f"Hybrid extraction failed: {e}")

    duration_ms = (time.perf_counter() - start) * 1000
    hallucinated = sum(1 for e in entities if _is_hallucinated(e.get("name", ""), text))
    # Hybrid uses LLM only for canonicalization: title + entity list prompt (~500 tokens)
    tokens = _estimate_tokens(text[:500]) + 100  # entity list + overhead

    return ExtractionResult(
        article_url=url,
        article_len_chars=len(text),
        method="gliner2_llm_hybrid",
        duration_ms=duration_ms,
        entity_count=len(entities),
        relation_count=len(relations),
        hallucinated_entity_count=hallucinated,
        estimated_tokens=tokens,
        entities=entities,
        error=error,
    )


# ── Method C: GLiNER2 only ────────────────────────────────────────────────────

def _extract_gliner_only(text: str, url: str) -> ExtractionResult:
    """Local GLiNER2 extraction only — no LLM calls.

    Uses the same gliner2 package and model as the production ExtractionAgent
    (fastino/gliner2-base-v1), but skips the LLM canonicalization and enrichment steps.
    """
    from gliner2 import GLiNER2
    from agents.extraction import ENTITY_LABELS, RELATION_LABELS

    start = time.perf_counter()
    error = None
    entities = []
    relations = []

    try:
        gliner = GLiNER2.from_pretrained("fastino/gliner2-base-v1")
        schema = gliner.create_schema().entities(ENTITY_LABELS).relations(RELATION_LABELS)
        raw = gliner.extract(text[:2000], schema, include_confidence=True)

        seen: set[str] = set()
        for etype, items in raw.get("entities", {}).items():
            for item in items:
                name = item["text"] if isinstance(item, dict) else str(item)
                conf = item.get("confidence", 1.0) if isinstance(item, dict) else 1.0
                if name not in seen and conf >= 0.3:
                    seen.add(name)
                    entities.append({"name": name, "type": etype, "confidence": conf})

        for rel_type, pairs in raw.get("relation_extraction", {}).items():
            for pair in pairs:
                if isinstance(pair, dict):
                    src = pair.get("head", {}).get("text", "") if isinstance(pair.get("head"), dict) else ""
                    tgt = pair.get("tail", {}).get("text", "") if isinstance(pair.get("tail"), dict) else ""
                elif isinstance(pair, (list, tuple)) and len(pair) >= 2:
                    src, tgt = str(pair[0]), str(pair[1])
                else:
                    continue
                if src and tgt:
                    relations.append({"source": src, "target": tgt, "type": rel_type})
    except Exception as e:
        error = str(e)
        logger.warning(f"GLiNER2-only extraction failed: {e}")

    duration_ms = (time.perf_counter() - start) * 1000
    hallucinated = sum(1 for e in entities if _is_hallucinated(e.get("name", ""), text))

    return ExtractionResult(
        article_url=url,
        article_len_chars=len(text),
        method="gliner2_only",
        duration_ms=duration_ms,
        entity_count=len(entities),
        relation_count=len(relations),
        hallucinated_entity_count=hallucinated,
        estimated_tokens=0,  # No LLM calls
        entities=entities,
        error=error,
    )


# ── Benchmark runner ──────────────────────────────────────────────────────────

def run_benchmark(n_articles: int = 20) -> dict:
    """Run all three methods on N articles from the database."""
    db = SessionLocal()
    try:
        rows = db.scalars(
            select(ScrapedArticle)
            .where(ScrapedArticle.full_text.isnot(None))
            .where(ScrapedArticle.full_text != "")
            .order_by(desc(ScrapedArticle.scraped_at))
            .limit(n_articles)
        ).all()
    finally:
        db.close()

    if not rows:
        logger.error("No articles found in database. Run the producer first.")
        return {}

    articles = [(row.full_text, row.url) for row in rows if row.full_text]
    logger.info(f"Benchmarking {len(articles)} articles across 3 methods...")

    results_by_method: dict[str, list[ExtractionResult]] = {
        "llm_only": [],
        "gliner2_llm_hybrid": [],
        "gliner2_only": [],
    }

    for i, (text, url) in enumerate(articles):
        logger.info(f"  Article {i+1}/{len(articles)}: {url[:70]}...")

        # Run all three methods
        r_llm = _extract_llm_only(text, url)
        results_by_method["llm_only"].append(r_llm)

        r_hybrid = _extract_hybrid(text, url)
        results_by_method["gliner2_llm_hybrid"].append(r_hybrid)

        r_gliner = _extract_gliner_only(text, url)
        results_by_method["gliner2_only"].append(r_gliner)

        logger.info(
            f"    LLM-only: {r_llm.duration_ms:.0f}ms, {r_llm.entity_count} entities, "
            f"{r_llm.hallucinated_entity_count} hallucinated"
        )
        logger.info(
            f"    Hybrid:   {r_hybrid.duration_ms:.0f}ms, {r_hybrid.entity_count} entities, "
            f"{r_hybrid.hallucinated_entity_count} hallucinated"
        )
        logger.info(
            f"    GLiNER2:  {r_gliner.duration_ms:.0f}ms, {r_gliner.entity_count} entities, "
            f"{r_gliner.hallucinated_entity_count} hallucinated"
        )

    # Compute summaries
    summaries = []
    for method, results in results_by_method.items():
        valid = [r for r in results if r.error is None]
        if not valid:
            continue
        durations = [r.duration_ms for r in valid]
        all_entities = sum(r.entity_count for r in valid)
        all_hallucinated = sum(r.hallucinated_entity_count for r in valid)
        hallucination_rate = (all_hallucinated / all_entities * 100) if all_entities > 0 else 0.0

        summary = BenchmarkSummary(
            method=method,
            n_articles=len(valid),
            avg_duration_ms=mean(durations),
            std_duration_ms=stdev(durations) if len(durations) > 1 else 0.0,
            avg_entity_count=mean(r.entity_count for r in valid),
            avg_relation_count=mean(r.relation_count for r in valid),
            hallucination_rate_pct=hallucination_rate,
            avg_tokens=mean(r.estimated_tokens for r in valid),
            total_errors=len([r for r in results if r.error]),
        )
        summaries.append(summary)

    # Print comparison table
    print("\n" + "=" * 80)
    print("EXTRACTION BENCHMARK RESULTS")
    print("=" * 80)
    print(f"{'Metric':<35} {'LLM-Only':>12} {'Hybrid (ours)':>14} {'GLiNER2-Only':>13}")
    print("-" * 80)

    hybrid = next((s for s in summaries if s.method == "gliner2_llm_hybrid"), None)
    llm = next((s for s in summaries if s.method == "llm_only"), None)
    gliner = next((s for s in summaries if s.method == "gliner2_only"), None)

    def _fmt(s: Optional[BenchmarkSummary], attr: str, fmt: str = ".1f") -> str:
        if s is None:
            return "N/A".rjust(12)
        val = getattr(s, attr)
        return format(val, fmt).rjust(12)

    print(f"{'Avg extraction time (ms)':<35} {_fmt(llm,'avg_duration_ms')} {_fmt(hybrid,'avg_duration_ms')} {_fmt(gliner,'avg_duration_ms')}")
    print(f"{'Avg entities per article':<35} {_fmt(llm,'avg_entity_count')} {_fmt(hybrid,'avg_entity_count')} {_fmt(gliner,'avg_entity_count')}")
    print(f"{'Avg relations per article':<35} {_fmt(llm,'avg_relation_count')} {_fmt(hybrid,'avg_relation_count')} {_fmt(gliner,'avg_relation_count')}")
    print(f"{'Hallucination rate (%)':<35} {_fmt(llm,'hallucination_rate_pct')} {_fmt(hybrid,'hallucination_rate_pct')} {_fmt(gliner,'hallucination_rate_pct')}")
    print(f"{'Avg estimated tokens':<35} {_fmt(llm,'avg_tokens','.0f')} {_fmt(hybrid,'avg_tokens','.0f')} {_fmt(gliner,'avg_tokens','.0f')}")
    print(f"{'Errors':<35} {_fmt(llm,'total_errors','.0f')} {_fmt(hybrid,'total_errors','.0f')} {_fmt(gliner,'total_errors','.0f')}")
    print("=" * 80)

    if llm and hybrid:
        speedup = llm.avg_duration_ms / hybrid.avg_duration_ms if hybrid.avg_duration_ms > 0 else 0
        halluc_reduction = (llm.hallucination_rate_pct - hybrid.hallucination_rate_pct)
        token_reduction = (llm.avg_tokens - hybrid.avg_tokens) / llm.avg_tokens * 100 if llm.avg_tokens > 0 else 0
        print(f"\nHybrid vs LLM-Only:")
        print(f"  Speed:        {speedup:.1f}x faster")
        print(f"  Hallucination:{halluc_reduction:+.1f}pp reduction")
        print(f"  Token cost:   {token_reduction:.0f}% cheaper")
    print("=" * 80 + "\n")

    return {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "n_articles": len(articles),
        "summaries": [asdict(s) for s in summaries],
        "per_article": {
            method: [asdict(r) for r in results]
            for method, results in results_by_method.items()
        },
    }


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Benchmark extraction pipelines")
    parser.add_argument("--articles", type=int, default=20, help="Number of articles to benchmark (default: 20)")
    parser.add_argument("--output", type=str, default="", help="Optional: save JSON results to file")
    args = parser.parse_args()

    results = run_benchmark(n_articles=args.articles)

    if args.output and results:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        logger.info(f"Results saved to {args.output}")


if __name__ == "__main__":
    main()
