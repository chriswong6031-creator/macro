"""Forward-only A-share limit-alpha probability and grade ledger.

This module is the production counterpart to the frozen SOL ONSET Wave-1
research packet.  It deliberately does not import the research runner: model
parameters are loaded from the tracked receipt, validated by hash, and never
refit.  Every output remains ``context_display_only``.

The append contract is intentionally narrow:

* ``engine.ledger_lane.asia_advance_enabled()`` is the first write gate;
* the observed signal date is discovered from broad nominal-raw support;
* future sessions come only from a tracked, official SSE/SZSE calendar;
* probability identity excludes ``entry_session`` (calendar corrections are
  mutations, not new predictions);
* probability and grade rows live in immutable daily Parquet parts; and
* keep-first contradictions fail before any planned partition is installed.

The ledger is evidence, not trade authority.  It does not rank, size, gate, or
recommend positions outside the frozen diagnostic top-20 selection field.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import pairwise
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from engine import ledger_lane

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECEIPT_PATH = (
    ROOT / "research" / "cn_limit_alpha_sol" / "ONSET_W1_RECEIPT_2026-08-08.json"
)
DEFAULT_SEED_PATH = (
    ROOT / "research" / "cn_limit_alpha_sol" / "ONSET_W1_FORWARD_SEED_2026-08-08.jsonl"
)
DEFAULT_RAW_DIR = ROOT / "data" / "china_stocks_raw"
DEFAULT_ST_PATH = ROOT / "data" / "china_st" / "st_snapshot.parquet"
DEFAULT_CALENDAR_PATH = (
    ROOT / "data" / "cn_limit_alpha" / "reference" / "cn_exchange_calendar_2026.json"
)
DEFAULT_LEDGER_ROOT = ROOT / "data" / "cn_limit_alpha" / "forward"

AUTHORITY = "context_display_only"
PROBABILITY_SCHEMA_VERSION = "cn_limit_alpha_probability.v2"
GRADE_SCHEMA_VERSION = "cn_limit_alpha_grade.v2"
CALENDAR_SCHEMA_VERSION = "cn_exchange_calendar.v1"
LIMIT_DEFINITION = "tolerant_0.2pct_primary"
ENTRY_RULE = "opening_auction_order_queue_cushion_0.2pct"
TOLERANT_CUSHION = 0.002
HORIZONS = (1, 3, 5)
COST_BPS = (0, 30, 60, 100)
MAX_LOWER_LIMIT_CARRY = 20
FEATURE_NAMES = (
    "vol_z20",
    "runup_5",
    "gap_pct",
    "dist_52w_low",
    "consec_up_days",
    "drawdown_20",
    "ma200_dist",
    "reversal_3",
    "washout_x_runup",
    "below_ma200_x_vol",
    "reversal_x_vol",
)

PROBABILITY_KEY = (
    "signal_date",
    "ticker",
    "model_version",
    "limit_definition",
    "entry_rule",
)
GRADE_KEY = PROBABILITY_KEY + ("grade_kind", "horizon")

PROBABILITY_REQUIRED = frozenset(
    {
        *PROBABILITY_KEY,
        "decision_available_at",
        "entry_session",
        "probability",
        "era",
        "board",
        "universe_id",
        "universe_size",
        "config_hash",
        "source_hash",
        "definition_hash",
        "model_hash",
        "fillable_state",
        "selection_state",
        "selection_rank",
        "outcome_state",
        "authority",
    }
)

GRADE_COMMON_REQUIRED = frozenset(
    {
        *GRADE_KEY,
        "entry_session",
        "graded_at",
        "authority",
        "event_outcome",
        "entry_fill_state",
        "fill_decided_at",
        "source_hash",
    }
)

PROBABILITY_SCHEMA = pa.schema(
    [
        pa.field("ledger_schema_version", pa.string(), nullable=False),
        pa.field("artifact_kind", pa.string()),
        pa.field("authority", pa.string(), nullable=False),
        pa.field("signal_date", pa.string(), nullable=False),
        pa.field("decision_available_at", pa.string(), nullable=False),
        pa.field("entry_session", pa.string(), nullable=False),
        pa.field("entry_rule", pa.string(), nullable=False),
        pa.field("ticker", pa.string(), nullable=False),
        pa.field("board", pa.string(), nullable=False),
        pa.field("era", pa.string(), nullable=False),
        pa.field("probability", pa.float64(), nullable=False),
        pa.field("model_version", pa.string(), nullable=False),
        pa.field("limit_definition", pa.string(), nullable=False),
        pa.field("universe_id", pa.string(), nullable=False),
        pa.field("universe_size", pa.int64(), nullable=False),
        pa.field("config_hash", pa.string(), nullable=False),
        pa.field("source_hash", pa.string(), nullable=False),
        pa.field("definition_hash", pa.string(), nullable=False),
        pa.field("model_hash", pa.string(), nullable=False),
        pa.field("fillable_state", pa.string(), nullable=False),
        pa.field("selection_rank", pa.int64(), nullable=False),
        pa.field("selection_state", pa.string(), nullable=False),
        pa.field("outcome_state", pa.string(), nullable=False),
        pa.field("entry_calendar_source", pa.string()),
        pa.field("packet_receipt_date", pa.string()),
    ]
)

_NET_RETURN_STRUCT = pa.struct([pa.field(str(cost), pa.float64()) for cost in COST_BPS])
GRADE_SCHEMA = pa.schema(
    [
        pa.field("ledger_schema_version", pa.string(), nullable=False),
        pa.field("authority", pa.string(), nullable=False),
        pa.field("source_hash", pa.string(), nullable=False),
        pa.field("signal_date", pa.string(), nullable=False),
        pa.field("ticker", pa.string(), nullable=False),
        pa.field("model_version", pa.string(), nullable=False),
        pa.field("limit_definition", pa.string(), nullable=False),
        pa.field("entry_rule", pa.string(), nullable=False),
        pa.field("grade_kind", pa.string(), nullable=False),
        pa.field("horizon", pa.string(), nullable=False),
        pa.field("entry_session", pa.string(), nullable=False),
        pa.field("graded_at", pa.string(), nullable=False),
        pa.field("grade_observed_session", pa.string(), nullable=False),
        pa.field("fill_decided_at", pa.string(), nullable=False),
        pa.field("entry_fill_state", pa.string(), nullable=False),
        pa.field("event_outcome", pa.bool_(), nullable=False),
        pa.field("event_state", pa.string()),
        pa.field("exit_state", pa.string()),
        pa.field("scheduled_exit_session", pa.string()),
        pa.field("realized_exit_session", pa.string()),
        pa.field("gross_return", pa.float64()),
        pa.field("net_return_bps_grid", _NET_RETURN_STRUCT),
        pa.field("book_contribution_return", pa.float64()),
    ]
)


class IntegrityError(RuntimeError):
    """A ledger authority, clock, identity, or immutability rule was violated."""


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_hash(value: object) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _row_key(row: Mapping[str, object], fields: Sequence[str]) -> tuple[object, ...]:
    missing = [field for field in fields if field not in row]
    if missing:
        raise IntegrityError(f"ledger key fields missing: {missing}")
    return tuple(row[field] for field in fields)


def canonical_ticker(ticker: str) -> str:
    """Canonicalize mainland exchange aliases, including ``.SH`` to ``.SS``."""
    value = str(ticker).strip().upper()
    if value.endswith(".SH"):
        value = value[:-3] + ".SS"
    return value


def board_from_ticker(ticker: str) -> str:
    code = canonical_ticker(ticker).split(".", 1)[0]
    if code.startswith(("688", "689")):
        return "star"
    if code.startswith(("300", "301", "302")):
        return "chinext"
    if code.startswith(("8", "4", "92")):
        return "bse"
    return "main"


def era_for(board: str, day: date) -> str:
    if board == "chinext":
        return "chinext_20" if day >= date(2020, 8, 24) else "chinext_10"
    if board == "star":
        return "star_20"
    if board == "main":
        return "main_10"
    raise IntegrityError(f"unsupported board in onset ledger: {board}")


def width_for(board: str, day: date) -> float:
    if board == "star":
        return 0.20
    if board == "chinext":
        return 0.20 if day >= date(2020, 8, 24) else 0.10
    if board == "main":
        return 0.10
    raise IntegrityError(f"unsupported board in onset ledger: {board}")


@dataclass(frozen=True)
class ExchangeCalendar:
    year: int
    sessions: tuple[date, ...]
    source_urls: tuple[str, ...]
    artifact_hash: str

    def _assert_year(self, day: date) -> None:
        if day.year != self.year:
            raise IntegrityError(
                f"official exchange calendar is attested only for {self.year}; got {day}"
            )

    def is_session(self, day: date) -> bool:
        self._assert_year(day)
        return day in self.sessions

    def position(self, day: date) -> int:
        self._assert_year(day)
        try:
            return self.sessions.index(day)
        except ValueError as exc:
            raise IntegrityError(
                f"date is not an attested SSE/SZSE session: {day}"
            ) from exc

    def next_session(self, day: date) -> date:
        pos = self.position(day)
        if pos + 1 >= len(self.sessions):
            raise IntegrityError(
                f"next session after {day} falls outside attested calendar year {self.year}"
            )
        return self.sessions[pos + 1]

    def offset(self, day: date, sessions: int) -> date:
        if sessions < 0:
            raise IntegrityError("calendar offset must be nonnegative")
        pos = self.position(day)
        target = pos + sessions
        if target >= len(self.sessions):
            raise IntegrityError(
                f"session offset {sessions} from {day} exceeds attested year {self.year}"
            )
        return self.sessions[target]


def load_exchange_calendar(path: Path = DEFAULT_CALENDAR_PATH) -> ExchangeCalendar:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IntegrityError(
            f"cannot load official exchange calendar {path}: {exc}"
        ) from exc
    if payload.get("schema_version") != CALENDAR_SCHEMA_VERSION:
        raise IntegrityError("unexpected CN exchange-calendar schema")
    year = payload.get("year")
    if not isinstance(year, int) or isinstance(year, bool):
        raise IntegrityError("exchange calendar year must be an integer")
    if set(payload.get("markets", [])) != {"SSE", "SZSE"}:
        raise IntegrityError("exchange calendar must attest both SSE and SZSE")
    if payload.get("weekends_closed") is not True:
        raise IntegrityError("exchange calendar must explicitly attest weekend closure")
    sources = tuple(payload.get("source_urls", []))
    if not any("sse.com.cn" in source for source in sources) or not any(
        "szse.cn" in source for source in sources
    ):
        raise IntegrityError("calendar lacks primary SSE and SZSE source URLs")

    closed: set[date] = set()
    for raw in payload.get("closed_ranges", []):
        if not isinstance(raw, list) or len(raw) < 2:
            raise IntegrityError(f"invalid closed range: {raw!r}")
        try:
            start, end = date.fromisoformat(raw[0]), date.fromisoformat(raw[1])
        except (TypeError, ValueError) as exc:
            raise IntegrityError(f"invalid calendar date range: {raw!r}") from exc
        if start.year != year or end.year != year or end < start:
            raise IntegrityError(f"calendar range escapes attested year: {raw!r}")
        cursor = start
        while cursor <= end:
            closed.add(cursor)
            cursor += timedelta(days=1)

    sessions: list[date] = []
    cursor = date(year, 1, 1)
    final = date(year, 12, 31)
    while cursor <= final:
        if cursor.weekday() < 5 and cursor not in closed:
            sessions.append(cursor)
        cursor += timedelta(days=1)
    if not sessions or any(a >= b for a, b in pairwise(sessions)):
        raise IntegrityError(
            "official exchange calendar produced no monotonic sessions"
        )
    return ExchangeCalendar(
        year=year,
        sessions=tuple(sessions),
        source_urls=sources,
        artifact_hash=canonical_hash(payload),
    )


@dataclass(frozen=True)
class FrozenPacket:
    receipt_path: Path
    receipt_date: str
    config: Mapping[str, object]
    config_hash: str
    models: Mapping[str, Mapping[str, object]]
    model_versions: Mapping[str, str]
    receipt_hash: str


def load_frozen_packet(path: Path = DEFAULT_RECEIPT_PATH) -> FrozenPacket:
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IntegrityError(f"cannot load frozen ONSET receipt {path}: {exc}") from exc
    if receipt.get("authority") not in {
        AUTHORITY,
        "context_display_only_no_rank_size_gate_trade_recommendation",
    }:
        raise IntegrityError("ONSET receipt has non-display authority")
    config = receipt.get("config")
    if not isinstance(config, dict) or config.get("authority") != AUTHORITY:
        raise IntegrityError("ONSET config is missing context-display-only authority")
    config_hash = receipt.get("config_hash")
    if canonical_hash(config) != config_hash:
        raise IntegrityError("ONSET frozen config hash does not recompute")
    models = receipt.get("models")
    if not isinstance(models, dict) or set(models) != {
        "O1_five_axis",
        "O1_fixed_equal_rank_blend",
        "O3_washout_transition",
    }:
        raise IntegrityError("ONSET receipt does not contain the expected three models")
    for name, raw_model in models.items():
        if not isinstance(raw_model, dict) or raw_model.get("name") != name:
            raise IntegrityError(f"malformed frozen model receipt: {name}")
        body = dict(raw_model)
        declared = body.pop("model_hash", None)
        if canonical_hash(body) != declared:
            raise IntegrityError(f"frozen model hash does not recompute: {name}")

    contract = receipt.get("forward_ledger_contract")
    expected_versions = (
        contract.get("expected_model_versions") if isinstance(contract, dict) else None
    )
    if not isinstance(expected_versions, list) or len(expected_versions) != len(models):
        raise IntegrityError("receipt lacks three declared forward model versions")
    model_versions: dict[str, str] = {}
    for version in expected_versions:
        if not isinstance(version, str) or ":" not in version:
            raise IntegrityError(f"invalid declared model version: {version!r}")
        model_name = version.rsplit(":", 1)[-1]
        if model_name not in models or model_name in model_versions:
            raise IntegrityError(f"model-version mapping is not one-to-one: {version}")
        model_versions[model_name] = version
    if set(model_versions) != set(models):
        raise IntegrityError("declared forward versions do not cover frozen models")

    receipt_body = dict(receipt)
    receipt_hash = receipt_body.pop("receipt_hash", None)
    if canonical_hash(receipt_body) != receipt_hash:
        raise IntegrityError("ONSET receipt hash does not recompute")
    return FrozenPacket(
        receipt_path=path,
        receipt_date=str(receipt.get("receipt_date")),
        config=config,
        config_hash=config_hash,
        models=models,
        model_versions=model_versions,
        receipt_hash=receipt_hash,
    )


def definition_hash(packet: FrozenPacket) -> str:
    return canonical_hash(
        {
            "limit_definition": LIMIT_DEFINITION,
            "entry_clock": packet.config["entry_clock"],
            "outcome_clock": packet.config["outcome_clock"],
            "queue_rule": packet.config["queue_rule"],
            "exit_rule": packet.config["exit_rule"],
        }
    )


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-35.0, min(35.0, value))))


def score_frozen_model(
    packet: FrozenPacket, model_name: str, features: Mapping[str, float]
) -> float:
    """Score one row using only receipt-declared parameters."""
    model = packet.models.get(model_name)
    if model is None:
        raise IntegrityError(f"unknown frozen model: {model_name}")
    if model_name == "O1_fixed_equal_rank_blend":
        ranks: list[float] = []
        knots = model.get("knots")
        if not isinstance(knots, dict):
            raise IntegrityError("equal-rank model lacks frozen knots")
        for feature in model["features"]:
            values = np.asarray(knots[feature], dtype=np.float64)
            if len(values) == 0 or np.any(np.diff(values) < 0):
                raise IntegrityError(f"invalid equal-rank knots for {feature}")
            ranks.append(
                float(np.searchsorted(values, features[feature], side="right"))
                / len(values)
            )
        raw = min(1.0 - 1e-6, max(1e-6, float(np.mean(ranks))))
        raw_logit = math.log(raw / (1.0 - raw))
        intercept, slope = map(float, model["calibration"])
        return _sigmoid(intercept + slope * raw_logit)

    columns = list(model["columns"])
    scaler = model["scaler"]
    mean = np.asarray(scaler["mean"], dtype=np.float64)
    std = np.asarray(scaler["std"], dtype=np.float64)
    beta = np.asarray(model["beta"], dtype=np.float64)
    values = np.asarray([features[name] for name in columns], dtype=np.float64)
    if len(values) != len(mean) or len(values) + 1 != len(beta) or np.any(std <= 0):
        raise IntegrityError(f"malformed frozen logistic dimensions: {model_name}")
    raw_logit = float(beta[0] + ((values - mean) / std) @ beta[1:])
    intercept, slope = map(float, model["platt_intercept_slope"])
    return _sigmoid(intercept + slope * raw_logit)


def clean_raw_frame(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"open", "close", "high", "low", "volume"}
    if frame.empty or not required.issubset(frame.columns):
        raise IntegrityError(
            f"nominal raw frame lacks OHLCV columns: {sorted(frame.columns)}"
        )
    out = frame.loc[:, sorted(required)].copy()
    out.index = pd.to_datetime(out.index, errors="coerce")
    out = out[~out.index.isna()].sort_index()
    out = out[~out.index.duplicated(keep="last")]
    if out.empty:
        raise IntegrityError("nominal raw frame has no valid dates")
    return out


def load_raw_frames(raw_dir: Path = DEFAULT_RAW_DIR) -> dict[str, pd.DataFrame]:
    """Load the nominal raw store once, rejecting exchange-alias collisions."""
    paths = sorted(raw_dir.glob("*.parquet"))
    if not paths:
        raise IntegrityError(f"nominal A-share raw store is empty: {raw_dir}")
    frames: dict[str, pd.DataFrame] = {}
    for path in paths:
        ticker = canonical_ticker(path.stem)
        if ticker in frames:
            raise IntegrityError(
                f"duplicate canonical raw ticker (.SH/.SS collision): {ticker}"
            )
        try:
            frames[ticker] = clean_raw_frame(pd.read_parquet(path))
        except IntegrityError:
            raise
        except Exception as exc:
            raise IntegrityError(f"cannot read nominal raw file {path}: {exc}") from exc
    return frames


@dataclass(frozen=True)
class ObservedSession:
    day: date
    support_names: int
    peak_recent_support: int
    minimum_required_support: int
    reference_ticker: str


def discover_latest_complete_session(
    frames: Mapping[str, pd.DataFrame],
    calendar: ExchangeCalendar,
    *,
    reference_ticker: str = "600519.SS",
    recent_rows: int = 20,
    minimum_names: int = 50,
    support_ratio: float = 0.98,
) -> ObservedSession:
    """Find the newest broad, reference-attested nominal session.

    A partially collected tail must not become the signal clock.  The latest
    date must exist in the high-support reference and reach both an absolute
    name floor and ``support_ratio`` of the best recent cross-sectional support.
    Volume is deliberately not part of this market-clock test: a zero-volume
    placeholder is still evidence that the date exists, while eligibility and
    grading separately classify it as missing/halted.
    """
    if not 0.0 < support_ratio <= 1.0:
        raise IntegrityError("support_ratio must lie in (0, 1]")
    reference = frames.get(canonical_ticker(reference_ticker))
    if reference is None:
        raise IntegrityError(f"latest-session reference is absent: {reference_ticker}")
    reference_days = {
        stamp.date()
        for stamp in reference.index[-recent_rows:]
        if stamp.year == calendar.year
    }
    if not reference_days:
        raise IntegrityError("latest-session reference has no dates in attested year")

    support: dict[date, int] = {}
    for frame in frames.values():
        for stamp in frame.index[-recent_rows:]:
            day = stamp.date()
            if day.year != calendar.year or day not in reference_days:
                continue
            if day.weekday() >= 5:
                raise IntegrityError(
                    f"nominal raw store contains weekend support: {day}"
                )
            support[day] = support.get(day, 0) + 1
    official_support = {
        day: count for day, count in support.items() if calendar.is_session(day)
    }
    if not official_support:
        raise IntegrityError(
            "no official session has nominal high-support observations"
        )
    peak = max(official_support.values())
    required = max(int(minimum_names), math.ceil(peak * support_ratio))
    eligible = [day for day, count in official_support.items() if count >= required]
    if not eligible:
        raise IntegrityError(
            f"no broad nominal session reaches support floor {required}; peak={peak}"
        )
    latest = max(eligible)
    return ObservedSession(
        day=latest,
        support_names=official_support[latest],
        peak_recent_support=peak,
        minimum_required_support=required,
        reference_ticker=canonical_ticker(reference_ticker),
    )


@dataclass(frozen=True)
class STExclusions:
    tickers: frozenset[str]
    asof: date
    artifact_hash: str


def load_st_exclusions(path: Path = DEFAULT_ST_PATH) -> STExclusions:
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:
        raise IntegrityError(
            f"cannot read current ST exclusion snapshot {path}: {exc}"
        ) from exc
    if not {"ticker", "asof"}.issubset(frame.columns):
        raise IntegrityError(
            "current ST exclusion snapshot lacks ticker/asof attestation"
        )
    tickers = {
        canonical_ticker(value) for value in frame["ticker"].dropna().astype(str)
    }
    raw_asofs = {str(value)[:10] for value in frame["asof"].dropna()}
    if len(raw_asofs) != 1:
        raise IntegrityError(
            f"ST exclusion snapshot has ambiguous asof values: {sorted(raw_asofs)}"
        )
    try:
        asof = date.fromisoformat(next(iter(raw_asofs)))
    except (StopIteration, ValueError) as exc:
        raise IntegrityError("ST exclusion snapshot has no valid asof date") from exc
    return STExclusions(
        tickers=frozenset(tickers),
        asof=asof,
        artifact_hash=file_hash(path),
    )


def require_st_exclusions_for_signal(snapshot: STExclusions, signal_day: date) -> None:
    if snapshot.asof != signal_day:
        raise IntegrityError(
            "ST/risk-warning membership is not point-in-time attested for the signal session: "
            f"snapshot={snapshot.asof} signal={signal_day}"
        )


def _consecutive_up(close: np.ndarray) -> np.ndarray:
    out = np.zeros(len(close), dtype=np.float64)
    streak = 0
    for index in range(1, len(close)):
        if (
            np.isfinite(close[index])
            and np.isfinite(close[index - 1])
            and close[index] > close[index - 1]
        ):
            streak += 1
        else:
            streak = 0
        out[index] = streak
    return out


def compute_feature_frame(
    frame: pd.DataFrame, clip_bounds: Mapping[str, Sequence[float]]
) -> pd.DataFrame:
    """Reproduce the eleven frozen ONSET features without importing research code."""
    raw_volume = pd.to_numeric(frame["volume"], errors="coerce").astype(float)
    observed = raw_volume > 0
    close = pd.to_numeric(frame["close"], errors="coerce").astype(float).where(observed)
    open_ = pd.to_numeric(frame["open"], errors="coerce").astype(float).where(observed)
    volume = raw_volume.where(observed)

    prior_volume = volume.shift(1)
    volume_mean = prior_volume.rolling(20, min_periods=15).mean()
    volume_std = prior_volume.rolling(20, min_periods=15).std(ddof=0)
    vol_z20 = (volume - volume_mean) / volume_std.replace(0.0, np.nan)
    runup_5 = close / close.shift(5) - 1.0
    gap_pct = open_ / close.shift(1) - 1.0
    dist_52w_low = close / close.rolling(252, min_periods=120).min() - 1.0
    consec_up_days = _consecutive_up(close.to_numpy(dtype=float))
    drawdown_20 = close / close.rolling(20, min_periods=15).max() - 1.0
    ma200_dist = close / close.rolling(200, min_periods=120).mean() - 1.0
    reversal_3 = close / close.rolling(3, min_periods=3).min() - 1.0
    washout_x_runup = (-drawdown_20.clip(upper=0.0)) * runup_5
    below_ma200_x_vol = (-ma200_dist.clip(upper=0.0)) * vol_z20
    reversal_x_vol = reversal_3 * vol_z20

    output = pd.DataFrame(
        {
            "vol_z20": vol_z20,
            "runup_5": runup_5,
            "gap_pct": gap_pct,
            "dist_52w_low": dist_52w_low,
            "consec_up_days": consec_up_days,
            "drawdown_20": drawdown_20,
            "ma200_dist": ma200_dist,
            "reversal_3": reversal_3,
            "washout_x_runup": washout_x_runup,
            "below_ma200_x_vol": below_ma200_x_vol,
            "reversal_x_vol": reversal_x_vol,
        },
        index=frame.index,
    )
    if set(clip_bounds) != set(FEATURE_NAMES):
        raise IntegrityError(
            "frozen receipt clip bounds do not cover exact feature set"
        )
    for feature in FEATURE_NAMES:
        raw = clip_bounds[feature]
        if not isinstance(raw, (list, tuple)) or len(raw) != 2:
            raise IntegrityError(f"invalid frozen clip bound for {feature}")
        output[feature] = output[feature].clip(float(raw[0]), float(raw[1]))
    return output


@dataclass(frozen=True)
class DailyState:
    observation: str
    event_outcome: bool
    entry_fill_state: str
    open_price: float | None
    upper_limit: float | None
    lower_limit: float | None
    source_hash: str


def _frame_position(frame: pd.DataFrame, day: date) -> int | None:
    wanted = pd.Timestamp(day)
    position = int(frame.index.searchsorted(wanted))
    if position >= len(frame) or frame.index[position].date() != day:
        return None
    return position


def _source_scalar(value: object) -> object:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (int, float, np.integer, np.floating)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else str(numeric)
    return str(value)


def _daily_source_hash(
    frame: pd.DataFrame | None, ticker: str, day: date, position: int | None
) -> str:
    payload: dict[str, object] = {
        "ticker": canonical_ticker(ticker),
        "session": day.isoformat(),
    }
    if frame is None:
        payload["observation"] = "ticker_frame_absent"
    elif position is None:
        payload["observation"] = "exact_session_absent"
    else:
        payload["observation"] = "exact_session_row"
        rows: list[dict[str, object]] = []
        for role, raw_position in (
            ("previous_raw_row", position - 1),
            ("session_row", position),
        ):
            if raw_position < 0:
                rows.append({"role": role, "state": "absent"})
                continue
            raw = frame.iloc[raw_position]
            rows.append(
                {
                    "role": role,
                    "date": frame.index[raw_position].date().isoformat(),
                    **{
                        field: _source_scalar(raw.get(field))
                        for field in ("open", "close", "high", "low", "volume")
                    },
                }
            )
        payload["rows"] = rows
    return canonical_hash(payload)


def daily_state(frame: pd.DataFrame | None, ticker: str, day: date) -> DailyState:
    """Classify one exact ticker-session without hopping to a later print."""
    if frame is None:
        source_hash = _daily_source_hash(frame, ticker, day, None)
        return DailyState(
            "missing_halted",
            False,
            "missing_halted_no_fill",
            None,
            None,
            None,
            source_hash,
        )
    position = _frame_position(frame, day)
    source_hash = _daily_source_hash(frame, ticker, day, position)
    if position is None or position == 0:
        return DailyState(
            "missing_halted",
            False,
            "missing_halted_no_fill",
            None,
            None,
            None,
            source_hash,
        )
    row = frame.iloc[position]
    previous = frame.iloc[position - 1]
    try:
        open_price = float(row["open"])
        close_price = float(row["close"])
        volume = float(row["volume"])
        previous_close = float(previous["close"])
    except (TypeError, ValueError):
        return DailyState(
            "missing_halted",
            False,
            "missing_halted_no_fill",
            None,
            None,
            None,
            source_hash,
        )
    if not all(map(math.isfinite, (open_price, close_price, volume, previous_close))):
        return DailyState(
            "missing_halted",
            False,
            "missing_halted_no_fill",
            None,
            None,
            None,
            source_hash,
        )
    if open_price <= 0 or close_price <= 0 or previous_close <= 0 or volume <= 0:
        return DailyState(
            "missing_halted",
            False,
            "missing_halted_no_fill",
            None,
            None,
            None,
            source_hash,
        )
    board = board_from_ticker(ticker)
    if board == "bse":
        raise IntegrityError("BSE ticker entered the SSE/SZSE onset ledger")
    width = width_for(board, day)
    upper = round(previous_close * (1.0 + width) + 1e-12, 2)
    lower = round(previous_close * (1.0 - width) + 1e-12, 2)
    corporate_action = abs(open_price - previous_close) / previous_close > width * 1.5
    if corporate_action:
        return DailyState(
            "invalid_corporate_action",
            False,
            "missing_halted_no_fill",
            None,
            upper,
            lower,
            source_hash,
        )
    event = close_price >= upper * (1.0 - TOLERANT_CUSHION)
    fill_state = (
        "queue_required_no_fill"
        if open_price >= upper * (1.0 - TOLERANT_CUSHION)
        else "fillable_daily_proxy"
    )
    return DailyState(
        "observed", event, fill_state, open_price, upper, lower, source_hash
    )


def _ipo_no_limit_session(frame: pd.DataFrame, ticker: str, position: int) -> bool:
    volume = pd.to_numeric(frame["volume"], errors="coerce").to_numpy(dtype=float)
    positive_positions = np.flatnonzero(np.isfinite(volume) & (volume > 0))
    matches = np.flatnonzero(positive_positions == position)
    if len(matches) != 1:
        return True
    ordinal = int(matches[0])
    first_day = frame.index[int(positive_positions[0])].date()
    board = board_from_ticker(ticker)
    if (
        board == "star"
        or board == "chinext"
        and first_day >= date(2020, 8, 24)
        or board == "main"
        and first_day >= date(2023, 4, 10)
    ):
        no_limit_sessions = 5
    else:
        no_limit_sessions = 1
    return ordinal < no_limit_sessions


@dataclass(frozen=True)
class EligibleSignal:
    ticker: str
    board: str
    era: str
    features: Mapping[str, float]
    source_row: Mapping[str, object]


def build_latest_eligible_population(
    frames: Mapping[str, pd.DataFrame],
    signal_day: date,
    packet: FrozenPacket,
    st_exclusions: set[str],
) -> list[EligibleSignal]:
    population: list[EligibleSignal] = []
    clip_bounds = packet.config.get("clip_bounds")
    if not isinstance(clip_bounds, dict):
        raise IntegrityError("frozen receipt lacks feature clip bounds")
    for ticker in sorted(frames):
        canonical = canonical_ticker(ticker)
        board = board_from_ticker(canonical)
        if board == "bse" or canonical in st_exclusions:
            continue
        frame = frames[ticker]
        position = _frame_position(frame, signal_day)
        if position is None or _ipo_no_limit_session(frame, canonical, position):
            continue
        state = daily_state(frame, canonical, signal_day)
        if state.observation != "observed" or state.event_outcome:
            continue
        feature_frame = compute_feature_frame(frame, clip_bounds)
        values = feature_frame.iloc[position]
        if not all(math.isfinite(float(values[name])) for name in FEATURE_NAMES):
            continue
        features = {name: float(values[name]) for name in FEATURE_NAMES}
        row = frame.iloc[position]
        source_row = {
            "ticker": canonical,
            "signal_date": signal_day.isoformat(),
            "open": float(row["open"]),
            "close": float(row["close"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "volume": float(row["volume"]),
            "features": features,
        }
        population.append(
            EligibleSignal(
                ticker=canonical,
                board=board,
                era=era_for(board, signal_day),
                features=features,
                source_row=source_row,
            )
        )
    if not population:
        raise IntegrityError(f"no eligible onset population at {signal_day}")
    tickers = [row.ticker for row in population]
    if len(tickers) != len(set(tickers)):
        raise IntegrityError(
            "eligible onset population contains duplicate canonical tickers"
        )
    return population


def build_probability_snapshot(
    population: Sequence[EligibleSignal],
    signal_day: date,
    entry_day: date,
    packet: FrozenPacket,
    calendar: ExchangeCalendar,
    *,
    st_snapshot_hash: str,
) -> list[dict[str, object]]:
    tickers = sorted(row.ticker for row in population)
    universe_id = canonical_hash(
        {"signal_date": signal_day.isoformat(), "tickers": tickers}
    )
    source_hash = canonical_hash(
        {
            "signal_date": signal_day.isoformat(),
            "rows": [
                row.source_row
                for row in sorted(population, key=lambda item: item.ticker)
            ],
            "st_snapshot_hash": st_snapshot_hash,
        }
    )
    frozen_definition_hash = definition_hash(packet)
    output: list[dict[str, object]] = []
    for model_name in sorted(packet.models):
        scored = [
            (row, score_frozen_model(packet, model_name, row.features))
            for row in population
        ]
        ranks: dict[str, int] = {}
        for era in sorted({row.era for row, _ in scored}):
            group = [
                (row, probability) for row, probability in scored if row.era == era
            ]
            group.sort(key=lambda item: (-item[1], item[0].ticker))
            for rank, (row, _) in enumerate(group, 1):
                ranks[row.ticker] = rank
        model = packet.models[model_name]
        for row, probability in sorted(scored, key=lambda item: item[0].ticker):
            rank = ranks[row.ticker]
            output.append(
                {
                    "ledger_schema_version": PROBABILITY_SCHEMA_VERSION,
                    "artifact_kind": "live_forward_probability_snapshot",
                    "authority": AUTHORITY,
                    "signal_date": signal_day.isoformat(),
                    "decision_available_at": f"{signal_day.isoformat()}T15:00:00+08:00",
                    "entry_session": entry_day.isoformat(),
                    "entry_rule": ENTRY_RULE,
                    "ticker": row.ticker,
                    "board": row.board,
                    "era": row.era,
                    "probability": probability,
                    "model_version": packet.model_versions[model_name],
                    "limit_definition": LIMIT_DEFINITION,
                    "universe_id": universe_id,
                    "universe_size": len(population),
                    "config_hash": packet.config_hash,
                    "source_hash": source_hash,
                    "definition_hash": frozen_definition_hash,
                    "model_hash": model["model_hash"],
                    "fillable_state": "unknown_pending",
                    "selection_rank": rank,
                    "selection_state": (
                        "selected_top20" if rank <= 20 else "not_selected_no_fire"
                    ),
                    "outcome_state": "pending",
                    "entry_calendar_source": (
                        f"data/cn_limit_alpha/reference/cn_exchange_calendar_2026.json"
                        f"#{calendar.artifact_hash}"
                    ),
                    "packet_receipt_date": packet.receipt_date,
                }
            )
    return output


def _normalize_probability(row: Mapping[str, object]) -> dict[str, object]:
    normalized = dict(row)
    normalized["ledger_schema_version"] = PROBABILITY_SCHEMA_VERSION
    normalized["ticker"] = canonical_ticker(str(normalized.get("ticker", "")))
    for field in PROBABILITY_SCHEMA.names:
        normalized.setdefault(field, None)
    unknown = set(normalized) - set(PROBABILITY_SCHEMA.names)
    if unknown:
        raise IntegrityError(
            f"unknown probability fields cannot enter v2 Parquet: {sorted(unknown)}"
        )
    return {field: normalized[field] for field in PROBABILITY_SCHEMA.names}


def _normalize_grade(row: Mapping[str, object]) -> dict[str, object]:
    normalized = dict(row)
    normalized["ledger_schema_version"] = GRADE_SCHEMA_VERSION
    normalized["ticker"] = canonical_ticker(str(normalized.get("ticker", "")))
    for field in GRADE_SCHEMA.names:
        normalized.setdefault(field, None)
    unknown = set(normalized) - set(GRADE_SCHEMA.names)
    if unknown:
        raise IntegrityError(
            f"unknown grade fields cannot enter v2 Parquet: {sorted(unknown)}"
        )
    grid = normalized.get("net_return_bps_grid")
    if grid is not None:
        if not isinstance(grid, dict) or set(grid) != {str(cost) for cost in COST_BPS}:
            raise IntegrityError("net-return grid does not cover the frozen cost ruler")
        normalized["net_return_bps_grid"] = {
            str(cost): grid[str(cost)] for cost in COST_BPS
        }
    return {field: normalized[field] for field in GRADE_SCHEMA.names}


def load_seed_jsonl(path: Path = DEFAULT_SEED_PATH) -> list[dict[str, object]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise IntegrityError(f"cannot read honest ONSET seed {path}: {exc}") from exc
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise IntegrityError(
                f"invalid seed JSONL {path}:{line_number}: {exc}"
            ) from exc
        if not isinstance(raw, dict):
            raise IntegrityError(f"seed row is not an object at {path}:{line_number}")
        rows.append(_normalize_probability(raw))
    if not rows:
        raise IntegrityError("honest ONSET seed is empty")
    return rows


def _validate_probability_rows(
    rows: Sequence[Mapping[str, object]],
    packet: FrozenPacket,
    calendar: ExchangeCalendar,
    *,
    label: str,
) -> dict[tuple[object, ...], dict[str, object]]:
    expected_versions = set(packet.model_versions.values())
    by_key: dict[tuple[object, ...], dict[str, object]] = {}
    snapshots: dict[tuple[str, str, str], dict[str, list[dict[str, object]]]] = {}
    for raw in rows:
        row = _normalize_probability(raw)
        missing = sorted(
            field for field in PROBABILITY_REQUIRED if row.get(field) is None
        )
        if missing:
            raise IntegrityError(f"{label} probability row missing fields: {missing}")
        key = _row_key(row, PROBABILITY_KEY)
        if key in by_key:
            raise IntegrityError(f"duplicate probability key in {label}: {key}")
        by_key[key] = row
        if row["authority"] != AUTHORITY:
            raise IntegrityError(f"non-display probability authority in {label}")
        if row["ledger_schema_version"] != PROBABILITY_SCHEMA_VERSION:
            raise IntegrityError("unexpected probability ledger schema")
        probability = row["probability"]
        if isinstance(probability, bool) or not isinstance(probability, (int, float)):
            raise IntegrityError("probability is not numeric")
        if not math.isfinite(float(probability)) or not 0.0 < float(probability) < 1.0:
            raise IntegrityError("probability must lie strictly inside (0, 1)")
        if row["model_version"] not in expected_versions:
            raise IntegrityError(
                f"unexpected frozen model version: {row['model_version']}"
            )
        model_name = str(row["model_version"]).rsplit(":", 1)[-1]
        if row["model_hash"] != packet.models[model_name]["model_hash"]:
            raise IntegrityError(
                "probability row model hash contradicts frozen receipt"
            )
        if row["config_hash"] != packet.config_hash:
            raise IntegrityError(
                "probability row config hash contradicts frozen receipt"
            )
        if row["definition_hash"] != definition_hash(packet):
            raise IntegrityError("probability row definition hash does not recompute")
        for field in (
            "universe_id",
            "config_hash",
            "source_hash",
            "definition_hash",
            "model_hash",
        ):
            if not _is_sha256(row[field]):
                raise IntegrityError(f"probability {field} is not a SHA-256 digest")
        if (
            row["fillable_state"] != "unknown_pending"
            or row["outcome_state"] != "pending"
        ):
            raise IntegrityError("immutable probability row contains post-entry state")
        universe_size = row["universe_size"]
        rank = row["selection_rank"]
        if (
            isinstance(universe_size, bool)
            or not isinstance(universe_size, int)
            or universe_size <= 0
            or isinstance(rank, bool)
            or not isinstance(rank, int)
            or not 1 <= rank <= universe_size
        ):
            raise IntegrityError("probability rank/universe size is invalid")
        expected_selection = "selected_top20" if rank <= 20 else "not_selected_no_fire"
        if row["selection_state"] != expected_selection:
            raise IntegrityError("selection state contradicts frozen per-era rank")
        signal_day = date.fromisoformat(str(row["signal_date"]))
        entry_day = date.fromisoformat(str(row["entry_session"]))
        if calendar.next_session(signal_day) != entry_day:
            raise IntegrityError(
                "entry_session is payload (not identity) and is not the official exact successor"
            )
        snapshot_id = (
            str(row["signal_date"]),
            str(row["limit_definition"]),
            str(row["entry_rule"]),
        )
        snapshots.setdefault(snapshot_id, {}).setdefault(
            str(row["model_version"]), []
        ).append(row)

    for snapshot_id, models in snapshots.items():
        if set(models) != expected_versions:
            raise IntegrityError(
                f"{label} snapshot lacks the complete three-model set: {snapshot_id}"
            )
        reference_tickers: list[str] | None = None
        reference_entry: str | None = None
        for version in sorted(models):
            group = models[version]
            tickers = sorted(str(row["ticker"]) for row in group)
            sizes = {int(row["universe_size"]) for row in group}
            if (
                len(sizes) != 1
                or len(group) != next(iter(sizes))
                or len(tickers) != len(set(tickers))
            ):
                raise IntegrityError(
                    f"{label} snapshot is not full-population for {snapshot_id}/{version}"
                )
            expected_universe_id = canonical_hash(
                {"signal_date": snapshot_id[0], "tickers": tickers}
            )
            if {row["universe_id"] for row in group} != {expected_universe_id}:
                raise IntegrityError("probability universe_id does not recompute")
            entries = {str(row["entry_session"]) for row in group}
            if len(entries) != 1:
                raise IntegrityError("entry_session differs inside a model snapshot")
            for era in {str(row["era"]) for row in group}:
                era_ranks = sorted(
                    int(row["selection_rank"]) for row in group if row["era"] == era
                )
                if era_ranks != list(range(1, len(era_ranks) + 1)):
                    raise IntegrityError(
                        f"per-era ranks are incomplete for {version}/{era}"
                    )
            if reference_tickers is not None and tickers != reference_tickers:
                raise IntegrityError(
                    "model populations differ inside probability snapshot"
                )
            entry = next(iter(entries))
            if reference_entry is not None and entry != reference_entry:
                raise IntegrityError(
                    "model entry sessions differ inside probability snapshot"
                )
            reference_tickers = tickers
            reference_entry = entry
    return by_key


def _validate_grade_rows(
    rows: Sequence[Mapping[str, object]],
    probabilities: Mapping[tuple[object, ...], Mapping[str, object]],
    calendar: ExchangeCalendar,
    *,
    label: str,
) -> dict[tuple[object, ...], dict[str, object]]:
    by_key: dict[tuple[object, ...], dict[str, object]] = {}
    for raw in rows:
        row = _normalize_grade(raw)
        missing = sorted(
            field for field in GRADE_COMMON_REQUIRED if row.get(field) is None
        )
        if missing:
            raise IntegrityError(f"{label} grade row missing fields: {missing}")
        key = _row_key(row, GRADE_KEY)
        if key in by_key:
            raise IntegrityError(f"duplicate grade key in {label}: {key}")
        probability_key = _row_key(row, PROBABILITY_KEY)
        probability = probabilities.get(probability_key)
        if probability is None:
            raise IntegrityError(
                f"grade has no immutable probability: {probability_key}"
            )
        if (
            row["authority"] != AUTHORITY
            or row["ledger_schema_version"] != GRADE_SCHEMA_VERSION
        ):
            raise IntegrityError("grade authority/schema is invalid")
        if not _is_sha256(row["source_hash"]):
            raise IntegrityError("grade source_hash is not a SHA-256 digest")
        if row["entry_session"] != probability["entry_session"]:
            raise IntegrityError("grade entry session mutates probability payload")
        if not isinstance(row["event_outcome"], bool):
            raise IntegrityError("event outcome must be boolean")
        fill_state = row["entry_fill_state"]
        if fill_state not in {
            "fillable_daily_proxy",
            "missing_halted_no_fill",
            "queue_required_no_fill",
        }:
            raise IntegrityError(f"invalid terminal entry fill state: {fill_state}")
        signal_day = date.fromisoformat(str(row["signal_date"]))
        entry_day = date.fromisoformat(str(row["entry_session"]))
        if calendar.next_session(signal_day) != entry_day:
            raise IntegrityError("grade signal-to-entry clock is not exact T+1")
        try:
            grade_day = date.fromisoformat(str(row["grade_observed_session"]))
        except ValueError as exc:
            raise IntegrityError("grade observed session is not an ISO date") from exc
        if not calendar.is_session(grade_day) or grade_day < entry_day:
            raise IntegrityError(
                "grade observed session is not a valid processing clock"
            )
        if row["graded_at"] != f"{grade_day.isoformat()}T15:00:00+08:00":
            raise IntegrityError(
                "graded_at does not match the actual processing session"
            )
        expected_fill_clock = (
            "15:00:00" if fill_state == "missing_halted_no_fill" else "09:30:00"
        )
        if row["fill_decided_at"] != (
            f"{entry_day.isoformat()}T{expected_fill_clock}+08:00"
        ):
            raise IntegrityError("fill_decided_at does not match the exact entry clock")
        kind = row["grade_kind"]
        if kind == "event":
            if row["horizon"] != "EVENT_D" or row["event_state"] not in {
                "observed_event",
                "observed_non_event",
                "missing_halted_non_event",
            }:
                raise IntegrityError("event grade state/horizon is invalid")
            if any(
                row[field] is not None
                for field in (
                    "exit_state",
                    "scheduled_exit_session",
                    "realized_exit_session",
                    "gross_return",
                    "net_return_bps_grid",
                    "book_contribution_return",
                )
            ):
                raise IntegrityError("event grade contains execution-return fields")
        elif kind == "execution_return":
            if probability["selection_state"] != "selected_top20":
                raise IntegrityError(
                    "execution grade is permitted only for selected orders"
                )
            if row["horizon"] not in {f"H{h}_next_open" for h in HORIZONS}:
                raise IntegrityError("execution grade has invalid horizon")
            if row["event_state"] is not None or row["exit_state"] is None:
                raise IntegrityError("execution grade mixes event/exit state")
            horizon = int(str(row["horizon"])[1:].split("_", 1)[0])
            scheduled = date.fromisoformat(str(row["scheduled_exit_session"]))
            if calendar.offset(entry_day, horizon) != scheduled:
                raise IntegrityError(
                    "execution grade scheduled exit is not exact session H"
                )
            grid = row["net_return_bps_grid"]
            gross = row["gross_return"]
            book = row["book_contribution_return"]
            if fill_state != "fillable_daily_proxy":
                expected_exit = (
                    "not_entered_queue_no_fill"
                    if fill_state == "queue_required_no_fill"
                    else "not_entered_missing_halted_no_fill"
                )
                if (
                    gross is not None
                    or grid is not None
                    or row["realized_exit_session"] is not None
                    or float(book) != 0.0
                    or row["exit_state"] != expected_exit
                ):
                    raise IntegrityError(
                        "selected unfilled execution is not null-gross/cash-zero"
                    )
            elif gross is None:
                if (
                    grid is not None
                    or row["realized_exit_session"] is not None
                    or float(book) != 0.0
                ):
                    raise IntegrityError(
                        "unresolved filled exit is not null-return/cash-zero"
                    )
            else:
                if grid is None or row["realized_exit_session"] is None:
                    raise IntegrityError("resolved filled execution lacks return/exit")
                gross_value = float(gross)
                if not math.isfinite(gross_value) or not math.isclose(
                    float(book), gross_value, abs_tol=1e-12
                ):
                    raise IntegrityError(
                        "resolved book contribution must equal gross return"
                    )
                for cost in COST_BPS:
                    expected = gross_value - cost / 10_000.0
                    if not math.isclose(
                        float(grid[str(cost)]), expected, abs_tol=1e-12
                    ):
                        raise IntegrityError(
                            "net-return grid contradicts gross/cost ruler"
                        )
        else:
            raise IntegrityError(f"unknown grade kind: {kind}")
        by_key[key] = row
    return by_key


def _partition_path(root: Path, kind: str, day: date) -> Path:
    if kind not in {"probabilities", "grades"}:
        raise IntegrityError(f"invalid ledger partition kind: {kind}")
    return root / kind / day.strftime("%Y-%m") / f"{day.isoformat()}.parquet"


def read_partition(path: Path, schema: pa.Schema) -> list[dict[str, object]]:
    try:
        table = pq.read_table(path)
    except Exception as exc:
        raise IntegrityError(f"cannot read ledger partition {path}: {exc}") from exc
    if table.schema != schema:
        raise IntegrityError(f"ledger partition schema mismatch: {path}")
    return table.to_pylist()


def load_partitioned_rows(root: Path, kind: str) -> list[dict[str, object]]:
    schema = PROBABILITY_SCHEMA if kind == "probabilities" else GRADE_SCHEMA
    directory = root / kind
    if not directory.exists():
        return []
    rows: list[dict[str, object]] = []
    for path in sorted(directory.glob("????-??/????-??-??.parquet")):
        rows.extend(read_partition(path, schema))
    return rows


def _atomic_write_partition(
    path: Path, rows: Sequence[Mapping[str, object]], schema: pa.Schema
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist([dict(row) for row in rows], schema=schema)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        pq.write_table(
            table,
            temporary,
            compression="zstd",
            use_dictionary=False,
            write_statistics=True,
        )
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


@dataclass(frozen=True)
class PlannedPartition:
    path: Path
    rows: tuple[dict[str, object], ...]
    schema: pa.Schema


def _plan_partition(
    path: Path,
    rows: Sequence[Mapping[str, object]],
    schema: pa.Schema,
    key_fields: Sequence[str],
) -> PlannedPartition | None:
    ordered = tuple(
        sorted((dict(row) for row in rows), key=lambda row: _row_key(row, key_fields))
    )
    if not ordered:
        return None
    if path.exists():
        existing = sorted(
            read_partition(path, schema), key=lambda row: _row_key(row, key_fields)
        )
        if canonical_hash(existing) != canonical_hash(list(ordered)):
            raise IntegrityError(
                f"keep-first immutable partition contradiction: {path}"
            )
        return None
    return PlannedPartition(path=path, rows=ordered, schema=schema)


def _grade_observation(role: str, day: date, state: DailyState) -> dict[str, object]:
    """Bind one exact-session classification to the raw rows that produced it."""
    return {
        "role": role,
        "session": day.isoformat(),
        "daily_source_hash": state.source_hash,
        "observation": state.observation,
        "event_outcome": state.event_outcome,
        "entry_fill_state": state.entry_fill_state,
        "open_price": _source_scalar(state.open_price),
        "upper_limit": _source_scalar(state.upper_limit),
        "lower_limit": _source_scalar(state.lower_limit),
    }


def _grade_source_hash(
    probability: Mapping[str, object],
    calendar: ExchangeCalendar,
    *,
    grade_kind: str,
    horizon: str,
    scheduled_day: date | None,
    observations: Sequence[Mapping[str, object]],
) -> str:
    """Hash the immutable probability, official clock, rules, and raw observations.

    ``latest_day`` is deliberately excluded: it is the processing clock recorded in
    ``graded_at``, not market evidence.  Re-running a final grade later therefore
    compares equal, while any revised entry/intermediate/exit raw row changes a
    daily digest and triggers the keep-first contradiction.
    """
    identity = {field: probability.get(field) for field in PROBABILITY_KEY}
    return canonical_hash(
        {
            "schema_version": "cn_limit_alpha_grade_source.v1",
            "probability_identity": identity,
            "probability_source_hash": probability.get("source_hash"),
            "clock": {
                "signal_session": probability.get("signal_date"),
                "entry_session": probability.get("entry_session"),
                "grade_kind": grade_kind,
                "horizon": horizon,
                "scheduled_exit_session": (
                    scheduled_day.isoformat() if scheduled_day is not None else None
                ),
                "calendar_artifact_hash": calendar.artifact_hash,
            },
            "rules": {
                "limit_definition": probability.get("limit_definition"),
                "entry_rule": probability.get("entry_rule"),
                "tolerant_cushion": TOLERANT_CUSHION,
                "max_lower_limit_carry": MAX_LOWER_LIMIT_CARRY,
                "cost_bps": list(COST_BPS),
            },
            "observations": [dict(observation) for observation in observations],
        }
    )


def _event_grade(
    probability: Mapping[str, object],
    state: DailyState,
    calendar: ExchangeCalendar,
    latest_day: date,
) -> dict[str, object]:
    entry_day = date.fromisoformat(str(probability["entry_session"]))
    if state.observation == "observed":
        event_state = "observed_event" if state.event_outcome else "observed_non_event"
    else:
        event_state = "missing_halted_non_event"
    fill_clock = "09:30:00" if state.observation == "observed" else "15:00:00"
    source_hash = _grade_source_hash(
        probability,
        calendar,
        grade_kind="event",
        horizon="EVENT_D",
        scheduled_day=None,
        observations=[_grade_observation("entry", entry_day, state)],
    )
    return _normalize_grade(
        {
            "authority": AUTHORITY,
            "source_hash": source_hash,
            "signal_date": probability["signal_date"],
            "ticker": probability["ticker"],
            "model_version": probability["model_version"],
            "limit_definition": probability["limit_definition"],
            "entry_rule": probability["entry_rule"],
            "grade_kind": "event",
            "horizon": "EVENT_D",
            "entry_session": probability["entry_session"],
            "graded_at": f"{latest_day.isoformat()}T15:00:00+08:00",
            "grade_observed_session": latest_day.isoformat(),
            "fill_decided_at": f"{entry_day.isoformat()}T{fill_clock}+08:00",
            "entry_fill_state": state.entry_fill_state,
            "event_outcome": state.event_outcome,
            "event_state": event_state,
        }
    )


def _execution_grade_base(
    probability: Mapping[str, object],
    entry_state: DailyState,
    latest_day: date,
    horizon: int,
    scheduled_day: date,
    source_hash: str,
) -> dict[str, object]:
    entry_day = date.fromisoformat(str(probability["entry_session"]))
    fill_clock = "09:30:00" if entry_state.observation == "observed" else "15:00:00"
    return {
        "authority": AUTHORITY,
        "source_hash": source_hash,
        "signal_date": probability["signal_date"],
        "ticker": probability["ticker"],
        "model_version": probability["model_version"],
        "limit_definition": probability["limit_definition"],
        "entry_rule": probability["entry_rule"],
        "grade_kind": "execution_return",
        "horizon": f"H{horizon}_next_open",
        "entry_session": probability["entry_session"],
        "graded_at": f"{latest_day.isoformat()}T15:00:00+08:00",
        "grade_observed_session": latest_day.isoformat(),
        "fill_decided_at": f"{entry_day.isoformat()}T{fill_clock}+08:00",
        "entry_fill_state": entry_state.entry_fill_state,
        "event_outcome": entry_state.event_outcome,
        "scheduled_exit_session": scheduled_day.isoformat(),
    }


def _unfilled_execution_grade(
    probability: Mapping[str, object],
    entry_state: DailyState,
    latest_day: date,
    horizon: int,
    scheduled_day: date,
    source_hash: str,
) -> dict[str, object]:
    base = _execution_grade_base(
        probability, entry_state, latest_day, horizon, scheduled_day, source_hash
    )
    base.update(
        {
            "exit_state": (
                "not_entered_queue_no_fill"
                if entry_state.entry_fill_state == "queue_required_no_fill"
                else "not_entered_missing_halted_no_fill"
            ),
            "realized_exit_session": None,
            "gross_return": None,
            "net_return_bps_grid": None,
            "book_contribution_return": 0.0,
        }
    )
    return _normalize_grade(base)


def _unresolved_execution_grade(
    probability: Mapping[str, object],
    entry_state: DailyState,
    latest_day: date,
    horizon: int,
    scheduled_day: date,
    exit_state: str,
    source_hash: str,
) -> dict[str, object]:
    base = _execution_grade_base(
        probability, entry_state, latest_day, horizon, scheduled_day, source_hash
    )
    base.update(
        {
            "exit_state": exit_state,
            "realized_exit_session": None,
            "gross_return": None,
            "net_return_bps_grid": None,
            "book_contribution_return": 0.0,
        }
    )
    return _normalize_grade(base)


def _resolved_execution_grade(
    probability: Mapping[str, object],
    entry_state: DailyState,
    latest_day: date,
    horizon: int,
    scheduled_day: date,
    realized_day: date,
    exit_price: float,
    source_hash: str,
) -> dict[str, object]:
    if entry_state.open_price is None or entry_state.open_price <= 0:
        raise IntegrityError("resolved execution lacks a valid entry open")
    gross = exit_price / entry_state.open_price - 1.0
    base = _execution_grade_base(
        probability, entry_state, latest_day, horizon, scheduled_day, source_hash
    )
    base.update(
        {
            "exit_state": (
                "resolved_scheduled_open"
                if realized_day == scheduled_day
                else "resolved_after_lower_limit_carry"
            ),
            "realized_exit_session": realized_day.isoformat(),
            "gross_return": gross,
            "net_return_bps_grid": {
                str(cost): gross - cost / 10_000.0 for cost in COST_BPS
            },
            "book_contribution_return": gross,
        }
    )
    return _normalize_grade(base)


def build_execution_grade(
    probability: Mapping[str, object],
    frames: Mapping[str, pd.DataFrame],
    calendar: ExchangeCalendar,
    latest_day: date,
    horizon: int,
    *,
    entry_state: DailyState | None = None,
) -> dict[str, object] | None:
    """Build a final execution grade, or ``None`` while its exact clock is unresolved."""
    ticker = canonical_ticker(str(probability["ticker"]))
    frame = frames.get(ticker)
    entry_day = date.fromisoformat(str(probability["entry_session"]))
    state = entry_state or daily_state(frame, ticker, entry_day)
    scheduled_day = calendar.offset(entry_day, horizon)
    if latest_day < scheduled_day:
        return None
    observations = [_grade_observation("entry", entry_day, state)]
    if state.entry_fill_state != "fillable_daily_proxy":
        source_hash = _grade_source_hash(
            probability,
            calendar,
            grade_kind="execution_return",
            horizon=f"H{horizon}_next_open",
            scheduled_day=scheduled_day,
            observations=observations,
        )
        return _unfilled_execution_grade(
            probability, state, latest_day, horizon, scheduled_day, source_hash
        )

    # H3/H5 may not jump across a missing intermediate exact session.
    for offset in range(1, horizon):
        intermediate_day = calendar.offset(entry_day, offset)
        intermediate = daily_state(frame, ticker, intermediate_day)
        observations.append(
            _grade_observation(f"intermediate_{offset}", intermediate_day, intermediate)
        )
        if intermediate.observation != "observed":
            source_hash = _grade_source_hash(
                probability,
                calendar,
                grade_kind="execution_return",
                horizon=f"H{horizon}_next_open",
                scheduled_day=scheduled_day,
                observations=observations,
            )
            return _unresolved_execution_grade(
                probability,
                state,
                latest_day,
                horizon,
                scheduled_day,
                "missing_intermediate_session_no_hop",
                source_hash,
            )

    for carry in range(MAX_LOWER_LIMIT_CARRY + 1):
        exit_day = calendar.offset(scheduled_day, carry)
        if exit_day > latest_day:
            return None
        exit_observation = daily_state(frame, ticker, exit_day)
        observations.append(
            _grade_observation(f"exit_or_carry_{carry}", exit_day, exit_observation)
        )
        if (
            exit_observation.observation != "observed"
            or exit_observation.open_price is None
            or exit_observation.lower_limit is None
        ):
            source_hash = _grade_source_hash(
                probability,
                calendar,
                grade_kind="execution_return",
                horizon=f"H{horizon}_next_open",
                scheduled_day=scheduled_day,
                observations=observations,
            )
            return _unresolved_execution_grade(
                probability,
                state,
                latest_day,
                horizon,
                scheduled_day,
                "missing_exact_exit_session_no_hop",
                source_hash,
            )
        lower_locked = exit_observation.open_price <= exit_observation.lower_limit * (
            1.0 + TOLERANT_CUSHION
        )
        if not lower_locked:
            source_hash = _grade_source_hash(
                probability,
                calendar,
                grade_kind="execution_return",
                horizon=f"H{horizon}_next_open",
                scheduled_day=scheduled_day,
                observations=observations,
            )
            return _resolved_execution_grade(
                probability,
                state,
                latest_day,
                horizon,
                scheduled_day,
                exit_day,
                exit_observation.open_price,
                source_hash,
            )
        if carry == MAX_LOWER_LIMIT_CARRY:
            source_hash = _grade_source_hash(
                probability,
                calendar,
                grade_kind="execution_return",
                horizon=f"H{horizon}_next_open",
                scheduled_day=scheduled_day,
                observations=observations,
            )
            return _unresolved_execution_grade(
                probability,
                state,
                latest_day,
                horizon,
                scheduled_day,
                "unresolved_lower_limit_carry_20_sessions",
                source_hash,
            )
    raise AssertionError("lower-limit carry loop exhausted unexpectedly")


def build_due_grades(
    probabilities: Sequence[Mapping[str, object]],
    existing_grades: Sequence[Mapping[str, object]],
    frames: Mapping[str, pd.DataFrame],
    calendar: ExchangeCalendar,
    latest_day: date,
) -> list[dict[str, object]]:
    """Return only new final grades, rejecting recomputed keep-first contradictions."""
    probability_index = {
        _row_key(row, PROBABILITY_KEY): dict(row) for row in probabilities
    }
    existing_index = _validate_grade_rows(
        existing_grades, probability_index, calendar, label="existing"
    )
    candidates: list[dict[str, object]] = []
    state_cache: dict[tuple[str, date], DailyState] = {}
    for probability in sorted(
        probabilities, key=lambda row: _row_key(row, PROBABILITY_KEY)
    ):
        entry_day = date.fromisoformat(str(probability["entry_session"]))
        if entry_day > latest_day:
            continue
        ticker = canonical_ticker(str(probability["ticker"]))
        cache_key = (ticker, entry_day)
        if cache_key not in state_cache:
            state_cache[cache_key] = daily_state(frames.get(ticker), ticker, entry_day)
        entry_state = state_cache[cache_key]
        candidates.append(_event_grade(probability, entry_state, calendar, latest_day))
        if probability["selection_state"] != "selected_top20":
            continue
        for horizon in HORIZONS:
            execution = build_execution_grade(
                probability,
                frames,
                calendar,
                latest_day,
                horizon,
                entry_state=entry_state,
            )
            if execution is not None:
                candidates.append(execution)

    candidate_index = _validate_grade_rows(
        candidates, probability_index, calendar, label="recomputed due"
    )
    additions: list[dict[str, object]] = []
    for key, row in candidate_index.items():
        prior = existing_index.get(key)
        if prior is not None:
            # grade_observed_session/graded_at are evidence payload.  Recomputing
            # an already final row on a later night must not mutate those fields.
            comparable = dict(row)
            comparable["grade_observed_session"] = prior["grade_observed_session"]
            comparable["graded_at"] = prior["graded_at"]
            if canonical_hash(prior) != canonical_hash(comparable):
                raise IntegrityError(f"keep-first grade contradiction: {key}")
            continue
        additions.append(row)

    # Once entry D is observed, every probability in that snapshot has one event grade.
    combined = {
        **existing_index,
        **{_row_key(row, GRADE_KEY): row for row in additions},
    }
    due_probability_keys = {
        _row_key(row, PROBABILITY_KEY)
        for row in probabilities
        if date.fromisoformat(str(row["entry_session"])) <= latest_day
    }
    event_keys = {
        key[: len(PROBABILITY_KEY)]
        for key, row in combined.items()
        if row["grade_kind"] == "event"
    }
    if not due_probability_keys.issubset(event_keys):
        raise IntegrityError(
            "event grading is incomplete for the due full-population probability set"
        )
    return additions


def _merge_keep_first(
    existing: Sequence[Mapping[str, object]],
    incoming: Sequence[Mapping[str, object]],
    key_fields: Sequence[str],
    *,
    label: str,
) -> list[dict[str, object]]:
    by_key = {_row_key(row, key_fields): dict(row) for row in existing}
    if len(by_key) != len(existing):
        raise IntegrityError(f"duplicate keys in existing {label}")
    for raw in incoming:
        row = dict(raw)
        key = _row_key(row, key_fields)
        prior = by_key.get(key)
        if prior is not None and canonical_hash(prior) != canonical_hash(row):
            raise IntegrityError(f"keep-first {label} contradiction: {key}")
        by_key.setdefault(key, row)
    return [by_key[key] for key in sorted(by_key)]


@dataclass(frozen=True)
class AdvanceReceipt:
    latest_complete_session: str | None
    latest_support_names: int | None
    probability_rows_total: int
    grade_rows_total: int
    probability_rows_written: int
    grade_rows_written: int
    partitions_written: tuple[str, ...]
    bootstrap_only: bool
    authority: str = AUTHORITY

    def as_dict(self) -> dict[str, object]:
        return {
            "latest_complete_session": self.latest_complete_session,
            "latest_support_names": self.latest_support_names,
            "probability_rows_total": self.probability_rows_total,
            "grade_rows_total": self.grade_rows_total,
            "probability_rows_written": self.probability_rows_written,
            "grade_rows_written": self.grade_rows_written,
            "partitions_written": list(self.partitions_written),
            "bootstrap_only": self.bootstrap_only,
            "authority": self.authority,
        }


def advance_forward_ledger(
    *,
    receipt_path: Path = DEFAULT_RECEIPT_PATH,
    seed_path: Path = DEFAULT_SEED_PATH,
    raw_dir: Path = DEFAULT_RAW_DIR,
    st_path: Path = DEFAULT_ST_PATH,
    calendar_path: Path = DEFAULT_CALENDAR_PATH,
    ledger_root: Path = DEFAULT_LEDGER_ROOT,
    bootstrap_only: bool = False,
    minimum_support_names: int = 50,
    support_ratio: float = 0.98,
) -> AdvanceReceipt:
    """Bootstrap/advance the forward ledger under the sole Asia write lane."""
    # Load the gate dynamically; no import-time env cache and no alternate lane alias.
    # No directory or temporary file is created before this check.
    if not ledger_lane.asia_advance_enabled():
        raise IntegrityError("CN limit-alpha ledger may mutate only with CN_LANE=asia")

    packet = load_frozen_packet(receipt_path)
    calendar = load_exchange_calendar(calendar_path)
    seed_rows = load_seed_jsonl(seed_path)
    _validate_probability_rows(seed_rows, packet, calendar, label="honest seed")

    existing_probabilities = load_partitioned_rows(ledger_root, "probabilities")
    existing_grades = load_partitioned_rows(ledger_root, "grades")
    if existing_probabilities:
        _validate_probability_rows(
            existing_probabilities, packet, calendar, label="existing partition store"
        )

    plans: list[PlannedPartition] = []
    seed_day_values = {date.fromisoformat(str(row["signal_date"])) for row in seed_rows}
    if len(seed_day_values) != 1:
        raise IntegrityError("honest bootstrap seed spans more than one signal date")
    seed_day = next(iter(seed_day_values))
    seed_plan = _plan_partition(
        _partition_path(ledger_root, "probabilities", seed_day),
        seed_rows,
        PROBABILITY_SCHEMA,
        PROBABILITY_KEY,
    )
    if seed_plan is not None:
        plans.append(seed_plan)
    combined_probabilities = _merge_keep_first(
        existing_probabilities,
        seed_rows,
        PROBABILITY_KEY,
        label="probability",
    )

    latest: ObservedSession | None = None
    new_probability_rows: list[dict[str, object]] = []
    new_grade_rows: list[dict[str, object]] = []
    frames: dict[str, pd.DataFrame] = {}
    if not bootstrap_only:
        frames = load_raw_frames(raw_dir)
        latest = discover_latest_complete_session(
            frames,
            calendar,
            minimum_names=minimum_support_names,
            support_ratio=support_ratio,
        )
        signal_already_stamped = any(
            row["signal_date"] == latest.day.isoformat()
            for row in combined_probabilities
        )
        if not signal_already_stamped:
            st_snapshot = load_st_exclusions(st_path)
            require_st_exclusions_for_signal(st_snapshot, latest.day)
            population = build_latest_eligible_population(
                frames, latest.day, packet, set(st_snapshot.tickers)
            )
            entry_day = calendar.next_session(latest.day)
            new_probability_rows = build_probability_snapshot(
                population,
                latest.day,
                entry_day,
                packet,
                calendar,
                st_snapshot_hash=st_snapshot.artifact_hash,
            )
            _validate_probability_rows(
                new_probability_rows, packet, calendar, label="new snapshot"
            )
            probability_plan = _plan_partition(
                _partition_path(ledger_root, "probabilities", latest.day),
                new_probability_rows,
                PROBABILITY_SCHEMA,
                PROBABILITY_KEY,
            )
            if probability_plan is not None:
                plans.append(probability_plan)
            combined_probabilities = _merge_keep_first(
                combined_probabilities,
                new_probability_rows,
                PROBABILITY_KEY,
                label="probability",
            )

        new_grade_rows = build_due_grades(
            combined_probabilities,
            existing_grades,
            frames,
            calendar,
            latest.day,
        )
        if new_grade_rows:
            grade_plan = _plan_partition(
                _partition_path(ledger_root, "grades", latest.day),
                new_grade_rows,
                GRADE_SCHEMA,
                GRADE_KEY,
            )
            if grade_plan is not None:
                plans.append(grade_plan)

    # Global validation happens before the first partition is installed.
    probability_index = _validate_probability_rows(
        combined_probabilities, packet, calendar, label="planned combined store"
    )
    combined_grades = _merge_keep_first(
        existing_grades,
        new_grade_rows,
        GRADE_KEY,
        label="grade",
    )
    _validate_grade_rows(
        combined_grades, probability_index, calendar, label="planned combined store"
    )

    written_paths: list[str] = []
    probability_written = 0
    grade_written = 0
    for plan in sorted(plans, key=lambda item: str(item.path)):
        if plan.path.exists():
            raise IntegrityError(
                f"partition appeared after validation; refusing overwrite: {plan.path}"
            )
        _atomic_write_partition(plan.path, plan.rows, plan.schema)
        written_paths.append(
            str(
                plan.path.relative_to(ROOT)
                if plan.path.is_relative_to(ROOT)
                else plan.path
            )
        )
        if "/probabilities/" in plan.path.as_posix():
            probability_written += len(plan.rows)
        else:
            grade_written += len(plan.rows)

    return AdvanceReceipt(
        latest_complete_session=latest.day.isoformat() if latest else None,
        latest_support_names=latest.support_names if latest else None,
        probability_rows_total=len(combined_probabilities),
        grade_rows_total=len(combined_grades),
        probability_rows_written=probability_written,
        grade_rows_written=grade_written,
        partitions_written=tuple(written_paths),
        bootstrap_only=bootstrap_only,
    )


__all__ = [
    "AUTHORITY",
    "DEFAULT_CALENDAR_PATH",
    "DEFAULT_LEDGER_ROOT",
    "DEFAULT_RAW_DIR",
    "DEFAULT_RECEIPT_PATH",
    "DEFAULT_SEED_PATH",
    "DEFAULT_ST_PATH",
    "GRADE_KEY",
    "GRADE_SCHEMA",
    "PROBABILITY_KEY",
    "PROBABILITY_SCHEMA",
    "AdvanceReceipt",
    "ExchangeCalendar",
    "FrozenPacket",
    "IntegrityError",
    "STExclusions",
    "advance_forward_ledger",
    "board_from_ticker",
    "build_due_grades",
    "build_execution_grade",
    "build_latest_eligible_population",
    "build_probability_snapshot",
    "canonical_hash",
    "canonical_ticker",
    "clean_raw_frame",
    "compute_feature_frame",
    "daily_state",
    "discover_latest_complete_session",
    "load_exchange_calendar",
    "load_frozen_packet",
    "load_partitioned_rows",
    "load_raw_frames",
    "load_seed_jsonl",
    "load_st_exclusions",
    "read_partition",
    "require_st_exclusions_for_signal",
    "score_frozen_model",
]
