"""Gate G4: pytest gate (see pytest_gate.py and gates.toml [pytest_paths.G4])."""

import sys

from pytest_gate import run_gate

if __name__ == "__main__":
    sys.exit(run_gate("G4"))
