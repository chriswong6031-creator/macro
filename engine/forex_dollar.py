"""Dollar Desk — a deepened, multi-signal read of the master variable (broad USD).

The dollar routes ~89% of FX turnover, so it is the hub that conditions every pair
on the board AND the cross-asset picture (commodities, equities, bonds, crypto).
The existing master tile is thin (a 4-quad "smile" + a risk-off composite). This
module adds the signals a real dollar desk watches, all from data already in the
store but unused by the forex page:

  real-rate regime   US 10y real yield (DFII10) + 10y breakeven (T10YIE) -> the
                     dollar's structural anchor and which arm of the smile (real-led
                     vs reflation) is driving.
  Fed path           implied Fed-funds path from ZQ futures (the US leg of the rate
                     differential) + its repricing momentum.
  positioning        CFTC COT net-spec on the US Dollar Index (cot_dollar, 1995->) —
                     a crowding / fragility gauge (NOT a timing signal).
  valuation          US BIS REER vs its long-run mean — multi-year rich/cheap anchor.
  trend stack        broad-USD trend across 21/63/126/252d — a breadth/coherence read.
  liquidity          net Fed liquidity (WALCL - RRP) rate-of-change — scarcer dollars
                     are USD-supportive (slow, regime-conditional).
  smile confirmation tally how many independent legs corroborate the smile regime,
                     plus a "triple-red" haven-loss flag (USD & stocks & bonds down
                     together — the dollar NOT acting as a haven).

HONESTY BAR (load-bearing): every signal here is DISPLAY-ONLY / never scored. FX
violates UIP, the dollar move is often the tightening itself (coincident), and every
forex conviction backtest fails the deflated-Sharpe bar (reports/forex-calibration.md).
These are REGIME / CONTEXT reads, not trade calls. There is deliberately NO aggregate
"USD score -> BUY/SELL" — a `lean` word summarizes the balance of context flags and
says so. No literature magnitude constants are baked into outputs; everything is
computed live from the store with rolling, causal windows.

Pure module: every function guards missing data and returns None / a degraded dict
rather than raising, so build_forex can never break the site.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine import commodity_signals as cs
from engine import forex_signals as fxs

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _last(s: pd.Series | None) -> float | None:
    """Last finite value of a series, else None."""
    if s is None or len(s) == 0:
        return None
    s = s.dropna()
    return float(s.iloc[-1]) if len(s) else None


def _roc(s: pd.Series, w: int) -> float | None:
    if s is None or len(s) <= w:
        return None
    return _last(s.pct_change(w))


# --------------------------------------------------------------------------- #
# 1 · real-rate regime
# --------------------------------------------------------------------------- #
def real_rate_regime(real: pd.Series | None, breakeven: pd.Series | None,
                     cfg: dict) -> dict | None:
    """US 10y real yield level/direction + breakeven momentum -> a smile-arm regime.
    Restrictive, rising real yields are USD-supportive; a reflationary (rising
    breakeven) backdrop tends to soften the dollar. CONTEXT / coincident."""
    if real is None or real.empty:
        return None
    lb, w = cfg["z_lookback_d"], cfg["chg_window_d"]
    real = real.dropna()
    real_z = _last(fxs._zclip(real, lb))
    real_lvl = _last(real)
    real_chg = _last(real.diff(w))
    be_z = be_lvl = None
    if breakeven is not None and not breakeven.empty:
        be = breakeven.dropna()
        be_lvl = _last(be)
        be_z = _last(fxs._zclip(be.diff(w), lb))
    if real_z is None:
        return None
    hi, lo = cfg["high_z"], cfg["low_z"]
    rising = (real_chg or 0) > 0
    if real_z >= hi:
        regime, zh, lean = "Restrictive real yields", "实际利率偏紧", "supportive"
    elif real_z <= lo:
        regime, zh, lean = "Easy real yields", "实际利率宽松", "soft"
    elif be_z is not None and be_z >= cfg.get("be_high_z", 0.3):
        regime, zh, lean = "Reflation — rising breakevens", "再通胀 — 盈亏平衡上行", "soft"
    elif be_z is not None and be_z <= cfg.get("be_low_z", -0.3):
        regime, zh, lean = "Disinflation — falling breakevens", "去通胀 — 盈亏平衡下行", "neutral"
    else:
        regime, zh, lean = "Neutral real-rate backdrop", "实际利率中性", "neutral"
    # restrictive AND rising = the cleanest dollar tailwind
    if lean == "supportive" and not rising:
        lean = "neutral"
    return {"regime": regime, "regime_zh": zh, "lean": lean,
            "real_yield": round(real_lvl, 2) if real_lvl is not None else None,
            "real_z": round(real_z, 2),
            "real_rising": bool(rising),
            "breakeven": round(be_lvl, 2) if be_lvl is not None else None,
            "be_z": round(be_z, 2) if be_z is not None else None}


# --------------------------------------------------------------------------- #
# 2 · Fed policy path (US leg of the rate differential)
# --------------------------------------------------------------------------- #
def fed_path(zq: pd.DataFrame | None, cfg: dict) -> dict | None:
    """Implied Fed-funds path from ZQ futures: how many cuts/hikes are priced to 12m
    and whether the path is repricing hawkish/dovish. This is the US leg of the rate
    differential (no clean foreign OIS in the store) — priced expectations, coincident,
    not a forecast edge."""
    if zq is None or zq.empty:
        return None
    near, far = cfg.get("near", "m1"), cfg.get("far", "m12")
    if near not in zq.columns or far not in zq.columns:
        return None
    n = zq[near].dropna()
    f = zq[far].dropna()
    if n.empty or f.empty:
        return None
    near_r, far_r = float(n.iloc[-1]), float(f.iloc[-1])
    path_bps = round((far_r - near_r) * 100, 0)              # + = tightening priced to 12m, - = cuts
    w = cfg.get("reprice_window_d", 21)
    reprice = None
    if len(f) > w:
        reprice = round((float(f.iloc[-1]) - float(f.iloc[-1 - w])) * 100, 0)
    thr = cfg.get("reprice_bps", 10)
    if reprice is None:
        lean, lean_label, zh = "steady", "path steady", "路径稳定"
    elif reprice >= thr:
        lean, lean_label, zh = "hawkish_repricing", "repricing hawkish", "鹰派重定价"
    elif reprice <= -thr:
        lean, lean_label, zh = "dovish_repricing", "repricing dovish", "鸽派重定价"
    else:
        lean, lean_label, zh = "steady", "path steady", "路径稳定"
    return {"near_rate": round(near_r, 2), "far_rate": round(far_r, 2),
            "path_bps": path_bps, "reprice_bps": reprice,
            "lean": lean, "lean_label": lean_label, "lean_zh": zh}


# --------------------------------------------------------------------------- #
# 3 · USD positioning (CFTC COT net-spec on the dollar index)
# --------------------------------------------------------------------------- #
def positioning(cot_dollar: pd.Series | None, idx: pd.Index, cfg: dict) -> dict | None:
    """Speculative net positioning on the USD index as a rolling percentile + a
    crowding state. A crowding / fragility gauge — UNMEASURED for forward content,
    contrarian-only at the tails, and lagged (Tue-as-of, Fri-released)."""
    if cot_dollar is None or cot_dollar.empty:
        return None
    pcfg = {"pctile_lookback_d": cfg["pctile_lookback_d"],
            "crowded_long_pctile": cfg["crowded_long_pctile"],
            "crowded_short_pctile": cfg["crowded_short_pctile"]}
    pos = cs.positioning(cot_dollar, idx, pcfg)
    if pos.empty or "pos_pctile" not in pos:
        return None
    pct = _last(pos["pos_pctile"])
    if pct is None:
        return None
    state = pos["pos_state"].dropna()
    st = str(state.iloc[-1]) if len(state) else "neutral"
    net = _last(pos["pos_net_pct_oi"]) if "pos_net_pct_oi" in pos else None
    return {"pctile": round(pct, 0), "state": st,
            "net_pct_oi": round(net, 1) if net is not None else None}


# --------------------------------------------------------------------------- #
# 4 · valuation (US REER vs long-run mean)
# --------------------------------------------------------------------------- #
def valuation(reer_us: pd.Series | None, cfg: dict, idx: pd.Index) -> dict | None:
    """US BIS real-effective rate vs its ~5y log mean. + gap = the dollar is rich
    (a multi-year mean-reversion anchor, never a tactical entry)."""
    if reer_us is None or reer_us.empty:
        return None
    va = fxs.value_signal(reer_us, cfg, idx)
    if va.empty or "reer_gap" not in va:
        return None
    gap = va["reer_gap"].dropna()
    if gap.empty:
        return None
    gap_last = float(gap.iloc[-1])
    z = _last(fxs._zraw(va["reer_gap"], cfg["z_lookback_d"]))
    stretched = bool(z is not None and abs(z) >= cfg.get("stretch_z", 1.5))
    rg = cfg.get("rich_gap", 0.01)
    label = "rich" if gap_last > rg else ("cheap" if gap_last < -rg else "fair")
    return {"gap_pct": round(100 * gap_last, 1),
            "z": round(z, 2) if z is not None else None,
            "stretched": stretched, "label": label}


# --------------------------------------------------------------------------- #
# 5 · broad-USD trend stack (breadth / coherence read)
# --------------------------------------------------------------------------- #
def trend_stack(broad: pd.Series | None, cfg: dict) -> dict | None:
    """Broad-USD trend across multiple horizons. A breadth read — how many horizons
    point the same way — NOT a forward signal (broad-dollar trend calibrates
    INVERTED on most pairs; mean-reversion dominates)."""
    if broad is None or broad.empty:
        return None
    broad = broad.dropna()
    horizons = cfg.get("horizons_d", [21, 63, 126, 252])
    rows, n_up = [], 0
    for h in horizons:
        roc = _roc(broad, h)
        if roc is None:
            continue
        up = roc > 0
        n_up += int(up)
        rows.append({"d": h, "roc_pct": round(100 * roc, 1), "up": bool(up)})
    if not rows:
        return None
    n_tot = len(rows)
    up_frac = cfg.get("up_frac", 0.75)
    label = "up" if n_up >= max(1, int(np.ceil(up_frac * n_tot))) else \
            ("down" if n_up <= int(np.floor((1 - up_frac) * n_tot)) else "mixed")
    zh = {"up": "走强", "down": "走软", "mixed": "分化"}[label]
    return {"n_up": n_up, "n_tot": n_tot, "label": label, "label_zh": zh,
            "horizons": rows}


# --------------------------------------------------------------------------- #
# 6 · USD liquidity (net Fed liquidity rate-of-change)
# --------------------------------------------------------------------------- #
def liquidity(fed_bs: pd.Series | None, on_rrp: pd.Series | None,
              idx: pd.Index, cfg: dict, tga: pd.Series | None = None) -> dict | None:
    """USD-framed net-Fed-liquidity rate-of-change (audit #12/#28/#40).

    Net liquidity is the CANONICAL 3-term ``WALCL − RRP − TGA`` (billions) — this desk
    previously DROPPED TGA (a bug: TGA is a large, volatile drain) and re-derived netliq
    inline, diverging from the regime overlay's series. Now it calls ``engine.canon``:
      * ``canon.net_liquidity_bn`` for the ONE 3-term series (WALCL/1000 and TGA/1000 to
        billions; RRP already billions);
      * ``canon.dollar_liquidity_roc`` for the intentional DOLLAR sign framing — falling
        net liquidity drains dollars and is USD-SUPPORTIVE, so this desk reads the
        NEGATED change (supportive ⇒ positive roc). That sign flip is a framing of the
        SAME liquidity series, not a different one (the #12 "divergent formula" fix).
    Slow, regime-conditional, context only (the level↔dollar link is largely spurious)."""
    from engine import canon
    if fed_bs is None or fed_bs.empty:
        return None
    bs_bn = (fed_bs.reindex(idx).ffill() / 1000.0)            # millions -> billions
    rrp_bn = on_rrp.reindex(idx).ffill() if on_rrp is not None else None
    tga_bn = (tga.reindex(idx).ffill() / 1000.0) if tga is not None else None  # millions->bn
    net = canon.net_liquidity_bn(bs_bn, rrp_bn, tga_bn).dropna()
    if net.empty:
        return None
    w = cfg.get("chg_window_d", 63)
    # DOLLAR framing: supportive when liquidity is FALLING → roc = −Δnet (canon transform).
    roc = canon.dollar_liquidity_roc(net, w)
    chg = _last(roc)
    z = _last(fxs._zraw(roc, cfg.get("z_lookback_d", 252)))
    if chg is None:
        return None
    # chg > 0 now means liquidity draining (USD supportive); keep the desk's word contract.
    direction = "supportive" if chg > 0 else ("soft" if chg < 0 else "neutral")
    return {"net_chg_bn": round(chg, 0), "z": round(z, 2) if z is not None else None,
            "dir": direction, "window_d": w, "tga_included": tga is not None}


# --------------------------------------------------------------------------- #
# IRD-R10 · DXY smile decomposition (display-only — no vote added)
# --------------------------------------------------------------------------- #
# DXY weights (ICE benchmark, rounded): EUR 57.6%, JPY 13.6%, GBP 11.9%,
# CAD 9.1%, SEK 4.2%, CHF 3.6%.  We have 2y rates for EUR/JPY/GBP only.
# Re-weight within the three available: EUR 69.3%, JPY 16.4%, GBP 14.3%
# (proportional to their DXY weights; documented here for IRD-R10 surface).
_SMILE_WEIGHTS_2Y = {
    "eur": 0.693,   # ez_aaa_2y from sovereign store
    "jpy": 0.164,   # jgb_2y from sovereign store
    "gbp": 0.143,   # IR3TIB01GBM156N (monthly) from fred store — forward-filled
}
_SMILE_OLS_WINDOW = 120   # 120 calendar-day rolling OLS (trading days ≈ 84d)
_SMILE_RESID_WINDOW = 20  # cumulative residual lookback
_SMILE_Z_WINDOW_DAYS = 252  # 1y for z-score of residual


def _load_series_for_smile(store_obj) -> dict[str, pd.Series | None]:
    """Load DXY, US 2y, and foreign 2y rates for smile decomposition."""
    from lib import store as _store

    def _read_col(grp: str, name: str) -> pd.Series | None:
        df = _store.read(grp, name)
        if df is None or df.empty:
            return None
        s = df.iloc[:, 0].astype(float).dropna()
        return s if not s.empty else None

    return {
        "dxy": _read_col("yahoo", "DX-Y.NYB"),
        "us2y": _read_col("fred", "DGS2"),
        "eur2y": _read_col("sovereign", "ez_aaa_2y"),
        "jpy2y": _read_col("sovereign", "jgb_2y"),
        "gbp2y": _read_col("fred", "IR3TIB01GBM156N"),   # monthly; forward-filled
    }


def smile_decomp() -> dict | None:
    """IRD-R10 DXY smile decomposition (display-only, never scored).

    Computes:
      - 120d rolling OLS of daily DXY log-returns on daily change of the
        US-minus-basket 2y rate differential (USD − weighted EUR/JPY/GBP 2y).
      - beta    : regression slope (current 120d window)
      - r2      : OLS R² (current window)
      - residual_20d : cumulative 20d OLS residual = safety/risk-premium read
      - safety_bid_today : bool — DXY up 5d AND DGS2 down 5d
      - regime  : 'rates-driven' | 'safety-driven' | 'mixed'
                  |z| < 1 → rates-driven; z ≥ 1 → safety-driven; z ≤ -1 → mixed
      - regime_60d : same regime computed on a 60d residual z window for sensitivity
      - weights_used : dict documenting the 2y basket composition
      - gaps    : list of data notes

    Fail-open: returns None if DXY or US 2y are absent.
    """
    import math
    from datetime import datetime, timezone

    gaps: list[str] = []
    series = _load_series_for_smile(None)

    dxy = series.get("dxy")
    us2y = series.get("us2y")
    if dxy is None or dxy.empty:
        gaps.append("smile_decomp: DXY (DX-Y.NYB) absent")
        return {"gaps": gaps, "regime": None, "display_only": True}
    if us2y is None or us2y.empty:
        gaps.append("smile_decomp: DGS2 absent")
        return {"gaps": gaps, "regime": None, "display_only": True}

    # Build basket 2y (weighted EUR/JPY/GBP)
    # Stored as (key, series, weight) tuples so label tracks the survivor when
    # a series is absent and the list is shorter than _SMILE_WEIGHTS_2Y.
    basket_parts: list[tuple[str, pd.Series, float]] = []
    for key, weight in _SMILE_WEIGHTS_2Y.items():
        s = series.get(f"{key[:3]}2y")
        if s is not None and not s.empty:
            basket_parts.append((key, s, weight))
        else:
            gaps.append(f"smile_decomp: {key}_2y absent — re-weighted to available")

    if not basket_parts:
        gaps.append("smile_decomp: no foreign 2y series available — differential leg null")
        return {"gaps": gaps, "regime": None, "display_only": True}

    # Re-normalize weights to available series (key label travels with the tuple)
    total_w = sum(w for _, _s, w in basket_parts)
    basket_parts = [(k, s, w / total_w) for k, s, w in basket_parts]

    # Build common daily index (union of all series)
    all_idx = dxy.index
    for _, s, _ in basket_parts:
        all_idx = all_idx.union(s.index)
    all_idx = all_idx.union(us2y.index)
    all_idx = all_idx.sort_values()

    # Forward-fill monthly series up to 40 days (monthly cadence)
    dxy_a = dxy.reindex(all_idx).ffill(limit=5)
    us2y_a = us2y.reindex(all_idx).ffill(limit=5)
    basket_2y = sum(s.reindex(all_idx).ffill(limit=40) * w for _, s, w in basket_parts)

    # Daily changes
    dxy_ret = np.log(dxy_a / dxy_a.shift(1))       # DXY log return
    diff_chg = (us2y_a - basket_2y).diff(1)         # Δ(US 2y − basket 2y)

    # Align to intersection with both non-null
    common = dxy_ret.dropna().index.intersection(diff_chg.dropna().index)
    if len(common) < _SMILE_OLS_WINDOW + _SMILE_RESID_WINDOW + 10:
        gaps.append(f"smile_decomp: insufficient common history ({len(common)} rows)")
        return {"gaps": gaps, "regime": None, "display_only": True}

    dxy_ret = dxy_ret.reindex(common)
    diff_chg = diff_chg.reindex(common)

    # Rolling 120d OLS: dxy_ret = beta * diff_chg + alpha + resid
    n = len(common)
    W = _SMILE_OLS_WINDOW
    beta_ser = pd.Series(index=common, dtype=float)
    r2_ser = pd.Series(index=common, dtype=float)
    resid_ser = pd.Series(index=common, dtype=float)

    for end in range(W, n + 1):
        y = dxy_ret.iloc[end - W: end].values
        x = diff_chg.iloc[end - W: end].values
        mask = np.isfinite(y) & np.isfinite(x)
        if mask.sum() < W // 2:
            continue
        y_, x_ = y[mask], x[mask]
        x_m = x_ - x_.mean()
        y_m = y_ - y_.mean()
        denom = np.dot(x_m, x_m)
        if denom < 1e-12:
            continue
        b = np.dot(x_m, y_m) / denom
        a = y_.mean() - b * x_.mean()
        y_hat = a + b * x_
        ss_res = np.dot(y_ - y_hat, y_ - y_hat)
        ss_tot = np.dot(y_m, y_m)
        r2 = float(1.0 - ss_res / ss_tot) if ss_tot > 1e-12 else 0.0
        beta_ser.iloc[end - 1] = b
        r2_ser.iloc[end - 1] = r2
        # Today's residual: y[-1] - (a + b * x[-1])
        resid_today = float(dxy_ret.iloc[end - 1]) - (a + b * float(diff_chg.iloc[end - 1]))
        resid_ser.iloc[end - 1] = resid_today if math.isfinite(resid_today) else float("nan")

    beta_ser = beta_ser.dropna()
    r2_ser = r2_ser.dropna()
    resid_ser = resid_ser.dropna()

    if resid_ser.empty:
        gaps.append("smile_decomp: OLS produced no valid windows")
        return {"gaps": gaps, "regime": None, "display_only": True}

    # cumulative 20d residual (the safety/risk premium read)
    resid_20d_cum = resid_ser.rolling(_SMILE_RESID_WINDOW, min_periods=10).sum()
    resid_20d = float(resid_20d_cum.iloc[-1]) if not resid_20d_cum.dropna().empty else None

    # z-score of 20d cumulative residual vs trailing 1y (252 obs) distribution
    def _resid_z(window: int) -> float | None:
        r = resid_20d_cum.dropna()
        if len(r) < window // 4:
            return None
        w = r.iloc[-window:]
        sd = float(w.std())
        if sd < 1e-12 or not math.isfinite(sd):
            return None
        z = float(r.iloc[-1]) / sd
        return round(z, 3) if math.isfinite(z) else None

    resid_z = _resid_z(_SMILE_Z_WINDOW_DAYS)
    resid_z_60d = _resid_z(60)

    def _regime_from_z(z: float | None) -> str:
        if z is None:
            return "unknown"
        if z >= 1.0:
            return "safety-driven"
        if z <= -1.0:
            return "mixed"    # negative residual = risk-appetite, dollar soft on rates alone
        return "rates-driven"

    # 5d safety-bid flag: DXY up AND DGS2 down
    safety_bid_today: bool | None = None
    if len(dxy_a.dropna()) >= 6 and len(us2y_a.dropna()) >= 6:
        dxy_5d = float(dxy_a.dropna().iloc[-1]) - float(dxy_a.dropna().iloc[-6])
        dgs2_5d = float(us2y_a.dropna().iloc[-1]) - float(us2y_a.dropna().iloc[-6])
        safety_bid_today = bool(dxy_5d > 0 and dgs2_5d < 0)

    beta_last = float(beta_ser.iloc[-1]) if not beta_ser.empty else None
    r2_last = float(r2_ser.iloc[-1]) if not r2_ser.empty else None

    # Actual weights after re-normalization (for surface disclosure).
    # Key labels come from the basket_parts tuples — correct even when a series
    # is absent and basket_parts is shorter than _SMILE_WEIGHTS_2Y.
    weights_used = {
        f"{k[:3]}2y": round(w, 3)
        for k, _s, w in basket_parts
    }

    return {
        "beta": round(beta_last, 4) if beta_last is not None and math.isfinite(beta_last) else None,
        "r2": round(r2_last, 3) if r2_last is not None and math.isfinite(r2_last) else None,
        "residual_20d": round(resid_20d, 5) if resid_20d is not None and math.isfinite(resid_20d) else None,
        "residual_20d_z": resid_z,
        "regime": _regime_from_z(resid_z),
        "regime_60d": _regime_from_z(resid_z_60d),
        "safety_bid_today": safety_bid_today,
        "ols_window_days": _SMILE_OLS_WINDOW,
        "z_window_days": _SMILE_Z_WINDOW_DAYS,
        "regime_thresholds": {
            "rates_driven": "|z| < 1",
            "safety_driven": "z >= 1 (positive residual — DXY up more than rates explain)",
            "mixed": "z <= -1 (negative residual — risk-appetite, DXY soft vs rates)",
        },
        "weights_used": weights_used,
        "weights_note": (
            "DXY basket weights: EUR 57.6%, JPY 13.6%, GBP 11.9% "
            "(ICE benchmark). Re-weighted to available 2y series: "
            f"EUR {_SMILE_WEIGHTS_2Y['eur']:.1%}, JPY {_SMILE_WEIGHTS_2Y['jpy']:.1%}, "
            f"GBP {_SMILE_WEIGHTS_2Y['gbp']:.1%}. "
            "CAD/SEK/CHF excluded (no 2y in store). "
            f"Actual weights after re-norm: {weights_used}."
        ),
        "gaps": gaps,
        "display_only": True,
        "built": datetime.now(timezone.utc).isoformat(),
    }


# --------------------------------------------------------------------------- #
# 7 · smile confirmation + triple-red haven-loss flag
# --------------------------------------------------------------------------- #
# smile regime -> the implied USD direction (strong/weak)
_SMILE_USD = {"US growth premium": "strong", "Risk-off haven bid": "strong",
              "Global reflation": "weak", "US-specific stress": "weak", "Neutral": None}


def smile_confirm(dol: pd.DataFrame, real: dict | None, trend: dict | None,
                  liq: dict | None, drivers: dict, cfg: dict) -> dict:
    """How many independent legs corroborate the current smile regime's USD direction
    + a triple-red haven-loss flag (USD & equities & Treasuries falling together = the
    dollar is NOT acting as a safe haven). Descriptive only."""
    last = dol.iloc[-1]
    regime = last.get("smile_regime", "Neutral")
    usd_dir = _SMILE_USD.get(regime)
    confirms, against = [], []

    def _vote(name_en, name_zh, leg_dir):
        if usd_dir is None or leg_dir is None:
            return
        (confirms if leg_dir == usd_dir else against).append((name_en, name_zh))

    if real:
        _vote("real yields", "实际利率",
              "strong" if real["lean"] == "supportive" else ("weak" if real["lean"] == "soft" else None))
    if trend:
        _vote("trend stack", "趋势栈",
              "strong" if trend["label"] == "up" else ("weak" if trend["label"] == "down" else None))
    if liq:
        _vote("liquidity", "流动性",
              "strong" if liq["dir"] == "supportive" else ("weak" if liq["dir"] == "soft" else None))

    n = len(confirms)
    conf = "high" if n >= 3 else ("medium" if n == 2 else ("low" if n == 1 else "none"))
    conf_zh = {"high": "高", "medium": "中", "low": "低", "none": "无"}[conf]

    # triple-red: USD down + SPY down + UST price down (10y yield UP) over the window
    w = cfg.get("triple_red_window_d", 21)
    broad = drivers.get("broad_dollar")
    spy = drivers.get("spy")
    us10y = drivers.get("us10y")
    triple_red = False
    if broad is not None and spy is not None and us10y is not None:
        ud = _roc(broad.dropna(), w)
        sd = _roc(spy.dropna(), w)
        yd = _last(us10y.dropna().diff(w))                    # yield change; + = price down
        if ud is not None and sd is not None and yd is not None:
            triple_red = (ud < 0) and (sd < 0) and (yd > 0)
    return {"regime": regime, "usd_dir": usd_dir, "confidence": conf,
            "confidence_zh": conf_zh, "n_confirm": n,
            "confirms": [c[0] for c in confirms], "confirms_zh": [c[1] for c in confirms],
            "against": [a[0] for a in against],
            "triple_red": bool(triple_red)}


# --------------------------------------------------------------------------- #
# assemble the desk
# --------------------------------------------------------------------------- #
def dollar_desk(dol: pd.DataFrame, drivers: dict, extra: dict, cfg: dict) -> dict:
    """Full Dollar Desk read. Each leg degrades to None on missing data; the desk
    never raises. `dol` = the _dollar master frame; `drivers` = the shared driver
    series; `extra` = {cot_dollar: Series, zq_path: DataFrame}. `cfg` = forex config."""
    try:
        dcfg = cfg["dollar_desk"]
        idx = dol.index
        rr = real_rate_regime(drivers.get("us10y_real"), drivers.get("breakeven_10y"),
                              dcfg["real_rate"])
        fp = fed_path(extra.get("zq_path"), dcfg["fed_path"])
        po = positioning(extra.get("cot_dollar"), idx, dcfg["positioning"])
        va = valuation(drivers.get("reer_us"), dcfg["valuation"], idx)
        tr = trend_stack(drivers.get("broad_dollar"), dcfg["trend"])
        lq = liquidity(drivers.get("fed_bs"), drivers.get("on_rrp"), idx, dcfg["liquidity"],
                       tga=drivers.get("tga"))   # audit #28: TGA drain no longer dropped
        sm = smile_confirm(dol, rr, tr, lq, drivers, dcfg["smile"])

        # balance of context flags -> a descriptive LEAN word (explicitly NOT a score)
        votes = []
        if rr and rr["lean"] in ("supportive", "soft"):
            votes.append(1 if rr["lean"] == "supportive" else -1)
        if tr and tr["label"] in ("up", "down"):
            votes.append(1 if tr["label"] == "up" else -1)
        if lq and lq["dir"] in ("supportive", "soft"):
            votes.append(1 if lq["dir"] == "supportive" else -1)
        if fp and fp["lean"] in ("hawkish_repricing", "dovish_repricing"):
            votes.append(1 if fp["lean"] == "hawkish_repricing" else -1)
        net = sum(votes)
        if not votes:
            lean, lean_zh = "mixed", "分化"
        elif net >= 2:
            lean, lean_zh = "dollar-supportive backdrop", "偏多美元背景"
        elif net <= -2:
            lean, lean_zh = "dollar-soft backdrop", "偏空美元背景"
        else:
            lean, lean_zh = "mixed backdrop", "分化背景"

        # IRD-R10: smile_decomp is DISPLAY-ONLY; no vote added to the lean accumulator
        try:
            sd = smile_decomp()
        except Exception as _sd_exc:  # noqa: BLE001
            log.warning("smile_decomp failed (%s)", _sd_exc)
            sd = None

        return {"real_rate": rr, "fed_path": fp, "positioning": po, "valuation": va,
                "trend": tr, "liquidity": lq, "smile": sm,
                "smile_decomp": sd,   # IRD-R10 display-only leg
                "lean": lean, "lean_zh": lean_zh,
                "lean_net": net, "lean_n": len(votes)}
    except Exception as e:  # noqa: BLE001 — desk must never break the build
        log.warning("dollar_desk failed (%s)", e)
        return {}


# --------------------------------------------------------------------------- #
# currency strength meter
# --------------------------------------------------------------------------- #
# currency code -> (zh, is_em/managed flag) for display
_CCY = {"USD": ("美元", False), "EUR": ("欧元", False), "JPY": ("日元", False),
        "GBP": ("英镑", False), "AUD": ("澳元", False), "CAD": ("加元", False),
        "CHF": ("瑞郎", False), "CNH": ("离岸人民币", True), "MXN": ("墨西哥比索", True),
        "BRL": ("巴西雷亚尔", True)}


def strength_meter(results: dict, cfg: dict, assets_cfg: dict) -> dict:
    """Cross-currency strength, independent of any single pair. For each currency we
    average its bilateral appreciation against every other currency (USD crosses make
    the USD leg cancel cleanly), then standardize cross-sectionally per horizon. The
    USD leg is anchored to the same basket so the meter and the desk never contradict.

    DESCRIPTIVE trailing trend — green never means buy. Returns {horizons: {hk: rows},
    default, order}. Each row: {ccy, ccy_zh, strength (z for the bar), vs_usd_pct, em}."""
    try:
        horizons = cfg.get("horizons_d", {"1w": 5, "1m": 21, "3m": 63})
        # base currency -> its base-vs-USD close series (rising = base stronger vs USD)
        base_close: dict[str, pd.Series] = {}
        for pair, df in results.items():
            if pair == "_dollar" or df is None or df.empty or "close" not in df:
                continue
            meta = assets_cfg.get(pair, {})
            base = meta.get("base")
            if not base:
                continue
            base_close[base] = df["close"].dropna()
        if not base_close:
            return {}
        out_h: dict[str, list] = {}
        for hk, w in horizons.items():
            rets = {}                                         # ccy -> log return over w
            for ccy, s in base_close.items():
                if len(s) <= w:
                    continue
                r = float(np.log(s.iloc[-1] / s.iloc[-1 - w]))
                if np.isfinite(r):
                    rets[ccy] = r
            if not rets:
                continue
            rets["USD"] = 0.0                                 # numeraire leg
            grand = float(np.mean(list(rets.values())))
            strength = {c: r - grand for c, r in rets.items()}   # excess over avg ccy (zero-sum)
            sd = float(np.std(list(strength.values()))) or 1.0
            rows = []
            for c, v in strength.items():
                zh, em = _CCY.get(c, (c, False))
                vs_usd = 0.0 if c == "USD" else 100 * rets.get(c, 0.0)
                rows.append({"ccy": c, "ccy_zh": zh, "em": em,
                             "strength": round(float(np.clip(v / sd, -2.5, 2.5)) / 2.5, 3),
                             "vs_usd_pct": round(vs_usd, 1)})
            rows.sort(key=lambda r: -r["strength"])
            out_h[hk] = rows
        if not out_h:
            return {}
        default = cfg.get("default_horizon", "1m")
        if default not in out_h:
            default = next(iter(out_h))
        return {"horizons": out_h, "default": default, "order": list(horizons.keys())}
    except Exception as e:  # noqa: BLE001
        log.warning("strength_meter failed (%s)", e)
        return {}
