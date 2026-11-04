"""Pinned protocol values (pins/PINS.toml). Do not change them without a new pin decision."""

import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
UCP_VERSION = "2026-04-08"  # https://ucp.dev/2026-04-08/specification/overview/
UCP_SCHEMA_BASE = "https://ucp.dev/2026-04-08/schemas/"
UCP_MIXED_SCHEMA_BASE = "https://ucp.dev/2026-01-23/schemas/"  # [ucp_mixed_version], D.1.1
GPAY_HANDLER = "com.google.pay"
GPAY_VERSION = "2026-01-23"  # Google handler page: version "must be 2026-01-23"
GPAY_SPEC = "https://pay.google.com/gp/p/ucp/2026-01-23/"
GPAY_SCHEMA_BASE = "https://pay.google.com/gp/p/ucp/2026-01-23/schemas/"
GPAY_SCHEMA = GPAY_SCHEMA_BASE + "config.json"
GPAY_INSTRUMENT_SCHEMA = GPAY_SCHEMA_BASE + "card_payment_instrument.json"
SHOPPING_SERVICE = "dev.ucp.shopping"
LOOPBACK_HOST = os.environ.get("LOOPBACK_HOST", "127.0.0.1")
PROFILE_CACHE_CONTROL = "public, max-age=300"  # overview "Hosting": public and max-age >= 60
MAX_PROFILE_BYTES = 1024 * 1024  # overview "Fetching": SHOULD be >= 128 KiB


def mode() -> str:
    """Return MODE (02-design 17.4). Only `ci` and `demo` are valid. The default is `demo`."""
    m = os.environ.get("MODE", "demo")
    if m not in ("ci", "demo"):
        raise ValueError(f"MODE must be ci or demo, not {m!r}")
    return m
