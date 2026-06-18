"""Anticipation Engine — the live per-asset emitter.

Turns the validated feature legs (engine/velocity, engine/vol_forecast) into a
multi-horizon, probabilistic forward-outcome cone via the conditional-distribution
kernel (engine/forward_dist), then packages it as the display JSON the UI renders.

WHAT IT CLAIMS, HONESTLY (Phase-0 measured, scripts/anticipation_phase0.py):
  * The cone (conditional forward RETURN quantiles + DRAWDOWN) is the forecastable
    quantity. The confluence state — vol regime + deteriorating-trend velocity +
    rising-variance + extension — orders forward drawdown robustly (GO legs).
  * Short-horizon DIRECTION is a measured coin-flip (Brier skill ≈ 0): P(up) is
    EB-shrunk, capped, and the short horizon is always labelled TOSS-UP.
  * Legs that did NOT pass Phase-0 (acceleration, RS-velocity, impulse, extension at
    the short gauge) appear as DISPLAY-ONLY drivers, never in the scored state.

POINT-IN-TIME: every input is computed from close ≤ as_of; band edges and the analog
cell come from history up to as_of only. Truncate-and-recompute == full at past dates
(tests/test_anticipation.py). Reads data/regime/anticipation_gate.json for which legs
are GO per asset class; an unknown/missing gate ⇒ everything display-only (NEUTRAL).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from engine import forward_dist, index_direction, indicators, velocity, vol_forecast

# (lo_td, hi_td, representative_window_td) — ranges justified in research/ANTICIPATION_ENGINE.md
HORIZONS = {"short": (1, 10, 5), "medium": (21, 63, 42), "long": (126, 252, 189)}
_GATE_PATH = Path("data") / "regime" / "anticipation_gate.json"
_INDEX_BANDS = ("calm", "elevated", "high", "extreme")

# Market overlay legs (same for every name on a date), oriented higher = more
# dangerous. Built ONCE per run and shared by the live engine and the Phase-0 harness
# (scripts/anticipation_phase0 imports these) so live == validated. GEX is absent on
# purpose — no free history to validate; it can only be a live display-only chip.
MACRO_LEGS = ["m_vix", "m_vix_term", "m_move", "m_hy_oas", "m_hy_vel", "m_curve_inv",
              "m_dollar_vel", "m_netliq_vel", "m_nfci", "m_gpr", "m_gpr_act",
              "m_epu", "m_breadth_vel"]


def load_gate(asset_class: str = "US") -> dict:
    """Per-class {leg: GO|NEUTRAL}. Missing/unreadable ⇒ {} ⇒ all display-only."""
    try:
        g = json.loads(_GATE_PATH.read_text())
        return g.get(asset_class, g.get("US", {})) if isinstance(g, dict) else {}
    except Exception:
        return {}


def direction_gate(asset: str) -> dict:
    """The INDEX_DIRECTION[asset] block (per-index directional model). Missing ⇒ {} ⇒
    the index stays a coin-flip / display-only, mirroring the risk-gate rule."""
    try:
        g = json.loads(_GATE_PATH.read_text())
        return (g.get("INDEX_DIRECTION", {}) or {}).get(asset, {})
    except Exception:
        return {}


def name_direction_gate() -> dict:
    """The shared NAME_DIRECTION block (single-name macro-transmission model). ONE block for
    ALL names. Missing/all-display-only ⇒ {} ⇒ every name stays a coin-flip (the validated
    default — single-name real-rate transmission is a Phase-0 null)."""
    try:
        g = json.loads(_GATE_PATH.read_text())
        return g.get("NAME_DIRECTION", {}) or {}
    except Exception:
        return {}


def name_direction_scored(gate: dict | None = None) -> bool:
    """True iff the shared NAME_DIRECTION gate has at least one scored horizon — the cheap
    check build_stock_library uses to decide whether to compute per-name betas at all (so a
    NULL gate adds ZERO cost to the daily build)."""
    g = gate if gate is not None else name_direction_gate()
    return any((g.get(h) or {}).get("scored") for h in ("medium", "long"))


def macro_legs_frame() -> pd.DataFrame:
    """Date-indexed market overlay legs (oriented higher = more dangerous), forward-
    filled to daily. The single source of truth shared with the Phase-0 harness.
    Returns an empty frame if the macro stores are absent (engine never crashes)."""
    F, Y, U = Path("data/fred"), Path("data/yahoo"), Path("data/uncertainty")
    try:
        idx = pd.bdate_range("1985-01-01", "2027-01-01")
        R = lambda s: s.reindex(idx).ffill()
        col0 = lambda p: (lambda d: d[d.columns[0]])(pd.read_parquet(p))
        clean = lambda s: s.replace(0, np.nan)
        vix = R(clean(pd.read_parquet(Y / "_VIX.parquet")["close"]))
        try:
            vix = R(clean(col0(F / "VIXCLS.parquet"))).fillna(vix)
        except Exception:
            pass
        vix3m = R(clean(pd.read_parquet(Y / "_VIX3M.parquet")["close"]))
        move = R(clean(pd.read_parquet(Y / "_MOVE.parquet")["close"]))
        hy = R(col0(F / "BAMLH0A0HYM2.parquet"))
        curve = R(col0(F / "T10Y3M.parquet"))
        dollar = R(col0(F / "DTWEXBGS.parquet"))
        netliq = R(col0(F / "WALCL.parquet")) / 1e6 - R(col0(F / "RRPONTSYD.parquet"))
        nfci = R(col0(F / "NFCI.parquet"))
        g = pd.read_parquet(U / "gpr.parquet")
        gpr_l, gpr_act = R(g["gpr"]), R(g["gpr_act"])
        epu = R(col0(U / "epu_us.parquet"))
        brd = R(pd.read_parquet("data/breadth/breadth.parquet")["pct_above_200"])
    except Exception:
        return pd.DataFrame()

    def pctl(s, w=252):
        return s.rolling(w, min_periods=w // 2).rank(pct=True)

    def zz(s, w=504):
        m = s.rolling(w, min_periods=w // 3)
        return (s - m.mean()) / m.std(ddof=0).replace(0, np.nan)

    sl = lambda s, log=False: indicators.slope_z(s, 20, 60, use_log=log)
    M = pd.DataFrame(index=idx)
    M["m_vix"] = pctl(vix)
    M["m_vix_term"] = zz(vix - vix3m, 252)
    M["m_move"] = pctl(move)
    M["m_hy_oas"] = zz(hy)
    M["m_hy_vel"] = sl(hy)
    M["m_curve_inv"] = -curve
    M["m_dollar_vel"] = sl(dollar, log=True)
    M["m_netliq_vel"] = -sl(netliq)
    M["m_nfci"] = nfci
    M["m_gpr"] = pctl(gpr_l)
    M["m_gpr_act"] = pctl(gpr_act)
    M["m_epu"] = pctl(epu)
    M["m_breadth_vel"] = -sl(brd)
    return M


def macro_overlay(macro_frame: pd.DataFrame, gate: dict, as_of) -> dict | None:
    """Combine the VALIDATED (GO) macro legs into a single market-stress read as of
    `as_of`: a 0-100 stress percentile + a cone-WIDTH multiplier (high credit/conditions
    stress widens every name's downside) + the scored macro drivers. Display/risk only —
    never touches direction. None if no GO macro legs or no data."""
    go = [l for l in MACRO_LEGS if (gate or {}).get(l) == "GO"]
    if not go or macro_frame is None or macro_frame.empty:
        return None
    comp = macro_frame[go].apply(lambda s: s.rolling(252, min_periods=120).rank(pct=True)).mean(axis=1)
    comp = comp.dropna()
    if comp.empty:
        return None
    stress = float(comp.asof(pd.Timestamp(as_of))) if as_of else float(comp.iloc[-1])
    if not np.isfinite(stress):
        stress = float(comp.iloc[-1])
    width_mult = round(1.0 + 0.6 * max(0.0, stress - 0.5) * 2, 2)   # widen tail above median stress
    drivers = []
    for l in go:
        v = macro_frame[l].dropna()
        if v.empty:
            continue
        en, zh = _DRIVER_LABEL.get(l, (l, l))
        drivers.append({"axis": l, "value": round(float(v.asof(pd.Timestamp(as_of)) if as_of else v.iloc[-1]), 2),
                        "scored": True, "display_only": False, "label": {"en": en, "zh": zh}})
    return {"stress_pct": round(100 * stress, 1), "width_mult": width_mult,
            "go_legs": go, "drivers": drivers}


def _zr(s: pd.Series, win: int) -> pd.Series:
    m = s.rolling(win, min_periods=max(40, win // 3))
    return (s - m.mean()) / m.std(ddof=0).replace(0, np.nan)


def _legs(close: pd.Series, bench, breadth) -> tuple[pd.DataFrame, pd.Series]:
    """Oriented legs (higher = more dangerous) + the confluence composite state.
    Mirrors scripts/anticipation_phase0.oriented_legs so live == validated."""
    vf = velocity.velocity_features(close, bench=bench, breadth=breadth)
    L = pd.DataFrame(index=close.index)
    L["det_z"] = velocity.deterioration_z(vf)
    L["neg_trend_vel"] = -vf["trend_vel"]
    L["neg_trend_accel"] = -_zr(vf["trend_accel"], 252)
    if "rs_vel" in vf:
        L["neg_rs_vel"] = -vf["rs_vel"]
    L["neg_impulse"] = -vf["impulse"]
    L["rvar_vel"] = _zr(vf["rvar_vel"], 252)
    ma200 = close.rolling(200, min_periods=120).mean()
    L["ext_z"] = _zr(close / ma200, 504)
    L["vol_pct"] = vol_forecast.vol_regime(close, 252)
    L["trend_vel"] = vf["trend_vel"]
    confluence = pd.concat([L["det_z"], L["ext_z"], L["vol_pct"].sub(0.5).mul(4),
                            L["neg_trend_vel"]], axis=1).mean(axis=1)
    L["confluence"] = confluence
    return L, confluence


_DRIVER_LABEL = {
    "vol_pct": ("Volatility regime", "波动率状态"),
    "neg_trend_vel": ("Trend deteriorating (velocity)", "趋势恶化（速度）"),
    "rvar_vel": ("Variance rising (early-warning)", "方差上升（预警）"),
    "confluence": ("Confluence (combined)", "合流（综合）"),
    "det_z": ("Deterioration composite", "恶化综合"),
    "neg_trend_accel": ("Deterioration accelerating", "恶化加速"),
    "neg_rs_vel": ("Relative-strength fading", "相对强度走弱"),
    "neg_impulse": ("Momentum impulse down", "动量脉冲向下"),
    "ext_z": ("Stretched above trend", "高于趋势拉伸"),
    "m_hy_oas": ("Credit spreads (HY OAS)", "信用利差（高收益）"),
    "m_hy_vel": ("Credit spreads widening", "信用利差走阔"),
    "m_nfci": ("Financial conditions tightening", "金融条件收紧"),
    "m_vix": ("Market fear (VIX)", "市场恐慌（VIX）"),
    "m_gpr": ("Geopolitical risk", "地缘政治风险"),
}


def _conviction(p_up: float, horizon_name: str) -> str:
    if horizon_name == "short":
        return "TOSS_UP"                      # measured coin-flip — never an edge
    lean = abs(p_up - 0.5)
    return "TOSS_UP" if lean < 0.03 else ("LEAN" if lean < 0.08 else "EDGE")


def anticipate(close: pd.Series, high: pd.Series | None = None, low: pd.Series | None = None,
               *, bench: pd.Series | None = None, breadth: pd.Series | None = None,
               asset: str = "", asset_class: str = "us_equity", gate: dict | None = None,
               macro_frame: pd.DataFrame | None = None, horizons: dict = HORIZONS,
               name_dir_inputs: dict | None = None) -> dict:
    """Multi-horizon anticipation cone for one asset. Returns {} if too little history.
    `gate` overrides the on-disk gate (for tests); `macro_frame` is the shared market
    overlay (build once via macro_legs_frame(); None ⇒ no overlay). `name_dir_inputs`
    (single-name macro-transmission lean: {inputs, gate, dur_prior}) is passed ONLY for
    equities AND only when the NAME_DIRECTION gate has a scored horizon — None ⇒ coin-flip."""
    close = close.dropna().astype(float)
    if len(close) < 300:
        return {}
    gate = gate if gate is not None else load_gate("US")
    L, conf = _legs(close, bench, breadth)
    as_of = str(close.index[-1])[:10]

    # confluence state band (causal: edges from history up to as_of) + the cone
    cone = forward_dist.multi_horizon_cone(
        close, conf, {k: rep for k, (_, _, rep) in horizons.items()}, k=4)
    idx_val = cone.get("now")
    band = cone.get("band")
    index_band = _INDEX_BANDS[band] if band is not None else "n/a"
    # 0..100 index = percentile of current confluence in its own history (display)
    idx_pct = float(conf.rank(pct=True).iloc[-1] * 100) if conf.notna().any() else None

    # direction cell: trend × vol_band (the measured coin-flip baseline)
    vmed = L["vol_pct"].median()
    vol_band = np.where(L["vol_pct"] > vmed, "hi", "lo")
    cell_key = pd.Series(np.where(L["trend_vel"] > 0, "up_", "dn_"), index=close.index) \
        + pd.Series(vol_band, index=close.index)

    # per-index DIRECTIONAL model — gated on INDEX MEMBERSHIP (not asset_class), so it
    # fires for SPY/QQQ/IWM/DIA whether they arrive as 'index' or via the stock library,
    # and NEVER for a single name. Replaces the coin-flip center ONLY at a scored horizon;
    # for an index whose horizon is NOT validated it pins P(up)=0.5 (honest coin-flip).
    dir_block = None
    if asset in index_direction.PRESETS:
        try:
            dir_block = index_direction.forecast(close, asset=asset, gate=direction_gate(asset))
        except Exception:  # noqa: BLE001 — additive, never break the cone
            dir_block = None
    elif asset_class == "us_equity" and name_dir_inputs is not None:
        # single-name macro-transmission lean (real_rate duration), shared NAME_DIRECTION gate.
        # Reaches here only when that gate has a scored horizon (build_stock_library passes
        # inputs only then) → unscored/null is a pure coin-flip at zero per-name cost. Same
        # block shape as index_direction.forecast, so the assembly below is reused verbatim.
        try:
            from engine import name_direction
            dir_block = name_direction.forecast(
                close, inputs=name_dir_inputs.get("inputs"),
                gate=name_dir_inputs.get("gate"),
                dur_prior=float(name_dir_inputs.get("dur_prior", 0.0) or 0.0))
        except Exception:  # noqa: BLE001 — additive, never break the cone
            dir_block = None

    # assemble per-horizon
    H = {}
    for name, (lo_td, hi_td, rep) in horizons.items():
        c = cone["horizons"].get(name, {})
        p_up, n_cell, _cell = forward_dist.cond_up_prob(close, cell_key, rep)
        thin = bool(c.get("thin", True) or c.get("n", 0) < 150)
        long_underpowered = (name == "long" and asset_class in ("us_equity", "index")
                             and (close.index[-1] - close.index[0]).days / 365.25 < 25)
        rq = c.get("ret_q")
        dh = (dir_block or {}).get("horizons", {}).get(name)
        dir_scored = bool(dh and dh.get("scored"))
        if dh is not None and name != "short":
            p_up = dh["p_up"]                          # index: validated center, else 0.5 (coin-flip)
            if dir_scored and rq and dh.get("r_hat") is not None:
                shift = dh["r_hat"] - rq.get("p50", 0.0)
                rq = {k: round(v + shift, 2) for k, v in rq.items()}   # recenter to r̂; WIDTH unchanged
        direction = ("coin-flip" if name == "short" else
                     (dh["direction"] if dir_scored else
                      ("up-lean" if p_up > 0.52 else ("down-lean" if p_up < 0.48 else "neutral"))))
        H[name] = {
            "range_td": [lo_td, hi_td], "window_td": rep,
            "p_up": round(p_up, 3), "conviction": _conviction(p_up, name),
            "direction": direction, "direction_scored": dir_scored,
            "ret_q": rq, "dd_avg": c.get("dd_avg"), "dd_tail": c.get("dd_tail"),
            "mfe_med": c.get("mfe_med"), "cell_n": c.get("n", 0), "thin": thin,
            "underpowered": bool(long_underpowered),
            "r_hat": (dh or {}).get("r_hat") if dir_scored else None,
            "oos_r2": (dh or {}).get("oos_r2") if dir_scored else None,
            "dir_legs": (dh or {}).get("used") if dir_scored else None,
        }

    # vol cone width (annualized HAR-style estimate)
    cone_vol = vol_forecast.cone_vol_ann(close)
    cv = float(cone_vol.iloc[-1]) if cone_vol.notna().any() else None

    # market overlay (validated GO macro legs: credit / conditions) — widens the cone,
    # never touches direction
    macro = macro_overlay(macro_frame, gate, as_of) if macro_frame is not None else None

    # drivers: GO legs scored, the rest display-only — sorted by |current oriented z|
    go = {k for k, v in (gate or {}).items() if v == "GO"}
    drivers = []
    for leg in ("vol_pct", "neg_trend_vel", "rvar_vel", "confluence", "det_z",
                "neg_trend_accel", "neg_rs_vel", "neg_impulse", "ext_z"):
        if leg not in L:
            continue
        val = L[leg].iloc[-1]
        if pd.isna(val):
            continue
        v = float(val if leg != "vol_pct" else (val - 0.5) * 4)
        en, zh = _DRIVER_LABEL.get(leg, (leg, leg))
        drivers.append({"axis": leg, "value": round(v, 2), "sign": int(np.sign(v)),
                        "scored": leg in go, "display_only": leg not in go,
                        "label": {"en": en, "zh": zh}})
    # macro drivers (validated GO market legs) lead the list when present
    macro_drivers = (macro or {}).get("drivers", [])
    for d in macro_drivers:
        d["sign"] = int(np.sign(d["value"]))
    drivers.sort(key=lambda d: -abs(d["value"]))
    drivers = macro_drivers + drivers

    scored_h = [n for n, h in H.items() if h.get("direction_scored")]
    dir_trust = (f"scored (Clark-West OOS-R²>0, calibrated) at {', '.join(scored_h)}" if scored_h
                 else "display-only (measured coin-flip)")
    out = {
        "asset": asset, "asset_class": asset_class, "as_of": as_of,
        "anticipation_index": round(idx_pct, 1) if idx_pct is not None else None,
        "index_band": index_band, "confluence_value": round(idx_val, 3) if idx_val is not None else None,
        "n_go_legs": len(go),
        "vol_cone_ann": round(cv, 3) if cv is not None else None,
        "horizons": H,
        "drivers": drivers[:8],
        "direction_trust": dir_trust,
        "guards": {"short_direction": "coin-flip",
                   "direction": ("scored at " + ", ".join(scored_h)) if scored_h else "display-only",
                   "scored_legs": sorted(go), "display_only_until_go": True},
        "caveats": [
            ("Direction at " + ", ".join(scored_h) + " is a validated OOS lean; short stays a coin-flip."
             if scored_h else
             "Risk cone (drawdown/vol) is the validated read; DIRECTION is display-only (measured coin-flip)."),
            "Cone widens with horizon; downside tail is the forecastable left side.",
        ] + (["Long per-name cone is thin/under-powered — defer to the sector cone."]
             if H.get("long", {}).get("underpowered") else []),
        "trust": {"gate_scored": bool(go), "long_cell_n": H.get("long", {}).get("cell_n", 0)},
    }
    if macro:
        out["macro"] = {"stress_pct": macro["stress_pct"], "width_mult": macro["width_mult"],
                        "go_legs": macro["go_legs"]}
        if macro["stress_pct"] >= 70:
            out["caveats"].append("Market overlay: elevated credit/conditions stress — cone widened.")
    if dir_block and dir_block.get("horizons"):
        md = dir_block["horizons"].get("medium", {})
        out["direction_model"] = {"trust": dir_block.get("trust"),
                                  "medium_legs_used": md.get("used", []),
                                  "medium_oos_r2": md.get("oos_r2"), "medium_cw_p": md.get("cw_p")}
    return out
