from __future__ import annotations

import csv
from dataclasses import replace
import hashlib
import inspect
import json
from pathlib import Path

import pytest

from scripts.research.temporal_scale.contracts import REQUIRED_EXPORT_COLUMNS, strict_json_dumps
from scripts.research.temporal_scale.chart_export import (
    REQUIRED_PROBE_COLUMNS,
    ExportError,
    LoadedChartExport,
    load_chart_export,
)


CHART_COLUMNS = (
    "TG_chart_is_standard",
    "TG_chart_is_heikinashi",
    "TG_chart_is_renko",
    "TG_chart_is_linebreak",
    "TG_chart_is_kagi",
    "TG_chart_is_pnf",
    "TG_chart_is_range",
)
EXPECTED_COLUMNS = (*REQUIRED_EXPORT_COLUMNS, *CHART_COLUMNS)


def recipe_dict() -> dict:
    return {
        "schema_version": "mastermind.temporal_chart_recipe.v1",
        "recipe_id": "wmt-60-synthetic-fixture",
        "captured_at": "2026-09-03T06:00:00Z",
        "capture_status": "complete",
        "observer": "fixture",
        "instrument": {
            "display_symbol": "WMT", "tickerid": "NYSE:WMT", "main_tickerid": "NYSE:WMT",
            "asset_class": "equity", "exchange": "NYSE", "vendor_feed": "fixture", "currency": "USD",
            "contract_month": None, "continuous_symbol": None, "roll_recipe": None, "settlement_basis": None,
        },
        "chart": {
            "timeframe_period": "60", "named_session": "extended", "exchange_timezone": "America/New_York",
            "chart_timezone": "America/New_York", "extended_hours_enabled": True,
            "price_adjustment": "split_adjusted", "dividend_adjustment": "off",
            "back_adjustment": "not_applicable", "settlement_as_close": "not_applicable",
            "allowed_session_variants": ["extended", "regular"],
            "chart_is_standard": True, "chart_is_heikinashi": False, "chart_is_renko": False,
            "chart_is_linebreak": False, "chart_is_kagi": False, "chart_is_pnf": False, "chart_is_range": False,
        },
        "indicator": {
            "observed_indicator_family": "owner_rsi_macd_stochrsi", "observed_indicator_title": "fixture",
            "observed_indicator_source_kind": "repository_exact", "observed_indicator_source_hash": "1" * 40,
            "observed_indicator_inputs": {"rsi_len": 14, "macd_fast": 14, "macd_slow": 60, "macd_signal": 5, "stoch_len": 14, "smooth_k": 3, "smooth_d": 3},
            "probe_indicator_family": "owner_rsi_macd_stochrsi", "probe_source_git_blob_sha": "1" * 40,
            "probe_inputs": {"rsi_len": 14, "macd_fast": 14, "macd_slow": 60, "macd_signal": 5, "stoch_len": 14, "smooth_k": 3, "smooth_d": 3},
            "probe_ema_adjust": False, "probe_rma_seed": "sma_seeded", "observed_equals_probe": True,
        },
        "export": {"csv_filename": "synthetic.csv", "csv_sha256": "0" * 64, "row_count": 0, "first_bar_open_ms": 0, "last_bar_close_ms": 0, "loaded_history_start_ms": 0},
        "rights": {"use": "local_research_only", "redistribution": "blocked", "source_reference": "synthetic"},
        "missing_fields": [],
    }


def synthetic_rows(count: int = 3) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index in range(count):
        open_ms = 1_700_000_000_000 + index * 3_600_000
        rows.append({
            "TG_time_open_ms": str(open_ms), "TG_time_close_ms": str(open_ms + 3_600_000),
            "TG_time_tradingday_ms": "1699920000000", "TG_duration_ms": "3600000", "TG_bar_index": str(index),
            "TG_is_confirmed": "1", "TG_is_market": "1", "TG_is_premarket": "0", "TG_is_postmarket": "0",
            "TG_is_firstbar": "1" if index == 0 else "0", "TG_is_lastbar": "1" if index == count - 1 else "0",
            "TG_is_firstbar_regular": "1" if index == 0 else "0", "TG_is_lastbar_regular": "1" if index == count - 1 else "0",
            "TG_open": f"{100 + index:.16f}", "TG_high": f"{101 + index:.16f}", "TG_low": f"{99 + index:.16f}",
            "TG_close": f"{100.5 + index:.16f}", "TG_volume": f"{1000 + index:.16f}",
            "TG_rsi": f"{50 + index:.12f}", "TG_rsi_macd": f"{0.1 + index / 100:.12f}",
            "TG_rsi_macd_signal": f"{0.05 + index / 100:.12f}", "TG_rsi_macd_hist": f"{0.05:.12f}",
            "TG_stoch_k": f"{60 + index:.12f}", "TG_stoch_d": f"{59 + index:.12f}",
            "TG_chart_is_standard": "1", "TG_chart_is_heikinashi": "0", "TG_chart_is_renko": "0",
            "TG_chart_is_linebreak": "0", "TG_chart_is_kagi": "0", "TG_chart_is_pnf": "0", "TG_chart_is_range": "0",
        })
    return rows


def write_fixture(
    tmp_path: Path,
    *,
    headers: tuple[str, ...] = EXPECTED_COLUMNS,
    rows: list[dict[str, str]] | None = None,
    quoting: int = csv.QUOTE_MINIMAL,
) -> tuple[Path, Path]:
    rows = synthetic_rows() if rows is None else rows
    csv_path = tmp_path / "synthetic.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, quoting=quoting)
        writer.writerow(headers)
        writer.writerows([[row.get(header, "") for header in headers] for row in rows])
    raw = recipe_dict()
    raw["export"].update(
        csv_sha256=hashlib.sha256(csv_path.read_bytes()).hexdigest(), row_count=len(rows),
        # Keep recipe metadata syntactically valid even when a hostile CSV cell
        # deliberately is not an integer; loader validation must own that error.
        first_bar_open_ms=1_700_000_000_000, last_bar_close_ms=1_700_010_800_000,
        loaded_history_start_ms=1_699_996_400_000,
    )
    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_text(json.dumps(raw), encoding="utf-8")
    return recipe_path, csv_path


def refresh_hash(recipe_path: Path, csv_path: Path) -> dict:
    raw = json.loads(recipe_path.read_text(encoding="utf-8"))
    raw["export"]["csv_sha256"] = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    recipe_path.write_text(json.dumps(raw), encoding="utf-8")
    return raw


def rewrite_csv(csv_path: Path, headers: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows([[row.get(header, "") for header in headers] for row in rows])


def test_exact_happy_path_normalizes_canonical_columns_and_bar_receipts(tmp_path: Path) -> None:
    recipe_path, csv_path = write_fixture(tmp_path)
    loaded = load_chart_export(recipe_path, csv_path)
    assert REQUIRED_PROBE_COLUMNS == EXPECTED_COLUMNS
    assert tuple(loaded.frame.columns) == EXPECTED_COLUMNS
    assert len(loaded.frame) == len(loaded.receipts) == 3
    assert loaded.receipts[0].known_at_ms == loaded.receipts[0].close_ms
    assert loaded.receipts[0].volume == 1000.0
    assert loaded.excluded_provisional_row_sha256 is None
    assert loaded.csv_sha256 == hashlib.sha256(csv_path.read_bytes()).hexdigest()


def test_unique_script_suffix_headers_resolve_to_canonical_probe_titles(tmp_path: Path) -> None:
    headers = tuple(f"Mastermind Temporal Recipe Probe v1: {title}" for title in EXPECTED_COLUMNS)
    rows = [{header: value for header, value in zip(headers, row.values(), strict=True)} for row in synthetic_rows()]
    recipe_path, csv_path = write_fixture(tmp_path, headers=headers, rows=rows)
    loaded = load_chart_export(recipe_path, csv_path)
    assert tuple(loaded.frame.columns) == EXPECTED_COLUMNS


def test_hash_mismatch_fails_before_pandas_parse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    recipe_path, csv_path = write_fixture(tmp_path)
    csv_path.write_bytes(csv_path.read_bytes() + b"\n")
    import scripts.research.temporal_scale.chart_export as chart_export
    monkeypatch.setattr(chart_export.pd, "read_csv", lambda *_args, **_kwargs: pytest.fail("parser invoked"))
    with pytest.raises(ExportError, match="CSV_HASH_MISMATCH"):
        load_chart_export(recipe_path, csv_path)


@pytest.mark.parametrize("mode", ("missing", "ambiguous", "fuzzy", "duplicate"))
def test_headers_fail_closed_for_missing_ambiguous_fuzzy_and_duplicate_titles(tmp_path: Path, mode: str) -> None:
    rows = synthetic_rows()
    headers = list(EXPECTED_COLUMNS)
    if mode == "missing":
        headers.remove("TG_rsi")
        expected = "CSV_COLUMN_MISSING"
    elif mode == "ambiguous":
        headers.append("probe: TG_rsi")
        expected = "CSV_COLUMN_AMBIGUOUS"
    elif mode == "fuzzy":
        headers[headers.index("TG_rsi")] = "TG_rsi_rounded"
        expected = "CSV_COLUMN_MISSING"
    else:
        headers.append("TG_rsi")
        expected = "CSV_HEADER_DUPLICATE"
    recipe_path, csv_path = write_fixture(tmp_path, headers=tuple(headers), rows=rows)
    with pytest.raises(ExportError, match=expected):
        load_chart_export(recipe_path, csv_path)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    (("TG_time_open_ms", "1700000000000.5", "CSV_INTEGER_INVALID"), ("TG_is_market", "2", "CSV_FLAG_INVALID"), ("TG_rsi", "NaN", "CSV_NUMERIC_INVALID")),
)
def test_invalid_integral_flags_and_nonfinite_numerics_fail_closed(tmp_path: Path, field: str, value: str, expected: str) -> None:
    rows = synthetic_rows()
    rows[0][field] = value
    recipe_path, csv_path = write_fixture(tmp_path, rows=rows)
    with pytest.raises(ExportError, match=expected):
        load_chart_export(recipe_path, csv_path)


def test_low_precision_oscillators_fail_before_parity(tmp_path: Path) -> None:
    rows = synthetic_rows()
    rows[0]["TG_rsi"] = "50.0000"
    recipe_path, csv_path = write_fixture(tmp_path, rows=rows)
    with pytest.raises(ExportError, match="^INSUFFICIENT_EXPORT_PRECISION$"):
        load_chart_export(recipe_path, csv_path)


def test_each_oscillator_allows_only_leading_blank_or_null_warmup_cells(tmp_path: Path) -> None:
    rows = synthetic_rows()
    rows[0]["TG_rsi"] = ""
    rows[0]["TG_rsi_macd"] = "null"
    rows[0]["TG_rsi_macd_signal"] = ""
    rows[0]["TG_rsi_macd_hist"] = "null"
    rows[0]["TG_stoch_k"] = ""
    rows[0]["TG_stoch_d"] = "null"
    rows[1]["TG_rsi_macd_signal"] = "null"
    recipe_path, csv_path = write_fixture(tmp_path, rows=rows)
    loaded = load_chart_export(recipe_path, csv_path)
    for column in ("TG_rsi", "TG_rsi_macd", "TG_rsi_macd_signal", "TG_rsi_macd_hist", "TG_stoch_k", "TG_stoch_d"):
        assert loaded.frame.loc[0, column] is None
    assert loaded.frame.loc[1, "TG_rsi_macd_signal"] is None
    assert "null" in strict_json_dumps(loaded.frame.loc[0].to_dict())
    assert loaded.receipts[0].source_row_sha256 == hashlib.sha256(
        strict_json_dumps(loaded.frame.loc[0].to_dict()).encode("utf-8")
    ).hexdigest()


@pytest.mark.parametrize(
    ("column", "values", "expected"),
    (
        ("TG_rsi", ("50.000000000000", "", "52.000000000000"), "CSV_OSCILLATOR_GAP:TG_rsi"),
        ("TG_stoch_k", ("null", "", "null"), "CSV_OSCILLATOR_WARMUP_INVALID:TG_stoch_k"),
        ("TG_stoch_d", ("", "60.0000", "61.000000000000"), "INSUFFICIENT_EXPORT_PRECISION"),
    ),
)
def test_oscillator_warmup_rejects_gaps_all_missing_and_low_precision_after_warmup(
    tmp_path: Path, column: str, values: tuple[str, str, str], expected: str
) -> None:
    rows = synthetic_rows()
    for row, value in zip(rows, values, strict=True):
        row[column] = value
    recipe_path, csv_path = write_fixture(tmp_path, rows=rows)
    with pytest.raises(ExportError, match=expected):
        load_chart_export(recipe_path, csv_path)


def test_row_count_range_order_and_duration_fail_closed(tmp_path: Path) -> None:
    recipe_path, csv_path = write_fixture(tmp_path)
    raw = json.loads(recipe_path.read_text(encoding="utf-8"))
    raw["export"]["row_count"] = 4
    recipe_path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ExportError, match="CSV_ROW_COUNT_MISMATCH"):
        load_chart_export(recipe_path, csv_path)
    recipe_path, csv_path = write_fixture(tmp_path)
    raw = json.loads(recipe_path.read_text(encoding="utf-8"))
    raw["export"]["first_bar_open_ms"] += 1
    recipe_path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ExportError, match="CSV_RANGE_MISMATCH"):
        load_chart_export(recipe_path, csv_path)
    recipe_path, csv_path = write_fixture(tmp_path)
    rows = synthetic_rows()
    rows[1]["TG_time_open_ms"] = rows[0]["TG_time_open_ms"]
    rows[1]["TG_time_close_ms"] = rows[0]["TG_time_close_ms"]
    rewrite_csv(csv_path, EXPECTED_COLUMNS, rows)
    refresh_hash(recipe_path, csv_path)
    with pytest.raises(ExportError, match="CSV_TIME_ORDER_INVALID"):
        load_chart_export(recipe_path, csv_path)
    recipe_path, csv_path = write_fixture(tmp_path)
    rows = synthetic_rows()
    rows[0]["TG_duration_ms"] = "1"
    rewrite_csv(csv_path, EXPECTED_COLUMNS, rows)
    refresh_hash(recipe_path, csv_path)
    with pytest.raises(ExportError, match="CSV_DURATION_MISMATCH"):
        load_chart_export(recipe_path, csv_path)


def test_negative_bar_index_raises_typed_export_error(tmp_path: Path) -> None:
    rows = synthetic_rows()
    rows[0]["TG_bar_index"] = "-1"
    recipe_path, csv_path = write_fixture(tmp_path, rows=rows)
    with pytest.raises(ExportError, match="CSV_INTEGER_INVALID:TG_bar_index"):
        load_chart_export(recipe_path, csv_path)


def test_negative_trading_day_raises_typed_export_error(tmp_path: Path) -> None:
    rows = synthetic_rows()
    rows[0]["TG_time_tradingday_ms"] = "-1"
    recipe_path, csv_path = write_fixture(tmp_path, rows=rows)
    with pytest.raises(ExportError, match="CSV_INTEGER_INVALID:TG_time_tradingday_ms"):
        load_chart_export(recipe_path, csv_path)


def test_chart_flags_must_be_coherent_constant_and_recipe_equal(tmp_path: Path) -> None:
    rows = synthetic_rows()
    rows[0]["TG_chart_is_renko"] = "1"
    recipe_path, csv_path = write_fixture(tmp_path, rows=rows)
    with pytest.raises(ExportError, match="CHART_CONSTRUCTION_IDENTITY_ERROR"):
        load_chart_export(recipe_path, csv_path)
    rows = synthetic_rows()
    rows[1].update(TG_chart_is_standard="0", TG_chart_is_heikinashi="1")
    recipe_path, csv_path = write_fixture(tmp_path, rows=rows)
    with pytest.raises(ExportError, match="CHART_CONSTRUCTION_IDENTITY_ERROR"):
        load_chart_export(recipe_path, csv_path)


def test_blank_volume_stays_null_and_row_hash_is_deterministic(tmp_path: Path) -> None:
    rows = synthetic_rows()
    rows[1]["TG_volume"] = ""
    recipe_path, csv_path = write_fixture(tmp_path, rows=rows)
    first = load_chart_export(recipe_path, csv_path)
    second = load_chart_export(recipe_path, csv_path)
    assert first.receipts[1].volume is None
    assert first.receipts[0].source_row_sha256 == second.receipts[0].source_row_sha256


def test_final_provisional_is_hashed_and_excluded_but_interior_is_rejected(tmp_path: Path) -> None:
    rows = synthetic_rows()
    rows[-1]["TG_is_confirmed"] = "0"
    recipe_path, csv_path = write_fixture(tmp_path, rows=rows)
    loaded = load_chart_export(recipe_path, csv_path)
    assert len(loaded.frame) == len(loaded.receipts) == 2
    assert loaded.excluded_provisional_row_sha256 is not None
    assert len(loaded.excluded_provisional_row_sha256) == 64
    rows = synthetic_rows()
    rows[0]["TG_is_confirmed"] = "0"
    recipe_path, csv_path = write_fixture(tmp_path, rows=rows)
    with pytest.raises(ExportError, match="INTERIOR_UNCONFIRMED_ROW"):
        load_chart_export(recipe_path, csv_path)


def test_loaded_frame_is_defensive_and_constructor_does_not_retain_an_alias(tmp_path: Path) -> None:
    recipe_path, csv_path = write_fixture(tmp_path)
    loaded = load_chart_export(recipe_path, csv_path)
    original_digest = loaded.receipts[0].source_row_sha256
    escaped = loaded.frame
    escaped.loc[0, "TG_rsi"] = 999.0
    assert loaded.frame.loc[0, "TG_rsi"] == 50.0
    assert loaded.receipts[0].source_row_sha256 == original_digest
    constructor_input = loaded.frame
    copied = LoadedChartExport(
        recipe=loaded.recipe,
        frame=constructor_input,
        receipts=loaded.receipts,
        csv_sha256=loaded.csv_sha256,
        excluded_provisional_row_sha256=None,
    )
    constructor_input.loc[0, "TG_rsi"] = 123.0
    assert copied.frame.loc[0, "TG_rsi"] == 50.0


def test_loaded_constructor_rejects_noncanonical_columns_and_illegal_scalar_cells(tmp_path: Path) -> None:
    recipe_path, csv_path = write_fixture(tmp_path)
    loaded = load_chart_export(recipe_path, csv_path)
    reversed_frame = loaded.frame.loc[:, list(reversed(EXPECTED_COLUMNS))]
    with pytest.raises(ExportError, match="NORMALIZED_FRAME_COLUMNS_INVALID"):
        LoadedChartExport(
            recipe=loaded.recipe, frame=reversed_frame, receipts=loaded.receipts,
            csv_sha256=loaded.csv_sha256, excluded_provisional_row_sha256=None,
        )
    illegal_frame = loaded.frame
    illegal_frame.iat[0, EXPECTED_COLUMNS.index("TG_rsi")] = {"nested": "mutable"}
    with pytest.raises(ExportError, match="NORMALIZED_CELL_INVALID:TG_rsi"):
        LoadedChartExport(
            recipe=loaded.recipe, frame=illegal_frame, receipts=loaded.receipts,
            csv_sha256=loaded.csv_sha256, excluded_provisional_row_sha256=None,
        )


@pytest.mark.parametrize(
    ("column", "value"),
    (("TG_open", float("nan")), ("TG_volume", [1]), ("TG_is_market", True), ("TG_time_open_ms", "1700000000000")),
)
def test_loaded_constructor_rejects_nonfinite_or_non_scalar_normalized_cells(
    tmp_path: Path, column: str, value: object
) -> None:
    recipe_path, csv_path = write_fixture(tmp_path)
    loaded = load_chart_export(recipe_path, csv_path)
    malformed = loaded.frame
    malformed.loc[0, column] = value
    with pytest.raises(ExportError, match=f"NORMALIZED_CELL_INVALID:{column}"):
        LoadedChartExport(
            recipe=loaded.recipe, frame=malformed, receipts=loaded.receipts,
            csv_sha256=loaded.csv_sha256, excluded_provisional_row_sha256=None,
        )


def test_loaded_constructor_rejects_receipt_identity_hash_count_and_digest_incoherence(tmp_path: Path) -> None:
    recipe_path, csv_path = write_fixture(tmp_path)
    loaded = load_chart_export(recipe_path, csv_path)
    common = {"recipe": loaded.recipe, "frame": loaded.frame, "csv_sha256": loaded.csv_sha256}
    with pytest.raises(ExportError, match="RECEIPT_COUNT_MISMATCH"):
        LoadedChartExport(receipts=loaded.receipts[:-1], excluded_provisional_row_sha256=None, **common)
    with pytest.raises(ExportError, match="RECEIPT_RECIPE_ID_MISMATCH"):
        LoadedChartExport(
            receipts=(replace(loaded.receipts[0], recipe_id="different"), *loaded.receipts[1:]),
            excluded_provisional_row_sha256=None,
            **common,
        )
    with pytest.raises(ExportError, match="RECEIPT_ROW_HASH_MISMATCH"):
        LoadedChartExport(
            receipts=(replace(loaded.receipts[0], source_row_sha256="0" * 64), *loaded.receipts[1:]),
            excluded_provisional_row_sha256=None,
            **common,
        )
    with pytest.raises(ExportError, match="CSV_SHA256_INVALID"):
        LoadedChartExport(receipts=loaded.receipts, csv_sha256="A" * 64, excluded_provisional_row_sha256=None, recipe=loaded.recipe, frame=loaded.frame)
    with pytest.raises(ExportError, match="PROVISIONAL_DIGEST_INVALID"):
        LoadedChartExport(receipts=loaded.receipts, excluded_provisional_row_sha256="A" * 64, **common)


def test_loaded_constructor_requires_the_recipe_csv_digest_exactly(tmp_path: Path) -> None:
    recipe_path, csv_path = write_fixture(tmp_path)
    loaded = load_chart_export(recipe_path, csv_path)
    with pytest.raises(ExportError, match="CSV_SHA256_MISMATCH"):
        LoadedChartExport(
            recipe=loaded.recipe, frame=loaded.frame, receipts=loaded.receipts,
            csv_sha256="1" * 64, excluded_provisional_row_sha256=None,
        )


@pytest.mark.parametrize(
    "replacement",
    (
        lambda receipt: replace(receipt, bar_index=receipt.bar_index + 7),
        lambda receipt: replace(receipt, nominal_minutes=receipt.nominal_minutes + 1, clipped=True),
        lambda receipt: replace(receipt, volume=None),
        lambda receipt: replace(receipt, session_flags={**receipt.session_flags, "market": False}),
        lambda receipt: replace(receipt, empty_interval=True, volume=None),
        lambda receipt: replace(receipt, known_at_ms=receipt.known_at_ms + 1),
    ),
)
def test_loaded_constructor_requires_exact_receipt_semantics(tmp_path: Path, replacement: object) -> None:
    recipe_path, csv_path = write_fixture(tmp_path)
    loaded = load_chart_export(recipe_path, csv_path)
    altered = replacement(loaded.receipts[0])
    with pytest.raises(ExportError, match="RECEIPT_EXACT_MISMATCH"):
        LoadedChartExport(
            recipe=loaded.recipe, frame=loaded.frame, receipts=(altered, *loaded.receipts[1:]),
            csv_sha256=loaded.csv_sha256, excluded_provisional_row_sha256=None,
        )


def test_loaded_constructor_rejects_tampered_receipt_schema_field(tmp_path: Path) -> None:
    recipe_path, csv_path = write_fixture(tmp_path)
    loaded = load_chart_export(recipe_path, csv_path)
    tampered = loaded.receipts[0]
    object.__setattr__(tampered, "schema_version", "not-a-receipt-schema")
    with pytest.raises(ExportError, match="RECEIPT_EXACT_MISMATCH"):
        LoadedChartExport(
            recipe=loaded.recipe, frame=loaded.frame, receipts=(tampered, *loaded.receipts[1:]),
            csv_sha256=loaded.csv_sha256, excluded_provisional_row_sha256=None,
        )


@pytest.mark.parametrize(
    ("mutate", "expected"),
    (
        (lambda frame: frame.__setitem__("TG_time_open_ms", [1, *frame["TG_time_open_ms"].tolist()[1:]]), "CSV_RANGE_MISMATCH"),
        (lambda frame: (frame.__setitem__("TG_time_open_ms", [frame["TG_time_open_ms"].iloc[0], frame["TG_time_open_ms"].iloc[0], frame["TG_time_open_ms"].iloc[2]]), frame.__setitem__("TG_time_close_ms", [frame["TG_time_close_ms"].iloc[0], frame["TG_time_close_ms"].iloc[0], frame["TG_time_close_ms"].iloc[2]])), "CSV_TIME_ORDER_INVALID"),
        (lambda frame: frame.__setitem__("TG_duration_ms", [1, *frame["TG_duration_ms"].tolist()[1:]]), "CSV_DURATION_MISMATCH"),
        (lambda frame: frame.__setitem__("TG_chart_is_renko", [1, 1, 1]), "CHART_CONSTRUCTION_IDENTITY_ERROR"),
        (lambda frame: frame.__setitem__("TG_is_confirmed", [0, 1, 1]), "INCLUDED_UNCONFIRMED_ROW"),
    ),
)
def test_loaded_constructor_applies_retained_row_semantics(tmp_path: Path, mutate: object, expected: str) -> None:
    recipe_path, csv_path = write_fixture(tmp_path)
    loaded = load_chart_export(recipe_path, csv_path)
    malformed = loaded.frame
    mutate(malformed)
    with pytest.raises(ExportError, match=expected):
        LoadedChartExport(
            recipe=loaded.recipe, frame=malformed, receipts=loaded.receipts,
            csv_sha256=loaded.csv_sha256, excluded_provisional_row_sha256=None,
        )


@pytest.mark.parametrize(
    "column",
    ("TG_rsi", "TG_rsi_macd", "TG_rsi_macd_signal", "TG_rsi_macd_hist", "TG_stoch_k", "TG_stoch_d"),
)
def test_final_provisional_cannot_supply_the_only_finite_oscillator_value(tmp_path: Path, column: str) -> None:
    rows = synthetic_rows()
    rows[0][column] = ""
    rows[1][column] = "null"
    rows[-1]["TG_is_confirmed"] = "0"
    recipe_path, csv_path = write_fixture(tmp_path, rows=rows)
    with pytest.raises(ExportError, match=f"CSV_OSCILLATOR_WARMUP_INVALID:{column}"):
        load_chart_export(recipe_path, csv_path)


@pytest.mark.parametrize("mutation", ("missing", "extra"))
def test_raw_csv_record_arity_is_rejected_before_pandas(tmp_path: Path, mutation: str) -> None:
    recipe_path, csv_path = write_fixture(tmp_path)
    lines = csv_path.read_text(encoding="utf-8").splitlines()
    if mutation == "missing":
        lines[1] = lines[1].rsplit(",", 1)[0]
    else:
        lines[1] = f"{lines[1]},extra"
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    refresh_hash(recipe_path, csv_path)
    with pytest.raises(ExportError, match="CSV_ROW_ARITY_INVALID"):
        load_chart_export(recipe_path, csv_path)


def test_quoted_csv_records_remain_legal_when_arity_matches(tmp_path: Path) -> None:
    headers = (*EXPECTED_COLUMNS, "operator_note")
    rows = [dict(row, operator_note="quoted, note\ncontinued") for row in synthetic_rows()]
    recipe_path, csv_path = write_fixture(tmp_path, headers=headers, rows=rows, quoting=csv.QUOTE_ALL)
    assert len(load_chart_export(recipe_path, csv_path).frame) == 3


def test_incomplete_recipe_and_unsupported_timeframe_are_typed_export_errors(tmp_path: Path) -> None:
    recipe_path, csv_path = write_fixture(tmp_path)
    raw = json.loads(recipe_path.read_text(encoding="utf-8"))
    raw["capture_status"] = "incomplete"
    raw["instrument"]["tickerid"] = None
    raw["missing_fields"] = ["instrument.tickerid"]
    recipe_path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ExportError, match="UNRESOLVED_DATA"):
        load_chart_export(recipe_path, csv_path)
    recipe_path, csv_path = write_fixture(tmp_path)
    raw = json.loads(recipe_path.read_text(encoding="utf-8"))
    raw["chart"]["timeframe_period"] = "1D"
    recipe_path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ExportError, match="UNSUPPORTED_TIMEFRAME"):
        load_chart_export(recipe_path, csv_path)


def test_chart_export_source_has_no_network_or_write_side_effects() -> None:
    import scripts.research.temporal_scale.chart_export as chart_export
    source = inspect.getsource(chart_export)
    for forbidden in ("requests", "urllib", "http://", "https://", "write_text", "write_bytes", "to_csv"):
        assert forbidden not in source
