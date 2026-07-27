"""PSS-CD1 prospective correlation-one / low-dispersion hazard accrual."""

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

PROGRAM_ID = "PSS-CD1"
FAMILY = "pss_cd1_correlation_dispersion_prospective"
LEDGER_SCHEMA = "personality_crowding_hazard.ledger/v1"
STATE_SCHEMA = "personality_crowding_hazard.state/v1"
MANIFEST_SCHEMA = "personality_crowding_hazard.manifest/v1"
CONSTRUCTION_ID = "pss_cd1_peer_factor_crowding_v1"

EXPECTED_MANIFEST_SHA256 = (
    "4bb7383cc48dfc11a92061a778225107490971213b5f29abb70ae573ceeaf242"
)
EXPECTED_CONSTRUCTION_SHA256 = (
    "4b956ab36a3ddf00f4b67708e8b716abd8cf2b3bad86698e83dc46f705d3920f"
)
EXPECTED_MEMBERSHIP_SHA256 = common.RH1_MEMBERSHIP_SHA256
NOT_BEFORE_SESSION = common.NOT_BEFORE_SESSION
AUTHORITY = dict(common.AUTHORITY)

PEER_MIN = 15
RETURN_SESSIONS = 10
DISPERSION_RETURN_SESSIONS = 5
HISTORY_WINDOW = 126
HISTORY_MIN = 63
PC1_Q = 0.80
DISPERSION_Q = 0.20

PRIMARY_GROUPS = ("crowding_hazard", "uncrowded_control")
REQUIRED = {
    "matured_primary_rows": 250,
    "unique_names": 125,
    "crowding_hazard_rows": 50,
    "uncrowded_control_rows": 50,
    "distinct_action_months": 12,
    "action_date_span_days": 365,
    "informative_exact_strata": 20,
}


def manifest_path(root: Path | None = None) -> Path:
    return common.base(root) / "crowding_hazard_manifest_v1.json"


def ledger_path(root: Path | None = None) -> Path:
    return common.base(root) / "crowding_hazard.jsonl"


def state_path(root: Path | None = None) -> Path:
    return common.base(root) / "crowding_hazard_state.json"


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
        log.warning("personality_crowding_hazard: registration rejected (%s)", exc)
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


def factor_metrics(peer_close: pd.DataFrame, position: int) -> dict[str, float] | None:
    """Return the exact common-factor share and cross-sectional dispersion."""
    if position < RETURN_SESSIONS:
        return None
    daily = peer_close.pct_change(fill_method=None)
    window = daily.iloc[
        position - RETURN_SESSIONS + 1 : position + 1
    ].astype(float)
    five = peer_close.iloc[position] / peer_close.iloc[
        position - DISPERSION_RETURN_SESSIONS
    ] - 1.0
    valid = [
        column
        for column in peer_close.columns
        if window[column].notna().all()
        and np.isfinite(window[column].to_numpy(dtype=float)).all()
        and pd.notna(five[column])
        and np.isfinite(float(five[column]))
    ]
    if len(valid) < PEER_MIN:
        return None
    matrix = window[valid].to_numpy(dtype=float)
    sigma = np.std(matrix, axis=0, ddof=0)
    nonconstant = sigma > 1e-12
    if int(np.sum(nonconstant)) < PEER_MIN:
        return None
    matrix = matrix[:, nonconstant]
    matrix = (matrix - np.mean(matrix, axis=0)) / np.std(matrix, axis=0, ddof=0)
    singular = np.linalg.svd(matrix, full_matrices=False, compute_uv=False)
    energy = float(np.sum(np.square(singular)))
    if not np.isfinite(energy) or energy <= 0:
        return None
    pc1_share = float(singular[0] ** 2 / energy)
    five_values = five.loc[np.asarray(valid)[nonconstant]].to_numpy(dtype=float)
    center = float(np.median(five_values))
    dispersion = float(np.median(np.abs(five_values - center)))
    return {
        "pc1_share": pc1_share,
        "dispersion_5": dispersion,
        "peer_count": int(len(five_values)),
    }


def classify_crowding(
    peer_close: pd.DataFrame,
    source_position: int,
) -> tuple[dict[str, Any] | None, str]:
    """Classify B using only current metrics and thresholds frozen through B-1."""
    history: list[dict[str, float]] = []
    start = max(RETURN_SESSIONS, source_position - HISTORY_WINDOW)
    for position in range(start, source_position):
        metrics = factor_metrics(peer_close, position)
        if metrics is not None:
            history.append(metrics)
    history = history[-HISTORY_WINDOW:]
    if len(history) < HISTORY_MIN:
        return None, "insufficient_prior_metric_history"
    current = factor_metrics(peer_close, source_position)
    if current is None:
        return None, "current_metrics_unavailable"
    pc1_q80 = float(np.quantile([row["pc1_share"] for row in history], PC1_Q))
    dispersion_q20 = float(
        np.quantile([row["dispersion_5"] for row in history], DISPERSION_Q)
    )
    high_pc1 = bool(current["pc1_share"] >= pc1_q80)
    low_dispersion = bool(current["dispersion_5"] <= dispersion_q20)
    if high_pc1 and low_dispersion:
        group = "crowding_hazard"
    elif not high_pc1 and not low_dispersion:
        group = "uncrowded_control"
    else:
        group = "mixed_diagnostic"
    return {
        **current,
        "pc1_q80_prior": pc1_q80,
        "dispersion_q20_prior": dispersion_q20,
        "prior_metric_sessions": len(history),
        "high_pc1": high_pc1,
        "low_dispersion": low_dispersion,
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
        peer_close = pd.DataFrame(
            {
                name: frame["close"].reindex(index)
                for name, frame in sorted(frames.items())
                if name != sym
            },
            index=index,
        )
        result, reason = classify_crowding(peer_close, source_position)
        if result is None:
            reasons[reason] += 1
            continue
        action_date = str(source["action_date"])
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
                "source_action_date": action_date,
                "sym": sym,
                "sector": sector,
                "anchor_date": str(source["anchor_date"]),
                "formation_confirm": str(source["formation_confirm"]),
                "action_date": action_date,
                "action_close": float(source["action_close"]),
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
                "pc1_share": round(float(result["pc1_share"]), 10),
                "pc1_q80_prior": round(float(result["pc1_q80_prior"]), 10),
                "dispersion_5": round(float(result["dispersion_5"]), 10),
                "dispersion_q20_prior": round(
                    float(result["dispersion_q20_prior"]), 10
                ),
                "peer_count": int(result["peer_count"]),
                "prior_metric_sessions": int(result["prior_metric_sessions"]),
                "high_pc1": bool(result["high_pc1"]),
                "low_dispersion": bool(result["low_dispersion"]),
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
        f"# PSS-CD1 prospective crowding-hazard ledger — schema {LEDGER_SCHEMA}\n"
        "# Source/action date must be strictly after 2026-07-24. No backfill.\n"
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
        prefix=".crowding_hazard.",
    )


def _write_state(root: Path | None, state: dict[str, Any]) -> None:
    common.atomic_write(
        state_path(root),
        json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False, default=str)
        + "\n",
        prefix=".crowding_hazard_state.",
    )


def update(root: Path | None = None, *, as_of: str | None = None) -> dict | None:
    """Enroll future RH1 crowding states and advance mature grades nightly."""
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
                "crowding_hazard": groups["crowding_hazard"],
                "uncrowded_control": groups["uncrowded_control"],
                "mixed_diagnostic": groups["mixed_diagnostic"],
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
                "Prospective common-factor concentration plus low-dispersion "
                "overlay inside future RH1 hazards. Operator research only."
            ),
        }
        _write_state(root, state)
        if appended or advanced:
            log.info(
                "personality_crowding_hazard: +%d events, +%d grades",
                appended,
                advanced,
            )
        return state
    except Exception as exc:  # noqa: BLE001 — additive lane never breaks engine
        log.warning("personality_crowding_hazard update failed (%s)", exc)
        return None
