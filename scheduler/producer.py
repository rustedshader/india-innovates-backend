"""Kafka producer — periodically scrapes RSS feeds and publishes articles.

Run as a standalone process:
    python -m scheduler.producer
"""

import json
import logging
import signal
import time

import redis
from kafka import KafkaProducer
from sqlalchemy import select

from config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_TOPIC,
    REDIS_HOST,
    REDIS_PORT,
    SCRAPE_INTERVAL_SECONDS,
)
from models.database import SessionLocal
from models.scraped_article import ScrapedArticle
from scrapers.news_rss import create_default_scraper

logger = logging.getLogger(__name__)

_shutdown = False

REDIS_SEEN_KEY = "india-innovates:seen_urls"


def _handle_signal(signum, frame):
    global _shutdown
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    _shutdown = True


def _seed_redis_from_postgres(r: redis.Redis) -> int:
    """Seed the Redis seen-URLs set from Postgres (on first startup)."""
    if r.scard(REDIS_SEEN_KEY) > 0:
        count = r.scard(REDIS_SEEN_KEY)
        logger.info(f"Redis already has {count} seen URLs, skipping Postgres seed")
        return count

    db = SessionLocal()
    try:
        urls = db.scalars(select(ScrapedArticle.url)).all()
        if urls:
            r.sadd(REDIS_SEEN_KEY, *urls)
        logger.info(f"Seeded Redis with {len(urls)} URLs from Postgres")
        return len(urls)
    finally:
        db.close()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info("=" * 60)
    logger.info("Starting Kafka Producer")
    logger.info(f"  Kafka: {KAFKA_BOOTSTRAP_SERVERS}")
    logger.info(f"  Topic: {KAFKA_TOPIC}")
    logger.info(f"  Redis: {REDIS_HOST}:{REDIS_PORT}")
    logger.info(f"  Scrape interval: {SCRAPE_INTERVAL_SECONDS}s")
    logger.info("=" * 60)

    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    _seed_redis_from_postgres(r)

    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        acks="all",
        retries=3,
    )

    scraper = create_default_scraper()

    # Mark already-seen URLs in scraper from Redis
    seen_urls = r.smembers(REDIS_SEEN_KEY)
    scraper.mark_seen(seen_urls)

    while not _shutdown:
        try:
            logger.info("--- Scrape cycle starting ---")

            # Fetch RSS metadata
            articles = scraper.fetch_all()
            logger.info(f"Fetched {len(articles)} articles from RSS feeds")

            if articles:
                # Extract full content
                scraper.extract_all_content(articles, max_workers=5)
                new_articles = scraper.get_new_articles(articles)
                logger.info(f"{len(new_articles)} new articles with content")

                # Publish each article to Kafka
                published = 0
                for article in new_articles:
                    # Skip if already seen (cross-process dedup via Redis)
                    if r.sismember(REDIS_SEEN_KEY, article.url):
                        continue

                    try:
                        producer.send(KAFKA_TOPIC, value=article.to_dict())
                        r.sadd(REDIS_SEEN_KEY, article.url)
                        published += 1
                    except Exception as e:
                        logger.error(f"Failed to publish article {article.url}: {e}")

                producer.flush()
                logger.info(f"Published {published} articles to Kafka topic '{KAFKA_TOPIC}'")
            else:
                logger.info("No new articles found")

        except Exception as e:
            logger.error(f"Scrape cycle failed: {e}", exc_info=True)

        # Sleep in small increments so we can catch shutdown signals
        logger.info(f"Sleeping {SCRAPE_INTERVAL_SECONDS}s until next scrape...")
        for _ in range(SCRAPE_INTERVAL_SECONDS):
            if _shutdown:
                break
            time.sleep(1)

    producer.close()
    logger.info("Producer shut down.")


if __name__ == "__main__":
    main()
