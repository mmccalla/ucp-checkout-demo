"""Gate G2: schema checks, offline (02-design 17.3, AC-86, AC-88).

1. The sha256 of each local contract copy agrees with `pins/schema-manifest.sha256` (AC-88).
2. Each pinned schema has `$schema` = JSON Schema draft 2020-12 (AC-86, first part).
3. `ucp-schema lint --strict` on the local copies gives 0 findings.
4. `ucp-schema validate` (offline, `--schema-local-base`) on the demo handler config.
5. Slice checks from `tools/gates/gates.toml` (`g2_extra`), for example the profile golden files.
Run: uv run python tools/gates/g2.py [--root DIR] [--report FILE]
"""

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import tomllib

DRAFT = "https://json-schema.org/draft/2020-12/schema"
GPAY_REMOTE = "https://pay.google.com/gp/p/ucp/2026-01-23/schemas"


def ucp_schema() -> str:
    return os.environ.get("UCP_SCHEMA_BIN", "ucp-schema")


def manifest(root: pathlib.Path) -> list[tuple[str, str]]:
    rows = []
    for line in (root / "pins/schema-manifest.sha256").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            digest, rel = line.split()
            rows.append((rel, digest))
    return rows


def check_hashes(root: pathlib.Path) -> list[str]:
    errs = []
    for rel, want in manifest(root):
        p = root / "contracts" / rel
        if not p.exists():
            errs.append(f"missing {rel}")
            continue
        got = hashlib.sha256(p.read_bytes()).hexdigest()
        if got != want:
            errs.append(f"sha256 mismatch {rel}: {got} != {want}")
    return errs


def check_draft(root: pathlib.Path) -> list[str]:
    errs = []
    for rel, _ in manifest(root):
        p = root / "contracts" / rel
        if p.exists() and json.loads(p.read_bytes()).get("$schema") != DRAFT:
            errs.append(f"{rel}: $schema is not draft 2020-12")
    return errs


def run(cmd: list[str], root: pathlib.Path) -> list[str]:
    r = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    print(f"   $ {' '.join(cmd)}  -> exit {r.returncode}")
    return [] if r.returncode == 0 else [(r.stdout + r.stderr).strip()[-2000:]]


def check_lint(root: pathlib.Path, folder: str) -> list[str]:
    return run([ucp_schema(), "lint", "--strict", f"contracts/{folder}"], root)


def check_handler_config(root: pathlib.Path) -> list[str]:
    handler = json.loads((root / "contracts/fixtures/gpay-handler-test.json").read_text())
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(handler["config"], f)
    # `--strict` stays false: the Google schema leaves `parameters` open (ADR 0001).
    return run(
        [
            ucp_schema(),
            "validate",
            "--schema",
            "contracts/gpay-handler/config.json",
            "--schema-local-base",
            "contracts/gpay-handler",
            "--schema-remote-base",
            GPAY_REMOTE,
            "--op",
            "create",
            f.name,
        ],
        root,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(pathlib.Path(__file__).resolve().parents[2]))
    ap.add_argument("--report")
    a = ap.parse_args()
    root = pathlib.Path(a.root)
    checks: dict[str, list[str]] = {
        "sha256 manifest (AC-88)": check_hashes(root),
        "draft 2020-12 (AC-86)": check_draft(root),
    }
    if not checks["sha256 manifest (AC-88)"]:
        checks["lint --strict contracts/ucp-schemas"] = check_lint(root, "ucp-schemas")
        checks["lint --strict contracts/gpay-handler"] = check_lint(root, "gpay-handler")
        checks["validate gpay-handler-test config"] = check_handler_config(root)
        gates = root / "tools/gates/gates.toml"
        if gates.exists():
            cfg = tomllib.loads(gates.read_text())
            for name, cmd in cfg.get("g2_extra", {}).get(cfg["current_slice"], {}).items():
                checks[name] = run(["uv", "run", "--no-sync", *cmd], root)
    ok = all(not v for v in checks.values())
    for name, errs in checks.items():
        print(f"{'PASS' if not errs else 'FAIL'} {name}")
        for e in errs:
            print(f"   {e}")
    print(f"G2 {'PASS' if ok else 'FAIL'}")
    if a.report:
        pathlib.Path(a.report).write_text(
            json.dumps(
                {"gate": "G2", "status": "PASS" if ok else "FAIL", "checks": checks}, indent=2
            )
        )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
