"""S1 fixtures: one offline schema registry for the session."""

from __future__ import annotations

import pytest
from ucp_core.schema_registry import SchemaRegistry


@pytest.fixture(scope="session")
def reg() -> SchemaRegistry:
    return SchemaRegistry.load()
