"""engine/market_state_audit.py — forward-grade log + per-corroborator attribution."""
from __future__ import annotations

import pandas as pd
import pytest

from engine import market_state_audit as A


@pytest.fixture
def spy(monkeypatch):
    """Deterministic SPY: flat at 100 for 120 business days, then a -10% leg on day 60,
    so a matured entry dated near day 55 PRECEDES a >=5% drawdown and an entry near day 0
    does not. Monkeypatched so the test never touches the real price store."""
    idx = pd.bdate_range("2026-01-01", periods=120)
    px = pd.Series(100.0, index=idx)
    px.iloc[60:] = 90.0          # a clean -10% step down
    monkeypatch.setattr(A, "_spy", lambda: px)
    return px


def _ms(asof, verdict, keys, state="caution", top=90):
    return {"asof": asof, "verdict": verdict, "score": 28, "raw_score": 61,
            "radar": {"state": state, "top_score": top, "amp": len(keys),
                      "amp_keys": keys, "severe_gated": True}}


def test_log_is_idempotent_by_asof(tmp_path, spy):
    snap = _ms("2026-02-02", "RISK_OFF", ["conjunction"])
    assert A.log_snapshot(snap, root=tmp_path) is True
    assert A.log_snapshot(snap, root=tmp_path) is False          # same as-of -> no dupe
    rows = A._read(A._path(tmp_path))
    assert len(rows) == 1 and rows[0]["amp_keys"] == ["conjunction"]


def test_grading_classifies_tp_fp_and_miss(tmp_path, spy):
    # day ~55 (before the -10% leg on day 60) -> drawdown follows
    A.log_snapshot(_ms("2026-03-20", "RISK_OFF", ["conjunction", "complacency"]), root=tmp_path)
    # day ~5 (flat region, no drawdown ahead) -> false positive
    A.log_snapshot(_ms("2026-01-08", "RISK_OFF", ["drawdown_band"]), root=tmp_path)
    # a quiet call right before the drawdown -> a miss
    A.log_snapshot(_ms("2026-03-20", "RISK_ON", [], state=None, top=None), root=tmp_path)  # dup asof, ignored
    A.log_snapshot(_ms("2026-03-23", "RISK_ON", [], state=None, top=None), root=tmp_path)
    assert A.grade_log(root=tmp_path) >= 2
    sc = A.scorecard(root=tmp_path)
    assert sc["n_graded"] >= 3
    outs = {r["asof"]: r["graded"]["outcome"] for r in A._read(A._path(tmp_path)) if r.get("graded")}
    assert outs["2026-03-20"] == "true_positive"
    assert outs["2026-01-08"] == "false_positive"
    assert outs["2026-03-23"] == "miss"


def test_unmatured_entry_is_not_graded(tmp_path, spy):
    # as-of at the very end of the series -> 21-bd horizon can't mature
    A.log_snapshot(_ms("2026-06-12", "RISK_OFF", ["conjunction"]), root=tmp_path)
    A.grade_log(root=tmp_path)
    rows = A._read(A._path(tmp_path))
    assert rows[0]["graded"] is None


def test_per_corroborator_attribution(tmp_path, spy):
    # conjunction present on a TP; drawdown_band present only on an FP
    A.log_snapshot(_ms("2026-03-20", "RISK_OFF", ["conjunction"]), root=tmp_path)        # TP
    A.log_snapshot(_ms("2026-01-08", "RISK_OFF", ["drawdown_band"]), root=tmp_path)      # FP
    A.grade_log(root=tmp_path)
    pc = A.scorecard(root=tmp_path)["per_corroborator"]
    assert pc["conjunction"]["precision"] == 1.0          # led the drawdown
    assert pc["drawdown_band"]["precision"] == 0.0        # did not -> a prune candidate


def test_empty_log_scorecard_is_safe():
    sc = A.scorecard(root="/nonexistent-root-xyz")
    assert sc["n_graded"] == 0 and "accruing" in sc["note"]
