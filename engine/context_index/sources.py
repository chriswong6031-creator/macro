"""
CXI-1b source discovery: config load (v2 multi-repo), file discovery, deny rules, symlink safety.

v2 adds a top-level "projects:" map with per-project root, visibility, db, sources, deny.
v1 configs are rejected with a clear error message (config_hash change forces a rebuild anyway).

Backward-compat: Config(sources, deny) NamedTuple is kept so CXI-1 unit tests continue to pass.
v2 load returns MultiProjectConfig; run_ingest accepts both.

No third-party deps beyond PyYAML (already in repo).
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Iterator, NamedTuple, Optional

import yaml

# ---------------------------------------------------------------------------
# Hard deny patterns (apply to ALL projects; per-project deny adds on top)
# ---------------------------------------------------------------------------

_HARD_DENY: list[str] = [
    "**/.env*",
    "**/*credential*",
    "**/*secret*",
    "**/auth.json",
    "**/__pycache__/**",
    "**/node_modules/**",
    ".context-index/**",
    ".git/**",
]


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class SourceEntry(NamedTuple):
    id: str
    roots: list[str]
    authority_class: str
    visibility: str
    chunker: str
    source_type: str = "research"


# Backwards-compat Config (CXI-1 single-project form; used by existing unit tests)
class Config(NamedTuple):
    sources: list[SourceEntry]
    deny: list[str]


class ProjectConfig(NamedTuple):
    key: str                  # e.g. "macro-dashboard", "terminal", "mastermind"
    root: Path                # resolved absolute path (tilde-expanded + env override applied)
    visibility: str           # "shared" or "private"
    db_file: str              # e.g. "shared.sqlite"
    sources: list[SourceEntry]
    deny: list[str]           # project-specific deny patterns (hard deny always also applied)


class MultiProjectConfig(NamedTuple):
    """Parsed v2 configuration (multi-repo)."""
    projects: list[ProjectConfig]
    absent_projects: list[str]   # project keys whose root was absent/non-git at load time


# ---------------------------------------------------------------------------
# Root resolution helper
# ---------------------------------------------------------------------------


def _resolve_root(
    raw_root: str,
    root_env: Optional[str],
    config_path: Path,
) -> tuple[Optional[Path], str]:
    """
    Resolve a project root to an absolute Path.

    Priority: env var override → tilde-expanded raw_root.
    "." is resolved relative to the config file's repo root (parent of config/).

    Returns (resolved_path, reason_if_absent).
    """
    def _is_git_root(p: Path) -> bool:
        """Return True for a normal git repo (.git dir) or a git worktree (.git file)."""
        git = p / ".git"
        return git.is_dir() or git.is_file()

    # Env override wins
    if root_env:
        env_val = os.environ.get(root_env, "").strip()
        if env_val:
            p = Path(env_val).expanduser().resolve()
            if p.is_dir() and _is_git_root(p):
                return p, ""
            return None, f"env override {root_env}={env_val} not found or not a git repo"

    # "." → repo root (parent of config/)
    if raw_root == ".":
        # config_path is <repo_root>/config/context_index.yml
        repo_root = config_path.parent.parent.resolve()
        return repo_root, ""

    # Tilde-expanded external path
    p = Path(raw_root).expanduser().resolve()
    if p.is_dir() and _is_git_root(p):
        return p, ""
    return None, f"root {raw_root} not found or not a git repo"


# ---------------------------------------------------------------------------
# Config loader (v2 only)
# ---------------------------------------------------------------------------


def load_config(config_path: Path) -> MultiProjectConfig:
    """
    Load config/context_index.yml (v2 schema).

    Rejects v1 configs (schema: macro_context_index.config.v1) with a clear error.
    Returns MultiProjectConfig with projects list; absent projects are collected in
    absent_projects rather than raising (CXI-R13: absent repo = graceful skip).
    """
    with config_path.open() as f:
        raw = yaml.safe_load(f)

    schema = raw.get("schema", "")
    if schema == "macro_context_index.config.v1":
        raise ValueError(
            "config/context_index.yml uses schema v1 which is no longer supported. "
            "Update to macro_context_index.config.v2 with a top-level 'projects:' map."
        )
    if schema != "macro_context_index.config.v2":
        raise ValueError(
            f"Unrecognised config schema {schema!r}. "
            "Expected macro_context_index.config.v2."
        )

    projects_raw = raw.get("projects", {})
    if not isinstance(projects_raw, dict):
        raise ValueError("'projects:' must be a mapping in v2 config.")

    projects: list[ProjectConfig] = []
    absent: list[str] = []

    for proj_key, proj_data in projects_raw.items():
        if not isinstance(proj_data, dict):
            raise ValueError(f"Project {proj_key!r} must be a mapping.")

        raw_root = proj_data.get("root", ".")
        root_env = proj_data.get("root_env", None)
        visibility = proj_data.get("visibility", "shared")
        db_file = proj_data.get("db", "shared.sqlite")

        resolved_root, reason = _resolve_root(raw_root, root_env, config_path)
        if resolved_root is None:
            # Graceful skip — not a build failure
            absent.append(proj_key)
            continue

        # Build per-project deny list (hard deny always included)
        proj_deny = list(_HARD_DENY)
        for pat in proj_data.get("deny", []):
            if pat not in proj_deny:
                proj_deny.append(pat)

        # Parse sources
        sources: list[SourceEntry] = []
        for s in proj_data.get("sources", []):
            sources.append(SourceEntry(
                id=s["id"],
                roots=s.get("roots", []),
                authority_class=s.get("authority_class", "A3"),
                visibility=s.get("visibility", visibility),
                chunker=s.get("chunker", "markdown_sections"),
                source_type=s.get("source_type", "research"),
            ))

        projects.append(ProjectConfig(
            key=proj_key,
            root=resolved_root,
            visibility=visibility,
            db_file=db_file,
            sources=sources,
            deny=proj_deny,
        ))

    return MultiProjectConfig(projects=projects, absent_projects=absent)


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
# Discovery (DiscoveredFile)
# ---------------------------------------------------------------------------


class DiscoveredFile(NamedTuple):
    abs_path: Path
    rel_path: str
    source_id: str
    authority_class: str
    visibility: str
    chunker: str
    source_type: str
    project_key: str = "macro-dashboard"   # which project this file belongs to


def discover_files(
    project_or_config,  # ProjectConfig | Config (backwards-compat)
    repo_root: Optional[Path] = None,
) -> Iterator[tuple[DiscoveredFile | None, str | None]]:
    """
    Yield (DiscoveredFile, None) for each accepted file, or
    (None, reason_string) for each skipped file.

    Accepts either:
    - ProjectConfig (v2): uses project.root and project.deny
    - Config (v1 legacy): requires repo_root kwarg; uses hard deny + config.deny
    """
    # Normalise to a ProjectConfig-like duck type
    if isinstance(project_or_config, ProjectConfig):
        project = project_or_config
        actual_root = project.root
        deny_patterns = project.deny
        proj_key = project.key
        sources = project.sources
    else:
        # Legacy Config(sources, deny) — use deny exactly as provided (caller may omit _HARD_DENY)
        cfg: Config = project_or_config
        if repo_root is None:
            raise ValueError("repo_root is required when calling discover_files with a legacy Config")
        actual_root = repo_root
        deny_patterns = list(cfg.deny)
        proj_key = "macro-dashboard"
        sources = cfg.sources

    seen: set[Path] = set()

    for src in sources:
        if src.visibility == "private" and proj_key == "macro-dashboard":
            # CXI-1 scope: shared plane only for macro-dashboard
            continue

        for root_glob in src.roots:
            import glob as _glob
            matched = _glob.glob(
                str(actual_root / root_glob), recursive=True
            )
            if not matched:
                continue

            for abs_str in matched:
                abs_path = Path(abs_str)

                if not abs_path.is_file():
                    continue

                # Symlink safety: resolve and check inside project root
                try:
                    real = abs_path.resolve()
                except OSError:
                    yield None, f"symlink-escape:{abs_path}"
                    continue

                try:
                    real.relative_to(actual_root.resolve())
                except ValueError:
                    yield None, f"symlink-escape:{abs_path}"
                    continue

                rel = str(abs_path.relative_to(actual_root))

                # Deny check against both discovery path and resolved target
                try:
                    real_rel = str(real.relative_to(actual_root.resolve()))
                except ValueError:
                    real_rel = rel

                if _is_denied(rel, deny_patterns) or _is_denied(real_rel, deny_patterns):
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
                    project_key=proj_key,
                ), None
