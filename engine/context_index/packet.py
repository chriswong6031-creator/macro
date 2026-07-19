"""
CXI-2 packet assembler — context_packet.v1 per docket §7.3.

Runs lexical + structured + gitinfo retrievers, fuses, packs to token budget.

Public function:
  build_packet(query, db_dir, project_db_map, repo_root_map, ...)
  → dict  (context_packet.v1)

ABSOLUTE RULES:
  - index_stale must be VISIBLE; never silently report current.
  - no_answer_reason set when zero results above floor.
  - Never fabricate results.
  - conflicts list populated when a killed/forbidden registry row AND an active
    doc both rank for the query.
  - token_budget hard cap 8000; default 6000.
  - Greedy packing by fused rank; never split top result.

stdlib + sqlite3 only.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .fusion import fuse
from .gitinfo import gitinfo_search, repo_sha, index_sha
from .lexical import lexical_search
from .structured import structured_search

# ---------------------------------------------------------------------------
# Token budget
# ---------------------------------------------------------------------------

TOKEN_BUDGET_DEFAULT = 6000
TOKEN_BUDGET_HARD_CAP = 8000

# Rough chars-per-token ratio (conservative)
_CHARS_PER_TOKEN = 4

EXCERPT_MAX_CHARS = 700  # per result excerpt


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


# ---------------------------------------------------------------------------
# Staleness check
# ---------------------------------------------------------------------------


def _check_staleness(
    db_dir: Path,
    project_db_map: dict[str, str],
    repo_root_map: dict[str, Path],
) -> tuple[dict[str, str], bool]:
    """
    Returns (index_sha_map, any_stale).
    index_sha_map: project_key → indexed_sha
    any_stale: True if any project's indexed sha != its current HEAD sha
    """
    shas: dict[str, str] = {}
    any_stale = False

    for proj, db_file in project_db_map.items():
        db_path = db_dir / db_file
        i_sha = index_sha(db_path)
        shas[proj] = i_sha
        root = repo_root_map.get(proj)
        if root:
            r_sha = repo_sha(root)
            if r_sha and i_sha and r_sha != i_sha:
                any_stale = True
            elif not i_sha:
                any_stale = True  # not indexed yet

    return shas, any_stale


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------


def _detect_conflicts(results: list[dict], query: str = "") -> list[dict]:
    """
    Conflicts: when a killed/forbidden registry row AND an active doc
    both rank for the query on the same topic.

    Overlap detection uses:
      1. Same document path (exact).
      2. Shared non-trivial content tokens from the chunk text/heading_path —
         locator strings are path-like and don't split into meaningful terms.
      3. Query-term overlap: both the killed row and active doc contain
         significant query terms (at least 2 non-stopword tokens in common).
    """
    _STOPWORDS = {
        "the", "a", "an", "is", "in", "of", "to", "and", "or", "for",
        "on", "with", "that", "this", "it", "as", "at", "by", "from",
        "how", "does", "what", "where", "why", "when", "which", "do",
        "i", "we", "you", "are", "was", "be", "have", "has", "had",
        "been", "will", "would", "could", "should", "may", "can",
    }

    import re as _re
    query_tokens = {
        t for t in _re.findall(r'\w{3,}', query.lower()) if t not in _STOPWORDS
    }

    def _content_tokens(r: dict) -> set[str]:
        """Extract significant tokens from a result's text/heading."""
        text = (r.get("text", "") or r.get("excerpt", "") or "") + " " + (r.get("heading_path", "") or "")
        return {t for t in _re.findall(r'\w{3,}', text.lower()) if t not in _STOPWORDS}

    conflicts = []
    killed = [r for r in results if r.get("status") in ("killed", "forbidden")]
    active = [r for r in results if r.get("status") == "active"]

    seen_pairs: set[tuple[str, str]] = set()

    for k in killed:
        k_path = k.get("path", "")
        k_tokens = _content_tokens(k) & query_tokens  # terms in common with query

        for a in active:
            a_path = a.get("path", "")
            pair = (k.get("locator", ""), a.get("locator", ""))
            if pair in seen_pairs:
                continue

            # Condition 1: same document path (e.g. two chunks of same file)
            same_path = k_path and a_path and k_path == a_path
            # Condition 2: both contain at least 2 shared query-relevant terms
            a_tokens = _content_tokens(a) & query_tokens
            shared_query_terms = k_tokens & a_tokens
            topic_overlap = len(shared_query_terms) >= 2

            if same_path or topic_overlap:
                seen_pairs.add(pair)
                conflicts.append({
                    "killed_locator": k["locator"],
                    "active_locator": a["locator"],
                    "reason": (
                        f"killed/forbidden row {k['locator']!r} conflicts with "
                        f"active doc {a['locator']!r}"
                        + (f" (shared query terms: {sorted(shared_query_terms)!r})" if topic_overlap else "")
                    ),
                })

    return conflicts


# ---------------------------------------------------------------------------
# Packer: greedy by fused rank
# ---------------------------------------------------------------------------


def _pack_results(
    results: list[dict],
    token_budget: int,
) -> tuple[list[dict], int]:
    """
    Greedy packing: include results in rank order until budget exhausted.
    Never splits the top result (always included if budget > 0).
    Returns (packed_results, omitted_due_to_budget).
    """
    if not results:
        return [], 0

    # Fetch text from result (text field may be on the raw result)
    packed = []
    used_tokens = 0
    omitted = 0

    for i, r in enumerate(results):
        text = r.get("text", "") or r.get("excerpt", "") or ""
        excerpt = text[:EXCERPT_MAX_CHARS]
        tokens = _estimate_tokens(excerpt)

        if i == 0:
            # Top result always included
            packed.append(dict(r, excerpt=excerpt))
            used_tokens += tokens
            continue

        if used_tokens + tokens > token_budget:
            omitted += 1
        else:
            packed.append(dict(r, excerpt=excerpt))
            used_tokens += tokens

    return packed, omitted


# ---------------------------------------------------------------------------
# Fetch chunk text from DB (for results that don't carry text inline)
# ---------------------------------------------------------------------------


def _enrich_text(
    results: list[dict],
    db_dir: Path,
    project_db_map: dict[str, str],
) -> None:
    """Fetch chunk.text for any results missing it, in-place."""
    # Group by project
    by_proj: dict[str, list[dict]] = {}
    for r in results:
        if not r.get("text"):
            proj = r.get("project", "macro-dashboard")
            by_proj.setdefault(proj, []).append(r)

    for proj, proj_results in by_proj.items():
        db_file = project_db_map.get(proj)
        if not db_file:
            continue
        db_path = db_dir / db_file
        if not db_path.exists():
            continue
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            for r in proj_results:
                row = conn.execute(
                    "SELECT text FROM chunks WHERE chunk_id=?", (r["chunk_id"],)
                ).fetchone()
                if row:
                    r["text"] = row["text"] or ""
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Main packet builder
# ---------------------------------------------------------------------------


def build_packet(
    query: str,
    db_dir: Path,
    project_db_map: dict[str, str],
    repo_root_map: dict[str, Path],
    mode: str = "research",
    token_budget: int = TOKEN_BUDGET_DEFAULT,
    generated_at: Optional[str] = None,
    include_gitinfo: bool = True,
    expand_neighbors: bool = True,
    max_results: int = 20,
    status_filter: Optional[list[str]] = None,
) -> dict:
    """
    Build a context_packet.v1 dict.

    Args:
        query: user/agent query string
        db_dir: directory containing project SQLite DBs
        project_db_map: {project_key: db_filename}
        repo_root_map: {project_key: Path} for staleness checks and gitinfo
        mode: code|architecture|research|operations|governance|adjudication
        token_budget: target token budget (default 6000, hard cap 8000)
        generated_at: ISO timestamp (pass one to ensure deterministic tests)
        include_gitinfo: whether to run gitinfo retriever
        expand_neighbors: whether to fetch neighboring chunks for top-3
        max_results: maximum results in packet
        status_filter: if set, only include results with these statuses
    """
    token_budget = min(token_budget, TOKEN_BUDGET_HARD_CAP)
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).isoformat()

    # --- Staleness ---
    index_sha_map, any_stale = _check_staleness(db_dir, project_db_map, repo_root_map)

    # Use first macro-dashboard repo sha as the packet's repo_sha
    primary_root = repo_root_map.get("macro-dashboard")
    current_repo_sha = repo_sha(primary_root) if primary_root else ""
    primary_index_sha = index_sha_map.get("macro-dashboard", "")

    # --- Retrieval ---
    lexical_results = lexical_search(query, db_dir, project_db_map)
    structured_results = structured_search(query, db_dir, project_db_map, mode=mode)

    gitinfo_results: list[dict] = []
    if include_gitinfo and primary_root:
        # Pass matched paths from other retrievers to narrow git search
        matched_paths = list({
            r["path"] for r in (lexical_results[:5] + structured_results[:5])
            if r.get("path")
        })
        gitinfo_results = gitinfo_search(
            query=query,
            repo_root=primary_root,
            extra_paths=matched_paths[:5],
            project_key="macro-dashboard",
        )

    retrievers_used = ["lexical", "structured"]
    if gitinfo_results:
        retrievers_used.append("gitinfo")

    # --- adjudication mode extras ---
    if mode == "adjudication":
        # Force ACTIVE_BUILD_MAP into structured results if not already there
        # (done by structured retriever via governance_docs path)
        pass

    # --- Fusion ---
    retriever_map: dict[str, list[dict]] = {
        "lexical": lexical_results,
        "structured": structured_results,
    }
    if gitinfo_results:
        retriever_map["gitinfo"] = gitinfo_results

    fused, omitted_cap = fuse(
        retriever_results=retriever_map,
        mode=mode,
        per_file_cap=2,  # docket §10.3: at most 2 chunks per source_uri
        top_n=max_results + 10,  # fetch extra for budget trimming
        db_dir=db_dir,
        project_db_map=project_db_map,
        expand_neighbors=expand_neighbors,
    )

    # Optional status filter
    if status_filter:
        fused = [r for r in fused if r.get("status") in status_filter]

    # --- Enrich with text if missing ---
    _enrich_text(fused, db_dir, project_db_map)

    # --- Conflict detection ---
    conflicts = _detect_conflicts(fused, query=query)

    # --- Pack to budget ---
    packed, omitted_budget = _pack_results(fused, token_budget)
    # omitted_cap: results dropped by per-file-cap + top_n cap in fusion
    # omitted_budget: results present after fusion but dropped by token budget
    # Sum reported as omitted_due_to_budget (composite: cap + budget drops)
    total_omitted = omitted_cap + omitted_budget

    # --- no_answer_reason ---
    no_answer_reason = None
    if not packed:
        no_answer_reason = f"No results found for query: {query!r}"

    # --- Build result dicts ---
    result_dicts = []
    for r in packed:
        result_dicts.append({
            "source_uri": r.get("source_uri", ""),
            "locator": r.get("locator", ""),
            "authority_class": r.get("authority_class", "A3"),
            "status": r.get("status", "active"),
            "source_as_of": r.get("source_as_of", ""),
            "git_sha": r.get("git_sha", ""),
            "excerpt": r.get("excerpt", "")[:EXCERPT_MAX_CHARS],
            "score_components": r.get("score_components", {
                "exact_rank": None,
                "lexical_rank": None,
                "semantic_rank": None,
                "fused_score": r.get("fused_score", 0.0),
            }),
            "why_retrieved": r.get("why", ""),
            "project": r.get("project", "macro-dashboard"),
            "path": r.get("path", ""),
            "rank": r.get("rank", 0),
        })

    return {
        "schema": "context_packet.v1",
        "query": query,
        "project_scope": list(project_db_map.keys()),
        "mode": mode,
        "generated_at": generated_at,
        "repo_sha": current_repo_sha,
        "index_sha": primary_index_sha,
        "index_stale": any_stale,
        "token_budget": token_budget,
        "retrievers_used": retrievers_used,
        "results": result_dicts,
        "conflicts": conflicts,
        "omitted_due_to_budget": total_omitted,
        "no_answer_reason": no_answer_reason,
    }
