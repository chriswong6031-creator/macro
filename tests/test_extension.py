"""Unit tests for engine/extension.py — the display-only extension / exhaustion axis.

These lock the validated semantics: ext_z is own-history extension, the parabolic flag is
the >2σ tail, valuation-vs-own-history reads the right tail, and the cohort gauge tiers.
None of this is ever scored — see reports/top-picks-freshness-phase0.md.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine.extension import (
    ANCHOR_COVERAGE_FLOOR,
    ANCHOR_MARGIN_NOTE,
    ANCHOR_MAX_AGE,
    ANCHOR_MIN_LIVE,
    EXT_Z_MIN_ROWS,
    LIVE_LOOKBACK,
    cohort_stretch,
    extension_signals,
    grade,
    valuation_vs_history,
)

REPO = Path(__file__).resolve().parent.parent


def _dates(n):
    return pd.bdate_range("2022-01-03", periods=n)


def test_grade_thresholds():
    assert grade(2.5, 0.99) == "parabolic"      # >2σ own-history extension
    assert grade(2.0, 0.5) == "parabolic"
    assert grade(1.4, 0.7) == "stretched"
    assert grade(1.0, 0.99) == "stretched"
    assert grade(0.2, 0.95) == "intrend"        # near highs, not stretched
    assert grade(0.2, 0.50) == "steady"         # not stretched, not near highs
    assert grade(None, 0.9) == "na"
    assert grade(float("nan"), 0.9) == "na"


def test_extension_signals_parabolic_vs_steady():
    n = 320
    idx = _dates(n)
    # STEADY: a gentle compounding uptrend → moderate, in-trend extension
    steady = pd.Series(100 * (1.0008) ** np.arange(n), index=idx)
    # SPIKE: flat for most of the window, then a sharp late run-up → high ext_z, near highs
    base = np.concatenate([np.full(n - 25, 100.0),
                           100 * (1.05) ** np.arange(1, 26)])
    spike = pd.Series(base, index=idx)
    closes = pd.DataFrame({"STEADY": steady, "SPIKE": spike})

    out = extension_signals(closes)
    assert {"STEADY", "SPIKE"} <= set(out)
    # the late spike is far more extended vs its own history than the steady grinder
    assert out["SPIKE"]["ext_z"] > out["STEADY"]["ext_z"]
    assert out["SPIKE"]["ext_z"] >= 2.0 and out["SPIKE"]["parabolic"] is True
    assert out["SPIKE"]["grade"] == "parabolic"
    # both are pressing their 52-week highs (monotone up to the end)
    assert out["SPIKE"]["near_52wh"] > 0.99
    assert 0.0 < out["STEADY"]["near_52wh"] <= 1.0
    # steady grinder is not flagged parabolic
    assert out["STEADY"]["parabolic"] is False


def test_extension_signals_skips_short_history():
    closes = pd.DataFrame({"NEW": pd.Series(range(50), index=_dates(50), dtype=float)})
    assert extension_signals(closes) == {}            # < the rolling minimums → omitted
    assert extension_signals(pd.DataFrame()) == {}


def test_valuation_vs_history_richest_when_price_runs_up():
    n = 300
    idx = _dates(n)
    # price triples over the window → current earnings yield is the lowest it's been
    price = pd.Series(np.linspace(50, 150, n), index=idx)
    closes = pd.DataFrame({"RICH": price})
    panel = pd.DataFrame({"ticker": ["RICH"], "asof_date": [pd.Timestamp("2021-06-01")],
                          "ni": [1_000_000.0], "shares": [1_000_000.0]})  # EPS = 1.0, constant
    out = valuation_vs_history(closes, panel)
    assert "RICH" in out
    assert out["RICH"]["ey_pctile"] <= 10            # richest decile of its own history
    assert out["RICH"]["val_label"] == "richest"


def test_valuation_vs_history_cheap_when_price_falls():
    n = 300
    idx = _dates(n)
    price = pd.Series(np.linspace(150, 50, n), index=idx)   # price falls → EY rises → cheap
    closes = pd.DataFrame({"CHEAP": price})
    panel = pd.DataFrame({"ticker": ["CHEAP"], "asof_date": [pd.Timestamp("2021-06-01")],
                          "ni": [1_000_000.0], "shares": [1_000_000.0]})
    out = valuation_vs_history(closes, panel)
    assert out["CHEAP"]["ey_pctile"] >= 66
    assert out["CHEAP"]["val_label"] == "cheap"


def test_valuation_vs_history_degrades_gracefully():
    assert valuation_vs_history(pd.DataFrame(), pd.DataFrame()) == {}
    # ticker with no fundamentals row is simply absent
    closes = pd.DataFrame({"X": pd.Series(range(300), index=_dates(300), dtype=float)})
    assert valuation_vs_history(closes, pd.DataFrame(
        {"ticker": [], "asof_date": [], "ni": [], "shares": []})) == {}


def test_cohort_stretch_tiers():
    assert cohort_stretch([{"ext_z": 0.0}] * 3)["state"] == "na"      # too few names
    normal = [{"ext_z": 0.0, "grade": "steady", "near_52wh": 0.7} for _ in range(20)]
    assert cohort_stretch(normal)["state"] == "normal"
    stretched = [{"ext_z": 1.5, "grade": "stretched", "near_52wh": 0.99} for _ in range(20)]
    s = cohort_stretch(stretched)
    assert s["state"] == "stretched"
    assert s["pct_stretched"] == 100 and s["n"] == 20


def test_extension_signals_never_returns_nan_fields():
    out = extension_signals(pd.DataFrame(
        {"A": pd.Series(100 * (1.001) ** np.arange(320), index=_dates(320))}))
    for v in out.values():
        assert not (isinstance(v["ext_z"], float) and np.isnan(v["ext_z"]))
        assert v["grade"] in {"intrend", "steady", "stretched", "parabolic"}


# --------------------------------------------------------------------------- #
# the sparse-last-row defect: a partial price advance must not blank the board
# --------------------------------------------------------------------------- #
# Measured on the US board run of 2026-08-06: the equity close panel's newest row held
# 6 of 3,034 members — `panel.through=2026-08-07, majority_through=2026-08-06,
# members_at_through=6, mixed_vintage=true` in the artifact's staleness block — because
# the price advance was caught mid-refresh.  `extension_signals` read one global
# `.iloc[-1]`, so the extension map collapsed to those 6 names and all 69 buy-lane rows
# came back `ext_z=None`.  These pin the heal AND the two honesty conditions on it: the
# anchor must remove the panel-wide collapse WITHOUT inventing a reading for any single
# name, and WITHOUT letting an older session's reading reach a consumer undeclared.
MEMBERS = 500            # 1 fresh member on the newest row == 0.2%, the 6/3,034 shape
ROWS = 400
BOARD = [f"T{i:04d}" for i in range(69)]        # stands in for the 69 buy-lane rows


def _walk(index, seed):
    rng = np.random.default_rng(seed)
    return pd.Series(
        100 * np.cumprod(1.0 + 0.0006 + rng.normal(0, 0.012, len(index))), index=index)


@pytest.fixture(scope="module")
def covered_panel():
    """A healthy 500-name equity panel through 2026-08-06 — no sparse tail."""
    idx = pd.bdate_range(end="2026-08-06", periods=ROWS)
    return pd.DataFrame({f"T{i:04d}": _walk(idx, i) for i in range(MEMBERS)})


@pytest.fixture(scope="module")
def partial_advance_panel(covered_panel):
    """...with ONE more calendar row carrying a single member: the partial advance."""
    fresh = pd.Timestamp("2026-08-07")
    row = pd.DataFrame(np.nan, index=[fresh], columns=covered_panel.columns)
    row.loc[fresh, "T0499"] = float(covered_panel["T0499"].iloc[-1]) * 1.01
    out = pd.concat([covered_panel, row])
    out.index = pd.DatetimeIndex(out.index)
    return out


def _old_positional_read(closes: pd.DataFrame) -> set[str]:
    """The pre-fix rule, verbatim: ONE global `.iloc[-1]`, every NaN dropped."""
    px = closes.sort_index()
    ext = px / px.rolling(200, min_periods=100).mean() - 1.0
    ez = ((ext - ext.rolling(252, min_periods=120).mean())
          / ext.rolling(252, min_periods=120).std().replace(0, np.nan)).iloc[-1]
    return {t for t in px.columns if pd.notna(ez.get(t))}


class TestPartialPriceAdvance:

    def test_the_fixture_is_the_measured_shape(self, partial_advance_panel):
        last = partial_advance_panel.iloc[-1]
        assert last.notna().sum() == 1
        assert last.notna().mean() <= 0.003                  # 6/3,034 == 0.20%
        assert partial_advance_panel.iloc[-2].notna().all()  # the row before is full

    def test_the_old_positional_rule_blanked_every_board_row(self, partial_advance_panel):
        """What shipped on 2026-08-06: the read collapsed to whoever happened to have
        printed, and no board row was among them."""
        survivors = _old_positional_read(partial_advance_panel)
        assert survivors == {"T0499"}
        assert not (survivors & set(BOARD))

    def test_the_coverage_floor_anchors_to_the_last_covered_session(
            self, partial_advance_panel):
        out = extension_signals(partial_advance_panel)
        assert set(BOARD) <= set(out)
        assert len(out) == MEMBERS
        assert {v["ext_asof"] for v in out.values()} == {"2026-08-06"}

    def test_every_served_row_declares_the_vintage_it_was_read_at(
            self, partial_advance_panel):
        """The heal's whole risk is an older session's reading scored as today's.  A
        consumer cannot avoid that unless the age is ON the row it consumes — so both
        fields are unconditional, and the age is a NUMBER of sessions, not a flag."""
        out = extension_signals(partial_advance_panel)
        assert {v["ext_age"] for v in out.values()} == {1}
        assert all(v["ext_asof"] == "2026-08-06" for v in out.values())
        assert all({"ext_asof", "ext_age"} <= set(v) for v in out.values())

    def test_the_sparse_trailing_row_moves_no_reading(
            self, partial_advance_panel, covered_panel):
        """PIT soundness, kept: the half-finished row must not change a single value —
        the reading is EXACTLY the one the panel gives without it, nothing borrowed and
        nothing recomputed.  `ext_age` is the one field that legitimately differs, and
        it differs in the honest direction: the truncated panel has no leading edge to
        be behind (0), the sparse-tailed one is one row behind its own (1)."""
        a = extension_signals(partial_advance_panel)
        b = extension_signals(covered_panel)

        def _readings(d):
            return {t: {k: v for k, v in r.items() if k != "ext_age"} for t, r in d.items()}

        assert _readings(a) == _readings(b)                  # values AND ext_asof
        assert {v["ext_age"] for v in a.values()} == {1}
        assert {v["ext_age"] for v in b.values()} == {0}

    def test_the_anchor_never_selects_a_row_after_the_newest(self, partial_advance_panel):
        """PIT: the read is the panel truncated at the anchor.  No lookahead is possible
        if the anchored session is never later than a session the panel already holds,
        and if truncating there reproduces the values exactly."""
        out = extension_signals(partial_advance_panel)
        asof = pd.Timestamp(next(iter(out.values()))["ext_asof"])
        assert asof <= partial_advance_panel.index.max()
        truncated = extension_signals(partial_advance_panel.loc[:asof])
        assert {t: r["ext_z"] for t, r in out.items()} == \
               {t: r["ext_z"] for t, r in truncated.items()}

    def test_a_healthy_panel_still_reads_its_newest_row(self, covered_panel):
        """No behaviour change on the days this never fired."""
        out = extension_signals(covered_panel)
        assert len(out) == MEMBERS
        assert {v["ext_asof"] for v in out.values()} == {"2026-08-06"}
        assert {v["ext_age"] for v in out.values()} == {0}

    def test_the_shift_is_announced_as_a_github_annotation(
            self, partial_advance_panel, capsys):
        extension_signals(partial_advance_panel)
        lines = capsys.readouterr().out.splitlines()
        hit = [ln for ln in lines if "extension-anchor-shifted" in ln]
        assert hit, lines
        assert all(ln.startswith("::") for ln in hit)   # house law: annotations line-start
        assert "1 row(s) behind" in hit[0], hit          # the age is IN the annotation


class TestTheFloorNeverFabricates:

    def test_a_name_absent_from_the_anchor_row_is_still_null(self, partial_advance_panel):
        """The floor heals the PANEL, never the name: a member halted through the
        anchored session stays unknown rather than borrowing an older close."""
        panel = partial_advance_panel.copy()
        panel.loc[panel.index[-4:], "T0007"] = np.nan
        out = extension_signals(panel)
        assert "T0007" not in out                    # per-name null, printed honestly
        assert len(out) == MEMBERS - 1
        assert {v["ext_asof"] for v in out.values()} == {"2026-08-06"}

    def test_long_dead_members_do_not_sit_in_the_denominator(self, covered_panel):
        """A library carries names that stopped trading months ago.  If they counted as
        live the floor would be unreachable on a perfectly healthy session — and they
        must still read null individually."""
        panel = covered_panel.copy()
        dead = list(panel.columns[:250])             # half the panel, dark for 6 months
        panel.loc[panel.index[-130:], dead] = np.nan
        out = extension_signals(panel)
        assert {v["ext_asof"] for v in out.values()} == {"2026-08-06"}   # newest row
        assert not (set(dead) & set(out))

    def test_an_outage_past_the_age_cap_is_not_served_at_all(
            self, covered_panel, capsys):
        """The fail-closed half.  No row within ANCHOR_MAX_AGE clears the floor, so
        there is no current reading to give — and the answer is NOTHING, printed with a
        reason.  Reading the newest row anyway is what blanked the board; reaching
        further back publishes a stale cross-section as today's.  Liveness is judged
        over a quarter, so an outage this short cannot redefine the membership down to
        its own survivors and call itself covered."""
        panel = covered_panel.copy()
        panel.loc[panel.index[-(ANCHOR_MAX_AGE + 2):], panel.columns[5:]] = np.nan
        assert extension_signals(panel) == {}
        warn = [ln for ln in capsys.readouterr().out.splitlines()
                if ln.startswith("::warning") and "extension-anchor-uncovered" in ln]
        assert warn
        assert "serving NO extension read" in warn[0]

    def test_the_survivors_of_an_outage_are_not_served_either(self, covered_panel):
        """The five names still printing through the outage are exactly the trap: they
        have a current reading, and serving it would publish a 5-name board as if the
        panel were healthy.  A withheld panel is withheld for everyone."""
        panel = covered_panel.copy()
        panel.loc[panel.index[-(ANCHOR_MAX_AGE + 2):], panel.columns[5:]] = np.nan
        assert not (set(extension_signals(panel)) & set(panel.columns[:5]))


class TestTheAgeCapIsTheFailClosedBoundary:
    """A reading may lag the panel's leading edge by at most ANCHOR_MAX_AGE rows.  One
    row is the measured mid-refresh partial advance; beyond the cap the honest output is
    no output.  These pin BOTH sides of the boundary so it cannot drift silently."""

    @staticmethod
    def _panel_with_blank_tail(rows: int):
        idx = pd.bdate_range(end="2026-08-06", periods=ROWS)
        panel = pd.DataFrame({f"T{i:04d}": _walk(idx, i) for i in range(60)})
        if rows:
            panel.loc[panel.index[-rows:], panel.columns[1:]] = np.nan
        return panel

    def test_at_the_cap_the_read_is_served_and_stamped_with_its_age(self):
        out = extension_signals(self._panel_with_blank_tail(ANCHOR_MAX_AGE))
        assert out
        assert {v["ext_age"] for v in out.values()} == {ANCHOR_MAX_AGE}

    def test_one_row_past_the_cap_nothing_is_served(self):
        assert extension_signals(self._panel_with_blank_tail(ANCHOR_MAX_AGE + 1)) == {}

    def test_the_caller_may_tighten_the_cap_but_the_default_is_the_constant(self):
        panel = self._panel_with_blank_tail(1)
        assert {v["ext_age"] for v in extension_signals(panel).values()} == {1}
        assert extension_signals(panel, max_age=ANCHOR_MAX_AGE) == extension_signals(panel)
        assert extension_signals(panel, max_age=0) == {}


class TestStrictModeForAnyoneWritingADatedHistory:
    """`froth_fragility` stamps the cohort parabolicity — computed from these readings —
    into a percentile history under the BOARD's asof (`_parab_history`, keyed on the
    build date).  The moment a value is written under a date, its own age is gone: a
    2-session-old cross-section becomes a permanent, wrong, dated observation.  So the
    module offers `max_age=0`: a current-session reading or none at all."""

    @staticmethod
    def _stale_panel():
        idx = pd.bdate_range(end="2026-08-06", periods=ROWS)
        panel = pd.DataFrame({f"T{i:04d}": _walk(idx, i) for i in range(60)})
        panel.loc[panel.index[-1], panel.columns[1:]] = np.nan
        return panel

    def test_strict_refuses_a_stale_reading_the_default_would_serve(self):
        panel = self._stale_panel()
        assert {v["ext_age"] for v in extension_signals(panel).values()} == {1}
        assert extension_signals(panel, max_age=0) == {}

    def test_strict_serves_a_current_session_normally(self):
        idx = pd.bdate_range(end="2026-08-06", periods=ROWS)
        healthy = pd.DataFrame({f"T{i:04d}": _walk(idx, i) for i in range(60)})
        out = extension_signals(healthy, max_age=0)
        assert len(out) == 60
        assert {v["ext_age"] for v in out.values()} == {0}

    def test_strict_still_prints_a_reason_when_it_withholds(self, capsys):
        extension_signals(self._stale_panel(), max_age=0)
        assert [ln for ln in capsys.readouterr().out.splitlines()
                if ln.startswith("::warning") and "extension-anchor-uncovered" in ln]


class TestTheFloorIsAPanelRuleNotAPerNameGate:
    """A fraction floor over a handful of names IS a per-name gate: at n_live=3 one
    absent name is 33 points of coverage.  Measured on the shipped code, a 3-name panel
    with one name printing served all three off the previous row — including the one
    that had printed — and a ONE-column frame (`intl_equity_risk` passes exactly that,
    as does `replay_standout_pipeline` per ticker) silently read the prior session
    whenever the last cell was NaN.  Below ANCHOR_MIN_LIVE there is no walk-back."""

    @staticmethod
    def _tiny(n_cols: int, absent: list[str]):
        idx = pd.bdate_range(end="2026-08-06", periods=ROWS)
        panel = pd.DataFrame({f"S{i}": _walk(idx, i) for i in range(n_cols)})
        panel.loc[panel.index[-1], absent] = np.nan
        return panel

    def test_a_three_name_panel_does_not_backdate_the_name_that_printed(self):
        out = extension_signals(self._tiny(3, ["S0", "S1"]))
        assert set(out) == {"S2"}                     # the two silent names stay null
        assert out["S2"]["ext_asof"] == "2026-08-06"  # ...and S2 keeps its OWN session
        assert out["S2"]["ext_age"] == 0

    def test_a_single_column_frame_never_borrows_the_previous_session(self):
        """The PIT contract `replay_standout_pipeline` states at its call site — that
        extension_signals reads ONLY the last row of the matrix it is passed — holds
        again for a one-column frame."""
        assert extension_signals(self._tiny(1, ["S0"])) == {}

    def test_the_walk_back_switches_on_at_the_minimum_live_count(self):
        """Either side of ANCHOR_MIN_LIVE, on the same shape: below it the newest row
        is read as-is, at it the panel rule applies and the anchor may step back."""
        below = extension_signals(
            self._tiny(ANCHOR_MIN_LIVE - 1, [f"S{i}" for i in range(ANCHOR_MIN_LIVE - 1)]))
        at = extension_signals(
            self._tiny(ANCHOR_MIN_LIVE, [f"S{i}" for i in range(ANCHOR_MIN_LIVE - 1)]))
        assert below == {}                            # newest row, nobody resolves
        assert len(at) == ANCHOR_MIN_LIVE             # walked back one covered row
        assert {v["ext_age"] for v in at.values()} == {1}


class TestTheGateMeasuresWhatIsServed:
    """The floor has to be read off the RESOLVABILITY of ext_z, not off close presence.
    Measured on the shipped code: 300 names x 210 rows of gapless closes is 100%
    'covered', serves 0 of 300 names, and printed nothing at all."""

    def test_a_fully_covered_panel_that_resolves_nobody_is_announced(self, capsys):
        idx = pd.bdate_range(end="2026-08-06", periods=EXT_Z_MIN_ROWS - 9)
        panel = pd.DataFrame({f"T{i:04d}": _walk(idx, i) for i in range(300)})
        assert panel.notna().all().all()              # 100% close coverage
        assert extension_signals(panel) == {}
        warn = [ln for ln in capsys.readouterr().out.splitlines()
                if ln.startswith("::warning") and "extension-unresolvable" in ln]
        assert warn, "a 300-name panel serving nobody must not be silent"

    def test_a_small_frame_that_resolves_nobody_stays_quiet(self, capsys):
        """...but a per-ticker caller asking about a young name is ordinary, not a
        defect: annotating it would spam the Actions summary once per ticker."""
        idx = pd.bdate_range(end="2026-08-06", periods=EXT_Z_MIN_ROWS - 9)
        assert extension_signals(pd.DataFrame({"NEW": _walk(idx, 1)})) == {}
        assert not [ln for ln in capsys.readouterr().out.splitlines()
                    if ln.startswith("::warning")]

    def test_ext_z_first_resolves_exactly_at_EXT_Z_MIN_ROWS(self):
        """The constant is measured, not asserted: it is the row count at which a
        gapless column's ext_z becomes non-null, so it cannot rot away from the
        min_periods it summarises."""
        def _resolves(rows):
            idx = pd.bdate_range(end="2026-08-06", periods=rows)
            frame = pd.DataFrame({f"T{i:04d}": _walk(idx, i) for i in range(ANCHOR_MIN_LIVE)})
            return bool(extension_signals(frame))

        assert _resolves(EXT_Z_MIN_ROWS)
        assert not _resolves(EXT_Z_MIN_ROWS - 1)


class TestTheAnchorChoiceDisclosesItsOwnInstability:
    """The floor is a cliff and the module holds no cross-build state to hysterese
    against.  Measured: one extra absent name flips names-served 61 -> 100 and the
    anchor back two sessions.  What the module CAN do is say when the choice is close
    enough to the floor that a name or two would move it."""

    @staticmethod
    def _panel(absent_newest: int):
        idx = pd.bdate_range(end="2026-08-06", periods=ROWS)
        panel = pd.DataFrame({f"C{i:03d}": _walk(idx, i) for i in range(100)})
        panel.loc[panel.index[-1], panel.columns[:absent_newest]] = np.nan
        return panel

    def test_an_anchor_sitting_just_above_the_floor_says_so(self, capsys):
        out = extension_signals(self._panel(39))          # 61% coverage
        assert {v["ext_age"] for v in out.values()} == {0}
        assert [ln for ln in capsys.readouterr().out.splitlines()
                if ln.startswith("::warning") and "extension-anchor-marginal" in ln]

    def test_a_comfortable_anchor_says_nothing(self, capsys):
        extension_signals(self._panel(5))                 # 95% coverage
        assert not [ln for ln in capsys.readouterr().out.splitlines()
                    if "extension-anchor-marginal" in ln]

    def test_the_band_is_the_constant_it_claims_to_be(self, capsys):
        """One name inside the band and one outside it, so the disclosure boundary is
        pinned to ANCHOR_MARGIN_NOTE rather than to a number that happened to work."""
        just_inside = round(100 * (1 - (ANCHOR_COVERAGE_FLOOR + ANCHOR_MARGIN_NOTE))) + 1
        extension_signals(self._panel(just_inside))
        assert [ln for ln in capsys.readouterr().out.splitlines()
                if "extension-anchor-marginal" in ln]
        extension_signals(self._panel(just_inside - 2))
        assert not [ln for ln in capsys.readouterr().out.splitlines()
                    if "extension-anchor-marginal" in ln]


class TestTheVintageReachesTheGaugeThatScoresOnIt:
    """`cohort_stretch` tiers the cohort on hard ext_z cutoffs, so it is the first
    consumer that could score a stale read blind.  It carries the vintage of what it
    tiered — including the case `build_stock_library` creates by design, where equities
    and crypto are anchored on SEPARATE calendars and unioned into one map."""

    def test_the_gauge_reports_the_session_it_tiered(self):
        rows = [{"ext_z": 0.0, "grade": "steady", "near_52wh": 0.7,
                 "ext_asof": "2026-08-06", "ext_age": 1} for _ in range(20)]
        out = cohort_stretch(rows)
        assert out["asof"] == "2026-08-06"
        assert out["age"] == 1 and out["mixed_vintage"] is False

    def test_a_union_of_two_anchored_panels_is_flagged_not_averaged(self):
        rows = [{"ext_z": 0.0, "grade": "steady", "near_52wh": 0.7,
                 "ext_asof": "2026-08-06", "ext_age": 0} for _ in range(18)]
        rows += [{"ext_z": 0.0, "grade": "steady", "near_52wh": 0.7,
                  "ext_asof": "2026-08-04", "ext_age": 2} for _ in range(4)]
        out = cohort_stretch(rows)
        assert out["mixed_vintage"] is True
        assert out["asof"] is None                  # there is no single one to report
        assert out["age"] == 2                      # the OLDEST, not the average

    def test_the_thin_cohort_still_carries_its_vintage(self):
        out = cohort_stretch([{"ext_z": 0.0, "ext_asof": "2026-08-06", "ext_age": 0}] * 3)
        assert out["state"] == "na" and out["asof"] == "2026-08-06"

    def test_readings_without_vintage_degrade_instead_of_raising(self):
        out = cohort_stretch([{"ext_z": 0.0, "grade": "steady"} for _ in range(20)])
        assert out["state"] == "normal"
        assert out["asof"] is None and out["age"] is None


# --------------------------------------------------------------------------- #
# the floor, calibrated against real sessions instead of against itself
# --------------------------------------------------------------------------- #
# Committed close stores, each on ONE calendar — the shape the anchor is designed for.
SINGLE_CALENDAR_STORES = (
    "data/china_search/closes.parquet",
    "data/canada_search/closes.parquet",
    "data/hk_search/closes_deep.parquet",
    "data/breadth/_closes_cache.parquet",
)
# ...and one store that is NOT: international names across many holiday calendars, the
# same union-of-calendars shape `extension_panels` exists to split apart.
MIXED_CALENDAR_STORE = "data/intl_search/closes.parquet"
# A session only counts once every live member has had a full liveness window in which
# to resolve — before that the panel is still warming up and coverage is meaningless.
WARMUP_ROWS = EXT_Z_MIN_ROWS + LIVE_LOOKBACK


def _session_coverage(px: pd.DataFrame) -> np.ndarray:
    """Per-session resolvability coverage, exactly as `_anchor_row` computes it, for
    every mature row in the store.  Deterministic: no sampling, no RNG."""
    px = px.sort_index()
    sma = px.rolling(200, min_periods=100).mean()
    ext = px / sma - 1.0
    ez = (ext - ext.rolling(252, min_periods=120).mean()) \
        / ext.rolling(252, min_periods=120).std().replace(0, np.nan)
    ok = ez.notna()
    n_live = ok.rolling(LIVE_LOOKBACK, min_periods=1).max().astype(bool).sum(axis=1)
    cov = ok.sum(axis=1) / n_live.replace(0, np.nan)
    return cov.iloc[WARMUP_ROWS:].dropna().to_numpy(dtype=float)


def _measure(rel: str) -> np.ndarray | None:
    p = REPO / rel
    if not p.exists():
        return None
    try:
        return _session_coverage(pd.read_parquet(p))
    except Exception:  # noqa: BLE001 — a corrupt/unreadable store is not evidence
        return None


@pytest.fixture(scope="module")
def measured():
    """Every mature session in each committed single-calendar store, measured once."""
    got = {s: c for s in SINGLE_CALENDAR_STORES
           if (c := _measure(s)) is not None and len(c)}
    if len(got) < 2:
        pytest.skip(f"need 2+ committed close stores, found {sorted(got)}")
    return got


class TestTheFloorIsCalibratedOnRealSessions:
    """`0.5 < ANCHOR_COVERAGE_FLOOR < 0.95` asserted constants against constants and
    proved nothing; 0.60 itself came from one snapshot.  This replays the floor over
    every mature session in the committed close stores and asserts what actually has to
    be true of it — measured at authoring over 8,458 sessions across four stores:

        china_search   968 sessions   min 0.9578   nothing below 0.85
        canada_search 1011 sessions   min 1.0000   nothing below 0.85
        hk_search     6411 sessions   min 0.9881   nothing below 0.85
        breadth         68 sessions   min 0.9900   nothing below 0.85

    Real sessions cluster at ~1.0; the broken shapes sit at 0.2% (the partial advance)
    and 50% (a 5-day calendar sharing a panel with 24/7 crypto).  The floor is a choice
    inside an EMPTY band, which is the property that makes it robust: no value in
    roughly (0.55, 0.95) would behave differently on this evidence.  Asserted as
    properties of the distribution, never as equality against a stored number, because
    these stores are refreshed nightly.
    """

    def test_the_replay_is_not_vacuous(self, measured):
        total = sum(len(c) for c in measured.values())
        assert total >= 500, {s: len(c) for s, c in measured.items()}

    def test_no_real_session_is_anywhere_near_the_floor(self, measured):
        """The claim the constant makes: on a single-calendar panel the floor never
        fires.  Reported per store so a genuine future outage names itself."""
        worst = {s: float(c.min()) for s, c in measured.items()}
        assert all(v > ANCHOR_COVERAGE_FLOOR for v in worst.values()), worst
        assert all(np.percentile(c, 1) > ANCHOR_COVERAGE_FLOOR + 0.25
                   for c in measured.values()), \
            {s: float(np.percentile(c, 1)) for s, c in measured.items()}

    def test_the_floor_sits_in_an_empty_band_so_its_exact_value_is_not_load_bearing(
            self, measured):
        """The anti-fitting assertion.  If real sessions crowded just above 0.60 the
        constant would be a tuned threshold and one bad session would move the anchor;
        they do not, so any floor in the band is the same floor."""
        lo, hi = ANCHOR_COVERAGE_FLOOR - 0.05, ANCHOR_COVERAGE_FLOOR + 0.25
        share = {s: float(((c >= lo) & (c < hi)).mean()) for s, c in measured.items()}
        assert all(v <= 0.005 for v in share.values()), share

    def test_the_broken_shapes_fall_below_the_floor(self):
        """The other side of the separation, in the two shapes actually observed: the
        6-of-3,034 partial advance, and a crypto-only row in a mixed-calendar panel."""
        assert 6 / 3034 < ANCHOR_COVERAGE_FLOOR
        assert 3 / 6 < ANCHOR_COVERAGE_FLOOR

    def test_a_mixed_calendar_store_is_where_the_floor_would_misfire(self):
        """The measurement that justifies splitting panels BEFORE anchoring, rather
        than trusting the floor to survive a union of calendars: on international names
        across many holiday calendars ~11% of sessions land in the band that is empty
        on every single-calendar store, and some fall below the floor outright.  A
        panel like this must be split, not anchored — which is what `extension_panels`
        does, and what tests/test_ext_panel_calendar.py pins."""
        cov = _measure(MIXED_CALENDAR_STORE)
        if cov is None or not len(cov):
            pytest.skip(f"{MIXED_CALENDAR_STORE} not available")
        lo, hi = ANCHOR_COVERAGE_FLOOR - 0.05, ANCHOR_COVERAGE_FLOOR + 0.25
        in_band = float(((cov >= lo) & (cov < hi)).mean())
        assert in_band > 0.01, in_band
        assert cov.min() < ANCHOR_COVERAGE_FLOOR, float(cov.min())
