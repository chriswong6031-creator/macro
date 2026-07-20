"""Validate docs/site_semantics/*.md — every "Computed by" backtick ref must point to an
existing file and an existing symbol in that file. Also asserts every entry has all four
required bullet keys. No network calls; pure filesystem grep.

Symbol validation for .py files uses a word-boundary pattern (finding #9, 2026-07-20):
plain `symbol in content` substring match is vacuous — 'build' passes for 'build_china',
'run' passes for 'shrunken'. For .py files we require the symbol to appear as a
definition (`def <symbol>`, `<symbol> =`, or as a standalone identifier at a word
boundary). This catches 'build' claimed against engine/market_state_cn.py (no such
def) and 'run' claimed against engine/risk_radar.py (no such def).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
SEMANTICS_DIR = REPO_ROOT / "docs" / "site_semantics"
REQUIRED_KEYS = ("**Shown as:**", "**Means:**", "**Computed by:**", "**So what:**")

# Known file extensions — only tokens ending with these are treated as file refs.
_FILE_EXT_PAT = re.compile(r"\.(py|yml|yaml|md|j2|json|html|csv|parquet)$")

# ---------------------------------------------------------------------------
# Parse helpers
# ---------------------------------------------------------------------------

def _parse_entries(md_path: Path) -> list[dict]:
    """Extract all ### entries from a glossary markdown file."""
    text = md_path.read_text(encoding="utf-8")
    parts = re.split(r"(?m)^(###\s+.+)$", text)
    entries = []
    i = 1
    while i < len(parts):
        heading = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        i += 2
        entries.append({"heading": heading, "body": body, "source": md_path.name})
    return entries


def _is_file_token(tok: str) -> bool:
    """Return True iff the backtick token looks like a file path.

    Rules (all must hold):
      - no whitespace (prose formulas like 'score = 100 × ...' excluded)
      - no '=' character (assignment literals excluded)
      - does not start with '(' (expressions like '(H+L)/2' excluded)
      - no '×' or '>' (math/comparison excluded)
      - the last path segment (basename) must end with a known file extension
      - if no '/' in the token (bare filename), must not be a dotted-attribute
        path like 'pb.dial.posture' (more than one dot and no extension is fine,
        but dotted paths with known-extension-less suffixes are attribute access)
    """
    if " " in tok:
        return False
    if "=" in tok:
        return False
    if tok.startswith("("):
        return False
    if "×" in tok or ">" in tok:
        return False
    basename = tok.split("/")[-1]
    if not _FILE_EXT_PAT.search(basename):
        return False
    # Dotted-access paths with no slash: pb.dial.posture, entry_signal.status
    # They would not have matched the extension pattern above unless they end in .py etc.
    # But if they have multiple dots and no slash, treat as attribute access.
    if "/" not in tok and tok.count(".") > 1:
        return False
    return True


def _extract_computed_by_refs(body: str) -> list[tuple[str, str]]:
    """Extract (file_path, symbol) pairs from the 'Computed by' bullet.

    A file token must satisfy _is_file_token().  Every non-file token that
    follows a file token is paired with that file as a symbol to check.
    If no symbol tokens follow a file token, a ('file', '') pair is emitted
    so that file-existence is still verified.
    """
    computed_by_pat = re.compile(
        r"\*\*Computed by:\*\*(.*?)(?=\n\s*[-*]|\Z)", re.DOTALL
    )
    m = computed_by_pat.search(body)
    if not m:
        return []
    section = m.group(1)
    tokens = re.findall(r"`([^`]+)`", section)
    if not tokens:
        return []
    pairs: list[tuple[str, str]] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if _is_file_token(tok):
            file_ref = tok
            j = i + 1
            while j < len(tokens):
                nxt = tokens[j]
                if _is_file_token(nxt):
                    break
                pairs.append((file_ref, nxt))
                j += 1
            if j == i + 1:
                pairs.append((file_ref, ""))
            i = j
        else:
            i += 1
    return pairs


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _all_entries():
    """Collect all (md_path, entry_dict) pairs for parametrize."""
    entries = []
    for md_path in sorted(SEMANTICS_DIR.glob("*.md")):
        for entry in _parse_entries(md_path):
            entries.append((md_path, entry))
    return entries


@pytest.fixture(scope="session")
def semantics_dir_exists():
    assert SEMANTICS_DIR.is_dir(), f"docs/site_semantics/ must exist: {SEMANTICS_DIR}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSemanticsStructure:
    """Every entry has all four required bullet keys."""

    @pytest.mark.parametrize("md_path,entry", _all_entries())
    def test_required_keys_present(self, md_path, entry, semantics_dir_exists):
        body = entry["body"]
        heading = entry["heading"]
        missing = [k for k in REQUIRED_KEYS if k not in body]
        assert not missing, (
            f"{md_path.name} / {heading!r} is missing required bullet(s): {missing}"
        )


class TestComputedByRefs:
    """Every 'Computed by' file ref must exist; every symbol must appear in the file."""

    @pytest.mark.parametrize("md_path,entry", _all_entries())
    def test_computed_by_files_exist(self, md_path, entry, semantics_dir_exists):
        refs = _extract_computed_by_refs(entry["body"])
        if not refs:
            return
        for file_ref, _symbol in refs:
            target = REPO_ROOT / file_ref
            assert target.exists(), (
                f"{md_path.name} / {entry['heading']!r}: "
                f"Computed by references non-existent file: {file_ref!r}"
            )

    @pytest.mark.parametrize("md_path,entry", _all_entries())
    def test_computed_by_symbols_exist_in_file(self, md_path, entry, semantics_dir_exists):
        refs = _extract_computed_by_refs(entry["body"])
        for file_ref, symbol in refs:
            if not symbol:
                continue
            target = REPO_ROOT / file_ref
            if not target.exists():
                continue  # caught by file-existence test above
            content = target.read_text(encoding="utf-8", errors="replace")

            # For Python files: require a definition-anchor match, not just a
            # substring match.  Plain `symbol in content` is vacuous — 'build'
            # matches 'build_china', 'run' matches 'shrunken'.  We require the
            # symbol to appear as a top-level def/class/variable, OR as a
            # standalone identifier at a word boundary (covers module-level
            # constants and dict keys).
            if file_ref.endswith(".py"):
                # Primary: look for `def symbol(`, `class symbol(`, or `symbol =`
                # at line start (module-level), or standalone at a word boundary.
                anchor_pat = re.compile(
                    r"(?m)(?:^(?:def|class)\s+" + re.escape(symbol) + r"\b"
                    r"|^" + re.escape(symbol) + r"\s*="
                    r"|(?<![.\w])" + re.escape(symbol) + r"(?![.\w]))"
                )
                found = bool(anchor_pat.search(content))
                assert found, (
                    f"{md_path.name} / {entry['heading']!r}: "
                    f"symbol {symbol!r} not found as a definition or standalone "
                    f"identifier in {file_ref} (bare substring match is not sufficient "
                    f"— 'build' would match 'build_china'; 'run' would match 'shrunken')"
                )
            else:
                # Non-Python files: bare substring is acceptable (YAML keys, MD
                # headings, JSON fields do not have a standard anchor syntax).
                assert symbol in content, (
                    f"{md_path.name} / {entry['heading']!r}: "
                    f"symbol {symbol!r} not found in {file_ref}"
                )


class TestGlossaryFiles:
    """Top-level sanity: all four required page files exist with enough entries."""

    @pytest.mark.parametrize("page", ["macro.md", "us_stocks.md", "china.md", "china_stocks.md"])
    def test_page_file_exists(self, page, semantics_dir_exists):
        p = SEMANTICS_DIR / page
        assert p.exists(), f"Required glossary file missing: docs/site_semantics/{page}"

    @pytest.mark.parametrize("page,min_entries", [
        ("macro.md", 8),
        ("us_stocks.md", 8),
        ("china.md", 8),
        ("china_stocks.md", 6),
    ])
    def test_page_has_minimum_entries(self, page, min_entries, semantics_dir_exists):
        p = SEMANTICS_DIR / page
        if not p.exists():
            pytest.skip(f"{page} not found")
        entries = _parse_entries(p)
        assert len(entries) >= min_entries, (
            f"docs/site_semantics/{page} has only {len(entries)} entries, expected >= {min_entries}"
        )
