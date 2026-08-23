from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import engine.global_liquidity_transmission as glt
from scripts.build_global_liquidity_transmission import preserve_first_known


def _cfg() -> dict:
    monetary = {}
    for name in ("fed", "ecb", "boj"):
        monetary[name] = {
            "provider": name,
            "source_id": name.upper(),
            "frequency": "weekly",
            "period_anchor": "observation_date",
            "release_lag_bdays": 1,
            "stale_after_calendar_days": 14,
            "unit_multiplier": 1.0,
            "fx": None,
            "weight": 1.0,
            "pit_status": "fixture",
            "revision_risk": "low",
        }
    funding = {}
    for name in ("broad_dollar", "real_yield_10y", "high_yield_oas"):
        funding[name] = {
            "provider": name,
            "source_id": name.upper(),
            "frequency": "weekly",
            "period_anchor": "observation_date",
            "release_lag_bdays": 1,
            "stale_after_calendar_days": 14,
            "change_transform": "level_change",
            "change_periods": 4,
            "direction_multiplier": -1.0,
            "weight": 1.0,
            "pit_status": "fixture",
            "revision_risk": "low",
        }
    return {
        "contract_schema": glt.CONTRACT_SCHEMA,
        "producer_version": "fixture.1",
        "authority": "measurement_only",
        "frequency": "W-FRI",
        "min_history_periods": 12,
        "orthogonal_min_history_periods": 24,
        "min_monetary_coverage_ratio": 2 / 3,
        "min_funding_coverage_ratio": 2 / 3,
        "monetary_components": monetary,
        "usd_funding_components": funding,
        "quality_thresholds": {"monetary_impulse_z": 0.05},
    }


def _inputs(periods: int = 180) -> tuple[dict, dict, dict]:
    idx = pd.date_range("2018-01-03", periods=periods, freq="W-WED")
    t = np.arange(periods, dtype=float)
    monetary = {
        "fed": pd.Series(100 + 0.30 * t + np.sin(t / 9), index=idx),
        "ecb": pd.Series(90 + 0.20 * t + np.cos(t / 7), index=idx),
        "boj": pd.Series(80 + 0.10 * t + np.sin(t / 11), index=idx),
    }
    funding = {
        "broad_dollar": pd.Series(100 + np.sin(t / 5), index=idx),
        "real_yield_10y": pd.Series(1.0 + np.cos(t / 8), index=idx),
        "high_yield_oas": pd.Series(3.0 + np.sin(t / 6), index=idx),
    }
    return monetary, {name: None for name in monetary}, funding


def test_boj_monthly_label_is_anchored_to_month_end_before_release() -> None:
    raw = pd.Series([500.0], index=pd.to_datetime(["2026-07-01"]))
    fx = pd.Series(
        [150.0, 155.0],
        index=pd.to_datetime(["2026-07-01", "2026-07-31"]),
    )
    spec = {
        "period_anchor": "month_end",
        "release_lag_bdays": 2,
        "stale_after_calendar_days": 45,
        "unit_multiplier": 1.0,
        "fx": {"invert": True},
    }
    grid = pd.DatetimeIndex(["2026-07-31", "2026-08-07"])

    aligned = glt.align_component(raw, spec, grid, fx)

    assert pd.isna(aligned.value.loc["2026-07-31"])
    assert aligned.reference_date.loc["2026-08-07"] == pd.Timestamp("2026-07-31")
    assert aligned.available_date.loc["2026-08-07"] == pd.Timestamp("2026-08-04")
    assert aligned.value.loc["2026-08-07"] == pytest.approx(500.0 / 155.0)


def test_future_source_mutation_cannot_change_past_state() -> None:
    cfg = _cfg()
    monetary, fx, funding = _inputs()
    cutoff = pd.Timestamp("2020-12-25")
    before, *_ = glt.build_state_history(monetary, fx, funding, cfg, asof=cutoff)

    mutated = {name: series.copy() for name, series in monetary.items()}
    future_idx = mutated["fed"].index > cutoff
    mutated["fed"].loc[future_idx] *= 50.0
    after, *_ = glt.build_state_history(mutated, fx, funding, cfg)

    pd.testing.assert_frame_equal(
        before,
        after.loc[before.index],
        check_exact=False,
        rtol=1e-12,
        atol=1e-12,
    )


def test_missing_components_reduce_coverage_and_never_become_supportive_zero() -> None:
    cfg = _cfg()
    monetary, fx, funding = _inputs()
    cutoff = monetary["ecb"].index[-30]
    monetary["ecb"] = monetary["ecb"].loc[:cutoff]
    monetary["boj"] = monetary["boj"].loc[:cutoff]

    history, *_ = glt.build_state_history(monetary, fx, funding, cfg)

    latest = history.iloc[-1]
    assert latest["monetary_coverage_ratio"] == pytest.approx(1 / 3)
    assert pd.isna(latest["monetary_stance"])
    assert pd.isna(latest["monetary_impulse"])
    assert pd.isna(latest["liquidity_breadth"])


def test_orthogonal_residual_uses_only_prior_pairs() -> None:
    idx = pd.date_range("2020-01-03", periods=60, freq="W-FRI")
    stance = pd.Series(np.linspace(-2, 2, 60), index=idx)
    impulse = 0.5 + 0.25 * stance + pd.Series(np.sin(np.arange(60)), index=idx)
    baseline = glt.causal_orthogonal_residual(impulse, stance, min_periods=20)
    changed = impulse.copy()
    changed.iloc[-1] += 1000
    replay = glt.causal_orthogonal_residual(changed, stance, min_periods=20)

    pd.testing.assert_series_equal(baseline.iloc[:-1], replay.iloc[:-1])
    expected_delta = changed.iloc[-1] - impulse.iloc[-1]
    assert replay.iloc[-1] - baseline.iloc[-1] == pytest.approx(expected_delta)


def test_contract_is_state_only_and_reports_null_global_credit(monkeypatch, tmp_path) -> None:
    cfg = _cfg()
    monetary, fx, funding = _inputs()
    monkeypatch.setattr(glt, "load_inputs", lambda _cfg: (monetary, fx, funding))

    payload, history = glt.build_contract(
        producer_cfg=cfg,
        root=tmp_path,
        generated_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )

    assert set(payload) == {"meta", "state", "quality", "freshness"}
    assert payload["meta"]["schema"] == "global_liquidity_transmission.v1"
    assert payload["meta"]["authority"] == "measurement_only"
    assert payload["state"]["credit_impulse_global"] is None
    assert payload["quality"]["global_credit"]["status"] == "insufficient_comparable_pit_coverage"
    event = payload["state"]["event_reference"]
    assert event["producer_schema"] == "global_liquidity_transmission.v1"
    assert event["state_family"] == "monetary_impulse"
    assert event["shock_type"] == "policy_liquidity_impulse"
    assert event["direction"] in (-1, 1)
    assert 0 <= event["breadth"] <= 1
    assert 0 <= event["confidence"] <= 1
    assert 0 <= event["coverage"] <= 1
    assert event["freshness"] == "fresh"
    assert len(event["source_snapshot_hash"]) == 64
    assert event["data_version"].startswith("glt_data:")
    assert event["clocks"]["adapter_observed_at_field"] == "release_at"
    assert event["clocks"]["adapter_known_at_field"] == "first_known_at"
    assert "transmission" not in payload
    assert "repricing_gap" not in payload
    assert history["orthogonalised_impulse"].notna().any()


def test_source_snapshot_hash_excludes_first_known_clock(monkeypatch, tmp_path) -> None:
    cfg = _cfg()
    monetary, fx, funding = _inputs()
    monkeypatch.setattr(glt, "load_inputs", lambda _cfg: (monetary, fx, funding))
    first, _ = glt.build_contract(
        producer_cfg=cfg,
        root=tmp_path,
        generated_at=datetime(2026, 8, 22, 10, tzinfo=timezone.utc),
    )
    replay, _ = glt.build_contract(
        producer_cfg=cfg,
        root=tmp_path,
        generated_at=datetime(2026, 8, 22, 11, tzinfo=timezone.utc),
    )

    assert first["meta"]["source_snapshot_hash"] == replay["meta"]["source_snapshot_hash"]
    assert first["meta"]["data_version"] == replay["meta"]["data_version"]
    assert (
        first["state"]["event_reference"]["clocks"]["first_known_at"]
        != replay["state"]["event_reference"]["clocks"]["first_known_at"]
    )
    preserved = preserve_first_known(replay, first)
    assert (
        preserved["state"]["event_reference"]["clocks"]["first_known_at"]
        == first["state"]["event_reference"]["clocks"]["first_known_at"]
    )
    assert (
        preserved["freshness"]["clocks"]["first_known_at"]
        == first["state"]["event_reference"]["clocks"]["first_known_at"]
    )


def test_frozen_fixture_reproduces_historical_window() -> None:
    fixture_path = Path(__file__).parent / "fixtures/global_liquidity_transmission_wliq1_window.json"
    fixture = json.loads(fixture_path.read_text())
    idx = pd.DatetimeIndex(fixture["dates"])
    monetary = {name: pd.Series(values, index=idx) for name, values in fixture["monetary"].items()}
    funding = {name: pd.Series(values, index=idx) for name, values in fixture["funding"].items()}
    cfg = _cfg()
    cfg["orthogonal_min_history_periods"] = fixture["orthogonal_min_history_periods"]

    history, *_ = glt.build_state_history(
        monetary,
        {name: None for name in monetary},
        funding,
        cfg,
    )

    assert str(history.index[-1].date()) == fixture["expected_last_asof"]
    for field, expected in fixture["expected_last"].items():
        assert history.iloc[-1][field] == pytest.approx(expected, abs=1e-12)


def test_walk_forward_receipt_has_purge_gap_and_no_promotion_authority() -> None:
    cfg = _cfg()
    monetary, fx, funding = _inputs(periods=360)
    history, *_ = glt.build_state_history(monetary, fx, funding, cfg)
    btc = pd.Series(
        np.exp(np.linspace(6, 9, 360) + 0.1 * np.sin(np.arange(360) / 8)),
        index=pd.date_range("2018-01-03", periods=360, freq="W-WED"),
    )

    receipt = glt.walk_forward_factor_comparison(
        history,
        btc,
        initial_train_weeks=80,
        test_weeks=26,
        purge_weeks=4,
    )

    assert receipt["authority"] == "research_only_no_promotion"
    assert set(receipt["factors"]) == {
        "monetary_stance",
        "monetary_impulse",
        "orthogonalised_impulse",
    }
    for result in receipt["factors"].values():
        assert result["oos_n"] > 0
        for fold in result["folds"]:
            assert (pd.Timestamp(fold["test_start"]) - pd.Timestamp(fold["train_end"])).days >= 28
