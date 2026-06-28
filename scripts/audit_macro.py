"""End-of-collection data-quality audit for MACRO series stores.

Audits the macro time-series groups (``fred``, ``china_macro``, ``eia`` by default; override
via ``cfg['macro_groups']``). Each group is one auditable *universe*. Per series we run four
deterministic checks:

  A) BACKWARDS-REVISION (HARD FAIL) — the headline integrity check. Today's frame is compared,
     on the overlap of *settled* historical dates, to a stored baseline snapshot. A settled value
     that moved by more than ``macro_revision_alert_pct`` AND by more than a level-aware absolute
     floor is a real backwards revision (statistical agencies do legitimately revise the most
     recent vintages, so a trailing UNSETTLED window is excluded). The dual relative-AND-absolute
     test is essential: a series that sits near or crosses zero (a YoY rate, a 2s10s spread) would
     otherwise produce an enormous relative % from a meaningless sub-noise wiggle. After the
     comparison the baseline is overwritten with the current frame.
  B) INF (HARD FAIL) — any +/-inf in a numeric column is gross corruption.
  C) GAPS (FLAG, log only) — cadence-aware holes in the RECENT window. Macro calendars are
     structurally irregular (9/11; China combines Jan+Feb statistics so there is always a Dec->Mar
     hole; LPR prints monthly; sparse 1980s EIA), so a gap is "look at this", NOT an abort-the-build
     failure. The hard-fail integrity teeth are the revision check; gaps are surfaced, not fatal.
  D) STALE (FLAG, log only) — last observation older than ``macro_stale_days`` (+cadence).
  E) Z-OUTLIER (FLAG, log only) — the latest first-difference is an extreme move vs the series' own
     change distribution.

READ-ONLY contract: this audit NEVER writes to the source data stores. The SOLE sanctioned write
outside ``data/quality/`` is to ``data/quality/baselines/<group>/<safe>.parquet`` — the revision
baseline snapshot. It tracks the latest values so a revision is caught exactly once, then absorbed:
re-running immediately finds baseline == current and reports zero revisions (idempotent).

Run as a module:  ``python -m scripts.audit_macro``  (writes ``data/quality/macro_audit.json``).
Importable as:     ``from scripts import audit_macro``.
"""
from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from scripts import audit_common as ac

log = logging.getLogger("audit.macro")

# Default macro groups (each one universe); cfg['macro_groups'] overrides.
DEFAULT_GROUPS = ["fred", "china_macro", "eia"]

# Cadence-aware gap thresholds. The spec's nominal spacing is 2 business days (daily) / 1 month
# (monthly); each threshold = that nominal spacing PLUS a holiday / publication-delay tolerance so
# a long weekend or a late government print does not read as a hole. Gaps are FLAGS (not fails).
DAILY_GAP_BDAYS = 3        # nominal 2 business days + 1 for holidays / late publication
WEEKLY_GAP_DAYS = 16       # nominal 7 calendar days + tolerance (skipped week, late release)
MONTHLY_GAP_DAYS = 45      # nominal ~31 calendar days + ~2wk publication-delay tolerance
QUARTERLY_GAP_DAYS = 130   # nominal ~92 calendar days + tolerance

# Gaps are evaluated only over the recent edge — deep-history holes (9/11, China's structural
# Jan/Feb combine, sparse 1980s data) are immutable and not actionable. ~18 months keeps enough
# recent observations for every cadence (daily ~370, monthly ~18, quarterly ~6) to spot a hole.
GAP_LOOKBACK_DAYS = 540

# Backwards-revision absolute floor: a flagged revision must move by more than this FRACTION of the
# series' own typical magnitude, on top of clearing macro_revision_alert_pct. Without it a series
# crossing zero yields a huge relative % from a meaningless absolute change (false hard fail).
_REV_ABS_FRAC = 1e-3

# How many distinct reasons to surface per revised series (the .fail records the series once;
# multiple reasons accumulate onto that one entry).
_MAX_REASONS = 5


def _safe(name: str) -> str:
    """Replicate the lib.store unsafe-char map so a passed-in data_dir override resolves correctly."""
    return name.replace("^", "_").replace("=", "_").replace("/", "_").replace(" ", "_")


def _numeric_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce to the numeric columns only — revision math is meaningless on text columns."""
    num = df.apply(pd.to_numeric, errors="coerce")
    keep = [c for c in num.columns if num[c].notna().any()]
    return num[keep]


def _check_revision(u: ac.Universe, series: str, cur_num: pd.DataFrame,
                    baseline_path: Path, cadence: float, cfg: dict) -> None:
    """Compare today's settled history to the stored baseline, then overwrite the baseline.

    First run (no baseline) just seeds and never fails. The trailing UNSETTLED window is excluded
    because recent vintages legitimately revise; settle_days = max(3*cadence, 35)."""
    alert = float(cfg["macro_revision_alert_pct"])
    if baseline_path.exists():
        try:
            base = pd.read_parquet(baseline_path)
        except Exception as err:  # corrupt baseline — reseed below, do not fail the data
            log.warning("macro: unreadable baseline %s (%s) — reseeding", baseline_path, err)
            base = None
        if base is not None and len(cur_num.index):
            base = ac.clean_index(base)
            settle_days = max(3.0 * cadence if np.isfinite(cadence) else 31.0, 35.0)
            series_max = cur_num.index.max()
            cutoff = series_max - pd.Timedelta(days=settle_days)
            shared_dates = cur_num.index.intersection(base.index)
            settled_dates = shared_dates[shared_dates <= cutoff]
            shared_cols = [c for c in cur_num.columns if c in base.columns]
            reasons: list[str] = []
            for col in shared_cols:
                cur_c = cur_num.loc[settled_dates, col]
                base_c = pd.to_numeric(base.loc[settled_dates, col], errors="coerce")
                both = cur_c.notna() & base_c.notna()
                if not both.any():
                    continue
                cv = cur_c[both]
                bv = base_c[both]
                # Level-aware absolute floor: a revision must be material vs the series' OWN typical
                # magnitude (median |level| over the full column), not just a big relative % off a
                # near-zero base. Both conditions must hold to flag (see _REV_ABS_FRAC).
                vals = cur_num[col].to_numpy(dtype="float64", na_value=np.nan)
                vals = vals[np.isfinite(vals)]
                typ = float(np.median(np.abs(vals))) if len(vals) else 0.0
                abs_floor = max(_REV_ABS_FRAC * typ, 1e-9)
                diff = (cv - bv).abs()
                rel = diff / bv.abs().clip(lower=abs_floor)
                hits = (rel * 100.0 > alert) & (diff > abs_floor)
                for dt in cv.index[hits.to_numpy()]:
                    reasons.append(
                        f"backwards revision: {col}@{pd.Timestamp(dt).date()} "
                        f"{bv.loc[dt]:.6g}->{cv.loc[dt]:.6g} ({rel.loc[dt] * 100:.1f}%)")
                    if len(reasons) >= _MAX_REASONS:
                        break
                if len(reasons) >= _MAX_REASONS:
                    break
            for r in reasons:
                u.fail(series, r)
    # ALWAYS (re)seed the baseline with today's numeric frame — makes the next run idempotent.
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    cur_num.to_parquet(baseline_path)


def _check_gaps(u: ac.Universe, series: str, idx: pd.DatetimeIndex, lab: str, asof: date) -> None:
    """Cadence-aware gap detection over the RECENT window — a FLAG, never a fail (macro calendars
    are structurally irregular). Unknown cadence is unauditable for gaps — skip it."""
    start = pd.Timestamp(asof) - pd.Timedelta(days=GAP_LOOKBACK_DAYS)
    pos = int(idx.searchsorted(start))
    recent = idx[max(0, pos - 1):]            # keep one pre-window point to catch a boundary hole
    if lab == "daily":
        gaps = ac.business_gaps_over(recent, DAILY_GAP_BDAYS)
        thresh, unit = DAILY_GAP_BDAYS, "bd"
    elif lab == "weekly":
        gaps = ac.calendar_gaps_over(recent, WEEKLY_GAP_DAYS)
        thresh, unit = WEEKLY_GAP_DAYS, "d"
    elif lab == "monthly":
        gaps = ac.calendar_gaps_over(recent, MONTHLY_GAP_DAYS)
        thresh, unit = MONTHLY_GAP_DAYS, "d"
    elif lab == "quarterly":
        gaps = ac.calendar_gaps_over(recent, QUARTERLY_GAP_DAYS)
        thresh, unit = QUARTERLY_GAP_DAYS, "d"
    else:
        return
    if gaps:
        prev, cur, n = max(gaps, key=lambda g: g[2])
        u.flag(series, "gap", f"{len(gaps)} recent gap(s) > {thresh}{unit} "
                              f"(largest {n}{unit} at {prev.date()}->{cur.date()})")


def _check_stale(u: ac.Universe, series: str, idx: pd.DatetimeIndex, cadence: float,
                 lab: str, asof: date, cfg: dict) -> None:
    """Last observation too old (FLAG only). Threshold widens by the cadence so a quarterly
    series is not flagged just for being quarterly."""
    last = idx.max()
    thresh = float(cfg["macro_stale_days"]) + (cadence if np.isfinite(cadence) else 0.0)
    age = (asof - last.date()).days
    if age > thresh:
        c = f"{cadence:.0f}" if np.isfinite(cadence) else "?"
        u.flag(series, "stale", f"last {last.date()}, {age}d old (cadence ~{c}d, {lab})")


def _check_inf(u: ac.Universe, series: str, num: pd.DataFrame) -> None:
    """+/-inf in any numeric column is gross corruption (HARD FAIL)."""
    for col in num.columns:
        if ac.has_bad_floats(num[col]):
            u.fail(series, f"inf in {col}")


def _check_zoutlier(u: ac.Universe, series: str, num: pd.DataFrame, cfg: dict) -> None:
    """Latest first-difference is extreme vs the series' own change distribution (FLAG only)."""
    zlim = float(cfg["macro_outlier_z"])
    for col in num.columns:
        diffs = num[col].dropna().diff().dropna()
        diffs = diffs[np.isfinite(diffs)]      # inf already failed above; keep std/mean finite
        if len(diffs) < 30:
            continue
        sd = diffs.std()
        if not (sd > 0):
            continue
        z = (diffs.iloc[-1] - diffs.mean()) / sd
        if abs(z) > zlim:
            u.flag(series, "zoutlier", f"{col} latest Δ z={z:.1f}")


def _audit_group(group: str, data_dir: Path, baseline_dir: Path, asof: date,
                 cfg: dict) -> ac.Universe:
    u = ac.Universe(group)
    gdir = data_dir / group
    if not gdir.is_dir():
        u.skipped = True
        u.note = f"no directory {gdir}"
        return u
    files = sorted(gdir.glob("*.parquet"))
    if not files:
        u.skipped = True
        u.note = f"no parquet files in {gdir}"
        return u

    u.n = len(files)
    base_group_dir = baseline_dir / group
    for fp in files:
        series = fp.stem
        try:
            raw = pd.read_parquet(fp)
        except Exception as err:
            u.fail(series, f"unreadable: {err}")
            continue
        df = ac.clean_index(raw)
        if df.empty:
            u.fail(series, "empty after clean_index (no valid dated rows)")
            continue
        idx = df.index
        cadence = ac.infer_cadence_days(idx)
        lab = ac.cadence_label(cadence)
        num = _numeric_frame(df)
        if num.empty:
            u.fail(series, "no numeric columns")
            continue
        baseline_path = base_group_dir / f"{_safe(series)}.parquet"
        _check_inf(u, series, num)
        _check_revision(u, series, num, baseline_path, cadence, cfg)
        _check_gaps(u, series, idx, lab, asof)
        _check_stale(u, series, idx, cadence, lab, asof, cfg)
        _check_zoutlier(u, series, num, cfg)
    return u


def run(groups: list[str] | None = None, cfg: dict | None = None, asof: date | None = None,
        out_dir: Path | None = None, data_dir: Path | None = None,
        baseline_dir: Path | None = None) -> dict:
    """Audit the macro series groups and write data/quality/macro_audit.json.

    Never raises for data issues — every problem is recorded as a fail (hard) or flag (soft).
    The ONLY write outside data/quality/ is forbidden; the baseline snapshots live under
    data/quality/baselines/ (the sanctioned read-only exception). Returns the audit doc dict."""
    cfg = cfg or ac.quality_cfg()
    asof = asof or date.today()
    data_dir = Path(data_dir) if data_dir is not None else ac.ROOT / "data"
    baseline_dir = Path(baseline_dir) if baseline_dir is not None else ac.quality_dir() / "baselines"
    if groups is None:
        groups = cfg.get("macro_groups") or DEFAULT_GROUPS

    universes = [_audit_group(g, data_dir, baseline_dir, asof, cfg) for g in groups]
    doc = ac.write_audit("macro", "macro", universes, cfg, asof=asof, out_dir=out_dir)
    log.info("macro audit: n=%d n_failed=%d fail_pct=%.2f%% n_flags=%d",
             doc["n"], doc["n_failed"], doc["fail_pct"], doc["n_flags"])
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Audit macro series stores (revisions/gaps/stale/outliers).")
    ap.add_argument("--groups", nargs="*", default=None, help="override macro groups")
    ap.add_argument("--data-dir", default=None, help="override data/ root")
    ap.add_argument("--out-dir", default=None, help="override data/quality output dir")
    ap.add_argument("--baseline-dir", default=None, help="override revision baseline dir")
    ap.add_argument("--asof", default=None, help="override as-of date (YYYY-MM-DD)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    asof = date.fromisoformat(args.asof) if args.asof else None
    doc = run(
        groups=args.groups,
        asof=asof,
        out_dir=Path(args.out_dir) if args.out_dir else None,
        data_dir=Path(args.data_dir) if args.data_dir else None,
        baseline_dir=Path(args.baseline_dir) if args.baseline_dir else None,
    )
    log.info("wrote macro audit: n=%d n_failed=%d n_flags=%d", doc["n"], doc["n_failed"], doc["n_flags"])
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
