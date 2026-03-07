"""Weather data ingestion scheduler.

Periodically fetches weather data from Open-Meteo, computes anomaly scores,
detects weather events, and stores results in Postgres + publishes alerts.

Run as a standalone process:
    python -m scheduler.weather_producer

One-time bootstrap:
    python -m scheduler.weather_producer --bootstrap-normals
    python -m scheduler.weather_producer --backfill --years 5
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import time
from datetime import datetime, timedelta, date

import pandas as pd
import redis

from config import (
    REDIS_HOST,
    REDIS_PORT,
    WEATHER_SCRAPE_INTERVAL_SECONDS,
    WEATHER_HISTORICAL_BACKFILL_YEARS,
)
from models.database import SessionLocal
from models.weather_observation import WeatherObservation
from models.weather_anomaly import WeatherAnomalyRecord
from models.climate_normal import ClimateNormal
from scrapers.weather import WeatherScraper, INDIA_CITIES, VARIABLE_TO_COLUMN
from agents.weather_anomaly import WeatherAnomalyDetector, DetectedAnomaly

logger = logging.getLogger(__name__)

_shutdown = False

WEATHER_ALERT_CHANNEL = "india-innovates:weather-alerts"
LIVE_FEED_CHANNEL = "india-innovates:live-feed"


def _handle_signal(signum, frame):
    global _shutdown
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    _shutdown = True


# ──────────────────────────────────────────────────────────────────────
# Database helpers
# ──────────────────────────────────────────────────────────────────────


def _load_normals(city: str) -> pd.DataFrame | None:
    """Load climate normals for a city from Postgres into a DataFrame."""
    db = SessionLocal()
    try:
        rows = (
            db.query(ClimateNormal)
            .filter(ClimateNormal.city == city)
            .all()
        )
        if not rows:
            return None
        records = [
            {
                "month": r.month,
                "variable": r.variable,
                "mean": r.mean,
                "std": r.std,
                "p5": r.p5,
                "p25": r.p25,
                "p75": r.p75,
                "p95": r.p95,
            }
            for r in rows
        ]
        return pd.DataFrame(records)
    finally:
        db.close()


def _upsert_observations(city: str, df: pd.DataFrame) -> int:
    """Upsert scored weather observations into Postgres. Returns count upserted."""
    db = SessionLocal()
    count = 0
    try:
        for idx, row in df.iterrows():
            obs_date = idx.date() if hasattr(idx, "date") else idx

            existing = (
                db.query(WeatherObservation)
                .filter(
                    WeatherObservation.city == city,
                    WeatherObservation.date == obs_date,
                )
                .first()
            )

            values = {
                "city": city,
                "date": obs_date,
                "temperature_max": _safe_float(row.get("temperature_max")),
                "temperature_min": _safe_float(row.get("temperature_min")),
                "temperature_mean": _safe_float(row.get("temperature_mean")),
                "apparent_temperature_max": _safe_float(row.get("apparent_temperature_max")),
                "apparent_temperature_min": _safe_float(row.get("apparent_temperature_min")),
                "precipitation_sum": _safe_float(row.get("precipitation_sum")),
                "rain_sum": _safe_float(row.get("rain_sum")),
                "snowfall_sum": _safe_float(row.get("snowfall_sum")),
                "precipitation_hours": _safe_float(row.get("precipitation_hours")),
                "wind_speed_max": _safe_float(row.get("wind_speed_max")),
                "wind_gusts_max": _safe_float(row.get("wind_gusts_max")),
                "humidity_mean": _safe_float(row.get("humidity_mean")),
                "soil_moisture_mean": _safe_float(row.get("soil_moisture_mean")),
                "et0_evapotranspiration": _safe_float(row.get("et0_evapotranspiration")),
                "shortwave_radiation_sum": _safe_float(row.get("shortwave_radiation_sum")),
                "weather_code": _safe_int(row.get("weather_code")),
                "temp_max_zscore": _safe_float(row.get("temp_max_zscore")),
                "temp_min_zscore": _safe_float(row.get("temp_min_zscore")),
                "precip_zscore": _safe_float(row.get("precip_zscore")),
                "soil_moisture_zscore": _safe_float(row.get("soil_moisture_zscore")),
            }

            if existing:
                for k, v in values.items():
                    if k not in ("city", "date"):
                        setattr(existing, k, v)
            else:
                db.add(WeatherObservation(**values))
            count += 1

        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to upsert observations for {city}: {e}")
    finally:
        db.close()
    return count


def _save_anomalies(anomalies: list[DetectedAnomaly]) -> list[WeatherAnomalyRecord]:
    """Save new anomalies to Postgres (skip duplicates by city+type+start_date)."""
    if not anomalies:
        return []

    db = SessionLocal()
    saved = []
    try:
        for a in anomalies:
            existing = (
                db.query(WeatherAnomalyRecord)
                .filter(
                    WeatherAnomalyRecord.city == a.city,
                    WeatherAnomalyRecord.anomaly_type == a.anomaly_type,
                    WeatherAnomalyRecord.start_date == a.start_date,
                )
                .first()
            )
            if existing:
                continue

            record = WeatherAnomalyRecord(
                city=a.city,
                anomaly_type=a.anomaly_type,
                severity=a.severity,
                start_date=a.start_date,
                end_date=a.end_date,
                peak_value=a.peak_value,
                z_score=a.z_score,
                description=a.description,
            )
            db.add(record)
            saved.append(record)

        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save anomalies: {e}")
    finally:
        db.close()
    return saved


def _save_normals(city: str, normals_df: pd.DataFrame) -> int:
    """Save or replace climate normals for a city."""
    db = SessionLocal()
    count = 0
    try:
        # Delete existing normals for this city
        db.query(ClimateNormal).filter(ClimateNormal.city == city).delete()

        for _, row in normals_df.iterrows():
            db.add(ClimateNormal(
                city=city,
                month=int(row["month"]),
                variable=str(row["variable"]),
                mean=float(row["mean"]),
                std=float(row["std"]),
                p5=_safe_float(row.get("p5")),
                p25=_safe_float(row.get("p25")),
                p75=_safe_float(row.get("p75")),
                p95=_safe_float(row.get("p95")),
            ))
            count += 1

        db.commit()
        logger.info(f"Saved {count} climate normal rows for {city}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save normals for {city}: {e}")
    finally:
        db.close()
    return count


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        import math
        f = float(val)
        return None if math.isnan(f) else f
    except (ValueError, TypeError):
        return None


def _safe_int(val) -> int | None:
    if val is None:
        return None
    try:
        import math
        f = float(val)
        return None if math.isnan(f) else int(f)
    except (ValueError, TypeError):
        return None


# ──────────────────────────────────────────────────────────────────────
# Main ingestion cycle
# ──────────────────────────────────────────────────────────────────────


def run_cycle():
    """Single weather ingestion + anomaly detection cycle for all cities."""
    scraper = WeatherScraper()
    detector = WeatherAnomalyDetector()

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    logger.info(f"Fetching weather data for {len(INDIA_CITIES)} cities ({start_date} to {end_date})")

    try:
        all_data = scraper.fetch_all_cities_historical(start_date, end_date)
    except Exception as e:
        logger.error(f"Failed to fetch weather data: {e}")
        return

    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    total_anomalies = 0

    for city_obj in INDIA_CITIES:
        city = city_obj.name
        df = all_data.get(city)
        if df is None or df.empty:
            logger.warning(f"No data for {city}, skipping")
            continue

        # Load climate normals
        normals = _load_normals(city)
        if normals is not None and not normals.empty:
            # Compute z-scores
            df = detector.compute_anomaly_scores(df, normals)

        # Upsert observations
        _upsert_observations(city, df)

        # Detect anomalies (only if we have normals)
        if normals is not None and not normals.empty:
            anomalies = detector.detect_all(city, df, normals)
            if anomalies:
                saved = _save_anomalies(anomalies)
                total_anomalies += len(saved)

                # Publish alerts for new anomalies
                for a in anomalies:
                    try:
                        alert = json.dumps({
                            "event_type": "weather_anomaly",
                            "anomaly_type": a.anomaly_type,
                            "city": a.city,
                            "severity": a.severity,
                            "start_date": str(a.start_date),
                            "end_date": str(a.end_date) if a.end_date else None,
                            "peak_value": a.peak_value,
                            "z_score": a.z_score,
                            "description": a.description,
                            "detected_at": datetime.now().isoformat(),
                        })
                        r.publish(WEATHER_ALERT_CHANNEL, alert)
                        r.publish(LIVE_FEED_CHANNEL, alert)
                    except Exception as e:
                        logger.debug(f"Failed to publish alert: {e}")

    r.close()
    logger.info(f"Weather cycle complete: {len(all_data)} cities, {total_anomalies} new anomalies")


def bootstrap_normals():
    """One-time: compute and store 30-year climate normals for all cities.

    Skips cities that already have normals in Postgres (safe to re-run).
    Sleeps between requests to respect Open-Meteo's minutely rate limit.
    """
    scraper = WeatherScraper()
    rate_limit_delay = 35  # seconds between API calls to stay under free-tier limit

    for i, city in enumerate(INDIA_CITIES):
        # Skip cities that already have normals
        existing = _load_normals(city.name)
        if existing is not None and not existing.empty:
            logger.info(f"[{i+1}/{len(INDIA_CITIES)}] {city.name}: normals already exist ({len(existing)} rows), skipping")
            continue

        logger.info(f"[{i+1}/{len(INDIA_CITIES)}] Computing climate normals for {city.name}...")
        try:
            raw = scraper.fetch_climate_normals(city)
            normals_df = scraper.compute_monthly_normals(raw)
            _save_normals(city.name, normals_df)
        except Exception as e:
            logger.error(f"Failed to compute normals for {city.name}: {e}")

        # Rate-limit: wait between requests (skip delay after the last city)
        if i < len(INDIA_CITIES) - 1:
            logger.info(f"Waiting {rate_limit_delay}s for rate limit...")
            time.sleep(rate_limit_delay)


def backfill_historical(years: int):
    """One-time: backfill N years of historical data for all cities."""
    scraper = WeatherScraper()
    detector = WeatherAnomalyDetector()

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=365 * years)).strftime("%Y-%m-%d")

    logger.info(f"Backfilling {years} years of data ({start_date} to {end_date})")

    for city in INDIA_CITIES:
        logger.info(f"Backfilling {city.name}...")
        try:
            df = scraper.fetch_historical(city, start_date, end_date)
            normals = _load_normals(city.name)
            if normals is not None and not normals.empty:
                df = detector.compute_anomaly_scores(df, normals)
            count = _upsert_observations(city.name, df)
            logger.info(f"  {city.name}: {count} observations saved")
        except Exception as e:
            logger.error(f"Failed to backfill {city.name}: {e}")


# ──────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Weather data producer")
    parser.add_argument("--bootstrap-normals", action="store_true",
                        help="Compute and store 30-year climate normals")
    parser.add_argument("--backfill", action="store_true",
                        help="Backfill historical weather data")
    parser.add_argument("--years", type=int, default=WEATHER_HISTORICAL_BACKFILL_YEARS,
                        help="Number of years to backfill (default from config)")
    parser.add_argument("--once", action="store_true",
                        help="Run a single cycle and exit")
    args = parser.parse_args()

    if args.bootstrap_normals:
        bootstrap_normals()
        return

    if args.backfill:
        backfill_historical(args.years)
        return

    if args.once:
        run_cycle()
        return

    # Continuous mode
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info("=" * 60)
    logger.info("Starting Weather Producer")
    logger.info(f"  Cities: {len(INDIA_CITIES)}")
    logger.info(f"  Interval: {WEATHER_SCRAPE_INTERVAL_SECONDS}s")
    logger.info("=" * 60)

    while not _shutdown:
        try:
            run_cycle()
        except Exception as e:
            logger.error(f"Weather cycle failed: {e}", exc_info=True)

        logger.info(f"Sleeping {WEATHER_SCRAPE_INTERVAL_SECONDS}s until next cycle...")
        for _ in range(WEATHER_SCRAPE_INTERVAL_SECONDS):
            if _shutdown:
                break
            time.sleep(1)

    logger.info("Weather producer shut down.")


if __name__ == "__main__":
    main()
