# ADR 0006: S2 checkout: reuse of the samples server, the host gate and the error bodies

- Status: Accepted (build decision under spec v1.1.2 section 15.2 and the build plan, slice S2).
- Date: 2026-10-24.
- Owner: Mark McCalla.

## Context

1. Spec T-05 and D11 tell us to reuse `rest/python/server` from `Universal-Commerce-Protocol/samples` at commit `e7c9c12`, and to fix the 8 defects of `02-design.md` 17.2.
2. The pinned spec text is UCP commit `9c9d6fc` (a local clone, not in this repository). The error rules are in `ucp@9c9d6fc:docs/specification/overview.md` lines 804 to 833 and 862 to 886, `checkout.md` lines 141 to 145 and 239 to 241, and `checkout-rest.md` lines 171 to 175, 1256 to 1268, 1275 to 1276 and 1319 to 1320.
3. Spec v1.1.2 section 15.2 gives the S2 rules for AC-14, T-95, P12, T-102 and T-103.

## Decision

1. **Sample reuse.** `business/src/ucp_sample_server/` is the sample copy with the patches in `business/UPSTREAM.md` (P1 to P10, P12, P13 and D6). `business_app.main` mounts only the sample `/checkout-sessions` routes. It does not mount the sample discovery and MCP routers (P11).
2. **Host gate.** `business_app.gate.Gate` is a pure ASGI middleware in front of the checkout routes. It does these checks in this order:
   1. CI faults only (`MODE=ci`): HTTP 429 or 503 with `Retry-After`.
   2. The `UCP-Agent` profile URL: it must be `https` with the path `/.well-known/ucp`, else HTTP 400 `invalid_profile_url` (AC-108). The fetch uses `netguard` (no redirect, address guard). A fetch failure gives 424 `profile_unreachable` or 422 `profile_malformed` (AC-10).
   3. The Platform version: it must be `2026-04-08`, else 422 `version_unsupported` (overview.md lines 2190 to 2202, AC-95).
   4. The RFC 9421 signature, with the sample verifier and the `signing_keys` of the Platform profile (T-04). Enforcement is on by default (P3). It is off only in gate G5.
   5. `Idempotency-Key` on POST and PUT. If it is missing: HTTP 400 `error_response` with code `invalid_request` (AC-48, T-31). UNVERIFIED: the pinned spec gives no code for this case.
      - Status (spec v1.1.3 section 15.3 row 7): CLOSED. The code `invalid_request` is demo policy. `error_code.json` line 5 permits freeform codes ("freeform codes are permitted").
   6. The idempotency store: if it does not answer, HTTP 503 `store_unavailable` with `Retry-After: 2`, and `/readyz` is red (AC-47).
   7. The composed schema (`contracts/composed`) for Create and Update. A failure gives HTTP 400 `error_response`, code `invalid_request` (AC-89, AC-104).
   8. The gate logs unknown root fields (for example `risk_signals`). P7 does not store them (AC-38, T-86).
3. **Error bodies (T-102).** A protocol error is `{code, content}` with HTTP 401, 403, 409, 422, 424, 429, 500 or 503, or HTTP 400 with `invalid_profile_url`, `digest_mismatch` or `algorithm_unsupported`. 422 and 424 can have `continue_url`. 429 and 503 send `Retry-After`. UNVERIFIED: no pinned schema defines this body.
   - Status (spec v1.1.3 section 15.3 row 5): CLOSED. The spec owner examined the 91 pinned JSON files. No pinned schema defines `{code, content}`. The body stays as T-102 gives it.
4. **Unknown checkout id.** The Business returns HTTP 200 `error_response` with code `not_found` and severity `unrecoverable`. Reason: `checkout.md` lines 141 to 145 (no resource gives `ucp.status` `error`), and the `checkout-rest.md` status table (lines 1256 to 1268) has no 404. `not_found` is an example in `types/error_code.json`.
5. **Sample exceptions.** The sample uses UPPERCASE codes. The host maps them to lowercase. An idempotency conflict and "checkout not modifiable" stay HTTP 409 (overview.md: 409 is idempotency key reuse). A sample HTTP 400 becomes `invalid_request` `error_response`. A status that is not in T-102 (for example 402) becomes 500. CLOSED in S4 by spec v1.1.4 T-105 (section 15.4) and patch P15: a failed payment on Complete is HTTP 200 with the checkout body. The status stays `ready_for_complete`. There is no `order`. There is exactly one message: `type` `error`, `code` `payment_failed`, `severity` `recoverable`. The content has no token and no PSP reason. The sample does not use 402 or 403 for a payment failure now. Sources at UCP `9c9d6fc`: checkout-rest.md lines 1275-1282, checkout.md lines 242 and 245-248, rest.openapi.json lines 301-317. See ADR 0010.
   - Status (spec v1.1.3 section 15.3 row 5): OPEN. The 402 and `payment_failed` handling stays UNVERIFIED. Product Manager Bot decides it before S4.
6. **AC-14 (v1.1.2).** A Create that makes a checkout returns 201 with `messages[]`. An Update returns 200. A Create that makes no checkout returns HTTP 200 `error_response`.
7. **Platform signatures.** The Platform signs each checkout request with its ES256 key (`ucp_sigs`, which loads the sample `ucp_signing.py`). The Platform profile publishes the public key in `signing_keys`. The private key is in `.run/keys/` (not in Git). CI uses a new ephemeral key for each process.
8. **Platform retries (AC-49, AC-50).** A retry sends the same body, `Idempotency-Key` and `Request-Id`. The client waits for `Retry-After` (cap 5 s) and stops after 3 tries.
9. **Not done in S2.** AC-R2 (reject a request that omits a field) is not done. The validator is not strict, because the root allows unknown fields (AC-38).
   - Update (spec v1.1.4 T-104, ACCEPTED by the project owner on 24 Oct 2026, spec v1.1.4 section 15.4 row 1): for `groups[].line_item_ids` and `groups[].options` only, the Business does not reject. It ignores the client value, never echoes it, and logs only the field path. Patch P14 does this. The no-echo part is necessary under each rule. Test: `tests/s2/contract/test_t104_group_no_echo.py`. AC-R2 for other `omit` fields is still not done (Business validator, slice S2 scope).

## Sources

- https://github.com/Universal-Commerce-Protocol/ucp/blob/9c9d6fce39ffa8bf7cb66309c378b79fb75b5382/docs/specification/overview.md
- https://github.com/Universal-Commerce-Protocol/ucp/blob/9c9d6fce39ffa8bf7cb66309c378b79fb75b5382/docs/specification/checkout.md
- https://github.com/Universal-Commerce-Protocol/ucp/blob/9c9d6fce39ffa8bf7cb66309c378b79fb75b5382/docs/specification/checkout-rest.md
- https://github.com/Universal-Commerce-Protocol/ucp/blob/9c9d6fce39ffa8bf7cb66309c378b79fb75b5382/source/schemas/shopping/types/error_code.json
- https://github.com/Universal-Commerce-Protocol/samples/tree/e7c9c124864108cbb35e5102beeac9cbef80a154/rest/python/server
- RFC 9421: https://www.rfc-editor.org/rfc/rfc9421
- Spec v1.1.3 section 15.3 (`03-spec.md`), rows 5, 7 and 8, and appendix T-104.
- https://github.com/Universal-Commerce-Protocol/ucp/blob/9c9d6fce39ffa8bf7cb66309c378b79fb75b5382/source/schemas/shopping/types/fulfillment_group.json lines 8, 19 and 25
- https://github.com/Universal-Commerce-Protocol/ucp/blob/9c9d6fce39ffa8bf7cb66309c378b79fb75b5382/docs/specification/fulfillment.md line 29
