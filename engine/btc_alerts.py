"""Bitcoin Vector alert engine.

Two kinds of events, one schema:
- DAILY state-change events, derived deterministically from the signal history
  (risk regime crossing 25, structure-shift trigger, momentum flip, allocation
  step, fundamentals zone, leadership rotation, market mode). Recomputing from
  history is idempotent — no stateful append needed.
- FLASH-CRASH events from a price-only state machine over hourly candles
  (normal -> flash_crash -> tail_risk_event -> stabilizing_price -> normal),
  which the intraday sentinel also drives live.

Event schema (richer than the macro feed; the home hub normalizes both):
  {id, ts, source='vector', type, severity (high|medium|info),
   headline, detail, context{}, anchor}

`id` = type:ts-bucket:to_state -> the sentinel and the daily recompute produce
the same id for the same transition, so they dedup naturally.

Writes data/vector/alerts.jsonl (full event log, newest first).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

ANCHOR = {"risk_regime": "#risk", "structure_shift": "#structure",
          "momentum_trigger": "#momentum", "allocation_change": "#allocation",
          "fundamentals": "#bfi", "leadership": "#crossasset",
          "market_mode": "#allocation", "risk_extreme": "#risk",
          "flash_crash": "#flash"}


def _ev(type_, ts, severity, headline, detail, context, to_state) -> dict:
    ts = pd.Timestamp(ts)
    bucket = ts.strftime("%Y-%m-%dT%H:%M")
    return {"id": f"{type_}:{bucket}:{to_state}", "ts": ts.isoformat(),
            "source": "vector", "type": type_, "severity": severity,
            "headline": headline, "detail": detail, "context": context,
            "anchor": ANCHOR.get(type_, "")}


# --------------------------------------------------------------------------- #
# daily state-change events
# --------------------------------------------------------------------------- #
def _transitions(state: pd.Series) -> list[tuple[pd.Timestamp, str, str]]:
    s = state.dropna()
    chg = s != s.shift()
    chg.iloc[0] = False
    return [(t, s.shift()[t], s[t]) for t in s.index[chg]]


def daily_state_events(sig: pd.DataFrame) -> list[dict]:
    out: list[dict] = []
    close = sig["close"]

    for ts, frm, to in _transitions(sig["risk_regime"]):
        word = "High Risk" if to == "high_risk" else "Low Risk"
        sev = "high"
        ri = sig["risk_index"].get(ts, float("nan"))
        out.append(_ev("risk_regime", ts, sev,
                       f"Risk Off Signal changed to: {word}",
                       f"Risk Index crossed the 25 threshold to {ri:.0f} "
                       f"({'rising' if to=='high_risk' else 'falling'}). "
                       f"BTC ${close.get(ts, float('nan')):,.0f}.",
                       {"risk_index": round(float(ri), 1) if pd.notna(ri) else None,
                        "price": round(float(close.get(ts, float('nan'))))}, to))

    for ts, frm, to in _transitions(sig["structure_state"]):
        if to == "constructive":
            head, sev = "Structure Shift: Bullish trigger", "high"
        elif to == "broken":
            head, sev = "Structure Shift: Bearish trigger", "high"
        else:
            head, sev = "Structure Shift: neutral", "medium"
        val = sig["structure"].get(ts, float("nan"))
        out.append(_ev("structure_shift", ts, sev, head,
                       f"Structure oscillator now {val:+.2f} ({frm} → {to}).",
                       {"structure": round(float(val), 2) if pd.notna(val) else None}, to))

    for ts, frm, to in _transitions(sig["momentum_state"]):
        if to == "bull":
            head, sev = "Momentum turned Bullish", "high"
        elif to == "bear":
            head, sev = "Momentum turned Bearish", "high"
        else:
            head, sev = "Momentum cooled to neutral", "medium"
        m = sig["momentum"].get(ts, float("nan"))
        out.append(_ev("momentum_trigger", ts, sev, head,
                       f"Momentum score {m:+.2f} ({frm} → {to}); ±0.5 is the trigger band.",
                       {"momentum": round(float(m), 2) if pd.notna(m) else None}, to))

    alloc = sig["alloc_optimal"]
    for ts, frm, to in _transitions(alloc):
        pct = int(round(float(to) * 100))
        out.append(_ev("allocation_change", ts, "medium",
                       f"Allocation changed to {pct}% BTC",
                       f"Optimal strategy moved {int(float(frm)*100)}% → {pct}% BTC "
                       f"(momentum × risk grid).",
                       {"alloc_pct": pct}, str(to)))

    if "bfi_zone" in sig.columns:
        for ts, frm, to in _transitions(sig["bfi_zone"]):
            sev = "medium" if to != "neutral" else "info"
            out.append(_ev("fundamentals", ts, sev,
                           f"Fundamentals turned {to}",
                           f"BFI entered the {to} zone (40/60 bands); "
                           f"now {sig['bfi'].get(ts, float('nan')):.0f}.",
                           {"bfi": round(float(sig['bfi'].get(ts, float('nan'))))}, to))

    if "market_mode" in sig.columns:
        for ts, frm, to in _transitions(sig["market_mode"]):
            out.append(_ev("market_mode", ts, "medium",
                           f"Market mode changed to {to}",
                           f"Trend efficiency shifted the regime {frm} → {to}.",
                           {}, to))

    if "alt_cycle_leader" in sig.columns:
        for ts, frm, to in _transitions(sig["alt_cycle_leader"]):
            out.append(_ev("leadership", ts, "info",
                           f"Leadership rotated to {to}",
                           f"Relative-strength leadership moved {frm} → {to}.",
                           {}, to))
    return out


def risk_extreme_events(sig: pd.DataFrame, cfg: dict) -> list[dict]:
    """A capitulation-watch when Risk Index holds high for N days — the
    documented contrarian-at-extremes use. One event per onset."""
    lvl, ndays = cfg["risk_extreme_level"], cfg["risk_extreme_days"]
    hi = (sig["risk_index"] >= lvl)
    streak = hi.groupby((~hi).cumsum()).cumsum()
    onset = (streak == ndays)
    out = []
    for ts in sig.index[onset.fillna(False)]:
        out.append(_ev("risk_extreme", ts, "info",
                       "Capitulation watch: risk elevated",
                       f"Risk Index held ≥ {lvl} for {ndays} days "
                       f"(now {sig['risk_index'].get(ts):.0f}). At sustained extremes "
                       f"the index is contrarian — historically near-capitulation.",
                       {"risk_index": round(float(sig['risk_index'].get(ts)))}, "extreme"))
    return out


# --------------------------------------------------------------------------- #
# flash-crash state machine (hourly, price-only)
# --------------------------------------------------------------------------- #
def flash_crash_states(hourly: pd.DataFrame, cfg: dict) -> pd.Series:
    f = cfg["flash"]
    close = hourly["close"]
    ret = close.pct_change()
    sigma6 = ret.rolling(f["vol_window_h"]).std() * np.sqrt(f["drop_window_h"])
    r6 = close.pct_change(f["drop_window_h"])
    r24 = close.pct_change(24)
    low24 = close.rolling(24).min()

    states = []
    cur = "normal"
    quiet = 0
    last_low = np.inf
    idx = close.index
    for i, ts in enumerate(idx):
        c = close.iloc[i]
        s6 = sigma6.iloc[i]
        shock = pd.notna(s6) and s6 > 0 and r6.iloc[i] < -f["enter_sigma"] * s6
        big6 = pd.notna(r6.iloc[i]) and r6.iloc[i] * 100 < f["enter_6h_pct"]
        big24 = pd.notna(r24.iloc[i]) and r24.iloc[i] * 100 < f["enter_24h_pct"]
        acute = (shock and big6) or big24
        new_low = c <= low24.iloc[i] * 1.0005 if pd.notna(low24.iloc[i]) else False

        if cur == "normal":
            if acute:
                cur, quiet, last_low = "flash_crash", 0, c
        elif cur == "flash_crash":
            if pd.notna(r24.iloc[i]) and r24.iloc[i] * 100 < f["tail_24h_pct"]:
                cur = "tail_risk_event"
            elif not new_low:
                quiet += 1
                if quiet >= f["stabilize_quiet_h"]:
                    cur, quiet = "stabilizing_price", 0
            else:
                quiet, last_low = 0, min(last_low, c)
        elif cur == "tail_risk_event":
            if not new_low:
                quiet += 1
                if quiet >= f["stabilize_quiet_h"]:
                    cur, quiet = "stabilizing_price", 0
            else:
                quiet, last_low = 0, min(last_low, c)
        elif cur == "stabilizing_price":
            if acute:
                cur, quiet, last_low = "flash_crash", 0, c
            else:
                quiet += 1
                if quiet >= f["normal_quiet_h"]:
                    cur, quiet = "normal", 0
        states.append(cur)
    return pd.Series(states, index=idx, name="flash_state")


def impulse_sign(hourly: pd.DataFrame, cfg: dict) -> pd.Series:
    ret = hourly["close"].pct_change()
    ema = ret.ewm(span=cfg["flash"]["impulse_window_h"], adjust=False).mean()
    return np.sign(ema)


def flash_events(hourly: pd.DataFrame | None, cfg: dict) -> list[dict]:
    if hourly is None or hourly.empty:
        return []
    states = flash_crash_states(hourly, cfg)
    imp = impulse_sign(hourly, cfg)
    close = hourly["close"]
    out = []
    STATE_WORD = {"flash_crash": "flash crash", "tail_risk_event": "tail risk event",
                  "stabilizing_price": "stabilizing price", "normal": "normal"}
    for ts, frm, to in _transitions(states):
        if to == "normal":
            continue  # don't alert the all-clear as its own card (implied by stabilizing)
        c = float(close.get(ts, float("nan")))
        c24 = float(close.shift(24).get(ts, float("nan")))
        chg = (c / c24 - 1) * 100 if pd.notna(c24) and c24 else float("nan")
        impulse = "positive" if imp.get(ts, 0) > 0 else "negative"
        sev = "high" if to in ("flash_crash", "tail_risk_event") else "medium"
        out.append(_ev("flash_crash", ts, sev,
                       f"Flash Crash Index changed to: {STATE_WORD[to]}",
                       f"BTC ${c:,.0f}, {chg:+.2f}% (24h). Impulse {impulse}.",
                       {"price": round(c), "chg_24h_pct": round(chg, 2),
                        "impulse": impulse, "state": to}, to))
    return out


# --------------------------------------------------------------------------- #
# build / load
# --------------------------------------------------------------------------- #
def _path() -> "object":
    return config.data_dir() / "vector" / "alerts.jsonl"


def compute_all_events(sig: pd.DataFrame | None = None) -> list[dict]:
    cfg = config.load()["vector"]["alerts"]
    if sig is None:
        sig = store.read("vector", "signals")
        sig.index = pd.to_datetime(sig.index)
    events = daily_state_events(sig) + risk_extreme_events(sig, cfg)
    events += flash_events(store.read("coinbase", "btc_hourly"), cfg)
    # merge with any sentinel-appended events newer than what we can derive
    existing = load_events()
    by_id = {e["id"]: e for e in events}
    for e in existing:
        by_id.setdefault(e["id"], e)  # keep sentinel-only events; recompute wins on collision
    merged = sorted(by_id.values(), key=lambda e: e["ts"], reverse=True)
    return merged


def write_events(events: list[dict]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")


def load_events() -> list[dict]:
    p = _path()
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def rebuild(sig: pd.DataFrame | None = None) -> list[dict]:
    events = compute_all_events(sig)
    write_events(events)
    log.info("vector alerts: %d events, latest %s",
             len(events), events[0]["ts"] if events else "none")
    return events


def recent(events: list[dict], days: int) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - pd.Timedelta(days=days)).isoformat()
    return [e for e in events if e["ts"] >= cutoff]
