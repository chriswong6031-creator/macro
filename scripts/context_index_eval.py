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
  - no_answer rows pass when packet.no_answer_reason is set OR zero results — but
    ONLY once the row has cleared the NOT-EVALUATED gate below; a missing DB is
    never graded as a correct null.
  - required_status binds ONLY to verdict-carrying registry sources
    (DO_NOT_REBUILD.md, ruling_graph.yml, compiled_kill_registry.yml) among the
    required sources; all other required sources are graded on presence alone —
    an active masterplan cannot carry the kill status (CXI-R17a).
  - required_status: superseded rows are presence-only — the one-status-per-chunk
    model cannot label a still-live ruling row whose sub-clause was struck (CXI-R17c).
  - Cross-repo rows (CTX-082..096) require --include-private.
  - CXI-R16 per-row project scoping: each row is evaluated ONLY against its owning
    project's DB (project_db_map = {row_project: _PROJECT_DB_MAP[row_project]}) —
    never against the full 3-DB map, even for private-visibility rows.

NOT-EVALUATED (metric repair, C0, 2026-08-28, op key
macro-context-index-completion-20260828-sol-001): before grading a row, its owning
project's DB file is checked for existence and a non-empty indexed sha. If either
check fails, the row is marked NOT-EVALUATED with a reason and is listed in its
own "### Not evaluated" report section. It is excluded from every
pass/fail/recall/precision/accuracy denominator — including no_answer rows, which
must never grade as a correct null against an absent DB — but it forces the global
promotion gate and any covering adjudication/governance/negative-control gate to
NOT-MET. Rows already out of scope (private-visibility rows when
--include-private is not set) never enter the requested scope and keep the prior
behavior: excluded entirely, with the existing "Cross-repo block" banner.

Gates reported (PASS/FAIL/NOT-MET):
  - Global Recall@10 >= 90%
  - adjudication_replay family Recall@10 >= 90%
  - Governance A0/A1 precision (true) >= 95% — micro-averaged TP/FP over top-10
    results whose authority_class is A0 or A1, for governance-family rows in scope.
    A result is a TP when it path-matches any required_source or acceptable_source
    of its row, else FP. NOT-MET when zero A0/A1 results were returned at all
    ("n/a (0 A0/A1 results returned)").
  - Negative-control (no-answer) accuracy >= 90% — pass-rate over negative_control
    family rows in scope. NOT-MET when zero such rows are in scope.

Informational (no PASS/FAIL gate):
  - Governance recall (row pass-rate) — the OLD governance metric (fraction of
    governance-family rows that pass Recall@10). This was previously mislabeled
    "precision" in the gate table; it is retained as a separate informational
    line because it is a genuinely useful number, just not the precision gate.

Output: research/context_index/BENCHMARK_RESULTS.md (NEVER chunk text excerpts).

ABSOLUTE RULE: this script writes ONLY to research/context_index/BENCHMARK_RESULTS.md
(or --output). Never writes to data/, site/, .context-index.
"""

from __future__ import annotations

import json
import os
import subprocess
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

# Env overrides for cross-repo project roots (CXI-R16 metric-repair pass).
_TERMINAL_ROOT_ENV = "MACRO_CTX_TERMINAL_ROOT"
_MASTERMIND_ROOT_ENV = "MACRO_CTX_MASTERMIND_ROOT"

# Governance authority classes
_GOV_AUTH = {"A0", "A1"}

# Gate thresholds
_GLOBAL_RECALL_THRESHOLD = 0.90
_ADJ_RECALL_THRESHOLD = 0.90
_GOV_TRUE_PRECISION_THRESHOLD = 0.95
_NEG_ACCURACY_THRESHOLD = 0.90


def get_db_dir() -> Path:
    env = os.environ.get(_DB_DIR_ENV, "").strip()
    return Path(env) if env else _DB_DIR


def _resolve_repo_root_map() -> dict[str, Path]:
    """
    Resolve project roots for the report header's repo-SHA/dirty columns,
    honoring MACRO_CTX_TERMINAL_ROOT / MACRO_CTX_MASTERMIND_ROOT env overrides
    and falling back to _REPO_ROOT_MAP.
    """
    resolved = dict(_REPO_ROOT_MAP)
    term_override = os.environ.get(_TERMINAL_ROOT_ENV, "").strip()
    if term_override:
        resolved["terminal"] = Path(term_override).expanduser()
    mm_override = os.environ.get(_MASTERMIND_ROOT_ENV, "").strip()
    if mm_override:
        resolved["mastermind"] = Path(mm_override).expanduser()
    return resolved


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


def _not_evaluated_reason(project_key: str, db_dir: Path) -> Optional[str]:
    """
    Returns a reason string if the given project's DB cannot be evaluated
    against (missing file, or index_sha() returns falsy), else None.

    CXI metric repair (C0, 2026-08-28): this check MUST run before a row is
    graded at all — including no_answer rows, which must never grade as a
    correct null just because an absent DB returned zero results.
    """
    db_file = _PROJECT_DB_MAP.get(project_key)
    if not db_file:
        return f"unknown project: {project_key}"
    db_path = db_dir / db_file
    if not db_path.exists():
        return f"db missing: {db_file}"
    if not index_sha(db_path):
        return f"db missing: {db_file}"
    return None


def _project_db_map_for_row(row: dict) -> dict[str, str]:
    """
    CXI-R16 per-row project scoping: a row is evaluated against exactly its
    owning project's DB — never the full 3-DB map, even for private-visibility
    rows whose project happens to be macro-dashboard.
    """
    project = row.get("project", "macro-dashboard")
    return {project: _PROJECT_DB_MAP[project]}


def evaluate_row(row: dict, db_dir: Path, repo_root_map: dict[str, Path]) -> dict:
    """
    Evaluate a single benchmark row against its owning project's DB.

    Returns a dict. When the owning project's DB is unavailable, returns
    {"not_evaluated": True, "reason": <str>, "row": row} and NEVER includes a
    "pass" key — a missing DB can never grade as a pass, correct-null or
    otherwise. Otherwise returns
    {"not_evaluated": False, "reason": None, "pass", "miss_sources", "notes",
     "row", "packet", "latency_s", "n_results"}.
    """
    row_project = row.get("project", "macro-dashboard")
    reason = _not_evaluated_reason(row_project, db_dir)
    if reason:
        return {"not_evaluated": True, "reason": reason, "row": row}

    project_db_map = _project_db_map_for_row(row)
    query = row["query"]
    mode = row.get("mode", "research")

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

    grade = grade_row(row, packet)
    return {
        "not_evaluated": False,
        "reason": None,
        **grade,
        "row": row,
        "packet": packet,
        "latency_s": elapsed,
        "n_results": len(packet.get("results", [])),
    }


def compute_governance_recall(rows: list[dict], results_by_id: dict[str, dict]) -> tuple[float, int, int]:
    """
    Governance row pass-rate: fraction of governance-family rows (in scope) that
    pass Recall@10. Population is strictly governance-family only (not
    adjudication_replay or research), per CXI-R5/R6 definition (A0=CLAUDE.md;
    A1=configs/ruling-graph/kill-registry).

    NOTE (metric repair, C0, 2026-08-28): this is a RECALL number (row
    pass-rate), not precision — it was previously mislabeled "precision" in
    the gate table despite this docstring already describing pass-rate. It is
    now reported as a separate informational line with no PASS/FAIL gate; the
    real precision gate is compute_governance_true_precision() below.
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


def compute_governance_true_precision(results_by_id: dict[str, dict]) -> dict:
    """
    TRUE governance A0/A1 precision (CXI metric repair, C0, 2026-08-28):
    micro-averaged precision of high-authority results returned for
    governance-family rows in scope.

    For each governance row, each top-10 result whose authority_class is A0
    or A1 is a true positive (TP) if it path-matches (via _path_match) any
    entry of that row's required_sources or acceptable_sources, else a false
    positive (FP). gov_true_precision = TP / (TP + FP).

    results_by_id values must carry "row" (the benchmark row dict) and
    "packet" (the packet dict with a "results" list) keys — this is exactly
    the shape evaluate_row() returns for evaluated (non-NOT-EVALUATED) rows,
    but the function accepts any dict shaped that way so it is testable with
    synthetic packets and no real DB.

    Returns {"tp": int, "fp": int, "precision": float | None}; precision is
    None when TP+FP == 0 (no A0/A1 results were returned at all) — the caller
    reports that as gate NOT-MET, never as a false 0% or 100%.
    """
    tp = 0
    fp = 0
    for entry in results_by_id.values():
        row = entry.get("row", {})
        if row.get("family") != "governance":
            continue
        packet = entry.get("packet") or {}
        top10 = packet.get("results", [])[:10]
        relevant = set(row.get("required_sources", []) or []) | set(row.get("acceptable_sources", []) or [])
        for r in top10:
            if r.get("authority_class") not in _GOV_AUTH:
                continue
            is_tp = any(
                _path_match(r.get("path", ""), r.get("source_uri", ""), src)
                for src in relevant
            )
            if is_tp:
                tp += 1
            else:
                fp += 1

    denom = tp + fp
    precision = (tp / denom) if denom > 0 else None
    return {"tp": tp, "fp": fp, "precision": precision}


def compute_negative_control_accuracy(results_by_id: dict[str, dict]) -> dict:
    """
    Negative-control (no-answer) accuracy (CXI metric repair, C0, 2026-08-28):
    pass-rate over rows with family == "negative_control" among evaluated
    (in-scope, not NOT-EVALUATED) rows.

    Returns {"pass": int, "total": int, "accuracy": float | None}; accuracy is
    None when total == 0 (no negative_control rows in scope) — the caller
    reports that as gate NOT-MET.
    """
    neg_entries = [e for e in results_by_id.values() if e.get("row", {}).get("family") == "negative_control"]
    total = len(neg_entries)
    passed = sum(1 for e in neg_entries if e.get("pass"))
    accuracy = (passed / total) if total > 0 else None
    return {"pass": passed, "total": total, "accuracy": accuracy}


def _repo_dirty(root: Path, timeout: int = 10) -> Optional[bool]:
    """
    Returns True if `git -C root status --porcelain` reports any changes,
    False if clean, None if the check could not be performed (missing root,
    not a git repo, timeout, etc.) — never fabricates clean/dirty on failure.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            return None
        return bool(result.stdout.strip())
    except Exception:
        return None


def run_eval(include_private: bool = False, output_path: Optional[Path] = None) -> dict:
    db_dir = get_db_dir()
    questions = load_questions()

    # Determine scope
    shared_map = {"macro-dashboard": "shared.sqlite"}
    scope_project_map = dict(_PROJECT_DB_MAP) if include_private else shared_map

    repo_root_map = _resolve_repo_root_map()

    # Index SHAs + repo SHAs/dirty flags for header (projects in scope only)
    index_shas: dict[str, str] = {}
    repo_shas: dict[str, dict] = {}
    for proj, db_file in scope_project_map.items():
        db_path = db_dir / db_file
        index_shas[proj] = index_sha(db_path)

        root = repo_root_map.get(proj)
        if root and root.exists():
            repo_shas[proj] = {"sha": repo_sha(root), "dirty": _repo_dirty(root)}
        else:
            repo_shas[proj] = {"sha": "", "dirty": None}

    results_by_id: dict[str, dict] = {}
    not_evaluated: list[dict] = []
    latencies: list[float] = []

    # Split rows: shared vs cross-repo (visibility, per CXI-R16 — not id range)
    shared_rows = [q for q in questions if q.get("visibility") == "shared"]
    private_rows = [q for q in questions if q.get("visibility") == "private"]

    all_rows_to_eval = list(shared_rows)
    if include_private:
        all_rows_to_eval.extend(private_rows)

    for row in all_rows_to_eval:
        row_id = row["id"]
        result = evaluate_row(row, db_dir, repo_root_map)
        if result["not_evaluated"]:
            not_evaluated.append({
                "id": row_id,
                "family": row.get("family", "unknown"),
                "reason": result["reason"],
            })
            continue
        results_by_id[row_id] = result
        latencies.append(result["latency_s"])

    # Per-family stats (NOT-EVALUATED rows excluded — they never entered results_by_id)
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

    # Governance recall (old metric, informational — no gate)
    gov_recall, gov_correct, gov_total = compute_governance_recall(
        [r["row"] for r in results_by_id.values()], results_by_id
    )

    # Governance A0/A1 TRUE precision (the actual gate)
    gov_true = compute_governance_true_precision(results_by_id)
    gov_true_precision = gov_true["precision"]
    gov_tp = gov_true["tp"]
    gov_fp = gov_true["fp"]

    # Negative-control (no-answer) accuracy (the new explicit gate)
    neg = compute_negative_control_accuracy(results_by_id)
    neg_accuracy = neg["accuracy"]
    neg_pass = neg["pass"]
    neg_total = neg["total"]

    # Latency
    latencies_sorted = sorted(latencies)
    p50 = latencies_sorted[len(latencies_sorted) // 2] if latencies_sorted else 0.0
    p95 = latencies_sorted[int(len(latencies_sorted) * 0.95)] if latencies_sorted else 0.0

    # Gate results. An intended in-scope row that was NOT-EVALUATED cannot be
    # discarded as a denominator-only detail: the global promotion gate and
    # any family gate that covers it are not met. Rows outside the requested
    # scope never enter all_rows_to_eval, so they do not reach this list.
    not_evaluated_families = {item["family"] for item in not_evaluated}
    gate_global = (
        "NOT-MET" if not_evaluated
        else ("PASS" if global_recall >= _GLOBAL_RECALL_THRESHOLD else "FAIL")
    )
    gate_adj = (
        "NOT-MET" if "adjudication_replay" in not_evaluated_families
        else ("PASS" if adj_recall >= _ADJ_RECALL_THRESHOLD else ("NOT-MET" if adj_total == 0 else "FAIL"))
    )
    gate_gov = (
        "NOT-MET" if "governance" in not_evaluated_families
        else ("NOT-MET" if gov_true_precision is None else (
            "PASS" if gov_true_precision >= _GOV_TRUE_PRECISION_THRESHOLD else "FAIL"
        ))
    )
    gate_neg = (
        "NOT-MET" if "negative_control" in not_evaluated_families
        else ("NOT-MET" if neg_accuracy is None else (
            "PASS" if neg_accuracy >= _NEG_ACCURACY_THRESHOLD else "FAIL"
        ))
    )

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
        "gov_precision": gov_recall,  # back-compat alias; equals gov_recall
        "gov_correct": gov_correct,
        "gov_total": gov_total,
        "gov_recall": gov_recall,
        "gov_true_precision": gov_true_precision,
        "gov_tp": gov_tp,
        "gov_fp": gov_fp,
        "neg_accuracy": neg_accuracy,
        "neg_pass": neg_pass,
        "neg_total": neg_total,
        "gate_neg": gate_neg,
        "not_evaluated": not_evaluated,
        "not_evaluated_families": sorted(not_evaluated_families),
        "repo_shas": repo_shas,
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


def _fmt_gov_true_value(s: dict) -> str:
    if s["gov_true_precision"] is None:
        return "n/a (0 A0/A1 results returned)"
    return f"{s['gov_true_precision']:.1%} ({s['gov_tp']}/{s['gov_tp'] + s['gov_fp']})"


def _fmt_neg_value(s: dict) -> str:
    if s["neg_accuracy"] is None:
        return "n/a (0 negative_control rows in scope)"
    return f"{s['neg_accuracy']:.1%} ({s['neg_pass']}/{s['neg_total']})"


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
        rs = s["repo_shas"].get(proj, {})
        rsha = rs.get("sha") or ""
        dirty = rs.get("dirty")
        dirty_str = "clean" if dirty is False else ("dirty" if dirty is True else "unknown")
        repo_sha_disp = rsha[:12] if rsha else "NOT-AVAILABLE"
        lines.append(
            f"- `{proj}`: index `{sha[:12] if sha else 'NOT-INDEXED'}`, "
            f"repo `{repo_sha_disp}` ({dirty_str})"
        )
    lines.append("")

    scope_note = "shared-visibility rows only" if not include_private else "all rows including private"
    lines += [
        f"### Scope: {scope_note}",
        "",
        f"Rows evaluated: **{s['total_rows']}**  "
        f"Pass: **{s['total_pass']}**  "
        f"Global Recall@10: **{s['global_recall']:.1%}**  "
        f"Not-evaluated: **{len(s['not_evaluated'])}**",
        "",
        "### Gate results",
        "",
        f"| Gate | Threshold | Result | Value |",
        f"|------|-----------|--------|-------|",
        f"| Global Recall@10 | ≥90% | **{s['gate_global']}** | {s['global_recall']:.1%} |",
        f"| adjudication_replay Recall@10 | ≥90% | **{s['gate_adj']}** | {s['adj_recall']:.1%} ({s['adj_pass']}/{s['adj_total']}) |",
        f"| Governance A0/A1 precision (true) | ≥95% | **{s['gate_gov']}** | {_fmt_gov_true_value(s)} |",
        f"| Negative-control (no-answer) accuracy | ≥90% | **{s['gate_neg']}** | {_fmt_neg_value(s)} |",
        "",
        f"_Informational (no gate) — Governance recall (row pass-rate): "
        f"{s['gov_recall']:.1%} ({s['gov_correct']}/{s['gov_total']})._",
        "",
        "### Not evaluated",
        "",
    ]

    if not s["not_evaluated"]:
        lines.append("_None._")
    else:
        for item in s["not_evaluated"]:
            lines.append(f"- **{item['id']}** ({item['family']}): {item['reason']}")

    lines += [
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
    print(f"  Global Recall@10:                  {summary['global_recall']:.1%}  [{summary['gate_global']}]")
    print(f"  Adj-replay Recall:                 {summary['adj_recall']:.1%}  [{summary['gate_adj']}]")
    print(f"  Gov A0/A1 precision (true):        {_fmt_gov_true_value(summary)}  [{summary['gate_gov']}]")
    print(f"  Governance recall (row pass-rate): {summary['gov_recall']:.1%} "
          f"({summary['gov_correct']}/{summary['gov_total']})  [informational]")
    print(f"  Negative-control accuracy:         {_fmt_neg_value(summary)}  [{summary['gate_neg']}]")
    print(f"  p50={summary['p50_s']*1000:.0f}ms  p95={summary['p95_s']*1000:.0f}ms")
    print(f"  Not-evaluated rows: {len(summary['not_evaluated'])}")
    print(f"  Failed rows: {len(summary['failed_rows'])}")

    for item in summary["not_evaluated"]:
        print(f"    NOT-EVALUATED {item['id']} ({item['family']}): {item['reason']}")

    for rid, r in summary["failed_rows"]:
        miss = ", ".join(r.get("miss_sources", []))
        print(f"    FAIL {rid}: {miss}")


if __name__ == "__main__":
    main()
