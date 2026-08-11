"""Canonical, point-in-time release targets from ALFRED full-vintage data.

Release Radar forecasts a *published release*, not the difference between two
values that happened to be first observed in different vintages.  This module
therefore reconstructs both the current and previous monthly level from one
explicit release vintage before calculating a target.

The six price-index targets expose the unrounded (latent) index change and a
one-decimal published-print proxy.  PAYEMS exposes the exact difference in
thousands.  The proxy is intentionally not labelled as the official release;
official release text remains the final authority when it is available.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from math import isfinite
from pathlib import Path

import pandas as pd

SCHEMA_VERSION = "release_target_truth.v1"
SOURCE_OUTPUT_TYPE = 2

PERCENT_TARGET_SERIES: tuple[str, ...] = (
    "CPIAUCSL",
    "CPILFESL",
    "PCEPI",
    "PCEPILFE",
    "PPIFIS",
    "PPIFES",
)
PAYROLL_TARGET_SERIES: tuple[str, ...] = ("PAYEMS",)
SUPPORTED_SERIES: tuple[str, ...] = PERCENT_TARGET_SERIES + PAYROLL_TARGET_SERIES

TARGET_IDS: Mapping[str, str] = {
    "CPIAUCSL": "cpi_headline_mom",
    "CPILFESL": "cpi_core_mom",
    "PCEPI": "pce_headline_mom",
    "PCEPILFE": "pce_core_mom",
    "PPIFIS": "ppi_final_demand_mom",
    "PPIFES": "ppi_final_demand_ex_food_energy_mom",
    "PAYEMS": "nfp_payroll_change",
}

REQUIRED_VINTAGE_COLUMNS = {
    "period",
    "realtime_start",
    "realtime_end",
    "value",
}


class ReleaseTargetTruthError(ValueError):
    """The supplied vintage store cannot safely produce canonical targets."""


def default_vintage_path(repo_root: str | Path, series_id: str) -> Path:
    """Return the canonical collector path for a supported series."""
    series = _validate_series(series_id)
    return (
        Path(repo_root)
        / "data"
        / "fred_vintage"
        / "release_targets"
        / f"{series}_all_vintages.parquet"
    )


def normalize_full_vintage_frame(
    frame: pd.DataFrame,
    *,
    series_id: str | None = None,
) -> pd.DataFrame:
    """Validate and normalize an ALFRED ``output_type=2`` long frame.

    A frame without a ``series`` column must be accompanied by ``series_id``.
    The optional ``source_output_type`` column, when present, must contain only
    ``2``.  Conflicting duplicate values for a single series/period/vintage are
    rejected rather than resolved heuristically.

    ``realtime_end`` is represented as :class:`datetime.date`, which preserves
    ALFRED's open-ended ``9999-12-31`` sentinel without pandas nanosecond
    overflow.
    """
    if not isinstance(frame, pd.DataFrame):
        raise ReleaseTargetTruthError("vintages must be a pandas DataFrame")

    missing = REQUIRED_VINTAGE_COLUMNS - set(frame.columns)
    if missing:
        raise ReleaseTargetTruthError(
            f"full-vintage frame is missing required columns: {sorted(missing)}"
        )

    out = frame.copy()
    if "source_output_type" in out.columns:
        output_types = pd.to_numeric(out["source_output_type"], errors="coerce")
        if len(out) and (
            output_types.isna().any()
            or not output_types.eq(SOURCE_OUTPUT_TYPE).all()
        ):
            raise ReleaseTargetTruthError(
                "source_output_type must be exactly 2 (ALFRED full-vintage matrix)"
            )

    if "series" not in out.columns:
        if series_id is None:
            raise ReleaseTargetTruthError(
                "series_id is required when the frame has no series column"
            )
        out["series"] = _validate_series(series_id)
    else:
        out["series"] = out["series"].astype(str).str.upper().str.strip()
        unknown = sorted(set(out["series"].dropna()) - set(SUPPORTED_SERIES))
        if unknown:
            raise ReleaseTargetTruthError(
                f"unsupported series in full-vintage frame: {unknown}"
            )
        if series_id is not None:
            series = _validate_series(series_id)
            out = out[out["series"] == series].copy()

    out["period"] = pd.to_datetime(out["period"], errors="coerce")
    out["realtime_start"] = pd.to_datetime(
        out["realtime_start"], errors="coerce"
    )
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out["realtime_end"] = out["realtime_end"].map(_coerce_end_date)
    out = out.dropna(subset=["period", "realtime_start", "value"])

    # These targets are monthly.  Normalize harmless day/time differences so
    # callers cannot accidentally request the same period two different ways.
    out["period"] = out["period"].dt.to_period("M").dt.to_timestamp()
    out["realtime_start"] = out["realtime_start"].dt.normalize()

    keys = ["series", "period", "realtime_start"]
    conflicts = out.groupby(keys, dropna=False)["value"].nunique(dropna=False)
    if (conflicts > 1).any():
        bad = conflicts[conflicts > 1].index[0]
        raise ReleaseTargetTruthError(
            "conflicting values for one series/period/vintage: "
            f"series={bad[0]} period={bad[1]} realtime_start={bad[2]}"
        )

    out = (
        out.sort_values(keys)
        .drop_duplicates(keys, keep="last")
        .reset_index(drop=True)
    )
    ordered = [
        "series",
        "period",
        "realtime_start",
        "realtime_end",
        "value",
    ]
    if "source_output_type" in out.columns:
        ordered.append("source_output_type")
    return out[ordered]


def load_full_vintage_parquets(
    paths: str | Path | Sequence[str | Path],
    *,
    series_id: str | None = None,
    require_output_type_marker: bool = True,
) -> pd.DataFrame:
    """Load one or more collector parquet files and validate their provenance.

    New canonical stores carry ``source_output_type=2``.  Set
    ``require_output_type_marker=False`` only for a known legacy output-type-2
    file and provide ``series_id`` when that file has no ``series`` column.
    This explicit opt-in prevents an initial-release-only (output type 4) file
    from being mistaken for a full-vintage store.
    """
    path_list = _as_path_list(paths)
    if not path_list:
        raise ReleaseTargetTruthError("at least one parquet path is required")

    frames: list[pd.DataFrame] = []
    for path in path_list:
        raw = pd.read_parquet(path)
        if require_output_type_marker and "source_output_type" not in raw.columns:
            raise ReleaseTargetTruthError(
                f"{path} has no source_output_type marker; refusing ambiguous store"
            )
        frames.append(raw)

    combined = pd.concat(frames, ignore_index=True, sort=False)
    return normalize_full_vintage_frame(combined, series_id=series_id)


def reconstruct_release_target(
    vintages: pd.DataFrame,
    *,
    series_id: str,
    period: str | date | datetime | pd.Timestamp,
    release_date: str | date | datetime | pd.Timestamp | None = None,
    as_of: str | date | datetime | pd.Timestamp | None = None,
) -> dict[str, object]:
    """Reconstruct one target from current/prior levels in the same vintage.

    If ``release_date`` is omitted, the first vintage in which ``period`` was
    available (bounded by ``as_of`` when supplied) is selected.  If it is
    supplied, values active on that exact date are selected.  ``as_of`` is an
    information cutoff, never a substitute vintage.

    Missing same-vintage levels produce an explicit ``status='unavailable'``
    receipt.  The function never substitutes a prior period's first or latest
    value from another vintage.
    """
    series = _validate_series(series_id)
    target_period = _coerce_month(period, "period")
    prior_period = target_period - pd.offsets.MonthBegin(1)
    normalized = normalize_full_vintage_frame(vintages, series_id=series)
    series_rows = normalized[normalized["series"] == series]
    current_rows = series_rows[series_rows["period"] == target_period]

    requested_as_of = _coerce_day(as_of, "as_of") if as_of is not None else None
    if release_date is None:
        eligible = current_rows
        if requested_as_of is not None:
            eligible = eligible[eligible["realtime_start"] <= requested_as_of]
        if eligible.empty:
            return _unavailable(
                series,
                target_period,
                prior_period,
                release_date=None,
                as_of=requested_as_of,
                reason="current_period_not_available_by_as_of",
                release_selection="initial_for_period",
            )
        selected_release = eligible["realtime_start"].min()
        release_selection = "initial_for_period"
    else:
        selected_release = _coerce_day(release_date, "release_date")
        release_selection = "explicit"

    effective_as_of = requested_as_of or selected_release
    if effective_as_of < selected_release:
        return _unavailable(
            series,
            target_period,
            prior_period,
            release_date=selected_release,
            as_of=effective_as_of,
            reason="release_not_available_by_as_of",
            release_selection=release_selection,
        )

    current, current_reason = _row_active_on(current_rows, selected_release)
    if current is None:
        return _unavailable(
            series,
            target_period,
            prior_period,
            release_date=selected_release,
            as_of=effective_as_of,
            reason=f"current_{current_reason}",
            release_selection=release_selection,
        )

    prior_rows = series_rows[series_rows["period"] == prior_period]
    prior, prior_reason = _row_active_on(prior_rows, selected_release)
    if prior is None:
        return _unavailable(
            series,
            target_period,
            prior_period,
            release_date=selected_release,
            as_of=effective_as_of,
            reason=f"prior_{prior_reason}",
            release_selection=release_selection,
        )

    current_level = float(current["value"])
    prior_level = float(prior["value"])
    if series in PERCENT_TARGET_SERIES:
        if prior_level == 0:
            return _unavailable(
                series,
                target_period,
                prior_period,
                release_date=selected_release,
                as_of=effective_as_of,
                reason="prior_level_is_zero",
                release_selection=release_selection,
            )
        latent_decimal = (
            Decimal(str(current_level)) / Decimal(str(prior_level)) - Decimal(1)
        ) * Decimal(100)
        latent_change = float(latent_decimal)
        published_proxy = _round_decimal_1dp(latent_decimal)
        target_kind = "percent_mom"
        unit = "percent"
        published_proxy_1dp: float | None = published_proxy
        payroll_change_thousands: float | None = None
        published_precision = "0.1 percentage point"
    else:
        latent_change = current_level - prior_level
        published_proxy = latent_change
        target_kind = "payroll_change"
        unit = "thousands"
        published_proxy_1dp = None
        payroll_change_thousands = latent_change
        published_precision = "exact source-series thousand"

    provenance = {
        "source": "FRED/ALFRED",
        "source_output_type": SOURCE_OUTPUT_TYPE,
        "series_id": series,
        "observation_period": _iso_day(target_period),
        "prior_observation_period": _iso_day(prior_period),
        "release_date": _iso_day(selected_release),
        "as_of": _iso_day(effective_as_of),
        "current_vintage": _row_provenance(current),
        "prior_vintage": _row_provenance(prior),
        "same_release_vintage": True,
        "cross_vintage_fallback_used": False,
    }
    return {
        "schema": SCHEMA_VERSION,
        "status": "ok",
        "series_id": series,
        "target_id": TARGET_IDS[series],
        "target_kind": target_kind,
        "period": target_period.strftime("%Y-%m"),
        "prior_period": prior_period.strftime("%Y-%m"),
        "release_date": _iso_day(selected_release),
        "as_of": _iso_day(effective_as_of),
        "release_selection": release_selection,
        "current_level": current_level,
        "prior_level_same_vintage": prior_level,
        "latent_change": latent_change,
        "published_proxy": published_proxy,
        "published_proxy_1dp": published_proxy_1dp,
        "payroll_change_thousands": payroll_change_thousands,
        "published_precision": published_precision,
        "unit": unit,
        "published_proxy_is_official_release": False,
        "basis": "same_release_vintage",
        "cross_vintage_fallback_used": False,
        "provenance": provenance,
    }


def reconstruct_release_targets(
    vintages: pd.DataFrame,
    requests: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Pure batch wrapper around :func:`reconstruct_release_target`."""
    return [reconstruct_release_target(vintages, **dict(item)) for item in requests]


def round_published_1dp(value: float) -> float:
    """Round a release proxy to one decimal using conventional half-up rules."""
    if not isfinite(float(value)):
        raise ReleaseTargetTruthError("cannot round a non-finite release target")
    return _round_decimal_1dp(Decimal(str(value)))


def _round_decimal_1dp(value: Decimal) -> float:
    rounded = float(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
    # JSON distinguishes the spelling ``-0.0`` even though the published CPI
    # print does not.  Canonical receipts therefore collapse signed zero.
    return 0.0 if rounded == 0.0 else rounded


def _row_active_on(
    rows: pd.DataFrame,
    release_date: pd.Timestamp,
) -> tuple[pd.Series | None, str]:
    if rows.empty:
        return None, "period_missing"
    release_day = release_date.date()
    active = rows[
        (rows["realtime_start"] <= release_date)
        & rows["realtime_end"].map(lambda end: end >= release_day)
    ]
    if active.empty:
        return None, "same_vintage_value_missing"
    latest_start = active["realtime_start"].max()
    selected = active[active["realtime_start"] == latest_start]
    if len(selected) != 1:
        return None, "same_vintage_value_ambiguous"
    return selected.iloc[0], "ok"


def _unavailable(
    series: str,
    period: pd.Timestamp,
    prior_period: pd.Timestamp,
    *,
    release_date: pd.Timestamp | None,
    as_of: pd.Timestamp | None,
    reason: str,
    release_selection: str,
) -> dict[str, object]:
    return {
        "schema": SCHEMA_VERSION,
        "status": "unavailable",
        "reason": reason,
        "series_id": series,
        "target_id": TARGET_IDS[series],
        "period": period.strftime("%Y-%m"),
        "prior_period": prior_period.strftime("%Y-%m"),
        "release_date": _iso_day(release_date) if release_date is not None else None,
        "as_of": _iso_day(as_of) if as_of is not None else None,
        "release_selection": release_selection,
        "basis": "same_release_vintage",
        "cross_vintage_fallback_used": False,
    }


def _row_provenance(row: pd.Series) -> dict[str, object]:
    return {
        "period": _iso_day(row["period"]),
        "realtime_start": _iso_day(row["realtime_start"]),
        "realtime_end": row["realtime_end"].isoformat(),
        "value": float(row["value"]),
    }


def _validate_series(series_id: str) -> str:
    series = str(series_id).upper().strip()
    if series not in SUPPORTED_SERIES:
        raise ReleaseTargetTruthError(
            f"unsupported release-target series {series!r}; "
            f"supported={list(SUPPORTED_SERIES)}"
        )
    return series


def _coerce_month(value: object, name: str) -> pd.Timestamp:
    day = _coerce_day(value, name)
    return day.to_period("M").to_timestamp()


def _coerce_day(value: object, name: str) -> pd.Timestamp:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        raise ReleaseTargetTruthError(f"{name} is not a valid date: {value!r}")
    if isinstance(parsed, pd.DatetimeIndex):
        raise ReleaseTargetTruthError(f"{name} must be a scalar date")
    stamp = pd.Timestamp(parsed)
    if stamp.tzinfo is not None:
        stamp = stamp.tz_convert("UTC").tz_localize(None)
    return stamp.normalize()


def _coerce_end_date(value: object) -> date:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return date.max
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()[:10]
    if text in {"", "NaT", "nan", "None"}:
        return date.max
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ReleaseTargetTruthError(
            f"realtime_end is not a valid date: {value!r}"
        ) from exc


def _iso_day(value: pd.Timestamp) -> str:
    return pd.Timestamp(value).date().isoformat()


def _as_path_list(paths: str | Path | Sequence[str | Path]) -> list[Path]:
    if isinstance(paths, (str, Path)):
        return [Path(paths)]
    return [Path(path) for path in paths]


__all__ = [
    "PAYROLL_TARGET_SERIES",
    "PERCENT_TARGET_SERIES",
    "SCHEMA_VERSION",
    "SOURCE_OUTPUT_TYPE",
    "SUPPORTED_SERIES",
    "TARGET_IDS",
    "ReleaseTargetTruthError",
    "default_vintage_path",
    "load_full_vintage_parquets",
    "normalize_full_vintage_frame",
    "reconstruct_release_target",
    "reconstruct_release_targets",
    "round_published_1dp",
]
