#!/usr/bin/env python3
"""Seed script for weather anomaly thresholds."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from models.database import SessionLocal
from models.weather_threshold import WeatherThreshold

INITIAL_THRESHOLDS = [
    # Heat waves by zone
    {
        "city": None,
        "zone": "plains",
        "season": None,
        "threshold_type": "heat_wave_temp",
        "threshold_value": 40.0,
        "departure_value": 4.5,
        "consecutive_days": 3,
        "active": True,
    },
    {
        "city": None,
        "zone": "coastal",
        "season": None,
        "threshold_type": "heat_wave_temp",
        "threshold_value": 37.0,
        "departure_value": 4.5,
        "consecutive_days": 3,
        "active": True,
    },
    {
        "city": None,
        "zone": "hills",
        "season": None,
        "threshold_type": "heat_wave_temp",
        "threshold_value": 30.0,
        "departure_value": 5.0,
        "consecutive_days": 3,
        "active": True,
    },
    # Cold waves by zone
    {
        "city": None,
        "zone": "plains",
        "season": None,
        "threshold_type": "cold_wave_temp",
        "threshold_value": 4.0,
        "departure_value": -4.5,
        "consecutive_days": 3,
        "active": True,
    },
    {
        "city": None,
        "zone": "coastal",
        "season": None,
        "threshold_type": "cold_wave_temp",
        "threshold_value": 10.0,
        "departure_value": -4.5,
        "consecutive_days": 3,
        "active": True,
    },
    {
        "city": None,
        "zone": "hills",
        "season": None,
        "threshold_type": "cold_wave_temp",
        "threshold_value": -2.0,
        "departure_value": -5.0,
        "consecutive_days": 3,
        "active": True,
    },
    # Rainfall thresholds
    {
        "city": None,
        "zone": "plains",
        "season": None,
        "threshold_type": "extreme_rain",
        "threshold_value": 204.5,
        "departure_value": None,
        "consecutive_days": 1,
        "active": True,
    },
    {
        "city": None,
        "zone": "coastal",
        "season": None,
        "threshold_type": "extreme_rain",
        "threshold_value": 204.5,
        "departure_value": None,
        "consecutive_days": 1,
        "active": True,
    },
    {
        "city": None,
        "zone": "hills",
        "season": None,
        "threshold_type": "extreme_rain",
        "threshold_value": 204.5,
        "departure_value": None,
        "consecutive_days": 1,
        "active": True,
    },
    {
        "city": None,
        "zone": "plains",
        "season": None,
        "threshold_type": "very_heavy_rain",
        "threshold_value": 115.6,
        "departure_value": None,
        "consecutive_days": 1,
        "active": True,
    },
    {
        "city": None,
        "zone": "plains",
        "season": None,
        "threshold_type": "heavy_rain",
        "threshold_value": 64.5,
        "departure_value": None,
        "consecutive_days": 1,
        "active": True,
    },
    # Drought (soil moisture z-score)
    {
        "city": None,
        "zone": "plains",
        "season": None,
        "threshold_type": "drought_soil_z",
        "threshold_value": -1.5,
        "departure_value": None,
        "consecutive_days": 7,
        "active": True,
    },
    # Cyclone (wind speed)
    {
        "city": None,
        "zone": "coastal",
        "season": None,
        "threshold_type": "cyclone_wind",
        "threshold_value": 90.0,  # km/h
        "departure_value": None,
        "consecutive_days": 1,
        "active": True,
    },
    # City-specific overrides
    {
        "city": "Leh",
        "zone": "hills",
        "season": None,
        "threshold_type": "cold_wave_temp",
        "threshold_value": -10.0,
        "departure_value": -5.0,
        "consecutive_days": 3,
        "active": True,
    },
]


def seed_weather_thresholds():
    """Seed weather anomaly thresholds."""
    db = SessionLocal()
    try:
        print("Seeding weather thresholds...")

        for threshold in INITIAL_THRESHOLDS:
            # Check if exists
            stmt = select(WeatherThreshold).where(
                WeatherThreshold.city == threshold["city"],
                WeatherThreshold.zone == threshold["zone"],
                WeatherThreshold.season == threshold["season"],
                WeatherThreshold.threshold_type == threshold["threshold_type"],
            )
            existing = db.execute(stmt).scalar_one_or_none()

            if existing:
                city_part = f"city={threshold['city']}, " if threshold['city'] else ""
                print(
                    f"  ✓ Threshold already exists: {city_part}zone={threshold['zone']}, "
                    f"type={threshold['threshold_type']}"
                )
            else:
                new_threshold = WeatherThreshold(**threshold)
                db.add(new_threshold)
                city_part = f"city={threshold['city']}, " if threshold['city'] else ""
                print(
                    f"  + Added: {city_part}zone={threshold['zone']}, "
                    f"type={threshold['threshold_type']}, value={threshold['threshold_value']}"
                )

        db.commit()
        print(f"✓ Successfully seeded {len(INITIAL_THRESHOLDS)} weather thresholds")

    except Exception as e:
        db.rollback()
        print(f"✗ Error seeding weather thresholds: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_weather_thresholds()
