#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq pkg-config libssl-dev

if ! command -v uv >/dev/null 2>&1; then
  curl -fsSL https://astral.sh/uv/install.sh | sh
  sudo ln -sf "${HOME}/.local/bin/uv" /usr/local/bin/uv
fi

uv python install 3.12.16
uv sync --locked

TOOLS="${ROOT}/.tools"
SCHEMA_BIN="${TOOLS}/ucp-schema/bin/ucp-schema"
if [ ! -x "$SCHEMA_BIN" ] || [ "$("$SCHEMA_BIN" --version 2>/dev/null || true)" != "ucp-schema 1.4.1" ]; then
  cargo install --locked --git https://github.com/Universal-Commerce-Protocol/ucp-schema \
    --rev 6dd2a613d38828c97dca723bdb9ccfc79b2a7e80 --root "${TOOLS}/ucp-schema"
fi

tools/get_caddy.sh "${TOOLS}/caddy-bin"

uv run --no-sync playwright install chromium

echo "install ok"
