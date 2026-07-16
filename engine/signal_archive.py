"""Append-only archive of the daily MODEL-OUTPUT snapshots (the "signal layer").

Every engine run OVERWRITES data/<mkt>/latest.json (and bond_health.json,
regime_snap.json, forex/commodity latest.json, ...) with TODAY's read. Those
overwrites are recoverable only via the daily git commit — inconvenient — and
regime_history.parquet is RECOMPUTED from scratch each run (so it carries data
revisions + today's engine code backwards), which means neither is a faithful
point-in-time record of what the model actually SAID on a given day.

This module keeps a clean, append-only, point-in-time copy keyed by as-of date in
ONE columnar file per label — data/signal_archive/<label>.parquet — with:

  - asof / logged_at        the point-in-time keys
  - <flattened scalars>     every scalar leaf of the snapshot, dot-flattened to
                            columns (quad, growth_score, macro_risk_score, ...) so
                            the signal time series is queryable without parsing
  - snapshot_json           the FULL snapshot as a JSON string — LOSSLESS, so the
                            lists the flat columns drop (sector_rs, playbook,
                            alerts) are always recoverable

Columnar compression makes this cheap (~1.8 KB/row amortized even at 500+ cols,
because slow-moving daily values and the near-identical snapshot_json blob both
compress hard) — the same daily-rewritten-parquet pattern lib/store.py already
uses for every price series, so it is the codebase-native choice.

Keep-FIRST per as-of date: the first publish for a date is the honest record of
what was shown at the time; same-day re-runs and stale (failed-build) files dedup
to a no-op. Best-effort and DISPLAY/RESEARCH-only: never read back into any score,
never breaks a build. It is the safety net while signal definitions are still in
flux — snapshot_json survives definition drift, and because the file is committed
in the same daily commit, each row's git commit is its model-version fingerprint
(provenance for free).

Scale lever (only once a label is years long): partition the filename by year
(<label>/<year>.parquet) so closed years stop being rewritten daily. Trivial later
— the store is keyed by asof, so a one-time split is lossless.

Mirrors the append_log() convention in engine/market_drivers.py.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from lib import config

log = logging.getLogger(__name__)


def _ledger_advance_enabled() -> bool:
    """True only when running in the nightly engine lane.

    Gate: COLLECT_LANE=nightly — the same sentinel set by daily.yml's engine-job
    env.  US_LANE is accepted as a legacy alias.
    """
    val = os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")
    return val.lower() == "nightly"

# date keys tried, in order, when a snapshot does not name one explicitly
_ASOF_KEYS = ("date", "as_of", "asof", "state_asof", "generated_at", "updated")


def flatten_scalars(d: dict, _prefix: str = "", _depth: int = 0, _max_depth: int = 8) -> dict:
    """Flatten the scalar LEAVES of a (possibly nested) snapshot into a single flat
    row: nested dicts are walked and their keys joined with "_". LISTS are skipped
    — repeating structures (sector_rs, alerts, playbook ladders) stay lossless in
    the jsonl and would only explode the table width. Scalars = str/int/float/bool/
    None. Depth-guarded so a pathological tree can't run away."""
    out: dict = {}
    if not isinstance(d, dict) or _depth > _max_depth:
        return out
    for k, v in d.items():
        key = f"{_prefix}{k}"
        if v is None or isinstance(v, (str, int, float, bool)):
            out[key] = v
        elif isinstance(v, dict):
            out.update(flatten_scalars(v, f"{key}_", _depth + 1, _max_depth))
        # lists / other -> skipped (kept in the lossless jsonl)
    return out


def normalize_asof(value) -> str:
    """Coerce an as-of value to an ISO date string ("2026-06-16"). Handles both
    ISO inputs and the human format some dashboards emit ("Jun 17, 2026"). Falls
    back to the stripped raw string if it cannot be parsed."""
    if value is None:
        return ""
    try:
        ts = pd.to_datetime(value)
        if pd.isna(ts):          # pd.to_datetime("") -> NaT, whose isoformat is "NaT"
            return ""
        return ts.date().isoformat()
    except Exception:
        return str(value).strip()


def find_asof(snap: dict, prefer: str | None = None) -> str | None:
    """Discover the as-of date inside a snapshot. Tries `prefer` first, then the
    common keys. Returns a normalized ISO string, or None if none is present."""
    if not isinstance(snap, dict):
        return None
    keys = ([prefer] if prefer else []) + [k for k in _ASOF_KEYS if k != prefer]
    for k in keys:
        if k and snap.get(k) not in (None, ""):
            iso = normalize_asof(snap[k])
            if iso:
                return iso
    return None


def _archive_dir(archive_dir: str | Path | None) -> Path:
    p = Path(archive_dir) if archive_dir is not None else config.data_dir() / "signal_archive"
    p.mkdir(parents=True, exist_ok=True)
    return p


def archive_snapshot(label: str, snap: dict, asof: str, *,
                     archive_dir: str | Path | None = None,
                     logged_at: str | None = None) -> bool:
    """Append one daily model-output snapshot to data/signal_archive/<label>.parquet,
    keyed by `asof` (keep-FIRST). Returns True if a new row was written, False if it
    was a no-op (already logged for that date, or no usable as-of). The row carries
    the flattened scalar columns plus a lossless `snapshot_json` blob. Tolerates
    schema drift — pandas unions columns across days. Raises only on genuinely broken
    I/O — callers (scripts/archive_signals) wrap each target so one failure never
    breaks the build."""
    asof = normalize_asof(asof)
    if not asof or not isinstance(snap, dict):
        return False
    parquet = _archive_dir(archive_dir) / f"{label}.parquet"
    old = pd.read_parquet(parquet) if parquet.exists() else None
    if old is not None and "asof" in old.columns and asof in set(old["asof"].astype(str)):
        return False  # keep-first: this date is already recorded
    if not _ledger_advance_enabled():
        log.debug(
            "signal_archive.archive_snapshot: write skipped for label=%s asof=%s "
            "(COLLECT_LANE != nightly)",
            label, asof,
        )
        return False
    logged_at = logged_at or datetime.now(timezone.utc).isoformat()

    row = {"asof": asof, "logged_at": logged_at,
           **flatten_scalars(snap),
           "snapshot_json": json.dumps(snap, default=str)}  # lossless backstop
    merged = pd.concat([old, pd.DataFrame([row])], ignore_index=True) \
        if old is not None else pd.DataFrame([row])
    merged.to_parquet(parquet, index=False)
    return True


def load_archive(label: str, *, archive_dir: str | Path | None = None) -> pd.DataFrame | None:
    """Read a label's archive back, with the lossless snapshot recovered into a
    `snapshot` dict column (parsed from snapshot_json). Convenience for analysis /
    later model training. Returns None if the archive does not exist yet."""
    parquet = _archive_dir(archive_dir) / f"{label}.parquet"
    if not parquet.exists():
        return None
    df = pd.read_parquet(parquet)
    if "snapshot_json" in df.columns:
        df = df.assign(snapshot=df["snapshot_json"].map(
            lambda s: json.loads(s) if isinstance(s, str) else None))
    return df
