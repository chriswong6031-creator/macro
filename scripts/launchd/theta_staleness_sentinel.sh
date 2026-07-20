#!/usr/bin/env bash
# scripts/launchd/theta_staleness_sentinel.sh
#
# Staleness sentinel for the ThetaData EOD store. Installed 2026-07-20 after a
# 3-day silent stall (terminal died Fri evening 07-17; nothing alarmed until a
# human noticed frozen options planes on 07-20).
#
# Checks two things and ALERTS on either:
#   1. Terminal health — :25503 not answering, OR answering 200 with a trivial
#      body on /v3/option/list/symbols (a terminal on a stale/revoked
#      THETA_API_KEY stays up as a ZOMBIE serving empty 200s while real data
#      endpoints time out — bit live 2026-07-20; a bare status-code check
#      stayed green through it). Either shape means the whole lane is dead
#      ahead of the next post-close window (leading indicator).
#   2. Store staleness — latest date in greeks/SPY/{YYYY}.parquet vs the last
#      session that SHOULD be there. sessions_missing counts NYSE weekday
#      sessions from (latest+1) .. today, including today only when invoked
#      with --due-today (evening lane, after the 16:10 ET close pull window).
#      ALERT at >= 2 missing sessions, WARN at 1. (US market holidays are not
#      special-cased — a holiday can inflate the count by 1, which the WARN
#      tier absorbs; the ALERT tier only false-fires if a holiday AND a real
#      miss stack, which is exactly when a human look is cheap.)
#
# Outputs (all append/atomic-write, never touches the parquet store):
#   /tmp/theta_staleness.json  — machine-readable latest verdict
#   /tmp/theta_staleness.log   — append-only history
#   macOS notification via osascript on WARN/ALERT (operator works on this Mac)
#
# Install:
#   cp scripts/launchd/com.macro.theta-staleness.plist ~/Library/LaunchAgents/
#   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.macro.theta-staleness.plist

set -uo pipefail

PYTHON="/opt/homebrew/Caskroom/miniconda/base/bin/python"
STORE="/Users/chriswong/theta-ops-wt/data/thetadata_eod"
OUT_JSON="/tmp/theta_staleness.json"
LOG="/tmp/theta_staleness.log"
HEALTH_URL="http://127.0.0.1:25503/v3/option/list/symbols"

# due-today: today's session counts as missing only after the post-close pull
# window (16:10 ET / 13:10 PT). launchd can't vary args per StartCalendarInterval
# firing, so infer from local time (>= 17:00 local = evening lane); --due-today
# forces it for manual runs.
DUE_TODAY=0
[ "$(date +%H)" -ge 17 ] && DUE_TODAY=1
[ "${1:-}" = "--due-today" ] && DUE_TODAY=1

# Health = 200 AND a non-trivial body (healthy symbols list ≈ 106 KB / 15.6k
# roots; a stale-key zombie serves a 0 B body — see header). The body is
# counted, never persisted.
SYMBOLS_MIN_BYTES=1000
term_body="$(mktemp /tmp/theta_sentinel_health.XXXXXX)"
term_code=$(curl -s -m 6 -o "${term_body}" -w '%{http_code}' "${HEALTH_URL}" 2>/dev/null); term_code="${term_code:-000}"
term_bytes=$(wc -c < "${term_body}" 2>/dev/null | tr -d '[:space:]'); term_bytes="${term_bytes:-0}"
rm -f "${term_body}"

DUE_TODAY="${DUE_TODAY}" TERM_CODE="${term_code}" TERM_BYTES="${term_bytes}" \
SYMBOLS_MIN_BYTES="${SYMBOLS_MIN_BYTES}" STORE="${STORE}" OUT_JSON="${OUT_JSON}" LOG="${LOG}" \
"${PYTHON}" - <<'PY'
import datetime as dt
import json, os, subprocess, sys

store = os.environ["STORE"]
due_today = os.environ["DUE_TODAY"] == "1"
term_code = os.environ["TERM_CODE"]
term_bytes = int(os.environ.get("TERM_BYTES", "0") or 0)
min_bytes = int(os.environ.get("SYMBOLS_MIN_BYTES", "1000") or 1000)
out_json = os.environ["OUT_JSON"]
log_path = os.environ["LOG"]

today = dt.date.today()
now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

latest = None
err = None
try:
    import pandas as pd
    path = f"{store}/greeks/SPY/{today.year}.parquet"
    if not os.path.exists(path) and today.month == 1:
        path = f"{store}/greeks/SPY/{today.year - 1}.parquet"
    df = pd.read_parquet(path)
    col = "date" if "date" in df.columns else next(
        (c for c in df.columns if "date" in c.lower()), None)
    if col is None:
        err = f"no date-like column in {path}: {list(df.columns)[:8]}"
    else:
        latest = pd.to_datetime(df[col]).max().date()
except Exception as e:
    err = f"{type(e).__name__}: {e}"

def weekday_sessions(start, end_exclusive):
    n, d = 0, start
    while d < end_exclusive:
        if d.weekday() < 5:
            n += 1
        d += dt.timedelta(days=1)
    return n

if latest is not None:
    end = today + dt.timedelta(days=1) if due_today else today
    missing = weekday_sessions(latest + dt.timedelta(days=1), end)
else:
    missing = None

level = "OK"
reasons = []
if term_code != "200":
    level = "ALERT"
    reasons.append(f"terminal :25503 unreachable (http={term_code})")
elif term_bytes <= min_bytes:
    # Zombie shape: the socket answers but serves nothing (stale/revoked key).
    level = "ALERT"
    reasons.append(
        f"terminal :25503 ZOMBIE — http=200 but symbols body {term_bytes}B "
        f"(<={min_bytes}B; stale/revoked THETA_API_KEY?)")
if err:
    level = "ALERT"
    reasons.append(f"store read failed: {err}")
if missing is not None:
    if missing >= 2:
        level = "ALERT"
        reasons.append(f"greeks {missing} sessions behind (latest={latest})")
    elif missing == 1 and level == "OK":
        level = "WARN"
        reasons.append(f"greeks 1 session behind (latest={latest})")

verdict = {
    "checked_at": now,
    "level": level,
    "terminal_http": term_code,
    "terminal_body_bytes": term_bytes,
    "latest_greeks_date": str(latest) if latest else None,
    "sessions_missing": missing,
    "due_today": due_today,
    "reasons": reasons,
}
tmp = out_json + ".tmp"
with open(tmp, "w") as f:
    json.dump(verdict, f, indent=1)
os.replace(tmp, out_json)
with open(log_path, "a") as f:
    f.write(json.dumps(verdict) + "\n")

if level != "OK":
    msg = "; ".join(reasons)[:180]
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{msg}" with title "Theta EOD lane: {level}"'],
            timeout=10, check=False)
    except Exception:
        pass
print(f"[{now}] theta_staleness_sentinel: {level} — {'; '.join(reasons) or 'store current'}")
PY
