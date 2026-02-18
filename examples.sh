#!/bin/bash

set -e

BASE_URL="${API_URL:-http://localhost:8000}"

echo "=============================================="
echo "Experimentation API - Comprehensive Demo"
echo "Base URL: $BASE_URL"
echo "=============================================="
echo ""

echo ">>> 1. Health Check"
curl -s "$BASE_URL/health" | python3 -m json.tool
echo ""

echo ">>> 2. Get JWT Token"
TOKEN_RESPONSE=$(curl -s -X POST "$BASE_URL/auth/token" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}')
echo "$TOKEN_RESPONSE" | python3 -m json.tool
TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")
AUTH_HEADER="Authorization: Bearer $TOKEN"
echo ""

echo "=============================================="
echo "EXPERIMENT 1: Button Color Test (Full Lifecycle)"
echo "=============================================="
echo ""

echo ">>> 3. Create Experiment 1 - Button Color Test"
EXP1_RESPONSE=$(curl -s -X POST "$BASE_URL/experiments" \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Button Color Test",
    "description": "Testing blue vs green CTA buttons",
    "variants": [
      {"name": "control", "description": "Blue button", "traffic_allocation": 50, "config": {"color": "blue"}},
      {"name": "treatment", "description": "Green button", "traffic_allocation": 50, "config": {"color": "green"}}
    ]
  }')
echo "$EXP1_RESPONSE" | python3 -m json.tool
EXP1_ID=$(echo "$EXP1_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
echo "Experiment 1 ID: $EXP1_ID (Status: draft)"
echo ""

echo ">>> 4. Start Experiment 1 (draft -> running)"
curl -s -X PATCH "$BASE_URL/experiments/$EXP1_ID" \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  -d '{"status": "running"}' | python3 -m json.tool
echo ""

echo ">>> 5. Assign Users to Experiment 1"
for i in {1..20}; do
  curl -s "$BASE_URL/experiments/$EXP1_ID/assignment/user-$(printf "%03d" $i)" \
    -H "$AUTH_HEADER" > /dev/null
done
echo "Assigned 20 users to Experiment 1"
echo ""

echo ">>> 6. Idempotency Test - Same user gets same variant"
echo "First call for user-001:"
curl -s "$BASE_URL/experiments/$EXP1_ID/assignment/user-001" -H "$AUTH_HEADER" | python3 -m json.tool
echo "Second call for user-001 (should return same variant, is_new_assignment=false):"
curl -s "$BASE_URL/experiments/$EXP1_ID/assignment/user-001" -H "$AUTH_HEADER" | python3 -m json.tool
echo ""

echo ">>> 7. Record Events for Experiment 1 Users"
for i in {1..15}; do
  curl -s -X POST "$BASE_URL/events" \
    -H "$AUTH_HEADER" \
    -H "Content-Type: application/json" \
    -d "{\"user_id\": \"user-$(printf "%03d" $i)\", \"event_type\": \"click\", \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"properties\": {\"page\": \"/home\"}}" > /dev/null
done
echo "Recorded 15 click events"

for i in {1..8}; do
  curl -s -X POST "$BASE_URL/events" \
    -H "$AUTH_HEADER" \
    -H "Content-Type: application/json" \
    -d "{\"user_id\": \"user-$(printf "%03d" $i)\", \"event_type\": \"purchase\", \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"properties\": {\"amount\": $((RANDOM % 100 + 10)).99}}" > /dev/null
done
echo "Recorded 8 purchase events"

for i in {1..5}; do
  curl -s -X POST "$BASE_URL/events" \
    -H "$AUTH_HEADER" \
    -H "Content-Type: application/json" \
    -d "{\"user_id\": \"user-$(printf "%03d" $i)\", \"event_type\": \"signup\", \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"properties\": {\"plan\": \"pro\"}}" > /dev/null
done
echo "Recorded 5 signup events"
echo ""

echo "=============================================="
echo "EXPERIMENT 2: Pricing Page Test (Paused)"
echo "=============================================="
echo ""

echo ">>> 8. Create Experiment 2 - Pricing Page Test"
EXP2_RESPONSE=$(curl -s -X POST "$BASE_URL/experiments" \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Pricing Page Layout",
    "description": "Testing horizontal vs vertical pricing cards",
    "variants": [
      {"name": "horizontal", "description": "Horizontal layout", "traffic_allocation": 33, "config": {"layout": "horizontal"}},
      {"name": "vertical", "description": "Vertical layout", "traffic_allocation": 33, "config": {"layout": "vertical"}},
      {"name": "grid", "description": "Grid layout", "traffic_allocation": 34, "config": {"layout": "grid"}}
    ]
  }')
echo "$EXP2_RESPONSE" | python3 -m json.tool
EXP2_ID=$(echo "$EXP2_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
echo "Experiment 2 ID: $EXP2_ID"
echo ""

echo ">>> 9. Start then Pause Experiment 2"
curl -s -X PATCH "$BASE_URL/experiments/$EXP2_ID" \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  -d '{"status": "running"}' > /dev/null
echo "Started Experiment 2"

for i in {21..30}; do
  curl -s "$BASE_URL/experiments/$EXP2_ID/assignment/user-$(printf "%03d" $i)" \
    -H "$AUTH_HEADER" > /dev/null
done
echo "Assigned 10 users"

curl -s -X PATCH "$BASE_URL/experiments/$EXP2_ID" \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  -d '{"status": "paused"}' | python3 -m json.tool
echo "Experiment 2 is now PAUSED"
echo ""

echo "=============================================="
echo "EXPERIMENT 3: Checkout Flow (Completed)"
echo "=============================================="
echo ""

echo ">>> 10. Create Experiment 3 - Checkout Flow"
EXP3_RESPONSE=$(curl -s -X POST "$BASE_URL/experiments" \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Checkout Flow Optimization",
    "description": "Single page vs multi-step checkout",
    "variants": [
      {"name": "single-page", "description": "All in one page", "traffic_allocation": 50, "config": {"steps": 1}},
      {"name": "multi-step", "description": "3-step wizard", "traffic_allocation": 50, "config": {"steps": 3}}
    ]
  }')
echo "$EXP3_RESPONSE" | python3 -m json.tool
EXP3_ID=$(echo "$EXP3_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
echo "Experiment 3 ID: $EXP3_ID"
echo ""

echo ">>> 11. Run and Complete Experiment 3"
curl -s -X PATCH "$BASE_URL/experiments/$EXP3_ID" \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  -d '{"status": "running"}' > /dev/null

for i in {31..50}; do
  curl -s "$BASE_URL/experiments/$EXP3_ID/assignment/user-$(printf "%03d" $i)" \
    -H "$AUTH_HEADER" > /dev/null
done
echo "Assigned 20 users"

for i in {31..45}; do
  curl -s -X POST "$BASE_URL/events" \
    -H "$AUTH_HEADER" \
    -H "Content-Type: application/json" \
    -d "{\"user_id\": \"user-$(printf "%03d" $i)\", \"event_type\": \"checkout_started\", \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"properties\": {}}" > /dev/null
done
echo "Recorded 15 checkout_started events"

for i in {31..40}; do
  curl -s -X POST "$BASE_URL/events" \
    -H "$AUTH_HEADER" \
    -H "Content-Type: application/json" \
    -d "{\"user_id\": \"user-$(printf "%03d" $i)\", \"event_type\": \"checkout_completed\", \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"properties\": {\"total\": $((RANDOM % 200 + 50)).99}}" > /dev/null
done
echo "Recorded 10 checkout_completed events"

curl -s -X PATCH "$BASE_URL/experiments/$EXP3_ID" \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  -d '{"status": "completed"}' | python3 -m json.tool
echo "Experiment 3 is now COMPLETED"
echo ""

echo "=============================================="
echo "EXPERIMENT 4: Draft Only (Not Started)"
echo "=============================================="
echo ""

echo ">>> 12. Create Experiment 4 - Feature Flag (Draft)"
EXP4_RESPONSE=$(curl -s -X POST "$BASE_URL/experiments" \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "New Dashboard Feature",
    "description": "Testing new analytics dashboard",
    "variants": [
      {"name": "old-dashboard", "description": "Current dashboard", "traffic_allocation": 80, "config": {"version": "v1"}},
      {"name": "new-dashboard", "description": "New dashboard", "traffic_allocation": 20, "config": {"version": "v2"}}
    ]
  }')
echo "$EXP4_RESPONSE" | python3 -m json.tool
EXP4_ID=$(echo "$EXP4_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
echo "Experiment 4 ID: $EXP4_ID (Status: draft - not started yet)"
echo ""

echo "=============================================="
echo "RESULTS & ANALYTICS"
echo "=============================================="
echo ""

echo ">>> 13. List All Experiments (Different Statuses)"
curl -s "$BASE_URL/experiments" \
  -H "$AUTH_HEADER" | python3 -m json.tool
echo ""

echo ">>> 14. Filter Experiments by Status"
echo "--- Running experiments:"
curl -s "$BASE_URL/experiments?status=running" \
  -H "$AUTH_HEADER" | python3 -m json.tool
echo ""

echo "--- Completed experiments:"
curl -s "$BASE_URL/experiments?status=completed" \
  -H "$AUTH_HEADER" | python3 -m json.tool
echo ""

echo ">>> 15. Get Results - Full Format (Experiment 1)"
curl -s "$BASE_URL/experiments/$EXP1_ID/results" \
  -H "$AUTH_HEADER" | python3 -m json.tool
echo ""

echo ">>> 16. Get Results - Summary Format (Experiment 1)"
curl -s "$BASE_URL/experiments/$EXP1_ID/results?format=summary" \
  -H "$AUTH_HEADER" | python3 -m json.tool
echo ""

echo ">>> 17. Get Results - Filter by Event Type (purchases only)"
curl -s "$BASE_URL/experiments/$EXP1_ID/results?event_types=purchase" \
  -H "$AUTH_HEADER" | python3 -m json.tool
echo ""

echo ">>> 18. Get Results - Multiple Event Types"
curl -s "$BASE_URL/experiments/$EXP1_ID/results?event_types=click,purchase" \
  -H "$AUTH_HEADER" | python3 -m json.tool
echo ""

echo ">>> 19. Get Results - With Time Series (Hourly)"
curl -s "$BASE_URL/experiments/$EXP1_ID/results?include_time_series=true&time_series_granularity=hour" \
  -H "$AUTH_HEADER" | python3 -m json.tool
echo ""

echo ">>> 20. Get Results for Completed Experiment 3"
curl -s "$BASE_URL/experiments/$EXP3_ID/results" \
  -H "$AUTH_HEADER" | python3 -m json.tool
echo ""

echo ">>> 21. Export Experiment Data"
curl -s "$BASE_URL/experiments/$EXP1_ID/results/export" \
  -H "$AUTH_HEADER" | python3 -m json.tool
echo ""

echo ">>> 22. Query All Events"
echo "--- All event types in system:"
curl -s "$BASE_URL/events/types" \
  -H "$AUTH_HEADER" | python3 -m json.tool
echo ""

echo "--- Recent events (limit 10):"
curl -s "$BASE_URL/events?limit=10" \
  -H "$AUTH_HEADER" | python3 -m json.tool
echo ""

echo "--- Events by type (purchase):"
curl -s "$BASE_URL/events?event_type=purchase&limit=5" \
  -H "$AUTH_HEADER" | python3 -m json.tool
echo ""

echo "--- Events by user:"
curl -s "$BASE_URL/events?user_id=user-001" \
  -H "$AUTH_HEADER" | python3 -m json.tool
echo ""

echo "=============================================="
echo "ERROR HANDLING"
echo "=============================================="
echo ""

echo ">>> 23. Try to assign user to draft experiment (should fail)"
curl -s "$BASE_URL/experiments/$EXP4_ID/assignment/user-999" \
  -H "$AUTH_HEADER" | python3 -m json.tool
echo ""

echo ">>> 24. Try to assign user to paused experiment (should fail)"
curl -s "$BASE_URL/experiments/$EXP2_ID/assignment/user-999" \
  -H "$AUTH_HEADER" | python3 -m json.tool
echo ""

echo ">>> 25. Authentication Errors"
echo "--- Missing token:"
curl -s -w "\nHTTP Status: %{http_code}\n" "$BASE_URL/experiments" 2>&1 | head -3
echo ""

echo "--- Invalid token:"
curl -s -w "\nHTTP Status: %{http_code}\n" "$BASE_URL/experiments" \
  -H "Authorization: Bearer invalid-token" 2>&1 | head -3
echo ""

echo "=============================================="
echo "SUMMARY"
echo "=============================================="
echo ""
echo "Created 4 experiments with different statuses:"
echo "  - Experiment 1 (ID: $EXP1_ID): RUNNING - Button Color Test"
echo "  - Experiment 2 (ID: $EXP2_ID): PAUSED - Pricing Page Layout"
echo "  - Experiment 3 (ID: $EXP3_ID): COMPLETED - Checkout Flow"
echo "  - Experiment 4 (ID: $EXP4_ID): DRAFT - New Dashboard Feature"
echo ""
echo "Total users assigned: 50"
echo "Total events recorded: ~53 (clicks, purchases, signups, checkouts)"
echo ""
echo "=============================================="
echo "Demo completed successfully!"
echo "=============================================="
