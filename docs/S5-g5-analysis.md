# S5: analysis of the G5 result (conformance suite 016ecbc)

Status: record of a failing gate under test. G5 is not in the `run_all.sh` slice list. This file does not change the suite and does not relax a spec rule.

Data: local run records (not in this repository) (gate run on commit d85af6a): 77 tests, 1 pass, 69 fail, 7 skip.
Suite: https://github.com/Universal-Commerce-Protocol/conformance at commit 016ecbc22240affdec4429a60d539bedd04ab51b. UCP pin: 2026-04-08 at 9c9d6fc. Google Pay handler: 2026-01-23.

Class codes: (a) defect or gap in our Business. (b) mismatch between the suite and the spec or schema version. (c) decision for Mark or PM.

## Failures

| Group | Tests | Cause | Pinned rule | Class |
|---|---|---|---|---|
| A | 65 | Create returns 422 `profile_malformed`: `$.ucp: 'services' is a required property; $.ucp: 'payment_handlers' is a required property`. The suite mock agent profile (`shopping-agent-test.json`) has only `ucp.version` and `ucp.capabilities`. | `contracts/ucp-schemas/ucp.json` lines 179 to 190 (`platform_schema` requires `services` and `payment_handlers`). `ucp@9c9d6fc:docs/specification/overview.md` at 9c9d6fc lines 354 to 358: both are required and "MUST be present even when empty". | (b) and (c). The Business applies the pinned rule correctly. A pass needs a CI-only relaxation of a schema rule. I did not add it. |
| B | 3 (`ValidationTest.test_out_of_stock`, `test_product_not_found`, `test_structured_error_messages`) | The test needs a Create to work first. It gets the group A 422 body, which has no `detail` or `messages`. | Same as group A. | Follows from A. With the relaxation in a scratch copy, the 3 tests passed. |
| C | 1 (`ProtocolTest.test_version_negotiation`) | The test sends `UCP-Agent: profile="..."`. This is not a URL. The Business returns 400 `invalid_profile_url`. | `overview.md` at 9c9d6fc lines 1176 and 1222: profiles "MUST be served over HTTPS" and implementations "MUST reject URLs not served over HTTPS". AC-108 in `03-spec.md`. | (b) and (c). To pass, the Business must accept a profile that is not a URL. That breaks a MUST rule, so I stopped this item. |
| D | 26 more tests fail after A is removed in a scratch copy (all that call Complete: lifecycle, order, webhook, simulate-shipping, idempotency, card, AP2, binding) | Complete returns 400 `invalid_request` at `$.payment.instruments[0].credential.type`. The suite sends handler `mock_payment_handler` and `credential: {"type":"token","token":...}`. The Business checks every instrument against the `com.google.pay` schema. That schema allows only `DIRECT` or `PAYMENT_GATEWAY` for `credential.type`. | `contracts/gpay-handler/card_payment_instrument.json` lines 38 to 52 (handler version 2026-01-23). `03-spec.md` T-93 item 1: the CI profile must declare `dev.mock.payment_handler` (`id` `mock_payment_handler`). `overview.md` at 9c9d6fc line 1804: validate `handler_id` against the advertised set. | (a) and (c). In `MODE=ci` the Business does not declare the mock handler and has no schema for its instrument (`git grep dev.mock` finds nothing in `business/` and `libs/`). T-93 asks for it. The pinned UCP text gives no schema for a mock handler (T-93), so the schema is a decision for PM. |
| E | 2 more after A is removed (`ValidationTest.test_complete_without_fulfillment`, `test_payment_failure`) | Both send a Complete with the same payment body. They get the group D 400, not the expected code. | Same as group D. | Follows from D. UNVERIFIED until D is solved. |

Scratch result with only the group A relaxation: 41 pass, 29 fail (26 D, 1 C, 2 E), 7 skip. The scratch copy is not committed.

## Skips

| Tests | Cause | Rule | Class |
|---|---|---|---|
| 6 `discount_test.DiscountTest.*` | The Business does not advertise `dev.ucp.shopping.discount`. The test skips itself in `setUp`. | `03-spec.md` section 1.2 (Discount is out of scope) and T-94 (list them in `approved-skips.txt`, reason "discount out of scope (section 1.2)"). T-94 says "Approved with the spec". The spec is still a draft (v1.1.8). | (c) Mark must approve. `conformance/approved-skips.txt` is empty. |
| 1 `protocol_test.ProtocolTest.test_discovery_urls` | `@unittest.skip("Schemas not yet published on remote ucp.dev domain")` at `protocol_test.py` line 101. | T-94 does not list it. | (b) and (c). Add it to the approved list or not. Mark must decide. |

## Gate rules that apply (T-91, AC-119, AC-120)

- 7 unapproved skips fail the gate (AC-119).
- The count is 77 (AC-120). It is correct.
- A run with no failure and no skip needs groups A to E solved and Mark's approval for the skips.

## Open question: DM-26 and the 0.0.0.0 helper servers

The suite starts two helper servers on `0.0.0.0`: `integration_test_utils.py` lines 273 and 361 (`host="0.0.0.0"`). DM-26 says all services bind to 127.0.0.1 only.
`conformance/gate.py` runs the Business and the suite inside `unshare --map-root-user --net` with only the loopback interface up. The helper servers can then reach no other host.
I do not say this is compliant with DM-26. The suite code binds to `0.0.0.0`, and I did not change the suite. Question for Mark: is a private network namespace an accepted containment for this deviation, or must G5 not run until the suite binds to 127.0.0.1?
UNVERIFIED: that `unshare --map-root-user --net` works in every CI host (it works on this box).

## Other deviations kept in `MODE=ci` only (T-93)

- The Business accepts `http://localhost:<port>/profiles/shopping-agent.json` as the profile URL. This conflicts with `overview.md` line 1222 ("MUST reject URLs not served over HTTPS"). T-93 allows "test profile URLs" in CI mode. AC-108 still holds: with `http`, any other path gets 400 (unit test `tests/s5/unit/test_ci_seams.py`).
- `required_capabilities` in `conformance/input/conformance_input.json` is limited to checkout, order and fulfillment. PM must confirm.

## Decisions of the project owner (28 Oct 2026)

- Group C (no http profile URL) is REJECTED. The suite and the Business are not changed for it. The cases stay as failures and G5 stays out of every slice (expected FAIL).
- DM-26 containment (`unshare --map-root-user --net`) is ACCEPTED as CI-only, with 2 conditions. Both are built in `conformance/gate.py`: (1) G5 fails with exit 2 if `unshare` is not available or does not work; (2) G5 checks that the namespace is new and has only `lo`, before the Business starts (`netns-check.txt` in the report directory). Tests: `tests/s5/unit/test_g5_containment.py`.
- Finding: inside `unshare`, `/sys/class/net` lists the host interfaces (sysfs keeps the namespace of its mounter). The check reads `/proc/net/dev`, which shows the namespace of the reader.

## G5 after the rulings of 28 Oct 2026 (spec v1.1.12: T-94, T-110 to T-115)

Run: local run records (not in this repository) on the work tree after T-110 to T-115 (the commit that holds this text). The count is real: **77 tests, 64 pass, 6 fail, 7 skip.** G5 still FAILS (5 failures are not in `approved-failures.txt`). G5 is in no slice, so no gate blocks. The 7 skips are the 7 entries of `approved-skips.txt` (6 `DiscountTest` and `protocol_test.ProtocolTest.test_discovery_urls`).

### What changed

| Row | Change | Where |
|---|---|---|
| T-110 | A valid platform profile for the suite. A pytest plugin replaces the profile template in memory after the suite builds `AgentProfileServer`. No file of the suite changes. G5 checks that the suite HEAD is the pin and that no tracked file changed. | `conformance/input/shopping-agent-ci-profile.json`, `conformance/s5_profile.py`, `conformance/gate.py` (`suite_problems`) |
| T-111 | `MODE=ci` only: an instrument with `handler_id` `mock_payment_handler` is checked with `allOf` of the pinned `card_payment_instrument.json` and the pinned `token_credential.json`. `MODE=demo` refuses that handler (AC-32, T-93). `demo.json` has no change. | `conformance/schemas/ci_mock_payment_instrument.json`, `gate.py` `_check_instruments`, `SchemaRegistry.validate_document` |
| T-112 | `required_capabilities` has the 3 capabilities of `ci.json`. A test compares the two lists. | `tests/s5/unit/test_t110_t111_t112.py` |
| T-113 | `approved-failures.txt` has 1 entry: `protocol_test.ProtocolTest.test_version_negotiation`. G5 fails on an unlisted failure and on a listed test that passes. | `conformance/gate.py` `evaluate` |
| T-94 | `approved-skips.txt` has 7 entries. | `conformance/approved-skips.txt` |
| T-114 | The profile URL exception: exact pattern, with the guards port, `MODE=ci`, namespace and switch. | `platform_profiles.py`, `main.py`, `libs/ucp_core/netns.py` |
| T-115 | The webhook transport refuses `http` (code `blocked_non_https`). `MODE=ci` allows only the exact suite webhook URL, with the same guards. | `order_events.py`, `main.py` |
| Webhook `UCP-Agent` | The profile URL of the Business in a webhook must be HTTPS (`signatures.md` lines 622 to 625 at `9c9d6fc`). See "Finding" below. | `main.py` `webhook_profile_url`, `gate.py` |

### Finding: the webhook `UCP-Agent` in G5

Before this change, `sample_config.WEBHOOK_PROFILE_URL` was `origin + "/.well-known/ucp"`. In the G5 run `origin` is `BUSINESS_ORIGIN=http://127.0.0.1:18201` (`gate.py`). So the header held an `http` URL. That breaks `signatures.md` lines 622 to 625 ("MUST be a quoted string containing an HTTPS URL", "Reject non-HTTPS URLs"). The Business now refuses to start if this URL is not HTTPS, in each mode. In G5 the launcher gives `BUSINESS_WEBHOOK_PROFILE_URL=https://localhost:9443/.well-known/ucp` (the real HTTPS profile URL of the demo). UNVERIFIED: that the suite does not fetch this URL. No suite test failed because of it in `g5-r3`. Repo `main` at `5cb4d9a` has the same line with a default HTTPS origin, so it is not wrong there unless `BUSINESS_ORIGIN` is `http`.

### Remaining failures (G5 FAILS)

| Test | Result | Cause (found in the run `g5-r3`) | Status |
|---|---|---|---|
| `protocol_test.ProtocolTest.test_version_negotiation` | fails, 400 `invalid_profile_url` | The test sends `profile="..."`, which is not a URL. T-113 lists it. T-114 does not change it (the exception is for the exact suite URL only). | Approved failure (T-113) |
| `card_credential_test.CardCredentialTest.test_card_credential_payment` | fails, 400 at `$.payment.instruments[0].credential` | The suite sends `credential.type` `card` (a raw card). The T-111 schema requires the pinned `token_credential.json`. | NOT RULED. New. Hidden before by group D. |
| `order_test.OrderTest.test_order_update`, `test_order_adjustments`, `invalid_input_test.InvalidInputTest.test_invalid_adjustment_status`, `test_malformed_adjustment_payload` | fail, 405 | The suite sends `PUT /orders/{id}`. The Business has no such route. | NOT RULED. New. Hidden before by group D. |

I did not add a rule for these 5 tests. A rule needs a ruling.

### Other notes

- `business/profile/ci.json` has the spec URL `https://ucp.dev/2026-04-08/schemas/mock_payment_handler/spec` for `mock_payment_handler`. On 28 Oct 2026 it gives 404. The value comes from the upstream sample. I found no verified replacement. The value stays. UNVERIFIED. `ci.json` is a golden file (AC-107).
- Main still accepts `http` webhook URLs (`order_events.py` at `5cb4d9a`). Main is frozen. The change is on `s5-s6` only.

## G5 approved failures: 6 entries (ruling of the project owner, 28 Oct 2026)

The list `conformance/approved-failures.txt` has 6 entries. The spec text (v1.1.13: T-113, AC-114, AC-119, AC-120) still says "one entry". The spec owner must update it. UNVERIFIED: spec v1.1.14 was not on disk when I wrote this. I followed the ruling.

| Test | Cause | Source (pin `9c9d6fc`, checked in `<pin folder>/ucp-9c9d6fce39ffa8bf7cb66309c378b79fb75b5382`) |
| --- | --- | --- |
| `protocol_test.ProtocolTest.test_version_negotiation` | the value `profile="..."` is not a URL | `overview.md` line 806 |
| `card_credential_test.CardCredentialTest.test_card_credential_payment` | the test sends a raw card (credential type `card`) | `source/schemas/shopping/types/card_credential.json` line 5: "This credential type MUST NOT be used for checkout, only with payment handlers that tokenize or encrypt credentials." (line checked) |
| `order_test.OrderTest.test_order_update` | `PUT /orders/{id}` | `ucp@9c9d6fc:docs/specification/order.md` line 302 and `order-rest.md` line 77: the only operation is Get Order, `GET /orders/{id}`. Checked: `order.md` and `order-rest.md` have no `PUT` |
| `order_test.OrderTest.test_order_adjustments` | same | same |
| `invalid_input_test.InvalidInputTest.test_invalid_adjustment_status` | same | same |
| `invalid_input_test.InvalidInputTest.test_malformed_adjustment_payload` | same | same |

I built no card credential path and no order update.

## Start-up check of the suite ports (ruling of the project owner, 28 Oct 2026)

In `MODE=ci`, inside the T-109 namespace, with the switch on, a port value that is not a number from 1 to 65535 stops the start of the Business. The error is `ConfigurationError`: "configuration error: <VARIABLE> must be a port number from 1 to 65535, the value is '<value>'. The Business does not start." This applies to `BUSINESS_CI_SUITE_PROFILE_PORT` and `BUSINESS_CI_SUITE_WEBHOOK_PORT`. Outside the namespace (or with the switch off or MODE not `ci`) the port is not read and the Business starts (T-115 clause 7). Limit: the Business cannot know the real port of the suite. It checks only that the value is a valid port. Tests: `test_webhook_bad_port_fails_startup` (T-115 clause 9), `test_profile_bad_port_fails_startup` (T-114 clause 5), each with 7 bad values, and `test_webhook_switch_outside_netns_does_not_crash`.
