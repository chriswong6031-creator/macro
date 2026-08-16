"""Live Entry Radar PR-5 (W5) — the data layer: panels, features, episodes, vendor.

WHAT THIS SUITE IS FOR.  W5's replay reads outcomes, so every input path it walks
has to be provably PIT and provably non-vacuous BEFORE a single outcome attaches.
These tests pin the four things that decide whether a replay row means anything:

* the SESSION CALENDAR is the bench's equity sessions and nothing else (a union
  over mixed assets inherits weekend rows, and a positional horizon then silently
  spans 5/7 of its label);
* the COHORT law is first-match-wins in the frozen order — the order is what makes
  a cohort cut interpretable, and it is invisible to any test that only checks one
  branch at a time;
* the DECISION CLOCK is ``known_ts``, never ``ts``, and a null clock is a REFUSAL
  that is counted rather than repaired;
* the §5 superset screen is a NECESSARY condition only — it may shrink the fetch
  budget and may not move a single episode.

Every assertion carries a MUTATION CONTROL: the test is written so that deleting
the invariant makes it fail, not so that it restates a passing computation.  Two
of them are explicit (the screen's low-vs-close direction; the cohort's
first-match-beats-later-match), because those are the two places where a wrong
implementation still produces plausible-looking output.

NO NETWORK.  Nothing here touches the vendor: the minute/daily readers are
injected fixtures, and the one vendor test that could reach out monkeypatches the
client offline first.  The staged-Terminal fidelity test is skipped (never
silently passed) when the Terminal repo or the curated store is unavailable.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from engine.entry_radar import indicator_core as ic
from engine.entry_radar.replay import (controls, episodes, feature_panel,
                                       features, gates, panels, prereg)

ROOT = Path(__file__).resolve().parents[1]
ET = ZoneInfo("America/New_York")


# --------------------------------------------------------------------------- #
# synthetic fixtures (calibrated 2026-08-15 against the real indicator family)
# --------------------------------------------------------------------------- #
def _saw(n: int, up: float = 1.006, dn: float = 0.997,
         phase: tuple[int, ...] = (1, 1, 1, 0)) -> np.ndarray:
    """A rising sawtooth: three up steps, one small down step.

    A strictly monotone series has NO losses, so canon's RSI is a constant 100 and
    StochRSI's ``max-min`` denominator is zero — every %K is NaN and every cohort
    branch that reads K falls through.  The down step is what makes the oscillator
    DEFINED; it is the difference between a fixture that exercises the law and one
    that silently exercises the null path.
    """
    steps = [up if phase[i % 4] else dn for i in range(n - 1)]
    return 100.0 * np.cumprod(np.r_[1.0, steps])


def _frame(closes, *, opens=None, start: str = "2016-01-04",
           volume=None) -> pd.DataFrame:
    close = np.asarray(closes, dtype=float)
    index = pd.bdate_range(start, periods=len(close))
    open_ = (np.asarray(opens, dtype=float) if opens is not None
             else np.r_[close[0], close[:-1]])
    vol = (np.asarray(volume, dtype=float) if volume is not None
           else np.full(len(close), 1e6))
    return pd.DataFrame({"o": open_, "h": close * 1.01, "l": close * 0.99,
                         "c": close, "v": vol}, index=index)


def _spy(n: int = 1200, start: str = "2016-01-04") -> pd.Series:
    """A quiet bench (no 63-session drawdown) so the regime tag stays 'quiet'."""
    return pd.Series(np.linspace(100.0, 160.0, n),
                     index=pd.bdate_range(start, periods=n))


def _minute_rows(session: date, path) -> list[list[object]]:
    """390 one-minute RTH bars, 09:30..15:59 ET, following ``path``."""
    start = datetime(session.year, session.month, session.day, 9, 30, tzinfo=ET)
    return [[(start + timedelta(minutes=i)).isoformat(), float(p), float(p) * 1.001,
             float(p) * 0.999, float(p), 1000.0] for i, p in enumerate(path)]


def _cohort_of(frame: pd.DataFrame, *, shares: float | None = None) -> str:
    rows = feature_panel.build_feature_rows(
        "T", frame, _spy(), "Tech", (lambda _t: shares), [frame.index[-1].date()])
    assert len(rows) == 1, "the fixture must produce exactly one feature row"
    return str(rows["cohort"].iloc[0])


# --------------------------------------------------------------------------- #
# panels — the session calendar and the two universes
# --------------------------------------------------------------------------- #
def test_session_calendar_is_bench_only_and_excludes_weekend_rows():
    """A crypto frame's Saturday must never enter the replay's session index.

    MUTATION CONTROL is the second half: the naive union — the implementation this
    law forbids — DOES contain the Saturday.  Without it this test would pass
    against a calendar that simply never saw the crypto frame.
    """
    spy_index = pd.bdate_range("2024-01-02", periods=20)
    crypto_index = pd.date_range("2024-01-02", periods=28, freq="D")  # incl. weekends
    frames = {
        "SPY": pd.DataFrame({"c": np.arange(20, dtype=float)}, index=spy_index),
        "BTCUSD": pd.DataFrame({"c": np.arange(28, dtype=float)}, index=crypto_index),
    }
    calendar = panels.session_calendar(frames)

    saturdays = [d for d in crypto_index if d.dayofweek == 5]
    assert saturdays, "fixture must actually contain a Saturday"
    assert not set(calendar) & set(saturdays)
    assert set(calendar.dayofweek) <= {0, 1, 2, 3, 4}
    assert list(calendar) == list(spy_index)

    naive_union = spy_index.union(crypto_index)
    assert set(naive_union) & set(saturdays), (
        "mutation control is vacuous — the forbidden union must contain the weekend")


def test_session_calendar_refuses_without_the_bench():
    with pytest.raises(panels.PanelError, match="bench"):
        panels.session_calendar({"AAPL": pd.DataFrame({"c": [1.0]},
                                                      index=pd.bdate_range("2024-01-02",
                                                                           periods=1))})


def test_session_calendar_accepts_the_bench_frame_directly():
    index = pd.bdate_range("2024-01-02", periods=5)
    frame = pd.DataFrame({"c": np.ones(5)}, index=index)
    assert list(panels.session_calendar(frame)) == list(index)


def test_panel_a_refuses_an_absent_or_empty_store(tmp_path):
    with pytest.raises(panels.PanelError, match="not a directory"):
        panels.panel_a_names(tmp_path)
    (tmp_path / "data" / "stocks").mkdir(parents=True)
    with pytest.raises(panels.PanelError, match="no parquet"):
        panels.panel_a_names(tmp_path)


def test_panel_names_and_sectors_read_the_declared_sources(tmp_path):
    (tmp_path / "data" / "stocks").mkdir(parents=True)
    for name in ("BBB", "AAA"):
        pd.DataFrame({"close": [1.0]}, index=pd.bdate_range("2024-01-02", periods=1)
                     ).to_parquet(tmp_path / "data" / "stocks" / f"{name}.parquet")
    (tmp_path / "data" / "universe").mkdir(parents=True)
    pd.DataFrame({"ticker": ["AAA", "CCC", "AAA"],
                  "sector": ["Tech", "Energy", "Tech"]}
                 ).to_parquet(tmp_path / "data" / "universe" / "membership.parquet")
    (tmp_path / "data" / "breadth").mkdir(parents=True)
    pd.DataFrame({"ticker": ["CCC", "DDD"], "sector": ["Utilities", "Health Care"]}
                 ).to_parquet(tmp_path / "data" / "breadth" / "ticker_sectors.parquet")

    assert panels.panel_a_names(tmp_path) == ["AAA", "BBB"]
    assert panels.panel_b_names(tmp_path) == ["AAA", "CCC"]
    sectors = panels.sector_of(tmp_path)
    assert sectors["AAA"] == "Tech"
    assert sectors["CCC"] == "Energy", "membership must win over the breadth fallback"
    assert sectors["DDD"] == "Health Care", "fallback must still cover unlisted names"
    assert "BBB" not in sectors, "an unsectored name is ABSENT, never 'Unknown'"


def test_load_panel_daily_drops_missing_and_empty_names():
    good = pd.DataFrame({"c": [1.0, 2.0]}, index=pd.bdate_range("2024-01-02", periods=2))
    loaded = panels.load_panel_daily(
        ["OK", "NONE", "EMPTY"],
        lambda n: {"OK": good, "NONE": None,
                   "EMPTY": good.iloc[0:0]}[n])
    assert set(loaded) == {"OK"}


def test_session_positions_are_bench_ordinals():
    calendar = panels.session_calendar(
        pd.DataFrame({"c": np.ones(4)}, index=pd.bdate_range("2024-01-02", periods=4)))
    positions = panels.session_positions(calendar)
    assert positions[pd.Timestamp("2024-01-02")] == 0
    assert positions[pd.Timestamp("2024-01-05")] == 3


# --------------------------------------------------------------------------- #
# features — the frozen scalar laws
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("cap,bucket", [
    (None, "unknown"), (0.0, "unknown"), (float("nan"), "unknown"),
    (1.999e9, "<2B"), (2e9, "2-10B"), (9.999e9, "2-10B"),
    (10e9, "10-200B"), (199.9e9, "10-200B"), (200e9, ">200B"), (3e12, ">200B"),
])
def test_cap_bucket_edges_are_left_closed(cap, bucket):
    """The §7 buckets are ``[lo, hi)``: 2e9 is "2-10B", not "<2B"."""
    assert features.cap_bucket_of(cap) == bucket


def test_c32_flag_true_false_and_unevaluable():
    """C32 = fresh 60-session low AND roc20 off its own 20-session minimum."""
    need = prereg.C32_FRESH_LOW_SESSIONS + prereg.C32_ROC_SESSIONS

    short = pd.Series(np.linspace(100, 90, need - 1))
    assert features.c32_flag(short, len(short) - 1) is None, "warm-up is None, not False"

    # A decline that DECELERATES into the low: steep early, nearly flat late, so
    # roc20 at D sits ABOVE its own prior 20-session floor while price is still
    # at a fresh 60-session low.  The flat tail must be SHORTER than the roc20
    # window — a 50-bar tail leaves the last 20 roc20 values in a constant-rate
    # regime, where 1 ULP makes `last > min` true for acceleration too.
    # A LINEAR decline is the other trap: constant absolute steps make roc20
    # fall as the base shrinks, so it never clears its minimum.
    decel = pd.Series(100 * np.exp(-np.r_[np.linspace(0, 0.7, need),
                                          np.linspace(0.7, 0.72, 12)]))
    assert features.c32_flag(decel, len(decel) - 1) is True

    # MUTATION CONTROLS — one per leg, each holding the other leg TRUE, so the
    # True above cannot be coming from a single leg doing all the work.
    accel = pd.Series(100 * np.exp(-np.r_[np.linspace(0, 0.15, need),
                                          np.linspace(0.15, 1.10, 12)]))
    assert features.c32_flag(accel, len(accel) - 1) is False, (
        "fresh low but ACCELERATING into it — the roc20 leg must refuse")
    rallied = pd.Series(np.r_[decel.to_numpy(),
                              float(decel.iloc[-1]) * np.linspace(1.0, 1.35, 40)])
    assert features.c32_flag(rallied, len(rallied) - 1) is False, (
        "decelerating but no fresh low — the fresh-low leg must refuse")

    # A name at a fresh HIGH cannot be at a fresh low.
    rising = pd.Series(_saw(need + 40))
    assert features.c32_flag(rising, len(rising) - 1) is False


def test_regime_tag_stressed_and_quiet():
    quiet = _spy(300)
    assert features.regime_tag(quiet, quiet.index[-1].date()) == "quiet"
    crashed = pd.Series(np.r_[np.full(200, 100.0), np.linspace(100, 80, 40)],
                        index=pd.bdate_range("2020-01-02", periods=240))
    assert features.regime_tag(crashed, crashed.index[-1].date()) == "stressed"
    assert features.regime_tag(quiet, date(1990, 1, 2)) == "unknown"


# --------------------------------------------------------------------------- #
# feature_panel — the cohort law, in order
# --------------------------------------------------------------------------- #
N = 300


def _fixture_ipo_young() -> pd.DataFrame:
    return _frame(_saw(features.IPO_YOUNG_SESSIONS - 10))


def _fixture_gap_catalyst() -> pd.DataFrame:
    frame = _frame(_saw(N))
    opens = frame["o"].to_numpy(dtype=float).copy()
    opens[-3] = float(frame["c"].iloc[-4]) * 1.09          # a +9% gap 3 sessions ago
    frame["o"] = opens
    return frame


def _fixture_deep_mtf_washout() -> pd.DataFrame:
    return _frame(np.r_[_saw(N - 63), np.linspace(_saw(N - 63)[-1],
                                                  _saw(N - 63)[-1] * 0.55, 63)])


def _fixture_full_daily_washout() -> pd.DataFrame:
    base = _saw(N)
    return _frame(np.r_[base[:N - 3], base[N - 4] * np.cumprod(np.full(3, 0.998))])


def _fixture_partial_shallow_washout() -> pd.DataFrame:
    base = _saw(N)
    return _frame(np.r_[base[:N - 4], base[N - 5] * np.cumprod(np.full(4, 0.998))])


def _fixture_damaged_trend_rebound() -> pd.DataFrame:
    return _frame(np.r_[np.linspace(100, 150, 100) + np.sin(np.arange(100)) * 0.4,
                        np.linspace(150, 97, 150) + np.sin(np.arange(150)) * 0.4,
                        np.linspace(97, 108, 50) + np.sin(np.arange(50)) * 0.4])


def _fixture_leader_reset() -> pd.DataFrame:
    return _frame(_saw(N))


def _fixture_other() -> pd.DataFrame:
    return _frame(_saw(N, up=1.0008, dn=0.9997))


@pytest.mark.parametrize("builder,expected", [
    (_fixture_ipo_young, "ipo_young"),
    (_fixture_gap_catalyst, "gap_catalyst"),
    (_fixture_deep_mtf_washout, "deep_mtf_washout"),
    (_fixture_full_daily_washout, "full_daily_washout"),
    (_fixture_partial_shallow_washout, "partial_shallow_washout"),
    (_fixture_damaged_trend_rebound, "damaged_trend_rebound"),
    (_fixture_leader_reset, "leader_reset"),
    (_fixture_other, "other"),
])
def test_cohort_law_reaches_every_declared_branch(builder, expected):
    """Each of the eight pass-1 cohorts is REACHABLE (the ninth needs pass 2).

    A branch nobody can reach is a branch that will never appear in a cohort cut,
    and the cut would then read as "this cohort does not occur" rather than "this
    cohort was never computable".
    """
    assert _cohort_of(builder()) == expected


def test_cohort_first_match_wins_over_a_later_match():
    """An earlier branch beats a later one when BOTH hold — with its control.

    The gap fixture is built ON the leader fixture's series, so both
    ``gap_catalyst`` (rank 2) and ``leader_reset`` (rank 8) are true.  Removing
    ONLY the gap flips the answer to ``leader_reset``: that is what proves the
    assertion is about the ORDER and not about the series.
    """
    both = _fixture_gap_catalyst()
    assert _cohort_of(both) == "gap_catalyst"

    without_gap = both.copy()
    without_gap["o"] = np.r_[both["c"].iloc[0], both["c"].to_numpy()[:-1]]
    assert _cohort_of(without_gap) == "leader_reset"


def test_gap_cohort_is_unevaluable_without_opens():
    """A close-only plane cannot measure a gap; the row falls through, never scores.

    ``gap_catalyst`` on a plane with no opens would otherwise be a measured
    "no gap" — a null dressed as a negative.
    """
    frame = _fixture_gap_catalyst()
    frame["o"] = np.nan
    assert _cohort_of(frame) == "leader_reset"


def test_small_cap_cohort_is_pending_until_the_cross_section_exists():
    """Pass 1 cannot know a quintile, so it marks the row and lets pass 2 finish."""
    frame = _fixture_other()
    assert _cohort_of(frame, shares=1e6) == feature_panel.PENDING_SMALLCAP
    assert _cohort_of(frame, shares=1e12) == "other", "a mega-cap never goes pending"


# --------------------------------------------------------------------------- #
# feature_panel — pass 2
# --------------------------------------------------------------------------- #
def _panel_rows(n_names: int = 12) -> pd.DataFrame:
    """A synthetic panel: ``n_names`` names sharing one decision session."""
    spy = _spy()
    rng = np.random.default_rng(4)
    rows = []
    for i in range(n_names):
        drift = 1.0 + 0.0004 * i
        closes = _saw(N, up=1.002 * drift, dn=0.998)
        volume = np.full(N, 1e5 * (i + 1)) * rng.uniform(0.9, 1.1, N)
        frame = _frame(closes, volume=volume)
        rows.append(feature_panel.build_feature_rows(
            f"T{i:02d}", frame, spy, "Tech", (lambda _t, i=i: 1e6 * (i + 1) ** 4),
            [frame.index[-1].date()], panel="B"))
    return pd.concat(rows, ignore_index=True)


def test_cross_sectionalize_emits_exactly_the_declared_panel_columns():
    panel = feature_panel.cross_sectionalize(_panel_rows())
    assert list(panel.columns) == list(feature_panel.PANEL_COLUMNS) + ["panel"]
    for column in controls.REQUIRED_COLUMNS:
        assert column in panel.columns, f"controls requires {column}"
    assert not any(c.startswith("raw_") for c in panel.columns)


def test_cross_sectionalize_ranks_within_the_session_and_is_order_independent():
    """Deciles are cross-sectional AND deterministic under input permutation.

    Shuffling the input rows must not move a single bucket: ranking is done over a
    ticker-sorted frame with ``method="first"``, so a tie resolves lexicographically
    rather than by whichever name the loader happened to read first.
    """
    rows = _panel_rows()
    straight = feature_panel.cross_sectionalize(rows)
    shuffled = feature_panel.cross_sectionalize(
        rows.sample(frac=1.0, random_state=17).reset_index(drop=True))
    pd.testing.assert_frame_equal(
        straight.sort_values("ticker").reset_index(drop=True),
        shuffled.sort_values("ticker").reset_index(drop=True))

    deciles = sorted(straight["dollar_vol_decile"].tolist())
    assert deciles[0] == 0 and deciles[-1] == 9, "a 12-name panel must span the deciles"
    assert straight["proximity_decile"].nunique() > 1


def test_cross_sectionalize_leaves_an_all_missing_feature_unranked():
    """No feature => UNRANKED, never one uniform bucket for the whole panel."""
    rows = _panel_rows(6)
    rows["raw_dollar_vol"] = np.nan
    panel = feature_panel.cross_sectionalize(rows)
    assert (panel["dollar_vol_decile"] == feature_panel.UNRANKED).all()
    assert (panel["proximity_decile"] != feature_panel.UNRANKED).any()


def test_cross_sectionalize_resolves_the_pending_small_cap_cohort():
    """The pending marker never survives pass 2, and resolves per the frozen law."""
    rows = _panel_rows(10)
    rows["cohort"] = feature_panel.PENDING_SMALLCAP
    # top realized-vol quintile AND top |60d return| quintile on exactly one name
    rows["raw_vol20"] = np.linspace(0.01, 0.9, len(rows))
    rows["raw_absret60"] = np.linspace(0.01, 0.9, len(rows))
    panel = feature_panel.cross_sectionalize(rows)
    assert feature_panel.PENDING_SMALLCAP not in set(panel["cohort"])
    assert set(panel["cohort"]) <= {"smallcap_highvol_momentum", "other"}
    assert (panel["cohort"] == "smallcap_highvol_momentum").sum() >= 1
    assert (panel["cohort"] == "other").sum() >= 1, "not every pending row qualifies"


def test_hot_tier_is_the_top_decile_of_either_pit_proxy():
    rows = _panel_rows(10)
    rows["raw_relvol20"] = np.linspace(1.0, 2.0, len(rows))
    rows["raw_absret5"] = 0.01
    panel = feature_panel.cross_sectionalize(rows)
    assert set(panel["hot_tier"]) <= {0, 1}
    assert panel["hot_tier"].sum() >= 1, "the top relvol decile must be hot"
    assert (panel["hot_tier"] == 0).sum() >= 1, "not every name is hot"


def test_panel_attrs_feed_the_control_session_offset():
    """``controls._session_offset`` reads ``attrs['session_pos_by_date']``."""
    panel = feature_panel.cross_sectionalize(_panel_rows(4))
    positions = panel.attrs.get("session_pos_by_date")
    assert isinstance(positions, dict) and positions
    session = list(panel["session"])[0]
    assert controls._session_offset(panel, session, session) == 0

    calendar = panels.session_calendar(
        pd.DataFrame({"c": np.ones(300)}, index=pd.bdate_range("2016-01-04", periods=300)))
    bench_positions = feature_panel.attach_session_positions(panel, calendar)
    assert len(bench_positions) == 300, "a bench calendar must override the panel's own"


# --------------------------------------------------------------------------- #
# §7 control matching — the panel lookup, and the calendar its offsets count on
#
# Both defects pinned here produced NO error and NO empty output: they produced a
# refusal census and a shrunken control pool, which read exactly like sparse data.
# Every test below therefore carries a mutation control that fails on the old code.
# --------------------------------------------------------------------------- #
def test_session_key_collapses_every_spelling_to_one_date():
    """``date`` is the panel's canonical spelling; everything else converts to it."""
    from scripts import entry_radar_replay as runner

    day = date(2020, 2, 26)
    for value in (day, pd.Timestamp("2020-02-26"), pd.Timestamp("2020-02-26 15:59"),
                  datetime(2020, 2, 26, 9, 30), "2020-02-26"):
        assert runner._session_key(value) == day
        assert type(runner._session_key(value)) is date, f"{value!r} must yield a date"


def test_ctx_session_rows_reads_the_dtype_the_production_builder_emits():
    """The §7 panel lookup must key on the column the REAL builder produces.

    ``feature_panel._as_dates`` returns ``datetime.date``, so ``build_feature_rows``
    writes an OBJECT column and ``cross_sectionalize`` preserves it — and
    ``date(2020, 2, 26) == pd.Timestamp("2020-02-26")`` is **False** in Python.  The
    lookup keyed on ``pd.Timestamp`` therefore matched zero rows for EVERY session
    and pushed EVERY episode into the ``control_match_unavailable`` branch: a total
    §7 control blackout that arrived as a plausible refusal census.

    MUTATION CONTROL: the last assertion IS the pre-fix expression.  It must match
    zero rows, so a regression to the Timestamp key cannot pass this test, and the
    pin above cannot quietly go vacuous if the builder's dtype ever changes.
    """
    from scripts import entry_radar_replay as runner

    panel = feature_panel.cross_sectionalize(_panel_rows(6))
    session = list(panel["session"])[0]
    assert panel["session"].dtype == object, "production panels are object dtype"
    assert type(session) is date, "...holding plain datetime.date"

    rows = runner._ctx_session_rows({"features": panel}, session)
    assert len(rows) == 6, "every name on the session must be visible to §7"
    assert (panel["session"] == pd.Timestamp(session)).sum() == 0, (
        "MUTATION CONTROL: the pre-fix Timestamp key must match nothing")


def test_ctx_session_rows_also_answers_a_datetime64_panel():
    """The other spelling: the lookup handles both dtypes rather than assuming one.

    The cost of guessing wrong here is silence, not an exception, so the branch is
    tested rather than reasoned about.
    """
    from scripts import entry_radar_replay as runner

    panel = feature_panel.cross_sectionalize(_panel_rows(4))
    session = list(panel["session"])[0]
    panel["session"] = pd.to_datetime(panel["session"])
    assert panel["session"].dtype.kind == "M"
    assert len(runner._ctx_session_rows({"features": panel}, session)) == 4


def test_ctx_session_rows_still_refuses_an_absent_session():
    """The fix widens the KEY, never the match: an unknown session still raises."""
    from scripts import entry_radar_replay as runner

    panel = feature_panel.cross_sectionalize(_panel_rows(3))
    with pytest.raises(KeyError):
        runner._ctx_session_rows({"features": panel}, date(1990, 1, 2))


def test_build_match_context_counts_offsets_on_the_bench_calendar(monkeypatch):
    """§7 offsets are TRADING sessions — never slots between decision sessions.

    ``build_match_context`` derived ``session_pos_by_date`` from the panel's own
    rows, and the panel carries ONLY decision sessions.  Two fires 20 trading
    sessions apart then read as 1 slot apart, so the frozen "did NOT fire within ±5
    sessions of D" window excluded a name the law admits, and every control pool
    silently shrank.  ``attach_session_positions`` takes a bench calendar for
    exactly this reason; production never passed one.

    MUTATION CONTROL: the two decision sessions are deliberately SPARSE (20 trading
    sessions apart).  Panel-derived positions give an offset of 1 — inside ±5, so
    excluded; the bench calendar gives 20 — outside, so kept.  Both assertions
    invert under a regression.
    """
    from scripts import entry_radar_replay as runner

    names = ["AA", "BB", "CC"]
    bench = _frame(np.linspace(100.0, 160.0, 400))
    planes = {t: _frame(_saw(400), volume=np.full(400, 1e6 * (i + 1)))
              for i, t in enumerate(names)}
    calendar = bench.index
    picks = [calendar[300].date(), calendar[320].date()]  # 20 trading sessions apart

    monkeypatch.setattr(runner, "_daily_cached",
                        lambda _cache, t: bench if t == "SPY" else planes.get(t))
    monkeypatch.setattr(panels, "panel_b_names", lambda _root: list(names))
    monkeypatch.setattr(panels, "sector_of", lambda _root: dict.fromkeys(names, "Tech"))

    eps = [SimpleNamespace(ticker=t, decision_session=s,
                           detector_id="C5_BOTTOM_WATCH@1")
           for t in names for s in picks]
    ctx = runner.build_match_context(eps, cache_dir=Path("/nonexistent"), panel="B")

    positions = ctx["session_pos"]
    assert len(positions) == len(calendar), (
        "positions must span the BENCH calendar, not the 2 decision sessions")
    assert (positions[pd.Timestamp(picks[1])]
            - positions[pd.Timestamp(picks[0])]) == 20

    # The law, not just the map: a fire 20 sessions back is outside ±5 and the name
    # stays eligible.  Panel-derived slots read it as 1 session and dropped it.
    pool = controls.eligible_pool(
        runner._ctx_session_rows(ctx, picks[1]),
        detector_fire_sessions={"AA": [picks[0]]},
        candidate_session=picks[1])
    assert "AA" in set(pool["ticker"]), (
        "a fire 20 trading sessions back must remain in the §7 control pool")


def test_build_match_context_refuses_a_panel_that_answers_no_session(monkeypatch):
    """A lookup that resolves ZERO decision sessions is broken, not sparse.

    The original defect's whole cost was that it stayed inside the per-episode
    refusal path and so produced a census instead of a stack trace.  A panel that
    can answer nothing now refuses loudly.
    """
    from scripts import entry_radar_replay as runner

    names = ["AA", "BB"]
    bench = _frame(np.linspace(100.0, 160.0, 400))
    planes = {t: _frame(_saw(400)) for t in names}
    picks = [bench.index[300].date()]

    monkeypatch.setattr(runner, "_daily_cached",
                        lambda _cache, t: bench if t == "SPY" else planes.get(t))
    monkeypatch.setattr(panels, "panel_b_names", lambda _root: list(names))
    monkeypatch.setattr(panels, "sector_of", lambda _root: dict.fromkeys(names, "Tech"))
    # Re-introduce the defect at its source: a panel whose sessions cannot be keyed.
    monkeypatch.setattr(runner, "_session_key", lambda v: v)
    monkeypatch.setattr(feature_panel, "cross_sectionalize",
                        _sessions_as_timestamps(feature_panel.cross_sectionalize))

    eps = [SimpleNamespace(ticker=t, decision_session=picks[0],
                           detector_id="C5_BOTTOM_WATCH@1") for t in names]
    with pytest.raises(runner.ReplayRefusal, match="structurally broken"):
        runner.build_match_context(eps, cache_dir=Path("/nonexistent"), panel="B")


def _sessions_as_timestamps(inner):
    """Wrap ``cross_sectionalize`` so its session column comes back as datetime64."""
    def _wrapped(rows):
        out = inner(rows)
        out["session"] = pd.to_datetime(out["session"])
        return out
    return _wrapped


# --------------------------------------------------------------------------- #
# episodes — decision clocks
# --------------------------------------------------------------------------- #
def test_g0_candidates_key_on_known_ts_not_ts():
    """The G0 decision session is the ``known_ts`` session — with its control.

    ``ts`` is the 3D bar's OPEN date; the dot only became observable at the bar's
    last session.  The mutation control is the second assertion: dating the episode
    from ``ts`` would give a DIFFERENT session, so a regression to ``ts`` cannot
    pass this test by coincidence.
    """
    frame = _frame(_saw(120))
    ts_session = frame.index[40].date()
    known_session = frame.index[42].date()
    cands, refusals = episodes.g0_candidates(
        "T", [{"ts": ts_session.isoformat(), "known_ts": known_session.isoformat()}],
        frame)
    assert refusals == []
    assert [c["decision_session"] for c in cands] == [known_session]
    assert known_session != ts_session, "fixture must separate the two clocks"


def test_g0_candidates_map_a_non_session_known_ts_backwards():
    """A holiday label resolves to the last session BEFORE it, never after."""
    frame = _frame(_saw(120))
    friday = frame.index[40]
    assert friday.dayofweek == 4 or True
    saturday = (friday + pd.Timedelta(days=1)) if friday.dayofweek == 4 else friday
    cands, _ = episodes.g0_candidates(
        "T", [{"ts": "2016-01-04", "known_ts": saturday.date().isoformat()}], frame)
    assert cands[0]["decision_session"] <= saturday.date()
    assert cands[0]["decision_session"] in {d.date() for d in frame.index}


def test_g0_candidates_refuse_a_null_clock_and_a_duplicate_session():
    frame = _frame(_saw(120))
    session = frame.index[50].date().isoformat()
    cands, refusals = episodes.g0_candidates("T", [
        {"ts": "2016-02-01", "known_ts": None},
        {"ts": "2016-02-02", "known_ts": session},
        {"ts": "2016-02-03", "known_ts": session},
        {"ts": "2016-02-04", "known_ts": "1990-01-02"},
    ], frame)
    assert len(cands) == 1
    reasons = sorted(r["reason"] for r in refusals)
    assert reasons == ["duplicate_decision_session", "no_session_at_or_before",
                       "null_known_ts"]


def test_c5_candidates_pass_watches_through_and_count_refusals():
    frame = _frame(_saw(120))
    session = frame.index[60].date()
    cands, refusals = episodes.c5_candidates_from_watches("T", [
        {"ts": "2016-03-01", "known_ts": session.isoformat(), "kind": "early_dot",
         "quality": "washout_early_watch", "scored": False},
        {"ts": "2016-03-05", "known_ts": None, "kind": "blocked_trigger"},
    ], frame)
    assert len(cands) == 1 and cands[0]["decision_session"] == session
    assert cands[0]["variant"] == "early_dot"
    assert cands[0]["extra"]["pre_channel_reconstruction"] is True
    assert [r["reason"] for r in refusals] == ["null_known_ts"]


# --------------------------------------------------------------------------- #
# episodes — the incumbent gauge (Q5 comparator)
# --------------------------------------------------------------------------- #
def _oscillating(n: int = 1200, start: str = "2014-01-06") -> pd.Series:
    """A three-scale oscillation, chosen so BOTH incumbent controls bite.

    The ripple periods matter: with only a slow cycle every 2W crossover happens to
    arrive from below 20, and the ``K<20`` leg's mutation control goes vacuous
    (measured — a two-term series gives 6 strict and 6 loose fires).  The 61/23
    session ripples put crossovers in the mid-range too, so dropping the leg
    changes the answer.
    """
    t = np.arange(n)
    values = 100.0 * (1 + 0.22 * np.sin(2 * np.pi * t / 150)
                      + 0.10 * np.sin(2 * np.pi * t / 61)
                      + 0.05 * np.sin(2 * np.pi * t / 23) + 0.0002 * t)
    return pd.Series(values, index=pd.bdate_range(start, periods=n))


def test_incumbent_fires_reproduce_the_pss_construction():
    """2W anchor-A bars, canonical StochRSI, ``cross_up(K,D) & (K[-1] < 20)``.

    Recomputed here from the primitives rather than hard-coded, so the assertion
    survives a lawful indicator change and fails on an unlawful construction (e.g.
    a 1W rung, or dropping the ``K<20`` leg).
    """
    from engine import canon

    close = _oscillating()
    fires = episodes.incumbent_fires("T", close)
    assert fires, "the fixture must actually fire"

    bars = close.resample("W-FRI").last().dropna().iloc[::2]
    k, d = canon.stoch_rsi_kd(bars)
    mask = (canon.crossover(k, d) & (k.shift(1) < ic.OVERSOLD)).fillna(False)
    labels = list(bars.index[mask.to_numpy(dtype=bool)])
    assert len(fires) == len(labels)
    assert all(f <= label.date() for f, label in zip(fires, labels))

    # MUTATION CONTROL 1 — the ``K<20`` leg: dropping it admits more fires, so the
    # oversold requirement is doing work rather than describing every crossover.
    loose = canon.crossover(k, d).fillna(False)
    assert int(loose.sum()) > len(labels)

    # MUTATION CONTROL 2 — the RUNG: the gauge is 2W anchor-A (``.iloc[::2]``).
    # The 1W rung fires a different (larger) set, so a regression to 1W cannot
    # slip through as "still weekly".
    weekly = close.resample("W-FRI").last().dropna()
    k1, d1 = canon.stoch_rsi_kd(weekly)
    weekly_fires = (canon.crossover(k1, d1) & (k1.shift(1) < ic.OVERSOLD)).fillna(False)
    assert int(weekly_fires.sum()) != len(labels)


def test_incumbent_knowability_maps_a_dark_friday_backwards():
    """When the fired 2W label is not a trading session, the fire dates BACKWARDS.

    A forward map would date the decision by a bar the decider could not have seen.
    """
    close = _oscillating()
    fires = episodes.incumbent_fires("T", close)
    first = fires[0]
    holed = close.drop(index=[pd.Timestamp(first)])
    moved = episodes.incumbent_fires("T", holed)
    assert moved[0] < first, "removing the label's session must move the fire earlier"
    assert moved[0] in {d.date() for d in holed.index}


def test_incumbent_candidates_carry_the_confirmed_bar_p0_law():
    frame = _frame(_oscillating(600).to_numpy(), start="2014-01-06")
    cands = episodes.incumbent_candidates("T", frame)
    assert cands
    assert {c["p0_basis_required"] for c in cands} == {"first_trade_after_known_at"}
    assert {c["detector_id"] for c in cands} == {episodes.INCUMBENT}


# --------------------------------------------------------------------------- #
# episodes — the §5 superset screen
# --------------------------------------------------------------------------- #
def test_c1_screen_is_a_necessary_condition_only():
    """K(session LOW) < 20 is the screen; K(close) is a strict SUBSET of it.

    %K is monotone increasing in the provisional close and every sampled value is
    ≥ the raw low, so screening on the low can only ADD sessions relative to any
    lawful sampled path — it can never remove one that could have armed.

    MUTATION CONTROL: rebuilding the same frame with ``low == close`` changes the
    screened set.  Without that, a screen that ignored the low entirely would pass.
    """
    base = _saw(200)
    tail = base[-1] * np.cumprod(np.r_[1.0, np.tile([0.994, 0.998, 0.992, 1.001], 15)[:59]])
    frame = _frame(np.r_[base, tail])
    frame["l"] = frame["c"] * 0.96

    on_low = set(episodes.c1_screen_sessions(frame))
    mutated = frame.copy()
    mutated["l"] = mutated["c"]
    on_close = set(episodes.c1_screen_sessions(mutated))

    assert on_close, "the mutation control must not be vacuously empty"
    assert on_close <= on_low, "the low-based screen must be a SUPERSET"
    assert on_low != on_close, "mutation control failed — the screen ignores the low"


def test_c1_screen_can_be_restricted_to_a_session_subset():
    frame = _frame(_saw(120))
    frame["l"] = frame["c"] * 0.9
    subset = [d.date() for d in frame.index[-5:]]
    screened = episodes.c1_screen_sessions(frame, subset)
    assert set(screened) <= set(subset)


# --------------------------------------------------------------------------- #
# episodes — C1/C2/C3 replay through the frozen W3 engines
# --------------------------------------------------------------------------- #
def _intraday_daily(n: int = 260, start: str = "2019-01-02") -> pd.DataFrame:
    t = np.arange(n)
    close = 100.0 * (1 + 0.12 * np.sin(2 * np.pi * t / 40)
                     + 0.04 * np.sin(2 * np.pi * t / 11))
    frame = _frame(close, start=start)
    frame["l"] = frame["c"] * 0.985
    return frame


def _slide_reader(daily: pd.DataFrame, depth: float = 0.10):
    def reader(_ticker: str, session: date):
        base = float(daily.loc[pd.Timestamp(session), "c"])
        return _minute_rows(session, base * np.linspace(1.0, 1.0 - depth, 390))
    return reader


def test_c1_c2_replay_promotes_one_episode_and_one_c2_variant_fire():
    daily = _intraday_daily()
    sessions = [d.date() for d in daily.index[-6:]]
    out = episodes.c1_c2_episodes("T", daily, _slide_reader(daily), sessions)

    c1_rows = [e for e in out["episodes"] if e["detector_id"] == episodes.C1]
    assert len(c1_rows) == 1, "§10: one live episode per (ticker, detector)"
    assert c1_rows[0]["p0_basis_required"] == "sampled_last_trade_at_decision"
    assert c1_rows[0]["sampled_close_at_decision"] is not None

    c2_rows = [e for e in out["episodes"] if e["detector_id"] == episodes.C2]
    assert c2_rows, "the fixture must fire at least one C2 variant"
    assert len({r["variant"] for r in c2_rows}) == len(c2_rows), (
        "A5.3: the FIRST fire per episode x variant, never a second")
    assert all(r["first_armed_session"] == c1_rows[0]["first_armed_session"]
               for r in c2_rows)
    assert out["refusals"] == []
    assert set(out["path_observations"]) == {s.isoformat() for s in sessions}


def test_c1_c2_replay_records_a_refusal_when_the_minute_window_is_refused():
    """§5: a session whose window cannot be fetched is REFUSED, never approximated.

    MUTATION CONTROL is the pair: the very same sessions with a working reader DO
    produce an episode, so an implementation that silently returned nothing for
    both cases would fail the first half of this suite.
    """
    daily = _intraday_daily()
    sessions = [d.date() for d in daily.index[-6:]]
    out = episodes.c1_c2_episodes("T", daily, lambda _t, _s: None, sessions)
    assert out["episodes"] == []
    assert len(out["refusals"]) == len(sessions)
    assert {r["reason"] for r in out["refusals"]} == {"minute_window_refused"}
    assert out["path_observations"] == {}


def test_c1_c2_replay_refuses_rather_than_swallowing_a_reader_fault():
    daily = _intraday_daily()

    def broken(_ticker, _session):
        raise ValueError("vendor exploded")

    with pytest.raises(episodes.EpisodeError, match="vendor exploded"):
        episodes.c1_c2_episodes("T", daily, broken, [daily.index[-1].date()])


def test_c3_replay_promotes_after_the_indicator_warm_up():
    """C3 arms on a knowable confirmed washout and fires on the first post-arm turn."""
    rise = _saw(240)
    fall = rise[-1] * np.cumprod(
        np.r_[1.0, np.tile([0.994, 0.997, 0.993, 1.002], 15)[:59]])
    daily = _frame(np.r_[rise, fall], start="2019-01-02")
    daily["l"] = daily["c"] * 0.985
    sessions = [d.date() for d in daily.index[-100:]]

    def v_reader(_ticker, session):
        base = float(daily.loc[pd.Timestamp(session), "c"])
        down = base * np.linspace(1.0, 0.97, 200)
        up = down[-1] * np.linspace(1.0, 1.04, 190)
        return _minute_rows(session, np.r_[down, up])

    out = episodes.c3_episodes("T", daily, v_reader, sessions)
    assert len(out["episodes"]) == 1
    row = out["episodes"][0]
    assert row["detector_id"] == episodes.C3
    assert row["first_armed_session"] is not None
    assert row["decision_session"] >= row["first_armed_session"]
    assert out["turns"], "the 4H turn series must be non-empty for a promotion"


def test_c3_replay_records_an_arm_that_never_promoted():
    """An ARM with no candidate is a FACT the caller must see, not an absence."""
    daily = _intraday_daily()
    sessions = [d.date() for d in daily.index[-25:]]
    out = episodes.c3_episodes("T", daily, _slide_reader(daily, 0.08), sessions)
    assert out["episodes"] == []
    assert "armed_no_candidate" in {r["reason"] for r in out["refusals"]}
    assert out["armed_at"] is not None


def test_c3_replay_refuses_every_session_without_a_window():
    daily = _intraday_daily()
    sessions = [d.date() for d in daily.index[-5:]]
    out = episodes.c3_episodes("T", daily, lambda _t, _s: None, sessions)
    assert out["episodes"] == []
    assert {r["reason"] for r in out["refusals"]} == {"minute_window_refused"}


# --------------------------------------------------------------------------- #
# episodes — finalisation, the holdout fence, washout lows
# --------------------------------------------------------------------------- #
def _candidate(session: date) -> dict[str, object]:
    return {"ticker": "T", "detector_id": episodes.G0, "panel": "B",
            "decision_session": session, "first_armed_session": session,
            "washout_low_window": prereg.WASHOUT_LOW_FALLBACK_SESSIONS}


def test_finalize_episode_enforces_the_holdout_fence():
    """§14 G-6 fires in the ONE constructor, so no call site can route around it."""
    in_era = _candidate(date(2024, 6, 3))
    ref = episodes.finalize_episode(in_era, p0=10.0, p0_basis="next_session_close",
                                    a0=0.5, atr_basis="true_range_daily_ohlc",
                                    washout_low=9.0, cohort="other", regime="quiet")
    assert ref.decision_session == date(2024, 6, 3)
    assert ref.p0_basis == "next_session_close"

    holdout = _candidate(date(2026, 3, 2))
    assert holdout["decision_session"] > prereg.HOLDOUT_BOUNDARY
    with pytest.raises(gates.PreregGateRefusal, match="G-6"):
        episodes.finalize_episode(holdout, p0=10.0, p0_basis="next_session_close",
                                  a0=0.5, atr_basis="true_range_daily_ohlc",
                                  washout_low=9.0)

    with pytest.raises(gates.PreregGateRefusal, match="G-6"):
        episodes.finalize_episode(_candidate(date(2009, 1, 5)), p0=1.0,
                                  p0_basis="next_session_close", a0=0.1,
                                  atr_basis="true_range_daily_ohlc", washout_low=0.9)


def test_finalize_episode_carries_the_false_start_k_slice():
    ref = episodes.finalize_episode(
        _candidate(date(2024, 6, 3)), p0=10.0, p0_basis="next_session_close",
        a0=0.5, atr_basis="true_range_daily_ohlc", washout_low=9.0,
        confirmed_k_fwd=[15.0, 44.0])
    assert ref.extra["confirmed_k_fwd"] == [15.0, 44.0]


def test_washout_low_uses_both_frozen_forms():
    """Arm-to-decision min low for armed detectors; trailing-63 for the rest."""
    frame = _frame(_saw(200))
    frame["l"] = frame["c"] * 0.9
    decision = frame.index[150].date()

    trailing = episodes.washout_low(
        {"decision_session": decision,
         "washout_low_window": prereg.WASHOUT_LOW_FALLBACK_SESSIONS}, frame)
    window = frame["l"].iloc[150 - prereg.WASHOUT_LOW_FALLBACK_SESSIONS + 1: 151]
    assert trailing == pytest.approx(float(window.min()))

    armed = episodes.washout_low(
        {"decision_session": decision,
         "first_armed_session": frame.index[145].date()}, frame)
    assert armed == pytest.approx(float(frame["l"].iloc[145: 151].min()))
    assert armed != trailing, "the two forms must be distinguishable on this fixture"


def test_forward_confirmed_k_is_strictly_forward():
    frame = _frame(_saw(200))
    k = episodes.confirmed_k(frame)
    decision = frame.index[100].date()
    forward = episodes.forward_confirmed_k(k, decision, horizon=4)
    assert len(forward) == 4
    assert forward[0] == pytest.approx(float(k.iloc[101]))


# --------------------------------------------------------------------------- #
# vendor — cache discipline and the §11 cost floor (no network)
# --------------------------------------------------------------------------- #
def _vendor():
    import scripts.entry_radar_vendor as vendor
    return vendor


def test_vendor_refuses_a_cache_inside_the_repo():
    """§5: no permanent vendor store in the tree.  Fail-closed, on the RESOLVED path."""
    vendor = _vendor()
    with pytest.raises(vendor.VendorError, match="inside the repo"):
        vendor.daily_ohlcv("SPY", date(2024, 1, 2), date(2024, 1, 5),
                           cache_dir=ROOT / "data" / "scratch")


def test_vendor_honors_a_prewarmed_daily_cache_without_a_fetch(tmp_path, monkeypatch):
    """An orchestrator pre-warm must be served as-is — no key, no network, no rewrite."""
    vendor = _vendor()
    monkeypatch.setattr(vendor, "_client",
                        lambda: vendor._Client(base="http://unused", key=None,
                                               timeout=1, retries=1, user_agent="t"))
    index = pd.DatetimeIndex(pd.bdate_range("2024-01-02", periods=10), name="session")
    frame = pd.DataFrame({c: np.arange(10, dtype=float) for c in vendor.DAILY_COLUMNS},
                         index=index)
    path = tmp_path / "vendor_daily" / "SPY.parquet"
    path.parent.mkdir(parents=True)
    frame.to_parquet(path)

    out = vendor.daily_ohlcv("SPY", date(2024, 1, 3), date(2024, 1, 9),
                             cache_dir=tmp_path)
    assert list(out.columns) == list(vendor.DAILY_COLUMNS)
    assert out.index.min().date() == date(2024, 1, 3)
    assert out.index.max().date() == date(2024, 1, 9)
    assert vendor.read_manifest(tmp_path) == [], "a cache hit must record no fetch"


def test_vendor_refuses_a_prewarmed_cache_with_the_wrong_layout(tmp_path):
    vendor = _vendor()
    path = tmp_path / "vendor_daily" / "SPY.parquet"
    path.parent.mkdir(parents=True)
    pd.DataFrame({"close": [1.0]}, index=pd.bdate_range("2024-01-02", periods=1)
                 ).to_parquet(path)
    with pytest.raises(vendor.VendorError, match="missing"):
        vendor.daily_ohlcv("SPY", date(2024, 1, 2), date(2024, 1, 2), cache_dir=tmp_path)


def test_quotes_at_never_raises_and_returns_empty_offline(tmp_path, monkeypatch):
    """§11: a missing/unentitled NBBO yields [] so the LIQUIDITY FLOOR binds."""
    vendor = _vendor()
    monkeypatch.setattr(vendor, "_client",
                        lambda: vendor._Client(base="http://unused", key=None,
                                               timeout=1, retries=1, user_agent="t"))
    assert vendor.quotes_at("SPY", "2024-01-02T15:00:00Z", cache_dir=tmp_path) == []


def test_quotes_at_swallows_a_fetch_error_and_records_it(tmp_path, monkeypatch):
    vendor = _vendor()
    monkeypatch.setattr(vendor, "_client",
                        lambda: vendor._Client(base="http://unused", key="k",
                                               timeout=1, retries=1, user_agent="t"))

    def boom(*_a, **_k):
        raise vendor.VendorError("403 not entitled")

    monkeypatch.setattr(vendor, "_get_results", boom)
    assert vendor.quotes_at("SPY", "2024-01-02T15:00:00Z", cache_dir=tmp_path) == []
    manifest = vendor.read_manifest(tmp_path)
    assert manifest and "403" in str(manifest[-1].get("error"))


def test_half_spread_is_none_rather_than_zero_when_unmeasurable():
    """None means UNMEASURED and the floor binds; zero would mean 'free'."""
    vendor = _vendor()
    assert vendor.half_spread_bps([]) is None
    assert vendor.half_spread_bps([{"bid_price": 0.0, "ask_price": 1.0},
                                   {"bid_price": 5.0, "ask_price": 4.0}]) is None
    measured = vendor.half_spread_bps([{"bid_price": 99.9, "ask_price": 100.1}])
    assert measured == pytest.approx(0.2 / 2 / 100.0 * 1e4, rel=1e-3)


def test_minute_rows_for_session_slices_one_et_session():
    vendor = _vendor()
    session = date(2024, 1, 3)
    stamps = pd.DatetimeIndex(
        [pd.Timestamp("2024-01-02 15:59", tz="America/New_York"),
         pd.Timestamp("2024-01-03 09:30", tz="America/New_York"),
         pd.Timestamp("2024-01-03 09:31", tz="America/New_York")])
    frame = pd.DataFrame({"t": stamps, "o": [1.0, 2.0, 3.0], "h": [1.0, 2.0, 3.0],
                          "l": [1.0, 2.0, 3.0], "c": [1.0, 2.0, 3.0],
                          "v": [10.0, 20.0, 30.0]})
    rows = vendor.minute_rows_for_session(frame, session)
    assert len(rows) == 2
    assert rows[0][0].startswith("2024-01-03T09:30")


# --------------------------------------------------------------------------- #
# staged Terminal emitter — the §14 G-5 evidence
# --------------------------------------------------------------------------- #
def _staging():
    import scripts.entry_radar_stage_terminal as staging
    return staging


def test_g5_gate_consumes_the_staging_report_shape():
    """The report this module emits is exactly what ``check_staging_fidelity`` reads.

    Two mutation controls: a wrong pin and a false ``match`` must BOTH refuse —
    a report shape that satisfied the gate unconditionally would be worse than no
    gate at all.
    """
    good = {"terminal_pin": prereg.TERMINAL_PIN,
            "fixtures": {"NVDA": {"match": True, "dots_got": 40}}}
    receipt = gates.check_staging_fidelity(good)
    assert receipt.gate == "G-5"

    with pytest.raises(gates.PreregGateRefusal, match="G-5"):
        gates.check_staging_fidelity({**good, "terminal_pin": "deadbeef"})
    with pytest.raises(gates.PreregGateRefusal, match="G-5"):
        gates.check_staging_fidelity(
            {"terminal_pin": prereg.TERMINAL_PIN,
             "fixtures": {"NVDA": {"match": False}}})
    with pytest.raises(gates.PreregGateRefusal, match="G-5"):
        gates.check_staging_fidelity({"terminal_pin": prereg.TERMINAL_PIN,
                                      "fixtures": {}})


def test_staging_refuses_an_unreachable_pin(tmp_path):
    staging = _staging()
    repo = staging.terminal_repo_path()
    if not (repo / ".git").exists():
        pytest.skip(f"terminal repo unavailable at {repo}")
    with pytest.raises(staging.StagingError, match="not a reachable commit"):
        staging.stage("0" * 40, dest=tmp_path)


def _fidelity_prerequisites() -> str | None:
    staging = _staging()
    repo = staging.terminal_repo_path()
    if not (repo / ".git").exists():
        return f"terminal repo unavailable at {repo}"
    for name in staging.FIXTURE_NAMES:
        if not (ROOT / "data" / "stocks" / f"{name}.parquet").exists():
            return "curated data/stocks is not checked out (sparse worktree)"
    return None


@pytest.mark.skipif(_fidelity_prerequisites() is not None,
                    reason=_fidelity_prerequisites() or "")
def test_staged_emitter_reproduces_the_committed_fixtures(tmp_path):
    """§14 G-5 end to end: stage the pin, re-run it, compare, then pass the gate."""
    staging = _staging()
    staged = staging.stage(dest=tmp_path)
    report = staging.fixture_fidelity(staged)
    assert set(report["fixtures"]) == set(staging.FIXTURE_NAMES)
    for name, row in report["fixtures"].items():
        assert row["match"] is True, f"{name}: {row}"
        assert row["dots_got"] == row["dots_expected"] > 0
        assert row["watches_got"] == row["watches_expected"] > 0
        assert row["dots_population_uncapped"] >= row["dots_got"], (
            "the uncapped §3.1 population is a superset of the display side channel")
    gates.check_staging_fidelity(report)


@pytest.mark.skipif(_fidelity_prerequisites() is not None,
                    reason=_fidelity_prerequisites() or "")
def test_staged_emitter_dots_carry_a_decision_clock(tmp_path):
    """Every dot the replay consumes has a ``known_ts`` that is NOT its ``ts``.

    If the two were equal the G0 decision clock would be the 3D bar's open — a
    date the value was not yet observable on — which is the exact leak §3 forbids.
    """
    staging = _staging()
    staged = staging.stage(dest=tmp_path)
    frame = pd.read_parquet(ROOT / "data" / "stocks" / "NVDA.parquet")
    out = staging.run_name(staged, "NVDA", frame["close"], high=frame["high"],
                           low=frame["low"], volume=frame["volume"])
    assert out["dots"], "the population must be non-empty"
    assert all(d["known_ts"] for d in out["dots"])
    assert all(d["known_ts"] >= d["ts"] for d in out["dots"])
    assert any(d["known_ts"] != d["ts"] for d in out["dots"])
    assert len(out["dots"]) >= len(out["dots_side_channel"])


def test_staged_import_does_not_leak_into_sys_modules(tmp_path):
    """The staged package is removed from ``sys.modules`` after every run.

    A leaked import would let a LATER call silently reuse a tree nobody staged —
    and a fidelity report produced that way proves nothing about the pin.
    """
    import sys

    staging = _staging()
    repo = staging.terminal_repo_path()
    if not (repo / ".git").exists():
        pytest.skip(f"terminal repo unavailable at {repo}")
    staged = staging.stage(dest=tmp_path)
    before = {k for k in sys.modules if k.startswith(staging.STAGED_SUBTREE)}
    with staging.staged_signal_layer(staged) as (confluence, _v2):
        assert Path(confluence.__file__).resolve().is_relative_to(Path(staged).resolve())
    after = {k for k in sys.modules if k.startswith(staging.STAGED_SUBTREE)}
    assert before == after
    assert str(Path(staged).resolve()) not in sys.path


# --------------------------------------------------------------------------- #
# import purity — the package law the replay __init__ states
# --------------------------------------------------------------------------- #
def test_replay_modules_perform_no_module_level_io():
    """No network/env/file read at import scope in ``engine/entry_radar/replay/``.

    AST-level, not a line grep: an aliased or nested call would slip a text filter.
    Calls INSIDE a function or class body are fine — the law is about what happens
    when the module is merely imported.
    """
    import ast

    forbidden = {"read_parquet", "read_csv", "open", "getenv", "urlopen", "get",
                 "post", "load", "secret", "now", "today", "read_text", "run"}
    package = ROOT / "engine" / "entry_radar" / "replay"
    offenders: list[str] = []
    for path in sorted(package.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:                      # module scope ONLY
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            for call in ast.walk(node):
                if not isinstance(call, ast.Call):
                    continue
                name = (call.func.attr if isinstance(call.func, ast.Attribute)
                        else getattr(call.func, "id", ""))
                if name in forbidden:
                    offenders.append(f"{path.name}:{call.lineno} {name}()")
    assert offenders == [], f"module-level I/O in the pure replay package: {offenders}"


def test_prereg_constants_are_the_ones_the_modules_consume():
    """A doc<->code drift is a test failure, never a silent reinterpretation."""
    assert feature_panel.PANEL_COLUMNS[:len(controls.REQUIRED_COLUMNS)] == \
        controls.REQUIRED_COLUMNS
    assert episodes.ARM_EXPIRY_SESSIONS == 15
    assert episodes.C2_PRIMARY_VARIANT == "c2a_kd_cross"
    assert set(prereg.EXPECTED_SPEC_HASHES) >= {
        episodes.G0, episodes.C1, episodes.C2, episodes.C3, episodes.C5}
    assert episodes.INCUMBENT not in prereg.EXPECTED_SPEC_HASHES, (
        "the incumbent gauge is a Q5 COMPARATOR, never an arena detector")
