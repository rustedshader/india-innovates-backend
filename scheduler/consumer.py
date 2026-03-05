"""Kafka consumer — batches articles and runs the extraction pipeline.

Run as a standalone process:
    python -m scheduler.consumer
"""

import json
import logging
import signal
import time

import redis
from kafka import KafkaConsumer

from config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_TOPIC,
    KAFKA_BATCH_TIMEOUT_SECONDS,
    KAFKA_BATCH_MAX_SIZE,
    REDIS_HOST,
    REDIS_PORT,
)
from graphs.graph_builder import GraphBuilder
from scrapers.news_rss import Article

LIVE_FEED_CHANNEL = "india-innovates:live-feed"

logger = logging.getLogger(__name__)

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    _shutdown = True


def _deserialize_article(data: dict) -> Article:
    """Convert a JSON dict back into an Article dataclass."""
    return Article(
        url=data["url"],
        title=data["title"],
        source=data["source"],
        description=data.get("description", ""),
        pub_date=data.get("pub_date", ""),
        guid=data.get("guid", ""),
        full_text=data.get("full_text", ""),
        authors=data.get("authors", []),
        top_image=data.get("top_image", ""),
        content_hash=data.get("content_hash", ""),
        is_content_extracted=data.get("is_content_extracted", False),
    )


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info("=" * 60)
    logger.info("Starting Kafka Consumer")
    logger.info(f"  Kafka: {KAFKA_BOOTSTRAP_SERVERS}")
    logger.info(f"  Topic: {KAFKA_TOPIC}")
    logger.info(f"  Batch timeout: {KAFKA_BATCH_TIMEOUT_SECONDS}s")
    logger.info(f"  Batch max size: {KAFKA_BATCH_MAX_SIZE}")
    logger.info("=" * 60)

    consumer = KafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        group_id="india-innovates-pipeline",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        consumer_timeout_ms=1000,  # poll returns after 1s if no messages
        max_poll_interval_ms=1800000,  # 30min — processing a batch with LLM calls is slow
        session_timeout_ms=60000,  # 60s heartbeat timeout
    )

    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    logger.info("Initializing GraphBuilder (loading models)...")
    builder = GraphBuilder()
    logger.info("GraphBuilder ready.")

    try:
        while not _shutdown:
            batch: list[Article] = []
            batch_start = time.time()

            # Accumulate a batch
            while (
                not _shutdown
                and len(batch) < KAFKA_BATCH_MAX_SIZE
                and (time.time() - batch_start) < KAFKA_BATCH_TIMEOUT_SECONDS
            ):
                # poll() returns {TopicPartition: [records]}
                records = consumer.poll(timeout_ms=1000, max_records=KAFKA_BATCH_MAX_SIZE - len(batch))

                for tp, messages in records.items():
                    for message in messages:
                        try:
                            article = _deserialize_article(message.value)
                            batch.append(article)
                        except Exception as e:
                            logger.error(f"Failed to deserialize message: {e}")

            if not batch:
                continue

            # Process the batch through the full pipeline
            logger.info(f"Processing batch of {len(batch)} articles")
            try:
                count = builder.process_articles(batch)
                logger.info(f"Batch complete: {count} articles processed successfully")

                # Publish live feed events for each article
                for article in batch:
                    try:
                        event = json.dumps({
                            "url": article.url,
                            "title": article.title,
                            "source": article.source,
                            "thumbnail": article.top_image or "",
                            "pub_date": article.pub_date or "",
                            "status": "ingested",
                            "timestamp": time.time(),
                        })
                        r.publish(LIVE_FEED_CHANNEL, event)
                    except Exception as e:
                        logger.debug(f"Failed to publish live feed event: {e}")

                # Commit offsets after successful processing
                consumer.commit()
            except Exception as e:
                logger.error(f"Batch processing failed: {e}", exc_info=True)
                # Don't commit — messages will be redelivered on next poll

    finally:
        consumer.close()
        builder.close()
        logger.info("Consumer shut down.")


if __name__ == "__main__":
    main()
