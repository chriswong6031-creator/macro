#!/bin/sh
# ops/launchd/run_options_matrix.sh
#
# Runner for the nightly options-matrix builder (Package E).
# Invoked by com.macro.optionsmatrix.plist via run_with_env.sh.
#
# FRESHNESS GATE
# ─────────────────────────────────────────────────────────────────────────────
# Before running the matrix builder, this script verifies that the ThetaData
# OI store contains SPY data for the expected last NYSE session.
#
# The gate reads the OI store (not EOD) because build_matrix() resolves its
# published asof date from the OI parquet (engine/options_matrix.py line ~478:
# asof = latest date in oi_all).  Gating on EOD while the builder keys off OI
# would allow a stale-OI / fresh-EOD mismatch to slip through undetected.
#
# Logic:
#   1. Ask lib/nyse_calendar.expected_last_session() for the expected date.
#   2. Read only the 'date' column of the current-year SPY OI parquet shard
#      (column-pruned; never loads the full store).
#   3. If the latest date in the OI shard >= expected_last_session → FRESH → run.
#      (>= rather than == so a store that is ahead of the calendar does not
#      false-fail; the calendar is the floor, not the ceiling.)
#   4. Otherwise sleep 20 min and retry (max 6 attempts = 2h window).
#   5. After 6 failures, log and exit 1 without running the builder.
#
#   NOTE (early-January edge): if the new-year OI shard has not yet been
#   written, the fallback reads the prior-year shard whose last row is Dec 31
#   — this will always be stale vs a January expected date.  The runner will
#   burn all 6 retries and exit 1 every night until the new shard appears.
#   This is the safe direction (no publish on unknown data), but operators
#   should be aware of the early-January blackout window (typically 1-2 days).
#
# BYPASS
# ─────────────────────────────────────────────────────────────────────────────
# Set MATRIX_FRESHNESS_BYPASS=1 to skip the freshness wait loop and run the
# builder immediately regardless of store freshness.
#
# DRY-RUN (no publish)
# ─────────────────────────────────────────────────────────────────────────────
# Set MATRIX_NO_PUBLISH=1 to run the builder without --publish.  The builder
# writes local JSON to data/live_flow_out/options_matrix/ but does NOT upload
# to R2.  Use this for smoke / integration checks where you want to verify
# the build pipeline without touching live artifacts.
#
# USAGE (smoke / dry-run — builds locally, no R2 publish):
#   source /Users/chriswong/flow-ops-wt/.env
#   MATRIX_FRESHNESS_BYPASS=1 MATRIX_NO_PUBLISH=1 \
#     ops/launchd/run_options_matrix.sh
#
# USAGE (full publish — same as the nightly launchd run):
#   source /Users/chriswong/flow-ops-wt/.env
#   MATRIX_FRESHNESS_BYPASS=1 \
#     ops/launchd/run_options_matrix.sh
#
# LOG TAILING:
#   tail -f /tmp/optionsmatrix.stdout.log /tmp/optionsmatrix.stderr.log

set -eu

# ── paths ─────────────────────────────────────────────────────────────────────
REPO="/Users/chriswong/flow-ops-wt"
PYTHON="/opt/homebrew/Caskroom/miniconda/base/bin/python"
STORE="${THETADATA_STORE:-/Users/chriswong/theta-ops-wt/data/thetadata_eod}"

# ── freshness check helper ────────────────────────────────────────────────────
# Prints "fresh" if the SPY OI shard has the expected last session, else "stale".
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

expected = expected_last_session()

# Gate on the OI shard — build_matrix() resolves its published asof from
# the OI store, so freshness of the OI store is what actually matters.
# Gating on EOD (as before) would silently pass when EOD is fresh but OI
# lags a session, publishing a mismatched artifact.
year = expected.year
shard = Path(store) / "oi" / "SPY" / f"{year}.parquet"
if not shard.exists():
    # Edge: early Jan before the new-year OI shard is written.
    # Prior-year shard's last row is Dec 31 — always stale vs Jan expected.
    # Safe direction: will burn retries and exit 1 until shard appears.
    shard = Path(store) / "oi" / "SPY" / f"{year - 1}.parquet"
if not shard.exists():
    print("stale")
    sys.exit(0)

tbl = pq.read_table(str(shard), columns=["date"])
if tbl.num_rows == 0:
    print("stale")
    sys.exit(0)

# date column may be datetime or date; normalize to date
raw = tbl.column("date").to_pylist()[-1]
if hasattr(raw, "date"):
    latest = raw.date()
else:
    latest = raw

# >= rather than == : a store ahead of the calendar (e.g. after a holiday
# correction) should not false-fail; the calendar date is the floor.
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
if [ "${MATRIX_NO_PUBLISH:-0}" = "1" ]; then
    echo "[options_matrix] MATRIX_NO_PUBLISH=1 — launching build_options_matrix (local only, no R2 publish)"
    cd "$REPO"
    "$PYTHON" -m scripts.build_options_matrix
    BUILD_RC=$?
else
    echo "[options_matrix] launching build_options_matrix --publish"
    cd "$REPO"
    "$PYTHON" -m scripts.build_options_matrix --publish
    BUILD_RC=$?

    # ── gex_state R2 mirror ───────────────────────────────────────────────────
    # site/options_structure/gex_state/*.json are written by build_gex_board.py
    # (nightly render) and git-committed to site/, but were NEVER mirrored to R2.
    # The terminal's f=gexstate proxies R2 → 503 → GEX tab regime chip breaks.
    # Upload them here, after the matrix build, using the same R2 credentials.
    # This is idempotent — objects in R2 are simply overwritten each nightly run.
    GEX_STATE_DIR="$REPO/site/options_structure/gex_state"
    if [ -d "$GEX_STATE_DIR" ]; then
        GEX_FILES=$(find "$GEX_STATE_DIR" -name "*.json" 2>/dev/null | wc -l | tr -d ' ')
        echo "[options_matrix] uploading ${GEX_FILES} gex_state JSON(s) to R2 …"
        "$PYTHON" - "$GEX_STATE_DIR" <<'PYEOF'
import os, sys, json, pathlib, logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("gex_state_mirror")

gex_dir = pathlib.Path(sys.argv[1])
ep = os.environ.get("R2_ENDPOINT", "")
ak = os.environ.get("R2_ACCESS_KEY_ID", "")
sk = os.environ.get("R2_SECRET_ACCESS_KEY", "")
bucket = os.environ.get("R2_BUCKET", "")

if not (ep and ak and sk and bucket):
    log.warning("gex_state_mirror: R2 creds incomplete — skipping gex_state upload")
    sys.exit(0)

try:
    import boto3
    from botocore.config import Config
    kw = dict(region_name="auto", signature_version="s3v4",
              retries={"max_attempts": 3, "mode": "standard"})
    try:
        cfg = Config(**kw, request_checksum_calculation="when_required",
                     response_checksum_validation="when_required")
    except TypeError:
        cfg = Config(**kw)
    s3 = boto3.client("s3", endpoint_url=ep, aws_access_key_id=ak,
                      aws_secret_access_key=sk, config=cfg)
except Exception as e:
    log.warning("gex_state_mirror: boto3 client failed: %s", e)
    sys.exit(0)

ok = 0
fail = 0
for f in sorted(gex_dir.glob("*.json")):
    r2_key = f"options_structure/gex_state/{f.name}"
    try:
        s3.upload_file(str(f), bucket, r2_key,
                       ExtraArgs={"ContentType": "application/json"})
        log.info("gex_state_mirror: uploaded %s", r2_key)
        ok += 1
    except Exception as e:
        log.warning("gex_state_mirror: FAILED %s: %s", r2_key, e)
        fail += 1

log.info("gex_state_mirror: done ok=%d fail=%d", ok, fail)
if fail:
    sys.exit(1)
PYEOF
        GEX_RC=$?
        if [ "$GEX_RC" -ne 0 ]; then
            echo "[options_matrix] WARNING: gex_state mirror exited with rc=$GEX_RC"
        fi
    else
        echo "[options_matrix] WARNING: gex_state dir not found at $GEX_STATE_DIR — skipping mirror"
    fi
fi

exit "$BUILD_RC"

# (gex_state R2 mirror runs inline above — scripts/mirror_gex_state_r2.py remains
# available for standalone/manual mirroring.)
