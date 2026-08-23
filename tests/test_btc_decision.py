"""P0A: one canonical Bitcoin Vector action/exposure contract."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import btc_decision as D  # noqa: E402
from engine import btc_recommend as R  # noqa: E402


def _frame(
    *,
    previous: float = 1.0,
    final: float = 1.0,
    raw: float | None = 1.0,
    override_active: int = 0,
    override_id: str = "",
    momentum_state: str = "bear",
) -> pd.DataFrame:
    idx = pd.to_datetime(["2026-08-20", "2026-08-21"])
    data = {
        "close": [73000.0, 78305.0],
        "alloc_optimal": [previous, final],
        "override_active": [0, override_active],
        "override_id": ["", override_id],
        "override_released": [0, 0],
        "override_release_frac": [1.0, 1.0 if not override_active else final / raw if raw else 0.0],
        "reentry_trigger": ["", ""],
        "momentum": [0.70, 0.76],
        "momentum_state": [momentum_state, momentum_state],
        "risk_index": [9.0, 8.0],
        "risk_regime": ["low_risk", "low_risk"],
        "valuation_state": ["fair", "fair"],
        "market_extreme": ["normal", "normal"],
        "mvrv_z": [1.2, 1.3],
        "mayer": [1.1, 1.2],
        "reserve_risk": [0.004, 0.004],
        "sth_cost_basis": [67000.0, 67500.0],
        "composite_state": ["RISK-ON", "RISK-ON"],
    }
    if raw is not None:
        data["alloc_optimal_raw"] = [previous, raw]
    return pd.DataFrame(data, index=idx)


def _master() -> dict:
    return {
        "score": 46,
        "band": "STRONG RISK-ON",
        "drivers_pos": [],
        "drivers_neg": [],
    }


def _cones() -> dict:
    cell = {"p5": -18.0, "p25": -4.0, "p50": 7.0, "p75": 19.0, "p95": 42.0}
    return {"ok": True, "horizons": {"30d": cell, "90d": cell}}


def test_aug21_split_brain_is_structurally_impossible() -> None:
    sig = _frame(previous=1.0, final=1.0, raw=1.0, momentum_state="bear")
    out = R.recommend(sig, _master(), _cones(), {"avg": -2.0, "tail": -8.0}, {"size_pct": 6})

    assert out["ok"] is True
    assert out["action"] == "HOLD 100% BTC"
    assert "DEFENSIVE" not in out["action"]
    assert out["exposure_lo"] == out["exposure_hi"] == 100
    assert out["decision"]["final"]["exposure_pct"] == 100
    assert out["conviction"] == "MODEL"
    assert out["advisory_conviction"] == "MODERATE"
    assert out["decision"]["receipts"]["kelly_risk_budget_pct"] == 6
    assert out["decision"]["receipts"]["categorical_momentum"] == "bear"
    assert out["advisory_action"] == "STAY DEFENSIVE"  # preserved only as a receipt
    assert out["decision"]["integrity"]["advisory_can_resize"] is False


def test_material_change_projects_exact_final_exposure() -> None:
    sig = _frame(previous=0.5, final=1.0, raw=1.0, momentum_state="bull")
    decision = D.build(sig, _master(), {}, generated_at="2026-08-21T23:59:00+00:00")
    assert decision["status"] == "ok"
    assert decision["final"] == {
        "exposure_pct": 100,
        "previous_exposure_pct": 50,
        "change_pp": 50.0,
        "action_code": "increase",
        "action_en": "INCREASE TO 100% BTC",
        "action_zh": "将 BTC 仓位提高至 100%",
        "tone": "bull",
        "basis_en": (
            "Exact final exposure from the canonical Bitcoin Vector allocation. "
            "Kelly and factor states below are analytical receipts only."
        ),
        "basis_zh": "仓位精确取自比特币向量的最终权威配置。下方 Kelly 与各因子状态仅作分析收据。",
    }


def test_unnamed_raw_final_difference_fails_closed() -> None:
    sig = _frame(previous=1.0, final=0.0, raw=1.0, override_active=0, override_id="")
    decision = D.build(sig, _master(), {})
    assert decision["status"] == "conflict"
    assert decision["error"]["code"] == "unnamed_raw_final_conflict"
    assert decision["integrity"]["action_projects_final_exposure"] is False

    recommendation = R.recommend(sig, _master(), _cones(), None, {"size_pct": 5})
    assert recommendation["ok"] is False
    assert recommendation["decision"]["status"] == "conflict"


def test_named_override_can_lawfully_explain_raw_final_difference() -> None:
    sig = _frame(
        previous=1.0,
        final=0.0,
        raw=1.0,
        override_active=1,
        override_id="registered_risk_veto",
        momentum_state="bull",
    )
    decision = D.build(sig, _master(), {})
    assert decision["status"] == "ok"
    assert decision["override"]["active"] is True
    assert decision["override"]["override_id"] == "registered_risk_veto"
    assert decision["final"]["action_en"] == "REDUCE TO 0% BTC"
    assert decision["final"]["exposure_pct"] == 0
    assert decision["integrity"]["raw_final_delta_has_named_override"] is True


def test_missing_or_invalid_final_allocation_never_fabricates_zero() -> None:
    no_alloc = pd.DataFrame({"close": [1.0]}, index=pd.to_datetime(["2026-08-21"]))
    missing = D.build(no_alloc, {}, {})
    assert missing["status"] == "unavailable"
    assert missing["error"]["code"] == "missing_authoritative_allocation"
    assert "final" not in missing

    bad = _frame(final=1.2, raw=1.2)
    invalid = D.build(bad, {}, {})
    assert invalid["status"] == "unavailable"
    assert invalid["error"]["code"] == "invalid_authoritative_allocation"


def test_single_row_sets_exact_exposure() -> None:
    sig = _frame().tail(1)
    decision = D.build(sig, _master(), {})
    assert decision["status"] == "ok"
    assert decision["final"]["previous_exposure_pct"] is None
    assert decision["final"]["action_en"] == "SET TO 100% BTC"


def test_contract_is_strict_json_safe() -> None:
    sig = _frame(previous=0.5, final=1.0, raw=1.0)
    decision = D.build(
        sig,
        _master(),
        {"kelly_pct": 6},
        generated_at=datetime(2026, 8, 21, 23, 59, tzinfo=timezone.utc),
    )
    encoded = json.dumps(decision, allow_nan=False, sort_keys=True)
    assert '"schema": "btc.decision/v1"' in encoded
    assert decision["generated_at"] == "2026-08-21T23:59:00+00:00"


def test_legacy_research_frame_keeps_old_advisory_shape_only() -> None:
    # Old synthetic harnesses omit the post-Override-Registry companion columns.
    # Their historical advisory assertions remain reproducible, while production
    # frames always take the canonical path above.
    sig = _frame().drop(columns=[
        "alloc_optimal_raw", "override_active", "override_id",
        "override_released", "override_release_frac", "reentry_trigger",
    ])
    out = R.recommend(sig, _master(), _cones(), None, {"size_pct": 6})
    assert out["ok"] is True
    assert "decision" not in out
    assert out["action"] == "STAY DEFENSIVE"
