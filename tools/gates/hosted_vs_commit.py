"""Compare the hosted schema copies with the pinned UCP commit (evidence only, not a gate).

The hosted site rewrites relative `$ref` values to absolute URLs, and adds `version` to some
files. The commit files use the unversioned `$id` base `https://ucp.dev/schemas/`. This script
resolves the relative refs, changes that base to the pinned base, then compares.
Usage: python tools/gates/hosted_vs_commit.py UCP_CHECKOUT_DIR
"""

import json
import pathlib
import sys
from typing import Any
from urllib.parse import urljoin

BASE = "https://ucp.dev/2026-04-08/"
HOSTED = pathlib.Path(__file__).resolve().parents[2] / "contracts" / "ucp-schemas"
SOURCE_PATH = {"discovery/profile.json": "discovery/profile_schema.json"}


UNVERSIONED = "https://ucp.dev/schemas/"


def resolve(o: Any, base: str) -> Any:
    """Resolve relative `$ref` values, and change the unversioned `$id` base to the pinned one."""
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            if k == "$ref" and isinstance(v, str) and not v.startswith("#"):
                out[k] = urljoin(base, v).replace(UNVERSIONED, BASE + "schemas/")
            elif k == "$id" and isinstance(v, str):
                out[k] = v.replace(UNVERSIONED, BASE + "schemas/")
            else:
                out[k] = resolve(v, base)
        return out
    if isinstance(o, list):
        return [resolve(v, base) for v in o]
    return o


def main(src_root: pathlib.Path) -> int:
    print("# Hosted https://ucp.dev/2026-04-08/schemas/ vs commit source/ (relative $ref resolved)")
    bad = 0
    for f in sorted(HOSTED.rglob("*.json")):
        rel = f.relative_to(HOSTED).as_posix()
        srel = SOURCE_PATH.get(rel, "schemas/" + rel)
        s = src_root / "source" / srel
        hosted = json.loads(f.read_text())
        commit = resolve(json.loads(s.read_text()), BASE + srel)
        extra = sorted(set(hosted) - set(commit))
        h2 = {k: v for k, v in hosted.items() if k not in extra}
        same = h2 == commit
        bad += not same
        print(
            f"{'SAME' if same else 'DIFF'} {rel} <- source/{srel}"
            + (f" (hosted adds: {', '.join(extra)}={[hosted[k] for k in extra]})" if extra else "")
        )
    print(f"RESULT {'PASS' if not bad else 'FAIL'} diffs={bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(pathlib.Path(sys.argv[1])))
