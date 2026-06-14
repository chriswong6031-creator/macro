"""engine.translate — gating, tolerant JSON parsing, and degrade-never-raise batching.

No network: a fake Anthropic-shaped client feeds canned responses so we can prove the
count-mismatch / non-CJK / refusal paths all fall back to None (caller keeps English).
"""
from types import SimpleNamespace

import engine.translate as tr


def _resp(text, stop_reason=None):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)],
                           stop_reason=stop_reason)


class _FakeClient:
    def __init__(self, text, stop_reason=None):
        self._text, self._stop = text, stop_reason
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        return _resp(self._text, self._stop)


# ---- gating ----------------------------------------------------------------

def test_is_enabled_false_when_disabled():
    assert tr.is_enabled({"enabled": False}) is False


def test_is_enabled_false_when_no_key(monkeypatch):
    monkeypatch.delenv("NOPE_KEY", raising=False)
    assert tr.is_enabled({"enabled": True, "api_key_env": "NOPE_KEY"}) is False


def test_translate_noop_when_disabled():
    assert tr.translate_to_zh(["Apple Inc. is a tech company."],
                              {"enabled": False}) == [None]


def test_translate_empty_input():
    assert tr.translate_to_zh([], {"enabled": True}) == []


# ---- tolerant JSON array extraction ----------------------------------------

def test_extract_plain_array():
    assert tr._extract_json_array('["甲", "乙"]') == ["甲", "乙"]


def test_extract_fenced_array():
    assert tr._extract_json_array('```json\n["甲", "乙"]\n```') == ["甲", "乙"]


def test_extract_array_with_prose_around():
    assert tr._extract_json_array('Sure! ["甲"] done') == ["甲"]


def test_extract_rejects_non_array():
    assert tr._extract_json_array('{"a": 1}') is None
    assert tr._extract_json_array('not json at all') is None


# ---- batch validation (fake client, no network) ----------------------------

def _cfg(**over):
    base = {"enabled": True, "model": "x", "batch_size": 10, "max_tokens": 100}
    base.update(over)
    return base


def test_batch_happy_path():
    c = _FakeClient('["苹果公司是一家科技公司。", "微软是一家软件公司。"]')
    out = tr._translate_one_batch(c, ["Apple is tech.", "Microsoft is software."], _cfg())
    assert out == ["苹果公司是一家科技公司。", "微软是一家软件公司。"]


def test_batch_count_mismatch_fails_closed():
    c = _FakeClient('["只有一个"]')  # 1 returned for 2 inputs
    out = tr._translate_one_batch(c, ["a", "b"], _cfg())
    assert out == [None, None]


def test_batch_non_cjk_item_rejected():
    # second item came back English — must be None so the caller keeps the original
    c = _FakeClient('["苹果公司", "Microsoft"]')
    out = tr._translate_one_batch(c, ["Apple", "Microsoft"], _cfg())
    assert out == ["苹果公司", None]


def test_batch_refusal_stop_reason():
    c = _FakeClient('["x"]', stop_reason="refusal")
    assert tr._translate_one_batch(c, ["a"], _cfg()) == [None]


def test_batch_garbage_response():
    c = _FakeClient("I cannot help with that.")
    assert tr._translate_one_batch(c, ["a", "b"], _cfg()) == [None, None]
