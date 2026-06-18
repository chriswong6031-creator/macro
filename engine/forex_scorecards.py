"""Forex strategy scorecards — honest, PIT backtests of two classic FX trades.

  g10_carry    Long the highest-carry G10 currencies vs USD, short the lowest
               (the canonical carry trade). Carry harvests a REAL risk premium but
               with a FAT LEFT TAIL — it crashes in risk-off (1998 / 2008 / 2015 /
               2020). We show CAGR / Sharpe / MaxDD / skew with a pre-/post-2008
               regime split so the decay and the tail are visible, not hidden behind
               a flattering full-sample Sharpe. Optional inverse-vol scaling is the
               standard carry-crash haircut.

  dollar_trend Long the dollar index when its 12-month trend is up, else flat — a
               crash-avoidance overlay, NOT alpha (broad-dollar trend calibrates
               weakly / INVERTED on most pairs; mean-reversion dominates).

DISPLAY-ONLY / experimental. These are risk-premium harvests and timing overlays
with documented fragility, never a recommendation. Backtests are NET of a one-way
spread cost and use only past information at each rebalance (no look-ahead).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.validation import backtest_core

log = logging.getLogger(__name__)

ANN = np.sqrt(252.0)


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #
def _metrics(r: pd.Series) -> dict:
    """CAGR / Sharpe / MaxDD / skew / worst-month from a daily return series."""
    r = r.dropna()
    if len(r) < 60:
        return {}
    eq = (1.0 + r).cumprod()
    years = (r.index[-1] - r.index[0]).days / 365.25
    cagr = (float(eq.iloc[-1]) ** (1.0 / years) - 1.0) if years > 0 and eq.iloc[-1] > 0 else np.nan
    sd = float(r.std())
    sharpe = (float(r.mean()) / sd * ANN) if sd > 0 else np.nan
    dd = float((eq / eq.cummax() - 1.0).min())
    skew = float(r.skew()) if len(r) > 8 else np.nan
    worst_m = float(r.rolling(21).sum().min())
    return {"cagr": round(100 * float(cagr), 1) if pd.notna(cagr) else None,
            "sharpe": round(float(sharpe), 2) if pd.notna(sharpe) else None,
            "maxdd": round(100 * dd, 1), "skew": round(float(skew), 2) if pd.notna(skew) else None,
            "worst_month": round(100 * worst_m, 1) if pd.notna(worst_m) else None}


def _split_metrics(r: pd.Series, split: str) -> dict:
    """Full + pre/post split-date metrics (the carry-crash regime boundary)."""
    sd = pd.Timestamp(split)
    out = {"full": _metrics(r)}
    pre, post = r[r.index < sd], r[r.index >= sd]
    if len(pre) >= 252:
        out["pre"] = _metrics(pre)
    if len(post) >= 252:
        out["post"] = _metrics(post)
    return out


# --------------------------------------------------------------------------- #
# G10 carry basket
# --------------------------------------------------------------------------- #
def g10_carry(results: dict, assets_cfg: dict, cfg: dict) -> dict:
    """Long top-N / short bottom-N carry currencies (base-vs-USD), monthly rebalance,
    optional inverse-vol scaling. Returns split metrics + a description."""
    try:
        ccfg = cfg["carry"]
        top_n = ccfg.get("top_n", 3)
        rebal = ccfg.get("rebalance_d", 21)
        cost_bps = cfg.get("cost_bps", 2)
        # pairs with a real carry differential (EM context pairs excluded)
        cols_close, cols_carry = {}, {}
        for p, df in results.items():
            if p == "_dollar" or df is None or df.empty:
                continue
            if "carry_diff" not in df.columns or "close" not in df.columns:
                continue
            base = assets_cfg.get(p, {}).get("base", p)
            cols_close[base] = df["close"]
            cols_carry[base] = df["carry_diff"]
        if len(cols_close) < 2 * top_n:
            return {}
        close = pd.DataFrame(cols_close).sort_index()
        carry = pd.DataFrame(cols_carry).reindex(close.index).ffill()
        ret = close.pct_change()
        idx = close.index
        # rebalance weights: rank by carry on each rebalance day, hold between
        rebal_days = idx[::rebal]
        weights = pd.DataFrame(0.0, index=idx, columns=close.columns)
        for d in rebal_days:
            c = carry.loc[d].dropna()
            if len(c) < 2 * top_n:
                continue
            order = c.sort_values(ascending=False)
            longs, shorts = order.index[:top_n], order.index[-top_n:]
            w = pd.Series(0.0, index=close.columns)
            w[longs] = 1.0 / top_n
            w[shorts] = -1.0 / top_n
            weights.loc[d] = w.values
        weights = weights.replace(0.0, np.nan).ffill().fillna(0.0)
        # next-bar application + turnover cost
        wpos = weights.shift(1).fillna(0.0)
        # total carry-trade return = spot move + the interest differential EARNED by
        # holding (a long high-carry base earns foreign-minus-US rate; a short pays it).
        # carry_diff is annualized %; accrue it on calendar days between bars.
        days = pd.Series(idx, index=idx).diff().dt.days.fillna(0).clip(lower=0)
        carry_income = (wpos * (carry / 100.0)).sum(axis=1) * (days.values / 365.0)
        gross = (wpos * ret).sum(axis=1) + carry_income
        turn = wpos.diff().abs().sum(axis=1).fillna(0.0)
        net = gross - (cost_bps / 1e4) * turn
        # inverse-vol scaling (carry-crash haircut) targeting ~10% annual vol
        if ccfg.get("vol_target"):
            vw = ccfg.get("vol_window_d", 63)
            rv = net.rolling(vw).std() * ANN
            scale = (0.10 / rv.replace(0, np.nan)).clip(0.2, 3.0).shift(1).fillna(1.0)
            net = (net * scale).rename("carry")
        m = _split_metrics(net.dropna(), cfg.get("split_date", "2008-09-15"))
        if not m.get("full"):
            return {}
        # latest tilt (who is long / short now)
        last = carry.iloc[-1].dropna().sort_values(ascending=False)
        longs = list(last.index[:top_n]) if len(last) >= 2 * top_n else []
        shorts = list(last.index[-top_n:]) if len(last) >= 2 * top_n else []
        span = f"{idx.min().date()}..{idx.max().date()}"
        return {"key": "carry", "metrics": m, "longs": longs, "shorts": shorts,
                "top_n": top_n, "span": span, "n_ccy": len(cols_close)}
    except Exception as e:  # noqa: BLE001
        log.warning("g10_carry scorecard failed (%s)", e)
        return {}


# --------------------------------------------------------------------------- #
# Dollar trend overlay
# --------------------------------------------------------------------------- #
def dollar_trend(dxy: pd.Series | None, cfg: dict, lookback: int = 252) -> dict:
    """Long the dollar index when its 12m trend is up, else flat. Crash-avoidance
    overlay vs buy & hold — reuses validation.backtest_core."""
    try:
        if dxy is None or dxy.empty:
            return {}
        dxy = pd.to_numeric(dxy, errors="coerce").dropna()
        if len(dxy) < lookback + 252:
            return {}
        alloc = (dxy.pct_change(lookback) > 0).astype(float)
        bt = backtest_core(dxy, alloc, cost_bps=cfg.get("cost_bps", 2))
        m = _split_metrics(bt["net"], cfg.get("split_date", "2008-09-15"))
        if not m.get("full"):
            return {}
        hold = _metrics(bt["hold"])
        cur_up = bool(alloc.iloc[-1] > 0)
        return {"key": "dollar_trend", "metrics": m, "hold": hold,
                "in_market": cur_up, "span": f"{dxy.index.min().date()}..{dxy.index.max().date()}"}
    except Exception as e:  # noqa: BLE001
        log.warning("dollar_trend scorecard failed (%s)", e)
        return {}


# --------------------------------------------------------------------------- #
# Risk-off haven basket (the mirror of carry)
# --------------------------------------------------------------------------- #
def haven_basket(results: dict, assets_cfg: dict, risk_off: pd.Series | None, cfg: dict) -> dict:
    """Long the haven/funder currencies (JPY, CHF) vs short the risk currencies
    (AUD, CAD, EM), static weights. This is the MIRROR of the carry trade: it bleeds
    the carry differential as an insurance premium most of the time, but PAYS in
    risk-off when havens rally and risk currencies fall. We surface its calm-vs-stress
    annualized return (split on the risk-off composite) — the whole point."""
    try:
        hcfg = cfg.get("haven", {})
        cost_bps = cfg.get("cost_bps", 2)
        longs, shorts, closes, carries = [], [], {}, {}
        for p, df in results.items():
            if p == "_dollar" or df is None or df.empty or "close" not in df.columns:
                continue
            arch = assets_cfg.get(p, {}).get("archetype", "")
            base = assets_cfg.get(p, {}).get("base", p)
            if arch == "haven-funder":
                longs.append(base)
            elif arch in ("commodity-dollar", "em", "em-managed"):
                shorts.append(base)
            else:
                continue
            closes[base] = df["close"]
            carries[base] = df["carry_diff"] if "carry_diff" in df.columns else None
        if len(longs) < 1 or len(shorts) < 1:
            return {}
        close = pd.DataFrame(closes).sort_index()
        idx = close.index
        ret = close.pct_change()
        w = pd.Series(0.0, index=close.columns)
        for b in longs:
            w[b] = 1.0 / len(longs)
        for b in shorts:
            w[b] = -1.0 / len(shorts)
        # total return = spot move + the carry differential earned (havens & shorted
        # high-yielders both BLEED carry -> a net negative-carry insurance basket)
        days = pd.Series(idx, index=idx).diff().dt.days.fillna(0).clip(lower=0)
        carry_df = pd.DataFrame({b: (carries[b] if carries.get(b) is not None
                                     else pd.Series(0.0, index=idx)) for b in close.columns})
        carry_df = carry_df.reindex(idx).ffill()
        carry_income = (carry_df / 100.0 * w).sum(axis=1) * (days.values / 365.0)
        net = (ret * w).sum(axis=1) + carry_income          # static weights -> ~no turnover cost
        net = net - (cost_bps / 1e4) * 0.0
        if hcfg.get("vol_target", True):
            vw = hcfg.get("vol_window_d", 63)
            rv = net.rolling(vw).std() * ANN
            scale = (0.10 / rv.replace(0, np.nan)).clip(0.2, 3.0).shift(1).fillna(1.0)
            net = net * scale
        net = net.dropna()
        m = _split_metrics(net, cfg.get("split_date", "2008-09-15"))
        if not m.get("full"):
            return {}
        regime = None
        if risk_off is not None:
            j = pd.concat([net.rename("r"), risk_off.reindex(net.index).rename("ro")],
                          axis=1).dropna()
            if len(j) > 200:
                calm, stress = j[j["ro"] <= 0]["r"], j[j["ro"] > 0]["r"]
                regime = {"calm_ann": round(100 * float(calm.mean()) * 252, 1) if len(calm) else None,
                          "stress_ann": round(100 * float(stress.mean()) * 252, 1) if len(stress) else None}
        return {"key": "haven", "metrics": m, "longs": longs, "shorts": shorts,
                "regime": regime, "span": f"{idx.min().date()}..{idx.max().date()}"}
    except Exception as e:  # noqa: BLE001
        log.warning("haven_basket scorecard failed (%s)", e)
        return {}


def scorecards(results: dict, assets_cfg: dict, dxy: pd.Series | None,
               cfg: dict, risk_off: pd.Series | None = None) -> list[dict]:
    """Assemble the scorecard list (skips any that fail to compute)."""
    out = []
    c = g10_carry(results, assets_cfg, cfg)
    if c:
        out.append(c)
    h = haven_basket(results, assets_cfg, risk_off, cfg)
    if h:
        out.append(h)
    d = dollar_trend(dxy, cfg)
    if d:
        out.append(d)
    return out
