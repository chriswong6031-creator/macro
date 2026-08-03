"""Verify the finite D0a BioCatalyst reference corpus without a product release.

``--reference-integrity`` proves committed references, hashes, finite state coverage,
PNG dimensions, bounded masks, and exact renderer/data byte bindings. ``--acceptance``
additionally invokes the semantic contract, whose v1 independent-verifier gate is
unconditional. This separation prevents any self-described manifest from turning a
pretty mockup into a launch approval.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.sector_intelligence.contracts import (  # noqa: E402
    ContractValidationError,
    canonical_json_sha256,
    validate_contract,
)

CONFIG = ROOT / "config" / "biocatalyst_product_acceptance.yml"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _png_size(path: Path) -> tuple[int, int]:
    raw = path.read_bytes()
    if raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR":
        raise ValueError(f"{path}: not a PNG with an IHDR header")
    return struct.unpack(">II", raw[16:24])


def _document() -> dict:
    loaded = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("product acceptance manifest must be a mapping")
    return loaded


def _bound_path(relative: str) -> Path:
    candidate = (ROOT / relative).resolve()
    if ROOT not in candidate.parents and candidate != ROOT:
        raise ValueError(f"path escapes repository: {relative}")
    return candidate


def reference_integrity_issues(document: dict) -> list[str]:
    issues: list[str] = []
    visual = document.get("visual", {})
    cells = visual.get("cells", []) if isinstance(visual, dict) else []
    seen: set[tuple[str, str, str, str]] = set()
    expected_states = set(visual.get("required_state_codes", [])) if isinstance(visual, dict) else set()
    seen_states: set[str] = set()
    for cell in cells:
        if not isinstance(cell, dict):
            issues.append("visual cell is not a mapping")
            continue
        viewport = cell.get("viewport", {})
        if not isinstance(viewport, dict):
            issues.append(f"{cell.get('id', '?')}: viewport missing")
            continue
        combo = (str(viewport.get("name")), str(cell.get("theme")), str(cell.get("language")), str(cell.get("motion")))
        if combo in seen:
            issues.append(f"{cell.get('id', '?')}: duplicate viewport/theme/language/motion cell")
        seen.add(combo)
        seen_states.add(str(cell.get("ui_state")))
        image = _bound_path(str(cell.get("reference_png_path", "")))
        if not image.is_file():
            issues.append(f"{cell.get('id', '?')}: missing reference PNG {image.relative_to(ROOT)}")
            continue
        if _sha256(image) != cell.get("reference_png_sha256"):
            issues.append(f"{cell.get('id', '?')}: reference PNG SHA-256 mismatch")
        try:
            dimensions = _png_size(image)
        except ValueError as exc:
            issues.append(str(exc))
            continue
        if dimensions != (viewport.get("width"), viewport.get("height")):
            issues.append(f"{cell.get('id', '?')}: image dimensions {dimensions} do not match frozen viewport")
        viewport_area = int(viewport.get("width", 0)) * int(viewport.get("height", 0))
        for mask in cell.get("masks", []):
            if not isinstance(mask, dict):
                issues.append(f"{cell.get('id', '?')}: non-mapping mask")
                continue
            x, y = mask.get("x"), mask.get("y")
            width, height = mask.get("width"), mask.get("height")
            if not all(isinstance(value, int) and not isinstance(value, bool) for value in (x, y, width, height)):
                issues.append(f"{cell.get('id', '?')}: mask coordinates must be finite integers")
                continue
            if x < 0 or y < 0 or width < 1 or height < 1 or x + width > viewport.get("width", 0) or y + height > viewport.get("height", 0):
                issues.append(f"{cell.get('id', '?')}: mask escapes frozen viewport")
            elif width * height > viewport_area * 0.08:
                issues.append(f"{cell.get('id', '?')}: mask exceeds 8% of viewport area")
    required_combos = {
        (viewport, theme, language, motion)
        for viewport in ("desktop", "tablet", "mobile")
        for theme in ("dark", "light")
        for language in ("en", "zh")
        for motion in ("standard", "reduced")
    }
    if seen != required_combos:
        issues.append("visual cells are not exactly the required 3×2×2×2 matrix")
    if seen_states != expected_states:
        issues.append("visual cells do not cover exactly the frozen required state codes")
    for binding_name in ("reference_fixture", "benchmark_corpus"):
        binding = document.get(binding_name, {})
        if not isinstance(binding, dict):
            issues.append(f"{binding_name}: missing binding")
            continue
        path = _bound_path(str(binding.get("path", "")))
        if not path.is_file() or _sha256(path) != binding.get("sha256"):
            issues.append(f"{binding_name}: file/hash binding does not match")
    renderer = visual.get("renderer_source", {}) if isinstance(visual, dict) else {}
    if isinstance(renderer, dict):
        renderer_path = _bound_path(str(renderer.get("path", "")))
        if (
            renderer.get("path") != "mockups/refs/biocatalyst/d0a/render_reference.py"
            or not renderer_path.is_file()
            or _sha256(renderer_path) != renderer.get("sha256")
        ):
            issues.append("visual renderer: exact source-byte binding does not match")
    else:
        issues.append("visual renderer: missing source-byte binding")
    artifact = visual.get("artifact", {}) if isinstance(visual, dict) else {}
    if isinstance(artifact, dict):
        path = _bound_path(str(artifact.get("path", "")))
        if not path.is_file() or _sha256(path) != artifact.get("sha256"):
            issues.append("visual artifact: file/hash binding does not match")
        else:
            try:
                receipt = json.loads(path.read_text(encoding="utf-8"))
                benchmark = document["benchmark_corpus"]
                corpus = json.loads(_bound_path(benchmark["path"]).read_text(encoding="utf-8"))
                if (
                    receipt.get("renderer", {}).get("entrypoint") != renderer.get("path")
                    or receipt.get("renderer", {}).get("source_sha256") != renderer.get("sha256")
                    or receipt.get("fixture", {}).get("path") != document["reference_fixture"]["path"]
                    or receipt.get("fixture", {}).get("sha256") != document["reference_fixture"]["sha256"]
                    or receipt.get("projection", {}).get("path") != corpus.get("projection_path")
                    or receipt.get("projection", {}).get("sha256") != corpus.get("projection_sha256")
                ):
                    issues.append("visual artifact: renderer/fixture/projection byte bindings do not match")
            except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
                issues.append("visual artifact: receipt or bound benchmark is not valid JSON")
    else:
        issues.append("visual artifact: missing binding")
    payload = {key: value for key, value in document.items() if key not in {"manifest_id", "content_sha256"}}
    digest = canonical_json_sha256(payload)
    if document.get("content_sha256") != digest:
        issues.append("manifest content SHA-256 does not match canonical payload")
    if document.get("manifest_id") != f"biocatalyst_product_acceptance_{digest[:24]}":
        issues.append("manifest ID does not derive from canonical payload SHA-256")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-integrity", action="store_true")
    parser.add_argument("--acceptance", action="store_true")
    args = parser.parse_args()
    if not args.reference_integrity and not args.acceptance:
        parser.error("choose --reference-integrity or --acceptance")
    document = _document()
    issues = reference_integrity_issues(document)
    if issues:
        print("D0a reference integrity failed:")
        for issue in issues:
            print(f"- {issue}")
        return 2
    print("D0a reference integrity: PASS (finite corpus and hashes match)")
    if args.acceptance:
        try:
            validate_contract(document, repo_root=ROOT)
        except ContractValidationError as exc:
            print(f"D0a product acceptance: BLOCKED — {exc}")
            return 3
        print("D0a product acceptance: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
