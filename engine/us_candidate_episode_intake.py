"""Canonical, source-specific intake for B1 candidate-episode observations.

This module only normalizes producer records for ``us_candidate_episode``.  It never
re-ranks, re-gates, or owns an episode lifecycle; reconciliation remains the sole writer.
"""
from __future__ import annotations

import json
from io import BytesIO
from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Callable, Mapping

import numpy as np
import pandas as pd

from engine.session_digest import session_window_et
from engine.stock_identity.fingerprint import spec_hash
from engine.us_candidate_episode import canonical_json
from lib.dataos.identity import IssuerMaster, VendorAliasTable


TURN_WATCH_SCHEMA = "prophet.candidate_episode_input.turn_watch/v1"
IDENTITY_SCHEMA = "stock_identity.fingerprint_spec.v1"


@dataclass(frozen=True)
class IdentitySpine:
    aliases: VendorAliasTable
    issuers: IssuerMaster
    source_receipts: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True)
class IntakeBatch:
    observations: tuple[dict[str, object], ...]
    suppressions: tuple[dict[str, object], ...]
    source_receipts: tuple[dict[str, object], ...]


def _file_receipt(path: Path, payload: bytes) -> dict[str, object]:
    return {"path": str(path), "sha256": "sha256:" + sha256(payload).hexdigest()}


def _records_snapshot(path: Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    payload = path.read_bytes()
    rows = pd.read_parquet(BytesIO(payload)).to_dict("records")
    return [_json_safe(dict(row)) for row in rows], _file_receipt(path, payload)


def _json_safe(value: object) -> object:
    """Normalize pandas scalar nulls and times before any canonical JSON boundary."""
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, float) and not pd.notna(value):
        return None
    return value


def load_identity_spine(data_root: Path) -> IdentitySpine:
    """Load the one Data OS alias/issuer reader pair; never recreate identity locally."""
    reference = Path(data_root) / "reference"
    alias_rows, alias_receipt = _records_snapshot(reference / "vendor_aliases.parquet")
    issuer_rows, issuer_receipt = _records_snapshot(reference / "security_master.parquet")
    aliases = VendorAliasTable.from_records(alias_rows)
    issuers = IssuerMaster.from_records(issuer_rows)
    return IdentitySpine(
        aliases=aliases,
        issuers=issuers,
        source_receipts=(
            {"source": "identity", **alias_receipt},
            {"source": "identity", **issuer_receipt},
        ),
    )


def _session(value: object) -> date | None:
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except (TypeError, ValueError):
        return None


def _close(value: object) -> str | None:
    session = _session(value)
    if session is None:
        return None
    return session_window_et(session)[1].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _timestamp(value: object, session: object) -> str | None:
    if isinstance(value, str):
        if len(value) == 10 and _session(value) is not None:
            return _close(value)
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return None
            return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return None
    return _close(session)


def _receipt(value: object) -> str | None:
    text = str(value or "")
    if text.startswith("sha256:") and len(text) == 71 and all(c in "0123456789abcdef" for c in text[7:]):
        return text
    return None


def _source_id(source: str, row: Mapping[str, object]) -> str:
    return f"{source}:" + sha256(canonical_json(dict(row)).encode("utf-8")).hexdigest()


def _suppression(source: str, schema: str, source_event_id: str, receipt: str | None,
                 ticker: object, reason: str, *, session: object = None,
                 security_id: str | None = None) -> dict[str, object]:
    return {
        "schema": "prophet.candidate_episode_suppression/v1",
        "source_system": source,
        "source_schema": schema,
        "source_event_id": source_event_id,
        "source_receipt": receipt,
        "ticker_at_observation": str(ticker or "") or None,
        "security_id": security_id,
        "observation_session": str(session or "")[:10] or None,
        "reason": reason,
    }


def _identity(spine: IdentitySpine, ticker: object, on: object) -> tuple[str | None, str | None]:
    session = _session(on)
    if session is None:
        return None, None
    security = spine.aliases.resolve("membership", str(ticker or ""), on=session)
    return security, spine.issuers.issuer_of_security(security) if security else None


def _observation(*, source: str, schema: str, source_event_id: str, receipt: str,
                 ticker: object, session: object, spine: IdentitySpine,
                 intake_class: str, anchor: dict[str, object] | None = None,
                 occurred_at: object = None, known_at: object = None,
                 expert_event_id: str | None = None) -> tuple[dict[str, object] | None, str | None]:
    security, company = _identity(spine, ticker, session)
    if security is None:
        return None, "IDENTITY_UNRESOLVED"
    if company is None:
        return None, "ISSUER_UNRESOLVED"
    occurred = _timestamp(occurred_at, session)
    known = _timestamp(known_at, session)
    if occurred is None or known is None:
        return None, "MALFORMED_RECEIPT"
    result: dict[str, object] = {
        "security_id": security, "company_id": company,
        "ticker_at_observation": str(ticker), "identity_epoch": "epoch_0",
        "identity_epoch_state": "provisional", "identity_spec_schema": IDENTITY_SCHEMA,
        "identity_spec_hash": spec_hash(), "anchor": anchor, "intake_class": intake_class,
        "occurred_at": occurred, "known_at": known, "source_system": source,
        "source_schema": schema, "source_event_id": source_event_id, "source_receipt": receipt,
    }
    if expert_event_id is not None:
        result["expert_event_id"] = expert_event_id
    return result, None


def turn_watch_observations(path: Path, spine: IdentitySpine) -> IntakeBatch:
    """Normalize full private TURN WATCH rows; only this source provides a structural anchor."""
    source, schema = "turn_watch", TURN_WATCH_SCHEMA
    try:
        payload = Path(path).read_bytes()
    except OSError:
        return IntakeBatch((), (), ({"source": source, "status": "degraded", "reason": "UNREADABLE_SOURCE"},))
    file_receipts = [_file_receipt(Path(path), payload)]
    try:
        document = json.loads(payload)
    except json.JSONDecodeError:
        return IntakeBatch((), (), ({"source": source, "status": "degraded", "reason": "MALFORMED_SOURCE",
                                     "files": file_receipts},))
    if not isinstance(document, Mapping):
        return IntakeBatch((), (), ({"source": source, "status": "degraded", "reason": "MALFORMED_SOURCE",
                                     "files": file_receipts},))
    rows = document.get("rows")
    digest = document.get("content_sha256")
    receipt = _receipt(f"sha256:{digest}" if isinstance(digest, str) else None)
    if document.get("schema") != TURN_WATCH_SCHEMA or not isinstance(rows, list):
        return IntakeBatch((), (), ({"source": source, "status": "degraded", "reason": "MALFORMED_SOURCE",
                                     "files": file_receipts},))
    expected_digest = sha256(canonical_json({key: value for key, value in document.items()
                                              if key != "content_sha256"}).encode("utf-8")).hexdigest()
    if receipt is None or digest != expected_digest:
        suppressions = tuple(
            _suppression(source, schema, _source_id(source, {"data_session": document.get("data_session"),
                                                               "row": dict(row) if isinstance(row, Mapping) else {}}),
                         None, row.get("ticker") if isinstance(row, Mapping) else None,
                         "MALFORMED_RECEIPT", session=document.get("data_session"))
            for row in rows
        )
        return IntakeBatch((), suppressions,
                           ({"source": source, "status": "degraded", "reason": "MALFORMED_RECEIPT",
                             "files": file_receipts},))
    observations: list[dict[str, object]] = []
    suppressions: list[dict[str, object]] = []
    session = document.get("data_session")
    for raw in rows:
        row = dict(raw) if isinstance(raw, Mapping) else {}
        event_id = _source_id(source, {"data_session": session, "row": row})
        ticker = row.get("ticker")
        fired = row.get("triggers")
        if not isinstance(fired, Mapping) or not any(isinstance(v, Mapping) and v.get("fired")
                                                     for v in fired.values()):
            suppressions.append(_suppression(source, schema, event_id, receipt, ticker, "MISSING_TRIGGER",
                                              session=session))
            continue
        if any(isinstance(v, Mapping) and v.get("fired") and not v.get("evaluated", False)
               for v in fired.values()):
            suppressions.append(_suppression(source, schema, event_id, receipt, ticker, "UNEVALUATED_TRIGGER",
                                              session=session))
            continue
        trigger_clocks = []
        for trigger in fired.values():
            if not isinstance(trigger, Mapping) or not trigger.get("fired"):
                continue
            trigger_clock = _close(trigger.get("last_date"))
            if trigger_clock is not None:
                trigger_clocks.append(trigger_clock)
        if not trigger_clocks:
            suppressions.append(_suppression(source, schema, event_id, receipt, ticker,
                                              "MALFORMED_RECEIPT", session=session))
            continue
        trigger_clock = min(trigger_clocks)
        reset = row.get("reset")
        if not isinstance(reset, Mapping) or reset.get("reset_low") is None or not reset.get("reset_low_date"):
            suppressions.append(_suppression(source, schema, event_id, receipt, ticker, "MISSING_RESET_LOW",
                                              session=session))
            continue
        anchor_time = _close(reset.get("reset_low_date"))
        if anchor_time is None:
            suppressions.append(_suppression(source, schema, event_id, receipt, ticker, "MALFORMED_RECEIPT",
                                              session=session))
            continue
        anchor = {"kind": "turn_watch_reset_low", "time": anchor_time,
                  "price": reset["reset_low"], "basis": "adjusted_close", "source_receipt": receipt}
        observation, reason = _observation(
            source=source, schema=schema, source_event_id=event_id, receipt=receipt,
            ticker=ticker, session=session, spine=spine, intake_class="technical_emergence",
            anchor=anchor,
            occurred_at=trigger_clock,
            known_at=trigger_clock,
        )
        if observation is None:
            security, _company = _identity(spine, ticker, session)
            suppressions.append(_suppression(source, schema, event_id, receipt, ticker, str(reason),
                                              session=session, security_id=security))
        else:
            observations.append(observation)
    return IntakeBatch(tuple(observations), tuple(suppressions),
                       ({"source": source, "status": "ok", "rows": len(rows),
                         "files": file_receipts},))


def _unanchored_batch(source: str, schema: str, rows: list[dict[str, object]], spine: IdentitySpine,
                      *, ticker_key: str = "ticker", session_key: str = "as_of",
                      source_id: Callable[[dict[str, object]], str] | None = None,
                      radar: bool = False,
                      file_receipts: list[dict[str, object]] | None = None) -> IntakeBatch:
    observations: list[dict[str, object]] = []
    suppressions: list[dict[str, object]] = []
    for row in rows:
        ticker, session = row.get(ticker_key), (row.get(session_key) or row.get("date")
                                                 or row.get("decision_session")
                                                 or row.get("signal_ts"))
        event_id = source_id(row) if source_id is not None else _source_id(source, row)
        if radar and not event_id:
            receipt = "sha256:" + sha256(canonical_json(row).encode("utf-8")).hexdigest()
            suppressions.append(_suppression(source, schema, event_id, receipt, ticker,
                                             "MISSING_EXPERT_EVENT_ID", session=session))
            continue
        receipt = "sha256:" + sha256(canonical_json(row).encode("utf-8")).hexdigest()
        if bool(row.get("historical") or row.get("replay")) and not str(row.get("security_id") or "").startswith("SEC:"):
            suppressions.append(_suppression(source, schema, event_id, receipt, ticker,
                                              "HISTORICAL_IDENTITY_UNPROVEN", session=session))
            continue
        observation, reason = _observation(
            source=source, schema=schema, source_event_id=event_id, receipt=receipt, ticker=ticker,
            session=session, spine=spine, intake_class="technical_emergence", anchor=None,
            occurred_at=row.get("signal_ts"), known_at=row.get("signal_known_ts") or row.get("observed_at"),
            expert_event_id=event_id if radar else None,
        )
        if observation is None:
            security, _company = _identity(spine, ticker, session)
            suppressions.append(_suppression(source, schema, event_id, receipt, ticker, str(reason),
                                              session=session, security_id=security))
        else:
            observations.append(observation)
    return IntakeBatch(tuple(observations), tuple(suppressions),
                       ({"source": source, "status": "ok", "rows": len(rows),
                         "files": list(file_receipts or [])},))


def candidate_observations(data_root: Path, spine: IdentitySpine) -> IntakeBatch:
    paths = sorted((Path(data_root) / "us_prophet_rank" / "candidates").glob("*.parquet"))
    if not paths:
        return IntakeBatch((), (), ({"source": "candidate", "status": "degraded", "reason": "MISSING_SOURCE_FILE"},))
    snapshots = [_records_snapshot(path) for path in paths]
    rows = [row for snapshot_rows, _receipt_row in snapshots for row in snapshot_rows]
    file_receipts = [receipt for _snapshot_rows, receipt in snapshots]
    sessions = [str(row.get("stamp_date") or "") for row in rows]
    current = max((value for value in sessions if _session(value) is not None), default=None)
    if current is not None:
        rows = [row for row in rows if str(row.get("stamp_date")) == current]
    return _unanchored_batch(
        "candidate", "us_prophet_rank.candidates/v1", rows, spine, session_key="stamp_date",
        source_id=lambda row: "candidate:{stamp_date}:{ticker}:{board_definition}".format(
            stamp_date=row.get("stamp_date"), ticker=row.get("ticker"),
            board_definition=row.get("board_definition")),
        file_receipts=file_receipts,
    )


def door_observations(path: Path, spine: IdentitySpine) -> IntakeBatch:
    if not Path(path).exists():
        return IntakeBatch((), (), ({"source": "doors", "status": "degraded", "reason": "MISSING_SOURCE_FILE"},))
    payload = Path(path).read_bytes()
    rows = [json.loads(line) for line in payload.splitlines() if line.strip()]
    current = max((str(row.get("date") or "") for row in rows if _session(row.get("date")) is not None), default=None)
    if current is not None:
        rows = [row for row in rows if str(row.get("date")) == current]
    return _unanchored_batch(
        "doors", "prophet_doors/v1", rows, spine, session_key="date",
        source_id=lambda row: "doors:{date}:{door}:{ticker}".format(
            date=row.get("date"), door=row.get("door"), ticker=row.get("ticker")),
        file_receipts=[_file_receipt(Path(path), payload)],
    )


def radar_observations(path: Path, spine: IdentitySpine) -> IntakeBatch:
    if not Path(path).exists():
        return IntakeBatch((), (), ({"source": "entry_radar", "status": "degraded", "reason": "MISSING_SOURCE_FILE"},))
    rows, receipt = _records_snapshot(Path(path))
    return _unanchored_batch(
        "entry_radar", "mastermind.entry_event.v1", rows, spine,
        session_key="decision_session", source_id=lambda row: str(row.get("episode_address") or ""),
        radar=True, file_receipts=[receipt],
    )
