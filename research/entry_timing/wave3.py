"""wave3.py — Durable-Bottom Entry Timing Study, Wave 3

Spec: research/signal_engine/DURABLE_BOTTOM_FRAMEWORK.md §8
      "Wave-3 pre-registration (2026-07-02)" block — the GATES are law.
Reports: research/entry_timing/WAVE2_REPORT.md (precursor)

CLI:
  python3 research/entry_timing/wave3.py --panel {cn,hk,stocks}
        [--study triggers] [--tickers ...] [--workers 6] [--out DIR]

Defaults:
  --out research/entry_timing/_out/wave3_{panel}[_triggers]

Panels:
  cn     — data/china_search/closes.parquet (wide, close-only, >= 800 bars)
             sector: data/china_search/members.parquet (12 sectors)
             theme:  data/baskets_china/membership.json
             EVAL_START 2022-09-01; time-halves split at 2024-09-24
  hk     — data/hk_search/closes_deep.parquet (wide, close-only, >= 800 bars)
             sector: data/hk_breadth/constituents.parquet (160 rows)
             EVAL_START 2012-01-01; time-halves split at 2020-01-01
  stocks — data/stocks/*.parquet (OHLCV, existing deep panel)
             used only with --study triggers

Study:
  triggers — --panel stocks --study triggers
             Five trigger variants x {inside, outside} COILED state (daily)
             Output table T-B
"""
from __future__ import annotations

import sys
import time
import json
import argparse
import warnings
import logging
from pathlib import Path
from multiprocessing import Pool

import numpy as np
import pandas as pd

if __name__ == "__main__":
    # CLI-only silencers.  logging.disable() is PROCESS-GLOBAL state: at module level it
    # leaks out of any import of this file and mutes every logger for the rest of the
    # process (order-dependent pytest flakes; bitten twice — see walk_forward.py and
    # tests/test_no_module_level_logging_disable.py).
    warnings.filterwarnings("ignore")
    logging.disable(logging.CRITICAL)

# ── path bootstrap ────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
SIG_ENG = ROOT / "research" / "signal_engine"
ENTRY_TIMING = ROOT / "research" / "entry_timing"
sys.path.insert(0, str(SIG_ENG))
sys.path.insert(0, str(ENTRY_TIMING))

import tuning_harness as TH  # noqa: E402
import wave1                  # noqa: E402
import wave2                  # noqa: E402

# Re-import key symbols from wave1 / wave2
from wave1 import (
    label_events, build_tf_grids,
    build_sector_d_matrix, get_cohort_frac,
    pct, rate, med,
    FWD_REQ, STOP5, DEAD_MONEY_BAND, DEAD_MONEY_CAP,
    MFE_MAE_W, H6_COHORT_MIN_PEERS, H6_COHORT_THRESH,
    H5_FAILED_WINDOW, DD_MIN, DURABLE_HOLD, LIFTOFF_126,
    H1_D_DEEP_THRESH, CAPTURE, OUTCOME_W,
    TROUGH_W, MIN_TROUGH_SEP,
)
from wave2 import (
    label_events_w2,
    compute_outcomes_w2,
    compute_features_w2,
    build_theme_d_matrix,
    build_theme_peers,
    _serialize_d_matrix,
    _rate_row,
    build_T4 as _w2_build_T4,
    build_T5 as _w2_build_T5,
    build_T8 as _w2_build_T8,
    OUTCOME_W_H189, CLEAN15_MULT, STOP_MULT,
    H6_COHORT_THRESH,
)

# ── data paths ────────────────────────────────────────────────────────────────
DATA_STOCKS         = ROOT / "data" / "stocks"
DATA_CN_CLOSES      = ROOT / "data" / "china_search" / "closes.parquet"
DATA_CN_MEMBERS     = ROOT / "data" / "china_search" / "members.parquet"
DATA_CN_MEMBERSHIP  = ROOT / "data" / "baskets_china" / "membership.json"
DATA_HK_CLOSES      = ROOT / "data" / "hk_search" / "closes_deep.parquet"
DATA_HK_CONSTITUENTS = ROOT / "data" / "hk_breadth" / "constituents.parquet"
BREADTH_CONST       = ROOT / "data" / "breadth" / "constituents.parquet"

# ── panel constants ───────────────────────────────────────────────────────────
CN_MIN_BARS    = 800
CN_EVAL_START  = pd.Timestamp("2022-09-01")
CN_HALF_CUT    = pd.Timestamp("2024-09-24")  # stimulus pivot

HK_MIN_BARS    = 800
HK_EVAL_START  = pd.Timestamp("2012-01-01")
HK_HALF_CUT    = pd.Timestamp("2020-01-01")

STOCKS_MIN_BARS   = 1500
STOCKS_EVAL_START = pd.Timestamp("2012-01-01")

# ── Wave-3 variants ───────────────────────────────────────────────────────────
# CN and HK: same two variants as wave2 for the main panel tables
W3_VARIANTS_CLOSE = ["m2d_s3d", "base3d"]

# Triggers study: five variants
TRIGGER_VARIANTS = ["m2d_s3d", "m2d_s3d_early", "stochlead3d", "m2d_s2d", "m1d_s3d"]


# ══════════════════════════════════════════════════════════════════════════════
# CN / HK basket membership helpers (mirrors wave2 but for CN baskets_china)
# ══════════════════════════════════════════════════════════════════════════════

def load_cn_membership() -> dict:
    """Load data/baskets_china/membership.json."""
    with open(DATA_CN_MEMBERSHIP) as f:
        return json.load(f)


def build_cn_theme_peers(membership: dict) -> dict[str, set[str]]:
    """Build ticker -> set of co-members across all CN baskets.

    Structure: membership['baskets'][basket_name]['members'] is a list of dicts
    with keys 'ticker', 'removed' (None = active), etc.
    Active members only (removed is None).
    """
    basket_members: dict[str, list[str]] = {}
    for bname, bdata in membership["baskets"].items():
        active = [
            m["ticker"] for m in bdata.get("members", [])
            if isinstance(m, dict) and m.get("removed") is None
        ]
        if active:
            basket_members[bname] = active

    # ticker -> set of baskets
    ticker_baskets: dict[str, list[str]] = {}
    for bname, members in basket_members.items():
        for t in members:
            ticker_baskets.setdefault(t, []).append(bname)

    # peers = union of co-members minus self
    out: dict[str, set[str]] = {}
    for ticker, bnames in ticker_baskets.items():
        peers: set[str] = set()
        for bname in bnames:
            peers.update(basket_members[bname])
        peers.discard(ticker)
        out[ticker] = peers
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Wide-parquet loader helpers (CN / HK: close-only)
# ══════════════════════════════════════════════════════════════════════════════

def load_close_only_wide(parquet_path: Path, min_bars: int) -> dict[str, pd.Series]:
    """Load a wide close-only parquet. Returns {ticker: daily_series} for tickers >= min_bars."""
    wide = pd.read_parquet(parquet_path)
    # rows = dates, cols = tickers
    out: dict[str, pd.Series] = {}
    for ticker in wide.columns:
        s = wide[ticker].dropna()
        if len(s) >= min_bars:
            out[ticker] = s
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Close-only sector weekly-D matrix (built from wide parquet, no file per name)
# ══════════════════════════════════════════════════════════════════════════════

def build_sector_d_matrix_from_close_dict(
    close_dict: dict[str, pd.Series],
    sector_map: dict[str, str],
) -> dict:
    """Build {ticker: (DatetimeIndex, weekly_D_daily_array)} from a dict of close series.

    Mirrors wave1.build_sector_d_matrix but uses a pre-loaded close dict rather than
    reading individual parquet files. Only builds entries for tickers that have a sector.
    """
    out: dict = {}
    for ticker, daily in close_dict.items():
        if ticker not in sector_map:
            continue
        try:
            sw = daily.resample("W-FRI").last().dropna()
            known_w = daily.resample("W-FRI").apply(
                lambda x: x.dropna().index.max()
            ).reindex(sw.index).dropna()
            sw = sw.reindex(known_w.index)
            _, dw = TH.stoch_rsi_kd(sw)
            known_w_dt = pd.Series(pd.to_datetime(known_w.values), index=known_w.index)
            dw_daily = TH.to_daily(dw, known_w_dt, daily.index, "ffill")
            out[ticker] = (daily.index, dw_daily.to_numpy())
        except Exception:
            continue
    return out


def build_theme_d_matrix_from_close_dict(
    close_dict: dict[str, pd.Series],
    theme_peers: dict[str, set[str]],
    panel_tickers: set[str],
) -> dict:
    """Build weekly-D matrix for theme peers (CN baskets), from close dict."""
    needed: set[str] = set()
    for ticker in panel_tickers:
        peers = theme_peers.get(ticker, set())
        needed.update(peers)
    needed.update(panel_tickers)

    out: dict = {}
    for ticker in needed:
        if ticker not in close_dict:
            continue
        daily = close_dict[ticker]
        try:
            sw = daily.resample("W-FRI").last().dropna()
            known_w = daily.resample("W-FRI").apply(
                lambda x: x.dropna().index.max()
            ).reindex(sw.index).dropna()
            sw = sw.reindex(known_w.index)
            _, dw = TH.stoch_rsi_kd(sw)
            known_w_dt = pd.Series(pd.to_datetime(known_w.values), index=known_w.index)
            dw_daily = TH.to_daily(dw, known_w_dt, daily.index, "ffill")
            out[ticker] = (daily.index, dw_daily.to_numpy())
        except Exception:
            continue
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Per-name processing (close-only, no low_stop5, no H4 volume)
# ══════════════════════════════════════════════════════════════════════════════

def _process_closeonly_inner(
    ticker: str,
    daily: pd.Series,
    sector_map: dict[str, str],
    sector_d_matrix: dict,
    theme_peers: dict[str, set[str]] | None,
    theme_d_matrix: dict | None,
    eval_start: pd.Timestamp,
    min_bars: int,
    variants: list[str],
) -> dict:
    """Process one close-only name. No high/low/volume → no low_stop5, no H4."""
    if len(daily) < min_bars:
        return {}

    c      = daily.to_numpy()
    idx    = daily.index
    n      = len(c)

    # Synthetic high/low = close (no data)
    hi = pd.Series(np.nan, index=idx)
    lo = pd.Series(np.nan, index=idx)
    hi_arr = np.full(n, np.nan)
    lo_arr = np.full(n, np.nan)
    vol_arr = None  # no volume

    # Label events (wave-2 extended)
    events_df = label_events_w2(daily)
    events_df["ticker"] = ticker

    # Build capture windows
    event_windows = []
    for _, ev in events_df.iterrows():
        t0     = ev["t0"]
        t0_pos = idx.get_loc(t0)
        event_windows.append({
            "t0_pos":      t0_pos,
            "w_start":     t0_pos + CAPTURE[0],
            "w_end":       t0_pos + CAPTURE[1],
            "label":       ev["label"],
            "p0":          ev["p0"],
            "b30":         ev["b30"],
            "dd_at_trough": ev["dd_at_trough"],
        })

    # TF grids (no SPY ratio for CN/HK; rs_low feature will be None)
    grids = build_tf_grids(daily, hi, lo, spy_ratio=None)

    result = {"events": events_df.to_dict("records")}

    for variant_name in variants:
        cfg   = TH.VARIANTS[variant_name]
        frame = TH.build_signals(daily, cfg, hi, lo)
        raw_fires = frame.index[frame["buy"]].tolist()

        fire_rows: list[dict] = []
        variant_fires_before: list[dict] = []

        for sig_date in raw_fires:
            i = idx.get_loc(sig_date)

            fill_idx  = i + 1
            if fill_idx >= n:
                continue
            fill_date = idx[fill_idx]

            # Track pre-eval fires for failed_180
            if fill_date < eval_start:
                pre_row: dict = {
                    "fill_idx":       fill_idx,
                    "sig_idx":        i,
                    "stop5":          0,
                    "resolution_idx": fill_idx + OUTCOME_W,
                }
                if fill_idx + FWD_REQ < n:
                    from wave1 import compute_outcomes as _w1_out
                    out_pre = _w1_out(fill_idx, c[fill_idx], c, hi_arr, lo_arr)
                    pre_row["stop5"]          = out_pre["stop5"]
                    pre_row["resolution_idx"] = out_pre["resolution_idx"]
                variant_fires_before.append(pre_row)
                continue

            if fill_idx + FWD_REQ >= n:
                continue

            p = c[fill_idx]
            if np.isnan(p):
                continue

            # Outcomes (close-only: low_stop5 will equal stop5 since lo=NaN→uses close)
            outcomes = compute_outcomes_w2(fill_idx, p, c, hi_arr, lo_arr)
            # For close-only panels we do NOT report low_stop5 (drop it)
            outcomes.pop("low_stop5", None)

            # Features (wave-2 extended, but vol_arr=None => H4 features all None)
            features = compute_features_w2(
                i, grids, vol_arr, variant_fires_before,
                ticker, sig_date,
                sector_map, sector_d_matrix,
                theme_peers, theme_d_matrix,
                eval_start,
            )

            # Event linkage
            captured  = False
            ev_label  = None
            premium   = None
            lead      = None
            for ew in event_windows:
                if ew["w_start"] <= i <= ew["w_end"]:
                    captured = True
                    ev_label = ew["label"]
                    premium  = p / ew["p0"] - 1 if ew["p0"] > 0 else None
                    lead     = i - ew["t0_pos"]
                    break

            row = {
                "ticker":   ticker,
                "sig_date": sig_date,
                "fill_date": fill_date,
                "p":        p,
                **outcomes,
                **features,
                "captured": captured,
                "ev_label": ev_label,
                "premium":  premium,
                "lead":     lead,
            }

            fire_rows.append(row)
            variant_fires_before.append({
                "fill_idx":       fill_idx,
                "sig_idx":        i,
                "stop5":          outcomes["stop5"],
                "resolution_idx": outcomes["resolution_idx"],
            })

        result[variant_name] = fire_rows

    return result


def _closeonly_worker(args: tuple) -> tuple[str, dict]:
    """Multiprocessing worker for close-only panel."""
    (ticker, close_vals, close_idx,
     sector_map, sector_d_matrix_ser,
     theme_peers, theme_d_matrix_ser,
     eval_start_str, min_bars, variants) = args

    # Reconstruct daily series
    # FIX: dates serialized as ISO strings to avoid ms→ns corruption
    daily = pd.Series(
        close_vals,
        index=pd.DatetimeIndex(close_idx),
    )

    # Reconstruct sector_d_matrix
    sector_d_matrix: dict = {}
    for t, (idx_vals, arr) in sector_d_matrix_ser.items():
        sector_d_matrix[t] = (pd.DatetimeIndex(idx_vals), np.array(arr))

    # Reconstruct theme_d_matrix
    theme_d_matrix: dict | None = None
    if theme_d_matrix_ser is not None:
        theme_d_matrix = {}
        for t, (idx_vals, arr) in theme_d_matrix_ser.items():
            theme_d_matrix[t] = (pd.DatetimeIndex(idx_vals), np.array(arr))

    eval_start = pd.Timestamp(eval_start_str)

    try:
        result = _process_closeonly_inner(
            ticker, daily,
            sector_map, sector_d_matrix,
            theme_peers, theme_d_matrix,
            eval_start, min_bars, variants,
        )
        return (ticker, result)
    except Exception as e:
        return (ticker, {"_error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# Table builders for wave3 (CN/HK):
#   T1, T3, T4, T5, T8 — all reused from wave2's _rate_row + helpers
#   where differences arise (no low_stop5, theme-only for CN), we handle inline
# ══════════════════════════════════════════════════════════════════════════════

def build_T1_w3(fires: pd.DataFrame, variant_name: str) -> list[dict]:
    """T1 pooled: same strata as wave2 T1.

    m2d_s3d rows: ALL / in_washout / COILED / noncoiled_washout / STAR /
                  coiled_no_div / div_only_noncoiled
    base3d rows: ALL + COILED
    """
    rows = []
    h6 = fires["h6_cohort_sector"] if "h6_cohort_sector" in fires.columns else pd.Series(np.nan, index=fires.index)

    rows.append(_rate_row(fires, "ALL"))

    if variant_name == "base3d":
        coiled_mask = fires["coiled"].astype(bool) if "coiled" in fires.columns else pd.Series(False, index=fires.index)
        rows.append(_rate_row(fires[coiled_mask], "COILED"))
        return rows

    washout_mask = fires["in_washout_ctx"].astype(bool) if "in_washout_ctx" in fires.columns else pd.Series(False, index=fires.index)
    coiled_mask  = fires["coiled"].astype(bool) if "coiled" in fires.columns else pd.Series(False, index=fires.index)
    bull_mask    = fires["bull_div"].astype(bool) if "bull_div" in fires.columns else pd.Series(False, index=fires.index)
    h6_notna     = h6.notna()

    rows.append(_rate_row(fires[washout_mask], "in_washout"))
    rows.append(_rate_row(fires[coiled_mask],  "COILED"))

    ncw_mask = washout_mask & h6_notna & (h6 < H6_COHORT_THRESH)
    rows.append(_rate_row(fires[ncw_mask], "noncoiled_washout"))

    rows.append(_rate_row(fires[coiled_mask & bull_mask],  "STAR"))
    rows.append(_rate_row(fires[coiled_mask & ~bull_mask], "coiled_no_div"))
    rows.append(_rate_row(fires[~coiled_mask & bull_mask & washout_mask], "div_only_noncoiled"))

    return rows


def build_T3_w3(fires: pd.DataFrame, half_cut: pd.Timestamp,
                has_theme: bool = False) -> list[dict]:
    """T3 time-half rows for COILED and noncoiled_washout.
    CN also gets COILED_theme rows if has_theme=True.
    """
    fires = fires.copy()
    fires["fill_date"] = pd.to_datetime(fires["fill_date"])

    pre_mask  = fires["fill_date"] < half_cut
    post_mask = fires["fill_date"] >= half_cut

    washout_mask = fires["in_washout_ctx"].astype(bool) if "in_washout_ctx" in fires.columns else pd.Series(False, index=fires.index)
    coiled_mask  = fires["coiled"].astype(bool) if "coiled" in fires.columns else pd.Series(False, index=fires.index)
    h6_s = fires["h6_cohort_sector"] if "h6_cohort_sector" in fires.columns else pd.Series(np.nan, index=fires.index)
    h6_t = fires["h6_cohort_theme"]  if "h6_cohort_theme"  in fires.columns else pd.Series(np.nan, index=fires.index)

    ncw_mask         = washout_mask & h6_s.notna() & (h6_s < H6_COHORT_THRESH)
    coiled_theme_mask = washout_mask & h6_t.notna() & (h6_t >= H6_COHORT_THRESH)
    ncw_theme_mask    = washout_mask & h6_t.notna() & (h6_t < H6_COHORT_THRESH)

    rows = []
    for period_label, mask in [("pre_half", pre_mask), ("post_half", post_mask)]:
        sub_c  = fires[mask & coiled_mask]
        sub_nc = fires[mask & ncw_mask]
        rows.append({
            "cut":         period_label,
            "cohort_type": "sector",
            "stratum":     "COILED",
            **_rate_row(sub_c, f"COILED_{period_label}"),
        })
        rows.append({
            "cut":         period_label,
            "cohort_type": "sector",
            "stratum":     "noncoiled_washout",
            **_rate_row(sub_nc, f"ncw_{period_label}"),
        })

    if has_theme:
        for period_label, mask in [("all", pd.Series(True, index=fires.index)),
                                   ("pre_half", pre_mask), ("post_half", post_mask)]:
            tc  = fires[mask & coiled_theme_mask]
            tnc = fires[mask & ncw_theme_mask]
            rows.append({
                "cut":         period_label,
                "cohort_type": "theme",
                "stratum":     "COILED_theme",
                **_rate_row(tc, f"COILED_theme_{period_label}"),
            })
            rows.append({
                "cut":         period_label,
                "cohort_type": "theme",
                "stratum":     "noncoiled_theme",
                **_rate_row(tnc, f"ncw_theme_{period_label}"),
            })

    return rows


def build_T4_w3(fires: pd.DataFrame) -> dict:
    """T4 per-name majority (>= 3 fires each stratum). Reuses wave2's build_T4."""
    return _w2_build_T4(fires)


def build_T5_w3(fires: pd.DataFrame) -> list[dict]:
    """T5 cohort quartiles among in_washout fires. Reuses wave2's build_T5."""
    return _w2_build_T5(fires)


def build_T8_w3(fires: pd.DataFrame, events: pd.DataFrame) -> dict:
    """T8 recall economics. Reuses wave2's build_T8."""
    return _w2_build_T8(fires, events, fires)


# ══════════════════════════════════════════════════════════════════════════════
# Tencent case: list all m2d_s3d fires for 0700.HK from 2021-01-01
# ══════════════════════════════════════════════════════════════════════════════

def build_tencent_case(fires_m: pd.DataFrame) -> list[dict]:
    """Return all 0700.HK m2d_s3d fires from 2021-01-01 onward with the required fields."""
    if len(fires_m) == 0:
        return []

    sub = fires_m[
        (fires_m["ticker"] == "0700.HK")
        & (pd.to_datetime(fires_m["sig_date"]) >= pd.Timestamp("2021-01-01"))
    ].copy()

    if len(sub) == 0:
        return []

    # Collect the required fields; gracefully handle absent columns
    def _get(row, col, default=None):
        v = row.get(col, default)
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return default
        return v

    rows = []
    for _, row in sub.iterrows():
        rows.append({
            "sig_date":    str(pd.Timestamp(row["sig_date"]).date()),
            "coiled":      bool(_get(row, "coiled", False)),
            "star":        bool(_get(row, "star", False)),
            "h6_cohort_sector": _get(row, "h6_cohort_sector"),
            "washout_ctx": bool(_get(row, "in_washout_ctx", False)),
            "bull_div":    bool(_get(row, "bull_div", False)),
            "stop5":       _get(row, "stop5"),
            "clean15":     _get(row, "clean15"),
            "dead_money":  _get(row, "dead_money"),
            "mfe63":       round(float(row["mfe63"]) * 100, 2) if not pd.isna(_get(row, "mfe63")) else None,
        })

    return rows


# ══════════════════════════════════════════════════════════════════════════════
# CN / HK main pipeline (--panel cn|hk)
# ══════════════════════════════════════════════════════════════════════════════

def run_panel_closeonly(panel: str, tickers_filter: list[str],
                        workers: int, out_dir: Path) -> dict:
    """Run wave3 for CN or HK close-only panel. Returns tables dict."""
    t_start = time.time()

    if panel == "cn":
        closes_path   = DATA_CN_CLOSES
        members_path  = DATA_CN_MEMBERS
        min_bars      = CN_MIN_BARS
        eval_start    = CN_EVAL_START
        half_cut      = CN_HALF_CUT
        has_theme     = True
    else:  # hk
        closes_path   = DATA_HK_CLOSES
        members_path  = DATA_HK_CONSTITUENTS
        min_bars      = HK_MIN_BARS
        eval_start    = HK_EVAL_START
        half_cut      = HK_HALF_CUT
        has_theme     = False

    print(f"Wave-3 | panel={panel} | eval_start={eval_start.date()} "
          f"| half_cut={half_cut.date()} | min_bars={min_bars} | workers={workers}")

    # ── Load close-only wide parquet ────────────────────────────────────────
    print(f"Loading {closes_path} ...")
    close_dict = load_close_only_wide(closes_path, min_bars)
    print(f"Tickers with >={min_bars} bars: {len(close_dict)}")

    # Apply ticker filter
    if tickers_filter:
        wanted = set(tickers_filter)
        close_dict = {t: s for t, s in close_dict.items() if t in wanted}
        print(f"Ticker filter applied: {len(close_dict)} names")

    ticker_list = list(close_dict.keys())

    # ── Load sector map ─────────────────────────────────────────────────────
    sector_map: dict[str, str] = {}
    if members_path.exists():
        mem_df = pd.read_parquet(members_path)
        # index = ticker, column 'sector'
        if "sector" in mem_df.columns:
            for sym in mem_df.index:
                sector_map[sym] = mem_df.loc[sym, "sector"]
    print(f"Sector map: {len(sector_map)} tickers")

    # HK: report overlap count
    if panel == "hk":
        hk_cols     = set(close_dict.keys())
        hkc_tickers = set(sector_map.keys())
        overlap     = hk_cols & hkc_tickers
        print(f"HK ticker-format overlap: {len(overlap)} of {len(hk_cols)} closes matched to constituents")

    # ── Load theme peers (CN only) ───────────────────────────────────────────
    theme_peers: dict[str, set[str]] | None = None
    if has_theme and DATA_CN_MEMBERSHIP.exists():
        membership = load_cn_membership()
        theme_peers = build_cn_theme_peers(membership)
        print(f"CN theme peers: {len(theme_peers)} tickers have peer sets")

    # ── Build sector weekly-D matrix ─────────────────────────────────────────
    print("Building sector weekly-D matrix...")
    t0_mat = time.time()
    sector_d_matrix = build_sector_d_matrix_from_close_dict(close_dict, sector_map)
    # For HK/CN we want ALL same-sector tickers (not just the panel subset) for the
    # cohort. If a ticker filter is applied and some sector peers are missing from the
    # filtered close_dict, we reload ALL close-only data for peer-sector tickers.
    if tickers_filter:
        print("  Reloading full panel for sector-D-matrix (cohort peers)...")
        full_close_dict = load_close_only_wide(closes_path, min_bars)
        sector_d_matrix = build_sector_d_matrix_from_close_dict(full_close_dict, sector_map)
    print(f"  Sector D-matrix: {len(sector_d_matrix)} tickers ({time.time()-t0_mat:.1f}s)")

    # ── Build theme weekly-D matrix (CN only) ────────────────────────────────
    theme_d_matrix: dict | None = None
    if has_theme and theme_peers is not None:
        print("Building CN theme weekly-D matrix...")
        t0_th = time.time()
        # Use full_close_dict if available, else close_dict
        _close_for_theme = full_close_dict if tickers_filter else close_dict
        theme_d_matrix = build_theme_d_matrix_from_close_dict(
            _close_for_theme, theme_peers, set(ticker_list)
        )
        print(f"  Theme D-matrix: {len(theme_d_matrix)} tickers ({time.time()-t0_th:.1f}s)")

    # ── Serialize matrices for multiprocessing ───────────────────────────────
    sector_d_matrix_ser = _serialize_d_matrix(sector_d_matrix)
    theme_d_matrix_ser  = _serialize_d_matrix(theme_d_matrix) if theme_d_matrix else None

    # ── Build worker args ────────────────────────────────────────────────────
    worker_args = []
    for ticker in ticker_list:
        daily = close_dict[ticker]
        worker_args.append((
            ticker,
            daily.to_numpy().tolist(),
            daily.index.strftime("%Y-%m-%d").tolist(),  # ISO strings (no ms→ns corruption)
            sector_map,
            sector_d_matrix_ser,
            theme_peers,
            theme_d_matrix_ser,
            eval_start.strftime("%Y-%m-%d"),
            min_bars,
            W3_VARIANTS_CLOSE,
        ))

    # ── Run pool ─────────────────────────────────────────────────────────────
    print(f"\nProcessing {len(worker_args)} names with {workers} workers...")
    t0_run = time.time()

    if workers <= 1:
        results = [_closeonly_worker(a) for a in worker_args]
    else:
        with Pool(workers) as pool:
            results = pool.map(_closeonly_worker, worker_args)

    all_fires_by_variant: dict[str, list[dict]] = {v: [] for v in W3_VARIANTS_CLOSE}
    all_events: list[dict] = []
    processed_tickers: list[str] = []
    errors: list[str] = []

    for ticker, result in results:
        if "_error" in result:
            errors.append(f"{ticker}: {result['_error']}")
            continue
        if not result:
            continue
        for vname in W3_VARIANTS_CLOSE:
            all_fires_by_variant[vname].extend(result.get(vname, []))
        all_events.extend(result.get("events", []))
        processed_tickers.append(ticker)

    total_elapsed = time.time() - t0_run
    n_names = len(processed_tickers)
    if errors:
        print(f"Errors ({len(errors)}): {errors[:5]}")
    print(f"Done: {n_names} names in {total_elapsed:.1f}s ({total_elapsed/max(n_names,1):.1f}s/name)")

    # ── Build DataFrames ──────────────────────────────────────────────────────
    events_df = pd.DataFrame(all_events)
    if "t0" in events_df.columns:
        events_df["t0"] = pd.to_datetime(events_df["t0"])

    fires_dfs: dict[str, pd.DataFrame] = {}
    for vname in W3_VARIANTS_CLOSE:
        rows = all_fires_by_variant[vname]
        if rows:
            df_v = pd.DataFrame(rows)
            df_v["sig_date"]  = pd.to_datetime(df_v["sig_date"])
            df_v["fill_date"] = pd.to_datetime(df_v["fill_date"])
            fires_dfs[vname] = df_v
        else:
            fires_dfs[vname] = pd.DataFrame()

    # ── Save parquets ─────────────────────────────────────────────────────────
    events_df.to_parquet(out_dir / "events.parquet", index=False)
    for vname in W3_VARIANTS_CLOSE:
        fires_dfs[vname].to_parquet(out_dir / f"fires_{vname}.parquet", index=False)
    print(f"Saved parquets to {out_dir}")

    # ── Build wave3_tables.json ───────────────────────────────────────────────
    fires_m = fires_dfs.get("m2d_s3d", pd.DataFrame())

    tables: dict = {
        "_meta": {
            "panel":       panel,
            "n_names":     n_names,
            "eval_start":  str(eval_start.date()),
            "half_cut":    str(half_cut.date()),
            "min_bars":    min_bars,
            "workers":     workers,
            "runtime_s":   round(total_elapsed, 1),
        }
    }

    # T1
    tables["T1"] = {}
    for vname in W3_VARIANTS_CLOSE:
        f = fires_dfs[vname]
        tables["T1"][vname] = build_T1_w3(f, vname) if len(f) > 0 else []

    # T3 — time halves
    tables["T3"] = build_T3_w3(fires_m, half_cut, has_theme=has_theme) if len(fires_m) > 0 else []

    # T4
    tables["T4"] = build_T4_w3(fires_m) if len(fires_m) > 0 else {}

    # T5
    tables["T5"] = build_T5_w3(fires_m) if len(fires_m) > 0 else []

    # T8
    tables["T8"] = build_T8_w3(fires_m, events_df) if len(fires_m) > 0 and len(events_df) > 0 else {}

    # HK EXTRA — tencent_case
    if panel == "hk":
        tables["tencent_case"] = build_tencent_case(fires_m)

    # Save
    tables_path = out_dir / "wave3_tables.json"
    with open(tables_path, "w") as f:
        json.dump(tables, f, indent=2, default=str)
    print(f"Saved wave3_tables.json to {tables_path}")

    # ── Print compact summary ─────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print(f"WAVE-3 SUMMARY | panel={panel}")
    print("=" * 70)
    n_ev = len(events_df)
    n_dur  = int((events_df["label"] == "durable").sum()) if n_ev > 0 else 0
    n_trap = int((events_df["label"] == "trap").sum())    if n_ev > 0 else 0
    print(f"Events: total={n_ev}  durable={n_dur}  trap={n_trap}")

    for vname in W3_VARIANTS_CLOSE:
        fires = fires_dfs[vname]
        if len(fires) == 0:
            print(f"\n--- {vname}: NO FIRES ---")
            continue

        coiled_mask  = fires["coiled"].astype(bool) if "coiled" in fires.columns else pd.Series(False, index=fires.index)
        washout_mask = fires["in_washout_ctx"].astype(bool) if "in_washout_ctx" in fires.columns else pd.Series(False, index=fires.index)
        h6_s = fires["h6_cohort_sector"] if "h6_cohort_sector" in fires.columns else pd.Series(np.nan, index=fires.index)
        ncw_mask = washout_mask & h6_s.notna() & (h6_s < H6_COHORT_THRESH)
        star_mask = fires["star"].astype(bool) if "star" in fires.columns else pd.Series(False, index=fires.index)

        n_all    = len(fires)
        n_coiled = int(coiled_mask.sum())
        n_star   = int(star_mask.sum())
        n_ncw    = int(ncw_mask.sum())
        all_s5   = round(float(fires["stop5"].mean()) * 100, 2)
        all_c15  = round(float(fires["clean15"].mean()) * 100, 2)
        c_s5  = round(float(fires[coiled_mask]["stop5"].mean()) * 100, 2)   if n_coiled > 0 else float("nan")
        c_c15 = round(float(fires[coiled_mask]["clean15"].mean()) * 100, 2) if n_coiled > 0 else float("nan")
        s_c15 = round(float(fires[star_mask]["clean15"].mean()) * 100, 2)   if n_star > 0 else float("nan")
        nc_c15 = round(float(fires[ncw_mask]["clean15"].mean()) * 100, 2)   if n_ncw > 0 else float("nan")

        print(f"\n--- {vname} ---")
        print(f"  fires={n_all}  coiled={n_coiled}  star={n_star}  ncw={n_ncw}")
        print(f"  ALL:    stop5={all_s5}%  clean15={all_c15}%")
        if n_coiled > 0:
            print(f"  COILED: stop5={c_s5}%  clean15={c_c15}%")
        if n_star > 0:
            print(f"  STAR:   clean15={s_c15}%")
        if n_ncw > 0:
            print(f"  NCW:    clean15={nc_c15}%")
        if not np.isnan(c_c15) and not np.isnan(nc_c15):
            print(f"  COILED vs NCW clean15 spread: {round(c_c15 - nc_c15, 2)}pp")

    print("=" * 70)
    wall_total = time.time() - t_start
    secs_per_name = total_elapsed / max(n_names, 1)
    full_n = {"cn": 1382, "hk": 157}[panel]
    projected = secs_per_name * full_n / max(workers, 1) / 60
    print(f"\nProjected full {panel} runtime: ~{projected:.1f} min @ --workers {workers} ({full_n} names)")

    return tables, events_df, fires_dfs


# ══════════════════════════════════════════════════════════════════════════════
# Triggers study (--panel stocks --study triggers)
# ══════════════════════════════════════════════════════════════════════════════

def _compute_washout_state_daily(c: np.ndarray, n: int) -> np.ndarray:
    """Compute per-bar washout_state array (same logic as in_washout_ctx in wave1).

    washout_state[i] = True iff:
      capit_idx = argmin(c[max(0,i-90)..i])
      dd_at_capit = c[capit_idx] / max(c[capit_idx-126..capit_idx]) - 1  <= -DD_MIN

    O(n) per name with a sliding-window argmin. We use a simple loop; this is
    intentionally O(n) and fast enough for 200-500 names.
    """
    washout = np.zeros(n, dtype=bool)
    for i in range(n):
        start90 = max(0, i - 90)
        window90 = c[start90: i + 1]
        capit_local = int(np.argmin(window90))
        capit_idx = start90 + capit_local

        if capit_idx < 126:
            continue
        prior_max = np.nanmax(c[capit_idx - 126: capit_idx])
        if prior_max <= 0:
            continue
        dd_at = c[capit_idx] / prior_max - 1
        washout[i] = dd_at <= -DD_MIN
    return washout


def _compute_daily_coiled_state(
    daily: pd.Series,
    ticker: str,
    sector_map: dict[str, str],
    sector_d_matrix: dict,
) -> np.ndarray:
    """Compute COILED_state per bar: washout_state AND cohort >= 0.4.

    Returns boolean array aligned to daily.index.
    """
    c   = daily.to_numpy()
    idx = daily.index
    n   = len(c)

    # washout state per bar
    washout = _compute_washout_state_daily(c, n)

    # sector weekly-D daily-mapped (for cohort fraction)
    # Use the pre-computed sector_d_matrix; build cohort fraction for each bar
    my_sector = sector_map.get(ticker)
    coiled = np.zeros(n, dtype=bool)

    if my_sector is None:
        return coiled

    peers = [t for t, sec in sector_map.items() if sec == my_sector and t != ticker
             and t in sector_d_matrix]

    if len(peers) < H6_COHORT_MIN_PEERS:
        return coiled

    for i in range(n):
        if not washout[i]:
            continue
        bar_date = idx[i]
        vals = []
        for p in peers:
            pidx, pdw = sector_d_matrix[p]
            pos = pidx.searchsorted(bar_date, side="right") - 1
            if pos < 0:
                continue
            v = pdw[pos]
            if not np.isnan(v):
                vals.append(v)
        if len(vals) < H6_COHORT_MIN_PEERS:
            continue
        frac = float(np.mean(np.array(vals) < 30))
        coiled[i] = frac >= H6_COHORT_THRESH

    return coiled


def _triggers_worker(args: tuple) -> tuple[str, dict]:
    """Multiprocessing worker for trigger study."""
    (ticker, fp, spy_ratio_vals, spy_ratio_idx,
     sector_map, sector_d_matrix_ser,
     eval_start_str, min_bars) = args

    # Reconstruct spy_ratio
    spy_ratio: pd.Series | None = None
    if spy_ratio_vals is not None and spy_ratio_idx is not None:
        spy_ratio = pd.Series(spy_ratio_vals, index=pd.DatetimeIndex(spy_ratio_idx))

    # Reconstruct sector_d_matrix
    sector_d_matrix: dict = {}
    for t, (idx_vals, arr) in sector_d_matrix_ser.items():
        sector_d_matrix[t] = (pd.DatetimeIndex(idx_vals), np.array(arr))

    eval_start = pd.Timestamp(eval_start_str)

    try:
        result = _triggers_inner(
            ticker, fp, spy_ratio,
            sector_map, sector_d_matrix,
            eval_start, min_bars,
        )
        return (ticker, result)
    except Exception as e:
        return (ticker, {"_error": str(e)})


def _triggers_inner(
    ticker: str,
    fp: str,
    spy_ratio: pd.Series | None,
    sector_map: dict[str, str],
    sector_d_matrix: dict,
    eval_start: pd.Timestamp,
    min_bars: int,
) -> dict:
    """Inner processing for one name in the triggers study."""
    df = pd.read_parquet(fp)
    daily = df["close"].dropna()
    if len(daily) < min_bars:
        return {}

    hi  = df["high"].reindex(daily.index)   if "high"   in df.columns else pd.Series(np.nan, index=daily.index)
    lo  = df["low"].reindex(daily.index)    if "low"    in df.columns else pd.Series(np.nan, index=daily.index)
    vol = df["volume"].reindex(daily.index) if "volume" in df.columns else None

    c      = daily.to_numpy()
    hi_arr = hi.to_numpy()
    lo_arr = lo.to_numpy()
    vol_arr = vol.to_numpy() if vol is not None else None
    idx    = daily.index
    n      = len(c)

    # SPY ratio alignment
    spy_ratio_aligned: pd.Series | None = None
    if spy_ratio is not None:
        try:
            spy_ratio_aligned = spy_ratio.reindex(daily.index, method="ffill")
        except Exception:
            pass

    # Label events (for recall_B15 computation)
    events_df = label_events(daily)
    events_df["ticker"] = ticker

    # Build capture windows
    event_windows = []
    for _, ev in events_df.iterrows():
        t0     = ev["t0"]
        t0_pos = idx.get_loc(t0)
        event_windows.append({
            "t0_pos": t0_pos,
            "w_start": t0_pos + CAPTURE[0],
            "w_end":   t0_pos + CAPTURE[1],
            "label":   ev["label"],
            "p0":      ev["p0"],
        })

    # Compute daily COILED_state (no div in the state — div is a fire-bar feature, not a state)
    coiled_state = _compute_daily_coiled_state(daily, ticker, sector_map, sector_d_matrix)

    # TF grids (for premium-over-trough: need capit_idx from grids)
    grids = build_tf_grids(daily, hi, lo, spy_ratio_aligned)

    result = {"events": events_df.to_dict("records")}

    for variant_name in TRIGGER_VARIANTS:
        cfg   = TH.VARIANTS[variant_name]
        frame = TH.build_signals(daily, cfg, hi, lo)
        raw_fires = frame.index[frame["buy"]].tolist()

        fire_rows: list[dict] = []

        for sig_date in raw_fires:
            i = idx.get_loc(sig_date)
            fill_idx = i + 1
            if fill_idx >= n:
                continue
            fill_date = idx[fill_idx]
            if fill_date < eval_start:
                continue
            if fill_idx + FWD_REQ >= n:
                continue

            p = c[fill_idx]
            if np.isnan(p):
                continue

            # Outcomes (full OHLCV available for US panel)
            from wave1 import compute_outcomes as _w1_out
            outcomes = _w1_out(fill_idx, p, c, hi_arr, lo_arr)

            # COILED_state at signal bar
            inside_coiled = bool(coiled_state[i])

            # Premium over trough: capit_idx from grids
            start90 = max(0, i - 90)
            window90 = c[start90: i + 1]
            capit_local = int(np.argmin(window90))
            capit_idx = start90 + capit_local
            trough_p = c[capit_idx]
            premium_over_trough = (p / trough_p - 1) if (trough_p > 0 and not np.isnan(trough_p)) else np.nan

            # Event linkage for recall
            captured  = False
            ev_label  = None
            lead      = None
            for ew in event_windows:
                if ew["w_start"] <= i <= ew["w_end"]:
                    captured = True
                    ev_label = ew["label"]
                    lead     = i - ew["t0_pos"]
                    break

            row = {
                "ticker":               ticker,
                "variant":              variant_name,
                "sig_date":             sig_date,
                "fill_date":            fill_date,
                "p":                    p,
                "inside_coiled":        inside_coiled,
                "stop5":                outcomes["stop5"],
                "clean15":              outcomes["clean15"],
                "dead_money":           outcomes["dead_money"],
                "mfe63":                outcomes["mfe63"],
                "premium_over_trough":  premium_over_trough,
                "captured":             captured,
                "ev_label":             ev_label,
                "lead":                 lead,
            }

            fire_rows.append(row)

        result[variant_name] = fire_rows

    return result


def _recall_for_fires(fire_sub: pd.DataFrame, ev_sub: pd.DataFrame) -> float:
    """Fraction of events with >=1 fire from fire_sub in [t0-7cal, t0+21cal] window."""
    if len(fire_sub) == 0 or len(ev_sub) == 0:
        return float("nan")
    fire_sub = fire_sub.copy()
    fire_sub["sig_date"] = pd.to_datetime(fire_sub["sig_date"])
    hit = 0
    for _, ev in ev_sub.iterrows():
        ticker = ev["ticker"]
        t0     = pd.Timestamp(ev["t0"])
        w_start = t0 - pd.Timedelta(days=7)
        w_end   = t0 + pd.Timedelta(days=21)
        matching = fire_sub[
            (fire_sub["ticker"] == ticker)
            & (fire_sub["sig_date"] >= w_start)
            & (fire_sub["sig_date"] <= w_end)
        ]
        if len(matching) > 0:
            hit += 1
    return hit / len(ev_sub)


def build_TB(all_fires: pd.DataFrame, events_df: pd.DataFrame) -> list[dict]:
    """Build Table T-B: variant x {inside, outside} COILED_state.

    Columns: variant, cell (inside/outside), n, stop5, clean15, dead_money,
             med_premium_over_trough, med_lead, recall_B15_if_only_this_cell,
             ticker_half_even_clean15, ticker_half_odd_clean15 (sign stability)
    The m2d_s3d inside row is flagged as baseline.
    """
    events_df = events_df.copy()
    events_df["t0"] = pd.to_datetime(events_df["t0"])
    dur_events = events_df[events_df["label"] == "durable"]

    all_tickers = sorted(all_fires["ticker"].unique())
    half_even = set(all_tickers[::2])
    half_odd  = set(all_tickers[1::2])

    rows = []
    for variant_name in TRIGGER_VARIANTS:
        v_fires = all_fires[all_fires["variant"] == variant_name]
        for cell_label, inside_flag in [("inside", True), ("outside", False)]:
            sub = v_fires[v_fires["inside_coiled"] == inside_flag]
            n = len(sub)

            if n == 0:
                rows.append({
                    "variant": variant_name, "cell": cell_label, "n": 0,
                    "stop5": float("nan"), "clean15": float("nan"),
                    "dead_money": float("nan"),
                    "med_premium_over_trough": float("nan"),
                    "med_lead": float("nan"),
                    "recall_B15_if_only_this_cell": float("nan"),
                    "ticker_half_even_clean15": float("nan"),
                    "ticker_half_odd_clean15": float("nan"),
                    "is_baseline": False,
                })
                continue

            stop5_r    = round(float(sub["stop5"].mean()) * 100, 2)
            clean15_r  = round(float(sub["clean15"].mean()) * 100, 2)
            dead_money_r = round(float(sub["dead_money"].mean()) * 100, 2)
            med_prem   = round(float(sub["premium_over_trough"].dropna().median()) * 100, 2) if sub["premium_over_trough"].notna().any() else float("nan")
            med_lead   = float(sub["lead"].dropna().median()) if sub["lead"].notna().any() else float("nan")

            recall_B15 = _recall_for_fires(sub, dur_events)
            recall_B15_r = round(recall_B15 * 100, 2) if not np.isnan(recall_B15) else float("nan")

            # Ticker-half sign stability
            sub_even = sub[sub["ticker"].isin(half_even)]
            sub_odd  = sub[sub["ticker"].isin(half_odd)]
            even_c15 = round(float(sub_even["clean15"].mean()) * 100, 2) if len(sub_even) > 0 else float("nan")
            odd_c15  = round(float(sub_odd["clean15"].mean()) * 100, 2) if len(sub_odd) > 0 else float("nan")

            rows.append({
                "variant":                     variant_name,
                "cell":                        cell_label,
                "n":                           n,
                "stop5":                       stop5_r,
                "clean15":                     clean15_r,
                "dead_money":                  dead_money_r,
                "med_premium_over_trough":     med_prem,
                "med_lead":                    med_lead,
                "recall_B15_if_only_this_cell": recall_B15_r,
                "ticker_half_even_clean15":    even_c15,
                "ticker_half_odd_clean15":     odd_c15,
                "is_baseline":                 (variant_name == "m2d_s3d" and cell_label == "inside"),
            })

    return rows


def run_triggers_study(tickers_filter: list[str], workers: int, out_dir: Path) -> dict:
    """Run the triggers study (--panel stocks --study triggers)."""
    t_start = time.time()
    min_bars   = STOCKS_MIN_BARS
    eval_start = STOCKS_EVAL_START
    data_dir   = DATA_STOCKS

    print(f"Wave-3 triggers study | eval_start={eval_start.date()} | min_bars={min_bars} | workers={workers}")

    # ── Resolve file list ────────────────────────────────────────────────────
    all_files = sorted(data_dir.glob("*.parquet"))
    if tickers_filter:
        wanted = set(tickers_filter)
        all_files = [f for f in all_files if f.stem in wanted]

    panel_files: list[Path] = []
    for fp in all_files:
        try:
            df = pd.read_parquet(fp)
            if len(df["close"].dropna()) >= min_bars:
                panel_files.append(fp)
        except Exception:
            pass
    print(f"Panel files (>={min_bars} bars): {len(panel_files)}")

    # ── Sector map (constituents.parquet) ────────────────────────────────────
    sector_map: dict[str, str] = {}
    if BREADTH_CONST.exists():
        const_df = pd.read_parquet(BREADTH_CONST)
        for sym in const_df.index:
            sector_map[sym] = const_df.loc[sym, "sector"]
    print(f"Sector map: {len(sector_map)} tickers")

    # ── Sector D-matrix (build from ALL files for full cohort coverage) ─────
    print("Building sector weekly-D matrix from full data dir...")
    t0_mat = time.time()
    sector_peer_files = [fp for fp in sorted(data_dir.glob("*.parquet")) if fp.stem in sector_map]
    sector_d_matrix = build_sector_d_matrix(
        [str(fp) for fp in sector_peer_files], sector_map
    )
    print(f"  D-matrix: {len(sector_d_matrix)} tickers ({time.time()-t0_mat:.1f}s)")

    # ── SPY ──────────────────────────────────────────────────────────────────
    spy_path = DATA_STOCKS / "SPY.parquet"
    if not spy_path.exists():
        spy_path = ROOT / "data" / "yahoo" / "SPY.parquet"
    spy_close: pd.Series | None = None
    if spy_path.exists():
        spy_close = pd.read_parquet(spy_path)["close"].dropna()

    # ── Serialize ─────────────────────────────────────────────────────────────
    sector_d_matrix_ser = _serialize_d_matrix(sector_d_matrix)

    # ── Build worker args ────────────────────────────────────────────────────
    worker_args = []
    for fp in panel_files:
        ticker = fp.stem
        spy_vals = None
        spy_idx_vals = None
        if spy_close is not None:
            try:
                df_t = pd.read_parquet(fp)
                daily_t = df_t["close"].dropna()
                spy_aligned = spy_close.reindex(daily_t.index, method="ffill")
                spy_ratio_s = (daily_t / spy_aligned).replace([np.inf, -np.inf], np.nan)
                spy_vals     = spy_ratio_s.to_numpy().tolist()
                spy_idx_vals = daily_t.index.strftime("%Y-%m-%d").tolist()
            except Exception:
                pass
        worker_args.append((
            ticker, str(fp),
            spy_vals, spy_idx_vals,
            sector_map, sector_d_matrix_ser,
            eval_start.strftime("%Y-%m-%d"),
            min_bars,
        ))

    # ── Run pool ─────────────────────────────────────────────────────────────
    print(f"\nProcessing {len(worker_args)} names with {workers} workers...")
    t0_run = time.time()

    if workers <= 1:
        results = [_triggers_worker(a) for a in worker_args]
    else:
        with Pool(workers) as pool:
            results = pool.map(_triggers_worker, worker_args)

    all_fire_rows: list[dict] = []
    all_events: list[dict] = []
    processed_tickers: list[str] = []
    errors: list[str] = []

    for ticker, result in results:
        if "_error" in result:
            errors.append(f"{ticker}: {result['_error']}")
            continue
        if not result:
            continue
        for vname in TRIGGER_VARIANTS:
            all_fire_rows.extend(result.get(vname, []))
        all_events.extend(result.get("events", []))
        processed_tickers.append(ticker)

    total_elapsed = time.time() - t0_run
    n_names = len(processed_tickers)
    if errors:
        print(f"Errors ({len(errors)}): {errors[:5]}")
    print(f"Done: {n_names} names in {total_elapsed:.1f}s ({total_elapsed/max(n_names,1):.1f}s/name)")

    # ── DataFrames ─────────────────────────────────────────────────────────
    all_fires_df = pd.DataFrame(all_fire_rows)
    events_df    = pd.DataFrame(all_events)
    if "t0" in events_df.columns:
        events_df["t0"] = pd.to_datetime(events_df["t0"])
    if len(all_fires_df) > 0:
        all_fires_df["sig_date"]  = pd.to_datetime(all_fires_df["sig_date"])
        all_fires_df["fill_date"] = pd.to_datetime(all_fires_df["fill_date"])

    # Save
    events_df.to_parquet(out_dir / "events.parquet", index=False)
    all_fires_df.to_parquet(out_dir / "fires_triggers.parquet", index=False)
    print(f"Saved parquets to {out_dir}")

    # ── Build T-B ─────────────────────────────────────────────────────────
    tb_rows = build_TB(all_fires_df, events_df) if len(all_fires_df) > 0 else []

    tables: dict = {
        "_meta": {
            "study":       "triggers",
            "panel":       "stocks",
            "n_names":     n_names,
            "eval_start":  str(eval_start.date()),
            "min_bars":    min_bars,
            "workers":     workers,
            "runtime_s":   round(total_elapsed, 1),
            "variants":    TRIGGER_VARIANTS,
        },
        "T-B": tb_rows,
    }

    tables_path = out_dir / "wave3_tables.json"
    with open(tables_path, "w") as f:
        json.dump(tables, f, indent=2, default=str)
    print(f"Saved wave3_tables.json to {tables_path}")

    # ── Print summary ─────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("WAVE-3 TRIGGERS SUMMARY | T-B")
    print("=" * 70)
    if tb_rows:
        print(f"{'variant':<18} {'cell':<10} {'n':>6}  stop5%  clean15%  dead$%  med_prem%  B15_recall%")
        for r in tb_rows:
            baseline_flag = " *** BASELINE" if r.get("is_baseline") else ""
            print(f"  {r['variant']:<16} {r['cell']:<10} {r['n']:>6}  "
                  f"{r['stop5']:>5}  {r['clean15']:>7}  {r['dead_money']:>5}  "
                  f"{r['med_premium_over_trough']:>8}  {r['recall_B15_if_only_this_cell']:>10}"
                  f"{baseline_flag}")

    wall_total = time.time() - t_start
    secs_per_name = total_elapsed / max(n_names, 1)
    n_full = 211
    projected = secs_per_name * n_full / max(workers, 1) / 60
    print(f"\nProjected full triggers runtime: ~{projected:.1f} min @ --workers {workers} ({n_full} names)")

    return tables, all_fires_df, events_df


# ══════════════════════════════════════════════════════════════════════════════
# Smoke assertions
# ══════════════════════════════════════════════════════════════════════════════

def run_smoke_cn(tables: dict, events_df: pd.DataFrame, fires_dfs: dict):
    """CN smoke assertions."""
    print("\n" + "=" * 70)
    print("SMOKE — CN panel")
    print("=" * 70)
    errors: list[str] = []

    n_dur  = int((events_df["label"] == "durable").sum()) if len(events_df) > 0 else 0
    n_trap = int((events_df["label"] == "trap").sum())    if len(events_df) > 0 else 0
    print(f"[1] Events: durable={n_dur}, trap={n_trap}")
    if n_dur  == 0: errors.append("No durable events")
    if n_trap == 0: errors.append("No trap events")

    fires_m = fires_dfs.get("m2d_s3d", pd.DataFrame())
    n_fires = len(fires_m)
    print(f"[2] m2d_s3d fires: {n_fires}")
    if n_fires == 0:
        errors.append("No m2d_s3d fires")

    if n_fires > 0:
        n_coiled = int(fires_m["coiled"].sum()) if "coiled" in fires_m.columns else 0
        n_star   = int(fires_m["star"].sum())   if "star"   in fires_m.columns else 0
        h6_notna = int(fires_m["h6_cohort_sector"].notna().sum()) if "h6_cohort_sector" in fires_m.columns else 0
        print(f"[3] COILED={n_coiled}, STAR={n_star}, h6_notna={h6_notna}/{n_fires}")

        if n_coiled == 0 and h6_notna < 5:
            # In small subset, COILED may be zero but h6 must be non-null for some
            errors.append("h6_cohort_sector all null — sector D-matrix not working")
        if n_coiled > 0:
            print(f"    COILED non-degenerate: OK (n={n_coiled})")
        else:
            # Acceptable in very small subset; verify h6 is non-null and time-varying
            print(f"    COILED=0 (small subset); verifying h6_cohort_sector non-null & time-varying...")
            if h6_notna > 0:
                h6_vals = fires_m["h6_cohort_sector"].dropna().values
                h6_var  = np.std(h6_vals) > 0.001
                print(f"    h6_cohort_sector: {h6_notna} non-null, std={np.std(h6_vals):.4f} ({'time-varying' if h6_var else 'FLAT'})")
                if not h6_var:
                    errors.append("h6_cohort_sector is non-null but constant — cohort not working")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
        raise AssertionError(f"CN smoke: {len(errors)} failure(s)")
    else:
        print("CN smoke: PASS")


def run_smoke_hk(tables: dict, events_df: pd.DataFrame, fires_dfs: dict):
    """HK smoke assertions."""
    print("\n" + "=" * 70)
    print("SMOKE — HK panel")
    print("=" * 70)
    errors: list[str] = []

    n_dur  = int((events_df["label"] == "durable").sum()) if len(events_df) > 0 else 0
    n_trap = int((events_df["label"] == "trap").sum())    if len(events_df) > 0 else 0
    print(f"[1] Events: durable={n_dur}, trap={n_trap}")
    if n_dur  == 0: errors.append("No durable events")
    if n_trap == 0: errors.append("No trap events")

    fires_m = fires_dfs.get("m2d_s3d", pd.DataFrame())
    n_fires = len(fires_m)
    print(f"[2] m2d_s3d fires: {n_fires}")
    if n_fires == 0:
        errors.append("No m2d_s3d fires")

    # tencent_case: 0700.HK fires from 2021+
    tc = tables.get("tencent_case", [])
    print(f"[3] tencent_case rows: {len(tc)}")
    if len(tc) == 0:
        errors.append("tencent_case has 0 rows (0700.HK fires 2021+ expected)")
    else:
        print(f"    First entry: {tc[0]}")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
        raise AssertionError(f"HK smoke: {len(errors)} failure(s)")
    else:
        print("HK smoke: PASS")


def run_smoke_triggers(tables: dict, all_fires_df: pd.DataFrame, events_df: pd.DataFrame):
    """Triggers smoke assertions."""
    print("\n" + "=" * 70)
    print("SMOKE — triggers study")
    print("=" * 70)
    errors: list[str] = []

    tb = tables.get("T-B", [])
    if len(tb) == 0:
        errors.append("T-B table is empty!")
    else:
        # All 5 variants x 2 cells should be present
        found_cells = {(r["variant"], r["cell"]) for r in tb}
        for v in TRIGGER_VARIANTS:
            for cell in ["inside", "outside"]:
                if (v, cell) not in found_cells:
                    errors.append(f"T-B missing ({v}, {cell})")
        print(f"[1] T-B rows: {len(tb)}  expected: {len(TRIGGER_VARIANTS)*2}")

        # m2d_s3d inside non-empty
        baseline = next((r for r in tb if r["variant"] == "m2d_s3d" and r["cell"] == "inside"), None)
        if baseline is None or baseline["n"] == 0:
            errors.append("m2d_s3d inside cell is empty!")
        else:
            print(f"[2] m2d_s3d inside: n={baseline['n']}  stop5={baseline['stop5']}%  clean15={baseline['clean15']}%")

        # m2d_s3d ALL matches wave-2 smoke reference within 1pp
        # Reference from wave-2 smoke: stop5=36.54, clean15=35.01 on 8-ticker set
        # For the triggers study, ALL fires = inside + outside together
        if len(all_fires_df) > 0:
            m2d_all = all_fires_df[all_fires_df["variant"] == "m2d_s3d"]
            SMOKE_TICKERS = {"AAPL", "MSFT", "NVDA", "JNJ", "WMT", "XOM", "KO", "CAT"}
            smoke_m2d = m2d_all[m2d_all["ticker"].isin(SMOKE_TICKERS)]
            if len(smoke_m2d) > 0:
                s5  = round(float(smoke_m2d["stop5"].mean()) * 100, 2)
                c15 = round(float(smoke_m2d["clean15"].mean()) * 100, 2)
                print(f"[3] m2d_s3d ALL (8-ticker smoke): stop5={s5}% (ref 36.54±1pp), clean15={c15}% (ref 35.01±1pp)")
                if abs(s5 - 36.54) > 1.0:
                    errors.append(f"m2d_s3d stop5={s5} differs from wave-2 ref 36.54 by >1pp")
                if abs(c15 - 35.01) > 1.0:
                    errors.append(f"m2d_s3d clean15={c15} differs from wave-2 ref 35.01 by >1pp")
            else:
                print("[3] Smoke tickers not all in panel subset — wave-2 consistency check skipped")

        # COILED-inside cells non-empty for at least one variant
        inside_cells = [r for r in tb if r["cell"] == "inside" and r["n"] > 0]
        print(f"[4] COILED-inside cells non-empty: {len(inside_cells)} of {len(TRIGGER_VARIANTS)}")
        if len(inside_cells) == 0:
            errors.append("All COILED-inside cells are empty!")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
        raise AssertionError(f"Triggers smoke: {len(errors)} failure(s)")
    else:
        print("Triggers smoke: PASS")


# ══════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ══════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="Wave-3 durable-bottom entry timing study")
    ap.add_argument("--panel", required=True, choices=["cn", "hk", "stocks"],
                    help="Panel: cn, hk, or stocks (stocks only used with --study triggers)")
    ap.add_argument("--study", default="", choices=["", "triggers"],
                    help="Optional study: triggers (--panel stocks only)")
    ap.add_argument("--tickers", default="",
                    help="Comma-separated ticker subset (default: all)")
    ap.add_argument("--workers", type=int, default=6,
                    help="Multiprocessing pool size")
    ap.add_argument("--out", default="",
                    help="Output directory (default: research/entry_timing/_out/wave3_{panel}[_triggers])")
    args = ap.parse_args()

    if args.study and args.panel != "stocks":
        ap.error("--study triggers is only valid with --panel stocks")

    tickers_filter = [t.strip() for t in args.tickers.split(",") if t.strip()] if args.tickers else []

    suffix = f"_triggers" if args.study == "triggers" else ""
    if args.out:
        out_dir = Path(args.out)
    else:
        out_dir = ROOT / "research" / "entry_timing" / "_out" / f"wave3_{args.panel}{suffix}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Output: {out_dir}")

    if args.study == "triggers":
        tables, all_fires_df, events_df = run_triggers_study(tickers_filter, args.workers, out_dir)
        run_smoke_triggers(tables, all_fires_df, events_df)
    elif args.panel in ("cn", "hk"):
        tables, events_df, fires_dfs = run_panel_closeonly(args.panel, tickers_filter, args.workers, out_dir)
        if args.panel == "cn":
            run_smoke_cn(tables, events_df, fires_dfs)
        else:
            run_smoke_hk(tables, events_df, fires_dfs)
    else:
        # --panel stocks without --study
        ap.error("--panel stocks requires --study triggers")


if __name__ == "__main__":
    main()
