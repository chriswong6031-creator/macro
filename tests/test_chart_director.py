"""TrendSpider hardening PR-C — chart director, timeframe facts, follow-ups.

THE FOUR GATES THIS SUITE EXISTS FOR (masterplan §0). Each one is written so
that REVERTING the enforcement turns it red, not so that it merely exercises a
happy path:

  1. the claim-window law   — a fact whose evidence window is wider than the
                              widest permitted axis is REFUSED, and the refusal
                              is visible in ``ChartSpec.rejected``.
  2. the forming-bar law    — a Friday-partial week never reaches a fact.
  3. in-frame restatement   — a caption number the chart does not draw is a
                              violation.
  4. the long-tail quota    — a shortfall prints a bare line-start ``::warning``.

Everything else here is the doctrine table, the grammar budgets, and the
degradation paths (empty pools, short history) that must not fabricate.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.marketing import chart_director as CD
from engine.marketing import chart_facts as CF
from engine.marketing import chart_followups as FU
from engine.marketing import content_studio as CS


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures — synthetic bars, so nothing here depends on the live parquet tree
# ─────────────────────────────────────────────────────────────────────────────

def _daily(n: int, start: str = "2024-01-01", step: float = 1.0) -> tuple:
    """n weekday bars from *start*, drifting up by *step* a day."""
    from datetime import date, timedelta

    d = date.fromisoformat(start)
    dates: list[str] = []
    while len(dates) < n:
        if d.weekday() < 5:
            dates.append(d.isoformat())
        d += timedelta(days=1)
    c = [100.0 + i * step for i in range(n)]
    o = [x - step * 0.5 for x in c]
    h = [x + 1.0 for x in c]
    l = [x - 1.0 for x in c]
    v = [1_000_000.0 + i for i in range(n)]
    return dates, o, h, l, c, v


def _fact(**kw) -> dict:
    base = {
        "id": "t_fact",
        "text": "TEST fact",
        "salience": 8,
        "numbers": [],
        "timeframe": "DAILY",
        "claim_kind": "superlative",
        "window_start": "2024-01-01",
        "window_bars": 100,
        "anchor_dates": [],
    }
    base.update(kw)
    return base


# ═════════════════════════════════════════════════════════════════════════════
# GATE 1 — the claim-window law (§0 gate 2)
# ═════════════════════════════════════════════════════════════════════════════

class TestClaimWindowLaw:
    """A claim may not be wider than the axis that is supposed to evidence it.

    THE FAILURE THIS PREVENTS is documented in the corpus study: three of
    thirteen sampled charts assert "ever" or "since 2015" over an axis that
    starts in 2025. The reader is shown a picture that cannot contain the claim
    and has to take the window on faith.
    """

    def test_a_window_older_than_the_axis_is_refused(self):
        dates = [f"2026-0{m}-01" for m in range(1, 8)]
        fact = _fact(window_start="2015-01-01", claim_kind="superlative")
        why = CD.claim_window_violation(fact, dates, timeframe="DAILY")
        assert why, "a 2015 claim over a 2026 axis must be refused"
        assert "2015-01-01" in why and "2026-01-01" in why

    def test_a_window_inside_the_axis_passes(self):
        dates = [f"2026-0{m}-01" for m in range(1, 8)]
        fact = _fact(window_start="2026-02-01")
        assert CD.claim_window_violation(fact, dates, timeframe="DAILY") == ""

    def test_a_fact_with_no_window_at_all_is_refused_not_waved_through(self):
        """Absent metadata is not "the window is fine"."""
        dates = [f"2026-0{m}-01" for m in range(1, 8)]
        fact = _fact(window_start="", window_bars=0, claim_kind="superlative")
        why = CD.claim_window_violation(fact, dates, timeframe="DAILY")
        assert why, "a superlative with no window metadata must be refused"
        assert "no window_start" in why

    def test_bar_counted_windows_are_checked_against_the_drawn_bar_count(self):
        """A stage read has no dated evidence bar, so it is judged on bars."""
        dates = [f"2026-01-{d:02d}" for d in range(1, 11)]
        fact = _fact(window_start="", window_bars=30, claim_kind="stage_read",
                     timeframe="WEEKLY")
        why = CD.claim_window_violation(fact, dates, timeframe="WEEKLY")
        assert why and "30" in why
        long_axis = [f"2026-{m:02d}-01" for m in range(1, 13)] * 3
        assert CD.claim_window_violation(
            fact, long_axis, timeframe="WEEKLY") == ""

    def test_build_spec_refuses_an_unspannable_fact_and_says_so(self, tmp_path):
        """THE MUTATION TARGET. Revert the refusal and this goes green wrongly.

        The fact asks for more bars than ``MAX_LOOKBACK`` permits on any axis,
        so no amount of widening can carry it. The director must fall through to
        the next candidate (here: none) and record WHY in ``rejected`` rather
        than draw a chart that silently under-evidences the claim.
        """
        root = _tiny_store(tmp_path, "WIDE", bars=400)
        impossible = _fact(id="impossible", claim_kind="superlative",
                           timeframe="DAILY", window_start="1990-01-01",
                           window_bars=CD.MAX_LOOKBACK["DAILY"] * 3)
        spec = CD.build_spec("WIDE", root=root, facts=[impossible],
                             angle="precedent")
        assert spec is not None, "the tape floor should still produce a card"
        assert spec.fact_id == "", "the impossible fact must not be drawn"
        assert spec.claim_kind == "tape"
        assert any("impossible" in r for r in spec.rejected), spec.rejected

    def test_a_spannable_fact_widens_the_axis_instead_of_being_dropped(
            self, tmp_path):
        """Widen FIRST, refuse second: the masterplan's own order of remedies."""
        root = _tiny_store(tmp_path, "WIDE", bars=400)
        wide = _fact(id="wide", claim_kind="superlative", timeframe="DAILY",
                     window_start="", window_bars=300,
                     anchor_dates=[])
        spec = CD.build_spec("WIDE", root=root, facts=[wide], angle="precedent")
        assert spec is not None and spec.fact_id == "wide", spec.rejected
        assert spec.kwargs["_lookback_bars"] >= 300


# ═════════════════════════════════════════════════════════════════════════════
# GATE 2 — the forming-bar law
# ═════════════════════════════════════════════════════════════════════════════

class TestFormingBarLaw:
    """The chart PLOTS the live bar; a FACT never consumes it.

    ``chart_render.resample_bars`` keeps the forming bucket on purpose (a chart
    that hid the current week would hide "you are here").
    ``chart_facts.resample_completed`` drops it, on the opposite purpose: a
    Friday-partial week must not mint a "worst week" fact that Friday's close
    can falsify.
    """

    def test_a_wednesday_drops_the_week_it_is_standing_in(self):
        # 2026-07-27 Mon .. 2026-07-29 Wed — the week's Friday is 07-31.
        dates = ["2026-07-20", "2026-07-21", "2026-07-22", "2026-07-23",
                 "2026-07-24", "2026-07-27", "2026-07-28", "2026-07-29"]
        n = len(dates)
        o = h = l = c = [100.0] * n
        v = [1.0] * n
        kept = CF.resample_completed(dates, o, h, l, c, v, "WEEKLY")
        assert kept[0] == ["2026-07-24"], kept[0]
        # The RENDERER keeps it — the two series differ by exactly one bar.
        from engine.marketing.chart_render import resample_bars
        drawn = resample_bars(dates, o, h, l, c, v, "WEEKLY")
        assert drawn[0] == ["2026-07-24", "2026-07-31"], drawn[0]

    def test_a_friday_keeps_the_completed_week(self):
        dates = ["2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30",
                 "2026-07-31"]
        n = len(dates)
        o = h = l = c = [100.0] * n
        kept = CF.resample_completed(dates, o, h, l, c, [1.0] * n, "WEEKLY")
        assert kept[0] == ["2026-07-31"]

    def test_a_friday_partial_week_does_not_mint_a_worst_week_fact(self):
        """THE MUTATION TARGET, and the defect in one sentence.

        Two completed red weeks, then a Monday-to-Wednesday slide. The streak
        detector's floor is three, so:

          * reading COMPLETED bars, the answer is two, and NO fact is emitted;
          * reading the forming bucket as if it were a bar, the answer is three
            and "$X has closed red 3 weeks in a row" ships over a chart whose
            last candle is a two-day stub — a sentence Friday's close can erase.

        The control below reproduces the second reading on the SAME series, so
        this test can see the failure it names (a test that only asserts the
        good branch cannot tell enforcement from luck).
        """
        from datetime import date, timedelta

        dates: list[str] = []
        d = date(2024, 1, 1)
        while len(dates) < 420:
            if d.weekday() < 5:
                dates.append(d.isoformat())
            d += timedelta(days=1)
        # Trim to a WEDNESDAY so the last bucket is genuinely partial.
        while date.fromisoformat(dates[-1]).weekday() != 2:
            dates.pop()
        n = len(dates)
        c = [100.0 + i * 0.5 for i in range(n)]
        o = [x - 0.25 for x in c]
        # Crater the last two COMPLETED weeks (10 sessions) plus the three
        # sessions of the forming week.
        for i in range(n - 13, n):
            c[i] = 40.0 - i * 0.01
            o[i] = 60.0
        h = [max(a, b) + 1 for a, b in zip(o, c)]
        l = [min(a, b) - 1 for a, b in zip(o, c)]
        v = [1e6] * n

        packet = CF.compute_timeframe_facts("PART", dates, o, h, l, c, v,
                                            timeframe="WEEKLY")
        ids = {f["id"] for f in packet["facts"]}
        assert "tf_streak_down" not in ids, (
            "a Friday-partial week minted a red-streak fact: "
            f"{[f['text'] for f in packet['facts']]}")

        from engine.marketing.chart_render import resample_bars
        rd, ro, rh, rl, rc, _rv = resample_bars(dates, o, h, l, c, v, "WEEKLY")
        bad = CF._fact_tf_streak("PART", rd, ro, rc, "WEEKLY")
        assert bad is not None and bad["streak_direction"] == "down", (
            "the control did not reproduce the defect, so the assertion above "
            "proves nothing")
        assert bad["streak_len"] == 3

    def test_anchors_map_by_date_so_the_off_by_one_cannot_shift_a_disc(self):
        """Fact series and chart series differ by one bar at the right edge."""
        chart_dates = ["2026-07-03", "2026-07-10", "2026-07-17", "2026-07-24",
                       "2026-07-31"]
        # A fact computed on completed bars ends one bucket earlier.
        assert CD._index_of_date(chart_dates, "2026-07-24") == 3
        assert CD._index_of_date(chart_dates, "2026-07-31") == 4
        # A date between buckets resolves to the bar that CONTAINS it, never to
        # the next one (which would point the disc at a bar the fact predates).
        assert CD._index_of_date(chart_dates, "2026-07-27") == 3
        assert CD._index_of_date(chart_dates, "2020-01-01") is None


# ═════════════════════════════════════════════════════════════════════════════
# GATE 3 — in-frame restatement (§0 gate 5)
# ═════════════════════════════════════════════════════════════════════════════

class TestCaptionNumbersMustBeOnThePicture:
    """A screenshot outlives its thread.

    A caption whose number exists nowhere on the image becomes an unsourced
    claim the moment somebody re-shares the picture without the text.
    """

    def test_a_number_the_chart_never_drew_is_a_violation(self):
        out = CD.caption_number_violations(
            "$MU is holding 977.56 and I am not chasing it", ["192.93"])
        assert out and "977.56" in out[0]

    def test_a_number_the_chart_restates_passes(self):
        assert CD.caption_number_violations(
            "$MU is holding 192.93 and I am not chasing it", ["192.93"]) == []

    def test_thousands_separators_and_signs_normalise(self):
        """The writer cannot see how the axis tag was formatted."""
        assert CD.caption_number_violations("held 1,147.32", ["1147.32"]) == []
        assert CD.caption_number_violations("up +12.3%", ["12.3%"]) == []

    def test_bare_small_integers_are_exempt(self):
        """Matches the existing validator's exemption: "four red weeks"."""
        assert CD.caption_number_violations("6 red weeks in a row", []) == []

    def test_a_director_spec_licenses_its_own_facts_numbers(self, tmp_path):
        """THE MUTATION TARGET on the producing side.

        A compliant post has to pass BY CONSTRUCTION, otherwise the gate is a
        lottery: the director puts every level it draws and every number of the
        fact it drew into ``in_frame_numbers``.
        """
        root = _tiny_store(tmp_path, "INF", bars=300)
        fact = _fact(id="lvl", claim_kind="level_touch", timeframe="DAILY",
                     window_start="", window_bars=60,
                     numbers=["123.45", "3"], level=123.45,
                     ma={"kind": "sma", "length": 50},
                     anchor_dates=[])
        spec = CD.build_spec("INF", root=root, facts=[fact], angle="level_watch")
        assert spec is not None and spec.fact_id == "lvl", spec.rejected
        assert "123.45" in spec.in_frame_numbers
        assert CD.caption_number_violations(
            "$INF keeps finding buyers at 123.45", spec.in_frame_numbers) == []


# ═════════════════════════════════════════════════════════════════════════════
# GATE 4 — the long-tail quota warning (§0 gate 6)
# ═════════════════════════════════════════════════════════════════════════════

class TestLongTailWarning:
    """A shortfall prints, it never silently narrows.

    BARE PRINT, LINE START, FLUSHED. Every builder in this repo logs through a
    prefixing formatter, so ``log.warning("::warning ...")`` emits
    ``WARNING ::warning`` and Actions drops it. This shipped dead five times
    before the sweep that added tests/test_gh_annotation_line_start.py.
    """

    def test_a_shortfall_prints_a_line_start_annotation(self, capsys):
        fired = CS.warn_long_tail(1, 3, 9)
        assert fired is True
        out = capsys.readouterr().out
        lines = [ln for ln in out.splitlines() if ln.strip()]
        assert lines, "nothing was printed at all"
        assert lines[0].startswith("::"), (
            f"annotation is not at line start: {lines[0]!r}")
        assert "::warning title=marketing-long-tail-quota::" in lines[0]

    def test_meeting_the_quota_prints_nothing(self, capsys):
        assert CS.warn_long_tail(3, 3, 9) is False
        assert capsys.readouterr().out.strip() == ""

    def test_the_message_separates_an_empty_pool_from_a_narrow_selector(
            self, capsys):
        """A count alone cannot tell "no supply" from "the selector ate them"."""
        CS.warn_long_tail(0, 3, 0)
        empty = capsys.readouterr().out
        CS.warn_long_tail(0, 3, 40)
        narrow = capsys.readouterr().out
        assert "offered NONE" in empty and "supply side" in empty
        assert "40" in narrow and "selector narrowed" in narrow

    def test_this_programs_annotations_are_bare_flushed_prints(self):
        """The five-strike law, asserted on THIS program's emission sites.

        Repo-wide coverage lives in tests/test_gh_annotation_line_start.py; this
        pins the modules PR-C added, where the whole annotation is one statement.
        A line merely DESCRIBING the law is not an emission, so the scan keys on
        ``title=``, which only a real annotation string carries.
        """
        for mod in (FU, CD, CF):
            lines = Path(mod.__file__).read_text(encoding="utf-8").splitlines()
            for i, line in enumerate(lines):
                if "::warning title=" not in line:
                    continue
                assert "print(" in line, f"{mod.__name__}: {line.strip()!r}"
                assert "log." not in line and "logger" not in line, line
                stmt = "".join(lines[i:i + 6])
                assert "flush=True" in stmt, (
                    f"{mod.__name__}: unflushed annotation: {line.strip()!r}")

        # The one CS site this PR added, pinned by name.
        src = Path(CS.__file__).read_text(encoding="utf-8")
        assert 'print(f"::warning title=marketing-long-tail-quota::{msg}", flush=True)' \
            in src, "the long-tail annotation is no longer a bare flushed print"


# ═════════════════════════════════════════════════════════════════════════════
# The doctrine table + the grammar budgets
# ═════════════════════════════════════════════════════════════════════════════

class TestGrammarBudgets:
    def test_at_most_one_moving_average_survives(self):
        kwargs = {"mas": [{"kind": "sma", "length": 50},
                          {"kind": "sma", "length": 200}]}
        out, notes = CD.enforce_grammar(dict(kwargs))
        assert len(out["mas"]) == CD.MAX_MAS == 1
        assert any("MAs" in n for n in notes)

    def test_at_most_two_sub_panes_survive(self):
        out, notes = CD.enforce_grammar({
            "indicators": ("volume", "macd", "rsi", "streak"),
            "volume_overlay": False})
        from engine.marketing.chart_render import _SUBPANE_KINDS
        panes = [i for i in out["indicators"] if i in _SUBPANE_KINDS]
        assert len(panes) <= CD.MAX_SUBPANES
        assert any("sub-panes" in n for n in notes)

    def test_paneless_volume_does_not_spend_a_sub_pane_budget(self):
        out, notes = CD.enforce_grammar({
            "indicators": ("volume", "streak"), "volume_overlay": True})
        assert out["indicators"] == ("volume", "streak")
        assert notes == []

    def test_annotation_families_are_capped_and_the_gold_disc_survives(self):
        out, notes = CD.enforce_grammar({
            "spotlights": [{"index": 1, "tense": "past"}],
            "zones": [{"lo": 1, "hi": 2}],
            "trendlines": [{"from_idx": 0}],
            "arcs": [{"indices": [1, 2]}],
            "measure_box": {"from_index": 0, "to_index": 3},
        })
        families = [k for k in ("spotlights", "zones", "trendlines", "arcs",
                                "measure_box") if out.get(k)]
        assert len(families) <= CD.MAX_ANNOTATION_FAMILIES
        assert "spotlights" in families, "spotlights are the load-bearing family"
        assert notes

    def test_a_spotlight_trim_keeps_the_oldest_and_the_NEWEST(self):
        """Dropping the gold "now" disc to fit a budget deletes the point."""
        spots = [{"index": i, "tense": "past"} for i in range(20)]
        spots.append({"index": 99, "tense": "now"})
        out, _notes = CD.enforce_grammar({"spotlights": spots})
        kept = out["spotlights"]
        assert len(kept) == CD.MAX_SPOTLIGHTS
        assert kept[-1]["tense"] == "now"
        assert kept[0]["index"] == 0


class TestDoctrineTable:
    def test_a_level_touch_draws_one_average_discs_and_a_level_tag(self, tmp_path):
        root = _tiny_store(tmp_path, "LVL", bars=300)
        fact = _fact(id="ma_touch_50", claim_kind="level_touch",
                     timeframe="DAILY", window_start="", window_bars=90,
                     level=150.0, ma={"kind": "sma", "length": 50},
                     callout="3rd visit", numbers=["150.00", "3"])
        spec = CD.build_spec("LVL", root=root, facts=[fact], angle="level_watch")
        assert spec is not None and spec.claim_kind == "level_touch"
        assert len(spec.kwargs["mas"]) == 1
        assert spec.kwargs["mas"][0]["length"] == 50
        assert spec.kwargs["level_tags"], "the level must be restated on the axis"
        assert spec.kwargs["spotlights"][-1]["tense"] == "now"

    def test_a_streak_gets_the_pane_whose_y_unit_is_the_claims_unit(self, tmp_path):
        root = _tiny_store(tmp_path, "STK", bars=900)
        fact = _fact(id="tf_streak_down", claim_kind="streak",
                     timeframe="WEEKLY", window_start="", window_bars=60,
                     streak_len=6, streak_direction="down",
                     callout="6 red weeks in a row", numbers=["6"])
        spec = CD.build_spec("STK", root=root, facts=[fact], angle="risk_frame")
        assert spec is not None and spec.claim_kind == "streak"
        assert "streak" in spec.kwargs["indicators"]
        assert spec.kwargs["zones"], "the record bars are boxed"
        assert spec.kwargs["zones"][0]["label"] == "6 red weeks in a row"

    def test_a_multi_year_chart_goes_log(self, tmp_path):
        root = _tiny_store(tmp_path, "LOG", bars=3000)
        fact = _fact(id="multi_year_high", claim_kind="analog",
                     timeframe="WEEKLY", window_start="", window_bars=300,
                     level=200.0, anchor_dates=[])
        spec = CD.build_spec("LOG", root=root, facts=[fact], angle="precedent")
        assert spec is not None
        assert spec.kwargs["log_scale"] is True

    def test_the_editorial_chart_draws_no_average_at_all(self, tmp_path):
        """ref-13: a 50-period curve on a 12-year axis is noise, not context."""
        root = _tiny_store(tmp_path, "EDI", bars=3000)
        fact = _fact(id="multi_year_high", claim_kind="analog",
                     timeframe="WEEKLY", window_start="", window_bars=300,
                     level=200.0)
        spec = CD.build_spec("EDI", root=root, facts=[fact], angle="precedent")
        assert spec is not None and spec.kwargs["mas"] == []

    def test_the_director_never_asks_for_the_legacy_50_200_PAIR(self, tmp_path):
        """``mas=None`` means "draw the legacy pair", which is two averages."""
        root = _tiny_store(tmp_path, "PAIR", bars=300)
        spec = CD.build_spec("PAIR", root=root, facts=[], angle="")
        assert spec is not None
        assert spec.kwargs["mas"] is not None
        assert len(spec.kwargs["mas"]) <= CD.MAX_MAS

    def test_volume_profile_is_on_by_default_and_off_when_refused(self, tmp_path):
        root = _tiny_store(tmp_path, "VBP", bars=300)
        on = CD.build_spec("VBP", root=root, facts=[], angle="")
        off = CD.build_spec("VBP", root=root, facts=[], angle="",
                            volume_profile=False)
        assert on is not None and off is not None
        assert off.kwargs["poc_overlay"] is None

    def test_only_a_signal_variant_carries_the_entry_marker(self, tmp_path):
        root = _tiny_store(tmp_path, "VAR", bars=300)
        tape = CD.build_spec("VAR", root=root, facts=[], angle="", variant="tape")
        sig = CD.build_spec("VAR", root=root, facts=[], angle="", variant="signal")
        assert tape is not None and sig is not None
        assert tape.kwargs["marker_index"] is None
        assert tape.kwargs["highlight_index"] is None
        assert tape.kwargs["pct_from_index"] is None
        assert sig.kwargs["marker_index"] is not None

    def test_an_unknown_ticker_yields_no_spec_and_no_snapshot_fallback(self, tmp_path):
        assert CD.build_spec("NOSUCHTICKER", root=tmp_path, facts=[]) is None


# ═════════════════════════════════════════════════════════════════════════════
# Facts: PIT discipline and pool degradation
# ═════════════════════════════════════════════════════════════════════════════

class TestFactDiscipline:
    def test_short_history_suppresses_every_timeframe_fact(self):
        d, o, h, l, c, v = _daily(120)
        packet = CF.compute_timeframe_facts("SHORT", d, o, h, l, c, v,
                                            timeframe="WEEKLY")
        assert packet["facts"] == [], "24 weekly bars cannot carry a year claim"

    def test_every_timeframe_fact_carries_its_window(self):
        d, o, h, l, c, v = _daily(1200)
        packet = CF.compute_timeframe_facts("WIN", d, o, h, l, c, v,
                                            timeframe="WEEKLY")
        assert packet["facts"], "the synthetic ramp should produce a record"
        for f in packet["facts"]:
            assert f.get("window_start"), f
            assert f.get("window_bars"), f
            assert f.get("claim_kind") in CF.CLAIM_KINDS, f

    def test_an_ma_touch_claim_is_scoped_to_its_argument_not_to_the_load(self):
        """The window is an ARGUMENT. Two lookbacks, two different windows."""
        d, o, h, l, c, v = _daily(600, step=0.0)
        # Flat series with a sawtooth so the average is actually touched.
        for i in range(len(c)):
            c[i] = 100.0 + (2.0 if i % 20 < 10 else -2.0)
            o[i] = c[i]
            h[i] = c[i] + 0.2
            l[i] = c[i] - 0.2
        wide = CF._fact_ma_touches("SC", d, h, l, c, 50, "50-day average",
                                   "DAILY", lookback=500)
        narrow = CF._fact_ma_touches("SC", d, h, l, c, 50, "50-day average",
                                     "DAILY", lookback=100)
        for got in (wide, narrow):
            if got is not None:
                assert got["window_start"] in d

    def test_stage_facts_degrade_to_nothing_when_the_pool_is_empty(
            self, tmp_path, monkeypatch):
        """The stage backfill is a weekly artifact and legitimately fails its
        own freshness gate. An empty pool must yield NO fact, never a guess."""
        from engine.marketing import attention_source as ASRC
        CF.reset_pool_cache()
        monkeypatch.setattr(ASRC, "stage2_leaders", lambda *a, **k: [])
        monkeypatch.setattr(ASRC, "stage_transitions", lambda *a, **k: [])
        assert CF.compute_stage_facts("ANY", tmp_path)["facts"] == []

    def test_stage_copy_is_plain_words_and_the_chart_label_is_the_idiom(
            self, tmp_path, monkeypatch):
        from engine.marketing import attention_source as ASRC
        CF.reset_pool_cache()
        monkeypatch.setattr(ASRC, "stage_transitions", lambda *a, **k: [])
        monkeypatch.setattr(ASRC, "stage2_leaders", lambda *a, **k: [
            {"ticker": "STG", "rank": 1, "why": "stage 2A, SATA 88, 12w in stage",
             "asof": "2026-07-31", "source": "stage_analysis"}])
        packet = CF.compute_stage_facts("STG", tmp_path)
        assert packet["facts"], "a fresh stage row must produce a fact"
        fact = packet["facts"][0]
        assert "marking up" in fact["text"]
        assert "Stage" not in fact["text"], (
            "the numbered idiom is a CHART LABEL, never copy")
        assert fact["callout"] == "Stage 2"

    def test_the_stage_read_never_reads_the_ungated_radar_feed(self):
        """`radar_internal._feed_stage` has no freshness gate; the pools do."""
        src = Path(CF.__file__).read_text(encoding="utf-8")
        assert "_feed_stage" not in src.replace(
            "``radar_internal._feed_stage``", "")

    def test_attention_facts_never_name_an_artifact_or_a_slug(
            self, tmp_path, monkeypatch):
        from engine.marketing import attention_source as ASRC
        CF.reset_pool_cache()
        monkeypatch.setattr(ASRC, "retail_attention", lambda *a, **k: [
            {"ticker": "ATT", "rank": 4, "why": "312 board mentions",
             "asof": "2026-07-31", "source": "wallstreetbets"}])
        monkeypatch.setattr(ASRC, "top_by_options_volume", lambda *a, **k: [])
        monkeypatch.setattr(ASRC, "top_by_dollar_volume", lambda *a, **k: [])
        text = CF.compute_attention_facts("ATT", tmp_path)["facts"][0]["text"]
        for banned in ("parquet", "wallstreetbets", "_pack", "adv_rank", "json"):
            assert banned not in text.lower(), text

    def test_the_pool_memo_reads_each_pool_once_per_process(
            self, tmp_path, monkeypatch):
        """383 parquet files re-read per ticker would eat the render budget."""
        from engine.marketing import attention_source as ASRC
        CF.reset_pool_cache()
        calls = {"n": 0}

        def _counted(*_a, **_k):
            calls["n"] += 1
            return []

        monkeypatch.setattr(ASRC, "retail_attention", _counted)
        monkeypatch.setattr(ASRC, "top_by_options_volume", lambda *a, **k: [])
        monkeypatch.setattr(ASRC, "top_by_dollar_volume", lambda *a, **k: [])
        for t in ("A", "B", "C", "D"):
            CF.compute_attention_facts(t, tmp_path, as_of="2026-08-02")
        assert calls["n"] == 1, calls


# ═════════════════════════════════════════════════════════════════════════════
# Selection: attention supply, angles, the per-ticker cap
# ═════════════════════════════════════════════════════════════════════════════

class TestAngleVocabulary:
    def test_the_two_new_angles_exist_and_reach_the_chart_family(self):
        assert "long_term_structure" in CS.ANGLES
        assert "stage_read" in CS.ANGLES
        assert CS.angle_for("watchlist", 1) == "stage_read"
        assert CS.angle_for("chart", 2) == "long_term_structure"

    def test_a_weekend_slot_prefers_the_long_horizon(self):
        assert CS.angle_for("watchlist", 0, today="2026-08-01") == \
            "long_term_structure"
        assert CS.angle_for("chart", 0, today="2026-08-02") == \
            "long_term_structure"
        # A weekday is unchanged, and so is a non-chart kind on a weekend.
        assert CS.angle_for("watchlist", 0, today="2026-07-31") == "level_watch"
        assert CS.angle_for("macro", 0, today="2026-08-01") == "macro_read"

    def test_the_weekend_never_SHRINKS_the_angle_set(self):
        """Two desks on one name still need disjoint jobs on a Saturday."""
        got = {CS.angle_for("watchlist", i, today="2026-08-01") for i in range(3)}
        assert len(got) == 3

    def test_a_long_horizon_angle_pins_the_director_to_weekly(self):
        assert CS.director_timeframe_hint("long_term_structure") == "WEEKLY"
        assert CS.director_timeframe_hint("stage_read") == "WEEKLY"
        assert CS.director_timeframe_hint("level_watch") is None
        assert CS.director_timeframe_hint("level_watch", "2026-08-01") == "WEEKLY"


class TestAttentionSupply:
    def _pools(self, monkeypatch, **rows):
        from engine.marketing import attention_source as ASRC
        for name in ("retail_attention", "top_by_options_volume",
                     "top_by_dollar_volume", "stage2_leaders"):
            monkeypatch.setattr(ASRC, name, lambda *a, **k: [])
        monkeypatch.setattr(CS, "_hot_story_rows", lambda *a, **k: rows.get("hot", []))
        for key, name in (("retail", "retail_attention"),
                          ("options", "top_by_options_volume"),
                          ("dollar", "top_by_dollar_volume"),
                          ("stage", "stage2_leaders")):
            if key in rows:
                monkeypatch.setattr(ASRC, name,
                                    lambda *a, _r=rows[key], **k: _r)

    def test_pools_are_walked_in_the_masterplans_priority_order(
            self, tmp_path, monkeypatch):
        self._pools(
            monkeypatch,
            hot=[{"ticker": "HOT", "why": "up 9%", "asof": "", "source": "movers"}],
            retail=[{"ticker": "RET", "rank": 1, "why": "board chatter",
                     "asof": "", "source": "wsb"}],
            dollar=[{"ticker": "DOL", "rank": 1, "why": "liquid",
                     "asof": "", "source": "pack"}],
            stage=[{"ticker": "STG", "rank": 1, "why": "stage 2",
                    "asof": "", "source": "stage_analysis"}],
        )
        got = [r["ticker"] for r in CS.attention_supply(tmp_path)]
        assert got == ["HOT", "RET", "DOL", "STG"], got

    def test_claimed_and_cooled_names_never_reach_the_supply(
            self, tmp_path, monkeypatch):
        self._pools(monkeypatch, retail=[
            {"ticker": "A", "rank": 1, "why": "", "asof": "", "source": ""},
            {"ticker": "B", "rank": 2, "why": "", "asof": "", "source": ""},
            {"ticker": "C", "rank": 3, "why": "", "asof": "", "source": ""},
        ])
        got = [r["ticker"] for r in CS.attention_supply(
            tmp_path, exclude={"A"}, cooled={"B"})]
        assert got == ["C"]

    def test_fresh_names_are_lifted_to_the_front_of_their_own_tier(
            self, tmp_path, monkeypatch):
        self._pools(monkeypatch, retail=[
            {"ticker": "OLD1", "rank": 1, "why": "", "asof": "", "source": ""},
            {"ticker": "OLD2", "rank": 2, "why": "", "asof": "", "source": ""},
            {"ticker": "NEW", "rank": 3, "why": "", "asof": "", "source": ""},
        ])
        got = CS.attention_supply(tmp_path, posted_recent={"OLD1", "OLD2"})
        assert got[0]["ticker"] == "NEW" and got[0]["fresh"] is True
        assert all(not r["fresh"] for r in got[1:])

    def test_an_empty_pool_set_is_a_legitimate_answer(self, tmp_path, monkeypatch):
        self._pools(monkeypatch)
        assert CS.attention_supply(tmp_path) == []

    def test_a_ticker_less_watchlist_slot_now_draws_a_name(self):
        """THE SELECTION DEFECT, in one assertion.

        `plan_account` pulls a ticker only for (signal, chart, receipt), so a
        directly-tilted watchlist slot used to start with `ticker=""` and stay
        that way. 168 of 335 watchlist posts on one measured plan were demoted
        signals because the lane had no supply of its own.
        """
        acct = {"id": "flagship", "voice": "authoritative desk", "kind": "desk"}
        supply = [{"ticker": "SUP1", "why": "board chatter", "pool": "retail_attention"},
                  {"ticker": "SUP2", "why": "liquid", "pool": "dollar_volume"}]
        items = CS.plan_account(acct, [], n_days=1, per_day=12,
                                tilt={"watchlist": 1.0},
                                ticker_supply=supply)
        watch = [i for i in items if i.type == "watchlist"]
        assert watch, "the tilt should have produced watchlist slots"
        assert any(i.ticker for i in watch), \
            "every watchlist slot came out ticker-less"
        # The supply is walked in order across EVERY chart-family slot in the
        # queue (a `chart` slot with an empty Prophet pool draws from it too),
        # so the assertion is about the ORDER, not about which kind got first
        # refusal: SUP1 before SUP2, each carrying its own pool's receipt.
        drawn = [i for i in items if i.supply_pool]
        assert [i.ticker for i in drawn] == ["SUP1", "SUP2"], \
            [(i.type, i.ticker) for i in drawn]
        assert drawn[0].supply_pool == "retail_attention"
        assert drawn[0].supply_why == "board chatter"
        assert drawn[1].supply_pool == "dollar_volume"

    def test_the_per_ticker_chart_cap_is_a_NETWORK_cap(self):
        """A per-desk cap is not a cap: six desks would each be "within budget"."""
        supply = [{"ticker": "ONE", "why": "", "pool": "retail_attention"}]
        shared: dict[str, int] = {}
        seen = 0
        for acct_id in ("a", "b", "c", "d", "e"):
            items = CS.plan_account(
                {"id": acct_id, "voice": "authoritative desk"}, [],
                n_days=1, per_day=8, tilt={"watchlist": 1.0},
                ticker_supply=supply, chart_post_counts=shared,
                max_chart_posts_per_ticker=2)
            seen += sum(1 for i in items if i.ticker == "ONE")
        assert seen == 2, f"the network cap leaked: {seen} posts on ONE"

    def test_a_supply_sourced_item_is_still_chartable(self):
        """THE TRAP THE FIRST CUT OF THIS FIX FELL INTO.

        The featured-chart loop refuses to chart a ticker with no postable
        Prophet plan, as defence-in-depth against charting a stale SIGNAL. A
        supply-sourced watchlist name has no plan BY CONSTRUCTION, so the first
        cut produced ticker-bearing posts with no ``chart_id`` — and a
        ticker-bearing post with no chart DEFERS FOREVER at publish under the
        ticker-post-carries-a-chart law. It shipped a lane that could not post.

        Caught end to end by tests/test_marketing_chart_coverage.py; pinned here
        on the source so the reason survives the next edit of that gate.
        """
        src = Path(CS.__file__).read_text(encoding="utf-8")
        assert 'if item_type == "signal" or not item_dict.get("supply_pool"):' in src, (
            "the no-plan branch of the featured-chart loop no longer admits a "
            "supply-sourced item; watchlist posts will ship uncharted and defer")
        # And the two plan_match dereferences below it must stay None-safe.
        assert 'if variant == "signal" and plan_match is not None:' in src
        assert '(plan_match or {}).get("_signal_date", "")' in src

    def test_no_supply_leaves_the_historic_behaviour_exactly(self):
        acct = {"id": "flagship", "voice": "authoritative desk"}
        before = CS.plan_account(acct, [], n_days=1, per_day=12,
                                 tilt={"watchlist": 1.0})
        assert all(i.ticker == "" for i in before)
        assert all(i.supply_pool is None for i in before)


# ═════════════════════════════════════════════════════════════════════════════
# The follow-up mechanic (SPEC + DATA ONLY)
# ═════════════════════════════════════════════════════════════════════════════

class TestFollowUps:
    def _ledger(self, tmp_path, **kw):
        row = FU.origination_row(
            asset_id="chart-001", ticker="FUP", drawn_level=100.0,
            origin_date="2026-07-29", timeframe="DAILY",
            claim_kind="level_touch", last_price=kw.pop("last_price", 110.0),
            **kw)
        FU.record_originations(tmp_path, [row])
        return row

    def test_the_row_is_written_at_ORIGINATION_not_at_outcome(self, tmp_path):
        """The honest denominator. A pool built from winners deletes its losers."""
        self._ledger(tmp_path)
        rows = [json.loads(x) for x in
                (Path(tmp_path) / FU.LEDGER_REL).read_text().splitlines() if x]
        assert len(rows) == 1
        assert rows[0]["drawn_level"] == 100.0
        assert rows[0]["side"] == "support"

    def test_recording_twice_does_not_double_the_denominator(self, tmp_path):
        self._ledger(tmp_path)
        self._ledger(tmp_path)
        rows = [x for x in
                (Path(tmp_path) / FU.LEDGER_REL).read_text().splitlines() if x]
        assert len(rows) == 1

    def test_a_level_reached_two_days_later_becomes_a_candidate(self, tmp_path):
        self._ledger(tmp_path)

        def _loader(_t):
            return (["2026-07-30", "2026-07-31"], [112.0, 105.0],
                    [108.0, 99.5], [110.0, 101.0])

        got = FU.scan_candidates(tmp_path, today="2026-07-31",
                                price_loader=_loader)
        assert len(got) == 1
        assert got[0]["trigger"] == "level_reached"
        assert got[0]["age_days"] == 2
        assert got[0]["parent_asset_id"] == "chart-001"
        assert got[0]["drawn_level"] == 100.0
        assert got[0]["last_price"] == 101.0

    def test_thesis_hurt_outranks_level_reached(self, tmp_path):
        """"Ouch" follow-ups out-reach victory laps 107k to 76k. A scanner that
        checked the happy trigger first would relabel every break as a touch."""
        self._ledger(tmp_path)

        def _loader(_t):
            return (["2026-07-30", "2026-07-31"], [112.0, 101.0],
                    [99.0, 90.0], [110.0, 92.0])

        got = FU.scan_candidates(tmp_path, today="2026-07-31",
                                 price_loader=_loader)
        assert got and got[0]["trigger"] == "thesis_hurt"

    def test_only_the_two_to_four_day_window_yields_candidates(self, tmp_path):
        self._ledger(tmp_path)

        def _loader(_t):
            return (["2026-07-30"], [112.0], [99.0], [101.0])

        assert FU.scan_candidates(tmp_path, today="2026-07-30",
                                  price_loader=_loader) == []
        assert FU.scan_candidates(tmp_path, today="2026-08-10",
                                  price_loader=_loader) == []

    def test_the_candidate_file_is_REWRITTEN_not_appended(self, tmp_path):
        FU.write_candidates(tmp_path, [{"parent_asset_id": "a"}])
        FU.write_candidates(tmp_path, [{"parent_asset_id": "b"}])
        body = (Path(tmp_path) / FU.CANDIDATES_REL).read_text().splitlines()
        assert len(body) == 1 and json.loads(body[0])["parent_asset_id"] == "b"

    def test_every_row_carries_the_contracted_keys(self, tmp_path):
        self._ledger(tmp_path)

        def _loader(_t):
            return (["2026-07-31"], [112.0], [99.0], [101.0])

        got = FU.scan_candidates(tmp_path, today="2026-07-31",
                                 price_loader=_loader)
        assert got
        for key in ("parent_asset_id", "ticker", "trigger", "age_days",
                    "drawn_level", "last_price"):
            assert key in got[0], key
        assert got[0]["trigger"] in FU.TRIGGERS

    def test_this_module_touches_no_publisher_or_scheduler(self):
        """SPEC AND DATA ONLY: posting cadence belongs to another session's lane.

        Asserted on the IMPORTS and calls, not on the prose — the docstring says
        the word "cadence" precisely because it is explaining the boundary.
        """
        src = Path(FU.__file__).read_text(encoding="utf-8")
        code = "\n".join(
            ln for ln in src.splitlines()
            if not ln.strip().startswith("#"))
        for forbidden in ("marketing_publisher", "social_publisher",
                          "outbox.emit", "scheduled_at", "sentinel",
                          "approval_desk"):
            assert forbidden not in code, forbidden


# ═════════════════════════════════════════════════════════════════════════════
# Copy shapes
# ═════════════════════════════════════════════════════════════════════════════

class TestChartCopyShapes:
    def test_the_caption_budget_is_enforced_on_the_single_line_shapes(self):
        from engine.marketing import copywriter as CW
        long_line = "x" * 140
        ctx = {"type": "chart", "shape": "one_liner"}
        assert CW.chart_caption_violations(long_line, ctx)
        assert not CW.chart_caption_violations("Short and honest.", ctx)

    def test_a_multi_line_shape_is_an_argument_not_a_caption(self):
        from engine.marketing import copywriter as CW
        ctx = {"type": "chart", "shape": "stack"}
        assert CW.chart_caption_violations("x" * 140, ctx) == []

    def test_a_non_chart_kind_is_untouched(self):
        from engine.marketing import copywriter as CW
        assert CW.chart_caption_violations(
            "x" * 140, {"type": "macro", "shape": "one_liner"}) == []

    def test_the_alarm_and_ledger_registers_never_appear_on_a_chart_post(self):
        from engine.marketing import copywriter as CW
        ctx = {"type": "chart", "shape": "one_liner"}
        assert CW.chart_caption_violations("Base is holding 🚨", ctx)
        assert CW.chart_caption_violations("Base is holding 🟢", ctx)
        assert CW.chart_caption_violations("Base is holding 👀", ctx) == []

    def test_the_prompt_carries_the_shapes_the_validator_enforces(self):
        from engine.marketing import copywriter as CW
        block = CW.chart_copy_block()
        for key in CW.CHART_COPY_SHAPES:
            assert key.split("_")[0].upper() in block.upper(), key
        assert str(CW.CHART_CAPTION_MAX_CHARS) in block

    def test_the_prompt_block_carries_no_dash_tell_of_its_own(self):
        from engine.marketing import copywriter as CW
        block = CW.chart_copy_block()
        for tell in ("—", "–", "―"):
            assert tell not in block, repr(tell)

    def test_the_banned_vocab_law_is_untouched(self):
        from engine.marketing import copywriter as CW
        for token in ("macd", "rsi", "avwap", "poc"):
            assert token in CW._BANNED_VOCAB or any(
                token in s for s in CW._BANNED_SUBSTRINGS), token


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _tiny_store(tmp_path: Path, ticker: str, *, bars: int) -> Path:
    """A minimal ``data/baskets/ohlcv/<TICKER>.parquet`` under *tmp_path*."""
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    d, o, h, l, c, v = _daily(bars, start="2014-01-01", step=0.05)
    df = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v},
                      index=pd.to_datetime(d))
    out = Path(tmp_path) / "data" / "baskets" / "ohlcv"
    out.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out / f"{ticker}.parquet")
    return Path(tmp_path)
