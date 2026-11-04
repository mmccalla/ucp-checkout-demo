"""Error bodies of the Business (spec T-102, AC-89, ADR 0006).

- Protocol errors (401, 403, 409, 422, 424, 429, 500, 503, and the HTTP 400 codes
  `invalid_profile_url`, `digest_mismatch`, `algorithm_unsupported`): a JSON body with
  `code` and `content`. 422 and 424 can have `continue_url`. 429 and 503 send `Retry-After`.
  Source: checkout-rest.md lines 1275-1276, overview.md lines 804-833 and 862-886 (UCP
  commit 9c9d6fc). UNVERIFIED: no pinned schema defines this body (T-102).
- A request that fails schema validation: `error_response`, HTTP 400, code `invalid_request`.
- A business outcome with no checkout (all items out of stock, unknown checkout id):
  `error_response` with HTTP 200 (checkout.md lines 141-145, checkout-rest.md 1319-1320).
"""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse
from ucp_core.constants import UCP_VERSION

PROTOCOL_STATUSES = {401, 403, 409, 422, 424, 429, 500, 503}
PROTOCOL_400_CODES = {"invalid_profile_url", "digest_mismatch", "algorithm_unsupported"}


def protocol(
    status: int,
    code: str,
    content: str,
    retry_after: int | None = None,
    continue_url: str | None = None,
) -> JSONResponse:
    if status not in PROTOCOL_STATUSES and not (status == 400 and code in PROTOCOL_400_CODES):
        raise ValueError(f"HTTP {status} {code} is not a T-102 protocol error")
    body: dict[str, Any] = {"code": code, "content": content}
    if continue_url and status in (422, 424):
        body["continue_url"] = continue_url
    headers = {}
    if status in (429, 503):
        headers["Retry-After"] = str(retry_after if retry_after is not None else 1)
    return JSONResponse(body, status_code=status, headers=headers)


def message(code: str, content: str, severity: str, path: str | None = None) -> dict[str, Any]:
    m: dict[str, Any] = {"type": "error", "code": code, "content": content, "severity": severity}
    if path:
        m["path"] = path
    return m


def error_response(messages: list[dict[str, Any]], status: int = 200) -> JSONResponse:
    body = {"ucp": {"version": UCP_VERSION, "status": "error"}, "messages": messages}
    return JSONResponse(body, status_code=status)


def invalid_request(problems: list[tuple[str, str]]) -> JSONResponse:
    msgs = [message("invalid_request", text, "recoverable", path) for path, text in problems[:10]]
    if not msgs:
        msgs = [message("invalid_request", "The request is not valid.", "recoverable")]
    return error_response(msgs, status=400)
