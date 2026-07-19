#!/usr/bin/env python3
"""
CXI-2 CLI — context_index_query.py

Subcommands:
  search   -- run a query, output context_packet.v1 (JSON default, --text readable)
  open     -- print exact source region ±20 lines for a locator
  recent   -- recent git commits for a topic
  explain  -- per-retriever ranks for top results
  status   -- index health (wraps build --status)

Project scope:
  Default: ["macro-dashboard"] only.
  External: --projects terminal,mastermind  or  --include-private
  Invalid project keys → error with valid list.

Usage examples:
  python scripts/context_index_query.py search "DO_NOT_REBUILD market structure"
  python scripts/context_index_query.py search "kill registry MSP" --mode adjudication --text
  python scripts/context_index_query.py open "research/DO_NOT_REBUILD.md#row-5"
  python scripts/context_index_query.py status
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Resolve repo root (scripts/ is directly under repo root)
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from engine.context_index.packet import build_packet, TOKEN_BUDGET_DEFAULT, TOKEN_BUDGET_HARD_CAP
from engine.context_index.gitinfo import gitinfo_search, repo_sha, index_sha
from engine.context_index.lexical import lexical_search, _sanitize_fts5
from engine.context_index.structured import structured_search

# ---------------------------------------------------------------------------
# DB / config helpers
# ---------------------------------------------------------------------------

_DEFAULT_DB_DIR_ENV = "MACRO_CONTEXT_INDEX_DIR"
_DEFAULT_DB_DIR = _REPO_ROOT / ".context-index"

# Known project keys and their DB files
_PROJECT_DB_MAP_DEFAULT: dict[str, str] = {
    "macro-dashboard": "shared.sqlite",
    "terminal": "terminal.sqlite",
    "mastermind": "mastermind.sqlite",
}

_VALID_PROJECTS = set(_PROJECT_DB_MAP_DEFAULT.keys())


def _get_db_dir() -> Path:
    env = os.environ.get(_DEFAULT_DB_DIR_ENV, "").strip()
    if env:
        return Path(env)
    return _DEFAULT_DB_DIR


def _resolve_project_scope(
    projects_arg: str | None,
    include_private: bool,
) -> dict[str, str]:
    """
    Return project_db_map for the requested scope.
    Raises SystemExit on invalid project keys.
    """
    if projects_arg:
        keys = [k.strip() for k in projects_arg.split(",") if k.strip()]
        invalid = [k for k in keys if k not in _VALID_PROJECTS]
        if invalid:
            print(
                f"ERROR: unknown project keys: {invalid}. "
                f"Valid: {sorted(_VALID_PROJECTS)}",
                file=sys.stderr,
            )
            sys.exit(1)
        return {k: _PROJECT_DB_MAP_DEFAULT[k] for k in keys}

    if include_private:
        return dict(_PROJECT_DB_MAP_DEFAULT)

    return {"macro-dashboard": "shared.sqlite"}


def _get_repo_root_map() -> dict[str, Path]:
    """Return known repo roots for each project (for staleness checks)."""
    return {
        "macro-dashboard": _REPO_ROOT,
        "terminal": Path("~/Documents/Cluade/charting-app").expanduser(),
        "mastermind": Path("~/Documents/Cluade/Mastermind").expanduser(),
    }


# ---------------------------------------------------------------------------
# search subcommand
# ---------------------------------------------------------------------------

def cmd_search(args: argparse.Namespace) -> None:
    db_dir = _get_db_dir()
    project_db_map = _resolve_project_scope(
        getattr(args, "projects", None),
        getattr(args, "include_private", False),
    )
    repo_root_map = _get_repo_root_map()

    status_filter = None
    if getattr(args, "status_filter", None):
        status_filter = [s.strip() for s in args.status_filter.split(",")]

    budget = min(getattr(args, "budget", TOKEN_BUDGET_DEFAULT), TOKEN_BUDGET_HARD_CAP)
    max_results = getattr(args, "max_results", 20)

    packet = build_packet(
        query=args.query,
        db_dir=db_dir,
        project_db_map=project_db_map,
        repo_root_map=repo_root_map,
        mode=getattr(args, "mode", "research"),
        token_budget=budget,
        max_results=max_results,
        status_filter=status_filter,
    )

    if getattr(args, "json", False) or not getattr(args, "text", False):
        print(json.dumps(packet, indent=2, ensure_ascii=False))
    else:
        _print_packet_text(packet)


def _print_packet_text(packet: dict) -> None:
    stale = " [STALE INDEX]" if packet.get("index_stale") else ""
    print(f"=== Context Packet: {packet['mode']} mode{stale} ===")
    print(f"Query: {packet['query']}")
    print(f"Projects: {packet['project_scope']}")
    print(f"Generated: {packet['generated_at']}")
    print(f"Repo SHA: {packet.get('repo_sha', '')[:12]}")
    if packet.get("index_stale"):
        print("WARNING: Index is stale — run context_index_build.py --rebuild")
    print(f"Retrievers: {packet.get('retrievers_used', [])}")
    print(f"Results: {len(packet['results'])}  Omitted: {packet.get('omitted_due_to_budget', 0)}")
    if packet.get("no_answer_reason"):
        print(f"NO ANSWER: {packet['no_answer_reason']}")
    print()

    for r in packet["results"]:
        sc = r.get("score_components", {})
        print(f"  [{r['rank']}] {r['authority_class']} {r['status']:12s} {r['locator']}")
        print(f"       fused={sc.get('fused_score', 0):.4f}  why={r.get('why_retrieved','')}")
        excerpt = r.get("excerpt", "")
        if excerpt:
            preview = excerpt[:200].replace("\n", " ")
            print(f"       {preview!r}")
        print()

    if packet.get("conflicts"):
        print(f"CONFLICTS ({len(packet['conflicts'])}):")
        for c in packet["conflicts"]:
            print(f"  {c.get('reason','')}")


# ---------------------------------------------------------------------------
# open subcommand
# ---------------------------------------------------------------------------

def cmd_open(args: argparse.Namespace) -> None:
    """Print ±20 lines around a locator's source region."""
    locator = args.locator
    db_dir = _get_db_dir()
    project_db_map = _resolve_project_scope(
        getattr(args, "projects", None),
        getattr(args, "include_private", False),
    )
    repo_root_map = _get_repo_root_map()

    # Resolve locator to a path + line anchor
    # Format: path#anchor  or  repo://path#anchor  or  repo://project/path#anchor
    import sqlite3 as _sqlite3

    target_locator = locator
    if locator.startswith("repo://"):
        # Strip scheme
        rest = locator[len("repo://"):]
        # Check if project-prefixed
        for proj in project_db_map:
            if rest.startswith(proj + "/"):
                rest = rest[len(proj) + 1:]
                break
        target_locator = rest

    # Split path#anchor
    if "#" in target_locator:
        file_path_str, anchor = target_locator.split("#", 1)
    else:
        file_path_str = target_locator
        anchor = None

    # Find the chunk text from the DB
    for proj, db_file in project_db_map.items():
        db_path = db_dir / db_file
        if not db_path.exists():
            continue
        conn = _sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = _sqlite3.Row
        try:
            row = conn.execute(
                "SELECT c.text, c.locator, d.path, d.source_uri FROM chunks c "
                "JOIN documents d ON d.document_id=c.document_id "
                "WHERE c.locator LIKE ? AND d.tombstoned=0 LIMIT 1",
                (f"%{target_locator}%",),
            ).fetchone()
            if row:
                print(f"=== {row['source_uri']} ===")
                print(row["text"])
                conn.close()
                return
        finally:
            conn.close()

    # Fall back to reading the file directly — with traversal containment
    repo_root = repo_root_map.get("macro-dashboard", _REPO_ROOT)
    # Reject absolute paths and any traversal attempts before joining
    if file_path_str.startswith("/") or ".." in Path(file_path_str).parts:
        print(f"ERROR: locator path rejected (absolute or traversal): {file_path_str!r}", file=sys.stderr)
        sys.exit(1)
    file_path = (repo_root / file_path_str).resolve()
    # Enforce root containment after resolution
    try:
        file_path.relative_to(repo_root.resolve())
    except ValueError:
        print(f"ERROR: locator resolves outside repo root: {file_path}", file=sys.stderr)
        sys.exit(1)
    if not file_path.exists():
        print(f"ERROR: not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    lines = file_path.read_text(errors="replace").splitlines()
    # Print all if small, else first 40 lines
    context_lines = lines[:40]
    print(f"=== {file_path_str} ===")
    for i, line in enumerate(context_lines, 1):
        print(f"{i:4}: {line}")


# ---------------------------------------------------------------------------
# recent subcommand
# ---------------------------------------------------------------------------

def cmd_recent(args: argparse.Namespace) -> None:
    repo_root = _get_repo_root_map().get("macro-dashboard", _REPO_ROOT)
    results = gitinfo_search(
        query=args.topic,
        repo_root=repo_root,
        since_days=30,
        top_n=15,
    )
    if not results:
        print("No recent commits found for this topic.")
        return
    for r in results:
        sha = r.get("_git_sha", "")[:12]
        date = r.get("_git_date", "")
        subject = r.get("_git_subject", "")
        files = r.get("_git_files", [])
        print(f"{sha}  {date}  {subject}")
        for f in files[:5]:
            print(f"           {f}")


# ---------------------------------------------------------------------------
# explain subcommand
# ---------------------------------------------------------------------------

def cmd_explain(args: argparse.Namespace) -> None:
    db_dir = _get_db_dir()
    project_db_map = _resolve_project_scope(
        getattr(args, "projects", None),
        getattr(args, "include_private", False),
    )

    from engine.context_index.fusion import fuse
    lex = lexical_search(args.query, db_dir, project_db_map)
    struct = structured_search(args.query, db_dir, project_db_map, mode="research")
    fused, _ = fuse({"lexical": lex, "structured": struct}, top_n=10)

    print(f"=== Explain: {args.query!r} ===")
    print(f"Lexical hits: {len(lex)}  Structured hits: {len(struct)}")
    print()
    for r in fused[:10]:
        sc = r.get("score_components", {})
        print(
            f"  [{r['rank']}] {r['locator'][:60]:60s} "
            f"lex={sc.get('lexical_rank','?')!s:>4}  "
            f"struct={sc.get('exact_rank','?')!s:>4}  "
            f"fused={sc.get('fused_score',0):.4f}  "
            f"auth={r.get('authority_class','?')}  "
            f"status={r.get('status','?')}"
        )


# ---------------------------------------------------------------------------
# status subcommand
# ---------------------------------------------------------------------------

def cmd_status(args: argparse.Namespace) -> None:
    db_dir = _get_db_dir()
    project_db_map = _resolve_project_scope(
        getattr(args, "projects", None),
        getattr(args, "include_private", False),
    )
    repo_root_map = _get_repo_root_map()

    import sqlite3 as _sqlite3

    print(f"=== Context Index Status ===")
    print(f"DB dir: {db_dir}")
    print()

    for proj, db_file in project_db_map.items():
        db_path = db_dir / db_file
        print(f"Project: {proj}  ({db_file})")
        if not db_path.exists():
            print("  [NOT INDEXED]")
            continue

        conn = _sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = _sqlite3.Row
        try:
            ndocs = conn.execute("SELECT COUNT(*) as n FROM documents WHERE tombstoned=0").fetchone()["n"]
            nchunks = conn.execute("SELECT COUNT(*) as n FROM chunks").fetchone()["n"]
            i_sha = conn.execute("SELECT value FROM meta WHERE key='indexed_git_sha'").fetchone()
            built_at = conn.execute("SELECT value FROM meta WHERE key='built_at'").fetchone()
            i_sha_val = i_sha["value"][:12] if i_sha else "?"
            built_val = built_at["value"] if built_at else "?"
        finally:
            conn.close()

        root = repo_root_map.get(proj)
        r_sha = repo_sha(root)[:12] if root else "?"
        stale = " [STALE]" if (r_sha != i_sha_val and r_sha and i_sha_val) else ""
        print(f"  docs={ndocs}  chunks={nchunks}  indexed_sha={i_sha_val}{stale}")
        print(f"  repo_sha={r_sha}  built_at={built_val}")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Macro Context Index query CLI (CXI-2)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # search
    p_search = sub.add_parser("search", help="Search the context index")
    p_search.add_argument("query", help="Query string")
    p_search.add_argument("--mode", default="research",
                          choices=["code", "architecture", "research", "operations",
                                   "governance", "adjudication"],
                          help="Retrieval mode (default: research)")
    p_search.add_argument("--projects", help="Comma-separated project keys (default: macro-dashboard)")
    p_search.add_argument("--include-private", action="store_true",
                          help="Include private projects (terminal, mastermind)")
    p_search.add_argument("--status", dest="status_filter",
                          help="Comma-separated status filter")
    p_search.add_argument("--budget", type=int, default=TOKEN_BUDGET_DEFAULT,
                          help=f"Token budget (default {TOKEN_BUDGET_DEFAULT}, hard cap {TOKEN_BUDGET_HARD_CAP})")
    p_search.add_argument("--max-results", type=int, default=20,
                          help="Maximum results (default 20)")
    p_search.add_argument("--json", action="store_true", help="JSON output (default)")
    p_search.add_argument("--text", action="store_true", help="Human-readable output")

    # open
    p_open = sub.add_parser("open", help="Open a locator and print its source")
    p_open.add_argument("locator", help="Locator (path#anchor or repo://...)")
    p_open.add_argument("--projects", help="Project scope")
    p_open.add_argument("--include-private", action="store_true")

    # recent
    p_recent = sub.add_parser("recent", help="Recent git commits for a topic")
    p_recent.add_argument("topic", help="Topic or path to search in git log")

    # explain
    p_explain = sub.add_parser("explain", help="Per-retriever breakdown for a query")
    p_explain.add_argument("query", help="Query string")
    p_explain.add_argument("--projects", help="Project scope")
    p_explain.add_argument("--include-private", action="store_true")

    # status
    p_status = sub.add_parser("status", help="Index status and staleness")
    p_status.add_argument("--projects", help="Project scope")
    p_status.add_argument("--include-private", action="store_true")

    args = parser.parse_args()

    dispatch = {
        "search": cmd_search,
        "open": cmd_open,
        "recent": cmd_recent,
        "explain": cmd_explain,
        "status": cmd_status,
    }
    dispatch[args.subcommand](args)


if __name__ == "__main__":
    main()
