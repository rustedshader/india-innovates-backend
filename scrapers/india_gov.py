"""India Government Data Scrapers.

Covers:
  - PIB (Press Information Bureau)   — RSS + web
  - MEA (Ministry of External Affairs) — press releases
  - Lok Sabha / Rajya Sabha           — parliamentary proceedings RSS
  - DRDO                              — defense R&D press releases
  - data.gov.in                       — Open Government Data (OGD) catalog

Each scraper wraps a CircuitBreaker to prevent silent failures.
Instead of failing silently, sources emit intelligence-gap signals.
"""

import logging
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests
from rss_parser import RSSParser

from scrapers.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

_IST = timezone(timedelta(hours=5, minutes=30))


# ── Base data structure ───────────────────────────────────────────────────────

@dataclass
class GovDocument:
    """A document retrieved from an Indian government source."""
    url: str
    title: str
    source: str          # e.g. "PIB", "MEA", "Lok Sabha"
    source_type: str     # "rss" | "api" | "scrape"
    ministry: str = ""   # e.g. "Ministry of Defence"
    language: str = "en"
    pub_date: str = ""
    description: str = ""
    full_text: str = ""
    metadata: dict = field(default_factory=dict)
    fetched_at: Optional[datetime] = None

    def to_article_dict(self) -> dict:
        """Converts to the same dict format as scrapers.news_rss.Article.to_dict()."""
        return {
            "url": self.url,
            "title": self.title,
            "source": self.source,
            "description": self.description,
            "pub_date": self.pub_date,
            "guid": self.url,
            "full_text": self.full_text or self.description,
            "authors": [self.ministry] if self.ministry else [],
            "top_image": "",
            "images": [],
            "publish_date": self.pub_date,
            "content_hash": "",
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            "is_content_extracted": bool(self.full_text),
        }


# ── Base scraper ──────────────────────────────────────────────────────────────

class BaseGovScraper(ABC):
    """Abstract base for Indian government data scrapers."""

    def __init__(
        self,
        source_name: str,
        circuit_breaker: Optional[CircuitBreaker] = None,
        request_timeout: int = 15,
    ):
        self.source_name = source_name
        self.cb = circuit_breaker
        self.timeout = request_timeout

    def _get(self, url: str, **kwargs) -> Optional[requests.Response]:
        """HTTP GET with circuit breaker guard."""
        if self.cb and not self.cb.can_request():
            logger.warning(
                f"{self.source_name}: circuit OPEN — skipping {url[:80]}"
            )
            return None
        try:
            resp = requests.get(url, timeout=self.timeout, **kwargs)
            resp.raise_for_status()
            if self.cb:
                self.cb.record_success()
            return resp
        except Exception as e:
            logger.error(f"{self.source_name}: request failed {url[:80]}: {e}")
            if self.cb:
                self.cb.record_failure()
            return None

    @abstractmethod
    def fetch(self) -> list[GovDocument]:
        """Fetch and return documents from this source."""
        ...

    def circuit_status(self) -> Optional[dict]:
        return self.cb.status() if self.cb else None


# ── PIB ───────────────────────────────────────────────────────────────────────

class PIBScraper(BaseGovScraper):
    """Press Information Bureau RSS scraper.

    PIB publishes press releases from all Union Ministries.
    RSS feed: https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3
    """

    PIB_FEEDS: list[tuple[str, str]] = [
        ("PIB Top Stories", "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3"),
        ("PIB Defence", "https://pib.gov.in/RssMain.aspx?ModId=7&Lang=1&Regid=3"),
        ("PIB Finance", "https://pib.gov.in/RssMain.aspx?ModId=2&Lang=1&Regid=3"),
        ("PIB External Affairs", "https://pib.gov.in/RssMain.aspx?ModId=3&Lang=1&Regid=3"),
        ("PIB Science Tech", "https://pib.gov.in/RssMain.aspx?ModId=11&Lang=1&Regid=3"),
    ]

    def __init__(self, circuit_breaker: Optional[CircuitBreaker] = None):
        super().__init__("PIB", circuit_breaker)

    def fetch(self) -> list[GovDocument]:
        docs: list[GovDocument] = []
        for feed_name, feed_url in self.PIB_FEEDS:
            resp = self._get(feed_url)
            if not resp:
                continue
            try:
                rss = RSSParser.parse(resp.text)
                for item in rss.channel.items:
                    url = item.links[0].content if item.links else None
                    if not url:
                        continue
                    docs.append(GovDocument(
                        url=url,
                        title=item.title.content if item.title else "",
                        source="PIB",
                        source_type="rss",
                        ministry=feed_name.replace("PIB ", ""),
                        pub_date=item.pub_date.content if hasattr(item, "pub_date") and item.pub_date else "",
                        description=item.description.content if item.description else "",
                        fetched_at=datetime.now(_IST),
                    ))
            except Exception as e:
                logger.error(f"PIB feed parse failed ({feed_url}): {e}")
        logger.info(f"PIB: fetched {len(docs)} documents")
        return docs


# ── MEA ───────────────────────────────────────────────────────────────────────

class MEAScraper(BaseGovScraper):
    """Ministry of External Affairs press releases RSS."""

    MEA_FEEDS: list[tuple[str, str]] = [
        ("MEA Press Releases", "https://mea.gov.in/pressreleaselist.htm?dtl/rss"),
        ("MEA Speeches", "https://mea.gov.in/speecheslist.htm?dtl/rss"),
    ]

    def __init__(self, circuit_breaker: Optional[CircuitBreaker] = None):
        super().__init__("MEA", circuit_breaker)

    def fetch(self) -> list[GovDocument]:
        docs: list[GovDocument] = []
        for feed_name, feed_url in self.MEA_FEEDS:
            resp = self._get(feed_url)
            if not resp:
                continue
            try:
                rss = RSSParser.parse(resp.text)
                for item in rss.channel.items:
                    url = item.links[0].content if item.links else None
                    if not url:
                        continue
                    docs.append(GovDocument(
                        url=url,
                        title=item.title.content if item.title else "",
                        source="MEA",
                        source_type="rss",
                        ministry="Ministry of External Affairs",
                        pub_date=item.pub_date.content if hasattr(item, "pub_date") and item.pub_date else "",
                        description=item.description.content if item.description else "",
                        fetched_at=datetime.now(_IST),
                    ))
            except Exception as e:
                logger.error(f"MEA feed parse failed ({feed_url}): {e}")
        logger.info(f"MEA: fetched {len(docs)} documents")
        return docs


# ── Parliament ────────────────────────────────────────────────────────────────

class ParliamentScraper(BaseGovScraper):
    """Lok Sabha and Rajya Sabha proceedings RSS."""

    PARLIAMENT_FEEDS: list[tuple[str, str]] = [
        ("Lok Sabha Q&A", "https://loksabha.nic.in/rss/questionlist.aspx"),
        ("Rajya Sabha", "https://rajyasabha.nic.in/rss/questionlist.aspx"),
    ]

    def __init__(self, circuit_breaker: Optional[CircuitBreaker] = None):
        super().__init__("Parliament", circuit_breaker)

    def fetch(self) -> list[GovDocument]:
        docs: list[GovDocument] = []
        for feed_name, feed_url in self.PARLIAMENT_FEEDS:
            resp = self._get(feed_url)
            if not resp:
                continue
            try:
                rss = RSSParser.parse(resp.text)
                for item in rss.channel.items:
                    url = item.links[0].content if item.links else None
                    if not url:
                        continue
                    docs.append(GovDocument(
                        url=url,
                        title=item.title.content if item.title else "",
                        source="Parliament",
                        source_type="rss",
                        ministry=feed_name,
                        pub_date=item.pub_date.content if hasattr(item, "pub_date") and item.pub_date else "",
                        description=item.description.content if item.description else "",
                        fetched_at=datetime.now(_IST),
                    ))
            except Exception as e:
                logger.error(f"Parliament RSS parse failed ({feed_url}): {e}")
        logger.info(f"Parliament: fetched {len(docs)} documents")
        return docs


# ── DRDO ──────────────────────────────────────────────────────────────────────

class DRDOScraper(BaseGovScraper):
    """DRDO (Defence Research and Development Organisation) press releases."""

    DRDO_FEEDS: list[tuple[str, str]] = [
        ("DRDO News", "https://www.drdo.gov.in/rss-feeds/latest-news"),
        ("DRDO Technologies", "https://www.drdo.gov.in/rss-feeds/technology-transfer"),
    ]

    def __init__(self, circuit_breaker: Optional[CircuitBreaker] = None):
        super().__init__("DRDO", circuit_breaker)

    def fetch(self) -> list[GovDocument]:
        docs: list[GovDocument] = []
        for feed_name, feed_url in self.DRDO_FEEDS:
            resp = self._get(feed_url)
            if not resp:
                continue
            try:
                rss = RSSParser.parse(resp.text)
                for item in rss.channel.items:
                    url = item.links[0].content if item.links else None
                    if not url:
                        continue
                    docs.append(GovDocument(
                        url=url,
                        title=item.title.content if item.title else "",
                        source="DRDO",
                        source_type="rss",
                        ministry="Ministry of Defence — DRDO",
                        pub_date=item.pub_date.content if hasattr(item, "pub_date") and item.pub_date else "",
                        description=item.description.content if item.description else "",
                        fetched_at=datetime.now(_IST),
                    ))
            except Exception as e:
                logger.error(f"DRDO RSS parse failed ({feed_url}): {e}")
        logger.info(f"DRDO: fetched {len(docs)} documents")
        return docs


# ── Aggregated India Gov Producer ─────────────────────────────────────────────

class IndiaGovProducer:
    """Aggregates all Indian government scrapers into a single call.

    Usage:
        producer = IndiaGovProducer(redis_client=r)
        docs = producer.fetch_all()
        # docs: list[GovDocument], convert with doc.to_article_dict()
    """

    def __init__(self, redis_client=None):
        def _cb(name: str) -> Optional[CircuitBreaker]:
            return CircuitBreaker(name, redis_client) if redis_client else None

        self.scrapers: list[BaseGovScraper] = [
            PIBScraper(circuit_breaker=_cb("PIB")),
            MEAScraper(circuit_breaker=_cb("MEA")),
            ParliamentScraper(circuit_breaker=_cb("Parliament")),
            DRDOScraper(circuit_breaker=_cb("DRDO")),
        ]

    def fetch_all(self) -> list[GovDocument]:
        """Fetch from all government sources, skipping those with open circuits."""
        all_docs: list[GovDocument] = []
        for scraper in self.scrapers:
            try:
                docs = scraper.fetch()
                all_docs.extend(docs)
            except Exception as e:
                logger.error(f"{scraper.source_name}: uncaught error: {e}")
        logger.info(f"IndiaGovProducer: fetched {len(all_docs)} total documents")
        return all_docs

    def circuit_statuses(self) -> list[dict]:
        """Return circuit breaker status for all scrapers (for health/gap reporting)."""
        return [
            s.circuit_status() for s in self.scrapers if s.circuit_status()
        ]
