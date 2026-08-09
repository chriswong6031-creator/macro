"""Build the display-only Options Prophet shadow projection.

This is intentionally a projection, not a new signal engine.  It re-publishes
the existing Flow Leaders ordering, exposes only actual Pick Lab fires as
opportunities, and carries the existing calibration gates without inventing a
score, probability, direction, contract, or exit target.

Inputs
------
site/flowleaders/leaders.json
site/labdata/pick_lab.json
data/options_flow/signing_gate.json
data/options_entry/gate.json
data/options_entry/coverage.json
data/options_dislocation/validation_gate.json
optional Konseki Market Memory context (`konseki.market_memory/v1`)

Output
------
site/options_prophet/index.json  (schema options.prophet_shadow/v1)

Usage
-----
    python -m scripts.build_options_prophet
"""
from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "options.prophet_shadow/v1"
AUTHORITY = "display_only"
FLOW_BOOKS = (
    ("plab_flow_leader", "flow_leader"),
    ("plab_flow_washout", "flow_washout"),
)
BAR_SIGNING_SOURCES = frozenset({"bar", "minute_bar", "minute_tick"})
KONSEKI_SCHEMA = "konseki.market_memory/v1"
OUTCOME_HORIZONS = ("1h", "eod", "1d", "3d", "5d", "10d", "expiry")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> tuple[dict[str, Any], str | None]:
    """Read an object-valued JSON file, returning an explicit failure reason."""
    if not path.exists():
        return {}, "missing"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, "unreadable"
    if not isinstance(value, Mapping):
        return {}, "root_not_object"
    return dict(value), None


def _as_bool(value: Any) -> bool:
    return value is True


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _count(value: Any) -> int | None:
    """Return a governed count only when it is a nonnegative integer."""
    number = _number(value)
    if number is None or number < 0 or int(number) != number:
        return None
    return int(number)


def _json_safe(value: Any) -> Any:
    """Recursively replace non-finite numbers before crossing the JSON boundary.

    Python's json encoder accepts NaN by default, while browser JSON.parse rejects
    it. Upstream research artifacts can contain permissively decoded NaN tokens, so
    the public projection must normalize them to an honest null and then serialize
    with ``allow_nan=False``.
    """
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _session_date(value: Any) -> str | None:
    """Normalize an ISO-like value to a valid YYYY-MM-DD session date."""
    if not isinstance(value, str) or len(value) < 10:
        return None
    candidate = value[:10]
    try:
        datetime.strptime(candidate, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return candidate


def _iso_timestamp(value: Any) -> str | None:
    """Return an exact UTC timestamp only when the source supplied a zone."""
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _timestamp_lte(left: str | None, right: str | None) -> bool:
    """Return true only for two exact UTC clocks ordered left <= right."""
    if left is None or right is None:
        return False
    return datetime.fromisoformat(left.replace("Z", "+00:00")) <= datetime.fromisoformat(
        right.replace("Z", "+00:00")
    )


def _execution_envelope() -> dict[str, Any]:
    """Reserve the executable-call contract without fabricating any leg or level."""
    return {
        "status": "withheld",
        "executable": False,
        "contract": {
            "occ_symbol": None,
            "right": None,
            "strike": None,
            "expiry": None,
        },
        "entry": {"type": None, "price": None, "quote_at": None},
        "stop": None,
        "targets": [],
        "take_profit_management": None,
        "reason": (
            "No point-in-time contract selection, executable quote/fill, or managed "
            "exit lifecycle is attached."
        ),
    }


def _signing_read(signing_gate: Mapping[str, Any]) -> dict[str, Any]:
    tape = signing_gate.get("thetadata_tape")
    tape = tape if isinstance(tape, Mapping) else {}
    bar_reliable = _as_bool(signing_gate.get("direction_reliable"))
    tape_reliable = (
        _as_bool(tape.get("direction_reliable_tape"))
        and _as_bool(tape.get("production_ready"))
    )
    payload = {
        "bar_sources_reliable": bar_reliable,
        "tape_sources_reliable": tape_reliable,
        "bar_net_sign_recovery": _number(signing_gate.get("net_sign_recovery")),
        "bar_required": _number(signing_gate.get("bar")),
        "tape_sessions": _number(tape.get("sessions_n")),
        "tape_sessions_required": _number(
            (tape.get("production_ready_criteria") or {}).get("sessions_ok_needed")
            if isinstance(tape.get("production_ready_criteria"), Mapping)
            else None
        ),
        "tape_suspend_reason": tape.get("suspend_reason"),
    }
    return _json_safe(payload)


def _source_direction_reliable(source: Any, signing: Mapping[str, Any]) -> bool:
    normalized = str(source or "").strip().lower()
    if normalized == "tape":
        return _as_bool(signing.get("tape_sources_reliable"))
    if normalized in BAR_SIGNING_SOURCES:
        return _as_bool(signing.get("bar_sources_reliable"))
    return False


def _opportunities(
    pick_lab: Mapping[str, Any],
    signing: Mapping[str, Any],
    *,
    projection_available_at: str,
) -> list[dict[str, Any]]:
    """Project actual Pick Lab fires only; never promote a watch row to a fire."""
    books = pick_lab.get("books")
    books = books if isinstance(books, Mapping) else {}
    source_available_at = _iso_timestamp(pick_lab.get("built_at"))
    result: list[dict[str, Any]] = []
    for engine_id, lane in FLOW_BOOKS:
        book = books.get(engine_id)
        book = book if isinstance(book, Mapping) else {}
        picks = book.get("picks_today")
        if not isinstance(picks, list):
            continue
        ordered = sorted(
            (pick for pick in picks if isinstance(pick, Mapping)),
            key=lambda pick: (
                pick.get("rank") is None,
                pick.get("rank") if isinstance(pick.get("rank"), int) else 10**9,
                str(pick.get("ticker") or ""),
            ),
        )
        for pick in ordered:
            symbol = str(pick.get("ticker") or "").strip().upper()
            if not symbol:
                continue
            fire_date = _session_date(pick.get("fire_date") or pick_lab.get("as_of"))
            pick_session = _session_date(pick_lab.get("as_of"))
            if not fire_date or fire_date != pick_session:
                continue
            features = pick.get("features")
            features = features if isinstance(features, Mapping) else {}
            signing_source = features.get("signing_source")
            decision_at = _iso_timestamp(pick.get("decision_at"))
            available_at = _iso_timestamp(pick.get("available_at")) or source_available_at
            if available_at is None:
                continue
            if not _timestamp_lte(available_at, projection_available_at):
                continue
            if decision_at is not None and not _timestamp_lte(
                decision_at, available_at
            ):
                continue
            result.append(
                {
                    "symbol": symbol,
                    "lane": lane,
                    "engine_id": engine_id,
                    "source_rank": pick.get("rank"),
                    "fire_date": fire_date,
                    # Never synthesize a close time from a date. The current Pick
                    # Lab contract supplies an exact artifact availability time but
                    # not an exact decision timestamp.
                    "decision_at": decision_at,
                    "available_at": available_at,
                    "sector": pick.get("sector"),
                    "close_at_fire": pick.get("close_at_fire"),
                    "why": _string_list(pick.get("why")),
                    "signing_source": signing_source,
                    "authority": AUTHORITY,
                    # A trustworthy signing source is still not an originated,
                    # calibrated directional opportunity. Keep these concepts split.
                    "source_signing_reliable": _source_direction_reliable(
                        signing_source, signing
                    ),
                    "direction_reliable": False,
                    "execution": _execution_envelope(),
                }
            )
    return result


def _watchlist(
    flow_leaders: Mapping[str, Any],
    signing: Mapping[str, Any],
    *,
    projection_available_at: str,
) -> list[dict[str, Any]]:
    """Return the source-ordered Board A then Board B stable union.

    A symbol present on both boards is folded into one row, but both source
    memberships and positions are retained.  No value is used to re-rank rows.
    """
    rows_by_symbol: dict[str, dict[str, Any]] = {}
    ordered_symbols: list[str] = []
    source_available_at = _iso_timestamp(flow_leaders.get("as_of"))
    if not _timestamp_lte(source_available_at, projection_available_at):
        return []
    board_specs = (
        ("board_a", "flow_leader", "fire_a"),
        ("board_b", "flow_washout", "fire_b"),
    )
    observation_keys = (
        "recurrence_count",
        "net_prem_norm_abs",
        "flow_z",
        "days_since_inflection",
        "oi_confirmed",
        "zerodte_dominated",
        "gamma_regime",
        "K_a",
        "n_avail_a",
        "K_b",
        "n_avail_b",
    )

    for board_name, lane, fire_field in board_specs:
        board = flow_leaders.get(board_name)
        if not isinstance(board, list):
            continue
        for source_position, raw in enumerate(board, 1):
            if not isinstance(raw, Mapping):
                continue
            symbol = str(raw.get("ticker") or "").strip().upper()
            if not symbol:
                continue
            row = rows_by_symbol.get(symbol)
            if row is None:
                signing_source = raw.get("signing_source")
                row = {
                    "order": len(ordered_symbols) + 1,
                    "symbol": symbol,
                    "decision_at": None,
                    "available_at": source_available_at,
                    "lanes": [],
                    "source_positions": {"board_a": None, "board_b": None},
                    "fire_lanes": [],
                    "signing_source": signing_source,
                    "source_signing_reliable": _source_direction_reliable(
                        signing_source, signing
                    ),
                    "direction_reliable": False,
                    "observations": {
                        key: raw.get(key) for key in observation_keys
                    },
                    "de_escalation": dict(raw.get("de_escalation") or {})
                    if isinstance(raw.get("de_escalation"), Mapping)
                    else {},
                }
                rows_by_symbol[symbol] = row
                ordered_symbols.append(symbol)
            row["lanes"].append(lane)
            row["source_positions"][board_name] = source_position
            if raw.get(fire_field) is True:
                row["fire_lanes"].append(lane)

    return [rows_by_symbol[symbol] for symbol in ordered_symbols]


def _horizon(row: Mapping[str, Any], prefix: str) -> dict[str, Any]:
    return {
        "n": _count(row.get(f"{prefix}_n")),
        "win_rate_absolute": row.get(f"{prefix}_wr_abs"),
        "win_rate_excess_spy": row.get(f"{prefix}_wr_exc"),
        "median_excess_spy": row.get(f"{prefix}_med_exc"),
        "median_mfe": row.get(f"{prefix}_med_mfe"),
        "median_abs_mae": row.get(f"{prefix}_med_abs_mae"),
        "asymmetry": row.get(f"{prefix}_asym"),
    }


def _path(row: Mapping[str, Any], prefix: str) -> dict[str, Any]:
    return {
        "n": _count(row.get(f"{prefix}_n")),
        "median_mfe": row.get(f"{prefix}_med_mfe"),
        "median_abs_mae": row.get(f"{prefix}_med_abs_mae"),
        "asymmetry": row.get(f"{prefix}_asym"),
        "median_sessions_to_mfe": row.get(f"{prefix}_med_t_mfe"),
        "median_sessions_to_mae": row.get(f"{prefix}_med_t_mae"),
        "pct_mae_first": row.get(f"{prefix}_pct_mae_first"),
        "median_underwater_sessions": row.get(f"{prefix}_med_underwater"),
    }


def _forward_ledgers(pick_lab: Mapping[str, Any]) -> dict[str, Any]:
    scoreboard = pick_lab.get("scoreboard")
    scoreboard = scoreboard if isinstance(scoreboard, list) else []
    by_id = {
        str(row.get("engine_id")): row
        for row in scoreboard
        if isinstance(row, Mapping) and row.get("engine_id")
    }
    books: list[dict[str, Any]] = []
    for engine_id, _lane in FLOW_BOOKS:
        row = by_id.get(engine_id)
        if not isinstance(row, Mapping):
            continue
        n_fires = _count(row.get("n_fires"))
        n_open = _count(row.get("n_open"))
        n_dates = _count(row.get("n_distinct_fire_dates"))
        horizons = {
            name: _horizon(row, name) for name in ("h5", "h10", "h21", "h63")
        }
        paths = {
            name: _path(row, name) for name in ("path25", "path63")
        }
        required_counts = [
            n_fires,
            n_open,
            n_dates,
            *(cell["n"] for cell in horizons.values()),
            *(cell["n"] for cell in paths.values()),
        ]
        if any(value is None for value in required_counts):
            continue
        books.append(
            {
                "engine_id": engine_id,
                "name": row.get("name_en"),
                "name_en": row.get("name_en"),
                "name_zh": row.get("name_zh"),
                "status": row.get("status"),
                # Upstream metadata is evidence, never an authority grant. This
                # projection hard-fences every relayed book at display-only.
                "authority": AUTHORITY,
                "ruler": row.get("ruler"),
                "n_fires": n_fires,
                "n_open": n_open,
                "n_distinct_fire_dates": n_dates,
                "months_span": row.get("months_span"),
                "horizons": horizons,
                "paths": paths,
            }
        )
    return {
        "source_artifact": "site/labdata/pick_lab.json",
        "books": books,
        "incremental_options_attribution": {
            "available": False,
            "reason": (
                "The flow books grade options-originated fires, but no paired "
                "macro_base versus macro_plus_options attribution ledger exists yet."
            ),
        },
    }


def _accrual_contract(
    *,
    opportunities: list[dict[str, Any]],
    ledgers: Mapping[str, Any],
) -> dict[str, Any]:
    """Keep immutable fire accrual separate from fire-by-horizon outcomes."""
    raw_books = ledgers.get("books")
    books = raw_books if isinstance(raw_books, list) else []
    event_books = []
    event_counts_valid = True
    seen_event_engines: set[str] = set()
    allowed_engines = {engine_id for engine_id, _lane in FLOW_BOOKS}
    for raw in books:
        if not isinstance(raw, Mapping):
            event_counts_valid = False
            continue
        engine_id = raw.get("engine_id")
        n_fires = _count(raw.get("n_fires"))
        n_open = _count(raw.get("n_open"))
        n_dates = _count(raw.get("n_distinct_fire_dates"))
        if (
            engine_id not in allowed_engines
            or engine_id in seen_event_engines
            or any(value is None for value in (n_fires, n_open, n_dates))
        ):
            event_counts_valid = False
            continue
        seen_event_engines.add(engine_id)
        event_books.append(
            {
                "engine_id": engine_id,
                "n_fires": n_fires,
                "n_open": n_open,
                "n_distinct_fire_dates": n_dates,
            }
        )
    if (
        not event_counts_valid
        or len(books) != len(FLOW_BOOKS)
        or len(event_books) != len(books)
    ):
        event_books = []

    def outcome_horizon(horizon: str) -> dict[str, Any]:
        source_key = {"5d": "h5", "10d": "h10"}.get(horizon)
        if source_key is None:
            return {
                "instrumented": False,
                "status": "not_instrumented",
                "authority": "none",
                "books": [],
                "reason": (
                    "No immutable point-in-time outcome book exists for this horizon."
                ),
            }
        horizon_books = []
        valid_counts = True
        seen_horizon_engines: set[str] = set()
        for raw in books:
            if not isinstance(raw, Mapping):
                valid_counts = False
                continue
            horizons = raw.get("horizons")
            horizons = horizons if isinstance(horizons, Mapping) else {}
            cell = horizons.get(source_key)
            cell = cell if isinstance(cell, Mapping) else {}
            engine_id = raw.get("engine_id")
            n = _count(cell.get("n"))
            if (
                engine_id not in allowed_engines
                or engine_id in seen_horizon_engines
                or n is None
            ):
                valid_counts = False
                continue
            seen_horizon_engines.add(engine_id)
            horizon_books.append(
                {
                    "engine_id": engine_id,
                    "n": n,
                    "status": raw.get("status"),
                }
            )
        instrumented = (
            bool(horizon_books)
            and valid_counts
            and len(books) == len(FLOW_BOOKS)
            and len(horizon_books) == len(books)
        )
        if not instrumented:
            horizon_books = []
        return {
            "instrumented": instrumented,
            "status": "accruing" if instrumented else "not_instrumented",
            "authority": "descriptive_only" if instrumented else "none",
            "books": horizon_books,
            # Current Pick Lab history is session-based and predates exact
            # decision_at/available_at clocks, so it cannot be promoted as PIT.
            "pit_exact": False,
            "reason": (
                "Legacy session-horizon outcomes are accruing; exact decision and "
                "availability clocks are not yet present on the historical fires."
                if instrumented
                else (
                    "No complete governed nonnegative sample count is available for "
                    "every registered outcome book at this horizon."
                )
            ),
        }

    exact_decisions = sum(row.get("decision_at") is not None for row in opportunities)
    exact_availability = sum(row.get("available_at") is not None for row in opportunities)
    return {
        "events": {
            "unit": "immutable_options_originated_fire",
            "books": event_books,
            "published_now": len(opportunities),
            "timestamp_coverage": {
                "n_published": len(opportunities),
                "n_exact_decision_at": exact_decisions,
                "n_exact_available_at": exact_availability,
            },
            "authority": "display_only",
        },
        "outcomes": {
            "unit": "fire_x_horizon",
            "separate_from_event_accrual": True,
            "horizons": {
                horizon: outcome_horizon(horizon) for horizon in OUTCOME_HORIZONS
            },
        },
    }


def _konseki_context(
    context: Mapping[str, Any],
    *,
    projection_available_at: str,
    projection_decision_at: str | None,
) -> dict[str, Any]:
    """Project a narrow zero-authority Market Memory receipt when supplied."""
    schema_ok = context.get("schema") == KONSEKI_SCHEMA
    source_authority_ok = context.get("authority") == "context_only"
    decision_at = _iso_timestamp(context.get("decision_at"))
    available_at = _iso_timestamp(context.get("available_at"))
    memory_id_raw = context.get("memory_id")
    memory_id = (
        memory_id_raw.strip()
        if isinstance(memory_id_raw, str) and memory_id_raw.strip()
        else None
    )
    clock_order_ok = (
        _timestamp_lte(decision_at, available_at)
        and _timestamp_lte(available_at, projection_available_at)
        and (
            projection_decision_at is None
            or _timestamp_lte(available_at, projection_decision_at)
        )
    )
    connected = (
        schema_ok
        and source_authority_ok
        and memory_id is not None
        and clock_order_ok
    )
    return {
        "expected_schema": KONSEKI_SCHEMA,
        "connected": connected,
        "authority": "context_only",
        "weight": 0.0,
        "may_rank": False,
        "may_gate": False,
        "may_size": False,
        "decision_at": decision_at if connected else None,
        "available_at": available_at if connected else None,
        "receipt": {
            "memory_id": memory_id,
            "context_tags": _string_list(context.get("context_tags")),
        }
        if connected
        else None,
        "reason": (
            "A governed Market Memory receipt is connected as context only; it cannot "
            "change Options Alpha or Macro authority."
            if connected
            else "No governed Konseki Market Memory receipt is connected."
        ),
    }


def _positioning_readiness(
    *,
    context_available: bool,
    options_entry_gate: Mapping[str, Any],
    options_entry_coverage: Mapping[str, Any],
    dislocation_gate: Mapping[str, Any],
) -> dict[str, Any]:
    entry_weight = _number(options_entry_gate.get("weight"))
    entry_promoted = (
        _as_bool(options_entry_gate.get("scored"))
        and entry_weight is not None
        and entry_weight > 0
    )
    scored_primitives = dislocation_gate.get("scored_primitives")
    scored_primitives = scored_primitives if isinstance(scored_primitives, list) else []
    dislocation_promoted = (
        _as_bool(dislocation_gate.get("scored")) and bool(scored_primitives)
    )
    promotion_ready = entry_promoted or dislocation_promoted

    feature_coverage = options_entry_coverage.get("feature_coverage")
    feature_coverage = feature_coverage if isinstance(feature_coverage, Mapping) else {}
    feature_rows = feature_coverage.get("features")
    feature_rows = feature_rows if isinstance(feature_rows, list) else []
    by_feature = {
        str(row.get("feature")): row
        for row in feature_rows
        if isinstance(row, Mapping) and row.get("feature")
    }
    highlight_names = (
        "iv_rank_252",
        "iv_rank_5d_chg",
        "signed_vanna_pressure",
        "vanna_hedge_5d",
        "front7_charm_share",
        "pin_risk",
    )
    feature_highlights = []
    for name in highlight_names:
        row = by_feature.get(name)
        if not isinstance(row, Mapping):
            continue
        feature_highlights.append(
            {
                "feature": name,
                "n_nonnull": row.get("n_nonnull"),
                "n_total": row.get("n_total"),
                "share_nonnull": row.get("share_nonnull"),
            }
        )

    structural = options_entry_coverage.get("structural_nulls")
    structural = structural if isinstance(structural, Mapping) else {}
    structural_highlights = []
    for name in ("iv_rank_252", "pin_risk", "gamma_regime_constancy"):
        row = structural.get(name)
        if not isinstance(row, Mapping):
            continue
        structural_highlights.append(
            {
                "feature": name,
                "null_share": row.get("null_share"),
                "note": row.get("root_cause") or row.get("caveat") or row.get("note"),
            }
        )
    return {
        # An engine is not ready merely because its display context exists.
        "ready": promotion_ready,
        "context_available": context_available,
        "promotion_ready": promotion_ready,
        "authority": {
            "may_rank": False,
            "may_gate": False,
            "may_size": False,
            "weight": 0.0,
        },
        "evidence": {
            "options_entry": {
                "schema": options_entry_gate.get("schema"),
                "status": options_entry_gate.get("status"),
                "scored": _as_bool(options_entry_gate.get("scored")),
                "weight": entry_weight,
            },
            "options_dislocation": {
                "schema": dislocation_gate.get("schema"),
                "status": dislocation_gate.get("status"),
                "scored": _as_bool(dislocation_gate.get("scored")),
                "weight": _number(dislocation_gate.get("weight")),
                "scored_primitives": scored_primitives,
            },
            "coverage": {
                "schema": options_entry_coverage.get("schema"),
                "as_of": options_entry_coverage.get("as_of"),
                "n_rows": feature_coverage.get("n_rows"),
                "n_features": feature_coverage.get("n_features"),
                "absent_stores": list(options_entry_coverage.get("absent_stores") or []),
                "feature_highlights": feature_highlights,
                "structural_null_highlights": structural_highlights,
            },
        },
        "reason": (
            "Positioning context is present, but the options-entry and dislocation "
            "gates currently confer zero rank, gate, size, or Macro weight authority."
            if context_available and not promotion_ready
            else None
            if promotion_ready
            else "No positioning context artifact is available."
        ),
    }


def build_payload(
    *,
    flow_leaders: Mapping[str, Any] | None = None,
    pick_lab: Mapping[str, Any] | None = None,
    signing_gate: Mapping[str, Any] | None = None,
    options_entry_gate: Mapping[str, Any] | None = None,
    options_entry_coverage: Mapping[str, Any] | None = None,
    dislocation_gate: Mapping[str, Any] | None = None,
    konseki_context: Mapping[str, Any] | None = None,
    source_errors: Mapping[str, str | None] | None = None,
    built_at: str | None = None,
) -> dict[str, Any]:
    flow_leaders = flow_leaders or {}
    pick_lab = pick_lab or {}
    signing_gate = signing_gate or {}
    options_entry_gate = options_entry_gate or {}
    options_entry_coverage = options_entry_coverage or {}
    dislocation_gate = dislocation_gate or {}
    konseki_context = konseki_context or {}
    source_errors = source_errors or {}
    projection_built_at = _iso_timestamp(built_at) or _now_iso()

    flow_session = _session_date(flow_leaders.get("session_date"))
    pick_session = _session_date(pick_lab.get("as_of"))
    flow_available_at = _iso_timestamp(flow_leaders.get("as_of"))
    pick_available_at = _iso_timestamp(pick_lab.get("built_at"))
    flow_pit_ready = _timestamp_lte(flow_available_at, projection_built_at)
    pick_pit_ready = _timestamp_lte(pick_available_at, projection_built_at)
    flow_schema_ok = flow_leaders.get("schema") == "flow_leaders.v1"
    flow_fresh = flow_leaders.get("stale") is False
    flow_warm = flow_leaders.get("cold_start") is False
    flow_ready = (
        flow_schema_ok
        and flow_fresh
        and flow_warm
        and bool(flow_session)
        and flow_pit_ready
    )
    books_obj = pick_lab.get("books")
    books_obj = books_obj if isinstance(books_obj, Mapping) else {}
    flow_books_match_contract = all(
        isinstance(books_obj.get(engine_id), Mapping)
        and books_obj[engine_id].get("engine_id") == engine_id
        and isinstance(books_obj[engine_id].get("picks_today"), list)
        for engine_id, _lane in FLOW_BOOKS
    )
    pick_ready = (
        pick_lab.get("authority") == AUTHORITY
        and flow_books_match_contract
        and bool(pick_session)
        and pick_pit_ready
    )
    source_alignment = bool(flow_session and pick_session and flow_session == pick_session)

    signing = _signing_read(signing_gate)
    # Row projection is contract-gated, not merely annotated by a blocked card.
    # Foreign Flow Leaders shapes and non-display Pick Lab payloads cannot render
    # candidates or fires in Terminal.
    opportunities = (
        _opportunities(
            pick_lab,
            signing,
            projection_available_at=projection_built_at,
        )
        if pick_ready and flow_ready and source_alignment
        else []
    )
    watchlist = (
        _watchlist(
            flow_leaders,
            signing,
            projection_available_at=projection_built_at,
        )
        if flow_ready
        else []
    )
    ledgers = _forward_ledgers(pick_lab) if pick_ready else _forward_ledgers({})
    accrual = _accrual_contract(opportunities=opportunities, ledgers=ledgers)
    ledger_ready = len(ledgers["books"]) == len(FLOW_BOOKS)
    sample_ready = ledger_ready and all(
        book.get("status") == "SCOREABLE" for book in ledgers["books"]
    )

    projected_rows = [*opportunities, *watchlist]
    used_sources = {
        str(row.get("signing_source") or "").strip().lower()
        for row in projected_rows
    }
    signing_ready = bool(projected_rows) and all(
        bool(source) and _source_direction_reliable(source, signing)
        for source in used_sources
    )
    entry_schema = str(options_entry_gate.get("schema") or "")
    positioning_gate_available = entry_schema.startswith("options_entry.gate.v")
    coverage_available = (
        options_entry_coverage.get("schema") == "options_entry_coverage.v1"
        and isinstance(options_entry_coverage.get("feature_coverage"), Mapping)
    )
    dislocation_available = (
        dislocation_gate.get("schema") == "options_dislocation.gate.v1"
    )
    context_available = (
        bool(watchlist)
        or positioning_gate_available
        or coverage_available
        or dislocation_available
    )
    positioning = _positioning_readiness(
        context_available=context_available,
        options_entry_gate=options_entry_gate,
        options_entry_coverage=options_entry_coverage,
        dislocation_gate=dislocation_gate,
    )

    if signing_ready:
        signing_reason = None
    elif not projected_rows:
        signing_reason = "No signed-flow source is present in the projection."
    else:
        signing_reason = (
            "At least one represented signing source has not passed its production "
            "direction gate; magnitude and positioning may still be displayed."
        )

    components = {
        "information": {
            "ready": flow_ready and signing_ready,
            "context_available": bool(watchlist),
            "promotion_ready": False,
            "reason": signing_reason
            if not signing_ready
            else "Signed information is observable but remains display-only.",
        },
        "positioning": positioning,
        "execution": {
            "ready": False,
            "context_available": False,
            "promotion_ready": False,
            "reason": (
                "No executable OCC contract selection, quote/spread, fill, lifecycle, "
                "or mark ledger is part of this projection."
            ),
        },
        "flow_leaders": {
            "ready": flow_ready,
            "reason": None
            if flow_ready
            else "Flow Leaders is missing, stale, cold, or on the wrong schema.",
        },
        "pick_lab": {
            "ready": pick_ready,
            "reason": None
            if pick_ready
            else "The two display-only flow books are not available in Pick Lab.",
        },
        "signed_flow": {
            "ready": signing_ready,
            "reason": signing_reason,
        },
        "flow_forward_ledgers": {
            "ready": ledger_ready,
            "sample_ready": sample_ready,
            "reason": None
            if ledger_ready
            else "One or both flow-book forward ledger rows are absent.",
        },
    }

    as_of = flow_session if flow_ready else pick_session if pick_ready else None
    if not as_of and flow_schema_ok and isinstance(flow_leaders.get("as_of"), str):
        as_of = str(flow_leaders.get("as_of"))[:10]

    payload = {
        "schema": SCHEMA,
        "as_of": as_of,
        "built_at": projection_built_at,
        "decision_at": None,
        "available_at": projection_built_at,
        "pit_provenance": {
            "clock": "UTC",
            "decision_at_required_for_issued_portfolio": True,
            "decision_at_status": "not_available_in_current_pick_lab_contract",
            "available_at_status": "exact_projection_publication_time",
            "source_available_at": {
                "flow_leaders": flow_available_at,
                "pick_lab": pick_available_at,
            },
            "promotion_ready": False,
            "reason": (
                "An issued position requires exact decision_at and available_at on "
                "every fire. Current Pick Lab fires expose exact artifact availability "
                "when present but not an exact decision clock."
            ),
        },
        "authority": AUTHORITY,
        "mode": "shadow",
        "selection_policy": {
            "style": "abstention_first",
            "stage": "future_model_portfolio_policy_not_implemented",
            "target_batch_size": {"min": 3, "max": 4},
            "cadence": "event_driven_every_few_sessions",
            "abstention_allowed": True,
            "capacity_enforced_by_projection": False,
            "capacity_breach": len(opportunities) > 4,
            "reason": (
                "Wave 0 preserves every governed Pick Lab fire. A later issued-model-"
                "portfolio policy must jointly enforce regime, correlation/sleeve, cash, "
                "cooldown, new-pick, and minimum-hold constraints; the UI cannot simulate "
                "that policy by hiding extra fires."
            ),
        },
        "portfolio_boundary": {
            "current_stage": "research_fire",
            "operator_reviewed_issue_desk": False,
            "issued_model_portfolio": False,
            "managed_positions": False,
            "reason": (
                "A research candidate or Pick Lab fire is not an issued portfolio position. "
                "No operator Issue Desk, allocation, portfolio-fit, minimum-hold, or "
                "managed-position policy is implemented in this artifact."
            ),
        },
        "opportunities": opportunities,
        "watchlist": watchlist,
        "readiness": {
            "components": components,
            "gates": {
                "source_freshness": {
                    "pass": flow_ready and pick_ready,
                    "scope": "flow_leaders_freshness_and_pick_lab_contract",
                    "reason": None
                    if flow_ready and pick_ready
                    else (
                        "Flow Leaders is stale/cold/foreign or the Pick Lab flow-book "
                        "contract is unavailable."
                    ),
                },
                "source_alignment": {
                    "pass": source_alignment,
                    "scope": "flow_leaders_and_pick_lab_only",
                    "reason": (
                        "Flow Leaders and Pick Lab sessions align; context gates retain "
                        "their separately disclosed vintages."
                    )
                    if source_alignment
                    else "Flow Leaders session_date and Pick Lab as_of do not match.",
                },
                "signing": {"pass": signing_ready, "reason": signing_reason},
                "forward_sample": {
                    "pass": sample_ready,
                    "reason": None
                    if sample_ready
                    else "Both flow books have not yet reached SCOREABLE sample status.",
                },
                "trajectory_calibration": {
                    "pass": False,
                    "reason": "No pre-registered options path/exit calibration is attached.",
                },
            },
        },
        "direction": {
            # Passing the signing gate only establishes a measurement input. This
            # projection originates no directional value, so reliability is false.
            "reliable": False,
            "value": None,
            "signing_gate_passed": signing_ready,
            **signing,
            "reason": signing_reason
            or "Signing is measurable; this projection still originates no direction.",
        },
        "trajectory": {
            "status": "withheld",
            "take_profit": None,
            "time_to_target": None,
            "exit_window": None,
            "reason": "Trajectory remains withheld until a PIT path/exit calibration passes.",
        },
        "forward_ledgers": ledgers,
        "accrual": accrual,
        "context_inputs": {
            "konseki_market_memory": _konseki_context(
                konseki_context,
                projection_available_at=projection_built_at,
                projection_decision_at=None,
            ),
        },
        "macro_feedback": {
            "enabled": False,
            "weight": 0.0,
            "mode": "shadow_only",
            "reason": (
                "No paired incremental-attribution gate has earned options weight in "
                "Macro Prophet ranking."
            ),
        },
        "provenance": {
            "flow_leaders": {
                "path": "site/flowleaders/leaders.json",
                "schema": flow_leaders.get("schema"),
                "as_of": flow_session or flow_leaders.get("as_of"),
                "available": bool(flow_leaders),
                "error": source_errors.get("flow_leaders"),
            },
            "pick_lab": {
                "path": "site/labdata/pick_lab.json",
                "schema": "implicit",
                "as_of": pick_session,
                "available": bool(pick_lab),
                "error": source_errors.get("pick_lab"),
            },
            "signing_gate": {
                "path": "data/options_flow/signing_gate.json",
                "schema": signing_gate.get("schema") or "implicit",
                "as_of": signing_gate.get("asof"),
                "available": bool(signing_gate),
                "error": source_errors.get("signing_gate"),
            },
            "options_entry_gate": {
                "path": "data/options_entry/gate.json",
                "schema": options_entry_gate.get("schema"),
                "as_of": options_entry_gate.get("generated_at"),
                "available": bool(options_entry_gate),
                "error": source_errors.get("options_entry_gate"),
            },
            "options_entry_coverage": {
                "path": "data/options_entry/coverage.json",
                "schema": options_entry_coverage.get("schema"),
                "as_of": options_entry_coverage.get("as_of")
                or options_entry_coverage.get("generated_at"),
                "available": bool(options_entry_coverage),
                "error": source_errors.get("options_entry_coverage"),
            },
            "options_dislocation_gate": {
                "path": "data/options_dislocation/validation_gate.json",
                "schema": dislocation_gate.get("schema"),
                "as_of": dislocation_gate.get("generated_at"),
                "available": bool(dislocation_gate),
                "error": source_errors.get("dislocation_gate"),
            },
            "konseki_market_memory": {
                "path": source_errors.get("konseki_context_path"),
                "expected_schema": KONSEKI_SCHEMA,
                "schema": konseki_context.get("schema"),
                "available_at": _iso_timestamp(konseki_context.get("available_at")),
                "available": bool(konseki_context),
                "error": source_errors.get("konseki_context"),
            },
        },
        "method_note": (
            "Display-only projection of existing Flow Leaders order and Pick Lab fires. "
            "No composite score, probability, direction, contract, or trajectory is created."
        ),
    }
    return _json_safe(payload)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(payload, indent=2, sort_keys=False, allow_nan=False) + "\n"
    ).encode("utf-8")
    descriptor, staged_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    staged = Path(staged_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staged, path)
    finally:
        if staged.exists():
            staged.unlink()


def build_from_disk(
    *,
    flow_leaders_path: Path,
    pick_lab_path: Path,
    signing_gate_path: Path,
    options_entry_gate_path: Path,
    options_entry_coverage_path: Path,
    dislocation_gate_path: Path,
    output_path: Path,
    konseki_context_path: Path | None = None,
    built_at: str | None = None,
) -> dict[str, Any]:
    source_paths = {
        "flow_leaders": flow_leaders_path,
        "pick_lab": pick_lab_path,
        "signing_gate": signing_gate_path,
        "options_entry_gate": options_entry_gate_path,
        "options_entry_coverage": options_entry_coverage_path,
        "dislocation_gate": dislocation_gate_path,
    }
    loaded: dict[str, dict[str, Any]] = {}
    errors: dict[str, str | None] = {}
    for name, path in source_paths.items():
        loaded[name], errors[name] = _read_json(path)
    if konseki_context_path is not None:
        loaded["konseki_context"], errors["konseki_context"] = _read_json(
            konseki_context_path
        )
        errors["konseki_context_path"] = str(konseki_context_path)
    else:
        loaded["konseki_context"] = {}
        errors["konseki_context"] = None
        errors["konseki_context_path"] = None

    payload = build_payload(
        flow_leaders=loaded["flow_leaders"],
        pick_lab=loaded["pick_lab"],
        signing_gate=loaded["signing_gate"],
        options_entry_gate=loaded["options_entry_gate"],
        options_entry_coverage=loaded["options_entry_coverage"],
        dislocation_gate=loaded["dislocation_gate"],
        konseki_context=loaded["konseki_context"],
        source_errors=errors,
        built_at=built_at,
    )
    _atomic_write_json(output_path, payload)
    return payload


def _default_paths() -> dict[str, Path]:
    root = _repo_root()
    return {
        "flow_leaders_path": root / "site" / "flowleaders" / "leaders.json",
        "pick_lab_path": root / "site" / "labdata" / "pick_lab.json",
        "signing_gate_path": root / "data" / "options_flow" / "signing_gate.json",
        "options_entry_gate_path": root / "data" / "options_entry" / "gate.json",
        "options_entry_coverage_path": root
        / "data"
        / "options_entry"
        / "coverage.json",
        "dislocation_gate_path": root
        / "data"
        / "options_dislocation"
        / "validation_gate.json",
        "output_path": root / "site" / "options_prophet" / "index.json",
    }


def main() -> int:
    defaults = _default_paths()
    parser = argparse.ArgumentParser(
        description="Build the display-only Options Prophet shadow projection"
    )
    parser.add_argument("--flow-leaders", type=Path, default=defaults["flow_leaders_path"])
    parser.add_argument("--pick-lab", type=Path, default=defaults["pick_lab_path"])
    parser.add_argument("--signing-gate", type=Path, default=defaults["signing_gate_path"])
    parser.add_argument(
        "--options-entry-gate",
        type=Path,
        default=defaults["options_entry_gate_path"],
    )
    parser.add_argument(
        "--options-entry-coverage",
        type=Path,
        default=defaults["options_entry_coverage_path"],
    )
    parser.add_argument(
        "--dislocation-gate",
        type=Path,
        default=defaults["dislocation_gate_path"],
    )
    parser.add_argument(
        "--konseki-context",
        type=Path,
        default=None,
        help=(
            "Optional governed konseki.market_memory/v1 receipt; projected as "
            "context_only with weight zero"
        ),
    )
    parser.add_argument("--output", type=Path, default=defaults["output_path"])
    args = parser.parse_args()

    payload = build_from_disk(
        flow_leaders_path=args.flow_leaders,
        pick_lab_path=args.pick_lab,
        signing_gate_path=args.signing_gate,
        options_entry_gate_path=args.options_entry_gate,
        options_entry_coverage_path=args.options_entry_coverage,
        dislocation_gate_path=args.dislocation_gate,
        konseki_context_path=args.konseki_context,
        output_path=args.output,
    )
    print(
        "build_options_prophet: "
        f"wrote {args.output} ({len(payload['opportunities'])} opportunities, "
        f"{len(payload['watchlist'])} watch rows, authority={AUTHORITY})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
