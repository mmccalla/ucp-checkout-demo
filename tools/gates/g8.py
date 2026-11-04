"""Gate G8: latency against Google's targets (AC-117) and readiness within 120 s (AC-58).

It runs `tools/latency/run_g8.sh` on a clean export of HEAD in a private network namespace.
The report is `G8.json` in the report directory. The gate fails if the tree is not clean,
if readiness takes more than 120 s, if a p95 value is above its limit, or if one call fails.
"""

import argparse
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report")
    a = ap.parse_args()
    report = pathlib.Path(a.report) if a.report else ROOT / ".run" / "G8.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.unlink(missing_ok=True)
    r = subprocess.run([str(ROOT / "tools/latency/run_g8.sh"), str(report.parent)], cwd=ROOT)
    if report.exists():
        data = json.loads(report.read_text())
        status = data.get("status", "FAIL")
    else:
        status = "FAIL"
        report.write_text(json.dumps({"gate": "G8", "status": status, "exit": r.returncode}))
    ok = status == "PASS" and r.returncode == 0
    print(f"G8 {'PASS' if ok else 'FAIL'}")
    if not ok and status == "PASS":
        report.write_text(json.dumps({"gate": "G8", "status": "FAIL", "exit": r.returncode}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
