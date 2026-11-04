#!/usr/bin/env bash
# Start the loopback layout (DM-26): Platform, Business, mock PSP (S2), Caddy TLS 1.3 proxy.
# Usage: tools/run_local.sh start|stop
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source deploy/ports.env; set +a
RUN=.run; mkdir -p "$RUN"
CADDY="${CADDY:-$(pwd)/../tools/caddy-bin/caddy}"
export XDG_DATA_HOME="$(pwd)/$RUN/xdg-data" XDG_CONFIG_HOME="$(pwd)/$RUN/xdg-config"
case "${1:-start}" in
  start)
    # Traces (AC-56): if Jaeger answers on loopback, the services send spans to its OTLP/HTTP port.
    # The telemetry module accepts a loopback endpoint only. Set UCP_TRACING=0 to turn this off.
    if [ "${UCP_TRACING:-auto}" != "0" ] && curl -fs "http://127.0.0.1:$JAEGER_UI_PORT/api/v3/services" >/dev/null 2>&1; then
      export OTEL_EXPORTER_OTLP_ENDPOINT="http://127.0.0.1:$OTLP_HTTP_PORT"
      echo "tracing on: $OTEL_EXPORTER_OTLP_ENDPOINT"
    fi
    PYTHONPATH=platform/backend/src:libs nohup uv run --no-sync uvicorn platform_app.main:app \
      --host "$LOOPBACK_HOST" --port "$PLATFORM_APP_PORT" > "$RUN/platform.log" 2>&1 & echo $! > "$RUN/platform.pid"
    PYTHONPATH=business/src:libs nohup uv run --no-sync uvicorn --factory business_app.main:create_app \
      --host "$LOOPBACK_HOST" --port "$BUSINESS_APP_PORT" > "$RUN/business.log" 2>&1 & echo $! > "$RUN/business.pid"
    PYTHONPATH=psp-mock/src:libs nohup uv run --no-sync uvicorn --factory psp_mock.main:create_app \
      --host "$LOOPBACK_HOST" --port "$PSP_MOCK_APP_PORT" > "$RUN/psp-mock.log" 2>&1 & echo $! > "$RUN/psp-mock.pid"
    nohup "$CADDY" run --config deploy/tls/Caddyfile --adapter caddyfile > "$RUN/caddy.log" 2>&1 & echo $! > "$RUN/caddy.pid"
    for _ in $(seq 1 50); do
      curl -fsk --tlsv1.3 "https://localhost:$PLATFORM_TLS_PORT/livez" >/dev/null 2>&1 && \
      curl -fsk --tlsv1.3 "https://localhost:$BUSINESS_TLS_PORT/livez" >/dev/null 2>&1 && { echo started; exit 0; }
      sleep 0.2
    done
    echo "start failed"; exit 1 ;;
  stop)
    for p in caddy psp-mock business platform; do [ -f "$RUN/$p.pid" ] && kill "$(cat "$RUN/$p.pid")" 2>/dev/null || true; rm -f "$RUN/$p.pid"; done
    echo stopped ;;
esac
