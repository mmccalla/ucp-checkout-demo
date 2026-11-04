#!/usr/bin/env bash
# Rebuild business/src/ucp_sample_server from samples e7c9c12 + tools/vendor/patch_sample.py.
# Usage: tools/vendor/regen_vendored.sh [SAMPLES_CLONE]  (default ../src/gh-samples)
set -euo pipefail
cd "$(dirname "$0")/../.."
SRC="${1:-../src/gh-samples}"; C=e7c9c124864108cbb35e5102beeac9cbef80a154
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir -p "$T/tools/vendor" "$T/business/src/ucp_sample_server"
cp tools/vendor/patch_sample.py "$T/tools/vendor/"
git -C "$SRC" archive "$C" rest/python/server | tar -x -C "$T"
cp -a "$T/rest/python/server/." "$T/business/src/ucp_sample_server/"
python3 "$T/tools/vendor/patch_sample.py"
find business/src/ucp_sample_server -mindepth 1 -not -path '*/__pycache__*' -delete 2>/dev/null || true
cp -a "$T/business/src/ucp_sample_server/." business/src/ucp_sample_server/
