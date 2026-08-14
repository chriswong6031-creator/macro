#!/usr/bin/env python3
"""Canonical path contract for code that can manufacture CI proof.

The trusted-base authority gate and the older self-modification fence must use
one pattern inventory.  Keeping that inventory here prevents a new planner,
indexer, failure classifier, or workflow from being protected by one fence but
not the other.
"""

from __future__ import annotations

import fnmatch
import unicodedata
from collections.abc import Iterable
from pathlib import PurePosixPath


class AuthorityPathError(ValueError):
    """A GitHub-supplied path is not a safe canonical repository path."""


# Paths capable of selecting, executing, summarizing, or admitting CI proof.
# Directory patterns deliberately cover files that do not exist yet: creating a
# new workflow or replacing the committed scope index is itself authority.
CI_AUTHORITY_PATTERNS: tuple[str, ...] = (
    ".github/ci/**",
    ".github/workflows/**",
    # CI authorities are invoked as ``python scripts/foo.py``. Python prepends
    # that directory to sys.path, so a candidate ``scripts/json.py`` or
    # ``scripts/argparse.py`` can shadow a stdlib import before an exact-list
    # authority ever starts. Protect the whole executable directory; enumerating
    # today's entrypoints is structurally bypassable by tomorrow's import name.
    "scripts/**",
    # Pytest startup hooks and dependency/bootstrap manifests can make every
    # logical test return success without changing the protected planner. Treat
    # them as executable CI authority, not ordinary full-suite invalidators.
    "conftest.py",
    "**/conftest.py",
    "sitecustomize.py",
    "usercustomize.py",
    "pytest.ini",
    "**/pytest.ini",
    "pyproject.toml",
    "**/pyproject.toml",
    "setup.cfg",
    "**/setup.cfg",
    "setup.py",
    "**/setup.py",
    "tox.ini",
    "**/tox.ini",
    "requirements*.txt",
    "**/requirements*.txt",
    "constraints*.txt",
    "**/constraints*.txt",
    "uv.lock",
    "**/uv.lock",
    "poetry.lock",
    "**/poetry.lock",
    "package.json",
    "**/package.json",
    "package-lock.json",
    "**/package-lock.json",
)


def canonical_repo_path(value: object) -> str:
    """Return a strict repository-relative POSIX path or raise.

    GitHub's files API is the authority for the changed-file inventory.  We do
    not normalize its values before classification: two spellings that would
    normalize to the same path are rejected, as are control/format characters
    that could make logs or glob review misleading.
    """
    if type(value) is not str or not value:
        raise AuthorityPathError("path must be a non-empty string")
    if len(value.encode("utf-8")) > 4096:
        raise AuthorityPathError("path exceeds the 4096-byte safety bound")
    if unicodedata.normalize("NFC", value) != value:
        raise AuthorityPathError("path is not NFC-normalized")
    if any(
        unicodedata.category(character) in {"Cc", "Cf", "Cs", "Zl", "Zp"}
        for character in value
    ):
        raise AuthorityPathError("path contains a control or formatting character")
    if value.startswith("/") or value.endswith("/") or "\\" in value:
        raise AuthorityPathError("path must be repository-relative POSIX")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise AuthorityPathError("path contains an empty or relative segment")
    if PurePosixPath(value).as_posix() != value:
        raise AuthorityPathError("path is not canonical POSIX")
    return value


def matches_pattern_set(path: str, patterns: Iterable[str]) -> bool:
    """Match a canonical path against exact/glob and recursive-tree patterns."""
    for pattern in patterns:
        if pattern.endswith("/**"):
            root = pattern[:-3].rstrip("/")
            if path == root or path.startswith(root + "/"):
                return True
        elif fnmatch.fnmatchcase(path, pattern):
            return True
    return False


def is_ci_authority_path(value: object) -> bool:
    """Classify one untrusted API path using the shared authority inventory."""
    path = canonical_repo_path(value)
    return matches_pattern_set(path, CI_AUTHORITY_PATTERNS)
