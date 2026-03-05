"""Report scheduler — autonomously generates domain intelligence reports.

Run as a standalone process:
    python -m scheduler.report_scheduler
"""

import json
import logging
import signal
import time

from config import REDIS_HOST, REDIS_PORT, REPORT_INTERVAL_SECONDS, REPORT_DATE_RANGE
from agents.report import ReportAgent, DOMAIN_CONFIG
from models.database import Base, engine, SessionLocal
from models.domain_report import DomainReport

logger = logging.getLogger(__name__)

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    _shutdown = True


def _save_report(domain: str, date_range: str, report: dict):
    """Save a generated report to Postgres."""
    db = SessionLocal()
    try:
        entry = DomainReport(
            domain=domain,
            date_range=date_range,
            content=json.dumps(report, ensure_ascii=False),
        )
        db.add(entry)
        db.commit()
        logger.info(f"Saved {domain} report to Postgres (id={entry.id})")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save {domain} report: {e}")
    finally:
        db.close()


def _publish_notification(domain: str):
    """Publish a live-feed notification when a new report is generated."""
    try:
        import redis
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        r.publish("india-innovates:live-feed", json.dumps({
            "type": "report",
            "domain": domain,
            "status": "generated",
            "timestamp": time.time(),
        }))
        r.close()
    except Exception as e:
        logger.debug(f"Failed to publish report notification: {e}")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    domains = list(DOMAIN_CONFIG.keys())

    logger.info("=" * 60)
    logger.info("Starting Report Scheduler")
    logger.info(f"  Domains: {', '.join(domains)}")
    logger.info(f"  Interval: {REPORT_INTERVAL_SECONDS}s")
    logger.info(f"  Date range: {REPORT_DATE_RANGE}")
    logger.info("=" * 60)

    # Ensure table exists
    Base.metadata.create_all(engine)
    logger.info("Database tables ensured.")

    # Initialize agent (loads LLM config)
    agent = ReportAgent()
    logger.info("ReportAgent initialized.")

    try:
        while not _shutdown:
            cycle_start = time.time()

            for domain in domains:
                if _shutdown:
                    break

                logger.info(f"Generating {domain.upper()} report...")
                try:
                    report = agent.generate(domain, date_range=REPORT_DATE_RANGE)
                    _save_report(domain, REPORT_DATE_RANGE, report)
                    _publish_notification(domain)
                    logger.info(f"✓ {domain.upper()} report complete")
                except Exception as e:
                    logger.error(f"✗ {domain.upper()} report failed: {e}", exc_info=True)

            elapsed = time.time() - cycle_start
            logger.info(f"Report cycle complete in {elapsed:.1f}s — sleeping {REPORT_INTERVAL_SECONDS}s")

            # Sleep in small increments to check shutdown flag
            sleep_end = time.time() + REPORT_INTERVAL_SECONDS
            while not _shutdown and time.time() < sleep_end:
                time.sleep(5)

    finally:
        agent.close()
        logger.info("Report scheduler shut down.")


if __name__ == "__main__":
    main()
