#!/usr/bin/env python3
"""Reconstruct Prophet plan publication and price-basis chronology.

This is an audit instrument: it never rewrites raw plans or the outcome ledger, and may
only append validated correction-overlay receipts. It joins four independent facts:

* the immutable plan file and its ``asof`` publication/run date;
* the Git commit that first added that plan;
* the creation commit's exact origination receipt (or its legacy ``us_standouts``
  artifact before receipts existed); and
* the ticker's stored daily closes.

The result deliberately separates a plan's publication date from the market session
whose close supplied ``entry``.  Missing or non-unique price evidence stays unknown;
the script never guesses a date merely because it is near the run date.

This instrument also refuses to "correct" ``signal_date`` from a price match. T1,
T2 and T3 have different causal clocks, and old compact boards did not persist all
of them. Price evidence can repair entry/publication chronology; it cannot prove
which tier event originated a plan. Signal corrections require a separate
creation-vintage tier replay and are withheld here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any

import pandas as pd

from engine.prophet_integrity import (
    LEDGER_CORRECTION_SCHEMA,
    PLAN_CORRECTION_SCHEMA,
    PlanCorrectionError,
    load_ledger_corrections,
    load_plan_corrections,
    validate_ledger_correction,
    validate_plan_correction,
)
from lib.nyse_calendar import last_session_on_or_before, sessions_between

PRICE_DIRS = (
    Path("data/baskets/ohlcv"),
    Path("data/stocks"),
    Path("data/yahoo"),
)

ORIGINATION_RECEIPT_DIR = Path("data/prophet/origination_receipts")
ORIGINATION_RECEIPT_SCHEMA = "prophet.origination_receipt/v1"


class OriginationReceiptError(RuntimeError):
    """A receipt-era plan lacks one exact, self-consistent provenance receipt."""


def _git(repo: Path, *args: str, binary: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True,
    )
    return result.stdout if binary else result.stdout.decode("utf-8")


def first_add(repo: Path, relative: str) -> tuple[str, str] | None:
    """Return ``(commit, committed_at)`` for the commit that first added ``relative``."""
    text = str(_git(
        repo, "log", "--diff-filter=A", "--format=%H%x09%cI", "--", relative,
    )).strip()
    if not text:
        return None
    # Defensive: an unusual delete/re-add history can produce more than one A record;
    # the oldest one is the publication origin.
    commit, committed_at = text.splitlines()[-1].split("\t", 1)
    return commit, committed_at


def decimal_tolerance(value: Decimal) -> Decimal:
    """Half of the plan's displayed unit, with a tiny serialization allowance."""
    exponent = value.as_tuple().exponent
    unit = Decimal(1).scaleb(exponent) if exponent < 0 else Decimal(1)
    return unit / Decimal(2) + Decimal("0.000001")


def match_price_basis(
    entry: Decimal,
    closes: Iterable[tuple[date, float]],
    recorded_on: date,
) -> dict[str, Any]:
    """Find the evidenced close date behind ``entry`` without inventing a tie-break.

    A same-recorded-session match is authoritative.  Otherwise exactly one matching
    prior close is required.  Repeated penny prices are common; two prior matches are
    reported as ambiguous rather than choosing whichever one happens to be latest.
    """
    tolerance = decimal_tolerance(entry)
    matches: list[dict[str, Any]] = []
    for session, close in closes:
        if session > recorded_on:
            continue
        close_decimal = Decimal(str(close))
        if abs(close_decimal - entry) <= tolerance:
            matches.append({
                "date": session.isoformat(),
                "close": float(close_decimal),
                "difference": float(abs(close_decimal - entry)),
            })
    matches.sort(key=lambda item: item["date"])
    same_day = [row for row in matches if row["date"] == recorded_on.isoformat()]
    if len(same_day) == 1:
        return {"status": "matched", "match": same_day[0], "matches": matches}
    if len(matches) == 1:
        return {"status": "matched", "match": matches[0], "matches": matches}
    return {
        "status": "ambiguous" if matches else "unmatched",
        "match": None,
        "matches": matches,
    }


def match_latest_price_basis(
    entry: Decimal,
    closes: Iterable[tuple[date, float]],
    recorded_on: date,
) -> dict[str, Any]:
    """Test the latest available close, matching the production originator's rule.

    ``engine.prophet_bridge`` originates ``entry`` from ``entry_signal.spot`` and
    documents that value as the latest-close proxy.  When the exact price-store blob
    from the creation commit is available, older repeated prices are irrelevant: the
    final eligible bar is the only bar the originator could have read.
    """
    eligible = sorted(
        ((session, close) for session, close in closes if session <= recorded_on),
        key=lambda item: item[0],
    )
    if not eligible:
        return {"status": "unmatched", "match": None, "matches": []}
    session, close = eligible[-1]
    difference = abs(Decimal(str(close)) - entry)
    candidate = {
        "date": session.isoformat(),
        "close": float(close),
        "difference": float(difference),
    }
    if difference <= decimal_tolerance(entry):
        return {"status": "matched", "match": candidate, "matches": [candidate]}
    return {"status": "unmatched", "match": None, "matches": [candidate]}


def session_lag(price_basis: date, recorded_on: date) -> int:
    """Completed market sessions after the price bar through the publication day."""
    publication_session = last_session_on_or_before(recorded_on)
    if publication_session <= price_basis:
        return 0
    return len(sessions_between(price_basis + timedelta(days=1), publication_session))


def _load_closes(path: Path) -> list[tuple[date, float]]:
    frame = pd.read_parquet(path)
    return _closes_from_frame(frame)


def _load_closes_blob(blob: bytes) -> list[tuple[date, float]]:
    return _closes_from_frame(pd.read_parquet(BytesIO(blob)))


def _closes_from_frame(frame: pd.DataFrame) -> list[tuple[date, float]]:
    if not isinstance(frame.index, pd.DatetimeIndex):
        date_col = next(
            (column for column in ("date", "Date", "timestamp", "asof") if column in frame),
            None,
        )
        if date_col is None:
            raise ValueError("no date index/column")
        frame = frame.set_index(pd.to_datetime(frame[date_col]))
    close_col = next(
        (column for column in ("close", "Close", "adj_close", "Adj Close") if column in frame),
        None,
    )
    if close_col is None:
        raise ValueError("no close column")
    out: list[tuple[date, float]] = []
    for timestamp, value in frame[close_col].dropna().items():
        out.append((pd.Timestamp(timestamp).date(), float(value)))
    return out


def _blob_at(repo: Path, commit: str, relative: str) -> bytes | None:
    probe = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}:{relative}"],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if probe.returncode != 0:
        return None
    return _git(repo, "show", f"{commit}:{relative}", binary=True)  # type: ignore[return-value]


def _plan_at_creation(repo: Path, commit: str, relative: str) -> dict[str, Any]:
    raw = str(_git(repo, "show", f"{commit}:{relative}"))
    return json.loads(raw, parse_float=Decimal)


def _standouts_at_creation(repo: Path, commit: str) -> tuple[dict[str, Any], bytes]:
    relative = "site/factordata/us_standouts.json"
    blob = _blob_at(repo, commit, relative)
    if blob is None:
        raise RuntimeError(f"creation commit has no {relative}: {commit}")
    return json.loads(blob.decode("utf-8")), blob


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _canonical_date(value: Any) -> str | None:
    """Return a canonical ISO date or null; audit output must never normalize guesses."""
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return value if parsed.isoformat() == value else None


def _strict_json(blob: bytes, *, label: str) -> dict[str, Any]:
    """Decode an object using the workflow's ``allow_nan=False`` contract."""

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant {value}")

    try:
        decoded = json.loads(blob.decode("utf-8"), parse_constant=reject_constant)
    except (UnicodeDecodeError, ValueError, TypeError) as exc:
        raise OriginationReceiptError(f"{label} is not strict JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise OriginationReceiptError(f"{label} must contain a JSON object")
    return decoded


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _safe_relative_path(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise OriginationReceiptError(f"{label} must be a non-empty relative path")
    parsed = PurePosixPath(value)
    if (
        parsed.is_absolute()
        or str(parsed) != value
        or any(part in ("", ".", "..") for part in parsed.parts)
        or "\\" in value
    ):
        raise OriginationReceiptError(f"{label} is not a canonical relative path: {value!r}")
    return value


def _receipt_paths_at(repo: Path, commit: str) -> list[str]:
    directory = ORIGINATION_RECEIPT_DIR.as_posix()
    text = str(_git(
        repo, "ls-tree", "-r", "--name-only", commit, "--", directory,
    ))
    return sorted(
        path for path in text.splitlines()
        if path.startswith(f"{directory}/") and path.endswith(".json")
    )


def _validate_receipt_source(
    receipt: dict[str, Any], *, receipt_path: str,
) -> dict[str, Any]:
    source = receipt.get("source")
    if not isinstance(source, dict):
        raise OriginationReceiptError(f"{receipt_path}: source must be an object")
    required = {
        "path", "sha256", "size_bytes", "board_asof", "source_asof",
        "price_through", "source_basis", "basis", "delayed", "unknown",
        "staleness", "gate_go",
    }
    missing = sorted(required - source.keys())
    if missing:
        raise OriginationReceiptError(
            f"{receipt_path}: source is missing {', '.join(missing)}"
        )

    _safe_relative_path(source["path"], label=f"{receipt_path}: source.path")
    if source["path"] != "site/factordata/us_standouts.json":
        raise OriginationReceiptError(
            f"{receipt_path}: source.path must identify the canonical US board"
        )
    if not _is_sha256(source["sha256"]):
        raise OriginationReceiptError(f"{receipt_path}: source.sha256 is invalid")
    size = source["size_bytes"]
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise OriginationReceiptError(
            f"{receipt_path}: source.size_bytes must be a non-negative integer"
        )
    for field in ("board_asof", "source_asof", "price_through"):
        value = source[field]
        if value is not None and _canonical_date(value) is None:
            raise OriginationReceiptError(
                f"{receipt_path}: source.{field} is not a canonical date"
            )
    if source["price_through"] is None:
        raise OriginationReceiptError(
            f"{receipt_path}: source.price_through must be explicit"
        )
    if source["source_asof"] != source["price_through"]:
        raise OriginationReceiptError(
            f"{receipt_path}: source_asof and price_through disagree"
        )
    if source["source_basis"] != source["basis"]:
        raise OriginationReceiptError(
            f"{receipt_path}: source_basis and basis disagree"
        )
    if not isinstance(source["delayed"], bool) or not isinstance(source["unknown"], bool):
        raise OriginationReceiptError(
            f"{receipt_path}: source delayed/unknown must be booleans"
        )
    if source["gate_go"] is not None and not isinstance(source["gate_go"], bool):
        raise OriginationReceiptError(
            f"{receipt_path}: source.gate_go must be boolean or null"
        )

    staleness = source["staleness"]
    if not isinstance(staleness, dict):
        raise OriginationReceiptError(f"{receipt_path}: source.staleness must be an object")
    mirrored = {
        "price_through": "price_through",
        "basis": "basis",
        "delayed": "delayed",
        "unknown": "unknown",
    }
    for source_field, staleness_field in mirrored.items():
        if (
            staleness_field not in staleness
            or source[source_field] != staleness[staleness_field]
        ):
            raise OriginationReceiptError(
                f"{receipt_path}: source.{source_field} disagrees with "
                f"staleness.{staleness_field}"
            )
    return source


def _validate_receipt_shape(
    receipt: dict[str, Any], *, receipt_path: str,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if receipt.get("schema") != ORIGINATION_RECEIPT_SCHEMA:
        raise OriginationReceiptError(
            f"{receipt_path}: schema must be {ORIGINATION_RECEIPT_SCHEMA}"
        )
    receipt_id = receipt.get("receipt_id")
    if not isinstance(receipt_id, str) or not receipt_id:
        raise OriginationReceiptError(f"{receipt_path}: receipt_id is missing")
    if PurePosixPath(receipt_path).name != f"{receipt_id}.json":
        raise OriginationReceiptError(
            f"{receipt_path}: filename does not match receipt_id {receipt_id!r}"
        )
    source = _validate_receipt_source(receipt, receipt_path=receipt_path)

    plan_ids = receipt.get("originated_plan_ids")
    originations = receipt.get("originations")
    if (
        not isinstance(plan_ids, list)
        or any(not isinstance(plan_id, str) or not plan_id for plan_id in plan_ids)
    ):
        raise OriginationReceiptError(
            f"{receipt_path}: originated_plan_ids must be a list of plan IDs"
        )
    if plan_ids != sorted(set(plan_ids)):
        raise OriginationReceiptError(
            f"{receipt_path}: originated_plan_ids must be sorted and unique"
        )
    if not isinstance(originations, list):
        raise OriginationReceiptError(f"{receipt_path}: originations must be a list")

    by_id: dict[str, dict[str, Any]] = {}
    for position, origin in enumerate(originations, start=1):
        label = f"{receipt_path}: originations[{position}]"
        if not isinstance(origin, dict):
            raise OriginationReceiptError(f"{label} must be an object")
        required = {
            "plan_id", "asset", "formation_date", "plan_path", "plan_sha256",
            "admission_rank", "board_row_sha256", "board_row",
        }
        missing = sorted(required - origin.keys())
        if missing:
            raise OriginationReceiptError(f"{label} is missing {', '.join(missing)}")
        plan_id = origin["plan_id"]
        if not isinstance(plan_id, str) or not plan_id or plan_id in by_id:
            raise OriginationReceiptError(f"{label}.plan_id is invalid or duplicated")
        _safe_relative_path(origin["plan_path"], label=f"{label}.plan_path")
        if not _is_sha256(origin["plan_sha256"]):
            raise OriginationReceiptError(f"{label}.plan_sha256 is invalid")
        rank = origin["admission_rank"]
        if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
            raise OriginationReceiptError(
                f"{label}.admission_rank must be a positive integer"
            )
        board_row = origin["board_row"]
        if not isinstance(board_row, dict):
            raise OriginationReceiptError(f"{label}.board_row must be an object")
        try:
            canonical_row = json.dumps(
                board_row, sort_keys=True, separators=(",", ":"), allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise OriginationReceiptError(
                f"{label}.board_row is not canonical JSON: {exc}"
            ) from exc
        if not _is_sha256(origin["board_row_sha256"]):
            raise OriginationReceiptError(f"{label}.board_row_sha256 is invalid")
        if hashlib.sha256(canonical_row).hexdigest() != origin["board_row_sha256"]:
            raise OriginationReceiptError(f"{label}.board_row hash mismatch")
        by_id[plan_id] = origin

    if plan_ids != list(by_id):
        raise OriginationReceiptError(
            f"{receipt_path}: originated_plan_ids and originations disagree"
        )
    selection = receipt.get("selection")
    if isinstance(selection, dict) and "originated_count" in selection:
        count = selection["originated_count"]
        if isinstance(count, bool) or not isinstance(count, int) or count != len(by_id):
            raise OriginationReceiptError(
                f"{receipt_path}: selection.originated_count is inconsistent"
            )
    return source, by_id


def _receipt_board_at_creation(
    repo: Path,
    commit: str,
    *,
    relative_plan_path: str,
    plan: dict[str, Any],
) -> dict[str, Any] | None:
    """Resolve one atomic first-add receipt, or return null for a legacy commit.

    Once the receipt directory exists in a creation commit, absence, ambiguity, or any
    malformed receipt is a provenance failure.  Only commits predating the directory
    retain the standouts-file compatibility path.
    """
    receipt_paths = _receipt_paths_at(repo, commit)
    if not receipt_paths:
        return None

    plan_id = str(plan.get("id") or "")
    matches: list[dict[str, Any]] = []
    for receipt_path in receipt_paths:
        blob = _git(repo, "show", f"{commit}:{receipt_path}", binary=True)
        if not isinstance(blob, bytes):  # pragma: no cover - _git(binary=True) contract
            raise OriginationReceiptError(f"{receipt_path}: could not read receipt bytes")
        receipt = _strict_json(blob, label=receipt_path)
        source, origins = _validate_receipt_shape(receipt, receipt_path=receipt_path)
        origin = origins.get(plan_id)
        if origin is not None:
            matches.append({
                "path": receipt_path,
                "sha256": hashlib.sha256(blob).hexdigest(),
                "source": source,
                "origin": origin,
            })

    if len(matches) != 1:
        raise OriginationReceiptError(
            f"{commit}: expected exactly one origination receipt for {plan_id}, "
            f"found {len(matches)}"
        )
    matched = matches[0]
    origin = matched["origin"]
    if origin["plan_path"] != relative_plan_path:
        raise OriginationReceiptError(
            f"{matched['path']}: plan_path {origin['plan_path']!r} does not match "
            f"first-added path {relative_plan_path!r}"
        )
    plan_blob = _blob_at(repo, commit, relative_plan_path)
    if plan_blob is None:
        raise OriginationReceiptError(
            f"{matched['path']}: first-add plan blob is missing"
        )
    if hashlib.sha256(plan_blob).hexdigest() != origin["plan_sha256"]:
        raise OriginationReceiptError(f"{matched['path']}: plan blob hash mismatch")
    if str(origin.get("asset") or "") != str(plan.get("asset") or ""):
        raise OriginationReceiptError(f"{matched['path']}: plan asset mismatch")
    if origin.get("formation_date") != plan.get("formation_date"):
        raise OriginationReceiptError(f"{matched['path']}: plan formation_date mismatch")
    board_row = origin["board_row"]
    if str(board_row.get("ticker") or "") != str(plan.get("asset") or ""):
        raise OriginationReceiptError(f"{matched['path']}: board row asset mismatch")

    source = matched["source"]
    # This is intentionally a minimal reconstruction: the receipt freezes the one row
    # that originated this plan and the exact source-clock metadata.  Reading the full
    # standouts blob from the selective first-add commit could substitute older bytes.
    matched["board"] = {
        "as_of": source["board_asof"],
        "source_asof": source["source_asof"],
        "staleness": source["staleness"],
        "gate_go": source["gate_go"],
        "buy": [board_row],
    }
    return matched


def audit_plan(repo: Path, plan_path: Path) -> dict[str, Any]:
    relative = plan_path.relative_to(repo).as_posix()
    added = first_add(repo, relative)
    if added is None:
        raise RuntimeError(f"plan has no first-add commit: {relative}")
    commit, committed_at = added
    plan = _plan_at_creation(repo, commit, relative)
    recorded_on = date.fromisoformat(str(plan["asof"])[:10])
    receipt = _receipt_board_at_creation(
        repo, commit, relative_plan_path=relative, plan=plan,
    )
    standouts_blob: bytes | None
    if receipt is None:
        standouts, standouts_blob = _standouts_at_creation(repo, commit)
    else:
        standouts = receipt["board"]
        standouts_blob = None
    asset = str(plan.get("asset") or "")
    board_row = next(
        (row for row in (standouts.get("buy") or []) if str(row.get("ticker")) == asset),
        {},
    )
    board_signal = board_row.get("signal") or {}
    board_last_marker = board_signal.get("last") or {}
    board_signal_tier = str(board_signal.get("tier_cascade") or "") or None
    board_source_marker_date = _canonical_date(board_last_marker.get("date"))
    publication_session = last_session_on_or_before(recorded_on)
    board_staleness = standouts.get("staleness") or {}
    board_price_basis = _canonical_date(board_staleness.get("price_through"))
    embedded_mixed_vintage = bool(
        board_staleness.get("inputs", {}).get("panel", {}).get(
            "mixed_vintage"
        )
    )
    # A Saturday publication backed by Friday's board is current, not mixed-vintage.
    # ``as_of`` is wrapper/publication metadata. Compare the ranked-price watermark to
    # the last completed session, then preserve the embedded panel warning.
    mixed_vintage = embedded_mixed_vintage or bool(
        board_price_basis != publication_session.isoformat()
    )

    source: Path | None = None
    price_read: dict[str, Any]
    source_hash: str | None = None
    source_error: str | None = None
    source_scope: str | None = None
    source_last_session: str | None = None
    source_reads: list[tuple[Path, bytes, list[tuple[date, float]], dict[str, Any]]] = []
    if receipt is None:
        for directory in PRICE_DIRS:
            relative_source = (directory / f"{asset}.parquet").as_posix()
            blob = _blob_at(repo, commit, relative_source)
            if blob is None:
                continue
            try:
                closes = _load_closes_blob(blob)
                read = match_latest_price_basis(Decimal(plan["entry"]), closes, recorded_on)
                source_reads.append(
                    (repo / directory / f"{asset}.parquet", blob, closes, read)
                )
            except Exception as exc:  # noqa: BLE001 - parquet engines vary by store
                source_error = f"{relative_source}: {exc}"

    matched_sources = [item for item in source_reads if item[3].get("match")]
    matched_dates = {item[3]["match"]["date"] for item in matched_sources}
    if receipt is not None:
        board_spot = (board_row.get("entry_signal") or {}).get("spot")
        try:
            board_difference = abs(Decimal(str(board_spot)) - Decimal(plan["entry"]))
        except (ArithmeticError, KeyError, TypeError, ValueError) as exc:
            raise OriginationReceiptError(
                f"{receipt['path']}: receipt row has no comparable entry spot"
            ) from exc
        if board_difference > decimal_tolerance(Decimal(plan["entry"])):
            raise OriginationReceiptError(
                f"{receipt['path']}: receipt row spot does not match the plan entry"
            )
        source_metadata = receipt["source"]
        source = repo / source_metadata["path"]
        source_hash = source_metadata["sha256"]
        source_scope = "origination_receipt_board_contract"
        source_last_session = board_price_basis
        candidate = {
            "date": board_price_basis,
            "close": float(Decimal(str(board_spot))),
            "difference": float(board_difference),
        }
        price_read = {
            "status": "matched_origination_receipt",
            "match": candidate,
            "matches": [candidate],
        }
    elif matched_sources and len(matched_dates) == 1:
        source, blob, closes, price_read = matched_sources[0]
        source_hash = hashlib.sha256(blob).hexdigest()
        source_scope = "creation_commit"
        eligible_dates = [session for session, _ in closes if session <= recorded_on]
        source_last_session = max(eligible_dates).isoformat() if eligible_dates else None
    elif matched_sources:
        price_read = {
            "status": "ambiguous",
            "match": None,
            "matches": [item[3]["match"] for item in matched_sources],
        }
        source_error = "creation-commit price stores disagree on the latest close date"
    else:
        board_spot = (board_row.get("entry_signal") or {}).get("spot")
        board_difference: Decimal | None = None
        try:
            board_difference = abs(Decimal(str(board_spot)) - Decimal(plan["entry"]))
        except (ArithmeticError, KeyError, TypeError, ValueError):
            board_difference = None
        # The coherent creation board is exact pipeline provenance and therefore wins
        # over a CURRENT store whose historical bars may since have been adjusted.
        if (
            not mixed_vintage
            and board_price_basis == publication_session.isoformat()
            and board_difference is not None
            and board_difference <= decimal_tolerance(Decimal(plan["entry"]))
        ):
            source = repo / "site/factordata/us_standouts.json"
            if standouts_blob is None:  # pragma: no cover - receipt handled above
                raise RuntimeError("legacy board bytes unexpectedly unavailable")
            source_hash = hashlib.sha256(standouts_blob).hexdigest()
            source_scope = "creation_board_contract"
            source_last_session = board_price_basis
            candidate = {
                "date": board_price_basis,
                "close": float(Decimal(str(board_spot))),
                "difference": float(board_difference),
            }
            price_read = {
                "status": "matched_board_contract",
                "match": candidate,
                "matches": [candidate],
            }
        else:
            # A current store is weaker evidence (its old bars may have adjusted).
            # It is useful for diagnosis, but correction policy quarantines an unknown
            # or lagged mixed-vintage row rather than treating this fallback as proof.
            source = next(
                (repo / directory / f"{asset}.parquet" for directory in PRICE_DIRS
                 if (repo / directory / f"{asset}.parquet").exists()),
                None,
            )
            if source is None:
                price_read = {"status": "source_absent", "match": None, "matches": []}
            else:
                try:
                    closes = _load_closes(source)
                    price_read = match_latest_price_basis(
                        Decimal(plan["entry"]), closes, recorded_on
                    )
                    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
                    source_scope = "current_fallback"
                    eligible_dates = [session for session, _ in closes if session <= recorded_on]
                    source_last_session = max(eligible_dates).isoformat() if eligible_dates else None
                except Exception as exc:  # noqa: BLE001 - diagnostic fallback
                    price_read = {"status": "source_unreadable", "match": None, "matches": []}
                    source_error = str(exc)

    match = price_read.get("match")
    lag: int | None = None
    if match:
        lag = session_lag(date.fromisoformat(match["date"]), recorded_on)
    if source_scope == "current_fallback":
        integrity = "price_basis_unverified_current_fallback"
    elif lag is None:
        integrity = "price_basis_unknown"
    elif lag > 0:
        integrity = "stale_price_basis"
    elif mixed_vintage:
        integrity = "price_current_board_mixed_vintage"
    else:
        integrity = "price_current"
    if board_signal_tier in {"T1", "T2", "T3"}:
        admission_integrity = "actionable_tier_proven"
    elif board_signal_tier == "T4":
        admission_integrity = "non_actionable_t4"
    else:
        admission_integrity = "admission_tier_unknown"
    price_quarantine = integrity in {
        "price_basis_unknown",
        "price_basis_unverified_current_fallback",
        "stale_price_basis",
    }
    admission_quarantine = admission_integrity != "actionable_tier_proven"

    audited = {
        "plan_id": plan.get("id"),
        "asset": asset,
        "recorded_at": recorded_on.isoformat(),
        "first_commit": commit,
        "first_committed_at": committed_at,
        "board_as_of": standouts.get("as_of"),
        "board_price_basis": board_price_basis,
        "board_mixed_vintage": mixed_vintage,
        "board_row_signal_asof": board_signal.get("asof"),
        "board_row_signal_tier": board_signal_tier,
        "board_row_source_marker_date": board_source_marker_date,
        "board_row_source_marker_type": board_last_marker.get("type"),
        "board_row_spot": (board_row.get("entry_signal") or {}).get("spot"),
        "published_signal_date": plan.get("signal_date"),
        "published_entry_date": plan.get("entry_date"),
        "published_entry": plan.get("entry"),
        "price_source": source.relative_to(repo).as_posix() if source else None,
        "price_source_scope": source_scope,
        "price_source_last_session": source_last_session,
        "price_source_sha256": source_hash,
        "price_source_error": source_error,
        "price_match_status": price_read.get("status"),
        "price_matches": price_read.get("matches"),
        "price_basis_date": match.get("date") if match else None,
        "market_session_lag": lag,
        "integrity_status": integrity,
        "admission_integrity": admission_integrity,
        "quarantine_recommended": price_quarantine or admission_quarantine,
    }
    if receipt is not None:
        audited.update({
            "origination_receipt_path": receipt["path"],
            "origination_receipt_sha256": receipt["sha256"],
        })
    return _jsonable(audited)


def build_report(repo: Path, start: date, end: date) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for plan_path in sorted((repo / "site/prophet/plans").glob("*.json")):
        with plan_path.open(encoding="utf-8") as handle:
            plan = json.load(handle)
        recorded = plan.get("asof")
        if not recorded:
            continue
        recorded_on = date.fromisoformat(str(recorded)[:10])
        if start <= recorded_on <= end:
            rows.append(audit_plan(repo, plan_path))
    counts: dict[str, int] = {}
    admission_counts: dict[str, int] = {}
    for row in rows:
        key = str(row["integrity_status"])
        counts[key] = counts.get(key, 0) + 1
        admission_key = str(row["admission_integrity"])
        admission_counts[admission_key] = admission_counts.get(admission_key, 0) + 1
    return {
        "schema": "prophet.plan_chronology_audit/v1",
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "plan_count": len(rows),
        "integrity_counts": dict(sorted(counts.items())),
        "admission_integrity_counts": dict(sorted(admission_counts.items())),
        "quarantine_recommended_count": sum(
            1 for row in rows if row["quarantine_recommended"]
        ),
        "signal_date_correction_policy": {
            "corrections_emitted": 0,
            "status": "withheld_without_tier_causal_replay",
            "reason": (
                "price matching proves price_basis_date, not a T1/T2/T3 event; "
                "legacy plan identity and published signal labels remain immutable"
            ),
        },
        "rows": rows,
    }


def _correction_evidence(row: dict[str, Any], *, audit_receipt: str) -> dict[str, Any]:
    evidence = {
        "audit_receipt": audit_receipt,
        "first_commit": row["first_commit"],
        "first_committed_at": row["first_committed_at"],
        "board_as_of": row["board_as_of"],
        "board_mixed_vintage": row["board_mixed_vintage"],
        "board_row_signal_tier": row.get("board_row_signal_tier"),
        "board_row_source_marker_date": row.get("board_row_source_marker_date"),
        "board_row_source_marker_type": row.get("board_row_source_marker_type"),
        "price_source": row["price_source"],
        "price_source_scope": row["price_source_scope"],
        "price_source_sha256": row["price_source_sha256"],
        "price_match_status": row["price_match_status"],
        "market_session_lag": row["market_session_lag"],
        "admission_integrity": row.get("admission_integrity"),
    }
    receipt_path = row.get("origination_receipt_path")
    receipt_hash = row.get("origination_receipt_sha256")
    if receipt_path is not None or receipt_hash is not None:
        if not receipt_path or not receipt_hash:
            raise OriginationReceiptError(
                "receipt-backed audit row must carry both receipt path and hash"
            )
        evidence.update({
            "origination_receipt_path": receipt_path,
            "origination_receipt_sha256": receipt_hash,
        })
    return evidence


def _integrity_disposition(row: dict[str, Any]) -> tuple[str, str]:
    admission = str(row.get("admission_integrity") or "")
    if admission == "non_actionable_t4":
        return (
            "quarantined",
            ("creation-vintage evidence shows a projected T4 observation, which was "
            "not an actionable fired event and must not have originated a live plan"),
        )
    if admission == "admission_tier_unknown":
        return (
            "quarantined",
            ("creation-vintage board lacks a persisted causal admission tier; the "
            "legacy signal clock cannot be validated without guessing"),
        )
    status = str(row["integrity_status"])
    if status == "stale_price_basis":
        return (
            "quarantined",
            ("outage-era plan was published after its entry-price session; "
            "the hypothetical timely plan geometry cannot be reconstructed"),
        )
    if status in {"price_basis_unknown", "price_basis_unverified_current_fallback"}:
        return (
            "quarantined",
            ("mixed-vintage outage plan lacks an exact creation-vintage price source; "
            "the entry clock cannot be corrected without guessing"),
        )
    if status == "price_current_board_mixed_vintage":
        return (
            "audited_mixed_vintage",
            ("entry price matches the publication session, but board inputs were "
            "explicitly mixed-vintage"),
        )
    return (
        "audited_current",
        ("creation-vintage evidence confirms a current entry-price session and a "
        "session-coherent board"),
    )


def build_plan_corrections(
    repo: Path,
    report: dict[str, Any],
    *,
    corrected_at: date,
    audit_receipt: str,
) -> list[dict[str, Any]]:
    """Build deterministic append-only corrections from the chronology receipt."""
    corrections: list[dict[str, Any]] = []
    for audited in report["rows"]:
        plan_id = str(audited["plan_id"])
        raw = json.loads(
            (repo / "site/prophet/plans" / f"{plan_id}.json").read_text(
                encoding="utf-8"
            )
        )
        evidence = _correction_evidence(audited, audit_receipt=audit_receipt)
        status, reason = _integrity_disposition(audited)
        changes: list[tuple[str, Any, str]] = [
            (
                "formation_date",
                raw.get("signal_date"),
                ("legacy plan ID and published signal_date prove the immutable "
                "base-formation anchor"),
            ),
            (
                "signal_date_basis",
                "legacy_formation_alias",
                ("the legacy plan published signal_date as its ID formation anchor; "
                "the creation board did not carry a tier-native event-date contract"),
            ),
            (
                "recorded_at",
                str(raw.get("asof"))[:10],
                "raw plan asof and its first-add commit prove the publication run date",
            ),
            ("integrity_status", status, "chronology audit disposition"),
            ("integrity_reason", reason, "chronology audit disposition"),
        ]
        if audited.get("board_row_signal_tier") in {"T1", "T2", "T3", "T4"}:
            changes.append((
                "signal_tier",
                audited["board_row_signal_tier"],
                "exact creation-commit standouts row proves the admission tier",
            ))
        if audited.get("board_row_source_marker_date"):
            changes.append((
                "source_marker_date",
                audited["board_row_source_marker_date"],
                ("exact creation-commit standouts row preserves the legacy marker label "
                "without treating it as the tier event date"),
            ))
        if (
            audited.get("price_basis_date")
            and audited.get("price_source_scope") != "current_fallback"
        ):
            changes.extend([
                (
                    "price_basis_date",
                    audited["price_basis_date"],
                    "creation-vintage price evidence identifies the close behind entry",
                ),
                (
                    "entry_date",
                    audited["price_basis_date"],
                    "compatibility entry clock mirrors the evidenced price-basis session",
                ),
            ])
        for field, new_value, basis in changes:
            corrections.append({
                "schema": PLAN_CORRECTION_SCHEMA,
                "id": f"{plan_id}:{field}:{corrected_at.strftime('%Y%m%d')}",
                "corrects_id": plan_id,
                "field": field,
                "old_value": raw.get(field),
                "new_value": new_value,
                "basis": basis,
                "corrected_at": corrected_at.isoformat(),
                "evidence": evidence,
            })
    return sorted(corrections, key=lambda row: (row["corrects_id"], row["field"]))


def build_ledger_corrections(
    repo: Path,
    report: dict[str, Any],
    *,
    corrected_at: date,
    audit_receipt: str,
) -> list[dict[str, Any]]:
    """Correct dates on intersecting terminal rows without mutating ledger.jsonl."""
    audited_by_id = {
        str(row["plan_id"]): row for row in report["rows"]
        if (
            row.get("quarantine_recommended")
            and row.get("price_basis_date")
            and row.get("price_source_scope") != "current_fallback"
        )
    }
    corrections: list[dict[str, Any]] = []
    ledger_path = repo / "data/prophet/ledger.jsonl"
    for raw_line in ledger_path.read_text(encoding="utf-8").splitlines():
        text = raw_line.strip()
        if not text or text.startswith("#"):
            continue
        ledger_row = json.loads(text)
        plan_id = str(ledger_row.get("id") or "")
        audited = audited_by_id.get(plan_id)
        if audited is None:
            continue
        plan = json.loads(
            (repo / "site/prophet/plans" / f"{plan_id}.json").read_text(
                encoding="utf-8"
            )
        )
        evidence = _correction_evidence(audited, audit_receipt=audit_receipt)
        evidence["ledger_row_sha256"] = hashlib.sha256(
            text.encode("utf-8")
        ).hexdigest()
        _, plan_reason = _integrity_disposition(audited)
        reason = (
            f"{plan_reason}; proven date facts are projected but this terminal "
            "outcome remains excluded from record claims"
        )
        changes = [
            ("formation_date", plan.get("signal_date")),
            ("signal_date_basis", "legacy_formation_alias"),
            ("recorded_at", str(plan.get("asof"))[:10]),
            ("price_basis_date", audited["price_basis_date"]),
            ("entry_date", audited["price_basis_date"]),
            ("integrity_status", "quarantined"),
            ("integrity_reason", reason),
        ]
        if audited.get("board_row_signal_tier") in {"T1", "T2", "T3", "T4"}:
            changes.append(("signal_tier", audited["board_row_signal_tier"]))
        if audited.get("board_row_source_marker_date"):
            changes.append((
                "source_marker_date", audited["board_row_source_marker_date"]
            ))
        for field, new_value in changes:
            corrections.append({
                "schema": LEDGER_CORRECTION_SCHEMA,
                "id": f"{plan_id}:ledger:{field}:{corrected_at.strftime('%Y%m%d')}",
                "corrects_id": plan_id,
                "field": field,
                "old_value": ledger_row.get(field),
                "new_value": new_value,
                "basis": "creation-vintage chronology audit; raw terminal row remains immutable",
                "corrected_at": corrected_at.isoformat(),
                "evidence": evidence,
            })
    return sorted(corrections, key=lambda row: (row["corrects_id"], row["field"]))


def _jsonl(rows: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)


def _append_correction_rows(
    path: Path,
    rows: list[dict[str, Any]],
    *,
    loader: Any,
    validator: Any,
) -> int:
    """Append only genuinely new correction targets; never truncate prior evidence.

    An exact rerun is idempotent. Reusing a correction ID with different content, or
    attempting to revise an existing ``(corrects_id, field)`` target, fails closed: the
    v1 contract has no hidden last-write-wins or supersession semantics.
    """
    existing = loader(path) if path.exists() and path.stat().st_size else []
    by_id = {str(row["id"]): row for row in existing}
    by_target = {
        (str(row["corrects_id"]), str(row["field"])): row for row in existing
    }
    pending: list[dict[str, Any]] = []
    pending_ids: set[str] = set()
    pending_targets: set[tuple[str, str]] = set()
    for position, row in enumerate(rows, start=1):
        validator(row, line=position)
        correction_id = str(row["id"])
        target = (str(row["corrects_id"]), str(row["field"]))
        if correction_id in pending_ids:
            raise PlanCorrectionError(
                f"generated duplicate correction id {correction_id}"
            )
        if target in pending_targets:
            raise PlanCorrectionError(
                f"generated duplicate correction target {target[0]}.{target[1]}"
            )
        pending_ids.add(correction_id)
        pending_targets.add(target)
        prior_id = by_id.get(correction_id)
        if prior_id is not None:
            if prior_id != row:
                raise PlanCorrectionError(
                    f"correction id {correction_id} already exists with different content"
                )
            continue
        prior_target = by_target.get(target)
        if prior_target is not None:
            raise PlanCorrectionError(
                f"correction target {target[0]}.{target[1]} already exists as "
                f"{prior_target['id']}"
            )
        pending.append(row)

    if not pending:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    prefix = ""
    if path.exists() and path.stat().st_size:
        with path.open("rb") as handle:
            handle.seek(-1, 2)
            if handle.read(1) != b"\n":
                prefix = "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(prefix + _jsonl(pending))
    # Re-load after the append so a partial/malformed write cannot be reported as success.
    loader(path)
    return len(pending)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--from", dest="start", type=date.fromisoformat, required=True)
    parser.add_argument("--to", dest="end", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--plan-corrections-output", type=Path)
    parser.add_argument("--ledger-corrections-output", type=Path)
    parser.add_argument(
        "--corrected-at", type=date.fromisoformat, default=date.today()  # noqa: DTZ011
    )
    args = parser.parse_args()
    report = build_report(args.repo.resolve(), args.start, args.end)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    receipt = (
        args.output.relative_to(args.repo).as_posix()
        if args.output and args.output.is_relative_to(args.repo)
        else str(args.output or "stdout")
    )
    if args.plan_corrections_output:
        _append_correction_rows(
            args.plan_corrections_output,
            build_plan_corrections(
                args.repo.resolve(), report, corrected_at=args.corrected_at,
                audit_receipt=receipt,
            ),
            loader=load_plan_corrections,
            validator=validate_plan_correction,
        )
    if args.ledger_corrections_output:
        _append_correction_rows(
            args.ledger_corrections_output,
            build_ledger_corrections(
                args.repo.resolve(), report, corrected_at=args.corrected_at,
                audit_receipt=receipt,
            ),
            loader=load_ledger_corrections,
            validator=validate_ledger_correction,
        )


if __name__ == "__main__":
    main()
