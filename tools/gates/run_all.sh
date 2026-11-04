#!/usr/bin/env bash
# Run the gates of the current slice, then the summary. Usage: tools/gates/run_all.sh [REPORT_DIR]
set -uo pipefail
cd "$(dirname "$0")/../.."
OUT="${1:-.run/gates}"; mkdir -p "$OUT"; rm -f "$OUT"/G*.json "$OUT"/G*.log "$OUT"/summary.md
SLICE=$(uv run --no-sync python -c "import tomllib;print(tomllib.load(open('tools/gates/gates.toml','rb'))['current_slice'])")
GATES=$(uv run --no-sync python -c "import tomllib;c=tomllib.load(open('tools/gates/gates.toml','rb'));print(' '.join(c['slices'][c['current_slice']]))")
echo "slice $SLICE gates $GATES"
for g in $GATES; do
  s="tools/gates/$(echo "$g" | tr 'G' 'g').py"
  uv run --no-sync python "$s" --report "$OUT/$g.json" 2>&1 | tee "$OUT/$g.log"
done
uv run --no-sync python tools/gates/summary.py "$OUT"
