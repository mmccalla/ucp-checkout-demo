"""Gate G6: request and webhook signatures on (02-design 17.3) (see pytest_gate.py and gates.toml [pytest_paths.G6])."""

import sys

from pytest_gate import run_gate

if __name__ == "__main__":
    sys.exit(run_gate("G6"))
