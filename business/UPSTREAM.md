# Upstream provenance: the vendored samples server

- Source: `Universal-Commerce-Protocol/samples`, folder `rest/python/server`, commit `e7c9c124864108cbb35e5102beeac9cbef80a154` (spec T-05, D11).
- Licence: Apache License 2.0. Each source file keeps its upstream header. See `NOTICE` and `docs/adr/0005-licence-mit-and-apache-2.md`.
- Copy: the git-tracked files of the folder at that commit, copied to `business/src/ucp_sample_server/`. Then `tools/vendor/patch_sample.py` applies the patches below. Each patch must match exactly one place, else the script stops.
- Each changed file has a change notice after its licence header (Apache-2.0 section 4(b)). Each change has a comment that starts with "UCP demo patch".
- Type check: `tools/gates/g1_vendored.py` with the exact per-file baseline `tools/gates/mypy-vendored-baseline.json` (spec T-103, ADR 0007).

## Files removed from the copy

| File | Reason |
|---|---|
| `routes/discovery_profile.json` | Patch P1. The template has the wrong Google Pay handler entry (02-design 17.2 defects 1 to 5). The host app gives the profile. |
| `README.md` | Patch P13. It shows the same wrong handler entry (handler version `2026-04-08`). The demo pins handler `2026-01-23` (AC-118). Original: https://github.com/Universal-Commerce-Protocol/samples/blob/e7c9c124864108cbb35e5102beeac9cbef80a154/rest/python/server/README.md |

## Patches

| ID | File | Change | Reason |
|---|---|---|---|
| P1 | `config.py` | `set_profile()`, `_get_profile()` with no file fallback, `get_response_capabilities()`. Typed profile cache. | 02-design 17.2 defects 1 to 5. The served profile passed the S1 checks (AC-106). |
| P1 | `services/checkout_service.py` | `capabilities=config.get_response_capabilities()` | The response capabilities come from the served profile. |
| P2 | `config.py` | `DEFAULT_CURRENCY = "GBP"` | Spec T-70. |
| P3 | `config.py` | `require_signatures` default `True` | 02-design 17.2 defect 7, spec T-04. Off only in gate G5. |
| P4 | `config.py` | Hooks `PAYMENT_AUTHORIZER` (fails closed), `PROFILE_RESOLVER`, `LINKS` | 02-design 17.2 defect 6, AC-109. |
| P5 | `dependencies.py` | `verify_signature` skips when the host gate has checked the signature | The gate verifies one time, before the route (ADR 0006). |
| P6 | `routes/ucp_implementation.py` | `extract_webhook_url` uses `PROFILE_RESOLVER`. No second fetch. | The host fetch rules apply (netguard, AC-122). |
| P7 | `services/checkout_service.py` | Remove the unknown root fields (`model_extra`) from the stored data | AC-38, spec T-86. The gate logs them. |
| P8 | `services/checkout_service.py` | `out_of_stock` as a `messages[]` entry (path `$.line_items[i]`, severity `recoverable`). A Create with no item in stock makes no checkout (HTTP 200 `error_response`). An error message keeps the status `incomplete`. | AC-14, spec v1.1.2 section 15.2. checkout-rest.md "Business outcomes". |
| P9 | `server.py` | Bind `127.0.0.1` | DM-26. |
| P10 | `services/checkout_service.py` | `links=list(config.LINKS)`. No delivery option gives `address_undeliverable` (path `$.fulfillment.methods[m].destinations[d]`). Messages reset on each recalculation. | AC-109, AC-14. |
| P12 | `models.py` | The Update model uses `FulfillmentUpdateRequest`, not the response type `Fulfillment` | 02-design 17.2 defect 8, spec v1.1.2 section 15.2 row 9. |
| P13 | `README.md` | Removed | See above. |
| P14 | `services/checkout_service.py` | A client-sent `groups[].line_item_ids` or `groups[].options` on Update is ignored and never echoed. The business sets the group line items. A warning log has the field path only, never the value. | Spec v1.1.4 T-104 (ACCEPTED, section 15.4 row 1). The no-echo part is necessary under each rule. fulfillment.md line 29 and fulfillment_group.json lines 19 and 25 at UCP `9c9d6fc`. Test `tests/s2/contract/test_t104_group_no_echo.py`. |
| P15 | `exceptions.py`, `config.py`, `services/checkout_service.py` | T-105: `PaymentFailedError` is code `payment_failed`, HTTP 200, `recoverable`. Complete checks the fulfillment and the stock before it charges. A payment failure stores the checkout body with one `payment_failed` message for the Idempotency-Key, with no order and no save. Only declared handlers can pay (AC-32). `PAYMENT_GATEWAY` credentials go to `PAYMENT_AUTHORIZER`. The completed response echoes the instruments without `credential` (AC-112). The request log masks each credential (AC-54). `WEBHOOK_TRANSPORT` is a test seam for webhook deliveries. | Spec v1.1.4 T-105 (section 15.4). checkout-rest.md lines 1275-1282, checkout.md lines 242 and 245-248, rest.openapi.json lines 301-317 at UCP `9c9d6fc`. Tests `tests/s4/unit/test_complete.py`. |
| P16 | `config.py`, `webhook_signer.py`, `services/checkout_service.py` | S4 webhooks. `WEBHOOK_SIGNING_KEY`: the webhook signer uses the key that the profile publishes in `signing_keys` (AC-65). `WEBHOOK_PROFILE_URL`: `UCP-Agent` names the public profile URL, not the proxy upstream. The retry backoff adds jitter (T-42). `WEBHOOK_DEAD_LETTER` is called after the last failed attempt or a 4xx (T-42). `ship_order` adds a fake `tracking_number`, `tracking_url` and `carrier` (sample defect: `fulfillment_event.json` needs them when `type` is not `processing`). New `deliver_order` adds a `delivered` event and sends `order_delivered` (AC-74). | order.md lines 416-542 at UCP `9c9d6fc`. https://ucp.dev/2026-04-08/schemas/shopping/types/fulfillment_event.json. Spec T-42, AC-65, AC-74. Tests `tests/s4/g6/test_webhooks.py`. |
| D6 | `services/checkout_service.py` | `google_pay` and `gpay*` handler ids call `config.PAYMENT_AUTHORIZER` | 02-design 17.2 defect 6. S4 sets the authorizer. In S2 it fails closed. |

The host app does not mount the sample discovery and MCP routers (P11: they are not in the demo scope).

## Changed files

- `config.py`
- `dependencies.py`
- `exceptions.py`
- `models.py`
- `routes/ucp_implementation.py`
- `server.py`
- `services/checkout_service.py`
- `webhook_signer.py`
