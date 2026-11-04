#!/usr/bin/env bash
# Write a verified `git bundle` of all refs to the backups folder (ADR 0004).
# Usage: tools/bundle.sh <label>
set -euo pipefail
label="${1:?label}"
root="$(git rev-parse --show-toplevel)"
dest="${UCP_BACKUP_DIR:-$(dirname "$root")/backups}"
mkdir -p "$dest"
sha="$(git -C "$root" rev-parse --short=12 HEAD)"
name="$(date +%Y%m%dT%H%M%S%z)-${label}-${sha}.bundle"
git -C "$root" bundle create "$dest/$name" --all
git -C "$root" bundle verify "$dest/$name" >/dev/null
(cd "$dest" && sha256sum "$name" > "$name.sha256" && sha256sum -c "$name.sha256" >/dev/null)
echo "$dest/$name $(cut -d' ' -f1 "$dest/$name.sha256")"
