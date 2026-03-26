#!/usr/bin/env python3
"""Test script to verify database seeding."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func
from models.database import SessionLocal
from models.entity_type_domain_mapping import EntityTypeDomainMapping
from models.weather_threshold import WeatherThreshold
from models.scoring_weight import ScoringWeight
from models.city_metadata import CityMetadata


def test_seeds():
    """Test that all seeds were loaded correctly."""
    db = SessionLocal()
    try:
        print("=" * 60)
        print("TESTING DATABASE SEEDS")
        print("=" * 60)
        print()

        # Test 1: Entity Type Domain Mappings
        print("[1/4] Entity Type Domain Mappings")
        print("-" * 60)
        count = db.execute(select(func.count()).select_from(EntityTypeDomainMapping)).scalar()
        print(f"Total mappings: {count}")

        # Get a sample
        sample = db.execute(select(EntityTypeDomainMapping).limit(3)).scalars().all()
        for mapping in sample:
            print(f"  - {mapping.entity_type} → {mapping.primary_domain} (confidence: {mapping.confidence})")

        assert count >= 9, f"Expected at least 9 mappings, got {count}"
        print("✓ Entity mappings test passed")
        print()

        # Test 2: Weather Thresholds
        print("[2/4] Weather Thresholds")
        print("-" * 60)
        count = db.execute(select(func.count()).select_from(WeatherThreshold)).scalar()
        print(f"Total thresholds: {count}")

        # Get samples by type
        heat_wave = db.execute(
            select(WeatherThreshold).where(WeatherThreshold.threshold_type == "heat_wave_temp")
        ).scalars().all()
        print(f"  Heat wave thresholds: {len(heat_wave)}")
        for hw in heat_wave:
            city_str = f" ({hw.city})" if hw.city else ""
            print(f"    - {hw.zone}{city_str}: {hw.threshold_value}°C")

        assert count >= 14, f"Expected at least 14 thresholds, got {count}"
        print("✓ Weather thresholds test passed")
        print()

        # Test 3: Scoring Weights
        print("[3/4] Scoring Weights")
        print("-" * 60)
        count = db.execute(select(func.count()).select_from(ScoringWeight)).scalar()
        print(f"Total weights: {count}")

        # Get samples by type
        domain_weights = db.execute(
            select(ScoringWeight).where(ScoringWeight.weight_type == "domain_multiplier")
        ).scalars().all()
        print(f"  Domain multipliers: {len(domain_weights)}")
        for w in domain_weights[:5]:
            print(f"    - {w.component_name}: {w.weight_value}")

        formula_weights = db.execute(
            select(ScoringWeight).where(ScoringWeight.weight_type == "importance_formula")
        ).scalars().all()
        print(f"  Formula components: {len(formula_weights)}")
        for w in formula_weights:
            print(f"    - {w.component_name}: {w.weight_value}")

        assert count >= 17, f"Expected at least 17 weights, got {count}"
        print("✓ Scoring weights test passed")
        print()

        # Test 4: City Metadata
        print("[4/4] City Metadata")
        print("-" * 60)
        count = db.execute(select(func.count()).select_from(CityMetadata)).scalar()
        print(f"Total cities: {count}")

        # Get samples by zone
        for zone in ["plains", "coastal", "hills"]:
            zone_cities = db.execute(
                select(CityMetadata).where(CityMetadata.zone == zone)
            ).scalars().all()
            print(f"  {zone.capitalize()} cities: {len(zone_cities)}")
            for city in zone_cities[:3]:
                print(f"    - {city.city_name}, {city.state} (elevation: {city.elevation_meters}m)")

        assert count >= 25, f"Expected at least 25 cities, got {count}"
        print("✓ City metadata test passed")
        print()

        print("=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
        print()
        print("Summary:")
        print(f"  - {db.execute(select(func.count()).select_from(EntityTypeDomainMapping)).scalar()} entity type mappings")
        print(f"  - {db.execute(select(func.count()).select_from(WeatherThreshold)).scalar()} weather thresholds")
        print(f"  - {db.execute(select(func.count()).select_from(ScoringWeight)).scalar()} scoring weights")
        print(f"  - {db.execute(select(func.count()).select_from(CityMetadata)).scalar()} cities")

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    test_seeds()
