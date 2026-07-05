"""Entry-Stack Expansion W1 — S-EV Earnings-Blackout Historical Study.

Masterplan ref: research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md
  §3 F1 (S-EV design), §5 (hygiene bar), §10 RUL-3/RUL-4/RUL-7/RUL-9/RUL-12.
W0 baselines frozen in: research/entry_stack/W0_BASELINES.md (RUL-7 gate).
NC yardstick: research/entry_stack/W1_NC_REPORT.md (RUL-3).

Family: esx_ev_blackout (budget=9: k in {1,2,3} x 3 panels; k=3 POOLED primary).

Pre-registered expectations (masterplan §3 F1):
  - Stratum = fires whose NEXT Item-2.02 filing_date for that ticker falls
    within k TRADING DAYS strictly after the fire date. A fire on the
    announcement date itself (k=0) counts as k=0 and is included in every k.
  - Contrast stratum vs rest with the R1 date-FE estimator.
  - Primary endpoints: stop5 and mae63.
  - Full asymmetry table secondary; era analysis on the POOLED deep+baskets set.
  - Coverage-limited fires (ticker absent from 8-K store) EXCLUDED from BOTH
    arms with counts printed — never silently treated as non-blackout.
  - Vetoed-volume percentage per k reported; >10% = hygiene-cap violation.
  - k=3 POOLED is the registered primary; k=1/2 are sensitivity arms.
  - Kill line: if inside-window fires NOT worse on stop5 OR mae63
    (pooled FE CI includes 0 at k=3) → do not wire; print null.

EDGAR 8-K anchor: data/edgar/earnings_8k_dates.parquet
  (full Item 2.02 history, rebuilt 2026-07-05 PR #1378 with pagination fix).

Usage:
    cd /path/to/repo
    python scripts/research/run_w1_sev.py
    python scripts/research/run_w1_sev.py --smoke           # 50 boot, deep only
    python scripts/research/run_w1_sev.py --n-bootstrap 500
    python scripts/research/run_w1_sev.py --panel deep baskets
    python scripts/research/run_w1_sev.py --out research/entry_stack/W1_SEV_REPORT.md
"""
from __future__ import annotations

import argparse
import logging
import sys
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Import harness primitives from W0 PR-C
# ---------------------------------------------------------------------------
from scripts.research.entry_strata_phase0 import (  # noqa: E402
    _build_sector_map,
    _get_closes,
    _register_all_families,
    _prepare_binary_outcomes,
    _assign_era,
    compute_recall,
    grade_fires,
    load_fires,
    FAMILY_BUDGETS,
    PROGRAM_ERAS,
    BH_Q_THRESHOLD,
    N_BOOTSTRAP,
    RNG_SEED,
)

# Import fast R1 estimator from NC runner (O(n log n) block construction)
from scripts.research.run_w1_nc import (  # noqa: E402
    fast_r1_estimate,
    fast_effect_table,
    fast_era_table,
    bh_correction,
    _fast_make_blocks,
    _empty_r1,
    _fmt_pct,
    _fmt_f,
    _ci_str,
    _excl_zero,
    _write_effect_md,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_DATA             = _REPO_ROOT / "data"
_RESEARCH_DIR     = _REPO_ROOT / "research" / "entry_stack"
_FIRES_DEEP       = _DATA / "research" / "gate_fires_deep.parquet"
_FIRES_BASKETS    = _DATA / "research" / "gate_fires_baskets.parquet"
_EDGAR_8K_DATES   = _DATA / "edgar" / "earnings_8k_dates.parquet"
_EDGAR_COVERAGE   = _DATA / "edgar" / "earnings_8k_dates_coverage.json"
_LEDGER_PATH      = _DATA / "trial_ledger.jsonl"

# ---------------------------------------------------------------------------
# Study constants (masterplan §3 F1, frozen pre-registration)
# ---------------------------------------------------------------------------
K_VALUES       = [1, 2, 3]   # k ∈ {1,2,3}; k=3 is the primary
K_PRIMARY      = 3
HYGIENE_VETO_CAP = 0.10       # >10% vetoed volume = hygiene-cap violation

# ---------------------------------------------------------------------------
# Step 0 Self-Gate: coverage check
# ---------------------------------------------------------------------------

def check_coverage() -> dict[str, Any]:
    """Read earnings_8k_dates_coverage.json and return gate result.

    Gate: ≥800 names with ≥8 years of 8-K history.
    If coverage.json absent, fall back to computing from parquet.
    """
    import json

    if _EDGAR_COVERAGE.exists():
        cov = json.loads(_EDGAR_COVERAGE.read_text())
        return {
            "gate_pass":     cov.get("gate_pass", False),
            "gate_verdict":  cov.get("gate_verdict", "UNKNOWN"),
            "gate_reason":   cov.get("gate_reason", ""),
            "names_total":   cov.get("names_total", 0),
            "names_ge8y":    cov.get("names_ge8y", 0),
            "total_rows":    cov.get("total_rows", 0),
            "overall_span":  cov.get("overall_span", ""),
            "as_of":         cov.get("as_of", ""),
        }

    if not _EDGAR_8K_DATES.exists():
        return {
            "gate_pass":    False,
            "gate_verdict": "FAIL",
            "gate_reason":  "earnings_8k_dates.parquet not found",
            "names_total":  0,
            "names_ge8y":   0,
            "total_rows":   0,
            "overall_span": "",
            "as_of":        "",
        }

    # Compute from parquet
    df = pd.read_parquet(_EDGAR_8K_DATES)
    df["filing_date"] = pd.to_datetime(df["filing_date"])
    span_by_ticker = df.groupby("ticker")["filing_date"].agg(["min", "max"])
    years_by_ticker = (span_by_ticker["max"] - span_by_ticker["min"]).dt.days / 365.25
    names_ge8y = int((years_by_ticker >= 8).sum())
    names_total = len(span_by_ticker)
    gate_pass = names_ge8y >= 800
    return {
        "gate_pass":    gate_pass,
        "gate_verdict": "PASS" if gate_pass else "FAIL",
        "gate_reason":  f"{names_ge8y} names with ≥8y — {'meets' if gate_pass else 'below'} threshold of 800",
        "names_total":  names_total,
        "names_ge8y":   names_ge8y,
        "total_rows":   len(df),
        "overall_span": f"{df['filing_date'].min().date()} .. {df['filing_date'].max().date()}",
        "as_of":        str(pd.Timestamp.now().date()),
    }


# ---------------------------------------------------------------------------
# Build trading-day calendar from deep-panel price files
# ---------------------------------------------------------------------------

def _build_trading_day_index() -> pd.DatetimeIndex:
    """Return a sorted DatetimeIndex of all trading days from the deep panel."""
    deep_store = _DATA / "stocks"
    all_dates: set = set()
    for path in sorted(deep_store.glob("*.parquet")):
        try:
            df = pd.read_parquet(path, columns=["close"])
            all_dates.update(df.index.to_list())
        except Exception as exc:  # noqa: BLE001
            log.debug("failed to read %s: %s", path, exc)
    if not all_dates:
        # Fallback to business-day calendar
        log.warning("No deep-panel price files found; using business-day calendar fallback.")
        return pd.bdate_range("1960-01-01", "2030-12-31")
    return pd.DatetimeIndex(sorted(all_dates))


# ---------------------------------------------------------------------------
# Trading-day distance computation
# ---------------------------------------------------------------------------

def _td_distance(
    fire_date: pd.Timestamp,
    filing_date: pd.Timestamp,
    td_index: pd.DatetimeIndex,
) -> int | None:
    """Number of trading days from fire_date to filing_date (exclusive, signed).

    Returns:
        0   if filing_date == fire_date (announcement on fire day)
        1   if filing_date is the NEXT trading day after fire_date
        etc.
        Negative if filing_date is before fire_date.
        None if fire_date or filing_date not representable in td_index.

    Implementation: binary-search both dates in td_index, subtract positions.
    The distance is the number of trading bars strictly after fire_date up to
    and including filing_date (i.e. filing_idx - fire_idx).
    """
    # searchsorted to find position
    fire_pos = td_index.searchsorted(fire_date, side="left")
    filing_pos = td_index.searchsorted(filing_date, side="left")

    # Check that fire_date is actually a known trading day (within ±1d tolerance)
    # For fires on non-trading days (rare edge), snap to the nearest following day.
    # The key invariant is that fire_pos points to fire_date or the next trading day.
    # For the distance computation, we use positions directly.
    # Clamp to valid range
    if fire_pos >= len(td_index) or filing_pos >= len(td_index):
        return None

    return int(filing_pos - fire_pos)


# ---------------------------------------------------------------------------
# Build 8-K blackout labels for all fires
# ---------------------------------------------------------------------------

def build_blackout_labels(
    fires: pd.DataFrame,
    ek_dates: pd.DataFrame,
    td_index: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Attach blackout-stratum columns to the fires DataFrame.

    For each fire:
      - Look up the NEXT Item-2.02 filing_date for that ticker STRICTLY AFTER
        (or on) the fire date.
      - Compute trading-day distance k_td = td_distance(fire_date, filing_date).
      - A fire on the announcement date itself (k_td == 0) counts as k=0 and is
        included in every k stratum.
      - ev_blackout_k (for k in {1,2,3}) = 1 iff k_td in [0, k]; 0 otherwise.
        (k_td == 0 means the 8-K was filed on the fire day itself.)
      - ev_coverage = 1 if ticker present in 8-K store; 0 if absent.
        Fires with ev_coverage==0 are EXCLUDED from both arms (printed, not silent).
      - ev_next_filing = the filing_date used (or NaT if none found)
      - ev_k_td = the trading-day distance computed (or NaN if not found)

    The masterplan says: "a fire on the announcement date itself counts as k=0
    — include in every k". So k_td == 0 → ev_blackout_1 = ev_blackout_2 = ev_blackout_3 = 1.
    And k_td == 1 → ev_blackout_1 = 1. k_td == 2 → ev_blackout_2 = 1, etc.
    """
    ek_by_ticker = {}
    for ticker, grp in ek_dates.groupby("ticker"):
        dates = grp["filing_date"].sort_values().values  # sorted numpy array
        ek_by_ticker[ticker] = dates

    ev_coverage_list: list[int] = []
    ev_next_filing_list: list[pd.Timestamp | None] = []
    ev_k_td_list: list[float] = []
    ev_blackout: dict[int, list[int]] = {k: [] for k in K_VALUES}

    for _, row in fires.iterrows():
        ticker = str(row["ticker"])
        fire_date = pd.Timestamp(row["date"])

        if ticker not in ek_by_ticker:
            # Coverage-limited: exclude from both arms
            ev_coverage_list.append(0)
            ev_next_filing_list.append(None)
            ev_k_td_list.append(np.nan)
            for k in K_VALUES:
                ev_blackout[k].append(np.nan)  # NaN = excluded
            continue

        ev_coverage_list.append(1)
        filings = ek_by_ticker[ticker]

        # Find the NEXT filing on or after fire_date
        idx = np.searchsorted(filings, fire_date, side="left")
        if idx >= len(filings):
            # No future filing in the store for this ticker after fire_date
            ev_next_filing_list.append(None)
            ev_k_td_list.append(np.nan)
            for k in K_VALUES:
                ev_blackout[k].append(0)  # covered ticker, no upcoming filing → not in blackout
            continue

        next_filing = pd.Timestamp(filings[idx])
        ev_next_filing_list.append(next_filing)

        k_td = _td_distance(fire_date, next_filing, td_index)
        if k_td is None:
            ev_k_td_list.append(np.nan)
            for k in K_VALUES:
                ev_blackout[k].append(0)
            continue

        ev_k_td_list.append(float(k_td))

        # Assign blackout strata: k_td in [0, k] means in the k-day blackout window
        for k in K_VALUES:
            ev_blackout[k].append(1 if (0 <= k_td <= k) else 0)

    result = fires.copy()
    result["ev_coverage"]    = ev_coverage_list
    result["ev_next_filing"] = ev_next_filing_list
    result["ev_k_td"]        = ev_k_td_list
    for k in K_VALUES:
        result[f"ev_blackout_k{k}"] = ev_blackout[k]

    return result


# ---------------------------------------------------------------------------
# Trial-ledger registration for S-EV runs
# ---------------------------------------------------------------------------

def _register_sev_trials(ledger_path: Path | None = None) -> None:
    """Log each S-EV study configuration as a trial in esx_ev_blackout family."""
    try:
        from engine.trial_ledger import TrialLedger
    except ImportError:
        log.warning("trial_ledger not importable; S-EV trial rows skipped")
        return
    led = TrialLedger(path=ledger_path or _LEDGER_PATH)
    configs = [
        {"k": k, "stratum": f"ev_blackout_k{k}", "panel": panel}
        for k in K_VALUES
        for panel in ["deep", "baskets", "pooled"]
    ]
    for cfg in configs:
        led.log_trial(cfg, family="esx_ev_blackout", note="W1 S-EV run")
    log.info("Logged %d S-EV trial configs in esx_ev_blackout", len(configs))


# ---------------------------------------------------------------------------
# Core study runner for one panel + one k
# ---------------------------------------------------------------------------

def _run_one_k(
    labeled: pd.DataFrame,
    closes: dict[str, pd.Series],
    sector_map: dict[str, str],
    k: int,
    *,
    panel_name: str,
    fe_granularity: str = "date",
    n_bootstrap: int = N_BOOTSTRAP,
) -> dict[str, Any]:
    """Run the S-EV study for a given k on the labeled fire set.

    labeled must have columns: ev_coverage, ev_blackout_k{k}, sector (or None).
    Coverage-excluded fires (ev_coverage==0) are excluded from BOTH arms.
    The remaining covered fires are split: stratum=1 (inside k-day window)
    vs stratum=0 (outside window, covered and no upcoming filing within k days).
    """
    stratum_col = f"ev_blackout_k{k}"

    # Exclude coverage-limited fires (NaN stratum = not in 8K store)
    df_covered = labeled[labeled["ev_coverage"] == 1].copy()
    n_coverage_excluded = int((labeled["ev_coverage"] == 0).sum())
    n_no_upcoming = int((df_covered[stratum_col] == 0).sum())
    n_in_window   = int((df_covered[stratum_col] == 1).sum())

    log.info(
        "Panel=%s k=%d: covered=%d, excluded=%d, in_window=%d, not_in_window=%d",
        panel_name, k, len(df_covered), n_coverage_excluded, n_in_window, n_no_upcoming,
    )

    # Compute vetoed-volume percentage (as fraction of ALL covered fires)
    n_covered_total = len(df_covered)
    veto_pct = n_in_window / n_covered_total if n_covered_total > 0 else 0.0
    hygiene_cap_ok = veto_pct <= HYGIENE_VETO_CAP

    if n_covered_total == 0 or n_in_window < 10 or n_no_upcoming < 10:
        log.warning("Insufficient fires for k=%d panel=%s; skipping estimation.", k, panel_name)
        return {
            "k": k,
            "panel": panel_name,
            "stratum_col": stratum_col,
            "n_covered": n_covered_total,
            "n_coverage_excluded": n_coverage_excluded,
            "n_in_window": n_in_window,
            "n_not_in_window": n_no_upcoming,
            "veto_pct": veto_pct,
            "hygiene_cap_ok": hygiene_cap_ok,
            "note": "insufficient fires for estimation",
            "effect_table": None,
            "era_table": None,
            "recall": None,
        }

    # Grade the covered fires (RUL-9: one grader)
    log.info("Panel=%s k=%d: grading %d covered fires...", panel_name, k, n_covered_total)
    graded = grade_fires(df_covered, closes)
    n_gradable = int(graded["gradable"].fillna(False).sum())
    log.info("  Gradable: %d / %d", n_gradable, n_covered_total)

    # Attach sector column
    graded["sector"] = graded["ticker"].map(sector_map)

    # Effect table
    eff = fast_effect_table(
        graded, stratum_col,
        fe_granularity=fe_granularity,
        sector_col="sector",
        n_bootstrap=n_bootstrap,
        family_label=f"esx_ev_blackout_k{k}_{panel_name}",
    )

    # Era table (pooled only; single-panel era tables are secondary)
    era = fast_era_table(graded, stratum_col, panel_label=panel_name)

    # Recall
    recall = compute_recall(graded, stratum_col)

    return {
        "k": k,
        "panel": panel_name,
        "stratum_col": stratum_col,
        "n_covered": n_covered_total,
        "n_coverage_excluded": n_coverage_excluded,
        "n_in_window": n_in_window,
        "n_not_in_window": n_no_upcoming,
        "veto_pct": veto_pct,
        "hygiene_cap_ok": hygiene_cap_ok,
        "n_gradable": n_gradable,
        "effect_table": eff,
        "era_table": era.to_dict(orient="records") if era is not None else [],
        "recall": recall,
    }


# ---------------------------------------------------------------------------
# Main study runner
# ---------------------------------------------------------------------------

def run_sev_study(
    *,
    n_bootstrap: int = N_BOOTSTRAP,
    panels: list[str] | None = None,
    ledger_path: Path | None = None,
) -> dict[str, Any]:
    """Run the S-EV earnings-blackout study across panels and k values.

    Returns a nested dict: results[panel][k] = per-k result dict.
    The 'pooled' pseudo-panel concatenates deep + baskets fires.
    """
    _register_all_families(ledger_path)
    _register_sev_trials(ledger_path)

    # --- Coverage gate (Step 0) ---
    cov = check_coverage()
    log.info("Coverage gate: %s — %s", cov["gate_verdict"], cov["gate_reason"])
    if not cov["gate_pass"]:
        return {"coverage": cov, "gate_fail": True, "results": {}}

    # --- Load 8-K dates ---
    log.info("Loading 8-K dates from %s", _EDGAR_8K_DATES)
    ek_dates = pd.read_parquet(_EDGAR_8K_DATES)
    ek_dates["filing_date"] = pd.to_datetime(ek_dates["filing_date"])
    log.info("  8-K rows: %d, tickers: %d", len(ek_dates), ek_dates["ticker"].nunique())

    # --- Build trading-day calendar ---
    log.info("Building trading-day calendar from deep panel...")
    td_index = _build_trading_day_index()
    log.info("  Trading days: %d (%s .. %s)", len(td_index), td_index[0].date(), td_index[-1].date())

    # --- Sector map ---
    sector_map = _build_sector_map()
    log.info("Sector map: %d tickers", len(sector_map))

    # --- Panel configs ---
    panel_configs = [
        ("deep",    _FIRES_DEEP),
        ("baskets", _FIRES_BASKETS),
    ]
    if panels:
        panel_configs = [(n, p) for n, p in panel_configs if n in panels]

    # --- Load + label fires per panel ---
    labeled_panels: dict[str, pd.DataFrame] = {}
    closes_panels:  dict[str, dict[str, pd.Series]] = {}

    for panel_name, fires_path in panel_configs:
        if not fires_path.exists():
            log.warning("Fire dump not found: %s — skipping %s", fires_path, panel_name)
            continue
        fires = load_fires(fires_path)
        log.info("Panel %s: %d fires loaded", panel_name, len(fires))

        log.info("  Labeling blackout strata...")
        labeled = build_blackout_labels(fires, ek_dates, td_index)
        n_excl = int((labeled["ev_coverage"] == 0).sum())
        log.info("  Coverage-excluded (ticker absent from 8-K store): %d fires", n_excl)

        labeled_panels[panel_name] = labeled
        closes_panels[panel_name]  = _get_closes(panel_name)

    # Build pooled panel (deep + baskets combined) for primary k=3 analysis
    # Panel eras analysis runs on this pooled set (masterplan §3 F1).
    if "deep" in labeled_panels and "baskets" in labeled_panels and (
        panels is None or ("deep" in panels and "baskets" in panels)
    ):
        labeled_pooled = pd.concat([
            labeled_panels["deep"],
            labeled_panels["baskets"],
        ], ignore_index=True)
        # For the pooled panel, closes = combined from both
        closes_pooled = {}
        closes_pooled.update(closes_panels.get("deep", {}))
        closes_pooled.update(closes_panels.get("baskets", {}))
        labeled_panels["pooled"] = labeled_pooled
        closes_panels["pooled"]  = closes_pooled
        log.info("Pooled panel: %d fires", len(labeled_pooled))
    elif len(labeled_panels) == 1:
        # Only one panel was requested; no pooled panel
        pass

    # --- Run k-grid study per panel ---
    all_results: dict[str, dict[int, Any]] = {}

    for panel_name, labeled in labeled_panels.items():
        fe_gran = "date"
        log.info("=== Panel: %s (fe=%s) ===", panel_name, fe_gran)
        closes = closes_panels[panel_name]
        all_results[panel_name] = {}

        for k in K_VALUES:
            log.info("--- k=%d ---", k)
            res = _run_one_k(
                labeled, closes, sector_map, k,
                panel_name=panel_name,
                fe_granularity=fe_gran,
                n_bootstrap=n_bootstrap,
            )
            all_results[panel_name][k] = res

    return {
        "coverage":   cov,
        "gate_fail":  False,
        "results":    all_results,
        "td_calendar_size": len(td_index) if "td_index" in dir() else 0,
    }


# ---------------------------------------------------------------------------
# Markdown report writer
# ---------------------------------------------------------------------------

def _hygiene_str(ok: bool, veto_pct: float) -> str:
    status = "MET" if ok else "NOT MET"
    return f"{status} (vetoed {veto_pct:.1%} of covered fires; cap is 10%)"


def write_report(study_results: dict[str, Any], out_path: Path) -> None:
    """Write W1_SEV_REPORT.md."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Load NC yardstick from W1_NC_REPORT.md to embed (RUL-3)
    nc_report_path = _RESEARCH_DIR / "W1_NC_REPORT.md"
    nc_yardstick_lines: list[str] = []
    if nc_report_path.exists():
        nc_text = nc_report_path.read_text(encoding="utf-8")
        in_yardstick = False
        for line in nc_text.splitlines():
            if "## YARDSTICK" in line:
                in_yardstick = True
            if in_yardstick:
                nc_yardstick_lines.append(line)
    else:
        nc_yardstick_lines = ["*(W1_NC_REPORT.md not found — see that file for NC reference numbers)*"]

    lines: list[str] = []
    a = lines.append

    a("# W1 S-EV Earnings-Blackout Study Report — Entry-Stack Expansion")
    a("")
    a("**Family:** `esx_ev_blackout` (budget=9: k ∈ {1,2,3} × 3 panels; k=3 POOLED is the pre-registered primary)")
    a("**Status:** W1 study report only — no promotion, no product change (RUL-4 / HYGIENE semantics).")
    a("**Date:** 2026-07-05")
    a("")
    a("**Adjacency (R2 per RUL-2):** No falsified relative; `event_blackout` slot pre-sanctioned in")
    a("REJECTION_TAXONOMY (grading.py:110), currently emitted by nothing. This is not an alpha claim —")
    a("it is a hygiene claim: a known binary event inside the stop horizon converts a timing edge into")
    a("a coin flip; suppressing fresh entries T-k..T+0 before scheduled earnings removes variance")
    a("that the entry signal is never paid for.")
    a("")
    a("**Coverage anchor:** EDGAR 8-K Item 2.02 filing dates (data/edgar/earnings_8k_dates.parquet),")
    a("rebuilt 2026-07-05 PR #1378 with pagination fix. All rows in the store are Item 2.02.")
    a("")

    # Coverage gate result
    cov = study_results.get("coverage", {})
    a("## Step 0: Coverage Gate")
    a("")
    a(f"| Field | Value |")
    a(f"|---|---|")
    a(f"| Gate verdict | **{cov.get('gate_verdict', 'UNKNOWN')}** |")
    a(f"| Gate reason | {cov.get('gate_reason', '')} |")
    a(f"| Names total (in 8-K store) | {cov.get('names_total', 0):,} |")
    a(f"| Names ≥8y history | {cov.get('names_ge8y', 0):,} |")
    a(f"| Total Item 2.02 rows | {cov.get('total_rows', 0):,} |")
    a(f"| Overall date span | {cov.get('overall_span', '')} |")
    a(f"| as_of | {cov.get('as_of', '')} |")
    a("")

    if study_results.get("gate_fail"):
        a("**DEMOTION RECORD:** Coverage gate FAILED. S-EV demotes to live-veto-only")
        a("(forward-accrued hygiene, no historical verdict) per masterplan §3 F1.")
        a("No historical study run. Live wiring deferred until 8-K coverage reaches ≥800 names × ≥8y.")
        out_path.write_text("\n".join(lines), encoding="utf-8")
        log.info("Wrote demotion record to %s", out_path)
        return

    # NC yardstick (RUL-3)
    a("---")
    a("")
    a("## NC Yardstick (RUL-3)")
    a("")
    a("> Per §10 RUL-3: null-competitor reference numbers appear as the first table.")
    a("> Source: research/entry_stack/W1_NC_REPORT.md.")
    a("> Note which CIs are marked [proxy] or [low-block caveat].")
    a("")
    for nc_line in nc_yardstick_lines:
        a(nc_line)
    a("")

    a("---")
    a("")
    a("## Study Design")
    a("")
    a("**Stratum definition:** A fire is IN the k-day blackout window iff the NEXT")
    a("Item-2.02 8-K filing_date for that ticker falls within k trading days strictly")
    a("after (or on) the fire date. A fire on the announcement date itself (k=0) is")
    a("included in every k stratum. Trading-day arithmetic uses the actual NYSE/NASDAQ")
    a("calendar derived from the deep-panel price files (no calendar-day approximation).")
    a("")
    a("**Coverage exclusion:** Fires whose ticker is absent from the 8-K store are")
    a("excluded from BOTH the treatment and control arms. They are counted and printed")
    a("here — never silently treated as non-blackout.")
    a("")
    a("**Primary endpoint:** k=3 POOLED (deep + baskets), stop5 and mae63.")
    a("**Sensitivity:** k=1 and k=2; separate deep/baskets panels.")
    a("**Era analysis:** Runs on the POOLED deep+baskets fire set per masterplan §3 F1.")
    a("")
    a("**Hygiene bar (masterplan §5):** CI-excluding-0 degradation on stop5 OR mae63")
    a("(pooled FE, k=3 primary). Vetoed volume ≤10% of fires. RUL-7 caveat: bare 2pp")
    a("point-estimate rarely clears CI-excluding-0 at minimum n — the CI clause is operative.")
    a("")

    all_results = study_results.get("results", {})

    # Write per-panel, per-k results
    for panel_name, k_results in all_results.items():
        a("---")
        a("")
        a(f"## Panel: {panel_name.upper()}")
        a("")
        a("**SURVIVOR BIAS STAMP:** SURVIVOR BIAS: absolute rates on surviving names only.")
        a("Within-arm comparisons are directionally valid.")
        a("")

        for k in K_VALUES:
            res = k_results.get(k)
            if res is None:
                continue
            is_primary = (k == K_PRIMARY and panel_name == "pooled")
            primary_tag = " **(PRIMARY — k=3 POOLED)**" if is_primary else ""
            a(f"### k={k}{primary_tag}")
            a("")

            # Coverage summary
            a(f"**Coverage exclusion:**")
            a(f"- Fires in this panel: N/A (see n_covered below)")
            a(f"- Ticker absent from 8-K store (excluded from BOTH arms): {res.get('n_coverage_excluded', 'N/A'):,}")
            a(f"- Covered fires (in estimation): {res.get('n_covered', 'N/A'):,}")
            a(f"- In blackout window (treatment): {res.get('n_in_window', 'N/A'):,}")
            a(f"- Outside window (control): {res.get('n_not_in_window', 'N/A'):,}")
            a("")
            veto_pct = res.get("veto_pct", np.nan)
            hygiene_cap_ok = res.get("hygiene_cap_ok", False)
            a(f"**Hygiene: vetoed-volume cap (≤10%):** {_hygiene_str(hygiene_cap_ok, veto_pct)}")
            a("")

            eff = res.get("effect_table")
            if eff is None or res.get("note"):
                a(f"**Note:** {res.get('note', 'estimation not run')}")
                a("")
                continue

            n_grad = res.get("n_gradable", "N/A")
            a(f"- Gradable fires: {n_grad:,}" if isinstance(n_grad, int) else f"- Gradable fires: {n_grad}")
            a("")

            # Recall (precision beside recall per masterplan §5)
            recall_d = res.get("recall", {})
            rc_val = recall_d.get("recall")
            rc_n_treat = recall_d.get("n_treatment", 0)
            rc_n_all = recall_d.get("n_all", 0)
            a(f"**Recall:** {_fmt_pct(rc_val)} of gradable covered fires are in the treatment arm "
              f"({rc_n_treat:,} of {rc_n_all:,}). Recall note: fires outside the window ({rc_n_all - rc_n_treat:,}) "
              f"are the control arm.")
            a("")

            _write_effect_md(lines, eff, f"Effect Table — k={k} {panel_name.upper()} (R1 FE, block bootstrap)")

            # Era table (print only for pooled panel and k=3 primary)
            era_recs = res.get("era_table", [])
            if era_recs and panel_name == "pooled":
                era_df = pd.DataFrame(era_recs)
                prog = era_df[era_df["era"].isin(PROGRAM_ERAS)] if "era" in era_df.columns else era_df
                if not prog.empty:
                    stratum_col = res.get("stratum_col", f"ev_blackout_k{k}")
                    a(f"#### Era Analysis (POOLED, program eras, k={k})")
                    a("")
                    cols = [c for c in ["era", stratum_col, "n_fires", "stop5_rate", "mae63_mean"]
                            if c in prog.columns]
                    a("| " + " | ".join(cols) + " |")
                    a("|" + "---|" * len(cols))
                    for _, row in prog.iterrows():
                        cells = []
                        for c in cols:
                            v = row.get(c)
                            if c == "stop5_rate":
                                cells.append(_fmt_pct(v))
                            elif c == "mae63_mean":
                                cells.append(_fmt_f(v))
                            else:
                                cells.append(str(v) if v is not None else "—")
                        a("| " + " | ".join(cells) + " |")
                    a("")

    # ---------------------------------------------------------------------------
    # Hygiene summary table across all k / panels
    # ---------------------------------------------------------------------------
    a("---")
    a("")
    a("## Hygiene Summary: Vetoed-Volume Cap per k and Panel")
    a("")
    a("| Panel | k | Vetoed (treatment) | Covered fires | Veto pct | Cap (≤10%) |")
    a("|---|---|---|---|---|---|")
    for panel_name, k_results in all_results.items():
        for k in K_VALUES:
            res = k_results.get(k)
            if res is None:
                continue
            a(f"| {panel_name} | {k} | "
              f"{res.get('n_in_window', '?'):,} | "
              f"{res.get('n_covered', '?'):,} | "
              f"{_fmt_pct(res.get('veto_pct'))} | "
              f"{'MET' if res.get('hygiene_cap_ok') else 'NOT MET'} |")
    a("")

    # ---------------------------------------------------------------------------
    # Verdict summary (mechanical: met/not met per clause; no promotion language)
    # ---------------------------------------------------------------------------
    a("---")
    a("")
    a("## Hygiene Bar Verdict (Mechanical — RUL-7 Caveats Apply)")
    a("")
    a("Masterplan §5 HYGIENE bar:")
    a("1. CI-excluding-0 degradation on stop5 OR mae63 (pooled FE, k=3 primary)")
    a("2. Vetoed volume ≤10% of covered fires per k")
    a("")
    a("RUL-7 caveat: the CI-excluding-0 clause is operative (not the bare 2pp point-estimate).")
    a("A bare effect of 2pp rarely clears CI-excluding-0 at minimum n.")
    a("")

    # Mechanically read verdict from pooled k=3
    pooled_k3 = all_results.get("pooled", {}).get(K_PRIMARY)
    if pooled_k3 and pooled_k3.get("effect_table"):
        eff = pooled_k3["effect_table"]
        effects_by_label = {e["label"]: e for e in eff.get("effects", [])}

        stop5_e = effects_by_label.get("stop5", {})
        mae63_e = effects_by_label.get("mae63", {})

        stop5_coef = stop5_e.get("coef")
        stop5_ci_lo = stop5_e.get("ci_lo")
        stop5_ci_hi = stop5_e.get("ci_hi")
        mae63_coef = mae63_e.get("coef")
        mae63_ci_lo = mae63_e.get("ci_lo")
        mae63_ci_hi = mae63_e.get("ci_hi")

        # stop5 degradation = POSITIVE coefficient (more stops in window)
        # mae63 degradation = NEGATIVE coefficient (worse MAE = more negative)
        stop5_excl_0 = (stop5_ci_lo is not None and stop5_ci_hi is not None and
                        (stop5_ci_lo > 0 or stop5_ci_hi < 0))
        mae63_excl_0 = (mae63_ci_lo is not None and mae63_ci_hi is not None and
                        (mae63_ci_lo > 0 or mae63_ci_hi < 0))

        # For stop5: degradation means HIGHER stop-out rate in window → positive coef
        stop5_degrades = (stop5_excl_0 and stop5_coef is not None and stop5_coef > 0)
        # For mae63: degradation means WORSE (more negative) MAE in window → negative coef
        mae63_degrades = (mae63_excl_0 and mae63_coef is not None and mae63_coef < 0)

        hygiene_cap_k3 = pooled_k3.get("hygiene_cap_ok", False)

        a("### Primary Endpoint (k=3, POOLED panel)")
        a("")
        a(f"| Clause | Result | Detail |")
        a(f"|---|---|---|")
        a(f"| stop5 CI-excluding-0 degradation | {'MET' if stop5_degrades else 'NOT MET'} | "
          f"coef={_fmt_f(stop5_coef, 4)}, CI={_ci_str(stop5_e)} |")
        a(f"| mae63 CI-excluding-0 degradation | {'MET' if mae63_degrades else 'NOT MET'} | "
          f"coef={_fmt_f(mae63_coef, 4)}, CI={_ci_str(mae63_e)} |")
        a(f"| Either stop5 OR mae63 CI-excl-0 | {'MET' if (stop5_degrades or mae63_degrades) else 'NOT MET'} | "
          f"primary hygiene condition |")
        a(f"| Vetoed-volume cap ≤10% (k=3) | {'MET' if hygiene_cap_k3 else 'NOT MET'} | "
          f"vetoed {_fmt_pct(pooled_k3.get('veto_pct'))} of covered fires |")
        a("")

        if stop5_degrades or mae63_degrades:
            a("**Overall: hygiene evidence PRESENT on primary endpoint** (RUL-7 caveat applies: "
              "CI-excluding-0 at k=3 pooled on ≥1 of stop5/mae63). Forward to reviewer for "
              "sign-off before any wiring decision. No promotion decision made here.")
        else:
            a("**Overall: NULL on primary endpoint** (k=3 pooled; CI includes 0 on both stop5 "
              "and mae63). Per masterplan §3 F1 kill line: inside-window fires not demonstrably "
              "worse → do not wire. Null printed, not hidden.")
        a("")
        a("No promotion, no wiring decision. Reports only (RUL-4).")
    else:
        a("*(Pooled k=3 result not available — see above for individual panels)*")

    a("")
    a("---")
    a("")
    a("*Generated by `scripts/research/run_w1_sev.py`*")
    a("*Grader: engine/grading.py (program barriers, RUL-9).*")
    a("*'validated' word deliberately absent (CI-enforced).*")
    a("*No promotion language. Study report only.*")
    a("*Family: esx_ev_blackout | Budget declared: 9 | Runs: k∈{1,2,3} × 3 panels*")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Wrote %s", out_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Entry-Stack Expansion W1 — S-EV Earnings-Blackout Study.",
    )
    parser.add_argument(
        "--out", default=str(_RESEARCH_DIR / "W1_SEV_REPORT.md"),
        help="Output path for W1_SEV_REPORT.md",
    )
    parser.add_argument(
        "--n-bootstrap", type=int, default=1000,
        help="Block-bootstrap resamples (default 1000; --smoke uses 50)",
    )
    parser.add_argument(
        "--panel", nargs="+", choices=["deep", "baskets"],
        default=None,
        help="Restrict to named panel(s); default runs all (including pooled).",
    )
    parser.add_argument(
        "--smoke", action="store_true",
        help="Quick smoke test: 50 bootstrap, deep panel only.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )
    warnings.filterwarnings("ignore", category=RuntimeWarning)

    n_boot  = 50 if args.smoke else args.n_bootstrap
    panels  = ["deep"] if args.smoke else args.panel

    log.info("Starting W1 S-EV study (n_bootstrap=%d, panels=%s)", n_boot, panels or "all")
    results = run_sev_study(n_bootstrap=n_boot, panels=panels)

    if results.get("gate_fail"):
        log.warning("Coverage gate FAILED — writing demotion record only.")
    else:
        log.info("Coverage gate PASSED — running full study.")

    write_report(results, Path(args.out))
    log.info("Done. Report at %s", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
