# ADR 0010: S4 mock PSP, failed payment (T-105), source labels and the decline screen

- Status: Accepted for S4b. Items 9 and 10 stay open.
- Date: 2026-10-25.
- Owner: Mark McCalla.

## Context

Slice S4 (04-build-plan.md) adds Complete with the mock PSP, the order and the signed webhooks. Spec v1.1.4 section 15.4 gives two decisions: T-105 (a failed payment) and the fifth source label `LOCAL STEP`. Section 15.5 aligns the UX texts with 02-design.md v1.1.3 and input-ux.md v1.1. The UCP sources are at commit `9c9d6fc`.

## Decision

1. Mock PSP (`psp-mock/`). `POST /charges` takes `handler_id`, `idempotency_key`, `amount`, `currency` and `token`. It gives `approved` or `declined`. `PUT /outcome` sets the next outcome (SC7). The charge records keep no token (AC-97). An approved key gives the stored approval again. A declined key can be tried again. The PSP binds to 127.0.0.1 (DM-26).
2. PSP client (`business/src/business_app/psp_client.py`). The Business sends the checkout ID as the PSP idempotency key (02-design.md section 14.1, T-31). A decline raises `PaymentFailedError`. The PSP reason goes to the log only. A transport error gives HTTP 503 `psp_unavailable`.
3. T-105 (AC-34). A failed payment on Complete is HTTP 200 with the checkout body (`ucp.status` `success`). The status stays `ready_for_complete`. There is no `order`. There is one message: `type` `error`, `code` `payment_failed`, `severity` `recoverable`. The content is "The payment was not accepted. You did not pay. You can try again with a new payment." It has no token and no PSP reason. The line items, totals and fulfillment do not change. The response is never 402 and never 500. Sources at UCP `9c9d6fc`: checkout-rest.md lines 1275-1282, checkout.md lines 242 and 245-248, rest.openapi.json lines 301-317.
4. Idempotency (AC-46). The Business stores the failed response for the Idempotency-Key. The same key and the same body give the stored response, with no second PSP call. The same key with another body gives HTTP 409. A new token gives a new body, so the Platform sends a new key (AC-35). Source: signatures.md lines 833 and 844-848 at UCP `9c9d6fc`.
5. Order of checks (patch P15). Complete checks the fulfillment and the stock before it charges. Thus an invalid fulfillment gives no charge. Only a handler that the Business profile declares can pay (AC-32).
6. AC-112 and AC-54. The completed response echoes the instruments without `credential`. The sample request log (`request_logs`) masks each credential.
7. Source labels (AC-63, spec v1.1.4 section 15.4 row 2 and section 15.5 row 8). There are 5 labels. `LOCAL STEP` is only on the 2 Google Pay mapping rows (handler config to `PaymentDataRequest`, and M7 `card_payment_instrument`). These rows also keep `NOT UCP`. M10 Complete is `LIVE CALL`. M9 (Business to PSP) is `SIMULATED`. The Platform does not see M9. The M9 row tells what the M10 response shows. In a replay each label is `RECORDED` and `NOT UCP` stays (UX-4.5).
8. Icons (UX-4.4.1). The labels use Material Symbols icons with `aria-hidden="true"`: `sync_alt` (LIVE CALL), `history` (RECORDED), `science` (GOOGLE PAY TEST), `theater_comedy` (SIMULATED) and `laptop` (LOCAL STEP). The SVG files are vendored in `platform/web/checkout/vendor/material-symbols/` from https://github.com/google/material-design-icons at commit `10ecc14790612ca8fd164e3f4ffe9c16fc50d5b7`, with pinned sha256 values. The licence is Apache-2.0 (the LICENSE file at the same commit). The page loads no icon font and calls no CDN. The repository has no `laptop` folder. The codepoints file gives `laptop` and `computer` the same codepoint (`e31e`). Thus `laptop.svg` is `computer_24px.svg`. `LOCAL STEP` uses the neutral tokens: text `#374151`, border and icon `#4B5563`, fill `#F3F4F6`.
9. LOCAL STEP text (open). Section 15.4 gives "The Platform computed this step itself. No request went over the network for this step." Section 15.5 row 8 (UX-4.4.1) gives the accessible name and the visible detail text "Local step: the Platform did this step. No network call." The code follows the later section 15.5. The difference is recorded for the PM.
10. Decline screen ST13 (UX-7.3, UX-8.2). The first decline shows `declined.heading` and `declined.body`. A second or later decline in the same checkout shows `declined.again.heading` and `declined.again.body`. The focus moves to the panel heading. The status region (`role="status"`) announces `declined.announce` or `declined.again.announce`. Error panels have `role="alert"`. The decline panel is not an error. The M10 row shows `inspector.m10.declined`. A retry M10 row shows `inspector.retry.newKey`. The UI shows `inspector.retry.sameKey` in CI mode only, in the cases of ADR 0012. A same-key Complete is not a "Try again" action: ADR 0012 gives the AC-44 recovery and the "Try again" scope (Create and Update, AC-52).
11. Contrast test UX-U-18 (G7). `tests/s3/e2e/test_g7_s4.py` measures the computed colours of each badge and of the decline panel in the built page. It uses the WCAG 2.2 relative luminance and contrast ratio (https://www.w3.org/TR/WCAG22/#dfn-relative-luminance, https://www.w3.org/TR/WCAG22/#dfn-contrast-ratio). Text needs 4.5:1 (SC 1.4.3). Borders and icons need 3:1 (SC 1.4.11). `GOOGLE PAY TEST` shows only with the real pay.js, so the test also renders one badge of each label with the page's own CSS.
12. Webhook test seam. The sample signs each webhook delivery (RFC 9421). The config value `WEBHOOK_TRANSPORT` lets the tests record the deliveries in the process. No test delivery goes to the network.

## Consequences

- AC-79 and AC-98 pass in G7: the keyboard run ends on "Order confirmed" with an order ID.
- ADR 0006 decision 5 and ADR 0009 items 6 and 10 are closed or replaced.
- The demo-mode Business profile does not declare `dev.mock.payment_handler`. Only the CI profile declares it.

## Sources

- 03-spec.md v1.1.4 sections 15.4 and 15.5, appendix T-105, AC-34 and AC-63.
- 02-design.md v1.1.3 UX-4.4.1, UX-4.5, UX-7.2, UX-7.3 and UX-8.2.
- UCP at `9c9d6fc`: checkout-rest.md, checkout.md, rest.openapi.json, signatures.md (lines above).
- https://github.com/google/material-design-icons/tree/10ecc14790612ca8fd164e3f4ffe9c16fc50d5b7
- https://www.w3.org/TR/WCAG22/
