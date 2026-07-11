"""Tests for engine.theme_scoring leadership-split disclosure fields (ruling M7C-R4).

Verifies:
  - A 7-member basket with 2 strong leaders (+8%) and poor breadth (r20_rel -0.3%)
    still labels "deteriorating" and reco "avoid" (NO behavior change) AND now
    surfaces leadership_split=True with the leaders list.
  - A 50-member basket correctly suppresses leadership_split (member_count > 12).
  - The note strings are present and non-empty when split is True.
  - The note fields are None when split is False.

No network calls; all inputs are synthetic fixtures.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import theme_scoring as ts


# --------------------------------------------------------------------------- helpers

def _make_lead(top_rets: list[float]) -> dict:
    """Build a synthetic leadership dict as returned by group_flow._leadership."""
    tickers = [f"T{i}" for i in range(len(top_rets))]
    n = len(top_rets)
    tot = sum(abs(r) for r in top_rets) or 1.0
    top = [
        {"ticker": t, "name": t, "ret_20d": r, "share": abs(r) / tot, "alpha": None}
        for t, r in zip(tickers, top_rets)
    ]
    hhi = sum((abs(r) / tot) ** 2 for r in top_rets) if tot > 0 else 0.0
    return {
        "top": top,
        "hhi": round(hhi, 3),
        "n": n,
        "breadth": "narrow" if hhi > 2.5 / n else "broad",
    }


def _fp_deteriorating():
    """Fingerprint that reproduces the deteriorating label for a 7-member basket."""
    return {"accel_z": -0.7, "rs_pctile": 0.4}


# --------------------------------------------------------------------------- task 1: label/reco unchanged

def test_label_still_deteriorating_with_leaders():
    """Core regression: the presence of strong leaders does NOT change label or reco."""
    fp = _fp_deteriorating()
    perf = {"20d": {"rel": -0.003}, "5d": {"rel": -0.002}, "60d": {"rel": -0.01}}
    breadth_d = {"pct50": 0.286, "pct200": 0.4, "nh": 0, "nl": 2, "n": 7}
    delta_5d = -0.002
    label = ts._label(40, fp, perf, breadth_d, delta_5d)
    assert label == "deteriorating", f"expected deteriorating, got {label!r}"
    reco = ts._reco(label, 0.0, 0.1, fp)
    assert reco == "avoid", f"expected avoid, got {reco!r}"


# --------------------------------------------------------------------------- task 2: leadership_split True

def test_leadership_split_true_seven_members():
    """7-member basket, top-2 at +8%: leadership_split should be True."""
    lead = _make_lead([0.088, 0.081, -0.02, -0.05, -0.03, -0.01, 0.0])
    fields = ts._leadership_split_fields(n_members=7, lead=lead, label="deteriorating")
    assert fields["leadership_split"] is True
    assert len(fields["leaders"]) >= 2
    # returned leaders use "symbol" key (not "ticker")
    for ldr in fields["leaders"]:
        assert "symbol" in ldr and "ret_20d" in ldr
    # notes are present and non-empty
    assert fields["leadership_split_note_en"]
    assert fields["leadership_split_note_zh"]
    # sanity: at least the first two leaders (the ones that triggered the split) are positive
    assert fields["leaders"][0]["ret_20d"] > 0
    assert fields["leaders"][1]["ret_20d"] > 0


def test_leadership_split_true_for_fading_label():
    """Fading label also triggers split disclosure."""
    lead = _make_lead([0.09, 0.07, -0.02, -0.01])
    fields = ts._leadership_split_fields(n_members=4, lead=lead, label="fading")
    assert fields["leadership_split"] is True


def test_leadership_split_true_for_neutral_label():
    """Neutral label also triggers split disclosure."""
    lead = _make_lead([0.10, 0.08, 0.0, -0.01])
    fields = ts._leadership_split_fields(n_members=6, lead=lead, label="neutral")
    assert fields["leadership_split"] is True


# --------------------------------------------------------------------------- task 3: leadership_split False

def test_leadership_split_false_fifty_members():
    """50-member basket: member_count > 12 suppresses split regardless of leaders."""
    lead = _make_lead([0.12, 0.09, -0.01, -0.02])
    fields = ts._leadership_split_fields(n_members=50, lead=lead, label="deteriorating")
    assert fields["leadership_split"] is False
    assert fields["leaders"] == []
    assert fields["leadership_split_note_en"] is None
    assert fields["leadership_split_note_zh"] is None


def test_leadership_split_false_dominant_label():
    """Dominant label does not trigger split (only deteriorating/fading/neutral do)."""
    lead = _make_lead([0.15, 0.10, 0.05])
    fields = ts._leadership_split_fields(n_members=7, lead=lead, label="dominant")
    assert fields["leadership_split"] is False
    assert fields["leaders"] == []


def test_leadership_split_false_weak_leaders():
    """Top-2 mean ret_20d < 5%: split is False even on a small basket."""
    lead = _make_lead([0.03, 0.02, -0.05, -0.04, -0.03, 0.0, 0.0])
    fields = ts._leadership_split_fields(n_members=7, lead=lead, label="deteriorating")
    assert fields["leadership_split"] is False


def test_leadership_split_false_thirteen_members():
    """13 members (just over the 12-member threshold) suppresses split."""
    lead = _make_lead([0.12, 0.09] + [-0.01] * 5)
    fields = ts._leadership_split_fields(n_members=13, lead=lead, label="deteriorating")
    assert fields["leadership_split"] is False


# --------------------------------------------------------------------------- task 4: exact scenario from brief

def test_mag7_scenario_from_brief():
    """Reproduce the exact mag7 context from the brief:
    - 7 members, pct50=0.286 (<0.4 → 'breaking'), r20_rel=-0.003%
    - AAPL+8.8% / META+8.1% (leaders)
    - Expect: label=deteriorating, reco=avoid, leadership_split=True
    """
    # Step 1: label/reco check (independent of leadership_split)
    fp = {"accel_z": -0.26, "rs_pctile": 0.45}
    perf_d = {"20d": {"rel": -0.0026}, "5d": {"rel": -0.001}, "60d": {"rel": 0.0}}
    breadth_d = {"pct50": 0.286, "pct200": 0.43, "nh": 0, "nl": 1, "n": 7}
    label = ts._label(38, fp, perf_d, breadth_d, delta_5d=-0.001)
    assert label == "deteriorating", f"label={label!r}"
    reco = ts._reco(label, 0.0, 0.2, fp)
    assert reco == "avoid", f"reco={reco!r}"

    # Step 2: leadership_split fields
    lead = _make_lead([0.088, 0.081, -0.03, -0.04, -0.02, 0.01, 0.0])
    fields = ts._leadership_split_fields(n_members=7, lead=lead, label=label)
    assert fields["leadership_split"] is True, "expected split=True for the mag7 scenario"
    assert len(fields["leaders"]) >= 2
    # The two leaders should be the ones with positive rets
    pos_leaders = [l for l in fields["leaders"] if l["ret_20d"] is not None and l["ret_20d"] > 0]
    assert len(pos_leaders) >= 2


# --------------------------------------------------------------------------- task 5: baskets HORIZONS 10d key

def test_baskets_horizons_contains_10d():
    """engine.baskets.HORIZONS must include the new '10d' key."""
    from engine.baskets import HORIZONS
    assert "10d" in HORIZONS
    assert HORIZONS["10d"] == 10


def test_baskets_perf_includes_10d():
    """_perf() output must include '10d' after adding it to HORIZONS."""
    from engine.baskets import _perf, _mtd_anchor, HORIZONS
    idx = pd.date_range("2024-01-01", periods=80, freq="B")
    lvl = pd.Series(np.linspace(1.0, 1.2, 80), index=idx)
    bench = pd.Series(np.linspace(1.0, 1.1, 80), index=idx)
    ytd_anchor = idx[0]
    mtd_anchor = _mtd_anchor(idx)
    result = _perf(lvl, bench, idx, ytd_anchor, mtd_anchor)
    assert "10d" in result, f"expected '10d' in perf; keys={list(result)}"
    assert "ret" in result["10d"] and "rel" in result["10d"]


def test_baskets_default_sort_still_uses_20d():
    """Adding '10d' must not change the default 20d-rel sort in compute_baskets.
    This is a structural check — the sort key is a literal '20d' string in the code."""
    from engine import baskets
    import inspect
    src = inspect.getsource(baskets.compute_baskets)
    assert '"20d"' in src, "expected the 20d sort key to remain in compute_baskets"
    # Ensure the theme_scoring perf snapshot still excludes 10d (its own dict literal)
    src_ts = inspect.getsource(ts.compute_theme_intel)
    # theme_scoring explicitly picks ("5d", "20d", "60d", "ytd") — not "10d"
    assert '"10d"' not in src_ts or '("5d", "20d", "60d", "ytd")' in src_ts
