#!/bin/sh
# ops/launchd/run_options_matrix.sh
#
# Runner for the nightly options-matrix builder (Package E).
# Invoked by com.macro.optionsmatrix.plist via run_with_env.sh.
#
# FRESHNESS GATE
# ─────────────────────────────────────────────────────────────────────────────
# Before running the matrix builder, this script verifies that the ThetaData
# EOD store contains SPY data for the expected last NYSE session.
#
# Logic:
#   1. Ask lib/nyse_calendar.expected_last_session() for the expected date.
#   2. Read only the 'date' column of the current-year SPY parquet shard
#      (column-pruned; never loads the full store).
#   3. If the latest date in the shard == expected_last_session → FRESH → run.
#   4. Otherwise sleep 20 min and retry (max 6 attempts = 2h window).
#   5. After 6 failures, log and exit 1 without running the builder.
#
# BYPASS
# ─────────────────────────────────────────────────────────────────────────────
# Set MATRIX_FRESHNESS_BYPASS=1 to skip the wait loop (used for one-shot
# smoke verification).
#
# USAGE (manual smoke):
#   source /Users/chriswong/flow-ops-wt/.env
#   MATRIX_FRESHNESS_BYPASS=1 \
#     ops/launchd/run_options_matrix.sh
#
# LOG TAILING:
#   tail -f /tmp/optionsmatrix.stdout.log /tmp/optionsmatrix.stderr.log

set -eu

# ── paths ─────────────────────────────────────────────────────────────────────
REPO="/Users/chriswong/Documents/Cluade/Macro Dashboard"
PYTHON="/opt/homebrew/Caskroom/miniconda/base/bin/python"
STORE="${THETADATA_STORE:-/Users/chriswong/theta-ops-wt/data/thetadata_eod}"

# ── freshness check helper ────────────────────────────────────────────────────
# Prints "fresh" if SPY EOD data has the expected last session, else "stale".
_check_freshness() {
    "$PYTHON" - "$STORE" "$REPO" <<'PYEOF'
import sys
from pathlib import Path
import pyarrow.parquet as pq

store = sys.argv[1]
repo  = sys.argv[2]

# resolve nyse_calendar from repo
sys.path.insert(0, repo)
from lib.nyse_calendar import expected_last_session
from datetime import datetime, timezone

expected = expected_last_session()

# column-pruned read of the current-year SPY shard only
year = expected.year
shard = Path(store) / "eod" / "SPY" / f"{year}.parquet"
if not shard.exists():
    # Fall back to prior year shard (edge: Jan 1 before new year shard written)
    shard = Path(store) / "eod" / "SPY" / f"{year - 1}.parquet"
if not shard.exists():
    print("stale")
    sys.exit(0)

tbl = pq.read_table(str(shard), columns=["date"])
if tbl.num_rows == 0:
    print("stale")
    sys.exit(0)

# date column may be datetime or date; normalize to date
import pyarrow.compute as pc
raw = tbl.column("date").to_pylist()[-1]
if hasattr(raw, "date"):
    latest = raw.date()
else:
    latest = raw

if latest >= expected:
    print("fresh")
else:
    print("stale")
PYEOF
}

# ── freshness gate ────────────────────────────────────────────────────────────
if [ "${MATRIX_FRESHNESS_BYPASS:-0}" = "1" ]; then
    echo "[options_matrix] MATRIX_FRESHNESS_BYPASS=1 — skipping freshness gate"
else
    MAX_ATTEMPTS=6
    SLEEP_SECS=1200   # 20 min

    attempt=1
    while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
        status=$(_check_freshness 2>/dev/null || echo "error")
        if [ "$status" = "fresh" ]; then
            echo "[options_matrix] store fresh (attempt $attempt/$MAX_ATTEMPTS) — proceeding"
            break
        fi
        echo "[options_matrix] store not fresh yet (attempt $attempt/$MAX_ATTEMPTS) — sleeping ${SLEEP_SECS}s"
        if [ "$attempt" -eq "$MAX_ATTEMPTS" ]; then
            echo "[options_matrix] ERROR: store still not fresh after $MAX_ATTEMPTS attempts — aborting"
            exit 1
        fi
        sleep "$SLEEP_SECS"
        attempt=$((attempt + 1))
    done
fi

# ── run builder ───────────────────────────────────────────────────────────────
echo "[options_matrix] launching build_options_matrix --publish"
cd "$REPO"
exec "$PYTHON" -m scripts.build_options_matrix --publish
