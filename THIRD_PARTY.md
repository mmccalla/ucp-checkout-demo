# THIRD_PARTY: software that is installed at run time

This file lists the Python packages that `uv.lock` pins. `uv sync` downloads them from PyPI.
None of them is copied into this repository. This repository does not pass on their source code or their binaries.
The licence of each package comes from the metadata of the installed package (and from PyPI where the metadata gave only a family name).
The licence texts are in each package. `NOTICE` lists the files that this repository does hold from other authors.

The lock file has 77 packages (17 direct run time, 4 direct development only, 56 indirect).

| Package | Version | Role | Licence |
|---|---|---|---|
| absl-py | 2.5.1 | direct, run time | Apache-2.0 |
| aiosqlite | 0.22.1 | direct, run time | MIT |
| cryptography | 50.0.2 | direct, run time | Apache-2.0 OR BSD-3-Clause |
| fastapi | 0.121.0 | direct, run time | MIT |
| greenlet | 3.5.6 | direct, run time | MIT AND PSF-2.0 |
| httpx | 0.28.1 | direct, run time | BSD-3-Clause |
| jsonschema | 4.26.0 | direct, run time | MIT |
| opentelemetry-api | 1.45.1 | direct, run time | Apache-2.0 |
| opentelemetry-exporter-otlp-proto-http | 1.45.1 | direct, run time | Apache-2.0 |
| opentelemetry-instrumentation-fastapi | 0.66b1 | direct, run time | Apache-2.0 |
| opentelemetry-instrumentation-httpx | 0.66b1 | direct, run time | Apache-2.0 |
| opentelemetry-sdk | 1.45.1 | direct, run time | Apache-2.0 |
| referencing | 0.37.0 | direct, run time | MIT |
| shortuuid | 1.0.13 | direct, run time | BSD-3-Clause |
| sqlalchemy | 2.0.55 | direct, run time | MIT |
| ucp-sdk | 0.4.6 | direct, run time | Apache-2.0 |
| uvicorn | 0.38.0 | direct, run time | BSD-3-Clause |
| mypy | 1.18.2 | direct, development only | MIT |
| playwright | 1.56.0 | direct, development only | Apache-2.0 |
| pytest | 8.4.2 | direct, development only | MIT |
| ruff | 0.14.3 | direct, development only | MIT |
| annotated-doc | 0.0.5 | indirect | MIT |
| annotated-types | 0.8.0 | indirect | MIT |
| anyio | 4.15.1 | indirect | MIT |
| arrow | 1.4.0 | indirect | Apache-2.0 |
| asgiref | 3.13.0 | indirect | BSD-3-Clause |
| attrs | 26.1.0 | indirect | MIT |
| certifi | 2026.10.23 | indirect | MPL-2.0 |
| cffi | 2.1.1 | indirect | MIT-0 |
| charset-normalizer | 3.5.2 | indirect | MIT |
| click | 8.5.0 | indirect | BSD-3-Clause |
| colorama | 0.4.6 | indirect | UNVERIFIED (Windows only. The metadata is not installed on Linux. PyPI has no licence text in the data that I read.) |
| dnspython | 2.9.0 | indirect | ISC |
| email-validator | 2.3.0 | indirect | Unlicense |
| fqdn | 1.6.0 | indirect | MPL-2.0 |
| googleapis-common-protos | 1.76.0 | indirect | Apache-2.0 |
| h11 | 0.16.0 | indirect | MIT |
| httpcore | 1.0.9 | indirect | BSD-3-Clause |
| idna | 3.20 | indirect | BSD-3-Clause |
| iniconfig | 2.3.1 | indirect | MIT |
| isoduration | 20.11.0 | indirect | ISC |
| jsonpointer | 3.5 | indirect | BSD-3-Clause (PyPI: "Modified BSD License") |
| jsonschema-specifications | 2025.9.1 | indirect | MIT |
| lark | 1.3.1 | indirect | MIT |
| mypy-extensions | 1.1.0 | indirect | MIT |
| opentelemetry-exporter-http-transport | 0.66b1 | indirect | Apache-2.0 |
| opentelemetry-exporter-otlp-common | 0.66b1 | indirect | Apache-2.0 |
| opentelemetry-exporter-otlp-proto-common | 1.45.1 | indirect | Apache-2.0 |
| opentelemetry-instrumentation | 0.66b1 | indirect | Apache-2.0 |
| opentelemetry-instrumentation-asgi | 0.66b1 | indirect | Apache-2.0 |
| opentelemetry-proto | 1.45.1 | indirect | Apache-2.0 |
| opentelemetry-semantic-conventions | 0.66b1 | indirect | Apache-2.0 |
| opentelemetry-util-http | 0.66b1 | indirect | Apache-2.0 |
| packaging | 26.3 | indirect | Apache-2.0 OR BSD-2-Clause |
| pathspec | 1.1.1 | indirect | MPL-2.0 |
| pluggy | 1.7.0 | indirect | MIT |
| protobuf | 7.36.2 | indirect | BSD-3-Clause |
| pycparser | 3.12 | indirect | BSD-3-Clause |
| pydantic | 2.14.1 | indirect | MIT |
| pydantic-core | 2.50.1 | indirect | MIT |
| pyee | 13.0.1 | indirect | MIT |
| pygments | 2.21.0 | indirect | BSD-2-Clause |
| python-dateutil | 3.0.0 | indirect | Apache-2.0 OR BSD-3-Clause (PyPI: "Dual License") |
| requests | 2.34.2 | indirect | Apache-2.0 |
| rfc3339-validator | 0.1.4 | indirect | MIT |
| rfc3986-validator | 0.1.1 | indirect | MIT |
| rfc3987-syntax | 1.1.0 | indirect | MIT |
| rpds-py | 2026.9.1 | indirect | MIT |
| six | 1.17.0 | indirect | MIT |
| starlette | 0.49.3 | indirect | BSD-3-Clause |
| typing-extensions | 4.16.0 | indirect | PSF-2.0 |
| typing-inspection | 0.4.4 | indirect | MIT |
| tzdata | 2026.5 | indirect | Apache-2.0 |
| uri-template | 1.3.0 | indirect | MIT |
| urllib3 | 2.8.0 | indirect | MIT |
| webcolors | 25.10.0 | indirect | BSD-3-Clause |
| wrapt | 2.5.1 | indirect | BSD-2-Clause |

## Tools that scripts download

The pinned version and checksum of each tool are in `pins/PINS.toml`. None of these tools is in this repository.

| Tool | Version | Licence | Source |
|---|---|---|---|
| Caddy | 2.11.7 | Apache-2.0 | https://github.com/caddyserver/caddy/blob/v2.11.7/LICENSE |
| Jaeger | 2.22.0 | Apache-2.0 | https://github.com/jaegertracing/jaeger/blob/v2.22.0/LICENSE |
| ucp-schema | 1.4.1 | Apache-2.0 | https://github.com/Universal-Commerce-Protocol/ucp-schema/blob/6dd2a613d38828c97dca723bdb9ccfc79b2a7e80/LICENSE |
| Chromium (Playwright) | set by Playwright 1.56.0 | UNVERIFIED | https://playwright.dev/python/docs/browsers |
| Google Pay library (`pay.js`) | not pinned | Google terms apply | https://pay.google.com/gp/p/js/pay.js (loaded in the browser at run time, not in CI mode) |

The Google Pay handler schemas in `contracts/gpay-handler/` are in the repository. They are not a package. `NOTICE` (item C1) gives their source, their fetch date (2026-11-04 08:19:46 UTC), their sha256 values and the licence status.
