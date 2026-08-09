"""Coverage-regression refusal for recompute-in-place engine stores.

hk_run / china_run recompute their full regime history every run and overwrite
``data/<region>_regime/regime_history.parquet``. The weekly lane then discards
those ``data/`` writes (weekly.yml's W0b unstage of asia-close-owned paths)
while still shipping the ``site/`` artifacts built FROM the recompute — so a
recompute degraded by a transient input ships a timeline that contradicts the
committed store it sits next to. 2026-08-08: a stale runner-workspace
constituent-close cache plus the 40-bday macro ffill runout NaN'd the HK
inflation axis for 9 sessions; commit 901282ec209 shipped
site/hk_regime_timeline.json with 9 trailing nulls while the committed parquet
in the same tree had values on every one of those dates, and the nulls crashed
the landing hub.

The guard compares the fresh recompute against the store it is about to
overwrite and REFUSES (raises) when previously-computed cells have gone missing
or the history's end has moved backwards — both are input-plane degradation,
never new information. Callers treat the raise like any engine failure
(build_hk/build_china skip their pages), so the previous committed state keeps
serving and the next healthy run heals everything. Genuinely new dates may
still carry NaN (an honest "not computable yet" ships; the client null-guard
renders it), and value CHANGES on historical dates pass — recalibration and
input revisions are legitimate.

A legitimate permanent revision that really does null historical cells (e.g. an
upstream series is withdrawn) is unblocked by setting
``REGIME_ALLOW_COVERAGE_REGRESSION=1`` for one run.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

ESCAPE_ENV = "REGIME_ALLOW_COVERAGE_REGRESSION"

# Columns whose NULLNESS ENCODES STATE rather than availability: pending_quad
# is null exactly when no quad flip is pending, so any legitimate value drift
# (recalibration, revised inputs) relocates its non-null episodes. Guarding it
# would wedge every honest recompute; availability columns (scores, quad,
# liquidity, cycle, …) are the artifact contract the guard exists to protect.
STATE_NULL_COLS = ("pending_quad",)


def _span(mask: pd.Series) -> str:
    hit = mask.index[mask]
    first, last = hit[0], hit[-1]
    fmt = (lambda v: f"{v:%Y-%m-%d}") if isinstance(first, pd.Timestamp) else str
    return f"{fmt(first)}..{fmt(last)}"


def check_coverage_regression(new: pd.DataFrame, path: Path, name: str) -> None:
    """Refuse to overwrite ``path`` when ``new`` regresses its coverage.

    Raises RuntimeError (after a line-start ``::warning`` annotation) when any
    cell that is non-null in the existing store is null in ``new`` on the same
    date, or when ``new`` ends before the existing store does. No-op when the
    store does not exist yet, cannot be read, or ``REGIME_ALLOW_COVERAGE_REGRESSION=1``
    is set (the warning still prints so the revision is on the record).
    """
    if not path.exists():
        return
    try:
        old = pd.read_parquet(path)
    except Exception:
        return  # unreadable previous store — nothing to regress against

    problems = []
    if len(old.index) and len(new.index) and new.index.max() < old.index.max():
        problems.append(
            f"history end moved backwards ({new.index.max()} < {old.index.max()})")

    idx = new.index.intersection(old.index)
    cols = [c for c in new.columns
            if c in old.columns and c not in STATE_NULL_COLS]
    if len(idx) and cols:
        regressed = old.loc[idx, cols].notna() & new.loc[idx, cols].isna()
        regressed = regressed.sort_index()
        n = int(regressed.values.sum())
        if n:
            detail = "; ".join(
                f"{c}: {int(regressed[c].sum())} cells ({_span(regressed[c])})"
                for c in cols if regressed[c].any())
            problems.append(f"{n} previously-computed cells went null — {detail}")

    if not problems:
        return
    msg = (f"{name} regime recompute regresses coverage vs {path.name}: "
           + " | ".join(problems)
           + f" — degraded transient input; refusing to overwrite the store or ship "
             f"artifacts built from it (set {ESCAPE_ENV}=1 for a legitimate revision)")
    # House law: GitHub annotations must START the line via a bare print —
    # loggers prefix the level name and GitHub silently drops the annotation
    # (tests/test_gh_annotation_line_start.py).
    print(f"::warning title={name}-regime-coverage-regression::{msg}", flush=True)
    if os.environ.get(ESCAPE_ENV) == "1":
        return
    raise RuntimeError(msg)
