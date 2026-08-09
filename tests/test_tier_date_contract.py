"""Cascade-native tier dates for board/plan provenance.

The §7 marker is authoritative only for T1. T2 has its own fired 2D event, while
T3/T4 are projections and therefore have an observation but no event. These tests pin
that boundary end-to-end through ``signal_gate.compact`` without changing any tier gate,
ordering, weight, or the incumbent T3-only ``provisional`` badge.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import confluence_tiers, signal_gate


_DATE_KEYS = {
    "tier_event_date",
    "tier_observed_date",
    "tier_observation_provisional",
}


def _synthetic_close(n: int = 520, seed: int = 0) -> pd.Series:
    """Deterministic cross-producing fixture shared with provisional replay tests."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    idx = pd.bdate_range("2023-01-02", periods=n)
    base = 100 + 12 * np.sin(t / 24) + 0.03 * t + 4 * np.sin(t / 6)
    return pd.Series(base + np.cumsum(rng.normal(0, 0.3, n)), index=idx)


def _through(seed: int, stamp: str) -> pd.Series:
    close = _synthetic_close(seed=seed)
    return close[close.index <= pd.Timestamp(stamp)]


def _analyze_result(marker: dict) -> dict:
    return {
        "markers": [marker],
        "state": "long-bias",
        "above200": True,
        "weekly_bull": True,
        "early_now": False,
        "asof": "2024-01-10",
    }


def test_t1_uses_only_the_explicit_marker_knowability_close(monkeypatch):
    """T1 event = §7 signal_date; confirmation/current observation are distinct clocks."""
    close = _through(22, "2024-01-10")
    marker = {
        "date": "2024-01-03",              # legacy 3D bucket-open label
        "type": "buy",
        "quality": "take",
        "reason": "confirmed",
        "signal_date": "2024-01-05",       # bucket close / native T1 event
        "confirmed_date": "2024-01-10",    # buy-filter verdict knowable
    }
    monkeypatch.setattr(signal_gate, "analyze",
                        lambda ticker, tape, **kwargs: _analyze_result(marker))

    verdict = signal_gate.gate("SYN", close)
    assert verdict["tier_cascade"] == "T1"
    assert verdict["tier_event_date"] == "2024-01-05"
    assert verdict["tier_observed_date"] == "2024-01-10"
    assert verdict["tier_observation_provisional"] is False
    assert verdict["last"]["confirmed_date"] == "2024-01-10"
    assert signal_gate.compact(verdict)["tier_event_date"] == "2024-01-05"


def test_t1_missing_or_invalid_event_date_fails_null_without_changing_grade():
    """A weekend/absent marker clock is never replaced with legacy date or as-of."""
    close = _through(22, "2024-01-10")
    valid = confluence_tiers.cascade(
        close, take_active=True, take_date="2024-01-10",
        take_event_date="2024-01-10",
    )
    weekend = confluence_tiers.cascade(
        close, take_active=True, take_date="2024-01-10",
        take_event_date="2024-01-06",
    )
    missing = confluence_tiers.cascade(
        close, take_active=True, take_date="2024-01-10",
    )

    assert valid["tier"] == weekend["tier"] == missing["tier"] == "T1"
    assert weekend["tier_event_date"] is None
    assert missing["tier_event_date"] is None
    assert weekend["tier_observed_date"] == missing["tier_observed_date"] == "2024-01-10"
    # Provenance is additive only: it cannot influence tier gates, order, weight or age.
    for key in valid.keys() - _DATE_KEYS:
        assert weekend[key] == valid[key]
        assert missing[key] == valid[key]


def test_t2_event_is_the_native_2d_cross_not_an_unrelated_marker(monkeypatch):
    """The NVDA/GE class: a T2 plan must never borrow §7 marker dates."""
    close = _through(22, "2024-01-10")
    unrelated = {
        "date": "2024-01-08",
        "type": "buy",
        "quality": "block",
        "reason": "veto: bearish divergence",
        "signal_date": "2024-01-10",
        "confirmed_date": None,
    }
    monkeypatch.setattr(signal_gate, "analyze",
                        lambda ticker, tape, **kwargs: _analyze_result(unrelated))

    verdict = signal_gate.gate("SYN", close)
    assert verdict["tier_cascade"] == "T2"
    assert verdict["last"]["signal_date"] == "2024-01-10"
    assert verdict["tier_event_date"] == "2024-01-05"
    assert verdict["tier_observed_date"] == "2024-01-10"
    assert verdict["tier_observation_provisional"] is False
    compact = signal_gate.compact(verdict)
    assert compact["tier_event_date"] == "2024-01-05"
    assert compact["tier_observed_date"] == "2024-01-10"


def test_t3_projection_has_observation_but_no_fired_event_end_to_end():
    close = _through(50, "2023-11-20")
    casc = confluence_tiers.cascade(close)
    assert casc["tier"] == "T3"
    assert casc["tier_event_date"] is None
    assert casc["tier_observed_date"] == "2023-11-20"
    assert casc["tier_observation_provisional"] is True
    assert casc["provisional"] is True              # incumbent T3 display badge

    verdict = signal_gate.gate("SYN", close)
    compact = signal_gate.compact(verdict)
    assert verdict["tier_cascade"] == "T3"
    assert compact["tier_event_date"] is None
    assert compact["tier_observed_date"] == "2023-11-20"
    assert compact["tier_observation_provisional"] is True
    assert compact["provisional"] is True


def test_t4_projection_gets_date_provenance_without_changing_gate_behavior():
    """T4 remains eligible-but-not-buyable and keeps the incumbent provisional=False."""
    close = _through(2, "2023-11-21")
    casc = confluence_tiers.cascade(close)
    assert casc["tier"] == "T4"
    assert casc["tier_event_date"] is None
    assert casc["tier_observed_date"] == "2023-11-21"
    assert casc["tier_observation_provisional"] is True
    assert casc["provisional"] is False             # do not repurpose calibrated badge

    verdict = signal_gate.gate("SYN", close)
    assert verdict["tier_cascade"] == "T4"
    assert verdict["eligible"] is True              # existing signal_gate behaviour
    assert signal_gate.is_buyable(verdict) is False  # existing board admission fence
    assert verdict["provisional"] is False
    assert verdict["tier_observation_provisional"] is True


def test_forming_t1_is_observed_provisionally_on_its_marker_close(monkeypatch):
    """signal_gate's pending->T1 promotion gets the same fail-closed clock contract."""
    close = _through(22, "2024-01-10")
    pending = {
        "date": "2024-01-08",
        "type": "buy",
        "quality": "pending",
        "reason": "pending confirmation",
        "signal_date": "2024-01-10",
        "confirmed_date": None,
    }
    monkeypatch.setattr(signal_gate, "analyze",
                        lambda ticker, tape, **kwargs: _analyze_result(pending))

    def no_native_tier(tape, *, take_active=False, take_date=None,
                       take_event_date=None, market="US"):
        assert take_active is False
        return dict(confluence_tiers._BLANK, evaluated=True, not_topped=True,
                    ticks=0, bars=len(tape), young_history=False,
                    anchor_era=confluence_tiers.ANCHOR_ERA)

    monkeypatch.setattr(confluence_tiers, "cascade", no_native_tier)
    verdict = signal_gate.gate("SYN", close)
    assert verdict["tier_cascade"] == "T1"
    assert verdict["sub"] == "pending"
    assert verdict["tier_event_date"] == "2024-01-10"
    assert verdict["tier_observed_date"] == "2024-01-10"
    assert verdict["tier_observation_provisional"] is True
    assert verdict["last"]["confirmed_date"] is None


def test_no_tier_has_no_tier_dates():
    close = _synthetic_close(n=60)
    casc = confluence_tiers.cascade(close)
    assert casc["tier"] is None
    assert casc["tier_event_date"] is None
    assert casc["tier_observed_date"] is None
    assert casc["tier_observation_provisional"] is False
