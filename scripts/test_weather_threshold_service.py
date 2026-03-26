#!/usr/bin/env python3
"""Test script for Weather Threshold Service."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.database import SessionLocal
from agents.weather_threshold_service import WeatherThresholdService


def test_weather_threshold_service():
    """Test WeatherThresholdService functionality."""
    print("=" * 60)
    print("TESTING WEATHER THRESHOLD SERVICE")
    print("=" * 60)
    print()

    db = SessionLocal()
    try:
        service = WeatherThresholdService(db)

        # Test 1: Zone-level heat wave threshold
        print("[Test 1] Zone-level heat wave threshold - plains")
        print("-" * 60)
        threshold = service.get_heat_wave_threshold(city=None, zone="plains")
        print(f"✓ Heat wave threshold for plains:")
        print(f"  Temperature: {threshold['threshold_value']}°C")
        print(f"  Departure: {threshold['departure_value']}°C")
        print(f"  Consecutive days: {threshold['consecutive_days']}")
        assert threshold['threshold_value'] == 40.0
        assert threshold['consecutive_days'] == 3
        print()

        # Test 2: Zone-level cold wave threshold
        print("[Test 2] Zone-level cold wave threshold - hills")
        print("-" * 60)
        threshold = service.get_cold_wave_threshold(city=None, zone="hills")
        print(f"✓ Cold wave threshold for hills:")
        print(f"  Temperature: {threshold['threshold_value']}°C")
        print(f"  Departure: {threshold['departure_value']}°C")
        print(f"  Consecutive days: {threshold['consecutive_days']}")
        assert threshold['threshold_value'] == -2.0
        print()

        # Test 3: Coastal heat wave threshold
        print("[Test 3] Coastal heat wave threshold")
        print("-" * 60)
        threshold = service.get_heat_wave_threshold(city=None, zone="coastal")
        print(f"✓ Heat wave threshold for coastal:")
        print(f"  Temperature: {threshold['threshold_value']}°C")
        assert threshold['threshold_value'] == 37.0
        print()

        # Test 4: Rainfall threshold
        print("[Test 4] Extreme rainfall threshold")
        print("-" * 60)
        threshold = service.get_threshold(city=None, zone="plains", threshold_type="extreme_rain")
        print(f"✓ Extreme rain threshold:")
        print(f"  Rainfall: {threshold['threshold_value']}mm")
        assert threshold['threshold_value'] == 204.5
        print()

        # Test 5: Drought threshold
        print("[Test 5] Drought threshold")
        print("-" * 60)
        threshold = service.get_threshold(city=None, zone="plains", threshold_type="drought_soil_z")
        print(f"✓ Drought soil moisture z-score threshold:")
        print(f"  Z-score: {threshold['threshold_value']}")
        assert threshold['threshold_value'] == -1.5
        print()

        # Test 6: Cyclone wind speed threshold
        print("[Test 6] Cyclone wind speed threshold")
        print("-" * 60)
        threshold = service.get_threshold(city=None, zone="coastal", threshold_type="cyclone_wind")
        print(f"✓ Cyclone wind speed threshold:")
        print(f"  Wind speed: {threshold['threshold_value']} km/h")
        assert threshold['threshold_value'] == 90.0
        print()

        # Test 7: Get all thresholds for a city
        print("[Test 7] Get all thresholds for Delhi")
        print("-" * 60)
        all_thresholds = service.get_all_thresholds_for_city("Delhi", "plains")
        print(f"✓ Found {len(all_thresholds)} threshold types for Delhi:")
        for threshold_type, values in all_thresholds.items():
            print(f"  - {threshold_type}: {values['threshold_value']}")
        assert len(all_thresholds) >= 1  # At least heat wave should be found
        print()

        # Test 8: Cache test
        print("[Test 8] Cache test - retrieve same threshold")
        print("-" * 60)
        threshold1 = service.get_heat_wave_threshold(city=None, zone="plains")
        threshold2 = service.get_heat_wave_threshold(city=None, zone="plains")
        print("✓ Retrieved threshold twice (2nd from cache)")
        assert threshold1 == threshold2
        print()

        # Test 9: Error handling for missing threshold
        print("[Test 9] Error handling for missing threshold")
        print("-" * 60)
        try:
            service.get_threshold(city="UnknownCity", zone="unknown_zone", threshold_type="fake_threshold")
            print("✗ FAIL: Should have raised ValueError")
            assert False
        except ValueError as e:
            print(f"✓ Correctly raised ValueError: {str(e)[:80]}...")
        print()

        # Test 10: Clear cache
        print("[Test 10] Clear cache")
        print("-" * 60)
        service.clear_cache()
        print("✓ Cache cleared")
        print()

        print("=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    test_weather_threshold_service()
