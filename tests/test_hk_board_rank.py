"""tests/test_hk_board_rank.py — engine/hk_board_rank.py (hk_prophet_v2 — era bumped 2026-08-03 with the reclaim-veto removal).

Spec: research/HK_BOARD_RESURRECTION_MASTERPLAN_BY_FABLE.md §0 gates G1-G5.
Machinery under test is the PARAMETERISATION of engine/us_board_rank.py, so the
shared arithmetic is pinned by identity against that module (a copy that drifted
would fail here) and only the HK-specific behaviour is re-derived.

The G1 lane test runs against a fixture generated from the COMMITTED close panel
(`data/hk_search/closes_deep.parquet`) with the real `engine.signal_gate` — it is a
measurement replayed, not a hand-built board.  See ``regenerate_g1_fixture``.
"""
from __future__ import annotations

import json
from pathlib import Path
import statistics

import pytest

from engine import hk_board_rank as hbr
from engine import signal_quality as sq
from engine import us_board_rank as ubr
from engine.setups import norm_company


FIXTURE = Path(__file__).parent / "fixtures" / "hk_board_2026_07_31.json"
# The 2026-07-31 board, frozen alongside the price panel above.  NOT
# site/factordata/hk_standouts.json — see the `prod_board` docstring.
ARTIFACT = Path(__file__).parent / "fixtures" / "hk_standouts_2026_07_31.json"

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

    THE TAIL IS 3B-PHASE-ALIGNED (2026-08-03), and that is load-bearing rather than
    cosmetic.  Both move-anchored lanes derive their anchor through
    ``signal_quality.signal_frame``, whose ``resample("3B")`` bins are anchored on the
    series' FIRST index date — so an arbitrary tail re-phases every bucket label and
    the frozen verdicts' marker dates stop being bucket labels at all.  The tail start
    is therefore walked back to a business-day multiple of 3 from the full column's
    start, and it was lengthened from 90 sessions to ~340 because a 90-session window
    cannot build the frame at all (it needs 90 buckets ≈ 270 sessions, plus the
    indicator warm-up).  The previously shipped 90-session window survives byte-for-
    byte as the suffix of each longer one.
    """
    return (
        "python3 - <<'PY'\n"
        "import json, numpy as np, pandas as pd\n"
        "from engine import signal_gate\n"
        "df = pd.read_parquet('data/hk_search/closes_deep.parquet')\n"
        "# for each column with >=250 closes: signal_gate.compact(signal_gate.gate(t, s))\n"
        "# plus ~340 trailing sessions of dates/closes (closes rounded to 3dp) whose\n"
        "# START is walked back until np.busday_count(col_start, tail_start) % 3 == 0,\n"
        "# plus price/off_high/dir meta\n"
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
def prod_board():
    """The production HK board for the fixture's own as_of — the exclusion source.

    The artifact the nightly shipped for 2026-07-31, the same session the G1 panel
    was frozen from.  Its buy and watch arrays ARE the sets the builder hands the
    lanes as `exclude`, so reading them here replays production rather than
    approximating it.

    FROZEN (incident 2026-08-04).  This read `site/factordata/hk_standouts.json`
    live, and the guard below was a `pytest.skip` — so when the nightly moved the
    board to `as_of: 2026-08-03` the pairing check stopped being a safety net and
    became an off switch: NINE G1 gates (five-of-seven witness visibility, the
    watch-strip witness, lane caps binding, the vetoed lane's missed moves) went
    silently green-by-skip, and the suite reported `154 passed, 9 skipped` for a
    board nobody was checking any more.  The pairing is now an ASSERT against a
    frozen file: it cannot drift, so if it ever fails someone regenerated one half
    of the pair without the other, and that must be loud.
    """
    assert ARTIFACT.exists(), f"missing frozen board artifact {ARTIFACT}"
    art = json.loads(ARTIFACT.read_text())
    assert str(art.get("as_of")) == BOARD_ASOF, (
        f"frozen artifact as_of {art.get('as_of')} != panel {BOARD_ASOF} — re-pin "
        f"the price panel, the artifact and BOARD_ASOF in the same commit")
    return art


@pytest.fixture(scope="module")
def lanes(board, prod_board):
    """The three display lanes, built exactly as scripts/build_hk_library.py builds them.

    HARNESS FIDELITY (adversarial review, 2026-08-03).  This fixture used to call the
    lanes with NO `exclude`, NO `dedup_name` and momentum over the full close series —
    none of which is how scripts/build_hk_library.py:1573-1609 calls them.  The
    difference is not cosmetic: it manufactured a witness.  With an empty exclusion
    1024.HK printed in `vetoed` and the measurement read 6 of 7; under production
    arguments the WATCH strip claims 1024.HK first and the lanes place 5 of 7.  A
    harness that flatters the engine is worse than no harness, so it now passes the
    builder's own arguments, and the G1 pin stands against that number.

    What is replayed, argument for argument:
      * `exclude` — the buy ∪ watch ticker sets, from the same session's artifact.
      * `dedup_name=norm_company` — the dual-class / H-share collapse.  It needs real
        company NAMES, which the frozen panel's `meta` does not carry (it stores the
        ticker), so they are backfilled from the artifact where it has them.
      * momentum over the ENRICHED panel, sliced to LEADERS_MOMENTUM_SESSIONS + 1
        exactly as the builder slices `_lane_closes`.
      * the same lane ORDER, each lane excluding the ones above it.

    Laggards are deliberately NOT in this exclusion set even though the builder now
    puts them there: the committed artifact's laggards were selected by the PRE-G5
    composite key, so feeding them here would exclude names (3690.HK, 9618.HK) that
    the shipped key does not put in that lane.  The builder-side exclusion is pinned
    directly in TestBuilderWiring instead.
    """
    verdicts = board["verdicts"]
    meta = {t: dict(m) for t, m in board["meta"].items()}
    closes = board["closes"]

    # real company names for the dedup leg (the frozen panel stores tickers)
    for lane in ("buy", "watch", "laggards"):
        for row in prod_board.get(lane) or []:
            if row.get("ticker") in meta and row.get("name"):
                meta[row["ticker"]]["name"] = row["name"]

    exclude = ({r["ticker"] for r in prod_board.get("buy") or []}
               | {r["ticker"] for r in prod_board.get("watch") or []})

    def close_of(ticker):
        series = closes.get(ticker)
        if not series:
            return None
        return (series["dates"], series["closes"])

    momentum = hbr.total_return_z(
        {t: (s["closes"] or [])[-(hbr.LEADERS_MOMENTUM_SESSIONS + 1):]
         for t, s in closes.items() if s.get("closes")},
        sessions=hbr.LEADERS_MOMENTUM_SESSIONS)
    leadership = {"state": "leaders_participating", "cohesion_now": 0.9,
                  "broad_breadth_pct": 71.2, "breadth_confirming": True}

    leaders = hbr.build_leaders_rows(
        momentum, verdict_by=verdicts, meta_by=meta,
        exclude=exclude,
        leadership=leadership, board_asof=BOARD_ASOF,
        dedup_name=norm_company)
    ran = hbr.build_ran_rows(
        verdicts, meta_by=meta, close_of=close_of,
        exclude=exclude | {r["ticker"] for r in leaders},
        leadership=leadership, board_asof=BOARD_ASOF)
    vetoed = hbr.build_vetoed_rows(
        verdicts, meta_by=meta, close_of=close_of,
        exclude=exclude | {r["ticker"] for r in leaders} | {r["ticker"] for r in ran},
        leadership=leadership, board_asof=BOARD_ASOF)
    return {"leaders": leaders, "ran": ran, "vetoed": vetoed,
            "_excluded": exclude}


@pytest.fixture(scope="module")
def frozen_lanes(board):
    """The move-anchored lanes built from the FROZEN PANEL ALONE — no artifact.

    ``lanes`` reproduces the exact production board, so it needs the shipped artifact
    and skips itself whenever that artifact has advanced past the fixture's ``as_of``
    — which is most nights, since the nightly rewrites it and the fixture is frozen.
    The anchor gates must not inherit that skip: a regression gate that is dark on any
    night the board renders is not a gate.  These lanes need only the verdicts and
    closes the fixture already carries, so they run every time.
    """
    closes = board["closes"]

    def close_of(ticker):
        series = closes.get(ticker)
        return (series["dates"], series["closes"]) if series else None

    ran = hbr.build_ran_rows(board["verdicts"], meta_by=board["meta"],
                             close_of=close_of, board_asof=BOARD_ASOF)
    vetoed = hbr.build_vetoed_rows(board["verdicts"], meta_by=board["meta"],
                                   close_of=close_of, board_asof=BOARD_ASOF)
    assert ran and vetoed, "the frozen panel must fill both move-anchored lanes"
    return {"ran": ran, "vetoed": vetoed}


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
# a close series real enough to carry a confirmation anchor
# --------------------------------------------------------------------------- #
# Both move-anchored lanes now derive their anchor through signal_quality.signal_frame
# (bucket i+2's last daily session), so an eight-point list cannot produce a move at
# ALL — every test built on one would go on passing while printing nothing but nulls,
# which is exactly the failure these tests exist to catch.  A test that passes for the
# wrong reason is worse here than one that fails, so the synthetic series is now long
# enough for the real geometry and the markers sit on real 3B bucket labels.
_SYNTH_SESSIONS = 420


def _synth_closes(tail_scale: float = 1.0, tail_len: int = 20):
    """(dates, closes, bucket_labels) — a series signal_frame will accept.

    ``tail_scale`` lifts only the last ``tail_len`` sessions, so two names can share
    one index (hence one bucket grid, hence one confirmation date per marker) and
    still differ in the move that grid measures.  ``tail_len`` must stay SHORT enough
    that a test marker's confirmation close falls outside the lifted stretch — lift
    both ends of the ratio and the move is identical again, which silently disarms
    any ordering test built on it.
    """
    import numpy as np
    import pandas as pd

    from engine import signal_quality as sq

    step = np.arange(_SYNTH_SESSIONS)
    index = pd.bdate_range("2025-01-01", periods=_SYNTH_SESSIONS)
    values = (100 + 10 * np.sin(step / 25) + 0.10 * step
              + 3 * np.sin(step / 6)).astype(float)
    if tail_scale != 1.0:
        values[-tail_len:] *= tail_scale
    series = pd.Series(values, index=index)
    frame = sq.signal_frame(series).dropna(
        subset=["macd", "sig", "k", "d", "rsi14"])
    return ([str(stamp.date()) for stamp in index],
            [float(value) for value in values],
            [str(stamp.date()) for stamp in frame.index])


def _as_series(dates, closes):
    """The (dates, closes) pair as the pandas Series signal_quality reads."""
    import pandas as pd

    return pd.Series(list(closes), index=pd.to_datetime(list(dates)))


# --------------------------------------------------------------------------- #
# 1. frozen constants + shared-machinery identity
# --------------------------------------------------------------------------- #
class TestFrozenConstants:
    def test_definition_string(self):
        assert hbr.BOARD_DEFINITION == "hk_prophet_v2"

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

    def test_the_row_key_the_builder_actually_stamps_is_read(self):
        """The fallback was dead: the builder writes `_adv63`, not `adv63`.

        Every map miss therefore fell straight through to `adv_unknown` while a good
        number sat on the row.  Pinned against the BUILDER's own spelling so the two
        halves cannot drift apart again.
        """
        import inspect

        from scripts import build_hk_library as bhl
        assert 'e["_adv63"] = adv63.get' in inspect.getsource(bhl.compute_hk_standouts)
        extra = hbr.featured_shortfalls_extra({})
        assert extra({"ticker": "0001.HK", "_adv63": 999_000_000.0}) == []

    def test_the_map_still_outranks_the_row(self):
        extra = hbr.featured_shortfalls_extra({"0001.HK": 1.0})
        assert extra({"ticker": "0001.HK", "_adv63": 999_000_000.0}) == [
            "adv_below_floor"]

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
        assert {r["prophet"]["version"] for r in rows} == {"hk_prophet_v2"}

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
        assert block["definition"] == "hk_prophet_v2"
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

    def test_marker_anchor_is_preferred_for_the_date_and_the_age(self):
        """The DATE and the AGE are still the marker's — that half is unchanged.

        The MOVE is not: this eight-session series is far too short for the 3B frame
        the confirmation anchor is derived from, so the row keeps its exact age and
        prints a disclosed null rather than the marker-anchored figure it used to.
        """
        rows = hbr.build_ran_rows(
            {"A": _verdict(ticks=5, fresh_bars=4, last=_marker("2026-07-03", quality="take"))},
            meta_by={"A": {"name": "A"}}, close_of=self._close_of,
            board_asof=BOARD_ASOF)
        assert rows[0]["anchor"] == hbr.ANCHOR_MARKER
        assert rows[0]["cross_date"] == "2026-07-03"
        assert rows[0]["sessions_since"] == 5
        assert rows[0]["pct_since"] is None
        assert rows[0]["measured_from"] is None

    def test_the_move_is_measured_from_the_confirmation_close(self):
        """MEASURED 2026-07-31: all 12 displayed HK ran rows overstated, mean +8.09pp.

        Same defect as the vetoed lane and the same fix — the marker date is a 3B
        bucket's left edge whose label reads two buckets forward, so it precedes the
        verdict by ~8 sessions and sits at the low that created the signal.
        """
        dates, closes, labels = _synth_closes()
        marker = labels[-12]
        rows = hbr.build_ran_rows(
            {"A": _verdict(ticks=5, fresh_bars=4, last=_marker(marker, quality="take"))},
            meta_by={"A": {"name": "A"}}, close_of=lambda t: (dates, closes),
            board_asof=BOARD_ASOF)
        row = rows[0]
        assert row["anchor"] == hbr.ANCHOR_CONFIRM
        assert row["cross_date"] == marker, "the DATE is still the marker's"
        assert row["measured_from"] > marker, "the MOVE starts later than the marker"
        # and it is the exact figure measured from that close, not from the marker
        assert row["pct_since"] == hbr.cross_read(
            dates, closes, cross_date=row["measured_from"])["pct_since"]
        assert row["pct_since"] != hbr.cross_read(
            dates, closes, cross_date=marker)["pct_since"]

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

    @pytest.mark.parametrize("eligible", [None, "unknown"])
    def test_an_unevaluated_cascade_is_out_not_in(self, eligible):
        """Fail-closed, like every other leg.

        The test began as `eligible is not True`, which admitted a name the cascade
        never reached — and this lane's whole claim is that the GATE refused the
        signal.  Printing that about a decision nobody made is the one error a
        self-critical lane cannot afford.
        """
        verdict = _verdict(last=_marker())
        verdict["eligible"] = eligible
        assert hbr.veto_admits(verdict, {}) is False

    def test_a_missing_eligibility_key_is_out(self):
        assert hbr.veto_admits({"weekly_bull": True, "last": _marker()}, {}) is False

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
        # eight sessions cannot build the 3B frame the move's anchor comes from, so
        # the age survives exactly and the move is a disclosed null
        assert row["pct_since"] is None
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
        """Ordered by the CONFIRMATION-anchored move — the number the lane prints.

        Both names share one index, so they share one bucket grid and one confirmation
        date; only the path between differs.  With the eight-point series this test
        used to use, every move is now null and the order collapses to the ticker
        tiebreak — it would have gone on passing while testing nothing.
        """
        dates, closes, labels = _synth_closes()
        _, big_closes, _ = _synth_closes(tail_scale=1.35)
        marker = labels[-12]
        verdicts = {"SMALL": _verdict(fresh_bars=4, last=_marker(marker)),
                    "BIG": _verdict(fresh_bars=4, last=_marker(marker))}
        series = {"SMALL": (dates, closes), "BIG": (dates, big_closes)}
        rows = hbr.build_vetoed_rows(
            verdicts, meta_by={t: {"name": t} for t in verdicts},
            close_of=series.get, board_asof=BOARD_ASOF)
        assert [r["ticker"] for r in rows] == ["BIG", "SMALL"]
        assert rows[0]["pct_since"] > rows[1]["pct_since"]
        assert rows[0]["measured_from"] == rows[1]["measured_from"] > marker

    def test_null_move_sorts_last_but_is_not_dropped(self):
        dates, closes, labels = _synth_closes()
        marker = labels[-12]
        verdicts = {"NULL": _verdict(fresh_bars=4, last=_marker(marker)),
                    "MOVED": _verdict(fresh_bars=4, last=_marker(marker))}
        series = {"MOVED": (dates, closes)}
        rows = hbr.build_vetoed_rows(
            verdicts, meta_by={t: {"name": t} for t in verdicts},
            close_of=series.get, board_asof=BOARD_ASOF)
        assert [r["ticker"] for r in rows] == ["MOVED", "NULL"]
        assert rows[0]["pct_since"] is not None, "the fixture must produce a real move"
        assert rows[1]["pct_since"] is None
        assert rows[1]["anchor"] == hbr.ANCHOR_MARKER, "no series, so no confirmation"

    def test_zero_move_is_ranked_not_treated_as_null(self):
        """0.0 is a measurement; None is the absence of one.  They must not merge.

        The marker three buckets from the end confirms on the LAST session the series
        holds, so spot and anchor are the same bar and the honest answer is exactly
        zero — the falsy value that a truthiness test would swallow into the null path.
        (A literally constant price series cannot stand in here: a flat stretch NaNs
        the StochRSI band, drops the bucket out of the frame entirely, and yields a
        null for a quite different reason.)
        """
        dates, closes, labels = _synth_closes()
        rows = hbr.build_vetoed_rows(
            {"FLAT": _verdict(fresh_bars=4, last=_marker(labels[-3]))},
            meta_by={"FLAT": {"name": "FLAT"}},
            close_of=lambda t: (dates, closes), board_asof=BOARD_ASOF)
        assert rows[0]["pct_since"] == 0.0
        assert rows[0]["measured_from"] == dates[-1]
        assert rows[0]["anchor"] == hbr.ANCHOR_CONFIRM

    # ---- the anchor itself ------------------------------------------------- #
    def test_the_move_is_measured_from_the_confirmation_close(self):
        """The defect this lane shipped: +7.16pp of mean overstatement, measured.

        `marker['date']` is the 3B bucket's LEFT edge and the label there reads two
        buckets forward, so it precedes the first close at which the block was knowable
        by ~8 sessions — and it sits at the trough that CREATED the signal.
        signal_quality._buy_filter forbids grading from it in as many words.
        """
        dates, closes, labels = _synth_closes()
        marker = labels[-12]
        rows = hbr.build_vetoed_rows(
            {"A": _verdict(fresh_bars=4, last=_marker(marker))},
            meta_by={"A": {"name": "A"}}, close_of=lambda t: (dates, closes),
            board_asof=BOARD_ASOF)
        row = rows[0]
        assert row["anchor"] == hbr.ANCHOR_CONFIRM
        assert row["signal_date"] == marker, "the block's own date is unchanged"
        assert row["measured_from"] == str(
            sq.confirmation_date(_as_series(dates, closes), marker).date())
        assert row["pct_since"] == hbr.cross_read(
            dates, closes, cross_date=row["measured_from"])["pct_since"]

    def test_a_marker_anchored_move_is_unreachable_not_merely_discouraged(self):
        """Every path that cannot confirm prints null — none falls back to the marker.

        The structural half of the fix: `pct_since` is non-null ONLY under `confirm`,
        so no future edit can quietly restore the forbidden number by widening a
        fallback.  Checked across all three non-confirming shapes.
        """
        dates, closes, labels = _synth_closes()
        marker_pct = hbr.cross_read(dates, closes,
                                    cross_date=labels[-12])["pct_since"]
        # one session INTO a bucket rather than on its label — recent enough to clear
        # the staleness gate, so the row is kept and its move is the thing under test
        off_grid = dates[dates.index(labels[-12]) + 1]
        cases = {
            # a block still inside its own confirmation window (bar i+2 unprinted)
            "PENDING": (_verdict(fresh_bars=4, last=_marker(labels[-1])),
                        lambda t: (dates, closes)),
            # a marker date that is not a bucket label of THIS series
            "OFFGRID": (_verdict(fresh_bars=4, last=_marker(off_grid)),
                        lambda t: (dates, closes)),
            # no price series at all
            "NOPRICE": (_verdict(fresh_bars=4, last=_marker(labels[-12])),
                        lambda t: None),
        }
        for name, (verdict, close_of) in cases.items():
            rows = hbr.build_vetoed_rows(
                {name: verdict}, meta_by={name: {"name": name}},
                close_of=close_of, board_asof=BOARD_ASOF)
            assert len(rows) == 1, f"{name} must survive as a disclosed null"
            assert rows[0]["pct_since"] is None, name
            assert rows[0]["measured_from"] is None, name
            assert rows[0]["anchor"] != hbr.ANCHOR_CONFIRM, name
            assert rows[0]["sessions_since"] is not None, f"{name} keeps its age"
            assert rows[0]["pct_since"] != marker_pct, (
                f"{name} fell back to the forbidden marker anchor")

    # ---- the population behind the truncated rows --------------------------- #
    def test_rows_carry_the_population_they_were_selected_from(self):
        """The lane ranks by the move and truncates, so the rows ARE the winners.

        Without the population and its middle move beside them, twelve big figures
        read as a P&L claim the lane never made.
        """
        dates, closes, labels = _synth_closes()
        _, big, _ = _synth_closes(tail_scale=1.35)
        marker = labels[-12]
        verdicts = {f"T{i:02d}": _verdict(fresh_bars=4, last=_marker(marker))
                    for i in range(20)}
        series = {t: (dates, big if int(t[1:]) % 2 else closes) for t in verdicts}
        kwargs = dict(meta_by={t: {"name": t} for t in verdicts},
                      close_of=series.get, board_asof=BOARD_ASOF)
        rows = hbr.build_vetoed_rows(verdicts, **kwargs)
        whole = hbr.build_vetoed_rows(verdicts, cap=100, **kwargs)
        assert len(rows) == hbr.VETOED_CAP < len(whole) == 20
        for row in rows:
            assert row["population"] == 20
            assert row["population_measured"] == 20
        # the rows ARE the winners: exactly the move-ordered prefix of the population
        assert [r["ticker"] for r in rows] == [r["ticker"] for r in whole][:len(rows)]
        # ...and the median is the WHOLE set's, not the displayed set's — which is the
        # entire point, since selecting on the move moves the displayed middle
        median = rows[0]["population_median_pct"]
        assert median == round(statistics.median(
            [r["pct_since"] for r in whole]), 1)
        assert statistics.median([r["pct_since"] for r in rows]) > median, (
            "the fixture must exercise a visible selection effect, or this test "
            "would pass on a lane that printed the displayed median instead")

    def test_the_median_denominator_excludes_the_disclosed_nulls(self):
        """`population_measured` is the median's base, and it is printed separately.

        Medianing the measurable rows while advertising the full count would delete
        the nulls from the denominator — the resolution-conditioned base this house
        keeps re-learning.
        """
        dates, closes, labels = _synth_closes()
        marker = labels[-12]
        verdicts = {"HAS": _verdict(fresh_bars=4, last=_marker(marker)),
                    "NULL": _verdict(fresh_bars=4, last=_marker(marker))}
        rows = hbr.build_vetoed_rows(
            verdicts, meta_by={t: {"name": t} for t in verdicts},
            close_of={"HAS": (dates, closes)}.get, board_asof=BOARD_ASOF)
        assert rows[0]["population"] == 2
        assert rows[0]["population_measured"] == 1
        assert rows[0]["population_median_pct"] == rows[0]["pct_since"]

    def test_population_median_is_null_when_nothing_is_measurable(self):
        rows = hbr.build_vetoed_rows(
            {"A": _verdict(fresh_bars=4, last=_marker())},
            meta_by={"A": {"name": "A"}}, close_of=lambda t: None,
            board_asof=BOARD_ASOF)
        assert rows[0]["population"] == 1
        assert rows[0]["population_measured"] == 0
        assert rows[0]["population_median_pct"] is None

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


class TestBasingOptIn:
    """The `basing` shelf, ported from the US board (W-E.1 / D18).

    WHAT IS AND IS NOT CLAIMED HERE.  HK's staged pool is CASCADE-GATED — the builder
    hands :func:`score_rows` only the names `hk_cascade_eligible` admitted — so a
    pre-signal BOTTOM WATCH row is structurally rare on this board in a way it is not
    on the US one: measured ZERO across all 14 committed board snapshots
    (2026-07-20..08-04).  What is under test is the ROUTING, not a population.  The
    shelf is the labelled home for the day the cycle ladder and the cascade disagree,
    so such a row lands under a heading a reader can read instead of falling through
    the template's catch-all, which renders an unknown stage LAST, below Blocked.

    The full membership fence for the split (nothing but `stage` moves, no other
    ladder state is read as basing) is pinned once, on the shared machinery, in
    tests/test_us_board_rank.py::TestBasingStage.  This class pins the HK
    PARAMETERISATION: the re-export, the keyword thread-through, and that the HK
    builder actually asks for it.
    """

    def _row(self) -> dict:
        """The HK row shape — the ladder's DISPLAY label, and no internal `state` key.

        The builder maps the scoreboard's `cycle` into `label` and never stamps
        `state` on an HK row (scripts/build_hk_library.py), so the LABEL rung of
        `is_bottom_watch` is the only one that can fire on this board.  A fixture
        carrying `state` would pin a path HK cannot reach.
        """
        return {"ticker": "8888.HK", "label": "NEARING A LOW", "dir": "down",
                "entry_signal": {"status": "watch"}}

    def test_the_re_export_is_the_shared_constant(self):
        """Same identity idiom as `test_stage_vocabulary_is_shared` — a local copy of
        the string would let the two boards' bucket names drift apart silently."""
        assert hbr.STAGE_BASING is ubr.STAGE_BASING
        assert hbr.STAGE_BASING in hbr.STAGE_ORDER

    def test_the_default_keeps_bottom_watch_in_blocked(self):
        """No opt-in, no change — the pre-shelf behaviour, byte for byte."""
        rows = hbr.score_rows([self._row()], board_asof=BOARD_ASOF)
        assert rows[0]["stage"] == hbr.STAGE_BLOCKED

    def test_the_opt_in_reaches_the_shared_engine(self):
        """The thread-through: HK's `score_rows` is a WRAPPER, so a parameter it
        accepts and forgets to forward would look wired and route nothing."""
        rows = hbr.score_rows([self._row()], board_asof=BOARD_ASOF,
                              bottom_watch_stage=hbr.STAGE_BASING)
        assert rows[0]["stage"] == hbr.STAGE_BASING

    def test_the_shelf_moves_the_row_between_display_buckets_and_nothing_else(self):
        """Display-tier, at row grain: the same row through both calls differs in
        `stage` alone.  Position stamps are compared separately because they are
        positions — they move with the bucket, which is the feature."""
        before = hbr.score_rows([self._row()], board_asof=BOARD_ASOF)[0]
        after = hbr.score_rows([self._row()], board_asof=BOARD_ASOF,
                               bottom_watch_stage=hbr.STAGE_BASING)[0]
        assert (before["stage"], after["stage"]) == (hbr.STAGE_BLOCKED,
                                                     hbr.STAGE_BASING)
        positional = {"stage", "display_rank", "score_rank"}
        assert set(before) == set(after)
        assert ({k: v for k, v in before.items() if k not in positional}
                == {k: v for k, v in after.items() if k not in positional})

    def test_the_builder_asks_for_the_shelf(self, tmp_path, monkeypatch):
        """A REAL CALL, not a source grep: the builder runs and the kwarg is recorded.

        An engine that accepts `bottom_watch_stage` while the builder never passes it
        is a dark parameter — the HK surface would ship the shelf's markup and never
        route a row to it.  The recorder delegates to the real function so the rest of
        the build is unchanged; this fixture's rows are DECLINE, so it produces no
        basing row and is not asked to.
        """
        import json as _json
        import lib.config as cfg_module
        from scripts.build_hk_library import compute_hk_standouts

        helper = TestBuilderWiring()          # same synthetic fixture, one definition
        tickers = ["9988.HK", "0700.HK", "9618.HK", "3690.HK", "1810.HK"]
        hd = tmp_path / "site" / "hkstockdata"
        hd.mkdir(parents=True, exist_ok=True)
        for ticker in tickers:
            (hd / f"{ticker}.json").write_text(_json.dumps(helper._stock_json(ticker)))
        monkeypatch.setattr(cfg_module, "ROOT", tmp_path)

        seen: list[dict] = []
        real = hbr.score_rows

        def _recorder(rows, **kwargs):
            seen.append(dict(kwargs))
            return real(rows, **kwargs)

        monkeypatch.setattr(hbr, "score_rows", _recorder)
        out = compute_hk_standouts({
            "as_of": "2026-07-08", "risk_state": "risk_off",
            "modes": {"all": [helper._scoreboard_row(t) for t in tickers]},
        })
        if out is None:                       # pragma: no cover — env-dependent
            pytest.skip("compute_hk_standouts returned None — enriched < 4 here")
        assert seen, "the builder never called hk_board_rank.score_rows"
        assert [k.get("bottom_watch_stage") for k in seen] == [hbr.STAGE_BASING], (
            "the HK builder must opt into the basing shelf explicitly")


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
        """G1's pin, against the PRODUCTION measurement: 5 of 7 through the lanes.

        9618.HK reaches `leaders` (it holds its 200-day average and sits 10.6% off
        its high).  3690.HK reaches `ran`.  0700 / 9988 / 1810 reach `vetoed`, each
        blocked on the same 200-day reclaim test.

        1024.HK does NOT reach a lane, and that is the correction the harness fix
        surfaced: it is on the board's WATCH strip, which claims its ticker before
        the vetoed lane runs, so it is visible on the page but under the watch
        strip's framing rather than with its own marker date.  Counting the watch
        strip the page shows 6 of 7 — pinned separately below so the two numbers can
        never be confused again.

        9961.HK is the one that stays dark, and honestly so: it is outside the
        mega-cap cohort, its trailing-quarter total return is −12%, and its move
        since the blocked marker does not beat the non-cohort field.  A lane that
        showed it anyway would be showing everything.
        """
        seen = {ticker: [lane for lane, rows in lanes.items()
                         if lane != "_excluded"
                         and any(r["ticker"] == ticker for r in rows)]
                for ticker in WITNESSES}
        visible = [t for t, where in seen.items() if where]
        assert len(visible) >= 5, f"only {len(visible)} of 7 visible: {seen}"

    def test_the_witness_the_lanes_miss_is_on_the_watch_strip(self, lanes, prod_board):
        """The 6th witness is reachable, just not through a display lane.

        Pins the exact fact the empty-exclusion harness hid: 1024.HK is excluded
        from `vetoed` BECAUSE the watch strip already carries it.  If a future change
        drops it from watch without adding it to a lane, the page loses a witness and
        this fails — which is the only way "6 of 7 on the page" stays true.
        """
        lane_tickers = {r["ticker"] for lane, rows in lanes.items()
                        if lane != "_excluded" for r in rows}
        watch = {r["ticker"] for r in prod_board.get("watch") or []}
        buy = {r["ticker"] for r in prod_board.get("buy") or []}
        on_page = lane_tickers | watch | buy
        visible = [t for t in WITNESSES if t in on_page]
        assert "1024.HK" in watch, "1024.HK is the watch-strip witness"
        assert "1024.HK" not in lane_tickers, (
            "a name on watch must not also occupy a display lane")
        assert len(visible) == 6, f"page-level visibility moved: {visible}"

    def test_each_visible_witness_carries_a_stance(self, lanes):
        for lane, rows in lanes.items():
            if lane == "_excluded":
                continue
            for row in rows:
                if row["ticker"] in WITNESSES:
                    assert row.get("stance"), row["ticker"]
                    assert row.get("stance_zh"), row["ticker"]
                    assert row.get("display_only") is True

    def test_a_witness_appears_in_exactly_one_lane(self, lanes):
        """The builder excludes upstream lanes, so no name is double-counted."""
        for ticker in WITNESSES:
            hits = [lane for lane, rows in lanes.items()
                    if lane != "_excluded"
                    and any(r["ticker"] == ticker for r in rows)]
            assert len(hits) <= 1, f"{ticker} appears in {hits}"

    def test_no_lane_row_belongs_to_the_buy_or_watch_lanes(self, lanes):
        """The exclusion the harness used to skip, asserted directly.

        Without this the fixture could quietly go back to an empty `exclude` and the
        G1 count would go back up to 6 with nothing failing.
        """
        excluded = lanes["_excluded"]
        assert excluded, "the production exclusion set must not be empty"
        for lane, rows in lanes.items():
            if lane == "_excluded":
                continue
            collisions = [r["ticker"] for r in rows if r["ticker"] in excluded]
            assert not collisions, f"{lane} re-lists board names: {collisions}"

    def test_lane_caps_actually_bind_on_the_real_panel(self, lanes):
        """Without this, a witness could be 'visible' only for lack of competition.

        leaders and vetoed still fill to their caps under the production exclusion.

        RE-DERIVED under the absolute session anchor (era abs-session-2026-08-06). HK now
        buckets on the HK session calendar rather than the market-blind business-day grid, so
        22 of the fixture's 157 verdicts moved — a ticks histogram dominated by −1 (14 names),
        which is the extra session per window the HK calendar carries. Exactly ONE name left
        the eligible set (0763.HK, T2 → None), so the buy∪watch exclusion no longer claims it
        and `ran` fills to RAN_CAP instead of coming back one short.

        Still pinned as an exact number, and still for the original reason: without it a
        witness could be "visible" only for lack of competition, and a drift in either
        direction must show up rather than be absorbed as slack.
        """
        assert len(lanes["leaders"]) == hbr.LEADERS_CAP
        assert len(lanes["vetoed"]) == hbr.VETOED_CAP
        assert len(lanes["ran"]) == hbr.RAN_CAP, (
            "re-measured 2026-08-06 under exclude=buy∪watch on the HK session calendar; "
            "RAN_CAP is %d" % hbr.RAN_CAP)

    def test_every_vetoed_row_names_its_block_reason(self, lanes):
        for row in lanes["vetoed"]:
            assert row["blocked_reason_en"] and row["blocked_reason_zh"]
            assert row["anchor"] in (hbr.ANCHOR_CONFIRM, hbr.ANCHOR_MARKER,
                                     hbr.ANCHOR_APPROX)
            assert row["sessions_since"] is not None, "an unanchored row must be dropped"
            # a move may only ride on a confirmation anchor
            if row["pct_since"] is not None:
                assert row["anchor"] == hbr.ANCHOR_CONFIRM
                assert row["measured_from"] > row["signal_date"]

    def test_the_vetoed_lane_prints_what_the_board_missed(self, lanes):
        """Self-critical by construction: the moves are real and they are shown."""
        moves = [r["pct_since"] for r in lanes["vetoed"] if r["pct_since"] is not None]
        assert moves, "the lane exists to print these"
        assert max(moves) > 20.0, "the 2026-07-31 panel carries >20% missed moves"

    def test_no_vetoed_move_exceeds_its_confirmation_anchored_truth(self, frozen_lanes,
                                                                    board):
        """THE REGRESSION GATE, on the frozen panel: not one row may overstate.

        Re-derives each row's honest figure straight from the closes the fixture
        carries and demands an exact match.  Against the OLD marker anchor these same
        rows overstated by +8.40pp on average (measured 2026-07-31, 12/12 rows), so a
        revert to it fails here loudly rather than shipping twelve flattering numbers.
        """
        closes = board["closes"]
        checked, excess = 0, []
        for row in frozen_lanes["vetoed"]:
            if row["pct_since"] is None:
                continue
            dates, values = closes[row["ticker"]]["dates"], closes[row["ticker"]]["closes"]
            # the RAW marker date, not row["signal_date"]: the marker is a 3B bucket
            # LABEL and a label can fall on an exchange holiday (0656.HK's sits on
            # 2026-07-01), in which case the row displays the nearest session at or
            # before it — which is not a bucket label and cannot re-derive the anchor.
            marker = board["verdicts"][row["ticker"]]["last"]["date"]
            confirmed = sq.confirmation_date(_as_series(dates, values), marker)
            assert confirmed is not None, row["ticker"]
            truth = hbr.cross_read(dates, values,
                                   cross_date=str(confirmed.date()))["pct_since"]
            assert row["pct_since"] == truth, (
                f"{row['ticker']} prints {row['pct_since']}% but the confirmation "
                f"close ({confirmed.date()}) says {truth}%")
            excess.append(hbr.cross_read(dates, values,
                                         cross_date=marker)["pct_since"]
                          - row["pct_since"])
            checked += 1
        assert checked >= 10, "the frozen panel must exercise a full lane"
        # The effect is a POPULATION claim, not a per-row one: the marker sits at the
        # trough that created the signal, so on average it flatters the move — but a
        # name that fell between the marker and its confirmation close reads HIGHER
        # from the honest anchor, not lower (0656.HK: 21.7% confirmed vs 19.6% from
        # the marker).  Asserting "never higher" row-by-row would be a false claim
        # that happens to hold on most rows, which is how a wrong gate survives.
        assert statistics.mean(excess) > 5.0, (
            f"the frozen panel must exercise the overstatement this gate exists to "
            f"catch (mean marker-minus-confirmation excess {statistics.mean(excess):+.2f}pp)")

    def test_the_population_line_has_something_to_disclose(self, frozen_lanes):
        """The lane truncates on the real panel, and the middle move is far below it.

        MEASURED 2026-07-31: 46 refusals, median +3.1%, against a displayed set whose
        smallest member is several times that.  If these ever converge the disclosure
        is cheap; it is when they diverge — as here — that omitting it misleads.

        THE SPREAD RATIO ALONE IS NOT A GATE (added 2026-08-05).  ``max > median*3``
        survived the off-grid fixture at ``4.7 > 4.2`` — on a lane where 28 of 33
        names had gone unmeasurable and the five survivors were the five SMALLEST
        moves in it.  A ratio between two numbers drawn from the same 15% of a
        population says nothing about the population, so the coverage is floored
        directly: a disclosure line computed over a lane that is 85% null is not a
        disclosure, it is a different measurement wearing the same label.
        """
        rows = frozen_lanes["vetoed"]
        assert rows[0]["population"] > len(rows), "the cap must actually bind"

        population = rows[0]["population"]
        measured = rows[0]["population_measured"]
        assert measured / population >= 0.75, (
            f"only {measured} of {population} names in the vetoed population carry a "
            f"measurable move ({measured / population:.0%}) — the median and the "
            f"maximum below are drawn from a censored slice, and on this panel the "
            f"censoring is TOP-first (an off-grid fixture deleted ranks 1-11 of 33 "
            f"and left a 4.7% 'maximum'). Check the frozen windows' 3B phase before "
            f"reading anything on this lane")

        median = rows[0]["population_median_pct"]
        assert median is not None
        assert max(r["pct_since"] for r in rows if r["pct_since"] is not None) > median * 3

    def test_every_ran_row_is_confirmation_anchored_too(self, frozen_lanes):
        """The audit half: `ran` shared the defect and shares the fix.

        MEASURED 2026-07-31: all 12 displayed ran rows overstated, mean +8.09pp.
        """
        for row in frozen_lanes["ran"]:
            if row["pct_since"] is not None:
                assert row["anchor"] == hbr.ANCHOR_CONFIRM
                assert row["measured_from"] > row["cross_date"]

    def test_leaders_lane_is_momentum_ordered(self, lanes):
        keys = [r["rank_key"] for r in lanes["leaders"]]
        assert keys == sorted(keys, reverse=True)


class TestBuilderWiring:
    """End-to-end through scripts/build_hk_library.compute_hk_standouts.

    A unit-tested engine that the builder never calls is a dark lane.  This runs
    the real function over a minimal synthetic fixture (the pattern
    tests/test_hk_washout_watch.py established) and asserts the hk_prophet_v2 keys
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
        assert built["rank_by"] == "hk_prophet_v2"
        assert built["board_definition"] == "hk_prophet_v2"

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
        assert block["definition"] == "hk_prophet_v2"
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

    def test_display_lanes_are_excluded_from_the_laggards_lane(self, built):
        """No ticker may carry two stances on one page."""
        lag = {r["ticker"] for r in built["laggards"]}
        for lane in ("leaders", "ran", "vetoed"):
            clash = lag & {r["ticker"] for r in built[lane]}
            assert not clash, f"{lane} double-lists a laggard: {clash}"

    def test_no_display_lane_shares_a_ticker_with_buy_or_watch(self, built):
        """The display lanes claim last, so they never re-list a board name.

        `laggards` is deliberately NOT in this loop: it is drawn from the same scored
        universe by a different key and the builder has never excluded buy/watch from
        it (2331.HK is both on 2026-07-31).  That is pre-existing board behaviour,
        outside this change; what IS new is that laggards now claim their tickers
        before the display lanes run — pinned in the test above.
        """
        board = ({r["ticker"] for r in built["buy"]}
                 | {r["ticker"] for r in built["watch"]})
        for lane in ("leaders", "ran", "vetoed"):
            clash = board & {r["ticker"] for r in built[lane]}
            assert not clash, f"{lane} re-lists a board name: {clash}"

    def test_laggards_print_the_key_they_were_sorted_by(self, built):
        """MAJOR-2: the figure on the strip is the sort key, not a neighbouring one."""
        rows = built["laggards"]
        for row in rows:
            assert "laggard_z" in row, row["ticker"]
            key = hbr.laggards_key(row)
            if row["laggard_z"] is None:
                assert key == float("inf"), "an unresolved key must sort LAST"
            else:
                assert row["laggard_z"] == key
        keys = [r["laggard_z"] for r in rows if r["laggard_z"] is not None]
        assert keys == sorted(keys), "printed values must rise with the row order"

    def test_the_knife_class_is_stamped_across_the_universe(self, built):
        """B2: the H4 population is a stamp, not a lane membership read."""
        for lane in ("buy", "watch", "laggards"):
            for row in built[lane]:
                assert isinstance(row.get("knife_risk"), bool), row["ticker"]

    def test_only_cohort_members_are_ever_chipped(self, built):
        """M3, the half the real build can answer: no chip on a non-member."""
        cohort = hbr.leadership_cohort()
        for row in built["buy"]:
            if row.get("leadership"):
                assert row["ticker"].upper() in cohort, (
                    "%s is chipped but not in the cohort" % row["ticker"])


class TestCohortChipReachesTheBuyCards:
    """M3: the chip the leaders strip prints must reach a buy CARD for the same name.

    Pinned on the ENGINE helper the builder calls, with real cohort tickers — the
    old suite stamped `theme`/`leadership` onto its own fixture rows, which is
    exactly what hid the missing stamp: the fixture was doing the builder's job.
    """

    _LEAD = {"state": "leaders_participating", "cohesion_now": 0.9,
             "broad_breadth_pct": 71.2, "breadth_confirming": True}

    def _cohort_ticker(self):
        members = sorted(hbr.leadership_cohort())
        assert members, "the cohort organ shipped an empty roster"
        return members[0]

    def test_a_cohort_member_on_the_buy_lane_is_chipped(self):
        tk = self._cohort_ticker()
        rows = [{"ticker": tk}, {"ticker": "0001.HK"}]
        assert hbr.stamp_leadership_chips(rows, self._LEAD) == 1
        assert rows[0]["leadership"]["state_en"], "the chip must carry plain words"
        assert rows[0]["leadership"]["display_only"] is True
        assert rows[0]["in_leadership_cohort"] is True

    def test_a_non_member_is_never_chipped(self):
        rows = [{"ticker": "0001.HK"}]
        assert hbr.stamp_leadership_chips(rows, self._LEAD) == 0
        assert "leadership" not in rows[0]

    def test_the_payload_is_the_one_the_leaders_strip_uses(self):
        """One chip definition, not two that can drift."""
        tk = self._cohort_ticker()
        rows = [{"ticker": tk}]
        hbr.stamp_leadership_chips(rows, self._LEAD)
        assert rows[0]["leadership"] == hbr.leadership_chip(self._LEAD)

    def test_a_dead_organ_chips_nothing_and_does_not_raise(self):
        rows = [{"ticker": self._cohort_ticker()}]
        assert hbr.stamp_leadership_chips(rows, None) == 0
        assert hbr.stamp_leadership_chips(rows, {}) == 0
        assert "leadership" not in rows[0]

    def test_the_builder_stamps_the_buy_lane_with_it(self):
        """Reachability: the render path must call this, or the fix is dead code."""
        import inspect

        from scripts import build_hk_library as bhl
        src = inspect.getsource(bhl.compute_hk_standouts)
        assert "stamp_leadership_chips(buys" in src, (
            "the builder no longer chips the buy lane")


class TestLedgerIsTheGradedBoardOnly:
    """B1(a): the display lanes must never enter the graded board ledger.

    `append_board` assigns `board_pos` by list position and the ledger's rank-IC is
    Spearman(board_pos, forward excess) across a date's rows, so a lane row with no
    entry claim silently takes a position in the buy lane's own rank sample.

    Tested against `_board_ledger_calls` — the builder's own row constructor — rather
    than through a full board build, because a build that happens to produce no buys
    (the synthetic panel does) would pass every one of these vacuously.  The builder
    calling it is pinned separately below, so the helper is not a parallel universe.
    """

    def _rows(self):
        buys = [{"ticker": "0001.HK", "group": "entry_open", "edge_z": 1.2,
                 "price": 10.0, "signal": {"tier": "T2"}, "align_tier": "aligned",
                 "entry_window": {"kind": "open-now"}},
                {"ticker": "0002.HK", "group": "setting_up", "edge_z": 0.4,
                 "price": 20.0, "signal": {"tier": "T3"}}]
        watch = [{"ticker": "0003.HK", "edge_z": -0.5, "price": 5.0,
                  "knife_demoted": True, "knife_z": -1.8}]
        return buys, watch

    def _lanes(self):
        return [{"ticker": "9988.HK", "group": "leaders", "close_asof": 1.0},
                {"ticker": "0700.HK", "group": "ran", "close_asof": 1.0},
                {"ticker": "1810.HK", "group": "vetoed", "close_asof": 1.0}]

    def _calls(self):
        from scripts.build_hk_library import _board_ledger_calls
        buys, watch = self._rows()
        return _board_ledger_calls(buys, watch)

    def test_no_display_lane_row_is_appended(self):
        groups = {c.get("group") for c in self._calls()}
        for lane in hbr.DISPLAY_TIER_LANES:
            assert lane not in groups, (
                "%s reached the graded ledger: %r" % (lane, sorted(groups)))

    def test_the_appended_population_is_exactly_buy_plus_watch(self):
        buys, watch = self._rows()
        calls = self._calls()
        assert [c["ticker"] for c in calls] == (
            [r["ticker"] for r in buys] + [r["ticker"] for r in watch])
        assert {c["group"] for c in calls} == {"entry_open", "setting_up", "watch"}

    def test_re_adding_the_lanes_breaks_the_pin(self):
        """MUTATION: the guard above must be able to SEE the defect it forbids.

        Reconstructs the pre-fix shape — the lane rows appended to the same list —
        and asserts the assertion above would fail on it.  Without this the pin
        could be passing because nothing ever produces a lane row, not because the
        builder stopped producing them.
        """
        mutated = self._calls() + self._lanes()
        groups = {c.get("group") for c in mutated}
        leaked = [lane for lane in hbr.DISPLAY_TIER_LANES if lane in groups]
        assert leaked == list(hbr.DISPLAY_TIER_LANES), (
            "the mutation did not reproduce the defect — the pin above is vacuous")
        assert len(mutated) != len(self._calls()), "the population pin is live too"

    def test_every_appended_row_carries_the_era_stamp(self):
        """B1(b): a graded row without a definition would pool with the old board."""
        calls = self._calls()
        assert calls, "nothing was appended"
        for call in calls:
            assert call.get("board_definition") == hbr.BOARD_DEFINITION, call

    def test_watch_rows_keep_their_group_and_their_stamps(self):
        """On-lane behaviour for the cohorts that DO get logged is unchanged."""
        calls = self._calls()
        watch_row = calls[-1]
        assert watch_row["group"] == "watch"
        assert watch_row["knife_demoted"] is True
        assert watch_row["knife_z"] == -1.8
        assert watch_row["primary_rejection_reason"] == "knife_demote"
        assert watch_row["gate_ver"] == "cascade_v1"
        buy_row = calls[0]
        assert (buy_row["edge_z"], buy_row["gate_tier"], buy_row["align_tier"],
                buy_row["entry_state"]) == (1.2, "T2", "aligned", "open-now")

    def test_a_degraded_placement_store_stamps_none_not_false(self):
        from scripts.build_hk_library import _board_ledger_calls
        buys, watch = self._rows()
        rows = _board_ledger_calls(buys, watch, placement_ok=False)
        assert all(r["placement_flag"] is None for r in rows)

    def test_the_builder_uses_this_constructor(self, tmp_path, monkeypatch):
        """The helper is not a parallel universe: the render path hands its output
        straight to append_board, unchanged and un-extended."""
        import json as _json

        import lib.config as cfg_module
        from engine import board_ledger
        from scripts import build_hk_library as bhl

        seen: list[list[dict]] = []
        marker = [{"ticker": "SENTINEL.HK", "group": "entry_open"}]
        monkeypatch.setattr(bhl, "_board_ledger_calls",
                            lambda *a, **k: [dict(m) for m in marker])
        monkeypatch.setattr(board_ledger, "append_board",
                            lambda calls, market, asof=None: (seen.append(list(calls))
                                                              or 0))

        tickers = ["9988.HK", "0700.HK", "9618.HK", "3690.HK", "1810.HK"]
        hd = tmp_path / "site" / "hkstockdata"
        hd.mkdir(parents=True, exist_ok=True)
        chart = [round(10.0 + i * 0.01, 4) for i in range(80)]
        for ticker in tickers:
            (hd / f"{ticker}.json").write_text(_json.dumps({
                "ticker": ticker, "name": f"Test {ticker}", "sector": "Technology",
                "tech": {"price": chart[-1], "rsi14": 38.0, "ma200": 15.0,
                         "off_52w_high_pct": -0.25},
                "chart": {"c": chart}, "conviction": None}))
        monkeypatch.setattr(cfg_module, "ROOT", tmp_path)
        out = bhl.compute_hk_standouts({
            "as_of": "2026-07-08", "risk_state": "risk_off",
            "modes": {"all": [{"ticker": t, "name": f"Test {t}",
                               "sector": "Technology", "sector_zh": "科技",
                               "cycle": "DECLINE", "cycle_zh": "DECLINE",
                               "cycle_dir": "down", "beta": 1.2, "role": "cyclical",
                               "tilt": "growth", "price": 10.0} for t in tickers]},
        })
        if out is None:                        # pragma: no cover — env-dependent
            pytest.skip("compute_hk_standouts returned None")
        assert seen, "the render path never reached append_board"
        assert seen[-1] == marker, (
            "the builder appended rows the constructor did not produce: %r" % seen[-1])


class TestOnLaneLedgerFailureStillAlarms:
    """M6: the G7 caller fix must not have silenced a REAL write failure.

    The off-lane skip stops raising a health row; an ON-lane append that returns 0
    is still a genuine failure and must still raise it.  Without this test the two
    cases are indistinguishable from the outside and the fix could quietly become a
    blanket mute.
    """

    def _health(self, tmp_path, monkeypatch, *, on_lane: bool):
        import json as _json

        import lib.config as cfg_module
        from engine import board_ledger, ledger_lane
        from scripts.build_hk_library import compute_hk_standouts

        monkeypatch.setattr(board_ledger, "append_board",
                            lambda *a, **k: 0)          # a zero-row write
        monkeypatch.setattr(ledger_lane, "asia_advance_enabled", lambda: on_lane)

        tickers = ["9988.HK", "0700.HK", "9618.HK", "3690.HK", "1810.HK"]
        hd = tmp_path / "site" / "hkstockdata"
        hd.mkdir(parents=True, exist_ok=True)
        chart = [round(10.0 + i * 0.01, 4) for i in range(80)]
        for ticker in tickers:
            (hd / f"{ticker}.json").write_text(_json.dumps({
                "ticker": ticker, "name": f"Test {ticker}", "sector": "Technology",
                "tech": {"price": chart[-1], "rsi14": 38.0, "ma200": 15.0,
                         "off_52w_high_pct": -0.25},
                "chart": {"c": chart}, "conviction": None}))
        monkeypatch.setattr(cfg_module, "ROOT", tmp_path)
        out = compute_hk_standouts({
            "as_of": "2026-07-08", "risk_state": "risk_off",
            "modes": {"all": [{"ticker": t, "name": f"Test {t}",
                               "sector": "Technology", "sector_zh": "科技",
                               "cycle": "DECLINE", "cycle_zh": "DECLINE",
                               "cycle_dir": "down", "beta": 1.2, "role": "cyclical",
                               "tilt": "growth", "price": 10.0} for t in tickers]},
        })
        if out is None:                        # pragma: no cover — env-dependent
            pytest.skip("compute_hk_standouts returned None")
        return {row.get("leg") for row in (out.get("health") or [])}

    def test_on_lane_zero_rows_raises_the_health_row(self, tmp_path, monkeypatch):
        assert "board_ledger" in self._health(tmp_path, monkeypatch, on_lane=True), (
            "an on-lane append that wrote nothing IS a failure and must be surfaced")

    def test_off_lane_zero_rows_stays_quiet(self, tmp_path, monkeypatch):
        assert "board_ledger" not in self._health(tmp_path, monkeypatch,
                                                  on_lane=False)


class TestG1FixtureIsNotStale:
    """A frozen fixture that no longer matches its historical panel would keep G1 green.

    The close panel is append-only and may advance beyond the fixture's ``_as_of``.
    Appends must not invalidate a historical replay, but a rewrite at or before that
    date must.  Compare every frozen tail against the matching historical slice, then
    re-derive the seven witnesses from that same slice.  This preserves the stale-data
    tripwire without making every new market session break an older measurement.
    """

    def test_every_frozen_window_starts_on_a_3b_bucket_boundary(self, board):
        """THE PHASE INVARIANT — asserted, not described.

        ``regenerate_g1_fixture`` has called the 3B alignment "load-bearing rather
        than cosmetic" since 2026-08-03 and NOTHING checked it.  It broke exactly as
        prose predicts: a regenerator re-cutting a flat ``tail(_tail_sessions)``
        (correct only if every window were the same length — 123 of these 157 are
        not) put 123 windows off-grid, and because ``signal_quality.signal_frame``
        anchors its ``resample("3B")`` bins on the series' FIRST index date, every
        frozen marker date stopped being a bucket label.  The move-anchored lanes
        then dropped the rows they could no longer anchor: the vetoed lane fell from
        33 measured names (max +24.3%) to 5 (max +4.7%), TOP-FIRST.

        The only thing that failed was ``test_the_vetoed_lane_prints_what_the_board
        _missed``'s ``max(moves) > 20.0``, which reads as "the panel no longer
        carries big missed moves" — a data-falsification claim.  A whole
        investigation went that way.  A fixture-shape defect must fail as a
        fixture-shape defect, so it is measured here, on the shape, by name.
        """
        np = pytest.importorskip("numpy")
        pd = pytest.importorskip("pandas")
        src = Path(board["_source"])
        if not src.exists():                    # pragma: no cover — committed in-tree
            pytest.skip(f"{src} not present")
        panel = pd.read_parquet(src).loc[:board["_as_of"]]

        off_grid = {}
        for ticker, frozen in board["closes"].items():
            column_start = str(panel[ticker].dropna().index[0].date())
            phase = int(np.busday_count(column_start, frozen["dates"][0])) % 3
            if phase:
                off_grid[ticker] = phase
        assert not off_grid, (
            f"{len(off_grid)} of {len(board['closes'])} frozen windows do not start "
            f"on a 3B bucket boundary of their own column "
            f"(first few: {dict(list(off_grid.items())[:5])}) — the frozen verdicts' "
            f"marker dates are no longer bucket labels, so the move-anchored lanes "
            f"will silently drop rows rather than fail. Regenerate the fixture: "
            f"{regenerate_g1_fixture()}")

    def test_the_window_stamp_describes_the_windows_it_stamps(self, board):
        """``_tail_sessions: 340`` was false for 123 of 157 tickers, and it was READ.

        It was the era parameter the regenerator sliced by, so the file's own
        metadata is what told the regenerator to flatten it.  The stamp is now
        ``_tail_anchor`` — a RULE, not a count — and a count cannot come back
        without this failing, because a count is not a thing these windows have.
        """
        assert "_tail_sessions" not in board, (
            "a single session count cannot describe windows of three different "
            "lengths; it is the field that caused the flattening")
        anchor = board["_tail_anchor"]
        assert anchor["rule"] == "3b_phase_aligned"
        assert anchor["phase_mod"] == 3
        lengths = {len(v["dates"]) for v in board["closes"].values()}
        assert min(lengths) >= anchor["min_sessions"], (
            f"windows {sorted(lengths)} vs declared minimum {anchor['min_sessions']}")
        assert len(lengths) > 1, (
            "if every window really were the same length this stamp would be "
            "over-engineering — it is not: " + str(sorted(lengths)))

    def test_source_panel_history_is_unchanged(self, board):
        pd = pytest.importorskip("pandas")
        src = Path(board["_source"])
        if not src.exists():                    # pragma: no cover — committed in-tree
            pytest.skip(f"{src} not present")
        panel = pd.read_parquet(src).loc[:board["_as_of"]]
        for ticker, frozen in board["closes"].items():
            # Anchored on the frozen window's OWN first date, not on a tail count:
            # the tail is cut to a 3B bucket boundary of the full column (see
            # regenerate_g1_fixture), so its length varies by a session or two per
            # ticker and `tail(N)` would compare misaligned windows.
            series = panel[ticker].dropna().loc[frozen["dates"][0]:]
            dates = [str(index.date()) for index in series.index]
            closes = [round(float(value), 3) for value in series.tolist()]
            assert dates == frozen["dates"], (
                f"{ticker} historical dates drifted — regenerate the fixture: "
                f"{regenerate_g1_fixture()}")
            assert closes == frozen["closes"], (
                f"{ticker} historical closes drifted — regenerate the fixture: "
                f"{regenerate_g1_fixture()}")

    def test_witness_verdicts_replay_from_the_live_panel(self, board):
        pd = pytest.importorskip("pandas")
        from engine import signal_gate
        src = Path(board["_source"])
        if not src.exists():                    # pragma: no cover
            pytest.skip(f"{src} not present")
        panel = pd.read_parquet(src)
        for ticker in WITNESSES:
            series = panel[ticker].loc[:board["_as_of"]].dropna()
            live = signal_gate.compact(signal_gate.gate(ticker, series))
            frozen = board["verdicts"][ticker]
            for key in ("eligible", "ticks", "fresh_bars", "above200", "weekly_bull"):
                assert live.get(key) == frozen[key], f"{ticker}.{key} drifted"
