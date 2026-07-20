"""Tests for CXI-R23a — brain gateway operator-allowlist internals gate.

Coverage:
  1. _internals_allowed: empty env → False
  2. _internals_allowed: spacing/case normalisation
  3. _internals_allowed: exact match — sub@domain vs domain mismatch
  4. _internals_allowed: multi-entry list; correct email matches; wrong does not
  5. Tool schemas absent for non-allowlisted (no context_* names in schema list)
  6. Tool schemas present for allowlisted (context_search + context_open present)
  7. System prompt proprietary clause present for non-allowlisted
  8. System prompt operator-internals clause present for allowlisted (refusal absent)
  9. context_open: absolute path rejected
  10. context_open: '..' traversal rejected
  11. context_open: symlink escape rejected (mocked)
  12. context_search: fail-soft when index dir missing → {available: False}
  13. No real operator emails in this test file (uses example.test domain only)
  MM_DATA_GUARD: all file I/O goes to tmp dirs; no data/ paths touched.
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import types
from unittest.mock import MagicMock, patch

import pytest

# Ensure repo root is on sys.path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import engine.neuralweb.brain_gateway as gw  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_ask_brain_module():
    """Return a minimal stub for engine.neuralweb.ask_brain."""
    m = types.ModuleType("engine.neuralweb.ask_brain")
    m._read_tool_schemas = lambda: []
    m._INJECTION_PATTERNS = []
    return m


# ---------------------------------------------------------------------------
# 1. _internals_allowed: empty env → False
# ---------------------------------------------------------------------------

def test_allowlist_empty_env_false(monkeypatch):
    monkeypatch.delenv("BRAIN_INTERNALS_ALLOWLIST", raising=False)
    assert gw._internals_allowed("op@example.test") is False


def test_allowlist_whitespace_only_env_false(monkeypatch):
    monkeypatch.setenv("BRAIN_INTERNALS_ALLOWLIST", "   ")
    assert gw._internals_allowed("op@example.test") is False


def test_allowlist_empty_email_false(monkeypatch):
    monkeypatch.setenv("BRAIN_INTERNALS_ALLOWLIST", "op@example.test")
    assert gw._internals_allowed("") is False


# ---------------------------------------------------------------------------
# 2. Spacing/case normalisation
# ---------------------------------------------------------------------------

def test_allowlist_case_normalise(monkeypatch):
    monkeypatch.setenv("BRAIN_INTERNALS_ALLOWLIST", "  OP@Example.TEST  ")
    # Both sides lowered/stripped → should match
    assert gw._internals_allowed("op@example.test") is True


def test_allowlist_env_extra_spaces(monkeypatch):
    monkeypatch.setenv("BRAIN_INTERNALS_ALLOWLIST", " op@example.test , admin@example.test ")
    assert gw._internals_allowed("admin@example.test") is True


# ---------------------------------------------------------------------------
# 3. Exact match — sub@domain vs domain mismatch
# ---------------------------------------------------------------------------

def test_allowlist_exact_match_only(monkeypatch):
    monkeypatch.setenv("BRAIN_INTERNALS_ALLOWLIST", "op@example.test")
    # Same domain, different prefix → should NOT match
    assert gw._internals_allowed("other@example.test") is False
    # Exact match → True
    assert gw._internals_allowed("op@example.test") is True


def test_allowlist_no_wildcard_domain(monkeypatch):
    # Verify we don't accidentally do domain matching
    monkeypatch.setenv("BRAIN_INTERNALS_ALLOWLIST", "example.test")
    assert gw._internals_allowed("anyone@example.test") is False


# ---------------------------------------------------------------------------
# 4. Multi-entry list
# ---------------------------------------------------------------------------

def test_allowlist_multi_entry(monkeypatch):
    monkeypatch.setenv("BRAIN_INTERNALS_ALLOWLIST", "a@example.test,b@example.test,c@example.test")
    assert gw._internals_allowed("a@example.test") is True
    assert gw._internals_allowed("b@example.test") is True
    assert gw._internals_allowed("d@example.test") is False


# ---------------------------------------------------------------------------
# 5. Tool schemas absent for non-allowlisted
# ---------------------------------------------------------------------------

def test_schemas_no_internals_for_non_allowlisted(monkeypatch, tmp_path):
    monkeypatch.delenv("BRAIN_INTERNALS_ALLOWLIST", raising=False)

    with patch.dict(sys.modules, {"engine.neuralweb.ask_brain": _fake_ask_brain_module()}):
        schemas = gw._all_brain_tool_schemas(tmp_path, page="", internals_allowed=False)

    names = {s["name"] for s in schemas}
    assert "context_search" not in names
    assert "context_open" not in names


# ---------------------------------------------------------------------------
# 6. Tool schemas present for allowlisted
# ---------------------------------------------------------------------------

def test_schemas_internals_present_for_allowlisted(monkeypatch, tmp_path):
    with patch.dict(sys.modules, {"engine.neuralweb.ask_brain": _fake_ask_brain_module()}):
        schemas = gw._all_brain_tool_schemas(tmp_path, page="", internals_allowed=True)

    names = {s["name"] for s in schemas}
    assert "context_search" in names
    assert "context_open" in names


# ---------------------------------------------------------------------------
# 7. System prompt proprietary clause present for non-allowlisted
# ---------------------------------------------------------------------------

def test_prompt_refusal_clause_for_non_allowlisted():
    prompt = gw._build_system_prompt(mode="chat", page="", internals_allowed=False)
    assert "PROPRIETARY" in prompt
    assert "Report what the signals SAY, never how they are BUILT" in prompt
    assert "OPERATOR-INTERNALS MODE" not in prompt


# ---------------------------------------------------------------------------
# 8. System prompt operator-internals clause for allowlisted (refusal absent)
# ---------------------------------------------------------------------------

def test_prompt_internals_clause_for_allowlisted():
    prompt = gw._build_system_prompt(mode="chat", page="", internals_allowed=True)
    assert "OPERATOR-INTERNALS MODE" in prompt
    # The refusal line must be gone for allowlisted sessions
    assert "Report what the signals SAY, never how they are BUILT" not in prompt


# ---------------------------------------------------------------------------
# 9. context_open: absolute path rejected
# ---------------------------------------------------------------------------

def test_context_open_rejects_absolute_path(tmp_path):
    result = gw._tool_context_open({"locator": "/etc/passwd"}, root=tmp_path)
    assert "error" in result
    assert "absolute" in result["error"].lower() or "rejected" in result["error"].lower()


# ---------------------------------------------------------------------------
# 10. context_open: '..' traversal rejected
# ---------------------------------------------------------------------------

def test_context_open_rejects_dotdot(tmp_path):
    result = gw._tool_context_open({"locator": "../../../etc/passwd"}, root=tmp_path)
    assert "error" in result
    assert "rejected" in result["error"].lower()


def test_context_open_rejects_dotdot_in_middle(tmp_path):
    result = gw._tool_context_open({"locator": "engine/../../../etc/passwd"}, root=tmp_path)
    assert "error" in result


# ---------------------------------------------------------------------------
# 11. context_open: symlink escape — resolved path outside root rejected
# ---------------------------------------------------------------------------

def test_context_open_rejects_symlink_escape(tmp_path):
    # Create a symlink inside tmp_path that points outside it
    outside = tmp_path.parent / "outside_file.txt"
    outside.write_text("secret")
    link = tmp_path / "evil_link.txt"
    link.symlink_to(outside)

    result = gw._tool_context_open({"locator": "evil_link.txt"}, root=tmp_path)
    assert "error" in result
    assert "symlink" in result["error"].lower() or "escape" in result["error"].lower() or "rejected" in result["error"].lower()


# ---------------------------------------------------------------------------
# 12. context_search: fail-soft when index dir missing → {available: False}
# ---------------------------------------------------------------------------

def test_context_search_failsoft_missing_index(tmp_path, monkeypatch):
    # Point to a tmp_path with no .context-index/ subdirectory
    monkeypatch.delenv("MACRO_CONTEXT_INDEX_DIR", raising=False)

    # The packet module may or may not be importable; either way the missing dir
    # must return {available: False} without raising.
    result = gw._tool_context_search({"query": "test query"}, root=tmp_path)
    assert result.get("available") is False
    assert "note" in result


def test_context_search_failsoft_with_corrupt_db(tmp_path, monkeypatch):
    # Create the dir + a corrupt (non-SQLite) file
    idx_dir = tmp_path / ".context-index"
    idx_dir.mkdir()
    (idx_dir / "shared.sqlite").write_text("not a sqlite file")

    monkeypatch.setenv("MACRO_CONTEXT_INDEX_DIR", str(idx_dir))

    result = gw._tool_context_search({"query": "test query"}, root=tmp_path)
    # Should fail soft: either available=False or an error key, never a raised exception
    assert result.get("available") is False or "error" in result


# ---------------------------------------------------------------------------
# 13. Smoke: context_search empty query returns error, not exception
# ---------------------------------------------------------------------------

def test_context_search_empty_query(tmp_path):
    result = gw._tool_context_search({"query": ""}, root=tmp_path)
    assert "error" in result


# ---------------------------------------------------------------------------
# 14. Internals tool names are in _BRAIN_TOOLS frozenset (dispatcher accept)
# ---------------------------------------------------------------------------

def test_internals_tools_in_brain_tools_frozenset():
    assert "context_search" in gw._BRAIN_TOOLS
    assert "context_open" in gw._BRAIN_TOOLS
    assert "context_search" in gw._BRAIN_INTERNALS_TOOLS
    assert "context_open" in gw._BRAIN_INTERNALS_TOOLS


# ---------------------------------------------------------------------------
# 15. chat() and chat_stream() accept user_email kwarg (interface check)
# ---------------------------------------------------------------------------

def test_chat_accepts_user_email_kwarg():
    """Verify user_email is a valid kwarg for gw.chat() (signature check, no network)."""
    import inspect
    sig = inspect.signature(gw.chat)
    assert "user_email" in sig.parameters


def test_chat_stream_accepts_user_email_kwarg():
    import inspect
    sig = inspect.signature(gw.chat_stream)
    assert "user_email" in sig.parameters


# ---------------------------------------------------------------------------
# 16. Finding 1 fix: available_tools in refused-tool error excludes internals
#     names for non-allowlisted sessions (CXI-R23a §3)
# ---------------------------------------------------------------------------

def test_dispatch_refused_tool_excludes_internals_names_for_non_allowlisted(tmp_path):
    """Non-allowlisted session: refused-tool error must not list context_* names."""
    result = gw._dispatch_brain_tool(
        "bogus_tool_xyz", {}, tmp_path, tmp_path, "", internals_ok=False
    )
    assert "error" in result
    tools = result.get("available_tools", [])
    assert "context_search" not in tools, "context_search must not leak to non-allowlisted session"
    assert "context_open" not in tools, "context_open must not leak to non-allowlisted session"


def test_dispatch_refused_tool_includes_internals_names_for_allowlisted(tmp_path):
    """Allowlisted session: refused-tool error may include context_* names."""
    result = gw._dispatch_brain_tool(
        "bogus_tool_xyz", {}, tmp_path, tmp_path, "", internals_ok=True
    )
    assert "error" in result
    tools = result.get("available_tools", [])
    assert "context_search" in tools
    assert "context_open" in tools


# ---------------------------------------------------------------------------
# 17. Finding 3 fix: execution-boundary auth check — internals tools refused
#     even when named directly for non-allowlisted sessions
# ---------------------------------------------------------------------------

def test_dispatch_internals_tool_refused_without_allowlist(tmp_path):
    """Direct call to context_search by name must be refused for non-allowlisted sessions."""
    result = gw._dispatch_brain_tool(
        "context_search", {"query": "test"}, tmp_path, tmp_path, "", internals_ok=False
    )
    assert "error" in result
    # Must not return results — any available_tools is fine but must not have revealed content
    assert "results" not in result


def test_dispatch_internals_tool_allowed_for_allowlisted(tmp_path, monkeypatch):
    """context_search with internals_ok=True reaches the tool fn (fail-soft on missing index)."""
    monkeypatch.delenv("MACRO_CONTEXT_INDEX_DIR", raising=False)
    result = gw._dispatch_brain_tool(
        "context_search", {"query": "test query"}, tmp_path, tmp_path, "", internals_ok=True
    )
    # Missing index → {available: False} — NOT an auth error
    assert "error" not in result or result.get("available") is not None
    assert result.get("available") is False or "results" in result


# ---------------------------------------------------------------------------
# 18. Finding 4 fix: context_search maps 'why_retrieved' correctly
# ---------------------------------------------------------------------------

def test_context_search_why_retrieved_mapped(tmp_path, monkeypatch):
    """why field in results uses why_retrieved key from packet rows."""
    monkeypatch.delenv("MACRO_CONTEXT_INDEX_DIR", raising=False)

    # Inject a mock packet module so we can control the row shape
    fake_packet = types.ModuleType("engine.context_index.packet")
    fake_packet.TOKEN_BUDGET_DEFAULT = 4000

    def _fake_build_packet(**kwargs):
        return {
            "results": [
                {
                    "locator": "engine/foo.py#bar",
                    "authority_class": "A2",
                    "status": "active",
                    "excerpt": "some excerpt",
                    "why_retrieved": "matches the governance query terms",
                    "why": "",  # old key is empty — must use why_retrieved
                }
            ],
            "index_stale": False,
            "index_sha": "abc123",
        }

    fake_packet.build_packet = _fake_build_packet

    # Create a fake index dir so the missing-dir guard doesn't fire
    idx_dir = tmp_path / ".context-index"
    idx_dir.mkdir()
    (idx_dir / "shared.sqlite").write_text("placeholder")

    with patch.dict(sys.modules, {"engine.context_index.packet": fake_packet}):
        result = gw._tool_context_search({"query": "governance query"}, root=tmp_path)

    assert "results" in result, f"expected results, got: {result}"
    assert result["results"][0]["why"] == "matches the governance query terms"


def test_context_search_excerpt_prefers_excerpt_key(tmp_path, monkeypatch):
    """excerpt field reads 'excerpt' key (not 'text') from packet rows."""
    monkeypatch.delenv("MACRO_CONTEXT_INDEX_DIR", raising=False)

    fake_packet = types.ModuleType("engine.context_index.packet")
    fake_packet.TOKEN_BUDGET_DEFAULT = 4000

    def _fake_build_packet(**kwargs):
        return {
            "results": [
                {
                    "locator": "engine/foo.py",
                    "authority_class": "A2",
                    "status": "active",
                    "excerpt": "correct excerpt text",
                    "why_retrieved": "reason",
                }
            ],
        }

    fake_packet.build_packet = _fake_build_packet

    idx_dir = tmp_path / ".context-index"
    idx_dir.mkdir()
    (idx_dir / "shared.sqlite").write_text("placeholder")

    with patch.dict(sys.modules, {"engine.context_index.packet": fake_packet}):
        result = gw._tool_context_search({"query": "test"}, root=tmp_path)

    assert result["results"][0]["excerpt"] == "correct excerpt text"
