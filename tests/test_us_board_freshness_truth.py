"""The US board must tell the truth about its own freshness.

PR-2 of the US Prophet permanence program.  On 2026-08-26 the board was read as
five days stale and a force-majeure was declared over it.  The board was fresh:
`as_of` had advanced every night throughout.  What the reader actually saw was the
per-card zone-row date chip — `n.signal.asof` — and that date is neither the zone's
vintage nor a per-card fact:

  · buy_zone is rebuilt EVERY session.  Between the 2026-08-24 board (be061c6d49e9)
    and the 2026-08-25 board, 101 of 101 common tickers carrying a zone had their
    `low`/`high` move; zero held still.
  · signal.asof is a 3-session bucket clock and is BOARD-WIDE: on the 2026-08-25
    board all 133 carded rows read the identical `2026-08-21`.

So the chip printed one board constant, 133 times, against numbers four days newer
than it.  DESIGN_DOCTRINE Law 4 ("one as-of stamp per panel"; "no per-row repetition
of a constant") and Law 3 ("a number on Tier 1 arrives with its interpretation") both
land on the same fix, and this suite pins all three halves of it:

  1. the board card carries NO bare date in the zone row, even when the row has one;
  2. the page header states the vintage in plain words — "Data through <as_of>" —
     and carries a machine-readable twin on the board container for monitors;
  3. the delayed banner fires on the engine's own `staleness.delayed` verdict and
     NEVER on the healthy T+1 state (`sessions_behind == 1`, `delayed: false`), which
     is what the board looks like every evening before the nightly lands.

Import-light on purpose: the render harness is shared with
tests/test_dashboard_template_render.py, whose `_env()` mirrors
scripts/build_site.py's Jinja environment exactly.  That import pulls pandas/plotly,
so it is guarded the same way test_us_board_gate.py guards its builder tests.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.test_dashboard_template_render import _base_vm, _board_row, _env  # noqa: E402

# The board's own vintage keys, in the shape scripts/build_site.py hands the template
# (site/factordata/us_standouts.json).  ASOF is deliberately NOT equal to the signal
# bucket date: the whole defect was the two being confused for one another.
ASOF = "2026-08-25"
SIGNAL_ASOF = "2026-08-21"

PV_DT = re.compile(r'<span class="pv-dt">')
SU_PANEL = re.compile(r'<div class="panel span12 notable" id="us-standouts"[^>]*>')
# The banner ELEMENT, never the bare class name: dashboard.html.j2 names
# `.nb-stale-note` inside a CSS comment explaining what a neighbouring surface is
# deliberately NOT, so a substring test for the class passes on a board that renders
# no banner at all.
STALE_BANNER = re.compile(r'<div class="nb-stale-note">')
# Attribute VALUES carry the Tier-2 copy (data-tip-en/zh), which legitimately holds
# the demoted signal-bucket date.  Strip attributes to ask what a reader actually
# SEES without a hover.
ATTRS = re.compile(r'\s[a-zA-Z-]+="[^"]*"')


def _skip_without_render_deps() -> None:
    pytest.importorskip("pandas")
    pytest.importorskip("plotly")


def _staleness(**overrides) -> dict:
    """The artifact's own staleness block.  Defaults are the HEALTHY evening state
    measured on the shipped 2026-08-25 board: one session behind, not delayed."""
    block = {
        "price_through": ASOF,
        "age_days": 1,
        "sessions_behind": 1,
        "delayed": False,
        "unknown": False,
        "basis": "panel_majority",
    }
    block.update(overrides)
    return block


def _vm(*, as_of: str | None = ASOF, staleness: dict | None = None,
        signal_asof: str | None = SIGNAL_ASOF, rows: list | None = None) -> dict:
    vm = _base_vm()
    sig = {"asof": signal_asof} if signal_asof else None
    vm["us_standouts"] = {
        "buy": rows if rows is not None else [
            _board_row(signal=sig),
            _board_row(ticker="ZEUS", name="Zeus Industries", lane=None,
                       dossier=None, signal=sig),
        ],
        "eligible": 2,
    }
    if as_of:
        vm["us_standouts"]["as_of"] = as_of
    if staleness is not None:
        vm["us_standouts"]["staleness"] = staleness
    return vm


def _render(vm: dict) -> str:
    return _env().get_template("dashboard.html.j2").render(**vm, mode="stocks")


def _board_cards(**kw) -> str:
    """The card partial on its own — the surface scripts/build_site.py also renders
    directly for the LOCKED tier remainder, so a date that came back here would ship
    to paying readers even if the shell were clean."""
    items = kw.pop("items", None) or [_board_row(signal={"asof": SIGNAL_ASOF},
                                                 entry_signal={"status": "buy_now",
                                                               "buy_zone": {"low": 82.19,
                                                                            "high": 84.0}})]
    return _env().get_template("_us_board_cards.html.j2").render(
        items=items, sg_any=False, bs_adj=False, xu_allfeat=False,
        trg_map={}, rw_en="", rw_zh="", **kw)


# --------------------------------------------------------------------------- #
# 1 · the card stops printing a date against numbers on a different clock
# --------------------------------------------------------------------------- #

def _cards_env_ok() -> None:
    _skip_without_render_deps()


def test_board_card_prints_no_bare_date_even_when_the_row_carries_one():
    """The regression pin for the force-majeure itself.  A row WITH signal.asof must
    still render no `.pv-dt` chip — the value is untouched in the artifact, it simply
    is not the zone's vintage and no longer sits against the zone's numbers."""
    _cards_env_ok()
    html = _board_cards()
    assert "pvcard" in html, "fixture must actually produce a card"
    assert PV_DT.search(html) is None, (
        "the zone row printed a bare date again — that date is a board-wide 3-session "
        "signal-bucket constant, not the vintage of the buy-zone numbers beside it"
    )
    # The macro renders the date FORMATTED ("Aug 21" / "08-21"), never as the raw ISO,
    # so an ISO-only assertion here would pass against the very markup this pin exists
    # to forbid.  Check both rendered forms and the raw value.
    for leaked in (SIGNAL_ASOF, "Aug 21", "08-21"):
        assert leaked not in html, f"the signal bucket date leaked back onto the card: {leaked!r}"


def test_board_card_still_renders_its_zone_numbers():
    """Removing the date must not take the zone with it — the numbers are the point."""
    _cards_env_ok()
    html = _board_cards()
    assert "82.19" in html and "84.00" in html


def test_plan_cards_keep_their_honest_per_plan_dates():
    """_us_prophet_plan_cards.html.j2 passes `p.plan_asof or p.recorded_at`, which IS
    a per-plan fact.  The shared macro keeps full `date` support; only the US board
    partial stopped passing one.  If this fails, the fix was made in the macro instead
    of at the one caller that was lying."""
    _cards_env_ok()
    html = _render(_vm())
    assert PV_DT.search(html) is not None, (
        "the plan-card grid lost its dates — the date slot was removed from the shared "
        "macro rather than from the US board partial's call"
    )


# --------------------------------------------------------------------------- #
# 2 · the board states its vintage in plain words, once
# --------------------------------------------------------------------------- #

def test_header_labels_the_vintage_in_both_languages():
    _skip_without_render_deps()
    html = _render(_vm(staleness=_staleness()))
    assert "Data through" in html, "the header stopped naming what its date is the date OF"
    assert "数据截至" in html, "ZH lost the vintage label (bilingual parity)"
    assert f"<strong>{ASOF}</strong>" in html


def test_header_vintage_is_the_boards_as_of_not_the_signal_bucket():
    """The two clocks must never be swapped back.  Judged on VISIBLE text only: the
    signal date is allowed to live in this chip's hover (that is its demoted home),
    but it must never be the number a reader sees without hovering."""
    _skip_without_render_deps()
    html = _render(_vm(staleness=_staleness()))
    visible = ATTRS.sub("", html.split('id="stocks-header"', 1)[1].split("</h1>", 1)[0]
                        + html.split('class="stk-head-meta"', 1)[1].split("</div>", 1)[0])
    assert ASOF in visible
    assert SIGNAL_ASOF not in visible, (
        "the header prints the signal bucket date as the board's vintage — that is the "
        "exact clock misread as the board's freshness on 2026-08-26"
    )


def test_delayed_header_keeps_a_word_not_just_a_colour():
    """The amber dot must never be the only carrier of the warning."""
    _skip_without_render_deps()
    html = _render(_vm(staleness=_staleness(delayed=True, sessions_behind=4, age_days=4)))
    assert "Delayed · data through" in html
    assert "已延迟 · 数据截至" in html


def test_header_falls_back_cleanly_when_the_artifact_has_no_as_of():
    """An older or degraded artifact carries no as_of; the header must still render
    rather than printing an empty label."""
    _skip_without_render_deps()
    html = _render(_vm(as_of=None, staleness=None))
    assert "Data through" not in html
    assert 'class="stk-status' in html


def test_header_hover_explains_both_clocks_and_names_the_signal_date():
    """The bucket date is demoted, not deleted (DESIGN_DOCTRINE §1 demotion rule) —
    it lives on the board-level element, once, where it is true."""
    _skip_without_render_deps()
    html = _render(_vm(staleness=_staleness()))
    assert "data-tip-en=" in html
    tip = html.split('data-tip-en="', 1)[1].split('"', 1)[0]
    assert "rebuilt from scratch every session" in tip
    assert SIGNAL_ASOF in tip, "the signal bucket date lost its Tier-2 home"


def test_header_hover_stays_silent_when_the_board_disagrees_on_one_signal_date():
    """Self-falsifying: the sentence generalises ONE value to the whole board, so it
    may only render when the whole board actually carries that one value.  If a future
    artifact makes signal.asof per-card, the clause disappears instead of lying."""
    _skip_without_render_deps()
    rows = [
        _board_row(signal={"asof": "2026-08-21"}),
        _board_row(ticker="ZEUS", lane=None, dossier=None, signal={"asof": "2026-08-18"}),
    ]
    html = _render(_vm(staleness=_staleness(), rows=rows))
    tip = html.split('data-tip-en="', 1)[1].split('"', 1)[0]
    assert "2026-08-21" not in tip and "2026-08-18" not in tip


# --------------------------------------------------------------------------- #
# 3 · machine-readable twin, for monitors that grade the RENDERED page
# --------------------------------------------------------------------------- #

def test_board_container_carries_the_machine_readable_vintage():
    _skip_without_render_deps()
    html = _render(_vm(staleness=_staleness()))
    panel = SU_PANEL.search(html)
    assert panel, "#us-standouts board container missing"
    assert f'data-board-asof="{ASOF}"' in panel.group(0)
    assert 'data-board-delayed="0"' in panel.group(0)


def test_machine_readable_vintage_tracks_the_delayed_verdict():
    _skip_without_render_deps()
    html = _render(_vm(staleness=_staleness(delayed=True, sessions_behind=4)))
    panel = SU_PANEL.search(html)
    assert 'data-board-delayed="1"' in panel.group(0)


def test_machine_readable_vintage_is_absent_when_there_is_no_artifact():
    """Absence is the honest signal — a monitor must not read a stale attribute off a
    board that has no artifact behind it."""
    _skip_without_render_deps()
    html = _render(_vm(as_of=None, staleness=None))
    panel = SU_PANEL.search(html)
    assert panel and "data-board-asof" not in panel.group(0)


def test_rendered_attribute_agrees_with_the_words_in_the_header():
    """One clock, two readers: a monitor grading the attribute and a human reading the
    header must never be able to disagree."""
    _skip_without_render_deps()
    html = _render(_vm(staleness=_staleness()))
    attr = re.search(r'data-board-asof="([^"]+)"', html).group(1)
    assert f"<strong>{attr}</strong>" in html


# --------------------------------------------------------------------------- #
# 4 · the delayed banner, and the state it must never fire on
# --------------------------------------------------------------------------- #

def test_banner_is_invisible_on_the_healthy_t_plus_one_board():
    """THE frozen constraint.  The shipped 2026-08-25 board carried
    `sessions_behind: 1, delayed: false` — the designed pre-nightly state, and the
    single most likely false alarm.  The banner reads the engine's verdict, never a
    client-side day count, so weekends and holidays cannot manufacture one either."""
    _skip_without_render_deps()
    html = _render(_vm(staleness=_staleness()))
    assert STALE_BANNER.search(html) is None


def test_banner_appears_when_the_engine_says_the_board_is_delayed():
    _skip_without_render_deps()
    html = _render(_vm(staleness=_staleness(delayed=True, sessions_behind=4,
                                            age_days=4, price_through="2026-08-21")))
    assert STALE_BANNER.search(html) is not None
    assert "prices as of 2026-08-21" in html, (
        "scripts/freshness_sentinel.py::_DELAY_RE is a load-bearing contract with this "
        "exact English phrasing"
    )
    assert "4 sessions behind" in html
    assert "落后 4 个交易日" in html


def test_banner_says_so_plainly_when_the_vintage_is_unknowable():
    """Fail-closed: an undatable board is a delayed one, in plain words."""
    _skip_without_render_deps()
    html = _render(_vm(staleness=_staleness(delayed=True, unknown=True,
                                            price_through=None)))
    assert STALE_BANNER.search(html) is not None
    assert "can’t confirm how current these prices are" in html
    assert "无法确认这些价格是否最新" in html


# --------------------------------------------------------------------------- #
# 5 · house law that binds every user-facing change here
# --------------------------------------------------------------------------- #

def test_no_translated_text_in_title_attributes_on_the_new_markup():
    """CI-guarded house law (scripts/check_title_i18n.py); asserted locally too so a
    failure names the reason rather than arriving as a distant lint."""
    _skip_without_render_deps()
    html = _render(_vm(staleness=_staleness(delayed=True)))
    for m in re.finditer(r'title="([^"]*)"', html):
        assert not re.search(r"[一-鿿]", m.group(1)), (
            f"translated text inside a title= attribute: {m.group(1)!r}"
        )
