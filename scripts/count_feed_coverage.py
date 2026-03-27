"""
Diagnostic: compare what's currently available in RSS feeds (28-day window)
vs what's already stored in Postgres.

Run with:
    uv run python scripts/count_feed_coverage.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime, timedelta, timezone
from collections import defaultdict

from sqlalchemy import select, func
from models.database import SessionLocal
from models.scraped_article import ScrapedArticle
from scrapers.news_rss import create_default_scraper


CUTOFF = datetime.now(timezone.utc) - timedelta(days=28)


def count_in_db() -> dict[str, int]:
    """Count articles per source in Postgres scraped within the last 28 days."""
    db = SessionLocal()
    try:
        rows = db.execute(
            select(ScrapedArticle.source, func.count(ScrapedArticle.id))
            .where(ScrapedArticle.scraped_at >= CUTOFF)
            .group_by(ScrapedArticle.source)
            .order_by(ScrapedArticle.source)
        ).all()
        return {source: count for source, count in rows}
    finally:
        db.close()


def count_total_in_db() -> int:
    db = SessionLocal()
    try:
        return db.scalar(select(func.count(ScrapedArticle.id)))
    finally:
        db.close()


def count_in_feeds() -> dict[str, int]:
    """
    Fetch all feeds with include_seen=True so deduplication doesn't hide anything.
    Reports how many articles each feed currently exposes within the 28-day window.
    """
    scraper = create_default_scraper()
    # include_seen=True: ignore the seen-URL filter so we see everything the feed has
    # days=28: still apply the date cutoff
    articles = scraper.fetch_all(include_seen=True, days=28)

    by_source: dict[str, int] = defaultdict(int)
    for a in articles:
        by_source[a.source] += 1
    return dict(by_source)


def main():
    print(f"\nCutoff date: {CUTOFF.strftime('%Y-%m-%d %H:%M UTC')}  (last 28 days)\n")

    print("Fetching live RSS feeds (include_seen=True, days=28)…")
    feed_counts = count_in_feeds()
    total_in_feeds = sum(feed_counts.values())

    print("Querying Postgres for articles scraped in the last 28 days…")
    db_counts = count_in_db()
    total_in_db = sum(db_counts.values())
    total_all_time = count_total_in_db()

    # Combine all sources
    all_sources = sorted(set(feed_counts) | set(db_counts))

    col = 26
    print(f"\n{'Source':<{col}} {'In feeds now':>14} {'In DB (28d)':>12} {'Gap':>6}")
    print("-" * (col + 36))
    for src in all_sources:
        in_feed = feed_counts.get(src, 0)
        in_db   = db_counts.get(src, 0)
        gap     = in_feed - in_db   # positive = feeds have articles not yet in DB
        gap_str = f"+{gap}" if gap > 0 else str(gap)
        print(f"{src:<{col}} {in_feed:>14} {in_db:>12} {gap_str:>6}")

    print("-" * (col + 36))
    print(f"{'TOTAL':<{col}} {total_in_feeds:>14} {total_in_db:>12}")
    print(f"\nTotal articles in DB (all time): {total_all_time}")
    print()

    if total_in_feeds == 0:
        print("NOTE: 0 articles found in feeds. Either all feeds are unreachable,")
        print("      or every article is outside the 28-day window.")
    elif total_in_feeds <= total_in_db:
        print("STATUS: DB coverage looks complete — no unseen articles in feeds right now.")
        print(f"        The producer shows 0 new articles because it has already scraped")
        print(f"        everything available within the 28-day window.")
    else:
        gap = total_in_feeds - total_in_db
        print(f"STATUS: {gap} articles in feeds are NOT yet in DB — run the producer to capture them.")


if __name__ == "__main__":
    main()
