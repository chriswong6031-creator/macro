"""Immutable, strict-JSON contracts for the temporal-grain W1A study.

The records here describe research evidence only.  They deliberately provide no
ranking, gating, sizing, trading, or Prophet authority.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import json
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Literal

from lib.dataos.identity import IdentityError, parse_future_id, parse_fx_id


class ContractError(ValueError):
    """Raised when a temporal-scale evidence record is malformed."""


CHART_RECIPE_SCHEMA = "mastermind.temporal_chart_recipe.v1"
BAR_RECEIPT_SCHEMA = "mastermind.temporal_bar_receipt.v1"
KERNEL_SIGNATURE_SCHEMA = "mastermind.temporal_kernel_signature.v1"
ARTIFACT_ATTACK_SCHEMA = "mastermind.temporal_artifact_attack.v1"

EXPORT_PRECISION_INSUFFICIENT = "INSUFFICIENT_EXPORT_PRECISION"
REQUIRED_EXPORT_COLUMNS = (
    "TG_time_open_ms",
    "TG_time_close_ms",
    "TG_time_tradingday_ms",
    "TG_duration_ms",
    "TG_bar_index",
    "TG_is_confirmed",
    "TG_is_market",
    "TG_is_premarket",
    "TG_is_postmarket",
    "TG_is_firstbar",
    "TG_is_lastbar",
    "TG_is_firstbar_regular",
    "TG_is_lastbar_regular",
    "TG_open",
    "TG_high",
    "TG_low",
    "TG_close",
    "TG_volume",
    "TG_rsi",
    "TG_rsi_macd",
    "TG_rsi_macd_signal",
    "TG_rsi_macd_hist",
    "TG_stoch_k",
    "TG_stoch_d",
)

_HEX = re.compile(r"^[0-9a-f]+$")
_AUTHORITY_KEYS = frozenset(
    {"may_rank", "may_gate", "may_size", "may_trade", "may_modify_prophet"}
)
_RECIPE_KEYS = frozenset(
    {
        "schema_version", "recipe_id", "captured_at", "capture_status", "observer",
        "instrument", "chart", "indicator", "export", "rights", "missing_fields",
    }
)
_INSTRUMENT_KEYS = frozenset(
    {
        "display_symbol", "tickerid", "main_tickerid", "asset_class", "exchange",
        "vendor_feed", "currency", "contract_month", "continuous_symbol", "roll_recipe",
        "settlement_basis", "canonical_id",
    }
)
_CHART_KEYS = frozenset(
    {
        "timeframe_period", "named_session", "exchange_timezone", "chart_timezone",
        "extended_hours_enabled", "price_adjustment", "dividend_adjustment",
        "back_adjustment", "settlement_as_close", "allowed_session_variants",
        "chart_is_standard", "chart_is_heikinashi", "chart_is_renko",
        "chart_is_linebreak", "chart_is_kagi", "chart_is_pnf", "chart_is_range",
    }
)
_INDICATOR_KEYS = frozenset(
    {
        "observed_indicator_family", "observed_indicator_title", "observed_indicator_source_kind",
        "observed_indicator_source_hash", "observed_indicator_inputs", "probe_indicator_family",
        "probe_source_git_blob_sha", "probe_inputs", "probe_ema_adjust", "probe_rma_seed",
        "observed_equals_probe",
    }
)
_EXPORT_KEYS = frozenset(
    {
        "csv_filename", "csv_sha256", "row_count", "first_bar_open_ms",
        "last_bar_close_ms", "loaded_history_start_ms",
    }
)
_RIGHTS_KEYS = frozenset({"use", "redistribution", "source_reference"})
_SESSION_FLAG_KEYS = frozenset(
    {
        "premarket", "market", "postmarket", "first_session_bar", "last_session_bar",
        "first_regular_bar", "last_regular_bar",
    }
)
_CHART_TYPE_FLAGS = (
    "chart_is_standard", "chart_is_heikinashi", "chart_is_renko", "chart_is_linebreak",
    "chart_is_kagi", "chart_is_pnf", "chart_is_range",
)
_NONSTANDARD_CHART_TYPE_FLAGS = _CHART_TYPE_FLAGS[1:]
_OBSERVED_SOURCE_KINDS = frozenset(
    {"repository_exact", "pine_source_exact", "tradingview_builtin", "invite_only", "closed_source", "unknown"}
)
_UNRESOLVABLE_OBSERVED_SOURCE_KINDS = frozenset({"invite_only", "closed_source", "unknown"})
_PROBE_INPUT_KEYS = frozenset(
    {"rsi_len", "macd_fast", "macd_slow", "macd_signal", "stoch_len", "smooth_k", "smooth_d"}
)
_REQUIRED_ARTIFACT_AXES = frozenset({"G", "A", "K", "PARITY", "TRUNCATION"})


def _reject_nonfinite(value: object, path: str = "root") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ContractError(f"{path} must be finite")
    if isinstance(value, Mapping):
        for key, child in value.items():
            _reject_nonfinite(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_nonfinite(child, f"{path}[{index}]")


def _require_json_value(value: object, path: str = "root") -> None:
    """Reject values that cannot survive the strict JSON evidence boundary."""
    if value is None or type(value) in {bool, int, str}:
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractError(f"{path} must be finite")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ContractError(f"{path} object keys must be strings")
            _require_json_value(child, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _require_json_value(child, f"{path}[{index}]")
        return
    raise ContractError(f"{path} must be strict JSON data")


def strict_json_dumps(value: object) -> str:
    """Serialize strict canonical JSON; NaN and infinity are never evidence."""
    _require_json_value(value)
    return json.dumps(
        _thaw(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Atomically write one UTF-8, canonical JSON object."""
    payload = strict_json_dumps(value) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(payload, encoding="utf-8")
    temp.replace(path)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ContractError("object keys must be strings")
        return MappingProxyType({key: _freeze(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(child) for child in value)
    if isinstance(value, tuple):
        return tuple(_freeze(child) for child in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw(child) for child in value]
    return value


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{path} must be an object")
    return value


def _require_keys(raw: Mapping[str, Any], allowed: frozenset[str], path: str) -> None:
    if not all(isinstance(key, str) for key in raw):
        raise ContractError(f"{path} object keys must be strings")
    actual = set(raw)
    missing = allowed - actual
    unknown = actual - allowed
    if missing:
        raise ContractError(f"{path} missing required fields: {sorted(missing)}")
    if unknown:
        raise ContractError(f"{path} has unknown fields: {sorted(unknown)}")


def _require_nonempty(value: object, path: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{path} must be a nonempty string")


def _require_bool(value: object, path: str) -> None:
    if type(value) is not bool:
        raise ContractError(f"{path} must be boolean")


def _require_int(value: object, path: str, *, minimum: int | None = None) -> None:
    if type(value) is not int:
        raise ContractError(f"{path} must be an integer")
    if minimum is not None and value < minimum:
        raise ContractError(f"{path} must be at least {minimum}")


def _require_hex(value: object, length: int, path: str) -> None:
    if not isinstance(value, str) or len(value) != length or not _HEX.fullmatch(value):
        raise ContractError(f"{path} must be {length}-hex")


def _reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    object_value: dict[str, Any] = {}
    for key, value in pairs:
        if key in object_value:
            raise ContractError(f"duplicate JSON object key: {key}")
        object_value[key] = value
    return object_value


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_object_keys)
    except ContractError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read strict JSON {path}: {exc}") from exc
    _reject_nonfinite(raw)
    return _mapping(raw, "root")


def _validate_authority(authority: Mapping[str, Any]) -> None:
    if set(authority) != _AUTHORITY_KEYS:
        raise ContractError("authority must contain exactly the zero-authority fields")
    if any(value is not False for value in authority.values()):
        raise ContractError("authority must remain exactly false")


def _validate_indicator_channel(channel: Mapping[str, Any], name: str) -> None:
    _require_keys(channel, frozenset({"status"}), name)
    if channel.get("status") not in {"PASS", "FAIL", "UNRESOLVED_DATA"}:
        raise ContractError(f"{name}.status is unknown")


def _missing_recipe_fields(raw: Mapping[str, Any]) -> set[str]:
    missing: set[str] = set()
    for section, keys in (
        ("instrument", ("display_symbol", "tickerid", "main_tickerid", "asset_class", "exchange", "vendor_feed", "currency")),
        ("chart", ("timeframe_period", "named_session", "exchange_timezone", "chart_timezone", "price_adjustment", "dividend_adjustment", "back_adjustment", "settlement_as_close", *_CHART_TYPE_FLAGS)),
        ("indicator", ("observed_indicator_family", "observed_indicator_title", "observed_indicator_source_kind", "observed_indicator_source_hash", "observed_indicator_inputs", "probe_indicator_family", "probe_source_git_blob_sha", "probe_inputs", "probe_rma_seed")),
        ("export", ("csv_filename", "csv_sha256", "row_count", "first_bar_open_ms", "last_bar_close_ms", "loaded_history_start_ms")),
        ("rights", ("use", "redistribution", "source_reference")),
    ):
        section_raw = _mapping(raw[section], section)
        for key in keys:
            value = section_raw[key]
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.add(f"{section}.{key}")
    chart = _mapping(raw["chart"], "chart")
    type_values = [chart[key] for key in _CHART_TYPE_FLAGS]
    if not all(type(value) is bool for value in type_values):
        missing.add("chart.type_coherence")
    else:
        standard = chart["chart_is_standard"]
        nonstandard_count = sum(chart[key] for key in _NONSTANDARD_CHART_TYPE_FLAGS)
        if standard != (nonstandard_count == 0) or nonstandard_count > 1:
            missing.add("chart.type_coherence")
    instrument = _mapping(raw["instrument"], "instrument")
    asset_class = instrument["asset_class"]
    continuous_symbol = instrument["continuous_symbol"]
    if asset_class == "futures":
        if continuous_symbol:
            if instrument["roll_recipe"] is None or not str(instrument["roll_recipe"]).strip():
                missing.add("instrument.roll_recipe")
        elif instrument["contract_month"] is None or not str(instrument["contract_month"]).strip():
            missing.add("instrument.contract_month")
    if asset_class == "cfd" and continuous_symbol and (
        instrument["roll_recipe"] is None or not str(instrument["roll_recipe"]).strip()
    ):
        missing.add("instrument.roll_recipe")
    return missing


@dataclass(frozen=True, slots=True)
class ChartRecipe:
    schema_version: str
    recipe_id: str
    captured_at: str
    capture_status: Literal["complete", "incomplete"]
    observer: str
    instrument: Mapping[str, Any]
    chart: Mapping[str, Any]
    indicator: Mapping[str, Any]
    export: Mapping[str, Any]
    rights: Mapping[str, Any]
    missing_fields: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("instrument", "chart", "indicator", "export", "rights"):
            object.__setattr__(self, name, _freeze(_mapping(getattr(self, name), name)))
        if isinstance(self.missing_fields, (str, bytes)) or not isinstance(self.missing_fields, (list, tuple)):
            raise ContractError("missing_fields must be a non-string sequence")
        object.__setattr__(self, "missing_fields", tuple(self.missing_fields))
        _require_json_value(self.to_dict())
        self.validate()

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ChartRecipe":
        raw = _mapping(raw, "recipe")
        _reject_nonfinite(raw)
        _require_keys(raw, _RECIPE_KEYS, "recipe")
        recipe = cls(
            schema_version=raw["schema_version"], recipe_id=raw["recipe_id"],
            captured_at=raw["captured_at"], capture_status=raw["capture_status"],
            observer=raw["observer"], instrument=_freeze(_mapping(raw["instrument"], "instrument")),
            chart=_freeze(_mapping(raw["chart"], "chart")),
            indicator=_freeze(_mapping(raw["indicator"], "indicator")),
            export=_freeze(_mapping(raw["export"], "export")),
            rights=_freeze(_mapping(raw["rights"], "rights")),
            missing_fields=tuple(raw["missing_fields"]) if isinstance(raw["missing_fields"], list) else (),
        )
        if not isinstance(raw["missing_fields"], list) or not all(isinstance(item, str) for item in recipe.missing_fields):
            raise ContractError("missing_fields must be a list of field paths")
        recipe.validate()
        return recipe

    @classmethod
    def from_json(cls, path: Path) -> "ChartRecipe":
        return cls.from_dict(_load_json(path))

    def validate(self) -> None:
        if self.schema_version != CHART_RECIPE_SCHEMA:
            raise ContractError("schema_version must be mastermind.temporal_chart_recipe.v1")
        for name in ("recipe_id", "captured_at", "observer"):
            _require_nonempty(getattr(self, name), name)
        try:
            if not self.captured_at.endswith("Z"):
                raise ValueError
            offset = datetime.fromisoformat(f"{self.captured_at[:-1]}+00:00").utcoffset()
            if offset is None or offset.total_seconds() != 0:
                raise ValueError
        except (AttributeError, TypeError, ValueError) as exc:
            raise ContractError("captured_at must be ISO-8601 UTC ending in Z") from exc
        if self.capture_status not in {"complete", "incomplete"}:
            raise ContractError("capture_status must be complete or incomplete")
        if not all(isinstance(item, str) for item in self.missing_fields):
            raise ContractError("missing_fields must contain field paths")

        def present(section: Mapping[str, Any], key: str) -> bool:
            value = section[key]
            return not (
                self.capture_status == "incomplete"
                and (value is None or (isinstance(value, str) and not value.strip()))
            )

        required_instrument_keys = _INSTRUMENT_KEYS - {"canonical_id"}
        missing_instrument_keys = required_instrument_keys - set(self.instrument)
        unknown_instrument_keys = set(self.instrument) - _INSTRUMENT_KEYS
        if missing_instrument_keys:
            raise ContractError(f"instrument missing required fields: {sorted(missing_instrument_keys)}")
        if unknown_instrument_keys:
            raise ContractError(f"instrument has unknown fields: {sorted(unknown_instrument_keys)}")
        _require_keys(self.chart, _CHART_KEYS, "chart")
        _require_keys(self.indicator, _INDICATOR_KEYS, "indicator")
        _require_keys(self.export, _EXPORT_KEYS, "export")
        _require_keys(self.rights, _RIGHTS_KEYS, "rights")
        if present(self.instrument, "asset_class") and self.instrument["asset_class"] not in {"equity", "futures", "spot_fx", "cfd", "etf", "other"}:
            raise ContractError("instrument.asset_class is unknown")
        for key in ("display_symbol", "tickerid", "main_tickerid", "exchange", "vendor_feed", "currency"):
            if present(self.instrument, key) and not isinstance(self.instrument[key], str):
                raise ContractError(f"instrument.{key} must be a string")
        for key in ("contract_month", "continuous_symbol", "roll_recipe", "settlement_basis"):
            if self.instrument[key] is not None and not isinstance(self.instrument[key], str):
                raise ContractError(f"instrument.{key} must be a string or null")
        contract_month = self.instrument["contract_month"]
        if contract_month is not None and (
            not re.fullmatch(r"[0-9]{6}", contract_month) or not 1 <= int(contract_month[4:6]) <= 12
        ):
            raise ContractError("instrument.contract_month must be YYYYMM with a valid month")
        vendor_feed = self.instrument["vendor_feed"]
        if isinstance(vendor_feed, str) and vendor_feed.strip().lower().split(":", 1)[0] in {"yahoo", "polygon", "massive"}:
            raise ContractError("instrument.vendor_feed proxy cannot satisfy a TradingView recipe identity")
        if present(self.chart, "named_session") and self.chart["named_session"] not in {"regular", "extended", "24h", "us_regular", "vendor_named"}:
            raise ContractError("chart.named_session is unknown")
        for key in ("timeframe_period", "exchange_timezone", "chart_timezone"):
            if present(self.chart, key) and (not isinstance(self.chart[key], str) or not self.chart[key].strip()):
                raise ContractError(f"chart.{key} must be a nonempty string")
        if present(self.chart, "price_adjustment") and self.chart["price_adjustment"] not in {"split_adjusted", "raw", "other"}:
            raise ContractError("chart.price_adjustment is unknown")
        if present(self.chart, "dividend_adjustment") and self.chart["dividend_adjustment"] not in {"on", "off", "unknown"}:
            raise ContractError("chart.dividend_adjustment is unknown")
        if present(self.chart, "back_adjustment") and self.chart["back_adjustment"] not in {"on", "off", "not_applicable", "unknown"}:
            raise ContractError("chart.back_adjustment is unknown")
        if present(self.chart, "settlement_as_close") and self.chart["settlement_as_close"] not in {"on", "off", "not_applicable", "unknown"}:
            raise ContractError("chart.settlement_as_close is unknown")
        _require_bool(self.chart["extended_hours_enabled"], "chart.extended_hours_enabled")
        if not isinstance(self.chart["allowed_session_variants"], tuple) or not self.chart["allowed_session_variants"]:
            raise ContractError("chart.allowed_session_variants must be a nonempty list")
        if not all(isinstance(item, str) and item in {"regular", "extended", "24h", "us_regular", "vendor_named"} for item in self.chart["allowed_session_variants"]):
            raise ContractError("chart.allowed_session_variants contains an unknown session")
        for key in _CHART_TYPE_FLAGS:
            value = self.chart[key]
            if value is not None and type(value) is not bool:
                raise ContractError(f"chart.{key} must be boolean or null while incomplete")
        if present(self.indicator, "observed_indicator_source_kind") and self.indicator["observed_indicator_source_kind"] not in _OBSERVED_SOURCE_KINDS:
            raise ContractError("indicator.observed_indicator_source_kind is unknown")
        for key in ("observed_indicator_family", "observed_indicator_title", "probe_indicator_family", "probe_rma_seed"):
            if present(self.indicator, key) and (not isinstance(self.indicator[key], str) or not self.indicator[key].strip()):
                raise ContractError(f"indicator.{key} must be a nonempty string")
        observed_equals_probe = self.indicator["observed_equals_probe"]
        if type(observed_equals_probe) is not bool and observed_equals_probe != "unknown":
            raise ContractError("indicator.observed_equals_probe must be true, false, or unknown")
        if present(self.indicator, "probe_source_git_blob_sha"):
            _require_hex(self.indicator["probe_source_git_blob_sha"], 40, "indicator.probe_source_git_blob_sha")
        if self.indicator["observed_indicator_source_hash"] is not None:
            _require_hex(self.indicator["observed_indicator_source_hash"], 40, "indicator.observed_indicator_source_hash")
        for key in ("observed_indicator_inputs", "probe_inputs"):
            if self.indicator[key] is not None:
                _mapping(self.indicator[key], f"indicator.{key}")
        probe_inputs = self.indicator["probe_inputs"]
        if present(self.indicator, "probe_inputs"):
            if not isinstance(probe_inputs, Mapping) or not probe_inputs:
                raise ContractError("indicator.probe_inputs must contain the frozen owner input inventory")
            _require_keys(probe_inputs, _PROBE_INPUT_KEYS, "indicator.probe_inputs")
            for key, value in probe_inputs.items():
                _require_int(value, f"indicator.probe_inputs.{key}", minimum=1)
        if present(self.indicator, "probe_rma_seed") and self.indicator["probe_rma_seed"] != "sma_seeded":
            raise ContractError("indicator.probe_rma_seed is unknown")
        _require_bool(self.indicator["probe_ema_adjust"], "indicator.probe_ema_adjust")
        if present(self.export, "csv_filename"):
            _require_nonempty(self.export["csv_filename"], "export.csv_filename")
        if present(self.export, "csv_sha256"):
            _require_hex(self.export["csv_sha256"], 64, "export.csv_sha256")
        if present(self.rights, "use") and self.rights["use"] != "local_research_only":
            raise ContractError("rights.use must be local_research_only")
        if present(self.rights, "redistribution") and self.rights["redistribution"] not in {"blocked", "allowed", "unknown"}:
            raise ContractError("rights.redistribution is unknown")
        if present(self.rights, "source_reference"):
            _require_nonempty(self.rights["source_reference"], "rights.source_reference")
        for key in ("row_count", "first_bar_open_ms", "last_bar_close_ms", "loaded_history_start_ms"):
            if present(self.export, key):
                _require_int(self.export[key], f"export.{key}", minimum=0)
        if present(self.export, "row_count") and self.export["row_count"] < 1:
            raise ContractError("export.row_count must be at least 1")
        if present(self.export, "loaded_history_start_ms") and present(self.export, "first_bar_open_ms") and self.export["loaded_history_start_ms"] > self.export["first_bar_open_ms"]:
            raise ContractError("export.loaded_history_start_ms must not follow first_bar_open_ms")
        if present(self.export, "first_bar_open_ms") and present(self.export, "last_bar_close_ms") and self.export["first_bar_open_ms"] >= self.export["last_bar_close_ms"]:
            raise ContractError("export first/last bar times are inconsistent")
        missing = _missing_recipe_fields(self.to_dict())
        declared = set(self.missing_fields)
        if len(declared) != len(self.missing_fields):
            raise ContractError("missing_fields must not contain duplicates")
        if self.capture_status == "complete":
            if missing:
                raise ContractError(f"complete recipe has missing fields: {sorted(missing)}")
            if declared:
                raise ContractError("complete recipe requires missing_fields=[]")
        elif declared != missing:
            raise ContractError(f"incomplete recipe must name exactly missing fields: {sorted(missing)}")
        source_kind = self.indicator["observed_indicator_source_kind"]
        if source_kind in _UNRESOLVABLE_OBSERVED_SOURCE_KINDS and self.capture_status == "complete":
            raise ContractError("indicator.observed_indicator_source_kind cannot be complete without exact source math")
        equality_fields_present = all(
            present(self.indicator, key)
            for key in (
                "observed_indicator_family", "observed_indicator_source_kind",
                "observed_indicator_source_hash", "observed_indicator_inputs",
                "probe_indicator_family", "probe_source_git_blob_sha", "probe_inputs",
            )
        )
        if observed_equals_probe is True and equality_fields_present:
            if source_kind not in {"repository_exact", "pine_source_exact"}:
                raise ContractError("indicator.observed_equals_probe requires an exact observed source")
            if (
                self.indicator["observed_indicator_family"] != self.indicator["probe_indicator_family"]
                or self.indicator["observed_indicator_source_hash"] != self.indicator["probe_source_git_blob_sha"]
                or self.indicator["observed_indicator_inputs"] != self.indicator["probe_inputs"]
            ):
                raise ContractError("indicator.observed_equals_probe requires exact source hash and input equality")
        asset_class = self.instrument["asset_class"]
        continuous = self.instrument["continuous_symbol"]
        if asset_class in {"futures", "cfd"} and continuous:
            for path, value in (
                ("instrument.vendor_feed", self.instrument["vendor_feed"]),
                ("instrument.roll_recipe", self.instrument["roll_recipe"]),
                ("chart.named_session", self.chart["named_session"]),
            ):
                if not value and self.capture_status == "complete":
                    raise ContractError(f"continuous contract requires {path}")
        elif asset_class == "futures" and not self.instrument["contract_month"] and self.capture_status == "complete":
            raise ContractError("concrete futures require instrument.contract_month")
        canonical_id = self.instrument.get("canonical_id")
        if canonical_id is not None:
            if not isinstance(canonical_id, str) or not canonical_id:
                raise ContractError("instrument.canonical_id must be nonempty when declared")
            try:
                if asset_class == "futures":
                    _, _, month = parse_future_id(canonical_id)
                    if not continuous and month != self.instrument["contract_month"]:
                        raise ContractError("instrument.canonical_id contract month disagrees")
                elif asset_class == "spot_fx":
                    parse_fx_id(canonical_id)
                else:
                    raise ContractError("instrument.canonical_id is only defined for futures or spot_fx")
            except IdentityError as exc:
                raise ContractError(f"instrument.canonical_id is not a canonical {asset_class} identity") from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "recipe_id": self.recipe_id,
            "captured_at": self.captured_at, "capture_status": self.capture_status,
            "observer": self.observer, "instrument": _thaw(self.instrument),
            "chart": _thaw(self.chart), "indicator": _thaw(self.indicator),
            "export": _thaw(self.export), "rights": _thaw(self.rights),
            "missing_fields": list(self.missing_fields),
        }


@dataclass(frozen=True, slots=True)
class BarReceipt:
    schema_version: str
    recipe_id: str
    bar_index: int
    open_ms: int
    close_ms: int
    nominal_minutes: int
    effective_minutes: int
    traded_minutes: int | None
    volume: float | None
    trade_count: int | None
    realized_variance: float | None
    session_flags: Mapping[str, bool]
    clipped: bool
    confirmed: bool
    empty_interval: bool
    known_at_ms: int
    source_row_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_flags", _freeze(_mapping(self.session_flags, "session_flags")))
        _require_json_value(self.to_dict())
        self.validate()

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "BarReceipt":
        raw = _mapping(raw, "bar receipt")
        _reject_nonfinite(raw)
        names = frozenset(cls.__dataclass_fields__)
        _require_keys(raw, names, "bar receipt")
        receipt = cls(**{name: _freeze(raw[name]) for name in names})
        receipt.validate()
        return receipt

    @classmethod
    def from_json(cls, path: Path) -> "BarReceipt":
        return cls.from_dict(_load_json(path))

    def validate(self) -> None:
        if self.schema_version != BAR_RECEIPT_SCHEMA:
            raise ContractError("schema_version must be mastermind.temporal_bar_receipt.v1")
        _require_nonempty(self.recipe_id, "recipe_id")
        for key in ("bar_index", "open_ms", "close_ms", "nominal_minutes", "effective_minutes", "known_at_ms"):
            _require_int(getattr(self, key), key, minimum=0)
        if self.open_ms >= self.close_ms or self.close_ms > self.known_at_ms:
            raise ContractError("open_ms < close_ms <= known_at_ms is required")
        if self.nominal_minutes < 1:
            raise ContractError("nominal_minutes must be positive")
        if self.effective_minutes != (self.close_ms - self.open_ms) // 60_000:
            raise ContractError("effective_minutes must equal (close_ms-open_ms)//60000")
        if self.clipped is not (self.effective_minutes < self.nominal_minutes):
            raise ContractError("clipped must mean effective_minutes is less than nominal_minutes")
        for key in ("clipped", "confirmed", "empty_interval"):
            _require_bool(getattr(self, key), key)
        if self.traded_minutes is not None:
            _require_int(self.traded_minutes, "traded_minutes", minimum=0)
        if self.trade_count is not None:
            _require_int(self.trade_count, "trade_count", minimum=0)
        for key in ("volume", "realized_variance"):
            value = getattr(self, key)
            if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0):
                raise ContractError(f"{key} must be a nonnegative finite number or null")
        if self.empty_interval and any(value is not None for value in (self.volume, self.trade_count, self.realized_variance)):
            raise ContractError("empty_interval cannot carry volume, trade_count, or realized_variance")
        _require_keys(self.session_flags, _SESSION_FLAG_KEYS, "session_flags")
        for key, value in self.session_flags.items():
            _require_bool(value, f"session_flags.{key}")
        _require_hex(self.source_row_sha256, 64, "source_row_sha256")

    def to_dict(self) -> dict[str, Any]:
        return {name: _thaw(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class KernelSignature:
    schema_version: str
    indicator_spec_hash: str
    input_series: str
    components: tuple[Mapping[str, Any], ...]
    bar_memory: Mapping[str, float]
    clock_basis: Literal["bar_count", "elapsed_time", "traded_time", "volume_time", "trade_time", "variance_time"]
    clock_parameter: Mapping[str, Any]
    warmup_first_finite_index: Mapping[str, int | None]
    linear_diagnostics: Mapping[str, Any]
    nonlinear_caveat: str

    def __post_init__(self) -> None:
        if not isinstance(self.components, (list, tuple)):
            raise ContractError("components must be a list")
        object.__setattr__(self, "components", tuple(_freeze(item) for item in self.components))
        for name in ("bar_memory", "clock_parameter", "warmup_first_finite_index", "linear_diagnostics"):
            object.__setattr__(self, name, _freeze(_mapping(getattr(self, name), name)))
        _require_json_value(self.to_dict())
        self.validate()

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "KernelSignature":
        raw = _mapping(raw, "kernel signature")
        _reject_nonfinite(raw)
        names = frozenset(cls.__dataclass_fields__)
        _require_keys(raw, names, "kernel signature")
        if not isinstance(raw["components"], list):
            raise ContractError("components must be a list")
        signature = cls(
            schema_version=raw["schema_version"], indicator_spec_hash=raw["indicator_spec_hash"],
            input_series=raw["input_series"], components=tuple(_freeze(item) for item in raw["components"]),
            bar_memory=_freeze(_mapping(raw["bar_memory"], "bar_memory")),
            clock_basis=raw["clock_basis"], clock_parameter=_freeze(_mapping(raw["clock_parameter"], "clock_parameter")),
            warmup_first_finite_index=_freeze(_mapping(raw["warmup_first_finite_index"], "warmup_first_finite_index")),
            linear_diagnostics=_freeze(_mapping(raw["linear_diagnostics"], "linear_diagnostics")),
            nonlinear_caveat=raw["nonlinear_caveat"],
        )
        signature.validate()
        return signature

    @classmethod
    def from_json(cls, path: Path) -> "KernelSignature":
        return cls.from_dict(_load_json(path))

    def validate(self) -> None:
        if self.schema_version != KERNEL_SIGNATURE_SCHEMA:
            raise ContractError("schema_version must be mastermind.temporal_kernel_signature.v1")
        _require_hex(self.indicator_spec_hash, 64, "indicator_spec_hash")
        _require_nonempty(self.input_series, "input_series")
        if self.clock_basis not in {"bar_count", "elapsed_time", "traded_time", "volume_time", "trade_time", "variance_time"}:
            raise ContractError("clock_basis is unknown")
        _require_nonempty(self.nonlinear_caveat, "nonlinear_caveat")
        if not all(isinstance(item, Mapping) for item in self.components):
            raise ContractError("components must contain objects")
        for key, value in self.bar_memory.items():
            if not isinstance(key, str) or not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
                raise ContractError("bar_memory must map names to positive finite numbers")
        for key, value in self.warmup_first_finite_index.items():
            if not isinstance(key, str) or (value is not None and (type(value) is not int or value < 0)):
                raise ContractError("warmup_first_finite_index must map names to nonnegative integers or null")

    def to_dict(self) -> dict[str, Any]:
        return {name: _thaw(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class ArtifactTest:
    test_id: str
    axis: Literal["G", "A", "K", "D", "PARITY", "TRUNCATION", "DENSITY"]
    variant_id: str
    input_hash: str
    status: Literal["PASS", "FAIL", "UNAVAILABLE"]
    metrics: Mapping[str, Any]
    findings: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "metrics", _freeze(_mapping(self.metrics, "metrics")))
        if isinstance(self.findings, str) or not isinstance(self.findings, (list, tuple)):
            raise ContractError("findings must be a non-string sequence")
        object.__setattr__(self, "findings", tuple(self.findings))
        _require_json_value(self.to_dict())
        self.validate()

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ArtifactTest":
        raw = _mapping(raw, "artifact test")
        _reject_nonfinite(raw)
        names = frozenset(cls.__dataclass_fields__)
        _require_keys(raw, names, "artifact test")
        if not isinstance(raw["findings"], list):
            raise ContractError("findings must be a list")
        result = cls(
            test_id=raw["test_id"], axis=raw["axis"], variant_id=raw["variant_id"],
            input_hash=raw["input_hash"], status=raw["status"],
            metrics=_freeze(_mapping(raw["metrics"], "metrics")), findings=tuple(raw["findings"]),
        )
        result.validate()
        return result

    @classmethod
    def from_json(cls, path: Path) -> "ArtifactTest":
        return cls.from_dict(_load_json(path))

    def validate(self) -> None:
        for name in ("test_id", "variant_id"):
            _require_nonempty(getattr(self, name), name)
        if self.axis not in {"G", "A", "K", "D", "PARITY", "TRUNCATION", "DENSITY"}:
            raise ContractError("axis is unknown")
        if self.status not in {"PASS", "FAIL", "UNAVAILABLE"}:
            raise ContractError("status is unknown")
        _require_hex(self.input_hash, 64, "input_hash")
        if not all(isinstance(item, str) and item for item in self.findings):
            raise ContractError("findings must contain nonempty deterministic tokens")

    def to_dict(self) -> dict[str, Any]:
        return {name: _thaw(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class ArtifactAttackResult:
    schema_version: str
    operation_key: str
    recipes: tuple[str, ...]
    frozen_grid_hash: str
    trial_family: str
    tests: tuple[ArtifactTest, ...]
    parity: Mapping[str, Any]
    mechanical_status: Literal["ARTIFACT", "UNRESOLVED_DATA", "MECHANICALLY_SURVIVES"]
    final_mechanism_classification: None
    mechanical_receipts: tuple[str, ...]
    observed_indicator_reproduction: Mapping[str, Any]
    observed_indicator_reproduction_receipts: tuple[str, ...]
    owner_probe_control: Mapping[str, Any]
    owner_probe_control_receipts: tuple[str, ...]
    authority: Mapping[str, bool]

    def __post_init__(self) -> None:
        for name in ("recipes", "tests", "mechanical_receipts", "observed_indicator_reproduction_receipts", "owner_probe_control_receipts"):
            value = getattr(self, name)
            if isinstance(value, str) or not isinstance(value, (list, tuple)):
                raise ContractError(f"{name} must be a non-string sequence")
        if not all(isinstance(test, ArtifactTest) for test in self.tests):
            raise ContractError("tests must contain ArtifactTest records")
        object.__setattr__(self, "recipes", tuple(self.recipes))
        object.__setattr__(self, "tests", tuple(self.tests))
        object.__setattr__(self, "mechanical_receipts", tuple(self.mechanical_receipts))
        object.__setattr__(self, "observed_indicator_reproduction_receipts", tuple(self.observed_indicator_reproduction_receipts))
        object.__setattr__(self, "owner_probe_control_receipts", tuple(self.owner_probe_control_receipts))
        for name in ("parity", "observed_indicator_reproduction", "owner_probe_control", "authority"):
            object.__setattr__(self, name, _freeze(_mapping(getattr(self, name), name)))
        _require_json_value(self.to_dict())
        self.validate()

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ArtifactAttackResult":
        raw = _mapping(raw, "artifact attack result")
        _reject_nonfinite(raw)
        authority = _mapping(raw.get("authority"), "authority")
        _validate_authority(authority)
        names = frozenset(cls.__dataclass_fields__)
        _require_keys(raw, names, "artifact attack result")
        if not all(isinstance(raw[key], list) for key in ("recipes", "tests", "mechanical_receipts", "observed_indicator_reproduction_receipts", "owner_probe_control_receipts")):
            raise ContractError("recipes, tests, and all receipt collections must be lists")
        result = cls(
            schema_version=raw["schema_version"], operation_key=raw["operation_key"],
            recipes=tuple(raw["recipes"]), frozen_grid_hash=raw["frozen_grid_hash"],
            trial_family=raw["trial_family"], tests=tuple(
                item if isinstance(item, ArtifactTest) else ArtifactTest.from_dict(_mapping(item, "tests[]"))
                for item in raw["tests"]
            ), parity=_freeze(_mapping(raw["parity"], "parity")),
            mechanical_status=raw["mechanical_status"],
            final_mechanism_classification=raw["final_mechanism_classification"],
            mechanical_receipts=tuple(raw["mechanical_receipts"]),
            observed_indicator_reproduction=_freeze(_mapping(raw["observed_indicator_reproduction"], "observed_indicator_reproduction")),
            observed_indicator_reproduction_receipts=tuple(raw["observed_indicator_reproduction_receipts"]),
            owner_probe_control=_freeze(_mapping(raw["owner_probe_control"], "owner_probe_control")),
            owner_probe_control_receipts=tuple(raw["owner_probe_control_receipts"]),
            authority=_freeze(authority),
        )
        result.validate()
        return result

    @classmethod
    def from_json(cls, path: Path) -> "ArtifactAttackResult":
        return cls.from_dict(_load_json(path))

    def validate(self) -> None:
        if self.schema_version != ARTIFACT_ATTACK_SCHEMA:
            raise ContractError("schema_version must be mastermind.temporal_artifact_attack.v1")
        for name in ("operation_key", "trial_family"):
            _require_nonempty(getattr(self, name), name)
        _require_hex(self.frozen_grid_hash, 64, "frozen_grid_hash")
        if not all(isinstance(item, str) and item for item in self.recipes):
            raise ContractError("recipes must contain recipe ids")
        if not all(isinstance(item, ArtifactTest) for item in self.tests):
            raise ContractError("tests must contain ArtifactTest records")
        if self.parity.get("status") not in {"PASS", "FAIL", "UNRESOLVED_DATA"}:
            raise ContractError("parity.status is unknown")
        if self.mechanical_status not in {"ARTIFACT", "UNRESOLVED_DATA", "MECHANICALLY_SURVIVES"}:
            raise ContractError("mechanical_status is invalid for W1A")
        if self.final_mechanism_classification is not None:
            raise ContractError("final_mechanism_classification must be null in W1A")
        if not all(isinstance(item, str) and item for item in self.mechanical_receipts):
            raise ContractError("mechanical_receipts must contain receipt ids")
        _validate_indicator_channel(self.observed_indicator_reproduction, "observed_indicator_reproduction")
        _validate_indicator_channel(self.owner_probe_control, "owner_probe_control")
        for name in ("observed_indicator_reproduction_receipts", "owner_probe_control_receipts"):
            if not all(isinstance(item, str) and item for item in getattr(self, name)):
                raise ContractError(f"{name} must contain receipt ids")
        _validate_authority(self.authority)
        required_tests = tuple(test for test in self.tests if test.axis in _REQUIRED_ARTIFACT_AXES)
        unresolved = (
            self.parity["status"] == "UNRESOLVED_DATA"
            or self.observed_indicator_reproduction["status"] == "UNRESOLVED_DATA"
            or self.owner_probe_control["status"] == "UNRESOLVED_DATA"
            or any(test.status == "UNAVAILABLE" for test in required_tests)
        )
        artifact = (
            self.parity["status"] == "FAIL"
            or self.observed_indicator_reproduction["status"] == "FAIL"
            or self.owner_probe_control["status"] == "FAIL"
            or any(test.status == "FAIL" for test in required_tests)
            or any("single_arbitrary_phase_only" in test.findings for test in self.tests)
        )
        expected_status = "UNRESOLVED_DATA" if unresolved else "ARTIFACT" if artifact else "MECHANICALLY_SURVIVES"
        if self.mechanical_status != expected_status:
            raise ContractError(f"mechanical_status must be {expected_status} under carrier priority")
        if self.mechanical_status == "MECHANICALLY_SURVIVES":
            covered_axes = {test.axis for test in self.tests}
            if not {"G", "A", "K", "D", "PARITY", "TRUNCATION"}.issubset(covered_axes):
                raise ContractError("MECHANICALLY_SURVIVES requires six-axis coverage")
            if not self.recipes:
                raise ContractError("MECHANICALLY_SURVIVES requires nonempty recipes")
            if not self.mechanical_receipts:
                raise ContractError("MECHANICALLY_SURVIVES requires nonempty mechanical_receipts")
            if self.observed_indicator_reproduction["status"] == "PASS" and not self.observed_indicator_reproduction_receipts:
                raise ContractError("MECHANICALLY_SURVIVES requires observed_indicator_reproduction_receipts")
            if self.owner_probe_control["status"] == "PASS" and not self.owner_probe_control_receipts:
                raise ContractError("MECHANICALLY_SURVIVES requires owner_probe_control_receipts")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operation_key": self.operation_key,
            "recipes": list(self.recipes),
            "frozen_grid_hash": self.frozen_grid_hash,
            "trial_family": self.trial_family,
            "tests": [test.to_dict() for test in self.tests],
            "parity": _thaw(self.parity),
            "mechanical_status": self.mechanical_status,
            "final_mechanism_classification": self.final_mechanism_classification,
            "mechanical_receipts": list(self.mechanical_receipts),
            "observed_indicator_reproduction": _thaw(self.observed_indicator_reproduction),
            "observed_indicator_reproduction_receipts": list(self.observed_indicator_reproduction_receipts),
            "owner_probe_control": _thaw(self.owner_probe_control),
            "owner_probe_control_receipts": list(self.owner_probe_control_receipts),
            "authority": _thaw(self.authority),
        }
