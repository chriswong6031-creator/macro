"""
CXI-2 fusion — Reciprocal Rank Fusion (RRF) across retrievers.

RRF score = sum over retrievers: 1 / (60 + rank)

Post-fusion steps (in order):
  1. Dedupe by chunk_id (keep best RRF score per chunk).
  2. Per-file cap: at most 2 chunks per source_uri (overflow counted; default per_file_cap=2).
  3. Status filter: exclude killed/forbidden/superseded UNLESS mode in
     ('adjudication', 'historical') — governance queries NEED kills.
  4. Authority floor: if any A0/A1 result matched, top-3 slots reserved
     for highest-RRF A0/A1 rows (cannot be crowded out by A2-A5 floods).
  5. Neighbor expansion: fetch neighbor_before/after for top-3 results only
     (budget permitting — callers can disable).

stdlib + sqlite3 only.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

# Statuses excluded in default mode.
# "deferred" is excluded: it means the topic is on hold, not active.
# "unknown" status on DO_NOT_REBUILD chunks is governance-only noise in non-governance modes.
_EXCLUDED_STATUSES_DEFAULT = {"killed", "forbidden", "superseded", "deferred"}

# Modes that include excluded statuses
_GOVERNANCE_MODES = {"adjudication", "historical", "governance"}

# Authority classes that get floor-reservation
_HIGH_AUTH = {"A0", "A1"}

RRF_K = 60  # RRF constant


def _rrf_score(rank: int) -> float:
    return 1.0 / (RRF_K + rank)


def fuse(
    retriever_results: dict[str, list[dict]],
    mode: str = "research",
    per_file_cap: int = 2,
    top_n: int = 20,
    db_dir: Optional[Path] = None,
    project_db_map: Optional[dict[str, str]] = None,
    expand_neighbors: bool = True,
) -> tuple[list[dict], int]:
    """
    Fuse results from multiple retrievers.

    retriever_results: {"lexical": [...], "structured": [...], "gitinfo": [...]}
    Returns (fused_results, omitted_due_to_budget).

    Each result in fused_results has score_components added:
      {exact_rank, lexical_rank, semantic_rank, fused_score}
    """
    # Step 1: Compute RRF scores per chunk_id
    scores: dict[str, float] = {}
    chunk_data: dict[str, dict] = {}
    retriever_ranks: dict[str, dict[str, int]] = {name: {} for name in retriever_results}

    _SPECIFIC_STATUS = {"killed", "forbidden", "deferred", "superseded"}
    _STATUS_BOOST = 0.001  # small boost for status-bearing governance chunks

    for retriever_name, results in retriever_results.items():
        for result in results:
            cid = result["chunk_id"]
            r = result["rank"]
            base_score = _rrf_score(r)
            # Small boost for kill-registry chunks with specific status
            if result.get("status") in _SPECIFIC_STATUS:
                base_score += _STATUS_BOOST
            scores[cid] = scores.get(cid, 0.0) + base_score
            retriever_ranks[retriever_name][cid] = r
            # Keep the data dict with best (highest) RRF score
            if cid not in chunk_data or scores[cid] > chunk_data[cid].get("_rrf", 0):
                chunk_data[cid] = dict(result)
                chunk_data[cid]["_rrf"] = scores[cid]

    # Attach score_components
    for cid, data in chunk_data.items():
        data["score_components"] = {
            "exact_rank": retriever_ranks.get("structured", {}).get(cid),
            "lexical_rank": retriever_ranks.get("lexical", {}).get(cid),
            "semantic_rank": None,
            "fused_score": round(scores[cid], 6),
        }
        data["fused_score"] = scores[cid]

    # Sort by fused score descending
    ranked = sorted(chunk_data.values(), key=lambda r: -r["fused_score"])

    # Step 2: Status filter (BEFORE per-file cap so cap isn't wasted on excluded rows)
    if mode not in _GOVERNANCE_MODES:
        ranked = [r for r in ranked if r.get("status", "active") not in _EXCLUDED_STATUSES_DEFAULT]

    # Step 3: Authority floor — ensure A0/A1 hits occupy at least top-3 slots.
    # If any A0/A1 result matched, the top-3 RRF-scored A0/A1 rows are guaranteed
    # to appear in positions 1-3.  Other A0/A1 rows remain in their natural RRF
    # position among the rest; this is a PROMOTION not a DROP.
    high_auth_hits = [r for r in ranked if r.get("authority_class") in _HIGH_AUTH]
    other_hits = [r for r in ranked if r.get("authority_class") not in _HIGH_AUTH]

    if high_auth_hits:
        # The top-3 A0/A1 by RRF score go first.
        top3_high = high_auth_hits[:3]
        top3_ids = {r["chunk_id"] for r in top3_high}
        # Remaining rows (A0/A1 beyond top-3 AND all A2-A5), sorted by RRF score.
        remaining = [r for r in ranked if r["chunk_id"] not in top3_ids]
        ranked = top3_high + remaining
    # (If no high-auth hits, order is purely by RRF score — already sorted)

    # Step 4: Per-file cap
    file_counts: dict[str, int] = {}
    capped: list[dict] = []
    omitted = 0
    for r in ranked:
        file_key = r.get("source_uri", r.get("path", r["chunk_id"]))
        cnt = file_counts.get(file_key, 0)
        if cnt >= per_file_cap:
            omitted += 1
            continue
        file_counts[file_key] = cnt + 1
        capped.append(r)

    # Also count truly omitted (beyond top_n after capping)
    total_omitted = omitted + max(0, len(capped) - top_n)
    final = capped[:top_n]

    # Step 5: Neighbor expansion for top-3 (if db_dir provided)
    if expand_neighbors and db_dir and project_db_map and len(final) >= 1:
        neighbors = _fetch_neighbors(final[:3], db_dir, project_db_map)
        # Add unique neighbors at the end (don't displace existing)
        existing_ids = {r["chunk_id"] for r in final}
        for nb in neighbors:
            if nb["chunk_id"] not in existing_ids:
                final.append(nb)
                existing_ids.add(nb["chunk_id"])

    # Re-number ranks
    for i, r in enumerate(final):
        r["rank"] = i + 1

    return final, total_omitted


def _fetch_neighbors(
    results: list[dict],
    db_dir: Path,
    project_db_map: dict[str, str],
) -> list[dict]:
    """Fetch neighbor_before and neighbor_after chunks for the given results."""
    # Group by project to avoid multiple opens
    by_project: dict[str, list[dict]] = {}
    for r in results:
        proj = r.get("project", "macro-dashboard")
        by_project.setdefault(proj, []).append(r)

    neighbors: list[dict] = []
    for proj, proj_results in by_project.items():
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
                # Get the chunk row to find neighbor IDs
                row = conn.execute(
                    "SELECT neighbor_before, neighbor_after FROM chunks WHERE chunk_id=?",
                    (r["chunk_id"],),
                ).fetchone()
                if not row:
                    continue

                for nb_id in [row["neighbor_before"], row["neighbor_after"]]:
                    if not nb_id:
                        continue
                    nb_row = conn.execute(
                        """
                        SELECT c.chunk_id, c.document_id, c.locator, c.heading_path,
                               c.symbol, c.text,
                               d.source_uri, d.path, d.authority_class, d.status, d.visibility
                        FROM chunks c
                        JOIN documents d ON d.document_id = c.document_id
                        WHERE c.chunk_id=? AND d.tombstoned=0
                        """,
                        (nb_id,),
                    ).fetchone()
                    if nb_row:
                        neighbors.append({
                            "chunk_id": nb_row["chunk_id"],
                            "document_id": nb_row["document_id"],
                            "source_uri": nb_row["source_uri"],
                            "locator": nb_row["locator"],
                            "path": nb_row["path"] or "",
                            "authority_class": nb_row["authority_class"] or "A3",
                            "status": nb_row["status"] or "active",
                            "visibility": nb_row["visibility"] or "shared",
                            "project": proj,
                            "rank": 9999,
                            "raw_score": 0.0,
                            "why": "neighbor_expansion",
                            "heading_path": nb_row["heading_path"] or "[]",
                            "symbol": nb_row["symbol"] or "",
                            "fused_score": 0.0,
                            "score_components": {
                                "exact_rank": None,
                                "lexical_rank": None,
                                "semantic_rank": None,
                                "fused_score": 0.0,
                            },
                            "text": nb_row["text"] or "",
                        })
        finally:
            conn.close()

    return neighbors
