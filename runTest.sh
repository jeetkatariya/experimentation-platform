#!/bin/bash

set -e

# Priority: 1. Command line arg, 2. API_URL env var, 3. Default localhost
BASE_URL="${1:-${API_URL:-http://localhost:8000}}"

echo "========================================"
echo "🛒 E-COMMERCE A/B TESTING DEMO"
echo "Real-world experiments with meaningful data"
echo "========================================"
echo ""

echo ">>> Getting JWT Token..."
TOKEN=$(curl -s -X POST "$BASE_URL/auth/token" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
AUTH="Authorization: Bearer $TOKEN"
echo "Token obtained!"
echo ""

echo "========================================"
echo "EXPERIMENT 1: Dark Mode Beta (Pilot Test)"
echo "Small rollout to 20 beta testers"
echo "========================================"

EXP1=$(curl -s -X POST "$BASE_URL/experiments" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Dark Mode Beta Test",
    "description": "Testing dark mode with beta users before wider rollout. Measuring if dark mode increases session duration.",
    "variants": [
      {"name": "light-mode", "description": "Current light theme", "traffic_allocation": 50, "config": {"theme": "light", "contrast": "normal"}},
      {"name": "dark-mode", "description": "New dark theme", "traffic_allocation": 50, "config": {"theme": "dark", "contrast": "high"}}
    ]
  }')
EXP1_ID=$(echo "$EXP1" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "Created: Dark Mode Beta Test (ID: $EXP1_ID)"

curl -s -X PATCH "$BASE_URL/experiments/$EXP1_ID" -H "$AUTH" -H "Content-Type: application/json" -d '{"status": "running"}' > /dev/null

echo "Enrolling 20 beta testers..."
for i in $(seq 1 20); do
  ASSIGN=$(curl -s "$BASE_URL/experiments/$EXP1_ID/assignment/beta-user-$i" -H "$AUTH")
  VARIANT=$(echo "$ASSIGN" | python3 -c "import sys,json; print(json.load(sys.stdin)['variant_name'])")
  
  if [ "$VARIANT" = "light-mode" ]; then
    # Light mode: 50% have extended sessions
    if [ $((RANDOM % 100)) -lt 50 ]; then
      curl -s -X POST "$BASE_URL/events" -H "$AUTH" -H "Content-Type: application/json" \
        -d "{\"user_id\": \"beta-user-$i\", \"event_type\": \"extended_session\", \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"properties\": {\"duration_minutes\": $((RANDOM % 30 + 10))}}" > /dev/null
    fi
  else
    # Dark mode: 75% have extended sessions (users love it!)
    if [ $((RANDOM % 100)) -lt 75 ]; then
      curl -s -X POST "$BASE_URL/events" -H "$AUTH" -H "Content-Type: application/json" \
        -d "{\"user_id\": \"beta-user-$i\", \"event_type\": \"extended_session\", \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"properties\": {\"duration_minutes\": $((RANDOM % 45 + 20))}}" > /dev/null
    fi
  fi
done
echo "Beta test complete - awaiting more data for confidence"

curl -s -X PATCH "$BASE_URL/experiments/$EXP1_ID" -H "$AUTH" -H "Content-Type: application/json" -d '{"status": "completed"}' > /dev/null
echo "Experiment 1 COMPLETED (Status: Needs more users for confidence)"
echo ""

echo "========================================"
echo "EXPERIMENT 2: Checkout Button Redesign"
echo "Testing new CTA button on 250 users"
echo "========================================"

EXP2=$(curl -s -X POST "$BASE_URL/experiments" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Checkout Button Redesign",
    "description": "Testing if a larger, animated checkout button increases purchase completion rate.",
    "variants": [
      {"name": "standard-button", "description": "Current small green button", "traffic_allocation": 50, "config": {"size": "small", "color": "#28a745", "animation": false}},
      {"name": "animated-button", "description": "Large pulsing orange button", "traffic_allocation": 50, "config": {"size": "large", "color": "#ff6600", "animation": true, "pulse_speed": "slow"}}
    ]
  }')
EXP2_ID=$(echo "$EXP2" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "Created: Checkout Button Redesign (ID: $EXP2_ID)"

curl -s -X PATCH "$BASE_URL/experiments/$EXP2_ID" -H "$AUTH" -H "Content-Type: application/json" -d '{"status": "running"}' > /dev/null

echo "Processing 250 checkout sessions..."
STANDARD_COUNT=0
ANIMATED_COUNT=0
STANDARD_PURCHASES=0
ANIMATED_PURCHASES=0

for i in $(seq 1 250); do
  ASSIGN=$(curl -s "$BASE_URL/experiments/$EXP2_ID/assignment/shopper-$i" -H "$AUTH")
  VARIANT=$(echo "$ASSIGN" | python3 -c "import sys,json; print(json.load(sys.stdin)['variant_name'])")
  
  # Only record purchase_completed events (the metric we care about)
  # No add_to_cart to avoid diluting the conversion rate
  
  if [ "$VARIANT" = "standard-button" ]; then
    STANDARD_COUNT=$((STANDARD_COUNT + 1))
    # Standard button: 35% complete purchase
    if [ $((RANDOM % 100)) -lt 35 ]; then
      curl -s -X POST "$BASE_URL/events" -H "$AUTH" -H "Content-Type: application/json" \
        -d "{\"user_id\": \"shopper-$i\", \"event_type\": \"purchase_completed\", \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"properties\": {\"order_total\": $((RANDOM % 200 + 25)).99, \"payment_method\": \"card\"}}" > /dev/null
      STANDARD_PURCHASES=$((STANDARD_PURCHASES + 1))
    fi
  else
    ANIMATED_COUNT=$((ANIMATED_COUNT + 1))
    # Animated button: 60% complete purchase (71% lift over 35%!)
    if [ $((RANDOM % 100)) -lt 60 ]; then
      curl -s -X POST "$BASE_URL/events" -H "$AUTH" -H "Content-Type: application/json" \
        -d "{\"user_id\": \"shopper-$i\", \"event_type\": \"purchase_completed\", \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"properties\": {\"order_total\": $((RANDOM % 200 + 25)).99, \"payment_method\": \"card\"}}" > /dev/null
      ANIMATED_PURCHASES=$((ANIMATED_PURCHASES + 1))
    fi
  fi
  
  if [ $((i % 50)) -eq 0 ]; then
    echo "  Processed $i shoppers..."
  fi
done
echo "Standard button: $STANDARD_COUNT users, $STANDARD_PURCHASES purchases"
echo "Animated button: $ANIMATED_COUNT users, $ANIMATED_PURCHASES purchases"

curl -s -X PATCH "$BASE_URL/experiments/$EXP2_ID" -H "$AUTH" -H "Content-Type: application/json" -d '{"status": "completed"}' > /dev/null
echo "Experiment 2 COMPLETED"
echo ""

echo "========================================"
echo "EXPERIMENT 3: Free Shipping Threshold"
echo "Large scale test with 1200 customers"
echo "========================================"

EXP3=$(curl -s -X POST "$BASE_URL/experiments" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Free Shipping Threshold Test",
    "description": "Testing if lowering free shipping threshold from $75 to $50 increases order completion and average order value.",
    "variants": [
      {"name": "threshold-75", "description": "Current: Free shipping at $75+", "traffic_allocation": 50, "config": {"free_shipping_min": 75, "shipping_cost": 7.99}},
      {"name": "threshold-50", "description": "Test: Free shipping at $50+", "traffic_allocation": 50, "config": {"free_shipping_min": 50, "shipping_cost": 7.99}}
    ]
  }')
EXP3_ID=$(echo "$EXP3" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "Created: Free Shipping Threshold Test (ID: $EXP3_ID)"

curl -s -X PATCH "$BASE_URL/experiments/$EXP3_ID" -H "$AUTH" -H "Content-Type: application/json" -d '{"status": "running"}' > /dev/null

echo "Processing 1200 customer sessions (this takes ~4 minutes)..."
THRESHOLD75_ORDERS=0
THRESHOLD50_ORDERS=0

for i in $(seq 1 1200); do
  ASSIGN=$(curl -s "$BASE_URL/experiments/$EXP3_ID/assignment/customer-$i" -H "$AUTH")
  VARIANT=$(echo "$ASSIGN" | python3 -c "import sys,json; print(json.load(sys.stdin)['variant_name'])")
  
  if [ "$VARIANT" = "threshold-75" ]; then
    # $75 threshold: 45% complete order
    if [ $((RANDOM % 100)) -lt 45 ]; then
      ORDER_VALUE=$((RANDOM % 100 + 60))
      curl -s -X POST "$BASE_URL/events" -H "$AUTH" -H "Content-Type: application/json" \
        -d "{\"user_id\": \"customer-$i\", \"event_type\": \"order_placed\", \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"properties\": {\"order_total\": $ORDER_VALUE.99, \"free_shipping\": $([ $ORDER_VALUE -ge 75 ] && echo true || echo false), \"item_count\": $((RANDOM % 4 + 1))}}" > /dev/null
      THRESHOLD75_ORDERS=$((THRESHOLD75_ORDERS + 1))
    fi
  else
    # $50 threshold: 65% complete order (44% lift - lower barrier works!)
    if [ $((RANDOM % 100)) -lt 65 ]; then
      ORDER_VALUE=$((RANDOM % 80 + 45))
      curl -s -X POST "$BASE_URL/events" -H "$AUTH" -H "Content-Type: application/json" \
        -d "{\"user_id\": \"customer-$i\", \"event_type\": \"order_placed\", \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"properties\": {\"order_total\": $ORDER_VALUE.99, \"free_shipping\": $([ $ORDER_VALUE -ge 50 ] && echo true || echo false), \"item_count\": $((RANDOM % 4 + 1))}}" > /dev/null
      THRESHOLD50_ORDERS=$((THRESHOLD50_ORDERS + 1))
    fi
  fi
  
  if [ $((i % 200)) -eq 0 ]; then
    echo "  Processed $i customers..."
  fi
done
echo "\$75 threshold orders: $THRESHOLD75_ORDERS"
echo "\$50 threshold orders: $THRESHOLD50_ORDERS"

curl -s -X PATCH "$BASE_URL/experiments/$EXP3_ID" -H "$AUTH" -H "Content-Type: application/json" -d '{"status": "completed"}' > /dev/null
echo "Experiment 3 COMPLETED"
echo ""

echo "========================================"
echo "📊 RESULTS SUMMARY"
echo "========================================"
echo ""

echo ">>> EXPERIMENT 1: Dark Mode Beta Test"
echo "    (Small pilot - LOW confidence expected)"
curl -s "$BASE_URL/experiments/$EXP1_ID/results" -H "$AUTH" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f\"    Status: {d['experiment_status'].upper()}\")
print(f\"    Users: {d['summary']['total_assignments']}\")
print(f\"    Confidence: {d['summary']['confidence_level'].upper()}\")
print(f\"    Winner: {d['summary']['leading_variant'] or 'No clear winner'}\")
for v in d['variant_metrics']:
    print(f\"    → {v['variant_name']}: {v['conversion_rate']}% extended sessions\")
"
echo ""

echo ">>> EXPERIMENT 2: Checkout Button Redesign"
echo "    (Medium test - MEDIUM confidence expected)"
curl -s "$BASE_URL/experiments/$EXP2_ID/results" -H "$AUTH" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f\"    Status: {d['experiment_status'].upper()}\")
print(f\"    Users: {d['summary']['total_assignments']}\")
print(f\"    Confidence: {d['summary']['confidence_level'].upper()}\")
print(f\"    Winner: {d['summary']['leading_variant'] or 'No clear winner'}\")
for v in d['variant_metrics']:
    print(f\"    → {v['variant_name']}: {v['conversion_rate']}% purchase rate\")
"
echo ""

echo ">>> EXPERIMENT 3: Free Shipping Threshold"
echo "    (Large test - HIGH confidence expected)"
curl -s "$BASE_URL/experiments/$EXP3_ID/results" -H "$AUTH" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f\"    Status: {d['experiment_status'].upper()}\")
print(f\"    Users: {d['summary']['total_assignments']}\")
print(f\"    Confidence: {d['summary']['confidence_level'].upper()}\")
print(f\"    Winner: {d['summary']['leading_variant'] or 'No clear winner'}\")
for v in d['variant_metrics']:
    print(f\"    → {v['variant_name']}: {v['conversion_rate']}% order rate\")
"
echo ""

echo "========================================"
echo "📏 CONFIDENCE LEVEL THRESHOLDS"
echo "========================================"
echo ""
echo "  ┌─────────────┬──────────────────┬─────────────┐"
echo "  │ Confidence  │ Min Users/Variant│ Min Lift    │"
echo "  ├─────────────┼──────────────────┼─────────────┤"
echo "  │ LOW         │ < 30             │ Any         │"
echo "  │ MEDIUM      │ 100+             │ 20%+        │"
echo "  │ HIGH        │ 500+             │ 15%+        │"
echo "  │ SIGNIFICANT │ 1000+            │ 10%+        │"
echo "  └─────────────┴──────────────────┴─────────────┘"
echo ""
echo "  Lift = (Treatment Rate - Control Rate) / Control Rate"
echo ""

echo "========================================"
echo "💡 BUSINESS INSIGHTS"
echo "========================================"
echo ""
echo "1. DARK MODE (Low Confidence)"
echo "   → Promising results but need 100+ users to be confident"
echo "   → Recommendation: Expand beta before full rollout"
echo ""
echo "2. CHECKOUT BUTTON (Medium Confidence)"
echo "   → Animated button shows ~60% lift in purchases!"
echo "   → Recommendation: Consider rolling out to 50% of traffic"
echo ""
echo "3. FREE SHIPPING (High Confidence)"
echo "   → Lower threshold significantly increases orders"
echo "   → Recommendation: Roll out \$50 threshold company-wide"
echo ""
echo "========================================"
echo "Demo completed!"
echo "========================================"
