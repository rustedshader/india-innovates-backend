"""
Tests for RSS feed pagination and 28-day date filtering in NewsRSSScraper.

Covers:
- Single-page feeds within the window → all articles returned
- Single-page feeds with stale articles → old articles excluded
- Paginated feeds → next-page link followed
- Pagination stops when a page's articles are all older than cutoff
- No pub_date items are included regardless (conservative: include unknown dates)
- fetch_all days= parameter propagates the cutoff correctly
- max_per_feed cap respected across pages
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

from scrapers.news_rss import NewsRSSScraper, _parse_pub_date, _extract_next_page_url


# ── Helpers ──────────────────────────────────────────────────────────────────

def _rfc2822(dt: datetime) -> str:
    """Format a datetime as RFC 2822 (standard RSS pub_date format)."""
    from email.utils import format_datetime
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return format_datetime(dt)


def _rss_page(items: list[dict], next_url: str | None = None) -> str:
    """
    Build a minimal RSS 2.0 XML string.

    Each item dict should have: url, title, pub_date (optional).
    If next_url is given, an <atom:link rel="next"> element is included.
    """
    atom_ns = 'xmlns:atom="http://www.w3.org/2005/Atom"'
    next_link = (
        f'<atom:link rel="next" href="{next_url}"/>'
        if next_url
        else ""
    )
    items_xml = ""
    for item in items:
        pub_date_tag = f"<pubDate>{item['pub_date']}</pubDate>" if item.get("pub_date") else ""
        items_xml += f"""
        <item>
            <title>{item.get('title', 'Test Article')}</title>
            <link>{item['url']}</link>
            <guid>{item['url']}</guid>
            {pub_date_tag}
            <description>Test description</description>
        </item>"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" {atom_ns}>
  <channel>
    <title>Test Feed</title>
    <link>https://example.com</link>
    <description>Test</description>
    {next_link}
    {items_xml}
  </channel>
</rss>"""


def _mock_response(text: str, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


# ── _parse_pub_date ───────────────────────────────────────────────────────────

class TestParsePubDate:
    def test_rfc2822_with_timezone(self):
        dt = _parse_pub_date("Thu, 27 Mar 2026 10:00:00 +0000")
        assert dt is not None
        assert dt.year == 2026
        assert dt.tzinfo is not None

    def test_rfc2822_without_timezone_gets_utc(self):
        dt = _parse_pub_date("Thu, 27 Mar 2026 10:00:00")
        assert dt is not None
        assert dt.tzinfo == timezone.utc

    def test_iso8601_format(self):
        dt = _parse_pub_date("2026-03-27T10:00:00Z")
        assert dt is not None
        assert dt.year == 2026

    def test_empty_string_returns_none(self):
        assert _parse_pub_date("") is None

    def test_garbage_returns_none(self):
        assert _parse_pub_date("not a date at all !!") is None


# ── _extract_next_page_url ────────────────────────────────────────────────────

class TestExtractNextPageUrl:
    def test_atom_link_rel_next(self):
        xml = '<atom:link rel="next" href="https://example.com/feed?page=2"/>'
        assert _extract_next_page_url(xml) == "https://example.com/feed?page=2"

    def test_atom_link_href_first(self):
        xml = '<atom:link href="https://example.com/feed?page=2" rel="next"/>'
        assert _extract_next_page_url(xml) == "https://example.com/feed?page=2"

    def test_link_rel_next(self):
        xml = '<link rel="next" href="https://example.com/feed?page=2"/>'
        assert _extract_next_page_url(xml) == "https://example.com/feed?page=2"

    def test_no_next_link_returns_none(self):
        xml = '<link rel="self" href="https://example.com/feed"/>'
        assert _extract_next_page_url(xml) is None

    def test_no_pagination_in_feed(self):
        assert _extract_next_page_url("<rss><channel><item/></channel></rss>") is None


# ── Single-page fetch ─────────────────────────────────────────────────────────

class TestFetchFeedSinglePage:
    def _scraper(self) -> NewsRSSScraper:
        return NewsRSSScraper(dedup_titles=False)

    def test_fresh_articles_returned(self):
        now = datetime.now(timezone.utc)
        items = [
            {"url": "https://example.com/1", "title": "Article 1", "pub_date": _rfc2822(now - timedelta(days=1))},
            {"url": "https://example.com/2", "title": "Article 2", "pub_date": _rfc2822(now - timedelta(days=5))},
        ]
        feed_xml = _rss_page(items)
        cutoff = now - timedelta(days=28)

        with patch("scrapers.news_rss.requests.get", return_value=_mock_response(feed_xml)):
            scraper = self._scraper()
            articles = scraper.fetch_feed("Test", "https://example.com/rss", cutoff_date=cutoff)

        assert len(articles) == 2
        assert articles[0].url == "https://example.com/1"
        assert articles[1].url == "https://example.com/2"

    def test_stale_articles_excluded(self):
        now = datetime.now(timezone.utc)
        items = [
            {"url": "https://example.com/1", "pub_date": _rfc2822(now - timedelta(days=5))},   # fresh
            {"url": "https://example.com/2", "pub_date": _rfc2822(now - timedelta(days=30))},  # stale
            {"url": "https://example.com/3", "pub_date": _rfc2822(now - timedelta(days=60))},  # stale
        ]
        feed_xml = _rss_page(items)
        cutoff = now - timedelta(days=28)

        with patch("scrapers.news_rss.requests.get", return_value=_mock_response(feed_xml)):
            scraper = self._scraper()
            articles = scraper.fetch_feed("Test", "https://example.com/rss", cutoff_date=cutoff)

        assert len(articles) == 1
        assert articles[0].url == "https://example.com/1"

    def test_no_cutoff_returns_all(self):
        now = datetime.now(timezone.utc)
        items = [
            {"url": "https://example.com/1", "pub_date": _rfc2822(now - timedelta(days=5))},
            {"url": "https://example.com/2", "pub_date": _rfc2822(now - timedelta(days=60))},
            {"url": "https://example.com/3", "pub_date": _rfc2822(now - timedelta(days=365))},
        ]
        feed_xml = _rss_page(items)

        with patch("scrapers.news_rss.requests.get", return_value=_mock_response(feed_xml)):
            scraper = self._scraper()
            articles = scraper.fetch_feed("Test", "https://example.com/rss", cutoff_date=None)

        assert len(articles) == 3

    def test_items_without_pub_date_are_included(self):
        """Articles with no pub_date cannot be age-checked, so they should be included."""
        items = [
            {"url": "https://example.com/1", "title": "No date article"},
        ]
        feed_xml = _rss_page(items)
        cutoff = datetime.now(timezone.utc) - timedelta(days=28)

        with patch("scrapers.news_rss.requests.get", return_value=_mock_response(feed_xml)):
            scraper = self._scraper()
            articles = scraper.fetch_feed("Test", "https://example.com/rss", cutoff_date=cutoff)

        assert len(articles) == 1

    def test_max_per_feed_respected(self):
        now = datetime.now(timezone.utc)
        items = [{"url": f"https://example.com/{i}", "pub_date": _rfc2822(now - timedelta(hours=i))} for i in range(10)]
        feed_xml = _rss_page(items)

        with patch("scrapers.news_rss.requests.get", return_value=_mock_response(feed_xml)):
            scraper = self._scraper()
            articles = scraper.fetch_feed("Test", "https://example.com/rss", max_per_feed=3)

        assert len(articles) == 3


# ── Paginated fetch ───────────────────────────────────────────────────────────

class TestFetchFeedPagination:
    def _scraper(self) -> NewsRSSScraper:
        return NewsRSSScraper(dedup_titles=False)

    def test_follows_next_page_link(self):
        """Scraper should follow the <atom:link rel='next'> and fetch page 2."""
        now = datetime.now(timezone.utc)
        page1_items = [
            {"url": "https://example.com/1", "pub_date": _rfc2822(now - timedelta(days=1))},
            {"url": "https://example.com/2", "pub_date": _rfc2822(now - timedelta(days=2))},
        ]
        page2_items = [
            {"url": "https://example.com/3", "pub_date": _rfc2822(now - timedelta(days=3))},
            {"url": "https://example.com/4", "pub_date": _rfc2822(now - timedelta(days=4))},
        ]
        page1_xml = _rss_page(page1_items, next_url="https://example.com/rss?page=2")
        page2_xml = _rss_page(page2_items)  # no next link → last page

        responses = {
            "https://example.com/rss": _mock_response(page1_xml),
            "https://example.com/rss?page=2": _mock_response(page2_xml),
        }

        with patch("scrapers.news_rss.requests.get", side_effect=lambda url, **kw: responses[url]):
            scraper = self._scraper()
            cutoff = now - timedelta(days=28)
            articles = scraper.fetch_feed("Test", "https://example.com/rss", cutoff_date=cutoff)

        assert len(articles) == 4
        urls = [a.url for a in articles]
        assert "https://example.com/1" in urls
        assert "https://example.com/3" in urls

    def test_pagination_stops_when_cutoff_reached(self):
        """
        Page 1 has fresh articles, page 2 starts with an old article.
        The scraper should stop before fetching a (hypothetical) page 3.
        """
        now = datetime.now(timezone.utc)
        page1_items = [
            {"url": "https://example.com/1", "pub_date": _rfc2822(now - timedelta(days=5))},
            {"url": "https://example.com/2", "pub_date": _rfc2822(now - timedelta(days=10))},
        ]
        page2_items = [
            # This article is beyond the 28-day window
            {"url": "https://example.com/3", "pub_date": _rfc2822(now - timedelta(days=35))},
        ]
        page1_xml = _rss_page(page1_items, next_url="https://example.com/rss?page=2")
        page2_xml = _rss_page(page2_items, next_url="https://example.com/rss?page=3")

        get_call_count = {"n": 0}

        def fake_get(url, **kw):
            get_call_count["n"] += 1
            if url == "https://example.com/rss":
                return _mock_response(page1_xml)
            if url == "https://example.com/rss?page=2":
                return _mock_response(page2_xml)
            raise AssertionError(f"Unexpected URL requested: {url}")

        with patch("scrapers.news_rss.requests.get", side_effect=fake_get):
            scraper = self._scraper()
            cutoff = now - timedelta(days=28)
            articles = scraper.fetch_feed("Test", "https://example.com/rss", cutoff_date=cutoff)

        # Only page1 articles should be returned; page2 article is stale
        assert len(articles) == 2
        # Page 3 must never have been requested
        assert get_call_count["n"] == 2

    def test_three_pages_all_within_window(self):
        """All three pages are within 28 days → all articles collected."""
        now = datetime.now(timezone.utc)

        def make_page(start_day, end_day, next_url=None):
            items = [
                {"url": f"https://example.com/{d}", "pub_date": _rfc2822(now - timedelta(days=d))}
                for d in range(start_day, end_day)
            ]
            return _rss_page(items, next_url=next_url)

        page1_xml = make_page(1, 5, next_url="https://example.com/rss?page=2")
        page2_xml = make_page(5, 10, next_url="https://example.com/rss?page=3")
        page3_xml = make_page(10, 15)

        responses = {
            "https://example.com/rss": _mock_response(page1_xml),
            "https://example.com/rss?page=2": _mock_response(page2_xml),
            "https://example.com/rss?page=3": _mock_response(page3_xml),
        }

        with patch("scrapers.news_rss.requests.get", side_effect=lambda url, **kw: responses[url]):
            scraper = self._scraper()
            cutoff = now - timedelta(days=28)
            articles = scraper.fetch_feed("Test", "https://example.com/rss", cutoff_date=cutoff)

        assert len(articles) == 14  # days 1..14

    def test_max_per_feed_stops_pagination(self):
        """max_per_feed should cap results and stop further page fetches."""
        now = datetime.now(timezone.utc)
        page1_items = [
            {"url": f"https://example.com/{i}", "pub_date": _rfc2822(now - timedelta(days=i))}
            for i in range(1, 4)
        ]
        page2_items = [
            {"url": f"https://example.com/{i}", "pub_date": _rfc2822(now - timedelta(days=i))}
            for i in range(4, 7)
        ]
        page1_xml = _rss_page(page1_items, next_url="https://example.com/rss?page=2")
        page2_xml = _rss_page(page2_items)

        get_call_count = {"n": 0}

        def fake_get(url, **kw):
            get_call_count["n"] += 1
            if url == "https://example.com/rss":
                return _mock_response(page1_xml)
            return _mock_response(page2_xml)

        with patch("scrapers.news_rss.requests.get", side_effect=fake_get):
            scraper = self._scraper()
            articles = scraper.fetch_feed("Test", "https://example.com/rss", max_per_feed=2)

        assert len(articles) == 2
        assert get_call_count["n"] == 1  # page 2 never fetched


# ── fetch_all days parameter ──────────────────────────────────────────────────

class TestFetchAllDaysParameter:
    def test_default_28_days_filters_old_articles(self):
        now = datetime.now(timezone.utc)
        items = [
            {"url": "https://example.com/fresh", "pub_date": _rfc2822(now - timedelta(days=5))},
            {"url": "https://example.com/stale", "pub_date": _rfc2822(now - timedelta(days=40))},
        ]
        feed_xml = _rss_page(items)

        with patch("scrapers.news_rss.requests.get", return_value=_mock_response(feed_xml)):
            scraper = NewsRSSScraper(dedup_titles=False)
            scraper.add_feed("Test", "https://example.com/rss")
            articles = scraper.fetch_all()  # default days=28

        assert len(articles) == 1
        assert articles[0].url == "https://example.com/fresh"

    def test_days_zero_disables_filtering(self):
        now = datetime.now(timezone.utc)
        items = [
            {"url": "https://example.com/fresh", "pub_date": _rfc2822(now - timedelta(days=5))},
            {"url": "https://example.com/old", "pub_date": _rfc2822(now - timedelta(days=400))},
        ]
        feed_xml = _rss_page(items)

        with patch("scrapers.news_rss.requests.get", return_value=_mock_response(feed_xml)):
            scraper = NewsRSSScraper(dedup_titles=False)
            scraper.add_feed("Test", "https://example.com/rss")
            articles = scraper.fetch_all(days=0)

        assert len(articles) == 2

    def test_custom_days_parameter(self):
        now = datetime.now(timezone.utc)
        items = [
            {"url": "https://example.com/1", "pub_date": _rfc2822(now - timedelta(days=3))},   # within 7
            {"url": "https://example.com/2", "pub_date": _rfc2822(now - timedelta(days=10))},  # outside 7
        ]
        feed_xml = _rss_page(items)

        with patch("scrapers.news_rss.requests.get", return_value=_mock_response(feed_xml)):
            scraper = NewsRSSScraper(dedup_titles=False)
            scraper.add_feed("Test", "https://example.com/rss")
            articles = scraper.fetch_all(days=7)

        assert len(articles) == 1
        assert articles[0].url == "https://example.com/1"

    def test_multiple_feeds_each_paginated(self):
        """fetch_all should paginate independently per feed."""
        now = datetime.now(timezone.utc)

        feed_a_page1 = _rss_page(
            [{"url": "https://a.com/1", "pub_date": _rfc2822(now - timedelta(days=1))}],
            next_url="https://a.com/rss?page=2",
        )
        feed_a_page2 = _rss_page(
            [{"url": "https://a.com/2", "pub_date": _rfc2822(now - timedelta(days=2))}],
        )
        feed_b_xml = _rss_page(
            [{"url": "https://b.com/1", "pub_date": _rfc2822(now - timedelta(days=3))}],
        )

        responses = {
            "https://a.com/rss": _mock_response(feed_a_page1),
            "https://a.com/rss?page=2": _mock_response(feed_a_page2),
            "https://b.com/rss": _mock_response(feed_b_xml),
        }

        with patch("scrapers.news_rss.requests.get", side_effect=lambda url, **kw: responses[url]):
            scraper = NewsRSSScraper(dedup_titles=False)
            scraper.add_feed("FeedA", "https://a.com/rss")
            scraper.add_feed("FeedB", "https://b.com/rss")
            articles = scraper.fetch_all(days=28)

        assert len(articles) == 3
        urls = {a.url for a in articles}
        assert urls == {"https://a.com/1", "https://a.com/2", "https://b.com/1"}
