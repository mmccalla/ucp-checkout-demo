#!/usr/bin/env bash
# Check that the vendored samples copy = samples e7c9c12 (git-tracked files) + tools/vendor/patch_sample.py.
# Usage: tools/vendor/verify_vendored.sh [SAMPLES_CLONE]  (default ../src/gh-samples)
set -euo pipefail
cd "$(dirname "$0")/../.."
SRC="${1:-../src/gh-samples}"; C=e7c9c124864108cbb35e5102beeac9cbef80a154
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir -p "$T/tools/vendor" "$T/business/src/ucp_sample_server"
cp tools/vendor/patch_sample.py "$T/tools/vendor/"
git -C "$SRC" archive "$C" rest/python/server | tar -x -C "$T"
cp -a "$T/rest/python/server/." "$T/business/src/ucp_sample_server/"
python3 "$T/tools/vendor/patch_sample.py" >/dev/null
if diff -r -x __pycache__ "$T/business/src/ucp_sample_server" business/src/ucp_sample_server; then
  echo "IDENTICAL: vendored copy = samples $C + patch_sample.py"
else
  echo "DIFFERENT"; exit 1
fi
