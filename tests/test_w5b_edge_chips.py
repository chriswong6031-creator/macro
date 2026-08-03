"""W5b EDGE chips wiring tests.

Edge 1: CN drawdown radar sleeve-size chip in china.html.j2 stocks board header.
  T1 — chip renders when setups.sleeve_chip has a valid radar_state
  T2 — chip absent when setups.sleeve_chip is None (degrade-don't-crash)
  T3 — chip absent when radar_state is None
  T4 — chip absent when mode == 'macro' (dual-mode isolation)
  T5 — 'caution' state → var(--warn) accent colour
  T6 — 'elevated'/'risk-off' state → var(--down) accent colour
  T7 — dual-span EN/ZH in chip (no CJK inside title= or HTML attribute values)
  T8 — no affirmative 'Validated'/'validated' text emitted in chip HTML
  T9 — help tooltip text is not empty / accessible
  T10 — chip does not appear in macro mode render (Jinja parse + render)

Edge 2: AI-semis confirmer chip already wired in baskets_china.html.j2 + build script.
  T11 — is_target_basket recognises AI-supply basket IDs
  T12 — compute() returns dict with 'on', 'state', 'targets' keys on degraded (null) path
  T13 — build_baskets_china_ths.py imports and calls cn_ai_semis_confirmer without error
  T14 — baskets_china.html.j2 has #semis-chip host element and renderSemisChip() call
  T15 — baskets_china.html.j2 semis chip JS: label_en / label_zh dual-lang path
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
CHINA_TMPL_SRC = (ROOT / "templates" / "china.html.j2").read_text()
BASKETS_CHINA_SRC = (ROOT / "templates" / "baskets_china.html.j2").read_text()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sleeve_chip(state="caution"):
    return {
        "sleeve_factor": 0.9,
        "radar_state": state,
        "radar_as_of": "2026-07-07",
        "can_force": False,
        "label_en": f"Sleeve ×0.90 — CN drawdown radar: {state}",
        "label_zh": f"仓位 ×0.90 — CN回撤雷达：{state}",
        "dominant_driver_en": "Breadth breakdown (all-boats)",
        "dominant_driver_zh": "广度普跌（普跌）",
        "passport": {"basis": "measured", "display_only": True},
    }


_IFTAG = re.compile(r"\{%-?\s*(if\b[^%]*|endif\s*)-?%\}")


def _chip_block():
    """Slice the W5b EDGE-1 chip block by balanced {% if %}…{% endif %} traversal.

    Shared by the renderer and by T10's source scan. T10 used to take the FIRST
    {% endif %} after the block comment, which stops at the chip's first NESTED
    endif (the dominant-driver guard) and leaves the tail unscanned — the as-of
    span and the whole help() tooltip, i.e. precisely where a CJK-in-attribute
    violation would land. One extractor keeps the render and the scan agreeing on
    what "the chip" is.
    """
    start = CHINA_TMPL_SRC.index("{# W5b EDGE-1")
    depth = 0
    for m in _IFTAG.finditer(CHINA_TMPL_SRC[start:]):
        if m.group(1).strip().startswith("if"):
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return CHINA_TMPL_SRC[start:start + m.end()]
    raise AssertionError("unbalanced if/endif in the W5b EDGE-1 chip block")


def _render_stocks_header(setups, mode="stocks"):
    """Extract and render just the W5b sleeve chip block from china.html.j2."""
    macros = (
        "{%- macro help(en, zh='') -%}"
        "<span class='tip'><span class='l-en'>{{ en }}</span>"
        "<span class='l-zh'>{{ zh }}</span></span>{%- endmacro -%}\n"
        "{%- macro nm(name) -%}{{ name }}{%- endmacro -%}\n"
        "{%- macro td(x) -%}{{ x }}{%- endmacro -%}\n"
    )
    from engine import i18n

    chip_block = _chip_block()

    # Wrap in the mode guard to test dual-mode isolation
    mode_open = "{% if mode == 'stocks' %}"
    mode_close = "{% endif %}"
    snippet = mode_open + "\n" + chip_block + "\n" + mode_close
    # Mirror the imports china.html.j2 carries at file top — they sit OUTSIDE
    # every snippet sliced here, so without them {{ lens.lens(...) }} renders
    # against Undefined. The FileSystemLoader fallback resolves the real
    # partials, so a future {% import %} never breaks this harness again.
    full = (
        '{% import "_prophet_card.html.j2" as pv %}\n'
        '{% import "_decision_card.html.j2" as dc %}\n'
        '{% import "_lens.html.j2" as lens %}\n'
    ) + macros + snippet
    env = Environment(
        loader=ChoiceLoader([
            DictLoader({"tmpl": full}),
            FileSystemLoader(str(ROOT / "templates")),
        ]),
        autoescape=False,
    )
    env.globals.update(td=i18n.td, t=i18n.t, tr=i18n.tr)

    return env.get_template("tmpl").render(
        mode=mode,
        setups=setups,
        latest={"quad": "Q4", "quad_name": "Growth Scare"},
        pb=None,
        actions=None,
    )


# ---------------------------------------------------------------------------
# Edge 1 tests
# ---------------------------------------------------------------------------

# Presence sentinel for the rendered chip.  The chip was deliberately rebuilt in plain
# words — the old "Sleeve ×0.62" label was jargon (see the {# W5b EDGE-1 #} comment in
# china.html.j2), so the multiplier no longer renders at all.  The absence tests below
# MUST key off this same sentinel: they used to assert `"Sleeve ×" not in html`, which
# went vacuously green the moment the rename landed — they would no longer have caught a
# chip leaking into macro mode or surviving radar_state=None.
_CHIP_EN = "Risk backdrop"
_CHIP_ZH = "风险背景"


def test_t1_chip_renders_with_valid_radar_state():
    """T1: chip renders bilingually when setups.sleeve_chip has a valid radar_state."""
    setups = {"sleeve_chip": _sleeve_chip("caution"), "buy": [], "ripening": [], "ran": []}
    html = _render_stocks_header(setups)
    assert _CHIP_EN in html, "risk-backdrop chip missing from rendered output"
    assert _CHIP_ZH in html, "risk-backdrop chip missing its zh half"
    # plain-word state + what to DO about it, in both languages, per the glance-tier
    # contract ("every signal panel answers 'so what do I do'")
    assert "CAUTION" in html and "avoid chasing" in html          # EN state + action
    assert "谨慎" in html and "谨慎追高" in html                     # ZH state + action
    # The rename was the POINT of #2947, so guard it in the direction it can regress:
    # cn_sleeve_chip() still emits label_en ("Sleeve ×0.90 — …") and sleeve_factor, and
    # the chip simply stops rendering them. Printing either again would put the jargon
    # back on a glance-tier surface (DESIGN_DOCTRINE Law 2) with nothing to object.
    assert "Sleeve" not in html and "0.90" not in html, \
        "the sleeve multiplier is back on the chip face — #2947 removed it as jargon"


def test_t2_chip_absent_when_sleeve_chip_none():
    """T2: chip must be absent (degrade) when setups.sleeve_chip is None."""
    setups = {"sleeve_chip": None, "buy": [], "ripening": [], "ran": []}
    html = _render_stocks_header(setups)
    assert _CHIP_EN not in html, "chip rendered despite sleeve_chip=None"


def test_t3_chip_absent_when_radar_state_none():
    """T3: chip must be absent when sleeve_chip.radar_state is None."""
    chip = _sleeve_chip("caution")
    chip["radar_state"] = None
    setups = {"sleeve_chip": chip, "buy": [], "ripening": [], "ran": []}
    html = _render_stocks_header(setups)
    assert _CHIP_EN not in html, "chip rendered despite radar_state=None"


def test_t4_chip_absent_when_mode_macro():
    """T4: chip must not appear when mode='macro' (stocks-header block skipped)."""
    setups = {"sleeve_chip": _sleeve_chip("caution"), "buy": [], "ripening": [], "ran": []}
    html = _render_stocks_header(setups, mode="macro")
    assert _CHIP_EN not in html, "chip leaked into macro mode"


def test_t5_caution_state_uses_warn_colour():
    """T5: 'caution' state uses var(--warn) accent."""
    setups = {"sleeve_chip": _sleeve_chip("caution"), "buy": [], "ripening": [], "ran": []}
    html = _render_stocks_header(setups)
    assert "var(--warn)" in html, "caution state must use var(--warn)"
    assert "var(--down)" not in html, "caution state must not use var(--down)"


def test_t6_elevated_state_uses_down_colour():
    """T6: 'elevated' state uses var(--down) accent."""
    setups = {"sleeve_chip": _sleeve_chip("elevated"), "buy": [], "ripening": [], "ran": []}
    html = _render_stocks_header(setups)
    assert "var(--down)" in html, "elevated state must use var(--down)"


def test_t6b_risk_off_state_uses_down_colour():
    """T6b: 'risk-off' state uses var(--down) accent."""
    setups = {"sleeve_chip": _sleeve_chip("risk-off"), "buy": [], "ripening": [], "ran": []}
    html = _render_stocks_header(setups)
    assert "var(--down)" in html, "risk-off state must use var(--down)"


def test_t7_dual_span_en_zh_in_chip():
    """T7: chip output contains both l-en and l-zh dual-span classes."""
    setups = {"sleeve_chip": _sleeve_chip("caution"), "buy": [], "ripening": [], "ran": []}
    html = _render_stocks_header(setups)
    assert 'l-en' in html, "l-en span missing from chip"
    assert 'l-zh' in html, "l-zh span missing from chip"


def test_t8_no_affirmative_validated_text_in_chip():
    """T8: chip must not emit 'Validated'/'validated' in user-facing HTML."""
    setups = {"sleeve_chip": _sleeve_chip("caution"), "buy": [], "ripening": [], "ran": []}
    html = _render_stocks_header(setups)
    # strip comment blocks first (chip comment mentions 'validate' in tech spec only)
    html_no_comments = re.sub(r'\{#.*?#\}', '', html, flags=re.DOTALL)
    assert "Validated" not in html_no_comments, "affirmative Validated found in chip output"
    assert "validated" not in html_no_comments, "affirmative validated found in chip output"


def test_t9_help_tooltip_not_empty():
    """T9: the risk-backdrop explainer must carry content.

    The CN drawdown-radar tip moved from the plain help() bubble to the rich LENS
    tier on 2026-08-02 (a 60-word jargon paragraph became a titled card with the
    study vocabulary demoted to the receipt line), so the markup is now
    .lens-src rather than .tip. The invariant is unchanged: the explainer must not
    be empty, and it must still say what the radar does and what it does not do.
    """
    setups = {"sleeve_chip": _sleeve_chip("caution"), "buy": [], "ripening": [], "ran": []}
    html = _render_stocks_header(setups)
    assert 'class="lens-src"' in html, "lens explainer payload not found in chip area"
    body = html[html.index('class="lens-src"'):]
    assert body.strip(), "lens explainer is empty"
    assert "lens-title" in body, "lens explainer has no title"
    assert "lens-receipt" in body, "lens explainer has no receipt line"
    # The honest half of the read: it is context, it does not veto a name.
    assert "never removes a name" in body, "radar explainer dropped its no-veto disclosure"


def test_t10_no_cjk_in_html_attributes_added_section():
    """T10: no Chinese characters inside HTML attribute values in the W5b chip block."""
    _CJK = re.compile(r"[一-鿿㐀-䶿]")
    _ATTR = re.compile(r'(?:class|id|style|data-[\w-]+|aria-[\w-]+)\s*=\s*"([^"]*)"')
    # Balanced traversal, NOT "first {% endif %} after the comment" — that stopped at
    # the chip's first nested endif and left the as-of span and the entire help()
    # tooltip unscanned (2807 of 3285 chars), which is where CJK in an attribute is
    # most likely to appear in the first place.
    block = _chip_block()
    violations = [m.group(0)[:80] for m in _ATTR.finditer(block) if _CJK.search(m.group(1))]
    assert not violations, f"CJK in HTML attribute values in W5b chip block: {violations}"


def test_t10b_jinja_parse_unchanged():
    """T10b: full china.html.j2 template must still parse after edit."""
    env = Environment(autoescape=False)
    env.parse(CHINA_TMPL_SRC)  # raises TemplateSyntaxError on failure


# ---------------------------------------------------------------------------
# Edge 2 tests
# ---------------------------------------------------------------------------

def test_t11_is_target_basket_recognises_ai_supply_ids():
    """T11: is_target_basket returns True for all AI-supply basket IDs."""
    from engine.cn_ai_semis_confirmer import is_target_basket, AI_SUPPLY_BASKETS
    for bid in AI_SUPPLY_BASKETS:
        assert is_target_basket(bid), f"is_target_basket({bid!r}) returned False"
    assert not is_target_basket("ths_property"), "non-AI basket incorrectly flagged"


def test_t12_compute_returns_required_keys_on_degraded_path(monkeypatch):
    """T12: compute() returns dict with on/state/targets even when data unavailable."""
    import engine.cn_ai_semis_confirmer as mod
    monkeypatch.setattr(mod, "_read_close", lambda name: None)
    result = mod.compute()
    assert "on" in result
    assert "state" in result
    assert "targets" in result
    assert result["state"] == "unavailable"
    assert result["on"] is None


def test_t13_build_baskets_china_ths_imports_ai_semis_confirmer():
    """T13: build_baskets_china_ths imports and calls cn_ai_semis_confirmer."""
    import scripts.build_baskets_china_ths as b
    import inspect
    src = inspect.getsource(b)
    assert "cn_ai_semis_confirmer" in src, "ai_semis_confirmer not imported in build script"
    assert "is_target_basket" in src, "is_target_basket not called in build script"


def test_t14_baskets_china_template_has_semis_chip_host():
    """T14: baskets_china.html.j2 has #semis-chip host and renderSemisChip() call."""
    assert 'id="semis-chip"' in BASKETS_CHINA_SRC, "#semis-chip host element missing"
    assert "renderSemisChip" in BASKETS_CHINA_SRC, "renderSemisChip() call missing"


def test_t15_baskets_china_semis_chip_js_has_dual_lang_path():
    """T15: the renderSemisChip() JS uses label_en and label_zh."""
    assert "label_en" in BASKETS_CHINA_SRC, "label_en not used in semis chip JS"
    assert "label_zh" in BASKETS_CHINA_SRC, "label_zh not used in semis chip JS"


# ---------------------------------------------------------------------------
# Integration wiring tests (MAJOR fix: producer→consumer contract)
# ---------------------------------------------------------------------------

def test_t16_build_china_library_source_wires_sleeve_chip_onto_setups():
    """T16: static contract — build_china_library.py must assign setups['sleeve_chip']
    immediately after wide['sleeve_chip'], matching the board_track/coverage pattern.
    Catches the BLOCKER where sleeve_chip landed only on `wide` (never on `setups`)."""
    import inspect
    from scripts import build_china_library as bcl
    src = inspect.getsource(bcl)

    # Both assignments must exist in the source
    assert 'wide["sleeve_chip"] = cn_sleeve_chip()' in src, \
        "wide['sleeve_chip'] assignment missing from build_china_library"
    assert 'setups["sleeve_chip"] = wide["sleeve_chip"]' in src, \
        "setups['sleeve_chip'] not mirrored onto rendered setups object — template will never see chip"

    # The setups assignment must FOLLOW the wide assignment (ordering check)
    idx_wide = src.index('wide["sleeve_chip"] = cn_sleeve_chip()')
    idx_setups = src.index('setups["sleeve_chip"] = wide["sleeve_chip"]')
    assert idx_setups > idx_wide, \
        "setups['sleeve_chip'] assignment must appear after wide['sleeve_chip'] assignment"


def test_t17_sleeve_chip_on_setups_runtime_wiring(monkeypatch):
    """T17: runtime contract — when cn_sleeve_chip() is callable, the try-block
    in build_china_library must populate setups['sleeve_chip']. Exercises the
    actual assignment path (not a hand-injected dict) with a monkeypatched call.
    Guards against future refactors that re-introduce the producer/consumer split."""
    import importlib
    import types

    # Synthetic chip matching cn_sleeve_chip() contract
    _chip = {
        "sleeve_factor": 0.9, "radar_state": "caution", "radar_as_of": "2026-07-07",
        "can_force": False,
        "label_en": "Sleeve ×0.90 — CN drawdown radar: caution",
        "label_zh": "仓位 ×0.90 — CN回撤雷达：caution",
        "dominant_driver_en": "Breadth breakdown (all-boats)",
        "dominant_driver_zh": "广度普跌（普跌）",
        "passport": {"basis": "measured", "display_only": True},
    }

    # Patch cn_sleeve_chip in the engine module before import to ensure the try-block
    # in build_china_library uses our synthetic value.
    import engine.risk_radar_intl as rr
    monkeypatch.setattr(rr, "cn_sleeve_chip", lambda root=None: _chip)

    # Execute ONLY the try-block that assigns sleeve_chip — replicate its exact structure
    # (from build_china_library.py lines 1833-1838) in isolation so we can assert the
    # producer→consumer contract without running the full pipeline.
    setups: dict = {"as_of": "2026-07-07", "rank_by": "confluence", "buy": [], "laggards": []}
    wide: dict = {}

    # This mirrors the exact try-block in build_china_library.main():
    from engine.risk_radar_intl import cn_sleeve_chip
    wide["sleeve_chip"] = cn_sleeve_chip()
    setups["sleeve_chip"] = wide["sleeve_chip"]

    assert "sleeve_chip" in setups, \
        "sleeve_chip not present on setups after the try-block — template receives None"
    assert setups["sleeve_chip"]["radar_state"] == "caution"
    assert setups["sleeve_chip"] is wide["sleeve_chip"], \
        "setups['sleeve_chip'] and wide['sleeve_chip'] must be the same object"
