"""Mastermind Data OS — the convergence spine, not a new stack.

THE THESIS (§D0).  This repo does not lack point-in-time or contract discipline.  It
contains **at least six independent, locally-correct implementations of it** —
Calcbench 5-clock bitemporal fundamentals, FRED/ALFRED vintage as-of reads, the CN
TuShare generation-atomic PIT universe, ``basket_membership_pit`` append-only
snapshots, ``collectors/base.py::ColumnContract`` per-column freshness, and
``engine/canon.py``'s golden-vector concept canon — which share **no vocabulary, no
registry and no enforcement**.  Correctness is therefore per-module and globally
unverifiable, and every new session re-invents the same wheel a seventh time.

**The Data OS is a convergence and enforcement spine over patterns the house already
proved.**  Corollary that governs every addition here: *the boring answer already
exists in this repo.*  Anything that is not an extension of an in-repo pattern must
name the specific requirement the in-repo pattern fails.

What each module owns:

``identity``   §D2 — a symbol is never an identity.  Listing keys, issuer/security
               ids, instrument-class ids, CN/HK symbol normalization, and a
               TIME-SCOPED vendor alias table.  Motivated by the MMC->MRSH rename that
               left ``data/baskets/ohlcv/MMC.parquet`` nonexistent for seven months.
``temporal``   §D3 — the seven named times, six temporal profiles, and the fail-closed
               PIT law: a profile that cannot answer ``known_at`` RAISES rather than
               silently returning the latest vintage.
``price``      §D4 — the naming law.  No stored price column may be named ``close``,
               ``price`` or ``value`` without a basis suffix; ``KNOWN_STORE_BASES``
               records the measured truth of the stores that exist today.
``nulls``      §D6 — the closed missing-reason vocabulary.  ``0`` may never be written
               to mean absence.
``registry``   §D5/§D9 — ``DatasetContract``, the registry file, and the static
               lineage DAG.  No new store.
``quality``    §D8 — nine check families x four severities, as PURE validators.

WHAT THIS IS NOT (§D11).  Not Kafka, Snowflake, Databricks, a data mesh, a lineage
SaaS, event sourcing, a feature store (§D10 verdict: NO), a rewrite of any store, or a
second control plane / authority map — the last is explicitly prohibited cross-repo
(``duplicate_control_planes``, Mastermind AGENTS.md).

STDLIB ONLY at import time.  ``yaml`` is imported lazily inside
``registry.load_registry`` and pandas appears nowhere, so every module here is
importable in the thin CI lanes and inside a collector that must not pay a dataframe
import to translate a ticker.
"""
from __future__ import annotations

from lib.dataos.identity import (
    AliasRow,
    CNBoard,
    IdentityError,
    KNOWN_MICS,
    ListingKey,
    VendorAliasTable,
    cn_board,
    fx_id,
    future_id,
    index_id,
    is_legacy_bse_code,
    issuer_id,
    listing_id,
    normalize_cn_symbol,
    normalize_hk_symbol,
    option_contract_id,
    parse_fx_id,
    parse_future_id,
    parse_id,
    parse_index_id,
    parse_listing_key,
    parse_option_contract_id,
    security_id,
)
from lib.dataos.nulls import MissingReason, NullPolicy, validate_value
from lib.dataos.price import (
    AMBIGUOUS_NAMES,
    AdjustmentBasis,
    KNOWN_STORE_BASES,
    PriceError,
    PriceField,
    Session,
    VenueScope,
    canonical_column,
    is_ambiguous,
    parse_column,
)
from lib.dataos.quality import (
    CheckFamily,
    Finding,
    Severity,
    check_completeness,
    check_freshness,
    check_referential,
    check_temporal_integrity,
    check_uniqueness,
    check_validity_ohlc,
    emit_annotations,
)
from lib.dataos.registry import (
    ConflictPolicy,
    DatasetContract,
    DatasetStatus,
    Layer,
    REGISTRY_PATH,
    Registry,
    RegistryError,
    load_registry,
    validate_registry,
)
from lib.dataos.temporal import (
    Clock,
    KNOWN_AT_CLOCKS,
    PointInTimeError,
    TemporalError,
    TemporalProfile,
    as_of_filter,
    assert_pit_readable,
    known_at,
    utc,
)

__all__ = [
    # identity (§D2)
    "IdentityError", "KNOWN_MICS", "ListingKey", "parse_listing_key",
    "listing_id", "security_id", "issuer_id", "parse_id",
    "option_contract_id", "parse_option_contract_id",
    "future_id", "parse_future_id", "index_id", "parse_index_id",
    "fx_id", "parse_fx_id",
    "CNBoard", "cn_board", "is_legacy_bse_code",
    "normalize_cn_symbol", "normalize_hk_symbol",
    "AliasRow", "VendorAliasTable",
    # temporal (§D3)
    "TemporalError", "PointInTimeError", "Clock", "TemporalProfile",
    "KNOWN_AT_CLOCKS", "utc", "known_at", "assert_pit_readable", "as_of_filter",
    # price (§D4)
    "PriceError", "AdjustmentBasis", "PriceField", "Session", "VenueScope",
    "canonical_column", "parse_column", "AMBIGUOUS_NAMES", "is_ambiguous",
    "KNOWN_STORE_BASES",
    # registry (§D5/§D9)
    "RegistryError", "Layer", "DatasetStatus", "ConflictPolicy",
    "DatasetContract", "Registry", "REGISTRY_PATH", "load_registry",
    "validate_registry",
    # nulls (§D6)
    "MissingReason", "NullPolicy", "validate_value",
    # quality (§D8)
    "Severity", "CheckFamily", "Finding",
    "check_uniqueness", "check_validity_ohlc", "check_freshness",
    "check_completeness", "check_referential", "check_temporal_integrity",
    "emit_annotations",
]
