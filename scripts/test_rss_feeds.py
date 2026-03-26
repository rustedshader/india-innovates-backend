"""
Test all RSS feeds to check which are working and which are failing.
Creates a detailed report of feed health.
"""

import logging
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path so we can import from scrapers
sys.path.insert(0, str(Path(__file__).parent.parent))

from scrapers.news_rss import NewsRSSScraper

logging.basicConfig(
    level=logging.WARNING,  # Suppress INFO logs for cleaner output
    format="%(message)s"
)

def test_all_feeds():
    """Test all configured RSS feeds and generate a report."""

    # Get all feeds from the default scraper
    scraper = NewsRSSScraper()

    # Manually add all feeds (copy from create_default_scraper)
    feeds = [
        # World
        ("Washington Post", "https://feeds.washingtonpost.com/rss/world"),
        ("BBC", "https://feeds.bbci.co.uk/news/world/rss.xml"),

        # India
        ("NDTV", "https://feeds.feedburner.com/ndtvnews-top-stories"),
        ("India Today Nation", "https://www.indiatoday.in/rss/1206514"),
        ("India Today Economy", "https://www.indiatoday.in/rss/1206513"),
        ("India Today World", "https://www.indiatoday.in/rss/1206577"),

        # The Hindu
        ("The Hindu", "https://www.thehindu.com/news/feeder/default.rss"),
        ("The Hindu World", "https://www.thehindu.com/news/international/feeder/default.rss"),
        ("The Hindu States", "https://www.thehindu.com/news/states/feeder/default.rss"),
        ("The Hindu Cities", "https://www.thehindu.com/news/cities/feeder/default.rss"),
        ("The Hindu Economy", "https://www.thehindu.com/business/Economy/feeder/default.rss"),
        ("The Hindu Markets", "https://www.thehindu.com/business/markets/feeder/default.rss"),
        ("The Hindu Budget", "https://www.thehindu.com/business/budget/feeder/default.rss"),

        # Live Mint
        ("Live Mint News", "https://www.livemint.com/rss/news"),
        ("Live Mint Companies", "https://www.livemint.com/rss/companies"),
        ("Live Mint Money", "https://www.livemint.com/rss/money"),
        ("Live Mint Politics", "https://www.livemint.com/rss/politics"),
        ("Live Mint AI", "https://www.livemint.com/rss/AI"),

        # Economic Times
        ("Economic Times", "https://b2b.economictimes.indiatimes.com/rss/recentstories"),
        ("Economic Times Defence", "https://b2b.economictimes.indiatimes.com/rss/defence"),

        # India TV
        ("India TV Top", "https://www.indiatvnews.com/rssnews/topstory.xml"),
        ("India TV Politics", "https://www.indiatvnews.com/rssnews/topstory-politics.xml/"),
        ("India TV World", "https://www.indiatvnews.com/rssnews/topstory-world.xml"),
        ("India TV Entertainment", "https://www.indiatvnews.com/rssnews/topstory-entertainment.xml"),
        ("India TV Sports", "https://www.indiatvnews.com/rssnews/topstory-sports.xml"),
        ("India TV Technology", "https://www.indiatvnews.com/rssnews/topstory-technology.xml"),
        ("India TV Health", "https://www.indiatvnews.com/rssnews/topstory-health.xml"),
        ("India TV Lifestyle", "https://www.indiatvnews.com/rssnews/topstory-lifestyle.xml"),
        ("India TV Business", "https://www.indiatvnews.com/rssnews/topstory-business.xml"),
        ("India TV Education", "https://www.indiatvnews.com/rssnews/topstory-education.xml"),
        ("India TV Crime", "https://www.indiatvnews.com/rssnews/topstory-crime.xml"),

        # PIB (Government)
        ("PIB Top Stories", "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3"),
        ("PIB Defence", "https://pib.gov.in/RssMain.aspx?ModId=7&Lang=1&Regid=3"),
        ("PIB Finance", "https://pib.gov.in/RssMain.aspx?ModId=2&Lang=1&Regid=3"),
        ("PIB External Affairs", "https://pib.gov.in/RssMain.aspx?ModId=3&Lang=1&Regid=3"),
        ("PIB Science Tech", "https://pib.gov.in/RssMain.aspx?ModId=11&Lang=1&Regid=3"),

        # The Print
        ("The Print Defence", "https://theprint.in/category/defence/feed/"),
        ("The Print Security", "https://theprint.in/category/security/feed/"),
        ("The Print Diplomacy", "https://theprint.in/category/diplomacy/feed/"),
        ("The Print Economy", "https://theprint.in/category/economy/feed/"),

        # Others
        ("The Wire", "https://thewire.in/feed"),
        ("WION", "https://www.wionews.com/rss/world.xml"),
        ("WION South Asia", "https://www.wionews.com/rss/south-asia.xml"),
        ("The Wire Geopolitics", "https://thewire.in/category/diplomacy/feed"),
        ("ORF Online", "https://www.orfonline.org/feed/"),
        ("Foreign Affairs", "https://www.foreignaffairs.com/rss/latest.xml"),

        # Financial
        ("Moneycontrol", "https://www.moneycontrol.com/rss/latestnews.xml"),
        ("Moneycontrol Economy", "https://www.moneycontrol.com/rss/economy.xml"),
        ("Business Standard", "https://www.business-standard.com/rss/home_page_top_stories.rss"),
        ("BS Defence", "https://www.business-standard.com/rss/defence.rss"),

        # Technology
        ("The Wire Science", "https://science.thewire.in/feed/"),
        ("Analytics India", "https://analyticsindiamag.com/feed/"),
        ("YourStory Tech", "https://yourstory.com/feed"),

        # Climate
        ("Down To Earth", "https://www.downtoearth.org.in/rss/latest.xml"),
        ("Climate Home News", "https://www.climatechangenews.com/feed/"),
    ]

    print("=" * 80)
    print(f"RSS FEED HEALTH CHECK REPORT")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Total feeds to test: {len(feeds)}")
    print("=" * 80)
    print()

    results = []
    working_count = 0
    failing_count = 0

    for i, (source_name, rss_url) in enumerate(feeds, 1):
        print(f"[{i}/{len(feeds)}] Testing: {source_name}")
        print(f"    URL: {rss_url}")

        # Create a fresh scraper for each test
        test_scraper = NewsRSSScraper()

        # Try to fetch the feed
        try:
            articles = test_scraper.fetch_feed(
                source_name,
                rss_url,
                include_seen=True,
                max_per_feed=3  # Only get 3 articles to test
            )

            if not articles:
                print(f"    ❌ FAIL: No articles found in RSS feed")
                results.append({
                    "source": source_name,
                    "url": rss_url,
                    "status": "FAIL",
                    "reason": "No articles in feed",
                    "article_count": 0,
                    "scrape_success": False,
                })
                failing_count += 1
                print()
                continue

            print(f"    ✓ RSS fetch OK: {len(articles)} articles found")

            # Try to extract content from the first article
            test_article = articles[0]
            print(f"    Testing article: {test_article.title[:60]}...")

            success = test_article.extract_content()

            if success and test_article.full_text:
                text_preview = test_article.full_text[:100].replace('\n', ' ')
                print(f"    ✅ SUCCESS: Scraped {len(test_article.full_text)} chars")
                print(f"    Preview: {text_preview}...")
                results.append({
                    "source": source_name,
                    "url": rss_url,
                    "status": "SUCCESS",
                    "article_count": len(articles),
                    "scrape_success": True,
                    "text_length": len(test_article.full_text),
                    "sample_title": test_article.title,
                })
                working_count += 1
            else:
                print(f"    ⚠️  PARTIAL: RSS works but scraping failed")
                results.append({
                    "source": source_name,
                    "url": rss_url,
                    "status": "PARTIAL",
                    "reason": "Content extraction failed",
                    "article_count": len(articles),
                    "scrape_success": False,
                })
                failing_count += 1

        except Exception as e:
            print(f"    ❌ FAIL: {str(e)[:100]}")
            results.append({
                "source": source_name,
                "url": rss_url,
                "status": "FAIL",
                "reason": str(e)[:100],
                "article_count": 0,
                "scrape_success": False,
            })
            failing_count += 1

        print()

    # Print summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total feeds tested: {len(feeds)}")
    print(f"✅ Working (RSS + Scraping): {working_count} ({working_count/len(feeds)*100:.1f}%)")
    print(f"❌ Failing: {failing_count} ({failing_count/len(feeds)*100:.1f}%)")
    print()

    # Show failing feeds
    failing_feeds = [r for r in results if r["status"] in ["FAIL", "PARTIAL"]]
    if failing_feeds:
        print("=" * 80)
        print(f"FAILING FEEDS ({len(failing_feeds)})")
        print("=" * 80)
        for feed in failing_feeds:
            print(f"\n❌ {feed['source']}")
            print(f"   URL: {feed['url']}")
            print(f"   Status: {feed['status']}")
            print(f"   Reason: {feed.get('reason', 'Content extraction failed')}")

    # Show working feeds
    working_feeds = [r for r in results if r["status"] == "SUCCESS"]
    if working_feeds:
        print("\n" + "=" * 80)
        print(f"WORKING FEEDS ({len(working_feeds)})")
        print("=" * 80)
        for feed in working_feeds:
            print(f"\n✅ {feed['source']}")
            print(f"   URL: {feed['url']}")
            print(f"   Articles in feed: {feed['article_count']}")
            print(f"   Scraped text length: {feed['text_length']} chars")
            print(f"   Sample: {feed['sample_title'][:70]}")

    print("\n" + "=" * 80)
    print("END OF REPORT")
    print("=" * 80)

    return results


if __name__ == "__main__":
    test_all_feeds()
