"""G1 part: mypy --strict on the vendored samples server, with an exact per-file baseline.

Spec T-103 (v1.1.2 section 15.2), ADR 0007. The baseline is
`tools/gates/mypy-vendored-baseline.json`: each vendored .py file path and its exact error
count. There is no glob. The check fails if:
1. a file has more errors than its baseline,
2. a file has fewer errors than its baseline (update the baseline in the same commit),
3. a file with errors is not in the baseline, or a baseline file is not in the copy.

Run: uv run python tools/gates/g1_vendored.py [--measure]
With --measure, it prints the counts as JSON and does not compare.
"""

from __future__ import annotations

import collections
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
VENDORED = "business/src/ucp_sample_server"
CONFIG = "tools/gates/mypy-vendored.ini"
BASELINE = ROOT / "tools" / "gates" / "mypy-vendored-baseline.json"
LINE = re.compile(r"^(?P<path>[^:]+\.py):\d+(?::\d+)?: error: ")


def files() -> list[str]:
    return sorted(str(p.relative_to(ROOT)) for p in (ROOT / VENDORED).rglob("*.py"))


def measure() -> dict[str, int]:
    r = subprocess.run(
        [sys.executable, "-m", "mypy", "--config-file", CONFIG, "--no-error-summary", VENDORED],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    counts: collections.Counter[str] = collections.Counter()
    for line in r.stdout.splitlines():
        m = LINE.match(line)
        if m:
            counts[m.group("path")] += 1
    if r.returncode not in (0, 1) or (r.returncode == 1 and not counts):
        print(r.stdout[-2000:] + r.stderr[-2000:])
        raise SystemExit(f"mypy did not run (exit {r.returncode})")
    return {f: counts.get(f, 0) for f in files()} | {
        f: n for f, n in counts.items() if f not in files()
    }


def main() -> int:
    got = measure()
    if "--measure" in sys.argv:
        print(json.dumps({"total": sum(got.values()), "files": got}, indent=2))
        return 0
    base: dict[str, int] = json.loads(BASELINE.read_text())["files"]
    errors = []
    for f in sorted(set(got) | set(base)):
        if f not in base:
            if got[f]:
                errors.append(f"{f}: {got[f]} errors, file not in the baseline")
            else:
                errors.append(f"{f}: file not in the baseline (add it with count 0)")
        elif f not in got:
            errors.append(f"{f}: in the baseline, but not in the vendored copy")
        elif got[f] != base[f]:
            word = "more" if got[f] > base[f] else "fewer"
            errors.append(f"{f}: {got[f]} errors, baseline {base[f]} ({word}; T-103)")
    for e in errors:
        print(e)
    print(f"vendored mypy: total {sum(got.values())}, baseline {sum(base.values())}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
