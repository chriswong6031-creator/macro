"""Live Entry Radar PR-3 (W3) — C1/C2 point-in-time battery.

WHAT THIS SUITE IS FOR
----------------------
C1 and C2 are the only Radar detectors that read a **provisional** bar, so they
are the only ones that can leak the future by arithmetic rather than by
bookkeeping.  Every test below is a leak test with a named contract row:

  PIT-1   a C1 reading at T survives arbitrary mutation of every minute after T
          and of the session's eventual EOD close/high/low
  PIT-2   the same, for all six C2 variants at once
  PIT-4   the turn predicate carries NO current-K<20 requirement
  PIT-5   a C2c pivot is knowable only at j+1
  PIT-6   C2f measures the rebound off the SAMPLED low, never a raw minute low
  PIT-11  premarket and postmarket prints cannot move an RTH reading
  PIT-17  appending future sessions cannot move a reading behind the edge
  PIT-18  a missing ATR makes C2f UNAVAILABLE, never False

THE MUTATION TESTS APPLY THE MUTATION.  Each one runs the detector a second time
with the named defect substituted in and asserts the result CHANGES.  An
assertion that merely restates the passing behaviour proves the code does what it
does today; it does not prove the property is load-bearing.

THE FIXTURE IS SYNTHETIC AND SAYS SO.  ``tests/fixtures/entry_radar/w3_*.json``
carry a machine-readable provenance manifest (``w3_provenance.json``);
``scripts/entry_radar_fixture_gen.py`` is the generator and the receipt.  The
morphology is CONSTRUCTED by inverting canonical StochRSI, because the boundary
cases this suite needs (a flash low three ATR below every sampled point, on the
one bar where it matters) appear in a real session only by accident.

Nothing here reads ``data/``, ``site/`` or the network.
"""
from __future__ import annotations

import copy
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from engine.entry_radar import challengers as ch
from engine.entry_radar import indicator_core as ic
from engine.entry_radar.four_hour import tape_from_rows
from engine.entry_radar.readings import canonical_readings

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "entry_radar"
ET = ZoneInfo("America/New_York")
TICKER = "ZZWO"


# ---------------------------------------------------------------------------
# fixture loading (shared with the C3 and C4 suites)
# ---------------------------------------------------------------------------

def load_fixture(name: str = "w3_c1c2_path.json") -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def daily_history(fixture: dict, *, rows: list[list] | None = None,
                  price_basis: str = ch.BASIS_ADJUSTED,
                  blank_ohlc: bool = False) -> ch.DailyHistory:
    """Build the confirmed daily frame from the fixture's ``daily`` block."""
    rows = list(fixture["daily"]["rows"] if rows is None else rows)
    frame = pd.DataFrame([r[1:] for r in rows],
                         columns=["open", "high", "low", "close"],
                         index=pd.DatetimeIndex([r[0] for r in rows]))
    if blank_ohlc:
        frame = frame.assign(high=float("nan"), low=float("nan"))
    return ch.DailyHistory(frame=frame, price_basis=price_basis,
                           vintage="w3-fixture")


def session_tapes(fixture: dict, *, tapes: list[dict] | None = None,
                  price_basis: str | None = None) -> list[ch.SessionTape]:
    out = []
    for raw in (fixture["tapes"] if tapes is None else tapes):
        out.append(tape_from_rows(
            date.fromisoformat(raw["session"]), raw["rows"],
            price_basis=price_basis or raw["price_basis"], vintage="w3-fixture",
            tz=ET))
    return out


def observation_path(fixture: dict, **kwargs) -> tuple[ch.Observation, ...]:
    return ch.build_observation_path(
        ticker=TICKER, daily=kwargs.pop("daily", None) or daily_history(fixture),
        tapes=kwargs.pop("tapes", None) or session_tapes(fixture), **kwargs)


@pytest.fixture(scope="module")
def fixture() -> dict:
    return load_fixture()


@pytest.fixture(scope="module")
def path(fixture) -> tuple[ch.Observation, ...]:
    return observation_path(fixture)


@pytest.fixture(scope="module")
def c1_run(path) -> ch.C1Run:
    return ch.run_c1(path)


@pytest.fixture(scope="module")
def c2_run(path, c1_run) -> ch.C2Run:
    return ch.run_c2(path, c1_run.episode)


def _k_by_time(path) -> dict[str, float | None]:
    return {o.observed_at: o.k for o in path}


def _readings_at_or_before(readings, cutoff: str):
    return [r for r in readings if r.observed_at <= cutoff]


# ---------------------------------------------------------------------------
# fixture morphology — the properties the PIT tests below depend on
# ---------------------------------------------------------------------------

def test_fixture_provenance_is_recorded_as_synthetic():
    manifest = json.loads((FIXTURES / "w3_provenance.json").read_text(encoding="utf-8"))
    for name, row in manifest["files"].items():
        assert row["kind"] in {"synthetic", "real"}, name
        assert row["source"], name
        assert row["vintage"], name
    assert "w3_c1c2_path.json" in manifest["files"]


def test_fixture_morphology_is_the_one_the_battery_needs(path, c1_run, c2_run):
    """A fixture that lost its morphology makes every test below vacuous."""
    ks = [o.k for o in path if o.k is not None]
    assert max(ks) >= 35.0, "the path must open above 35"
    assert 4.0 <= min(ks) <= 8.0, "a partial washout: deep, but never a zero print"
    assert min(ks) > 2.0, "no zero print requirement anywhere (§4)"

    by_session: dict[str, list[float]] = {}
    for obs in path:
        if obs.k is not None:
            by_session.setdefault(obs.market_session, []).append(obs.k)
    sessions = sorted(by_session)
    assert len(sessions) == 3
    # round trip: 35 -> below 20 -> ~4 -> back through 14 -> above 24
    assert by_session[sessions[0]][0] >= 35.0
    assert min(by_session[sessions[0]]) < 20.0, "the arm happens on the first session"
    assert min(by_session[sessions[1]]) <= 5.0, "the trough"
    assert max(by_session[sessions[1]]) >= 24.0, "recovery through 14 and past 24"
    assert max(by_session[sessions[2]]) >= 40.0

    # one arm -> failed micro-turn -> later successful C2a
    trough = by_session[sessions[1]]
    low_index = trough.index(min(trough))
    assert any(trough[i] > trough[i - 1] for i in range(1, low_index)), \
        "a micro-turn that failed before the real low"
    assert len(c2_run.fires["c2a_kd_cross"]) >= 1
    assert c1_run.episode is not None


def test_c1_arms_once_and_the_arm_is_the_candidate(path, c1_run):
    episode = c1_run.episode
    assert len(c1_run.episodes) == 1, "one live episode per (ticker, detector_id)"
    assert episode.first_armed_at == episode.candidate_at
    assert len(c1_run.events) == 1, "one candidate per episode, not one every 5 minutes"
    assert len(episode.fires) > 10, "later oversold observations are PATH observations"
    armed = next(o for o in path if o.observed_at == episode.first_armed_at)
    assert armed.k < ic.OVERSOLD
    earlier = [o for o in path if o.observed_at < episode.first_armed_at]
    assert all(o.k is None or o.k >= ic.OVERSOLD for o in earlier), \
        "the arm is the FIRST K < 20"


def test_a_second_episode_cannot_open_while_the_first_is_nonterminal(path, c1_run):
    """§10: one live episode per (ticker, detector_id), and W3 owns no terminator."""
    assert len(c1_run.episodes) == 1
    assert not c1_run.episode.terminal
    again = ch.run_c1(list(path) + list(path))
    assert len(again.episodes) == 1, "replaying the path cannot mint a second episode"


@pytest.mark.parametrize("ks,elapsed,expected", [
    ([55.0, 61.0], 1, True),                 # two consecutive above 50
    ([55.0, 44.0, 61.0], 1, False),          # the run is broken
    ([55.0, None, 61.0], 1, False),          # a missing reading breaks it too
    ([10.0, 12.0], 15, True),                # 15 sessions elapsed, whichever first
    ([10.0, 12.0], 14, False),
    ([], 0, False),
])
def test_the_rearm_rule_is_section_10s_frozen_rule(ks, elapsed, expected):
    assert ch.rearm_eligible(ks, elapsed) is expected


def test_every_reading_is_display_tier_and_unavailable_is_never_false(c1_run, c2_run):
    for reading in list(c1_run.readings) + list(c2_run.readings):
        assert reading.authority == {k: False for k in reading.authority}
        if reading.availability == "unavailable":
            assert reading.condition_met is None
    assert any(r.condition_met is None for r in c2_run.readings), \
        "the null state must actually occur, or the law is untested here"


# ---------------------------------------------------------------------------
# PIT-1 / PIT-2 — the EOD-mutation test
# ---------------------------------------------------------------------------

def _mutate_after(fixture: dict, cutoff: datetime, *, factor: float = 1.5) -> dict:
    """Multiply every minute at/after ``cutoff`` and every later daily bar."""
    mutated = copy.deepcopy(fixture)
    for tape in mutated["tapes"]:
        for row in tape["rows"]:
            if datetime.fromisoformat(row[0]).replace(tzinfo=ET) >= cutoff:
                for i in (1, 2, 3, 4):
                    row[i] = round(row[i] * factor, 4)
    cutoff_session = cutoff.date().isoformat()
    for row in mutated["daily"]["rows"]:
        if row[0] >= cutoff_session:
            for i in (1, 2, 3, 4):
                row[i] = round(row[i] * factor, 4)
    return mutated


@pytest.fixture(scope="module")
def eod_cutoff(fixture) -> datetime:
    """Mid-session on the trough session — the bar the mutation must not reach."""
    session = date.fromisoformat(fixture["tape_sessions"][1])
    open_dt, _close = ch.session_window_et(session)
    return open_dt + timedelta(minutes=120)


def test_PIT1_a_c1_reading_at_T_survives_mutation_of_every_later_minute_and_the_EOD_bar(
        fixture, c1_run, eod_cutoff):
    cutoff_iso = ch.utc_iso(eod_cutoff)
    mutated = _mutate_after(fixture, eod_cutoff)
    mutated_run = ch.run_c1(observation_path(mutated))

    before = _readings_at_or_before(c1_run.readings, cutoff_iso)
    after = _readings_at_or_before(mutated_run.readings, cutoff_iso)
    assert len(before) == len(after) > 100
    assert canonical_readings(before) == canonical_readings(after)


def test_CONTROL_the_eod_mutation_is_real(fixture, c1_run, eod_cutoff):
    """A mutation nothing can see would make PIT-1 and PIT-2 vacuous."""
    cutoff_iso = ch.utc_iso(eod_cutoff)
    mutated_run = ch.run_c1(observation_path(_mutate_after(fixture, eod_cutoff)))
    later_before = [r for r in c1_run.readings if r.observed_at > cutoff_iso]
    later_after = [r for r in mutated_run.readings if r.observed_at > cutoff_iso]
    assert canonical_readings(later_before) != canonical_readings(later_after)


def test_PIT2_all_six_c2_variants_survive_the_same_mutation(fixture, c2_run, eod_cutoff):
    cutoff_iso = ch.utc_iso(eod_cutoff)
    mutated = _mutate_after(fixture, eod_cutoff)
    mutated_path = observation_path(mutated)
    mutated_c2 = ch.run_c2(mutated_path, ch.run_c1(mutated_path).episode)

    for variant in ch.C2_VARIANTS:
        before = _readings_at_or_before(
            [r for r in c2_run.readings if r.variant == variant], cutoff_iso)
        after = _readings_at_or_before(
            [r for r in mutated_c2.readings if r.variant == variant], cutoff_iso)
        assert before, variant
        assert canonical_readings(before) == canonical_readings(after), variant


# ---------------------------------------------------------------------------
# PIT-4 — the turn carries no current-K<20 requirement
# ---------------------------------------------------------------------------

def _c2a_requiring_current_oversold(state, obs):
    """THE MUTATION: a C2a that also demands the washout still be current.

    This is the natural-looking mistake — "a turn out of oversold" reading as
    "oversold AND turning".  A5.3 is explicit that the washout is the episode's
    HISTORY and the turn is the event.
    """
    verdict = ch._eval_c2a(state, obs)
    if verdict is None:
        return None
    return bool(verdict and obs.k is not None and obs.k < ic.OVERSOLD)


def test_PIT4_the_c2a_cross_fires_after_K_recovers_above_20(path, c1_run, c2_run):
    fires = c2_run.fires["c2a_kd_cross"]
    assert fires, "the fixture must produce a C2a cross"
    ks = _k_by_time(path)
    assert all(ks[t] >= ic.OVERSOLD for t in fires), \
        "this fixture's crosses all land above 20 — that is what makes the mutation bite"
    assert fires[0] > c1_run.episode.first_armed_at, "no variant fires before its arm"


def test_PIT4_MUTATION_requiring_current_K_below_20_at_the_turn_kills_the_cross(
        path, c1_run, c2_run):
    mutated = ch.run_c2(path, c1_run.episode,
                        evaluators={**ch.C2_EVALUATORS,
                                    "c2a_kd_cross": _c2a_requiring_current_oversold})
    assert c2_run.fires["c2a_kd_cross"], "baseline must fire"
    assert mutated.fires["c2a_kd_cross"] == (), \
        "the mutated predicate must lose the cross — otherwise PIT-4 proves nothing"
    assert mutated.variant_episode("c2a_kd_cross") is None


def test_a_variant_may_fire_while_K_is_still_below_20_too(path, c1_run, c2_run):
    """The law is 'no requirement', not 'a requirement in the other direction'."""
    ks = _k_by_time(path)
    below = [t for t in c2_run.fires["c2b_k_slope"] if ks[t] < ic.OVERSOLD]
    above = [t for t in c2_run.fires["c2b_k_slope"] if ks[t] >= ic.OVERSOLD]
    assert below and above, "C2 fires on both sides of 20 — the turn is the event"


def test_nothing_fires_before_the_c1_arm(path, c1_run, c2_run):
    armed = c1_run.episode.first_armed_at
    for variant, fires in c2_run.fires.items():
        assert all(t >= armed for t in fires), variant
    pre_arm = [r for r in c2_run.readings if r.observed_at < armed]
    assert pre_arm, "the fixture must contain pre-arm observations"
    assert all(r.availability == "unavailable" and r.condition_met is None
               for r in pre_arm), "pre-arm is UNAVAILABLE, never a measured False"


# ---------------------------------------------------------------------------
# PIT-5 — the C2c pivot is causal
# ---------------------------------------------------------------------------

def _causal_pivot_fires(ks: list[float]) -> list[int]:
    """The lawful rule: a low at j is confirmed at j+1 and fires THERE."""
    pivots: list[float] = []
    out: list[int] = []
    for i in range(2, len(ks)):
        prev2, prev, now = ks[i - 2], ks[i - 1], ks[i]
        if prev2 > prev and now >= prev:
            if pivots and prev > pivots[-1]:
                out.append(i)
            pivots.append(prev)
    return out


def _centered_pivot_fires(ks: list[float]) -> list[int]:
    """THE MUTATION: a centered window that reads j+1 while dated at j."""
    pivots: list[float] = []
    out: list[int] = []
    for i in range(1, len(ks) - 1):
        prev, now, nxt = ks[i - 1], ks[i], ks[i + 1]
        if prev > now and nxt >= now:
            if pivots and now > pivots[-1]:
                out.append(i)
            pivots.append(now)
    return out


def test_PIT5_the_engine_matches_the_causal_pivot_rule(path, c1_run, c2_run):
    armed = c1_run.episode.first_armed_at
    eligible = [o for o in path if o.k is not None and o.observed_at >= armed]
    ks = [o.k for o in eligible]
    expected = {eligible[i].observed_at for i in _causal_pivot_fires(ks)}
    assert set(c2_run.fires["c2c_higher_k_low"]) == expected
    assert expected, "the fixture must produce a higher pivot low"


def test_PIT5_MUTATION_a_centered_window_fires_one_observation_early(path, c1_run):
    armed = c1_run.episode.first_armed_at
    eligible = [o for o in path if o.k is not None and o.observed_at >= armed]
    ks = [o.k for o in eligible]
    causal = _causal_pivot_fires(ks)
    centered = _centered_pivot_fires(ks)
    assert causal and centered
    assert centered != causal, "the centered window must produce a different answer"
    assert min(centered) < min(causal), \
        "the centered window dates the fire at j — one observation before it is knowable"


def test_PIT5_the_pivot_is_invisible_until_the_confirming_observation(path, c1_run):
    """Truncate the path AT the pivot: nothing fires.  Extend by one: it fires."""
    armed = c1_run.episode.first_armed_at
    eligible = [o for o in path if o.k is not None and o.observed_at >= armed]
    fire_index = _causal_pivot_fires([o.k for o in eligible])[0]
    fire_at = eligible[fire_index].observed_at
    cut = [o for o in path if o.observed_at < fire_at]
    assert ch.run_c2(cut, c1_run.episode).fires["c2c_higher_k_low"] == ()
    upto = [o for o in path if o.observed_at <= fire_at]
    assert ch.run_c2(upto, c1_run.episode).fires["c2c_higher_k_low"] == (fire_at,)


# ---------------------------------------------------------------------------
# PIT-6 — C2f reads the SAMPLED low, never a raw minute low
# ---------------------------------------------------------------------------

def _c2f_on_raw_minute_low(state, obs):
    """THE MUTATION: the rebound measured off the raw one-minute low.

    Minute lows are <= sampled lows by construction, so this fires EARLIER and
    MORE OFTEN than the live lane could ever have observed — the exact optimism
    §7.1's frozen replay rule exists to forbid.
    """
    if (obs.sampled_close is None or obs.running_minute_low is None
            or obs.atr_prior_confirmed is None or obs.atr_basis is None):
        return None
    return bool(obs.sampled_close - obs.running_minute_low
                >= ch.C2F_ATR_MULTIPLE * obs.atr_prior_confirmed)


def test_PIT6_the_fixture_contains_a_minute_low_far_below_every_sampled_point(path):
    gaps = [(o.running_sampled_low - o.running_minute_low) for o in path
            if o.running_sampled_low is not None and o.running_minute_low is not None]
    atr = next(o.atr_prior_confirmed for o in path if o.atr_prior_confirmed)
    assert max(gaps) > ch.C2F_ATR_MULTIPLE * atr, \
        "the flash low must be material, or the mutation cannot change anything"


def test_PIT6_MUTATION_using_the_raw_minute_low_changes_the_c2f_result(
        path, c1_run, c2_run):
    mutated = ch.run_c2(path, c1_run.episode,
                        evaluators={**ch.C2_EVALUATORS,
                                    "c2f_rebound_atr": _c2f_on_raw_minute_low})
    lawful = c2_run.fires["c2f_rebound_atr"]
    optimistic = mutated.fires["c2f_rebound_atr"]
    assert lawful != optimistic
    assert len(optimistic) > len(lawful), "the minute-low form fires more often"
    assert min(optimistic) < min(lawful), "and earlier"

    flash_session = load_fixture()["tape_sessions"][0]
    sessions = {o.observed_at: o.market_session for o in path}
    assert [t for t in lawful if sessions[t] == flash_session] == [], \
        "the sampled path declines monotonically there, so the lawful rule cannot fire"
    assert [t for t in optimistic if sessions[t] == flash_session], \
        "the raw-minute-low rule fires off the flash — a rebound nobody could trade"


def test_c2f_measures_the_rebound_off_the_running_sampled_low(path, c2_run):
    by_time = {o.observed_at: o for o in path}
    for reading in c2_run.readings:
        if reading.variant != "c2f_rebound_atr" or reading.condition_met is not True:
            continue
        obs = by_time[reading.observed_at]
        assert reading.features["running_sampled_low"] == obs.running_sampled_low
        assert reading.features["atr_multiple"] == ch.C2F_ATR_MULTIPLE
        assert (obs.sampled_close - obs.running_sampled_low
                >= ch.C2F_ATR_MULTIPLE * obs.atr_prior_confirmed)


# ---------------------------------------------------------------------------
# PIT-18 — a missing ATR is UNAVAILABLE, never False
# ---------------------------------------------------------------------------

def test_PIT18_removing_the_ATR_input_makes_c2f_unavailable_not_false(fixture, c1_run):
    blind = observation_path(fixture, daily=daily_history(fixture, blank_ohlc=True))
    assert all(o.atr_prior_confirmed is None for o in blind)
    run = ch.run_c2(blind, ch.run_c1(blind).episode)
    c2f = [r for r in run.readings if r.variant == "c2f_rebound_atr"]
    assert c2f
    assert all(r.condition_met is None for r in c2f), \
        "a rebound we could not measure is not a measured non-rebound"
    assert all(r.availability == "unavailable" for r in c2f)
    assert run.fires["c2f_rebound_atr"] == ()
    # the OTHER variants are untouched: K and the histogram need no OHLC
    assert run.fires["c2a_kd_cross"], "only C2f depends on ATR"


def test_PIT18_a_basis_disagreement_makes_c2f_unavailable_too(fixture):
    mixed = observation_path(
        fixture, tapes=session_tapes(fixture, price_basis=ch.BASIS_RAW))
    assert all(o.atr_prior_confirmed is None for o in mixed)
    run = ch.run_c2(mixed, ch.run_c1(mixed).episode)
    assert run.fires["c2f_rebound_atr"] == ()
    assert all(r.condition_met is None
               for r in run.readings if r.variant == "c2f_rebound_atr")


# ---------------------------------------------------------------------------
# PIT-11 — extended hours cannot reach an RTH reading
# ---------------------------------------------------------------------------

def _extended_hours_rows(fixture) -> int:
    count = 0
    for tape in fixture["tapes"]:
        session = date.fromisoformat(tape["session"])
        open_dt, close_dt = ch.session_window_et(session)
        for row in tape["rows"]:
            start = datetime.fromisoformat(row[0]).replace(tzinfo=ET)
            if start < open_dt or start + timedelta(minutes=1) > close_dt:
                count += 1
    return count


def test_PIT11_the_fixture_actually_carries_extended_hours_prints(fixture):
    assert _extended_hours_rows(fixture) >= 100, \
        "a session filter tested against a fixture with no premarket proves nothing"


def test_PIT11_mutating_premarket_and_postmarket_moves_nothing(fixture, c1_run, c2_run):
    mutated = copy.deepcopy(fixture)
    for tape in mutated["tapes"]:
        session = date.fromisoformat(tape["session"])
        open_dt, close_dt = ch.session_window_et(session)
        for row in tape["rows"]:
            start = datetime.fromisoformat(row[0]).replace(tzinfo=ET)
            if start < open_dt or start + timedelta(minutes=1) > close_dt:
                for i in (1, 2, 3, 4):
                    row[i] = round(row[i] * 3.0, 4)
    mutated_path = observation_path(mutated)
    assert canonical_readings(ch.run_c1(mutated_path).readings) == \
        canonical_readings(c1_run.readings)
    mutated_c2 = ch.run_c2(mutated_path, ch.run_c1(mutated_path).episode)
    assert canonical_readings(mutated_c2.readings) == canonical_readings(c2_run.readings)


def test_PIT11_deleting_extended_hours_entirely_moves_nothing(fixture, c1_run):
    stripped = copy.deepcopy(fixture)
    for tape in stripped["tapes"]:
        session = date.fromisoformat(tape["session"])
        open_dt, close_dt = ch.session_window_et(session)
        tape["rows"] = [
            r for r in tape["rows"]
            if open_dt <= datetime.fromisoformat(r[0]).replace(tzinfo=ET)
            and datetime.fromisoformat(r[0]).replace(tzinfo=ET)
            + timedelta(minutes=1) <= close_dt]
    assert canonical_readings(ch.run_c1(observation_path(stripped)).readings) == \
        canonical_readings(c1_run.readings)


# ---------------------------------------------------------------------------
# PIT-17 — the future cannot reach behind the edge
# ---------------------------------------------------------------------------

def test_PIT17_appending_future_sessions_leaves_every_earlier_reading_identical(
        fixture, c1_run, c2_run):
    extended = copy.deepcopy(fixture)
    last_session = date.fromisoformat(extended["daily"]["rows"][-1][0])
    last_close = float(extended["daily"]["rows"][-1][4])
    for step in range(1, 6):
        nxt = last_session + timedelta(days=step)
        price = round(last_close * (1.0 + 0.03 * step), 4)
        extended["daily"]["rows"].append(
            [nxt.isoformat(), price, round(price * 1.02, 4), round(price * 0.98, 4),
             price])

    edge = c1_run.readings[-1].observed_at
    extended_path = observation_path(extended)
    extended_c1 = ch.run_c1(extended_path)
    extended_c2 = ch.run_c2(extended_path, extended_c1.episode)

    assert canonical_readings(_readings_at_or_before(extended_c1.readings, edge)) == \
        canonical_readings(c1_run.readings)
    assert canonical_readings(_readings_at_or_before(extended_c2.readings, edge)) == \
        canonical_readings(c2_run.readings)


def test_PIT17_a_later_session_tape_cannot_move_an_earlier_session(fixture):
    one = observation_path(fixture, tapes=session_tapes(fixture)[:1])
    two = observation_path(fixture, tapes=session_tapes(fixture)[:2])
    first_session = fixture["tape_sessions"][0]
    a = ch.run_c1([o for o in one if o.market_session == first_session])
    b = ch.run_c1([o for o in two if o.market_session == first_session])
    assert canonical_readings(a.readings) == canonical_readings(b.readings)


# ---------------------------------------------------------------------------
# the A5.1 reconstruction itself
# ---------------------------------------------------------------------------

def test_the_sampled_path_is_five_minute_anchored_at_the_session_open(fixture):
    tape = session_tapes(fixture)[0]
    points = ch.sample_session_path(tape)
    open_dt, close_dt = ch.session_window_et(tape.session)
    assert points[0].interval_start == open_dt
    assert points[-1].observed_at == close_dt
    assert all((p.observed_at - p.interval_start) <= timedelta(minutes=5)
               for p in points)
    assert len(points) == 78, "09:30-16:00 is 78 five-minute intervals"


def test_a_minute_bar_is_knowable_only_at_its_close(fixture):
    tape = session_tapes(fixture)[0]
    open_dt, _close = ch.session_window_et(tape.session)
    first = min((m for m in tape.minutes if m.start >= open_dt), key=lambda m: m.start)
    assert first.knowable_at == first.start + timedelta(seconds=60)
    points = ch.sample_session_path(tape)
    lawful = [m for m in ch.rth_minutes(tape)
              if m.knowable_at <= points[0].observed_at]
    assert points[0].sampled_close == lawful[-1].close


def test_the_provisional_close_is_appended_never_replacing_a_confirmed_one(fixture):
    """§7.1's append-not-replace law, checked on the series the detector reads."""
    daily = daily_history(fixture)
    session = date.fromisoformat(fixture["tape_sessions"][1])
    confirmed = daily.confirmed_through(session)
    assert confirmed.index.max() < pd.Timestamp(session)
    full = daily.frame
    assert pd.Timestamp(session) in full.index, \
        "the fixture DOES carry the session's eventual close — the cut is the law"
    tail = observation_path(fixture)
    obs = next(o for o in tail if o.market_session == session.isoformat())
    assert obs.confirmed_bars == len(confirmed)


def test_a_session_with_no_prints_yet_is_unavailable_not_zero(fixture):
    empty = copy.deepcopy(fixture)
    empty["tapes"] = [empty["tapes"][0]]
    empty["tapes"][0]["rows"] = []
    blank = observation_path(empty)
    assert blank, "the grid still exists — the session did open"
    assert all(o.availability == "unavailable" and o.k is None for o in blank)
    run = ch.run_c1(blank)
    assert run.episodes == ()
    assert all(r.condition_met is None for r in run.readings)
