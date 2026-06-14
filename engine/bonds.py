"""Bonds & bond-health engine — a health-first read of the bond market.

What the curve, credit, real rates, rates-vol and funding plumbing say about
economic health, market health, regime and cycle position. The output is BOTH a
human dashboard (scripts/build_bonds.py) and a machine-readable signal vector
(data/bonds/bond_health.json) for the cross-asset AI synthesis brain.

This module is HEALTH-FIRST, not a per-instrument trade vector. It reads the
shared macro feature frame (engine.inputs.build_features) and REUSES the already-
validated conditions layer (engine.conditions: recession_risk, drawdown_risk,
stock_bond_corr) rather than re-deriving it — then adds the bond-specific signal
families that layer does not compute:

  • Curve & growth   — 3m10y + the NY Fed recession probit, the near-term forward
                       spread (Engstrom-Sharpe, statistically beats 2s10s), the
                       term-premium-adjusted slope, the bull/bear x steepener/
                       flattener move taxonomy, and the un-inversion alarm.
  • Credit           — HY/IG OAS distress bands, the HY-IG ratio, the Moody's
                       Baa-Aaa deep-history gauge, and the monthly Excess Bond
                       Premium (the cleanest "smart-money" recession signal).
  • Real & inflation — TIPS real yields, breakevens (incl. 5y5y forward), and the
                       term premium (the 2023-25 repricing).
  • Stress & plumbing— the MOVE index (the "VIX of bonds") with stress bands and
                       a MOVE-leads-VIX flag, plus SOFR-IORB / repo-stress.
  • Cross-asset      — the stock-bond correlation regime ("is the hedge working?").
  • Cycle clock      — the curve x credit four-box rotation.
  • Health score     — a transparent 0..100 composite (higher = healthier) built
                       from the MEASURED recession/drawdown gauges + the credit/
                       vol/plumbing stress reads. NOT tuned to a backtest; the
                       weighting is a documented prior pending calibration
                       (scripts/calibrate_bonds.py, Phase 4).

Everything degrades gracefully — a missing input drops out of its composite (the
renormalize-over-available pattern from engine.conditions), the run never crashes.
See research/BOND_HEALTH_DASHBOARD.md.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from engine import conditions
from engine.indicators import pct_rank_window
from lib import config, store


# --- small helpers -----------------------------------------------------------
def _col(f: pd.DataFrame, name: str) -> pd.Series | None:
    if name not in f.columns or f[name].isna().all():
        return None
    return f[name]


def _last(s: pd.Series | None) -> float | None:
    if s is None:
        return None
    s = s.dropna()
    return float(s.iloc[-1]) if len(s) else None


def _z(s: pd.Series, window: int) -> pd.Series:
    m = s.rolling(window, min_periods=window // 4).mean()
    sd = s.rolling(window, min_periods=window // 4).std()
    return (s - m) / sd.replace(0, np.nan)


def _norm_cdf(x: float) -> float:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return float("nan")
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _interp(xs: list[float], ys: list[float], v: float | None) -> float:
    """Clamped piecewise-linear map (for the stress bands). Missing -> NaN (so a
    .map() over a numeric series stays float dtype, not object)."""
    if v is None or pd.isna(v):
        return float("nan")
    return float(np.interp(v, xs, ys))


# --- pillar primitives (each returns a causal Series or scalar) --------------
def ny_fed_recession_prob(spread_10y3m: pd.Series, cfg: dict) -> pd.Series:
    """Estrella-Mishkin / NY Fed probit on the 10y-3m spread (pp): the canonical
    12-month-ahead recession probability. P = Phi(a + b*spread)."""
    z = cfg["nyfed_a"] + cfg["nyfed_b"] * spread_10y3m
    return z.map(_norm_cdf)


def near_term_forward_spread(f: pd.DataFrame) -> pd.Series | None:
    """Engstrom-Sharpe near-term forward spread: the implied 3-month Treasury rate
    ~6 quarters (18 months) ahead minus the current 3-month bill. Inverts when the
    market prices Fed cuts — i.e. when growth is breaking. A -1sd (~-80bp) move
    raises 12m recession probability ~35pp; the 10y-2y spread's coefficient is not
    statistically different from zero once this is in the model (Fed, 2018).

    We bootstrap the forward from the par curve: y(1.5) and y(1.75) are linear
    interpolations between the 1y and 2y nodes (both targets lie in [1,2]), and the
    3m-rate-1.5y-forward = (y1.75*1.75 - y1.5*1.5)/0.25. Coupon effects under 2y are
    negligible (par ~= zero), so this is a faithful free-data approximation."""
    y1, y2, y3m = _col(f, "us1y"), _col(f, "us2y"), _col(f, "us3m")
    if y1 is None or y2 is None or y3m is None:
        return None
    y15 = y1 + 0.50 * (y2 - y1)
    y175 = y1 + 0.75 * (y2 - y1)
    fwd = (y175 * 1.75 - y15 * 1.50) / 0.25
    return fwd - y3m


_TAXONOMY = {
    "bull_steepener": ("Bull steepener", "牛市陡峭",
                       "short rates falling faster than long — the market is pricing Fed cuts",
                       "短端利率下行快于长端 — 市场在为美联储降息定价"),
    "bull_flattener": ("Bull flattener", "牛市平坦",
                       "long rates falling faster than short — growth/inflation fears pulling the long end",
                       "长端利率下行快于短端 — 增长/通胀担忧压低长端"),
    "bear_steepener": ("Bear steepener", "熊市陡峭",
                       "long rates rising faster than short — reflation / term-premium / fiscal repricing",
                       "长端利率上行快于短端 — 再通胀/期限溢价/财政重新定价"),
    "bear_flattener": ("Bear flattener", "熊市平坦",
                       "short rates rising faster than long — a hawkish Fed; classic late-cycle tightening",
                       "短端利率上行快于长端 — 鹰派美联储；典型的周期晚段紧缩"),
}


def curve_move_taxonomy(f: pd.DataFrame, window: int) -> tuple[str | None, pd.Series | None]:
    """Classify the recent curve move into bull/bear x steepener/flattener. Returns
    (latest_key, per-day key Series). Bull/bear by the 10y direction; steepener/
    flattener by the 2s10s slope change."""
    y2, y10 = _col(f, "us2y"), _col(f, "us10y")
    if y2 is None or y10 is None:
        return None, None
    dlong = y10 - y10.shift(window)
    slope = y10 - y2
    dslope = slope - slope.shift(window)
    direction = np.where(dlong > 0, "bear", "bull")
    shape = np.where(dslope > 0, "steepener", "flattener")
    key = pd.Series([f"{d}_{s}" for d, s in zip(direction, shape)], index=f.index)
    key = key.where(dlong.notna() & dslope.notna())
    last = key.dropna()
    return (last.iloc[-1] if len(last) else None), key


def uninversion(spread: pd.Series, lookback: int) -> tuple[bool, pd.Series]:
    """Un-inversion alarm: the curve dis-inverting AFTER a prior inversion. The
    dis-inversion leads recession by ~66 days on average (vs ~334d from the first
    inversion), so it is the genuinely ominous configuration. Returns (latest flag,
    per-day flag Series)."""
    inverted = spread < 0
    was_inv = inverted.rolling(lookback, min_periods=1).max().astype(bool)
    # un-inverted today = positive now AND inverted somewhere in the lookback AND
    # inverted as recently as ~1 month ago (so it is a fresh dis-inversion).
    recent_inv = inverted.rolling(21, min_periods=1).max().shift(1).fillna(False).astype(bool)
    flag = (spread >= 0) & was_inv & recent_inv
    return bool(flag.iloc[-1]) if len(flag) else False, flag


def _hy_band(oas: float | None, cfg: dict) -> str | None:
    if oas is None:
        return None
    if oas < cfg["hy_tight"]:
        return "tight"
    if oas < cfg["hy_elevated"]:
        return "normal"
    if oas < cfg["hy_distress"]:
        return "elevated"
    if oas < cfg["hy_crisis"]:
        return "distress"
    return "crisis"


def _move_band(move: float | None, cfg: dict) -> str | None:
    if move is None:
        return None
    if move < cfg["move_calm"]:
        return "calm"
    if move < cfg["move_elevated"]:
        return "normal"
    if move < cfg["move_crisis"]:
        return "elevated"
    return "crisis"


# stress maps (0 = no stress, 100 = max). Documented practitioner band knots.
def _hy_stress(oas):
    return _interp([2, 3, 5, 8, 10, 12], [0, 20, 50, 80, 90, 100], oas)


def _move_stress(move):
    return _interp([50, 80, 120, 150, 200], [0, 30, 65, 85, 100], move)


def _plumbing_stress(sofr_iorb_bp):
    return _interp([-5, 0, 5, 15, 30], [0, 20, 50, 80, 100], sofr_iorb_bp)


def _cycle_phase(curve: float | None, hy_pctile: float | None, hy_dir: str | None,
                 cfg: dict) -> str | None:
    """The curve x credit four-box clock. curve = 10y-3m (pp); hy_pctile = HY OAS
    2y percentile; hy_dir = 'widening'|'tightening'."""
    if curve is None or hy_pctile is None:
        return None
    wide = hy_pctile >= cfg["oas_high_third"]
    tight = hy_pctile <= cfg["oas_low_third"]
    flat_or_inv = curve < cfg["flat_level"]   # 10y-3m below the ~median slope = flat/inverted
    if wide:
        return "recession" if hy_dir == "widening" else "early"
    if tight:
        return "late" if (flat_or_inv or hy_dir == "widening") else "mid"
    # middle credit band — break the tie on the curve + credit direction
    if hy_dir == "widening":
        return "late"
    return "late" if flat_or_inv else "mid"


# --- the bond-health time series (for charts + alerts) -----------------------
def bonds_frame(f: pd.DataFrame) -> pd.DataFrame:
    """Daily time series of the bond-health signals + the composite score."""
    bcfg = config.load()["bonds"]
    cond = conditions.conditions_frame(f)            # reuse the validated layer
    out = pd.DataFrame(index=f.index)

    # carry through the reusable conditions legs (already causal, no look-ahead)
    for src, dst in [("recession_risk", "recession_risk"), ("drawdown_risk", "drawdown_risk"),
                     ("stock_bond_corr", "stock_bond_corr"), ("curve_tp_adj", "curve_tp_adj")]:
        if src in cond.columns:
            out[dst] = cond[src]

    # --- curve & growth ------------------------------------------------------
    s10y3m = _col(f, "spread_10y3m")
    if s10y3m is not None:
        out["spread_10y3m"] = s10y3m
        out["nyfed_prob"] = ny_fed_recession_prob(s10y3m, bcfg["curve"])
    if "spread_2s10s" in f:
        out["spread_2s10s"] = f["spread_2s10s"]
    ntfs = near_term_forward_spread(f)
    if ntfs is not None:
        out["ntfs"] = ntfs
    _, tax = curve_move_taxonomy(f, bcfg["curve"]["move_window_d"])
    if tax is not None:
        out["curve_move"] = tax
    if s10y3m is not None:
        _, uflag = uninversion(s10y3m, bcfg["curve"]["uninvert_lookback_d"])
        out["uninversion"] = uflag

    # --- credit --------------------------------------------------------------
    hy, ig = _col(f, "hy_oas"), _col(f, "ig_oas")
    if hy is not None:
        out["hy_oas"] = hy
        out["hy_pctile"] = pct_rank_window(hy, bcfg["cycle"]["oas_lookback_d"])
    if ig is not None:
        out["ig_oas"] = ig
    if hy is not None and ig is not None:
        out["hy_ig_ratio"] = hy / ig.replace(0, np.nan)
    baa, aaa = store.read("fred", "DBAA"), store.read("fred", "DAAA")
    if baa is not None and aaa is not None:
        ba = (baa.iloc[:, 0].reindex(f.index).ffill(limit=5)
              - aaa.iloc[:, 0].reindex(f.index).ffill(limit=5))
        out["baa_aaa"] = ba
    ebp = _col(f, "ebp")
    if ebp is not None:
        out["ebp"] = ebp

    # --- real & inflation ----------------------------------------------------
    for col in ["us10y_real", "us5y_real", "breakeven_10y", "breakeven_5y",
                "breakeven_5y5y", "term_premium_10y"]:
        s = _col(f, col)
        if s is not None:
            out[col] = s

    # --- stress & plumbing ---------------------------------------------------
    move = _col(f, "move")
    if move is not None:
        out["move"] = move
        out["move_pctile"] = pct_rank_window(move, bcfg["rates_vol"]["z_window_d"])
    sofr = store.read("fred", "SOFR")
    iorb = store.read("fred", "IORB")
    if sofr is not None and iorb is not None:
        si = (sofr.iloc[:, 0].reindex(f.index).ffill(limit=5)
              - iorb.iloc[:, 0].reindex(f.index).ffill(limit=5)) * 100.0   # -> bp
        out["sofr_iorb_bp"] = si
    sofr99 = store.read("fred", "SOFR99")
    if sofr is not None and sofr99 is not None:
        out["repo_spike_bp"] = (sofr99.iloc[:, 0].reindex(f.index).ffill(limit=5)
                                - sofr.iloc[:, 0].reindex(f.index).ffill(limit=5)) * 100.0

    # --- composite health score (0..100, higher = healthier) -----------------
    w = bcfg["health"]["weights"]
    legs: dict[str, tuple[pd.Series, float]] = {}
    if "recession_risk" in out:
        legs["recession"] = (out["recession_risk"].clip(0, 100), w["recession"])
    if "drawdown_risk" in out:
        legs["drawdown"] = (out["drawdown_risk"].clip(0, 100), w["drawdown"])
    if "hy_oas" in out:
        legs["credit"] = (out["hy_oas"].map(_hy_stress), w["credit"])
    if "move" in out:
        legs["rates_vol"] = (out["move"].map(_move_stress), w["rates_vol"])
    if "sofr_iorb_bp" in out:
        legs["plumbing"] = (out["sofr_iorb_bp"].map(_plumbing_stress), w["plumbing"])
    if legs:
        num = sum(s.fillna(0) * wt for s, wt in legs.values())
        den = sum(s.notna().astype(float) * wt for s, wt in legs.values())
        stress = (num / den.replace(0, np.nan))
        out["health_score"] = (100.0 - stress).clip(0, 100)
        for name, (s, _wt) in legs.items():
            out[f"stress_{name}"] = s
    return out


# --- snapshot dict (latest.json + bond_health.json + panels) -----------------
def _dir_word(s: pd.Series | None, window: int = 20) -> str | None:
    """'widening'/'tightening' (or 'rising'/'falling') over `window` days."""
    if s is None:
        return None
    s = s.dropna()
    if len(s) <= window:
        return None
    return "widening" if s.iloc[-1] > s.iloc[-window] else "tightening"


def bonds_snapshot(f: pd.DataFrame, fr: pd.DataFrame | None = None) -> dict:
    bcfg = config.load()["bonds"]
    fr = fr if fr is not None else bonds_frame(f)
    row = fr.dropna(how="all").iloc[-1] if len(fr.dropna(how="all")) else pd.Series(dtype=float)

    def g(name):
        v = row.get(name)
        return None if v is None or pd.isna(v) else float(v)

    # --- curve & growth ------------------------------------------------------
    s10y3m = _col(f, "spread_10y3m")
    tax_key, _ = curve_move_taxonomy(f, bcfg["curve"]["move_window_d"])
    uninv = bool(g("uninversion")) if "uninversion" in fr else False
    bull_steepener_uninv = uninv and tax_key == "bull_steepener"
    tax = _TAXONOMY.get(tax_key, (tax_key, tax_key, "", ""))
    curve = {
        "spread_10y3m": g("spread_10y3m"),
        "spread_2s10s": g("spread_2s10s"),
        "curve_tp_adjusted": g("curve_tp_adj"),
        "ntfs": g("ntfs"),
        "ny_fed_recession_prob": g("nyfed_prob"),
        "inverted": (None if g("spread_10y3m") is None else g("spread_10y3m") < 0),
        "tp_adj_inverted": (None if g("curve_tp_adj") is None else g("curve_tp_adj") < 0),
        "move_taxonomy": tax_key,
        "move_taxonomy_en": tax[0], "move_taxonomy_zh": tax[1],
        "move_taxonomy_note_en": tax[2], "move_taxonomy_note_zh": tax[3],
        "uninversion_alarm": uninv,
        "bull_steepener_uninversion": bull_steepener_uninv,
    }

    # --- credit --------------------------------------------------------------
    hy = g("hy_oas")
    hy_dir = _dir_word(_col(fr, "hy_oas"), bcfg["credit"]["widening_window_d"])
    credit = {
        "hy_oas": hy, "ig_oas": g("ig_oas"), "hy_ig_ratio": g("hy_ig_ratio"),
        "baa_aaa": g("baa_aaa"), "ebp": g("ebp"),
        "hy_pctile": g("hy_pctile"),
        "distress_band": _hy_band(hy, bcfg["credit"]),
        "direction": hy_dir,
    }

    # --- real & inflation ----------------------------------------------------
    real_inflation = {
        "real_10y": g("us10y_real"), "real_5y": g("us5y_real"),
        "breakeven_10y": g("breakeven_10y"), "breakeven_5y5y": g("breakeven_5y5y"),
        "term_premium": g("term_premium_10y"),
        "tp_repriced_positive": (None if g("term_premium_10y") is None
                                 else g("term_premium_10y") > 0),
    }

    # --- stress & plumbing ---------------------------------------------------
    move = g("move")
    move_z = _last(_z(_col(fr, "move"), bcfg["rates_vol"]["z_window_d"])) if "move" in fr else None
    vix_z = _last(_z(_col(f, "vix"), bcfg["rates_vol"]["z_window_d"])) if _col(f, "vix") is not None else None
    move_leads_vix = bool(move_z is not None and vix_z is not None and move_z > vix_z + 0.5)
    si_bp = g("sofr_iorb_bp")
    repo_bp = g("repo_spike_bp")
    stress = {
        "move": move, "move_band": _move_band(move, bcfg["rates_vol"]),
        "move_pctile": g("move_pctile"), "move_leads_vix": move_leads_vix,
        "sofr_iorb_bp": si_bp, "repo_spike_bp": repo_bp,
        "reserve_scarcity": (None if si_bp is None else si_bp > bcfg["plumbing"]["sofr_iorb_stress_bp"]),
        "repo_stress": (None if repo_bp is None else repo_bp > bcfg["plumbing"]["repo_spike_bp"]),
    }

    # --- cross-asset / regime ------------------------------------------------
    sb = g("stock_bond_corr")
    ccfg = config.load()["engine"]["conditions"]["corr"]
    cross_asset = {
        "stock_bond_corr": sb,
        "regime": (None if sb is None else
                   ("breakdown" if sb > ccfg["high"] else
                    ("diversifying" if sb < ccfg["low"] else "mixed"))),
        "hedge_working": (None if sb is None else sb < ccfg["low"]),
    }

    # --- cycle phase ---------------------------------------------------------
    phase = _cycle_phase(g("spread_10y3m"), g("hy_pctile"), hy_dir, bcfg["cycle"])

    # --- composite health ----------------------------------------------------
    hs = g("health_score")
    hcfg = bcfg["health"]
    health_label = (None if hs is None else
                    ("healthy" if hs >= hcfg["healthy_score"] else
                     ("stressed" if hs < hcfg["stressed_score"] else "mixed")))

    snap = {
        "as_of": fr.dropna(how="all").index.max().strftime("%Y-%m-%d") if len(fr.dropna(how="all")) else None,
        "health_score": None if hs is None else round(hs),
        "health_label": health_label,
        "cycle_phase": phase,
        "recession_risk": g("recession_risk"),
        "drawdown_risk": g("drawdown_risk"),
        "pillars": {
            "curve": curve, "credit": credit, "real_inflation": real_inflation,
            "stress": stress, "cross_asset": cross_asset,
        },
        "stress_legs": {k.replace("stress_", ""): g(k) for k in fr.columns
                        if k.startswith("stress_") and g(k) is not None},
    }
    snap["alarms"] = _alarms(snap)
    snap["verdict_en"], snap["verdict_zh"] = _verdict(snap)
    snap["drivers_for"] = _drivers_for(snap)
    return snap


# --- synthesis: alarms, verdict, cross-asset hand-off ------------------------
def _alarms(s: dict) -> list[dict]:
    """The transition triggers that are firing — the high-signal watch-items."""
    out = []
    c, cr, st = s["pillars"]["curve"], s["pillars"]["credit"], s["pillars"]["stress"]
    if c.get("bull_steepener_uninversion"):
        out.append({"key": "uninversion", "severity": "high",
                    "en": "Bull-steepening un-inversion — the curve dis-inverted while short rates fall; "
                          "historically the ~66-day pre-recession configuration.",
                    "zh": "牛市陡峭式解除倒挂 — 收益率曲线在短端利率下行时解除倒挂；历史上是衰退前约66天的形态。"})
    elif c.get("uninversion_alarm"):
        out.append({"key": "uninversion", "severity": "medium",
                    "en": "Curve un-inverted after a prior inversion — the dis-inversion, not the inversion, "
                          "tends to lead recession.",
                    "zh": "曲线在此前倒挂后解除 — 引领衰退的往往是解除倒挂而非倒挂本身。"})
    if cr.get("distress_band") in ("distress", "crisis"):
        out.append({"key": "credit_distress", "severity": "high",
                    "en": f"High-yield credit at {cr.get('distress_band')} levels (OAS {cr.get('hy_oas')}%).",
                    "zh": f"高收益信用利差处于{('危机' if cr.get('distress_band')=='crisis' else '困境')}水平（OAS {cr.get('hy_oas')}%）。"})
    elif cr.get("distress_band") == "elevated" and cr.get("direction") == "widening":
        out.append({"key": "credit_widening", "severity": "medium",
                    "en": "Credit spreads widening from tight levels — the early-warning the 'smart money' sends first.",
                    "zh": "信用利差自偏紧水平扩大 — “聪明钱”最先发出的预警。"})
    if st.get("move_band") == "crisis":
        out.append({"key": "rates_vol", "severity": "high",
                    "en": f"MOVE in crisis territory ({st.get('move')}) — systemic rates-vol stress.",
                    "zh": f"MOVE 指数处于危机区间（{st.get('move')}）— 系统性利率波动压力。"})
    elif st.get("move_leads_vix"):
        out.append({"key": "rates_vol", "severity": "medium",
                    "en": "Rates volatility (MOVE) leading equity volatility (VIX) — stress often transmits this way.",
                    "zh": "利率波动（MOVE）领先股票波动（VIX）— 压力常以此路径传导。"})
    if st.get("repo_stress"):
        out.append({"key": "plumbing", "severity": "high",
                    "en": "Repo-stress spike (SOFR 99th pctile) — funding plumbing under strain.",
                    "zh": "回购市场承压（SOFR 第99百分位跳升）— 资金管道紧张。"})
    elif st.get("reserve_scarcity"):
        out.append({"key": "plumbing", "severity": "medium",
                    "en": "SOFR drifting above IORB — creeping reserve scarcity in the funding markets.",
                    "zh": "SOFR 持续高于准备金利率 — 资金市场准备金趋于稀缺。"})
    return out


_PHASE_WORD = {"recession": ("recession", "衰退"), "early": ("early-cycle recovery", "周期早段复苏"),
               "mid": ("mid-cycle", "周期中段"), "late": ("late-cycle", "周期晚段")}


def _verdict(s: dict) -> tuple[str, str]:
    """A one-line synthesis composed from the pillar states (bilingual at source)."""
    c, cr, st = s["pillars"]["curve"], s["pillars"]["credit"], s["pillars"]["stress"]
    phase = s.get("cycle_phase")
    pw_en, pw_zh = _PHASE_WORD.get(phase, (phase or "—", phase or "—"))
    health = s.get("health_label") or "—"
    health_zh = {"healthy": "健康", "mixed": "中性", "stressed": "承压"}.get(health, health)

    en = [f"Bond health {health} ({s.get('health_score')}/100), {pw_en}."]
    zh = [f"债券健康度{health_zh}（{s.get('health_score')}/100），{pw_zh}。"]
    # curve
    if c.get("inverted") is False and c.get("uninversion_alarm"):
        en.append("Curve un-inverted (watch the dis-inversion).")
        zh.append("曲线已解除倒挂（留意解除倒挂信号）。")
    elif c.get("tp_adj_inverted"):
        en.append("Term-premium-adjusted curve inverted.")
        zh.append("期限溢价调整后的曲线倒挂。")
    elif c.get("inverted") is False:
        en.append("Curve positively sloped.")
        zh.append("曲线正向倾斜。")
    # credit
    band = cr.get("distress_band")
    if band:
        bw = {"tight": "credit tight", "normal": "credit normal", "elevated": "credit elevated",
              "distress": "credit distressed", "crisis": "credit in crisis"}.get(band, band)
        bz = {"tight": "信用偏紧", "normal": "信用正常", "elevated": "信用利差升高",
              "distress": "信用困境", "crisis": "信用危机"}.get(band, band)
        en.append(f"{bw[0].upper()}{bw[1:]}.")
        zh.append(f"{bz}。")
    # rates vol
    mb = st.get("move_band")
    if mb:
        mw = {"calm": "rates-vol calm", "normal": "rates-vol normal",
              "elevated": "rates-vol elevated", "crisis": "rates-vol in crisis"}.get(mb, mb)
        mz = {"calm": "利率波动平静", "normal": "利率波动正常",
              "elevated": "利率波动升高", "crisis": "利率波动危机"}.get(mb, mb)
        en.append(f"{mw[0].upper()}{mw[1:]}.")
        zh.append(f"{mz}。")
    return " ".join(en), "".join(zh)


def _drivers_for(s: dict) -> dict:
    """The explicit cross-asset hand-off: what bonds imply for each other dashboard.
    This is the bond layer's contribution to the holistic AI synthesis."""
    c = s["pillars"]["curve"]
    ri = s["pillars"]["real_inflation"]
    cr = s["pillars"]["credit"]
    st = s["pillars"]["stress"]
    risk_off = (cr.get("distress_band") in ("elevated", "distress", "crisis")
                or st.get("move_band") in ("elevated", "crisis"))
    return {
        "forex": {
            "note_en": "Rate differentials drive FX — the US 2y policy-path and the real-10y are the carry and "
                       "value anchors; a US-favorable widening vs foreign rates is a USD tailwind.",
            "real_10y": ri.get("real_10y"), "term_premium": ri.get("term_premium"),
        },
        "commodities": {
            "note_en": "Real-10y is gold's discount rate (inverse); breakevens track oil/energy; curve slope "
                       "proxies the growth impulse for copper/oil.",
            "real_10y": ri.get("real_10y"), "breakeven_10y": ri.get("breakeven_10y"),
        },
        "bitcoin": {
            "note_en": "BTC is a long-duration, real-rate-sensitive liquidity asset — falling real-10y + easing "
                       "plumbing is a tailwind; widening credit / rising MOVE is a risk-off gate.",
            "real_10y": ri.get("real_10y"), "risk_off_gate": risk_off,
        },
        "equities": {
            "note_en": "Discount-rate channel (real-10y, term premium) compresses long-duration multiples; "
                       "credit (HY OAS) is the canary that leads equity drawdowns; the SPEED of yield moves "
                       "(MOVE) matters more than the level.",
            "hy_oas": cr.get("hy_oas"), "credit_canary": cr.get("direction") == "widening",
            "stock_bond_corr": s["pillars"]["cross_asset"].get("stock_bond_corr"),
        },
    }
