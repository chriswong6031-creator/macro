from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re

import pandas as pd
import pytest
from jsonschema import Draft202012Validator, FormatChecker

from engine.btc_decision import build_decision


ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "contracts" / "btc_decision.schema.json"


def _validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _assert_contract(payload: dict) -> None:
    _validator().validate(payload)
    json.dumps(payload, ensure_ascii=False, allow_nan=False)


def _signals(rows: list[dict]) -> pd.DataFrame:
    idx = pd.date_range("2026-08-20", periods=len(rows), freq="D")
    return pd.DataFrame(rows, index=idx)


def _master(score: int = 46) -> dict:
    return {
        "score": score,
        "band_en": "STRONG RISK-ON",
        "band_zh": "强风险偏好",
    }


def _old_conflicting_rec() -> dict:
    return {
        "ok": True,
        "action": "STAY DEFENSIVE",
        "action_zh": "保持防守",
        "tone": "bear",
        "exposure_lo": 0,
        "exposure_hi": 10,
        "kelly_pct": 5,
        "conviction": "MODERATE",
        "basis_en": "trend broken — cut exposure",
        "basis_zh": "趋势走坏 — 降低敞口",
        "levels": {"price": 78_305, "invalidation": 71_000},
        "rationale": [{"label_en": "Momentum", "state_en": "Bear"}],
        "key_risk_en": "Volatility",
        "key_risk_zh": "波动",
        "horizon_en": "weeks–months (strategic)",
        "horizon_zh": "数周至数月（战略）",
    }


def test_aug21_split_brain_fixture_projects_only_final_100() -> None:
    sig = _signals(
        [
            {
                "alloc_optimal": 0.0,
                "alloc_optimal_raw": 0.0,
                "momentum": 0.20,
                "momentum_state": "neutral",
                "risk_index": 18.0,
                "risk_regime": "low_risk",
            },
            {
                "alloc_optimal": 1.0,
                "alloc_optimal_raw": 1.0,
                "momentum": 0.76,
                # Reproduce the stale categorical disagreement that used to drive the card.
                "momentum_state": "bear",
                "risk_index": 8.0,
                "risk_regime": "low_risk",
                "valuation_state": "fair",
                "market_extreme": "normal",
            },
        ]
    )
    out = build_decision(
        sig,
        _master(),
        recommendation=_old_conflicting_rec(),
        sizing={"size_pct": 5},
        generated_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )

    assert out["status"] == "ok"
    assert out["final"]["exposure_pct"] == 100.0
    assert out["final"]["action_code"] == "INCREASE_EXPOSURE"
    assert out["final"]["action_en"] == "INCREASE TO 100% BTC"
    assert out["receipts"]["kelly_risk_budget_pct"] == 5.0
    assert out["receipts"]["categorical_momentum"] == "bear"

    # The old competing authority is deliberately not allowlisted.
    advisory = out["advisory"]
    for forbidden in (
        "action",
        "action_zh",
        "tone",
        "exposure_lo",
        "exposure_hi",
        "kelly_pct",
        "conviction",
        "basis_en",
        "basis_zh",
    ):
        assert forbidden not in advisory
    assert advisory["levels"]["price"] == 78_305


def test_kelly_zero_does_not_change_final_target() -> None:
    sig = _signals(
        [
            {"alloc_optimal": 1.0, "alloc_optimal_raw": 1.0},
            {"alloc_optimal": 1.0, "alloc_optimal_raw": 1.0},
        ]
    )
    out = build_decision(sig, _master(), sizing={"size_pct": 0})
    assert out["status"] == "ok"
    assert out["final"]["action_en"] == "HOLD 100% BTC"
    assert out["receipts"]["kelly_risk_budget_pct"] == 0.0


def test_legacy_bear_momentum_cannot_originate_defensive_action() -> None:
    sig = _signals(
        [
            {"alloc_optimal": 1.0, "alloc_optimal_raw": 1.0},
            {
                "alloc_optimal": 1.0,
                "alloc_optimal_raw": 1.0,
                "momentum_state": "bear",
            },
        ]
    )
    out = build_decision(sig, _master(), recommendation=_old_conflicting_rec())
    assert out["final"]["action_code"] == "HOLD_EXPOSURE"
    assert "DEFENSIVE" not in out["final"]["action_en"]


def test_raw_final_mismatch_without_named_override_fails_closed() -> None:
    sig = _signals(
        [
            {"alloc_optimal": 1.0, "alloc_optimal_raw": 1.0},
            {
                "alloc_optimal": 0.0,
                "alloc_optimal_raw": 1.0,
                "override_active": False,
            },
        ]
    )
    out = build_decision(sig, _master())
    assert out["status"] == "unavailable"
    assert out["final"]["action_code"] is None
    assert "RAW_FINAL_MISMATCH_WITHOUT_NAMED_OVERRIDE" in out["integrity"]["errors"]


def test_named_override_may_lawfully_explain_raw_final_difference() -> None:
    sig = _signals(
        [
            {"alloc_optimal": 1.0, "alloc_optimal_raw": 1.0},
            {
                "alloc_optimal": 0.0,
                "alloc_optimal_raw": 1.0,
                "override_active": True,
                "override_id": "liquidity_crisis_veto",
            },
        ]
    )
    out = build_decision(sig, _master())
    assert out["status"] == "ok"
    assert out["override"]["active"] is True
    assert out["final"]["action_code"] == "REDUCE_EXPOSURE"
    assert out["final"]["action_en"] == "REDUCE TO 0% BTC"


def test_active_override_without_id_fails_closed_even_without_mismatch() -> None:
    sig = _signals(
        [
            {"alloc_optimal": 0.5, "alloc_optimal_raw": 0.5},
            {
                "alloc_optimal": 0.5,
                "alloc_optimal_raw": 0.5,
                "override_active": True,
            },
        ]
    )
    out = build_decision(sig, _master())
    assert out["status"] == "unavailable"
    assert "ACTIVE_OVERRIDE_WITHOUT_ID" in out["integrity"]["errors"]


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), -0.1, 1.1])
def test_missing_or_out_of_range_final_allocation_fails_closed(bad) -> None:
    sig = _signals(
        [
            {"alloc_optimal": 0.5, "alloc_optimal_raw": 0.5},
            {"alloc_optimal": bad, "alloc_optimal_raw": 0.5},
        ]
    )
    out = build_decision(sig, _master())
    assert out["status"] == "unavailable"
    assert out["final"]["action_code"] is None


def test_missing_raw_is_not_fabricated_from_final() -> None:
    sig = _signals(
        [
            {"alloc_optimal": 0.5},
            {"alloc_optimal": 0.5},
        ]
    )
    out = build_decision(sig, _master())
    assert out["status"] == "ok"
    assert out["raw_model"]["exposure"] is None
    assert out["raw_model"]["exposure_pct"] is None
    assert out["integrity"]["checks"]["raw_final_consistent_or_named_override"] is True


def test_missing_prior_is_set_target_not_assumed_increase_from_zero() -> None:
    sig = _signals([{"alloc_optimal": 1.0, "alloc_optimal_raw": 1.0}])
    out = build_decision(sig, _master())
    assert out["final"]["previous_exposure_pct"] is None
    assert out["final"]["action_code"] == "SET_EXPOSURE"
    assert out["final"]["action_en"] == "MODEL TARGET 100% BTC"


@pytest.mark.parametrize(
    ("prior", "current", "expected"),
    [
        (0.500, 0.599, "HOLD_EXPOSURE"),
        (0.500, 0.600, "INCREASE_EXPOSURE"),
        (0.500, 0.401, "HOLD_EXPOSURE"),
        (0.500, 0.400, "REDUCE_EXPOSURE"),
    ],
)
def test_ten_percentage_point_materiality_boundary(prior, current, expected) -> None:
    sig = _signals(
        [
            {"alloc_optimal": prior, "alloc_optimal_raw": prior},
            {"alloc_optimal": current, "alloc_optimal_raw": current},
        ]
    )
    out = build_decision(sig, _master())
    assert out["final"]["action_code"] == expected


def test_unchanged_zero_is_stay_out() -> None:
    sig = _signals(
        [
            {"alloc_optimal": 0.0, "alloc_optimal_raw": 0.0},
            {"alloc_optimal": 0.0, "alloc_optimal_raw": 0.0},
        ]
    )
    out = build_decision(sig, _master())
    assert out["final"]["action_en"] == "STAY OUT — 0% BTC"
    assert out["final"]["action_zh"] == "保持空仓 — 0% BTC"


def test_empty_signals_is_unavailable() -> None:
    out = build_decision(pd.DataFrame(), _master())
    assert out["status"] == "unavailable"
    assert out["integrity"]["errors"] == ["EMPTY_SIGNALS"]


def test_generated_at_is_injected_and_utc() -> None:
    sig = _signals([{"alloc_optimal": 1.0, "alloc_optimal_raw": 1.0}])
    out = build_decision(
        sig,
        _master(),
        generated_at=datetime(2026, 8, 22, 12, 34, 56),
    )
    assert out["generated_at"] == "2026-08-22T12:34:56Z"


def test_schema_accepts_ok_unavailable_and_missing_raw_states() -> None:
    good = build_decision(
        _signals(
            [
                {"alloc_optimal": 0.5, "alloc_optimal_raw": 0.5},
                {"alloc_optimal": 0.6, "alloc_optimal_raw": 0.6},
            ]
        ),
        _master(),
        recommendation=_old_conflicting_rec(),
        sizing={"size_pct": 5},
        generated_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )
    unavailable = build_decision(
        _signals(
            [
                {"alloc_optimal": 1.0, "alloc_optimal_raw": 1.0},
                {"alloc_optimal": 0.0, "alloc_optimal_raw": 1.0},
            ]
        ),
        _master(),
        generated_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )
    missing_raw = build_decision(
        _signals([{"alloc_optimal": 0.44}, {"alloc_optimal": 0.44}]),
        _master(),
        generated_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )

    for payload in (good, unavailable, missing_raw):
        _assert_contract(payload)


def test_empty_state_is_schema_valid_and_carries_no_action() -> None:
    out = build_decision(
        pd.DataFrame(),
        _master(),
        generated_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )
    _assert_contract(out)
    assert out["final"] is None
    assert out["status"] == "unavailable"


def test_invalid_input_values_fail_closed_without_poisoning_contract() -> None:
    sig = _signals(
        [
            {"alloc_optimal": 0.5, "alloc_optimal_raw": 0.5},
            {
                "alloc_optimal": 1.4,
                "alloc_optimal_raw": -0.2,
                "override_active": True,
                "override_id": "named",
                "override_release_frac": 1.2,
            },
        ]
    )
    out = build_decision(
        sig,
        _master(),
        generated_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )

    _assert_contract(out)
    assert out["status"] == "unavailable"
    assert out["raw_model"]["exposure"] is None
    assert out["override"]["release_frac"] is None
    assert out["final"]["exposure"] is None
    assert set(out["integrity"]["errors"]) >= {
        "FINAL_ALLOCATION_OUT_OF_RANGE",
        "RAW_ALLOCATION_OUT_OF_RANGE",
        "OVERRIDE_RELEASE_FRAC_OUT_OF_RANGE",
    }


def test_malformed_advisory_is_contained_and_cannot_break_final_decision() -> None:
    sig = _signals(
        [
            {"alloc_optimal": 1.0, "alloc_optimal_raw": 1.0},
            {"alloc_optimal": 1.0, "alloc_optimal_raw": 1.0},
        ]
    )
    out = build_decision(
        sig,
        _master(),
        recommendation={
            "action": "STAY DEFENSIVE",
            "exposure_lo": 0,
            "exposure_hi": 10,
            "levels": "not-an-object",
            "rationale": "not-an-array",
            "key_risk_en": float("nan"),
        },
        generated_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )

    _assert_contract(out)
    assert out["status"] == "ok"
    assert out["final"]["action_en"] == "HOLD 100% BTC"
    assert out["advisory"]["available"] is False
    assert out["advisory"]["levels"] is None
    assert out["advisory"]["rationale"] is None
    assert out["advisory"]["key_risk_en"] is None


def test_missing_recommendation_and_kelly_leave_final_decision_available() -> None:
    sig = _signals(
        [
            {"alloc_optimal": 0.44, "alloc_optimal_raw": 0.44},
            {"alloc_optimal": 0.44, "alloc_optimal_raw": 0.44},
        ]
    )
    out = build_decision(
        sig,
        _master(),
        generated_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )

    _assert_contract(out)
    assert out["status"] == "ok"
    assert out["final"]["exposure_pct"] == 44
    assert out["advisory"]["available"] is False
    assert out["receipts"]["kelly_risk_budget_pct"] is None


@pytest.mark.parametrize(
    ("prior", "current", "expected_code", "target"),
    [
        (0.0, 1.0, "INCREASE_EXPOSURE", 100),
        (1.0, 0.0, "REDUCE_EXPOSURE", 0),
        (0.44, 0.44, "HOLD_EXPOSURE", 44),
        (0.0, 0.0, "STAY_OUT", 0),
    ],
)
def test_bilingual_action_numbers_equal_final_display_target(
    prior, current, expected_code, target
) -> None:
    out = build_decision(
        _signals(
            [
                {"alloc_optimal": prior, "alloc_optimal_raw": prior},
                {"alloc_optimal": current, "alloc_optimal_raw": current},
            ]
        ),
        _master(),
        generated_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )
    _assert_contract(out)

    assert out["final"]["action_code"] == expected_code
    assert out["final"]["exposure_pct"] == target
    for key in ("action_en", "action_zh"):
        match = re.search(r"(\d+)% BTC", out["final"][key])
        assert match, out["final"][key]
        assert int(match.group(1)) == target


def test_previous_exposure_uses_prior_finite_observation() -> None:
    sig = _signals(
        [
            {"alloc_optimal": 0.2, "alloc_optimal_raw": 0.2},
            {"alloc_optimal": float("inf"), "alloc_optimal_raw": 0.2},
            {"alloc_optimal": None, "alloc_optimal_raw": 0.2},
            {"alloc_optimal": 0.4, "alloc_optimal_raw": 0.4},
        ]
    )
    out = build_decision(
        sig,
        _master(),
        generated_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )

    _assert_contract(out)
    assert out["final"]["previous_exposure_pct"] == 20
    assert out["final"]["change_pp"] == 20
    assert out["final"]["action_code"] == "INCREASE_EXPOSURE"


def test_vector_action_surface_reads_only_decision_state() -> None:
    template = (ROOT / "templates" / "vector.html.j2").read_text(encoding="utf-8")
    builder = (ROOT / "scripts" / "build_vector.py").read_text(encoding="utf-8")

    for forbidden in (
        "rec.action",
        "rec.action_zh",
        "rec.tone",
        "rec.exposure_lo",
        "rec.exposure_hi",
        "rec.conviction",
        "rec.basis_en",
        "rec.basis_zh",
    ):
        assert forbidden not in template
    assert "decision.final.action_en" in template
    assert "decision.final.exposure_pct" in template
    assert "decision.advisory.levels" in template
    assert "exposure_lo" not in template
    assert "exposure_hi" not in template
    assert "btc_decision.build_decision" in builder
    assert '"decision": decision' in builder
