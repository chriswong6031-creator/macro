"""Tests for the EXIT-CROWD Phase-0 L4 interim runner (roadmap P4.4a).

Covers the prereg-mandated invariants:
  - fire detection on synthetic flow series (divergence + flow-cross-below-0)
  - placebo exclusion-zone honoured (§5)
  - base-rate comparison sign convention (exhaustion = more-negative excess)
  - PIT: no future snapshot reads in the flow reconstruction
  - L1-L3 stubs hard-fail while the thetadata manifest is incomplete (R8/§8.11)
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import scripts.run_exit_crowding_phase0 as rc


# ---------------------------------------------------------------------------
# Fire detection
# ---------------------------------------------------------------------------
def test_fire_detection_divergence_and_cross():
    # Synthetic flow-by-date for one theme "T".
    d1, d2, d3 = date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)
    flow = {
        # d1: positive flow, no fire
        d1: {"T": {"flow_score": 0.5, "divergence": False, "n_covered": 5, "n_members": 10}},
        # d2: flow crosses below 0 (prev >=0, now <0), coverage ok -> FIRE (cross)
        d2: {"T": {"flow_score": -0.3, "divergence": False, "n_covered": 5, "n_members": 10}},
        # d3: divergence True -> FIRE (divergence)
        d3: {"T": {"flow_score": -0.4, "divergence": True, "n_covered": 5, "n_members": 10}},
    }
    fires = rc.detect_fires(flow)
    kinds = {(f["as_of"], f["kind"]) for f in fires}
    assert ("2026-01-02", "flow_cross_below_0") in kinds
    assert ("2026-01-03", "divergence") in kinds
    assert ("2026-01-01", "flow_cross_below_0") not in kinds  # positive flow never fires
    assert len(fires) == 2


def test_fire_detection_coverage_gate():
    # Below coverage threshold (n_covered/n_members < 0.10) -> no fire even with div flag.
    d1, d2 = date(2026, 1, 1), date(2026, 1, 2)
    flow = {
        d1: {"T": {"flow_score": 0.5, "divergence": False, "n_covered": 1, "n_members": 100}},
        d2: {"T": {"flow_score": -0.3, "divergence": True, "n_covered": 1, "n_members": 100}},
    }
    fires = rc.detect_fires(flow)
    assert fires == []


def test_fire_no_cross_when_prev_already_negative():
    # flow already negative on d1 -> d2 negative is NOT a fresh cross.
    d1, d2 = date(2026, 1, 1), date(2026, 1, 2)
    flow = {
        d1: {"T": {"flow_score": -0.2, "divergence": False, "n_covered": 5, "n_members": 10}},
        d2: {"T": {"flow_score": -0.3, "divergence": False, "n_covered": 5, "n_members": 10}},
    }
    fires = rc.detect_fires(flow)
    assert fires == []


# ---------------------------------------------------------------------------
# Base-rate comparison sign convention (§2.3)
# ---------------------------------------------------------------------------
def test_base_rate_sign_convention():
    # Build a sector level series and SPY so the theme's forward 21d excess is negative.
    idx = pd.bdate_range("2026-01-01", periods=60)
    # sector flat, SPY rising -> negative excess (exhaustion payoff)
    sector = pd.Series(100.0, index=idx)
    spy = pd.Series(np.linspace(100.0, 110.0, len(idx)), index=idx)
    levels = {"XLK": sector}
    theme_to_sector = {"T": "XLK"}
    exc = rc.forward_excess(theme_to_sector, date(2026, 1, 1), "T", levels, spy, 21)
    assert exc is not None
    assert exc < 0, "sector flat vs rising SPY must yield a NEGATIVE forward excess"

    # delta vs SELL base rate: more-negative than -1.24 => sharpens
    base = -1.24
    delta = exc - base
    sharpens = delta < 0
    # our fabricated excess is strongly negative -> should sharpen
    assert sharpens is True


def test_forward_excess_not_matured_returns_none():
    idx = pd.bdate_range("2026-01-01", periods=10)  # only 10 days, need 21
    levels = {"XLK": pd.Series(100.0, index=idx)}
    spy = pd.Series(100.0, index=idx)
    exc = rc.forward_excess({"T": "XLK"}, date(2026, 1, 1), "T", levels, spy, 21)
    assert exc is None


# ---------------------------------------------------------------------------
# Placebo exclusion-zone (§5)
# ---------------------------------------------------------------------------
def test_placebo_exclusion_zone():
    # 40 consecutive theme-days for theme "T"; a real fire on index 20.
    dates = list(pd.bdate_range("2026-01-01", periods=40).date)
    flow_by_date = {}
    for i, d in enumerate(dates):
        flow_by_date[d] = {"T": {"flow_score": 0.1, "divergence": False,
                                 "n_covered": 5, "n_members": 10}}
    fire_date = dates[20]
    fires = [{"as_of": fire_date.isoformat(), "theme_id": "T",
              "kind": "divergence", "flow_score": -0.3, "n_covered": 5, "n_members": 10}]

    # sector level + SPY long enough to mature every candidate
    full_idx = pd.bdate_range("2026-01-01", periods=120)
    levels = {"XLK": pd.Series(np.linspace(100, 90, len(full_idx)), index=full_idx)}
    spy = pd.Series(np.linspace(100, 110, len(full_idx)), index=full_idx)
    theme_to_sector = {"T": "XLK"}
    rng = np.random.default_rng(0)

    pl = rc.build_placebo(flow_by_date, fires, theme_to_sector, levels, spy,
                          21, -1.24, rng)
    # candidate non-event days must EXCLUDE the fire day and its +/-10 index neighbours.
    # Total theme-days = 40; excluded = fire +/-10 => indices 10..30 (21 days) removed;
    # also days without a matured 21d forward are removed. Assert exclusion happened:
    assert pl["n_candidate_nonevent_days"] <= 40 - 21, (
        "exclusion_zone=10 must remove the fire day and its +/-10 neighbours")
    assert pl["exclusion_zone"] == 10
    assert pl["draws"] == 200


def test_placebo_insufficient_flagged():
    # No candidates at all -> insufficient_placebo True.
    d1 = date(2026, 1, 1)
    flow_by_date = {d1: {"T": {"flow_score": -0.3, "divergence": True,
                               "n_covered": 5, "n_members": 10}}}
    fires = [{"as_of": d1.isoformat(), "theme_id": "T", "kind": "divergence",
              "flow_score": -0.3, "n_covered": 5, "n_members": 10}]
    idx = pd.bdate_range("2026-01-01", periods=5)
    levels = {"XLK": pd.Series(100.0, index=idx)}
    spy = pd.Series(100.0, index=idx)
    rng = np.random.default_rng(0)
    pl = rc.build_placebo(flow_by_date, fires, {"T": "XLK"}, levels, spy, 21, -1.24, rng)
    assert pl["insufficient_placebo"] is True


# ---------------------------------------------------------------------------
# PIT: no future snapshot reads
# ---------------------------------------------------------------------------
def test_pit_no_future_snapshots(tmp_path, monkeypatch):
    """reconstruct_flow_pit must only expose snapshots dated <= as_of to theme_flow.

    We stub engine.theme_flow_rollup.theme_flow to capture which snapshot dates are
    visible under the repointed config.data_dir, and assert none are > as_of.
    """
    # Build a fake etf_holdings store with dated snapshots spanning past+future.
    data = tmp_path / "data"
    ehold = data / "etf_holdings"
    ehold.mkdir(parents=True)
    xlk = ehold / "BETZ"
    xlk.mkdir()
    snap_dates = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"]
    df = pd.DataFrame({"ticker": ["AAA", "BBB"], "shares": [100, 200], "weight_pct": [1.0, 2.0]})
    for d in snap_dates:
        df.to_parquet(xlk / f"{d}.parquet")
    # a non-holdings sibling dir that must be symlinked through
    (data / "baskets").mkdir()
    (data / "baskets" / "membership.json").write_text("{}")

    from engine import theme_flow_rollup as tfr
    from lib import config as engcfg

    seen_dates = {}

    def fake_theme_flow(region="us"):
        # inspect what config.data_dir() currently points at
        dd = engcfg.data_dir()
        visible = sorted(p.stem for p in (dd / "etf_holdings" / "BETZ").glob("*.parquet"))
        seen_dates["visible"] = visible
        return {}

    monkeypatch.setattr(tfr, "theme_flow", fake_theme_flow)

    as_of = date(2026, 1, 3)
    rc.reconstruct_flow_pit(ehold, as_of)
    visible = seen_dates.get("visible", [])
    assert visible, "flow reconstruction exposed no snapshots"
    for v in visible:
        assert v <= "2026-01-03", f"FUTURE snapshot {v} leaked past as_of {as_of}"
    assert "2026-01-04" not in visible and "2026-01-05" not in visible


# ---------------------------------------------------------------------------
# L1-L3 stubs hard-fail while manifest incomplete (R8 / §8.11)
# ---------------------------------------------------------------------------
def test_l1_l3_stub_blocks_on_incomplete_manifest(tmp_path):
    # empty manifest (n_roots=0, updated_at=null) -> SystemExit
    root = tmp_path
    (root / "data" / "thetadata_eod").mkdir(parents=True)
    (root / "data" / "thetadata_eod" / "_manifest.json").write_text(
        json.dumps({"store": "thetadata_eod", "n_roots": 0, "per_root": {}, "updated_at": None}))
    with pytest.raises(SystemExit) as ei:
        rc.run_l1_l2_l3_stub("L1", root)
    assert "BLOCKED" in str(ei.value)


def test_l1_l3_stub_blocks_on_missing_manifest(tmp_path):
    with pytest.raises(SystemExit) as ei:
        rc.run_l1_l2_l3_stub("L2", tmp_path)
    assert "BLOCKED" in str(ei.value)


def test_manifest_complete_detection(tmp_path):
    (tmp_path / "data" / "thetadata_eod").mkdir(parents=True)
    (tmp_path / "data" / "thetadata_eod" / "_manifest.json").write_text(
        json.dumps({"store": "thetadata_eod", "n_roots": 360,
                    "per_root": {}, "updated_at": "2026-08-01T00:00:00Z"}))
    ok, info = rc._manifest_complete(tmp_path)
    assert ok is True
    assert info["n_roots"] == 360


# ---------------------------------------------------------------------------
# Live SELL base-rate stamp
# ---------------------------------------------------------------------------
def test_live_sell_base_rate_stamped():
    br = rc.read_live_sell_base_rate()
    assert "exc63" in br and "n" in br
    assert br["_source"].startswith("engine.sector_signals")
    assert "_stamped_at" in br
