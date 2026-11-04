"""Root fixtures: in-process tests write data and timeline rows to a temporary folder."""

from __future__ import annotations

import os
import tempfile

import pytest


def pytest_configure(config: pytest.Config) -> None:
    del config
    tmp = tempfile.mkdtemp(prefix="ucp-tests-")
    os.environ.setdefault("BUSINESS_DATA_DIR", os.path.join(tmp, "business"))
    os.environ.setdefault("BUSINESS_EVENTS", os.path.join(tmp, "business.jsonl"))
    os.environ.setdefault("PLATFORM_EVENTS", os.path.join(tmp, "platform.jsonl"))
