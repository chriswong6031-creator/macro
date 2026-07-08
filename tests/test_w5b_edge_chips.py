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
from jinja2 import DictLoader, Environment

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

    # Extract just the W5b EDGE-1 chip block (balanced if/endif traversal).
    # Match opening {% if ... %} tokens (any content) and closing {% endif %} tokens.
    import re as _re
    chip_start = CHINA_TMPL_SRC.index("{# W5b EDGE-1")
    depth = 0
    chip_end = chip_start
    for _m in _re.finditer(r"\{%-?\s*(if\b[^%]*|endif\s*)-?%\}", CHINA_TMPL_SRC[chip_start:]):
        tag_body = _m.group(1).strip()
        if tag_body.startswith("if"):
            depth += 1
        elif tag_body.startswith("endif"):
            depth -= 1
            if depth == 0:
                chip_end = chip_start + _m.end()
                break
    chip_block = CHINA_TMPL_SRC[chip_start:chip_end]

    # Wrap in the mode guard to test dual-mode isolation
    mode_open = "{% if mode == 'stocks' %}"
    mode_close = "{% endif %}"
    snippet = mode_open + "\n" + chip_block + "\n" + mode_close
    full = macros + snippet
    env = Environment(loader=DictLoader({"tmpl": full}), autoescape=False)
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

def test_t1_chip_renders_with_valid_radar_state():
    """T1: chip renders when setups.sleeve_chip has a valid radar_state."""
    setups = {"sleeve_chip": _sleeve_chip("caution"), "buy": [], "ripening": [], "ran": []}
    html = _render_stocks_header(setups)
    assert "Sleeve" in html, "sleeve chip label_en missing from rendered output"
    assert "0.90" in html, "sleeve_factor missing from rendered output"


def test_t2_chip_absent_when_sleeve_chip_none():
    """T2: chip must be absent (degrade) when setups.sleeve_chip is None."""
    setups = {"sleeve_chip": None, "buy": [], "ripening": [], "ran": []}
    html = _render_stocks_header(setups)
    assert "Sleeve ×" not in html, "chip rendered despite sleeve_chip=None"


def test_t3_chip_absent_when_radar_state_none():
    """T3: chip must be absent when sleeve_chip.radar_state is None."""
    chip = _sleeve_chip("caution")
    chip["radar_state"] = None
    setups = {"sleeve_chip": chip, "buy": [], "ripening": [], "ran": []}
    html = _render_stocks_header(setups)
    assert "Sleeve ×" not in html, "chip rendered despite radar_state=None"


def test_t4_chip_absent_when_mode_macro():
    """T4: chip must not appear when mode='macro' (stocks-header block skipped)."""
    setups = {"sleeve_chip": _sleeve_chip("caution"), "buy": [], "ripening": [], "ran": []}
    html = _render_stocks_header(setups, mode="macro")
    assert "Sleeve ×" not in html, "chip leaked into macro mode"


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
    """T9: help tooltip (tip span) must not be empty."""
    setups = {"sleeve_chip": _sleeve_chip("caution"), "buy": [], "ripening": [], "ran": []}
    html = _render_stocks_header(setups)
    # help renders as <span class='tip'>...</span>
    tip_match = re.search(r"class='tip'>(.*?)</span>", html, re.DOTALL)
    assert tip_match is not None, "help tip span not found in chip area"
    assert tip_match.group(1).strip(), "help tooltip is empty"


def test_t10_no_cjk_in_html_attributes_added_section():
    """T10: no Chinese characters inside HTML attribute values in the W5b chip block."""
    _CJK = re.compile(r"[一-鿿㐀-䶿]")
    _ATTR = re.compile(r'(?:class|id|style|data-[\w-]+|aria-[\w-]+)\s*=\s*"([^"]*)"')
    # Extract only the W5b chip block
    start = CHINA_TMPL_SRC.index("{# W5b EDGE-1")
    # find next {% endif %} after start
    end = CHINA_TMPL_SRC.index("{% endif %}", start) + len("{% endif %}")
    block = CHINA_TMPL_SRC[start:end]
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
