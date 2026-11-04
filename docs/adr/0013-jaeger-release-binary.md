# ADR 0013: Jaeger 2.22.0 runs as the official release binary

- Status: Accepted for S4 (T-106).
- Date: 2026-10-28.
- Owner: Mark McCalla.

## Context

T-34 says "Jaeger 2.22 all-in-one". The first pin was the image `cr.jaegertracing.io/jaegertracing/jaeger:2.22.0` in the old Compose file (removed by T-106). The box has no `docker` and no `podman`. T-106 (ACCEPTED, 25 Oct 2026) replaces the image with the official release binary.

## Decision

1. The demo runs `jaeger-2.22.0-linux-amd64/jaeger` from the official release `v2.22.0` (https://github.com/jaegertracing/jaeger/releases/tag/v2.22.0). The release was published 6 Oct 2026 at 14:27:50 UTC (15:27 Europe/London).
2. Before the first run, `tools/jaeger.sh verify` checks the sha256 of the archive, checks the gpg signature, and checks the sha256 of the binary. `tools/jaeger.sh start` checks the sha256 of the binary each time. If a check fails, the binary does not run.

   | Item | Value | Source |
   |---|---|---|
   | Archive sha256 | `cb0c0be9a4b8fba424bbbc6217b0feb0adeea3bca5b73a83db1af31bb7d34389` | Same as T-106 and as the `digest` field of the GitHub release asset |
   | Binary sha256 | `fa574f53e2f739301f301f66e5608c84d0b9a90cdd08e4f6cba8809d171854e1` | Same as T-106 and as the line for `jaeger` in `jaeger-2.22.0-linux-amd64.sha256sum.txt` from the release |
   | Signing key | `BD0B 0260 14C7 2526 1C94 7887 B42D 1DB0 F079 690F`, "Jaeger Tracing Artifact Signing <jaeger-tracing@googlegroups.com>" | Public key block on https://www.jaegertracing.io/download/ ("Signed Artifacts"). Saved as `pins/jaeger-signing-key.asc` |
   | Signature result | `gpg: Good signature` (the key is not certified by a trusted signature in a new keyring, as expected) | local run records (not in this repository) |

3. The checksum file of the release (`jaeger-2.22.0-linux-amd64.sha256sum.txt`) lists the files in the archive. It does not list the archive. The archive sha256 is thus checked against T-106 and the GitHub `digest`, and the gpg signature protects the archive.
4. All-in-one role. The Jaeger 2.22 getting-started page (https://www.jaegertracing.io/docs/2.22/getting-started/) says that the plain start "runs the all-in-one configuration of Jaeger ... that combines collector and query components in a single process and uses a transient in-memory storage". The configuration page (https://www.jaegertracing.io/docs/2.22/deployment/configuration/) says that `cmd/jaeger/internal/all-in-one.yaml` is "bundled in the Jaeger binary for `all-in-one` role". The binary with no `--config` flag prints "No '--config' flags detected, using default All-in-One configuration with memory storage." (local run records (not in this repository)). CONFIRMED.
5. Loopback. With no config, the 2 query listeners (16686 HTTP and 16685 gRPC) bind to all addresses (`*`). The other listeners bind to `127.0.0.1` (local run records (not in this repository)). This does not agree with DM-26. The configuration page documents `--set` overrides for the all-in-one role. `tools/jaeger.sh start` thus uses `--set=extensions.jaeger_query.http.endpoint=127.0.0.1:16686` and `--set=extensions.jaeger_query.grpc.endpoint=127.0.0.1:16685`. `ss -ltnp` then shows 16 listeners and all are on `127.0.0.1` (local run records (not in this repository), run in a separate network namespace). The ports are 4317, 4318, 5778, 5779, 6831 (UDP), 6832 (UDP), 8888, 9411, 13132, 13133, 14250, 14268, 16685, 16686, 27777 and 27778.
6. Tests read only `/api/v3/*` (T-34, https://www.jaegertracing.io/docs/2.22/apis/ "Read APIs").
7. `pins/PINS.toml` section `[jaeger]` now holds the version, the URL, the two sha256 values and the key fingerprint. T-106 removed the old Compose file. Nothing else used it. `02-design.md` section 17.5 and `04-build-plan.md` line 82 are changed to the binary.

## Consequences

- The box needs no container runtime.
- The in-memory storage keeps traces only while Jaeger runs.
- UNVERIFIED: the check in item 5 ran in a separate network namespace, because another Jaeger process (started before this run) held the default ports on the host. The process on the host also shows only `127.0.0.1` listeners (local run records (not in this repository)).
