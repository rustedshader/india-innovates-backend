import json
import logging
from collections import defaultdict

from neo4j import GraphDatabase
from sqlalchemy import select

from config import NEO4J_URI, NEO4J_AUTH
from scrapers.news_rss import Article, create_default_scraper
from models.database import SessionLocal
from models.scraped_article import ScrapedArticle
from graphs.schemas import ArticleExtraction
from agents.extraction import ExtractionAgent
from agents.resolution import ResolutionAgent
from agents.temporal import TemporalAgent

logger = logging.getLogger(__name__)


class GraphBuilder:
    def __init__(self, model: str = "openai/gpt-oss-20b"):
        self.extraction_agent = ExtractionAgent(model=model)
        self.resolution_agent = ResolutionAgent(model=model)
        self.temporal_agent = TemporalAgent()
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
        self.scraper = create_default_scraper()
        self._load_seen_urls()

    def _load_seen_urls(self):
        db = SessionLocal()
        try:
            urls = db.scalars(select(ScrapedArticle.url)).all()
            self.scraper.mark_seen(urls)
            logger.info(f"Loaded {len(urls)} already-processed URLs")
        finally:
            db.close()

    def _save_articles_to_postgres(self, articles: list[Article]):
        db = SessionLocal()
        try:
            for article in articles:
                try:
                    db.add(ScrapedArticle(
                        url=article.url, content_hash=article.content_hash,
                        title=article.title, source=article.source,
                        description=article.description, pub_date=article.pub_date,
                        guid=article.guid, full_text=article.full_text,
                        authors=json.dumps(article.authors), top_image=article.top_image,
                        is_content_extracted=article.is_content_extracted,
                    ))
                    db.flush()
                except Exception:
                    db.rollback()
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Postgres save failed: {e}")
        finally:
            db.close()

    def close(self):
        self.driver.close()

    def save_to_neo4j(self, extractions: list[tuple[Article, ArticleExtraction]]):
        """Save resolved extractions to Neo4j using batched UNWIND queries."""

        # --- Collect all data into flat lists for batching ---
        articles_data = []
        entities_data = []
        relations_data = []
        events_data = []
        event_entity_links = []
        event_article_links = []

        for article, extraction in extractions:
            articles_data.append({
                "url": article.url, "title": article.title,
                "source": article.source, "pub_date": article.pub_date,
            })

            for entity in extraction.entities:
                entities_data.append({
                    "name": entity.name, "type": entity.type,
                    "pub_date": article.pub_date, "url": article.url,
                })

            for rel in extraction.relations:
                relations_data.append({
                    "source": rel.source, "target": rel.target,
                    "relation": rel.relation, "temporal": rel.temporal,
                    "confidence": rel.confidence, "causal": rel.causal,
                    "url": article.url,
                })

            for event in extraction.events:
                events_data.append({
                    "name": event.name, "date": event.date, "status": event.status,
                    "url": article.url,
                })
                for entity_name in event.entities:
                    event_entity_links.append({
                        "entity": entity_name, "event": event.name,
                    })
                event_article_links.append({
                    "url": article.url, "event": event.name,
                })

        # --- Execute batched queries ---
        with self.driver.session() as s:
            # 1. Create/update Article nodes
            if articles_data:
                s.run("""
                    UNWIND $rows AS row
                    MERGE (a:Article {url: row.url})
                    SET a.title = row.title, a.source = row.source, a.pub_date = row.pub_date
                """, rows=articles_data)

            # 2. Create Entity nodes + EVIDENCES links
            if entities_data:
                s.run("""
                    UNWIND $rows AS row
                    MERGE (e:Entity {name: row.name})
                    ON CREATE SET e.type = row.type, e.first_seen = row.pub_date
                    SET e.last_updated = row.pub_date
                    WITH e, row
                    MATCH (a:Article {url: row.url})
                    MERGE (a)-[:EVIDENCES]->(e)
                """, rows=entities_data)

            # 3. Create relationships (confidence averaged, capped at 1.0)
            if relations_data:
                s.run("""
                    UNWIND $rows AS row
                    MATCH (src:Entity {name: row.source}), (tgt:Entity {name: row.target})
                    MERGE (src)-[r:RELATES_TO {type: row.relation}]->(tgt)
                    ON CREATE SET r.since = row.temporal, r.confidence = row.confidence,
                                  r.causal = row.causal, r.current = true, r.evidence_count = 1
                    ON MATCH SET
                        r.evidence_count = coalesce(r.evidence_count, 1) + 1,
                        r.confidence = CASE
                            WHEN r.confidence IS NULL THEN row.confidence
                            ELSE toFloat(
                                (coalesce(r.confidence, 0) * coalesce(r.evidence_count, 1) + row.confidence)
                                / (coalesce(r.evidence_count, 1) + 1)
                            )
                        END,
                        r.causal = CASE WHEN row.causal THEN true ELSE r.causal END
                    WITH src, row
                    MATCH (a:Article {url: row.url})
                    MERGE (a)-[:EVIDENCES_REL {relation_type: row.relation}]->(src)
                """, rows=relations_data)

            # 4. Create Event nodes + Article EVIDENCES
            if events_data:
                s.run("""
                    UNWIND $rows AS row
                    MERGE (ev:Event {name: row.name})
                    ON CREATE SET ev.date = row.date, ev.status = row.status
                    SET ev.status = row.status, ev.date = row.date
                """, rows=events_data)

            # 5. Link entities to events
            if event_entity_links:
                s.run("""
                    UNWIND $rows AS row
                    MATCH (e:Entity {name: row.entity}), (ev:Event {name: row.event})
                    MERGE (e)-[:INVOLVED_IN]->(ev)
                """, rows=event_entity_links)

            # 6. Article EVIDENCES Event
            if event_article_links:
                s.run("""
                    UNWIND $rows AS row
                    MATCH (a:Article {url: row.url}), (ev:Event {name: row.event})
                    MERGE (a)-[:EVIDENCES]->(ev)
                """, rows=event_article_links)

        # Log summary
        all_entities = {e.name for _, ext in extractions for e in ext.entities}
        all_rels = sum(len(ext.relations) for _, ext in extractions)
        all_events = {ev.name for _, ext in extractions for ev in ext.events}
        logger.info(
            f"Neo4j: saved {len(extractions)} articles, "
            f"{len(all_entities)} unique entities, {all_rels} relations, "
            f"{len(all_events)} events"
        )

    def process_articles(self, articles: list[Article]) -> int:
        """Run the full extraction → resolution → temporal → save pipeline.

        This is the core processing logic, reusable by both the CLI `run()`
        method and the Kafka consumer.

        Args:
            articles: List of Article objects with full_text already extracted.

        Returns:
            Number of articles successfully processed.
        """
        if not articles:
            logger.info("No articles to process")
            return 0

        # Step 1: Extract (per-article)
        logger.info("=" * 60)
        logger.info("STEP 1: Extraction Agent (per-article)")
        logger.info("=" * 60)
        extractions = self.extraction_agent.extract_batch(articles)

        if not extractions:
            logger.info("No extractions produced")
            return 0

        # Step 2: Resolve entities (cross-article)
        logger.info("=" * 60)
        logger.info("STEP 2: Resolution Agent (3-tier)")
        logger.info("=" * 60)
        extractions = self.resolution_agent.resolve(extractions)

        # Step 3: Temporal processing
        logger.info("=" * 60)
        logger.info("STEP 3: Temporal Agent")
        logger.info("=" * 60)
        extractions = self.temporal_agent.process(extractions)

        # Step 4: Save to Neo4j + Postgres
        logger.info("=" * 60)
        logger.info("STEP 4: Saving to Neo4j + Postgres")
        logger.info("=" * 60)
        self.save_to_neo4j(extractions)
        self._save_articles_to_postgres([art for art, _ in extractions])

        logger.info("=" * 60)
        logger.info(f"DONE — {len(extractions)} articles processed")
        logger.info("=" * 60)
        return len(extractions)

    def run(self, max_workers: int = 5, max_per_feed: int = 0):
        """Scrape RSS feeds and process all new articles."""
        logger.info("=" * 60)
        logger.info("Scraping RSS feeds")
        logger.info("=" * 60)
        articles = self.scraper.fetch_all(max_per_feed=max_per_feed)
        logger.info(f"Fetched {len(articles)} articles")

        self.scraper.extract_all_content(articles, max_workers=max_workers)
        new_articles = self.scraper.get_new_articles(articles)
        logger.info(f"{len(new_articles)} new articles with content")

        return self.process_articles(new_articles)


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-per-feed", type=int, default=10,
                        help="Max articles per RSS feed (0 = unlimited, default 10)")
    args = parser.parse_args()
    builder = GraphBuilder()
    try:
        builder.run(max_per_feed=args.max_per_feed)
    finally:
        builder.close()
