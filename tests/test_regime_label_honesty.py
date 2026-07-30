"""Regime-label honesty invariants (engine/playbook.py, engine/master_brain.py).

Pins the fixes for four proven defects found by adversarial audit 2026-07-29:

1. ASSERTED QUAD GLOSS. `QUAD_MEANING["Q1"]` — "Goldilocks — growth improving while
   inflation cools" — was emitted for the sticky label regardless of the axis values.
   On 2026-07-29 the label was Q1 with growth −0.133 (deteriorating) and inflation
   +0.400 (rising): BOTH clauses false, Stagflation on the raw rule. `raw_quad != quad`
   on ~44% of sessions since 2000, so this was not a rare edge.
2. RAW ENGLISH SLUG IN ZH COPY. The trigger builder emitted
   "…若其反转，growth 信号将翻转。" — an untranslated axis name inside 中文 prose.
3. BRIEF PROSE CONTRADICTING THE DETERMINISTIC ROW. The LLM brief context carried
   quad/axes/flip_condition but NOT quad_vector, so the brief wrote "could tip into
   Reflation" while the transition row had the odds drifting toward Stagflation.
4. TWO NAMES FOR ONE OBJECT IN ZH. The chip rail rendered Goldilocks as
   "金发姑娘(不冷不热)" and the translated prose used "金发姑娘" / "制度" / "整体机制",
   while the house lexicon (engine/i18n.py LEX) is 理想增长 and 周期.

No network, no disk writes, no LLM calls.

Run as a plain script:  python tests/test_regime_label_honesty.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import master_brain as mb  # noqa: E402
from engine import playbook as pb  # noqa: E402
from engine.i18n import LEX  # noqa: E402


# --------------------------------------------------------------------------- #
# 1. the quad gloss must follow the axes, not the label
# --------------------------------------------------------------------------- #

def test_gloss_is_canonical_when_the_label_agrees():
    m = pb.quad_meaning_for("Q1", growth=0.40, inflation=-0.40)
    assert m["canonical"] is True
    assert m["en"] == pb.QUAD_MEANING["Q1"]
    assert m["zh"] == pb.QUAD_MEANING_ZH["Q1"]


def test_gloss_refuses_to_assert_a_contradicted_direction():
    """The live 2026-07-29 shape: label Q1, growth −0.133, inflation +0.400 -> Q3 raw."""
    m = pb.quad_meaning_for("Q1", growth=-0.133, inflation=0.400)
    assert m["canonical"] is False
    en = m["en"]
    assert "growth improving" not in en, "must not assert a direction the axes contradict"
    assert "inflation cools" not in en
    assert "-0.13" in en and "+0.40" in en, "the actual readings must be printed"
    assert "deteriorating" in en and "rising" in en
    assert "Stagflation" in en, "the raw-rule quad must be named"
    assert "Goldilocks" in en, "the confirmed label must still be named"
    # ZH pair carries the same content in the house lexicon
    zh = m["zh"]
    assert LEX["Goldilocks"] in zh and LEX["Stagflation"] in zh
    assert "增长走弱" in zh and "通胀上行" in zh
    assert "growth" not in zh and "inflation" not in zh, "no raw EN slug in ZH copy"


def test_gloss_uses_the_supplied_raw_quad_when_given():
    m = pb.quad_meaning_for("Q1", growth=-0.1, inflation=0.1, raw_quad="Q3")
    assert m["canonical"] is False and "Stagflation" in m["en"]
    # and derives it identically when not supplied
    assert pb.quad_meaning_for("Q1", growth=-0.1, inflation=0.1)["en"] == m["en"]


def test_gloss_falls_back_to_canonical_without_axis_values():
    for m in (pb.quad_meaning_for("Q2"),
              pb.quad_meaning_for("Q2", growth=None, inflation=0.4),
              pb.quad_meaning_for("Q2", growth=0.4, inflation=None)):
        assert m["canonical"] is True and m["en"] == pb.QUAD_MEANING["Q2"]


def test_every_quad_glosses_in_both_languages():
    for q in ("Q1", "Q2", "Q3", "Q4"):
        agree = {"Q1": (0.4, -0.4), "Q2": (0.4, 0.4),
                 "Q3": (-0.4, 0.4), "Q4": (-0.4, -0.4)}[q]
        m = pb.quad_meaning_for(q, *agree)
        assert m["canonical"] is True and m["en"] and m["zh"]
        # a contradicted variant is always expressible in both languages too
        bad = pb.quad_meaning_for(q, -agree[0] or 0.4, -agree[1] or 0.4)
        assert bad["en"] and bad["zh"]


# --------------------------------------------------------------------------- #
# 2. no untranslated axis slug in the ZH trigger lines
# --------------------------------------------------------------------------- #

def _lines(flip, pending=None):
    return pb._trigger_lines({}, flip, pending, None)


def test_zh_trigger_line_translates_the_axis_name():
    flip = {"axis": "growth", "component": "iwm_spy", "z": -0.45,
            "label_unsupported": False}
    (en, zh), = _lines(flip)
    assert "the growth signal flips" in en
    assert "growth" not in zh, "raw EN axis slug leaked into ZH copy"
    assert pb.AXIS_ZH["growth"] + "信号将翻转" in zh


def test_zh_trigger_line_translates_the_inflation_axis_too():
    flip = {"axis": "inflation", "component": "oil_trend", "z": 0.5,
            "label_unsupported": False}
    (en, zh), = _lines(flip)
    assert "inflation" not in zh
    assert pb.AXIS_ZH["inflation"] in zh


def test_unsupported_label_line_replaces_the_weakest_supporter_line():
    """When the label's own axes contradict it, the trigger row must name that —
    not caption anti-evidence as 'the most fragile support'."""
    flip = {"axis": "growth", "component": None, "label_unsupported": True,
            "displayed_quad": "Q1", "raw_quad": "Q3",
            "pending_quad": "Q3", "pending_days": 3, "pending_need": 7}
    (en, zh), = _lines(flip)
    assert "most fragile support" not in en
    assert "no longer support" in en
    assert "Stagflation" in en and "Goldilocks" in en
    assert "3 of 7 confirmation days" in en
    assert LEX["Stagflation"] in zh and LEX["Goldilocks"] in zh
    assert "3/7" in zh


def test_countdown_is_not_printed_twice():
    """The pending line and the unsupported-label line both know about the countdown;
    only one of them may say it, or a 4-line list wastes two lines on one fact."""
    flip = {"axis": "growth", "component": None, "label_unsupported": True,
            "displayed_quad": "Q1", "raw_quad": "Q3",
            "pending_quad": "Q3", "pending_days": 3, "pending_need": 7}
    pending = {"quad": "Q3", "days": 3, "need": 7}
    lines = _lines(flip, pending)
    assert len(lines) == 2, "expected the pending line plus the unsupported-label line"
    joined_en = " ".join(en for en, _zh in lines)
    assert joined_en.count("3 of 7 confirmation days done") == 1
    joined_zh = " ".join(zh for _en, zh in lines)
    assert joined_zh.count("3/7") == 1
    # the countdown IS restated when the pending line is absent
    solo, = _lines(flip, None)
    assert "3 of 7 confirmation days done" in solo[0]


def test_axis_zh_and_posture_zh_match_the_house_lexicon():
    for posture, zh in pb.POSTURE_ZH.items():
        assert LEX[posture] == zh, f"{posture} diverges from engine/i18n.py LEX"


# --------------------------------------------------------------------------- #
# 3. transition direction reaches the brief context
# --------------------------------------------------------------------------- #

_MACRO = {
    "date": "2026-07-29", "quad": "Q1", "quad_name": "Goldilocks",
    "transition_state": "TRANSITIONING",
    "flip_condition": {"axis": "growth", "component": None},
    "quad_vector": {
        "degraded": False,
        "transition_momentum": {"gaining": "Q3", "gaining_rate": 0.012,
                                "losing": "Q1", "losing_rate": -0.015,
                                "window_sessions": 5},
    },
}


def test_regime_path_carries_transition_momentum():
    rp = mb._build_regime_path(_MACRO, root=None)
    tm = rp.get("transition_momentum")
    assert tm is not None, "the brief context had no transition-direction producer"
    assert tm["gaining"] == "Q3" and tm["losing"] == "Q1"
    assert tm["gaining_rate"] == 0.012 and tm["window_sessions"] == 5
    assert tm["degraded"] is False
    assert "TRANSITION DIRECTION MUST COME FROM HERE" in tm["_instruction"]


def test_regime_path_omits_momentum_when_absent_or_empty():
    for qv in (None, {}, {"transition_momentum": None},
               {"transition_momentum": {}}, {"transition_momentum": {"gaining": None}}):
        m = dict(_MACRO, quad_vector=qv)
        assert "transition_momentum" not in mb._build_regime_path(m, root=None)


def test_regime_path_marks_a_degraded_direction_read():
    m = dict(_MACRO, quad_vector=dict(_MACRO["quad_vector"], degraded=True))
    tm = mb._build_regime_path(m, root=None)["transition_momentum"]
    assert tm["degraded"] is True
    assert "degraded" in tm["_instruction"]


def test_system_prompt_binds_transition_direction_to_the_deterministic_row():
    law = mb._REGIME_MAP_LAW
    assert "transition_momentum" in law
    assert "gaining" in law
    for tmpl in (mb.MASTER_SYSTEM_TMPL, mb.CHINA_SYSTEM_TMPL, mb.BTC_SYSTEM_TMPL):
        assert "transition_momentum" in tmpl


def test_drift_is_stamped_with_the_parquet_vintage(tmp_path):
    """The drift is read off the history parquet, whose tail can lag the brief by a
    session — on 2026-07-29 the brief was stamped 07-29 against an 07-28 tail with no
    as-of at all."""
    import pandas as pd
    idx = pd.bdate_range("2026-06-01", periods=30)
    df = pd.DataFrame({"growth_score": [0.1] * 29 + [-0.133],
                       "inflation_score": [0.2] * 29 + [0.400]}, index=idx)
    p = tmp_path / "regime_history.parquet"
    df.to_parquet(p)
    d = mb._regime_path_drift(p)
    assert d, "drift should be produced for a well-formed history"
    assert d["asof"] == str(idx[-1].date())
    assert d["vs_5d_asof"] == str(idx[-6].date())
    assert d["vs_20d_asof"] == str(idx[-21].date())
    assert "may lag the brief" in d["_asof_note"]


def test_drift_stays_fail_open_on_a_missing_file(tmp_path):
    assert mb._regime_path_drift(tmp_path / "nope.parquet") == {}


# --------------------------------------------------------------------------- #
# 4. one ZH name per object
# --------------------------------------------------------------------------- #

def test_chip_rail_uses_the_house_lexicon_for_the_quad():
    en, zh, _tone = mb._quad_display("Goldilocks", shifting=False)
    assert en == "Goldilocks"
    assert zh == LEX["Goldilocks"] == "理想增长"
    assert "金发姑娘" not in zh, "retired second translation of Goldilocks"
    for name in ("Reflation", "Stagflation"):
        _e, z, _t = mb._quad_display(name, shifting=False)
        assert z == LEX[name]


def test_chip_rail_shifting_suffix_survives_the_lexicon_change():
    en, zh, tone = mb._quad_display("Goldilocks", shifting=True)
    assert en.endswith(" · shifting") and zh.endswith(" · 转换中")
    assert zh.startswith(LEX["Goldilocks"]) and tone == "warn"


def test_zh_lexicon_normalizer_routes_translator_output_to_house_terms():
    cases = {
        "当前处于金发姑娘(不冷不热)状态": "理想增长",
        "当前处于金发姑娘（不冷不热）状态": "理想增长",
        "这是金发姑娘式的组合": "理想增长",
        "宏观处于金发姑娘阶段": "理想增长",
        "整体机制保持稳定": "周期",
        "宏观制度未变": "宏观周期",
        "该制度已持续数月": "该周期",
    }
    for src, expect in cases.items():
        out = mb._normalize_zh_lexicon(src)
        assert expect in out, f"{src!r} -> {out!r}"
        assert "金发姑娘" not in out
        assert "整体机制" not in out


def test_zh_lexicon_normalizer_is_a_no_op_on_clean_and_empty_input():
    clean = "理想增长周期仍在延续，增长改善、通胀降温。"
    assert mb._normalize_zh_lexicon(clean) == clean
    for v in (None, "", 42, ["x"]):
        assert mb._normalize_zh_lexicon(v) == v


def test_zh_lexicon_fixups_are_ordered_longest_specific_first():
    """A short form must not eat the tail of a longer one it is a prefix of."""
    fixups = mb._ZH_LEXICON_FIXUPS
    for i, (bad, _good) in enumerate(fixups):
        for later_bad, _lg in fixups[i + 1:]:
            assert not later_bad.startswith(bad) or later_bad == bad, (
                f"{later_bad!r} is unreachable — {bad!r} matches its prefix first")


if __name__ == "__main__":
    import tempfile

    fns = [(k, v) for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for name, fn in fns:
        if "tmp_path" in fn.__code__.co_varnames[:fn.__code__.co_argcount]:
            with tempfile.TemporaryDirectory() as d:
                fn(Path(d))
        else:
            fn()
        print(f"ok  {name}")
    print(f"\n{len(fns)} passed")
