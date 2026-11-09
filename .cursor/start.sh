#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

export CADDY="${ROOT}/.tools/caddy-bin/caddy"
export UCP_SCHEMA_BIN="${ROOT}/.tools/ucp-schema/bin/ucp-schema"
export UCP_TRACING=0

if [ -f .run/platform.pid ] || [ -f .run/caddy.pid ]; then
  tools/run_local.sh stop || true
  sleep 0.5
fi

tools/run_local.sh start
