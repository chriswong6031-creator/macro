#!/usr/bin/env bash
# Nightly Mastermind Terminal universe + price refresh (VPS /usr/local/bin/terminal-data).
#
# Builds the FULL multi-market manifest into a STAGING file (TERMINAL_MANIFEST) and
# ATOMICALLY swaps it over the live manifest.json only at the very end — so the live
# universe is NEVER reduced mid-run. This lets build_polygon_universe run (fresh
# flagship-37 verdicts + slices) without its 37-symbol baseline ever reaching live.
#
# Side benefit: the rebuild starts from build_polygon_universe's fresh manifest, so the
# universe is the CURRENT top-N each night (no unbounded additive drift; names that drop
# out are pruned from search — their watchlist rows + OHLC files still persist).
#
# FAILURE-GUARDED: if the staged rebuild ends below 80% of the live count, the swap is
# skipped and live is left untouched. Per-symbol OHLC/slice files write straight to the
# live dir (atomic per file). Logs to /var/log/terminal-data.log (cron 30 21 * * *).

set -u
cd /opt/terminal || exit 1
set -a; [ -f /opt/terminal/.env ] && . /opt/terminal/.env; set +a
export MACRO_REPO=/opt/macro
export MACRO_STOCKDATA="${MACRO_STOCKDATA:-/opt/macro/site/stockdata}"
PY=/opt/macro/.venv/bin/python
D=/opt/terminal/terminal/public/data
LIVE="$D/manifest.json"
STAGE="$D/manifest.staging.json"
export TERMINAL_MANIFEST="$STAGE"
ts(){ date -u "+%Y-%m-%d %H:%M:%S"; }
count(){ "$PY" -c "import json,sys;print(len(json.load(open(sys.argv[1]))['symbols']))" "$1" 2>/dev/null || echo 0; }

# ── flock: prevents concurrent fast_flagship runs from racing the nightly swap ──
LOCKFILE=/tmp/terminal-data.lock
exec 9>"$LOCKFILE" || exit 1
flock -n 9 || { echo "[$(ts)] another terminal-data holds the lock — exit"; exit 0; }
trap 'rm -f "$LOCKFILE"' EXIT

echo "[$(ts)] === terminal refresh start (staging) ==="

rm -f "$STAGE"
run(){ echo "[$(ts)] -> $*"; "$@" || echo "[$(ts)] WARN: '$*' exited $?"; }

# Snapshot the live manifest at run start: recovery artifact + shrink-guard baseline.
BAK="$D/manifest.json.bak-nightly"
START_N=$(count "$LIVE")
[ "$START_N" -gt 0 ] && cp -f "$LIVE" "$BAK"

# ── PHASE 1: flagship + fast price refresh (~5 min) ──
# flagship 37 -> staging manifest + fresh real-OHLC/slices/verdicts (OHLC/slices go to live dir)
run "$PY" -m ingest.build_polygon_universe
[ -s "$STAGE" ] || cp -f "$LIVE" "$STAGE"
# Rewrite the flagship slices with the full-basis GC-v2 emission (quality/tier/score +
# SELL confirms). The builder's indicator_contract call predates v2 — without this pass
# every flagship BUY renders "regime_blocked" and SELL pills vanish until the first RTH
# fast_flagship tick. Preserves slice.backtest verbatim; reuses/builds the cohort cache
# that gen_slices_all reuses later tonight (single build per night).
run "$PY" ingest/regen_flagship_slices.py
# Defense-in-depth: Phase 1 must NEVER touch the live manifest (only TERMINAL_MANIFEST
# staging). On 2026-07-10/11 a regressed builder that ignored TERMINAL_MANIFEST wrote its
# flagship-37 manifest straight to live, shrinking the site to 34 symbols until the final
# swap ~2h later. If live shrank during Phase 1, restore the run-start snapshot now —
# but only if tonight's snapshot is verifiably the run-start universe (guards against a
# failed snapshot cp leaving a stale/smaller bak from a prior night), and atomically
# (tmp + mv) so readers never see a half-written manifest and a concurrent atomic writer
# can't orphan the restore mid-copy.
P1_N=$(count "$LIVE")
if [ "$START_N" -gt 0 ] && [ "$P1_N" -lt "$START_N" ]; then
  if [ "$(count "$BAK")" -ge "$START_N" ]; then
    echo "[$(ts)] GUARD: live shrank $START_N -> $P1_N during phase 1 — restoring run-start snapshot"
    cp -f "$BAK" "$LIVE.restore.tmp" && mv -f "$LIVE.restore.tmp" "$LIVE"
  else
    echo "[$(ts)] GUARD: live shrank $START_N -> $P1_N but snapshot is unusable ($(count "$BAK") rows) — NOT restoring"
  fi
fi
# refresh US OHLC to the latest close via Polygon grouped-daily (1 call/date, whole US
# market). backfill_ohlc only fetches NEW symbols, so without this existing non-flagship
# OHLC (and watchlist LAST/CHG) freezes at file-creation date. Runs before hydrate so the
# fresh close flows into the manifest same night (--days 7 self-corrects any missed day).
run "$PY" ingest/refresh_ohlc.py --days 7 --write
# Note: the quote hub resolves prevClose from the per-symbol OHLC daily file (anchor.js
# resolution order: daily_file → polygon_prev → manifest fallback). refresh_ohlc.py above
# writes today's close into each SYM.json in the live data dir, so the hub sees the correct
# same-day prevClose immediately — no manifest swap is required at Phase 1.

# ── PHASE 2: full universe marathon (~3-4 hr) ──
# expand base multi-market universe + China/HK/US OHLC from the macro deep stores
run "$PY" ingest/build_universe.py --ohlc all
# US -> ~3,000 (Polygon ref+snapshot) and HK -> ~500 (akshare turnover)
run "$PY" ingest/expand_universe.py
# bilingual Chinese names (china_search name_zh + akshare 名称)
run "$PY" ingest/enrich_zh.py
# fill OHLC for any name still missing one (expanded US via Polygon, HK/Canada via yfinance)
run "$PY" ingest/backfill_ohlc.py --market all
# broad-universe confluence slices
run "$PY" ingest/gen_slices_all.py
# artifact freshness conformance
run "$PY" -m ingest.artifact_conformance
# pull macro dashboard intel bridge
run "$PY" ingest/pull_macro_intel.py
# refresh non-US OHLC (HK/CN/intl) to latest close via yfinance bulk
run "$PY" ingest/refresh_ohlc_intl.py --days 10 --write
# Final hydrate: pick up any OHLC written during Phase 2
run "$PY" ingest/hydrate_prices.py --write

# ── FINAL SWAP (full universe) ──
NEW=$(count "$STAGE"); LIVEN=$(count "$LIVE")
MIN=$(( LIVEN * 80 / 100 )); [ "$MIN" -lt 1000 ] && MIN=1000
if [ "${NEW:-0}" -ge "$MIN" ]; then
  mv -f "$STAGE" "$LIVE"
  echo "[$(ts)] refresh OK: swapped in $NEW symbols (was $LIVEN)"
  # gc_orphans: DISABLED pending dry-run verification (§0.10 / judge ruling)
  # run "$PY" ingest/gc_orphans.py
else
  echo "[$(ts)] GUARD: staged $NEW < min $MIN (live $LIVEN) — keeping live, discarding staging"
  rm -f "$STAGE"
fi
echo "[$(ts)] === terminal refresh done ==="
