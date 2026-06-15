"""China-native risk-appetite / recession / drawdown conditioning layer.

A China clone of engine/conditions.py (RORO composite, recession gauge,
drawdown gauge) + the scripts/build_site.py Fear<->Euphoria synthesis, rebuilt
on A-share-native inputs. It runs ALONGSIDE the split-half quad (engine/
china_regime.py) and gives the dashboard a second, independent lens the
price-based quad lacks:

  • RORO composite      — an equal-weight mean of available causal-z cross-asset
                          legs (copper/gold, breadth, southbound smart-money,
                          M1-M2 scissors, turnover band, QVIX fear, offshore
                          yuan, margin froth, AH premium), signed so +1 = risk-ON.
  • Recession / slowdown — a 0..100 China-native weighted-leg gauge (credit
                          impulse, PPI deflation, PMI vs 50, M1-M2 scissors,
                          property cycle, GDP trend).
  • Drawdown risk        — an expanding rank-percentile of a z-mean of macro
                          stress (slowdown, margin froth, flat CGB curve, QVIX
                          level, turnover mania). The PBoC pins the front end so
                          the curve is CONTEXT only (low weight).
  • Fear <-> Euphoria    — maps the RORO composite + key sub-pillars onto a
                          rolling-5y 0-100 Panic/Fear/Neutral/Greed/Euphoria
                          scale, decomposes the signed legs and tallies cross-
                          asset confirmation.

DISPLAY-ONLY INVARIANT: nothing in this module feeds engine/china_axes.py,
engine/china_regime.py or engine/china_playbook.py. These are descriptive
panels, NEVER scored signals. A-shares mean-revert and China history is short /
regime-unstable, so the recession + drawdown gauges are explicitly UNCALIBRATED
(no measured forward-return claims, unlike the US conditions.py). The RORO
composite gates nothing.

Everything degrades gracefully: a missing input drops out of its composite and
the affected read renormalizes (or returns None) — the run never crashes.
Causal / point-in-time only: rolling z-scores use trailing windows, percentiles
use expanding or trailing windows (no look-ahead). Every human-facing label
carries an EN and a paired *_zh / zh field.
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


# --- small helpers (mirror engine/conditions.py + china_internals.py) --------
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
    """Align a (possibly lower-cadence) store series onto the feature index.
    monthly / off-session prints survive via a union reindex, then ffill."""
    s = s[~s.index.duplicated(keep="last")].sort_index()
    union = idx.union(s.index)
    s = s.reindex(union)
    if ffill_limit:
        s = s.ffill(limit=ffill_limit)
    return s.reindex(idx)


# --------------------------------------------------------------------------- #
# (1) RORO — A-share risk-on/risk-off composite
# --------------------------------------------------------------------------- #
# Each leg below is the SIGNED contribution exactly as it enters the equal-weight
# mean (fear / froth / weak-yuan legs negated). +1 = risk-ON. The legs are stored
# as roro_<key> so a display-only decomposition can read them back and the test
# can assert mean(signed legs) == composite. NEVER scored.
_RORO_LEG_META = [
    ("copper_gold", "Copper / Gold", "铜／金 比"),
    ("breadth", "Breadth (% > 50d)", "市场宽度（>50日）"),
    ("southbound", "Southbound smart-money", "南向资金"),
    ("m1_m2", "M1−M2 scissors", "M1−M2 剪刀差"),
    ("turnover", "Turnover band", "成交活跃度"),
    ("qvix", "QVIX fear (300)", "QVIX 恐慌（300）"),
    ("usdcnh", "Offshore yuan (20d)", "离岸人民币（20日）"),
    ("margin", "Margin froth", "融资拥挤度"),
    ("ah_premium", "AH premium", "AH 溢价"),
]


def roro_frame(f: pd.DataFrame) -> pd.DataFrame:
    """Daily signed-leg + composite RORO frame on f.index. Columns: roro_<key>
    per available leg and roro = equal-weight mean of those legs (NaN-tolerant:
    a missing leg drops out of the row mean, so the composite always equals the
    mean of the legs PRESENT that day)."""
    out = pd.DataFrame(index=f.index)
    idx = f.index
    legs: dict[str, pd.Series] = {}

    # + copper/gold ratio z (risk-on industrial-vs-haven)
    cu = _store_series("yahoo", "HG=F", "close")
    au = _store_series("yahoo", "GC=F", "close")
    if cu is not None and au is not None:
        cg = (_reindex(cu, idx, None) / _reindex(au, idx, None)).ffill(limit=5)
        legs["copper_gold"] = _z(cg)

    # + breadth (% above 50d) z  (fallback: ad_line 20d slope z)
    b50 = _col(f, "pct_above_50")
    if b50 is not None:
        legs["breadth"] = _z(b50)
    else:
        ad = _col(f, "ad_line")
        if ad is not None:
            legs["breadth"] = _z(ad.diff(20))

    # + southbound net z (smart money IN). southbound_cum is the cumulative net;
    #   its daily diff is the net flow, z-scored.
    sbc = _col(f, "southbound_cum")
    if sbc is not None:
        legs["southbound"] = _z(sbc.diff())

    # + M1−M2 scissors (剪刀差): rising = liquidity flowing to transactional money
    m1, m2 = _col(f, "m1_yoy"), _col(f, "m2_yoy")
    if m1 is not None and m2 is not None:
        legs["m1_m2"] = _z(m1 - m2)

    # + turnover band z (whole-market 沪+深 daily turnover; the retail-activity gauge)
    turn = _market_turnover_series()
    if turn is not None:
        legs["turnover"] = _z(_reindex(turn, idx).ffill(limit=5))

    # - QVIX(300) z (fear)
    qv = _store_series("china_qvix", "qvix300", "close")
    if qv is not None:
        legs["qvix"] = -_z(_reindex(qv, idx).ffill(limit=5))

    # - offshore yuan 20d move (a WEAKER yuan = higher USDCNH = risk-off)
    cnh = _col(f, "usdcnh")
    if cnh is not None:
        legs["usdcnh"] = -_z(cnh.pct_change(20, fill_method=None))

    # - margin froth percentile (financing-as-%-of-float; crowding = fragile).
    #   percentile in [0,1] -> centred to [-0.5,0.5] so it sits on the z scale.
    fin = _store_series("china_margin", "balance", "fin_pct_float")
    if fin is not None:
        fin_d = _reindex(fin, idx).ffill(limit=5)
        legs["margin"] = -(pct_rank_window(fin_d, Z_WINDOW * 4) - 0.5)

    # - AH premium z (mainland paying up over HK = froth). Often unavailable
    #   (shallow on disk) -> drops out gracefully.
    ah = _store_series("china_flows", "ah_premium", "hsahp")
    if ah is not None and len(ah) >= 30:
        legs["ah_premium"] = -_z(_reindex(ah, idx).ffill(limit=5))

    if not legs:
        return out
    for k, s in legs.items():
        out[f"roro_{k}"] = s
    # squash the equal-weight mean of the available legs to (-1, +1) via tanh
    raw = pd.concat(list(legs.values()), axis=1).mean(axis=1)
    out["roro_raw"] = raw
    out["roro"] = np.tanh(raw)
    return out


def _market_turnover_series() -> pd.Series | None:
    """Whole-market daily turnover (亿元), derived for free from the margin data:
    margin_trade_amt / trade_amt_ratio * 100 (mirrors china_internals.market_turnover)."""
    dt = store.read("china_margin", "daily_trade")
    if dt is None or dt.empty or not {"margin_trade_amt", "trade_amt_ratio"}.issubset(dt.columns):
        return None
    ratio = dt["trade_amt_ratio"].where(dt["trade_amt_ratio"] > 0)
    turn = (dt["margin_trade_amt"] / ratio * 100).dropna()
    return turn if len(turn) else None


def china_roro(f: pd.DataFrame) -> dict:
    """RORO snapshot: composite roro in (-1,+1), a ±0.35-band state, and the
    latest signed per-leg contributions china_roro_<key>.

    INVARIANT (asserted in tests): the mean of the AVAILABLE signed legs equals
    the pre-tanh composite (roro_raw). The headline `roro` is tanh(roro_raw).
    DISPLAY-ONLY — gates nothing."""
    rf = roro_frame(f)
    out: dict = {"roro": None, "roro_raw": None, "roro_state": None}
    if "roro_raw" not in rf.columns:
        return out
    rr = rf["roro_raw"].dropna()
    if rr.empty:
        return out
    asof = rr.index[-1]                          # read EVERY leg at the composite's as-of date
    out["roro_raw"] = _round(float(rr.iloc[-1]))  # so the decomposition reconciles to the
    out["roro"] = _round(rf["roro"].get(asof))    # headline even when a feed lags (no cross-date mix)
    legs = {}
    for key, en, zh in _RORO_LEG_META:
        col = f"roro_{key}"
        v = rf[col].get(asof) if col in rf.columns else None
        if v is not None and not np.isfinite(v):
            v = None
        out[f"china_roro_{key}"] = _round(v)
        if v is not None:
            legs[key] = {"key": key, "name_en": en, "name_zh": zh,
                         "value": _round(v),
                         "lean": "risk-on" if v > 0 else ("risk-off" if v < 0 else "neutral")}
    out["legs"] = list(legs.values())
    r = out["roro"]
    out["roro_state"] = (None if r is None else
                         ("risk-on" if r > 0.35 else ("risk-off" if r < -0.35 else "neutral")))
    return out


def _round(v, n: int = 3):
    return None if v is None or not np.isfinite(v) else round(float(v), n)


# --------------------------------------------------------------------------- #
# (2) Recession / slowdown gauge — 0..100, UNCALIBRATED, display-only
# --------------------------------------------------------------------------- #
# China-native weighted-leg score: each leg -> a [0,1] slowdown intensity (1 =
# maximal slowdown / recession-ward), renormalized weighted mean over available
# legs -> 0..100. The leg breakdown mirrors equity_alloc.risk_legs for a stacked
# bar. UNCALIBRATED: no measured forward-return mapping (China history is too
# short / regime-unstable for the US-style backtest) — read as a NARRATIVE gauge.
_REC_LEG_META = {
    "credit_impulse": (1.4, "Credit impulse (社融)", "信用脉冲（社融）"),
    "ppi": (1.0, "PPI deflation", "PPI 通缩"),
    "pmi": (1.2, "Manufacturing PMI", "制造业 PMI"),
    "m1_m2": (0.8, "M1−M2 scissors", "M1−M2 剪刀差"),
    "property": (1.2, "Property cycle", "地产周期"),
    "gdp": (1.0, "GDP trend", "GDP 趋势"),
}


def _recession_legs(f: pd.DataFrame) -> dict:
    """Per-leg [0,1] slowdown intensity Series (1 = recession-ward) + weight.
    SINGLE SOURCE OF TRUTH for both the 0..100 series and the snapshot."""
    idx = f.index
    legs: dict[str, dict] = {}

    def add(key, series01):
        w, en, zh = _REC_LEG_META[key]
        legs[key] = {"score": series01.clip(0, 1), "weight": w,
                     "label": en, "label_zh": zh}

    # credit impulse: 12m %-change of trailing-12m TSF (china_internals.credit_tape).
    # LOW / falling impulse = slowdown. Map z<-? via a centred percentile so deep
    # negative impulse -> ~1. We invert an expanding percentile (low pctile = slow).
    tsf = store.read("china_credit", "tsf")
    if tsf is not None and not tsf.empty and "tsf_total" in tsf.columns:
        t = tsf["tsf_total"].dropna()
        if len(t) >= 24:
            impulse = (t.rolling(12).sum().pct_change(12) * 100).dropna()
            if len(impulse) >= 12:
                imp_pct = impulse.expanding(min_periods=12).rank(pct=True)
                add("credit_impulse", _reindex(1.0 - imp_pct, idx, ffill_limit=40))

    # PPI YoY: deep negative = deflationary recession risk. Map -6% -> 1, +3% -> 0.
    ppi = _col(f, "ppi_yoy")
    if ppi is not None:
        add("ppi", ((3.0 - ppi) / 9.0))

    # Manufacturing PMI vs 50: below 50 = contraction. 47 -> 1, 53 -> 0.
    pmi = _col(f, "pmi_mfg")
    if pmi is not None:
        add("pmi", ((53.0 - pmi) / 6.0))

    # M1−M2 scissors: NEGATIVE (M1 lagging M2) = liquidity not reaching the real
    # economy = slowdown. -8 -> 1, +4 -> 0.
    m1, m2 = _col(f, "m1_yoy"), _col(f, "m2_yoy")
    if m1 is not None and m2 is not None:
        sciss = m1 - m2
        add("m1_m2", ((4.0 - sciss) / 12.0))

    # Property cycle: home-price breadth diffusion (count rising − falling over 70
    # cities). Deeply negative breadth = contraction. -60 -> 1, +20 -> 0.
    hp = store.read("china_property", "home_price")
    if hp is not None and not hp.empty and "new_breadth" in hp.columns:
        nb = hp["new_breadth"].dropna()
        if len(nb):
            add("property", _reindex(((20.0 - nb) / 80.0), idx, ffill_limit=40))

    # GDP YoY trend: lower = slowdown. 3% -> 1, 7% -> 0 (post-2010 China band).
    gdp = _col(f, "gdp_yoy")
    if gdp is not None:
        add("gdp", ((7.0 - gdp) / 4.0))

    return legs


def _recession_score_series(f: pd.DataFrame) -> tuple[pd.Series, dict]:
    legs = _recession_legs(f)
    if not legs:
        return pd.Series(index=f.index, dtype=float), legs
    num = sum(d["score"].fillna(0) * d["weight"] for d in legs.values())
    den = sum(d["score"].notna().astype(float) * d["weight"] for d in legs.values())
    score = (100.0 * num / den.replace(0, np.nan)).clip(0, 100)
    return score, legs


def china_recession(f: pd.DataFrame) -> dict:
    """0..100 China slowdown / recession gauge (UNCALIBRATED, display-only) + a
    per-leg breakdown whose `points` sum to the headline (stacked-bar ready,
    mirrors equity_alloc.risk_legs). Higher = more recession-ward. Renormalized
    over available legs. NEVER scored into china_axes / regime / playbook."""
    score, legs = _recession_score_series(f)
    sc = score.dropna()
    if sc.empty:
        return {"score": None, "label": None, "legs": [], "uncalibrated": True}
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
    val = round(float(sc.iloc[-1]), 1)
    label = ("high" if val >= 66 else "elevated" if val >= 40 else "low")
    return {"score": val, "label": label, "legs": leg_rows, "uncalibrated": True,
            "note": "uncalibrated narrative gauge — China history is short/regime-unstable; never scored"}


# --------------------------------------------------------------------------- #
# (3) Drawdown-risk gauge — 0..100, UNCALIBRATED, display-only
# --------------------------------------------------------------------------- #
# Expanding rank-percentile of a z-mean of A-share stress legs. China rarely
# inverts its curve (PBoC pins the front end) so the CGB-curve leg is CONTEXT at
# a low weight. UNCALIBRATED — no measured P(drawdown) claim, unlike the US side.
_DD_CURVE_WEIGHT = 0.3   # CGB curve = context only (PBoC pins the front end)


def _drawdown_components(f: pd.DataFrame, rec_score: pd.Series) -> dict:
    """(z-Series, weight) per drawdown-stress leg, on f.index."""
    idx = f.index
    comps: dict[str, tuple[pd.Series, float]] = {}
    # slowdown gauge (already 0..100) — the macro-stress backbone
    if rec_score is not None and not rec_score.dropna().empty:
        comps["slowdown"] = (_z(rec_score, DD_Z_LOOKBACK), 1.0)
    # margin froth percentile (crowding) — froth precedes fragility
    fin = _store_series("china_margin", "balance", "fin_pct_float")
    if fin is not None:
        fin_d = _reindex(fin, idx).ffill(limit=5)
        comps["margin_froth"] = (_z(fin_d, DD_Z_LOOKBACK), 0.8)
    # CGB 10y-2y slope: FLATTER = worse. Negate so flattening -> higher stress.
    cgb = store.read("china_property", "cgb")
    if cgb is not None and not cgb.empty and "cgb_10y2y" in cgb.columns:
        slope = cgb["cgb_10y2y"].dropna()
        if len(slope):
            comps["cgb_flat"] = (-_z(_reindex(slope, idx).ffill(limit=10), DD_Z_LOOKBACK),
                                 _DD_CURVE_WEIGHT)
    # QVIX level (fear) — high implied vol = stress
    qv = _store_series("china_qvix", "qvix300", "close")
    if qv is not None:
        comps["qvix"] = (_z(_reindex(qv, idx).ffill(limit=5), DD_Z_LOOKBACK), 0.8)
    # turnover mania — extreme retail turnover precedes A-share tops
    turn = _market_turnover_series()
    if turn is not None:
        comps["turnover_mania"] = (_z(_reindex(turn, idx).ffill(limit=5), DD_Z_LOOKBACK), 0.6)
    return comps


def _drawdown_score_series(f: pd.DataFrame, rec_score: pd.Series) -> pd.Series:
    comps = _drawdown_components(f, rec_score)
    if len(comps) < 2:
        return pd.Series(index=f.index, dtype=float)
    num = sum(z.fillna(0) * w for z, w in comps.values())
    den = sum(z.notna().astype(float) * w for z, w in comps.values())
    zmean = num / den.replace(0, np.nan)
    return (zmean.expanding(min_periods=252).rank(pct=True) * 100)


def china_drawdown(f: pd.DataFrame, rec_score: pd.Series | None = None) -> dict:
    """0..100 A-share drawdown-risk gauge (UNCALIBRATED, display-only): expanding
    rank-percentile of a z-mean of slowdown + margin froth + flat-CGB + QVIX +
    turnover-mania. Higher = more fragile. NEVER scored."""
    if rec_score is None:
        rec_score, _ = _recession_score_series(f)
    series = _drawdown_score_series(f, rec_score).dropna()
    if series.empty:
        return {"score": None, "band": None, "uncalibrated": True}
    val = round(float(series.iloc[-1]), 1)
    band = ("extreme" if val >= 90 else "high" if val >= 75
            else "elevated" if val >= 50 else "low")
    return {"score": val, "band": band, "uncalibrated": True,
            "note": "uncalibrated rank-percentile of A-share stress legs — display-only, never scored"}


# --------------------------------------------------------------------------- #
# Fear <-> Euphoria synthesis (mirror scripts/build_site.py _fe_* logic)
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
    asof = raw.index[-1]                            # align every leg to the composite's date
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
    """Cross-asset confirmation tally over the signed RORO legs (the dispersion
    the headline mean hides). Majority-anchored; NEVER scored."""
    if not legs:
        return None
    on = [lg for lg in legs if lg["lean"] == "risk-on"]
    off = [lg for lg in legs if lg["lean"] == "risk-off"]
    n_on, n_off = len(on), len(off)
    total = n_on + n_off                         # neutral (exactly-0) legs don't take a side
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
    """DISPLAY-ONLY China Fear<->Euphoria synthesis. Maps the RORO composite to a
    rolling-5y 0-100 percentile, decomposes its signed legs and tallies cross-asset
    confirmation. NEVER scores; NEVER touches china_axes / regime / playbook.

    History caveat: the rolling-5y percentile needs >=2.5y of RORO history; on a
    shorter window it degrades to an expanding percentile, and returns a
    'warming up' note when even that is too thin. Returns None only if no RORO
    composite can be built at all."""
    if f is None:
        from engine.china_inputs import build_features
        f = build_features()
    rf = roro_frame(f)
    if "roro" not in rf.columns or rf["roro_raw"].dropna().empty:
        return None
    raw = rf["roro_raw"].dropna()
    warming = len(raw) < FE_MIN_HISTORY
    # use the pre-tanh composite for the percentile (monotone in roro, more spread)
    if warming:
        pct = _last(rf["roro_raw"].expanding(min_periods=20).rank(pct=True))
    else:
        pct = _last(pct_rank_window(rf["roro_raw"], FE_PCTILE_WINDOW))
    legs = _fe_legs(rf)
    roro_state = china_roro(f)
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
    """ISO-date + 0..100 Fear<->Euphoria history line (rolling-5y percentile of
    the pre-tanh RORO composite, or expanding while warming up)."""
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
    """The DISPLAY-ONLY conditions bundle the China engine persists to
    latest['conditions']: RORO composite + signed legs, the recession/slowdown
    gauge + leg breakdown, the drawdown-risk gauge, and chart-ready {dates,vals}
    history for the RORO line, the recession line and the drawdown line.

    `regime` is accepted for signature parity with the US conditions snapshot but
    is unused here (this layer reads no regime labels — it is independent of the
    quad). NEVER scored into china_axes / regime / playbook."""
    if f is None:
        from engine.china_inputs import build_features
        f = build_features()
    rf = roro_frame(f)
    rec_series, _legs = _recession_score_series(f)
    dd_series = _drawdown_score_series(f, rec_series)

    roro = china_roro(f)
    recession = china_recession(f)
    drawdown = china_drawdown(f, rec_series)

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
        "note": ("display-only conditioning lens — RORO + uncalibrated recession/drawdown gauges; "
                 "never feeds china_axes / china_regime / china_playbook"),
    }
