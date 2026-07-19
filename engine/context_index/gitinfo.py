"""
CXI-2 gitinfo retriever — recent-change retriever via git log.

Returns pseudo-results for recent commits matching sanitized query terms,
with source_uri = git://<sha>, authority A4.

Also exposes repo_sha() for staleness checks.

subprocess calls: never shell=True, always cwd=repo_root, always timeout.
stdlib only.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Query sanitization for --grep
# ---------------------------------------------------------------------------

_SHELL_UNSAFE = re.compile(r"[;|&`$'\"\\<>(){}\[\]!#]")


def _sanitize_grep_term(query: str) -> str:
    """Strip characters unsafe for git --grep values."""
    safe = _SHELL_UNSAFE.sub(" ", query)
    return safe.strip()


# ---------------------------------------------------------------------------
# git rev-parse HEAD
# ---------------------------------------------------------------------------


def repo_sha(repo_root: Path, timeout: int = 10) -> str:
    """Return current HEAD sha, or '' on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            timeout=timeout,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def index_sha(db_path: Path) -> str:
    """Read the indexed git sha from a project DB's meta table."""
    if not db_path.exists():
        return ""
    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT value FROM meta WHERE key='indexed_git_sha'").fetchone()
        conn.close()
        return row["value"] if row else ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# git log retrieval
# ---------------------------------------------------------------------------


def _git_log(
    repo_root: Path,
    grep_terms: list[str],
    extra_paths: Optional[list[str]] = None,
    since_days: int = 30,
    max_commits: int = 20,
    timeout: int = 15,
) -> list[dict]:
    """
    Run git log --oneline with --grep for each term (OR logic via --all-match=false).
    Returns list of {sha, date, subject, files}.
    Never shell=True.
    """
    if not grep_terms and not extra_paths:
        return []

    cmd = [
        "git", "log",
        f"--since={since_days} days ago",
        f"--max-count={max_commits}",
        "--format=%H\x00%cs\x00%s",
        "--name-only",  # show changed files
        "--no-merges",
    ]

    for term in grep_terms[:3]:  # limit to 3 grep terms
        safe = _sanitize_grep_term(term)
        if safe:
            cmd.append(f"--grep={safe}")

    # Multiple --grep with default is OR; we want at least one to match
    # (git default is OR for multiple --grep when --all-match is absent)

    if extra_paths:
        cmd.append("--")
        cmd.extend(extra_paths[:10])  # limit paths

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            timeout=timeout,
        )
    except Exception:
        return []

    if result.returncode != 0:
        return []

    commits = []
    current: Optional[dict] = None
    for line in result.stdout.splitlines():
        if "\x00" in line:
            # Header line: sha\x00date\x00subject
            if current:
                commits.append(current)
            parts = line.split("\x00", 2)
            sha = parts[0] if len(parts) > 0 else ""
            date = parts[1] if len(parts) > 1 else ""
            subject = parts[2] if len(parts) > 2 else ""
            current = {"sha": sha, "date": date, "subject": subject, "files": []}
        elif line.strip() and current is not None:
            current["files"].append(line.strip())

    if current:
        commits.append(current)

    return commits[:max_commits]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def gitinfo_search(
    query: str,
    repo_root: Path,
    extra_paths: Optional[list[str]] = None,
    since_days: int = 30,
    top_n: int = 10,
    project_key: str = "macro-dashboard",
) -> list[dict]:
    """
    Return recent commits matching query terms as pseudo-result dicts.
    source_uri = git://<sha>
    authority_class = A4 (temporal state)
    """
    # Extract meaningful terms (skip short words)
    terms = [t for t in re.findall(r'\w+', query) if len(t) >= 4]
    terms = list(dict.fromkeys(terms))[:5]  # dedupe, cap at 5

    commits = _git_log(
        repo_root=repo_root,
        grep_terms=terms,
        extra_paths=extra_paths,
        since_days=since_days,
        max_commits=top_n * 2,
        timeout=15,
    )

    results = []
    for rank, c in enumerate(commits[:top_n]):
        text = f"{c['subject']}\n{c['date']}\nFiles: {', '.join(c['files'][:10])}"
        results.append({
            "chunk_id": f"git:{c['sha'][:12]}",
            "document_id": f"git:{c['sha']}",
            "source_uri": f"git://{c['sha']}",
            "locator": f"git://{c['sha']}",
            "path": "",
            "authority_class": "A4",
            "status": "active",
            "visibility": "shared",
            "project": project_key,
            "rank": rank + 1,
            "raw_score": float(rank + 1),
            "why": "git_recent",
            "heading_path": "[]",
            "symbol": "",
            # Extra metadata carried through
            "_git_sha": c["sha"],
            "_git_date": c["date"],
            "_git_subject": c["subject"],
            "_git_files": c["files"],
            "text": text,
        })

    return results
