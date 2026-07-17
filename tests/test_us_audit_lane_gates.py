"""Lane gates for the three US forward-ledger audit modules (port of the #2693
ignition_audit gate).

House law: nightly is the SOLE advancer of data/ forward ledgers. All three
ledgers' only advancing lane is daily.yml's engine job (job-level
COLLECT_LANE=nightly — every advancing commit is "engine: regime update"):

  engine/risk_radar_audit.py          data/risk_radar/forward_log.jsonl
  engine/risk_radar_recovery_audit.py data/risk_radar/recovery_log.jsonl
  engine/market_state_audit.py        data/market_state/forward_log.jsonl

Their call sites (engine/run.py; scripts/build_site.py market_state_view) also
run on closing-bell (COLLECT_LANE deliberately UNSET — that lane's contract is
that every ledger writer self-gates) and the engine-render/render re-render
lanes; appends are idempotent-by-asof with FIRST-WRITER-WINS, so an ungated
off-lane append would permanently displace the nightly row. Mirrors
tests/test_ignition_lane_gate.py.

NOTE tests/conftest.py arms COLLECT_LANE=nightly autouse — off-lane cases must
pop BOTH env vars explicitly.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine import market_state_audit as msa
from engine import risk_radar_audit as rra
from engine import risk_radar_recovery_audit as rrra

ROOT = Path(__file__).resolve().parent.parent

MODULES = (rra, rrra, msa)
MODULE_IDS = ("risk_radar", "recovery", "market_state")

LEDGER_REL = {
    rra: Path("risk_radar") / "forward_log.jsonl",
    rrra: Path("risk_radar") / "recovery_log.jsonl",
    msa: Path("market_state") / "forward_log.jsonl",
}


def _radar_snap(asof="2026-07-16", state="elevated"):
    return {
        "asof": asof, "state": state, "alert": state in rra.ALERT_STATES,
        "dominant_scare": "credit", "top_score": 55,
        "scares": [{"scare": "credit", "score": 55, "band": "elevated"}],
        "drawdown_prob": {"conjunction_n": 1},
    }


def _recovery(asof="2026-07-16"):
    return {
        "asof": asof, "n_fresh": 1, "turn_confirmed_full": False,
        "market": {
            "chips": [{"key": "breadth_thrust", "fired": True, "fresh": True}],
            "veto": {"active": False, "p_now": 0.1},
            "market_confirmed": False,
            "morphology": {"shape": "grinding"},
        },
    }


def _recovery_radar(phase="receding"):
    return {"trajectory": {"phase": phase, "intensity": 0.4}}


def _ms_snap(asof="2026-07-16", verdict="RISK_OFF"):
    return {
        "asof": asof, "verdict": verdict, "score": 25, "raw_score": 30,
        "radar": {"state": "risk-off", "top_score": 70, "amp": 1.2,
                  "amp_keys": ["conjunction"], "severe_gated": False},
    }


def _log(mod, asof, root) -> bool:
    """Call the module's log_snapshot with a minimal valid snapshot."""
    if mod is rra:
        return rra.log_snapshot(_radar_snap(asof), root=root)
    if mod is rrra:
        return rrra.log_snapshot(_recovery(asof), _recovery_radar(), root=root)
    return msa.log_snapshot(_ms_snap(asof), root=root)


def _offlane(monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1: env matrix — same contract as ignition_audit.ledger_lane_armed (#2693)
# ═══════════════════════════════════════════════════════════════════════════

def test_ledger_lane_armed_env_matrix(monkeypatch):
    cases = [
        ({}, False),                                          # both absent
        ({"COLLECT_LANE": "nightly"}, True),                  # nightly collect lane
        ({"COLLECT_LANE": "intraday"}, False),                # intraday lane
        ({"US_LANE": "nightly"}, True),                       # legacy alias
        ({"COLLECT_LANE": "", "US_LANE": "nightly"}, True),   # empty falls through to alias
    ]
    for mod in MODULES:
        for env, expected in cases:
            _offlane(monkeypatch)
            for k, v in env.items():
                monkeypatch.setenv(k, v)
            assert mod.ledger_lane_armed() is expected, (
                f"{mod.__name__}.ledger_lane_armed() with {env} != {expected}"
            )


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2: appenders — off-lane no-op, on-lane appends (idempotent by asof)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("mod", MODULES, ids=MODULE_IDS)
def test_log_snapshot_lane_gated(mod, tmp_path, monkeypatch):
    _offlane(monkeypatch)
    assert _log(mod, "2026-07-16", tmp_path) is False, (
        "off-lane log_snapshot must no-op (house law: nightly is the sole advancer)"
    )
    p = tmp_path / "data" / LEDGER_REL[mod]
    assert not p.exists() or p.read_text().strip() == "", (
        "off-lane log_snapshot must not write ledger rows"
    )

    monkeypatch.setenv("COLLECT_LANE", "nightly")
    assert _log(mod, "2026-07-16", tmp_path) is True
    assert _log(mod, "2026-07-16", tmp_path) is False    # idempotent by asof


def test_offlane_snapshot_cannot_displace_nightly_row(tmp_path, monkeypatch):
    """The actual hazard (cf. #2684/#2693): appends are first-writer-wins, so an
    off-lane call with a NEW asof must not claim the day's row ahead of the nightly."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    assert rra.log_snapshot(_radar_snap("2026-07-15"), root=tmp_path) is True

    _offlane(monkeypatch)
    assert rra.log_snapshot(_radar_snap("2026-07-16", state="calm"), root=tmp_path) is False

    monkeypatch.setenv("COLLECT_LANE", "nightly")
    assert rra.log_snapshot(_radar_snap("2026-07-16"), root=tmp_path) is True
    rows = [json.loads(l) for l in
            (tmp_path / "data" / "risk_radar" / "forward_log.jsonl").read_text().splitlines()]
    today = [r for r in rows if r["asof"] == "2026-07-16"]
    assert len(today) == 1 and today[0]["state"] == "elevated", (
        "the nightly row must own the asof — off-lane snapshot displaced it"
    )


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3: graders — grades are keep-first-permanent; off-lane must not write them
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("mod", MODULES, ids=MODULE_IDS)
def test_grade_log_lane_gated(mod, tmp_path, monkeypatch):
    idx = pd.bdate_range("2026-01-02", periods=200)
    spy = pd.Series(np.linspace(400.0, 440.0, 200), index=idx)
    monkeypatch.setattr(mod, "_spy", lambda: spy)
    asof = str(idx[5].date())

    monkeypatch.setenv("COLLECT_LANE", "nightly")
    assert _log(mod, asof, tmp_path) is True

    _offlane(monkeypatch)
    assert mod.grade_log(root=tmp_path) == 0
    p = tmp_path / "data" / LEDGER_REL[mod]
    assert json.loads(p.read_text().splitlines()[0])["graded"] is None, (
        "off-lane grade_log must leave matured rows ungraded"
    )

    monkeypatch.setenv("COLLECT_LANE", "nightly")
    assert mod.grade_log(root=tmp_path) == 1
    assert json.loads(p.read_text().splitlines()[0])["graded"] is not None


# ═══════════════════════════════════════════════════════════════════════════
# TEST 4: snapshot_and_grade off-lane = pure scorecard read, display populated
# ═══════════════════════════════════════════════════════════════════════════

def test_snapshot_and_grade_offlane_is_readonly_but_populates_display(tmp_path, monkeypatch):
    _offlane(monkeypatch)
    for sc in (
        rra.snapshot_and_grade(_radar_snap(), root=tmp_path),
        rrra.snapshot_and_grade(_recovery(), _recovery_radar(), root=tmp_path),
        msa.snapshot_and_grade(_ms_snap(), root=tmp_path),
    ):
        assert isinstance(sc, dict) and sc.get("n_graded") == 0 and "note" in sc, (
            "display payload must stay populated off-lane"
        )
    for rel in LEDGER_REL.values():
        assert not (tmp_path / "data" / rel).exists(), (
            f"off-lane snapshot_and_grade must not create {rel}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# TEST 5: source tripwires — writers stay gated; the advancing lane stays armed
# ═══════════════════════════════════════════════════════════════════════════

def test_us_audit_writers_self_gate_source():
    """Every mutating writer must check ledger_lane_armed() before touching the
    ledger (the closing-bell.yml contract: COLLECT_LANE is deliberately unset
    there BECAUSE every ledger writer self-gates)."""
    for fname in ("risk_radar_audit.py", "risk_radar_recovery_audit.py",
                  "market_state_audit.py"):
        src = (ROOT / "engine" / fname).read_text(encoding="utf-8")
        for fn in ("def log_snapshot", "def grade_log"):
            start = src.index(fn)
            nxt = src.find("\ndef ", start + 1)
            body = src[start: nxt if nxt != -1 else len(src)]
            assert "ledger_lane_armed()" in body, f"{fname}: {fn} is not lane-gated"


def test_daily_engine_job_arms_collect_lane():
    """daily.yml's engine job is the SOLE advancing lane for all three US audit
    ledgers (it commits "engine: regime update"). Removing its job-level
    COLLECT_LANE=nightly would silently FREEZE all three forward ledgers
    (frozen-ledger class, cf. #2659/#2688/#2690)."""
    src = (ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
    m = re.search(r"\n  engine:\n(.*?)(?=\n  \w[\w-]*:\n)", src, re.S)
    assert m, "daily.yml no longer has an engine job?"
    assert "COLLECT_LANE: nightly" in m.group(1), (
        "daily.yml's engine job must arm COLLECT_LANE=nightly or the gated US "
        "audit ledgers (risk_radar / recovery / market_state forward logs) freeze"
    )
