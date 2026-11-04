"""Business profile at `/.well-known/ucp` (FR-01, AC-02, AC-106, AC-107).

- Template per MODE in `business/profile/` (02-design 17.4). The CI profile adds only the
  `mock_payment_handler` declaration.
- `endpoint` is the public TLS origin (Caddy, T-90), not the loopback app address.
- The public ES256 key is in `signing_keys` (canonical) and in the `keys` mirror (T-04). The
  overview requires the same `kid` set and equal RFC 7638 thumbprints in both arrays.
- `Cache-Control: public, max-age=300` (overview "Hosting": `public`, `max-age` >= 60).
"""

from __future__ import annotations

import json
import os
import pathlib
from typing import Any

from ucp_core.constants import PROFILE_CACHE_CONTROL, ROOT

PROFILE_DIR = ROOT / "business" / "profile"
DEFAULT_ORIGIN = "https://localhost:9443"
CACHE_CONTROL = PROFILE_CACHE_CONTROL


def origin() -> str:
    return os.environ.get("BUSINESS_ORIGIN", DEFAULT_ORIGIN).rstrip("/")


def build(mode: str, jwk: dict[str, Any], endpoint: str) -> dict[str, Any]:
    text = (PROFILE_DIR / f"{mode}.json").read_text()
    profile: dict[str, Any] = json.loads(text.replace("{{ENDPOINT}}", endpoint))
    profile["signing_keys"] = [jwk]
    profile["keys"] = [dict(jwk)]
    return profile


def key_file() -> pathlib.Path:
    return pathlib.Path(
        os.environ.get("BUSINESS_KEY_FILE", str(ROOT / ".run/keys/business-es256.pem"))
    )
