"""RFC 9421 request signatures for UCP (T-04), from the vendored sample `ucp_signing.py`.

The samples copy (`business/src/ucp_sample_server/ucp_signing.py`, commit `e7c9c12`) has the
signer and the verifier ("Used by the demo client and the tests"). This module loads that one
file by path, so the Platform and the tests use the same code as the Business. There is no
second implementation.
"""

from __future__ import annotations

import importlib.util
import sys
from types import ModuleType
from typing import Any

from ucp_core.constants import ROOT

_PATH = ROOT / "business" / "src" / "ucp_sample_server" / "ucp_signing.py"


def _load() -> ModuleType:
    if "ucp_signing" in sys.modules:
        return sys.modules["ucp_signing"]
    spec = importlib.util.spec_from_file_location("ucp_signing", _PATH)
    if spec is None or spec.loader is None:
        raise ImportError(str(_PATH))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ucp_signing"] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load()


def sign_request(
    private_key: Any, kid: str, method: str, url: str, headers: dict[str, str], body: bytes
) -> dict[str, str]:
    """Return the headers to add: Content-Digest (with a body), Signature-Input, Signature."""
    out: dict[str, str] = _mod.sign_request(private_key, kid, method, url, headers, body)
    return out


SignatureError: type[Exception] = _mod.SignatureError


def verify_request(
    method: str,
    authority: str,
    path: str,
    query: str,
    headers: dict[str, str],
    body: bytes,
    keys: list[dict[str, Any]],
) -> str:
    """Verify an inbound request (the sample verifier). Return the `keyid`."""
    kid: str = _mod.verify_request(method, authority, path, query, headers, body, keys)
    return kid


# S4 (AC-66 to AC-68, T-04): the demo also requires that a webhook signature covers the
# Standard Webhooks headers. The sample signer covers them (`extra_components`). This is a
# design choice: signatures.md (9c9d6fc) gives only the request floor.
WEBHOOK_COMPONENTS = ("webhook-id", "webhook-timestamp")


def verify_webhook(
    authority: str, path: str, headers: dict[str, str], body: bytes, keys: list[dict[str, Any]]
) -> str:
    """Verify an order webhook (order.md "Verification (Platform)"). Return the `keyid`.

    `headers` must have lower-case names. Raise SignatureError (401 or 400) on a problem.
    """
    parsed = _mod.parse_signature_input(headers.get("signature-input", "")) or {}
    for name in WEBHOOK_COMPONENTS:
        if name not in headers:
            raise SignatureError("signature_invalid", 401, f"The {name} header is missing.")
    if parsed and not any(set(WEBHOOK_COMPONENTS) <= set(d["components"]) for d in parsed.values()):
        raise SignatureError(
            "signature_invalid",
            401,
            "The signature does not cover webhook-id and webhook-timestamp.",
        )
    return verify_request("POST", authority, path, "", headers, body, keys)


def sign_response(
    private_key: Any, kid: str, status: int, headers: dict[str, str], body: bytes
) -> dict[str, str]:
    """REST response signing (signatures.md "REST Response Signing", `@status`).

    Return the headers to add: Content-Digest (with a body), Signature-Input, Signature.
    """
    import base64
    import time

    merged = {k.lower(): v for k, v in headers.items()}
    add: dict[str, str] = {}
    components = ["@status"]
    if body:
        add["content-digest"] = merged["content-digest"] = _mod.content_digest(body)
        merged.setdefault("content-type", "application/json")
        components += ["content-digest", "content-type"]
    raw = (
        "(" + " ".join(f'"{c}"' for c in components) + f');created={int(time.time())};keyid="{kid}"'
    )

    def resolve(name: str) -> str | None:
        return str(status) if name == "@status" else merged.get(name)

    base = _mod.build_signature_base(components, raw, resolve)
    sig = _mod._raw_sign(private_key, base)
    add["signature-input"] = f"sig1={raw}"
    add["signature"] = "sig1=:" + base64.b64encode(sig).decode("ascii") + ":"
    return add


def verify_response(
    status: int, headers: dict[str, str], body: bytes, keys: list[dict[str, Any]]
) -> str:
    """REST response verification (signatures.md "REST Response Verification").

    `headers` must have lower-case names. Return the `keyid`. Raise SignatureError.
    """
    sig_input = _mod.parse_signature_input(headers.get("signature-input", ""))
    sigs = _mod.parse_signature(headers.get("signature", ""))
    if not sig_input or not sigs:
        raise SignatureError("signature_missing", 401, "The response is not signed.")
    required = ["@status"] + (["content-digest", "content-type"] if body else [])
    by_kid = {k.get("kid"): k for k in keys}
    last: Exception = SignatureError("signature_invalid", 401, "No valid signature found.")
    for label, desc in sig_input.items():
        sig = sigs.get(label)
        if sig is None:
            continue
        if not set(required) <= set(desc["components"]):
            last = SignatureError("signature_invalid", 401, "Required components missing.")
            continue
        if body and not _mod.content_digest_matches(headers.get("content-digest", ""), body):
            last = SignatureError("digest_mismatch", 400, "Content-Digest does not match.")
            continue
        kid = desc["params"].get("keyid")
        jwk = by_kid.get(kid)
        if jwk is None:
            last = SignatureError("key_not_found", 401, f"No published key with kid={kid!r}.")
            continue

        def resolve(name: str) -> str | None:
            if name == "@status":
                return str(status)
            v = headers.get(name)
            return v.strip() if isinstance(v, str) else None

        base = _mod.build_signature_base(desc["components"], desc["raw"], resolve)
        if base is None:
            last = SignatureError("signature_invalid", 401, "Unresolvable component.")
            continue
        try:
            _mod.verify_raw_signature(jwk, base, sig)
        except Exception as e:  # noqa: BLE001  (the sample raises SignatureError)
            last = e
            continue
        return str(kid)
    raise last
