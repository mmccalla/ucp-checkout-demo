#!/usr/bin/env bash
# M-01 readiness check (docs/M-01-procedure.md).
# Usage: tools/m01_ready.sh [LOG_FILE]
# It runs the gates, starts the loopback layout (MODE=demo) and leaves it running for M-01.
# Exit 0: ready for the full M-01 (release scope).
# Exit 2: ready for part A only (Google Pay sheet on /smoke/). The last line names what part B still needs.
# Exit 1: not ready. Do not hand over the desktop.
# Rebuilt 2026-10-24 after the box restart. Old commit 8f0a6c9 (lost). Section 3 adds the S2 Create check.
set -uo pipefail
cd "$(dirname "$0")/.."
LOG="${1:-.run/m01-readiness.log}"; mkdir -p "$(dirname "$LOG")" .run
exec > >(tee "$LOG") 2>&1
set -a; source deploy/ports.env; set +a
CA=.run/xdg-data/caddy/pki/authorities/local/root.crt
FAIL=0; PARTB=1; MISSING=""
ok()   { echo "PASS  $1"; }
bad()  { echo "FAIL  $1"; FAIL=1; }
info() { echo "INFO  $1"; }
check() { local name="$1"; shift; if "$@" >/dev/null 2>&1; then ok "$name"; else bad "$name"; fi; }

echo "# M-01 readiness  $(date '+%Y-%m-%d %H:%M:%S %Z')"
SHA=$(git rev-parse HEAD); echo "commit $SHA"
if [ -z "$(git status --porcelain)" ]; then ok "working tree is clean (the evidence record can name one commit)"; else bad "working tree has changes that are not committed"; fi

echo "## 1. Gates G1 to G4 (tools/gates/run_all.sh)"
export UCP_SCHEMA_BIN="${UCP_SCHEMA_BIN:-$(pwd)/../tools/bin/ucp-schema}"
if tools/gates/run_all.sh .run/m01-gates > .run/m01-gates.log 2>&1; then ok "gates (summary .run/m01-gates/summary.md)"; else bad "gates (see .run/m01-gates.log)"; fi
grep -E '^\| (G[1-8]|M1)' .run/m01-gates/summary.md 2>/dev/null | sed 's/^/      /'

echo "## 2. Loopback layout (MODE=demo)"
tools/run_local.sh stop >/dev/null 2>&1
if MODE=demo tools/run_local.sh start >/dev/null 2>&1; then ok "services started: MODE=demo tools/run_local.sh start"; else bad "services did not start"; fi
NONLOOP=$(ss -ltnH 2>/dev/null | awk '{print $4}' | grep -E ":(${PLATFORM_TLS_PORT}|${BUSINESS_TLS_PORT}|${PLATFORM_APP_PORT}|${BUSINESS_APP_PORT}|${PSP_MOCK_APP_PORT}|${CADDY_ADMIN_PORT}|16686|16685|4318)$" | grep -vE '^(127\.0\.0\.1|\[::1\]):' || true)
if [ -z "$NONLOOP" ]; then ok "all demo listeners use 127.0.0.1 (DM-26)"; else bad "listener not on loopback: $NONLOOP"; fi
check "TLS 1.3 to https://localhost:${PLATFORM_TLS_PORT}" curl -fsS --cacert "$CA" --tlsv1.3 -o /dev/null "https://localhost:${PLATFORM_TLS_PORT}/livez"
if curl -sS --cacert "$CA" --tlsv1.2 --tls-max 1.2 -o /dev/null "https://localhost:${PLATFORM_TLS_PORT}/livez" >/dev/null 2>&1; then bad "TLS 1.2 is accepted (AC-121)"; else ok "TLS 1.2 is refused (AC-121)"; fi

echo "## 3. Profiles, the smoke page and the S2 checkout API"
BP=$(curl -fsS --cacert "$CA" "https://localhost:${BUSINESS_TLS_PORT}/.well-known/ucp" 2>/dev/null)
if printf '%s' "$BP" | python3 -c 'import json,sys; u=json.load(sys.stdin)["ucp"]; h=u["payment_handlers"]; assert u["version"]=="2026-04-08"; assert h["com.google.pay"][0]["config"]["environment"]=="TEST"; assert not any("mock" in k for k in h)'; then ok "Business profile: 2026-04-08, com.google.pay TEST, no mock handler"; else bad "Business profile"; fi
if curl -fsS --cacert "$CA" "https://localhost:${PLATFORM_TLS_PORT}/api/discovery" 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["ok"] and d["transport"]=="REST"'; then ok "Platform discovery ok, transport REST"; else bad "Platform discovery"; fi
CODE=$(curl -sS --cacert "$CA" -o /dev/null -w '%{http_code}' "https://localhost:${PLATFORM_TLS_PORT}/smoke/" 2>/dev/null)
if [ "$CODE" = 200 ]; then ok "smoke page https://localhost:${PLATFORM_TLS_PORT}/smoke/ (200)"; else bad "smoke page ($CODE)"; fi
if curl -fsS --cacert "$CA" "https://localhost:${PLATFORM_TLS_PORT}/smoke/handler-config.json" 2>/dev/null | python3 -c 'import sys; t=sys.stdin.read(); assert "PRODUCTION" not in t and t.count("\"TEST\"")>=1'; then ok "smoke handler config is TEST, no PRODUCTION (AC-26)"; else bad "smoke handler config"; fi
if curl -fsS --cacert "$CA" -H 'Content-Type: application/json' -d '{"line_items":[{"item":{"id":"demo_tshirt"},"quantity":1}],"fulfillment":{"methods":[{"type":"shipping"}]}}' "https://localhost:${PLATFORM_TLS_PORT}/api/checkout" 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["http_status"]==201, d'; then ok "S2 signed Create through the Platform API: Business HTTP 201"; else bad "S2 signed Create through the Platform API"; fi
if [ -w .run ]; then ok "event log path .run/smoke-events.jsonl is writable"; else bad "event log path is not writable"; fi

echo "## 4. Google and the desktop browser"
check "pay.js is reachable (https://pay.google.com/gp/p/js/pay.js)" curl -fsS -o /dev/null https://pay.google.com/gp/p/js/pay.js
check "test card suite page is reachable" curl -fsSL -o /dev/null https://developers.google.com/pay/api/web/guides/resources/test-card-suite
if [ -x /usr/bin/google-chrome ]; then ok "Google Chrome: $(/usr/bin/google-chrome --version 2>/dev/null)"; else bad "Google Chrome is not installed"; fi
info "the box desktop Chrome bypasses its proxy for localhost and 127.0.0.1. It does not trust the Caddy CA. Accept the warning (procedure, precondition 3)."

echo "## 5. Release scope (part B: checkout to completed and an order ID)"
if [ -f platform/web/checkout/index.html ]; then ok "Platform checkout page (S3) exists"; else info "Platform checkout page (S3) is not built yet"; PARTB=0; MISSING="$MISSING S3"; fi
# S4: the Business sends the Google Pay token to psp-mock (127.0.0.1). The page shows the order.
if curl -fsS "http://${LOOPBACK_HOST}:${PSP_MOCK_APP_PORT}/readyz" 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("outcome")=="approve", d'; then ok "psp-mock is ready on ${LOOPBACK_HOST}:${PSP_MOCK_APP_PORT}, next outcome approve (S4)"; else info "psp-mock is not ready, or its next outcome is not approve (S4)"; PARTB=0; MISSING="$MISSING psp-mock"; fi
if grep -qs 'function confirmed' platform/web/checkout/app.js && grep -qs 'PaymentFailedError' business/src/ucp_sample_server/exceptions.py; then ok "Complete, order confirmation and T-105 decline screen exist (S4)"; else info "Complete with psp-mock (S4) is not built yet"; PARTB=0; MISSING="$MISSING S4"; fi
info "this script sends no Complete. A test Complete would add to the daily spend ledger (AC-24)."
echo "## Result"
if [ "$FAIL" = 1 ]; then echo "NOT READY. Fix each FAIL line. Do not hand over the desktop."; exit 1; fi
if [ "$PARTB" = 0 ]; then echo "READY FOR PART A ONLY (sheet on /smoke/) at commit $SHA. Part B still needs:${MISSING}."; exit 2; fi
echo "READY FOR M-01 PARTS A AND B at commit $SHA. The services run on 127.0.0.1 (MODE=demo). Part B ends on \"Order confirmed\" with an order ID."; exit 0