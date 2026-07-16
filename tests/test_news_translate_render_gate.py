"""news_translate render-lane gate — RENDER_NO_DRIP=1 lanes fill only when the
operator opts in via news_translation.render_lanes; cache reads always work. No network."""
from __future__ import annotations

import json
from types import SimpleNamespace

from engine import news_translate as nt


def _cfg(tmp_path, **over):
    cfg = {"enabled": True, "cache_dir": str(tmp_path / "cache"),
           "model": "deepseek-chat", "batch_size": 16}
    cfg.update(over)
    return cfg


def _fake_client(reply: str):
    def create(**kwargs):
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=reply)])
    return SimpleNamespace(messages=SimpleNamespace(create=create))


def _counting_client(calls: dict, reply: str):
    def factory(cfg):
        calls["n"] += 1
        return _fake_client(reply)
    return factory


def test_render_lane_default_off_skips_fill(tmp_path, monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(nt, "_client", _counting_client(calls, json.dumps(["美联储降息"])))
    monkeypatch.setenv("RENDER_NO_DRIP", "1")
    out = nt.translate_to_zh(["Fed cuts rates"], _cfg(tmp_path))
    assert out == [None]          # cache miss degrades to EN fallback, no API attempt
    assert calls["n"] == 0        # client never even constructed


def test_render_lane_opt_in_fills(tmp_path, monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(nt, "_client", _counting_client(calls, json.dumps(["美联储降息"])))
    monkeypatch.setenv("RENDER_NO_DRIP", "1")
    out = nt.translate_to_zh(["Fed cuts rates"], _cfg(tmp_path, render_lanes=True))
    assert out == ["美联储降息"]
    assert calls["n"] == 1


def test_render_lane_still_serves_cache(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    # seed the cache on an allowed lane (sentinel unset)
    monkeypatch.delenv("RENDER_NO_DRIP", raising=False)
    monkeypatch.setattr(nt, "_client", lambda c: _fake_client(json.dumps(["美联储降息"])))
    assert nt.translate_to_zh(["Fed cuts rates"], cfg) == ["美联储降息"]
    # render lane, flag off, client unavailable: committed cache still serves
    monkeypatch.setenv("RENDER_NO_DRIP", "1")
    monkeypatch.setattr(nt, "_client", lambda c: None)
    assert nt.translate_to_zh(["Fed cuts rates"], cfg) == ["美联储降息"]


def test_non_render_lane_unaffected(tmp_path, monkeypatch):
    calls = {"n": 0}
    monkeypatch.delenv("RENDER_NO_DRIP", raising=False)
    monkeypatch.setattr(nt, "_client", _counting_client(calls, json.dumps(["美联储降息"])))
    assert nt.translate_to_zh(["Fed cuts rates"], _cfg(tmp_path)) == ["美联储降息"]
    assert calls["n"] == 1        # nightly/asia lanes fill exactly as before


def test_gate_applies_to_en_direction_too(tmp_path, monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(nt, "_client", _counting_client(calls, json.dumps(["PBOC cuts RRR"])))
    monkeypatch.setenv("RENDER_NO_DRIP", "1")
    assert nt.translate_to_en(["央行宣布降准"], _cfg(tmp_path)) == [None]
    assert calls["n"] == 0
    assert nt.translate_to_en(["央行宣布降准"], _cfg(tmp_path, render_lanes=True)) == ["PBOC cuts RRR"]
    assert calls["n"] == 1


def test_disabled_wins_over_opt_in(tmp_path, monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(nt, "_client", _counting_client(calls, json.dumps(["美联储降息"])))
    monkeypatch.setenv("RENDER_NO_DRIP", "1")
    out = nt.translate_to_zh(["Fed cuts rates"], _cfg(tmp_path, enabled=False, render_lanes=True))
    assert out == [None]
    assert calls["n"] == 0
