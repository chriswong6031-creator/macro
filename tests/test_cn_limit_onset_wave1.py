"""Focused chronology, execution, model, and forward-ledger contracts for ONSET Wave 1."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.cn_limit_alpha_sol import onset_wave1 as mod


def _calendar(n: int = 150) -> np.ndarray:
    return pd.bdate_range("2025-01-02", periods=n).to_numpy(dtype="datetime64[D]").astype(np.int32)


def _frame(days: np.ndarray) -> pd.DataFrame:
    n = len(days)
    close = 10.0 + np.arange(n) * 0.01
    return pd.DataFrame({
        "open": close - 0.01,
        "close": close,
        "high": close + 0.03,
        "low": close - 0.03,
        "volume": 1_000_000 + (np.arange(n) % 17) * 10_000,
    }, index=pd.DatetimeIndex(days.astype("datetime64[D]"), name="Date"))


def test_ipo_clock_uses_positive_volume_sessions_not_prelisting_rows():
    days = pd.to_datetime([
        "2026-06-29", "2026-06-30", "2026-07-02", "2026-07-03",
        "2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09",
    ]).to_numpy(dtype="datetime64[D]").astype(np.int32)
    positive = np.asarray([False, False, True, True, True, True, True, True])
    mask = mod.ipo_no_limit_mask("main", days, positive)
    assert np.flatnonzero(mask).tolist() == [2, 3, 4, 5, 6]


def test_ipo_clock_is_era_specific_for_chinext_and_star():
    pre_days = pd.bdate_range("2019-01-02", periods=7).to_numpy(
        dtype="datetime64[D]"
    ).astype(np.int32)
    post_days = pd.bdate_range("2020-08-24", periods=7).to_numpy(
        dtype="datetime64[D]"
    ).astype(np.int32)
    positive = np.ones(7, dtype=bool)
    assert np.flatnonzero(mod.ipo_no_limit_mask("chinext", pre_days, positive)).tolist() == [0]
    assert np.flatnonzero(mod.ipo_no_limit_mask("chinext", post_days, positive)).tolist() == [0, 1, 2, 3, 4]
    assert np.flatnonzero(mod.ipo_no_limit_mask("star", post_days, positive)).tolist() == [0, 1, 2, 3, 4]


def test_legacy_main_listing_day_is_never_an_ordinary_ten_percent_session():
    days = pd.bdate_range("2023-04-03", periods=4).to_numpy(
        dtype="datetime64[D]"
    ).astype(np.int32)
    positive = np.ones(4, dtype=bool)
    assert np.flatnonzero(mod.ipo_no_limit_mask("main", days, positive)).tolist() == [0]


def test_zt_ticker_alias_is_canonicalized():
    assert mod.canonical_ticker("600000.SH") == "600000.SS"
    assert mod.canonical_ticker("000001.SZ") == "000001.SZ"


def test_missing_exact_D_remains_competing_zero_and_never_jumps_to_resumption():
    calendar = _calendar()
    target = int(calendar[130])
    raw_days = np.delete(calendar, 130)  # D is halted/missing; D+1 exists in the ticker frame.
    frame = _frame(raw_days)
    chunk, _, _ = mod.extract_ticker(
        frame, ticker="000001.SZ", ticker_id=0, board="main",
        calendar_days=calendar, day_to_calendar_pos={int(d): i for i, d in enumerate(calendar)},
        panel_start=target, panel_end=target,
    )
    assert len(chunk["dates"]) == 1
    assert int(chunk["dates"][0]) == target
    assert int(chunk["target_state"][0]) == 1  # missing_halted
    assert not bool(chunk["y_tolerant"][0])
    assert not bool(chunk["y_strict"][0])
    assert int(chunk["fill_state"][0]) == 2
    assert np.array_equal(chunk["gross_returns"][0], np.zeros(3, dtype=np.float32))


def test_features_are_frozen_at_D_minus_1_and_ignore_D_price_mutation():
    calendar = _calendar()
    target = int(calendar[130])
    frame_a = _frame(calendar)
    frame_b = frame_a.copy()
    target_stamp = pd.Timestamp(np.datetime64(target, "D"))
    frame_b.loc[target_stamp, ["open", "close", "high", "low"]] = [8.0, 8.1, 8.2, 7.9]
    kwargs = dict(ticker="000001.SZ", ticker_id=0, board="main", calendar_days=calendar,
                  day_to_calendar_pos={int(d): i for i, d in enumerate(calendar)},
                  panel_start=target, panel_end=target)
    a, _, _ = mod.extract_ticker(frame_a, **kwargs)
    b, _, _ = mod.extract_ticker(frame_b, **kwargs)
    np.testing.assert_array_equal(a["x"], b["x"])


def test_missing_exact_exit_never_jumps_to_later_ticker_bar():
    calendar = _calendar(8)
    target = int(calendar[1])
    raw_days = np.delete(calendar, 2)  # scheduled D+1 missing; D+2 remains available
    limits = {"open": np.full(len(raw_days), 10.0), "lower": np.full(len(raw_days), 9.0),
              "valid": np.ones(len(raw_days), dtype=bool)}
    gross, state, carry = mod.simulate_exit(
        raw_days=raw_days, calendar_days=calendar,
        day_to_calendar_pos={int(d): i for i, d in enumerate(calendar)}, limits=limits,
        entry_open=10.0, target_day=target, horizon=1,
    )
    assert gross == 0.0
    assert int(state) == 2  # missing_cash, not a D+2 resumption fill
    assert int(carry) == 0


def test_long_horizon_exit_rejects_an_intervening_halt_before_resumption():
    calendar = _calendar(8)
    target = int(calendar[1])
    # D+1 is absent but D+3, the nominal H3 exit, exists.  Treating D+3 as usable would make the
    # label conditional on the ticker having resumed by the requested horizon.
    raw_days = np.delete(calendar, 2)
    limits = {"open": np.full(len(raw_days), 10.5), "lower": np.full(len(raw_days), 9.0),
              "valid": np.ones(len(raw_days), dtype=bool)}
    gross, state, carry = mod.simulate_exit(
        raw_days=raw_days, calendar_days=calendar,
        day_to_calendar_pos={int(d): i for i, d in enumerate(calendar)}, limits=limits,
        entry_open=10.0, target_day=target, horizon=3,
    )
    assert gross == 0.0
    assert int(state) == 2
    assert int(carry) == 0


def test_long_horizon_exit_rejects_an_intervening_zero_volume_placeholder():
    calendar = _calendar(8)
    target = int(calendar[1])
    valid = np.ones(len(calendar), dtype=bool)
    valid[2] = False  # exact D+1 row exists, but is a zero-volume placeholder
    gross, state, carry = mod.simulate_exit(
        raw_days=calendar, calendar_days=calendar,
        day_to_calendar_pos={int(d): i for i, d in enumerate(calendar)},
        limits={"open": np.full(len(calendar), 10.5),
                "lower": np.full(len(calendar), 9.0), "valid": valid},
        entry_open=10.0, target_day=target, horizon=3,
    )
    assert gross == 0.0
    assert int(state) == 2
    assert int(carry) == 0


def test_lower_limit_lock_is_the_only_allowed_exit_carry():
    calendar = _calendar(8)
    target = int(calendar[1])
    opens = np.full(len(calendar), 10.0)
    lowers = np.full(len(calendar), 9.0)
    opens[2] = 9.0   # exact D+1 is lower-limit locked
    opens[3] = 9.5   # exact D+2 releases
    gross, state, carry = mod.simulate_exit(
        raw_days=calendar, calendar_days=calendar,
        day_to_calendar_pos={int(d): i for i, d in enumerate(calendar)},
        limits={"open": opens, "lower": lowers, "valid": np.ones(len(calendar), dtype=bool)},
        entry_open=10.0,
        target_day=target, horizon=1,
    )
    assert gross == pytest.approx(-0.05)
    assert int(state) == 3
    assert int(carry) == 1


def test_zero_volume_target_is_missing_no_fill_not_observed():
    calendar = _calendar()
    target = int(calendar[130])
    frame = _frame(calendar)
    target_stamp = pd.Timestamp(np.datetime64(target, "D"))
    frame.loc[target_stamp, "volume"] = 0.0
    chunk, _, stats = mod.extract_ticker(
        frame, ticker="000001.SZ", ticker_id=0, board="main",
        calendar_days=calendar, day_to_calendar_pos={int(d): i for i, d in enumerate(calendar)},
        panel_start=target, panel_end=target,
    )
    assert len(chunk["dates"]) == 1
    assert int(chunk["target_state"][0]) == 1
    assert int(chunk["fill_state"][0]) == 2
    assert not bool(chunk["y_tolerant"][0])
    assert stats["missing_target_zero_volume"] == 1


def test_zero_volume_exit_cannot_fill_or_start_lower_limit_carry():
    calendar = _calendar(8)
    target = int(calendar[1])
    valid = np.ones(len(calendar), dtype=bool)
    valid[2] = False  # D+1 has a nominal lower-limit price but zero volume.
    opens = np.full(len(calendar), 10.0)
    opens[2] = 9.0
    gross, state, carry = mod.simulate_exit(
        raw_days=calendar, calendar_days=calendar,
        day_to_calendar_pos={int(d): i for i, d in enumerate(calendar)},
        limits={"open": opens, "lower": np.full(len(calendar), 9.0), "valid": valid},
        entry_open=10.0, target_day=target, horizon=1,
    )
    assert gross == 0.0
    assert int(state) == 2
    assert int(carry) == 0


def test_joint_book_keeps_queue_and_missing_candidates_as_cash_zero():
    fill = np.asarray([0, 1, 2], dtype=np.uint8)
    gross = np.asarray([0.09, 0.80, -0.50], dtype=np.float32)
    exit_state = np.asarray([0, 1, 2], dtype=np.uint8)
    joint = mod.cash_book_return(fill, gross, exit_state, 0)
    assert joint.tolist() == pytest.approx([0.09, 0.0, 0.0])
    assert float(joint.mean()) == pytest.approx(0.03)  # P(fill) * E(return | fill), not 9%


def test_sequential_h1_fixed_sleeves_block_duplicate_ticker_during_carry():
    calendar = _calendar(6)
    d1, d2 = int(calendar[1]), int(calendar[2])
    panel = mod.Panel(
        dates=np.asarray([d1, d1, d2, d2], dtype=np.int32),
        ticker_id=np.asarray([0, 2, 0, 1], dtype=np.uint16),
        board=np.zeros(4, dtype=np.uint8), era=np.zeros(4, dtype=np.uint8),
        x=np.zeros((4, len(mod.FEATURE_NAMES)), dtype=np.float32),
        y_tolerant=np.zeros(4, dtype=bool), y_strict=np.zeros(4, dtype=bool),
        target_state=np.zeros(4, dtype=np.uint8),
        fill_state=np.asarray([0, 1, 0, 0], dtype=np.uint8),
        gross_returns=np.zeros((4, len(mod.HORIZONS)), dtype=np.float32),
        exit_state=np.zeros((4, len(mod.HORIZONS)), dtype=np.uint8),
        carry_sessions=np.zeros((4, len(mod.HORIZONS)), dtype=np.uint8),
        tickers=["A", "B", "C"],
    )
    panel.exit_state[0, 0] = 3
    panel.carry_sessions[0, 0] = 1  # A entered d1 cannot release until d3.
    ranked = [np.asarray([0, 1]), np.asarray([2, 3])]
    overlap = mod.event_overlap_diagnostics(panel, ranked, [d1, d2], 0, 1, calendar)
    assert overlap["overlapping_reselection_rows"] == 1
    sequential, state = mod.sequential_h1_fixed_sleeve_selection(
        panel, ranked, [d1, d2], 2, calendar
    )
    assert sequential[0].tolist() == [0, 1]
    assert sequential[1].tolist() == [3]  # held A skipped; free sleeve orders B
    assert state["duplicate_rows_skipped"] == 1
    assert state["unavailable_sleeve_days"] == 1
    assert state["no_duplicate_ticker_asserted"] is True


def test_sequential_h1_explicitly_exits_before_same_open_reentry():
    calendar = _calendar(6)
    d1, d2 = int(calendar[1]), int(calendar[2])
    panel = mod.Panel(
        dates=np.asarray([d1, d2], dtype=np.int32),
        ticker_id=np.asarray([0, 0], dtype=np.uint16),
        board=np.zeros(2, dtype=np.uint8), era=np.zeros(2, dtype=np.uint8),
        x=np.zeros((2, len(mod.FEATURE_NAMES)), dtype=np.float32),
        y_tolerant=np.zeros(2, dtype=bool), y_strict=np.zeros(2, dtype=bool),
        target_state=np.zeros(2, dtype=np.uint8), fill_state=np.zeros(2, dtype=np.uint8),
        gross_returns=np.zeros((2, len(mod.HORIZONS)), dtype=np.float32),
        exit_state=np.zeros((2, len(mod.HORIZONS)), dtype=np.uint8),
        carry_sessions=np.zeros((2, len(mod.HORIZONS)), dtype=np.uint8), tickers=["A"],
    )
    sequential, state = mod.sequential_h1_fixed_sleeve_selection(
        panel, [np.asarray([0]), np.asarray([1])], [d1, d2], 1, calendar,
    )
    assert [rows.tolist() for rows in sequential] == [[0], [1]]
    assert state["duplicate_rows_skipped"] == 0
    assert state["same_open_exit_then_reentry"].startswith("explicitly_allowed")


def test_h1_book_uses_fixed_K_denominator_and_h3_h5_are_event_only():
    calendar = _calendar(4)
    day = int(calendar[1])
    panel = mod.Panel(
        dates=np.asarray([day, day], dtype=np.int32),
        ticker_id=np.asarray([0, 1], dtype=np.uint16),
        board=np.zeros(2, dtype=np.uint8), era=np.zeros(2, dtype=np.uint8),
        x=np.zeros((2, len(mod.FEATURE_NAMES)), dtype=np.float32),
        y_tolerant=np.asarray([True, False]), y_strict=np.asarray([True, False]),
        target_state=np.zeros(2, dtype=np.uint8),
        fill_state=np.asarray([0, 1], dtype=np.uint8),
        gross_returns=np.asarray([[0.10, 0.20, 0.30], [0.90, 0.90, 0.90]], dtype=np.float32),
        exit_state=np.asarray([[0, 0, 2], [1, 1, 1]], dtype=np.uint8),
        carry_sessions=np.zeros((2, len(mod.HORIZONS)), dtype=np.uint8), tickers=["A", "B"],
    )
    result = mod.topk_metrics(
        panel, np.ones(2, dtype=bool), np.asarray([0.9, 0.8]), panel.y_tolerant, calendar,
    )["top_10"]
    h1 = result["sequential_H1_fixed_K_sleeve_book"]
    assert h1["cost_grid"]["0"]["day_weighted_fixed_sleeve_mean"] == pytest.approx(0.01)
    assert result["event_level_cohort_returns"]["H3_next_open"]["status"].endswith(
        "NOT_A_CAPITAL_BOOK"
    )
    assert result["event_level_cohort_returns"]["H5_next_open"]["status"].endswith(
        "NOT_A_CAPITAL_BOOK"
    )


def test_damped_calibration_solver_recovers_a_known_synthetic_slope():
    rng = np.random.default_rng(20260808)
    logit = rng.normal(size=80_000)
    expected = np.asarray([-1.25, 1.60])
    probability = mod.sigmoid(expected[0] + expected[1] * logit)
    outcome = rng.random(len(logit)) < probability
    fitted = mod.fit_two_parameter_logistic(logit, outcome)
    assert fitted[0] == pytest.approx(expected[0], abs=0.04)
    assert fitted[1] == pytest.approx(expected[1], abs=0.04)


def test_month_block_bootstrap_is_deterministic_and_date_blocked():
    dates = pd.bdate_range("2025-01-02", "2025-03-31").to_numpy(dtype="datetime64[D]").astype(np.int32)
    values = np.linspace(-0.02, 0.03, len(dates))
    first = mod.month_block_bootstrap_mean(values, dates, replicates=200, seed=7)
    second = mod.month_block_bootstrap_mean(values, dates, replicates=200, seed=7)
    assert first == second
    assert first["months"] == 3
    assert first["point"] == pytest.approx(float(values.mean()))
    assert first["p2_5"] <= first["median"] <= first["p97_5"]


def test_tolerant_definition_rides_beside_strict():
    days = np.asarray([mod._day("2026-08-06"), mod._day("2026-08-07")], dtype=np.int32)
    frame = pd.DataFrame({"open": [10.0, 10.5], "close": [10.0, 10.98],
                          "high": [10.0, 11.0], "low": [10.0, 10.4], "volume": [1, 1]},
                         index=pd.DatetimeIndex(days.astype("datetime64[D]")))
    limits = mod.limit_arrays(frame, "main", days)
    assert limits["upper"][1] == pytest.approx(11.0)
    assert bool(limits["tolerant"][1]) is True
    assert bool(limits["strict"][1]) is False
    zero_volume = frame.copy()
    zero_volume.iloc[1, zero_volume.columns.get_loc("volume")] = 0
    unavailable = mod.limit_arrays(zero_volume, "main", days)
    assert bool(unavailable["positive_volume"][1]) is False
    assert bool(unavailable["valid"][1]) is False
    assert bool(unavailable["tolerant"][1]) is False


def test_split_purges_last_ten_common_sessions_from_preceding_blocks():
    calendar = pd.bdate_range("2019-12-01", "2020-02-01").to_numpy(dtype="datetime64[D]").astype(np.int32)
    dates = calendar.copy()
    codes, receipt = mod.split_codes(dates, calendar)
    train_days = calendar[calendar <= mod._day("2019-12-31")]
    assert np.all(codes[np.isin(dates, train_days[-10:])] == 0)
    assert receipt["dates"][mod.SPLIT_NAMES[1]] == [mod._iso(d) for d in train_days[-10:]]


def test_observed_calendar_includes_known_missing_composite_session_and_fails_closed():
    calendar = mod.load_calendar()
    anchor = mod._day("2014-12-25")
    assert anchor in calendar
    broken = calendar[calendar != anchor]
    with pytest.raises(mod.IntegrityError, match="completeness anchors"):
        mod.validate_calendar_days(broken)
    frozen = calendar[calendar >= mod._day("2011-01-01")]
    assert mod.validate_calendar_consensus(frozen, frozen.copy())["set_identical"] is True
    with pytest.raises(mod.IntegrityError, match="consensus mismatch"):
        mod.validate_calendar_consensus(frozen, frozen[:-1])


def _probability_snapshot(
    probability: float = 0.1, *, signal_date: str = "2026-08-07",
    entry_session: str = "2026-08-10", names: int = 1,
) -> list[dict]:
    tickers = [f"{index + 1:06d}.SZ" for index in range(names)]
    universe_id = mod.canonical_hash({"signal_date": signal_date, "tickers": tickers})
    common_hash = mod.canonical_hash({"fixture": signal_date})
    rows = []
    for model_version in sorted(mod.EXPECTED_FORWARD_MODEL_VERSIONS):
        for rank, ticker in enumerate(tickers, 1):
            rows.append({
                "signal_date": signal_date,
                "decision_available_at": f"{signal_date}T15:00:00+08:00",
                "entry_session": entry_session,
                "entry_rule": "opening_auction_order_queue_cushion_0.2pct",
                "ticker": ticker, "probability": probability,
                "model_version": model_version, "era": "main_10", "board": "main",
                "universe_id": universe_id, "limit_definition": "tolerant_0.2pct_primary",
                "universe_size": names, "config_hash": common_hash, "source_hash": common_hash,
                "definition_hash": common_hash, "model_hash": common_hash,
                "fillable_state": "unknown_pending",
                "selection_state": "selected_top20" if rank <= 20 else "not_selected_no_fire",
                "selection_rank": rank, "outcome_state": "pending",
                "authority": "context_display_only",
            })
    return rows


def _event_grade(row: dict) -> dict:
    source_hash = mod.canonical_hash({"fixture": "event-grade"})
    return {
        **{key: row[key] for key in mod.PROBABILITY_KEY},
        "entry_session": row["entry_session"], "grade_kind": "event", "horizon": "EVENT_D",
        "graded_at": "2026-08-10T16:00:00+08:00",
        "grade_observed_session": "2026-08-10",
        "ledger_schema_version": "cn_limit_alpha_grade.v2", "source_hash": source_hash,
        "fill_decided_at": "2026-08-10T09:31:00+08:00",
        "entry_fill_state": "missing_halted_no_fill", "event_state": "missing_halted_non_event",
        "event_outcome": False, "authority": "context_display_only",
    }


def _execution_grade(row: dict) -> dict:
    source_hash = mod.canonical_hash({"fixture": "execution-grade"})
    return {
        **{key: row[key] for key in mod.PROBABILITY_KEY},
        "entry_session": row["entry_session"], "grade_kind": "execution_return",
        "horizon": "H1_next_open", "graded_at": "2026-08-11T16:00:00+08:00",
        "grade_observed_session": "2026-08-11",
        "ledger_schema_version": "cn_limit_alpha_grade.v2", "source_hash": source_hash,
        "fill_decided_at": "2026-08-10T09:31:00+08:00",
        "entry_fill_state": "missing_halted_no_fill",
        "scheduled_exit_session": "2026-08-11", "realized_exit_session": None,
        "exit_state": "not_entered_missing_halted_no_fill", "event_outcome": False,
        "gross_return": None,
        "net_return_bps_grid": {str(cost): None for cost in mod.COST_BPS},
        "book_contribution_return": 0.0,
        "authority": "context_display_only",
    }


def test_probability_ledger_is_nightly_keep_first_and_immutable(tmp_path):
    path = tmp_path / "probabilities.jsonl"
    rows = _probability_snapshot()
    with pytest.raises(mod.IntegrityError, match="nightly"):
        mod.append_probability_snapshot(path, rows, lane="render")
    assert mod.append_probability_snapshot(path, rows, lane="nightly") == 3
    assert mod.append_probability_snapshot(path, rows, lane="nightly") == 0
    mutated_probability = [dict(row) for row in rows]
    mutated_probability[0]["probability"] = 0.2
    with pytest.raises(mod.IntegrityError, match="mutation"):
        mod.append_probability_snapshot(path, mutated_probability, lane="nightly")
    corrected_calendar = [dict(row) for row in rows]
    for row in corrected_calendar:
        row["entry_session"] = "2026-08-11"
    with pytest.raises(mod.IntegrityError, match="mutation"):
        mod.append_probability_snapshot(path, corrected_calendar, lane="nightly")
    assert {row["probability"] for row in mod.load_jsonl(path)} == {0.1}


def test_probability_ledger_refuses_a_partial_full_population_snapshot(tmp_path):
    rows = _probability_snapshot()
    for row in rows:
        row["universe_size"] = 2
    with pytest.raises(mod.IntegrityError, match="incomplete"):
        mod.append_probability_snapshot(tmp_path / "probabilities.jsonl", rows, lane="nightly")


def test_probability_ledger_validates_model_set_authority_probability_and_universe(tmp_path):
    rows = _probability_snapshot()
    with pytest.raises(mod.IntegrityError, match="expected model set"):
        mod.append_probability_snapshot(tmp_path / "models.jsonl", rows[:-1], lane="nightly")
    bad_authority = [dict(row) for row in rows]
    bad_authority[0]["authority"] = "trade"
    with pytest.raises(mod.IntegrityError, match="authority"):
        mod.append_probability_snapshot(tmp_path / "authority.jsonl", bad_authority, lane="nightly")
    bad_probability = [dict(row) for row in rows]
    bad_probability[0]["probability"] = float("nan")
    with pytest.raises(mod.IntegrityError, match="finite"):
        mod.append_probability_snapshot(tmp_path / "probability.jsonl", bad_probability, lane="nightly")
    bad_universe = [dict(row) for row in rows]
    bad_universe[0]["universe_id"] = mod.canonical_hash({"wrong": True})
    with pytest.raises(mod.IntegrityError, match="recompute"):
        mod.append_probability_snapshot(tmp_path / "universe.jsonl", bad_universe, lane="nightly")


def test_probability_ledger_rejects_duplicate_or_malformed_existing_store(tmp_path):
    rows = _probability_snapshot()
    duplicate_path = tmp_path / "duplicate.jsonl"
    mod.atomic_write_jsonl(duplicate_path, [*rows, rows[0]])
    with pytest.raises(mod.IntegrityError, match="duplicate probability key in existing"):
        mod.append_probability_snapshot(duplicate_path, rows, lane="nightly")
    malformed_path = tmp_path / "malformed.jsonl"
    malformed = [dict(row) for row in rows]
    del malformed[0]["authority"]
    mod.atomic_write_jsonl(malformed_path, malformed)
    with pytest.raises(mod.IntegrityError, match="existing probability row missing"):
        mod.append_probability_snapshot(malformed_path, rows, lane="nightly")


def test_probability_grades_are_separate_and_require_a_probability(tmp_path):
    probabilities = tmp_path / "probabilities.jsonl"
    grades = tmp_path / "grades.jsonl"
    rows = _probability_snapshot()
    mod.append_probability_snapshot(probabilities, rows, lane="nightly")
    event_grades = [_event_grade(row) for row in rows]
    observed = np.asarray([
        mod._day("2026-08-07"), mod._day("2026-08-10"), mod._day("2026-08-11"),
    ], dtype=np.int32)
    assert mod.append_probability_grades(
        probabilities, grades, event_grades, lane="nightly", observed_calendar_days=observed,
    ) == 3
    assert mod.append_probability_grades(
        probabilities, grades, event_grades, lane="nightly", observed_calendar_days=observed,
    ) == 0
    execution = _execution_grade(rows[0])
    assert mod.append_probability_grades(
        probabilities, grades, [execution], lane="nightly", observed_calendar_days=observed,
    ) == 1
    assert mod.load_jsonl(probabilities)[0]["outcome_state"] == "pending"


def test_selected_but_unfilled_execution_grade_is_no_trade_not_flat_trade(tmp_path):
    probabilities = tmp_path / "probabilities.jsonl"
    rows = _probability_snapshot()
    mod.append_probability_snapshot(probabilities, rows, lane="nightly")
    observed = np.asarray([
        mod._day("2026-08-07"), mod._day("2026-08-10"), mod._day("2026-08-11"),
    ], dtype=np.int32)
    no_trade = _execution_grade(rows[0])
    assert mod.append_probability_grades(
        probabilities, tmp_path / "grades.jsonl", [no_trade], lane="nightly",
        observed_calendar_days=observed,
    ) == 1
    flattened = dict(no_trade)
    flattened["gross_return"] = 0.0
    with pytest.raises(mod.IntegrityError, match="gross_return must be null"):
        mod.append_probability_grades(
            probabilities, tmp_path / "bad-grades.jsonl", [flattened], lane="nightly",
            observed_calendar_days=observed,
        )


def test_event_grades_require_full_population_and_execution_grades_selected_only(tmp_path):
    probabilities = tmp_path / "probabilities.jsonl"
    grades = tmp_path / "grades.jsonl"
    rows = _probability_snapshot(names=21)
    mod.append_probability_snapshot(probabilities, rows, lane="nightly")
    observed = np.asarray([
        mod._day("2026-08-07"), mod._day("2026-08-10"), mod._day("2026-08-11"),
    ], dtype=np.int32)
    with pytest.raises(mod.IntegrityError, match="coverage incomplete"):
        mod.append_probability_grades(
            probabilities, grades, [_event_grade(rows[0])], lane="nightly",
            observed_calendar_days=observed,
        )
    unselected = next(row for row in rows if row["selection_state"] == "not_selected_no_fire")
    with pytest.raises(mod.IntegrityError, match="selected order"):
        mod.append_probability_grades(
            probabilities, grades, [_execution_grade(unselected)], lane="nightly",
            observed_calendar_days=observed,
        )


def test_grade_clock_requires_exact_observed_successors(tmp_path):
    probabilities = tmp_path / "probabilities.jsonl"
    rows = _probability_snapshot()
    mod.append_probability_snapshot(probabilities, rows, lane="nightly")
    incomplete_clock = np.asarray([
        mod._day("2026-08-07"), mod._day("2026-08-11"),
    ], dtype=np.int32)
    with pytest.raises(mod.IntegrityError, match="exact observed"):
        mod.append_probability_grades(
            probabilities, tmp_path / "grades.jsonl", [_execution_grade(rows[0])],
            lane="nightly", observed_calendar_days=incomplete_clock,
        )


def test_frozen_seed_calendar_fails_closed_outside_the_one_pinned_snapshot():
    assert mod.frozen_seed_entry_session(mod._day("2026-08-07")) == mod._day("2026-08-10")
    with pytest.raises(mod.IntegrityError, match="authoritative annual exchange calendar"):
        mod.frozen_seed_entry_session(mod._day("2024-02-14"))


def test_jsonl_bridge_refuses_an_eleventh_signal_session(tmp_path):
    path = tmp_path / "probabilities.jsonl"
    signals = pd.bdate_range("2026-01-05", periods=11)
    entries = pd.bdate_range("2026-01-06", periods=11)
    for index in range(10):
        rows = _probability_snapshot(
            signal_date=signals[index].strftime("%Y-%m-%d"),
            entry_session=entries[index].strftime("%Y-%m-%d"),
        )
        assert mod.append_probability_snapshot(path, rows, lane="nightly") == 3
    rows = _probability_snapshot(
        signal_date=signals[10].strftime("%Y-%m-%d"),
        entry_session=entries[10].strftime("%Y-%m-%d"),
    )
    with pytest.raises(mod.IntegrityError, match="session cap"):
        mod.append_probability_snapshot(path, rows, lane="nightly")


def test_forward_seed_contains_full_selected_and_no_fire_population():
    x = np.zeros(len(mod.FEATURE_NAMES), dtype=np.float32)
    latest = [{"ticker": f"{i:06d}.SZ", "board": "main", "era": "main_10",
               "signal_day": int(mod._day("2026-08-07")), "x": x.copy()} for i in range(25)]
    scaler = mod.Scaler(mean=np.zeros(5), std=np.ones(5))
    model = mod.LogisticModel("O1", mod.O1_COLS, scaler, np.zeros(6), np.asarray([0.0, 1.0]), 1)
    rows = mod.build_forward_seed(latest, [model], config_hash="c", source_hash="s")
    assert len(rows) == 25
    assert {row["fillable_state"] for row in rows} == {"unknown_pending"}
    assert sum(row["selection_state"] == "selected_top20" for row in rows) == 20
    assert sum(row["selection_state"] == "not_selected_no_fire" for row in rows) == 5
    assert {row["signal_date"] for row in rows} == {"2026-08-07"}
    assert {row["entry_session"] for row in rows} == {"2026-08-10"}
    assert {row["universe_size"] for row in rows} == {25}
    assert all(len(row["definition_hash"]) == 64 for row in rows)


def test_equal_rank_probability_family_is_a_first_class_forward_seed_model():
    x = np.zeros(len(mod.FEATURE_NAMES), dtype=np.float32)
    latest = [{"ticker": f"{i:06d}.SZ", "board": "main", "era": "main_10",
               "signal_day": int(mod._day("2026-08-07")), "x": x.copy()} for i in range(3)]
    knots = np.tile(np.linspace(-1.0, 1.0, 101)[:, None], (1, len(mod.O1_COLS)))
    model = mod.EqualRankModel("O1_fixed_equal_rank_blend", mod.O1_COLS, knots,
                               np.asarray([0.0, 1.0]))
    rows = mod.build_forward_seed(latest, [model], config_hash="c", source_hash="s")
    assert len(rows) == 3
    assert {row["model_version"] for row in rows} == {
        f"{mod.MODEL_VERSION}:O1_fixed_equal_rank_blend"
    }
    assert len({row["model_hash"] for row in rows}) == 1
    assert all(0.0 < row["probability"] < 1.0 for row in rows)
