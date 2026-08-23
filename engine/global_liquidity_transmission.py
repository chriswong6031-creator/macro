"""Causal Global Liquidity Transmission state producer (W-LIQ.1).

This module is deliberately a measurement-only leaf.  It reads already-owned
Macro stores, aligns every observation to a conservative availability date,
and produces candidate state factors.  It has no trading, alerting, routing,
or transmission-curve authority.

The pure functions accept in-memory series so the point-in-time properties can
be tested without touching the repository stores.  Repository I/O lives in the
small ``load_inputs`` / ``build_contract`` boundary at the bottom of the file.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
import yaml

from engine.canon import credit_impulse_accel, credit_impulse_level
from lib import config as macro_config
from lib import store


CONTRACT_SCHEMA = "global_liquidity_transmission.v1"
STATE_COLUMNS = (
    "monetary_stance",
    "monetary_impulse",
    "orthogonalised_impulse",
    "liquidity_breadth",
    "usd_funding_impulse",
)


@dataclass(frozen=True)
class AlignedComponent:
    """One source after release-date alignment onto the weekly decision grid."""

    value: pd.Series
    reference_date: pd.Series
    available_date: pd.Series
    usable: pd.Series


def load_producer_config(path: Path | None = None) -> dict[str, Any]:
    path = path or Path(macro_config.ROOT) / "config/global_liquidity_transmission_v1.yml"
    return yaml.safe_load(path.read_text())


def _normalise_series(series: pd.Series) -> pd.Series:
    out = pd.to_numeric(series, errors="coerce").dropna().copy()
    idx = pd.DatetimeIndex(pd.to_datetime(out.index))
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    out.index = idx.normalize()
    return out[~out.index.duplicated(keep="last")].sort_index()


def _period_reference(index: pd.DatetimeIndex, period_anchor: str) -> pd.DatetimeIndex:
    if period_anchor == "month_end":
        return index.to_period("M").to_timestamp("M")
    if period_anchor != "observation_date":
        raise ValueError(f"unsupported period_anchor={period_anchor!r}")
    return index


def _asof_values(source: pd.Series, at: pd.DatetimeIndex) -> np.ndarray:
    """Return the last source value known on or before each timestamp in ``at``."""
    source = _normalise_series(source)
    union = source.index.union(at).sort_values()
    return source.reindex(union).ffill().reindex(at).to_numpy(dtype=float)


def align_component(
    raw: pd.Series,
    spec: Mapping[str, Any],
    grid: pd.DatetimeIndex,
    fx: pd.Series | None = None,
) -> AlignedComponent:
    """Convert and causally align one raw source to ``grid``.

    Monthly end-of-period sources may be labelled by the provider on the first
    day of their month.  ``period_anchor: month_end`` moves only the economic
    reference date; the value becomes usable after the configured business-day
    release lag.  FX is sampled on or before the economic reference date, never
    on the later build date.
    """
    raw = _normalise_series(raw)
    grid = pd.DatetimeIndex(pd.to_datetime(grid)).tz_localize(None).normalize()
    reference = _period_reference(pd.DatetimeIndex(raw.index), str(spec["period_anchor"]))
    values = raw.to_numpy(dtype=float) * float(spec.get("unit_multiplier", 1.0))

    if fx is not None:
        fx_values = _asof_values(fx, reference)
        if bool((spec.get("fx") or {}).get("invert", False)):
            fx_values = 1.0 / fx_values
        values = values * fx_values

    available = reference + pd.offsets.BDay(int(spec.get("release_lag_bdays", 0)))
    events = pd.DataFrame(
        {
            "value": values,
            "reference_date": reference,
            "available_date": available,
        },
        index=available,
    )
    events = events[~events.index.duplicated(keep="last")].sort_index()
    expanded = events.reindex(events.index.union(grid).sort_values()).ffill().reindex(grid)
    age_days = (pd.Series(grid, index=grid) - pd.to_datetime(expanded["reference_date"])).dt.days
    usable = expanded["value"].notna() & age_days.le(int(spec["stale_after_calendar_days"]))
    return AlignedComponent(
        value=expanded["value"].where(usable).astype(float),
        reference_date=pd.to_datetime(expanded["reference_date"]),
        available_date=pd.to_datetime(expanded["available_date"]),
        usable=usable.astype(bool),
    )


def causal_expanding_z(series: pd.Series, min_periods: int) -> pd.Series:
    """Expanding z-score whose parameters contain observations strictly before t."""
    series = pd.to_numeric(series, errors="coerce").astype(float)
    prior_mean = series.expanding(min_periods=min_periods).mean().shift(1)
    prior_std = series.expanding(min_periods=min_periods).std(ddof=1).shift(1)
    out = (series - prior_mean) / prior_std.replace(0.0, np.nan)
    return out.replace([np.inf, -np.inf], np.nan)


def causal_orthogonal_residual(
    impulse: pd.Series,
    stance: pd.Series,
    min_periods: int,
) -> pd.Series:
    """Residualise current impulse on stance using only earlier paired rows."""
    y = pd.to_numeric(impulse, errors="coerce").astype(float)
    x = pd.to_numeric(stance, errors="coerce").astype(float)
    result = pd.Series(np.nan, index=y.index, dtype=float)
    for pos in range(len(y)):
        if not np.isfinite(y.iloc[pos]) or not np.isfinite(x.iloc[pos]):
            continue
        prior = pd.DataFrame({"y": y.iloc[:pos], "x": x.iloc[:pos]}).dropna()
        if len(prior) < min_periods or prior["x"].nunique() < 2:
            continue
        design = np.column_stack([np.ones(len(prior)), prior["x"].to_numpy()])
        beta, *_ = np.linalg.lstsq(design, prior["y"].to_numpy(), rcond=None)
        result.iloc[pos] = y.iloc[pos] - (beta[0] + beta[1] * x.iloc[pos])
    return result


def _weighted_available_mean(
    values: pd.DataFrame,
    weights: Mapping[str, float],
    minimum_ratio: float,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    weight = pd.Series({name: float(weights[name]) for name in values.columns})
    present = values.notna()
    available_weight = present.mul(weight, axis=1).sum(axis=1)
    total_weight = float(weight.sum())
    coverage = available_weight / total_weight
    numerator = values.mul(weight, axis=1).sum(axis=1, min_count=1)
    composite = (numerator / available_weight.replace(0.0, np.nan)).where(coverage >= minimum_ratio)
    return composite, coverage, present.sum(axis=1).astype(int)


def build_state_history(
    monetary_raw: Mapping[str, pd.Series],
    monetary_fx: Mapping[str, pd.Series | None],
    funding_raw: Mapping[str, pd.Series],
    producer_cfg: Mapping[str, Any],
    *,
    asof: pd.Timestamp | str | None = None,
) -> tuple[pd.DataFrame, dict[str, AlignedComponent], dict[str, AlignedComponent]]:
    """Build the causal weekly W-LIQ.1 state history from in-memory sources."""
    if not monetary_raw:
        raise ValueError("at least one monetary component is required")
    if asof is not None:
        end = pd.Timestamp(asof).normalize()
    else:
        availability_tips: list[pd.Timestamp] = []
        for name, series in monetary_raw.items():
            spec = producer_cfg["monetary_components"][name]
            tip = _normalise_series(series).index[-1:]
            ref = _period_reference(pd.DatetimeIndex(tip), str(spec["period_anchor"]))[0]
            availability_tips.append(ref + pd.offsets.BDay(int(spec.get("release_lag_bdays", 0))))
        for name, series in funding_raw.items():
            spec = producer_cfg["usd_funding_components"][name]
            tip = _normalise_series(series).index[-1:]
            ref = _period_reference(pd.DatetimeIndex(tip), str(spec["period_anchor"]))[0]
            availability_tips.append(ref + pd.offsets.BDay(int(spec.get("release_lag_bdays", 0))))
        end = max(availability_tips)
    start = min(_normalise_series(series).index.min() for series in monetary_raw.values())
    grid = pd.date_range(start=start, end=end, freq=str(producer_cfg["frequency"]))
    if grid.empty:
        raise ValueError("no weekly observations in requested interval")

    monetary_aligned: dict[str, AlignedComponent] = {}
    monetary_scores: dict[str, pd.Series] = {}
    monetary_weights: dict[str, float] = {}
    for name, raw in monetary_raw.items():
        spec = producer_cfg["monetary_components"][name]
        aligned = align_component(raw, spec, grid, monetary_fx.get(name))
        monetary_aligned[name] = aligned
        transformed = np.log(aligned.value.where(aligned.value > 0.0))
        monetary_scores[name] = causal_expanding_z(
            transformed, int(producer_cfg["min_history_periods"])
        )
        monetary_weights[name] = float(spec.get("weight", 1.0))

    monetary_frame = pd.DataFrame(monetary_scores, index=grid)
    stance, monetary_coverage, monetary_count = _weighted_available_mean(
        monetary_frame,
        monetary_weights,
        float(producer_cfg["min_monetary_coverage_ratio"]),
    )
    impulse = stance.diff()
    orthogonal = causal_orthogonal_residual(
        impulse,
        stance,
        int(producer_cfg["orthogonal_min_history_periods"]),
    )
    improvement = monetary_frame.diff().gt(0.0).where(monetary_frame.notna())
    breadth = improvement.sum(axis=1, min_count=1) / monetary_frame.notna().sum(axis=1).replace(0, np.nan)
    breadth = breadth.where(monetary_coverage >= float(producer_cfg["min_monetary_coverage_ratio"]))

    funding_aligned: dict[str, AlignedComponent] = {}
    funding_scores: dict[str, pd.Series] = {}
    funding_weights: dict[str, float] = {}
    for name, raw in funding_raw.items():
        spec = producer_cfg["usd_funding_components"][name]
        aligned = align_component(raw, spec, grid)
        funding_aligned[name] = aligned
        periods = int(spec["change_periods"])
        if spec["change_transform"] == "log_change":
            change = np.log(aligned.value.where(aligned.value > 0.0)).diff(periods)
        elif spec["change_transform"] == "level_change":
            change = aligned.value.diff(periods)
        else:
            raise ValueError(f"unsupported change_transform={spec['change_transform']!r}")
        change = change * float(spec.get("direction_multiplier", 1.0))
        funding_scores[name] = causal_expanding_z(
            change, int(producer_cfg["min_history_periods"])
        )
        funding_weights[name] = float(spec.get("weight", 1.0))

    funding_frame = pd.DataFrame(funding_scores, index=grid)
    funding, funding_coverage, funding_count = _weighted_available_mean(
        funding_frame,
        funding_weights,
        float(producer_cfg["min_funding_coverage_ratio"]),
    )

    history = pd.DataFrame(
        {
            "monetary_stance": stance,
            "monetary_impulse": impulse,
            "orthogonalised_impulse": orthogonal,
            "liquidity_breadth": breadth,
            "usd_funding_impulse": funding,
            "monetary_coverage_ratio": monetary_coverage,
            "monetary_component_count": monetary_count,
            "funding_coverage_ratio": funding_coverage,
            "funding_component_count": funding_count,
        },
        index=grid,
    )
    for name, score in monetary_scores.items():
        history[f"monetary_component_z__{name}"] = score
    for name, score in funding_scores.items():
        history[f"funding_component_z__{name}"] = score
    history.index.name = "asof"
    return history, monetary_aligned, funding_aligned


def _read_store_series(spec: Mapping[str, Any]) -> pd.Series:
    frame = store.read(str(spec["store"]), str(spec["key"]))
    column = str(spec["column"])
    if frame is None or column not in frame:
        raise FileNotFoundError(f"missing canonical store {spec['store']}/{spec['key']}:{column}")
    return frame[column].dropna()


def load_inputs(producer_cfg: Mapping[str, Any]) -> tuple[dict, dict, dict]:
    monetary: dict[str, pd.Series] = {}
    fx: dict[str, pd.Series | None] = {}
    for name, spec in producer_cfg["monetary_components"].items():
        monetary[name] = _read_store_series(spec)
        fx_spec = spec.get("fx")
        fx[name] = _read_store_series(fx_spec) if fx_spec else None
    funding = {
        name: _read_store_series(spec)
        for name, spec in producer_cfg["usd_funding_components"].items()
    }
    return monetary, fx, funding


def _finite(value: Any, digits: int = 6) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, digits) if np.isfinite(number) else None


def canonical_hash(payload: Mapping[str, Any]) -> str:
    """Stable SHA-256 for a closed JSON object (no timestamps added implicitly)."""
    encoded = json.dumps(
        dict(payload), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _series_hash(series: pd.Series) -> str:
    """Stable content hash for a dated derived series, independent of parquet bytes."""
    digest = hashlib.sha256()
    for stamp, value in pd.to_numeric(series, errors="coerce").items():
        rendered = "null" if pd.isna(value) else format(float(value), ".17g")
        digest.update(f"{pd.Timestamp(stamp).date().isoformat()}={rendered}\n".encode("ascii"))
    return digest.hexdigest()


def _state_label(impulse: float | None, threshold: float) -> str:
    if impulse is None:
        return "unknown"
    if impulse > threshold:
        return "expanding"
    if impulse < -threshold:
        return "contracting"
    return "flat"


def _quality_label(state_label: str, us_quality: Mapping[str, Any] | None) -> str:
    us_label = str((us_quality or {}).get("label", "unknown"))
    if state_label == "expanding" and us_label == "benign-expansion":
        return "easing"
    if state_label == "contracting" and us_label == "contracting":
        return "tightening"
    if state_label == "unknown" and us_label == "unknown":
        return "unknown"
    return "mixed"


def _confidence(
    receipts: Mapping[str, Mapping[str, Any]],
    coverage: float | None,
    reliability: Mapping[str, float] | None = None,
) -> float | None:
    """Coverage times disclosed PIT reliability; it is data confidence, not alpha confidence."""
    if coverage is None:
        return None
    reliability = dict(
        reliability or {"low": 1.0, "medium": 0.75, "high": 0.5, "unknown": 0.5}
    )
    usable = [
        reliability.get(str(row.get("revision_risk", "unknown")), 0.5)
        for row in receipts.values()
        if row.get("status") == "usable"
    ]
    return _finite(float(coverage) * float(np.mean(usable)), 6) if usable else 0.0


def _latest_component_receipts(
    aligned: Mapping[str, AlignedComponent],
    specs: Mapping[str, Any],
    asof: pd.Timestamp,
) -> dict[str, dict[str, Any]]:
    receipts: dict[str, dict[str, Any]] = {}
    for name, component in aligned.items():
        pos = component.value.index.get_loc(asof)
        ref = component.reference_date.iloc[pos]
        avail = component.available_date.iloc[pos]
        usable = bool(component.usable.iloc[pos])
        receipts[name] = {
            "provider": specs[name]["provider"],
            "source_id": specs[name]["source_id"],
            "frequency": specs[name]["frequency"],
            "reference_date": None if pd.isna(ref) else str(pd.Timestamp(ref).date()),
            "available_date": None if pd.isna(avail) else str(pd.Timestamp(avail).date()),
            "age_calendar_days": None if pd.isna(ref) else int((asof - pd.Timestamp(ref)).days),
            "stale_after_calendar_days": int(specs[name]["stale_after_calendar_days"]),
            "status": "usable" if usable else "missing_or_stale",
            "pit_status": specs[name]["pit_status"],
            "revision_risk": specs[name]["revision_risk"],
        }
    return receipts


def _load_us_quality(root: Path, asof: pd.Timestamp) -> dict[str, Any] | None:
    path = root / "data/regime/latest.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    value = payload.get("liquidity_quality")
    if not isinstance(value, dict):
        return None
    quality_asof = pd.Timestamp(value.get("asof")) if value.get("asof") else None
    return value if quality_asof is not None and quality_asof <= asof else None


def _credit_context(root: Path, asof: pd.Timestamp) -> dict[str, Any]:
    """Expose non-comparable US/China directions without inventing a global scalar."""
    us_path = root / "data/fred/BUSLOANS.parquet"
    cn_path = root / "data/china_credit/tsf.parquet"
    us: dict[str, Any] = {"status": "missing"}
    china: dict[str, Any] = {"status": "missing"}

    if us_path.exists():
        frame = pd.read_parquet(us_path)
        series = pd.to_numeric(frame.get("ci_loans"), errors="coerce").dropna()
        series = series.loc[:asof]
        yoy = series.pct_change(12, fill_method=None) * 100.0
        if not yoy.empty and pd.notna(yoy.iloc[-1]):
            us = {
                "status": "context_only",
                "source_id": "BUSLOANS",
                "reference_date": str(pd.Timestamp(series.index[-1]).date()),
                "ci_loans_yoy_pct": _finite(yoy.iloc[-1], 3),
                "direction": "improving" if yoy.iloc[-1] > 0.5 else "weakening" if yoy.iloc[-1] < -0.5 else "flat",
                "pit_status": "initial_release_archive_available_from_1996_but_not_used_in_this_current_context_read",
            }

    if cn_path.exists():
        frame = pd.read_parquet(cn_path)
        if "availability_date" in frame:
            frame = frame[pd.to_datetime(frame["availability_date"]) <= asof]
        total = pd.to_numeric(frame.get("tsf_total"), errors="coerce").dropna()
        if not total.empty:
            level = credit_impulse_level(total)
            accel = credit_impulse_accel(total)
            value = accel.iloc[-1] if not accel.empty else np.nan
            china = {
                "status": "context_only",
                "source_id": "PBOC_TSF",
                "reference_date": str(pd.Timestamp(total.index[-1]).date()),
                "available_date": str(pd.Timestamp(frame.loc[total.index[-1], "availability_date"]).date()),
                "credit_impulse_level_pct": _finite(level.iloc[-1], 3) if not level.empty else None,
                "credit_impulse_acceleration_pct": _finite(value, 3),
                "direction": "improving" if pd.notna(value) and value > 0 else "weakening" if pd.notna(value) and value < 0 else "flat_or_unknown",
                "pit_status": "explicit_conservative_availability_date",
            }

    return {
        "credit_impulse_global": None,
        "status": "insufficient_comparable_pit_coverage",
        "reason": "US C&I loans and China TSF are different constructs; BIS coverage is quarterly and lacks repository release-vintage timestamps.",
        "components": {"us_bank_credit": us, "china_total_social_financing": china},
    }


def build_contract(
    *,
    producer_cfg: Mapping[str, Any] | None = None,
    root: Path | None = None,
    asof: pd.Timestamp | str | None = None,
    generated_at: datetime | None = None,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Build the public state-only contract and its causal historical frame."""
    producer_cfg = dict(producer_cfg or load_producer_config())
    root = Path(root or macro_config.ROOT)
    monetary, fx, funding = load_inputs(producer_cfg)
    history, monetary_aligned, funding_aligned = build_state_history(
        monetary, fx, funding, producer_cfg, asof=asof
    )
    usable_history = history.dropna(subset=["monetary_stance"])
    if usable_history.empty:
        raise ValueError("no usable monetary state after PIT and coverage gates")
    latest_index = usable_history.index[-1]
    latest = history.loc[latest_index]
    current_impulse = _finite(latest["monetary_impulse"])
    threshold = float(producer_cfg["quality_thresholds"]["monetary_impulse_z"])
    monetary_receipts = _latest_component_receipts(
        monetary_aligned, producer_cfg["monetary_components"], latest_index
    )
    funding_receipts = _latest_component_receipts(
        funding_aligned, producer_cfg["usd_funding_components"], latest_index
    )
    missing = [
        f"monetary:{name}" for name, row in monetary_receipts.items() if row["status"] != "usable"
    ] + [
        f"funding:{name}" for name, row in funding_receipts.items() if row["status"] != "usable"
    ]
    credit = (
        _credit_context(root, latest_index)
        if asof is None
        else {
            "credit_impulse_global": None,
            "status": "not_pit_reconstructed_for_historical_contract",
            "reason": "W-LIQ.1 backfills state factors only; current-vintage US/China credit context is not projected backward.",
            "components": {},
        }
    )
    us_quality = _load_us_quality(root, latest_index)
    generated_at = generated_at or datetime.now(timezone.utc)
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    generated_at_utc = generated_at.astimezone(timezone.utc)

    component_snapshot: dict[str, dict[str, Any]] = {"monetary": {}, "usd_funding": {}}
    for name, receipt in monetary_receipts.items():
        material = {
            "receipt": receipt,
            "current_contribution_z": _finite(latest[f"monetary_component_z__{name}"]),
            "history_hash": _series_hash(history[f"monetary_component_z__{name}"]),
            "model_spec": producer_cfg["monetary_components"][name],
        }
        component_snapshot["monetary"][name] = {
            **material,
            "component_hash": canonical_hash(material),
        }
    for name, receipt in funding_receipts.items():
        material = {
            "receipt": receipt,
            "current_contribution_z": _finite(latest[f"funding_component_z__{name}"]),
            "history_hash": _series_hash(history[f"funding_component_z__{name}"]),
            "model_spec": producer_cfg["usd_funding_components"][name],
        }
        component_snapshot["usd_funding"][name] = {
            **material,
            "component_hash": canonical_hash(material),
        }

    config_hash = canonical_hash(producer_cfg)
    snapshot_material = {
        "config_hash": config_hash,
        "components": component_snapshot,
        "us_liquidity_quality_hash": canonical_hash(us_quality or {"status": "missing"}),
        "global_credit_context_hash": canonical_hash(credit),
        "state_asof": str(latest_index.date()),
    }
    source_snapshot_hash = canonical_hash(snapshot_material)
    model_version = "glt_state.v1"
    data_version = f"glt_data:{source_snapshot_hash[:16]}"
    state_label = _state_label(current_impulse, threshold)
    monetary_coverage = _finite(latest["monetary_coverage_ratio"])
    funding_coverage = _finite(latest["funding_coverage_ratio"])
    state_confidence = _confidence(
        monetary_receipts,
        monetary_coverage,
        producer_cfg.get("confidence_revision_reliability"),
    )
    monetary_missing = [
        name for name, row in monetary_receipts.items() if row["status"] != "usable"
    ]
    freshness_status = (
        "unknown"
        if current_impulse is None
        else "degraded"
        if monetary_missing
        else "fresh"
    )
    quality_label = _quality_label(state_label, us_quality)
    direction_sign = None if current_impulse is None or current_impulse == 0.0 else (
        1 if current_impulse > 0.0 else -1
    )
    usable_monetary = [row for row in monetary_receipts.values() if row["status"] == "usable"]
    latest_observed = max(row["reference_date"] for row in usable_monetary)
    latest_release = max(row["available_date"] for row in usable_monetary)
    clocks = {
        "state_asof": f"{latest_index.date().isoformat()}T00:00:00Z",
        "latest_component_observed_at": f"{latest_observed}T00:00:00Z",
        "release_at": f"{latest_release}T00:00:00Z",
        "first_known_at": generated_at_utc.isoformat().replace("+00:00", "Z"),
        "release_clock_precision": "conservative_date_only",
        "adapter_observed_at_field": "release_at",
        "adapter_known_at_field": "first_known_at",
    }

    payload: dict[str, Any] = {
        "meta": {
            "schema": CONTRACT_SCHEMA,
            "producer_version": producer_cfg["producer_version"],
            "model_version": model_version,
            "data_version": data_version,
            "config_hash": config_hash,
            "source_snapshot_hash": source_snapshot_hash,
            "hash_algorithm": "sha256_canonical_json",
            "generated_at": generated_at_utc.isoformat(),
            "authority": producer_cfg["authority"],
            "frequency": producer_cfg["frequency"],
            "owner": "Macro/Data Producer W-LIQ.1",
            "architecture_authority": "Mastermind issue #117; orchestration and acceptance authority Mastermind issue #123",
            "contract_scope": "state_quality_freshness_only",
            "forbidden_authority": ["trade", "allocation", "alert", "dispatch", "transmission_curve", "repricing_gap"],
            "methodology": "research/GLOBAL_LIQUIDITY_TRANSMISSION_STATE_METHODOLOGY_2026-08-22.md",
            "pit_policy": "economic reference date plus conservative business-day release lag; expanding transforms use only prior observations",
            "revision_law": {
                "snapshot_identity": "source_snapshot_hash",
                "exact_retry": "same hash is the same immutable source snapshot and preserves its earliest published first_known_at",
                "changed_source_or_model": "emit a new snapshot and data/model version; never rewrite a downstream first-known episode",
                "episode_amendments": "owned by W-LIQ.3 append-only ledgers, not this producer",
            },
            "historical_first_known_status": "not_reconstructable_before_this_producer_existed",
        },
        "state": {
            "asof": str(latest_index.date()),
            "label": state_label,
            "label_enum": ["expanding", "flat", "contracting", "unknown"],
            "monetary_stance": _finite(latest["monetary_stance"]),
            "monetary_impulse": current_impulse,
            "orthogonalised_impulse": _finite(latest["orthogonalised_impulse"]),
            "liquidity_breadth": _finite(latest["liquidity_breadth"]),
            "credit_impulse_global": None,
            "usd_funding_impulse": _finite(latest["usd_funding_impulse"]),
            "policy_liquidity_impulse": current_impulse,
            "units": {
                "monetary_stance": "expanding_z_score",
                "monetary_impulse": "weekly_change_in_expanding_z_score",
                "orthogonalised_impulse": "causal_regression_residual_z_units",
                "liquidity_breadth": "share_0_to_1",
                "credit_impulse_global": "null_until_comparable_pit_coverage",
                "usd_funding_impulse": "expanding_z_score_positive_is_easier",
                "policy_liquidity_impulse": "weekly_change_in_expanding_z_score",
            },
            "event_reference": {
                "producer_schema": CONTRACT_SCHEMA,
                "source_snapshot_hash": source_snapshot_hash,
                "model_version": model_version,
                "data_version": data_version,
                "state_family": "monetary_impulse",
                "shock_type": "policy_liquidity_impulse",
                "direction": direction_sign,
                "direction_label": state_label,
                "magnitude_z": current_impulse,
                "breadth": _finite(latest["liquidity_breadth"]),
                "quality": quality_label,
                "confidence": state_confidence,
                "confidence_semantics": "monetary coverage times mean disclosed PIT reliability; data confidence only, not predictive confidence",
                "coverage": monetary_coverage,
                "freshness": freshness_status,
                "clocks": clocks,
                "conditions": {
                    "us_liquidity_quality": (us_quality or {}).get("label", "unknown"),
                    "usd_funding_impulse": _finite(latest["usd_funding_impulse"]),
                },
                "regional_gates": {},
                "component_snapshot": component_snapshot,
            },
        },
        "quality": {
            "status": "degraded" if missing or us_quality is None else "measured",
            "degraded": bool(missing or us_quality is None),
            "missing_or_stale": missing,
            "us_liquidity_quality": us_quality,
            "global_credit": credit,
            "event_quality": quality_label,
            "confidence": {
                "value": state_confidence,
                "kind": "data_lineage_and_coverage_only",
                "not": ["predictive_probability", "alpha_confidence", "promotion_grade"],
            },
            "source_semantics": {
                "monetary": "Fed, ECB, and BoJ balance-sheet stance; coverage-renormalised, never zero-filled",
                "treasury_plumbing": "canonical US WALCL minus RRP minus TGA quality classifier, reused without re-derivation",
                "credit": "US and China directions remain separate context; no false global scalar",
                "usd_funding": "broad dollar, 10Y real yield, and HY OAS; positive means easier funding",
            },
            "revision_limitations": [
                "ECB and BoJ stores do not carry full vintage histories; release-lag alignment does not eliminate later-revision risk.",
                "China M2 has no repository release timestamp or vintage and is excluded from the causal state.",
                "NFCI and ANFCI revise their full histories and are excluded from the causal state.",
                "BoE, SNB, and clean keyless PBoC total assets lack adequate canonical balance-sheet feeds and are omitted.",
            ],
        },
        "freshness": {
            "asof": str(latest_index.date()),
            "degraded": bool(missing),
            "status": freshness_status,
            "clocks": clocks,
            "monetary_coverage_ratio": monetary_coverage,
            "funding_coverage_ratio": funding_coverage,
            "components": {"monetary": monetary_receipts, "usd_funding": funding_receipts},
            "component_snapshot": component_snapshot,
        },
    }
    return payload, history


def walk_forward_factor_comparison(
    history: pd.DataFrame,
    asset_close: pd.Series,
    *,
    horizon_weeks: int = 4,
    initial_train_weeks: int = 208,
    test_weeks: int = 52,
    purge_weeks: int = 4,
) -> dict[str, Any]:
    """Frozen one-asset/one-horizon walk-forward comparison for candidate factors.

    This is research evidence, not a promotion test.  The purge removes labels
    whose forward-return window overlaps the first test observation.
    """
    close = _normalise_series(asset_close).resample("W-FRI").last().ffill()
    future_return = np.log(close.shift(-horizon_weeks) / close)
    data = history[list(STATE_COLUMNS[:3])].join(future_return.rename("target"), how="inner")
    data = data.dropna(subset=["target"])
    results: dict[str, Any] = {}

    for factor in STATE_COLUMNS[:3]:
        frame = data[[factor, "target"]].dropna()
        folds: list[dict[str, Any]] = []
        predictions: list[float] = []
        actuals: list[float] = []
        test_start = initial_train_weeks + purge_weeks
        while test_start < len(frame):
            train_end = test_start - purge_weeks
            test_end = min(test_start + test_weeks, len(frame))
            train = frame.iloc[:train_end]
            test = frame.iloc[test_start:test_end]
            if len(train) < initial_train_weeks or test.empty or train[factor].nunique() < 2:
                break
            design = np.column_stack([np.ones(len(train)), train[factor].to_numpy()])
            beta, *_ = np.linalg.lstsq(design, train["target"].to_numpy(), rcond=None)
            pred = beta[0] + beta[1] * test[factor].to_numpy()
            predictions.extend(pred.tolist())
            actuals.extend(test["target"].to_numpy().tolist())
            folds.append(
                {
                    "train_start": str(train.index[0].date()),
                    "train_end": str(train.index[-1].date()),
                    "test_start": str(test.index[0].date()),
                    "test_end": str(test.index[-1].date()),
                    "train_n": len(train),
                    "test_n": len(test),
                    "purge_weeks": purge_weeks,
                }
            )
            test_start = test_end

        pred_a = np.asarray(predictions, dtype=float)
        actual_a = np.asarray(actuals, dtype=float)
        corr = np.corrcoef(pred_a, actual_a)[0, 1] if len(pred_a) > 2 else np.nan
        directional = np.mean(np.sign(pred_a) == np.sign(actual_a)) if len(pred_a) else np.nan
        mse = np.mean((pred_a - actual_a) ** 2) if len(pred_a) else np.nan
        results[factor] = {
            "folds": folds,
            "oos_n": int(len(actual_a)),
            "oos_correlation": _finite(corr, 4),
            "oos_directional_accuracy": _finite(directional, 4),
            "oos_mse": _finite(mse, 8),
        }

    return {
        "schema": "global_liquidity_transmission.factor_comparison.v1",
        "authority": "research_only_no_promotion",
        "asset": "BTC-USD",
        "target": f"forward_{horizon_weeks}w_log_return",
        "frequency": "W-FRI",
        "initial_train_weeks": initial_train_weeks,
        "test_weeks": test_weeks,
        "purge_weeks": purge_weeks,
        "caveat": "Single frozen asset/horizon comparison; no multiple-testing claim and no trading authority.",
        "factors": results,
    }
