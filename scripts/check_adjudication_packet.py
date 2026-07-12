"""Adjudication packet validator — check_adjudication_packet.py.

Validates neuralweb.adjudication_packet.v1 packets against the rubrics
defined in config/adjudication_rubrics.yml.  Loads either an adjudication
queue (data/neuralweb/adjudication_queue.json) or a single packet file
(--packet) and runs a set of hard-blocker (HB) and warn (W) rules.

Exit codes
----------
0 : No hard-blocker violations (warns may be present).
1 : One or more HB violations, or selftest failure.

Hard-blocker rules (HB)
-----------------------
HB-1  decision.outcome present AND in blocked_outcomes
HB-2  tier 2 decided without >=2 panel entries with stance=refute AND verdicts
HB-3  tier 2 decided with decided_by != operator
HB-4  decision_class matches an invariant — always block
HB-5  statistics.outcome_data_seen true AND preregistration_ref null
HB-6  statistics.trial_budget_change true AND fdr_family null
HB-7  tier >=1, empty ruling_hits AND empty deferred_or_killed_hits AND duplicate_risk != low
HB-8  missing required fields for its tier
HB-9  missing or unknown decision_class (not in rubrics)
HB-10 packet tier lower than rubric tier for its decision_class (tier laundering)
HB-11 authority floor unmet (RUL-SUCC-10)
HB-12 privacy floor unmet (RUL-SUCC-11)
HB-13 tier field missing while decision_class maps to a known tier

Warn rules (W)
--------------
W-1  undecided packet older than stale_after_days without escalated=true
W-2  duplicate_risk high with empty deferred_or_killed_hits
W-3  decided packet missing rationale
W-4  standout-lobe proposal cites hit_quality sensor without paired coverage sensor

Usage
-----
  python scripts/check_adjudication_packet.py
  python scripts/check_adjudication_packet.py --queue data/neuralweb/adjudication_queue.json
  python scripts/check_adjudication_packet.py --packet /path/to/packet.json
  python scripts/check_adjudication_packet.py --rubrics config/adjudication_rubrics.yml
  python scripts/check_adjudication_packet.py --as-of 2026-07-06
  python scripts/check_adjudication_packet.py --selftest
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent

_DEFAULT_QUEUE = "data/neuralweb/adjudication_queue.json"
_DEFAULT_RUBRICS = "config/adjudication_rubrics.yml"

# ---------------------------------------------------------------------------
# Rubric loading
# ---------------------------------------------------------------------------


def load_rubrics(path: Path) -> dict:
    """Load and parse the rubrics YAML."""
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _build_class_tier_map(rubrics: dict) -> dict[str, int]:
    """Return {decision_class: tier_int} from rubrics decision_classes list."""
    result: dict[str, int] = {}
    for entry in rubrics.get("decision_classes", []):
        cls = entry.get("class")
        tier = entry.get("tier")
        if cls is not None and tier is not None:
            result[cls] = int(tier)
    return result


def _build_invariant_set(rubrics: dict) -> set[str]:
    """Return the set of invariant class names."""
    result: set[str] = set()
    for entry in rubrics.get("invariants", []):
        cls = entry.get("class")
        if cls:
            result.add(cls)
    return result


def _required_fields_for_tier(rubrics: dict, tier: int) -> list[str]:
    """Return required field names for a given tier integer."""
    rf = rubrics.get("required_fields", {})
    if tier == 0:
        return list(rf.get("t0_minimal", []))
    elif tier == 1:
        return list(rf.get("t1", []))
    elif tier == 2:
        return list(rf.get("t2", []))
    return []


# ---------------------------------------------------------------------------
# Packet loading
# ---------------------------------------------------------------------------


def _load_queue(path: Path) -> list[dict]:
    """Load packets from an adjudication queue JSON file."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return list(data.get("packets", []))


def _load_single_packet(path: Path) -> dict:
    """Load a single packet from a JSON or YAML file."""
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yml", ".yaml"):
        return yaml.safe_load(text)
    return json.loads(text)


# ---------------------------------------------------------------------------
# Date helpers — deterministic, no datetime.now()
# ---------------------------------------------------------------------------


def _parse_date_str(s: str | None) -> tuple[int, int, int] | None:
    """Parse YYYY-MM-DD (or ISO-UTC with T) into (year, month, day) tuple."""
    if not s:
        return None
    # Accept YYYY-MM-DDTHH:MM:SSZ or YYYY-MM-DD
    date_part = str(s).split("T")[0].strip()
    parts = date_part.split("-")
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None


def _days_between(earlier: tuple[int, int, int], later: tuple[int, int, int]) -> int:
    """Approximate day delta (good enough for stale check; avoids datetime import)."""
    # Simple julian-day approximation
    def jd(y: int, m: int, d: int) -> int:
        a = (14 - m) // 12
        y2 = y + 4800 - a
        m2 = m + 12 * a - 3
        return d + (153 * m2 + 2) // 5 + 365 * y2 + y2 // 4 - y2 // 100 + y2 // 400 - 32045

    return jd(*later) - jd(*earlier)


# ---------------------------------------------------------------------------
# Core validation
# ---------------------------------------------------------------------------

Finding = dict  # {packet_id, rule, severity, message}


def _get_nested(obj: Any, *keys: str, default: Any = None) -> Any:
    """Safely navigate a nested dict."""
    cur = obj
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, default)
        if cur is None:
            return default
    return cur


def _is_decided(packet: dict) -> bool:
    """True if decision.outcome is non-null and non-empty."""
    outcome = _get_nested(packet, "decision", "outcome")
    return bool(outcome)


def validate_packet(
    packet: dict,
    rubrics: dict,
    class_tier_map: dict[str, int],
    invariant_set: set[str],
    as_of: tuple[int, int, int] | None,
) -> list[Finding]:
    """Run all HB and W rules against a single packet. Return list of findings."""
    findings: list[Finding] = []
    pid = packet.get("packet_id", "<unknown>")

    def hb(rule: str, msg: str) -> None:
        findings.append({"packet_id": pid, "rule": rule, "severity": "HARD", "message": msg})

    def warn(rule: str, msg: str) -> None:
        findings.append({"packet_id": pid, "rule": rule, "severity": "WARN", "message": msg})

    # ── Section-coercion guard ──────────────────────────────────────────────
    # Any top-level section that is present-but-not-a-mapping (e.g. a string
    # or int) would crash downstream rule evaluation with an AttributeError.
    # For each such section: emit HB-8 ("section X is not a mapping") and
    # replace the value in a local shadow dict with {} so all floor/rule
    # checks still run safely and the sweep continues to the next packet.
    _TOP_SECTIONS = (
        "request", "scope", "case_law", "authority", "privacy",
        "statistics", "clocks", "build_collision", "review", "escalation",
        "decision",
    )
    _pkt: dict = dict(packet)  # shadow copy — do not mutate the original
    for _sec in _TOP_SECTIONS:
        if _sec in _pkt and _pkt[_sec] is not None and not isinstance(_pkt[_sec], dict):
            hb(
                "HB-8",
                f"section {_sec!r} is not a mapping (got "
                f"{type(_pkt[_sec]).__name__!r}) — cannot evaluate rules for this section",
            )
            _pkt[_sec] = {}
    # authority.article3_evidence coercion
    _auth_sec = _pkt.get("authority") or {}
    if isinstance(_auth_sec, dict):
        _art3 = _auth_sec.get("article3_evidence")
        if _art3 is not None and not isinstance(_art3, dict):
            hb(
                "HB-8",
                f"section 'authority.article3_evidence' is not a mapping (got "
                f"{type(_art3).__name__!r}) — cannot evaluate authority floor rules",
            )
            # Replace in the shadow copy so downstream reads see an empty dict
            _auth_sec = dict(_auth_sec)
            _auth_sec["article3_evidence"] = {}
            _pkt["authority"] = _auth_sec
    # Use shadow copy for all remaining rule evaluation in this packet
    packet = _pkt

    # ── Extract common fields ───────────────────────────────────────────────
    decision_class = _get_nested(packet, "request", "decision_class")
    packet_tier_raw = packet.get("tier")
    try:
        packet_tier = int(packet_tier_raw) if packet_tier_raw is not None else None
    except (TypeError, ValueError):
        packet_tier = None

    # ── HB-9: missing or unknown decision_class ─────────────────────────────
    if decision_class is None:
        hb("HB-9", "request.decision_class is missing — cannot determine tier or check rules")
        # Without decision_class we cannot proceed with tier-dependent checks
        return findings
    elif decision_class not in class_tier_map and decision_class not in invariant_set:
        hb("HB-9", f"decision_class {decision_class!r} is not registered in rubrics")
        # Can't do tier checks without knowing the class tier; skip HB-10/13
    else:
        # ── HB-4: invariant class ───────────────────────────────────────────
        if decision_class in invariant_set:
            hb("HB-4", f"decision_class {decision_class!r} is an invariant — never approvable")

        # ── HB-13: tier field missing when class maps to a tier ─────────────
        elif decision_class in class_tier_map:
            rubric_tier = class_tier_map[decision_class]
            if packet_tier is None:
                hb(
                    "HB-13",
                    f"tier field missing while decision_class {decision_class!r} maps to "
                    f"tier {rubric_tier} — tier must be declared",
                )

            # ── HB-10: tier laundering ──────────────────────────────────────
            elif packet_tier < rubric_tier:
                hb(
                    "HB-10",
                    f"tier laundering: packet claims tier {packet_tier} but rubrics assign "
                    f"tier {rubric_tier} to decision_class {decision_class!r}",
                )

    # Compute effective_tier: max(declared, expected) so omission/understatement
    # cannot skip tier-scoped checks (M1 requirement).
    rubric_tier_for_class = class_tier_map.get(decision_class)
    if packet_tier is not None and rubric_tier_for_class is not None:
        effective_tier = max(packet_tier, rubric_tier_for_class)
    elif packet_tier is not None:
        effective_tier = packet_tier
    elif rubric_tier_for_class is not None:
        effective_tier = rubric_tier_for_class
    else:
        effective_tier = None

    # ── HB-8: missing required fields ───────────────────────────────────────
    # NOTE: this is presence-only (top-level keys); nested completeness is
    # enforced by HB-11 (authority floor) and HB-12 (privacy floor).
    if effective_tier is not None:
        required = _required_fields_for_tier(rubrics, effective_tier)
        missing = [f for f in required if f not in packet]
        if missing:
            hb("HB-8", f"missing required fields for tier {effective_tier}: {missing}")

    # ── HB-1: outcome in blocked_outcomes ──────────────────────────────────
    outcome = _get_nested(packet, "decision", "outcome")
    blocked = packet.get("blocked_outcomes") or []
    if outcome and blocked and outcome in blocked:
        hb("HB-1", f"decision.outcome {outcome!r} is listed in blocked_outcomes")

    # ── HB-2: tier 2 decided without >=2 panel entries with stance=refute AND verdicts ──
    # Uses effective_tier so an understated declaration cannot skip this check.
    decided = _is_decided(packet)
    if effective_tier == 2 and decided:
        panel = _get_nested(packet, "review", "panel") or []
        with_refute_verdict = [
            p for p in panel
            if isinstance(p, dict)
            and p.get("stance") == "refute"
            and p.get("verdict")
        ]
        if len(with_refute_verdict) < 2:
            hb(
                "HB-2",
                f"tier 2 decided but only {len(with_refute_verdict)} panel member(s) have "
                f"stance='refute' AND a verdict (need >=2); entries with stance!='refute' "
                f"do not count toward the adversarial panel minimum",
            )

    # ── HB-3: tier 2 decided without operator sign-off ─────────────────────
    # Uses effective_tier so an understated declaration cannot skip this check.
    if effective_tier == 2 and decided:
        decided_by = _get_nested(packet, "decision", "decided_by")
        if decided_by != "operator":
            hb(
                "HB-3",
                f"tier 2 decided with decided_by={decided_by!r}; only 'operator' may "
                f"sign a constitutional decision",
            )

    # ── HB-5: outcome_data_seen without preregistration_ref ─────────────────
    ods = _get_nested(packet, "statistics", "outcome_data_seen")
    prereg = _get_nested(packet, "statistics", "preregistration_ref")
    if ods is True and not prereg:
        hb(
            "HB-5",
            "statistics.outcome_data_seen is true but preregistration_ref is null — "
            "post-hoc analysis block",
        )

    # ── HB-6: trial_budget_change without fdr_family ────────────────────────
    tbc = _get_nested(packet, "statistics", "trial_budget_change")
    fdr = _get_nested(packet, "statistics", "fdr_family")
    if tbc is True and not fdr:
        hb(
            "HB-6",
            "statistics.trial_budget_change is true but fdr_family is null",
        )

    # ── HB-7: tier >=1 with no caselaw scan evidence ────────────────────────
    # Uses effective_tier so an understated declaration cannot skip this check.
    if effective_tier is not None and effective_tier >= 1:
        ruling_hits = _get_nested(packet, "case_law", "ruling_hits") or []
        dk_hits = _get_nested(packet, "case_law", "deferred_or_killed_hits") or []
        dup_risk = _get_nested(packet, "case_law", "duplicate_risk") or ""
        if (not ruling_hits) and (not dk_hits) and dup_risk != "low":
            hb(
                "HB-7",
                f"tier {effective_tier} packet has empty ruling_hits and empty "
                f"deferred_or_killed_hits but duplicate_risk is {dup_risk!r} (not 'low') — "
                f"caselaw scan required",
            )

    # ── HB-11: authority floor unmet (RUL-SUCC-10) ──────────────────────────
    # Trigger: ceiling change, non-empty article2_surfaces, or authority_promotion class.
    authority = packet.get("authority") or {}
    auth_current = authority.get("current_ceiling")
    auth_requested = authority.get("requested_ceiling")
    art2_surfaces = authority.get("article2_surfaces_touched") or []
    _auth_floor_triggered = (
        (auth_current is not None and auth_requested is not None and auth_current != auth_requested)
        or bool(art2_surfaces)
        or decision_class == "authority_promotion_above_A2"
    )
    if _auth_floor_triggered:
        article_citation = authority.get("article_citation")
        art3_evidence = authority.get("article3_evidence") or {}
        art3_n = art3_evidence.get("n")
        art3_hits = art3_evidence.get("hits")
        art3_wilson_lb = art3_evidence.get("wilson_lb")
        art3_staleness_days = art3_evidence.get("staleness_days")
        ruling_hits_auth = _get_nested(packet, "case_law", "ruling_hits") or []
        dk_hits_auth = _get_nested(packet, "case_law", "deferred_or_killed_hits") or []
        case_law_present = bool(ruling_hits_auth) or bool(dk_hits_auth)

        missing_auth: list[str] = []
        if not article_citation:
            missing_auth.append("authority.article_citation")
        if art3_n is None:
            missing_auth.append("authority.article3_evidence.n")
        if art3_hits is None:
            missing_auth.append("authority.article3_evidence.hits")
        if art3_wilson_lb is None:
            missing_auth.append("authority.article3_evidence.wilson_lb")
        if art3_staleness_days is None:
            missing_auth.append("authority.article3_evidence.staleness_days")
        if not case_law_present:
            missing_auth.append("case_law scan (ruling_hits or deferred_or_killed_hits)")

        if missing_auth:
            hb(
                "HB-11",
                f"authority floor unmet (RUL-SUCC-10): packet touches authority but "
                f"missing required fields: {missing_auth}",
            )

    # ── HB-12: privacy floor unmet (RUL-SUCC-11) ────────────────────────────
    # Trigger: privacy_class in sensitive set, non-empty private_fields, or sensitive class.
    _PRIVACY_SENSITIVE_CLASSES = frozenset({
        "public_private_boundary", "held_book_fill_schema", "public_write_endpoint"
    })
    _PRIVATE_PRIVACY_CLASSES = frozenset({"host_private", "mastermind_private"})
    privacy = packet.get("privacy") or {}
    privacy_class_val = privacy.get("privacy_class")
    private_fields_val = privacy.get("private_fields") or []
    _priv_floor_triggered = (
        privacy_class_val in _PRIVATE_PRIVACY_CLASSES
        or bool(private_fields_val)
        or decision_class in _PRIVACY_SENSITIVE_CLASSES
    )
    if _priv_floor_triggered:
        missing_priv: list[str] = []
        if "privacy_class" not in privacy or privacy_class_val is None:
            missing_priv.append("privacy.privacy_class")
        if "public_paths_touched" not in privacy:
            missing_priv.append("privacy.public_paths_touched")
        if "private_fields" not in privacy:
            missing_priv.append("privacy.private_fields")
        mastermind_unchanged = privacy.get("mastermind_booleans_unchanged")
        if mastermind_unchanged is not True:
            missing_priv.append("privacy.mastermind_booleans_unchanged (must be true)")

        if missing_priv:
            hb(
                "HB-12",
                f"privacy floor unmet (RUL-SUCC-11): packet touches private data but "
                f"missing required fields: {missing_priv}",
            )

    # ── W-1: stale undecided packet ─────────────────────────────────────────
    if not decided and as_of is not None:
        created_raw = packet.get("created_at") or ""
        created_date = _parse_date_str(created_raw)
        stale_days = rubrics.get("escalation", {}).get("stale_after_days", 14)
        escalated = _get_nested(packet, "escalation", "escalated")
        if created_date and not escalated:
            age = _days_between(created_date, as_of)
            if age > stale_days:
                warn(
                    "W-1",
                    f"undecided packet is {age} days old (stale_after_days={stale_days}) "
                    f"and escalated is not true",
                )

    # ── W-2: high duplicate_risk with empty deferred_or_killed_hits ─────────
    dup_risk_w = _get_nested(packet, "case_law", "duplicate_risk") or ""
    dk_hits_w = _get_nested(packet, "case_law", "deferred_or_killed_hits") or []
    if dup_risk_w == "high" and not dk_hits_w:
        warn(
            "W-2",
            "case_law.duplicate_risk is 'high' but deferred_or_killed_hits is empty — "
            "caselaw may be incomplete",
        )

    # ── W-3: decided packet missing rationale ──────────────────────────────
    if decided:
        rationale = _get_nested(packet, "decision", "rationale")
        if not rationale:
            warn("W-3", "decided packet is missing decision.rationale")

    # ── W-4: standout-lobe precision-only fitness contract (SA-R4) ──────────
    # Fires when a fitness_contract.sensor is 'hit_quality' (precision sensor)
    # on a standout lobe without a paired coverage sensor in the same packet.
    #
    # F4 FIX: auditor proposals carry 'market' not 'lobe'; derive lobe from
    # market when 'lobe' is absent.
    _COVERAGE_SENSORS = frozenset({
        "coverage_health", "missed_mover_rate", "upside_capture",
    })
    _PRECISION_SENSORS = frozenset({"hit_quality"})
    _MARKET_TO_LOBE: dict[str, str] = {
        "us": "site-us-standouts",
        "cn": "site-china-standouts",
    }
    try:
        proposals = packet.get("proposals") or []
        for prop in proposals:
            fc = prop.get("fitness_contract") or {}
            sensor = str(fc.get("sensor") or prop.get("targets_sensor") or "").strip()
            lobe = str(prop.get("lobe") or "").strip()
            # F4: derive lobe from 'market' when 'lobe' is absent
            if not lobe:
                market_val = str(prop.get("market") or "").strip().lower()
                lobe = _MARKET_TO_LOBE.get(market_val, "")
            # Only fire for standout lobes
            if lobe not in ("site-us-standouts", "site-china-standouts"):
                continue
            if sensor in _PRECISION_SENSORS:
                # Check all proposals in this packet for a paired coverage sensor
                has_coverage = any(
                    str(
                        (p.get("fitness_contract") or {}).get("sensor")
                        or p.get("targets_sensor") or ""
                    ).strip() in _COVERAGE_SENSORS
                    for p in proposals
                )
                if not has_coverage:
                    warn(
                        "W-4",
                        f"standout-lobe proposal targets '{sensor}' (precision sensor) "
                        f"without a paired coverage sensor (coverage_health, "
                        f"missed_mover_rate, upside_capture) in the docket — "
                        f"SA-R4 anti-narrowing check requires coverage counter-evidence",
                    )
    except Exception:  # noqa: BLE001
        pass  # NEVER-RAISE: warn rules must not abort the checker

    return findings


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _print_finding(f: Finding) -> None:
    rule = f["rule"]
    pid = f["packet_id"]
    msg = f["message"]
    line = f"[{rule}] packet {pid}: {msg}"
    print(line)
    level = "error" if f["severity"] == "HARD" else "warning"
    print(f"::{level}::{line}")


# ---------------------------------------------------------------------------
# Selftest
# ---------------------------------------------------------------------------

_DRILL_PACKET_TITLE = "Promote cycle-pattern turn hazard into a board rank conditioner"


def _make_clean_t1_packet() -> dict:
    """A well-formed, decided tier 1 packet that should pass all checks."""
    return {
        "schema": "neuralweb.adjudication_packet.v1",
        "packet_id": "adj-2026-07-06-clean-t1",
        "tier": 1,
        "created_at": "2026-07-06T10:00:00Z",
        "created_by": "opus",
        "request": {
            "title": "Add a new display-only metric to the entry dashboard",
            "requested_decision": "scoped_build",
            "decision_class": "scoped_build",
            "source_doc": "research/ENTRY_STACK_AMENDMENT3.md",
            "source_pr": None,
        },
        "scope": {
            "owner_program": "entry_stack_expansion",
            "proposed_classification": "study",
            "touched_artifacts": ["entry_dashboard"],
            "touched_paths": ["engine/entry_stack.py"],
        },
        "case_law": {
            "ruling_hits": ["RUL-7"],
            "duplicate_risk": "low",
            "deferred_or_killed_hits": [],
        },
        "authority": {
            "current_ceiling": "A2",
            "requested_ceiling": "A2",
            "article2_surfaces_touched": [],
            "nondelegable": False,
        },
        "privacy": None,
        "statistics": {
            "fdr_family": "esx_decline_geometry",
            "trial_budget_change": False,
            "evidence_floor_met": True,
            "outcome_data_seen": False,
            "preregistration_ref": None,
        },
        "clocks": {
            "come_back_on": "2026-10-06",
            "due_status": "accruing",
        },
        "build_collision": None,
        "review": None,
        "allowed_outcomes": ["scoped_build"],
        "blocked_outcomes": ["new_lobe_charter"],
        "escalation": {
            "opened_on": "2026-07-06",
            "stale_after_days": 14,
            "escalated": False,
        },
        "decision": {
            "outcome": "scoped_build",
            "decided_by": "opus",
            "actor_ref": "opus-session-001",
            "rationale": "Scoped display build within program; no scored-path change.",
            "decided_on": "2026-07-06",
        },
    }


def _make_drill_packet(tier_override: int | None = None) -> dict:
    """V1 drill: scored_path_behavior_change claimed as tier 1 (laundered)."""
    tier = tier_override if tier_override is not None else 1
    return {
        "schema": "neuralweb.adjudication_packet.v1",
        "packet_id": "adj-2026-07-06-drill-v1",
        "tier": tier,
        "created_at": "2026-07-06T09:00:00Z",
        "created_by": "codex",
        "request": {
            "title": _DRILL_PACKET_TITLE,
            "requested_decision": "scoped_build",
            "decision_class": "scored_path_behavior_change",
            "source_doc": "research/CODEX_MEMO.md",
            "source_pr": None,
        },
        "scope": {
            "owner_program": "entry_stack",
            "proposed_classification": "study",
            "touched_artifacts": ["board_rank"],
            "touched_paths": ["engine/entry_stack.py"],
        },
        "case_law": {
            "ruling_hits": [],
            "duplicate_risk": "low",
            "deferred_or_killed_hits": [],
        },
        "authority": {
            "current_ceiling": "A2",
            "requested_ceiling": "A2",
            "article2_surfaces_touched": ["board_rank"],
            "nondelegable": False,
        },
        "privacy": None,
        "statistics": {
            "fdr_family": "esx_decline_geometry",
            "trial_budget_change": False,
            "evidence_floor_met": True,
            "outcome_data_seen": False,
            "preregistration_ref": None,
        },
        "clocks": {
            "come_back_on": "2026-08-06",
            "due_status": "not_clocked",
        },
        "build_collision": None,
        "review": None,
        "allowed_outcomes": ["scoped_build"],
        "blocked_outcomes": [],
        "escalation": {
            "opened_on": "2026-07-06",
            "stale_after_days": 14,
            "escalated": False,
        },
        "decision": {
            "outcome": "scoped_build",
            "decided_by": "opus",
            "actor_ref": "opus-session-002",
            "rationale": "Approving as scoped build.",
            "decided_on": "2026-07-06",
        },
    }


def _make_t2_packet_with_panel(panel: list, decided_by: str = "operator") -> dict:
    """A tier 2 packet with a configurable panel and decider."""
    return {
        "schema": "neuralweb.adjudication_packet.v1",
        "packet_id": "adj-2026-07-06-t2-panel",
        "tier": 2,
        "created_at": "2026-07-06T08:00:00Z",
        "created_by": "operator",
        "request": {
            "title": "Charter a new Neural Web lobe for macro timing",
            "requested_decision": "new_lobe_charter",
            "decision_class": "new_lobe_charter",
            "source_doc": "research/NW_CODEX_THREE_LOBES.md",
            "source_pr": None,
        },
        "scope": {
            "owner_program": "nw_rails_lobes",
            "proposed_classification": "lobe",
            "touched_artifacts": [],
            "touched_paths": [],
        },
        "case_law": {
            "ruling_hits": ["RUL-SUCC-1"],
            "duplicate_risk": "low",
            "deferred_or_killed_hits": [],
        },
        "authority": {
            "current_ceiling": "A2",
            "requested_ceiling": "A2",
            "article2_surfaces_touched": [],
            "nondelegable": True,
        },
        "privacy": {
            "privacy_class": "public_research",
            "public_paths_touched": [],
            "private_fields": [],
        },
        "statistics": {
            "fdr_family": "macro_tx",
            "trial_budget_change": False,
            "evidence_floor_met": True,
            "outcome_data_seen": False,
            "preregistration_ref": None,
        },
        "clocks": {
            "come_back_on": "2026-10-01",
            "due_status": "accruing",
        },
        "build_collision": {
            "open_prs_touching_paths": [],
            "owner_conflicts": [],
        },
        "review": {
            "required_lenses": ["evidence", "architecture"],
            "opus_findings": [],
            "panel": panel,
        },
        "allowed_outcomes": ["new_lobe_charter"],
        "blocked_outcomes": [],
        "escalation": {
            "opened_on": "2026-07-06",
            "stale_after_days": 14,
            "escalated": False,
        },
        "decision": {
            "outcome": "new_lobe_charter",
            "decided_by": decided_by,
            "actor_ref": "operator",
            "rationale": "Panel cleared; evidence floor met; operator signs off.",
            "decided_on": "2026-07-06",
        },
    }


def _run_selftest(rubrics: dict) -> int:
    """Run all selftest cases. Return 0 on full pass, 1 on any failure."""
    class_tier_map = _build_class_tier_map(rubrics)
    invariant_set = _build_invariant_set(rubrics)
    as_of = (2026, 7, 6)
    all_passed = True

    def check_case(label: str, packet: dict, expected_rules: set[str]) -> bool:
        findings = validate_packet(packet, rubrics, class_tier_map, invariant_set, as_of)
        hard_rules = {f["rule"] for f in findings if f["severity"] == "HARD"}
        missing = expected_rules - hard_rules
        unexpected = hard_rules - expected_rules
        if missing or unexpected:
            print(f"  selftest [FAIL] {label}")
            if missing:
                print(f"    expected HB rules not fired: {sorted(missing)}")
            if unexpected:
                print(f"    unexpected HB rules fired: {sorted(unexpected)}")
            return False
        else:
            print(f"  selftest [PASS] {label}")
            return True

    # Case 1: clean t1 packet — no hard fails
    p1 = _make_clean_t1_packet()
    ok = check_case("clean t1 packet passes", p1, set())
    all_passed = all_passed and ok

    # Case 2: HB-1 — outcome in blocked_outcomes
    p2 = _make_clean_t1_packet()
    p2["decision"]["outcome"] = "new_lobe_charter"
    p2["blocked_outcomes"] = ["new_lobe_charter"]
    ok = check_case("HB-1 outcome in blocked_outcomes", p2, {"HB-1"})
    all_passed = all_passed and ok

    # Case 3: HB-2 — tier 2 decided without panel (no entries at all)
    p3 = _make_t2_packet_with_panel([])
    ok = check_case("HB-2 tier 2 no panel", p3, {"HB-2"})
    all_passed = all_passed and ok

    # Case 3b: HB-2 — tier 2 decided with 2 approve-stance panelists (stance!=refute → don't count)
    p3b = _make_t2_packet_with_panel([
        {"reviewer_ref": "reviewer-a", "stance": "approve", "verdict": "stands", "rationale": "looks good"},
        {"reviewer_ref": "reviewer-b", "stance": "approve", "verdict": "stands", "rationale": "also good"},
    ])
    ok = check_case("HB-2 two approve-stance panelists hard-fails", p3b, {"HB-2"})
    all_passed = all_passed and ok

    # Case 4: HB-4 — invariant class
    p4 = _make_clean_t1_packet()
    p4["request"]["decision_class"] = "article_1_amendment_or_a7_origination"
    # tier is 1 but the class is invariant — HB-4 fires (HB-10 does not because invariants
    # are checked separately and the class has no rubric tier entry)
    ok = check_case("HB-4 invariant class blocks", p4, {"HB-4"})
    all_passed = all_passed and ok

    # Case 5: HB-8 — missing required field for tier 1 (remove 'scope')
    p5 = _make_clean_t1_packet()
    del p5["scope"]
    ok = check_case("HB-8 missing required field", p5, {"HB-8"})
    all_passed = all_passed and ok

    # Case 6: HB-10 — tier laundering (scored_path_behavior_change is t2, claimed as t1).
    # Effective tier is max(1, 2)=2 so HB-2/HB-3 also fire (no panel, opus decider).
    # The drill packet also has article2_surfaces_touched=["board_rank"], triggering HB-11.
    p6 = _make_drill_packet(tier_override=1)
    ok = check_case("HB-10 tier laundering (drill packet tier=1)", p6, {"HB-10", "HB-2", "HB-3", "HB-11"})
    all_passed = all_passed and ok

    # Case 7: drill packet with tier corrected to 2 — HB-2 and HB-3 fire (no panel, opus decider).
    # article2_surfaces_touched=["board_rank"] also triggers HB-11.
    p7 = _make_drill_packet(tier_override=2)
    # Also add required t2 fields so HB-8 doesn't muddy the picture
    p7["privacy"] = {
        "privacy_class": "public_research",
        "public_paths_touched": [],
        "private_fields": [],
    }
    p7["build_collision"] = {"open_prs_touching_paths": [], "owner_conflicts": []}
    p7["review"] = {"required_lenses": [], "opus_findings": [], "panel": []}
    ok = check_case("drill packet tier=2 → HB-2, HB-3, HB-11", p7, {"HB-2", "HB-3", "HB-11"})
    all_passed = all_passed and ok

    # Case 8: HB-9 — unknown decision_class
    p8 = _make_clean_t1_packet()
    p8["request"]["decision_class"] = "totally_made_up_class"
    ok = check_case("HB-9 unknown decision_class", p8, {"HB-9"})
    all_passed = all_passed and ok

    # Case 9: HB-9 — missing decision_class (None)
    p9 = _make_clean_t1_packet()
    p9["request"]["decision_class"] = None
    ok = check_case("HB-9 missing decision_class (None)", p9, {"HB-9"})
    all_passed = all_passed and ok

    # Case 10: HB-13 — known class but tier field absent.
    # HB-8 also fires because "tier" is itself in the t1 required fields list;
    # HB-13 is the more specific blocker, but both are correct and expected.
    p10 = _make_clean_t1_packet()
    del p10["tier"]
    ok = check_case("HB-13 tier field missing for known class", p10, {"HB-13", "HB-8"})
    all_passed = all_passed and ok

    # Case 11: HB-11 — authority-touching packet with empty authority dict
    # Trigger: ceiling change (requested != current)
    p11 = _make_clean_t1_packet()
    p11["authority"] = {
        "current_ceiling": "A2",
        "requested_ceiling": "A3",   # ceiling change → floor triggered
        "article2_surfaces_touched": [],
        "nondelegable": False,
        # No article_citation, no article3_evidence
    }
    ok = check_case("HB-11 authority-touching missing floor fields", p11, {"HB-11"})
    all_passed = all_passed and ok

    # Case 12: HB-12 — privacy-touching packet missing mastermind_booleans_unchanged
    p12 = _make_clean_t1_packet()
    p12["request"]["decision_class"] = "public_private_boundary"
    p12["tier"] = 2
    p12["privacy"] = {
        "privacy_class": "host_private",
        "public_paths_touched": [],
        "private_fields": ["secret_key"],
        # mastermind_booleans_unchanged is absent → floor violation
    }
    p12["build_collision"] = {"open_prs_touching_paths": [], "owner_conflicts": []}
    p12["review"] = {"required_lenses": [], "opus_findings": [], "panel": []}
    ok = check_case("HB-12 privacy floor missing mastermind_booleans_unchanged", p12, {"HB-2", "HB-3", "HB-12"})
    all_passed = all_passed and ok

    print()
    if all_passed:
        print("selftest PASSED — all cases handled correctly")
        return 0
    else:
        print("selftest FAILED — one or more cases did not match expected rules")
        return 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--queue",
        type=Path,
        default=None,
        metavar="PATH",
        help=f"Adjudication queue JSON file (default: {_DEFAULT_QUEUE})",
    )
    ap.add_argument(
        "--packet",
        type=Path,
        default=None,
        metavar="PATH",
        help="Single packet JSON or YAML file to validate",
    )
    ap.add_argument(
        "--rubrics",
        type=Path,
        default=ROOT / _DEFAULT_RUBRICS,
        metavar="PATH",
        help=f"Rubrics YAML file (default: {_DEFAULT_RUBRICS})",
    )
    ap.add_argument(
        "--as-of",
        default=None,
        metavar="YYYY-MM-DD",
        help=(
            "Date for stale computation (YYYY-MM-DD). "
            "Defaults to queue updated_at, then skipped if unavailable."
        ),
    )
    ap.add_argument(
        "--selftest",
        action="store_true",
        help="Run selftest with synthetic packets; exit 0 on pass, 1 on fail",
    )
    args = ap.parse_args()

    # Load rubrics
    rubrics_path = args.rubrics.resolve() if args.rubrics else ROOT / _DEFAULT_RUBRICS
    try:
        rubrics = load_rubrics(rubrics_path)
    except FileNotFoundError:
        print(f"::error::check_adjudication_packet: rubrics file not found: {rubrics_path}")
        return 1

    if args.selftest:
        print("Running adjudication packet validator selftest ...")
        return _run_selftest(rubrics)

    class_tier_map = _build_class_tier_map(rubrics)
    invariant_set = _build_invariant_set(rubrics)

    # Resolve as-of date
    as_of: tuple[int, int, int] | None = None
    if args.as_of:
        as_of = _parse_date_str(args.as_of)

    # Load packets
    packets: list[dict] = []
    if args.packet:
        pkt_path = args.packet.resolve()
        try:
            pkt = _load_single_packet(pkt_path)
        except Exception as exc:
            print(f"::error::check_adjudication_packet: failed to load packet {pkt_path}: {exc}")
            return 1
        packets = [pkt]
    else:
        queue_path = (args.queue or ROOT / _DEFAULT_QUEUE).resolve() if args.queue else ROOT / _DEFAULT_QUEUE
        if not queue_path.exists():
            print(
                f"check_adjudication_packet: queue not found at {queue_path} — "
                f"no packets to validate (OK)"
            )
            return 0
        try:
            raw_queue = json.loads(queue_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"::error::check_adjudication_packet: failed to load queue {queue_path}: {exc}")
            return 1
        # Try to pull updated_at for as-of if not specified
        if as_of is None:
            updated_at = raw_queue.get("updated_at")
            if updated_at:
                as_of = _parse_date_str(updated_at)
        packets = list(raw_queue.get("packets", []))

    if not packets:
        print("check_adjudication_packet: no packets to validate")
        return 0

    all_findings: list[Finding] = []
    for pkt in packets:
        findings = validate_packet(pkt, rubrics, class_tier_map, invariant_set, as_of)
        all_findings.extend(findings)

    hard = [f for f in all_findings if f["severity"] == "HARD"]
    warns = [f for f in all_findings if f["severity"] == "WARN"]

    for f in all_findings:
        _print_finding(f)

    n_pkt = len(packets)
    n_hard = len(hard)
    n_warn = len(warns)

    if n_hard > 0:
        print(
            f"\n::error::check_adjudication_packet: {n_hard} hard-blocker violation(s) "
            f"across {n_pkt} packet(s)"
        )
        return 1

    if n_warn > 0:
        print(
            f"\n::warning::check_adjudication_packet: {n_warn} warning(s) across "
            f"{n_pkt} packet(s)"
        )
    else:
        print(
            f"check_adjudication_packet: OK — {n_pkt} packet(s) validated, "
            f"no violations"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
