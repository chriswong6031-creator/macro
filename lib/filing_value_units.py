"""13F market-value unit normalization.

The SEC changed Form 13F from values rounded to the nearest thousand dollars to
values rounded to the nearest dollar on 2023-01-03.  A small number of filers
still submit post-change information tables in the legacy unit.  EDGAR accepts
those documents and the XML schema carries no unit flag, so blindly selecting a
multiplier from ``period_end`` produces thousand-fold book-value errors.

This module keeps the compatibility rule pure and deliberately conservative:
post-change legacy units are inferred only when both the reported book is below
the $100m 13F threshold and the per-share values are implausibly small for a
normal dollar-valued equity table.  The reported value and inference reason are
retained by the collector for provenance.
"""
from __future__ import annotations

from datetime import date

import pandas as pd


DOLLARS_FROM = date(2022, 12, 31)


def _period_date(period_end: date | str | pd.Timestamp | None) -> date | None:
    if period_end is None:
        return None
    if isinstance(period_end, date) and not isinstance(period_end, pd.Timestamp):
        return period_end
    try:
        return pd.Timestamp(period_end).date()
    except (TypeError, ValueError):
        return None


def infer_13f_value_multiplier(
    frame: pd.DataFrame,
    period_end: date | str | pd.Timestamp | None,
    *,
    value_col: str = "value_raw",
) -> tuple[float, str]:
    """Return ``(multiplier, reason)`` for one information table.

    Pre-2023 tables are unambiguously reported in thousands.  For later tables,
    SEC's required unit is dollars.  The compatibility branch catches a narrow,
    observed legacy-exporter failure mode without reclassifying distressed or
    penny-stock portfolios whose genuine dollar values can also be below $2 per
    share.
    """
    pe = _period_date(period_end)
    if pe is not None and pe < DOLLARS_FROM:
        return 1000.0, "sec-pre-2023-thousands"
    if frame.empty or value_col not in frame.columns or "shares" not in frame.columns:
        return 1.0, "sec-nearest-dollar"

    values = pd.to_numeric(frame[value_col], errors="coerce")
    shares = pd.to_numeric(frame["shares"], errors="coerce")
    sh_type = (
        frame["sh_type"].astype(str).str.upper()
        if "sh_type" in frame.columns
        else pd.Series("SH", index=frame.index)
    )
    positive_values = values[values > 0]
    total_reported = float(positive_values.sum()) if not positive_values.empty else 0.0
    mask = (values > 0) & (shares > 0) & (sh_type == "SH")
    implied = (values[mask] / shares[mask]).replace([float("inf"), -float("inf")], pd.NA).dropna()

    # Compatibility detector for observed post-change filings still expressed
    # in $000s.  Requiring three independent share lines, a sub-threshold raw
    # book, and broad low-price agreement avoids treating a one-line microcap or
    # a distressed/debt-heavy dollar filing as a thousand-dollar table.
    legacy_shape = (
        len(implied) >= 3
        and 100_000.0 <= total_reported < 100_000_000.0
        and float(implied.median()) < 2.0
        and float((implied < 5.0).mean()) >= 0.60
    )
    if legacy_shape:
        return 1000.0, "post-2023-legacy-thousands-compatibility"
    return 1.0, "sec-nearest-dollar"


def normalize_13f_snapshot(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a normalized copy of a stored 13F snapshot.

    New snapshots carry ``value_multiplier`` and are already normalized.  This
    read-time bridge repairs legacy repo snapshots created by the old
    period-only rule without rewriting the immutable filing evidence files.
    """
    if frame.empty or "value_usd" not in frame.columns:
        return frame
    if "value_multiplier" in frame.columns:
        return frame

    period_end = None
    if "period_end" in frame.columns and len(frame):
        period_end = frame["period_end"].iloc[0]
    # Pre-change snapshots in the repository were already multiplied by 1,000
    # at collection time; only post-change legacy files need the compatibility
    # bridge.
    pe = _period_date(period_end)
    if pe is None or pe < DOLLARS_FROM:
        return frame

    multiplier, reason = infer_13f_value_multiplier(
        frame, period_end, value_col="value_usd")
    if multiplier == 1.0:
        return frame
    out = frame.copy()
    out["value_reported"] = pd.to_numeric(out["value_usd"], errors="coerce")
    out["value_usd"] = out["value_reported"] * multiplier
    out["value_multiplier"] = multiplier
    out["value_unit_inference"] = reason
    out["value_normalized_runtime"] = True
    return out
