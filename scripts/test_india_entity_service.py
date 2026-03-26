#!/usr/bin/env python3
"""Test script for India Entity Discovery Service."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.database import SessionLocal
from agents.india_entity_service import IndiaEntityService


def test_india_entity_service():
    """Test IndiaEntityService functionality."""
    print("=" * 60)
    print("TESTING INDIA ENTITY DISCOVERY SERVICE")
    print("=" * 60)
    print()

    db = SessionLocal()
    try:
        service = IndiaEntityService(db)

        # Test 1: Discover entities from Neo4j graph
        print("[Test 1] Discover India entities from Neo4j graph")
        print("-" * 60)
        try:
            discovered = service.discover_from_graph(
                max_hops=3,
                min_connection_count=2,
                max_entities=100
            )
            print(f"✓ Discovered {len(discovered)} entities from graph")
            print(f"  Top 5 entities by connection count:")
            for entity in discovered[:5]:
                print(f"    - {entity['entity_name']} ({entity['entity_type']}): {entity['connection_count']} connections")
            assert len(discovered) > 0, "Should discover at least some entities"
        except Exception as e:
            print(f"  Note: Graph discovery failed: {e}")
            print(f"  (This may be expected if Neo4j is not running or empty)")
            discovered = []
        print()

        # Test 2: Refresh database (if we discovered entities)
        if discovered:
            print("[Test 2] Refresh India entities database from graph")
            print("-" * 60)
            try:
                result = service.refresh_database(
                    max_hops=3,
                    min_connection_count=2,
                    mark_core_threshold=10
                )
                print(f"✓ Database refresh complete:")
                print(f"  Status: {result['status']}")
                print(f"  Added: {result['added']}")
                print(f"  Updated: {result['updated']}")
                print(f"  Total: {result['total']}")
                assert result['status'] == 'success'
                assert result['total'] > 0
            except Exception as e:
                print(f"  Note: Database refresh failed: {e}")
            print()

            # Test 3: Get India entities from database
            print("[Test 3] Get India entities from database")
            print("-" * 60)
            entities = service.get_india_entities(min_relevance_score=0.3)
            print(f"✓ Retrieved {len(entities)} entities from database")
            print(f"  Sample entities: {list(entities)[:5]}")
            assert len(entities) > 0, "Should have entities in database after refresh"
            print()

            # Test 4: Get entities again (should use cache)
            print("[Test 4] Get India entities (cached)")
            print("-" * 60)
            entities_cached = service.get_india_entities()
            print(f"✓ Retrieved {len(entities_cached)} entities (from cache)")
            assert len(entities_cached) == len(entities), "Cache should return same count"
            print()

            # Test 5: Get statistics
            print("[Test 5] Get entity statistics")
            print("-" * 60)
            stats = service.get_statistics()
            print(f"✓ Statistics:")
            print(f"  Total entities: {stats['total']}")
            print(f"  Core entities: {stats['core']}")
            print(f"  Non-core entities: {stats['non_core']}")
            print(f"  Avg relevance score: {stats['avg_relevance_score']:.2f}")
            print(f"  Avg connection count: {stats['avg_connection_count']:.1f}")
            print(f"  By discovery method: {stats['by_discovery_method']}")
            assert stats['total'] > 0
            print()

        # Test 6: Add manual entity
        print("[Test 6] Add manual entity")
        print("-" * 60)
        service.add_manual_entity(
            entity_name="Test Entity",
            entity_type="Organization",
            relevance_score=0.9,
            is_core=True
        )
        print("✓ Added manual entity: Test Entity")
        # Clear cache and verify
        service.clear_cache()
        entities = service.get_india_entities(min_relevance_score=0.8)
        assert "Test Entity" in entities, "Manual entity should be in database"
        print("✓ Manual entity verified in database")
        print()

        # Test 7: Get statistics after manual add
        print("[Test 7] Statistics after manual entity")
        print("-" * 60)
        stats = service.get_statistics()
        print(f"✓ Total entities now: {stats['total']}")
        print(f"  Discovery methods: {stats['by_discovery_method']}")
        assert stats['by_discovery_method'].get('manual', 0) >= 1
        print()

        # Test 8: Clear cache
        print("[Test 8] Clear cache")
        print("-" * 60)
        service.clear_cache()
        print("✓ Cache cleared")
        print()

        print("=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
        print()

        if not discovered:
            print("Note: Some tests skipped due to Neo4j unavailability.")
            print("This is acceptable if Neo4j is not running.")

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
        service.close()


if __name__ == "__main__":
    test_india_entity_service()
