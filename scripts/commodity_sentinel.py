"""Commodity Vector intraday shock sentinel — the intraday loop.

Runs every ~30 min on a lightweight cron. For each of the four commodities:
  1. fetch the last ~1mo of hourly bars from Yahoo (GC=F/SI=F/HG=F/CL=F), upsert
  2. recompute the SYMMETRIC price-shock state machine (up OR down) over a window
  3. if any asset's state CHANGED since last run: append the event to
     data/commodity/alerts.jsonl, update data/commodity/shock_state.json, push a
     Telegram card, and exit 10 (CI rebuilds + commits the site)
  4. otherwise just refresh the eval timestamp and exit 0 (no commit — quiet repo)

Exit codes: 0 = no change, 10 = a state changed (rebuild+commit), 1 = hard error.
Honest cadence: Actions cron is best-effort (~15–45 min); this is price-only
intraday — the residual/regime/positioning signals still refresh daily. Commodity
thresholds are per-asset and PROVISIONAL (commodity vol << crypto); tune once a few
weeks of hourly history accrue.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import commodity_alerts  # noqa: E402
from lib import config, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("commodity_sentinel")

CHANGED = 10


def _fetch_hourly(ticker: str) -> pd.DataFrame | None:
    import yfinance as yf
    df = yf.download(ticker, period="1mo", interval="60m", auto_adjust=True,
                     progress=False, threads=False)
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df = df.xs(ticker, axis=1, level=-1) if ticker in df.columns.get_level_values(-1) \
            else df.droplevel(-1, axis=1)
    df = df.rename(columns=str.lower)[["open", "high", "low", "close"]].dropna(subset=["close"])
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df[~df.index.duplicated(keep="last")].sort_index()


def _state_path() -> Path:
    return config.data_dir() / "commodity" / "shock_state.json"


def main() -> int:
    cfg = config.load()["commodities"]
    acfg = cfg["alerts"]
    lookback = acfg["shock"]["intraday_lookback_d"]
    assets = list(cfg["assets"])

    prev_all = {}
    sp = _state_path()
    if sp.exists():
        prev_all = json.loads(sp.read_text())
    now_iso = datetime.now(timezone.utc).isoformat()

    changed_events: list[dict] = []
    new_state_all: dict = {}
    for asset in assets:
        ticker = cfg["assets"][asset][0]
        try:
            recent = _fetch_hourly(ticker)
            if recent is not None and not recent.empty:
                store.upsert("commodity", f"{asset}_hourly", recent, normalize_index=False)
        except Exception as e:  # noqa: BLE001 — network hiccup: use stored bars
            log.warning("%s hourly fetch failed (%s); using stored", asset, e)

        hourly = store.read("commodity", f"{asset}_hourly")
        if hourly is None or hourly.empty:
            log.warning("%s: no hourly data yet", asset)
            continue
        window = hourly[hourly.index >= hourly.index.max() - pd.Timedelta(days=lookback)]
        states = commodity_alerts.shock_states(window, asset, acfg)
        cur = states.iloc[-1]
        price = float(window["close"].iloc[-1])
        # Watermark on the last-emitted transition ts (ISO, lexicographically
        # comparable). Emit EVERY new shock card past the watermark — captures the
        # full normal->shock->extended path (and round-trips) even when the move
        # escalates within one best-effort cron gap, instead of only the final-bar
        # card. Cold start seeds the watermark without flooding 60d of history.
        prev = prev_all.get(asset, {})
        last_emitted = prev.get("last_emitted_ts")
        evs = commodity_alerts.shock_events(window, asset, acfg)
        if last_emitted is None:
            last_emitted = evs[-1]["ts"] if evs else None  # seed, don't backfill
        else:
            new_cards = [e for e in evs if e["ts"] > last_emitted]
            if new_cards:
                changed_events.extend(new_cards)
                last_emitted = new_cards[-1]["ts"]
                log.info("%s shock cards: %s ($%.2f)", asset,
                         [e["context"].get("state") for e in new_cards], price)
        new_state_all[asset] = {"state": cur, "ts": states.index[-1].isoformat(),
                                "last_eval": now_iso, "price": price,
                                "last_emitted_ts": last_emitted}

    # merge state file (keep assets we couldn't refresh this run)
    merged_state = {**prev_all, **new_state_all}
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(merged_state, indent=2, default=str))

    if not changed_events:
        log.info("no commodity shock-state change")
        return 0

    existing = commodity_alerts.load_events()
    have = {e["id"] for e in existing}
    fresh = [e for e in changed_events if e["id"] not in have]
    if fresh:
        commodity_alerts.write_events(fresh + existing)
    for e in fresh:
        _notify(e)
    return CHANGED


def _notify(ev: dict) -> None:
    try:
        from scripts.notify import send_telegram
        c = ev["context"]
        send_telegram(f"<b>{ev['headline']}</b>\n{ev['detail']}\n"
                      f"{ev['ts'][:16].replace('T', ' ')} UTC")
    except Exception as e:  # noqa: BLE001 — never fail the sentinel on notify
        log.warning("telegram notify skipped: %s", e)


if __name__ == "__main__":
    sys.exit(main())
