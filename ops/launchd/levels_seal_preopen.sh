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
# Greeks-lag reality: the theta store gets a session's greeks with ~T+1 lag, so at
# 04:30 the last trading day's greeks may not have landed yet ("no reconstructable
# board", exit 4). The 06:00 retry catches the late case. The already-sealed guard
# below makes the retry a no-op when the 04:30 pass succeeded — NEVER re-seal a
# date (a later sealed_at would replace an earlier, better one).
cd /Users/chriswong/hub-ops-wt || exit 1
PY=/opt/homebrew/Caskroom/miniconda/base/bin/python
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

echo "levelsseal: sealing session-date $D  $(date)"
exec "$PY" -m scripts.seal_levels_ledger \
  --roots SPY,QQQ,IWM,DIA,AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA,AVGO \
  --date "$D" --publish
