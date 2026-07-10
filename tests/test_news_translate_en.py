"""news_translate ZH->EN direction — passthrough, cache, validator, degrade. No network."""
from __future__ import annotations

import json
from types import SimpleNamespace

from engine import news_translate as nt


def _cfg(tmp_path, enabled=True):
    return {"enabled": enabled, "cache_dir": str(tmp_path / "cache"),
            "model": "deepseek-chat", "batch_size": 16}


def _fake_client(reply: str):
    def create(**kwargs):
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=reply)])
    return SimpleNamespace(messages=SimpleNamespace(create=create))


def test_english_passthrough_and_disabled_zh(tmp_path):
    cfg = _cfg(tmp_path, enabled=False)
    out = nt.translate_to_en(["PBOC cuts rates", "央行宣布降准", ""], cfg)
    assert out[0] == "PBOC cuts rates"        # already English -> passthrough
    assert out[1] is None                     # zh, disabled -> caller falls back
    assert out[2] is None


def test_translate_and_cache_roundtrip(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    reply = json.dumps(["PBOC announces 50bp RRR cut, releasing ~1t yuan"])
    monkeypatch.setattr(nt, "_client", lambda c: _fake_client(reply))
    out = nt.translate_to_en(["央行宣布降准0.5个百分点"], cfg)
    assert out == ["PBOC announces 50bp RRR cut, releasing ~1t yuan"]
    # second call: client gone, cache serves
    monkeypatch.setattr(nt, "_client", lambda c: None)
    out2 = nt.translate_to_en(["央行宣布降准0.5个百分点"], cfg)
    assert out2 == out
    # zh-direction cache is keyed separately — no cross-direction bleed
    assert nt.translate_to_zh(["央行宣布降准0.5个百分点"], cfg) == ["央行宣布降准0.5个百分点"]


def test_validator_rejects_cjk_heavy_or_malformed(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    # "translation" that is still Chinese -> rejected -> None (fallback to raw)
    monkeypatch.setattr(nt, "_client", lambda c: _fake_client(json.dumps(["央行宣布降准"])))
    assert nt.translate_to_en(["央行宣布降准0.5个百分点"], cfg) == [None]
    # malformed reply (wrong arity) -> None
    monkeypatch.setattr(nt, "_client", lambda c: _fake_client(json.dumps(["a", "b"])))
    assert nt.translate_to_en(["证监会立案调查"], cfg) == [None]
    # proper-noun CJK residue within a mostly-English string is accepted
    monkeypatch.setattr(
        nt, "_client",
        lambda c: _fake_client(json.dumps(["CSRC probes Zhongtai Auto (众泰) over disclosure violations"])))
    assert nt.translate_to_en(["众泰汽车遭证监会立案"], cfg)[0].startswith("CSRC probes")


def test_client_error_degrades(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)

    def create(**kwargs):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(nt, "_client",
                        lambda c: SimpleNamespace(messages=SimpleNamespace(create=create)))
    assert nt.translate_to_en(["央行宣布降准"], cfg) == [None]


def test_attach_translations_sets_title_en(monkeypatch):
    from engine import china_news as cn
    heads = [{"title": "央行宣布降准0.5个百分点", "summary": "", "source_lang": "zh"},
             {"title": "China GDP beats expectations", "summary": "", "source_lang": "en"}]
    monkeypatch.setattr(nt, "translate_to_en",
                        lambda texts, cfg=None: ["PBOC announces 50bp RRR cut"
                                                 if nt._has_cjk(t) else t for t in texts])
    monkeypatch.setattr(nt, "translate_to_zh",
                        lambda texts, cfg=None: [t if nt._has_cjk(t) else "中国GDP超预期"
                                                 for t in texts])
    out = cn._attach_translations(heads)
    assert out[0]["title_en"] == "PBOC announces 50bp RRR cut"
    assert out[0]["title_zh"] == "央行宣布降准0.5个百分点"
    assert out[1]["title_zh"] == "中国GDP超预期"
    assert "title_en" not in out[1]           # passthrough == original -> not duplicated
