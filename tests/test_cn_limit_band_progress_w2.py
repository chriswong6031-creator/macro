from __future__ import annotations

import importlib.util
import json
import shutil
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


def _to_cents(value: float) -> int:
    return round(value * 100)


def state(
    *,
    high: float,
    close: float,
    pre_close: float = 10.0,
    up_limit: float = 11.0,
    down_limit: float = 9.0,
):
    return bp.classify_band_state(
        pre_close_cents=_to_cents(pre_close),
        open_cents=_to_cents(pre_close),
        high_cents=_to_cents(high),
        low_cents=_to_cents(min(pre_close, close)),
        close_cents=_to_cents(close),
        up_limit_cents=_to_cents(up_limit),
        down_limit_cents=_to_cents(down_limit),
    )


def test_full_a_adapter_defaults_bind_to_frozen_sol_spine_contract() -> None:
    assert bp.DEFAULT_SPINE_ROOT == ROOT / "data" / "china_tushare_spine"
    assert bp.DEFAULT_EVENT_DAILY == bp.DEFAULT_SPINE_ROOT / "event_daily"
    assert bp.DEFAULT_CALENDAR == (
        bp.DEFAULT_SPINE_ROOT / "reference" / "market_sessions.parquet"
    )
    assert bp.DEFAULT_SECURITY_MASTER == (
        bp.DEFAULT_SPINE_ROOT / "reference" / "security_master.parquet"
    )
    assert bp.DEFAULT_MANIFEST_SCHEMA.name == (
        "cn_tushare_a_share_spine_manifest.v1.schema.json"
    )


def test_private_spine_root_derives_the_v1_relative_layout(tmp_path: Path) -> None:
    private_root = tmp_path / "licensed-private-store"
    args = bp.parse_args(["--spine-root", str(private_root), "--skip-legacy-audit"])
    assert args.store == private_root
    assert args.daily == private_root / "daily"
    assert args.limits == private_root / "stk_limit"
    assert args.event_daily == private_root / "event_daily"
    assert args.calendar == private_root / "reference" / "market_sessions.parquet"
    assert args.security_master == (
        private_root / "reference" / "security_master.parquet"
    )
    assert args.manifest == private_root / "completeness_manifest.json"
    assert args.manifest_schema == bp.DEFAULT_MANIFEST_SCHEMA
    with pytest.raises(SystemExit):
        bp.parse_args(
            [
                "--spine-root",
                str(private_root),
                "--daily",
                str(tmp_path / "split-daily"),
            ]
        )


def test_exchange_half_up_tick_differs_from_python_ties_to_even() -> None:
    assert bp.half_up_yuan_tick("2.675") == 2.68
    assert round(2.675, 2) == 2.67
    assert bp.half_up_limit_from_tick("0.95", "0.10") == 1.05
    assert round(0.95 * 1.10, 2) == 1.04
    assert bp.half_up_limit_from_tick("0.70", "0.05") == 0.74
    assert bp.half_up_limit_from_tick("1.00", "0.10", side="down") == 0.90
    assert bp.half_up_limit_from_tick("0.01", "0.10") == 0.02
    assert bp.half_up_limit_from_tick("0.01", "0.10", side="down") == 0.01


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


def test_vendor_event_classification_uses_equality_and_quarantines_overshoots() -> None:
    exact = state(high=11.00, close=11.00)
    assert exact.strict_seal is True
    assert exact.exact_touch is True

    with pytest.raises(ValueError, match="outside exact vendor bounds"):
        bp.classify_band_state(
            pre_close_cents=1000,
            open_cents=1000,
            high_cents=1101,
            low_cents=995,
            close_cents=1100,
            up_limit_cents=1100,
            down_limit_cents=900,
        )
    with pytest.raises(ValueError, match="outside exact vendor bounds"):
        bp.classify_band_state(
            pre_close_cents=1000,
            open_cents=1000,
            high_cents=1050,
            low_cents=899,
            close_cents=1030,
            up_limit_cents=1100,
            down_limit_cents=900,
        )


def test_vendor_event_classification_requires_integer_cents() -> None:
    with pytest.raises(ValueError, match="positive integer CNY cents"):
        bp.classify_band_state(
            pre_close_cents=1000,
            open_cents=1000,
            high_cents=1099.5,
            low_cents=995,
            close_cents=1090,
            up_limit_cents=1100,
            down_limit_cents=900,
        )


def test_one_cent_floor_can_equal_pre_close_without_invalidating_bar() -> None:
    observed = bp.classify_band_state(
        pre_close_cents=1,
        open_cents=1,
        high_cents=1,
        low_cents=1,
        close_cents=1,
        up_limit_cents=2,
        down_limit_cents=1,
    )
    assert observed.partial_no_touch is True
    assert observed.high_progress == 0.0
    assert observed.close_progress == 0.0


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
    ten = bp.classify_band_state(
        pre_close_cents=1000,
        open_cents=1000,
        high_cents=1080,
        low_cents=1000,
        close_cents=1080,
        up_limit_cents=1100,
        down_limit_cents=900,
    )
    twenty = bp.classify_band_state(
        pre_close_cents=1000,
        open_cents=1000,
        high_cents=1080,
        low_cents=1000,
        close_cents=1080,
        up_limit_cents=1200,
        down_limit_cents=800,
    )
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


def test_run_clusters_use_attested_session_adjacency() -> None:
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
        "store": missing,
        "daily": missing / "daily",
        "limits": missing / "limits",
        "event_daily": missing / "event_daily",
        "calendar": missing / "calendar.parquet",
        "security_master": missing / "security_master.parquet",
        "stock_st": missing / "stock_st",
        "coverage": missing / "coverage.parquet",
        "manifest": missing / "completeness_manifest.json",
        "manifest_schema": missing / "manifest.schema.json",
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


def _file_receipt(store: Path, path: Path, *, partition: bool = False) -> dict:
    payload = {
        "path": path.relative_to(store).as_posix(),
        "sha256": bp._sha256_file(path),
        "semantic_sha256": "0" * 64,
        "bytes": path.stat().st_size,
        "rows": len(pd.read_parquet(path)),
        "duplicate_key_rows": 0,
    }
    if partition:
        payload.update({"min_date": "2026-08-07", "max_date": "2026-08-07"})
    return payload


def _write_synthetic_full_a_contract(
    tmp_path: Path, *, include_measurement_overlay: bool = False
) -> dict[str, Path]:
    store = tmp_path / "china_tushare_spine"
    relative = Path("year=2026/month=08/part.parquet")
    daily = store / "daily" / relative
    limits = store / "stk_limit" / relative
    event = store / "event_daily" / relative
    stock_st = store / "stock_st" / relative
    calendar = store / "reference" / "market_sessions.parquet"
    security = store / "reference" / "security_master.parquet"
    coverage = store / "coverage" / "daily_security_coverage.parquet"
    for path in (daily, limits, event, stock_st, calendar, security, coverage):
        path.parent.mkdir(parents=True, exist_ok=True)

    identity = {
        "security_id": "CN-XSHG-600000",
        "ticker": "600000.SS",
        "source_ts_code": "600000.SH",
        "exchange": "SSE",
        "board": "main",
        "trade_date": "2026-08-07",
        "market_session_position": 1,
    }
    daily_row = {
        **identity,
        "open_cents": 1000,
        "high_cents": 1098,
        "low_cents": 995,
        "close_cents": 1090,
        "pre_close_cents": 1000,
        "volume_lots": 1000.0,
        "positive_volume": True,
        "price_source_basis": "tushare.daily_unadjusted_nominal",
    }
    limit_row = {
        **identity,
        "pre_close_cents": 1000,
        "up_limit_cents": 1100,
        "down_limit_cents": 900,
        "source_limits_present": True,
        "limit_price_source": "tushare.stk_limit_exact_daily",
    }
    event_row = {
        **daily_row,
        "limit_pre_close_cents": 1000,
        "up_limit_cents": 1100,
        "down_limit_cents": 900,
        "source_limits_present": True,
        "event_eligible": True,
        "touched_up": False,
        "sealed_up": False,
        "touched_down": False,
        "sealed_down": False,
        "event_price_authority": "tushare.daily_unadjusted_plus_stk_limit_exact_daily",
        "calculated_limit_role": "validator_only_never_event_authority",
    }
    if include_measurement_overlay:
        event_row.update(
            {
                "rule_cohort": "main_10pct",
                "session_eligible": True,
                "corporate_action_reference_known": True,
                "no_limit": False,
                "ipo_no_limit_state_known": True,
                "st_membership_state": "known_not_st",
                "st_provenance": "tushare.stock_st_exact_daily",
            }
        )
    pd.DataFrame([daily_row]).to_parquet(daily, index=False)
    pd.DataFrame([limit_row]).to_parquet(limits, index=False)
    pd.DataFrame([event_row]).to_parquet(event, index=False)
    pd.DataFrame(
        [
            {
                **identity,
                "is_st": False,
                "st_provenance": "tushare.stock_st_exact_daily",
            }
        ]
    ).to_parquet(stock_st, index=False)
    pd.DataFrame(
        [
            {
                "trade_date": "2026-08-07",
                "market_session_position": 1,
                "calendar_provenance": "tushare.trade_cal:SSE=SZSE",
                "bse_calendar_provenance": "derived_from_attested_SSE_SZSE_consensus",
            }
        ]
    ).to_parquet(calendar, index=False)
    pd.DataFrame(
        [
            {
                "security_id": "CN-XSHG-600000",
                "ticker": "600000.SS",
                "source_ts_code": "600000.SH",
                "exchange": "SSE",
                "board": "main",
                "list_status": "L",
                "list_date": "1999-01-01",
                "delist_date": None,
                "effective_from": "1999-01-01",
                "effective_to": None,
            }
        ]
    ).to_parquet(security, index=False)
    pd.DataFrame(
        [
            {
                "trade_date": "2026-08-07",
                "eligible_n": 1,
                "daily_n": 1,
                "positive_volume_n": 1,
                "suspended_n": 0,
                "unexplained_missing_n": 0,
                "unexpected_daily_n": 0,
            }
        ]
    ).to_parquet(coverage, index=False)

    daily_receipt = _file_receipt(store, daily, partition=True)
    limit_receipt = _file_receipt(store, limits, partition=True)
    st_receipt = _file_receipt(store, stock_st, partition=True)
    event_receipt = _file_receipt(store, event)
    manifest = {
        "schema_version": bp.MANIFEST_SCHEMA_VERSION,
        "authority": "context_only",
        "source": "tushare_pro",
        "requested_range": {"start": "2011-01-01", "end": "2026-08-07"},
        "complete": True,
        "reference": {
            "ready": True,
            "security_master": _file_receipt(store, security),
            "market_sessions": _file_receipt(store, calendar),
        },
        "endpoints": {
            "daily": {
                "required": True,
                "complete": True,
                "partitions": [daily_receipt],
            },
            "stk_limit": {
                "required": True,
                "complete": True,
                "partitions": [limit_receipt],
            },
            "stock_st": {
                "required": True,
                "complete": True,
                "partitions": [st_receipt],
            },
        },
        "canonical_event_substrate": {
            "ready": True,
            "daily_source": "tushare.daily_unadjusted_nominal",
            "limit_source": "tushare.stk_limit_exact_daily",
            "integer_price_unit": "CNY_cents",
            "calculated_limit_role": "validator_only_never_event_authority",
            "partitions": [event_receipt],
        },
        "daily_security_coverage": {"complete": True},
    }
    manifest["manifest_identity_sha256"] = bp._manifest_identity_sha256(manifest)
    manifest_path = store / "completeness_manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    schema_path = tmp_path / "manifest.schema.json"
    schema_path.write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": [
                    "schema_version",
                    "authority",
                    "source",
                    "requested_range",
                    "complete",
                    "reference",
                    "endpoints",
                    "canonical_event_substrate",
                    "daily_security_coverage",
                    "manifest_identity_sha256",
                ],
                "properties": {
                    "schema_version": {"const": bp.MANIFEST_SCHEMA_VERSION},
                    "manifest_identity_sha256": {"pattern": "^[0-9a-f]{64}$"},
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return {
        "store": store,
        "daily": store / "daily",
        "limits": store / "stk_limit",
        "event_daily": store / "event_daily",
        "calendar": calendar,
        "security_master": security,
        "stock_st": store / "stock_st",
        "coverage": coverage,
        "manifest": manifest_path,
        "manifest_schema": schema_path,
    }


def _pin_synthetic_schema(monkeypatch: pytest.MonkeyPatch, schema_path: Path) -> None:
    monkeypatch.setattr(bp, "DEFAULT_MANIFEST_SCHEMA", schema_path)
    monkeypatch.setattr(bp, "MANIFEST_SCHEMA_SHA256", bp._sha256_file(schema_path))


def test_canonical_full_a_contract_binds_but_missing_overlay_stays_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _write_synthetic_full_a_contract(tmp_path)
    _pin_synthetic_schema(monkeypatch, paths["manifest_schema"])
    receipt = bp.build_receipt(
        **paths,
        legacy_raw=None,
        st_snapshot=None,
    )
    substrate = receipt["authoritative_substrate"]
    assert substrate["contract_snapshot_commit"] == "b2548fdc095"
    assert substrate["contract_snapshot_has_readiness_authority"] is False
    assert substrate["all_canonical_schema_gates_pass"] is True
    assert substrate["layout_binding"]["pass"] is True
    assert substrate["manifest_gate_pass"] is True
    assert substrate["manifest"]["receipt_count"] == 6
    assert substrate["measurement_overlay"]["pass"] is False
    assert substrate["measurement_overlay"]["missing_columns"] == sorted(
        bp.MEASUREMENT_OVERLAY_REQUIRED
    )
    assert substrate["ready_for_measurement"] is False
    assert substrate["row_level_measurement_gates_run"] is False
    assert substrate["row_level_measurement_gates_pass"] is False
    assert receipt["status"] == "BLOCKED_SUBSTRATE"
    assert receipt["strategy_metrics_emitted"] is False
    assert receipt["transition_rates_emitted"] is False
    assert receipt["return_metrics_emitted"] is False
    assert receipt["fill_metrics_emitted"] is False
    assert (
        receipt["construction_protocol"][
            "outcome_measurement_observed_before_corrections"
        ]
        is False
    )
    assert "rule_cohort" in receipt["blocker"]


def test_authoritative_event_row_recomputes_exact_flags_and_rejects_disagreement(
    tmp_path: Path,
) -> None:
    paths = _write_synthetic_full_a_contract(tmp_path)
    row = (
        pd.read_parquet(next(paths["event_daily"].rglob("*.parquet"))).iloc[0].to_dict()
    )
    observed = bp.classify_authoritative_event_row(row)
    assert observed.partial_no_touch is True
    assert bp.signal_memberships(observed) == (
        "NT_H_095_100",
        "NT_C_080_095",
    )

    row["high_cents"] = 1100
    row["touched_up"] = False
    with pytest.raises(ValueError, match="flags disagree"):
        bp.classify_authoritative_event_row(row)

    row["touched_up"] = True
    observed = bp.classify_authoritative_event_row(row)
    assert observed.exact_touch_failed is True


def test_complete_contract_still_cannot_authorize_without_row_reattestation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _write_synthetic_full_a_contract(tmp_path, include_measurement_overlay=True)
    _pin_synthetic_schema(monkeypatch, paths["manifest_schema"])
    receipt = bp.build_receipt(**paths, legacy_raw=None, st_snapshot=None)
    substrate = receipt["authoritative_substrate"]
    assert substrate["measurement_overlay"]["pass"] is True
    assert substrate["shape_ready_for_row_attestation"] is True
    assert substrate["generation_binding"]["pass"] is False
    assert substrate["contract_ready_for_row_attestation"] is False
    assert substrate["row_level_measurement_gates_run"] is False
    assert substrate["row_level_measurement_gates_pass"] is False
    assert substrate["ready_for_measurement"] is False
    assert "row re-attestation has not run" in receipt["blocker"]
    assert receipt["strategy_metrics_emitted"] is False


def test_manifest_identity_or_file_hash_failure_keeps_gate_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _write_synthetic_full_a_contract(tmp_path)
    _pin_synthetic_schema(monkeypatch, paths["manifest_schema"])
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    manifest["complete"] = False
    paths["manifest"].write_text(json.dumps(manifest), encoding="utf-8")
    gate = bp.authoritative_substrate_gate(**paths)
    assert gate["manifest"]["schema_valid"] is True
    assert gate["manifest"]["identity_valid"] is False
    assert gate["manifest_gate_pass"] is False
    assert gate["ready_for_measurement"] is False


def test_plane_override_cannot_split_schema_gate_from_manifest_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _write_synthetic_full_a_contract(tmp_path, include_measurement_overlay=True)
    _pin_synthetic_schema(monkeypatch, paths["manifest_schema"])
    outside_daily = tmp_path / "outside" / "daily"
    shutil.copytree(paths["daily"], outside_daily)
    split_paths = {**paths, "daily": outside_daily}
    gate = bp.authoritative_substrate_gate(**split_paths)
    assert gate["gates"]["tushare_unadjusted_daily"]["pass"] is True
    assert gate["manifest_gate_pass"] is True
    assert gate["layout_binding"]["bindings"]["daily"]["pass"] is False
    assert gate["layout_binding"]["pass"] is False
    assert gate["shape_ready_for_row_attestation"] is False
    assert gate["ready_for_measurement"] is False


def test_manifest_schema_is_hash_pinned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _write_synthetic_full_a_contract(tmp_path)
    _pin_synthetic_schema(monkeypatch, paths["manifest_schema"])
    paths["manifest_schema"].write_text(
        paths["manifest_schema"].read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    gate = bp.authoritative_substrate_gate(**paths)
    assert gate["manifest"]["schema_valid"] is True
    assert gate["manifest"]["schema_binding"]["sha256_matches"] is False
    assert gate["manifest_gate_pass"] is False
    assert gate["ready_for_measurement"] is False


def test_receipt_files_are_byte_deterministic(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    receipt = bp.build_receipt(
        store=missing,
        daily=missing / "daily",
        limits=missing / "limits",
        event_daily=missing / "event_daily",
        calendar=missing / "calendar",
        security_master=missing / "security_master",
        stock_st=missing / "stock_st",
        coverage=missing / "coverage",
        manifest=missing / "manifest",
        manifest_schema=missing / "manifest_schema",
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
