#!/usr/bin/env bash
# Run the official Jaeger 2.22.0 release binary (T-106, ADR 0013). All listeners bind to 127.0.0.1 (DM-26).
# Usage: tools/jaeger.sh verify|start|stop
# JAEGER_DIR holds the archive, the .asc file and the unpacked binary (default ../tools/jaeger).
set -euo pipefail
cd "$(dirname "$0")/.."
JAEGER_DIR="${JAEGER_DIR:-$(pwd)/../tools/jaeger}"
RUN=.run; mkdir -p "$RUN"
pin() { python3 -c "import tomllib,sys; print(tomllib.load(open('pins/PINS.toml','rb'))['jaeger']['$1'])"; }
ASSET=$(pin asset); BIN="$JAEGER_DIR/${ASSET%.tar.gz}/jaeger"
check_binary() {
  [ "$(sha256sum "$BIN" | cut -d' ' -f1)" = "$(pin sha256_binary)" ] || { echo "binary sha256 differs from the pin"; exit 1; }
}
case "${1:-start}" in
  verify)  # the sha256 of the archive and the gpg signature, in a new empty keyring
    [ "$(sha256sum "$JAEGER_DIR/$ASSET" | cut -d' ' -f1)" = "$(pin sha256_archive)" ] || { echo "archive sha256 differs from the pin"; exit 1; }
    GNUPGHOME=$(mktemp -d); export GNUPGHOME; chmod 700 "$GNUPGHOME"
    gpg --batch --import pins/jaeger-signing-key.asc 2>/dev/null
    gpg --batch --fingerprint "$(pin signing_key_fingerprint)" >/dev/null
    gpg --batch --verify "$JAEGER_DIR/$ASSET.asc" "$JAEGER_DIR/$ASSET" 2>&1 | tee "$RUN/jaeger-gpg-verify.txt"
    grep -q "Good signature" "$RUN/jaeger-gpg-verify.txt" && grep -q "$(pin signing_key_fingerprint)" "$RUN/jaeger-gpg-verify.txt"
    check_binary; echo "verified" ;;
  start)   # the binary with no config runs the all-in-one role. Two --set flags move the query listeners to loopback.
    check_binary
    nohup "$BIN" \
      --set=extensions.jaeger_query.http.endpoint=127.0.0.1:"${JAEGER_UI_PORT:-16686}" \
      --set=extensions.jaeger_query.grpc.endpoint=127.0.0.1:16685 > "$RUN/jaeger.log" 2>&1 & echo $! > "$RUN/jaeger.pid"
    echo started ;;
  stop)
    [ -f "$RUN/jaeger.pid" ] && kill "$(cat "$RUN/jaeger.pid")" 2>/dev/null || true; rm -f "$RUN/jaeger.pid"; echo stopped ;;
esac
