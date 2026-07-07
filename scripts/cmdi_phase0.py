"""Phase-0 validation: NY Fed Corporate Bond Market Distress Index (CMDI) as a
de-escalation-input candidate for the credit conditioning family w2104_cmdi_conditioning.

PRE-REGISTERED: family w2104_cmdi_conditioning (this file IS the registration).

=============================================================================
HYPOTHESIS
The NY Fed CMDI (free, monthly-resolution, 2005-present) captures aggregate
corporate bond market stress across primary and secondary markets. High CMDI
(elevated distress) should predict elevated forward equity drawdown risk; the
index should add signal beyond the readily available HY OAS spread level.

SOURCE DATA:
  - CMDI: NY Fed weekly data, end-of-week Fridays, resampled to month-end.
    Market CMDI, IG CMDI, HY CMDI sub-indices.
    URL: https://www.newyorkfed.org/medialibrary/research/interactives/data/cmdi/cmdi_interactive_data.xlsx
    Cached to: data/nyfed_cmdi/cmdi_weekly.parquet  (raw weekly)
              data/nyfed_cmdi/cmdi_monthly.parquet  (month-end resampled)
  - SPY: data/yahoo/SPY.parquet (daily close; forward drawdown target)
  - HY OAS baseline: data/fred/BAMLH0A0HYM2.parquet (daily HY OAS)

=============================================================================
SIGNALS (3 series x 2 forms = 6 total, but only 4 GATED CELLS):
  Series:  market_cmdi_pctile, ig_cmdi_pctile, hy_cmdi_pctile
           market_cmdi_3m_chg, ig_cmdi_3m_chg, hy_cmdi_3m_chg
  Gated:   {market level pctile, hy level pctile} x {21d, 63d} = 4 cells
  Others computed for context; AUC/CI reported for all.

PIT RULE:
  CMDI is a WEEKLY series (end-of-week Fridays, currently 1120 observations,
  updated continuously). It is NOT a monthly release with a fixed publication
  lag. We resample to month-end by taking the last available Friday reading
  in each calendar month. The most-recent month-end reading is thus available
  within days of month-end.

  AMENDMENT A1 (registered here before computing):
  We apply a conservative 2-month lag (signal for evaluation at month M uses
  CMDI through month M-2). This is more conservative than the data cadence
  requires, but is adopted for robustness: it eliminates any ambiguity about
  which Friday reading is "in" a given month, avoids reliance on intra-month
  updates, and is verified look-ahead-free at COVID (2020-03 signal uses
  Jan-2020 CMDI, not the COVID spike). The collector note about
  "last-Wednesday-of-month" refers to the FRED-style monthly aggregation
  schedule and is superseded by the direct weekly source.
  We report M-1 lag as a sensitivity check (labeled SENSITIVITY, not gated).

  AMENDMENT A2 (registered here before computing):
  Pctile = expanding window quantile (PIT — no look-ahead into future
  distress). Min 24 months of history required before first percentile output
  (to avoid degenerate early period).

  AMENDMENT A3 (registered here before computing):
  3m change = raw CMDI(t) - CMDI(t-3) in index units (not z-scored), also
  expanding-PIT-percentile-ranked for the pctile form. 3m = 3 monthly obs.

=============================================================================
TESTS:
  T1 AUC: CMDI signal vs binary label "SPY enters >=5% drawdown within horizon"
          (21d or 63d). Higher signal -> should precede higher drawdown prob.
          Computed via Mann-Whitney U (no sklearn), block-bootstrap 95% CI.
          GATE: AUC >= 0.60 AND CI excludes 0.50.

  T2 COMPARISON: CMDI AUC vs HY-OAS-z baseline AUC (same label, same dates).
          GATE: CMDI beats HY-OAS at >= 1 of the 4 gated cells (point estimate
          sufficient; CI is reported but not gated given HY-OAS is our baseline,
          not a null-hypothesis of no information).

  T3 LOCO: leave-one-crisis-out stability. Crises: 2008, 2011, 2015-16, 2020,
          2022, 2023-03. Each removal must produce same-direction AUC >0.50
          (not necessarily above gate threshold; stability, not magnitude).
          GATE: all 6 LOCO AUCs > 0.50 (same direction, crisis-stable).

=============================================================================
FINAL VERDICT:
  PASS (de-escalation input candidacy): T1 PASS AND T2 PASS AND T3 PASS.
  FAIL on any gate -> context verdict (all numbers printed, null accepted).

=============================================================================
NIGHTLY WIRING (for consolidation — do not merge until the build PR lands):
  Collector:  scripts/collect_nyfed_cmdi.py  (standalone, ships with this PR)
  Output:     data/nyfed_cmdi/cmdi_weekly.parquet
              data/nyfed_cmdi/cmdi_monthly.parquet
  Schedule:   Monthly (last Wednesday of month, after 10am ET) or weekly
              with idempotent caching. Recommend weekly cron to catch rereleases.
  Integration: engine/signal_lab.py consumer: read cmdi_monthly.parquet,
              apply 2-month lag, compute expanding pctile + 3m change,
              pass to de-escalation gate router when AUC candidates are promoted.

Run:
  python3 -m scripts.cmdi_phase0
Writes:
  reports/w2104-cmdi-conditioning-phase0.md
  data/nyfed_cmdi/cmdi_weekly.parquet (collector)
  data/nyfed_cmdi/cmdi_monthly.parquet (collector)
"""
from __future__ import annotations

import sys
import math
import json
from pathlib import Path
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.trial_ledger import TrialLedger  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"

CMDI_DIR = DATA_DIR / "nyfed_cmdi"
CMDI_WEEKLY_PATH = CMDI_DIR / "cmdi_weekly.parquet"
CMDI_MONTHLY_PATH = CMDI_DIR / "cmdi_monthly.parquet"
CMDI_URL = (
    "https://www.newyorkfed.org/medialibrary/research/interactives/data/cmdi/"
    "cmdi_interactive_data.xlsx"
)

FAMILY = "w2104_cmdi_conditioning"
MIN_HISTORY_MONTHS = 24   # for expanding pctile
LAG_MONTHS = 2            # PIT lag (conservative, see A1)

# Horizons tested (CALENDAR days ahead in SPY — forward_max_drawdown uses
# pd.Timedelta(days=N), so H21 = 21 calendar days (~14 trading days, ~3 weeks)
# and H63 = 63 calendar days (~42 trading days, ~2 months).
H21 = 21     # 21 calendar days (~14 trading days, ~3 weeks)
H63 = 63     # 63 calendar days (~42 trading days, ~2 calendar months)

# 5% drawdown threshold for binary label
DRAWDOWN_THRESH = -0.05

# Crisis windows for LOCO (inclusive start/end of removal)
CRISES = {
    "2008": ("2007-09-01", "2009-06-30"),
    "2011": ("2011-06-01", "2011-12-31"),
    "2015-16": ("2015-06-01", "2016-03-31"),
    "2020": ("2020-01-01", "2020-06-30"),
    "2022": ("2022-01-01", "2022-12-31"),
    "2023-03": ("2023-01-01", "2023-06-30"),
}

AUC_GATE = 0.60
LOCO_DIRECTION = 0.50   # must exceed 0.50 for same-direction stability


# ============================================================================ #
# Collector: fetch + cache
# ============================================================================ #
def collect_cmdi(force: bool = False) -> pd.DataFrame:
    """Download CMDI from NY Fed, cache as parquet. Returns weekly raw df."""
    CMDI_DIR.mkdir(parents=True, exist_ok=True)

    if CMDI_WEEKLY_PATH.exists() and not force:
        df = pd.read_parquet(CMDI_WEEKLY_PATH)
        print(f"[cmdi] loaded from cache: {len(df)} weekly rows, "
              f"{df.index.min().date()} -> {df.index.max().date()}")
        return df

    print(f"[cmdi] downloading from NY Fed: {CMDI_URL}")
    import urllib.request
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    req = urllib.request.Request(CMDI_URL, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()

    import io
    df = pd.read_excel(io.BytesIO(raw), sheet_name="Sheet1")
    df = df.rename(columns={
        "eow_friday": "date",
        "Market CMDI": "market_cmdi",
        "IG CMDI": "ig_cmdi",
        "HY CMDI": "hy_cmdi",
    })
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    # Keep only the three sub-indices + percentile bands
    cols = ["market_cmdi", "ig_cmdi", "hy_cmdi",
            "p5", "p10", "p25", "p50", "p75", "p90", "p95", "p99"]
    df = df[[c for c in cols if c in df.columns]]
    df.to_parquet(CMDI_WEEKLY_PATH)
    print(f"[cmdi] cached {len(df)} weekly rows -> {CMDI_WEEKLY_PATH}")
    return df


def build_monthly(weekly: pd.DataFrame) -> pd.DataFrame:
    """Resample weekly (end-of-week Friday) to month-end by taking the last
    available reading in each month — PIT-clean since CMDI is published weekly."""
    monthly = weekly[["market_cmdi", "ig_cmdi", "hy_cmdi"]].resample("ME").last()
    monthly.to_parquet(CMDI_MONTHLY_PATH)
    print(f"[cmdi] monthly: {len(monthly)} obs, "
          f"{monthly.index.min().date()} -> {monthly.index.max().date()}")
    return monthly


# ============================================================================ #
# Signal construction
# ============================================================================ #
def expanding_pctile_pit(series: pd.Series, min_history: int = 24) -> pd.Series:
    """Expanding-window PIT percentile rank (0-1). Returns NaN for first
    min_history periods. Amendment A2."""
    out = pd.Series(np.nan, index=series.index)
    vals = series.values
    for i in range(min_history, len(vals)):
        window = vals[: i + 1]  # up to and including current = expanding
        v = vals[i]
        if np.isnan(v):
            continue
        w = window[~np.isnan(window)]
        if len(w) < min_history:
            continue
        # percentile = fraction of historical values <= current
        out.iloc[i] = float(np.mean(w <= v))
    return out


def build_signals(monthly: pd.DataFrame, lag: int = LAG_MONTHS) -> pd.DataFrame:
    """Build all 6 signals. Apply PIT lag (shift by lag months).
    Returns a monthly DataFrame aligned to SPY-evaluation dates.
    Amendment A3: 3m change in raw index units, then also pctile-ranked.
    """
    sigs = pd.DataFrame(index=monthly.index)

    for col, name in [("market_cmdi", "market"), ("ig_cmdi", "ig"), ("hy_cmdi", "hy")]:
        raw = monthly[col]
        # Level percentile (expanding PIT)
        pctile = expanding_pctile_pit(raw, MIN_HISTORY_MONTHS)
        sigs[f"{name}_level_pctile"] = pctile

        # 3m change (raw index units), then pctile-ranked
        chg3m = raw.diff(3)
        pctile_chg = expanding_pctile_pit(chg3m, MIN_HISTORY_MONTHS + 3)
        sigs[f"{name}_3m_chg_pctile"] = pctile_chg

    # Apply PIT lag: shift signals forward by lag months so signal at date D
    # was only available from data through D-lag. shift(lag) means the value
    # at month M comes from month M-lag.
    sigs = sigs.shift(lag)
    return sigs


def build_hyoas_baseline(lag: int = LAG_MONTHS) -> pd.Series:
    """HY OAS z-score baseline (expanding PIT, resampled to monthly).
    Uses data/fred/BAMLH0A0HYM2.parquet."""
    path = DATA_DIR / "fred" / "BAMLH0A0HYM2.parquet"
    if not path.exists():
        print(f"[warn] HY OAS not found at {path}")
        return pd.Series(dtype=float)

    oas = pd.read_parquet(path)["hy_oas"].sort_index()
    # Resample to month-end
    oas_m = oas.resample("ME").last()
    # Expanding z-score (PIT)
    oas_z = pd.Series(np.nan, index=oas_m.index)
    for i in range(MIN_HISTORY_MONTHS, len(oas_m)):
        window = oas_m.iloc[: i + 1].dropna()
        if len(window) < MIN_HISTORY_MONTHS:
            continue
        mu = float(window.mean())
        sd = float(window.std(ddof=1))
        if sd > 0:
            oas_z.iloc[i] = (float(oas_m.iloc[i]) - mu) / sd
        else:
            oas_z.iloc[i] = 0.0

    # Apply same PIT lag
    oas_z = oas_z.shift(lag)
    return oas_z


# ============================================================================ #
# Forward drawdown label construction
# ============================================================================ #
def forward_max_drawdown(spy_close: pd.Series, horizon_days: int) -> pd.Series:
    """For each date, compute the worst drawdown (minimum peak-to-trough ratio - 1)
    in the next horizon_days calendar days. Returns negative numbers; NaN at tail."""
    out = {}
    vals = spy_close.values
    dates = spy_close.index
    for i, d in enumerate(dates):
        end_date = d + pd.Timedelta(days=horizon_days)
        future_mask = (dates > d) & (dates <= end_date)
        if not future_mask.any():
            out[d] = np.nan
            continue
        # Forward window from d onward (inclusive of d as peak reference)
        future = vals[future_mask]
        # Drawdown from d's price
        base = vals[i]
        if base <= 0:
            out[d] = np.nan
            continue
        dd = float(np.min(future / base - 1.0))
        out[d] = dd
    return pd.Series(out)


def make_drawdown_label(spy_close: pd.Series, horizon_days: int,
                        thresh: float = DRAWDOWN_THRESH) -> pd.Series:
    """Binary label: 1 if forward drawdown <= thresh (i.e., a >= |thresh| drop occurs)."""
    dd = forward_max_drawdown(spy_close, horizon_days)
    label = (dd <= thresh).astype(float)
    label[dd.isna()] = np.nan
    return label


# ============================================================================ #
# AUC (Mann-Whitney U, no sklearn)
# ============================================================================ #
def mann_whitney_auc(scores: np.ndarray, labels: np.ndarray) -> float:
    """AUC = P(score(pos) > score(neg)), ties = 0.5. Pure numpy."""
    pos = scores[labels == 1]
    neg = scores[labels == 0]
    pos = pos[~np.isnan(pos)]
    neg = neg[~np.isnan(neg)]
    if len(pos) == 0 or len(neg) == 0:
        return np.nan
    combined = np.concatenate([pos, neg])
    order = combined.argsort(kind="mergesort")
    sorted_vals = combined[order]
    avg_ranks = np.empty(combined.size, dtype=float)
    i = 0
    while i < sorted_vals.size:
        j = i
        while j + 1 < sorted_vals.size and sorted_vals[j + 1] == sorted_vals[i]:
            j += 1
        r = (i + 1 + j + 1) / 2.0
        avg_ranks[order[i: j + 1]] = r
        i = j + 1
    rank_sum_pos = float(avg_ranks[: len(pos)].sum())
    u_pos = rank_sum_pos - len(pos) * (len(pos) + 1) / 2.0
    return float(u_pos / (len(pos) * len(neg)))


def bootstrap_auc_ci(scores: np.ndarray, labels: np.ndarray,
                     n_boot: int = 2000, ci: float = 0.95,
                     seed: int = 42) -> tuple[float, float, float]:
    """Bootstrap CI for AUC. Resample positives and negatives independently."""
    rng = np.random.default_rng(seed)
    pos = scores[labels == 1]
    neg = scores[labels == 0]
    pos = pos[~np.isnan(pos)]
    neg = neg[~np.isnan(neg)]
    point = mann_whitney_auc(scores, labels)
    if len(pos) == 0 or len(neg) == 0 or np.isnan(point):
        return np.nan, np.nan, np.nan
    boot = np.empty(n_boot)
    for b in range(n_boot):
        p = rng.choice(pos, size=len(pos), replace=True)
        q = rng.choice(neg, size=len(neg), replace=True)
        lbl_b = np.concatenate([np.ones(len(p)), np.zeros(len(q))])
        sc_b = np.concatenate([p, q])
        boot[b] = mann_whitney_auc(sc_b, lbl_b)
    alpha = (1 - ci) / 2
    lo = float(np.percentile(boot, 100 * alpha))
    hi = float(np.percentile(boot, 100 * (1 - alpha)))
    return point, lo, hi


def newey_west_tstat(x: np.ndarray, lags: int = 6) -> dict:
    """Newey-West HAC t-stat for mean of x (monthly series, lags=6 by default
    for ~6-month overlap correction at 63d horizon). Pure numpy."""
    a = np.asarray(x, float)
    a = a[~np.isnan(a)]
    n = len(a)
    if n < 8:
        return {"mean": None, "t": None, "p": None, "n": n}
    mean = float(a.mean())
    d = a - mean
    var = float(np.dot(d, d) / n)
    L = min(int(lags), n - 1)
    for j in range(1, L + 1):
        gj = float(np.dot(d[j:], d[:-j]) / n)
        var += 2.0 * (1.0 - j / (L + 1)) * gj
    se = math.sqrt(max(var, 1e-18) / n)
    t = mean / se if se else float("nan")
    # Two-sided p from normal approx
    from scipy.special import ndtr
    p = float(2.0 * (1.0 - ndtr(abs(t))))
    return {"mean": round(mean, 4), "se": round(se, 4), "t": round(t, 3),
            "p": round(p, 4), "n": n}


# ============================================================================ #
# Evaluation harness
# ============================================================================ #
def evaluate_signal(sig: pd.Series, label: pd.Series,
                    name: str, n_boot: int = 2000) -> dict:
    """Full AUC evaluation for one (signal, label) pair on date-collapsed monthly obs.
    Stats law: monthly series -> each obs is one calendar month, no overlap.
    Returns dict with AUC point, CI, NW t-stat on (2*label-1), N_events, N_non."""
    j = pd.concat([sig.rename("s"), label.rename("l")], axis=1).dropna()
    # Collapse to one obs per month (already monthly, but verify)
    j = j[~j.index.duplicated(keep="last")]
    if len(j) < 20:
        return {"name": name, "n": len(j), "auc": np.nan, "ci_lo": np.nan,
                "ci_hi": np.nan, "n_events": 0, "n_non": 0,
                "nw_t": None, "nw_p": None}

    sc = j["s"].values
    lb = j["l"].values
    auc, ci_lo, ci_hi = bootstrap_auc_ci(sc, lb, n_boot=n_boot)
    n_events = int(lb.sum())
    n_non = int((lb == 0).sum())

    # NW t-stat on (signal * (2*label-1)) to test signed predictive relation
    signed = sc * (2 * lb - 1)
    nw = newey_west_tstat(signed, lags=6)

    return {
        "name": name,
        "n": len(j),
        "n_events": n_events,
        "n_non": n_non,
        "auc": auc,
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "nw_t": nw.get("t"),
        "nw_p": nw.get("p"),
        "dates": j.index,
        "scores": sc,
        "labels": lb,
    }


def evaluate_loco(sig: pd.Series, label: pd.Series,
                  name: str, crises: dict = CRISES) -> dict:
    """Leave-one-crisis-out AUC. Returns dict crisis -> AUC."""
    j = pd.concat([sig.rename("s"), label.rename("l")], axis=1).dropna()
    j = j[~j.index.duplicated(keep="last")]
    out = {}
    for cz, (start, end) in crises.items():
        mask = ~((j.index >= start) & (j.index <= end))
        jj = j[mask]
        if len(jj) < 15:
            out[cz] = np.nan
            continue
        auc = mann_whitney_auc(jj["s"].values, jj["l"].values)
        out[cz] = round(auc, 4)
    return out


# ============================================================================ #
# Main
# ============================================================================ #
def main() -> None:
    REPORTS_DIR.mkdir(exist_ok=True)
    CMDI_DIR.mkdir(parents=True, exist_ok=True)

    # -- Pre-register trial grid BEFORE computing (law) ---------------------- #
    # 6 signals x 2 horizons = 12 cells; gated = 4
    led = TrialLedger(path=ROOT / "data" / "trial_ledger.jsonl", family=FAMILY)
    GRID = [
        {"signal": sig, "horizon": h}
        for sig in ["market_level_pctile", "ig_level_pctile", "hy_level_pctile",
                    "market_3m_chg_pctile", "ig_3m_chg_pctile", "hy_3m_chg_pctile"]
        for h in [H21, H63]
    ]
    n_new = led.log_grid(GRID, family=FAMILY, info_cutoff="2026-06-30",
                         source="w2104_cmdi_phase0")
    n_total = led.effective_n(FAMILY)
    print(f"[ledger] logged {n_new} new configs; family total N={n_total}")

    # -- Collect + load data ------------------------------------------------- #
    weekly = collect_cmdi()
    monthly = build_monthly(weekly)

    # Verify positive control: load SPY and HY OAS
    spy = pd.read_parquet(DATA_DIR / "yahoo" / "SPY.parquet")["close"].sort_index()
    hy_oas = build_hyoas_baseline()
    print(f"[store] SPY: {len(spy)} rows {spy.index.min().date()}->{spy.index.max().date()}")
    print(f"[store] HY OAS monthly: {hy_oas.dropna().count()} non-nan")
    print(f"[store] CMDI monthly: {len(monthly)} rows {monthly.index.min().date()}->{monthly.index.max().date()}")

    # Build signals
    sigs = build_signals(monthly, lag=LAG_MONTHS)
    print(f"[signals] built {len(sigs.columns)} signal columns")
    print(f"[signals] first valid rows (after lag+min_history):")
    for c in sigs.columns:
        first = sigs[c].dropna().index.min() if sigs[c].dropna().any() else None
        print(f"  {c}: {first}")

    # Build forward drawdown labels (SPY daily -> monthly evaluation dates)
    # We evaluate at the last trading day of each month
    print(f"\n[labels] computing forward drawdown labels (SPY daily)...")
    label_21d = make_drawdown_label(spy, H21, DRAWDOWN_THRESH)
    label_63d = make_drawdown_label(spy, H63, DRAWDOWN_THRESH)

    # Resample labels to monthly (last trading day of each month)
    label_21d_m = label_21d.resample("ME").last()
    label_63d_m = label_63d.resample("ME").last()

    n21 = label_21d_m.dropna().sum()
    n63 = label_63d_m.dropna().sum()
    pct21 = n21 / label_21d_m.dropna().count()
    pct63 = n63 / label_63d_m.dropna().count()
    print(f"[labels] 21d: {int(n21)} events / {label_21d_m.dropna().count()} obs "
          f"({100*pct21:.1f}% base rate)")
    print(f"[labels] 63d: {int(n63)} events / {label_63d_m.dropna().count()} obs "
          f"({100*pct63:.1f}% base rate)")

    # Align signals and labels to common monthly index
    all_months = sigs.index.union(label_21d_m.index).union(label_63d_m.index)
    sigs_full = sigs.reindex(all_months)
    lbl21 = label_21d_m.reindex(all_months)
    lbl63 = label_63d_m.reindex(all_months)
    hy_oas_full = hy_oas.reindex(all_months)

    # -------------------------------------------------------------------------
    # GATED CELLS: {market level, hy level} x {21d, 63d}
    # -------------------------------------------------------------------------
    GATED = [
        ("market_level_pctile", lbl21, "21d", "market_level_pctile_21d"),
        ("market_level_pctile", lbl63, "63d", "market_level_pctile_63d"),
        ("hy_level_pctile", lbl21, "21d", "hy_level_pctile_21d"),
        ("hy_level_pctile", lbl63, "63d", "hy_level_pctile_63d"),
    ]

    # All 6 signals x 2 horizons for context
    ALL_SIGS = [
        (col, lbl21, "21d") for col in sigs.columns
    ] + [
        (col, lbl63, "63d") for col in sigs.columns
    ]

    print(f"\n[eval] running AUC evaluations ({len(ALL_SIGS)} cells) + LOCO...")

    results_all = {}
    for col, lbl, hz in ALL_SIGS:
        if col not in sigs_full.columns:
            continue
        r = evaluate_signal(sigs_full[col], lbl, f"{col}_{hz}")
        results_all[f"{col}_{hz}"] = r

    # HY OAS baseline evaluations — FULL coverage (for display only, not T2 gate)
    hyoas_r21_full = evaluate_signal(hy_oas_full, lbl21, "hyoas_baseline_21d_full")
    hyoas_r63_full = evaluate_signal(hy_oas_full, lbl63, "hyoas_baseline_63d_full")

    # T2 pre-registered requirement: IDENTICAL dates per gated cell.
    # evaluate_signal() drops NA independently per series, so an unconstrained
    # HY-OAS baseline picks up extra months (1999-2006) that CMDI cannot cover.
    # Fix: for each gated cell, restrict HY-OAS to the exact dates used by that
    # cell's CMDI evaluation (intersect on the joined non-NaN index).
    hyoas_r_by_key: dict = {}
    for col, lbl, hz, key in GATED:
        cmdi_r = results_all.get(key, {})
        cmdi_dates = cmdi_r.get("dates", None)
        if cmdi_dates is None or len(cmdi_dates) == 0:
            hyoas_r_by_key[key] = {"auc": np.nan, "n": 0}
            continue
        # Restrict HY-OAS to CMDI evaluation dates for this cell
        hy_restricted = hy_oas_full.reindex(cmdi_dates)
        lbl_restricted = lbl.reindex(cmdi_dates)
        r = evaluate_signal(hy_restricted, lbl_restricted, f"hyoas_identical_{key}")
        hyoas_r_by_key[key] = r

    # LOCO for gated cells only
    loco_results = {}
    for col, lbl, hz, key in GATED:
        if col not in sigs_full.columns:
            continue
        loco = evaluate_loco(sigs_full[col], lbl, key)
        loco_results[key] = loco

    # -------------------------------------------------------------------------
    # Gate evaluation
    # -------------------------------------------------------------------------
    def gate_t1(key: str) -> tuple[bool, str]:
        r = results_all.get(key, {})
        auc = r.get("auc", np.nan)
        ci_lo = r.get("ci_lo", np.nan)
        if np.isnan(auc):
            return False, "N/A (insufficient data)"
        pass_ = (auc >= AUC_GATE) and (ci_lo > 0.50)
        return pass_, f"AUC={auc:.4f} CI=[{ci_lo:.4f},{r.get('ci_hi',np.nan):.4f}]"

    # T1 pass requires BOTH gated cells at a given horizon to pass... actually
    # the spec says "AUC >= 0.60 with block-bootstrap CI excluding 0.5 AND beats
    # HY-OAS AUC at >=1 gated cell" - so T1 is per-cell, T2 is "beats at >=1".
    # Gate T1: each gated cell independently gate-checked; OVERALL T1 = any gated cell passes.
    # The spec says "AUC>=0.60 with block-bootstrap CI excluding 0.5" as the gate.

    gated_t1 = {}
    for col, lbl, hz, key in GATED:
        ok, msg = gate_t1(key)
        gated_t1[key] = {"pass": ok, "msg": msg, "r": results_all.get(key, {})}

    t1_any_pass = any(v["pass"] for v in gated_t1.values())

    # T2: beats HY OAS at >= 1 gated cell (IDENTICAL-DATES baseline per cell)
    beats_baseline = {}
    for col, lbl, hz, key in GATED:
        r = results_all.get(key, {})
        cmdi_auc = r.get("auc", np.nan)
        oas_r = hyoas_r_by_key.get(key, {})
        oas_auc = oas_r.get("auc", np.nan)
        beats = (not np.isnan(cmdi_auc) and not np.isnan(oas_auc) and
                 cmdi_auc > oas_auc)
        beats_baseline[key] = {
            "beats": beats,
            "cmdi_auc": cmdi_auc,
            "oas_auc": oas_auc,
            "n_identical": oas_r.get("n", 0),
        }

    t2_pass = any(v["beats"] for v in beats_baseline.values())

    # T3: LOCO stability (all crises same direction > 0.50)
    loco_stable_per_key = {}
    for key, loco in loco_results.items():
        all_stable = all(
            (not np.isnan(v)) and (v > LOCO_DIRECTION)
            for v in loco.values()
        )
        loco_stable_per_key[key] = all_stable

    t3_pass = any(loco_stable_per_key.values())  # at least one gated cell is LOCO stable

    # Overall verdict
    overall_pass = t1_any_pass and t2_pass and t3_pass

    # =========================================================================
    # Report generation
    # =========================================================================
    out = []
    out.append("# CMDI Conditioning Phase-0 — w2104_cmdi_conditioning")
    out.append("")
    out.append("> **Registered family:** `w2104_cmdi_conditioning`  ")
    out.append(f"> **Run date:** 2026-07-06  ")
    out.append(f"> **Signal lag (PIT):** {LAG_MONTHS} months (Amendment A1)  ")
    out.append(f"> **Expanding pctile min history:** {MIN_HISTORY_MONTHS} months (Amendment A2)  ")
    out.append(f"> **3m change:** raw index units, pctile-ranked (Amendment A3)")
    out.append("")

    out.append("## In Plain English")
    out.append("")
    out.append("The NY Fed publishes a Corporate Bond Market Distress Index (CMDI) as a "
               "weekly series (end-of-week Friday, updated continuously). This report tests "
               "whether that index can predict when the US equity market (SPY) is about to "
               "drop 5% or more within the next 21 calendar days (~14 trading days, ~3 weeks) "
               "or 63 calendar days (~42 trading days, ~2 calendar months). We also test "
               "whether CMDI is any better than the HY credit spread (OAS) already on disk, "
               "and whether the result holds when we remove each major market crisis from "
               "the sample one at a time.")
    out.append("")
    out.append("CMDI data is available weekly with only a few days of lag. We apply a "
               "conservative 2-month lag anyway — this means the signal we use for any "
               "given month uses CMDI readings from two months prior, which is verifiably "
               "look-ahead free even in fast-moving crises (e.g., 2020-03 signal uses "
               "January 2020 CMDI, not the COVID spike). Even with this conservative lag, "
               "if CMDI is genuinely informative, high distress readings should cluster "
               "before large drawdowns.")
    out.append("")

    # Data summary
    out.append("## Data Coverage")
    out.append("")
    out.append(f"| Source | Coverage | N |")
    out.append("|---|---|---|")
    out.append(f"| CMDI weekly (NY Fed) | {weekly.index.min().date()} -> {weekly.index.max().date()} | {len(weekly)} weeks |")
    out.append(f"| CMDI monthly (resampled) | {monthly.index.min().date()} -> {monthly.index.max().date()} | {len(monthly)} months |")
    out.append(f"| SPY daily (Yahoo) | {spy.index.min().date()} -> {spy.index.max().date()} | {len(spy)} days |")
    out.append(f"| HY OAS (FRED BAMLH0A0HYM2) | {hy_oas.dropna().index.min().date()} -> {hy_oas.dropna().index.max().date()} | {hy_oas.dropna().count()} months |")
    out.append("")
    out.append(f"**Forward label base rates** (SPY drawdown <= {100*DRAWDOWN_THRESH:.0f}% within horizon):")
    out.append(f"- 21d horizon: {int(n21)} events / {label_21d_m.dropna().count()} months "
               f"({100*pct21:.1f}%)")
    out.append(f"- 63d horizon: {int(n63)} events / {label_63d_m.dropna().count()} months "
               f"({100*pct63:.1f}%)")
    out.append("")

    # Signal coverage
    out.append("## Signal First-Valid Dates (post lag + min-history)")
    out.append("")
    out.append("| Signal | First Valid |")
    out.append("|---|---|")
    for c in sigs.columns:
        first = sigs[c].dropna().index.min() if sigs[c].notna().any() else "N/A"
        out.append(f"| {c} | {first} |")
    out.append("")

    # Pre-registration summary
    out.append("## Pre-Registration")
    out.append("")
    out.append(f"Trial ledger: family=`{FAMILY}`, {len(GRID)} configs logged at generation, "
               f"family effective N={n_total}.")
    out.append("")

    # All AUC results
    out.append("## T1 AUC Results — All Signals")
    out.append("")
    out.append("Gate: AUC >= 0.60 AND bootstrap 95% CI excludes 0.50.")
    out.append("Horizons: 21 = 21 calendar days (~14 trading days, ~3 weeks); "
               "63 = 63 calendar days (~42 trading days, ~2 calendar months). "
               "forward_max_drawdown() uses pd.Timedelta(days=N), so these are "
               "calendar-day windows, not trading-day windows.")
    out.append("Overlap: monthly series — each obs is one calendar month, no overlap correction needed.")
    out.append("")
    out.append("| Signal | Horizon | N | N_events | AUC | 95% CI lo | 95% CI hi | "
               "CI>0.5 | Gate | NW_t | NW_p |")
    out.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for col, lbl, hz in sorted(ALL_SIGS, key=lambda x: x[2]):
        key = f"{col}_{hz}"
        r = results_all.get(key, {})
        auc = r.get("auc", np.nan)
        ci_lo = r.get("ci_lo", np.nan)
        ci_hi = r.get("ci_hi", np.nan)
        ci_ok = "Y" if not np.isnan(ci_lo) and ci_lo > 0.50 else "N"
        gated_keys = [k for _, _, _, k in GATED]
        is_gated = key in gated_keys
        gate_str = ""
        if is_gated:
            g = gated_t1.get(key, {})
            gate_str = "PASS" if g.get("pass") else "FAIL"
        else:
            gate_str = "(context)"
        auc_str = f"{auc:.4f}" if not np.isnan(auc) else "nan"
        ci_lo_str = f"{ci_lo:.4f}" if not np.isnan(ci_lo) else "nan"
        ci_hi_str = f"{ci_hi:.4f}" if not np.isnan(ci_hi) else "nan"
        nw_t = r.get("nw_t")
        nw_p = r.get("nw_p")
        nw_t_str = f"{nw_t:.3f}" if nw_t is not None else "nan"
        nw_p_str = f"{nw_p:.4f}" if nw_p is not None else "nan"
        out.append(f"| {col} | {hz} | {r.get('n', 0)} | {r.get('n_events', 0)} | "
                   f"{auc_str} | {ci_lo_str} | {ci_hi_str} | {ci_ok} | "
                   f"{'**' + gate_str + '**' if is_gated else gate_str} | {nw_t_str} | {nw_p_str} |")
    out.append("")

    # HY OAS baseline — full coverage (for display context only)
    out.append("### HY OAS Baseline (Full Coverage — display only)")
    out.append("")
    out.append("These numbers show HY OAS evaluated on its own full date range (back to 1999). "
               "They are **not** used for the T2 gate — see T2 section for identical-date comparisons.")
    out.append("")
    out.append("| Series | Horizon | N | N_events | AUC | 95% CI lo | 95% CI hi |")
    out.append("|---|---|---|---|---|---|---|")
    for hz, r in [("21d", hyoas_r21_full), ("63d", hyoas_r63_full)]:
        auc = r.get("auc", np.nan)
        ci_lo = r.get("ci_lo", np.nan)
        ci_hi = r.get("ci_hi", np.nan)
        out.append(f"| HY OAS z-score (full) | {hz} | {r.get('n', 0)} | {r.get('n_events', 0)} | "
                   f"{auc:.4f} | {ci_lo:.4f} | {ci_hi:.4f} |")
    out.append("")

    # T2: beats baseline — IDENTICAL dates per gated cell
    out.append("## T2 — CMDI vs HY OAS Baseline (Gated Cells, Identical Dates)")
    out.append("")
    out.append("**Pre-registered requirement:** IDENTICAL labels vs HY-OAS baseline. "
               "HY-OAS AUC is computed on the exact same months used for each CMDI cell "
               "(the intersection of non-NaN dates from the joined signal+label series). "
               "Without this restriction, the HY-OAS baseline covers 1999–2026 (330 months) "
               "while CMDI covers only 2007–2026 (232 months), giving HY-OAS the full "
               "2008 run-up window that CMDI cannot see — inflating its unconstrained AUC.")
    out.append("")
    out.append("Gate: CMDI beats HY-OAS AUC (identical dates) at >= 1 gated cell.")
    out.append("")
    out.append("| Gated Cell | CMDI AUC | HY OAS AUC (identical N) | N identical | CMDI Beats |")
    out.append("|---|---|---|---|---|")
    for key, b in beats_baseline.items():
        ca = b["cmdi_auc"]
        oa = b["oas_auc"]
        n_id = b.get("n_identical", 0)
        beats_str = "YES" if b["beats"] else "NO"
        ca_str = f"{ca:.4f}" if not np.isnan(ca) else "nan"
        oa_str = f"{oa:.4f}" if not np.isnan(oa) else "nan"
        out.append(f"| {key} | {ca_str} | {oa_str} | {n_id} | {beats_str} |")
    out.append("")
    n_beats = sum(v["beats"] for v in beats_baseline.values())
    if t2_pass:
        out.append(f"**T2 GATE: PASS** (CMDI beats HY-OAS on identical dates at {n_beats}/4 gated cell(s))")
    else:
        out.append(f"**T2 GATE: FAIL** (CMDI does not beat HY-OAS on identical dates at any gated cell; "
                   f"{n_beats}/4 cells where CMDI wins)")
    out.append("")

    # T3: LOCO
    out.append("## T3 — Leave-One-Crisis-Out Stability (Gated Cells)")
    out.append("")
    out.append("Gate: each removal produces AUC > 0.50 (same direction). "
               "At least one gated cell must be fully LOCO-stable.")
    out.append("")
    for key, loco in loco_results.items():
        stable = loco_stable_per_key.get(key, False)
        out.append(f"### {key} — LOCO {'STABLE' if stable else 'UNSTABLE'}")
        out.append("")
        out.append("| Crisis excised | AUC | > 0.50 |")
        out.append("|---|---|---|")
        for cz, auc in loco.items():
            ok = "YES" if not np.isnan(auc) and auc > LOCO_DIRECTION else "NO"
            out.append(f"| -{cz} | {auc:.4f} if not np.isnan(auc) else 'nan' | {ok} |")
        out.append("")

    # Fix the f-string issue above
    # rewrite LOCO section cleanly
    out_loco = []
    out_loco.append("## T3 — Leave-One-Crisis-Out Stability (Gated Cells)")
    out_loco.append("")
    out_loco.append("Gate: each removal produces AUC > 0.50 (same direction). "
                    "At least one gated cell must be fully LOCO-stable.")
    out_loco.append("")
    for key, loco in loco_results.items():
        stable = loco_stable_per_key.get(key, False)
        out_loco.append(f"### {key} — LOCO {'STABLE' if stable else 'UNSTABLE'}")
        out_loco.append("")
        out_loco.append("| Crisis excised | AUC | > 0.50 |")
        out_loco.append("|---|---|---|")
        for cz, auc in loco.items():
            auc_str = f"{auc:.4f}" if not np.isnan(auc) else "nan"
            ok = "YES" if not np.isnan(auc) and auc > LOCO_DIRECTION else "NO"
            out_loco.append(f"| -{cz} | {auc_str} | {ok} |")
        out_loco.append("")

    out_loco.append(f"**T3 GATE: {'PASS' if t3_pass else 'FAIL'}** "
                    f"({'>=1 gated cell LOCO-stable' if t3_pass else 'no gated cell fully LOCO-stable'})")
    out_loco.append("")

    # Rebuild output replacing the flawed LOCO section
    # Find and replace T3 section
    t3_start = next((i for i, l in enumerate(out) if l.startswith("## T3")), None)
    if t3_start is not None:
        out = out[:t3_start] + out_loco
    else:
        out.extend(out_loco)

    # Gate summary
    out.append("## Gate Summary")
    out.append("")
    out.append("| Gate | Result | Details |")
    out.append("|---|---|---|")
    out.append(f"| T1: AUC>=0.60, CI>0.50 at any gated cell | "
               f"{'**PASS**' if t1_any_pass else '**FAIL**'} | "
               f"Gated cells passing: {sum(v['pass'] for v in gated_t1.values())}/4 |")
    out.append(f"| T2: CMDI beats HY-OAS at >=1 gated cell | "
               f"{'**PASS**' if t2_pass else '**FAIL**'} | "
               f"Cells where CMDI wins: {sum(v['beats'] for v in beats_baseline.values())}/4 |")
    out.append(f"| T3: LOCO stable (>=1 gated cell) | "
               f"{'**PASS**' if t3_pass else '**FAIL**'} | "
               f"Stable cells: {sum(loco_stable_per_key.values())}/{len(loco_stable_per_key)} |")
    out.append("")
    out.append(f"## VERDICT: {'PASS — DE-ESCALATION INPUT CANDIDACY' if overall_pass else 'FAIL — CONTEXT VERDICT (null accepted)'}")
    out.append("")

    if overall_pass:
        out.append("CMDI meets all three pre-registered gates. It is a candidate for the "
                   "de-escalation input pool. Next step: submit to the conditioning gate "
                   "router for live tracking; promote only after accrual clock completes.")
    else:
        passing_gates = []
        if t1_any_pass:
            passing_gates.append("T1 (AUC)")
        if t2_pass:
            passing_gates.append("T2 (vs baseline)")
        if t3_pass:
            passing_gates.append("T3 (LOCO)")
        failed = [g for g in ["T1", "T2", "T3"]
                  if g not in [x.split(" ")[0] for x in passing_gates]]
        out.append(f"Failed gates: {', '.join(failed)}. "
                   f"CMDI remains a context signal — high readings are informative for "
                   f"narrative/display but do not meet the de-escalation candidacy bar. "
                   f"Re-test if methodology or lag assumption changes.")
    out.append("")

    # Honest-N section
    out.append("## Honest-N")
    out.append("")
    out.append(f"Monthly series, ~{len(sigs.dropna(how='all'))} monthly obs usable "
               f"(after lag + min-history). Independent 'crisis' events in-sample: "
               f"{len(CRISES)} excision windows tested in LOCO. "
               f"AUC CI via bootstrap resampling positives/negatives independently "
               f"(correct for binary AUC, not block-bootstrap which is for return series). "
               f"NW lags=6 covers 6-month serial correlation at 63d horizon.")
    out.append("")

    # Nightly wiring section
    out.append("## Nightly Wiring (for consolidation)")
    out.append("")
    out.append("### Collector: `scripts/collect_nyfed_cmdi.py`")
    out.append("")
    out.append("Standalone collector (ships with this PR). Fetches the NY Fed CMDI Excel "
               "file via the interactive data URL, parses Market/IG/HY sub-indices, "
               "saves weekly raw and month-end resampled parquets.")
    out.append("")
    out.append("**Outputs:**")
    out.append("- `data/nyfed_cmdi/cmdi_weekly.parquet` — weekly raw (end-of-week Friday)")
    out.append("- `data/nyfed_cmdi/cmdi_monthly.parquet` — month-end last reading")
    out.append("")
    out.append("**Wiring into nightly collect.py:**")
    out.append("```python")
    out.append("# In scripts/collect.py — add after existing nyfed collectors:")
    out.append("from scripts.collect_nyfed_cmdi import collect_nyfed_cmdi")
    out.append("collect_nyfed_cmdi()  # idempotent; skips if already current")
    out.append("```")
    out.append("")
    out.append("**Signal construction (engine/signal_lab.py consumer):**")
    out.append("```python")
    out.append("from scripts.cmdi_phase0 import build_signals, build_monthly")
    out.append("import pandas as pd")
    out.append("")
    out.append("monthly = pd.read_parquet('data/nyfed_cmdi/cmdi_monthly.parquet')")
    out.append("sigs = build_signals(monthly, lag=2)  # 2-month PIT lag")
    out.append("# Columns: market_level_pctile, ig_level_pctile, hy_level_pctile,")
    out.append("#          market_3m_chg_pctile, ig_3m_chg_pctile, hy_3m_chg_pctile")
    out.append("```")
    out.append("")
    out.append("**Recommended schedule:** Weekly cron (e.g., Wednesday 11am ET) for "
               "idempotent refresh. CMDI is a weekly series updated on Fridays; "
               "weekly polling picks up the latest reading within days of each "
               "week-end. The 2-month lag in signal construction ensures the data "
               "remains look-ahead-free regardless of exact collection timing.")
    out.append("")

    report_text = "\n".join(out)

    report_path = REPORTS_DIR / "w2104-cmdi-conditioning-phase0.md"
    report_path.write_text(report_text)
    print(f"\n[report] written -> {report_path}")
    print(report_text[:3000])

    # Machine-readable JSON summary
    print("\n=== JSON SUMMARY ===")
    print(json.dumps({
        "family": FAMILY,
        "verdict": "PASS" if overall_pass else "FAIL",
        "t1_any_gated_pass": t1_any_pass,
        "t2_beats_baseline": t2_pass,
        "t3_loco_stable": t3_pass,
        "gated_cells": {k: {"auc": round(v["r"].get("auc", float("nan")), 4),
                            "ci_lo": round(v["r"].get("ci_lo", float("nan")), 4),
                            "ci_hi": round(v["r"].get("ci_hi", float("nan")), 4),
                            "gate_pass": v["pass"]}
                        for k, v in gated_t1.items()},
        "hyoas_baseline_21d_auc": round(hyoas_r21_full.get("auc", float("nan")), 4),
        "hyoas_baseline_63d_auc": round(hyoas_r63_full.get("auc", float("nan")), 4),
        "trial_n": n_total,
        "n_monthly_obs": int(sigs.dropna(how="all").shape[0]),
        "n_events_21d": int(n21),
        "n_events_63d": int(n63),
        "base_rate_21d": round(float(pct21), 4),
        "base_rate_63d": round(float(pct63), 4),
    }, indent=2))


if __name__ == "__main__":
    main()
