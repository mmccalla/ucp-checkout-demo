"""Run the pinned ucp-schema binary (UCP_SCHEMA_BIN) with the given arguments."""

import os
import subprocess
import sys

if __name__ == "__main__":
    sys.exit(
        subprocess.run([os.environ.get("UCP_SCHEMA_BIN", "ucp-schema"), *sys.argv[1:]]).returncode
    )
