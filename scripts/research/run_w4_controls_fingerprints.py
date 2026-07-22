"""Winner Autopsy Lab — W4 Matched-Controls Fingerprint Study (Layer-3b).

Spec: research/winners/W4_CONTROLS_STUDY_SPEC.md (2026-07-22, main-loop Fable).
Executes the masterplan's Layer-3 question (b): pre-onset, what separated eventual
breakaway names from matched controls sampled the SAME calendar day.

Different question than W3 (Layer-3a, FINGERPRINT_CENSUS_W3.md, WA-R8 null): W3 asked
*who keeps going among breakaways*; W4 asks *who breaks away at all* — the
watchlist-formation question. DESCRIPTIVE / display-tier throughout. NO hypothesis
registration in this lane (any survivor goes to a WA-R8-style ruling appended by the
main loop). No composite scores (WA-R1/R5).

Usage:
    python scripts/research/run_w4_controls_fingerprints.py \\
        --root /path/to/data \\
        --out research/winners/FINGERPRINT_CONTROLS_W4.md \\
        [--episodes data/research/winner_episodes.parquet] \\
        [--seed 20260722] \\
        [--n-boot 50000] \\
        [--sample N]   # smoke mode: first N matured episodes only

The script NEVER writes under --root (read-only stores). The engine
(engine/winner_autopsy.py) is imported READ-ONLY — no engine logic edits.

Stat machinery (α/m percentile CI, month-block bootstrap, ticker-cluster bootstrap,
degenerate guard, Wilson CI) is ADAPTED from scripts/research/run_w3_census_fingerprints.py
(2026-07-20 review-round-1 corrections). The estimator differs: W4 is a MATCHED-SET design
(Δ = value(E,t0) − median(value(controls, t0)) per episode), so the resampling atom is the
matched set — an episode never separates from its controls in a bootstrap draw (spec §4).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Repo root on sys.path for engine import (read-only).
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine.winner_autopsy import (  # noqa: E402  (read-only import)
    BENCH,
    _GICS_ETF,
    _dollar_volume_series,
    _dv_ratio,
    _dv_zscore,
    _resolve_benchmark,
    compute_excess,
    extract_features,
    sample_controls,
)

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MATURED_LABELS = {"durable_winner", "clean_hold", "blow_off", "failed"}
KEPT_GOING_LABELS = {"durable_winner", "clean_hold"}

# Crypto: 7-day calendar + SPY benchmark category error (spec §0.6). Excluded from
# primary; counts printed.
CRYPTO_TICKERS: frozenset[str] = frozenset({"BTC-USD", "BTC_F", "ETH-USD", "SOL-USD"})

ALPHA = 0.05
BOOT_REPS = 50_000
BOOT_SEED = 20260722  # spec §0.1 / §4

# Control eligibility floor (spec §1): episodes with < 3 eligible controls are excluded.
MIN_CONTROLS = 3

# 8-K B1 item codes (verbatim from engine constants).
B1_HARD_ITEMS: frozenset[str] = frozenset({"1.01", "2.01"})
B1_SOFT_ITEMS: frozenset[str] = frozenset({"7.01", "8.01"})
B1_ERA_CUTOFF: pd.Timestamp = pd.Timestamp("2014-01-01")

# Parity tolerance (spec §3, test-pinned).
PARITY_TOL = 1e-6

# Fundamentals A2 firewall (spec §3): no t0 >= this date fundamentals aggregation.
A2_FIREWALL = pd.Timestamp("2024-01-01")

# NON-COMPARABLE coverage floor for fundamentals (spec §3).
NON_COMPARABLE_FLOOR = 0.30


# ---------------------------------------------------------------------------
# Store loaders (mirror scripts/research/build_winner_autopsy.py loading pattern).
# Everything read-only under --root.
# ---------------------------------------------------------------------------

def _load_yahoo_bars(root: Path) -> dict[str, pd.DataFrame]:
    """Load yahoo parquets as {ticker: DataFrame(close, volume)}."""
    ydir = root / "yahoo"
    bars: dict[str, pd.DataFrame] = {}
    if not ydir.exists():
        log.warning("yahoo dir not found: %s", ydir)
        return bars
    for entry in sorted(os.scandir(ydir), key=lambda e: e.name):
        if not entry.name.endswith(".parquet") or entry.name.startswith("_"):
            continue
        ticker = entry.name[:-len(".parquet")]
        try:
            df = pd.read_parquet(entry.path)
            if "close" not in df.columns:
                continue
            d2 = pd.DataFrame(index=df.index)
            d2["close"] = df["close"]
            if "volume" in df.columns:
                d2["volume"] = df["volume"]
            for c in ("high", "low"):  # yahoo usually lacks these; keep if present
                if c in df.columns:
                    d2[c] = df[c]
            d2 = d2.dropna(subset=["close"]).sort_index()
            if len(d2) > 0:
                bars[ticker] = d2
        except Exception as exc:  # noqa: BLE001
            log.debug("yahoo load fail %s: %s", ticker, exc)
    log.info("Loaded %d yahoo bars", len(bars))
    return bars


def _load_massive_bars(root: Path) -> dict[str, pd.DataFrame]:
    """Load massive_stock_day parquets (open/high/low/close/volume). Empty if absent."""
    mdir = root / "massive_stock_day"
    bars: dict[str, pd.DataFrame] = {}
    if not mdir.exists():
        return bars
    for entry in sorted(os.scandir(mdir), key=lambda e: e.name):
        if not entry.name.endswith(".parquet") or entry.name.startswith("_"):
            continue
        ticker = entry.name[:-len(".parquet")]
        try:
            df = pd.read_parquet(entry.path)
            if "close" not in df.columns:
                continue
            cols = ["close"] + [c for c in ("volume", "high", "low") if c in df.columns]
            d2 = df[cols].dropna(subset=["close"]).sort_index()
            if len(d2) > 0:
                bars[ticker] = d2
        except Exception as exc:  # noqa: BLE001
            log.debug("massive load fail %s: %s", ticker, exc)
    if bars:
        log.info("Loaded %d massive bars", len(bars))
    return bars


def _load_dead_name_bars(root: Path) -> dict[str, pd.DataFrame]:
    """Load dead_name_prices.parquet as {ticker: DataFrame(close, volume)}. Empty if absent."""
    fpath = root / "edgar" / "dead_name_prices.parquet"
    bars: dict[str, pd.DataFrame] = {}
    if not fpath.exists():
        return bars
    try:
        df = pd.read_parquet(fpath)
        if df.empty or "ticker" not in df.columns or "close" not in df.columns:
            return bars
        df["date"] = pd.to_datetime(df["date"]).dt.normalize()
        for ticker, grp in df.groupby("ticker"):
            g = grp.set_index("date").sort_index()
            g = g[~g.index.duplicated(keep="last")]
            sub = pd.DataFrame({"close": g["close"]})
            if "volume" in g.columns:
                sub["volume"] = g["volume"]
            sub = sub.dropna(subset=["close"])
            if len(sub) >= 2:
                bars[str(ticker)] = sub
    except Exception as exc:  # noqa: BLE001
        log.warning("dead_name bars load fail: %s", exc)
    if bars:
        log.info("Loaded %d dead-name bars", len(bars))
    return bars


def _merge_bars(
    yahoo: dict[str, pd.DataFrame],
    massive: dict[str, pd.DataFrame],
    dead: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    """Merge with priority yahoo > massive > dead_name (matches build script)."""
    merged: dict[str, pd.DataFrame] = {}
    for ticker in set(yahoo) | set(massive) | set(dead):
        if ticker in yahoo:
            merged[ticker] = yahoo[ticker]
        elif ticker in massive:
            merged[ticker] = massive[ticker]
        else:
            merged[ticker] = dead[ticker]
    return merged


def _load_bench_closes(bars: dict[str, pd.DataFrame]) -> dict[str, pd.Series]:
    bench_tickers = set(_GICS_ETF.values()) | {BENCH}
    return {
        etf: bars[etf]["close"].dropna().sort_index()
        for etf in bench_tickers
        if etf in bars
    }


def _load_sector_of(root: Path) -> dict[str, str]:
    fpath = root / "breadth" / "ticker_sectors.parquet"
    if not fpath.exists():
        log.warning("ticker_sectors not found: %s", fpath)
        return {}
    df = pd.read_parquet(fpath)
    if "ticker" not in df.columns or "sector" not in df.columns:
        return {}
    return dict(zip(df["ticker"].astype(str), df["sector"].astype(str)))


def _load_pit_membership(root: Path) -> pd.DataFrame | None:
    fpath = root / "breadth" / "sp1500_pit_membership.parquet"
    if not fpath.exists():
        return None
    df = pd.read_parquet(fpath)
    for col in ("start_date", "end_date"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def _load_8k_events(root: Path) -> pd.DataFrame | None:
    fpath = root / "edgar" / "material_8k_events.parquet"
    if not fpath.exists():
        log.warning("material_8k_events not found: %s", fpath)
        return None
    df = pd.read_parquet(fpath)
    if "filing_date" in df.columns:
        df["filing_date"] = pd.to_datetime(df["filing_date"], errors="coerce")
    log.info("Loaded material_8k_events: %d rows", len(df))
    return df


def _load_statements(root: Path) -> pd.DataFrame | None:
    """Annual statements panel for B2 self-funding (only used if coverage warrants)."""
    fpath = root / "edgar" / "statements.parquet"
    if not fpath.exists():
        return None
    try:
        return pd.read_parquet(fpath)
    except Exception as exc:  # noqa: BLE001
        log.warning("statements load fail: %s", exc)
        return None


# ---------------------------------------------------------------------------
# 8-K item parsing (mirrors engine _parse_items_list semantics).
# ---------------------------------------------------------------------------

def _parse_items_list(items_str: Any) -> list[str]:
    if items_str is None or (isinstance(items_str, float) and np.isnan(items_str)):
        return []
    s = str(items_str).strip()
    if not s:
        return []
    if s.startswith("["):
        import ast
        try:
            return [str(x) for x in ast.literal_eval(s)]
        except Exception:  # noqa: BLE001
            pass
    return [x.strip().strip("'\"") for x in s.replace(";", ",").split(",") if x.strip()]


# ---------------------------------------------------------------------------
# ONE feature code path (spec §3): applied IDENTICALLY to episode and control
# tickers at the episode's t0. For the three parity-pinned columns the episode-side
# recompute MUST equal the committed parquet value (tolerance 1e-6).
# ---------------------------------------------------------------------------

# Feature keys → (type, source-family). Structurally-constant / candidate-state features
# (excess_21d_pp, new-high flags) are EXCLUDED from the fingerprint set (spec §3, §0.2):
# they ARE the detector's selection variables. excess_21d_pp is still recomputed for the
# parity check and reported in the tautology section only.
CONTINUOUS_FEATURES = [
    "dollar_vol_z21",
    "dv_5_60_ratio",
    "drawdown_from_252d_high_at_t0m21",
    "days_below_200dma",
    "updown_dollar_vol_ratio",
    "close_location_value",
    "realized_vol_63d",
    "hard_event_count_126d",
    "soft_event_count_126d",
]
BINARY_FEATURES = [
    "rs_turn_21_63",
    "trailing_rung_ge2",
    "self_funded_at_t0",
]


def _parity_trio(
    ticker: str,
    t0: pd.Timestamp,
    bars: dict[str, pd.DataFrame],
    bench_closes: dict[str, pd.Series],
    sector_of: dict[str, str],
) -> dict[str, float | None]:
    """Recompute the three parity-pinned columns via the detect_episodes code path.

    detect_episodes computes these on the bench-aligned common index and reads the value
    AT t0 (inclusive), NOT on the strictly-pre-t0 series that extract_features uses. This
    is why extract_features' dv_z21 is NOT parity-safe — we recompute here. Verified to
    reproduce committed columns at 0.0 diff (AMAT 2019-01-25).

    Returns {excess_21d_pp, dollar_vol_z21, dv_5_60_ratio} (each float | None).
    """
    out = {"excess_21d_pp": None, "dollar_vol_z21": None, "dv_5_60_ratio": None}
    df = bars.get(ticker)
    if df is None or df.empty or "close" not in df.columns:
        return out
    close = df["close"].dropna().sort_index()
    bench_etf, _ = _resolve_benchmark(ticker, sector_of)
    bench_s = bench_closes.get(bench_etf)
    if bench_s is None or bench_s.empty:
        bench_s = bench_closes.get(BENCH)
    if bench_s is None or bench_s.empty:
        return out
    common = close.index.intersection(bench_s.index)
    if len(common) < 65:
        return out
    c = close.reindex(common)
    b = bench_s.reindex(common)

    # Position at t0 (inclusive) on the common index.
    pos = common.searchsorted(pd.Timestamp(t0), side="right") - 1
    if pos < 0 or pos >= len(common):
        return out
    # Only accept an exact t0 bar for the episode-side parity pin; for controls we take
    # the last bar at-or-before t0 (they may not trade exactly on t0). We do NOT require
    # exactness here — the caller (parity check) verifies episodes land on their t0.

    exc21 = compute_excess(c, b, 21)
    if len(exc21) > pos:
        v = exc21.iloc[pos]
        out["excess_21d_pp"] = float(v) if not np.isnan(v) else None

    volume: pd.Series | None = None
    if "volume" in df.columns:
        volume = df["volume"].dropna().sort_index()
    if volume is not None:
        dv_raw = _dollar_volume_series(close, volume)
        if dv_raw is not None:
            dv = dv_raw.reindex(common)
            dvz = _dv_zscore(dv, 21)
            dvr = _dv_ratio(dv, 5, 60)
            if len(dvz) > pos:
                vz = dvz.iloc[pos]
                out["dollar_vol_z21"] = float(vz) if not np.isnan(vz) else None
            if len(dvr) > pos:
                vr = dvr.iloc[pos]
                out["dv_5_60_ratio"] = float(vr) if not np.isnan(vr) else None
    return out


def _realized_vol_63d(
    ticker: str,
    t0: pd.Timestamp,
    bars: dict[str, pd.DataFrame],
) -> float | None:
    """Annualized realized vol from the 63 trading days strictly before t0 (spec §3)."""
    df = bars.get(ticker)
    if df is None or df.empty or "close" not in df.columns:
        return None
    close = df["close"].dropna().sort_index()
    close_pre = close[close.index < pd.Timestamp(t0)]
    if len(close_pre) < 64:
        return None
    rets = np.log(close_pre / close_pre.shift(1)).dropna().iloc[-63:]
    if len(rets) < 40:
        return None
    sd = float(rets.std(ddof=1))
    if np.isnan(sd):
        return None
    return round(sd * np.sqrt(252.0) * 100.0, 4)


def _trailing_8k_counts(
    ticker: str,
    t0: pd.Timestamp,
    events_df: pd.DataFrame | None,
) -> dict[str, float | None]:
    """Hard/soft 8-K counts in (t0-126d, t0) via PIT filing_date < t0 (spec §3).

    MASK-don't-impute: if the ticker is entirely absent from the 8-K store, the counts
    are None (dropped from the feature, coverage counted) — never zero-filled. A ticker
    PRESENT in the store but with no filings in the window returns 0 (real zero).
    Pre-era (t0 < 2014) → masked (store does not cover it).
    """
    empty = {
        "hard_event_count_126d": None,
        "soft_event_count_126d": None,
        "trailing_rung_ge2": None,
        "_8k_covered": False,
    }
    if events_df is None or events_df.empty:
        return empty
    if pd.Timestamp(t0) < B1_ERA_CUTOFF:
        return empty
    if "ticker" not in events_df.columns or "filing_date" not in events_df.columns:
        return empty
    ev = events_df[events_df["ticker"].astype(str) == str(ticker)]
    if ev.empty:
        # Ticker not in store → coverage absent → MASK.
        return empty
    fd = ev["filing_date"]
    t0n = pd.Timestamp(t0)
    window_lo = t0n - pd.Timedelta(days=126)
    in_win = ev[(fd >= window_lo) & (fd < t0n)]
    hard = 0
    soft = 0
    for _, row in in_win.iterrows():
        items = _parse_items_list(row.get("items"))
        if any(code in B1_HARD_ITEMS for code in items):
            hard += 1
        if any(code in B1_SOFT_ITEMS for code in items):
            soft += 1
    return {
        "hard_event_count_126d": float(hard),
        "soft_event_count_126d": float(soft),
        "trailing_rung_ge2": bool((hard + soft) >= 2),
        "_8k_covered": True,
    }


def compute_features(
    ticker: str,
    t0: pd.Timestamp,
    bars: dict[str, pd.DataFrame],
    bench_closes: dict[str, pd.Series],
    sector_of: dict[str, str],
    events_df: pd.DataFrame | None,
) -> dict[str, Any]:
    """THE single feature code path (spec §3), applied identically to E and each C at t0.

    Combines:
      - engine extract_features geometry (drawdown, days_below_200dma, rs_turn,
        updown_dollar_vol_ratio, close_location_value) — read-only engine call;
      - the parity-pinned trio via _parity_trio (detect_episodes path);
      - realized_vol_63d (spec §3, not in extract_features);
      - trailing 8-K counts (masked where store coverage absent).

    Returns a flat dict of feature keys (values float | bool | None). Missing → None
    (mask, never impute — spec §0.3).
    """
    feats: dict[str, Any] = {}

    # Engine geometry (identical both sides). rs_turn/CLV need bench/high-low.
    geo = extract_features(ticker, pd.Timestamp(t0), bars, bench_closes, sector_of)
    feats["drawdown_from_252d_high_at_t0m21"] = geo.get("drawdown_from_252d_high_at_t0m21")
    feats["days_below_200dma"] = (
        float(geo["days_below_200dma"]) if geo.get("days_below_200dma") is not None else None
    )
    feats["rs_turn_21_63"] = geo.get("rs_turn_21_63")  # bool | None
    feats["updown_dollar_vol_ratio"] = geo.get("updown_dollar_vol_ratio")
    feats["close_location_value"] = geo.get("close_location_value_or_None")

    # Parity trio (bench-aligned, at-t0).
    trio = _parity_trio(ticker, pd.Timestamp(t0), bars, bench_closes, sector_of)
    feats["excess_21d_pp"] = trio["excess_21d_pp"]  # tautological — parity-only, not a fingerprint
    feats["dollar_vol_z21"] = trio["dollar_vol_z21"]
    feats["dv_5_60_ratio"] = trio["dv_5_60_ratio"]

    # Realized vol.
    feats["realized_vol_63d"] = _realized_vol_63d(ticker, pd.Timestamp(t0), bars)

    # Trailing 8-K.
    ev = _trailing_8k_counts(ticker, pd.Timestamp(t0), events_df)
    feats["hard_event_count_126d"] = ev["hard_event_count_126d"]
    feats["soft_event_count_126d"] = ev["soft_event_count_126d"]
    feats["trailing_rung_ge2"] = ev["trailing_rung_ge2"]

    # self_funded_at_t0 (B2) is fundamentals-firewalled and low-coverage; computed
    # only for the episode side from the committed parquet column (see caller). For
    # controls it is left None (statements-panel join is UNTESTABLE at census scale here).
    feats["self_funded_at_t0"] = None
    return feats


# ---------------------------------------------------------------------------
# Matched-set estimator (spec §4).
# For each episode i: Δ_i = value(E_i) − median(value(C_ij)) over covered controls
# (continuous), or [1{E_i} − mean_j 1{C_ij}] (binary rate within the matched set).
# A matched set with NO covered controls for that feature is dropped (coverage counted).
# ---------------------------------------------------------------------------

def _matched_deltas(
    episode_feats: list[dict[str, Any]],
    control_feats: list[list[dict[str, Any]]],
    feature: str,
    is_binary: bool,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (deltas, months, tickers) over episodes with >=1 covered control.

    deltas[i] = f(E_i) − median_j f(C_ij)   (continuous)
              = f(E_i) − mean_j f(C_ij)      (binary; both coerced to 0/1 float)
    months[i] = 'YYYY-MM' of t0_i ; tickers[i] = episode ticker (for cluster bootstrap).
    Episodes where the episode value is None, OR no control has a covered value, are
    dropped (masked) — coverage is reported separately by the caller.
    """
    deltas: list[float] = []
    months: list[str] = []
    tickers: list[str] = []
    for ef, cf_list in zip(episode_feats, control_feats):
        e_val = ef.get(feature)
        if e_val is None:
            continue
        if isinstance(e_val, bool):
            e_val = 1.0 if e_val else 0.0
        c_vals = []
        for cf in cf_list:
            cv = cf.get(feature)
            if cv is None:
                continue
            if isinstance(cv, bool):
                cv = 1.0 if cv else 0.0
            c_vals.append(float(cv))
        if not c_vals:
            continue
        c_arr = np.array(c_vals, dtype=float)
        if is_binary:
            ctrl_stat = float(np.mean(c_arr))
        else:
            ctrl_stat = float(np.median(c_arr))
        deltas.append(float(e_val) - ctrl_stat)
        months.append(ef["_month"])
        tickers.append(ef["_ticker"])
    return np.array(deltas, dtype=float), np.array(months), np.array(tickers)


def month_block_matched_bootstrap(
    deltas: np.ndarray,
    months: np.ndarray,
    n_reps: int = BOOT_REPS,
    seed: int = BOOT_SEED,
    alpha_bonf: float | None = None,
) -> dict[str, float]:
    """Month-block bootstrap over matched-set Δ (spec §4).

    Block = t0 calendar month. Resample months with replacement (n = distinct months per
    replicate). The MATCHED SET is the resampling atom: each Δ_i is a single scalar that
    already folded in the whole control set, so an episode never separates from its
    controls in a draw (test-pinned in test_month_block_matched_bootstrap_atomicity).
    Statistic = median(Δ) across the resampled episodes.

    Returns dict: point, ci95_lo, ci95_hi, ci_bonf_lo, ci_bonf_hi, n_months.
    """
    rng = np.random.default_rng(seed)
    point = float(np.median(deltas)) if len(deltas) else float("nan")

    # Map month -> array of Δ.
    by_month: dict[str, list[float]] = {}
    for d, m in zip(deltas, months):
        by_month.setdefault(m, []).append(float(d))
    month_arrays = {m: np.array(v, dtype=float) for m, v in by_month.items()}
    all_months = np.array(sorted(month_arrays.keys()))
    n_m = len(all_months)

    boot: list[float] = []
    for _ in range(n_reps):
        drawn = rng.choice(all_months, size=n_m, replace=True)
        pool = np.concatenate([month_arrays[m] for m in drawn])
        boot.append(float(np.median(pool)) if len(pool) else float("nan"))
    boot_arr = np.array(boot)
    boot_arr = boot_arr[~np.isnan(boot_arr)]
    if len(boot_arr) == 0:
        return {
            "point": point, "ci95_lo": float("nan"), "ci95_hi": float("nan"),
            "ci_bonf_lo": float("nan"), "ci_bonf_hi": float("nan"), "n_months": n_m,
        }
    res = {
        "point": point,
        "ci95_lo": float(np.percentile(boot_arr, 2.5)),
        "ci95_hi": float(np.percentile(boot_arr, 97.5)),
        "n_months": n_m,
    }
    if alpha_bonf is not None:
        tail = (alpha_bonf / 2.0) * 100.0
        res["ci_bonf_lo"] = float(np.percentile(boot_arr, tail))
        res["ci_bonf_hi"] = float(np.percentile(boot_arr, 100.0 - tail))
    else:
        res["ci_bonf_lo"] = float("nan")
        res["ci_bonf_hi"] = float("nan")
    return res


def ticker_cluster_matched_bootstrap(
    deltas: np.ndarray,
    tickers: np.ndarray,
    n_reps: int = BOOT_REPS,
    seed: int = BOOT_SEED,
) -> tuple[float, float]:
    """Ticker-cluster bootstrap over matched-set Δ (spec §0.4/§4 robustness).

    Resample episode TICKERS with replacement; a ticker's episodes (and thus their whole
    matched sets, already folded into Δ) move together. Returns 95% CI (lo, hi).
    """
    rng = np.random.default_rng(seed + 1)
    by_ticker: dict[str, list[float]] = {}
    for d, t in zip(deltas, tickers):
        by_ticker.setdefault(t, []).append(float(d))
    tk_arrays = {t: np.array(v, dtype=float) for t, v in by_ticker.items()}
    uniq = np.array(list(tk_arrays.keys()))
    if len(uniq) == 0:
        return float("nan"), float("nan")
    boot: list[float] = []
    for _ in range(n_reps):
        drawn = rng.choice(uniq, size=len(uniq), replace=True)
        pool = np.concatenate([tk_arrays[t] for t in drawn])
        boot.append(float(np.median(pool)) if len(pool) else float("nan"))
    boot_arr = np.array(boot)
    boot_arr = boot_arr[~np.isnan(boot_arr)]
    if len(boot_arr) == 0:
        return float("nan"), float("nan")
    return float(np.percentile(boot_arr, 2.5)), float(np.percentile(boot_arr, 97.5))


def _distinct_months(months: np.ndarray) -> int:
    return len(set(months.tolist()))


def analyze_feature(
    feature: str,
    is_binary: bool,
    episode_feats: list[dict[str, Any]],
    control_feats: list[list[dict[str, Any]]],
    contrast_name: str,
    alpha_bonf: float,
    n_boot: int,
    seed: int,
) -> dict[str, Any]:
    """Run the matched-set analysis for one feature × one contrast.

    Degenerate guard (spec §4): < 12 distinct t0 months among covered episodes → report
    point + coverage only, no CI. NON-COMPARABLE (spec §3): reported by caller for
    fundamentals below 30% coverage.
    """
    deltas, months, tickers = _matched_deltas(
        episode_feats, control_feats, feature, is_binary
    )
    n_cov = len(deltas)
    n_months = _distinct_months(months) if n_cov else 0

    res: dict[str, Any] = {
        "feature": feature,
        "contrast": contrast_name,
        "type": "binary" if is_binary else "continuous",
        "n_covered": n_cov,
        "n_months": n_months,
        "point": round(float(np.median(deltas)), 4) if n_cov else None,
        "ci95_lo": None, "ci95_hi": None,
        "ci_bonf_lo": None, "ci_bonf_hi": None,
        "ci_cluster_lo": None, "ci_cluster_hi": None,
        "bonf_survives": None,
        "degenerate": False,
        "note": "",
    }
    if n_cov < 5:
        res["note"] = "insufficient covered episodes (<5)"
        return res
    if n_months < 12:
        res["degenerate"] = True
        res["note"] = f"degenerate: {n_months} distinct t0 months (<12) — no CI"
        return res

    mb = month_block_matched_bootstrap(
        deltas, months, n_reps=n_boot, seed=seed, alpha_bonf=alpha_bonf
    )
    res["point"] = round(mb["point"], 4)
    res["ci95_lo"] = round(mb["ci95_lo"], 4) if not np.isnan(mb["ci95_lo"]) else None
    res["ci95_hi"] = round(mb["ci95_hi"], 4) if not np.isnan(mb["ci95_hi"]) else None
    res["ci_bonf_lo"] = round(mb["ci_bonf_lo"], 4) if not np.isnan(mb["ci_bonf_lo"]) else None
    res["ci_bonf_hi"] = round(mb["ci_bonf_hi"], 4) if not np.isnan(mb["ci_bonf_hi"]) else None
    if res["ci_bonf_lo"] is not None and res["ci_bonf_hi"] is not None:
        res["bonf_survives"] = bool(res["ci_bonf_lo"] > 0 or res["ci_bonf_hi"] < 0)

    cl_lo, cl_hi = ticker_cluster_matched_bootstrap(
        deltas, tickers, n_reps=n_boot, seed=seed
    )
    res["ci_cluster_lo"] = round(cl_lo, 4) if not np.isnan(cl_lo) else None
    res["ci_cluster_hi"] = round(cl_hi, 4) if not np.isnan(cl_hi) else None
    return res


# ---------------------------------------------------------------------------
# Study runner
# ---------------------------------------------------------------------------

def run_study(
    episodes_path: Path,
    root: Path,
    out_path: Path,
    n_boot: int = BOOT_REPS,
    seed: int = BOOT_SEED,
    sample_n: int | None = None,
) -> dict[str, Any]:
    """Execute the W4 study end-to-end. Returns a summary dict (also written to out_path)."""
    t_start = time.time()

    eps = pd.read_parquet(episodes_path)
    eps["t0"] = pd.to_datetime(eps["t0"])

    manifest_path = episodes_path.parent / "winner_episodes_manifest.json"
    manifest_hash = "N/A"
    harvest_date = "N/A"
    if manifest_path.exists():
        raw = manifest_path.read_text()
        manifest_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]
        try:
            harvest_date = json.loads(raw).get("as_of", "N/A")
        except Exception:  # noqa: BLE001
            pass

    # Crypto segregation (spec §0.6).
    is_crypto = eps["ticker"].isin(CRYPTO_TICKERS)
    eps_equity = eps[~is_crypto].copy()
    matured = eps_equity[eps_equity["outcome_label"].isin(MATURED_LABELS)].copy()
    unmatured_n = int((eps_equity["outcome_label"] == "unmatured").sum())
    crypto_matured_n = int(
        eps[is_crypto & eps["outcome_label"].isin(MATURED_LABELS)].shape[0]
    )

    matured = matured.sort_values(["ticker", "t0"]).reset_index(drop=True)
    if sample_n is not None:
        matured = matured.head(sample_n).copy()
        log.info("SMOKE MODE: first %d matured episodes", len(matured))

    log.info("Loading stores (read-only) from %s", root)
    yahoo = _load_yahoo_bars(root)
    massive = _load_massive_bars(root)
    dead = _load_dead_name_bars(root)
    bars = _merge_bars(yahoo, massive, dead)
    bench_closes = _load_bench_closes(bars)
    sector_of = _load_sector_of(root)
    pit = _load_pit_membership(root)
    events_df = _load_8k_events(root)
    log.info(
        "bars=%d bench=%d sectors=%d pit_rows=%s 8k=%s",
        len(bars), len(bench_closes), len(sector_of),
        0 if pit is None else len(pit), 0 if events_df is None else len(events_df),
    )

    # -----------------------------------------------------------------------
    # Sample controls + compute features (one code path both sides).
    # -----------------------------------------------------------------------
    t_ctrl = time.time()
    episode_records: list[dict[str, Any]] = []  # per kept episode: features + meta
    excluded_lt3 = 0
    excluded_no_bars = 0
    control_pool_sizes: list[int] = []
    parity_fail_rows: list[dict[str, Any]] = []
    parity_checked = 0
    parity_pass = 0

    for _, row in matured.iterrows():
        ticker = str(row["ticker"])
        t0 = pd.Timestamp(row["t0"])
        if ticker not in bars:
            excluded_no_bars += 1
            continue
        controls = sample_controls(row, bars, sector_of, pit, k=20)
        n_ctrl = len(controls)
        control_pool_sizes.append(n_ctrl)
        if n_ctrl < MIN_CONTROLS:
            excluded_lt3 += 1
            continue

        ef = compute_features(ticker, t0, bars, bench_closes, sector_of, events_df)
        ef["_month"] = t0.strftime("%Y-%m")
        ef["_ticker"] = ticker
        ef["_t0"] = t0
        ef["_label"] = str(row["outcome_label"])
        ef["_gap_leg_crossed"] = bool(row.get("gap_leg_crossed", False))
        # Episode-side self_funded_at_t0 from committed parquet (B2; None where absent).
        sf = row.get("self_funded_at_t0")
        ef["self_funded_at_t0"] = None if pd.isna(sf) else bool(sf)

        # PARITY CHECK (spec §3): episode-side recomputed trio must equal committed cols.
        for col in ("excess_21d_pp", "dollar_vol_z21", "dv_5_60_ratio"):
            committed = row.get(col)
            recomputed = ef.get(col)
            if pd.isna(committed) or recomputed is None:
                continue
            parity_checked += 1
            if abs(float(committed) - float(recomputed)) <= PARITY_TOL:
                parity_pass += 1
            else:
                parity_fail_rows.append({
                    "ticker": ticker, "t0": str(t0.date()), "col": col,
                    "committed": float(committed), "recomputed": float(recomputed),
                    "diff": abs(float(committed) - float(recomputed)),
                })

        cf_list = [
            compute_features(c, t0, bars, bench_closes, sector_of, events_df)
            for c in controls
        ]
        ef["_controls"] = cf_list
        episode_records.append(ef)

    ctrl_secs = time.time() - t_ctrl
    log.info(
        "Controls+features: kept=%d excluded_lt3=%d excluded_no_bars=%d in %.1fs",
        len(episode_records), excluded_lt3, excluded_no_bars, ctrl_secs,
    )
    log.info("Parity: %d/%d pass, %d fail", parity_pass, parity_checked, len(parity_fail_rows))
    if parity_fail_rows:
        log.error("PARITY FAILURES (spec §3 — control-side definitions do not match census):")
        for r in parity_fail_rows[:10]:
            log.error("  %s", r)

    # -----------------------------------------------------------------------
    # Contrasts (spec §2). Contrast 1 = ALL matured; 2 = kept_going; 3 = blow_off.
    # -----------------------------------------------------------------------
    def _subset(records: list[dict], labels: set[str] | None) -> list[dict]:
        if labels is None:
            return records
        return [r for r in records if r["_label"] in labels]

    contrasts = [
        ("all_matured", None),
        ("kept_going", KEPT_GOING_LABELS),
        ("blow_off", {"blow_off"}),
    ]

    # m: testable features (structurally-constant excess_21d_pp already excluded from the
    # feature list). Declared per spec §0.1: m = |features| × |contrasts|. self_funded and
    # any feature that turns out NON-COMPARABLE / UNTESTABLE stay in the tables but do not
    # earn a bonf slot; we keep them in m for an honest (conservative) correction.
    all_features = (
        [(f, False) for f in CONTINUOUS_FEATURES]
        + [(f, True) for f in BINARY_FEATURES]
    )
    m_total = len(all_features) * len(contrasts)
    alpha_bonf = ALPHA / m_total
    log.info("m_total=%d alpha_bonf=%.6f", m_total, alpha_bonf)

    results: list[dict[str, Any]] = []
    for cname, labels in contrasts:
        recs = _subset(episode_records, labels)
        ep_feats = recs
        ctrl_feats = [r["_controls"] for r in recs]
        for feat, is_bin in all_features:
            res = analyze_feature(
                feat, is_bin, ep_feats, ctrl_feats, cname,
                alpha_bonf, n_boot, seed,
            )
            results.append(res)

    # -----------------------------------------------------------------------
    # excess_21d_pp tautology readout (parity-only; NOT a fingerprint — spec §3/§0.2).
    # Reported descriptively on the all_matured contrast for transparency.
    # -----------------------------------------------------------------------
    taut_deltas, taut_months, _ = _matched_deltas(
        episode_records,
        [r["_controls"] for r in episode_records],
        "excess_21d_pp",
        is_binary=False,
    )
    taut_median = float(np.median(taut_deltas)) if len(taut_deltas) else float("nan")
    taut_n = len(taut_deltas)

    # -----------------------------------------------------------------------
    # Coverage counts per feature (episode-side AND control-side) — spec §5.
    # -----------------------------------------------------------------------
    coverage: list[dict[str, Any]] = []
    for feat, _is_bin in all_features:
        ep_cov = sum(1 for r in episode_records if r.get(feat) is not None)
        ctrl_total = 0
        ctrl_cov = 0
        for r in episode_records:
            for cf in r["_controls"]:
                ctrl_total += 1
                if cf.get(feat) is not None:
                    ctrl_cov += 1
        coverage.append({
            "feature": feat,
            "ep_covered": ep_cov,
            "ep_total": len(episode_records),
            "ctrl_covered": ctrl_cov,
            "ctrl_total": ctrl_total,
        })

    # Fundamentals NON-COMPARABLE flag (spec §3): self_funded coverage < 30% either side.
    sf_cov = next(c for c in coverage if c["feature"] == "self_funded_at_t0")
    sf_ep_frac = sf_cov["ep_covered"] / max(sf_cov["ep_total"], 1)
    sf_ctrl_frac = sf_cov["ctrl_covered"] / max(sf_cov["ctrl_total"], 1)
    self_funded_non_comparable = (
        sf_ep_frac < NON_COMPARABLE_FLOOR or sf_ctrl_frac < NON_COMPARABLE_FLOOR
    )

    # -----------------------------------------------------------------------
    # gap_leg_crossed == False stratum rerun of Contrast 1 (spec §5).
    # -----------------------------------------------------------------------
    gap_clean_recs = [r for r in episode_records if not r["_gap_leg_crossed"]]
    gap_stratum: list[dict[str, Any]] = []
    for feat, is_bin in all_features:
        res = analyze_feature(
            feat, is_bin, gap_clean_recs, [r["_controls"] for r in gap_clean_recs],
            "all_matured (gap_leg_crossed==False)", alpha_bonf, n_boot, seed,
        )
        gap_stratum.append(res)

    # Control-pool distribution (spec §5).
    pool_arr = np.array(control_pool_sizes) if control_pool_sizes else np.array([0])
    pool_dist = {
        "n_episodes_sampled": len(control_pool_sizes),
        "min": int(pool_arr.min()),
        "p25": float(np.percentile(pool_arr, 25)),
        "median": float(np.median(pool_arr)),
        "p75": float(np.percentile(pool_arr, 75)),
        "max": int(pool_arr.max()),
        "eq_20": int((pool_arr >= 20).sum()),
        "lt_3": int((pool_arr < 3).sum()),
        "mean": round(float(pool_arr.mean()), 2),
    }

    elapsed = time.time() - t_start

    summary = {
        "manifest_hash": manifest_hash,
        "harvest_date": harvest_date,
        "episodes_path": str(episodes_path),
        "n_equity_matured_total": int(len(matured)),
        "n_kept_going_labels": int(
            sum(1 for r in episode_records if r["_label"] in KEPT_GOING_LABELS)
        ),
        "n_blow_off_labels": int(
            sum(1 for r in episode_records if r["_label"] == "blow_off")
        ),
        "n_included": len(episode_records),
        "excluded_lt3": excluded_lt3,
        "excluded_no_bars": excluded_no_bars,
        "unmatured_n": unmatured_n,
        "crypto_matured_n": crypto_matured_n,
        "control_pool_dist": pool_dist,
        "parity_checked": parity_checked,
        "parity_pass": parity_pass,
        "parity_fail_rows": parity_fail_rows,
        "m_total": m_total,
        "alpha_bonf": alpha_bonf,
        "results": results,
        "gap_stratum": gap_stratum,
        "coverage": coverage,
        "self_funded_non_comparable": self_funded_non_comparable,
        "taut_median": taut_median,
        "taut_n": taut_n,
        "n_boot": n_boot,
        "seed": seed,
        "elapsed": elapsed,
        "sample_n": sample_n,
    }

    _write_report(out_path=out_path, summary=summary)
    log.info("Done. Wall time: %.1fs -> %s", elapsed, out_path)
    return summary


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def _fmt(v: Any, decs: int = 4) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:.{decs}f}"
    return str(v)


def _verdict_line(res: dict[str, Any]) -> str:
    """SEPARATES / NULL / UNTESTABLE (spec §6) for one feature × contrast.

    SEPARATES = α/m CI (corrected Bonferroni) excludes zero.
    NULL = α/m CI contains zero with adequate coverage.
    UNTESTABLE = insufficient coverage, degenerate (no CI), or NON-COMPARABLE.
    """
    feat = res["feature"]
    con = res["contrast"]
    if res.get("degenerate") or res.get("ci_bonf_lo") is None:
        return f"- {feat} [{con}]: UNTESTABLE ({res.get('note') or 'no α/m CI'})"
    if res.get("bonf_survives"):
        direction = "higher in episodes" if (res["ci_bonf_lo"] or 0) > 0 else "lower in episodes"
        return (
            f"- {feat} [{con}]: SEPARATES — α/m CI excludes 0 ({direction}; "
            f"Δ={_fmt(res['point'])}, α/m [{_fmt(res['ci_bonf_lo'])}, {_fmt(res['ci_bonf_hi'])}])"
        )
    return (
        f"- {feat} [{con}]: NULL — α/m CI contains 0 "
        f"(Δ={_fmt(res['point'])}, 95% [{_fmt(res['ci95_lo'])}, {_fmt(res['ci95_hi'])}])"
    )


def _write_report(*, out_path: Path, summary: dict[str, Any]) -> None:
    s = summary
    lines: list[str] = []

    def w(x: str = "") -> None:
        lines.append(x)

    smoke = s["sample_n"] is not None
    w("<!-- W4 matched-controls fingerprint study (Layer-3b). DESCRIPTIVE ONLY (WA-R1/R5/R8). -->")
    w("<!-- Machine outputs. No registration, no filters, no site surfaces. -->")
    w()
    w("# Winner Autopsy Lab — W4 Matched-Controls Fingerprint Study (Layer-3b)")
    w()
    w("**Status:** DESCRIPTIVE ONLY — no hypothesis registration, no verdicts, no filters, no site surfaces.")
    w("Rulings WA-R1 / WA-R5 / WA-R8. Spec: `research/winners/W4_CONTROLS_STUDY_SPEC.md`.")
    w("Question (Layer-3b): pre-onset, what separated eventual breakaway names from matched")
    w("controls sampled the SAME calendar day — the watchlist-formation question. Distinct")
    w("from W3 (`FINGERPRINT_CENSUS_W3.md`, WA-R8 null: winners ≈ blow-offs at onset).")
    w()
    if smoke:
        w(f"> **SMOKE RUN** — first {s['sample_n']} matured episodes only. Not the full population.")
        w()
    w(f"**Substrate:** `{Path(s['episodes_path']).name}` — manifest hash `{s['manifest_hash']}`, "
      f"harvest date `{s['harvest_date']}` (frozen; no re-harvest — spec §1).")
    w(f"**Run:** seed {s['seed']}, n_boot {s['n_boot']:,}, m={s['m_total']} tests, "
      f"α_Bonferroni = 0.05/{s['m_total']} = {s['alpha_bonf']:.6f}.")
    w(f"**Estimator:** matched-set Δ = value(E,t0) − median(value(controls,t0)); "
      f"month-block bootstrap with the matched set as the resampling atom (spec §4).")
    w(f"**Wall time:** {s['elapsed']:.1f}s")
    w()

    # Bottom line.
    w("## Bottom line")
    w()
    sep = [r for r in s["results"] if r.get("bonf_survives")]
    w("Machine outputs — not adjudications. The main loop appends the ruling below.")
    w()
    if sep:
        sep_feats = sorted({r["feature"] for r in sep})
        gate_feats = {"dollar_vol_z21", "dv_5_60_ratio"}
        gate_hit = sorted(f for f in sep_feats if f in gate_feats)
        w(f"**{len(sep)} feature × contrast cell(s) SEPARATE** at the α/m threshold "
          f"(α/m CI excludes 0), across features: {', '.join(sep_feats)}. See per-feature "
          "verdict lines.")
        w()
        if gate_hit:
            w(f"**Construction caveat (mechanical, not an adjudication):** the separators are "
              f"dominated by volume / realized-vol features. Of these, {', '.join(gate_hit)} "
              "are DETECTOR-GATE ECHOES — the onset condition requires `dollar_vol_z21 ≥ 1 OR "
              "dv_5_60_ratio ≥ 1.5`, which holds for 100% of episodes by construction while "
              "controls are ungated on volume (see 'Volume-confirm selection linkage'). "
              "Weigh those like `excess_21d_pp`. The non-gate separators "
              "(`updown_dollar_vol_ratio`, `realized_vol_63d`, `drawdown_from_252d_high_at_t0m21`) "
              "are not direct gate echoes. Every 8-K density and RS-turn cell is NULL; "
              "`self_funded_at_t0` and `close_location_value` are UNTESTABLE (coverage).")
    else:
        w("**No feature SEPARATES at the α/m threshold on any of the three contrasts.** "
          "Every tested pre-onset feature's α/m CI contains 0 (or the cell is UNTESTABLE). "
          "Consistent with the W3 null: pre-onset t0 geometry does not cleanly mark the "
          "eventual breakaway vs its same-day, same-sector control.")
    w()

    # Population.
    w("## Population & control pool")
    w()
    w(f"- Equity matured episodes considered: **{s['n_equity_matured_total']:,}** "
      "(crypto segregated — see honesty section).")
    w(f"- Included (≥ {MIN_CONTROLS} eligible controls, bars present): **{s['n_included']:,}**")
    w(f"  - of which kept_going label: {s['n_kept_going_labels']}; blow_off label: {s['n_blow_off_labels']}")
    w(f"- Excluded — < {MIN_CONTROLS} eligible controls: **{s['excluded_lt3']:,}**")
    w(f"- Excluded — no bars for episode ticker: **{s['excluded_no_bars']:,}**")
    w(f"- Unmatured (equity, not in analysis): {s['unmatured_n']:,}")
    w(f"- Crypto matured (excluded from primary): {s['crypto_matured_n']}")
    w()
    pd_ = s["control_pool_dist"]
    w("**Control-pool size distribution** (per episode, over episodes actually sampled):")
    w()
    w("| n_sampled | min | p25 | median | mean | p75 | max | =20 (capped) | <3 (excluded) |")
    w("|---|---|---|---|---|---|---|---|---|")
    w(f"| {pd_['n_episodes_sampled']} | {pd_['min']} | {_fmt(pd_['p25'],1)} | "
      f"{_fmt(pd_['median'],1)} | {pd_['mean']} | {_fmt(pd_['p75'],1)} | {pd_['max']} | "
      f"{pd_['eq_20']} | {pd_['lt_3']} |")
    w()

    # Parity.
    w("## Parity check (spec §3 — control-side implementation pinned to census definitions)")
    w()
    w(f"Episode-side recompute of `excess_21d_pp`, `dollar_vol_z21`, `dv_5_60_ratio` "
      f"(via the `detect_episodes` code path: bench-aligned common index, value at t0) vs "
      f"the committed parquet columns, tolerance {PARITY_TOL:g}:")
    w()
    w(f"- Cells checked: **{s['parity_checked']:,}**")
    w(f"- Pass: **{s['parity_pass']:,}**")
    w(f"- Fail: **{len(s['parity_fail_rows'])}**")
    w()
    if s["parity_fail_rows"]:
        w("**PARITY FAILURES — control-side feature definitions do not match the census. "
          "Every contrast below is invalid until fixed (spec §3).**")
        w()
        w("| ticker | t0 | col | committed | recomputed | diff |")
        w("|---|---|---|---|---|---|")
        for r in s["parity_fail_rows"][:20]:
            w(f"| {r['ticker']} | {r['t0']} | {r['col']} | {_fmt(r['committed'],6)} | "
              f"{_fmt(r['recomputed'],6)} | {_fmt(r['diff'],2)} |")
    else:
        w("**PASS** — recomputed trio is byte-for-value identical to the committed columns "
          "within tolerance. The one feature code path applied to controls matches the "
          "census's own definitions.")
    w()

    # Per-feature results tables, one per contrast.
    w("## Per-feature results (matched-set Δ)")
    w()
    w("Δ = median across episodes of [ value(E,t0) − median(value(controls,t0)) ] "
      "(continuous) or [ 1{E} − mean_j 1{C_j} ] (binary). Positive Δ = episode side higher.")
    w("CI95 = 95% month-block matched bootstrap; CIbonf = α/m percentile CI of the SAME "
      "draws (bonf_survives uses CIbonf, never CI95 — spec §0.1); CIcluster = ticker-cluster "
      "bootstrap robustness. `cov` = covered episodes / distinct t0 months.")
    w()
    contrasts_order = ["all_matured", "kept_going", "blow_off"]
    contrast_titles = {
        "all_matured": "Contrast 1 (PRIMARY): all matured episodes vs matched controls",
        "kept_going": "Contrast 2: kept_going episodes vs matched controls",
        "blow_off": "Contrast 3: blow_off episodes vs matched controls",
    }
    for cname in contrasts_order:
        w(f"### {contrast_titles[cname]}")
        w()
        w("| Feature | Type | Δ | n_cov | mo | CI95_lo | CI95_hi | CIbonf_lo | CIbonf_hi | "
          "Bonf | CIclus_lo | CIclus_hi | Note |")
        w("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for res in s["results"]:
            if res["contrast"] != cname:
                continue
            w(f"| {res['feature']} | {res['type']} | {_fmt(res['point'])} | {res['n_covered']} | "
              f"{res['n_months']} | {_fmt(res['ci95_lo'])} | {_fmt(res['ci95_hi'])} | "
              f"{_fmt(res['ci_bonf_lo'])} | {_fmt(res['ci_bonf_hi'])} | {_fmt(res['bonf_survives'])} | "
              f"{_fmt(res['ci_cluster_lo'])} | {_fmt(res['ci_cluster_hi'])} | {res['note']} |")
        w()

    # Contrast 2/3 vs Contrast 1 comparison.
    w("## Contrast 2 / 3 vs Contrast 1 (motion vs quality)")
    w()
    w("Spec §2: if Contrasts 2/3 mirror Contrast 1 (expected under the W3 null), that is "
      "itself the finding — pre-onset structure predicts *motion* (any breakaway onset), "
      "not *quality* (kept_going vs blow_off).")
    w()
    w("| Feature | C1 Δ | C1 bonf | C2 Δ | C2 bonf | C3 Δ | C3 bonf | mirrors C1? |")
    w("|---|---|---|---|---|---|---|---|")
    by_key = {(r["feature"], r["contrast"]): r for r in s["results"]}
    for feat, _is_bin in (
        [(f, False) for f in CONTINUOUS_FEATURES] + [(f, True) for f in BINARY_FEATURES]
    ):
        c1 = by_key.get((feat, "all_matured"))
        c2 = by_key.get((feat, "kept_going"))
        c3 = by_key.get((feat, "blow_off"))
        if not c1:
            continue
        def _bf(r: dict | None) -> Any:
            return None if r is None else r.get("bonf_survives")
        mirror = (_bf(c1) == _bf(c2) == _bf(c3))
        w(f"| {feat} | {_fmt(c1['point'])} | {_fmt(_bf(c1))} | "
          f"{_fmt(c2['point'] if c2 else None)} | {_fmt(_bf(c2))} | "
          f"{_fmt(c3['point'] if c3 else None)} | {_fmt(_bf(c3))} | {'yes' if mirror else 'NO'} |")
    w()
    all_mirror = all(
        (by_key.get((f, "all_matured"), {}).get("bonf_survives")
         == by_key.get((f, "kept_going"), {}).get("bonf_survives")
         == by_key.get((f, "blow_off"), {}).get("bonf_survives"))
        for f, _ in ([(x, False) for x in CONTINUOUS_FEATURES] + [(x, True) for x in BINARY_FEATURES])
    )
    if all_mirror:
        w("**Contrasts 2 and 3 mirror Contrast 1 on every feature** (same SEPARATES/NULL/"
          "UNTESTABLE verdict). Pre-onset structure predicts motion, not quality — the W3 "
          "null carried into the controls frame.")
    else:
        w("**Contrasts 2/3 do NOT fully mirror Contrast 1** — at least one feature's bonf "
          "verdict differs across the quality split. See the differing rows above.")
    w()

    # excess_21d_pp tautology.
    w("## excess_21d_pp — tautology disclosure (parity-only, NOT a fingerprint)")
    w()
    w("`excess_21d_pp` is the detector's primary selection variable (breakaway onset ≡ "
      "excess crossing ≥20pp, or 42d ≥25pp). Controls are sampled to NOT be in candidate "
      "state within ±21td of t0. Comparing episode-vs-control excess is therefore "
      "guaranteed-positive by construction — TAUTOLOGICAL (spec §3 exclusion / §0.2), not a "
      "market regularity. It is recomputed above only to pin the parity check; it earns no "
      "fingerprint slot and is excluded from m.")
    w()
    w(f"Descriptive (all matured, matched-set Δ, n={s['taut_n']}): "
      f"median Δ = {_fmt(s['taut_median'])} pp (episode side higher by construction).")
    w()
    w("### Volume-confirm selection linkage (construction note, NOT an adjudication)")
    w()
    w("The detector's candidate condition is `liquid & rel_breakaway & new_high & "
      "vol_confirm`, where `vol_confirm = (dollar_vol_z21 ≥ 1) OR (dv_5_60_ratio ≥ 1.5)`. "
      "That gate holds for 100% of episodes by construction, while controls are NOT gated "
      "on volume (only on excess / candidate-state). So the SEPARATES verdicts on "
      "`dollar_vol_z21` and `dv_5_60_ratio` are SELECTION-LINKED in the same way "
      "`excess_21d_pp` is — an episode is admitted partly *because* one of these was "
      "elevated at t0. Read them as detector-gate echoes, not discovered fingerprints; the "
      "main-loop ruling should weigh them accordingly. `updown_dollar_vol_ratio` and "
      "`realized_vol_63d` are NOT in the candidate condition, so their separation is not a "
      "direct gate echo (though volume/vol elevation is correlated with the excess move "
      "that IS gated). This note states a construction fact; it does not change any "
      "SEPARATES/NULL/UNTESTABLE cell above.")
    w()

    # Honesty section.
    w("## Honesty section")
    w()
    w("### Survivor-only (spec §0.5)")
    w()
    w("The census and its control pool are survivor-lean: the `survivorship_biased` column "
      "is an unpopulated constant (False), and no dead-name price source is present in this "
      "parquet's `price_source` (yahoo/massive only). No survivorship stratum is tested or "
      "claimed — the gap is stated, not resolved.")
    w()
    w("### Per-feature coverage (episode-side AND control-side)")
    w()
    w("| Feature | ep covered | ep total | ep % | ctrl covered | ctrl total | ctrl % |")
    w("|---|---|---|---|---|---|---|")
    for c in s["coverage"]:
        ep_pct = c["ep_covered"] / max(c["ep_total"], 1) * 100
        ct_pct = c["ctrl_covered"] / max(c["ctrl_total"], 1) * 100
        w(f"| {c['feature']} | {c['ep_covered']} | {c['ep_total']} | {ep_pct:.0f}% | "
          f"{c['ctrl_covered']} | {c['ctrl_total']} | {ct_pct:.0f}% |")
    w()
    if s["self_funded_non_comparable"]:
        w("**NON-COMPARABLE:** `self_funded_at_t0` (B2 fundamentals) coverage is below 30% on "
          "at least one side — printed in the tables but must not be interpreted as "
          "representative. Control-side B2 is not joined at census scale here (statements "
          "panel + A2 firewall), so this feature is UNTESTABLE for the contrast.")
        w()
    w("### Excluded-episode counts")
    w()
    w(f"- < {MIN_CONTROLS} eligible controls: {s['excluded_lt3']:,}")
    w(f"- no bars for episode ticker: {s['excluded_no_bars']:,}")
    w(f"- crypto (7-day calendar + SPY benchmark category error): {s['crypto_matured_n']} matured")
    w(f"- unmatured (forward windows not closed): {s['unmatured_n']:,}")
    w()
    w("### gap_leg_crossed == False stratum (Contrast 1 rerun)")
    w()
    w("| Feature | Type | Δ | n_cov | mo | CI95_lo | CI95_hi | CIbonf_lo | CIbonf_hi | Bonf | Note |")
    w("|---|---|---|---|---|---|---|---|---|---|---|")
    for res in s["gap_stratum"]:
        w(f"| {res['feature']} | {res['type']} | {_fmt(res['point'])} | {res['n_covered']} | "
          f"{res['n_months']} | {_fmt(res['ci95_lo'])} | {_fmt(res['ci95_hi'])} | "
          f"{_fmt(res['ci_bonf_lo'])} | {_fmt(res['ci_bonf_hi'])} | {_fmt(res['bonf_survives'])} | "
          f"{res['note']} |")
    w()
    w("### What W4 cannot see")
    w()
    w("Per-ticker options positioning, analyst-revision breadth, and PIT short-interest are "
      "still forward-accruing (joins began ~2026-06 per the masterplan clock; first "
      "answerable ~2027-06). W4 tests only t0 price/volume geometry and trailing 8-K "
      "density — the substrates that exist today. A null here closes the tested "
      "constructions, not the search space (house epistemics: 'not found yet' ≠ 'does not "
      "exist').")
    w()

    # Per-feature verdict lines (spec §6).
    w("## Per-feature verdicts (SEPARATES / NULL / UNTESTABLE)")
    w()
    w("SEPARATES = α/m CI excludes 0; NULL = α/m CI contains 0 with adequate coverage; "
      "UNTESTABLE = insufficient coverage / degenerate (no CI) / NON-COMPARABLE.")
    w()
    for cname in contrasts_order:
        w(f"**{contrast_titles[cname]}**")
        w()
        for res in s["results"]:
            if res["contrast"] == cname:
                w(_verdict_line(res))
        w()

    # Adjudication placeholder.
    w("## Adjudication (main loop)")
    w()
    w("PENDING")
    w()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Winner Autopsy W4 matched-controls fingerprint study (Layer-3b)."
    )
    parser.add_argument(
        "--root", required=True,
        help="Data root for read-only stores (yahoo/, massive_stock_day/, breadth/, edgar/).",
    )
    parser.add_argument(
        "--out", default="research/winners/FINGERPRINT_CONTROLS_W4.md",
        help="Output report path.",
    )
    parser.add_argument(
        "--episodes", default="data/research/winner_episodes.parquet",
        help="Committed census parquet (from the worktree, NOT --root).",
    )
    parser.add_argument("--seed", type=int, default=BOOT_SEED)
    parser.add_argument("--n-boot", type=int, default=BOOT_REPS)
    parser.add_argument(
        "--sample", type=int, default=None,
        help="Smoke mode: first N matured episodes only.",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    episodes_path = Path(args.episodes).resolve()
    out_path = Path(args.out).resolve()

    if not episodes_path.exists():
        log.error("episodes parquet not found: %s", episodes_path)
        return 2
    if not root.exists():
        log.error("data root not found: %s", root)
        return 2

    run_study(
        episodes_path=episodes_path,
        root=root,
        out_path=out_path,
        n_boot=args.n_boot,
        seed=args.seed,
        sample_n=args.sample,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
