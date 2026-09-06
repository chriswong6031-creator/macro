"""Tests for engine.stock_identity.analog_pit (packet A-F10-W2-1).

Synthetic frames only -- fast, offline, no committed-artifact dependency
(idiom from tests/test_stock_identity_state_episodes.py). Test 22 binds to
the real pilot catalog when present and skips cleanly when it is not
(sparse checkout convention, .github/ci/legacy-jobs.yml:951).
"""
from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine.stock_identity import analog_pit as pit
from engine.stock_identity import episodes as ep
from engine.stock_identity.authority import authority_block


def _row(**overrides):
    base = dict(
        symbol="AAA",
        price_plane_id="stock_identity_ohlcv_v1",
        episode_type="reset_decline",
        tier=pd.NA,
        start_date=pd.Timestamp("2020-01-02"),
        anchor_date=pd.NaT,
        end_date=pd.NaT,
        resolution=pd.NA,
        censored=False,
        depth_pct=np.nan,
        depth_atr=np.nan,
        duration_sessions=pd.NA,
        a0_leg="down",
        a0_anchor=np.nan,
        atr_basis=1.0,
        resolution_known_date=pd.NaT,
        terminated_reason=pd.NA,
        reference_price=100.0,
        anchor_price=np.nan,
    )
    base.update(overrides)
    return base


def _frame(rows):
    return pd.DataFrame(rows, columns=list(pit.EPISODE_COLUMNS))


def test_lookahead_outcome_does_not_leak_when_resolution_known_date_is_after_asof():
    rows = [_row(
        start_date=pd.Timestamp("2020-01-02"),
        end_date=pd.Timestamp("2020-06-01"),
        resolution_known_date=pd.Timestamp("2020-06-01"),
        resolution="durable_low",
        depth_pct=0.4237,
        tier=1,
        anchor_price=61.5,
    )]
    result = pit.pit_universe(_frame(rows), asof="2020-03-01", dedup=False)
    out = result.frame
    assert len(out) == 1
    row = out.iloc[0]
    assert row["resolution"] is pd.NA
    assert np.isnan(row["depth_pct"])
    assert row["tier"] is pd.NA
    assert row["anchor_date"] is pd.NaT
    assert row["censored"] == True  # noqa: E712
    assert row["outcome_state"] == "pending_resolution"
    # LOOKAHEAD LEAK regression (PR #6911 blocker): resolution_known_date is
    # itself outcome-shaped information -- it reveals both THAT a pending
    # episode resolves and WHEN, ahead of the as-of date. It must be masked
    # exactly like every other outcome column.
    assert row["resolution_known_date"] is pd.NaT
    scanned = out.astype(str).to_string()
    assert "0.4237" not in scanned
    assert "61.5" not in scanned
    assert "2020-06-01" not in scanned


def test_every_outcome_column_is_masked_for_every_pending_row():
    rows = [_row(
        start_date=pd.Timestamp("2020-01-02"),
        end_date=pd.Timestamp("2020-06-01"),
        resolution_known_date=pd.Timestamp("2020-06-01"),
        resolution="durable_low", depth_pct=0.1, depth_atr=0.2, tier=1,
        duration_sessions=10, anchor_date=pd.Timestamp("2020-05-01"),
        anchor_price=55.0, terminated_reason="x",
    )]
    out = pit.pit_universe(_frame(rows), asof="2020-03-01", dedup=False).frame
    row = out.iloc[0]
    for col in pit.OUTCOME_COLUMNS:
        if col not in out.columns:
            continue
        val = row[col]
        assert val is pd.NA or val is pd.NaT or (isinstance(val, float) and np.isnan(val))


def test_admit_as_of_has_no_unmasked_public_path():
    """MAJOR regression (PR #6911): admit_as_of used to accept
    mask_outcomes=False while its receipt unconditionally reported
    outcome_masked_rows/masked_columns as if masking had happened -- a
    self-certifying lie. The kwarg must not exist any more: masking is
    unconditional, so the receipt can never claim it happened when it did
    not."""
    import inspect
    sig = inspect.signature(pit.admit_as_of)
    assert "mask_outcomes" not in sig.parameters

    rows = [_row(
        start_date=pd.Timestamp("2020-01-02"),
        resolution_known_date=pd.Timestamp("2020-06-01"),
        resolution="durable_low", depth_pct=0.4237, tier=1, anchor_price=61.5,
    )]
    admitted, info = pit.admit_as_of(_frame(rows), asof="2020-03-01")
    row = admitted.iloc[0]
    assert row["resolution"] is pd.NA
    assert info["outcome_masked_rows"] == 1
    assert "resolution_known_date" in info["masked_columns"]


def test_admission_excludes_episode_starting_after_asof():
    rows = [_row(start_date=pd.Timestamp("2020-05-01"))]
    result = pit.pit_universe(_frame(rows), asof="2020-01-01", dedup=False)
    assert len(result.frame) == 0
    assert result.receipt["rejected_not_started"] == 1


def test_admission_includes_episode_starting_exactly_on_asof():
    rows = [_row(start_date=pd.Timestamp("2020-01-01"))]
    result = pit.pit_universe(_frame(rows), asof="2020-01-01", dedup=False)
    assert len(result.frame) == 1


def test_resolution_known_date_equal_to_asof_is_known_not_pending():
    rows = [_row(
        start_date=pd.Timestamp("2020-01-02"),
        end_date=pd.Timestamp("2020-03-01"),
        resolution_known_date=pd.Timestamp("2020-03-01"),
        resolution="durable_low", depth_pct=0.3, tier=2,
    )]
    out = pit.pit_universe(_frame(rows), asof="2020-03-01", dedup=False).frame
    assert out.iloc[0]["outcome_state"] == "known"
    assert out.iloc[0]["resolution"] == "durable_low"


def test_missing_start_date_is_rejected_and_counted():
    rows = [_row(start_date=pd.NaT)]
    result = pit.pit_universe(_frame(rows), asof="2020-01-01", dedup=False)
    assert len(result.frame) == 0
    assert result.receipt["rejected_missing_start"] == 1


def test_source_censored_episode_is_typed_missing_not_dropped():
    rows = [_row(
        start_date=pd.Timestamp("2020-01-02"), censored=True,
        resolution_known_date=pd.NaT,
    )]
    out = pit.pit_universe(_frame(rows), asof="2020-06-01", dedup=False).frame
    assert len(out) == 1
    assert out.iloc[0]["outcome_state"] == "censored"
    assert out.iloc[0]["censored"] == True  # noqa: E712


def test_masked_integer_columns_are_pandas_NA_not_zero_and_not_float():
    rows = [_row(
        start_date=pd.Timestamp("2020-01-02"),
        resolution_known_date=pd.Timestamp("2020-06-01"),
        tier=1, duration_sessions=5,
    )]
    out = pit.pit_universe(_frame(rows), asof="2020-03-01", dedup=False).frame
    assert str(out["tier"].dtype) == "Int64"
    assert str(out["duration_sessions"].dtype) == "Int64"
    assert out.iloc[0]["tier"] is pd.NA
    assert pd.isna(out.iloc[0]["tier"])


def test_unknowable_row_is_counted_as_contract_violation():
    rows = [_row(
        start_date=pd.Timestamp("2020-01-02"), censored=False,
        resolution_known_date=pd.NaT,
    )]
    result = pit.pit_universe(_frame(rows), asof="2020-06-01", dedup=False)
    assert result.receipt["contract_violations"] == 1
    assert result.frame.iloc[0]["outcome_state"] == "unknowable"


def test_dedup_drops_overlapping_episodes_and_reports_the_count():
    rows = [
        _row(start_date=pd.Timestamp("2020-01-02"),
             resolution_known_date=pd.Timestamp("2020-02-01"),
             end_date=pd.Timestamp("2020-02-01"), resolution="durable_low"),
        _row(start_date=pd.Timestamp("2020-01-10"),
             episode_type="failed_breakdown",
             resolution_known_date=pd.Timestamp("2020-01-20"),
             end_date=pd.Timestamp("2020-01-20"), resolution="recovered"),
    ]
    result = pit.pit_universe(_frame(rows), asof="2020-06-01", dedup=True)
    assert result.receipt["dedup"]["dropped_overlap"] == 1
    assert len(result.frame) == 1


def test_dedup_reports_dropped_rows_rather_than_discarding_silently():
    rows = [
        _row(start_date=pd.Timestamp("2020-01-02"),
             resolution_known_date=pd.Timestamp("2020-02-01"),
             end_date=pd.Timestamp("2020-02-01")),
        _row(start_date=pd.Timestamp("2020-01-02"),
             resolution_known_date=pd.Timestamp("2020-02-01"),
             end_date=pd.Timestamp("2020-02-01")),
    ]
    result = pit.pit_universe(_frame(rows), asof="2020-06-01", dedup=True)
    admitted = result.receipt["admitted"]["total"]
    dropped = result.receipt["dedup"]["dropped_total"]
    assert admitted == len(result.frame) + dropped


def test_dedup_is_invariant_to_input_row_order():
    rows = [
        _row(start_date=pd.Timestamp("2020-01-02"), symbol="AAA",
             resolution_known_date=pd.Timestamp("2020-02-01"), end_date=pd.Timestamp("2020-02-01")),
        _row(start_date=pd.Timestamp("2020-03-02"), symbol="BBB",
             resolution_known_date=pd.Timestamp("2020-04-01"), end_date=pd.Timestamp("2020-04-01")),
        _row(start_date=pd.Timestamp("2020-05-02"), symbol="AAA",
             price_plane_id="other_plane",
             resolution_known_date=pd.Timestamp("2020-06-01"), end_date=pd.Timestamp("2020-06-01")),
    ]
    frame = _frame(rows)
    shuffled = frame.sample(frac=1, random_state=7).reset_index(drop=True)
    r1 = pit.pit_universe(frame, asof="2020-08-01", dedup=True)
    r2 = pit.pit_universe(shuffled, asof="2020-08-01", dedup=True)
    pd.testing.assert_frame_equal(
        r1.frame.sort_values(["symbol", "price_plane_id"]).reset_index(drop=True),
        r2.frame.sort_values(["symbol", "price_plane_id"]).reset_index(drop=True),
    )
    assert r1.receipt["output_hash"] == r2.receipt["output_hash"]


def test_dedup_ignores_outcome_fields():
    base = [
        _row(start_date=pd.Timestamp("2020-01-02"),
             resolution_known_date=pd.Timestamp("2020-02-01"),
             end_date=pd.Timestamp("2020-02-01"), tier=1, depth_pct=0.1, resolution="durable_low"),
        _row(start_date=pd.Timestamp("2020-01-10"), episode_type="failed_breakdown",
             resolution_known_date=pd.Timestamp("2020-01-20"),
             end_date=pd.Timestamp("2020-01-20"), tier=2, depth_pct=0.9, resolution="recovered"),
    ]
    perturbed = [
        _row(start_date=pd.Timestamp("2020-01-02"),
             resolution_known_date=pd.Timestamp("2020-02-01"),
             end_date=pd.Timestamp("2020-02-01"), tier=5, depth_pct=0.55, resolution="failed"),
        _row(start_date=pd.Timestamp("2020-01-10"), episode_type="failed_breakdown",
             resolution_known_date=pd.Timestamp("2020-01-20"),
             end_date=pd.Timestamp("2020-01-20"), tier=9, depth_pct=0.05, resolution="held"),
    ]
    r1 = pit.pit_universe(_frame(base), asof="2020-06-01", dedup=True)
    r2 = pit.pit_universe(_frame(perturbed), asof="2020-06-01", dedup=True)
    keys1 = set(zip(r1.frame["start_date"], r1.frame["episode_type"]))
    keys2 = set(zip(r2.frame["start_date"], r2.frame["episode_type"]))
    assert keys1 == keys2


def test_dedup_uses_the_pit_visible_interval_not_the_future_end_date():
    rows = [
        _row(start_date=pd.Timestamp("2020-01-02"),
             resolution_known_date=pd.Timestamp("2030-01-01"),
             end_date=pd.Timestamp("2030-01-01")),
        _row(start_date=pd.Timestamp("2020-06-01"), episode_type="failed_breakdown",
             resolution_known_date=pd.Timestamp("2020-07-01"),
             end_date=pd.Timestamp("2020-07-01")),
    ]
    result = pit.pit_universe(_frame(rows), asof="2020-06-15", dedup=True)
    assert len(result.frame) == 1
    assert result.receipt["dedup"]["dropped_overlap"] == 1

    rows2 = [
        _row(start_date=pd.Timestamp("2020-01-02"),
             resolution_known_date=pd.Timestamp("2030-01-01"),
             end_date=pd.Timestamp("2030-01-01")),
        _row(start_date=pd.Timestamp("2021-01-01"), episode_type="failed_breakdown",
             resolution_known_date=pd.Timestamp("2021-02-01"),
             end_date=pd.Timestamp("2021-02-01")),
    ]
    result2 = pit.pit_universe(_frame(rows2), asof="2020-06-15", dedup=True)
    assert len(result2.frame) == 1
    assert result2.receipt["dedup"]["dropped_overlap"] == 0


def test_dedup_scope_symbol_plane_keeps_same_start_on_a_different_plane():
    rows = [
        _row(start_date=pd.Timestamp("2020-01-02"), price_plane_id="plane_a",
             resolution_known_date=pd.Timestamp("2020-02-01"), end_date=pd.Timestamp("2020-02-01")),
        _row(start_date=pd.Timestamp("2020-01-02"), price_plane_id="plane_b",
             resolution_known_date=pd.Timestamp("2020-02-01"), end_date=pd.Timestamp("2020-02-01")),
    ]
    result = pit.pit_universe(_frame(rows), asof="2020-06-01", dedup=True, scope="symbol_plane")
    assert len(result.frame) == 2
    assert result.receipt["dedup"]["dropped_total"] == 0


def test_dedup_scope_symbol_plane_type_is_supported_and_deterministic():
    rows = [
        _row(start_date=pd.Timestamp("2020-01-02"), episode_type="reset_decline",
             resolution_known_date=pd.Timestamp("2020-02-01"), end_date=pd.Timestamp("2020-02-01")),
        _row(start_date=pd.Timestamp("2020-01-10"), episode_type="failed_breakdown",
             resolution_known_date=pd.Timestamp("2020-01-20"), end_date=pd.Timestamp("2020-01-20")),
    ]
    r1 = pit.pit_universe(_frame(rows), asof="2020-06-01", dedup=True, scope="symbol_plane_type")
    r2 = pit.pit_universe(_frame(rows), asof="2020-06-01", dedup=True, scope="symbol_plane_type")
    assert r1.receipt["output_hash"] == r2.receipt["output_hash"]
    assert len(r1.frame) == 2


def test_exact_duplicate_is_dropped_and_counted():
    row = _row(start_date=pd.Timestamp("2020-01-02"),
               resolution_known_date=pd.Timestamp("2020-02-01"),
               end_date=pd.Timestamp("2020-02-01"))
    result = pit.pit_universe(_frame([dict(row), dict(row)]), asof="2020-06-01", dedup=True)
    assert result.receipt["dedup"]["dropped_exact_duplicate"] == 1
    assert len(result.frame) == 1


def test_rerun_on_identical_input_is_identical():
    rows = [_row(start_date=pd.Timestamp("2020-01-02"),
                  resolution_known_date=pd.Timestamp("2020-02-01"),
                  end_date=pd.Timestamp("2020-02-01"))]
    frame = _frame(rows)
    r1 = pit.pit_universe(frame, asof="2020-06-01", dedup=True)
    r2 = pit.pit_universe(frame, asof="2020-06-01", dedup=True)
    pd.testing.assert_frame_equal(r1.frame, r2.frame)
    assert r1.receipt == r2.receipt


def test_receipt_carries_no_wallclock_or_absolute_path():
    rows = [_row(start_date=pd.Timestamp("2020-01-02"))]
    receipt = pit.pit_universe(_frame(rows), asof="2020-06-01").receipt

    def scan(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                assert "generated_at" not in str(k)
                assert "timestamp" not in str(k).lower()
                scan(v)
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                scan(v)
        else:
            assert "/Users/" not in str(obj)

    scan(receipt)


def test_receipt_authority_block_is_all_false_and_ceiling_is_research_navigation():
    rows = [_row(start_date=pd.Timestamp("2020-01-02"))]
    receipt = pit.pit_universe(_frame(rows), asof="2020-06-01").receipt
    assert receipt["authority"] == authority_block()
    assert all(v is False for v in receipt["authority"].values())
    assert receipt["authority_ceiling"] == "research_navigation_until_promoted; explicitly not decision-grade"
    assert receipt["llm_involved"] is False


def test_module_is_pure_no_network_no_data_write_no_llm():
    src = Path(pit.__file__).read_text()
    banned = ["requests", "urllib", "httpx", "to_parquet", "to_csv", "open(",
              "openai", "anthropic", "brain"]
    for token in banned:
        assert token not in src, f"forbidden token {token!r} found in analog_pit.py"


def test_empty_result_is_an_explicit_state_with_full_columns():
    rows = [_row(start_date=pd.Timestamp("2025-01-01"))]
    result = pit.pit_universe(_frame(rows), asof="2020-01-01", dedup=True)
    assert len(result.frame) == 0
    assert list(result.frame.columns) == pit._output_columns(result.frame)
    assert result.receipt["empty_reason"] == "no_qualifying_episodes_at_asof"
    state = pit.empty_state("2020-01-01")
    assert state["plain_en"] and state["plain_zh"]


def test_null_lines_are_plain_words_bilingual():
    rows = [
        _row(start_date=pd.Timestamp("2020-01-02"),
             resolution_known_date=pd.Timestamp("2030-01-01"),
             end_date=pd.Timestamp("2030-01-01")),
    ]
    receipt = pit.pit_universe(_frame(rows), asof="2020-06-01", dedup=True).receipt
    lines = pit.plain_null_lines(receipt)
    assert lines
    banned_substrings = ("resolution_known_date", "price_plane_id", "reset_decline", "_")
    for line in lines:
        assert line["plain_en"]
        assert line["plain_zh"]
        for token in banned_substrings:
            assert token not in line["plain_en"]


def test_frozen_episode_columns_match_the_catalog_owner():
    assert tuple(ep.episode_columns()) == pit.EPISODE_COLUMNS


REAL_CATALOG_PATH = Path("data/stock_identity/episodes/pilot_episode_catalog_v0.parquet")


@pytest.mark.skipif(not REAL_CATALOG_PATH.exists(), reason="catalog artifact absent (sparse checkout)")
def test_real_pilot_catalog_passes_the_gate():
    catalog = pd.read_parquet(REAL_CATALOG_PATH)
    for col in pit.EPISODE_COLUMNS:
        assert col in catalog.columns
    result = pit.pit_universe(catalog, asof="2015-01-02", dedup=True)
    assert 0 < len(result.frame) < len(catalog)
    pending = result.frame[result.frame["outcome_state"] == "pending_resolution"]
    for col in pit.OUTCOME_COLUMNS:
        if col not in pending.columns:
            continue
        assert pending[col].isna().all() or (pending[col] is pd.NA).all()
    r = result.receipt
    assert r["admitted"]["total"] == r["dedup"]["kept"] + r["dedup"]["dropped_total"]
    assert r["dedup"]["dropped_overlap"] > 0
