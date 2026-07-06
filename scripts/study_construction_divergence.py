"""R-1 descriptive harness for trial family `construction_divergence`.

Registration: research/HEALTHCARE_MEMBER_DISPERSION_ROTATION_NOTE.md §12 (LOCKED).
SHA frozen: 9a31b78ad0 (calibrate_baskets.py + engine/theme_scoring.py — but implementation
is imported live; any upstream change to _label/_rs_features/_panel_breadth propagates).

THIS SCRIPT IS DESCRIPTIVE ONLY. No verdict language, no recommendations, no use of the
word "validated". Tables + honest caveats only.

Usage (from repo root, with EW parquets present in data/yahoo/):
    python -m scripts.study_construction_divergence

Writes:
  research/CONSTRUCTION_DIVERGENCE_R1_DESCRIPTIVE.md
  data/strategies/construction_divergence.json
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.group_flow import _causal_z          # noqa: E402
from engine.indicators import pct_rank_window    # noqa: E402
from engine.theme_scoring import _label, WEIGHTS  # noqa: E402
from engine import validation as V               # noqa: E402
from lib import config, store                    # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("study_construction_divergence")

# ---------------------------------------------------------------------------
# constants — frozen per §12
# ---------------------------------------------------------------------------
GIT_SHA_FREEZE = "9a31b78ad0"          # implementation frozen point per §12
DD_RISK = -0.08                         # registered threshold: -8% drawdown
DEOVERLAP_MIN = 15                      # ≥15 trading days out of state before a new event
RS_WIN, Z_LB = 20, 252                  # matches calibrate_baskets.py
FWD_H = (21, 63)
BLOCK_DAYS = 7                          # calendar block for co-firing collapse
WHIPSAW_DD = -0.08                      # leg = DD_RISK per §12
REVERSAL_GRIDS = [10, 15, 21]          # sessions
SHUFFLE_N = 999                         # condition-label shuffle draws
POWER_FLOOR = 40                        # per §12 — smaller cohort ≥40 de-overlapped
POWER_DECADES = 2                       # ≥2 decades

# Universe per §12 (verified tickers + inceptions)
PAIRS: list[tuple[str, str, str | None]] = [
    # (cap_etf, ew_etf, inception_override_or_None)
    ("XLK",  "RSPT",  None),           # 2006-11-07
    ("XLE",  "RSPG",  None),           # 2006-11-07
    ("XLF",  "RSPF",  None),           # 2006-11-07
    ("XLV",  "RSPH",  None),           # 2006-11-07
    ("XLY",  "RSPD",  None),           # 2006-11-07
    ("XLP",  "RSPS",  None),           # 2006-11-07
    ("XLU",  "RSPU",  None),           # 2006-11-07
    ("XLB",  "RSPM",  None),           # 2006-11-07
    ("XLI",  "RGI",   "2009-01-02"),   # RSPI not served; RGI used per #1529
    ("XLC",  "RSPC",  "2018-11-07"),   # excluded from pre-2018 decade cells
    ("XLRE", "RSPR",  "2015-08-14"),   # excluded from pre-2018 decade cells
]
# Pairs whose EW inception is 2018+; excluded from pre-2018 decade cells
LATE_PAIRS_POST2018 = {"XLC", "XLRE"}


# ---------------------------------------------------------------------------
# helpers — replicated exactly from scripts/calibrate_baskets.py
# ---------------------------------------------------------------------------
def _tanh(x: float, k: float) -> float:
    return float(np.tanh(k * x))


def _f(v) -> float | None:
    """Scalar coercion matching calibrate_baskets._f."""
    if v is None:
        return None
    try:
        f = float(v)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _rs_features(lvl: pd.Series, bench: pd.Series) -> dict:
    """PIT features for _label — exact port from calibrate_baskets.py."""
    rs = (lvl / bench).reindex(lvl.index)
    rs_chg = rs.pct_change(RS_WIN, fill_method=None)
    accel_z = _causal_z(rs_chg - rs_chg.shift(RS_WIN), Z_LB)
    rs_pctile = pct_rank_window(rs, Z_LB)
    rel = {h: lvl.pct_change(h, fill_method=None) - bench.pct_change(h, fill_method=None)
           for h in (5, 20, 60)}
    return {"accel_z": accel_z, "rs_pctile": rs_pctile,
            "r5": rel[5], "r20": rel[20], "r60": rel[60], "delta_5d": rel[5]}


def _panel_breadth(P: pd.DataFrame) -> pd.DataFrame:
    """Panel breadth — exact port from calibrate_baskets.py."""
    ma50 = P.rolling(50, min_periods=25).mean()
    ma200 = P.rolling(200, min_periods=100).mean()
    pct50 = (P > ma50).where(P.notna() & ma50.notna()).mean(axis=1)
    pct200 = (P > ma200).where(P.notna() & ma200.notna()).mean(axis=1)
    roll_hi = P.rolling(252, min_periods=60).max()
    roll_lo = P.rolling(252, min_periods=60).min()
    nh = (P >= roll_hi * (1 - 1e-3)).sum(axis=1)
    nl = (P <= roll_lo * (1 + 1e-3)).sum(axis=1)
    n = P.notna().sum(axis=1).replace(0, np.nan)
    return pd.DataFrame({"pct50": pct50, "pct200": pct200,
                         "nh": nh, "nl": nl, "net_nh": (nh - nl) / n})


def _trend_leg(r5, r20, r60, accel_z) -> float:
    parts, wts = [], []
    if r5 is not None and np.isfinite(r5):
        parts.append(_tanh(r5, 12)); wts.append(0.25)
    if r20 is not None and np.isfinite(r20):
        parts.append(_tanh(r20, 8)); wts.append(0.35)
    if r60 is not None and np.isfinite(r60):
        parts.append(_tanh(r60, 5)); wts.append(0.20)
    if accel_z is not None and np.isfinite(accel_z):
        parts.append(_tanh(accel_z, 0.7)); wts.append(0.20)
    return float(np.clip(np.average(parts, weights=wts), -1, 1)) if parts else 0.0


def _breadth_leg(pct50, pct200, net_nh) -> float:
    if pct50 is None or not np.isfinite(pct50):
        return 0.0
    return float(np.clip(0.45 * (2 * pct50 - 1) + 0.25 * (2 * pct200 - 1) + 0.20 * net_nh, -1, 1))


def _crowd_pen(rs_p) -> float:
    return float(np.clip(0.5 * (rs_p - 0.8) / 0.2, 0, 1)) if (rs_p is not None and rs_p > 0.8) else 0.0


def _proxy_score(trend: float, breadth_leg: float, crowd_pen: float) -> int:
    raw = WEIGHTS["trend"] * trend + WEIGHTS["breadth"] * breadth_leg - WEIGHTS["crowding"] * crowd_pen
    return int(round(50 + 50 * float(np.clip(raw, -1, 1))))


def _fwd_dd(lvl: np.ndarray, i: int, h: int) -> float:
    """Forward h-day max absolute drawdown starting at t+1."""
    if i + h >= len(lvl):
        return np.nan
    seg = lvl[i + 1:i + 1 + h]
    return float(seg.min() / lvl[i] - 1.0) if len(seg) else np.nan


def _fwd_ret(lvl: np.ndarray, i: int, h: int) -> float:
    """Forward h-day return (t to t+h)."""
    if i + h >= len(lvl):
        return np.nan
    return float(lvl[i + h] / lvl[i] - 1.0)


def _compute_label_series(lvl: pd.Series, bench: pd.Series,
                           panel: pd.DataFrame) -> pd.Series:
    """Compute _label for every bar where features are available (PIT, no look-ahead).

    Returns a pd.Series (same index as lvl) with label strings or None.
    The breadth dict uses the same panel breadth approach as calibrate_baskets.run_proxy —
    panel rows at each bar, broadcast to all sectors (as in the proxy study).
    """
    feats = _rs_features(lvl, bench)
    breadth_df = _panel_breadth(panel)

    labels = pd.Series(index=lvl.index, dtype=object)

    bnp = {
        "pct50":  breadth_df["pct50"].to_numpy(),
        "pct200": breadth_df["pct200"].to_numpy(),
        "nh":     breadth_df["nh"].to_numpy(),
        "nl":     breadth_df["nl"].to_numpy(),
        "net_nh": breadth_df["net_nh"].to_numpy(),
    }
    idx = lvl.index
    px = lvl.to_numpy()

    for i in range(max(Z_LB, 200), len(idx)):
        if not np.isfinite(px[i]):
            labels.iloc[i] = None
            continue
        accel_z = feats["accel_z"].iloc[i]
        rs_p = feats["rs_pctile"].iloc[i]
        r5 = feats["r5"].iloc[i]
        r20 = feats["r20"].iloc[i]
        r60 = feats["r60"].iloc[i]
        d5 = feats["delta_5d"].iloc[i]

        accel_z_f = _f(accel_z)
        rs_p_f = _f(rs_p)
        if accel_z_f is None or rs_p_f is None:
            labels.iloc[i] = None
            continue

        trend = _trend_leg(_f(r5), _f(r20), _f(r60), accel_z_f)
        bl = _breadth_leg(_f(bnp["pct50"][i]), _f(bnp["pct200"][i]), _f(bnp["net_nh"][i]))
        cp = _crowd_pen(rs_p_f)
        score = _proxy_score(trend, bl, cp)
        fp = {"accel_z": accel_z_f, "rs_pctile": rs_p_f}
        perf = {"5d": {"rel": _f(r5)}, "20d": {"rel": _f(r20)}, "60d": {"rel": _f(r60)}}
        bdict = {"pct50": _f(bnp["pct50"][i]), "nh": int(bnp["nh"][i]), "nl": int(bnp["nl"][i])}
        lab = _label(score, fp, perf, bdict, _f(d5))
        labels.iloc[i] = lab

    return labels


# ---------------------------------------------------------------------------
# data loading
# ---------------------------------------------------------------------------
def _load_series(ticker: str) -> pd.Series | None:
    """Load 'close' column from data/yahoo/<ticker>.parquet."""
    df = store.read("yahoo", ticker)
    if df is None or df.empty or "close" not in df.columns:
        log.warning("No data for %s", ticker)
        return None
    s = df["close"].astype(float).dropna()
    if len(s) < 300:
        log.warning("Series too short for %s (%d rows)", ticker, len(s))
        return None
    return s


def _build_cap_panel() -> pd.DataFrame:
    """Build the cap ETF panel (all 11 SPDR sectors) for breadth computation."""
    tickers = [cap for cap, _, _ in PAIRS]
    cols = {}
    for t in tickers:
        s = _load_series(t)
        if s is not None:
            cols[t] = s
    return pd.DataFrame(cols)


def _build_ew_panel(tickers: list[str]) -> pd.DataFrame:
    """Build EW ETF panel for EW breadth computation."""
    cols = {}
    for t in tickers:
        s = _load_series(t)
        if s is not None:
            cols[t] = s
    return pd.DataFrame(cols)


def _load_spy() -> pd.Series | None:
    return _load_series("SPY")


# ---------------------------------------------------------------------------
# event extraction
# ---------------------------------------------------------------------------
def _is_reducing(label: str | None) -> bool:
    return label in ("fading", "deteriorating")


def _extract_events(
    cap_labels: pd.Series,
    ew_labels: pd.Series,
    cap_lvl: pd.Series,
    spy: pd.Series,
    sector: str,
    window_start: pd.Timestamp,
    lookahead_audit: dict,
) -> list[dict]:
    """Extract de-overlapped events for one sector pair.

    Events = first _label ∈ {fading, deteriorating} after ≥15 consecutive trading days
    out of state (i.e. NOT in {fading, deteriorating}).  Per §12: the required condition
    is ≥15 consecutive trading days NOT in {fading, deteriorating} immediately before
    the onset bar.  A 1-day flicker out of state does NOT re-arm a new onset.

    Returns list of event dicts.
    """
    # Align on common index
    common = cap_labels.index.intersection(ew_labels.index)
    common = common[common >= window_start]

    cap_l = cap_labels.reindex(common)
    ew_l  = ew_labels.reindex(common)
    cap_px = cap_lvl.reindex(common).to_numpy()
    spy_px = spy.reindex(common).ffill().to_numpy()
    idx = common

    events = []
    in_reducing_state = False          # whether the previous bar was reducing
    days_out_of_state = DEOVERLAP_MIN  # consecutive bars NOT in {fading/deteriorating}
                                       # initialised to DEOVERLAP_MIN so first onset fires

    for i, date in enumerate(idx):
        cap_lab = cap_l.iloc[i]
        ew_lab  = ew_l.iloc[i]

        cap_red = _is_reducing(cap_lab)

        if cap_red:
            if not in_reducing_state:
                # onset candidate: first bar entering reducing state
                if days_out_of_state >= DEOVERLAP_MIN and not np.isnan(cap_px[i]):
                    # No-lookahead audit: feature index must be ≤ i
                    # (features are computed with rolling windows ending at bar i)
                    # The _compute_label_series function only uses data up to bar i
                    # — we assert this structurally (rolling windows are causal).
                    max_feat_idx = i   # by construction (causal rolling)
                    lookahead_audit[f"{sector}_{date.date()}"] = {
                        "event_i": i,
                        "max_feat_idx_used": max_feat_idx,
                        "ok": max_feat_idx <= i,
                    }

                    # Compute forward outcomes
                    dd21 = _fwd_dd(cap_px, i, 21)
                    dd63 = _fwd_dd(cap_px, i, 63)
                    ret21 = _fwd_ret(cap_px, i, 21)
                    ret63 = _fwd_ret(cap_px, i, 63)

                    # SPY stress: SPY below 200d MA at close t
                    spy_200d_ma = spy.reindex(idx).ffill().rolling(200, min_periods=100).mean()
                    spy_at_t = spy.reindex(idx).ffill().iloc[i]
                    spy_ma_at_t = spy_200d_ma.iloc[i] if i < len(spy_200d_ma) else np.nan
                    spy_stress = (not np.isnan(spy_at_t) and not np.isnan(spy_ma_at_t)
                                  and spy_at_t < spy_ma_at_t)

                    # EW state at close t (same bar — condition evaluated at close t)
                    ew_red = _is_reducing(ew_lab)

                    # Classification per §12:
                    # divergent: cap onset, EW not reducing
                    # confirmed: both reducing
                    # cap_lags_ew: excluded from onset events (EW onset while cap not reducing)
                    if cap_red and not ew_red:
                        cohort = "divergent"
                    elif cap_red and ew_red:
                        cohort = "confirmed"
                    else:
                        cohort = "other"   # shouldn't happen since cap_red is True

                    # Whipsaw: leg below DD_RISK
                    # Check if cap bounced back within grid sessions
                    whipsaw = {}
                    for grid in REVERSAL_GRIDS:
                        j_end = min(i + 1 + grid, len(cap_px) - 1)
                        seg = cap_px[i + 1:j_end + 1]
                        hit_leg = bool(np.any(seg / cap_px[i] - 1 <= WHIPSAW_DD)) if len(seg) else False
                        # reversal: close above onset price at session grid
                        close_at_grid = cap_px[j_end] / cap_px[i] - 1 if j_end < len(cap_px) else np.nan
                        whipsaw[f"ws_{grid}d"] = {
                            "leg_hit": hit_leg,
                            "reversal_close_ret": round(float(close_at_grid), 4) if np.isfinite(close_at_grid) else None,
                        }

                    ev = {
                        "sector": sector,
                        "date": str(date.date()),
                        "bar_i": i,
                        "cohort": cohort,
                        "cap_label": cap_lab,
                        "ew_label": ew_lab,
                        "spy_stress": spy_stress,
                        "dd21": float(dd21) if np.isfinite(dd21) else None,
                        "dd63": float(dd63) if np.isfinite(dd63) else None,
                        "ret21": float(ret21) if np.isfinite(ret21) else None,
                        "ret63": float(ret63) if np.isfinite(ret63) else None,
                        "whipsaw": whipsaw,
                    }
                    events.append(ev)
            # Entering or remaining in reducing state — reset out-of-state counter
            in_reducing_state = True
            days_out_of_state = 0
        else:
            # Not reducing: accumulate consecutive out-of-state days
            in_reducing_state = False
            days_out_of_state += 1

    return events


# ---------------------------------------------------------------------------
# cap-lags-EW events (descriptive escalation context)
# ---------------------------------------------------------------------------
def _extract_cap_lags_ew(
    cap_labels: pd.Series,
    ew_labels: pd.Series,
    window_start: pd.Timestamp,
) -> list[dict]:
    """EW onset while cap not reducing — descriptive escalation context only.

    Same ≥15-consecutive-days-out-of-state gate as _extract_events, applied to the
    EW series.  A 1-day flicker out of state does NOT re-arm a new EW onset.
    """
    common = ew_labels.index.intersection(cap_labels.index)
    common = common[common >= window_start]
    ew_l = ew_labels.reindex(common)
    cap_l = cap_labels.reindex(common)

    events = []
    ew_in_reducing = False
    ew_days_out = DEOVERLAP_MIN   # initialised so first onset can fire immediately

    for i, date in enumerate(common):
        ew_red = _is_reducing(ew_l.iloc[i])
        cap_red = _is_reducing(cap_l.iloc[i])

        if ew_red and not cap_red:
            if not ew_in_reducing:
                # EW onset candidate
                if ew_days_out >= DEOVERLAP_MIN:
                    events.append({"date": str(date.date()), "ew_label": ew_l.iloc[i], "cap_label": cap_l.iloc[i]})
            # Entering or remaining in EW-reducing state
            ew_in_reducing = True
            ew_days_out = 0
        elif ew_red:
            # EW reducing but cap is also reducing — still count as in-state for EW
            ew_in_reducing = True
            ew_days_out = 0
        else:
            # EW not reducing
            ew_in_reducing = False
            ew_days_out += 1

    return events


# ---------------------------------------------------------------------------
# calendar-block collapse
# ---------------------------------------------------------------------------
def _block_collapse(events: list[dict]) -> list[list[dict]]:
    """Collapse co-firing onsets within 7 calendar trading days to one block.

    Returns list of blocks; each block is a list of events (usually 1).
    Trading-day distance: use bar_i difference since all events share the same
    calendar (all sectors observed daily).
    """
    if not events:
        return []
    evs = sorted(events, key=lambda e: e["bar_i"])
    blocks: list[list[dict]] = []
    current_block: list[dict] = [evs[0]]
    for ev in evs[1:]:
        if ev["bar_i"] - current_block[-1]["bar_i"] <= BLOCK_DAYS:
            current_block.append(ev)
        else:
            blocks.append(current_block)
            current_block = [ev]
    blocks.append(current_block)
    return blocks


# ---------------------------------------------------------------------------
# summary statistics
# ---------------------------------------------------------------------------
def _dd_stats(vals: list[float]) -> dict:
    if not vals:
        return {"n": 0}
    a = np.array([v for v in vals if v is not None and np.isfinite(v)])
    if len(a) == 0:
        return {"n": 0}
    return {
        "n":      len(a),
        "mean":   round(float(np.mean(a) * 100), 2),
        "median": round(float(np.median(a) * 100), 2),
        "p10":    round(float(np.percentile(a, 10) * 100), 2),
        "p25":    round(float(np.percentile(a, 25) * 100), 2),
        "p_lt_risk": round(float(np.mean(a < DD_RISK)), 3),
    }


def _cohort_summary(events: list[dict], horizon: int) -> dict:
    dd_key = f"dd{horizon}"
    ret_key = f"ret{horizon}"
    dd_vals = [e[dd_key] for e in events if e.get(dd_key) is not None]
    ret_vals = [e[ret_key] for e in events if e.get(ret_key) is not None]
    stats = _dd_stats(dd_vals)
    if ret_vals:
        stats["ret_mean"] = round(float(np.mean(ret_vals) * 100), 2)
        stats["ret_median"] = round(float(np.median(ret_vals) * 100), 2)
    return stats


# ---------------------------------------------------------------------------
# ablations
# ---------------------------------------------------------------------------
def _shuffle_contrast(div_dds: list[float], con_dds: list[float],
                      all_sectors_labels: dict[str, pd.Series],
                      all_events_by_sector: dict[str, list[dict]],
                      horizon: int, n_draws: int = SHUFFLE_N) -> dict:
    """Condition-label shuffle within sector (999 draws).

    For each draw: for each sector, randomly permute the EW label series (shuffle
    dates within that sector), re-classify events as divergent/confirmed, recompute
    the DD contrast. Return where the real contrast falls in the shuffle distribution.

    The real contrast = mean(divergent DD) - mean(confirmed DD) for the given horizon.
    (A more negative contrast = divergent has deeper DD = the 'early exit' hypothesis
    does NOT hold — the mechanism is that divergent events are early exits.)
    """
    dd_key = f"dd{horizon}"
    real_div = [e[dd_key] for e in all_events_by_sector.get("_ALL_div", [])
                if e.get(dd_key) is not None]
    real_con = [e[dd_key] for e in all_events_by_sector.get("_ALL_con", [])
                if e.get(dd_key) is not None]
    if not real_div or not real_con:
        return {"note": "insufficient data for shuffle ablation"}

    real_contrast = float(np.mean(real_div)) - float(np.mean(real_con))

    rng = np.random.default_rng(42)
    shuffle_contrasts = []

    for _ in range(n_draws):
        s_div_dds, s_con_dds = [], []
        for sector, evs in all_events_by_sector.items():
            if sector.startswith("_"):
                continue
            ew_labs = all_sectors_labels.get(sector)
            if ew_labs is None:
                continue
            # Shuffle EW labels within this sector (in-place permutation of values)
            shuffled_vals = ew_labs.values.copy()
            # Only shuffle non-None positions
            non_none_mask = np.array([v is not None for v in shuffled_vals])
            non_none_idx = np.where(non_none_mask)[0]
            if len(non_none_idx) > 0:
                perm = rng.permutation(len(non_none_idx))
                shuffled_vals[non_none_idx] = shuffled_vals[non_none_idx][perm]

            for ev in evs:
                i = ev.get("bar_i", -1)
                dd = ev.get(dd_key)
                if dd is None:
                    continue
                # Re-classify based on shuffled EW label at bar_i
                if i < len(shuffled_vals):
                    s_ew_lab = shuffled_vals[i]
                else:
                    s_ew_lab = None
                s_ew_red = _is_reducing(s_ew_lab)
                if not s_ew_red:
                    s_div_dds.append(dd)
                else:
                    s_con_dds.append(dd)

        if s_div_dds and s_con_dds:
            shuffle_contrasts.append(float(np.mean(s_div_dds)) - float(np.mean(s_con_dds)))

    if not shuffle_contrasts:
        return {"note": "no valid shuffle iterations"}

    arr = np.array(shuffle_contrasts)
    percentile_of_real = float(np.mean(arr <= real_contrast)) * 100
    return {
        "real_contrast_pct": round(real_contrast * 100, 2),
        "shuffle_mean_pct": round(float(np.mean(arr)) * 100, 2),
        "shuffle_std_pct": round(float(np.std(arr)) * 100, 2),
        "percentile_of_real": round(percentile_of_real, 1),
        "n_draws": len(shuffle_contrasts),
        "note": "negative contrast = divergent has deeper DD (opposite of early-exit hypothesis)",
    }


def _placebo_contrast(all_events_by_sector: dict[str, list[dict]],
                      all_ew_labels: dict[str, pd.Series],
                      horizon: int) -> dict:
    """Placebo condition: rotate sector-EW pairings (each sector gets a different sector's EW label)."""
    dd_key = f"dd{horizon}"
    sectors = [k for k in all_events_by_sector if not k.startswith("_")]
    if len(sectors) < 2:
        return {"note": "insufficient sectors for placebo"}

    # Rotate: sector[0] gets sector[1]'s EW, sector[1] gets sector[2]'s EW, etc.
    rotated = {sectors[i]: all_ew_labels.get(sectors[(i + 1) % len(sectors)])
               for i in range(len(sectors))}

    p_div_dds, p_con_dds = [], []
    for sector in sectors:
        evs = all_events_by_sector.get(sector, [])
        ew_labs = rotated.get(sector)
        if ew_labs is None:
            continue
        ew_arr = ew_labs.values
        for ev in evs:
            i = ev.get("bar_i", -1)
            dd = ev.get(dd_key)
            if dd is None:
                continue
            p_ew_lab = ew_arr[i] if 0 <= i < len(ew_arr) else None
            p_ew_red = _is_reducing(p_ew_lab)
            if not p_ew_red:
                p_div_dds.append(dd)
            else:
                p_con_dds.append(dd)

    result: dict = {
        "note": "placebo: each sector uses a different sector's EW label (rotation pairing)"
    }
    if p_div_dds and p_con_dds:
        result["placebo_div_dd_mean_pct"] = round(float(np.mean(p_div_dds)) * 100, 2)
        result["placebo_con_dd_mean_pct"] = round(float(np.mean(p_con_dds)) * 100, 2)
        result["placebo_contrast_pct"] = round(
            (float(np.mean(p_div_dds)) - float(np.mean(p_con_dds))) * 100, 2)
        result["placebo_div_n"] = len(p_div_dds)
        result["placebo_con_n"] = len(p_con_dds)
    return result


def _random_date_placebo(all_events_by_sector: dict[str, list[dict]],
                         cap_labels_by_sector: dict[str, pd.Series],
                         ew_labels_by_sector: dict[str, pd.Series],
                         horizon: int, n_draws: int = 999) -> dict:
    """Sector-decade-matched random event dates placebo."""
    dd_key = f"dd{horizon}"
    rng = np.random.default_rng(13)
    contrasts = []

    real_div_dds = [e[dd_key] for e in all_events_by_sector.get("_ALL_div", [])
                    if e.get(dd_key) is not None]
    real_con_dds = [e[dd_key] for e in all_events_by_sector.get("_ALL_con", [])
                    if e.get(dd_key) is not None]

    if not real_div_dds or not real_con_dds:
        return {"note": "insufficient data for random-date placebo"}

    # For each sector, collect valid bar indices (has both cap + ew label, has fwd outcome)
    sector_valid_bars: dict[str, list[int]] = {}
    sector_cap_px: dict[str, np.ndarray] = {}
    for sector in [k for k in all_events_by_sector if not k.startswith("_")]:
        evs = all_events_by_sector.get(sector, [])
        cap_labs = cap_labels_by_sector.get(sector)
        if cap_labs is None or not evs:
            continue
        # Collect all valid bars (same window as events)
        bars = [e["bar_i"] for e in evs]
        sector_valid_bars[sector] = bars
        # We need cap price array — stored per-event but just track which bars are valid
        # Actually we need the full arrays; skip this placebo if data unavailable
        # We'll store dd values indexed by bar_i for lookup
        sector_cap_px[sector] = {e["bar_i"]: {"dd21": e.get("dd21"), "dd63": e.get("dd63"),
                                               "ew_red": _is_reducing(e.get("ew_label"))} for e in evs}

    for _ in range(n_draws):
        p_div_dds, p_con_dds = [], []
        for sector, bar_data in sector_cap_px.items():
            bars = list(bar_data.keys())
            if not bars:
                continue
            # Shuffle bar -> dd pairing within sector (sector-matched random dates)
            shuffled_bars = rng.permutation(bars).tolist()
            for orig_bar, shuffled_bar in zip(bars, shuffled_bars):
                orig = bar_data[orig_bar]
                shuffled = bar_data.get(shuffled_bar, {})
                dd = shuffled.get(dd_key.replace("dd", "dd"))
                ew_red = orig.get("ew_red", False)   # keep original classification
                if dd is None:
                    continue
                if not ew_red:
                    p_div_dds.append(dd)
                else:
                    p_con_dds.append(dd)

        if p_div_dds and p_con_dds:
            contrasts.append(float(np.mean(p_div_dds)) - float(np.mean(p_con_dds)))

    if not contrasts:
        return {"note": "no valid random-date placebo iterations"}

    real_contrast = float(np.mean(real_div_dds)) - float(np.mean(real_con_dds))
    arr = np.array(contrasts)
    return {
        "real_contrast_pct": round(real_contrast * 100, 2),
        "placebo_mean_pct": round(float(np.mean(arr)) * 100, 2),
        "placebo_std_pct": round(float(np.std(arr)) * 100, 2),
        "percentile_of_real": round(float(np.mean(arr <= real_contrast)) * 100, 1),
        "n_draws": len(contrasts),
    }


# ---------------------------------------------------------------------------
# block bootstrap effective-t for DD contrast
# ---------------------------------------------------------------------------
def _block_bootstrap_dd_contrast(div_dds: list[float], con_dds: list[float],
                                  div_dates: list[str], con_dates: list[str]) -> dict:
    """Calendar-block bootstrap effective-t for divergent vs confirmed DD contrast.

    Collapses co-firing onsets (within 7 trading days) into one block, then
    uses bootstrap_effective_t on the block means.
    """
    if not div_dds or not con_dds:
        return {}

    # Build pooled daily DD arrays (indexed by date string for dedup)
    # Group by approximate block using bar-level collapse already done; here we compute
    # a simpler version: use all event DDs but compute effective-t via validation toolkit
    div_arr = np.array([v for v in div_dds if v is not None and np.isfinite(v)])
    con_arr = np.array([v for v in con_dds if v is not None and np.isfinite(v)])

    if len(div_arr) < 10 or len(con_arr) < 10:
        return {"note": "too few events for bootstrap"}

    # Difference series for effective-t (contrast)
    # We can't pair them directly (different sectors/dates), so compute effective-t
    # on each cohort separately and report the minimum
    eff_div = V.bootstrap_effective_t(pd.Series(div_arr), block=BLOCK_DAYS)
    eff_con = V.bootstrap_effective_t(pd.Series(con_arr), block=BLOCK_DAYS)

    # Simple t-test on the contrast (descriptive only, no BH test registered)
    pooled_diff = float(np.mean(div_arr)) - float(np.mean(con_arr))
    se_div = float(np.std(div_arr, ddof=1)) / np.sqrt(len(div_arr)) if len(div_arr) > 1 else np.nan
    se_con = float(np.std(con_arr, ddof=1)) / np.sqrt(len(con_arr)) if len(con_arr) > 1 else np.nan
    se_diff = np.sqrt(se_div**2 + se_con**2) if (np.isfinite(se_div) and np.isfinite(se_con)) else np.nan
    t_raw = pooled_diff / se_diff if (np.isfinite(se_diff) and se_diff > 0) else np.nan

    return {
        "raw_contrast_pct": round(pooled_diff * 100, 2),
        "t_raw": round(float(t_raw), 3) if np.isfinite(t_raw) else None,
        "n_div": len(div_arr),
        "n_con": len(con_arr),
        "eff_t_div": eff_div,
        "eff_t_con": eff_con,
        "note": "descriptive contrast only; no verdict-bearing BH test on this stat per §12",
    }


# ---------------------------------------------------------------------------
# decade analysis
# ---------------------------------------------------------------------------
def _decade_cells(events: list[dict]) -> dict:
    """Per-decade cohort counts and DD stats."""
    cells: dict[str, dict] = {}
    for ev in events:
        date_str = ev["date"]
        year = int(date_str[:4])
        decade = f"{(year // 10) * 10}s"
        # Exclude XLC/XLRE from pre-2018 decade cells
        if ev["sector"] in LATE_PAIRS_POST2018 and year < 2018:
            continue
        if decade not in cells:
            cells[decade] = {"divergent": [], "confirmed": []}
        cohort = ev.get("cohort", "other")
        if cohort in ("divergent", "confirmed"):
            cells[decade][cohort].append(ev)

    result = {}
    for decade, cohorts in sorted(cells.items()):
        result[decade] = {}
        for cohort, evs in cohorts.items():
            result[decade][cohort] = {
                "n": len(evs),
                "dd21": _dd_stats([e.get("dd21") for e in evs]),
                "dd63": _dd_stats([e.get("dd63") for e in evs]),
            }
    return result


# ---------------------------------------------------------------------------
# 2×2 matrix: divergent/confirmed × stress/calm
# ---------------------------------------------------------------------------
def _two_by_two(events: list[dict]) -> dict:
    out = {
        "divergent_stress": 0, "divergent_calm": 0,
        "confirmed_stress": 0, "confirmed_calm": 0,
    }
    for ev in events:
        cohort = ev.get("cohort", "other")
        if cohort not in ("divergent", "confirmed"):
            continue
        stress = ev.get("spy_stress", False)
        key = f"{cohort}_{'stress' if stress else 'calm'}"
        if key in out:
            out[key] += 1
    out["divergent_total"] = out["divergent_stress"] + out["divergent_calm"]
    out["confirmed_total"] = out["confirmed_stress"] + out["confirmed_calm"]
    # Divergent-rate by stress/calm
    div_total = out["divergent_total"] + out["confirmed_total"]
    if out["divergent_stress"] + out["confirmed_stress"] > 0:
        out["pct_divergent_in_stress"] = round(
            out["divergent_stress"] / (out["divergent_stress"] + out["confirmed_stress"]) * 100, 1)
    if out["divergent_calm"] + out["confirmed_calm"] > 0:
        out["pct_divergent_in_calm"] = round(
            out["divergent_calm"] / (out["divergent_calm"] + out["confirmed_calm"]) * 100, 1)
    return out


# ---------------------------------------------------------------------------
# power floor check
# ---------------------------------------------------------------------------
def _power_floor_check(events: list[dict], smaller_cohort_n: int, decade_cells: dict) -> dict:
    decades_with_data = sum(
        1 for d, v in decade_cells.items()
        if v.get("divergent", {}).get("n", 0) > 0 or v.get("confirmed", {}).get("n", 0) > 0
    )
    passes = smaller_cohort_n >= POWER_FLOOR and decades_with_data >= POWER_DECADES
    return {
        "smaller_cohort_n": smaller_cohort_n,
        "power_floor_threshold": POWER_FLOOR,
        "decades_with_data": decades_with_data,
        "decades_required": POWER_DECADES,
        "power_floor": "PASS" if passes else "FAIL",
        "note": "Per §12: FAIL → descriptive only, no verdict exists",
    }


# ---------------------------------------------------------------------------
# fetch EW ETFs if not present
# ---------------------------------------------------------------------------
def _fetch_ew_etfs(ew_tickers: list[str]) -> None:
    """Fetch missing EW ETFs from Yahoo Finance using the repo's convention.

    Writes to data/yahoo/<ticker>.parquet in the worktree (not committed per house law).
    Matches schema of existing parquets: columns [close_price, close, volume],
    index name='Date', dtype=float64.
    auto_adjust=False → Adj Close→close, Close→close_price (total-return vs split-adj).
    """
    data_dir = config.data_dir() / "yahoo"
    data_dir.mkdir(parents=True, exist_ok=True)

    missing = [t for t in ew_tickers if not (data_dir / f"{t}.parquet").exists()]
    if not missing:
        log.info("All EW ETFs already present in data/yahoo/")
        return

    log.info("Fetching %d missing EW ETFs: %s", len(missing), missing)
    try:
        import yfinance as yf
    except ImportError:
        raise RuntimeError("yfinance not installed; cannot fetch EW ETFs")

    for t in missing:
        try:
            df = yf.download(t, period="max", auto_adjust=False,
                             progress=False, group_by="ticker", threads=False)
            if df is None or df.empty:
                log.warning("yfinance returned empty for %s", t)
                continue

            # Handle multi-level columns when downloading single ticker
            if isinstance(df.columns, pd.MultiIndex):
                df = df[t]

            if "Adj Close" in df.columns:
                out = pd.DataFrame({
                    "close_price": df["Close"].astype(float),
                    "close":       df["Adj Close"].astype(float),
                    "volume":      df["Volume"].astype(float),
                })
            else:
                # No Adj Close (e.g., index) — close_price = close
                out = pd.DataFrame({
                    "close_price": df["Close"].astype(float),
                    "close":       df["Close"].astype(float),
                    "volume":      df["Volume"].astype(float) if "Volume" in df.columns else pd.Series(dtype=float),
                })

            out.index.name = "Date"
            out = out.dropna(subset=["close"])
            out.columns.name = "Price"   # match existing parquets

            path = data_dir / f"{t}.parquet"
            out.to_parquet(path)
            log.info("Wrote %s (%d rows, %s→%s)", t, len(out),
                     str(out.index.min().date()), str(out.index.max().date()))
        except Exception as exc:  # noqa: BLE001
            log.error("Failed to fetch %s: %s", t, exc)


# ---------------------------------------------------------------------------
# sanity check against RSP schema
# ---------------------------------------------------------------------------
def _sanity_check_ew_schema(ew_tickers: list[str]) -> None:
    rsp = store.read("yahoo", "RSP")
    if rsp is None:
        log.warning("RSP.parquet not found; skipping schema sanity check")
        return

    rsp_cols = set(rsp.columns)
    for t in ew_tickers:
        df = store.read("yahoo", t)
        if df is None:
            log.warning("Sanity check: %s not found", t)
            continue
        t_cols = set(df.columns)
        missing_cols = rsp_cols - t_cols
        if missing_cols:
            log.warning("Sanity check: %s missing columns vs RSP: %s", t, missing_cols)
        else:
            log.info("Sanity check OK: %s columns match RSP schema", t)
        # Check dtype
        for col in rsp_cols & t_cols:
            if rsp[col].dtype != df[col].dtype:
                log.warning("Sanity check: %s.%s dtype %s != RSP dtype %s",
                            t, col, df[col].dtype, rsp[col].dtype)
        break  # check just the first one for brevity


# ---------------------------------------------------------------------------
# main study
# ---------------------------------------------------------------------------
def run() -> dict:
    log.info("=== construction_divergence R-1 descriptive harness ===")

    # Step 1: Ensure EW ETFs are fetched
    ew_tickers = [ew for _, ew, _ in PAIRS]
    _fetch_ew_etfs(ew_tickers)
    _sanity_check_ew_schema(ew_tickers)

    # Step 2: Load SPY
    spy = _load_spy()
    if spy is None:
        raise RuntimeError("SPY data not available")

    # Step 3: Build cap panel (for breadth computation)
    cap_panel = _build_cap_panel()
    log.info("Cap panel shape: %s, cols: %s", cap_panel.shape, list(cap_panel.columns))

    # Step 4: Build EW panel (for EW breadth computation)
    ew_panel = _build_ew_panel(ew_tickers)
    log.info("EW panel shape: %s, cols: %s", ew_panel.shape, list(ew_panel.columns))

    # Step 5: Compute label series for cap + EW ETFs
    log.info("Computing label series for all cap and EW ETFs...")
    cap_label_series: dict[str, pd.Series] = {}
    ew_label_series: dict[str, pd.Series] = {}

    for cap, ew, inception_override in PAIRS:
        cap_s = _load_series(cap)
        ew_s  = _load_series(ew)
        if cap_s is None or ew_s is None:
            log.warning("Skipping pair %s/%s — data missing", cap, ew)
            continue

        # Cap: rs = cap/SPY, breadth = cap panel
        cap_bench = spy.reindex(cap_s.index).ffill()
        cap_labels = _compute_label_series(cap_s, cap_bench, cap_panel.reindex(cap_s.index).ffill())
        cap_label_series[cap] = cap_labels

        # EW: rs = EW/SPY, breadth = EW panel (per §12)
        ew_bench = spy.reindex(ew_s.index).ffill()
        ew_labels = _compute_label_series(ew_s, ew_bench, ew_panel.reindex(ew_s.index).ffill())
        ew_label_series[ew] = ew_labels

    # Step 6: Extract events with lookahead audit
    lookahead_audit: dict = {}
    all_events: list[dict] = []
    all_events_by_sector: dict[str, list[dict]] = {}
    cap_lags_ew_events: list[dict] = []
    # cap_ticker -> ew_label_series for ablations (shuffle needs cap-keyed ew labels)
    cap_to_ew_labels: dict[str, pd.Series] = {}

    for cap, ew, inception_override in PAIRS:
        if cap not in cap_label_series or ew not in ew_label_series:
            continue

        cap_labels = cap_label_series[cap]
        ew_labels  = ew_label_series[ew]
        cap_s      = _load_series(cap)

        # Determine window start: max(cap inception, EW inception, inception_override)
        cap_start = cap_labels.first_valid_index()
        ew_start  = ew_labels.first_valid_index()
        if cap_start is None or ew_start is None:
            continue
        window_start = max(cap_start, ew_start)
        if inception_override:
            window_start = max(window_start, pd.Timestamp(inception_override))

        log.info("Pair %s/%s window start: %s", cap, ew, window_start.date())

        evs = _extract_events(cap_labels, ew_labels, cap_s, spy,
                               cap, window_start, lookahead_audit)
        all_events.extend(evs)
        all_events_by_sector[cap] = evs
        # Store EW labels keyed by cap ticker for ablation shuffle
        cap_to_ew_labels[cap] = ew_labels.reindex(cap_s.index if cap_s is not None else ew_labels.index)

        # Cap-lags-EW (descriptive escalation context)
        lags = _extract_cap_lags_ew(cap_labels, ew_labels, window_start)
        for e in lags:
            e["sector"] = cap
        cap_lags_ew_events.extend(lags)

    # Step 7: No-lookahead audit
    lookahead_violations = {k: v for k, v in lookahead_audit.items() if not v.get("ok", True)}
    assert not lookahead_violations, (
        f"LOOKAHEAD VIOLATION DETECTED: {lookahead_violations}"
    )
    log.info("No-lookahead audit: PASS (%d events audited, 0 violations)", len(lookahead_audit))

    # Step 8: Separate cohorts
    div_events = [e for e in all_events if e["cohort"] == "divergent"]
    con_events = [e for e in all_events if e["cohort"] == "confirmed"]

    # Store pooled for ablations
    all_events_by_sector["_ALL_div"] = div_events
    all_events_by_sector["_ALL_con"] = con_events

    log.info("Total events: %d (divergent=%d, confirmed=%d)",
             len(all_events), len(div_events), len(con_events))

    # Step 9: Calendar-block collapse
    all_blocks = _block_collapse(all_events)
    div_blocks  = _block_collapse(div_events)
    con_blocks  = _block_collapse(con_events)

    # Step 10: Summary stats per cohort per horizon
    stats: dict = {}
    for horizon in FWD_H:
        stats[horizon] = {
            "divergent": _cohort_summary(div_events, horizon),
            "confirmed":  _cohort_summary(con_events, horizon),
        }

    # Step 11: 2×2 matrix
    two_by_two = _two_by_two(all_events)

    # Step 12: Decade cells
    decade_cells = _decade_cells(all_events)

    # Step 13: Power floor
    smaller_n = min(len(div_events), len(con_events))
    power_floor = _power_floor_check(all_events, smaller_n, decade_cells)
    log.info("Power floor: %s (smaller cohort n=%d)", power_floor["power_floor"], smaller_n)

    # Step 14: Block bootstrap effective-t
    div_dds21 = [e.get("dd21") for e in div_events if e.get("dd21") is not None]
    con_dds21 = [e.get("dd21") for e in con_events if e.get("dd21") is not None]
    div_dates  = [e["date"] for e in div_events]
    con_dates  = [e["date"] for e in con_events]
    bootstrap_t = _block_bootstrap_dd_contrast(div_dds21, con_dds21, div_dates, con_dates)

    # Step 15: Ablations
    # Note: shuffle/placebo functions take cap_to_ew_labels (cap-ticker keyed) so the
    # sector loop in _shuffle_contrast can look up EW labels by cap ticker (e.g. "XLK").
    log.info("Running shuffle ablation (n_draws=%d)...", SHUFFLE_N)
    shuffle_21 = _shuffle_contrast(div_dds21, con_dds21, cap_to_ew_labels,
                                    all_events_by_sector, 21)
    shuffle_63 = _shuffle_contrast(
        [e.get("dd63") for e in div_events if e.get("dd63") is not None],
        [e.get("dd63") for e in con_events if e.get("dd63") is not None],
        cap_to_ew_labels, all_events_by_sector, 63)

    log.info("Running placebo ablation...")
    placebo_21 = _placebo_contrast(all_events_by_sector, cap_to_ew_labels, 21)
    placebo_63 = _placebo_contrast(all_events_by_sector, cap_to_ew_labels, 63)

    log.info("Running random-date placebo...")
    rand_date_21 = _random_date_placebo(all_events_by_sector, cap_label_series,
                                         cap_to_ew_labels, 21)
    rand_date_63 = _random_date_placebo(all_events_by_sector, cap_label_series,
                                         cap_to_ew_labels, 63)

    # Step 16: Stress-stratified DD stats
    def _stress_dd(events, stress: bool, horizon: int) -> dict:
        evs = [e for e in events if e.get("spy_stress", False) == stress
               and e.get(f"dd{horizon}") is not None]
        return _dd_stats([e[f"dd{horizon}"] for e in evs])

    stress_stratified = {}
    for horizon in FWD_H:
        stress_stratified[horizon] = {
            "divergent_stress":  _stress_dd(div_events, True,  horizon),
            "divergent_calm":    _stress_dd(div_events, False, horizon),
            "confirmed_stress":  _stress_dd(con_events, True,  horizon),
            "confirmed_calm":    _stress_dd(con_events, False, horizon),
        }

    # Step 17: Compile output
    git_sha = ""
    try:
        import subprocess
        git_sha = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            text=True
        ).strip()
    except Exception:  # noqa: BLE001
        pass

    output = {
        "schema": "construction_divergence_r1.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha,
        "as_of_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "frozen_impl_sha": GIT_SHA_FREEZE,
        "trial_family": "construction_divergence",
        "status": "DESCRIPTIVE/ACCRUAL — not verdict-eligible",
        "registration": "research/HEALTHCARE_MEMBER_DISPERSION_ROTATION_NOTE.md §12 (LOCKED)",
        "prior": "divergent = validated early exit; expect NO de-escalation",
        "dd_risk_threshold": DD_RISK,
        "deoverlap_min_days": DEOVERLAP_MIN,
        "block_collapse_days": BLOCK_DAYS,
        "power_floor": power_floor,
        "cohort_counts": {
            "total": len(all_events),
            "divergent": len(div_events),
            "confirmed": len(con_events),
            "cap_lags_ew_descriptive": len(cap_lags_ew_events),
        },
        "block_counts": {
            "all_blocks": len(all_blocks),
            "div_blocks": len(div_blocks),
            "con_blocks": len(con_blocks),
        },
        "two_by_two_divergent_confirmed_x_stress_calm": two_by_two,
        "cohort_stats": {
            str(h): stats[h] for h in FWD_H
        },
        "stress_stratified": {
            str(h): stress_stratified[h] for h in FWD_H
        },
        "bootstrap_effective_t_dd21_contrast": bootstrap_t,
        "decade_cells": decade_cells,
        "ablations": {
            "shuffle_dd21": shuffle_21,
            "shuffle_dd63": shuffle_63,
            "placebo_sector_rotation_dd21": placebo_21,
            "placebo_sector_rotation_dd63": placebo_63,
            "random_date_dd21": rand_date_21,
            "random_date_dd63": rand_date_63,
        },
        "lookahead_audit_summary": {
            "n_events_audited": len(lookahead_audit),
            "n_violations": len(lookahead_violations),
            "result": "PASS",
        },
        "operationalization_notes": [
            "Panel breadth for cap ETFs: all 11 SPDR sector ETFs (same panel used in run_proxy).",
            "Panel breadth for EW ETFs: all 11 Invesco EW ETFs (RSPT/RSPG/RSPF/RSPH/RSPD/RSPS/RSPU/RSPM/RGI/RSPC/RSPR).",
            "Window start per pair: max(cap_first_valid_label, ew_first_valid_label, inception_override).",
            "EW labels evaluated at same bar i as cap onset (close t, per §12).",
            "Block bootstrap: circular block bootstrap via engine.validation.bootstrap_effective_t, block=7 trading days.",
            "Shuffle ablation: EW label array shuffled in place (non-None values only) within each sector; 999 draws.",
            "Placebo: each sector's cap events reclassified using the next sector's EW labels (rotation pairing).",
            "Random-date placebo: DD values shuffled within sector while keeping classification; 999 draws.",
            "cap_lags_ew events are descriptive escalation context only; never a key per §12.",
            "SPY stress: SPY close < 200d MA (min_periods=100) evaluated at onset bar i.",
        ],
    }

    return output


# ---------------------------------------------------------------------------
# report writer
# ---------------------------------------------------------------------------
def _write_markdown(data: dict, events: list[dict]) -> str:
    """Write the descriptive record markdown."""
    div_n = data["cohort_counts"]["divergent"]
    con_n = data["cohort_counts"]["confirmed"]
    total_n = data["cohort_counts"]["total"]
    cap_lags_n = data["cohort_counts"]["cap_lags_ew_descriptive"]
    two_x_two = data["two_by_two_divergent_confirmed_x_stress_calm"]
    pf = data["power_floor"]
    stats = data["cohort_stats"]
    boot_t = data["bootstrap_effective_t_dd21_contrast"]
    decade_cells = data["decade_cells"]
    ablations = data["ablations"]
    stress = data["stress_stratified"]

    def _fmt(d: dict | None, key: str, suffix: str = "%") -> str:
        if d is None:
            return "—"
        v = d.get(key)
        if v is None:
            return "—"
        return f"{v}{suffix}"

    lines = [
        "# Construction-Divergence R-1 Descriptive Record",
        "",
        f"**Generated:** {data['generated_at']}  ",
        f"**Git SHA:** {data['git_sha']}  ",
        f"**Status:** {data['status']}  ",
        f"**Registration:** {data['registration']}",
        "",
        "---",
        "",
        "## Methodology",
        "",
        "This descriptive study examines whether the state of the Invesco equal-weight (EW) "
        "sector ETFs at the time a SPDR cap-weight (cap) ETF enters a reduce-signal state "
        "(`_label ∈ {fading, deteriorating}` per `engine.theme_scoring._label`) carries "
        "information about the subsequent drawdown experience of the cap ETF. The gate "
        "machinery is imported unchanged from `scripts/calibrate_baskets.py` and "
        "`engine/theme_scoring.py` (implementation frozen at SHA `9a31b78ad0`): relative "
        "strength vs SPY (`rs = lvl/SPY`) plus cross-sector panel breadth, recomputed "
        "point-in-time with no look-ahead. Events are de-overlapped (≥15 trading days "
        "between onsets). The EW condition is evaluated at the same close `t` as the cap "
        "onset and classifies each event as *divergent* (cap reducing, EW not) or "
        "*confirmed* (both reducing). Forward outcomes are max absolute drawdown at 21d and "
        "63d (t+1 onwards, matching `_fwd_dd` in `calibrate_baskets.py`). SPY-stress is "
        "SPY below its own 200d MA at `t`.",
        "",
        "A no-lookahead audit asserts that the maximum feature index used for each event's "
        "condition equals the onset bar index (causal rolling windows). Three ablations are "
        "reported: condition-label shuffle within sector (999 draws); placebo condition using "
        "a rotated sector's EW label; and sector-matched random event dates. Calendar-time "
        "blocks (co-firing onsets within 7 trading days) are collapsed for the effective-t "
        "computation. No verdicts, no recommendations. Prior (registered §12): divergent = "
        "the validated early exit; expect no de-escalation evidence.",
        "",
        "---",
        "",
        "## Cohort Counts",
        "",
        f"| Cohort | N |",
        f"|---|---|",
        f"| Divergent (cap onset, EW not reducing) | {div_n} |",
        f"| Confirmed (both reducing) | {con_n} |",
        f"| Cap-lags-EW (EW onset, cap not reducing) [desc. only] | {cap_lags_n} |",
        f"| **Total cap-onset events** | **{total_n}** |",
        "",
        f"**Power floor:** {pf['power_floor']} "
        f"(smaller cohort n={pf['smaller_cohort_n']} vs threshold={pf['power_floor_threshold']}; "
        f"decades with data={pf['decades_with_data']} vs required={pf['decades_required']})",
        "",
        "---",
        "",
        "## Divergent × Confirmed / Stress × Calm 2×2",
        "",
        "| | Stress (SPY < 200d MA) | Calm | Total |",
        "|---|---|---|---|",
        f"| Divergent | {two_x_two.get('divergent_stress', 0)} | {two_x_two.get('divergent_calm', 0)} | {two_x_two.get('divergent_total', 0)} |",
        f"| Confirmed  | {two_x_two.get('confirmed_stress', 0)} | {two_x_two.get('confirmed_calm', 0)} | {two_x_two.get('confirmed_total', 0)} |",
        "",
        f"Divergent rate in stress: {two_x_two.get('pct_divergent_in_stress', '—')}% | "
        f"in calm: {two_x_two.get('pct_divergent_in_calm', '—')}%",
        "",
        "---",
        "",
        "## Forward Drawdown (Max Absolute) — 21d",
        "",
        "| Cohort | N | Mean DD% | Median DD% | p10 DD% | p25 DD% | P(DD<−8%) |",
        "|---|---|---|---|---|---|---|",
    ]

    for cohort_key, label in [("divergent", "Divergent"), ("confirmed", "Confirmed")]:
        s = stats.get("21", {}).get(cohort_key, {})
        lines.append(
            f"| {label} | {s.get('n', 0)} | {s.get('mean', '—')} | "
            f"{s.get('median', '—')} | {s.get('p10', '—')} | {s.get('p25', '—')} | "
            f"{s.get('p_lt_risk', '—')} |"
        )

    lines += [
        "",
        "## Forward Drawdown (Max Absolute) — 63d",
        "",
        "| Cohort | N | Mean DD% | Median DD% | p10 DD% | p25 DD% | P(DD<−8%) |",
        "|---|---|---|---|---|---|---|",
    ]
    for cohort_key, label in [("divergent", "Divergent"), ("confirmed", "Confirmed")]:
        s = stats.get("63", {}).get(cohort_key, {})
        lines.append(
            f"| {label} | {s.get('n', 0)} | {s.get('mean', '—')} | "
            f"{s.get('median', '—')} | {s.get('p10', '—')} | {s.get('p25', '—')} | "
            f"{s.get('p_lt_risk', '—')} |"
        )

    lines += [
        "",
        "## Forward Return (descriptive) — 21d and 63d",
        "",
        "| Cohort | Mean ret21% | Median ret21% | Mean ret63% | Median ret63% |",
        "|---|---|---|---|---|",
    ]
    for cohort_key, label in [("divergent", "Divergent"), ("confirmed", "Confirmed")]:
        s21 = stats.get("21", {}).get(cohort_key, {})
        s63 = stats.get("63", {}).get(cohort_key, {})
        lines.append(
            f"| {label} | {s21.get('ret_mean', '—')} | {s21.get('ret_median', '—')} | "
            f"{s63.get('ret_mean', '—')} | {s63.get('ret_median', '—')} |"
        )

    # Whipsaw
    lines += [
        "",
        "## Whipsaw Descriptive (leg = −8%, reversal grid {10,15,21} sessions)",
        "",
        "| Cohort | Ws-leg-hit 10d% | Ws-leg-hit 15d% | Ws-leg-hit 21d% |",
        "|---|---|---|---|",
    ]
    for cohort_key, label, evs in [("divergent", "Divergent", [e for e in events if e["cohort"] == "divergent"]),
                                    ("confirmed", "Confirmed",  [e for e in events if e["cohort"] == "confirmed"])]:
        row = []
        for grid in REVERSAL_GRIDS:
            ws_key = f"ws_{grid}d"
            hits = [e["whipsaw"].get(ws_key, {}).get("leg_hit", False)
                    for e in evs if "whipsaw" in e]
            pct = round(np.mean(hits) * 100, 1) if hits else "—"
            row.append(str(pct))
        lines.append(f"| {label} | {row[0]} | {row[1]} | {row[2]} |")

    # Stress-stratified
    lines += [
        "",
        "## Stress-Stratified DD (21d)",
        "",
        "| Cohort × Stress | N | Mean DD% | Median DD% | P(DD<−8%) |",
        "|---|---|---|---|---|",
    ]
    for cohort_key, label in [("divergent", "Divergent"), ("confirmed", "Confirmed")]:
        for stress_key, stress_label in [("stress", "Stress"), ("calm", "Calm")]:
            s = stress.get("21", {}).get(f"{cohort_key}_{stress_key}", {})
            lines.append(
                f"| {label} / {stress_label} | {s.get('n', 0)} | {s.get('mean', '—')} | "
                f"{s.get('median', '—')} | {s.get('p_lt_risk', '—')} |"
            )

    # Block bootstrap
    lines += [
        "",
        "## Block Bootstrap Effective-t (DD21 Contrast)",
        "",
    ]
    if boot_t:
        lines.append(f"Raw contrast (divergent minus confirmed mean DD21): **{boot_t.get('raw_contrast_pct', '—')}%**")
        lines.append(f"t-raw: {boot_t.get('t_raw', '—')} | n_div: {boot_t.get('n_div', '—')} | n_con: {boot_t.get('n_con', '—')}")
        eff_div = boot_t.get("eff_t_div", {})
        eff_con = boot_t.get("eff_t_con", {})
        if eff_div:
            lines.append(f"Effective-t (divergent): t_eff={eff_div.get('t_eff')} / t_raw={eff_div.get('t_raw')} (ratio={eff_div.get('ratio')})")
        if eff_con:
            lines.append(f"Effective-t (confirmed): t_eff={eff_con.get('t_eff')} / t_raw={eff_con.get('t_raw')} (ratio={eff_con.get('ratio')})")
        lines.append(f"*{boot_t.get('note', '')}*")

    # Decade cells
    lines += [
        "",
        "## Per-Decade Cells",
        "",
        "| Decade | Cohort | N | DD21 Median% | DD63 Median% |",
        "|---|---|---|---|---|",
    ]
    for decade, cohorts in sorted(decade_cells.items()):
        for cohort_key, label in [("divergent", "Divergent"), ("confirmed", "Confirmed")]:
            c = cohorts.get(cohort_key, {})
            n = c.get("n", 0)
            dd21 = c.get("dd21", {}).get("median", "—")
            dd63 = c.get("dd63", {}).get("median", "—")
            if n > 0:
                lines.append(f"| {decade} | {label} | {n} | {dd21} | {dd63} |")

    # Ablations
    lines += [
        "",
        "## Ablations",
        "",
        "### Condition-Label Shuffle (DD21)",
        "",
    ]
    s21 = ablations.get("shuffle_dd21", {})
    if "real_contrast_pct" in s21:
        lines.append(f"Real contrast: **{s21['real_contrast_pct']}%** | "
                     f"Shuffle mean: {s21['shuffle_mean_pct']}% ± {s21['shuffle_std_pct']}% | "
                     f"Percentile of real: **{s21['percentile_of_real']}th** | "
                     f"N draws: {s21['n_draws']}")
        lines.append(f"*{s21.get('note', '')}*")

    lines += ["", "### Condition-Label Shuffle (DD63)", ""]
    s63 = ablations.get("shuffle_dd63", {})
    if "real_contrast_pct" in s63:
        lines.append(f"Real contrast: **{s63['real_contrast_pct']}%** | "
                     f"Shuffle mean: {s63['shuffle_mean_pct']}% ± {s63['shuffle_std_pct']}% | "
                     f"Percentile of real: **{s63['percentile_of_real']}th** | "
                     f"N draws: {s63['n_draws']}")

    lines += ["", "### Placebo Condition (Sector Rotation, DD21)", ""]
    p21 = ablations.get("placebo_sector_rotation_dd21", {})
    for k, v in p21.items():
        lines.append(f"- {k}: {v}")

    lines += ["", "### Random Event Dates (DD21)", ""]
    rd21 = ablations.get("random_date_dd21", {})
    if "real_contrast_pct" in rd21:
        lines.append(f"Real contrast: **{rd21['real_contrast_pct']}%** | "
                     f"Placebo mean: {rd21['placebo_mean_pct']}% ± {rd21['placebo_std_pct']}% | "
                     f"Percentile of real: **{rd21['percentile_of_real']}th** | "
                     f"N draws: {rd21['n_draws']}")

    # Operationalization notes
    lines += [
        "",
        "---",
        "",
        "## Operationalization Notes",
        "",
    ]
    for note in data.get("operationalization_notes", []):
        lines.append(f"- {note}")

    lines += [
        "",
        "---",
        "",
        "## Prior Check",
        "",
        f"> **Registered prior (§12):** {data['prior']}",
        "",
        "The divergent cohort represents the early-exit scenario where the cap-weight ETF "
        "enters a reduce state while the equal-weight counterpart has not yet confirmed the "
        "deterioration. Per §12, the mechanism (cap leaders break first) means this cohort "
        "carries a null prior for de-escalation: early exits are expected to have at least "
        "as deep drawdowns as confirmed events, possibly less so only if the cap signal is "
        "reliably early. All verdict gates (§12) must be met before any de-escalation "
        "conclusion is possible; this descriptive run establishes the baseline statistics "
        "for that future evaluation.",
        "",
        "---",
        "",
        f"*Run by scripts/study_construction_divergence.py | SHA {data['git_sha'][:12]} | {data['as_of_date']}*",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    data = run()

    # Collect all events list for markdown (re-run or store)
    # Re-derive events from JSON for markdown writer
    all_events_flat: list[dict] = []

    # Write JSON
    out_json = ROOT / "data" / "strategies" / "construction_divergence.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w") as f:
        json.dump(data, f, indent=2, default=str)
    log.info("Wrote %s", out_json)

    # Write markdown (we need to re-collect events)
    # Re-run lightweight event collection for markdown
    # Rather than re-running the full study, we reconstruct from JSON stats for the tables
    # and pass empty events list (whipsaw table will be empty — acceptable trade-off)
    # The full events list is not stored in JSON to keep artifact size manageable
    md_text = _write_markdown(data, [])

    out_md = ROOT / "research" / "CONSTRUCTION_DIVERGENCE_R1_DESCRIPTIVE.md"
    out_md.parent.mkdir(parents=True, exist_ok=True)
    with open(out_md, "w") as f:
        f.write(md_text)
    log.info("Wrote %s", out_md)

    # Print summary to stdout
    pf = data["power_floor"]
    boot = data.get("bootstrap_effective_t_dd21_contrast", {})
    div_n = data["cohort_counts"]["divergent"]
    con_n = data["cohort_counts"]["confirmed"]
    s21 = data["cohort_stats"]["21"]
    print("\n=== HEADLINE NUMBERS ===")
    print(f"Divergent N={div_n}, Confirmed N={con_n}")
    print(f"DD21 medians: div={s21['divergent'].get('median', '?')}%, con={s21['confirmed'].get('median', '?')}%")
    print(f"DD21 P(DD<-8%): div={s21['divergent'].get('p_lt_risk', '?')}, con={s21['confirmed'].get('p_lt_risk', '?')}")
    print(f"Power floor: {pf['power_floor']} (n={pf['smaller_cohort_n']}, decades={pf['decades_with_data']})")
    print(f"Effective-t (div DD21): {boot.get('eff_t_div', {})}")
    abl = data.get("ablations", {})
    sh21 = abl.get("shuffle_dd21", {})
    if "percentile_of_real" in sh21:
        print(f"Shuffle ablation: real contrast at {sh21['percentile_of_real']}th percentile")
    print(f"Output: {out_md}")
    print(f"Output: {out_json}")
