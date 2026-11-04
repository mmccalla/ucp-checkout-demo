"""Gate G3: pytest gate (see pytest_gate.py and gates.toml [pytest_paths.G3])."""

import sys

from pytest_gate import run_gate

if __name__ == "__main__":
    sys.exit(run_gate("G3"))
