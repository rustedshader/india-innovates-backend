"""
Attempt to fix failing RSS feeds with various strategies:
1. Add user-agent headers for 403 errors
2. Research and try alternative URLs for 404 errors
3. Increase timeout for connection issues
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(message)s")

# Custom headers to bypass bot detection
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'application/rss+xml, application/xml, text/xml, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1'
}

def test_url_with_headers(url, name):
    """Test if adding headers fixes 403 errors"""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"URL: {url}")

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        print(f"Status Code: {response.status_code}")

        if response.status_code == 200:
            # Check if it's valid XML/RSS
            content_type = response.headers.get('Content-Type', '')
            print(f"Content-Type: {content_type}")

            # Try to parse as XML
            try:
                from xml.etree import ElementTree as ET
                ET.fromstring(response.content)
                print("✅ SUCCESS - Valid XML/RSS feed")
                return True, url
            except Exception as e:
                print(f"⚠️  Got 200 but XML parsing failed: {str(e)[:100]}")
                return False, url
        else:
            print(f"❌ Still failing with status {response.status_code}")
            return False, url

    except Exception as e:
        print(f"❌ Error: {str(e)[:100]}")
        return False, url

def find_alternative_rss_urls(base_url, source_name):
    """Try to find RSS feed URLs from the website"""
    print(f"\n{'='*60}")
    print(f"Searching for RSS feeds on: {source_name}")
    print(f"Base URL: {base_url}")

    try:
        response = requests.get(base_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Look for RSS feed links
        rss_links = []

        # Method 1: Look for <link> tags with RSS
        for link in soup.find_all('link', type=['application/rss+xml', 'application/atom+xml']):
            href = link.get('href')
            if href:
                if not href.startswith('http'):
                    from urllib.parse import urljoin
                    href = urljoin(base_url, href)
                rss_links.append(href)
                print(f"  Found: {href}")

        # Method 2: Look for /feed, /rss, .xml links in the page
        for a in soup.find_all('a', href=True):
            href = a['href']
            if any(x in href.lower() for x in ['/feed', '/rss', '.xml', '.rss']):
                if not href.startswith('http'):
                    from urllib.parse import urljoin
                    href = urljoin(base_url, href)
                if href not in rss_links:
                    rss_links.append(href)
                    print(f"  Found: {href}")

        return rss_links

    except Exception as e:
        print(f"  Error searching: {str(e)[:100]}")
        return []

def main():
    print("="*80)
    print("ATTEMPTING TO FIX FAILING RSS FEEDS")
    print("="*80)

    results = {
        'fixed': [],
        'still_failing': []
    }

    # ============================================================
    # 1. Test 403 Forbidden feeds with headers
    # ============================================================
    print("\n" + "="*80)
    print("STRATEGY 1: Add Headers for 403 Forbidden Errors")
    print("="*80)

    forbidden_feeds = [
        ("The Print Defence", "https://theprint.in/category/defence/feed/"),
        ("The Print Security", "https://theprint.in/category/security/feed/"),
        ("The Print Diplomacy", "https://theprint.in/category/diplomacy/feed/"),
        ("The Print Economy", "https://theprint.in/category/economy/feed/"),
        ("The Wire", "https://thewire.in/feed"),
        ("The Wire Geopolitics", "https://thewire.in/category/diplomacy/feed"),
        ("Business Standard", "https://www.business-standard.com/rss/home_page_top_stories.rss"),
        ("BS Defence", "https://www.business-standard.com/rss/defence.rss"),
    ]

    for name, url in forbidden_feeds:
        success, final_url = test_url_with_headers(url, name)
        if success:
            results['fixed'].append((name, final_url))
        else:
            results['still_failing'].append((name, url, "403/Headers didn't work"))

    # ============================================================
    # 2. Find alternative URLs for 404 errors
    # ============================================================
    print("\n" + "="*80)
    print("STRATEGY 2: Find Alternative URLs for 404 Errors")
    print("="*80)

    # WION - try different patterns
    print("\nWION feeds:")
    wion_attempts = [
        ("WION World", "https://www.wionews.com/feed"),
        ("WION World Alt", "https://www.wionews.com/rss"),
        ("WION All", "https://www.wionews.com/feeds/all.xml"),
    ]
    for name, url in wion_attempts:
        success, final_url = test_url_with_headers(url, name)
        if success:
            results['fixed'].append((name, final_url))
            break
    else:
        # Try to find RSS on the site
        rss_links = find_alternative_rss_urls("https://www.wionews.com", "WION")
        if rss_links:
            for link in rss_links[:2]:  # Test first 2
                success, final_url = test_url_with_headers(link, f"WION (discovered)")
                if success:
                    results['fixed'].append((f"WION", final_url))
                    break

        if not any("WION" in x[0] for x in results['fixed']):
            results['still_failing'].append(("WION", "https://www.wionews.com/rss/world.xml", "404/No working alternative"))

    # ORF Online
    print("\nORF Online:")
    orf_attempts = [
        ("ORF Online", "https://www.orfonline.org/feed/"),
        ("ORF RSS", "https://www.orfonline.org/rss/"),
        ("ORF Research", "https://www.orfonline.org/research/feed/"),
    ]
    for name, url in orf_attempts:
        success, final_url = test_url_with_headers(url, name)
        if success:
            results['fixed'].append((name, final_url))
            break
    else:
        results['still_failing'].append(("ORF Online", "https://www.orfonline.org/feed/", "404/No working alternative"))

    # Foreign Affairs
    print("\nForeign Affairs:")
    fa_attempts = [
        ("Foreign Affairs", "https://www.foreignaffairs.com/rss.xml"),
        ("Foreign Affairs Alt", "https://www.foreignaffairs.com/feeds/all"),
    ]
    for name, url in fa_attempts:
        success, final_url = test_url_with_headers(url, name)
        if success:
            results['fixed'].append((name, final_url))
            break
    else:
        results['still_failing'].append(("Foreign Affairs", "https://www.foreignaffairs.com/rss/latest.xml", "404/No working alternative"))

    # Down To Earth
    print("\nDown To Earth:")
    dte_attempts = [
        ("Down To Earth", "https://www.downtoearth.org.in/rss"),
        ("Down To Earth News", "https://www.downtoearth.org.in/news.rss"),
        ("Down To Earth Latest", "https://www.downtoearth.org.in/latest.rss"),
    ]
    for name, url in dte_attempts:
        success, final_url = test_url_with_headers(url, name)
        if success:
            results['fixed'].append((name, final_url))
            break
    else:
        results['still_failing'].append(("Down To Earth", "https://www.downtoearth.org.in/rss/latest.xml", "404/No working alternative"))

    # Washington Post - try with longer timeout
    print("\nWashington Post (timeout issue):")
    success, final_url = test_url_with_headers("https://feeds.washingtonpost.com/rss/world", "Washington Post")
    if success:
        results['fixed'].append(("Washington Post", final_url))
    else:
        results['still_failing'].append(("Washington Post", "https://feeds.washingtonpost.com/rss/world", "Timeout"))

    # ============================================================
    # 3. PIB feeds - try alternative URLs
    # ============================================================
    print("\n" + "="*80)
    print("STRATEGY 3: PIB Government Feeds - Try Alternatives")
    print("="*80)

    # PIB seems to have RSS issues, try pib.gov.in main feed
    pib_attempts = [
        ("PIB Main", "https://pib.gov.in/allRss.aspx"),
        ("PIB Press Release", "https://www.pib.gov.in/PressReleasePage.aspx?PRID="),
    ]

    for name, url in pib_attempts:
        success, final_url = test_url_with_headers(url, name)
        if success:
            results['fixed'].append((name, final_url))
            break
    else:
        results['still_failing'].append(("PIB All Feeds", "https://pib.gov.in/RssMain.aspx", "XML Parse/Connection errors"))

    # ============================================================
    # Summary
    # ============================================================
    print("\n" + "="*80)
    print("RESULTS SUMMARY")
    print("="*80)

    print(f"\n✅ FIXED: {len(results['fixed'])} feeds")
    for name, url in results['fixed']:
        print(f"  • {name}")
        print(f"    {url}")

    print(f"\n❌ STILL FAILING: {len(results['still_failing'])} feeds")
    for name, url, reason in results['still_failing']:
        print(f"  • {name}: {reason}")

    # Generate updated feed list
    print("\n" + "="*80)
    print("RECOMMENDATION")
    print("="*80)

    if results['fixed']:
        print("\nAdd these working feeds to the scraper:")
        for name, url in results['fixed']:
            print(f'scraper.add_feed("{name}", "{url}")')

    if results['still_failing']:
        print(f"\nRemove these {len(results['still_failing'])} permanently failing feeds")

    return results

if __name__ == "__main__":
    main()
