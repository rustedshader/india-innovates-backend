#!/usr/bin/env python3
"""Master seed script - runs all seed scripts in order."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.seed_entity_mappings import seed_entity_mappings
from scripts.seed_weather_thresholds import seed_weather_thresholds
from scripts.seed_scoring_weights import seed_scoring_weights
from scripts.seed_city_metadata import seed_city_metadata


def seed_all():
    """Run all seed scripts."""
    print("=" * 60)
    print("RUNNING ALL SEED SCRIPTS")
    print("=" * 60)
    print()

    try:
        # Phase 1: Entity type domain mappings
        print("[1/4] Entity Type Domain Mappings")
        print("-" * 60)
        seed_entity_mappings()
        print()

        # Phase 2: Weather thresholds
        print("[2/4] Weather Thresholds")
        print("-" * 60)
        seed_weather_thresholds()
        print()

        # Phase 3: Scoring weights
        print("[3/4] Scoring Weights")
        print("-" * 60)
        seed_scoring_weights()
        print()

        # Phase 4: City metadata
        print("[4/4] City Metadata")
        print("-" * 60)
        seed_city_metadata()
        print()

        print("=" * 60)
        print("✓ ALL SEEDS COMPLETED SUCCESSFULLY")
        print("=" * 60)

    except Exception as e:
        print()
        print("=" * 60)
        print(f"✗ SEED FAILED: {e}")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    seed_all()
