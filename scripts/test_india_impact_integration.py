#!/usr/bin/env python3
"""Integration test for India Impact Agent with dynamic entity discovery."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.india_impact import IndiaImpactAgent
from agents.india_entity_service import IndiaEntityService
from models.database import SessionLocal


def test_india_impact_integration():
    """Test that India Impact Agent uses database-backed entity discovery."""
    print("=" * 60)
    print("TESTING INDIA IMPACT AGENT INTEGRATION")
    print("=" * 60)
    print()

    try:
        # Test 1: Verify India entities are in database
        print("[Test 1] Verify India entities in database")
        print("-" * 60)
        db = SessionLocal()
        try:
            service = IndiaEntityService(db)
            entities = service.get_india_entities(min_relevance_score=0.1)
            print(f"✓ Found {len(entities)} India entities in database")

            if len(entities) == 0:
                print("  Note: Database is empty, refreshing from graph...")
                result = service.refresh_database(max_hops=3, min_connection_count=2)
                print(f"  ✓ Refreshed: added {result['added']} entities")
                entities = service.get_india_entities(min_relevance_score=0.1)
                print(f"  ✓ Now have {len(entities)} entities")

            assert len(entities) > 0, "Should have India entities after refresh"

            # Show sample entities
            print(f"  Sample entities: {list(entities)[:10]}")

        finally:
            db.close()
            service.close()
        print()

        # Test 2: Verify agent uses database (not hardcoded)
        print("[Test 2] Verify IndiaImpactAgent uses database")
        print("-" * 60)
        agent = IndiaImpactAgent()
        try:
            discovered = agent._discover_india_entities()
            print(f"✓ Agent discovered {len(discovered)} entities")

            # Verify these match database entities
            db2 = SessionLocal()
            try:
                service2 = IndiaEntityService(db2)
                db_entities = service2.get_india_entities(min_relevance_score=0.3)

                # Check overlap
                overlap = discovered.intersection(db_entities)
                print(f"  Overlap with database: {len(overlap)}/{len(discovered)} entities")

                # Should have significant overlap (database entities are subset of discovered)
                if db_entities:
                    overlap_pct = len(overlap) / len(db_entities) * 100 if db_entities else 0
                    print(f"  Coverage: {overlap_pct:.1f}% of database entities")
                    assert overlap_pct >= 80, f"Expected >=80% overlap, got {overlap_pct:.1f}%"
            finally:
                db2.close()

        finally:
            agent.close()
        print()

        # Test 3: Verify no hardcoded INDIA_SEED_ENTITIES usage
        print("[Test 3] Verify no hardcoded fallback")
        print("-" * 60)
        # Read the source file and check it doesn't contain INDIA_SEED_ENTITIES constant
        with open(Path(__file__).parent.parent / "agents" / "india_impact.py", "r") as f:
            content = f.read()

        # Check that INDIA_SEED_ENTITIES constant is not defined
        if "INDIA_SEED_ENTITIES: set[str] = {" in content:
            print("✗ FAIL: Hardcoded INDIA_SEED_ENTITIES constant still exists!")
            assert False
        else:
            print("✓ PASS: Hardcoded INDIA_SEED_ENTITIES constant removed")

        # Check that IndiaEntityService is imported
        if "from agents.india_entity_service import IndiaEntityService" in content:
            print("✓ PASS: IndiaEntityService import found")
        else:
            print("✗ FAIL: IndiaEntityService not imported")
            assert False

        print()

        print("=" * 60)
        print("✓ ALL INTEGRATION TESTS PASSED")
        print("=" * 60)
        print()
        print("Summary:")
        print("  ✓ India entities stored in database")
        print("  ✓ IndiaImpactAgent uses database for entity discovery")
        print("  ✓ No hardcoded INDIA_SEED_ENTITIES fallback")
        print("  ✓ Dynamic entity discovery working correctly")
        print()

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    test_india_impact_integration()
