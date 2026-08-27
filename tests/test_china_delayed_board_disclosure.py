"""China delayed-board disclosure — the engine verdict and the string the sentinel reads.

china.html used to render no board-lag disclosure at all, so
scripts/freshness_sentinel.py ran that surface bake-only: a China board could freeze for a
week while the page re-baked nightly and nothing would say so. This suite pins the whole
chain end to end:

    build_china_library.compute_board_staleness  →  board_staleness.delayed
        →  templates/china.html.j2 renders "prices as of YYYY-MM-DD"
            →  freshness_sentinel.board_delay_stamp parses it
                →  evaluate() breaches past the china delay budget

The contract test at the bottom is the load-bearing one: the template's English wording and
the sentinel's regex are two halves of one interface held together by nothing but this
assertion. Reword the banner without it and the sentinel silently reads a healthy page
forever — the exact failure this disclosure was built to end.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from jinja2 import ChainableUndefined, Environment, FileSystemLoader

from scripts import freshness_sentinel as fs
from scripts.build_china_library import compute_board_staleness

ROOT = Path(__file__).resolve().parent.parent

# A settled weekday evening, well clear of any mainland holiday.
NOW = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# Engine verdict
# --------------------------------------------------------------------------- #
class TestComputeBoardStaleness:
    def test_current_board_is_not_delayed(self):
        st = compute_board_staleness("2026-08-06", NOW)
        assert st["delayed"] is False
        assert st["age_days"] == 0
        assert st["inputs"]["sessions_behind"] == 0

    def test_one_session_behind_is_not_delayed(self):
        """Same >= 2 threshold the US board uses — a single late bar is not an outage."""
        st = compute_board_staleness("2026-08-05", NOW)
        assert st["inputs"]["sessions_behind"] == 1
        assert st["delayed"] is False

    def test_two_sessions_behind_is_delayed(self):
        st = compute_board_staleness("2026-08-04", NOW)
        assert st["inputs"]["sessions_behind"] == 2
        assert st["delayed"] is True

    def test_the_six_day_freeze_is_delayed(self):
        """The shape of the outage this exists for: board frozen 07-31, six days on."""
        st = compute_board_staleness("2026-07-31", NOW)
        assert st["delayed"] is True
        assert st["price_through"] == "2026-07-31"
        assert st["age_days"] == 6
        assert st["inputs"]["sessions_behind"] == 4

    def test_golden_week_is_not_delayed(self):
        """The false positive a calendar-day rule would produce every October: the board
        legitimately shows Sep 30 prices all week because no session has happened."""
        st = compute_board_staleness("2026-09-30",
                                     datetime(2026, 10, 7, 12, tzinfo=timezone.utc))
        assert st["inputs"]["expected_session"] == "2026-09-30"
        assert st["inputs"]["sessions_behind"] == 0
        assert st["delayed"] is False

    def test_spring_festival_is_not_delayed(self):
        st = compute_board_staleness("2026-02-13",
                                     datetime(2026, 2, 20, 12, tzinfo=timezone.utc))
        assert st["delayed"] is False

    def test_calendar_day_backstop_fires_without_the_holiday_table(self, monkeypatch):
        """The guard that survives a wrong holiday table. Force the session count to 0 —
        simulating a table that wrongly believes every day was a holiday — and the
        calendar-day backstop must still call a long freeze delayed."""
        from lib import cn_calendar

        monkeypatch.setattr(cn_calendar, "sessions_between", lambda *a, **k: 0)
        st = compute_board_staleness("2026-06-01", NOW)
        assert st["inputs"]["sessions_behind"] == 0          # the table learned nothing
        assert st["age_days"] > cn_calendar.MAX_LEGIT_CLOSURE_DAYS
        assert st["delayed"] is True, "backstop must catch a freeze a broken table misses"

    @pytest.mark.parametrize("bad", ["not-a-date", "", None, "2026-13-45"])
    def test_unusable_anchor_is_fail_soft(self, bad, monkeypatch):
        """A build must never die over a badge. An unreadable anchor suppresses the
        disclosure instead — delayed=False so the template renders nothing."""
        monkeypatch.setattr("scripts.build_china_library._data_through", lambda: bad)
        st = compute_board_staleness(bad, NOW)
        assert st["delayed"] is False
        assert st["price_through"] is None

    def test_raising_calendar_is_fail_soft(self, monkeypatch):
        from lib import cn_calendar

        def boom(*a, **k):
            raise RuntimeError("calendar exploded")

        monkeypatch.setattr(cn_calendar, "expected_last_session", boom)
        assert compute_board_staleness("2026-07-31", NOW) == {
            "price_through": None, "age_days": None, "delayed": False,
        }


# --------------------------------------------------------------------------- #
# Full-page render
# --------------------------------------------------------------------------- #
class _Zero(int):
    """Stand-in for every view-model field this suite does not care about: renders empty,
    counts as 0, iterates empty, and chains through any attribute or call."""

    def __new__(cls):
        return int.__new__(cls, 0)

    def __getattr__(self, k):
        return _Zero()

    def __getitem__(self, k):
        return _Zero()

    def __call__(self, *a, **k):
        return _Zero()

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0

    def get(self, k, d=None):
        return _Zero() if d is None else d

    def keys(self):
        return ()

    def items(self):
        return ()

    def __str__(self):
        return ""

    def __html__(self):
        return ""


class _Loose(dict):
    def __getattr__(self, k):
        return dict.get(self, k, _Zero())

    def __getitem__(self, k):
        try:
            return dict.__getitem__(self, k)
        except KeyError:
            return _Zero()

    def get(self, k, d=None):
        v = dict.get(self, k, None)
        return v if v is not None else (_Zero() if d is None else d)


def _render(staleness: dict | None, mode: str = "macro") -> str:
    """Render the REAL china.html.j2 against a sparse view-model.

    A snippet-extraction test cannot prove what matters here — that the block sits outside
    the macro/stocks mode split — so this renders the whole template both ways.
    """
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")),
                      autoescape=False, undefined=ChainableUndefined)
    from engine import i18n

    env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    return env.get_template("china.html.j2").render(
        mode=mode,
        board_staleness=staleness,
        latest=_Loose(date="2026-08-06", quad_name="Goldilocks"),
        market_state=_Loose(color="yellow"),
        sectors=[],
    )


DELAYED = {"price_through": "2026-07-31", "age_days": 6, "delayed": True,
           "inputs": {"expected_session": "2026-08-06", "sessions_behind": 4}}
HEALTHY = {"price_through": "2026-08-06", "age_days": 0, "delayed": False}
SUPPRESSED = {"price_through": None, "age_days": None, "delayed": False}


class TestRender:
    @pytest.mark.parametrize("mode", ["macro", "stocks"])
    def test_delayed_board_renders_the_marker(self, mode):
        html = _render(DELAYED, mode)
        assert "BOARD DELAYED" in html
        assert "prices as of 2026-07-31" in html
        assert "(6d behind)" in html

    @pytest.mark.parametrize("mode", ["macro", "stocks"])
    def test_healthy_board_renders_nothing(self, mode):
        html = _render(HEALTHY, mode)
        assert "BOARD DELAYED" not in html
        assert fs.board_delay_stamp(html) is None

    @pytest.mark.parametrize("state", [SUPPRESSED, None, {}])
    def test_absent_or_suppressed_staleness_renders_nothing(self, state):
        """Fail-soft at the template edge: a missing key must not print a marker with a
        blank date, which would breach the sentinel on an unparseable stamp."""
        html = _render(state)
        assert "BOARD DELAYED" not in html
        assert fs.board_delay_stamp(html) is None

    def test_macro_page_carries_it_even_though_it_has_no_setups_board(self):
        """china.html is the surface the sentinel watches and it renders no setups board.
        This is the assertion that fails if the block is ever moved inside the stocks-only
        half of the template."""
        html = _render(DELAYED, "macro")
        # the shelf's MARKUP, not its CSS — the stylesheet and its comments ship in both modes
        assert 'class="rip-shelf"' not in html, "macro mode should render no setups shelf"
        assert 'class="rip-shelf-title"' not in html
        assert "prices as of 2026-07-31" in html

    def test_disclosure_is_bilingual(self):
        html = _render(DELAYED, "macro")
        assert "数据延迟" in html
        assert "价格截至 2026-07-31" in html

    def test_no_translated_text_in_title_attributes(self):
        """House rule (check_title_i18n): bilingual copy ships as l-en/l-zh spans, never in
        a title= attribute."""
        html = _render(DELAYED, "macro")
        block = html[html.index("BOARD DELAYED") - 700: html.index("BOARD DELAYED") + 900]
        assert "title=" not in block

    def test_freshness_pill_agrees_with_the_banner(self):
        """One page, one verdict: the stocks header pill must not read healthy directly
        above a BOARD DELAYED banner.

        The strings moved on 2026-08-27 and the verdict did not.  The pill used to print a
        bare state word plus an UNLABELLED date ("Fresh 2026-08-06"); it now labels the
        date it was always showing ("Data through 2026-08-06" / "Delayed · data through
        2026-08-06"), so the assertions below track the new copy.  The healthy word
        "Fresh" is deliberately gone — the green dot already carries that state
        non-verbally — which is why the healthy half now asserts the LABEL is present and
        the alarm word is absent rather than looking for a word that no longer ships.  The
        alarm word itself is still mandatory: colour must never be the only carrier of a
        warning.  See tests/test_cn_board_freshness_truth.py for the full pin.
        """
        html = _render(DELAYED, "stocks")
        assert "BOARD DELAYED" in html
        assert ">Delayed · data through</span>" in html
        assert ">数据延迟 · 数据截至</span>" in html, (
            "the ZH pill must use the same word as the ZH banner (数据延迟) — one page, "
            "one name for one state"
        )
        healthy = _render(HEALTHY, "stocks")
        assert ">Data through</span>" in healthy and ">数据截至</span>" in healthy
        assert "Delayed" not in healthy.split('id="stocks-header"', 1)[1][:2000], (
            "a healthy board must not carry the alarm word in its header pill"
        )


# --------------------------------------------------------------------------- #
# Template <-> sentinel contract
# --------------------------------------------------------------------------- #
class TestSentinelContract:
    def test_rendered_marker_is_what_the_sentinel_parses(self):
        """The interface assertion. The sentinel's regex and the template's English copy are
        maintained in different files by different concerns."""
        html = _render(DELAYED, "macro")
        assert fs.board_delay_stamp(html) == "2026-07-31"

    def test_fx_widget_stamp_alone_never_registers(self):
        """china.html's only pre-existing dated string was the FX widget's own stamp, on a
        cadence of its own. Arming the surface on that would have watched a string that stays
        fresh while the board freezes — so it must not read as a board delay, even sitting in
        a page that also carries other widget as-of text."""
        page = _render(HEALTHY, "macro").replace(
            "</body>",
            '<div class="l-en">FX data as of 2026-08-07</div>'
            '<div class="l-en">rotation as of 2026-08-07</div></body>',
        )
        assert re.search(r"as of 2026-08-07", page)
        assert fs.board_delay_stamp(page) is None

    def test_end_to_end_breach_on_the_rendered_page(self):
        """Rendered page → fetch result → evaluate(). Bake stamp deliberately FRESH: the
        board froze while the page kept re-baking, which is the failure Last-Modified
        cannot see."""
        html = _render(
            {"price_through": "2026-07-20", "age_days": 19, "delayed": True}, "macro")
        now = datetime(2026, 8, 8, 5, 0, tzinfo=timezone.utc)
        results = {
            s["id"]: fs.FetchResult(
                status=200,
                last_modified=now - timedelta(hours=2),
                body=html if s["id"] == "china" else None,
            )
            for s in fs.SURFACES
        }
        report = fs.evaluate(results, now)

        assert report["ok"] is False
        assert report["stale_surfaces"] == ["china"]
        c = report["surfaces"]["china"]
        assert c["board_price_through"] == "2026-07-20"
        assert "page re-bakes are landing, board data is not" in c["detail"]

    def test_end_to_end_healthy_page_is_ok(self):
        html = _render(HEALTHY, "macro")
        now = datetime(2026, 8, 8, 5, 0, tzinfo=timezone.utc)
        results = {
            s["id"]: fs.FetchResult(
                status=200,
                last_modified=now - timedelta(hours=2),
                body=html if s["id"] == "china" else None,
            )
            for s in fs.SURFACES
        }
        report = fs.evaluate(results, now)
        assert report["ok"] is True
        assert report["surfaces"]["china"]["board_delayed"] is False

    def test_within_budget_lag_does_not_breach(self):
        """A holiday-length lag with the marker showing is disclosed, not paged."""
        html = _render(
            {"price_through": "2026-08-01", "age_days": 7, "delayed": True}, "macro")
        now = datetime(2026, 8, 8, 5, 0, tzinfo=timezone.utc)
        results = {
            s["id"]: fs.FetchResult(
                status=200,
                last_modified=now - timedelta(hours=2),
                body=html if s["id"] == "china" else None,
            )
            for s in fs.SURFACES
        }
        report = fs.evaluate(results, now)
        assert report["ok"] is True
        assert report["surfaces"]["china"]["board_delayed"] is True
        assert report["surfaces"]["china"]["status"] == "ok"


def test_china_surface_is_armed():
    """Guards the other direction: this whole suite is vacuous if the surface is bake-only."""
    china = next(s for s in fs.SURFACES if s["id"] == "china")
    assert china["delay_budget_days"] == 12
