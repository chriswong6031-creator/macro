"""Lane gate for the sector-ignition forward ledgers (engine/ignition_audit.py).

House law: nightly is the SOLE advancer of data/ forward ledgers. The ignition
appender call sites also run on closing-bell (COLLECT_LANE deliberately UNSET —
that lane's contract is that every ledger writer self-gates) and the
engine-render/render re-render lanes; appends are idempotent-by-(asof, basket)
with FIRST-WRITER-WINS, so an ungated off-lane append would permanently displace
the nightly row. Mirrors tests/test_risk_radar_intl_profiles.py's ledger-lane
tests for the #2684 intl-radar gate.

NOTE tests/conftest.py arms COLLECT_LANE=nightly autouse — off-lane cases must
pop BOTH env vars explicitly.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from engine import ignition_audit as ia

ROOT = Path(__file__).resolve().parent.parent


def _snap(asof="2026-07-16", items=None):
    return {
        "as_of": asof,
        "market": "hk",
        "items": items if items is not None else [
            {"id": "b1", "name": "B1", "ignition_score": 0.7, "state": "igniting"},
        ],
    }


def _us_snap(asof="2026-07-16"):
    return {
        "as_of": asof,
        "state": "confirmed",
        "k_count": 5,
        "chips": [],
        "regime": {"fragile": False, "label_en": "calm"},
        "narrow": {"items": []},
    }


def _offlane(monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1: env matrix — same contract as intl_run._ledger_lane_armed (#2684)
# ═══════════════════════════════════════════════════════════════════════════

def test_ignition_ledger_lane_armed_env_matrix(monkeypatch):
    cases = [
        ({}, False),                                          # both absent
        ({"COLLECT_LANE": "nightly"}, True),                  # nightly collect lane
        ({"COLLECT_LANE": "intraday"}, False),                # intraday lane
        ({"US_LANE": "nightly"}, True),                       # legacy alias
        ({"COLLECT_LANE": "", "US_LANE": "nightly"}, True),   # empty falls through to alias
    ]
    for env, expected in cases:
        _offlane(monkeypatch)
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        assert ia.ledger_lane_armed() is expected, (
            f"ledger_lane_armed() with {env} != {expected}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2: per-market appender (HK/CA arm) — off-lane no-op, on-lane appends
# ═══════════════════════════════════════════════════════════════════════════

def test_market_log_snapshot_lane_gated(tmp_path, monkeypatch):
    _offlane(monkeypatch)
    assert ia.log_snapshot(_snap(), "hk", root=tmp_path) == 0, (
        "off-lane log_snapshot must no-op (house law: nightly is the sole advancer)"
    )
    p = tmp_path / "data" / "ignition_log" / "hk_ignition.jsonl"
    assert not p.exists() or p.read_text().strip() == "", (
        "off-lane log_snapshot must not write ledger rows"
    )

    monkeypatch.setenv("COLLECT_LANE", "nightly")
    assert ia.log_snapshot(_snap(), "hk", root=tmp_path) == 1
    assert ia.log_snapshot(_snap(), "hk", root=tmp_path) == 0   # idempotent by (asof, basket)


def test_offlane_snapshot_cannot_displace_nightly_row(tmp_path, monkeypatch):
    """The actual #2684 hazard: appends are first-writer-wins, so an off-lane call
    with a NEW asof must not claim the day's row ahead of the nightly."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    assert ia.log_snapshot(_snap("2026-07-15"), "hk", root=tmp_path) == 1

    _offlane(monkeypatch)
    early = _snap("2026-07-16", [
        {"id": "b1", "name": "B1", "ignition_score": 0.2, "state": "quiet"},
    ])
    assert ia.log_snapshot(early, "hk", root=tmp_path) == 0

    monkeypatch.setenv("COLLECT_LANE", "nightly")
    assert ia.log_snapshot(_snap("2026-07-16"), "hk", root=tmp_path) == 1
    rows = [json.loads(l) for l in
            (tmp_path / "data" / "ignition_log" / "hk_ignition.jsonl").read_text().splitlines()]
    today = [r for r in rows if r["asof"] == "2026-07-16"]
    assert len(today) == 1 and today[0]["state"] == "igniting", (
        "the nightly row must own the asof — off-lane snapshot displaced it"
    )


def test_market_grade_log_lane_gated(tmp_path, monkeypatch):
    """Grades are keep-first-permanent — off-lane grade_log must not write them."""
    idx = pd.bdate_range("2026-01-02", periods=60)
    lvl = pd.Series(np.linspace(100.0, 120.0, 60), index=idx)     # basket beats...
    bench = pd.Series(100.0, index=idx)                            # ...a flat bench
    asof = str(idx[5].date())

    monkeypatch.setenv("COLLECT_LANE", "nightly")
    assert ia.log_snapshot(_snap(asof), "hk", root=tmp_path) == 1

    _offlane(monkeypatch)
    assert ia.grade_log("hk", level_of=lambda b: lvl, bench_series=bench, root=tmp_path) == 0
    p = tmp_path / "data" / "ignition_log" / "hk_ignition.jsonl"
    assert json.loads(p.read_text().splitlines()[0])["graded"] is None, (
        "off-lane grade_log must leave matured rows ungraded"
    )

    monkeypatch.setenv("COLLECT_LANE", "nightly")
    assert ia.grade_log("hk", level_of=lambda b: lvl, bench_series=bench, root=tmp_path) == 1
    g = json.loads(p.read_text().splitlines()[0])["graded"]
    assert g["outcome"] == "true_positive"


def test_snapshot_and_grade_offlane_is_readonly_but_populates_display(tmp_path, monkeypatch):
    """The read-only path: off-lane snapshot_and_grade still returns the scorecard
    (scoreboard display populated) without creating/advancing the ledger."""
    _offlane(monkeypatch)
    sc = ia.snapshot_and_grade(_snap(), "hk",
                               level_of=lambda b: None, bench_series=None, root=tmp_path)
    assert isinstance(sc, dict) and sc.get("market") == "hk"
    assert sc.get("n_logged_today") == 0
    assert "note" in sc or "n_graded" in sc, "display payload must stay populated off-lane"
    assert not (tmp_path / "data" / "ignition_log" / "hk_ignition.jsonl").exists(), (
        "off-lane snapshot_and_grade must not create the ledger"
    )


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3: US arm — log_us_snapshot / grade_us_log / us_snapshot_and_grade
# ═══════════════════════════════════════════════════════════════════════════

def test_us_arm_lane_gated(tmp_path, monkeypatch):
    _offlane(monkeypatch)
    assert ia.log_us_snapshot(_us_snap(), root=tmp_path) == 0
    assert not (tmp_path / "data" / "ignition_log" / "us_ignition.jsonl").exists()

    idx = pd.bdate_range("2026-01-02", periods=200)
    spy = pd.Series(np.linspace(400.0, 440.0, 200), index=idx)
    assert ia.grade_us_log(spy, root=tmp_path) == 0

    sc = ia.us_snapshot_and_grade(_us_snap(), spy, root=tmp_path)
    assert isinstance(sc, dict) and sc.get("market") == "us" and "note" in sc, (
        "off-lane us_snapshot_and_grade must still return the display scorecard"
    )
    assert not (tmp_path / "data" / "ignition_log" / "us_ignition.jsonl").exists()

    monkeypatch.setenv("COLLECT_LANE", "nightly")
    assert ia.log_us_snapshot(_us_snap(), root=tmp_path) == 1
    assert ia.log_us_snapshot(_us_snap(), root=tmp_path) == 0    # idempotent by asof


# ═══════════════════════════════════════════════════════════════════════════
# TEST 4: source tripwires — writers stay gated; asia-close stays armed for HK
# ═══════════════════════════════════════════════════════════════════════════

def test_ignition_writers_self_gate_source():
    """Every mutating writer must check ledger_lane_armed() before touching the
    ledger (the closing-bell.yml contract: COLLECT_LANE is deliberately unset
    there BECAUSE every ledger writer self-gates)."""
    src = (ROOT / "engine" / "ignition_audit.py").read_text(encoding="utf-8")
    for fn in ("def log_snapshot", "def grade_log",
               "def log_us_snapshot", "def grade_us_log"):
        start = src.index(fn)
        nxt = src.find("\ndef ", start + 1)
        body = src[start: nxt if nxt != -1 else len(src)]
        assert "ledger_lane_armed()" in body, f"{fn} is not lane-gated"


def test_asia_close_arms_hk_baskets_lane():
    """asia-close is the HK ignition ledger's advancing lane (it is the only
    fresh-HKEX lane that commits data/) but sets no job-level COLLECT_LANE —
    the gate is armed inline on the build_baskets_hk invocation. Removing that
    arm silently FREEZES data/ignition_log/hk_ignition.jsonl (frozen-ledger
    class, cf. #2659/#2690)."""
    src = (ROOT / ".github" / "workflows" / "asia-close.yml").read_text(encoding="utf-8")
    lines = [l for l in src.splitlines()
             if "scripts.build_baskets_hk" in l and not l.strip().startswith("#")]
    assert lines, "asia-close.yml no longer invokes scripts.build_baskets_hk?"
    for line in lines:
        assert "COLLECT_LANE=nightly" in line, (
            "asia-close's build_baskets_hk invocation must arm COLLECT_LANE=nightly "
            "inline or the HK ignition forward ledger freezes"
        )
