"""tests/test_hk_board_rank.py — engine/hk_board_rank.py (hk_prophet_v1).

Spec: research/HK_BOARD_RESURRECTION_MASTERPLAN_BY_FABLE.md §0 gates G1-G5.
Machinery under test is the PARAMETERISATION of engine/us_board_rank.py, so the
shared arithmetic is pinned by identity against that module (a copy that drifted
would fail here) and only the HK-specific behaviour is re-derived.

The G1 lane test runs against a fixture generated from the COMMITTED close panel
(`data/hk_search/closes_deep.parquet`) with the real `engine.signal_gate` — it is a
measurement replayed, not a hand-built board.  See ``regenerate_g1_fixture``.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from engine import hk_board_rank as hbr
from engine import us_board_rank as ubr


FIXTURE = Path(__file__).parent / "fixtures" / "hk_board_2026_07_31.json"

# The seven names the operator named as missing from the board (masterplan §1).
# 9961.HK is the HK-listed exposure standing in for PDD, which has no HK line.
WITNESSES = ("0700.HK", "9988.HK", "9618.HK", "1810.HK",
             "3690.HK", "1024.HK", "9961.HK")

BOARD_ASOF = "2026-07-31"


def regenerate_g1_fixture() -> str:
    """The exact command that produced tests/fixtures/hk_board_2026_07_31.json.

    Not run by the suite — recorded so the fixture is reproducible rather than
    mysterious.  ``TestG1FixtureIsNotStale`` re-derives the seven witnesses live and
    fails if the committed fixture no longer matches the panel, so a silently rotted
    fixture cannot keep the G1 gate green.
    """
    return (
        "python3 - <<'PY'\n"
        "import json, hashlib, pandas as pd\n"
        "from engine import signal_gate\n"
        "df = pd.read_parquet('data/hk_search/closes_deep.parquet')\n"
        "# for each column with >=250 closes: signal_gate.compact(signal_gate.gate(t, s))\n"
        "# plus the trailing 90 sessions of dates/closes and price/off_high/dir meta\n"
        "PY"
    )


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def board():
    if not FIXTURE.exists():          # pragma: no cover — the fixture is committed
        pytest.fail(f"missing G1 fixture {FIXTURE}; regenerate with "
                    f"{regenerate_g1_fixture()}")
    return json.loads(FIXTURE.read_text())


@pytest.fixture(scope="module")
def lanes(board):
    """The three display lanes, built exactly as scripts/build_hk_library.py builds them."""
    verdicts = board["verdicts"]
    meta = board["meta"]
    closes = board["closes"]

    def close_of(ticker):
        series = closes.get(ticker)
        if not series:
            return None
        return (series["dates"], series["closes"])

    momentum = hbr.total_return_z(
        {t: s["closes"] for t, s in closes.items()},
        sessions=hbr.LEADERS_MOMENTUM_SESSIONS)
    leadership = {"state": "leaders_participating", "cohesion_now": 0.9,
                  "broad_breadth_pct": 71.2, "breadth_confirming": True}

    leaders = hbr.build_leaders_rows(
        momentum, verdict_by=verdicts, meta_by=meta,
        leadership=leadership, board_asof=BOARD_ASOF)
    ran = hbr.build_ran_rows(
        verdicts, meta_by=meta, close_of=close_of,
        exclude=[r["ticker"] for r in leaders],
        leadership=leadership, board_asof=BOARD_ASOF)
    vetoed = hbr.build_vetoed_rows(
        verdicts, meta_by=meta, close_of=close_of,
        exclude=[r["ticker"] for r in leaders] + [r["ticker"] for r in ran],
        leadership=leadership, board_asof=BOARD_ASOF)
    return {"leaders": leaders, "ran": ran, "vetoed": vetoed}


def _verdict(*, eligible=False, tier="T2", ticks=1, fresh_bars=5, above200=True,
             weekly_bull=True, provisional=False, asof=BOARD_ASOF, last=None):
    return {"eligible": eligible, "tier_cascade": tier, "ticks": ticks,
            "fresh_bars": fresh_bars, "above200": above200,
            "weekly_bull": weekly_bull, "provisional": provisional,
            "asof": asof, "last": last}


def _marker(date="2026-07-06", kind="buy", quality="block",
            reason="counter-trend, no 200-reclaim/hold"):
    return {"date": date, "type": kind, "quality": quality, "reason": reason}


# --------------------------------------------------------------------------- #
# 1. frozen constants + shared-machinery identity
# --------------------------------------------------------------------------- #
class TestFrozenConstants:
    def test_definition_string(self):
        assert hbr.BOARD_DEFINITION == "hk_prophet_v1"

    def test_caps(self):
        assert (hbr.FEATURED_CAP, hbr.SECTOR_CAP, hbr.RAN_CAP) == (12, 4, 12)
        assert (hbr.LEADERS_CAP, hbr.VETOED_CAP) == (15, 12)

    def test_weights_are_the_us_object_not_a_copy(self):
        """One scoring language, two markets — a duplicated dict could drift."""
        assert hbr.SCORE_WEIGHTS is ubr.SCORE_WEIGHTS
        assert sum(hbr.SCORE_WEIGHTS.values()) == 100.0

    def test_stage_vocabulary_is_shared(self):
        assert hbr.STAGE_ORDER is ubr.STAGE_ORDER
        assert hbr.stage_for is ubr.stage_for
        assert hbr.ran_admits is ubr.ran_admits
        assert hbr.cross_read is ubr.cross_read

    def test_score_kind_carries_no_forecast_claim(self):
        text = hbr.SCORE_KIND.lower()
        assert "priority" in text and "not a calibrated return forecast" in text
        for banned in ("validated", "win rate", "win-rate", "expected return"):
            assert banned not in text

    def test_ran_window_is_the_shared_window(self):
        assert (hbr.RAN_TICKS_MIN, hbr.RAN_TICKS_MAX) == (
            ubr.RAN_TICKS_MIN, ubr.RAN_TICKS_MAX)


class TestCopy:
    """Falsifier/refutation vocabulary is never front-facing (operator, #3821)."""

    def _strings(self):
        out = [hbr.LEADERS_STANCE, hbr.LEADERS_STANCE_ZH, hbr.VETOED_STANCE,
               hbr.VETOED_STANCE_ZH, hbr.VETO_REASON_FALLBACK["en"],
               hbr.VETO_REASON_FALLBACK["zh"]]
        for copy in hbr.VETO_REASON_COPY.values():
            out.extend(copy.values())
        return out

    @pytest.mark.parametrize("banned", [
        "falsifier", "falsified", "refuted", "refutation", "证伪",
        "validated", "guaranteed", "will ",
    ])
    def test_no_banned_vocabulary(self, banned):
        for text in self._strings():
            assert banned not in text.lower(), f"banned {banned!r} in {text!r}"

    def test_leaders_stance_is_the_chartered_line(self):
        assert hbr.LEADERS_STANCE == "watch — don't chase"
        assert hbr.LEADERS_STANCE_ZH

    def test_every_veto_reason_has_both_languages(self):
        for key, copy in hbr.VETO_REASON_COPY.items():
            assert copy.get("en") and copy.get("zh"), key
        assert hbr.VETO_REASON_FALLBACK["en"] and hbr.VETO_REASON_FALLBACK["zh"]

    def test_glance_copy_never_leaks_an_internal_slug(self):
        """The engine's own reason strings are internal vocabulary, not UI copy."""
        for text in self._strings():
            assert "200-reclaim" not in text
            assert "_" not in text


# --------------------------------------------------------------------------- #
# 2. the HK selection axis (the `edge` leg's field)
# --------------------------------------------------------------------------- #
class TestSelectionAxis:
    def test_prefers_the_fused_edge_z(self):
        row = {"edge_z": 1.25, "alpha": -9.0,
               "conviction": {"axes": {"selection": {"z": -9.0}}}}
        assert hbr.selection_value(row) == 1.25

    def test_falls_back_to_the_published_axis(self):
        row = {"alpha": -9.0, "conviction": {"axes": {"selection": {"z": 0.84}}}}
        assert hbr.selection_value(row) == 0.84

    def test_falls_back_to_alpha_only_when_no_hk_leg_resolved(self):
        assert hbr.selection_value({"alpha": 0.49}) == 0.49

    def test_unknown_axis_is_none_not_zero(self):
        """Fail-closed: an unknown edge earns 0 points, never a mid-pool default."""
        assert hbr.selection_value({}) is None
        assert hbr.selection_value({"edge_z": None, "alpha": None}) is None

    def test_zero_edge_z_resolves_and_does_not_fall_through(self):
        """0.0 is a real reading — a truthiness test here would read alpha instead."""
        row = {"edge_z": 0.0, "alpha": 5.0}
        assert hbr.selection_value(row) == 0.0

    def test_zero_axis_z_resolves_and_does_not_fall_through(self):
        row = {"conviction": {"axes": {"selection": {"z": 0.0}}}, "alpha": 5.0}
        assert hbr.selection_value(row) == 0.0

    def test_nan_and_garbage_do_not_resolve(self):
        assert hbr.selection_value({"edge_z": float("nan"), "alpha": 1.0}) == 1.0
        assert hbr.selection_value({"edge_z": "n/a"}) is None

    def test_edge_leg_reads_the_hk_axis_not_alpha(self):
        """The whole point of the parameterisation: pool order follows edge_z."""
        rows = [
            {"ticker": "A", "edge_z": 2.0, "alpha": -3.0},
            {"ticker": "B", "edge_z": -1.0, "alpha": 9.0},
        ]
        pct = ubr.alpha_percentiles(rows, value_of=hbr.selection_value)
        assert pct[0] == 1.0 and pct[1] == 0.0


# --------------------------------------------------------------------------- #
# 3. G5 — laggards stop reading the entry-contaminated composite
# --------------------------------------------------------------------------- #
class TestLaggardsG5:
    def _row(self, ticker, sel, entry, composite):
        return {"ticker": ticker, "edge_z": sel,
                "conviction": {"composite_z": composite,
                               "axes": {"selection": {"z": sel},
                                        "entry": {"z": entry}}}}

    # n_lag on the live board — compute_hk_standouts(..., n_lag=6).
    N_LAG = 6

    # The six rows the 2026-07-31 board actually printed as laggards, with their
    # shipped selection / entry / composite readings.  Four of the six carried a
    # POSITIVE selection reading and were dragged in by the entry penalty alone.
    SHIPPED_LAGGARDS = [
        ("0884.HK", -2.12, -0.45, -1.426),
        ("3690.HK", +0.55, -1.25, -1.222),   # Meituan — 4th worst of 156
        ("0019.HK", +0.53, -2.88, -1.206),
        ("9618.HK", +0.84, -1.68, -1.113),   # JD
        ("0992.HK", +1.11, -2.36, -1.103),   # Lenovo
        ("1799.HK", -1.19, -0.56, -1.024),
    ]

    def _universe(self):
        """The shipped laggards plus the genuinely weak tail they were ranked above.

        The board takes the bottom ``n_lag`` of the WHOLE universe (156 names), so a
        six-row pool cannot express the defect — with six rows everything is a
        laggard.  These eight extra rows stand in for the tail: names whose
        SELECTION edge is genuinely negative, which is the only thing the lane is
        supposed to be about.  Their composites are deliberately mild so the old
        key would NOT have picked them — that is precisely the inversion under test.
        """
        pool = [self._row(t, sel, entry, comp)
                for t, sel, entry, comp in self.SHIPPED_LAGGARDS]
        pool += [self._row(f"WEAK{i}", -1.5 - i * 0.1, +1.0, -0.10 * i)
                 for i in range(8)]
        return pool

    def test_meituan_shaped_row_cannot_enter_laggards(self):
        """G5's fixture pin, with the SHIPPED 2026-07-31 numbers.

        3690.HK carried selection +0.55 and entry −1.25 and printed 4th-worst of
        156 in the middle of a +44% run.  Under the selection axis it must fall
        clean out of the bottom-``n_lag`` slice, and the genuinely weak-edge names
        must take its place.
        """
        pool = self._universe()

        composite_lane = [r["ticker"] for r in sorted(
            pool, key=lambda r: r["conviction"]["composite_z"])[:self.N_LAG]]
        assert "3690.HK" in composite_lane, "the old key is what made this a defect"
        assert "9618.HK" in composite_lane and "0992.HK" in composite_lane

        selection_lane = [r["ticker"] for r in sorted(
            pool, key=hbr.laggards_key)[:self.N_LAG]]
        for positive_edge in ("3690.HK", "0019.HK", "9618.HK", "0992.HK"):
            assert positive_edge not in selection_lane, positive_edge

    def test_every_row_in_the_new_lane_has_a_negative_selection_edge(self):
        """"Laggard" is a claim about the selection axis — and now only that."""
        lane = sorted(self._universe(), key=hbr.laggards_key)[:self.N_LAG]
        assert all(hbr.laggards_key(r) < 0 for r in lane)

    def test_positive_selection_always_sorts_behind_negative_selection(self):
        """Structural, not incidental: no entry penalty can bridge the sign gap."""
        positive = self._row("POS", +0.01, -99.0, -99.0)
        negative = self._row("NEG", -0.01, +99.0, +99.0)
        assert hbr.laggards_key(positive) > hbr.laggards_key(negative)

    def test_entry_axis_has_no_weight_at_all(self):
        a = self._row("A", 0.5, -5.0, -5.0)
        b = self._row("B", 0.5, +5.0, +5.0)
        assert hbr.laggards_key(a) == hbr.laggards_key(b)

    def test_unknown_selection_sorts_last_not_first(self):
        """An unknown edge is not evidence of a weak one — do not accuse."""
        unknown = {"ticker": "UNK"}
        weak = self._row("WEAK", -2.0, 0.0, -2.0)
        assert hbr.laggards_key(unknown) > hbr.laggards_key(weak)
        assert hbr.laggards_key(unknown) == float("inf")

    def test_zero_selection_is_ranked_not_treated_as_unknown(self):
        zero = self._row("ZERO", 0.0, 0.0, 0.0)
        assert hbr.laggards_key(zero) == 0.0


# --------------------------------------------------------------------------- #
# 4. featured — the HK turnover floor
# --------------------------------------------------------------------------- #
class TestFeaturedTurnover:
    def test_floor_value(self):
        assert hbr.FEATURED_MIN_ADV_HKD == 30_000_000.0

    def test_below_floor_is_vetoed(self):
        extra = hbr.featured_shortfalls_extra({"0001.HK": 1_000_000.0})
        assert extra({"ticker": "0001.HK"}) == ["adv_below_floor"]

    def test_above_floor_passes(self):
        extra = hbr.featured_shortfalls_extra({"0001.HK": 500_000_000.0})
        assert extra({"ticker": "0001.HK"}) == []

    def test_unknown_turnover_fails_closed(self):
        """Featured is a promotion; unknown evidence never earns the best case."""
        extra = hbr.featured_shortfalls_extra({})
        assert extra({"ticker": "0001.HK"}) == ["adv_unknown"]

    def test_row_level_adv_is_read_when_the_map_misses(self):
        extra = hbr.featured_shortfalls_extra({})
        assert extra({"ticker": "0001.HK", "adv63": 999_000_000.0}) == []

    def test_zero_turnover_is_below_floor_not_unknown(self):
        """A measured zero and an absent reading are different facts."""
        extra = hbr.featured_shortfalls_extra({"0001.HK": 0.0})
        assert extra({"ticker": "0001.HK"}) == ["adv_below_floor"]

    def test_exactly_at_the_floor_qualifies(self):
        extra = hbr.featured_shortfalls_extra(
            {"0001.HK": hbr.FEATURED_MIN_ADV_HKD})
        assert extra({"ticker": "0001.HK"}) == []


class TestScoreRows:
    def _row(self, ticker, *, edge_z, status="buy_now", adv=None):
        row = {"ticker": ticker, "sector": "Tech", "edge_z": edge_z,
               "entry_signal": {"status": status},
               "signal": {"tier_cascade": "T2", "ticks": 1, "asof": BOARD_ASOF}}
        if adv is not None:
            row["adv63"] = adv
        return row

    def test_definition_is_stamped_on_every_row(self):
        rows = hbr.score_rows([self._row("A", edge_z=1.0),
                               self._row("B", edge_z=0.0)], board_asof=BOARD_ASOF)
        assert {r["prophet"]["version"] for r in rows} == {"hk_prophet_v1"}

    def test_membership_is_untouched(self):
        pool = [self._row("A", edge_z=1.0), self._row("B", edge_z=-1.0),
                self._row("C", edge_z=0.0, status="avoid")]
        out = hbr.score_rows(pool, board_asof=BOARD_ASOF)
        assert sorted(r["ticker"] for r in out) == ["A", "B", "C"]
        assert len(out) == len(pool)

    def test_order_is_stage_then_score(self):
        pool = [self._row("BLOCKED", edge_z=9.0, status="avoid"),
                self._row("LIVE", edge_z=-9.0, status="buy_now")]
        out = hbr.score_rows(pool, board_asof=BOARD_ASOF)
        assert [r["ticker"] for r in out] == ["LIVE", "BLOCKED"]
        assert out[0]["stage"] == hbr.STAGE_LIVE
        assert out[1]["stage"] == hbr.STAGE_BLOCKED

    def test_ranks_are_stamped(self):
        out = hbr.score_rows([self._row("A", edge_z=1.0),
                              self._row("B", edge_z=0.0)], board_asof=BOARD_ASOF)
        assert [r["score_rank"] for r in out] == [1, 2]
        assert [r["display_rank"] for r in out] == [1, 2]

    def test_featured_needs_the_turnover_reading(self):
        out = hbr.score_rows([self._row("A", edge_z=1.0),
                              self._row("B", edge_z=0.5)], board_asof=BOARD_ASOF)
        assert all(r["featured"] is False for r in out)
        assert all("adv_unknown" in r["featured_blocked_by"] for r in out)

    def test_featured_lights_with_turnover(self):
        out = hbr.score_rows(
            [self._row("A", edge_z=1.0), self._row("B", edge_z=0.5)],
            adv_by={"A": 9e8, "B": 9e8}, board_asof=BOARD_ASOF)
        assert out[0]["featured"] is True

    def test_new_flag_on_a_same_session_signal(self):
        out = hbr.score_rows([self._row("A", edge_z=1.0)], board_asof=BOARD_ASOF)
        assert out[0]["new"] is True

    def test_ranking_block_discloses_the_hk_edge_and_the_turnover_gate(self):
        rows = hbr.score_rows([self._row("A", edge_z=1.0),
                               self._row("B", edge_z=0.0)], board_asof=BOARD_ASOF)
        block = hbr.ranking_block(rows)
        assert block["definition"] == "hk_prophet_v1"
        assert block["weights"] == dict(ubr.SCORE_WEIGHTS)
        edge = [f for f in block["formula_points"] if f["component"] == "edge"][0]
        assert "HK edge" in edge["reads"]
        assert any("turnover" in req for req in block["featured_requirements"])
        assert block["display_tier_lanes"] == list(hbr.DISPLAY_TIER_LANES)
        assert "component_coverage" in block

    def test_ranking_block_names_the_leadership_fence(self):
        block = hbr.ranking_block([])
        assert "no rank, size or gate authority" in block["leadership_authority"]


# --------------------------------------------------------------------------- #
# 5. G2 — the leaders lane
# --------------------------------------------------------------------------- #
class TestLeadersLane:
    def _meta(self, off_high=-5.0, name=None, **extra):
        return {"name": name, "off_high": off_high, "price": 10.0,
                "dir": "up", **extra}

    def test_ranks_on_momentum_not_on_the_selection_axis(self):
        """G2's core: a beta-neutral reading would erase a cohort rally."""
        rows = hbr.build_leaders_rows(
            {"LOW": 0.1, "HIGH": 2.0},
            verdict_by={"LOW": _verdict(), "HIGH": _verdict()},
            meta_by={"LOW": self._meta(), "HIGH": self._meta()},
            board_asof=BOARD_ASOF)
        assert [r["ticker"] for r in rows] == ["HIGH", "LOW"]

    def test_cohort_membership_boosts_the_rank_key(self):
        rows = hbr.build_leaders_rows(
            {"PLAIN": 0.4, "COHORT": 0.0},
            verdict_by={"PLAIN": _verdict(), "COHORT": _verdict()},
            meta_by={"PLAIN": self._meta(), "COHORT": self._meta()},
            cohort=["COHORT"], board_asof=BOARD_ASOF)
        # 0.0 + 0.5 boost beats a plain 0.4.
        assert [r["ticker"] for r in rows] == ["COHORT", "PLAIN"]
        assert rows[0]["rank_key"] == 0.5
        assert rows[0]["in_leadership_cohort"] is True
        assert rows[1]["in_leadership_cohort"] is False

    def test_boost_is_a_tiebreak_not_an_admission(self):
        """A cohort member that fails the trend gate is still out."""
        rows = hbr.build_leaders_rows(
            {"COHORT": 5.0},
            verdict_by={"COHORT": _verdict(above200=False)},
            meta_by={"COHORT": self._meta()},
            cohort=["COHORT"], board_asof=BOARD_ASOF)
        assert rows == []

    def test_cohort_chip_payload(self):
        rows = hbr.build_leaders_rows(
            {"COHORT": 1.0}, verdict_by={"COHORT": _verdict()},
            meta_by={"COHORT": self._meta()}, cohort=["COHORT"],
            leadership={"state": "leaders_participating", "cohesion_now": 0.9,
                        "broad_breadth_pct": 71.2, "breadth_confirming": True},
            board_asof=BOARD_ASOF)
        chip = rows[0]["leadership"]
        assert chip["id"] == "hk_leadership"
        assert chip["state"] == "leaders_participating"
        assert chip["cohesion_now"] == 0.9
        assert chip["broad_breadth_pct"] == 71.2
        assert chip["display_only"] is True
        assert chip["state_en"] and chip["state_zh"]
        assert "_" not in chip["state_en"], "the raw slug must not reach the glance tier"

    def test_no_chip_when_the_organ_did_not_run(self):
        rows = hbr.build_leaders_rows(
            {"COHORT": 1.0}, verdict_by={"COHORT": _verdict()},
            meta_by={"COHORT": self._meta()}, cohort=["COHORT"],
            leadership=None, board_asof=BOARD_ASOF)
        assert "leadership" not in rows[0]
        assert rows[0]["in_leadership_cohort"] is True

    @pytest.mark.parametrize("verdict_kwargs", [
        {"above200": False}, {"weekly_bull": False},
        {"above200": None}, {"weekly_bull": None},
    ])
    def test_trend_gates_are_is_true_tests(self, verdict_kwargs):
        rows = hbr.build_leaders_rows(
            {"A": 5.0}, verdict_by={"A": _verdict(**verdict_kwargs)},
            meta_by={"A": self._meta()}, board_asof=BOARD_ASOF)
        assert rows == []

    def test_downtrend_row_is_refused(self):
        rows = hbr.build_leaders_rows(
            {"A": 5.0}, verdict_by={"A": _verdict()},
            meta_by={"A": self._meta(dir="down")}, board_asof=BOARD_ASOF)
        assert rows == []

    def test_off_high_floor(self):
        rows = hbr.build_leaders_rows(
            {"NEAR": 1.0, "FAR": 5.0},
            verdict_by={"NEAR": _verdict(), "FAR": _verdict()},
            meta_by={"NEAR": self._meta(off_high=-19.9),
                     "FAR": self._meta(off_high=-20.1)},
            board_asof=BOARD_ASOF)
        assert [r["ticker"] for r in rows] == ["NEAR"]

    def test_exactly_at_the_off_high_floor_qualifies(self):
        rows = hbr.build_leaders_rows(
            {"A": 1.0}, verdict_by={"A": _verdict()},
            meta_by={"A": self._meta(off_high=hbr.LEADERS_OFF_HIGH_FLOOR)},
            board_asof=BOARD_ASOF)
        assert [r["ticker"] for r in rows] == ["A"]

    def test_unknown_off_high_fails_closed(self):
        rows = hbr.build_leaders_rows(
            {"A": 5.0}, verdict_by={"A": _verdict()},
            meta_by={"A": self._meta(off_high=None)}, board_asof=BOARD_ASOF)
        assert rows == []

    def test_zero_momentum_is_admitted_not_treated_as_missing(self):
        """0.0 is a real cross-sectional reading — the median name."""
        rows = hbr.build_leaders_rows(
            {"A": 0.0}, verdict_by={"A": _verdict()},
            meta_by={"A": self._meta()}, board_asof=BOARD_ASOF)
        assert [r["ticker"] for r in rows] == ["A"]
        assert rows[0]["momentum_z"] == 0.0

    def test_missing_momentum_is_skipped(self):
        rows = hbr.build_leaders_rows(
            {"A": None, "B": 1.0},
            verdict_by={"A": _verdict(), "B": _verdict()},
            meta_by={"A": self._meta(), "B": self._meta()}, board_asof=BOARD_ASOF)
        assert [r["ticker"] for r in rows] == ["B"]

    def test_exclusion_wins(self):
        rows = hbr.build_leaders_rows(
            {"A": 5.0}, verdict_by={"A": _verdict()},
            meta_by={"A": self._meta()}, exclude=["A"], board_asof=BOARD_ASOF)
        assert rows == []

    def test_cap_is_respected(self):
        momentum = {f"T{i:02d}": float(i) for i in range(30)}
        verdicts = {t: _verdict() for t in momentum}
        meta = {t: self._meta() for t in momentum}
        rows = hbr.build_leaders_rows(momentum, verdict_by=verdicts,
                                      meta_by=meta, board_asof=BOARD_ASOF)
        assert len(rows) == hbr.LEADERS_CAP

    def test_dual_class_dedup(self):
        rows = hbr.build_leaders_rows(
            {"AAA": 2.0, "BBB": 1.0},
            verdict_by={"AAA": _verdict(), "BBB": _verdict()},
            meta_by={"AAA": self._meta(name="Big Co Ltd"),
                     "BBB": self._meta(name="Big Co Ltd")},
            dedup_name=lambda n: (n or "").strip().lower() or None,
            board_asof=BOARD_ASOF)
        assert [r["ticker"] for r in rows] == ["AAA"]

    def test_rows_carry_the_stance_and_no_entry_claim(self):
        rows = hbr.build_leaders_rows(
            {"A": 1.0}, verdict_by={"A": _verdict()},
            meta_by={"A": self._meta()}, board_asof=BOARD_ASOF)
        row = rows[0]
        assert row["stance"] == hbr.LEADERS_STANCE
        assert row["stance_zh"] == hbr.LEADERS_STANCE_ZH
        assert row["display_only"] is True
        assert row["lane"] == "leader"
        assert "entry_signal" not in row
        assert "prophet" not in row


# --------------------------------------------------------------------------- #
# 6. G3 — the ran lane (B3 anchor discipline)
# --------------------------------------------------------------------------- #
class TestRanLane:
    DATES = [f"2026-07-{d:02d}" for d in (1, 2, 3, 6, 7, 8, 9, 10)]
    CLOSES = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 110.0]

    def _close_of(self, ticker):
        return (self.DATES, self.CLOSES)

    def test_marker_anchor_is_preferred(self):
        rows = hbr.build_ran_rows(
            {"A": _verdict(ticks=5, fresh_bars=4, last=_marker("2026-07-03", quality="take"))},
            meta_by={"A": {"name": "A"}}, close_of=self._close_of,
            board_asof=BOARD_ASOF)
        assert rows[0]["anchor"] == hbr.ANCHOR_MARKER
        assert rows[0]["cross_date"] == "2026-07-03"
        assert rows[0]["sessions_since"] == 5
        assert rows[0]["pct_since"] == pytest.approx(7.8, abs=0.1)

    def test_no_marker_falls_back_to_fresh_bars_sessions(self):
        rows = hbr.build_ran_rows(
            {"A": _verdict(ticks=5, fresh_bars=3, last={"type": "sell", "date": "2026-07-03"})},
            meta_by={"A": {"name": "A"}}, close_of=self._close_of,
            board_asof=BOARD_ASOF)
        assert rows[0]["anchor"] == hbr.ANCHOR_APPROX
        assert rows[0]["sessions_since"] == 3

    def test_no_anchor_at_all_drops_the_row(self):
        """B3: a missing row beats a wrong age.  ticks must never become the age."""
        rows = hbr.build_ran_rows(
            {"A": _verdict(ticks=9, fresh_bars=None, last={"type": "sell"})},
            meta_by={"A": {"name": "A"}}, close_of=self._close_of,
            board_asof=BOARD_ASOF)
        assert rows == []

    def test_ticks_are_never_used_as_the_session_count(self):
        """The measured ~3x understatement this signature exists to prevent."""
        rows = hbr.build_ran_rows(
            {"A": _verdict(ticks=9, fresh_bars=3, last={"type": "sell"})},
            meta_by={"A": {"name": "A"}}, close_of=self._close_of,
            board_asof=BOARD_ASOF)
        assert rows[0]["sessions_since"] == 3 != rows[0]["ticks"]

    def test_missing_price_series_keeps_the_row_with_a_null_move(self):
        rows = hbr.build_ran_rows(
            {"A": _verdict(ticks=5, fresh_bars=4, last=_marker("2026-07-03", quality="take"))},
            meta_by={"A": {"name": "A"}}, close_of=lambda t: None,
            board_asof=BOARD_ASOF)
        assert len(rows) == 1
        assert rows[0]["pct_since"] is None
        assert rows[0]["sessions_since"] == 4
        assert rows[0]["anchor"] == hbr.ANCHOR_MARKER

    def test_zero_fresh_bars_is_an_anchor_not_a_missing_one(self):
        rows = hbr.build_ran_rows(
            {"A": _verdict(ticks=5, fresh_bars=0, last={"type": "sell"})},
            meta_by={"A": {"name": "A"}}, close_of=lambda t: None,
            board_asof=BOARD_ASOF)
        assert len(rows) == 1
        assert rows[0]["sessions_since"] == 0

    @pytest.mark.parametrize("ticks,admitted", [
        (2, False), (3, True), (15, True), (16, False), (0, False),
    ])
    def test_tick_window_boundaries(self, ticks, admitted):
        rows = hbr.build_ran_rows(
            {"A": _verdict(ticks=ticks, fresh_bars=4, last={"type": "sell"})},
            meta_by={"A": {"name": "A"}}, close_of=lambda t: None,
            board_asof=BOARD_ASOF)
        assert bool(rows) is admitted

    def test_eligible_row_is_not_a_ran_row(self):
        rows = hbr.build_ran_rows(
            {"A": _verdict(eligible=True, ticks=5, fresh_bars=4)},
            meta_by={"A": {"name": "A"}}, close_of=lambda t: None,
            board_asof=BOARD_ASOF)
        assert rows == []

    @pytest.mark.parametrize("kwargs", [{"above200": None}, {"weekly_bull": None}])
    def test_unanalysed_trend_never_reads_as_intact(self, kwargs):
        rows = hbr.build_ran_rows(
            {"A": _verdict(ticks=5, fresh_bars=4, last={"type": "sell"}, **kwargs)},
            meta_by={"A": {"name": "A"}}, close_of=lambda t: None,
            board_asof=BOARD_ASOF)
        assert rows == []

    def test_cohort_chip_rides_the_ran_lane(self):
        rows = hbr.build_ran_rows(
            {"A": _verdict(ticks=5, fresh_bars=4, last={"type": "sell"})},
            meta_by={"A": {"name": "A"}}, close_of=lambda t: None,
            cohort=["A"],
            leadership={"state": "leaders_participating", "cohesion_now": 0.9},
            board_asof=BOARD_ASOF)
        assert rows[0]["in_leadership_cohort"] is True
        assert rows[0]["leadership"]["id"] == "hk_leadership"
        assert rows[0]["display_only"] is True

    def test_ran_rows_carry_no_entry_claim(self):
        rows = hbr.build_ran_rows(
            {"A": _verdict(ticks=5, fresh_bars=4, last={"type": "sell"})},
            meta_by={"A": {"name": "A"}}, close_of=lambda t: None,
            board_asof=BOARD_ASOF)
        assert "entry_signal" not in rows[0]
        assert "prophet" not in rows[0]
        assert rows[0]["stage"] == hbr.STAGE_RAN


# --------------------------------------------------------------------------- #
# 7. G1 / G6 — the vetoed lane
# --------------------------------------------------------------------------- #
class TestVetoedLane:
    DATES = [f"2026-07-{d:02d}" for d in (1, 2, 3, 6, 7, 8, 9, 10)]
    CLOSES = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 120.0]

    def _close_of(self, ticker):
        return (self.DATES, self.CLOSES)

    def test_admits_a_blocked_buy_marker(self):
        assert hbr.veto_admits(_verdict(last=_marker()), {}) is True

    def test_refuses_an_eligible_name(self):
        assert hbr.veto_admits(_verdict(eligible=True, last=_marker()), {}) is False

    def test_refuses_a_taken_marker(self):
        assert hbr.veto_admits(
            _verdict(last=_marker(quality="take")), {}) is False

    def test_refuses_a_sell_marker(self):
        assert hbr.veto_admits(_verdict(last=_marker(kind="sell")), {}) is False

    @pytest.mark.parametrize("weekly", [False, None])
    def test_a_veto_that_was_right_is_not_news(self, weekly):
        """A blocked signal whose weekly has since rolled over stays out."""
        assert hbr.veto_admits(
            _verdict(weekly_bull=weekly, last=_marker()), {}) is False

    def test_refuses_a_downtrend_row(self):
        assert hbr.veto_admits(_verdict(last=_marker()), {"dir": "down"}) is False

    def test_row_shape_names_the_reason_in_plain_words(self):
        rows = hbr.build_vetoed_rows(
            {"A": _verdict(fresh_bars=4, last=_marker("2026-07-03"))},
            meta_by={"A": {"name": "A Co"}}, close_of=self._close_of,
            board_asof=BOARD_ASOF)
        row = rows[0]
        assert row["lane"] == "vetoed"
        assert row["stage"] == hbr.STAGE_BLOCKED
        assert row["signal_date"] == "2026-07-03"
        assert row["sessions_since"] == 5
        assert row["pct_since"] == pytest.approx(17.6, abs=0.1)
        assert row["anchor"] == hbr.ANCHOR_MARKER
        assert row["blocked_reason_en"] == (
            "Price never held above its 200-day average after the signal")
        assert row["blocked_reason_zh"]
        assert row["reason_raw"] == "counter-trend, no 200-reclaim/hold"
        assert row["stance"] == hbr.VETOED_STANCE
        assert row["display_only"] is True
        assert "entry_signal" not in row
        assert "prophet" not in row

    def test_unknown_reason_falls_back_to_plain_copy(self):
        rows = hbr.build_vetoed_rows(
            {"A": _verdict(fresh_bars=4, last=_marker(reason="some new veto"))},
            meta_by={"A": {"name": "A"}}, close_of=lambda t: None,
            board_asof=BOARD_ASOF)
        assert rows[0]["blocked_reason_en"] == hbr.VETO_REASON_FALLBACK["en"]
        assert rows[0]["reason_raw"] == "some new veto"

    def test_no_anchor_drops_the_row(self):
        rows = hbr.build_vetoed_rows(
            {"A": _verdict(fresh_bars=None, last=_marker(date=None))},
            meta_by={"A": {"name": "A"}}, close_of=lambda t: None,
            board_asof=BOARD_ASOF)
        assert rows == []

    def test_stale_veto_is_dropped(self):
        rows = hbr.build_vetoed_rows(
            {"A": _verdict(fresh_bars=hbr.VETOED_MAX_SESSIONS + 1,
                           last={"type": "buy", "quality": "block"})},
            meta_by={"A": {"name": "A"}}, close_of=lambda t: None,
            board_asof=BOARD_ASOF)
        assert rows == []

    def test_exactly_at_the_stale_window_survives(self):
        rows = hbr.build_vetoed_rows(
            {"A": _verdict(fresh_bars=hbr.VETOED_MAX_SESSIONS,
                           last={"type": "buy", "quality": "block"})},
            meta_by={"A": {"name": "A"}}, close_of=lambda t: None,
            board_asof=BOARD_ASOF)
        assert len(rows) == 1

    def test_cohort_members_are_never_capped_out(self):
        """The names a reader goes looking for must survive a crowded lane."""
        verdicts = {f"T{i:02d}": _verdict(fresh_bars=4, last=_marker())
                    for i in range(20)}
        verdicts["COHORT"] = _verdict(fresh_bars=4, last=_marker())
        meta = {t: {"name": t} for t in verdicts}
        rows = hbr.build_vetoed_rows(
            verdicts, meta_by=meta, close_of=lambda t: None,
            cohort=["COHORT"], board_asof=BOARD_ASOF)
        assert rows[0]["ticker"] == "COHORT"
        assert len(rows) == hbr.VETOED_CAP

    def test_cohort_overflow_is_still_all_emitted(self):
        cohort = [f"C{i:02d}" for i in range(15)]
        verdicts = {t: _verdict(fresh_bars=4, last=_marker()) for t in cohort}
        rows = hbr.build_vetoed_rows(
            verdicts, meta_by={t: {"name": t} for t in cohort},
            close_of=lambda t: None, cohort=cohort, board_asof=BOARD_ASOF)
        assert len(rows) == 15, "a cohort member is never truncated"

    def test_non_cohort_tail_is_ordered_by_move(self):
        verdicts = {"SMALL": _verdict(fresh_bars=4, last=_marker()),
                    "BIG": _verdict(fresh_bars=4, last=_marker())}
        closes = {"SMALL": (self.DATES, [100.0] * 7 + [101.0]),
                  "BIG": (self.DATES, [100.0] * 7 + [150.0])}
        rows = hbr.build_vetoed_rows(
            verdicts, meta_by={t: {"name": t} for t in verdicts},
            close_of=closes.get, board_asof=BOARD_ASOF)
        assert [r["ticker"] for r in rows] == ["BIG", "SMALL"]

    def test_null_move_sorts_last_but_is_not_dropped(self):
        verdicts = {"NULL": _verdict(fresh_bars=4, last=_marker()),
                    "MOVED": _verdict(fresh_bars=4, last=_marker())}
        closes = {"MOVED": (self.DATES, self.CLOSES)}
        rows = hbr.build_vetoed_rows(
            verdicts, meta_by={t: {"name": t} for t in verdicts},
            close_of=closes.get, board_asof=BOARD_ASOF)
        assert [r["ticker"] for r in rows] == ["MOVED", "NULL"]
        assert rows[1]["pct_since"] is None

    def test_zero_move_is_ranked_not_treated_as_null(self):
        rows = hbr.build_vetoed_rows(
            {"FLAT": _verdict(fresh_bars=4, last=_marker())},
            meta_by={"FLAT": {"name": "FLAT"}},
            close_of=lambda t: (self.DATES, [100.0] * 8), board_asof=BOARD_ASOF)
        assert rows[0]["pct_since"] == 0.0

    def test_exclusion_wins(self):
        rows = hbr.build_vetoed_rows(
            {"A": _verdict(fresh_bars=4, last=_marker())},
            meta_by={"A": {"name": "A"}}, close_of=lambda t: None,
            exclude=["A"], board_asof=BOARD_ASOF)
        assert rows == []


# --------------------------------------------------------------------------- #
# 8. stage arithmetic + falsy-zero guards on the shared machinery
# --------------------------------------------------------------------------- #
class TestStageArithmetic:
    @pytest.mark.parametrize("status,stage", [
        ("buy_now", hbr.STAGE_LIVE), ("partial", hbr.STAGE_LIVE),
        ("buy_soon", hbr.STAGE_LIVE), ("extended", hbr.STAGE_RAN),
        ("hold", hbr.STAGE_RAN), ("watch", hbr.STAGE_SETTING_UP),
        ("avoid", hbr.STAGE_BLOCKED), ("blocked", hbr.STAGE_BLOCKED),
    ])
    def test_status_buckets(self, status, stage):
        assert hbr.stage_for({}, {"status": status}) == stage

    def test_unknown_status_never_advertises_live(self):
        assert hbr.stage_for({}, {"status": "brand_new"}) == hbr.STAGE_SETTING_UP
        assert hbr.stage_for({}, None) == hbr.STAGE_SETTING_UP

    def test_downtrend_is_unconditional(self):
        assert hbr.stage_for({"dir": "down"}, {"status": "buy_now"}) == hbr.STAGE_BLOCKED

    def test_stage_order_is_live_first_blocked_last(self):
        ranks = [hbr.stage_rank(s) for s in hbr.STAGE_ORDER]
        assert ranks == sorted(ranks)
        assert hbr.stage_rank(hbr.STAGE_LIVE) < hbr.stage_rank(hbr.STAGE_BLOCKED)
        assert hbr.stage_rank("nonsense") == len(hbr.STAGE_ORDER)


class TestFalsyZeroGuards:
    """The traps: a truthiness test on any of these silently inverts the answer."""

    def test_zero_ticks_is_the_freshest_signal(self):
        assert hbr.signal_value({"tier_cascade": "T2", "ticks": 0}) == 1.0

    def test_zero_fresh_bars_is_a_session_count(self):
        age, basis = hbr.signal_age({"fresh_bars": 0}, "2026-07-01", BOARD_ASOF)
        assert age == 0 and basis == hbr.BASIS_SESSIONS

    def test_zero_edge_z_scores_the_pool_position_it_earned(self):
        rows = [{"ticker": "A", "edge_z": 1.0}, {"ticker": "B", "edge_z": 0.0}]
        pct = ubr.alpha_percentiles(rows, value_of=hbr.selection_value)
        assert pct[1] == 0.0, "a zero reading is ranked, not dropped from the pool"

    def test_zero_cohesion_still_produces_a_chip(self):
        chip = hbr.leadership_chip({"state": "quiet", "cohesion_now": 0.0,
                                    "broad_breadth_pct": 0.0})
        assert chip is not None
        assert chip["cohesion_now"] == 0.0
        assert chip["broad_breadth_pct"] == 0.0

    def test_missing_state_yields_no_chip(self):
        assert hbr.leadership_chip({}) is None
        assert hbr.leadership_chip(None) is None

    def test_zero_days_since_signal_is_same_session(self):
        assert hbr.days_since_signal(BOARD_ASOF, BOARD_ASOF) == 0


class TestLaneCounts:
    def test_stage_buckets_sum_to_the_buy_lane(self):
        buy = [{"stage": hbr.STAGE_LIVE}, {"stage": hbr.STAGE_LIVE},
               {"stage": hbr.STAGE_BLOCKED}]
        counts = hbr.lane_counts(buy=buy, leaders=[1, 2], ran=[1],
                                 vetoed=[1, 2, 3], featured=2)
        assert sum(counts[s] for s in hbr.STAGE_ORDER) == len(buy)
        assert counts["buy"] == 3
        assert counts["leaders_lane"] == 2
        assert counts["ran_lane"] == 1
        assert counts["vetoed_lane"] == 3
        assert counts["featured"] == 2

    def test_every_stage_bucket_is_present_even_at_zero(self):
        counts = hbr.lane_counts(buy=[])
        for stage in hbr.STAGE_ORDER:
            assert stage in counts, "a zero is a fact, not an absence"


# --------------------------------------------------------------------------- #
# 9. G1 — the witnesses are visible (replayed measurement)
# --------------------------------------------------------------------------- #
class TestG1Witnesses:
    def test_fixture_covers_the_whole_committed_universe(self, board):
        assert len(board["verdicts"]) >= 150
        for ticker in WITNESSES:
            assert ticker in board["verdicts"], ticker

    def test_none_of_the_witnesses_can_reach_the_buy_lane(self, board):
        """The premise: this is why they were invisible, and it is unchanged.

        G6 forbids healing the veto by loosening it, so every witness is still
        cascade-INELIGIBLE after this build.  Visibility had to come from the
        display lanes, not from admitting names the gate refused.
        """
        for ticker in WITNESSES:
            assert board["verdicts"][ticker]["eligible"] is not True, ticker

    def test_at_least_five_of_seven_witnesses_are_visible(self, lanes):
        """G1's pin.  MEASURED on the committed 2026-07-31 panel: 6 of 7.

        9618.HK reaches `leaders` (it holds its 200-day average and sits 10.6% off
        its high).  3690.HK reaches `ran`.  0700 / 9988 / 1810 / 1024 reach
        `vetoed` — each blocked on the same 200-day reclaim test, one of them
        (1024.HK) on a single marker that has stood for 59 sessions.

        9961.HK is the one that stays dark, and honestly so: it is outside the
        mega-cap cohort, its trailing-quarter total return is −12%, and its move
        since the blocked marker does not beat the non-cohort field.  A lane that
        showed it anyway would be showing everything.
        """
        seen = {ticker: [lane for lane, rows in lanes.items()
                         if any(r["ticker"] == ticker for r in rows)]
                for ticker in WITNESSES}
        visible = [t for t, where in seen.items() if where]
        assert len(visible) >= 5, f"only {len(visible)} of 7 visible: {seen}"

    def test_each_visible_witness_carries_a_stance(self, lanes):
        for rows in lanes.values():
            for row in rows:
                if row["ticker"] in WITNESSES:
                    assert row.get("stance"), row["ticker"]
                    assert row.get("stance_zh"), row["ticker"]
                    assert row.get("display_only") is True

    def test_a_witness_appears_in_exactly_one_lane(self, lanes):
        """The builder excludes upstream lanes, so no name is double-counted."""
        for ticker in WITNESSES:
            hits = [lane for lane, rows in lanes.items()
                    if any(r["ticker"] == ticker for r in rows)]
            assert len(hits) <= 1, f"{ticker} appears in {hits}"

    def test_lane_caps_actually_bind_on_the_real_panel(self, lanes):
        """Without this, a witness could be 'visible' only for lack of competition."""
        assert len(lanes["leaders"]) == hbr.LEADERS_CAP
        assert len(lanes["ran"]) == hbr.RAN_CAP
        assert len(lanes["vetoed"]) == hbr.VETOED_CAP

    def test_every_vetoed_row_names_its_block_reason(self, lanes):
        for row in lanes["vetoed"]:
            assert row["blocked_reason_en"] and row["blocked_reason_zh"]
            assert row["anchor"] in (hbr.ANCHOR_MARKER, hbr.ANCHOR_APPROX)
            assert row["sessions_since"] is not None, "an unanchored row must be dropped"

    def test_the_vetoed_lane_prints_what_the_board_missed(self, lanes):
        """Self-critical by construction: the moves are real and they are shown."""
        moves = [r["pct_since"] for r in lanes["vetoed"] if r["pct_since"] is not None]
        assert moves, "the lane exists to print these"
        assert max(moves) > 20.0, "the 2026-07-31 panel carries >20% missed moves"

    def test_leaders_lane_is_momentum_ordered(self, lanes):
        keys = [r["rank_key"] for r in lanes["leaders"]]
        assert keys == sorted(keys, reverse=True)


class TestBuilderWiring:
    """End-to-end through scripts/build_hk_library.compute_hk_standouts.

    A unit-tested engine that the builder never calls is a dark lane.  This runs
    the real function over a minimal synthetic fixture (the pattern
    tests/test_hk_washout_watch.py established) and asserts the hk_prophet_v1 keys
    reach the artifact.
    """

    def _stock_json(self, ticker, *, n_bars=80):
        chart = [round(10.0 + i * 0.01, 4) for i in range(n_bars)]
        return {"ticker": ticker, "name": f"Test {ticker}", "sector": "Technology",
                "tech": {"price": chart[-1], "rsi14": 38.0, "ma200": 15.0,
                         "off_52w_high_pct": -0.25},
                "chart": {"c": chart}, "conviction": None}

    def _scoreboard_row(self, ticker):
        return {"ticker": ticker, "name": f"Test {ticker}", "sector": "Technology",
                "sector_zh": "科技", "cycle": "DECLINE", "cycle_zh": "DECLINE",
                "cycle_dir": "down", "beta": 1.2, "role": "cyclical",
                "tilt": "growth", "price": 10.0}

    @pytest.fixture
    def built(self, tmp_path, monkeypatch):
        import json as _json
        import lib.config as cfg_module
        from scripts.build_hk_library import compute_hk_standouts

        tickers = ["9988.HK", "0700.HK", "9618.HK", "3690.HK", "1810.HK"]
        hd = tmp_path / "site" / "hkstockdata"
        hd.mkdir(parents=True, exist_ok=True)
        for ticker in tickers:
            (hd / f"{ticker}.json").write_text(_json.dumps(self._stock_json(ticker)))
        monkeypatch.setattr(cfg_module, "ROOT", tmp_path)
        out = compute_hk_standouts({
            "as_of": "2026-07-08", "risk_state": "risk_off",
            "modes": {"all": [self._scoreboard_row(t) for t in tickers]},
        })
        if out is None:                       # pragma: no cover — env-dependent
            pytest.skip("compute_hk_standouts returned None — enriched < 4 here")
        return out

    def test_board_definition_is_stamped(self, built):
        assert built["rank_by"] == "hk_prophet_v1"
        assert built["board_definition"] == "hk_prophet_v1"

    def test_every_new_lane_key_is_present(self, built):
        for key in ("leaders", "ran", "vetoed", "ranking", "lane_counts"):
            assert key in built, key
            assert built[key] is not None, key
        for lane in ("leaders", "ran", "vetoed"):
            assert isinstance(built[lane], list), lane

    def test_universe_gap_is_disclosed_as_a_number(self, built):
        """G7: a count that moved is not a disclosure — print the excluded count."""
        assert isinstance(built["universe_excluded"], int)
        assert isinstance(built["universe_source_rows"], int)
        assert built["universe_source_rows"] >= built["universe"]
        assert (built["universe_source_rows"] - built["universe"]
                == built["universe_excluded"])

    def test_ranking_receipt_reaches_the_artifact(self, built):
        block = built["ranking"]
        assert block["definition"] == "hk_prophet_v1"
        assert block["score_kind"] == hbr.SCORE_KIND
        assert block["display_tier_lanes"] == list(hbr.DISPLAY_TIER_LANES)

    def test_lane_counts_agree_with_the_lanes(self, built):
        counts = built["lane_counts"]
        assert counts["buy"] == len(built["buy"])
        assert counts["leaders_lane"] == len(built["leaders"])
        assert counts["ran_lane"] == len(built["ran"])
        assert counts["vetoed_lane"] == len(built["vetoed"])
        assert counts["laggards"] == len(built["laggards"])

    def test_pre_existing_keys_survive(self, built):
        """Additive contract — the port must not delete anything the board had."""
        for key in ("as_of", "risk_state", "overlay", "calm", "buy", "watch",
                    "laggards", "eligible", "universe", "health", "board_track",
                    "leadership", "washout_watch", "context_chips"):
            assert key in built, key

    def test_off_lane_render_raises_no_ledger_alarm(self, built, monkeypatch):
        """G7: CN_LANE is unset here, so the skip is by design and must not alarm."""
        legs = {row.get("leg") for row in (built.get("health") or [])}
        assert "board_ledger" not in legs, (
            "an off-lane append skip is not a write failure")


class TestG1FixtureIsNotStale:
    """A frozen fixture that no longer matches the panel would keep G1 vacuously green.

    Re-derives the seven witnesses' verdicts LIVE from the committed parquet (about
    5s — the other 150 names stay frozen because they only provide competition for
    the caps).  A mismatch means the panel moved and the fixture needs regenerating;
    it does not mean the engine broke.
    """

    def test_source_panel_is_unchanged(self, board):
        src = Path(board["_source"])
        if not src.exists():                    # pragma: no cover — committed in-tree
            pytest.skip(f"{src} not present")
        digest = hashlib.sha256(src.read_bytes()).hexdigest()[:16]
        assert digest == board["_source_sha256_16"], (
            f"{src} changed — regenerate the fixture: {regenerate_g1_fixture()}")

    def test_witness_verdicts_replay_from_the_live_panel(self, board):
        pd = pytest.importorskip("pandas")
        from engine import signal_gate
        src = Path(board["_source"])
        if not src.exists():                    # pragma: no cover
            pytest.skip(f"{src} not present")
        panel = pd.read_parquet(src)
        for ticker in WITNESSES:
            series = panel[ticker].dropna()
            live = signal_gate.compact(signal_gate.gate(ticker, series))
            frozen = board["verdicts"][ticker]
            for key in ("eligible", "ticks", "fresh_bars", "above200", "weekly_bull"):
                assert live.get(key) == frozen[key], f"{ticker}.{key} drifted"
