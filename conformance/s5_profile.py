"""pytest plugin for G5: serve a valid platform profile to the Business (spec T-110).

The suite reads its mock agent profile from a hard-coded file, `shopping-agent-test.json`
(`AgentProfileServer.__init__` in `integration_test_utils.py` at 016ecbc). That profile has no
`services` and no `payment_handlers`, and `platform_profile` requires both (overview.md lines
354 to 358 at 9c9d6fc). This plugin replaces the profile template in memory, after the suite
has built the server. No file of the suite changes. The Business does not change.
The fixture is `conformance/input/shopping-agent-ci-profile.json`.
"""

from __future__ import annotations

import os
import pathlib
from typing import Any

FIXTURE = pathlib.Path(__file__).resolve().parent / "input" / "shopping-agent-ci-profile.json"


def install(server_cls: Any, fixture: pathlib.Path = FIXTURE) -> None:
    original = server_cls.__init__
    template = fixture.read_text()

    def init(self: Any, *args: Any, **kwargs: Any) -> None:
        original(self, *args, **kwargs)
        self._profile_template = template

    server_cls.__init__ = init


def pytest_sessionstart(session: Any) -> None:
    del session
    from integration_test_utils import AgentProfileServer  # type: ignore[import-not-found]  # the suite

    install(AgentProfileServer, pathlib.Path(os.environ.get("S5_PROFILE_FIXTURE", FIXTURE)))
