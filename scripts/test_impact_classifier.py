#!/usr/bin/env python3
"""Test script for Impact Direction Classifier."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.impact_direction_classifier import ImpactDirectionClassifier


def test_impact_classifier():
    """Test ImpactDirectionClassifier functionality."""
    print("=" * 60)
    print("TESTING IMPACT DIRECTION CLASSIFIER")
    print("=" * 60)
    print()

    try:
        # Try to test with LLM enabled (if API key is available)
        try:
            classifier = ImpactDirectionClassifier(enable_llm=True)
            llm_available = True
            print("✓ LLM enabled (GROQ_API_KEY found)")
        except Exception as e:
            print(f"⚠ LLM not available: {e}")
            print("  Continuing with rule-based tests only")
            classifier = ImpactDirectionClassifier(enable_llm=False)
            llm_available = False
        print()

        # Test 1: Military asset in defense domain
        print("[Test 1] Military asset in defense domain")
        print("-" * 60)
        result = classifier.classify(
            entity_name="J-20 Fighter Jet",
            entity_type="Military_Asset",
            domain="defense",
            relation_type="DEPLOYS",
            scenario_context="China deploys J-20 fighter jets near Indian border" if llm_available else None
        )
        print(f"✓ Classification: {result}")
        print(f"  Entity: J-20 Fighter Jet (Military_Asset)")
        print(f"  Domain: defense")
        print(f"  Method: {'LLM' if llm_available else 'Rules'}")
        assert result in ["risk", "opportunity", "neutral"], f"Invalid direction: {result}"
        print()

        # Test 2: Technology innovation
        print("[Test 2] Technology innovation")
        print("-" * 60)
        result = classifier.classify(
            entity_name="AI Chip",
            entity_type="Technology",
            domain="technology",
            relation_type="INNOVATES",
            scenario_context="India develops new AI chip for autonomous systems" if llm_available else None
        )
        print(f"✓ Classification: {result}")
        print(f"  Entity: AI Chip (Technology)")
        print(f"  Domain: technology")
        print(f"  Method: {'LLM' if llm_available else 'Rules'}")
        assert result in ["risk", "opportunity", "neutral"], f"Invalid direction: {result}"
        print()

        # Test 3: Economic indicator declining
        print("[Test 3] Economic indicator declining")
        print("-" * 60)
        result = classifier.classify(
            entity_name="GDP Growth",
            entity_type="Economic_Indicator",
            domain="economics",
            relation_type="DECLINES",
            scenario_context="GDP growth rate declines to 5.4%" if llm_available else None
        )
        print(f"✓ Classification: {result}")
        print(f"  Entity: GDP Growth (Economic_Indicator)")
        print(f"  Domain: economics")
        print(f"  Method: {'LLM' if llm_available else 'Rules'}")
        assert result in ["risk", "opportunity", "neutral"], f"Invalid direction: {result}"
        print()

        # Test 4: Country forming alliance
        print("[Test 4] Country forming alliance")
        print("-" * 60)
        result = classifier.classify(
            entity_name="Japan",
            entity_type="Country",
            domain="geopolitics",
            relation_type="ALLIANCE",
            scenario_context="Japan strengthens alliance with India on technology sharing" if llm_available else None
        )
        print(f"✓ Classification: {result}")
        print(f"  Entity: Japan (Country)")
        print(f"  Domain: geopolitics")
        print(f"  Method: {'LLM' if llm_available else 'Rules'}")
        assert result in ["risk", "opportunity", "neutral"], f"Invalid direction: {result}"
        print()

        # Test 5: Cache test
        print("[Test 5] Cache test - J-20 again")
        print("-" * 60)
        result = classifier.classify(
            entity_name="J-20 Fighter Jet",
            entity_type="Military_Asset",
            domain="defense",
            relation_type="DEPLOYS",
        )
        print(f"✓ Retrieved from cache: {result}")
        print()

        # Test 6: Rule-based fallback (disable LLM)
        print("[Test 6] Rule-based classification (LLM disabled)")
        print("-" * 60)
        rule_classifier = ImpactDirectionClassifier(enable_llm=False)
        result = rule_classifier.classify(
            entity_name="Cyber Attack",
            entity_type="Military_Asset",
            domain="defense",
            relation_type="THREATENS",
        )
        print(f"✓ Classification via rules: {result}")
        print(f"  Entity: Cyber Attack (Military_Asset)")
        assert result == "risk", f"Expected 'risk', got '{result}'"
        print()

        # Test 7: Batch classification
        print("[Test 7] Batch classification")
        print("-" * 60)
        entities = [
            {"name": "GDP", "type": "Economic_Indicator", "domain": "economics", "relation_type": "GROWS"},
            {"name": "Missile System", "type": "Military_Asset", "domain": "defense", "relation_type": "DEPLOYS"},
            {"name": "Trade Agreement", "type": "Policy", "domain": "geopolitics", "relation_type": "REFORM"},
        ]
        results = classifier.classify_batch(
            entities,
            scenario_context="Regional economic and security developments" if llm_available else None
        )
        print(f"✓ Classified {len(results)} entities:")
        for entity, direction in zip(entities, results):
            print(f"  - {entity['name']} ({entity['type']}) → {direction}")
            assert direction in ["risk", "opportunity", "neutral"], f"Invalid direction: {direction}"
        print()

        # Test 8: Clear cache
        print("[Test 8] Clear cache")
        print("-" * 60)
        classifier.clear_cache()
        print("✓ Cache cleared")
        print()

        print("=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
        print()
        print("Note: LLM classifications may vary based on model output.")
        print("The tests verify the classifier runs without errors and")
        print("returns valid directions (risk/opportunity/neutral).")

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    test_impact_classifier()
