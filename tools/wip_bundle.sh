#!/usr/bin/env bash
# Save the working tree as a commit on wip/<name> and write a verified bundle (ADR 0004).
# It does not change HEAD, the index or the working tree. Do not push wip/ branches.
# Usage: tools/wip_bundle.sh <name>
set -euo pipefail
name="${1:?name}"
root="$(git rev-parse --show-toplevel)"
idx="$(mktemp)"
trap 'rm -f "$idx"' EXIT
export GIT_INDEX_FILE="$idx"
git -C "$root" read-tree HEAD
git -C "$root" add -A
tree="$(git -C "$root" write-tree)"
commit="$(git -C "$root" commit-tree "$tree" -p HEAD -m "wip: $name (local only, not pushed)")"
git -C "$root" update-ref "refs/heads/wip/$name" "$commit"
unset GIT_INDEX_FILE
echo "wip/$name -> $commit"
"$root/tools/bundle.sh" "wip-$name"
