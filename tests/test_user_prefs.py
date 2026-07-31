"""tests/test_user_prefs.py — lib/user_prefs.py (Analyst OS W3).

Fully offline: the ONLY seam is ``urllib.request.urlopen`` (the GoTrue admin API).

What this suite pins:
  1. The enum table is CLOSED — an illegal value is dropped on read and refuses the write,
     and an unknown KEY can never reach ``user_metadata`` through this door.
  2. The merge happens on OUR side and keeps unrelated stored keys. This is the whole reason
     the module exists: a partial ``user_metadata`` PUT has REPLACED the object on some
     GoTrue versions, so a blind write silently deletes whatever else is stored there.
  3. A caller holding the record pays ONE call (PUT); a caller holding only a user id pays a
     GET first — and a FAILED read REFUSES the write instead of PUTting a partial object.
  4. Fail-soft everywhere: no configuration, a dead API, or a junk value → False, never a
     raise. A display preference is not worth a 500.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import user_prefs  # noqa: E402

SB = ("https://proj.supabase.test", "service-role-test-key")
UID = "9c1f-user"

#: What the account already stores for this user besides the prefs. If a write ever drops
#: `display_name`, a real user loses their name to a theme toggle.
STORED = {"display_name": "Ada", "lang": "en", "onboarded": True}


class _Resp:
    def __init__(self, body: bytes = b"{}"):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


class _Api:
    """Records every admin-API call; answers GETs with ``STORED`` by default."""

    def __init__(self, *, metadata: dict | None = None, fail_get=False, fail_put=False,
                 get_body: bytes | None = None):
        self.calls: list[tuple[str, str, dict | None]] = []
        self.headers: list[dict] = []
        self.metadata = STORED if metadata is None else metadata
        self.fail_get = fail_get
        self.fail_put = fail_put
        self.get_body = get_body

    def urlopen(self, req, timeout=None):
        method = req.get_method()
        payload = json.loads(req.data.decode()) if req.data else None
        self.calls.append((method, req.full_url, payload))
        self.headers.append(dict(req.headers))
        if method == "GET":
            if self.fail_get:
                raise OSError("supabase unreachable")
            if self.get_body is not None:
                return _Resp(self.get_body)
            return _Resp(json.dumps({"id": UID, "user_metadata": self.metadata}).encode())
        if self.fail_put:
            raise OSError("supabase unreachable")
        return _Resp()

    @property
    def methods(self) -> list[str]:
        return [c[0] for c in self.calls]

    def payload_of(self, method: str) -> dict:
        return next(c[2] for c in self.calls if c[0] == method)


@pytest.fixture
def api(monkeypatch) -> _Api:
    a = _Api()
    monkeypatch.setattr(urllib.request, "urlopen", a.urlopen)
    return a


def _install(monkeypatch, a: _Api) -> _Api:
    monkeypatch.setattr(urllib.request, "urlopen", a.urlopen)
    return a


# --------------------------------------------------------------------------- #
# 1. the enum table is closed
# --------------------------------------------------------------------------- #
def test_the_three_keys_and_their_value_sets():
    assert set(user_prefs.PREF_VALUES) == {"lang", "theme", "brain_depth"}
    assert user_prefs.PREF_VALUES["lang"] == ("en", "zh")
    assert user_prefs.PREF_VALUES["theme"] == ("light", "dark")
    assert user_prefs.PREF_VALUES["brain_depth"] == ("concise", "standard", "deep")


@pytest.mark.parametrize("key, raw, expect", [
    ("lang", "zh", "zh"),
    ("lang", "ZH", "zh"),          # normalised, not rejected
    ("lang", " en ", "en"),
    ("theme", "Dark", "dark"),
    ("brain_depth", "CONCISE", "concise"),
    ("brain_depth", "standard", "standard"),
    ("brain_depth", "deep", "deep"),
    ("lang", "en-US", None),       # a locale is not one of the two values
    ("lang", "klingon", None),
    ("theme", "sepia", None),
    ("brain_depth", "turbo", None),
    ("brain_depth", "", None),
    ("brain_depth", 5, None),      # a non-string is never a value
    ("brain_depth", None, None),
    ("tier", "pro", None),         # unknown KEY: no fourth preference through this door
])
def test_normalize_pref(key, raw, expect):
    assert user_prefs.normalize_pref(key, raw) == expect


def test_validate_prefs_names_the_rejected_keys_and_skips_absent_ones():
    clean, rejected = user_prefs.validate_prefs(
        {"lang": "ZH", "theme": "sepia", "brain_depth": None, "tier": "pro"})
    assert clean == {"lang": "zh"}
    # `brain_depth: None` is "don't change this", not junk — absent from BOTH lists.
    assert sorted(rejected) == ["theme", "tier"]


def test_validate_prefs_never_raises_on_junk():
    assert user_prefs.validate_prefs(None) == ({}, [])
    assert user_prefs.validate_prefs({}) == ({}, [])


# --------------------------------------------------------------------------- #
# 2. read: zero network, illegal values dropped
# --------------------------------------------------------------------------- #
def test_read_user_prefs_returns_only_legal_values():
    user = {"id": UID, "user_metadata": {
        "display_name": "Ada", "lang": "zh-CN", "theme": "dark",
        "brain_depth": "concise", "tier": "pro"}}
    # 'zh-CN' is not one of the two stored values — dropped, not guessed into 'zh'. Only a
    # value this module itself would WRITE reads back.
    assert user_prefs.read_user_prefs(user) == {"theme": "dark", "brain_depth": "concise"}


def test_read_user_prefs_on_a_guest_and_on_junk():
    assert user_prefs.read_user_prefs({"id": "guest:abc", "email": ""}) == {}
    assert user_prefs.read_user_prefs({"user_metadata": None}) == {}
    assert user_prefs.read_user_prefs({"user_metadata": "nope"}) == {}
    assert user_prefs.read_user_prefs(None) == {}
    assert user_prefs.read_user_prefs("not a dict") == {}


def test_read_user_prefs_makes_no_network_call(monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("read_user_prefs must never hit the network")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    assert user_prefs.read_user_prefs({"user_metadata": {"lang": "zh"}}) == {"lang": "zh"}


# --------------------------------------------------------------------------- #
# 3. write with a base: one PUT, merged on our side
# --------------------------------------------------------------------------- #
def test_write_with_base_is_one_put_and_keeps_unrelated_keys(api):
    ok = user_prefs.write_user_prefs(UID, {"theme": "dark"}, base=dict(STORED), supabase=SB)
    assert ok is True
    assert api.methods == ["PUT"], "a caller holding the record must not pay a read"
    method, url, payload = api.calls[0]
    assert url == f"https://proj.supabase.test/auth/v1/admin/users/{UID}"
    assert payload["user_metadata"] == {
        "display_name": "Ada", "lang": "en", "onboarded": True, "theme": "dark"}


def test_write_normalises_before_storing(api):
    user_prefs.write_user_prefs(UID, {"brain_depth": " DEEP "}, base={}, supabase=SB)
    assert api.payload_of("PUT")["user_metadata"] == {"brain_depth": "deep"}


def test_write_url_quotes_the_user_id(api):
    user_prefs.write_user_prefs("a b/../c", {"lang": "zh"}, base={}, supabase=SB)
    assert "a%20b%2F..%2Fc" in api.calls[0][1]


def test_write_sends_the_service_role_key_both_ways(api):
    """GoTrue's admin endpoints want the key as BOTH `apikey` and a Bearer — sending only
    one gets a 401 that looks like a bad user id."""
    user_prefs.write_user_prefs(UID, {"lang": "zh"}, base={}, supabase=SB)
    headers = {k.lower(): v for k, v in api.headers[0].items()}
    assert headers["apikey"] == SB[1]
    assert headers["authorization"] == f"Bearer {SB[1]}"
    assert headers["content-type"] == "application/json"


# --------------------------------------------------------------------------- #
# 4. write without a base: GET first, and a failed read refuses the write
# --------------------------------------------------------------------------- #
def test_write_without_base_reads_current_metadata_then_merges(api):
    ok = user_prefs.write_user_prefs(UID, {"brain_depth": "concise"}, supabase=SB)
    assert ok is True
    assert api.methods == ["GET", "PUT"]
    assert api.payload_of("PUT")["user_metadata"] == {
        "display_name": "Ada", "lang": "en", "onboarded": True, "brain_depth": "concise"}


def test_a_failed_read_refuses_the_write(monkeypatch):
    """The whole point: we cannot merge what we could not read, and a partial PUT can
    REPLACE the object. Refusing loses a preference; writing loses the user's name."""
    a = _install(monkeypatch, _Api(fail_get=True))
    assert user_prefs.write_user_prefs(UID, {"lang": "zh"}, supabase=SB) is False
    assert a.methods == ["GET"], "no PUT may follow a read we could not complete"


def test_fetch_user_metadata_distinguishes_unknown_from_empty(monkeypatch):
    """None means "we could not read it"; {} means "we read it and nothing is stored". The
    write path branches on that difference, so it must not collapse."""
    a = _install(monkeypatch, _Api(fail_get=True))
    assert user_prefs.fetch_user_metadata(UID, supabase=SB) is None   # unknown
    assert a.methods == ["GET"]
    _install(monkeypatch, _Api(get_body=b'{"id":"x"}'))
    assert user_prefs.fetch_user_metadata(UID, supabase=SB) == {}     # known-empty
    _install(monkeypatch, _Api(get_body=b'{"user_metadata":"junk"}'))
    assert user_prefs.fetch_user_metadata(UID, supabase=SB) == {}


def test_write_on_a_user_with_no_stored_metadata_yet(monkeypatch):
    _install(monkeypatch, _Api(metadata={}))
    assert user_prefs.write_user_prefs(UID, {"lang": "zh"}, supabase=SB) is True


# --------------------------------------------------------------------------- #
# 5. fail-soft: junk, no config, dead API
# --------------------------------------------------------------------------- #
def test_a_rejected_value_writes_nothing_at_all(api):
    """Strict on purpose: a caller that wants to report WHICH value was wrong validates
    first. A half-applied patch is the worst of the three outcomes."""
    assert user_prefs.write_user_prefs(UID, {"lang": "zh", "theme": "sepia"},
                                      base={}, supabase=SB) is False
    assert api.calls == []


def test_an_empty_patch_writes_nothing(api):
    assert user_prefs.write_user_prefs(UID, {}, base={}, supabase=SB) is False
    assert user_prefs.write_user_prefs(UID, {"lang": None}, base={}, supabase=SB) is False
    assert api.calls == []


def test_unconfigured_supabase_no_ops(api, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    # No env and no injected pair: a service-role PUT must never be aimed at a guessed
    # project, so the write no-ops rather than defaulting.
    assert user_prefs.write_user_prefs(UID, {"lang": "zh"}, base={}) is False
    assert user_prefs.fetch_user_metadata(UID) is None
    assert api.calls == []
    # ...and a half-configured pair is still unconfigured.
    assert user_prefs.write_user_prefs(UID, {"lang": "zh"}, base={},
                                       supabase=("https://x.test", "")) is False
    assert api.calls == []


def test_missing_user_id_no_ops(api):
    assert user_prefs.write_user_prefs("", {"lang": "zh"}, base={}, supabase=SB) is False
    assert api.calls == []


def test_env_supplies_the_pair_when_no_caller_injects_one(api, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://env.supabase.test/")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "env-key")
    assert user_prefs.write_user_prefs(UID, {"lang": "zh"}, base={}) is True
    # trailing slash stripped — one slash, not two
    assert api.calls[0][1] == f"https://env.supabase.test/auth/v1/admin/users/{UID}"


def test_a_dead_api_is_false_never_a_raise(monkeypatch):
    _install(monkeypatch, _Api(fail_put=True))
    assert user_prefs.write_user_prefs(UID, {"lang": "zh"}, base={}, supabase=SB) is False


def test_an_unserialisable_stored_value_is_false_not_a_raise(api):
    """`base` is somebody else's dict. A value json cannot encode must come back False —
    this is a fire-and-forget preference write, not a place to raise out of."""
    assert user_prefs.write_user_prefs(UID, {"lang": "zh"},
                                       base={"weird": object()}, supabase=SB) is False


def test_a_non_dict_base_refuses_the_write(api):
    """Same refusal as a failed read: an unreadable base means we do not know what is
    stored, and a PUT would replace an object we never saw."""
    for junk in ("nope", 5, [], object()):
        assert user_prefs.write_user_prefs(UID, {"lang": "zh"}, base=junk, supabase=SB) is False
    assert api.calls == []
