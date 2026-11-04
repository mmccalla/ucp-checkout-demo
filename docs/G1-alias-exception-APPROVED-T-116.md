# APPROVED (T-116): a named G1 exception for the 2 alias strings in the schema registry

Status: **APPROVED and built (T-116).** The project owner approved this text as written on 28 Oct 2026. Code: `tools/gates/g1.py` (`alias_exempt_lines`, `alias_exemptions`). Tests: `tests/s5/unit/test_g1_alias_exception.py` (14 test functions and 17 collected cases; counted with `pytest --collect-only` on 28 Oct 2026). The spec file `03-spec.md` (v1.1.16) holds T-116.

## Problem

`libs/ucp_core/schema_registry.py` has a list named `FORBIDDEN`. It holds 3 strings (`schema_registry.py` lines 38 to 40): the `ucp.dev` address with the path part `latest`, the same address with the path part `draft`, and `https://ucp.dev/schemas/`. Only the first 2 are aliases for G1. The third string has no date, no `latest` and no `draft` after `ucp.dev/`, so the G1 pattern does not match it. G1 does not flag it and it needs no exemption (checked: `test_third_string_is_not_an_alias_for_g1_and_is_not_exempt`). The registry must refuse a schema whose `$id` starts with one of them (AC-118, the pin rule). The list must hold the exact strings, or the refusal cannot work.

G1 (AC-118) flags every `ucp.dev` alias outside `tests/`. The marker `g1-allow-unpinned` cannot cover these 2 lines under T-108 (APPROVED 28 Oct 2026): clause 3 allows the marker only if the same comment cites a UCP 2026-08-25 URL and `AC-44` or `AC-45`. The 2 lines have nothing to do with the August version. A marker with a false citation is a hack. A whole-line skip is not allowed.

Result: after the marker is removed from these 2 lines, G1 reports 2 errors:
one error for the `latest` line and one for the `draft` line (message: "alias is not pinned").

## Design (built)

A separate, named, narrow exception in `tools/gates/g1.py`. It is not the marker.

1. A constant `ALIAS_REFUSAL_FILE = "libs/ucp_core/schema_registry.py"` and a constant `ALIAS_REFUSAL_COUNT = 2`.
2. The exception applies only if all of these are true:
   a. The file is exactly `ALIAS_REFUSAL_FILE`.
   b. The alias string is inside the tuple or list named `FORBIDDEN`. G1 finds it with the `ast` module: an assignment to the name `FORBIDDEN` whose value is a tuple or list of string constants. G1 does not use a comment or a text marker.
   c. The string is exactly one of the 2 alias strings (the `latest` form or the `draft` form), as a whole string constant. A longer URL with a path after the alias is not exempt.
3. For such a string G1 skips only the alias check. The GitHub commit check and the Google Pay handler check still run.
4. G1 fails if the number of exempt strings is not `ALIAS_REFUSAL_COUNT` (2). A third alias-form string in `FORBIDDEN` (the same `latest` or `draft` string again), or a second file, fails G1. A string that is not an alias form (the third string of the real list) is neither flagged nor exempt.
5. G1 prints the exempt lines (file:line) in its report, so a reviewer sees them.
6. The exception does not change the T-108 marker rule. The marker count stays 3.

Why `ast` and not a comment: nothing in the exempt line can be copied to another place to get the same effect. The place is fixed by file, by name and by value.

## Test plan (AC-118)

Unit tests in `tests/s5/unit/test_g1_alias_exception.py`. Each test builds a small copy of the repository in `tmp_path`.

| Test | Expected result |
| --- | --- |
| The real tree: `FORBIDDEN` has 3 strings, 2 are alias strings | G1 passes, 2 exempt lines reported |
| Same strings in another `.py` file | G1 fails (alias is not pinned) |
| Same strings in `schema_registry.py`, but outside `FORBIDDEN` (a plain variable) | G1 fails |
| A third alias-form string in `FORBIDDEN` (a repeat of `latest`) | G1 fails (count is not 2) |
| One of the 2 strings is removed from `FORBIDDEN` | G1 fails (count is not 2) |
| A longer URL (alias plus a path) in `FORBIDDEN` | G1 fails |
| A GitHub URL with a wrong commit in `FORBIDDEN` | G1 fails (the other checks still run) |
| The marker `g1-allow-unpinned` on an exempt line | G1 fails (clause 3 of T-108) |
| `schema_registry.py` cannot be parsed | G1 fails with a clear error |

Added after the review of 28 Oct 2026 (tests in the same file, 8 more):

| Test | Expected result |
| --- | --- |
| `FORBIDDEN` in the real registry | 3 strings: the 2 alias strings first, then `https://ucp.dev/schemas/` |
| The third string (not an alias form) in a copy of the tree | G1 gives no error. It is not exempt (2 exempt lines) |
| A schema file with a `$id` that starts with each alias (2 tests) | `SchemaRegistry.load` raises `RegistryError` ("forbidden") |
| A schema URL and a document `$ref` with each alias (2 tests) | `validator` and `validate_document` raise `RegistryError` |
| Each alias removed from `FORBIDDEN` (2 tests) | the "forbidden" refusal does not happen: the list is the cause of the refusal |

## Decision

Approved as written. The strings are not built at run time in `schema_registry.py`. G1 prints each exempt line as `EXEMPT (T-116, alias check only) file:line`.
