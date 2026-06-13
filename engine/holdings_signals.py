"""Holdings accumulation signals — decompose ETF weight changes into a price
component and a residual (genuine rebalance / accumulation) component.

For a market-cap-weighted index fund a holding's weight rises mostly because its
price rose versus peers, NOT because anyone "favored" it. So each holding's
weight change is split:

    w_price = w0 * (1 + r_stock) / (1 + r_fund)   # weight if the basket were untouched
    active  = w1 - w_price                          # the signal: pp of weight beyond price

On the PASSIVE sector SPDRs the residual is real institutional flow — index funds
worldwide must buy when a name's float-adjusted index weight rises (reconstitution
/ float updates) — but it is NOT discretionary manager conviction. That reading
belongs to ACTIVE funds (Phase 2), where the same residual is genuine conviction.
See DECISIONS D70 and LIMITATIONS.md.

Needs >= 2 daily snapshots in data/sector_holdings/<FUND>.parquet to produce
anything; returns None / [] gracefully until history accumulates. The math core,
`decompose`, is a pure function (directly unit-tested); everything else is a thin
store-backed reader on top of it.
"""
from __future__ import annotations

import logging

import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

# Cycle-ladder states that confirm an accumulation read (the stock is also
# basing / turning up technically) — keys match engine.cycles STATE_STYLES.
BULLISH_STATES = {"FRESH BUY", "TURN SIGNALED", "RALLY ON", "BOTTOM WATCH"}

DECOMP_COLS = ["w0", "w1", "raw_change", "w_price", "active_change", "active_pct"]


def _cfg() -> dict:
    return config.load().get("holdings_signals", {})


def decompose(w0: pd.Series, w1: pd.Series, r_stock: pd.Series,
              r_fund: float) -> pd.DataFrame:
    """Split each holding's weight change into price-driven and residual parts.

    w0, w1   : weight_pct (0-100) indexed by ticker, the two snapshots.
    r_stock  : fractional return of each stock over [t0, t1], indexed by ticker.
    r_fund   : fractional return of the fund itself over [t0, t1] (scalar).

    Returns one row per ticker present in BOTH snapshots that also has a return:
    w0, w1, raw_change, w_price, active_change, active_pct. `active_change`
    (percentage points) is weight growth beyond what price action alone explains —
    the accumulation/rebalance signal — and `active_pct` expresses it relative to
    the price-implied weight. Sorted by active_change desc.
    """
    common = w0.index.intersection(w1.index).intersection(r_stock.dropna().index)
    if len(common) == 0:
        return pd.DataFrame(columns=DECOMP_COLS)
    w0c, w1c, rc = w0[common].astype(float), w1[common].astype(float), r_stock[common].astype(float)
    denom = 1.0 + r_fund
    w_price = w0c * (1.0 + rc) / denom
    raw = w1c - w0c
    active = w1c - w_price
    active_pct = 100.0 * active / w_price.where(w_price != 0)
    out = pd.DataFrame({
        "w0": w0c.round(4), "w1": w1c.round(4), "raw_change": raw.round(4),
        "w_price": w_price.round(4), "active_change": active.round(4),
        "active_pct": active_pct.round(2),
    })
    return out.sort_values("active_change", ascending=False)


def _period_return(close: pd.Series, t0: pd.Timestamp, t1: pd.Timestamp) -> float | None:
    """Fractional return between the closes nearest to (<=) t0 and t1."""
    s = close.dropna()
    if s.empty:
        return None
    s1 = s[s.index <= t1]
    s0 = s[s.index <= t0]
    if s0.empty or s1.empty:
        return None
    p0, p1 = s0.iloc[-1], s1.iloc[-1]
    if pd.isna(p0) or pd.isna(p1) or p0 == 0:
        return None
    return float(p1 / p0 - 1.0)


def _latest_aum(fund: str, asof: pd.Timestamp) -> float | None:
    fl = store.read("flows", fund)
    if fl is None or "aum_mn" not in fl:
        return None
    fl = fl.dropna(subset=["aum_mn"])
    fl = fl[fl.index <= asof]
    if fl.empty:
        return None
    return float(fl["aum_mn"].iloc[-1])


def weight_decomposition(fund: str, lookback_days: int | None = None) -> pd.DataFrame | None:
    """Price-decomposed weight changes for one sector fund's top-10 holdings.
    Returns None until >= 2 snapshots exist or if the fund's own return can't be
    computed (we never fabricate the denominator)."""
    cfg = _cfg()
    lookback_days = lookback_days or cfg.get("lookback_days", 5)
    df = store.read("sector_holdings", fund)
    if df is None or df.empty or "ticker" not in df.columns:
        return None
    df.index = pd.to_datetime(df.index)
    dates = sorted(df.index.unique())
    if len(dates) < 2:
        return None
    t1 = dates[-1]
    cutoff = t1 - pd.Timedelta(days=lookback_days)
    earlier = [d for d in dates if d <= cutoff]
    t0 = earlier[-1] if earlier else dates[0]

    w0 = df.loc[[t0]].set_index("ticker")["weight_pct"].astype(float)
    snap1 = df.loc[[t1]].set_index("ticker")
    w1 = snap1["weight_pct"].astype(float)
    names = snap1["name"] if "name" in snap1.columns else pd.Series(dtype=str)

    etf = store.read("yahoo", fund)
    if etf is None or "close" not in etf:
        return None
    r_fund = _period_return(etf["close"], t0, t1)
    if r_fund is None:
        return None

    r_stock: dict[str, float] = {}
    for tk in w0.index.union(w1.index):
        px = store.read("stocks", str(tk).replace(".", "-"))
        if px is None or "close" not in px:
            continue
        r = _period_return(px["close"], t0, t1)
        if r is not None:
            r_stock[tk] = r
    r_stock_s = pd.Series(r_stock, dtype=float)
    if r_stock_s.empty:
        return None

    dec = decompose(w0, w1, r_stock_s, r_fund)
    if dec.empty:
        return None
    dec["name"] = [str(names.get(t, "")) for t in dec.index]
    dec["r_stock"] = r_stock_s.reindex(dec.index)
    dec["r_fund"] = r_fund
    dec["t0"], dec["t1"] = str(t0.date()), str(t1.date())
    aum = _latest_aum(fund, t1)
    dec["est_flow_mn"] = (dec["active_change"] / 100.0 * aum) if aum else float("nan")
    return dec


def _ladder_for(ticker: str, min_hist: int) -> dict | None:
    """The stock's calibrated cycle/ladder state — the 'is a buy signal forming?'
    confirmation layer. Reuses engine.cycles.analyze; None if too little history."""
    px = store.read("stocks", str(ticker).replace(".", "-"))
    if px is None or "close" not in px or len(px) < min_hist:
        return None
    try:
        from engine.cycles import analyze
        lad = analyze(px["close"], px.get("high")).get("ladder")
    except Exception as e:  # noqa: BLE001 — confirmation is additive, never fatal
        log.debug("cycle read failed for %s: %s", ticker, e)
        return None
    if not lad:
        return None
    return {"state": lad["state"], "label": lad["label"], "action": lad["action"],
            "urgency": lad["entry"]["urgency"], "tag": lad["entry"]["tag"]}


def accumulation_signals(fund: str) -> list[dict]:
    """Holdings whose residual weight change clears the config threshold, each
    enriched with the stock's cycle state. `confirmed` = accumulating AND the
    stock is technically basing/turning up (the strongest combination)."""
    cfg = _cfg()
    pp = cfg.get("active_change_pp", 0.15)
    pct = cfg.get("active_change_pct", 8)
    min_hist = cfg.get("min_price_history", 60)
    dec = weight_decomposition(fund)
    if dec is None:
        return []
    flagged = dec[(dec["active_change"].abs() >= pp) | (dec["active_pct"].abs() >= pct)]
    out = []
    for tk, row in flagged.iterrows():
        ladder = _ladder_for(str(tk), min_hist)
        direction = "accumulating" if row["active_change"] > 0 else "distributing"
        confirmed = bool(
            direction == "accumulating" and ladder
            and (ladder["state"] in BULLISH_STATES
                 or ladder["urgency"] in ("now", "imminent", "soon")))
        out.append({
            "fund": fund, "ticker": str(tk), "name": str(row.get("name", "")).title(),
            "w0": float(row["w0"]), "w1": float(row["w1"]),
            "raw_change": float(row["raw_change"]),
            "active_change": float(row["active_change"]),
            "active_pct": float(row["active_pct"]) if pd.notna(row["active_pct"]) else None,
            "est_flow_mn": float(row["est_flow_mn"]) if pd.notna(row["est_flow_mn"]) else None,
            "t0": row["t0"], "t1": row["t1"],
            "direction": direction, "ladder": ladder, "confirmed": confirmed,
        })
    return sorted(out, key=lambda r: -abs(r["active_change"]))


def all_accumulation_signals() -> list[dict]:
    """Flattened, magnitude-sorted accumulation signals across every sector SPDR."""
    funds = config.load()["sponsors"]["sector_funds"]
    out: list[dict] = []
    for fund in funds:
        try:
            out.extend(accumulation_signals(fund))
        except Exception as e:  # noqa: BLE001 — one fund must not kill the rest
            log.error("accumulation_signals %s failed: %s", fund, e)
    return sorted(out, key=lambda r: -abs(r["active_change"]))
