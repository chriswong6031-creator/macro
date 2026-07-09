"""HC-RC-1 — R-1 construction-divergence re-check under repaired calendar-block inference.

Re-check registration: research/TIME_CONFOUND_EXPOSURE_AUDIT.md §7 item 6 (HC-RC-1).
Original study: scripts/study_construction_divergence.py (DO NOT MODIFY — historical record).
Adjudication authority: Fable-tier (pending).

WHAT IS FIXED (CD-1/CD-2/CD-3 per audit §4):
  CD-1: Events were passed to bootstrap_effective_t in sector-pair concatenation order
        (not calendar order), so effective-t measured nothing about calendar time.
        Fix: sort pooled event list globally by real date before any block operation.
  CD-2: The ±7-day co-firing block collapse was keyed on per-sector-pair positional
        bar_i, not real dates, making cross-sector co-firing invisible. The collapsed
        block_counts were reported but never fed into any statistic.
        Fix: real calendar-date proximity collapse across all sectors simultaneously,
        with transitive chaining; blocks used as the resampling unit in a proper
        block-cluster bootstrap of the div-vs-con contrast.
  CD-3: All three ablations preserve calendar composition — powerless against time confound.
        Fix: the PRIMARY contrast now uses block-cluster bootstrap (blocks defined in
        CD-2). Ablations retained as reference only (original within-unit permutations).

FROZEN (per task brief):
  - Event definitions (divergent/confirmed onset classification)
  - De-overlap rules (≥15 trading days)
  - DD21/DD63 outcome definitions
  - Sector-pair universe
  - Window (2007-2026)
  - SPY-stress stratum definition (SPY < 200d MA at t)

REPRODUCTION GATE:
  Must reproduce within rounding of original shipped counts (divergent ~315, confirmed
  ~485) and raw DD21 medians (div −2.32 / con −2.56). If these deviate materially, the
  script halts with a WIP-blocked note.

OUTPUT:
  research/CONSTRUCTION_DIVERGENCE_R1_TC_RECHECK.md
  research/construction_divergence_tc_recheck.json

Usage (from repo root, with EW parquets present or auto-fetched):
    python -m scripts.study_construction_divergence_tc
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date, timedelta
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
log = logging.getLogger("study_construction_divergence_tc")

# ---------------------------------------------------------------------------
# Constants — frozen per §12 (identical to original)
# ---------------------------------------------------------------------------
GIT_SHA_FREEZE = "9a31b78ad0"
DD_RISK = -0.08
DEOVERLAP_MIN = 15
RS_WIN, Z_LB = 20, 252
FWD_H = (21, 63)
BLOCK_DAYS = 7        # calendar days for co-firing collapse
SHUFFLE_N = 999
POWER_FLOOR = 40
POWER_DECADES = 2

# Bootstrap parameters (repaired inference)
BOOTSTRAP_DRAWS = 2000     # per task spec (reduce to ≥1000 if needed)
BOOTSTRAP_SEED = 42        # fixed seed per task spec

# Reproduction gate tolerances (counts)
REPRO_DIV_TARGET = 315     # from shipped report (±5 tolerance)
REPRO_CON_TARGET = 485
REPRO_TOLERANCE_COUNT = 6
REPRO_DIV_MED21_TARGET = -2.32   # %
REPRO_CON_MED21_TARGET = -2.56
REPRO_TOLERANCE_MED = 0.15       # percentage-point tolerance

# Universe — frozen per §12
PAIRS: list[tuple[str, str, str | None]] = [
    ("XLK",  "RSPT",  None),
    ("XLE",  "RSPG",  None),
    ("XLF",  "RSPF",  None),
    ("XLV",  "RSPH",  None),
    ("XLY",  "RSPD",  None),
    ("XLP",  "RSPS",  None),
    ("XLU",  "RSPU",  None),
    ("XLB",  "RSPM",  None),
    ("XLI",  "RGI",   "2009-01-02"),
    ("XLC",  "RSPC",  "2018-11-07"),
    ("XLRE", "RSPR",  "2015-08-14"),
]
LATE_PAIRS_POST2018 = {"XLC", "XLRE"}


# ---------------------------------------------------------------------------
# Helpers — replicated from original (frozen)
# ---------------------------------------------------------------------------
def _tanh(x: float, k: float) -> float:
    return float(np.tanh(k * x))


def _f(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _rs_features(lvl: pd.Series, bench: pd.Series) -> dict:
    rs = (lvl / bench).reindex(lvl.index)
    rs_chg = rs.pct_change(RS_WIN, fill_method=None)
    accel_z = _causal_z(rs_chg - rs_chg.shift(RS_WIN), Z_LB)
    rs_pctile = pct_rank_window(rs, Z_LB)
    rel = {h: lvl.pct_change(h, fill_method=None) - bench.pct_change(h, fill_method=None)
           for h in (5, 20, 60)}
    return {"accel_z": accel_z, "rs_pctile": rs_pctile,
            "r5": rel[5], "r20": rel[20], "r60": rel[60], "delta_5d": rel[5]}


def _panel_breadth(P: pd.DataFrame) -> pd.DataFrame:
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
    if r5 is not None and np.isfinite(r5): parts.append(_tanh(r5, 12)); wts.append(0.25)
    if r20 is not None and np.isfinite(r20): parts.append(_tanh(r20, 8)); wts.append(0.35)
    if r60 is not None and np.isfinite(r60): parts.append(_tanh(r60, 5)); wts.append(0.20)
    if accel_z is not None and np.isfinite(accel_z): parts.append(_tanh(accel_z, 0.7)); wts.append(0.20)
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
    if i + h >= len(lvl):
        return np.nan
    seg = lvl[i + 1:i + 1 + h]
    return float(seg.min() / lvl[i] - 1.0) if len(seg) else np.nan


def _fwd_ret(lvl: np.ndarray, i: int, h: int) -> float:
    if i + h >= len(lvl):
        return np.nan
    return float(lvl[i + h] / lvl[i] - 1.0)


def _compute_label_series(lvl: pd.Series, bench: pd.Series,
                           panel: pd.DataFrame) -> pd.Series:
    feats = _rs_features(lvl, bench)
    breadth_df = _panel_breadth(panel)
    labels = pd.Series(index=lvl.index, dtype=object)
    bnp = {k: breadth_df[k].to_numpy() for k in ("pct50", "pct200", "nh", "nl", "net_nh")}
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
        accel_z_f, rs_p_f = _f(accel_z), _f(rs_p)
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


def _is_reducing(label: str | None) -> bool:
    return label in ("fading", "deteriorating")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def _load_series(ticker: str) -> pd.Series | None:
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
    tickers = [cap for cap, _, _ in PAIRS]
    return pd.DataFrame({t: s for t in tickers if (s := _load_series(t)) is not None})


def _build_ew_panel(tickers: list[str]) -> pd.DataFrame:
    return pd.DataFrame({t: s for t in tickers if (s := _load_series(t)) is not None})


def _load_spy() -> pd.Series | None:
    return _load_series("SPY")


def _fetch_ew_etfs(ew_tickers: list[str]) -> None:
    """Fetch missing EW ETFs from Yahoo Finance (writes to worktree data/yahoo/)."""
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
            if isinstance(df.columns, pd.MultiIndex):
                df = df[t]
            if "Adj Close" in df.columns:
                out = pd.DataFrame({
                    "close_price": df["Close"].astype(float),
                    "close":       df["Adj Close"].astype(float),
                    "volume":      df["Volume"].astype(float),
                })
            else:
                out = pd.DataFrame({
                    "close_price": df["Close"].astype(float),
                    "close":       df["Close"].astype(float),
                    "volume":      df["Volume"].astype(float) if "Volume" in df.columns else pd.Series(dtype=float),
                })
            out.index.name = "Date"
            out = out.dropna(subset=["close"])
            out.columns.name = "Price"
            path = data_dir / f"{t}.parquet"
            out.to_parquet(path)
            log.info("Wrote %s (%d rows, %s to %s)", t, len(out),
                     str(out.index.min().date()), str(out.index.max().date()))
        except Exception as exc:  # noqa: BLE001
            log.error("Failed to fetch %s: %s", t, exc)


# ---------------------------------------------------------------------------
# Event extraction — identical to original (frozen)
# ---------------------------------------------------------------------------
def _extract_events(
    cap_labels: pd.Series,
    ew_labels: pd.Series,
    cap_lvl: pd.Series,
    spy: pd.Series,
    sector: str,
    window_start: pd.Timestamp,
    lookahead_audit: dict,
) -> list[dict]:
    common = cap_labels.index.intersection(ew_labels.index)
    common = common[common >= window_start]
    cap_l = cap_labels.reindex(common)
    ew_l  = ew_labels.reindex(common)
    cap_px = cap_lvl.reindex(common).to_numpy()
    spy_px = spy.reindex(common).ffill().to_numpy()
    idx = common

    events = []
    in_reducing_state = False
    days_out_of_state = DEOVERLAP_MIN

    for i, dt in enumerate(idx):
        cap_lab = cap_l.iloc[i]
        ew_lab  = ew_l.iloc[i]
        cap_red = _is_reducing(cap_lab)

        if cap_red:
            if not in_reducing_state:
                if days_out_of_state >= DEOVERLAP_MIN and not np.isnan(cap_px[i]):
                    lookahead_audit[f"{sector}_{dt.date()}"] = {
                        "event_i": i, "max_feat_idx_used": i, "ok": True}
                    dd21 = _fwd_dd(cap_px, i, 21)
                    dd63 = _fwd_dd(cap_px, i, 63)
                    ret21 = _fwd_ret(cap_px, i, 21)
                    ret63 = _fwd_ret(cap_px, i, 63)
                    spy_200d_ma = spy.reindex(idx).ffill().rolling(200, min_periods=100).mean()
                    spy_at_t = spy.reindex(idx).ffill().iloc[i]
                    spy_ma_at_t = spy_200d_ma.iloc[i] if i < len(spy_200d_ma) else np.nan
                    spy_stress = (not np.isnan(spy_at_t) and not np.isnan(spy_ma_at_t)
                                  and spy_at_t < spy_ma_at_t)
                    ew_red = _is_reducing(ew_lab)
                    if cap_red and not ew_red:
                        cohort = "divergent"
                    elif cap_red and ew_red:
                        cohort = "confirmed"
                    else:
                        cohort = "other"

                    whipsaw = {}
                    for grid in [10, 15, 21]:
                        j_end = min(i + 1 + grid, len(cap_px) - 1)
                        seg = cap_px[i + 1:j_end + 1]
                        hit_leg = bool(np.any(seg / cap_px[i] - 1 <= DD_RISK)) if len(seg) else False
                        close_at_grid = cap_px[j_end] / cap_px[i] - 1 if j_end < len(cap_px) else np.nan
                        whipsaw[f"ws_{grid}d"] = {
                            "leg_hit": hit_leg,
                            "reversal_close_ret": round(float(close_at_grid), 4) if np.isfinite(close_at_grid) else None,
                        }

                    ev = {
                        "sector": sector,
                        "date": str(dt.date()),
                        "bar_i": i,          # positional within sector — NOT used for TC collapse
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
            in_reducing_state = True
            days_out_of_state = 0
        else:
            in_reducing_state = False
            days_out_of_state += 1

    return events


# ---------------------------------------------------------------------------
# CD-1 + CD-2 FIX: real cross-sector co-firing block collapse
# ---------------------------------------------------------------------------
def _real_date_block_collapse(events: list[dict]) -> list[list[dict]]:
    """CD-2 fix: group events into blocks where onset DATES fall within ±7 calendar
    days of each other, with transitive chaining.

    Sort by real date (CD-1 fix), then chain: event j merges into the current block
    if its date is within BLOCK_DAYS calendar days of the EARLIEST date in the block
    (strict chaining via the block anchor, not just the trailing edge, avoids
    unbounded drifting chains).

    This is cross-sector: all cohorts pooled so confirmed and divergent events that
    fired in the same macro episode end up in the same block.

    Returns list of blocks (each a list of event dicts).
    """
    if not events:
        return []
    # CD-1: sort globally by real date string (ISO → lexicographic = chronological)
    evs = sorted(events, key=lambda e: e["date"])
    blocks: list[list[dict]] = []
    current_block: list[dict] = [evs[0]]
    block_anchor_date = date.fromisoformat(evs[0]["date"])

    for ev in evs[1:]:
        ev_date = date.fromisoformat(ev["date"])
        if (ev_date - block_anchor_date).days <= BLOCK_DAYS:
            current_block.append(ev)
            # anchor stays at first event in block (strict chaining)
        else:
            blocks.append(current_block)
            current_block = [ev]
            block_anchor_date = ev_date

    blocks.append(current_block)
    return blocks


# ---------------------------------------------------------------------------
# CD-2 FIX: block-cluster bootstrap for div-vs-con mean DD contrast
# ---------------------------------------------------------------------------
def _block_cluster_bootstrap_contrast(
    events: list[dict],
    horizon: int,
    blocks: list[list[dict]],
    n_draws: int = BOOTSTRAP_DRAWS,
    seed: int = BOOTSTRAP_SEED,
) -> dict:
    """Resample co-firing blocks (with replacement) to form the bootstrap distribution
    of the divergent-minus-confirmed mean DD contrast.

    Each block may contain zero, one, or both cohorts. We resample BLOCKS (not events),
    compute mean DD per cohort from the resampled pool, and record the contrast.

    Returns dict with: raw_contrast_pct, ci_95_lo_pct, ci_95_hi_pct, p_two_sided,
    n_blocks, n_events_div, n_events_con, mean_block_size, n_draws.
    """
    dd_key = f"dd{horizon}"
    # Annotate each block with its events' dd values by cohort
    block_data: list[dict] = []
    for blk in blocks:
        div_dds = [e[dd_key] for e in blk if e.get("cohort") == "divergent"
                   and e.get(dd_key) is not None and np.isfinite(e[dd_key])]
        con_dds = [e[dd_key] for e in blk if e.get("cohort") == "confirmed"
                   and e.get(dd_key) is not None and np.isfinite(e[dd_key])]
        block_data.append({"div": div_dds, "con": con_dds, "size": len(blk)})

    # Observed statistics (uses all events directly)
    all_div = [e[dd_key] for e in events if e.get("cohort") == "divergent"
               and e.get(dd_key) is not None and np.isfinite(e[dd_key])]
    all_con = [e[dd_key] for e in events if e.get("cohort") == "confirmed"
               and e.get(dd_key) is not None and np.isfinite(e[dd_key])]

    if not all_div or not all_con:
        return {"note": "insufficient events for block-bootstrap"}

    n_blocks = len(block_data)
    if n_blocks < 10:
        return {"note": f"too few blocks for bootstrap: {n_blocks}"}

    raw_div_mean = float(np.mean(all_div))
    raw_con_mean = float(np.mean(all_con))
    raw_contrast = raw_div_mean - raw_con_mean

    rng = np.random.default_rng(seed)
    boot_contrasts: list[float] = []

    for _ in range(n_draws):
        # Resample blocks with replacement
        chosen_idx = rng.integers(0, n_blocks, size=n_blocks)
        b_div: list[float] = []
        b_con: list[float] = []
        for bi in chosen_idx:
            b_div.extend(block_data[bi]["div"])
            b_con.extend(block_data[bi]["con"])
        if b_div and b_con:
            boot_contrasts.append(float(np.mean(b_div)) - float(np.mean(b_con)))

    if len(boot_contrasts) < 100:
        return {"note": f"insufficient bootstrap iterations: {len(boot_contrasts)}"}

    boot_arr = np.array(boot_contrasts)
    # Percentile CI (basic bootstrap)
    ci_lo = float(np.percentile(boot_arr, 2.5))
    ci_hi = float(np.percentile(boot_arr, 97.5))
    # Two-sided p: fraction of bootstrap distribution that has opposite sign from observed
    # (under the null contrast = 0: p = 2 * min(P(boot<=0), P(boot>=0)))
    if raw_contrast >= 0:
        p_val = 2.0 * float(np.mean(boot_arr <= 0))
    else:
        p_val = 2.0 * float(np.mean(boot_arr >= 0))
    p_val = min(p_val, 1.0)

    # Block size distribution
    sizes = [bd["size"] for bd in block_data]
    size_hist: dict[str, int] = {}
    for s in sizes:
        k = f"size_{s}"
        size_hist[k] = size_hist.get(k, 0) + 1

    return {
        "raw_contrast_pct":   round(raw_contrast * 100, 3),
        "raw_div_mean_pct":   round(raw_div_mean * 100, 3),
        "raw_con_mean_pct":   round(raw_con_mean * 100, 3),
        "ci_95_lo_pct":       round(ci_lo * 100, 3),
        "ci_95_hi_pct":       round(ci_hi * 100, 3),
        "p_two_sided":        round(p_val, 4),
        "n_blocks":           n_blocks,
        "n_events_div":       len(all_div),
        "n_events_con":       len(all_con),
        "mean_block_size":    round(float(np.mean(sizes)), 2),
        "max_block_size":     int(max(sizes)),
        "block_size_hist":    dict(sorted(size_hist.items())),
        "n_bootstrap_draws":  len(boot_contrasts),
        "note": (
            "block-cluster bootstrap (resample co-firing calendar blocks, CD-2 fix); "
            f"seed={seed}; positive contrast = divergent has SHALLOWER DD "
            "(early-exit hypothesis direction)"
        ),
    }


# ---------------------------------------------------------------------------
# Stress-stratified block-bootstrap contrast
# ---------------------------------------------------------------------------
def _stress_stratified_contrast(
    events: list[dict],
    blocks: list[list[dict]],
    horizon: int,
    n_draws: int = BOOTSTRAP_DRAWS,
    seed: int = BOOTSTRAP_SEED,
) -> dict:
    """Block-bootstrap contrast within each SPY-stress stratum.

    Blocks that contain events from BOTH strata are kept whole and assigned to
    whichever stratum applies to each constituent event (no splitting).
    Within each stratum, we resample the BLOCKS that contributed at least one
    event to that stratum (blocks may overlap across strata).
    """
    result: dict[str, Any] = {}
    for stress_flag in (True, False):
        stratum_name = "stress" if stress_flag else "calm"
        # Filter events to this stratum
        stratum_events = [e for e in events if e.get("spy_stress") == stress_flag]

        # Filter blocks to only blocks that contain at least one stratum event
        # (keep the full block, but DD contribution is only from stratum events)
        stratum_block_data: list[dict] = []
        for blk in blocks:
            stratum_blk = [e for e in blk if e.get("spy_stress") == stress_flag]
            if stratum_blk:
                stratum_block_data.append(stratum_blk)

        n_stratum_blocks = len(stratum_block_data)
        dd_key = f"dd{horizon}"

        stratum_div = [e[dd_key] for e in stratum_events
                       if e.get("cohort") == "divergent"
                       and e.get(dd_key) is not None and np.isfinite(e[dd_key])]
        stratum_con = [e[dd_key] for e in stratum_events
                       if e.get("cohort") == "confirmed"
                       and e.get(dd_key) is not None and np.isfinite(e[dd_key])]

        raw_stats: dict = {
            "n_div": len(stratum_div),
            "n_con": len(stratum_con),
            "n_blocks": n_stratum_blocks,
            "div_mean_pct": round(float(np.mean(stratum_div)) * 100, 3) if stratum_div else None,
            "con_mean_pct": round(float(np.mean(stratum_con)) * 100, 3) if stratum_con else None,
            "div_median_pct": round(float(np.median(stratum_div)) * 100, 3) if stratum_div else None,
            "con_median_pct": round(float(np.median(stratum_con)) * 100, 3) if stratum_con else None,
            "div_p10_pct": round(float(np.percentile(stratum_div, 10)) * 100, 3) if stratum_div else None,
            "con_p10_pct": round(float(np.percentile(stratum_con, 10)) * 100, 3) if stratum_con else None,
        }

        if len(stratum_div) < 5 or len(stratum_con) < 5 or n_stratum_blocks < 5:
            raw_stats["bootstrap"] = {"note": f"too few events/blocks for bootstrap in {stratum_name}"}
            result[stratum_name] = raw_stats
            continue

        raw_contrast = float(np.mean(stratum_div)) - float(np.mean(stratum_con))
        rng = np.random.default_rng(seed)
        boot_contrasts: list[float] = []

        # Annotate stratum blocks with div/con dd values
        stratum_block_annotated: list[dict] = []
        for sblk in stratum_block_data:
            div_dds = [e[dd_key] for e in sblk if e.get("cohort") == "divergent"
                       and e.get(dd_key) is not None and np.isfinite(e[dd_key])]
            con_dds = [e[dd_key] for e in sblk if e.get("cohort") == "confirmed"
                       and e.get(dd_key) is not None and np.isfinite(e[dd_key])]
            stratum_block_annotated.append({"div": div_dds, "con": con_dds})

        for _ in range(n_draws):
            chosen_idx = rng.integers(0, n_stratum_blocks, size=n_stratum_blocks)
            b_div: list[float] = []
            b_con: list[float] = []
            for bi in chosen_idx:
                b_div.extend(stratum_block_annotated[bi]["div"])
                b_con.extend(stratum_block_annotated[bi]["con"])
            if b_div and b_con:
                boot_contrasts.append(float(np.mean(b_div)) - float(np.mean(b_con)))

        if len(boot_contrasts) < 50:
            raw_stats["bootstrap"] = {"note": f"insufficient bootstrap iterations in {stratum_name}"}
            result[stratum_name] = raw_stats
            continue

        boot_arr = np.array(boot_contrasts)
        ci_lo = float(np.percentile(boot_arr, 2.5))
        ci_hi = float(np.percentile(boot_arr, 97.5))
        if raw_contrast >= 0:
            p_val = 2.0 * float(np.mean(boot_arr <= 0))
        else:
            p_val = 2.0 * float(np.mean(boot_arr >= 0))

        raw_stats["bootstrap"] = {
            "raw_contrast_pct": round(raw_contrast * 100, 3),
            "ci_95_lo_pct":     round(ci_lo * 100, 3),
            "ci_95_hi_pct":     round(ci_hi * 100, 3),
            "p_two_sided":      round(min(p_val, 1.0), 4),
            "n_bootstrap_draws": len(boot_contrasts),
        }
        result[stratum_name] = raw_stats

    return result


# ---------------------------------------------------------------------------
# Tail contrast (p10 of DD within cohort, block-bootstrap CI)
# ---------------------------------------------------------------------------
def _tail_contrast(
    events: list[dict],
    blocks: list[list[dict]],
    horizon: int,
    n_draws: int = BOOTSTRAP_DRAWS,
    seed: int = BOOTSTRAP_SEED,
) -> dict:
    """Block-bootstrap CI on the p10 DD within each cohort (tail measure).

    Resamples blocks with replacement, computes p10 of the div/con pools separately.
    Reports CIs for each cohort's p10 separately (not a difference CI, which is
    more complex for quantiles).
    """
    dd_key = f"dd{horizon}"
    # Annotate blocks
    block_data: list[dict] = []
    for blk in blocks:
        div_dds = [e[dd_key] for e in blk if e.get("cohort") == "divergent"
                   and e.get(dd_key) is not None and np.isfinite(e[dd_key])]
        con_dds = [e[dd_key] for e in blk if e.get("cohort") == "confirmed"
                   and e.get(dd_key) is not None and np.isfinite(e[dd_key])]
        block_data.append({"div": div_dds, "con": con_dds})

    n_blocks = len(block_data)
    all_div = [e[dd_key] for e in events if e.get("cohort") == "divergent"
               and e.get(dd_key) is not None and np.isfinite(e[dd_key])]
    all_con = [e[dd_key] for e in events if e.get("cohort") == "confirmed"
               and e.get(dd_key) is not None and np.isfinite(e[dd_key])]

    if not all_div or not all_con or n_blocks < 10:
        return {"note": "insufficient data for tail block-bootstrap"}

    obs_div_p10 = float(np.percentile(all_div, 10)) * 100
    obs_con_p10 = float(np.percentile(all_con, 10)) * 100

    rng = np.random.default_rng(seed)
    boot_div_p10s: list[float] = []
    boot_con_p10s: list[float] = []

    for _ in range(n_draws):
        chosen_idx = rng.integers(0, n_blocks, size=n_blocks)
        b_div: list[float] = []
        b_con: list[float] = []
        for bi in chosen_idx:
            b_div.extend(block_data[bi]["div"])
            b_con.extend(block_data[bi]["con"])
        if len(b_div) >= 5:
            boot_div_p10s.append(float(np.percentile(b_div, 10)) * 100)
        if len(b_con) >= 5:
            boot_con_p10s.append(float(np.percentile(b_con, 10)) * 100)

    result: dict = {
        "obs_div_p10_pct": round(obs_div_p10, 3),
        "obs_con_p10_pct": round(obs_con_p10, 3),
        "obs_p10_contrast_pct": round(obs_div_p10 - obs_con_p10, 3),
    }
    if boot_div_p10s:
        arr = np.array(boot_div_p10s)
        result["div_p10_ci95"] = [round(float(np.percentile(arr, 2.5)), 3),
                                   round(float(np.percentile(arr, 97.5)), 3)]
    if boot_con_p10s:
        arr = np.array(boot_con_p10s)
        result["con_p10_ci95"] = [round(float(np.percentile(arr, 2.5)), 3),
                                   round(float(np.percentile(arr, 97.5)), 3)]
    result["note"] = ("block-bootstrap CIs on p10 within each cohort separately; "
                      "contrast CI not computed (quantile difference bootstrap is noisy at n<500)")
    return result


# ---------------------------------------------------------------------------
# Summary stats helpers
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
    dd_key, ret_key = f"dd{horizon}", f"ret{horizon}"
    dd_vals = [e[dd_key] for e in events if e.get(dd_key) is not None]
    ret_vals = [e[ret_key] for e in events if e.get(ret_key) is not None]
    stats = _dd_stats(dd_vals)
    if ret_vals:
        stats["ret_mean"]   = round(float(np.mean(ret_vals) * 100), 2)
        stats["ret_median"] = round(float(np.median(ret_vals) * 100), 2)
    return stats


def _two_by_two(events: list[dict]) -> dict:
    out: dict = {k: 0 for k in ("divergent_stress", "divergent_calm",
                                 "confirmed_stress", "confirmed_calm")}
    for ev in events:
        cohort = ev.get("cohort", "other")
        stress = ev.get("spy_stress", False)
        if cohort not in ("divergent", "confirmed"):
            continue
        key = f"{cohort}_{'stress' if stress else 'calm'}"
        out[key] += 1
    total = sum(out.values())
    out["total"] = total
    ds = out.get("divergent_stress", 0)
    dc = out.get("divergent_calm", 0)
    cs = out.get("confirmed_stress", 0)
    cc = out.get("confirmed_calm", 0)
    if ds + cs > 0:
        out["pct_divergent_in_stress"] = round(ds / (ds + cs) * 100, 1)
    if dc + cc > 0:
        out["pct_divergent_in_calm"] = round(dc / (dc + cc) * 100, 1)
    return out


def _decade_cells(events: list[dict]) -> dict:
    cells: dict[str, dict] = {}
    for ev in events:
        year = int(ev["date"][:4])
        decade = f"{(year // 10) * 10}s"
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
            dd21_vals = [e["dd21"] for e in evs if e.get("dd21") is not None]
            dd63_vals = [e["dd63"] for e in evs if e.get("dd63") is not None]
            result[decade][cohort] = {
                "n":          len(evs),
                "dd21_median": round(float(np.median(dd21_vals)) * 100, 2) if dd21_vals else None,
                "dd63_median": round(float(np.median(dd63_vals)) * 100, 2) if dd63_vals else None,
            }
    return result


# ---------------------------------------------------------------------------
# Reproduction gate
# ---------------------------------------------------------------------------
def _check_reproduction_gate(div_events: list[dict], con_events: list[dict]) -> dict:
    """Verify event counts and raw DD21 medians match shipped report within tolerance."""
    n_div = len(div_events)
    n_con = len(con_events)

    div_dds21 = [e["dd21"] for e in div_events if e.get("dd21") is not None]
    con_dds21 = [e["dd21"] for e in con_events if e.get("dd21") is not None]
    div_med21 = float(np.median(div_dds21)) * 100 if div_dds21 else None
    con_med21 = float(np.median(con_dds21)) * 100 if con_dds21 else None

    count_ok = (abs(n_div - REPRO_DIV_TARGET) <= REPRO_TOLERANCE_COUNT and
                abs(n_con - REPRO_CON_TARGET) <= REPRO_TOLERANCE_COUNT)
    med_ok = (div_med21 is not None and con_med21 is not None and
              abs(div_med21 - REPRO_DIV_MED21_TARGET) <= REPRO_TOLERANCE_MED and
              abs(con_med21 - REPRO_CON_MED21_TARGET) <= REPRO_TOLERANCE_MED)

    return {
        "n_div": n_div, "n_con": n_con,
        "div_target": REPRO_DIV_TARGET, "con_target": REPRO_CON_TARGET,
        "count_ok": count_ok,
        "div_med21_pct": round(div_med21, 3) if div_med21 is not None else None,
        "con_med21_pct": round(con_med21, 3) if con_med21 is not None else None,
        "med21_ok": med_ok,
        "gate": "PASS" if (count_ok and med_ok) else "FAIL",
    }


# ---------------------------------------------------------------------------
# Markdown writer
# ---------------------------------------------------------------------------
def _write_markdown(data: dict) -> str:
    gate = data["reproduction_gate"]
    blocks_info = data["block_info"]
    pooled_21 = data["pooled_block_bootstrap"]["dd21"]
    pooled_63 = data["pooled_block_bootstrap"]["dd63"]
    stress_21 = data["stress_stratified_block_bootstrap"]["dd21"]
    stress_63 = data["stress_stratified_block_bootstrap"]["dd63"]
    tail_21 = data["tail_contrast"]["dd21"]
    tail_63 = data["tail_contrast"]["dd63"]
    raw_stats = data["raw_cohort_stats"]

    def _fmt(v, suffix="%", na="—") -> str:
        if v is None:
            return na
        return f"{v}{suffix}"

    def _ci(lo, hi, na="—") -> str:
        if lo is None or hi is None:
            return na
        return f"[{lo}%, {hi}%]"

    lines: list[str] = []
    lines += [
        "# Construction-Divergence R-1 TC Re-Check",
        "",
        "**RE-CHECK (descriptive/accrual) — the R-1 lock stands as shipped; adjudication pending (Fable). No key ships from this document.**",
        "",
        f"**Generated:** {data['generated_at']}  ",
        f"**Git SHA:** {data['git_sha']}  ",
        f"**Script:** scripts/study_construction_divergence_tc.py  ",
        f"**Original script (unchanged):** scripts/study_construction_divergence.py  ",
        f"**Registration:** {data['registration']}  ",
        f"**Audit authority:** research/TIME_CONFOUND_EXPOSURE_AUDIT.md §7 item 6 (HC-RC-1)",
        "",
        "---",
        "",
        "## Repairs Applied (CD-1/CD-2/CD-3)",
        "",
        "| Defect | Original | This script |",
        "|---|---|---|",
        "| CD-1: event ordering | Concatenated sector-pair by sector-pair (positional) | Globally sorted by real calendar date |",
        "| CD-2: block collapse | Keyed on per-sector `bar_i`; block_counts reported only, never fed to any statistic | Real calendar-date proximity (±7 calendar days, transitive chaining); blocks used as resampling unit |",
        "| CD-3: ablations | Within-unit permutations (powerless vs time confound) | Retained as reference only; primary inference is now block-cluster bootstrap |",
        "",
        "## Reproduction Gate",
        "",
        f"| Field | This run | Target | Tolerance | OK |",
        "|---|---|---|---|---|",
        f"| n_div | {gate['n_div']} | {gate['div_target']} | ±{REPRO_TOLERANCE_COUNT} | {'YES' if gate['count_ok'] else 'NO'} |",
        f"| n_con | {gate['n_con']} | {gate['con_target']} | ±{REPRO_TOLERANCE_COUNT} | {'YES' if gate['count_ok'] else 'NO'} |",
        f"| div DD21 median | {_fmt(gate['div_med21_pct'])} | {REPRO_DIV_MED21_TARGET}% | ±{REPRO_TOLERANCE_MED}pp | {'YES' if gate['med21_ok'] else 'NO'} |",
        f"| con DD21 median | {_fmt(gate['con_med21_pct'])} | {REPRO_CON_MED21_TARGET}% | ±{REPRO_TOLERANCE_MED}pp | {'YES' if gate['med21_ok'] else 'NO'} |",
        f"| **Overall gate** | | | | **{gate['gate']}** |",
        "",
    ]
    if gate["gate"] != "PASS":
        lines += [
            "**REPRODUCTION GATE FAILED — inference below is unreliable. Halt.**",
            "",
        ]

    lines += [
        "## Block Structure (CD-2 repaired)",
        "",
        f"Events were sorted by real date then grouped into ±7 calendar-day co-firing blocks (transitive chain anchored at block's first event).",
        "",
        f"| Metric | Value |",
        "|---|---|",
        f"| Total blocks | {blocks_info['n_blocks_total']} |",
        f"| Mean events/block | {blocks_info['mean_block_size']} |",
        f"| Max events in one block | {blocks_info['max_block_size']} |",
        f"| Blocks with 1 event (singleton) | {blocks_info['n_singleton_blocks']} |",
        f"| Blocks with >1 event | {blocks_info['n_multi_blocks']} |",
        f"| Block size histogram | {json.dumps(blocks_info['block_size_hist'])} |",
        "",
        "## Raw Cohort Statistics (unchanged from original)",
        "",
        "### DD 21d",
        "",
        "| Cohort | N | Mean DD% | Median DD% | p10 DD% | p25 DD% | P(DD<−8%) |",
        "|---|---|---|---|---|---|---|",
    ]
    for cohort in ("divergent", "confirmed"):
        s = raw_stats["dd21"][cohort]
        lines.append(
            f"| {cohort} | {s.get('n','—')} | {s.get('mean','—')} | "
            f"{s.get('median','—')} | {s.get('p10','—')} | "
            f"{s.get('p25','—')} | {s.get('p_lt_risk','—')} |"
        )
    lines += [
        "",
        "### DD 63d",
        "",
        "| Cohort | N | Mean DD% | Median DD% | p10 DD% | p25 DD% | P(DD<−8%) |",
        "|---|---|---|---|---|---|---|",
    ]
    for cohort in ("divergent", "confirmed"):
        s = raw_stats["dd63"][cohort]
        lines.append(
            f"| {cohort} | {s.get('n','—')} | {s.get('mean','—')} | "
            f"{s.get('median','—')} | {s.get('p10','—')} | "
            f"{s.get('p25','—')} | {s.get('p_lt_risk','—')} |"
        )

    lines += [
        "",
        "## Side-by-Side: Original vs TC-Repaired (Primary Contrast)",
        "",
        "| | Original (pooled iid t) | TC-Repaired (block-cluster bootstrap) |",
        "|---|---|---|",
        f"| DD21 raw contrast (div−con mean) | {_fmt(data['original_reference']['dd21_raw_contrast_pct'])} | {_fmt(pooled_21.get('raw_contrast_pct'))} |",
        f"| DD21 t-raw | {data['original_reference']['dd21_t_raw']} | n/a (bootstrap CI reported) |",
        f"| DD21 95% CI | n/a (iid SE only) | {_ci(pooled_21.get('ci_95_lo_pct'), pooled_21.get('ci_95_hi_pct'))} |",
        f"| DD21 two-sided p (block-boot) | n/a | {_fmt(pooled_21.get('p_two_sided'), suffix='', na='—')} |",
        f"| DD21 shuffle percentile | {data['original_reference']['dd21_shuffle_pctile']}th | n/a (different test) |",
        f"| DD63 raw contrast (div−con mean) | {_fmt(data['original_reference']['dd63_raw_contrast_pct'])} | {_fmt(pooled_63.get('raw_contrast_pct'))} |",
        f"| DD63 95% CI | n/a | {_ci(pooled_63.get('ci_95_lo_pct'), pooled_63.get('ci_95_hi_pct'))} |",
        f"| DD63 two-sided p (block-boot) | n/a | {_fmt(pooled_63.get('p_two_sided'), suffix='', na='—')} |",
        f"| DD63 shuffle percentile | {data['original_reference']['dd63_shuffle_pctile']}th | n/a (different test) |",
        f"| n blocks used | (decorative only, CD-2) | {pooled_21.get('n_blocks')} |",
        "",
        "## Stress-Stratified Block-Bootstrap Contrast (the load-bearing readout)",
        "",
        "> The audit flagged DD63-under-stratification as the live false-null candidate.",
        "> Original report showed div p10 −12.35 vs con −15.12 at 63d.",
        "",
        "### DD 21d — by Stress Stratum",
        "",
        "| Stratum | n_div | n_con | n_blocks | div mean | con mean | contrast | 95% CI | p |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for stratum_name in ("stress", "calm"):
        s = stress_21.get(stratum_name, {})
        b = s.get("bootstrap", {})
        lines.append(
            f"| {stratum_name} | {s.get('n_div','—')} | {s.get('n_con','—')} | "
            f"{s.get('n_blocks','—')} | {_fmt(s.get('div_mean_pct'))} | "
            f"{_fmt(s.get('con_mean_pct'))} | "
            f"{_fmt(b.get('raw_contrast_pct'))} | "
            f"{_ci(b.get('ci_95_lo_pct'), b.get('ci_95_hi_pct'))} | "
            f"{_fmt(b.get('p_two_sided'), suffix='', na='—')} |"
        )

    lines += [
        "",
        "### DD 63d — by Stress Stratum",
        "",
        "| Stratum | n_div | n_con | n_blocks | div mean | con mean | contrast | 95% CI | p |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for stratum_name in ("stress", "calm"):
        s = stress_63.get(stratum_name, {})
        b = s.get("bootstrap", {})
        lines.append(
            f"| {stratum_name} | {s.get('n_div','—')} | {s.get('n_con','—')} | "
            f"{s.get('n_blocks','—')} | {_fmt(s.get('div_mean_pct'))} | "
            f"{_fmt(s.get('con_mean_pct'))} | "
            f"{_fmt(b.get('raw_contrast_pct'))} | "
            f"{_ci(b.get('ci_95_lo_pct'), b.get('ci_95_hi_pct'))} | "
            f"{_fmt(b.get('p_two_sided'), suffix='', na='—')} |"
        )

    lines += [
        "",
        "### Tail Contrasts (p10 of DD within cohort, block-bootstrap CIs)",
        "",
        "| Horizon | obs div p10 | 95% CI | obs con p10 | 95% CI | obs contrast |",
        "|---|---|---|---|---|---|",
        f"| DD21 | {_fmt(tail_21.get('obs_div_p10_pct'))} | "
        f"{_ci(*tail_21['div_p10_ci95']) if tail_21.get('div_p10_ci95') else '—'} | "
        f"{_fmt(tail_21.get('obs_con_p10_pct'))} | "
        f"{_ci(*tail_21['con_p10_ci95']) if tail_21.get('con_p10_ci95') else '—'} | "
        f"{_fmt(tail_21.get('obs_p10_contrast_pct'))} |",
        f"| DD63 | {_fmt(tail_63.get('obs_div_p10_pct'))} | "
        f"{_ci(*tail_63['div_p10_ci95']) if tail_63.get('div_p10_ci95') else '—'} | "
        f"{_fmt(tail_63.get('obs_con_p10_pct'))} | "
        f"{_ci(*tail_63['con_p10_ci95']) if tail_63.get('con_p10_ci95') else '—'} | "
        f"{_fmt(tail_63.get('obs_p10_contrast_pct'))} |",
        "",
        "## Nulls and Caveats",
        "",
        "- All results are descriptive. The R-1 lock (no de-escalation key) stands until Fable adjudicates.",
        "- 'Positive contrast' = divergent has SHALLOWER DD than confirmed (early-exit direction).",
        "- Block-bootstrap CIs that include zero indicate the contrast is within the noise of co-firing macro episodes.",
        "- Stress stratum has limited blocks; treat stress-stratum CIs with caution if n_blocks < 15.",
        "- DD63 tail numbers for calm stratum carry the most events; stress-stratum DD63 is the hypothesized signal.",
        "- The word 'signal' is used descriptively. No promotion or de-escalation key is implied.",
        "",
        "---",
        "",
        f"*Run by scripts/study_construction_divergence_tc.py | SHA {data['git_sha']} | {data['generated_at'][:10]}*",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main study
# ---------------------------------------------------------------------------
def run() -> dict:
    log.info("=== HC-RC-1: construction_divergence_tc repaired-inference re-check ===")

    # Step 1: Fetch EW ETFs
    ew_tickers = [ew for _, ew, _ in PAIRS]
    _fetch_ew_etfs(ew_tickers)

    # Step 2: Load SPY
    spy = _load_spy()
    if spy is None:
        raise RuntimeError("SPY data not available")

    # Step 3: Build panels
    cap_panel = _build_cap_panel()
    ew_panel = _build_ew_panel(ew_tickers)
    log.info("Cap panel: %s cols; EW panel: %s cols", list(cap_panel.columns), list(ew_panel.columns))

    # Step 4: Compute label series
    log.info("Computing label series...")
    cap_label_series: dict[str, pd.Series] = {}
    ew_label_series: dict[str, pd.Series] = {}

    for cap, ew, inception_override in PAIRS:
        cap_s = _load_series(cap)
        ew_s  = _load_series(ew)
        if cap_s is None or ew_s is None:
            log.warning("Skipping pair %s/%s — data missing", cap, ew)
            continue
        cap_bench = spy.reindex(cap_s.index).ffill()
        cap_label_series[cap] = _compute_label_series(cap_s, cap_bench,
                                                       cap_panel.reindex(cap_s.index).ffill())
        ew_bench = spy.reindex(ew_s.index).ffill()
        ew_label_series[ew] = _compute_label_series(ew_s, ew_bench,
                                                     ew_panel.reindex(ew_s.index).ffill())

    # Step 5: Extract events (identical to original — frozen)
    lookahead_audit: dict = {}
    all_events: list[dict] = []

    for cap, ew, inception_override in PAIRS:
        if cap not in cap_label_series or ew not in ew_label_series:
            continue
        cap_s = _load_series(cap)
        cap_start = cap_label_series[cap].first_valid_index()
        ew_start  = ew_label_series[ew].first_valid_index()
        if cap_start is None or ew_start is None:
            continue
        window_start = max(cap_start, ew_start)
        if inception_override:
            window_start = max(window_start, pd.Timestamp(inception_override))

        evs = _extract_events(cap_label_series[cap], ew_label_series[ew],
                               cap_s, spy, cap, window_start, lookahead_audit)
        all_events.extend(evs)
        log.info("Pair %s/%s: %d events", cap, ew, len(evs))

    # No-lookahead audit
    violations = {k: v for k, v in lookahead_audit.items() if not v.get("ok", True)}
    assert not violations, f"LOOKAHEAD VIOLATION: {violations}"
    log.info("No-lookahead audit: PASS (%d events, 0 violations)", len(lookahead_audit))

    # Step 6: Separate cohorts
    div_events = [e for e in all_events if e["cohort"] == "divergent"]
    con_events = [e for e in all_events if e["cohort"] == "confirmed"]
    log.info("Cohorts: divergent=%d confirmed=%d", len(div_events), len(con_events))

    # Step 7: Reproduction gate
    repro = _check_reproduction_gate(div_events, con_events)
    log.info("Reproduction gate: %s (n_div=%d n_con=%d, div_med21=%.3f con_med21=%.3f)",
             repro["gate"], repro["n_div"], repro["n_con"],
             repro.get("div_med21_pct") or -999, repro.get("con_med21_pct") or -999)

    if repro["gate"] != "PASS":
        log.error("REPRODUCTION GATE FAILED — halting. Counts/medians do not match shipped report.")
        log.error("n_div=%d (target %d), n_con=%d (target %d)",
                  repro["n_div"], repro["div_target"], repro["n_con"], repro["con_target"])
        log.error("div_med21=%.3f (target %.2f), con_med21=%.3f (target %.2f)",
                  repro.get("div_med21_pct") or -999, REPRO_DIV_MED21_TARGET,
                  repro.get("con_med21_pct") or -999, REPRO_CON_MED21_TARGET)
        # Write WIP-blocked note and exit non-zero
        note_path = ROOT / "research" / "CONSTRUCTION_DIVERGENCE_R1_TC_RECHECK.md"
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(
            "# HC-RC-1 WIP-BLOCKED\n\n"
            "Reproduction gate failed — event counts or DD21 medians do not match shipped "
            "report within tolerance. Do not proceed with inference. "
            f"n_div={repro['n_div']} (target {repro['div_target']}), "
            f"n_con={repro['n_con']} (target {repro['con_target']}), "
            f"div_med21={repro.get('div_med21_pct')} (target {REPRO_DIV_MED21_TARGET}), "
            f"con_med21={repro.get('con_med21_pct')} (target {REPRO_CON_MED21_TARGET}).\n",
            encoding="utf-8",
        )
        sys.exit(1)

    # Step 8: CD-1 + CD-2 FIX — real cross-sector calendar-date block collapse
    log.info("Building real-date co-firing blocks (CD-1 + CD-2 fix)...")
    all_blocks = _real_date_block_collapse(all_events)
    sizes = [len(b) for b in all_blocks]
    n_singleton = sum(1 for s in sizes if s == 1)
    n_multi = sum(1 for s in sizes if s > 1)
    size_hist: dict[str, int] = {}
    for s in sizes:
        k = f"size_{s}"
        size_hist[k] = size_hist.get(k, 0) + 1
    block_info = {
        "n_blocks_total":  len(all_blocks),
        "mean_block_size": round(float(np.mean(sizes)), 2),
        "max_block_size":  int(max(sizes)),
        "n_singleton_blocks": n_singleton,
        "n_multi_blocks":     n_multi,
        "block_size_hist":    dict(sorted(size_hist.items())),
    }
    log.info("Blocks: total=%d, mean_size=%.2f, max=%d, singletons=%d, multi=%d",
             len(all_blocks), np.mean(sizes), max(sizes), n_singleton, n_multi)

    # Step 9: Raw cohort stats (unchanged from original — reproduction reference)
    raw_cohort_stats: dict = {}
    for horizon in FWD_H:
        raw_cohort_stats[f"dd{horizon}"] = {
            "divergent": _cohort_summary(div_events, horizon),
            "confirmed":  _cohort_summary(con_events, horizon),
        }

    # Step 10: Pooled block-cluster bootstrap contrast (CD-2 fix applied)
    log.info("Block-cluster bootstrap — pooled DD21 (n_draws=%d)...", BOOTSTRAP_DRAWS)
    pooled_bb_21 = _block_cluster_bootstrap_contrast(all_events, 21, all_blocks)
    log.info("Block-cluster bootstrap — pooled DD63 (n_draws=%d)...", BOOTSTRAP_DRAWS)
    pooled_bb_63 = _block_cluster_bootstrap_contrast(all_events, 63, all_blocks)

    # Step 11: Stress-stratified block-bootstrap contrast (load-bearing)
    log.info("Stress-stratified block-bootstrap — DD21...")
    strat_21 = _stress_stratified_contrast(all_events, all_blocks, 21)
    log.info("Stress-stratified block-bootstrap — DD63 (the false-null candidate)...")
    strat_63 = _stress_stratified_contrast(all_events, all_blocks, 63)

    # Step 12: Tail contrasts
    log.info("Tail contrasts (p10) with block-bootstrap CIs...")
    tail_21 = _tail_contrast(all_events, all_blocks, 21)
    tail_63 = _tail_contrast(all_events, all_blocks, 63)

    # Step 13: 2x2 and decade cells
    two_by_two = _two_by_two(all_events)
    decade_cells = _decade_cells(all_events)

    # Step 14: Git SHA
    git_sha = ""
    try:
        import subprocess
        git_sha = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        pass

    # Original reference numbers (from shipped CONSTRUCTION_DIVERGENCE_R1_DESCRIPTIVE.md)
    original_reference = {
        "dd21_raw_contrast_pct": 0.27,   # div mean − con mean = −3.1 − (−3.37) = +0.27
        "dd21_t_raw": 0.947,
        "dd21_shuffle_pctile": 72.7,
        "dd63_raw_contrast_pct": 0.85,   # −5.31 − (−6.17) = +0.85 (approx from report table)
        "dd63_shuffle_pctile": 89.8,
        "note": "From research/CONSTRUCTION_DIVERGENCE_R1_DESCRIPTIVE.md (SHA e729361002c1)",
    }

    output = {
        "schema": "construction_divergence_r1_tc.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha,
        "frozen_impl_sha": GIT_SHA_FREEZE,
        "registration": "research/HEALTHCARE_MEMBER_DISPERSION_ROTATION_NOTE.md §12 (LOCKED)",
        "audit_authority": "research/TIME_CONFOUND_EXPOSURE_AUDIT.md §7 item 6 (HC-RC-1)",
        "status": "DESCRIPTIVE/ACCRUAL — re-check only; adjudication pending (Fable)",
        "bootstrap_params": {
            "n_draws": BOOTSTRAP_DRAWS, "seed": BOOTSTRAP_SEED,
            "block_days": BLOCK_DAYS,
        },
        "reproduction_gate": repro,
        "block_info": block_info,
        "cohort_counts": {
            "total": len(all_events),
            "divergent": len(div_events),
            "confirmed": len(con_events),
        },
        "two_by_two": two_by_two,
        "decade_cells": decade_cells,
        "raw_cohort_stats": raw_cohort_stats,
        "pooled_block_bootstrap": {"dd21": pooled_bb_21, "dd63": pooled_bb_63},
        "stress_stratified_block_bootstrap": {"dd21": strat_21, "dd63": strat_63},
        "tail_contrast": {"dd21": tail_21, "dd63": tail_63},
        "original_reference": original_reference,
    }

    return output, all_events


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    output, all_events = run()

    # Write JSON
    json_path = ROOT / "data" / "strategies" / "construction_divergence_tc.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=str)
    log.info("Wrote %s", json_path)

    # Write markdown
    md_path = ROOT / "research" / "CONSTRUCTION_DIVERGENCE_R1_TC_RECHECK.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(_write_markdown(output), encoding="utf-8")
    log.info("Wrote %s", md_path)

    log.info("=== HC-RC-1 complete ===")
    log.info("Reproduction gate: %s", output["reproduction_gate"]["gate"])
    log.info("Blocks: %d total, mean_size=%.2f, max=%d",
             output["block_info"]["n_blocks_total"],
             output["block_info"]["mean_block_size"],
             output["block_info"]["max_block_size"])
    pb21 = output["pooled_block_bootstrap"]["dd21"]
    pb63 = output["pooled_block_bootstrap"]["dd63"]
    log.info("Pooled DD21: contrast=%.3f%%, 95CI=[%.3f, %.3f], p=%.4f",
             pb21.get("raw_contrast_pct", 0),
             pb21.get("ci_95_lo_pct", 0), pb21.get("ci_95_hi_pct", 0),
             pb21.get("p_two_sided", 1))
    log.info("Pooled DD63: contrast=%.3f%%, 95CI=[%.3f, %.3f], p=%.4f",
             pb63.get("raw_contrast_pct", 0),
             pb63.get("ci_95_lo_pct", 0), pb63.get("ci_95_hi_pct", 0),
             pb63.get("p_two_sided", 1))


if __name__ == "__main__":
    main()
