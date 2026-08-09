from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "research" / "cn_limit_band_progress_w2.py"
SPEC = importlib.util.spec_from_file_location("cn_limit_band_progress_w2", MODULE_PATH)
assert SPEC and SPEC.loader
bp = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bp
SPEC.loader.exec_module(bp)


def state(
    *, high: float, close: float, pre_close: float = 10.0, up_limit: float = 11.0
):
    return bp.classify_band_state(
        pre_close=pre_close, high=high, close=close, up_limit=up_limit
    )


def test_exchange_half_up_tick_differs_from_python_ties_to_even() -> None:
    assert bp.half_up_yuan_tick("2.675") == 2.68
    assert round(2.675, 2) == 2.67
    assert bp.half_up_limit_from_tick("0.95", "0.10") == 1.05
    assert round(0.95 * 1.10, 2) == 1.04
    assert bp.half_up_limit_from_tick("0.70", "0.05") == 0.74
    assert bp.half_up_limit_from_tick("1.00", "0.10", side="down") == 0.90


@pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf"), "bad"])
def test_half_up_rejects_invalid_prices(bad: object) -> None:
    with pytest.raises(ValueError):
        bp.half_up_yuan_tick(bad)


def test_limit_reconstruction_requires_a_legal_prior_tick() -> None:
    with pytest.raises(ValueError, match="not aligned"):
        bp.half_up_limit_from_tick("10.001", "0.10")
    with pytest.raises(ValueError, match="side"):
        bp.half_up_limit_from_tick("10.00", "0.10", side="sideways")


def test_strict_seal_is_not_conflated_with_tolerant_only_close() -> None:
    strict = state(high=11.00, close=11.00)
    assert strict.strict_seal
    assert bp.signal_memberships(strict) == ("S_STRICT",)

    tolerant_touch = state(high=11.00, close=10.99)
    assert not tolerant_touch.strict_seal
    assert tolerant_touch.tolerant_only
    assert tolerant_touch.exact_touch_failed
    assert bp.signal_memberships(tolerant_touch) == ("S_TOL_ONLY", "TF_TOL_ONLY")


@pytest.mark.parametrize(
    ("close", "expected"),
    [
        (10.97, "TF_CP_095_100"),
        (10.90, "TF_CP_080_095"),
        (10.70, "TF_CP_060_080"),
        (10.30, "TF_CP_LT060"),
    ],
)
def test_exact_touch_failed_seal_retreat_buckets_are_frozen(
    close: float, expected: str
) -> None:
    observed = state(high=11.00, close=close)
    assert observed.exact_touch_failed
    memberships = bp.signal_memberships(observed)
    assert memberships == (expected,)


def test_no_touch_high_and_close_progress_are_parallel_marginals() -> None:
    observed = state(high=10.97, close=10.85)
    assert observed.partial_no_touch
    assert bp.signal_memberships(observed) == (
        "NT_H_095_100",
        "NT_C_080_095",
    )

    high_only = state(high=10.70, close=10.30)
    assert bp.signal_memberships(high_only) == ("NT_H_060_080",)


def test_progress_is_relative_to_vendor_band_span() -> None:
    ten = bp.classify_band_state(pre_close=10, high=10.8, close=10.8, up_limit=11)
    twenty = bp.classify_band_state(pre_close=10, high=10.8, close=10.8, up_limit=12)
    assert ten.close_progress == pytest.approx(0.8)
    assert twenty.close_progress == pytest.approx(0.4)


def test_entry_proxy_keeps_upper_queue_and_missing_rows_cash() -> None:
    assert (
        bp.entry_proxy_state(open_price=10.99, up_limit=11.0, volume=100)
        == "upper_queue_no_fill"
    )
    assert (
        bp.entry_proxy_state(open_price=10.50, up_limit=11.0, volume=100)
        == "daily_tradability_proxy"
    )
    assert (
        bp.entry_proxy_state(open_price=10.50, up_limit=11.0, volume=0)
        == "zero_volume_halt_or_no_trade_no_fill"
    )
    assert (
        bp.entry_proxy_state(
            open_price=None, up_limit=None, volume=None, row_present=False
        )
        == "missing_bar_halt_or_data_missing_no_fill"
    )


def test_exit_clock_is_tplus1_legal_after_dplus1_entry() -> None:
    calendar = pd.date_range("2026-08-03", periods=6, freq="B")
    assert bp.exact_exit_session(
        calendar, signal_date="2026-08-03", exit_id="E1_OPEN"
    ) == pd.Timestamp("2026-08-05")
    assert bp.exact_exit_session(
        calendar, signal_date="2026-08-03", exit_id="E1_CLOSE"
    ) == pd.Timestamp("2026-08-05")
    assert bp.exact_exit_session(
        calendar, signal_date="2026-08-03", exit_id="E3_CLOSE"
    ) == pd.Timestamp("2026-08-07")


def test_run_clusters_use_official_session_adjacency() -> None:
    calendar = pd.to_datetime(["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06"])
    frame = pd.DataFrame(
        {
            "ticker": ["A", "A", "A", "A"],
            "signal_date": ["2026-08-03", "2026-08-04", "2026-08-06", "2026-08-06"],
            "construction_id": ["X", "X", "X", "Y"],
        }
    )
    ids = bp.run_cluster_ids(frame, calendar=calendar).tolist()
    assert ids == ["X:A:1", "X:A:1", "X:A:2", "Y:A:1"]


def test_no_duplicate_state_machine_rejects_until_exit_and_keeps_nonfills_cash() -> (
    None
):
    frame = pd.DataFrame(
        {
            "ticker": ["A", "A", "A", "B"],
            "signal_date": pd.to_datetime(
                ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-03"]
            ),
            "entry_date": pd.to_datetime(
                ["2026-08-04", "2026-08-05", "2026-08-06", "2026-08-04"]
            ),
            "exit_date": pd.to_datetime(
                ["2026-08-05", "2026-08-06", "2026-08-07", None]
            ),
            "entry_state": [
                "daily_tradability_proxy",
                "daily_tradability_proxy",
                "daily_tradability_proxy",
                "upper_queue_no_fill",
            ],
        }
    )
    assert bp.apply_no_duplicate_state_machine(frame).tolist() == [
        "accepted_fill",
        "overlap_rejected_cash",
        "accepted_fill",
        "candidate_nonfill_cash",
    ]


def test_wilson_and_cluster_bootstrap_are_deterministic() -> None:
    low, high = bp.wilson_interval(5, 10)
    assert low == pytest.approx(0.236593090512564)
    assert high == pytest.approx(0.763406909487436)
    values = [0.1, 0.2, -0.1, 0.0]
    clusters = ["a", "a", "b", "c"]
    first = bp.cluster_bootstrap_mean(values, clusters, reps=100, seed=7)
    second = bp.cluster_bootstrap_mean(values, clusters, reps=100, seed=7)
    assert first == second


def test_legacy_audit_reports_rounding_key_delta_but_no_strategy_metrics(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    frame = pd.DataFrame(
        {
            "open": [0.95, 1.00, 1.00],
            "high": [0.95, 1.04, 1.041],
            "close": [0.95, 1.04, 1.041],
            "volume": [100.0, 100.0, 100.0],
        },
        index=pd.to_datetime(["2026-08-03", "2026-08-04", "2026-08-05"]),
    )
    frame.index.name = "Date"
    frame.to_parquet(raw / "600000.SS.parquet")
    audit = bp.legacy_substrate_diagnostic(raw, st_snapshot_path=None)
    assert audit["authority"] == "SUBSTRATE_INVALID_DIAGNOSTIC_ONLY"
    assert audit["counts"]["half_up_vs_legacy_upper_price_diff_rows"] >= 1
    assert audit["counts"]["strict_seal_removed_by_half_up"] == 1
    assert "returns" not in json.dumps(audit).lower()
    assert "strategy" in audit["warning"].lower()


def test_missing_authoritative_planes_emit_deterministic_blocked_receipt(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing"
    kwargs = {
        "daily": missing / "daily",
        "limits": missing / "limits",
        "calendar": missing / "calendar.parquet",
        "security_sessions": missing / "security",
        "legacy_raw": None,
        "st_snapshot": None,
    }
    first = bp.build_receipt(**kwargs)
    second = bp.build_receipt(**kwargs)
    assert first == second
    assert first["status"] == "BLOCKED_SUBSTRATE"
    assert first["verdict"] == "BLOCKED_SUBSTRATE_NO_STRATEGY_MEASUREMENT"
    assert first["strategy_metrics_emitted"] is False
    assert first["return_metrics_emitted"] is False
    assert first["fill_metrics_emitted"] is False
    assert len(first["ore_ledger"]["untested_variants"]) >= 10


def test_schema_seams_still_do_not_authorize_measurement(tmp_path: Path) -> None:
    daily = tmp_path / "daily.parquet"
    limits = tmp_path / "limits.parquet"
    calendar = tmp_path / "calendar.parquet"
    security = tmp_path / "security.parquet"
    pd.DataFrame(
        columns=[
            "ts_code",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "vol",
        ]
    ).to_parquet(daily)
    pd.DataFrame(
        columns=["ts_code", "trade_date", "up_limit", "down_limit"]
    ).to_parquet(limits)
    pd.DataFrame(columns=["cal_date", "is_open"]).to_parquet(calendar)
    pd.DataFrame(
        columns=[
            "ts_code",
            "trade_date",
            "board",
            "rule_cohort",
            "session_eligible",
            "rule_known",
            "no_limit",
            "corporate_action_reference_known",
        ]
    ).to_parquet(security)
    receipt = bp.build_receipt(
        daily=daily,
        limits=limits,
        calendar=calendar,
        security_sessions=security,
        legacy_raw=None,
        st_snapshot=None,
    )
    assert receipt["authoritative_substrate"]["all_schema_gates_pass"] is True
    assert receipt["status"] == "CONSTRUCTION_ONLY_ROW_GATES_AND_MEASUREMENT_NOT_RUN"
    assert receipt["strategy_metrics_emitted"] is False


def test_receipt_files_are_byte_deterministic(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    receipt = bp.build_receipt(
        daily=missing / "daily",
        limits=missing / "limits",
        calendar=missing / "calendar",
        security_sessions=missing / "security",
        legacy_raw=None,
        st_snapshot=None,
    )
    json_path = tmp_path / "receipt.json"
    markdown_path = tmp_path / "receipt.md"
    bp.write_receipts(receipt, json_path=json_path, markdown_path=markdown_path)
    first_json = json_path.read_bytes()
    first_markdown = markdown_path.read_bytes()
    bp.write_receipts(receipt, json_path=json_path, markdown_path=markdown_path)
    assert json_path.read_bytes() == first_json
    assert markdown_path.read_bytes() == first_markdown
