"""tests/test_us_leaders_lane.py — Leaders strip v2 admission + ordering + NaN safety.

The lane exists because the US board's fresh-cross confluence gate structurally cannot
admit a market leader that never pulls back (measured 2026-07-28: of the top-100
3-month runners, 2 passed the gate, 53 sat at flat-sell). It is DISPLAY-TIER coverage
of those names — never an entry claim.

v2 (2026-08-02) changed the RANK KEY, and that is what most of this file pins.
v1 ranked by residual alpha with a 0.5 floor. Residual alpha is beta-stripped, so it
structurally erases a theme rally in which a whole cohort rises together: the lane held
ZERO software names through the entire ai_software / non_ai_software leadership run
while filling up with idiosyncratic small caps whose residual was large only because
their beta was small. v2 ranks by the composite TOTAL-momentum leg, boosts membership
of a top-8 in-favour basket, requires the name to trade near its high, and keeps
residual alpha as the final tiebreak only.

Tests import the REAL helpers from scripts.build_stock_library — nothing here mirrors
builder logic.

Key invariants:
  A. Admission: intact trend (above200 AND weekly_bull, both strictly True) AND a
     total-momentum reading AND off_high >= LEADERS_OFF_HIGH_FLOOR AND not already
     surfaced (exclude) AND dir != 'down'.
  B. Order: (momentum + theme boost) desc, alpha desc, ticker asc — deterministic.
  C. Dual-class dedup keeps the FIRST-ranked variant; cap caps; rows tag lane='leader'.
  D. Serialisation: leaders rows go through the SAME whole-dict _json_safe scrub the
     artifact write applies, so allow_nan=False cannot trip on this lane.
  E. G0.3 ON REAL DATA: the committed 2026-07-31 fixture. A-D are synthetic — numbers
     picked to make the rule work, which can only show the rule is self-consistent. E is
     the program's central claim measured on the actual board.

PRODUCTION SHAPE (load-bearing): _select_leaders runs BEFORE the board-row enrichment
pass, so at call time the row carries NEITHER `composite` NOR `off_high` — both arrive
through the composite_by / disp_by maps. The fixtures below are therefore map-shaped by
default; the row-fallback path gets its own explicit tests. A fixture that put those
fields on the row would pass while production shipped an empty strip.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

from scripts.build_stock_library import (
    LEADERS_CAP,
    LEADERS_OFF_HIGH_FLOOR,
    LEADERS_THEME_BOOST,
    _drop_spurious_sector_rows,
    _json_safe,
    _select_leaders,
)

# ---------------------------------------------------------------------------
# Fixtures (data only — all logic under test is imported)
# ---------------------------------------------------------------------------


def _row(ticker: str, alpha, *, name: str | None = None,
         sector: str = "Information Technology", **extra) -> dict:
    """One board row as row_by_t holds it AT LEADERS TIME — no composite, no
    off_high (both are attached later by the enrichment pass). `name` defaults to a
    unique company so the dual-class dedup is inert unless a test shares a name."""
    r = {"ticker": ticker, "name": name if name is not None else f"{ticker} Corp",
         "sector": sector, "alpha": alpha}
    r.update(extra)
    return r


def _verdict(*, above200=True, weekly_bull=True) -> dict:
    """Minimal signal_gate verdict — only the two structure keys the strip gates on."""
    return {"above200": above200, "weekly_bull": weekly_bull, "eligible": False}


def _fixture(rows: list[dict], verdicts: dict | None = None, *,
             momentum: dict | None = None, off_high: dict | None = None,
             default_momentum: float = 1.0, default_off_high: float = -5.0):
    """(scored, row_by_t, sig_verdict, kwargs) for a list of rows.

    `kwargs` carries the composite_by / disp_by maps in the production shape.
    scored order is irrelevant to the strip (it re-sorts) but is kept ticker-stable.
    """
    row_by_t = {r["ticker"]: r for r in rows}
    scored = [(r["ticker"], {"composite_z": 0.0}) for r in rows]
    sv = {r["ticker"]: _verdict() for r in rows}
    sv.update(verdicts or {})

    mom = {r["ticker"]: default_momentum for r in rows}
    mom.update(momentum or {})
    oh = {r["ticker"]: default_off_high for r in rows}
    oh.update(off_high or {})

    momentum_by = {t: v for t, v in mom.items() if v is not None}
    disp_by = {t: {"off_high": v} for t, v in oh.items()}
    return scored, row_by_t, sv, {"momentum_by": momentum_by, "disp_by": disp_by}


def _tickers(leaders: list[dict]) -> list[str]:
    return [r["ticker"] for r in leaders]


# ---------------------------------------------------------------------------
# A. Admission
# ---------------------------------------------------------------------------

class TestLeadersAdmission:

    def test_structure_intact_with_momentum_admitted(self):
        """The base case: above200 + weekly_bull + a momentum reading + near high."""
        scored, rbt, sv, kw = _fixture([_row("NVDA", 1.8)])
        assert _tickers(_select_leaders(scored, rbt, sv, set(), **kw)) == ["NVDA"]

    def test_low_residual_alpha_no_longer_blocks_admission(self):
        """The v1 alpha >= 0.5 floor is GONE — that floor is what deleted the
        software cohort, whose residual is small precisely because the whole theme
        was rising together."""
        scored, rbt, sv, kw = _fixture([_row("MSFT", 0.2)],
                                       momentum={"MSFT": 2.0})
        assert _tickers(_select_leaders(scored, rbt, sv, set(), **kw)) == ["MSFT"]

    def test_negative_residual_alpha_is_still_admissible(self):
        scored, rbt, sv, kw = _fixture([_row("BETA", -0.4)], momentum={"BETA": 2.5})
        assert _tickers(_select_leaders(scored, rbt, sv, set(), **kw)) == ["BETA"]

    def test_excluded_ticker_dropped(self):
        """A name already surfaced on buy/watch/laggards never repeats on the strip."""
        scored, rbt, sv, kw = _fixture([_row("NVDA", 1.8), _row("AMD", 1.5)])
        assert _tickers(_select_leaders(scored, rbt, sv, {"NVDA"}, **kw)) == ["AMD"]

    def test_above200_false_excluded(self):
        scored, rbt, sv, kw = _fixture(
            [_row("BRKN", 2.0)], {"BRKN": _verdict(above200=False)})
        assert _select_leaders(scored, rbt, sv, set(), **kw) == []

    def test_above200_none_excluded(self):
        """None means UNKNOWN, not intact — an unanalysed name is not a leader."""
        scored, rbt, sv, kw = _fixture(
            [_row("UNKN", 2.0)], {"UNKN": _verdict(above200=None)})
        assert _select_leaders(scored, rbt, sv, set(), **kw) == []

    def test_weekly_bull_false_excluded(self):
        scored, rbt, sv, kw = _fixture(
            [_row("ROLL", 2.0)], {"ROLL": _verdict(weekly_bull=False)})
        assert _select_leaders(scored, rbt, sv, set(), **kw) == []

    def test_weekly_bull_none_excluded(self):
        scored, rbt, sv, kw = _fixture(
            [_row("UNKW", 2.0)], {"UNKW": _verdict(weekly_bull=None)})
        assert _select_leaders(scored, rbt, sv, set(), **kw) == []

    def test_missing_verdict_excluded(self):
        """No verdict at all => no structure evidence => not admitted."""
        scored, rbt, _sv, kw = _fixture([_row("GHOST", 2.0)])
        assert _select_leaders(scored, rbt, {}, set(), **kw) == []

    def test_missing_momentum_excluded(self):
        """No momentum reading, no row — the rank key must never be defaulted."""
        scored, rbt, sv, kw = _fixture([_row("NOMOM", 2.0)],
                                       momentum={"NOMOM": None})
        assert _select_leaders(scored, rbt, sv, set(), **kw) == []

    def test_nan_momentum_excluded(self):
        scored, rbt, sv, kw = _fixture([_row("NANM", 2.0)],
                                       momentum={"NANM": float("nan")})
        assert _select_leaders(scored, rbt, sv, set(), **kw) == []

    def test_momentum_of_zero_is_a_reading_not_a_missing_value(self):
        """0.0 is the middle of a z-scored cross-section, not an absence."""
        scored, rbt, sv, kw = _fixture([_row("MID", 1.0)], momentum={"MID": 0.0})
        assert _tickers(_select_leaders(scored, rbt, sv, set(), **kw)) == ["MID"]

    def test_off_high_floor_is_inclusive(self):
        scored, rbt, sv, kw = _fixture(
            [_row("EDGE", 1.0)], off_high={"EDGE": LEADERS_OFF_HIGH_FLOOR})
        assert _tickers(_select_leaders(scored, rbt, sv, set(), **kw)) == ["EDGE"]

    def test_far_off_high_excluded(self):
        """Leaders trade near their highs; a name 30% off one is not leading."""
        scored, rbt, sv, kw = _fixture(
            [_row("DEEP", 3.0)], off_high={"DEEP": LEADERS_OFF_HIGH_FLOOR - 0.01})
        assert _select_leaders(scored, rbt, sv, set(), **kw) == []

    def test_unknown_off_high_excluded(self):
        """Fail-closed: an unknown distance from the high is not a near-high name."""
        scored, rbt, sv, kw = _fixture([_row("BLIND", 2.0)], off_high={"BLIND": None})
        assert _select_leaders(scored, rbt, sv, set(), **kw) == []

    def test_alpha_none_or_nan_is_admissible_and_sorts_last(self):
        """Alpha is only a tiebreak now, so a missing one must not delete the row."""
        scored, rbt, sv, kw = _fixture(
            [_row("NOA", None), _row("NANA", float("nan")), _row("HASA", 1.0)])
        out = _tickers(_select_leaders(scored, rbt, sv, set(), **kw))
        assert out[0] == "HASA"
        assert set(out) == {"HASA", "NOA", "NANA"}

    def test_dir_down_excluded(self):
        scored, rbt, sv, kw = _fixture([_row("FALL", 2.0, dir="down")])
        assert _select_leaders(scored, rbt, sv, set(), **kw) == []

    def test_dir_up_and_absent_admitted(self):
        """dir='up' and a missing dir key are both fine — only 'down' is a veto."""
        scored, rbt, sv, kw = _fixture([_row("UPUP", 2.0, dir="up"), _row("BARE", 1.9)],
                                       momentum={"UPUP": 2.0, "BARE": 1.0})
        assert _tickers(_select_leaders(scored, rbt, sv, set(), **kw)) == ["UPUP", "BARE"]

    def test_row_missing_from_row_by_t_skipped(self):
        """A scored ticker with no board row is skipped, not a crash."""
        scored, rbt, sv, kw = _fixture([_row("REAL", 2.0)])
        scored = scored + [("PHANTOM", {"composite_z": 0.0})]
        sv["PHANTOM"] = _verdict()
        assert _tickers(_select_leaders(scored, rbt, sv, set(), **kw)) == ["REAL"]


# ---------------------------------------------------------------------------
# A2. The software-cohort regression — why the rank key changed
# ---------------------------------------------------------------------------

class TestSoftwareCohortRegression:
    """The measured 2026-08-02 failure, as a test.

    MSFT-class: big total momentum, small residual (the whole theme moved together).
    Callaway-class: small total momentum, huge residual (an idiosyncratic small cap).
    v1 selected the second and could not see the first. v2 must invert that.
    """

    _MSFT = _row("MSFT", 0.2, name="Microsoft Corp")
    _CALY = _row("CALY", 2.0, name="Callaway Golf Co",
                 sector="Consumer Discretionary")

    def _fx(self):
        return _fixture(
            [dict(self._MSFT), dict(self._CALY)],
            momentum={"MSFT": 2.0, "CALY": 0.3},
            off_high={"MSFT": -5.0, "CALY": -8.0},
        )

    def test_msft_class_is_selected_and_outranks_the_residual_freak(self):
        scored, rbt, sv, kw = self._fx()
        assert _tickers(_select_leaders(scored, rbt, sv, set(), **kw)) == ["MSFT", "CALY"]

    def test_the_v1_rule_would_have_rejected_msft_outright(self):
        """Counterfactual on the SAME fixture: alpha >= 0.5, alpha-desc. Keeps the
        fixture honest — if MSFT's alpha ever drifts above the old floor this test
        fails and the regression above stops proving anything."""
        v1_floor = 0.5
        admitted = sorted(
            (r["ticker"] for r in (self._MSFT, self._CALY) if r["alpha"] >= v1_floor))
        assert admitted == ["CALY"], (
            "fixture no longer reproduces the v1 failure — MSFT must sit BELOW the "
            "old residual-alpha floor for this regression to mean anything")

    def test_theme_boost_lifts_a_near_tie(self):
        """A top-8 in-favour basket member outranks a marginally stronger outsider —
        the boost is exactly LEADERS_THEME_BOOST, applied to the display rank only."""
        scored, rbt, sv, kw = _fixture(
            [_row("THEMED", 0.0), _row("PLAIN", 0.0)],
            momentum={"THEMED": 1.0, "PLAIN": 1.0 + LEADERS_THEME_BOOST / 2})
        out = _select_leaders(scored, rbt, sv, set(),
                              theme_by={"THEMED": {"id": "ai_software"}}, **kw)
        assert _tickers(out) == ["THEMED", "PLAIN"]

    def test_theme_boost_does_not_rescue_a_far_weaker_name(self):
        """The boost is a nudge, not an override — it cannot invent leadership."""
        scored, rbt, sv, kw = _fixture(
            [_row("THEMED", 0.0), _row("STRONG", 0.0)],
            momentum={"THEMED": 1.0, "STRONG": 3.0})
        out = _select_leaders(scored, rbt, sv, set(),
                              theme_by={"THEMED": {"id": "ai_software"}}, **kw)
        assert _tickers(out) == ["STRONG", "THEMED"]

    def test_no_theme_map_is_a_no_op(self):
        scored, rbt, sv, kw = _fixture(
            [_row("A", 0.0), _row("B", 0.0)], momentum={"A": 1.0, "B": 2.0})
        assert _tickers(_select_leaders(scored, rbt, sv, set(), **kw)) == ["B", "A"]
        assert _tickers(_select_leaders(
            scored, rbt, sv, set(), theme_by=None, **kw)) == ["B", "A"]


# ---------------------------------------------------------------------------
# B. Ordering
# ---------------------------------------------------------------------------

class TestLeadersOrdering:

    def test_momentum_desc(self):
        scored, rbt, sv, kw = _fixture(
            [_row("LOW", 1.0), _row("HIGH", 1.0), _row("MID", 1.0)],
            momentum={"LOW": 0.6, "HIGH": 3.1, "MID": 1.4})
        assert _tickers(_select_leaders(scored, rbt, sv, set(), **kw)) == [
            "HIGH", "MID", "LOW"]

    def test_alpha_breaks_a_momentum_tie(self):
        scored, rbt, sv, kw = _fixture(
            [_row("AAA", 0.1), _row("BBB", 2.0)], momentum={"AAA": 1.0, "BBB": 1.0})
        assert _tickers(_select_leaders(scored, rbt, sv, set(), **kw)) == ["BBB", "AAA"]

    def test_ticker_tiebreak_is_ascending_and_deterministic(self):
        """Equal momentum AND alpha must never leave order to insertion order."""
        rows = [_row("ZZZ", 1.0), _row("AAA", 1.0), _row("MMM", 1.0)]
        scored, rbt, sv, kw = _fixture(rows)
        assert _tickers(_select_leaders(scored, rbt, sv, set(), **kw)) == [
            "AAA", "MMM", "ZZZ"]
        # reversed input, identical output
        rows2 = [_row("MMM", 1.0), _row("AAA", 1.0), _row("ZZZ", 1.0)]
        scored2, rbt2, sv2, kw2 = _fixture(rows2)
        assert _tickers(_select_leaders(scored2, rbt2, sv2, set(), **kw2)) == [
            "AAA", "MMM", "ZZZ"]


# ---------------------------------------------------------------------------
# B2. The map-vs-row indirection (the production path)
# ---------------------------------------------------------------------------

class TestRankSourceIndirection:
    """Where the rank key comes from — the most load-bearing thing in this file.

    At leaders time the ROW has no composite/off_high; both arrive through maps. And
    the map that must win is `momentum_by` (3-month TOTAL return), NOT the composite's
    `momentum` leg: that leg is fed by the same residual alpha the v1 rule used
    (measured corr 0.984 on the 2026-07-31 board), so ranking by it would be v1 under
    a new name. The composite is a logged last resort, nothing more.
    """

    def test_momentum_map_is_read_when_the_row_has_nothing(self):
        scored, rbt, sv, kw = _fixture([_row("MAPPED", 1.0)])
        assert "composite" not in rbt["MAPPED"] and "off_high" not in rbt["MAPPED"]
        assert _tickers(_select_leaders(scored, rbt, sv, set(), **kw)) == ["MAPPED"]

    def test_no_maps_and_no_row_fields_selects_nothing(self):
        """Counterfactual: drop the maps and the strip goes empty — proof that the
        test above is exercising the map path, not a row fallback."""
        scored, rbt, sv, _kw = _fixture([_row("MAPPED", 1.0)])
        assert _select_leaders(scored, rbt, sv, set()) == []

    def test_total_return_momentum_outranks_the_composite_leg(self):
        """The whole point of v2: when the two disagree, total return decides."""
        scored, rbt, sv, kw = _fixture(
            [_row("THEME_LEADER", 0.1), _row("RESIDUAL_FREAK", 3.0)],
            momentum={"THEME_LEADER": 3.0, "RESIDUAL_FREAK": 0.2})
        composite_by = {"THEME_LEADER": {"legs": {"momentum": 0.1}},
                        "RESIDUAL_FREAK": {"legs": {"momentum": 3.0}}}
        out = _select_leaders(scored, rbt, sv, set(),
                              composite_by=composite_by, **kw)
        assert _tickers(out) == ["THEME_LEADER", "RESIDUAL_FREAK"]

    def test_composite_is_the_fallback_when_the_momentum_map_misses_a_name(self):
        scored, rbt, sv, kw = _fixture([_row("GAP", 1.0)])
        kw["momentum_by"] = {}
        out = _select_leaders(scored, rbt, sv, set(),
                              composite_by={"GAP": {"legs": {"momentum": 1.0}}}, **kw)
        assert _tickers(out) == ["GAP"]

    def test_the_composite_fallback_announces_itself(self, capsys):
        """A silent degradation to the residual-alpha-equivalent key is the exact
        failure v2 exists to prevent — it must be visible in the build log."""
        scored, rbt, sv, kw = _fixture([_row("GAP", 1.0)])
        kw["momentum_by"] = {}
        _select_leaders(scored, rbt, sv, set(),
                        composite_by={"GAP": {"legs": {"momentum": 1.0}}}, **kw)
        out = capsys.readouterr().out
        assert out.startswith("::warning"), (
            "the annotation must START the line — a logger prefix makes GitHub "
            "drop it silently")
        assert "leaders_rank_source" in out

    def test_no_warning_when_the_momentum_map_covers_everything(self, capsys):
        scored, rbt, sv, kw = _fixture([_row("OK", 1.0)])
        _select_leaders(scored, rbt, sv, set(), **kw)
        assert capsys.readouterr().out == ""

    def test_enriched_row_is_the_last_fallback(self):
        """An already-enriched row (post-enrichment callers, tests) still works."""
        rows = [_row("ENR", 1.0, composite={"legs": {"momentum": 2.0}}, off_high=-3.0)]
        scored, rbt, sv, _kw = _fixture(rows)
        assert _tickers(_select_leaders(scored, rbt, sv, set())) == ["ENR"]

    def test_disp_map_wins_over_the_row_for_off_high(self):
        rows = [_row("A", 1.0, off_high=-99.0)]
        scored, rbt, sv, kw = _fixture(rows, off_high={"A": -1.0})
        assert _tickers(_select_leaders(scored, rbt, sv, set(), **kw)) == ["A"]


# ---------------------------------------------------------------------------
# C. Dedup / cap / lane tag
# ---------------------------------------------------------------------------

class TestLeadersDedupCapTag:

    def test_dual_class_dedupe_keeps_first_ranked(self):
        """GOOG/GOOGL share a normalised company name — the higher-ranked wins."""
        scored, rbt, sv, kw = _fixture(
            [_row("GOOG", 1.0, name="Alphabet Inc"),
             _row("GOOGL", 1.0, name="Alphabet Inc."),
             _row("MSFT", 1.0, name="Microsoft Corp")],
            momentum={"GOOG": 1.2, "GOOGL": 1.9, "MSFT": 1.5})
        assert _tickers(_select_leaders(scored, rbt, sv, set(), **kw)) == [
            "GOOGL", "MSFT"]

    def test_cap_respected(self):
        rows = [_row(f"T{i:02d}", 1.0) for i in range(LEADERS_CAP + 7)]
        scored, rbt, sv, kw = _fixture(
            rows, momentum={f"T{i:02d}": 1.0 + i / 100 for i in range(LEADERS_CAP + 7)})
        out = _select_leaders(scored, rbt, sv, set(), **kw)
        assert len(out) == LEADERS_CAP
        # the cap keeps the TOP-momentum rows, not an arbitrary slice
        assert out[0]["ticker"] == f"T{LEADERS_CAP + 6:02d}"

    def test_explicit_cap_override(self):
        rows = [_row(f"T{i}", 1.0) for i in range(6)]
        scored, rbt, sv, kw = _fixture(
            rows, momentum={f"T{i}": 1.0 + i / 100 for i in range(6)})
        assert len(_select_leaders(scored, rbt, sv, set(), cap=2, **kw)) == 2

    def test_explicit_off_high_floor_override(self):
        scored, rbt, sv, kw = _fixture([_row("DEEP", 1.0)], off_high={"DEEP": -40.0})
        assert _select_leaders(scored, rbt, sv, set(), **kw) == []
        assert _tickers(_select_leaders(
            scored, rbt, sv, set(), off_high_floor=-50.0, **kw)) == ["DEEP"]

    def test_rows_tagged_lane_leader(self):
        """The lane tag is what keeps the strip out of every buy-lane consumer."""
        scored, rbt, sv, kw = _fixture([_row("NVDA", 1.8), _row("AMD", 1.5)])
        out = _select_leaders(scored, rbt, sv, set(), **kw)
        assert [r["lane"] for r in out] == ["leader", "leader"]

    def test_non_admitted_rows_not_tagged(self):
        """A row that fails admission must not acquire lane='leader' as a side effect."""
        scored, rbt, sv, kw = _fixture(
            [_row("NOPE", 2.0)], {"NOPE": _verdict(above200=False)})
        assert _select_leaders(scored, rbt, sv, set(), **kw) == []
        assert "lane" not in rbt["NOPE"]

    def test_empty_inputs_return_empty(self):
        assert _select_leaders([], {}, {}, set()) == []


# ---------------------------------------------------------------------------
# D. Artifact-side safety: the leaders lane is a serialised array
# ---------------------------------------------------------------------------

class TestLeadersArtifactSafety:

    def test_json_safe_scrubs_the_leaders_lane(self):
        """The artifact write is `json.dumps(_json_safe(wide), allow_nan=False)`.
        _json_safe is a WHOLE-DICT recursive scrub, so a new top-level lane is
        covered with no lane-keyed change — this pins that. A non-finite float
        anywhere under leaders[] would otherwise raise ValueError on the write."""
        wide = {"as_of": "2026-07-28", "buy": [], "watch": [],
                "leaders": [{"ticker": "NVDA", "lane": "leader", "alpha": 1.8,
                             "ext_z": float("nan"),
                             "theme": {"id": "ai_software", "bull_days": 5},
                             "conviction": {"score": float("inf")},
                             "entry_signal": {"buy_zone": {"low": float("nan"),
                                                           "high": 101.0}}}],
                "laggards": []}
        payload = json.dumps(_json_safe(wide), separators=(",", ":"),
                             default=str, allow_nan=False)
        back = json.loads(payload)
        row = back["leaders"][0]
        assert row["ext_z"] is None
        assert row["conviction"]["score"] is None
        assert row["entry_signal"]["buy_zone"]["low"] is None
        assert row["entry_signal"]["buy_zone"]["high"] == 101.0
        assert row["theme"]["id"] == "ai_software"
        assert not any(math.isnan(v) for v in [1.8])  # sanity: finite values survive
        assert row["alpha"] == 1.8

    def test_spurious_sector_guard_sweeps_leaders(self):
        """The sector-integrity backstop must cover the new lane too — a junk sector
        label on a leaders row would otherwise ship straight to the strip."""
        wide = {"buy": [], "watch": [], "laggards": [],
                "leaders": [{"ticker": "GOOD", "sector": "Information Technology"},
                            {"ticker": "BLANK", "sector": None},
                            {"ticker": "JUNK", "sector": "history"}]}
        dropped = _drop_spurious_sector_rows(wide)
        assert [r["ticker"] for r in wide["leaders"]] == ["GOOD", "BLANK"]
        assert dropped["leaders"] == [("JUNK", "history")]

    def test_spurious_sector_guard_tolerates_missing_leaders_key(self):
        """Pre-migration shape (no leaders key) must not raise."""
        wide = {"buy": [{"ticker": "A", "sector": "Energy"}], "watch": [], "laggards": []}
        assert _drop_spurious_sector_rows(wide) == {}
        assert "leaders" not in wide


# ---------------------------------------------------------------------------
# E. G0.3 on REAL data — the committed 2026-07-31 fixture
# ---------------------------------------------------------------------------
#
# Everything above is synthetic: the numbers were chosen so the rule works, so they can
# only prove the rule is internally consistent. They would all still pass on a v2 that
# never surfaces a single software name in production, because no production number ever
# enters them. The masterplan's central claim (§0 G0.3) is an empirical one — "the leaders
# lane surfaces the software/AI cohort, not residual-alpha noise" — and this section is the
# only place it is measured.
#
# The fixture is real. Every field is the production call on committed caches as of
# 2026-07-31: total_return_z from engine.us_board_rank.total_return_z over the full 1563-name
# universe, above200/weekly_bull from signal_gate.gate, off_high from technicals.snapshot,
# dir from cycles.analyze, alpha from site/factordata/alpha.json, theme from the nightly
# baskets snapshot. Provenance and regeneration: scripts/dev/make_leaders_fixture.py.
#
# The fixture holds the top 40 names by momentum z plus the charter names, and the generator
# hard-asserts that no omitted universe name could reach the 15-row cap — so the strip these
# tests see is the strip production would have shipped, not a flattering subset.

_FIXTURE_PATH = (Path(__file__).resolve().parent
                 / "fixtures" / "leaders_v2_realdata_fixture.json")
_REALDATA = json.loads(_FIXTURE_PATH.read_text())
_COHORT_THEMES = {"ai_software", "non_ai_software"}


def _realdata_inputs(rows: list[dict] | None = None):
    """(scored, row_by_t, sig_verdict, kwargs) from the committed real-data fixture.

    Production shape, faithfully: a name with no residual alpha never becomes a board row
    (build_stock_library L2354) and `scored` is itself filtered to `t in row_by_t` (L3274),
    so `has_board_row` names are the only ones that reach the selector. Rows are rebuilt on
    every call — _select_leaders stamps lane='leader' onto the dicts it returns.
    """
    rows = _REALDATA["names"] if rows is None else rows
    board = [r for r in rows if r["has_board_row"]]
    row_by_t = {r["ticker"]: {"ticker": r["ticker"], "name": r["name"],
                              "sector": r["sector"], "alpha": r["alpha"],
                              "dir": r["dir"]}
                for r in board}
    scored = [(r["ticker"], {"composite_z": 0.0}) for r in board]
    sig_verdict = {r["ticker"]: {"above200": r["above200"],
                                 "weekly_bull": r["weekly_bull"], "eligible": False}
                   for r in rows}
    kwargs = {
        "momentum_by": {r["ticker"]: r["total_return_z"] for r in rows
                        if r["total_return_z"] is not None},
        "disp_by": {r["ticker"]: {"off_high": r["off_high"]} for r in rows},
        "theme_by": {r["ticker"]: r["theme"] for r in rows if r["theme"]},
    }
    return scored, row_by_t, sig_verdict, kwargs


def _realdata_leaders(**over):
    scored, rbt, sv, kw = _realdata_inputs()
    kw.update(over)
    return _select_leaders(scored, rbt, sv, set(), **kw)


def _by_ticker(ticker: str) -> dict:
    return next(r for r in _REALDATA["names"] if r["ticker"] == ticker)


class TestG03SoftwareCohortOnRealData:
    """The claim, measured: 2026-07-31, real board readings, real selector."""

    def test_the_strip_fills_to_the_cap(self):
        """Read this first — every exclusion assertion below is worthless without it.
        An empty or short strip would satisfy 'CALY is not present' trivially."""
        out = _realdata_leaders()
        assert len(out) == LEADERS_CAP
        assert all(r["lane"] == "leader" for r in out)

    def test_at_least_three_cohort_members_are_selected(self):
        """G0.3 verbatim: >= 3 members of ai_software / non_ai_software on the strip."""
        picked = _tickers(_realdata_leaders())
        cohort = [t for t in picked
                  if ((_by_ticker(t)["theme"] or {}).get("id")) in _COHORT_THEMES]
        assert len(cohort) >= 3, (
            f"only {len(cohort)} software-cohort names on the real-data strip: {cohort}")

    def test_the_cohort_members_are_the_expected_names(self):
        """Pin WHICH names, not just how many — a count-only assertion survives the
        selector picking three entirely different cohort members."""
        picked = set(_tickers(_realdata_leaders()))
        assert {"SNOW", "PANW", "CRWD"} <= picked

    def test_residual_alpha_only_names_are_excluded(self):
        """CALY / TMP / NHC are the names the v1 residual-alpha rule put on the strip
        (masterplan §1.3). v2 must not."""
        picked = set(_tickers(_realdata_leaders()))
        assert picked.isdisjoint(set(_REALDATA["residual_alpha_only"]))

    def test_the_excluded_names_lose_on_RANK_not_on_admission(self):
        """The load-bearing half of the exclusion.

        If CALY / TMP / NHC were simply inadmissible on 2026-07-31 — or absent from the
        fixture — the assertion above would pass on a selector that had regressed all the
        way back to v1. Lift the cap and they ARE selected: they clear every admission
        gate and are beaten purely by the momentum rank key.
        """
        big = _realdata_leaders(cap=len(_REALDATA["names"]))
        picked = set(_tickers(big))
        assert set(_REALDATA["residual_alpha_only"]) <= picked
        # …and they sit well below the cap, not one slot outside it
        order = _tickers(big)
        assert all(order.index(t) >= LEADERS_CAP
                   for t in _REALDATA["residual_alpha_only"])

    def test_the_v1_rule_would_have_inverted_this_on_the_same_data(self):
        """Counterfactual on the SAME real rows: v1 was `alpha >= 0.5`, alpha desc.

        This is the regression the lane exists to prevent, priced in real numbers — the
        residual-alpha rule selects all three small caps and cannot see SNOW at all: its
        residual is NEGATIVE (-0.15) while it is the #2 total-return name of 1563.
        """
        v1 = sorted((r for r in _REALDATA["names"]
                     if (r["alpha"] or -99) >= 0.5 and r["has_board_row"]),
                    key=lambda r: -r["alpha"])[:LEADERS_CAP]
        v1_tickers = {r["ticker"] for r in v1}
        assert set(_REALDATA["residual_alpha_only"]) <= v1_tickers
        assert "SNOW" not in v1_tickers
        assert _by_ticker("SNOW")["alpha"] < 0.5      # invisible to the v1 floor
        assert _by_ticker("SNOW")["z_rank"] == 2      # while leading on total return

    def test_the_selection_does_not_depend_on_input_order(self):
        """Same data, shuffled arrival order, identical strip — the board is rebuilt
        nightly and its row order is not a contract."""
        baseline = _tickers(_realdata_leaders())
        for seed in (0, 1, 7, 42):
            rows = list(_REALDATA["names"])
            random.Random(seed).shuffle(rows)
            scored, rbt, sv, kw = _realdata_inputs(rows)
            assert _tickers(_select_leaders(scored, rbt, sv, set(), **kw)) == baseline


class TestRealDataFixtureIntegrity:
    """Guards on the fixture itself — a fixture that quietly stops containing the case
    turns every assertion above into a tautology."""

    def test_pinned_to_the_measured_day(self):
        assert _REALDATA["as_of"] == "2026-07-31"
        assert _REALDATA["theme_as_of"] == "2026-07-31"
        assert _REALDATA["alpha_as_of"] == "2026-07-31"

    def test_every_charter_name_is_present(self):
        present = {r["ticker"] for r in _REALDATA["names"]}
        assert set(_REALDATA["cohort"]) <= present
        assert set(_REALDATA["residual_alpha_only"]) <= present

    def test_the_fixture_params_match_the_builder(self):
        """The fixture was generated against these constants; if the builder's cap or
        floor moves, the recorded faithfulness proof no longer describes this test."""
        p = _REALDATA["leaders_params"]
        assert p["cap"] == LEADERS_CAP
        assert p["off_high_floor"] == LEADERS_OFF_HIGH_FLOOR
        assert p["theme_boost"] == LEADERS_THEME_BOOST

    def test_no_omitted_universe_name_could_reach_the_cap(self):
        """The generator's faithfulness proof, re-asserted here: the 15th admitted name
        outscores the best any name outside the fixture could possibly reach."""
        f = _REALDATA["faithfulness"]
        assert f["cap_rank_key"] > f["omitted_ceiling"]
        assert f["omitted_ceiling"] == round(
            _REALDATA["universe"]["first_omitted_z"] + LEADERS_THEME_BOOST, 4)

    def test_the_residual_names_really_are_residual_alpha_freaks(self):
        """The fixture must keep reproducing the v1 failure: high residual alpha,
        unremarkable total momentum. If these ever invert, the counterfactual above
        stops proving anything."""
        for t in _REALDATA["residual_alpha_only"]:
            row = _by_ticker(t)
            assert row["alpha"] >= 0.5, f"{t} no longer clears the v1 alpha floor"
            assert row["z_rank"] > 100, f"{t} is now a genuine momentum leader"

    def test_the_cohort_carries_its_theme_membership(self):
        for t in _REALDATA["cohort"]:
            assert (_by_ticker(t)["theme"] or {}).get("id") in _COHORT_THEMES

    def test_pltr_is_recorded_as_structurally_inadmissible(self):
        """Honest disclosure, not a hidden hole: PLTR is a charter cohort name that did
        NOT qualify on 2026-07-31 (below its 200dma, 40% off its high). It is in the
        fixture so the fact is visible; pinned so a regeneration that flips it is seen."""
        pltr = _by_ticker("PLTR")
        assert pltr["above200"] is False
        assert pltr["off_high"] < LEADERS_OFF_HIGH_FLOOR
        assert "PLTR" not in _tickers(_realdata_leaders())

    def test_the_universe_behind_the_z_is_the_whole_board(self):
        """The z values are cross-sectional standings over the real universe, not a
        re-z of these 45 names — that is what makes SNOW's #1 meaningful."""
        u = _REALDATA["universe"]
        assert u["size"] > 1000
        assert u["z_names"] == u["size"]
        assert u["z_sessions"] == 63
        assert len(_REALDATA["names"]) < u["size"]
