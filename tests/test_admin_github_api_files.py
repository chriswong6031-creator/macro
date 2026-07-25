"""Tests for admin.github_api.get_file / put_file — the deployed-mode Contents
API path that lets the VPS admin persist file edits (e.g. the desk on/off
override) without an authenticated git working tree.
"""
from __future__ import annotations

import base64
import json

import pytest

from admin import github_api


class _Resp:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


@pytest.fixture
def _wired(monkeypatch):
    """Give github_api a token + repo so the API branch runs."""
    monkeypatch.setattr(github_api, "token", lambda: "tkn")
    monkeypatch.setattr(github_api, "repo", lambda: ("owner", "macro"))
    # ensure the `requests is None` guard passes
    if github_api.requests is None:  # pragma: no cover
        pytest.skip("requests unavailable")


def test_get_file_decodes_content_and_sha(_wired, monkeypatch):
    b64 = base64.b64encode(b'{"flagship": {"enabled": true}}').decode()
    captured = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        return _Resp(200, {"content": b64, "sha": "abc"})

    monkeypatch.setattr(github_api.requests, "get", fake_get)
    r = github_api.get_file("data/marketing/account_overrides.json")
    assert r["ok"] is True
    assert json.loads(r["content"])["flagship"]["enabled"] is True
    assert r["sha"] == "abc"
    assert captured["params"] == {"ref": "main"}
    assert "contents/data/marketing/account_overrides.json" in captured["url"]


def test_get_file_404_is_ok_with_none(_wired, monkeypatch):
    monkeypatch.setattr(github_api.requests, "get",
                        lambda *a, **k: _Resp(404))
    r = github_api.get_file("nope.json")
    assert r == {"ok": True, "content": None, "sha": None}


def test_get_file_no_token_errors(monkeypatch):
    monkeypatch.setattr(github_api, "token", lambda: None)
    r = github_api.get_file("x.json")
    assert r["ok"] is False


def test_put_file_creates_and_returns_commit_sha(_wired, monkeypatch):
    captured = {}

    def fake_put(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["body"] = json
        return _Resp(201, {"commit": {"sha": "c0ffee"}})

    monkeypatch.setattr(github_api.requests, "put", fake_put)
    r = github_api.put_file("x.json", '{"a": 1}\n', "admin: test", sha=None)
    assert r["ok"] is True and r["commit_sha"] == "c0ffee"
    # content is base64-encoded, branch defaults to main, no sha on create
    assert base64.b64decode(captured["body"]["content"]).decode() == '{"a": 1}\n'
    assert captured["body"]["branch"] == "main"
    assert "sha" not in captured["body"]


def test_put_file_passes_sha_on_update(_wired, monkeypatch):
    captured = {}

    def fake_put(url, headers=None, json=None, timeout=None):
        captured["body"] = json
        return _Resp(200, {"commit": {"sha": "deadbeef"}})

    monkeypatch.setattr(github_api.requests, "put", fake_put)
    r = github_api.put_file("x.json", "{}", "m", sha="prev-sha")
    assert r["ok"] is True
    assert captured["body"]["sha"] == "prev-sha"


def test_put_file_403_is_friendly_error(_wired, monkeypatch):
    monkeypatch.setattr(github_api.requests, "put",
                        lambda *a, **k: _Resp(403, text="Forbidden"))
    r = github_api.put_file("x.json", "{}", "m")
    assert r["ok"] is False
    assert "403" in r["error"] and "Contents" in r["error"]


def test_put_file_no_token_errors(monkeypatch):
    monkeypatch.setattr(github_api, "token", lambda: None)
    r = github_api.put_file("x.json", "{}", "m")
    assert r["ok"] is False
    assert "token" in r["error"].lower()
