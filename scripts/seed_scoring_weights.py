#!/usr/bin/env python3
"""Seed script for scoring formula weights."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from models.database import SessionLocal
from models.scoring_weight import ScoringWeight

INITIAL_WEIGHTS = [
    # Domain multipliers (from DOMAIN_WEIGHT in news_priority.py)
    {"weight_type": "domain_multiplier", "component_name": "geopolitics", "weight_value": 1.10, "version": 1, "active": True},
    {"weight_type": "domain_multiplier", "component_name": "defense", "weight_value": 1.10, "version": 1, "active": True},
    {"weight_type": "domain_multiplier", "component_name": "diplomacy", "weight_value": 1.10, "version": 1, "active": True},
    {"weight_type": "domain_multiplier", "component_name": "economics", "weight_value": 1.05, "version": 1, "active": True},
    {"weight_type": "domain_multiplier", "component_name": "energy", "weight_value": 1.05, "version": 1, "active": True},
    {"weight_type": "domain_multiplier", "component_name": "technology", "weight_value": 1.05, "version": 1, "active": True},
    {"weight_type": "domain_multiplier", "component_name": "health", "weight_value": 1.00, "version": 1, "active": True},
    {"weight_type": "domain_multiplier", "component_name": "climate", "weight_value": 1.00, "version": 1, "active": True},
    {"weight_type": "domain_multiplier", "component_name": "society", "weight_value": 0.95, "version": 1, "active": True},
    {"weight_type": "domain_multiplier", "component_name": "culture", "weight_value": 0.90, "version": 1, "active": True},
    {"weight_type": "domain_multiplier", "component_name": "sports", "weight_value": 0.85, "version": 1, "active": True},
    {"weight_type": "domain_multiplier", "component_name": "human_interest", "weight_value": 0.85, "version": 1, "active": True},
    # Formula components (line 291 in news_priority.py)
    {"weight_type": "importance_formula", "component_name": "impact_score", "weight_value": 0.50, "version": 1, "active": True},
    {"weight_type": "importance_formula", "component_name": "novelty_score", "weight_value": 0.20, "version": 1, "active": True},
    {"weight_type": "importance_formula", "component_name": "india_relevance", "weight_value": 0.30, "version": 1, "active": True},
    # Coverage bonus parameters (line 298 in news_priority.py)
    {"weight_type": "coverage_bonus", "component_name": "log_base", "weight_value": 6.0, "version": 1, "active": True},
    {"weight_type": "coverage_bonus", "component_name": "multiplier", "weight_value": 0.5, "version": 1, "active": True},
]


def seed_scoring_weights():
    """Seed scoring formula weights."""
    db = SessionLocal()
    try:
        print("Seeding scoring weights...")

        for weight in INITIAL_WEIGHTS:
            # Check if exists
            stmt = select(ScoringWeight).where(
                ScoringWeight.weight_type == weight["weight_type"],
                ScoringWeight.component_name == weight["component_name"],
                ScoringWeight.version == weight["version"],
            )
            existing = db.execute(stmt).scalar_one_or_none()

            if existing:
                print(
                    f"  ✓ Weight already exists: {weight['weight_type']}/{weight['component_name']} "
                    f"= {weight['weight_value']} (v{weight['version']})"
                )
            else:
                new_weight = ScoringWeight(**weight)
                db.add(new_weight)
                print(
                    f"  + Added: {weight['weight_type']}/{weight['component_name']} "
                    f"= {weight['weight_value']} (v{weight['version']})"
                )

        db.commit()
        print(f"✓ Successfully seeded {len(INITIAL_WEIGHTS)} scoring weights")

    except Exception as e:
        db.rollback()
        print(f"✗ Error seeding scoring weights: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_scoring_weights()
