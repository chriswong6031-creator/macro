"""Full chip DISTRIBUTION (筹码分布) per ticker x trade_date — TuShare ``cyq_chips``, GATED.

The missing sibling of the running ``cyq_perf`` plane. ``tushare_chips.py`` collects the daily
SUMMARY (winner_rate, weighted-average cost, the 5/50/95pct cost quantiles) in one whole-market
call; ``cyq_chips`` returns the underlying HISTOGRAM — one row per price level, carrying the
share of float held at that level. Summary statistics cannot be inverted back into the shape,
so the distribution is a genuinely new observable: bimodality, the size of an overhead supply
wall, and how tightly cost basis clusters around the last price are all invisible to cyq_perf.

CONTRACT (pinned from the official documentation page, doc_id=294, captured 2026-08-09):

  ts_code     str    股票代码
  trade_date  str    交易日期
  price       float  成本价格 — the price level of this histogram bucket
  percent     float  价格占比（%） — the share of float held at that level, in PERCENTAGE
                     POINTS (0-100), NOT a 0-1 fraction. The vendor's own label carries the
                     ``%``; the rows of one ticker x trade_date sum to ~100.

  ts_code is REQUIRED — unlike cyq_perf there is no whole-market ``trade_date=`` snapshot, so
  this plane costs one call per ticker (per date window). 6000-row single-call cap; history
  from 2018; vendor updates 18:00-19:00 CST.

``percent`` is stored EXACTLY as the vendor documents it — percentage points, unconverted. The
0-1 fractions the research consumers want are produced by the aggregation contract below, which
divides by 100 in one audited place. A silent 100x rescale would corrupt every downstream
concentration feature identically and invisibly, so ``percent_mass_observation`` classifies the
observed mass per partition and REFUSES a response whose mass is fraction-like (~1 instead of
~100): a scale contradiction is a loud stop, never a quiet renormalization.

STORE — ``data/china_chips_distribution/`` (private to the collection host; the ``.gitignore``
line for this root ships with Lane A, so do not run a bulk accrual against the default root
until that line has landed):

  by_trade_date=YYYY-MM-DD/by_ticker=<TICKER>/{part.parquet,receipt.json}

Keep-first immutable, staged then atomically renamed, exactly as ``tushare_addons`` installs its
partitions. The ``by_ticker=`` level is load-bearing rather than decorative: because ts_code is
required, a date partition can only ever hold ONE ticker, so a flat ``by_trade_date=`` directory
would make the second ticker collected for a date a keep-first contradiction against the first.
Re-collecting an existing partition with identical rows is a no-op; with different rows it
raises rather than overwriting.

This collector is operator-ordered under
``research/TUSHARE_WIRING_TAKEOVER_2026-08-09.md``. Receipts carry that instruction as plain
collection provenance. The module embeds no extra authorization environment gate and reaches no
legal conclusion; execution still requires ``TUSHARE_TOKEN`` plus every technical bound below.

What survives in every receipt is EPISTEMIC: access is observed only for the exact request that
returned rows, no completeness is claimed across tickers or dates, the distribution semantics
are pinned to the official doc page (or marked as observed-and-pending if a future contract
capture has to come from a probe), and nothing here carries rank/size/gate authority — promotion
runs the normal gauntlet. Raw distribution rows stay in the private store; the DERIVED
aggregates below are the research-facing surface.

GATED: every entry point no-ops unless ``TUSHARE_TOKEN`` is set. No token, request header, or
raw vendor payload is ever logged or persisted — vendor error text is untrusted and can echo a
request, so failures are reported by reason CODE only.

DISPLAY/CONTEXT-ONLY. This is a context plane, not a signal: promotion of any feature derived
here to rank/size/gate authority goes through the normal gauntlet.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import shutil
import sys
import tempfile
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from collectors import tushare_client as tc
from lib import config

log = logging.getLogger("tushare_chips_distribution")

DEFAULT_OUTPUT_ROOT = config.data_dir() / "china_chips_distribution"

# EPISTEMIC tier only — display/context until a feature is gauntleted.
AUTHORITY = "context_display_only"
PARTITION_SCHEMA_VERSION = "china_chips_distribution_partition.v1"
RECEIPT_SCHEMA_VERSION = "china_chips_distribution_collection_receipt.v1"

# --- Operator-ordered collection provenance (plain instruction, not a legal conclusion) -----
COLLECTION_PROVENANCE_MODE = "operator_ordered_wiring"
COLLECTION_PROVENANCE_DOCUMENT = "research/TUSHARE_WIRING_TAKEOVER_2026-08-09.md"
COLLECTION_PROVENANCE_SHA256 = (
    "18bd19ea22a0bcb47a5ce8b983ba64ecacc8d706ae329578d1e6d2d6e7e7594d"
)

# --- Vendor contract, pinned from the official doc page ------------------------------------
ENDPOINT = "cyq_chips"
CONTRACT_DOC_ID = 294
CONTRACT_CAPTURE_DATE = "2026-08-09"
CONTRACT_SOURCE = "official_doc_page"
VENDOR_FIELDS: tuple[str, ...] = ("ts_code", "trade_date", "price", "percent")
VENDOR_MAX_ROWS = 6000
VENDOR_HISTORY_START = "2018"
PERCENT_UNIT = "percentage_points_0_100"
PERCENT_UNIT_VENDOR_LABEL = "价格占比（%）"
PRICE_UNIT = "cny_per_share_exact_decimal"
PRICE_DECIMAL_SCALE = 4

# Whole-market premium pool is 300/min and SHARED with every other TuShare lane; this plane
# margins itself to 240/min so nightly incrementals and the running premium collectors never
# starve behind a bulk accrual. The shared client's own per-endpoint throttle is applied on
# top, so the effective rate is the stricter of the two and this ceiling can only tighten.
MAX_CALLS_PER_MINUTE = 240
_MIN_CALL_INTERVAL_S = 60.0 / MAX_CALLS_PER_MINUTE
_MAX_CALLS_PER_RUN = 60

# One ticker x date distribution sums to ~100 percentage points. A response whose mass is
# fraction-like is a UNIT contradiction against the documented label, not a data quirk.
_PERCENT_MASS_PCT_BAND = (90.0, 110.0)
_PERCENT_MASS_FRACTION_BAND = (0.90, 1.10)

_TICKER_RE = re.compile(r"^[0-9]{6}\.(?:SS|SZ|BJ)$")

DEFAULT_BANDS: tuple[float, ...] = (5.0, 10.0)

QueryFunction = Callable[..., "pd.DataFrame | None"]


class CollectionHeld(RuntimeError):
    """Collection deliberately did not happen. Carries a reason CODE, never vendor text."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


class CollectorIntegrityError(RuntimeError):
    """The vendor response or an installed partition contradicts the pinned contract."""


@dataclass(frozen=True)
class CollectionResult:
    status: str  # "written" | "unchanged"
    ticker: str
    trade_date: str
    partition_path: str
    row_count: int
    data_hash: str
    receipt_hash: str
    percent_mass_total: float
    percent_mass_observation: str
    authority: str = AUTHORITY

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "ticker": self.ticker,
            "trade_date": self.trade_date,
            "partition_path": self.partition_path,
            "row_count": self.row_count,
            "data_hash": self.data_hash,
            "receipt_hash": self.receipt_hash,
            "percent_mass_total": self.percent_mass_total,
            "percent_mass_observation": self.percent_mass_observation,
            "authority": self.authority,
        }


# ---------------------------------------------------------------------------------------
# canonical hashing / provenance helpers
# ---------------------------------------------------------------------------------------


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
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
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _jsonable(value: object) -> object:
    """Canonical JSON scalar — Decimal becomes its exact string so hashes stay exact."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    item = getattr(value, "item", None)
    if callable(item) and not isinstance(value, (str, bytes)):
        return _jsonable(item())
    if isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CollectorIntegrityError("vendor value is not finite")
        return value
    raise CollectorIntegrityError("vendor value has an unsupported scalar type")


def _canonical_rows(records: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    return [{k: _jsonable(v) for k, v in sorted(row.items())} for row in records]


def endpoint_contract() -> dict[str, object]:
    """The pinned vendor contract. Any drift here changes ``contract_sha256`` and so is loud."""
    payload = {
        "api_name": ENDPOINT,
        "doc_id": CONTRACT_DOC_ID,
        "document_url": f"https://tushare.pro/document/2?doc_id={CONTRACT_DOC_ID}",
        "contract_source": CONTRACT_SOURCE,
        "contract_capture_date": CONTRACT_CAPTURE_DATE,
        "vendor_fields": list(VENDOR_FIELDS),
        "required_params": ["ts_code"],
        "max_rows_per_call": VENDOR_MAX_ROWS,
        "history_start": VENDOR_HISTORY_START,
        "percent_unit": PERCENT_UNIT,
        "percent_vendor_label": PERCENT_UNIT_VENDOR_LABEL,
        "price_unit": PRICE_UNIT,
        "price_decimal_scale": PRICE_DECIMAL_SCALE,
        "tier": "premium_300_per_minute_shared_pool",
    }
    return {**payload, "contract_sha256": canonical_hash(payload)}


def _collection_provenance_receipt() -> dict[str, object]:
    """Record the operator's collection instruction without making a legal conclusion."""
    return {
        "mode": COLLECTION_PROVENANCE_MODE,
        "authority_document": COLLECTION_PROVENANCE_DOCUMENT,
        "authority_document_sha256": COLLECTION_PROVENANCE_SHA256,
        "scope": "private_collection_and_in_repo_research",
        "legal_conclusion": "none_embedded_in_collection_receipt",
    }


def schema_descriptor() -> dict[str, object]:
    return {
        "schema_version": PARTITION_SCHEMA_VERSION,
        "fields": [
            {"name": "schema_version", "type": "string"},
            {"name": "authority", "type": "string"},
            {"name": "ticker", "type": "string"},
            {"name": "trade_date", "type": "string"},
            {"name": "price", "type": f"decimal128(18,{PRICE_DECIMAL_SCALE})"},
            {"name": "percent", "type": "double"},
        ],
        "percent_unit": PERCENT_UNIT,
        "price_unit": PRICE_UNIT,
    }


def arrow_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("schema_version", pa.string(), nullable=False),
            pa.field("authority", pa.string(), nullable=False),
            pa.field("ticker", pa.string(), nullable=False),
            pa.field("trade_date", pa.string(), nullable=False),
            pa.field("price", pa.decimal128(18, PRICE_DECIMAL_SCALE), nullable=False),
            pa.field("percent", pa.float64(), nullable=False),
        ]
    )


# ---------------------------------------------------------------------------------------
# request / response normalization
# ---------------------------------------------------------------------------------------


def canonical_ticker(raw: object) -> str:
    """Vendor ts_code -> this repo's suffix convention, validated as an A-share code."""
    normalized = tc.norm_ticker(str(raw or "").strip().upper()) or ""
    if not _TICKER_RE.fullmatch(normalized):
        raise CollectorIntegrityError("ticker is not a canonical A-share code")
    return normalized


def vendor_ticker(ticker: str) -> str:
    """This repo's ``.SS`` back to the vendor's ``.SH``; ``.SZ``/``.BJ`` pass through."""
    return ticker[:-3] + ".SH" if ticker.endswith(".SS") else ticker


def parse_trade_date(raw: date | str) -> date:
    if isinstance(raw, datetime):
        raise CollectionHeld("trade_date_must_not_include_time")
    if isinstance(raw, date):
        return raw
    value = str(raw).strip()
    try:
        if re.fullmatch(r"[0-9]{8}", value):
            value = f"{value[:4]}-{value[4:6]}-{value[6:]}"
        return date.fromisoformat(value)
    except ValueError as exc:
        raise CollectionHeld("invalid_trade_date") from exc


def _exact_price(value: object) -> Decimal:
    """Vendor price -> exact Decimal. Excess precision RAISES rather than silently rounding."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        raise CollectorIntegrityError("vendor price level is null")
    if isinstance(value, bool):
        raise CollectorIntegrityError("boolean entered the vendor price field")
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise CollectorIntegrityError("vendor price level is not numeric") from exc
    if not parsed.is_finite():
        raise CollectorIntegrityError("vendor price level is not finite")
    if parsed <= 0:
        raise CollectorIntegrityError("vendor price level is not positive")
    if -parsed.as_tuple().exponent > PRICE_DECIMAL_SCALE:
        # Rounding here would silently move a price level off the vendor's grid.
        raise CollectorIntegrityError(
            "vendor price level exceeds the pinned decimal scale"
        )
    # Pad to exactly the pinned scale. Excess precision was already REJECTED above, so this
    # only appends trailing zeros and can never round a level away. It is load-bearing for
    # keep-first: Parquet returns decimals at the column's scale, so an unpadded in-memory
    # Decimal("10.0") would canonicalize differently from the stored Decimal("10.0000") and
    # every re-collect would read as a partition contradiction against itself.
    return parsed.quantize(Decimal(1).scaleb(-PRICE_DECIMAL_SCALE))


def _percent(value: object) -> float:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        raise CollectorIntegrityError("vendor percent share is null")
    if isinstance(value, bool):
        raise CollectorIntegrityError("boolean entered the vendor percent field")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise CollectorIntegrityError("vendor percent share is not numeric") from exc
    if not math.isfinite(parsed):
        raise CollectorIntegrityError("vendor percent share is not finite")
    if parsed < 0:
        raise CollectorIntegrityError("vendor percent share is negative")
    return parsed


def percent_mass_observation(mass: float) -> str:
    """Classify the observed percent mass against the documented percentage-point unit."""
    if _PERCENT_MASS_PCT_BAND[0] <= mass <= _PERCENT_MASS_PCT_BAND[1]:
        return "consistent_with_documented_percentage_points"
    if _PERCENT_MASS_FRACTION_BAND[0] <= mass <= _PERCENT_MASS_FRACTION_BAND[1]:
        return "contradicts_documented_percentage_points_fraction_like"
    return "indeterminate_percent_mass"


def normalize_rows(
    frame: pd.DataFrame, ticker: str, trade_day: date
) -> list[dict[str, object]]:
    """Vendor frame -> validated partition records, sorted by price level.

    Raises rather than repairing: a missing/extra column, an off-request ticker or date, a
    duplicate price level, or a fraction-like percent mass are all contract contradictions.
    """
    missing = sorted(set(VENDOR_FIELDS) - set(frame.columns))
    extra = sorted(set(frame.columns) - set(VENDOR_FIELDS))
    if missing or extra:
        raise CollectorIntegrityError(
            "cyq_chips response schema differs from the pinned fields"
        )
    if len(frame) > VENDOR_MAX_ROWS:
        raise CollectorIntegrityError(
            "cyq_chips response exceeds the documented row cap"
        )
    expected_compact = trade_day.strftime("%Y%m%d")
    records: list[dict[str, object]] = []
    for raw in frame.to_dict(orient="records"):
        row_ticker = canonical_ticker(raw["ts_code"])
        if row_ticker != ticker:
            raise CollectorIntegrityError("vendor row escaped the requested ticker")
        if str(raw["trade_date"] or "").strip().replace("-", "") != expected_compact:
            raise CollectorIntegrityError("vendor row escaped the requested session")
        records.append(
            {
                "schema_version": PARTITION_SCHEMA_VERSION,
                "authority": AUTHORITY,
                "ticker": ticker,
                "trade_date": trade_day.isoformat(),
                "price": _exact_price(raw["price"]),
                "percent": _percent(raw["percent"]),
            }
        )
    if not records:
        raise CollectionHeld("cyq_chips_unavailable_empty_or_unentitled")
    prices = [row["price"] for row in records]
    if len(set(prices)) != len(prices):
        raise CollectorIntegrityError("cyq_chips response repeats a price level")
    mass = sum(float(row["percent"]) for row in records)
    if percent_mass_observation(mass) == (
        "contradicts_documented_percentage_points_fraction_like"
    ):
        # Storing this as-is would make every derived concentration feature 100x wrong and
        # look entirely plausible. Stop loudly; a unit change is a contract revision.
        raise CollectorIntegrityError(
            "cyq_chips percent mass is fraction-like and contradicts the documented % unit"
        )
    records.sort(key=lambda row: row["price"])
    return records


# ---------------------------------------------------------------------------------------
# aggregation contract — the research-facing surface (pure, no I/O)
# ---------------------------------------------------------------------------------------


def levels_from_rows(rows: Iterable[Mapping[str, object]]) -> list[tuple[float, float]]:
    """``[{price, percent}, ...]`` -> ``[(price, share_fraction), ...]`` sorted by price.

    This is the ONE place the documented percentage points become 0-1 share fractions, so a
    unit question has a single answer to audit. Rows with a null price or percent are dropped.
    """
    levels: list[tuple[float, float]] = []
    for row in rows:
        price = row.get("price")
        percent = row.get("percent")
        if price is None or percent is None:
            continue
        try:
            price_f = float(price)
            share = float(percent) / 100.0
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(price_f) and math.isfinite(share)):
            continue
        levels.append((price_f, share))
    levels.sort(key=lambda item: item[0])
    return levels


def concentration_share(
    levels: Sequence[tuple[float, float]], ref_price: float | None, band_pct: float
) -> float | None:
    """Fraction of chip mass sitting within +/-``band_pct``% of ``ref_price`` (edges inclusive).

    None — never 0.0 — when there is no usable reference price or no mass: "we cannot say" and
    "no chips are clustered near the close" are opposite readings and must not share a value.
    """
    total = sum(share for _, share in levels)
    if (
        ref_price is None
        or not math.isfinite(float(ref_price))
        or float(ref_price) <= 0
    ):
        return None
    if total <= 0:
        return None
    tolerance = float(ref_price) * float(band_pct) / 100.0
    inside = sum(
        share for price, share in levels if abs(price - float(ref_price)) <= tolerance
    )
    return inside / total


def winner_shares(
    levels: Sequence[tuple[float, float]], ref_price: float | None
) -> dict[str, float | None]:
    """Mass held below / at / above ``ref_price``, as fractions of total mass.

    Three-way and exhaustive by construction: chips bought BELOW the reference are in profit,
    ABOVE are underwater, and the level sitting exactly AT it is neither. Splitting the tie
    arbitrarily into one side is how a winner-rate quietly disagrees with cyq_perf's own.
    """
    total = sum(share for _, share in levels)
    if (
        ref_price is None
        or not math.isfinite(float(ref_price))
        or float(ref_price) <= 0
    ):
        return {"winner_share": None, "loser_share": None, "at_cost_share": None}
    if total <= 0:
        return {"winner_share": None, "loser_share": None, "at_cost_share": None}
    ref = float(ref_price)
    below = sum(share for price, share in levels if price < ref)
    above = sum(share for price, share in levels if price > ref)
    at = sum(share for price, share in levels if price == ref)
    return {
        "winner_share": below / total,
        "loser_share": above / total,
        "at_cost_share": at / total,
    }


def distribution_entropy(
    levels: Sequence[tuple[float, float]],
) -> dict[str, float | int | None]:
    """Shannon entropy (nats) of the chip mass across price levels, plus its normalization.

    ``entropy_normalized`` divides by ``ln(level_count)`` — the entropy of a distribution
    spread evenly over the WHOLE returned price grid. Normalizing by the occupied levels
    instead would score a two-level 50/50 split and a hundred-level uniform sheet identically
    at 1.0, erasing exactly the concentration the M2/M4 footprints are looking for.
    """
    total = sum(share for _, share in levels)
    level_count = len(levels)
    support = sum(1 for _, share in levels if share > 0)
    if level_count == 0 or total <= 0:
        return {
            "entropy_nats": None,
            "entropy_normalized": None,
            "level_count": level_count,
            "support_level_count": support,
        }
    entropy = 0.0
    for _, share in levels:
        if share > 0:
            p = share / total
            entropy -= p * math.log(p)
    normalized = entropy / math.log(level_count) if level_count > 1 else 0.0
    return {
        "entropy_nats": entropy,
        "entropy_normalized": normalized,
        "level_count": level_count,
        "support_level_count": support,
    }


def summarize_distribution(
    rows: Iterable[Mapping[str, object]],
    *,
    ref_price: float | None = None,
    bands: Sequence[float] = DEFAULT_BANDS,
) -> dict[str, object]:
    """One raw distribution -> the per-ticker-date DERIVED feature row (M2/M4 footprints).

    Pure. Raw histogram rows stay in the private store; this dict is what research consumes.
    Every share is a 0-1 fraction of the ticker's chip mass; reference-dependent features are
    None when no usable reference price was supplied.
    """
    rows = list(rows)
    levels = levels_from_rows(rows)
    total_share = sum(share for _, share in levels)
    features: dict[str, object] = {
        "ticker": next((str(r["ticker"]) for r in rows if r.get("ticker")), None),
        "trade_date": next(
            (str(r["trade_date"]) for r in rows if r.get("trade_date")), None
        ),
        "percent_mass_total": total_share * 100.0 if levels else None,
        "price_min": levels[0][0] if levels else None,
        "price_max": levels[-1][0] if levels else None,
        "peak_price": max(levels, key=lambda item: item[1])[0] if levels else None,
        "mass_weighted_avg_price": (
            sum(price * share for price, share in levels) / total_share
            if total_share > 0
            else None
        ),
        "ref_price": float(ref_price) if ref_price is not None else None,
    }
    features.update(distribution_entropy(levels))
    features.update(winner_shares(levels, ref_price))
    for band in bands:
        features[f"concentration_share_{band:g}pct"] = concentration_share(
            levels, ref_price, band
        )
    return features


# ---------------------------------------------------------------------------------------
# partition install (keep-first immutable)
# ---------------------------------------------------------------------------------------


def partition_path(root: Path, ticker: str, trade_day: date) -> Path:
    return Path(root) / f"by_trade_date={trade_day.isoformat()}" / f"by_ticker={ticker}"


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _receipt_without_hash(
    *,
    ticker: str,
    trade_day: date,
    records: Sequence[Mapping[str, object]],
    source_rows_hash: str,
    data_hash: str,
    parquet_hash: str,
    percent_mass: float,
    percent_mass_observation: str,
    now_utc: datetime,
) -> dict[str, object]:
    identity = {
        "endpoint": ENDPOINT,
        "ticker": ticker,
        "trade_date": trade_day.isoformat(),
    }
    descriptor = schema_descriptor()
    return {
        "receipt_schema_version": RECEIPT_SCHEMA_VERSION,
        "authority": AUTHORITY,
        "collection_provenance": _collection_provenance_receipt(),
        "endpoint_contract": endpoint_contract(),
        "access_observation_receipt": {
            "observation": "access_observed_at_request_time",
            "observation_basis": "valid_nonempty_rows_returned_for_this_request",
            "observed_at_utc": now_utc.isoformat(),
            "nonclaims": ["not_proof_of_future_access"],
        },
        "request": {
            "identity": identity,
            "identity_sha256": canonical_hash(identity),
            "vendor_request_without_token": {
                "transport": "HTTPS",
                "api_name": ENDPOINT,
                "params": {
                    "ts_code": vendor_ticker(ticker),
                    "trade_date": trade_day.strftime("%Y%m%d"),
                },
            },
            "range_or_bulk_mode": False,
        },
        "runtime_receipt": {
            "python": ".".join(str(v) for v in sys.version_info[:3]),
            "pandas": pd.__version__,
            "pyarrow": pa.__version__,
            "collector_source_sha256": file_hash(Path(__file__)),
            "tushare_client_source_sha256": file_hash(Path(tc.__file__)),
            "github_repository": os.environ.get("GITHUB_REPOSITORY"),
            "github_sha": os.environ.get("GITHUB_SHA"),
            "github_run_id": os.environ.get("GITHUB_RUN_ID"),
            "nonclaim": "environment_fields_are_execution_context_not_signed_identity",
        },
        "schema_receipt": {**descriptor, "schema_sha256": canonical_hash(descriptor)},
        "data_receipt": {
            "row_count": len(records),
            "canonical_vendor_rows_sha256": source_rows_hash,
            "normalized_rows_sha256": data_hash,
            "parquet_sha256": parquet_hash,
            "percent_mass_total": percent_mass,
            "percent_mass_observation": percent_mass_observation,
            "percent_unit": PERCENT_UNIT,
        },
        "partition_identity": identity,
        # EPISTEMIC nonclaims only. Collection provenance records the operator's instruction;
        # it does not alter what these rows can support.
        "nonclaims": [
            "context_only_not_signal_rank_size_or_gate_authority",
            "access_attested_only_for_this_exact_request",
            "no_completeness_claim_across_tickers_or_dates",
            f"distribution_semantics_pinned_from_{CONTRACT_SOURCE}",
        ],
    }


def _load_receipt(path: Path) -> dict[str, object]:
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CollectorIntegrityError(
            "immutable partition receipt is unreadable"
        ) from exc
    if not isinstance(receipt, dict):
        raise CollectorIntegrityError("immutable partition receipt is not an object")
    declared = receipt.get("receipt_sha256")
    body = dict(receipt)
    body.pop("receipt_sha256", None)
    if not _is_sha256(declared) or canonical_hash(body) != declared:
        raise CollectorIntegrityError(
            "immutable partition receipt hash does not recompute"
        )
    return receipt


def _validate_existing_partition(
    destination: Path,
    ticker: str,
    trade_day: date,
    incoming_data_hash: str,
    incoming_source_rows_hash: str,
) -> dict[str, object]:
    """Keep-first: an existing partition must AGREE with the incoming response, or we stop."""
    if destination.is_symlink() or not destination.is_dir():
        raise CollectorIntegrityError("immutable partition path is not a directory")
    if any(child.is_symlink() for child in destination.iterdir()):
        raise CollectorIntegrityError("immutable partition bundle contains a symlink")
    if {child.name for child in destination.iterdir()} != {
        "part.parquet",
        "receipt.json",
    }:
        raise CollectorIntegrityError(
            "immutable partition bundle is partial or has extra files"
        )
    receipt = _load_receipt(destination / "receipt.json")
    if (
        receipt.get("receipt_schema_version") != RECEIPT_SCHEMA_VERSION
        or receipt.get("authority") != AUTHORITY
    ):
        raise CollectorIntegrityError("immutable partition receipt authority changed")
    if receipt.get("endpoint_contract") != endpoint_contract():
        raise CollectorIntegrityError("immutable partition endpoint contract changed")
    if receipt.get("collection_provenance") != _collection_provenance_receipt():
        raise CollectorIntegrityError("immutable collection provenance changed")
    identity = {
        "endpoint": ENDPOINT,
        "ticker": ticker,
        "trade_date": trade_day.isoformat(),
    }
    if receipt.get("partition_identity") != identity:
        raise CollectorIntegrityError("immutable partition identity changed")
    data_receipt = receipt.get("data_receipt")
    if not isinstance(data_receipt, dict):
        raise CollectorIntegrityError("immutable partition data receipt is malformed")
    parquet_path = destination / "part.parquet"
    if data_receipt.get("parquet_sha256") != file_hash(parquet_path):
        raise CollectorIntegrityError("immutable Parquet bytes contradict the receipt")
    if data_receipt.get("canonical_vendor_rows_sha256") != incoming_source_rows_hash:
        raise CollectorIntegrityError("keep-first vendor source contradiction")
    try:
        table = pq.ParquetFile(parquet_path).read()
    except Exception as exc:  # unreadable bytes are themselves an integrity fact
        raise CollectorIntegrityError("immutable Parquet part is unreadable") from exc
    if table.schema != arrow_schema():
        raise CollectorIntegrityError(
            "immutable Parquet schema contradicts the contract"
        )
    stored_hash = canonical_hash(_canonical_rows(table.to_pylist()))
    if data_receipt.get("normalized_rows_sha256") != stored_hash:
        raise CollectorIntegrityError(
            "immutable normalized rows contradict the receipt"
        )
    if incoming_data_hash != stored_hash:
        raise CollectorIntegrityError("keep-first immutable partition contradiction")
    return receipt


def _install_partition(
    *,
    root: Path,
    ticker: str,
    trade_day: date,
    records: Sequence[Mapping[str, object]],
    source_rows_hash: str,
    percent_mass: float,
    percent_mass_observation: str,
    now_utc: datetime,
) -> CollectionResult:
    destination = partition_path(root, ticker, trade_day)
    data_hash = canonical_hash(_canonical_rows(records))

    def _unchanged(receipt: Mapping[str, object]) -> CollectionResult:
        return CollectionResult(
            status="unchanged",
            ticker=ticker,
            trade_date=trade_day.isoformat(),
            partition_path=str(destination),
            row_count=len(records),
            data_hash=data_hash,
            receipt_hash=str(receipt["receipt_sha256"]),
            percent_mass_total=percent_mass,
            percent_mass_observation=percent_mass_observation,
        )

    if destination.exists():
        return _unchanged(
            _validate_existing_partition(
                destination, ticker, trade_day, data_hash, source_rows_hash
            )
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".chips-dist-stage-", dir=destination.parent))
    try:
        parquet_path = stage / "part.parquet"
        table = pa.Table.from_pylist(list(records), schema=arrow_schema())
        pq.write_table(
            table,
            parquet_path,
            compression="zstd",
            use_dictionary=False,
            write_statistics=True,
        )
        receipt = _receipt_without_hash(
            ticker=ticker,
            trade_day=trade_day,
            records=records,
            source_rows_hash=source_rows_hash,
            data_hash=data_hash,
            parquet_hash=file_hash(parquet_path),
            percent_mass=percent_mass,
            percent_mass_observation=percent_mass_observation,
            now_utc=now_utc,
        )
        receipt["receipt_sha256"] = canonical_hash(receipt)
        receipt_path = stage / "receipt.json"
        receipt_path.write_bytes(_json_bytes(receipt) + b"\n")
        _fsync_file(parquet_path)
        _fsync_file(receipt_path)
        _fsync_dir(stage)
        try:
            os.rename(stage, destination)
        except OSError:
            if not destination.exists():
                raise
            return _unchanged(
                _validate_existing_partition(
                    destination, ticker, trade_day, data_hash, source_rows_hash
                )
            )
        _fsync_dir(destination.parent)
        return CollectionResult(
            status="written",
            ticker=ticker,
            trade_date=trade_day.isoformat(),
            partition_path=str(destination),
            row_count=len(records),
            data_hash=data_hash,
            receipt_hash=str(receipt["receipt_sha256"]),
            percent_mass_total=percent_mass,
            percent_mass_observation=percent_mass_observation,
        )
    finally:
        if stage.exists():
            shutil.rmtree(stage)


# ---------------------------------------------------------------------------------------
# collection
# ---------------------------------------------------------------------------------------

_last_call_monotonic: float | None = None


def _govern() -> None:
    """Hold this plane at or under ``MAX_CALLS_PER_MINUTE`` of the SHARED premium pool."""
    global _last_call_monotonic
    if _last_call_monotonic is not None:
        wait = _MIN_CALL_INTERVAL_S - (time.monotonic() - _last_call_monotonic)
        if wait > 0:
            time.sleep(wait)
    _last_call_monotonic = time.monotonic()


def _fetch(
    query_fn: QueryFunction, ticker: str, trade_day: date | None
) -> tuple[pd.DataFrame, date]:
    """One bounded vendor call. Returns (frame, resolved trade date).

    ``trade_day=None`` walks back from the latest open session to the newest date that
    actually has rows for this ticker — the same snapshot-by-date fallback the cyq_perf
    collector uses, scoped by ts_code because cyq_chips has no whole-market call.
    """
    code = vendor_ticker(ticker)
    _govern()
    if trade_day is None:
        try:
            frame, resolved = tc.snapshot_by_date(ENDPOINT, ts_code=code)
        except Exception:  # noqa: BLE001 — never surface vendor/client exception text
            raise CollectionHeld(
                "tushare_query_failed_without_persisted_payload"
            ) from None
        if frame is None or resolved is None or frame.empty:
            raise CollectionHeld("cyq_chips_unavailable_empty_or_unentitled")
        return frame.copy(), parse_trade_date(resolved)
    try:
        frame = query_fn(
            ENDPOINT, ts_code=code, trade_date=trade_day.strftime("%Y%m%d")
        )
    except Exception:  # noqa: BLE001
        raise CollectionHeld("tushare_query_failed_without_persisted_payload") from None
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        raise CollectionHeld("cyq_chips_unavailable_empty_or_unentitled")
    return frame.copy(), trade_day


def collect(
    ticker: str,
    trade_date: date | str | None = None,
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    query_fn: QueryFunction = tc.query,
    now: datetime | None = None,
) -> CollectionResult:
    """Collect ONE ticker x trade_date distribution into a keep-first immutable partition."""
    if not tc.enabled():
        raise CollectionHeld("tushare_token_absent")
    canonical = canonical_ticker(ticker)
    trade_day = parse_trade_date(trade_date) if trade_date is not None else None
    frame, resolved = _fetch(query_fn, canonical, trade_day)
    source_rows = (
        [
            {field: _jsonable(raw.get(field)) for field in VENDOR_FIELDS}
            for raw in frame.to_dict(orient="records")
        ]
        if set(VENDOR_FIELDS) <= set(frame.columns)
        else None
    )
    if source_rows is None:
        raise CollectorIntegrityError(
            "cyq_chips response schema differs from the pinned fields"
        )
    source_rows.sort(key=_json_bytes)
    records = normalize_rows(frame, canonical, resolved)
    mass = sum(float(row["percent"]) for row in records)
    return _install_partition(
        root=Path(output_root),
        ticker=canonical,
        trade_day=resolved,
        records=records,
        source_rows_hash=canonical_hash(source_rows),
        percent_mass=mass,
        percent_mass_observation=percent_mass_observation(mass),
        now_utc=(now or datetime.now(timezone.utc)).astimezone(timezone.utc),
    )


def read_partition(
    root: Path, ticker: str, trade_date: date | str
) -> list[dict[str, object]]:
    """Raw distribution rows back out of the private store (research/aggregation input)."""
    path = partition_path(
        Path(root), canonical_ticker(ticker), parse_trade_date(trade_date)
    )
    return pq.ParquetFile(path / "part.parquet").read().to_pylist()


def refresh(
    tickers: Sequence[str],
    *,
    trade_date: date | str | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    max_calls: int = _MAX_CALLS_PER_RUN,
    query_fn: QueryFunction = tc.query,
) -> int:
    """Collect a BOUNDED set of tickers for one session. Gated; returns partitions written.

    Deliberately takes an explicit ticker list and a per-run call cap: cyq_chips costs one
    call per name, so an unbounded sweep would eat the shared premium pool the running daily
    collectors depend on. Bulk accrual is scheduled separately, after Lane B's backfill.
    """
    if not tc.enabled():
        return 0
    written = 0
    for ticker in list(tickers)[:max_calls]:
        try:
            result = collect(
                ticker, trade_date, output_root=output_root, query_fn=query_fn
            )
        except CollectionHeld as exc:
            log.info("chips distribution held for %s (%s)", ticker, exc.reason_code)
            continue
        except CollectorIntegrityError as exc:
            log.warning("chips distribution integrity stop for %s (%s)", ticker, exc)
            continue
        if result.status == "written":
            written += 1
    log.info("chips distribution: wrote %d partitions", written)
    return written


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    import argparse

    parser = argparse.ArgumentParser(
        description="Collect cyq_chips distributions (gated)."
    )
    parser.add_argument(
        "tickers", nargs="+", help="Repo-convention tickers, e.g. 600519.SS"
    )
    parser.add_argument(
        "--trade-date", default=None, help="YYYY-MM-DD (default: latest)"
    )
    args = parser.parse_args()
    return 0 if refresh(args.tickers, trade_date=args.trade_date) else 1


if __name__ == "__main__":
    raise SystemExit(main())
