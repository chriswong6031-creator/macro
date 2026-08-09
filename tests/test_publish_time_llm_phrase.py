"""tests/test_publish_time_llm_phrase.py — the OPTIONAL publish-time wire phrase pass.

Covers `engine.marketing.publish_time_content.phrase_or_template` and its
`wire_violations` law set: the LLM re-wording layer that sits on top of the
deterministic v3 template copy for `mover` / `theme_list` posts.

THE ONE PROPERTY EVERY TEST HERE IS ABOUT: **a live mover is never blocked or
delayed by a model.** Disabled, unarmed, no credential, provider exception, empty
reply, a phrase that breaks one wire law, or a pass that outruns its budget all
return the caller's deterministic template string UNCHANGED, and the public entry
point never raises.

ZERO NETWORK, ZERO SUBPROCESS. Every provider is monkeypatched at
`engine.llm_auth.build_providers` / `.make_call`, which is where
`phrase_or_template` reaches for its waterfall (lazily, inside the call), so a
host with no credentials and no Codex CLI runs this file identically to one with
both.

Run: .venv/bin/python -m pytest tests/test_publish_time_llm_phrase.py -q
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from engine import llm_auth
from engine.marketing import publish_time_content as pt


# Thursday 2026-07-23, 14:05 UTC == 10:05 ET (the AM slot), matching
# tests/test_marketing_publish_time_content.py so the two files reason about the
# same session when they talk about "today" and "on Friday".
NOW = datetime(2026, 7, 23, 14, 5, 0, tzinfo=timezone.utc)

#: A deterministic render in this lane's shape: headline, blank line, body.
TEMPLATE = ("Mover of the day.\n\n"
            "$NVDA is up 7.2% today on the tape. Watching the 180 level.")

#: The engine-computed facts that go with it. Numbers here are admissible in a
#: phrase even when the template did not print them (8.1 is the 5-day move).
FACTS = {"ticker": "NVDA", "cashtag": "$NVDA", "pct": 7.2, "pct_5d": 8.1,
         "level": 180, "asof": "2026-07-23"}

#: A rewrite that clears every law: same ticker, same numbers, no new session
#: claim, wire register, no first person, no CTA, no emoji, no dash tells.
CLEAN_PHRASE = "$NVDA up 7.2% today. The 180 level is the line."

ARMED_CFG = {"publish": {"publish_time_movers": {"llm": {
    "enabled": True,
    # Small so the timeout test does not sit for the production 20s. Every other
    # test resolves long before any budget matters.
    "budget_s": 5.0,
}}}}


@pytest.fixture(autouse=True)
def _clean_module_state(monkeypatch):
    """Zero the per-process counters and the call cap around every test."""
    pt.reset_phrase_stats()
    monkeypatch.delenv(pt._LLM_ENV_FLAG, raising=False)
    yield
    pt.reset_phrase_stats()


def _arm(monkeypatch) -> None:
    """Set the environment half of the two-key arming."""
    monkeypatch.setenv(pt._LLM_ENV_FLAG, "1")


def _serve(monkeypatch, phrase: str, *, provider: str = "codex") -> dict:
    """Wire a fake one-rung waterfall that answers with *phrase*.

    Returns the capture dict the provider-config assertions read.
    """
    captured: dict = {}

    def _fake_build(cfg_dict, **kwargs):
        captured["cfg"] = dict(cfg_dict)
        captured["kwargs"] = dict(kwargs)
        return [{"name": provider, "client": object(), "model": "fake"}]

    def _fake_call(providers, call_fn, *, context: str = "", attempts=None):
        captured["context"] = context
        captured["providers"] = providers
        return phrase, None, provider

    monkeypatch.setattr(llm_auth, "build_providers", _fake_build)
    monkeypatch.setattr(llm_auth, "make_call", _fake_call)
    return captured


# ─────────────────────────────────────────────────────────────────────────────
# (a) OFF-safe — the template comes back byte-identical
# ─────────────────────────────────────────────────────────────────────────────

def test_disabled_returns_template_byte_identical():
    """No config block at all: no provider, no call, the same string back."""
    out = pt.phrase_or_template(TEMPLATE, facts=FACTS, kind="mover", now=NOW, cfg={})
    assert out["mode"] == "off"
    assert out["text"] == TEMPLATE          # byte-identical, not merely equal-ish
    assert out["text"] is not None and out["provider"] is None
    assert out["violations"] == []


def test_env_flag_without_config_does_not_arm(monkeypatch):
    """One key is not arming: the env flag alone leaves the desk disarmed."""
    _arm(monkeypatch)
    out = pt.phrase_or_template(TEMPLATE, facts=FACTS, now=NOW, cfg={})
    assert out["mode"] == "off" and out["text"] == TEMPLATE


def test_config_enabled_without_env_flag_does_not_arm(monkeypatch):
    """The other key alone is not arming either — and no provider is built."""
    def _boom(*_a, **_kw):  # pragma: no cover — must never be reached
        raise AssertionError("build_providers must not be called while disarmed")

    monkeypatch.setattr(llm_auth, "build_providers", _boom)
    out = pt.phrase_or_template(TEMPLATE, facts=FACTS, now=NOW, cfg=ARMED_CFG)
    assert out["mode"] == "off" and out["text"] == TEMPLATE


def test_disarmed_pass_builds_no_provider_and_costs_no_latency(monkeypatch):
    """Disarmed is a dict build and a return: no waterfall, no credential read."""
    calls: list = []
    monkeypatch.setattr(llm_auth, "build_providers",
                        lambda *a, **k: calls.append(a) or [])
    monkeypatch.setattr(llm_auth, "make_call",
                        lambda *a, **k: calls.append(a) or (None, None, None))
    out = pt.phrase_or_template(TEMPLATE, facts=FACTS, now=NOW, cfg={})
    assert out["mode"] == "off" and calls == []


# ─────────────────────────────────────────────────────────────────────────────
# (b) The provider path fails — the template still ships
# ─────────────────────────────────────────────────────────────────────────────

def test_build_providers_raises_returns_template(monkeypatch):
    _arm(monkeypatch)

    def _raise(*_a, **_kw):
        raise RuntimeError("credential store on fire")

    monkeypatch.setattr(llm_auth, "build_providers", _raise)
    out = pt.phrase_or_template(TEMPLATE, facts=FACTS, now=NOW, cfg=ARMED_CFG)
    assert out["mode"] == "fallback_provider"
    assert out["text"] == TEMPLATE


def test_make_call_raises_returns_template(monkeypatch):
    """An exception raised on the worker THREAD still reaches the fallback.

    The pass runs its waterfall on a daemon thread, so an exception there is
    invisible to a naive `try` around the call site — `_run_with_deadline`
    re-raises it into the caller precisely so this branch exists.
    """
    _arm(monkeypatch)
    monkeypatch.setattr(llm_auth, "build_providers",
                        lambda *a, **k: [{"name": "codex", "client": object(),
                                          "model": "fake"}])

    def _raise(*_a, **_kw):
        raise RuntimeError("every rung 401'd")

    monkeypatch.setattr(llm_auth, "make_call", _raise)
    out = pt.phrase_or_template(TEMPLATE, facts=FACTS, now=NOW, cfg=ARMED_CFG)
    assert out["mode"] == "fallback_provider"
    assert out["text"] == TEMPLATE


def test_no_credential_annotates_at_line_start_and_falls_back(monkeypatch, capsys):
    """ARMED BUT MUTE is announced with a bare print at column 0.

    GitHub only parses a workflow command when `::` starts the line, and every
    logger in this repo prefixes its records — so this assertion is the guard
    that the alarm is not silently dropped (tests/test_gh_annotation_line_start.py
    pins the same law statically).
    """
    _arm(monkeypatch)
    monkeypatch.setattr(llm_auth, "build_providers", lambda *a, **k: [])
    out = pt.phrase_or_template(TEMPLATE, facts=FACTS, now=NOW, cfg=ARMED_CFG)
    assert out["mode"] == "fallback_provider" and out["text"] == TEMPLATE
    printed = capsys.readouterr().out
    hits = [ln for ln in printed.splitlines()
            if ln.startswith("::warning title=publish-time-wire-mute::")]
    assert hits, f"no line-start mute annotation in: {printed!r}"


def test_empty_model_reply_returns_template(monkeypatch):
    _arm(monkeypatch)
    _serve(monkeypatch, "")
    out = pt.phrase_or_template(TEMPLATE, facts=FACTS, now=NOW, cfg=ARMED_CFG)
    assert out["mode"] == "fallback_provider" and out["text"] == TEMPLATE


# ─────────────────────────────────────────────────────────────────────────────
# (c) The phrase breaks a wire law — the template still ships
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("phrase, law", [
    ("$NVDA up 7.2% today!", "exclamation_banned"),
    ("$NVDA up 9.9% today.", "number '9.9%' not in FactPacket"),
    ("$NVDA up 7.2% today \U0001F680", "emoji_banned"),
    ("$NVDA up 7.2% today — clean tape.", "dash_or_smart_quote_banned"),
    ("$NVDA up 7.2% today. #stocks", "hashtag_banned"),
    ("My read: $NVDA up 7.2% today.", "first_person_banned"),
    ("$NVDA up 7.2% today. Follow for more.", "engagement_cta"),
    ("$AMD up 7.2% today.", "cashtag_not_in_template"),
    ("The tape is up 7.2% today.", "cashtag_dropped"),
    ("$NVDA up 7.2% on Friday.", "session_claim_not_in_template"),
    ("$NVDA up 7.2% today. https://example.com/x", "link_not_in_template"),
    ("$NVDA up 7.2% today. " + "The tape is wide open and the level holds. " * 8,
     "too long"),
])
def test_violating_phrase_returns_template(monkeypatch, phrase, law):
    """Every law is fail-to-template, and the reason travels on the result."""
    _arm(monkeypatch)
    _serve(monkeypatch, phrase)
    out = pt.phrase_or_template(TEMPLATE, facts=FACTS, now=NOW, cfg=ARMED_CFG)
    assert out["text"] == TEMPLATE, f"{law}: phrase shipped anyway"
    assert out["mode"] == "fallback_validation"
    assert any(law in v for v in out["violations"]), out["violations"]


def test_wire_violations_is_clean_on_a_compliant_phrase():
    assert pt.wire_violations(CLEAN_PHRASE, TEMPLATE, facts=FACTS, now=NOW) == []


def test_a_fact_number_the_template_did_not_print_is_allowed():
    """`facts` widens the whitelist: the engine computed 8.1, so the copy may say it."""
    phrase = "$NVDA up 7.2% today, 8.1% over five sessions."
    assert pt.wire_violations(phrase, TEMPLATE, facts=FACTS, now=NOW) == []
    # ...and it is NOT allowed when the facts are withheld — the whitelist is the
    # packet, not a guess about which numbers look plausible.
    assert pt.wire_violations(phrase, TEMPLATE, facts=None, now=NOW)


def test_session_claim_matching_the_template_is_allowed():
    """The subset law rejects a NEW claim, not the template's own day word."""
    assert pt.wire_violations("$NVDA up 7.2% today.", TEMPLATE,
                              facts=FACTS, now=NOW) == []


def test_empty_phrase_is_a_violation():
    assert pt.wire_violations("   ", TEMPLATE, facts=FACTS, now=NOW) == ["empty_phrase"]


# ─────────────────────────────────────────────────────────────────────────────
# (d) A clean phrase serves
# ─────────────────────────────────────────────────────────────────────────────

def test_clean_phrase_is_returned(monkeypatch):
    _arm(monkeypatch)
    _serve(monkeypatch, CLEAN_PHRASE)
    out = pt.phrase_or_template(TEMPLATE, facts=FACTS, kind="mover",
                                now=NOW, cfg=ARMED_CFG)
    assert out["text"] == CLEAN_PHRASE
    assert out["mode"] == "llm"
    assert out["provider"] == "codex"
    assert out["violations"] == []
    assert pt.phrase_stats()["llm"] == 1


def test_model_wrappers_are_stripped_before_the_laws_run(monkeypatch):
    """A fenced/quoted reply is tidied, not rejected for its wrapper."""
    _arm(monkeypatch)
    _serve(monkeypatch, f'```\n"{CLEAN_PHRASE}"\n```')
    out = pt.phrase_or_template(TEMPLATE, facts=FACTS, now=NOW, cfg=ARMED_CFG)
    assert out["mode"] == "llm" and out["text"] == CLEAN_PHRASE


def test_provider_config_is_the_terra_wire_lane(monkeypatch):
    """The routing contract: codex-first, TERRA at low effort, publish-time-wire.

    House model-tier law — sol writes long-form copy, terra critiques and WIRES,
    luna never touches user-facing words. This is a wire lane, so a future edit
    that "upgrades" the source model to sol is a routing regression, not a
    quality improvement. `codex_timeout_s` is asserted EXPLICITLY because
    llm_auth silently reuses `client_timeout_s` for the codex SUBPROCESS when the
    key is absent, which would hand an HTTP socket budget to a process.
    """
    _arm(monkeypatch)
    cap = _serve(monkeypatch, CLEAN_PHRASE)
    pt.phrase_or_template(TEMPLATE, facts=FACTS, now=NOW, cfg=ARMED_CFG)
    cfg = cap["cfg"]
    assert cfg["provider_order"] == ["codex", "oauth", "anthropic", "deepseek"]
    assert cfg["codex_source_model"] == "gpt-5.6-terra"
    assert cfg["codex_reasoning_effort"] == "low"
    assert cfg["usage_lane"] == "publish-time-wire"
    assert cfg["oauth_pool_lane"] == "publish-time-wire"
    assert "codex_timeout_s" in cfg, "the codex SUBPROCESS budget must be explicit"
    assert float(cfg["codex_timeout_s"]) == float(pt._LLM_DEFAULTS["codex_timeout_s"])
    assert float(cfg["client_timeout_s"]) == float(pt._LLM_DEFAULTS["client_timeout_s"])
    assert int(cfg["client_max_retries"]) == 0
    assert cap["context"] == "publish_time_wire"


def test_default_budget_is_twenty_seconds_or_less():
    """The stated hard budget for the whole pass."""
    assert float(pt._LLM_DEFAULTS["budget_s"]) <= 20.0
    assert pt._LLM_DEFAULTS["enabled"] is False
    assert pt._LLM_DEFAULTS["codex_source_model"] == "gpt-5.6-terra"


# ─────────────────────────────────────────────────────────────────────────────
# The wall clock — a live mover is never DELAYED either
# ─────────────────────────────────────────────────────────────────────────────

def test_pass_gives_up_at_its_budget_and_returns_template(monkeypatch):
    """A hung provider costs the caller its budget, not the provider's timeout."""
    _arm(monkeypatch)
    monkeypatch.setattr(llm_auth, "build_providers",
                        lambda *a, **k: [{"name": "codex", "client": object(),
                                          "model": "fake"}])

    def _hang(*_a, **_kw):
        time.sleep(30)  # daemon thread; abandoned, never joined
        return CLEAN_PHRASE, None, "codex"   # pragma: no cover

    monkeypatch.setattr(llm_auth, "make_call", _hang)
    cfg = {"publish": {"publish_time_movers": {"llm": {
        "enabled": True, "budget_s": 0.4}}}}
    started = time.monotonic()
    out = pt.phrase_or_template(TEMPLATE, facts=FACTS, now=NOW, cfg=cfg)
    elapsed = time.monotonic() - started
    assert out["mode"] == "fallback_timeout"
    assert out["text"] == TEMPLATE
    assert elapsed < 5.0, f"the deadline did not bound the caller ({elapsed:.1f}s)"


def test_per_run_call_cap_falls_back_rather_than_grinding(monkeypatch):
    _arm(monkeypatch)
    _serve(monkeypatch, CLEAN_PHRASE)
    cfg = {"publish": {"publish_time_movers": {"llm": {
        "enabled": True, "budget_s": 5.0, "max_calls_per_run": 1}}}}
    first = pt.phrase_or_template(TEMPLATE, facts=FACTS, now=NOW, cfg=cfg)
    second = pt.phrase_or_template(TEMPLATE, facts=FACTS, now=NOW, cfg=cfg)
    assert first["mode"] == "llm"
    assert second["mode"] == "fallback_provider" and second["text"] == TEMPLATE


# ─────────────────────────────────────────────────────────────────────────────
# (e) The pass never raises
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("template", ["", None, TEMPLATE])
@pytest.mark.parametrize("cfg", [
    None, {}, [], "not-a-dict", {"publish": None},
    {"publish": {"publish_time_movers": {"llm": {"enabled": "yes",
                                                 "budget_s": "not-a-number",
                                                 "provider_order": 5}}}},
])
def test_never_raises_on_hostile_inputs(monkeypatch, template, cfg):
    _arm(monkeypatch)
    _serve(monkeypatch, CLEAN_PHRASE)
    out = pt.phrase_or_template(template, facts=FACTS, now=NOW, cfg=cfg)
    assert isinstance(out, dict) and isinstance(out["text"], str)
    assert out["mode"] in {"off", "llm", "fallback_provider",
                           "fallback_validation", "fallback_timeout"}


@pytest.mark.parametrize("reply", [
    None, 0, object(), b"bytes", ["a", "list"], "\n\n\n",
])
def test_never_raises_on_a_hostile_model_reply(monkeypatch, reply):
    _arm(monkeypatch)
    monkeypatch.setattr(llm_auth, "build_providers",
                        lambda *a, **k: [{"name": "codex", "client": object(),
                                          "model": "fake"}])
    monkeypatch.setattr(llm_auth, "make_call",
                        lambda *a, **k: (reply, None, "codex"))
    out = pt.phrase_or_template(TEMPLATE, facts=FACTS, now=NOW, cfg=ARMED_CFG)
    assert out["text"] in {TEMPLATE, str(reply)}
    assert out["mode"] != "llm" or out["text"] != TEMPLATE


def test_never_raises_when_make_call_returns_a_bad_shape(monkeypatch):
    _arm(monkeypatch)
    monkeypatch.setattr(llm_auth, "build_providers",
                        lambda *a, **k: [{"name": "codex", "client": object(),
                                          "model": "fake"}])
    monkeypatch.setattr(llm_auth, "make_call", lambda *a, **k: "not-a-tuple")
    out = pt.phrase_or_template(TEMPLATE, facts=FACTS, now=NOW, cfg=ARMED_CFG)
    assert out["text"] == TEMPLATE and out["mode"] == "fallback_provider"


def test_wire_violations_never_raises_on_hostile_text():
    for bad in ("", None, "\x00\x01", "$" * 400, "1" * 400):
        assert isinstance(
            pt.wire_violations(bad, TEMPLATE, facts=FACTS, now=NOW), list)
    # A missing clock simply skips the session-claim law rather than failing.
    assert pt.wire_violations(CLEAN_PHRASE, TEMPLATE, facts=FACTS, now=None) == []


# ─────────────────────────────────────────────────────────────────────────────
# The shipped config block
# ─────────────────────────────────────────────────────────────────────────────

def test_marketing_yml_ships_the_block_disarmed():
    """config/marketing.yml carries the lane's llm block, and it is OFF."""
    yaml = pytest.importorskip("yaml")
    root = Path(__file__).resolve().parent.parent
    cfg = yaml.safe_load(
        (root / "config" / "marketing.yml").read_text(encoding="utf-8")) or {}
    block = (((cfg.get("publish") or {}).get("publish_time_movers") or {})
             .get("llm") or {})
    assert block, "publish.publish_time_movers.llm is missing from marketing.yml"
    assert block.get("enabled") is False, "the wire phrase pass must ship DARK"
    assert block.get("provider_order") == ["codex", "oauth", "anthropic", "deepseek"]
    assert block.get("codex_source_model") == "gpt-5.6-terra"
    assert block.get("codex_reasoning_effort") == "low"
    assert block.get("usage_lane") == "publish-time-wire"
    assert float(block.get("budget_s")) <= 20.0
    assert float(block.get("codex_timeout_s")) > 0



# ─────────────────────────────────────────────────────────────────────────────
# The WIRING — the pass sits between the template's validation and the gates
#
# Fixtures mirror tests/test_marketing_publish_time_content.py (tmp_path root,
# injected now=, zero network) and run DRY (live=False), which skips the card
# raster and every data/ write while still exercising the whole copy path.
# ─────────────────────────────────────────────────────────────────────────────

NOW_MS = int(NOW.timestamp() * 1000)
NOW_ISO = NOW.strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _write_snapshot(tmp: Path, quotes: dict) -> None:
    p = tmp / "data" / "marketing"
    p.mkdir(parents=True, exist_ok=True)
    q = {t: {"price": v[0], "prevClose": v[1], "changePct": v[2], "ts": NOW_MS}
         for t, v in quotes.items()}
    (p / "live_quotes_snapshot.json").write_text(
        json.dumps({"asof": NOW_ISO, "quotes": q}), encoding="utf-8")


def _write_sp500(tmp: Path, tiles: list[dict]) -> None:
    p = tmp / "site" / "marketdata"
    p.mkdir(parents=True, exist_ok=True)
    (p / "sp500_heatmap.json").write_text(
        json.dumps({"asof": "2026-07-22", "tiles": tiles}), encoding="utf-8")


def _lane_cfg(llm: dict | None) -> dict:
    """The lane armed for ONE mover on one desk, with *llm* as its phrase block."""
    block: dict = {
        "enabled": True, "max_per_run": 1,
        "min_abs_mover_pct": 3.0, "min_abs_theme_pct": 1.0,
        "max_quote_age_min": 45, "min_active_tiles": 1,
        "max_theme_cashtags_in_text": 3, "accounts": ["flagship"],
    }
    if llm is not None:
        block["llm"] = llm
    return {
        "publish": {"publish_time_movers": block, "channels": {"flagship": "c1"}},
        "desk_network": {"accounts": [{"id": "flagship",
                                      "voice": "authoritative desk"}]},
        "copywriter": {"personas": {"flagship": {
            "name": "The Desk", "voice_notes": "terse. Emoji budget: 0"}}},
    }


def _dry_run(tmp: Path, cfg: dict) -> dict:
    from engine.marketing import outbox
    return pt.generate_slot_items(
        tmp, cfg=cfg, now=NOW, state=outbox.fold_state(tmp), approved_due=[],
        posted_counts={}, cap=2, live=False, account_filter=None)


def _seed_tape(tmp: Path) -> None:
    _write_sp500(tmp, [{"t": "AMD", "name": "AMD", "sector": "Tech",
                        "perf": {"1D": 0.1}}])
    _write_snapshot(tmp, {"AMD": (150.0, 144.0, 4.2)})


def test_wiring_disarmed_reports_off_and_leaves_the_post_unchanged(tmp_path):
    """No llm block ⇒ every item is tallied `off` and carries template copy."""
    _seed_tape(tmp_path)
    rep = _dry_run(tmp_path, _lane_cfg(None))
    assert rep["would_generate"], rep["dropped"]
    assert rep["llm_phrase_modes"] == {"off": len(rep["would_generate"])}


def test_wiring_rejected_phrase_ships_the_same_post_as_a_disarmed_run(
        tmp_path, monkeypatch):
    """A phrase that breaks a wire law costs the post nothing at all."""
    _seed_tape(tmp_path)
    baseline = _dry_run(tmp_path, _lane_cfg({"enabled": False}))
    assert baseline["would_generate"], baseline["dropped"]

    _arm(monkeypatch)
    _serve(monkeypatch, "$AMD is ripping today!!!")
    armed = _dry_run(tmp_path, _lane_cfg({"enabled": True, "budget_s": 5.0}))
    assert armed["llm_phrase_modes"].get("fallback_validation") == 1
    assert (armed["would_generate"][0]["text"]
            == baseline["would_generate"][0]["text"])


def test_wiring_clean_phrase_reaches_the_post(tmp_path, monkeypatch):
    """An accepted phrase replaces the template text and clears the gates below.

    The reply is derived from the template the pass actually handed the model
    (captured through `_wire_user_message`), so this asserts the substitution
    without hard-coding whichever v3 variant the deterministic picker landed on.
    """
    _seed_tape(tmp_path)
    _arm(monkeypatch)

    seen: dict = {}
    real_user_msg = pt._wire_user_message

    def _capture(template_text, facts, kind):
        seen["template"] = template_text
        return real_user_msg(template_text, facts, kind)

    monkeypatch.setattr(pt, "_wire_user_message", _capture)
    monkeypatch.setattr(llm_auth, "build_providers",
                        lambda *a, **k: [{"name": "codex", "client": object(),
                                          "model": "fake"}])

    def _fake_call(providers, call_fn, *, context: str = "", attempts=None):
        tag = pt._CASHTAG_RE.findall(seen["template"].upper())[0]
        # No number, no session word, one cashtag already in the template: a
        # phrase that is subset-clean by construction.
        return f"{tag} tape check.", None, "codex"

    monkeypatch.setattr(llm_auth, "make_call", _fake_call)
    rep = _dry_run(tmp_path, _lane_cfg({"enabled": True, "budget_s": 5.0}))
    assert rep["would_generate"], rep["dropped"]
    assert rep["llm_phrase_modes"].get("llm") == 1
    assert rep["would_generate"][0]["text"].endswith("tape check.")
    assert "$AMD" in rep["would_generate"][0]["text"]


def test_config_block_resolves_through_the_lane_resolver():
    """The shipped YAML actually lands on `_llm_cfg` (paths, not just presence)."""
    yaml = pytest.importorskip("yaml")
    root = Path(__file__).resolve().parent.parent
    cfg = yaml.safe_load(
        (root / "config" / "marketing.yml").read_text(encoding="utf-8")) or {}
    resolved = pt._llm_cfg(cfg)
    assert resolved["enabled"] is False
    assert resolved["codex_source_model"] == "gpt-5.6-terra"
    assert resolved["usage_lane"] == "publish-time-wire"
    assert float(resolved["budget_s"]) <= 20.0
