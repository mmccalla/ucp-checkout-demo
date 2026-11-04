"""Validators for the composed checkout schemas in contracts/composed/ (S2).

`tools/contracts/compose.py` makes these files with the pinned ucp-schema CLI. The files
are self-contained (each `$ref` is `#` or an embedded `$id`). The loader checks each file
against contracts/composed/manifest.sha256 before use.
"""

from __future__ import annotations

import functools
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .constants import ROOT

COMPOSED = ROOT / "contracts" / "composed"
NAMES = ("checkout.create_request", "checkout.update_request", "checkout.read_response")


class ComposedError(Exception):
    pass


@dataclass(frozen=True)
class Problem:
    path: str
    message: str


def _manifest() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (COMPOSED / "manifest.sha256").read_text().splitlines():
        digest, name = line.split(None, 1)
        out[name.strip()] = digest
    return out


@functools.lru_cache(maxsize=None)
def validator(name: str) -> Draft202012Validator:
    if name not in NAMES:
        raise ComposedError(f"unknown composed schema {name}")
    fname = f"{name}.json"
    raw = (COMPOSED / fname).read_bytes()
    if hashlib.sha256(raw).hexdigest() != _manifest().get(fname):
        raise ComposedError(f"{fname}: sha256 does not match contracts/composed/manifest.sha256")
    schema: dict[str, Any] = json.loads(raw)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def problems(name: str, instance: Any) -> list[Problem]:
    errs = sorted(validator(name).iter_errors(instance), key=lambda e: list(e.absolute_path))
    out = []
    for e in errs:
        path = "$" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in e.absolute_path)
        out.append(Problem(path, e.message))
    return out


def names() -> list[str]:
    """Return the composed schema names in the manifest (without `.json`)."""
    return sorted(n.removesuffix(".json") for n in _manifest())
