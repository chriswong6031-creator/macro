"""Keyless USAspending award/action collector for Government Revenue Foresight.

Official endpoints only:

* award discovery: ``POST /api/v2/search/spending_by_award/``
* award actions: ``POST /api/v2/transactions/``

The collector preserves three different clocks/tables instead of overwriting history:

* ``awards.parquet``: latest award identity/state with immutable ``first_seen_at``;
* ``award_actions.parquet``: append-only immutable actions, deduped by action id;
* ``award_snapshots.parquet``: one first-observed state per award per UTC day.

Every record carries ``known_at``, ``effective_at``, and an official source URL.  Entity
queries are curated fuzzy-name matches and therefore remain context, never signal truth.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import requests

from collectors.base import Adapter
from lib import config

AWARDS_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
TRANSACTIONS_URL = "https://api.usaspending.gov/api/v2/transactions/"
AWARD_DETAIL_URL = "https://api.usaspending.gov/api/v2/awards/{award_id}/"
CONTRACT_TYPES = ["A", "B", "C", "D"]
AWARD_FIELDS = [
    "Award ID",
    "Recipient Name",
    "Recipient UEI",
    "Start Date",
    "End Date",
    "Award Amount",
    "Total Outlays",
    "Awarding Agency",
    "Awarding Sub Agency",
    "Funding Agency",
    "Funding Sub Agency",
    "Contract Award Type",
    "Description",
    "Last Modified Date",
    "Base Obligation Date",
    "generated_internal_id",
    "NAICS",
    "PSC",
]
DEFAULT_USER_AGENT = "MastermindX Government Revenue Foresight contact@mastermind-x.com"
INGEST_STATUS_SCHEMA = "government_revenue.ingest_status.v2"
COLLECTION_RECEIPT_SCHEMA = "government_revenue.collection_receipt.v1"
COLLECTION_RECEIPTS_FILENAME = "collection_receipts.jsonl"
log = logging.getLogger(__name__)

AWARD_COLUMNS = [
    "ticker",
    "award_id",
    "generated_award_id",
    "award_key",
    "recipient_name",
    "recipient_uei",
    "description",
    "start_date",
    "end_date",
    "base_obligation_date",
    "last_modified_date",
    "total_obligated",
    "total_outlays",
    "current_award_amount",
    "potential_award_amount",
    "current_award_amount_observed_at",
    "potential_award_amount_observed_at",
    "awarding_agency",
    "awarding_sub_agency",
    "funding_agency",
    "funding_sub_agency",
    "award_type",
    "naics",
    "psc",
    "program",
    "dod_acquisition_program",
    "dod_claimant_program",
    "major_program",
    "program_acronym",
    "known_at",
    "effective_at",
    "first_seen_at",
    "last_seen_at",
    "source_url",
    "award_page_url",
    "detail_source_url",
]
ACTION_COLUMNS = [
    "ticker",
    "award_id",
    "generated_award_id",
    "award_key",
    "action_id",
    "action_date",
    "action_type",
    "action_type_description",
    "modification_number",
    "federal_action_obligation",
    "description",
    "known_at",
    "effective_at",
    "first_seen_at",
    "source_url",
    "award_page_url",
]
SNAPSHOT_COLUMNS = [
    "ticker",
    "award_id",
    "generated_award_id",
    "award_key",
    "snapshot_date",
    "recipient_name",
    "recipient_uei",
    "description",
    "start_date",
    "end_date",
    "base_obligation_date",
    "total_obligated",
    "total_outlays",
    "current_award_amount",
    "potential_award_amount",
    "current_award_amount_observed_at",
    "potential_award_amount_observed_at",
    "last_modified_date",
    "awarding_agency",
    "awarding_sub_agency",
    "funding_agency",
    "funding_sub_agency",
    "award_type",
    "naics",
    "psc",
    "program",
    "dod_acquisition_program",
    "dod_claimant_program",
    "major_program",
    "program_acronym",
    "snapshot_content_sha256",
    "known_at",
    "effective_at",
    "first_seen_at",
    "source_url",
    "detail_source_url",
]


def _canonical_json_bytes(value: Any) -> bytes:
    """Canonical bytes for receipt binding; request headers/body never persist raw."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _safe_error(exc: Exception | str) -> str:
    """Keep status diagnostics useful without allowing credential-shaped text through."""
    text = str(exc)
    return re.sub(
        r"(?i)(api[\s_-]?key|authorization|token|secret|password)\s*[=:]\s*[^,;\n]+",
        r"\1=[redacted]",
        text,
    )[:800]


def _bool_or_none(value: Any) -> bool | None:
    """Interpret documented pagination flags without assuming a missing flag is false."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    return None


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _utc_iso(value: str | datetime | None = None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text and text.lower() not in {"none", "nan", "nat"} else None


def _float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if pd.notna(out) else None


def _classification_parts(value: Any) -> tuple[str | None, str | None]:
    """Return a clean code/description pair from USAspending scalar or object fields."""
    parsed = value
    if isinstance(value, str) and value.lstrip().startswith("{"):
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            parsed = value
    if isinstance(parsed, dict):
        code = _text(parsed.get("code") or parsed.get("value") or parsed.get("id"))
        description = _text(parsed.get("description") or parsed.get("name") or parsed.get("label"))
        return code, description
    return _text(parsed), None


def _normalize_classification_cells(frame: pd.DataFrame) -> pd.DataFrame:
    """Repair legacy object-string PSC/NAICS cells before atomic persistence."""
    out = frame.copy()
    psc_descriptions = (
        out["psc"].map(lambda value: _classification_parts(value)[1])
        if "psc" in out.columns
        else pd.Series(index=out.index, dtype=object)
    )
    if "program" in out.columns:
        clean_program = out["program"].map(
            lambda value: _classification_parts(value)[1] or _classification_parts(value)[0]
        )
        out["program"] = clean_program.where(clean_program.notna(), psc_descriptions)
    for column in ("psc", "naics"):
        if column in out.columns:
            out[column] = out[column].map(lambda value: _classification_parts(value)[0])
    return out


def _award_page(generated_award_id: str | None) -> str:
    return (
        f"https://www.usaspending.gov/award/{generated_award_id}/"
        if generated_award_id
        else "https://www.usaspending.gov/search/"
    )


def _award_key(generated_award_id: Any, award_id: Any) -> str | None:
    """Canonical award identity; PIID is an explicit legacy fallback only."""
    generated = _text(generated_award_id)
    if generated:
        return f"generated:{generated}"
    piid = _text(award_id)
    return f"piid:{piid}" if piid else None


def _ensure_award_keys(frame: pd.DataFrame) -> pd.DataFrame:
    """Backfill canonical identity when reading pre-award_key ledgers."""
    out = frame.copy()
    if "award_key" not in out.columns:
        out["award_key"] = None
    generated = out.get("generated_award_id", pd.Series(index=out.index, dtype=object))
    piids = out.get("award_id", pd.Series(index=out.index, dtype=object))
    for idx in out.index:
        if _text(out.at[idx, "award_key"]):
            continue
        out.at[idx, "award_key"] = _award_key(generated.get(idx), piids.get(idx))
    return out


def normalize_award(raw: dict, ticker: str, observed_at: str) -> dict:
    """Normalize one documented spending_by_award result without inferred fields."""
    generated = _text(raw.get("generated_internal_id") or raw.get("generated_award_id"))
    award_id = _text(raw.get("Award ID") or raw.get("award_id"))
    effective = _text(
        raw.get("Last Modified Date")
        or raw.get("last_modified_date")
        or raw.get("Base Obligation Date")
        or raw.get("base_obligation_date")
        or raw.get("Start Date")
        or raw.get("start_date")
    )
    row = {
        "ticker": ticker.upper(),
        "award_id": award_id,
        "generated_award_id": generated,
        "award_key": _award_key(generated, award_id),
        "recipient_name": _text(raw.get("Recipient Name") or raw.get("recipient_name")),
        "recipient_uei": _text(raw.get("Recipient UEI") or raw.get("recipient_uei")),
        "description": _text(raw.get("Description") or raw.get("description")),
        "start_date": _text(raw.get("Start Date") or raw.get("start_date")),
        "end_date": _text(raw.get("End Date") or raw.get("end_date")),
        "base_obligation_date": _text(raw.get("Base Obligation Date") or raw.get("base_obligation_date")),
        "last_modified_date": _text(raw.get("Last Modified Date") or raw.get("last_modified_date")),
        "total_obligated": _float(raw.get("Award Amount", raw.get("total_obligated"))),
        "total_outlays": _float(raw.get("Total Outlays", raw.get("total_outlays"))),
        # These fields are intentionally nullable. The documented award-search response
        # does not expose exercised/current value or ceiling, and obligation != ceiling.
        "current_award_amount": _float(
            raw.get("Current Award Amount", raw.get("current_award_amount"))
        ),
        "potential_award_amount": _float(
            raw.get("Potential Award Amount", raw.get("potential_award_amount"))
        ),
        "current_award_amount_observed_at": None,
        "potential_award_amount_observed_at": None,
        "awarding_agency": _text(raw.get("Awarding Agency") or raw.get("awarding_agency")),
        "awarding_sub_agency": _text(
            raw.get("Awarding Sub Agency") or raw.get("awarding_sub_agency")
        ),
        "funding_agency": _text(raw.get("Funding Agency") or raw.get("funding_agency")),
        "funding_sub_agency": _text(raw.get("Funding Sub Agency") or raw.get("funding_sub_agency")),
        "award_type": _text(raw.get("Contract Award Type") or raw.get("award_type")),
        "naics": _classification_parts(raw.get("NAICS") or raw.get("naics"))[0],
        "psc": _classification_parts(raw.get("PSC") or raw.get("psc"))[0],
        "program": _text(raw.get("program")),
        "dod_acquisition_program": _text(raw.get("dod_acquisition_program")),
        "dod_claimant_program": _text(raw.get("dod_claimant_program")),
        "major_program": _text(raw.get("major_program")),
        "program_acronym": _text(raw.get("program_acronym")),
        "known_at": observed_at,
        "effective_at": effective,
        "first_seen_at": observed_at,
        "last_seen_at": observed_at,
        "source_url": AWARDS_URL,
        "award_page_url": _award_page(generated),
        "detail_source_url": AWARD_DETAIL_URL.format(award_id=generated) if generated else None,
    }
    return row


def enrich_award(award: dict, detail: dict) -> dict:
    """Overlay official award-detail values required for backlog/program context.

    ``total_obligation`` is money obligated, ``base_exercised_options`` is currently
    exercised contract value, and ``base_and_all_options`` is potential value. They are
    deliberately kept separate; no field is reverse-engineered from another.
    """
    out = award.copy()
    pop = detail.get("period_of_performance") or {}
    recipient = detail.get("recipient") or {}
    contract = detail.get("latest_transaction_contract_data") or {}
    generated = _text(detail.get("generated_unique_award_id")) or out.get("generated_award_id")
    acquisition = _text(
        contract.get("dod_acquisition_program_description")
        or contract.get("dod_acquisition_program")
    )
    claimant = _text(
        contract.get("dod_claimant_program_description")
        or contract.get("dod_claimant_program")
    )
    major = _text(contract.get("major_program"))
    acronym = _text(contract.get("program_acronym"))
    naics_code, _naics_description = _classification_parts(contract.get("naics"))
    psc_code, psc_description = _classification_parts(contract.get("product_or_service_code"))
    current_amount_present = "base_exercised_options" in detail
    potential_amount_present = "base_and_all_options" in detail
    updates = {
        "generated_award_id": generated,
        "award_id": _text(detail.get("piid")) or out.get("award_id"),
        "recipient_name": _text(recipient.get("recipient_name")) or out.get("recipient_name"),
        "recipient_uei": _text(recipient.get("recipient_uei")) or out.get("recipient_uei"),
        "description": _text(detail.get("description")) or out.get("description"),
        "start_date": _text(pop.get("start_date")) or out.get("start_date"),
        "end_date": _text(pop.get("end_date")) or out.get("end_date"),
        "last_modified_date": _text(pop.get("last_modified_date")) or out.get("last_modified_date"),
        "total_obligated": _float(detail.get("total_obligation")),
        "total_outlays": _float(detail.get("total_outlay")),
        "current_award_amount": _float(detail.get("base_exercised_options")),
        "potential_award_amount": _float(detail.get("base_and_all_options")),
        "naics": naics_code or out.get("naics"),
        "psc": psc_code or out.get("psc"),
        "program": acquisition or major or acronym or claimant or psc_description,
        "dod_acquisition_program": acquisition,
        "dod_claimant_program": claimant,
        "major_program": major,
        "program_acronym": acronym,
        "award_page_url": _award_page(generated),
        "detail_source_url": AWARD_DETAIL_URL.format(award_id=generated) if generated else None,
    }
    # Detail can occasionally contain nulls that the search record populated. Null detail
    # must never erase a previously observed value.
    for key, value in updates.items():
        if value is not None:
            out[key] = value
    # Successful detail responses distinguish an explicitly null field from a
    # field that was not requested/observed in a search-only pass.
    if current_amount_present:
        out["current_award_amount"] = updates["current_award_amount"]
        out["current_award_amount_observed_at"] = out.get("known_at")
    if potential_amount_present:
        out["potential_award_amount"] = updates["potential_award_amount"]
        out["potential_award_amount_observed_at"] = out.get("known_at")
    out["award_key"] = _award_key(out.get("generated_award_id"), out.get("award_id"))
    out["effective_at"] = out.get("last_modified_date") or out.get("effective_at")
    return out


def normalize_action(raw: dict, award: dict, observed_at: str) -> dict:
    """Normalize one documented /transactions result."""
    action_date = _text(raw.get("action_date"))
    action_id = _text(raw.get("id") or raw.get("action_id"))
    # A deterministic fallback supports rare legacy records without id while keeping
    # repeat fetches idempotent.
    if not action_id:
        action_id = "|".join(
            str(x or "")
            for x in (
                award.get("generated_award_id") or award.get("award_id"),
                raw.get("modification_number"),
                action_date,
                raw.get("federal_action_obligation"),
            )
        )
    return {
        "ticker": award.get("ticker"),
        "award_id": award.get("award_id"),
        "generated_award_id": award.get("generated_award_id"),
        "award_key": award.get("award_key") or _award_key(
            award.get("generated_award_id"), award.get("award_id")
        ),
        "action_id": action_id,
        "action_date": action_date,
        "action_type": _text(raw.get("action_type")),
        "action_type_description": _text(raw.get("action_type_description")),
        "modification_number": _text(raw.get("modification_number")),
        "federal_action_obligation": _float(raw.get("federal_action_obligation")),
        "description": _text(raw.get("description")),
        "known_at": observed_at,
        "effective_at": action_date,
        "first_seen_at": observed_at,
        "source_url": TRANSACTIONS_URL,
        "award_page_url": award.get("award_page_url") or _award_page(award.get("generated_award_id")),
    }


def append_first_seen(
    existing: pd.DataFrame,
    incoming: pd.DataFrame,
    key_columns: Iterable[str],
    columns: Iterable[str],
) -> pd.DataFrame:
    """Append immutable first observations and keep the first copy of duplicate keys."""
    keys = list(key_columns)
    cols = list(columns)
    if incoming.empty:
        return existing.reindex(columns=cols).copy() if not existing.empty else pd.DataFrame(columns=cols)
    combined = pd.concat(
        [existing.reindex(columns=cols), incoming.reindex(columns=cols)], ignore_index=True
    )
    if any(c not in combined.columns for c in keys):
        raise ValueError(f"missing append key column(s): {keys}")
    combined = combined.dropna(subset=keys).drop_duplicates(keys, keep="first")
    return combined.reindex(columns=cols).reset_index(drop=True)


def merge_awards(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    """Update mutable award state without erasing prior detail enrichment.

    Award-search rows do not carry the exercised-value, all-options-value, and
    program fields supplied by the award-detail endpoint.  A bounded detail run
    (or a transient detail failure) must therefore treat incoming nulls as
    "not observed this pass", rather than as evidence that a prior value became
    null.  Non-null incoming fields still win and the observation clocks advance.
    """
    if incoming.empty:
        return existing.reindex(columns=AWARD_COLUMNS).copy()
    old = _ensure_award_keys(existing.reindex(columns=AWARD_COLUMNS))
    new = _ensure_award_keys(incoming.reindex(columns=AWARD_COLUMNS))
    key = ["ticker", "award_key"]
    if old.empty:
        return new.dropna(subset=key).drop_duplicates(key, keep="last").reset_index(drop=True)
    old = old.dropna(subset=key).drop_duplicates(key, keep="last").set_index(key)
    new = new.dropna(subset=key).drop_duplicates(key, keep="last").set_index(key)
    old_first = old["first_seen_at"].copy()

    # ``combine_first`` keeps every non-null value from the new observation and
    # fills only its null holes from the previously enriched state.
    combined = new.combine_first(old)
    for value_column, observed_column in (
        ("current_award_amount", "current_award_amount_observed_at"),
        ("potential_award_amount", "potential_award_amount_observed_at"),
    ):
        explicit_null = new[observed_column].notna() & new[value_column].isna()
        for index in new.index[explicit_null]:
            combined.at[index, value_column] = None
    for k, first_seen in old_first.items():
        if k in combined.index:
            combined.at[k, "first_seen_at"] = first_seen
    return combined.reset_index().reindex(columns=AWARD_COLUMNS)


def snapshot_rows(awards: pd.DataFrame, observed_at: str) -> pd.DataFrame:
    """Build immutable observation-version rows for later point-in-time replay."""
    if awards.empty:
        return pd.DataFrame(columns=SNAPSHOT_COLUMNS)
    day = observed_at[:10]
    rows = []
    for _, award in awards.iterrows():
        snapshot = {
            "ticker": award.get("ticker"),
            "award_id": award.get("award_id"),
            "generated_award_id": award.get("generated_award_id"),
            "award_key": award.get("award_key") or _award_key(
                award.get("generated_award_id"), award.get("award_id")
            ),
            "snapshot_date": day,
            "recipient_name": award.get("recipient_name"),
            "recipient_uei": award.get("recipient_uei"),
            "description": award.get("description"),
            "start_date": award.get("start_date"),
            "end_date": award.get("end_date"),
            "base_obligation_date": award.get("base_obligation_date"),
            "total_obligated": award.get("total_obligated"),
            "total_outlays": award.get("total_outlays"),
            "current_award_amount": award.get("current_award_amount"),
            "potential_award_amount": award.get("potential_award_amount"),
            "current_award_amount_observed_at": award.get("current_award_amount_observed_at"),
            "potential_award_amount_observed_at": award.get("potential_award_amount_observed_at"),
            "last_modified_date": award.get("last_modified_date"),
            "awarding_agency": award.get("awarding_agency"),
            "awarding_sub_agency": award.get("awarding_sub_agency"),
            "funding_agency": award.get("funding_agency"),
            "funding_sub_agency": award.get("funding_sub_agency"),
            "award_type": award.get("award_type"),
            "naics": award.get("naics"),
            "psc": award.get("psc"),
            "program": award.get("program"),
            "dod_acquisition_program": award.get("dod_acquisition_program"),
            "dod_claimant_program": award.get("dod_claimant_program"),
            "major_program": award.get("major_program"),
            "program_acronym": award.get("program_acronym"),
            "known_at": observed_at,
            "effective_at": award.get("effective_at"),
            "first_seen_at": award.get("first_seen_at") or observed_at,
            "source_url": AWARDS_URL,
            "detail_source_url": award.get("detail_source_url"),
        }
        snapshot["snapshot_content_sha256"] = _snapshot_content_sha256(snapshot)
        rows.append(snapshot)
    return pd.DataFrame(rows, columns=SNAPSHOT_COLUMNS)


def _snapshot_content_sha256(row: dict | pd.Series) -> str:
    """Hash mutable award state while excluding observation-only clocks."""
    payload: dict[str, Any] = {}
    for column in SNAPSHOT_COLUMNS:
        if column in {
            "snapshot_date",
            "known_at",
            "snapshot_content_sha256",
            "current_award_amount_observed_at",
            "potential_award_amount_observed_at",
        }:
            continue
        value = row.get(column)
        try:
            if pd.isna(value):
                value = None
        except (TypeError, ValueError):
            pass
        if isinstance(value, pd.Timestamp):
            value = value.isoformat()
        payload[column] = value
    return _sha256_json(payload)


def _ensure_snapshot_hashes(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.reindex(columns=SNAPSHOT_COLUMNS).copy()
    if out.empty:
        return out
    missing = out["snapshot_content_sha256"].isna() | out[
        "snapshot_content_sha256"
    ].astype(str).str.strip().eq("")
    if missing.any():
        out.loc[missing, "snapshot_content_sha256"] = [
            _snapshot_content_sha256(row)
            for _, row in out.loc[missing].iterrows()
        ]
    return out


def append_snapshot_versions(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    """Append state transitions, including a later reversion to an older hash."""
    accrued = _ensure_snapshot_hashes(existing)
    fresh = _ensure_snapshot_hashes(incoming)
    if fresh.empty:
        return accrued.reset_index(drop=True)
    if accrued.empty:
        return fresh.sort_values("known_at", kind="stable").reset_index(drop=True)

    latest_hash: dict[tuple[str, str], str] = {}
    ordered_existing = accrued.assign(
        _known=pd.to_datetime(accrued["known_at"], utc=True, errors="coerce")
    ).sort_values("_known", kind="stable")
    for _, row in ordered_existing.iterrows():
        latest_hash[(str(row.get("ticker")), str(row.get("award_key")))] = str(
            row.get("snapshot_content_sha256")
        )

    additions: list[dict] = []
    ordered_fresh = fresh.assign(
        _known=pd.to_datetime(fresh["known_at"], utc=True, errors="coerce")
    ).sort_values("_known", kind="stable")
    for _, row in ordered_fresh.drop(columns=["_known"]).iterrows():
        key = (str(row.get("ticker")), str(row.get("award_key")))
        content_hash = str(row.get("snapshot_content_sha256"))
        if latest_hash.get(key) == content_hash:
            continue
        additions.append(row.to_dict())
        latest_hash[key] = content_hash
    if not additions:
        return accrued.reset_index(drop=True)
    return pd.concat(
        [accrued, pd.DataFrame(additions, columns=SNAPSHOT_COLUMNS)],
        ignore_index=True,
    ).reindex(columns=SNAPSHOT_COLUMNS)


def _read_existing(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    try:
        return pd.read_parquet(path).reindex(columns=columns)
    except Exception as exc:  # noqa: BLE001 - accrued PIT history must fail closed
        raise RuntimeError(f"refusing to overwrite unreadable accrued store: {path}: {exc}") from exc


def _atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        frame.to_parquet(tmp, index=False)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _atomic_json(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001 - last-good status must not be silently replaced
        raise RuntimeError(f"refusing to overwrite unreadable status: {path}: {_safe_error(exc)}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"refusing to overwrite non-object status: {path}")
    return payload


def _append_collection_receipts(receipts: list[dict], path: Path) -> dict:
    """Append hash-only source receipts without modifying an existing collection event.

    The raw responses are intentionally not persisted here: USAspending responses can be
    re-fetched from their official endpoints, while the immutable request/response hashes
    prove exactly which source page informed this run without retaining headers or secrets.
    A corrupt accrued receipt ledger fails closed rather than being overwritten.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_text = ""
    existing_ids: set[str] = set()
    if path.exists():
        try:
            existing_text = path.read_text()
            for raw_line in existing_text.splitlines():
                if not raw_line.strip():
                    continue
                row = json.loads(raw_line)
                if not isinstance(row, dict) or not isinstance(row.get("receipt_id"), str):
                    raise ValueError("missing receipt_id")
                existing_ids.add(row["receipt_id"])
        except Exception as exc:  # noqa: BLE001 - preserve immutable receipt history
            raise RuntimeError(
                f"refusing to overwrite unreadable collection receipt ledger: {path}: {_safe_error(exc)}"
            ) from exc

    new_lines: list[str] = []
    for receipt in receipts:
        receipt_id = receipt.get("receipt_id")
        if not isinstance(receipt_id, str) or not receipt_id:
            raise ValueError("collection receipt missing receipt_id")
        if receipt_id in existing_ids:
            continue
        new_lines.append(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
        existing_ids.add(receipt_id)

    if new_lines:
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            separator = "" if not existing_text or existing_text.endswith("\n") else "\n"
            content = existing_text + separator + "\n".join(new_lines) + "\n"
            tmp.write_text(content)
            os.replace(tmp, path)
        finally:
            if tmp.exists():
                tmp.unlink()
    return {
        "schema_version": COLLECTION_RECEIPT_SCHEMA,
        "path": COLLECTION_RECEIPTS_FILENAME,
        "response_receipts_this_run": len(receipts),
        "new_receipts_this_run": len(new_lines),
        "receipts_total": len(existing_ids),
        "raw_response_bodies_persisted": False,
    }


class UsaspendingAwardsCollector:
    """Official USAspending collector with explicit bounded-sample semantics.

    Award searches remain intentionally bounded by a per-entity safety cap and
    award-detail/action work remains a top-award sample.  Those limits are not a
    proxy for full-corpus coverage: every rail records its own denominator,
    pagination outcome, and last-good timestamp in ``ingest_status.json``.
    """

    def __init__(
        self,
        root: Path | None = None,
        session: requests.Session | None = None,
        page_size: int = 50,
        max_pages: int = 2,
        max_action_awards_per_entity: int = 8,
        action_page_size: int = 5000,
        max_action_pages: int = 100,
        request_pacing_seconds: float = 0.2,
        user_agent: str | None = None,
    ) -> None:
        self.root = Path(root).resolve() if root is not None else Path.cwd().resolve()
        self.session = session or requests.Session()
        self.page_size = max(1, min(int(page_size), 100))
        self.max_pages = max(1, int(max_pages))
        self.max_action_awards_per_entity = max(0, int(max_action_awards_per_entity))
        self.action_page_size = max(1, min(int(action_page_size), 5000))
        self.max_action_pages = max(1, int(max_action_pages))
        self.request_pacing_seconds = max(0.0, float(request_pacing_seconds))
        self.headers = {
            "User-Agent": user_agent or os.getenv("USA_SPENDING_USER_AGENT", DEFAULT_USER_AGENT),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _post(self, url: str, body: dict, retries: int = 3, timeout: int = 60) -> dict:
        last: Exception | None = None
        for attempt in range(retries):
            try:
                response = self.session.post(url, json=body, headers=self.headers, timeout=timeout)
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise requests.HTTPError(f"HTTP {response.status_code}", response=response)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError(f"expected object response from {url}")
                return payload
            except Exception as exc:  # noqa: BLE001 - retry network and parse failures
                last = exc
                if attempt + 1 < retries:
                    time.sleep(1.5 * (attempt + 1))
        assert last is not None
        raise last

    def _get(self, url: str, retries: int = 3, timeout: int = 60) -> dict:
        last: Exception | None = None
        for attempt in range(retries):
            try:
                response = self.session.get(url, headers=self.headers, timeout=timeout)
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise requests.HTTPError(f"HTTP {response.status_code}", response=response)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError(f"expected object response from {url}")
                return payload
            except Exception as exc:  # noqa: BLE001 - retry network and parse failures
                last = exc
                if attempt + 1 < retries:
                    time.sleep(1.5 * (attempt + 1))
        assert last is not None
        raise last

    def _entities(self) -> dict[str, dict]:
        path = self.root / "data" / "government_revenue" / "entities.json"
        payload = json.loads(path.read_text())
        entities = payload.get("entities") or {}
        if not isinstance(entities, dict) or not entities:
            raise ValueError(f"entity map missing or empty: {path}")
        return entities

    @staticmethod
    def _response_receipt(
        *,
        rail: str,
        endpoint: str,
        request: dict,
        response: dict,
        subject: dict[str, Any],
        observed_at: str,
        run_id: str,
        page: int | None,
        record_count: int,
        has_next: bool | None,
    ) -> dict:
        """Bind a successful official response without persisting raw source bytes."""
        request_sha256 = _sha256_json(request)
        response_sha256 = _sha256_json(response)
        safe_subject = {
            str(key): _text(value)
            for key, value in subject.items()
            if _text(value) is not None
        }
        return {
            "schema_version": COLLECTION_RECEIPT_SCHEMA,
            "receipt_id": (
                f"usaspending:{run_id}:{rail}:{request_sha256[:16]}:{response_sha256[:16]}"
            ),
            "run_id": run_id,
            "observed_at": observed_at,
            "rail": rail,
            "endpoint": endpoint,
            "subject": safe_subject,
            "page": page,
            "record_count": int(record_count),
            "has_next": has_next,
            "request_sha256": request_sha256,
            "response_sha256": response_sha256,
        }

    def _fetch_post_pages(
        self,
        *,
        rail: str,
        endpoint: str,
        body_for_page: Any,
        subject: dict[str, Any],
        max_pages: int,
        observed_at: str,
        run_id: str,
    ) -> tuple[list[dict], dict, list[dict]]:
        """Fetch every declared page, or return an auditable incomplete outcome.

        We only call a rail complete after the upstream explicitly returns
        ``page_metadata.hasNext == false``.  A missing flag, a request failure,
        or an explicit safety-cap hit remains partial even when earlier pages
        yielded useful append-only records.
        """
        rows: list[dict] = []
        receipts: list[dict] = []
        pages_requested = 0
        pages_succeeded = 0
        raw_records = 0
        accepted_records = 0
        page = 1
        complete = False
        unresolved_has_next = False
        missing_has_next = False
        last_has_next: bool | None = None
        reason: str | None = None
        error: str | None = None

        while page <= max_pages:
            body = body_for_page(page)
            pages_requested += 1
            try:
                payload = self._post(endpoint, body)
                results = payload.get("results") or []
                if not isinstance(results, list):
                    raise ValueError(f"USAspending {rail} results is not a list")
            except Exception as exc:  # noqa: BLE001 - partial append-only collection is permitted
                error = _safe_error(exc)
                reason = "request_failed"
                break

            pages_succeeded += 1
            raw_records += len(results)
            accepted = [row for row in results if isinstance(row, dict)]
            accepted_records += len(accepted)
            rows.extend(accepted)
            metadata = payload.get("page_metadata")
            metadata = metadata if isinstance(metadata, dict) else {}
            last_has_next = _bool_or_none(metadata.get("hasNext"))
            receipts.append(self._response_receipt(
                rail=rail,
                endpoint=endpoint,
                request=body,
                response=payload,
                subject=subject,
                observed_at=observed_at,
                run_id=run_id,
                page=page,
                record_count=len(results),
                has_next=last_has_next,
            ))

            if last_has_next is False:
                complete = True
                reason = "has_next_false"
                break
            if last_has_next is None:
                missing_has_next = True
                reason = "missing_has_next"
                break
            if page >= max_pages:
                unresolved_has_next = True
                reason = "max_pages_reached_with_has_next"
                break
            page += 1
            if self.request_pacing_seconds:
                time.sleep(self.request_pacing_seconds)

        state = "complete" if complete else ("failed" if pages_succeeded == 0 else "partial")
        return rows, {
            "state": state,
            "reason": reason or "pagination_not_started",
            "pages": {
                "requested": pages_requested,
                "succeeded": pages_succeeded,
                "safety_cap": int(max_pages),
            },
            "records": {"raw": raw_records, "accepted": accepted_records},
            "has_next": last_has_next,
            "unresolved_has_next": unresolved_has_next,
            "missing_has_next": missing_has_next,
            "error": error,
        }, receipts

    def fetch_awards_with_metadata(
        self,
        ticker: str,
        entity: dict,
        start_date: str,
        end_date: str,
        *,
        observed_at: str,
        run_id: str,
    ) -> tuple[list[dict], dict, list[dict]]:
        query = entity.get("recipient_search_text") or entity.get("name") or ticker
        def body_for_page(page: int) -> dict:
            return {
                "subawards": False,
                "limit": self.page_size,
                "page": page,
                "order": "desc",
                "sort": "Award Amount",
                "filters": {
                    "time_period": [{"start_date": start_date, "end_date": end_date}],
                    "recipient_search_text": [query],
                    "award_type_codes": CONTRACT_TYPES,
                },
                "fields": AWARD_FIELDS,
            }

        return self._fetch_post_pages(
            rail="awards",
            endpoint=AWARDS_URL,
            body_for_page=body_for_page,
            subject={"ticker": ticker},
            max_pages=self.max_pages,
            observed_at=observed_at,
            run_id=run_id,
        )

    def fetch_awards(self, ticker: str, entity: dict, start_date: str, end_date: str) -> list[dict]:
        """Compatibility wrapper for callers that only need source rows."""
        rows, _meta, _receipts = self.fetch_awards_with_metadata(
            ticker,
            entity,
            start_date,
            end_date,
            observed_at=_utc_iso(),
            run_id="ad_hoc",
        )
        return rows

    def fetch_actions_with_metadata(
        self,
        award: dict,
        *,
        observed_at: str,
        run_id: str,
    ) -> tuple[list[dict], dict, list[dict]]:
        generated = award.get("generated_award_id")
        if not generated:
            return [], {
                "state": "not_requested",
                "reason": "missing_generated_award_id",
                "pages": {"requested": 0, "succeeded": 0, "safety_cap": self.max_action_pages},
                "records": {"raw": 0, "accepted": 0},
                "has_next": None,
                "unresolved_has_next": False,
                "missing_has_next": False,
                "error": None,
            }, []

        def body_for_page(page: int) -> dict:
            return {
                "award_id": generated,
                "page": page,
                "sort": "action_date",
                "order": "desc",
                "limit": self.action_page_size,
            }

        return self._fetch_post_pages(
            rail="actions",
            endpoint=TRANSACTIONS_URL,
            body_for_page=body_for_page,
            subject={"ticker": award.get("ticker"), "award_key": award.get("award_key")},
            max_pages=self.max_action_pages,
            observed_at=observed_at,
            run_id=run_id,
        )

    def fetch_actions(self, award: dict) -> list[dict]:
        """Compatibility wrapper for callers that only need source rows."""
        rows, _meta, _receipts = self.fetch_actions_with_metadata(
            award,
            observed_at=_utc_iso(),
            run_id="ad_hoc",
        )
        return rows

    def fetch_award_detail(self, award: dict) -> dict:
        generated = award.get("generated_award_id")
        if not generated:
            return {}
        return self._get(AWARD_DETAIL_URL.format(award_id=generated))

    def fetch_award_detail_with_receipt(
        self,
        award: dict,
        *,
        observed_at: str,
        run_id: str,
    ) -> tuple[dict, dict | None]:
        generated = award.get("generated_award_id")
        if not generated:
            return {}, None
        endpoint = AWARD_DETAIL_URL.format(award_id=generated)
        payload = self._get(endpoint)
        return payload, self._response_receipt(
            rail="award_detail",
            endpoint=endpoint,
            request={"method": "GET", "award_id": generated},
            response=payload,
            subject={"ticker": award.get("ticker"), "award_key": award.get("award_key")},
            observed_at=observed_at,
            run_id=run_id,
            page=None,
            record_count=1,
            has_next=None,
        )

    def collect(
        self,
        tickers: Iterable[str] | None = None,
        as_of: str | None = None,
        lookback_days: int = 1826,
    ) -> dict:
        observed_at = _utc_iso()
        end = datetime.fromisoformat(as_of).date() if as_of else datetime.now(timezone.utc).date()
        start = end - timedelta(days=int(lookback_days))
        selected = {str(x).upper() for x in tickers} if tickers else None
        entities = self._entities()
        data_dir = self.root / "data" / "government_revenue"
        status_path = data_dir / "ingest_status.json"
        # Status itself carries the last-good clocks.  Refuse to replace an unreadable
        # status document with a fresh-looking, less informative result.
        previous_status = _read_json(status_path)
        entity_items = [
            (ticker, entity)
            for ticker, entity in entities.items()
            if selected is None or ticker in selected
        ]
        unknown_tickers = sorted(selected - set(entities)) if selected is not None else []
        requested_entities = len(selected) if selected is not None else len(entities)
        full_configured_universe = (
            selected is None
            or (not unknown_tickers and selected == {str(ticker).upper() for ticker in entities})
        )
        run_id = "usaspending-" + _sha256_json({
            "observed_at": observed_at,
            "as_of": end.isoformat(),
            "tickers": sorted(selected) if selected is not None else sorted(entities),
            "lookback_days": int(lookback_days),
        })[:24]
        award_rows: list[dict] = []
        action_rows: list[dict] = []
        receipts: list[dict] = []
        errors: list[dict] = []
        entities_with_awards = 0
        award_pages_requested = 0
        award_pages_succeeded = 0
        award_raw_records = 0
        award_accepted_records = 0
        award_complete_entities = 0
        award_partial_entities = 0
        award_failed_entities = 0
        award_unresolved_has_next = 0
        award_missing_has_next = 0
        award_normalization_failures = 0
        award_rejected_without_key = 0
        detail_attempted = 0
        detail_succeeded = 0
        detail_skipped_missing_identifier = 0
        detail_candidates = 0
        action_awards_attempted = 0
        action_awards_succeeded = 0
        action_awards_partial = 0
        action_awards_failed = 0
        action_awards_not_requested = 0
        action_pages_requested = 0
        action_pages_succeeded = 0
        action_raw_records = 0
        action_accepted_records = 0
        action_unresolved_has_next = 0
        action_missing_has_next = 0

        for ticker in unknown_tickers:
            errors.append({
                "ticker": ticker,
                "stage": "awards",
                "reason": "ticker_not_in_entity_map",
                "error": "requested ticker is not in the curated recipient entity map",
            })

        for ticker, entity in entity_items:
            try:
                raw_awards, award_meta, award_receipts = self.fetch_awards_with_metadata(
                    ticker,
                    entity,
                    start.isoformat(),
                    end.isoformat(),
                    observed_at=observed_at,
                    run_id=run_id,
                )
                receipts.extend(award_receipts)
                award_pages_requested += _as_int((award_meta.get("pages") or {}).get("requested"))
                award_pages_succeeded += _as_int((award_meta.get("pages") or {}).get("succeeded"))
                award_raw_records += _as_int((award_meta.get("records") or {}).get("raw"))
                award_accepted_records += _as_int((award_meta.get("records") or {}).get("accepted"))
                if award_meta.get("unresolved_has_next"):
                    award_unresolved_has_next += 1
                if award_meta.get("missing_has_next"):
                    award_missing_has_next += 1
                award_state = str(award_meta.get("state") or "failed")
                if award_state == "complete":
                    award_complete_entities += 1
                elif award_state == "partial":
                    award_partial_entities += 1
                else:
                    award_failed_entities += 1
                if award_state != "complete":
                    errors.append({
                        "ticker": ticker,
                        "stage": "awards",
                        "reason": award_meta.get("reason"),
                        "error": award_meta.get("error") or "award pagination did not reach explicit hasNext=false",
                    })

                normalized: list[dict] = []
                for raw_award in raw_awards:
                    try:
                        award = normalize_award(raw_award, ticker, observed_at)
                    except Exception as exc:  # noqa: BLE001 - retain other rows from an official page
                        award_normalization_failures += 1
                        errors.append({
                            "ticker": ticker,
                            "stage": "awards",
                            "reason": "normalization_failed",
                            "error": _safe_error(exc),
                        })
                        continue
                    if not award.get("award_key"):
                        award_rejected_without_key += 1
                        errors.append({
                            "ticker": ticker,
                            "stage": "awards",
                            "reason": "missing_award_identity",
                            "error": "official award result has neither generated award id nor award id",
                        })
                        continue
                    normalized.append(award)
                if normalized:
                    entities_with_awards += 1

                # Detail/actions are a sample, never a full-corpus claim.  One source
                # duplicate cannot consume more than one of the limited sample slots.
                by_award_key: dict[str, dict] = {}
                for award in normalized:
                    award_key = str(award["award_key"])
                    existing = by_award_key.get(award_key)
                    if existing is None or (award.get("total_obligated") or 0.0) > (existing.get("total_obligated") or 0.0):
                        by_award_key[award_key] = award
                candidates = sorted(
                    by_award_key.values(),
                    key=lambda item: item.get("total_obligated") or 0.0,
                    reverse=True,
                )[: self.max_action_awards_per_entity]
                detail_candidates += len(candidates)
                enriched_by_key: dict[str, dict] = dict(by_award_key)
                for candidate in candidates:
                    award_key = str(candidate["award_key"])
                    if not candidate.get("generated_award_id"):
                        detail_skipped_missing_identifier += 1
                        errors.append({
                            "ticker": ticker,
                            "stage": "award_detail",
                            "award_id": candidate.get("award_id"),
                            "reason": "missing_generated_award_id",
                            "error": "award detail endpoint requires generated_award_id",
                        })
                        continue
                    detail_attempted += 1
                    try:
                        detail, detail_receipt = self.fetch_award_detail_with_receipt(
                            candidate,
                            observed_at=observed_at,
                            run_id=run_id,
                        )
                        if detail_receipt is not None:
                            receipts.append(detail_receipt)
                        enriched_by_key[award_key] = enrich_award(candidate, detail)
                        detail_succeeded += 1
                    except Exception as exc:  # noqa: BLE001 - detail is additive per award
                        errors.append({
                            "ticker": ticker,
                            "stage": "award_detail",
                            "award_id": candidate.get("award_id"),
                            "reason": "request_failed",
                            "error": _safe_error(exc),
                        })
                    if self.request_pacing_seconds:
                        time.sleep(self.request_pacing_seconds)

                enriched = [enriched_by_key.get(str(award["award_key"]), award) for award in normalized]
                award_rows.extend(enriched)
                enriched_candidates = [
                    enriched_by_key.get(str(candidate["award_key"]), candidate)
                    for candidate in candidates
                ]
                for award in enriched_candidates:
                    action_raw_rows, action_meta, action_receipts = self.fetch_actions_with_metadata(
                        award,
                        observed_at=observed_at,
                        run_id=run_id,
                    )
                    receipts.extend(action_receipts)
                    action_pages_requested += _as_int((action_meta.get("pages") or {}).get("requested"))
                    action_pages_succeeded += _as_int((action_meta.get("pages") or {}).get("succeeded"))
                    action_raw_records += _as_int((action_meta.get("records") or {}).get("raw"))
                    action_accepted_records += _as_int((action_meta.get("records") or {}).get("accepted"))
                    if action_meta.get("unresolved_has_next"):
                        action_unresolved_has_next += 1
                    if action_meta.get("missing_has_next"):
                        action_missing_has_next += 1
                    action_state = str(action_meta.get("state") or "failed")
                    if action_state == "complete":
                        action_awards_attempted += 1
                        action_awards_succeeded += 1
                    elif action_state == "partial":
                        action_awards_attempted += 1
                        action_awards_partial += 1
                    elif action_state == "not_requested":
                        action_awards_not_requested += 1
                    else:
                        action_awards_attempted += 1
                        action_awards_failed += 1
                    if action_state != "complete":
                        errors.append({
                            "ticker": ticker,
                            "stage": "actions",
                            "award_id": award.get("award_id"),
                            "reason": action_meta.get("reason"),
                            "error": action_meta.get("error") or "action pagination did not reach explicit hasNext=false",
                        })
                    for raw_action in action_raw_rows:
                        try:
                            action_rows.append(normalize_action(raw_action, award, observed_at))
                        except Exception as exc:  # noqa: BLE001 - record every unreconciled source action
                            errors.append({
                                "ticker": ticker,
                                "stage": "actions",
                                "award_id": award.get("award_id"),
                                "reason": "normalization_failed",
                                "error": _safe_error(exc),
                            })
                    if self.request_pacing_seconds:
                        time.sleep(self.request_pacing_seconds)
            except Exception as exc:  # noqa: BLE001 - retain other mapped recipients
                award_failed_entities += 1
                errors.append({
                    "ticker": ticker,
                    "stage": "awards",
                    "reason": "collector_exception",
                    "error": _safe_error(exc),
                })
            if self.request_pacing_seconds:
                time.sleep(self.request_pacing_seconds)

        incoming_awards = pd.DataFrame(award_rows, columns=AWARD_COLUMNS)
        incoming_actions = pd.DataFrame(action_rows, columns=ACTION_COLUMNS)
        if (
            requested_entities > 0
            and award_complete_entities == requested_entities
            and not unknown_tickers
            and award_normalization_failures == 0
            and award_rejected_without_key == 0
            and full_configured_universe
        ):
            awards_state = "complete"
        elif award_complete_entities or award_partial_entities:
            awards_state = "partial"
        else:
            awards_state = "failed"

        if self.max_action_awards_per_entity <= 0:
            detail_state = "not_requested"
            actions_state = "not_requested"
        elif detail_candidates == 0:
            detail_state = "complete" if awards_state == "complete" else "partial"
            actions_state = "complete" if awards_state == "complete" else "partial"
        else:
            detail_state = (
                "complete"
                if (
                    detail_succeeded == detail_candidates
                    and detail_skipped_missing_identifier == 0
                    and awards_state == "complete"
                )
                else "partial"
            )
            actions_state = (
                "complete"
                if (
                    action_awards_succeeded == detail_candidates
                    and action_awards_partial == 0
                    and action_awards_failed == 0
                    and action_awards_not_requested == 0
                    and awards_state == "complete"
                )
                else "partial"
            )

        prior_rails = previous_status.get("rails") if isinstance(previous_status.get("rails"), dict) else {}

        def prior_last_good(rail: str) -> str | None:
            prior_rail = prior_rails.get(rail) if isinstance(prior_rails, dict) else None
            if isinstance(prior_rail, dict) and _text(prior_rail.get("last_successful_observed_at")):
                return _text(prior_rail.get("last_successful_observed_at"))
            return _text(previous_status.get("last_successful_observed_at"))

        receipt_failure = False
        try:
            receipt_summary = _append_collection_receipts(
                receipts,
                data_dir / COLLECTION_RECEIPTS_FILENAME,
            )
        except Exception as exc:  # noqa: BLE001 - no ledger mutation without collection receipts
            receipt_failure = True
            receipt_summary = {
                "schema_version": COLLECTION_RECEIPT_SCHEMA,
                "path": COLLECTION_RECEIPTS_FILENAME,
                "response_receipts_this_run": len(receipts),
                "new_receipts_this_run": 0,
                "raw_response_bodies_persisted": False,
                "error": _safe_error(exc),
            }
            errors.append({
                "stage": "collection_receipt",
                "reason": "persist_failed",
                "error": _safe_error(exc),
            })

        persisted = False
        totals: dict[str, int] = {
            "awards_seen": int(len(incoming_awards)),
            "awards_total": _as_int(previous_status.get("awards_total")),
            "actions_seen": int(len(incoming_actions)),
            "actions_total": _as_int(previous_status.get("actions_total")),
            "snapshots_total": _as_int(previous_status.get("snapshots_total")),
        }
        # A partial source run can accrue successfully read rows, but its last-good
        # clock stays fixed.  A total award-query failure does not touch any ledger.
        if not receipt_failure and award_pages_succeeded > 0:
            try:
                totals = self.persist(incoming_awards, incoming_actions, observed_at)
                persisted = True
            except Exception as exc:  # noqa: BLE001 - atomic writes retain old artifacts on failure
                errors.append({
                    "stage": "persist",
                    "reason": "ledger_write_failed",
                    "error": _safe_error(exc),
                })

        if receipt_failure or not persisted:
            run_state = "failed"
        elif (
            awards_state == "complete"
            and detail_state in {"complete", "not_requested"}
            and actions_state in {"complete", "not_requested"}
        ):
            run_state = "ok"
        else:
            run_state = "partial"
        last_good = observed_at if run_state == "ok" else _text(previous_status.get("last_successful_observed_at"))

        # Rail state describes what the product can safely publish, not merely
        # what upstream returned.  If receipt binding or atomic persistence
        # failed, none of the newly fetched pages advances a current rail even
        # when its source pagination was otherwise complete.
        if not persisted:
            awards_state = "failed"
            if detail_state != "not_requested":
                detail_state = "failed"
            if actions_state != "not_requested":
                actions_state = "failed"

        rails = {
            "awards": {
                "state": awards_state,
                "last_successful_observed_at": (
                    observed_at if awards_state == "complete" and persisted else prior_last_good("awards")
                ),
                "pages": {
                    "requested": award_pages_requested,
                    "succeeded": award_pages_succeeded,
                    "safety_cap_per_entity": self.max_pages,
                    "unresolved_has_next_entities": award_unresolved_has_next,
                    "missing_has_next_entities": award_missing_has_next,
                },
                "records": {
                    "raw": award_raw_records,
                    "accepted": award_accepted_records,
                    "normalized": len(incoming_awards),
                    "ledger_total": _as_int(totals.get("awards_total")),
                },
                "denominators": {
                    "entities_requested": requested_entities,
                    "entities_mapped": len(entity_items),
                    "entities_configured_total": len(entities),
                    "full_configured_universe": full_configured_universe,
                    "queries_complete": award_complete_entities,
                    "queries_partial": award_partial_entities,
                    "queries_failed": award_failed_entities,
                    "normalization_failures": award_normalization_failures,
                    "records_rejected_without_identity": award_rejected_without_key,
                },
                "completeness": {
                    "state": awards_state,
                    "full_usaspending_corpus": False,
                    "scope": "recipient-query contract awards in the configured time window only",
                    "claim": "complete only when every mapped recipient query returned explicit hasNext=false before its safety cap",
                },
                "response_receipts": len([row for row in receipts if row.get("rail") == "awards"]),
            },
            "award_detail": {
                "state": detail_state,
                "last_successful_observed_at": (
                    observed_at if detail_state == "complete" and persisted else prior_last_good("award_detail")
                ),
                "pages": {
                    "requested": detail_attempted,
                    "succeeded": detail_succeeded,
                    "safety_cap_per_entity": self.max_action_awards_per_entity,
                },
                "records": {
                    "candidate_awards": detail_candidates,
                    "details_fetched": detail_succeeded,
                    "ledger_total": _as_int(totals.get("awards_total")),
                },
                "denominators": {
                    "candidate_awards": detail_candidates,
                    "attempted": detail_attempted,
                    "succeeded": detail_succeeded,
                    "skipped_missing_generated_award_id": detail_skipped_missing_identifier,
                },
                "completeness": {
                    "state": detail_state,
                    "full_usaspending_corpus": False,
                    "scope": "top reported-obligation awards among source rows returned for each entity",
                    "claim": "bounded award-detail sample; never a full award-detail corpus",
                    "sample_is_globally_ranked": awards_state == "complete",
                },
                "response_receipts": len([row for row in receipts if row.get("rail") == "award_detail"]),
            },
            "actions": {
                "state": actions_state,
                "last_successful_observed_at": (
                    observed_at if actions_state == "complete" and persisted else prior_last_good("actions")
                ),
                "pages": {
                    "requested": action_pages_requested,
                    "succeeded": action_pages_succeeded,
                    "safety_cap_per_award": self.max_action_pages,
                    "unresolved_has_next_awards": action_unresolved_has_next,
                    "missing_has_next_awards": action_missing_has_next,
                },
                "records": {
                    "raw": action_raw_records,
                    "accepted": action_accepted_records,
                    "normalized": len(incoming_actions),
                    "ledger_total": _as_int(totals.get("actions_total")),
                },
                "denominators": {
                    "sampled_awards": detail_candidates,
                    "queries_attempted": action_awards_attempted,
                    "queries_complete": action_awards_succeeded,
                    "queries_partial": action_awards_partial,
                    "queries_failed": action_awards_failed,
                    "queries_not_requested": action_awards_not_requested,
                },
                "completeness": {
                    "state": actions_state,
                    "full_usaspending_corpus": False,
                    "scope": "complete transaction history only for the bounded award-detail sample",
                    "claim": "actions paginate until explicit hasNext=false; an unresolved safety-cap hit is partial",
                },
                "response_receipts": len([row for row in receipts if row.get("rail") == "actions"]),
            },
        }
        receipt_summary["run_id"] = run_id
        receipt_summary["receipt_payloads_sha256"] = _sha256_json(receipts)
        status = {
            "schema_version": INGEST_STATUS_SCHEMA,
            "observed_at": observed_at,
            "effective_at": end.isoformat(),
            "status": run_state,
            "partial": run_state != "ok",
            "last_successful_observed_at": last_good,
            "freshness": {
                "state": "fresh" if run_state == "ok" else run_state,
                "last_good_at": last_good,
            },
            "entities_requested": requested_entities,
            "entities_mapped": len(entity_items),
            "entities_configured_total": len(entities),
            "full_configured_universe": full_configured_universe,
            "entities_with_awards": entities_with_awards,
            "bounded": True,
            "coverage_scope": "bounded recipient-query award data plus bounded award-detail/action sample; not full USAspending coverage",
            "lookback_days": int(lookback_days),
            "page_size": self.page_size,
            "max_pages_per_entity": self.max_pages,
            "award_search_limit_per_entity": self.page_size * self.max_pages,
            "detail_awards_limit_per_entity": self.max_action_awards_per_entity,
            "action_page_size": self.action_page_size,
            "max_action_pages_per_award": self.max_action_pages,
            "detail_awards_attempted": detail_attempted,
            "detail_awards_succeeded": detail_succeeded,
            "action_awards_attempted": action_awards_attempted,
            "action_awards_succeeded": action_awards_succeeded,
            "awards_seen": _as_int(totals.get("awards_seen")),
            "awards_total": _as_int(totals.get("awards_total")),
            "actions_seen": _as_int(totals.get("actions_seen")),
            "actions_total": _as_int(totals.get("actions_total")),
            "snapshots_total": _as_int(totals.get("snapshots_total")),
            "rails": rails,
            "collection_receipts": receipt_summary,
            "errors": errors,
            "source_urls": [AWARDS_URL, AWARD_DETAIL_URL, TRANSACTIONS_URL],
        }
        _atomic_json(status, status_path)
        return status

    def persist(
        self,
        incoming_awards: pd.DataFrame,
        incoming_actions: pd.DataFrame,
        observed_at: str,
    ) -> dict:
        data_dir = self.root / "data" / "government_revenue"
        award_path = data_dir / "awards.parquet"
        action_path = data_dir / "award_actions.parquet"
        snapshot_path = data_dir / "award_snapshots.parquet"
        existing_awards = _read_existing(award_path, AWARD_COLUMNS)
        existing_actions = _read_existing(action_path, ACTION_COLUMNS)
        existing_snapshots = _ensure_snapshot_hashes(_ensure_award_keys(
            _read_existing(snapshot_path, SNAPSHOT_COLUMNS)
        ).reindex(columns=SNAPSHOT_COLUMNS))

        merged_awards = _normalize_classification_cells(
            merge_awards(existing_awards, incoming_awards)
        )
        merged_actions = append_first_seen(
            existing_actions, incoming_actions, ["ticker", "action_id"], ACTION_COLUMNS
        )
        incoming_keys = _ensure_award_keys(incoming_awards).reindex(
            columns=["ticker", "award_key"]
        ).dropna().drop_duplicates()
        observed_awards = merged_awards.merge(
            incoming_keys,
            on=["ticker", "award_key"],
            how="inner",
        ) if not incoming_keys.empty else pd.DataFrame(columns=AWARD_COLUMNS)
        daily = snapshot_rows(observed_awards, observed_at)
        merged_snapshots = _normalize_classification_cells(
            append_snapshot_versions(existing_snapshots, daily)
        )
        _atomic_parquet(merged_awards, award_path)
        _atomic_parquet(merged_actions, action_path)
        _atomic_parquet(merged_snapshots, snapshot_path)
        return {
            "awards_seen": int(len(incoming_awards)),
            "awards_total": int(len(merged_awards)),
            "actions_seen": int(len(incoming_actions)),
            "actions_total": int(len(merged_actions)),
            "snapshots_total": int(len(merged_snapshots)),
        }


class UsaspendingAwardsAdapter(Adapter):
    """Standard nightly-runner wrapper around the composite-key collector.

    The granular ledgers persist inside ``UsaspendingAwardsCollector`` because the
    standard store is date-indexed and would collapse multiple awards on the same date.
    A small dated heartbeat gives the runner normal freshness/circuit-breaker behavior.
    """

    name = "usaspending_awards"
    group = "government_revenue"
    stale_after_days = 4

    def stored_series(self) -> list[str]:
        """Expose only the runner-owned date-indexed heartbeat to base health.

        The sibling award/action/snapshot Parquets use composite-key RangeIndexes
        and are owned by ``UsaspendingAwardsCollector``; generic store freshness
        code must never reinterpret them as time-series stores.
        """
        return ["collector_heartbeat"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        status = UsaspendingAwardsCollector(root=config.ROOT).collect(
            lookback_days=3652 if full_history else 1826
        )
        return {"collector_heartbeat": heartbeat_frame(status)}


def heartbeat_frame(status: dict) -> pd.DataFrame:
    """Build the standard date-indexed health row from a composite-ledger run."""
    observed = pd.Timestamp(status["observed_at"])
    if observed.tzinfo is not None:
        observed = observed.tz_convert(None)
    observed = observed.normalize()
    rails = status.get("rails") if isinstance(status.get("rails"), dict) else {}
    award_pages = (rails.get("awards") or {}).get("pages") if isinstance(rails.get("awards"), dict) else {}
    action_pages = (rails.get("actions") or {}).get("pages") if isinstance(rails.get("actions"), dict) else {}
    row = {
        "awards_seen": float(status.get("awards_seen", 0)),
        "awards_total": float(status.get("awards_total", 0)),
        "actions_seen": float(status.get("actions_seen", 0)),
        "actions_total": float(status.get("actions_total", 0)),
        "snapshots_total": float(status.get("snapshots_total", 0)),
        "errors": float(len(status.get("errors") or [])),
        "collection_complete": float(status.get("status") == "ok"),
        "collection_partial": float(status.get("status") in {"partial", "failed"}),
        "award_pagination_unresolved": float(
            _as_int((award_pages or {}).get("unresolved_has_next_entities"))
            + _as_int((award_pages or {}).get("missing_has_next_entities"))
        ),
        "action_pagination_unresolved": float(
            _as_int((action_pages or {}).get("unresolved_has_next_awards"))
            + _as_int((action_pages or {}).get("missing_has_next_awards"))
        ),
    }
    return pd.DataFrame([row], index=[observed])


def write_heartbeat(status: dict, root: Path) -> Path:
    """Persist CLI-run health exactly where the standard Adapter runner would."""
    path = Path(root) / "data" / "government_revenue" / "collector_heartbeat.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        heartbeat_frame(status).to_parquet(tmp, index=True)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--ticker", action="append", dest="tickers")
    parser.add_argument("--as-of")
    parser.add_argument("--max-pages", type=int, default=2)
    parser.add_argument("--max-action-awards", type=int, default=8)
    parser.add_argument("--action-page-size", type=int, default=5000)
    parser.add_argument("--max-action-pages", type=int, default=100)
    parser.add_argument("--lookback-days", type=int, default=1826)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    collector = UsaspendingAwardsCollector(
        root=args.root,
        max_pages=args.max_pages,
        max_action_awards_per_entity=args.max_action_awards,
        action_page_size=args.action_page_size,
        max_action_pages=args.max_action_pages,
    )
    status = collector.collect(args.tickers, as_of=args.as_of, lookback_days=args.lookback_days)
    write_heartbeat(status, args.root)
    print(json.dumps(status, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
