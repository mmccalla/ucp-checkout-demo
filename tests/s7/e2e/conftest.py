"""S7 e2e: the fixtures of the G7 harness (`tests/s3/e2e/conftest.py`).

The browser fixture has module scope, as in S3. See the comment there and
`tests/s3/e2e/test_loop_released.py`.
"""

from __future__ import annotations

from tests.s3.e2e.conftest import browser, make_stack, reg, server

__all__ = ["browser", "make_stack", "reg", "server"]
