#!/usr/bin/env python3
"""Test script for Coordination Analyzer."""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.coordination_analyzer import CoordinationAnalyzer


def test_coordination_analyzer():
    """Test CoordinationAnalyzer functionality."""
    print("=" * 60)
    print("TESTING COORDINATION ANALYZER")
    print("=" * 60)
    print()

    try:
        analyzer = CoordinationAnalyzer()

        # Test 1: High coordination - identical messages
        print("[Test 1] High coordination - identical messages")
        print("-" * 60)
        now = datetime.now()
        articles = [
            {
                "title": "Breaking: Major policy announcement",
                "description": "Government announces new initiative for economic growth",
                "source": "Source A",
                "pub_date": now,
                "url": "http://example.com/1"
            },
            {
                "title": "Breaking: Major policy announcement",
                "description": "Government announces new initiative for economic growth",
                "source": "Source B",
                "pub_date": now + timedelta(minutes=5),
                "url": "http://example.com/2"
            },
            {
                "title": "Breaking: Major policy announcement",
                "description": "Government announces new initiative for economic growth",
                "source": "Source C",
                "pub_date": now + timedelta(minutes=10),
                "url": "http://example.com/3"
            },
        ]
        score = analyzer.analyze_coordination(articles)
        print(f"✓ Coordination score: {score}")
        print(f"  (Expected: high, >0.7 due to identical messages and tight timing)")
        assert score > 0.7, f"Expected high coordination (>0.7), got {score}"
        print()

        # Test 2: Medium coordination - similar messages
        print("[Test 2] Medium coordination - similar messages")
        print("-" * 60)
        articles = [
            {
                "title": "Economic policy announced",
                "description": "New economic initiative launched by government",
                "source": "Source A",
                "pub_date": now,
                "url": "http://example.com/4"
            },
            {
                "title": "Government unveils economic plan",
                "description": "Initiative for economic development revealed",
                "source": "Source B",
                "pub_date": now + timedelta(hours=1),
                "url": "http://example.com/5"
            },
            {
                "title": "New economic strategy announced",
                "description": "Official announcement of growth initiative",
                "source": "Source C",
                "pub_date": now + timedelta(hours=2),
                "url": "http://example.com/6"
            },
        ]
        score = analyzer.analyze_coordination(articles)
        print(f"✓ Coordination score: {score}")
        print(f"  (Expected: medium, 0.4-0.7 due to similar but not identical content)")
        assert 0.4 <= score <= 0.8, f"Expected medium coordination (0.4-0.8), got {score}"
        print()

        # Test 3: Low coordination - different messages
        print("[Test 3] Low coordination - different messages")
        print("-" * 60)
        articles = [
            {
                "title": "Weather update: Rain expected",
                "description": "Meteorological department forecasts rainfall",
                "source": "Source A",
                "pub_date": now,
                "url": "http://example.com/7"
            },
            {
                "title": "Sports: Team wins championship",
                "description": "National team secures victory in finals",
                "source": "Source B",
                "pub_date": now + timedelta(hours=12),
                "url": "http://example.com/8"
            },
            {
                "title": "Technology: New smartphone released",
                "description": "Latest model features advanced camera",
                "source": "Source C",
                "pub_date": now + timedelta(days=1),
                "url": "http://example.com/9"
            },
        ]
        score = analyzer.analyze_coordination(articles)
        print(f"✓ Coordination score: {score}")
        print(f"  (Expected: low, <0.4 due to completely different topics)")
        assert score < 0.5, f"Expected low coordination (<0.5), got {score}"
        print()

        # Test 4: Same source - high network density
        print("[Test 4] Same source - high network density")
        print("-" * 60)
        articles = [
            {
                "title": "Article 1",
                "description": "Content from same source",
                "source": "Coordinated Source",
                "pub_date": now,
                "url": "http://example.com/10"
            },
            {
                "title": "Article 2",
                "description": "More content from same source",
                "source": "Coordinated Source",
                "pub_date": now + timedelta(minutes=30),
                "url": "http://example.com/11"
            },
            {
                "title": "Article 3",
                "description": "Even more from same source",
                "source": "Coordinated Source",
                "pub_date": now + timedelta(hours=1),
                "url": "http://example.com/12"
            },
        ]
        score = analyzer.analyze_coordination(articles)
        print(f"✓ Coordination score: {score}")
        print(f"  (Expected: high, >0.6 due to single source publishing multiple articles)")
        assert score > 0.6, f"Expected high coordination (>0.6), got {score}"
        print()

        # Test 5: Detailed analysis
        print("[Test 5] Detailed analysis with breakdown")
        print("-" * 60)
        articles = [
            {
                "title": "Government policy update",
                "description": "New regulations announced for industry",
                "source": "Source A",
                "pub_date": now,
                "url": "http://example.com/13"
            },
            {
                "title": "Policy changes revealed",
                "description": "Industry regulations updated by authorities",
                "source": "Source B",
                "pub_date": now + timedelta(minutes=15),
                "url": "http://example.com/14"
            },
        ]
        details = analyzer.analyze_with_details(articles)
        print(f"✓ Detailed analysis:")
        print(f"  Coordination score: {details['coordination_score']}")
        print(f"  Message similarity: {details['message_similarity']}")
        print(f"  Timing correlation: {details['timing_correlation']}")
        print(f"  Network density: {details['network_density']}")
        print(f"  Article count: {details['article_count']}")
        print(f"  Unique sources: {details['unique_sources']}")
        assert "coordination_score" in details
        assert "message_similarity" in details
        print()

        # Test 6: Edge case - single article
        print("[Test 6] Edge case - single article")
        print("-" * 60)
        articles = [
            {
                "title": "Single article",
                "description": "Only one article",
                "source": "Source A",
                "pub_date": now,
                "url": "http://example.com/15"
            }
        ]
        score = analyzer.analyze_coordination(articles)
        print(f"✓ Coordination score: {score}")
        print(f"  (Expected: 0.0 for single article)")
        assert score == 0.0, f"Expected 0.0 for single article, got {score}"
        print()

        # Test 7: Edge case - empty list
        print("[Test 7] Edge case - empty list")
        print("-" * 60)
        score = analyzer.analyze_coordination([])
        print(f"✓ Coordination score: {score}")
        print(f"  (Expected: 0.0 for empty list)")
        assert score == 0.0, f"Expected 0.0 for empty list, got {score}"
        print()

        print("=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
        print()
        print("Note: Coordination scores are based on semantic similarity,")
        print("timing patterns, and source clustering. Exact values may vary")
        print("slightly based on the embedding model.")

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    test_coordination_analyzer()
