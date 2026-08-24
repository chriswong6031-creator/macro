"""FIF-3A1/3A2: authenticated as-reported statement read over golden AAPL packages.

Admission is a dedicated statement contract. It reuses FIF-2 transport laws
(duplicate JSON keys, UTF-8, 64 KiB, binary-float rejection) without opening
the query metric/period kernel. Provider.resolve is never called before
admission succeeds. No request-time network. No implicit now.
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .financial_intelligence_packet import load_core_registry
from .query_service import (
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    FinancialQueryAdmissionError,
    FinancialQueryUnavailableError,
    admit_request_bytes,
)
from .raw_ledger import canonical_json
from .statement_graph import (
    GOLDEN_AAPL_FIXTURES,
    GoldenFilingPackage,
    StatementGraphError,
    load_golden_aapl_package,
    reconstruct_primary_statements,
)

_REQUEST_SCHEMA = "fundamental_forensics.financial_statement_request/v1"
_RESPONSE_SCHEMA = "fundamental_forensics.financial_statement_response/v1"
_REQUIRED_ROOT_FIELDS = frozenset({"schema", "entity_id", "accession"})
_GOLDEN_ENTITY_ID = "ISS:US-XNAS-AAPL"
_RELATED_EVENT_REF_KEYS = frozenset(
    {"plane", "event_id", "relation", "source_filing_distinction"}
)


@dataclass(frozen=True)
class AdmittedStatementRequest:
    entity_id: str
    accession: str


@dataclass(frozen=True)
class FinancialStatementResult:
    body: bytes
    sha256: str
    envelope: dict[str, Any]


class FinancialStatementProvider:
    def resolve(self, entity_id: str, accession: str) -> GoldenFilingPackage:
        raise NotImplementedError


class UnavailableFinancialStatementProvider:
    def resolve(self, entity_id: str, accession: str) -> GoldenFilingPackage:
        raise FinancialQueryUnavailableError()


class GoldenAaplStatementProvider:
    """Serves only the committed AAPL golden filing set. No ticker. No latest."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]


    def resolve(self, entity_id: str, accession: str) -> GoldenFilingPackage:
        if entity_id != _GOLDEN_ENTITY_ID:
            raise FinancialQueryAdmissionError(400, "unknown entity")
        if accession not in GOLDEN_AAPL_FIXTURES:
            raise FinancialQueryAdmissionError(400, "unknown filing")
        try:
            return load_golden_aapl_package(self.repo_root, accession=accession)
        except StatementGraphError:
            raise FinancialQueryUnavailableError() from None


def admit_statement_request(body: bytes) -> AdmittedStatementRequest:
    parsed = admit_request_bytes(body)
    extra = set(parsed) - _REQUIRED_ROOT_FIELDS
    missing = _REQUIRED_ROOT_FIELDS - set(parsed)
    if extra or missing:
        raise FinancialQueryAdmissionError(400, "request contract violation")
    if parsed.get("schema") != _REQUEST_SCHEMA:
        raise FinancialQueryAdmissionError(400, "request contract violation")
    entity_id = parsed["entity_id"]
    accession = parsed["accession"]
    if isinstance(entity_id, float) or isinstance(accession, float):
        raise FinancialQueryAdmissionError(400, "request contract violation")
    if not isinstance(entity_id, str) or not entity_id:
        raise FinancialQueryAdmissionError(400, "request contract violation")
    if not isinstance(accession, str) or not accession:
        raise FinancialQueryAdmissionError(400, "request contract violation")
    return AdmittedStatementRequest(entity_id=entity_id, accession=accession)


def _load_security_records(repo_root: Path) -> list[dict[str, Any]]:
    try:
        import pandas as pd
    except Exception as exc:  # noqa: BLE001
        raise FinancialQueryUnavailableError() from exc
    path = Path(repo_root) / "data" / "reference" / "security_master.parquet"
    if not path.is_file():
        raise FinancialQueryUnavailableError()
    return pd.read_parquet(path).to_dict("records")


def _load_issuer_metadata(repo_root: Path, entity_id: str) -> dict[str, str]:
    try:
        import pandas as pd
    except Exception as exc:  # noqa: BLE001
        raise FinancialQueryUnavailableError() from exc
    path = Path(repo_root) / "data" / "reference" / "issuer_master.parquet"
    if not path.is_file():
        raise FinancialQueryUnavailableError()
    issuers = pd.read_parquet(path)
    rows = issuers[issuers["issuer_id"] == entity_id]
    if len(rows) != 1:
        raise FinancialQueryAdmissionError(400, "unknown entity")
    row = rows.iloc[0]
    cik = str(row["cik"]).zfill(10)
    return {
        "cik": cik,
        "legal_name": str(row.get("legal_name") or ""),
    }


def bind_canonical_identity(
    entity_id: str,
    *,
    issuer_master: Any,
    issuer_metadata: dict[str, str],
) -> dict[str, str]:
    """Resolve issuer→security through IssuerMaster only.

    Raw issuer/security tables may supply metadata after that canonical
    membership is known. FIF must not independently pick among securities.
    IssuerMaster is imported here so API module load does not pull Data OS
    identity into unrelated job import closures.
    """
    from lib.dataos.identity import IssuerMaster

    if not isinstance(issuer_master, IssuerMaster):
        raise FinancialQueryUnavailableError()
    securities = issuer_master.securities_of_issuer(entity_id)
    if len(securities) != 1:
        raise FinancialQueryAdmissionError(400, "unknown entity")
    security_id = securities[0]
    row = next((item for item in issuer_master.rows if item.security_id == security_id), None)
    if row is None:
        raise FinancialQueryAdmissionError(400, "unknown entity")
    cik = str(issuer_metadata.get("cik") or "").zfill(10)
    if len(cik) != 10 or not cik.isdigit():
        raise FinancialQueryUnavailableError()
    return {
        "entity_id": entity_id,
        "cik": cik,
        "security_id": security_id,
        "listing_key": row.listing_key,
        "legal_name": str(issuer_metadata.get("legal_name") or ""),
    }


def _bind_data_os_issuer(
    repo_root: Path,
    entity_id: str,
    *,
    issuer_master: Any | None = None,
    issuer_metadata: dict[str, str] | None = None,
) -> dict[str, str]:
    from lib.dataos.identity import IssuerMaster

    if issuer_master is None:
        issuer_master = IssuerMaster.from_records(_load_security_records(repo_root))
    if issuer_metadata is None:
        issuer_metadata = _load_issuer_metadata(repo_root, entity_id)
    return bind_canonical_identity(
        entity_id,
        issuer_master=issuer_master,
        issuer_metadata=issuer_metadata,
    )


def _related_event_ref(manifest: dict[str, Any]) -> dict[str, Any] | None:
    raw = manifest.get("related_event_ref")
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) != _RELATED_EVENT_REF_KEYS:
        raise FinancialQueryUnavailableError()
    distinction = raw.get("source_filing_distinction")
    if not isinstance(distinction, dict):
        raise FinancialQueryUnavailableError()
    eight_k = distinction.get("earnings_release_8k_accession")
    periodic = distinction.get("periodic_report_accession")
    if eight_k == periodic:
        raise FinancialQueryUnavailableError()
    return {
        "plane": raw["plane"],
        "event_id": raw["event_id"],
        "relation": raw["relation"],
        "source_filing_distinction": {
            "earnings_release_8k_accession": eight_k,
            "periodic_report_accession": periodic,
        },
    }


def execute_financial_statements(
    *,
    body: bytes,
    repo_root: Path,
    provider: FinancialStatementProvider | None = None,
    provider_factory: Callable[[], FinancialStatementProvider] | None = None,
    issuer_master: Any | None = None,
    issuer_metadata: dict[str, str] | None = None,
) -> FinancialStatementResult:
    admitted = admit_statement_request(body)
    binding = _bind_data_os_issuer(
        repo_root,
        admitted.entity_id,
        issuer_master=issuer_master,
        issuer_metadata=issuer_metadata,
    )
    if provider is None:
        if provider_factory is None:
            raise FinancialQueryUnavailableError()
        provider = provider_factory()
    package = provider.resolve(admitted.entity_id, admitted.accession)
    if package.manifest.get("entity_id") != binding["entity_id"]:
        raise FinancialQueryUnavailableError()
    if package.manifest.get("cik") != binding["cik"]:
        raise FinancialQueryUnavailableError()
    if package.manifest.get("accession") != admitted.accession:
        raise FinancialQueryUnavailableError()
    try:
        registry = load_core_registry(repo_root)
        reconstructed = reconstruct_primary_statements(package=package, registry=registry)
    except FinancialQueryAdmissionError:
        raise
    except StatementGraphError:
        raise FinancialQueryUnavailableError() from None
    except Exception:
        raise FinancialQueryUnavailableError() from None

    envelope = {
        "schema": _RESPONSE_SCHEMA,
        "entity": {
            "entity_id": binding["entity_id"],
            "cik": binding["cik"],
            "source_entity_id": binding["cik"],
            "security_id": binding["security_id"],
            "listing_key": binding["listing_key"],
            "legal_name": binding["legal_name"],
        },
        "filing": {
            "accession": package.manifest["accession"],
            "form": package.manifest["form"],
            "primary_document": package.manifest["primary_document"],
            "period_of_report": package.manifest["period_of_report"],
            "filing_date": package.manifest["filing_date"],
            "source_accepted_at": package.manifest["source_accepted_at"],
            "fixture_recorded_at": package.manifest.get("fixture_recorded_at"),
        },
        "package": {
            "archive_index_url": package.manifest["archive_index_url"],
            "index_sha256": package.manifest["index_sha256"],
            "member_count": package.manifest["member_count"],
            "retained_count": package.manifest["retained_count"],
            "members": [
                {
                    "name": item["name"],
                    "state": item["state"],
                    "role": item.get("role"),
                    "content_sha256": item.get("content_sha256"),
                    "byte_length": item.get("byte_length"),
                }
                for item in package.manifest["members"]
            ],
        },
        "authority": {
            "class": "context_only",
            "display_only": True,
        },
        "statements": reconstructed["statements"],
        "coverage": {
            "parsed_document_kind": reconstructed["parsed_document_kind"],
            "fact_count": reconstructed["fact_count"],
            "context_count": reconstructed["context_count"],
        },
        "delivery": {
            "kind": "committed_golden_fixture",
            "attested": False,
            "production_issuer_service": False,
        },
    }
    related = _related_event_ref(package.manifest)
    if related is not None:
        envelope["related_event_ref"] = related
    body_out = canonical_json(envelope).encode("utf-8")
    if len(body_out) > MAX_RESPONSE_BYTES:
        raise FinancialQueryAdmissionError(413, "response exceeds bound")
    digest = hashlib.sha256(body_out).hexdigest()
    return FinancialStatementResult(body=body_out, sha256=digest, envelope=envelope)


__all__ = [
    "AdmittedStatementRequest",
    "FinancialStatementProvider",
    "FinancialStatementResult",
    "GoldenAaplStatementProvider",
    "UnavailableFinancialStatementProvider",
    "admit_statement_request",
    "bind_canonical_identity",
    "execute_financial_statements",
    "MAX_REQUEST_BYTES",
]
