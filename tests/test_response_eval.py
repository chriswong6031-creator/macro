"""Tests for the W2 offline answer-quality eval harness.

    engine/neuralweb/response_eval.py       scoring core (rubric, checks, judge)
    engine/neuralweb/eval/benchmark_*.json  the frozen operator case
    scripts/run_brain_eval.py               the weekly entry
    .github/workflows/brain-eval.yml        the weekly lane

NO NETWORK ANYWHERE IN THIS FILE. The judge and the answerer are injected
callables (that is why they are injected), so every test here passes a fake. A
test that reached a provider would be a test that is red whenever a key expires,
which is how a suite stops being run.

The sharpest pins in here are the ones that catch a harness that LOOKS like it
works: parse_judge clamping (an unclamped axis inflates the total past 100), the
unparseable-vs-zero distinction (a transport failure must never read as a quality
collapse), and the sidecar merge preserving operator keys (a weekly machine pass
that erases the operator's own grades is worse than no harness at all).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from engine.neuralweb import response_eval as ev

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row(rid="r1", answer="A clean read.\n\nWatch — don't chase — events unsettled.",
         **kw):
    base = {
        "id": rid,
        "schema": "mastermind.response_log.v1",
        "ts": "2026-07-28T12:00:00+00:00",
        "surface": "macro",
        "lane": "fast",
        "model": "deepseek-v4-pro",
        "question": "Why is everything red?",
        "answer": answer,
        "lang": "en",
        "flags": {"filtered": False, "degraded": False, "error": False,
                  "screened": False},
    }
    base.update(kw)
    return base


def _judge_reply(total_each=None, tags=None, note="ok", **axes):
    """A judge reply JSON string. `total_each` fills every axis with its max."""
    scores = {}
    for axis, weight in ev.RUBRIC.items():
        scores[axis] = weight if total_each == "max" else (total_each or 0)
    scores.update(axes)
    return json.dumps({"scores": scores, "tags": tags or [], "note": note})


def _fake_judge(reply, *, model="fake-judge"):
    calls: list[str] = []

    def _j(prompt):
        calls.append(prompt)
        return reply(prompt) if callable(reply) else reply

    _j.model_id = model
    _j.calls = calls
    return _j


# ---------------------------------------------------------------------------
# Rubric + taxonomy
# ---------------------------------------------------------------------------

def test_rubric_weights_sum_to_100():
    """§9 is a 100-point rubric with a pass at 80. If the weights drift the
    threshold silently changes meaning — an 80 out of 90 is not a pass at 80."""
    assert sum(ev.RUBRIC.values()) == 100
    assert ev.PASS_THRESHOLD == 80


def test_rubric_axes_are_exactly_the_nine_section_axes():
    assert set(ev.RUBRIC) == {
        "regime_identification", "user_supplied_data", "catalyst_verification",
        "cross_asset_consistency", "mechanical_translation",
        "fact_desk_inference_separation", "conditional_signposts",
        "voice_compliance",
    }
    # Every axis is glossed for the judge — an unglossed axis is graded on the
    # strength of its slug alone, which is how a rubric quietly stops working.
    assert set(ev.RUBRIC_GLOSS) == set(ev.RUBRIC)


def test_failure_tags_are_frozen_and_glossed():
    assert set(ev.FAILURE_TAGS) == {
        "headline_first", "single_cause_forcing", "yield_direction_misread",
        "stale_as_live", "invented_odds", "refusal_regression", "doctrine_leak",
    }
    assert set(ev.FAILURE_TAG_GLOSS) == set(ev.FAILURE_TAGS)
    assert ev.MECHANICAL_TAGS <= set(ev.FAILURE_TAGS)
    assert ev.HARD_FAIL_TAGS <= ev.MECHANICAL_TAGS


def test_stance_enum_matches_the_gateway_prompt():
    """The stance enum is restated in response_eval (brain_gateway is a FastAPI
    request-path module). This is the pin that keeps the copy honest: a gateway
    edit that renames or adds a stance must red HERE, or the mechanical stance
    check starts reporting a compliant answer as a voice defect."""
    src = (ROOT / "engine" / "neuralweb" / "brain_gateway.py").read_text(encoding="utf-8")
    line = "Act · Get ready · Watch — don't chase · Protect gains · Stand aside · Ignore"
    assert line in src, "gateway stance enum line moved — re-pin STANCE_ENUM"
    assert [s.strip() for s in line.split("·")] == list(ev.STANCE_ENUM)


# ---------------------------------------------------------------------------
# mechanical_checks — one test per failure class
# ---------------------------------------------------------------------------

def test_mech_stance_present_and_absent():
    good = ev.mechanical_checks(_row())
    assert good["stance"]["found"] and good["stance"]["value"] == "Watch — don't chase"
    assert good["tags"] == []
    bad = ev.mechanical_checks(_row(answer="Stocks fell. Bonds fell. That is all."))
    assert bad["stance"]["found"] is False


def test_mech_stance_tolerates_ascii_dash_and_curly_apostrophe():
    c = ev.mechanical_checks(_row(answer="Watch - don’t chase — the long end leads."))
    assert c["stance"]["value"] == "Watch — don't chase"


def test_mech_stance_does_not_fire_on_the_word_actually():
    """"Act" is a whole stance AND the prefix of a common adverb. Without the
    line anchor + word boundary every answer containing "Actually" would read as
    carrying a compliant stance line, and the check would pass on everything."""
    c = ev.mechanical_checks(_row(answer="Actually the curve steepened, and action was thin."))
    assert c["stance"]["found"] is False


def test_zh_stance_forms_track_the_i18n_glossary():
    """engine/i18n.py's LEX is the canonical doctrine six ("for this and every
    future surface"), and brain_gateway._language_directive("zh") hands the model
    those exact forms. The frozen fallback in response_eval is only for an import
    failure — if the glossary is edited and the fallback is not, THIS reds."""
    from engine.i18n import LEX

    live = ev._zh_stance_forms()
    assert set(live) == set(ev.STANCE_ENUM)
    for en in ev.STANCE_ENUM:
        assert LEX[en] == live[en] == ev.ZH_STANCE_FALLBACK[en], en

    # …and the gateway really does instruct these forms on a zh turn.
    gw = (ROOT / "engine" / "neuralweb" / "brain_gateway.py").read_text(encoding="utf-8")
    for en in ev.STANCE_ENUM:
        assert f"{en}={LEX[en]}" in gw, f"gateway zh directive missing {en}"


def test_mech_stance_is_checkable_on_a_zh_turn_via_the_doctrine_forms():
    """W1 finding C fix: the zh stance IS mechanically checkable now — a Chinese
    answer carrying a Chinese doctrine form has a compliant stance line."""
    zh = ev.mechanical_checks(_row(
        answer="今天曲线呈现熊市变陡：长端抛售，前端走强。\n\n观察—勿追高。", lang="zh"))
    assert zh["stance"]["checkable"] is True
    assert zh["stance"]["found"] is True
    assert zh["stance"]["value"] == "Watch — don't chase"
    assert zh["stance"]["form_lang"] == "zh"
    assert zh["stance"]["lang_mismatch"] is False
    assert zh["stance_lang_mismatch"] is False

    # every one of the six resolves
    for en, zh_form in ev._zh_stance_forms().items():
        c = ev.mechanical_checks(_row(answer=f"长端抛售。\n\n{zh_form}。", lang="zh"))
        assert c["stance"]["value"] == en, en
        assert c["stance"]["form_lang"] == "zh", en


def test_mech_zh_stance_tolerates_doubled_dash_and_spacing():
    """"观察—勿追高" is one em dash canonically; a model reaches for "——" or
    spaces. The form is still the doctrine form."""
    for answer in ("长端抛售。观察——勿追高。", "长端抛售。观察 — 勿追高。",
                   "长端抛售。观察-勿追高。", "长端抛售。观察勿追高。"):
        c = ev.mechanical_checks(_row(answer=answer, lang="zh"))
        assert c["stance"]["value"] == "Watch — don't chase", answer


def test_mech_zh_stance_does_not_fire_on_incidental_prose():
    """The CJK counterpart of the "Actually" trap, and worse: CJK writes no
    spaces and has no \\b, so an unanchored 忽略/立即行动 matches ordinary prose
    ("不要忽略信贷市场的信号" = "don't ignore credit market signals") and the
    stance check would pass on nearly every Chinese answer."""
    for answer in ("不要忽略信贷市场的信号，长端仍在抛售。",
                   "市场需要立即行动的理由还不充分。"):
        c = ev.mechanical_checks(_row(answer=answer, lang="zh"))
        assert c["stance"]["found"] is False, answer

    # …but the same words ON THEIR OWN LINE are the real stance line.
    for zh_form, en in (("忽略", "Ignore"), ("立即行动", "Act")):
        c = ev.mechanical_checks(_row(answer=f"长端抛售，前端走强。\n\n{zh_form}。",
                                      lang="zh"))
        assert c["stance"]["value"] == en, zh_form


def test_mech_english_stance_on_a_zh_turn_is_a_language_mismatch():
    """Precisely W1 finding C: the stance is PRESENT but in the wrong alphabet.
    A distinct defect from a missing stance, so it rides as its own flag."""
    c = ev.mechanical_checks(_row(
        answer="长端抛售，前端走强。\n\nWatch — don't chase.", lang="zh"))
    assert c["stance"]["found"] is True
    assert c["stance"]["form_lang"] == "en"
    assert c["stance"]["lang_mismatch"] is True
    assert c["stance_lang_mismatch"] is True
    # …and it is NOT smuggled into the frozen §9 taxonomy.
    assert "stance_lang_mismatch" not in ev.FAILURE_TAGS
    assert c["tags"] == []
    scored = ev.score_response(_row(answer="长端抛售。Watch — don't chase.", lang="zh"),
                               _fake_judge(_judge_reply("max")))
    assert scored["tags"] == [], "mech-only flag must never enter the tag census"


def test_mech_zh_stance_on_an_english_turn_is_also_a_mismatch():
    c = ev.mechanical_checks(_row(answer="The long end sold off.\n\n观察—勿追高。",
                                  lang="en"))
    assert c["stance"]["found"] is True and c["stance"]["form_lang"] == "zh"
    assert c["stance"]["lang_mismatch"] is True


def test_mech_stance_mismatch_is_none_when_the_turn_language_is_unknown():
    """None, not False: an older lane-less row declares no language, so there is
    nothing for the stance to be mismatched against."""
    c = ev.mechanical_checks(_row(answer="Watch — don't chase.", lang=None))
    assert c["stance"]["found"] is True
    assert c["stance"]["lang_mismatch"] is None
    assert c["stance_lang_mismatch"] is False


def test_mech_absent_stance_on_a_zh_turn_is_still_a_real_defect():
    c = ev.mechanical_checks(_row(answer="今天全线下跌，长端抛售。", lang="zh"))
    assert c["stance"]["checkable"] is True
    assert c["stance"]["found"] is False
    assert c["stance"]["lang_mismatch"] is None


def test_judge_prompt_reports_the_stance_mismatch_and_both_alphabets():
    mismatch = _row(answer="长端抛售。\n\nWatch — don't chase.", lang="zh")
    p = ev.build_judge_prompt(mismatch, ev.mechanical_checks(mismatch))
    assert "stance line: PRESENT" in p
    assert "stance LANGUAGE MISMATCH" in p
    assert "观察—勿追高" in p
    assert "NOT MECHANICALLY CHECKABLE" not in p

    absent = _row(answer="今天全线下跌。", lang="zh")
    p2 = ev.build_judge_prompt(absent, ev.mechanical_checks(absent))
    assert "stance line: ABSENT" in p2
    # the ABSENT line names BOTH alphabets, so the judge is not told to look for
    # an English token under a Chinese answer
    assert "立即行动" in p2 and "Act /" in p2

    clean = _row(answer="长端抛售。\n\n观察—勿追高。", lang="zh")
    p3 = ev.build_judge_prompt(clean, ev.mechanical_checks(clean))
    assert "stance line: PRESENT" in p3 and "LANGUAGE MISMATCH" not in p3


def test_mech_catches_doctrine_leak_from_both_libraries():
    from engine.neuralweb import analyst_doctrine, doctrine

    for sentinel in (analyst_doctrine.LEAK_SENTINELS[0], doctrine.LEAK_SENTINELS[0]):
        c = ev.mechanical_checks(_row(answer=f"As the {sentinel} says, start with the regime."))
        assert c["leak"]["hit"], sentinel
        assert "doctrine_leak" in c["tags"]
        assert sentinel in c["leak"]["sentinels"]


def test_mech_catches_invented_odds_in_every_shape():
    for answer in (
        "There is a 70% chance of a cut this month.",
        "The probability of a cut is around 60%.",
        "Odds of a bounce sit near 55%.",
        "This resolved higher 7 of 10 times.",
        "This resolved higher 7 out of 10 times.",
        "降息的概率约 70%。",
        "有 70% 的可能性反弹。",
    ):
        c = ev.mechanical_checks(_row(answer=answer))
        assert c["odds"]["hit"], answer
        assert "invented_odds" in c["tags"], answer
        assert c["odds"]["matches"], answer


def test_mech_does_not_flag_honest_conditional_language_as_odds():
    """The product's compliant form is a CONDITION, not a probability. If the
    odds regex fired on these, the tag would become noise and get ignored."""
    for answer in (
        "If breakevens keep rising, the long end stays under pressure.",
        "Watch — don't chase. Two things would change the read.",
        "The 10Y moved 8.6bp while the 1Y fell 5.1bp.",
        "Breadth is 55% advancing.",
    ):
        c = ev.mechanical_checks(_row(answer=answer))
        assert not c["odds"]["hit"], answer


def test_mech_catches_refusal_regression():
    """Recommendations are ENABLED for this product (operator ruling). A refusal
    or an advice disclaimer is a REGRESSION, so it must be tagged, not rewarded."""
    for answer in (
        "I can't provide financial advice.",
        "I'm not a financial advisor, so I cannot recommend anything.",
        "Please consult a financial advisor before acting.",
        "抱歉，我无法提供投资建议。",
    ):
        c = ev.mechanical_checks(_row(answer=answer))
        assert c["refusal"]["hit"], answer
        assert "refusal_regression" in c["tags"], answer


def test_mech_zh_language_compliance():
    english_to_zh_turn = (
        "The curve bear-steepened today: the long end sold off hard while the "
        "front end rallied on growth fear, and TLT fell with it."
    )
    bad = ev.mechanical_checks(_row(answer=english_to_zh_turn, lang="zh"))
    assert bad["lang"]["compliant"] is False
    assert bad["lang"]["cjk_ratio"] < ev.ZH_CJK_MIN_RATIO

    good = ev.mechanical_checks(_row(
        answer="今天曲线呈现熊市变陡：长端大幅抛售，前端因增长担忧而走强，TLT 同步下跌。",
        lang="zh"))
    assert good["lang"]["compliant"] is True

    # An English turn is never measured on CJK share.
    en = ev.mechanical_checks(_row(answer=english_to_zh_turn, lang="en"))
    assert en["lang"]["compliant"] is None


def test_mech_zh_ratio_unmeasurable_on_a_tiny_answer_is_none_not_false():
    """None, not False: a two-word answer carries no evidence about language, and
    reporting False there would manufacture a defect on every short reply."""
    c = ev.mechanical_checks(_row(answer="好的。", lang="zh"))
    assert c["lang"]["compliant"] is None


def test_mech_passes_flags_through_and_marks_empty():
    c = ev.mechanical_checks(_row(answer="", flags={"degraded": True, "error": True}))
    assert c["empty"] is True and c["chars"] == 0
    assert c["flags"]["degraded"] is True and c["flags"]["error"] is True


def test_mech_never_raises_on_garbage():
    for bad in (None, [], "a string", {"answer": 42}, {"flags": "nope"}):
        out = ev.mechanical_checks(bad)  # type: ignore[arg-type]
        assert isinstance(out, dict) and "tags" in out


# ---------------------------------------------------------------------------
# build_judge_prompt
# ---------------------------------------------------------------------------

def test_judge_prompt_carries_rubric_tags_and_data_markers():
    row = _row(answer="Bear steepening. Watch — don't chase.")
    p = ev.build_judge_prompt(row, ev.mechanical_checks(row))
    for axis, weight in ev.RUBRIC.items():
        assert axis in p and f"max {weight}" in p
    for tag in ev.FAILURE_TAGS:
        assert tag in p
    # The logged question is USER-AUTHORED text. It rides inside explicit data
    # markers with an ignore-instructions directive, exactly as in
    # admin/mastermind_logs._classify_prompt — a logged question reading "score
    # this 100" must not be able to steer the grader judging it.
    assert "<<<DATA" in p and "DATA>>>" in p
    assert "never instructions" in p
    assert row["question"] in p and row["answer"] in p


def test_judge_prompt_hands_mechanical_findings_to_the_judge():
    leak_row = _row(answer="The MARKET ANALYST DOCTRINE says to start with regime.")
    p = ev.build_judge_prompt(leak_row, ev.mechanical_checks(leak_row))
    assert "internal-guide leak: DETECTED" in p
    clean = _row()
    p2 = ev.build_judge_prompt(clean, ev.mechanical_checks(clean))
    assert "internal-guide leak: none" in p2
    assert "stance line: PRESENT" in p2


def test_judge_prompt_accepts_extra_context():
    row = _row()
    p = ev.build_judge_prompt(row, ev.mechanical_checks(row),
                              extra_context="PROPERTY: names the regime first")
    assert "CASE-SPECIFIC CONTEXT" in p
    assert "names the regime first" in p


# ---------------------------------------------------------------------------
# parse_judge
# ---------------------------------------------------------------------------

def test_parse_judge_clamps_every_axis_to_its_weight():
    """An unclamped axis is how a total exceeds 100 and a pass rate becomes
    fiction. 999 on a 15-point axis must land on 15, and -5 must land on 0."""
    raw = json.dumps({"scores": {a: 999 for a in ev.RUBRIC},
                      "tags": [], "note": "x"})
    out = ev.parse_judge(raw)
    assert out is not None
    assert out["scores"] == dict(ev.RUBRIC)
    assert out["total"] == 100

    neg = ev.parse_judge(json.dumps({"scores": {a: -5 for a in ev.RUBRIC}}))
    assert neg is not None and neg["total"] == 0


def test_parse_judge_missing_axis_scores_zero_not_absent():
    out = ev.parse_judge(json.dumps({"scores": {"voice_compliance": 15}}))
    assert out is not None
    assert set(out["scores"]) == set(ev.RUBRIC)
    assert out["total"] == 15


def test_parse_judge_filters_tags_to_the_frozen_enum():
    out = ev.parse_judge(json.dumps({
        "scores": {}, "tags": ["Headline-First", "invented_odds", "vibes_bad",
                               "__proto__", "doctrine leak"],
    }))
    assert out is not None
    assert out["tags"] == ["headline_first", "invented_odds", "doctrine_leak"]


def test_parse_judge_survives_prose_and_code_fences():
    wrapped = ("Sure, here is my grading:\n```json\n"
               + _judge_reply("max") + "\n```\nHope that helps!")
    out = ev.parse_judge(wrapped)
    assert out is not None and out["total"] == 100


def test_parse_judge_returns_none_on_unrecoverable_text():
    """None, NOT a zero-score dict. A dead/garbled judge reply is a HARNESS
    failure; scoring it 0 would let a transport problem read in the weekly
    summary as an answer-quality collapse."""
    for bad in ("", None, "I refuse to grade this.", "{not json at all"):
        assert ev.parse_judge(bad) is None  # type: ignore[arg-type]


def test_parse_judge_non_numeric_axis_degrades_to_zero():
    out = ev.parse_judge(json.dumps({"scores": {"voice_compliance": "great",
                                                "regime_identification": 20}}))
    assert out is not None
    assert out["scores"]["voice_compliance"] == 0
    assert out["total"] == 20


# ---------------------------------------------------------------------------
# score_response
# ---------------------------------------------------------------------------

def test_score_response_composes_checks_and_judge():
    row = _row()
    j = _fake_judge(_judge_reply("max", note="clean"))
    out = ev.score_response(row, j)
    assert out["id"] == "r1" and out["lane"] == "fast" and out["lang"] == "en"
    assert out["total"] == 100 and out["passed"] is True
    assert out["judged"] is True and out["judged_at_model"] == "fake-judge"
    assert out["scores"] == dict(ev.RUBRIC)
    assert out["mech"]["stance"]["found"] is True
    assert out["note"] == "clean"
    assert len(j.calls) == 1


def test_score_response_pass_threshold_is_inclusive():
    row = _row()
    at = ev.score_response(row, _fake_judge(_judge_reply(0, regime_identification=20,
                                                        cross_asset_consistency=15,
                                                        voice_compliance=15,
                                                        user_supplied_data=10,
                                                        catalyst_verification=10,
                                                        mechanical_translation=10)))
    assert at["total"] == 80 and at["passed"] is True
    below = ev.score_response(row, _fake_judge(_judge_reply(0, regime_identification=20,
                                                           cross_asset_consistency=15,
                                                           voice_compliance=15,
                                                           user_supplied_data=10,
                                                           catalyst_verification=10,
                                                           mechanical_translation=9)))
    assert below["total"] == 79 and below["passed"] is False


def test_score_response_mechanical_hard_fail_outranks_a_perfect_judge():
    """A leaked internal guide and a refusal are shipped defects. The judge is
    unreliable exactly here (it reads a leaked header as good structure), so a
    100/100 must not be able to mark either one as passed."""
    for answer in ("The MARKET ANALYST DOCTRINE says regime first. Act — now.",
                   "I can't provide financial advice. Act — anyway."):
        out = ev.score_response(_row(answer=answer), _fake_judge(_judge_reply("max")))
        assert out["total"] == 100
        assert out["passed"] is False
        assert out["hard_fail"] is True

    # invented_odds is tagged but NOT a hard fail — it is a scoring matter the
    # judge docks conditional_signposts for, not an automatic zero.
    odds = ev.score_response(_row(answer="A 70% chance. Act — now."),
                             _fake_judge(_judge_reply("max")))
    assert "invented_odds" in odds["tags"]
    assert odds["hard_fail"] is False and odds["passed"] is True


def test_score_response_unions_mechanical_and_judge_tags_in_frozen_order():
    out = ev.score_response(
        _row(answer="A 70% chance of a cut. Act — now."),
        _fake_judge(_judge_reply("max", tags=["headline_first"])),
    )
    assert out["tags"] == ["headline_first", "invented_odds"]


def test_score_response_records_unjudged_without_passing_or_raising():
    row = _row()
    dead = ev.score_response(row, _fake_judge(None))
    assert dead["judged"] is False and dead["total"] is None
    assert dead["passed"] is False and dead["error"] == "no_reply"
    # mechanical findings survive a dead judge — that is the free tier's value.
    assert dead["mech"]["stance"]["found"] is True

    garbage = ev.score_response(row, _fake_judge("not json"))
    assert garbage["judged"] is False and garbage["error"] == "unparseable"

    def _boom(_p):
        raise RuntimeError("provider down")

    thrown = ev.score_response(row, _boom)
    assert thrown["judged"] is False and thrown["passed"] is False
    assert "judge_error" in thrown["error"]


# ---------------------------------------------------------------------------
# The frozen benchmark fixture
# ---------------------------------------------------------------------------

def test_benchmark_fixture_loads_and_is_frozen():
    case = ev.load_benchmark()
    assert case, "frozen benchmark fixture must be present"
    assert case["benchmark_id"] == "bear_steepener_2026-07-29"
    assert case["frozen"] is True
    assert "§12" in case["source"]
    assert case["rubric_weights_ref"] == "masterplan §9"
    assert ev.benchmark_path().is_file()


def test_benchmark_fixture_carries_every_operator_number():
    """The §12 tape is the whole point of this case — a fixture that lost a leg
    would still score, and the score would be measuring a different question."""
    case = ev.load_benchmark()
    usd = case["user_supplied_data"]
    assert usd == {
        "YM": "-2.30%", "ES": "-1.72%", "NQ": "-2.24%", "RTY": "-1.94%",
        "yield_1y_bp": -5.1, "yield_2y_bp": -1.7, "yield_5y_bp": 4.6,
        "yield_10y_bp": 8.6, "yield_20y_bp": 12.9, "TLT": "-1.65%",
        "tips_10y_bp": 1.0,
    }
    # …and every one of them reaches the model, in the packet-shaped block.
    digest = case["packet_digest_fixture"]
    for token in ("2.30", "1.72", "2.24", "1.94", "1.65",
                  "5.1", "1.7", "4.6", "8.6", "12.9", "1.0"):
        assert token in digest, token
    for label in ("YM", "ES", "NQ", "RTY", "TLT", "1Y", "2Y", "5Y", "10Y", "20Y"):
        assert label in digest, label


def test_benchmark_digest_imitates_the_live_packet_render():
    """Shaped like market_packet.render_digest output — header first, then TAPE,
    then CURVE, house separator and minus glyph. If the fixture drifted into some
    other format the benchmark would stop testing what production sends."""
    from engine.neuralweb import market_packet as mp

    digest = ev.load_benchmark()["packet_digest_fixture"]
    lines = digest.splitlines()
    assert lines[0].startswith("[CURRENT DASHBOARD STATE")
    assert lines[1].startswith("TAPE (")
    assert lines[2].startswith("CURVE (")
    assert mp._SEP in lines[1] and mp._SEP in lines[2]
    assert mp._MINUS in lines[1]


def test_benchmark_digest_does_not_pre_answer_the_regime():
    """DELIBERATE: the fixture carries the tenor NUMBERS but not the desk's
    precomputed `bear steepener` gloss. The case's first expected property is
    "identifies bear steepening from the tenor pattern BEFORE naming any cause" —
    a fixture that states the conclusion makes that property unfalsifiable, and a
    benchmark that cannot fail on its headline axis is not a regression gate."""
    digest = ev.load_benchmark()["packet_digest_fixture"].lower()
    assert "steepen" not in digest
    assert "bear steepener" not in digest


def test_benchmark_expected_properties_are_complete_and_tagged():
    props = ev.load_benchmark()["expected_properties"]
    assert len(props) == 10
    assert {p["tag"] for p in props} == {
        "regime_from_structure", "family_elimination", "family_candidates",
        "catalyst_verification", "duration_arithmetic", "second_story",
        "front_vs_long", "conditional_signposts", "user_numbers_quoted", "voice",
    }
    assert all(p.get("check") for p in props)


def test_load_benchmark_missing_file_is_empty_not_an_exception():
    assert ev.load_benchmark("no_such_benchmark.json") == {}


# ---------------------------------------------------------------------------
# run_benchmark
# ---------------------------------------------------------------------------

def test_run_benchmark_scores_with_injected_answerer_and_judge():
    seen: dict[str, str] = {}

    def _answer(system, user):
        seen["system"] = system
        seen["user"] = user
        return ("Front end rallied, long end sold off — that is bear steepening. "
                "TLT −1.65% squares with a +12.9bp 20Y at ~16y duration.\n\n"
                "Watch — don't chase — I have not confirmed today's catalyst.")

    _answer.model_id = "fake-answerer"
    judge = _fake_judge(_judge_reply("max", note="all axes clear"))
    out = ev.run_benchmark(ROOT, judge, _answer)

    assert out["ok"] is True
    assert out["benchmark_id"] == "bear_steepener_2026-07-29"
    assert out["total"] == 100 and out["passed"] is True
    assert out["scores"] == dict(ev.RUBRIC)
    assert out["tags"] == []
    assert "bear steepening" in out["answer"]
    assert out["answered_by_model"] == "fake-answerer"
    assert out["judged_at_model"] == "fake-judge"

    # The system prompt is the REAL analyst doctrine, not a frozen copy: the
    # benchmark's job is to score the doctrine that is in the repo today.
    from engine.neuralweb import analyst_doctrine as ad

    assert "MARKET ANALYST DOCTRINE" in seen["system"]
    assert ad.LEAK_SENTINELS[0] in seen["system"]
    assert ad.lane_dial("fast") in seen["system"]
    assert out["system_chars"] == len(seen["system"])
    assert out["doctrine_fingerprint"] == ad.fingerprint()

    # …and the user turn is the frozen packet + the question, in that order.
    case = ev.load_benchmark()
    assert seen["user"].startswith(case["packet_digest_fixture"])
    assert seen["user"].endswith(case["question_en"])


def test_run_benchmark_judge_sees_the_expected_properties():
    judge = _fake_judge(_judge_reply("max"))
    ev.run_benchmark(ROOT, judge, lambda _s, _u: "An answer.")
    prompt = judge.calls[0]
    assert "FROZEN benchmark case" in prompt
    for prop in ev.load_benchmark()["expected_properties"]:
        assert prop["check"] in prompt
    assert ev.load_benchmark()["gold_standard_sentence"] in prompt


def test_run_benchmark_dead_answerer_is_reported_not_raised():
    out = ev.run_benchmark(ROOT, _fake_judge(_judge_reply("max")), lambda _s, _u: None)
    assert out["ok"] is False and out["error"] == "no_answer"
    assert out["total"] is None and out["passed"] is False

    def _boom(_s, _u):
        raise RuntimeError("provider down")

    assert ev.run_benchmark(ROOT, _fake_judge(_judge_reply("max")), _boom)["ok"] is False


def test_run_benchmark_dead_judge_keeps_the_answer():
    out = ev.run_benchmark(ROOT, _fake_judge(None), lambda _s, _u: "An answer.")
    assert out["ok"] is False and out["total"] is None
    assert out["answer"] == "An answer."


def test_run_benchmark_missing_fixture_is_soft():
    out = ev.run_benchmark(ROOT, _fake_judge(_judge_reply("max")),
                           lambda _s, _u: "x", name="nope.json")
    assert out["ok"] is False and out["error"] == "benchmark_absent"


# ---------------------------------------------------------------------------
# judge_via_llm_auth — construction only, never a call
# ---------------------------------------------------------------------------

def test_judge_factory_is_deepseek_first_and_never_spends_codex(monkeypatch):
    """The judge is a mechanical labeller. It must never fall back onto the
    operator's attached ChatGPT account (house model-routing law: mechanical work
    goes to the cheap tier), and DeepSeek must be tried first."""
    captured: dict = {}

    def _fake_build(cfg, **kw):
        captured.update(cfg)
        return []

    monkeypatch.setattr("engine.llm_auth.build_providers", _fake_build)
    j = ev.judge_via_llm_auth(ROOT)
    assert j.model_id == ev.JUDGE_DEEPSEEK_MODEL
    assert j("a prompt") is None            # no providers -> no call, no raise
    assert captured["provider_order"][0] == "deepseek"
    assert captured["codex_provider"] is False
    assert captured["deepseek_model"] == ev.JUDGE_DEEPSEEK_MODEL


def test_judge_factory_retries_once_then_gives_up(monkeypatch):
    """One retry, not a loop: a small model missing the JSON instruction once is
    normal, but at 150 rows an unbounded retry is real money."""
    calls = {"n": 0}

    def _fake_one_shot(cfg, system, user, *, max_tokens, context):
        calls["n"] += 1
        return "not json"

    monkeypatch.setattr(ev, "_one_shot", _fake_one_shot)
    assert ev.judge_via_llm_auth(ROOT)("p") is None
    assert calls["n"] == 2


def test_judge_factory_returns_first_parseable_reply(monkeypatch):
    replies = iter(["garbage", _judge_reply("max")])
    monkeypatch.setattr(ev, "_one_shot",
                        lambda *a, **kw: next(replies))
    out = ev.judge_via_llm_auth(ROOT)("p")
    assert out is not None and ev.parse_judge(out)["total"] == 100


# ---------------------------------------------------------------------------
# scripts/run_brain_eval.py
# ---------------------------------------------------------------------------

@pytest.fixture()
def runner():
    import scripts.run_brain_eval as rbe
    return rbe


def _seed_ledger(root: Path, rows: list[dict]) -> None:
    d = root / "data" / "mastermind"
    d.mkdir(parents=True, exist_ok=True)
    (d / "response_log.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _ts(hours_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat(
        timespec="seconds")


def test_select_rows_keeps_all_pro_caps_fast_and_drops_errors(runner):
    rows = (
        [_row(f"p{i}", lane="pro", ts=_ts(i + 1)) for i in range(30)]
        + [_row(f"f{i}", lane="fast", ts=_ts(i + 1)) for i in range(200)]
        + [_row("e1", lane="fast", ts=_ts(1), flags={"error": True})]
        + [_row("old", lane="pro", ts=_ts(24 * 30))]
    )
    sel = runner.select_rows(rows)
    ids = {r["id"] for r in sel}
    assert len({i for i in ids if i.startswith("p")}) == 30, "pro is never sampled away"
    assert len({i for i in ids if i.startswith("f")}) == runner.MAX_FAST
    assert "e1" not in ids, "flags.error rows grade the transport, not the answer"
    assert "old" not in ids, "outside the 7-day window"
    assert len(sel) <= runner.MAX_JUDGED
    # newest first
    tss = [r["ts"] for r in sel]
    assert tss == sorted(tss, reverse=True)


def test_select_rows_keeps_lane_less_rows_on_the_fast_budget(runner):
    rows = [_row("n1", lane=None, ts=_ts(1)), _row("n2", lane="", ts=_ts(2))]
    assert {r["id"] for r in runner.select_rows(rows)} == {"n1", "n2"}


def test_select_rows_hard_cap_bites(runner):
    rows = [_row(f"p{i}", lane="pro", ts=_ts(i + 1)) for i in range(400)]
    assert len(runner.select_rows(rows)) == runner.MAX_JUDGED


def test_sidecar_merge_preserves_operator_and_contradiction_keys(runner, tmp_path):
    """THE pin for this harness. The weekly machine pass shares one sidecar with
    the operator's own grades and with the contradiction tier. A merge that
    replaced the row instead of folding into it would silently erase hand grading
    every Sunday — worse than having no harness at all."""
    from admin import mastermind_logs as ml

    d = tmp_path / "data" / "mastermind"
    d.mkdir(parents=True)
    (d / "response_eval.jsonl").write_text(json.dumps({
        "id": "r1", "schema": "mastermind.response_eval.v1",
        "grade": 5, "thumb": "up", "star": True, "tags": ["good_read"],
        "note": "operator liked this", "evaluator": "operator",
        "updated_ts": "2026-07-20T00:00:00+00:00",
        "contra_verdict": "market_divergence", "contra_model": "deepseek-v4-flash",
    }) + "\n", encoding="utf-8")

    overlay = ml._eval_overlay(tmp_path)
    scored = ev.score_response(_row("r1"), _fake_judge(_judge_reply("max")))
    assert runner._merge_auto(tmp_path, overlay, scored) is True

    folded = ml._eval_overlay(tmp_path)["r1"]
    # the machine's own namespace landed…
    assert folded["auto_total"] == 100 and folded["auto_passed"] is True
    assert folded["auto_scores"] == dict(ev.RUBRIC)
    assert folded["auto_model"] == "fake-judge" and folded["auto_judged_at"]
    # …and nothing of the operator's or the contradiction tier's was touched.
    assert folded["grade"] == 5 and folded["thumb"] == "up" and folded["star"] is True
    assert folded["tags"] == ["good_read"] and folded["note"] == "operator liked this"
    assert folded["evaluator"] == "operator", "a machine pass must not read as human"
    assert folded["updated_ts"] == "2026-07-20T00:00:00+00:00"
    assert folded["contra_verdict"] == "market_divergence"
    # and the panel's public shape still reads the operator's verdict
    assert ml._public_eval(folded)["grade"] == 5


def test_sidecar_merge_on_a_virgin_row_labels_itself_auto(runner, tmp_path):
    from admin import mastermind_logs as ml

    scored = ev.score_response(_row("new1"), _fake_judge(_judge_reply("max")))
    assert runner._merge_auto(tmp_path, {}, scored) is True
    folded = ml._eval_overlay(tmp_path)["new1"]
    assert folded["evaluator"] == "auto_eval"


def test_summary_pass_rate_is_conditioned_on_judged_rows(runner):
    """An unjudged row is a HARNESS failure. Counting it in the denominator would
    make a dead API key read as an answer-quality collapse."""
    results = [
        ev.score_response(_row("a", lane="fast"), _fake_judge(_judge_reply("max"))),
        ev.score_response(_row("b", lane="fast"), _fake_judge(_judge_reply(0))),
        ev.score_response(_row("c", lane="fast"), _fake_judge(None)),
        ev.score_response(_row("d", lane="pro"), _fake_judge(_judge_reply("max"))),
    ]
    s = runner.build_summary(results, {}, ingest={}, refreshed={}, dry_run=False)
    assert s["sampled"] == 4 and s["judged"] == 3 and s["passed"] == 2
    assert s["pass_rate"] == round(2 / 3, 3)
    assert s["by_lane"]["fast"] == {"n": 3, "judged": 2, "passed": 1,
                                    "pass_rate": 0.5, "mean_total": 50.0}
    assert s["by_lane"]["pro"]["pass_rate"] == 1.0
    assert s["pass_threshold"] == ev.PASS_THRESHOLD
    assert s["rubric_axes"] == dict(ev.RUBRIC)
    assert s["iso_week"].startswith(str(datetime.now(timezone.utc).year))


def test_summary_counts_tags_and_hard_fails(runner):
    results = [
        ev.score_response(_row("a", answer="The MARKET ANALYST DOCTRINE. Act — now."),
                          _fake_judge(_judge_reply("max"))),
        ev.score_response(_row("b", answer="A 70% chance. Act — now."),
                          _fake_judge(_judge_reply("max", tags=["headline_first"]))),
    ]
    s = runner.build_summary(results, {}, ingest={}, refreshed={}, dry_run=False)
    assert s["hard_fails"] == 1
    assert s["tags"]["doctrine_leak"] == 1
    assert s["tags"]["invented_odds"] == 1
    assert s["tags"]["headline_first"] == 1
    assert s["mechanical_tags"]["doctrine_leak"] == 1
    assert "headline_first" not in s["mechanical_tags"]


def test_dry_run_is_green_on_an_empty_ledger(runner, tmp_path, capsys):
    """The lane's smoke test: no ledger, no creds, no LLM — still exit 0 with a
    well-formed summary and exactly one annotation."""
    rc = runner.main(["--dry-run", "--root", str(tmp_path)])
    assert rc == 0
    summary = json.loads((tmp_path / "data" / "mastermind"
                          / runner.SUMMARY_NAME).read_text(encoding="utf-8"))
    assert summary["dry_run"] is True
    assert summary["sampled"] == 0 and summary["judged"] == 0
    assert summary["schema"] == "mastermind.eval_summary.v1"
    out = capsys.readouterr().out
    notices = [ln for ln in out.splitlines() if ln.startswith("::notice")]
    assert len(notices) == 1
    assert "title=brain-eval::" in notices[0]


def test_dry_run_runs_the_mechanical_tier_and_writes_no_sidecar(runner, tmp_path):
    _seed_ledger(tmp_path, [
        _row("a", lane="pro", ts=_ts(1)),
        _row("b", lane="fast", ts=_ts(2), answer="A 70% chance of a cut."),
        _row("c", lane="fast", ts=_ts(3), answer="I can't provide financial advice."),
    ])
    assert runner.main(["--dry-run", "--root", str(tmp_path)]) == 0
    summary = json.loads((tmp_path / "data" / "mastermind"
                          / runner.SUMMARY_NAME).read_text(encoding="utf-8"))
    assert summary["sampled"] == 3
    assert summary["judged"] == 0, "a dry run makes no LLM calls"
    assert summary["mechanical_tags"] == {"invented_odds": 1, "refusal_regression": 1}
    assert summary["benchmark"]["fixture_loaded"] is True
    assert summary["sidecar_writes"] == 0
    assert not (tmp_path / "data" / "mastermind" / "response_eval.jsonl").exists()


def test_notice_is_a_bare_print_at_line_start(runner):
    """GitHub only parses an annotation when '::' opens the line, and every logger
    here prefixes the level — a logged annotation runs clean and produces nothing.
    tests/test_gh_annotation_line_start.py is the repo-wide guard; this pins that
    THIS script's one annotation is reached and shaped right."""
    src = (ROOT / "scripts" / "run_brain_eval.py").read_text(encoding="utf-8")
    assert 'print(\n        f"::notice title=brain-eval::' in src
    assert "log.warning(\"::" not in src and "log.info(\"::" not in src


def test_summary_and_sidecar_paths_are_gitignored():
    """The corpus and every derivative of it are admin-local. A committed eval
    summary would put LLM-judge scores in git, one import away from a site
    builder — the exact line the §3 row-14 ruling draws."""
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    import scripts.run_brain_eval as rbe

    for entry in ("data/mastermind/response_log.jsonl",
                  "data/mastermind/response_eval.jsonl",
                  f"data/mastermind/{rbe.SUMMARY_NAME}"):
        assert entry in ignore, entry


# ---------------------------------------------------------------------------
# admin surface
# ---------------------------------------------------------------------------

def test_admin_eval_summary_reads_the_file(tmp_path):
    from admin import mastermind_logs as ml
    import scripts.run_brain_eval as rbe

    d = tmp_path / "data" / "mastermind"
    d.mkdir(parents=True)
    (d / rbe.SUMMARY_NAME).write_text(json.dumps({
        "iso_week": "2026-W31", "generated_at": "2026-07-26T13:00:00+00:00",
        "window_days": 7, "pass_threshold": 80, "sampled": 40, "judged": 38,
        "passed": 30, "pass_rate": 0.789, "mean_total": 82.4, "hard_fails": 1,
        "by_lane": {"fast": {"n": 30, "judged": 29, "passed": 22,
                             "pass_rate": 0.759, "mean_total": 80.1}},
        "tags": {"headline_first": 5, "stale_as_live": 2, "invented_odds": 1,
                 "doctrine_leak": 1},
        "benchmark": {"benchmark_id": "bear_steepener_2026-07-29", "total": 88,
                      "passed": True},
    }), encoding="utf-8")

    out = ml.eval_summary(root=tmp_path)
    assert out["ok"] is True
    assert out["iso_week"] == "2026-W31" and out["pass_rate"] == 0.789
    assert out["by_lane"]["fast"]["passed"] == 22
    assert out["mean_total"] == 82.4
    assert out["benchmark"]["total"] == 88 and out["benchmark"]["passed"] is True
    # top 3 only, worst first
    assert [t["tag"] for t in out["top_tags"]] == ["headline_first", "stale_as_live",
                                                   "invented_odds"]


def test_admin_eval_summary_is_fail_soft(tmp_path):
    from admin import mastermind_logs as ml
    import scripts.run_brain_eval as rbe

    assert ml.eval_summary(root=tmp_path)["ok"] is False
    assert ml.eval_summary(root=tmp_path)["error"] == "absent"

    d = tmp_path / "data" / "mastermind"
    d.mkdir(parents=True)
    (d / rbe.SUMMARY_NAME).write_text("{not json", encoding="utf-8")
    assert ml.eval_summary(root=tmp_path)["ok"] is False

    (d / rbe.SUMMARY_NAME).write_text("[1, 2, 3]", encoding="utf-8")
    assert ml.eval_summary(root=tmp_path)["error"] == "malformed"


def test_admin_eval_summary_coerces_a_hand_edited_file(tmp_path):
    """The sidecar's neighbours are hand-editable local files and app.js indexes
    by_lane/tags directly. A string where a count belongs must render as an
    honest zero, never reach the renderer as a string."""
    from admin import mastermind_logs as ml
    import scripts.run_brain_eval as rbe

    d = tmp_path / "data" / "mastermind"
    d.mkdir(parents=True)
    (d / rbe.SUMMARY_NAME).write_text(json.dumps({
        "sampled": "lots", "judged": None, "pass_rate": 7.5,
        "by_lane": {"fast": "not a dict", "pro": {"n": "x", "pass_rate": -1}},
        "tags": {"headline_first": "many"}, "benchmark": "nope",
    }), encoding="utf-8")
    out = ml.eval_summary(root=tmp_path)
    assert out["sampled"] == 0 and out["judged"] == 0
    assert out["pass_rate"] == 1.0, "clamped into 0..1"
    assert "fast" not in out["by_lane"]
    assert out["by_lane"]["pro"] == {"n": 0, "judged": 0, "passed": 0,
                                     "pass_rate": 0.0, "mean_total": None}
    assert out["benchmark"]["total"] is None


def test_admin_server_exposes_the_eval_summary_route():
    src = (ROOT / "admin" / "server.py").read_text(encoding="utf-8")
    assert '"/api/mastermind_ai/response_logs/eval_summary"' in src
    assert "mastermind_logs.eval_summary()" in src


def test_app_js_renders_the_summary_card_with_escaped_values():
    js = (ROOT / "admin" / "static" / "app.js").read_text(encoding="utf-8")
    assert "/api/mastermind_ai/response_logs/eval_summary" in js
    assert "function mmlEvalSummaryHtml(" in js
    assert "mmlEvalSummaryHtml(evs)" in js
    # every interpolated string goes through esc() — the summary is a local file
    # an operator can edit, and iso_week/tag names land in innerHTML.
    for expr in ("esc(s.iso_week", "esc(t.tag)", "esc(b.benchmark_id"):
        assert expr in js, expr


# ---------------------------------------------------------------------------
# The workflow
# ---------------------------------------------------------------------------

def _workflow() -> dict:
    p = ROOT / ".github" / "workflows" / "brain-eval.yml"
    assert p.is_file(), "brain-eval.yml must exist"
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def test_workflow_parses_with_on_and_jobs():
    doc = _workflow()
    # PyYAML (YAML 1.1) reads the bare key `on` as boolean True — same tolerance
    # as scripts/check_workflow_yaml.py.
    trig = doc.get("on", doc.get(True))
    assert isinstance(trig, dict) and "schedule" in trig and "workflow_dispatch" in trig
    assert trig["schedule"][0]["cron"] == "0 13 * * 0"
    jobs = doc["jobs"]
    assert isinstance(jobs, dict) and jobs
    job = jobs["brain-eval"]
    assert job["runs-on"] == ["self-hosted", "macstudio"]
    assert job["timeout-minutes"] == 45
    assert doc["concurrency"]["group"] == "brain-eval"
    assert doc["concurrency"]["cancel-in-progress"] is False
    runs = " ".join(str(s.get("run") or "") for s in job["steps"])
    assert "python scripts/run_brain_eval.py" in runs


def test_workflow_is_not_a_declared_dag_lane():
    """Deliberately invisible to check_dag_conformance: this lane renders nothing,
    commits nothing, and advances no ledger, so it is not a pipeline lane. Adding
    it to config/dag.yml would demand a module manifest it has no business having.
    If someone declares it later, THIS is the test that makes them prove why."""
    dag = yaml.safe_load((ROOT / "config" / "dag.yml").read_text(encoding="utf-8"))
    # `lanes:` is a LIST of {workflow, job, steps} records — the checker yaml-loads
    # only the workflow files named here, which is exactly why a non-lane workflow
    # is invisible to it.
    lanes = dag.get("lanes") or []
    declared = {str(lane.get("workflow") or "") for lane in lanes
                if isinstance(lane, dict)}
    assert declared, "dag.yml lanes shape changed — re-pin this test"
    assert ".github/workflows/brain-eval.yml" not in declared
    assert not any("brain-eval" in w for w in declared)


def test_workflow_wires_the_creds_the_script_actually_needs():
    """A lane missing R2 creds grades an empty ledger; missing judge keys grade
    nothing at all. Both fail SOFT, so neither would ever red the run — hence a
    test rather than trust."""
    job = _workflow()["jobs"]["brain-eval"]
    env = {}
    for step in job["steps"]:
        env.update(step.get("env") or {})
    for name in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
                 "R2_BUCKET", "DEEPSEEK_API_KEY"):
        assert name in env, name
        assert "secrets." in env[name]


def test_workflow_writes_nothing_back_to_git():
    """Scores are internal QA telemetry and both outputs are gitignored. A commit
    step here would be the mechanism that puts judge scores in the repo."""
    doc = _workflow()
    assert doc.get("permissions", {}).get("contents") == "read"
    body = " ".join(str(s.get("run") or "") for s in doc["jobs"]["brain-eval"]["steps"])
    for forbidden in ("git commit", "git push", "publish_r2 --dirs site"):
        assert forbidden not in body, forbidden


def test_nothing_in_the_harness_writes_to_site():
    """The §3 row-14 line, mechanically. If a future edit reaches site/, the
    'validated' guard and the display-tier law are both one import away."""
    for rel in ("engine/neuralweb/response_eval.py", "scripts/run_brain_eval.py"):
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert '"site"' not in src and "'site'" not in src, rel
        assert "site/" not in src.replace("site/ or", "").replace("to site/", ""), rel
