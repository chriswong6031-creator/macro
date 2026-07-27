"""PSS-CR1 prospective first-pullback challenge-resilience accrual."""

from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from engine import personality_followon_common as common
from engine import personality_relief_hazard as rh1
from engine.ledger_lane import nightly_advance_enabled

log = logging.getLogger(__name__)

PROGRAM_ID = "PSS-CR1"
FAMILY = "pss_cr1_challenge_resilience_prospective"
LEDGER_SCHEMA = "personality_challenge_resilience.ledger/v1"
STATE_SCHEMA = "personality_challenge_resilience.state/v1"
MANIFEST_SCHEMA = "personality_challenge_resilience.manifest/v1"
CONSTRUCTION_ID = "pss_cr1_first_peer_pullback_resilience_v1"

EXPECTED_MANIFEST_SHA256 = (
    "0b520e60616d60f4c4182e9796bbf4e23cc58279ccf2b0b2d03eb3cec3c352e1"
)
EXPECTED_CONSTRUCTION_SHA256 = (
    "243fde8127390938856b0af6d0797dbed8bcc4f031f7ec630fb0f903bca2394b"
)
EXPECTED_MEMBERSHIP_SHA256 = common.RH1_MEMBERSHIP_SHA256
NOT_BEFORE_SESSION = common.NOT_BEFORE_SESSION
AUTHORITY = dict(common.AUTHORITY)

PEER_MIN = 15
HISTORY_WINDOW = 126
HISTORY_MIN = 63
CHALLENGE_Q = 0.20
SEARCH_FIRST = 5
SEARCH_LAST = 20
LEADER_PERCENTILE = 0.75
RELATIVE_ATR = 0.50
HOLD_ATR = 0.50
BREACH_ATR = 0.50

PRIMARY_GROUPS = ("resilient_leader", "challenged_control")
REQUIRED = {
    "matured_primary_rows": 300,
    "unique_names": 150,
    "resilient_leader_rows": 75,
    "challenged_control_rows": 75,
    "distinct_action_months": 12,
    "action_date_span_days": 365,
    "informative_exact_strata": 20,
}


def manifest_path(root: Path | None = None) -> Path:
    return common.base(root) / "challenge_resilience_manifest_v1.json"


def ledger_path(root: Path | None = None) -> Path:
    return common.base(root) / "challenge_resilience.jsonl"


def state_path(root: Path | None = None) -> Path:
    return common.base(root) / "challenge_resilience_state.json"


def load_registration(root: Path | None = None) -> dict[str, Any] | None:
    try:
        return common.load_registration(
            root,
            manifest_name=manifest_path(root).name,
            expected_manifest_sha256=EXPECTED_MANIFEST_SHA256,
            manifest_schema=MANIFEST_SCHEMA,
            program_id=PROGRAM_ID,
            family=FAMILY,
            expected_construction_sha256=EXPECTED_CONSTRUCTION_SHA256,
        )
    except Exception as exc:  # noqa: BLE001 — invalid registration fails inert
        log.warning("personality_challenge_resilience: registration rejected (%s)", exc)
        return None


def _load_events(root: Path | None) -> list[dict[str, Any]]:
    return common.read_events(ledger_path(root), schema=LEDGER_SCHEMA, program_id=PROGRAM_ID)


def _source_events(root: Path | None) -> list[dict[str, Any]]:
    rows = common.read_events(
        common.source_path(root, "relief_hazard.jsonl"),
        schema=rh1.LEDGER_SCHEMA,
        program_id=rh1.PROGRAM_ID,
    )
    return [
        row
        for row in rows
        if row.get("construction_sha256") == rh1.EXPECTED_CONSTRUCTION_SHA256
        and row.get("membership_sha256") == EXPECTED_MEMBERSHIP_SHA256
        and row.get("authority") == AUTHORITY
    ]


def challenge_band(peer_return: float) -> str:
    if peer_return <= -0.04:
        return "c3"
    if peer_return <= -0.02:
        return "c2"
    return "c1"


def find_challenge(
    subject: pd.DataFrame,
    peer_close: pd.DataFrame,
    source_position: int,
    *,
    atr_anchor: float,
    reference_low: float,
    source_action_close: float,
) -> tuple[dict[str, Any] | None, str]:
    """Find the first fully observed peer challenge and classify subject response."""
    if peer_close.shape[1] < PEER_MIN:
        return None, "too_few_loaded_peers"
    returns3 = peer_close / peer_close.shift(3) - 1.0
    peer_count = returns3.notna().sum(axis=1)
    peer_median = returns3.median(axis=1, skipna=True).where(peer_count >= PEER_MIN)
    history = peer_median.iloc[max(0, source_position - HISTORY_WINDOW) : source_position]
    history = history.dropna().tail(HISTORY_WINDOW)
    if len(history) < HISTORY_MIN:
        return None, "insufficient_prior_challenge_history"
    frozen_q20 = float(np.quantile(history.to_numpy(dtype=float), CHALLENGE_Q))

    search_start = source_position + SEARCH_FIRST
    search_end = min(source_position + SEARCH_LAST, len(subject) - 1)
    if search_start > search_end:
        return None, "awaiting_challenge_window"
    completion: int | None = None
    peer_return = float("nan")
    for position in range(search_start, search_end + 1):
        value = peer_median.iloc[position]
        if pd.isna(value):
            continue
        if float(value) < 0.0 and float(value) <= frozen_q20:
            completion = position
            peer_return = float(value)
            break
    if completion is None:
        reason = (
            "no_challenge_in_complete_window"
            if search_end >= source_position + SEARCH_LAST
            else "awaiting_or_no_challenge_yet"
        )
        return None, reason

    challenge_start = completion - 2
    low = subject["low"].to_numpy(dtype=float)
    close = subject["close"].to_numpy(dtype=float)
    no_breach_window = low[source_position + 1 : completion + 1]
    held_window = close[challenge_start : completion + 1]
    no_breach = bool(
        len(no_breach_window) > 0
        and np.isfinite(no_breach_window).all()
        and float(np.min(no_breach_window))
        >= reference_low - BREACH_ATR * atr_anchor
    )
    held = bool(
        len(held_window) == 3
        and np.isfinite(held_window).all()
        and float(np.min(held_window)) >= reference_low + HOLD_ATR * atr_anchor
    )

    peer_vector = returns3.iloc[completion].dropna().to_numpy(dtype=float)
    if len(peer_vector) < PEER_MIN:
        return None, "too_few_challenge_peers"
    subject_return = float(close[completion] / close[completion - 3] - 1.0)
    percentile = float((np.sum(peer_vector <= subject_return) + 1) / (len(peer_vector) + 1))
    relative_return = float(subject_return - peer_return)
    relative_floor = float(RELATIVE_ATR * atr_anchor / source_action_close)
    leader = bool(
        no_breach
        and held
        and percentile >= LEADER_PERCENTILE
        and relative_return >= relative_floor
    )
    if not no_breach or not held:
        group = "failed_hold_diagnostic"
    elif leader:
        group = "resilient_leader"
    else:
        group = "challenged_control"
    return {
        "completion_position": completion,
        "challenge_start_position": challenge_start,
        "peer_return_3": peer_return,
        "peer_q20_at_source": frozen_q20,
        "peer_count": int(len(peer_vector)),
        "subject_return_3": subject_return,
        "subject_return_percentile": percentile,
        "subject_relative_return": relative_return,
        "subject_relative_floor": relative_floor,
        "no_breach": no_breach,
        "held_recovery": held,
        "group": group,
    }, "ok"


def _scan_sources(
    registration: dict[str, Any],
    root: Path | None,
    through: pd.Timestamp,
    *,
    skip_sources: set[tuple[str, str, str]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    skipped = skip_sources or set()
    sources = [
        row
        for row in _source_events(root)
        if row.get("group") == "relief_hazard"
        and str(row.get("action_date") or "") > NOT_BEFORE_SESSION
        and pd.Timestamp(str(row.get("action_date"))) <= through
        and common.upstream_key(row) not in skipped
    ]
    reasons: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []
    by_sector: dict[str, dict[str, pd.DataFrame]] = {}

    for source in sources:
        sym = str(source.get("sym") or "")
        sector = str(source.get("sector") or "")
        if sector not in by_sector:
            by_sector[sector] = common.sector_ohlcv(
                registration,
                root,
                sector,
                through=through,
            )
        frames = by_sector[sector]
        subject = frames.get(sym)
        if subject is None:
            reasons["missing_subject_ohlcv"] += 1
            continue
        index = pd.DatetimeIndex(subject.index)
        source_position = common.exact_pos(index, str(source.get("action_date") or ""))
        if source_position is None:
            reasons["missing_source_session"] += 1
            continue
        peer_names = sorted(name for name in frames if name != sym)
        peer_close = pd.DataFrame(
            {name: frames[name]["close"].reindex(index) for name in peer_names},
            index=index,
        )
        result, reason = find_challenge(
            subject,
            peer_close,
            source_position,
            atr_anchor=float(source["atr_anchor"]),
            reference_low=float(source["reference_low"]),
            source_action_close=float(source["action_close"]),
        )
        if result is None:
            reasons[reason] += 1
            continue
        completion = int(result["completion_position"])
        challenge_start = int(result["challenge_start_position"])
        action_date = str(index[completion].date())
        # Independent defense: both the source and derived action are prospective.
        if str(source.get("action_date") or "") <= NOT_BEFORE_SESSION:
            reasons["pre_cutoff_source"] += 1
            continue
        if action_date <= NOT_BEFORE_SESSION:
            reasons["pre_cutoff_action"] += 1
            continue
        rows.append(
            {
                "kind": "event",
                "schema": LEDGER_SCHEMA,
                "program_id": PROGRAM_ID,
                "family": FAMILY,
                "construction_id": CONSTRUCTION_ID,
                "construction_sha256": EXPECTED_CONSTRUCTION_SHA256,
                "membership_sha256": EXPECTED_MEMBERSHIP_SHA256,
                "authority": dict(AUTHORITY),
                "source_program_id": rh1.PROGRAM_ID,
                "source_construction_id": source.get("construction_id"),
                "source_action_date": str(source["action_date"]),
                "source_action_close": float(source["action_close"]),
                "sym": sym,
                "sector": sector,
                "anchor_date": str(source["anchor_date"]),
                "formation_confirm": str(source["formation_confirm"]),
                "challenge_start": str(index[challenge_start].date()),
                "action_date": action_date,
                "action_close": float(subject["close"].iloc[completion]),
                "atr_anchor": float(source["atr_anchor"]),
                "reference_low": float(source["reference_low"]),
                "anchor_breadth": float(source["anchor_breadth"]),
                "formation_peer_peak": float(source["formation_peer_peak"]),
                "source_level_min": float(source["level_min"]),
                "source_active_min": float(source["active_min"]),
                "source_delay_sessions": int(source["delay_sessions"]),
                "source_close_depth_atr": float(source["close_depth_atr"]),
                "severity_band": str(source["severity_band"]),
                "delay_band": str(source["delay_band"]),
                "peer_return_3": round(float(result["peer_return_3"]), 10),
                "peer_q20_at_source": round(float(result["peer_q20_at_source"]), 10),
                "challenge_peer_count": int(result["peer_count"]),
                "challenge_band": challenge_band(float(result["peer_return_3"])),
                "subject_return_3": round(float(result["subject_return_3"]), 10),
                "subject_return_percentile": round(
                    float(result["subject_return_percentile"]), 10
                ),
                "subject_relative_return": round(
                    float(result["subject_relative_return"]), 10
                ),
                "subject_relative_floor": float(result["subject_relative_floor"]),
                "no_breach": bool(result["no_breach"]),
                "held_recovery": bool(result["held_recovery"]),
                "group": str(result["group"]),
                "grade": None,
                "grade_as_of": None,
            }
        )
        reasons[f"group_{result['group']}"] += 1

    rows.sort(
        key=lambda row: (
            row["action_date"],
            row["sector"],
            row["sym"],
            row["source_action_date"],
        )
    )
    return rows, {
        "eligible_future_rh1_sources": len(sources),
        "derived_events": len(rows),
        "reasons": dict(sorted(reasons.items())),
    }


def _rewrite_ledger(root: Path | None, events: list[dict[str, Any]]) -> None:
    registration = {
        "kind": "registration",
        "schema": LEDGER_SCHEMA,
        "program_id": PROGRAM_ID,
        "family": FAMILY,
        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "membership_sha256": EXPECTED_MEMBERSHIP_SHA256,
        "construction_sha256": EXPECTED_CONSTRUCTION_SHA256,
        "not_before_session": NOT_BEFORE_SESSION,
        "event_rows_at_launch": 0,
        "authority": dict(AUTHORITY),
    }
    header = (
        f"# PSS-CR1 prospective challenge-resilience ledger — schema {LEDGER_SCHEMA}\n"
        "# Source/action dates must be strictly after 2026-07-24. No backfill.\n"
        "# Nightly is the sole advancer. Keep-first rows; one 63-session grade.\n"
        "# OPERATOR RESEARCH ONLY — no entry/rank/size/gate/alert/display authority.\n"
    )
    body = "\n".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
        for row in [registration, *events]
    )
    common.atomic_write(
        ledger_path(root),
        header + body + "\n",
        prefix=".challenge_resilience.",
    )


def _write_state(root: Path | None, state: dict[str, Any]) -> None:
    common.atomic_write(
        state_path(root),
        json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False, default=str)
        + "\n",
        prefix=".challenge_resilience_state.",
    )


def update(root: Path | None = None, *, as_of: str | None = None) -> dict | None:
    """Enroll post-cutoff challenge responses and advance mature grades nightly."""
    try:
        observed_as_of = as_of or pd.Timestamp.now("UTC").date().isoformat()
        through = pd.Timestamp(observed_as_of)
        gate_open = nightly_advance_enabled()
        registration = load_registration(root)
        existing = _load_events(root)
        appended = advanced = rejected_pre_cutoff = 0
        scan_census: dict[str, Any] = {}

        if gate_open and registration is not None:
            detected, scan_census = _scan_sources(
                registration,
                root,
                through,
                skip_sources={common.source_key(row) for row in existing},
            )
            seen = {common.event_key(row) for row in existing}
            for row in detected:
                if (
                    str(row.get("source_action_date") or "") <= NOT_BEFORE_SESSION
                    or str(row.get("action_date") or "") <= NOT_BEFORE_SESSION
                ):
                    rejected_pre_cutoff += 1
                    continue
                key = common.event_key(row)
                if key in seen:
                    continue
                row["observed_as_of"] = observed_as_of
                row["enrolled_as_of"] = observed_as_of
                row["last_advanced_as_of"] = None
                existing.append(row)
                seen.add(key)
                appended += 1
            for row in existing:
                if row.get("grade") is not None:
                    continue
                frame = common.load_ohlcv(
                    root,
                    str(row.get("sym") or ""),
                    through=through,
                )
                if frame is None:
                    continue
                grade = common.grade_row(frame, row)
                if grade is None:
                    continue
                row["grade"] = grade
                row["grade_as_of"] = observed_as_of
                row["last_advanced_as_of"] = observed_as_of
                advanced += 1

        if gate_open and registration is not None and (appended or advanced):
            existing.sort(
                key=lambda row: (
                    row.get("action_date") or "",
                    row.get("sector") or "",
                    row.get("sym") or "",
                    row.get("source_action_date") or "",
                )
            )
            _rewrite_ledger(root, existing)

        groups = Counter(str(row.get("group")) for row in existing)
        matured = sum(row.get("grade") is not None for row in existing)
        dates = sorted(str(row["action_date"]) for row in existing if row.get("action_date"))
        state = {
            "schema": STATE_SCHEMA,
            "program_id": PROGRAM_ID,
            "family": FAMILY,
            "status": "prospective_accrual_only",
            "authority": dict(AUTHORITY),
            "as_of": observed_as_of,
            "generated_utc": pd.Timestamp.now("UTC").isoformat(),
            "gate_open": gate_open,
            "registration_ok": registration is not None,
            "not_before_session": NOT_BEFORE_SESSION,
            "manifest_sha256": EXPECTED_MANIFEST_SHA256,
            "membership_sha256": EXPECTED_MEMBERSHIP_SHA256,
            "construction_sha256": EXPECTED_CONSTRUCTION_SHA256,
            "ledger": {
                "events": len(existing),
                "primary_events": groups[PRIMARY_GROUPS[0]] + groups[PRIMARY_GROUPS[1]],
                "resilient_leader": groups["resilient_leader"],
                "challenged_control": groups["challenged_control"],
                "failed_hold_diagnostic": groups["failed_hold_diagnostic"],
                "matured": matured,
                "ungraded": len(existing) - matured,
                "appended_today": appended,
                "advanced_today": advanced,
                "rejected_pre_cutoff_today": rejected_pre_cutoff,
                "earliest_action": dates[0] if dates else None,
                "latest_action": dates[-1] if dates else None,
            },
            "scan_census": scan_census,
            "decision_read": common.coverage_state(
                existing,
                primary_groups=PRIMARY_GROUPS,
                required=REQUIRED,
            ),
            "consumers": [],
            "note": (
                "Prospective test of selective leadership during the first real "
                "peer pullback after an RH1 hazard. Operator research only."
            ),
        }
        _write_state(root, state)
        if appended or advanced:
            log.info(
                "personality_challenge_resilience: +%d events, +%d grades",
                appended,
                advanced,
            )
        return state
    except Exception as exc:  # noqa: BLE001 — additive lane never breaks engine
        log.warning("personality_challenge_resilience update failed (%s)", exc)
        return None
