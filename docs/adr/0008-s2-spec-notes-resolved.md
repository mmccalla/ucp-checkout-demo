# ADR 0008: S2 spec notes 1 to 4, resolved by spec v1.1.2 section 15.2

- Status: Accepted.
- Date: 2026-10-24.
- Owner: Mark McCalla.

## Context

Before the rebuild, slice S2 found four places where the pinned upstream code and the spec v1.1.1 text did not agree. Spec v1.1.2 section 15.2 resolves them.

## Decision

| Note | Pinned upstream behaviour | v1.1.2 rule | Build |
|---|---|---|---|
| 1 | The sample Create returns 201 for a checkout with an error message | AC-14: 201 for a Create that makes a checkout, 200 for an Update, 200 `error_response` for a Create that makes no checkout | Patch P8, test `test_ac14_*` |
| 2 | The Platform expected only 200 | T-95: the Platform accepts 201 and 200 | `checkout_client`, `checkout_view` |
| 3 | The sample Update model uses the response type `Fulfillment` (`fulfillment_group.json` line 7 requires `line_item_ids`, but line 19 gives `"ucp_request": "omit"`) | P12: `FulfillmentUpdateRequest` | Patch P12, test `test_ac109_*` |
| 4 | No pinned schema for the protocol error body | T-102: `{code, content}` for the listed statuses and codes. UNVERIFIED (no schema) | `business_app/errors.py`, ADR 0006 |

## P12 review

1. `fulfillment_method.json` line 25: `line_item_ids` has `"ucp_request": {"create": "optional", "update": "required"}`. The SDK `FulfillmentMethodUpdateRequest` has `line_item_ids: list[str]` (required). They agree.
2. `fulfillment_group.json` line 19: `line_item_ids` has `"ucp_request": "omit"`. The SDK `FulfillmentGroupUpdateRequest` has only `id` (required, line 13) and `selected_option_id`. It has no `line_item_ids` field. They agree. The model has `extra="allow"`, so a sent `line_item_ids` is not rejected. The composed schema also allows it (the root and the group allow unknown fields).
   - Defect (found again in S3 under spec v1.1.3 T-104): the vendored `services/checkout_service.py` Update path (repository line 671) put the client `line_item_ids` into the response. P12 did not change this. Patch P14 fixes it: the Business ignores the client `line_item_ids` and `options`, never echoes them, and logs the field path only. T-104 is ACCEPTED (spec v1.1.4 section 15.4 row 1). P14 in commit `a6f7ec4` already implements the no-echo rule and its test. The no-echo patch is necessary under each rule.
3. A valid Update with `line_item_ids` on each method and only `id` and `selected_option_id` on each group passes (`test_ac109_incomplete_to_ready_minor_units_links`). An Update method without `line_item_ids` fails (`test_bad_payloads_fail`).

## Sources

- https://github.com/Universal-Commerce-Protocol/ucp/blob/9c9d6fce39ffa8bf7cb66309c378b79fb75b5382/source/schemas/shopping/types/fulfillment_method.json
- https://github.com/Universal-Commerce-Protocol/ucp/blob/9c9d6fce39ffa8bf7cb66309c378b79fb75b5382/source/schemas/shopping/types/fulfillment_group.json
- `ucp-sdk` 0.4.6 (PyPI wheel, sha256 in `pins/PINS.toml`): `ucp_sdk/models/schemas/shopping/types/fulfillment_method_update_request.py` line 47, `fulfillment_group_update_request.py` lines 32 and 36.
