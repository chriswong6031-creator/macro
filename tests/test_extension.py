"""Unit tests for engine/extension.py — the display-only extension / exhaustion axis.

These lock the validated semantics: ext_z is own-history extension, the parabolic flag is
the >2σ tail, valuation-vs-own-history reads the right tail, and the cohort gauge tiers.
None of this is ever scored — see reports/top-picks-freshness-phase0.md.
"""
import numpy as np
import pandas as pd
import pytest

from engine.extension import (ANCHOR_COVERAGE_FLOOR, ANCHOR_MAX_LOOKBACK,
                              LIVE_LOOKBACK, cohort_stretch, extension_signals,
                              grade, valuation_vs_history)


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
# came back `ext_z=None`.  These pin the heal AND the honesty condition on it: the floor
# must remove the panel-wide collapse WITHOUT inventing a reading for any single name.
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

    def test_the_sparse_trailing_row_is_inert(self, partial_advance_panel, covered_panel):
        """Not merely 'more names': the reading must be EXACTLY the one the panel gives
        without the half-finished row — same values, same anchor, nothing borrowed."""
        assert extension_signals(partial_advance_panel) == extension_signals(covered_panel)

    def test_a_healthy_panel_still_reads_its_newest_row(self, covered_panel):
        """No behaviour change on the days this never fired."""
        out = extension_signals(covered_panel)
        assert len(out) == MEMBERS
        assert {v["ext_asof"] for v in out.values()} == {"2026-08-06"}

    def test_the_shift_is_announced_as_a_github_annotation(
            self, partial_advance_panel, capsys):
        extension_signals(partial_advance_panel)
        lines = capsys.readouterr().out.splitlines()
        hit = [ln for ln in lines if "extension-anchor-shifted" in ln]
        assert hit, lines
        assert all(ln.startswith("::") for ln in hit)   # house law: annotations line-start


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

    def test_the_lookback_is_bounded_so_a_broken_panel_is_not_backdated(
            self, covered_panel, capsys):
        """No row in the search window clears the floor: read the newest row anyway —
        the pre-fix behaviour — rather than publishing a weeks-old cross-section as if
        it were today's.  Liveness is judged over a quarter, so an outage that short
        cannot redefine the membership down to its own survivors."""
        panel = covered_panel.copy()
        panel.loc[panel.index[-(ANCHOR_MAX_LOOKBACK + 2):], panel.columns[5:]] = np.nan
        out = extension_signals(panel)
        assert set(out) <= set(panel.columns[:5])
        assert {v["ext_asof"] for v in out.values()} == {"2026-08-06"}
        assert [ln for ln in capsys.readouterr().out.splitlines()
                if ln.startswith("::warning") and "extension-anchor-uncovered" in ln]


def test_the_floor_sits_between_the_broken_shapes_and_an_honest_session():
    """The constant is load-bearing in both directions: above a half-panel calendar
    collision (3 of 6 members) and a partial advance (0.2%), below the coverage a real
    session posts once halts and same-day listings are allowed for."""
    assert 0.5 < ANCHOR_COVERAGE_FLOOR < 0.95
    assert ANCHOR_MAX_LOOKBACK < LIVE_LOOKBACK
