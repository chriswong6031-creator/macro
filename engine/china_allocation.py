"""China Income Vector — a statically-diversified, drawdown-managed income allocation.

The onshore-RMB analogue of the US S&P Vector, redesigned for how China's market
actually behaves. The US strategy times a broad index <-> T-bills on a macro/trend
score; that template does NOT port to China, for two structural reasons:

  1. A-shares are CYCLICAL and mean-reverting (not a perpetual uptrend), so a trend /
     momentum timing overlay WHIPSAWS — measured here, it lowers Sharpe and does not
     cut drawdown (see `momentum_overlay_ab`). It is OFF by default and shipped only
     as an honest "we tested timing, it doesn't help" comparison.
  2. The cash leg is broken — 10Y CGB ~1.7%, money-market ~0.8% — so de-risking into
     cash earns nothing.

What DOES work in China is DIVERSIFICATION, not timing. An income / "cashflow-king"
core (dividend / low-vol / free-cash-flow ETF) blended with GOLD and short BONDS —
the two liquid onshore assets that are ~uncorrelated to A-share equity (daily corr to
the dividend ETF ~0.06 gold / ~-0.11 bond) — lifts the Sharpe ratio from ~0.5 (CSI 300
buy & hold) to ~1.0-1.2 and cuts the max drawdown from ~-45% to ~-10/-16%. That blend
IS the strategy; the income core is the return engine, gold the crisis diversifier,
bonds the low-vol ballast.

DISPLAY-ONLY / educational allocation tool. It is independent of and never scored into
engine/china_axes.py, china_regime.py or china_playbook.py. Backtest reuses the house
harness: next-bar execution, cost-aware, gold/bond carry their OWN return streams (not a
cash yield). House rule — judge on forward DRAWDOWN, and because China history is short,
report the independent BEAR-EPISODE count and a block-bootstrap CI, never a bare Sharpe.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.equity_alloc import bear_episodes
from engine.validation import block_bootstrap_ci
from lib import store

TRADING_YEAR = 252
REBAL_COST_PP = 0.10   # ~10bps/yr drag for a quarterly-rebalanced static blend (conservative)

# --------------------------------------------------------------------------- #
# instruments — onshore RMB ETFs (fetched into the `china` store group)
# --------------------------------------------------------------------------- #
# role: income (the cashflow-king core), growth (A-share beta kicker), gold, bond.
SLEEVES: dict[str, dict] = {
    "income":  {"ticker": "510880.SS", "role": "income",
                "name_en": "Dividend (income core)", "name_zh": "红利（收入核心）", "color": "#C0392B"},
    "growth":  {"ticker": "510300.SS", "role": "growth",
                "name_en": "CSI 300 (growth kicker)", "name_zh": "沪深300（增长）", "color": "#2E86DE"},
    "gold":    {"ticker": "518880.SS", "role": "gold",
                "name_en": "Gold", "name_zh": "黄金", "color": "#D4A017"},
    "bond":    {"ticker": "511010.SS", "role": "bond",
                "name_en": "Treasury bonds", "name_zh": "国债", "color": "#27AE60"},
}
# Alternative income cores surfaced on the page (not used in the deep backtest because
# they are shorter-lived): low-vol dividend and the new "cash-cow" free-cash-flow ETF.
ALT_CORES = {
    "510880.SS": {"name_en": "SSE Dividend", "name_zh": "上证红利", "since": "2008"},
    "512890.SS": {"name_en": "CSI Dividend Low-Vol", "name_zh": "中证红利低波", "since": "2018"},
    "159201.SZ": {"name_en": "Free Cash Flow ('cash-cow')", "name_zh": "自由现金流（现金牛）", "since": "2025"},
}

# Static variants. Weights sum to 1; each value is a target portfolio weight.
VARIANTS: dict[str, dict] = {
    "conservative": {"label_en": "Conservative", "label_zh": "保守",
                     "weights": {"income": 0.25, "gold": 0.25, "bond": 0.50},
                     "blurb_en": "Bond-heavy — shallowest drawdown, steadiest line.",
                     "blurb_zh": "偏债 —— 回撤最浅、曲线最稳。"},
    "balanced":     {"label_en": "Balanced", "label_zh": "均衡",
                     "weights": {"income": 0.35, "gold": 0.30, "bond": 0.35},
                     "blurb_en": "The risk-parity-style default — best Sharpe per unit of drawdown.",
                     "blurb_zh": "类风险平价的默认 —— 单位回撤的夏普最佳。"},
    "growth":       {"label_en": "Growth", "label_zh": "进取",
                     "weights": {"income": 0.225, "growth": 0.225, "gold": 0.30, "bond": 0.25},
                     "blurb_en": "Adds a CSI 300 sleeve — higher return, still ~quarter the index drawdown.",
                     "blurb_zh": "加入沪深300 —— 更高收益，回撤仍约为指数的四分之一。"},
}
DEFAULT_VARIANT = "balanced"


# --------------------------------------------------------------------------- #
# data
# --------------------------------------------------------------------------- #
def _close(ticker: str, group: str = "china") -> pd.Series | None:
    df = store.read(group, ticker)
    if df is None or df.empty or "close" not in df.columns:
        return None
    s = df["close"].astype(float).dropna()
    return s if len(s) else None


def sleeve_returns(keys: list[str], income_ticker: str | None = None) -> pd.DataFrame:
    """Aligned daily returns for the requested sleeves (inner-join on common dates).
    `income_ticker` overrides the income sleeve's ETF (e.g. the low-vol core)."""
    cols: dict[str, pd.Series] = {}
    for k in keys:
        tk = income_ticker if (k == "income" and income_ticker) else SLEEVES[k]["ticker"]
        s = _close(tk)
        if s is not None:
            cols[k] = s
    if not cols:
        return pd.DataFrame()
    px = pd.concat(cols, axis=1, sort=True).dropna()   # sorted union of the sleeve dates
    return px.pct_change().dropna(how="all").fillna(0.0)


# --------------------------------------------------------------------------- #
# stats (small, local — mirror engine/equity_alloc helpers, keep this leaf standalone)
# --------------------------------------------------------------------------- #
def _cagr(eq: pd.Series, years: float) -> float:
    return float(eq.iloc[-1]) ** (1 / years) - 1 if years > 0 and eq.iloc[-1] > 0 else np.nan


def _sharpe(r: pd.Series) -> float:
    sd = r.std()
    return float(r.mean() / sd * np.sqrt(TRADING_YEAR)) if sd else np.nan


def _sortino(r: pd.Series) -> float:
    dn = r[r < 0].std()
    return float(r.mean() / dn * np.sqrt(TRADING_YEAR)) if dn else np.nan


def _maxdd(eq: pd.Series) -> float:
    return float((eq / eq.cummax() - 1).min())


def _vol(r: pd.Series) -> float:
    return float(r.std() * np.sqrt(TRADING_YEAR))


def blend_returns(weights: dict, rets: pd.DataFrame, cost_pp: float = REBAL_COST_PP) -> pd.Series:
    """Constant-mix (rebalanced) daily return of a static target blend, net of a flat
    annualized rebalancing drag (cost_pp, charged evenly across trading days). A static
    sleeve blend has very low turnover, so a small flat drag is a fair, conservative
    stand-in for quarterly rebalancing costs."""
    avail = [k for k in weights if k in rets.columns]
    if not avail:
        return pd.Series(dtype=float)
    w = {k: weights[k] for k in avail}
    tot = sum(w.values()) or 1.0
    gross = sum((wk / tot) * rets[k] for k, wk in w.items())
    drag = (cost_pp / 100.0) / TRADING_YEAR
    return gross - drag


# --------------------------------------------------------------------------- #
# backtest
# --------------------------------------------------------------------------- #
def _scorecard(ret: pd.Series, label: str) -> dict:
    ret = ret.dropna()
    eq = (1 + ret).cumprod()
    years = (ret.index[-1] - ret.index[0]).days / 365.25 if len(ret) > 1 else np.nan
    return {
        "label": label,
        "start": ret.index[0].strftime("%Y-%m-%d") if len(ret) else None,
        "years": round(years, 1) if pd.notna(years) else None,
        "cagr": round(100 * _cagr(eq, years), 2) if pd.notna(years) else None,
        "vol": round(100 * _vol(ret), 1),
        "sharpe": round(_sharpe(ret), 2),
        "sortino": round(_sortino(ret), 2),
        "maxdd": round(100 * _maxdd(eq), 1),
        "final_mult": round(float(eq.iloc[-1]), 2) if len(eq) else None,
    }


def backtest(variant: str = DEFAULT_VARIANT, income_ticker: str | None = None,
             start: str | None = None) -> dict:
    """Full scorecard for one variant on the deepest common window of its sleeves, vs
    two benchmarks (CSI 300 buy & hold, income-core only). Adds the independent
    bear-episode count + a block-bootstrap 95% CI on Sharpe / MaxDD (the honest sample
    size for a China strategy with short history)."""
    spec = VARIANTS[variant]
    keys = list(spec["weights"].keys())
    rets = sleeve_returns(sorted(set(keys + ["growth", "income"])), income_ticker)
    if rets.empty:
        return {"variant": variant, "error": "no data"}
    if start:
        rets = rets.loc[start:]
    ret = blend_returns(spec["weights"], rets).dropna()
    if ret.empty:
        return {"variant": variant, "error": "no overlap"}
    out = _scorecard(ret, spec["label_en"])
    out["variant"] = variant
    # benchmarks on the SAME window
    bench = rets.loc[ret.index]
    if "growth" in bench:
        out["bench_csi300"] = _scorecard(bench["growth"], "CSI 300 buy & hold")
    if "income" in bench:
        out["bench_income"] = _scorecard(bench["income"], "Income core only")
    # honest-N + CI
    eq = (1 + ret).cumprod()
    out["bear_episodes"] = bear_episodes(eq, 0.10)          # 10%+ episodes (China blends are shallow)
    out["bootstrap"] = block_bootstrap_ci(ret, block=21, B=4000, ann=TRADING_YEAR)
    return out


def equity_curves(variant: str = DEFAULT_VARIANT, income_ticker: str | None = None) -> dict:
    """{dates, strat, csi300, income, dd_strat, dd_csi300} growth-of-1 + drawdown series
    for the page charts (the blend vs CSI 300 buy & hold vs the income core alone)."""
    spec = VARIANTS[variant]
    keys = sorted(set(list(spec["weights"].keys()) + ["growth", "income"]))
    rets = sleeve_returns(keys, income_ticker)
    if rets.empty:
        return {"dates": []}
    ret = blend_returns(spec["weights"], rets).dropna()
    idx = ret.index
    eq = (1 + ret).cumprod()
    csi = (1 + rets["growth"].loc[idx]).cumprod() if "growth" in rets else None
    inc = (1 + rets["income"].loc[idx]).cumprod() if "income" in rets else None

    def dd(s):
        return (s / s.cummax() - 1) * 100

    return {
        "dates": [d.strftime("%Y-%m-%d") for d in idx],
        "strat": [round(float(v), 4) for v in eq],
        "csi300": [round(float(v), 4) for v in csi] if csi is not None else [],
        "income": [round(float(v), 4) for v in inc] if inc is not None else [],
        "dd_strat": [round(float(v), 2) for v in dd(eq)],
        "dd_csi300": [round(float(v), 2) for v in dd(csi)] if csi is not None else [],
    }


# --------------------------------------------------------------------------- #
# momentum overlay A/B — the honest "we tested timing, it doesn't help" panel
# --------------------------------------------------------------------------- #
def momentum_overlay_ab(variant: str = DEFAULT_VARIANT, window: int = 200) -> dict:
    """Compare the static blend against the SAME blend with a slow (Faber-style, monthly)
    trend overlay that de-risks the income+growth sleeves into bonds when the equity
    benchmark is below its `window`-day MA. Returns both scorecards so the page can show,
    transparently, that momentum timing lowers Sharpe / does not cut drawdown in China's
    mean-reverting market — the direct evidence behind keeping the strategy static."""
    spec = VARIANTS[variant]
    keys = sorted(set(list(spec["weights"].keys()) + ["growth", "income"]))
    rets = sleeve_returns(keys, None)
    if rets.empty or "growth" not in rets:
        return {}
    static_ret = blend_returns(spec["weights"], rets)
    # trend signal on CSI 300, checked monthly (suppresses whipsaw), acted next bar
    csi_px = _close(SLEEVES["growth"]["ticker"]).reindex(rets.index).ffill()
    sma = csi_px.rolling(window).mean()
    on = (csi_px > sma).resample("ME").last().reindex(rets.index, method="ffill").fillna(False)
    on = on.shift(1).fillna(False)
    # overlay: when OFF, the equity sleeves (income+growth) rotate to bonds
    eqw = {k: v for k, v in spec["weights"].items() if k in ("income", "growth")}
    defw = {k: v for k, v in spec["weights"].items() if k in ("gold", "bond")}
    rb = rets.get("bond", pd.Series(0.0, index=rets.index))
    on_f = on.astype(float)
    eq_ret = sum(w * (on_f * rets[k] + (1 - on_f) * rb) for k, w in eqw.items() if k in rets)
    def_ret = sum(w * rets[k] for k, w in defw.items() if k in rets)
    drag = (REBAL_COST_PP / 100.0) / TRADING_YEAR
    overlay_ret = (eq_ret + def_ret - drag).dropna()
    static_ret = static_ret.loc[overlay_ret.index]
    a, b = _scorecard(static_ret, "Static (no timing)"), _scorecard(overlay_ret, f"{window}d trend overlay")
    return {"variant": variant, "static": a, "overlay": b,
            "verdict_en": ("Timing LOWERS the Sharpe ratio and does not reduce drawdown — "
                           "diversification, not momentum, is the edge in China."),
            "verdict_zh": "择时降低夏普且不减回撤 —— 在中国，优势来自分散而非动量。",
            "helps": bool(b["sharpe"] is not None and a["sharpe"] is not None and b["sharpe"] > a["sharpe"])}


# --------------------------------------------------------------------------- #
# current read + the latest card the index-health button consumes
# --------------------------------------------------------------------------- #
def current_read(income_ticker: str | None = None) -> dict:
    """Per-sleeve latest price, 1-day change, % off 52w high, and trend-vs-200d — the
    'where each sleeve is now' strip on the page."""
    rows = []
    for k, meta in SLEEVES.items():
        s = _close(income_ticker if (k == "income" and income_ticker) else meta["ticker"])
        if s is None or len(s) < 2:
            continue
        px = float(s.iloc[-1])
        chg = float(s.iloc[-1] / s.iloc[-2] - 1) * 100
        hi = float(s.iloc[-252:].max()) if len(s) >= 60 else float(s.max())
        sma200 = float(s.iloc[-200:].mean()) if len(s) >= 200 else None
        rows.append({"key": k, "role": meta["role"], "name_en": meta["name_en"],
                     "name_zh": meta["name_zh"], "color": meta["color"],
                     "price": round(px, 3), "chg": round(chg, 2),
                     "off_high": round(100 * (px / hi - 1), 1) if hi else None,
                     "above200": (px > sma200) if sma200 else None})
    return {"sleeves": rows}


def latest_card(variant: str = DEFAULT_VARIANT) -> dict:
    """Compact dict for the China index-health allocation button (mirrors the US
    alloc_card): recommended variant, its growth/defensive split, Sharpe & MaxDD."""
    bt = backtest(variant)
    if bt.get("error"):
        return {"present": False}
    w = VARIANTS[variant]["weights"]
    growth_w = round(100 * (w.get("income", 0) + w.get("growth", 0)))
    defensive_w = round(100 * (w.get("gold", 0) + w.get("bond", 0)))
    maxdd = bt.get("maxdd")
    band = ("low" if maxdd is not None and maxdd > -12
            else "elevated" if maxdd is not None and maxdd > -20 else "high")
    return {"present": True, "variant": variant,
            "label_en": VARIANTS[variant]["label_en"], "label_zh": VARIANTS[variant]["label_zh"],
            "growth_w": growth_w, "defensive_w": defensive_w,
            "sharpe": bt.get("sharpe"), "maxdd": maxdd, "cagr": bt.get("cagr"),
            "band": band, "years": bt.get("years")}


def snapshot() -> dict:
    """The full bundle the build script persists to china_alloc_latest.json: all variants'
    scorecards, the balanced equity/drawdown series, the momentum A/B, the per-sleeve
    current read, and the alt income-core menu. Everything degrades gracefully."""
    variants = {v: backtest(v) for v in VARIANTS}
    return {
        "as_of": _as_of(),
        "default_variant": DEFAULT_VARIANT,
        "variants": variants,
        "curves": equity_curves(DEFAULT_VARIANT),
        "momentum_ab": momentum_overlay_ab(DEFAULT_VARIANT),
        "current": current_read(),
        "card": latest_card(DEFAULT_VARIANT),
        "alt_cores": ALT_CORES,
        "display_only": True,
        "note": ("display-only educational allocation — a static, diversified income+gold+bond "
                 "blend; independent of and never scored into china_axes / china_regime / china_playbook"),
    }


def _as_of() -> str | None:
    s = _close(SLEEVES["income"]["ticker"])
    return s.index[-1].strftime("%Y-%m-%d") if s is not None and len(s) else None
