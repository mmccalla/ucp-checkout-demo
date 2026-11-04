"""One place for the evidence directory of the tests.

The base directory is the environment variable UCP_EVIDENCE_DIR. If it is not set, the base
is `.run/evidence` in the repository (Git ignores `.run`). A test never writes to a fixed
absolute path, so the tests also run on a CI runner and in a clean clone.
The old per-slice variable S3_EVIDENCE still sets the directory of the S3 e2e tests.
"""

from __future__ import annotations

import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def base() -> pathlib.Path:
    value = os.environ.get("UCP_EVIDENCE_DIR")
    return pathlib.Path(value) if value else ROOT / ".run" / "evidence"


def evidence_dir(*parts: str) -> pathlib.Path:
    """Return `<base>/<parts>` and create it."""
    path = base().joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path
