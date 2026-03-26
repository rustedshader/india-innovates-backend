"""
Verify that all feeds in the updated scraper configuration work correctly.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scrapers.news_rss import create_default_scraper

logging.basicConfig(level=logging.WARNING, format="%(message)s")

def verify_feeds():
    """Test all feeds from the default scraper configuration."""
    scraper = create_default_scraper()

    print("=" * 80)
    print("VERIFICATION: Updated RSS Feed Configuration")
    print("=" * 80)
    print()

    total_feeds = len(scraper._feeds)
    print(f"Total feeds configured: {total_feeds}")
    print()

    working = 0
    failing = 0
    failed_feeds = []

    for i, (source_name, rss_url) in enumerate(scraper._feeds, 1):
        print(f"[{i}/{total_feeds}] Testing: {source_name}")
        print(f"    URL: {rss_url}")

        try:
            articles = scraper.fetch_feed(
                source_name,
                rss_url,
                include_seen=True,
                max_per_feed=3
            )

            if not articles:
                print(f"    ❌ FAIL: No articles found")
                failing += 1
                failed_feeds.append((source_name, rss_url, "No articles"))
            else:
                # Try to extract content from first article
                test_article = articles[0]
                success = test_article.extract_content()

                if success and test_article.full_text:
                    print(f"    ✅ SUCCESS: {len(articles)} articles, scraped {len(test_article.full_text)} chars")
                    working += 1
                else:
                    print(f"    ⚠️  PARTIAL: RSS works but scraping failed")
                    failing += 1
                    failed_feeds.append((source_name, rss_url, "Scraping failed"))

        except Exception as e:
            print(f"    ❌ FAIL: {str(e)[:100]}")
            failing += 1
            failed_feeds.append((source_name, rss_url, str(e)[:100]))

        print()

    print("=" * 80)
    print("VERIFICATION SUMMARY")
    print("=" * 80)
    print(f"Total feeds: {total_feeds}")
    print(f"✅ Working: {working} ({working/total_feeds*100:.1f}%)")
    print(f"❌ Failing: {failing} ({failing/total_feeds*100:.1f}%)")

    if failed_feeds:
        print()
        print("=" * 80)
        print(f"FAILING FEEDS ({len(failed_feeds)})")
        print("=" * 80)
        for source, url, reason in failed_feeds:
            print(f"\n❌ {source}")
            print(f"   URL: {url}")
            print(f"   Reason: {reason}")

    print()
    print("=" * 80)

    return working, failing

if __name__ == "__main__":
    working, failing = verify_feeds()
    sys.exit(0 if failing == 0 else 1)
