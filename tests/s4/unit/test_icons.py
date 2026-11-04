"""UX-4.4.1: the source label icons are vendored Material Symbols with pinned sha256 values.

Source: https://github.com/google/material-design-icons at commit
10ecc14790612ca8fd164e3f4ffe9c16fc50d5b7, files symbols/web/<name>/materialsymbolsoutlined/
<name>_24px.svg. Licence: Apache-2.0 (LICENSE at the same commit). The codepoints file
variablefont/MaterialSymbolsOutlined[FILL,GRAD,opsz,wght].codepoints gives `laptop` and `computer`
the same codepoint (e31e). The repository has no `laptop` folder, so laptop.svg is computer_24px.svg.
The page loads no icon font and calls no CDN at runtime.
"""

from __future__ import annotations

import hashlib
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]
WEB = ROOT / "platform/web/checkout"
VENDOR = WEB / "vendor/material-symbols"
PINNED = {
    "history.svg": "9dbbac013fd1a1fa4677670e64164f953647e32878c2870909a3e0910f28b0d9",
    "laptop.svg": "e341b4ac9d81fd291cbe6cc6dce3b0b367f500837460b4962e7fdb9686edd792",
    "science.svg": "8798e7d12cc1eac54595c2b4a28a9eabbdfe23f6735cb4cdf9f74ce3943949c2",
    "sync_alt.svg": "d2d6d855bff76057a3896cf21f73d2e57c9ea64ad1c6a7b4ed28af063f999b1a",
    "theater_comedy.svg": "40aa67c13edfc7a361dcd7c5be06033b740a7e94fe70c63d1c9100d928665fe1",
    "LICENSE": "58d1e17ffe5109a7ae296caafcadfdbe6a7d176f0bc4ab01e12a689b0499d8bd",
}
MAP = {
    "live": "sync_alt",
    "recorded": "history",
    "gpaytest": "science",
    "simulated": "theater_comedy",
    "local": "laptop",
}


def test_vendored_files_match_pinned_sha256() -> None:
    for name, sha in PINNED.items():
        assert hashlib.sha256((VENDOR / name).read_bytes()).hexdigest() == sha, name
    assert "Apache License" in (VENDOR / "LICENSE").read_text()


def test_app_js_icons_are_the_vendored_paths() -> None:
    js = (WEB / "app.js").read_text()
    for key, name in MAP.items():
        d = re.search(r'<path d="([^"]+)"', (VENDOR / f"{name}.svg").read_text())
        assert d is not None
        line = next(x for x in js.splitlines() if x.strip().startswith(f"{key}: '<svg"))
        assert d.group(1) in line and 'aria-hidden="true"' in line, key


def test_no_runtime_cdn_for_icons() -> None:
    for f in ("app.js", "index.html", "app.css"):
        t = (WEB / f).read_text()
        assert "fonts.googleapis" not in t and "fonts.gstatic" not in t, f
