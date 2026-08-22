#!/usr/bin/env python3
"""Deterministic, zero-network Agent OS -> Linear desired-state compiler (P0).

The compiler reuses ``scripts.agentos`` for parsing and validation, reads direct
``agentos/workstreams/WS-*.md`` records as authority, and emits
``linear_portfolio_plan.v1``. It never calls a network, carries credentials, writes
Linear, creates issues, or decides whether work may run.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts import agentos  # noqa: E402

PLAN_SCHEMA = "linear_portfolio_plan.v1"
RECEIPT_SCHEMA = "linear_portfolio_plan_receipt.v1"
LINEAR_SNAPSHOT_SCHEMA = "linear_portfolio_snapshot.v1"
GITHUB_SNAPSHOT_SCHEMA = "github_portfolio_snapshot.v1"

ACTIVE = frozenset({"active", "blocked", "awaiting_ci", "awaiting_review"})
CANDIDATE = frozenset({"proposed"})
EXCLUDED = frozenset({"done", "parked", "killed"})
TERMINAL_WAVES = frozenset({"done", "dropped"})
GATE_EXPECTING_STATUS = frozenset({"blocked", "awaiting_ci", "awaiting_review"})

STATUS_CLASS = {
    "active": "started",
    "blocked": "paused",
    "awaiting_ci": "started",
    "awaiting_review": "started",
    "proposed": "candidate",
    "done": "completed",
    "parked": "paused",
    "killed": "canceled",
}


class PlanError(RuntimeError):
    """Deterministic, machine-readable refusal to emit a green plan."""

    def __init__(self, failures: list[dict[str, Any]]) -> None:
        self.failures = tuple(failures)
        super().__init__(f"linear portfolio plan refused: {len(failures)} hard defect(s)")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": PLAN_SCHEMA,
            "status": "refused",
            "failures": list(self.failures),
        }


def clean(value: Any) -> str:
    """Whitespace-normalized display text for labels/summaries, never source prose."""
    return "" if value is None else " ".join(str(value).split())


def direct_text(value: Any) -> str:
    """Parsed canonical prose with only transport line endings/outer padding normalized."""
    if value is None:
        return ""
    return str(value).replace("\r\n", "\n").replace("\r", "\n").strip()


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def semantic_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _jsonable(value: Any) -> Any:
    """Canonical JSON-safe form of already-validated Agent OS parsed values."""
    if isinstance(value, (_dt.datetime, _dt.date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def normalized_record_bytes(rec: Mapping[str, Any]) -> bytes:
    """Semantic direct-record bytes, stable across YAML mapping-order/format churn.

    Agent OS already owns parsing semantics. Re-serializing the parsed mapping through
    canonical JSON avoids making harmless frontmatter key order or quoting differences
    look like a portfolio change, while preserving ordered lists and the exact normalized
    Markdown body as semantic record content.
    """
    normalized = {
        str(key): _jsonable(value)
        for key, value in rec.items()
        if key != "_body"
    }
    body = str(rec.get("_body") or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized["_body"] = body
    return canonical_bytes(normalized)


def source_hash(rec: Mapping[str, Any]) -> str:
    return hashlib.sha256(normalized_record_bytes(rec)).hexdigest()


def rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve().parent).as_posix()
    except ValueError:
        return path.name


def load_json_witness(
    path: Path | None,
    schema: str,
    code: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if path is None or not path.exists():
        return None, [
            {
                "code": f"{code}_unavailable",
                "path": path.name if path else None,
            }
        ]
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [
            {
                "code": f"{code}_unreadable",
                "path": path.name,
                "error": type(exc).__name__,
            }
        ]
    if not isinstance(doc, dict) or doc.get("schema") != schema:
        return None, [{"code": f"{code}_wrong_schema", "path": path.name}]
    return doc, []


def generated_statuses(
    doc: Mapping[str, Any] | None,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    out: dict[str, str] = {}
    warnings: list[dict[str, Any]] = []
    if doc is None:
        return out, warnings
    rows = doc.get("workstreams")
    if not isinstance(rows, list):
        return out, [{"code": "generated_state_missing_workstreams"}]
    for index, row in enumerate(rows):
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("key"), str)
            or not isinstance(row.get("status"), str)
        ):
            warnings.append({"code": "generated_state_bad_row", "index": index})
            continue
        key = row["key"]
        if key in out:
            warnings.append(
                {
                    "code": "generated_state_duplicate_key",
                    "workstream_key": f"WS:{key}",
                }
            )
            continue
        out[key] = row["status"]
    return out, warnings


def non_done_waves(rec: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for wave in rec.get("waves") or []:
        if not isinstance(wave, dict) or wave.get("status") in TERMINAL_WAVES:
            continue
        row: dict[str, Any] = {
            "id": str(wave.get("id") or ""),
            "title": clean(wave.get("title")),
            "status": wave.get("status"),
            "depends_on": sorted(
                str(item)
                for item in (wave.get("depends_on") or [])
                if isinstance(item, str)
            ),
        }
        raw = wave.get("pr")
        if raw is not None:
            values = raw if isinstance(raw, list) else [raw]
            row["prs"] = sorted(
                int(item) for item in values if str(item).strip().isdigit()
            )
        wave_next = direct_text(wave.get("next_action"))
        if wave_next:
            row["next_action"] = wave_next
        out.append(row)
    return out


def gate_observation(rec: Mapping[str, Any]) -> dict[str, Any]:
    """Project only explicit typed sources; never infer a gate kind from prose."""
    needs = rec.get("needs_ceo")
    if isinstance(needs, dict):
        return {
            "typed_source": "needs_ceo",
            "projection": "observation_only",
            "question": direct_text(needs.get("question")),
            "recommendation": direct_text(needs.get("recommendation")),
        }

    blocked_by = rec.get("blocked_by")
    if isinstance(blocked_by, list) and blocked_by:
        return {
            "typed_source": "blocked_by",
            "projection": "observation_only",
            "causes": [direct_text(item) for item in blocked_by if direct_text(item)],
        }

    for wave in rec.get("waves") or []:
        if isinstance(wave, dict) and wave.get("status") == "awaiting_ci":
            return {
                "typed_source": "wave_status",
                "projection": "observation_only",
                "wave_id": str(wave.get("id") or ""),
                "wave_status": "awaiting_ci",
            }

    return {"typed_source": None, "projection": "not_inferred"}


def _typed_gate_warning(
    key: str,
    status: str,
    observation: Mapping[str, Any],
) -> dict[str, Any] | None:
    if status not in GATE_EXPECTING_STATUS or observation.get("typed_source") is not None:
        return None
    return {
        "code": "typed_gate_source_missing",
        "workstream_key": f"WS:{key}",
        "canonical_status": status,
        "behavior": "not_inferred_from_prose",
    }


def project_row(
    key: str,
    rec: Mapping[str, Any],
    path: Path,
    root: Path,
    generated: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    status = str(rec.get("status"))
    title = clean(rec.get("title"))
    next_action = direct_text(rec.get("next_action"))
    source_path = rel(path, root)
    digest = source_hash(rec)
    objective = clean(rec.get("objective")) or title
    summary = objective if len(objective) <= 240 else objective[:237].rstrip() + "..."
    gate = gate_observation(rec)
    managed = "\n".join(
        [
            "<!-- mastermind-portfolio-projector:managed:v1 -->",
            f"Canonical workstream: `WS:{key}`",
            f"Canonical status: `{status}`",
            f"Source: `{source_path}`",
            f"Source content SHA-256: `{digest}`",
            "",
            "Current canonical next action:",
            next_action or "(none recorded)",
            "<!-- /mastermind-portfolio-projector:managed:v1 -->",
        ]
    )
    row = {
        "workstream_key": f"WS:{key}",
        "title": title,
        "program": clean(rec.get("program")),
        "canonical_status": status,
        "owner": clean(rec.get("owner")),
        "repos": sorted(str(item) for item in (rec.get("repos") or [])),
        "class": rec.get("class"),
        "blast_radius": rec.get("blast_radius"),
        "ambiguity": rec.get("ambiguity"),
        "next_action": next_action,
        "source_path": source_path,
        "source_content_sha256": digest,
        "non_done_waves": non_done_waves(rec),
        "gate_observation": gate,
        "desired_project_name": f"WS:{key} — {title}",
        "desired_project_summary": summary,
        "desired_project_status_class": STATUS_CLASS[status],
        "managed_description_block": managed,
        "projection_warnings": [],
    }
    warnings: list[dict[str, Any]] = []

    if generated is not None and generated != status:
        warning = {
            "code": "generated_state_disagrees_with_direct_record",
            "workstream_key": f"WS:{key}",
            "direct_status": status,
            "generated_status": generated,
        }
        warnings.append(warning)
        row["projection_warnings"].append(warning["code"])

    gate_warning = _typed_gate_warning(key, status, gate)
    if gate_warning is not None:
        warnings.append(gate_warning)
        row["projection_warnings"].append(gate_warning["code"])

    return row, warnings


def _is_workstream_path(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to((root / "workstreams").resolve())
        return True
    except ValueError:
        return False


def _hard_failure(problem: Any, root: Path) -> dict[str, Any]:
    """Normalize Agent OS validator findings into the frozen P0 failure vocabulary."""
    code = "agentos_validation_error"
    if _is_workstream_path(problem.path, root):
        if problem.rule == "duplicate-key":
            code = "duplicate_workstream_key"
        elif problem.rule == "bad-enum" and "'status'" in problem.message:
            code = "unknown_canonical_status"
        else:
            code = "malformed_workstream_record"
    return {
        "code": code,
        "path": rel(problem.path, root),
        "source_rule": problem.rule,
        "message": problem.message,
    }


def _snapshot_status_class(row: Mapping[str, Any]) -> str | None:
    value = row.get("status_class")
    return value if isinstance(value, str) and value else None


def linear_drift(
    snapshot: Mapping[str, Any] | None,
    active: Sequence[Mapping[str, Any]],
    excluded: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Compare an externally normalized read-only Linear project snapshot.

    ``status_class`` is optional for backwards-compatible fixtures. When supplied it
    lets a completed/canceled historical project agree with an excluded canonical
    lifecycle state instead of being misreported as an extra live project.
    """
    if snapshot is None:
        return []
    rows = snapshot.get("projects")
    if not isinstance(rows, list):
        return [{"code": "linear_snapshot_missing_projects"}]

    current: dict[str, list[Mapping[str, Any]]] = {}
    warnings: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("workstream_key"), str):
            warnings.append({"code": "linear_snapshot_bad_project", "index": index})
            continue
        current.setdefault(row["workstream_key"], []).append(row)

    desired = {row["workstream_key"]: row for row in active}
    excluded_by_key = {row["workstream_key"]: row for row in excluded}

    for key in sorted(desired):
        matches = current.get(key, [])
        if not matches:
            warnings.append(
                {"code": "existing_project_binding_missing", "workstream_key": key}
            )
            continue
        if len(matches) > 1:
            warnings.append(
                {
                    "code": "existing_project_binding_ambiguous",
                    "workstream_key": key,
                    "count": len(matches),
                }
            )
            continue

        match = matches[0]
        if match.get("name") != desired[key]["desired_project_name"]:
            warnings.append(
                {
                    "code": "project_name_drift",
                    "workstream_key": key,
                    "current": match.get("name"),
                    "desired": desired[key]["desired_project_name"],
                }
            )
        current_class = _snapshot_status_class(match)
        desired_class = desired[key]["desired_project_status_class"]
        if current_class is not None and current_class != desired_class:
            warnings.append(
                {
                    "code": "project_status_drift",
                    "workstream_key": key,
                    "current": current_class,
                    "desired": desired_class,
                }
            )

    for key in sorted(set(current) - set(desired)):
        matches = current[key]
        excluded_row = excluded_by_key.get(key)
        if len(matches) == 1 and excluded_row is not None:
            current_class = _snapshot_status_class(matches[0])
            desired_class = excluded_row["desired_project_status_class"]
            if current_class is not None:
                if current_class != desired_class:
                    warnings.append(
                        {
                            "code": "project_lifecycle_drift",
                            "workstream_key": key,
                            "current": current_class,
                            "desired": desired_class,
                            "canonical_status": excluded_row["canonical_status"],
                        }
                    )
                continue
        warnings.append({"code": "would_deactivate_or_archive", "workstream_key": key})

    return warnings


def compile_plan(
    store_root: Path,
    *,
    programs: set[str] | None = None,
    generated_state_path: Path | None = None,
    linear_snapshot_path: Path | None = None,
    github_snapshot_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    store = agentos.load_store(store_root, programs)
    hard = [
        _hard_failure(problem, store.root)
        for problem in sorted(
            store.problems,
            key=lambda item: (item.path.as_posix(), item.rule, item.message),
        )
        if problem.hard
    ]
    if hard:
        raise PlanError(hard)

    generated_doc, warnings = load_json_witness(
        generated_state_path,
        agentos.STATE_SCHEMA,
        "generated_state",
    )
    generated, generated_warnings = generated_statuses(generated_doc)
    warnings.extend(generated_warnings)

    linear, linear_warnings = load_json_witness(
        linear_snapshot_path,
        LINEAR_SNAPSHOT_SCHEMA,
        "linear_snapshot",
    )
    warnings.extend(linear_warnings)

    _github, github_warnings = load_json_witness(
        github_snapshot_path,
        GITHUB_SNAPSHOT_SCHEMA,
        "github_snapshot",
    )
    warnings.extend(github_warnings)

    active: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    workstreams = store.of_type("WS")

    for key in sorted(workstreams):
        rec = workstreams[key]
        status = rec.get("status")
        if status not in ACTIVE | CANDIDATE | EXCLUDED:
            raise PlanError(
                [
                    {
                        "code": "unknown_canonical_status",
                        "path": rel(store.paths[f"WS/{key}"], store.root),
                        "source_rule": "projector-status-law",
                        "message": f"status {status!r} has no {PLAN_SCHEMA} ruling",
                    }
                ]
            )

        row, row_warnings = project_row(
            key,
            rec,
            store.paths[f"WS/{key}"],
            store.root,
            generated.get(key),
        )
        warnings.extend(row_warnings)

        if status in ACTIVE:
            active.append(row)
        elif status in CANDIDATE:
            candidates.append(row)
            warnings.append(
                {"code": "proposed_requires_review", "workstream_key": f"WS:{key}"}
            )
        else:
            excluded.append(
                {
                    "workstream_key": f"WS:{key}",
                    "title": row["title"],
                    "canonical_status": status,
                    "source_path": row["source_path"],
                    "source_content_sha256": row["source_content_sha256"],
                    "desired_project_status_class": row["desired_project_status_class"],
                    "reason": f"canonical_status_{status}",
                }
            )

    if generated_doc is not None:
        direct = set(workstreams)
        warnings.extend(
            {
                "code": "generated_state_unknown_workstream",
                "workstream_key": f"WS:{key}",
            }
            for key in sorted(set(generated) - direct)
        )
        warnings.extend(
            {
                "code": "generated_state_missing_workstream",
                "workstream_key": f"WS:{key}",
            }
            for key in sorted(direct - set(generated))
        )

    warnings.extend(linear_drift(linear, active, excluded))
    warnings = sorted(warnings, key=canonical_bytes)
    warning_counts = dict(sorted(Counter(row["code"] for row in warnings).items()))

    semantic: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "active_projects": active,
        "review_candidates": candidates,
        "excluded_projects": excluded,
        "warnings": warnings,
        "summary": {
            "active_projects": len(active),
            "review_candidates": len(candidates),
            "excluded_projects": len(excluded),
            "warnings": len(warnings),
            "warning_counts": warning_counts,
            "canonical_status_counts": {
                status: sum(
                    1 for rec in workstreams.values() if rec.get("status") == status
                )
                for status in sorted(agentos.WORKSTREAM_STATUS)
            },
        },
    }
    digest = hashlib.sha256(canonical_bytes(semantic)).hexdigest()
    plan = {**semantic, "semantic_hash": digest}
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "status": "compiled",
        "semantic_hash": digest,
        "record_counts": dict(sorted(store.counts.items())),
        "validator_warning_count": sum(
            1 for problem in store.problems if not problem.hard
        ),
        "warning_counts": warning_counts,
        "generated_state_supplied": generated_state_path is not None,
        "linear_snapshot_supplied": linear_snapshot_path is not None,
        "github_snapshot_supplied": github_snapshot_path is not None,
    }
    return plan, receipt


def markdown_report(plan: Mapping[str, Any]) -> str:
    summary = plan["summary"]
    lines = [
        "# Linear portfolio desired-state report",
        "",
        f"Schema: `{PLAN_SCHEMA}`",
        f"Semantic hash: `{plan['semantic_hash']}`",
        "",
        "## Summary",
        "",
        f"- Active desired projects: {summary['active_projects']}",
        f"- Review candidates: {summary['review_candidates']}",
        f"- Excluded workstreams: {summary['excluded_projects']}",
        f"- Warnings: {summary['warnings']}",
        "",
        "## Active desired projects",
        "",
    ]
    lines.extend(
        f"- `{row['workstream_key']}` — `{row['canonical_status']}` — {row['title']}"
        for row in plan["active_projects"]
    )
    lines.extend(["", "## Review candidates", ""])
    lines.extend(
        [
            f"- `{row['workstream_key']}` — {row['title']}"
            for row in plan["review_candidates"]
        ]
        or ["- None"]
    )
    lines.extend(["", "## Excluded", ""])
    lines.extend(
        f"- `{row['workstream_key']}` — `{row['canonical_status']}` — {row['title']}"
        for row in plan["excluded_projects"]
    )
    lines.extend(["", "## Warnings", ""])
    lines.extend(
        [
            f"- `{row['code']}` — "
            + json.dumps(
                {key: value for key, value in row.items() if key != "code"},
                ensure_ascii=False,
                sort_keys=True,
            )
            for row in plan["warnings"]
        ]
        or ["- None"]
    )
    return "\n".join(lines) + "\n"


def write(path: str | None, text: str) -> None:
    if path in (None, "-"):
        sys.stdout.write(text)
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(agentos._DEFAULT_STORE))
    parser.add_argument("--generated-state", default=str(agentos._STATE_JSON))
    parser.add_argument("--linear-snapshot")
    parser.add_argument("--github-snapshot")
    parser.add_argument("--json-output", default="-")
    parser.add_argument("--report-output")
    parser.add_argument("--receipt-output")
    args = parser.parse_args(argv)

    try:
        plan, receipt = compile_plan(
            Path(args.root),
            programs=agentos._load_programs(),
            generated_state_path=Path(args.generated_state) if args.generated_state else None,
            linear_snapshot_path=Path(args.linear_snapshot) if args.linear_snapshot else None,
            github_snapshot_path=Path(args.github_snapshot) if args.github_snapshot else None,
        )
    except PlanError as exc:
        sys.stderr.write(
            json.dumps(exc.as_dict(), ensure_ascii=False, sort_keys=True, indent=2)
            + "\n"
        )
        return 2

    write(args.json_output, semantic_json(plan))
    if args.report_output:
        write(args.report_output, markdown_report(plan))
    if args.receipt_output:
        write(args.receipt_output, semantic_json(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
