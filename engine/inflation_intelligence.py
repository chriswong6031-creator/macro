"""Display-only inflation-state bridge for Release Radar.

``inflation_intelligence.v1`` deliberately keeps three different clocks apart:

``released_state``
    Latest locally stored official CPI index history and exact released 3m/6m
    annualized trends.  The local FRED files are latest-revision data, not an
    original-release vintage, and the artifact says so.

``next_release_forecast``
    The earliest upcoming CPI release in Release Radar, including the immutable
    forecast path reconstructed from its append-only forward ledger.

``current_month_proxy_pressure``
    Public-data/model pressure for the in-progress reference month.  It is
    explicitly *not* an official CPI observation or a substitute for one.

All reads are fail-open.  Missing/corrupt inputs produce null/empty blocks plus
structured gaps; they never promote a proxy into a fact and never confer signal
authority.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from engine.conditions import _smooth_annual_rate

SCHEMA = "inflation_intelligence.v1"
DEFAULT_OUTPUT = Path("data/release_forecast/inflation_intelligence.json")
DEFAULT_RADAR_LATEST = Path("data/release_forecast/latest.json")
DEFAULT_FORWARD_LEDGER = Path("data/release_forecast/forward_ledger.jsonl")

_FRED_SERIES = {
    "headline": ("CPIAUCSL", "headline_cpi"),
    "core": ("CPILFESL", "core_cpi"),
    "sticky": ("STICKCPIM157SFRBATL", "sticky_cpi"),
    "flexible": ("FLEXCPIM157SFRBATL", "flex_cpi"),
}

_AUTHORITY_NOTE = (
    "DISPLAY-ONLY context. This artifact may describe released inflation, an upcoming "
    "Release Radar forecast, and in-progress proxy pressure. It may not originate, "
    "rank, size, gate, escalate, or execute a signal or trade."
)


def _repo_root(root: str | Path | None) -> Path:
    return Path(root) if root is not None else Path(__file__).resolve().parent.parent


def _resolve(repo: Path, path: str | Path | None, default: Path) -> Path:
    candidate = Path(path) if path is not None else default
    return candidate if candidate.is_absolute() else repo / candidate


def _path_label(repo: Path, path: Path) -> str:
    try:
        return str(path.relative_to(repo))
    except ValueError:
        return str(path)


def _number(value: Any, digits: int = 6) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return round(result, digits)


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return pd.Timestamp(value).date()
    except Exception:  # noqa: BLE001 - date parsing is a fail-open boundary
        return None


def _month_age(observation_period: str | None, as_of: date) -> int | None:
    if not observation_period:
        return None
    try:
        period = pd.Period(observation_period, freq="M")
    except Exception:  # noqa: BLE001
        return None
    return (as_of.year - period.year) * 12 + as_of.month - period.month


def _read_json(path: Path, label: str, gaps: list[str]) -> dict[str, Any] | None:
    if not path.exists():
        gaps.append(f"{label}:absent")
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"{label}:unreadable:{type(exc).__name__}")
        return None
    if not isinstance(value, dict):
        gaps.append(f"{label}:not_object")
        return None
    return value


def _read_ledger(
    repo: Path,
    path: Path,
    gaps: list[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    status = {
        "available": False,
        "path": _path_label(repo, path),
        "rows_read": 0,
        "malformed_rows": 0,
    }
    if not path.exists():
        gaps.append("release_radar_forward_ledger:absent")
        return [], status

    rows: list[dict[str, Any]] = []
    malformed = 0
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except Exception:  # noqa: BLE001
                    malformed += 1
                    continue
                if isinstance(row, dict):
                    rows.append(row)
                else:
                    malformed += 1
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"release_radar_forward_ledger:unreadable:{type(exc).__name__}")
        return [], status

    status.update(available=True, rows_read=len(rows), malformed_rows=malformed)
    if malformed:
        gaps.append(f"release_radar_forward_ledger:malformed_rows:{malformed}")
    return rows, status


def _read_fred_series(
    repo: Path,
    series_id: str,
    preferred_column: str,
    as_of: date,
    gaps: list[str],
) -> tuple[pd.Series | None, dict[str, Any]]:
    path = repo / "data" / "fred" / f"{series_id}.parquet"
    status: dict[str, Any] = {
        "series_id": series_id,
        "available": False,
        "path": _path_label(repo, path),
        "observation_period": None,
    }
    if not path.exists():
        gaps.append(f"fred:{series_id}:absent")
        return None, status
    try:
        frame = pd.read_parquet(path)
        if frame is None or frame.empty:
            gaps.append(f"fred:{series_id}:empty")
            return None, status
        frame = frame.copy()
        frame.index = pd.to_datetime(frame.index, errors="coerce")
        frame = frame[frame.index.notna()].sort_index()
        frame = frame.loc[frame.index.date <= as_of]
        if frame.empty:
            gaps.append(f"fred:{series_id}:no_observation_by_asof")
            return None, status
        column = preferred_column if preferred_column in frame.columns else None
        if column is None:
            numeric = list(frame.select_dtypes(include="number").columns)
            column = numeric[0] if numeric else None
        if column is None:
            gaps.append(f"fred:{series_id}:no_numeric_column")
            return None, status
        series = pd.to_numeric(frame[column], errors="coerce").dropna()
        series = series[~series.index.duplicated(keep="last")].sort_index()
        if series.empty:
            gaps.append(f"fred:{series_id}:no_numeric_observations")
            return None, status
        status.update(
            available=True,
            column=str(column),
            observations=len(series),
            observation_period=str(series.index[-1].to_period("M")),
        )
        return series, status
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"fred:{series_id}:unreadable:{type(exc).__name__}")
        return None, status


def _monthly_levels(series: pd.Series) -> pd.Series:
    clean = pd.to_numeric(series, errors="coerce").dropna().sort_index()
    if clean.empty:
        return pd.Series(dtype=float)
    monthly = clean.groupby(clean.index.to_period("M")).last().astype(float)
    # Missing calendar months must remain missing; positional shifts would silently
    # turn a four-month span with a hole into a three-month rate.
    full_index = pd.period_range(monthly.index.min(), monthly.index.max(), freq="M")
    return monthly.reindex(full_index)


def _level_change(monthly: pd.Series, months: int, annualized: bool) -> float | None:
    if monthly.empty or months < 1:
        return None
    current_period = monthly.index[-1]
    prior_period = current_period - months
    if prior_period not in monthly.index:
        return None
    current = _number(monthly.loc[current_period], digits=12)
    prior = _number(monthly.loc[prior_period], digits=12)
    if current is None or prior is None or current <= 0 or prior <= 0:
        return None
    gross = current / prior
    exponent = 12.0 / months if annualized else 1.0
    return _number((gross**exponent - 1.0) * 100.0)


def _released_index_state(
    series: pd.Series | None,
    series_id: str,
    label: str,
    as_of: date,
) -> dict[str, Any]:
    empty = {
        "available": False,
        "series_id": series_id,
        "label": label,
        "observation_period": None,
        "index_level": None,
        "mom_pct": None,
        "yoy_pct": None,
        "annualized_3m_pct": None,
        "annualized_6m_pct": None,
        "acceleration_3m_minus_6m_pp": None,
        "revision_basis": "latest_local_fred_not_original_release_vintage",
    }
    if series is None or series.empty:
        return empty
    monthly = _monthly_levels(series)
    if monthly.empty or pd.isna(monthly.iloc[-1]):
        return empty
    ann3 = _level_change(monthly, 3, annualized=True)
    ann6 = _level_change(monthly, 6, annualized=True)
    period = str(monthly.index[-1])
    return {
        **empty,
        "available": True,
        "observation_period": period,
        "observation_age_months": _month_age(period, as_of),
        "index_level": _number(monthly.iloc[-1], digits=3),
        "mom_pct": _level_change(monthly, 1, annualized=False),
        "yoy_pct": _level_change(monthly, 12, annualized=False),
        "annualized_3m_pct": ann3,
        "annualized_6m_pct": ann6,
        "acceleration_3m_minus_6m_pp": (
            _number(ann3 - ann6) if ann3 is not None and ann6 is not None else None
        ),
    }


def _monthly_proxy_state(
    series: pd.Series | None,
    series_id: str,
    label: str,
    as_of: date,
) -> dict[str, Any]:
    empty = {
        "available": False,
        "series_id": series_id,
        "label": label,
        "observation_period": None,
        "monthly_pct": None,
        "annualized_3m_pct": None,
        "annualized_6m_pct": None,
        "acceleration_3m_minus_6m_pp": None,
        "revision_basis": "latest_local_fred_proxy_series",
    }
    if series is None or series.empty:
        return empty
    clean = pd.to_numeric(series, errors="coerce").dropna().sort_index()
    if clean.empty:
        return empty
    ann3_series = _smooth_annual_rate(clean, 3).dropna()
    ann6_series = _smooth_annual_rate(clean, 6).dropna()
    ann3 = _number(ann3_series.iloc[-1]) if not ann3_series.empty else None
    ann6 = _number(ann6_series.iloc[-1]) if not ann6_series.empty else None
    period = str(clean.index[-1].to_period("M"))
    return {
        **empty,
        "available": True,
        "observation_period": period,
        "observation_age_months": _month_age(period, as_of),
        "monthly_pct": _number(clean.iloc[-1]),
        "annualized_3m_pct": ann3,
        "annualized_6m_pct": ann6,
        "acceleration_3m_minus_6m_pp": (
            _number(ann3 - ann6) if ann3 is not None and ann6 is not None else None
        ),
    }


def _cpi_entries(radar: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not radar:
        return []
    upcoming = radar.get("upcoming")
    if not isinstance(upcoming, list):
        return []
    return [
        row for row in upcoming
        if isinstance(row, dict)
        and row.get("release_type") in {"cpi_headline", "cpi_core"}
    ]


def _forecast_evolution(
    ledger_rows: list[dict[str, Any]],
    release_type: str,
    period: str | None,
) -> dict[str, Any]:
    # One authoritative/champion projection per as-of. Shadow model rows are kept
    # in the source ledger but excluded from this path to avoid mixing model identities.
    by_asof: dict[str, dict[str, Any]] = {}
    for row in ledger_rows:
        if row.get("release") != release_type or str(row.get("period") or "") != str(period or ""):
            continue
        if row.get("row_type") not in (None, "projection"):
            continue
        if row.get("model") not in (None, "", "champion"):
            continue
        asof = str(row.get("asof_night") or row.get("asof") or "")
        if not asof:
            continue
        by_asof[asof] = {
            "asof": asof,
            "point": _number(row.get("projection_point")),
            "p10": _number(row.get("projection_p10")),
            "p25": _number(row.get("projection_p25")),
            "p50": _number(row.get("projection_p50")),
            "p75": _number(row.get("projection_p75")),
            "p90": _number(row.get("projection_p90")),
            "confidence": _number(row.get("confidence")),
            "input_completeness": _number(row.get("input_completeness")),
            "cutoff_label": row.get("cutoff_label"),
            "prediction_id": row.get("prediction_id"),
        }
    points = [by_asof[key] for key in sorted(by_asof)]
    return {
        "basis": "append_only_release_radar_forward_ledger_champion_path",
        "n_points": len(points),
        "first_asof": points[0]["asof"] if points else None,
        "last_asof": points[-1]["asof"] if points else None,
        "points": points,
    }


def _coverage(entry: dict[str, Any]) -> dict[str, Any]:
    flags = entry.get("coverage_flags") if isinstance(entry.get("coverage_flags"), dict) else {}
    pit = entry.get("pit") if isinstance(entry.get("pit"), dict) else {}
    bridge = ((entry.get("shadows") or {}).get("cpi_bridge")
              if isinstance(entry.get("shadows"), dict) else None)
    bridge = bridge if isinstance(bridge, dict) else {}
    return {
        "input_completeness": _number(entry.get("input_completeness")),
        "radar_weight_coverage": _number(flags.get("weight_coverage")),
        "radar_fresh_proxy_coverage": _number(flags.get("fresh_proxy_coverage")),
        "radar_non_vintaged_share": _number(flags.get("non_vintaged_share")),
        "model_maturity_n": flags.get("model_maturity"),
        "bridge_modelled_weight_coverage": _number(bridge.get("weight_coverage")),
        "bridge_prior_driven_share": _number(bridge.get("prior_driven_share")),
        "bridge_weight_basis": bridge.get("weight_basis"),
        "bridge_weight_basis_warning": bridge.get("weight_basis_warning"),
        "bridge_known_scope_mismatches": bridge.get("known_scope_mismatches") or [],
        "absent_legs": sorted(str(x) for x in (pit.get("absent_legs") or [])),
        "revision_optimistic_legs": sorted(
            str(x) for x in (pit.get("revision_optimistic_legs") or [])
        ),
        "range_violation_legs": sorted(str(x) for x in (pit.get("range_violation_legs") or [])),
    }


def _component_freshness(entry: dict[str, Any], forecast_asof: str | None) -> list[dict[str, Any]]:
    bridge = ((entry.get("shadows") or {}).get("cpi_bridge")
              if isinstance(entry.get("shadows"), dict) else None)
    components = bridge.get("components") if isinstance(bridge, dict) else None
    basis = "cpi_bridge"
    if not isinstance(components, list):
        components = entry.get("components") if isinstance(entry.get("components"), list) else []
        basis = "release_radar_components"

    out: list[dict[str, Any]] = []
    for component in components:
        if not isinstance(component, dict):
            continue
        prior_only = bool(component.get("prior_only"))
        degraded = bool(component.get("degraded"))
        missing = sorted(str(x) for x in (component.get("missing_legs") or []))
        if prior_only:
            status = "prior_only"
        elif degraded or missing:
            status = "degraded_proxy"
        elif _number(component.get("confidence")) == 0.0:
            status = "prior_or_unmodelled"
        else:
            status = "proxy_available"
        out.append({
            "component": component.get("block") or component.get("name"),
            "basis": basis,
            "forecast_asof": forecast_asof,
            "status": status,
            "contribution_pp": _number(
                component.get("contribution_pp", component.get("contrib_pp"))
            ),
            "component_mom_estimate_pct": _number(component.get("mom_est")),
            "weight_pct": _number(component.get("weight")),
            "confidence": _number(component.get("confidence")),
            "legs_used": component.get("legs_used"),
            "legs_expected": component.get("legs_expected"),
            "missing_legs": missing,
        })
    return out


def _forecast_target(
    entry: dict[str, Any] | None,
    ledger_rows: list[dict[str, Any]],
    radar_asof: str | None,
) -> dict[str, Any]:
    if not entry:
        return {
            "available": False,
            "release_type": None,
            "period": None,
            "release_date": None,
            "release_radar_projection": None,
            "combined_display_estimate": None,
            "coverage": {},
            "component_freshness": [],
            "forecast_evolution": {
                "basis": "append_only_release_radar_forward_ledger_champion_path",
                "n_points": 0,
                "first_asof": None,
                "last_asof": None,
                "points": [],
            },
        }
    projection = entry.get("projection") if isinstance(entry.get("projection"), dict) else {}
    combined = entry.get("combined") if isinstance(entry.get("combined"), dict) else {}
    combined_components = (
        combined.get("combined_components")
        if isinstance(combined.get("combined_components"), dict) else {}
    )
    inputs_used = [str(x) for x in (combined_components.get("inputs_used") or [])]
    release_type = str(entry.get("release_type") or "")
    period = str(entry.get("period") or "") or None
    primary = {
        "point": _number(projection.get("point")),
        "p10": _number(projection.get("p10")),
        "p25": _number(projection.get("p25")),
        "p50": _number(projection.get("p50")),
        "p75": _number(projection.get("p75")),
        "p90": _number(projection.get("p90")),
        "confidence": _number(entry.get("confidence")),
    }
    combined_display = None
    if combined:
        combined_display = {
            "point": _number(combined.get("combined_point")),
            "p10": _number(combined.get("p10")),
            "p25": _number(combined.get("p25")),
            "p50": _number(combined.get("p50")),
            "p75": _number(combined.get("p75")),
            "p90": _number(combined.get("p90")),
            "inputs_used": inputs_used,
            "includes_external_benchmark": any(
                name in {"cleveland", "consensus"} for name in inputs_used
            ),
            "n_scored_basis": combined.get("n_scored_basis"),
            "display_only": True,
            "authority": False,
        }
    return {
        "available": any(value is not None for value in primary.values()),
        "release_type": release_type or None,
        "period": period,
        "release_date": entry.get("release_date"),
        "days_to_release": entry.get("days_to"),
        "target": entry.get("target"),
        "forecast_asof": radar_asof,
        "release_radar_projection": primary,
        "combined_display_estimate": combined_display,
        "coverage": _coverage(entry),
        "component_freshness": _component_freshness(entry, radar_asof),
        "input_snapshot_ref": entry.get("input_snapshot_ref"),
        "forecast_evolution": _forecast_evolution(ledger_rows, release_type, period),
    }


def _entries_for_date(entries: list[dict[str, Any]], release_date: str) -> dict[str, dict[str, Any]]:
    return {
        str(entry.get("release_type")): entry
        for entry in entries
        if str(entry.get("release_date") or "") == release_date
    }


def _next_release_block(
    entries: list[dict[str, Any]],
    ledger_rows: list[dict[str, Any]],
    radar_asof: str | None,
    as_of: date,
) -> tuple[dict[str, Any], str | None]:
    future = [
        entry for entry in entries
        if (_parse_date(entry.get("release_date")) or date.max) >= as_of
    ]
    dated = [entry for entry in future if _parse_date(entry.get("release_date")) is not None]
    if not dated:
        return {
            "available": False,
            "release_date": None,
            "period": None,
            "headline": _forecast_target(None, ledger_rows, radar_asof),
            "core": _forecast_target(None, ledger_rows, radar_asof),
        }, None
    release_date = min(str(entry.get("release_date")) for entry in dated)
    grouped = _entries_for_date(dated, release_date)
    headline = grouped.get("cpi_headline")
    core = grouped.get("cpi_core")
    period = (headline or core or {}).get("period")
    return {
        "available": bool(headline or core),
        "release_date": release_date,
        "period": period,
        "headline": _forecast_target(headline, ledger_rows, radar_asof),
        "core": _forecast_target(core, ledger_rows, radar_asof),
    }, str(period) if period is not None else None


def _pressure_direction(value: float | None) -> str | None:
    if value is None:
        return None
    if value > 0:
        return "upward_price_pressure"
    if value < 0:
        return "downward_price_pressure"
    return "flat_model_pressure"


def _current_month_pressure_block(
    entries: list[dict[str, Any]],
    ledger_rows: list[dict[str, Any]],
    radar_asof: str | None,
    as_of: date,
    sticky: dict[str, Any],
    flexible: dict[str, Any],
) -> dict[str, Any]:
    period = f"{as_of.year:04d}-{as_of.month:02d}"
    current = {
        str(entry.get("release_type")): entry
        for entry in entries
        if str(entry.get("period") or "") == period
    }
    headline_entry = current.get("cpi_headline")
    core_entry = current.get("cpi_core")
    headline = _forecast_target(headline_entry, ledger_rows, radar_asof)
    core = _forecast_target(core_entry, ledger_rows, radar_asof)
    hpoint = None
    if headline.get("release_radar_projection"):
        hpoint = headline["release_radar_projection"].get("point")
    sticky_ann = sticky.get("annualized_3m_pct")
    flexible_ann = flexible.get("annualized_3m_pct")
    if sticky_ann is not None and flexible_ann is not None:
        proxy_mix = "sticky_led" if sticky_ann >= flexible_ann else "flexible_led"
    else:
        proxy_mix = None
    components = _component_freshness(headline_entry or {}, radar_asof)
    return {
        "available": bool(headline.get("available") or core.get("available")
                          or sticky.get("available") or flexible.get("available")),
        "period": period,
        "definition": (
            "Public-data and model pressure for the in-progress reference month; "
            "not an official CPI observation, not a real-time CPI index, and not a "
            "substitute for the next BLS release."
        ),
        "pressure_direction": _pressure_direction(hpoint),
        "headline_model_pressure": headline,
        "core_model_pressure": core,
        "underlying_proxy_mix": {
            "read": proxy_mix,
            "sticky": sticky,
            "flexible": flexible,
        },
        "component_freshness": components,
        "coverage": _coverage(headline_entry or {}),
    }


def build_inflation_intelligence(
    root: str | Path | None = None,
    *,
    as_of: str | date | None = None,
    radar_latest_path: str | Path | None = None,
    forward_ledger_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build a JSON-safe ``inflation_intelligence.v1`` payload. Never raises."""
    repo = _repo_root(root)
    gaps: list[str] = []
    radar_path = _resolve(repo, radar_latest_path, DEFAULT_RADAR_LATEST)
    ledger_path = _resolve(repo, forward_ledger_path, DEFAULT_FORWARD_LEDGER)

    radar = _read_json(radar_path, "release_radar_latest", gaps)
    radar_asof = str(radar.get("asof")) if radar and radar.get("asof") else None
    resolved_asof = (
        _parse_date(as_of)
        or _parse_date(radar_asof)
        or datetime.now(timezone.utc).date()
    )
    ledger_rows, ledger_status = _read_ledger(repo, ledger_path, gaps)

    series: dict[str, pd.Series | None] = {}
    fred_status: dict[str, dict[str, Any]] = {}
    for key, (series_id, column) in _FRED_SERIES.items():
        series[key], fred_status[key] = _read_fred_series(
            repo, series_id, column, resolved_asof, gaps
        )

    released_headline = _released_index_state(
        series["headline"], _FRED_SERIES["headline"][0], "Headline CPI-U", resolved_asof
    )
    released_core = _released_index_state(
        series["core"], _FRED_SERIES["core"][0], "Core CPI-U", resolved_asof
    )
    sticky = _monthly_proxy_state(
        series["sticky"], _FRED_SERIES["sticky"][0], "Sticky-price CPI proxy", resolved_asof
    )
    flexible = _monthly_proxy_state(
        series["flexible"], _FRED_SERIES["flexible"][0], "Flexible-price CPI proxy", resolved_asof
    )

    released_state = {
        "available": bool(released_headline["available"] or released_core["available"]),
        "basis": "latest_local_fred_official_index_levels_not_original_release_vintage",
        "headline": released_headline,
        "core": released_core,
        "underlying_proxies": {"sticky": sticky, "flexible": flexible},
    }

    entries = _cpi_entries(radar)
    next_release, _ = _next_release_block(
        entries, ledger_rows, radar_asof, resolved_asof
    )
    current_pressure = _current_month_pressure_block(
        entries, ledger_rows, radar_asof, resolved_asof, sticky, flexible
    )

    return {
        "schema": SCHEMA,
        "asof": resolved_asof.isoformat(),
        "display_only": True,
        "authority": False,
        "is_context_only": True,
        "allowed_actions": {
            "may_rank": False,
            "may_score": False,
            "may_size": False,
            "may_gate": False,
            "may_escalate": False,
            "may_trade": False,
        },
        "authority_note": _AUTHORITY_NOTE,
        "released_state": released_state,
        "next_release_forecast": next_release,
        "current_month_proxy_pressure": current_pressure,
        "source_status": {
            "fred": fred_status,
            "release_radar_latest": {
                "available": radar is not None,
                "path": _path_label(repo, radar_path),
                "asof": radar_asof,
                "cpi_entries": len(entries),
            },
            "release_radar_forward_ledger": ledger_status,
        },
        "gaps": sorted(set(gaps)),
    }


def write_inflation_intelligence(
    root: str | Path | None = None,
    *,
    output_path: str | Path | None = None,
    as_of: str | date | None = None,
    radar_latest_path: str | Path | None = None,
    forward_ledger_path: str | Path | None = None,
) -> tuple[dict[str, Any], Path]:
    """Build and atomically replace the artifact file."""
    repo = _repo_root(root)
    target = _resolve(repo, output_path, DEFAULT_OUTPUT)
    payload = build_inflation_intelligence(
        repo,
        as_of=as_of,
        radar_latest_path=radar_latest_path,
        forward_ledger_path=forward_ledger_path,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(target)
    return payload, target
