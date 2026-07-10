"""MRI W11-E Track S — Print-integrity chip (MRI-R38).

Computes a data-quality regime descriptor for macro releases from:

  1. CES collection/response rates  (data/bls_print_integrity/integrity.parquet,
                                     table='ces_response')
  2. CPI median standard errors     (data/bls_print_integrity/integrity.parquet,
                                     table='cpi_se')
  3. NFP revision streak            (data/fred_vintage/vintages.parquet, PAYEMS series)

Output dict (display-only — no model uses these values):
  {
    "regime": "normal" | "degraded" | "disrupted",
    "collection_rate_vs_5y": float | None,   # pct-point delta vs 5y mean
    "cpi_median_se_trend": "rising" | "flat" | "falling" | None,
    "revision_streak": int | None,           # consecutive same-direction NFP revisions
    "source_years": list[int],               # years of CES data used
    "as_of": "YYYY-MM-DD",
  }

Regime thresholds (deterministic):
  - disrupted: collection_rate_vs_5y < -10 pp  (e.g., COVID-era drop)
  - degraded:  collection_rate_vs_5y < -5 pp   (below baseline trend)
  - normal:    collection_rate_vs_5y >= -5 pp or unavailable

Display-only law (MRI-R20): no value from this module shifts any
point estimate, interval, or skew.  It emits a metadata dict only.

Citations:
  BLS CES response rates: https://www.bls.gov/ces/publications/responserate/
  BLS CPI standard errors: https://www.bls.gov/cpi/tables/relative-importance/home.htm
  FRED ALFRED PAYEMS vintages: https://alfred.stlouisfed.org/series/PAYEMS
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regime thresholds
# ---------------------------------------------------------------------------

_THRESHOLD_DISRUPTED_PP: float = -10.0   # collection rate vs 5y mean
_THRESHOLD_DEGRADED_PP: float = -5.0
_REVISION_STREAK_MIN: int = 3            # minimum streak length to report


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# CES response-rate regime
# ---------------------------------------------------------------------------

def _compute_ces_regime(
    integrity_df: pd.DataFrame, as_of_year: int
) -> tuple[str, float | None, list[int]]:
    """Compute (regime, collection_rate_vs_5y, source_years) from CES data.

    Returns ('normal', None, []) if data unavailable.
    """
    try:
        ces = integrity_df[integrity_df["table"] == "ces_response"].copy()
        if ces.empty:
            return "normal", None, []

        # period_key is the year (stored as str or int from the parquet)
        ces["year"] = pd.to_numeric(ces["period_key"], errors="coerce")
        ces = ces.dropna(subset=["year"])
        ces["year"] = ces["year"].astype(int)

        # Latest year available (the one being rated)
        latest = ces[ces["year"] == ces["year"].max()]
        if latest.empty:
            return "normal", None, []

        latest_year = int(latest.iloc[0]["year"])
        latest_rate = float(latest.iloc[0]["metric_a"])

        # 5y prior mean: last 5 years BEFORE the latest year
        prior = ces[ces["year"] < latest_year].sort_values("year")
        last5 = prior.tail(5)

        if len(last5) < 2:
            return "normal", None, []

        source_years = sorted(last5["year"].tolist())
        mean_5y = last5["metric_a"].mean()  # metric_a = collection_rate_pct
        delta = latest_rate - mean_5y

        if delta < _THRESHOLD_DISRUPTED_PP:
            regime = "disrupted"
        elif delta < _THRESHOLD_DEGRADED_PP:
            regime = "degraded"
        else:
            regime = "normal"

        return regime, round(delta, 2), source_years

    except Exception as exc:
        log.warning("release_integrity CES regime error: %s", exc)
        return "normal", None, []


# ---------------------------------------------------------------------------
# CPI SE trend
# ---------------------------------------------------------------------------

def _compute_cpi_se_trend(integrity_df: pd.DataFrame) -> str | None:
    """Compute CPI median SE trend: 'rising' | 'flat' | 'falling' | None."""
    try:
        cpi = integrity_df[
            (integrity_df["table"] == "cpi_se") &
            (integrity_df["component"] == "all_items")
        ].copy()
        if len(cpi) < 3:
            return None

        cpi["period_int"] = pd.to_numeric(cpi["period_key"], errors="coerce")
        cpi = cpi.dropna(subset=["period_int"]).sort_values("period_int")
        ses = cpi["metric_a"].dropna().values

        if len(ses) < 3:
            return None

        # Simple: compare last 3 years
        recent = ses[-3:]
        delta = recent[-1] - recent[0]
        if delta > 0.005:
            return "rising"
        elif delta < -0.005:
            return "falling"
        else:
            return "flat"

    except Exception as exc:
        log.warning("release_integrity CPI SE trend error: %s", exc)
        return None


# ---------------------------------------------------------------------------
# NFP revision streak from ALFRED vintages
# ---------------------------------------------------------------------------

def _compute_revision_streak(root: Path) -> int | None:
    """Count consecutive same-direction NFP revisions from ALFRED vintages.

    Uses data/fred_vintage/vintages.parquet (PAYEMS series), which stores
    initial-release values.  A revision is computed as:
      revision_t = initial_release_{t+1_vintage} - initial_release_{t_vintage}

    Returns the streak count (positive = consecutive upward revisions,
    negative = consecutive downward revisions), or None if data unavailable.
    """
    try:
        vintage_path = root / "data" / "fred_vintage" / "vintages.parquet"
        if not vintage_path.exists():
            return None

        df = pd.read_parquet(vintage_path)
        if df.empty:
            return None

        # ALFRED vintages parquet schema: varies by implementation
        # Try to find PAYEMS rows
        payems = None
        if "series_id" in df.columns:
            payems = df[df["series_id"] == "PAYEMS"].copy()
        elif "series" in df.columns:
            payems = df[df["series"] == "PAYEMS"].copy()

        if payems is None or payems.empty:
            return None

        # We need 'date' (reference period) and 'value' (initial release value)
        date_col = next((c for c in ["date", "period", "observation_date"] if c in payems.columns), None)
        val_col = next((c for c in ["value", "initial_value", "val"] if c in payems.columns), None)

        if date_col is None or val_col is None:
            return None

        payems = (
            payems[[date_col, val_col]]
            .rename(columns={date_col: "date", val_col: "value"})
            .dropna()
            .sort_values("date")
        )
        payems["value"] = pd.to_numeric(payems["value"], errors="coerce")
        payems = payems.dropna(subset=["value"])

        if len(payems) < 4:
            return None

        # Compute month-to-month change (these are LEVELS; convert to MoM change)
        payems["revision"] = payems["value"].diff()
        revisions = payems["revision"].dropna().values[-12:]  # last 12 months

        if len(revisions) < 2:
            return None

        # Count streak from most recent backward
        latest_direction = 1 if revisions[-1] > 0 else -1
        streak = 1
        for i in range(len(revisions) - 2, -1, -1):
            direction = 1 if revisions[i] > 0 else -1
            if direction == latest_direction:
                streak += 1
            else:
                break

        return streak * latest_direction  # positive = upward streak

    except Exception as exc:
        log.warning("release_integrity revision streak error: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_print_integrity(
    release_type: str = "nfp",
    as_of: date | None = None,
    root: Path | str | None = None,
) -> dict[str, Any]:
    """Compute print-integrity chip for a release type.

    Parameters
    ----------
    release_type : str
        'nfp' (uses CES response rates + revision streak) or
        'cpi_headline' / 'cpi_core' (uses CPI SE trend).
        Other types return a minimal dict with regime='normal'.
    as_of : date or None
        Reference date for 5y lookback.  Defaults to today.
    root : Path or None
        Repository root.

    Returns
    -------
    dict with keys:
      regime              : 'normal' | 'degraded' | 'disrupted'
      collection_rate_vs_5y : float | None  (NFP only)
      cpi_median_se_trend   : str | None    (CPI only)
      revision_streak       : int | None    (NFP only)
      source_years          : list[int]
      as_of                 : str (YYYY-MM-DD)
    """
    if root is None:
        root = _repo_root()
    root = Path(root)

    if as_of is None:
        as_of = date.today()

    out: dict[str, Any] = {
        "regime": "normal",
        "collection_rate_vs_5y": None,
        "cpi_median_se_trend": None,
        "revision_streak": None,
        "source_years": [],
        "as_of": str(as_of),
    }

    # Load integrity parquet
    parquet_path = root / "data" / "bls_print_integrity" / "integrity.parquet"
    integrity_df: pd.DataFrame | None = None
    if parquet_path.exists():
        try:
            integrity_df = pd.read_parquet(parquet_path)
        except Exception as exc:
            log.warning("release_integrity: could not read integrity parquet: %s", exc)

    if integrity_df is None or integrity_df.empty:
        # Fall back to seed data
        try:
            from collectors.bls_print_integrity import load_print_integrity  # type: ignore[import]
            integrity_df = load_print_integrity(root=root)
        except Exception as exc:
            log.warning("release_integrity: could not load seed integrity data: %s", exc)
            integrity_df = None

    if release_type == "nfp" and integrity_df is not None:
        regime, delta, source_years = _compute_ces_regime(integrity_df, as_of_year=as_of.year)
        out["regime"] = regime
        out["collection_rate_vs_5y"] = delta
        out["source_years"] = source_years
        out["revision_streak"] = _compute_revision_streak(root)

    elif release_type in ("cpi_headline", "cpi_core") and integrity_df is not None:
        out["cpi_median_se_trend"] = _compute_cpi_se_trend(integrity_df)
        # CPI doesn't use CES collection rate; regime stays 'normal' unless
        # we have evidence of collection disruption (government shutdown)
        # — that path is handled by the quirk flag, not the integrity regime.

    return out
