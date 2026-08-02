"""Shared helpers for the end-of-collection data-quality audit suite.

Three sibling scripts (audit_prices / audit_macro / audit_universe) run AFTER collection
(wired into scripts/collect.py). They are:
  - DETERMINISTIC — rule-based only, no ML, no thresholds fit to outcomes;
  - READ-ONLY over the data stores — they only ever WRITE under data/quality/;
  - IDEMPOTENT — re-running on unchanged data yields the same verdict (the macro
    revision baseline is the one exception by design: it tracks the latest values, so a
    revision is caught once, then the baseline absorbs it and a re-run is clean).

Each audit writes data/quality/<name>_audit.json and returns a structured dict whose
per-universe `fail_pct` the collect.py governance gate consumes (>5% of a universe failing
aborts the run; 1-5% warns). Soft issues (big single-day moves, z-outliers, staleness) are
FLAGS — logged, never counted as failures (per the spec: "log, don't fail").
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger("audit")

ROOT: Path = config.ROOT


def quality_dir() -> Path:
    return config.data_dir() / "quality"


# --- config -----------------------------------------------------------------

# Hard defaults so an audit still runs if the `quality:` block is absent. config.yml is
# the single source of truth (CLAUDE.md: nothing tunable is hardcoded in engine/collectors);
# these mirror the committed block and only fill gaps.
_DEFAULTS = {
    "price_max_gap_days": 4,        # > this many BUSINESS days between bars = a real hole (tolerates holidays)
    "price_move_alert_pct": 20.0,   # |single-day move| beyond this = FLAG (log only)
    "price_recent_days": 120,       # gap + big-move checks scoped to the last N calendar days (recent edge only)
    "macro_revision_alert_pct": 5.0,  # settled historical value changing by more than this vs baseline = fail
    "macro_stale_days": 45,         # last obs older than this (+cadence) = stale FLAG
    "universe_min_bars": 250,       # a configured ticker with fewer rows is "short"
    "abort_fail_pct": 5.0,          # > this % of a universe failing aborts the collect (RuntimeError)
    "warn_fail_pct": 1.0,           # 1-this% warns + logs
    "macro_outlier_z": 5.0,         # |z| of the latest change beyond this = FLAG (log only)
    # --- massive_stock_day whole-market store (audit_massive_store) ---
    "massive_max_gap_bdays": 5,     # > this many consecutive missing BUSINESS days in an anchor = coverage hole (fail)
    "massive_stale_bdays": 5,       # newest anchor bar older than this many business days = stale FLAG
    "massive_manifest_ahead_bdays": 2,  # manifest latest_date this far ahead of anchor content = manifest lie (fail)
    "massive_min_files": 100,       # fewer parquets than this = store absent (CI checkout) -> universe skipped
    "massive_recent_window_bdays": 90,  # continuity is judged over the trailing N bdays only; a deeper gap flags (descriptive, not tonight's feed)
    "email_alerts": False,          # NEVER email — deterministic file + conspicuous log only
}


def quality_cfg() -> dict:
    q = config.load().get("quality") or {}
    out = dict(_DEFAULTS)
    for k in _DEFAULTS:
        if k in q and q[k] is not None:
            out[k] = q[k]
    # optional store/group overrides (lists) pass through untouched
    out["price_stores"] = q.get("price_stores")
    out["macro_groups"] = q.get("macro_groups")
    return out


# --- result model -----------------------------------------------------------


@dataclass
class Universe:
    """One auditable cohort. `failed` items count toward the abort/warn gate;
    `flags` are soft (logged, never fatal). `skipped` excludes the cohort from the
    gate entirely (its backing store is absent — never abort the build for that)."""
    name: str
    n: int = 0
    failed: list = field(default_factory=list)  # [{"name": str, "reasons": [str, ...]}]
    flags: list = field(default_factory=list)   # [{"name": str, "kind": str, "detail": str}]
    skipped: bool = False
    note: str = ""

    def fail(self, name: str, reason: str) -> None:
        for f in self.failed:
            if f["name"] == name:
                f["reasons"].append(reason)
                return
        self.failed.append({"name": name, "reasons": [reason]})

    def flag(self, name: str, kind: str, detail: str) -> None:
        self.flags.append({"name": name, "kind": kind, "detail": detail})

    @property
    def n_failed(self) -> int:
        return len(self.failed)

    @property
    def fail_pct(self) -> float:
        return 100.0 * self.n_failed / self.n if self.n else 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name, "n": self.n, "n_failed": self.n_failed,
            "fail_pct": round(self.fail_pct, 3), "n_flags": len(self.flags),
            "skipped": self.skipped, "note": self.note,
            "failed": self.failed, "flags": self.flags,
        }


def write_audit(name: str, kind: str, universes: list[Universe], cfg: dict,
                asof: date | None = None, out_dir: Path | None = None) -> dict:
    """Persist data/quality/<name>_audit.json and return the document. Active (non-skipped)
    universes drive the totals the governance gate reads."""
    out_dir = out_dir or quality_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    asof = asof or date.today()
    active = [u for u in universes if not u.skipped]
    n = sum(u.n for u in active)
    n_failed = sum(u.n_failed for u in active)
    n_flags = sum(len(u.flags) for u in universes)
    echo = {k: cfg[k] for k in _DEFAULTS if k in cfg}
    doc = {
        "asof": asof.isoformat(),
        "audit": kind,
        "config": echo,
        "n": n, "n_failed": n_failed,
        "fail_pct": round(100.0 * n_failed / n, 3) if n else 0.0,
        "n_flags": n_flags,
        "universes": [u.to_dict() for u in universes],
    }
    (out_dir / f"{name}_audit.json").write_text(json.dumps(doc, indent=1))
    return doc


# --- time-series primitives (shared by prices + macro) ----------------------


def clean_index(df: pd.DataFrame) -> pd.DataFrame:
    """A sorted, de-duplicated, tz-naive datetime-indexed copy. Drops rows whose index is
    NaT (a corrupt date is itself worth nothing to the gap/revision math). The index is
    forced tz-NAIVE so the recent-window slicing (which compares against a tz-naive asof
    Timestamp) never raises on a future tz-aware store."""
    out = df.copy()
    idx = pd.to_datetime(out.index, errors="coerce")
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    out.index = idx
    out = out[~out.index.isna()]
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out


def _unique_days(idx: pd.DatetimeIndex) -> np.ndarray:
    return np.unique(pd.DatetimeIndex(idx).normalize().values.astype("datetime64[D]"))


def business_gaps_over(idx: pd.DatetimeIndex, max_bdays: int) -> list[tuple]:
    """[(prev, cur, n_business_days), ...] for consecutive observations whose business-day
    distance exceeds max_bdays. Business-day distance ignores weekends so normal Fri->Mon
    reads as 1; only genuine multi-session holes (or a stale series) clear the bar."""
    days = _unique_days(idx)
    if len(days) < 2:
        return []
    gaps = np.busday_count(days[:-1], days[1:])
    bad = np.where(gaps > max_bdays)[0]
    return [(pd.Timestamp(days[k]), pd.Timestamp(days[k + 1]), int(gaps[k])) for k in bad]


def calendar_gaps_over(idx: pd.DatetimeIndex, max_days: int) -> list[tuple]:
    """Calendar-day analogue, for monthly/quarterly series where business days are
    meaningless. [(prev, cur, n_calendar_days), ...] over max_days."""
    days = _unique_days(idx)
    if len(days) < 2:
        return []
    gaps = (days[1:] - days[:-1]).astype("timedelta64[D]").astype(int)
    bad = np.where(gaps > max_days)[0]
    return [(pd.Timestamp(days[k]), pd.Timestamp(days[k + 1]), int(gaps[k])) for k in bad]


def infer_cadence_days(idx: pd.DatetimeIndex) -> float:
    """Median calendar spacing between observations — the robust cadence estimate
    (~1-3=daily, ~7=weekly, ~28-31=monthly, ~90=quarterly)."""
    days = _unique_days(idx)
    if len(days) < 3:
        return float("nan")
    d = np.diff(days).astype("timedelta64[D]").astype(int)
    d = d[d > 0]
    return float(np.median(d)) if len(d) else float("nan")


def cadence_label(cadence_days: float) -> str:
    if not np.isfinite(cadence_days):
        return "unknown"
    if cadence_days <= 3.5:
        return "daily"
    if cadence_days <= 10:
        return "weekly"
    if cadence_days <= 45:
        return "monthly"
    return "quarterly"


def has_bad_floats(s: pd.Series) -> bool:
    """True if the series carries +/-inf (NaN handled separately — see audit_prices)."""
    v = pd.to_numeric(s, errors="coerce")
    return bool(np.isinf(v.to_numpy(dtype="float64", na_value=np.nan)).any())


def interior_nan_count(s: pd.Series) -> int:
    """NaNs strictly between the first and last non-null observation. Leading/trailing NaN
    (a series that starts late or a not-yet-populated optional column) is not corruption;
    an interior hole is."""
    v = s.notna()
    if not v.any():
        return 0
    lo = v.idxmax()
    hi = v[::-1].idxmax()
    return int(s.loc[lo:hi].isna().sum())
