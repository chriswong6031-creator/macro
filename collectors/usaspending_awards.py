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
import json
import logging
import os
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
    "known_at",
    "effective_at",
    "first_seen_at",
    "source_url",
    "detail_source_url",
]


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
    for k, first_seen in old_first.items():
        if k in combined.index:
            combined.at[k, "first_seen_at"] = first_seen
    return combined.reset_index().reindex(columns=AWARD_COLUMNS)


def snapshot_rows(awards: pd.DataFrame, observed_at: str) -> pd.DataFrame:
    """Build the once-per-day current-state rows that make later PIT replay possible."""
    if awards.empty:
        return pd.DataFrame(columns=SNAPSHOT_COLUMNS)
    day = observed_at[:10]
    rows = []
    for _, award in awards.iterrows():
        rows.append({
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
        })
    return pd.DataFrame(rows, columns=SNAPSHOT_COLUMNS)


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


class UsaspendingAwardsCollector:
    """Bounded official-API collector with injectable session for hermetic tests."""

    def __init__(
        self,
        root: Path | None = None,
        session: requests.Session | None = None,
        page_size: int = 50,
        max_pages: int = 2,
        max_action_awards_per_entity: int = 8,
        request_pacing_seconds: float = 0.2,
        user_agent: str | None = None,
    ) -> None:
        self.root = Path(root).resolve() if root is not None else Path.cwd().resolve()
        self.session = session or requests.Session()
        self.page_size = max(1, min(int(page_size), 100))
        self.max_pages = max(1, int(max_pages))
        self.max_action_awards_per_entity = max(0, int(max_action_awards_per_entity))
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

    def fetch_awards(self, ticker: str, entity: dict, start_date: str, end_date: str) -> list[dict]:
        rows: list[dict] = []
        query = entity.get("recipient_search_text") or entity.get("name") or ticker
        for page in range(1, self.max_pages + 1):
            body = {
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
            payload = self._post(AWARDS_URL, body)
            results = payload.get("results") or []
            if not isinstance(results, list):
                raise ValueError("USAspending award results is not a list")
            rows.extend(x for x in results if isinstance(x, dict))
            metadata = payload.get("page_metadata") or {}
            if not metadata.get("hasNext") or not results:
                break
            if self.request_pacing_seconds:
                time.sleep(self.request_pacing_seconds)
        return rows

    def fetch_actions(self, award: dict) -> list[dict]:
        generated = award.get("generated_award_id")
        if not generated:
            return []
        body = {
            "award_id": generated,
            "page": 1,
            "sort": "action_date",
            "order": "desc",
            "limit": 5000,
        }
        payload = self._post(TRANSACTIONS_URL, body)
        results = payload.get("results") or []
        if not isinstance(results, list):
            raise ValueError("USAspending transaction results is not a list")
        return [x for x in results if isinstance(x, dict)]

    def fetch_award_detail(self, award: dict) -> dict:
        generated = award.get("generated_award_id")
        if not generated:
            return {}
        return self._get(AWARD_DETAIL_URL.format(award_id=generated))

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
        award_rows: list[dict] = []
        action_rows: list[dict] = []
        errors: list[dict] = []
        entities_with_awards = 0
        detail_attempted = 0
        detail_succeeded = 0
        action_awards_attempted = 0
        action_awards_succeeded = 0

        for ticker, entity in entities.items():
            if selected is not None and ticker not in selected:
                continue
            try:
                raw_awards = self.fetch_awards(ticker, entity, start.isoformat(), end.isoformat())
                normalized = [normalize_award(x, ticker, observed_at) for x in raw_awards]
                normalized = [x for x in normalized if x.get("award_key")]
                if normalized:
                    entities_with_awards += 1
                candidate_keys = {
                    x.get("award_key")
                    for x in sorted(
                        normalized,
                        key=lambda x: x.get("total_obligated") or 0.0,
                        reverse=True,
                    )[: self.max_action_awards_per_entity]
                }
                enriched: list[dict] = []
                for award in normalized:
                    if award.get("award_key") not in candidate_keys:
                        enriched.append(award)
                        continue
                    detail_attempted += 1
                    try:
                        award = enrich_award(award, self.fetch_award_detail(award))
                        detail_succeeded += 1
                    except Exception as exc:  # noqa: BLE001 - detail is additive per award
                        errors.append({
                            "ticker": ticker,
                            "stage": "award_detail",
                            "award_id": award.get("award_id"),
                            "error": str(exc),
                        })
                    enriched.append(award)
                    if self.request_pacing_seconds:
                        time.sleep(self.request_pacing_seconds)
                award_rows.extend(enriched)
                candidates = sorted(
                    [x for x in enriched if x.get("award_key") in candidate_keys],
                    key=lambda x: x.get("total_obligated") or 0.0,
                    reverse=True,
                )
                for award in candidates:
                    action_awards_attempted += 1
                    try:
                        action_rows.extend(
                            normalize_action(x, award, observed_at) for x in self.fetch_actions(award)
                        )
                        action_awards_succeeded += 1
                    except Exception as exc:  # noqa: BLE001 - one award cannot sink the entity
                        errors.append({
                            "ticker": ticker,
                            "stage": "actions",
                            "award_id": award.get("award_id"),
                            "error": str(exc),
                        })
                    if self.request_pacing_seconds:
                        time.sleep(self.request_pacing_seconds)
            except Exception as exc:  # noqa: BLE001 - retain other mapped recipients
                errors.append({"ticker": ticker, "stage": "awards", "error": str(exc)})
            if self.request_pacing_seconds:
                time.sleep(self.request_pacing_seconds)

        incoming_awards = pd.DataFrame(award_rows, columns=AWARD_COLUMNS)
        incoming_actions = pd.DataFrame(action_rows, columns=ACTION_COLUMNS)
        if incoming_awards.empty and errors:
            raise RuntimeError(f"USAspending award collection returned no usable rows: {errors[:3]}")
        status = self.persist(incoming_awards, incoming_actions, observed_at)
        status.update({
            "schema_version": "government_revenue.ingest_status.v1",
            "observed_at": observed_at,
            "effective_at": end.isoformat(),
            "entities_requested": len(selected) if selected is not None else len(entities),
            "entities_with_awards": entities_with_awards,
            "bounded": True,
            "lookback_days": int(lookback_days),
            "page_size": self.page_size,
            "max_pages_per_entity": self.max_pages,
            "award_search_limit_per_entity": self.page_size * self.max_pages,
            "detail_awards_limit_per_entity": self.max_action_awards_per_entity,
            "detail_awards_attempted": detail_attempted,
            "detail_awards_succeeded": detail_succeeded,
            "action_awards_attempted": action_awards_attempted,
            "action_awards_succeeded": action_awards_succeeded,
            "errors": errors,
            "source_urls": [AWARDS_URL, AWARD_DETAIL_URL, TRANSACTIONS_URL],
        })
        _atomic_json(status, self.root / "data" / "government_revenue" / "ingest_status.json")
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
        existing_snapshots = _ensure_award_keys(
            _read_existing(snapshot_path, SNAPSHOT_COLUMNS)
        ).reindex(columns=SNAPSHOT_COLUMNS)

        merged_awards = _normalize_classification_cells(
            merge_awards(existing_awards, incoming_awards)
        )
        merged_actions = append_first_seen(
            existing_actions, incoming_actions, ["ticker", "action_id"], ACTION_COLUMNS
        )
        daily = snapshot_rows(incoming_awards, observed_at)
        merged_snapshots = _normalize_classification_cells(append_first_seen(
            existing_snapshots,
            daily,
            ["ticker", "award_key", "snapshot_date"],
            SNAPSHOT_COLUMNS,
        ))
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
    row = {
        "awards_seen": float(status.get("awards_seen", 0)),
        "awards_total": float(status.get("awards_total", 0)),
        "actions_seen": float(status.get("actions_seen", 0)),
        "actions_total": float(status.get("actions_total", 0)),
        "snapshots_total": float(status.get("snapshots_total", 0)),
        "errors": float(len(status.get("errors") or [])),
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
    parser.add_argument("--lookback-days", type=int, default=1826)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    collector = UsaspendingAwardsCollector(
        root=args.root,
        max_pages=args.max_pages,
        max_action_awards_per_entity=args.max_action_awards,
    )
    status = collector.collect(args.tickers, as_of=args.as_of, lookback_days=args.lookback_days)
    write_heartbeat(status, args.root)
    print(json.dumps(status, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
