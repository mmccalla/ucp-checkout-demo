#!/usr/bin/env python3
"""Repro of the GitHub workflow .github/workflows/ci.yaml on a Linux box (the box is not a runner).

What it does (all is written to the log file, with each command and its output):
 1. fresh `git clone` of the branch in a clean directory outside the repository and outside the hidden paths (work dir under /var/tmp, not under /tmp);
 2. runs each `run:` block of the real workflow file, in the order of the file, with `bash -eo pipefail -c`,
    as the GitHub runner does (GITHUB_ENV file, GITHUB_WORKSPACE, RUNNER_TEMP, CI=true);
 3. each step runs in `bwrap` (bubblewrap) as uid 1001 (a new user namespace; the host user is not uid 1001): empty environment (`env -i`), HOME in the work dir, the paths of --hide
    hidden under a read-only empty tmpfs, /tmp new and empty. From the step "Jaeger start" on, it also has
    a new network namespace (the loopback only), as G8 needs, and it cannot reach the demo ports.
 4. `uses:` steps cannot run here: checkout is a git clone, setup-uv is checked (uv version only).
    `actions/upload-artifact` (after "Jaeger start") is emulated as a local copy of its `path` into
    `$RUNNER_TEMP/emulated-artifacts/<name>`. It runs only if an earlier step failed (`if: failure()`).
 5. `sudo` is a shim: there is no sudo for this user on the box. It logs the command and does nothing.
Usage: repro_ci.py --src <git dir> --sha <commit> --steps <ci.yaml or steps json> --work <dir> --log <file>
See tools/ci-repro/README.md.
"""

import argparse
import importlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from typing import Any

ap = argparse.ArgumentParser()
ap.add_argument("--src", required=True)
ap.add_argument("--sha", required=True)
ap.add_argument(
    "--steps", required=True
)  # the workflow file (.yaml, needs PyYAML) or its steps as json
ap.add_argument("--work", required=True)
ap.add_argument("--log", required=True)
ap.add_argument("--hide", nargs="*", default=[])
ap.add_argument("--stop-after", default="")
ap.add_argument(
    "--override",
    action="append",
    default=[],
    help="STEP-NAME-PREFIX=script (a deviation; it is logged)",
)
a = ap.parse_args()

W = os.path.abspath(a.work)
LOG = open(a.log, "w", buffering=1)


def log(s: str = "") -> None:
    LOG.write(s + "\n")
    print(s, flush=True)


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()) + "Z"


def load_spec(path: str) -> dict[str, Any]:
    if path.endswith((".yaml", ".yml")):
        yaml = importlib.import_module("yaml")  # PyYAML: only for a workflow file
        job = yaml.safe_load(open(path))["jobs"]["gates"]
        return {"env": job.get("env"), "steps": job["steps"]}
    spec: dict[str, Any] = json.load(open(path))
    return spec


spec = load_spec(a.steps)
env_job = spec.get("env") or {}
steps = spec["steps"]
WS = f"{W}/work/ucp-checkout-demo/ucp-checkout-demo"
TMP = f"{W}/_temp"
HOME = f"{W}/home"
SHIM = f"{W}/shim"
for d in (WS, TMP, HOME, SHIM, f"{W}/tmpfs-empty"):
    os.makedirs(d, exist_ok=True)
GHENV = f"{TMP}/github_env"
open(GHENV, "w").close()
open(f"{SHIM}/sudo", "w").write(
    '#!/bin/bash\necho "[sudo shim] NOT RUN (no sudo on the box): sudo $*"\nexit 0\n'
)
os.chmod(f"{SHIM}/sudo", 0o755)

log(f"# repro of ci.yaml  start {now()}")
log(f"# user: {subprocess.getoutput('id')}  (not a runner user; not root)")
log(
    f"# host: {subprocess.getoutput('uname -srm')}; {subprocess.getoutput('. /etc/os-release; echo $PRETTY_NAME')}"
)
log(f"# work dir: {W}")
log(f"# hidden under a read-only empty tmpfs: {a.hide}")


def run(
    cmd: str | list[str],
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    shell: bool = False,
) -> int:
    log(f"$ {cmd if isinstance(cmd, str) else ' '.join(cmd)}   [{now()}]")
    p = subprocess.Popen(
        cmd,
        shell=shell,
        env=env,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    )
    assert p.stdout is not None
    for line in p.stdout:
        LOG.write("    " + line)
    p.wait()
    log(f"    -> exit {p.returncode}")
    return p.returncode


# 1. checkout (stand-in for actions/checkout: a fresh clone, then the exact commit, detached)
shutil.rmtree(WS, ignore_errors=True)
rc = run(["git", "clone", "--quiet", a.src, WS], env={"PATH": "/usr/bin:/bin", "HOME": HOME})
rc |= run(
    ["git", "-C", WS, "checkout", "--quiet", "--detach", a.sha],
    env={"PATH": "/usr/bin:/bin", "HOME": HOME},
)
run(["git", "-C", WS, "log", "--oneline", "-1"], env={"PATH": "/usr/bin:/bin", "HOME": HOME})
if rc:
    sys.exit(2)

base_env = {
    "PATH": f"{SHIM}:{HOME}/.cargo/bin:{HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin",
    "HOME": HOME,
    "USER": "runner",
    "LANG": "C.UTF-8",
    "TERM": "dumb",
    "CI": "true",
    "GITHUB_ACTIONS": "true",
    "GITHUB_WORKSPACE": WS,
    "RUNNER_TEMP": TMP,
    "GITHUB_ENV": GHENV,
    "GITHUB_REPOSITORY": "mmccalla/ucp-checkout-demo",
    "RUNNER_OS": "Linux",
    "RUNNER_ARCH": "X64",
}
base_env.update({k: str(v) for k, v in env_job.items()})


def load_ghenv() -> None:
    for line in open(GHENV).read().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            base_env[k] = v


def session_step(st: dict[str, Any]) -> tuple[str, str]:
    """Name and bash script of a step in the sandbox session (after "Jaeger start").

    A `run:` step gives its script. A `uses: actions/upload-artifact@...` step gives a script that
    copies the `path` input into `$RUNNER_TEMP/emulated-artifacts/<name>` (a stand-in: no upload, and
    `retention-days` has no effect). The workflow expressions `${{ env.X }}` and `${{ runner.temp }}`
    in `path` are replaced. Any other `uses:` step gives a script that only prints NOT RUN.
    """
    if "run" in st:
        return st.get("name") or st["run"].splitlines()[0][:70], str(st["run"])
    uses = str(st["uses"])
    name = st.get("name") or uses.split("@")[0]
    if not uses.startswith("actions/upload-artifact@"):
        return name, f"echo {shlex.quote('uses ' + uses + ': NOT RUN (not emulated)')}"
    with_ = st.get("with") or {}
    path = str(with_.get("path", ""))
    path = re.sub(r"\$\{\{\s*env\.(\w+)\s*\}\}", lambda m: "${" + m.group(1) + "}", path)
    path = re.sub(r"\$\{\{\s*runner\.temp\s*\}\}", "${RUNNER_TEMP}", path)
    art = shlex.quote(str(with_.get("name", "artifact")))
    return name, (
        f'src="{path}"; dst="$RUNNER_TEMP/emulated-artifacts"/{art}\n'
        'echo "uses '
        + uses
        + ': EMULATED as a local copy (no upload; retention-days has no effect)"\n'
        'if [ -e "$src" ]; then mkdir -p "$dst" && cp -a "$src"/. "$dst"/ && echo "copied to $dst" && ls -l "$dst"; '
        'else echo "no files found at $src (the action ignores it)"; fi'
    )


results = []
netns = False
for i, st in enumerate(steps, 1):
    name = st.get("name") or (st.get("run", st.get("uses", "")).splitlines() or [""])[0][:70]
    log("")
    log(f"## step {i}: {name}")
    if "uses" in st:
        u = st["uses"]
        if u.startswith("actions/checkout@"):
            log(f"    uses {u}: done above as a git clone (stand-in)")
            results.append((i, name, "EMULATED", ""))
        elif u.startswith("astral-sh/setup-uv@"):
            want = st["with"]["version"]
            out = subprocess.getoutput("uv --version")
            ok = want in out
            log(
                f"    uses {u}: stand-in. wanted uv {want}; box has: {out} -> {'OK' if ok else 'DIFFERENT'}"
            )
            results.append((i, name, "EMULATED" if ok else "UV VERSION DIFFERS", out))
        else:
            log(f"    uses {u}: not emulated")
            results.append((i, name, "NOT RUN", ""))
        continue
    if st.get("if") == "always()" and not results:
        pass
    if name.startswith("Jaeger start"):
        netns = True
        log(
            "    (from here on: ONE sandbox session with a new network namespace, loopback only; the steps run"
        )
        log(
            "     one after the other in it, so background services stay up between the steps, as on a runner VM)"
        )
        # $3 is the mode: 0 = run only if no step failed, 1 = `if: always()`, 2 = `if: failure()`.
        parts = [
            "failed=0",
            'run_step() { if [ "$3" = 2 ] && [ "$failed" -eq 0 ]; then echo "### STEP $1 NOT RUN"; return 0; fi; '
            'if [ "$failed" -ne 0 ] && [ "$3" = 0 ]; then echo "### STEP $1 NOT RUN"; return 0; fi; '
            'echo "### STEP $1 $2"; echo "$4" | sed "s/^/      | /"; bash -eo pipefail -c "$4"; rc=$?; echo "### STEP $1 rc=$rc"; '
            '[ "$rc" -ne 0 ] && failed=1; return 0; }',
        ]
        for j, st2 in enumerate(steps[i - 1 :], i):
            n2, script2 = session_step(st2)
            mode = {"always()": 1, "failure()": 2}.get(str(st2.get("if")), 0)
            parts.append("run_step %d %s %d %s" % (j, shlex.quote(n2), mode, shlex.quote(script2)))
        outer = "\n".join(parts)
        cmd = (
            ["env", "-i"]
            + [f"{k}={v}" for k, v in base_env.items()]
            + [
                "bwrap",
                "--unshare-user",
                "--uid",
                "1001",
                "--gid",
                "1001",
                "--ro-bind",
                "/",
                "/",
                "--dev",
                "/dev",
                "--proc",
                "/proc",
                "--bind",
                W,
                W,
                "--tmpfs",
                "/tmp",
            ]
        )
        for h in a.hide:
            cmd += ["--tmpfs", h, "--remount-ro", h]
        cmd += [
            "--unshare-pid",
            "--die-with-parent",
            "--unshare-net",
            "--chdir",
            WS,
            "bash",
            "-c",
            outer,
        ]
        rc = run(cmd)
        text = open(a.log).read()
        for j, st2 in enumerate(steps[i - 1 :], i):
            n2, _ = session_step(st2)
            m = re.findall(r"### STEP %d rc=(\d+)" % j, text)
            results.append(
                (
                    j,
                    n2,
                    ("PASS" if m[-1] == "0" else f"FAIL (exit {m[-1]})") if m else "NOT RUN",
                    "",
                )
            )
        break
    script = st["run"]
    for ov in a.override:
        pre, _, scr = ov.partition("=")
        if name.startswith(pre):
            log(
                "    !! DEVIATION: the script of this step is replaced for the repro (reason: no sudo and no libssl-dev on the box)"
            )
            script = scr
    cmd = (
        ["env", "-i"]
        + [f"{k}={v}" for k, v in base_env.items()]
        + [
            "bwrap",
            "--unshare-user",
            "--uid",
            "1001",
            "--gid",
            "1001",
            "--ro-bind",
            "/",
            "/",
            "--dev",
            "/dev",
            "--proc",
            "/proc",
            "--bind",
            W,
            W,
            "--tmpfs",
            "/tmp",
        ]
    )
    for h in a.hide:
        cmd += ["--tmpfs", h, "--remount-ro", h]
    cmd += ["--unshare-pid", "--die-with-parent"]
    if netns:
        cmd += ["--unshare-net"]
    cmd += ["--chdir", WS, "bash", "-eo", "pipefail", "-c", script]
    log("    script:")
    for ln in script.splitlines():
        log("      | " + ln)
    rc = run(cmd)
    load_ghenv()
    results.append((i, name, "PASS" if rc == 0 else f"FAIL (exit {rc})", ""))
    if rc != 0 and st.get("if") != "always()":
        log("    step failed: later steps without `if: always()` do not run (as in GitHub Actions)")
        failed = True
        for j, st2 in enumerate(steps[i:], i + 1):
            if st2.get("if") == "always()":
                results.append((j, st2.get("name") or st2["run"][:50], "RUN (always)", ""))
                cmd2 = cmd[:-5] + ["bash", "-eo", "pipefail", "-c", st2["run"]]
                run(cmd2)
            else:
                results.append((j, st2.get("name") or st2.get("run", "")[:50], "NOT RUN", ""))
        break
    if a.stop_after and name.startswith(a.stop_after):
        break

log("")
log("## summary")
for r in results:
    log(f"| {r[0]} | {r[1]} | {r[2]} |")
log(f"# end {now()}")
