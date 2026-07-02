"""Display-vs-scoring manifest integrity test.

Loads data/intl_bridge/manifest.json and asserts:
  1. Every (file, symbol) pair actually exists in the repo tree.
  2. The engine/intl_feed.py module imports nothing from the scoring core
     (engine.stock_score, engine.conditions, engine.playbook).

These tests prevent the manifest from silently rotting when files are renamed
or refactored. Run in CI on every PR that touches engine/ or data/intl_bridge/.

Run: python -m pytest tests/test_manifest_seams.py -v
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "data" / "intl_bridge" / "manifest.json"
INTL_FEED_PATH = ROOT / "engine" / "intl_feed.py"

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _grep(symbol: str, filepath: Path) -> bool:
    """Return True if `symbol` appears in the file (as a definition or reference)."""
    try:
        text = filepath.read_text(errors="replace")
    except OSError:
        return False
    # Match: def symbol, class symbol, symbol =, or any bare token occurrence.
    # Broad intentionally — the test is "does this symbol exist here at all."
    return bool(re.search(r"\b" + re.escape(symbol) + r"\b", text))


# ---------------------------------------------------------------------------
# load manifest
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def manifest() -> dict:
    if not MANIFEST_PATH.exists():
        pytest.skip(f"manifest not found at {MANIFEST_PATH}")
    return json.loads(MANIFEST_PATH.read_text())


@pytest.fixture(scope="module")
def seams(manifest) -> list[dict]:
    return manifest.get("seams", [])


# ---------------------------------------------------------------------------
# parametric: every (file, symbol) must exist in the tree
# ---------------------------------------------------------------------------

def _seam_id(seam: dict) -> str:
    return f"{seam.get('file', '?')}::{seam.get('symbol', '?')}"


def pytest_generate_tests(metafunc):
    if "seam" in metafunc.fixturenames:
        if not MANIFEST_PATH.exists():
            metafunc.parametrize("seam", [], ids=[])
            return
        manifest = json.loads(MANIFEST_PATH.read_text())
        seams = manifest.get("seams", [])
        metafunc.parametrize("seam", seams, ids=[_seam_id(s) for s in seams])


def test_seam_file_exists(seam):
    """Every 'file' listed in the manifest must exist under the repo root."""
    rel = seam.get("file", "")
    assert rel, f"seam entry has no 'file' key: {seam}"
    p = ROOT / rel
    assert p.exists(), (
        f"Manifest seam file not found: {rel}\n"
        f"Seam: {seam.get('seam', '')}\n"
        f"Expected at: {p}\n"
        "Update manifest.json and DISPLAY_VS_SCORING_MANIFEST.md when files move."
    )


def test_seam_symbol_exists(seam):
    """Every 'symbol' listed in the manifest must appear in the referenced file."""
    rel = seam.get("file", "")
    symbol = seam.get("symbol", "")
    if not rel or not symbol:
        pytest.skip("seam entry missing file or symbol")

    p = ROOT / rel
    if not p.exists():
        pytest.skip(f"file not found (covered by test_seam_file_exists): {rel}")

    # Special-case: some symbols are field names / dict keys, not Python defs.
    # The grep is broad enough to catch both def/class and bare token usage.
    found = _grep(symbol, p)
    assert found, (
        f"Symbol '{symbol}' not found in {rel}\n"
        f"Seam: {seam.get('seam', '')}\n"
        "Update manifest.json and DISPLAY_VS_SCORING_MANIFEST.md when symbols are renamed."
    )


# ---------------------------------------------------------------------------
# leaf purity: intl_feed.py must not import from the scoring core
# ---------------------------------------------------------------------------

# Patterns that match actual Python import statements only (not docstring mentions).
# We check lines that START with 'import' or 'from' to avoid false positives from
# docstrings that name the forbidden modules for documentation purposes.
_FORBIDDEN_IMPORT_PATTERNS = [
    re.compile(r"^\s*(import|from)\s+engine\.stock_score\b"),
    re.compile(r"^\s*(import|from)\s+engine\.conditions\b"),
    re.compile(r"^\s*(import|from)\s+engine\.playbook\b"),
    re.compile(r"^\s*from\s+engine\s+import\s+stock_score\b"),
    re.compile(r"^\s*from\s+engine\s+import\s+conditions\b"),
    re.compile(r"^\s*from\s+engine\s+import\s+playbook\b"),
]


def test_intl_feed_leaf_purity():
    """engine/intl_feed.py must not import from the scoring core (leaf purity contract)."""
    assert INTL_FEED_PATH.exists(), f"intl_feed.py not found at {INTL_FEED_PATH}"
    lines = INTL_FEED_PATH.read_text().splitlines()
    violations = []
    for i, line in enumerate(lines, 1):
        for pat in _FORBIDDEN_IMPORT_PATTERNS:
            if pat.match(line):
                violations.append(f"  line {i}: {line.strip()}")
    assert not violations, (
        f"engine/intl_feed.py imports from the scoring core — leaf purity violated:\n"
        + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# manifest structural checks
# ---------------------------------------------------------------------------

def test_manifest_has_required_fields(manifest):
    assert "schema" in manifest, "manifest missing 'schema'"
    assert "seams" in manifest, "manifest missing 'seams'"
    assert isinstance(manifest["seams"], list), "'seams' must be a list"
    assert len(manifest["seams"]) > 0, "manifest 'seams' list is empty"


def test_every_seam_has_kind(manifest):
    for seam in manifest.get("seams", []):
        assert seam.get("kind") in ("scoring", "display"), (
            f"seam '{seam.get('seam', '?')}' has invalid kind: {seam.get('kind')!r}\n"
            "Must be 'scoring' or 'display'."
        )


def test_at_least_one_scoring_and_display_seam(manifest):
    kinds = {s.get("kind") for s in manifest.get("seams", [])}
    assert "scoring" in kinds, "manifest has no scoring seams"
    assert "display" in kinds, "manifest has no display seams"


if __name__ == "__main__":
    import pytest as _pt
    _pt.main([__file__, "-v"])
