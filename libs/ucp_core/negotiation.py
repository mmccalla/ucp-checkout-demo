"""Capability intersection and spec URL binding (FR-04, AC-05, AC-08, AC-09).

Algorithm from https://ucp.dev/2026-04-08/specification/overview/ ("Intersection Algorithm"):
1. Keep each business capability that the platform also declares (same name).
2. Keep the highest version in both arrays. With no mutual version, exclude the capability.
3. Remove a capability whose `extends` parent is not in the result. Repeat until no change.

Binding ("Spec URL Binding"): "The origin of these URLs MUST match the namespace authority".
The authority is the reversed first two labels (`dev.ucp` -> `ucp.dev`). A subdomain of the
authority (for example `pay.google.com` for `com.google.pay`) is accepted. That subdomain rule
is UNVERIFIED (INFERENCE): the overview shows only the exact origin.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

Caps = dict[str, list[dict[str, Any]]]


def _parents(entry: dict[str, Any]) -> list[str]:
    ext = entry.get("extends")
    if ext is None:
        return []
    return [ext] if isinstance(ext, str) else list(ext)


def intersect(business: Caps, platform: Caps) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Return (active name -> selected business entry, excluded name -> reason)."""
    active: dict[str, dict[str, Any]] = {}
    excluded: dict[str, str] = {}
    for name, entries in sorted(business.items()):
        if name not in platform:
            excluded[name] = "not declared by the platform"
            continue
        mutual = {e["version"] for e in entries} & {e["version"] for e in platform[name]}
        if not mutual:
            excluded[name] = "no mutual version"
            continue
        best = max(mutual)  # YYYY-MM-DD strings sort by date
        active[name] = next(e for e in entries if e["version"] == best)
    for name in sorted(set(platform) - set(business)):
        excluded[name] = "not declared by the business"
    changed = True
    while changed:
        changed = False
        for name, entry in list(active.items()):
            ps = _parents(entry)
            if ps and not any(p in active for p in ps):
                del active[name]
                excluded[name] = f"parent {', '.join(ps)} not active"
                changed = True
    return active, excluded


def authority(name: str) -> str:
    labels = name.split(".")
    if len(labels) < 2:
        raise ValueError(f"{name}: not a reverse-domain name")
    return f"{labels[1]}.{labels[0]}"


def binding_issues(name: str, entry: dict[str, Any]) -> list[str]:
    """Return the reasons that `spec` or `schema` does not bind to the name (empty = bound)."""
    auth = authority(name)
    out = []
    for key in ("spec", "schema"):
        url = entry.get(key)
        if url is None:
            continue
        p = urlsplit(url)
        host = p.hostname or ""
        if p.scheme != "https":
            out.append(f"{key} {url} is not https")
        elif host != auth and not host.endswith("." + auth):
            out.append(f"{key} host {host} does not bind to {name} (authority {auth})")
    return out
