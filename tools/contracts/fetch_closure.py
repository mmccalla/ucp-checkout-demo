"""Compute the `$ref` closure of the root contracts and compare it with the manifest.

Roots: the 22 A.4 files (checkout, order, profile, transports and the Google handler files).
The script follows each absolute `$ref` under a pinned base (schema_registry.BASES). It reads
only the local copies. It reports a file that the closure needs but the manifest does not list,
and a manifest file that the closure does not need. It does not change any file (dry run).
Usage: uv run --no-sync python tools/contracts/fetch_closure.py
"""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Any
from urllib.parse import urldefrag

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "libs"))

from ucp_core.schema_registry import BASES, read_manifest  # noqa: E402

ROOTS = [
    "ucp-schemas/ucp.json",
    "ucp-schemas/discovery/profile.json",
    "ucp-schemas/shopping/checkout.json",
    "ucp-schemas/shopping/fulfillment.json",
    "ucp-schemas/shopping/order.json",
    "ucp-schemas/transports/embedded_config.json",
    "gpay-handler/config.json",
    "gpay-handler/card_payment_instrument.json",
]


def rel_for(url: str) -> str | None:
    for top, base in BASES.items():
        if url.startswith(base):
            return f"{top}/{url[len(base) :]}"
    return None


def refs(doc: Any, base: str) -> set[str]:
    out: set[str] = set()
    if isinstance(doc, dict):
        for k, v in doc.items():
            if k == "$ref" and isinstance(v, str) and not v.startswith("#"):
                url = urldefrag(v)[0]
                if not url.startswith("https://"):
                    url = base.rsplit("/", 1)[0] + "/" + url
                out.add(url)
            else:
                out |= refs(v, base)
    elif isinstance(doc, list):
        for v in doc:
            out |= refs(v, base)
    return out


def main() -> int:
    manifest = read_manifest(ROOT / "pins/schema-manifest.sha256")
    seen: set[str] = set()
    todo = [r for r in ROOTS if r in manifest]
    missing: set[str] = set()
    outside: set[str] = set()
    while todo:
        rel = todo.pop()
        if rel in seen:
            continue
        seen.add(rel)
        p = ROOT / "contracts" / rel
        if not p.exists():
            missing.add(rel)
            continue
        doc = json.loads(p.read_text())
        for url in refs(doc, doc.get("$id", "")):
            r = rel_for(url)
            if r is None:
                outside.add(url)
            elif r not in seen:
                todo.append(r)
    not_listed = sorted(r for r in seen if r not in manifest)
    unused = sorted(r for r in manifest if r not in seen)
    print(f"closure files={len(seen)} manifest files={len(manifest)}")
    for r in not_listed:
        print(f"NOT IN MANIFEST {r}")
    for r in sorted(missing):
        print(f"MISSING LOCAL COPY {r}")
    for u in sorted(outside):
        print(f"REF OUTSIDE PINNED BASES {u}")
    for r in unused:
        print(f"IN MANIFEST, NOT IN CLOSURE {r}")
    ok = not not_listed and not missing and not outside
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
