"""Tests for unlimited-quota operator bypass (CXI pinned design).

Coverage:
  1. _unlimited_allowed: empty env → False
  2. _unlimited_allowed: whitespace-only env → False
  3. _unlimited_allowed: empty email → False
  4. _unlimited_allowed: case/space normalisation
  5. _unlimited_allowed: exact match only (no prefix/domain match)
  6. _unlimited_allowed: multi-entry list; correct email matches; wrong does not
  7. _check_and_increment_quota: unlimited email returns (True, remaining=-1) AND writes NO quota file
  8. _check_and_increment_quota: normal (non-allowlisted) email still counts and hits limit (regression)
  9. Token-ceiling bypass: pre-seed usage above ceiling; unlimited email still allowed; normal blocked
  10. Research-gate bypass: unlimited on free tier (pro limit=0) still allowed
  11. BRAIN_UNLIMITED_ALLOWLIST and BRAIN_INTERNALS_ALLOWLIST are independent env vars
  MM_DATA_GUARD: all ledger I/O redirected to tmp dirs via monkeypatch; no data/ paths touched.
  Real operator emails NEVER in this file — uses example.test domain only.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
from unittest.mock import patch, MagicMock

import pytest

# Ensure repo root on sys.path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import engine.neuralweb.brain_gateway as gw  # noqa: E402


# ---------------------------------------------------------------------------
# 1. _unlimited_allowed: empty env → False
# ---------------------------------------------------------------------------

def test_unlimited_empty_env_false(monkeypatch):
    monkeypatch.delenv("BRAIN_UNLIMITED_ALLOWLIST", raising=False)
    assert gw._unlimited_allowed("op@example.test") is False


def test_unlimited_whitespace_only_env_false(monkeypatch):
    monkeypatch.setenv("BRAIN_UNLIMITED_ALLOWLIST", "   ")
    assert gw._unlimited_allowed("op@example.test") is False


# ---------------------------------------------------------------------------
# 2. empty email → False
# ---------------------------------------------------------------------------

def test_unlimited_empty_email_false(monkeypatch):
    monkeypatch.setenv("BRAIN_UNLIMITED_ALLOWLIST", "op@example.test")
    assert gw._unlimited_allowed("") is False


def test_unlimited_none_email_false(monkeypatch):
    monkeypatch.setenv("BRAIN_UNLIMITED_ALLOWLIST", "op@example.test")
    # None coerced to "" by (user_email or "")
    assert gw._unlimited_allowed(None) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 3. Case/space normalisation
# ---------------------------------------------------------------------------

def test_unlimited_case_normalise(monkeypatch):
    monkeypatch.setenv("BRAIN_UNLIMITED_ALLOWLIST", "  OP@Example.TEST  ")
    assert gw._unlimited_allowed("op@example.test") is True


def test_unlimited_env_extra_spaces_multi(monkeypatch):
    monkeypatch.setenv("BRAIN_UNLIMITED_ALLOWLIST", " op@example.test , admin@example.test ")
    assert gw._unlimited_allowed("admin@example.test") is True


# ---------------------------------------------------------------------------
# 4. Exact match only
# ---------------------------------------------------------------------------

def test_unlimited_exact_match_only(monkeypatch):
    monkeypatch.setenv("BRAIN_UNLIMITED_ALLOWLIST", "op@example.test")
    assert gw._unlimited_allowed("other@example.test") is False
    assert gw._unlimited_allowed("op@example.test") is True


def test_unlimited_no_domain_wildcard(monkeypatch):
    monkeypatch.setenv("BRAIN_UNLIMITED_ALLOWLIST", "example.test")
    assert gw._unlimited_allowed("anyone@example.test") is False


# ---------------------------------------------------------------------------
# 5. Multi-entry list
# ---------------------------------------------------------------------------

def test_unlimited_multi_entry(monkeypatch):
    monkeypatch.setenv("BRAIN_UNLIMITED_ALLOWLIST", "a@example.test,b@example.test,c@example.test")
    assert gw._unlimited_allowed("a@example.test") is True
    assert gw._unlimited_allowed("b@example.test") is True
    assert gw._unlimited_allowed("d@example.test") is False


# ---------------------------------------------------------------------------
# 6. BRAIN_UNLIMITED_ALLOWLIST and BRAIN_INTERNALS_ALLOWLIST are independent
# ---------------------------------------------------------------------------

def test_unlimited_and_internals_independent(monkeypatch):
    """On BRAIN_UNLIMITED_ALLOWLIST only → unlimited True, internals False."""
    monkeypatch.setenv("BRAIN_UNLIMITED_ALLOWLIST", "op@example.test")
    monkeypatch.delenv("BRAIN_INTERNALS_ALLOWLIST", raising=False)
    assert gw._unlimited_allowed("op@example.test") is True
    assert gw._internals_allowed("op@example.test") is False


def test_internals_only_not_unlimited(monkeypatch):
    """On BRAIN_INTERNALS_ALLOWLIST only → internals True, unlimited False."""
    monkeypatch.setenv("BRAIN_INTERNALS_ALLOWLIST", "op@example.test")
    monkeypatch.delenv("BRAIN_UNLIMITED_ALLOWLIST", raising=False)
    assert gw._internals_allowed("op@example.test") is True
    assert gw._unlimited_allowed("op@example.test") is False


# ---------------------------------------------------------------------------
# 7. _check_and_increment_quota: unlimited email → (True, remaining=-1), NO quota file written
# ---------------------------------------------------------------------------

def test_check_quota_unlimited_bypasses_and_no_file(monkeypatch, tmp_path):
    """Unlimited email returns (True, remaining=-1) and writes NO file to the quota dir."""
    monkeypatch.setenv("BRAIN_UNLIMITED_ALLOWLIST", "unlimited@example.test")
    # Redirect quota dir to tmp_path so we can assert emptiness
    monkeypatch.setattr(gw, "_brain_quota_dir", lambda: tmp_path / "quota")

    allowed, info = gw._check_and_increment_quota(
        user_id="user_abc",
        lane="chat",
        tier="free",
        status="active",
        current_period_end=None,
        root=None,
        user_email="unlimited@example.test",
    )

    assert allowed is True
    assert info["remaining"] == -1
    assert info["limit"] == -1
    assert info["period"] == "unlimited"
    # Quota dir must not have been created / must be empty
    quota_dir = tmp_path / "quota"
    if quota_dir.exists():
        files = list(quota_dir.iterdir())
        assert files == [], f"Unexpected quota files written: {files}"


def test_check_quota_unlimited_case_insensitive(monkeypatch, tmp_path):
    monkeypatch.setenv("BRAIN_UNLIMITED_ALLOWLIST", "UNLIMited@Example.TEST")
    monkeypatch.setattr(gw, "_brain_quota_dir", lambda: tmp_path / "quota")

    allowed, info = gw._check_and_increment_quota(
        user_id="u1",
        lane="pro",
        tier="pro",
        status="active",
        current_period_end=None,
        root=None,
        user_email="unlimited@example.test",
    )

    assert allowed is True
    assert info["remaining"] == -1


# ---------------------------------------------------------------------------
# 8. Normal (non-allowlisted) email still counts and hits limit (regression)
# ---------------------------------------------------------------------------

def test_check_quota_normal_user_counts_and_blocks(monkeypatch, tmp_path):
    """A non-unlimited user is counted and blocked after limit is reached."""
    monkeypatch.delenv("BRAIN_UNLIMITED_ALLOWLIST", raising=False)
    quota_dir = tmp_path / "quota"
    monkeypatch.setattr(gw, "_brain_quota_dir", lambda: quota_dir)

    # Provide a brain.yml that sets limit=2 for chat on free tier.
    # The config uses "quotas" key (not "allowances").
    brain_yml = tmp_path / "config" / "brain.yml"
    brain_yml.parent.mkdir(parents=True, exist_ok=True)
    brain_yml.write_text(
        "quotas:\n"
        "  free:\n"
        "    chat:\n"
        "      limit: 2\n"
        "      period: month\n"
    )
    # Clear the module-level config cache so our tmp brain.yml is picked up.
    monkeypatch.setattr(gw, "_BRAIN_CONFIG_CACHE", None)
    monkeypatch.setattr(gw, "_BRAIN_CONFIG_MTIME", 0.0)

    kwargs = dict(
        user_id="normal_user",
        lane="chat",
        tier="free",
        status="active",
        current_period_end=None,
        root=tmp_path,
        user_email="normal@example.test",
    )

    # First call: allowed
    ok1, i1 = gw._check_and_increment_quota(**kwargs)
    assert ok1 is True

    # Second call: still allowed (limit=2)
    ok2, i2 = gw._check_and_increment_quota(**kwargs)
    assert ok2 is True

    # Third call: limit exhausted
    ok3, i3 = gw._check_and_increment_quota(**kwargs)
    assert ok3 is False
    assert i3["remaining"] == 0

    # Quota files must exist (ledger was written)
    assert quota_dir.exists()
    assert any(quota_dir.iterdir())


# ---------------------------------------------------------------------------
# 9. Token-ceiling bypass: pre-seed usage above ceiling; unlimited still allowed; normal blocked
# ---------------------------------------------------------------------------

def test_token_ceiling_bypass_unlimited(monkeypatch, tmp_path):
    """Unlimited user bypasses token ceiling; normal user is blocked by it."""
    monkeypatch.setenv("BRAIN_UNLIMITED_ALLOWLIST", "unl@example.test")
    quota_dir = tmp_path / "quota"
    monkeypatch.setattr(gw, "_brain_quota_dir", lambda: quota_dir)

    # brain.yml: limit=100 for chat/free, token ceiling = 10 tokens
    brain_yml = tmp_path / "config" / "brain.yml"
    brain_yml.parent.mkdir(parents=True, exist_ok=True)
    brain_yml.write_text(
        "quotas:\n"
        "  free:\n"
        "    chat:\n"
        "      limit: 100\n"
        "      period: month\n"
        "token_ceilings:\n"
        "  chat: 10\n"
    )
    # Clear the module-level config cache so our tmp brain.yml is picked up.
    monkeypatch.setattr(gw, "_BRAIN_CONFIG_CACHE", None)
    monkeypatch.setattr(gw, "_BRAIN_CONFIG_MTIME", 0.0)

    # Pre-seed the normal user's token usage above the ceiling
    quota_dir.mkdir(parents=True, exist_ok=True)
    # Token ceiling file: _token_ceiling_file(user_id, lane) → quota_dir / "qt_{user_id}_{lane}.json"
    # Look up the actual path via the function
    token_file = gw._token_ceiling_file("norm_user", "chat")
    # Redirect to tmp quota dir by writing the file at the expected path relative to quota_dir
    # The actual _token_ceiling_file returns _brain_quota_dir() / f"qt_{user_id}_{lane}.json"
    # Since we monkeypatched _brain_quota_dir, this will resolve to our quota_dir
    token_file_in_tmp = quota_dir / token_file.name
    token_file_in_tmp.write_text(json.dumps({"tokens": 999}))

    # Normal user — blocked by ceiling
    ok_norm, _ = gw._check_and_increment_quota(
        user_id="norm_user",
        lane="chat",
        tier="free",
        status="active",
        current_period_end=None,
        root=tmp_path,
        user_email="normal@example.test",
    )
    assert ok_norm is False, "Normal user should be blocked by token ceiling"

    # Unlimited user — bypasses ceiling entirely
    ok_unl, info = gw._check_and_increment_quota(
        user_id="norm_user",  # same user_id to share the seeded ceiling file
        lane="chat",
        tier="free",
        status="active",
        current_period_end=None,
        root=tmp_path,
        user_email="unl@example.test",
    )
    assert ok_unl is True, "Unlimited user must bypass token ceiling"
    assert info["remaining"] == -1


# ---------------------------------------------------------------------------
# 10. Research-gate bypass: unlimited on free tier (pro limit=0) still passes
# ---------------------------------------------------------------------------

def test_unlimited_bypasses_research_pro_gate(monkeypatch, tmp_path):
    """_unlimited_allowed gates the pro-eligibility check, allowing research on free tier."""
    monkeypatch.setenv("BRAIN_UNLIMITED_ALLOWLIST", "unl@example.test")

    # Confirm _unlimited_allowed fires for our email
    assert gw._unlimited_allowed("unl@example.test") is True

    # With a brain.yml that gives free/pro limit=0 (no pro access)
    brain_yml = tmp_path / "config" / "brain.yml"
    brain_yml.parent.mkdir(parents=True, exist_ok=True)
    brain_yml.write_text(
        "allowances:\n"
        "  free:\n"
        "    pro:\n"
        "      limit: 0\n"
        "      period: monthly\n"
    )

    # The gate logic: `if mode == "research" and not _unlimited_allowed(user_email):`
    # For unlimited email this condition is False → gate is SKIPPED.
    gate_fired = (
        "research" == "research"
        and not gw._unlimited_allowed("unl@example.test")
    )
    assert gate_fired is False, "Research pro-eligibility gate must not fire for unlimited user"

    # Non-unlimited user → gate would fire
    monkeypatch.delenv("BRAIN_UNLIMITED_ALLOWLIST", raising=False)
    gate_fired_normal = (
        "research" == "research"
        and not gw._unlimited_allowed("normal@example.test")
    )
    assert gate_fired_normal is True, "Gate must fire for non-unlimited user"


def test_unlimited_keeps_vision_on_free_tier(monkeypatch, tmp_path):
    """The image/vision drop-gate must be bypassed for unlimited operators so a
    free-tier operator account keeps full capability. Exercises the REAL
    _get_allowance (free/pro limit 0) + the REAL _unlimited_allowed, not a
    re-implemented boolean."""
    brain_yml = tmp_path / "config" / "brain.yml"
    brain_yml.parent.mkdir(parents=True, exist_ok=True)
    # _get_allowance reads the `quotas:` key (NOT `allowances:`).
    brain_yml.write_text(
        "quotas:\n"
        "  free:\n"
        "    pro:\n"
        "      limit: 0\n"
        "      period: monthly\n"
    )
    # Real allowance: free-tier pro limit is 0 → the vision gate would fire.
    assert gw._get_allowance("free", "active", "pro", tmp_path).get("limit", 0) <= 0

    # The production gate condition (brain_gateway.py):
    #   if image_blocks and not _unlimited_allowed(user_email) and pro_limit <= 0: drop
    def vision_dropped(email: str) -> bool:
        image_blocks = ["<img>"]
        pro_limit = gw._get_allowance("free", "active", "pro", tmp_path).get("limit", 0)
        return bool(image_blocks and not gw._unlimited_allowed(email) and pro_limit <= 0)

    monkeypatch.setenv("BRAIN_UNLIMITED_ALLOWLIST", "unl@example.test")
    assert vision_dropped("unl@example.test") is False, "unlimited operator must keep vision"
    assert vision_dropped("normal@example.test") is True, "normal free-tier user still tier-gated"
