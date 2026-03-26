#!/bin/bash
# Test script for Admin API endpoints

BASE_URL="http://localhost:8000/admin"

echo "============================================================"
echo "TESTING ADMIN API ENDPOINTS"
echo "============================================================"
echo

# Test 1: Get all entity mappings
echo "[Test 1] GET /admin/entity-mappings - Get all mappings"
echo "------------------------------------------------------------"
curl -s -X GET "$BASE_URL/entity-mappings" | jq '.[0:3]'
echo
echo

# Test 2: Get specific entity mapping
echo "[Test 2] GET /admin/entity-mappings/Person - Get specific mapping"
echo "------------------------------------------------------------"
curl -s -X GET "$BASE_URL/entity-mappings/Person" | jq '.'
echo
echo

# Test 3: Create new entity mapping
echo "[Test 3] POST /admin/entity-mappings - Create new mapping"
echo "------------------------------------------------------------"
curl -s -X POST "$BASE_URL/entity-mappings" \
  -H "Content-Type: application/json" \
  -d '{
    "entity_type": "CyberThreat",
    "primary_domain": "technology",
    "secondary_domains": ["defense"],
    "confidence": 0.85
  }' | jq '.'
echo
echo

# Test 4: Update entity mapping
echo "[Test 4] PUT /admin/entity-mappings/CyberThreat - Update mapping"
echo "------------------------------------------------------------"
curl -s -X PUT "$BASE_URL/entity-mappings/CyberThreat" \
  -H "Content-Type: application/json" \
  -d '{
    "entity_type": "CyberThreat",
    "primary_domain": "defense",
    "secondary_domains": ["technology"],
    "confidence": 0.95
  }' | jq '.'
echo
echo

# Test 5: Get updated mapping
echo "[Test 5] GET /admin/entity-mappings/CyberThreat - Verify update"
echo "------------------------------------------------------------"
curl -s -X GET "$BASE_URL/entity-mappings/CyberThreat" | jq '.'
echo
echo

# Test 6: Delete entity mapping
echo "[Test 6] DELETE /admin/entity-mappings/CyberThreat - Delete mapping"
echo "------------------------------------------------------------"
curl -s -X DELETE "$BASE_URL/entity-mappings/CyberThreat" | jq '.'
echo
echo

# Test 7: Verify deletion
echo "[Test 7] GET /admin/entity-mappings/CyberThreat - Verify deletion (should 404)"
echo "------------------------------------------------------------"
curl -s -X GET "$BASE_URL/entity-mappings/CyberThreat" | jq '.'
echo
echo

echo "============================================================"
echo "ADMIN API TESTS COMPLETE"
echo "============================================================"
