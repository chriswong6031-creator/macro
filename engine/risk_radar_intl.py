"""Risk Radar (international) — a genuinely-leading, calibrated forward-drawdown radar
for China, Hong Kong and Canada, mirroring the US engine.risk_radar but built from the
drivers that *do* lead these markets.

WHY THIS EXISTS
---------------
The old China/HK/CA conditions layer (engine/china_conditions.py et al.) concluded there
was "no forward-drawdown edge" — but it only ever tested China-INTERNAL froth legs (margin
balance, turnover mania, valuation extension), which are indeed dead/contrarian (A-shares
mean-revert on those). It never tested the EXTERNAL drivers the owner flagged: as China (and,
more recently, HK and Canada) has coupled to US policy, drawdowns are led by US rate shocks,
a widening US–China yield gap, a strengthening dollar / depreciating yuan, AND a broad-based
breadth breakdown (China corrections sink all sectors — "all boats" — unlike the US rotational
tape, which makes the breadth leg genuinely leading rather than self-cancelling).

VALIDATION (research harness, causal trailing-504d percentiles, block-permutation p, split-half
+ 2016+ era; SHCOMP 1997+, confirmed on CSI 300):
  breadth collapse (% < 200dMA)     lift 1.97 (≥10%/42d), 2016+ 3.13x, p=0.04, leading (1.67x near highs)
  US 2y / real-10y / 10y rate shock 1.5–1.7x full, 2016+ 2.4–3.3x, p≤0.04, sign-stable
  US–China 10y differential widening 1.61x, 2016+ 2.78x, p=0.03
  USD/CNH depreciation               1.9x, h2 2.6x
  composite (this engine)            ≥10%/42d 2.07x (h1/h2 2.28/2.00, p=0.01); CSI300 2.22x
HK generalises moderately (≈1.5x, recent-era only — coupling is recent), Canada weakly
(≈1.4–1.6x recent, commodity-driven). Honest per-market calibration + caveats below.

HONESTY: the edge is MODEST (~1.4–2x conditional lift at the extremes, not a forecast) and
concentrated where it should be (a context gate keeps the LOUD tiers quiet until the broad
index is actually below its 200-day line). Every probability here is MEASURED from the market's
own history; the de-risk response is SIZING, not selection. All signals are causal/leak-free
(trailing-window percentiles). No public function raises into the build.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from engine.indicators import pct_rank_window
from lib import config, store

log = logging.getLogger(__name__)

_PCT_WIN = 504                       # ~2y trailing causal percentile window (matches US radar)
_STATE_ORDER = ["calm", "watch", "caution", "elevated", "risk-off"]
# scare-meter colour bands on the 0-100 per-scare score (mean of leg percentiles * 100)
_SCARE_BANDS = {"watch": 55.0, "caution": 68.0, "elevated": 78.0, "risk_off": 88.0}
_GROSS = {"calm": 1.0, "watch": 0.97, "caution": 0.90, "elevated": 0.78, "risk-off": 0.62}
_DISCLAIMER = ("Evidence-gated leading-risk radar — built only from the external drivers (US "
               "rate shocks, US–China yield gap, USD/FX) + breadth that MEASURABLY lead this "
               "market's drawdowns (not the internal froth legs, which mean-revert). Edge is "
               "modest (~1.4–2x at the extremes, not a forecast); odds are measured from the "
               "market's own history; de-risk = sizing, not selection.")


# --- store readers (causal) --------------------------------------------------
def _read(group: str, name: str, col: str = "close") -> pd.Series | None:
    df = store.read(group, name)
    if df is None or getattr(df, "empty", True):
        return None
    c = col if col in df.columns else df.columns[0]
    s = df[c].dropna()
    if s.empty:
        return None
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _pct(s: pd.Series | None) -> pd.Series | None:
    """Trailing-504d causal percentile (0-1). None-safe."""
    if s is None:
        return None
    s = s.dropna()
    return pct_rank_window(s, _PCT_WIN) if len(s) else None


# --- individual sub-leg builders (each → causal 'risk-rising' percentile on idx) ---
_RATE_SUBS = {
    "us_rate_2y":  ("fred", "DGS2", "us2y"),
    "us_real_rate": ("fred", "DFII10", "us10y_real"),
    "us_rate_10y": ("fred", "DGS10", "us10y"),
}


def _sub_legs(idx: pd.DatetimeIndex, profile: "RadarProfile") -> dict:
    """{sub_code: causal percentile SERIES on idx} for every sub-leg the profile uses."""
    out: dict[str, pd.Series] = {}
    # US-rate shocks (21d change percentile) — shared by all three markets
    for code, (g, n, c) in _RATE_SUBS.items():
        s = _read(g, n, c)
        if s is not None:
            out[code] = _pct(s.reindex(idx).ffill().diff(21))
    # USD / FX
    if profile.key == "cn":
        cnh = _read("yahoo", "CNH_F")
        dxy = _read("yahoo", "DX-Y.NYB")
        fx = cnh.reindex(idx).ffill().pct_change(21) if cnh is not None else None
        if dxy is not None:                                   # DXY 63d ROC fills pre-2013 CNH gap
            d = dxy.reindex(idx).ffill().pct_change(63)
            fx = d if fx is None else fx.combine_first(d)
        out["usd_cnh"] = _pct(fx)
        u10 = _read("fred", "DGS10", "us10y")
        cgb = store.read("china_property", "cgb")
        if u10 is not None and cgb is not None and "cgb_10y" in getattr(cgb, "columns", []):
            c10 = cgb["cgb_10y"].dropna(); c10.index = pd.to_datetime(c10.index)
            diff = u10.reindex(idx).ffill() - c10.sort_index().reindex(idx).ffill()
            out["us_cn_diff"] = _pct(diff.diff(21))           # widening gap = outflow pressure
    else:
        dxy = _read("yahoo", "DX-Y.NYB")
        if dxy is not None:
            out["usd_strength"] = _pct(dxy.reindex(idx).ffill().pct_change(63))
    # breadth collapse (% < 200dMA) — where deep history exists
    if profile.breadth_group:
        br = store.read(profile.breadth_group, "breadth")
        if br is not None and "pct_above_200" in getattr(br, "columns", []):
            b = br["pct_above_200"].dropna(); b.index = pd.to_datetime(b.index)
            if len(b) >= 500:
                out[profile.breadth_code] = _pct(-b.sort_index().reindex(idx).ffill())
    return {k: v for k, v in out.items() if v is not None}


# --- profile -----------------------------------------------------------------
@dataclass(frozen=True)
class RadarProfile:
    key: str                          # 'cn' | 'hk' | 'ca'
    bench: tuple                      # (store group, name) — the index drawdowns are measured on
    breadth_group: str | None         # store group for the breadth frame (None = no breadth leg)
    breadth_code: str                 # sub-leg display code for the breadth leg
    comp_legs: tuple                  # ((comp_key, (sub_codes...), weight), ...) — composite structure
    scares: tuple                     # ((scare_key, tier, label_en, label_zh, (comp_keys), (sub_codes)), ...)
    bands: dict                       # {watch,caution,elevated,risk_off} on the 0-100 composite percentile
    prob_cal: dict                    # {h5/h10/h21: {state: P(>=5% drawdown within h)}}
    prob_base: dict                   # {h5,h10,h21} unconditional base rates
    caveat_en: str
    caveat_zh: str


def _band(score, bands: dict) -> str:
    if score is None or (isinstance(score, float) and np.isnan(score)):
        return "calm"
    if score >= bands["risk_off"]:
        return "risk-off"
    if score >= bands["elevated"]:
        return "elevated"
    if score >= bands["caution"]:
        return "caution"
    if score >= bands["watch"]:
        return "watch"
    return "calm"


def _last(s: pd.Series | None):
    if s is None:
        return None
    s = s.dropna()
    return float(s.iloc[-1]) if len(s) else None


def _calib(profile: "RadarProfile", root=None) -> dict:
    """Per-market calibration = the baked profile surface, OPTIONALLY overlaid by the bounded
    tuner (data/risk_radar_intl/<key>_calibration.json, engine/risk_radar_intl_tune.py). The
    overlay may adjust the prob surface only (the displayed odds become measured from the
    radar's own track record); the bands stay structural. Absent file ⇒ baked defaults."""
    cal = {"prob_cal": {h: dict(v) for h, v in profile.prob_cal.items()},
           "prob_base": dict(profile.prob_base), "bands": dict(profile.bands)}
    try:
        base = config.data_dir() if root is None else (Path(root) / "data")
        p = base / "risk_radar_intl" / f"{profile.key}_calibration.json"
        if p.exists():
            ov = json.loads(p.read_text())
            for h, d in (ov.get("prob_cal") or {}).items():
                if h in cal["prob_cal"]:
                    cal["prob_cal"][h].update({k: float(v) for k, v in d.items()})
            if ov.get("prob_base"):
                cal["prob_base"].update({k: float(v) for k, v in ov["prob_base"].items()})
    except Exception as e:  # noqa: BLE001
        log.warning("risk_radar_intl calib overlay(%s) failed: %s", profile.key, e)
    return cal


def _probs(cal: dict, state: str) -> dict:
    pc, base = cal["prob_cal"], cal["prob_base"]
    out = {h: pc[h].get(state, base[h]) for h in ("h5", "h10", "h21")}
    out["base_h5"], out["base_h10"], out["base_h21"] = base["h5"], base["h10"], base["h21"]
    out["lift_h21"] = round(out["h21"] / base["h21"], 2) if base["h21"] else None
    out["measure"] = ">=5% index pullback within h business days (measured on this market's own history)"
    return out


def compute(profile: "RadarProfile", root=None) -> dict:
    """Live calibrated radar snapshot for `profile`. Reads the store; never raises a useful
    payload away. Returns the (risk_radar_intl.v1) dict the market-state radar mapping consumes."""
    null = {"schema": "risk_radar_intl.v1", "state": None, "market": profile.key,
            "degraded_reason": "no_data", "disclaimer": _DISCLAIMER}
    B = _read(*profile.bench)
    if B is None or len(B) < 300:
        return null
    idx = B.index
    sub = _sub_legs(idx, profile)
    if not sub:
        return null
    cal = _calib(profile, root)          # baked surface + the tuner's overlay, if any

    # composite-leg latest percentiles + series (the calibrated structure)
    comp_last: dict[str, float] = {}
    comp_series: dict[str, tuple] = {}
    for comp_key, sub_codes, w in profile.comp_legs:
        members = [sub[c] for c in sub_codes if c in sub]
        if not members:
            continue
        ser = pd.concat(members, axis=1).mean(axis=1)
        comp_series[comp_key] = (ser, w)
        comp_last[comp_key] = _last(ser)

    # blended composite → trailing percentile → 0-100 risk score
    num = den = None
    for ser, w in comp_series.values():
        col = ser.fillna(0.5) * w
        av = ser.notna().astype(float) * w
        num = col if num is None else num + col
        den = av if den is None else den + av
    if num is None:
        return null
    comp = pct_rank_window((num / den.replace(0, np.nan)).dropna(), _PCT_WIN)
    top = _last(comp)
    top100 = round(top * 100) if top is not None else None

    # context gate — the LOUD tiers (elevated+) require the broad index to be BELOW its
    # 200-day line (the "all boats" breakdown). Below the gate, cap at caution: the early
    # tiers still show, but the loud banner waits for the broad tape to confirm.
    ma = B.rolling(200, min_periods=120).mean()
    below = bool(B.iloc[-1] < ma.iloc[-1]) if ma.dropna().size else False
    state_ungated = _band(top * 100 if top is not None else None, cal["bands"])
    state = state_ungated
    if not below and _STATE_ORDER.index(state) > _STATE_ORDER.index("caution"):
        state = "caution"

    # per-scare meters (display) + plain-English firing legs
    scares = []
    for skey, tier, le, lz, comp_keys, sub_codes in profile.scares:
        vals = [comp_last[k] for k in comp_keys if comp_last.get(k) is not None]
        if not vals:
            continue
        sc = float(np.mean(vals)) * 100.0
        firing = [{"leg": c, "pctile": round(sub_latest, 3), "confirmed": bool(sub_latest >= 0.85)}
                  for c in sub_codes
                  if (sub_latest := _last(sub.get(c))) is not None and sub_latest >= 0.55]
        firing.sort(key=lambda d: -d["pctile"])
        scares.append({"scare": skey, "tier": tier, "label_en": le, "label_zh": lz,
                       "score": round(sc, 1), "band": _band(sc, _SCARE_BANDS),
                       "firing_legs": firing})
    scares.sort(key=lambda d: -d["score"])
    tierA = [s for s in scares if s["tier"] == "A"]
    dominant = tierA[0] if tierA else (scares[0] if scares else None)
    nhot = sum(1 for s in tierA if s["band"] in ("caution", "elevated", "risk-off"))

    if state == "calm":
        dom_en, dom_zh = "Calm — no driver elevated", "平静 — 无驱动升高"
    else:
        dom_en = dominant["label_en"] if dominant else "calm"
        dom_zh = dominant["label_zh"] if dominant else "平静"

    return {
        "schema": "risk_radar_intl.v1",
        "asof": str(pd.Timestamp(idx[-1]).date()),
        "market": profile.key,
        "state": state,
        "state_ungated": state_ungated,
        "top_score": top100,
        "dominant_scare": dominant["scare"] if dominant else None,
        "dominant_label_en": dom_en,
        "dominant_label_zh": dom_zh,
        "scares": scares,
        "drawdown_prob": _probs(cal, state),
        "gross_factor": _GROSS.get(state, 1.0),
        "conjunction": bool(nhot >= 2),
        "context_gate": {"met": below, "below_200dma": below},
        "caveat_en": profile.caveat_en,
        "caveat_zh": profile.caveat_zh,
        "disclaimer": _DISCLAIMER,
    }


def snapshot(profile: "RadarProfile", root=None) -> dict:
    """IO wrapper the build persists to latest['risk_radar']. Never raises."""
    try:
        return compute(profile, root)
    except Exception as e:  # noqa: BLE001
        log.error("risk_radar_intl(%s) failed: %s", getattr(profile, "key", "?"), e)
        return {"schema": "risk_radar_intl.v1", "state": None,
                "market": getattr(profile, "key", None), "degraded_reason": "compute_error",
                "disclaimer": _DISCLAIMER}


# === per-market profiles =====================================================
# Composite-percentile bands shared across markets (calibrated: elevated+ ≈ top ~12% of
# history AND gated on a broad break; see research/ harness). Probability surfaces are each
# MEASURED from that market's own ≥5% forward-drawdown frequency by band (monotone at the top
# where the edge is real; modest, not a forecast).
_BANDS = {"watch": 58.0, "caution": 72.0, "elevated": 83.0, "risk_off": 91.0}

CN_PROFILE = RadarProfile(
    key="cn",
    bench=("china", "000001.SS"),                # Shanghai Composite (longest clean history)
    breadth_group="china_breadth", breadth_code="cn_breadth",
    comp_legs=(
        ("rateshock", ("us_rate_2y", "us_real_rate", "us_rate_10y"), 1.0),
        ("usd",       ("usd_cnh",),                                   0.6),
        ("diff",      ("us_cn_diff",),                                0.8),
        ("breadth",   ("cn_breadth",),                                1.0),
    ),
    scares=(
        ("rate_shock", "A", "US rate shock", "美债利率冲击",
         ("rateshock",), ("us_rate_2y", "us_real_rate", "us_rate_10y")),
        ("capital_flow", "A", "Capital outflow / FX", "资本外流／汇率",
         ("usd", "diff"), ("usd_cnh", "us_cn_diff")),
        ("breadth", "A", "Breadth breakdown (all-boats)", "广度普跌（普跌）",
         ("breadth",), ("cn_breadth",)),
    ),
    bands=_BANDS,
    prob_base={"h5": 0.072, "h10": 0.160, "h21": 0.305},
    prob_cal={
        "h5":  {"calm": 0.06, "watch": 0.08, "caution": 0.09, "elevated": 0.12, "risk-off": 0.15},
        "h10": {"calm": 0.13, "watch": 0.16, "caution": 0.18, "elevated": 0.21, "risk-off": 0.32},
        "h21": {"calm": 0.27, "watch": 0.32, "caution": 0.35, "elevated": 0.40, "risk-off": 0.50},
    },
    caveat_en=("Validated but modest: China drawdowns are led by US rate shocks, a widening US–China "
               "yield gap, dollar strength / yuan weakness, and a broad breadth breakdown (corrections "
               "sink all sectors). Odds are measured from A-share history; the internal froth legs are "
               "excluded (they mean-revert). Context, sized — not a forecast."),
    caveat_zh=("已验证但偏温和：A股回撤由美债利率冲击、中美利差走阔、美元走强／人民币走弱，以及广度普跌（调整时各板块同跌）"
               "领先。概率取自A股自身历史；内部拥挤腿已剔除（其均值回归）。用于定仓的背景，而非预测。"),
)

HK_PROFILE = RadarProfile(
    key="hk",
    bench=("hk", "_HSI"),                         # Hang Seng Index
    breadth_group=None, breadth_code="hk_breadth",
    comp_legs=(
        ("rateshock", ("us_rate_2y", "us_real_rate", "us_rate_10y"), 1.0),
        ("usd",       ("usd_strength",),                              0.6),
    ),
    scares=(
        ("rate_shock", "A", "US rate shock", "美债利率冲击",
         ("rateshock",), ("us_rate_2y", "us_real_rate", "us_rate_10y")),
        ("capital_flow", "A", "USD / HKD funding", "美元／港元资金",
         ("usd",), ("usd_strength",)),
    ),
    bands=_BANDS,
    prob_base={"h5": 0.077, "h10": 0.174, "h21": 0.309},
    prob_cal={
        "h5":  {"calm": 0.07, "watch": 0.08, "caution": 0.09, "elevated": 0.10, "risk-off": 0.16},
        "h10": {"calm": 0.16, "watch": 0.17, "caution": 0.19, "elevated": 0.22, "risk-off": 0.35},
        "h21": {"calm": 0.29, "watch": 0.31, "caution": 0.34, "elevated": 0.42, "risk-off": 0.54},
    },
    caveat_en=("Lighter than the China read and recent-era only: HK's US-coupling (HKD peg → US rates "
               "transmit directly, dollar strength) has only led HSI drawdowns since ~2016; deep HK "
               "breadth history is unavailable, so this leans on the external legs. Context, not a forecast."),
    caveat_zh=("较A股版更轻量，且仅近年有效：港元联系汇率使美债利率直接传导、美元走强——这种美股联动自约2016年起"
               "才领先恒指回撤；港股深度广度历史缺失，故以外部因子为主。仅作背景，而非预测。"),
)

CA_PROFILE = RadarProfile(
    key="ca",
    bench=("canada", "_GSPTSE"),                  # S&P/TSX Composite
    breadth_group="canada_breadth", breadth_code="ca_breadth",
    comp_legs=(
        ("rateshock", ("us_rate_2y", "us_real_rate", "us_rate_10y"), 1.0),
        ("usd",       ("usd_strength",),                              0.6),
        ("breadth",   ("ca_breadth",),                                1.0),
    ),
    scares=(
        ("rate_shock", "A", "US rate shock", "美债利率冲击",
         ("rateshock",), ("us_rate_2y", "us_real_rate", "us_rate_10y")),
        ("capital_flow", "A", "USD strength", "美元走强",
         ("usd",), ("usd_strength",)),
        ("breadth", "A", "Breadth breakdown", "广度破位",
         ("breadth",), ("ca_breadth",)),
    ),
    bands=_BANDS,
    prob_base={"h5": 0.027, "h10": 0.068, "h21": 0.155},
    prob_cal={
        "h5":  {"calm": 0.026, "watch": 0.03, "caution": 0.04, "elevated": 0.07, "risk-off": 0.07},
        "h10": {"calm": 0.065, "watch": 0.07, "caution": 0.09, "elevated": 0.12, "risk-off": 0.16},
        "h21": {"calm": 0.155, "watch": 0.16, "caution": 0.19, "elevated": 0.25, "risk-off": 0.29},
    },
    caveat_en=("The lightest read and emerging-only: the TSX is commodity-driven and the least US-coupled "
               "of the three; US rate shocks, dollar strength and a breadth breakdown lead its drawdowns "
               "only weakly and only in the recent era. Context, sized — not a forecast."),
    caveat_zh=("三者中最轻量、且仅近期显现：多伦多指数由大宗商品驱动，与美股联动最弱；美债利率冲击、美元走强与广度破位"
               "仅在近年、且较弱地领先其回撤。用于定仓的背景，而非预测。"),
)

PROFILES = {"cn": CN_PROFILE, "hk": HK_PROFILE, "ca": CA_PROFILE}
