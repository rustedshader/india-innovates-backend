"""
Check the freshness of RSS feeds - identify feeds with old/stale content.
"""

import logging
import sys
from pathlib import Path
from datetime import datetime, timedelta
from dateutil import parser as date_parser

sys.path.insert(0, str(Path(__file__).parent.parent))

from scrapers.news_rss import create_default_scraper

logging.basicConfig(level=logging.WARNING, format="%(message)s")

def check_feed_freshness():
    """Check how recent the latest articles are from each feed."""
    scraper = create_default_scraper()

    print("=" * 80)
    print("RSS FEED FRESHNESS CHECK")
    print(f"Current Date: {datetime.now().strftime('%Y-%m-%d')}")
    print("=" * 80)
    print()

    now = datetime.now()
    stale_threshold = now - timedelta(days=365)  # 1 year old
    dead_threshold = now - timedelta(days=730)   # 2 years old

    fresh_feeds = []
    stale_feeds = []
    dead_feeds = []

    for i, (source_name, rss_url) in enumerate(scraper._feeds, 1):
        print(f"[{i}/{len(scraper._feeds)}] Checking: {source_name}")

        try:
            articles = scraper.fetch_feed(
                source_name,
                rss_url,
                include_seen=True,
                max_per_feed=5  # Check 5 most recent articles
            )

            if not articles:
                print(f"    ⚠️  No articles found")
                dead_feeds.append((source_name, rss_url, "No articles", None))
                continue

            # Parse pub_date strings to datetime objects
            parsed_dates = []
            for article in articles:
                if article.pub_date:
                    try:
                        parsed_date = date_parser.parse(article.pub_date)
                        # Make timezone-naive for comparison
                        if parsed_date.tzinfo is not None:
                            parsed_date = parsed_date.replace(tzinfo=None)
                        parsed_dates.append(parsed_date)
                    except Exception:
                        pass

            if not parsed_dates:
                print(f"    ⚠️  No valid dates found")
                dead_feeds.append((source_name, rss_url, "No valid dates", None))
                continue

            # Get the most recent article date
            latest_date = max(parsed_dates)
            days_old = (now - latest_date).days

            print(f"    Latest article: {latest_date.strftime('%Y-%m-%d')} ({days_old} days old)")

            if latest_date < dead_threshold:
                print(f"    🪦 DEAD FEED - {days_old} days old (>{730} days)")
                dead_feeds.append((source_name, rss_url, f"{days_old} days old", latest_date))
            elif latest_date < stale_threshold:
                print(f"    ⚠️  STALE FEED - {days_old} days old (>{365} days)")
                stale_feeds.append((source_name, rss_url, f"{days_old} days old", latest_date))
            else:
                print(f"    ✅ FRESH - {days_old} days old")
                fresh_feeds.append((source_name, rss_url, f"{days_old} days old", latest_date))

        except Exception as e:
            print(f"    ❌ Error: {str(e)[:80]}")
            dead_feeds.append((source_name, rss_url, str(e)[:80], None))

        print()

    # Summary
    print("=" * 80)
    print("FRESHNESS SUMMARY")
    print("=" * 80)
    print(f"✅ Fresh feeds (< 1 year): {len(fresh_feeds)}")
    print(f"⚠️  Stale feeds (1-2 years): {len(stale_feeds)}")
    print(f"🪦 Dead feeds (> 2 years or broken): {len(dead_feeds)}")
    print()

    if dead_feeds:
        print("=" * 80)
        print(f"DEAD FEEDS TO REMOVE ({len(dead_feeds)})")
        print("=" * 80)
        for source, url, reason, date in dead_feeds:
            print(f"\n🪦 {source}")
            print(f"   URL: {url}")
            print(f"   Status: {reason}")
            if date:
                print(f"   Last article: {date.strftime('%Y-%m-%d')}")

    if stale_feeds:
        print("\n" + "=" * 80)
        print(f"STALE FEEDS (Consider removing) ({len(stale_feeds)})")
        print("=" * 80)
        for source, url, reason, date in stale_feeds:
            print(f"\n⚠️  {source}")
            print(f"   URL: {url}")
            print(f"   Status: {reason}")
            if date:
                print(f"   Last article: {date.strftime('%Y-%m-%d')}")

    print("\n" + "=" * 80)
    print("END OF FRESHNESS CHECK")
    print("=" * 80)

    return fresh_feeds, stale_feeds, dead_feeds

if __name__ == "__main__":
    fresh, stale, dead = check_feed_freshness()
    sys.exit(0)
