"""Pure, deterministic and coverage-aligned 13F company context views.

The older ``engine.smart_money.compute_smart_money`` surface is intentionally
not consumed here.  Its latest-snapshot shortcut can mix an early filed quarter
with the prior quarter.  This projection pins a single legally available
quarter, requires exact paths for that quarter and its immediate predecessor,
and exposes the reporting set on every view.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from typing import Any, Mapping

import pandas as pd
import yaml

from engine.company_intelligence.contracts import ContractError, parse_date, safe_ticker, validate_context as validate_company_context, validate_manifest as validate_company_manifest
from engine.company_theme_exposure.views import load_company_generation
from engine.smart_money import _norm, diff_snapshots, issuer_key, resolve_tickers

from .contracts import (
    AUTHORITY, CONTEXT_SCHEMA, MANIFEST_SCHEMA, bytes_sha256, canonical_json_bytes,
    canonical_json_sha256, company_filename, validate_context, validate_manifest,
)


FILING_WINDOW_DAYS = 45
TREND_VALUE_CHANGE_PCT = 15.0


def _as_date(value: object) -> date:
    return parse_date(value, field="as_of")


def _quarter_end_on_or_before(value: date) -> date:
    """The latest standard calendar quarter-end no later than ``value``."""
    candidates = (date(value.year, 3, 31), date(value.year, 6, 30), date(value.year, 9, 30), date(value.year, 12, 31))
    return max(candidate for candidate in candidates if candidate <= value) if any(candidate <= value for candidate in candidates) else date(value.year - 1, 12, 31)


def _previous_quarter(value: date) -> date:
    if value.month == 3:
        return date(value.year - 1, 12, 31)
    if value.month == 6:
        return date(value.year, 3, 31)
    if value.month == 9:
        return date(value.year, 6, 30)
    if value.month == 12:
        return date(value.year, 9, 30)
    raise ContractError(f"not a quarter end: {value.isoformat()}")


def aligned_consensus_period(as_of: str | date) -> tuple[str, str, str]:
    """Return current/prior exact snapshot periods after the 45-day 13F window.

    ``filing_window_closed_on`` is a deterministic eligibility boundary, not an
    observation.  Actual public availability elsewhere always comes from the
    filing-date column in the raw snapshot.
    """
    build_date = _as_date(as_of)
    quarter = _quarter_end_on_or_before(build_date)
    while quarter + timedelta(days=FILING_WINDOW_DAYS) > build_date:
        quarter = _previous_quarter(quarter)
    return quarter.isoformat(), _previous_quarter(quarter).isoformat(), (quarter + timedelta(days=FILING_WINDOW_DAYS)).isoformat()


def _load_manager_config(path: Path) -> dict[str, Mapping[str, Any]]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ContractError(f"smart money config unavailable: {path}: {exc}") from exc
    root = payload.get("smart_money") if isinstance(payload, Mapping) else None
    funds = root.get("funds") if isinstance(root, Mapping) else None
    if not isinstance(funds, Mapping) or not funds:
        raise ContractError("smart money funds config invalid")
    cleaned: dict[str, Mapping[str, Any]] = {}
    for slug, spec in funds.items():
        if not isinstance(slug, str) or not slug or not isinstance(spec, Mapping):
            raise ContractError("smart money manager config invalid")
        name, style = spec.get("name"), spec.get("style")
        if not isinstance(name, str) or not name or not isinstance(style, str) or not style:
            raise ContractError(f"smart money manager metadata invalid: {slug}")
        cleaned[slug] = spec
    return cleaned


def _membership_name_map(path: Path) -> dict[str, str]:
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        raise ContractError(f"universe membership unavailable: {path}: {exc}") from exc
    if not {"ticker", "name"} <= set(frame.columns):
        raise ContractError("universe membership schema invalid")
    if "active" in frame.columns:
        frame = frame[frame["active"].astype(bool)]
    result: dict[str, str] = {}
    for row in frame[["ticker", "name"]].itertuples(index=False):
        try:
            ticker = safe_ticker(row.ticker)
        except ContractError:
            continue
        normalized = _norm(str(row.name or ""))
        if normalized:
            result.setdefault(normalized, ticker)
    if not result:
        raise ContractError("universe membership has no resolvable company names")
    return result


def _snapshot_path(root: Path, manager: str, period: str) -> Path:
    return root / manager / f"{period}.parquet"


def _read_snapshot(root: Path, manager: str, period: str) -> tuple[pd.DataFrame, dict[str, Any]] | None:
    path = _snapshot_path(root, manager, period)
    if not path.is_file():
        return None
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        raise ContractError(f"13F snapshot unreadable: {path}: {exc}") from exc
    expected = {"cusip", "issuer", "sh_type", "shares", "value_usd", "period_end", "filing_date"}
    if frame.empty or not expected <= set(frame.columns):
        raise ContractError(f"13F snapshot schema invalid: {path}")
    period_values = {str(value)[:10] for value in frame["period_end"].dropna().tolist()}
    dates = {str(value)[:10] for value in frame["filing_date"].dropna().tolist()}
    if period_values != {period} or len(dates) != 1:
        raise ContractError(f"13F snapshot period or filing date inconsistent: {path}")
    filing_date = next(iter(dates))
    parse_date(filing_date, field="filing_date")
    return frame, {
        "path": path.relative_to(Path.cwd()).as_posix() if path.is_relative_to(Path.cwd()) else f"data/smart_money/{manager}/{period}.parquet",
        "sha256": bytes_sha256(path),
        "bytes": path.stat().st_size,
        "period_end": period,
        "filing_date": filing_date,
    }


def _snapshot_index(snapshot_root: Path, active_managers: list[str]) -> tuple[dict[str, list[dict[str, Any]]], str, int]:
    """Hash the entire exact raw snapshot catalogue (not only a lucky ticker)."""
    index: dict[str, list[dict[str, Any]]] = {}
    total = 0
    for manager in active_managers:
        records: list[dict[str, Any]] = []
        directory = snapshot_root / manager
        if directory.is_dir():
            for path in sorted(directory.glob("*.parquet")):
                try:
                    period = path.stem
                    parse_date(period, field="snapshot period")
                    loaded = _read_snapshot(snapshot_root, manager, period)
                    if loaded is not None:
                        _frame, receipt = loaded
                        records.append({key: receipt[key] for key in ("path", "sha256", "bytes", "period_end", "filing_date")})
                except ContractError:
                    raise
        index[manager] = records
        total += len(records)
    return index, canonical_json_sha256(index), total


def _manager_grade(spec: Mapping[str, Any]) -> str:
    """Static declared qualifier, never a predicted or backtested score."""
    value = spec.get("signal_quality")
    return str(value) if isinstance(value, str) and value else "not_graded"


def _resolve_diff(
    current: pd.DataFrame,
    previous: pd.DataFrame | None,
    name_map: Mapping[str, str],
) -> tuple[pd.DataFrame, int, int]:
    """Resolve and collapse one manager's exact two-quarter delta by issuer key."""
    diff = diff_snapshots(previous, current)
    if diff.empty:
        return diff, 0, 0
    resolved = resolve_tickers(diff, dict(name_map), {})
    unresolved = int(resolved["ticker"].isna().sum())
    resolved = resolved[resolved["ticker"].notna()].copy()
    if resolved.empty:
        return resolved, 0, unresolved
    resolved["canonical_ticker"] = [issuer_key(str(ticker), str(cusip)) for ticker, cusip in zip(resolved["ticker"], resolved["cusip"])]
    # Do not double count two listed classes of the same issuer in one manager.
    # The largest current-dollar lot determines the descriptive action; values,
    # shares and book weights remain sums across the collapsed issuer.
    order = resolved.sort_values(["value_usd", "canonical_ticker"], ascending=[False, True])
    collapsed = order.groupby("canonical_ticker", as_index=False).agg(
        action=("action", "first"), pct_portfolio=("pct_portfolio", "sum"), value_usd=("value_usd", "sum"),
        shares=("shares", "sum"), shares_change_pct=("shares_change_pct", "first"), issuer=("issuer", "first"),
    )
    return collapsed, int(len(collapsed)), unresolved


def _period_aggregate(
    snapshots: Mapping[str, tuple[pd.DataFrame, dict[str, Any]]],
    active_managers: list[str],
    name_map: Mapping[str, str],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Aggregate one exact historical period without composing different sets."""
    result: dict[str, dict[str, Any]] = {}
    unresolved = 0
    for manager, loaded in snapshots.items():
        frame, _receipt = loaded
        equity = frame[frame["sh_type"].astype(str).eq("SH")].copy()
        if equity.empty:
            continue
        grouped = equity.groupby("cusip", as_index=False).agg(issuer=("issuer", "first"), value_usd=("value_usd", "sum"))
        resolved = resolve_tickers(grouped, dict(name_map), {})
        unresolved += int(resolved["ticker"].isna().sum())
        resolved = resolved[resolved["ticker"].notna()].copy()
        if resolved.empty:
            continue
        resolved["canonical_ticker"] = [issuer_key(str(ticker), str(cusip)) for ticker, cusip in zip(resolved["ticker"], resolved["cusip"])]
        per = resolved.groupby("canonical_ticker", as_index=False).agg(value_usd=("value_usd", "sum"))
        for row in per.itertuples(index=False):
            slot = result.setdefault(str(row.canonical_ticker), {"holder_count": 0, "total_value_usd": 0.0})
            slot["holder_count"] += 1
            slot["total_value_usd"] += float(row.value_usd)
    reports = len(snapshots)
    available = max((str(receipt["filing_date"]) for _frame, receipt in snapshots.values()), default=None)
    return result, {
        "reporting_manager_count": reports,
        "missing_manager_count": len(active_managers) - reports,
        "available_on": available if reports == len(active_managers) else None,
        "unresolved_position_count": unresolved,
    }


def _trend_for_company(points: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [point for point in points if point["eligible"]]
    if not points:
        return {"status": "no_history", "direction": None, "eligible_period_count": 0, "periods": []}
    if len(eligible) < 2:
        return {"status": "insufficient_coverage", "direction": None, "eligible_period_count": len(eligible), "periods": points}
    first, last = eligible[0], eligible[-1]
    holders_delta = last["holder_count"] - first["holder_count"]
    value_change = ((last["total_value_usd"] - first["total_value_usd"]) / first["total_value_usd"] * 100.0) if first["total_value_usd"] else None
    if holders_delta > 0 or (holders_delta == 0 and value_change is not None and value_change > TREND_VALUE_CHANGE_PCT):
        direction = "accumulating"
    elif holders_delta < 0 or (holders_delta == 0 and value_change is not None and value_change < -TREND_VALUE_CHANGE_PCT):
        direction = "distributing"
    else:
        direction = "stable"
    return {"status": "available", "direction": direction, "eligible_period_count": len(eligible), "periods": points}


def _history_periods(snapshot_index: Mapping[str, list[Mapping[str, Any]]], consensus_period: str) -> list[str]:
    return sorted({str(record["period_end"]) for records in snapshot_index.values() for record in records if str(record["period_end"]) <= consensus_period})[-12:]


def build_bundle(
    contexts: Mapping[str, Mapping[str, Any]],
    *,
    company_manifest: Mapping[str, Any],
    smart_money_config: Mapping[str, Any],
    smart_money_config_sha256: str,
    share_class_equivalence_sha256: str,
    universe_membership_sha256: str,
    snapshot_root: Path,
    universe_membership: Path,
    as_of: str | date | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Build one pinned, immutable institutional-context object per CI company."""
    validate_company_manifest(company_manifest)
    ci_generation = str(company_manifest["generation_id"])
    run_date = _as_date(as_of if as_of is not None else company_manifest["generated_at"])
    consensus_period, comparison_period, filing_window_closed_on = aligned_consensus_period(run_date)
    managers = {slug: spec for slug, spec in smart_money_config.items()}
    active_managers = sorted(slug for slug, spec in managers.items() if str(spec.get("status") or "") != "closed")
    closed_count = len(managers) - len(active_managers)
    if not active_managers:
        raise ContractError("all smart money managers are closed")
    name_map = _membership_name_map(universe_membership)
    snapshot_index, snapshot_index_sha256, snapshot_count = _snapshot_index(snapshot_root, active_managers)

    current: dict[str, tuple[pd.DataFrame, dict[str, Any]]] = {}
    previous: dict[str, tuple[pd.DataFrame, dict[str, Any]]] = {}
    for manager in active_managers:
        now = _read_snapshot(snapshot_root, manager, consensus_period)
        prior = _read_snapshot(snapshot_root, manager, comparison_period)
        if now is not None:
            current[manager] = now
        if prior is not None:
            previous[manager] = prior
    current_missing = len(active_managers) - len(current)
    previous_missing = len(active_managers) - len(previous)
    current_latest_filing = max((receipt["filing_date"] for _frame, receipt in current.values()), default=None)
    consensus_available = current_latest_filing if current_missing == 0 else None

    # Build exact coverage-aligned historical aggregates once, then project them
    # into every company object (including companies no manager currently holds).
    historical_by_ticker: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    history_meta: dict[str, dict[str, Any]] = {}
    history_unresolved = 0
    for period in _history_periods(snapshot_index, consensus_period):
        period_snaps: dict[str, tuple[pd.DataFrame, dict[str, Any]]] = {}
        for manager in active_managers:
            loaded = _read_snapshot(snapshot_root, manager, period)
            if loaded is not None:
                period_snaps[manager] = loaded
        aggregate, meta = _period_aggregate(period_snaps, active_managers, name_map)
        history_meta[period] = meta
        history_unresolved += int(meta["unresolved_position_count"])
        for ticker, values in aggregate.items():
            historical_by_ticker[ticker][period] = values

    positions_by_ticker: dict[str, list[dict[str, Any]]] = defaultdict(list)
    current_resolved = current_unresolved = 0
    for manager in active_managers:
        loaded = current.get(manager)
        if loaded is None:
            continue
        frame, receipt = loaded
        prior = previous.get(manager)
        # A current reporting manager with no exact previous snapshot is a
        # holder observation, not a guessed "new" position.
        collapsed, resolved_count, unresolved_count = _resolve_diff(frame, prior[0] if prior is not None else None, name_map)
        current_resolved += resolved_count
        current_unresolved += unresolved_count
        if collapsed.empty:
            continue
        for row in collapsed.itertuples(index=False):
            action = str(row.action) if prior is not None else "unavailable"
            value = float(row.value_usd)
            is_current_holder = action != "exit"
            record = {
                "manager": manager,
                "manager_name": str(managers[manager]["name"]),
                "manager_style": str(managers[manager]["style"]),
                "manager_grade": _manager_grade(managers[manager]),
                "action": action,
                "is_current_holder": is_current_holder,
                "value_usd": round(value, 2),
                "book_weight_pct": round(float(row.pct_portfolio), 4),
                "shares": round(float(row.shares), 4),
                "shares_change_pct": None if pd.isna(row.shares_change_pct) else round(float(row.shares_change_pct), 4),
                "period_end": consensus_period,
                "filing_date": str(receipt["filing_date"]),
                "snapshot": {key: receipt[key] for key in ("path", "sha256", "bytes")},
            }
            positions_by_ticker[str(row.canonical_ticker)].append(record)

    common_coverage = {
        "configured_manager_count": len(managers),
        "active_manager_count": len(active_managers),
        "closed_manager_count": closed_count,
        "reporting_manager_count": len(current),
        "missing_manager_count": current_missing,
        "comparison_reporting_manager_count": len(previous),
        "comparison_missing_manager_count": previous_missing,
        "resolved_position_count": current_resolved,
        "unresolved_position_count": current_unresolved,
    }
    all_contexts: dict[str, dict[str, Any]] = {}
    manifest_warnings: set[str] = set()
    trend_incomplete_any = False
    for ticker in sorted(contexts):
        source_context = contexts[ticker]
        validate_company_context(source_context)
        if safe_ticker(ticker) != safe_ticker(source_context["company"]["ticker"]) or source_context["generation_id"] != ci_generation:
            raise ContractError("company intelligence context pin mismatch")
        latest = source_context.get("latest_event")
        # A company dossier may use the non-canonical public share class (GOOG)
        # while 13F aggregation correctly collapses it onto a canonical issuer
        # key (GOOGL).  Expose the same one-manager-one-position observation to
        # either dossier; do not create a second economic holder count.
        canonical_ticker = issuer_key(ticker, None)
        listed_positions = sorted(positions_by_ticker.get(canonical_ticker, positions_by_ticker.get(ticker, [])), key=lambda value: (value["action"], value["manager"]))
        point_rows: list[dict[str, Any]] = []
        for period in sorted(history_meta):
            meta = history_meta[period]
            aggregate = historical_by_ticker.get(canonical_ticker, historical_by_ticker.get(ticker, {})).get(period, {"holder_count": 0, "total_value_usd": 0.0})
            point_rows.append({
                "period_end": period,
                "available_on": meta["available_on"],
                "reporting_manager_count": meta["reporting_manager_count"],
                "missing_manager_count": meta["missing_manager_count"],
                "holder_count": aggregate["holder_count"],
                "total_value_usd": round(float(aggregate["total_value_usd"]), 2),
                "eligible": bool(meta["missing_manager_count"] == 0 and meta["available_on"] is not None),
            })
        trend = _trend_for_company(point_rows)
        trend_incomplete_any = trend_incomplete_any or trend["status"] == "insufficient_coverage"
        current_positions = [value for value in listed_positions if value["is_current_holder"]]
        values = [float(value["value_usd"]) for value in current_positions]
        total_value = sum(values)
        weights = [float(value["book_weight_pct"]) for value in current_positions]
        consensus = {
            "current_holder_count": len(current_positions),
            "buyer_count": sum(value["action"] in {"new", "add"} for value in current_positions),
            "trimmer_count": sum(value["action"] == "trim" for value in current_positions),
            "exit_count": sum(value["action"] == "exit" for value in listed_positions),
            "unknown_move_count": sum(value["action"] == "unavailable" for value in current_positions),
            "total_value_usd": round(total_value, 2),
            "ownership_hhi": round(sum((value / total_value) ** 2 for value in values), 6) if total_value else None,
            "max_book_weight_pct": round(max(weights), 4) if weights else None,
            "avg_book_weight_pct": round(sum(weights) / len(weights), 4) if weights else None,
        }
        warnings: list[str] = []
        if current_missing:
            warnings.append("current_snapshots_missing")
        if previous_missing:
            warnings.append("comparison_snapshots_missing")
        if current_unresolved:
            warnings.append("resolution_partial")
        if trend["status"] == "insufficient_coverage":
            warnings.append("history_coverage_incomplete")
        warnings.sort()
        status = "no_covered_holder" if not current_positions else ("partial" if warnings else "ready")
        all_contexts[ticker] = {
            "schema": CONTEXT_SCHEMA,
            "authority": AUTHORITY,
            "generated_at": str(company_manifest["generated_at"]),
            "generation_id": "0" * 24,
            "status": status,
            "company": {"ticker": ticker},
            "company_intelligence": {
                "generation_id": ci_generation,
                "context_sha256": canonical_json_sha256(source_context),
                "latest_event_id": latest.get("event_id") if isinstance(latest, Mapping) else None,
                "latest_event_call_date": latest.get("call_date") if isinstance(latest, Mapping) else None,
            },
            "period": {
                "build_as_of": run_date.isoformat(),
                "consensus_period": consensus_period,
                "comparison_period": comparison_period,
                "filing_window_closed_on": filing_window_closed_on,
                "consensus_available_on": consensus_available,
                "latest_reporting_filing_date": current_latest_filing,
            },
            "coverage": dict(common_coverage),
            "positions": listed_positions,
            "consensus": consensus,
            "trend": trend,
            "warnings": warnings,
        }
        manifest_warnings.update(warnings)
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "generation_id": "0" * 24,
        "generated_at": str(company_manifest["generated_at"]),
        "company_count": len(all_contexts),
        "covered_company_count": sum(bool(item["consensus"]["current_holder_count"]) for item in all_contexts.values()),
        "position_record_count": sum(len(item["positions"]) for item in all_contexts.values()),
        "consensus_period": consensus_period,
        "coverage": common_coverage,
        "source": {
            "company_intelligence": {"generation_id": ci_generation, "sha256": canonical_json_sha256(company_manifest)},
            "smart_money_config": {"sha256": smart_money_config_sha256},
            "share_class_equivalence": {"sha256": share_class_equivalence_sha256},
            "universe_membership": {"sha256": universe_membership_sha256},
            "snapshot_index": {"sha256": snapshot_index_sha256, "snapshot_count": snapshot_count, "manager_count": len(active_managers)},
            "builder": CONTEXT_SCHEMA,
        },
        "files": {},
        "status": "empty" if not all_contexts else ("partial" if manifest_warnings else "ready"),
        # The manifest must never claim a clean tree when every per-company
        # trend correctly declined to assert a direction on incomplete history.
        "warnings": sorted(manifest_warnings),
    }
    generation_id = derive_generation_id(all_contexts, manifest)
    manifest["generation_id"] = generation_id
    for context in all_contexts.values():
        context["generation_id"] = generation_id
        validate_context(context)
    validate_manifest(manifest, allow_unmaterialized_files=True)
    return all_contexts, manifest


def derive_generation_id(contexts: Mapping[str, Mapping[str, Any]], manifest: Mapping[str, Any]) -> str:
    normalized: dict[str, Any] = {}
    for ticker in sorted(contexts):
        value = json.loads(json.dumps(contexts[ticker], ensure_ascii=False))
        value["generation_id"] = "0" * 24
        normalized[ticker] = value
    marker = json.loads(json.dumps(manifest, ensure_ascii=False))
    marker["generation_id"] = "0" * 24
    marker["files"] = {}
    return canonical_json_sha256({"contexts": normalized, "manifest": marker})[:24]


def _atomic_write(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        handle.write(body)
        temporary = Path(handle.name)
    temporary.replace(path)


def write_generation(out_dir: Path, contexts: Mapping[str, Mapping[str, Any]], manifest: Mapping[str, Any]) -> Path:
    validate_manifest(manifest, allow_unmaterialized_files=True)
    for ticker, context in contexts.items():
        validate_context(context)
        if safe_ticker(ticker) != safe_ticker(context["company"]["ticker"]):
            raise ContractError("context filename ticker does not match payload")
    generation_id = derive_generation_id(contexts, manifest)
    if generation_id != manifest["generation_id"]:
        raise ContractError("generation_id does not bind final context/manifest content")
    generation = out_dir / "generations" / generation_id
    receipts: dict[str, dict[str, Any]] = {}
    for ticker in sorted(contexts):
        context = contexts[ticker]
        if context["generation_id"] != generation_id:
            raise ContractError("context generation_id does not bind final content")
        body = canonical_json_bytes(context)
        path = generation / company_filename(ticker)
        if path.exists() and path.read_bytes() != body:
            raise ContractError(f"immutable generation collision: {path}")
        if not path.exists():
            _atomic_write(path, body)
        receipts[company_filename(ticker)] = {"sha256": sha256(body).hexdigest(), "bytes": len(body)}
    final = dict(manifest)
    final["files"] = receipts
    validate_manifest(final)
    body = canonical_json_bytes(final)
    immutable = generation / "manifest.json"
    if immutable.exists() and immutable.read_bytes() != body:
        raise ContractError(f"immutable generation collision: {immutable}")
    if not immutable.exists():
        _atomic_write(immutable, body)
    _atomic_write(out_dir / "manifest.json", body)
    return generation


def load_config(path: Path) -> tuple[dict[str, Mapping[str, Any]], str]:
    managers = _load_manager_config(path)
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ContractError(f"smart money config unavailable: {path}: {exc}") from exc
    return managers, canonical_json_sha256(payload)


def load_company_intelligence(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    return load_company_generation(root)
