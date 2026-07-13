"""tests/test_preflight_claude_resolve.py — claude CLI binary resolution.

The self-hosted runner daemon inherits a minimal launchd PATH that omits
per-user bin dirs, so a bare "claude" invocation raised FileNotFoundError
even with the CLI installed at ~/.local/bin/claude (first armed PROPOSE
cycle, 2026-07-13).  resolve_claude_bin() must prefer PATH, fall back to
known install locations, and degrade to the bare name.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

from scripts.preflight_claude_auth import resolve_claude_bin


def test_path_hit_wins(monkeypatch) -> None:
    """When `claude` is on PATH, shutil.which's answer is returned as-is."""
    import shutil
    monkeypatch.setattr(shutil, "which", lambda name: "/fake/path/claude")
    assert resolve_claude_bin() == "/fake/path/claude"


def test_candidate_fallback(monkeypatch, tmp_path: Path) -> None:
    """PATH miss → first existing executable candidate wins."""
    import shutil
    import scripts.preflight_claude_auth as pf
    monkeypatch.setattr(shutil, "which", lambda name: None)
    fake = tmp_path / "claude"
    fake.write_text("#!/bin/sh\necho pong\n", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr(
        pf, "_CLAUDE_BIN_CANDIDATES",
        (str(tmp_path / "missing"), str(fake)),
    )
    assert resolve_claude_bin() == str(fake)


def test_bare_name_fallback(monkeypatch) -> None:
    """PATH miss + no candidates → bare name (original error path preserved)."""
    import shutil
    import scripts.preflight_claude_auth as pf
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr(pf, "_CLAUDE_BIN_CANDIDATES", ())
    assert resolve_claude_bin() == "claude"


def test_never_raises(monkeypatch) -> None:
    import shutil
    def _boom(name):  # noqa: ANN001
        raise RuntimeError("which exploded")
    monkeypatch.setattr(shutil, "which", _boom)
    assert resolve_claude_bin() == "claude"


def test_check_auth_flags_cli_missing(monkeypatch) -> None:
    """FileNotFoundError ping → auth_ok=False AND cli_missing=True, so
    SDK-channel stages (PROPOSE/ADJUDICATE) can proceed on their own channel."""
    import scripts.preflight_claude_auth as pf
    import engine.neuralweb.capability_broker as cb
    monkeypatch.setattr(cb, "resolve", lambda cid, lane, root=None: {
        "allowed": True, "reason": "ok", "ref_name": "FAKE_TOKEN_ENV"})
    monkeypatch.setattr(cb, "audit", lambda *a, **k: None)
    monkeypatch.setenv("FAKE_TOKEN_ENV", "tok")
    monkeypatch.setattr(pf, "_run_ping_check", lambda ref: (
        False, pf.CLI_MISSING_PREFIX + " — cannot verify OAuth token health."))
    monkeypatch.setattr(pf, "_notify_auth_failure", lambda reason: None)
    result = pf.check_auth(lane="test-lane")
    assert result["auth_ok"] is False
    assert result["cli_missing"] is True


def test_check_auth_dead_token_not_cli_missing(monkeypatch) -> None:
    """A live CLI reporting a dead token must stay fail-closed (no flag)."""
    import scripts.preflight_claude_auth as pf
    import engine.neuralweb.capability_broker as cb
    monkeypatch.setattr(cb, "resolve", lambda cid, lane, root=None: {
        "allowed": True, "reason": "ok", "ref_name": "FAKE_TOKEN_ENV"})
    monkeypatch.setattr(cb, "audit", lambda *a, **k: None)
    monkeypatch.setenv("FAKE_TOKEN_ENV", "tok")
    monkeypatch.setattr(pf, "_run_ping_check", lambda ref: (
        False, "claude -p ping exited 1: authentication_error"))
    monkeypatch.setattr(pf, "_notify_auth_failure", lambda reason: None)
    result = pf.check_auth(lane="test-lane")
    assert result["auth_ok"] is False
    assert result.get("cli_missing") is False


def test_build_session_cmd_uses_resolved_bin(monkeypatch) -> None:
    """metabolism_build._build_session_cmd embeds the resolved binary."""
    import scripts.preflight_claude_auth as pf
    monkeypatch.setattr(pf, "resolve_claude_bin", lambda: "/resolved/claude")
    from scripts.metabolism_build import _build_session_cmd
    cmd = _build_session_cmd("do the thing")
    assert "/resolved/claude" in cmd
    assert "claude" not in cmd  # the bare name must be fully replaced
    assert cmd[-1] == "do the thing"
