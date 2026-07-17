#!/usr/bin/env bash
# scripts/launchd/theta_surface_accrual.sh
#
# Nightly options-surface forward-accrual wrapper (W2 SURFACE, RIC program).
# Invoked by launchd (com.macro.thetadata-surface.plist) AFTER the nightly
# thetadata EOD backfill pass (com.macro.thetadata-backfill) has completed.
#
# CONTRACT:
#   (a) TIMING GATE: do not run before 21:00 UTC (14:00 PT / 17:00 ET) — the
#       thetadata EOD backfill refresh pass finishes by ~20:30 UTC on most nights;
#       the extra 30m ensures fresh greeks are on disk before we read them.
#   (b) DUPLICATE GUARD: exit if build_options_surface is already running.
#   (c) Run nightly forward-accrual:
#         python -m scripts.build_options_surface   (defaults to most recent date)
#   (d) If accrual exits 0, commit data/options_surface/*.parquet via the narrow
#       git commit (same pattern as the thetadata backfill narrow commit).
#   (e) Emit the liveness audit artifact (handled inside build_options_surface).
#
# PYTHON PATH: use the full conda path — launchd's default PATH is minimal.
#
# Install (once, from the ops worktree):
#   cp scripts/launchd/com.macro.thetadata-surface.plist ~/Library/LaunchAgents/
#   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.macro.thetadata-surface.plist
#
# Uninstall:
#   launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.macro.thetadata-surface.plist
#   rm ~/Library/LaunchAgents/com.macro.thetadata-surface.plist
#
# NOTE: The launchd plist MUST point to a copy of this script outside ~/Documents/
# (macOS TCC blocks exec from ~/Documents/).  The canonical ops-worktree location is:
#   /Users/chriswong/theta-ops-wt/scripts/launchd/theta_surface_accrual.sh
# Copy it there after updating (the repo copy is the source of truth).

set -uo pipefail

THETA_OPS_WT="/Users/chriswong/theta-ops-wt"
SURFACE_LOG="${THETA_OPS_WT}/surface_accrual.log"
PYTHON="/opt/homebrew/Caskroom/miniconda/base/bin/python"

# --- (a) TIMING GATE: do not run before 21:00 UTC ----------------------------
current_hhmm=$(date -u +%H%M)
if [ "${current_hhmm}" -lt "2100" ]; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] theta_surface_accrual: pre-21:00 UTC gate (${current_hhmm}) — deferring" \
        >> "${SURFACE_LOG}"
    exit 1
fi

# --- (b) DUPLICATE GUARD: exit if already running ----------------------------
if pgrep -f "build_options_surface" > /dev/null 2>&1; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] theta_surface_accrual: build_options_surface already running — skip" \
        >> "${SURFACE_LOG}"
    exit 1
fi

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] theta_surface_accrual: starting nightly accrual" \
    >> "${SURFACE_LOG}"

cd "${THETA_OPS_WT}"

# --- (c) Run nightly surface accrual -----------------------------------------
rc=0
"${PYTHON}" -m scripts.build_options_surface >> "${SURFACE_LOG}" 2>&1 || rc=$?

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] theta_surface_accrual: build_options_surface exited (status=${rc})" \
    >> "${SURFACE_LOG}"

if [ "${rc}" -ne 0 ]; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] theta_surface_accrual: accrual FAILED — skipping git commit" \
        >> "${SURFACE_LOG}"
    exit "${rc}"
fi

# --- (d) Narrow git commit: data/options_surface/*.parquet + state file ------
#         Same narrow-commit pattern as the thetadata backfill lane.
git -C "${THETA_OPS_WT}" add \
    data/options_surface/index_etf.parquet \
    data/options_surface/sector_etf.parquet \
    data/options_surface/industry_etf.parquet \
    data/options_surface/_backfill_state.json \
    2>> "${SURFACE_LOG}" || true

# Check if there is anything to commit
if git -C "${THETA_OPS_WT}" diff --cached --quiet; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] theta_surface_accrual: nothing to commit (no changes)" \
        >> "${SURFACE_LOG}"
    exit 0
fi

COMMIT_MSG="surface: nightly accrual $(date -u +%Y-%m-%dT%H:%MZ)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"

git -C "${THETA_OPS_WT}" commit -m "${COMMIT_MSG}" >> "${SURFACE_LOG}" 2>&1
commit_rc=$?

if [ "${commit_rc}" -eq 0 ]; then
    git -C "${THETA_OPS_WT}" push origin HEAD >> "${SURFACE_LOG}" 2>&1
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] theta_surface_accrual: committed and pushed surface parquets" \
        >> "${SURFACE_LOG}"
else
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] theta_surface_accrual: git commit failed (status=${commit_rc})" \
        >> "${SURFACE_LOG}"
    exit "${commit_rc}"
fi

exit 0
