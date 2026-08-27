"""master_brain provider ladder — DeepSeek must not be the only rung.

engine/master_brain.py::_call_model used to hand-build a ONE-RUNG provider
list pointed only at DeepSeek. When the operator's DeepSeek balance ran out,
that single rung failed and the AI Daily Brief (site/aibrief.html) did not
render at all — engine/ai_desk.py inherits the same failure via
_mb._call_model. _call_model now builds a multi-rung ladder (codex -> oauth
-> anthropic -> deepseek) via engine.llm_auth.build_providers() whenever the
lane's legacy llm_* config describes DeepSeek's endpoint (_is_deepseek_lane),
after translating the legacy keys into build_providers' vocabulary
(_ladder_cfg). An operator who pinned some OTHER endpoint keeps the historic
single-provider descriptor untouched.

All stub-based — no network, no real API keys, no sparse-omitted directory.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import llm_auth as llm_auth_mod  # noqa: E402
from engine import master_brain as mb  # noqa: E402

# The shipped config.yml shape for master_brain/ai_desk before the ladder keys
# were added: only the legacy llm_* keys are present.
_SHIPPED_CFG = {
    "api_key_env": "DEEPSEEK_API_KEY",
    "llm_base_url": "https://api.deepseek.com/anthropic",
    "llm_model": "deepseek-v4-pro",
}

# A lane that deliberately pins a non-DeepSeek endpoint (e.g. an operator who
# swapped master_brain straight to Claude via the legacy llm_* keys).
_CUSTOM_ENDPOINT_CFG = {
    "api_key_env": "ANTHROPIC_API_KEY",
    "llm_base_url": "https://api.anthropic.com",
    "llm_model": "claude-opus-4-8",
}


class _FakeBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class _FakeResponse:
    def __init__(self, text: str):
        self.stop_reason = None
        self.content = [_FakeBlock(text)]
        self.usage = None


class _FakeMessages:
    def __init__(self, text: str | None = None, exc: BaseException | None = None):
        self._text = text
        self._exc = exc

    def create(self, **kw):
        if self._exc is not None:
            raise self._exc
        return _FakeResponse(self._text)


class _FakeClient:
    def __init__(self, text: str | None = None, exc: BaseException | None = None):
        self.messages = _FakeMessages(text=text, exc=exc)


def _fake_provider(name: str, *, text: str | None = None,
                    exc: BaseException | None = None) -> dict:
    return {
        "name": name,
        "env_var": f"FAKE_{name.upper()}_ENV",
        "cred": "present",
        "client": _FakeClient(text=text, exc=exc),
        "model": f"{name}-fake-model",
        "usage_lane": "test-ladder",
        "usage_stage": "",
    }


# --------------------------------------------------------------------------- #
# 1. _ladder_cfg on the shipped config shape
# --------------------------------------------------------------------------- #
def test_ladder_cfg_translates_shipped_deepseek_key():
    out = mb._ladder_cfg(_SHIPPED_CFG)
    # THE regression this guards: master_brain's api_key_env has always named
    # the DEEPSEEK key. Handed over untranslated, build_providers would read
    # it as the ANTHROPIC key and build a client against api.anthropic.com
    # holding a DeepSeek credential — a rung that 401s on every call.
    assert out["deepseek_key_env"] == "DEEPSEEK_API_KEY"
    assert out["api_key_env"] == "ANTHROPIC_API_KEY"
    assert out["api_key_env"] != "DEEPSEEK_API_KEY"
    assert out["deepseek_base_url"] == "https://api.deepseek.com/anthropic"
    assert out["deepseek_model"] == "deepseek-v4-pro"
    assert out["provider_order"] == ["codex", "oauth", "anthropic", "deepseek"]


# --------------------------------------------------------------------------- #
# 2. _call_model on a DeepSeek-shaped cfg calls build_providers with the
#    operator-mandated rung order.
# --------------------------------------------------------------------------- #
def test_call_model_builds_ladder_via_build_providers(monkeypatch):
    captured: dict = {}

    def _fake_build_providers(cfg, *, opus_model=None, deepseek_model=None, **kw):
        captured["cfg"] = cfg
        captured["opus_model"] = opus_model
        captured["deepseek_model"] = deepseek_model
        return [_fake_provider("codex", text="codex reply"),
                _fake_provider("deepseek", text="deepseek reply")]

    monkeypatch.setattr(llm_auth_mod, "build_providers", _fake_build_providers)

    text, reason = mb._call_model("sys", "user", dict(_SHIPPED_CFG))

    assert captured["cfg"]["provider_order"] == ["codex", "oauth", "anthropic", "deepseek"]
    assert text == "codex reply"
    assert reason is None


# --------------------------------------------------------------------------- #
# 3. Fallthrough — a non-auth failure on rung 1 (codex) must not blank the
#    brief; rung 2 (deepseek) still serves. This is the exact failure that
#    killed the AI Daily Brief when the DeepSeek account ran out of balance
#    (mirrored here on the FIRST rung to prove the waterfall, not the config).
# --------------------------------------------------------------------------- #
def test_call_model_falls_through_a_failed_rung(monkeypatch):
    providers = [
        _fake_provider("codex", exc=RuntimeError("402 Insufficient Balance")),
        _fake_provider("deepseek", text="deepseek saved the brief"),
    ]
    monkeypatch.setattr(llm_auth_mod, "build_providers", lambda *a, **kw: providers)

    text, reason = mb._call_model("sys", "user", dict(_SHIPPED_CFG))

    assert text == "deepseek saved the brief"
    assert reason is None


# --------------------------------------------------------------------------- #
# 4. Empty ladder (no credentials anywhere) preserves the early-return
#    contract: (None, "no_client_or_key").
# --------------------------------------------------------------------------- #
def test_call_model_empty_ladder_returns_no_client_or_key(monkeypatch):
    monkeypatch.setattr(llm_auth_mod, "build_providers", lambda *a, **kw: [])

    text, reason = mb._call_model("sys", "user", dict(_SHIPPED_CFG))

    assert text is None
    assert reason == "no_client_or_key"


# --------------------------------------------------------------------------- #
# 5. A non-DeepSeek lane (operator pinned a custom endpoint) must NOT call
#    build_providers — it keeps the historic single-descriptor path.
# --------------------------------------------------------------------------- #
def test_call_model_custom_endpoint_bypasses_ladder(monkeypatch):
    called = {"n": 0}

    def _fake_build_providers(*a, **kw):
        called["n"] += 1
        return []

    monkeypatch.setattr(llm_auth_mod, "build_providers", _fake_build_providers)

    client_calls: list = []

    def _sentinel_client(cfg):
        client_calls.append(True)
        return None  # None -> "no_client_or_key" via the legacy path

    # monkeypatch.setattr restores mb._client automatically at test teardown.
    monkeypatch.setattr(mb, "_client", _sentinel_client)
    text, reason = mb._call_model("sys", "user", dict(_CUSTOM_ENDPOINT_CFG))

    assert called["n"] == 0, "build_providers must not be called for a custom endpoint"
    assert client_calls, "_client() must be called on the legacy single-provider path"
    assert text is None
    assert reason == "no_client_or_key"


# A clean reply with no banned-style tokens (no snake_case, no Q1-4 quad codes, no
# sigma/z-score/percentile forms) so the style lint accepts it on the FIRST pass —
# keeps the served-by/model assertions below independent of the rewrite-retry path.
_CLEAN_REPLY = {
    "summary": "Backdrop stays low risk; liquidity contracting.",
    "regime_read": "Low macro risk with FX risk-on.",
    "conflicts": ["FX risk-on vs contracting liquidity"],
    "rotation_check": "Partly tracking.",
    "transmission": ["liquidity drain -> crypto first"],
    "watch_items": ["FOMC meeting ahead"],
    "confidence": "medium",
}
_STATE = {"macro": {"date": "2026-01-05", "quad": "steady"}}


# --------------------------------------------------------------------------- #
# 6. synthesize() records served_by + the SERVING rung's model — not always
#    "deepseek-v4-pro" — so the load balancer is verifiable from the artifact
#    itself (the coordinator's follow-up concern: nobody could tell from the
#    brief whether Codex served or DeepSeek quietly took every call).
# --------------------------------------------------------------------------- #
def test_synthesize_records_served_by_and_serving_model(monkeypatch):
    providers = [_fake_provider("codex", text=json.dumps(_CLEAN_REPLY))]
    monkeypatch.setattr(llm_auth_mod, "build_providers", lambda *a, **kw: providers)

    brief = mb.synthesize(dict(_STATE), dict(_SHIPPED_CFG), lens="macro")

    assert brief["served_by"] == "codex"
    assert brief["model"] == "codex-fake-model"
    assert brief["model"] != "deepseek-v4-pro"


# --------------------------------------------------------------------------- #
# 7. An OLD-signature `_call_model` stub (3 positional args, no `served` kwarg —
#    the shape several existing tests monkeypatch, e.g.
#    tests/test_master_brain_producer.py:45) must still drive synthesize()
#    without raising; brief["model"] falls back to the cfg value.
# --------------------------------------------------------------------------- #
def test_synthesize_tolerates_old_signature_call_model_stub(monkeypatch):
    def _old_stub(system, user, cfg):   # no `served` kwarg — the pre-follow-up shape
        return json.dumps(_CLEAN_REPLY), None

    monkeypatch.setattr(mb, "_call_model", _old_stub)

    cfg = dict(_SHIPPED_CFG)
    brief = mb.synthesize(dict(_STATE), cfg, lens="macro")

    assert brief["degraded_reason"] is None
    assert brief["summary"] == _CLEAN_REPLY["summary"]
    assert brief["model"] == cfg.get("llm_model", "deepseek-v4-pro")
    assert brief["served_by"] is None   # unknown — the stub never populated `served`
