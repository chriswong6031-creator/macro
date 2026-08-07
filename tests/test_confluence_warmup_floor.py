"""The US indicator floor is the MEASURED warmup requirement, not a round number.

Operator order 2026-08-05 ("200 bar indicator floor, lets lift this?"). These tests pin
the four properties the change rests on:

  1. Every leg's warmup in ``LEG_WARMUP_BARS`` is what the leg ACTUALLY needs — remeasured
     here from confluence_tiers' own helpers, so a leg whose warmup moves fails loudly
     instead of silently drifting the floor it derives.
  2. ``MIN_HISTORY`` is the max over the GATING legs — arithmetic, not a chosen number.
  3. A leg short of its warmup is NULL with a disclosed reason, never False (the PLTR
     narration-gap precedent), and a null does NOT read as False to its consumers.
  4. ``young_history`` is stamped on every name below the pre-change 200-bar floor and
     survives the trip to the board row (era law: the population change is labelled).

MEASUREMENT BASIS (re-measured under the absolute session anchor, R7, era
abs-session-2026-08-06). Buckets are phased to a fixed reference calendar, so a trailing
N-bar window yields ``ceil(N/n)`` TF bars when it starts on a bucket boundary and one MORE
when it straddles — a floor read off ONE alignment is a floor that holds only at that
alignment. So the basis is REAL NYSE sessions (``lib.nyse_calendar``, real holidays, real
phases), the window END slid across ``N_PHASE_OFFSETS`` consecutive sessions, and the floor
is the MAX over offsets of the minimal sufficient N.

Two legs are pinned differently and on purpose. ``wbull``/``htf_2w`` are CALENDAR-week legs:
their warmup is set by how many weeks a window spans, which moves with HOLIDAY DENSITY rather
than bucket phase, so on real sessions they measure BELOW the shipped floor
(``REAL_SESSION_WORST_CASE``). The shipped floor is the no-holiday worst case and is kept —
over-disclosing a leg as not-yet-knowable costs nothing, under-disclosing asserts a leg is
live when it is not (the PLTR error class), and neither leg gates a tier. Both numbers are
pinned here so the gap stays measured rather than assumed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from datetime import date

from engine import confluence_tiers as ct
from engine import signal_gate
from engine.confluence_tiers import (
    CONF_W,
    GATING_LEGS,
    LEG_WARMUP_BARS,
    MA200_WARMUP_BARS,
    MIN_HISTORY,
    RSI_LEN,
    YOUNG_HISTORY_BARS,
    _completed_resample,
    _null_legs,
    _rsi_macd,
    _stoch_rsi_kd,
    _tf_bars,
    _xup,
    cascade,
    tier_stream,
)
from engine.technicals import rsi
from lib import nyse_calendar

#: Real NYSE sessions — the phases and holidays a production window actually sees.
_SESSIONS = pd.DatetimeIndex(pd.to_datetime(
    nyse_calendar.sessions_between(date(2015, 1, 1), date(2026, 8, 4))))
#: How many consecutive window-END sessions to slide across. 14 covers every 2D/3D phase
#: (2 and 3), every weekday phase (5) and both fortnight parities (10).
N_PHASE_OFFSETS = 14
#: N must hold for N..N+_STABILITY_BAND, so a single lucky alignment cannot set a floor.
_STABILITY_BAND = 12

#: The CALENDAR-week legs, whose real-session floor sits BELOW the shipped (no-holiday) one.
CALENDAR_WEEK_LEGS = ("wbull", "htf_2w")
#: What those two measure on real sessions across the 14 phase offsets. Pinned so a drift in
#: either direction is loud: the shipped floor stays conservative BY A KNOWN MARGIN.
REAL_SESSION_WORST_CASE = {"wbull": 376, "htf_2w": 759}


def _synth(n: int, seed: int = 7, end_offset: int = 0) -> pd.Series:
    """``n`` REAL NYSE sessions ending ``end_offset`` sessions before 2026-08-04.

    ``end_offset`` is the phase knob: sliding the window end by one session shifts which
    absolute bucket the final bar lands in, which is exactly what a floor must survive.
    """
    end = len(_SESSIONS) - 1 - end_offset
    idx = _SESSIONS[end - n + 1: end + 1]
    rng = np.random.default_rng(seed)
    return pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0, 0.02, len(idx)))), index=idx)


# --------------------------------------------------------------------------- #
# 1. the per-leg warmup table is REMEASURED, not trusted
# --------------------------------------------------------------------------- #

def _leg_defined(c: pd.Series, leg: str) -> bool:
    """Is ``leg`` computable at the final bar of ``c``? Uses confluence_tiers' own helpers,
    so this is a remeasurement of production math, not a second implementation of it."""
    sm, _smk = _tf_bars(c, 2)
    ss3, _sk3 = _tf_bars(c, 3)

    if leg == "rsi_ok":
        return bool(rsi(ss3, RSI_LEN).notna().sum() >= 1)
    if leg in ("k2_d2", "recent2", "fromos2"):
        k2, d2 = _stoch_rsi_kd(sm)
        if leg == "k2_d2":
            return bool(k2.notna().sum() >= 1 and d2.notna().sum() >= 1)
        if leg == "recent2":                    # _xup needs the pair on TWO consecutive bars
            return bool(k2.notna().sum() >= 2 and d2.notna().sum() >= 2)
        return bool(d2.rolling(CONF_W).min().notna().sum() >= 1)
    if leg in ("k3_d3", "recent3", "fromos3"):
        k3, d3 = _stoch_rsi_kd(ss3)
        if leg == "k3_d3":
            return bool(k3.notna().sum() >= 1 and d3.notna().sum() >= 1)
        if leg == "recent3":
            return bool(k3.notna().sum() >= 2 and d3.notna().sum() >= 2)
        return bool(d3.rolling(CONF_W).min().notna().sum() >= 1)
    if leg in ("m2_s2", "mb2", "imm2", "imm2_persist2"):
        m2, s2 = _rsi_macd(sm)
        h2 = m2 - s2
        slope2 = h2 - h2.shift(1)
        if leg == "m2_s2":
            return bool(m2.notna().sum() >= 1 and s2.notna().sum() >= 1)
        if leg == "mb2":
            return bool(m2.notna().sum() >= 2 and s2.notna().sum() >= 2)
        if leg == "imm2":                       # needs the histogram slope -> 2 bars of h2
            return bool(slope2.notna().sum() >= 1)
        return bool(slope2.notna().sum() >= 2)  # persistence: imm2 True on 2 consecutive bars
    if leg in ("m3_s3", "mb3"):
        m3, s3 = _rsi_macd(ss3)
        need = 1 if leg == "m3_s3" else 2
        return bool(m3.notna().sum() >= need and s3.notna().sum() >= need)
    if leg == "above200":
        return bool(pd.notna(c.rolling(200).mean().iloc[-1]))
    if leg == "wbull":
        wm, ws = _rsi_macd(c.resample("W-FRI").last().dropna())
        return bool(wm.notna().sum() >= 2 and ws.notna().sum() >= 2)
    if leg == "htf_2w":
        # the PRODUCTION path: the S1/S2 badges read completed 2W buckets, and since the
        # absolute-fortnight repair (R6) that is no longer what raw resample("2W-FRI") gives.
        raw, _kn = _completed_resample(c, "2W-FRI")
        wm, ws = _rsi_macd(raw)
        return bool(wm.notna().sum() >= 2 and ws.notna().sum() >= 2)
    raise AssertionError(f"unmeasured leg in LEG_WARMUP_BARS: {leg}")


def _minimal_n(leg: str, end_offset: int, lo: int, hi: int) -> int | None:
    """Smallest N at which ``leg`` is computable for every N' in ``N..N+_STABILITY_BAND``,
    with the window ending ``end_offset`` sessions back. None if unresolved in ``[lo, hi)``."""
    for n in range(lo, hi):
        if all(_leg_defined(_synth(m, end_offset=end_offset), leg)
               for m in range(n, n + _STABILITY_BAND + 1)):
            return n
    return None


def _phase_worst_case(leg: str) -> int:
    """The MAX over reference phases of the minimal sufficient N — the floor's definition
    under the absolute anchor (R7). A floor measured at one alignment is not a floor."""
    need = LEG_WARMUP_BARS[leg]
    lo, hi = max(2, need - 60), need + 60
    per_offset = [_minimal_n(leg, o, lo, hi) for o in range(N_PHASE_OFFSETS)]
    assert all(n is not None for n in per_offset), (
        f"{leg}: warmup unresolved in [{lo},{hi}) at some phase — {per_offset}")
    return max(per_offset)


@pytest.mark.parametrize("leg", sorted(LEG_WARMUP_BARS))
def test_leg_warmup_is_the_phase_worst_case_measurement(leg):
    """The tabled floor IS the max-over-phases minimal N — both halves, in one measurement.

    ``worst == need`` pins the table from both sides at once: too LOW and some phase would
    need more than the table admits (the floor lets a null through as a live leg); too HIGH
    and no phase would need that many (the floor locks out names whose legs are already live).
    The old one-alignment form could assert neither under a phased anchor.

    ``CALENDAR_WEEK_LEGS`` are the deliberate exception — see the module docstring: their
    shipped floor is the conservative no-holiday case, and what real sessions measure is
    pinned separately so the margin cannot drift unnoticed.
    """
    worst = _phase_worst_case(leg)
    if leg in CALENDAR_WEEK_LEGS:
        assert worst == REAL_SESSION_WORST_CASE[leg], (
            f"{leg}: real-session phase-worst-case moved to {worst} (pinned "
            f"{REAL_SESSION_WORST_CASE[leg]}) — re-measure before editing the table")
        assert worst < LEG_WARMUP_BARS[leg], (
            f"{leg}: the shipped floor {LEG_WARMUP_BARS[leg]} is no longer conservative "
            f"against the real-session measurement {worst} — it now UNDER-discloses")
        return
    assert worst == LEG_WARMUP_BARS[leg], (
        f"{leg}: LEG_WARMUP_BARS says {LEG_WARMUP_BARS[leg]} daily bars, but the phase-worst-"
        f"case measurement is {worst}. Lower means the table locks out names whose legs are "
        f"already live; higher means the floor admits names whose leg is still NaN.")


def test_the_anchor_did_not_move_any_session_counted_floor():
    """The era's headline claim, asserted rather than remembered: bucketing by absolute
    session position changed NO session-counted leg's warmup, so MIN_HISTORY (and with it the
    graded cohort boundary) is exactly where the 2026-08-05 floor-lift left it.

    The reason is arithmetic: a window starting on a bucket boundary yields ceil(N/n) TF bars
    under either anchor, and a real session maps to a CONSECUTIVE reference position because
    holidays are absent from both the series and the reference. If this ever reds, the era
    stamp needs a new value — a moved floor is a moved graded population.
    """
    assert MIN_HISTORY == 159
    assert LEG_WARMUP_BARS["m3_s3"] == 232      # F6's boundary rides on this one


def test_min_history_is_derived_from_the_gating_legs_not_chosen():
    assert MIN_HISTORY == max(LEG_WARMUP_BARS[k] for k in GATING_LEGS)
    assert MIN_HISTORY == 159, "the measured floor moved — re-run the census before editing"
    # the round number it replaced must no longer be the floor
    assert MIN_HISTORY < 200
    # T4's 200dMA leg is NOT a gating leg: T4 self-gates on it instead
    assert "above200" not in GATING_LEGS
    assert MA200_WARMUP_BARS == 200


def test_gating_legs_are_the_ones_a_reachable_tier_actually_needs():
    """Every gating leg must be cheaper than the old floor — a leg above 200 bars cannot
    be what gates a tier reachable below 200, and listing one there would re-raise the
    floor through the max()."""
    for leg in GATING_LEGS:
        assert LEG_WARMUP_BARS[leg] < 200, f"{leg} is not reachable below the old floor"


# --------------------------------------------------------------------------- #
# 2. mutation check — putting the floor back must red the newly-eligible property
# --------------------------------------------------------------------------- #

def test_names_between_the_measured_floor_and_200_can_be_graded():
    """The whole point of the change: at 159-199 bars the cascade returns a real verdict
    (a computed tier or a computed blank), not the thin-history refusal.

    MUTATION: raising MIN_HISTORY back to 200 makes these names return the thin-history
    blank — `bars` is still stamped but every leg the cascade would have read is listed in
    null_legs. That difference is what this test would lose.
    """
    c = _synth(180)
    live = cascade(c)
    assert live["bars"] == 180
    assert live["young_history"] is True
    # `asof` is the discriminator between a COMPUTED blank and the thin-history REFUSAL:
    # only the path that actually ran the cascade math stamps the last bar's date.
    assert live["asof"] is not None, "180 bars must be graded, not refused"
    # a graded name reads its legs: the T2/T3 gating legs are NOT in the null disclosure
    for leg in GATING_LEGS:
        assert leg not in (live["null_legs"] or {}), (
            f"{leg} disclosed as null at 180 bars, but the floor admits the name — "
            f"the floor and the table disagree")
    # and the stream (the vectorized twin) grades the same series
    assert not tier_stream(c).empty

    monkey_floor = 200
    original = ct.MIN_HISTORY
    try:
        ct.MIN_HISTORY = monkey_floor
        refused = cascade(c)
        assert refused["tier"] is None and refused["eligible"] is False
        # the refusal is structural, not a market read — every gating leg is disclosed
        assert tier_stream(c).empty
    finally:
        ct.MIN_HISTORY = original
    assert cascade(c)["bars"] == 180        # restored


# --------------------------------------------------------------------------- #
# 3. null-not-false: an unreachable leg is NULL with a reason
# --------------------------------------------------------------------------- #

def test_above200_is_null_not_false_below_its_warmup():
    """The PLTR precedent. Below 200 bars the 200dMA does not exist, so `above200` must be
    None — a False there is the claim "trading below its 200-day average", which the data
    cannot support."""
    young = cascade(_synth(MA200_WARMUP_BARS - 20))
    assert young["above200"] is None, "unknowable 200dMA must be null, never False"
    assert young["above200"] is not False
    assert "above200" in young["null_legs"]
    assert "200" in young["null_legs"]["above200"]          # the reason names the requirement

    grown = cascade(_synth(320))
    assert grown["above200"] in (True, False), "a computable 200dMA must be a real boolean"
    assert "above200" not in grown["null_legs"]


def test_null_legs_names_every_unreachable_leg_with_a_plain_reason():
    nulls = _null_legs(120)
    assert nulls, "a 120-bar series has unreachable legs; the disclosure must not be empty"
    for leg, reason in nulls.items():
        assert LEG_WARMUP_BARS[leg] > 120
        assert "120" in reason and "needs" in reason
    # legs already live at 120 bars are NOT claimed to be null
    for leg in ("rsi_ok", "k3_d3", "recent3", "fromos3"):
        assert leg not in nulls
    assert _null_legs(10_000) == {}, "a long history discloses nothing"


def test_thin_history_refusal_still_discloses_rather_than_asserting():
    """Below the floor the cascade refuses — but it must say WHY, and must not stamp a
    False on any leg it never computed."""
    v = cascade(_synth(40))
    assert v["tier"] is None and v["eligible"] is False
    assert v["bars"] == 40 and v["young_history"] is True
    assert v["above200"] is None                       # not False
    assert set(v["null_legs"]) >= set(GATING_LEGS)     # every gating leg disclosed


def test_blank_returns_do_not_share_one_mutable_null_legs_dict():
    """``_BLANK`` is shallow-copied on every blank return. A shared mutable disclosure
    would let one name's nulls leak into another's."""
    a, b = cascade(_synth(40)), cascade(_synth(60))
    assert a["null_legs"] is not b["null_legs"]
    a["null_legs"]["injected"] = "x"
    assert "injected" not in cascade(_synth(40))["null_legs"]


# --------------------------------------------------------------------------- #
# 4. downstream consumer: a null must not read as False
# --------------------------------------------------------------------------- #

def test_null_above200_is_not_reported_as_below_the_average():
    """The consumer-facing half. Every lane tests ``above200 is True``, so a null already
    fails to claim an intact trend (correct). What must NOT happen is the opposite error:
    a name whose 200dMA IS computable being left null and silently dropped."""
    v = signal_gate.gate("TEST", _synth(240))
    # signal_quality needs ~270 daily bars, so its own above200 is absent here; the cascade
    # can measure it at 240, and the gate fills it rather than leaving an unknowable-looking
    # null on a knowable value.
    assert v["above200"] in (True, False), (
        "a 240-bar name has a computable 200dMA — leaving it None makes every "
        "`above200 is True` lane drop it for a reason that is not true")
    assert v["above200"] is not None


def test_genuinely_unknowable_above200_stays_null_through_the_gate():
    """The other direction: the gate must not manufacture a False to fill the hole."""
    v = signal_gate.gate("TEST", _synth(170))
    assert v["above200"] is None, "below 200 bars the 200dMA is unknowable — stay null"
    assert v["above200"] is not False


# --------------------------------------------------------------------------- #
# 5. young_history is stamped and travels
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("n,expected", [(170, True), (199, True), (200, False), (400, False)])
def test_young_history_boundary_is_the_pre_change_floor(n, expected):
    assert YOUNG_HISTORY_BARS == 200
    assert cascade(_synth(n))["young_history"] is expected


def test_young_history_reaches_the_verdict_and_the_slim_buy_signal():
    young = signal_gate.gate("TEST", _synth(175))
    assert young["young_history"] is True
    assert young["history_bars"] == 175
    assert signal_gate.buy_signal(young)["young_history"] is True
    assert "young_history" in signal_gate.compact(young)

    grown = signal_gate.gate("TEST", _synth(500))
    assert grown["young_history"] is False
    assert signal_gate.buy_signal(grown)["young_history"] is False


def test_young_history_reaches_the_candidates_store():
    """The permanent graded record. Era law rests on THIS: without the column the store
    cannot separate the pre- and post-2026-08-05 populations after the fact."""
    from engine import us_context_vector

    rows = us_context_vector.build_records(
        stamp_date="2026-08-05", board_definition="test",
        is_buyable=signal_gate.is_buyable,
        verdicts={
            "YOUNG": {"eligible": True, "tier_cascade": "T2",
                      "young_history": True, "history_bars": 175},
            "GROWN": {"eligible": True, "tier_cascade": "T2",
                      "young_history": False, "history_bars": 900},
            "UNSTAMPED": {"eligible": False},
        })
    by = {r["ticker"]: r for r in rows}
    assert by["YOUNG"]["young_history"] is True
    assert by["YOUNG"]["history_bars"] == 175
    assert by["GROWN"]["young_history"] is False
    # an unstamped verdict must read NULL, not a fabricated False — "we did not label this
    # row" and "this row is not young" are different facts and the ledger must not conflate
    # them when the two cohorts are split later.
    assert by["UNSTAMPED"]["young_history"] is None


def test_young_history_is_carried_on_ineligible_verdicts_too():
    """The label is a population fact, not a badge for winners — a name that grades to no
    tier still belongs to its cohort, or the ledger cannot separate the eras."""
    v = cascade(_synth(165))
    assert v["eligible"] is False
    assert v["young_history"] is True and v["bars"] == 165
