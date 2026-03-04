"""
News RSS Scraper

A reusable scraper that takes any RSS feed URL, fetches the latest articles,
and extracts full content using newspaper3k.
"""

import logging
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import newspaper
from rss_parser import RSSParser


logger = logging.getLogger(__name__)


@dataclass
class Article:
    """Represents a fully extracted news article."""

    url: str
    title: str
    source: str  # e.g. "NDTV", "BBC", "CNN"
    description: str = ""
    pub_date: str = ""
    guid: str = ""

    # Fields populated after full content extraction
    full_text: str = ""
    authors: list[str] = field(default_factory=list)
    top_image: str = ""
    images: list[str] = field(default_factory=list)
    publish_date: Optional[datetime] = None

    # Metadata
    content_hash: str = ""
    fetched_at: Optional[datetime] = None
    is_content_extracted: bool = False

    def __post_init__(self):
        if not self.content_hash and self.url:
            self.content_hash = hashlib.sha256(self.url.encode()).hexdigest()[:16]

    def extract_content(self, timeout: int = 10) -> bool:
        """
        Download and parse the full article content using newspaper3k.

        Returns True if extraction succeeded, False otherwise.
        """
        try:
            article = newspaper.Article(self.url)
            article.download()
            article.parse()

            self.full_text = article.text
            self.authors = article.authors
            self.top_image = article.top_image or ""
            self.images = list(article.images) if article.images else []
            self.publish_date = article.publish_date
            self.is_content_extracted = True
            self.fetched_at = datetime.now()

            # Update title from article if RSS title was empty
            if not self.title and article.title:
                self.title = article.title

            logger.info(f"Extracted content for: {self.title} ({len(self.full_text)} chars)")
            return True

        except Exception as e:
            logger.error(f"Failed to extract content from {self.url}: {e}")
            self.is_content_extracted = False
            return False

    def to_dict(self) -> dict:
        """Serialize article to a dictionary."""
        return {
            "url": self.url,
            "title": self.title,
            "source": self.source,
            "description": self.description,
            "pub_date": self.pub_date,
            "guid": self.guid,
            "full_text": self.full_text,
            "authors": self.authors,
            "top_image": self.top_image,
            "images": self.images,
            "publish_date": self.publish_date.isoformat() if self.publish_date else None,
            "content_hash": self.content_hash,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            "is_content_extracted": self.is_content_extracted,
        }


class NewsRSSScraper:
    """
    Scrapes news articles from RSS feeds.

    Usage:
        scraper = NewsRSSScraper()

        # Add feeds
        scraper.add_feed("NDTV", "https://feeds.feedburner.com/ndtvnews-top-stories")
        scraper.add_feed("BBC", "https://feeds.bbci.co.uk/news/rss.xml")

        # Fetch latest articles (metadata only, from RSS)
        articles = scraper.fetch_all()

        # Extract full content for all articles
        scraper.extract_all_content(articles)

        # Or do both in one call
        articles = scraper.fetch_and_extract_all()
    """

    def __init__(self, request_timeout: int = 10, dedup_titles: bool = True):
        self._feeds: dict[str, str] = {}  # source_name -> rss_url
        self._seen_urls: set[str] = set()
        self._seen_title_keys: set[str] = set()  # normalized title keys for cross-source dedup
        self._dedup_titles = dedup_titles
        self._request_timeout = request_timeout

    @property
    def feeds(self) -> dict[str, str]:
        """Return registered feeds."""
        return dict(self._feeds)

    @property
    def seen_urls(self) -> set[str]:
        """Return set of already-processed URLs."""
        return set(self._seen_urls)

    def add_feed(self, source_name: str, rss_url: str) -> None:
        """Register an RSS feed source."""
        self._feeds[source_name] = rss_url
        logger.info(f"Added feed: {source_name} -> {rss_url}")

    def remove_feed(self, source_name: str) -> None:
        """Remove a registered RSS feed source."""
        self._feeds.pop(source_name, None)
        logger.info(f"Removed feed: {source_name}")

    def mark_seen(self, urls: set[str] | list[str]) -> None:
        """Mark URLs as already processed (won't be returned by fetch)."""
        self._seen_urls.update(urls)

    def clear_seen(self) -> None:
        """Clear the set of seen URLs."""
        self._seen_urls.clear()
        self._seen_title_keys.clear()

    @staticmethod
    def _normalize_title(title: str) -> str:
        """Normalize title for dedup: lowercase, strip punctuation, collapse whitespace."""
        import re
        t = title.lower().strip()
        t = re.sub(r'[^\w\s]', '', t)      # remove punctuation
        t = re.sub(r'\s+', ' ', t).strip()  # collapse whitespace
        # Drop very short words that vary across sources (a, an, the, etc.)
        words = [w for w in t.split() if len(w) > 2]
        # Use first 8 meaningful words as the key (headlines vary in length)
        return ' '.join(words[:8])

    # ── Fetching (RSS metadata only) ──────────────────────────────────────

    def fetch_feed(self, source_name: str, rss_url: str, *, include_seen: bool = False, max_per_feed: int = 0) -> list[Article]:
        """
        Fetch articles from a single RSS feed.
        Returns Article objects with metadata only (no full text yet).

        Args:
            source_name: Name of the source (e.g. "BBC")
            rss_url: The RSS feed URL
            include_seen: If True, include articles that were already fetched before
            max_per_feed: Max articles to take from this feed (0 = unlimited)
        """
        try:
            response = requests.get(rss_url, timeout=self._request_timeout)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch RSS feed from {source_name} ({rss_url}): {e}")
            return []

        try:
            rss = RSSParser.parse(response.text)
        except Exception as e:
            logger.error(f"Failed to parse RSS feed from {source_name}: {e}")
            return []

        articles = []
        for item in rss.channel.items:
            url = item.links[0].content if item.links else None
            if not url:
                continue

            # Skip already-seen URLs unless explicitly requested
            if not include_seen and url in self._seen_urls:
                continue

            title = item.title.content if item.title else ""

            # Cross-source title dedup: skip if a very similar headline was already fetched
            if self._dedup_titles and title:
                title_key = self._normalize_title(title)
                if title_key and title_key in self._seen_title_keys:
                    logger.debug(f"Title dedup: skipping '{title[:60]}' from {source_name}")
                    continue
                if title_key:
                    self._seen_title_keys.add(title_key)

            description = item.description.content if item.description else ""
            pub_date = item.pub_date.content if hasattr(item, "pub_date") and item.pub_date else ""
            guid = item.guid.content if hasattr(item, "guid") and item.guid else ""

            article = Article(
                url=url,
                title=title,
                source=source_name,
                description=description,
                pub_date=pub_date,
                guid=guid,
            )
            articles.append(article)
            self._seen_urls.add(url)

            if max_per_feed and len(articles) >= max_per_feed:
                break

        logger.info(f"Fetched {len(articles)} articles from {source_name}")
        return articles

    def fetch_all(self, *, include_seen: bool = False, max_per_feed: int = 0) -> list[Article]:
        """
        Fetch articles from all registered RSS feeds.
        Returns Article objects with metadata only (no full text yet).

        Args:
            max_per_feed: Max articles per feed (0 = unlimited)
        """
        all_articles = []
        for source_name, rss_url in self._feeds.items():
            articles = self.fetch_feed(source_name, rss_url, include_seen=include_seen, max_per_feed=max_per_feed)
            all_articles.extend(articles)

        logger.info(f"Fetched {len(all_articles)} total articles from {len(self._feeds)} feeds")
        return all_articles

    # ── Content Extraction (full article text) ────────────────────────────

    def extract_content(self, article: Article) -> Article:
        """Extract full content for a single article. Returns the same article (mutated)."""
        article.extract_content(timeout=self._request_timeout)
        return article

    def extract_all_content(
        self, articles: list[Article], *, max_workers: int = 5
    ) -> list[Article]:
        """
        Extract full content for a list of articles in parallel.

        Args:
            articles: List of Article objects to extract content for
            max_workers: Number of parallel download threads
        """
        succeeded = 0
        failed = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(article.extract_content, self._request_timeout): article
                for article in articles
            }
            for future in as_completed(futures):
                article = futures[future]
                try:
                    result = future.result()
                    if result:
                        succeeded += 1
                    else:
                        failed += 1
                except Exception as e:
                    logger.error(f"Extraction failed for {article.url}: {e}")
                    failed += 1

        logger.info(
            f"Content extraction complete: {succeeded} succeeded, {failed} failed "
            f"out of {len(articles)} articles"
        )
        return articles

    # ── Combined fetch + extract ──────────────────────────────────────────

    def fetch_and_extract_all(
        self,
        *,
        include_seen: bool = False,
        max_workers: int = 5,
    ) -> list[Article]:
        """
        Fetch all RSS feeds and extract full content for every article.

        Args:
            include_seen: If True, re-process previously seen URLs
            max_workers: Number of parallel download threads for content extraction
        """
        articles = self.fetch_all(include_seen=include_seen)
        if articles:
            self.extract_all_content(articles, max_workers=max_workers)
        return articles

    def fetch_and_extract_feed(
        self,
        source_name: str,
        rss_url: str,
        *,
        include_seen: bool = False,
        max_workers: int = 5,
    ) -> list[Article]:
        """
        Fetch a single RSS feed and extract full content for every article.
        The feed does not need to be pre-registered.
        """
        articles = self.fetch_feed(source_name, rss_url, include_seen=include_seen)
        if articles:
            self.extract_all_content(articles, max_workers=max_workers)
        return articles

    # ── Utilities ─────────────────────────────────────────────────────────

    def get_new_articles(self, articles: list[Article]) -> list[Article]:
        """Filter articles to only those with successfully extracted content."""
        return [a for a in articles if a.is_content_extracted and a.full_text]

    def summary(self, articles: list[Article]) -> dict:
        """Return a summary of the fetched articles."""
        by_source: dict[str, int] = {}
        for a in articles:
            by_source[a.source] = by_source.get(a.source, 0) + 1

        return {
            "total": len(articles),
            "with_content": sum(1 for a in articles if a.is_content_extracted),
            "by_source": by_source,
        }


# ── Convenience: pre-configured scraper with common news feeds ────────────

def create_default_scraper() -> NewsRSSScraper:
    """Create a scraper pre-loaded with common news RSS feeds."""
    scraper = NewsRSSScraper()
    # World
    scraper.add_feed("Washington Post", "https://feeds.washingtonpost.com/rss/world")
    scraper.add_feed("BBC", "https://feeds.bbci.co.uk/news/world/rss.xml")
    # India
    scraper.add_feed("NDTV", "https://feeds.feedburner.com/ndtvnews-top-stories")
    # India Today Nation
    scraper.add_feed("India Today", "https://www.indiatoday.in/rss/1206514")
    # India Today Economy
    scraper.add_feed("India Today", "https://www.indiatoday.in/rss/1206513")
    # Inndia Today World
    scraper.add_feed("India Today", "https://www.indiatoday.in/rss/1206577")

    # The Hindu
    scraper.add_feed("The Hindu", "https://www.thehindu.com/news/feeder/default.rss")
    # The Hindu World
    scraper.add_feed("The Hindu", "https://www.thehindu.com/news/international/feeder/default.rss")
    # The Hindu States
    scraper.add_feed("The Hindu", "https://www.thehindu.com/news/states/feeder/default.rss")
    # The Hindu Cities
    scraper.add_feed("The Hindu", "https://www.thehindu.com/news/cities/feeder/default.rss")
    # The Hindu Economy
    scraper.add_feed("The Hindu", "https://www.thehindu.com/business/Economy/feeder/default.rss")
    # The Hindu Markets
    scraper.add_feed("The Hindu", "https://www.thehindu.com/business/markets/feeder/default.rss")
    # The Hindu Budget
    scraper.add_feed("The Hindu", "https://www.thehindu.com/business/budget/feeder/default.rss")

    # Live Mint
    scraper.add_feed("Live Mint", "https://www.livemint.com/rss/news")
    # Live Mint Companies
    scraper.add_feed("Live Mint", "https://www.livemint.com/rss/companies")
    # Live Mint Money
    scraper.add_feed("Live Mint", "https://www.livemint.com/rss/money")
    # Live Mint Politics
    scraper.add_feed("Live Mint", "https://www.livemint.com/rss/politics")
    # Live Mint AI
    scraper.add_feed("Live Mint", "https://www.livemint.com/rss/AI")

    # Economic Times
    scraper.add_feed("Economic Times", "https://b2b.economictimes.indiatimes.com/rss/recentstories")
    # Economic Times Defence
    scraper.add_feed("Economic Times", "https://b2b.economictimes.indiatimes.com/rss/defence")

    return scraper


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    scraper = create_default_scraper()

    # Fetch RSS metadata for all feeds
    print("Fetching RSS feeds...")
    articles = scraper.fetch_all()
    print(f"\nFound {len(articles)} articles across all feeds\n")

    # Show what we got from RSS
    for article in articles[:5]:
        print(f"[{article.source}] {article.title}")
        print(f"  URL: {article.url}")
        print(f"  Published: {article.pub_date}")
        print()

    # Extract full content in parallel
    print("Extracting full article content...")
    scraper.extract_all_content(articles, max_workers=5)

    # Show results
    print(f"\n{'='*60}")
    print(scraper.summary(articles))
    print(f"{'='*60}\n")

    # Show a sample extracted article
    extracted = scraper.get_new_articles(articles)
    if extracted:
        sample = extracted[0]
        print(f"Sample article: {sample.title}")
        print(f"Source: {sample.source}")
        print(f"Authors: {sample.authors}")
        print(f"Text preview: {sample.full_text[:500]}...")