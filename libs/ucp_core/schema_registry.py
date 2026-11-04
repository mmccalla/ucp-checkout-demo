"""Offline JSON Schema registry for the pinned contracts (AC-86, AC-87, AC-105, TC-MV5, TC-MV6).

Rules (input-data D.1, D.1.1):
- Load only the local copies in `contracts/`. Each copy must have the sha256 in
  `pins/schema-manifest.sha256`, else the load stops (AC-88, TC-MV5).
- Each `$id` must be a versioned URL under an allowed base, and it must equal the URL that the
  local path gives. An unversioned `$id` or a duplicate `$id` stops the load (TC-MV6).
- A `$ref` to a URL that is not in the registry raises. The registry never uses the network.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource

from .constants import GPAY_SCHEMA_BASE, ROOT, UCP_MIXED_SCHEMA_BASE, UCP_SCHEMA_BASE

DRAFT = "https://json-schema.org/draft/2020-12/schema"
BASES = {
    "ucp-schemas": UCP_SCHEMA_BASE,
    "ucp-schemas-2026-01-23": UCP_MIXED_SCHEMA_BASE,
    "gpay-handler": GPAY_SCHEMA_BASE,
}
# Refusal list (AC-87, TC-MV6).
# The 2 alias lines below hold the exact strings that the registry must refuse (`$id` check and
# `validator()`). They are data for a refusal, not a source. G1 (AC-118) flags a `ucp.dev` alias
# outside `tests/`. The marker is not allowed here (T-108, clause 3). G1 exempts these 2 lines
# by name (T-116, APPROVED): `ast` match on `FORBIDDEN`, exact strings, count 2. See
# `docs/G1-alias-exception-APPROVED-T-116.md`.
FORBIDDEN = (
    "https://ucp.dev/latest/",
    "https://ucp.dev/draft/",
    "https://ucp.dev/schemas/",
)


class RegistryError(Exception):
    """The registry cannot be used. The build must stop."""


@dataclass(frozen=True)
class Issue:
    path: str
    message: str


def read_manifest(path: pathlib.Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            digest, rel = line.split()
            rows[rel] = digest
    return rows


def expected_id(rel: str) -> str:
    top, rest = rel.split("/", 1)
    if top not in BASES:
        raise RegistryError(f"{rel}: no pinned base for folder {top}")
    return BASES[top] + rest


def _retrieve(uri: str) -> Resource[Any]:
    raise NoSuchResource(ref=uri)  # type: ignore[call-arg]  # offline only (AC-87): no fetch for an unknown $ref


class SchemaRegistry:
    def __init__(self, files: dict[str, pathlib.Path], manifest: dict[str, str]):
        self.ids: dict[str, str] = {}
        resources: list[tuple[str, Resource[Any]]] = []
        for rel, p in sorted(files.items()):
            body = p.read_bytes()
            digest = hashlib.sha256(body).hexdigest()
            if manifest.get(rel) != digest:
                raise RegistryError(f"{rel}: sha256 {digest} is not in the manifest (TC-MV5)")
            doc = json.loads(body)
            sid = doc.get("$id", "")
            if doc.get("$schema") != DRAFT:
                raise RegistryError(f"{rel}: $schema is not draft 2020-12 (AC-86)")
            if not sid or sid.startswith(FORBIDDEN):
                raise RegistryError(f"{rel}: unversioned or forbidden $id {sid!r} (TC-MV6)")
            if sid != expected_id(rel):
                raise RegistryError(f"{rel}: $id {sid} is not {expected_id(rel)} (TC-MV5)")
            if sid in self.ids:
                raise RegistryError(f"{rel}: duplicate $id {sid} (TC-MV6)")
            self.ids[sid] = rel
            resources.append((sid, Resource.from_contents(doc)))
        self.registry: Registry[Any] = Registry(retrieve=_retrieve).with_resources(resources)  # type: ignore[call-arg]

    @classmethod
    def load(cls, root: pathlib.Path = ROOT) -> SchemaRegistry:
        manifest = read_manifest(root / "pins" / "schema-manifest.sha256")
        files = {rel: root / "contracts" / rel for rel in manifest}
        for rel, p in files.items():
            if not p.exists():
                raise RegistryError(f"{rel}: listed in the manifest but missing")
        return cls(files, manifest)

    def validator(self, schema_url: str) -> Draft202012Validator:
        if schema_url.startswith(FORBIDDEN):
            raise RegistryError(f"forbidden schema URL {schema_url} (AC-87)")
        return Draft202012Validator(
            {"$schema": DRAFT, "$ref": schema_url},
            registry=self.registry,
            format_checker=Draft202012Validator.FORMAT_CHECKER,
        )

    def validate_document(self, instance: Any, schema: dict[str, Any]) -> list[Issue]:
        """Validate with a schema document that only composes pinned schemas by `$ref`.

        Each `$ref` is resolved in this registry (offline). A forbidden URL is refused.
        """
        text = json.dumps(schema)
        if any(f in text for f in FORBIDDEN):
            raise RegistryError("forbidden schema URL in a schema document (AC-87)")
        v = Draft202012Validator(
            schema, registry=self.registry, format_checker=Draft202012Validator.FORMAT_CHECKER
        )
        return [Issue(e.json_path, e.message) for e in v.iter_errors(instance)]

    def validate(self, instance: Any, schema_url: str) -> list[Issue]:
        """Return all issues. An empty list is PASS. A missing `$ref` target raises."""
        v = self.validator(schema_url)
        return [Issue(e.json_path, e.message) for e in v.iter_errors(instance)]
