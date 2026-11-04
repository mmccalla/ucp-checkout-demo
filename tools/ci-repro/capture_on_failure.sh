#!/usr/bin/env bash
# Run a command (the pytest step). Only if the command fails, keep a capture of the host and the trace.
#
# Usage: tools/ci-repro/capture_on_failure.sh <command> [args...]
#   Example: tools/ci-repro/capture_on_failure.sh uv run --no-sync pytest -q
#
# The capture folder is $UCP_CAPTURE_DIR. If it is not set: $RUNNER_TEMP/failure-capture, or
# <repository>/.run/failure-capture. The script deletes the folder at the start.
#
# Always, while the command runs:   `vmstat -t 1` writes vmstat.txt (a time stamp on each line).
#                                   The plugin ucp_failure_capture starts a Playwright trace on each
#                                   new browser context (UCP_TRACE_ON_FAILURE=1).
# Only if the command fails:        ps.txt (a `ps` snapshot after the command), dmesg.txt,
#                                   traces/*.zip (the trace of each failed e2e test, and a `ps` snapshot
#                                   at the time of each failure), and capture-info.txt.
# If the command succeeds:          the script deletes the capture folder. Nothing stays.
#
# The script does not change the command, its arguments, its timeouts or its retries.
# The exit code is the exit code of the command. A failure of the capture does not change it.
# The plugin is loaded with PYTEST_ADDOPTS. A command that is not pytest ignores that variable.
set -uo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
root=$(cd "$here/../.." && pwd)
out=${UCP_CAPTURE_DIR:-${RUNNER_TEMP:-$root/.run}/failure-capture}
if [ "$#" -eq 0 ]; then
  echo "usage: capture_on_failure.sh <command> [args...]" >&2
  exit 2
fi

rm -rf "$out"
mkdir -p "$out"
export UCP_CAPTURE_DIR="$out"
export UCP_TRACE_ON_FAILURE=1
export PYTHONPATH="$here${PYTHONPATH:+:$PYTHONPATH}"
export PYTEST_ADDOPTS="-p ucp_failure_capture${PYTEST_ADDOPTS:+ $PYTEST_ADDOPTS}"

vmstat_pid=""
stop_vmstat() {
  if [ -n "$vmstat_pid" ]; then
    kill "$vmstat_pid" 2>/dev/null
    wait "$vmstat_pid" 2>/dev/null
    vmstat_pid=""
  fi
}
trap stop_vmstat EXIT

if command -v vmstat >/dev/null 2>&1; then
  vmstat -t 1 >"$out/vmstat.txt" 2>&1 &
  vmstat_pid=$!
else
  echo "vmstat is not installed" >"$out/vmstat.txt"
fi

"$@"
rc=$?
stop_vmstat

if [ "$rc" -eq 0 ]; then
  rm -rf "$out"
  exit 0
fi

# The command failed. Keep the capture. Each step below can fail: then it writes the reason to a file.
{
  echo "command: $*"
  echo "exit code: $rc"
  echo "time (UTC): $(date -u '+%Y-%m-%d %H:%M:%S')"
  echo "kernel: $(uname -r)"
  echo "user: $(id -un) (uid $(id -u))"
} >"$out/capture-info.txt"

ps -eo pid,ppid,stat,pcpu,pmem,etime,cmd --sort=-pcpu >"$out/ps.txt" 2>&1 \
  || echo "ps: failed (exit $?)" >>"$out/capture-info.txt"

# dmesg can be restricted (kernel.dmesg_restrict). Try dmesg, then `sudo -n dmesg`. Keep the reason if both fail.
if dmesg -T >"$out/dmesg.txt" 2>"$out/dmesg.err"; then
  echo "dmesg: ok (command: dmesg -T)" >>"$out/capture-info.txt"
elif command -v sudo >/dev/null 2>&1 && sudo -n dmesg -T >"$out/dmesg.txt" 2>>"$out/dmesg.err"; then
  echo "dmesg: ok (command: sudo -n dmesg -T)" >>"$out/capture-info.txt"
else
  {
    echo "dmesg: NOT AVAILABLE. Reason from dmesg and sudo:"
    cat "$out/dmesg.err"
  } >"$out/dmesg.txt"
  echo "dmesg: not available (see dmesg.txt)" >>"$out/capture-info.txt"
fi
rm -f "$out/dmesg.err"

echo "capture kept in: $out" >&2
ls -l "$out" >&2
exit "$rc"
