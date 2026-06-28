#!/usr/bin/env bash
# Wire the Mastermind Terminal's data to the macro confluence oracle (EOD, NOT real-time).
# Runs charting-app/ingest/build_polygon_universe daily → refreshes the 34-symbol
# /opt/terminal/terminal/public/data/{manifest,{SYM}.json,{SYM}.slice.json} that the Next app
# serves at /data/*. OHLC = Polygon HISTORICAL (the charting-app "backtesting feed", explicitly
# NOT live trading); the verdict/WR/PF/CAGR signals come from the macro confluence oracle
# (signal_layer/confluence.py). Next serves public/ from disk, so a data refresh needs NO rebuild.
# Real-time (intraday/Alpaca) is a separate future step — deferred.
#
# Deploy model: the charting-app code (ingest/signal_layer/contracts) is rsynced to /opt/terminal
# (charting-app is local-git-only, no remote). This script just builds the wrapper + cron.
# Requires /opt/terminal/.env with POLYGON_API_KEY (transferred out-of-band, never committed).
set -euo pipefail
TROOT="/opt/terminal"
VENV="/opt/macro/.venv"   # reuse the engine venv (pandas/numpy/pyarrow) + jsonschema for contracts
log() { echo "[terminal-data] $*"; }

log "[1/3] ensure jsonschema in the engine venv"
"$VENV/bin/pip" install -q jsonschema

log "[2/3] runner wrapper (sources /opt/terminal/.env for POLYGON_API_KEY)"
cat > /usr/local/bin/terminal-data <<EOF
#!/usr/bin/env bash
set -a; [ -f $TROOT/.env ] && . $TROOT/.env; set +a
cd "$TROOT" && exec "$VENV/bin/python" -m ingest.build_polygon_universe
EOF
chmod +x /usr/local/bin/terminal-data

log "[3/3] cron: daily 21:30 UTC (after US close; crypto refreshes on weekends too)"
{ crontab -l 2>/dev/null | grep -v "terminal-data" || true ; \
  echo "30 21 * * * /usr/local/bin/terminal-data >> /var/log/terminal-data.log 2>&1" ; } | crontab -

log "DONE — Terminal data refreshes daily; crontab:"; crontab -l | grep terminal-data
