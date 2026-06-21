"""engine/flow_signing.py — trade-side signing methods + their calibration (pure, testable).

Our flow engine signs volume with the TICK RULE because the per-trade tape + NBBO are not in
our massive.com entitlement. The honest question is: HOW WRONG is the tick rule vs the
gold-standard QUOTE RULE (which needs the NBBO)? This module holds the two signing rules and
the calibration that answers it — pure functions so they unit-test without any vendor.

Once a Databento `tbbo` sample (each trade stamped with the prevailing NBBO) is pulled
(collectors/databento_tbbo), scripts/calibrate_flow_signing feeds it here to measure:
  • per-trade agreement between tick-rule and quote-rule signs, and
  • whether our MINUTE-aggregated tick-rule recovers the same NET daily sign per contract
    (what actually feeds the dealer-positioning read).
The result writes a gate so the flow engine can state its signing accuracy honestly instead
of guessing. References: Lee-Ready (1991), Ellis-Michaely-O'Hara (2000).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def quote_rule_sign(price, bid, ask, prev_price=None):
    """Lee-Ready quote rule: trade ABOVE the NBBO mid = buyer-initiated (+1), BELOW = seller
    (−1), AT mid = fall back to the tick test vs prev_price. Scalar or vectorised."""
    price = np.asarray(price, float); bid = np.asarray(bid, float); ask = np.asarray(ask, float)
    mid = (bid + ask) / 2.0
    s = np.where(price > mid, 1.0, np.where(price < mid, -1.0, 0.0))
    if prev_price is not None:
        pp = np.asarray(prev_price, float)
        tt = np.sign(price - pp)
        s = np.where(s == 0.0, tt, s)
    return s


def tick_rule_sign(price, prev_price):
    """Tick test: uptick = buy (+1), downtick = sell (−1), zero-tick = carry the prior sign.
    Returns the signed array (0 only where no prior non-zero tick exists)."""
    price = np.asarray(price, float); prev_price = np.asarray(prev_price, float)
    raw = np.nan_to_num(np.sign(price - prev_price), nan=0.0)   # no prior tick -> neutral
    out = raw.copy()
    last = 0.0
    for i in range(len(out)):           # carry-forward zero-ticks (small N per contract)
        if out[i] == 0.0:
            out[i] = last
        else:
            last = out[i]
    return out


def delta_adjusted_sign(d_option, d_underlying, delta):
    """Sign aggregated-bar volume by the residual after removing the underlying's delta-driven
    move:  resid = Δoption − delta·Δunderlying  → sign(resid). The idea: an option's price
    ticks mostly track the underlying (via delta), so the part NOT explained by delta is the
    closer proxy for buy/sell pressure. Needs the underlying minute bars (us_stocks_sip flat
    file, entitled) + per-contract delta (snapshot greeks).

    EMPIRICAL VERDICT (Databento tcbbo truth, 2026-06-18): this did NOT beat the plain tick
    rule — both ~0.55 minute-agreement / ~0.62 net-recovery. On the (quiet) days affordable to
    test, the underlying barely moved, so delta-drift was negligible and the dominant noise is
    BID-ASK BOUNCE (the minute close is a random draw from bid/ask), which delta-adjustment
    cannot fix. Its gain only appears on high-underlying-move days. Kept as a building block;
    production signs with the plain tick rule and labels DIRECTION soft. See
    research/OPTIONS_FLOW_DATA.md."""
    resid = np.asarray(d_option, float) - np.asarray(delta, float) * np.asarray(d_underlying, float)
    return np.sign(resid)


def compare_trade_signs(trades: pd.DataFrame) -> dict:
    """Per-trade agreement between tick-rule and quote-rule on a tbbo sample with columns
    [ticker, price, bid, ask, size, ts]. Returns accuracy overall + by liquidity tercile."""
    if trades is None or trades.empty or not {"price", "bid", "ask"} <= set(trades.columns):
        return {}
    df = trades.sort_values(["ticker", "ts"]).copy() if "ts" in trades else trades.copy()
    df["prev"] = df.groupby("ticker")["price"].shift()
    df = df.dropna(subset=["prev"])
    if df.empty:
        return {}
    q = quote_rule_sign(df["price"], df["bid"], df["ask"], df["prev"])
    t = np.empty(len(df))
    i = 0
    for _, g in df.groupby("ticker"):       # tick rule is per-contract sequential
        t[i:i + len(g)] = tick_rule_sign(g["price"].to_numpy(), g["prev"].to_numpy())
        i += len(g)
    valid = (q != 0)
    agree = float(np.mean(t[valid] == q[valid])) if valid.any() else None
    # size-weighted agreement (the aggregate that matters for $ flow)
    w = df["size"].to_numpy(float)[valid] if "size" in df else np.ones(int(valid.sum()))
    wagree = float(np.sum(w * (t[valid] == q[valid])) / np.sum(w)) if valid.any() and w.sum() else None
    return {"n": int(valid.sum()), "agreement": round(agree, 4) if agree is not None else None,
            "size_weighted_agreement": round(wagree, 4) if wagree is not None else None}


def minute_sign_recovery(trades: pd.DataFrame, freq: str = "1min") -> dict:
    """The decision-relevant test: does the MINUTE-bar tick rule (what our engine uses)
    recover the same NET signed volume sign per contract as full per-trade quote signing?
    Builds minute bars from the tbbo trades, signs each minute by its close tick, and compares
    the per-contract net sign to the quote-rule per-trade net sign."""
    if trades is None or trades.empty or "ts" not in trades:
        return {}
    df = trades.sort_values(["ticker", "ts"]).copy()
    df["prev"] = df.groupby("ticker")["price"].shift()
    df = df.dropna(subset=["prev"])
    if df.empty:
        return {}
    # truth: per-contract net signed volume by the quote rule
    qs = quote_rule_sign(df["price"], df["bid"], df["ask"], df["prev"])
    df["_q"] = qs * df.get("size", 1.0)
    truth = df.groupby("ticker")["_q"].sum()
    # our method: minute bars (close = last trade in the minute), tick rule on the minute close
    df["_min"] = pd.to_datetime(df["ts"]).dt.floor(freq)
    bars = df.groupby(["ticker", "_min"]).agg(close=("price", "last"),
                                              vol=("size", "sum")).reset_index()
    bars = bars.sort_values(["ticker", "_min"])
    bars["prevc"] = bars.groupby("ticker")["close"].shift()
    mine = []
    for tk, g in bars.groupby("ticker"):
        sgn = tick_rule_sign(g["close"].to_numpy(), g["prevc"].fillna(g["close"]).to_numpy())
        mine.append((tk, float(np.sum(sgn * g["vol"].to_numpy()))))
    mine = pd.Series(dict(mine))
    j = pd.concat([truth.rename("truth"), mine.rename("mine")], axis=1).dropna()
    if j.empty:
        return {}
    sign_match = float(np.mean(np.sign(j["truth"]) == np.sign(j["mine"])))
    return {"contracts": int(len(j)), "net_sign_recovery": round(sign_match, 4)}


def verdict(per_trade: dict, recovery: dict, bar: float = 0.70) -> dict:
    """Gate decision. Two distinct questions, because they have different answers:
      • DIRECTION (net buy vs sell): trustworthy only if the minute net-sign recovery clears
        `bar`. On option MINUTE bars this is typically WEAK — an option's price ticks are
        dominated by the underlying's delta-driven move, not order flow — so the cheap
        tick rule mis-signs direction. Calibrated, stated honestly, never assumed.
      • MAGNITUDE / positioning (volume, premium size, Vol>OI, 0DTE, gamma EXPOSURE): needs
        NO signing, so it is ALWAYS reliable regardless of the gate.
    """
    rec = (recovery or {}).get("net_sign_recovery")
    direction_ok = rec is not None and rec >= bar
    return {"scored": bool(direction_ok),                 # legacy key = direction trust
            "direction_reliable": bool(direction_ok),
            "magnitude_reliable": True,
            "net_sign_recovery": rec,
            "per_trade_agreement": (per_trade or {}).get("agreement"),
            "per_trade_size_weighted": (per_trade or {}).get("size_weighted_agreement"),
            "bar": bar,
            "note": ("flow DIRECTION validated (minute net-sign recovered ≥ bar)"
                     if direction_ok else
                     "flow DIRECTION is SOFT — option minute-ticks are delta-dominated, so net "
                     "buy/sell is approximate; MAGNITUDE / positioning reads stay reliable"
                     if rec is not None else
                     "no calibration sample yet — direction display-only, magnitude reliable")}
