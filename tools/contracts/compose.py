"""Make the composed checkout schemas in contracts/composed/ with the pinned ucp-schema CLI.

The CLI composes checkout and the fulfillment extension (the checkout capabilities of the demo
Business profile), then resolves the `ucp_request` annotations for each operation.
Usage: compose.py [--check]. With --check, it compares the new output to the files in Git.
The CLI command for each file is in contracts/composed/README.md.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "contracts" / "composed"
BIN = os.environ.get("UCP_SCHEMA_BIN", str(ROOT.parent / "tools" / "bin" / "ucp-schema"))
BASE = [
    "--schema-local-base",
    "contracts/ucp-schemas",
    "--schema-remote-base",
    "https://ucp.dev/2026-04-08/schemas",
]
OPS = [("request", "create"), ("request", "update"), ("response", "read")]


def payload() -> dict[str, object]:
    prof = json.loads((ROOT / "business" / "profile" / "demo.json").read_text())
    # The CLI needs one root capability (checkout). Order is a separate surface (webhook), and
    # the catalog capabilities are separate roots with their own schemas. None is composed here.
    skip = ("dev.ucp.shopping.order", "dev.ucp.shopping.catalog.")
    caps = {k: v for k, v in prof["ucp"]["capabilities"].items() if not k.startswith(skip)}
    return {"ucp": {"version": prof["ucp"]["version"], "capabilities": caps}, "id": "compose"}


def build(tmp: pathlib.Path) -> dict[str, bytes]:
    src = tmp / "self-describing.json"
    src.write_text(json.dumps(payload(), indent=2, sort_keys=True))
    out: dict[str, bytes] = {}
    for direction, op in OPS:
        dst = tmp / f"checkout.{op}_{direction}.json"
        subprocess.run(
            [
                BIN,
                "resolve",
                str(src),
                f"--{direction}",
                "--op",
                op,
                *BASE,
                "--pretty",
                "--output",
                str(dst),
            ],
            cwd=ROOT,
            check=True,
        )
        out[dst.name] = dst.read_bytes()
    out["self-describing.json"] = src.read_bytes()
    return out


def main() -> int:
    check = "--check" in sys.argv
    with tempfile.TemporaryDirectory() as t:
        files = build(pathlib.Path(t))
    manifest = "".join(f"{hashlib.sha256(b).hexdigest()}  {n}\n" for n, b in sorted(files.items()))
    if check:
        bad = [n for n, b in files.items() if (OUT / n).read_bytes() != b]
        if (OUT / "manifest.sha256").read_text() != manifest:
            bad.append("manifest.sha256")
        print("composed schemas:", "DIFF " + ",".join(bad) if bad else "SAME")
        return 1 if bad else 0
    OUT.mkdir(parents=True, exist_ok=True)
    for n, b in files.items():
        (OUT / n).write_bytes(b)
    (OUT / "manifest.sha256").write_text(manifest)
    print(manifest, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
