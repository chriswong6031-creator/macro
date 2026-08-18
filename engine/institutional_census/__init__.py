"""Institutional-manager census source and projection contracts.

The public SEC-source names stay available from this package, but importing a
lightweight submodule such as :mod:`models` or :mod:`storage` must not pull the
dataframe parser stack into isolated evidence-store runtimes.
"""
from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .sec_sources import (
        ATOM_EPHEMERAL_ENTRY_LIMIT,
        ATOM_HONORED_PAGE_SIZES,
        ATOM_PAGE_SIZE,
        AtomScanResult,
        BulkInvariantFinding,
        BulkTables,
        COVER_PAGE_COLUMNS,
        FilingDiscovery,
        FilingIndexDocument,
        FORM_TYPES,
        HOLDING_COLUMNS,
        INCLUDED_MANAGER_COLUMNS,
        LATEST_FILINGS_ATOM_URL,
        REPORTED_BY_COLUMNS,
        SUBMISSION_COLUMNS,
        SUMMARY_PAGE_COLUMNS,
        SecSourceError,
        iter_bulk_holding_chunks,
        normalize_accession,
        normalize_cik,
        normalize_date,
        normalize_timestamp,
        parse_filing_index,
        parse_filing_package,
        parse_latest_filings_atom,
        parse_master_index,
        read_bulk_package,
        read_filing_package,
        scan_latest_filings_atom,
        validate_bulk_invariants,
    )

__all__ = [
    "ATOM_EPHEMERAL_ENTRY_LIMIT",
    "ATOM_HONORED_PAGE_SIZES",
    "ATOM_PAGE_SIZE",
    "AtomScanResult",
    "BulkInvariantFinding",
    "BulkTables",
    "COVER_PAGE_COLUMNS",
    "FilingDiscovery",
    "FilingIndexDocument",
    "FORM_TYPES",
    "HOLDING_COLUMNS",
    "INCLUDED_MANAGER_COLUMNS",
    "LATEST_FILINGS_ATOM_URL",
    "REPORTED_BY_COLUMNS",
    "SUBMISSION_COLUMNS",
    "SUMMARY_PAGE_COLUMNS",
    "SecSourceError",
    "iter_bulk_holding_chunks",
    "parse_filing_index",
    "parse_filing_package",
    "parse_latest_filings_atom",
    "parse_master_index",
    "read_bulk_package",
    "read_filing_package",
    "normalize_accession",
    "normalize_cik",
    "normalize_date",
    "normalize_timestamp",
    "scan_latest_filings_atom",
    "validate_bulk_invariants",
]


def __getattr__(name: str) -> Any:
    """Load the dataframe-backed SEC source surface only when it is requested."""
    if name == "sec_sources":
        value = import_module(f"{__name__}.sec_sources")
    elif name in __all__:
        value = getattr(import_module(f"{__name__}.sec_sources"), name)
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Advertise the stable lazy public surface to introspection tools."""
    return sorted({*globals(), *__all__, "sec_sources"})
