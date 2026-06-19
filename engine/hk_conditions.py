"""Hong Kong risk-appetite / slowdown / drawdown conditioning layer.

An HK clone of engine/china_conditions.py (RORO composite, slowdown gauge,
drawdown gauge) + the Fear<->Euphoria synthesis, rebuilt on HK-native inputs. It
runs ALONGSIDE the split-half quad (engine/hk_regime.py) and gives the dashboard
a second, independent lens the price-based quad lacks.

HK has no own monetary policy — the HKD peg (7.75 strong / 7.85 weak) imports US
policy via HIBOR, HSI earnings are ~75% China-driven, and HK trades at ~2x the
Mainland's global-risk beta. So the HK legs blend three planes:
  • GLOBAL risk        — copper/gold, S&P, VIX, the dollar, EM equity (the
                         dominant high-frequency force; see engine/hk_global.py).
  • CHINA spillover     — southbound smart-money, the offshore yuan, M1-M2.
  • HK-LOCAL            — the HKD peg distance, HIBOR funding, VHSI fear, breadth,
                         the A/H premium.

Reads:
  • RORO composite      — equal-weight mean of available causal-z legs, signed so
                          +1 = risk-ON (fear / froth / weak-yuan / weak-side-peg
                          legs negated).
  • Slowdown gauge      — a 0..100 weighted-leg gauge (PMI vs 50, PPI deflation,
                          M1-M2 scissors, southbound drought, peg-funding stress,
                          GDP / industrial-production trend).
  • Drawdown risk       — an expanding rank-percentile of a z-mean of HK stress
                          (slowdown, VHSI level, peg stress, HIBOR spike, breadth
                          collapse).
  • Fear <-> Euphoria   — maps the RORO composite onto a rolling-5y 0-100
                          Panic/Fear/Neutral/Greed/Euphoria scale, decomposes the
                          signed legs and tallies cross-asset confirmation.

DISPLAY-ONLY INVARIANT: nothing here feeds engine/hk_axes.py, engine/hk_regime.py
or engine/hk_playbook.py. These are descriptive panels, NEVER scored signals. HK
history is short and globally coupled, so the slowdown + drawdown gauges ship
UNCALIBRATED (no measured forward-return claims; bands are the gauge's OWN
history-anchored percentiles). Everything degrades gracefully: a missing input
drops out of its composite and the read renormalizes (or returns None). Causal /
point-in-time only. Every human label carries an EN and a paired *_zh field.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.indicators import pct_rank_window
from lib import store

# --- z / percentile windows (trading days) -----------------------------------
Z_WINDOW = 252          # rolling-z lookback for the RORO legs (~1y)
DD_Z_LOOKBACK = 504     # drawdown-gauge z lookback (~2y)
FE_PCTILE_WINDOW = 252 * 5   # Fear<->Euphoria rolling-5y percentile
FE_MIN_HISTORY = int(252 * 2.5)   # need >=2.5y for a valid rolling-5y percentile


# --- small helpers (mirror engine/china_conditions.py) -----------------------
def _col(f: pd.DataFrame, name: str) -> pd.Series | None:
    if f is None or name not in f.columns or f[name].isna().all():
        return None
    return f[name]


def _z(s: pd.Series, window: int = Z_WINDOW) -> pd.Series:
    """Rolling z-score (causal — trailing mean/std only)."""
    m = s.rolling(window, min_periods=window // 4).mean()
    sd = s.rolling(window, min_periods=window // 4).std()
    return (s - m) / sd.replace(0, np.nan)


def _last(s: pd.Series | None) -> float | None:
    if s is None:
        return None
    s = s.dropna()
    return float(s.iloc[-1]) if len(s) else None


def _store_series(group: str, name: str, col: str) -> pd.Series | None:
    """Latest finite series for one store column, or None if missing/empty."""
    df = store.read(group, name)
    if df is None or df.empty or col not in df.columns:
        return None
    s = df[col].dropna()
    return s if len(s) else None


def _reindex(s: pd.Series, idx: pd.Index, ffill_limit: int | None = 5) -> pd.Series:
    """Align a (possibly lower-cadence) store series onto the feature index."""
    s = s[~s.index.duplicated(keep="last")].sort_index()
    union = idx.union(s.index)
    s = s.reindex(union)
    if ffill_limit:
        s = s.ffill(limit=ffill_limit)
    return s.reindex(idx)


def _round(v, n: int = 3):
    return None if v is None or not np.isfinite(v) else round(float(v), n)


def _peg_distance(f: pd.DataFrame) -> pd.Series | None:
    """HKD convertibility-band position (0 = 7.75 strong-side, 1 = 7.85 weak-side)
    reindexed onto f.index, via engine.hk_global.peg_frame. None if no USD/HKD."""
    u = _col(f, "usdhkd")
    if u is None:
        return None
    u = u.dropna()
    if u.empty:
        return None
    from engine import hk_global
    pf = hk_global.peg_frame(u)
    if pf.empty or "peg_distance" not in pf.columns:
        return None
    return _reindex(pf["peg_distance"], f.index, ffill_limit=5)


# --------------------------------------------------------------------------- #
# (1) RORO — HK risk-on/risk-off composite
# --------------------------------------------------------------------------- #
# Each leg is the SIGNED contribution exactly as it enters the equal-weight mean
# (fear / froth / weak-yuan / weak-side-peg legs negated). +1 = risk-ON. Stored as
# roro_<key> so a display-only decomposition can read them back and the test can
# assert mean(signed legs) == composite. NEVER scored.
_RORO_LEG_META = [
    ("copper_gold", "Copper / Gold", "铜／金 比"),
    ("spy", "S&P 500 (20d)", "标普500（20日）"),
    ("vix", "Volatility (VIX)", "波动率（VIX）"),
    ("dxy", "US Dollar (20d)", "美元（20日）"),
    ("eem", "EM equity (EEM)", "新兴市场股票"),
    ("usdcny", "Offshore yuan (20d)", "人民币（20日）"),
    ("southbound", "Southbound smart-money", "南向资金"),
    ("vhsi", "HK Volatility (VHSI)", "港股波动率（VHSI）"),
    ("breadth", "Breadth (% > 50d)", "市场宽度（>50日）"),
    ("peg", "HKD peg distance", "港元联汇距离"),
    ("ah_premium", "AH premium", "AH 溢价"),
    ("hibor", "HIBOR funding (20d Δ)", "HIBOR 资金（20日变动）"),
]


def roro_frame(f: pd.DataFrame) -> pd.DataFrame:
    """Daily signed-leg + composite RORO frame on f.index. Columns: roro_<key>
    per available leg and roro = tanh(equal-weight mean of those legs). NaN-tolerant:
    a missing leg drops out of the row mean."""
    out = pd.DataFrame(index=f.index)
    idx = f.index
    legs: dict[str, pd.Series] = {}

    # + copper/gold ratio z (risk-on industrial-vs-haven)
    cu = _store_series("yahoo", "HG=F", "close")
    au = _store_series("yahoo", "GC=F", "close")
    if cu is not None and au is not None:
        cg = (_reindex(cu, idx, None) / _reindex(au, idx, None)).ffill(limit=5)
        legs["copper_gold"] = _z(cg)

    # + S&P 500 20d momentum z (HK's dominant global-risk driver)
    spy = _store_series("yahoo", "SPY", "close")
    if spy is not None:
        legs["spy"] = _z(_reindex(spy, idx).pct_change(20, fill_method=None))

    # - VIX z (global fear)
    vix = _store_series("yahoo", "^VIX", "close")
    if vix is not None:
        legs["vix"] = -_z(_reindex(vix, idx))

    # - US dollar 20d move (a stronger dollar drains HK / EM liquidity)
    dxy = _store_series("yahoo", "DX-Y.NYB", "close")
    if dxy is not None:
        legs["dxy"] = -_z(_reindex(dxy, idx).pct_change(20, fill_method=None))

    # + EM equity 20d momentum z (HK is an EM-beta proxy)
    eem = _store_series("hk", "EEM", "close")
    if eem is not None:
        legs["eem"] = _z(_reindex(eem, idx).pct_change(20, fill_method=None))

    # - offshore yuan 20d move (a WEAKER yuan = higher USDCNY = China risk-off spillover)
    cny = _store_series("china", "CNY=X", "close")
    if cny is not None:
        legs["usdcny"] = -_z(_reindex(cny, idx).pct_change(20, fill_method=None))

    # + southbound net z (mainland smart money IN). southbound_cum is the cumulative
    #   net; its daily diff is the net flow, z-scored. (Data starts 2014-11.)
    sbc = _col(f, "southbound_cum")
    if sbc is not None:
        legs["southbound"] = _z(sbc.diff())

    # - VHSI z (HK's own implied-vol fear gauge — replaces China's QVIX leg)
    vh = _col(f, "vhsi")
    if vh is not None:
        legs["vhsi"] = -_z(vh)

    # + breadth (% above 50d) z  (fallback: ad_line 20d slope z)
    b50 = _col(f, "pct_above_50")
    if b50 is not None:
        legs["breadth"] = _z(b50)
    else:
        ad = _col(f, "ad_line")
        if ad is not None:
            legs["breadth"] = _z(ad.diff(20))

    # - HKD peg distance z (toward the 7.85 weak side = outflow / HSI headwind)
    pd_ = _peg_distance(f)
    if pd_ is not None:
        legs["peg"] = -_z(pd_)

    # - AH premium z (mainland A-shares paying up over the HK-listed H twin = froth;
    #   the H/HK line is the cheaper way to own the same company). Often shallow on
    #   disk (~3y) -> drops out gracefully.
    try:
        from engine.hk_ah import ah_basket_series
        ah = ah_basket_series()
    except Exception:  # noqa: BLE001 — additive leg, never fatal
        ah = None
    if ah is not None and len(ah) >= 30:
        legs["ah_premium"] = -_z(_reindex(ah, idx).ffill(limit=5))

    # - HIBOR overnight 20d change (rising HK funding cost = tightening / risk-off)
    hib = _col(f, "hibor_on")
    if hib is not None:
        legs["hibor"] = -_z(hib.diff(20))

    if not legs:
        return out
    for k, s in legs.items():
        out[f"roro_{k}"] = s
    raw = pd.concat(list(legs.values()), axis=1).mean(axis=1)
    out["roro_raw"] = raw
    out["roro"] = np.tanh(raw)
    return out


def hk_roro(f: pd.DataFrame) -> dict:
    """RORO snapshot: composite roro in (-1,+1), a ±0.35-band state, and the latest
    signed per-leg contributions.

    INVARIANT (asserted in tests): the mean of the AVAILABLE signed legs equals the
    pre-tanh composite (roro_raw). The headline `roro` is tanh(roro_raw).
    DISPLAY-ONLY — gates nothing."""
    rf = roro_frame(f)
    out: dict = {"roro": None, "roro_raw": None, "roro_state": None}
    if "roro_raw" not in rf.columns:
        return out
    rr = rf["roro_raw"].dropna()
    if rr.empty:
        return out
    asof = rr.index[-1]                            # read EVERY leg at the composite's as-of date
    out["roro_raw"] = _round(float(rr.iloc[-1]))   # so the decomposition reconciles to the
    out["roro"] = _round(rf["roro"].get(asof))     # headline even when a feed lags (no cross-date mix)
    legs = {}
    for key, en, zh in _RORO_LEG_META:
        col = f"roro_{key}"
        v = rf[col].get(asof) if col in rf.columns else None
        if v is not None and not np.isfinite(v):
            v = None
        out[f"hk_roro_{key}"] = _round(v)
        if v is not None:
            legs[key] = {"key": key, "name_en": en, "name_zh": zh,
                         "value": _round(v),
                         "lean": "risk-on" if v > 0 else ("risk-off" if v < 0 else "neutral")}
    out["legs"] = list(legs.values())
    r = out["roro"]
    out["roro_state"] = (None if r is None else
                         ("risk-on" if r > 0.35 else ("risk-off" if r < -0.35 else "neutral")))
    return out


# --------------------------------------------------------------------------- #
# (2) Slowdown gauge — 0..100, UNCALIBRATED, display-only
# --------------------------------------------------------------------------- #
# HK-native weighted-leg score: each leg -> a [0,1] slowdown intensity (1 = maximal
# slowdown), renormalized weighted mean over available legs -> 0..100. HSI earnings
# are ~75% China-driven, so the macro legs lean on the Mainland prints, plus the two
# HK-native funding/flow legs. UNCALIBRATED: no measured forward-return mapping (HK
# history is short and globally coupled) — read as a NARRATIVE gauge. Bands are the
# gauge's OWN 33rd/66th history percentiles.
_REC_LEG_META = {
    "pmi": (1.2, "Manufacturing PMI", "制造业 PMI"),
    "ppi": (1.0, "PPI deflation", "PPI 通缩"),
    "m1_m2": (0.8, "M1−M2 scissors", "M1−M2 剪刀差"),
    "southbound_drought": (0.8, "Southbound outflow", "南向流出"),
    "peg_funding": (1.0, "Peg funding stress", "联汇资金压力"),
    "gdp": (1.0, "China GDP trend", "中国 GDP 趋势"),
    "indpro": (0.7, "China IP trend", "工业增加值趋势"),
}
_CALIB_NOTE = ("UNCALIBRATED display-only gauge — HK history is short and globally "
               "coupled, so no measured forward-drawdown edge is claimed; bands are the "
               "gauge's own history-anchored percentiles. Never scored.")
_CALIB_NOTE_ZH = ("未校准的展示性仪表 —— 香港历史短且与全球高度耦合，不声称任何前瞻回撤优势；"
                  "区间为该仪表自身的历史分位锚定。从不计入评分。")


def _recession_legs(f: pd.DataFrame) -> dict:
    """Per-leg [0,1] slowdown intensity Series (1 = slowdown-ward) + weight.
    SINGLE SOURCE OF TRUTH for both the 0..100 series and the snapshot."""
    idx = f.index
    legs: dict[str, dict] = {}

    def add(key, series01):
        w, en, zh = _REC_LEG_META[key]
        legs[key] = {"score": series01.clip(0, 1), "weight": w,
                     "label": en, "label_zh": zh}

    # Manufacturing PMI vs 50: below 50 = contraction. 47 -> 1, 53 -> 0.
    pmi = _col(f, "pmi_mfg")
    if pmi is not None:
        add("pmi", ((53.0 - pmi) / 6.0))

    # PPI YoY: deep negative = deflationary recession risk. -6% -> 1, +3% -> 0.
    ppi = _col(f, "ppi_yoy")
    if ppi is not None:
        add("ppi", ((3.0 - ppi) / 9.0))

    # M1−M2 scissors: NEGATIVE (M1 lagging M2) = liquidity not reaching the real
    # economy = slowdown. -8 -> 1, +4 -> 0.
    m1, m2 = _col(f, "m1_yoy"), _col(f, "m2_yoy")
    if m1 is not None and m2 is not None:
        add("m1_m2", ((4.0 - (m1 - m2)) / 12.0))

    # Southbound drought: low trailing-quarter net southbound flow = mainland bid
    # withdrawing from HK = slowdown-ward. Inverted expanding-percentile of the 63d
    # net. (Data starts 2014-11 -> renormalizes in.)
    sbc = _col(f, "southbound_cum")
    if sbc is not None:
        net63 = sbc.diff(63)
        if net63.notna().sum() >= 24:
            sb_pct = net63.expanding(min_periods=24).rank(pct=True)
            add("southbound_drought", (1.0 - sb_pct))

    # Peg funding stress (HK-native): toward the 7.85 weak side = capital outflow /
    # HKMA draining the Aggregate Balance = tightening. peg_distance is already 0..1.
    pd_ = _peg_distance(f)
    if pd_ is not None:
        add("peg_funding", pd_)

    # China GDP YoY trend: lower = slowdown. 3% -> 1, 7% -> 0. GDP is QUARTERLY, so
    # ffill a full quarter + release lag (130td, matching china_inputs.gdp_yoy) — a
    # shorter limit would silently drop this weight-1.0 leg in the tail of each quarter.
    gdp = _store_series("china_macro", "gdp", "gdp_yoy")
    if gdp is not None:
        add("gdp", _reindex((7.0 - gdp) / 4.0, idx, ffill_limit=130))

    # China industrial-production YoY trend: lower = slowdown. 2% -> 1, 7% -> 0.
    ip = _store_series("china_macro", "indpro", "indpro_yoy")
    if ip is not None:
        add("indpro", _reindex((7.0 - ip) / 5.0, idx, ffill_limit=40))

    return legs


def _recession_score_series(f: pd.DataFrame) -> tuple[pd.Series, dict]:
    legs = _recession_legs(f)
    if not legs:
        return pd.Series(index=f.index, dtype=float), legs
    num = sum(d["score"].fillna(0) * d["weight"] for d in legs.values())
    den = sum(d["score"].notna().astype(float) * d["weight"] for d in legs.values())
    score = (100.0 * num / den.replace(0, np.nan)).clip(0, 100)
    return score, legs


def _own_bands(series: pd.Series) -> tuple[float, float]:
    """33rd/66th percentile of the gauge's OWN history (history-anchored bands for
    an uncalibrated gauge). Falls back to 33/66 fixed if too thin."""
    s = series.dropna()
    if len(s) < 60:
        return (33.0, 66.0)
    return (round(float(s.quantile(0.33)), 1), round(float(s.quantile(0.66)), 1))


def hk_recession(f: pd.DataFrame) -> dict:
    """0..100 HK slowdown gauge (UNCALIBRATED, display-only) + a per-leg breakdown
    whose `points` sum to the headline (stacked-bar ready). Higher = more
    slowdown-ward. Renormalized over available legs. NEVER scored."""
    score, legs = _recession_score_series(f)
    sc = score.dropna()
    if sc.empty:
        return {"score": None, "label": None, "legs": [], "calibrated": False}
    asof = sc.index[-1]
    num = sum(d["score"].fillna(0) * d["weight"] for d in legs.values())
    den = sum(d["score"].notna().astype(float) * d["weight"] for d in legs.values())
    den_at = float(den.loc[asof]) if pd.notna(den.loc[asof]) and den.loc[asof] else None
    leg_rows = []
    for key, d in legs.items():
        si = d["score"].get(asof, np.nan)
        active = pd.notna(si)
        value = round(100.0 * float(si), 1) if active else None
        points = (round(100.0 * d["weight"] * float(si) / den_at, 1)
                  if active and den_at else None)
        leg_rows.append({"key": key, "label": d["label"], "label_zh": d["label_zh"],
                         "weight": d["weight"], "active": bool(active),
                         "value": value, "points": points})
    bands = _own_bands(sc)
    val = round(float(sc.iloc[-1]), 1)
    label = ("high" if val >= bands[1] else "elevated" if val >= bands[0] else "low")
    return {"score": val, "label": label, "legs": leg_rows, "calibrated": False,
            "bands": list(bands), "note": _CALIB_NOTE, "note_zh": _CALIB_NOTE_ZH}


# --------------------------------------------------------------------------- #
# (3) Drawdown-risk gauge — 0..100, UNCALIBRATED, display-only
# --------------------------------------------------------------------------- #
# Expanding rank-percentile of a z-mean of HK stress legs. UNCALIBRATED — no
# measured P(drawdown) claim.
def _drawdown_components(f: pd.DataFrame, rec_score: pd.Series) -> dict:
    """(z-Series, weight) per drawdown-stress leg, on f.index."""
    comps: dict[str, tuple[pd.Series, float]] = {}
    # slowdown gauge (already 0..100) — the macro-stress backbone
    if rec_score is not None and not rec_score.dropna().empty:
        comps["slowdown"] = (_z(rec_score, DD_Z_LOOKBACK), 1.0)
    # VHSI level (HK fear) — high implied vol = stress
    vh = _col(f, "vhsi")
    if vh is not None:
        comps["vhsi"] = (_z(vh, DD_Z_LOOKBACK), 0.8)
    # peg stress — toward the weak side = capital-flight fragility
    pd_ = _peg_distance(f)
    if pd_ is not None:
        comps["peg_stress"] = (_z(pd_, DD_Z_LOOKBACK), 0.6)
    # HIBOR spike — a funding squeeze precedes HK drawdowns
    hib = _col(f, "hibor_on")
    if hib is not None:
        comps["hibor_spike"] = (_z(hib, DD_Z_LOOKBACK), 0.5)
    # breadth collapse — fewer names participating = fragile
    b50 = _col(f, "pct_above_50")
    if b50 is not None:
        comps["breadth_collapse"] = (-_z(b50, DD_Z_LOOKBACK), 0.6)
    return comps


def _drawdown_score_series(f: pd.DataFrame, rec_score: pd.Series) -> pd.Series:
    comps = _drawdown_components(f, rec_score)
    if len(comps) < 2:
        return pd.Series(index=f.index, dtype=float)
    num = sum(z.fillna(0) * w for z, w in comps.values())
    den = sum(z.notna().astype(float) * w for z, w in comps.values())
    zmean = num / den.replace(0, np.nan)
    return (zmean.expanding(min_periods=252).rank(pct=True) * 100)


def hk_drawdown(f: pd.DataFrame, rec_score: pd.Series | None = None) -> dict:
    """0..100 HK drawdown-risk gauge (UNCALIBRATED, display-only): expanding
    rank-percentile of a z-mean of slowdown + VHSI + peg stress + HIBOR spike +
    breadth collapse. Higher = more fragile. NEVER scored."""
    if rec_score is None:
        rec_score, _ = _recession_score_series(f)
    series = _drawdown_score_series(f, rec_score).dropna()
    if series.empty:
        return {"score": None, "band": None, "calibrated": False}
    val = round(float(series.iloc[-1]), 1)
    band = ("extreme" if val >= 90 else "high" if val >= 75
            else "elevated" if val >= 50 else "low")
    return {"score": val, "band": band, "calibrated": False,
            "note": ("history-anchored rank-percentile of HK stress legs — uncalibrated, "
                     "display-only context, never scored"),
            "note_zh": ("香港压力腿的历史分位排名 —— 未校准，仅作展示性背景，从不计入评分")}


# --------------------------------------------------------------------------- #
# Fear <-> Euphoria synthesis (mirror engine/china_conditions.py _fe_* logic)
# --------------------------------------------------------------------------- #
def _fe_map(pct: float) -> int:
    return int(max(0, min(100, round(100 * float(pct)))))


def _fe_band(fe: int) -> tuple[str, str]:
    """Half-open band: panic<10 / fear<35 / neutral<65 / greed<90 / euphoria>=90."""
    if fe < 10:
        return "Panic", "恐慌"
    if fe < 35:
        return "Fear", "恐惧"
    if fe < 65:
        return "Neutral", "中性"
    if fe < 90:
        return "Greed", "贪婪"
    return "Euphoria", "欣喜"


def _fe_legs(rf: pd.DataFrame) -> list[dict]:
    """Per-leg decomposition of the RORO composite from the signed roro_<key>
    columns: latest signed contribution, its rolling-5y percentile, and a lean."""
    legs = []
    if "roro_raw" not in rf.columns:
        return legs
    raw = rf["roro_raw"].dropna()
    if raw.empty:
        return legs
    asof = raw.index[-1]
    for key, en, zh in _RORO_LEG_META:
        col = f"roro_{key}"
        if col not in rf.columns:
            continue
        sig = rf[col]
        val = sig.get(asof)
        if val is None or not np.isfinite(val):
            continue
        p = _last(pct_rank_window(sig.loc[:asof], FE_PCTILE_WINDOW))
        if p is None:                              # warm-up shortfall fallback
            p = _last(sig.loc[:asof].expanding(min_periods=20).rank(pct=True))
        legs.append({"key": key, "name_en": en, "name_zh": zh,
                     "value": round(float(val), 3),
                     "pct": _fe_map(p) if p is not None else 50,
                     "lean": "risk-on" if val > 0 else ("risk-off" if val < 0 else "neutral")})
    return legs


def _roro_confirmation(legs: list[dict]) -> dict | None:
    """Cross-asset confirmation tally over the signed RORO legs (the dispersion the
    headline mean hides). Majority-anchored; NEVER scored."""
    if not legs:
        return None
    on = [lg for lg in legs if lg["lean"] == "risk-on"]
    off = [lg for lg in legs if lg["lean"] == "risk-off"]
    n_on, n_off = len(on), len(off)
    total = n_on + n_off
    if total == 0:
        return None
    if n_on > n_off:
        direction, dir_zh, majority, minority = "risk-on", "偏好风险", on, off
    elif n_off > n_on:
        direction, dir_zh, majority, minority = "risk-off", "避险", off, on
    else:
        direction, dir_zh, majority, minority = "split", "对半分歧", on, off
    agree = len(majority)
    ratio = agree / total
    if direction == "split":
        verdict_en, verdict_zh = "divergent (split)", "背离（对半）"
    elif ratio >= 0.85:
        verdict_en, verdict_zh = "clean " + direction, "一致" + dir_zh
    elif ratio >= 0.70:
        verdict_en, verdict_zh = direction + ", not clean", dir_zh + "（不一致）"
    else:
        verdict_en, verdict_zh = "divergent (no consensus)", "背离（无共识）"

    def _lab(xs):
        return [{"key": lg["key"], "en": lg["name_en"], "zh": lg["name_zh"]} for lg in xs]

    return {"n_on": n_on, "n_off": n_off, "total": total, "agree": agree,
            "direction": direction, "confirmed_by": _lab(majority), "dissent": _lab(minority),
            "verdict_en": verdict_en, "verdict_zh": verdict_zh}


def fear_euphoria(f: pd.DataFrame | None = None) -> dict | None:
    """DISPLAY-ONLY HK Fear<->Euphoria synthesis. Maps the RORO composite to a
    rolling-5y 0-100 percentile, decomposes its signed legs and tallies cross-asset
    confirmation. NEVER scores; NEVER touches hk_axes / regime / playbook.

    Returns None only if no RORO composite can be built at all; degrades to an
    expanding percentile + 'warming up' note on short history."""
    if f is None:
        from engine.hk_inputs import build_features
        f = build_features()
    rf = roro_frame(f)
    if "roro" not in rf.columns or rf["roro_raw"].dropna().empty:
        return None
    raw = rf["roro_raw"].dropna()
    warming = len(raw) < FE_MIN_HISTORY
    if warming:
        pct = _last(rf["roro_raw"].expanding(min_periods=20).rank(pct=True))
    else:
        pct = _last(pct_rank_window(rf["roro_raw"], FE_PCTILE_WINDOW))
    legs = _fe_legs(rf)
    roro_state = hk_roro(f)
    if pct is None or not np.isfinite(pct):
        return {"fe_score": None, "band": None, "band_zh": None,
                "roro": roro_state["roro"], "roro_state": roro_state["roro_state"],
                "legs": legs, "confirmation": _roro_confirmation(legs),
                "warming_up": True, "history_days": int(len(raw))}
    fe = _fe_map(pct)
    band_en, band_zh = _fe_band(fe)
    return {"fe_score": fe, "band": band_en, "band_zh": band_zh,
            "roro": roro_state["roro"], "roro_state": roro_state["roro_state"],
            "legs": legs, "confirmation": _roro_confirmation(legs),
            "warming_up": warming, "history_days": int(len(raw))}


# --------------------------------------------------------------------------- #
# snapshot — the bundle the engine persists to latest['conditions']
# --------------------------------------------------------------------------- #
def _fe_history(rf: pd.DataFrame, last_days: int = 1100) -> dict:
    raw = rf["roro_raw"] if "roro_raw" in rf.columns else pd.Series(dtype=float)
    if raw.dropna().empty:
        return {"dates": [], "vals": []}
    if len(raw.dropna()) >= FE_MIN_HISTORY:
        pct = pct_rank_window(raw, FE_PCTILE_WINDOW)
    else:
        pct = raw.expanding(min_periods=20).rank(pct=True)
    s = (pct * 100).dropna()
    if last_days:
        s = s.loc[s.index.max() - pd.Timedelta(days=last_days):]
    return {"dates": [d.strftime("%Y-%m-%d") for d in s.index],
            "vals": [round(float(v), 1) for v in s]}


def _line_history(series: pd.Series, last_days: int = 1100, ndigits: int = 1) -> dict:
    s = series.dropna()
    if s.empty:
        return {"dates": [], "vals": []}
    if last_days:
        s = s.loc[s.index.max() - pd.Timedelta(days=last_days):]
    return {"dates": [d.strftime("%Y-%m-%d") for d in s.index],
            "vals": [round(float(v), ndigits) for v in s]}


def snapshot(f: pd.DataFrame | None = None, regime: pd.DataFrame | None = None) -> dict:
    """The DISPLAY-ONLY conditions bundle the HK engine persists to
    latest['conditions']: RORO composite + signed legs, the slowdown gauge + leg
    breakdown, the drawdown-risk gauge, and chart-ready {dates,vals} history for the
    RORO line, the slowdown line and the drawdown line.

    `regime` is accepted for signature parity but unused (this layer reads no regime
    labels). NEVER scored into hk_axes / hk_regime / hk_playbook."""
    if f is None:
        from engine.hk_inputs import build_features
        f = build_features()
    rf = roro_frame(f)
    rec_series, _legs = _recession_score_series(f)
    dd_series = _drawdown_score_series(f, rec_series)

    roro = hk_roro(f)
    recession = hk_recession(f)
    drawdown = hk_drawdown(f, rec_series)

    charts = {
        "roro": _line_history(rf["roro"], ndigits=3) if "roro" in rf.columns else {"dates": [], "vals": []},
        "recession": _line_history(rec_series, ndigits=1),
        "drawdown": _line_history(dd_series, ndigits=1),
        "fear_euphoria": _fe_history(rf),
    }
    return {
        "roro": roro,
        "recession": recession,
        "drawdown_risk": drawdown,
        "charts": charts,
        "display_only": True,
        "note": ("display-only conditioning lens — RORO + uncalibrated slowdown/drawdown gauges; "
                 "never feeds hk_axes / hk_regime / hk_playbook"),
    }
