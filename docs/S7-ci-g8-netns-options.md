# G8 in GitHub CI: network namespace options (S7)

Status: written 28 Oct 2026 (Europe/London). Nothing in this file is proved by a GitHub CI run yet.
Each claim has a source. A claim without a source has the mark UNVERIFIED.

## 1. Problem

G8 (AC-117, T-109) runs the loopback layout in a private user and network namespace
(`tools/latency/run_g8.sh`: `unshare --map-root-user --net`). The ports are fixed, so the
private namespace is how G8 avoids a clash with the running demo, and how it measures with the loopback only.

GitHub CI, run 40772772285 (branch s7, commit 212382b, 28 Oct 2026), job `gates`, step
"Run tools/gates/run_all.sh .run/gates":

    unshare: write failed /proc/self/uid_map: Operation not permitted
    G8 FAIL

Runner image in that run: `ubuntu-24.04`, image version 20261025.353.1 (from the job log).
G8 passes on the box (same command, run by the normal user `box`, no sudo; about 10 s, evidence
local run records (not in this repository)).

## 2. Cause (sources)

- Ubuntu 24.04 restricts unprivileged user namespaces with AppArmor. A process that is unprivileged and
  unconfined can create a user namespace, but AppArmor denies the capabilities inside it.
  Source: Ubuntu 24.04 LTS (Noble Numbat) Release Notes, section "Unprivileged user namespace restrictions",
  https://discourse.ubuntu.com/t/ubuntu-24-04-lts-noble-numbat-release-notes/39890
  (post created 2024-04-11, last edit 2026-03-04 UTC; read 28 Oct 2026).
- The switch is the sysctl `kernel.apparmor_restrict_unprivileged_userns` (1 = restricted).
  Sources: the same release notes; Ubuntu blog "Restricted unprivileged user namespaces are coming to
  Ubuntu 23.10", https://ubuntu.com/blog/ubuntu-23-10-restricted-unprivileged-user-namespaces
  (published 2023; read 28 Oct 2026); AppArmor wiki "unprivileged_userns_restriction",
  https://gitlab.com/apparmor/apparmor/-/wikis/unprivileged_userns_restriction (read 28 Oct 2026).
- The value on the runner at the time of the run: UNVERIFIED (the run did not print it). The new workflow
  step prints it before and after the change.
- GitHub does not change the default on the runner image. Source: issue
  https://github.com/actions/runner-images/issues/10015 ("apparmor should be disabled by default on Ubuntu",
  opened 2024-06-07, closed; read 28 Oct 2026) and issue
  https://github.com/actions/runner-images/issues/10443 ("ubuntu-24.04 Error during unshare(...): Operation
  not permitted", opened 2024-08-15, closed; read 28 Oct 2026). These issues are user reports and answers
  in the runner-images repository. They are not a runner-images readme. I did not find a statement in the
  runner-images readme about this sysctl: UNVERIFIED that the image documents it.
- The runner image readme (https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md,
  image version 20261026.354.1, read 28 Oct 2026) lists OS 24.04.5 LTS, kernel 7.0.0-1017-azure,
  sudo 1.9.15p5, Google Chrome 156.0.8078.47, Cargo/Rust 1.99.1, gnupg2 2.4.4. The run above used image
  20261025.353.1; that page for that exact version was not found (404): UNVERIFIED that the tool versions
  of 20261025.353.1 equal the list.
- Linux and macOS GitHub-hosted runners run with passwordless sudo. Source: GitHub Docs, "GitHub-hosted
  runners", section "Administrative privileges",
  https://docs.github.com/en/actions/reference/runners/github-hosted-runners#administrative-privileges
  (read 28 Oct 2026).

## 3. Options

Cost: GitHub-hosted Linux runner time. The repository is not visible without a login (the GitHub API answers
404 to an unauthenticated request), so it is probably private: UNVERIFIED. If it is private, the minutes
count against the plan quota: UNVERIFIED which plan and which quota. The run 40772772285 took about 6.5 min
(21:32:25 to about 21:38:50 UTC). Billing rounds each job up to a whole minute.

| # | Option | Changes | Spec impact | Weakens T-109? | Extra Actions minutes | Status |
|---|--------|---------|-------------|----------------|-----------------------|--------|
| A | Workflow step `sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0` before the gates (CI only) | `.github/workflows/ci.yaml` only | None. No code, no test, no gate changes. | No. G8 runs the same command in the same kind of namespace. The sysctl changes the runner VM, which GitHub deletes after the job. | Under 1 s for the step. G8 itself runs about 10 s on the box (UNVERIFIED in CI). | CHOSEN. Sources in section 2. Proof: UNVERIFIED until a GitHub CI run passes G8. |
| B | A workflow step that installs an AppArmor profile which allows `userns` for `/usr/bin/unshare` only, then loads it with `sudo apparmor_parser` | Workflow only (new profile file, one step) | None | No | A few seconds | Narrower than A (only `unshare` is allowed). The profile syntax is in the AppArmor wiki and in the release notes (unconfined profile with a `userns,` rule). Not tried on a runner: UNVERIFIED. More code to keep. Fallback if A is red or the project owner wants the narrow change. |
| C | Run G8 under real root: `sudo unshare --net ...` (no user namespace) | `tools/latency/run_g8.sh` (tool code) | G8 tool changes. App code does not change. | Not by itself (still a private network namespace with loopback only), but the harness runs as root and the files it writes are owned by root. A ruling of the project owner is needed because the G8 tool changes. | A few seconds | NOT DONE. |
| D | Named namespace with `sudo ip netns add` and `ip netns exec` | `tools/latency/run_g8.sh` | Same as C | Same as C | A few seconds | NOT DONE. |
| E | Run the job on `ubuntu-22.04` | Workflow `runs-on` | None for the spec. Other tool versions (Chrome, Python, Rust). | No | Same | NOT DONE. The Ubuntu 22 images start deprecation on 17 Sep 2026 and end on 17 Apr 2027 (https://github.com/actions/runner-images/issues/14254, opened 2026-06-16, read 28 Oct 2026). Whether 22.04 restricts user namespaces: UNVERIFIED. |
| F | Run G8 in a container with `--network none` | New image and runner code | G8 harness changes | Possibly: different network stack | More (image pull) | NOT DONE. |
| G | Self-hosted runner | Infrastructure | None | No | None on GitHub, but it needs a host we do not have | NOT DONE. |
| H | Skip G8 in CI or let it fail | - | Breaks the gate rule (a failed gate is a failed gate) | YES | 0 | FORBIDDEN by the ruling. |

## 4. Decision in this change

Option A is in `.github/workflows/ci.yaml`, with the sources above in the comment above the step.
The step also runs `unshare --map-root-user --net true`, so a wrong sysctl value fails at that step with a clear
message and not later inside G8.

G8 is not skipped and not weakened. T-109, the G8 tool and the app code are not changed.

## 5. Open items

- UNVERIFIED: that option A works on the runner image in use. Only a GitHub CI run can show it.
- UNVERIFIED: the runner value of `kernel.apparmor_restrict_unprivileged_userns` before the change.
- UNVERIFIED: that a future runner image keeps the sysctl name (the Ubuntu 26.04 image becomes `ubuntu-latest`
  in November 2026, announcement https://github.com/actions/runner-images/issues/14748; this workflow uses
  `ubuntu-24.04`, not `ubuntu-latest`).
- If A is red, use option B and report to the project owner; do not use H.

## 6. Second G8 cause found by the fresh-clone repro (not a network namespace problem)

The workflow set `MODE: ci` for the whole job. With MODE=ci, `platform_app.main.signing_key()` makes a new
ephemeral key in each process. The G8 driver (`tools/latency/g8_driver.py`) is a second process: it signs
with its own key, and the Platform service in the layout publishes a different key. The Business refuses each
signed request with HTTP 401 and G8 reports 100 % errors (repro log `repro-82f6485.log`, attempt 3).
The box gates run without MODE (default `demo`, key file under `.run`), so they did not show it.
Fix: the workflow no longer sets MODE (comment in `.github/workflows/ci.yaml`; test
`test_job_does_not_set_mode_ci`). App code, G8 and T-109 are not changed.
