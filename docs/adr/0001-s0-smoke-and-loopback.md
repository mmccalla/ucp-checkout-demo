# ADR 0001: S0 smoke test, loopback layout and TLS proxy

- Status: Accepted. Date: 2026-10-24. Rebuilt on 2026-10-24 after the loss of the old repository (ADR 0004). The decisions did not change.

## Decisions

1. All services listen on `127.0.0.1` only (DM-26 option (a)). The ports are in `deploy/ports.env`.
2. Caddy 2.11.7 (T-90) is the TLS proxy. It accepts TLS 1.3 only (`protocols tls1.3`) and refuses TLS 1.2 (AC-121). It uses its local CA (`tls internal`, `skip_install_trust`). We do not install the CA in a system trust store without the approval of Mark.
3. The smoke page is on the Platform origin `https://localhost:8443/smoke/` (spec 4.2). It loads `https://pay.google.com/gp/p/js/pay.js` and uses `environment` `TEST`.
4. The Google Pay handler config schema leaves `tokenization_specification.parameters` open. `ucp-schema validate --strict true` refuses `gateway`, but the Google request reference requires `gateway`. Thus G2 validates the handler config with the default (`--strict false`).
5. The smoke log keeps no token value. It keeps only the token type and length.
6. The spec does not give a Caddy version. We pinned 2.11.7 with the sha512 from the release checksum file.

## Sources

- https://developers.google.com/pay/api/web/reference/request-objects
- https://pay.google.com/gp/p/ucp/2026-01-23/schemas/config.json
- https://caddyserver.com/docs/caddyfile/directives/tls (`protocols`)
