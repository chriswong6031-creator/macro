"""Tests for the HKRV-W3 leadership banner in templates/hk.html.j2.

Covers:
  (1) Banner renders when setups.leadership.state == 'leaders_participating'.
  (2) Banner is ABSENT when leadership is None.
  (3) Banner is ABSENT when leadership.state == 'quiet'.
  (4) Dynamic counts: n_above/n_total computed from members list.
  (5) Broad breadth line present when broad_breadth_pct is set.
  (6) Tier-2 receipt: study_n and study_hsi_fwd40_mean appear in the pop block.
  (7) Amber chip renders on an act-item whose label == 'TURN IN PROGRESS'.
  (8) Chip ABSENT when label is not 'TURN IN PROGRESS'.
  (9) No CJK characters in title= attributes in the new banner block.
  (10) l-en and l-zh spans present in banner.
  (11) hkrv-why-toggle button present with onclick.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_leadership(state: str = "leaders_participating",
                     n_above: int = 8, n_total: int = 10,
                     broad_breadth_pct: float | None = 21.6,
                     study_n: int = 15,
                     study_hsi_fwd40_mean: float = -1.73,
                     breadth_confirming: bool = False,
                     study_cohort_fwd60_mean: float | None = 4.9) -> dict:
    """Build a synthetic leadership dict."""
    members = []
    for i in range(n_total):
        members.append({
            "ticker": f"{str(i).zfill(4)}.HK",
            "above_rising_ma10": i < n_above,
            "sb_chg5": float(i) if i > 0 else None,
        })
    return {
        "state": state,
        "thrust_date": "2026-07-10",
        "cohesion_now": n_above / n_total if n_total > 0 else 0.0,
        "cohesion_10d_ago": 0.0,
        "broad_breadth_pct": broad_breadth_pct,
        "breadth_confirming": breadth_confirming,
        "members": members,
        "display_only": True,
        "copy_en": "Leaders are participating.",
        "copy_zh": "龙头正在参与。",
        "study_n": study_n,
        "study_hsi_fwd40_mean": study_hsi_fwd40_mean,
        "study_cohort_fwd60_mean": study_cohort_fwd60_mean,
        "study_note": "Study B: test note.",
    }


def _banner_block(html: str) -> str:
    """Slice out the rendered banner block (banner start → action grid)."""
    start = html.find("hkrv-banner-a")
    end = html.find("act-grid", start)
    assert start != -1, "banner block not found in rendered HTML"
    return html[start:end if end != -1 else None]


def _make_actions(with_confirming: bool = False) -> dict:
    """Build a minimal actions dict; optionally include a TURN IN PROGRESS item."""
    buy_soon = []
    if with_confirming:
        buy_soon.append({
            "ticker": "internet",
            "name": "Internet & Tech",
            "label": "TURN IN PROGRESS",
            "tag": "CONFIRMING TURN",
            "days": 5,
            "dir": "caution",
        })
    buy_soon.append({
        "ticker": "finance",
        "name": "Financials",
        "label": "BUY ZONE",
        "tag": "now",
        "days": 2,
        "dir": "up",
    })
    return {
        "buy_now": [],
        "buy_soon": buy_soon,
        "on_the_run": [],
        "take_profits": [],
        "hold": [],
        "avoid": [],
    }


def _make_setups(leadership: dict | None) -> dict:
    return {
        "leadership": leadership,
        "health": [],
        "buy": [],
        "watch": [],
        "laggards": [],
        "southbound_summary": None,
        "liquidity_regime": None,
        "dispersion_regime": None,
        "washout_watch": None,
        "context_chips": None,
        "board_track": None,
    }


def _render(setups: dict | None, actions: dict | None = None) -> str:
    """Render hk.html.j2 with a minimal vm and return the HTML string."""
    from jinja2 import Environment, FileSystemLoader
    from engine import i18n
    from markupsafe import Markup

    if actions is None:
        actions = _make_actions()

    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=False)
    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    env.globals["help"] = lambda en, zh="": Markup("")

    tmpl = env.get_template("hk.html.j2")
    vm = {
        "mode": "stocks",
        "latest": {
            "date": "2026-07-10",
            "quad_name": "Goldilocks",
            "quad": "Q1",
            "liquidity_overlay": "neutral",
            "pending_quad": None,
        },
        "actions": actions,
        "setups": setups,
        "gv": None,
        "market_state": None,
        "hk_scoreboard": None,
        "sectors_by_ticker": {},
        "velocity_desk": None,
        "built": "2026-07-10T00:00:00Z",
        "hk_breadth": None,
        "hk_full_breadth": None,
        "benchmark": None,
        "hk_sectors": [],
        "hk_flow": None,
        "track_record": None,
        "hk_ab": None,
        "hk_dispersion": None,
        "hk_cycles": None,
        "hk_indicators": None,
        "state_display_json": "{}",
        "washout_desk": None,
        "freshness": None,
        "hk_history": None,
        "hk_news": None,
        "hk_policy": None,
        "hk_macro": None,
        "hk_property": None,
        "hk_alerts": None,
        "hk_market_drivers": None,
        "hk_conditions": None,
        "hk_signal_stack": None,
        "hk_event_calendar": None,
        "hk_context_chips": None,
        "velocity_desk_picks": None,
        "hk_lab_button": None,
    }
    return tmpl.render(**vm)


# ---------------------------------------------------------------------------
# (1) Banner renders when state == 'leaders_participating'
# ---------------------------------------------------------------------------

def test_banner_renders_when_leaders_participating():
    """Banner must appear when leadership.state == 'leaders_participating'."""
    ldr = _make_leadership(state="leaders_participating")
    setups = _make_setups(ldr)
    html = _render(setups)
    assert 'id="hkrv-banner-a"' in html, "hkrv-banner-a element must be present"
    assert "Leaders moving first" in html, "Banner title 'Leaders moving first' must be present"
    assert "龙头先行" in html, "ZH banner title must be present"


# ---------------------------------------------------------------------------
# (2) Banner absent when leadership is None
# ---------------------------------------------------------------------------

def test_banner_absent_when_leadership_none():
    """Banner must NOT render when setups.leadership is None."""
    setups = _make_setups(None)
    html = _render(setups)
    assert 'id="hkrv-banner-a"' not in html, "hkrv-banner-a element must be absent when leadership is None"
    assert "Leaders moving first" not in html


# ---------------------------------------------------------------------------
# (3) Banner absent when state == 'quiet'
# ---------------------------------------------------------------------------

def test_banner_absent_when_quiet():
    """Banner must NOT render when leadership.state == 'quiet'."""
    ldr = _make_leadership(state="quiet")
    setups = _make_setups(ldr)
    html = _render(setups)
    assert 'id="hkrv-banner-a"' not in html, "hkrv-banner-a element must be absent when state is 'quiet'"


# ---------------------------------------------------------------------------
# (4) Dynamic counts from members list
# ---------------------------------------------------------------------------

def test_banner_shows_correct_counts():
    """n_above and n_total computed from the members list must appear in the banner."""
    ldr = _make_leadership(state="leaders_participating", n_above=7, n_total=10)
    setups = _make_setups(ldr)
    html = _render(setups)
    # Banner inline line: "7 of 10 mega-caps above rising 10-day MA"
    assert "7" in html
    assert "10" in html
    # More specific: the inline summary line
    assert "7 of 10 mega-caps" in html or "10只龙头中7只" in html


# ---------------------------------------------------------------------------
# (5) Broad breadth line when broad_breadth_pct is set
# ---------------------------------------------------------------------------

def test_banner_shows_breadth_when_present():
    """Broad breadth percentage must appear in the banner line when set."""
    ldr = _make_leadership(state="leaders_participating", broad_breadth_pct=22.3)
    setups = _make_setups(ldr)
    html = _render(setups)
    assert "22" in html, "Broad breadth pct must be present in banner"
    assert "broad breadth" in html.lower() or "大盘广度" in html


def test_banner_no_breadth_when_none():
    """Breadth line must be omitted when broad_breadth_pct is None."""
    ldr = _make_leadership(state="leaders_participating", broad_breadth_pct=None)
    setups = _make_setups(ldr)
    html = _render(setups)
    # Banner must still render
    assert 'id="hkrv-banner-a"' in html
    # But no breadth percentage line
    assert "broad breadth" not in html.lower()


# ---------------------------------------------------------------------------
# (6) Tier-2 receipt: study_n and study_hsi_fwd40_mean
# ---------------------------------------------------------------------------

def test_tier2_receipt_study_fields():
    """study_n and study_hsi_fwd40_mean must appear in the Tier-2 pop block."""
    ldr = _make_leadership(state="leaders_participating", study_n=15,
                            study_hsi_fwd40_mean=-1.73)
    setups = _make_setups(ldr)
    html = _render(setups)
    assert 'id="hkrv-pop-a"' in html, "hkrv-pop-a element must be present"
    # 15 episodes
    assert "15" in html, "study_n (15) must appear in the history row"
    # Forward return sign
    assert "-1.7" in html or "+1.7" in html or "1.73" in html, (
        "study_hsi_fwd40_mean must appear in the history row"
    )


# ---------------------------------------------------------------------------
# (7) Amber chip on TURN IN PROGRESS item
# ---------------------------------------------------------------------------

def test_chip_renders_for_confirming_turn_item():
    """act-turn-chip element must appear when an act-item has label='TURN IN PROGRESS'."""
    ldr = _make_leadership(state="leaders_participating")
    setups = _make_setups(ldr)
    actions = _make_actions(with_confirming=True)
    html = _render(setups, actions)
    assert 'class="act-turn-chip"' in html, "act-turn-chip element must be present"
    assert "turn in progress" in html.lower(), "Chip text 'turn in progress' must be present"
    assert "转向进行中" in html, "ZH chip text must be present"


# ---------------------------------------------------------------------------
# (8) Chip absent when no CONFIRMING TURN item
# ---------------------------------------------------------------------------

def test_chip_absent_when_no_confirming_turn():
    """act-turn-chip span element must NOT appear in item rows when no CONFIRMING TURN item.

    NOTE: The CSS class name '.act-turn-chip' appears in the <style> block always;
    we assert the rendered SPAN element with that class is absent, by checking
    for 'class="act-turn-chip"' (the element, not just the CSS selector).
    """
    ldr = _make_leadership(state="leaders_participating")
    setups = _make_setups(ldr)
    actions = _make_actions(with_confirming=False)
    html = _render(setups, actions)
    assert 'class="act-turn-chip"' not in html, (
        "act-turn-chip element must be absent when no CONFIRMING TURN item"
    )


# ---------------------------------------------------------------------------
# (9) No CJK in title= attributes in the banner block
# ---------------------------------------------------------------------------

_CJK_IN_TITLE = re.compile(r'title=["\'][^"\']*[一-鿿㐀-䶿][^"\']*["\']')


def test_no_cjk_in_title_attrs():
    """No CJK characters must appear inside title= attributes (CI-guarded)."""
    ldr = _make_leadership(state="leaders_participating")
    setups = _make_setups(ldr)
    html = _render(setups)
    bad = _CJK_IN_TITLE.findall(html)
    assert not bad, f"CJK found in title= attrs: {bad}"


# ---------------------------------------------------------------------------
# (10) l-en and l-zh spans present in banner
# ---------------------------------------------------------------------------

def test_bilingual_spans_in_banner():
    """Banner must contain both l-en and l-zh class spans."""
    ldr = _make_leadership(state="leaders_participating")
    setups = _make_setups(ldr)
    html = _render(setups)
    # Banner block should contain both span classes
    banner_section = html[html.find("hkrv-banner"):html.find("/div", html.find("hkrv-banner")) + 10]
    assert 'class="l-en"' in banner_section or 'class="l-en"' in html
    assert 'class="l-zh"' in banner_section or 'class="l-zh"' in html


# ---------------------------------------------------------------------------
# (11) Why toggle button present with onclick
# ---------------------------------------------------------------------------

def test_why_toggle_button_present():
    """hkrv-why-toggle button with onclick must be present in the banner."""
    ldr = _make_leadership(state="leaders_participating")
    setups = _make_setups(ldr)
    html = _render(setups)
    assert 'class="hkrv-why-toggle"' in html, "hkrv-why-toggle element must be present"
    assert "onclick" in html, "onclick handler must be present on the toggle button"
    assert 'id="hkrv-pop-a"' in html, "hkrv-pop-a id must be present for the toggle"


# ---------------------------------------------------------------------------
# Template parse sanity (guards against future regressions)
# ---------------------------------------------------------------------------

def test_template_parses_without_syntax_error():
    """hk.html.j2 must parse without Jinja syntax errors after the banner addition."""
    from jinja2 import Environment
    src = (ROOT / "templates" / "hk.html.j2").read_text(encoding="utf-8")
    env = Environment(autoescape=False)
    # Should not raise
    env.parse(src)


# ---------------------------------------------------------------------------
# (12) Two-tier ladder: breadth-confirmed tier (upgrade fix)
# ---------------------------------------------------------------------------

def test_confirmed_tier_renders_upgrade_copy():
    """breadth_confirming=True must swap title, body, and stance to the confirmed tier."""
    ldr = _make_leadership(breadth_confirming=True, broad_breadth_pct=38.0)
    html = _render(_make_setups(ldr))
    block = _banner_block(html)
    assert "Broad market joining in" in block, "Confirmed-tier title must render"
    assert "大盘跟进中" in block, "ZH confirmed-tier title must render"
    assert "broad breadth is now confirming" in block, "Confirmed-tier body must render"
    assert "Get ready" in block, "Confirmed-tier stance chip must be 'Get ready'"
    assert "准备就绪" in block, "ZH confirmed-tier stance must render"
    # Unconfirmed copy must be gone everywhere in the banner
    assert "hasn't confirmed yet" not in block
    assert "Leaders moving first" not in block
    assert "Watch — don't chase" not in block
    # Pop-over broad-market row flips to confirming
    assert "— confirming." in block
    assert "not confirmed" not in block


def test_unconfirmed_tier_keeps_ratified_copy():
    """breadth_confirming=False keeps the original ratified tier untouched."""
    ldr = _make_leadership(breadth_confirming=False, broad_breadth_pct=22.0)
    html = _render(_make_setups(ldr))
    block = _banner_block(html)
    assert "Leaders moving first" in block
    assert "hasn't confirmed yet" in block
    assert "Watch — don't chase" in block
    assert "Broad market joining in" not in block
    assert "Get ready" not in block


# ---------------------------------------------------------------------------
# (13) HKRV-R3 honest framing: cohort own-return on Tier 1 + Tier 2
# ---------------------------------------------------------------------------

def test_cohort_framing_footer_on_unconfirmed_tier():
    """Unconfirmed tier prints the plain-word Study B line (leaders climbed, index didn't)."""
    ldr = _make_leadership(breadth_confirming=False)
    html = _render(_make_setups(ldr))
    block = _banner_block(html)
    assert "the leaders themselves kept climbing" in block
    assert "龙头自身持续上涨" in block


def test_cohort_framing_footer_absent_on_confirmed_tier():
    """Confirmed tier omits the leaders-first footer (episode framing no longer applies)."""
    ldr = _make_leadership(breadth_confirming=True)
    html = _render(_make_setups(ldr))
    block = _banner_block(html)
    assert "kept climbing while the broad index went nowhere" not in block


def test_popover_history_includes_cohort_return():
    """Tier-2 history row prints the cohort's own +4.9%/60d next to the index null."""
    ldr = _make_leadership(study_cohort_fwd60_mean=4.9)
    html = _render(_make_setups(ldr))
    block = _banner_block(html)
    assert "+4.9" in block, "cohort own forward return must appear in the history row"
    assert "-1.7" in block, "index null must still be printed (R3)"


def test_graceful_without_cohort_field():
    """Old artifacts without study_cohort_fwd60_mean render the original history row, no footer."""
    ldr = _make_leadership(study_cohort_fwd60_mean=None)
    html = _render(_make_setups(ldr))
    block = _banner_block(html)
    assert 'id="hkrv-banner-a"' in html
    assert "the leaders themselves kept climbing" not in block
    assert "the broad index did not follow" in block, "fallback history sentence must render"
