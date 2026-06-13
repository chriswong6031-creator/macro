"""Bitcoin Vector flash-crash sentinel — the intraday loop.

Runs every ~15–30 min on a lightweight cron. One cheap job:
  1. fetch the last few hours of Coinbase candles (+ spot), append to the store
  2. recompute the flash-crash state machine over a trailing window
  3. if the state CHANGED since last run: append the event to alerts.jsonl,
     update data/vector/flash_state.json, push a Telegram card, and exit 10
     (CI uses the exit code to decide whether to rebuild + commit the site)
  4. otherwise update the last-eval timestamp and exit 0 (no commit — alerts
     are rare, so the repo stays quiet)

Exit codes: 0 = no change, 10 = state changed (rebuild+commit), 1 = error.
Honest cadence: GitHub Actions cron is best-effort (~15–45 min effective);
this is price-only intraday — on-chain/regime alerts still refresh daily.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import btc_alerts  # noqa: E402
from lib import config, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("vector_sentinel")

WINDOW_DAYS = 90  # trailing hourly context for the state machine (settles in <2d)
CHANGED = 10


def _fetch_recent_candles() -> pd.DataFrame | None:
    cfg = config.load()["coinbase"]
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=300)  # one 300-candle page of hourly
    import requests
    r = requests.get(cfg["candles_url"], timeout=30,
                     params={"granularity": "3600", "start": start.isoformat(),
                             "end": end.isoformat()})
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list) or not data:
        return None
    df = pd.DataFrame(data, columns=["ts", "low", "high", "open", "close", "volume"])
    df["date"] = pd.to_datetime(df["ts"], unit="s")
    return df.drop(columns=["ts"]).set_index("date").sort_index().astype(float)


def _state_path() -> Path:
    return config.data_dir() / "vector" / "flash_state.json"


def main() -> int:
    try:
        recent = _fetch_recent_candles()
        if recent is not None and not recent.empty:
            store.upsert("coinbase", "btc_hourly", recent, normalize_index=False)
    except Exception as e:  # noqa: BLE001 — network hiccup: fall back to stored data
        log.warning("candle fetch failed (%s); using stored hourly", e)

    hourly = store.read("coinbase", "btc_hourly")
    if hourly is None or hourly.empty:
        log.error("no hourly data")
        return 1
    cutoff = hourly.index.max() - pd.Timedelta(days=WINDOW_DAYS)
    window = hourly[hourly.index >= cutoff]

    cfg = config.load()["vector"]["alerts"]
    states = btc_alerts.flash_crash_states(window, cfg)
    cur_state = states.iloc[-1]
    cur_ts = states.index[-1]

    sp = _state_path()
    prev = json.loads(sp.read_text()) if sp.exists() else {"state": "normal", "ts": None}
    now_iso = datetime.now(timezone.utc).isoformat()

    if cur_state == prev.get("state"):
        sp.write_text(json.dumps({**prev, "last_eval": now_iso,
                                  "price": float(window["close"].iloc[-1])}))
        log.info("no flash-state change (state=%s, BTC $%.0f)",
                 cur_state, window["close"].iloc[-1])
        return 0

    # state changed -> emit the event
    events = btc_alerts.flash_events(window, cfg)
    new_ev = [e for e in events if e["context"].get("state") == cur_state]
    ev = new_ev[-1] if new_ev else None
    if ev:
        existing = btc_alerts.load_events()
        if not any(e["id"] == ev["id"] for e in existing):
            btc_alerts.write_events([ev] + existing)
        _notify(ev)
    sp.write_text(json.dumps({"state": cur_state, "ts": cur_ts.isoformat(),
                              "last_eval": now_iso,
                              "price": float(window["close"].iloc[-1])}))
    log.info("FLASH STATE CHANGE: %s -> %s (BTC $%.0f)",
             prev.get("state"), cur_state, window["close"].iloc[-1])
    return CHANGED


def _notify(ev: dict) -> None:
    try:
        from scripts.notify import send_telegram
        c = ev["context"]
        msg = (f"<b>{ev['headline']}</b>\n"
               f"BTC ${c.get('price', 0):,} · {c.get('chg_24h_pct', 0):+.2f}% (24h)\n"
               f"Impulse {c.get('impulse', '?')} · {ev['ts'][:16].replace('T', ' ')} UTC")
        send_telegram(msg)
    except Exception as e:  # noqa: BLE001 — never fail the sentinel on notify
        log.warning("telegram notify skipped: %s", e)


if __name__ == "__main__":
    sys.exit(main())
