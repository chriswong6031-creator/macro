#!/usr/bin/env bash
# scripts/launchd/theta_daily_refresh.sh
#
# Thin exec wrapper for the AD-1T1 daily incremental ThetaData T1 maintainer.
# Invoked by launchd (com.macro.thetadata-daily.plist) at four bounded fire
# points per market day. ALL gating logic (session/time gate, flock,
# deadline, receipt) lives in python — `scripts/topup_thetadata_day.py --daily`
# — and is unit-tested there. This wrapper does env/log plumbing only; it
# must never grow an `if` that decides whether to run.
#
# See research/AD1T1_INCREMENTAL_CADENCE_SPEC_2026-08-22.md §E and
# research/THETADATA_OPS_RUNBOOK.md for the install/transition procedure.

set -uo pipefail

# Full path to the conda python that has pandas/pyarrow/requests. launchd's
# PATH is /usr/bin:/bin:/usr/sbin:/sbin — bare 'python' is not found (exit 127).
PYTHON="/opt/homebrew/Caskroom/miniconda/base/bin/python"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}"

exec "${PYTHON}" -m scripts.topup_thetadata_day --daily
