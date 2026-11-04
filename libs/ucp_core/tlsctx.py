"""TLS client context for the loopback layout (T-90).

The process trusts the Caddy local CA only for its own connections. No system trust store
changes (Mark's approval is needed for that). TLS 1.3 minimum.
"""

from __future__ import annotations

import os
import ssl

from .constants import ROOT


def ca_file() -> str:
    return os.environ.get(
        "UCP_LOCAL_CA", str(ROOT / ".run/xdg-data/caddy/pki/authorities/local/root.crt")
    )


def client_context() -> ssl.SSLContext | bool:
    """Return a context that trusts the Caddy root CA, or True (system CAs) if it is absent."""
    ca = ca_file()
    if os.path.exists(ca):
        ctx = ssl.create_default_context(cafile=ca)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        return ctx
    return True
