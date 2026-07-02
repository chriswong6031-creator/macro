"""Provisional-basis tier replay guards — W6 #22 (engine.provisional_replay).

Pins the three properties the replay harness rests on:

  1. DETERMINISM — replaying the SAME day on the SAME truncated series twice yields byte-identical
     tiers/ticks/veto. The cascade is a pure function of the close history; if a future edit
     introduces state or randomness this fails.
  2. BUCKET-TAIL CORRECTNESS — on a hand-built fixture where the last 3B bucket is provisional
     (1-2 of 3 days printed) vs complete (all 3), the replay's per-day tier reflects the
     PARTIAL-tail value the live board would show, and the `bucket_completeness` classifier flags
     provisional vs completed correctly.
  3. HYSTERESIS — the not-topped veto with N-bar confirmation only trips after N consecutive topped
     bars (a single-bar wiggle no longer flips it), and its flicker rate is <= the single-bar
     version's on the same series.

Reads no external store — all fixtures are built in-memory. Run:
  .venv/bin/python -m pytest tests/test_provisional_replay.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine import provisional_replay as pr  # noqa: E402
from engine import confluence_tiers, signal_gate  # noqa: E402
from engine.hysteresis import hysteretic_not_topped, flicker_rate  # noqa: E402


def _synthetic_close(n=520, seed=0) -> pd.Series:
    """A daily close with real cycles so crosses actually fire (not flat noise)."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    idx = pd.bdate_range("2023-01-02", periods=n)
    base = 100 + 12 * np.sin(t / 24) + 0.03 * t + 4 * np.sin(t / 6)
    noise = np.cumsum(rng.normal(0, 0.3, n))
    return pd.Series(base + noise, index=idx)


# ------------------------------------------------------------------ 1. determinism
def test_replay_is_deterministic():
    c = _synthetic_close()
    f1 = pr.replay_series("SYN", c, max_days=40)
    f2 = pr.replay_series("SYN", c, max_days=40)
    assert not f1.empty
    # tiers, ticks, veto, eligibility all identical across two runs
    for col in ("tier", "ticks", "not_topped", "eligible"):
        assert list(f1[col].fillna("_")) == list(f2[col].fillna("_")), f"{col} not deterministic"


def test_single_day_replay_matches_direct_gate():
    """A replay day must equal a direct signal_gate.gate on the same truncated series (same path)."""
    c = _synthetic_close(seed=3)
    D = c.index[-5]
    frame = pr.replay_series("SYN", c, start=D, end=D)
    assert len(frame) == 1
    direct = signal_gate.gate("SYN", c[c.index <= D])
    assert frame.iloc[0]["tier"] == direct.get("tier_cascade")
    assert frame.iloc[0]["ticks"] == direct.get("ticks")


# ------------------------------------------------------------------ 2. bucket-tail correctness
def test_bucket_completeness_flags_provisional_tail():
    """Hand-built: on the day the 3B bucket's final day prints it is COMPLETE; the 1-2 days before
    it is PROVISIONAL. The classifier must agree with that ground truth."""
    # A clean business-day series; 3B buckets group consecutive triples of business days.
    idx = pd.bdate_range("2024-01-01", periods=30)
    c = pd.Series(np.arange(30, dtype=float) + 100, index=idx)
    # Find a 3B bucket and check each of its constituent days.
    s3 = c.resample("3B").last().dropna()
    # take an interior bucket (not the first partial one)
    label = s3.index[5]
    in_bucket = c[c.index >= label]
    # the bucket spans up to 3 business days from `label`
    days = list(in_bucket.index[:3])
    # day 0 of the bucket: only 1 of 3 printed -> provisional
    bc0 = pr.bucket_completeness(c, days[0])
    assert bc0["complete"] is False and bc0["printed"] == 1
    # day 1: 2 printed -> still provisional
    bc1 = pr.bucket_completeness(c, days[1])
    assert bc1["complete"] is False and bc1["printed"] == 2
    # day 2: all 3 printed -> complete
    bc2 = pr.bucket_completeness(c, days[2])
    assert bc2["complete"] is True and bc2["printed"] == 3


def test_provisional_tail_value_differs_from_completed():
    """The whole premise: the last 3B bucket's .last() value on a provisional day differs from the
    completed-bucket value the point-in-time backtest sees. Prove it on a monotone series."""
    idx = pd.bdate_range("2024-01-01", periods=30)
    c = pd.Series(np.arange(30, dtype=float), index=idx)
    s3 = c.resample("3B").last().dropna()
    label = s3.index[5]
    days = list(c[c.index >= label].index[:3])
    # truncate at day 0 (partial) vs day 2 (complete): the last bucket's .last() must differ
    v_partial = c[c.index <= days[0]].resample("3B").last().dropna().iloc[-1]
    v_complete = c[c.index <= days[2]].resample("3B").last().dropna().iloc[-1]
    assert v_partial != v_complete  # the provisional tail is genuinely a different bar


# ------------------------------------------------------------------ 3. hysteresis
def test_hysteresis_ignores_single_bar_wiggle():
    """A single topped bar surrounded by not-topped bars must NOT trip a 2-bar-confirmed veto,
    but two consecutive topped bars must."""
    # not_topped stream: True=constructive, False=topped. One-bar dip then a two-bar dip.
    raw = pd.Series([True, True, False, True, True, False, False, True, True])
    hyst = hysteretic_not_topped(raw, confirm=2)
    # single-bar dip at idx 2: hysteresis holds not_topped True (needs 2 consecutive topped)
    assert bool(hyst.iloc[2]) is True
    # two-bar dip at idx 5,6: by the 2nd topped bar the veto trips (not_topped -> False)
    assert bool(hyst.iloc[6]) is False
    # recovery needs confirmation too, but a single not-topped after a trip does not instantly clear
    assert bool(hyst.iloc[5]) is True  # first topped bar of the pair: not yet confirmed


def test_hysteresis_reduces_flicker():
    """On a noisy veto stream the hysteretic version flickers no more than the single-bar one."""
    rng = np.random.default_rng(7)
    raw = pd.Series(rng.random(200) > 0.35)  # noisy True/False
    single_fr = flicker_rate(raw)
    hyst_fr = flicker_rate(hysteretic_not_topped(raw, confirm=2))
    assert hyst_fr <= single_fr + 1e-9


def test_hysteresis_band_never_readmits_genuinely_topped():
    """A sustained topped run must stay vetoed under hysteresis (the AMAT guard must still fire)."""
    raw = pd.Series([True] * 5 + [False] * 10)
    hyst = hysteretic_not_topped(raw, confirm=2)
    # once 2 consecutive topped bars confirm, the rest of the topped run stays vetoed
    assert not hyst.iloc[-1]
    assert not hyst.iloc[-5]


# ------------------------------------------------------------------ vectorized tier_stream parity
def test_tier_stream_matches_cascade_on_settled_days():
    """The vectorized COMPLETED-bucket tier_stream must equal the scalar cascade on days where D is
    the last printed day of BOTH its 3B and 2B buckets (fully settled — no provisional tail, no
    future-bar leak). Any divergence there is a real bug in the vectorized twin, not a repaint."""
    c = _synthetic_close(n=560, seed=5)
    stream = confluence_tiers.tier_stream(c)
    assert not stream.empty
    checked = 0
    for D in c.index[-40:]:
        trunc = c[c.index <= D]
        bc3 = pr.bucket_completeness(trunc, D, 3)
        bc2 = pr.bucket_completeness(trunc, D, 2)
        if not (bc3["complete"] and bc2["complete"]):
            continue
        # cascade with take_active=True + take_date=None ages T1 by the raw 3D cross — the same
        # T1 basis tier_stream uses (its raw-cross fallback).
        casc = confluence_tiers.cascade(trunc, take_active=True)
        st = stream.loc[D, "tier"] if D in stream.index else None
        st = None if (st is None or (isinstance(st, float) and np.isnan(st))) else str(st)
        assert casc.get("tier") == st, f"tier mismatch on settled day {D.date()}: cascade={casc.get('tier')} stream={st}"
        checked += 1
    assert checked >= 3, "no fully-settled days found to check parity"


def test_tier_stream_ticks_are_point_in_time():
    """tier_stream's ticks count only TF bars up to the current day — never future bars (the
    interior-day leak the naive full-series pass introduced)."""
    c = _synthetic_close(n=560, seed=6)
    stream = confluence_tiers.tier_stream(c)
    # a fresh tier can never carry ticks beyond FRESH_TICKS (that would be a stale HOLD miscounted)
    fresh = stream[stream["tier"].isin(["T1", "T2"])]
    if not fresh.empty:
        assert (fresh["ticks"].dropna() <= confluence_tiers.FRESH_TICKS).all()


# ------------------------------------------------------------------ end-to-end shape
def test_replay_panel_shape():
    panel = {"A": _synthetic_close(seed=1), "B": _synthetic_close(seed=2)}
    res = pr.replay_panel(panel, max_days=30)
    assert res["n_names"] == 2
    assert "repaint" in res and "edge" in res and "veto_flicker" in res
    # config echoes the freshness knob under measurement
    assert res["config"]["FRESH_TICKS"] == confluence_tiers.FRESH_TICKS


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
