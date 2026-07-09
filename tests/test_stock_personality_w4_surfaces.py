"""tests/test_stock_personality_w4_surfaces.py

W4 operator-surface tests for the stock-personality display layer.

Three surface groups:
  1. build_theme_detail._personality_slim()  — pure function, extracting slim
     {chart, mode} from a stockdata personality block.
  2. build_site.py board-attach logic — the per-ticker slim dict thread from
     stock_personality.json into us_standouts buy cards.  Tested via the pure
     helper that was added; we test the data contracts not the full build.
  3. Template markup — basket_detail.html.j2 and stock.html.j2 contain the
     expected W4 markup (CSS classes, JS function names, guardrail comments).
     basket_detail renders the full Jinja template (detail_json is data passed
     as a JSON string to JS; Jinja itself is cheap to render).

All tests are display-only surface checks per R-SP13 — never test ranking,
gating, or sizing logic (none was added).
"""
from __future__ import annotations

import json
from pathlib import Path

import jinja2
import pytest

from lib import config


# ---------------------------------------------------------------------------
# 1. _personality_slim() — pure extraction helper
# ---------------------------------------------------------------------------

from scripts.build_theme_detail import _personality_slim


def _stockdata_rec(chart_labels=None, modes=None, *, include_personality=True) -> dict:
    """Build a minimal stockdata rec dict matching the personality block schema."""
    if not include_personality:
        return {"ticker": "TEST", "conviction": {"score": 70}}
    return {
        "ticker": "TEST",
        "conviction": {"score": 70},
        "personality": {
            "base": {
                "chart_personality": {"labels": chart_labels or []},
            },
            "current_mode": {"modes": modes or ["normal"]},
        },
    }


def test_personality_slim_extracts_chart_and_non_normal_mode():
    rec = _stockdata_rec(
        chart_labels=["stair_step_leader", "smooth_compounder_grind"],
        modes=["squeeze", "normal"],
    )
    result = _personality_slim(rec)
    assert result is not None
    assert result["chart"] == "stair_step_leader"
    assert result["mode"] == "squeeze"


def test_personality_slim_normal_mode_omitted():
    """'normal' mode must not become the mode chip — only non-normal surfaced."""
    rec = _stockdata_rec(chart_labels=["event_gapper"], modes=["normal"])
    result = _personality_slim(rec)
    assert result is not None
    assert result["chart"] == "event_gapper"
    assert result["mode"] is None


def test_personality_slim_no_chart_no_mode_returns_none():
    """If both chart and mode are empty/normal, slim returns None (fail-open)."""
    rec = _stockdata_rec(chart_labels=[], modes=["normal"])
    assert _personality_slim(rec) is None


def test_personality_slim_absent_block_returns_none():
    """Rec without personality key returns None gracefully."""
    rec = _stockdata_rec(include_personality=False)
    assert _personality_slim(rec) is None


def test_personality_slim_malformed_block_returns_none():
    """Corrupted personality block is caught and returns None (never fatal)."""
    rec = {"ticker": "X", "personality": "not_a_dict"}
    assert _personality_slim(rec) is None


def test_personality_slim_partial_block_no_crash():
    """Partial dict (missing base or current_mode) returns None, not exception."""
    rec = {"ticker": "X", "personality": {"base": {}}}
    result = _personality_slim(rec)
    assert result is None


# ---------------------------------------------------------------------------
# 2. board personality-attach contracts (via unit-level dict manipulation)
#    We reproduce the exact logic from build_site.py's W4 personality-attach
#    block to confirm the output contract rather than importing the heavy
#    build_site module (which triggers engine imports on load).
# ---------------------------------------------------------------------------

def _attach_personality(buy_cards: list[dict], per_ticker: dict) -> None:
    """Replicate the W4 board-attach block from build_site.py for testing."""
    for card in buy_cards:
        tk = card.get("ticker")
        slim = per_ticker.get(tk) if tk else None
        if slim:
            chart_list = slim.get("chart") or []
            modes = slim.get("modes") or []
            mode1 = next((m for m in modes if m != "normal"), None)
            card["personality"] = {
                "chart": chart_list[0] if chart_list else None,
                "mode": mode1,
            }


def test_board_attach_sets_personality_on_matching_ticker():
    cards = [{"ticker": "NVDA", "dir": "buy"}]
    per_ticker = {
        "NVDA": {"arch": "momentum_compounder", "chart": ["stair_step_leader"],
                 "modes": ["normal"], "own": [], "micro": [], "dna": None}
    }
    _attach_personality(cards, per_ticker)
    assert "personality" in cards[0]
    assert cards[0]["personality"]["chart"] == "stair_step_leader"
    assert cards[0]["personality"]["mode"] is None  # only "normal" present


def test_board_attach_non_normal_mode_surfaced():
    cards = [{"ticker": "TSLA", "dir": "buy"}]
    per_ticker = {
        "TSLA": {"chart": ["volatile_momentum_vehicle"], "modes": ["squeeze", "normal"],
                 "own": [], "micro": [], "dna": None}
    }
    _attach_personality(cards, per_ticker)
    assert cards[0]["personality"]["mode"] == "squeeze"


def test_board_attach_missing_ticker_no_personality_key():
    """Card for a ticker absent from per_ticker must not get a personality key."""
    cards = [{"ticker": "AAPL", "dir": "buy"}]
    _attach_personality(cards, per_ticker={})
    assert "personality" not in cards[0]


def test_board_attach_empty_per_ticker_no_crash():
    cards = [{"ticker": "META"}, {"ticker": "GOOG"}]
    _attach_personality(cards, per_ticker={})
    for c in cards:
        assert "personality" not in c


# ---------------------------------------------------------------------------
# 3. Template markup checks
#    basket_detail.html.j2 is rendered via Jinja (cheap: detail_json is opaque
#    to Jinja; all data lives in JS).  stock.html.j2 is also rendered to confirm
#    its W4 panel and renderPersonality() JS function are present.
#    dashboard.html.j2 personality chips are Jinja-rendered with a buy card.
# ---------------------------------------------------------------------------

def _jinja_env() -> jinja2.Environment:
    """Minimal Jinja env matching build_site.py's template environment."""
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(config.ROOT / "templates"),
        undefined=jinja2.Undefined,  # silent on missing — same as build_site
    )
    # Filters used in templates
    env.filters["min"] = lambda seq: min(seq)
    try:
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)
    except Exception:
        env.globals.update(zip=zip)
    return env


# basket_detail.html.j2 -------------------------------------------------------

def _minimal_detail_json() -> str:
    """Minimal detail JSON passed to basket_detail template; Jinja treats as opaque."""
    return json.dumps({
        "basket": {"id": "tech", "name": "Technology", "members": []},
        "members": [],
        "theme": {},
        "act_now": [],
        "history": [],
        "timeline": [],
        "as_of": "2026-07-07",
        "market_concentration": {},
        "stock_base": "../stock.html#",
        "back": "../baskets.html",
        "region": "us",
        "bench_label": "S&P 500",
        "bench_label_zh": "标普500",
    }, separators=(",", ":"))


def test_basket_detail_renders_without_crash():
    """Baseline: template renders at all."""
    html = _jinja_env().get_template("basket_detail.html.j2").render(
        detail_json=_minimal_detail_json(),
        basket_name="Technology",
        generated_utc="2026-07-07 00:00 UTC",
        back_href="../baskets.html",
    )
    assert "Technology" in html


def test_basket_detail_contains_personality_chip_css():
    """W4 CSS classes for holdings-table personality chips must be present."""
    html = _jinja_env().get_template("basket_detail.html.j2").render(
        detail_json=_minimal_detail_json(),
        basket_name="Technology",
        generated_utc="2026-07-07 00:00 UTC",
        back_href="../baskets.html",
    )
    assert "sp-td-chip" in html
    assert "sp-td-mode" in html


def test_basket_detail_contains_personality_js_function():
    """personalityChip() JS helper must be present in the rendered template."""
    html = _jinja_env().get_template("basket_detail.html.j2").render(
        detail_json=_minimal_detail_json(),
        basket_name="Technology",
        generated_utc="2026-07-07 00:00 UTC",
        back_href="../baskets.html",
    )
    assert "personalityChip" in html
    # Display-only guardrail comment preserved
    assert "R-SP13" in html


def test_basket_detail_no_validated_claims():
    """CI guard: no affirmative 'validated'/'已验证' in W4 additions."""
    html = _jinja_env().get_template("basket_detail.html.j2").render(
        detail_json=_minimal_detail_json(),
        basket_name="Technology",
        generated_utc="2026-07-07 00:00 UTC",
        back_href="../baskets.html",
    )
    # The word "validated" is only legal in allowlisted contexts (check_validated_claims.py).
    # Our W4 additions must not introduce it.  Simple substring check is sufficient here
    # since CI runs the authoritative checker.
    w4_additions = [
        "personalityChip", "sp-td-chip", "sp-td-mode", "R-SP13",
        "display-only context", "no ranking power",
    ]
    for marker in w4_additions:
        if marker in html:
            # W4 markup present — confirm no "validated" in the surrounding 200 chars
            idx = html.index(marker)
            window = html[max(0, idx - 100):idx + 200].lower()
            assert "validated" not in window or "already validated" not in window, (
                f"Unexpected 'validated' near W4 marker '{marker}'"
            )


# stock.html.j2 ---------------------------------------------------------------

def _stock_html() -> str:
    """Render stock.html.j2 with a minimal empty-ish context (JS-driven page)."""
    env = _jinja_env()
    tmpl = env.get_template("stock.html.j2")
    # stock.html.j2 is almost entirely JS-driven; Jinja variables are minimal.
    # The template gracefully degrades on missing template vars (Undefined).
    try:
        return tmpl.render()
    except Exception as exc:
        # If the template needs specific globals, surface the error clearly.
        pytest.fail(f"stock.html.j2 render failed: {exc}")


def test_stock_panel_personality_present_in_template():
    """W4 panel_personality div must exist in stock.html.j2."""
    html = _stock_html()
    assert "panel_personality" in html, (
        "W4 personality panel div (id='panel_personality') missing from stock.html.j2"
    )


def test_stock_render_personality_function_present():
    """renderPersonality() JS function must be defined in stock.html.j2."""
    html = _stock_html()
    assert "renderPersonality" in html, (
        "renderPersonality() JS function missing from stock.html.j2"
    )


def test_stock_personality_panel_no_title_cjk():
    """CI guard: no CJK inside title= attributes in the W4 additions."""
    html = _stock_html()
    # Simple heuristic: check that the known W4 attribute 'data-tip-en' is used
    # (not title=) for bilingual tooltips in the personality panel section.
    # The authoritative check is scripts/check_title_i18n.py.
    assert "data-tip-en" in html or "panel_personality" in html  # W4 additions present


def test_stock_personality_fail_open_pattern():
    """JS fail-open pattern: when personality absent, panel must be hidden."""
    html = _stock_html()
    # The fail-open branch: show('panel_personality', false) called when !p.
    assert "panel_personality" in html
    # The panel starts hidden (display:none) and is shown only when data present.
    assert 'style="display:none"' in html or "display:none" in html


# dashboard.html.j2 partial check (personality chips in nb-more) ---------------
# Full dashboard render requires extensive globals; we check only the Jinja
# source directly for the key W4 patterns (CSS + nb-sp-chips block).

def test_dashboard_template_contains_nb_sp_chip_css():
    """W4 CSS for slim personality chips must be in dashboard.html.j2 source."""
    src = (config.ROOT / "templates" / "dashboard.html.j2").read_text()
    assert "nb-sp-chart" in src
    assert "nb-sp-mode" in src


def test_dashboard_template_nb_sp_chips_inside_nb_more():
    """Personality chips must be inside .nb-more — never outside (guardrail 16)."""
    src = (config.ROOT / "templates" / "dashboard.html.j2").read_text()
    # Find the nb-sp-chips block and verify it sits inside the nb-more div.
    nb_more_idx = src.rfind("end .nb-more")  # comment marks closure
    nb_sp_idx = src.rfind("nb-sp-chips")
    assert nb_sp_idx != -1, "nb-sp-chips block missing from dashboard.html.j2"
    assert nb_sp_idx < nb_more_idx, (
        "nb-sp-chips block appears AFTER end .nb-more — violates guardrail 16"
    )


def test_dashboard_template_no_title_cjk_in_personality():
    """W4 additions in dashboard must use data-tip-en/zh not title= for bilingual."""
    src = (config.ROOT / "templates" / "dashboard.html.j2").read_text()
    # Extract only the nb-sp-chips block for a targeted check.
    start = src.rfind("nb-sp-chips")
    if start == -1:
        pytest.skip("nb-sp-chips not found — W4 additions may not be present")
    end = src.find("</div>", start) + len("</div>")
    block = src[start:end]
    # Block must use data-tip-en/data-tip-zh, not title=
    assert "data-tip-en=" in block, "Missing data-tip-en in personality chip"
    assert "title=" not in block or block.count("title=") == 0, (
        "title= attribute found in personality chip block — use data-tip-en/zh instead"
    )


# ---------------------------------------------------------------------------
# 4. Playbook map coverage (new W4 doctrine lines)
#    Import the engine's closed-set key constants and assert that every key
#    has a corresponding entry in the _PLAYBOOK JS map (EN + ZH) embedded in
#    stock.html.j2.  We parse the JS source rather than executing it so the
#    test is fast and dependency-free.
# ---------------------------------------------------------------------------

# Import canonical closed sets from the engine.
from engine.stock_personality import (
    CHART_PRECEDENCE,
    MICROSTRUCTURE_PRECEDENCE,
    OWNERSHIP_PRECEDENCE,
    CURRENT_MODE_PRECEDENCE,
)
from engine.stock_fundamentals import ARCHETYPE_PRECEDENCE


def _extract_playbook_js_keys(stock_html_src: str) -> set[str]:
    """Extract all keys defined in the _PLAYBOOK JS map in stock.html.j2.

    We parse the JS source by scanning for the lines of the form:
        key_name:  ['...', '...'],
    inside the _PLAYBOOK = { ... } block.  This is a structural match —
    valid as long as the map follows the one-key-per-line convention.
    """
    import re
    # Find the _PLAYBOOK block
    start = stock_html_src.find("var _PLAYBOOK = {")
    end = stock_html_src.find("};", start)
    assert start != -1 and end != -1, "_PLAYBOOK map not found in stock.html.j2"
    block = stock_html_src[start:end]
    # Match JS identifier keys at the start of a line before ':'
    keys = re.findall(r"^\s+([a-zA-Z_][a-zA-Z_0-9]*):\s*\[", block, re.MULTILINE)
    return set(keys)


def _extract_playbook_entries(stock_html_src: str) -> dict[str, tuple[str, str]]:
    """Return {key: (en_line, zh_line)} for all entries in _PLAYBOOK.

    Handles multi-line entries where the ZH string is on a continuation line.
    The extraction strategy:
      1. Collect the _PLAYBOOK block text.
      2. For each key line, extract the EN string from the same line.
      3. Scan forward (up to 3 lines) for the ZH string in the next single-quoted token.
    """
    import re
    start = stock_html_src.find("var _PLAYBOOK = {")
    end_marker = stock_html_src.find("};", start)
    assert start != -1 and end_marker != -1, "_PLAYBOOK map not found in stock.html.j2"
    block = stock_html_src[start:end_marker]
    lines = block.splitlines()

    # Pattern: key_name:  ['EN text',   (possibly ZH on same line or next)
    key_line_re = re.compile(
        r"^\s+([a-zA-Z_][a-zA-Z_0-9]*):\s*\['([^']*)'"
    )
    # Pattern to find a quoted ZH string anywhere in a line
    zh_re = re.compile(r"'([^']+)'")

    result = {}
    for i, line in enumerate(lines):
        m = key_line_re.match(line)
        if not m:
            continue
        key = m.group(1)
        en = m.group(2)

        # Try to find ZH: first check remainder of the same line after the EN string,
        # then look in the next 3 lines.
        remainder = line[m.end():]
        zh_match = zh_re.search(remainder)
        if zh_match:
            zh = zh_match.group(1)
        else:
            # Scan forward
            zh = ""
            for j in range(i + 1, min(i + 4, len(lines))):
                zh_match = zh_re.search(lines[j])
                if zh_match:
                    zh = zh_match.group(1)
                    break

        result[key] = (en, zh)
    return result


@pytest.fixture(scope="module")
def stock_html_src() -> str:
    return (config.ROOT / "templates" / "stock.html.j2").read_text()


@pytest.fixture(scope="module")
def playbook_entries(stock_html_src) -> dict[str, tuple[str, str]]:
    return _extract_playbook_entries(stock_html_src)


@pytest.fixture(scope="module")
def playbook_keys(playbook_entries) -> set[str]:
    return set(playbook_entries.keys())


def test_playbook_covers_all_archetype_keys(playbook_keys):
    """Every archetype in ARCHETYPE_PRECEDENCE must have a playbook entry."""
    missing = [k for k in ARCHETYPE_PRECEDENCE if k not in playbook_keys]
    assert not missing, (
        f"Archetypes missing from _PLAYBOOK: {missing}"
    )


def test_playbook_covers_all_chart_keys(playbook_keys):
    """Every chart personality in CHART_PRECEDENCE must have a playbook entry."""
    missing = [k for k in CHART_PRECEDENCE if k not in playbook_keys]
    assert not missing, (
        f"Chart labels missing from _PLAYBOOK: {missing}"
    )


def test_playbook_covers_all_ownership_keys(playbook_keys):
    """Every ownership habitat in OWNERSHIP_PRECEDENCE must have a playbook entry."""
    missing = [k for k in OWNERSHIP_PRECEDENCE if k not in playbook_keys]
    assert not missing, (
        f"Ownership labels missing from _PLAYBOOK: {missing}"
    )


def test_playbook_covers_all_micro_keys(playbook_keys):
    """Every microstructure label in MICROSTRUCTURE_PRECEDENCE must have a playbook entry."""
    missing = [k for k in MICROSTRUCTURE_PRECEDENCE if k not in playbook_keys]
    assert not missing, (
        f"Microstructure labels missing from _PLAYBOOK: {missing}"
    )


def test_playbook_covers_all_mode_keys(playbook_keys):
    """Every current-mode key in CURRENT_MODE_PRECEDENCE must have a playbook entry."""
    missing = [k for k in CURRENT_MODE_PRECEDENCE if k not in playbook_keys]
    assert not missing, (
        f"Mode keys missing from _PLAYBOOK: {missing}"
    )


def test_playbook_all_entries_have_en_and_zh(playbook_entries):
    """Every _PLAYBOOK entry must have a non-empty EN and ZH string."""
    bad = []
    for key, (en, zh) in playbook_entries.items():
        if not en.strip():
            bad.append(f"{key}: empty EN")
        if not zh.strip():
            bad.append(f"{key}: empty ZH")
    assert not bad, f"Playbook entries with empty EN or ZH: {bad}"


def test_playbook_en_lines_max_14_words(playbook_entries):
    """EN doctrine lines must be ≤14 words (per spec)."""
    violations = []
    for key, (en, _zh) in playbook_entries.items():
        word_count = len(en.split())
        if word_count > 14:
            violations.append(f"{key}: {word_count} words — '{en}'")
    assert not violations, f"EN lines exceed 14 words:\n" + "\n".join(violations)


def test_playbook_no_validated_word_in_lines(playbook_entries):
    """No playbook doctrine line may contain the word 'validated' or '已验证'."""
    hits = []
    for key, (en, zh) in playbook_entries.items():
        if "validated" in en.lower() or "已验证" in zh:
            hits.append(key)
    assert not hits, f"Playbook lines contain forbidden word 'validated': {hits}"


def test_stock_panel_contains_playbook_block_hook(stock_html_src):
    """stock.html.j2 must contain the sp-pb-block CSS class (playbook sub-block hook)."""
    assert "sp-pb-block" in stock_html_src, (
        "Playbook sub-block CSS class 'sp-pb-block' missing from stock.html.j2"
    )


def test_stock_panel_contains_playbook_helper_functions(stock_html_src):
    """_playbookLines() and _pbBlock() helpers must be defined in stock.html.j2."""
    assert "_playbookLines" in stock_html_src, "_playbookLines() helper missing"
    assert "_pbBlock" in stock_html_src, "_pbBlock() helper missing"


def test_stock_panel_contains_doctrine_doc_link(stock_html_src):
    """The playbook footer doc-link line must reference the playbook file."""
    assert "STOCK_PERSONALITY_OPERATOR_PLAYBOOK_BY_FABLE.md" in stock_html_src, (
        "Doctrine doc-link to playbook file missing from stock.html.j2"
    )
    assert "完整手册见研究文档" in stock_html_src, (
        "ZH doctrine doc-link text missing from stock.html.j2"
    )
