"""Strict local TradingView probe CSV loading for the temporal-scale study."""
from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
from io import StringIO
import math
from numbers import Integral, Real
from pathlib import Path
import re
from typing import Any

import pandas as pd

from scripts.research.temporal_scale.contracts import (
    BarReceipt,
    ChartRecipe,
    ContractError,
    REQUIRED_EXPORT_COLUMNS,
    strict_json_dumps,
)


class ExportError(ValueError):
    """Raised when a local chart export cannot be proven recipe-compatible."""


_CHART_COLUMNS = (
    "TG_chart_is_standard", "TG_chart_is_heikinashi", "TG_chart_is_renko",
    "TG_chart_is_linebreak", "TG_chart_is_kagi", "TG_chart_is_pnf", "TG_chart_is_range",
)
REQUIRED_PROBE_COLUMNS = (*REQUIRED_EXPORT_COLUMNS, *_CHART_COLUMNS)
_INTEGER_COLUMNS = frozenset({
    "TG_time_open_ms", "TG_time_close_ms", "TG_time_tradingday_ms", "TG_duration_ms", "TG_bar_index",
})
_FLAG_COLUMNS = frozenset({
    "TG_is_confirmed", "TG_is_market", "TG_is_premarket", "TG_is_postmarket", "TG_is_firstbar",
    "TG_is_lastbar", "TG_is_firstbar_regular", "TG_is_lastbar_regular", *_CHART_COLUMNS,
})
_OSCILLATOR_COLUMNS = frozenset({
    "TG_rsi", "TG_rsi_macd", "TG_rsi_macd_signal", "TG_rsi_macd_hist", "TG_stoch_k", "TG_stoch_d",
})
_FLOAT_COLUMNS = frozenset({"TG_open", "TG_high", "TG_low", "TG_close", "TG_volume", *_OSCILLATOR_COLUMNS})
_INTEGER_LEXEME = re.compile(r"^-?[0-9]+$")
_PRECISE_OSCILLATOR_LEXEME = re.compile(r"^-?[0-9]+\.[0-9]{12,}$")
_MISSING_VOLUME = frozenset({"", "na", "nan", "null"})
_MISSING_OSCILLATOR = frozenset({"", "null"})
_CHART_TO_RECIPE = dict(zip(_CHART_COLUMNS, (
    "chart_is_standard", "chart_is_heikinashi", "chart_is_renko", "chart_is_linebreak",
    "chart_is_kagi", "chart_is_pnf", "chart_is_range",
), strict=True))


@dataclass(frozen=True, slots=True, init=False, eq=False)
class LoadedChartExport:
    recipe: ChartRecipe
    _frame: pd.DataFrame
    receipts: tuple[BarReceipt, ...]
    csv_sha256: str
    excluded_provisional_row_sha256: str | None
    _evidence_key: tuple[str, str, tuple[str, ...], str | None]

    def __init__(
        self,
        *,
        recipe: ChartRecipe,
        frame: pd.DataFrame,
        receipts: tuple[BarReceipt, ...],
        csv_sha256: str,
        excluded_provisional_row_sha256: str | None,
    ) -> None:
        try:
            detached_frame, normalized_rows = _detach_normalized_frame(frame)
            _validate_loaded_evidence(
                recipe=recipe,
                rows=normalized_rows,
                receipts=receipts,
                csv_sha256=csv_sha256,
                excluded_provisional_row_sha256=excluded_provisional_row_sha256,
            )
        except ExportError:
            raise
        except Exception as exc:
            raise ExportError("LOADED_EXPORT_INVALID") from exc
        object.__setattr__(self, "recipe", recipe)
        object.__setattr__(self, "_frame", detached_frame)
        object.__setattr__(self, "receipts", receipts)
        object.__setattr__(self, "csv_sha256", csv_sha256)
        object.__setattr__(self, "excluded_provisional_row_sha256", excluded_provisional_row_sha256)
        recipe_digest = hashlib.sha256(strict_json_dumps(recipe.to_dict()).encode("utf-8")).hexdigest()
        object.__setattr__(
            self,
            "_evidence_key",
            (recipe_digest, csv_sha256, tuple(receipt.source_row_sha256 for receipt in receipts), excluded_provisional_row_sha256),
        )

    @property
    def frame(self) -> pd.DataFrame:
        """Return a deep defensive copy of the internally attested normalized frame."""
        return self._frame.copy(deep=True)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, LoadedChartExport) and self._evidence_key == other._evidence_key

    def __hash__(self) -> int:
        return hash(self._evidence_key)

    def __repr__(self) -> str:
        return (
            f"LoadedChartExport(recipe_id={self.recipe.recipe_id!r}, rows={len(self._frame)}, "
            f"csv_sha256={self.csv_sha256!r}, provisional_excluded={self.excluded_provisional_row_sha256 is not None})"
        )


def _path(value: object, code: str) -> Path:
    try:
        return Path(value)
    except (TypeError, ValueError) as exc:
        raise ExportError(f"{code}_PATH_INVALID") from exc


def _read_csv_snapshot(path: object) -> bytes:
    csv_path = _path(path, "CSV")
    try:
        return csv_path.read_bytes()
    except (OSError, ValueError) as exc:
        raise ExportError(f"CSV_READ_ERROR:{exc}") from exc


def sha256_file(path: object) -> str:
    return hashlib.sha256(_read_csv_snapshot(path)).hexdigest()


def resolve_column(frame: pd.DataFrame, exact_title: str) -> str:
    if not isinstance(frame, pd.DataFrame) or type(exact_title) is not str or not exact_title:
        raise ExportError("CSV_COLUMN_INPUT_INVALID")
    columns = tuple(frame.columns)
    if not all(type(column) is str for column in columns):
        raise ExportError("CSV_COLUMN_INPUT_INVALID")
    matches = [column for column in columns if column == exact_title or column.endswith(f": {exact_title}")]
    if not matches:
        raise ExportError(f"CSV_COLUMN_MISSING:{exact_title}")
    if len(matches) != 1:
        raise ExportError(f"CSV_COLUMN_AMBIGUOUS:{exact_title}:{matches}")
    return matches[0]


def _raw_headers(snapshot: str) -> list[str]:
    try:
        reader = csv.reader(StringIO(snapshot))
        headers = next(reader, None)
        if headers:
            for record in reader:
                if len(record) != len(headers):
                    raise ExportError("CSV_ROW_ARITY_INVALID")
    except csv.Error as exc:
        raise ExportError(f"CSV_PARSE_ERROR:{exc}") from exc
    if not headers:
        raise ExportError("CSV_HEADER_MISSING")
    if len(set(headers)) != len(headers):
        raise ExportError("CSV_HEADER_DUPLICATE")
    return headers


def _read_frame(snapshot: str) -> pd.DataFrame:
    _raw_headers(snapshot)
    try:
        return pd.read_csv(StringIO(snapshot), dtype=str, keep_default_na=False, na_filter=False)
    except (ValueError, pd.errors.ParserError) as exc:
        raise ExportError(f"CSV_PARSE_ERROR:{exc}") from exc


def _integer(value: str, column: str) -> int:
    if not _INTEGER_LEXEME.fullmatch(value):
        raise ExportError(f"CSV_INTEGER_INVALID:{column}")
    return int(value)


def _flag(value: str, column: str) -> int:
    if value not in {"0", "1"}:
        raise ExportError(f"CSV_FLAG_INVALID:{column}")
    return int(value)


def _finite_float(value: str, column: str) -> float:
    if not value.strip():
        raise ExportError(f"CSV_NUMERIC_INVALID:{column}")
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ExportError(f"CSV_NUMERIC_INVALID:{column}") from exc
    if not math.isfinite(parsed):
        raise ExportError(f"CSV_NUMERIC_INVALID:{column}")
    return parsed


def _oscillator(value: str, column: str) -> float:
    parsed = _finite_float(value, column)
    if not _PRECISE_OSCILLATOR_LEXEME.fullmatch(value):
        raise ExportError("INSUFFICIENT_EXPORT_PRECISION")
    return parsed


def _nominal_minutes(recipe: ChartRecipe) -> int:
    value = recipe.chart["timeframe_period"]
    if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]*", value):
        raise ExportError("UNSUPPORTED_TIMEFRAME")
    return int(value)


def _normalized_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    columns = {title: resolve_column(frame, title) for title in REQUIRED_PROBE_COLUMNS}
    normalized: list[dict[str, Any]] = []
    for _, raw_row in frame.iterrows():
        row: dict[str, Any] = {}
        for title in REQUIRED_PROBE_COLUMNS:
            value = raw_row[columns[title]]
            if not isinstance(value, str):
                raise ExportError(f"CSV_NUMERIC_INVALID:{title}")
            if title in _INTEGER_COLUMNS:
                row[title] = _integer(value, title)
            elif title in _FLAG_COLUMNS:
                row[title] = _flag(value, title)
            elif title == "TG_volume" and value.strip().lower() in _MISSING_VOLUME:
                row[title] = None
            elif title in _OSCILLATOR_COLUMNS:
                if value.strip().lower() in _MISSING_OSCILLATOR:
                    row[title] = None
                else:
                    row[title] = _oscillator(value, title)
            elif title in _FLOAT_COLUMNS:
                row[title] = _finite_float(value, title)
            else:
                raise ExportError(f"CSV_COLUMN_MISSING:{title}")
        normalized.append(row)
    _validate_oscillator_prefix(normalized)
    return normalized


def _validate_rows(recipe: ChartRecipe, rows: list[dict[str, Any]]) -> None:
    export = recipe.export
    if len(rows) != export["row_count"]:
        raise ExportError("CSV_ROW_COUNT_MISMATCH")
    _validate_retained_rows(recipe, rows, has_provisional=False, require_confirmed=False)


def _validate_retained_rows(
    recipe: ChartRecipe, rows: list[dict[str, Any]], *, has_provisional: bool, require_confirmed: bool
) -> None:
    export = recipe.export
    if not rows or rows[0]["TG_time_open_ms"] != export["first_bar_open_ms"]:
        raise ExportError("CSV_RANGE_MISMATCH")
    if not has_provisional and rows[-1]["TG_time_close_ms"] != export["last_bar_close_ms"]:
        raise ExportError("CSV_RANGE_MISMATCH")
    if export["loaded_history_start_ms"] > rows[0]["TG_time_open_ms"]:
        raise ExportError("CSV_RANGE_MISMATCH")
    previous_open: int | None = None
    expected_chart = tuple(int(recipe.chart[key]) for key in _CHART_TO_RECIPE.values())
    for row in rows:
        open_ms, close_ms, duration = row["TG_time_open_ms"], row["TG_time_close_ms"], row["TG_duration_ms"]
        for column in _INTEGER_COLUMNS:
            if row[column] < 0:
                raise ExportError(f"CSV_INTEGER_INVALID:{column}")
        if row["TG_volume"] is not None and row["TG_volume"] < 0:
            raise ExportError("CSV_NUMERIC_INVALID:TG_volume")
        if open_ms < 0 or close_ms < 0 or duration < 0 or open_ms >= close_ms or close_ms - open_ms != duration:
            raise ExportError("CSV_DURATION_MISMATCH")
        if previous_open is not None and open_ms <= previous_open:
            raise ExportError("CSV_TIME_ORDER_INVALID")
        previous_open = open_ms
        if require_confirmed and row["TG_is_confirmed"] != 1:
            raise ExportError("INCLUDED_UNCONFIRMED_ROW")
        chart_flags = tuple(row[column] for column in _CHART_COLUMNS)
        if sum(chart_flags) != 1 or chart_flags != expected_chart:
            raise ExportError("CHART_CONSTRUCTION_IDENTITY_ERROR")
    if any(tuple(row[column] for column in _CHART_COLUMNS) != expected_chart for row in rows):
        raise ExportError("CHART_CONSTRUCTION_IDENTITY_ERROR")


def _row_hash(row: dict[str, Any]) -> str:
    return hashlib.sha256(strict_json_dumps(row).encode("utf-8")).hexdigest()


def _normalized_cell(value: object, column: str) -> int | float | None:
    if column in _INTEGER_COLUMNS:
        if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
            raise ExportError(f"NORMALIZED_CELL_INVALID:{column}")
        return int(value)
    if column in _FLAG_COLUMNS:
        if isinstance(value, bool) or not isinstance(value, Integral) or value not in {0, 1}:
            raise ExportError(f"NORMALIZED_CELL_INVALID:{column}")
        return int(value)
    if column == "TG_volume" and value is None:
        return None
    if column in _OSCILLATOR_COLUMNS and value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ExportError(f"NORMALIZED_CELL_INVALID:{column}")
    if column == "TG_volume" and value < 0:
        raise ExportError(f"NORMALIZED_CELL_INVALID:{column}")
    return float(value)


def _detach_normalized_frame(frame: object) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    if not isinstance(frame, pd.DataFrame):
        raise ExportError("NORMALIZED_FRAME_INVALID")
    columns = tuple(frame.columns)
    if not all(type(column) is str for column in columns) or columns != REQUIRED_PROBE_COLUMNS:
        raise ExportError("NORMALIZED_FRAME_COLUMNS_INVALID")
    rows: list[dict[str, Any]] = []
    for values in frame.itertuples(index=False, name=None):
        if len(values) != len(REQUIRED_PROBE_COLUMNS):
            raise ExportError("NORMALIZED_FRAME_COLUMNS_INVALID")
        rows.append({
            column: _normalized_cell(value, column)
            for column, value in zip(REQUIRED_PROBE_COLUMNS, values, strict=True)
        })
    return pd.DataFrame(rows, columns=REQUIRED_PROBE_COLUMNS, dtype=object), rows


def _validate_oscillator_prefix(rows: list[dict[str, Any]]) -> None:
    for column in _OSCILLATOR_COLUMNS:
        has_finite = False
        for row in rows:
            value = row[column]
            if value is None:
                if has_finite:
                    raise ExportError(f"CSV_OSCILLATOR_GAP:{column}")
                continue
            has_finite = True
        if not has_finite:
            raise ExportError(f"CSV_OSCILLATOR_WARMUP_INVALID:{column}")


def _validate_loaded_evidence(
    *,
    recipe: object,
    rows: list[dict[str, Any]],
    receipts: object,
    csv_sha256: object,
    excluded_provisional_row_sha256: object,
) -> None:
    if not isinstance(recipe, ChartRecipe) or recipe.capture_status != "complete":
        raise ExportError("CHART_RECIPE_INVALID")
    if type(csv_sha256) is not str or not re.fullmatch(r"[0-9a-f]{64}", csv_sha256):
        raise ExportError("CSV_SHA256_INVALID")
    if excluded_provisional_row_sha256 is not None and (
        type(excluded_provisional_row_sha256) is not str
        or not re.fullmatch(r"[0-9a-f]{64}", excluded_provisional_row_sha256)
    ):
        raise ExportError("PROVISIONAL_DIGEST_INVALID")
    if not isinstance(receipts, tuple):
        raise ExportError("RECEIPTS_INVALID")
    expected_full_count = len(rows) + (1 if excluded_provisional_row_sha256 is not None else 0)
    if recipe.export["row_count"] != expected_full_count:
        raise ExportError("PROVISIONAL_COUNT_MISMATCH")
    if csv_sha256 != recipe.export["csv_sha256"]:
        raise ExportError("CSV_SHA256_MISMATCH")
    if len(receipts) != len(rows):
        raise ExportError("RECEIPT_COUNT_MISMATCH")
    _validate_retained_rows(
        recipe,
        rows,
        has_provisional=excluded_provisional_row_sha256 is not None,
        require_confirmed=True,
    )
    _validate_oscillator_prefix(rows)
    nominal_minutes = _nominal_minutes(recipe)
    for receipt, row in zip(receipts, rows, strict=True):
        if not isinstance(receipt, BarReceipt):
            raise ExportError("RECEIPT_INVALID")
        if receipt.recipe_id != recipe.recipe_id:
            raise ExportError("RECEIPT_RECIPE_ID_MISMATCH")
        if receipt.source_row_sha256 != _row_hash(row):
            raise ExportError("RECEIPT_ROW_HASH_MISMATCH")
        if receipt.to_dict() != _receipt(recipe, row, nominal_minutes).to_dict():
            raise ExportError("RECEIPT_EXACT_MISMATCH")


def _receipt(recipe: ChartRecipe, row: dict[str, Any], nominal_minutes: int) -> BarReceipt:
    effective_minutes = row["TG_duration_ms"] // 60_000
    return BarReceipt(
        schema_version="mastermind.temporal_bar_receipt.v1", recipe_id=recipe.recipe_id,
        bar_index=row["TG_bar_index"], open_ms=row["TG_time_open_ms"], close_ms=row["TG_time_close_ms"],
        nominal_minutes=nominal_minutes, effective_minutes=effective_minutes, traded_minutes=None,
        volume=row["TG_volume"], trade_count=None, realized_variance=None,
        session_flags={
            "premarket": bool(row["TG_is_premarket"]), "market": bool(row["TG_is_market"]),
            "postmarket": bool(row["TG_is_postmarket"]), "first_session_bar": bool(row["TG_is_firstbar"]),
            "last_session_bar": bool(row["TG_is_lastbar"]), "first_regular_bar": bool(row["TG_is_firstbar_regular"]),
            "last_regular_bar": bool(row["TG_is_lastbar_regular"]),
        },
        clipped=effective_minutes < nominal_minutes, confirmed=True, empty_interval=False,
        known_at_ms=row["TG_time_close_ms"], source_row_sha256=_row_hash(row),
    )


def load_chart_export(recipe_path: Path, csv_path: Path) -> LoadedChartExport:
    try:
        recipe = ChartRecipe.from_json(_path(recipe_path, "CHART_RECIPE"))
    except (ContractError, ExportError, OSError, UnicodeError, TypeError, ValueError) as exc:
        raise ExportError(f"CHART_RECIPE_INVALID:{exc}") from exc
    if recipe.capture_status != "complete":
        raise ExportError("UNRESOLVED_DATA:INCOMPLETE_RECIPE")
    snapshot = _read_csv_snapshot(csv_path)
    actual_hash = hashlib.sha256(snapshot).hexdigest()
    if actual_hash != recipe.export["csv_sha256"]:
        raise ExportError("CSV_HASH_MISMATCH")
    nominal_minutes = _nominal_minutes(recipe)
    try:
        decoded_snapshot = snapshot.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ExportError(f"CSV_DECODE_ERROR:{exc}") from exc
    rows = _normalized_rows(_read_frame(decoded_snapshot))
    _validate_rows(recipe, rows)
    unconfirmed = [index for index, row in enumerate(rows) if row["TG_is_confirmed"] == 0]
    if any(index != len(rows) - 1 for index in unconfirmed):
        raise ExportError("INTERIOR_UNCONFIRMED_ROW")
    provisional = rows[-1] if unconfirmed else None
    included = rows[:-1] if provisional is not None else rows
    receipts = tuple(_receipt(recipe, row, nominal_minutes) for row in included)
    return LoadedChartExport(
        recipe=recipe, frame=pd.DataFrame(included, columns=REQUIRED_PROBE_COLUMNS, dtype=object), receipts=receipts,
        csv_sha256=actual_hash, excluded_provisional_row_sha256=_row_hash(provisional) if provisional is not None else None,
    )
