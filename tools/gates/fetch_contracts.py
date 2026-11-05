"""Download the pinned contract files and compare them with the manifest (AC-88).

Each line of `pins/schema-manifest.sha256` gives a sha256 and a local path under `contracts/`.
The first folder of the path gives the pinned base URL (see BASES). The script stops if a
hosted file does not agree with the manifest. It does not change the manifest.
Usage: uv run python tools/gates/fetch_contracts.py [--check-only]
"""

import argparse
import hashlib
import pathlib
import sys

import httpx2

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASES = {
    "ucp-schemas": "https://ucp.dev/2026-04-08/schemas/",
    "ucp-schemas-2026-01-23": "https://ucp.dev/2026-01-23/schemas/",  # [ucp_mixed_version]
    "gpay-handler": "https://pay.google.com/gp/p/ucp/2026-01-23/schemas/",
}


def manifest(root: pathlib.Path) -> list[tuple[str, str]]:
    rows = []
    for line in (root / "pins/schema-manifest.sha256").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            digest, rel = line.split()
            rows.append((rel, digest))
    return rows


def url_for(rel: str) -> str:
    top, rest = rel.split("/", 1)
    return BASES[top] + rest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-only", action="store_true", help="compare only, do not write")
    a = ap.parse_args()
    bad = 0
    with httpx2.Client(timeout=20, follow_redirects=False) as client:
        for rel, want in manifest(ROOT):
            url = url_for(rel)
            r = client.get(url)
            got = hashlib.sha256(r.content).hexdigest()
            ok = r.status_code == 200 and got == want
            bad += not ok
            print(f"{'OK  ' if ok else 'FAIL'} {r.status_code} {got} {rel} <- {url}")
            if ok and not a.check_only:
                dest = ROOT / "contracts" / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(r.content)
    print(f"RESULT {'PASS' if not bad else 'FAIL'} files={len(manifest(ROOT))} failures={bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
