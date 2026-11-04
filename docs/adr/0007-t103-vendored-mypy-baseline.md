# ADR 0007: Per-file mypy baseline for the vendored samples server (T-103)

- Status: Accepted.
- Date: 2026-10-24.
- Owner: Mark McCalla.

## Context

1. Gate G1 runs `mypy --strict` on all code and fails on any error (T-91).
2. Spec T-103 (v1.1.2 section 15.2) gives one exception: the vendored copy of `rest/python/server` (samples `e7c9c12`). It needs an exact baseline for each file, with no glob.
3. Spec v1.1.2 says "The build reports 68 errors" and marks the value UNVERIFIED.
4. Spec v1.1.3 section 15.3 row 4 makes this ADR the spec value for T-103 item 2: 313 errors (315 before the patches), mypy 1.18.2. The spec owner reproduced the total and all 34 per-file counts.

## Measurement

1. Tool: mypy 1.18.2, `--strict`, config `tools/gates/mypy-vendored.ini` (mypy path = the sample folder). Measured on 2026-10-24 at about 23:30 BST.
2. Unchanged copy at `e7c9c12`: 315 errors.
3. Patched copy (this repository): 313 errors. P1 removes the file loader in `config.py` (6 to 4 errors).
4. The value 68 is not correct for this tool and this config. The baseline uses the measured value.
5. Code that we write has no exception (T-103 item 5). Two patch lines import `ucp-sdk` 0.4.6 modules. That package has no `py.typed` marker. Each of these two lines has `# type: ignore[import-untyped]`. All other patch lines have no new error.

## Decision

1. `tools/gates/mypy-vendored-baseline.json` gives each vendored `.py` file and its exact count (total 313).
2. `tools/gates/g1_vendored.py` runs in G1. It fails if a file has more or fewer errors than its baseline, if a file with an error is not in the baseline, or if a baseline file is missing.
3. The main mypy run excludes `business/src/ucp_sample_server/`. The `business_app` imports of the sample modules use `follow_imports = "skip"` in `pyproject.toml`.
4. The main ruff run excludes the vendored folder. It keeps its upstream style.
5. Reason: we keep the upstream code unchanged where we can (ADR 0005), so that a diff to upstream stays small.

## Sources

- Spec v1.1.3 section 15.3 row 4 and appendix T-103 (`03-spec.md`).

- mypy 1.18.2 docs, configuration: https://mypy.readthedocs.io/en/v1.18.2/config_file.html
- mypy docs, missing imports: https://mypy.readthedocs.io/en/v1.18.2/running_mypy.html#missing-imports
