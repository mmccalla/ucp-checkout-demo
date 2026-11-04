# ADR 0009: S3 review screen, approval gate, Google Pay mapper and CI stub

- Status: Accepted for S3. Item 6 is closed and item 10 is replaced in S4 (ADR 0010). Item 7 stays open.
- Date: 2026-10-25.
- Owner: Mark McCalla.

## Context

Slice S3 (04-build-plan.md) adds the review screen, the approval gate DM-06, the Google Pay button, the protocol inspector and a mapper from the Business handler config. CI uses a Google Pay stub. The spec is 03-spec.md v1.1.3. The Business Complete fails closed until S4 because S4 adds the payment authorizer.

## Decision

1. Approval gate (DM-06, AC-23 to AC-25). The Platform runs the gate on each review. The gate stops the payment if one of these is true:
   - The handler `environment` is not `TEST`.
   - The Business profile URL is not on the allowlist. The default allowlist is the demo Business. The env var `PLATFORM_ALLOWLIST` replaces it.
   - The currency is not GBP.
   - The total is more than GBP 50.00 (per payment).
   - The spend today plus the total is more than GBP 100.00 (per day). The ledger is a JSONL file (`PLATFORM_SPEND_FILE`). Only a `completed` order adds to it.
   When the gate stops, the page shows the reason and no Google Pay button.
2. Approval hash (AC-22). The hash is SHA-256 over `id`, Business, `currency`, `line_items`, `totals` and `handler_id`. The pay step does a fresh Get Checkout. If the hash changed, the Platform discards the token, sends no Complete and shows a new review screen. One approval permits one Complete. A second request while Complete is in flight gets HTTP 409 (AC-51).
3. Mapper (AC-21, AC-27, AC-36, AC-110). The Platform validates the handler config, then maps snake_case to camelCase (02-design.md section 8.3). `environment` goes to `PaymentsClient`. Tokenization parameters are copied without change. `merchantOrigin` and `authJwt` are not sent. `transactionInfo` has `totalPriceStatus` `FINAL`, `checkoutOption` `COMPLETE_IMMEDIATE_PURCHASE` and `countryCode` `GB`. The rule "COMPLETE_IMMEDIATE_PURCHASE works only with FINAL" and the `totalPrice` format come from https://developers.google.com/pay/api/web/reference/request-objects.
4. Click handler (AC-19, AC-77). `loadPaymentData` is the first call in the click handler (https://developers.google.com/pay/api/web/reference/client: the call must occur in a user click activation). The stub records `navigator.userActivation.isActive` and the test checks it.
5. CI stub. `platform/web/checkout/gpay-stub.js` copies the `PaymentsClient` calls (`isReadyToPay`, `createButton`, `loadPaymentData`). It returns the documented `PaymentData` example (https://developers.google.com/pay/api/web/reference/response-objects). The Platform serves it only when `MODE=ci`. In demo mode it gives HTTP 404 and the page loads `https://pay.google.com/gp/p/js/pay.js`.
6. Complete in S3 (open until S4). The Business has no payment authorizer for `gpay_demo_test_01`, so Complete gives HTTP 500 and the page shows a setup problem. Thus AC-79 and AC-98 are PARTIAL in S3: the keyboard run and the Complete request pass, the order completion is S4. CLOSED in S4: the mock PSP authorizes the payment and the shop places the order (ADR 0010).
7. No `continue_url` (T-68, open). The demo Business sends no `continue_url`. The e2e tests for AC-16 and AC-20 add one to the response with the test hook. The tests say so in a comment.
8. State tests. The demo Business does not make some states (`requires_buyer_input`, `requires_escalation`, `unrecoverable`, a totals mismatch, `PRODUCTION`, USD, a config without `merchant_id`). The e2e tests change the Business response in the test transport. The Platform code is not changed for the tests.
9. Accessibility checks. The e2e tests inject axe-core 4.14.0 (vendored test file, `tests/s3/e2e/vendor/README.md`) with the tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa` and `wcag22aa` (https://github.com/dequelabs/axe-core/blob/v4.14.0/doc/API.md). A second script checks the contrast, the target size (24 CSS px), names and labels, and horizontal scroll. The keyboard test records the tab sequence (AC-80).
10. Source labels (AC-63). The mapping row has the label `LIVE CALL` because the Platform really computes it. It is not a network call. The spec gives only four labels. This choice is UNVERIFIED with the PM. REPLACED in S4: spec v1.1.4 AC-63 has 5 labels. The mapping rows have `LOCAL STEP` (ADR 0010).

## Consequences

- G7 runs in CI with no Google account and no network to Google.
- The live sheet ("Pay now" label, AC-98) and a live `loadPaymentData` approval need M-01. They are BLOCKED-ON-M-01.
- U-45 (`countryCode` `GB`) stays UNVERIFIED. The request reference requires `countryCode` for EEA and SCA countries. It does not name GB.

## Sources

- https://developers.google.com/pay/api/web/reference/request-objects
- https://developers.google.com/pay/api/web/reference/response-objects
- https://developers.google.com/pay/api/web/reference/client
- https://github.com/Universal-Commerce-Protocol/ucp/blob/9c9d6fce39ffa8bf7cb66309c378b79fb75b5382/docs/specification/checkout.md (lines 797 to 815: totals rules, line 461: `continue_url`)
- https://github.com/dequelabs/axe-core/blob/v4.14.0/doc/API.md
