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
_EXT_PCT_WIN = 2520                  # ~10y causal window for the raw-extension percentile (long-history, NOT the self-defeating 252d z)
_EXT_PARABOLIC = 0.98                # extension percentile at/above which the regime counts as parabolic
_GATE_MEMORY = 60                    # sessions the parabolic gate stays open after the last parabolic reading
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
    # US-rate shocks (21d change percentile) — shared by all markets
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
    elif profile.fx_pair is not None:
        # per-market FX-depreciation leg: local-currency weakness = outflow pressure.
        # fx_risk_sign orients the pair so RISING series = depreciation risk; DXY 63d ROC
        # fills the pre-pair era (same stitch the CN leg uses for pre-2013 CNH).
        pair = _read(*profile.fx_pair)
        fx = pair.reindex(idx).ffill().pct_change(21) * profile.fx_risk_sign if pair is not None else None
        dxy = _read("yahoo", "DX-Y.NYB")
        if dxy is not None:
            d = dxy.reindex(idx).ffill().pct_change(63)
            fx = d if fx is None else fx.combine_first(d)
        out[profile.fx_code or "fx_depreciation"] = _pct(fx)
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
    # raw-extension percentile legs (melt-up detector): px/200dma-1 ranked in a LONG causal
    # window — the 2026 KOSPI class. A trailing-1y z would deflate exactly at the top
    # (the parabola inflates its own baseline); the ~10y percentile does not.
    for g, names, code in profile.ext_sources:
        members = []
        for n in (names if isinstance(names, tuple) else (names,)):
            s = _read(g, n)
            if s is None or len(s) < 300:
                continue
            px = s.reindex(idx).ffill()
            ma = px.rolling(200, min_periods=120).mean()
            p = pct_rank_window((px / ma - 1.0).dropna(), _EXT_PCT_WIN)
            members.append(p)
        if members:
            out[code] = pd.concat(members, axis=1).mean(axis=1) if len(members) > 1 else members[0]
    return {k: v for k, v in out.items() if v is not None}


# --- profile -----------------------------------------------------------------
@dataclass(frozen=True)
class RadarProfile:
    key: str                          # 'cn' | 'hk' | 'ca' | 'kr' | 'jp' | 'tw' | 'in' | 'au' | 'gb' | 'ez'
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
    # --- 7-market extension fields (2026-07-16). Defaults preserve CN/HK/CA behavior exactly. ---
    fx_pair: tuple | None = None      # (store group, name) of the market's FX pair, e.g. ("intl", "USDKRW=X")
    fx_risk_sign: int = 1             # +1: pair RISES = local ccy depreciates (USD/local quote); -1: pair FALLS = depreciates (local/USD quote)
    fx_code: str = ""                 # sub-leg display code, e.g. "krw_depreciation"
    ext_sources: tuple = ()           # ((group, name_or_name_tuple, sub_code), ...) — raw-extension percentile legs; a tuple of names = basket (mean of member percentiles)
    gate_mode: str = "below_200dma"   # "below_200dma" (legacy) | "below_or_recent_parabolic" (melt-up markets); INTL-50: no macro gate harms Korea
    disclaimer: str | None = None     # per-profile override; None = module _DISCLAIMER (legacy)


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


def _gate_series(B: pd.Series, sub: dict, profile: "RadarProfile") -> pd.Series:
    """True where the context gate is OPEN (loud tiers allowed). Causal. Legacy mode:
    index below its 200dma ("all boats" confirmation). Melt-up mode additionally opens
    while the extension percentile has printed parabolic (>= _EXT_PARABOLIC) within the
    last _GATE_MEMORY sessions — at a parabolic top the index is far ABOVE its 200dma,
    so the legacy gate would structurally silence the radar exactly when it matters
    (KOSPI 2026-06; INTL-50 ruling: no macro gate, only price/extension context gate)."""
    ma = B.rolling(200, min_periods=120).mean()
    gate = (B < ma).fillna(False)
    if profile.gate_mode == "below_or_recent_parabolic" and profile.ext_sources:
        e = sub.get(profile.ext_sources[0][2])
        if e is not None:
            recent_para = e.rolling(_GATE_MEMORY, min_periods=1).max() >= _EXT_PARABOLIC
            gate = gate | recent_para.reindex(B.index).fillna(False)
    return gate


def composite_series(profile: "RadarProfile", root=None):
    """(B, sub, comp, gate) — bench closes, sub-leg percentile dict, blended composite
    trailing percentile (0-1), and the boolean context-gate series. None when no data.
    THE single construction compute() and scripts/calibrate_risk_radar_intl.py share."""
    B = _read(*profile.bench)
    if B is None or len(B) < 300:
        return None, None, None, None
    idx = B.index
    sub = _sub_legs(idx, profile)
    if not sub:
        return None, None, None, None

    # composite-leg latest percentiles + series (the calibrated structure)
    comp_series_parts: dict[str, tuple] = {}
    for comp_key, sub_codes, w in profile.comp_legs:
        members = [sub[c] for c in sub_codes if c in sub]
        if not members:
            continue
        ser = pd.concat(members, axis=1).mean(axis=1)
        comp_series_parts[comp_key] = (ser, w)

    # blended composite → trailing percentile → 0-1 risk score
    num = den = None
    for ser, w in comp_series_parts.values():
        col = ser.fillna(0.5) * w
        av = ser.notna().astype(float) * w
        num = col if num is None else num + col
        den = av if den is None else den + av
    if num is None:
        return None, None, None, None

    comp = pct_rank_window((num / den.replace(0, np.nan)).dropna(), _PCT_WIN)
    gate = _gate_series(B, sub, profile)
    return B, sub, comp, gate


def _trajectory(comp, B, cal, window: int = 30, gate: pd.Series | None = None) -> dict | None:
    """Recent PATH of this market's composite radar — has it peaked + started rolling over, and how
    fast are the pullback odds dropping? Powers the de-escalation panel (engine/risk_radar_recovery).
    Reuses the SHARED classifier (engine/risk_radar._trajectory_from_series) so the phase logic is
    identical to the US radar. Leak-free (comp is a causal trailing percentile). Never raises.

    gate: when given, use it in place of the internally-computed below series. For legacy profiles
    the passed gate equals the internally-computed below → identical output."""
    try:
        from engine.risk_radar import _trajectory_from_series
        intensity = (comp.dropna() * 100.0)
        if len(intensity) < 10:
            return None
        bands = cal["bands"]
        if gate is not None:
            below = gate.reindex(intensity.index).fillna(False)
        else:
            ma = B.rolling(200, min_periods=120).mean()
            below = (B < ma).reindex(intensity.index).fillna(False)   # context gate: index < 200dma
        win = intensity.tail(window)
        states, odds = [], []
        for d, v in win.items():
            st = _band(v, bands)
            if not bool(below.get(d, False)) and _STATE_ORDER.index(st) > _STATE_ORDER.index("caution"):
                st = "caution"                                     # gate caps the loud tiers
            states.append(st)
            odds.append(_probs(cal, st)["h21"])
        return _trajectory_from_series(win, states, pd.Series(odds, index=win.index), bands["caution"])
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("risk_radar_intl trajectory failed: %s", e)
        return None


def compute(profile: "RadarProfile", root=None) -> dict:
    """Live calibrated radar snapshot for `profile`. Reads the store; never raises a useful
    payload away. Returns the (risk_radar_intl.v1) dict the market-state radar mapping consumes."""
    effective_disclaimer = profile.disclaimer or _DISCLAIMER
    null = {"schema": "risk_radar_intl.v1", "state": None, "market": profile.key,
            "degraded_reason": "no_data", "disclaimer": effective_disclaimer}
    B, sub, comp, gate = composite_series(profile, root)
    if B is None:
        return null
    if sub is None or comp is None or gate is None:
        return null
    cal = _calib(profile, root)          # baked surface + the tuner's overlay, if any

    # composite-leg latest percentiles (for scares)
    comp_last: dict[str, float] = {}
    for comp_key, sub_codes, w in profile.comp_legs:
        members = [sub[c] for c in sub_codes if c in sub]
        if not members:
            continue
        ser = pd.concat(members, axis=1).mean(axis=1)
        comp_last[comp_key] = _last(ser)

    top = _last(comp)
    top100 = round(top * 100) if top is not None else None

    # context gate — gate_open uses the shared gate series (legacy profiles: gate == below)
    gate_open = bool(gate.iloc[-1]) if len(gate) else False
    # also compute the raw price-vs-200dma bool (always present in the payload)
    ma = B.rolling(200, min_periods=120).mean()
    below_actual = bool(B.iloc[-1] < ma.iloc[-1]) if ma.dropna().size else False

    state_ungated = _band(top * 100 if top is not None else None, cal["bands"])
    state = state_ungated
    if not gate_open and _STATE_ORDER.index(state) > _STATE_ORDER.index("caution"):
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

    # context_gate payload: keep exact existing keys for ALL profiles; add recent_parabolic
    # only for new-mode profiles (gate_mode != "below_200dma") so cn/hk/ca payloads are byte-identical
    context_gate: dict = {"met": gate_open, "below_200dma": below_actual}
    if profile.gate_mode != "below_200dma" and profile.ext_sources:
        # memory semantics, same as _gate_series: parabolic printed within the last
        # _GATE_MEMORY sessions — a mid-crash receipt must still say "was parabolic"
        # (the memoryless latest-value read is the F1 self-erasing-flag failure)
        ext_s = sub.get(profile.ext_sources[0][2])
        recent = False
        if ext_s is not None:
            tail = ext_s.dropna().tail(_GATE_MEMORY)
            recent = bool(len(tail) and (tail >= _EXT_PARABOLIC).any())
        context_gate["recent_parabolic"] = recent

    return {
        "schema": "risk_radar_intl.v1",
        "asof": str(pd.Timestamp(B.index[-1]).date()),
        "market": profile.key,
        "state": state,
        "state_ungated": state_ungated,
        "top_score": top100,
        "dominant_scare": dominant["scare"] if dominant else None,
        "dominant_label_en": dom_en,
        "dominant_label_zh": dom_zh,
        "scares": scares,
        "drawdown_prob": _probs(cal, state),
        # de-escalation PATH (peaked? rolling over? how fast?) — reuses the composite series above.
        "trajectory": _trajectory(comp, B, cal, gate=gate),
        "gross_factor": _GROSS.get(state, 1.0),
        "conjunction": bool(nhot >= 2),
        "context_gate": context_gate,
        "caveat_en": profile.caveat_en,
        "caveat_zh": profile.caveat_zh,
        "disclaimer": effective_disclaimer,
    }


def snapshot(profile: "RadarProfile", root=None) -> dict:
    """IO wrapper the build persists to latest['risk_radar']. Never raises."""
    try:
        return compute(profile, root)
    except Exception as e:  # noqa: BLE001
        log.error("risk_radar_intl(%s) failed: %s", getattr(profile, "key", "?"), e)
        effective_disclaimer = getattr(profile, "disclaimer", None) or _DISCLAIMER
        return {"schema": "risk_radar_intl.v1", "state": None,
                "market": getattr(profile, "key", None), "degraded_reason": "compute_error",
                "disclaimer": effective_disclaimer}


def cn_sleeve_chip(root=None) -> dict:
    """Return a DISPLAY-ONLY sleeve-size chip from the validated CN drawdown radar.

    Called by the five China surfaces (china_stocks board, sector_central, baskets_china,
    subsectors_china, sector_cycles_china) to thread the risk_radar_intl gross_factor into
    their emitted JSON without re-ranking names or gating inclusion.

    Masterplan W6-CN rule: regime sizes sleeves, never vetoes names.

    Passport:
      basis: measured
      validation: risk_radar_intl ledger (data/risk_radar_intl/cn_forward_log.jsonl)
      consumers: china_stocks board header, sector_central, baskets_china,
                 subsectors_china, sector_cycles_china (display chips only)
    """
    try:
        r = snapshot(CN_PROFILE, root)
        state = r.get("state") or "unknown"
        gross = r.get("gross_factor", 1.0)
        as_of = r.get("asof", "")
        can_force = bool(r.get("can_force", False))
        dominant = r.get("dominant_label_en") or "no driver elevated"
        dominant_zh = r.get("dominant_label_zh") or "无驱动升高"
        return {
            "sleeve_factor": round(float(gross), 2),
            "radar_state": state,
            "radar_as_of": as_of,
            "can_force": can_force,
            # Human-readable display string for the board header chip
            "label_en": f"Sleeve ×{gross:.2f} — CN drawdown radar: {state}",
            "label_zh": f"仓位 ×{gross:.2f} — CN回撤雷达：{state}",
            "dominant_driver_en": dominant,
            "dominant_driver_zh": dominant_zh,
            # Signal passport (research/ENGINE_FIX_MASTERPLAN.md §W6-CN)
            "passport": {
                "basis": "measured",
                "validation": "risk_radar_intl ledger (cn_forward_log.jsonl)",
                "consumers": ["china_stocks", "sector_central_china", "baskets_china",
                              "subsectors_china", "sector_cycles_china"],
                "display_only": True,
                "note": ("Validated forward-drawdown composite on external drivers (US rate shocks, "
                         "USD/CNH, US-China yield gap, breadth). Sizes the SLEEVE, never vetoes names. "
                         "Lift: caution 1.97–3.13x, composite 2.07x p=0.01 (2016+ era)."),
            },
        }
    except Exception as e:  # noqa: BLE001 — sleeve chip is additive, never fatal
        log.warning("cn_sleeve_chip failed (%s); returning neutral", e)
        return {
            "sleeve_factor": 1.0, "radar_state": None, "radar_as_of": None,
            "can_force": False,
            "label_en": "Sleeve ×1.00 — CN drawdown radar: unavailable",
            "label_zh": "仓位 ×1.00 — CN回撤雷达：不可用",
            "passport": {"basis": "measured", "display_only": True, "degraded": True},
        }


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

# ─── 7-market extension profiles (2026-07-16) ────────────────────────────────
# Shared disclaimer for all 7 new profiles.
_INTL_7_DISCLAIMER = (
    "Leading-risk radar under accrual — external-driver legs (US rate shocks, FX depreciation, "
    "USD strength) ported from the China/HK/Canada radar research, plus a long-history extension "
    "percentile for melt-up regimes (2026 KOSPI class). The edge is unproven on this market until "
    "its own forward log matures; odds are measured from the market's own history; de-risk = "
    "sizing, not selection."
)

KR_PROFILE = RadarProfile(
    key="kr",
    bench=("intl", "^KS11"),
    breadth_group=None, breadth_code="kr_breadth",
    comp_legs=(
        ("rateshock", ("us_rate_2y", "us_real_rate", "us_rate_10y"), 1.0),
        ("fx",        ("krw_depreciation",),                          0.6),
        ("extension", ("ext_idx", "ext_etf"),                         1.0),
    ),
    scares=(
        ("rate_shock", "A", "US rate shock", "美债利率冲击",
         ("rateshock",), ("us_rate_2y", "us_real_rate", "us_rate_10y")),
        ("capital_flow", "A", "Won depreciation / outflows", "韩元贬值／资金外流",
         ("fx",), ("krw_depreciation",)),
        ("extension", "A", "Parabolic extension / exhaustion", "抛物线伸展／透支",
         ("extension",), ("ext_idx", "ext_etf")),
    ),
    bands=_BANDS,
    # prob surfaces: base rates measured from this market's own close history by
    # scripts/calibrate_risk_radar_intl.py (2026-07-16, window 1998-02-02..2026-07-16, n_days=7013; n counts overlapping forward windows, not independent samples).
    # prob_cal is seeded FLAT AT BASE: the in-sample per-state read of this ported
    # construction showed no (or overlap-fragile) loud-tier lift — printed by the
    # harness as a descriptive artifact, never baked. The live forward log + bounded
    # tuner (risk_radar_intl_tune, do-no-harm Brier) own the surface from n_graded>=25.
    prob_base={"h5": 0.092, "h10": 0.179, "h21": 0.289},
    prob_cal={
        "h5":  {"calm": 0.092, "watch": 0.092, "caution": 0.092, "elevated": 0.092, "risk-off": 0.092},
        "h10": {"calm": 0.179, "watch": 0.179, "caution": 0.179, "elevated": 0.179, "risk-off": 0.179},
        "h21": {"calm": 0.289, "watch": 0.289, "caution": 0.289, "elevated": 0.289, "risk-off": 0.289},
    },
    caveat_en=(
        "Ported construction, own-history odds: the external-driver legs (US rate shocks, won "
        "depreciation, USD strength) are ported from the China/HK/Canada radar research — their "
        "lead on KOSPI drawdowns is assumed from that work, not separately tested here; the "
        "extension leg tracks melt-up regimes (the 2026 KOSPI class). Odds are measured from "
        "KOSPI's own ~29y history; display-only while the forward log accrues. Context, sized "
        "— not a forecast."
    ),
    caveat_zh=(
        "构建为移植、赔率取自自身历史：外部驱动腿（美债利率冲击、韩元贬值、美元走强）移植自中国／香港／加拿大雷达研究，"
        "其对KOSPI回撤的领先性沿用该研究结论、未在本市场单独检验；伸展腿用于捕捉抛物线式过热行情（2026年KOSPI一类）。"
        "赔率测自KOSPI自身约29年历史；前向日志累积期间仅作展示。用于定仓的背景，而非预测。"
    ),
    fx_pair=("intl", "USDKRW=X"),
    fx_risk_sign=1,
    fx_code="krw_depreciation",
    ext_sources=(
        ("intl", "^KS11", "ext_idx"),
        ("intl_etf", "EWY", "ext_etf"),
    ),
    gate_mode="below_or_recent_parabolic",
    disclaimer=_INTL_7_DISCLAIMER,
)

JP_PROFILE = RadarProfile(
    key="jp",
    bench=("intl", "^N225"),
    breadth_group=None, breadth_code="jp_breadth",
    comp_legs=(
        ("rateshock", ("us_rate_2y", "us_real_rate", "us_rate_10y"), 1.0),
        ("fx",        ("jpy_depreciation",),                          0.6),
        ("extension", ("ext_idx", "ext_etf"),                         1.0),
    ),
    scares=(
        ("rate_shock", "A", "US rate shock", "美债利率冲击",
         ("rateshock",), ("us_rate_2y", "us_real_rate", "us_rate_10y")),
        ("capital_flow", "A", "Yen depreciation / outflows", "日元贬值／资金外流",
         ("fx",), ("jpy_depreciation",)),
        ("extension", "A", "Parabolic extension / exhaustion", "抛物线伸展／透支",
         ("extension",), ("ext_idx", "ext_etf")),
    ),
    bands=_BANDS,
    # prob surfaces: base rates measured from this market's own close history by
    # scripts/calibrate_risk_radar_intl.py (2026-07-16, window 1997-07-24..2026-07-16, n_days=7100; n counts overlapping forward windows, not independent samples).
    # prob_cal is seeded FLAT AT BASE: the in-sample per-state read of this ported
    # construction showed no (or overlap-fragile) loud-tier lift — printed by the
    # harness as a descriptive artifact, never baked. The live forward log + bounded
    # tuner (risk_radar_intl_tune, do-no-harm Brier) own the surface from n_graded>=25.
    prob_base={"h5": 0.073, "h10": 0.170, "h21": 0.307},
    prob_cal={
        "h5":  {"calm": 0.073, "watch": 0.073, "caution": 0.073, "elevated": 0.073, "risk-off": 0.073},
        "h10": {"calm": 0.170, "watch": 0.170, "caution": 0.170, "elevated": 0.170, "risk-off": 0.170},
        "h21": {"calm": 0.307, "watch": 0.307, "caution": 0.307, "elevated": 0.307, "risk-off": 0.307},
    },
    caveat_en=(
        "Ported construction, own-history odds: the external-driver legs (US rate shocks, yen "
        "depreciation, USD strength) are ported from the China/HK/Canada radar research — their "
        "lead on Nikkei 225 drawdowns is assumed from that work, not separately tested here; the "
        "extension leg tracks melt-up regimes. Odds are measured from Nikkei 225's own ~30y "
        "(capped) history; display-only while the forward log accrues. Context, sized — not a forecast."
    ),
    caveat_zh=(
        "构建为移植、赔率取自自身历史：外部驱动腿（美债利率冲击、日元贬值、美元走强）移植自中国／香港／加拿大雷达研究，"
        "其对日经225回撤的领先性沿用该研究结论、未在本市场单独检验；伸展腿用于捕捉抛物线式过热行情。"
        "赔率测自日经225自身约30年（上限截取）历史；前向日志累积期间仅作展示。用于定仓的背景，而非预测。"
    ),
    fx_pair=("intl", "USDJPY=X"),
    fx_risk_sign=1,
    fx_code="jpy_depreciation",
    ext_sources=(
        ("intl", "^N225", "ext_idx"),
        ("intl_etf", "EWJ", "ext_etf"),
    ),
    gate_mode="below_or_recent_parabolic",
    disclaimer=_INTL_7_DISCLAIMER,
)

TW_PROFILE = RadarProfile(
    key="tw",
    bench=("intl", "^TWII"),
    breadth_group=None, breadth_code="tw_breadth",
    comp_legs=(
        ("rateshock", ("us_rate_2y", "us_real_rate", "us_rate_10y"), 1.0),
        ("fx",        ("twd_depreciation",),                          0.6),
        ("extension", ("ext_idx", "ext_etf"),                         1.0),
    ),
    scares=(
        ("rate_shock", "A", "US rate shock", "美债利率冲击",
         ("rateshock",), ("us_rate_2y", "us_real_rate", "us_rate_10y")),
        ("capital_flow", "A", "TWD depreciation / outflows", "新台币贬值／资金外流",
         ("fx",), ("twd_depreciation",)),
        ("extension", "A", "Parabolic extension / exhaustion", "抛物线伸展／透支",
         ("extension",), ("ext_idx", "ext_etf")),
    ),
    bands=_BANDS,
    # prob surfaces: base rates measured from this market's own close history by
    # scripts/calibrate_risk_radar_intl.py (2026-07-16, window 1998-08-13..2026-07-16, n_days=6843; n counts overlapping forward windows, not independent samples).
    # prob_cal is seeded FLAT AT BASE: the in-sample per-state read of this ported
    # construction showed no (or overlap-fragile) loud-tier lift — printed by the
    # harness as a descriptive artifact, never baked. The live forward log + bounded
    # tuner (risk_radar_intl_tune, do-no-harm Brier) own the surface from n_graded>=25.
    prob_base={"h5": 0.070, "h10": 0.154, "h21": 0.272},
    prob_cal={
        "h5":  {"calm": 0.070, "watch": 0.070, "caution": 0.070, "elevated": 0.070, "risk-off": 0.070},
        "h10": {"calm": 0.154, "watch": 0.154, "caution": 0.154, "elevated": 0.154, "risk-off": 0.154},
        "h21": {"calm": 0.272, "watch": 0.272, "caution": 0.272, "elevated": 0.272, "risk-off": 0.272},
    },
    caveat_en=(
        "Ported construction, own-history odds: the external-driver legs (US rate shocks, TWD "
        "depreciation, USD strength) are ported from the China/HK/Canada radar research — their "
        "lead on TAIEX drawdowns is assumed from that work, not separately tested here; the "
        "extension leg tracks melt-up regimes. Odds are measured from TAIEX's own ~29y history; "
        "display-only while the forward log accrues. Context, sized — not a forecast."
    ),
    caveat_zh=(
        "构建为移植、赔率取自自身历史：外部驱动腿（美债利率冲击、新台币贬值、美元走强）移植自中国／香港／加拿大雷达研究，"
        "其对台湾加权指数回撤的领先性沿用该研究结论、未在本市场单独检验；伸展腿用于捕捉抛物线式过热行情。"
        "赔率测自台湾加权指数自身约29年历史；前向日志累积期间仅作展示。用于定仓的背景，而非预测。"
    ),
    fx_pair=("intl", "USDTWD=X"),
    fx_risk_sign=1,
    fx_code="twd_depreciation",
    ext_sources=(
        ("intl", "^TWII", "ext_idx"),
        ("intl_etf", "EWT", "ext_etf"),
    ),
    gate_mode="below_or_recent_parabolic",
    disclaimer=_INTL_7_DISCLAIMER,
)

IN_PROFILE = RadarProfile(
    key="in",
    bench=("intl", "^NSEI"),
    breadth_group=None, breadth_code="in_breadth",
    comp_legs=(
        ("rateshock", ("us_rate_2y", "us_real_rate", "us_rate_10y"), 1.0),
        ("fx",        ("inr_depreciation",),                          0.6),
        ("extension", ("ext_idx", "ext_etf"),                         1.0),
    ),
    scares=(
        ("rate_shock", "A", "US rate shock", "美债利率冲击",
         ("rateshock",), ("us_rate_2y", "us_real_rate", "us_rate_10y")),
        ("capital_flow", "A", "Rupee depreciation / outflows", "卢比贬值／资金外流",
         ("fx",), ("inr_depreciation",)),
        ("extension", "A", "Parabolic extension / exhaustion", "抛物线伸展／透支",
         ("extension",), ("ext_idx", "ext_etf")),
    ),
    bands=_BANDS,
    # prob surfaces: base rates measured from this market's own close history by
    # scripts/calibrate_risk_radar_intl.py (2026-07-16, window 2008-10-22..2026-07-16, n_days=4346; n counts overlapping forward windows, not independent samples).
    # prob_cal is seeded FLAT AT BASE: the in-sample per-state read of this ported
    # construction showed no (or overlap-fragile) loud-tier lift — printed by the
    # harness as a descriptive artifact, never baked. The live forward log + bounded
    # tuner (risk_radar_intl_tune, do-no-harm Brier) own the surface from n_graded>=25.
    prob_base={"h5": 0.032, "h10": 0.089, "h21": 0.185},
    prob_cal={
        "h5":  {"calm": 0.032, "watch": 0.032, "caution": 0.032, "elevated": 0.032, "risk-off": 0.032},
        "h10": {"calm": 0.089, "watch": 0.089, "caution": 0.089, "elevated": 0.089, "risk-off": 0.089},
        "h21": {"calm": 0.185, "watch": 0.185, "caution": 0.185, "elevated": 0.185, "risk-off": 0.185},
    },
    caveat_en=(
        "Ported construction, own-history odds: the external-driver legs (US rate shocks, rupee "
        "depreciation, USD strength) are ported from the China/HK/Canada radar research — their "
        "lead on Nifty 50 drawdowns is assumed from that work, not separately tested here; the "
        "extension leg tracks melt-up regimes. Odds are measured from Nifty 50 index's own "
        "~19y — the shortest history here; display-only while the forward log accrues. Context, "
        "sized — not a forecast."
    ),
    caveat_zh=(
        "构建为移植、赔率取自自身历史：外部驱动腿（美债利率冲击、卢比贬值、美元走强）移植自中国／香港／加拿大雷达研究，"
        "其对Nifty 50指数回撤的领先性沿用该研究结论、未在本市场单独检验；伸展腿用于捕捉抛物线式过热行情。"
        "赔率测自Nifty 50指数自身约19年（本组中最短）历史；前向日志累积期间仅作展示。用于定仓的背景，而非预测。"
    ),
    fx_pair=("intl", "USDINR=X"),
    fx_risk_sign=1,
    fx_code="inr_depreciation",
    ext_sources=(
        ("intl", "^NSEI", "ext_idx"),
        ("intl_etf", "INDA", "ext_etf"),
    ),
    gate_mode="below_or_recent_parabolic",
    disclaimer=_INTL_7_DISCLAIMER,
)

AU_PROFILE = RadarProfile(
    key="au",
    bench=("intl", "^AXJO"),
    breadth_group=None, breadth_code="au_breadth",
    comp_legs=(
        ("rateshock", ("us_rate_2y", "us_real_rate", "us_rate_10y"), 1.0),
        ("fx",        ("aud_depreciation",),                          0.6),
        ("extension", ("ext_idx", "ext_etf"),                         1.0),
    ),
    scares=(
        ("rate_shock", "A", "US rate shock", "美债利率冲击",
         ("rateshock",), ("us_rate_2y", "us_real_rate", "us_rate_10y")),
        ("capital_flow", "A", "AUD depreciation / outflows", "澳元贬值／资金外流",
         ("fx",), ("aud_depreciation",)),
        ("extension", "A", "Parabolic extension / exhaustion", "抛物线伸展／透支",
         ("extension",), ("ext_idx", "ext_etf")),
    ),
    bands=_BANDS,
    # prob surfaces: base rates measured from this market's own close history by
    # scripts/calibrate_risk_radar_intl.py (2026-07-16, window 1997-07-24..2026-07-16, n_days=7325; n counts overlapping forward windows, not independent samples).
    # prob_cal is seeded FLAT AT BASE: the in-sample per-state read of this ported
    # construction showed no (or overlap-fragile) loud-tier lift — printed by the
    # harness as a descriptive artifact, never baked. The live forward log + bounded
    # tuner (risk_radar_intl_tune, do-no-harm Brier) own the surface from n_graded>=25.
    prob_base={"h5": 0.024, "h10": 0.064, "h21": 0.154},
    prob_cal={
        "h5":  {"calm": 0.024, "watch": 0.024, "caution": 0.024, "elevated": 0.024, "risk-off": 0.024},
        "h10": {"calm": 0.064, "watch": 0.064, "caution": 0.064, "elevated": 0.064, "risk-off": 0.064},
        "h21": {"calm": 0.154, "watch": 0.154, "caution": 0.154, "elevated": 0.154, "risk-off": 0.154},
    },
    caveat_en=(
        "Ported construction, own-history odds: the external-driver legs (US rate shocks, AUD "
        "depreciation, USD strength) are ported from the China/HK/Canada radar research — their "
        "lead on ASX 200 drawdowns is assumed from that work, not separately tested here; the "
        "extension leg tracks melt-up regimes. Odds are measured from ASX 200 index's own "
        "~30y (capped) history; display-only while the forward log accrues. Context, sized "
        "— not a forecast."
    ),
    caveat_zh=(
        "构建为移植、赔率取自自身历史：外部驱动腿（美债利率冲击、澳元贬值、美元走强）移植自中国／香港／加拿大雷达研究，"
        "其对ASX 200指数回撤的领先性沿用该研究结论、未在本市场单独检验；伸展腿用于捕捉抛物线式过热行情。"
        "赔率测自ASX 200指数自身约30年（上限截取）历史；前向日志累积期间仅作展示。用于定仓的背景，而非预测。"
    ),
    fx_pair=("intl", "AUDUSD=X"),
    fx_risk_sign=-1,
    fx_code="aud_depreciation",
    ext_sources=(
        ("intl", "^AXJO", "ext_idx"),
        ("intl_etf", "EWA", "ext_etf"),
    ),
    gate_mode="below_or_recent_parabolic",
    disclaimer=_INTL_7_DISCLAIMER,
)

GB_PROFILE = RadarProfile(
    key="gb",
    bench=("intl", "^FTSE"),
    breadth_group=None, breadth_code="gb_breadth",
    comp_legs=(
        ("rateshock", ("us_rate_2y", "us_real_rate", "us_rate_10y"), 1.0),
        ("fx",        ("gbp_depreciation",),                          0.6),
        ("extension", ("ext_idx", "ext_etf"),                         1.0),
    ),
    scares=(
        ("rate_shock", "A", "US rate shock", "美债利率冲击",
         ("rateshock",), ("us_rate_2y", "us_real_rate", "us_rate_10y")),
        ("capital_flow", "A", "Sterling depreciation / outflows", "英镑贬值／资金外流",
         ("fx",), ("gbp_depreciation",)),
        ("extension", "A", "Parabolic extension / exhaustion", "抛物线伸展／透支",
         ("extension",), ("ext_idx", "ext_etf")),
    ),
    bands=_BANDS,
    # prob surfaces: base rates measured from this market's own close history by
    # scripts/calibrate_risk_radar_intl.py (2026-07-16, window 1997-07-23..2026-07-15, n_days=7319; n counts overlapping forward windows, not independent samples).
    # prob_cal is seeded FLAT AT BASE: the in-sample per-state read of this ported
    # construction showed no (or overlap-fragile) loud-tier lift — printed by the
    # harness as a descriptive artifact, never baked. The live forward log + bounded
    # tuner (risk_radar_intl_tune, do-no-harm Brier) own the surface from n_graded>=25.
    prob_base={"h5": 0.037, "h10": 0.087, "h21": 0.186},
    prob_cal={
        "h5":  {"calm": 0.037, "watch": 0.037, "caution": 0.037, "elevated": 0.037, "risk-off": 0.037},
        "h10": {"calm": 0.087, "watch": 0.087, "caution": 0.087, "elevated": 0.087, "risk-off": 0.087},
        "h21": {"calm": 0.186, "watch": 0.186, "caution": 0.186, "elevated": 0.186, "risk-off": 0.186},
    },
    caveat_en=(
        "Ported construction, own-history odds: the external-driver legs (US rate shocks, sterling "
        "depreciation, USD strength) are ported from the China/HK/Canada radar research — their "
        "lead on FTSE 100 drawdowns is assumed from that work, not separately tested here; the "
        "extension leg tracks melt-up regimes. Odds are measured from FTSE 100 index's own "
        "~30y (capped) history; display-only while the forward log accrues. Context, sized "
        "— not a forecast."
    ),
    caveat_zh=(
        "构建为移植、赔率取自自身历史：外部驱动腿（美债利率冲击、英镑贬值、美元走强）移植自中国／香港／加拿大雷达研究，"
        "其对富时100指数回撤的领先性沿用该研究结论、未在本市场单独检验；伸展腿用于捕捉抛物线式过热行情。"
        "赔率测自富时100指数自身约30年（上限截取）历史；前向日志累积期间仅作展示。用于定仓的背景，而非预测。"
    ),
    fx_pair=("intl", "GBPUSD=X"),
    fx_risk_sign=-1,
    fx_code="gbp_depreciation",
    ext_sources=(
        ("intl", "^FTSE", "ext_idx"),
        ("intl_etf", "EWU", "ext_etf"),
    ),
    gate_mode="below_or_recent_parabolic",
    disclaimer=_INTL_7_DISCLAIMER,
)

EZ_PROFILE = RadarProfile(
    key="ez",
    bench=("intl", "^STOXX"),
    breadth_group=None, breadth_code="ez_breadth",
    comp_legs=(
        ("rateshock", ("us_rate_2y", "us_real_rate", "us_rate_10y"), 1.0),
        ("fx",        ("eur_depreciation",),                          0.6),
        ("extension", ("ext_idx", "ext_etf"),                         1.0),
    ),
    scares=(
        ("rate_shock", "A", "US rate shock", "美债利率冲击",
         ("rateshock",), ("us_rate_2y", "us_real_rate", "us_rate_10y")),
        ("capital_flow", "A", "Euro depreciation / outflows", "欧元贬值／资金外流",
         ("fx",), ("eur_depreciation",)),
        ("extension", "A", "Parabolic extension / exhaustion", "抛物线伸展／透支",
         ("extension",), ("ext_idx", "ext_etf")),
    ),
    bands=_BANDS,
    # prob surfaces: base rates measured from this market's own close history by
    # scripts/calibrate_risk_radar_intl.py (2026-07-16, window 2005-05-18..2026-07-15, n_days=5314; n counts overlapping forward windows, not independent samples).
    # prob_cal is seeded FLAT AT BASE: the in-sample per-state read of this ported
    # construction showed no (or overlap-fragile) loud-tier lift — printed by the
    # harness as a descriptive artifact, never baked. The live forward log + bounded
    # tuner (risk_radar_intl_tune, do-no-harm Brier) own the surface from n_graded>=25.
    prob_base={"h5": 0.043, "h10": 0.102, "h21": 0.200},
    prob_cal={
        "h5":  {"calm": 0.043, "watch": 0.043, "caution": 0.043, "elevated": 0.043, "risk-off": 0.043},
        "h10": {"calm": 0.102, "watch": 0.102, "caution": 0.102, "elevated": 0.102, "risk-off": 0.102},
        "h21": {"calm": 0.200, "watch": 0.200, "caution": 0.200, "elevated": 0.200, "risk-off": 0.200},
    },
    caveat_en=(
        "Ported construction, own-history odds: the external-driver legs (US rate shocks, euro "
        "depreciation, USD strength) are ported from the China/HK/Canada radar research — their "
        "lead on STOXX Europe 600 drawdowns is assumed from that work, not separately tested here; "
        "the extension leg tracks melt-up regimes across a basket of country ETFs (EWG/EWQ/EWI/EWP "
        "— no single deep-history eurozone ETF is available). Odds are measured from the STOXX "
        "Europe 600 index's own ~22y history; display-only while the forward log accrues. Context, "
        "sized — not a forecast."
    ),
    caveat_zh=(
        "构建为移植、赔率取自自身历史：外部驱动腿（美债利率冲击、欧元贬值、美元走强）移植自中国／香港／加拿大雷达研究，"
        "其对斯托克欧洲600指数回撤的领先性沿用该研究结论、未在本市场单独检验；伸展腿通过国家ETF篮子（EWG／EWQ／EWI／EWP）"
        "捕捉欧元区整体过热行情（无单一长历史欧元区ETF可用）。赔率测自斯托克欧洲600指数自身约22年历史；"
        "前向日志累积期间仅作展示。用于定仓的背景，而非预测。"
    ),
    fx_pair=("intl", "EURUSD=X"),
    fx_risk_sign=-1,
    fx_code="eur_depreciation",
    ext_sources=(
        ("intl", "^STOXX", "ext_idx"),
        ("intl_etf", ("EWG", "EWQ", "EWI", "EWP"), "ext_etf"),
    ),
    gate_mode="below_or_recent_parabolic",
    disclaimer=_INTL_7_DISCLAIMER,
)

PROFILES = {
    "cn": CN_PROFILE,
    "hk": HK_PROFILE,
    "ca": CA_PROFILE,
    "kr": KR_PROFILE,
    "jp": JP_PROFILE,
    "tw": TW_PROFILE,
    "in": IN_PROFILE,
    "au": AU_PROFILE,
    "gb": GB_PROFILE,
    "ez": EZ_PROFILE,
}
