"""Hong Kong IPO backdrop — DISPLAY-ONLY, NEVER-SCORED (Phase 3).

The US-vs-HK story (research/IPO_RADAR.md): HK is structurally MORE retail-tradeable
than the US — a mandatory public-offer tranche with a clawback, a published
over-subscription multiple, and a grey market (暗盘) that trades the night before
listing. The cruel irony is that the keyless data for those PRIMARY-market signals is
currently broken/blocked (akshare's HK IPO endpoint returns A-share data; the grey
market is broker-proprietary). So we cannot show the HK deal-level demand.

What we CAN show, keylessly, is the LIQUIDITY BACKDROP that drives HK's hot windows:
  southbound Stock Connect flow   mainland capital into HK (the 2025 boom's fuel)
  HIBOR (1-month)                 the cost of margin-financing IPO subscriptions
  HKD peg state                   strong-side (inflow) vs weak-side (outflow) pressure
  HK global risk state            risk-on/off receptiveness (engine/hk regime)

This is the backdrop, NOT a deal signal, and it is never scored. Reuses the existing
HK collectors; degrades gracefully (available=False) when the HK build hasn't run.
"""
from __future__ import annotations

import json

import pandas as pd

from lib import config, store

SCORED = False


def _series(group: str, name: str, col: str) -> pd.Series | None:
    try:
        df = store.read(group, name)
    except Exception:  # noqa: BLE001
        return None
    if df is None or df.empty or col not in df:
        return None
    return df[col].astype(float).dropna()


def _hk_regime() -> dict:
    p = config.data_dir() / "hk_regime" / "latest.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return {}


def hk_backdrop() -> dict:
    legs: list[dict] = []

    def add(key, label, value, state, note):
        legs.append({"key": key, "label": label, "value": value, "state": state, "note": note})

    # 1) southbound Stock Connect — mainland $ into HK (the boom's fuel)
    sb = _series("china_connect", "southbound", "net")
    if sb is not None and len(sb) >= 20:
        cum20 = float(sb.iloc[-20:].sum())
        state = "constructive" if cum20 > 0 else "cautious" if cum20 < 0 else "neutral"
        add("southbound", "Southbound flow (20d net)", round(cum20),
            state, "mainland capital into HK = primary-market fuel")

    # 2) HIBOR 1m — cost of margin-financing IPO subscriptions (low = froth-enabling)
    hb = _series("hkma", "interbank_liquidity", "hibor_1m")
    if hb is not None and len(hb):
        v = float(hb.iloc[-1])
        state = "constructive" if v < 2.5 else "neutral" if v < 4.0 else "cautious"
        add("hibor", "Subscription funding (1M HIBOR)", round(v, 2),
            state, "cheap HK$ funding = leveraged retail subscription")

    # 3) HKD peg — strong-side (inflow) tailwind vs weak-side (outflow) headwind
    reg = _hk_regime()
    peg = reg.get("peg_state")
    if peg:
        state = ("constructive" if "strong" in peg else
                 "cautious" if "weak" in peg else "neutral")
        add("peg", "HKD peg pressure", peg, state, "inflow side supports issuance")

    # 4) HK global risk receptiveness
    risk = reg.get("risk_state")
    if risk:
        state = ("constructive" if "on" in risk.lower() else
                 "cautious" if "off" in risk.lower() else "neutral")
        add("risk", "HK risk appetite", risk, state, "risk-on tape welcomes new issues")

    cons = sum(1 for l in legs if l["state"] == "constructive")
    caut = sum(1 for l in legs if l["state"] == "cautious")
    n = len(legs)
    if n == 0:
        verdict = "unavailable"
    elif cons >= max(2, n * 0.5) and cons > caut:
        verdict = "receptive"
    elif caut >= max(2, n * 0.5) and caut > cons:
        verdict = "poor"
    else:
        verdict = "mixed"

    return {
        "available": n > 0,
        "verdict": verdict, "constructive": cons, "cautious": caut, "n_legs": n,
        "legs": legs, "as_of": reg.get("date"),
        "note": ("Liquidity backdrop only — HK is structurally more retail-tradeable "
                 "(public-offer tranche + clawback, published subscription multiple, "
                 "grey market) but those keyless primary-market feeds are currently "
                 "broken/blocked, so this is the issuance environment, not a deal signal. "
                 "Never scored."),
    }
