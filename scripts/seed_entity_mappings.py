#!/usr/bin/env python3
"""Seed script for entity type to domain mappings."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from models.database import SessionLocal
from models.entity_type_domain_mapping import EntityTypeDomainMapping

INITIAL_MAPPINGS = [
    {
        "entity_type": "Person",
        "primary_domain": "geopolitics",
        "secondary_domains": ["society"],
        "confidence": 0.9,
    },
    {
        "entity_type": "Organization",
        "primary_domain": "economics",
        "secondary_domains": ["geopolitics"],
        "confidence": 0.85,
    },
    {
        "entity_type": "Country",
        "primary_domain": "geopolitics",
        "secondary_domains": [],
        "confidence": 1.0,
    },
    {
        "entity_type": "Location",
        "primary_domain": "geopolitics",
        "secondary_domains": [],
        "confidence": 0.8,
    },
    {
        "entity_type": "Policy",
        "primary_domain": "geopolitics",
        "secondary_domains": ["economics"],
        "confidence": 0.9,
    },
    {
        "entity_type": "Technology",
        "primary_domain": "technology",
        "secondary_domains": ["economics"],
        "confidence": 0.9,
    },
    {
        "entity_type": "Economic_Indicator",
        "primary_domain": "economics",
        "secondary_domains": [],
        "confidence": 1.0,
    },
    {
        "entity_type": "Military_Asset",
        "primary_domain": "defense",
        "secondary_domains": [],
        "confidence": 1.0,
    },
    {
        "entity_type": "Resource",
        "primary_domain": "climate",
        "secondary_domains": ["economics"],
        "confidence": 0.85,
    },
]


def seed_entity_mappings():
    """Seed entity type to domain mappings."""
    db = SessionLocal()
    try:
        print("Seeding entity type domain mappings...")

        for mapping in INITIAL_MAPPINGS:
            # Check if exists
            stmt = select(EntityTypeDomainMapping).where(
                EntityTypeDomainMapping.entity_type == mapping["entity_type"]
            )
            existing = db.execute(stmt).scalar_one_or_none()

            if existing:
                print(f"  ✓ Mapping already exists: {mapping['entity_type']} -> {mapping['primary_domain']}")
            else:
                new_mapping = EntityTypeDomainMapping(**mapping)
                db.add(new_mapping)
                print(f"  + Added: {mapping['entity_type']} -> {mapping['primary_domain']}")

        db.commit()
        print(f"✓ Successfully seeded {len(INITIAL_MAPPINGS)} entity type mappings")

    except Exception as e:
        db.rollback()
        print(f"✗ Error seeding entity mappings: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_entity_mappings()
