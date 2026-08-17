#!/usr/bin/env python3
"""Repo-relative path helpers. No workstation-absolute paths in committed evidence."""
from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here.parents[2], here.parents[1], here.parents[3]):
        if (candidate / "ux-evidence").is_dir() and (
            (candidate / ".git").exists() or (candidate / ".git").is_file()
        ):
            return candidate
    raise RuntimeError("cannot derive repository root from ux-evidence/_tools/paths.py")


def evidence_root() -> Path:
    return repo_root() / "ux-evidence"


def relpath(path: Path | str) -> str:
    p = Path(path).resolve()
    root = repo_root()
    try:
        return p.relative_to(root).as_posix()
    except ValueError:
        return p.as_posix()


def abs_from_repo(rel: str) -> Path:
    rel = rel.lstrip("/")
    return (repo_root() / rel).resolve()


def is_workstation_absolute(value: str) -> bool:
    if not value or not isinstance(value, str):
        return False
    if value.startswith("file://"):
        return True
    if value.startswith("/Users/") or value.startswith("/home/") or value.startswith("/private/"):
        return True
    if len(value) >= 3 and value[1] == ":" and value[0].isalpha() and value[2] in "\\/":
        return True
    return False


def is_repo_relative(value: str) -> bool:
    if not value or not isinstance(value, str):
        return True
    if is_workstation_absolute(value):
        return False
    return True
