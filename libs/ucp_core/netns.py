"""Network namespace facts for the CI-only seam of the conformance gate (spec T-109, T-114).

`/proc/net/dev` shows the namespace of the reader. `/sys/class/net` does not: inside `unshare`
it lists the host interfaces.
"""

from __future__ import annotations

import pathlib

PROC_NET_DEV = pathlib.Path("/proc/net/dev")


def interfaces(path: pathlib.Path = PROC_NET_DEV) -> list[str]:
    names = [ln.split(":", 1)[0].strip() for ln in path.read_text().splitlines()[2:]]
    return sorted(n for n in names if n)


def loopback_only(path: pathlib.Path = PROC_NET_DEV) -> bool:
    """True if the only interface of this namespace is `lo`."""
    try:
        return interfaces(path) == ["lo"]
    except OSError:
        return False
