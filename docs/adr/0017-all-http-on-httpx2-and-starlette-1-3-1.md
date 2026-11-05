# ADR 0017: all HTTP code uses `httpx2`, and Starlette 1.3.1

- Status: ACCEPTED. Mark McCalla approved spec v3 on 5 Nov 2026 with the recommended answers.
- Date: 2026-11-05.
- Owner: Mark McCalla.

## Context

Starlette 1.3.1 builds `TestClient` on `httpx2` (`starlette/testclient.py`, class `TestClient`). The repository used `httpx` 0.28.1. The two libraries gave a type split. mypy read `Any` in the tests, and the tests read the private `TestClient._transport`. Dependabot alert 6 (GHSA-82w8-qh3p-5jfq) is fixed in Starlette 1.3.1. The fix of the cause is one HTTP library.

## Decision

1. `httpx2==2.16.0` replaces `httpx==0.28.1`. `httpx` is not a direct dependency. `starlette==1.3.1` and `fastapi==0.133.0` are pinned in the same commit, because a bump alone or a move alone has no working `TestClient` path.
2. Runtime code, tools, tests and the vendored sample use `httpx2` only. The vendored sample changes only through patch P17 in `tools/vendor/patch_sample.py`.
3. The in-process tests use `httpx2.MockTransport(test_client.send)`. `httpx2` has no public sync ASGI transport. `Client.send` and `MockTransport` are public API. No test reads `TestClient._transport`.
4. `libs/ucp_core/telemetry.py` uses `HTTPX2ClientInstrumentor`. The package name `opentelemetry-instrumentation-httpx` does not change (ADR 0014).
5. The `transport=` parameters of the runtime classes and `WEBHOOK_TRANSPORT` stay. They exist before this change.
6. `filterwarnings = ["error::starlette.exceptions.StarletteDeprecationWarning"]` makes a return of the `httpx` fallback of Starlette fail the tests. It does not suppress a warning.
7. The repository has no bridge, adapter, shim, `alias_httpx()` or union type across two libraries.

## Consequences

- Trust store. For `verify=True`, `httpx2` reads `SSL_CERT_FILE` or `SSL_CERT_DIR` first. On Linux it then loads the OpenSSL default CA locations of the host. `httpx` 0.28.1 used the `certifi` bundle. The trust set can be wider and it can differ on each host. Mark accepted this for `verify=True`. The Caddy CA path passes an explicit `ssl.SSLContext` and does not change.
- Lock. `uv.lock` has `httpx2`, `httpcore2`, `truststore` and `httpx2-jsfetch`. It has no `httpx` and no `httpcore`. `httpx2-jsfetch` installs only on Emscripten (marker in the `httpx2` metadata). Mark accepted it.
- Remaining `httpx` names. `fastapi` (extras `standard`, `standard-no-fastapi-cloud-cli`, `all`), `starlette` (extra `full`) and `opentelemetry-instrumentation-httpx` (extra `instruments-any`) name `httpx` only under extras. Nothing in this repository selects those extras.
- Young project. `httpx2` is a fork with fast releases. The exact pin and the lock hashes limit drift. Dependabot proposes each bump and the same gates run on it.
- Tracing. A call made directly on an in-process `TestClient` has no client span. No test asserts it.
- Vendored baseline. The G1 vendored mypy count stays at 313. If a later release lowers the count, G1 fails. Lower the baseline file only with the approval of Mark.

## Not in this change

- `CheckoutClient.verify: Any` and the stale rows of `THIRD_PARTY.md` (for example `pytest`). A separate small change handles them.

## Open items

- UNVERIFIED: `truststore` behaviour on Windows and macOS. The checks ran on Linux only.
- UNVERIFIED: the state of Dependabot alert 6 after merge. A scan runs after merge.
- UNVERIFIED: the GitHub CI run. It waits for the push approval of Mark.
