#!/usr/bin/env python3
"""onset_calibration_v1.py — CN LIMIT-MOVE ALPHA, Wave 1 / L3: the calibrated onset model.

WHAT THIS IS
    A CALIBRATED PROBABILITY model for the ONSET question — P(this name closes at the
    limit on its next usable bar), scored from information available at the prior close —
    plus the program's forward-ledger seed.  Display/audit tier.  Nothing here promotes,
    ranks for size, gates, or reaches a live surface.

    The pre-registered success criterion for the program is NOT "a feature shows lift".
    It is a model whose predicted probabilities are (a) CALIBRATED — when it says 6% it
    happens ~6% of the time — and (b) BETTER than the base-rate ladder every 打板 desk
    already has for free.  The 连板 ladder is a brutally strong free benchmark (v0:
    a first board multiplies next-bar odds 13x on the main board before any feature is
    computed), so "beats the ladder" is a real bar, not a formality.  This file answers
    that question once, on a frozen holdout, and prints the answer whichever way it goes.

THREE MODELS, ONE EVALUATION PASS
    B0  LADDER-ONLY BENCHMARK — P-hat = the fit-window base rate for the row's 连板 bucket
        N in {0, 1, 2, 3+}.  Calibrated by construction; carries no feature information.
        THE SKILL TARGET.
    B1  LOGISTIC — the six features v0 found sign-stable on holdout, winsorised and
        standardised on the fit window ONLY, plus N dummies.  Fitted on the fit CORE
        (first 85% of fit dates), isotonic-calibrated on the fit CALIBRATION slice (last
        15% of fit dates — out-of-sample for the logistic, and never the holdout), frozen,
        evaluated once.
    B2  EMPIRICAL BUCKET MODEL — fit-window rate in (f3 quintile x f6 quintile x N) cells,
        shrunk toward the N-marginal; THIN cells fall back to the N-marginal entirely.
        The non-parametric sanity check on B1: if B1 only matches a hand-built lookup
        table, the parametric machinery bought nothing.
    P1/P2 PARSIMONY PROBES — logistic on f3 alone, and f3 + N dummies.  How much of B1's
        skill survives the other five features being deleted?

WHY THESE SIX FEATURES AND NOT EIGHT
    The set is v0's pre-registered eight, minus the two v0's own holdout retired:
    f2_turnover_ratio is a printed NULL (no CN store carries per-date shares outstanding)
    and f5_near_limit_prev was printed UNSTABLE (per-name median lift 0.00, sign flip on
    STAR, total collapse in the ChiNext band-era control).  Carrying a feature v0 already
    retired into a probability model would launder the exact false discovery v0's
    pre-registration caught.  NO NEW FEATURE IS INTRODUCED HERE.  The one addition is the
    连板 state N as a model input, which is not a new feature — it is the benchmark B0
    itself, and B1 must beat B0 while containing it.

BINDING CONVENTIONS (inherited from v0, not re-decided here)
    * Basis is data/china_stocks_raw (nominal/unadjusted).  The adjusted twin
      data/china_stocks would fabricate limit misses.
    * Board + width from engine.china_microstructure (imported, era-aware).
    * PRIMARY limit-up close = close >= round(prev_close*(1+w), 2) * (1 - 0.002).  v0
      adjudicated this against the strict test with measured evidence (43.4% of the
      marginal events moved strictly MORE than the full band — impossible for a real
      limit-up, therefore feed price noise) and against the independent china_zt_pool
      vendor scrape (99.8% 连板 agreement vs 91.1% for strict).
    * Exclusions: ST cohort wholesale, STAR/ChiNext first 5 sessions, pre-2014 listings'
      first session, ex-dividend suspects, zero-volume bars.
    * A T -> T+1 pair is usable only if the bars are <= 10 calendar days apart.
    * NEVER pooled across boards.  ChiNext is modelled inside the +-20% band era only.

SELF-CONTAINED BY DESIGN
    The panel construction below is a verbatim re-implementation of v0's, because v0 lives
    on a sibling branch and importing across branches is not a thing.  That is a real risk
    (a silent drift in a feature definition would invalidate the comparison), so it is
    GATED, not asserted: V0_PARITY_TARGETS carries v0's published holdout numbers and this
    file reproduces them at run time.  A mismatch is printed loudly in the JSON.

Run from repo root:  TZ=UTC python3 research/cn_prophet_audit/onset_calibration_v1.py
Outputs (frozen, committed):
    research/cn_prophet_audit/ONSET_CALIBRATION_V1_2026-08-08.json
    research/cn_prophet_audit/onset_forward_ledger.jsonl
    research/cn_prophet_audit/ONSET_CALIBRATION_V1_2026-08-08.md   (hand-written from JSON)
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import OrderedDict
from pathlib import Path

os.environ["TZ"] = "UTC"
try:
    time.tzset()
except AttributeError:  # pragma: no cover - non-POSIX
    pass

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from engine.china_microstructure import (  # noqa: E402
    CHINEXT_STAR_IPO_WINDOW,
    CHINEXT_WIDE_DATE,
    IPO_PRE2014_DATE,
    LIMIT_TAPE_START_DATE,
    PRE2014_IPO_WINDOW,
    _board_from_ticker,
    limit_width_for_date,
)

try:
    from sklearn.isotonic import IsotonicRegression
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    SKLEARN = True
except ImportError:  # pragma: no cover - documented degradation path
    SKLEARN = False

DATA = REPO / "data"
OUT_DIR = REPO / "research" / "cn_prophet_audit"
OUT_JSON = OUT_DIR / "ONSET_CALIBRATION_V1_2026-08-08.json"
OUT_LEDGER = OUT_DIR / "onset_forward_ledger.jsonl"

# ── frozen parameters (v0's, unchanged) ───────────────────────────────────────

WINDOW_START = LIMIT_TAPE_START_DATE           # 2011-01-01
WINDOW_END = pd.Timestamp("2026-08-07")        # last bar in the raw store at build time
LIMIT_CLOSE_TOL = 0.002                        # PRIMARY definition's feed-precision cushion
NEAR_LIMIT_FRAC = 0.95
MAX_PAIR_GAP_DAYS = 10
FIT_FRACTION = 0.70                            # first 70% of trading dates fit
THIN_CELL_N = 20

# ── frozen parameters (this file's, pre-registered before the first run) ──────

CALIB_FRACTION = 0.15      # last 15% of FIT dates -> isotonic slice; never the holdout
WINSOR_Q = (0.01, 0.99)    # winsorisation quantiles, computed on the fit CORE only
N_CAP = 3                  # 连板 categorical: 0, 1, 2, 3+
RELIABILITY_BINS = 10
TOP_K = (10, 20, 50)
B2_QUANTILES = 5           # f3 x f6 quintiles
B2_SHRINK_M = 20           # pseudo-count toward the N-marginal
RETRO_DATES = 20           # last N holdout feature-dates to retro-stamp
LEDGER_TOP_N = 50          # rows stamped per (board, date)

# THIN GATES — pre-registered from the classic events-per-variable rule, NOT tuned.  B1
# carries 9 parameters (6 features + 3 N dummies), so 150 fit-core positives is EPV ~= 17,
# comfortably above the EPV >= 10 floor.  A board that misses any gate is printed
# THIN-skipped with its measured counts, never modelled at a lower standard.
MIN_FIT_CORE_POS = 150
MIN_CALIB_POS = 50
MIN_HOLDOUT_POS = 100

MODEL_VERSION = "onset_v1"

# The six v0-surviving features.  Order is the model's column order and is frozen.
MODEL_FEATURES = OrderedDict([
    ("f1_vol_z20", "volume z-score of the feature bar vs its own prior 20 bars"),
    ("f3_runup_5", "5-session run-up: close[T-1] / close[T-6] - 1"),
    ("f4_sector_heat", "same-day sector limit-up count at the feature bar, leave-one-out"),
    ("f6_gap_pct", "gap at the feature bar's open: open[T-1] / close[T-2] - 1"),
    ("f7_dist_52w_low", "distance from the 52w low: close[T-1] / min(low, 252 bars) - 1"),
    ("f8_consec_up_days", "consecutive up-close days ending at the feature bar"),
])
N_DUMMIES = ["N_is_1", "N_is_2", "N_is_3plus"]
DESIGN_COLS = list(MODEL_FEATURES) + N_DUMMIES

RETIRED_FEATURES = {
    "f2_turnover_ratio": (
        "PRINTED NULL in v0 — not measurable on this basis.  A turnover ratio needs shares "
        "outstanding PER DATE and no CN store carries one.  No proxy substituted."
    ),
    "f5_near_limit_prev": (
        "PRINTED UNSTABLE in v0 — pooled main-board lift 7.22x on a class that is 0.03% of "
        "rows, per-name median lift 0.00 (28 of 208 names above 1x), sign flip on STAR, and "
        "total collapse (65.2x -> 0.00x) in the ChiNext band-era control.  Excluded here "
        "BECAUSE v0's pre-registration retired it; re-admitting it into a probability model "
        "would launder the exact false discovery that mechanism caught."
    ),
}

# v0's PUBLISHED holdout numbers.  This file re-derives the panel from scratch, so these are
# the gate that the re-derivation did not drift.  Checked at run time, printed in the JSON.
V0_PARITY_TARGETS = {
    "split_date": "2021-11-26",
    "fit_dates": 2646,
    "holdout_dates": 1135,
    "main_holdout_base_rate_pct": 1.245,
    "main_holdout_rows": 1373390,
    "main_fit_base_rate_pct": None,      # not published to 4dp in the receipt; informational
    "chinext_era_rows": 438042,
    "chinext_era_split_date": "2024-10-25",
    "main_limit_up_events": 50421,
    "chinext_limit_up_events": 8999,
    "star_limit_up_events": 878,
}

BOARD_SPLIT_RULE = {
    "main": "global",
    "star": "global",
    "chinext": "chinext_wide_era",
}

FILLABILITY_NOTE = (
    "P is for a limit-up CLOSE at predict_date; an entry is only fillable if predict_date's "
    "open < limit price — see rider lane"
)


# ── small helpers ─────────────────────────────────────────────────────────────

def streak_lengths(flags: np.ndarray) -> np.ndarray:
    """Vectorised consecutive-True run length ending at each position (v0's helper)."""
    f = np.asarray(flags, dtype=bool)
    n = f.size
    if n == 0:
        return np.zeros(0, dtype=np.int32)
    idx = np.arange(1, n + 1, dtype=np.int64)
    reset = np.where(~f, idx, 0)
    np.maximum.accumulate(reset, out=reset)
    out = idx - reset
    out[~f] = 0
    return out.astype(np.int32)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n <= 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (max(0.0, (c - h) / d), min(1.0, (c + h) / d))


def jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if (np.isnan(v) or np.isinf(v)) else v
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, float):
        return None if (np.isnan(obj) or np.isinf(obj)) else obj
    if isinstance(obj, pd.Timestamp):
        return obj.strftime("%Y-%m-%d")
    return obj


def brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def auc(y: np.ndarray, p: np.ndarray) -> float | None:
    """Rank concordance — the DISCRIMINATION number, invariant to any monotone recalibration.

    This is the statistic that separates "the model does not know the order" from "the model
    knows the order and states the wrong level".  A Brier skill can go negative purely from
    the second, so reporting Brier without this would misattribute the failure.
    """
    if y.min() == y.max():
        return None
    if SKLEARN:
        return float(roc_auc_score(y, p))
    from scipy.stats import rankdata  # pragma: no cover - fallback path
    r = rankdata(p)
    npos = float(y.sum())
    nneg = float(len(y) - npos)
    return float((r[y > 0].sum() - npos * (npos + 1) / 2) / (npos * nneg))


def murphy(y: np.ndarray, p: np.ndarray) -> dict:
    """Exact Murphy decomposition BS = RELIABILITY - RESOLUTION + UNCERTAINTY.

    Grouped on DISTINCT predicted values, not on display bins, so the identity holds exactly
    (p is constant within a group by construction) and the split is not an artifact of a
    binning choice.  RELIABILITY is the miscalibration cost; RESOLUTION is the credit for
    separating the outcome; UNCERTAINTY is the base rate's own variance and is identical for
    every model on the same holdout.

    NOTE the asymmetry this creates in reading: RESOLUTION is what a perfect recalibration
    would keep, so a model with high RESOLUTION and high RELIABILITY is a good ranker stating
    wrong levels — a repairable failure.  A model with low RESOLUTION is not repairable by
    recalibration at all.  That distinction is the whole verdict here, which is why this is
    computed rather than argued.
    """
    vals, inv = np.unique(p, return_inverse=True)
    n = np.bincount(inv, minlength=len(vals)).astype(np.float64)
    k = np.bincount(inv, weights=y, minlength=len(vals))
    r = np.divide(k, n, out=np.zeros_like(k), where=n > 0)
    N = float(len(y))
    rbar = float(y.mean())
    rel = float(np.sum(n * (vals - r) ** 2) / N)
    res = float(np.sum(n * (r - rbar) ** 2) / N)
    unc = rbar * (1.0 - rbar)
    degenerate = len(vals) > 0.5 * N
    return {
        "distinct_predicted_values": int(len(vals)),
        "reliability_x1000": round(1000.0 * rel, 6),
        "resolution_x1000": round(1000.0 * res, 6),
        "uncertainty_x1000": round(1000.0 * unc, 6),
        "identity_residual_x1000": round(1000.0 * abs((rel - res + unc) - brier(y, p)), 9),
        "degenerate": bool(degenerate),
        "degenerate_note": (
            "DO NOT READ THESE TERMS.  A model whose predictions are near-unique puts one row "
            "in each group, so every group's realized rate is 0 or 1: RESOLUTION collapses "
            "onto UNCERTAINTY and RELIABILITY onto the Brier score itself.  That is an "
            "artifact of grouping a continuous prediction, not a statement about the model.  "
            "The comparable models are the ones whose predictions are quantised (isotonic "
            "output, ladder cells, bucket cells)." if degenerate else None),
    }


def logloss(y: np.ndarray, p: np.ndarray, eps: float = 1e-6) -> float:
    """Log-loss with the clip stated rather than hidden.

    Isotonic regression legitimately emits exactly 0.0 for a leading block with no
    positives; log-loss is undefined there.  The clip is symmetric and disclosed in the
    JSON, so the reader can see it is a numerical guard and not a scoring choice.
    """
    q = np.clip(p, eps, 1.0 - eps)
    return float(-np.mean(y * np.log(q) + (1 - y) * np.log(1 - q)))


# ── STAGE A — panel construction (verbatim re-implementation of v0) ───────────

def load_st_cohort() -> tuple[frozenset[str], str]:
    p = DATA / "china_st" / "st_snapshot.parquet"
    if not p.exists():
        return frozenset(), "st_snapshot.parquet MISSING — no ST exclusion applied"
    df = pd.read_parquet(p)
    tick = frozenset(df["ticker"].astype(str).tolist())
    asof = sorted(set(df["asof"].astype(str)))
    return tick, f"n={len(tick)} tickers, asof {asof}"


def load_sector_map() -> tuple[dict[str, str], dict]:
    p = DATA / "china_search" / "members.parquet"
    if not p.exists():
        return {}, {"source": str(p), "status": "MISSING"}
    df = pd.read_parquet(p)
    m = {str(k): str(v) for k, v in df["sector"].items()}
    return m, {
        "source": "data/china_search/members.parquet",
        "n_tickers": len(m),
        "n_sectors": int(df["sector"].nunique()),
        "caveat": (
            "CURRENT sector membership applied to 15 years of history — sector "
            "reclassification is not reconstructible from this store.  f4_sector_heat "
            "therefore measures heat within TODAY's sector definition and within THIS "
            "curated universe, not within the sector as it was constituted in 2013."
        ),
    }


def detect_ticker(ticker: str, df: pd.DataFrame, board: str) -> tuple[pd.DataFrame, dict]:
    """v0's detector, trimmed to the columns this model needs and carrying next_bar_date.

    Runs over the FULL price history so the rolling baselines (20-bar volume, 252-bar low)
    are warm at the window start, then returns only in-window rows.
    """
    stats = {"ipo_excluded": 0, "exdiv_excluded": 0, "zero_volume_excluded": 0,
             "bars_in_window": 0}
    if df is None or len(df) < 30:
        return pd.DataFrame(), stats

    df = df.sort_index()
    idx = pd.to_datetime(df.index)
    close = df["close"].to_numpy(dtype=np.float64)
    low = df["low"].to_numpy(dtype=np.float64)
    open_ = df["open"].to_numpy(dtype=np.float64)
    vol = df["volume"].to_numpy(dtype=np.float64)
    n = len(close)

    pc = np.roll(close, 1)
    pc[0] = np.nan

    if board == "chinext":
        width = np.where(
            idx.to_numpy() >= CHINEXT_WIDE_DATE.to_datetime64(),
            limit_width_for_date("chinext", CHINEXT_WIDE_DATE),
            limit_width_for_date("chinext", CHINEXT_WIDE_DATE - pd.Timedelta(days=1)))
    else:
        width = np.full(n, limit_width_for_date(board, WINDOW_END), dtype=np.float64)
    width = width.astype(np.float64)

    excl = np.zeros(n, dtype=bool)
    ipo_window = 0
    if board in ("star", "chinext"):
        ipo_window = CHINEXT_STAR_IPO_WINDOW
    elif idx.min() < IPO_PRE2014_DATE:
        ipo_window = PRE2014_IPO_WINDOW
    ipo_mask = np.zeros(n, dtype=bool)
    if ipo_window:
        ipo_mask[:ipo_window] = True
        excl |= ipo_mask

    bad_pc = ~np.isfinite(pc) | (pc <= 0)
    excl |= bad_pc

    with np.errstate(invalid="ignore", divide="ignore"):
        open_move = np.abs(open_ - pc) / pc
    exdiv = np.isfinite(open_move) & (open_move > width * 1.5) & ~excl
    excl |= exdiv

    zero_vol = np.isfinite(vol) & (vol <= 0) & ~excl
    excl |= zero_vol

    with np.errstate(invalid="ignore"):
        lim_up = np.round(pc * (1.0 + width), 2)
        ret = close / pc - 1.0

    in_win = np.asarray((idx >= WINDOW_START) & (idx <= WINDOW_END), dtype=bool)
    live = in_win & ~excl

    # PRIMARY definition (v0's adjudicated choice).
    lu = live & np.isfinite(lim_up) & (close >= lim_up * (1.0 - LIMIT_CLOSE_TOL))
    near_up = live & np.isfinite(ret) & (ret >= NEAR_LIMIT_FRAC * width) & ~lu
    lianban = streak_lengths(lu)

    # pre-registered features, all observable at the bar's own close
    s_vol = pd.Series(vol)
    base_mu = s_vol.shift(1).rolling(20, min_periods=15).mean().to_numpy()
    base_sd = s_vol.shift(1).rolling(20, min_periods=15).std(ddof=0).to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        f1 = np.where(base_sd > 0, (vol - base_mu) / base_sd, np.nan)
        f3 = close / np.roll(close, 5) - 1.0
        f6 = open_ / pc - 1.0
        low252 = pd.Series(low).rolling(252, min_periods=120).min().to_numpy()
        f7 = np.where(low252 > 0, close / low252 - 1.0, np.nan)
    f3[:5] = np.nan
    f8 = streak_lengths(np.r_[False, close[1:] > close[:-1]])

    days = idx.to_numpy().astype("datetime64[D]").astype(np.int64)
    gap_next = np.r_[np.diff(days), np.iinfo(np.int64).max]
    pair_ok = gap_next <= MAX_PAIR_GAP_DAYS

    nxt_lu = np.r_[lu[1:], False]
    nxt_live = np.r_[live[1:], False]
    y_ok = pair_ok & nxt_live
    nxt_date = np.r_[idx.to_numpy()[1:], np.datetime64("NaT", "ns")]

    keep = in_win
    stats["ipo_excluded"] = int((ipo_mask & keep).sum())
    stats["exdiv_excluded"] = int((exdiv & keep).sum())
    stats["zero_volume_excluded"] = int((zero_vol & keep).sum())
    stats["bars_in_window"] = int(keep.sum())

    out = pd.DataFrame({
        "date": idx[keep],
        "ticker": ticker,
        "board": board,
        "live": live[keep],
        "limit_up": lu[keep],
        "near_limit_up": near_up[keep],
        "lianban": lianban[keep].astype(np.int16),
        "y_ok": y_ok[keep],
        "y_limit_up": nxt_lu[keep],
        "next_bar_date": nxt_date[keep],
        "f1_vol_z20": f1[keep].astype(np.float32),
        "f3_runup_5": f3[keep].astype(np.float32),
        "f6_gap_pct": f6[keep].astype(np.float32),
        "f7_dist_52w_low": f7[keep].astype(np.float32),
        "f8_consec_up_days": f8[keep].astype(np.float32),
    })
    return out, stats


def build_panel() -> tuple[pd.DataFrame, dict]:
    st_set, st_note = load_st_cohort()
    sector_map, sector_meta = load_sector_map()

    files = sorted((DATA / "china_stocks_raw").glob("*.parquet"))
    meta = {
        "raw_store": ("data/china_stocks_raw (nominal/unadjusted OHLCV — the correct basis; "
                      "data/china_stocks is split/dividend adjusted and would fabricate "
                      "limit misses)"),
        "files_found": len(files),
        "st_cohort": st_note,
        "st_excluded_tickers": len(st_set),
        "sector_map": sector_meta,
        "window": [WINDOW_START.strftime("%Y-%m-%d"), WINDOW_END.strftime("%Y-%m-%d")],
    }

    frames, agg = [], {"ipo_excluded": 0, "exdiv_excluded": 0, "zero_volume_excluded": 0,
                       "bars_in_window": 0}
    boards_seen, kept, skipped_st, skipped_thin = {}, 0, 0, 0
    for p in files:
        ticker = p.stem
        if ticker in st_set:
            skipped_st += 1
            continue
        board = _board_from_ticker(ticker)
        try:
            df = pd.read_parquet(p)
        except Exception:  # noqa: BLE001
            skipped_thin += 1
            continue
        out, stats = detect_ticker(ticker, df, board)
        if out.empty:
            skipped_thin += 1
            continue
        for k in agg:
            agg[k] += stats[k]
        boards_seen[board] = boards_seen.get(board, 0) + 1
        frames.append(out)
        kept += 1

    meta.update({
        "tickers_kept": kept,
        "tickers_skipped_st": skipped_st,
        "tickers_skipped_thin_or_unreadable": skipped_thin,
        "board_counts": boards_seen,
        "excluded_bars": agg,
    })

    panel = pd.concat(frames, ignore_index=True)
    panel["sector"] = panel["ticker"].map(sector_map).fillna("UNKNOWN")
    panel["year"] = panel["date"].dt.year.astype(np.int16)

    # f4 — cohort heat, LEAVE-ONE-OUT so the feature measures the sector, not the name.
    grp = panel.groupby(["date", "sector"], observed=True)["limit_up"].transform("sum")
    panel["f4_sector_heat"] = (grp - panel["limit_up"].astype(np.int32)).astype(np.float32)
    panel.loc[panel["sector"] == "UNKNOWN", "f4_sector_heat"] = np.nan

    # 连板 categorical at the FEATURE bar.
    panel["N_bucket"] = np.minimum(panel["lianban"].to_numpy(), N_CAP).astype(np.int8)
    panel["N_is_1"] = (panel["N_bucket"] == 1).astype(np.float32)
    panel["N_is_2"] = (panel["N_bucket"] == 2).astype(np.float32)
    panel["N_is_3plus"] = (panel["N_bucket"] == 3).astype(np.float32)

    # COMPLETE-CASE flag.  A joint model needs every column present on the same row; v0's
    # per-feature decile tables did not.  Rows are NOT imputed — imputation on f4 would
    # invent sector heat for names with no sector row, and imputation on f7 would invent a
    # 52-week low for a name that has not traded 120 bars.  The coverage cost is measured
    # and printed rather than papered over.
    panel["complete_case"] = panel[list(MODEL_FEATURES)].notna().all(axis=1).to_numpy()

    meta["sector_coverage_pct"] = round(100.0 * float((panel["sector"] != "UNKNOWN").mean()), 2)
    meta["panel_rows"] = len(panel)
    meta["live_rows"] = int(panel["live"].sum())
    meta["limit_up_events_by_board"] = {
        str(b): int(g) for b, g in
        panel[panel["live"] & panel["limit_up"]].groupby("board", observed=True).size().items()
    }

    usable = panel["live"] & panel["y_ok"]
    cc = panel["complete_case"].to_numpy()
    meta["complete_case_coverage"] = {
        "usable_rows": int(usable.sum()),
        "usable_and_complete": int((usable & cc).sum()),
        "coverage_pct": round(100.0 * float((usable & cc).sum()) / max(1, int(usable.sum())), 2),
        "dropped_by_feature": {
            f: int((usable & panel[f].isna()).sum()) for f in MODEL_FEATURES
        },
        "note": (
            "Complete-case, NOT imputed.  The dominant single cause is f4_sector_heat, which "
            "is null wherever the name has no row in the CURRENT sector map — a universe "
            "property, not a random one, so the modelled row set is mildly non-random with "
            "respect to sector coverage.  Stated, not corrected: imputing a sector heat for a "
            "name with no sector is inventing the feature."
        ),
    }
    return panel, meta


# ── STAGE B — splits ──────────────────────────────────────────────────────────

def make_splits(panel: pd.DataFrame) -> tuple[dict, pd.Timestamp]:
    """Board -> {fit_core, fit_calib, holdout} date boundaries.  FROZEN.

    The GLOBAL split is v0's: the first 70% of usable trading dates, pooled over boards
    (the CN trading calendar is shared, so pooling the date set does not pool the rates).

    ChiNext gets its own split and its own era.  v0 measured that the global split lands
    AFTER ChiNext's 2020-08-24 move from a +-10% to a +-20% band, so a globally-split
    ChiNext model would be fitted mostly on a 10%-band market and evaluated entirely on a
    20%-band one — its fit and holdout base rates differ ~5x for a rule change, not a
    signal.  ChiNext is therefore restricted to the +-20% era and re-split 70/30 inside it.
    """
    usable = panel[panel["live"] & panel["y_ok"]]
    dates = np.sort(usable["date"].unique())
    split_i = int(len(dates) * FIT_FRACTION)
    global_split = pd.Timestamp(dates[split_i])

    out = {"global": {
        "rule": f"first {int(FIT_FRACTION * 100)}% of pooled usable trading dates",
        "split_date": global_split.strftime("%Y-%m-%d"),
        "fit_dates": int(split_i),
        "holdout_dates": int(len(dates) - split_i),
        "first_date": pd.Timestamp(dates[0]).strftime("%Y-%m-%d"),
        "last_date": pd.Timestamp(dates[-1]).strftime("%Y-%m-%d"),
    }}

    for board in sorted(usable["board"].unique()):
        rule = BOARD_SPLIT_RULE.get(board, "global")
        b = usable[usable["board"] == board]
        if rule == "chinext_wide_era":
            b = b[b["date"] >= CHINEXT_WIDE_DATE]
            bdates = np.sort(b["date"].unique())
            si = int(len(bdates) * FIT_FRACTION)
            sd = pd.Timestamp(bdates[si])
            era_start = CHINEXT_WIDE_DATE
        else:
            bdates = np.sort(b["date"].unique())
            sd = global_split
            si = int((bdates < sd).sum())
            era_start = pd.Timestamp(dates[0])
        fit_dates = bdates[bdates < sd]
        ci = int(len(fit_dates) * (1.0 - CALIB_FRACTION))
        calib_start = pd.Timestamp(fit_dates[ci]) if len(fit_dates) else sd
        out[board] = {
            "split_rule": rule,
            "era_start": era_start.strftime("%Y-%m-%d"),
            "fit_core": [era_start.strftime("%Y-%m-%d"),
                         (calib_start - pd.Timedelta(days=1)).strftime("%Y-%m-%d")],
            "fit_calib": [calib_start.strftime("%Y-%m-%d"),
                          (sd - pd.Timedelta(days=1)).strftime("%Y-%m-%d")],
            "holdout": [sd.strftime("%Y-%m-%d"),
                        pd.Timestamp(bdates[-1]).strftime("%Y-%m-%d")],
            "split_date": sd.strftime("%Y-%m-%d"),
            "calib_start": calib_start.strftime("%Y-%m-%d"),
            "n_fit_dates": int(si),
            "n_holdout_dates": int(len(bdates) - si),
            "why": ("ChiNext is modelled inside the +-20% band era ONLY and re-split within "
                    "it; pooling across 2020-08-24 would model two different games."
                    if rule == "chinext_wide_era" else
                    "v0's global 70/30 date split, unchanged."),
        }
    return out, global_split


def slice_board(panel: pd.DataFrame, board: str, splits: dict) -> dict:
    s = splits[board]
    era_start = pd.Timestamp(s["era_start"])
    sd = pd.Timestamp(s["split_date"])
    cs = pd.Timestamp(s["calib_start"])
    m = (panel["board"] == board) & (panel["date"] >= era_start)
    usable = panel[m & panel["live"] & panel["y_ok"] & panel["complete_case"]]
    return {
        "fit_core": usable[usable["date"] < cs],
        "fit_calib": usable[(usable["date"] >= cs) & (usable["date"] < sd)],
        "fit_all": usable[usable["date"] < sd],
        "holdout": usable[usable["date"] >= sd],
    }


# ── STAGE C — models ──────────────────────────────────────────────────────────

def fit_b0(fit_all: pd.DataFrame) -> dict:
    """Ladder-only benchmark: fit-window base rate per 连板 bucket.

    Fitted on the WHOLE fit window, not just the fit core.  That deliberately gives B0
    MORE data than B1's logistic gets, so the skill comparison is conservative in the
    benchmark's favour.  B0 needs no calibration step: it IS an empirical rate.
    """
    g = fit_all.groupby("N_bucket", observed=True)["y_limit_up"].agg(["size", "sum"])
    base = float(fit_all["y_limit_up"].mean())
    ladder = {}
    for nb, row in g.iterrows():
        n, k = int(row["size"]), int(row["sum"])
        ci = wilson(k, n)
        ladder[int(nb)] = {
            "N_label": f"{N_CAP}+" if int(nb) == N_CAP else str(int(nb)),
            "n": n, "k": k,
            "p": (k / n) if n else base,
            "rate_pct": round(100.0 * k / n, 4) if n else None,
            "wilson95_pct": [round(100.0 * ci[0], 4), round(100.0 * ci[1], 4)] if ci else None,
            "thin": n < THIN_CELL_N,
        }
    return {"ladder": ladder, "fallback_p": base,
            "fit_rows": len(fit_all), "fit_positives": int(fit_all["y_limit_up"].sum())}


def apply_b0(df: pd.DataFrame, model: dict) -> np.ndarray:
    lad = model["ladder"]
    fb = model["fallback_p"]
    nb = df["N_bucket"].to_numpy()
    out = np.full(len(df), fb, dtype=np.float64)
    for k, v in lad.items():
        out[nb == int(k)] = v["p"]
    return out


def fit_scaler(fit_core: pd.DataFrame) -> dict:
    """Winsorisation bounds + standardisation moments — FIT CORE ONLY (leakage guard)."""
    sc = {}
    for f in MODEL_FEATURES:
        v = fit_core[f].to_numpy(dtype=np.float64)
        v = v[np.isfinite(v)]
        lo, hi = np.quantile(v, WINSOR_Q[0]), np.quantile(v, WINSOR_Q[1])
        w = np.clip(v, lo, hi)
        mu, sd = float(w.mean()), float(w.std(ddof=0))
        sc[f] = {"winsor_lo": float(lo), "winsor_hi": float(hi),
                 "mean": mu, "std": sd if sd > 0 else 1.0}
    return sc


def design(df: pd.DataFrame, scaler: dict, cols: list[str]) -> np.ndarray:
    out = np.empty((len(df), len(cols)), dtype=np.float64)
    for j, c in enumerate(cols):
        v = df[c].to_numpy(dtype=np.float64)
        if c in scaler:
            s = scaler[c]
            v = np.clip(v, s["winsor_lo"], s["winsor_hi"])
            v = (v - s["mean"]) / s["std"]
        out[:, j] = v
    return out


def fit_logistic(X: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float, dict]:
    """Unpenalised logistic via sklearn lbfgs, with an IRLS fallback if sklearn is absent."""
    if SKLEARN:
        # C=np.inf is the unpenalised setting in sklearn >= 1.8 (penalty=None is deprecated
        # there and removed in 1.10).  Features are standardised, so the fit is well
        # conditioned without a ridge term and no shrinkage is silently applied.
        clf = LogisticRegression(C=np.inf, solver="lbfgs", max_iter=1000, tol=1e-7)
        clf.fit(X, y)
        return clf.coef_[0].copy(), float(clf.intercept_[0]), {
            "solver": "sklearn.linear_model.LogisticRegression(C=inf, lbfgs) — unpenalised",
            "n_iter": int(np.atleast_1d(clf.n_iter_)[0]),
        }
    # pragma: no cover — documented degradation path, exercised only without sklearn
    Xd = np.c_[np.ones(len(X)), X]
    beta = np.zeros(Xd.shape[1])
    for _ in range(60):
        eta = Xd @ beta
        p = 1.0 / (1.0 + np.exp(-np.clip(eta, -35, 35)))
        w = np.clip(p * (1 - p), 1e-8, None)
        z = eta + (y - p) / w
        XtW = Xd.T * w
        beta_new = np.linalg.solve(XtW @ Xd + 1e-8 * np.eye(Xd.shape[1]), XtW @ z)
        if np.max(np.abs(beta_new - beta)) < 1e-9:
            beta = beta_new
            break
        beta = beta_new
    return beta[1:], float(beta[0]), {"solver": "numpy IRLS (sklearn unavailable)",
                                      "n_iter": None}


def predict_logit(X: np.ndarray, coef: np.ndarray, intercept: float) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(X @ coef + intercept, -35, 35)))


class Isotonic:
    """Thin wrapper so the fallback path has the same shape as sklearn's."""

    def __init__(self, x: np.ndarray, y: np.ndarray):
        if SKLEARN:
            self._m = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            self._m.fit(x, y)
            self.knots = int(len(np.unique(self._m.predict(np.unique(x)))))
        else:  # pragma: no cover — PAVA fallback
            order = np.argsort(x, kind="stable")
            xs, ys = x[order], y[order].astype(np.float64)
            vals, wts = list(ys), [1.0] * len(ys)
            i = 0
            while i < len(vals) - 1:
                if vals[i] > vals[i + 1]:
                    tw = wts[i] + wts[i + 1]
                    vals[i] = (vals[i] * wts[i] + vals[i + 1] * wts[i + 1]) / tw
                    wts[i] = tw
                    del vals[i + 1], wts[i + 1]
                    i = max(i - 1, 0)
                else:
                    i += 1
            fitted, k = [], 0
            for v, w in zip(vals, wts):
                fitted.extend([v] * int(round(w)))
                k += 1
            self._x, self._y, self.knots = xs, np.array(fitted[:len(xs)]), k
            self._m = None

    def predict(self, x: np.ndarray) -> np.ndarray:
        if self._m is not None:
            return np.clip(np.asarray(self._m.predict(x), dtype=np.float64), 0.0, 1.0)
        return np.clip(np.interp(x, self._x, self._y), 0.0, 1.0)  # pragma: no cover


def fit_b1(sl: dict, cols: list[str], label: str) -> dict:
    """Logistic on fit CORE, isotonic on fit CALIB, frozen.  The holdout is never touched."""
    scaler = fit_scaler(sl["fit_core"])
    Xc = design(sl["fit_core"], scaler, cols)
    yc = sl["fit_core"]["y_limit_up"].to_numpy(dtype=np.float64)
    coef, icept, info = fit_logistic(Xc, yc)

    Xk = design(sl["fit_calib"], scaler, cols)
    yk = sl["fit_calib"]["y_limit_up"].to_numpy(dtype=np.float64)
    p_raw_calib = predict_logit(Xk, coef, icept)
    iso = Isotonic(p_raw_calib, yk)

    return {
        "label": label,
        "cols": list(cols),
        "scaler": scaler,
        "coef": {c: float(v) for c, v in zip(cols, coef)},
        "intercept": float(icept),
        "solver": info,
        "isotonic_knots": iso.knots,
        "fit_core_rows": len(sl["fit_core"]),
        "fit_core_positives": int(yc.sum()),
        "fit_calib_rows": len(sl["fit_calib"]),
        "fit_calib_positives": int(yk.sum()),
        "_iso": iso,
        "_coef": coef,
        "_icept": icept,
    }


def apply_b1(df: pd.DataFrame, model: dict, raw: bool = False) -> np.ndarray:
    X = design(df, model["scaler"], model["cols"])
    p = predict_logit(X, model["_coef"], model["_icept"])
    return p if raw else model["_iso"].predict(p)


def fit_b2(sl: dict) -> dict:
    """Empirical (f3 quintile x f6 quintile x N) cells — the non-parametric sanity check.

    Quantile edges come from the fit window ONLY.  Cell rates are shrunk toward the row's
    N-marginal with a pseudo-count of B2_SHRINK_M, and a cell thinner than THIN_CELL_N
    falls back to the N-marginal entirely.  A plain Laplace (k+1)/(n+2) would be badly
    biased upward at a ~1% base rate (an empty n=25 cell would read 3.7%), so the prior is
    the N-marginal rather than a uniform one — stated because it is a real choice.
    """
    f = sl["fit_all"]
    edges = {}
    for c in ("f3_runup_5", "f6_gap_pct"):
        q = np.quantile(f[c].to_numpy(dtype=np.float64),
                        np.linspace(0, 1, B2_QUANTILES + 1)[1:-1])
        edges[c] = [float(x) for x in np.unique(q)]
    nmarg = f.groupby("N_bucket", observed=True)["y_limit_up"].mean().to_dict()
    base = float(f["y_limit_up"].mean())

    def bucketise(df: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({
            "b3": np.searchsorted(edges["f3_runup_5"],
                                  df["f3_runup_5"].to_numpy(dtype=np.float64), side="right"),
            "b6": np.searchsorted(edges["f6_gap_pct"],
                                  df["f6_gap_pct"].to_numpy(dtype=np.float64), side="right"),
            "N": df["N_bucket"].to_numpy(),
        }, index=df.index)

    fb = bucketise(f)
    fb["y"] = f["y_limit_up"].to_numpy()
    agg = fb.groupby(["b3", "b6", "N"], observed=True)["y"].agg(["size", "sum"])
    cells = {}
    for (b3, b6, nb), row in agg.iterrows():
        n, k = int(row["size"]), int(row["sum"])
        prior = float(nmarg.get(nb, base))
        p = prior if n < THIN_CELL_N else (k + B2_SHRINK_M * prior) / (n + B2_SHRINK_M)
        cells[f"{int(b3)}|{int(b6)}|{int(nb)}"] = {"n": n, "k": k, "p": float(p),
                                                   "thin": n < THIN_CELL_N}
    return {
        "edges": edges, "n_marginal": {int(k): float(v) for k, v in nmarg.items()},
        "fallback_p": base, "cells": cells,
        "n_cells": len(cells),
        "n_cells_thin": int(sum(1 for v in cells.values() if v["thin"])),
        "shrink_pseudocount": B2_SHRINK_M,
        "_bucketise": bucketise,
    }


def apply_b2(df: pd.DataFrame, model: dict) -> np.ndarray:
    b = model["_bucketise"](df)
    keys = (b["b3"].astype(str) + "|" + b["b6"].astype(str) + "|" + b["N"].astype(str))
    lut = pd.Series({k: v["p"] for k, v in model["cells"].items()}, dtype="float64")
    out = np.array(keys.map(lut).to_numpy(dtype=np.float64), copy=True)
    miss = ~np.isfinite(out)
    if bool(miss.any()):
        nm, fb = model["n_marginal"], model["fallback_p"]
        nb = b["N"].to_numpy()
        out[miss] = np.array([float(nm.get(int(x), fb)) for x in nb[miss]])
    return out


# ── STAGE D — holdout evaluation ──────────────────────────────────────────────

def reliability(y: np.ndarray, p: np.ndarray, bins: int = RELIABILITY_BINS) -> dict:
    """Predicted-probability bins -> predicted mean vs realized rate.  THE PRODUCT SPINE.

    Quantile bins on P-hat, not fixed-width: at a ~1% base rate fixed-width bins put 99.9%
    of the mass in one cell and say nothing.  Ties (B0 has four distinct values; isotonic
    emits a step function) collapse bins, so the REALISED bin count is printed rather than
    assumed to be ten.
    """
    s = pd.Series(p)
    nuniq = int(s.nunique())
    if nuniq <= bins:
        # B0 is four numbers.  qcut over it collapses to ONE bin because 99% of the mass sits
        # at the N=0 rate, which would hide the benchmark's entire ladder structure and make
        # it look resolution-free.  When a model has fewer distinct values than requested
        # bins, its distinct values ARE the bins.
        b = s.rank(method="dense").astype(int).to_numpy() - 1
    else:
        try:
            b = pd.qcut(s, bins, labels=False, duplicates="drop")
        except ValueError:
            b = pd.Series(np.zeros(len(s), dtype=int))
        if b.isna().all():
            b = pd.Series(np.zeros(len(s), dtype=int))
        b = b.fillna(0).astype(int).to_numpy()
    rows, ece, n_tot = [], 0.0, len(y)
    for bb in sorted(set(b.tolist())):
        m = b == bb
        n = int(m.sum())
        k = int(y[m].sum())
        pm, rr = float(p[m].mean()), (k / n if n else 0.0)
        ci = wilson(k, n)
        ece += (n / max(1, n_tot)) * abs(pm - rr)
        rows.append({
            "bin": int(bb) + 1, "n": n, "k": k,
            "p_hat_mean_pct": round(100.0 * pm, 4),
            "p_hat_lo_pct": round(100.0 * float(p[m].min()), 4),
            "p_hat_hi_pct": round(100.0 * float(p[m].max()), 4),
            "realized_pct": round(100.0 * rr, 4),
            "realized_wilson95_pct": ([round(100.0 * ci[0], 4), round(100.0 * ci[1], 4)]
                                      if ci else None),
            "calibrated_in_ci": (bool(ci[0] <= pm <= ci[1]) if ci else None),
            "thin": n < THIN_CELL_N,
        })
    in_ci = [r["calibrated_in_ci"] for r in rows if r["calibrated_in_ci"] is not None]
    return {
        "bins_realized": len(rows),
        "bins_requested": bins,
        "ece_pct": round(100.0 * ece, 4),
        "bins_within_wilson95": int(sum(1 for x in in_ci if x)),
        "bins_total": len(in_ci),
        "table": rows,
    }


def headline(y: np.ndarray, p: np.ndarray, p_b0: np.ndarray) -> dict:
    bs, bs0 = brier(y, p), brier(y, p_b0)
    ll, ll0 = logloss(y, p), logloss(y, p_b0)
    a = auc(y, p)
    return {
        "brier_x1000": round(1000.0 * bs, 6),
        "brier_skill_vs_b0": round(1.0 - bs / bs0, 6) if bs0 > 0 else None,
        "brier_skill_vs_b0_pct": round(100.0 * (1.0 - bs / bs0), 4) if bs0 > 0 else None,
        "log_loss": round(ll, 6),
        "log_loss_skill_vs_b0_pct": round(100.0 * (1.0 - ll / ll0), 4) if ll0 > 0 else None,
        "auc": round(a, 5) if a is not None else None,
        "murphy": murphy(y, p),
        "mean_p_hat_pct": round(100.0 * float(p.mean()), 4),
        "realized_base_pct": round(100.0 * float(y.mean()), 4),
        "mean_p_over_realized": round(float(p.mean()) / float(y.mean()), 4) if y.mean() else None,
    }


def per_year_skill(hold: pd.DataFrame, preds: dict) -> list[dict]:
    rows = []
    for yr, g in hold.groupby("year", observed=True):
        m = g.index.to_numpy()
        yv = g["y_limit_up"].to_numpy(dtype=np.float64)
        bs0 = brier(yv, preds["B0"][m])
        rec = {"year": int(yr), "n": len(g), "positives": int(yv.sum()),
               "base_pct": round(100.0 * float(yv.mean()), 4),
               "b0_brier_x1000": round(1000.0 * bs0, 6)}
        for k in ("B1", "B2", "P1", "P2"):
            if k not in preds:
                continue
            bs = brier(yv, preds[k][m])
            rec[f"{k.lower()}_skill_pct"] = (round(100.0 * (1.0 - bs / bs0), 4)
                                             if bs0 > 0 else None)
        rows.append(rec)
    rows.sort(key=lambda r: r["year"])
    return rows


def top_k_table(hold: pd.DataFrame, preds: dict, ranker_names: list[str]) -> list[dict]:
    """Per holdout feature-date, rank by P-hat and measure the top-K bucket.

    Ties are broken by ticker ascending — deterministic, and load-bearing for B0, which has
    only four distinct values and therefore selects an essentially ARBITRARY K names from
    inside its top tie group.  That is not a defect of the measurement; it is the honest
    statement that a ladder is a calibration benchmark, not a ranker.
    """
    base = float(hold["y_limit_up"].mean())
    dates = hold["date"].to_numpy()
    tick = hold["ticker"].to_numpy()
    yv = hold["y_limit_up"].to_numpy(dtype=np.float64)
    order_date = np.argsort(dates, kind="stable")
    uniq, starts = np.unique(dates[order_date], return_index=True)
    bounds = list(starts) + [len(order_date)]

    out = []
    for name in ranker_names:
        p = preds[name]
        for K in TOP_K:
            hits = sel = 0
            psum = 0.0
            pos_total = 0
            dates_used = 0
            for i in range(len(uniq)):
                idx = order_date[bounds[i]:bounds[i + 1]]
                if idx.size == 0:
                    continue
                dates_used += 1
                pos_total += int(yv[idx].sum())
                sub_p, sub_t = p[idx], tick[idx]
                ordr = np.lexsort((sub_t, -sub_p))[:K]
                pick = idx[ordr]
                hits += int(yv[pick].sum())
                sel += int(pick.size)
                psum += float(p[pick].sum())
            out.append({
                "ranker": name, "K": K,
                "dates": dates_used,
                "rows_selected": sel,
                "hits": hits,
                "realized_rate_pct": round(100.0 * hits / max(1, sel), 4),
                "lift_vs_base": round((hits / max(1, sel)) / base, 3) if base > 0 else None,
                "mean_p_hat_pct": round(100.0 * psum / max(1, sel), 4),
                "calibration_ratio_p_over_realized": (
                    round((psum / max(1, sel)) / (hits / sel), 3) if hits > 0 else None),
                "capture_share_pct": round(100.0 * hits / max(1, pos_total), 3),
                "positives_available": pos_total,
            })
    return out


# ── STAGE E — forward ledger ──────────────────────────────────────────────────

def next_cn_session(d: pd.Timestamp) -> pd.Timestamp:
    """Next weekday after d.  CALENDAR ESTIMATE, holidays NOT applied.

    The store cannot know a future session date; every ledger row carries
    predict_date_source so a grader can tell an observed next bar from this estimate and
    re-resolve it against the store rather than trusting the guess.
    """
    n = d + pd.Timedelta(days=1)
    while n.weekday() >= 5:
        n += pd.Timedelta(days=1)
    return n


def ledger_rows(df: pd.DataFrame, p_b1: np.ndarray, p_b0: np.ndarray, era: str,
                stamped: str, top_n: int) -> list[dict]:
    d = df.copy()
    d["_p1"], d["_p0"] = p_b1, p_b0
    rows = []
    for (dt, board), g in d.groupby(["date", "board"], observed=True):
        g = g.sort_values(["_p1", "ticker"], ascending=[False, True]).head(top_n)
        for _i, r in g.iterrows():
            fd = pd.Timestamp(r["date"])
            nb = r["next_bar_date"]
            if pd.notna(nb):
                pd_date, src = pd.Timestamp(nb), "next_usable_bar_in_store"
            else:
                pd_date, src = next_cn_session(fd), "next_weekday_calendar_estimate"
            rows.append({
                "stamped_at_utc": stamped,
                "feature_date_T": fd.strftime("%Y-%m-%d"),
                "predict_date": pd_date.strftime("%Y-%m-%d"),
                "predict_date_source": src,
                "ticker": str(r["ticker"]),
                "board": str(r["board"]),
                "ladder_N_at_T": int(r["lianban"]),
                "p_next_board": round(float(r["_p1"]), 6),
                "p_b0": round(float(r["_p0"]), 6),
                "model_version": MODEL_VERSION,
                "era": era,
                "top_features_snapshot": {
                    f: (None if not np.isfinite(float(r[f])) else round(float(r[f]), 6))
                    for f in MODEL_FEATURES
                },
                "fillability_note": FILLABILITY_NOTE,
            })
    return rows


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:  # noqa: C901 - one linear instrument, deliberately readable top-to-bottom
    t0 = time.time()
    stamped = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"[onset_v1] sklearn={'yes' if SKLEARN else 'NO — numpy IRLS/PAVA fallback'}",
          flush=True)

    print("[A] building panel ...", flush=True)
    panel, meta = build_panel()
    print(f"    {len(panel):,} rows / {panel['ticker'].nunique()} names "
          f"/ {time.time() - t0:.1f}s", flush=True)

    print("[B] splits ...", flush=True)
    splits, global_split = make_splits(panel)

    # v0 parity gate — did the re-derived panel drift from v0's published numbers?
    usable_all = panel[panel["live"] & panel["y_ok"]]
    main_hold = usable_all[(usable_all["board"] == "main") & (usable_all["date"] >= global_split)]
    cx_era = usable_all[(usable_all["board"] == "chinext")
                        & (usable_all["date"] >= CHINEXT_WIDE_DATE)]
    got = {
        "split_date": splits["global"]["split_date"],
        "fit_dates": splits["global"]["fit_dates"],
        "holdout_dates": splits["global"]["holdout_dates"],
        "main_holdout_base_rate_pct": round(100.0 * float(main_hold["y_limit_up"].mean()), 3),
        "main_holdout_rows": len(main_hold),
        "chinext_era_rows": len(cx_era),
        "chinext_era_split_date": splits.get("chinext", {}).get("split_date"),
        "main_limit_up_events": meta["limit_up_events_by_board"].get("main"),
        "chinext_limit_up_events": meta["limit_up_events_by_board"].get("chinext"),
        "star_limit_up_events": meta["limit_up_events_by_board"].get("star"),
    }
    checks = {}
    for k, want in V0_PARITY_TARGETS.items():
        if want is None:
            continue
        checks[k] = {"v0_published": want, "recomputed": got.get(k),
                     "match": bool(got.get(k) == want)}
    parity = {
        "purpose": ("This file re-derives v0's panel from scratch (v0 lives on a sibling "
                    "branch).  These are v0's PUBLISHED numbers vs this run's — the gate "
                    "that the feature definitions did not drift."),
        "checks": checks,
        "all_match": bool(all(c["match"] for c in checks.values())),
    }
    print(f"    v0 parity: {'ALL MATCH' if parity['all_match'] else 'MISMATCH — see JSON'}",
          flush=True)

    print("[C/D] fitting + evaluating per board ...", flush=True)
    by_board, ledger, live_top = {}, [], {}
    max_date = pd.Timestamp(panel["date"].max())

    for board in sorted(panel["board"].unique()):
        if board not in splits:
            continue
        sl = slice_board(panel, board, splits)
        gate = {
            "fit_core_rows": len(sl["fit_core"]),
            "fit_core_positives": int(sl["fit_core"]["y_limit_up"].sum()),
            "fit_calib_rows": len(sl["fit_calib"]),
            "fit_calib_positives": int(sl["fit_calib"]["y_limit_up"].sum()),
            "holdout_rows": len(sl["holdout"]),
            "holdout_positives": int(sl["holdout"]["y_limit_up"].sum()),
            "floors": {"fit_core_positives": MIN_FIT_CORE_POS,
                       "fit_calib_positives": MIN_CALIB_POS,
                       "holdout_positives": MIN_HOLDOUT_POS},
        }
        gate["passes"] = bool(
            gate["fit_core_positives"] >= MIN_FIT_CORE_POS
            and gate["fit_calib_positives"] >= MIN_CALIB_POS
            and gate["holdout_positives"] >= MIN_HOLDOUT_POS)
        # REGIME DIAGNOSTIC.  A frozen isotonic map inherits the base rate of the slice it
        # was fitted on.  If the calibration slice ran hotter or cooler than the holdout, the
        # map imports that difference as a level error no amount of feature quality can undo.
        # Computed on the FIT side and on the holdout's own realized rate — no refit.
        srb = {}
        for nm in ("fit_core", "fit_calib", "holdout"):
            g = sl[nm]
            srb[nm] = {"rows": len(g), "positives": int(g["y_limit_up"].sum()),
                       "base_rate_pct": round(100.0 * float(g["y_limit_up"].mean()), 4)
                       if len(g) else None}
        if srb["holdout"]["base_rate_pct"]:
            srb["calib_over_holdout_x"] = round(
                srb["fit_calib"]["base_rate_pct"] / srb["holdout"]["base_rate_pct"], 3)
            srb["fit_core_over_holdout_x"] = round(
                srb["fit_core"]["base_rate_pct"] / srb["holdout"]["base_rate_pct"], 3)
        srb["reading"] = (
            "calib_over_holdout_x is the level error the frozen calibration map carries "
            "before a single feature is considered.  A value far from 1.0 means the model's "
            "probabilities are quoted in the calibration slice's regime, not the holdout's."
        )
        entry = {"split": splits[board], "thin_gate": gate, "slice_base_rates": srb}
        if not gate["passes"]:
            entry["status"] = "THIN-SKIP — not modelled"
            entry["reason"] = (
                "Pre-registered events-per-variable floor not met.  A 9-parameter logistic "
                "fitted below this floor would be an overfit dressed as a probability.  "
                "Printed as a measured null, not silently downgraded to a smaller model."
            )
            by_board[board] = entry
            print(f"    {board}: THIN-SKIP "
                  f"(fit-core positives {gate['fit_core_positives']} < {MIN_FIT_CORE_POS})",
                  flush=True)
            continue

        b0 = fit_b0(sl["fit_all"])
        b1 = fit_b1(sl, DESIGN_COLS, "B1 six features + N dummies")
        b2 = fit_b2(sl)
        p1 = fit_b1(sl, ["f3_runup_5"], "P1 f3 alone")
        p2 = fit_b1(sl, ["f3_runup_5"] + N_DUMMIES, "P2 f3 + N dummies")

        hold = sl["holdout"].reset_index(drop=True)
        yv = hold["y_limit_up"].to_numpy(dtype=np.float64)
        preds = {
            "B0": apply_b0(hold, b0),
            "B1": apply_b1(hold, b1),
            "B1_uncalibrated": apply_b1(hold, b1, raw=True),
            "B2": apply_b2(hold, b2),
            "P1": apply_b1(hold, p1),
            "P2": apply_b1(hold, p2),
        }
        entry["status"] = "modelled"
        entry["models"] = {
            "B0": {k: v for k, v in b0.items() if not k.startswith("_")},
            "B1": {k: v for k, v in b1.items() if not k.startswith("_")},
            "B2": {k: v for k, v in b2.items() if not k.startswith("_")},
            "P1": {k: v for k, v in p1.items() if not k.startswith("_")},
            "P2": {k: v for k, v in p2.items() if not k.startswith("_")},
        }
        entry["holdout"] = {
            "rows": len(hold), "positives": int(yv.sum()),
            "base_rate_pct": round(100.0 * float(yv.mean()), 4),
            "dates": int(hold["date"].nunique()),
            "headline": {k: headline(yv, preds[k], preds["B0"]) for k in
                         ("B0", "B1", "B1_uncalibrated", "B2", "P1", "P2")},
            "reliability": {k: reliability(yv, preds[k]) for k in ("B0", "B1", "B2", "P2")},
            "per_year_skill": per_year_skill(hold, preds),
            "top_k": top_k_table(hold, preds, ["B1", "B0", "P1", "B2"]),
        }
        b1s = entry["holdout"]["headline"]["B1"]["brier_skill_vs_b0_pct"]
        print(f"    {board}: holdout {len(hold):,} rows, base "
              f"{entry['holdout']['base_rate_pct']:.3f}%, B1 skill vs ladder {b1s:+.3f}%",
              flush=True)

        # ── ledger: retro (last RETRO_DATES holdout feature-dates) + live stamp ──
        hdates = np.sort(hold["date"].unique())[-RETRO_DATES:]
        retro = hold[hold["date"].isin(hdates)]
        ledger += ledger_rows(retro, apply_b1(retro, b1), apply_b0(retro, b0),
                              "retro", stamped, LEDGER_TOP_N)

        era_start = pd.Timestamp(splits[board]["era_start"])
        livem = ((panel["board"] == board) & panel["live"] & panel["complete_case"]
                 & (panel["date"] == max_date) & (panel["date"] >= era_start))
        live = panel[livem].reset_index(drop=True)
        if len(live):
            lp1, lp0 = apply_b1(live, b1), apply_b0(live, b0)
            lrows = ledger_rows(live, lp1, lp0, "live", stamped, LEDGER_TOP_N)
            ledger += lrows
            live_top[board] = lrows[:5]
        entry["live_stamp"] = {
            "feature_date_T": max_date.strftime("%Y-%m-%d"),
            "predict_date": next_cn_session(max_date).strftime("%Y-%m-%d"),
            "candidates_scored": len(live),
            "rows_stamped": min(len(live), LEDGER_TOP_N),
            "retro_dates": [pd.Timestamp(d).strftime("%Y-%m-%d") for d in hdates[:1]]
                           + ["..."] + [pd.Timestamp(hdates[-1]).strftime("%Y-%m-%d")],
            "retro_rows": sum(1 for r in ledger if r["era"] == "retro"
                              and r["board"] == board),
        }
        by_board[board] = entry

    # deterministic ledger order
    ledger.sort(key=lambda r: (r["era"], r["feature_date_T"], r["board"],
                               -r["p_next_board"], r["ticker"]))
    OUT_LEDGER.write_text("".join(json.dumps(jsonable(r), ensure_ascii=False) + "\n"
                                  for r in ledger))
    print(f"[E] ledger -> {OUT_LEDGER.name}: {len(ledger)} rows "
          f"({sum(1 for r in ledger if r['era'] == 'live')} live)", flush=True)

    payload = {
        "instrument": "research/cn_prophet_audit/onset_calibration_v1.py",
        "program": "CN LIMIT-MOVE ALPHA — Wave 1 / lane L3 (calibrated onset model)",
        "predecessor": "research/cn_prophet_audit/limit_move_footprint_v0.py (PR #4999)",
        "tier": ("display/audit — MEASUREMENT ONLY.  Nothing here promotes, ranks for size, "
                 "gates, admits, or reaches a live surface."),
        "generated_utc": stamped,
        "runtime_sec": None,
        "solver": ("scikit-learn (LogisticRegression penalty=None lbfgs; IsotonicRegression)"
                   if SKLEARN else "numpy IRLS + PAVA fallback (sklearn unavailable)"),
        "preregistration": {
            "decided_before_the_first_run": [
                "the six features are v0's holdout survivors; NO new feature is introduced",
                "f2 stays a printed NULL and f5 stays retired-UNSTABLE",
                "B0 = the 连板 ladder is the skill target, fitted on the WHOLE fit window "
                "(more data than B1 gets) so the comparison is conservative in its favour",
                "isotonic is fitted on the last 15% of FIT dates, never on the holdout",
                "winsorisation and standardisation moments come from the fit CORE only",
                f"THIN gates: fit-core positives >= {MIN_FIT_CORE_POS} (EPV ~17 at 9 "
                f"parameters), calib positives >= {MIN_CALIB_POS}, holdout positives >= "
                f"{MIN_HOLDOUT_POS}",
                "ONE evaluation pass on the holdout; no refit, no tuning, no second look",
            ],
            "model_features": dict(MODEL_FEATURES),
            "retired_features": RETIRED_FEATURES,
            "n_categorical": f"连板 N at the feature bar, bucketed 0/1/2/{N_CAP}+ "
                             f"(N=0 is the reference level)",
        },
        "definitions": {
            "target": ("y = the name closes at the limit (PRIMARY definition) on its NEXT "
                       "USABLE bar.  One bar, H=1."),
            "feature_date_T": ("the bar whose close carries the features.  NOTE the naming: "
                               "v0 calls this bar T-1 and the graded bar T; the ledger schema "
                               "calls the feature bar feature_date_T and the graded bar "
                               "predict_date.  Same two bars, different labels."),
            "limit_up_close_PRIMARY": ("close >= round(prev_close*(1+w), 2) * "
                                       f"(1 - {LIMIT_CLOSE_TOL}) — v0's adjudicated primary."),
            "w": ("engine.china_microstructure.limit_width_for_date — star 20%, chinext 20% "
                  "on/after 2020-08-24 else 10%, main 10%, bse 30%"),
            "lianban_N": ("consecutive limit-up closes ending on the feature bar; any "
                          "non-limit bar, including an excluded one, resets it to 0"),
            "usable_pair": f"T and its next bar <= {MAX_PAIR_GAP_DAYS} calendar days apart, "
                           f"and the next bar itself not excluded",
            "brier_skill": "1 - Brier(model) / Brier(B0).  Positive = beats the ladder.",
            "reliability": ("holdout rows binned into deciles OF THE PREDICTED PROBABILITY; "
                            "each bin reports mean P-hat vs realized rate with a Wilson 95% "
                            "interval on the realized side"),
            "ece": "sum over bins of (n_bin/N) * |mean P-hat - realized rate|",
            "capture_share": ("share of a date's realized limit-ups that the top-K selection "
                              "contained, pooled over holdout dates"),
            "log_loss_clip": "predictions clipped to [1e-6, 1-1e-6] (isotonic emits exact 0)",
        },
        "exclusions": {
            "st_cohort": "all dates for every ticker in data/china_st/st_snapshot.parquet",
            "ipo_windows": (f"STAR/ChiNext first {CHINEXT_STAR_IPO_WINDOW} sessions; pre-2014 "
                            f"listings' first {PRE2014_IPO_WINDOW} session"),
            "exdiv_suspect": "|open - prev_close| / prev_close > 1.5*w",
            "zero_volume": "bars with volume <= 0 (suspension placeholders)",
            "universe_is_curated": (
                "THE BINDING COVERAGE FACT, inherited unchanged from v0: "
                "data/china_stocks_raw holds ~1,836 names against a listed A-share market of "
                "roughly 5,400, and the 打板 game lives disproportionately in the small-cap "
                "and ST names it omits.  Every probability here is calibrated ON and FOR that "
                "curated universe."),
            "survivorship": ("the store holds the CURRENT listed universe; delisted names are "
                             "absent.  For the ONSET (limit-UP) question this bias is milder "
                             "than for limit-down, but it is not zero: a name that ran, "
                             "collapsed and delisted contributes neither its run-ups nor its "
                             "failures."),
            "resolution_conditioned_denominator": (
                "usability at the next bar is a property of the NEXT bar, so conditioning on "
                "it is a filter a trader at the feature close could not apply.  It is applied "
                "uniformly to numerator and denominator; the probabilities are rates among "
                "USABLE next bars, not among all next bars."),
        },
        "meta": meta,
        "splits": splits,
        "v0_parity_gate": parity,
        "by_board": by_board,
        "forward_ledger": {
            "path": "research/cn_prophet_audit/onset_forward_ledger.jsonl",
            "rows": len(ledger),
            "rows_retro": sum(1 for r in ledger if r["era"] == "retro"),
            "rows_live": sum(1 for r in ledger if r["era"] == "live"),
            "live_feature_date_T": max_date.strftime("%Y-%m-%d"),
            "live_predict_date": next_cn_session(max_date).strftime("%Y-%m-%d"),
            "live_top5_by_board": live_top,
            "seed_write_semantics": (
                "This script writes the SEED file WHOLE (idempotent re-run, no duplicate "
                "appends).  From the Wave-2 nightly wiring onward the file is APPEND-ONLY and "
                "the nightly is its sole advancer."),
            "grading_spec": {
                "binary_outcome": ("limit-up CLOSE under the PRIMARY definition on the row's "
                                   "predict_date usable bar"),
                "recorded_alongside_never_blended": [
                    "realized next-close return",
                    "near-limit flag (return >= 0.95*w and not a limit close)",
                ],
                "ungradeable": ("a row whose predict_date bar is missing, excluded, or more "
                                "than 10 calendar days later grades UNGRADEABLE, not 0 — "
                                "scoring a suspension as a miss would manufacture skill"),
                "predict_date_resolution": ("re-resolve predict_date against the store at "
                                            "grading time; rows stamped "
                                            "next_weekday_calendar_estimate have not had a "
                                            "holiday calendar applied"),
                "append_only": True,
                "sole_advancer": "nightly (Wave 2)",
            },
        },
        "nightly_hook_proposal": {
            "status": "PROPOSAL ONLY — nothing wired in this PR",
            "workflow": ".github/workflows/asia-close.yml",
            "insert_after": ("the 'CN Pick Lab — fire books + grade + render (CNPL-R8 asia "
                             "lane)' step"),
            "why_there": (
                "asia-close is the CN lane and the sole owner of the CN data plane: "
                "data/china_stocks_raw is written by its 'collect China/HK data' step "
                "(collectors/china_stock_raw.py via scripts/collect.py) BEFORE the builder "
                "bands, so tonight's feature bar is on disk by the time the Pick Lab step "
                "runs.  The CN Pick Lab is the exact structural analogue — a fire book plus a "
                "grade pass over an append-only jsonl — so the ledger inherits a proven "
                "pattern rather than inventing one."),
            "gate": ("reuse the CN_LANE=asia environment gate (CNPL-R8): the asia lane is the "
                     "ONLY lane permitted to advance the ledger; render/intraday lanes leave "
                     "CN_LANE unset and the writer must refuse.  This is the house law that "
                     "nightly is the sole advancer of forward ledgers, made executable."),
            "commit_path": ("the existing 'commit engine outputs' step already git-adds data/ "
                            "and site/.  research/ is NOT in that add, so Wave 2 must either "
                            "relocate the ledger under data/cn_limit_onset/ (recommended — it "
                            "is an operational ledger, not a research document) or extend the "
                            "add.  Flagged as a Wave-2 decision, not taken here."),
            "never_break_contract": ("wrap in the same 'exit 0 + ::error annotation' shape the "
                                     "Pick Lab steps use, so a ledger failure never reds the "
                                     "CN lane"),
            "budget": "one panel build ~35s + inference; comfortably inside the asia lane",
        },
        "what_this_does_NOT_establish": [
            "NO significance claim.  Limit-ups cluster hard in time and cross-section, so a "
            "naive interval on any cell here is understated.  The evidence offered is skill "
            "and calibration on a frozen holdout, plus per-year stability — not a p-value.",
            "Lift is not probability.  A 3x lift on a ~1.2% base is ~3.7%: the modelled event "
            "still does not happen ~96% of the time in the very best bucket.",
            "Calibration is IN-UNIVERSE.  The probabilities are calibrated for the curated "
            "~1,836-name store, not for the A-share market, and the 打板 game is denser in the "
            "names the store omits.",
            "It says nothing about FILLABILITY.  P is for a limit-up CLOSE; a name that gaps "
            "straight to the limit at the open is unfillable and still scores as a hit.  That "
            "is the rider lane's question and it is deliberately not smuggled in here.",
            "It says nothing about the CONTINUATION side.  N is an input, not the subject; "
            "P(next board | already N boards) empirics belong to lane L1.",
            "Survivorship and the current-membership sector map are unfixed with the stores we "
            "hold, and both are stated rather than patched.",
            "Nothing is promoted.  The gauntlet is a promotion gate; this is display tier and "
            "no key is being escalated.",
        ],
        "ore_ledger": [
            {"ore": "regime / market-state features (breadth, index trend, limit-up count "
                    "level, volatility state)",
             "status": "UNTESTED — lane L2 owns the instruments",
             "why_it_could_matter": "the per-year skill table is the direct evidence that the "
                                    "onset base rate is regime-dependent; a model that cannot "
                                    "see the regime is spending its capacity re-learning it",
             "next": "Wave-2 merge of L2's regime instruments as B1 covariates"},
            {"ore": "gradient boosting / non-linear interactions",
             "status": "UNTESTED — deliberately not attempted in v1",
             "why_it_could_matter": "B2's bucket model is a 2-way interaction by hand; if B2 "
                                    "beats B1 anywhere, the linear form is leaving structure "
                                    "on the table",
             "next": "only after the linear baseline is a published, graded ledger — a boosted "
                     "tree on a 1% event with no forward record is unauditable"},
            {"ore": "f3 x f4 crosses (run-up conditioned on cohort heat)",
             "status": "UNTESTED",
             "why_it_could_matter": "the practitioner reading is that a run-up INSIDE a hot "
                                    "sector is a different object from a lone run-up; the "
                                    "linear model cannot express that",
             "next": "explicit cross term, pre-registered, evaluated on the same frozen split"},
            {"ore": "per-name effects (name-level base rate / random intercept)",
             "status": "UNTESTED — v0 measured that per-name estimation is starved at this "
                       "base rate (652 of 1,243 main names qualify at its floors)",
             "why_it_could_matter": "onset propensity is plainly not uniform across names",
             "next": "partial pooling (shrunk per-name intercept) rather than per-name fits"},
            {"ore": "continuation-side model (P(board | already N boards))",
             "status": "OUT OF SCOPE — lane L1 owns those empirics",
             "why_it_could_matter": "the ladder is the strongest single conditioner in the "
                                    "data and it is here only as a benchmark input",
             "next": "L1's results merge as a sibling model, never as a pooled one"},
            {"ore": "zt_pool-universe scoring (the ~1,256 limit-up names our store lacks)",
             "status": "UNTESTED — blocked on universe coverage, not on method",
             "why_it_could_matter": "the omitted names are where the game is densest; every "
                                    "number here may be a large-cap special case",
             "next": "extend data/china_stocks_raw coverage, then re-fit and compare"},
            {"ore": "near-limit as a SOFT label (partial credit for a 9.6% close)",
             "status": "UNTESTED",
             "why_it_could_matter": "the binary target throws away the distinction between a "
                                    "miss at +2% and a miss at +9.8%, which is most of the "
                                    "information in a near-miss",
             "next": "ordinal or two-stage target; grade the binary in parallel so the "
                     "published ledger stays comparable"},
            {"ore": "longer horizons H > 1 (a board within the next 3 / 5 sessions)",
             "status": "UNTESTED",
             "why_it_could_matter": "H=1 is the hardest possible framing and may be why the "
                                    "absolute probabilities stay small",
             "next": "same features, H in {2,3,5}, same frozen split; overlapping windows make "
                     "the dependence worse, so state it before measuring"},
            {"ore": "isotonic thinness on the thinner boards",
             "status": "MEASURED HERE — see models.B1.fit_calib_positives and isotonic_knots "
                       "per board",
             "why_it_could_matter": "an isotonic map fitted on a few hundred positives is "
                                    "lumpy and can itself be the source of a reliability bend",
             "next": "compare against Platt/beta calibration on the same slice; report both"},
        ],
    }
    payload["runtime_sec"] = round(time.time() - t0, 1)
    OUT_JSON.write_text(json.dumps(jsonable(payload), indent=2, ensure_ascii=False) + "\n")
    print(f"[done] {payload['runtime_sec']:.1f}s -> {OUT_JSON.name}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
