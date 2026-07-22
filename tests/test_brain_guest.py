"""Tests for Brain guest access — anonymous free Fast lane + free-tier daily flip.

Covers (per the guest-access build spec):
  * _guest_cfg: default fail-closed, env override, clamp bounds, TTL cache honors updates
  * "day" period key
  * Guest dual cookie+IP ledger: enable/disable, day-key rollover, max() blocking
    (cookie cleared → same IP still capped), fast-only lane lock
  * Free-tier fast allowance flips to daily_limit/day when enabled, reverts when disabled
  * Guest restrictions: pro locked, research rejected, no internals tools (CXI-R23),
    no thread-store writes (stateless)
  * get_guest_quotas / me shape
  * admin store (admin/brain_guest.py): write+validate+read, atomic bytes

All offline (no network, no keys). Model mocked where chat() is exercised.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from engine.neuralweb import brain_gateway as gw  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_temp_root() -> pathlib.Path:
    d = pathlib.Path(tempfile.mkdtemp())
    nw = d / "data" / "neuralweb"
    nw.mkdir(parents=True, exist_ok=True)
    (nw / "world_state.json").write_text(json.dumps({"verdict": "RISK_OFF", "regime": "Q1", "score": 34}))
    cortex = nw / "cortex"
    cortex.mkdir(parents=True, exist_ok=True)
    (cortex / "memo.json").write_text(json.dumps({"schema": "neuralweb.cortex_memo.v1", "summary": "T.", "what_fired": []}))
    return d


class _MockUsage:
    def __init__(self, input_tokens=10, output_tokens=20):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _MockBlock:
    def __init__(self, type_, text="", name="", input_=None, id_="tid1"):
        self.type = type_
        self.text = text
        self.name = name
        self.input = input_ or {}
        self.id = id_


class _MockResponse:
    def __init__(self, content, stop_reason="end_turn", usage=None):
        self.content = content
        self.stop_reason = stop_reason
        self.usage = usage or _MockUsage()


class _MockClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self._i = 0
        self.messages = self

    def create(self, **kwargs):
        if self._i >= len(self._responses):
            return _MockResponse([_MockBlock("text", "Default.")], "end_turn")
        r = self._responses[self._i]
        self._i += 1
        return r


@pytest.fixture(autouse=True)
def _reset_guest_cache():
    """Every test starts with a cold guest-cfg cache + a private cfg path env, and restores it."""
    prev = os.environ.get("BRAIN_GUEST_CFG")
    gw._GUEST_CFG_CACHE = None
    yield
    gw._GUEST_CFG_CACHE = None
    if prev is None:
        os.environ.pop("BRAIN_GUEST_CFG", None)
    else:
        os.environ["BRAIN_GUEST_CFG"] = prev


def _write_cfg(tmp_path, enabled, daily_limit):
    p = tmp_path / "brain_guest_access.json"
    p.write_text(json.dumps({"enabled": enabled, "daily_limit": daily_limit}))
    os.environ["BRAIN_GUEST_CFG"] = str(p)
    gw._GUEST_CFG_CACHE = None
    return p


# ---------------------------------------------------------------------------
# _guest_cfg
# ---------------------------------------------------------------------------

def test_guest_cfg_default_fail_closed(tmp_path):
    """Absent config → fail-closed OFF with the default cap."""
    os.environ["BRAIN_GUEST_CFG"] = str(tmp_path / "nope.json")
    gw._GUEST_CFG_CACHE = None
    c = gw._guest_cfg()
    assert c == {"enabled": False, "daily_limit": 30}


def test_guest_cfg_env_override_and_read(tmp_path):
    _write_cfg(tmp_path, True, 42)
    c = gw._guest_cfg()
    assert c["enabled"] is True and c["daily_limit"] == 42


def test_guest_cfg_clamps_bounds(tmp_path):
    _write_cfg(tmp_path, True, 9999)
    assert gw._guest_cfg()["daily_limit"] == 500
    _write_cfg(tmp_path, True, 0)
    assert gw._guest_cfg()["daily_limit"] == 1
    _write_cfg(tmp_path, True, -5)
    assert gw._guest_cfg()["daily_limit"] == 1


def test_guest_cfg_bad_json_fails_closed(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json")
    os.environ["BRAIN_GUEST_CFG"] = str(p)
    gw._GUEST_CFG_CACHE = None
    assert gw._guest_cfg() == {"enabled": False, "daily_limit": 30}


def test_guest_cfg_ttl_cache_honors_updates(tmp_path):
    """A change to the file is picked up after the TTL, not before (cache works + expires)."""
    p = _write_cfg(tmp_path, True, 10)
    orig_ttl = gw._GUEST_CFG_TTL
    try:
        gw._GUEST_CFG_TTL = 0.3
        gw._GUEST_CFG_CACHE = None
        assert gw._guest_cfg()["daily_limit"] == 10
        p.write_text(json.dumps({"enabled": True, "daily_limit": 40}))
        # within TTL: still cached at 10
        assert gw._guest_cfg()["daily_limit"] == 10
        time.sleep(0.4)
        # after TTL: re-read → 40
        assert gw._guest_cfg()["daily_limit"] == 40
    finally:
        gw._GUEST_CFG_TTL = orig_ttl


# ---------------------------------------------------------------------------
# "day" period key
# ---------------------------------------------------------------------------

def test_day_period_key():
    dk = gw._period_key("day", "active", None)
    assert dk == datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # distinct from week + month
    assert dk != gw._period_key("week", "active", None)
    assert dk != gw._period_key("month", "active", None)


# ---------------------------------------------------------------------------
# Guest dual cookie+IP ledger
# ---------------------------------------------------------------------------

def test_guest_quota_disabled_still_uses_default_cap(tmp_path):
    """The guest quota function caps by daily_limit regardless of enabled (the enable gate is
    at the app layer). With the default (30), the first turns pass."""
    root = _make_temp_root()
    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        os.environ["BRAIN_GUEST_CFG"] = str(tmp_path / "absent.json")
        gw._GUEST_CFG_CACHE = None
        allowed, q = gw._check_and_increment_guest_quota("aid1", "ip1", "fast", root)
    assert allowed is True
    assert q["limit"] == 30 and q["period"] == "day"


def test_guest_quota_exhaustion_and_remaining(tmp_path):
    """Cap of 3 → three pass (remaining 2,1,0), fourth blocked."""
    root = _make_temp_root()
    _write_cfg(tmp_path, True, 3)
    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        res = [gw._check_and_increment_guest_quota("aidA", "ip1", "fast", root) for _ in range(4)]
    allowed = [r[0] for r in res]
    remaining = [r[1]["remaining"] for r in res]
    assert allowed == [True, True, True, False]
    assert remaining == [2, 1, 0, 0]


def test_guest_cookie_cleared_but_ip_still_caps(tmp_path):
    """The anti-farm: after the cap is hit on (aidA, ip1), a NEW cookie on the SAME ip1 is
    still blocked (the per-IP ledger holds the count)."""
    root = _make_temp_root()
    _write_cfg(tmp_path, True, 2)
    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        assert gw._check_and_increment_guest_quota("aidA", "ip1", "fast", root)[0] is True
        assert gw._check_and_increment_guest_quota("aidA", "ip1", "fast", root)[0] is True
        # cookie cleared → aidB, same ip1 → blocked by the IP ledger
        blocked, q = gw._check_and_increment_guest_quota("aidB", "ip1", "fast", root)
        assert blocked is False and q["remaining"] == 0
        # fresh cookie AND fresh IP → allowed
        assert gw._check_and_increment_guest_quota("aidC", "ip2", "fast", root)[0] is True


def test_guest_ip_reused_blocks_after_cookie_hits(tmp_path):
    """Symmetric: exhaust via the cookie ledger, then a shared IP with that cookie is blocked."""
    root = _make_temp_root()
    _write_cfg(tmp_path, True, 1)
    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        # aidX on ip_a hits the cap (1)
        assert gw._check_and_increment_guest_quota("aidX", "ip_a", "fast", root)[0] is True
        # aidX now blocked on a DIFFERENT ip because the cookie ledger is full
        blocked, _ = gw._check_and_increment_guest_quota("aidX", "ip_b", "fast", root)
        assert blocked is False


def test_guest_no_identity_denied_not_uncapped(tmp_path):
    """No cookie AND no routable IP → cannot be metered → DENIED (never served uncapped)."""
    root = _make_temp_root()
    _write_cfg(tmp_path, True, 30)
    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        allowed, q = gw._check_and_increment_guest_quota("", "", "fast", root)
    assert allowed is False and q["remaining"] == 0


def test_guest_pro_lane_locked(tmp_path):
    """Guests never get the pro lane (limit 0)."""
    root = _make_temp_root()
    _write_cfg(tmp_path, True, 30)
    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        allowed, q = gw._check_and_increment_guest_quota("aid1", "ip1", "pro", root)
    assert allowed is False and q["limit"] == 0


def test_guest_day_key_rollover(tmp_path):
    """A fresh UTC day resets the guest cap (keys are day-scoped)."""
    root = _make_temp_root()
    _write_cfg(tmp_path, True, 1)
    real_period_key = gw._period_key

    def fake_key(period, status, cpe, _day=["2026-07-22"]):
        if period == "day":
            return _day[0]
        return real_period_key(period, status, cpe)

    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        with patch.object(gw, "_period_key", side_effect=fake_key):
            assert gw._check_and_increment_guest_quota("aid1", "ip1", "fast", root)[0] is True
            assert gw._check_and_increment_guest_quota("aid1", "ip1", "fast", root)[0] is False  # day 1 exhausted
            # advance the day
            fake_key.__defaults__[0][0] = "2026-07-23"
            assert gw._check_and_increment_guest_quota("aid1", "ip1", "fast", root)[0] is True  # day 2 fresh


def test_guest_quota_status_readonly(tmp_path):
    """_guest_quota_status reports remaining WITHOUT incrementing."""
    root = _make_temp_root()
    _write_cfg(tmp_path, True, 5)
    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        gw._check_and_increment_guest_quota("aid1", "ip1", "fast", root)  # spend 1
        s1 = gw._guest_quota_status("aid1", "ip1", root)
        s2 = gw._guest_quota_status("aid1", "ip1", root)
    assert s1 == {"remaining": 4, "limit": 5, "period": "day"}
    assert s2["remaining"] == 4  # read did not decrement


# ---------------------------------------------------------------------------
# Free-tier fast flip
# ---------------------------------------------------------------------------

def test_free_fast_flips_to_daily_when_enabled(tmp_path):
    root = _make_temp_root()
    _write_cfg(tmp_path, True, 30)
    a = gw._get_allowance("free", "active", "fast", root)
    assert a == {"limit": 30, "period": "day"}


def test_free_fast_legacy_when_disabled(tmp_path):
    root = _make_temp_root()
    _write_cfg(tmp_path, False, 30)
    a = gw._get_allowance("free", "active", "fast", root)
    # legacy config value (brain.yml or hardcoded fallback) — week period, NOT day
    assert a["period"] == "week"


def test_flip_does_not_touch_pro_or_paid(tmp_path):
    root = _make_temp_root()
    _write_cfg(tmp_path, True, 30)
    # free pro untouched (still 0)
    assert gw._get_allowance("free", "active", "pro", root)["limit"] == 0
    # a paid tier's fast is untouched (day-flip is free-only)
    pro_fast = gw._get_allowance("pro", "active", "fast", root)
    assert pro_fast["period"] != "day"
    # trial untouched
    trial_fast = gw._get_allowance("insider", "trialing", "fast", root)
    assert trial_fast["period"] != "day"


# ---------------------------------------------------------------------------
# get_guest_quotas / me shape
# ---------------------------------------------------------------------------

def test_get_guest_quotas_shape(tmp_path):
    root = _make_temp_root()
    _write_cfg(tmp_path, True, 25)
    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        out = gw.get_guest_quotas("aid1", "ip1", root)
    assert out["tier"] == "guest"
    assert out["quotas"]["fast"] == {"remaining": 25, "limit": 25, "period": "day"}
    assert out["quotas"]["pro"] == {"remaining": 0, "limit": 0, "period": "day"}


# ---------------------------------------------------------------------------
# Guest chat() end-to-end restrictions
# ---------------------------------------------------------------------------

def test_guest_chat_fast_no_thread_writes(tmp_path):
    """A guest fast turn succeeds and NEVER calls the thread store (stateless)."""
    root = _make_temp_root()
    _write_cfg(tmp_path, True, 30)
    resp = _MockResponse([_MockBlock("text", "Reading. is_context_only: true — display-tier pending FDR.")], "end_turn")
    providers = [{"client": _MockClient([resp]), "model": "deepseek-chat"}]
    ensure = MagicMock(return_value=None)
    append = MagicMock()
    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        with patch.object(gw, "_build_lane_providers", return_value=providers):
            with patch.object(gw, "_ensure_thread", ensure):
                with patch.object(gw, "_append_message", append):
                    with patch("lib.ai_costs.record_usage", return_value=True):
                        result = gw.chat("what's the regime", "guest:aid1", lane="fast", root=root,
                                         is_guest=True, guest_aid="h_aid1", guest_ip="h_ip1")
    assert result.get("ok") is True
    assert result.get("thread_id") is None
    ensure.assert_not_called()       # no thread row created for a guest
    append.assert_not_called()       # no message persisted for a guest


def test_guest_chat_research_rejected(tmp_path):
    """Research mode for a guest → not pro-eligible → quota_exhausted (no model call)."""
    root = _make_temp_root()
    _write_cfg(tmp_path, True, 30)
    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        with patch.object(gw, "_build_lane_providers", return_value=[{"client": _MockClient([]), "model": "x"}]):
            result = gw.chat("deep dive", "guest:aid1", mode="research", root=root,
                             is_guest=True, guest_aid="h1", guest_ip="i1")
    assert result.get("quota_exhausted") is True
    assert result.get("lane") == "pro"


def test_guest_chat_fast_exhausted_402_shape(tmp_path):
    """When the guest daily cap is spent, chat returns the quota_exhausted shape."""
    root = _make_temp_root()
    _write_cfg(tmp_path, True, 1)
    resp = _MockResponse([_MockBlock("text", "ok. is_context_only: true — display-tier pending FDR.")], "end_turn")
    providers = [{"client": _MockClient([resp, resp]), "model": "deepseek-chat"}]
    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        with patch.object(gw, "_build_lane_providers", return_value=providers):
            with patch.object(gw, "_ensure_thread", return_value=None):
                with patch("lib.ai_costs.record_usage", return_value=True):
                    first = gw.chat("q1", "guest:aid1", lane="fast", root=root,
                                    is_guest=True, guest_aid="h1", guest_ip="i1")
                    second = gw.chat("q2", "guest:aid1", lane="fast", root=root,
                                     is_guest=True, guest_aid="h1", guest_ip="i1")
    assert first.get("ok") is True
    assert second.get("quota_exhausted") is True


def test_guest_images_stripped(tmp_path):
    """A guest attaching an image is not pro-eligible → the image is dropped (text-only answer)."""
    root = _make_temp_root()
    _write_cfg(tmp_path, True, 30)
    resp = _MockResponse([_MockBlock("text", "Text only. is_context_only: true — display-tier pending FDR.")], "end_turn")
    providers = [{"client": _MockClient([resp]), "model": "deepseek-chat"}]
    vis = MagicMock(return_value=[])   # if vision providers were requested, this proves the gate ran
    with patch.object(gw, "_brain_quota_dir", return_value=tmp_path):
        with patch.object(gw, "_build_lane_providers", return_value=providers):
            with patch.object(gw, "_ensure_thread", return_value=None):
                with patch.object(gw, "_vision_providers", vis):
                    with patch("lib.ai_costs.record_usage", return_value=True):
                        result = gw.chat("describe", "guest:aid1", lane="fast", root=root,
                                         images=["data:image/png;base64,iVBORw0KGgoAAAANS"],
                                         is_guest=True, guest_aid="h1", guest_ip="i1")
    assert result.get("ok") is True
    # image was stripped BEFORE vision-provider resolution → _vision_providers never called
    vis.assert_not_called()


# ---------------------------------------------------------------------------
# CXI-R23: guests never get internals tools
# ---------------------------------------------------------------------------

def test_guest_tool_schemas_have_no_internals():
    """A guest session (internals_allowed=False — email always '') exposes no context_* tools."""
    root = _make_temp_root()
    schemas = gw._all_brain_tool_schemas(root, page="", internals_allowed=False)
    names = {s.get("name") for s in schemas}
    assert "context_search" not in names
    assert "context_open" not in names
    # sanity: the positive control — internals_allowed=True DOES add them (proves the check has power)
    with_int = {s.get("name") for s in gw._all_brain_tool_schemas(root, page="", internals_allowed=True)}
    assert "context_search" in with_int and "context_open" in with_int


def test_guest_email_never_matches_internals_allowlist():
    """Even if an operator email is on the internals allowlist, a guest (email '') never matches."""
    with patch.dict(os.environ, {"BRAIN_INTERNALS_ALLOWLIST": "op@example.com"}):
        assert gw._internals_allowed("") is False
        assert gw._unlimited_allowed("") is False


# ---------------------------------------------------------------------------
# Admin store (admin/brain_guest.py)
# ---------------------------------------------------------------------------

def test_admin_store_write_read_roundtrip(tmp_path):
    from admin import brain_guest as bg
    os.environ["BRAIN_GUEST_CFG"] = str(tmp_path / "bg.json")
    assert bg.read()["enabled"] is False          # absent → default
    w = bg.write(True, 45)
    assert w["ok"] is True and w["enabled"] is True and w["daily_limit"] == 45
    r = bg.read()
    assert r["enabled"] is True and r["daily_limit"] == 45 and r["exists"] is True


def test_admin_store_rejects_bad_values(tmp_path):
    from admin import brain_guest as bg
    os.environ["BRAIN_GUEST_CFG"] = str(tmp_path / "bg.json")
    assert bg.write(True, True)["ok"] is False        # bool is not a valid int
    assert bg.write(True, 9999)["ok"] is False         # out of range
    assert bg.write(True, 0)["ok"] is False
    assert bg.write("yes", 30)["ok"] is False          # non-bool enabled


def test_admin_store_writes_clean_schema_bytes(tmp_path):
    from admin import brain_guest as bg
    p = tmp_path / "bg.json"
    os.environ["BRAIN_GUEST_CFG"] = str(p)
    bg.write(True, 30)
    parsed = json.loads(p.read_text())
    assert parsed == {"enabled": True, "daily_limit": 30}   # exactly the two keys, nothing else


def test_admin_store_and_gateway_agree_on_path(tmp_path):
    """The admin writer and the gateway reader resolve the SAME env-overridden path."""
    from admin import brain_guest as bg
    p = tmp_path / "shared.json"
    os.environ["BRAIN_GUEST_CFG"] = str(p)
    gw._GUEST_CFG_CACHE = None
    bg.write(True, 17)
    gw._GUEST_CFG_CACHE = None
    assert gw._guest_cfg()["enabled"] is True
    assert gw._guest_cfg()["daily_limit"] == 17


# ---------------------------------------------------------------------------
# App layer: the _brain_user_or_guest dependency (the auth boundary)
# ---------------------------------------------------------------------------

class _FakeReq:
    """Minimal Request stand-in for identity derivation (cookies + headers)."""
    def __init__(self, aid="cookieaid", ip="203.0.113.7"):
        self.cookies = {"mm_aid": aid} if aid else {}
        self._ip = ip
        self.headers = {}

    # _mm_client_ip reads request.headers.get(...); with no CDN headers it returns 'unknown'
    # unless we inject one. We inject a real-client-IP header so the IP ledger has a value.
    def _install_ip(self):
        if self._ip:
            self.headers = {"eo-client-ip": self._ip}
        return self


def test_dep_disabled_no_token_401(tmp_path):
    """Guest access OFF + no bearer → 401 (today's behaviour exactly)."""
    from app import main
    from fastapi import HTTPException
    _write_cfg(tmp_path, False, 30)
    with pytest.raises(HTTPException) as ei:
        main._brain_user_or_guest(_FakeReq()._install_ip(), authorization=None)
    assert ei.value.status_code == 401


def test_dep_enabled_no_token_returns_guest(tmp_path):
    """Guest access ON + no bearer → synthetic guest identity, email '' , split hashes set."""
    from app import main
    _write_cfg(tmp_path, True, 30)
    u = main._brain_user_or_guest(_FakeReq(aid="abc")._install_ip(), authorization=None)
    assert u["_is_guest"] is True
    assert u["email"] == ""                    # guests never carry an email
    assert u["id"].startswith("guest:")        # never a Supabase id
    assert u["_guest_aid"] and u["_guest_ip"]  # both ledger keys present (cookie + IP)


def test_dep_verified_user_always_wins(tmp_path):
    """A valid bearer → the verified user, NOT a guest, even when guest access is ON."""
    from app import main
    _write_cfg(tmp_path, True, 30)
    with patch.object(main, "require_user", return_value={"id": "uuid-1", "email": "u@x.com"}):
        u = main._brain_user_or_guest(_FakeReq()._install_ip(), authorization="Bearer good")
    assert u["_is_guest"] is False
    assert u["id"] == "uuid-1" and u["email"] == "u@x.com"


def test_dep_upstream_502_not_degraded(tmp_path):
    """A 502 from require_user (auth upstream down) must surface — NOT silently become guest."""
    from app import main
    from fastapi import HTTPException
    _write_cfg(tmp_path, True, 30)
    with patch.object(main, "require_user", side_effect=HTTPException(502, "auth down")):
        with pytest.raises(HTTPException) as ei:
            main._brain_user_or_guest(_FakeReq()._install_ip(), authorization="Bearer x")
    assert ei.value.status_code == 502


def test_me_route_guest_shape_when_enabled(tmp_path):
    """GET /api/brain/me with no token + guest ON → tier 'guest' shape (200)."""
    from fastapi.testclient import TestClient
    from app.main import app
    _write_cfg(tmp_path, True, 30)
    # gateway reads its cfg from REPO/admin/... by default; point REPO's reader at our file via env
    client = TestClient(app)
    resp = client.get("/api/brain/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tier"] == "guest"
    assert body["quotas"]["pro"]["limit"] == 0
    assert body["quotas"]["fast"]["period"] == "day"


def test_me_route_401_when_disabled(tmp_path):
    """GET /api/brain/me with no token + guest OFF → 401 (unchanged)."""
    from fastapi.testclient import TestClient
    from app.main import app
    _write_cfg(tmp_path, False, 30)
    client = TestClient(app)
    resp = client.get("/api/brain/me")
    assert resp.status_code == 401
