#!/usr/bin/env bash
# Voice gate smoke test — runs against local API (PORT 8000 by default).
# Usage: ./scripts/voice-gate-smoke.sh [BASE_URL] [TOKEN]
set -euo pipefail
BASE="${1:-http://localhost:8000}"
TOKEN="${2:-}"
PASS=0
FAIL=0

_check() {
  local name="$1" status="$2" expected="$3"
  if [ "$status" -eq "$expected" ]; then
    echo "  ✓ $name"
    PASS=$((PASS+1))
  else
    echo "  ✗ $name (got $status, want $expected)"
    FAIL=$((FAIL+1))
  fi
}

echo "=== AiPal Voice Gate Smoke Tests ==="
echo "Base: $BASE"
echo ""

# Gate-check: health endpoint
S=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/health")
_check "GET /health → 200" "$S" 200

if [ -n "$TOKEN" ]; then
  # Gate 1: text turn returns a reply (conversation loop works)
  S=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/turn/text" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d '{"text":"hello","session_id":"smoke-gate1"}')
  _check "Gate 1: POST /turn/text → 200" "$S" 200

  # Gate 3: greeting endpoint returns text
  S=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/turn/greeting" \
    -H "Authorization: Bearer $TOKEN")
  _check "Gate 3: GET /turn/greeting → 200" "$S" 200

  # Gate 7: verify Today view endpoint works (task nudge path)
  S=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/today" \
    -H "Authorization: Bearer $TOKEN")
  _check "Gate 7: GET /today → 200" "$S" 200
else
  echo "  (skipping authenticated gates — no TOKEN provided)"
  echo "  Usage: $0 [BASE_URL] TOKEN"
fi

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
