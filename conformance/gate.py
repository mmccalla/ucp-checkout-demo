"""G5: run the pinned conformance suite against the Business in MODE=ci (spec T-91, T-93).

`uv run python conformance/gate.py [--report-dir DIR] [--suite-dir DIR]`

Rules (input-engineering 7.3):
1. Run the full suite. No `-k` filter.
2. Fail on any `error` or `failure` in the JUnit XML.
3. Fail on a skip that is not in `approved-skips.txt` (AC-119). Fail on an approved skip that did
   not skip (AC-119).
4. Fail if the number of test cases is not the pinned number (AC-120).
Exit code 0 is a pass. Exit code 1 is a fail. Exit code 2 is a setup problem (no suite, no Business).

DM-26: the suite starts helper servers on `0.0.0.0` (ports 8284 and 8285, upstream code, pinned).
The gate runs the Business and the suite in a new network namespace that has only a loopback
interface (`unshare --map-root-user --net`). No address outside the namespace can reach them.
The project owner accepted this containment as CI-only, with 2 conditions (28 Oct 2026):
1. The gate FAILS (exit 2) if `unshare` is not installed or does not work. It never runs the
   suite outside a private namespace.
2. Before the Business starts, the gate checks that the namespace is a new one and that its only
   interface is `lo`. If not, it FAILS (exit 2). The interface list is in `netns-check.txt`.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import pathlib
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
PORT = 18201  # inside the namespace only
SUITE_WEBHOOK_PORT = 8284  # `mock_webhook_port` of the suite at 016ecbc
SUITE_AGENT_PORT = 8285  # `mock_agent_port` of the suite at 016ecbc
CASE_ID = "{classname}.{name}"


@dataclasses.dataclass(frozen=True)
class Pin:
    repo: str
    commit: str
    test_methods: int


@dataclasses.dataclass
class Verdict:
    ok: bool
    total: int
    passed: int
    failures: list[str]
    errors: list[str]
    skipped: list[tuple[str, str]]
    violations: list[str]

    def as_json(self) -> dict[str, object]:
        return dataclasses.asdict(self)


def read_pin(path: pathlib.Path) -> Pin:
    kv: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            kv[k.strip()] = v.strip()
    commit = kv["commit"]
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError(f"PIN commit is not a 40-digit lower-case hex value: {commit!r}")
    return Pin(kv["repo"], commit, int(kv["test_methods"]))


def read_approved(path: pathlib.Path) -> set[str]:
    """One test case per line: `<classname>.<name>`. A line can end with `# reason`."""
    out: set[str] = set()
    if path.exists():
        for line in path.read_text().splitlines():
            entry = line.split("#", 1)[0].strip()
            if entry:
                out.add(entry)
    return out


def evaluate(
    junit: pathlib.Path,
    pin: Pin,
    approved: set[str],
    approved_failures: set[str] | None = None,
) -> Verdict:
    """Judge a junit report. `approved_failures` is the list of T-113 (AC-119, AC-120)."""
    listed = approved_failures or set()
    root = ET.parse(junit).getroot()
    failures: list[str] = []
    errors: list[str] = []
    skipped: list[tuple[str, str]] = []
    total = passed = 0
    for tc in root.iter("testcase"):
        total += 1
        cid = CASE_ID.format(classname=tc.get("classname", ""), name=tc.get("name", ""))
        sk = tc.find("skipped")
        if tc.find("failure") is not None:
            failures.append(cid)
        elif tc.find("error") is not None:
            errors.append(cid)
        elif sk is not None:
            skipped.append((cid, sk.get("message", "")))
        else:
            passed += 1
    violations: list[str] = []
    unlisted = [c for c in failures if c not in listed]
    if unlisted:
        violations.append(f"{len(unlisted)} unlisted failure(s)")
    for cid in sorted(listed - set(failures)):
        violations.append(f"T-113: approved failure did not fail {cid}")
    if errors:
        violations.append(f"{len(errors)} error(s)")
    skipped_ids = {cid for cid, _ in skipped}
    for cid in sorted(skipped_ids - approved):
        violations.append(f"AC-119: unapproved skip {cid}")
    for cid in sorted(approved - skipped_ids):
        violations.append(f"AC-119: approved skip did not skip {cid}")
    if total != pin.test_methods:
        violations.append(f"AC-120: {total} test cases, the pin has {pin.test_methods}")
    return Verdict(not violations, total, passed, failures, errors, skipped, violations)


def suite_problems(pin: Pin, suite_dir: pathlib.Path) -> list[str]:
    """T-110 criterion 3: the suite HEAD is the pin and no tracked file changed."""
    out: list[str] = []
    head = subprocess.run(
        ["git", "-C", str(suite_dir), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    if head != pin.commit:
        out.append(f"T-110: suite HEAD {head} is not the pin {pin.commit}")
    dirty = subprocess.run(
        ["git", "-C", str(suite_dir), "status", "--porcelain", "--untracked-files=no"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    if dirty:
        out.append("T-110: a tracked file of the suite changed: " + dirty.replace("\n", "; "))
    return out


def ensure_suite(pin: Pin, suite_dir: pathlib.Path) -> None:
    """Get the suite at the pinned commit. The HEAD must be exactly the pin."""
    if not (suite_dir / ".git").exists():
        suite_dir.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--quiet", pin.repo, str(suite_dir)], check=True)
    head = subprocess.run(
        ["git", "-C", str(suite_dir), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if head != pin.commit:
        subprocess.run(["git", "-C", str(suite_dir), "checkout", "--quiet", pin.commit], check=True)
        head = subprocess.run(
            ["git", "-C", str(suite_dir), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    if head != pin.commit:
        raise RuntimeError(f"suite HEAD {head} is not the pin {pin.commit}")


def unshare_problem() -> str | None:
    """Return the reason why a private network namespace is not available, or None.

    The gate must fail in this case. It must not run the suite on the host network (DM-26).
    """
    if shutil.which("unshare") is None:
        return "unshare is not installed"
    r = subprocess.run(
        ["unshare", "--map-root-user", "--net", "true"], capture_output=True, text=True
    )
    if r.returncode != 0:
        return f"`unshare --map-root-user --net` failed: {r.stderr.strip()[:200]}"
    return None


def netns_interfaces() -> list[str]:
    """Interface names in the network namespace of this process.

    `/proc/net/dev` shows the namespace of the reader. `/sys/class/net` does not: sysfs keeps the
    namespace of the process that mounted it, so it lists the host interfaces inside `unshare`.
    """
    names = []
    for line in pathlib.Path("/proc/net/dev").read_text().splitlines()[2:]:
        names.append(line.split(":", 1)[0].strip())
    return sorted(n for n in names if n)


def loopback_problems(interfaces: list[str], outer_ns: str | None, inner_ns: str) -> list[str]:
    """Check the namespace: a new one (not the namespace of the caller) with only `lo`."""
    problems: list[str] = []
    if not outer_ns:
        problems.append("the gate did not pass the network namespace of the caller")
    elif outer_ns == inner_ns:
        problems.append(f"this is not a new network namespace ({inner_ns})")
    if "lo" not in interfaces:
        problems.append("the namespace has no `lo` interface")
    others = sorted(i for i in interfaces if i != "lo")
    if others:
        problems.append("the namespace has an interface other than `lo`: " + ", ".join(others))
    return problems


def _wait_ready(url: str, seconds: float) -> bool:
    import urllib.request

    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            with urllib.request.urlopen(url, timeout=1) as r:  # noqa: S310  loopback only
                if r.status == 200:
                    return True
        except OSError:
            time.sleep(0.2)
    return False


def run_inner(pin: Pin, suite_dir: pathlib.Path, report_dir: pathlib.Path) -> int:
    """Run in the namespace: start the Business, run the suite, stop the Business."""
    report_dir.mkdir(parents=True, exist_ok=True)
    interfaces = netns_interfaces()
    inner_ns = os.readlink("/proc/self/ns/net")
    problems = loopback_problems(interfaces, os.environ.get("G5_OUTER_NETNS"), inner_ns)
    (report_dir / "netns-check.txt").write_text(
        f"namespace: {inner_ns}\ncaller namespace: {os.environ.get('G5_OUTER_NETNS')}\n"
        f"interfaces: {' '.join(interfaces)}\n"
        + (
            "PASS: new namespace, loopback only\n"
            if not problems
            else "FAIL\n" + "\n".join(problems) + "\n"
        )
    )
    if problems:
        print("G5 setup: DM-26 containment check failed: " + "; ".join(problems), file=sys.stderr)
        return 2
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="g5-"))
    data = tmp / "data"
    data.mkdir()
    secret = secrets.token_hex(8)
    sample = ROOT / "business" / "src" / "ucp_sample_server"
    subprocess.run(
        [
            sys.executable,
            "import_csv.py",
            f"--products_db_path={data / 'products.db'}",
            f"--transactions_db_path={data / 'transactions.db'}",
            f"--data_dir={suite_dir / 'test_data' / 'flower_shop'}",
        ],
        cwd=sample,
        check=True,
        capture_output=True,
    )
    env = dict(os.environ)
    env.update(
        MODE="ci",
        BUSINESS_DATA_DIR=str(data),
        BUSINESS_REQUIRE_SIGNATURES="false",  # T-04: off only in G5
        BUSINESS_ORIGIN=f"http://127.0.0.1:{PORT}",
        # T-114 option (a): the one http suite profile URL. The Business checks again that it
        # runs in a namespace with only `lo`. If not, the seam is off.
        BUSINESS_CI_SUITE_PROFILE_HTTP="1",
        BUSINESS_CI_SUITE_PROFILE_PORT=str(SUITE_AGENT_PORT),
        BUSINESS_CI_SUITE_WEBHOOK_HTTP="1",  # T-115: the one suite webhook URL
        BUSINESS_CI_SUITE_WEBHOOK_PORT=str(SUITE_WEBHOOK_PORT),
        # The `UCP-Agent` of a webhook must be an HTTPS URL (signatures.md 622 to 625). Inside
        # the namespace the Business serves plain http, so the demo profile URL is given.
        BUSINESS_WEBHOOK_PROFILE_URL="https://localhost:9443/.well-known/ucp",
        BUSINESS_CI_NETNS="1",  # set only after `loopback_problems` was empty (above)
        SIMULATION_SECRET=secret,
        UCP_TRACING="0",
        PYTHONPATH=os.pathsep.join([str(ROOT / "business" / "src"), str(ROOT / "libs")]),
    )
    env.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
    log = (report_dir / "business.log").open("w")
    biz = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "--factory", "business_app.main:create_app",
            "--host", "127.0.0.1", "--port", str(PORT),
        ],
        cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
    )  # fmt: skip
    try:
        if not _wait_ready(f"http://127.0.0.1:{PORT}/readyz", 30):
            print("G5 setup: the Business did not become ready", file=sys.stderr)
            return 2
        senv = dict(os.environ)
        senv.update(
            SERVER_URL=f"http://127.0.0.1:{PORT}",
            SIMULATION_SECRET=secret,
            S5_CONFORMANCE_INPUT=str(HERE / "input" / "conformance_input.json"),
            S5_FIXTURE_CONFIG=str(HERE / "input" / "test_fixtures.json"),
            PYTHONPATH=os.pathsep.join([str(HERE), str(suite_dir)]),
        )
        junit = report_dir / "junit.xml"
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            "pyproject.toml",
            "-p",
            "s5_flags",
            "-p",
            "s5_profile",
            "-p",
            "no:cacheprovider",
            f"--junitxml={junit}",
            "-q",
            "-rs",
        ]  # fmt: skip  (no -k, no file list: the full suite)
        with (report_dir / "suite.log").open("w") as out:
            subprocess.run(cmd, cwd=suite_dir, env=senv, stdout=out, stderr=subprocess.STDOUT)
    finally:
        biz.terminate()
        try:
            biz.wait(timeout=10)
        except subprocess.TimeoutExpired:
            biz.kill()
        log.close()
        shutil.rmtree(tmp, ignore_errors=True)
    if not (report_dir / "junit.xml").exists():
        print("G5 setup: the suite wrote no JUnit file", file=sys.stderr)
        return 2
    v = evaluate(
        report_dir / "junit.xml",
        pin,
        read_approved(HERE / "approved-skips.txt"),
        read_approved(HERE / "approved-failures.txt"),
    )
    extra = suite_problems(pin, suite_dir)
    if extra:
        v.violations.extend(extra)
        v.ok = False
    (report_dir / "g5-report.json").write_text(json.dumps(v.as_json(), indent=2) + "\n")
    skips = "".join(f"{cid}\t{msg}\n" for cid, msg in v.skipped)
    (report_dir / "skip-report.txt").write_text(skips)
    print(
        f"G5 {'PASS' if v.ok else 'FAIL'} tests={v.total} passed={v.passed} "
        f"failures={len(v.failures)} errors={len(v.errors)} skipped={len(v.skipped)}"
    )
    for item in v.violations:
        print(f"  {item}")
    return 0 if v.ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report-dir", default=str(ROOT / ".run" / "g5"))
    ap.add_argument("--suite-dir", default=str(ROOT / ".run" / "conformance-suite"))
    ap.add_argument("--inner", action="store_true", help="internal: run in the namespace")
    a = ap.parse_args()
    pin = read_pin(HERE / "PIN")
    report_dir = pathlib.Path(a.report_dir).resolve()
    suite_dir = pathlib.Path(a.suite_dir).resolve()
    if a.inner:
        return run_inner(pin, suite_dir, report_dir)
    problem = unshare_problem()
    if problem:
        print(
            f"G5 setup: {problem}. G5 needs a private network namespace (DM-26). "
            "The gate does not run the suite on the host network.",
            file=sys.stderr,
        )
        return 2
    ensure_suite(pin, suite_dir)
    me = [sys.executable, str(pathlib.Path(__file__).resolve()), "--inner",
          f"--report-dir={report_dir}", f"--suite-dir={suite_dir}"]  # fmt: skip
    script = "ip link set lo up && exec " + " ".join(f"'{c}'" for c in me)
    env = dict(os.environ, G5_OUTER_NETNS=os.readlink("/proc/self/ns/net"))
    return subprocess.run(
        ["unshare", "--map-root-user", "--net", "bash", "-c", script], cwd=ROOT, env=env
    ).returncode


if __name__ == "__main__":
    sys.exit(main())
