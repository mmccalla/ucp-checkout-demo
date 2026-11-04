# ADR 0002: S1 shared core, schema closure, profile validation (AC-106)

- Status: Accepted. Date: 2026-10-24. Rebuilt on 2026-10-24 after the loss of the old repository (ADR 0004). The old commit of this ADR was `6c0ec7b`.
- Decisions by the project owner on 2026-10-24 are in sections 3 to 7.

## 1. Shared package `libs/ucp_core`

The Business and the Platform use the same code for these items:

- `schema_registry`: the offline JSON Schema registry (draft 2020-12, `jsonschema` 4.26.0, `referencing` 0.37.0).
- `netguard`: the profile fetch. It uses HTTPS only, follows no redirect and bounds the body size. It checks each resolved address before the connection (AC-122).
- `negotiation`: the capability intersection and the spec URL binding.
- `gpay_config`: the `com.google.pay` declaration checks and the map to the Google Pay Web names.
- `profile_check`: the profile checks for the discovery panel.
- `jwk`: the ES256 key and the RFC 7638 thumbprint.

This package is a change to the engineering layout. It prevents two copies of the same rules.

## 2. Offline registry rules

1. The registry loads only the files in `pins/schema-manifest.sha256`. A wrong sha256 stops the load (AC-88, TC-MV5).
2. Each `$id` must equal the pinned base plus the local path. An unversioned `$id` (for example `https://ucp.dev/schemas/...`) stops the load (TC-MV6).
3. The registry never uses the network. A `$ref` to a URL that is not in the registry raises an error (AC-87).
4. The registry refuses the aliases `latest` and `draft` under `https://ucp.dev/` (AC-87).

## 3. Schema closure: 36 more files (ACCEPTED)

Table A.4 lists 22 files. Offline validation needs 36 more files: 32 files at `2026-04-08` and 4 files at `2026-01-23`. `tools/contracts/fetch_closure.py` computes the `$ref` closure from the local copies. The result is 55 files. The other 3 files (`card_credential.json`, `card_payment_instrument.json`, `token_credential.json` at `2026-04-08`) are not in the closure. The TC-MV tests and AC-R6 use them. `tools/gates/hosted_vs_commit.py` shows that the 52 hosted `2026-04-08` files are equal to the files at UCP commit `9c9d6fc` (diffs=0).

## 4. New pin `[ucp_mixed_version]` (ACCEPTED)

The Google instrument schema refers to `https://ucp.dev/2026-01-23/schemas/shopping/types/card_payment_instrument.json`. Thus `pins/PINS.toml` has the new entry `[ucp_mixed_version]` with version `2026-01-23` (T-87, input-data D.1.1). No existing pin changed. G1 accepts the `latest` and `draft` aliases only in `tests/`, for the refusal tests.

## 5. New dependencies (ACCEPTED)

`jsonschema[format-nongpl]==4.26.0`, `referencing==0.37.0` and `cryptography==50.0.2`.

`jsonschema` has no type information. The stub package `types-jsonschema` would be one more dependency. Thus `pyproject.toml` has a mypy override `ignore_missing_imports` for the `jsonschema` modules only. `mypy --strict` stays on for all our code.

## 6. AC-106: `lint` and `validate`

The ucp-schema README at commit `6dd2a61` gives `lint` as "Static analysis of schema files". A profile is not a schema file. Thus we run `lint --strict` on the schema folders (G2), and we run `validate` on the served profile (ACCEPTED).

The exact `validate` command for the served profile:

```
ucp-schema validate <served-profile.json> \
  --schema contracts/ucp-schemas/discovery/profile.json \
  --schema-local-base contracts/ucp-schemas \
  --schema-remote-base https://ucp.dev/2026-04-08/schemas \
  --op read --def business_profile --json
```

Sources in ucp-schema at commit `6dd2a613d38828c97dca723bdb9ccfc79b2a7e80`:

| Argument | Source |
|---|---|
| `validate <payload>` | `src/bin/ucp-schema.rs:144-147` (`Validate { payload: PathBuf }`) |
| `--schema` | `src/bin/ucp-schema.rs:149-151`. Test: `tests/cli_test.rs:224-252` (`validate_valid_payload`) |
| `--schema-local-base` | `src/bin/ucp-schema.rs:153-155` |
| `--schema-remote-base` | `src/bin/ucp-schema.rs:157-159` (`requires = "schema_local_base"`). Tests: `tests/cli_test.rs:1207-1251` (`schema_remote_base_maps_url_prefix`), `tests/cli_test.rs:1254-1268` (`schema_remote_base_requires_local_base`) |
| `--op read` | `src/bin/ucp-schema.rs:173-175` (`op: String`, required) |
| `--def business_profile` | `src/bin/ucp-schema.rs:177-181` ("Validate against an explicit $defs entry"). Tests: `tests/container_test.rs:441-475`. `business_profile` is a `$defs` entry in `discovery/profile.json` (line 267) |
| `--json` | `src/bin/ucp-schema.rs:183-185` |
| `--strict` (not given, default `false`) | `src/bin/ucp-schema.rs:187-189` |

Note: `ucp-schema:tests/cli_test.rs` has no test that uses `--def`. The `--def` tests are in `ucp-schema:tests/container_test.rs`.

The contract test `tests/s1/contract/test_profiles_golden.py` runs this command on the demo and the CI profile (exit 0), and on a profile without `payment_handlers` (exit not 0).

## 7. Other decisions

1. AC-08 is "S1 PASS (part)". Checkout, fulfillment and order close in S1. `catalog.search` and `catalog.lookup` close in S7 (DM-11).
2. T-04 is used, not Q-P8. The profile has `signing_keys` and the `keys` mirror with the same key.
3. Binding. The overview says: "The origin of these URLs MUST match the namespace authority". We also accept a subdomain of the authority (for example `pay.google.com` for `com.google.pay`). This subdomain rule is UNVERIFIED (INFERENCE).
4. The CI profile has `dev.mock.payment_handler`. Its `spec` is on `ucp.dev`, and the authority of `dev.mock` is `mock.dev`. Thus our Platform does not use it. Only the conformance suite uses it.
5. The discovery panel has test cases (`case=malformed`, `binding`, `lookup-only`). Each case changes a copy of the fetched profile in the Platform. The Business does not change.

## Sources

- https://ucp.dev/2026-04-08/specification/overview/ (Namespace Governance, Spec URL Binding, Intersection Algorithm, Hosting, Fetching)
- https://github.com/Universal-Commerce-Protocol/ucp-schema/blob/6dd2a613d38828c97dca723bdb9ccfc79b2a7e80/README.md
- https://github.com/Universal-Commerce-Protocol/ucp-schema/blob/6dd2a613d38828c97dca723bdb9ccfc79b2a7e80/src/bin/ucp-schema.rs
- https://developers.google.com/pay/api/universal-commerce-protocol/google-pay-payment-handler
- https://www.rfc-editor.org/rfc/rfc7638
