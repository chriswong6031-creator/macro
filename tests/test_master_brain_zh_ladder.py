"""The brief's 中文 comes from the SAME worker that wrote the English.

_translate_brief used to build a hardcoded DeepSeek V4-Flash client and call
engine.translate, which has no provider ladder. Two consequences, both real:
the English half survived a DeepSeek balance exhaustion while the 中文 half
silently vanished, and every zh pass was billed to the one metered provider even
on nights Codex or Claude wrote the brief for free. It now routes through
_call_model — the same codex → oauth → anthropic → deepseek waterfall, the same
lane — with the lens usage_stage suffixed "-zh" so the cost ledger can still tell
the English and Chinese passes apart.

All stub-based: no network, no API keys, no sparse-omitted directory.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import master_brain as mb  # noqa: E402

_CFG = {
    "translate_zh": True,
    "api_key_env": "DEEPSEEK_API_KEY",
    "llm_base_url": "https://api.deepseek.com/anthropic",
    "llm_model": "deepseek-v4-pro",
}


def _brief(**over) -> dict:
    b = {
        "summary": "Risk appetite improved.",
        "regime_read": "Late cycle, easing.",
        "rotation_check": None,
        "tldr": ["Stocks up.", "Bonds quiet."],
        "conflicts": [],
        "transmission": [],
        "watch_items": ["Watch the dollar."],
        "degraded_reason": None,
    }
    b.update(over)
    return b


# --------------------------------------------------------------------------- #
# 1. The zh pass goes through the LADDER, not a DeepSeek-only client.
# --------------------------------------------------------------------------- #
def test_zh_uses_call_model_and_tags_the_lens_stage(monkeypatch):
    seen: list[dict] = []

    def fake_call_model(system, user, cfg, served=None):
        seen.append(dict(cfg))
        items = json.loads(user[user.find("["):user.rfind("]") + 1])
        return json.dumps(["中文" + str(i) for i in range(len(items))]), None

    monkeypatch.setattr(mb, "_call_model", fake_call_model)
    brief = _brief()
    mb._translate_brief(brief, dict(_CFG), lens="china")

    assert seen, "the zh pass never called _call_model — it is not on the ladder"
    # Cost attribution stays separable from the English pass.
    assert all(c.get("usage_stage") == "china-zh" for c in seen), seen
    # It inherits the brief's own lane config rather than a private DeepSeek cfg.
    assert all(c.get("llm_model") == "deepseek-v4-pro" for c in seen)
    assert brief["zh"]["summary"] is not None
    assert brief["zh"]["tldr"][0] is not None


def test_zh_does_not_import_the_deepseek_only_translator(monkeypatch):
    """engine.translate has no ladder; reaching for it would reintroduce the bug."""
    import engine.translate as _tr

    def boom(*a, **kw):  # pragma: no cover - only runs on regression
        raise AssertionError("_translate_brief called engine.translate.translate_to_zh")

    monkeypatch.setattr(_tr, "translate_to_zh", boom)
    monkeypatch.setattr(
        mb, "_call_model",
        lambda s, u, c, served=None: (json.dumps(["中"] * len(json.loads(
            u[u.find("["):u.rfind("]") + 1]))), None))
    mb._translate_brief(_brief(), dict(_CFG), lens="macro")


# --------------------------------------------------------------------------- #
# 2. Batch integrity — a short array must NOT shift fields onto wrong keys.
# --------------------------------------------------------------------------- #
def test_batch_fails_closed_on_a_count_mismatch(monkeypatch):
    monkeypatch.setattr(mb, "_call_model",
                        lambda s, u, c, served=None: (json.dumps(["只有一个"]), None))
    out = mb._zh_batch(["a", "b", "c"], dict(_CFG), "macro")
    assert out == [None, None, None], out


def test_batch_rejects_an_english_echo(monkeypatch):
    """A model that echoes the English back has not translated anything."""
    monkeypatch.setattr(
        mb, "_call_model",
        lambda s, u, c, served=None: (json.dumps(["Risk appetite improved."]), None))
    assert mb._zh_batch(["Risk appetite improved."], dict(_CFG), "macro") == [None]


def test_batch_degrades_when_the_whole_ladder_fails(monkeypatch):
    monkeypatch.setattr(mb, "_call_model",
                        lambda s, u, c, served=None: (None, "no_provider"))
    assert mb._zh_batch(["a", "b"], dict(_CFG), "macro") == [None, None]


def test_a_failed_batch_does_not_lose_the_other_batches(monkeypatch):
    """Batching exists so truncation is LOCAL — one bad batch must not blank 中文."""
    calls = {"n": 0}

    def flaky(system, user, cfg, served=None):
        calls["n"] += 1
        items = json.loads(user[user.find("["):user.rfind("]") + 1])
        if calls["n"] == 1:
            return json.dumps(["短"]), None          # wrong count -> batch fails closed
        return json.dumps(["译文"] * len(items)), None

    monkeypatch.setattr(mb, "_call_model", flaky)
    cfg = dict(_CFG, zh_batch_size=2)
    brief = _brief(tldr=["a", "b", "c", "d"], watch_items=["e", "f"])
    mb._translate_brief(brief, cfg, lens="macro")

    assert calls["n"] > 1, "expected several batches"
    zh = brief["zh"]
    survived = [v for v in ([zh["summary"], zh["regime_read"]] + zh["tldr"]
                            + zh["watch_items"]) if v]
    assert survived, "a single bad batch blanked the entire 中文 brief"


# --------------------------------------------------------------------------- #
# 3. Guard rails preserved from the previous implementation.
# --------------------------------------------------------------------------- #
def test_translate_zh_false_is_still_honoured(monkeypatch):
    monkeypatch.setattr(mb, "_call_model", lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError("called the model with translate_zh disabled")))
    brief = _brief()
    mb._translate_brief(brief, dict(_CFG, translate_zh=False), lens="macro")
    assert "zh" not in brief


def test_a_degraded_brief_is_not_translated(monkeypatch):
    monkeypatch.setattr(mb, "_call_model", lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError("translated a brief with no usable content")))
    brief = _brief(regime_read=None, degraded_reason="empty_reply")
    mb._translate_brief(brief, dict(_CFG), lens="macro")
    assert "zh" not in brief


def test_translation_never_raises_into_the_pipeline(monkeypatch):
    def explode(*a, **kw):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(mb, "_call_model", explode)
    brief = _brief()
    mb._translate_brief(brief, dict(_CFG), lens="macro")   # must not raise
    assert brief.get("zh") is None or isinstance(brief.get("zh"), dict)
