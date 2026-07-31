"""tests/test_marketing_hot_tape_llm.py — Hot Tape P2 LLM wire desk acceptance tests.

Program: Hot Tape (research/MARKETING_HOT_TAPE_MASTERPLAN.md §3.3), gates 0.2
(differentiating stat), 0.3 (facts are engine-computed) and 0.4 (observations,
not calls).

Fixture-driven; ZERO live network, ZERO live LLM. Every provider-path test
monkeypatches engine.llm_auth.build_providers / make_call, and the env flag is
set through monkeypatch so it can never leak into another suite. Import closure
is stdlib + pyyaml (jinja2 is installed in the lane but unused here) — the thin
marketing-engine CI lane has NO anthropic package, so a top-level
``import anthropic`` in engine/marketing/hot_tape_llm.py would turn this file red
at COLLECTION. Test 15 pins that mechanically as well.

Covers:
  1.  Every golden packet's human wire post clears every gate.
  2.  Numeric rejection: an invented -56%, an inflated -$210 billion.
  3.  Scale forms: $200 billion / $200B / 200,000,000,000 / $1 TRILLION.
  4.  Dates + years: "June 22nd" and "2026" pass, "June 23rd" does not.
  5.  Hedge rejection on the corpus's 95-view anti-example.
  6.  Call-language rejection, and "long-term" surviving the "long" ban.
  7.  Cashtag policy: unknown, repeated-primary, multi-name sector post.
  8.  Hashtag ban + the 280 cap via social_publisher.validate_postable.
  9.  Provider failure -> fallback_provider, template text, counters move.
  10. make_call raising -> fallback_provider, never raises out.
  11. A hallucinated number -> fallback_validation with violations populated.
  12. Success -> mode "llm", the model's text, the provider recorded.
  13. Disarmed -> mode "off" and NO provider call at all.
  14. Armed but mute -> a ::warning annotation at the START of the line.
  15. Import closure: no anthropic / llm_auth / yaml at module import.
  16. Prompt pins: the three exemplars, the anti-example, the numbers law.
  17. config.yml ships the hot_tape block + the hot_tape_wire model id.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import pytest
import yaml


def _worktree_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Could not locate repo root from {p}")


ROOT = _worktree_root()
sys.path.insert(0, str(ROOT))

from engine import llm_auth  # noqa: E402
from engine.marketing import hot_tape_llm as htl  # noqa: E402

MODULE_PATH = ROOT / "engine" / "marketing" / "hot_tape_llm.py"
FIXTURE = ROOT / "tests" / "fixtures" / "hot_tape_golden_packets.json"
GOLDEN = json.loads(FIXTURE.read_text(encoding="utf-8"))["packets"]
BY_ID = {e["id"]: e for e in GOLDEN}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

#: The llm cfg block, injected directly so no test depends on config.yml's
#: shipped `enabled:` value.
ARMED_CFG = {"enabled": True, "max_calls_per_run": 25, "max_tokens": 300}

_FAKE_PROVIDER = {
    "name": "oauth",
    "env_var": "CLAUDE_CODE_OAUTH_TOKEN",
    "cred": "not-a-real-token",
    "client": object(),
    "model": "claude-sonnet-4-6",
}


def _arm(monkeypatch, providers=(_FAKE_PROVIDER,)) -> None:
    """Arm the lane and hand it a fake provider list (never a real credential)."""
    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    monkeypatch.setattr(llm_auth, "build_providers", lambda *a, **k: list(providers))
    htl.reset_stats()


def _packet(pid: str) -> dict:
    return BY_ID[pid]["packet"]


# ─────────────────────────────────────────────────────────────────────────────
# 1. The golden posts clear every gate
# ─────────────────────────────────────────────────────────────────────────────

def test_every_golden_good_phrasing_passes_every_gate():
    # P1-P3 are the operator's corpus winners verbatim. If a gate rejects one of
    # them, the gate is wrong — these posts are the target, not the hazard.
    for entry in GOLDEN:
        violations = htl.validate_wire_copy(
            entry["good_phrasing"], entry["packet"],
            link=entry.get("link"), links_allowed=entry.get("links_allowed", True),
        )
        assert violations == [], f"{entry['id']} good_phrasing rejected: {violations}"


def test_every_golden_fallback_text_passes_every_gate():
    # The deterministic template is what ships on every failure path, so it has
    # to clear the same bar the model's copy does.
    for entry in GOLDEN:
        violations = htl.validate_wire_copy(
            entry["fallback_text"], entry["packet"],
            link=entry.get("link"), links_allowed=entry.get("links_allowed", True),
        )
        assert violations == [], f"{entry['id']} fallback_text rejected: {violations}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Numeric rejection — the gate-0.3 core
# ─────────────────────────────────────────────────────────────────────────────

def test_invented_number_is_rejected():
    p1 = _packet("P1")
    # The packet says -55; -56 is the shape of a model faking precision by
    # rounding half-up. Nothing in P1 licenses it.
    hits = htl.numeric_violations("$SNDK is now -56% from its record high.", p1)
    assert hits == ["number '-56%' not in FactPacket"], hits


def test_inflated_dollar_translation_is_rejected():
    hits = htl.numeric_violations(
        "$SNDK has lost -$210 billion in market cap.", _packet("P1"))
    assert len(hits) == 1 and "210" in hits[0], hits


def test_truncated_display_form_is_accepted():
    # "over -17%" is the corpus's own phrasing of a -17.0 packet value.
    assert htl.numeric_violations("$SNDK falls over -17% on the day.", _packet("P1")) == []


# ─────────────────────────────────────────────────────────────────────────────
# 3. Scale forms
# ─────────────────────────────────────────────────────────────────────────────

def test_scale_forms_all_resolve_to_the_same_packet_value():
    p1 = _packet("P1")  # dollar_change_abs = 2.0e11
    for text in ("$SNDK has lost $200 billion in market cap.",
                 "$SNDK has lost $200B in market cap.",
                 "$SNDK has lost 200,000,000,000 in market cap."):
        assert htl.numeric_violations(text, p1) == [], text


def test_trillion_scale_form_accepted():
    assert htl.numeric_violations(
        "$1 TRILLION has been wiped out from $NVDA marketcap.", _packet("P3")) == []


# ─────────────────────────────────────────────────────────────────────────────
# 4. Dates and years
# ─────────────────────────────────────────────────────────────────────────────

def test_date_components_and_year_are_admissible():
    p1 = _packet("P1")  # since_date 2026-06-22, as_of 2026-07-28
    assert htl.numeric_violations("$SNDK has bled since June 22nd.", p1) == []
    assert htl.numeric_violations("$SNDK is having its worst run of 2026.", p1) == []


def test_wrong_day_of_month_is_rejected():
    hits = htl.numeric_violations("$SNDK has bled since June 23rd.", _packet("P1"))
    assert hits == ["number '23rd' not in FactPacket"], hits


# ─────────────────────────────────────────────────────────────────────────────
# 5. Hedging — the anti-example
# ─────────────────────────────────────────────────────────────────────────────

def test_anti_example_is_rejected_for_hedging():
    hits = htl.hedge_violations(htl.ANTI_EXEMPLAR)
    assert hits == ["hedge:'seems'"], hits


def test_hedge_lexicon_covers_the_common_shapes():
    for text, word in (("it looks like a bottom", "looks like"),
                       ("this might extend", "might"),
                       ("we think the pause continues", "we think"),
                       ("it should keep going", "should")):
        assert f"hedge:'{word}'" in htl.hedge_violations(text), text


# ─────────────────────────────────────────────────────────────────────────────
# 6. Call language (gate 0.4)
# ─────────────────────────────────────────────────────────────────────────────

def test_call_language_is_rejected():
    assert "call_language:'added'" in htl.call_violations("added $SNDK here")
    assert "call_language:'buy'" in htl.call_violations("buy the dip")
    assert "call_language:'long'" in htl.call_violations("we are long $SNDK")


def test_long_term_does_not_trip_the_long_ban():
    # The ban is on the position word, not the English adjective.
    assert htl.call_violations("long-term holders have seen worse") == []
    assert htl.call_violations("a shortfall in memory supply") == []


# ─────────────────────────────────────────────────────────────────────────────
# 7. Cashtag policy
# ─────────────────────────────────────────────────────────────────────────────

def test_unknown_cashtag_is_rejected():
    hits = htl.validate_wire_copy(
        "$SNDK -17% today while $SPY holds.", _packet("P1"))
    assert "unknown_cashtag:'$SPY'" in hits, hits


def test_repeated_primary_cashtag_on_a_single_name_post_is_rejected():
    p2 = _packet("P2")
    hits = htl.validate_wire_copy(
        "$META has closed red 9 sessions in a row. $META has not done that in 5 years.", p2)
    assert any(v.startswith("primary_cashtag_repeated:") for v in hits), hits


def test_sector_post_may_carry_every_member_cashtag():
    entry = BY_ID["P4"]
    assert htl.validate_wire_copy(entry["good_phrasing"], entry["packet"]) == []


def test_sentence_ending_cashtag_keeps_its_punctuation_out_of_the_tag():
    # A greedy tag regex reads "…led by $NVDA." as the cashtag "$NVDA." and
    # rejects clean copy as a smuggled comparison.
    hits = htl.validate_wire_copy(
        "The chip tape is red, led by $NVDA.", _packet("P4"))
    assert hits == [], hits
    # The share-class form still parses as one tag.
    assert htl.validate_wire_copy(
        "$BRK.B is flat.", {"cashtag": "$BRK.B", "cashtags": ["$BRK.B"]}) == []


def test_url_fragment_is_not_a_hashtag():
    entry = BY_ID["P5"]
    text = entry["good_phrasing"] + " https://www.mastermind-x.com/us_stocks.html#plan"
    assert "hashtag_banned" not in htl.validate_wire_copy(
        text, entry["packet"], link=None, links_allowed=True)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Hashtags + the 280 cap
# ─────────────────────────────────────────────────────────────────────────────

def test_hashtag_is_rejected_but_a_day_number_is_not():
    assert "hashtag_banned" in htl.validate_wire_copy(
        "$SNDK -17% today #semis", _packet("P1"))
    # "Day #9" is the corpus's streak device — # followed by a DIGIT is not a
    # hashtag, and house exemplar 2 depends on that distinction.
    assert "hashtag_banned" not in htl.validate_wire_copy(
        BY_ID["P2"]["good_phrasing"], _packet("P2"))


def test_over_280_is_rejected_through_the_publisher_gate():
    long_text = "$SNDK " + "the tape keeps bleeding " * 13  # ~318 chars, no digits
    assert len(long_text) > 300
    hits = htl.validate_wire_copy(long_text, _packet("P1"))
    assert any(v.startswith("over_280:") for v in hits), hits


# ─────────────────────────────────────────────────────────────────────────────
# 9-12. The provider path (all fake, zero network)
# ─────────────────────────────────────────────────────────────────────────────

def test_provider_failure_falls_back_to_the_template(monkeypatch):
    _arm(monkeypatch)
    monkeypatch.setattr(llm_auth, "make_call",
                        lambda *a, **k: (None, "rate_limited_all", None))
    entry = BY_ID["P1"]
    out = htl.phrase_or_fallback(entry["packet"], entry["trigger"], entry["fallback_text"],
                                 cfg=ARMED_CFG)
    assert out["mode"] == "fallback_provider"
    assert out["text"] == entry["fallback_text"]
    assert out["provider"] is None
    stats = htl.fallback_stats()
    assert stats["calls"] == 1 and stats["fallback_provider"] == 1
    assert stats["fallback_rate"] == 1.0


def test_make_call_raising_never_escapes(monkeypatch):
    _arm(monkeypatch)

    def _boom(*_a, **_k):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(llm_auth, "make_call", _boom)
    entry = BY_ID["P1"]
    out = htl.phrase_or_fallback(entry["packet"], entry["trigger"], entry["fallback_text"],
                                 cfg=ARMED_CFG)
    assert out["mode"] == "fallback_provider"
    assert out["text"] == entry["fallback_text"]


def test_hallucinated_number_falls_back_with_violations(monkeypatch):
    _arm(monkeypatch)
    bad = "$SNDK falls -17% on the day and is now -56% from its record high."
    monkeypatch.setattr(llm_auth, "make_call", lambda *a, **k: (bad, None, "oauth"))
    entry = BY_ID["P1"]
    out = htl.phrase_or_fallback(entry["packet"], entry["trigger"], entry["fallback_text"],
                                 cfg=ARMED_CFG)
    assert out["mode"] == "fallback_validation"
    assert out["text"] == entry["fallback_text"]
    assert any("-56%" in v for v in out["violations"]), out["violations"]
    assert htl.fallback_stats()["fallback_validation"] == 1


def test_clean_model_copy_ships(monkeypatch):
    _arm(monkeypatch)
    entry = BY_ID["P1"]
    monkeypatch.setattr(llm_auth, "make_call",
                        lambda *a, **k: (entry["good_phrasing"], None, "oauth"))
    out = htl.phrase_or_fallback(entry["packet"], entry["trigger"], entry["fallback_text"],
                                 cfg=ARMED_CFG)
    assert out["mode"] == "llm"
    assert out["text"] == entry["good_phrasing"]
    assert out["provider"] == "oauth"
    assert out["violations"] == []
    assert isinstance(out["latency_ms"], int)
    assert htl.fallback_stats()["llm"] == 1


def test_model_copy_is_unwrapped_before_the_gates(monkeypatch):
    # Law 9 says "no quotes around it"; models add them anyway.
    _arm(monkeypatch)
    entry = BY_ID["P3"]
    monkeypatch.setattr(llm_auth, "make_call",
                        lambda *a, **k: (f'"{entry["good_phrasing"]}"', None, "deepseek"))
    out = htl.phrase_or_fallback(entry["packet"], entry["trigger"], entry["fallback_text"],
                                 cfg=ARMED_CFG)
    assert out["mode"] == "llm"
    assert out["text"] == entry["good_phrasing"]


def test_per_run_call_cap_falls_back(monkeypatch):
    _arm(monkeypatch)
    entry = BY_ID["P1"]
    monkeypatch.setattr(llm_auth, "make_call",
                        lambda *a, **k: (entry["good_phrasing"], None, "oauth"))
    cfg = {"enabled": True, "max_calls_per_run": 1}
    first = htl.phrase_or_fallback(entry["packet"], entry["trigger"],
                                   entry["fallback_text"], cfg=cfg)
    second = htl.phrase_or_fallback(entry["packet"], entry["trigger"],
                                    entry["fallback_text"], cfg=cfg)
    assert first["mode"] == "llm"
    assert second["mode"] == "fallback_provider"
    assert second["text"] == entry["fallback_text"]


# ─────────────────────────────────────────────────────────────────────────────
# 13. Disarmed
# ─────────────────────────────────────────────────────────────────────────────

def test_disarmed_never_touches_a_provider(monkeypatch):
    monkeypatch.delenv("MARKETING_LLM_ENABLED", raising=False)
    seen: list[str] = []
    monkeypatch.setattr(llm_auth, "build_providers",
                        lambda *a, **k: seen.append("build") or [_FAKE_PROVIDER])
    monkeypatch.setattr(llm_auth, "make_call",
                        lambda *a, **k: seen.append("call") or ("x", None, "oauth"))
    htl.reset_stats()
    entry = BY_ID["P1"]
    out = htl.phrase_or_fallback(entry["packet"], entry["trigger"], entry["fallback_text"],
                                 cfg=ARMED_CFG)
    assert out["mode"] == "off"
    assert out["text"] == entry["fallback_text"]
    assert seen == [], f"disarmed lane touched the waterfall: {seen}"
    assert htl.fallback_stats()["off"] == 1


def test_config_disabled_is_also_off(monkeypatch):
    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    seen: list[str] = []
    monkeypatch.setattr(llm_auth, "build_providers",
                        lambda *a, **k: seen.append("build") or [_FAKE_PROVIDER])
    htl.reset_stats()
    entry = BY_ID["P1"]
    out = htl.phrase_or_fallback(entry["packet"], entry["trigger"], entry["fallback_text"],
                                 cfg={"enabled": False})
    assert out["mode"] == "off" and seen == []


# ─────────────────────────────────────────────────────────────────────────────
# 14. Armed but mute — the annotation must START its line
# ─────────────────────────────────────────────────────────────────────────────

def test_armed_but_mute_emits_a_line_start_annotation(monkeypatch, capsys):
    # capsys, NOT caplog: the whole point is that the annotation is a bare print
    # at column 0. A logger would prefix it and GitHub would silently drop it
    # (tests/test_gh_annotation_line_start.py guards the same law repo-wide).
    _arm(monkeypatch, providers=[])
    entry = BY_ID["P1"]
    out = htl.phrase_or_fallback(entry["packet"], entry["trigger"], entry["fallback_text"],
                                 cfg=ARMED_CFG)
    assert out["mode"] == "fallback_provider"
    assert out["text"] == entry["fallback_text"]
    lines = capsys.readouterr().out.splitlines()
    hits = [ln for ln in lines if "hot_tape_llm_mute" in ln]
    assert hits, f"no mute annotation printed; stdout was {lines}"
    assert hits[0].startswith("::"), f"annotation is not at line start: {hits[0]!r}"
    assert hits[0].startswith("::warning title=hot_tape_llm_mute::"), hits[0]


# ─────────────────────────────────────────────────────────────────────────────
# 15. Import closure
# ─────────────────────────────────────────────────────────────────────────────

def test_module_imports_with_no_heavy_dependency():
    # The marketing-engine CI lane installs pytest + pyyaml + jinja2 ONLY, so
    # this file being collected at all in that lane is the live proof. The scans
    # below make the law mechanical rather than environmental.
    import engine.marketing.hot_tape_llm as _m  # noqa: F401
    src = MODULE_PATH.read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import anthropic|from anthropic)", src, re.MULTILINE)


def test_no_lazy_only_dependency_is_imported_at_module_level():
    forbidden = {
        "anthropic", "yaml", "pandas", "numpy", "httpx",
        "engine.llm_auth", "lib.config",
        "engine.marketing.copywriter", "engine.marketing.social_publisher",
        "engine.marketing.wire_voice",
    }
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    offenders = []
    for node in tree.body:  # module level ONLY — nested imports are the contract
        if isinstance(node, ast.Import):
            offenders += [a.name for a in node.names if a.name.split(".")[0] in forbidden
                          or a.name in forbidden]
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod in forbidden or mod.split(".")[0] in forbidden:
                offenders.append(mod)
    assert not offenders, (
        "hot_tape_llm imports these at module level; the marketing-engine lane has "
        f"no such packages and would go red at collection: {offenders}")


def test_module_never_imports_the_phase_1_radar():
    # Dependency inversion: the radar calls US and passes its template text in.
    src = MODULE_PATH.read_text(encoding="utf-8")
    assert "import hot_tape\n" not in src
    assert "from engine.marketing.hot_tape import" not in src
    assert "from engine.marketing import hot_tape\n" not in src


# ─────────────────────────────────────────────────────────────────────────────
# 16. Prompt pins
# ─────────────────────────────────────────────────────────────────────────────

def test_system_prompt_carries_the_house_exemplars():
    for exemplar in htl.HOUSE_EXEMPLARS:
        assert exemplar in htl.SYSTEM_PROMPT
    assert len(htl.HOUSE_EXEMPLARS) == 3


def test_system_prompt_carries_the_anti_example_and_its_lesson():
    assert htl.ANTI_EXEMPLAR in htl.SYSTEM_PROMPT
    assert "seems like" in htl.SYSTEM_PROMPT
    assert "95 views" in htl.SYSTEM_PROMPT


def test_system_prompt_states_the_numbers_law_and_the_char_budget():
    assert "ALLOWED NUMBERS" in htl.SYSTEM_PROMPT
    assert "never originate a number" in htl.SYSTEM_PROMPT
    assert "270 characters maximum" in htl.SYSTEM_PROMPT
    assert "No hashtags" in htl.SYSTEM_PROMPT


def test_user_message_carries_the_packet_and_the_allowed_numbers():
    entry = BY_ID["P1"]
    msg = htl.build_user_message(entry["packet"], entry["trigger"])
    assert "TRIGGER: mover_drop" in msg
    assert "ALLOWED NUMBERS" in msg
    assert "$SNDK" in msg
    for wanted in ("-17", "$200 billion", "June 22"):
        assert wanted in msg, wanted


def test_nothing_the_module_emits_claims_the_banned_word():
    # CLAUDE.md house law: "validated" in user-facing text is CI-enforced
    # (scripts/check_validated_claims.py). The prompt is copy the model reads
    # and echoes, so it counts.
    for blob in (htl.SYSTEM_PROMPT, *htl.HOUSE_EXEMPLARS, htl.ANTI_EXEMPLAR):
        assert "validated" not in blob.lower()


# ─────────────────────────────────────────────────────────────────────────────
# 17. config.yml wiring
# ─────────────────────────────────────────────────────────────────────────────

def test_config_yml_ships_the_hot_tape_block():
    cfg = yaml.safe_load((ROOT / "config.yml").read_text(encoding="utf-8")) or {}
    assert cfg.get("llm_models", {}).get("hot_tape_wire"), "llm_models.hot_tape_wire missing"
    llm = (cfg.get("hot_tape") or {}).get("llm") or {}
    assert llm.get("enabled") is True
    assert llm.get("client_max_retries") == 0, "SDK retries defeat the failover walk"
    assert float(llm.get("client_timeout_s")) <= 10.0
    assert int(llm.get("max_calls_per_run")) >= 1


def test_shipped_config_arms_the_lane_only_with_the_env_flag(monkeypatch):
    # config.yml says enabled: true. Without MARKETING_LLM_ENABLED the lane is
    # still off — two keys, exactly like the nightly copywriter.
    monkeypatch.delenv("MARKETING_LLM_ENABLED", raising=False)
    htl.reset_stats()
    entry = BY_ID["P1"]
    out = htl.phrase_or_fallback(entry["packet"], entry["trigger"], entry["fallback_text"])
    assert out["mode"] == "off"


# ─────────────────────────────────────────────────────────────────────────────
# Counters
# ─────────────────────────────────────────────────────────────────────────────

def test_fallback_stats_shape_and_reset():
    htl.reset_stats()
    stats = htl.fallback_stats()
    for key in ("calls", "llm", "fallback_validation", "fallback_provider", "off"):
        assert stats[key] == 0
    assert stats["fallback_rate"] == 0.0
    stats["calls"] = 99  # the returned dict is a copy
    assert htl.fallback_stats()["calls"] == 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))


# ─────────────────────────────────────────────────────────────────────────────
# 18. CHATGPT-FIRST ROUTING (operator directive 2026-07-29)
#
# "The marketing content LLM lanes must default to the attached ChatGPT/Codex
# account (Claude subscription tokens are being reserved for website-building
# sessions), with Claude as fallback drawn through the key_pool OAuth load
# balancer."
#
# Ruled tier for the wire desk: gpt-5.6-terra at LOW effort. Terra because the
# wire register is not persona writing; low because this lane runs on a 5-second
# per-provider budget and a reasoning pass it cannot wait for is spend with no
# product. The full ruling table lives in tests/test_marketing_copy_v2.py.
# ─────────────────────────────────────────────────────────────────────────────

def _capture_provider_cfg(monkeypatch) -> list[dict]:
    """Recorder in place of build_providers. Returning [] mutes the lane, which
    is the shortest path that still proves what the lane ASKED for."""
    seen: list[dict] = []

    def _rec(cfg, **kwargs):  # noqa: ANN001
        seen.append(dict(cfg))
        return []

    monkeypatch.setattr(llm_auth, "build_providers", _rec)
    return seen


def test_the_wire_desk_asks_for_codex_first_on_terra_at_low_effort(monkeypatch, capsys):
    seen = _capture_provider_cfg(monkeypatch)
    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    htl.reset_stats()
    entry = BY_ID["P1"]
    out = htl.phrase_or_fallback(entry["packet"], entry["trigger"],
                                 entry["fallback_text"], cfg=ARMED_CFG)
    capsys.readouterr()
    assert out["mode"] == "fallback_provider"

    assert seen, "the wire desk never reached the provider waterfall"
    cfg = seen[0]
    assert cfg["provider_order"] == ["codex", "oauth", "anthropic", "deepseek"]
    assert cfg["codex_source_model"] == "gpt-5.6-terra"
    assert cfg["codex_reasoning_effort"] == "low"
    assert cfg["oauth_pool_lane"] == "hot-tape-wire"
    assert cfg["usage_lane"] == "hot-tape-wire"


def test_the_shipped_hot_tape_block_carries_the_ruling():
    cfg = yaml.safe_load((ROOT / "config.yml").read_text(encoding="utf-8")) or {}
    block = (cfg.get("hot_tape") or {}).get("llm") or {}
    assert block.get("provider_order") == ["codex", "oauth", "anthropic", "deepseek"]
    assert block.get("codex_source_model") == "gpt-5.6-terra"
    assert block.get("codex_reasoning_effort") == "low"
    assert block.get("oauth_pool_lane") == "hot-tape-wire"
    # Luna never touches a user-facing word.
    assert "luna" not in str(block).lower()


def test_the_source_default_is_codex_first_too():
    """The config file is the operator surface; this literal is what runs when a
    caller hands the module a bare cfg. They must not disagree."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    assert '["codex", "oauth", "anthropic", "deepseek"]' in src
    assert '"gpt-5.6-terra"' in src
    assert '"gpt-5.6-luna"' not in src


# ─────────────────────────────────────────────────────────────────────────────
# 19. THE PROMPT STATES EVERY LAW THE VALIDATOR ENFORCES
#
# THE DEFECT (measured 2026-07-31: ~90% of armed attempts fell back).
# SYSTEM_PROMPT stated 9 laws; `validate_wire_copy` also enforced the whole
# `copywriter.banned_language()` house list, the AI-tell markers from
# config/press.yml and 24 call-violation words the prompt never mentioned — with
# no repair turn, so one unmentioned word cost the entire post. These tests are
# INTROSPECTIVE on purpose: they read the validator's own lists, so a term added
# upstream tomorrow fails here unless it also reaches the model.
# ─────────────────────────────────────────────────────────────────────────────

def test_every_banned_term_the_validator_enforces_is_stated_in_the_prompt():
    from engine.marketing.copywriter import banned_language

    prompt = htl.build_system_prompt()
    terms = htl._banned_language_terms()
    # A rename upstream would empty this list and make the loop vacuous.
    assert len(terms) >= 40, f"the house banned list read as {len(terms)} terms"
    for term in terms:
        # Each term really IS a rejection (the list is the validator's, not a
        # decorative copy)…
        assert banned_language(f"The tape shows {term} today."), term
        # …and the model is told about it.
        assert term in prompt, f"banned term never stated to the model: {term!r}"


def test_every_call_and_hedge_word_the_validator_enforces_is_in_the_prompt():
    prompt = htl.build_system_prompt()
    calls = htl._call_language_terms()
    hedges = htl._hedge_language_terms()
    assert len(calls) >= 24, len(calls)
    assert hedges, hedges
    for term in calls:
        assert htl.call_violations(f"We {term} the move."), term
        assert term in prompt, f"call word never stated to the model: {term!r}"
    for term in hedges:
        assert htl.hedge_violations(f"It {term} lower."), term
        assert term in prompt, f"hedge word never stated to the model: {term!r}"


def test_every_ai_tell_the_validator_enforces_is_in_the_prompt():
    prompt = htl.build_system_prompt()
    phrases = (yaml.safe_load((ROOT / "config" / "press.yml").read_text(encoding="utf-8"))
               .get("validators", {}).get("ai_tell_phrases") or [])
    assert phrases, "config/press.yml must supply the AI-tell lexicon"
    for phrase in phrases:
        assert str(phrase) in prompt, f"AI tell never stated to the model: {phrase!r}"
    # The two PATTERN rules have no phrase list, so they are stated in words.
    assert "Moreover," in prompt
    assert "not only" in prompt


def test_the_generated_prompt_still_carries_the_hand_written_half():
    # The generated block is ADDITIVE — the exemplars and the numbers law are
    # what make the register, and appending laws must not displace them.
    prompt = htl.build_system_prompt()
    assert prompt.startswith(htl.SYSTEM_PROMPT.rstrip()[:80])
    for exemplar in htl.HOUSE_EXEMPLARS:
        assert exemplar in prompt
    assert "ALLOWED NUMBERS" in prompt
    assert "270 characters maximum" in prompt


def test_the_prompt_the_provider_receives_is_the_generated_one(monkeypatch):
    # The generated prompt is worthless if the call still ships the constant.
    _arm(monkeypatch)
    entry = BY_ID["P1"]
    seen = _record_calls(monkeypatch, [entry["good_phrasing"]])
    out = htl.phrase_or_fallback(entry["packet"], entry["trigger"],
                                 entry["fallback_text"], cfg=ARMED_CFG)
    assert out["mode"] == "llm"
    assert len(seen) == 1
    system = seen[0]["system"]
    assert system != htl.SYSTEM_PROMPT
    assert "HOUSE BANNED LANGUAGE" in system
    assert "diamond hands" in system      # a term only the generated half states


# ─────────────────────────────────────────────────────────────────────────────
# 20. ONE REPAIR TURN before the template wins
# ─────────────────────────────────────────────────────────────────────────────

class _FakeResp:
    def __init__(self, text: str):
        self.content = [type("B", (), {"type": "text", "text": text})()]
        self.stop_reason = "end_turn"


class _FakeClient:
    """Records every messages.create kwarg and answers with scripted texts."""

    def __init__(self, texts, log):
        self._texts = list(texts)
        self._log = log
        self.messages = self

    def create(self, **kwargs):
        self._log.append(kwargs)
        return _FakeResp(self._texts.pop(0) if self._texts else "")


def _record_calls(monkeypatch, texts):
    """Arm make_call so it DRIVES the module's own _do_call. Returns the log."""
    log: list[dict] = []
    client = _FakeClient(texts, log)

    def _make_call(providers, do_call, context=None):
        text, reason, _resp = do_call(client, "fake-model")
        return text, reason, "oauth"

    monkeypatch.setattr(llm_auth, "make_call", _make_call)
    return log


def test_a_violating_draft_is_repaired_instead_of_falling_back(monkeypatch):
    _arm(monkeypatch)
    entry = BY_ID["P1"]
    # Draft 1 hedges ("seems like") — the corpus's 95-view shape. Draft 2 is the
    # house exemplar, which clears every gate.
    draft = "$SNDK seems like it will keep falling."
    seen = _record_calls(monkeypatch, [draft, entry["good_phrasing"]])

    out = htl.phrase_or_fallback(entry["packet"], entry["trigger"],
                                 entry["fallback_text"], cfg=ARMED_CFG)

    assert out["mode"] == "llm_repair", out
    assert out["text"] == entry["good_phrasing"]
    assert out["text"] != entry["fallback_text"], "the template must NOT have won"
    assert len(seen) == 2, "exactly one repair turn"
    # The repair turn names the failures and carries the rejected draft back.
    repair_msgs = seen[1]["messages"]
    assert [m["role"] for m in repair_msgs] == ["user", "assistant", "user"]
    assert repair_msgs[1]["content"] == draft
    assert "REJECTED" in repair_msgs[2]["content"]
    assert "seems" in repair_msgs[2]["content"]
    # A repaired post is model copy on the timeline, not a fallback.
    stats = htl.fallback_stats()
    assert stats["llm_repair"] == 1 and stats["fallback_validation"] == 0
    assert stats["fallback_rate"] == 0.0


def test_a_repair_that_still_violates_falls_back_and_reports_both_lists(monkeypatch):
    _arm(monkeypatch)
    entry = BY_ID["P1"]
    seen = _record_calls(monkeypatch, [
        "$SNDK seems like it will keep falling.",
        "$SNDK might fall further from here.",
    ])
    out = htl.phrase_or_fallback(entry["packet"], entry["trigger"],
                                 entry["fallback_text"], cfg=ARMED_CFG)
    assert out["mode"] == "fallback_validation"
    assert out["text"] == entry["fallback_text"]
    assert len(seen) == 2, "still exactly ONE repair — never a loop"
    assert any(v.startswith("repair:") for v in out["violations"]), out["violations"]
    assert any("seems" in v and not v.startswith("repair:") for v in out["violations"])


def test_the_repair_turn_respects_the_per_run_call_cap(monkeypatch):
    _arm(monkeypatch)
    entry = BY_ID["P1"]
    seen = _record_calls(monkeypatch, ["$SNDK seems like it will keep falling."])
    out = htl.phrase_or_fallback(entry["packet"], entry["trigger"],
                                 entry["fallback_text"],
                                 cfg={"enabled": True, "max_calls_per_run": 1})
    assert out["mode"] == "fallback_validation"
    assert len(seen) == 1, "the cap forbids the second call"


def test_a_raising_repair_turn_still_posts_the_template(monkeypatch):
    _arm(monkeypatch)
    entry = BY_ID["P1"]
    calls = {"n": 0}

    def _make_call(providers, do_call, context=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return "$SNDK seems like it will keep falling.", None, "oauth"
        raise RuntimeError("provider exploded on the repair")

    monkeypatch.setattr(llm_auth, "make_call", _make_call)
    out = htl.phrase_or_fallback(entry["packet"], entry["trigger"],
                                 entry["fallback_text"], cfg=ARMED_CFG)
    assert out["mode"] == "fallback_validation"
    assert out["text"] == entry["fallback_text"]


# ─────────────────────────────────────────────────────────────────────────────
# 21. The AI-tell gate is HARD, and says so out loud when it cannot run
#
# It was documented as a soft polish screen while its result was appended to the
# hard reject list — hard in effect, soft in sourcing. An unreadable
# config/press.yml silently loosened a live gate and nothing said so.
# ─────────────────────────────────────────────────────────────────────────────

def test_an_ai_tell_still_rejects_the_copy():
    entry = BY_ID["P1"]
    tell = entry["good_phrasing"] + " It is a testament to the selloff."
    violations = htl.validate_wire_copy(tell, entry["packet"])
    assert any("ai_tell" in v for v in violations), violations


def test_an_unreadable_ai_tell_lexicon_fails_LOUD(monkeypatch, capsys):
    from engine.marketing import wire_voice

    def _boom(*a, **kw):
        raise FileNotFoundError("config/press.yml")

    monkeypatch.setattr(wire_voice, "ai_tell_lexicon", _boom)
    entry = BY_ID["P1"]
    # The post still ships (a style screen may not stop a fired event) …
    assert htl.validate_wire_copy(entry["good_phrasing"], entry["packet"]) == []
    # … but the disarmed gate is announced at the START of the line.
    lines = capsys.readouterr().out.splitlines()
    hits = [ln for ln in lines if "hot_tape_ai_tell_lexicon" in ln]
    assert hits, f"no annotation printed; stdout was {lines}"
    assert hits[0].startswith("::warning title=hot_tape_ai_tell_lexicon::"), hits[0]
