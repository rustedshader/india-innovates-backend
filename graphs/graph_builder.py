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
        """Save resolved extractions to Neo4j."""
        with self.driver.session() as s:
            for article, extraction in extractions:
                # Create Article node
                s.run("""
                    MERGE (a:Article {url: $url})
                    SET a.title = $title, a.source = $source, a.pub_date = $pub_date
                """, url=article.url, title=article.title,
                    source=article.source, pub_date=article.pub_date)

                # Create Entity nodes + EVIDENCES links from Article
                for entity in extraction.entities:
                    s.run("""
                        MERGE (e:Entity {name: $name})
                        ON CREATE SET e.type = $type, e.first_seen = $pub_date
                        SET e.last_updated = $pub_date
                        WITH e
                        MATCH (a:Article {url: $url})
                        MERGE (a)-[:EVIDENCES]->(e)
                    """, name=entity.name, type=entity.type,
                        pub_date=article.pub_date, url=article.url)

                # Create typed relationships between entities
                for rel in extraction.relations:
                    s.run("""
                        MATCH (src:Entity {name: $source}), (tgt:Entity {name: $target})
                        MERGE (src)-[r:RELATES_TO {type: $relation}]->(tgt)
                        ON CREATE SET r.since = $temporal, r.confidence = $confidence,
                                      r.causal = $causal, r.current = true
                        SET r.confidence = CASE
                            WHEN r.confidence IS NOT NULL THEN r.confidence + $confidence
                            ELSE $confidence END
                        WITH r
                        MATCH (a:Article {url: $url})
                        MERGE (a)-[:EVIDENCES_REL {relation_type: $relation}]->(src)
                    """, source=rel.source, target=rel.target, relation=rel.relation,
                        temporal=rel.temporal, confidence=rel.confidence,
                        causal=rel.causal, url=article.url)

                # Create Event nodes
                for event in extraction.events:
                    s.run("""
                        MERGE (ev:Event {name: $name})
                        ON CREATE SET ev.date = $date, ev.status = $status
                        SET ev.status = $status, ev.date = $date
                    """, name=event.name, date=event.date, status=event.status)

                    # Link entities to events
                    for entity_name in event.entities:
                        s.run("""
                            MATCH (e:Entity {name: $entity}), (ev:Event {name: $event})
                            MERGE (e)-[:INVOLVED_IN]->(ev)
                        """, entity=entity_name, event=event.name)

                    # Article evidences event
                    s.run("""
                        MATCH (a:Article {url: $url}), (ev:Event {name: $event})
                        MERGE (a)-[:EVIDENCES]->(ev)
                    """, url=article.url, event=event.name)

        # Log summary
        all_entities = {e.name for _, ext in extractions for e in ext.entities}
        all_rels = sum(len(ext.relations) for _, ext in extractions)
        all_events = {ev.name for _, ext in extractions for ev in ext.events}
        logger.info(
            f"Neo4j: saved {len(extractions)} articles, "
            f"{len(all_entities)} unique entities, {all_rels} relations, "
            f"{len(all_events)} events"
        )

    def run(self, max_workers: int = 5, max_per_feed: int = 0):
        # Step 1: Scrape
        logger.info("=" * 60)
        logger.info("STEP 1: Scraping RSS feeds")
        logger.info("=" * 60)
        articles = self.scraper.fetch_all(max_per_feed=max_per_feed)
        logger.info(f"Fetched {len(articles)} articles")

        self.scraper.extract_all_content(articles, max_workers=max_workers)
        new_articles = self.scraper.get_new_articles(articles)
        logger.info(f"{len(new_articles)} new articles with content")

        if not new_articles:
            logger.info("No new articles to process")
            return 0

        # Step 2: Extract (per-article)
        logger.info("=" * 60)
        logger.info("STEP 2: Extraction Agent (per-article)")
        logger.info("=" * 60)
        extractions = self.extraction_agent.extract_batch(new_articles)

        if not extractions:
            logger.info("No extractions produced")
            return 0

        # Step 3: Resolve entities (cross-article)
        logger.info("=" * 60)
        logger.info("STEP 3: Resolution Agent (3-tier)")
        logger.info("=" * 60)
        extractions = self.resolution_agent.resolve(extractions)

        # Step 4: Temporal processing
        logger.info("=" * 60)
        logger.info("STEP 4: Temporal Agent")
        logger.info("=" * 60)
        extractions = self.temporal_agent.process(extractions)

        # Step 5: Save to Neo4j + Postgres
        logger.info("=" * 60)
        logger.info("STEP 5: Saving to Neo4j + Postgres")
        logger.info("=" * 60)
        self.save_to_neo4j(extractions)
        self._save_articles_to_postgres([art for art, _ in extractions])

        logger.info("=" * 60)
        logger.info(f"DONE — {len(extractions)} articles processed")
        logger.info("=" * 60)
        return len(extractions)


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
