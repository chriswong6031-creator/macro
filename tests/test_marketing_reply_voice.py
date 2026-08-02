"""tests/test_marketing_reply_voice.py — E4 reply-craft acceptance suite.

Program: Content Studio LLM-first §10 E4 ("reply-craft intelligence").
Doctrine: research/MARKETING_REPLY_DOCTRINE_BY_FABLE.md, distilled from
research/marketing_dockets/reply_corpus_2026_07_29/ (180 top replies under 12
large finance posts, captured 2026-07-29).

Fixture-driven; ZERO live network, ZERO live LLM. Every provider-path test
monkeypatches engine.llm_auth.build_providers / make_call, and the arming env
flag is set through monkeypatch so it can never leak into another suite. Import
closure is stdlib + pyyaml — the thin marketing-engine CI lane has NO anthropic
package, so a top-level ``import anthropic`` in engine/marketing/reply_voice.py
would turn this file red at COLLECTION. Test 9 pins that mechanically.

The load-bearing tests are the negative ones. It is easy to write a phrasing
pass that ships model copy; the claims worth pinning are that a hallucinated
number CANNOT ship, that a failed gate costs phrasing and never the reply, that
a disarmed lane touches no provider at all, and that adding a critic did not
quietly weaken the queue's full-roster gate.

Covers:
  1. The doctrine file exists and still carries the taxonomy (drift guard).
  2. Prompt pins: ten exemplars verbatim with likes, the anti-exemplars, laws.
  3. The gates: numbers, advice/calls, length, links/hashtags/mentions/dashes,
     smuggled cashtags, the per-persona dial.
  4. The provider path: clean copy ships, dirty copy falls back, failures and
     raises fall back, the per-run cap falls back.
  5. Arming: disarmed touches nothing; armed-but-mute announces itself.
  6. The drafter hook: off by default, voiced when armed, alternates untouched.
  7. The reply_value critic, one test per anti-pattern class + its exemptions.
  8. Roster completeness: the queue accepts a full stamp and refuses one that
     is missing the new critic.
  9. Import closure + dependency direction.
 10. config/marketing.yml ships the voice block.
"""
from __future__ import annotations

import ast
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import llm_auth  # noqa: E402
from engine.marketing import reply_critics as rc  # noqa: E402
from engine.marketing import reply_drafter as rdr  # noqa: E402
from engine.marketing import reply_queue as rq  # noqa: E402
from engine.marketing import reply_voice as rv  # noqa: E402

MODULE_PATH = ROOT / "engine" / "marketing" / "reply_voice.py"
DOCTRINE = ROOT / "research" / "MARKETING_REPLY_DOCTRINE_BY_FABLE.md"
CORPUS = ROOT / "research" / "marketing_dockets" / "reply_corpus_2026_07_29"

NOW = datetime(2026, 7, 29, 15, 0, tzinfo=timezone.utc)
PARENT = "Hyperscaler capex keeps climbing but credit spreads are widening."
GIFT = "IG spreads widened 12.5% this week while capex guidance held."
DRAFT = (
    "IG spreads widened 12.5% this week while capex guidance held.\n\n"
    "The price move is the reaction. Credit is the test."
)
#: A model line that clears every gate for kelly: keeps the fact, one thought,
#: no advice, no invented figure, inside the char cap.
#: WARMED 2026-08-01 (the warmth build): was "Credit is the test, not the tape.
#: ..." — fifteen content units with no human-register marker, which the
#: `warmth_register` critic now rejects on an employee desk (W1) and which
#: `validate_reply_copy` therefore refuses. "the thing that" is the Class B
#: marker; the fact, the shape and the length are unchanged.
VOICED = ("Credit is the thing that settles this, not the tape. "
          "IG spreads widened 12.5% while capex guidance held.")
WHITELIST = ["12.5%"]

FACTS = {
    "facts": [{"id": "f1", "text": GIFT, "salience": 1.0}],
    "numbers_whitelist": WHITELIST,
}
TARGET = {"subject": "capex", "mechanism": "credit",
          "text": PARENT, "author": "somequant"}

#: The DETERMINISTIC draft the drafter now produces for this (account, family,
#: parent) — the plain DRAFT above with Kelly's warmth opener fused onto it.
#:
#: COMPUTED, NOT TRANSCRIBED, and that is the point of the constant: these
#: tests assert "the deterministic draft is what ships when the model path does
#: not", and pinning the pre-warmth string turned that into "the deterministic
#: draft is the one the warmth build replaced". Composing it here keeps the
#: assertion about the FALLBACK CONTRACT and lets the register evolve; the
#: warmth register itself is pinned by tests/test_marketing_reply_warmth.py.
def _warmed(family: str = "missing_variable") -> str:
    move = rdr._select_warmth(
        "kelly", family=family, parent_shape=rdr.classify_parent(TARGET),
        root=None, recent_warmth=None, has_detail=True,
        parent_author=str(TARGET["author"]),
    )
    return rdr.compose(family, GIFT, {
        "subject": TARGET["subject"], "mechanism": TARGET["mechanism"],
        "account": "kelly", "detail": rdr.extract_detail(PARENT),
    }, warmth=move)


WARMED_DRAFT = _warmed()

#: The voice cfg block, injected directly so no test depends on the shipped
#: `enabled:` value in config/marketing.yml.
ARMED_CFG = {"reply_desk": {"voice": {"enabled": True, "max_calls_per_run": 40,
                                      "model_key": "marketing_copy"}}}

_FAKE_PROVIDER = {
    "name": "oauth",
    "env_var": "CLAUDE_CODE_OAUTH_TOKEN",
    "cred": "not-a-real-token",
    "client": object(),
    "model": "claude-sonnet-4-6",
}


@pytest.fixture(scope="module")
def cfg() -> dict:
    return yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))


def _arm(monkeypatch, providers=(_FAKE_PROVIDER,)) -> None:
    """Arm the lane and hand it a fake provider list (never a real credential)."""
    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    monkeypatch.setattr(llm_auth, "build_providers", lambda *a, **k: list(providers))
    rv.reset_stats()


def _returns(text: str):
    return lambda *a, **k: (text, None, "oauth")


def _gates(text: str, **over) -> list[str]:
    kwargs = {
        "draft": DRAFT, "numbers_whitelist": WHITELIST, "parent_text": PARENT,
        "account": "kelly", "family": "missing_variable",
    }
    kwargs.update(over)
    return rv.validate_reply_copy(text, **kwargs)


# ===========================================================================
# 1. The doctrine file is the contract — a drift guard, not a spell-check
# ===========================================================================
class TestDoctrineFile:
    def test_the_doctrine_ships_with_the_code(self):
        assert DOCTRINE.exists(), (
            "reply_voice's system prompt is a distillation of "
            f"{DOCTRINE.name}; shipping the prompt without the doctrine leaves "
            "the operator and the model reading different laws")

    @pytest.mark.parametrize("heading", [
        # The five-value taxonomy, enumerated BY HAND: parametrising over a
        # constant in the module under test would prove only that the module
        # agrees with itself.
        "### Data drop",
        "### Sharp read",
        "### Dry wit",
        "### Useful reframe",
        "### Missing-number correction",
    ])
    def test_the_value_taxonomy_is_still_there(self, heading):
        assert heading in DOCTRINE.read_text(encoding="utf-8")

    def test_the_length_law_carries_its_evidence(self):
        text = DOCTRINE.read_text(encoding="utf-8")
        assert "median 11" in text and "under 16 words" in text

    def test_the_confound_caveats_survive(self):
        """The honest half. A doctrine that drops its caveats becomes folklore."""
        text = DOCTRINE.read_text(encoding="utf-8")
        assert "necessary, not sufficient" in text
        assert "Blue-verified" in text          # the platform-visibility artifact
        assert "Nothing here is a measurement" in text   # n=180, one news cycle

    def test_the_brand_exclusion_is_explicit(self):
        text = DOCTRINE.read_text(encoding="utf-8")
        assert "moral-outrage pattern" in text
        assert "2,186" in text, "the excluded top reply keeps its like count as evidence"

    def test_the_source_corpus_is_committed(self):
        assert (CORPUS / "playbook.md").exists()
        assert (CORPUS / "replies.jsonl").exists()


# ===========================================================================
# 2. Prompt pins — the exemplars are the register
# ===========================================================================
class TestPromptPins:
    def test_ten_exemplars_ship_verbatim_with_their_likes(self):
        assert len(rv.PLAYBOOK_EXEMPLARS) == 10
        for likes, _pattern, text in rv.PLAYBOOK_EXEMPLARS:
            assert text in rv.SYSTEM_PROMPT
            assert f"[{likes} likes" in rv.SYSTEM_PROMPT

    def test_every_exemplar_traces_to_the_harvested_corpus(self):
        """Not invented, not paraphrased: each line is in replies.jsonl."""
        def _flat(s: str) -> str:
            # Curly quotes, JSON escapes and whitespace all differ between the
            # captured rows and a Python literal; none of them is the claim.
            for src, dst in (("’", ""), ("'", ""), ("\\u2019", ""),
                             ("\\n", " "), ("\\'", "")):
                s = s.replace(src, dst)
            return "".join(s.split())

        corpus = _flat((CORPUS / "replies.jsonl").read_text(encoding="utf-8"))
        for _likes, _pattern, text in rv.PLAYBOOK_EXEMPLARS:
            probe = _flat(text.split(".")[0][:48])
            assert probe in corpus, probe

    def test_the_anti_exemplars_ship_with_the_reason_they_failed(self):
        assert len(rv.ANTI_EXEMPLARS) >= 5
        for why, text in rv.ANTI_EXEMPLARS:
            assert text in rv.SYSTEM_PROMPT and why in rv.SYSTEM_PROMPT

    def test_the_hard_laws_are_in_the_prompt(self):
        prompt = rv.SYSTEM_PROMPT
        assert "ALLOWED NUMBERS" in prompt
        assert f"{rv.MAX_REPLY_CHARS} characters maximum" in prompt
        assert "No advice and no calls" in prompt
        assert "Never a question aimed at the poster" in prompt
        assert "Never moral outrage" in prompt

    def test_the_prompt_admits_the_confound(self):
        """The model is told a good line is necessary, not sufficient."""
        assert "necessary, not sufficient" in rv.SYSTEM_PROMPT

    def test_the_user_turn_carries_the_draft_the_parent_and_the_persona(self, cfg):
        msg = rv.build_user_message(
            draft=DRAFT, family="missing_variable", account="kelly",
            parent_text=PARENT, parent_author="somequant",
            numbers_whitelist=WHITELIST, cfg=cfg,
            family_spec=rdr.FAMILIES["missing_variable"],
        )
        assert PARENT in msg and DRAFT in msg
        assert "@somequant" in msg
        assert "12.5%" in msg
        assert "mechanism detective" in msg          # kelly's beat, from config
        assert rdr.FAMILIES["missing_variable"]["move"] in msg

    def test_the_long_form_exemption_is_read_from_the_critic(self):
        """One definition of "may run long", not two."""
        short = rv.build_user_message(draft=DRAFT, family="compression",
                                      account="kelly", parent_text=PARENT)
        long_ok = rv.build_user_message(draft=DRAFT, family="micro_framework",
                                        account="kelly", parent_text=PARENT)
        assert "characters maximum" in short
        assert "may run long" in long_ok
        assert "micro_framework" in rc.LONG_FORM_FAMILIES

    def test_allowed_numbers_covers_the_draft_and_the_whitelist(self):
        allowed = rv.allowed_numbers("Spreads widened 12.5% and issuance hit 3,500.", ["8.4%"])
        assert "8.4%" in allowed and "12.5%" in allowed and "3,500" in allowed


# ===========================================================================
# 3. The gates
# ===========================================================================
class TestGates:
    def test_clean_copy_clears_every_gate(self):
        assert _gates(VOICED) == []

    def test_an_invented_number_is_rejected(self):
        """THE gate. The engine computes, the model phrases, never the reverse."""
        hits = _gates("IG spreads widened 13.5% while capex guidance held.")
        assert any("13.5%" in h for h in hits)
        # Both the imported wire tokenizer AND the reply desk's own critic fire,
        # because the second is what would have judged this text downstream.
        assert any(h.startswith("fact_discipline:") for h in hits)

    def test_a_number_from_the_parent_post_is_not_admissible(self):
        """The parent's figures are numbers OUR engine did not compute."""
        hits = _gates("Spreads at 4.75 are the tell here.",
                      parent_text="Spreads at 4.75 and climbing.")
        assert any("4.75" in h for h in hits)

    def test_call_language_is_rejected(self):
        assert any("call_language" in h for h in _gates("Credit is the test. I'd add here."))

    def test_house_banned_vocabulary_is_rejected(self):
        assert _gates("The regime shifted while credit widened 12.5%.") != []

    def test_over_the_char_cap_is_rejected(self):
        long_line = "Credit is the test and capex is the story. " * 8
        assert any("over 240 chars" in h for h in _gates(long_line))

    @pytest.mark.parametrize("bad,tell", [
        ("Credit is the test. More here https://example.com/x", "link"),
        ("Credit is the test #capex", "hashtag"),
        ("Credit is the test, @somequant", "@-mention"),
        ("Credit is the test — capex is the story.", "dash tell"),
    ])
    def test_shape_tells_are_rejected(self, bad, tell):
        assert any(tell in h for h in _gates(bad)), f"{tell} not caught in {bad!r}"

    def test_a_smuggled_cashtag_is_rejected(self):
        hits = _gates("Credit is the test. $NVDA says otherwise.")
        assert any("unknown_cashtag" in h for h in hits)

    def test_the_parents_own_cashtag_is_legitimate(self):
        """It is the thread we are standing in, not a smuggled comparison."""
        hits = _gates("Credit is the test for $NVDA here.",
                      parent_text="$NVDA capex keeps climbing.")
        assert not any("unknown_cashtag" in h for h in hits)

    def test_the_per_persona_dial_is_enforced(self):
        """Sophia's signature emoji on Kelly's desk is a borrowed quirk."""
        assert _gates("breadth narrowed again \U0001F58B️") != []

    def test_an_empty_model_reply_is_a_violation(self):
        assert _gates("   ") == ["empty model reply"]

    def test_the_doctrine_bar_runs_inside_the_gates(self):
        """A voiced OP-directed question falls back rather than killing the item."""
        hits = _gates("What do you think of credit here?")
        assert any(h.startswith("reply_value:") for h in hits)


# ===========================================================================
# 4-5. The provider path and arming
# ===========================================================================
class TestProviderPath:
    def test_clean_model_copy_ships(self, monkeypatch):
        _arm(monkeypatch)
        monkeypatch.setattr(llm_auth, "make_call", _returns(VOICED))
        out = rv.voice_or_fallback(DRAFT, family="missing_variable", account="kelly",
                                   parent_text=PARENT, numbers_whitelist=WHITELIST,
                                   cfg=ARMED_CFG)
        assert out["mode"] == "llm" and out["text"] == VOICED
        assert out["provider"] == "oauth" and out["violations"] == []
        assert rv.fallback_stats()["llm"] == 1

    def test_a_hallucinated_number_falls_back_with_violations(self, monkeypatch):
        _arm(monkeypatch)
        monkeypatch.setattr(llm_auth, "make_call",
                            _returns("Spreads widened 13.5% this week."))
        out = rv.voice_or_fallback(DRAFT, family="missing_variable", account="kelly",
                                   parent_text=PARENT, numbers_whitelist=WHITELIST,
                                   cfg=ARMED_CFG)
        assert out["mode"] == "fallback_validation"
        assert out["text"] == DRAFT, "the deterministic draft is what ships"
        assert any("13.5%" in v for v in out["violations"])
        assert rv.fallback_stats()["fallback_rate"] == 1.0

    def test_advice_language_falls_back(self, monkeypatch):
        _arm(monkeypatch)
        monkeypatch.setattr(llm_auth, "make_call",
                            _returns("Stay informed and manage your risk here."))
        out = rv.voice_or_fallback(DRAFT, family="missing_variable", account="kelly",
                                   parent_text=PARENT, numbers_whitelist=WHITELIST,
                                   cfg=ARMED_CFG)
        assert out["mode"] == "fallback_validation" and out["text"] == DRAFT

    def test_model_copy_is_unwrapped_before_the_gates(self, monkeypatch):
        _arm(monkeypatch)
        monkeypatch.setattr(llm_auth, "make_call", _returns(f'```\n"{VOICED}"\n```'))
        out = rv.voice_or_fallback(DRAFT, family="missing_variable", account="kelly",
                                   parent_text=PARENT, numbers_whitelist=WHITELIST,
                                   cfg=ARMED_CFG)
        assert out["mode"] == "llm" and out["text"] == VOICED

    def test_provider_failure_falls_back_to_the_draft(self, monkeypatch):
        _arm(monkeypatch)
        monkeypatch.setattr(llm_auth, "make_call", lambda *a, **k: (None, "all_failed", None))
        out = rv.voice_or_fallback(DRAFT, account="kelly", cfg=ARMED_CFG)
        assert out["mode"] == "fallback_provider" and out["text"] == DRAFT

    def test_make_call_raising_never_escapes(self, monkeypatch):
        _arm(monkeypatch)

        def _boom(*_a, **_k):
            raise RuntimeError("provider exploded")

        monkeypatch.setattr(llm_auth, "make_call", _boom)
        out = rv.voice_or_fallback(DRAFT, account="kelly", cfg=ARMED_CFG)
        assert out["mode"] == "fallback_provider" and out["text"] == DRAFT

    def test_the_runaway_guard_falls_back(self, monkeypatch):
        _arm(monkeypatch)
        monkeypatch.setattr(llm_auth, "make_call", _returns(VOICED))
        cfg = {"reply_desk": {"voice": {"enabled": True, "max_calls_per_run": 1}}}
        first = rv.voice_or_fallback(DRAFT, account="kelly", parent_text=PARENT,
                                     numbers_whitelist=WHITELIST, cfg=cfg)
        second = rv.voice_or_fallback(DRAFT, account="kelly", parent_text=PARENT,
                                      numbers_whitelist=WHITELIST, cfg=cfg)
        assert first["mode"] == "llm"
        assert second["mode"] == "fallback_provider" and second["text"] == DRAFT
        assert rv.fallback_stats()["cap_hits"] == 1

    def test_the_guard_is_a_ROLLING_window_not_a_process_lifetime(self, monkeypatch):
        """The consumer is a daemon, not a per-tick process.

        `marketing_fastlane_daemon.py --lane reply` is a `while True` loop that
        ticks every 120s inside ONE process. A lifetime counter would mute the
        phrasing pass after the Nth reply of the daemon's life, silently, with
        every later reply shipping the template — the "armed but degraded"
        failure class. The window must roll.
        """
        _arm(monkeypatch)
        monkeypatch.setattr(llm_auth, "make_call", _returns(VOICED))
        cfg = {"reply_desk": {"voice": {"enabled": True, "max_calls_per_run": 1,
                                        "call_window_s": 1}}}
        assert rv.voice_or_fallback(DRAFT, account="kelly", parent_text=PARENT,
                                    numbers_whitelist=WHITELIST, cfg=cfg)["mode"] == "llm"
        assert rv.voice_or_fallback(DRAFT, account="kelly", parent_text=PARENT,
                                    numbers_whitelist=WHITELIST,
                                    cfg=cfg)["mode"] == "fallback_provider"
        # Age the recorded calls rather than sleeping through the window.
        _aged = [t - 10.0 for t in rv._CALL_TIMES]
        rv._CALL_TIMES.clear()
        rv._CALL_TIMES.extend(_aged)
        assert rv.voice_or_fallback(DRAFT, account="kelly", parent_text=PARENT,
                                    numbers_whitelist=WHITELIST, cfg=cfg)["mode"] == "llm"

    def test_an_abstention_is_never_phrased(self, monkeypatch):
        """No gift, no draft, nothing to say. The model is not asked to invent one."""
        _arm(monkeypatch)
        monkeypatch.setattr(llm_auth, "make_call",
                            lambda *a, **k: pytest.fail("provider touched on an empty draft"))
        assert rv.voice_or_fallback("", account="kelly", cfg=ARMED_CFG)["mode"] == "off"


class TestArming:
    def test_disarmed_env_never_touches_a_provider(self, monkeypatch):
        monkeypatch.delenv("MARKETING_LLM_ENABLED", raising=False)
        monkeypatch.setattr(llm_auth, "build_providers",
                            lambda *a, **k: pytest.fail("provider built while disarmed"))
        monkeypatch.setattr(llm_auth, "make_call",
                            lambda *a, **k: pytest.fail("provider called while disarmed"))
        rv.reset_stats()
        out = rv.voice_or_fallback(DRAFT, account="kelly", cfg=ARMED_CFG)
        assert out["mode"] == "off" and out["text"] == DRAFT

    def test_config_disabled_is_also_off(self, monkeypatch):
        monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
        monkeypatch.setattr(llm_auth, "build_providers",
                            lambda *a, **k: pytest.fail("provider built while disabled"))
        rv.reset_stats()
        out = rv.voice_or_fallback(
            DRAFT, account="kelly", cfg={"reply_desk": {"voice": {"enabled": False}}})
        assert out["mode"] == "off"

    def test_armed_but_mute_emits_a_line_start_annotation(self, monkeypatch, capsys):
        """The 2026-07-26 failure: armed, credential-less, silently templating.

        GitHub only parses `::` at column 0, and every logger here prefixes the
        line, so the annotation must be a bare print.
        """
        _arm(monkeypatch, providers=[])
        out = rv.voice_or_fallback(DRAFT, account="kelly", cfg=ARMED_CFG)
        assert out["mode"] == "fallback_provider"
        lines = [ln for ln in capsys.readouterr().out.splitlines()
                 if "reply_voice_mute" in ln]
        assert lines and lines[0].startswith("::warning title=reply_voice_mute::")


# ===========================================================================
# 6. The drafter hook
# ===========================================================================
class TestDrafterHook:
    def test_the_deterministic_path_is_untouched_when_disarmed(self, monkeypatch, cfg):
        monkeypatch.delenv("MARKETING_LLM_ENABLED", raising=False)
        out = rdr.draft_reply(account="kelly", target=TARGET, facts=FACTS,
                              family="missing_variable", cfg=cfg)
        assert out["draft"] == WARMED_DRAFT
        assert out["voice"]["mode"] == "off"
        assert out["components"]["voice_mode"] == "off"

    def test_an_armed_clean_model_line_ships_as_the_draft(self, monkeypatch, cfg):
        _arm(monkeypatch)
        monkeypatch.setattr(llm_auth, "make_call", _returns(VOICED))
        out = rdr.draft_reply(account="kelly", target=TARGET, facts=FACTS,
                              family="missing_variable", cfg=cfg, n_alts=2)
        assert out["draft"] == VOICED
        assert out["voice"]["mode"] == "llm"
        # Alternates are NOT voiced: they exist to differ in reasoning MOVE, and
        # one call per drafted reply is what keeps the per-run cap meaningful.
        assert all(GIFT in alt for alt in out["alt_drafts"])
        assert len(out["alt_drafts"]) == 2

    def test_a_violating_model_line_leaves_the_deterministic_draft(self, monkeypatch, cfg):
        _arm(monkeypatch)
        monkeypatch.setattr(llm_auth, "make_call",
                            _returns("Buy the widening. Spreads at 13.5% now."))
        out = rdr.draft_reply(account="kelly", target=TARGET, facts=FACTS,
                              family="missing_variable", cfg=cfg)
        assert out["draft"] == WARMED_DRAFT
        assert out["voice"]["mode"] == "fallback_validation"
        assert out["voice"]["violations"]

    def test_a_voice_module_failure_cannot_drop_a_reply(self, monkeypatch, cfg):
        _arm(monkeypatch)
        monkeypatch.setattr(rv, "voice_or_fallback",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        out = rdr.draft_reply(account="kelly", target=TARGET, facts=FACTS,
                              family="missing_variable", cfg=cfg)
        assert out["draft"] == WARMED_DRAFT and out["voice"]["mode"] == "off"

    def test_dial_findings_describe_the_text_that_ships(self, monkeypatch, cfg):
        """Grading the pre-voice text would report on copy nobody sees."""
        _arm(monkeypatch)
        monkeypatch.setattr(llm_auth, "make_call",
                            _returns("Credit is the test \U0001F58B️"))
        out = rdr.draft_reply(account="kelly", target=TARGET, facts=FACTS,
                              family="missing_variable", cfg=cfg)
        # The borrowed-quirk line never reaches the draft (the gates catch it),
        # so the shipping text is the deterministic one and grades clean.
        assert out["draft"] == WARMED_DRAFT
        assert out["dial_violations"] == []


# ===========================================================================
# 7. The reply_value critic — one test per anti-pattern class
# ===========================================================================
class TestReplyValueCritic:
    def test_a_genuine_question_to_the_poster_rejects(self):
        verdict = rc.reply_value("What do you think of TIPS in this environment?", {})
        assert verdict["verdict"] == "reject"
        assert "addressed to the poster" in verdict["reasons"][0]

    def test_a_question_carrying_a_gift_survives(self):
        """charter §3: an author reply-back is the highest-value reply outcome.

        The corpus measures LIKES, which is not our objective function, so the
        `author_question` family stays legal — as long as the room gets paid too.
        """
        draft = rdr.compose("author_question", GIFT,
                            {"subject": "capex", "mechanism": "credit"})
        assert draft.rstrip().endswith("?")
        assert rc.reply_value(draft, {"family": "author_question"})["verdict"] == "pass"

    def test_a_rhetorical_question_to_the_room_survives(self):
        """The winning question shape: an accusation with a question mark."""
        assert rc.reply_value(
            "Isn't a 12.5% spread move supposed to matter to equities?",
            {})["verdict"] == "pass"

    @pytest.mark.parametrize("boilerplate", [
        "Breaking events like this remind us why risk management matters.",
        "Stay informed and avoid emotional decisions here.",
        "Let this be a reminder that credit leads equities.",
    ])
    def test_advice_column_boilerplate_rejects(self, boilerplate):
        assert rc.reply_value(boilerplate, {})["verdict"] == "reject"

    def test_an_unclosed_ramble_rejects(self):
        ramble = ("credit spreads widened again and the capex story still has not "
                  "answered the funding question at all ") * 5
        verdict = rc.reply_value(ramble, {"family": "compression"})
        assert verdict["verdict"] == "reject"
        assert "words (bar 60)" in verdict["reasons"][0]

    def test_the_long_form_family_may_run_long(self):
        ramble = ("credit spreads widened again and the capex story still has not "
                  "answered the funding question at all ") * 5
        assert rc.reply_value(ramble, {"family": "micro_framework"})["verdict"] == "pass"

    def test_an_absent_family_fails_closed_on_length(self):
        """A caller that forgot to say which family this is gets the short bar."""
        ramble = ("credit spreads widened again and the capex story still has not "
                  "answered the funding question at all ") * 5
        assert rc.reply_value(ramble, {})["verdict"] == "reject"

    @pytest.mark.parametrize("reaction", ["Oh wonderful.", "This.", "Facts."])
    def test_one_word_reactions_reject(self, reaction):
        assert rc.reply_value(reaction, {})["verdict"] == "reject"

    def test_a_short_data_drop_is_not_a_one_word_reaction(self):
        """Calibrated against the corpus winners, not against intuition."""
        for winner in ("$NVDA -18.5% today", "Support at 900-925", "Actually closer to -10%"):
            assert rc.reply_value(winner, {})["verdict"] == "pass", winner

    def test_the_clean_house_draft_passes(self):
        assert rc.reply_value(DRAFT, {"family": "missing_variable"})["verdict"] == "pass"

    def test_the_critic_is_wired_into_the_pass(self, cfg):
        # WARMED_DRAFT, not DRAFT: the plain composition is now a cold printout
        # and `warmth_register` rejects it, which would make this test about the
        # wrong critic. The deterministic drafter ships the warmed form.
        verdict = rc.run_critics(WARMED_DRAFT, {
            "account": "kelly", "parent_text": PARENT, "numbers_whitelist": WHITELIST,
            "corpus": [], "theses": [], "cfg": cfg, "family": "missing_variable",
        })
        assert "reply_value" in {c["critic"] for c in verdict["critics"]}
        assert verdict["verdict"] == "pass"

    def test_the_critic_kills_a_draft_through_the_full_pass(self, cfg):
        verdict = rc.run_critics("What do you think of credit here?", {
            "account": "kelly", "parent_text": PARENT, "numbers_whitelist": WHITELIST,
            "corpus": [], "theses": [], "cfg": cfg,
        })
        assert "reply_value" in verdict["rejected_by"]


# ===========================================================================
# 8. Roster completeness — the queue's full-roster gate still holds
# ===========================================================================
def _item(draft: str = DRAFT, critics: dict | None = None) -> dict:
    return rq.make_item(
        account="kelly",
        target_url="https://x.com/somequant/status/1900000000000000001",
        parent_author="somequant", parent_excerpt=PARENT, draft=draft,
        tier="relationship", score=0.8, score_components={"author_tier": 0.26},
        critics=critics, now=NOW,
    )


class TestRosterCompleteness:
    def test_the_new_critic_is_in_the_register(self):
        assert "reply_value" in rc.CRITICS
        assert "reply_value" in rc._CRITIC_FUNCS
        # 9 at E4; the warmth build (2026-08-01) added `warmth_register` (the
        # anti-cold law) and `fabrication` (AM-R1 on every account, including
        # the codex-less flagship the dial could never reach).
        assert len(rc.CRITICS) == 11

    def test_a_full_stamp_still_enqueues(self, tmp_path, cfg):
        verdict, stamp = rc.screen(WARMED_DRAFT, {
            "account": "kelly", "parent_text": PARENT, "numbers_whitelist": WHITELIST,
            "corpus": [], "theses": [], "cfg": cfg, "family": "missing_variable",
        })
        assert verdict["verdict"] == "pass"
        assert "reply_value" in stamp["critics_run"]
        assert rq.enqueue(_item(critics=stamp), tmp_path / "store")["ok"] is True

    def test_a_stamp_without_the_new_critic_is_refused(self, tmp_path):
        """The store's guarantee, re-proved after the roster grew.

        A producer pinned to the OLD eight-critic roster must not be able to
        enqueue: an item that never faced `reply_value` has not cleared the
        critics, whatever its stamp says.
        """
        stale = rc.stamp({
            "verdict": "pass", "rejected_by": [],
            "critics": [{"critic": n, "verdict": "pass", "reasons": []}
                        for n in rc.CRITICS if n != "reply_value"],
        })
        item = _item(critics=stale)
        errors = rq.validate_critic_stamp(item)
        assert any("reply_value" in e for e in errors)
        assert rq.enqueue(item, tmp_path / "store")["ok"] is False


# ===========================================================================
# 9. Import closure + dependency direction
# ===========================================================================
def test_no_lazy_only_dependency_is_imported_at_module_level():
    forbidden = {
        "anthropic", "yaml", "pandas", "numpy", "httpx",
        "engine.llm_auth", "lib.config",
        "engine.marketing.copywriter", "engine.marketing.hot_tape_llm",
        "engine.marketing.reply_critics", "engine.marketing.expression_dial",
    }
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    offenders = []
    for node in tree.body:  # module level ONLY — nested imports are the contract
        if isinstance(node, ast.Import):
            offenders += [a.name for a in node.names
                          if a.name.split(".")[0] in forbidden or a.name in forbidden]
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod in forbidden or mod.split(".")[0] in forbidden:
                offenders.append(mod)
    assert not offenders, (
        "reply_voice imports these at module level; the marketing-engine lane has "
        f"no such packages and would go red at collection: {offenders}")


def test_module_imports_no_heavy_dependency():
    src = MODULE_PATH.read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import anthropic|from anthropic)", src, re.MULTILINE)


def test_the_dependency_points_one_way():
    """reply_drafter -> reply_voice, never the reverse.

    Prose may name the drafter (the docstring explains the seam); an IMPORT of
    it would make the phrasing pass a participant in composition rather than a
    layer on top of it, and would close an import cycle.
    """
    src = MODULE_PATH.read_text(encoding="utf-8")
    assert "import reply_drafter" not in src
    assert "from engine.marketing.reply_drafter import" not in src


def test_the_gates_are_imported_not_forked():
    """A second number regex means a figure that clears here fails downstream."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    assert "from engine.marketing.hot_tape_llm import numeric_violations" in src
    assert "from engine.marketing.hot_tape_llm import call_violations" in src
    assert "from engine.marketing.copywriter import banned_language" in src


# ===========================================================================
# 10. The shipped config
# ===========================================================================
class TestShippedConfig:
    def test_the_voice_block_ships(self, cfg):
        voice = cfg["reply_desk"]["voice"]
        assert voice["enabled"] is True
        assert int(voice["max_calls_per_run"]) == 40
        assert voice["model_key"] == "marketing_copy"
        assert float(voice["call_window_s"]) > 0, (
            "the runaway guard needs a window; without one it is a lifetime "
            "counter in a daemon that never restarts")

    def test_the_model_key_resolves_in_the_root_config(self, cfg):
        models = yaml.safe_load(
            (ROOT / "config.yml").read_text(encoding="utf-8"))["llm_models"]
        assert models[cfg["reply_desk"]["voice"]["model_key"]]

    def test_the_producer_is_still_dark(self, cfg):
        """Arming the phrasing must not arm the lane that calls it."""
        assert cfg["reply_desk"]["producer"]["enabled"] is False
        assert set(cfg["reply_desk"]["modes_enabled"]) == {"M0", "M1"}


# ===========================================================================
# 11. E-wave adversarial review — the never-raise contract, the gate's own
#     whitelist, the rolling window, and the §10 E3 exemplar hook
# ===========================================================================

class TestNeverRaisesIncludesTheGate:
    """MAJOR 9. `voice_or_fallback` is documented "Never raises" and doctrine
    §0 gate 1 rests on it: the caller treats a reply as always-postable.

    `validate_reply_copy` sat OUTSIDE the try that guards the provider walk, and
    it performs four LAZY imports (hot_tape_llm, reply_critics, copywriter,
    expression_dial) — any of which can ImportError in a thin runtime, which is
    exactly the environment this package is built to survive. The exception
    escaped the function that promised not to raise.
    """

    def test_a_raising_validator_falls_back_instead_of_escaping(self, monkeypatch):
        _arm(monkeypatch)
        monkeypatch.setattr(llm_auth, "make_call", _returns(VOICED))

        def _boom(*a, **k):
            raise ImportError("No module named 'expression_dial'")

        monkeypatch.setattr(rv, "validate_reply_copy", _boom)
        out = rv.voice_or_fallback(DRAFT, account="kelly", parent_text=PARENT,
                                   numbers_whitelist=WHITELIST, cfg=ARMED_CFG)

        assert out["text"] == DRAFT, "unvalidated model copy shipped"
        assert out["mode"] == "fallback_validation"
        assert any("ImportError" in v for v in out["violations"]), out["violations"]
        assert rv.fallback_stats()["fallback_validation"] == 1


class TestGateJudgesTheListThePromptHandedOut:
    """m1. The prompt's ALLOWED NUMBERS is the own-feed whitelist UNION the
    deterministic draft's own figures (`allowed_numbers`) — the draft is about
    to ship verbatim, so its numbers are admissible by construction. The
    fact_discipline gate was given the whitelist ALONE, so a model that obeyed
    the prompt and reused a draft figure was rejected for compliance, inflating
    the fallback telemetry with correct copy.
    """

    def test_a_draft_only_number_is_not_a_violation(self):
        draft = "Front-end yields sat at 4.25% while the curve held."
        # 4.25% is in the DRAFT and NOT in the own-feed whitelist.
        assert "4.25%" in rv.allowed_numbers(draft, ["12.5%"])
        hits = _gates("The curve held while front-end yields sat at 4.25%.",
                      draft=draft, numbers_whitelist=["12.5%"])
        assert not [h for h in hits if "fact_discipline" in h], hits

    def test_a_number_in_neither_set_still_rejects(self):
        draft = "Front-end yields sat at 4.25% while the curve held."
        hits = _gates("The curve held while front-end yields sat at 9.87%.",
                      draft=draft, numbers_whitelist=["12.5%"])
        assert [h for h in hits if "fact_discipline" in h or "number" in h.lower()], (
            "a figure in neither the whitelist nor the draft cleared the gate")


class TestRunawayGuardIsTrulyRolling:
    """m2. A tumbling counter (count + window-start, reset wholesale when the
    window elapses) permits 2x the cap across the boundary: 40 calls at t=3599
    and 40 more at t=3601 is 80 calls in two seconds, and the counters read
    compliant the whole time.
    """

    def test_a_burst_straddling_the_boundary_is_capped(self, monkeypatch):
        cap, window = 3, 3600.0
        ticks = {"t": 0.0}
        monkeypatch.setattr(rv.time, "monotonic", lambda: ticks["t"])
        rv.reset_stats()

        # One call opens the hour...
        assert rv._take_call_slot(cap, window) is True
        # ...and the rest of the budget is spent at the very END of it.
        ticks["t"] = 3599.0
        assert rv._take_call_slot(cap, window) is True
        assert rv._take_call_slot(cap, window) is True
        assert rv._take_call_slot(cap, window) is False

        # Two seconds later a TUMBLING window has elapsed (3601 - 0 >= 3600) and
        # hands back the WHOLE budget, so `cap` more calls fire in the next
        # instant: 2x the cap inside three seconds, with the counters reading
        # compliant throughout. A rolling window returns exactly the one slot
        # that aged out — the t=0 call — and not one more.
        ticks["t"] = 3601.0
        assert rv._take_call_slot(cap, window) is True
        assert rv._take_call_slot(cap, window) is False, (
            f"the guard handed back the whole budget at the boundary — a cap of "
            f"{cap} per {window:.0f}s allowed {cap * 2} calls in three seconds")

        # The budget returns only as the calls themselves age out.
        ticks["t"] = 3599.0 + window + 1.0
        assert rv._take_call_slot(cap, window) is True

    def test_the_window_still_rolls_for_a_long_lived_daemon(self, monkeypatch):
        """The mirror: a guard that never resets is an off switch with a delay."""
        ticks = {"t": 0.0}
        monkeypatch.setattr(rv.time, "monotonic", lambda: ticks["t"])
        rv.reset_stats()
        assert rv._take_call_slot(1, 60.0) is True
        assert rv._take_call_slot(1, 60.0) is False
        ticks["t"] += 61.0
        assert rv._take_call_slot(1, 60.0) is True


class TestReplyExemplarHook:
    """BLOCKER 3, reply half. §10 E3: "writer/critic prompts load exemplars from
    the store (config-pinned version, never auto-flipped)". `active_exemplars`
    had NO production caller — reply_voice imported neither exemplar_store nor
    x_intel.
    """

    @staticmethod
    def _store(tmp_path, *, version: int = 3) -> Path:
        import json

        from engine.marketing import exemplar_store

        d = tmp_path / "data" / "marketing" / "x_intel"
        d.mkdir(parents=True, exist_ok=True)
        (d / "exemplar_store.json").write_text(json.dumps({
            "schema": exemplar_store.STORE_SCHEMA,
            "latest_version": version + 1,
            "versions": [
                {"version": version, "ratified_by": "chris", "n_entries": 1,
                 "entries": [{"register": "trader", "text": "RATIFIED SHOT 41.7",
                              "post_id": "1", "engagement": {"interaction_rate": 0.2}}]},
                {"version": version + 1, "ratified_by": "chris", "n_entries": 1,
                 "entries": [{"register": "trader", "text": "NEWER UNPINNED SHOT",
                              "post_id": "2", "engagement": {"interaction_rate": 0.9}}]},
            ],
            "pending": [{"register": "trader", "text": "PENDING SHOT",
                         "post_id": "3", "engagement": {"interaction_rate": 0.99}}],
        }), encoding="utf-8")
        return tmp_path

    def test_unpinned_is_byte_identical_to_the_baseline_prompt(self, tmp_path):
        """DARK-SAFE. The shipped config pins nothing, so today's prompt must not
        move by a single byte — and the store must not even be opened."""
        root = self._store(tmp_path)
        assert rv.system_prompt({"intel": {"exemplar_store": {"active_version": None}}},
                                root) == rv.SYSTEM_PROMPT
        assert rv.system_prompt(None, root) == rv.SYSTEM_PROMPT
        assert rv.system_prompt({}, root) == rv.SYSTEM_PROMPT

    def test_a_pinned_version_reaches_the_prompt_the_provider_receives(
            self, monkeypatch, tmp_path):
        """Through the REAL production entry point, not a shim: whatever
        `voice_or_fallback` hands `client.messages.create` as `system`."""
        root = self._store(tmp_path)
        seen: dict = {}

        def _capture(providers, fn, context=""):
            class _C:
                class messages:
                    @staticmethod
                    def create(**kw):
                        seen.update(kw)
                        raise RuntimeError("stop here — the prompt is the assertion")
            try:
                fn(_C(), "m")
            except RuntimeError:
                pass
            return None, "captured", "oauth"

        _arm(monkeypatch)
        monkeypatch.setattr(llm_auth, "make_call", _capture)
        cfg = dict(ARMED_CFG)
        cfg["intel"] = {"exemplar_store": {"active_version": 3}}
        rv.voice_or_fallback(DRAFT, account="kelly", parent_text=PARENT,
                             numbers_whitelist=WHITELIST, cfg=cfg, root=root)

        system = seen.get("system") or ""
        assert "RATIFIED SHOT 41.7" in system, (
            "the pinned exemplar never reached the prompt the provider sees")
        # The playbook baseline is kept, never replaced.
        assert rv.PLAYBOOK_EXEMPLARS[0][2][:30] in system

    def test_the_pin_is_the_only_input_never_the_latest_or_the_pending_pool(
            self, tmp_path):
        root = self._store(tmp_path)
        prompt = rv.system_prompt({"intel": {"exemplar_store": {"active_version": 3}}},
                                  root)
        assert "NEWER UNPINNED SHOT" not in prompt, "the store auto-flipped forward"
        assert "PENDING SHOT" not in prompt, "an unratified candidate reached the writer"

    def test_an_exemplar_number_does_not_widen_the_numeric_gate(self, tmp_path):
        """EPISTEMICS. Exemplar TEXT is a style reference; the figures inside it
        are other people's. A model that lifts one is rejected exactly as if it
        had invented it."""
        root = self._store(tmp_path)
        prompt = rv.system_prompt({"intel": {"exemplar_store": {"active_version": 3}}},
                                  root)
        assert "41.7" in prompt, "fixture is degenerate — no number in the exemplar"
        assert "41.7" not in rv.allowed_numbers(DRAFT, WHITELIST)
        hits = _gates("Credit is the test, not the tape. Spreads at 41.7 say so.")
        assert hits, "a number that exists only in an exemplar cleared the gate"


# ===========================================================================
# 12. CHATGPT-FIRST ROUTING (operator directive 2026-07-29)
#
# "The marketing content LLM lanes must default to the attached ChatGPT/Codex
# account (Claude subscription tokens are being reserved for website-building
# sessions), with Claude as fallback drawn through the key_pool OAuth load
# balancer."
#
# Ruled tier for the reply desk: gpt-5.6-terra at medium effort. Terra because a
# reply is a short conversational turn on someone else's post, the same register
# as the wire. The full ruling table lives in tests/test_marketing_copy_v2.py.
# ===========================================================================

class TestCodexFirstRouting:
    def _capture(self, monkeypatch) -> list[dict]:
        """Recorder in place of build_providers. Returning [] takes the lane down
        its fallback branch, the shortest path that still proves the request."""
        seen: list[dict] = []

        def _rec(cfg, **kwargs):  # noqa: ANN001
            seen.append(dict(cfg))
            return []

        monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
        monkeypatch.setattr(llm_auth, "build_providers", _rec)
        rv.reset_stats()
        return seen

    def test_the_reply_desk_asks_for_codex_first_on_terra(self, monkeypatch, cfg, capsys):
        seen = self._capture(monkeypatch)
        out = rv.voice_or_fallback(
            DRAFT, family="missing_variable", account="kelly",
            parent_text=PARENT, numbers_whitelist=WHITELIST, cfg=cfg)
        capsys.readouterr()
        assert out["text"] == DRAFT, "a muted lane must hand the draft back"

        assert seen, "the reply desk never reached the provider waterfall"
        pcfg = seen[0]
        assert pcfg["provider_order"] == ["codex", "oauth", "anthropic", "deepseek"]
        assert pcfg["codex_source_model"] == "gpt-5.6-terra"
        assert pcfg["codex_reasoning_effort"] == "medium"
        assert pcfg["oauth_pool_lane"] == "reply-voice"
        assert pcfg["usage_lane"] == "reply-voice"

    def test_the_shipped_voice_block_carries_the_ruling(self, cfg):
        voice = cfg["reply_desk"]["voice"]
        assert voice["provider_order"] == ["codex", "oauth", "anthropic", "deepseek"]
        assert voice["codex_source_model"] == "gpt-5.6-terra"
        assert voice["codex_reasoning_effort"] == "medium"
        assert voice["oauth_pool_lane"] == "reply-voice"
        # Luna never touches a user-facing word.
        assert "luna" not in str(voice).lower()

    def test_the_source_default_is_codex_first_too(self):
        """The config file is the operator surface; this literal is what runs
        when a caller hands the module a bare cfg. They must not disagree."""
        src = MODULE_PATH.read_text(encoding="utf-8")
        assert '["codex", "oauth", "anthropic", "deepseek"]' in src
        assert '"gpt-5.6-terra"' in src
        assert '"gpt-5.6-luna"' not in src
