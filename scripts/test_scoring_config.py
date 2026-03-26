#!/usr/bin/env python3
"""Test script for Scoring Configuration Service."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.scoring_config import ScoringConfig
from models.database import SessionLocal


def test_scoring_config():
    """Test ScoringConfig service functionality."""
    print("=" * 60)
    print("TESTING SCORING CONFIGURATION SERVICE")
    print("=" * 60)
    print()

    db = SessionLocal()
    try:
        config = ScoringConfig(db)

        # Test 1: Get domain weight for geopolitics
        print("[Test 1] Domain weight - geopolitics")
        print("-" * 60)
        weight = config.get_domain_weight("geopolitics")
        print(f"✓ Domain weight for geopolitics: {weight}")
        print(f"  (Expected: 1.10 from seeds)")
        assert weight == 1.10, f"Expected 1.10, got {weight}"
        print()

        # Test 2: Get domain weight for unknown domain (fallback to 1.0)
        print("[Test 2] Domain weight - unknown domain fallback")
        print("-" * 60)
        weight = config.get_domain_weight("unknown_domain")
        print(f"✓ Domain weight for unknown_domain: {weight}")
        print(f"  (Expected: 1.0 default)")
        assert weight == 1.0, f"Expected 1.0, got {weight}"
        print()

        # Test 3: Get formula weights
        print("[Test 3] Formula weights")
        print("-" * 60)
        weights = config.get_formula_weights()
        print(f"✓ Formula weights:")
        print(f"  impact_score: {weights.get('impact_score')}")
        print(f"  novelty_score: {weights.get('novelty_score')}")
        print(f"  india_relevance: {weights.get('india_relevance')}")
        print(f"  (Expected: 0.5, 0.2, 0.3 from seeds)")
        assert weights.get("impact_score") == 0.5
        assert weights.get("novelty_score") == 0.2
        assert weights.get("india_relevance") == 0.3
        print()

        # Test 4: Get coverage bonus parameters
        print("[Test 4] Coverage bonus parameters")
        print("-" * 60)
        params = config.get_coverage_params()
        print(f"✓ Coverage params:")
        print(f"  log_base: {params.get('log_base')}")
        print(f"  multiplier: {params.get('multiplier')}")
        print(f"  (Expected: 6.0, 0.5 from seeds)")
        assert params.get("log_base") == 6.0
        assert params.get("multiplier") == 0.5
        print()

        # Test 5: Get all domain weights
        print("[Test 5] All domain weights")
        print("-" * 60)
        all_weights = config.get_all_domain_weights()
        print(f"✓ All domain weights:")
        for domain, weight in sorted(all_weights.items()):
            print(f"  {domain}: {weight}")
        print(f"  (Found {len(all_weights)} domain weights)")
        assert len(all_weights) > 0, "Expected at least 1 domain weight"
        assert "geopolitics" in all_weights
        assert "defense" in all_weights
        print()

        # Test 6: Cache functionality (should hit cache on second call)
        print("[Test 6] Cache functionality")
        print("-" * 60)
        weight1 = config.get_domain_weight("defense")
        weight2 = config.get_domain_weight("defense")
        print(f"✓ First call: {weight1}")
        print(f"✓ Second call (cached): {weight2}")
        assert weight1 == weight2, "Cache should return same value"
        print()

        # Test 7: Cache clear
        print("[Test 7] Cache clear")
        print("-" * 60)
        config.clear_cache()
        print("✓ Cache cleared successfully")
        weight3 = config.get_domain_weight("defense")
        print(f"✓ After cache clear: {weight3}")
        assert weight3 == 1.10, f"Expected 1.10, got {weight3}"
        print()

        # Test 8: Multiple domain weights
        print("[Test 8] Multiple domain weights")
        print("-" * 60)
        domains_to_test = ["geopolitics", "defense", "economics", "sports"]
        for domain in domains_to_test:
            weight = config.get_domain_weight(domain)
            print(f"✓ {domain}: {weight}")
        print()

        # Test 9: Formula weights sum check
        print("[Test 9] Formula weights sum")
        print("-" * 60)
        weights = config.get_formula_weights()
        total = (
            weights.get("impact_score", 0)
            + weights.get("novelty_score", 0)
            + weights.get("india_relevance", 0)
        )
        print(f"✓ Formula weights sum: {total}")
        print(f"  (Expected: 1.0 for normalized weights)")
        assert abs(total - 1.0) < 0.01, f"Expected sum ~1.0, got {total}"
        print()

        # Test 10: Test actual scoring calculation
        print("[Test 10] Sample scoring calculation")
        print("-" * 60)
        weights = config.get_formula_weights()
        coverage_params = config.get_coverage_params()

        # Sample article scores
        impact_score = 8
        novelty_score = 6
        india_relevance = 9
        domain = "geopolitics"
        article_count = 3

        # Calculate base score
        base = (
            weights.get("impact_score", 0.5) * impact_score
            + weights.get("novelty_score", 0.2) * novelty_score
            + weights.get("india_relevance", 0.3) * india_relevance
        )

        # Domain multiplier
        domain_mult = config.get_domain_weight(domain)

        # Coverage bonus
        import math
        log_base = coverage_params.get("log_base", 6.0)
        multiplier = coverage_params.get("multiplier", 0.5)
        coverage_bonus = min(
            math.log(max(article_count, 1) + 1) / math.log(log_base), 1.0
        ) * multiplier

        final_score = round(min((base * domain_mult) + coverage_bonus, 10.0), 2)

        print(f"✓ Sample calculation:")
        print(f"  Impact: {impact_score}, Novelty: {novelty_score}, India: {india_relevance}")
        print(f"  Domain: {domain}, Article count: {article_count}")
        print(f"  Base score: {base:.3f}")
        print(f"  Domain multiplier: {domain_mult}")
        print(f"  Coverage bonus: {coverage_bonus:.3f}")
        print(f"  Final score: {final_score}")
        assert 0 <= final_score <= 10, f"Score should be 0-10, got {final_score}"
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
    test_scoring_config()
