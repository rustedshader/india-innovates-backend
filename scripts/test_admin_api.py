#!/usr/bin/env python3
"""Test script for Admin API endpoints using FastAPI TestClient."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from api import app

client = TestClient(app)


def test_admin_api():
    """Test all admin API endpoints."""
    print("=" * 60)
    print("TESTING ADMIN API ENDPOINTS")
    print("=" * 60)
    print()

    try:
        # Test 1: Get all entity mappings
        print("[Test 1] GET /admin/entity-mappings - Get all mappings")
        print("-" * 60)
        response = client.get("/admin/entity-mappings")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        mappings = response.json()
        print(f"✓ Retrieved {len(mappings)} mappings")
        for mapping in mappings[:3]:
            print(f"  - {mapping['entity_type']} → {mapping['primary_domain']}")
        assert len(mappings) >= 9, f"Expected at least 9 mappings, got {len(mappings)}"
        print()

        # Test 2: Get specific entity mapping
        print("[Test 2] GET /admin/entity-mappings/Person - Get specific mapping")
        print("-" * 60)
        response = client.get("/admin/entity-mappings/Person")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        mapping = response.json()
        print(f"✓ Entity: {mapping['entity_type']}")
        print(f"  Primary domain: {mapping['primary_domain']}")
        print(f"  Secondary domains: {mapping['secondary_domains']}")
        print(f"  Confidence: {mapping['confidence']}")
        assert mapping['entity_type'] == "Person"
        assert mapping['primary_domain'] == "geopolitics"
        print()

        # Test 3: Create new entity mapping
        print("[Test 3] POST /admin/entity-mappings - Create new mapping")
        print("-" * 60)
        new_mapping = {
            "entity_type": "CyberThreat",
            "primary_domain": "technology",
            "secondary_domains": ["defense"],
            "confidence": 0.85,
        }
        response = client.post("/admin/entity-mappings", json=new_mapping)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        created = response.json()
        print(f"✓ Created mapping: {created['entity_type']} → {created['primary_domain']}")
        print(f"  Secondary domains: {created['secondary_domains']}")
        print(f"  Confidence: {created['confidence']}")
        print()

        # Test 4: Update entity mapping
        print("[Test 4] PUT /admin/entity-mappings/CyberThreat - Update mapping")
        print("-" * 60)
        updated_mapping = {
            "entity_type": "CyberThreat",
            "primary_domain": "defense",
            "secondary_domains": ["technology"],
            "confidence": 0.95,
        }
        response = client.put("/admin/entity-mappings/CyberThreat", json=updated_mapping)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        updated = response.json()
        print(f"✓ Updated mapping: {updated['entity_type']}")
        print(f"  Primary domain: {updated['primary_domain']} (changed)")
        print(f"  Secondary domains: {updated['secondary_domains']}")
        print(f"  Confidence: {updated['confidence']}")
        assert updated['primary_domain'] == "defense"
        assert updated['confidence'] == 0.95
        print()

        # Test 5: Verify update
        print("[Test 5] GET /admin/entity-mappings/CyberThreat - Verify update")
        print("-" * 60)
        response = client.get("/admin/entity-mappings/CyberThreat")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        mapping = response.json()
        print(f"✓ Verified: {mapping['entity_type']} → {mapping['primary_domain']}")
        assert mapping['primary_domain'] == "defense"
        print()

        # Test 6: Delete entity mapping
        print("[Test 6] DELETE /admin/entity-mappings/CyberThreat - Delete mapping")
        print("-" * 60)
        response = client.delete("/admin/entity-mappings/CyberThreat")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        result = response.json()
        print(f"✓ {result['message']}")
        print()

        # Test 7: Verify deletion (should 404)
        print("[Test 7] GET /admin/entity-mappings/CyberThreat - Verify deletion")
        print("-" * 60)
        response = client.get("/admin/entity-mappings/CyberThreat")
        assert response.status_code == 404, f"Expected 404 after deletion, got {response.status_code}"
        print("✓ Correctly returns 404 for deleted mapping")
        print()

        # Test 8: Try to create duplicate (should fail)
        print("[Test 8] POST /admin/entity-mappings - Try to create duplicate")
        print("-" * 60)
        duplicate = {
            "entity_type": "Person",
            "primary_domain": "test",
            "secondary_domains": [],
            "confidence": 0.5,
        }
        response = client.post("/admin/entity-mappings", json=duplicate)
        assert response.status_code == 400, f"Expected 400 for duplicate, got {response.status_code}"
        print("✓ Correctly rejects duplicate entity type")
        print()

        # Test 9: Try to get non-existent mapping
        print("[Test 9] GET /admin/entity-mappings/NonExistent - Test 404")
        print("-" * 60)
        response = client.get("/admin/entity-mappings/NonExistent")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Correctly returns 404 for non-existent mapping")
        print()

        print("=" * 60)
        print("✓ ALL ADMIN API TESTS PASSED")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    test_admin_api()
