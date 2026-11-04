# S7: CI failure capture

Status: built on branch `s7`. Scope: tools and the CI pytest step. No test, timeout, wait or retry changes.

## Purpose

One e2e test failed one time in a run of the CI repro (not on a real runner). The cause is UNVERIFIED (see the defect list in `docs/S7-catalog-build.md`).
The test stopped after a wait of more than 5 s for a page change. We cannot find the cause without data from the failed run.
The capture gives this data. It exists only after a failure.

## What the capture does

The capture runs around the pytest step. It uses the script `tools/ci-repro/capture_on_failure.sh`.

| Item | When | File in the capture folder |
|---|---|---|
| `vmstat -t 1` | It runs while pytest runs. The script keeps the output only if pytest fails. | `vmstat.txt` |
| Playwright trace | The plugin starts a trace on each new browser context. It saves the trace only for a failed test. | `traces/<test>-<n>.zip` |
| `ps` snapshot at the time of the failure | The plugin writes it when a test fails. | `traces/<test>-ps-at-failure.txt` |
| `ps` snapshot after pytest | The script writes it only if pytest fails. | `ps.txt` |
| `dmesg` | The script writes it only if pytest fails. | `dmesg.txt` |
| Facts of the run | The script writes them only if pytest fails. | `capture-info.txt` |

If pytest passes, the script deletes the capture folder. Nothing stays.

## dmesg can fail

A kernel can restrict `dmesg` (the setting `kernel.dmesg_restrict`). The script handles this in two steps.
First, it runs `dmesg -T`. If this fails, it runs `sudo -n dmesg -T`. The option `-n` stops a password question.
GitHub-hosted runners have passwordless `sudo`. Thus the second command is likely to work on a runner.
If both commands fail, the script writes the reason to `dmesg.txt` and the line `dmesg: not available` to `capture-info.txt`.
The exit code of the script stays the exit code of pytest. A failed capture step never changes the result of the job.
The repro tool replaces `sudo` with a shim that does nothing (see `tools/ci-repro/README.md`).
In the repro, `dmesg.txt` can thus hold the shim text. `capture-info.txt` shows which command ran.

## The trace does not change a test

The plugin is `tools/ci-repro/ucp_failure_capture.py`. It does nothing unless the environment variable `UCP_TRACE_ON_FAILURE` is `1`.
The script sets this variable and loads the plugin with `PYTEST_ADDOPTS`. The plugin changes no test file, timeout, wait or retry.
It wraps two Playwright methods:

1. `Browser.new_context` starts `context.tracing` (screenshots, snapshots, sources) when the context exists.
2. `BrowserContext.close` stops the trace. The plugin gives a file path to `Tracing.stop` only if the test failed. If not, the trace is dropped.

A hook wrapper on `pytest_runtest_makereport` tells the plugin if the `setup` or `call` phase of the test failed.
A failure in the `teardown` phase is not captured. The test fixtures close the context in the teardown phase, after the `call` report.
The plugin is the same idea as the RCA plugin of 30 October 2026. The new plugin has one change:
it numbers the trace files, so a test with more than one context does not overwrite a file.

A trace adds work in the browser (screenshots and DOM snapshots). This can change the timing of a page.
The effect on the stall is UNVERIFIED. The RCA ran 30 runs of the failed test with a trace and no run failed.

## Where the files go

The folder is `$UCP_CAPTURE_DIR`. In CI, the step "Set the paths" sets it to `$RUNNER_TEMP/failure-capture`.
Without this variable, the script uses `$RUNNER_TEMP/failure-capture`, or `.run/failure-capture` in the repository.
The path of the folder is not a path of the box.

## Upload in CI

The last step of the job uploads the folder. It uses `actions/upload-artifact` v7.0.2, pinned to the full commit SHA
`cf430e030ddbb5b0abf93d22962f4752f3646cd9`. The step has `if: failure()` and `retention-days: 7`.
The artifact name is `failure-capture`. The input `if-no-files-found: ignore` stops a warning when a step before pytest failed.
The repository, organization or enterprise can set a lower limit for `retention-days`. The value cannot be higher than that limit.

## Open the trace

Run `playwright show-trace <zip>` on a computer with Playwright, or open the zip file at https://trace.playwright.dev.
Use `vmstat.txt` to look for a pause in the time stamps. A pause of the host shows as a gap of more than 1 s between lines.
Compare the time of the gap with the time of the failed test in the pytest output.

## Sources

Playwright 1.56.0 (tag `v1.56.0`):
- Tracing API, `Tracing.start`, `Tracing.stop` and its option `path`:
  https://github.com/microsoft/playwright/blob/v1.56.0/docs/src/api/class-tracing.md
- Trace Viewer: https://github.com/microsoft/playwright/blob/v1.56.0/docs/src/trace-viewer.md

pytest 8.4 (the repository pins 8.4.2):
- Hook `pytest_runtest_makereport` (one report for each phase: setup, call, teardown):
  https://docs.pytest.org/en/8.4.x/reference/reference.html
- Hook wrappers (a generator that yields one time):
  https://docs.pytest.org/en/8.4.x/how-to/writing_hook_functions.html
- Option `-p name` (load a plugin module) and the variable `PYTEST_ADDOPTS`:
  https://docs.pytest.org/en/8.4.x/reference/reference.html and
  https://docs.pytest.org/en/8.4.x/how-to/plugins.html

GitHub Actions:
- Release `actions/upload-artifact` v7.0.2 (2026-10-07): https://github.com/actions/upload-artifact/releases/tag/v7.0.2
- The input `retention-days` and the artifact upload:
  https://docs.github.com/en/actions/tutorials/store-and-share-data
- Artifact retention (default 90 days, set at repository, organization and enterprise level):
  https://docs.github.com/en/actions/how-tos/manage-workflow-runs/remove-workflow-artifacts
- The function `failure()` (true when a previous step of the job fails):
  https://docs.github.com/en/actions/reference/workflows-and-actions/expressions
- The `env` context in `jobs.<job_id>.steps.with`:
  https://docs.github.com/en/actions/reference/workflows-and-actions/contexts

## Tests

`tests/s7/unit/test_failure_capture.py` has six tests. They need no browser.
They check the plugin switch, the file names, the trace save rule (with stand-in classes),
the script on a passing and on a failing command, and the workflow step (pin, `if: failure()`, `retention-days: 7`).

## UNVERIFIED

- The effect of the trace on the timing of a page.
- The value of `dmesg` on a GitHub-hosted runner. We did not run it there.
- The upload step on a real runner. The repro tool only copies the folder.
