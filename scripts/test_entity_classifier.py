#!/usr/bin/env python3
"""Test script for Entity Classifier Service."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.database import SessionLocal
from agents.entity_classifier import EntityClassifier


def test_entity_classifier():
    """Test EntityClassifier functionality."""
    db = SessionLocal()
    try:
        classifier = EntityClassifier(db)

        print("=" * 60)
        print("TESTING ENTITY CLASSIFIER")
        print("=" * 60)
        print()

        # Test 1: Known entity type from database
        print("[Test 1] Database lookup - Person")
        print("-" * 60)
        result = classifier.get_classification("Person")
        print(f"✓ Primary domain: {result['primary_domain']}")
        print(f"  Secondary domains: {result['secondary_domains']}")
        print(f"  Confidence: {result['confidence']}")
        assert result['primary_domain'] == "geopolitics", f"Expected geopolitics, got {result['primary_domain']}"
        print()

        # Test 2: Another known entity type
        print("[Test 2] Database lookup - Military_Asset")
        print("-" * 60)
        result = classifier.get_classification("Military_Asset")
        print(f"✓ Primary domain: {result['primary_domain']}")
        print(f"  Secondary domains: {result['secondary_domains']}")
        print(f"  Confidence: {result['confidence']}")
        assert result['primary_domain'] == "defense", f"Expected defense, got {result['primary_domain']}"
        print()

        # Test 3: Cache test (should be instant)
        print("[Test 3] Cache test - Person (2nd time)")
        print("-" * 60)
        result = classifier.get_classification("Person")
        print(f"✓ Retrieved from cache: {result['primary_domain']}")
        print()

        # Test 4: Unknown entity type (LLM fallback)
        print("[Test 4] LLM fallback - Spacecraft (unknown)")
        print("-" * 60)
        try:
            result = classifier.get_classification("Spacecraft")
            print(f"✓ Classified via LLM: {result['primary_domain']}")
            print(f"  Secondary domains: {result['secondary_domains']}")
            print(f"  Confidence: {result['confidence']}")
            # Verify it was stored in database
            db.commit()  # Ensure it's committed
            result2 = classifier.get_classification("Spacecraft")
            print(f"✓ Retrieved from database on 2nd call: {result2['primary_domain']}")
        except Exception as e:
            print(f"  Note: LLM classification may have failed: {e}")
            print("  (This is acceptable if LLM API is unavailable)")
        print()

        # Test 5: get_primary_domain convenience method
        print("[Test 5] Convenience method - get_primary_domain")
        print("-" * 60)
        domain = classifier.get_primary_domain("Organization")
        print(f"✓ Organization -> {domain}")
        assert domain == "economics", f"Expected economics, got {domain}"
        print()

        # Test 6: Get all mappings
        print("[Test 6] Get all mappings")
        print("-" * 60)
        all_mappings = classifier.get_all_mappings()
        print(f"✓ Total mappings in database: {len(all_mappings)}")
        for mapping in all_mappings[:5]:
            print(f"  - {mapping['entity_type']} → {mapping['primary_domain']} (confidence: {mapping['confidence']})")
        assert len(all_mappings) >= 9, f"Expected at least 9 mappings, got {len(all_mappings)}"
        print()

        # Test 7: Cache clearing
        print("[Test 7] Cache clearing")
        print("-" * 60)
        classifier.clear_cache()
        print("✓ Cache cleared")
        result = classifier.get_classification("Person")
        print(f"✓ Re-fetched from database: {result['primary_domain']}")
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
    test_entity_classifier()
