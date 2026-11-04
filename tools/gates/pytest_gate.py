"""Shared runner for the pytest gates G3, G4 and G7.

The gate fails if a test fails, errors, is skipped, xfails or xpasses (04-build-plan rule:
a skip counts as FAIL), or if it runs 0 tests. The test paths for each slice are in gates.toml.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[2]


def run_gate(gate: str) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report")
    a = ap.parse_args()
    cfg = tomllib.loads((ROOT / "tools/gates/gates.toml").read_text())
    paths: list[str] = cfg["pytest_paths"][gate][cfg["current_slice"]]
    report = pathlib.Path(a.report) if a.report else ROOT / ".run" / f"{gate}.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    junit = report.with_suffix(".junit.xml")
    cmd = ["uv", "run", "--no-sync", "pytest", "-v", "-rA", f"--junitxml={junit}", *paths]
    print("$ " + " ".join(cmd))
    r = subprocess.run(cmd, cwd=ROOT)
    root = ET.parse(junit).getroot()
    suite = root if root.tag == "testsuite" else root[0]
    counts = {k: int(suite.get(k, "0")) for k in ("tests", "failures", "errors", "skipped")}
    bad = counts["failures"] + counts["errors"] + counts["skipped"]
    ok = r.returncode == 0 and bad == 0 and counts["tests"] > 0
    status = "PASS" if ok else "FAIL"
    print(f"{gate} {status} {counts}")
    report.write_text(
        json.dumps({"gate": gate, "status": status, "counts": counts, "paths": paths}, indent=2)
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run_gate(sys.argv.pop(1)))
