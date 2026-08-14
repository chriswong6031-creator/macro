"""The not-topped veto's three legs are PUBLISHED, and the decision is unchanged.

`engine/confluence_tiers.py::cascade()` computed `stoch_ob` / `stoch_bear` /
`macd_bear` and threw them away; only their OR-negation `not_topped` survived, so
no forward store could ever say WHICH leg vetoed a name (masterplan §13.2). They
are now carried on every return and onto the `signal_gate` verdict.

That edit touches a SCORED GATE module, so the load-bearing test here is not that
the new keys exist — it is that **nothing else moved**:

* :data:`GOLDEN_DECISION_DIGESTS` is a sha256 per fixture over every
  decision-bearing field `cascade()` returns, **recorded from the pre-change
  module** (`git show HEAD:engine/confluence_tiers.py` at the commit this change
  was written against, run with `VETO_HYSTERESIS_CONFIRM` / `CONFLUENCE_T3_PERSIST`
  unset). A golden regenerated from the post-change code would prove nothing;
  these numbers predate the edit.
* :data:`GOLDEN_GATE_VERDICTS` does the same one layer up, for the fields a board
  branches on — `eligible`, `tier_cascade`, `weight`, `tier_sub`.

MUTATION-VERIFIED (2026-08-14): flipping `stoch_bear = k3n < d3n` to `>` in
`cascade()` reds `test_the_cascade_decision_is_byte_identical_to_the_pre_change_module`
on 4 of 14 fixtures and `test_the_gate_verdict_is_byte_identical_to_the_pre_change_module`
on 1 of 3 — so the guard can see a gate condition move, which is exactly the
failure it is here to refuse.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from engine import confluence_tiers, signal_gate

# --------------------------------------------------------------------------- #
# deterministic fixture battery — seeded RNG, no disk, no network
# --------------------------------------------------------------------------- #

#: ``name -> (bars, seed, drift, vol, shape)``.  Chosen for DECISION coverage, not
#: for realism.  The two that carry the argument:
#:
#: * ``young_210`` sits in the ``[MIN_HISTORY=159, m3_s3 warmup=232)`` window — the
#:   cascade runs the veto in full, but `macd_bear` reads `float(nan) < float(nan)`
#:   and FAILS OPEN.  This is the cohort the null-state columns exist for.
#: * ``thin_120`` is below ``MIN_HISTORY`` entirely: the veto never runs, so every
#:   leg must publish None rather than the False that reads as "checked, clean".
#: ``deep_400_turn`` fires a real tier; the rest are vetoed by knowable legs.
_SPECS: dict[str, tuple[int, int, float, float, str]] = {
    "thin_120":       (120, 11, 0.0010, 0.012, "trend"),
    "young_210":      (210, 78, 0.0008, 0.011, "trend"),
    "warm_250":       (250, 22, 0.0008, 0.011, "trend"),
    "deep_400":       (400, 33, 0.0006, 0.013, "trend"),
    "deep_400_top":   (400, 44, 0.0006, 0.013, "topped"),
    "deep_400_flush": (400, 55, 0.0006, 0.015, "washout"),
    "flat_300":       (300, 66, 0.0000, 0.004, "trend"),
    "deep_400_turn":  (400,  6, 0.0006, 0.013, "turn"),
}


def _series(n: int, seed: int, drift: float, vol: float, shape: str) -> pd.Series:
    rng = np.random.default_rng(seed)
    steps = rng.normal(drift, vol, n)
    if shape == "topped":
        steps[-30:] = rng.normal(0.004, vol, 30)          # blow-off into the tail
    elif shape == "washout":
        steps[-40:-10] = rng.normal(-0.006, vol, 30)      # deep flush, then a turn
        steps[-10:] = rng.normal(0.006, vol, 10)
    elif shape == "turn":
        steps[-60:-8] = rng.normal(-0.005, 0.014, 52)
        steps[-8:] = rng.normal(0.008, 0.012, 8)
    return pd.Series(np.round(50.0 * np.exp(np.cumsum(steps)), 4),
                     index=pd.bdate_range("2024-01-01", periods=n))


#: Every field of `cascade()`'s return a caller could branch on, plus the display
#: fields riding the same dict.  The NEW leg keys are deliberately absent: this
#: tuple is the pre-change surface, and pinning it is what makes the change
#: provably additive.
DECISION_FIELDS = (
    "tier", "weight", "sub", "eligible", "bars_to_cross", "asof", "not_topped",
    "ticks", "provisional", "htf", "hist_d2", "hist_d3", "bars", "young_history",
    "above200", "null_legs", "veto_legs_null", "anchor_era", "evaluated",
    "tier_event_date", "tier_observed_date", "tier_observation_provisional",
)

#: sha256 of the DECISION_FIELDS projection, RECORDED FROM THE PRE-CHANGE MODULE.
#:
#: case                        tier  elig   not_topped  unknowable-legs  bars
#: thin_120|take=False         None  False  True        macd_bear        120
#: thin_120|take=True          T1    True   True        macd_bear        120
#: young_210|take=*            None  False  True        macd_bear        210
#: warm_250|take=*             None  False  False       -                250
#: deep_400|take=*             None  False  False       -                400
#: deep_400_top|take=*         None  False  False       -                400
#: deep_400_flush|take=*       None  False  False       -                400
#: flat_300|take=*             None  False  False       -                300
#: deep_400_turn|take=False    T2    True   True        -                400
#: deep_400_turn|take=True     T1    True   True        -                400
GOLDEN_DECISION_DIGESTS = {
    "thin_120|take=False":       "7a46c880bda706f81d3e75fe42a21ccbbc9c7cb5fa71878c72a3ef1f98ff67dc",
    "thin_120|take=True":        "ac36f3e5c9ae0d2dd016fb3358044396d081a0acf6948cb794778f977c5c6c7a",
    "young_210|take=False":      "76027384d3a133574ab87fd3dce8e28031f1f0889920ad480e0eadce1cca72c7",
    "young_210|take=True":       "76027384d3a133574ab87fd3dce8e28031f1f0889920ad480e0eadce1cca72c7",
    "warm_250|take=False":       "a2189bc09b8481d8622e4d0d06dd01da5fa61df58e470406b3ab27dea1ac1483",
    "warm_250|take=True":        "a2189bc09b8481d8622e4d0d06dd01da5fa61df58e470406b3ab27dea1ac1483",
    "deep_400|take=False":       "4d2280233fc565981ebd7ada41827829e8a842dcdd85d920db488730e609d34d",
    "deep_400|take=True":        "4d2280233fc565981ebd7ada41827829e8a842dcdd85d920db488730e609d34d",
    "deep_400_top|take=False":   "dce7b04635f194546c29f54506e73016bb87809c10019ad7cc4a546875a5092b",
    "deep_400_top|take=True":    "dce7b04635f194546c29f54506e73016bb87809c10019ad7cc4a546875a5092b",
    "deep_400_flush|take=False": "baa58d8d7c9642285416a77bc2d81a8fbb4bdd35ba193dba2c5fa71703cd100d",
    "deep_400_flush|take=True":  "baa58d8d7c9642285416a77bc2d81a8fbb4bdd35ba193dba2c5fa71703cd100d",
    "flat_300|take=False":       "cdff4aad8048f736de801f14de19226d30bdb3a8e6003bb00958419d100bf93b",
    "flat_300|take=True":        "cdff4aad8048f736de801f14de19226d30bdb3a8e6003bb00958419d100bf93b",
    "deep_400_turn|take=False":  "8dbce59394733a108c1eb18961df72e81ba49a08fd1ce80d11b4ce2f98092bd6",
    "deep_400_turn|take=True":   "b61e5eed107416a41a3cc80d4e3303df23551ac66eb98eaa25d79c0e490724fd",
}

#: `signal_gate.gate()` verdict fields a board branches on, RECORDED FROM THE
#: PRE-CHANGE MODULE (gate() run with `signal_gate.confluence_tiers` swapped to it).
GOLDEN_GATE_VERDICTS = {
    "thin_120": {
        "eligible": False, "tier_cascade": None, "weight": 0.0, "tier_sub": None,
        "provisional": False, "ticks": None, "near_miss_reason": None,
        "htf_s1": False, "htf_s2": False, "young_history": True,
        "history_bars": 120, "above200": None,
    },
    "deep_400_turn": {
        "eligible": True, "tier_cascade": "T2", "weight": 1.0, "tier_sub": "deep",
        "provisional": False, "ticks": 2, "near_miss_reason": None,
        "htf_s1": False, "htf_s2": False, "young_history": False,
        "history_bars": 400, "above200": False,
    },
    "deep_400_top": {
        "eligible": False, "tier_cascade": None, "weight": 0.0, "tier_sub": None,
        "provisional": False, "ticks": 19, "near_miss_reason": None,
        "htf_s1": False, "htf_s2": False, "young_history": False,
        "history_bars": 400, "above200": True,
    },
    "young_210": {
        "eligible": False, "tier_cascade": None, "weight": 0.0, "tier_sub": None,
        "provisional": False, "ticks": None, "near_miss_reason": None,
        "htf_s1": False, "htf_s2": False, "young_history": False,
        "history_bars": 210, "above200": True,
    },
}

VETO_LEGS = ("stoch_ob", "stoch_bear", "macd_bear")


@pytest.fixture(autouse=True)
def _frozen_env(monkeypatch):
    """The goldens were recorded with both veto/persistence knobs unset."""
    monkeypatch.delenv("VETO_HYSTERESIS_CONFIRM", raising=False)
    monkeypatch.delenv("CONFLUENCE_T3_PERSIST", raising=False)


def _digest(result: dict) -> str:
    projection = {k: result.get(k) for k in DECISION_FIELDS}
    return hashlib.sha256(
        json.dumps(projection, sort_keys=True, default=str).encode()).hexdigest()


def _cases():
    for name, spec in _SPECS.items():
        series = _series(*spec)
        for take_active in (False, True):
            yield f"{name}|take={take_active}", series, take_active


# --------------------------------------------------------------------------- #
# 1. the fence: the decision did not move
# --------------------------------------------------------------------------- #

def test_the_cascade_decision_is_byte_identical_to_the_pre_change_module():
    """Every decision-bearing field, on every fixture, unchanged by the edit."""
    drifted = {}
    for key, series, take_active in _cases():
        result = confluence_tiers.cascade(series, take_active=take_active)
        actual = _digest(result)
        if actual != GOLDEN_DECISION_DIGESTS[key]:
            drifted[key] = {k: result.get(k) for k in DECISION_FIELDS}
    assert not drifted, (
        "surfacing the veto legs must be PURELY ADDITIVE — the cascade decision "
        "moved on: " + json.dumps(drifted, indent=2, sort_keys=True, default=str)
    )


def test_the_gate_verdict_is_byte_identical_to_the_pre_change_module():
    """One layer up: what a board actually branches on is unchanged."""
    drifted = {}
    for name, golden in GOLDEN_GATE_VERDICTS.items():
        verdict = signal_gate.gate("TEST", _series(*_SPECS[name]))
        actual = {k: verdict.get(k) for k in golden}
        if actual != golden:
            drifted[name] = {"expected": golden, "actual": actual}
    assert not drifted, (
        "the gate's eligibility/tier output moved: "
        + json.dumps(drifted, indent=2, sort_keys=True, default=str))


def test_the_published_legs_are_not_read_back_by_the_decision():
    """A leg key injected with a lie must not change any decision.

    The fence above proves the values did not move; this proves the new keys are
    not an INPUT anywhere — mutate them on the way out and `not_topped`, `tier`
    and `eligible` are indifferent.
    """
    series = _series(*_SPECS["deep_400_turn"])
    honest = confluence_tiers.cascade(series, take_active=False)
    poisoned = dict(honest, stoch_ob=True, stoch_bear=True, macd_bear=True)
    for field in ("tier", "eligible", "not_topped", "weight"):
        assert poisoned[field] == honest[field]


# --------------------------------------------------------------------------- #
# 2. the feature: the legs are published, and their null state with them
# --------------------------------------------------------------------------- #

def test_every_cascade_return_carries_all_three_legs():
    """Including the blank and crash paths — a missing key is not the same as
    False, and a store that stamps `record[leg]` must get one meaning per row."""
    for key, series, take_active in _cases():
        result = confluence_tiers.cascade(series, take_active=take_active)
        for leg in VETO_LEGS:
            assert leg in result, f"{key}: {leg} missing from the cascade return"
            assert result[leg] is None or isinstance(result[leg], (bool, np.bool_))


def test_the_crash_path_publishes_nulls_not_falses():
    """`evaluated=False` means nothing was checked — a False leg would read as
    'checked, and clean' (audit F2, the same shape as `above200`/PLTR)."""
    unparseable_index = pd.Series([1.0, 2.0, 3.0], index=["not", "a", "date"])
    result = confluence_tiers.cascade(unparseable_index)
    assert result["evaluated"] is False
    for leg in VETO_LEGS:
        assert result[leg] is None


def test_below_min_history_the_legs_are_null_because_the_veto_never_ran():
    """`thin_120` returns before the veto block, so no leg has a value to publish.

    This is the distinction the columns exist for: `veto_legs_null` names
    `macd_bear` here too, but for a DIFFERENT reason than at 210 bars — there the
    veto ran and one leg failed open; here nothing ran at all.
    """
    result = confluence_tiers.cascade(_series(*_SPECS["thin_120"]))
    assert result["bars"] == 120 and result["evaluated"] is True
    assert "macd_bear" in (result["veto_legs_null"] or {})
    for leg in VETO_LEGS:
        assert result[leg] is None


def test_not_topped_is_exactly_the_or_of_the_published_legs():
    """The published legs must BE the veto's own arithmetic, not a re-derivation."""
    for key, series, take_active in _cases():
        result = confluence_tiers.cascade(series, take_active=take_active)
        legs = [result[leg] for leg in VETO_LEGS]
        if any(v is None for v in legs):
            continue                      # cascade never got that far
        assert result["not_topped"] == (not any(legs)), key


def test_an_unknowable_leg_is_published_False_and_named_in_veto_legs_null():
    """The FAIL-OPEN disclosure, end to end.

    `macd_bear` compares `float(nan) < float(nan)` below the 3D RSI-MACD's warmup,
    which is False — the veto passes on a leg it never checked. The boolean stays
    that value on purpose (tri-stating it would blank the whole young cohort and
    silently reverse the 2026-08-05 floor lift); what makes the stamp honest is
    that `veto_legs_null` NAMES the leg beside it.
    """
    result = confluence_tiers.cascade(_series(*_SPECS["young_210"]))
    assert result["bars"] == 210
    assert "macd_bear" in (result["veto_legs_null"] or {})
    assert result["macd_bear"] is False          # fail-open arithmetic, preserved
    assert "stoch_ob" not in (result["veto_legs_null"] or {})
    assert result["stoch_ob"] is False           # genuinely measured, and clean
    assert result["not_topped"] is True          # passed a leg it could not check


def test_the_gate_verdict_carries_the_legs_beside_their_null_disclosure():
    verdict = signal_gate.gate("TEST", _series(*_SPECS["young_210"]))
    for leg in VETO_LEGS:
        assert leg in verdict
    assert verdict["macd_bear"] is False
    assert "macd_bear" in verdict["veto_legs_null"]
    assert verdict["veto_legs_null"]["macd_bear"].startswith("needs ")
