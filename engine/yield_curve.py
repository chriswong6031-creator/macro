"""Yield-curve analytics — the unified, theory-grounded interest-rate engine.

A LEAF module (imports nothing from the scoring core; nothing in the scoring path
imports it). It reads the shared causal feature frame (engine.inputs.build_features)
and assembles the full yield-curve read the dashboard was missing: the SHAPE
decomposition (level / slope / curvature, with the Litterman-Scheinkman PCA variance
the three factors span), every canonical SLOPE + its momentum, the bull/bear ×
steepener/flattener REGIME with its Fed-cycle phase and asset implications, the
RECESSION dashboard (near-term forward spread + the NY-Fed 10y-3m probit + the
un-inversion alarm + the term-premium-adjusted slope), the FORWARD-rate grid with
carry & roll-down, and the REAL curve / breakeven curve.

It then distils four typed SIGNAL families for the rest of the dashboard — core-macro
(curve regime + recession phase), sector tilts, equity style/factor tilts, and a
market-tendency (curve-speed → drawdown-risk) read — each carried with a basis tag so
a reader sees whether a tilt is MEASURED (from the calibrated transmission IC matrix)
or THEORY (textbook channel, no edge claim).

DISCIPLINE — display / LLM-context ONLY, never scored. The house calibrator's scored-
leg gate (the same forward-drawdown bar the bond-health legs pass) found NO rate
leg robust enough to move an allocation: repricing is reactive, rate-of-change beats
level, and the strongest reads are regime-dependent. So this layer ENLARGES the facts
a read can cite and the context the brain reasons over; it does not score anything.
Any candidate that DID earn a scored tier is gated in config (default off) and adopted
only after the calibration refresh confirms — the same restraint as bonds. It REUSES
the bond-engine curve primitives (engine.bonds: the probit, the near-term forward
spread, the move taxonomy, the un-inversion alarm) rather than re-deriving them, so the
two pages can never drift. Graceful: a missing input drops the relevant read to None.
Bilingual throughout. Additive, never fatal.

See research/YIELD_CURVE_ENGINE.md.
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from engine.bonds import (curve_move_taxonomy, ny_fed_recession_prob,
                          near_term_forward_spread, uninversion, _TAXONOMY)
from lib import config

log = logging.getLogger(__name__)

# Curve nodes available in the feature frame (FRED CMT), in maturity-years order.
NODES = [("us3m", 0.25), ("us6m", 0.5), ("us1y", 1.0), ("us2y", 2.0), ("us3y", 3.0),
         ("us5y", 5.0), ("us7y", 7.0), ("us10y", 10.0), ("us30y", 30.0)]
PCTILE_LOOKBACK = 1260          # ~5y window for level percentiles
MOM_WINDOW = 63                 # ~1 quarter for the curve-speed reads
PCA_WINDOW = 1260               # ~5y of daily changes for the L-S decomposition


def _cfg() -> dict:
    return config.load().get("yield_curve", {}) or {}


# --------------------------------------------------------------------------- #
# small helpers (mirror engine.bonds so the leaf is self-contained)
# --------------------------------------------------------------------------- #
def _col(f: pd.DataFrame, name: str) -> pd.Series | None:
    if name not in f.columns or f[name].isna().all():
        return None
    return f[name]


def _last(s: pd.Series | None) -> float | None:
    if s is None:
        return None
    s = s.dropna()
    return float(s.iloc[-1]) if len(s) else None


def _pctile(s: pd.Series | None, lookback: int = PCTILE_LOOKBACK) -> float | None:
    if s is None:
        return None
    s = s.dropna()
    if len(s) < 60:
        return None
    win = s.iloc[-lookback:]
    return round(float((win <= win.iloc[-1]).mean()), 2)


def _bil(en: str, zh: str) -> dict:
    return {"en": en, "zh": zh}


def _chg(s: pd.Series | None, n: int = MOM_WINDOW) -> float | None:
    if s is None:
        return None
    s = s.dropna()
    if len(s) <= n:
        return None
    return float(s.iloc[-1] - s.iloc[-1 - n])


# --------------------------------------------------------------------------- #
# 1) SHAPE — level / slope / curvature + the Litterman-Scheinkman PCA variance
# --------------------------------------------------------------------------- #
def _curve_matrix(f: pd.DataFrame) -> tuple[pd.DataFrame, list[float]]:
    """The (T × tenors) yield matrix over the tenors present, + their maturities."""
    cols, mats = [], []
    for col, mat in NODES:
        if col in f.columns and not f[col].isna().all():
            cols.append(col)
            mats.append(mat)
    if len(cols) < 4:
        return pd.DataFrame(), []
    return f[cols].dropna(how="all"), mats


def _fit_pca_eigh(dy_arr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Fit PCA via cov/eigh on a (T × p) diff array. Returns (eigenvalues, eigenvectors)
    sorted descending by eigenvalue — the same approach as the main PCA path so the health
    sub-block stays byte-compatible with it. Raises on degenerate input (caller catches)."""
    cov = np.cov(dy_arr.T)
    vals, vecs = np.linalg.eigh(cov)
    order = np.argsort(vals)[::-1]
    return vals[order], vecs[:, order]


def _pca_health(dy: pd.DataFrame, vals_full: np.ndarray, vecs_full: np.ndarray) -> dict:
    """Compute the pca_health sub-block. Called after the main PCA succeeds so vals_full
    and vecs_full are already available. All sub-fields are wrapped in individual
    try/except — if anything fails the field is None, never raised.

    Fields:
        eigenvalue_gaps       — {"pc1_to_pc2", "pc2_to_pc3", "pc3_to_pc4"}
        effective_dimension_pr — participation-ratio effective dimension
        pc1_loading_turnover_vs_2y — 1 - |cos(pc1_full, pc1_504)|, 6dp; None if <525 rows
        oos_null              — null-calibrated OOS orthogonality health (RUL-ORTH-8)
        vol_match_multipliers — {"pc2": sqrt(l1/l2), "pc3": sqrt(l1/l3)}, 2dp
        curvature_stability_tag — from pc3_to_pc4 gap
        window_set            — metadata
    """
    n_rows = len(dy)
    n_full = len(vals_full)

    out: dict = {}

    # ---- eigenvalue_gaps -------------------------------------------------- #
    gaps: dict[str, float | None] = {}
    # denominator floor: a numerically-zero eigenvalue (rank-deficient curve) must
    # yield gap=None, not a spuriously huge "well-separated" ratio
    _gap_floor = 1e-9 * float(max(np.clip(vals_full, 0.0, None).sum(), 0.0)) if n_full else 0.0
    for k, i, j in (("pc1_to_pc2", 0, 1), ("pc2_to_pc3", 1, 2), ("pc3_to_pc4", 2, 3)):
        try:
            if j < n_full and _gap_floor > 0 and vals_full[j] > _gap_floor:
                gaps[k] = round(float(vals_full[i] / vals_full[j]), 4)
            else:
                gaps[k] = None
        except Exception:  # noqa: BLE001
            gaps[k] = None
    out["eigenvalue_gaps"] = gaps

    # ---- effective_dimension_pr ------------------------------------------- #
    try:
        vals_pos = np.clip(vals_full, 0.0, None)  # eigh noise can dip negative; PR must stay >= 1
        s = float(vals_pos.sum())
        s2 = float((vals_pos ** 2).sum())
        out["effective_dimension_pr"] = round(s ** 2 / s2, 4) if s2 > 0 else None
    except Exception:  # noqa: BLE001
        out["effective_dimension_pr"] = None

    # ---- pc1_loading_turnover_vs_2y --------------------------------------- #
    try:
        if n_rows >= 525:
            dy_504 = dy.iloc[-504:].to_numpy(float)
            _, vecs_504 = _fit_pca_eigh(dy_504)
            pc1_full = vecs_full[:, 0]
            pc1_504 = vecs_504[:, 0]
            cos_sim = float(np.dot(pc1_full, pc1_504) /
                            (np.linalg.norm(pc1_full) * np.linalg.norm(pc1_504)))
            out["pc1_loading_turnover_vs_2y"] = round(1.0 - abs(cos_sim), 6)
        else:
            out["pc1_loading_turnover_vs_2y"] = None
    except Exception:  # noqa: BLE001
        out["pc1_loading_turnover_vs_2y"] = None

    # ---- oos_null --------------------------------------------------------- #
    try:
        dy_arr = dy.to_numpy(float)
        train_arr = dy_arr[:-21]
        test_arr = dy_arr[-21:]
        if len(train_arr) < 252:
            out["oos_null"] = None
        else:
            # fit on train; project test onto frozen first-3 PCs
            _, vecs_train = _fit_pca_eigh(train_arr)
            pc3_train = vecs_train[:, :3]  # (p, 3)

            def _max_off_diag_corr(rows: np.ndarray, pc_mat: np.ndarray) -> float | None:
                proj = rows @ pc_mat  # (T, 3)
                stds = proj.std(axis=0)
                if np.any(stds < 1e-12):
                    return None
                corr = np.corrcoef(proj.T)  # (3, 3)
                mask = ~np.eye(3, dtype=bool)
                return float(np.abs(corr[mask]).max())

            observed = _max_off_diag_corr(test_arr, pc3_train)

            # deterministic null: contiguous 21-row slices in train, stride 2,
            # cap 240 attempts — RUL-ORTH-8 binds every published orthogonality
            # metric to a >=200-draw within-window null. Note: the null is
            # in-window on the same frozen train PCs, so it is biased LOW vs a
            # true out-of-sample reference — pctile_vs_null reads conservative
            # (toward over-flagging); do not over-interpret high percentiles.
            n_train = len(train_arr)
            all_starts = list(range(0, n_train - 21 + 1, 2))
            if len(all_starts) > 240:
                # evenly space exactly 240 out of all_starts (deterministic)
                step = (len(all_starts) - 1) / 239.0
                indices = [int(round(step * k)) for k in range(240)]
                all_starts = [all_starts[i] for i in indices]

            null_draws: list[float] = []
            for st in all_starts:
                try:
                    chunk = train_arr[st:st + 21]
                    v = _max_off_diag_corr(chunk, pc3_train)
                    if v is not None:
                        null_draws.append(v)
                except Exception:  # noqa: BLE001
                    continue

            if len(null_draws) < 200 or observed is None:
                out["oos_null"] = None
            else:
                null_arr = np.asarray(null_draws, float)
                pctile = float(np.mean(null_arr <= observed))
                out["oos_null"] = {
                    "observed": round(float(observed), 4),
                    "null_median": round(float(np.median(null_arr)), 4),
                    "null_p90": round(float(np.percentile(null_arr, 90)), 4),
                    "pctile_vs_null": round(pctile, 4),
                    "n_null_draws": int(len(null_draws)),
                }
    except Exception:  # noqa: BLE001
        out["oos_null"] = None

    # ---- vol_match_multipliers ------------------------------------------- #
    try:
        l1 = float(vals_full[0]) if n_full > 0 else None
        mults: dict[str, float | None] = {}
        for k, j in (("pc2", 1), ("pc3", 2)):
            try:
                lj = float(vals_full[j]) if j < n_full else None
                if l1 is not None and lj is not None and lj > 0:
                    mults[k] = round(float(np.sqrt(l1 / lj)), 2)
                else:
                    mults[k] = None
            except Exception:  # noqa: BLE001
                mults[k] = None
        out["vol_match_multipliers"] = mults
    except Exception:  # noqa: BLE001
        out["vol_match_multipliers"] = {"pc2": None, "pc3": None}

    # ---- curvature_stability_tag ----------------------------------------- #
    try:
        gap34 = gaps.get("pc3_to_pc4")
        if gap34 is None:
            out["curvature_stability_tag"] = None
        elif gap34 >= 2.5:
            out["curvature_stability_tag"] = "stable"
        elif gap34 >= 1.5:
            out["curvature_stability_tag"] = "caution"
        else:
            out["curvature_stability_tag"] = "unstable"
    except Exception:  # noqa: BLE001
        out["curvature_stability_tag"] = None

    # ---- window_set ------------------------------------------------------- #
    out["window_set"] = {
        "full_window_d": int(n_rows),
        "compare_window_d": 504,
        "oos_horizon_d": 21,
    }

    return out


def pca_decomposition(f: pd.DataFrame) -> dict | None:
    """Litterman-Scheinkman: PCA of daily yield CHANGES across the curve. The first
    three components are — empirically and here — level, slope and curvature, and they
    span ~99% of the curve's variance. We report the variance each spans (the canonical
    result) and orient the loadings so the read is interpretable (PC1 = parallel level,
    PC2 = slope with + = steeper, PC3 = curvature with + = more humped)."""
    mat, mats = _curve_matrix(f)
    if mat.empty or len(mat) < 252:
        return None
    dy = mat.diff().dropna().iloc[-PCA_WINDOW:]
    if len(dy) < 252 or dy.shape[1] < 4:
        return None
    try:
        cov = np.cov(dy.to_numpy(float).T)
        vals, vecs = np.linalg.eigh(cov)
        order = np.argsort(vals)[::-1]
        vals, vecs = vals[order], vecs[:, order]
        var = vals / vals.sum()
        mats_arr = np.asarray(mats, float)
        out_factors = []
        names = [("level", "Level", "水平"), ("slope", "Slope", "斜率"),
                 ("curvature", "Curvature", "曲率")]
        for i, (key, en, zh) in enumerate(names):
            if i >= vecs.shape[1]:
                break
            v = vecs[:, i].copy()
            # orient: PC1 mostly-positive => level up; PC2 long-minus-short => + steeper;
            # PC3 belly-vs-wings => + more humped. Use the loading geometry to fix sign.
            if key == "level" and v.sum() < 0:
                v = -v
            elif key == "slope":
                # correlation of loading with maturity: + => long end loads up => steeper
                if np.corrcoef(v, mats_arr)[0, 1] < 0:
                    v = -v
            elif key == "curvature":
                # belly (3-7y) minus wings; + loading on belly => + = more humped
                belly = (mats_arr >= 3) & (mats_arr <= 7)
                if v[belly].mean() - v[~belly].mean() < 0:
                    v = -v
            out_factors.append({"key": key, "label": _bil(en, zh),
                                 "var_explained": round(float(var[i]), 4),
                                 "loadings": {c: round(float(x), 3) for c, x in zip(mat.columns, v)}})
        result = {"factors": out_factors,
                  "first3_var": round(float(var[:3].sum()), 4) if len(var) >= 3 else None,
                  "window_d": int(len(dy)), "tenors": list(mat.columns)}
        # additive pca_health — never mutates the main PCA result; any exception → None
        try:
            result["pca_health"] = _pca_health(dy, vals, vecs)
        except Exception as _he:  # noqa: BLE001
            log.warning("pca_health failed: %s", _he)
            result["pca_health"] = None
        return result
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("yield-curve PCA failed: %s", e)
        return None


def shape(f: pd.DataFrame) -> dict:
    """The interpretable level / slope / curvature state (the economic reading of the
    three PCs) + butterfly spreads, each with a 5y percentile."""
    def g(c):
        return _col(f, c)
    nodes = {c: g(c) for c, _ in NODES}
    present = {c: s for c, s in nodes.items() if s is not None}
    # LEVEL — average yield across the curve (parallel height)
    level = None
    if len(present) >= 4:
        level = pd.concat(present.values(), axis=1).mean(axis=1)
    # SLOPE — 2s10s (the headline) + 3m10y (the recession-grade slope)
    slope_2s10s = g("spread_2s10s")
    if slope_2s10s is None and nodes["us10y"] is not None and nodes["us2y"] is not None:
        slope_2s10s = nodes["us10y"] - nodes["us2y"]
    slope_3m10y = g("spread_10y3m")
    if slope_3m10y is None and nodes["us10y"] is not None and nodes["us3m"] is not None:
        slope_3m10y = nodes["us10y"] - nodes["us3m"]
    # CURVATURE — the 2s5s10s butterfly: 2·belly − wings (>0 = humped, <0 = bowed)
    fly_2s5s10s = None
    if all(nodes[c] is not None for c in ("us2y", "us5y", "us10y")):
        fly_2s5s10s = 2 * nodes["us5y"] - nodes["us2y"] - nodes["us10y"]
    fly_5s10s30s = None
    if all(nodes[c] is not None for c in ("us5y", "us10y", "us30y")):
        fly_5s10s30s = 2 * nodes["us10y"] - nodes["us5y"] - nodes["us30y"]

    def block(s, fmt=2):
        return {"value": round(_last(s), fmt) if _last(s) is not None else None,
                "pctile": _pctile(s), "chg_63d": (round(_chg(s) * 100, 0)
                if _chg(s) is not None else None)}

    return {
        "level": block(level),
        "slope_2s10s": block(slope_2s10s),
        "slope_3m10y": block(slope_3m10y),
        "fly_2s5s10s": block(fly_2s5s10s),
        "fly_5s10s30s": block(fly_5s10s30s),
        "pca": pca_decomposition(f),
    }


# --------------------------------------------------------------------------- #
# 2) SLOPES + curve MOMENTUM (the "rate-of-change beats level" reads)
# --------------------------------------------------------------------------- #
def slopes(f: pd.DataFrame) -> dict:
    out = {}
    defs = [
        ("2s10s", "spread_2s10s", "us10y", "us2y", "2s10s (cycle slope)", "2-10年（周期斜率）"),
        ("3m10y", "spread_10y3m", "us10y", "us3m", "3m10y (recession slope)", "3月-10年（衰退斜率）"),
        ("5s30s", None, "us30y", "us5y", "5s30s (long-end / term-premium)", "5-30年（长端/期限溢价）"),
        ("2s5s", None, "us5y", "us2y", "2s5s (front belly)", "2-5年（前段腹部）"),
    ]
    for key, direct, longc, shortc, en, zh in defs:
        s = _col(f, direct) if direct else None
        if s is None and _col(f, longc) is not None and _col(f, shortc) is not None:
            s = f[longc] - f[shortc]
        if s is None:
            continue
        out[key] = {"label": _bil(en, zh), "value": round(_last(s), 2) if _last(s) is not None else None,
                    "pctile": _pctile(s),
                    "chg_63d_bp": round(_chg(s) * 100, 0) if _chg(s) is not None else None,
                    "inverted": (_last(s) is not None and _last(s) < 0)}
    # REAL curve slope (5y vs 10y TIPS) + BREAKEVEN curve slope
    if _col(f, "us10y_real") is not None and _col(f, "us5y_real") is not None:
        rs = f["us10y_real"] - f["us5y_real"]
        out["real_5s10s"] = {"label": _bil("Real 5s10s (TIPS curve)", "实际5-10年（TIPS曲线）"),
                             "value": round(_last(rs), 2) if _last(rs) is not None else None,
                             "pctile": _pctile(rs),
                             "chg_63d_bp": round(_chg(rs) * 100, 0) if _chg(rs) is not None else None,
                             "inverted": (_last(rs) is not None and _last(rs) < 0)}
    if _col(f, "breakeven_10y") is not None and _col(f, "breakeven_5y") is not None:
        bs = f["breakeven_10y"] - f["breakeven_5y"]
        out["be_5s10s"] = {"label": _bil("Breakeven 5s10s (inflation curve)", "盈亏平衡5-10年（通胀曲线）"),
                           "value": round(_last(bs), 2) if _last(bs) is not None else None,
                           "pctile": _pctile(bs),
                           "chg_63d_bp": round(_chg(bs) * 100, 0) if _chg(bs) is not None else None,
                           "inverted": False}
    if _col(f, "curve_tp_adj") is not None:
        tp = f["curve_tp_adj"]
        out["tp_adj"] = {"label": _bil("TP-adjusted 2s10s", "期限溢价调整2-10年"),
                         "value": round(_last(tp), 2) if _last(tp) is not None else None,
                         "pctile": _pctile(tp),
                         "chg_63d_bp": round(_chg(tp) * 100, 0) if _chg(tp) is not None else None,
                         "inverted": (_last(tp) is not None and _last(tp) < 0)}
    return out


def momentum(f: pd.DataFrame) -> dict:
    """Curve SPEED — the rate-of-change reads. The SPEED of a real-yield move breaks
    equities more than its level (measured, see the transmission calibration); the
    63d slope change is the steepening/flattening impulse."""
    real_speed = _chg(_col(f, "us10y_real"))
    nom_speed = _chg(_col(f, "us10y"))
    front_speed = _chg(_col(f, "us2y"))
    slope_chg = _chg(_col(f, "spread_2s10s"))
    # percentile of the |real-yield speed| over 5y — "how violent is this move?"
    speed_pct = None
    rsp = _col(f, "us10y_real")
    if rsp is not None:
        sp = (rsp - rsp.shift(MOM_WINDOW)).abs()
        speed_pct = _pctile(sp)
    # low-frequency TREND of the term spread (Faria-Verona 2020): the smoothed, business-
    # cycle-frequency component of the 3m10y spread is the one curve read with genuine
    # OOS equity-premium content — the raw / detrended (high-frequency) part is NOT. We use
    # a 2y trailing mean (leakage-free) as the live trend; its level/direction are the read.
    s10y3m = _col(f, "spread_10y3m")
    if s10y3m is None and _col(f, "us10y") is not None and _col(f, "us3m") is not None:
        s10y3m = f["us10y"] - f["us3m"]
    trend = trend_dir = trend_chg = None
    if s10y3m is not None:
        tr = s10y3m.rolling(504, min_periods=252).mean()
        trend = _last(tr)
        trend_chg = _chg(tr, 252)
        trend_dir = ("rising" if (trend_chg or 0) > 0.05 else
                     "falling" if (trend_chg or 0) < -0.05 else "flat") if trend_chg is not None else None
    return {
        "real10y_speed_bp": round(real_speed * 100, 0) if real_speed is not None else None,
        "nom10y_speed_bp": round(nom_speed * 100, 0) if nom_speed is not None else None,
        "front2y_speed_bp": round(front_speed * 100, 0) if front_speed is not None else None,
        "slope_chg_bp": round(slope_chg * 100, 0) if slope_chg is not None else None,
        "real_speed_pctile": speed_pct,
        "trend_spread": round(trend, 2) if trend is not None else None,
        "trend_spread_dir": trend_dir,
        "trend_spread_chg_1y_bp": round(trend_chg * 100, 0) if trend_chg is not None else None,
        "window_d": MOM_WINDOW,
    }


# --------------------------------------------------------------------------- #
# 3) REGIME — bull/bear × steepener/flattener + Fed-cycle phase + implications
# --------------------------------------------------------------------------- #
# What each curve regime tends to favour / pressure, and where in the Fed cycle it sits.
# THEORY map (textbook channel; the per-asset MEASURED edge lives in the transmission
# IC matrix). favored/pressured are sector-ETF / asset tickers.
REGIME_PLAY = {
    "bull_steepener": {
        "fed_phase_en": "Fed easing — front end falling fastest as cuts get priced (early recovery OR recessionary emergency easing)",
        "fed_phase_zh": "美联储宽松——短端下行最快，市场计入降息（复苏初期或衰退式紧急宽松）",
        "favored": ["TLT", "XLF", "IWM", "XLB"],
        "pressured": ["DX-Y.NYB", "XLP", "XLV"],
        "note_en": "Two faces: the benign post-pivot recovery (small caps, banks via wider NIM, cyclicals lead) OR a recessionary emergency cut. Empirically bull steepeners have been ~flat-to-NEGATIVE for US equities (Lombard Odier 45-yr study), and emergency-cut versions ran S&P −10% to −35% (2001, 2008). Duration (TLT) is the one reliable winner; everything equity-side needs CREDIT confirmation before you trust the recovery read.",
        "note_zh": "两副面孔：良性的转向后复苏（小盘、银行经更宽净息差、周期领涨）或衰退式紧急降息。实证上牛市变陡对美股大体为平至负（Lombard Odier 45年研究），紧急降息版本曾使标普下跌10%至35%（2001、2008）。久期（TLT）是唯一可靠赢家；股票端在信用确认前都不可轻信复苏判断。"},
    "bear_steepener": {
        "fed_phase_en": "Reflation / fiscal supply / term-premium repricing — long end rising fastest",
        "fed_phase_zh": "再通胀／财政供给／期限溢价重新定价——长端上行最快",
        "favored": ["XLE", "XLF", "XLB"],
        "pressured": ["QQQ", "XLK", "XLU", "XLRE", "TLT", "GC=F"],
        "note_en": "Historically the BEST equity regime overall (~+22% annualised across post-2000 growth-led episodes) — value, banks and real-asset cyclicals over long-duration growth/utilities/REITs. BUT a TERM-PREMIUM/fiscal-driven steepener (long end up with no growth) is not the bullish kind — check 5s30s + breakevens to disambiguate; rising term premium also breaks the 'duration = safe haven' assumption.",
        "note_zh": "历史上整体最佳的股票状态（2000年后增长主导的episode年化约+22%）——价值、银行、实物资产周期跑赢长久期成长/公用/REITs。但由期限溢价/财政驱动的变陡（长端上行而无增长）并非看多版本——用5-30年与盈亏平衡来区分；上升的期限溢价也会打破“久期＝避风港”的假设。"},
    "bull_flattener": {
        "fed_phase_en": "Late-cycle growth scare — long end falling fastest on a safety bid, Fed not yet cutting",
        "fed_phase_zh": "周期晚段增长恐慌——避险买盘压低长端最快，美联储尚未降息",
        "favored": ["TLT", "XLU", "XLV", "XLK", "GC=F"],
        "pressured": ["IWM", "XLF", "XLB", "FXI"],
        "note_en": "A flight to duration: long Treasuries, bond-proxy defensives and gold lead. The long-end rally is also a tailwind for long-duration GROWTH — Growth > Value, with Health Care + IT favoured (Man Group / MSCI) — while cyclicals and small caps lag. The market is pricing slowing growth ahead of the Fed.",
        "note_zh": "向久期避险：长债、类债券防御与黄金领先。长端走强亦利好长久期成长——成长优于价值，医疗与科技受青睐（Man Group / MSCI）——而周期与小盘落后。市场在美联储之前为增长放缓定价。"},
    "bear_flattener": {
        "fed_phase_en": "Hawkish Fed / active tightening — front end rising fastest, curve compressing toward inversion",
        "fed_phase_zh": "鹰派美联储／主动紧缩——短端上行最快，曲线向倒挂压缩",
        "favored": ["XLV", "XLP", "XLE"],
        "pressured": ["QQQ", "XLK", "IWM", "XLRE", "TLT", "BTC-USD"],
        "note_en": "The Fed out-hiking the long end — the pre-inversion, pre-recession tell. Financing cost squeezes small caps and long-duration growth/REITs de-rate; defensives (health care, staples) are the relative haven. Note banks are NOT a winner here — the flattening compresses net interest margins (SSGA: ~−0.4%/mo).",
        "note_zh": "美联储加息快于长端——倒挂前、衰退前的信号。融资成本挤压小盘、长久期成长/REITs估值下修；防御板块（医疗、必需消费）为相对避风港。注意银行在此并非赢家——趋平压缩净息差（SSGA：约−0.4%/月）。"},
}


def regime(f: pd.DataFrame) -> dict:
    cfg = _cfg()
    win = int(cfg.get("regime_window_d", 21))
    key, _series = curve_move_taxonomy(f, win)
    if key is None or key not in _TAXONOMY:
        return {"key": None}
    en, zh, desc_en, desc_zh = _TAXONOMY[key]
    play = REGIME_PLAY.get(key, {})
    # magnitude of the move (how decisive?)
    y10, y2 = _col(f, "us10y"), _col(f, "us2y")
    dlong = float(round((_last(y10) - y10.dropna().iloc[-1 - win]) * 100, 0)) if (y10 is not None and len(y10.dropna()) > win) else None
    dslope = _chg(_col(f, "spread_2s10s"), win)
    # term-premium direction (Kim-Wright THREEFYTP10) — shown with the regime so the "duration = safe haven"
    # assumption is explicit: a steepener driven by a RISING term premium is the kind that
    # also hurts long Treasuries (a ~50bp TP rise ≈ ~3% bond drawdown).
    tp_chg = _chg(_col(f, "term_premium_10y"))
    tp_dir = ("rising" if (tp_chg or 0) > 0.05 else "falling" if (tp_chg or 0) < -0.05 else "stable") if tp_chg is not None else None
    return {
        "key": key, "label": _bil(en, zh), "desc": _bil(desc_en, desc_zh),
        "fed_phase": _bil(play.get("fed_phase_en", ""), play.get("fed_phase_zh", "")),
        "note": _bil(play.get("note_en", ""), play.get("note_zh", "")),
        "favored": play.get("favored", []), "pressured": play.get("pressured", []),
        "long_chg_bp": dlong, "slope_chg_bp": round(dslope * 100, 0) if dslope is not None else None,
        "term_premium_dir": tp_dir,
        "term_premium_chg_bp": round(tp_chg * 100, 0) if tp_chg is not None else None,
        "window_d": win,
    }


# --------------------------------------------------------------------------- #
# 4) RECESSION dashboard — NTFS + NY-Fed probit + un-inversion + TP-adjusted
# --------------------------------------------------------------------------- #
def recession(f: pd.DataFrame) -> dict:
    bcfg = config.load().get("bonds", {}).get("curve", {})
    s10y3m = _col(f, "spread_10y3m")
    if s10y3m is None and _col(f, "us10y") is not None and _col(f, "us3m") is not None:
        s10y3m = f["us10y"] - f["us3m"]
    nyfed = None
    if s10y3m is not None and bcfg:
        prob = ny_fed_recession_prob(s10y3m, bcfg)
        nyfed = round(_last(prob) * 100, 0) if _last(prob) is not None else None
    ntfs = near_term_forward_spread(f)
    ntfs_v = _last(ntfs)
    uninv = False
    if s10y3m is not None:
        uninv, _ = uninversion(s10y3m, int(bcfg.get("uninvert_lookback_d", 252)))
    tp = _last(_col(f, "curve_tp_adj"))

    # composite read — how many of the four are flashing?
    flags = []
    if ntfs_v is not None and ntfs_v < 0:
        flags.append("ntfs")
    if nyfed is not None and nyfed >= 30:
        flags.append("probit")
    if uninv:
        flags.append("uninversion")
    if tp is not None and tp < 0:
        flags.append("tp_adj")
    n = len(flags)
    if n == 0:
        risk = "low"
    elif n == 1:
        risk = "watch"
    elif n == 2:
        risk = "elevated"
    else:
        risk = "high"
    # Wright (2006) policy-stance context: the SAME curve slope is more restrictive at a
    # higher funds level — augmenting the probit with the funds level improves in-sample
    # fit. We show the stance vs a ~2.5% nominal-neutral (r* ~0.5% + 2% target) anchor.
    ff = _last(_col(f, "fed_funds"))
    neutral = float(config.load().get("yield_curve", {}).get("neutral_funds", 2.5))
    policy_stance = None
    if ff is not None:
        gap = ff - neutral
        stance = ("restrictive" if gap > 0.5 else "accommodative" if gap < -0.5 else "neutral")
        policy_stance = {
            "fed_funds": round(ff, 2), "neutral_anchor": neutral,
            "gap_pp": round(gap, 2), "stance": stance,
            "note": _bil(
                f"Funds {ff:.2f}% vs ~{neutral:.1f}% nominal-neutral = {stance}. Wright (2006): the same curve slope is more restrictive at a higher funds level — a flat curve at 5% funds is a stronger recession tell than at 2%.",
                f"联邦基金{ff:.2f}% vs 约{neutral:.1f}%名义中性＝{ {'restrictive':'偏紧','accommodative':'宽松','neutral':'中性'}[stance] }。Wright（2006）：相同曲线斜率在更高基金利率下更具紧缩性——5%基金利率下的平坦曲线比2%下更强的衰退信号。"),
        }
    return {
        "ntfs": round(ntfs_v, 2) if ntfs_v is not None else None,
        "ntfs_signal": ("inverted — market pricing cuts (growth breaking)" if (ntfs_v or 0) < 0
                        else "positive — no near-term break priced") if ntfs_v is not None else None,
        "nyfed_prob": nyfed,
        "uninversion": bool(uninv),
        "tp_adj_curve": round(tp, 2) if tp is not None else None,
        "flags": flags, "n_flags": n, "risk": risk,
        "policy_stance": policy_stance,
        "lead_time_note": _bil(
            "The near-term forward spread (3m rate ~18m forward − 3m bill) statistically dominates the 2s10s — Engstrom-Sharpe (Fed 2018-19) find it renders the 2s10s redundant in a joint probit. We read 3m10y, not 2s10s, as the recession slope (Estrella-Mishkin γ = −0.53, −0.66). The genuinely ominous configuration is the curve RE-STEEPENING out of a deep inversion: the un-inversion has historically COINCIDED WITH or slightly led recession onset (1990 ≈3m, 2001 ≈6m after the curve turned positive) — a fresh dis-inversion is the late-cycle handoff, not an all-clear.",
            "近端远期利差（约18个月远期3月利率−3月票据）在统计上优于2-10年——Engstrom-Sharpe（美联储2018-19）发现在联合probit中它使2-10年变得多余。我们以3月-10年（而非2-10年）作为衰退斜率（Estrella-Mishkin γ＝−0.53、−0.66）。真正危险的形态是深度倒挂后曲线重新变陡：历史上重新转正与衰退开始大致同步或略微领先（1990年约3个月、2001年约6个月），因此刚出现的重新变陡是周期晚段的交接，而非解除警报。"),
    }


# --------------------------------------------------------------------------- #
# 5) FORWARDS + carry & roll-down
# --------------------------------------------------------------------------- #
def _interp_yield(f: pd.DataFrame, t: float) -> float | None:
    """Linear interpolation of the par yield at maturity t (years) from the nodes."""
    pts = [(mat, _last(_col(f, col))) for col, mat in NODES if _last(_col(f, col)) is not None]
    if len(pts) < 2:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return float(np.interp(t, xs, ys))


def _forward(f: pd.DataFrame, t0: float, t1: float) -> float | None:
    """The (t1−t0)-period rate, t0 years forward, from the spot curve (continuous approx
    on the par curve): fwd = (y(t1)·t1 − y(t0)·t0) / (t1 − t0)."""
    y0, y1 = _interp_yield(f, t0), _interp_yield(f, t1)
    if y0 is None or y1 is None or t1 <= t0:
        return None
    return (y1 * t1 - y0 * t0) / (t1 - t0)


def forwards(f: pd.DataFrame) -> dict:
    y10, y7 = _interp_yield(f, 10.0), _interp_yield(f, 7.0)
    # carry & roll-down on a 10y held 1y: carry ≈ yield; roll-down ≈ (y10 − y9)·DV01-ish.
    # Practitioner shorthand on the par curve: roll = (y(10) − y(9)) × (modified duration).
    y9 = _interp_yield(f, 9.0)
    carry = y10
    roll = None
    if y10 is not None and y9 is not None:
        # approx modified duration of a 10y ≈ 8.0; roll-down return ≈ Δy × dur
        roll = (y10 - y9) * 8.0
    return {
        "f_1y1y": round(_forward(f, 1.0, 2.0), 2) if _forward(f, 1.0, 2.0) is not None else None,
        "f_2y1y": round(_forward(f, 2.0, 3.0), 2) if _forward(f, 2.0, 3.0) is not None else None,
        "f_5y5y": round(_forward(f, 5.0, 10.0), 2) if _forward(f, 5.0, 10.0) is not None else None,
        "carry_10y_pct": round(carry, 2) if carry is not None else None,
        "rolldown_10y_pct": round(roll, 2) if roll is not None else None,
        "carry_roll_10y_pct": round((carry or 0) / 1.0 + (roll or 0), 2) if carry is not None else None,
        "note": _bil(
            "Forward rates are the market-implied future short rates embedded in today's curve; carry+roll-down is the total return a duration holder earns if the curve is unchanged in a year (the cushion before price loss).",
            "远期利率是今日曲线隐含的市场预期未来短端利率；carry＋滚动收益是久期持有者在曲线一年不变时获得的总回报（价格亏损前的缓冲）。"),
    }


# --------------------------------------------------------------------------- #
# 6) SIGNAL families — core-macro / sector / stock-factor / market-tendency
# --------------------------------------------------------------------------- #
# the curve drivers in the transmission IC matrix, strongest-first — NTFS and the
# 2s5s10s curvature carry CONFIRMED split-half forward-IC cells for most equity sleeves
# (the calibration found them far stronger than the raw TP-adjusted slope, which is
# CONTEXT). A sector tile is tagged MEASURED off the strongest confirmed cell among these.
CURVE_IC_DRIVERS = ["ntfs", "curvature", "curve_tp_adj", "slope_chg63"]
_CURVE_DRIVER_LABEL = {"ntfs": "NTFS", "curvature": "curvature", "curve_tp_adj": "TP-curve",
                       "slope_chg63": "Δslope"}


def _load_transmission_matrix() -> dict:
    """The MEASURED per-asset forward-IC matrix (data/transmission/calibration.json),
    so sector tilts can be tagged MEASURED where an edge exists, THEORY otherwise."""
    p = config.data_dir() / "transmission" / "calibration.json"
    try:
        return (json.loads(p.read_text()) or {}).get("transmission_matrix", {}) if p.exists() else {}
    except Exception:  # noqa: BLE001
        return {}


def _best_curve_cell(mat: dict, etf: str) -> dict | None:
    """The strongest CONFIRMED/DIRECTIONAL curve-driver forward-IC cell for an asset."""
    best = None
    for drv in CURVE_IC_DRIVERS:
        cell = (mat.get(drv, {}).get("assets", {}) or {}).get(etf, {})
        if cell.get("verdict") in ("CONFIRMED", "DIRECTIONAL") and cell.get("ic") is not None:
            if best is None or abs(cell["ic"]) > abs(best["ic"]):
                best = {"driver": drv, "ic": cell["ic"], "verdict": cell["verdict"]}
    return best


# Per-sector curve/rate sensitivity — sign + mechanism (THEORY anchor). The dashboard
# blends this with the MEASURED IC where the calibrator has an edge. +slope_beta = helped
# by a STEEPER curve; +rate_beta = helped by HIGHER long rates (rare); -dur = long-duration.
SECTOR_RATE = {
    "XLF": {"slope": +1, "level": +1, "dur": "short", "mech_en": "banks earn the curve — steeper = wider NIM; rate beneficiary",
            "mech_zh": "银行赚取曲线——更陡＝更宽净息差；利率受益"},
    "XLRE": {"slope": 0, "level": -1, "dur": "long", "mech_en": "REITs are bond-proxy long-duration — hurt by higher long rates",
             "mech_zh": "REITs为类债券长久期——受长端利率上行拖累"},
    "XLU": {"slope": 0, "level": -1, "dur": "long", "mech_en": "utilities are the classic bond proxy — dividend yield competes with rates",
            "mech_zh": "公用事业为经典类债券——股息率与利率竞争"},
    "XLK": {"slope": -1, "level": -1, "dur": "long", "mech_en": "long-duration growth — rising discount rate de-rates future cash flows",
            "mech_zh": "长久期成长——贴现率上行压低未来现金流估值"},
    "XLY": {"slope": 0, "level": -1, "dur": "neutral", "mech_en": "consumer discretionary — cyclical growth offset by financing-cost drag (autos/credit) + long-duration mega-cap skew",
            "mech_zh": "可选消费——周期性增长被融资成本拖累（汽车/信贷）抵消，且有长久期巨头偏向"},
    "XLP": {"slope": -1, "level": 0, "dur": "short", "mech_en": "staples — mild bond proxy with pricing power; relatively favoured when the curve flattens / growth slows (weaker rate sensitivity than utilities)",
            "mech_zh": "必需消费——具定价权的温和类债券；曲线趋平/增长放缓时相对受青睐（利率敏感度弱于公用事业）"},
    "XLV": {"slope": -1, "level": 0, "dur": "short", "mech_en": "health care defensive — low rate sensitivity, late-cycle relative haven",
            "mech_zh": "医疗防御——利率敏感度低、周期晚段相对避风港"},
    "XLE": {"slope": +1, "level": +1, "dur": "short", "mech_en": "energy — reflation/inflation beneficiary, bear-steepener winner",
            "mech_zh": "能源——再通胀/通胀受益，熊市变陡赢家"},
    "XLB": {"slope": +1, "level": 0, "dur": "neutral", "mech_en": "materials — cyclical reflation play, helped by a steepening growth curve",
            "mech_zh": "材料——周期再通胀，受益于增长型变陡"},
    "XLI": {"slope": +1, "level": 0, "dur": "neutral", "mech_en": "industrials — cyclical, mild positive to a growth-led steepening",
            "mech_zh": "工业——周期性，对增长型变陡温和正向"},
    "IWM": {"slope": +1, "level": -1, "dur": "long", "mech_en": "small caps — heavy floating-rate debt; financing cost is the squeeze, easing the relief",
            "mech_zh": "小盘——大量浮动利率债务；融资成本是挤压，宽松是缓解"},
}


def sector_signals(f: pd.DataFrame, reg: dict, slp: dict) -> list:
    """Per-sector curve tilt: derived from the live regime's favored/pressured lists +
    the slope direction, tagged MEASURED where the transmission IC matrix has a confirmed
    cell, THEORY otherwise. Display-context only."""
    mat = _load_transmission_matrix()
    fav = set(reg.get("favored", []))
    pres = set(reg.get("pressured", []))
    # is the curve steepening or flattening right now (63d slope change)?
    slope_chg = (slp.get("2s10s", {}) or {}).get("chg_63d_bp")
    steepening = slope_chg is not None and slope_chg > 0
    out = []
    for etf, meta in SECTOR_RATE.items():
        # regime tilt
        if etf in fav:
            tilt = "tailwind"
        elif etf in pres:
            tilt = "headwind"
        else:
            # fall back to the slope-beta × current steepening direction
            sb = meta["slope"]
            if sb == 0 or slope_chg is None:
                tilt = "neutral"
            else:
                tilt = "tailwind" if (sb > 0) == steepening else "headwind"
        # measured-edge tag: the strongest CONFIRMED/DIRECTIONAL curve-driver cell here
        best = _best_curve_cell(mat, etf)
        basis = "measured" if best else "theory"
        out.append({"etf": etf, "tilt": tilt, "basis": basis,
                    "ic": best["ic"] if best else None,
                    "ic_driver": _CURVE_DRIVER_LABEL.get(best["driver"]) if best else None,
                    "verdict": best["verdict"] if best else None,
                    "duration": meta["dur"],
                    "mech": _bil(meta["mech_en"], meta["mech_zh"])})
    # order: tailwinds first, then headwinds, neutrals last
    rank = {"tailwind": 0, "headwind": 1, "neutral": 2}
    out.sort(key=lambda x: rank.get(x["tilt"], 3))
    return out


def factor_signals(reg: dict, slp: dict, mom: dict) -> dict:
    """Equity STYLE / FACTOR tilts the curve implies (display-context). Value-vs-growth
    tracks the curve: value (short-duration cash flows) outperforms growth (long-duration)
    when the curve bear-steepens / real rates rise; the mirror in a bull-flattener."""
    key = reg.get("key")
    slope_chg = (slp.get("2s10s", {}) or {}).get("chg_63d_bp")
    real_speed = mom.get("real10y_speed_bp")
    steepening = slope_chg is not None and slope_chg > 0
    rates_rising = real_speed is not None and real_speed > 0

    # value vs growth: + = value favored
    if key in ("bear_steepener", "bear_flattener") or rates_rising:
        value_growth = "value"
    elif key in ("bull_flattener",) or (real_speed is not None and real_speed < 0):
        value_growth = "growth"
    else:
        value_growth = "neutral"
    # size: small caps want a bull steepener (cuts) + falling real rates
    if key == "bull_steepener":
        size = "small"
    elif key in ("bear_flattener", "bull_flattener"):
        size = "large"
    else:
        size = "neutral"
    # duration factor (long-duration equities helped/hurt)
    duration = "headwind" if rates_rising else "tailwind" if (real_speed is not None and real_speed < 0) else "neutral"
    return {
        "value_vs_growth": value_growth,
        "size": size,
        "duration_factor": duration,
        "label": _bil(
            f"Curve favours { {'value':'value over growth','growth':'growth over value','neutral':'neither value nor growth decisively'}[value_growth] }"
            f", { {'small':'small caps','large':'large caps','neutral':'no clear size'}[size] }.",
            f"曲线倾向于{ {'value':'价值优于成长','growth':'成长优于价值','neutral':'价值/成长无明显倾向'}[value_growth] }"
            f"、{ {'small':'小盘','large':'大盘','neutral':'规模无明显倾向'}[size] }。"),
        "note": _bil(
            "Equity duration: growth stocks discount cash flows further out, so they behave as long-duration assets and de-rate when real yields rise (~2× the rate-sensitivity of value, BIS 2022); value/financials are short-duration. HONEST CAVEAT: the long-run correlation of the value-minus-growth factor with Δ10y is only ~0.10 (AQR/Asness) — the link is concentrated in episodes (the +25% growth→value rotation of 2022) and is largely NOT pure duration. Small caps are driven by the FRONT end (floating-rate debt cost), a distinct channel from value/growth duration.",
            "股票久期：成长股贴现更远期的现金流，因而表现为长久期资产，实际收益率上行时估值下修（利率敏感度约为价值的2倍，BIS 2022）；价值/金融为短久期。诚实提醒：价值减成长因子与10年期变动的长期相关性仅约0.10（AQR/Asness）——该联系集中于特定时期（如2022年+25%的成长→价值轮动），且大部分并非纯久期效应。小盘由前端驱动（浮动利率债务成本），与价值/成长久期是不同的渠道。"),
    }


def market_tendency(f: pd.DataFrame, mom: dict, rec: dict) -> dict:
    """Curve-speed → equity drawdown-risk read (market tendency). The SPEED of a real-
    yield move predicts forward equity drawdowns better than its level (measured), and a
    fresh un-inversion stacks recession risk. Display-context; the calibrator found no
    curve leg robust enough to SCORE this — it remains a reactive risk flag."""
    speed_pct = mom.get("real_speed_pctile")
    real_speed = mom.get("real10y_speed_bp")
    n_flags = rec.get("n_flags", 0)
    # a violent real-rate move is the cleanest drawdown precursor: 2022 ran ~+250bp real-
    # yield over the year → S&P −25%, Nasdaq −35% with the stock-bond hedge breaking; the
    # 1994 +300bp episode (from an already-positive base) cost only ~10%, so SPEED and the
    # starting point matter more than cumulative level. Flag on |Δ63d real-10y| ≥ ~75bp
    # (Engstrom-Sharpe / the transmission calibration) OR a top-quintile speed percentile.
    abs_violent = real_speed is not None and abs(real_speed) >= 75
    pct_violent = speed_pct is not None and speed_pct >= 0.80
    violent = abs_violent or pct_violent
    rising = real_speed is not None and real_speed > 0
    if violent and rising:
        risk = "elevated"
    elif n_flags >= 2 or (violent and not rising):
        risk = "watch"
    else:
        risk = "calm"
    return {
        "drawdown_risk": risk,
        "real_speed_pctile": speed_pct,
        "basis": "measured-direction, display-only",
        "label": _bil(
            {"elevated": "A fast real-yield repricing is the configuration that historically precedes equity drawdowns — reactive risk, not a forecast.",
             "watch": "Curve/rate stress building — worth watching, not yet a drawdown signal.",
             "calm": "No fast real-rate repricing — the curve is not flagging near-term equity stress."}[risk],
            {"elevated": "实际收益率快速重定价是历史上股票回撤前的形态——被动风险，并非预测。",
             "watch": "曲线/利率压力在积聚——值得关注，尚非回撤信号。",
             "calm": "无快速实际利率重定价——曲线未对近端股票压力发出警示。"}[risk]),
    }


# --------------------------------------------------------------------------- #
# CAVEATS + assembly
# --------------------------------------------------------------------------- #
CAVEATS = [
    _bil("Display / context only — never scored. The house calibrator's scored-leg gate found NO yield-curve leg robust enough to move an allocation (the strongest, real-rate speed, is regime-dependent and fails purged-CV).",
         "仅供展示／背景，从不计入评分。本系统校准器的可计分腿门槛发现没有任何收益率曲线腿稳健到足以改变配置（最强的实际利率速度依赖状态且未通过清洗交叉验证）。"),
    _bil("Rate-of-change beats level: the SPEED of a yield move informs equity risk more than its level, and curve repricing is REACTIVE — the curve moves after the data and the Fed, not before.",
         "变动速度胜过水平：收益率移动的速度比其水平更能反映股票风险，且曲线重定价是被动的——曲线在数据与美联储之后变动，而非之前。"),
    _bil("Sector / factor tilts tagged THEORY are textbook channels with no measured forward edge; only cells tagged MEASURED carry a calibrated forward IC. Neither is a trade signal.",
         "标注为“理论”的板块／因子倾向是教科书式传导、无实测前瞻优势；仅标注为“实测”的单元带有校准的前瞻IC。两者均非交易信号。"),
]


def snapshot(f: pd.DataFrame) -> dict | None:
    """Assemble the full yield-curve read. Graceful: returns None only if the curve
    itself is unavailable; any sub-block degrades to None/empty on its own."""
    cfg = _cfg()
    if not cfg.get("enabled", True):
        return None
    if _col(f, "us10y") is None or _col(f, "us2y") is None:
        return None
    try:
        sh = shape(f)
        slp = slopes(f)
        mom = momentum(f)
        reg = regime(f)
        rec = recession(f)
        fwd = forwards(f)
        sec = sector_signals(f, reg, slp)
        fac = factor_signals(reg, slp, mom)
        mt = market_tendency(f, mom, rec)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("yield_curve snapshot failed: %s", e)
        return None

    # the compact core-macro read for the dashboard / LLM brief
    reg_lbl = (reg.get("label") or {}).get("en", "—")
    core_macro = _bil(
        f"Curve: {reg_lbl}. {('recession dashboard ' + rec['risk']) if rec.get('risk') else ''} ({rec.get('n_flags', 0)}/4 flags).",
        f"曲线：{(reg.get('label') or {}).get('zh', '—')}。衰退面板{ {'low':'低','watch':'观察','elevated':'升高','high':'高'}.get(rec.get('risk'),'—') }（{rec.get('n_flags',0)}/4 项亮起）。")

    return {
        "asof": str(f.index[-1].date()),
        "shape": sh,
        "slopes": slp,
        "momentum": mom,
        "regime": reg,
        "recession": rec,
        "forwards": fwd,
        "signals": {
            "core_macro": core_macro,
            "sector": sec,
            "stock_factor": fac,
            "market_tendency": mt,
        },
        "scored_status": _bil(
            "Display-only. No yield-curve leg passed the forward-drawdown scored-leg gate (see reports/rate-inflation-transmission-calibration.md).",
            "仅供展示。没有任何收益率曲线腿通过前瞻回撤可计分门槛（详见校准报告）。"),
        "caveats": CAVEATS,
    }
