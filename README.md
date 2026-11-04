# ucp-checkout-demo

This project is a demo of a Universal Commerce Protocol (UCP) checkout. It uses UCP version 2026-04-08 and the `com.google.pay` payment handler.
The demo uses TEST mode only. No money moves. The demo cannot charge a card.

> This is a personal demo project. It is not an official project of Google or of the UCP project. Google LLC does not own this project and is not part of it. "Google" and "Google Pay" are trademarks of Google LLC. The project uses these names only to say which public interface the demo talks to.

The "Pay" button of the CI stub is a plain test button. It is not a Google Pay button.

## Licence

The code that Mark McCalla wrote uses the MIT licence. See `LICENSE` (Copyright (c) 2026 Mark McCalla).

The project also contains copies of files that other persons wrote. These files keep their own licences:

- These files use the Apache License 2.0 (`LICENSES/Apache-2.0.txt`).
  They are the sample server in `business/src/ucp_sample_server/`.
  They are the UCP schemas in `contracts/ucp-schemas/`, `contracts/ucp-schemas-2026-01-23/` and `contracts/composed/`.
  They are the input files in `conformance/input/`.
  They are the icons in `platform/web/checkout/vendor/material-symbols/`.
- The test tool `tests/s3/e2e/vendor/axe-4.14.0.min.js` uses the Mozilla Public License 2.0 (`tests/s3/e2e/vendor/axe-LICENSE`).
- The Google Pay handler schemas in `contracts/gpay-handler/` have no confirmed licence. The source is https://pay.google.com/gp/p/ucp/2026-01-23/schemas/. "Licence: not confirmed. The hosted files state no licence. Mark asks Google to confirm."

`NOTICE` lists each copied item with its source, its version, its licence, and our changes.
`THIRD_PARTY.md` lists the packages and the tools that a user installs at run time. The repository does not contain them.

## What the demo has

The demo has three services and one TLS proxy. All of them listen on `127.0.0.1` only.

| Part | URL | What it is |
|---|---|---|
| Platform | https://localhost:8443 | The shopping page and the UCP client |
| Business | https://localhost:9443 | The UCP server (`/.well-known/ucp`, `/checkout-sessions`) |
| Mock PSP | 127.0.0.1:8301 | A fake payment provider. It charges nothing |
| Caddy | ports 8443 and 9443 | A local TLS 1.3 proxy |

## What you need

- Linux, x86-64.
- `git`, `curl`, `tar`, `gpg`, and `python3`.
- `uv` (https://docs.astral.sh/uv/). It installs Python 3.12 by itself.
- Rust and `cargo`, with the packages `pkg-config` and `libssl-dev`. They are necessary to build `ucp-schema`.
- Google Chrome at `/usr/bin/google-chrome`. Only the browser tests and the smoke test use it.
- `unshare` with user namespaces (the `util-linux` package). Only the latency gate G8 uses it.

## Install the tools

Clone the repository:

```
git clone https://github.com/mmccalla/ucp-checkout-demo.git
cd ucp-checkout-demo
uv sync --locked
tools/get_caddy.sh
```

The command `uv sync --locked` installs the Python packages with the hashes in `uv.lock`.
The command `tools/get_caddy.sh` downloads the pinned Caddy release and checks its sha512. It writes the file `caddy` to the folder `../tools/caddy-bin/`. This folder is not in the clone.

Build the tool `ucp-schema` 1.4.1. Use the pinned commit:

```
cargo install --locked --git https://github.com/Universal-Commerce-Protocol/ucp-schema \
  --rev 6dd2a613d38828c97dca723bdb9ccfc79b2a7e80 --root "$HOME/ucp-tools/ucp-schema"
export UCP_SCHEMA_BIN="$HOME/ucp-tools/ucp-schema/bin/ucp-schema"
```

The build stops with an error if `pkg-config` is not installed. The gates G1 and G2, and one unit test, use this tool.

## Start the demo

```
tools/run_local.sh start
```

The command prints `started` when the TLS endpoints answer. The start takes about 2 seconds on the test computer.

Make sure that all services are ready. Each command prints JSON with `"status":"ok"`:

```
curl -s http://127.0.0.1:8101/readyz      # Platform
curl -s http://127.0.0.1:8201/readyz      # Business
curl -s http://127.0.0.1:8301/readyz      # mock PSP
```

The proxy uses a local certificate authority (CA). Caddy writes the root file to `.run/xdg-data/caddy/pki/authorities/local/root.crt`.
Use this file with `--cacert` to read the Business profile:

```
curl -s --cacert .run/xdg-data/caddy/pki/authorities/local/root.crt https://localhost:9443/.well-known/ucp
```

To open the shopping page, go to https://localhost:8443/checkout/. The address https://localhost:8443/ alone answers with HTTP 404.
The browser shows a certificate warning because your computer does not trust the local CA. The project does not install the CA.
Tell the browser to continue for `localhost`, for this one page. Or import the root file in a different browser profile.

Stop the demo:

```
tools/run_local.sh stop
```

## Smoke test without a Google Account

The smoke test opens a smoke page in headless Chrome. It records the Google Pay button and the result of the sheet. It does not sign in to a Google Account.

```
uv run --no-sync python tools/smoke/run_smoke.py .run/smoke
```

The smoke page loads `https://pay.google.com/gp/p/js/pay.js`. The computer must have internet access. Without internet access, the test ends with no button.
A full checkout with the Google Pay TEST sheet needs a person with a Google Account. The project has no automatic procedure for this step.

## Tests

Run the unit tests after you set `UCP_SCHEMA_BIN`:

```
uv run --no-sync pytest -q tests/s1/unit tests/s2/unit tests/s3/unit tests/s4/unit tests/s5/unit tests/s6/unit
```

On the test computer, 331 tests passed in about 27 seconds. Without `UCP_SCHEMA_BIN`, one test fails and one test skips.

## Gates

These items are necessary for the gates:

- A clean and committed working tree.
- The demo services. The gates start them.
- Jaeger, in operation (see the next section). Gate G4 stops with 6 errors if Jaeger does not operate.
- The value of `UCP_SCHEMA_BIN`.

```
tools/gates/run_all.sh .run/gates
```

The time for all gates is about 4 minutes on the test computer. The gates are G1 (pins, secrets, lint, types), G2 (schemas), G3 (unit tests), G4 (contract and live tests), G6 (signatures), G7 (browser tests), and G8 (latency and readiness).
The list for the current slice is in `tools/gates/gates.toml`.
The conformance gate G5 (`conformance/gate.py`) is not in the list. It fails today. The causes are in `docs/S5-g5-analysis.md`.

## Jaeger traces

Jaeger 2.22.0 shows one trace for each checkout. See `tools/jaeger.sh` and ADR 0013.
Download Jaeger and make sure that the signature is correct. Do this before you run the gates:

```
export JAEGER_DIR="$PWD/../tools/jaeger"
mkdir -p "$JAEGER_DIR"
base=https://github.com/jaegertracing/jaeger/releases/download/v2.22.0
curl -fsSL -o "$JAEGER_DIR/jaeger-2.22.0-linux-amd64.tar.gz" "$base/jaeger-2.22.0-linux-amd64.tar.gz"
curl -fsSL -o "$JAEGER_DIR/jaeger-2.22.0-linux-amd64.tar.gz.asc" "$base/jaeger-2.22.0-linux-amd64.tar.gz.asc"
tar -xzf "$JAEGER_DIR/jaeger-2.22.0-linux-amd64.tar.gz" -C "$JAEGER_DIR"
tools/jaeger.sh verify
tools/jaeger.sh start
```

When Jaeger answers on `127.0.0.1:16686`, `tools/run_local.sh` sends the spans to it. Set `UCP_TRACING=0` to turn this off.
Stop Jaeger with `tools/jaeger.sh stop`.

## Latency gate G8

```
tools/latency/run_g8.sh .run/g8
```

The script exports the last commit to a temporary folder. It starts a second copy of the demo in a private network namespace. Your demo does not change.

It sends 100 Create, 100 Update, and 100 Complete calls through the Platform client. It checks the p95 limits of Google (4 s, 5 s, 10 s) and 0 % errors.
It also checks that all services are ready in 120 s. On the test computer, all services were ready after 2.13 s.
The limits come from https://developers.google.com/merchant/ucp/guides/overview/native-checkout, section "Service level objectives". That page has no version in its URL.

## Manual check M-01

The check M-01 needs a person with a Google Account. It is not part of the automatic gates.
This repository has no written procedure for it. A person opens the checkout page and runs the Google Pay TEST sheet by hand.

## Folders

| Folder | Content |
|---|---|
| `platform/backend/src/platform_app/` | Platform server, UCP client, Google Pay page |
| `business/src/business_app/` | Business server (our code) |
| `business/src/ucp_sample_server/` | Copied and patched upstream sample server |
| `psp-mock/src/` | Mock PSP |
| `libs/ucp_core/` | Shared code (schemas, signatures, TLS, network guard) |
| `contracts/` | Pinned UCP schemas and the Google Pay handler schemas |
| `conformance/` | The G5 gate and its input files |
| `tools/` | `run_local.sh`, `get_caddy.sh`, `jaeger.sh`, `gates/`, `latency/`, `smoke/` |
| `tests/` | Tests, one folder for each slice |
| `docs/` | Decisions (`docs/adr/`) and slice reports |

## Project files

- `CONTRIBUTING.md` tells you how to report a problem and how to send a change.
- `SECURITY.md` tells you how to report a problem with the safety of the code.
- `CODE_OF_CONDUCT.md` gives the rules for behavior in this project.
- `LICENSE`, `NOTICE`, and `THIRD_PARTY.md` give the licences and the credit for the work of other people.
