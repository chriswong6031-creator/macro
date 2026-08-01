#!/bin/sh
# ops/launchd/levels_seal_preopen.sh — pre-open SHA-256 levels-ledger seal
# (launchd label: com.mastermind.levelsseal, weekdays 04:30 + 06:00 local retry —
# both well before the 09:30 ET open; OPRA OI for the session lands ~03:30 local).
#
# Seals the board built from the LAST TRADING DAY's greeks + its t-1 OI — the
# point-in-time map for the coming session — and appends the SHA-256 to the public
# manifest (scripts/seal_levels_ledger.py, WP-C3). Liquid marquee subset so the
# whole seal completes pre-open.
#
# Greeks-lag reality (measured 2026-07-31): ThetaData's EOD report for session D
# lands OVERNIGHT (~03:30 PT, with OPRA OI) — i.e. AFTER the previous evening's
# backfill pass (~16:10 ET), which therefore only ever captures D-1. Without a
# pre-open top-up the store is structurally one session behind at 04:30 on every
# weekday, and the seal can only ever succeed on Mondays (weekend backfill passes
# close the gap) — which is exactly what the ledger showed: two Monday seals,
# zero weekday seals. The top-up below pulls D's eod/oi/greeks for the seal roots
# and merges them into the store first; the 06:00 retry re-runs it, covering
# vendor data that lands between 04:30 and 06:00. The already-sealed guard
# below makes the retry a no-op when the 04:30 pass succeeded — NEVER re-seal a
# date (a later sealed_at would replace an earlier, better one).
cd /Users/chriswong/hub-ops-wt || exit 1
PY=/opt/homebrew/Caskroom/miniconda/base/bin/python
ROOTS="SPY,QQQ,IWM,DIA,AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA,AVGO"
D=$("$PY" -c "
from datetime import date, timedelta
d = date.today() - timedelta(days=1)
while d.weekday() >= 5:
    d -= timedelta(days=1)
print(d.isoformat())")

# already sealed? (idempotence guard — check the manifest, never re-seal)
if "$PY" -c "
import json, sys
try:
    idx = json.load(open('data/levels/ledger/index.json'))
except Exception:
    sys.exit(1)
sys.exit(0 if any(e.get('session_date') == '$D' for e in idx.get('entries', [])) else 1)
"; then
  echo "levelsseal: $D already sealed — skipping"
  exit 0
fi

# Pre-seal store top-up (R0.2) — bounded pull of D's eod/oi/greeks for the seal
# roots, merged into the year parquets. Non-fatal on failure: the sealer below
# still reports honestly, and the top-up skips itself if a backfill is running.
echo "levelsseal: pre-seal store top-up for $D  $(date)"
"$PY" -m scripts.topup_thetadata_day --roots "$ROOTS" --date "$D" \
  || echo "levelsseal: top-up incomplete for $D (continuing to seal attempt)"

echo "levelsseal: sealing session-date $D  $(date)"
exec "$PY" -m scripts.seal_levels_ledger \
  --roots "$ROOTS" \
  --date "$D" --publish
