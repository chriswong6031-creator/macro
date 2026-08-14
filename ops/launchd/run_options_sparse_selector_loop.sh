#!/bin/sh
# One host-private sparse-selector attempt.
#
# launchd owns the 300-second cadence.  Python owns the America/New_York slot,
# source/evidence authentication, replay, and no-op decision; this shell must
# never add a second clock or retry loop.  The fixed sealed runtime and fixed
# clean operational checkout are part of the installation receipt boundary.

set -u
umask 077

SEALED_PYTHON="/Users/chriswong/.mastermind_private/options_sparse_selector_runtime_v1/runtime/bin/python3.12"
REPO_ROOT="/Users/chriswong/options-sparse-selector-ops-wt"
RUNNER="/Users/chriswong/options-sparse-selector-ops-wt/scripts/run_options_sparse_selector.py"

if [ ! -x "$SEALED_PYTHON" ] || [ -L "$SEALED_PYTHON" ]; then
    echo "options sparse selector refused: sealed Python is unavailable" >&2
    exit 2
fi
if [ ! -f "$RUNNER" ] || [ -L "$RUNNER" ]; then
    echo "options sparse selector refused: fixed runner is unavailable" >&2
    exit 2
fi
SCRIPT_DIR=${0%/*}
ACTUAL_REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd -P) || exit 2
if [ "$ACTUAL_REPO_ROOT" != "$REPO_ROOT" ]; then
    echo "options sparse selector refused: launcher is outside the dedicated checkout" >&2
    exit 2
fi

cd "$REPO_ROOT" || exit 2
exec "$SEALED_PYTHON" -I -S -B "$RUNNER" --run-once
