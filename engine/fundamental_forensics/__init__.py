"""Deterministic SEC/XBRL Fundamental Forensics kernel (fixture slice v1)."""
from .models import FindingState, KnowledgeClock, RunResult, VintagePolicy
from .normalize import ForensicsRegistry, load_registry, registry_from_dict
from .pipeline import run_fixture_slice
from .disclosure_diff import (
    DisclosureComparison,
    DisclosureDiffRegistry,
    DisclosureFinding,
    compare_filings,
    load_disclosure_diff_registry,
    normalize_filing,
)
from .sec_document_spine import (
    FILING_MANIFEST_SCHEMA,
    FilingManifestError,
    build_filing_manifests,
    select_periodic_comparables,
)
from .ixbrl_extraction import (
    FFXBRL_SCHEMA,
    IxbrlExtraction,
    IxbrlExtractionError,
    build_ixbrl_extraction,
    verify_ixbrl_extraction_source,
)
from .filing_attestation import (
    FILING_ATTESTATION_SCHEMA,
    CompanyFactsSourcePaths,
    FilingAttestation,
    FilingAttestationError,
    PinnedSourceAuthority,
    build_filing_attestation,
    verify_filing_attestation_source,
)

__all__ = [
    "FindingState",
    "FFXBRL_SCHEMA",
    "FILING_ATTESTATION_SCHEMA",
    "FILING_MANIFEST_SCHEMA",
    "FilingManifestError",
    "FilingAttestation",
    "FilingAttestationError",
    "ForensicsRegistry",
    "IxbrlExtraction",
    "IxbrlExtractionError",
    "CompanyFactsSourcePaths",
    "KnowledgeClock",
    "RunResult",
    "PinnedSourceAuthority",
    "VintagePolicy",
    "DisclosureComparison",
    "DisclosureDiffRegistry",
    "DisclosureFinding",
    "build_filing_manifests",
    "build_ixbrl_extraction",
    "build_filing_attestation",
    "compare_filings",
    "load_disclosure_diff_registry",
    "load_registry",
    "normalize_filing",
    "registry_from_dict",
    "run_fixture_slice",
    "select_periodic_comparables",
    "verify_ixbrl_extraction_source",
    "verify_filing_attestation_source",
]
