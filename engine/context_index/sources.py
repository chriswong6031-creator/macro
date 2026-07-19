"""
CXI-1 source discovery: config load, file discovery, deny rules, symlink safety.

No third-party deps beyond PyYAML (already in repo).
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Iterator, NamedTuple

import yaml

# ---------------------------------------------------------------------------
# Deny patterns (per docket §8 + adjudication CXI-R10)
# ---------------------------------------------------------------------------

_HARD_DENY: list[str] = [
    "**/.env*",
    "**/*credential*",
    "**/*secret*",
    "**/auth.json",
    "site/**",
    "data/**",
    "**/__pycache__/**",
    "**/node_modules/**",
    "research/artifacts/**",
    "ObsidianBrain/**",
    ".context-index/**",
    ".git/**",
]


class SourceEntry(NamedTuple):
    id: str
    roots: list[str]
    authority_class: str
    visibility: str
    chunker: str
    source_type: str = "research"


class Config(NamedTuple):
    sources: list[SourceEntry]
    deny: list[str]


def load_config(config_path: Path) -> Config:
    """Load config/context_index.yml; return Config."""
    with config_path.open() as f:
        raw = yaml.safe_load(f)

    deny_patterns = list(_HARD_DENY)
    for pat in raw.get("deny", []):
        if pat not in deny_patterns:
            deny_patterns.append(pat)

    sources: list[SourceEntry] = []
    for s in raw.get("sources", []):
        sources.append(SourceEntry(
            id=s["id"],
            roots=s.get("roots", []),
            authority_class=s.get("authority_class", "A3"),
            visibility=s.get("visibility", "shared"),
            chunker=s.get("chunker", "markdown_sections"),
            source_type=s.get("source_type", "research"),
        ))

    return Config(sources=sources, deny=deny_patterns)


# ---------------------------------------------------------------------------
# Deny evaluation
# ---------------------------------------------------------------------------


def _is_denied(rel_path: str, deny_patterns: list[str]) -> bool:
    """
    Return True if rel_path matches any deny glob.

    Handling rules:
    - Root-anchored patterns (no leading **/):  matched against the full path
      only.  e.g. 'data/**' only matches paths that START with 'data/'.
    - Any-directory patterns (leading **/ or purely **): also matched against
      each trailing sub-path so '**/.env*' catches 'config/.env.local'.
    """
    for pat in deny_patterns:
        if fnmatch.fnmatch(rel_path, pat):
            return True
        if "**" in pat:
            # Strip leading **/ for the simplified match
            simple = pat.replace("**/", "")
            if fnmatch.fnmatch(rel_path, simple):
                return True
            # Only fan out to trailing sub-paths when the pattern is
            # non-root-anchored (starts with **/).  Root-anchored patterns
            # like 'data/**' or 'site/**' must only match from the root.
            if pat.startswith("**/"):
                parts = rel_path.split("/")
                for k in range(1, len(parts)):   # k=1: skip full path (already checked)
                    if fnmatch.fnmatch("/".join(parts[k:]), simple):
                        return True
    return False


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class DiscoveredFile(NamedTuple):
    abs_path: Path
    rel_path: str
    source_id: str
    authority_class: str
    visibility: str
    chunker: str
    source_type: str


def discover_files(
    repo_root: Path,
    config: Config,
) -> Iterator[tuple[DiscoveredFile | None, str | None]]:
    """
    Yield (DiscoveredFile, None) for each accepted file, or
    (None, reason_string) for each skipped file.

    All yielded paths have been:
    - resolved inside repo_root (symlink-safe)
    - checked against deny patterns
    """
    seen: set[Path] = set()

    for src in config.sources:
        if src.visibility == "private":
            # CXI-1 scope: shared plane only
            continue

        for root_glob in src.roots:
            # Expand glob relative to repo_root
            import glob as _glob
            matched = _glob.glob(
                str(repo_root / root_glob), recursive=True
            )
            if not matched:
                # literal path that might not exist yet — skip silently
                continue

            for abs_str in matched:
                abs_path = Path(abs_str)

                # Must be a file
                if not abs_path.is_file():
                    continue

                # Symlink safety: resolve and check inside repo_root
                try:
                    real = abs_path.resolve()
                except OSError:
                    yield None, f"symlink-escape:{abs_path}"
                    continue

                try:
                    real.relative_to(repo_root.resolve())
                except ValueError:
                    yield None, f"symlink-escape:{abs_path}"
                    continue

                rel = str(abs_path.relative_to(repo_root))

                # Deny check — evaluate against BOTH the discovery path and the
                # resolved target path so that in-repo symlinks pointing at denied
                # trees (data/, .env, site/) are caught even when the symlink itself
                # lives under a non-denied directory.
                try:
                    real_rel = str(real.relative_to(repo_root.resolve()))
                except ValueError:
                    real_rel = rel  # already handled by the escape check above

                if _is_denied(rel, config.deny) or _is_denied(real_rel, config.deny):
                    yield None, f"denied:{rel}"
                    continue

                # De-dup
                if real in seen:
                    continue
                seen.add(real)

                yield DiscoveredFile(
                    abs_path=abs_path,
                    rel_path=rel,
                    source_id=src.id,
                    authority_class=src.authority_class,
                    visibility=src.visibility,
                    chunker=src.chunker,
                    source_type=src.source_type,
                ), None
