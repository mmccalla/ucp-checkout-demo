# ci-repro: run the CI workflow on a clean clone

## Purpose

`repro_ci.py` runs the `run:` blocks of `.github/workflows/ci.yaml` on a Linux box.
It shows a CI failure before you push. The box is not a GitHub runner.
Use it before each push. A green repro does not replace the real CI run.

## Prerequisites

The versions below are the versions of the box where the tool was proven.

| Tool | Version | Use |
| --- | --- | --- |
| Linux, Debian 13 (trixie) | kernel 6.12 | host |
| bubblewrap (`bwrap`) | 0.12.0 | the sandbox. It needs unprivileged user namespaces. |
| Python 3 | 3.13.5 | runs `repro_ci.py` |
| PyYAML | 6.0.3 | reads `ci.yaml`. Only for the python that runs the tool. |
| git | 2.47.3 | the clean clone |
| uv | 0.13.6 | the same version as the workflow |
| curl | 8.14.1 | the Jaeger download |
| GnuPG (`gpg`) | 2.4.7 | the Jaeger signature |
| iproute2 (`ip`) | 6.15.0 | G8 |
| util-linux (`unshare`) | 2.41.5 | the namespace check of the workflow |
| Google Chrome | 156.0.8078.47 | the browser tests |
| cargo, rustc | 1.85.1 | the `ucp-schema` build step (see "Known limits") |
| ucp-schema | 1.4.1 | see "Known limits" |

The tool needs network access for the download steps (PyPI, Python builds, Caddy, Jaeger).
It does not need `sudo`. It does not need root.

## Command

Run it from the repository root. Replace each `<...>`.

```bash
PYTHONPATH=<dir with PyYAML> python3 tools/ci-repro/repro_ci.py \
  --src <git repository that has the commit> \
  --sha <full commit SHA> \
  --steps .github/workflows/ci.yaml \
  --work /var/tmp/ci-repro-<short SHA> \
  --log <log file> \
  --hide <dir 1> <dir 2> \
  --override 'ucp-schema=mkdir -p "$UCP_TOOLS_DIR/ucp-schema/bin" && cp "$GITHUB_WORKSPACE/../../../prebuilt/ucp-schema" "$UCP_TOOLS_DIR/ucp-schema/bin/ucp-schema" && test "$("$UCP_SCHEMA_BIN" --version)" = "ucp-schema 1.4.1"'
```

- `--src` and `--sha`: the tool clones `--src` and checks out `--sha` (detached). Use a full SHA.
- `--steps`: the workflow file. The tool reads the job `gates`. A JSON file with `env` and `steps` also works.
- `--work`: a new work directory. Do not use a path under `/tmp` (see "Known limits").
- `--log`: the tool writes each command and its output to this file.
- `--hide`: directories to hide. Hide the directory that holds your repository and your home directory.
  The sandbox must not see them. A step that reads a hidden path fails, as it fails on a runner.
- `--override STEP-NAME-PREFIX=script`: replaces the script of the step. The tool writes each
  override to the log as a DEVIATION. The example above replaces the ucp-schema build step.
- `--stop-after STEP-NAME-PREFIX`: stops after that step.

Before the first run, put a `ucp-schema` 1.4.1 binary in `<work dir>/prebuilt/ucp-schema`.
The example override copies it. The run takes about 8 minutes.

The last lines of the log are a table with the result of each step.
Step numbers follow the order of the steps in `ci.yaml`. A new step moves the numbers.

## What the tool isolates

- A fresh `git clone` and a detached checkout of the commit in the work directory.
- User: uid 1001 and gid 1001, in a new user namespace (not root, not your user).
- Environment: empty (`env -i`). The tool sets only `PATH`, `HOME`, `USER`, `LANG`, `TERM`, `CI`,
  `GITHUB_ACTIONS`, `GITHUB_WORKSPACE`, `RUNNER_TEMP`, `GITHUB_ENV`, `GITHUB_REPOSITORY`,
  `RUNNER_OS`, `RUNNER_ARCH`, the `env:` keys of the job, and the values that the steps write to `GITHUB_ENV`.
- `HOME` is in the work directory. The rest of the file system is read-only.
- Hidden paths: each `--hide` directory is an empty read-only tmpfs.
- `/tmp` is a new empty tmpfs. The process ids are in a new namespace.
- Network namespace: from the step "Jaeger start" on, all steps run in one sandbox session with a
  new network namespace (the loopback only). Background services stay up between the steps.
  The sandbox cannot reach the ports of other services on the host.
  The steps before it have network access.
- A step that fails stops the steps after it. Only the steps with `if: always()` still run.

## What the tool emulates

- `uses: actions/checkout`: a `git clone` and `git checkout` (see above).
- `uses: astral-sh/setup-uv`: no action runs. The tool only checks that `uv --version` has the version of the `with:` input.
- `uses: actions/upload-artifact` (it comes after "Jaeger start"): a stand-in. The tool copies the `path` folder to
  `$RUNNER_TEMP/emulated-artifacts/<name>`, and only if an earlier step failed (`if: failure()`). Nothing is uploaded.
  `retention-days` has no effect.
- Any other `uses:` step: not run. The log shows "NOT RUN".
- `sudo`: a shim in `PATH`. It writes `[sudo shim] NOT RUN` to the log and ends with exit code 0.
  A step that uses `sudo` (the `apt-get` step, `sysctl -w`) changes nothing on the box.
- The runner variables above. Other runner variables, secrets and the GitHub context do not exist.

## Known limits

- The work directory must not be inside a `--hide` directory.
- The work directory must not be under `/tmp`. The tool binds the work directory and then mounts a
  new tmpfs on `/tmp`. That hides the work directory, and `bwrap` fails with "Can't chdir".
  Use `/var/tmp`.
- The box is not the runner image. The kernel, the system Python, Chrome and the installed packages can differ.
  Compare the output of the step "Log the tool versions" with the CI log.
- The AppArmor switch `kernel.apparmor_restrict_unprivileged_userns` is not tested.
  `sudo` does nothing, and `sysctl` can be missing on the host (the log then shows "command not found").
  The `unshare` check passes because the host has no such restriction.
- From the step "Jaeger start" on, all steps share one session. A value that a step writes to
  `GITHUB_ENV` does not reach the next steps. The steps before it are not affected.
- `GITHUB_REPOSITORY` is fixed in the tool.
- The `ucp-schema` build step needs `libssl-dev`, which the `sudo apt-get` step installs. Without `sudo` this step cannot work.
  The override and a prebuilt binary replace it. The tool does not test the `cargo install` command.
- The tool needs the network. A change at a download site can fail a step that is not related to your change.
- The tool does not push, and it does not call GitHub.

## Failure capture (the pytest step)

The pytest step of `ci.yaml` runs `tools/ci-repro/capture_on_failure.sh uv run --no-sync pytest -q`.
Thus the repro runs the same capture as CI. Details and sources: `docs/S7-ci-failure-capture.md`.

If pytest fails, the capture folder stays. The folder is `$UCP_CAPTURE_DIR` (in the repro, `<work dir>/_temp/failure-capture`).
It holds `vmstat.txt` (`vmstat -t 1`, the output of the run), `ps.txt`, `dmesg.txt`, `capture-info.txt`,
and `traces/*.zip` (the Playwright trace of each failed e2e test).
If pytest passes, the script deletes the folder.

- `UCP_TRACE_ON_FAILURE=1` switches the trace plugin on. The script sets it. The plugin does not change a test, a timeout, a wait or a retry.
- `dmesg` can be restricted. The script then writes the reason to `dmesg.txt`.
  The repro has no `sudo` (a shim), so the second try, `sudo -n dmesg -T`, does nothing there.
- The script needs `vmstat` and `ps` (the package `procps`). If `vmstat` is missing, `vmstat.txt` says so.

To run the capture on your own command (a check of the capture), run for example:

```bash
UCP_CAPTURE_DIR=<new folder> tools/ci-repro/capture_on_failure.sh uv run --no-sync pytest -q <test id>
```
