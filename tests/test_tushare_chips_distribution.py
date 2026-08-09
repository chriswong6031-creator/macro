"""cyq_chips 筹码分布 plane — schema, keep-first store, percent semantics, aggregation math.

Fully synthetic and offline: every vendor response is a hand-built frame and no test touches
the network. Hermetic in DATA, not in TIME — the fixed ``2026-08-07`` below is payload that
flows through the collector, never compared against a clock, so these assertions do not rot
into a scheduled red. The one clock the collector reads (the receipt's observed-at stamp) is
injected explicitly.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from collectors import tushare_chips_distribution as chips
from collectors import tushare_history as hist

TRADE_DATE = "2026-08-07"
COMPACT = "20260807"
TICKER = "600519.SS"
VENDOR_CODE = "600519.SH"
FIXED_NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def gate_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """Open the token gate with a synthetic value and neutralize the rate governor."""
    monkeypatch.setenv("TUSHARE_TOKEN", "synthetic-test-token")
    monkeypatch.setattr(chips, "_govern", lambda: None)


def vendor_frame(
    percents=(25.0, 25.0, 25.0, 25.0),
    prices=("10", "11", "12", "13"),
    trade_date: str = COMPACT,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ts_code": VENDOR_CODE,
                "trade_date": trade_date,
                "price": float(p),
                "percent": pct,
            }
            for p, pct in zip(prices, percents)
        ]
    )


def query_returning(frame: pd.DataFrame):
    def _query(api_name: str, **kwargs):
        assert api_name == "cyq_chips"
        assert kwargs["ts_code"] == VENDOR_CODE
        return frame

    return _query


# ---------------------------------------------------------------------------------------
# store: schema round-trip, receipt, keep-first immutability
# ---------------------------------------------------------------------------------------


def test_partition_round_trips_with_exact_decimal_prices(tmp_path):
    result = chips.collect(
        TICKER,
        TRADE_DATE,
        output_root=tmp_path,
        query_fn=query_returning(vendor_frame()),
        now=FIXED_NOW,
    )
    assert result.status == "written"
    assert result.row_count == 4
    expected = tmp_path / f"by_trade_date={TRADE_DATE}" / f"by_ticker={TICKER}"
    assert Path(result.partition_path) == expected
    assert (expected / "part.parquet").is_file()
    assert (expected / "receipt.json").is_file()

    table = pq.ParquetFile(expected / "part.parquet").read()
    assert table.schema == chips.arrow_schema()
    rows = table.to_pylist()
    # price survives as an EXACT decimal on the vendor's grid, not a float approximation
    assert [r["price"] for r in rows] == [
        Decimal("10.0000"),
        Decimal("11.0000"),
        Decimal("12.0000"),
        Decimal("13.0000"),
    ]
    assert [r["ticker"] for r in rows] == [TICKER] * 4
    assert [r["trade_date"] for r in rows] == [TRADE_DATE] * 4
    assert all(r["authority"] == chips.AUTHORITY for r in rows)

    # the raw rows read back out through the module's own reader
    assert len(chips.read_partition(tmp_path, TICKER, TRADE_DATE)) == 4


def test_receipt_pins_contract_authority_and_recomputes(tmp_path):
    chips.collect(
        TICKER,
        TRADE_DATE,
        output_root=tmp_path,
        query_fn=query_returning(vendor_frame()),
        now=FIXED_NOW,
    )
    path = (
        tmp_path
        / f"by_trade_date={TRADE_DATE}"
        / f"by_ticker={TICKER}"
        / "receipt.json"
    )
    receipt = json.loads(path.read_text(encoding="utf-8"))

    declared = receipt.pop("receipt_sha256")
    assert chips.canonical_hash(receipt) == declared  # the hash actually recomputes

    contract = receipt["endpoint_contract"]
    assert contract["api_name"] == "cyq_chips"
    assert contract["doc_id"] == 294
    assert contract["contract_source"] == "official_doc_page"
    assert contract["percent_unit"] == "percentage_points_0_100"
    assert contract["required_params"] == ["ts_code"]
    assert contract["max_rows_per_call"] == 6000

    provenance = receipt["collection_provenance"]
    assert provenance == {
        "mode": "operator_ordered_wiring",
        "authority_document": "research/TUSHARE_WIRING_TAKEOVER_2026-08-09.md",
        "authority_document_sha256": (
            "18bd19ea22a0bcb47a5ce8b983ba64ecacc8d706ae329578d1e6d2d6e7e7594d"
        ),
        "scope": "private_collection_and_in_repo_research",
        "legal_conclusion": "none_embedded_in_collection_receipt",
    }
    assert receipt["nonclaims"] == [
        "context_only_not_signal_rank_size_or_gate_authority",
        "access_attested_only_for_this_exact_request",
        "no_completeness_claim_across_tickers_or_dates",
        "distribution_semantics_pinned_from_official_doc_page",
    ]
    flattened = json.dumps(receipt, ensure_ascii=False)
    for retired in (
        "not_proof_of_purchase",
        "not_proof_of_payment",
        "not_proof_of_license",
        "no_team_sharing",
        "operator_attestation_verified",
        "TUSHARE_ADDONS_COLLECTOR_FOUNDATION_2026-08-09.md",
    ):
        assert retired not in flattened
    assert receipt["access_observation_receipt"]["observation"] == (
        "access_observed_at_request_time"
    )

    data = receipt["data_receipt"]
    assert data["row_count"] == 4
    assert data["percent_mass_total"] == pytest.approx(100.0)
    assert (
        data["percent_mass_observation"]
        == "consistent_with_documented_percentage_points"
    )
    # the credential never reaches the receipt (the sanitized request key names it only to
    # say it is absent, so assert on the VALUE, not the substring)
    assert "synthetic-test-token" not in json.dumps(receipt, ensure_ascii=False)
    assert set(receipt["request"]["vendor_request_without_token"]["params"]) == {
        "ts_code",
        "trade_date",
    }


def test_recollecting_identical_rows_is_a_no_op(tmp_path):
    first = chips.collect(
        TICKER,
        TRADE_DATE,
        output_root=tmp_path,
        query_fn=query_returning(vendor_frame()),
        now=FIXED_NOW,
    )
    second = chips.collect(
        TICKER,
        TRADE_DATE,
        output_root=tmp_path,
        query_fn=query_returning(vendor_frame()),
        now=FIXED_NOW,
    )
    assert first.status == "written"
    assert second.status == "unchanged"
    assert second.data_hash == first.data_hash
    assert second.receipt_hash == first.receipt_hash


def test_keep_first_refuses_a_revised_response(tmp_path):
    chips.collect(
        TICKER,
        TRADE_DATE,
        output_root=tmp_path,
        query_fn=query_returning(vendor_frame()),
        now=FIXED_NOW,
    )
    revised = vendor_frame(percents=(40.0, 20.0, 25.0, 15.0))
    with pytest.raises(chips.CollectorIntegrityError, match="keep-first"):
        chips.collect(
            TICKER,
            TRADE_DATE,
            output_root=tmp_path,
            query_fn=query_returning(revised),
            now=FIXED_NOW,
        )


def test_gate_closed_without_a_token(tmp_path, monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    with pytest.raises(chips.CollectionHeld) as excinfo:
        chips.collect(
            TICKER,
            TRADE_DATE,
            output_root=tmp_path,
            query_fn=query_returning(vendor_frame()),
        )
    assert excinfo.value.reason_code == "tushare_token_absent"
    assert not list(tmp_path.iterdir())


# ---------------------------------------------------------------------------------------
# percent semantics — the documented 价格占比（%） unit
# ---------------------------------------------------------------------------------------


def test_percent_is_stored_in_documented_percentage_points(tmp_path):
    chips.collect(
        TICKER,
        TRADE_DATE,
        output_root=tmp_path,
        query_fn=query_returning(vendor_frame()),
        now=FIXED_NOW,
    )
    rows = chips.read_partition(tmp_path, TICKER, TRADE_DATE)
    # unconverted: the vendor's own units survive into the store
    assert [r["percent"] for r in rows] == [25.0, 25.0, 25.0, 25.0]
    # the 0-1 fractions consumers want are produced in ONE audited place
    assert [share for _, share in chips.levels_from_rows(rows)] == [0.25] * 4


def test_fraction_like_percent_mass_is_a_loud_stop(tmp_path):
    """A 100x unit flip must never be silently renormalized into the store."""
    fraction_like = vendor_frame(percents=(0.25, 0.25, 0.25, 0.25))
    with pytest.raises(chips.CollectorIntegrityError, match="fraction-like"):
        chips.collect(
            TICKER,
            TRADE_DATE,
            output_root=tmp_path,
            query_fn=query_returning(fraction_like),
            now=FIXED_NOW,
        )
    assert not list(tmp_path.iterdir())  # nothing partial left behind


def test_percent_mass_observation_classifies_the_three_cases():
    assert chips.percent_mass_observation(100.0) == (
        "consistent_with_documented_percentage_points"
    )
    assert chips.percent_mass_observation(99.4) == (
        "consistent_with_documented_percentage_points"
    )
    assert chips.percent_mass_observation(1.0) == (
        "contradicts_documented_percentage_points_fraction_like"
    )
    assert chips.percent_mass_observation(42.0) == "indeterminate_percent_mass"


def test_indeterminate_mass_is_recorded_not_rejected(tmp_path):
    partial = vendor_frame(percents=(20.0, 10.0, 10.0, 10.0))  # sums to 50
    result = chips.collect(
        TICKER,
        TRADE_DATE,
        output_root=tmp_path,
        query_fn=query_returning(partial),
        now=FIXED_NOW,
    )
    assert result.status == "written"
    assert result.percent_mass_observation == "indeterminate_percent_mass"


# ---------------------------------------------------------------------------------------
# response validation
# ---------------------------------------------------------------------------------------


def test_price_beyond_the_pinned_decimal_scale_raises(tmp_path):
    frame = vendor_frame()
    frame.loc[0, "price"] = 10.123456  # 6 dp against a scale-4 pin
    with pytest.raises(chips.CollectorIntegrityError, match="decimal scale"):
        chips.collect(
            TICKER,
            TRADE_DATE,
            output_root=tmp_path,
            query_fn=query_returning(frame),
            now=FIXED_NOW,
        )


def test_unexpected_columns_raise(tmp_path):
    frame = vendor_frame()
    frame["surprise"] = 1
    with pytest.raises(chips.CollectorIntegrityError, match="schema differs"):
        chips.collect(
            TICKER,
            TRADE_DATE,
            output_root=tmp_path,
            query_fn=query_returning(frame),
            now=FIXED_NOW,
        )


def test_row_escaping_the_requested_session_raises(tmp_path):
    frame = vendor_frame()
    frame.loc[2, "trade_date"] = "20260806"
    with pytest.raises(
        chips.CollectorIntegrityError, match="escaped the requested session"
    ):
        chips.collect(
            TICKER,
            TRADE_DATE,
            output_root=tmp_path,
            query_fn=query_returning(frame),
            now=FIXED_NOW,
        )


def test_repeated_price_level_raises(tmp_path):
    frame = vendor_frame(prices=("10", "10", "12", "13"))
    with pytest.raises(chips.CollectorIntegrityError, match="repeats a price level"):
        chips.collect(
            TICKER,
            TRADE_DATE,
            output_root=tmp_path,
            query_fn=query_returning(frame),
            now=FIXED_NOW,
        )


def test_empty_response_is_held_not_written(tmp_path):
    empty = pd.DataFrame(columns=["ts_code", "trade_date", "price", "percent"])
    with pytest.raises(chips.CollectionHeld) as excinfo:
        chips.collect(
            TICKER,
            TRADE_DATE,
            output_root=tmp_path,
            query_fn=query_returning(empty),
            now=FIXED_NOW,
        )
    assert excinfo.value.reason_code == "cyq_chips_unavailable_empty_or_unentitled"


def test_governor_stays_under_the_shared_premium_budget():
    assert chips.MAX_CALLS_PER_MINUTE <= 240  # 300/min pool, margined for other lanes
    assert chips._MIN_CALL_INTERVAL_S == pytest.approx(
        60.0 / chips.MAX_CALLS_PER_MINUTE
    )


# ---------------------------------------------------------------------------------------
# aggregation contract — hand-computed expectations
# ---------------------------------------------------------------------------------------


def rows_for(percents, prices=("10", "11", "12", "13")):
    return [
        {"ticker": TICKER, "trade_date": TRADE_DATE, "price": float(p), "percent": pct}
        for p, pct in zip(prices, percents)
    ]


def test_entropy_of_a_uniform_grid_is_maximal():
    levels = chips.levels_from_rows(rows_for((25.0, 25.0, 25.0, 25.0)))
    out = chips.distribution_entropy(levels)
    assert out["entropy_nats"] == pytest.approx(1.3862943611198906)  # ln 4
    assert out["entropy_normalized"] == pytest.approx(1.0)
    assert out["level_count"] == 4
    assert out["support_level_count"] == 4


def test_entropy_normalizes_against_the_whole_price_grid():
    """Two of four levels at 50/50 is HALF as dispersed as a uniform sheet: ln2 / ln4."""
    levels = chips.levels_from_rows(rows_for((50.0, 50.0, 0.0, 0.0)))
    out = chips.distribution_entropy(levels)
    assert out["entropy_nats"] == pytest.approx(0.6931471805599453)  # ln 2
    assert out["entropy_normalized"] == pytest.approx(0.5)
    assert out["level_count"] == 4
    assert out["support_level_count"] == 2


def test_entropy_of_a_single_occupied_level_is_zero():
    levels = chips.levels_from_rows(rows_for((100.0, 0.0, 0.0, 0.0)))
    out = chips.distribution_entropy(levels)
    assert out["entropy_nats"] == pytest.approx(0.0)
    assert out["entropy_normalized"] == pytest.approx(0.0)
    assert out["support_level_count"] == 1


def test_concentration_band_is_inclusive_and_relative_to_the_reference():
    levels = chips.levels_from_rows(rows_for((25.0, 25.0, 25.0, 25.0)))
    # +/-10% of 11.0 => [9.9, 12.1] => levels 10, 11, 12 => 3 of 4
    assert chips.concentration_share(levels, 11.0, 10.0) == pytest.approx(0.75)
    # +/-5% of 11.0 => [10.45, 11.55] => level 11 only
    assert chips.concentration_share(levels, 11.0, 5.0) == pytest.approx(0.25)
    # the band edge is INSIDE: +/-10% of 10.0 => [9.0, 11.0] => levels 10 and 11
    assert chips.concentration_share(levels, 10.0, 10.0) == pytest.approx(0.5)


def test_winner_shares_split_below_at_and_above_exhaustively():
    levels = chips.levels_from_rows(rows_for((25.0, 25.0, 25.0, 25.0)))
    out = chips.winner_shares(levels, 11.0)
    assert out["winner_share"] == pytest.approx(0.25)  # priced below the reference
    assert out["at_cost_share"] == pytest.approx(0.25)  # exactly at it — neither side
    assert out["loser_share"] == pytest.approx(0.50)
    assert sum(out.values()) == pytest.approx(1.0)


def test_winner_share_of_a_fully_profitable_book_is_one():
    levels = chips.levels_from_rows(rows_for((100.0, 0.0, 0.0, 0.0)))
    out = chips.winner_shares(levels, 12.0)
    assert out["winner_share"] == pytest.approx(1.0)
    assert out["loser_share"] == pytest.approx(0.0)


def test_reference_dependent_features_are_null_without_a_reference():
    """A missing close must read as "unknown", never as "no chips near the close"."""
    levels = chips.levels_from_rows(rows_for((25.0, 25.0, 25.0, 25.0)))
    assert chips.concentration_share(levels, None, 10.0) is None
    assert chips.concentration_share(levels, 0.0, 10.0) is None
    assert chips.winner_shares(levels, None) == {
        "winner_share": None,
        "loser_share": None,
        "at_cost_share": None,
    }


def test_empty_distribution_yields_nulls_not_zeros():
    out = chips.distribution_entropy([])
    assert out["entropy_nats"] is None
    assert out["entropy_normalized"] is None
    assert out["level_count"] == 0
    assert chips.concentration_share([], 11.0, 10.0) is None


def test_summarize_distribution_is_the_full_feature_row():
    features = chips.summarize_distribution(
        rows_for((10.0, 60.0, 20.0, 10.0)), ref_price=11.0, bands=(5.0, 10.0)
    )
    assert features["ticker"] == TICKER
    assert features["trade_date"] == TRADE_DATE
    assert features["percent_mass_total"] == pytest.approx(100.0)
    assert features["price_min"] == pytest.approx(10.0)
    assert features["price_max"] == pytest.approx(13.0)
    assert features["peak_price"] == pytest.approx(11.0)  # heaviest level
    # 10*0.10 + 11*0.60 + 12*0.20 + 13*0.10 = 1 + 6.6 + 2.4 + 1.3 = 11.3
    assert features["mass_weighted_avg_price"] == pytest.approx(11.3)
    assert features["winner_share"] == pytest.approx(0.10)
    assert features["at_cost_share"] == pytest.approx(0.60)
    assert features["loser_share"] == pytest.approx(0.30)
    assert features["concentration_share_5pct"] == pytest.approx(0.60)
    assert features["concentration_share_10pct"] == pytest.approx(0.90)
    assert features["ref_price"] == pytest.approx(11.0)
    assert set(chips.DEFAULT_BANDS) == {5.0, 10.0}


def test_summary_features_are_computable_straight_off_a_stored_partition(tmp_path):
    chips.collect(
        TICKER,
        TRADE_DATE,
        output_root=tmp_path,
        query_fn=query_returning(vendor_frame()),
        now=FIXED_NOW,
    )
    features = chips.summarize_distribution(
        chips.read_partition(tmp_path, TICKER, TRADE_DATE), ref_price=11.0
    )
    assert features["percent_mass_total"] == pytest.approx(100.0)
    assert features["entropy_normalized"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------------------
# history accrual leg
# ---------------------------------------------------------------------------------------

RANGE_DATES = ["20260805", "20260806", COMPACT]


def ranged_frame(dates=RANGE_DATES) -> pd.DataFrame:
    rows = []
    for d in dates:
        for price, pct in zip((10.0, 11.0, 12.0, 13.0), (10.0, 60.0, 20.0, 10.0)):
            rows.append(
                {
                    "ts_code": VENDOR_CODE,
                    "trade_date": d,
                    "price": price,
                    "percent": pct,
                }
            )
    return pd.DataFrame(rows)


def test_history_accrual_writes_derived_features_not_raw_levels(tmp_path, monkeypatch):
    monkeypatch.setattr(hist.tc, "query", lambda api, **kw: ranged_frame())
    monkeypatch.setattr(hist, "_close_panel", lambda: None)
    path = tmp_path / "chips_dist_hist.parquet"

    written = hist._accrue_chips_distribution(path, {TICKER}, RANGE_DATES)
    assert written == 3
    stored = pd.read_parquet(path)
    assert set(stored["date"]) == set(RANGE_DATES)
    assert set(stored["ticker"]) == {TICKER}
    # DERIVED aggregates only — no price/percent histogram rows leak into this grid
    assert "price" not in stored.columns and "percent" not in stored.columns
    assert {
        "chip_entropy_norm",
        "chip_peak_price",
        "chip_avg_cost",
        "chip_level_count",
        "chip_winner_share",
        "chip_conc_5pct",
        "chip_conc_10pct",
    } <= set(stored.columns)
    row = stored.iloc[0]
    assert row["chip_level_count"] == 4
    assert row["chip_peak_price"] == pytest.approx(11.0)
    assert row["chip_avg_cost"] == pytest.approx(11.3)
    # no close panel => reference-dependent features are NULL, not zero
    assert pd.isna(row["chip_winner_share"])
    assert pd.isna(row["chip_conc_10pct"])


def test_history_accrual_uses_the_close_as_the_reference_price(tmp_path, monkeypatch):
    closes = pd.DataFrame({TICKER: [11.0, 11.0, 11.0]}, index=RANGE_DATES)
    monkeypatch.setattr(hist.tc, "query", lambda api, **kw: ranged_frame())
    monkeypatch.setattr(hist, "_close_panel", lambda: closes)
    path = tmp_path / "chips_dist_hist.parquet"

    hist._accrue_chips_distribution(path, {TICKER}, RANGE_DATES)
    row = pd.read_parquet(path).iloc[0]
    assert row["chip_winner_share"] == pytest.approx(0.10)
    assert row["chip_conc_5pct"] == pytest.approx(0.60)
    assert row["chip_conc_10pct"] == pytest.approx(0.90)


def test_history_accrual_skips_pairs_it_already_has(tmp_path, monkeypatch):
    calls: list[dict] = []

    def _query(api, **kw):
        calls.append(kw)
        return ranged_frame()

    monkeypatch.setattr(hist.tc, "query", _query)
    monkeypatch.setattr(hist, "_close_panel", lambda: None)
    path = tmp_path / "chips_dist_hist.parquet"

    assert hist._accrue_chips_distribution(path, {TICKER}, RANGE_DATES) == 3
    assert hist._accrue_chips_distribution(path, {TICKER}, RANGE_DATES) == 0
    assert len(calls) == 1  # nothing missing => no second vendor call
    assert len(pd.read_parquet(path)) == 3


def test_history_accrual_drops_a_truncated_window(tmp_path, monkeypatch):
    """At the vendor row cap the response is partial and its mass features would be wrong."""
    monkeypatch.setattr(chips, "VENDOR_MAX_ROWS", 4)
    monkeypatch.setattr(hist.tc, "query", lambda api, **kw: ranged_frame())
    monkeypatch.setattr(hist, "_close_panel", lambda: None)
    path = tmp_path / "chips_dist_hist.parquet"

    assert hist._accrue_chips_distribution(path, {TICKER}, RANGE_DATES) == 0
    assert not path.exists()


def test_history_accrual_refuses_a_fraction_like_window(tmp_path, monkeypatch):
    frame = ranged_frame()
    frame["percent"] = frame["percent"] / 100.0  # the 100x unit flip
    monkeypatch.setattr(hist.tc, "query", lambda api, **kw: frame)
    monkeypatch.setattr(hist, "_close_panel", lambda: None)
    path = tmp_path / "chips_dist_hist.parquet"

    assert hist._accrue_chips_distribution(path, {TICKER}, RANGE_DATES) == 0
    assert not path.exists()


def test_history_accrual_is_bounded_by_the_call_cap(tmp_path, monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(
        hist.tc, "query", lambda api, **kw: (calls.append(kw), ranged_frame())[1]
    )
    monkeypatch.setattr(hist, "_close_panel", lambda: None)
    panel = {TICKER, "000001.SZ", "600000.SS"}

    hist._accrue_chips_distribution(
        tmp_path / "h.parquet", panel, RANGE_DATES, max_calls=2
    )
    assert len(calls) == 2
    assert all(kw["start_date"] == RANGE_DATES[0] for kw in calls)
    assert all(kw["end_date"] == RANGE_DATES[-1] for kw in calls)


def test_refresh_actually_wires_the_chip_distribution_leg(monkeypatch):
    """Pins the WIRING, not just the function: an unregistered leg fails this test."""
    seen: list[object] = []
    monkeypatch.setattr(hist.tc, "enabled", lambda: True)
    monkeypatch.setattr(hist, "_panel_tickers", lambda: {TICKER})
    monkeypatch.setattr(hist, "_grid_dates", lambda *a, **k: list(RANGE_DATES))
    monkeypatch.setattr(hist, "_accrue", lambda *a, **k: 0)
    monkeypatch.setattr(
        hist,
        "_accrue_chips_distribution",
        lambda path, panel, dates, **kw: seen.append((path, panel, dates)) or 3,
    )
    assert hist.refresh() == 3
    assert len(seen) == 1
    path, panel, dates = seen[0]
    assert path == hist.CHIPS_DIST_HIST
    assert path.name == "chips_dist_hist.parquet"
    assert panel == {TICKER}
    assert dates == RANGE_DATES


def test_vendor_ticker_maps_back_to_the_vendor_suffix():
    assert chips.vendor_ticker("600519.SS") == "600519.SH"
    assert chips.vendor_ticker("000001.SZ") == "000001.SZ"
    assert chips.canonical_ticker("600519.SH") == "600519.SS"
    with pytest.raises(chips.CollectorIntegrityError):
        chips.canonical_ticker("AAPL")
