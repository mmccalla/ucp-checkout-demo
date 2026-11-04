#!/usr/bin/env bash
# Download the pinned Caddy release (pins/PINS.toml [caddy]) and check its sha512. Linux amd64.
# Usage: tools/get_caddy.sh [DIR]   (default: ../tools/caddy-bin; run_local.sh looks there)
set -euo pipefail
cd "$(dirname "$0")/.."
DIR="${1:-$(pwd)/../tools/caddy-bin}"
pin() { python3 -c "import tomllib; print(tomllib.load(open('pins/PINS.toml','rb'))['caddy']['$1'])"; }
VER=$(pin version); ASSET=$(pin asset); SHA=$(pin sha512)
URL="https://github.com/caddyserver/caddy/releases/download/v$VER/$ASSET"
mkdir -p "$DIR"; T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
curl -fsSL -o "$T/$ASSET" "$URL"
[ "$(sha512sum "$T/$ASSET" | cut -d' ' -f1)" = "$SHA" ] || { echo "sha512 differs from the pin: not installed"; exit 1; }
tar -xzf "$T/$ASSET" -C "$T" caddy
install -m 0755 "$T/caddy" "$DIR/caddy"
echo "installed $("$DIR/caddy" version | cut -d' ' -f1) in $DIR"
