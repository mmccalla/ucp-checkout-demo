# ADR 0011: S4 order webhooks, response signatures and Get Order (gate G6)

- Status: Accepted for S4 part 1.
- Date: 2026-10-25.
- Owner: Mark McCalla.

## Context

Slice S4 adds the order, the signed order webhooks and gate G6 (AC-64 to AC-75, AC-113). The UCP sources are at commit `9c9d6fc`. The vendored sample is at commit `e7c9c12`. Patch P16 changes the sample (business/UPSTREAM.md).

## Decision

1. Business webhooks (P16). The sample signs each webhook with the key that the Business profile publishes in `signing_keys` (AC-65). The `UCP-Agent` header names the public profile URL. The retry backoff has jitter. After the last failed attempt or a 4xx, the Business writes a dead-letter row (T-42). Source: order.md lines 416-542.
2. Webhook signature cover (design choice). The Platform requires `webhook-id` and `webhook-timestamp` in the signature components. The sample signs these headers. The pinned text does not make them mandatory. Thus this rule is a demo policy.
3. Receiver results (T-42). A bad, missing or partial signature gives 401 (AC-67, AC-68). A bad body gives 400. A Business that does not own the order gives 403 (AC-69). A failed dedup store gives 503 with `Retry-After` (AC-72). The same `Webhook-Id` gives 2xx with no second effect (AC-70). The state only moves forward (AC-71).
4. Response signature (AC-64). With enforcement on, the Business signs the Complete response. The components are `@status`, `content-digest` and `content-type`. The Platform checks it and the inspector shows "Response signature: verified keyid=…". With enforcement off, the Business sends no signature and the inspector shows "not signed". Webhooks stay signed and checked (AC-65).
5. Get Order (AC-73). Only the Platform that created the order can read it. Another caller gets HTTP 200 with `error_response`, code `unauthorized` and content "Not authorized to access this order.". Source: order.md section "Get Order", Authorization. Reconcile compares the Get Order state with the webhook state.
6. Simulation (AC-74, AC-75). After the Complete response, the Business simulates "shipped", then "delivered". Each step sends one signed webhook. Tracking values are fake (`SIM-…`, `https://tracking.invalid/…`). The confirmation e-mail goes to a log file only. In demo mode each step waits 1 s.
7. Key fetch. The Platform reads the Business `signing_keys` from the allowed profile only, with a 300 s cache. The Platform reads the keys at Review, before Complete. The fetch has its own timeline row (AC-59).
8. Gate G6 runs `tests/s4/g6`. The S4 unit tests moved to `tests/s4/unit` (gate G3). `current_slice` is `S4`.

## Open items (UX gaps)

- The order step strings (`order.*`) and the phase name "Post-purchase" are not in input-ux.md. The UX Architect must give them.
- The trace parts of AC-66 and AC-72 wait for OpenTelemetry (part 4).
