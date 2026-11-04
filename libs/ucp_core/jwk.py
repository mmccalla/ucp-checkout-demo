"""ES256 signing key and the public JWK with the RFC 7638 thumbprint as `kid` (T-04)."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import pathlib
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64(n: int) -> str:
    return base64.urlsafe_b64encode(n.to_bytes(32, "big")).rstrip(b"=").decode()


def thumbprint(jwk: dict[str, Any]) -> str:
    """RFC 7638 section 3.2 for EC keys: members crv, kty, x, y in lexical order."""
    members = {k: jwk[k] for k in ("crv", "kty", "x", "y")}
    raw = json.dumps(members, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b"=").decode()


def public_jwk(key: ec.EllipticCurvePrivateKey) -> dict[str, Any]:
    nums = key.public_key().public_numbers()
    jwk = {"kty": "EC", "crv": "P-256", "x": _b64(nums.x), "y": _b64(nums.y)}
    return {"kid": thumbprint(jwk), **jwk, "use": "sig", "alg": "ES256"}


def load_or_create(path: pathlib.Path) -> ec.EllipticCurvePrivateKey:
    if path.exists():
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey) or key.curve.name != "secp256r1":
            raise ValueError(f"{path}: not a P-256 key")
        return key
    key = ec.generate_private_key(ec.SECP256R1())
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
    return key


def ephemeral() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())
