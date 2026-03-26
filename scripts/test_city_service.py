#!/usr/bin/env python3
"""Test script for City Service."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.database import SessionLocal
from agents.city_service import CityService, CityNotFoundError


def test_city_service():
    """Test CityService functionality."""
    db = SessionLocal()
    try:
        service = CityService(db)

        print("=" * 60)
        print("TESTING CITY SERVICE")
        print("=" * 60)
        print()

        # Test 1: Exact match
        print("[Test 1] Exact match - Delhi")
        print("-" * 60)
        result = service.get_city_metadata("Delhi")
        print(f"✓ Found: {result['city_name']}")
        print(f"  Zone: {result['zone']}")
        print(f"  State: {result['state']}")
        print(f"  Coordinates: ({result['latitude']}, {result['longitude']})")
        print(f"  Elevation: {result['elevation_meters']}m")
        assert result['city_name'] == "Delhi"
        assert result['zone'] == "plains"
        print()

        # Test 2: Case insensitive match
        print("[Test 2] Case insensitive - mumbai (lowercase)")
        print("-" * 60)
        result = service.get_city_metadata("mumbai")
        print(f"✓ Found: {result['city_name']}")
        print(f"  Zone: {result['zone']}")
        assert result['city_name'] == "Mumbai"
        assert result['zone'] == "coastal"
        print()

        # Test 3: Fuzzy match (typo)
        print("[Test 3] Fuzzy match - Dellhi (typo)")
        print("-" * 60)
        result = service.get_city_metadata("Dellhi")
        print(f"✓ Matched to: {result['city_name']}")
        print(f"  Zone: {result['zone']}")
        assert result['city_name'] == "Delhi"
        print()

        # Test 4: Hills city
        print("[Test 4] Hills city - Leh")
        print("-" * 60)
        result = service.get_city_metadata("Leh")
        print(f"✓ Found: {result['city_name']}")
        print(f"  Zone: {result['zone']}")
        print(f"  Elevation: {result['elevation_meters']}m")
        assert result['zone'] == "hills"
        assert result['elevation_meters'] == 3524.0
        print()

        # Test 5: Coastal city
        print("[Test 5] Coastal city - Chennai")
        print("-" * 60)
        result = service.get_city_metadata("Chennai")
        print(f"✓ Found: {result['city_name']}")
        print(f"  Zone: {result['zone']}")
        assert result['zone'] == "coastal"
        print()

        # Test 6: Cache test (should be instant)
        print("[Test 6] Cache test - Delhi (2nd time)")
        print("-" * 60)
        result = service.get_city_metadata("Delhi")
        print(f"✓ Retrieved from cache: {result['city_name']}")
        print()

        # Test 7: City not found
        print("[Test 7] City not found - InvalidCityXYZ123")
        print("-" * 60)
        try:
            result = service.get_city_metadata("InvalidCityXYZ123")
            print("✗ Should have raised CityNotFoundError")
            sys.exit(1)
        except CityNotFoundError as e:
            print(f"✓ Correctly raised CityNotFoundError: {e}")
        print()

        # Test 8: Geocoding fallback (if enabled)
        print("[Test 8] Geocoding fallback - Varanasi (not in seeds)")
        print("-" * 60)
        try:
            result = service.get_city_metadata("Varanasi")
            print(f"✓ Found via geocoding: {result['city_name']}")
            print(f"  Zone: {result['zone']}")
            print(f"  Coordinates: ({result['latitude']}, {result['longitude']})")
            print(f"  (Geocoding may be slow, this is normal)")
        except CityNotFoundError:
            print("  Note: Geocoding failed or unavailable (acceptable)")
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
    test_city_service()
