"""Metadata-only R0 monthly-cycle coverage audit for policy-turn-clock research."""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

SCHEMA = "policy_turn_clock.monthly_coverage_audit.r0.v1"
FLOOR = 24
FULL_STACK_FLOOR = 48
FORBIDDEN_OUTPUT_FRAGMENTS = (
    "return", "volatility", "drawdown", "direction", "hit_rate", "effect_size",
    "p_value", "q_value", "model_fit", "threshold", "forecast", "recommendation",
    "trade", "score", "probability", "rank", "gate", "position",
)
FORBIDDEN_INPUT_FRAGMENTS = FORBIDDEN_OUTPUT_FRAGMENTS + (
    "price", "portfolio", "prophet", "backtest",
)
DEFAULT_REQUIREMENTS = {
    "H1": ["opex_calendar", "session_calendar", "options", "treasury"],
    "H2": ["opex_calendar", "options"],
    "H3": ["opex_calendar", "options", "replacement"],
    "H4": ["opex_calendar", "options", "sign_passport"],
    "H5": ["opex_calendar", "relative_performance", "volume_breadth", "broad_flow", "rebalance_pulse"],
    "H6": ["duration_calendar", "duration_study"],
    "H7": ["quarterly_calendar", "migration"],
    "H8": ["vx_calendar", "vx_curve"],
    "H9": ["opex_calendar", "event_identity"],
    "H10": ["opex_calendar", "session_calendar", "options", "treasury", "replacement", "sign_passport", "relative_performance", "volume_breadth", "broad_flow", "rebalance_pulse", "duration_calendar", "duration_study", "quarterly_calendar", "migration", "vx_calendar", "vx_curve", "event_identity"],
}

def _parse_explicit_time(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an explicit timezone-aware timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601 with timezone") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include timezone")
    return parsed.isoformat()

def _has_forbidden_key(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if any(fragment in str(key).lower() for fragment in FORBIDDEN_INPUT_FRAGMENTS):
                return True
            if _has_forbidden_key(child):
                return True
    elif isinstance(value, list):
        return any(_has_forbidden_key(item) for item in value)
    return False

def validate_record(record):
    required = ("owner", "path", "schema", "version", "rights", "observed_at", "available_at", "correction_id", "correction_at", "row_count", "entity_count", "root_count", "cycle_ids", "classification", "missingness")
    missing = [name for name in required if name not in record]
    if missing:
        raise ValueError(f"source passport missing required metadata: {', '.join(missing)}")
    if "mtime" in record:
        raise ValueError("filesystem timestamp is not a decision clock")
    if _has_forbidden_key(record):
        raise ValueError("source passport contains prohibited data-domain field")
    if record["classification"] not in {"historical", "forward_only"}:
        raise ValueError("classification must be historical or forward_only")
    if record["missingness"] not in {"present", "missing", "unknown", "unavailable"}:
        raise ValueError("missingness is not an allowed state")
    _parse_explicit_time(record["observed_at"], "observed_at")
    if record["available_at"] is None and record["missingness"] == "present":
        raise ValueError("present source passport requires available_at")
    if record["available_at"] is not None:
        _parse_explicit_time(record["available_at"], "available_at")
    if record["correction_at"] is not None:
        _parse_explicit_time(record["correction_at"], "correction_at")
    if not isinstance(record["cycle_ids"], list) or not all(isinstance(cycle, str) and len(cycle) == 7 and cycle[4] == "-" for cycle in record["cycle_ids"]):
        raise ValueError("cycle_ids must contain YYYY-MM monthly identifiers")
    return dict(record)

def _era(cycle):
    year = int(cycle[:4])
    if year <= 2004:
        return "pre_weeklies"
    if year <= 2016:
        return "weeklies"
    if year <= 2022:
        return "modern_pre_0DTE"
    return "0DTE_current"

def _source_summary(record):
    cycles = sorted(set(record["cycle_ids"]))
    return {
        "owner": record["owner"], "path": record["path"], "schema": record["schema"], "version": record["version"], "rights": record["rights"],
        "observed_at": record["observed_at"], "available_at": record["available_at"], "correction_id": record["correction_id"], "correction_at": record["correction_at"],
        "row_count": record["row_count"], "entity_count": record["entity_count"], "root_count": record["root_count"], "cycle_count": len(cycles), "first_cycle": cycles[0] if cycles else None,
        "last_cycle": cycles[-1] if cycles else None, "classification": record["classification"], "missingness": record["missingness"],
    }

def _cell(hypothesis, owners, records):
    absent = sorted(owner for owner in owners if owner not in records or records[owner]["missingness"] != "present")
    forward = sorted(owner for owner in owners if owner in records and records[owner]["classification"] == "forward_only")
    base = {"id": hypothesis, "owners": owners, "missing_owners": absent}
    if absent:
        return base | {"availability": "UNAVAILABLE", "cycle_count": None, "cycles_by_era": {}, "reason": "required source passport is absent or not present"}
    if forward:
        return base | {"availability": "UNAVAILABLE", "cycle_count": None, "cycles_by_era": {}, "reason": "forward_only source cannot supply historical monthly coverage"}
    intersection = set(records[owners[0]]["cycle_ids"])
    for owner in owners[1:]:
        intersection &= set(records[owner]["cycle_ids"])
    cycles = sorted(intersection)
    by_era = {era: 0 for era in ("pre_weeklies", "weeklies", "modern_pre_0DTE", "0DTE_current")}
    for cycle in cycles:
        by_era[_era(cycle)] += 1
    floor = FULL_STACK_FLOOR if hypothesis == "H10" else FLOOR
    return base | {"availability": "COVERED" if len(cycles) >= floor else "BELOW_FLOOR", "cycle_count": len(cycles), "cycles_by_era": by_era, "reason": "exact required-source monthly intersection"}

def build_report(records, requirements=None):
    checked = [validate_record(record) for record in records]
    owners = [str(record["owner"]) for record in checked]
    if len(set(owners)) != len(owners):
        raise ValueError("each owner must have one source passport")
    indexed = {str(record["owner"]): record for record in checked}
    required = requirements or DEFAULT_REQUIREMENTS
    report = {
        "schema": SCHEMA, "method": "monthly-cycle-source-coverage-only",
        "sources": sorted((_source_summary(record) for record in checked), key=lambda row: str(row["owner"])),
        "hypotheses": [_cell(identifier, required[identifier], indexed) for identifier in sorted(required)],
    }
    payload = json.dumps(report, sort_keys=True, separators=(",", ":")).lower()
    if any(fragment in payload for fragment in FORBIDDEN_OUTPUT_FRAGMENTS):
        raise ValueError("audit output contains prohibited decision/outcome vocabulary")
    return report

def canonical_digest(report):
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()

def render_markdown(report, digest):
    lines = ["# Policy Turn Clock R0 Monthly Coverage Audit", "", "This is a metadata-only availability audit.", "", f"- Schema: {report['schema']}", f"- Semantic digest: {digest}", "", "## Source passports", "", "| Owner | First cycle | Last cycle | Monthly cycles | Classification | Missingness |", "|---|---|---|---:|---|---|"]
    for source in report["sources"]:
        lines.append(f"| {source['owner']} | {source['first_cycle'] or '—'} | {source['last_cycle'] or '—'} | {source['cycle_count']} | {source['classification']} | {source['missingness']} |")
    lines.extend(["", "## Exact required-source intersections", "", "| Hypothesis | Availability | Monthly cycles | Reason |", "|---|---|---:|---|"])
    for cell in report["hypotheses"]:
        count = "—" if cell["cycle_count"] is None else str(cell["cycle_count"])
        lines.append(f"| {cell['id']} | {cell['availability']} | {count} | {cell['reason']} |")
    lines.extend(["", "No availability count is a decision or outcome.", ""])
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--markdown-out", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    report = build_report(manifest["sources"])
    digest = canonical_digest(report)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report | {"semantic_digest": digest}, indent=2, sort_keys=True) + "\n")
    args.markdown_out.write_text(render_markdown(report, digest))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
