"""PSS-AF1 prospective FINRA short-marked absorption-witness accrual."""

from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from engine import personality_challenge_resilience as cr1
from engine import personality_followon_common as common
from engine.ledger_lane import nightly_advance_enabled

log = logging.getLogger(__name__)

PROGRAM_ID = "PSS-AF1"
FAMILY = "pss_af1_finra_absorption_witness_prospective"
LEDGER_SCHEMA = "personality_flow_absorption.ledger/v1"
STATE_SCHEMA = "personality_flow_absorption.state/v1"
MANIFEST_SCHEMA = "personality_flow_absorption.manifest/v1"
CONSTRUCTION_ID = "pss_af1_finra_short_marked_absorption_witness_v1"

EXPECTED_MANIFEST_SHA256 = (
    "6b9fc71307aca9d97a04eb4933f0fdc3744ae4b7b8d9a23cbd9b178be15aa658"
)
EXPECTED_CONSTRUCTION_SHA256 = (
    "31dafcf5f3606e084f73d120328fd0d0b55e7db7d8f8ae55c112f61062b79634"
)
EXPECTED_MEMBERSHIP_SHA256 = common.RH1_MEMBERSHIP_SHA256
EXPECTED_CR1_MANIFEST_SHA256 = cr1.EXPECTED_MANIFEST_SHA256
NOT_BEFORE_SESSION = common.NOT_BEFORE_SESSION
AUTHORITY = dict(common.AUTHORITY)

FINRA_PREFIX_END = "2026-07-21"
FINRA_PREFIX_ROWS = 51_960
FINRA_PREFIX_SHA256 = (
    "4d7165ff3346c7bdaaf28e0b4064f1eda4311a1600f3df33509e8d03d183bbf6"
)
FINRA_COLUMNS = (
    "date",
    "ticker",
    "short_vol",
    "short_exempt",
    "total_vol",
    "short_ratio",
)
BASELINE_SESSIONS = 20
CHALLENGE_SESSIONS = 3
RATIO_Q = 0.75

PRIMARY_GROUPS = ("flow_witness", "leader_flow_control")
REQUIRED = {
    "matured_primary_rows": 150,
    "unique_names": 100,
    "flow_witness_rows": 40,
    "leader_flow_control_rows": 40,
    "distinct_action_months": 12,
    "action_date_span_days": 365,
    "informative_exact_strata": 12,
}


def manifest_path(root: Path | None = None) -> Path:
    return common.base(root) / "flow_absorption_manifest_v1.json"


def ledger_path(root: Path | None = None) -> Path:
    return common.base(root) / "flow_absorption.jsonl"


def state_path(root: Path | None = None) -> Path:
    return common.base(root) / "flow_absorption_state.json"


def finra_path(root: Path | None = None) -> Path:
    return common.data_root(root) / "finra_short_volume" / "panel.parquet"


def canonical_finra_prefix_bytes(frame: pd.DataFrame) -> bytes:
    prefix = frame.loc[
        pd.to_datetime(frame["date"]).dt.normalize() <= pd.Timestamp(FINRA_PREFIX_END),
        list(FINRA_COLUMNS),
    ].copy()
    prefix["date"] = pd.to_datetime(prefix["date"]).dt.normalize()
    prefix = prefix.sort_values(["date", "ticker"]).reset_index(drop=True)
    lines = []
    for row in prefix.itertuples(index=False):
        lines.append(
            "|".join(
                [
                    str(row.date.date()),
                    str(row.ticker),
                    format(float(row.short_vol), ".12g"),
                    format(float(row.short_exempt), ".12g"),
                    format(float(row.total_vol), ".12g"),
                    format(float(row.short_ratio), ".12g"),
                ]
            )
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _load_finra(root: Path | None, *, through: pd.Timestamp | None = None) -> pd.DataFrame:
    frame = pd.read_parquet(finra_path(root), columns=list(FINRA_COLUMNS))
    if not set(FINRA_COLUMNS) <= set(frame.columns):
        raise ValueError("FINRA schema mismatch")
    frame = frame.copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    frame["ticker"] = frame["ticker"].astype(str)
    if through is not None:
        frame = frame.loc[frame["date"] <= through]
    return (
        frame.drop_duplicates(["date", "ticker"], keep="last")
        .sort_values(["date", "ticker"])
        .reset_index(drop=True)
    )


def load_registration(root: Path | None = None) -> dict[str, Any] | None:
    try:
        registration = common.load_registration(
            root,
            manifest_name=manifest_path(root).name,
            expected_manifest_sha256=EXPECTED_MANIFEST_SHA256,
            manifest_schema=MANIFEST_SCHEMA,
            program_id=PROGRAM_ID,
            family=FAMILY,
            expected_construction_sha256=EXPECTED_CONSTRUCTION_SHA256,
        )
        binding = (
            registration["manifest"].get("source_bindings") or {}
        ).get("finra_stable_prefix") or {}
        cr1_binding = (
            registration["manifest"].get("source_bindings") or {}
        ).get("cr1_manifest") or {}
        if (
            cr1_binding.get("sha256") != EXPECTED_CR1_MANIFEST_SHA256
            or common.sha256_file(cr1.manifest_path(root))
            != EXPECTED_CR1_MANIFEST_SHA256
        ):
            raise ValueError("PSS-CR1 manifest binding mismatch")
        if (
            binding.get("through") != FINRA_PREFIX_END
            or binding.get("row_count") != FINRA_PREFIX_ROWS
            or binding.get("canonical_sha256") != FINRA_PREFIX_SHA256
        ):
            raise ValueError("FINRA prefix binding mismatch")
        panel = _load_finra(root)
        prefix = panel.loc[panel["date"] <= pd.Timestamp(FINRA_PREFIX_END)]
        prefix_hash = hashlib.sha256(canonical_finra_prefix_bytes(panel)).hexdigest()
        if len(prefix) != FINRA_PREFIX_ROWS or prefix_hash != FINRA_PREFIX_SHA256:
            raise ValueError("FINRA stable prefix drift")
        return registration
    except Exception as exc:  # noqa: BLE001 — invalid registration fails inert
        log.warning("personality_flow_absorption: registration rejected (%s)", exc)
        return None


def _load_events(root: Path | None) -> list[dict[str, Any]]:
    return common.read_events(ledger_path(root), schema=LEDGER_SCHEMA, program_id=PROGRAM_ID)


def _source_events(root: Path | None) -> list[dict[str, Any]]:
    rows = common.read_events(
        common.source_path(root, "challenge_resilience.jsonl"),
        schema=cr1.LEDGER_SCHEMA,
        program_id=cr1.PROGRAM_ID,
    )
    return [
        row
        for row in rows
        if row.get("construction_sha256") == cr1.EXPECTED_CONSTRUCTION_SHA256
        and row.get("membership_sha256") == EXPECTED_MEMBERSHIP_SHA256
        and row.get("authority") == AUTHORITY
    ]


def classify_flow(
    panel: pd.DataFrame,
    sym: str,
    baseline_dates: pd.DatetimeIndex,
    challenge_dates: pd.DatetimeIndex,
) -> dict[str, Any]:
    """Apply the exact own-history, exact-date FINRA witness construction."""
    required_dates = pd.DatetimeIndex([*baseline_dates, *challenge_dates]).normalize()
    ticker = panel.loc[panel["ticker"].astype(str) == sym].copy()
    ticker["date"] = pd.to_datetime(ticker["date"]).dt.normalize()
    ticker = ticker.drop_duplicates("date", keep="last").set_index("date")
    available = ticker.reindex(required_dates)
    coverage = available[["short_vol", "total_vol"]].notna().all(axis=1)
    positive_total = available["total_vol"].fillna(0).astype(float) > 0
    missing = int((~(coverage & positive_total)).sum())
    if missing:
        return {
            "group": "missing_flow_diagnostic",
            "missing_required_rows": missing,
            "baseline_rows": int(
                ticker.index.intersection(baseline_dates.normalize()).nunique()
            ),
            "challenge_rows": int(
                ticker.index.intersection(challenge_dates.normalize()).nunique()
            ),
        }

    baseline = available.iloc[:BASELINE_SESSIONS]
    challenge = available.iloc[BASELINE_SESSIONS:]
    rolling_ratios: list[float] = []
    for start in range(BASELINE_SESSIONS - CHALLENGE_SESSIONS + 1):
        window = baseline.iloc[start : start + CHALLENGE_SESSIONS]
        total = float(window["total_vol"].sum())
        rolling_ratios.append(float(window["short_vol"].sum()) / total)
    ratio_q75 = float(np.quantile(rolling_ratios, RATIO_Q, method="linear"))
    challenge_total = float(challenge["total_vol"].sum())
    challenge_ratio = float(challenge["short_vol"].sum()) / challenge_total
    baseline_activity = float(np.median(baseline["total_vol"].to_numpy(dtype=float)))
    challenge_activity = float(np.mean(challenge["total_vol"].to_numpy(dtype=float)))
    activity_ratio = float(challenge_activity / baseline_activity)
    if challenge_activity < baseline_activity:
        group = "low_activity_diagnostic"
    elif challenge_ratio >= ratio_q75:
        group = "flow_witness"
    else:
        group = "leader_flow_control"
    return {
        "group": group,
        "missing_required_rows": 0,
        "baseline_rows": BASELINE_SESSIONS,
        "challenge_rows": CHALLENGE_SESSIONS,
        "prior_rolling_windows": len(rolling_ratios),
        "short_ratio_q75_prior": ratio_q75,
        "challenge_short_ratio": challenge_ratio,
        "baseline_median_total_vol": baseline_activity,
        "challenge_mean_total_vol": challenge_activity,
        "activity_ratio": activity_ratio,
    }


def _scan_sources(
    registration: dict[str, Any],
    root: Path | None,
    through: pd.Timestamp,
    *,
    skip_sources: set[tuple[str, str, str]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    del registration  # hash validation is the only registration dependency here
    skipped = skip_sources or set()
    sources = [
        row
        for row in _source_events(root)
        if row.get("group") == "resilient_leader"
        and str(row.get("action_date") or "") > NOT_BEFORE_SESSION
        and pd.Timestamp(str(row.get("action_date"))) <= through
        and common.upstream_key(row) not in skipped
    ]
    panel = _load_finra(root, through=through)
    reasons: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []

    for source in sources:
        sym = str(source.get("sym") or "")
        frame = common.load_ohlcv(root, sym, through=through)
        if frame is None:
            reasons["missing_subject_ohlcv"] += 1
            continue
        index = pd.DatetimeIndex(frame.index)
        start = common.exact_pos(index, str(source.get("challenge_start") or ""))
        action = common.exact_pos(index, str(source.get("action_date") or ""))
        if start is None or action is None or action - start != CHALLENGE_SESSIONS - 1:
            reasons["invalid_source_challenge_dates"] += 1
            continue
        if start < BASELINE_SESSIONS:
            reasons["insufficient_subject_baseline_sessions"] += 1
            continue
        baseline_dates = index[start - BASELINE_SESSIONS : start]
        challenge_dates = index[start : action + 1]
        result = classify_flow(panel, sym, baseline_dates, challenge_dates)
        action_date = str(source["action_date"])
        if action_date <= NOT_BEFORE_SESSION:
            reasons["pre_cutoff_action"] += 1
            continue
        event = {
            "kind": "event",
            "schema": LEDGER_SCHEMA,
            "program_id": PROGRAM_ID,
            "family": FAMILY,
            "construction_id": CONSTRUCTION_ID,
            "construction_sha256": EXPECTED_CONSTRUCTION_SHA256,
            "membership_sha256": EXPECTED_MEMBERSHIP_SHA256,
            "authority": dict(AUTHORITY),
            "source_program_id": cr1.PROGRAM_ID,
            "source_construction_id": source.get("construction_id"),
            "source_action_date": action_date,
            "sym": sym,
            "sector": str(source["sector"]),
            "anchor_date": str(source["anchor_date"]),
            "formation_confirm": str(source["formation_confirm"]),
            "challenge_start": str(source["challenge_start"]),
            "action_date": action_date,
            "action_close": float(source["action_close"]),
            "atr_anchor": float(source["atr_anchor"]),
            "reference_low": float(source["reference_low"]),
            "anchor_breadth": float(source["anchor_breadth"]),
            "formation_peer_peak": float(source["formation_peer_peak"]),
            "source_delay_sessions": int(source["source_delay_sessions"]),
            "severity_band": str(source["severity_band"]),
            "delay_band": str(source["delay_band"]),
            "challenge_band": str(source["challenge_band"]),
            "source_subject_return_percentile": float(
                source["subject_return_percentile"]
            ),
            "source_subject_relative_return": float(source["subject_relative_return"]),
            "group": str(result["group"]),
            "baseline_start": str(baseline_dates[0].date()),
            "baseline_end": str(baseline_dates[-1].date()),
            "flow_data_as_of": (
                str(panel["date"].max().date()) if not panel.empty else None
            ),
            "grade": None,
            "grade_as_of": None,
        }
        for key, value in result.items():
            if key == "group":
                continue
            if isinstance(value, float):
                event[key] = round(value, 10)
            else:
                event[key] = value
        rows.append(event)
        reasons[f"group_{result['group']}"] += 1

    rows.sort(
        key=lambda row: (
            row["action_date"],
            row["sector"],
            row["sym"],
        )
    )
    return rows, {
        "eligible_future_cr1_leader_sources": len(sources),
        "derived_events": len(rows),
        "finra_rows_through_as_of": len(panel),
        "finra_latest_session": (
            str(panel["date"].max().date()) if not panel.empty else None
        ),
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
        "finra_prefix_sha256": FINRA_PREFIX_SHA256,
        "not_before_session": NOT_BEFORE_SESSION,
        "event_rows_at_launch": 0,
        "authority": dict(AUTHORITY),
    }
    header = (
        f"# PSS-AF1 prospective FINRA-flow witness ledger — schema {LEDGER_SCHEMA}\n"
        "# Source/action date must be strictly after 2026-07-24. No backfill.\n"
        "# Nightly is the sole advancer. Keep-first rows; one 63-session grade.\n"
        "# Short-marked volume is not directional inventory. OPERATOR RESEARCH ONLY.\n"
    )
    body = "\n".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
        for row in [registration, *events]
    )
    common.atomic_write(
        ledger_path(root),
        header + body + "\n",
        prefix=".flow_absorption.",
    )


def _write_state(root: Path | None, state: dict[str, Any]) -> None:
    common.atomic_write(
        state_path(root),
        json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False, default=str)
        + "\n",
        prefix=".flow_absorption_state.",
    )


def update(root: Path | None = None, *, as_of: str | None = None) -> dict | None:
    """Enroll future CR1 leaders with exact-date FINRA context and grade nightly."""
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
            "finra_prefix_sha256": FINRA_PREFIX_SHA256,
            "ledger": {
                "events": len(existing),
                "primary_events": groups[PRIMARY_GROUPS[0]] + groups[PRIMARY_GROUPS[1]],
                "flow_witness": groups["flow_witness"],
                "leader_flow_control": groups["leader_flow_control"],
                "low_activity_diagnostic": groups["low_activity_diagnostic"],
                "missing_flow_diagnostic": groups["missing_flow_diagnostic"],
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
                "Prospective own-history FINRA short-marked activity witness "
                "inside future CR1 leaders. Not directional flow; research only."
            ),
        }
        _write_state(root, state)
        if appended or advanced:
            log.info(
                "personality_flow_absorption: +%d events, +%d grades",
                appended,
                advanced,
            )
        return state
    except Exception as exc:  # noqa: BLE001 — additive lane never breaks engine
        log.warning("personality_flow_absorption update failed (%s)", exc)
        return None
