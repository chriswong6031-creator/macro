"""scripts/build_active_build_map.py — Active Build Map generator.

Air-traffic-control artifact for multi-agent sessions: generates a map of open
PRs, their file collisions, and recent merges so new sessions stop re-proposing
in-flight work.

ADVISORY ONLY — no merge gating, no CI hard-fails.  The generated outputs are
informational; they gate nothing in the pipeline.

Outputs (defaults; override with --json-out and --md-out):
    data/governance/active_builds.json    schema active_builds.v1
    docs/ACTIVE_BUILD_MAP.md              human-readable map

Fail-open: if `gh` is missing, errors, or rate-limits the script prints a clear
warning to stderr and exits 0 WITHOUT touching existing output files.  The
nightly must never go red because of this script.

Usage::

    python -m scripts.build_active_build_map
    python -m scripts.build_active_build_map --merged-days 7
    python -m scripts.build_active_build_map --json-out /tmp/map.json --md-out /tmp/map.md
    python -m scripts.build_active_build_map --dry-run   # prints to stdout only
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import logging
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("build_active_build_map")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA = "active_builds.v1"

# Glob patterns for paths that carry elevated operational risk.  Touching them
# is INFORMATIONAL only — the flag records a fact; it blocks nothing.
PROTECTED_GLOBS: list[str] = [
    ".github/workflows/**",
    "config/dag.yml",
    "config/synapse.yml",
    "docs/SIGNAL_BUS.md",
    "scripts/check_*.py",
    "engine/validation.py",
    "engine/trial_ledger.py",
    "engine/promotion_gate.py",
    "engine/neuralweb/**",
    "engine/research_factory/**",
    "data/trial_ledger.jsonl",
    "data/governance/**",
    "data/experiments/registry_seed.json",
    "site/neuralwebdata/**",
]

_REPO_ROOT = Path(__file__).resolve().parent.parent

_DEFAULT_JSON_OUT = _REPO_ROOT / "data" / "governance" / "active_builds.json"
_DEFAULT_MD_OUT = _REPO_ROOT / "docs" / "ACTIVE_BUILD_MAP.md"


# ---------------------------------------------------------------------------
# Pure helpers (unit-testable; no subprocess/network calls)
# ---------------------------------------------------------------------------

def is_protected_path(file_path: str, globs: list[str] | None = None) -> bool:
    """Return True if *file_path* matches any protected glob pattern.

    Uses fnmatch on the raw path; also tests with a leading-slash stripped so
    both ``engine/neuralweb/foo.py`` and ``/engine/neuralweb/foo.py`` match the
    pattern ``engine/neuralweb/**``.
    """
    if globs is None:
        globs = PROTECTED_GLOBS
    path_norm = file_path.lstrip("/")
    for pattern in globs:
        if fnmatch.fnmatch(path_norm, pattern):
            return True
        # Also test basename for patterns like "config/dag.yml"
        if fnmatch.fnmatch(path_norm, pattern.lstrip("/")):
            return True
    return False


def compute_collisions(open_prs: list[dict]) -> list[dict]:
    """Return pairwise collision records for PRs sharing at least one file.

    Each record::

        {
          "pr_a": int,
          "pr_b": int,
          "shared_files": [str, ...],
          "shared_count": int,
          "any_protected": bool,
        }

    Sorted by shared_count descending.  Only pairs where files_truncated is
    False on BOTH PRs yield definitive collision data; truncated PRs are still
    included but any_protected / shared_files may be incomplete.
    """
    collisions: list[dict] = []
    for i, pr_a in enumerate(open_prs):
        files_a: set[str] = set(pr_a.get("files", []))
        if not files_a:
            continue
        for pr_b in open_prs[i + 1 :]:
            files_b: set[str] = set(pr_b.get("files", []))
            if not files_b:
                continue
            shared = sorted(files_a & files_b)
            if not shared:
                continue
            any_protected = any(is_protected_path(f) for f in shared)
            collisions.append(
                {
                    "pr_a": pr_a["number"],
                    "pr_b": pr_b["number"],
                    "shared_files": shared,
                    "shared_count": len(shared),
                    "any_protected": any_protected,
                }
            )
    collisions.sort(key=lambda c: -c["shared_count"])
    return collisions


def protected_paths_for_pr(pr: dict) -> list[str]:
    """Return the subset of a PR's files that match a protected glob."""
    return [f for f in pr.get("files", []) if is_protected_path(f)]


def render_markdown(payload: dict) -> str:
    """Render *payload* (active_builds.v1 schema) to a Markdown string.

    Pure function — no I/O.  Used by the script and by tests.
    """
    lines: list[str] = []

    lines.append(
        "<!-- GENERATED — do not edit by hand; "
        "regenerate with `python scripts/build_active_build_map.py`. "
        "Advisory only: this map informs sessions; it gates nothing. -->"
    )
    lines.append("")
    lines.append("# Active Build Map")
    lines.append("")

    gen_at = payload.get("generated_at", "unknown")
    base_sha = payload.get("base", {}).get("sha") if isinstance(payload.get("base"), dict) else payload.get("base")
    open_prs = payload.get("open_prs", [])
    recent_merged = payload.get("recent_merged", [])
    collisions = payload.get("collisions", [])

    merged_truncated = payload.get("merged_truncated", False)
    lines.append(
        f"Generated: {gen_at}  |  "
        f"Open PRs: {len(open_prs)}  |  "
        f"Merged (window): {len(recent_merged)}  |  "
        f"base: `{base_sha or 'unknown'}`"
    )
    lines.append("")

    # ------------------------------------------------------------------ §Open PRs
    lines.append("## Open PRs")
    lines.append("")
    lines.append("| PR | Title | Branch | Updated | Flags |")
    lines.append("|----|-------|--------|---------|-------|")
    n_unknown_mergeability = 0
    n_files_error = 0
    for pr in open_prs:
        num = pr["number"]
        title = pr.get("title", "").replace("|", "\\|")
        branch = pr.get("head_ref", "").replace("|", "\\|")
        updated = (pr.get("updated_at") or "")[:10]
        flags_parts: list[str] = []
        if pr.get("is_draft"):
            flags_parts.append("DRAFT")
        if pr.get("merge_state") == "DIRTY":
            flags_parts.append("⚠ CONFLICTING")
        n_protected = len(pr.get("protected_paths_touched", []))
        if n_protected:
            flags_parts.append(f"⚠ protected:{n_protected}")
        if pr.get("files_truncated"):
            flags_parts.append("files-truncated")
        if pr.get("files_error"):
            flags_parts.append("⚠ files:error")
            n_files_error += 1
        flags = " / ".join(flags_parts) if flags_parts else "—"
        lines.append(f"| #{num} | {title} | `{branch}` | {updated} | {flags} |")
        # Count PRs where mergeability remains UNKNOWN after the per-PR view call
        raw_state = pr.get("merge_state_raw")
        if raw_state == "UNKNOWN" or (raw_state is None and pr.get("merge_state", "") == "UNKNOWN"):
            n_unknown_mergeability += 1
    if not open_prs:
        lines.append("| — | No open PRs | — | — | — |")
    lines.append("")
    lines.append(
        "> ⚠ CONFLICTING means mergeStateStatus=DIRTY — pull_request CI is suppressed "
        "on conflicting PRs (known repo failure mode)."
    )
    if n_unknown_mergeability > 0:
        lines.append(
            f"> ℹ {n_unknown_mergeability} of {len(open_prs)} PRs: "
            "mergeability not yet computed by GitHub (UNKNOWN)."
        )
    if n_files_error > 0:
        lines.append(
            f"> ⚠ {n_files_error} PR(s) marked `files:error` — file fetch failed; "
            "collision data for those PRs is unknown."
        )
    lines.append("")

    # ------------------------------------------------------------------ §Collisions
    lines.append("## File Collisions")
    lines.append("")
    if collisions:
        lines.append("| PR A | PR B | Shared files | Files |")
        lines.append("|------|------|-------------|-------|")
        _MAX_SHOWN = 8
        for col in collisions:
            pr_a = col["pr_a"]
            pr_b = col["pr_b"]
            count = col["shared_count"]
            shown = col["shared_files"][:_MAX_SHOWN]
            extra = count - len(shown)
            file_cell = ", ".join(f"`{f}`" for f in shown)
            if extra > 0:
                file_cell += f" +{extra} more"
            prot = " ⚠" if col.get("any_protected") else ""
            lines.append(f"| #{pr_a} | #{pr_b} | {count}{prot} | {file_cell} |")
    else:
        lines.append("_No file collisions detected among open PRs._")
    lines.append("")

    # ------------------------------------------------------------------ §Recently merged
    merged_days = payload.get("merged_days", 14)
    merged_section_header = f"## Recently Merged (last {merged_days} days)"
    if merged_truncated:
        merged_section_header += " (showing most recent 500; window truncated)"
    lines.append(merged_section_header)
    lines.append("")
    if recent_merged:
        lines.append("| PR | Title | Merged |")
        lines.append("|----|-------|--------|")
        for pr in recent_merged:
            num = pr["number"]
            title = pr.get("title", "").replace("|", "\\|")
            merged_at = (pr.get("merged_at") or "")[:10]
            lines.append(f"| #{num} | {title} | {merged_at} |")
    else:
        lines.append("_No PRs merged in the window._")
    lines.append("")

    # ------------------------------------------------------------------ Footer
    lines.append("---")
    lines.append("")
    lines.append(
        "Before proposing or adjudicating new work: check your topic against the "
        "open-PR lanes above AND against `research/DO_NOT_REBUILD.md` "
        "(standing kills/forbidden designs)."
    )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# gh CLI data collection
# ---------------------------------------------------------------------------

def _run_gh(args: list[str], timeout: int = 30) -> Any | None:
    """Run a `gh` command and return parsed JSON, or None on any error."""
    cmd = ["gh"] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        log.warning("gh CLI not found — cannot collect PR data")
        return None
    except subprocess.TimeoutExpired:
        log.warning("gh command timed out: %s", " ".join(cmd))
        return None
    if result.returncode != 0:
        log.warning(
            "gh command failed (rc=%d): %s\nstderr: %s",
            result.returncode,
            " ".join(cmd),
            result.stderr.strip()[:400],
        )
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        log.warning("gh output is not valid JSON: %s", exc)
        return None


def _collect_open_prs() -> list[dict] | None:
    """Fetch open PRs via gh CLI.  Returns None on failure."""
    data = _run_gh([
        "pr", "list",
        "--state", "open",
        "--limit", "100",
        "--json", "number,title,headRefName,updatedAt,isDraft,mergeStateStatus",
    ])
    if data is None:
        return None
    prs: list[dict] = []
    for item in data:
        prs.append({
            "number": item.get("number"),
            "title": item.get("title", ""),
            "head_ref": item.get("headRefName", ""),
            "updated_at": item.get("updatedAt", ""),
            "is_draft": bool(item.get("isDraft", False)),
            "merge_state": item.get("mergeStateStatus", ""),
        })
    return prs


def _collect_pr_files(pr_number: int) -> tuple[list[str], bool, bool, str | None]:
    """Fetch changed files and resolved mergeability for a PR.

    Returns ``(files, files_truncated, files_error, resolved_merge_state)``.

    * ``files_truncated`` — True when the file list hit the API cap (>=100 files
      returned), meaning the actual changed-file set may be larger.
    * ``files_error`` — True when the gh fetch itself failed; files list is empty
      and collision data for this PR is unknown.
    * ``resolved_merge_state`` — the mergeStateStatus value from the per-PR view
      call (more reliably computed than the list-level value); None on fetch error.
    """
    data = _run_gh(["pr", "view", str(pr_number), "--json", "files,mergeStateStatus"])
    if data is None:
        return [], False, True, None
    raw_files = data.get("files", [])
    # gh caps the file list at 100; if exactly 100 assume truncation
    files = [f.get("path", "") for f in raw_files if isinstance(f, dict)]
    truncated = len(files) >= 100
    resolved_merge_state = data.get("mergeStateStatus") or None
    return files, truncated, False, resolved_merge_state


_MERGED_FETCH_LIMIT = 500


def _collect_recent_merged(merged_days: int) -> tuple[list[dict], bool] | tuple[None, bool]:
    """Fetch recently merged PRs filtered to the last *merged_days* days.

    Returns (list_of_prs, truncated_flag).  Returns (None, False) on gh failure.

    Uses a server-side date filter (``merged:>=<ISO-date>``) so the fetch window
    matches the requested window even for very busy repos.  If the API returns
    exactly _MERGED_FETCH_LIMIT entries the window may still be truncated; the
    flag is set in that case so callers can annotate honestly.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=merged_days)
    # Server-side date filter: ISO date only (YYYY-MM-DD) as required by gh search
    cutoff_date_str = cutoff.strftime("%Y-%m-%d")
    data = _run_gh([
        "pr", "list",
        "--state", "merged",
        "--search", f"merged:>={cutoff_date_str}",
        "--limit", str(_MERGED_FETCH_LIMIT),
        "--json", "number,title,mergedAt",
    ])
    if data is None:
        return None, False
    truncated = len(data) >= _MERGED_FETCH_LIMIT
    # Belt-and-suspenders: also filter client-side by exact datetime cutoff
    recent: list[dict] = []
    for item in data:
        merged_at_str = item.get("mergedAt", "") or ""
        try:
            merged_dt = datetime.fromisoformat(merged_at_str.replace("Z", "+00:00"))
        except ValueError:
            continue
        if merged_dt >= cutoff:
            recent.append({
                "number": item.get("number"),
                "title": item.get("title", ""),
                "merged_at": merged_at_str,
            })
    return recent, truncated


def _resolve_main_sha() -> str | None:
    """Return the SHA of origin/main if resolvable via git, else None."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "origin/main"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(_REPO_ROOT),
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def build_map(merged_days: int = 14) -> dict | None:
    """Collect data and return the active_builds.v1 payload dict.

    Returns None if gh is unavailable or any critical fetch failed.
    """
    open_prs_raw = _collect_open_prs()
    if open_prs_raw is None:
        log.warning("Could not fetch open PRs — aborting map generation")
        return None

    recent_merged_result = _collect_recent_merged(merged_days)
    if recent_merged_result[0] is None:
        log.warning("Could not fetch merged PRs — aborting map generation")
        return None
    recent_merged, merged_truncated = recent_merged_result

    # Enrich each open PR with file data and resolved mergeability
    enriched_prs: list[dict] = []
    for pr in open_prs_raw:
        num = pr["number"]
        files, files_truncated, files_error, resolved_merge_state = _collect_pr_files(num)
        # Override list-level merge_state when the per-PR call resolves to
        # something more specific than UNKNOWN
        list_merge_state = pr.get("merge_state", "")
        if resolved_merge_state and resolved_merge_state != "UNKNOWN":
            effective_merge_state = resolved_merge_state
        else:
            effective_merge_state = list_merge_state
        protected = [f for f in files if is_protected_path(f)]
        enriched_prs.append({
            **pr,
            "merge_state": effective_merge_state,
            "merge_state_raw": resolved_merge_state,
            "files_count": len(files),
            "files_truncated": files_truncated,
            "files_error": files_error,
            "files": files,
            "protected_paths_touched": protected,
        })

    collisions = compute_collisions(enriched_prs)
    base_sha = _resolve_main_sha()

    payload: dict = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base": {"sha": base_sha},
        "merged_days": merged_days,
        "merged_truncated": merged_truncated,
        "open_prs": enriched_prs,
        "collisions": collisions,
        "recent_merged": recent_merged,
    }
    return payload


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--json-out",
        default=str(_DEFAULT_JSON_OUT),
        help=f"Path for JSON output (default: {_DEFAULT_JSON_OUT})",
    )
    parser.add_argument(
        "--md-out",
        default=str(_DEFAULT_MD_OUT),
        help=f"Path for Markdown output (default: {_DEFAULT_MD_OUT})",
    )
    parser.add_argument(
        "--merged-days",
        type=int,
        default=14,
        help="How many days back to include in 'recently merged' (default: 14)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print outputs to stdout without writing files",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s  %(name)s  %(message)s",
        stream=sys.stderr,
    )
    args = _parse_args(argv)

    payload = build_map(merged_days=args.merged_days)
    if payload is None:
        # Fail-open: gh not available or errored — leave existing outputs untouched
        print(
            "WARNING: active build map generation skipped (gh unavailable or errored). "
            "Existing output files untouched.",
            file=sys.stderr,
        )
        return 0

    json_text = json.dumps(payload, indent=2, default=str)
    md_text = render_markdown(payload)

    if args.dry_run:
        print("=== JSON OUTPUT ===")
        print(json_text)
        print("\n=== MARKDOWN OUTPUT ===")
        print(md_text)
        return 0

    # Write JSON
    json_path = Path(args.json_out)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json_text, encoding="utf-8")
    log.info("Wrote %s", json_path)

    # Write Markdown
    md_path = Path(args.md_out)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md_text, encoding="utf-8")
    log.info("Wrote %s", md_path)

    n_open = len(payload.get("open_prs", []))
    n_merged = len(payload.get("recent_merged", []))
    n_collisions = len(payload.get("collisions", []))
    log.info(
        "Active build map: %d open PR(s), %d collision pair(s), %d merged in %dd window",
        n_open, n_collisions, n_merged, args.merged_days,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
