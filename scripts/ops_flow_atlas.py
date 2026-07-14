"""scripts/ops_flow_atlas.py — FS-2 flow-signal field-guide atlas builder.

OPS-LANE ONLY. NOT wired into any workflow (daily.yml / config/dag.yml).
Run manually after ops_flow_cohorts.py has produced cohort parquets.

OUTPUTS
-------
data/flow_signals/atlas/atlas_tables.json
    Machine-readable: per-table dims, cells with n, stat, Wilson 95% CI,
    coverage window, cohort tag.

stdout
    Markdown table blocks for regeneration into FLOW_SIGNAL_FIELD_GUIDE.md.

COHORT LAW (FS-R4)
------------------
Every table is computed per-cohort. Mixed-source frames raise ValueError.
Tables A/B/C/G(partial)/H/I/J/K use eod_proxy.
Tables D/E/F/G(partial) use tape_recon.
No code path pools cohorts.

RAM LAW
-------
All parquet reads use pyarrow iter_batches with column pruning.
Full-cohort joins (needed for era x outcome) are performed in controlled
batches that load only required columns. Never load the full 7.3M-row
frame with all columns.

USAGE
-----
  python3 -m scripts.ops_flow_atlas [--output-dir PATH] [--b-sample-roots N]

ENV OVERRIDES
-------------
  FLOW_SIGNALS_DIR   — override input/output directory (default: data/flow_signals/)
  THETADATA_EOD_DIR  — override EOD store root (default: ~/theta-ops-wt/data/thetadata_eod)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from math import sqrt
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

log = logging.getLogger(__name__)

# ── paths ─────────────────────────────────────────────────────────────────────

def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _flow_signals_dir() -> Path:
    env = os.environ.get("FLOW_SIGNALS_DIR")
    if env:
        p = Path(env)
    else:
        p = _repo_root() / "data" / "flow_signals"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _eod_store_root() -> Path | None:
    candidates: list[Path] = []
    env = os.environ.get("THETADATA_EOD_DIR")
    if env:
        candidates.append(Path(env))
    candidates.append(Path.home() / "theta-ops-wt" / "data" / "thetadata_eod")
    candidates.append(_repo_root() / "data" / "thetadata_eod")
    for c in candidates:
        if c.exists():
            return c
    return None


def _atlas_dir() -> Path:
    d = _flow_signals_dir() / "atlas"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Wilson CI ─────────────────────────────────────────────────────────────────

def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 95% CI for a proportion k/n.

    Returns (lo, hi).  Returns (nan, nan) when n == 0.
    """
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    denom = 1 + z ** 2 / n
    centre = (p + z ** 2 / (2 * n)) / denom
    margin = z * sqrt(p * (1 - p) / n + z ** 2 / (4 * n ** 2)) / denom
    return max(0.0, centre - margin), min(1.0, centre + margin)


N_FLOOR = 30  # cells below this get ERA-SPARSE; stat suppressed


def _sparse_cell(n: int) -> dict[str, Any]:
    return {"n": n, "flag": "ERA-SPARSE", "stat": None, "ci_lo": None, "ci_hi": None}


def _rate_cell(k: int, n: int, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    if n < N_FLOOR:
        return _sparse_cell(n)
    lo, hi = wilson_ci(k, n)
    cell: dict[str, Any] = {"n": n, "k": k, "rate": k / n, "ci_lo": lo, "ci_hi": hi}
    if extra:
        cell.update(extra)
    return cell


def _median_cell(values: list[float], n: int) -> dict[str, Any]:
    if n < N_FLOOR:
        return _sparse_cell(n)
    return {"n": n, "median": float(np.median(values)), "mean": float(np.mean(values))}


# ── guard: single-source frames ───────────────────────────────────────────────

def _assert_single_source(df: pd.DataFrame, expected: str) -> None:
    """Raise ValueError if df contains rows from any source != expected."""
    if "source" not in df.columns:
        return
    found = set(df["source"].dropna().unique())
    if len(found) > 1 or (len(found) == 1 and expected not in found):
        raise ValueError(
            f"Cohort separation violation: expected source='{expected}', "
            f"got {found!r}. Tables must never pool cohorts (FS-R4)."
        )


# ── load helpers ──────────────────────────────────────────────────────────────

def _load_ok_grades(grades_path: Path) -> pd.DataFrame:
    """Stream grades, return DataFrame of ok-graded rows with outcome columns."""
    wanted = [
        "event_id", "reason_code",
        "fwd_ret_5", "spy_excess_5",
        "fwd_ret_21", "spy_excess_21",
        "fwd_ret_63", "spy_excess_63",
        "terminal_state_clean8_21",
    ]
    rows = []
    pf = pq.ParquetFile(grades_path)
    for batch in pf.iter_batches(batch_size=300_000, columns=wanted):
        df = batch.to_pandas()
        ok = df[df["reason_code"] == "ok"].copy()
        if len(ok):
            rows.append(ok.drop(columns=["reason_code"]))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=[c for c in wanted if c != "reason_code"])


def _load_events(events_path: Path, columns: list[str]) -> pd.DataFrame:
    """Stream events parquet, return DataFrame with requested columns."""
    rows = []
    pf = pq.ParquetFile(events_path)
    for batch in pf.iter_batches(batch_size=300_000, columns=columns):
        rows.append(batch.to_pandas())
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=columns)


# ── Table A — event frequency ─────────────────────────────────────────────────

def table_a(events_path: Path, cohort: str) -> dict[str, Any]:
    """A: qualification class x dte_bucket x era counts + events/day + median premium."""
    log.info("Table A: event frequency (%s)", cohort)
    needed = ["event_id", "era", "dte_bucket", "vol_gt_oi", "premium", "session_date", "source"]

    # Stream and aggregate
    era_dte_class: dict[tuple, dict] = {}
    session_dates: set = set()

    pf = pq.ParquetFile(events_path)
    for batch in pf.iter_batches(batch_size=200_000, columns=needed):
        df = batch.to_pandas()
        _assert_single_source(df, cohort)
        session_dates.update(df["session_date"].astype(str).unique())

        # Qualification class
        df["qual_class"] = "unknown"
        if "vol_gt_oi" in df.columns:
            voi = df["vol_gt_oi"].fillna(False).astype(bool)
            # premium_burst proxied via premium_z >= 2.5 (eod_proxy) or baseline presence
            # For eod_proxy: vol_gt_oi is the primary flag; premium_burst indicated by NOT vol_gt_oi
            # (detection: either condition qualifies)
            df.loc[voi, "qual_class"] = "vol_gt_oi"
            df.loc[~voi, "qual_class"] = "premium_burst_only"
            # 'both' would require premium_z column which may not be in minimal load
            if "premium_z" in df.columns:
                pb = df["premium_z"].notna() & (df["premium_z"] >= 2.5)
                df.loc[voi & pb, "qual_class"] = "both"

        for (era, dte, qc), grp in df.groupby(["era", "dte_bucket", "qual_class"]):
            key = (str(era), str(dte), str(qc))
            if key not in era_dte_class:
                era_dte_class[key] = {"n": 0, "premiums": []}
            era_dte_class[key]["n"] += len(grp)
            # Reservoir sample premiums (keep at most 1000 per cell)
            prems = grp["premium"].dropna().tolist()
            existing = era_dte_class[key]["premiums"]
            if len(existing) < 1000:
                era_dte_class[key]["premiums"].extend(prems[: 1000 - len(existing)])

    n_days = len(session_dates)
    cells = []
    for (era, dte, qc), agg in sorted(era_dte_class.items()):
        n = agg["n"]
        prems = agg["premiums"]
        median_prem = float(np.median(prems)) if prems else None
        cells.append({
            "era": era, "dte_bucket": dte, "qual_class": qc,
            "n_events": n,
            "events_per_day": round(n / n_days, 2) if n_days else None,
            "median_premium_usd": round(median_prem, 0) if median_prem else None,
        })

    return {
        "table_id": "A",
        "title": "Event frequency by qualification class × DTE bucket × era",
        "cohort": cohort,
        "coverage_window": "inferred from data",
        "n_sessions": n_days,
        "n_floor": N_FLOOR,
        "cells": cells,
    }


# ── Table B — vol>OI genuine-positioning rate ────────────────────────────────

def table_b(events_path: Path, eod_store: Path | None, sample_roots: list[str]) -> dict[str, Any]:
    """B: % of vol>OI events where next-session OI rose >= 50% of burst volume.

    Uses a stratified 40-root sample.  Requires the OI store.
    """
    log.info("Table B: vol>OI genuine-positioning rate (%d sample roots)", len(sample_roots))

    if eod_store is None:
        return {
            "table_id": "B",
            "title": "Vol>OI genuine-positioning rate (OI store required)",
            "cohort": "eod_proxy",
            "status": "CANNOT_COMPUTE",
            "reason": "thetadata_eod OI store not found; set THETADATA_EOD_DIR",
        }

    oi_dir = eod_store / "oi"

    # Load vol>OI events for sample roots
    needed = ["event_id", "root", "session_date", "exp", "strike", "right", "size", "era"]
    pf = pq.ParquetFile(events_path)
    ev_rows = []
    for batch in pf.iter_batches(batch_size=200_000, columns=needed + ["vol_gt_oi"]):
        df = batch.to_pandas()
        sub = df[(df["vol_gt_oi"].fillna(False)) & (df["root"].isin(sample_roots))]
        if len(sub):
            ev_rows.append(sub[needed])
    if not ev_rows:
        return {
            "table_id": "B",
            "title": "Vol>OI genuine-positioning rate",
            "cohort": "eod_proxy",
            "status": "CANNOT_COMPUTE",
            "reason": "No vol>OI events found for sample roots",
        }

    events = pd.concat(ev_rows, ignore_index=True)
    events["session_date"] = pd.to_datetime(events["session_date"]).dt.date
    events["exp"] = pd.to_datetime(events["exp"]).dt.date
    events["strike"] = events["strike"].astype(float)

    confirmed = 0
    no_oi = 0
    tested = 0
    era_results: dict[str, dict[str, int]] = {}

    for root in sample_roots:
        oi_root_dir = oi_dir / root
        if not oi_root_dir.exists():
            no_oi += len(events[events["root"] == root])
            continue

        oi_dfs = []
        for yf in sorted(oi_root_dir.glob("*.parquet")):
            try:
                oi_dfs.append(
                    pq.read_table(yf, columns=["expiration", "strike", "right", "date", "open_interest"])
                    .to_pandas()
                )
            except Exception:
                pass
        if not oi_dfs:
            no_oi += len(events[events["root"] == root])
            continue

        oi = pd.concat(oi_dfs, ignore_index=True)
        # OI store uses 'expiration'; cohort parquet uses 'exp' — normalise to 'exp'
        oi["exp"] = pd.to_datetime(oi["expiration"])
        oi["date"] = pd.to_datetime(oi["date"])
        oi["strike"] = oi["strike"].astype(float)
        # Compute next-day OI per contract via shift (vectorized, RAM-safe for per-root OI)
        oi_sorted = oi.sort_values(["exp", "strike", "right", "date"])
        oi_sorted["oi_next"] = oi_sorted.groupby(["exp", "strike", "right"])["open_interest"].shift(-1)

        root_ev = events[events["root"] == root].copy()
        root_ev["session_date"] = pd.to_datetime(root_ev["session_date"])
        root_ev["exp"] = pd.to_datetime(root_ev["exp"])

        # Vectorized merge: join event to OI row at (exp, strike, right, session_date=date)
        merged = root_ev.merge(
            oi_sorted[["exp", "strike", "right", "date", "open_interest", "oi_next"]].rename(
                columns={"date": "session_date", "open_interest": "oi_today"}
            ),
            on=["exp", "strike", "right", "session_date"],
            how="left",
        )

        testable = merged[merged["oi_today"].notna() & merged["oi_next"].notna()]
        no_oi += len(merged) - len(testable)

        burst = testable["size"].astype(float)
        oi_delta = testable["oi_next"].astype(float) - testable["oi_today"].astype(float)
        conf_mask = oi_delta >= 0.5 * burst

        for era, grp_idx in testable.groupby("era").groups.items():
            era_s = str(era)
            if era_s not in era_results:
                era_results[era_s] = {"confirmed": 0, "tested": 0}
            t = len(grp_idx)
            c = int(conf_mask.loc[grp_idx].sum())
            era_results[era_s]["tested"] += t
            era_results[era_s]["confirmed"] += c
            tested += t
            confirmed += c

    cells = []
    for era, r in sorted(era_results.items()):
        t = r["tested"]
        c = r["confirmed"]
        lo, hi = wilson_ci(c, t) if t >= N_FLOOR else (None, None)
        flag = "ERA-SPARSE" if t < N_FLOOR else None
        cells.append({
            "era": era,
            "n_tested": t,
            "n_confirmed": c,
            "rate": round(c / t, 4) if t else None,
            "ci_lo": round(lo, 4) if lo is not None else None,
            "ci_hi": round(hi, 4) if hi is not None else None,
            "flag": flag,
        })

    overall_lo, overall_hi = wilson_ci(confirmed, tested) if tested >= N_FLOOR else (None, None)
    return {
        "table_id": "B",
        "title": "Vol>OI genuine-positioning rate (next-session OI rose >= 50% of burst volume)",
        "cohort": "eod_proxy",
        "sample_design": f"{len(sample_roots)}-root stratified sample across size deciles",
        "n_events_total": len(events),
        "n_tested": tested,
        "n_no_oi": no_oi,
        "overall_rate": round(confirmed / tested, 4) if tested else None,
        "overall_ci_lo": round(overall_lo, 4) if overall_lo is not None else None,
        "overall_ci_hi": round(overall_hi, 4) if overall_hi is not None else None,
        "cells_by_era": cells,
    }


# ── Table C — roll contamination ─────────────────────────────────────────────

def table_c(events_path: Path, sample_roots: list[str]) -> dict[str, Any]:
    """C: % of vol>OI events with same-strike near-expiry (<= 35d earlier) volume spike same session."""
    log.info("Table C: roll contamination rate")
    needed = ["event_id", "root", "session_date", "exp", "strike", "right", "dte", "era"]
    pf = pq.ParquetFile(events_path)
    ev_rows = []
    for batch in pf.iter_batches(batch_size=200_000, columns=needed + ["vol_gt_oi"]):
        df = batch.to_pandas()
        sub = df[(df["vol_gt_oi"].fillna(False)) & (df["root"].isin(sample_roots))]
        if len(sub):
            ev_rows.append(sub[needed])
    if not ev_rows:
        return {
            "table_id": "C",
            "title": "Roll contamination rate",
            "cohort": "eod_proxy",
            "status": "CANNOT_COMPUTE",
            "reason": "No vol>OI events for sample roots",
        }

    events = pd.concat(ev_rows, ignore_index=True)
    events["session_date"] = pd.to_datetime(events["session_date"])
    events["exp"] = pd.to_datetime(events["exp"])
    events["strike"] = events["strike"].astype(float)

    # Vectorized self-join: for each event find same-session same-(strike,right) events
    # with a SHORTER expiry within 35 calendar days (roll-candidate).
    ev = events.copy()
    ev_left = ev.rename(columns={"event_id": "eid_l", "exp": "exp_l"})
    ev_right = ev[["event_id", "session_date", "root", "exp", "strike", "right"]].rename(
        columns={"event_id": "eid_r", "exp": "exp_r"}
    )
    # Self-join on (root, session_date, strike, right), different events
    paired = ev_left.merge(ev_right, on=["root", "session_date", "strike", "right"])
    paired = paired[paired["eid_l"] != paired["eid_r"]]
    paired = paired[paired["exp_r"] < paired["exp_l"]]  # other has EARLIER expiry
    paired["exp_diff_days"] = (paired["exp_l"] - paired["exp_r"]).dt.days
    paired = paired[paired["exp_diff_days"] <= 35]

    contaminated_set = set(paired["eid_l"].unique())
    ev["roll_contaminated"] = ev["event_id"].isin(contaminated_set)

    era_results: dict[str, dict[str, int]] = {}
    for era, grp in ev.groupby("era"):
        era_s = str(era)
        era_results[era_s] = {
            "contaminated": int(grp["roll_contaminated"].sum()),
            "tested": len(grp),
        }
    contaminated = int(ev["roll_contaminated"].sum())
    tested = len(ev)

    cells = []
    for era, r in sorted(era_results.items()):
        t = r["tested"]
        c = r["contaminated"]
        lo, hi = wilson_ci(c, t) if t >= N_FLOOR else (None, None)
        cells.append({
            "era": era,
            "n_tested": t,
            "n_contaminated": c,
            "rate": round(c / t, 4) if t else None,
            "ci_lo": round(lo, 4) if lo is not None else None,
            "ci_hi": round(hi, 4) if hi is not None else None,
            "flag": "ERA-SPARSE" if t < N_FLOOR else None,
        })

    overall_lo, overall_hi = wilson_ci(contaminated, tested) if tested >= N_FLOOR else (None, None)
    return {
        "table_id": "C",
        "title": "Roll contamination rate (vol>OI events with near-expiry same-strike spike same session)",
        "cohort": "eod_proxy",
        "sample_design": f"{len(sample_roots)}-root sample",
        "n_events_total": len(events),
        "n_tested": tested,
        "overall_contamination_rate": round(contaminated / tested, 4) if tested else None,
        "overall_ci_lo": round(overall_lo, 4) if overall_lo is not None else None,
        "overall_ci_hi": round(overall_hi, 4) if overall_hi is not None else None,
        "cells_by_era": cells,
    }


# ── Table D/E/F — tape_recon outcome tables ───────────────────────────────────

def _tape_outcome_table(
    table_id: str,
    title: str,
    events: pd.DataFrame,
    grades: pd.DataFrame,
    group_col: str,
    group_labels: dict[str, str],
    coverage_label: str,
) -> dict[str, Any]:
    """Generic outcome table for tape_recon cohort."""
    df = events.merge(grades, on="event_id", how="inner")
    cells = []
    for col_val, label in group_labels.items():
        # Support boolean, string, and callable keys for grouping
        if callable(col_val):
            grp = df[col_val(df)]
        elif isinstance(col_val, bool):
            grp = df[df[group_col].fillna(not col_val).astype(bool) == col_val]
        else:
            grp = df[df[group_col] == col_val]
        n = len(grp)
        r5 = grp["fwd_ret_5"].dropna()
        r21 = grp["fwd_ret_21"].dropna()
        n5 = len(r5)
        n21 = len(r21)
        cell_r5 = _rate_cell(int((r5 > 0).sum()), n5, {"median_ret": float(r5.median()) if n5 else None}) if n5 >= N_FLOOR else _sparse_cell(n5)
        cell_r21 = _rate_cell(int((r21 > 0).sum()), n21, {"median_ret": float(r21.median()) if n21 else None}) if n21 >= N_FLOOR else _sparse_cell(n21)
        ex5 = grp["spy_excess_5"].dropna()
        cells.append({
            "group": label,
            "n_events": n,
            "fwd_ret_5": cell_r5,
            "fwd_ret_21": cell_r21,
            "spy_excess_5_mean": round(float(ex5.mean()), 5) if len(ex5) >= N_FLOOR else None,
        })
    return {
        "table_id": table_id,
        "title": title,
        "cohort": "tape_recon",
        "coverage_window": coverage_label,
        "n_graded": len(df),
        "n_floor": N_FLOOR,
        "cells": cells,
    }


def table_d(events: pd.DataFrame, grades: pd.DataFrame, coverage_label: str) -> dict[str, Any]:
    """D: Sweep vs non-sweep outcomes (tape_recon)."""
    log.info("Table D: sweep vs non-sweep outcomes")
    return _tape_outcome_table(
        "D",
        "Sweep vs non-sweep outcomes",
        events,
        grades,
        group_col="swept",
        group_labels={True: "swept", False: "non-swept"},
        coverage_label=coverage_label,
    )


def table_e(events: pd.DataFrame, grades: pd.DataFrame, coverage_label: str) -> dict[str, Any]:
    """E: Execution side at-ask vs at-bid outcomes (tape_recon)."""
    log.info("Table E: at-ask vs at-bid outcomes")
    # Derive execution side from ask_share / bid_share
    ev = events.copy()
    ev["exec_side"] = "mixed"
    ev.loc[ev["ask_share"].fillna(0) >= 0.6, "exec_side"] = "at-ask"
    ev.loc[ev["bid_share"].fillna(0) >= 0.6, "exec_side"] = "at-bid"
    return _tape_outcome_table(
        "E",
        "Execution side (at-ask vs at-bid) outcomes — quote-rule classification",
        ev,
        grades,
        group_col="exec_side",
        group_labels={"at-ask": "at-ask (ask_share>=0.60)", "at-bid": "at-bid (bid_share>=0.60)", "mixed": "mixed"},
        coverage_label=coverage_label,
    )


def table_f(events: pd.DataFrame, grades: pd.DataFrame, coverage_label: str) -> dict[str, Any]:
    """F: Repeat-cluster vs single-print outcomes (tape_recon)."""
    log.info("Table F: repeat-cluster vs single-print outcomes")
    return _tape_outcome_table(
        "F",
        "Repeat-cluster vs single-print outcomes",
        events,
        grades,
        group_col="repeated",
        group_labels={True: "repeated-cluster", False: "single-print"},
        coverage_label=coverage_label,
    )


# ── Table G — deep-OTM outcome distribution ──────────────────────────────────

def table_g(
    eod_events: pd.DataFrame,
    eod_grades: pd.DataFrame,
    tape_events: pd.DataFrame,
    tape_grades: pd.DataFrame,
    coverage_label_eod: str,
    coverage_label_tape: str,
) -> dict[str, Any]:
    """G: Deep-OTM outcome distribution (both cohorts where moneyness data allows).

    mny_bucket='unknown' for both cohorts currently; uses dte_bucket as proxy.
    When moneyness data is available (mny_bucket != 'unknown'), recompute.
    """
    log.info("Table G: deep-OTM outcome distribution")

    # Check mny_bucket availability in eod cohort
    mny_vals = eod_events["mny_bucket"].fillna("unknown").unique()
    mny_known = [v for v in mny_vals if v != "unknown"]

    note = (
        "mny_bucket='unknown' for all rows in both cohorts (no close-price alignment in store). "
        "Deep-OTM proxy: dte_bucket='90p' (long-dated) and dte_bucket='0d' (0DTE) as distribution anchors. "
        "Recompute when moneyness store is available."
    )

    cells = []
    # eod_proxy by dte_bucket proxy
    for cohort_label, ev_df, gr_df, cov in [
        ("eod_proxy", eod_events, eod_grades, coverage_label_eod),
        ("tape_recon", tape_events, tape_grades, coverage_label_tape),
    ]:
        _assert_single_source(ev_df, cohort_label)
        df = ev_df.merge(gr_df, on="event_id", how="inner")
        for dte_bkt in ["0d", "1_7d", "8_30d", "31_90d", "90p"]:
            grp = df[df["dte_bucket"] == dte_bkt]
            n = len(grp)
            r21 = grp["fwd_ret_21"].dropna()
            n21 = len(r21)
            cell_r21 = (
                _rate_cell(int((r21 > 0).sum()), n21, {"median_ret": round(float(r21.median()), 5)})
                if n21 >= N_FLOOR
                else _sparse_cell(n21)
            )
            cells.append({
                "cohort": cohort_label,
                "dte_bucket": dte_bkt,
                "n_events": n,
                "fwd_ret_21": cell_r21,
            })

    return {
        "table_id": "G",
        "title": "Outcome distribution by DTE bucket (deep-OTM proxy — mny_bucket unavailable)",
        "note": note,
        "n_floor": N_FLOOR,
        "cells": cells,
    }


# ── Table H — 0DTE/index vs single-name short-DTE ────────────────────────────

def table_h(events: pd.DataFrame, grades: pd.DataFrame) -> dict[str, Any]:
    """H: 0DTE/index vs single-name short-DTE comparison (eod_proxy)."""
    log.info("Table H: 0DTE/index vs single-name short-DTE")
    _assert_single_source(events, "eod_proxy")

    INDEX_ROOTS = {"SPX", "SPXW", "NDX", "NDXP", "RUT", "RUTW"}
    ev = events.copy()
    ev["is_index"] = ev["root"].isin(INDEX_ROOTS)
    ev["is_0dte"] = ev["zerodte"].fillna(False).astype(bool)

    groups = {
        "0DTE_index": ev[ev["is_0dte"] & ev["is_index"]],
        "0DTE_single_name": ev[ev["is_0dte"] & ~ev["is_index"]],
        "short_DTE_index": ev[ev["dte_bucket"].isin(["1_7d", "8_30d"]) & ev["is_index"]],
        "short_DTE_single_name": ev[ev["dte_bucket"].isin(["1_7d", "8_30d"]) & ~ev["is_index"]],
    }

    cells = []
    for label, grp in groups.items():
        n = len(grp)
        voi_n = int((grp["vol_gt_oi"].fillna(False)).sum())
        lo, hi = wilson_ci(voi_n, n) if n >= N_FLOOR else (None, None)

        joined = grp.merge(grades, on="event_id", how="inner")
        r5 = joined["fwd_ret_5"].dropna()
        n5 = len(r5)
        cell_r5 = (
            _rate_cell(int((r5 > 0).sum()), n5, {"median_ret": round(float(r5.median()), 5)})
            if n5 >= N_FLOOR
            else _sparse_cell(n5)
        )

        cells.append({
            "group": label,
            "n_events": n,
            "vol_gt_oi_rate": {
                "n": n, "k": voi_n, "rate": round(voi_n / n, 4) if n else None,
                "ci_lo": round(lo, 4) if lo else None, "ci_hi": round(hi, 4) if hi else None,
                "flag": "ERA-SPARSE" if n < N_FLOOR else None,
            },
            "fwd_ret_5": cell_r5,
            "note_0dte_voi": (
                "0DTE contracts start each session at OI=0 → vol>OI is trivially true; "
                "vol_gt_oi_rate=1.00 is a structural artifact, not a signal"
                if "0DTE" in label else None
            ),
        })

    return {
        "table_id": "H",
        "title": "0DTE/index vs single-name short-DTE: vol>OI flag rate + forward-outcome contrast",
        "cohort": "eod_proxy",
        "n_floor": N_FLOOR,
        "cells": cells,
    }


# ── Table I — era-stratified base rates ───────────────────────────────────────

def table_i(events: pd.DataFrame, grades: pd.DataFrame) -> dict[str, Any]:
    """I: Era-stratified base rates (eod_proxy) — the regime-shift check."""
    log.info("Table I: era-stratified base rates")
    _assert_single_source(events, "eod_proxy")

    df = events.merge(grades, on="event_id", how="inner")
    cells = []
    for era, grp in df.groupby("era"):
        n = len(grp)
        r5 = grp["fwd_ret_5"].dropna()
        r21 = grp["fwd_ret_21"].dropna()
        ex5 = grp["spy_excess_5"].dropna()
        ex21 = grp["spy_excess_21"].dropna()
        n5, n21 = len(r5), len(r21)

        cell_r5 = _rate_cell(int((r5 > 0).sum()), n5, {"median_ret": round(float(r5.median()), 5)}) if n5 >= N_FLOOR else _sparse_cell(n5)
        cell_r21 = _rate_cell(int((r21 > 0).sum()), n21, {"median_ret": round(float(r21.median()), 5)}) if n21 >= N_FLOOR else _sparse_cell(n21)

        cells.append({
            "era": str(era),
            "n_ok_graded": n,
            "fwd_ret_5": cell_r5,
            "fwd_ret_21": cell_r21,
            "spy_excess_5_mean": round(float(ex5.mean()), 5) if len(ex5) >= N_FLOOR else None,
            "spy_excess_21_mean": round(float(ex21.mean()), 5) if len(ex21) >= N_FLOOR else None,
        })

    return {
        "table_id": "I",
        "title": "Era-stratified base rates (eod_proxy) — regime-shift check, pre/post-2020 mandatory",
        "cohort": "eod_proxy",
        "coverage_window": "2012-06 to 2026-07",
        "n_floor": N_FLOOR,
        "note": "Pre/post-2020 split mandatory per mlquants 3-decade options-volume sign-flip (commission-free onset ~2019Q4)",
        "cells": cells,
    }


# ── Table J — premium-size decile vs outcome ──────────────────────────────────

def table_j(events: pd.DataFrame, grades: pd.DataFrame) -> dict[str, Any]:
    """J: Premium-size decile vs outcome within class (eod_proxy)."""
    log.info("Table J: premium-size decile vs outcome")
    _assert_single_source(events, "eod_proxy")

    df = events.merge(grades, on="event_id", how="inner")
    try:
        df["prem_decile"] = pd.qcut(
            df["premium"], 10, labels=[f"D{i+1}" for i in range(10)], duplicates="drop"
        )
    except Exception as exc:
        return {
            "table_id": "J",
            "title": "Premium-size decile vs outcome",
            "cohort": "eod_proxy",
            "status": "CANNOT_COMPUTE",
            "reason": str(exc),
        }

    cells = []
    for dec, grp in df.groupby("prem_decile", observed=True):
        r21 = grp["fwd_ret_21"].dropna()
        ex21 = grp["spy_excess_21"].dropna()
        n21 = len(r21)
        prem_grp = df[df["prem_decile"] == dec]["premium"]
        cell_r21 = (
            _rate_cell(int((r21 > 0).sum()), n21, {"median_ret": round(float(r21.median()), 5)})
            if n21 >= N_FLOOR
            else _sparse_cell(n21)
        )
        cells.append({
            "decile": str(dec),
            "premium_range_usd": {
                "lo": round(float(prem_grp.min()), 0),
                "hi": round(float(prem_grp.max()), 0),
                "median": round(float(prem_grp.median()), 0),
            },
            "n_ok_graded": len(grp),
            "fwd_ret_21": cell_r21,
            "spy_excess_21_mean": round(float(ex21.mean()), 5) if len(ex21) >= N_FLOOR else None,
        })

    return {
        "table_id": "J",
        "title": "Premium-size decile vs forward outcome (fwd_ret_21, spy_excess_21)",
        "cohort": "eod_proxy",
        "n_floor": N_FLOOR,
        "cells": cells,
    }


# ── Table K — crowdedness vs outcome ─────────────────────────────────────────

def table_k(events: pd.DataFrame, grades: pd.DataFrame) -> dict[str, Any]:
    """K: Crowdedness (events per root per trailing 7 sessions, terciles) vs outcome."""
    log.info("Table K: crowdedness vs outcome")
    _assert_single_source(events, "eod_proxy")

    ev = events.copy()
    ev["session_date"] = pd.to_datetime(ev["session_date"])
    ev["date_only"] = ev["session_date"].dt.date

    # Daily event count per root (proxy for crowdedness)
    daily_counts = (
        ev.groupby(["root", "date_only"]).size().reset_index(name="events_this_day")
    )
    ev = ev.merge(daily_counts, on=["root", "date_only"])

    p33 = float(daily_counts["events_this_day"].quantile(0.33))
    p67 = float(daily_counts["events_this_day"].quantile(0.67))

    # duplicates='drop' handles the case where p33 == p67 (e.g. all-same-count data)
    bins_uniq = sorted({0.0, p33, p67, float("inf")})
    n_bins = len(bins_uniq) - 1
    labels_map = ["low", "mid", "high"][:n_bins]
    ev["crowd_tercile"] = pd.cut(
        ev["events_this_day"],
        bins=bins_uniq,
        labels=labels_map,
        duplicates="drop",
    )

    df = ev.merge(grades, on="event_id", how="inner")
    cells = []
    for terc, grp in df.groupby("crowd_tercile", observed=True):
        r21 = grp["fwd_ret_21"].dropna()
        ex21 = grp["spy_excess_21"].dropna()
        n21 = len(r21)
        cell_r21 = (
            _rate_cell(int((r21 > 0).sum()), n21, {"median_ret": round(float(r21.median()), 5)})
            if n21 >= N_FLOOR
            else _sparse_cell(n21)
        )
        cells.append({
            "tercile": str(terc),
            "events_per_root_day_range": (
                f"<={p33:.0f}" if str(terc) == "low"
                else f"{p33:.0f}–{p67:.0f}" if str(terc) == "mid"
                else f">{p67:.0f}"
            ),
            "n_ok_graded": len(grp),
            "fwd_ret_21": cell_r21,
            "spy_excess_21_mean": round(float(ex21.mean()), 5) if len(ex21) >= N_FLOOR else None,
        })

    return {
        "table_id": "K",
        "title": "Crowdedness (events/root/day tercile, 7-session proxy) vs outcome",
        "cohort": "eod_proxy",
        "n_floor": N_FLOOR,
        "tercile_breakpoints": {"p33": round(p33, 1), "p67": round(p67, 1)},
        "note": "Crowdedness approximated as daily events-per-root; 7-session rolling requires timestamp joins. Recompute with full rolling window for FS-3.",
        "cells": cells,
    }


# ── Markdown rendering ────────────────────────────────────────────────────────

def _md_rate(cell: dict) -> str:
    if cell.get("flag") == "ERA-SPARSE":
        return f"ERA-SPARSE (n={cell['n']})"
    if cell.get("stat") is None and cell.get("rate") is None:
        return "—"
    rate = cell.get("rate", 0.0) or 0.0
    ci_lo = cell.get("ci_lo", 0.0) or 0.0
    ci_hi = cell.get("ci_hi", 1.0) or 1.0
    n = cell.get("n", 0)
    return f"{rate:.3f} [{ci_lo:.3f}–{ci_hi:.3f}] n={n}"


def print_markdown_tables(tables: list[dict]) -> None:
    for t in tables:
        print(f"\n### Table {t.get('table_id','?')}: {t.get('title','')}")
        print(f"Cohort: {t.get('cohort','—')}  |  Coverage: {t.get('coverage_window', t.get('coverage_label','—'))}")
        if t.get("status") == "CANNOT_COMPUTE":
            print(f"> CANNOT COMPUTE: {t.get('reason','')}")
            continue
        if t.get("note"):
            print(f"> Note: {t['note']}")
        cells = t.get("cells", t.get("cells_by_era", []))
        if not cells:
            print("(no cells)")
            continue
        # Simple key-value dump
        for cell in cells:
            line_parts = []
            for k, v in cell.items():
                if isinstance(v, dict):
                    if v.get("flag") == "ERA-SPARSE":
                        line_parts.append(f"{k}: ERA-SPARSE (n={v['n']})")
                    elif "rate" in v and v["rate"] is not None:
                        line_parts.append(
                            f"{k}={v['rate']:.3f} [{v.get('ci_lo',0.0):.3f}–{v.get('ci_hi',1.0):.3f}] n={v.get('n',0)}"
                        )
                elif isinstance(v, float):
                    line_parts.append(f"{k}={v:.4f}")
                else:
                    line_parts.append(f"{k}={v}")
            print("  " + " | ".join(line_parts))


# ── main ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    import lib.procutil as procutil  # import late so tests can skip

    parser = argparse.ArgumentParser(description="FS-2 flow-signal atlas builder")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Override output directory (default: FLOW_SIGNALS_DIR/atlas/)",
    )
    parser.add_argument(
        "--b-sample-roots",
        type=int,
        default=40,
        help="Number of roots to sample for Table B (default: 40)",
    )
    parser.add_argument(
        "--skip-oi-tables",
        action="store_true",
        help="Skip Table B and C (require OI store reads, can be slow)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    flow_dir = _flow_signals_dir()
    atlas_d = Path(args.output_dir) if args.output_dir else _atlas_dir()
    atlas_d.mkdir(parents=True, exist_ok=True)
    eod_store = _eod_store_root()

    eod_ev_path = flow_dir / "cohort_eod_proxy.parquet"
    eod_gr_path = flow_dir / "cohort_eod_proxy_grades.parquet"
    tape_ev_path = flow_dir / "cohort_tape_recon.parquet"
    tape_gr_path = flow_dir / "cohort_tape_recon_grades.parquet"

    if not eod_ev_path.exists():
        log.error("cohort_eod_proxy.parquet not found at %s — run ops_flow_cohorts.py eod_proxy first", eod_ev_path)
        procutil.hard_exit(1)

    # ── Load eod_proxy events + ok grades ────────────────────────────────────
    log.info("Loading eod_proxy events...")
    eod_ev_cols = [
        "event_id", "era", "dte_bucket", "mny_bucket", "vol_gt_oi",
        "premium", "session_date", "source", "root", "zerodte",
    ]
    eod_events = _load_events(eod_ev_path, eod_ev_cols)
    log.info("  eod_proxy events: %d", len(eod_events))

    log.info("Loading eod_proxy grades...")
    eod_grades = _load_ok_grades(eod_gr_path)
    log.info("  ok grades: %d", len(eod_grades))

    # ── Load tape_recon events + grades ──────────────────────────────────────
    tape_ev_cols = [
        "event_id", "dte_bucket", "mny_bucket", "swept", "repeated",
        "ask_share", "bid_share", "premium", "session_date", "source", "root",
    ]
    tape_events = pd.DataFrame(columns=tape_ev_cols)
    tape_grades = pd.DataFrame()
    tape_coverage_label = "accruing — no tape_recon parquet found"

    if tape_ev_path.exists():
        log.info("Loading tape_recon events...")
        tape_events = _load_events(tape_ev_path, tape_ev_cols)
        log.info("  tape_recon events: %d", len(tape_events))
        if tape_gr_path.exists():
            log.info("Loading tape_recon grades...")
            tape_grades = _load_ok_grades(tape_gr_path)
            log.info("  tape_recon ok grades: %d", len(tape_grades))
        tape_coverage_label = "SPY 2022-2023, accruing (tape_recon multi-day sweep in progress)"
    else:
        log.warning("tape_recon parquet not found — Tables D/E/F will be marked accruing")

    # ── Stratify sample roots for B/C ────────────────────────────────────────
    if not args.skip_oi_tables:
        log.info("Stratifying %d sample roots for Tables B/C...", args.b_sample_roots)
        root_counts: dict[str, int] = {}
        pf_tmp = pq.ParquetFile(eod_ev_path)
        for batch in pf_tmp.iter_batches(batch_size=200_000, columns=["root", "vol_gt_oi"]):
            df_tmp = batch.to_pandas()
            for root, grp in df_tmp[df_tmp["vol_gt_oi"].fillna(False)].groupby("root"):
                root_counts[root] = root_counts.get(root, 0) + len(grp)
        root_df = pd.DataFrame([{"root": r, "n": v} for r, v in root_counts.items()])
        root_df = root_df.sort_values("n")
        n_deciles = 10
        root_df["decile"] = pd.qcut(
            root_df["n"], n_deciles, labels=[f"D{i+1}" for i in range(n_deciles)], duplicates="drop"
        )
        sample_roots: list[str] = []
        per_decile = max(1, args.b_sample_roots // n_deciles)
        for _, grp in root_df.groupby("decile", observed=True):
            picks = grp.sample(min(per_decile, len(grp)), random_state=42)
            sample_roots.extend(picks["root"].tolist())
        log.info("  Sample roots (%d): %s", len(sample_roots), sample_roots[:10])
    else:
        sample_roots = []

    # ── Compute tables ────────────────────────────────────────────────────────
    tables: list[dict] = []

    # A
    t_a = table_a(eod_ev_path, "eod_proxy")
    tables.append(t_a)

    # B
    if args.skip_oi_tables:
        t_b: dict[str, Any] = {
            "table_id": "B",
            "title": "Vol>OI genuine-positioning rate (skipped with --skip-oi-tables)",
            "cohort": "eod_proxy",
            "status": "SKIPPED",
        }
    else:
        t_b = table_b(eod_ev_path, eod_store, sample_roots)
    tables.append(t_b)

    # C
    if args.skip_oi_tables or len(sample_roots) == 0:
        t_c: dict[str, Any] = {
            "table_id": "C",
            "title": "Roll contamination rate (skipped with --skip-oi-tables)",
            "cohort": "eod_proxy",
            "status": "SKIPPED",
        }
    else:
        # Use a smaller subset of sample_roots (5) for speed
        t_c = table_c(eod_ev_path, sample_roots[:5])
    tables.append(t_c)

    # D/E/F (tape_recon)
    if len(tape_events) > 0 and len(tape_grades) > 0:
        tables.append(table_d(tape_events, tape_grades, tape_coverage_label))
        tables.append(table_e(tape_events, tape_grades, tape_coverage_label))
        tables.append(table_f(tape_events, tape_grades, tape_coverage_label))
    else:
        for tid, title in [
            ("D", "Sweep vs non-sweep outcomes"),
            ("E", "Execution side (at-ask vs at-bid) outcomes"),
            ("F", "Repeat-cluster vs single-print outcomes"),
        ]:
            tables.append({
                "table_id": tid,
                "title": title,
                "cohort": "tape_recon",
                "status": "ACCRUING",
                "coverage_window": tape_coverage_label,
                "note": "tape_recon cohort empty or grades not found — re-run when sweep is further along",
            })

    # G
    tables.append(
        table_g(
            eod_events, eod_grades, tape_events, tape_grades,
            "2012-06 to 2026-07", tape_coverage_label,
        )
    )

    # H
    tables.append(table_h(eod_events, eod_grades))

    # I
    tables.append(table_i(eod_events, eod_grades))

    # J
    tables.append(table_j(eod_events, eod_grades))

    # K
    tables.append(table_k(eod_events, eod_grades))

    # ── Write JSON ────────────────────────────────────────────────────────────
    out_path = atlas_d / "atlas_tables.json"
    payload = {
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "generator": "scripts/ops_flow_atlas.py",
        "n_floor": N_FLOOR,
        "cohort_law": "FS-R4 — tables computed per-cohort; no pooling",
        "tables": tables,
    }
    with open(out_path, "w") as fh:
        json.dump(payload, fh, indent=2, default=str)
    log.info("Atlas written to %s", out_path)

    # ── Print markdown ────────────────────────────────────────────────────────
    print_markdown_tables(tables)

    procutil.hard_exit(0)


if __name__ == "__main__":
    main()
