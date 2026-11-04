# Composed checkout schemas (S2)

`tools/contracts/compose.py` makes these files with the pinned `ucp-schema` CLI (commit `6dd2a61`, ADR 0002).
Do not edit them by hand. The G4 contract test runs `compose.py --check`.

| File | CLI command (from the repository root) |
|---|---|
| `checkout.create_request.json` | `ucp-schema resolve self-describing.json --request --op create --schema-local-base contracts/ucp-schemas --schema-remote-base https://ucp.dev/2026-04-08/schemas --pretty` |
| `checkout.update_request.json` | the same, with `--op update` |
| `checkout.read_response.json` | the same, with `--response --op read` |

`self-describing.json` holds the capabilities of `business/profile/demo.json` (checkout and fulfillment). The CLI composes the fulfillment extension onto checkout. Then it applies the `ucp_request` annotations for the operation.

The Business validates each Create and Update body against these files (AC-89, AC-94, AC-104). The Platform validates each checkout response against `checkout.read_response.json`.
