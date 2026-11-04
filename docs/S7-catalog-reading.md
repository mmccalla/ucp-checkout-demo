# S7 v1 reading: catalog search and lookup (DM-11, AC-12, AC-08 part b)

- Status: reading and test plan only. No product code. No test code. Work stops here until Product Manager Bot confirms that AC-12 and AC-08 part (b) are complete and testable (instruction of 28 Oct 2026, 20:43 GMT).
- Date: 28 Oct 2026 (Europe/London).
- Author: executor for Mark McCalla.
- Branch: `s7`, from `d3f5864` (ADR 0016, section "Exception to the entry rule of S7").
- Scope: v1 only (search and lookup). The AI agent, MCP and cloud host phases are not in this file.

## 1. Sources

Pinned source: UCP version 2026-04-08, commit `9c9d6fc` (source tree extracted at `<pin folder>/ucp-9c9d6fce39ffa8bf7cb66309c378b79fb75b5382`). Each citation below is `<path>:<line>` in that tree. The hosted pages are:

- https://ucp.dev/2026-04-08/specification/catalog/ (file `ucp@9c9d6fc:docs/specification/catalog/index.md`)
- https://ucp.dev/2026-04-08/specification/catalog/search/ (`search.md`)
- https://ucp.dev/2026-04-08/specification/catalog/lookup/ (`lookup.md`)
- https://ucp.dev/2026-04-08/specification/catalog/rest/ (`rest.md`)
- https://ucp.dev/2026-04-08/specification/overview/ (`ucp@9c9d6fc:docs/specification/overview.md`)
- Schemas under `source/schemas/shopping/` and the REST description `source/services/shopping/rest.openapi.json`.

Project sources (spec `03-spec.md` v1.1.15, draft): DM-11 (line 197), AC-08 (lines 273 and 274, note at line 279), AC-12 (line 285), FR-05 (line 230), T-03 (line 678), T-26 (line 689), section 2.3 (lines 106 and 107). Build plan `04-build-plan.md`: section S7 (lines 116 to 128), AC rows at lines 151 and 155, flag 2 (line 132). The section 5 hash of the spec is `a96cddc5fc62f87cba0c3dc546b10d6769376daf33d8e3a3fdc1178c0f5e5feb` and it is unchanged.

The MCP binding (`catalog/mcp.md`) is not read for this file. It is for the later phase.

I did not use the output of another bot as a source. UNVERIFIED means that I could not confirm the item in the pinned source.

## 2. What the pinned source requires (short)

1. Two capabilities: `dev.ucp.shopping.catalog.search` and `dev.ucp.shopping.catalog.lookup` (`index.md:33` and `index.md:34`). The Lookup capability has two operations: Batch Lookup and Get Product (`lookup.md:29` and `lookup.md:30`).
2. REST endpoints (`rest.md:64` to `rest.md:66`): `POST /catalog/search`, `POST /catalog/lookup`, `POST /catalog/product`. When Lookup is advertised, both `/catalog/lookup` and `/catalog/product` MUST be available (`rest.md:659`).
3. The profile entry of each capability has `version`, `spec` and `schema` (`rest.md:45` to `rest.md:54`). The schema URLs end in `catalog_search.json` and `catalog_lookup.json`.
4. The catalog operations have no `Idempotency-Key` header. They have the required headers `Request-Id` and `UCP-Agent` (`rest.openapi.json:863`, `rest.openapi.json:882`, and the operation blocks at `rest.openapi.json:564`, `:608`, `:690`). The `idempotency_key` parameter (`rest.openapi.json:853`) is not in those blocks.
5. Business outcomes use HTTP 200 with the `ucp` envelope. Transport errors use HTTP 400, 401, 429 and 500 (`rest.md:587` to `rest.md:596`, `rest.md:598` to `rest.md:600`).

## 3. Reading table

Column "Testable as written": yes, partly, or no. "Gap or conflict" gives the reason. IDs G-01 and so on refer to section 4.

### 3.1 AC-12 (`03-spec.md:285`): Given search is active, When the buyer asks the agent for a product, Then the buyer sees product options with prices, and the selected item ID goes into checkout `line_items`

| Clause | Pinned file:line it depends on | Testable as written | Gap or conflict |
|---|---|---|---|
| A. "search is active" | `overview.md:747` to `overview.md:750` (intersection of capabilities, the Business MUST compute it). `rest.md:45` to `rest.md:49` (search declaration). Code that exists: `libs/ucp_core/profile_check.py` (`SEARCH`, `check`). | yes | Needs both profiles to declare search. The Business profiles `business/profile/demo.json` and `business/profile/ci.json` list no catalog capability today. See G-02 and G-12. |
| B. "the buyer asks the agent for a product" | `search.md:40` to `search.md:51` (a request needs at least one recognized input: `query`, `filters`, or an extension input). `04-build-plan.md:132` (v1 has no LLM). `03-spec.md` DM-01 (the own agent) and DM-11 ("Search works only with our own agent"). | **no** | v1 has no AI agent. "The agent" is not defined for v1. The only possible v1 actor is a search form in the Platform web page (build plan line 121, "`platform/` (search UI)"). PM must define what "the buyer asks the agent" means in v1. See G-01. |
| C. "the buyer sees product options with prices" | `product.json:7` to `product.json:13` (required: `id`, `title`, `description`, `price_range`, `variants`). `variant.json:7` to `variant.json:12` (required: `id`, `title`, `description`, `price`). `index.md:42` and `index.md:43` (price = amount in minor units + currency). `rest.md:660` (conformance item 2: valid `Price` objects). Schema-check: `catalog_search.json:35` to `catalog_search.json:38` (`ucp`, `products` required). | partly | "product options" is not defined. It can mean "the list of products" or "the option values (Size, Color) of a product" (`product_option.json`). The demo has 2 products and no options (`business/data/demo/products.csv`). Price display: the rule for the minor-unit conversion to GBP text is not in AC-12. The sample table has no description, no category and no currency (`business/src/ucp_sample_server/db.py:119` to `db.py:126`). See G-03, G-04, G-05. |
| D. "the selected item ID goes into checkout `line_items`" | `index.md:47` to `index.md:49` (the variant ID from catalog retrieval should match the item ID that checkout expects). `variant.json:16` ("Used as item.id in checkout"). `index.md:51` to `index.md:54` (catalog values are not a commitment; checkout is authoritative; do not reuse across sessions without re-validation). | partly | "Selected item ID" must be the variant ID (`variant.id`), not the product ID. The checkout code of the sample uses the products-table `id` (`demo_tshirt`, `demo_mug`) as `item.id`. So the variant ID of each catalog variant must equal that value. The spec does not say how the product ID is chosen. "Should match" (`index.md:48`) is a SHOULD, but AC-12 makes it a must for our demo. See G-06. |

### 3.2 AC-08 part (b) (`03-spec.md:274`): Given our Platform and our Business in slice S7, When negotiation is done, Then the panel also shows `dev.ucp.shopping.catalog.search` and `dev.ucp.shopping.catalog.lookup` active

| Clause | Pinned file:line | Testable as written | Gap or conflict |
|---|---|---|---|
| E. Business declares both capabilities | `rest.md:44` to `rest.md:55`. `capability.json` (profile entry shape, local copy in `contracts/ucp-schemas/`). | yes | The Business profile files must change. The local contract copies in `contracts/ucp-schemas/` do not hold the catalog schemas: 23 files are missing (G-07). The profile check in the Platform tests `spec` and `schema` bindings (`negotiation.binding_issues`, `profile_check.py`). It fetches no catalog schema, but UNVERIFIED: whether the profile schema check (`discovery/profile.json`) needs the files. |
| F. Platform declares both capabilities | `rest.md:45` to `rest.md:54`. `overview.md:747` to `overview.md:750`. Code: `platform/backend/src/platform_app/discovery.py:49` to `:57` (`_cat`). | yes | The live Platform profile today does not list catalog. Only the AC-09 case "lookup-only" adds it (`discovery.py:71` to `:73`). |
| G. "negotiation is done", capabilities active | `overview.md:333` to `overview.md:340` (negotiation and re-pruning). | yes | None. The result is the `active` list from `profile_check.check`. |
| H. "the panel shows" | Panel code `platform/web/checkout/app.js:210` and `:332` (shows `active` and the search notice). | yes | The UI test for part (a) exists. It must be extended for the two new names. |
| I. Link to AC-09 (not part of this scope, same area) | `lookup.md:21` to `lookup.md:23` (lookup works alone). | yes | AC-09 already passes in S1. S7 must not break it (G-12). |

### 3.3 DM-11 (`03-spec.md:197`)

| Clause | Pinned file:line | Testable as written | Gap or conflict |
|---|---|---|---|
| J. "Yes, built last, after payment works (S7)" | none (project order) | no (process rule) | Met by order of the slices. S7 started under the exception in ADR 0016. |
| K. "Search works only with our own agent" | The spec cites a live Google profile URL and `overview.md`. | no | UNVERIFIED. I did not read the live Google profile. It is not under the pin and can change. The pinned source says only that UCP turns on the capabilities that both sides declare (`overview.md:747` to `overview.md:750`). The statement about Google is a product fact, not a pinned fact. |
| L. Spec rows 106 and 107 (operations used) | `rest.md:64` to `rest.md:66`. | yes | The rows say "per the catalog search page" and "Get Product". The pinned REST paths are `POST /catalog/search` and `POST /catalog/product`. The rows are incomplete, not wrong (G-08). |

### 3.4 Pinned catalog rules that the AC rows do not name (needed for a testable S7)

| Rule | Pinned file:line | Testable | Gap or conflict |
|---|---|---|---|
| Search request has at least one recognized input; Business MUST validate; SHOULD reject empty or invalid requests | `search.md:40` to `search.md:51` | partly | The error code and the HTTP status for a rejected request are not defined at the pin (G-09). |
| Search with no match returns `products: []`, no messages, not an error | `index.md:260` to `index.md:271` | yes | None. |
| Filters: `categories` (OR), `price.min` and `price.max` in minor units, AND between filters | `search_filters.json:8` to `:15`, `price_filter.json:7` to `:16`, `index.md:71` to `index.md:75` | partly | Whether `min` and `max` include the bound is not stated (UNVERIFIED). The currency rule (filter in `context.currency`, convert if different, SHOULD) is open for a GBP-only shop (G-10). Demo products have no category (G-04). |
| Pagination: cursor; default limit 10; response `has_next_page` required; `cursor` required when `has_next_page` is true; clamp is allowed | `pagination.json:12` to `:21`, `:36` to `:49`, `search.md:56` to `search.md:60`, `rest.md:661` | partly | The demo has 2 products, so only `limit` = 1 gives a second page. The maximum page size is not in the pin (our own value, G-11). |
| Lookup: MUST support product ID and variant ID; MUST deduplicate; one product once | `lookup.md:51` to `lookup.md:59` | yes | None. |
| Lookup: each variant has `inputs` (`id`, `match` = `exact` or `featured`); variants without `inputs` MUST NOT appear | `lookup.md:61` to `lookup.md:72`, `lookup.md:83` to `lookup.md:88`, `catalog_lookup.json:14` to `:19`, `input_correlation.json:7` | yes | `match` is an open string with two well-known values. Only these two are used in tests. |
| Lookup: at least 10 identifiers; a maximum is allowed; above it HTTP 400 `request_too_large` | `lookup.md:76` to `lookup.md:79`, `rest.md:663` | yes | Our maximum is not set (G-11). The body shape of the 400 is not defined at the pin: `rest.openapi.json` lines 599 to 653 give only the `200` response for catalog operations (G-09). |
| Lookup with unknown ID: HTTP 200, fewer products, MAY have an info `not_found` message | `rest.md:662`, `rest.md:604` to `rest.md:635`, `index.md:315` to `index.md:336` | yes | The text "MAY" means a test can accept both with and without the message. The demo should state which one it does (G-13). |
| Get Product: single `product`; product ID or variant ID; variant ID is first in `variants`; `product.selected` required when the product has options | `lookup.md:118` to `lookup.md:136`, `lookup.md:164` to `lookup.md:168`, `catalog_lookup.json:87` to `:94`, `:153` to `:166` | yes | The demo products have no options, so `selected` and `preferences` are only testable as "ignored without error" (G-04). The text of `lookup.md:156` says each option name appears at most once. |
| Get Product, not found: HTTP 200, `ucp.status` `error`, message `not_found`, severity `unrecoverable` | `lookup.md:140` to `lookup.md:144`, `rest.md:549` to `rest.md:579` | yes | Conflicts with other lines (G-14). |
| Response envelope: `ucp` in every response; `capabilities` of the catalog response | `overview.md:751` to `overview.md:752`, `ucp.json:277` to `:292` | yes | None. |
| Headers on catalog calls: `Request-Id` and `UCP-Agent` required; no `Idempotency-Key` | `rest.openapi.json:863`, `:882`, `:564` to `:720` | yes | AC-07 covers only "any checkout request" (G-15). |
| Response prices are valid `Price` objects | `rest.md:660`, `price.json` | yes | None. |
| Media URL scheme: a Platform MAY refuse a non-HTTPS media URL | `index.md:150` to `index.md:151` | yes | Demo image URLs are HTTPS on `localhost:9443` (`products.csv`). |

## 4. Gaps and conflicts (for Product Manager Bot)

Each item has a proposed answer. A proposed answer is not a decision.

- **G-01 (AC-12 clause B, blocks "testable as written").** v1 has no AI agent, so "the buyer asks the agent" cannot run. Proposal: change the When to "the buyer submits a product search in the Platform page". The Platform sends `POST /catalog/search` to the Business. The AI-agent wording returns in the later phase.
- **G-02 (AC-08 part b).** The two Business profile files list no catalog capability. Proposal: add both capabilities to `demo.json`. For `ci.json`, ask PM. Reason: the pinned conformance suite (`016ecbc`) has no catalog test (the word "catalog" appears once, in a comment of `validation_test.py` line 309), so G5 cannot check catalog. A catalog entry in `ci.json` would make G5 test nothing new. UNVERIFIED: that G5 stays at 77 tests with 64 passed after the change. It needs a G5 run.
- **G-03 (AC-12 clause C).** "Product options" is ambiguous (list of products, or option values such as Size). Proposal: list of products, each with title, price (GBP text from minor units) and the variant ID. Option values are out of scope for v1 (the demo has none).
- **G-04 (data).** The sample products table has `id`, `title`, `price` (minor units) and `image_url` only (`db.py:119` to `db.py:126`). The pinned `product` needs `description`, `price_range` and at least one variant with a `description` (`product.json:7` to `:13`, `variant.json:7` to `:12`). There is no currency column (the shop uses one default currency; GBP by DM-16), no category, no option, no SKU. Proposal: a catalog layer in `business/src/business_app/` that builds the pinned shape from the table and one added data file with descriptions and categories. PM must approve the description and category text, or accept a fixed text. The 2 products stay.
- **G-05 (AC-12 clause C).** The AC does not say how a price is shown. Proposal: the page shows `£20.00` for 2000 minor units, from `price.amount` and `price.currency`. The Platform must not show a price that has no currency.
- **G-06 (AC-12 clause D).** Product ID and variant ID are different identifiers in the pin. Checkout needs the variant ID (`variant.json:16`). Proposal: variant ID = the existing checkout item ID (`demo_tshirt`, `demo_mug`). Product ID = a different value (for example `prod_demo_tshirt`). UNVERIFIED: whether the pin forbids that product ID and variant ID are equal. I found no such rule, but I did not search for it in every page. Proposal avoids the question.
- **G-07 (contracts).** 23 pinned schema files are not in `contracts/ucp-schemas/`: `shopping/catalog_lookup.json`, `shopping/catalog_search.json` and in `shopping/types/`: `category`, `description`, `detail_option_value`, `input_correlation`, `media`, `media_external_video`, `media_image`, `media_model_3d`, `media_source`, `media_video`, `option_value`, `pagination`, `price`, `price_filter`, `price_range`, `product`, `product_option`, `rating`, `search_filters`, `selected_option`, `variant`. S7 needs them for `ucp-schema validate` (build plan S7 "Test commands"). Adding them touches `pins/schema-manifest.sha256`, the fetch gate (AC-88), `ucp-schema lint --strict` (AC-106) and the pin count tests of S0. That change is in scope of S7 but it is a gate-relevant change. It needs its own commit and its own gate run.
  - Fact (probe in `/tmp`, no repository file): `ucp-schema validate <file> --op read --response --def search_response --schema <pin>/shopping/catalog_search.json --schema-local-base <pin> --schema-remote-base https://ucp.dev/schemas` gives `Valid` for a good payload and a message for a payload without `currency`. So the tool can validate catalog payloads with the pinned files. UNVERIFIED: the same for `lookup_response` and `get_product_response` (not run).
- **G-08 (spec text).** `03-spec.md` lines 106 and 107 do not name the REST paths. The owner of the spec can add `POST /catalog/search` and `POST /catalog/product` (`rest.md:64` to `rest.md:66`).
- **G-09 (undefined errors).** The pin does not define: the error for an empty search request (`search.md:47` to `search.md:51` says "appropriate error"); the body of a transport 400, including `request_too_large` (`rest.md:593`, `rest.md:663`); the OpenAPI file has only the `200` response for the catalog operations. Proposal: HTTP 400 with an error body that has `ucp.status` `error` and one message with `code` `invalid_request` (the existing checkout error shape, `error_response.json`, `AC-89`) for an empty request, and `request_too_large` for a long batch. These codes are our choice. Mark them PROPOSED in the spec. Tests must say that the body shape is our choice.
- **G-10 (price filter currency).** `index.md:71` to `index.md:75`: a filter is in `context.currency`; the Business SHOULD convert when the currency differs. The shop has GBP only. Proposal: if `context.currency` is not GBP, the Business ignores `context.currency` and applies the filter in GBP, and the response prices show `GBP`. UNVERIFIED whether this is the expected reading. The bound rule (inclusive or not) is not in the pin. Proposal: inclusive. PROPOSED.
- **G-11 (limits).** Pin: page size at least 10, batch at least 10 (SHOULD). Proposal: default page 10 (pin), maximum page 50, maximum batch 50. PROPOSED. A test with 51 identifiers gives `request_too_large`.
- **G-12 (do not break S1).** AC-09 test case "lookup-only" and `search_notice` tests exist. After S7 the live case has search and lookup active, and the lookup-only case must still show the notice. No conflict. Needs a regression test.
- **G-13 (not found in a batch).** The pin allows both. Proposal: the Business returns one info message `not_found` for each unknown ID, with the ID in `content` (the form of the pinned example, `rest.md:604` to `rest.md:635`). Test accepts that form only.
- **G-14 (conflicts inside the pinned pages).**
  - Code case: `index.md:235` shows `NOT_FOUND`, `OUT_OF_STOCK` (upper case). `index.md:327` and `rest.md:565` use `not_found` (lower case). Proposal: use the lower case, the form of the JSON examples and of the schema examples.
  - Severity: `index.md:244` says all catalog errors use `severity` `recoverable`. `rest.md:567` shows `unrecoverable` for a product that is not found. The schema allows both (`message_error.json`, `severity` enum). Proposal: follow `rest.md:567` for Get Product (it is the specific rule for that operation) and keep `recoverable` elsewhere. UNVERIFIED: which line the authors intend. If PM prefers, the test checks only that `severity` is in the enum.
  - Shape: the not-found example of Get Product (`rest.md:549` to `rest.md:579`) has no `product`, and `get_product_response` requires `product` (`catalog_lookup.json:155` to `:158`). The OpenAPI file solves it with `oneOf` of `get_product_response` and `error_response` (`rest.openapi.json:1019` to `:1023`). So the not-found body must validate against `error_response.json` (it needs `ucp`, `messages` with at least one item, no other property, `error_response.json:7` to `:21`). No conflict for REST, but the schema for the test is `error_response`, not `get_product_response`.
- **G-15 (headers).** AC-07 covers checkout requests only. The pin requires `Request-Id` and `UCP-Agent` also for catalog calls. Proposal: PM extends AC-07 to catalog calls, or adds one AC clause for it. I did not read `business/src/business_app/gate.py` for this file, so UNVERIFIED how the Business gate treats non-checkout paths today (signature, `UCP-Agent`, `Request-Id`). That is a code reading for the test phase.
- **G-16 (Lookup needs Get Product).** AC-08 part (b) and the build plan name "search and lookup". The pin requires `POST /catalog/product` when Lookup is advertised (`rest.md:659`). Proposal: PM confirms that Get Product is in S7 v1 scope. Without it the Business does not conform to the pinned REST binding.
- **G-17 (security and AC-54).** Catalog calls carry no payment data, so AC-54 does not apply to them in v1. The LLM part of AC-54 stays in the later phase (build plan flag 2). No gap for v1.
- **G-18 (DM-26).** The new endpoints are on the same Business process, bound to 127.0.0.1 only. No new port. The Platform calls them through the existing client (TLS through Caddy). UNVERIFIED: whether the catalog call from the Platform page should use the same signed client as checkout. See G-15.

## 5. Verdict for Product Manager Bot

- AC-12: NOT testable as written. Blocking items: G-01 (agent), G-03 (options), G-06 (item ID), G-04 (data for a valid `product`). Other items (G-05) are small.
- AC-08 part (b): testable as written, after G-02 (which profile files), and with the schema files of G-07 for the schema checks.
- Needed rulings: G-01, G-02, G-03, G-04, G-06, G-09, G-10, G-11, G-14, G-15, G-16. The rest are notes.

## 6. Test plan (names only; no code; written after PM confirms)

Folder: `tests/s7/`. Names follow the existing `tests/s6/` style. Marks: `unit` (no service), `contract` (Business only), `e2e` (Platform page).

### 6.1 Profile and negotiation (AC-08 part b)

- `tests/s7/unit/test_profiles.py::test_business_profile_declares_catalog_search_and_lookup`
- `tests/s7/unit/test_profiles.py::test_platform_profile_declares_catalog_search_and_lookup`
- `tests/s7/unit/test_profiles.py::test_catalog_entries_bind_spec_and_schema_hosts` (AC-05 rule for the new names)
- `tests/s7/unit/test_negotiation_catalog.py::test_search_and_lookup_active_when_both_declare`
- `tests/s7/unit/test_negotiation_catalog.py::test_lookup_only_platform_keeps_search_notice` (AC-09 regression, G-12)
- `tests/s7/unit/test_negotiation_catalog.py::test_business_without_catalog_excludes_both`
- `tests/s7/contract/test_live_discovery_catalog.py::test_live_panel_data_lists_search_and_lookup_active`
- `tests/s7/e2e/test_panel_catalog.py::test_panel_shows_search_and_lookup_active` (AC-08 part b, UI)

### 6.2 Schemas and contracts (G-07)

- `tests/s7/unit/test_contracts_catalog.py::test_catalog_schema_files_match_manifest`
- `tests/s7/unit/test_contracts_catalog.py::test_catalog_schemas_lint_strict_clean`
- `tests/s7/unit/test_catalog_payloads_validate.py::test_search_response_valid_for_ucp_schema` (and `lookup_response`, `get_product_response`, `error_response`)
- `tests/s7/unit/test_catalog_payloads_validate.py::test_response_without_currency_is_invalid`

### 6.3 Search (`POST /catalog/search`)

- `tests/s7/contract/test_search.py::test_query_returns_products_with_price_and_currency`
- `tests/s7/contract/test_search.py::test_product_has_required_fields_and_at_least_one_variant`
- `tests/s7/contract/test_search.py::test_variant_id_equals_checkout_item_id`
- `tests/s7/contract/test_search.py::test_no_match_returns_empty_products_without_messages`
- `tests/s7/contract/test_search.py::test_empty_request_is_rejected` (G-09)
- `tests/s7/contract/test_search.py::test_filter_only_request_browses`
- `tests/s7/contract/test_search.py::test_category_filter_or_logic`
- `tests/s7/contract/test_search.py::test_price_filter_min_max_inclusive_minor_units` (G-10)
- `tests/s7/contract/test_search.py::test_non_gbp_context_currency_is_handled` (G-10)
- `tests/s7/contract/test_search.py::test_unknown_filter_property_is_accepted`
- `tests/s7/contract/test_search.py::test_pagination_limit_one_gives_cursor_and_next_page`
- `tests/s7/contract/test_search.py::test_pagination_last_page_has_next_page_false`
- `tests/s7/contract/test_search.py::test_limit_above_maximum_is_clamped_without_error`
- `tests/s7/contract/test_search.py::test_default_page_size_is_ten`
- `tests/s7/contract/test_search.py::test_response_has_ucp_envelope_with_search_capability`
- `tests/s7/contract/test_search.py::test_request_without_ucp_agent_or_request_id_is_rejected` (G-15)
- `tests/s7/contract/test_search.py::test_response_prices_match_the_checkout_prices`

### 6.4 Batch lookup (`POST /catalog/lookup`)

- `tests/s7/contract/test_lookup.py::test_lookup_by_variant_id_gives_exact_match`
- `tests/s7/contract/test_lookup.py::test_lookup_by_product_id_gives_featured_match`
- `tests/s7/contract/test_lookup.py::test_every_returned_variant_has_inputs`
- `tests/s7/contract/test_lookup.py::test_duplicate_ids_are_deduplicated`
- `tests/s7/contract/test_lookup.py::test_product_id_and_its_variant_id_return_product_once_with_two_inputs`
- `tests/s7/contract/test_lookup.py::test_unknown_id_gives_200_and_info_not_found`
- `tests/s7/contract/test_lookup.py::test_all_unknown_gives_empty_products`
- `tests/s7/contract/test_lookup.py::test_batch_of_ten_is_accepted`
- `tests/s7/contract/test_lookup.py::test_batch_above_maximum_gives_400_request_too_large` (G-11)
- `tests/s7/contract/test_lookup.py::test_empty_ids_array_is_rejected` (`minItems` 1)
- `tests/s7/contract/test_lookup.py::test_price_filter_excludes_product_with_no_variant_in_range`
- `tests/s7/contract/test_lookup.py::test_response_is_valid_for_lookup_response_schema`

### 6.5 Get Product (`POST /catalog/product`)

- `tests/s7/contract/test_product.py::test_product_id_returns_single_product_object`
- `tests/s7/contract/test_product.py::test_variant_id_puts_that_variant_first`
- `tests/s7/contract/test_product.py::test_unknown_id_gives_200_status_error_not_found` (G-14)
- `tests/s7/contract/test_product.py::test_unknown_id_body_is_valid_error_response`
- `tests/s7/contract/test_product.py::test_selected_and_preferences_are_accepted_for_product_without_options` (G-04)
- `tests/s7/contract/test_product.py::test_response_is_valid_for_get_product_response_schema`
- `tests/s7/contract/test_endpoints.py::test_lookup_advertised_means_both_lookup_and_product_exist` (G-16)

### 6.6 End to end (AC-12)

- `tests/s7/e2e/test_search_to_checkout.py::test_search_shows_products_with_prices` (AC-12 clause C)
- `tests/s7/e2e/test_search_to_checkout.py::test_selected_variant_id_is_in_checkout_line_items` (AC-12 clause D)
- `tests/s7/e2e/test_search_to_checkout.py::test_checkout_total_agrees_with_catalog_price`
- `tests/s7/e2e/test_search_to_checkout.py::test_search_hidden_when_search_not_active` (AC-09 link)
- `tests/s7/e2e/test_search_to_checkout.py::test_search_form_is_keyboard_usable` (the checks of the S3 page, UX)

### 6.7 Gates and containment

- `tests/s7/unit/test_catalog_listens_on_loopback_only.py::test_no_new_listener_address` (DM-26)
- G1 to G8 run on each commit as before. G5 is run once after the profile change to confirm 77 tests, 64 passed (G-02).

## 7. Open points of this file

- UNVERIFIED: the live Google profile (DM-11 clause K).
- UNVERIFIED: that no pinned rule forbids equal product ID and variant ID (G-06).
- UNVERIFIED: price-filter bound rule and the reading of `context.currency` for a GBP-only shop (G-10).
- UNVERIFIED: which of `recoverable` and `unrecoverable` the authors intend for a missing product (G-14).
- UNVERIFIED: the Business gate behavior for catalog paths (G-15, `gate.py` not read for this task).
- UNVERIFIED: that G5 does not change after the profile change (G-02).
