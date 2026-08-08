"""Tests for engine/us_turn_watch.py — the TURN WATCH desk data plane (§6.9 R8).

Covers:
  (1)  The dot signature (a) fires on a washed-and-turning fixture and is silent on a
       steady uptrend; each of its three legs is individually necessary.
  (2)  Pre-confluence (b) is a CONJUNCTION: it never fires once the 3D has crossed, and
       the 3D bars-to-cross projection is published only in the regime where it means
       something (histogram below zero AND rising).
  (3)  The leader-pullback reset (d) needs a benchmark; without one it is UNEVALUATED on
       the row (`evaluated: False`), never a False verdict.
  (4)  Admission is the trigger UNION inside TRIGGER_LOOKBACK_SESSIONS, and a trigger that
       fired outside the window does not admit.
  (5)  Group-turn (c) flags every member of a TURNING/CONFIRMED basket and NOTHING else,
       and it never contributes to the recency term (a state is not a dated event).
  (6)  The context score is display-only: unknowable terms contribute zero and are NAMED,
       and the published formula string matches what the function actually does.
  (7)  The cap never deletes a lane (LANE_FLOOR), and beyond-cap names are disclosed.
  (8)  The session stamp is MAJORITY-based, not max() — one 24/7 tape reaching a later
       date cannot make the deck read fresh (the G0.2 fail-open shape).
  (9)  Nulls are printed, never asserted: an unknowable 200dMA is None, never False/0.
  (10) The why-not cell names blocking legs, and an ADMITTED name reports none.
  (11) Display-tier disclosure: authority text, the windows-not-certainties voice, zh
       siblings on every user-facing string, no "validated", no falsifier vocabulary.
  (12) Constants are pinned to their frozen v1 literals.
  (13) The universe excludes index/FX/crypto store files and enforces the bar floor.
  (14) Every ::warning this module emits starts at column 0 (GitHub drops the rest).

Frozen-fixture law: every behavioural assertion runs on a synthetic series built in-test.
Nothing here reads the live price store — a replay over live data asserts about TODAY and
rots the day the tape moves (the live deck + the 120-session replay are receipt evidence,
not test assertions).
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine import us_turn_watch as TW


# ---------------------------------------------------------------------------
# Fixture builders (frozen — no live store, no clock)
# ---------------------------------------------------------------------------

_FIXTURE_END = "2026-08-06"


def _series(vals: list[float], end: str = _FIXTURE_END) -> pd.Series:
    idx = pd.date_range(end=end, periods=len(vals), freq="B")
    return pd.Series(vals, index=idx, dtype=float)


def _flat(v: float, n: int) -> list[float]:
    return [v] * n


def _ramp(a: float, b: float, n: int) -> list[float]:
    return list(np.linspace(a, b, n))


def _wobble(vals: list[float], amp: float = 0.004) -> list[float]:
    """A deterministic ripple so rolling min/max windows are not degenerate."""
    return [v * (1.0 + amp * ((-1) ** i)) for i, v in enumerate(vals)]


#: A washout that grinds down for a year, bases, takes a TERMINAL FLUSH, then lifts — the
#: shape the deck exists for, and the one §6.8(a) is about ("the break WAS the capitulation").
#: The flush is load-bearing: it is what drives %D below OS so the washed leg can be satisfied
#: when %K turns back up.  A fixture that merely drifts sideways into a lift never washes.
_WASHOUT = _wobble(_flat(100.0, 120) + _ramp(100.0, 68.0, 200) + _flat(68.0, 30)
                   + _ramp(68.0, 55.0, 12) + _ramp(55.0, 70.0, 25))
#: A steady leader that never washes out.
_UPTREND = _wobble([100.0 * (1.0 + 0.0016) ** i for i in range(460)])
#: A leader that runs, takes a shallow controlled retrace, and resumes.
_LEADER_PULLBACK = _wobble(
    [100.0 * (1.0 + 0.0018) ** i for i in range(400)]
    + _ramp(205.0, 178.0, 22) + _ramp(178.0, 192.0, 14)
)


def _bench(n: int, end: str = _FIXTURE_END) -> pd.Series:
    """A flat-ish benchmark: any name that rises at all out-performs it."""
    return _series(_wobble([100.0 * (1.0 + 0.0002) ** i for i in range(n)]), end)


# ---------------------------------------------------------------------------
# (1) The dot signature
# ---------------------------------------------------------------------------

def test_dot_signature_fires_on_a_washed_and_turning_tape():
    s = _series(_WASHOUT)
    fired = TW.dot_signature(s)
    assert fired.any(), "dot signature never fired on the canonical washout fixture"
    # It must fire in the RECOVERY leg, not during the grind down.
    last_fire = int(np.where(fired.to_numpy())[0][-1])
    assert last_fire >= len(s) - 60, (
        f"last dot at bar {last_fire} of {len(s)} — not in the recovery leg")


def test_dot_signature_is_silent_on_a_steady_uptrend():
    # An uptrend never puts %D below OS, so the washed leg can never be satisfied.
    assert not TW.dot_signature(_series(_UPTREND)).any()


def test_dot_signature_legs_are_each_necessary():
    """Each leg alone admits strictly MORE bars than the conjunction — so each is binding."""
    from engine.confluence_tiers import _rsi_macd, _stoch_rsi_kd, _xup

    s = _series(_WASHOUT)
    k, d = _stoch_rsi_kd(s)
    cross = _xup(k, d).fillna(False)
    washed = (d.rolling(TW.DOT_WASHED_WINDOW).min() < TW.OS).fillna(False)
    m, sig = _rsi_macd(s)
    h = m - sig
    rising = ((h - h.shift(1)) > 0).fillna(False)

    conj = int(TW.dot_signature(s).sum())
    assert conj >= 1
    for name, leg in (("cross", cross), ("washed", washed), ("rising", rising)):
        assert int(leg.sum()) > conj, (
            f"leg {name} admits {int(leg.sum())} bars vs conjunction {conj} — not binding")


# ---------------------------------------------------------------------------
# (2) Pre-confluence: 2D crossed, 3D not
# ---------------------------------------------------------------------------

def test_pre_confluence_never_fires_once_the_3d_has_crossed():
    from engine.confluence_tiers import _rsi_macd, _tf_bars, _to_daily

    s = _series(_WASHOUT)
    fired, btc3 = TW.pre_confluence_2d(s)
    ss3, sk3 = _tf_bars(s, 3, "US")
    m3, s3 = _rsi_macd(ss3)
    h3_d = _to_daily(m3 - s3, sk3, s.index)
    crossed = (h3_d >= 0).fillna(False).to_numpy()
    assert not bool((fired.to_numpy() & crossed).any()), (
        "pre_confluence fired on a bar where the 3D histogram was already >= 0")


def test_pre_confluence_btc3_only_exists_in_the_projectable_regime():
    """`bars_to_cross` is a projection TO an up-cross: it is meaningless unless the
    histogram is below zero and rising, so it must be NaN everywhere else."""
    from engine.confluence_tiers import _rsi_macd, _tf_bars, _to_daily

    s = _series(_WASHOUT)
    _fired, btc3 = TW.pre_confluence_2d(s)
    ss3, sk3 = _tf_bars(s, 3, "US")
    m3, s3 = _rsi_macd(ss3)
    h3 = m3 - s3
    slope3 = h3 - h3.shift(1)
    ok_d = _to_daily(((h3 < 0) & (slope3 > 0)).astype(float), sk3, s.index).fillna(0) > 0
    have = btc3.notna().to_numpy()
    assert not bool((have & ~ok_d.to_numpy()).any()), (
        "btc3 published outside the below-zero-and-rising regime")
    assert bool((btc3.dropna() > 0).all()), "a bars-to-cross projection must be positive"


# ---------------------------------------------------------------------------
# (3) Leader-pullback reset needs a benchmark
# ---------------------------------------------------------------------------

def test_leader_reset_fires_on_a_controlled_retrace_and_resumption():
    s = _series(_LEADER_PULLBACK)
    fired = TW.leader_reset_turn(s, _bench(len(s)))
    assert fired.any(), "leader reset never fired on the controlled-pullback fixture"
    last = int(np.where(fired.to_numpy())[0][-1])
    assert last >= len(s) - 40, "leader reset did not fire in the resumption leg"


def test_leader_reset_does_not_fire_on_a_washout():
    """A -42% grind is not a controlled retrace — it is lane (a)/(c)'s business."""
    s = _series(_WASHOUT)
    assert not TW.leader_reset_turn(s, _bench(len(s))).any()


def test_missing_benchmark_makes_the_leader_trigger_unevaluated_not_false():
    s = _series(_LEADER_PULLBACK)
    row = TW.evaluate("TEST", s, benchmark=None)
    t = row["triggers"]["leader_reset_turn"]
    assert t["evaluated"] is False, "an unevaluated trigger must say so"
    assert t["fired"] is False
    # And every benchmark-derived column is a printed null, never a zero.
    assert row["rel_20d_pp"] is None
    assert any("benchmark unavailable" in n for n in row["null_notes"]), row["null_notes"]


# ---------------------------------------------------------------------------
# (4) Admission is the union, inside the lookback
# ---------------------------------------------------------------------------

def test_admission_is_the_union_within_the_lookback():
    s = _series(_WASHOUT)
    row = TW.evaluate("TEST", s, benchmark=_bench(len(s)))
    for tid in TW.TRIGGER_IDS:
        t = row["triggers"][tid]
        if t["days_since"] is not None and t["evaluated"]:
            assert t["fired"] is (t["days_since"] < TW.TRIGGER_LOOKBACK_SESSIONS), (
                f"{tid}: fired={t['fired']} but days_since={t['days_since']} "
                f"against lookback {TW.TRIGGER_LOOKBACK_SESSIONS}")
    assert row["triggers_fired"] == [t for t in TW.TRIGGER_IDS
                                     if row["triggers"][t]["fired"]]


def test_a_stale_trigger_does_not_admit():
    """Truncating the fixture so its last dot sits well outside the window closes it."""
    s = _series(_WASHOUT)
    fired = TW.dot_signature(s)
    idx = np.where(fired.to_numpy())[0]
    assert len(idx), "fixture precondition: the dot must fire at least once"
    cut = int(idx[-1]) + TW.TRIGGER_LOOKBACK_SESSIONS + 3
    if cut >= len(s):
        pytest.skip("fixture's last dot is too close to its end to build a stale case")
    row = TW.evaluate("TEST", s.iloc[:cut], benchmark=_bench(cut))
    t = row["triggers"]["dot_1d"]
    assert t["days_since"] >= TW.TRIGGER_LOOKBACK_SESSIONS
    assert t["fired"] is False, "a trigger outside the lookback must not admit"


# ---------------------------------------------------------------------------
# (5) Group turn flags members — and only members
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("state,expect", [("TURNING", True), ("CONFIRMED", True),
                                          ("BASING", False), ("NONE", False),
                                          ("FALLING", False), (None, False)])
def test_group_turn_flags_only_turning_or_confirmed(state, expect):
    s = _series(_UPTREND)
    row = TW.evaluate("TEST", s, benchmark=_bench(len(s)),
                      basket_ctx={"turn_state": state, "fired_date": "2026-08-06"})
    assert row["triggers"]["basket_turn"]["fired"] is expect


def test_group_turn_is_excluded_from_the_recency_term():
    """A group state is not a dated event: a basket-only row must not collect full recency,
    or every member of a turning basket outranks a name whose own dot printed yesterday."""
    row = {
        "triggers": {t: {"fired": False, "days_since": None} for t in TW.TRIGGER_IDS},
        "htf_washout": {"monthly": {"pinned_low": False}, "w2": {"pinned_low": False}},
        "base": {"base_depth_pct": 0.0},
        "basket": {"turn_state": "TURNING"},
        "slow_tier": {"eligible": False, "bars_to_cross_3d": None},
    }
    row["triggers"]["basket_turn"] = {"fired": True, "days_since": 0}
    score, nulls = TW.context_score(row)
    assert any("group-turn state only" in n for n in nulls), nulls
    # breadth (1/4 * 20) + cohort (0.6 * 10) and nothing else.
    assert score == pytest.approx(20 * 0.25 + 10 * 0.6, abs=1e-6), score


# ---------------------------------------------------------------------------
# (6) The context score is display-only and self-describing
# ---------------------------------------------------------------------------

def _full_row(**over):
    row = {
        "triggers": {t: {"fired": False, "days_since": None} for t in TW.TRIGGER_IDS},
        "htf_washout": {"monthly": {"pinned_low": True}, "w2": {"pinned_low": True}},
        "base": {"base_depth_pct": -60.0},
        "basket": {"turn_state": "CONFIRMED"},
        "slow_tier": {"eligible": True, "bars_to_cross_3d": None},
    }
    row["triggers"]["dot_1d"] = {"fired": True, "days_since": 0}
    row["triggers"]["pre_confluence_2d"] = {"fired": True, "days_since": 0}
    row["triggers"]["basket_turn"] = {"fired": True, "days_since": 0}
    row["triggers"]["leader_reset_turn"] = {"fired": True, "days_since": 0}
    row.update(over)
    return row


def test_context_score_is_bounded_and_saturates_at_100():
    score, nulls = TW.context_score(_full_row())
    assert score == pytest.approx(100.0, abs=1e-6), score
    assert nulls == []


def test_unknowable_terms_score_zero_and_are_named():
    row = _full_row(
        htf_washout={"monthly": {"pinned_low": None, "null_reason": "needs 20 monthly bars"},
                     "w2": {"pinned_low": None, "null_reason": "needs 20 w2 bars"}},
        base={"base_depth_pct": None},
        slow_tier={"eligible": False, "bars_to_cross_3d": None},
    )
    score, nulls = TW.context_score(row)
    # 0.30 recency + 0.20 breadth + 0.10 cohort survive; washout/base/proximity are null.
    assert score == pytest.approx(100 * (0.30 + 0.20 + 0.10), abs=1e-6), score
    joined = " ".join(nulls)
    for expect in ("washout.monthly", "washout.2w", "base", "proximity"):
        assert expect in joined, f"{expect} not named in {nulls}"


def test_published_formula_names_every_term_the_code_uses():
    src = inspect.getsource(TW.context_score)
    for term, weight in (("recency", "0.30"), ("breadth", "0.20"), ("washout", "0.15"),
                         ("base", "0.15"), ("cohort", "0.10"), ("proximity", "0.10")):
        assert term in TW.CONTEXT_SCORE_FORMULA, f"{term} missing from the published formula"
        assert f"{weight} * {term}" in src or f"{weight}*{term}" in src, (
            f"{term} is not weighted {weight} in the code — the published formula lies")
        assert f"{weight}*{term}" in TW.CONTEXT_SCORE_FORMULA.replace(" ", ""), (
            f"published formula does not weight {term} at {weight}")


def test_context_score_label_disclaims_authority():
    for label in (TW.CONTEXT_SCORE_LABEL, TW.CONTEXT_SCORE_LABEL_ZH):
        assert label.strip()
    low = TW.CONTEXT_SCORE_LABEL.lower()
    assert "non-authoritative" in low
    assert "not a rank" in low


# ---------------------------------------------------------------------------
# (7) The cap never deletes a lane
# ---------------------------------------------------------------------------

def _row(tk, score, triggers):
    return {"ticker": tk, "context_score": score, "triggers_fired": list(triggers)}


def test_cap_guarantees_every_lane_a_floor():
    """40 high-scoring group rows must not push the only leader row off the deck — the
    measured failure that motivated LANE_FLOOR (first full run: 0 leader rows in the top 40)."""
    rows = [_row(f"G{i:02d}", 90 - i, ["pre_confluence_2d", "basket_turn"]) for i in range(60)]
    rows += [_row("LEAD1", 10.0, ["leader_reset_turn"]), _row("DOT1", 9.0, ["dot_1d"])]
    rows.sort(key=lambda r: (-r["context_score"], r["ticker"]))

    deck, beyond = TW.apply_cap(rows, cap=40, lane_floor=TW.LANE_FLOOR)
    assert len(deck) == 40
    tickers = {r["ticker"] for r in deck}
    assert "LEAD1" in tickers, "the only leader-lane row was deleted by the cap"
    assert "DOT1" in tickers, "the only dot-lane row was deleted by the cap"
    assert len(beyond) == len(rows) - 40
    assert not (tickers & {r["ticker"] for r in beyond}), "a row is both in and beyond the deck"


def test_cap_output_is_sorted_by_score():
    rows = [_row(f"T{i:02d}", 90 - i, ["dot_1d"]) for i in range(20)]
    rows += [_row(f"P{i:02d}", 50 - i, ["pre_confluence_2d"]) for i in range(20)]
    rows.sort(key=lambda r: (-r["context_score"], r["ticker"]))
    deck, _ = TW.apply_cap(rows, cap=10, lane_floor=3)
    scores = [r["context_score"] for r in deck]
    assert scores == sorted(scores, reverse=True), scores


def test_lane_floor_is_clamped_so_lanes_cannot_overrun_a_small_cap():
    rows = [_row(f"X{i}", 50 - i, [t]) for i, t in enumerate(TW.TRIGGER_IDS)]
    deck, _ = TW.apply_cap(rows, cap=2, lane_floor=99)
    assert len(deck) == 2, "an oversized lane floor overran the cap"


# ---------------------------------------------------------------------------
# (8) The session stamp is majority-based, not max()
# ---------------------------------------------------------------------------

def test_session_stamp_is_the_majority_not_the_max():
    """The G0.2 fail-open shape: a handful of names reaching a later date must NOT make the
    whole deck read fresh. Measured live on 2026-08-08 — five 24/7 crypto/FX tapes carried an
    08-08 bar against 726 equities at 08-07 and moved the stamp."""
    # Explicit index, NOT freq="B": 2026-08-08 is a Saturday, which is exactly why the 24/7
    # tapes had a bar there and the equities did not. A business-day range would snap the
    # "ahead" fixture back onto 08-07 and quietly make this test vacuous.
    idx = pd.date_range(end="2026-08-07", periods=10, freq="B")
    majority = {f"EQ{i}": pd.Series(1.0, index=idx) for i in range(20)}
    ahead_idx = idx.append(pd.DatetimeIndex([pd.Timestamp("2026-08-08")]))
    ahead = {f"CRY{i}": pd.Series(1.0, index=ahead_idx) for i in range(3)}

    session, newest, note = TW._session_stamp({**majority, **ahead}, None)
    assert session == "2026-08-07", f"stamp failed open to {session}"
    assert newest == "2026-08-08", "the newest bar must still be visible"
    assert note and "3 of 23" in note, note


def test_session_stamp_with_no_graded_names_says_so():
    session, newest, note = TW._session_stamp({}, None)
    assert session is None and newest is None
    assert note and "unknown" in note.lower()


# ---------------------------------------------------------------------------
# (9) Nulls are printed, never asserted
# ---------------------------------------------------------------------------

def test_unknowable_200dma_is_none_never_false():
    """The PLTR narration-gap precedent: an unknowable average must not read as 'below'."""
    short = _series(_flat(100.0, 150))
    assert TW.ma_distance_pct(short) is None
    long = _series(_UPTREND)
    assert isinstance(TW.ma_distance_pct(long), float)


def test_htf_washout_legs_are_none_with_a_reason_when_unknowable():
    short = _series(_wobble(_ramp(100.0, 90.0, 210)))
    cells = TW.htf_washout(short)
    monthly = cells["monthly"]
    assert monthly["pinned_low"] is None, monthly
    assert monthly["null_reason"], "an unknowable leg must carry a plain-word reason"


def test_base_context_reports_three_distinct_readings():
    """off-high, base DEPTH and base AGE are different questions — a base that fell 40% and
    has recovered to -10% must not report -10% as its depth."""
    s = _series(_wobble(_flat(100.0, 60) + _ramp(100.0, 60.0, 120) + _ramp(60.0, 90.0, 60)))
    b = TW.base_context(s)
    assert b["off_52w_high_pct"] is not None and b["base_depth_pct"] is not None
    assert b["base_depth_pct"] < b["off_52w_high_pct"], (
        f"depth {b['base_depth_pct']} must be deeper than today's off-high "
        f"{b['off_52w_high_pct']}")
    assert b["base_age_sessions"] > 100, b["base_age_sessions"]


def test_reset_low_anchors_on_structure_not_on_todays_close():
    """The zone mechanism's cheap half (sibling receipt PR #5007: entry-vs-low 7.26% -> 2.29%).
    The anchor must be the LOW of the reset window, never the price at signal time."""
    vals = _flat(50.0, 30) + [40.0] + _flat(46.0, 5)
    s = _series(vals)
    cell = TW.reset_low(s, window=10)
    assert cell["reset_low"] == pytest.approx(40.0, abs=1e-6)
    assert cell["reset_low_date"] == str(s.index[30].date())
    assert cell["off_reset_low_pct"] == pytest.approx(15.0, abs=1e-6)
    assert cell["window"] == 10


def test_reset_low_is_null_on_a_series_too_short_to_have_one():
    assert TW.reset_low(_series(_flat(10.0, 3)))["reset_low"] is None


def test_reset_cell_claims_no_band_and_no_size():
    """It reports an anchor, not a buy zone — a zone claim needs the R3 builder + its gates."""
    cell = TW.reset_low(_series(_WASHOUT))
    assert set(cell) == {"reset_low", "reset_low_date", "off_reset_low_pct", "window"}


def test_replay_leg_lead_is_measured_off_the_same_low_as_the_confirmation():
    """The leg comparison must anchor trigger AND confirmation to one low in one move —
    a February trigger against a May confirmation is two events, not a lead."""
    s = _series(_WASHOUT)
    r = TW.first_deck_entry("TEST", s, benchmark=_bench(len(s)), sessions=120)
    assert r["window_start"], "the replay must disclose its window boundary"
    assert isinstance(r["first_trigger_at_window_start"], (bool, type(None)))
    if r["leg_trigger_date"] and r["first_confirm_date"]:
        assert r["leg_low_date"] <= r["leg_trigger_date"] <= r["first_confirm_date"], (
            f"leg ordering violated: low={r['leg_low_date']} "
            f"trigger={r['leg_trigger_date']} confirm={r['first_confirm_date']}")
        assert r["leg_lead_sessions"] >= 0


def test_replay_discloses_that_group_turn_has_no_history():
    """(c) cannot be replayed — the organ's ledger begins 2026-08-07 — and back-filling it
    would manufacture the very earliness the replay exists to measure."""
    r = TW.first_deck_entry("TEST", _series(_WASHOUT), benchmark=None, sessions=30)
    assert "group-turn" in r["note"], r["note"]
    assert "2026-08-07" in r["note"]


def test_replay_on_too_short_a_series_says_why_and_measures_nothing():
    r = TW.first_deck_entry("TEST", _series(_flat(10.0, 50)), benchmark=None)
    assert r["first_trigger_date"] is None
    assert "below the" in r["note"] and "bar deck floor" in r["note"]


def test_no_nan_or_inf_ever_reaches_the_artifact():
    s = _series(_WASHOUT)
    row = TW.evaluate("TEST", s, benchmark=_bench(len(s)))
    blob = json.dumps(row, default=str)
    for bad in ("NaN", "Infinity", "-Infinity"):
        assert bad not in blob, f"{bad} serialised into a deck row"


def test_numpy_scalars_never_leak_into_the_row():
    """numpy bools/floats are not JSON types; every published value must be a Python one."""
    row = TW.evaluate("TEST", _series(_WASHOUT), benchmark=_bench(len(_WASHOUT)))

    def walk(o, path="row"):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, f"{path}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{path}[{i}]")
        else:
            assert not isinstance(o, (np.bool_, np.integer, np.floating)), (
                f"{path} is a numpy scalar ({type(o).__name__})")

    walk(row)


# ---------------------------------------------------------------------------
# (10) The why-not cell
# ---------------------------------------------------------------------------

def test_why_not_cell_names_its_blocking_legs():
    s = _series(_WASHOUT)
    cell = TW.slow_tier_cell(s, None)
    assert cell["evaluated"] is True
    if not cell["eligible"]:
        assert cell["blocking"], "a name the cascade refused must say which leg refused it"
    for leg in cell["blocking"]:
        assert leg in TW.BLOCKER_LEXICON, f"blocking leg {leg!r} has no plain-word entry"


def test_an_admitted_name_reports_no_blockers():
    """'T2, but blocked' is a false statement; this cell answers why-NOT or stays silent."""
    for vals in (_WASHOUT, _UPTREND, _LEADER_PULLBACK):
        cell = TW.slow_tier_cell(_series(vals), None)
        if cell["eligible"]:
            assert cell["blocking"] == [], cell["blocking"]


def test_every_blocker_lexicon_entry_is_bilingual():
    for leg, pair in TW.BLOCKER_LEXICON.items():
        assert pair.get("en", "").strip(), f"{leg} has no EN label"
        assert pair.get("zh", "").strip(), f"{leg} has no ZH label"
        assert pair["en"] != pair["zh"], f"{leg}: zh is a copy of en"


# ---------------------------------------------------------------------------
# (11) Display-tier disclosure and voice
# ---------------------------------------------------------------------------

_USER_STRINGS = ("DISCLOSURE", "DISCLOSURE_ZH", "AUTHORITY", "AUTHORITY_ZH",
                 "NOISE_NOTE", "NOISE_NOTE_ZH", "CONTEXT_SCORE_LABEL",
                 "CONTEXT_SCORE_LABEL_ZH", "CONTEXT_SCORE_FORMULA")


def test_disclosure_carries_the_windows_not_certainties_voice():
    assert "windows, not certainties" in TW.DISCLOSURE
    assert "观察窗口" in TW.DISCLOSURE_ZH


def test_authority_block_is_display_tier():
    low = TW.AUTHORITY.lower()
    assert "display tier" in low and "zero scored authority" in low
    assert "ranks" in low or "rank" in low


def test_the_ci_guarded_word_validated_appears_nowhere():
    src = Path(TW.__file__).read_text()
    assert "validated" not in src.lower().replace("validated master", ""), (
        "the CI-guarded word 'validated' must not appear in user-facing copy")


def test_falsifier_vocabulary_is_never_front_facing():
    """Operator 2026-07-27: tripwire/refutation language stays off user surfaces."""
    banned = ("falsifier", "refuted", "invalidated", "证伪", "thesis broken")
    for name in _USER_STRINGS:
        blob = getattr(TW, name).lower()
        for word in banned:
            assert word not in blob, f"{name} carries front-facing {word!r}"


def test_no_forced_directional_call_in_any_user_string():
    """DNR:KILL-FORCED-CALLS — detection sees, the operator decides."""
    banned = ("will rise", "will rally", "guaranteed", "sure thing", "must buy",
              "price target", "buy now")
    for name in _USER_STRINGS:
        blob = getattr(TW, name).lower()
        for word in banned:
            assert word not in blob, f"{name} carries a directional claim: {word!r}"


def test_every_user_facing_string_has_a_zh_sibling():
    for en_name in ("DISCLOSURE", "AUTHORITY", "NOISE_NOTE", "CONTEXT_SCORE_LABEL"):
        zh = getattr(TW, f"{en_name}_ZH")
        assert zh.strip(), f"{en_name} has no zh sibling"
        assert any("一" <= ch <= "鿿" for ch in zh), (
            f"{en_name}_ZH carries no Chinese characters")


def test_lexicon_is_bilingual_and_covers_every_trigger():
    for tid in TW.TRIGGER_IDS:
        assert tid in TW.LEXICON, f"trigger {tid} has no lexicon entry"
        assert TW.LEXICON[tid]["en"].strip() and TW.LEXICON[tid]["zh"].strip()
    for key, pair in TW.LEXICON.items():
        assert any("一" <= ch <= "鿿" for ch in pair["zh"]), key


def test_module_imports_no_scoring_or_board_surface():
    """Zero-authority wiring: this desk must not be able to reach a graded lane."""
    src = Path(TW.__file__).read_text()
    for forbidden in ("us_board_rank", "prophet_bridge", "us_act_now", "signal_gate",
                      "theme_scoring"):
        assert forbidden not in src, f"{forbidden} imported into a display-tier desk"


# ---------------------------------------------------------------------------
# (12) Frozen constants
# ---------------------------------------------------------------------------

def test_v1_constants_are_pinned():
    assert TW.SCHEMA == "us_turn_watch.v1"
    assert TW.SELECTION_ERA == "anticipation-v1-2026-08-08"
    assert TW.MIN_BARS == 200
    assert TW.TRIGGER_LOOKBACK_SESSIONS == 5
    assert TW.DOT_WASHED_WINDOW == 8
    assert TW.DECK_CAP == 40
    assert TW.LANE_FLOOR == 5
    assert TW.BASE_WINDOW == 252
    assert TW.REL_WINDOW == 20
    assert TW.MA_WINDOW == 200
    assert TW.BENCHMARK == "SPY"
    assert TW.TRIGGER_IDS == ("dot_1d", "pre_confluence_2d", "basket_turn",
                              "leader_reset_turn")
    assert TW.BASKET_TURN_STATES == ("TURNING", "CONFIRMED")


def test_anchor_era_travels_with_the_numbers():
    """A private-helper import carries its owner's era; the artifact must publish it."""
    from engine import confluence_tiers as CT
    assert TW.ANCHOR_ERA == CT.ANCHOR_ERA
    assert TW.INDICATOR_SOURCE == "engine.confluence_tiers"


def test_leader_pullback_source_is_always_disclosed():
    """R4's organ may or may not exist on a given base — which one ran is never a guess."""
    row = TW.evaluate("TEST", _series(_LEADER_PULLBACK), benchmark=_bench(len(_LEADER_PULLBACK)))
    src = row["leader_pullback_source"]
    assert src, "no leader-pullback source stamped on the row"
    assert src.startswith("inline_minimal_v1") or src.startswith("engine.us_leader_pullback:")


# ---------------------------------------------------------------------------
# (13) Universe
# ---------------------------------------------------------------------------

def test_universe_excludes_index_fx_and_crypto_store_files(tmp_path):
    d = tmp_path / TW.DECK_STORE
    d.mkdir(parents=True)
    for stem in ("AAPL", "NVDA", "_GSPC", "DX-Y.NYB", "BTC-USD", "USDSGD_X", "ETH-USD"):
        (d / f"{stem}.parquet").write_bytes(b"")
    assert TW.universe(tmp_path) == ["AAPL", "NVDA"]


def test_universe_limit_is_deterministic_alphabetical(tmp_path):
    d = tmp_path / TW.DECK_STORE
    d.mkdir(parents=True)
    for stem in ("ZZZ", "AAA", "MMM"):
        (d / f"{stem}.parquet").write_bytes(b"")
    assert TW.universe(tmp_path, limit=2) == ["AAA", "MMM"]


def test_missing_price_store_is_announced_not_silent(tmp_path, capsys):
    assert TW.universe(tmp_path) == []
    out = capsys.readouterr().out
    assert "::warning" in out


def test_short_history_names_are_excluded_and_counted(tmp_path, monkeypatch):
    """The bar floor is a COUNT in coverage, not a silent drop."""
    root = tmp_path / "data"
    (root / TW.DECK_STORE).mkdir(parents=True)
    (root / "baskets").mkdir(parents=True)
    (root / "baskets" / "membership.json").write_text(json.dumps({"baskets": {}}))
    idx = pd.date_range(end=_FIXTURE_END, periods=50, freq="B")
    pd.DataFrame({"close": np.linspace(10, 12, 50)}, index=idx).to_parquet(
        root / TW.DECK_STORE / "SHORT.parquet")
    art = TW.compute_deck(root, tmp_path / "site")
    assert art["coverage"]["skipped_short_history"] == 1
    assert art["coverage"]["graded"] == 0
    assert art["deck"] == []


# ---------------------------------------------------------------------------
# (14) Annotations start the line
# ---------------------------------------------------------------------------

def _annotation_calls(path: Path):
    """Every call in `path` whose first argument's source contains a `::` annotation.

    Parsed with `ast`, not grepped: a substring scan hits the module docstring (which
    DISCUSSES annotations) and reads green for the wrong reason.
    """
    import ast

    src = path.read_text()
    tree = ast.parse(src)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        try:
            arg = ast.get_source_segment(src, node.args[0]) or ""
        except Exception:  # noqa: BLE001
            continue
        if "::warning" in arg or "::error" in arg or "::notice" in arg:
            out.append(node)
    return out


@pytest.mark.parametrize("module_path", [
    Path(TW.__file__),
    Path(TW.__file__).parent.parent / "scripts" / "build_turn_watch.py",
])
def test_every_annotation_is_a_bare_print_at_line_start(module_path):
    """GitHub silently drops a `::` that does not start its line, and this package's logging
    format prefixes every record — so annotations must be BARE prints, never `log.warning`
    (house law + the tests/test_gh_annotation_line_start.py precedent). Neither module is
    exempt: both run inside an Actions step via the nightly DAG."""
    calls = _annotation_calls(module_path)
    assert calls, f"no annotation calls found in {module_path} — did the scan break?"
    for node in calls:
        fn = node.func
        name = fn.id if isinstance(fn, __import__("ast").Name) else (
            getattr(fn, "attr", None))
        assert name == "print", (
            f"{module_path.name}:{node.lineno} emits an annotation through {name!r}, "
            f"not a bare print — GitHub will drop it")


@pytest.mark.parametrize("module_path", [
    Path(TW.__file__),
    Path(TW.__file__).parent.parent / "scripts" / "build_turn_watch.py",
])
def test_annotations_are_flushed(module_path):
    """stdout is block-buffered when piped in CI; an unflushed annotation can be lost."""
    for node in _annotation_calls(module_path):
        kw = {k.arg for k in node.keywords}
        assert "flush" in kw, (
            f"{module_path.name}:{node.lineno} annotation print is missing flush=True")


# ---------------------------------------------------------------------------
# End-to-end shape on a frozen mini-store
# ---------------------------------------------------------------------------

def test_compute_deck_end_to_end_on_a_frozen_store(tmp_path):
    root = tmp_path / "data"
    site = tmp_path / "site"
    (root / TW.DECK_STORE).mkdir(parents=True)
    (root / "baskets").mkdir(parents=True)

    def _write(stem, vals):
        idx = pd.date_range(end=_FIXTURE_END, periods=len(vals), freq="B")
        pd.DataFrame({"close": vals}, index=idx).to_parquet(
            root / TW.DECK_STORE / f"{stem}.parquet")

    _write("WASH", _WASHOUT)
    _write("LEAD", _LEADER_PULLBACK)
    _write("CALM", _UPTREND)
    _write(TW.BENCHMARK, [100.0 * (1.0 + 0.0002) ** i for i in range(len(_UPTREND))])
    (root / "baskets" / "membership.json").write_text(json.dumps({"baskets": {
        "test_theme": {"name": "Test Theme", "name_zh": "测试主题",
                       "members": [{"ticker": "WASH", "added": "2020-01-01",
                                    "removed": None}]}}}))
    (site / "basketdata").mkdir(parents=True)
    (site / "basketdata" / "us_basket_turn.json").write_text(json.dumps({
        "baskets": {"test_theme": {"state": "TURNING", "days_in_state": 3,
                                   "data_session": _FIXTURE_END}}}))

    art = TW.compute_deck(root, site)

    assert art["schema"] == TW.SCHEMA
    assert art["anchor_era"] == TW.ANCHOR_ERA
    assert art["selection_era"] == TW.SELECTION_ERA
    assert art["data_session"] == _FIXTURE_END
    assert art["coverage"]["benchmark"] == TW.BENCHMARK
    assert set(art["coverage"]["deck_by_trigger"]) == set(TW.TRIGGER_IDS)
    assert isinstance(art["runtime_seconds"], float)

    wash = next((r for r in art["deck"] if r["ticker"] == "WASH"), None)
    assert wash is not None, "the washout fixture never reached the deck"
    assert wash["basket"]["basket_id"] == "test_theme"
    assert wash["basket"]["name_zh"] == "测试主题"
    assert wash["triggers"]["basket_turn"]["fired"] is True
    assert wash["in_deck_universe"] is True

    # The whole artifact must round-trip through strict JSON.
    json.loads(json.dumps(art, default=str))


def test_write_artifact_lands_at_the_documented_path(tmp_path):
    p = TW.write_artifact({"schema": TW.SCHEMA, "deck": []}, tmp_path)
    assert p == tmp_path / "prophet" / "turn_watch.json"
    assert json.loads(p.read_text())["schema"] == TW.SCHEMA
