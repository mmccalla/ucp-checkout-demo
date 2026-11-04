#!/usr/bin/env bash
# G8 (AC-117) and the readiness check (AC-58) on a clean copy of HEAD.
# Usage: tools/latency/run_g8.sh REPORT_DIR
# It does not touch the running demo (`.run/` of the working tree stays as it is):
#  - it exports HEAD with `git archive` into a temporary directory,
#  - it starts the loopback layout there, in a private network namespace (loopback only),
#    so the fixed ports (8443, 9443, 8101, 8201, 8301, 2019) do not clash with the demo,
#  - it measures readiness, runs 100 calls for each operation, and stops the layout.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$(mkdir -p "${1:?report dir}" && cd "$1" && pwd)"
CADDY="${CADDY:-$ROOT/../tools/caddy-bin/caddy}"
[ -x "$CADDY" ] || { echo "caddy not found: $CADDY"; exit 2; }
if [ -n "$(git -C "$ROOT" status --porcelain)" ]; then echo "tree is not clean: commit first"; exit 2; fi
WORK="$(mktemp -d /tmp/g8-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT
git -C "$ROOT" archive HEAD | tar -x -C "$WORK"
ln -s "$ROOT/.venv" "$WORK/.venv"
export G8_GIT_HEAD="$(git -C "$ROOT" rev-parse HEAD)" G8_WORK="$WORK" G8_OUT="$OUT" CADDY
unshare --map-root-user --net bash -c '
  set -uo pipefail
  ip link set lo up
  cd "$G8_WORK"
  export UCP_TRACING=0 XDG_DATA_HOME="$G8_WORK/.run/xdg-data" XDG_CONFIG_HOME="$G8_WORK/.run/xdg-config"
  export PYTHONPATH="$G8_WORK/platform/backend/src:$G8_WORK/business/src:$G8_WORK/psp-mock/src:$G8_WORK/libs:$G8_WORK/tools/latency"
  START_NS=$(python3 -c "import time;print(time.monotonic_ns())")
  tools/run_local.sh start > "$G8_OUT/start.log" 2>&1
  PY="$G8_WORK/.venv/bin/python"
  "$PY" tools/latency/g8_driver.py ready --start-ns "$START_NS" --log "$G8_OUT/readiness.log"; r1=$?
  rc=1
  if [ $r1 -eq 0 ]; then "$PY" tools/latency/g8_driver.py run --report-dir "$G8_OUT" > "$G8_OUT/g8-run.log" 2>&1; rc=$?; tail -n 12 "$G8_OUT/g8-run.log"; fi
  tools/run_local.sh stop > /dev/null 2>&1; sleep 1
  mkdir -p "$G8_OUT/service-logs"; cp "$G8_WORK"/.run/*.log "$G8_OUT/service-logs/" 2>/dev/null || true
  exit $rc
'
