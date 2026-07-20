#!/usr/bin/env python3
"""
CXI-2 eval harness — runs all 104 benchmark rows against the REAL indexes.

Usage:
  python3 scripts/context_index_eval.py
  python3 scripts/context_index_eval.py --include-private
  python3 scripts/context_index_eval.py --output research/context_index/BENCHMARK_RESULTS.md

Grading (per README v1.5, CXI-R17):
  - A row PASSES Recall@10 when every required_source appears in the top-10 result
    source paths (match on path OR source_uri, tolerate repo:// prefix differences).
  - no_answer rows pass when packet.no_answer_reason is set OR zero results.
  - required_status binds ONLY to verdict-carrying registry sources
    (DO_NOT_REBUILD.md, ruling_graph.yml, compiled_kill_registry.yml) among the
    required sources; all other required sources are graded on presence alone —
    an active masterplan cannot carry the kill status (CXI-R17a).
  - required_status: superseded rows are presence-only — the one-status-per-chunk
    model cannot label a still-live ruling row whose sub-clause was struck (CXI-R17c).
  - Cross-repo rows (CTX-082..096) require --include-private.

Gates reported (PASS/FAIL/NOT-MET):
  - Global Recall@10 >= 90%
  - adjudication_replay family >= 90%
  - Governance A0/A1 precision >= 95%

Output: research/context_index/BENCHMARK_RESULTS.md (NEVER chunk text excerpts).

ABSOLUTE RULE: this script writes ONLY to research/context_index/BENCHMARK_RESULTS.md.
Never writes to data/, site/, .context-index.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from engine.context_index.packet import build_packet, TOKEN_BUDGET_DEFAULT
from engine.context_index.gitinfo import repo_sha, index_sha

_BENCHMARK_PATH = _REPO_ROOT / "research" / "context_index" / "BENCHMARK_QUESTIONS.jsonl"
_RESULTS_PATH = _REPO_ROOT / "research" / "context_index" / "BENCHMARK_RESULTS.md"
_DB_DIR_ENV = "MACRO_CONTEXT_INDEX_DIR"
_DB_DIR = _REPO_ROOT / ".context-index"

_PROJECT_DB_MAP: dict[str, str] = {
    "macro-dashboard": "shared.sqlite",
    "terminal": "terminal.sqlite",
    "mastermind": "mastermind.sqlite",
}
_REPO_ROOT_MAP = {
    "macro-dashboard": _REPO_ROOT,
    "terminal": Path("~/Documents/Cluade/charting-app").expanduser(),
    "mastermind": Path("~/Documents/Cluade/Mastermind").expanduser(),
}

# Governance authority classes
_GOV_AUTH = {"A0", "A1"}


def get_db_dir() -> Path:
    env = os.environ.get(_DB_DIR_ENV, "").strip()
    return Path(env) if env else _DB_DIR


def load_questions() -> list[dict]:
    questions = []
    with _BENCHMARK_PATH.open() as f:
        for line in f:
            line = line.strip()
            if line:
                questions.append(json.loads(line))
    return questions


def _path_match(result_path: str, result_source_uri: str, required_source: str) -> bool:
    """
    Returns True if required_source matches the result by path or source_uri.
    Handles repo:// prefix differences and memory:// URIs.
    """
    req = required_source.strip()

    # memory:// sources: match against document_id or path patterns
    if req.startswith("memory://"):
        mem_name = req[len("memory://"):]
        # Match locator containing the memory filename
        return mem_name in result_path or mem_name in result_source_uri

    # repo:// scheme
    result_bare = result_path
    if result_source_uri.startswith("repo://"):
        result_bare = result_source_uri[len("repo://"):]

    # required_source may be bare path or repo://...
    req_bare = req
    if req.startswith("repo://"):
        req_bare = req[len("repo://"):]
    # Strip leading project-key prefix if present (e.g. "terminal/foo" -> "foo")
    # when the project is already scoped

    # Require path-boundary match: exact equality, or result ends with "/"+req_bare
    # (prevents "engine/x.py" from matching "engine/x.py.bak")
    return result_bare == req_bare or result_bare.endswith("/" + req_bare)


def grade_row(row: dict, packet: dict) -> dict:
    """
    Grade a single benchmark row against a packet.
    Returns {pass, miss_sources, notes}
    """
    required = row.get("required_sources", [])
    req_status = row.get("required_status")
    is_no_answer = req_status == "no_answer"

    results = packet.get("results", [])
    top10 = results[:10]

    # Retrieval exceptions are failures, not honest no_answers
    if packet.get("error"):
        return {
            "pass": False,
            "miss_sources": [],
            "notes": f"ERROR during retrieval: {packet['error']}",
        }

    if is_no_answer:
        # Pass only if no_answer_reason was set by the retrieval path (not by exception)
        # and no results were returned
        passed = bool(packet.get("no_answer_reason")) or len(results) == 0
        return {
            "pass": passed,
            "miss_sources": [],
            "notes": "no_answer: " + ("correct null" if passed else f"returned {len(results)} results; expected honest null"),
        }

    # For each required source, check if it appears in top-10.
    # Status check (CXI-R17a, README v1.4): required_status applies ONLY to
    # registry/verdict sources (DO_NOT_REBUILD.md, ruling_graph, compiled_kill_registry).
    # Active docs required alongside a verdict source are checked for presence only —
    # they are expected to have status="active" which differs from "killed"/"forbidden".
    # Superseded rows (CXI-R17c) are presence-only: the amended registry row keeps its
    # live status (e.g. forbidden) while recording the struck sub-clause in its text.
    _VERDICT_PATHS = {
        "research/DO_NOT_REBUILD.md",
        "config/ruling_graph.yml",
        "config/compiled_kill_registry.yml",
    }

    def _is_verdict_source(src: str) -> bool:
        src_bare = src
        if src_bare.startswith("repo://"):
            src_bare = src_bare[len("repo://"):]
        for vp in _VERDICT_PATHS:
            if src_bare == vp or src_bare.endswith("/" + vp) or vp in src_bare:
                return True
        return False

    miss_sources = []
    for req_src in required:
        matched_in_top10 = [
            r for r in top10
            if _path_match(r.get("path", ""), r.get("source_uri", ""), req_src)
        ]
        if not matched_in_top10:
            miss_sources.append(req_src)
            continue

        # Status check only for verdict/registry sources; superseded rows presence-only
        if req_status and req_status not in ("no_answer", "superseded") and _is_verdict_source(req_src):
            status_ok = any(r.get("status") == req_status for r in matched_in_top10)
            if not status_ok:
                miss_sources.append(req_src)
        # Non-verdict sources: presence in top-10 is sufficient

    return {
        "pass": len(miss_sources) == 0,
        "miss_sources": miss_sources,
        "notes": "",
    }


def compute_governance_precision(rows: list[dict], results_by_id: dict[str, dict]) -> tuple[float, int, int]:
    """
    Governance A0/A1 row-recall: fraction of governance-family rows that pass.
    Population is strictly governance-family only (not adjudication_replay or research),
    per CXI-R5/R6 definition (A0=CLAUDE.md; A1=configs/ruling-graph/kill-registry).
    Reported as 'precision' in the gate label per README convention, but computed
    as row pass-rate on the governance family.
    """
    gov_rows = [r for r in rows if r.get("family") == "governance"]
    if not gov_rows:
        return 1.0, 0, 0

    correct = 0
    total = 0
    for row in gov_rows:
        gr = results_by_id.get(row["id"])
        if gr and gr["pass"]:
            correct += 1
        total += 1

    return (correct / total) if total > 0 else 1.0, correct, total


def run_eval(include_private: bool = False, output_path: Optional[Path] = None) -> dict:
    db_dir = get_db_dir()
    questions = load_questions()

    # Determine scope
    shared_map = {"macro-dashboard": "shared.sqlite"}
    private_map = dict(_PROJECT_DB_MAP) if include_private else shared_map

    repo_root_map = _REPO_ROOT_MAP

    # Index SHAs for header
    index_shas = {}
    for proj, db_file in private_map.items():
        db_path = db_dir / db_file
        index_shas[proj] = index_sha(db_path)

    results_by_id: dict[str, dict] = {}
    latencies: list[float] = []

    # Split rows: shared vs cross-repo
    shared_rows = [q for q in questions if q.get("visibility") == "shared"]
    private_rows = [q for q in questions if q.get("visibility") == "private"]

    all_rows_to_eval = list(shared_rows)
    if include_private:
        all_rows_to_eval.extend(private_rows)

    for row in all_rows_to_eval:
        row_id = row["id"]
        query = row["query"]
        mode = row.get("mode", "research")

        # Determine project scope for this row
        row_project = row.get("project", "macro-dashboard")
        if row_project == "macro-dashboard":
            project_db_map = shared_map
        elif include_private:
            # Use the full map but ensure the target project is included
            project_db_map = private_map
        else:
            project_db_map = shared_map

        # Prod-parity: adjudication mode uses gitinfo + neighbor expansion,
        # matching CLI behavior (CXI-R6 / Amendment 2 eval prod-parity rule).
        # Other modes skip gitinfo for eval speed.
        is_adjudication = mode == "adjudication"

        t0 = time.monotonic()
        try:
            packet = build_packet(
                query=query,
                db_dir=db_dir,
                project_db_map=project_db_map,
                repo_root_map=repo_root_map,
                mode=mode,
                token_budget=TOKEN_BUDGET_DEFAULT,
                include_gitinfo=is_adjudication,
                expand_neighbors=is_adjudication,
            )
        except Exception as e:
            # Mark as ERROR — not an honest no_answer; grade_row will fail it
            packet = {"results": [], "no_answer_reason": None, "error": str(e)}
        elapsed = time.monotonic() - t0
        latencies.append(elapsed)

        grade = grade_row(row, packet)
        results_by_id[row_id] = {
            **grade,
            "row": row,
            "latency_s": elapsed,
            "n_results": len(packet.get("results", [])),
        }

    # Per-family stats
    families: dict[str, dict] = {}
    for row_id, r in results_by_id.items():
        fam = r["row"].get("family", "unknown")
        if fam not in families:
            families[fam] = {"pass": 0, "fail": 0, "ids": []}
        if r["pass"]:
            families[fam]["pass"] += 1
        else:
            families[fam]["fail"] += 1
            families[fam]["ids"].append(row_id)

    total_rows = len(results_by_id)
    total_pass = sum(1 for r in results_by_id.values() if r["pass"])
    global_recall = total_pass / total_rows if total_rows > 0 else 0.0

    # adjudication_replay family
    adj_rows = {rid: r for rid, r in results_by_id.items()
                if r["row"].get("family") == "adjudication_replay"}
    adj_pass = sum(1 for r in adj_rows.values() if r["pass"])
    adj_total = len(adj_rows)
    adj_recall = adj_pass / adj_total if adj_total > 0 else 0.0

    # Governance precision
    gov_precision, gov_correct, gov_total = compute_governance_precision(
        [r["row"] for r in results_by_id.values()], results_by_id
    )

    # Latency
    latencies_sorted = sorted(latencies)
    p50 = latencies_sorted[len(latencies_sorted) // 2] if latencies_sorted else 0.0
    p95 = latencies_sorted[int(len(latencies_sorted) * 0.95)] if latencies_sorted else 0.0

    # Gate results
    gate_global = "PASS" if global_recall >= 0.90 else "FAIL"
    gate_adj = "PASS" if adj_recall >= 0.90 else ("NOT-MET" if adj_total == 0 else "FAIL")
    gate_gov = "PASS" if gov_precision >= 0.95 else "FAIL"

    # Failed rows detail
    failed_rows = [(rid, r) for rid, r in results_by_id.items() if not r["pass"]]
    failed_rows.sort(key=lambda x: x[0])

    # Cross-repo block: private-visibility rows from external projects only
    # (CXI-R16: cross-repo block defined by visibility=private, not id range)
    cross_rows = {rid: r for rid, r in results_by_id.items()
                  if r["row"].get("visibility") == "private"}
    cross_pass = sum(1 for r in cross_rows.values() if r["pass"])
    cross_total = len(cross_rows)

    summary = {
        "total_rows": total_rows,
        "total_pass": total_pass,
        "global_recall": global_recall,
        "adj_pass": adj_pass,
        "adj_recall": adj_recall,
        "adj_total": adj_total,
        "gov_precision": gov_precision,
        "gov_correct": gov_correct,
        "gov_total": gov_total,
        "p50_s": p50,
        "p95_s": p95,
        "gate_global": gate_global,
        "gate_adj": gate_adj,
        "gate_gov": gate_gov,
        "families": families,
        "failed_rows": failed_rows,
        "cross_pass": cross_pass,
        "cross_total": cross_total,
        "index_shas": index_shas,
    }

    # Write BENCHMARK_RESULTS.md
    if output_path is None:
        output_path = _RESULTS_PATH

    _write_results_md(summary, include_private, output_path)

    return summary


def _write_results_md(s: dict, include_private: bool, path: Path) -> None:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Append-only: prior runs remain unchanged (README §Append-only policy);
    # each invocation appends a new "## Eval run vN" section.
    prior = path.read_text(encoding="utf-8") if path.exists() else ""
    run_n = prior.count("## Eval run ") + 1

    lines = [] if prior else ["# Macro Context Index — Benchmark Results", ""]
    lines += [
        f"## Eval run v{run_n} — {now}",
        "",
        "### Index SHAs",
        "",
    ]
    for proj, sha in s["index_shas"].items():
        lines.append(f"- `{proj}`: `{sha[:12] if sha else 'NOT-INDEXED'}`")
    lines.append("")

    scope_note = "shared-visibility rows only" if not include_private else "all rows including private"
    lines += [
        f"### Scope: {scope_note}",
        "",
        f"Rows evaluated: **{s['total_rows']}**  "
        f"Pass: **{s['total_pass']}**  "
        f"Global Recall@10: **{s['global_recall']:.1%}**",
        "",
        "### Gate results",
        "",
        f"| Gate | Threshold | Result | Value |",
        f"|------|-----------|--------|-------|",
        f"| Global Recall@10 | ≥90% | **{s['gate_global']}** | {s['global_recall']:.1%} |",
        f"| adjudication_replay Recall@10 | ≥90% | **{s['gate_adj']}** | {s['adj_recall']:.1%} ({s['adj_pass']}/{s['adj_total']}) |",
        f"| Governance A0/A1 precision | ≥95% | **{s['gate_gov']}** | {s['gov_precision']:.1%} ({s['gov_correct']}/{s['gov_total']}) |",
        "",
        "### Latency",
        "",
        f"| p50 | p95 |",
        f"|-----|-----|",
        f"| {s['p50_s']*1000:.0f}ms | {s['p95_s']*1000:.0f}ms |",
        "",
        "### Per-family Recall@10",
        "",
        "| Family | Pass | Fail | Recall@10 |",
        "|--------|------|------|-----------|",
    ]

    for fam, fdata in sorted(s["families"].items()):
        p = fdata["pass"]
        f = fdata["fail"]
        total = p + f
        recall = p / total if total > 0 else 0.0
        lines.append(f"| {fam} | {p} | {f} | {recall:.1%} |")

    if include_private and s["cross_total"] > 0:
        cross_recall = (s['cross_pass'] / s['cross_total']) if s['cross_total'] > 0 else 0.0
        lines += [
            "",
            "### Cross-repo block (private-visibility rows)",
            "",
            f"Evaluated: {s['cross_total']}  Pass: {s['cross_pass']}  "
            f"Recall@10: {cross_recall:.1%}",
            "",
            "_Note: paths only; no content excerpts from external projects per CXI-R14._",
        ]
    elif not include_private:
        lines += [
            "",
            "### Cross-repo block (private-visibility rows)",
            "",
            "_NOT-EVALUATED: --include-private not set. Re-run with --include-private to evaluate cross-repo rows._",
        ]

    lines += [
        "",
        "### Failed rows",
        "",
    ]

    if not s["failed_rows"]:
        lines.append("_All evaluated rows passed._")
    else:
        lines.append(f"{len(s['failed_rows'])} failed:")
        lines.append("")
        for rid, r in s["failed_rows"]:
            miss = ", ".join(r.get("miss_sources", []))
            fam = r["row"].get("family", "?")
            notes = r.get("notes", "")
            # For no_answer and error rows, use notes as the reason; for others use miss_sources
            reason = miss if miss else (notes if notes else "missing unknown reason")
            lines.append(f"- **{rid}** ({fam}): {reason}")

    lines += [
        "",
        "---",
        "",
        "_Nulls printed per house epistemics. No content excerpts from private projects._",
    ]

    body = "\n".join(lines) + "\n"
    if prior:
        body = prior.rstrip("\n") + "\n\n" + body
    path.write_text(body, encoding="utf-8")
    print(f"Results written to {path} (run v{run_n})")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="CXI-2 eval harness")
    parser.add_argument("--include-private", action="store_true",
                        help="Include private projects (terminal, mastermind)")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output path (default: research/context_index/BENCHMARK_RESULTS.md)")
    args = parser.parse_args()

    print(f"Running eval against {get_db_dir()} ...")
    summary = run_eval(
        include_private=args.include_private,
        output_path=args.output,
    )

    print(f"\nResults:")
    print(f"  Global Recall@10:    {summary['global_recall']:.1%}  [{summary['gate_global']}]")
    print(f"  Adj-replay Recall:   {summary['adj_recall']:.1%}  [{summary['gate_adj']}]")
    print(f"  Gov A0/A1 precision: {summary['gov_precision']:.1%}  [{summary['gate_gov']}]")
    print(f"  p50={summary['p50_s']*1000:.0f}ms  p95={summary['p95_s']*1000:.0f}ms")
    print(f"  Failed rows: {len(summary['failed_rows'])}")

    for rid, r in summary["failed_rows"]:
        miss = ", ".join(r.get("miss_sources", []))
        print(f"    FAIL {rid}: {miss}")


if __name__ == "__main__":
    main()
