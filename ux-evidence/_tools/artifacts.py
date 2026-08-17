#!/usr/bin/env python3
"""Artifact manifests: sha256 + size for every generated evidence file."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from paths import relpath

SKIP_NAMES = {"__pycache__", ".DS_Store"}
SKIP_SUFFIXES = {".pyc"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def classify(path: Path) -> str:
    name = path.name
    suffix = path.suffix.lower()
    if suffix == ".png":
        return "screenshot"
    if name == "artifact-manifest.json":
        return "artifact_manifest"
    if name.endswith("manifest.json") or name in {
        "00-meta.json",
        "run-manifest.json",
        "page-sections.json",
        "control-coverage.json",
        "source-parity.json",
        "decision-data-map.json",
        "accessibility-summary.json",
        "capture-fidelity.json",
        "evidence-index.json",
    }:
        return "manifest"
    if name.startswith("extract-"):
        return "extract"
    if suffix in {".md", ".txt"}:
        return "text"
    if suffix == ".json":
        return "json"
    return "other"


def build_manifest(
    root: Path,
    *,
    generated_by: str,
    associated_route: str | None = None,
    extra: dict | None = None,
) -> dict:
    items = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name in SKIP_NAMES or path.suffix in SKIP_SUFFIXES:
            continue
        if path.name == "artifact-manifest.json":
            continue
        rec = {
            "repo_relative_path": relpath(path),
            "artifact_type": classify(path),
            "sha256": sha256_file(path),
            "byte_size": path.stat().st_size,
            "generated_by": generated_by,
            "associated_route": associated_route,
            "associated_state": None,
            "associated_viewport": None,
        }
        name = path.name
        for token in ("1440x1000", "1280x900", "1024x800", "768x900", "390x844"):
            if token in name or token in str(path):
                rec["associated_viewport"] = token
                break
        if "FAILED_" in name:
            rec["associated_state"] = "FAILED"
        items.append(rec)
    out = {"count": len(items), "artifacts": items}
    if extra:
        out.update(extra)
    return out


def write_manifest(root: Path, **kwargs) -> Path:
    dest = root / "artifact-manifest.json"
    dest.write_text(json.dumps(build_manifest(root, **kwargs), indent=2, ensure_ascii=False) + "\n")
    return dest


def verify_manifest(root: Path) -> list[str]:
    path = root / "artifact-manifest.json"
    if not path.exists():
        return ["missing artifact-manifest.json"]
    data = json.loads(path.read_text())
    errors = []
    seen = set()
    for item in data.get("artifacts") or []:
        rel = item.get("repo_relative_path")
        if not rel:
            errors.append("artifact missing repo_relative_path")
            continue
        seen.add(rel)
        fp = Path(rel)
        # resolve against repo root via the dossier path
        candidate = root
        # walk up to repo
        repo = root
        while repo.parent != repo and not (repo / ".git").exists() and not (repo / "ux-evidence").exists():
            repo = repo.parent
        if (repo / "ux-evidence").exists() and not (repo / ".git").exists():
            repo = repo  # evidence-only?
        full = (repo / rel) if not Path(rel).is_absolute() else Path(rel)
        if not full.exists():
            # try relative to dossier parent chain
            alt = None
            for p in [root, *root.parents]:
                if (p / rel).exists():
                    alt = p / rel
                    break
                if rel.startswith("ux-evidence/") and (p / rel.split("/", 1)[-1]).exists():
                    alt = p / rel.split("/", 1)[-1]
                    break
            full = alt or full
        if not full.exists():
            errors.append(f"artifact missing on disk: {rel}")
            continue
        actual = sha256_file(full)
        if actual != item.get("sha256"):
            errors.append(f"artifact hash mismatch: {rel}")
        if full.stat().st_size != item.get("byte_size"):
            errors.append(f"artifact size mismatch: {rel}")
    return errors
