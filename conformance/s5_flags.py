"""pytest plugin for G5: give the suite its input files without a change to the suite.

The suite reads absl flags. Its README shows `pytest --conformance_input=...`, but its
`conftest.py` has no pytest options. This plugin sets the flags after the suite has defined them.
"""

from __future__ import annotations

import os
from typing import Any


def pytest_sessionstart(session: Any) -> None:
    del session
    from integration_test_utils import FLAGS  # type: ignore[import-not-found]  # the suite

    FLAGS.conformance_input = os.environ["S5_CONFORMANCE_INPUT"]
    FLAGS.fixture_config = os.environ["S5_FIXTURE_CONFIG"]
