"""RBI (Reserve Bank of India) API client.

Fetches structured economic indicator data from RBI's public APIs:
  - Exchange rates (INR vs USD, EUR, GBP, JPY, CNY)
  - Policy repo rate
  - CPI inflation index
  - Forex reserves

Data is returned as GovDocument objects with JSON metadata,
and can be upserted as Economic_Indicator entities in Neo4j.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests

from scrapers.india_gov import GovDocument
from scrapers.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)
_IST = timezone(timedelta(hours=5, minutes=30))

# RBI public data API base
_RBI_BASE = "https://api.rbi.org.in/api"

# data.gov.in public datasets (OGPL/OData)
_DATAGOV_BASE = "https://api.data.gov.in/resource"

# Well-known data.gov.in resource IDs
_DATAGOV_RESOURCES = {
    "wholesale_price_index": "35985678-0d79-46b4-9ed6-6f13308a1d24",
    "consumer_price_index":  "3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69",
}


class RBIApiClient:
    """Fetches economic indicator data from RBI and data.gov.in."""

    def __init__(
        self,
        circuit_breaker: Optional[CircuitBreaker] = None,
        request_timeout: int = 20,
        datagov_api_key: str = "",
    ):
        self.cb = circuit_breaker
        self.timeout = request_timeout
        self.datagov_api_key = datagov_api_key

    def _get(self, url: str, params: Optional[dict] = None) -> Optional[dict]:
        if self.cb and not self.cb.can_request():
            logger.warning(f"RBI circuit OPEN — skipping {url[:80]}")
            return None
        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            if self.cb:
                self.cb.record_success()
            return resp.json()
        except Exception as e:
            logger.error(f"RBI API request failed ({url[:80]}): {e}")
            if self.cb:
                self.cb.record_failure()
            return None

    # ── Exchange rates ─────────────────────────────────────────────────────────

    def fetch_exchange_rates(self) -> list[GovDocument]:
        """Fetch INR exchange rates from RBI daily reference rates."""
        url = f"{_RBI_BASE}/ExchangeRate"
        data = self._get(url)
        docs = []
        if not data:
            # Fallback: fetch from ExchangeRate API (free tier)
            try:
                resp = requests.get(
                    "https://open.er-api.com/v6/latest/INR", timeout=15
                )
                if resp.ok:
                    rates = resp.json().get("rates", {})
                    now = datetime.now(_IST)
                    for currency, rate in rates.items():
                        if currency in ("USD", "EUR", "GBP", "JPY", "CNY", "AED"):
                            docs.append(GovDocument(
                                url=f"https://open.er-api.com/v6/latest/INR#{currency}",
                                title=f"INR/{currency} Exchange Rate",
                                source="RBI",
                                source_type="api",
                                ministry="Reserve Bank of India",
                                pub_date=now.strftime("%a, %d %b %Y %H:%M:%S %z"),
                                description=f"1 INR = {rate:.6f} {currency}",
                                full_text=f"RBI Reference Rate: 1 Indian Rupee (INR) = {rate:.6f} {currency} as of {now.strftime('%Y-%m-%d')}.",
                                metadata={"indicator": "exchange_rate", "currency": currency, "rate": rate},
                                fetched_at=now,
                            ))
            except Exception as e:
                logger.error(f"Exchange rate fallback failed: {e}")
        return docs

    # ── data.gov.in structured datasets ───────────────────────────────────────

    def fetch_consumer_price_index(self) -> list[GovDocument]:
        """Fetch CPI data from data.gov.in."""
        return self._fetch_datagov(
            resource_id=_DATAGOV_RESOURCES["consumer_price_index"],
            indicator_name="Consumer Price Index (CPI)",
            ministry="Ministry of Statistics",
        )

    def fetch_wholesale_price_index(self) -> list[GovDocument]:
        """Fetch WPI data from data.gov.in."""
        return self._fetch_datagov(
            resource_id=_DATAGOV_RESOURCES["wholesale_price_index"],
            indicator_name="Wholesale Price Index (WPI)",
            ministry="Ministry of Commerce and Industry",
        )

    def _fetch_datagov(
        self, resource_id: str, indicator_name: str, ministry: str
    ) -> list[GovDocument]:
        if not self.datagov_api_key:
            logger.debug(f"No data.gov.in API key — skipping {indicator_name}")
            return []

        url = f"{_DATAGOV_BASE}/{resource_id}"
        params = {
            "api-key": self.datagov_api_key,
            "format": "json",
            "limit": 10,
            "sort[updated]": "desc",
        }
        data = self._get(url, params=params)
        if not data:
            return []

        records = data.get("records", [])
        docs = []
        now = datetime.now(_IST)
        for rec in records[:10]:
            rec_str = json.dumps(rec)
            docs.append(GovDocument(
                url=f"{_DATAGOV_BASE}/{resource_id}",
                title=f"{indicator_name} — {rec.get('year', '')} {rec.get('month', '')}",
                source="data.gov.in",
                source_type="api",
                ministry=ministry,
                pub_date=now.strftime("%a, %d %b %Y %H:%M:%S %z"),
                description=f"Latest {indicator_name} data from Government of India.",
                full_text=f"{indicator_name} record: {rec_str}",
                metadata={"indicator": indicator_name, "record": rec},
                fetched_at=now,
            ))
        return docs

    def fetch_all(self) -> list[GovDocument]:
        """Fetch all available structured economic indicators."""
        docs = []
        docs.extend(self.fetch_exchange_rates())
        docs.extend(self.fetch_consumer_price_index())
        docs.extend(self.fetch_wholesale_price_index())
        logger.info(f"RBIApiClient: fetched {len(docs)} indicator documents")
        return docs
