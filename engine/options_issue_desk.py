"""Private, append-only R6.2-A Options Issue Desk.

This module deliberately owns operator research-plan records only.  It never
imports a ranker, broker, allocator, or options producer; an issued row is not
a brokerage trade and cannot grant any automatic authority.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import uuid
from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
from datetime import time as clock_time
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from lib import nyse_calendar

SCHEMA = "options.issue_desk/v1"
PROPOSAL_SCHEMA = "options.issue_desk_proposal/v1"
DECISION_SCHEMA = "options.issue_desk_decision/v1"
ISSUE_RECEIPT_SCHEMA = "options.issue_receipt/v1"
MAX_NEW_ISSUES = 4
ROLLING_SESSIONS = 3
MAX_PROPOSALS = 12
MAX_QUOTE_AGE = timedelta(minutes=15)
MAX_SPREAD_PCT = 0.20
MAX_ACTIVE_PER_SLEEVE = 2
MAX_ACTIVE_PER_CORRELATION_CLUSTER = 1
_SHA = re.compile(r"^[a-f0-9]{64}$")
_OCC = re.compile(r"^([A-Z0-9]{1,6})(\d{6})([CP])(\d{8})$")
_IDEMPOTENCY = re.compile(r"^[A-Za-z0-9._:-]{16,128}$")
APPROVE_REASON_CODES = {"PORTFOLIO_FIT", "REGIME_ALIGNED", "EXECUTION_VERIFIED", "DIVERSIFICATION_FIT"}
REJECT_REASON_CODES = {"ABSTAIN", "REGIME_MISMATCH", "CORRELATION_CAP", "COOLDOWN", "EVENT_RISK", "EXECUTION_MISSING", "LIQUIDITY", "NO_EDGE"}

AUTHORITY = {
    "may_trade": False,
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_automatic": False,
}


class IssueDeskError(ValueError):
    """A deterministic client-safe desk rejection."""


class ConflictError(IssueDeskError):
    """A legal request cannot change the current folded state."""


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", value
    ):
        raise IssueDeskError(f"{field} must be an exact UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IssueDeskError(f"{field} must be an exact UTC timestamp") from exc
    if parsed.tzinfo is None:
        raise IssueDeskError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _finite(value: object, field: str, *, positive: bool = False) -> float:
    if type(value) not in (int, float):
        raise IssueDeskError(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number) or (positive and number <= 0):
        raise IssueDeskError(f"{field} must be {'positive and ' if positive else ''}finite")
    return number


def _weight(value: object, field: str, *, positive: bool = False) -> float:
    number = _finite(value, field, positive=positive)
    if number < 0.0 or number > 1.0:
        raise IssueDeskError(f"{field} must be between 0 and 1")
    return number


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


@lru_cache(maxsize=1)
def _contract_validators() -> dict[str, Draft202012Validator]:
    contract_root = Path(__file__).resolve().parents[1] / "contracts" / "options"
    files = {
        "receipt": "options.issue_receipt.v1.schema.json",
        "proposal": "options.issue_desk_proposal.v1.schema.json",
        "decision": "options.issue_desk_decision.v1.schema.json",
        "document": "options.issue_desk.v1.schema.json",
    }
    registry = Registry()
    schemas: dict[str, dict[str, Any]] = {}
    for name, filename in files.items():
        try:
            schema = json.loads((contract_root / filename).read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
        except (OSError, KeyError, ValueError) as exc:
            raise IssueDeskError(f"Issue Desk {name} contract is unavailable") from exc
        schemas[name] = schema
    return {
        name: Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
        for name, schema in schemas.items()
    }


def _validate_contract(value: Mapping[str, Any], name: str) -> None:
    try:
        _canonical(value)
    except (TypeError, ValueError) as exc:
        raise IssueDeskError(f"Issue Desk {name} is not strict canonical JSON") from exc
    errors = sorted(_contract_validators()[name].iter_errors(value), key=lambda item: list(item.absolute_path))
    if errors:
        path = ".".join(str(part) for part in errors[0].absolute_path) or "root"
        raise IssueDeskError(f"Issue Desk {name} contract failed at {path}: {errors[0].message}")


def state_dir() -> Path:
    explicit = os.environ.get("OPTIONS_ISSUE_DESK_STATE_DIR", "").strip()
    if explicit:
        return Path(explicit)
    base = Path(os.environ.get("MACRO_API_STATE_DIR", "/var/lib/macro-api"))
    return base / "options_issue_desk"


def _paths(root: Path) -> tuple[Path, Path, Path]:
    return root / "proposals.jsonl", root / "decisions.jsonl", root / ".lock"


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None, str | None]:
    if not path.exists():
        return None, None, "missing"
    try:
        raw = path.read_bytes()
        value = json.loads(raw, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)), object_pairs_hook=_strict_object)
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return None, None, "unreadable"
    if not isinstance(value, dict):
        return None, None, "root_not_object"
    return value, hashlib.sha256(raw).hexdigest(), None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise IssueDeskError("desk ledger has a torn final line")
    rows: list[dict[str, Any]] = []
    for lineno, line in enumerate(raw.splitlines(), 1):
        if not line:
            raise IssueDeskError(f"desk ledger has a blank line at {lineno}")
        try:
            row = json.loads(line, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)), object_pairs_hook=_strict_object)
        except (ValueError, json.JSONDecodeError) as exc:
            raise IssueDeskError(f"desk ledger has malformed line {lineno}") from exc
        if not isinstance(row, dict):
            raise IssueDeskError(f"desk ledger line {lineno} is not an object")
        rows.append(row)
    return rows


def _append(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    encoded = _canonical(dict(row)) + b"\n"
    with path.open("a+b") as handle:
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _with_lock(root: Path):
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(root, 0o700)
    except OSError:
        pass
    _, _, lock_path = _paths(root)
    handle = lock_path.open("a+b")
    try:
        os.chmod(lock_path, 0o600)
    except OSError:
        pass
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    return handle


def _session_for(now: datetime) -> str:
    # Issuance is tied to a real NYSE session.  After close/weekends roll to the
    # next session rather than silently pretending a calendar date is tradable.
    local = now.astimezone(ZoneInfo("America/New_York"))
    candidate = local.date()
    if local.timetz().replace(tzinfo=None) >= clock_time(16, 0):
        candidate += timedelta(days=1)
    while not nyse_calendar.is_session(candidate):
        candidate += timedelta(days=1)
    return candidate.isoformat()


def _rolling_sessions(session: str) -> list[str]:
    cursor = date.fromisoformat(session)
    out: list[str] = []
    while len(out) < ROLLING_SESSIONS:
        if nyse_calendar.is_session(cursor):
            out.append(cursor.isoformat())
        cursor -= timedelta(days=1)
    return out


def _read_context_artifact(
    kind: str, path: Path, *, repo: Path, snapshot_at: datetime
) -> tuple[dict[str, Any] | None, dict[str, Any], bool]:
    """Read one context file once and bind its payload, digest, and exact PIT clock."""
    payload, digest, error = _read_json(path)
    available_at: str | None = None
    usable = False
    status = error or "available"
    if error is None and payload is not None:
        raw_available_at = payload.get("available_at")
        if not isinstance(payload.get("schema"), str) or not payload.get("schema") or not digest:
            status = "unreadable"
        elif not isinstance(raw_available_at, str):
            status = "availability_missing"
        else:
            try:
                parsed_available_at = _parse_utc(raw_available_at, f"{kind}.available_at")
            except IssueDeskError:
                status = "availability_invalid"
            else:
                if parsed_available_at > snapshot_at:
                    status = "future_unusable"
                else:
                    available_at = raw_available_at
                    usable = True
    receipt = {
        "kind": kind,
        "path": str(path.relative_to(repo)),
        "status": status,
        "schema": payload.get("schema") if payload else None,
        "sha256": digest,
        "as_of": (payload or {}).get("as_of") or (payload or {}).get("asof"),
        "available_at": available_at,
    }
    return payload, receipt, usable


def _proposal_from_plan(plan: Mapping[str, Any], *, source: dict[str, Any], receipts: list[dict[str, Any]], reviewer: str, source_rank: int, revision: int, now: datetime) -> dict[str, Any]:
    plan_id = str(plan.get("id") or "").strip()
    asset = str(plan.get("asset") or "").strip().upper()
    if not plan_id or not asset or str(plan.get("direction") or "").upper() != "BULL":
        raise IssueDeskError("source Macro plan is not a current BULL plan")
    frozen = {key: plan.get(key) for key in (
        "id", "asset", "direction", "entry", "trigger", "invalidation", "targets",
        "option_contract", "entry_zone", "plan_asof", "recorded_at", "phase",
        "closed", "horizon_days", "signal_date", "price_basis_date",
    )}
    identity = hashlib.sha256(plan_id.encode()).hexdigest()[:24]
    return {
        "schema": PROPOSAL_SCHEMA,
        "proposal_id": f"oidp_{identity}",
        "proposal_revision": revision,
        "state": "PENDING_REVIEW",
        "created_at": _iso(now),
        "available_at": _iso(now),
        "assigned_reviewer": reviewer,
        "source_rank": source_rank,
        "macro_candidate": frozen,
        "source": source,
        "context_receipts": receipts,
        "execution_readiness": {
            "ready": False,
            "reason": "A complete operator-attested executable issue receipt is required before approval.",
        },
        "authority": dict(AUTHORITY),
    }


def _validate_reason_codes(action: str, reason_codes: object) -> list[str]:
    allowed = APPROVE_REASON_CODES if action == "approve" else REJECT_REASON_CODES if action == "reject" else set()
    if (
        not allowed
        or not isinstance(reason_codes, list)
        or not (1 <= len(reason_codes) <= 8)
        or len(set(reason_codes)) != len(reason_codes)
        or any(not isinstance(item, str) or item not in allowed for item in reason_codes)
    ):
        raise IssueDeskError(f"reason_codes are invalid for {action or 'unknown'} action")
    return reason_codes


def _validate_proposal_context(proposal: Mapping[str, Any], proposal_available_at: datetime) -> None:
    receipts = proposal.get("context_receipts")
    if not isinstance(receipts, list):
        raise IssueDeskError("proposal context_receipts are invalid")
    for receipt in receipts:
        if not isinstance(receipt, Mapping) or not isinstance(receipt.get("source"), Mapping):
            raise IssueDeskError("proposal context receipt is invalid")
        kind = receipt.get("kind")
        source = receipt["source"]
        if source.get("kind") != kind:
            raise IssueDeskError("proposal context source kind does not match receipt kind")
        status = source.get("status")
        source_available_at: datetime | None = None
        if status == "available":
            source_available_at = _parse_utc(source.get("available_at"), f"context.{kind}.available_at")
            if source_available_at > proposal_available_at:
                raise IssueDeskError("proposal context availability exceeds proposal availability")
            if (
                not isinstance(source.get("schema"), str)
                or not source.get("schema")
                or not isinstance(source.get("sha256"), str)
                or not _SHA.fullmatch(source["sha256"])
            ):
                raise IssueDeskError("available proposal context lacks source schema or digest")
        elif (
            source.get("available_at") is not None
            or receipt.get("evidence") is not None
            or not isinstance(receipt.get("gap"), str)
            or not receipt["gap"].strip()
        ):
            raise IssueDeskError("unavailable proposal context must contain only an explicit gap")
        evidence = receipt.get("evidence")
        if kind == "options_shadow" and evidence is not None:
            if not isinstance(evidence, Mapping) or source_available_at is None:
                raise IssueDeskError("options context evidence lacks an available source receipt")
            evidence_available_at = _parse_utc(
                evidence.get("available_at"), "context.options_shadow.evidence.available_at"
            )
            if evidence_available_at > source_available_at:
                raise IssueDeskError("options context evidence availability exceeds source availability")
            expected_symbol = str((proposal.get("macro_candidate") or {}).get("asset") or "").upper()
            if evidence.get("symbol") != expected_symbol:
                raise IssueDeskError("options context evidence symbol does not match proposal symbol")


def _fold(proposals: list[dict[str, Any]], decisions: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    latest: dict[str, dict[str, Any]] = {}
    frozen: dict[str, dict[str, Any]] = {}
    for proposal in proposals:
        _validate_contract(proposal, "proposal")
        if proposal.get("state") != "PENDING_REVIEW":
            raise IssueDeskError("proposal ledger may contain only immutable PENDING_REVIEW rows")
        created_at = _parse_utc(proposal.get("created_at"), "proposal.created_at")
        available_at = _parse_utc(proposal.get("available_at"), "proposal.available_at")
        if available_at < created_at or proposal.get("authority") != AUTHORITY:
            raise IssueDeskError("proposal clock or authority is invalid")
        _validate_proposal_context(proposal, available_at)
        key = f"{proposal['proposal_id']}:{proposal['proposal_revision']}"
        if key in latest:
            raise IssueDeskError(f"duplicate proposal revision in desk ledger: {key}")
        frozen[key] = proposal
        latest[key] = {**proposal, "state": "PENDING_REVIEW"}
    latest_revision_by_id: dict[str, int] = {}
    for proposal in latest.values():
        proposal_id = str(proposal["proposal_id"])
        latest_revision_by_id[proposal_id] = max(
            latest_revision_by_id.get(proposal_id, 0), int(proposal["proposal_revision"])
        )
    for proposal in latest.values():
        if int(proposal["proposal_revision"]) != latest_revision_by_id[str(proposal["proposal_id"])]:
            proposal["state"] = "SUPERSEDED"
    ordered: list[dict[str, Any]] = []
    seen_decisions: set[str] = set()
    seen_idempotency: set[str] = set()
    decided_proposals: set[str] = set()
    prior_decision_at: datetime | None = None
    prior_available_at: datetime | None = None
    for decision in decisions:
        _validate_contract(decision, "decision")
        decision_id = str(decision["decision_id"])
        idempotency_key = str(decision["idempotency_key"])
        if decision_id in seen_decisions or idempotency_key in seen_idempotency:
            raise IssueDeskError("duplicate decision or idempotency key in desk ledger")
        seen_decisions.add(decision_id)
        seen_idempotency.add(idempotency_key)
        key = f"{decision['proposal_id']}:{decision['proposal_revision']}"
        proposal = latest.get(key)
        if proposal is None:
            raise IssueDeskError(f"decision references unknown proposal revision: {key}")
        if int(decision["proposal_revision"]) != latest_revision_by_id[str(decision["proposal_id"])]:
            raise IssueDeskError(f"decision references non-latest proposal revision: {key}")
        if key in decided_proposals or proposal.get("state") != "PENDING_REVIEW":
            raise IssueDeskError(f"multiple decisions for proposal revision: {key}")
        if decision.get("proposal_sha256") != _sha256(frozen[key]):
            raise IssueDeskError("decision proposal hash does not match the immutable proposal")
        decision_at = _parse_utc(decision.get("decision_at"), "decision.decision_at")
        available_at = _parse_utc(decision.get("available_at"), "decision.available_at")
        proposal_available = _parse_utc(proposal.get("available_at"), "proposal.available_at")
        if decision_at < proposal_available or available_at < decision_at:
            raise IssueDeskError("decision clocks precede available evidence")
        if (
            (prior_decision_at is not None and decision_at < prior_decision_at)
            or (prior_available_at is not None and available_at < prior_available_at)
        ):
            raise IssueDeskError("decision ledger clocks are not append-order monotonic")
        prior_decision_at, prior_available_at = decision_at, available_at
        if decision.get("decision_session") != _session_for(decision_at):
            raise IssueDeskError("decision_session does not match the decision clock")
        expected_sessions = sorted(_rolling_sessions(str(decision["decision_session"])))
        capacity = decision.get("capacity") or {}
        if capacity.get("rolling_sessions") != expected_sessions:
            raise IssueDeskError("decision capacity session window is invalid")
        prior_issued = [row for row in ordered if row.get("next_state") == "ISSUED"]
        issued_in_window_before = sum(row.get("decision_session") in set(expected_sessions) for row in prior_issued)
        action = str(decision.get("action") or "")
        _validate_reason_codes(action, decision.get("reason_codes"))
        is_issue = action == "approve"
        expected_symbol = str((proposal.get("macro_candidate") or {}).get("asset") or "").upper()
        if decision.get("proposal_symbol") != expected_symbol:
            raise IssueDeskError("decision proposal_symbol does not match the immutable proposal")
        expected_count = issued_in_window_before + (1 if is_issue else 0)
        if capacity.get("issued_in_window") != expected_count or capacity.get("remaining") != MAX_NEW_ISSUES - expected_count:
            raise IssueDeskError("decision capacity receipt does not replay")
        portfolio_before = _portfolio_state(prior_issued)
        if decision.get("portfolio_state_before") != portfolio_before:
            raise IssueDeskError("decision portfolio_state_before does not replay")
        next_state = decision["next_state"]
        if is_issue:
            symbol = expected_symbol
            receipt = _validate_issue_receipt(decision.get("issue_receipt"), decision_at=decision_at, expected_symbol=symbol)
            prior_symbols = {str(row.get("proposal_symbol") or "").upper() for row in prior_issued}
            if symbol in prior_symbols:
                raise IssueDeskError("duplicate active symbol in issued decision ledger")
            fit = receipt["portfolio_fit"]
            prior_fits = [((row.get("issue_receipt") or {}).get("portfolio_fit") or {}) for row in prior_issued]
            if sum(item.get("sleeve") == fit["sleeve"] for item in prior_fits) >= MAX_ACTIVE_PER_SLEEVE:
                raise IssueDeskError("issued decision ledger exceeds sleeve capacity")
            if sum(item.get("correlation_cluster") == fit["correlation_cluster"] for item in prior_fits) >= MAX_ACTIVE_PER_CORRELATION_CLUSTER:
                raise IssueDeskError("issued decision ledger exceeds correlation capacity")
            allocation_after = portfolio_before["allocation_weight"] + float(receipt["risk"]["allocation_weight"])
            expected_cash = max(0.0, 1.0 - allocation_after)
            if not math.isclose(float(receipt["risk"]["cash_after_weight"]), expected_cash, abs_tol=0.000001):
                raise IssueDeskError("issued decision cash receipt does not reconcile")
            expected_after = {
                "allocation_weight": allocation_after,
                "cash_weight": expected_cash,
                "active_position_count": portfolio_before["active_position_count"] + 1,
            }
        else:
            expected_after = portfolio_before
        if decision.get("portfolio_state_after") != expected_after:
            raise IssueDeskError("decision portfolio_state_after does not replay")
        request_digest = _sha256({
            "proposal_id": decision["proposal_id"],
            "proposal_revision": decision["proposal_revision"],
            "action": decision["action"],
            "reason_codes": decision["reason_codes"],
            "issue_receipt": decision["issue_receipt"],
            "reviewer": decision["reviewer"],
        })
        if decision.get("request_sha256") != request_digest or decision.get("authority") != AUTHORITY:
            raise IssueDeskError("decision request hash or authority is invalid")
        proposal["state"] = next_state
        proposal["decision_id"] = decision_id
        proposal["decision_at"] = decision["decision_at"]
        decided_proposals.add(key)
        ordered.append(decision)
    return latest, ordered


def _current_plan_source(repo: Path) -> tuple[dict[str, Any], list[Mapping[str, Any]]]:
    path = repo / "site" / "prophet" / "index.json"
    payload, digest, error = _read_json(path)
    if error is not None or payload is None or payload.get("schema") != "prophet.index/v1" or not digest:
        raise IssueDeskError("current Macro Prophet candidate artifact is unavailable")
    plans = payload.get("plans")
    if not isinstance(plans, list):
        raise IssueDeskError("current Macro Prophet candidate artifact has no plan list")
    source = {
        "path": "site/prophet/index.json",
        "schema": "prophet.index/v1",
        "sha256": digest,
        "as_of": payload.get("asof"),
        # Prophet v1 has no trustworthy exact availability clock.  The desk
        # clock below is the first exact availability time for this proposal.
        "available_at": None,
        "available_at_status": "not_available_in_current_macro_contract",
    }
    return source, [row for row in plans if isinstance(row, Mapping)]


def _context_receipts(
    symbol: str,
    *,
    snapshot_at: datetime,
    options_artifact: tuple[dict[str, Any] | None, dict[str, Any], bool],
    vol_artifact: tuple[dict[str, Any] | None, dict[str, Any], bool],
    gex_artifact: tuple[dict[str, Any] | None, dict[str, Any], bool],
) -> list[dict[str, Any]]:
    """Freeze bounded display context from single-read, exact-clock source receipts."""
    options, options_source, options_source_ok = options_artifact
    matching: Mapping[str, Any] | None = None
    if isinstance(options, dict):
        for field in ("opportunities", "watchlist"):
            rows = options.get(field)
            if isinstance(rows, list):
                matching = next((row for row in rows if isinstance(row, Mapping) and str(row.get("symbol") or "").upper() == symbol), None)
                if matching:
                    break
    if matching and options_source_ok:
        observations = matching.get("observations") if isinstance(matching.get("observations"), Mapping) else {}
        projected_observations = {key: observations.get(key) for key in ("recurrence_count", "net_prem_norm_abs", "days_since_inflection", "oi_confirmed", "zerodte_dominated", "gamma_regime", "K_a", "n_avail_a", "K_b", "n_avail_b")}
        flow_z = observations.get("flow_z")
        if type(flow_z) in (int, float) and math.isfinite(float(flow_z)):
            projected_observations["flow_magnitude"] = abs(float(flow_z))
        options_evidence: dict[str, Any] = {
            "symbol": symbol,
            "available_at": matching.get("available_at"),
            "source_signing_reliable": matching.get("source_signing_reliable") is True,
            "direction_reliable": matching.get("direction_reliable") is True,
            "signing_source": matching.get("signing_source"),
            "lanes": matching.get("lanes") if isinstance(matching.get("lanes"), list) else [],
            "fire_lanes": matching.get("fire_lanes") if isinstance(matching.get("fire_lanes"), list) else [],
            "source_positions": matching.get("source_positions") if isinstance(matching.get("source_positions"), Mapping) else {},
            "observations": projected_observations,
            "de_escalation": matching.get("de_escalation") if isinstance(matching.get("de_escalation"), Mapping) else {},
        }
        try:
            evidence_available = _parse_utc(matching.get("available_at"), "options_shadow.available_at")
            source_available = _parse_utc(options_source["available_at"], "options_shadow.source.available_at")
            if evidence_available > snapshot_at or evidence_available > source_available:
                options_evidence, options_gap = None, "context_available_after_proposal_snapshot"
            else:
                options_gap = None
        except IssueDeskError:
            options_evidence, options_gap = None, "options_shadow_available_at_missing_or_invalid"
    else:
        options_evidence, options_gap = None, "options_shadow_future_or_unavailable" if matching else "no_matching_options_prophet_row"

    vol, vol_source, vol_source_ok = vol_artifact
    snapshot = vol.get("snapshot") if isinstance(vol, dict) and isinstance(vol.get("snapshot"), Mapping) else None
    vol_evidence = {key: snapshot.get(key) for key in ("asof", "regime", "risk_score", "vix", "ts_slope_state", "vrp_state", "insurance_cost", "vol_target_scalar", "flags", "scored_active")} if snapshot and vol_source_ok else None

    gex, gex_source, gex_source_ok = gex_artifact
    gex_evidence = {key: gex.get(key) for key in ("asof", "root", "spot", "gamma_regime", "gamma_flip", "dist_to_flip_pct", "call_wall", "put_wall", "magnet", "max_pain", "authority_tier")} if isinstance(gex, dict) and gex_source_ok else None
    return [
        {"kind": "options_shadow", "source": options_source, "authority": "display_only" if isinstance(options, dict) and options.get("authority") == "display_only" else "unknown", "evidence": options_evidence, "gap": options_gap},
        {"kind": "vol_regime", "source": vol_source, "authority": "display_context", "evidence": vol_evidence, "gap": None if vol_evidence else "vol_regime_unavailable_or_future"},
        {"kind": "gex_state", "source": gex_source, "authority": "display_context", "evidence": gex_evidence, "gap": None if gex_evidence else "no_symbol_gex_state_or_future"},
    ]


def snapshot_current_proposals(*, repo: Path, reviewer: str, root: Path | None = None, now: datetime | None = None) -> dict[str, Any]:
    now = now or _now()
    root = root or state_dir()
    source, plans = _current_plan_source(repo)
    options_artifact = _read_context_artifact(
        "options_shadow", repo / "site" / "options_prophet" / "index.json", repo=repo, snapshot_at=now
    )
    vol_artifact = _read_context_artifact(
        "vol_regime", repo / "site" / "vol" / "regime.json", repo=repo, snapshot_at=now
    )
    gex_artifacts: dict[str, tuple[dict[str, Any] | None, dict[str, Any], bool]] = {}
    proposals_path, decisions_path, _ = _paths(root)
    handle = _with_lock(root)
    try:
        proposals = _read_jsonl(proposals_path)
        decisions = _read_jsonl(decisions_path)
        folded, _ = _fold(proposals, decisions)
        created = 0
        eligible = [p for p in plans if p.get("closed") is False and str(p.get("direction") or "").upper() == "BULL"]
        for source_rank, plan in enumerate(eligible[:MAX_PROPOSALS], 1):
            plan_id = str(plan.get("id") or "")
            prior = [p for p in folded.values() if (p.get("macro_candidate") or {}).get("id") == plan_id]
            if any(p.get("state") in {"ISSUED", "REJECTED"} for p in prior):
                # A terminal decision is tied to the stable Macro plan ID. A
                # changed artifact must not silently reopen the same thesis.
                continue
            same = [p for p in prior if (p.get("source") or {}).get("sha256") == source["sha256"]]
            if same:
                continue
            revision = max((int(p.get("proposal_revision") or 0) for p in prior), default=0) + 1
            symbol = str(plan.get("asset") or "").upper()
            if symbol not in gex_artifacts:
                gex_artifacts[symbol] = _read_context_artifact(
                    "gex_state",
                    repo / "site" / "options_structure" / "gex_state" / f"{symbol}.json",
                    repo=repo,
                    snapshot_at=now,
                )
            row = _proposal_from_plan(
                plan,
                source=source,
                receipts=_context_receipts(
                    symbol,
                    snapshot_at=now,
                    options_artifact=options_artifact,
                    vol_artifact=vol_artifact,
                    gex_artifact=gex_artifacts[symbol],
                ),
                reviewer=reviewer,
                source_rank=source_rank,
                revision=revision,
                now=now,
            )
            _validate_contract(row, "proposal")
            _append(proposals_path, row)
            folded[f"{row['proposal_id']}:{row['proposal_revision']}"] = row
            created += 1
        return {"created": created, "source": source}
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _validate_issue_receipt(value: object, *, decision_at: datetime, expected_symbol: str) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema") != ISSUE_RECEIPT_SCHEMA:
        raise IssueDeskError("complete operator-attested issue_receipt required; proposal remains pending")
    _validate_contract(value, "receipt")
    underlying = value.get("underlying")
    option = value.get("option")
    if not isinstance(underlying, dict) or not isinstance(option, dict):
        raise IssueDeskError("issue_receipt requires underlying and option objects")
    required_underlying = ("reference", "trigger", "no_chase", "stop", "t1", "t2", "t1_fraction", "t2_fraction", "minimum_hold_days", "horizon_days", "starter_allowed", "add_rule", "invalidation")
    if any(key not in underlying for key in required_underlying):
        raise IssueDeskError("issue_receipt underlying fields are incomplete")
    ref, trigger, no_chase, stop, t1, t2, invalidation = (
        _finite(underlying[key], f"underlying.{key}", positive=True)
        for key in ("reference", "trigger", "no_chase", "stop", "t1", "t2", "invalidation")
    )
    t1_fraction = _finite(underlying["t1_fraction"], "underlying.t1_fraction", positive=True)
    t2_fraction = _finite(underlying["t2_fraction"], "underlying.t2_fraction", positive=True)
    if not (stop < ref <= trigger <= no_chase < t1 < t2 and invalidation <= stop and t1_fraction + t2_fraction <= 1.0):
        raise IssueDeskError("issue_receipt underlying geometry is not a valid BULL research plan")
    minimum_hold_days = underlying["minimum_hold_days"]
    if type(minimum_hold_days) is not int or minimum_hold_days < 1:
        raise IssueDeskError("underlying.minimum_hold_days must be a positive integer")
    if type(underlying["horizon_days"]) is not int or underlying["horizon_days"] < underlying["minimum_hold_days"]:
        raise IssueDeskError("underlying.horizon_days must be an integer at least minimum_hold_days")
    if type(underlying["starter_allowed"]) is not bool or not isinstance(underlying["add_rule"], str) or not underlying["add_rule"].strip():
        raise IssueDeskError("underlying starter/add policy is invalid")
    required_option = ("occ_symbol", "right", "strike", "expiry", "quantity", "premium", "nbbo_bid", "nbbo_ask", "nbbo_mid", "quote_at", "quote_source", "receipt_sha256", "spread", "spread_pct")
    if any(key not in option for key in required_option):
        raise IssueDeskError("issue_receipt option fields are incomplete")
    occ_symbol = str(option["occ_symbol"] or "").strip().upper()
    occ = _OCC.fullmatch(occ_symbol)
    if not occ or option["right"] != "C" or occ.group(3) != option["right"] or occ.group(1) != expected_symbol:
        raise IssueDeskError("option OCC symbol or right is invalid")
    if type(option["quantity"]) is not int or option["quantity"] < 1:
        raise IssueDeskError("option.quantity must be a positive integer")
    strike, premium, bid, ask, mid, spread, spread_pct = (
        _finite(option[key], f"option.{key}", positive=True)
        for key in ("strike", "premium", "nbbo_bid", "nbbo_ask", "nbbo_mid", "spread", "spread_pct")
    )
    quoted_mid = (bid + ask) / 2.0
    if (
        not (bid <= premium <= ask)
        or not math.isclose(mid, quoted_mid, abs_tol=0.0001)
        or not math.isclose(spread, ask - bid, abs_tol=0.0001)
        or not math.isclose(spread_pct, spread / quoted_mid, abs_tol=0.0001)
        or spread_pct > MAX_SPREAD_PCT
    ):
        raise IssueDeskError("option NBBO is unordered or spread disagrees")
    quote_at = _parse_utc(option["quote_at"], "option.quote_at")
    if quote_at > decision_at or decision_at - quote_at > MAX_QUOTE_AGE:
        raise IssueDeskError("option quote is not contemporaneous with the decision")
    try:
        expiry = date.fromisoformat(str(option["expiry"]))
    except ValueError as exc:
        raise IssueDeskError("option.expiry must be YYYY-MM-DD") from exc
    occ_expiry = datetime.strptime(occ.group(2), "%y%m%d").replace(tzinfo=timezone.utc).date()
    if expiry != occ_expiry or not math.isclose(strike, int(occ.group(4)) / 1000, abs_tol=0.0001):
        raise IssueDeskError("option OCC expiry or strike is inconsistent")
    if (
        expiry < decision_at.date() + timedelta(days=minimum_hold_days)
        or not isinstance(option["quote_source"], str)
        or not option["quote_source"].strip()
    ):
        raise IssueDeskError("option expiry or quote source is invalid")
    receipt_sha = str(option["receipt_sha256"] or "")
    risk = value.get("risk")
    if not isinstance(risk, dict):
        raise IssueDeskError("issue_receipt risk receipt is incomplete")
    if set(risk) != {"allocation_weight", "loss_at_stop_weight", "cash_after_weight", "disclosure"}:
        raise IssueDeskError("issue_receipt risk fields are incomplete")
    allocation_weight = _weight(risk["allocation_weight"], "risk.allocation_weight", positive=True)
    loss_at_stop_weight = _weight(risk["loss_at_stop_weight"], "risk.loss_at_stop_weight")
    _weight(risk["cash_after_weight"], "risk.cash_after_weight")
    if allocation_weight > 0.25 or loss_at_stop_weight > allocation_weight or not _SHA.fullmatch(receipt_sha) or not isinstance(risk["disclosure"], str) or not risk["disclosure"].strip():
        raise IssueDeskError("issue_receipt risk receipt is incomplete")
    portfolio_fit = value.get("portfolio_fit")
    if not isinstance(portfolio_fit, dict) or set(portfolio_fit) != {"regime_alignment", "sleeve", "correlation_cluster", "cooldown_clear", "event_risk_clear"}:
        raise IssueDeskError("issue_receipt portfolio_fit is incomplete")
    if portfolio_fit["regime_alignment"] != "ALIGNED" or not all(isinstance(portfolio_fit.get(key), str) and re.fullmatch(r"[A-Za-z0-9_-]{1,32}", portfolio_fit[key]) for key in ("sleeve", "correlation_cluster")) or portfolio_fit.get("cooldown_clear") is not True or portfolio_fit.get("event_risk_clear") is not True:
        raise IssueDeskError("issue_receipt portfolio_fit is invalid")
    return json.loads(json.dumps(value, allow_nan=False))


def _portfolio_state(issued: list[dict[str, Any]]) -> dict[str, Any]:
    allocation = sum(float(((row.get("issue_receipt") or {}).get("risk") or {}).get("allocation_weight") or 0.0) for row in issued)
    return {"allocation_weight": allocation, "cash_weight": max(0.0, 1.0 - allocation), "active_position_count": len(issued)}


def review(*, root: Path | None = None, reviewer: str, proposal_id: str, proposal_revision: int, action: str, reason_codes: list[str], idempotency_key: str, issue_receipt: object, now: datetime | None = None) -> dict[str, Any]:
    if action not in {"approve", "reject"}:
        raise IssueDeskError("action must be approve or reject")
    if type(proposal_revision) is not int or proposal_revision < 1:
        raise IssueDeskError("proposal_revision must be a positive integer")
    if not isinstance(proposal_id, str) or not proposal_id.startswith("oidp_"):
        raise IssueDeskError("proposal_id is invalid")
    if not _IDEMPOTENCY.fullmatch(idempotency_key):
        raise IssueDeskError("idempotency_key must be 16-128 safe characters")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise IssueDeskError("reviewer identity is required")
    _validate_reason_codes(action, reason_codes)
    now = now or _now()
    root = root or state_dir()
    proposals_path, decisions_path, _ = _paths(root)
    try:
        request_digest = _sha256({
            "proposal_id": proposal_id,
            "proposal_revision": proposal_revision,
            "action": action,
            "reason_codes": reason_codes,
            "issue_receipt": issue_receipt,
            "reviewer": reviewer,
        })
    except (TypeError, ValueError) as exc:
        raise IssueDeskError("review request is not strict canonical JSON") from exc
    handle = _with_lock(root)
    try:
        proposals, decisions = _read_jsonl(proposals_path), _read_jsonl(decisions_path)
        folded, applied = _fold(proposals, decisions)
        for row in applied:
            if row.get("idempotency_key") == idempotency_key:
                if row.get("request_sha256") != request_digest:
                    raise ConflictError("idempotency_key was already used for a different request")
                return {"ok": True, "idempotent": True, "decision": row, "state": row.get("next_state"), "capacity": row.get("capacity")}
        proposal = folded.get(f"{proposal_id}:{proposal_revision}")
        if proposal is None:
            raise IssueDeskError("proposal revision is unknown")
        latest_revision = max((int(row.get("proposal_revision") or 0) for row in folded.values() if row.get("proposal_id") == proposal_id), default=0)
        if proposal_revision != latest_revision:
            raise ConflictError("proposal revision is superseded")
        if proposal.get("state") != "PENDING_REVIEW":
            raise ConflictError("proposal is no longer pending review")
        proposal_available_at = _parse_utc(proposal.get("available_at"), "proposal.available_at")
        if now < proposal_available_at:
            raise ConflictError("decision_at cannot precede proposal availability")
        session = _session_for(now)
        recent = set(_rolling_sessions(session))
        all_issued = [row for row in applied if row.get("next_state") == "ISSUED"]
        recent_issued = [row for row in all_issued if row.get("decision_session") in recent]
        capacity = {"max_new_issues": MAX_NEW_ISSUES, "rolling_sessions": sorted(recent), "issued_in_window": len(recent_issued), "remaining": max(0, MAX_NEW_ISSUES - len(recent_issued))}
        frozen_receipt = None
        portfolio_before = _portfolio_state(all_issued)
        portfolio_after = portfolio_before
        next_state = "REJECTED"
        if action == "approve":
            if len(recent_issued) >= MAX_NEW_ISSUES:
                raise ConflictError("rolling three-session issue capacity is exhausted")
            symbol = str((proposal.get("macro_candidate") or {}).get("asset") or "").upper()
            frozen_receipt = _validate_issue_receipt(issue_receipt, decision_at=now, expected_symbol=symbol)
            active_symbols = {str(row.get("proposal_symbol") or "").upper() for row in all_issued}
            if symbol in active_symbols:
                raise ConflictError("an active issued research plan already exists for this symbol")
            fit = frozen_receipt["portfolio_fit"]
            active_fits = [((row.get("issue_receipt") or {}).get("portfolio_fit") or {}) for row in all_issued]
            if sum(item.get("sleeve") == fit["sleeve"] for item in active_fits) >= MAX_ACTIVE_PER_SLEEVE:
                raise ConflictError("portfolio sleeve capacity is exhausted")
            if sum(item.get("correlation_cluster") == fit["correlation_cluster"] for item in active_fits) >= MAX_ACTIVE_PER_CORRELATION_CLUSTER:
                raise ConflictError("portfolio correlation-cluster capacity is exhausted")
            allocation_after = portfolio_before["allocation_weight"] + float(frozen_receipt["risk"]["allocation_weight"])
            cash_after = float(frozen_receipt["risk"]["cash_after_weight"])
            if allocation_after > 1.0 or not math.isclose(cash_after, 1.0 - allocation_after, abs_tol=0.000001):
                raise IssueDeskError("issue_receipt risk cash_after_weight does not reconcile to allocation")
            portfolio_after = {"allocation_weight": allocation_after, "cash_weight": cash_after, "active_position_count": portfolio_before["active_position_count"] + 1}
            next_state = "ISSUED"
            capacity["issued_in_window"] += 1
            capacity["remaining"] -= 1
        row = {
            "schema": DECISION_SCHEMA,
            "decision_id": f"oidd_{uuid.uuid4().hex[:24]}",
            "proposal_id": proposal_id,
            "proposal_revision": proposal_revision,
            "action": action,
            "previous_state": "PENDING_REVIEW",
            "next_state": next_state,
            "reviewer": reviewer,
            "decision_at": _iso(now),
            "available_at": _iso(now),
            "decision_session": session,
            "reason_codes": [code.strip() for code in reason_codes],
            "idempotency_key": idempotency_key,
            "request_sha256": request_digest,
            "proposal_sha256": _sha256(proposal),
            "proposal_symbol": str((proposal.get("macro_candidate") or {}).get("asset") or "").upper(),
            "capacity": capacity,
            "portfolio_state_before": portfolio_before,
            "portfolio_state_after": portfolio_after,
            "issue_receipt": frozen_receipt,
            "event": {"event_type": "ISSUED" if next_state == "ISSUED" else "REJECTED", "post_issue_mutation": False},
            "authority": dict(AUTHORITY),
        }
        _fold(proposals, [*applied, row])
        _append(decisions_path, row)
        return {"ok": True, "idempotent": False, "decision": row, "state": next_state, "capacity": capacity}
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def document(*, repo: Path, reviewer: str, root: Path | None = None, snapshot: bool = True, now: datetime | None = None) -> dict[str, Any]:
    root = root or state_dir()
    now = now or _now()
    snapshot_result = snapshot_current_proposals(repo=repo, reviewer=reviewer, root=root, now=now) if snapshot else {"created": 0}
    proposals_path, decisions_path, _ = _paths(root)
    proposals, decisions = _read_jsonl(proposals_path), _read_jsonl(decisions_path)
    folded, applied = _fold(proposals, decisions)
    session = _session_for(now)
    recent = set(_rolling_sessions(session))
    issued = [row for row in applied if row.get("next_state") == "ISSUED" and row.get("decision_session") in recent]
    latest_ids = {row["proposal_id"]: max(int(item.get("proposal_revision") or 0) for item in folded.values() if item.get("proposal_id") == row["proposal_id"]) for row in folded.values()}
    current = sorted((row for row in folded.values() if int(row.get("proposal_revision") or 0) == latest_ids[row["proposal_id"]]), key=lambda row: (int(row.get("source_rank") or 10**9), row.get("proposal_id", "")))
    decisions_by_id = {str(decision["decision_id"]): decision for decision in applied}
    current_issued = [row for row in current if row.get("state") == "ISSUED"]
    all_issued_decisions = [decision for decision in applied if decision.get("next_state") == "ISSUED"]
    for decision in all_issued_decisions:
        matches = [
            row for row in current_issued
            if row.get("decision_id") == decision.get("decision_id")
            and row.get("proposal_id") == decision.get("proposal_id")
            and row.get("proposal_revision") == decision.get("proposal_revision")
        ]
        if len(matches) != 1:
            raise IssueDeskError("issued decision does not map to exactly one current issued proposal")
    if len(current_issued) != len(all_issued_decisions):
        raise IssueDeskError("current issued proposals do not map one-to-one to issued decisions")
    positions = [
        {
            "position_id": f"oidpos_{hashlib.sha256(str(row.get('decision_id')).encode()).hexdigest()[:24]}",
            "proposal_id": row["proposal_id"], "proposal_revision": row["proposal_revision"],
            "symbol": (row.get("macro_candidate") or {}).get("asset"), "lifecycle_state": "ISSUED",
            "brokerage_trade": False, "issue_receipt": decisions_by_id[str(row["decision_id"])]["issue_receipt"],
            "events": [{
                "event_id": row.get("decision_id"),
                "event_type": "ISSUED",
                "decision_at": row.get("decision_at"),
                "available_at": decisions_by_id[str(row["decision_id"])]["available_at"],
                "reason_codes": decisions_by_id[str(row["decision_id"])]["reason_codes"],
                "reviewer": decisions_by_id[str(row["decision_id"])]["reviewer"],
                "post_issue_mutation": False,
            }],
            "authority": dict(AUTHORITY),
        }
        for row in current_issued
    ]
    if len(positions) != len(all_issued_decisions):
        raise IssueDeskError("issued decision does not map to exactly one position")
    # A document may be read after a proposal/decision was appended by another
    # request. The root receipt must never claim availability before any child
    # evidence it exposes.
    child_clocks = [now]
    for row in [*current, *applied]:
        value = row.get("available_at")
        if isinstance(value, str):
            child_clocks.append(_parse_utc(value, "child.available_at"))
    for position in positions:
        for event in position["events"]:
            value = event.get("available_at")
            if isinstance(value, str):
                child_clocks.append(_parse_utc(value, "position.event.available_at"))
    available_at = max(child_clocks)
    payload = {
        "schema": SCHEMA,
        "authority": dict(AUTHORITY),
        "authority_tier": "operator_reviewed_research_only",
        "mode": "private",
        "as_of": session,
        "built_at": _iso(now),
        "available_at": _iso(available_at),
        "policy": {"max_new_issues": MAX_NEW_ISSUES, "rolling_sessions": ROLLING_SESSIONS, "max_issue_allocation_weight": 0.25, "max_active_per_sleeve": MAX_ACTIVE_PER_SLEEVE, "max_active_per_correlation_cluster": MAX_ACTIVE_PER_CORRELATION_CLUSTER, "zero_is_valid": True, "automatic_authority": False, "post_issue_mutation_v1": False},
        "readiness": {"issuance_requires": "complete_operator_attested_issue_receipt", "current_options_shadow_authority": "display_only", "brokerage_execution": False},
        "proposals": current,
        "decisions": applied,
        "positions": positions,
        "capacity": {"max_new_issues": MAX_NEW_ISSUES, "rolling_sessions": sorted(recent), "issued_in_window": len(issued), "remaining": max(0, MAX_NEW_ISSUES - len(issued))},
        "provenance": {"durable_private_store": True, "snapshot": snapshot_result, "public_r2_mirror": False},
    }
    _validate_contract(payload, "document")
    return payload
