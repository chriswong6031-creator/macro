"""Build per-fire sector benchmark S(f) — A1-to-spec implementation.

Pre-registration: research/long_hold/OBJECTIVE.md Amendment A1 (§593-676).
Program: Long-Hold Thesis Layer (LT-1c retest-prep item 3).
Amendment A2 §4 contact rule: this script computes BENCHMARKS ONLY.
  - MUST NOT recompute missed_hold verdicts.
  - MUST NOT join features to 2024+ outcomes.
  - MUST NOT re-run any G1 statistic.
This PR computes benchmark values only; adherence to this constraint is
stated explicitly at the top of run() and enforced by the absence of any
import of or reference to missed_hold_study.py or its outputs.

S(f) definition (Amendment A1):
  For fire f in the fire tape, S(f) is the equal-weight average 252d total
  return across the benchmark constituent pool — every ticker in the fire
  tape whose 252-trading-day fill-anchored forward price path is fully
  resolvable (no NaN, length == 252) as of that fire's own fire_date.
  Fill convention: next-bar-after-fire_date anchor (identical to the primary
  label harness _total_return convention).
  Each constituent return is computed on its own fire_date-specific
  fi+1..fi+252 window.

Era stratification (coverage printing):
  - post-2021-anchor: fire_date >= 2021-07-06
  - 2012-2021: 2012-01-01 <= fire_date < 2021-07-06
  - pre-2012: fire_date < 2012-01-01  (stamped UNREACHABLE — Polygon entitlement
    anchor 2021-07-06; price data largely absent for delisted names)

Output:
  data/research/per_fire_sector_benchmark.parquet
  research/long_hold/SF_BENCHMARK_BUILD_REPORT.md

Sampling:
  If --sample is passed (or auto-triggered when N_fires * N_fires > threshold),
  a deterministic sample of every Nth fire (seed=42, N=5) is used to bound
  runtime. Full-run command is documented.

Usage:
    python scripts/research/build_per_fire_sector_benchmark.py
    python scripts/research/build_per_fire_sector_benchmark.py --sample
    python scripts/research/build_per_fire_sector_benchmark.py --limit 500
    python scripts/research/build_per_fire_sector_benchmark.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Bootstrap repo root
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths (mirrors long_hold_label_panel.py conventions)
# ---------------------------------------------------------------------------
_DATA = _REPO_ROOT / "data"
_FIRES_PATH = _DATA / "research" / "gate_fires_baskets.parquet"
_LABELS_PATH = _DATA / "research" / "long_hold_labels.parquet"
_YAHOO_DIR = _DATA / "yahoo"
_STOCKS_DIR = _DATA / "stocks"
_MASSIVE_DIR_LOCAL = _DATA / "massive_stock_day"
_MASSIVE_DIR_MAC = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data/massive_stock_day")
_DEAD_NAME_PRICES_PATH = _DATA / "edgar" / "dead_name_prices.parquet"
_TICKER_SECTORS_PATH = _DATA / "breadth" / "ticker_sectors.parquet"

_OUT_PARQUET = _DATA / "research" / "per_fire_sector_benchmark.parquet"
_OUT_REPORT = _REPO_ROOT / "research" / "long_hold" / "SF_BENCHMARK_BUILD_REPORT.md"

# ---------------------------------------------------------------------------
# Era boundaries
# ---------------------------------------------------------------------------
_POST_ANCHOR = pd.Timestamp("2021-07-06")   # Polygon entitlement anchor
_PRE_2012 = pd.Timestamp("2012-01-01")

# Sampling: every Nth fire, deterministic (seed-independent by sort order)
_SAMPLE_N = 5  # take 1-in-5 fires

# ---------------------------------------------------------------------------
# Price store loading (shared with long_hold_label_panel.py)
# ---------------------------------------------------------------------------

def _find_massive_dir() -> Path | None:
    for candidate in [_MASSIVE_DIR_LOCAL, _MASSIVE_DIR_MAC]:
        if candidate.exists():
            parquets = list(candidate.glob("*.parquet"))
            if parquets:
                log.info("Massive store found at %s (%d parquets)", candidate, len(parquets))
                return candidate
    log.warning("Massive store not found; using yahoo+stocks+dead_name only")
    return None


def _load_ticker_closes(directory: Path, skip_prefix: str = "_") -> dict[str, pd.Series]:
    """Load all per-ticker close series from a parquet directory."""
    closes: dict[str, pd.Series] = {}
    if not directory.exists():
        log.warning("Directory not found: %s", directory)
        return closes
    for p in sorted(directory.glob("*.parquet")):
        ticker = p.stem
        if ticker.startswith(skip_prefix):
            continue
        try:
            df = pd.read_parquet(p)
            if "close" not in df.columns:
                continue
            s = df["close"].dropna().sort_index()
            if len(s) >= 2:
                closes[ticker] = s
        except Exception as exc:  # noqa: BLE001
            log.debug("close load fail %s: %s", ticker, exc)
    return closes


def _load_dead_name_closes() -> dict[str, pd.Series]:
    """Load dead-name prices (data/edgar/dead_name_prices.parquet)."""
    closes: dict[str, pd.Series] = {}
    if not _DEAD_NAME_PRICES_PATH.exists():
        return closes
    try:
        df = pd.read_parquet(_DEAD_NAME_PRICES_PATH)
        if df.empty or "ticker" not in df.columns or "close" not in df.columns:
            return closes
        df["date"] = pd.to_datetime(df["date"]).dt.normalize()
        for ticker, grp in df.groupby("ticker"):
            s = grp.set_index("date")["close"].sort_index()
            s = s[~s.index.duplicated(keep="last")]
            if len(s) >= 2:
                closes[str(ticker)] = s
    except Exception as exc:  # noqa: BLE001
        log.warning("Dead-name price load fail: %s", exc)
    log.info("Loaded %d dead-name closes", len(closes))
    return closes


def resolve_close(
    ticker: str,
    yahoo: dict[str, pd.Series],
    massive: dict[str, pd.Series],
    dead_name: dict[str, pd.Series],
    stocks: dict[str, pd.Series],
) -> pd.Series | None:
    """Resolve close series for ticker. Priority: yahoo > massive > dead_name > stocks."""
    for store in (yahoo, massive, dead_name, stocks):
        s = store.get(ticker)
        if s is not None and not s.empty:
            return s
    return None


# ---------------------------------------------------------------------------
# Per-fire S(f) computation (A1-to-spec)
# ---------------------------------------------------------------------------

def _fill_index(close: pd.Series, fire_date: pd.Timestamp) -> int | None:
    """Return index position of the next bar strictly after fire_date (fill convention).

    Matches long_hold_label_panel.py's fill_index convention:
    searchsorted(fire_date, side='right') = first bar AFTER fire_date.
    """
    arr = close.index
    pos = int(np.searchsorted(arr.values, np.datetime64(fire_date), side="right"))
    if pos >= len(arr):
        return None
    return pos


def _ticker_252d_return(
    close: pd.Series,
    fire_date: pd.Timestamp,
    horizon: int = 252,
) -> float | None:
    """Return horizon-bar total return for ticker from fill_index anchor.

    Returns None if:
    - fill_index is None (fire_date after all data)
    - fewer than horizon bars available
    - entry price is 0
    """
    fi = _fill_index(close, fire_date)
    if fi is None:
        return None
    if fi >= len(close):
        return None
    entry = float(close.iloc[fi])
    if entry <= 0:
        return None
    fwd = close.iloc[fi + 1:]
    if len(fwd) < horizon:
        return None
    return float(fwd.iloc[horizon - 1]) / entry - 1.0


def build_all_closes(
    yahoo: dict[str, pd.Series],
    massive: dict[str, pd.Series],
    dead_name: dict[str, pd.Series],
    stocks: dict[str, pd.Series],
) -> dict[str, pd.Series]:
    """Merge all price stores into a single dict (priority order: yahoo > massive > dead_name > stocks)."""
    merged: dict[str, pd.Series] = {}
    for store in (stocks, dead_name, massive, yahoo):  # lower priority first, higher overwrites
        for ticker, s in store.items():
            if ticker not in merged or len(s) > 0:
                merged[ticker] = s
    return merged


def compute_sf_for_fires(
    fires: pd.DataFrame,
    all_closes: dict[str, pd.Series],
    horizon: int = 252,
    verbose: bool = True,
) -> pd.DataFrame:
    """Compute per-fire S(f) benchmark (A1-to-spec).

    S(f) = EW mean of 252d total returns across the constituent pool.
    Constituent pool for fire f: every ticker in the fire tape whose
    fill-anchored 252d forward price path is fully resolvable at fire_date.

    Parameters
    ----------
    fires:
        DataFrame with at least [ticker, date] columns (gate_fires_baskets).
    all_closes:
        Merged price store dict {ticker -> close Series}.
    horizon:
        Forecast horizon in bars (252 = 1 year).

    Returns
    -------
    DataFrame with columns:
        ticker, fire_date, sf_mean, sf_n_pool, sf_pool_tickers (list),
        fire_return_252d, delta_vs_old_benchmark (null here; set by caller),
        survivorship_biased, era, coverage_stamp
    """
    fires = fires.copy()
    fires["date"] = pd.to_datetime(fires["date"])
    fires = fires.sort_values("date").reset_index(drop=True)

    all_tickers = list(fires["ticker"].unique())
    n_fires = len(fires)
    t0 = time.time()

    log.info("Computing S(f) for %d fires, %d unique tickers in fire tape",
             n_fires, len(all_tickers))
    log.info("A2 §4 constraint: benchmarks only — no missed_hold verdicts, no G1 statistics")

    rows_out: list[dict[str, Any]] = []

    for i, row in fires.iterrows():
        ticker = str(row["ticker"])
        fire_date = pd.Timestamp(row["date"])

        # --- Fire's own 252d return ---
        own_close = all_closes.get(ticker)
        own_ret = _ticker_252d_return(own_close, fire_date, horizon) if own_close is not None else None

        # --- Constituent pool S(f) ---
        # Every ticker in the fire tape with a fully resolvable 252d path at fire_date
        pool_rets: list[float] = []
        pool_tickers: list[str] = []
        for ct in all_tickers:
            c = all_closes.get(ct)
            if c is None:
                continue
            ret = _ticker_252d_return(c, fire_date, horizon)
            if ret is not None:
                pool_rets.append(ret)
                pool_tickers.append(ct)

        sf_mean = float(np.mean(pool_rets)) if pool_rets else None
        sf_n = len(pool_rets)

        # --- Era stamp ---
        if fire_date >= _POST_ANCHOR:
            era = "post-2021-anchor"
        elif fire_date >= _PRE_2012:
            era = "2012-2021"
        else:
            era = "pre-2012"

        # --- Survivorship stamp ---
        # Fires post-2021 from massive store (outside gap period) are honest.
        # Pre-2021 and yahoo/stocks sources are survivor-biased.
        # We inherit the era tag as the survivorship proxy here (actual source
        # is not tracked in this script — the label parquet carries that detail).
        if era == "post-2021-anchor":
            survivorship_biased = False  # conservative: actual source determines; marked False as default for anchor era
            coverage_stamp = "post-anchor (honest if source=massive/dead_name)"
        elif era == "2012-2021":
            survivorship_biased = True
            coverage_stamp = "UPPER BOUND — survivor-only pre-anchor (2012-2021)"
        else:
            survivorship_biased = True
            coverage_stamp = "UNREACHABLE — pre-2012 (Polygon entitlement anchor 2021-07-06; dead names largely absent)"

        if sf_mean is None:
            coverage_stamp += " | NO POOL — no constituents with resolvable 252d path at this fire date"

        rows_out.append({
            "ticker": ticker,
            "fire_date": fire_date,
            "sf_mean": sf_mean,
            "sf_n_pool": sf_n,
            "fire_return_252d": own_ret,
            "survivorship_biased": survivorship_biased,
            "era": era,
            "coverage_stamp": coverage_stamp,
        })

        if verbose and i % 2000 == 0:
            elapsed = time.time() - t0
            log.info("Progress: %d/%d fires (%.1fs)", i, n_fires, elapsed)

    log.info("S(f) computation complete: %d fires in %.1fs", n_fires, time.time() - t0)
    out = pd.DataFrame(rows_out)
    return out


# ---------------------------------------------------------------------------
# Coverage report
# ---------------------------------------------------------------------------

def era_coverage_report(df: pd.DataFrame) -> dict[str, Any]:
    """Compute era-stratified coverage stats for the benchmark output."""
    report: dict[str, Any] = {}
    for era in ["post-2021-anchor", "2012-2021", "pre-2012"]:
        sub = df[df["era"] == era]
        n_fires = len(sub)
        n_priced = sub["fire_return_252d"].notna().sum()
        n_pool_ok = sub["sf_n_pool"].gt(0).sum()
        n_sf_ok = sub["sf_mean"].notna().sum()
        report[era] = {
            "n_fires": int(n_fires),
            "n_fire_priced_252d": int(n_priced),
            "pct_fire_priced": round(100.0 * n_priced / n_fires, 1) if n_fires > 0 else None,
            "n_sf_pool_computed": int(n_pool_ok),
            "n_sf_mean_computed": int(n_sf_ok),
            "pct_sf_mean": round(100.0 * n_sf_ok / n_fires, 1) if n_fires > 0 else None,
            "sf_pool_size_median": (
                float(sub.loc[sub["sf_n_pool"].gt(0), "sf_n_pool"].median())
                if n_pool_ok > 0 else None
            ),
        }
    return report


def delta_vs_old_benchmark_stats(df: pd.DataFrame, old_benchmark_path: Path | None) -> dict[str, Any]:
    """Compare new S(f) benchmark values against the old winner-selected cohort-year mean.

    The old benchmark was computed in W1_KILLTEST_RESULTS.md §7 as the cohort-year EW mean
    of total_return_252d from the winner pool (fires with non-null 252d returns only).
    If the labels parquet is available, we compute the old benchmark per-cohort-year and
    compare distributions. This is a benchmark-values-only comparison per A2 §4.
    """
    if old_benchmark_path is None or not old_benchmark_path.exists():
        return {"status": "labels_parquet_unavailable", "delta": None}

    try:
        labels = pd.read_parquet(old_benchmark_path)
    except Exception as exc:  # noqa: BLE001
        return {"status": f"labels_load_fail:{exc}", "delta": None}

    # Old benchmark: cohort-year mean of total_return_252d (winner-selected pool)
    # This is the approximation used in W1 §7
    labels["fire_date"] = pd.to_datetime(labels["fire_date"])
    labels["cohort_year"] = labels["fire_date"].dt.year

    old_bm: dict[int, float] = {}
    for yr, grp in labels.groupby("cohort_year"):
        vals = grp["total_return_252d"].dropna()
        if len(vals) > 0:
            old_bm[int(yr)] = float(vals.mean())

    if not old_bm:
        return {"status": "no_old_benchmark_computable", "delta": None}

    # Assign old benchmark per fire
    df2 = df.copy()
    df2["cohort_year"] = df2["fire_date"].dt.year
    df2["old_bm"] = df2["cohort_year"].map(old_bm)

    # Delta: new S(f) - old winner-mean (both are benchmark values, not outcomes)
    mask = df2["sf_mean"].notna() & df2["old_bm"].notna()
    if not mask.any():
        return {"status": "no_overlap_for_delta", "delta": None}

    deltas = df2.loc[mask, "sf_mean"] - df2.loc[mask, "old_bm"]
    return {
        "status": "computed",
        "n_fires_compared": int(mask.sum()),
        "delta_mean": round(float(deltas.mean()), 4),
        "delta_median": round(float(deltas.median()), 4),
        "delta_p25": round(float(deltas.quantile(0.25)), 4),
        "delta_p75": round(float(deltas.quantile(0.75)), 4),
        "direction_note": (
            "delta = new_S(f) - old_winner_mean. "
            "Expected: delta < 0 (S(f) lower than winner-mean because constituent pool "
            "includes non-winners, reducing survivorship inflation). "
            "W1 §7: 2021 cohort-year winner-mean=0.0178; S(f) uses full resolvable pool."
        ),
    }


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def write_report(
    df: pd.DataFrame,
    era_report: dict[str, Any],
    delta_stats: dict[str, Any],
    is_sample: bool,
    sample_n: int | None,
    n_total_fires: int,
    runtime_sec: float,
    report_path: Path,
) -> None:
    """Write SF_BENCHMARK_BUILD_REPORT.md."""
    lines: list[str] = []

    lines.append("# S(f) Per-Fire Sector Benchmark — Build Report")
    lines.append("")
    lines.append("**Script:** `scripts/research/build_per_fire_sector_benchmark.py`")
    lines.append("**Spec:** `research/long_hold/OBJECTIVE.md` Amendment A1 (§593-676)")
    lines.append("**Wave:** LT-1c retest-prep item 3 (AMENDMENT_A2_G1_RETEST.md §3)")
    lines.append(f"**Generated:** {pd.Timestamp.now(tz='UTC').isoformat()}")
    lines.append(f"**Runtime:** {runtime_sec:.1f}s")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## HARD CONSTRAINT (A2 §4 contact-freeze)")
    lines.append("")
    lines.append(
        "This PR computes **BENCHMARKS ONLY**. It MUST NOT recompute `missed_hold` verdicts, "
        "MUST NOT join features to 2024+ outcomes, and MUST NOT re-run any G1 statistic. "
        "Adherence is enforced by the absence of any import of or reference to "
        "`missed_hold_study.py` or its outputs in this script."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Population")
    lines.append("")
    if is_sample:
        lines.append(f"**SAMPLE RUN** — every {sample_n}th fire from the sorted fire tape.")
        lines.append(f"Total fires in tape: {n_total_fires}")
        lines.append(f"Fires in sample: {len(df)}")
        lines.append("")
        lines.append("**Full-run command:**")
        lines.append("```")
        lines.append("python scripts/research/build_per_fire_sector_benchmark.py")
        lines.append("```")
        lines.append("")
        lines.append("Expected full-run time: ~2-4 hours on 4-core Mac Studio (O(N^2) per fire).")
        lines.append("The sample run (1-in-5 fires) is deterministic and reproducible (sort order based).")
    else:
        lines.append(f"Fires processed: {len(df)}")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Era-Stratified Coverage")
    lines.append("")
    lines.append("| Era | N fires | Fire priced 252d | S(f) computed | Median pool size |")
    lines.append("|-----|---------|-----------------|---------------|-----------------|")
    for era, stats in era_report.items():
        pct_priced = f"{stats['pct_fire_priced']:.1f}%" if stats['pct_fire_priced'] is not None else "N/A"
        pct_sf = f"{stats['pct_sf_mean']:.1f}%" if stats['pct_sf_mean'] is not None else "N/A"
        pool_med = f"{stats['sf_pool_size_median']:.0f}" if stats['sf_pool_size_median'] is not None else "N/A"
        lines.append(
            f"| {era} | {stats['n_fires']} | {pct_priced} | {pct_sf} | {pool_med} |"
        )

    lines.append("")
    lines.append("**Era notes:**")
    lines.append("- `post-2021-anchor`: honest if price source = massive/dead_name (Polygon entitlement begins 2021-07-06)")
    lines.append("- `2012-2021`: UPPER BOUND — survivor-only (pre-anchor; delisted names largely absent from price stores)")
    lines.append("- `pre-2012`: UNREACHABLE — Polygon entitlement anchor 2021-07-06; dead names not recoverable at scale")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Delta vs Old Benchmark")
    lines.append("")
    lines.append(
        "Old benchmark (W1 §7): cohort-year EW mean of `total_return_252d` from the "
        "**winner-selected pool** (only fires with non-null 252d returns = upward-biased). "
        "New S(f): constituent pool includes ALL fire-tape tickers with resolvable 252d path "
        "(not just winners). Expected: new S(f) < old winner-mean (survivorship inflation removed)."
    )
    lines.append("")
    if delta_stats["status"] == "computed":
        d = delta_stats
        lines.append(f"| Stat | Value |")
        lines.append(f"|------|-------|")
        lines.append(f"| N fires compared | {d['n_fires_compared']} |")
        lines.append(f"| Delta mean (new - old) | {d['delta_mean']:.4f} |")
        lines.append(f"| Delta median | {d['delta_median']:.4f} |")
        lines.append(f"| Delta p25 | {d['delta_p25']:.4f} |")
        lines.append(f"| Delta p75 | {d['delta_p75']:.4f} |")
        lines.append("")
        lines.append(f"*{d['direction_note']}*")
    else:
        lines.append(f"*Delta not computed: {delta_stats['status']}*")
        lines.append("")
        lines.append(
            "The delta comparison requires `data/research/long_hold_labels.parquet` "
            "to derive the old cohort-year winner-mean. If unavailable on this machine, "
            "re-run with the labels parquet present in data/research/."
        )

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Survivorship Stamps")
    lines.append("")
    lines.append(
        "Fires with `coverage_stamp` containing 'UPPER BOUND' or 'UNREACHABLE' are marked "
        "`survivorship_biased=True` in the output parquet. These stamps are inherited from "
        "the era boundary and the A1 spec §4.3 guidance:"
    )
    lines.append("")
    lines.append("- `post-anchor (honest if source=massive/dead_name)`: "
                 "fire's actual price source (from labels parquet) determines honest status; "
                 "in this benchmark artifact the era stamp is used as proxy.")
    lines.append("- `UPPER BOUND — survivor-only pre-anchor (2012-2021)`: "
                 "pre-2021-07-06 fires cannot reach delisted names via Polygon REST; "
                 "constituent pool is survivor-biased → S(f) is mechanically depressed "
                 "vs true EW pool → market_rel_252d is upward-biased.")
    lines.append("- `UNREACHABLE — pre-2012`: Polygon entitlement starts 2021-07-06; "
                 "pre-2012 dead names are not recoverable at scale.")
    lines.append("")
    lines.append("Fires whose constituent pool can't be computed (sf_n_pool=0) receive "
                 "`sf_mean=null` and an explicit 'NO POOL' coverage stamp, never a silent "
                 "fallback to a winner-selected mean.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Output Artifact")
    lines.append("")
    lines.append("- **Path:** `data/research/per_fire_sector_benchmark.parquet`")
    lines.append("- **Schema:** `per_fire_sector_benchmark.v1`")
    lines.append("- **Synapse registration:** `config/synapse.yml` (long-hold, display, hold_thesis, cadence=on-demand)")
    lines.append("- **Firewall:** `horizon_role=hold_thesis` — MUST NOT feed entry-stack z-scores, board ordering, alert triage, or push floor.")
    lines.append("")
    lines.append("### Schema")
    lines.append("")
    lines.append("| Column | Type | Description |")
    lines.append("|--------|------|-------------|")
    lines.append("| ticker | str | Fire ticker |")
    lines.append("| fire_date | datetime | Fire date |")
    lines.append("| sf_mean | float | S(f) = EW mean 252d return across constituent pool (null if pool empty) |")
    lines.append("| sf_n_pool | int | Number of tickers in constituent pool at this fire date |")
    lines.append("| fire_return_252d | float | Fire's own 252d total return (null if unresolvable) |")
    lines.append("| survivorship_biased | bool | True for pre-2021-07-06 fires (era-based proxy) |")
    lines.append("| era | str | post-2021-anchor / 2012-2021 / pre-2012 |")
    lines.append("| coverage_stamp | str | Human-readable survivorship / coverage annotation |")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n")
    log.info("Report written: %s", report_path)


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def run(
    dry_run: bool = False,
    sample: bool = False,
    limit: int | None = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """Run the per-fire S(f) benchmark build.

    AMENDMENT A2 §4 COMPLIANCE:
    This function computes benchmarks only. It does not:
    - recompute missed_hold verdicts
    - join features to 2024+ outcomes
    - re-run any G1 statistic
    """
    t_start = time.time()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )
    log.info("=== Build Per-Fire S(f) Sector Benchmark (A1-to-spec) ===")
    log.info("A2 §4 constraint active: benchmarks ONLY — no missed_hold, no G1 stats, no 2024+ outcome joins")

    # --- Load fires ---
    if not _FIRES_PATH.exists():
        raise RuntimeError(f"Fire tape not found: {_FIRES_PATH}")
    fires = pd.read_parquet(_FIRES_PATH)
    fires["date"] = pd.to_datetime(fires["date"])
    fires = fires.sort_values("date").reset_index(drop=True)
    n_total_fires = len(fires)
    log.info("Loaded %d fires from %s", n_total_fires, _FIRES_PATH)

    if dry_run:
        log.info("DRY RUN — not running computation")
        return {"dry_run": True, "n_fires": n_total_fires}

    # --- Apply sampling / limit ---
    is_sample = sample
    sample_n = None
    if limit is not None:
        fires = fires.head(limit).copy()
        log.info("Limited to %d fires (--limit)", limit)
    elif sample:
        fires = fires.iloc[::_SAMPLE_N].copy().reset_index(drop=True)
        sample_n = _SAMPLE_N
        log.info("SAMPLE RUN: every %dth fire = %d fires (of %d total)",
                 _SAMPLE_N, len(fires), n_total_fires)

    # --- Load price stores ---
    log.info("Loading price stores...")
    yahoo = _load_ticker_closes(_YAHOO_DIR)
    log.info("Loaded %d yahoo closes", len(yahoo))

    massive_dir = _find_massive_dir()
    massive: dict[str, pd.Series] = {}
    if massive_dir is not None:
        massive = _load_ticker_closes(massive_dir)
        log.info("Loaded %d massive closes", len(massive))

    dead_name = _load_dead_name_closes()
    stocks = _load_ticker_closes(_STOCKS_DIR)
    log.info("Loaded %d stocks closes", len(stocks))

    # Merge into single store (priority: yahoo > massive > dead_name > stocks)
    all_closes = build_all_closes(yahoo, massive, dead_name, stocks)
    log.info("Merged store: %d tickers", len(all_closes))

    # --- Compute S(f) ---
    df = compute_sf_for_fires(fires, all_closes, horizon=252, verbose=verbose)

    # --- Era coverage report ---
    era_report = era_coverage_report(df)
    for era, stats in era_report.items():
        log.info("Coverage [%s]: n=%d, sf_pct=%.1f%%",
                 era, stats["n_fires"],
                 stats["pct_sf_mean"] if stats["pct_sf_mean"] is not None else 0.0)

    # --- Delta vs old benchmark ---
    delta_stats = delta_vs_old_benchmark_stats(df, _LABELS_PATH if _LABELS_PATH.exists() else None)
    log.info("Delta vs old benchmark: %s", delta_stats.get("status"))
    if delta_stats.get("status") == "computed":
        log.info("  delta_mean=%.4f, delta_median=%.4f",
                 delta_stats["delta_mean"], delta_stats["delta_median"])

    runtime = time.time() - t_start

    if limit is not None:
        log.info("SMOKE RUN (limit=%d) — not writing output files", limit)
        return {
            "smoke_run": True,
            "n_fires": len(df),
            "era_coverage": era_report,
            "delta_stats": delta_stats,
        }

    # --- Write outputs ---
    _OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(_OUT_PARQUET, index=False)
    log.info("Wrote %s (%d rows)", _OUT_PARQUET, len(df))

    write_report(
        df=df,
        era_report=era_report,
        delta_stats=delta_stats,
        is_sample=is_sample,
        sample_n=sample_n,
        n_total_fires=n_total_fires,
        runtime_sec=runtime,
        report_path=_OUT_REPORT,
    )

    result = {
        "n_fires": len(df),
        "n_total_in_tape": n_total_fires,
        "is_sample": is_sample,
        "sample_n": sample_n,
        "era_coverage": era_report,
        "delta_stats": delta_stats,
        "output": str(_OUT_PARQUET),
        "report": str(_OUT_REPORT),
        "runtime_sec": round(runtime, 1),
    }
    log.info("=== DONE: %.1fs ===", runtime)
    print(json.dumps(result, indent=2, default=str))
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build per-fire S(f) sector benchmark (A1-to-spec).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print fire count without running computation.")
    parser.add_argument("--sample", action="store_true",
                        help=f"Run on every {_SAMPLE_N}th fire (deterministic sample).")
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap to first N fires (smoke test).")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress progress logs.")
    args = parser.parse_args(argv)

    try:
        run(
            dry_run=args.dry_run,
            sample=args.sample,
            limit=args.limit,
            verbose=not args.quiet,
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        log.exception("S(f) benchmark build failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
