"""Cross-Asset Vector — multi-asset TREND (time-series momentum), INTERMARKET
RATIOS, and a light CARRY context, over a keyless price universe.

ADDITIVE / leaf module — imports nothing from the scoring core, and nothing in the
scoring path imports it. It REUSES the existing correlation-regime leaf
(engine.cross_asset.snapshot, the Kritzman-Page absorption ratio) for the
correlation panel rather than recomputing it.

TREND is the canonical time-series-momentum factor (Moskowitz-Ooi-Pedersen /
AQR managed-futures): the sign of each asset's trailing return predicts its next
return, diversified across asset classes. We compute the simple, leverage-free
variant — alloc ∈ [-1,1] = the average sign of the trailing return across 3/6/12-
month horizons (skip the most recent week to dodge 1-week reversal). AQR reports a
gross-of-cost diversified Sharpe ~1.8 and the effect is academically contested, so
the HONEST number we publish is the AFTER-COST, DSR-deflated, permutation-null one
(scripts/cross_asset_phase0.py) — never the gross headline. Framed as a REGIME /
CONTEXT read ("what is trending across asset classes"), not a buy list.

No new collectors: every series is read from the existing keyless stores
(yahoo closes; FRED yields for the bond leg, traded as a duration-return proxy).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

# universe fallback if config.cross_asset.universe is absent: name -> (group, key, col, class)
# CA-W3-R5: trend universe expanded with EFA/EEM/TLT legs (display regime read).
# NOTE: DEFAULT_MARKETS in engine.cross_asset (concentration universe) is FROZEN — do NOT touch it.
_DEFAULT_UNIVERSE = {
    "equity_us":    ("yahoo", "SPY",       "close", "equity"),
    "equity_sm":    ("yahoo", "IWM",       "close", "equity"),
    "equity_intl":  ("yahoo", "EFA",       "close", "equity"),   # CA-W3-R5
    "equity_em":    ("yahoo", "EEM",       "close", "equity"),   # CA-W3-R5
    "credit_hy":    ("yahoo", "HYG",       "close", "credit"),
    "gold":         ("yahoo", "GC=F",      "close", "commodity"),
    "silver":       ("yahoo", "SI=F",      "close", "commodity"),
    "copper":       ("yahoo", "HG=F",      "close", "commodity"),
    "oil":          ("yahoo", "CL=F",      "close", "commodity"),
    "dollar":       ("yahoo", "DX-Y.NYB",  "close", "fx"),
    "bond_10y":     ("fred",  "DGS10",     "us10y", "rates"),    # duration-return proxy
    "duration":     ("yahoo", "TLT",       "close", "rates"),    # CA-W3-R5
    "crypto":       ("yahoo", "BTC-USD",   "close", "crypto"),
}
_CLASS_LABEL = {"equity": ("Equity", "股票"), "credit": ("Credit", "信用"),
                "commodity": ("Commodity", "商品"), "fx": ("Dollar", "美元"),
                "rates": ("Rates", "利率"), "crypto": ("Crypto", "加密")}
_NAME_LABEL = {
    "equity_us":   ("S&P 500",          "标普500"),
    "equity_sm":   ("Small caps",        "小盘股"),
    "equity_intl": ("Intl stocks (DM)",  "国际发达股市"),   # CA-W3-R5
    "equity_em":   ("EM stocks",         "新兴市场股市"),   # CA-W3-R5
    "credit_hy":   ("High yield",        "高收益债"),
    "gold":        ("Gold",              "黄金"),
    "silver":      ("Silver",            "白银"),
    "copper":      ("Copper",            "铜"),
    "oil":         ("Crude oil",         "原油"),
    "dollar":      ("US dollar",         "美元"),
    "bond_10y":    ("10Y Treasury",      "10年美债"),
    "duration":    ("Long Treasuries",   "长期美债"),        # CA-W3-R5
    "crypto":      ("Bitcoin",           "比特币"),
}
_BOND_DURATION = 7.0   # approx modified duration of the 10y for the -D·Δy return proxy


def _cfg() -> dict:
    return config.load().get("cross_asset", {}) or {}


def _universe(cfg: dict | None = None) -> dict:
    cfg = cfg if cfg is not None else _cfg()
    u = cfg.get("universe")
    return {k: tuple(v) for k, v in u.items()} if u else _DEFAULT_UNIVERSE


def _bond_price_index(yld: pd.Series, dur: float = _BOND_DURATION) -> pd.Series:
    """Synthetic bond total-return price index from a yield LEVEL series (%).
    Daily price return ≈ -duration · Δyield (carry omitted) → cumulated to a price.
    A coarse but standard duration-return proxy so the bond leg can join TSMOM."""
    y = yld.astype(float).dropna()
    r = (-dur * y.diff() / 100.0).fillna(0.0)
    return (1.0 + r).cumprod() * 100.0


def _load_universe(cfg: dict | None = None) -> dict[str, pd.Series]:
    """name -> daily price (or price-proxy) series, from the keyless stores."""
    out: dict[str, pd.Series] = {}
    for name, (grp, key, col, _cls) in _universe(cfg).items():
        df = store.read(grp, key)
        if df is None or col not in getattr(df, "columns", []):
            continue
        s = df[col].astype(float).dropna()
        if len(s) < 300:
            continue
        out[name] = _bond_price_index(s) if grp == "fred" else s
    return out


# --------------------------------------------------------------------------- #
# TREND — time-series momentum (the validated core)
# --------------------------------------------------------------------------- #
def tsmom_alloc(price: pd.Series, cfg: dict | None = None) -> pd.Series:
    """Leverage-free TSMOM position ∈ [-1,1] = average sign of the trailing return
    across the configured horizons, skipping the most recent `skip_d` days. PURE.
    backtest_core applies the next-bar lag, so this is causal as-is."""
    t = (cfg or _cfg()).get("tsmom", {})
    lbs = t.get("lookbacks_d", [63, 126, 252])
    skip = int(t.get("skip_d", 5))
    p = price.astype(float)
    base = p.shift(skip)
    sig = pd.DataFrame({lb: np.sign(base.pct_change(lb)) for lb in lbs})
    return sig.mean(axis=1).reindex(price.index).fillna(0.0)


def _trail_ret(price: pd.Series, n: int) -> float | None:
    p = price.dropna()
    if len(p) < n + 1:
        return None
    v = p.iloc[-1] / p.iloc[-1 - n] - 1.0
    return float(v * 100.0) if np.isfinite(v) else None


def tsmom_panel(cfg: dict | None = None, universe: dict[str, pd.Series] | None = None) -> dict:
    """Current cross-asset trend board + a trend-breadth regime read."""
    cfg = cfg if cfg is not None else _cfg()
    uni = universe if universe is not None else _load_universe(cfg)
    cls = {k: v[3] for k, v in _universe(cfg).items()}
    rows, asof = [], None
    for name, price in uni.items():
        alloc = tsmom_alloc(price, cfg)
        score = float(alloc.iloc[-1]) if len(alloc) else 0.0
        state = "up" if score >= 0.34 else "down" if score <= -0.34 else "mixed"
        c = cls.get(name, "—")
        nl = _NAME_LABEL.get(name, (name, name))
        clab = _CLASS_LABEL.get(c, (c, c))
        rows.append({"key": name, "class": c, "name_en": nl[0], "name_zh": nl[1],
                     "class_en": clab[0], "class_zh": clab[1],
                     "score": round(score, 2), "trend": state,
                     "ret_3m": _round(_trail_ret(price, 63)), "ret_6m": _round(_trail_ret(price, 126)),
                     "ret_12m": _round(_trail_ret(price, 252))})
        asof = max(asof, price.index[-1]) if asof is not None else price.index[-1]
    rows.sort(key=lambda r: r["score"], reverse=True)
    n = len(rows)
    n_up = sum(1 for r in rows if r["trend"] == "up")
    n_down = sum(1 for r in rows if r["trend"] == "down")
    breadth = round((n_up - n_down) / n, 2) if n else 0.0
    regime = ("risk-on trends" if breadth >= 0.34 else
              "risk-off / defensive trends" if breadth <= -0.34 else "mixed / no clear trend")
    return {"asof": None if asof is None else str(asof.date()), "rows": rows,
            "n": n, "n_up": n_up, "n_down": n_down, "breadth": breadth, "regime": regime}


# --------------------------------------------------------------------------- #
# INTERMARKET RATIOS (no new data — from the universe closes)
# --------------------------------------------------------------------------- #
_RATIO_DEF = {
    "copper_gold": ("copper", "gold", ("Copper / Gold", "铜/金"),
                    "Cyclical-growth & bond-yield proxy (Gundlach): rising = growth/yields up."),
    "gold_silver": ("gold", "silver", ("Gold / Silver", "金/银"),
                    "Risk appetite: a high ratio (silver cheap) is defensive / late-cycle."),
    "oil_gold":    ("oil", "gold", ("Oil / Gold", "油/金"),
                    "Real-economy vs safe-haven demand: rising = reflation/growth."),
    "stocks_gold": ("equity_us", "gold", ("Stocks / Gold", "股/金"),
                    "Risk-asset vs hard-asset preference: rising = risk-on regime."),
}


def _pctile(s: pd.Series, lookback: int) -> float | None:
    s = s.dropna()
    if len(s) < 60:
        return None
    win = s.tail(lookback)
    return float((win <= win.iloc[-1]).mean() * 100.0)


def ratio_panel(universe: dict[str, pd.Series] | None = None, cfg: dict | None = None) -> list[dict]:
    cfg = cfg if cfg is not None else _cfg()
    uni = universe if universe is not None else _load_universe(cfg)
    lb = int(cfg.get("ratios", {}).get("pctile_lookback_d", 504))
    out = []
    for key, (num, den, label, note) in _RATIO_DEF.items():
        if num not in uni or den not in uni:
            continue
        a, b = uni[num], uni[den]
        idx = a.index.intersection(b.index)
        r = (a.reindex(idx).ffill() / b.reindex(idx).ffill()).dropna()
        if len(r) < 60:
            continue
        pct = _pctile(r, lb)
        chg = float(r.iloc[-1] / r.iloc[-min(63, len(r) - 1)] - 1.0) * 100.0 if len(r) > 63 else None
        state = ("elevated" if pct is not None and pct >= 80 else
                 "depressed" if pct is not None and pct <= 20 else "mid")
        out.append({"key": key, "label_en": label[0], "label_zh": label[1], "note": note,
                    "value": round(float(r.iloc[-1]), 3), "pctile": _round(pct, 0),
                    "chg_3m": _round(chg), "state": state})
    return out


# --------------------------------------------------------------------------- #
# CARRY (current-state context only — short history, NOT backtested here)
# --------------------------------------------------------------------------- #
def carry_panel(cfg: dict | None = None) -> dict:
    """Light cross-asset carry context: rates term-spread (10y-3m) + commodity
    roll-yield (front-vs-second) where available. Current-state CONTEXT — the
    commodity roll-yield store has <2y history, so this is NOT a validated factor."""
    rows = []
    d10 = store.read("fred", "DGS10")
    d3 = store.read("fred", "DTB3")
    if d10 is not None and d3 is not None and "us10y" in d10 and "us3m" in d3:
        sp = float(d10["us10y"].dropna().iloc[-1] - d3["us3m"].dropna().iloc[-1])
        rows.append({"key": "rates_term", "label_en": "Rates term-spread (10y-3m)",
                     "label_zh": "利率期限利差 (10年-3月)", "value": round(sp, 2), "unit": "%",
                     "state": "positive carry" if sp > 0 else "inverted (negative carry)"})
    for asset in ("gold", "silver", "copper", "oil"):
        c = store.read("commodity_carry", asset)
        if c is not None and "roll_yield_ann" in getattr(c, "columns", []):
            v = c["roll_yield_ann"].dropna()
            if len(v) and abs(float(v.iloc[-1])) >= 0.05:   # skip degenerate/near-zero
                ry = float(v.iloc[-1])
                rows.append({"key": f"roll_{asset}", "label_en": f"{asset.title()} roll yield",
                             "label_zh": f"{asset} 展期收益", "value": round(ry, 1), "unit": "%/yr",
                             "state": "backwardation (positive)" if ry > 0 else "contango (negative)"})
    return {"rows": rows,
            "note": "Current-state carry context only. Rates term-spread has deep history; "
                    "commodity roll-yield is reconstructed from dated futures with <2y of "
                    "history, so it is NOT backtested as a factor. Context, not a buy list."}


def correlation_snapshot() -> dict:
    """Reuse the existing cross-asset correlation-regime leaf (absorption ratio)."""
    try:
        from engine import cross_asset
        return cross_asset.snapshot()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("correlation snapshot failed (%s)", e)
        return {"verdict": "unknown", "headline": "correlation leaf unavailable"}


# --------------------------------------------------------------------------- #
# assembly for the page + hub
# --------------------------------------------------------------------------- #
NOTE = ("Cross-asset trend = time-series momentum (sign of trailing return), the "
        "canonical managed-futures factor — shown as a REGIME read, not a buy list. "
        "AQR's gross Sharpe is contested; the validated, after-cost number is in "
        "reports/cross-asset-phase0.md. Carry & ratios are current-state context.")


def snapshot(cfg: dict | None = None) -> dict | None:
    cfg = cfg if cfg is not None else _cfg()
    uni = _load_universe(cfg)
    if len(uni) < 4:
        return None
    trend = tsmom_panel(cfg, uni)
    corr = correlation_snapshot()
    return {
        "asof": trend.get("asof"),
        "built": datetime.now(timezone.utc).isoformat(),
        "note": NOTE,
        "regime": trend.get("regime"),
        "breadth": trend.get("breadth"),
        "trend": trend,
        "ratios": ratio_panel(uni, cfg),
        "carry": carry_panel(cfg),
        "correlation": corr,
        # compact hub feed
        "favored": [r["key"] for r in trend["rows"] if r["trend"] == "up"][:5],
    }


def _round(v, nd: int = 1):
    return None if v is None or not np.isfinite(v) else round(float(v), nd)
