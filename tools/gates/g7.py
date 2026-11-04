"""Gate G7: headless e2e with the Google Pay CI stub (see pytest_gate.py and gates.toml [pytest_paths.G7])."""

import sys

from pytest_gate import run_gate

if __name__ == "__main__":
    sys.exit(run_gate("G7"))
