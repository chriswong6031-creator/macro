"""news_translate lane gates — WHEN the fill is allowed and WHICH provider runs it.

  render-lane gate  — RENDER_NO_DRIP=1 lanes fill only when the operator opts in
                      via news_translation.render_lanes; cache reads always work.
  provider select   — operator directive 2026-07-31: the lane runs on the attached
                      Codex subscription (Terra) instead of the never-provisioned
                      DEEPSEEK_API_KEY, with the deepseek path kept byte-compatible
                      behind a config flip.

No network and no CLI turn: every test either patches `_client` or installs the
`codex` fixture below.
"""
from __future__ import annotations

import json
import logging
import sys
from types import SimpleNamespace

import pytest

from engine import news_translate as nt
from lib import config as _lib_config

ROOT = _lib_config.ROOT


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


# --------------------------------------------------------------------------- #
# Provider selection — codex (Terra) vs deepseek. Operator directive 2026-07-31.
# --------------------------------------------------------------------------- #
@pytest.fixture
def codex(monkeypatch):
    """A fake attached-Codex account. Never spawns a CLI turn.

    BOTH halves are patched on purpose. `is_available()` returns TRUE on the dev
    box and on the mac runner, so a test that patched only `CodexClient` would
    still be reading host state, and one that patched neither would execute a real
    `codex exec` turn inside pytest.

    The ledger sink is captured too. The fake response carries a real `usage`
    object — that is what makes the spend assertions meaningful — and without this
    every codex test would append a row to the repo's own data/ai_costs/usage.jsonl,
    a nightly-owned forward ledger. `rec["usage"]` holds what would have been filed.
    """
    cp = pytest.importorskip("engine.codex_provider")
    ac = pytest.importorskip("lib.ai_costs")
    rec: dict = {"init": [], "create": [], "usage": [], "reply": "[]",
                 "available": True}

    class _FakeCodexClient:
        def __init__(self, **kw):
            rec["init"].append(dict(kw))
            self.messages = SimpleNamespace(create=self._create)

        def _create(self, **kwargs):
            rec["create"].append(dict(kwargs))
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=rec["reply"])],
                usage=SimpleNamespace(input_tokens=11, output_tokens=7))

    monkeypatch.setattr(cp, "is_available", lambda: rec["available"])
    monkeypatch.setattr(cp, "CodexClient", _FakeCodexClient)
    monkeypatch.setattr(ac, "record_response_usage",
                        lambda **kw: rec["usage"].append(dict(kw)))
    return rec


def test_codex_provider_sends_the_terra_model(tmp_path, codex):
    codex["reply"] = json.dumps(["美联储降息"])
    cfg = _cfg(tmp_path, provider="codex", model="gpt-5.6-terra")
    assert nt.translate_to_zh(["Fed cuts rates"], cfg) == ["美联储降息"]
    assert len(codex["create"]) == 1
    assert codex["create"][0]["model"] == "gpt-5.6-terra"


def test_codex_keeps_the_batch_json_array_protocol(tmp_path, codex):
    """The transport moved; the contract did not. One request for the whole group,
    a JSON array in, a same-order JSON array out, the same system prompt."""
    codex["reply"] = json.dumps(["美联储降息", "初请失业金人数偏低"])
    out = nt.translate_to_zh(["Fed cuts rates", "Claims come in light"],
                             _cfg(tmp_path, provider="codex"))
    assert out == ["美联储降息", "初请失业金人数偏低"]
    assert len(codex["create"]) == 1, "the batch must stay ONE call"
    sent = codex["create"][0]
    assert sent["system"] == nt.SYSTEM_ZH
    body = sent["messages"][0]["content"]
    assert json.loads(body[body.index("["):]) == ["Fed cuts rates", "Claims come in light"]


def test_codex_model_defaults_to_terra_when_config_omits_it(tmp_path, codex):
    """A codex config with no `model` must not put "deepseek-chat" on the wire.
    translate_model() maps that to Terra anyway, so the call would WORK while the
    usage ledger recorded a model that never ran — a plausible, wrong receipt."""
    codex["reply"] = json.dumps(["美联储降息"])
    cfg = _cfg(tmp_path, provider="codex")
    cfg.pop("model")
    nt.translate_to_zh(["Fed cuts rates"], cfg)
    assert codex["create"][0]["model"] == nt.CODEX_TERRA_MODEL


def test_codex_unavailable_degrades_to_cache_only(tmp_path, codex):
    """A runner with no attached login is the DESIGNED path, not a failure: the
    item ships English and the client marks it 英文原文."""
    codex["available"] = False
    codex["reply"] = json.dumps(["美联储降息"])
    assert nt.translate_to_zh(["Fed cuts rates"], _cfg(tmp_path, provider="codex")) == [None]
    assert codex["init"] == [] and codex["create"] == []


def test_codex_timeout_and_effort_come_from_the_lane_config(tmp_path, codex):
    """The press daemon runs a 75 s tick whose heartbeat only touches after it
    returns, so it passes its own short timeout rather than the 180 s default."""
    codex["reply"] = json.dumps(["美联储降息"])
    nt.translate_to_zh(["Fed cuts rates"],
                       _cfg(tmp_path, provider="codex", timeout_s=20.0,
                            codex_reasoning_effort="low"))
    assert codex["init"] == [{"timeout_s": 20, "reasoning_effort": "low"}]


def test_codex_spend_is_filed_as_a_subscription_not_metered(tmp_path, codex):
    """infer_provider() only reads base_url shapes and the codex path has none, so
    the unguarded call filed an attached-subscription turn as metered claude_api."""
    codex["reply"] = json.dumps(["美联储降息"])
    cfg = _cfg(tmp_path, provider="codex")
    cfg.pop("model")                       # the per-provider default must reach the ledger
    nt.translate_to_zh(["Fed cuts rates"], cfg)
    assert len(codex["usage"]) == 1
    filed = codex["usage"][0]
    assert filed["provider"] == "codex"
    assert filed["cost_basis"] == "subscription"
    assert filed["model"] == nt.CODEX_TERRA_MODEL
    assert filed["lane"] == "news-translate"


def test_the_terra_literal_matches_the_provider_module():
    """The default tier is a literal in news_translate so a deepseek host never
    imports the codex_lane runner. That shortcut is only safe while the two agree."""
    cp = pytest.importorskip("engine.codex_provider")
    assert nt.CODEX_TERRA_MODEL == cp.TERRA_MODEL


def test_the_deepseek_path_is_byte_compatible(tmp_path, monkeypatch):
    """Same SDK, same base_url, same key env, same max_retries — the flip back has
    to be a comment edit, not a rebuild."""
    built: dict = {}

    class _FakeAnthropic:
        def __init__(self, **kw):
            built.update(kw)
            self.messages = SimpleNamespace(
                create=lambda **k: SimpleNamespace(content=[
                    SimpleNamespace(type="text", text=json.dumps(["美联储降息"]))]))

    monkeypatch.setitem(sys.modules, "anthropic",
                        SimpleNamespace(Anthropic=_FakeAnthropic))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-live")
    cfg = _cfg(tmp_path, provider="deepseek", max_retries=0,
               base_url="https://api.deepseek.com/anthropic")
    assert nt.translate_to_zh(["Fed cuts rates"], cfg) == ["美联储降息"]
    assert built == {"api_key": "sk-live", "max_retries": 0,
                     "base_url": "https://api.deepseek.com/anthropic"}


# --------------------------------------------------------------------------- #
# translator_ready — one readiness answer for BOTH providers
# --------------------------------------------------------------------------- #
def test_translator_ready_deepseek_needs_its_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-live")
    assert nt.translator_ready({"provider": "deepseek", "model": "deepseek-chat"}) == (
        True, "deepseek/deepseek-chat")
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    ready, why = nt.translator_ready({"provider": "deepseek"})
    assert not ready and "DEEPSEEK_API_KEY" in why


def test_translator_ready_defaults_to_the_deepseek_shape(monkeypatch):
    """A config with no `provider` key is the pre-directive shape and must stay
    deepseek — an absent key may never be read as "codex, then"."""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    ready, why = nt.translator_ready({})
    assert not ready and "DEEPSEEK_API_KEY" in why


def test_translator_ready_honours_a_custom_key_env(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OTHER_KEY", raising=False)
    ready, why = nt.translator_ready({"api_key_env": "OTHER_KEY"})
    assert not ready and "OTHER_KEY" in why


def test_translator_ready_codex_available_names_the_tier_that_ran(codex):
    assert nt.translator_ready({"provider": "codex", "model": "gpt-5.6-terra"}) == (
        True, "codex/gpt-5.6-terra")


def test_translator_ready_codex_unavailable_does_not_blame_a_key(codex, monkeypatch):
    """The whole point of the helper. On a codex host the old check warned about
    DEEPSEEK_API_KEY — which nothing needs — and stayed silent about the login that
    was actually missing."""
    codex["available"] = False
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-live")
    ready, why = nt.translator_ready({"provider": "codex"})
    assert not ready
    assert "Codex" in why and "DEEPSEEK_API_KEY" not in why


# --------------------------------------------------------------------------- #
# The shipped config + the unit that has to carry the credential
# --------------------------------------------------------------------------- #
def test_the_GLOBAL_config_block_stays_deepseek():
    """Adjudicated 2026-07-31. This block serves the nightly build_news title_zh
    fill, the render-family lanes and the china_news EN direction — all on runners
    that HAVE the DEEPSEEK_API_KEY repo secret and NO codex CLI or attached login.
    Routing the global to codex would dark every one of them, so the codex move is
    a press-lane override (asserted next), never a global flip."""
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load((ROOT / "config.yml").read_text(encoding="utf-8")) or {}
    block = doc.get("news_translation") or {}
    assert nt._provider(block) == "deepseek"
    assert nt._model(block) == "deepseek-chat"
    assert block.get("api_key_env") == "DEEPSEEK_API_KEY"
    assert "deepseek" in str(block.get("base_url", ""))
    assert "codex_reasoning_effort" not in block, (
        "the codex override values are documentation in this file, not live keys")


def test_the_PRESS_LANE_overrides_the_global_onto_codex_terra():
    """The daemon's host is the exact inverse of the nightly's: it carries the
    attached codex login and has never had a DEEPSEEK key. `_zh_cfg` is where this
    lane already diverges from the global block (cache_dir, usage_sink), so the
    provider routing belongs there too."""
    d = pytest.importorskip("scripts.marketing_fastlane_daemon")
    cfg = d._zh_cfg({})
    assert nt._provider(cfg) == "codex"
    assert nt._model(cfg) == nt.CODEX_TERRA_MODEL
    assert cfg["codex_reasoning_effort"] == "low"
    # ...and the lane's own guarantees still hold on top of the override
    assert cfg["usage_sink"] == "none" and cfg["max_retries"] == 0


def test_the_press_lane_override_can_be_flipped_back_without_a_deploy():
    """The escape hatch has to be coherent: flipping the provider must also drop
    the Terra model id, or the lane would post a codex model name to the DeepSeek
    endpoint — a 400 wearing the costume of a config choice."""
    d = pytest.importorskip("scripts.marketing_fastlane_daemon")
    cfg = d._zh_cfg({"zh_provider": "deepseek"})
    assert nt._provider(cfg) == "deepseek"
    assert nt._model(cfg) == "deepseek-chat", "the Terra id must not survive the flip"
    # an explicit model still wins over both defaults
    assert nt._model(d._zh_cfg({"zh_provider": "deepseek",
                                "zh_model": "deepseek-reasoner"})) == "deepseek-reasoner"


def test_the_press_lane_timeout_covers_a_codex_cli_turn():
    """A codex turn is a process spawn PLUS a model call; 20s sized the HTTP path.
    A too-small budget fails SOFT (batch -> None, items ship English), so it is
    silently ineffective rather than loud — hence the floor is pinned."""
    yaml = pytest.importorskip("yaml")
    d = pytest.importorskip("scripts.marketing_fastlane_daemon")
    wire = (yaml.safe_load(
        (ROOT / "config" / "press_sources.yml").read_text(encoding="utf-8")) or {}
    ).get("wire") or {}
    assert float(wire["zh_timeout_s"]) >= 45
    # deleting the key must not silently restore the old HTTP-sized budget
    assert d._zh_cfg({})["timeout_s"] >= 45
    # ...and it still has to fit inside the ~75 s tick
    assert d._zh_cfg({})["timeout_s"] < 75


def test_the_press_unit_carries_the_codex_env():
    """The press daemon is why this provider exists. Without CODEX_HOME and
    CODEX_PROVIDER_ENABLED in its unit the attached login is invisible to it and
    every wire item ships English-only — the same silent failure the lane already
    had under the unprovisioned DEEPSEEK_API_KEY."""
    unit = (ROOT / "app" / "deploy" / "marketing-press-feeds.service").read_text(
        encoding="utf-8")
    live = [ln.strip() for ln in unit.splitlines() if not ln.lstrip().startswith("#")]
    assert "Environment=CODEX_HOME=/var/lib/macro-codex" in live
    assert "Environment=CODEX_PROVIDER_ENABLED=1" in live


def test_the_press_preflight_asks_the_translator_not_the_deepseek_key(
        monkeypatch, caplog, codex):
    """Regression: a codex host with no DEEPSEEK_API_KEY logged a warning about a
    key nothing needs, once per 75 s tick, while translation worked fine."""
    d = pytest.importorskip("scripts.marketing_fastlane_daemon")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(d, "_zh_cfg", lambda wc: {
        "enabled": True, "provider": "codex", "model": "gpt-5.6-terra"})

    with caplog.at_level(logging.WARNING):
        d._zh_preflight({"zh_enabled": True})
    assert caplog.text == "", "a ready codex host must warn about nothing"

    codex["available"] = False
    with caplog.at_level(logging.WARNING):
        d._zh_preflight({"zh_enabled": True})
    assert "translator is not ready" in caplog.text
    assert "attached Codex account" in caplog.text
    assert "DEEPSEEK_API_KEY" not in caplog.text
