#!/usr/bin/env python3
"""Deterministic, zero-network Agent OS -> Linear desired-state compiler (P0).

The compiler reuses ``scripts.agentos`` for parsing and validation, reads direct
``agentos/workstreams/WS-*.md`` records as authority, and emits
``linear_portfolio_plan.v1``. It never calls a network, carries credentials, writes
Linear, creates issues, or decides whether work may run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from scripts import agentos

PLAN_SCHEMA = "linear_portfolio_plan.v1"
RECEIPT_SCHEMA = "linear_portfolio_plan_receipt.v1"
LINEAR_SNAPSHOT_SCHEMA = "linear_portfolio_snapshot.v1"
GITHUB_SNAPSHOT_SCHEMA = "github_portfolio_snapshot.v1"
ACTIVE = frozenset({"active", "blocked", "awaiting_ci", "awaiting_review"})
CANDIDATE = frozenset({"proposed"})
EXCLUDED = frozenset({"done", "parked", "killed"})
TERMINAL_WAVES = frozenset({"done", "dropped"})
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

    def __init__(self, failures: list[dict[str, str]]) -> None:
        self.failures = tuple(failures)
        super().__init__(f"linear portfolio plan refused: {len(failures)} hard defect(s)")

    def as_dict(self) -> dict[str, Any]:
        return {"schema": PLAN_SCHEMA, "status": "refused", "failures": list(self.failures)}


def clean(value: Any) -> str:
    return "" if value is None else " ".join(str(value).split())


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def semantic_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def source_hash(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
        return None, [{"code": f"{code}_unavailable", "path": path.name if path else None}]
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
                {"code": "generated_state_duplicate_key", "workstream_key": f"WS:{key}"}
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
        if clean(wave.get("next_action")):
            row["next_action"] = clean(wave.get("next_action"))
        out.append(row)
    return out


def gate_observation(rec: Mapping[str, Any]) -> dict[str, Any]:
    needs = rec.get("needs_ceo")
    if not isinstance(needs, dict):
        return {"typed_source": None, "projection": "not_inferred"}
    return {
        "typed_source": "needs_ceo",
        "projection": "observation_only",
        "question": clean(needs.get("question")),
        "recommendation": clean(needs.get("recommendation")),
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
    next_action = clean(rec.get("next_action"))
    source_path = rel(path, root)
    digest = source_hash(path)
    objective = clean(rec.get("objective")) or title
    summary = objective if len(objective) <= 240 else objective[:237].rstrip() + "..."
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
        "gate_observation": gate_observation(rec),
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
    return row, warnings


def linear_drift(
    snapshot: Mapping[str, Any] | None,
    active: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
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
    for key in sorted(desired):
        matches = current.get(key, [])
        if not matches:
            warnings.append(
                {"code": "existing_project_binding_missing", "workstream_key": key}
            )
        elif len(matches) > 1:
            warnings.append(
                {
                    "code": "existing_project_binding_ambiguous",
                    "workstream_key": key,
                    "count": len(matches),
                }
            )
        elif matches[0].get("name") != desired[key]["desired_project_name"]:
            warnings.append(
                {
                    "code": "project_name_drift",
                    "workstream_key": key,
                    "current": matches[0].get("name"),
                    "desired": desired[key]["desired_project_name"],
                }
            )
    for key in sorted(set(current) - set(desired)):
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
        {
            "path": rel(problem.path, store.root),
            "rule": problem.rule,
            "message": problem.message,
        }
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
                        "path": rel(store.paths[f"WS/{key}"], store.root),
                        "rule": "unknown-canonical-status",
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
    warnings.extend(linear_drift(linear, active))
    warnings = sorted(warnings, key=canonical_bytes)

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
