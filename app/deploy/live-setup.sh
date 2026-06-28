#!/usr/bin/env bash
# Live ENGINE SCORING on the VPS — the intraday fast-loop.
# Builds a LIGHT engine venv (NOT the full collector stack) and a cron that runs
# scripts.build_live_overlay every 5 min (Asia-open -> US-close, weekdays), writing the
# gitignored /opt/macro/site/live/overlay.json that macro-api serves at /api/overlay.
#
# What it computes: per-ticker FAST LEAVES (RSI / MACD / MA-distance / %-off-52w-high)
# recomputed on a LIVE price, spliced onto the nightly close series, plus a divergence
# flag vs the nightly anticipation cone. Slow brain (regime/conviction/GTAA) stays nightly.
# Fail-safe: when a market is closed (or a feed is down) legs are marked `stale` and consumers
# fall back to the nightly baseline — overlay.json still emits, never crashes.
#
# overlay.json is GITIGNORED, so the 3-min macro-update `git reset --hard` never clobbers it.
#
# REAL-TIME US: drop `POLYGON_API_KEY=...` into /etc/macro-live.env (chmod 600, NOT committed)
# and the next run uses Polygon real-time; otherwise it serves keyless Yahoo (~15-min delayed).
set -euo pipefail

APP_DIR="/opt/macro"
VENV="$APP_DIR/.venv"
log() { echo "[live-setup] $*"; }

log "[1/4] light engine venv (pandas/pyarrow/numpy/requests/pyyaml — not the full stack)"
export DEBIAN_FRONTEND=noninteractive
apt-get install -y python3-venv >/dev/null 2>&1 || true
test -d "$VENV" || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q pandas pyarrow numpy requests pyyaml

log "[2/4] runner wrapper (sources optional /etc/macro-live.env for POLYGON_API_KEY)"
cat > /usr/local/bin/macro-live <<EOF
#!/usr/bin/env bash
set -a; [ -f /etc/macro-live.env ] && . /etc/macro-live.env; set +a
cd "$APP_DIR" && exec "$VENV/bin/python" -m scripts.build_live_overlay
EOF
chmod +x /usr/local/bin/macro-live

log "[3/4] smoke test"
if macro-live > /tmp/live.log 2>&1; then tail -1 /tmp/live.log; else log "smoke test FAILED:"; tail -6 /tmp/live.log; fi

log "[4/4] cron: fast-loop every 5 min (1-21 UTC weekdays — Asia open through US close)"
{ crontab -l 2>/dev/null | grep -v "macro-live\|build_live_overlay" || true ; \
  echo "*/5 1-21 * * 1-5 /usr/local/bin/macro-live >> /var/log/live-overlay.log 2>&1" ; } | crontab -

log "DONE — /api/overlay serves the overlay; crontab:"; crontab -l | grep macro-live
