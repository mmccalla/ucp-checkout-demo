"""Gate summary (AC-116). A missing report for an enabled gate makes the summary fail.

M1 (the live M-01 TEST sheet) is a manual step. CI never shows it as PASS.
Usage: uv run python tools/gates/summary.py REPORT_DIR
"""

import json
import pathlib
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[2]
ALL = ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8"]


def main(report_dir: pathlib.Path) -> int:
    cfg = tomllib.loads((ROOT / "tools/gates/gates.toml").read_text())
    enabled = cfg["slices"][cfg["current_slice"]]
    rows, ok = [], True
    for g in ALL:
        f = report_dir / f"{g}.json"
        if g not in enabled:
            status = "NOT IN SLICE"
        elif not f.exists():
            status, ok = "MISSING REPORT (FAIL)", False
        else:
            status = json.loads(f.read_text())["status"]
            ok &= status == "PASS"
        rows.append((g, status))
    rows.append(("M1 (M-01 live TEST sheet)", "NOT RUN"))
    lines = [f"# Gate summary ({cfg['current_slice']})", "", "| Gate | Status |", "|---|---|"]
    lines += [f"| {g} | {s} |" for g, s in rows]
    lines += [
        "",
        f"Overall: {'PASS' if ok else 'FAIL'}",
        "A release without an M-01 evidence record for its commit is not complete.",
    ]
    text = "\n".join(lines) + "\n"
    (report_dir / "summary.md").write_text(text)
    print(text)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / ".run/gates")))
