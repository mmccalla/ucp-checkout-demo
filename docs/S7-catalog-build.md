# S7 v1: catalog build notes (Business endpoints and Platform client)

Status: built on branch `s7`. Spec: `03-spec.md` v1.1.18 (AC-08b, AC-12, U-50 to U-57, section 7.12).
Spec sha256: `46fc4418016f1d175975c4e1918e0237a28dd17a0a2d33480de0b2c8b135cf49`. Section 5 is unchanged.
Source: UCP 2026-04-08 at 9c9d6fc (`ucp@9c9d6fc:docs/specification/catalog/`, `source/schemas/shopping/`).
Read first: `docs/S7-catalog-reading.md` (the gaps G-01 to G-18).

## What is built

| Part | File | Notes |
|---|---|---|
| Business endpoints | `business/src/business_app/catalog.py` | `POST /catalog/search`, `/catalog/lookup`, `/catalog/product` (rest.md:64-66, 659). |
| Business data | `business/data/catalog/demo.json` | Demo products. The variant id is the checkout item id (AC-12.8). |
| Business Gate | `business/src/business_app/gate.py` | Catalog paths need no signature and no `Idempotency-Key` (AC-12.1). |
| Business profiles | `business/profile/demo.json`, `ci.json` | Add `dev.ucp.shopping.catalog.search` and `.lookup` (AC-08b-1). |
| Platform profile | `platform/backend/profile/platform.json` | Same two names. |
| Platform client | `platform/backend/src/platform_app/catalog_client.py` | `search`, `lookup`, `product`. Checks each answer with the pinned schemas. |
| Panel case | `platform/backend/src/platform_app/discovery.py` | Case `lookup-only` removes search from the Platform copy (AC-08b-4). |
| Schemas | `contracts/ucp-schemas/shopping/catalog_*.json`, `types/*` | 23 files. Hash lines in `pins/schema-manifest.sha256`. |

## Precedence where the pin disagrees with itself

Schema first, normative prose second, examples third (ruling of the project owner, 28 Oct 2026).

| Point | Result | Source |
|---|---|---|
| `ucp.capabilities` is an object, not an array | Object keyed by capability name. | `ucp.json:277-292` |
| Severity of a catalog error | `recoverable`. | `catalog/index.md:244`. `rest.md:567` shows `unrecoverable` (example, lower rank). |
| Product answer has `description` and `variants` | Both present. | `types/product.json` |
| Unknown id in Get Product | HTTP 200, `ucp.status` "error", message `not_found`, no `product`. | `rest.md:598-600`, `rest.openapi.json:1019-1024` |

## Platform screen SC2a and the product detail

Files: `platform/web/checkout/app.js`, `app.css`, `platform/backend/src/platform_app/main.py`
(`/api/catalog/search`, `/api/catalog/product`, `checkout_config.catalog_ms` = 10000).

| Design choice | Reason |
|---|---|
| A new search replaces the list only when it succeeds. The old list stays while the call is open and after an error. | AC-130 wins over the older design text ST22. |
| The screen title is an h1 (`#screen-title`). The design says level 2. | The page has one h1 for every screen. This is a deviation from UX-4.2a. |
| With search active and lookup not active, View details opens the detail from the search card. No Get Product call is sent. | AC-12.10. |
| The Platform sends no lookup or product call when lookup is not active. | A demo rule. See UNVERIFIED. |
| A product with no `availability` field gets an enabled Add button. | U-52. |
| The harness default removes the catalog capabilities from the Platform profile. Tests of S7 opt in. | The tests of S1 to S6 run as before. |

## Conflict: design F25 and the spec

02-design.md F25 says "unrecoverable" for a product that is not found. AC-12.15 and U-50 say
`recoverable`. The spec wins. The design document is not changed. The pin agrees with the spec
(`catalog/index.md:244`).

## Tests (command: `uv run pytest tests/s7 -q`)

The browser tests use the Playwright 1.56.0 sync API with a browser fixture at module scope (T-120).
The 10 second tests use `page.clock`. They do not wait 10 real seconds.

| AC | Test |
|---|---|
| AC-08b-1 to AC-08b-5 | `tests/s7/contract/test_ac08b_catalog_profiles.py` |
| AC-08b-6 (T-119) | `tests/s7/contract/test_ac08b6_inactive_capability.py`, `tests/s7/contract/test_platform_catalog_api.py`, and the page in `tests/s7/e2e/test_search_ui.py::test_ac132_*` |
| AC-12.1 to AC-12.15 (data) | `tests/s7/contract/test_ac12_search.py`, `test_ac12_lookup_product.py` |
| AC-123, AC-124, AC-125 | `tests/s7/e2e/test_search_ui.py::test_ac123_*`, `test_ac124_*`, `test_ac125_*` |
| AC-126, AC-127, AC-12.3 | `test_ac126_*`, `test_ac127_*`, `test_ac12_3_*` |
| AC-128, AC-129 | `test_ac128_ac129_show_more_results` |
| AC-130 | `test_ac130_no_answer_in_10_s` |
| AC-131 | `test_ac131_network_error_and_protocol_error` |
| AC-132, AC-12.10 | `test_ac132_*`, `test_ac12_10_*` (two tests) |
| AC-133, AC-12.8 | `test_ac133_view_details_calls_get_product` |
| AC-134, AC-12.9 | `test_ac134_*` (three tests) |
| AC-135, AC-12.15 | `test_ac135_no_answer_and_not_found`, `test_ac12_15_*`, `test_detail_protocol_error_buttons` |
| AC-136 | `test_ac136_inspector_rows_and_replay` |
| AC-137 | `test_ac137_keyboard_order_and_back_to_results` |
| AC-138 | `test_ac138_reflow_and_target_size_at_320` |
| UX-7.6 SC 1.1.1 (image text alternative) | `test_ux76_image_has_alt_text_or_is_decorative` |
| Schema files | `tests/s7/unit/test_contracts_catalog.py`, `tests/s1/unit/test_registry.py` |

## Not built

- The AI agent, MCP and the cloud host.

## UNVERIFIED (design choices, not from the pin)

- Page maximum 20 and batch maximum 10 (U-53). The pin says at least 10 for a batch (lookup.md:76-79).
- The body of HTTP 400 (`invalid_request`, `request_too_large`): the pin has no schema for it (G-09).
- Price filter bounds are inclusive.
- `context.currency` is not converted. The shop trades in GBP only.
- The code `not_found` for Get Product: no normative text names it.
- T-119 and U-54: the pin gives the rule for checkout (overview.md:789-810, 2205-2208). The use for the catalog is an inference.
- U-52 (a missing `availability` enables Add), U-55, U-56 and U-57: design choices of the spec, not from the pin.
- AC-136 says that M1 to M13 keep their IDs. The page does not show the IDs M1 to M13 in the DOM. No test reads them. Only M1a and M1b have an ID in the page (`data-mid`).
- The Platform guard for lookup and product when lookup is not active: a demo rule, not from the pin.
- The text of `search.hint` (UX-8.2 table) and the inspector text `inspector.announce.product`.
- The count text in the design has two forms. The page follows the copy table.
- T-120 is PROPOSED in the spec text. The user accepted it.
- An empty search (no query, no filter) gives HTTP 400 (T-118 ACCEPTED).

## Finding: ucp-schema and two root capabilities

`ucp-schema resolve` stops with "multiple root capabilities found" if the profile lists
checkout and the two catalog capabilities. `tools/contracts/compose.py` leaves the catalog names
out of the checkout composition. The composed files do not change.

## Gate set

`tools/gates/gates.toml` has a slice `S7` (current_slice). It has the same gates as S6. G3 also
runs `tests/s7/unit`. G4 also runs `tests/s7/contract`. Before this change the gates did not
run `tests/s7`. G7 also runs `tests/s7/e2e`. The evidence of the s7 commits is in local run records (not in this repository) (the wrapper
script has the S6 path).

## Defects

This list is new. No S7 defect list existed before. The ID scheme is `DEF-S7-NN`.

### DEF-S7-01: page stall of more than 5 s in `test_ac23_per_payment_limit`

- Test: `tests/s3/e2e/test_g7_flow.py::test_ac23_per_payment_limit`. It failed one time, in a run of the CI repro on tip `34c7a8f`.
- Symptom: a text check on `#screen-title` waited 5 s and failed. The call log has `2 x locator resolved`. The Business log has `POST /checkout-sessions` with `201 Created` and then nothing.
- Result of the RCA: class D. No natural run failed (RCA 2). A fault injection gives the same call log: a renderer stop of 7000 ms fails, a stop of 3000 ms passes. A slow server gives `9 x`, not `2 x`.
  The page, or its link to the Playwright driver, did not answer for more than 5 s.
- Cause of the real stall: source UNVERIFIED. No defect in the test or in the application is proven.
- Evidence: `<evidence folder>/ci-fix/rca/rca2/` (on the box, not in git). File `NOTES-rca2.md`, sha256 `ba04f46b76303087618c62d9ee69a581c03e2da8cb7a237ab66fcc9645d484bd`.
- Status: open. The test, the timeout and the retry are not changed.
- Next step: the failure capture (`docs/S7-ci-failure-capture.md`). If the test fails again, the capture gives the Playwright trace, `vmstat -t 1`, `ps` and `dmesg`.
