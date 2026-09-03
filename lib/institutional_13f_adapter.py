"""K2-C read-only institutional 13F owner-read adapter (pilot).

Composes EXISTING owner primitives only:

* ``engine.institutional_census.catalog`` / ``.storage`` / ``.models`` for the
  canonical institutional 13F evidence plane (catalog generations, filings,
  holdings rows, raw evidence receipts).
* ``lib.evidence_foundation`` for K1 ``EvidenceRef`` construction/validation.
* ``lib.institutional_intelligence`` (K2-B) for manager-research-intent
  recipe compilation.

This module adds zero owner code, no persistence, no schedule, and no
score/rank/gate/authority.  Every missing/ambiguous/rights/clock defect is a
*typed receipt state*, never a numeric zero and never a silently-swallowed
exception.  A genuine store outage or digest failure is an owner exception
and always propagates untouched -- it is never mistaken for typed absence,
and this module never retries any read.

**Owner-semantics law (post K2-C semantic-owner repair, 2026-09-03).** A
semantic positive (``PILOT_COMPILED``) requires BOTH of two owner-proven
seams for the same receipt: (1) the CUSIP is bound to one exact admitted
``SEC:`` security identity, and (2) the filer/vehicle context is bound to
truthful manager-complex/vehicle epochs -- including resolution state,
vehicle class and decision mode.  This module owns NEITHER seam.  A caller
supplies both, atomically, through the single keyword-only
``run_pilot(..., owner_semantics=...)`` channel; nothing else in this module
may originate that truth.  In particular: a 13F row's own
``investment_discretion`` field describes voting/investment AUTHORITY over
one reported position, never a vehicle's trading style, and is reported
verbatim in the per-period row blocks but feeds NO semantics anywhere; and a
filer CIK is a filer identifier, never a resolved manager-complex identity
-- this module mints no ``mcx_*``/``mce_*``/``veh_*``/``vie_*`` identity of
its own.  Validation of a supplied ``owner_semantics`` payload is strict and
fail-closed: anything missing, empty, wrong-typed, unresolved (the security
seam's own unresolved sentinel is never accepted as proof of resolution),
not a well-formed ``SEC:`` identity under the owner's own grammar,
structurally partial (missing any of the specific fields this adapter
itself reads out of an epoch -- never the full K2-B epoch schema, which the
K2-B compiler enforces once a recipe reaches it), or internally
self-contradictory (``status=="unresolved"`` alongside
``resolution_state=="resolved"``) makes the WHOLE payload unresolved (never
partially trusted), and the receipt then carries
``state=PILOT_OWNER_SEMANTICS_UNRESOLVED`` with no K2-B recipe ever
constructed -- refusing BEFORE construction rather than laundering
missingness through a placeholder vehicle class.  No current repository
producer supplies a lawful ``owner_semantics`` payload (see
``tests/test_institutional_13f_adapter_contract.py::
test_no_repo_producer_supplies_owner_manager_vehicle_epochs``); the CLI has
no flag for it either, by design (frozen spec point 8) -- a human-supplied
override would be exactly the back door this repair exists to close.

**Owner VERIFICATION gate (Sol review 5099850302 repair, 2026-09-03).** The
paragraph above describes SHAPE validation -- necessary, but proven
insufficient by adversarial review: a payload can satisfy every shape check
while still being wrong (a parseable ``SEC:`` identity that names the WRONG
security for the requested CUSIP; a vehicle epoch that links a
``manager_complex_id`` the manager epoch never claimed; a
``vehicle_class``/``decision_mode`` combination K2-B's own compiler would
reject), because no shape check can know the TRUTH of a caller's mapping --
only whether it is well-formed.  A shape-valid payload must therefore also
be bound to this exact request (cusip, cutoff, security id, epochs,
provenance) by a canonical owner verifier drawn from
``_CANONICAL_OWNER_VERIFIERS``.  That registry is EMPTY BY CONSTRUCTION: no
canonical CUSIP->SEC resolver and no canonical manager/vehicle epoch
producer exists anywhere in this repository today, and K2-C may never
populate it itself -- only the owning programs may, in their own waves (see
the registry's own comment, below).  Consequently ``build_recipe``/
``compile_recipe`` remain in this module as the structure a future owner
wires into, but **the positive path is unreachable by construction**: no
caller-supplied ``owner_semantics``, however well-formed, can ever pass
verification while the registry stays empty, so :func:`run_pilot` always
takes the typed pre-recipe ``PILOT_OWNER_SEMANTICS_UNRESOLVED`` branch, and
the ``POSITIVE_STATE``/``NON_POSITIVE_STATE`` branch below it is dead code
today -- present only for the owner who eventually populates the registry.
Two review findings fall out of this for free, not from a bespoke check: no
partial or self-contradictory epoch can ever reach ``build_recipe`` (nothing
can raise ``validate_recipe``'s own errors AFTER construction, because
construction itself is unreachable), and no caller-authored provenance is
ever admitted onto a receipt (the unresolved receipt's
``owner_semantics.provenance`` is always ``null``, and the receipt instead
carries the exact shape/verification ``reason`` it refused for -- see
:func:`run_pilot`).

See ``research/alpha_intelligence/K2C_INSTITUTIONAL_ADAPTER_PILOT_2026-08-27.md``
for the frozen design this module implements.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from engine.institutional_census.catalog import (
    HARD_MAX_CATALOG_POINTER_BYTES,
    PublishedCatalogGeneration,
    load_catalog_generation,
)
from engine.institutional_census.models import (
    canonical_json_bytes,
    catalog_pointer_key,
    normalize_accession,
    normalize_cik,
    normalize_report_period,
    raw_receipt_key,
    utc_datetime,
)
from engine.institutional_census.storage import (
    build_institutional_13f_store,
    load_raw_evidence,
)
from lib.dataos.identity import IdentityError, parse_id
from lib.evidence_foundation import (
    ALL_FALSE_AUTHORITY,
    compute_reference_id,
    validate_reference,
)
from lib.institutional_intelligence import (
    compile_recipe,
    compute_recipe_id,
    validate as validate_recipe,
)


SCHEMA = "institutional_intelligence.owner_read_receipt/v1"
ADAPTER_VERSION = "1.0.0"
RECEIPT_ID_PREFIX = "i13fpilot_"

# --- Typed refusal reasons (closed set; see design doc section 5) -----------
GENERATION_NOT_KNOWABLE_AT_CUTOFF = "generation_not_knowable_at_cutoff"
NOT_YET_KNOWABLE = "not_yet_knowable"
FILING_NOT_FOUND = "filing_not_found"
AMBIGUOUS_FILING_LINEAGE = "ambiguous_filing_lineage"
AMENDMENT_COMPOSITION_UNSUPPORTED = "amendment_composition_unsupported"
CUSIP_GRAMMAR_INVALID = "cusip_grammar_invalid"
SECURITY_NOT_IN_FILING = "security_not_in_filing"
AMBIGUOUS_HOLDINGS_ROWS = "ambiguous_holdings_rows"
MEASURE_UNIT_UNSUPPORTED = "measure_unit_unsupported"
SOURCE_RECEIPT_MISMATCH = "source_receipt_mismatch"
REPORT_PERIODS_NOT_INCREASING = "report_periods_not_increasing"
POSITIVE_STATE = "PILOT_COMPILED"
NON_POSITIVE_STATE = "PILOT_COMPILED_NON_POSITIVE"

# --- Owner-semantics gate (K2-C semantic-owner repair, 2026-09-03) ----------
# Neither of these is a typed *refusal* reason (TYPED_REFUSAL_REASONS below
# covers only PilotRefusal, raised strictly BEFORE these two owner seams are
# ever inspected). These describe the two independent owner bindings a
# caller may supply via run_pilot(..., owner_semantics=...), and the one
# terminal receipt state reached when either is missing.
SECURITY_BINDING_UNRESOLVED = "unresolved_no_authoritative_cusip_plane"
MANAGER_VEHICLE_BINDING_UNRESOLVED = "unresolved_no_canonical_manager_vehicle_owner"
OWNER_SEMANTICS_UNRESOLVED_STATE = "PILOT_OWNER_SEMANTICS_UNRESOLVED"

# --- Owner VERIFICATION gate (Sol review 5099850302 repair, 2026-09-03) -----
# Canonical owner verifiers that could admit an owner_semantics payload as
# PROOF. EMPTY by construction: no canonical owner exists today (see the
# operation's BLOCKED OWNER_PRIMITIVE_REQUIRED return). K2-C may NEVER
# populate this -- only the owning programs may, in their own waves:
#   * security axis  -> Data OS / Stock Identity
#   * manager/vehicle -> Institutional Intelligence (K2-B)
# While this is empty, no caller-supplied mapping can unlock recipe
# construction, because there is nothing that could verify it.
#
# A future verifier is called as
# ``verifier(owner_semantics=..., cusip=..., cutoff=..., security=...,
# manager_complex_epoch=..., vehicle_epoch=..., provenance=...) ->
# Mapping[str, Any] | None`` -- returning the payload (or an owner-corrected
# equivalent) only when it genuinely proves the binding for THIS request,
# else ``None`` so the next registered verifier (if any) gets a turn.
_CANONICAL_OWNER_VERIFIERS: tuple = ()
OWNER_VERIFIER_ABSENT = "no_canonical_owner_verifier"

# --- Owner-semantics SHAPE reasons (Sol review 5099850302 repair) ----------
# One reason per shape defect so the receipt says *which* thing was wrong.
# These are necessary but -- per the module docstring -- no longer
# sufficient: a shape-valid payload still falls through to
# OWNER_VERIFIER_ABSENT above, because nothing in this repository can prove
# a shape-valid payload TRUE.
OWNER_SEMANTICS_MALFORMED = "owner_semantics_malformed"
OWNER_SEMANTICS_PROVENANCE_INVALID = "owner_semantics_provenance_invalid"
OWNER_SEMANTICS_SECURITY_INVALID = "owner_semantics_security_invalid"
OWNER_SEMANTICS_SECURITY_UNRESOLVED_SENTINEL = "owner_semantics_security_unresolved_sentinel"
OWNER_SEMANTICS_SECURITY_NOT_OWNER_GRAMMAR = "owner_semantics_security_not_owner_grammar"
OWNER_SEMANTICS_MANAGER_EPOCH_INVALID = "owner_semantics_manager_epoch_invalid"
OWNER_SEMANTICS_VEHICLE_EPOCH_INVALID = "owner_semantics_vehicle_epoch_invalid"

TYPED_REFUSAL_REASONS = frozenset({
    GENERATION_NOT_KNOWABLE_AT_CUTOFF,
    NOT_YET_KNOWABLE,
    FILING_NOT_FOUND,
    AMBIGUOUS_FILING_LINEAGE,
    AMENDMENT_COMPOSITION_UNSUPPORTED,
    CUSIP_GRAMMAR_INVALID,
    SECURITY_NOT_IN_FILING,
    AMBIGUOUS_HOLDINGS_ROWS,
    MEASURE_UNIT_UNSUPPORTED,
    SOURCE_RECEIPT_MISMATCH,
    REPORT_PERIODS_NOT_INCREASING,
})

_CUSIP_RE = re.compile(r"^[0-9A-Z]{9}$")


class Institutional13FAdapterError(RuntimeError):
    """A structural, non-typed defect in adapter inputs or wiring.

    This is distinct from an owner exception (``Institutional13FError`` and
    its subclasses), which always propagates untouched, and from a typed
    refusal (``PilotRefusal``), which becomes a receipt.  This exception
    signals a bug in the *caller's request shape*, e.g. an unaware-naive
    cutoff -- something the frozen typed-state list does not cover.
    """


class PilotRefusal(Exception):
    """One typed, non-exceptional data-absence/ambiguity outcome.

    Caught internally by :func:`run_pilot` and turned into a typed refusal
    receipt.  Exposed publicly so the individual step functions can be unit
    tested in isolation.
    """

    def __init__(self, reason: str, detail: str) -> None:
        if reason not in TYPED_REFUSAL_REASONS:
            raise Institutional13FAdapterError(f"unknown typed refusal reason: {reason!r}")
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


# --- Public request contract -------------------------------------------------


@dataclass(frozen=True)
class PilotRequest:
    """A frozen, fully-specified two-period owner-read request.

    Construction performs only structural normalization (CIK zero-padding,
    report-period calendar-date normalization, cutoff timezone binding).  It
    deliberately does NOT validate CUSIP grammar -- that is a typed refusal
    produced by :func:`select_security_row`, not a constructor-time
    exception, so a malformed CUSIP still yields a lawful receipt.
    """

    filer_cik: str
    cusip: str
    report_period_prev: str
    report_period_now: str
    cutoff: datetime
    generation_id_prev: str | None = None
    generation_id_now: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "filer_cik", normalize_cik(self.filer_cik))
        object.__setattr__(self, "cusip", str(self.cusip or "").strip().upper())
        object.__setattr__(
            self, "report_period_prev", normalize_report_period(self.report_period_prev)
        )
        object.__setattr__(
            self, "report_period_now", normalize_report_period(self.report_period_now)
        )
        if (
            not isinstance(self.cutoff, datetime)
            or self.cutoff.tzinfo is None
            or self.cutoff.utcoffset() is None
        ):
            raise Institutional13FAdapterError("cutoff must be an aware UTC datetime")
        object.__setattr__(self, "cutoff", self.cutoff.astimezone(timezone.utc))
        for field_name in ("generation_id_prev", "generation_id_now"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, str):
                raise Institutional13FAdapterError(f"{field_name} must be a string or None")


# --- Step 1: generation resolution ------------------------------------------


def resolve_generation(
    store: Any,
    *,
    report_period: str,
    cutoff: datetime,
    generation_id: str | None = None,
) -> PublishedCatalogGeneration:
    """Resolve one catalog generation, refusing one not yet knowable at cutoff.

    A bounded, absence-tolerant pre-probe of the current-pointer object is
    used ONLY when ``generation_id`` is not supplied, mirroring the owner's
    own ``rolling._load_period_state`` precedent: an absent pointer means the
    report period has never been published at all (``filing_not_found``,
    never an exception).  Any other failure -- a corrupt pointer, a missing
    or digest-mismatched manifest/artifact, a real store outage -- is an
    owner exception and is left to propagate untouched.
    """
    period = normalize_report_period(report_period)
    if generation_id is None:
        pointer_bytes = store.get_bytes_strict_bounded(
            catalog_pointer_key(period), HARD_MAX_CATALOG_POINTER_BYTES
        )
        if pointer_bytes is None:
            raise PilotRefusal(
                FILING_NOT_FOUND,
                f"no catalog generation has ever been published for report_period {period}",
            )
    generation = load_catalog_generation(store, report_period=period, generation_id=generation_id)
    published_at = utc_datetime(str(generation.manifest.clocks.published_at), field="published_at")
    if published_at > cutoff:
        raise PilotRefusal(
            GENERATION_NOT_KNOWABLE_AT_CUTOFF,
            f"generation {generation.manifest.generation_id} published_at={published_at.isoformat()} "
            f"is after cutoff={cutoff.isoformat()}",
        )
    return generation


# --- Step 2: effective filing (amendment lineage) ---------------------------


def select_effective_filing(
    generation: PublishedCatalogGeneration,
    *,
    filer_cik: str,
    report_period: str,
    cutoff: datetime,
) -> Mapping[str, Any]:
    """Return the latest-knowable amendment-chain tip for one filer/period.

    Lineage is resolved from the owner's own ``is_amendment``/``lineage_state``
    fields (never re-derived): the effective filing is the knowable candidate
    with the latest ``max(accepted_at, retained_at)``.  A tie is
    ``ambiguous_filing_lineage``.  A tip that is a non-restatement amendment
    (``lineage_state`` other than ``amendment_restatement``) is
    ``amendment_composition_unsupported``, since combining a partial
    amendment with its predecessor's rows is outside this adapter's read
    (it never authors a merged holdings view).
    """
    cik = normalize_cik(filer_cik)
    period = normalize_report_period(report_period)
    candidates = [
        row
        for row in generation.filings
        if str(row["filer_cik"]) == cik and str(row["report_period"]) == period
    ]
    if not candidates:
        raise PilotRefusal(
            FILING_NOT_FOUND, f"no 13F filing found for filer {cik} in report_period {period}"
        )
    knowable: list[tuple[datetime, Mapping[str, Any]]] = []
    for row in candidates:
        accepted = utc_datetime(str(row["accepted_at"]), field="accepted_at")
        retained = utc_datetime(str(row["retained_at"]), field="retained_at")
        knowable_at = max(accepted, retained)
        if knowable_at <= cutoff:
            knowable.append((knowable_at, row))
    if not knowable:
        raise PilotRefusal(
            NOT_YET_KNOWABLE,
            f"filing(s) for filer {cik} in report_period {period} exist but are not yet "
            f"knowable at cutoff={cutoff.isoformat()}",
        )
    knowable.sort(key=lambda pair: (pair[0], str(pair[1]["accession"])))
    max_clock = knowable[-1][0]
    tips = [row for clock, row in knowable if clock == max_clock]
    if len(tips) > 1:
        identities = sorted(str(row["accession"]) for row in tips)
        raise PilotRefusal(
            AMBIGUOUS_FILING_LINEAGE,
            f"multiple equally-knowable filings for filer {cik} in report_period {period}: "
            f"{identities}",
        )
    tip = tips[0]
    if bool(tip["is_amendment"]) and str(tip["lineage_state"]) != "amendment_restatement":
        raise PilotRefusal(
            AMENDMENT_COMPOSITION_UNSUPPORTED,
            f"accession {tip['accession']} is a non-restatement amendment "
            f"(lineage_state={tip['lineage_state']!r})",
        )
    return tip


# --- Step 3: security row selection -----------------------------------------


def select_security_row(
    generation: PublishedCatalogGeneration,
    *,
    accession: str,
    cusip: str,
) -> tuple[Mapping[str, Any], int]:
    """Return the one non-derivative holdings row matching ``cusip`` and its q.

    ``q`` is the strict integer value of ``ssh_prn_amt`` where
    ``ssh_prn_type == "SH"``; any other unit is ``measure_unit_unsupported``.
    """
    normalized_cusip = str(cusip or "").strip()
    if not _CUSIP_RE.fullmatch(normalized_cusip):
        raise PilotRefusal(
            CUSIP_GRAMMAR_INVALID, f"cusip does not match ^[0-9A-Z]{{9}}$: {cusip!r}"
        )
    accession_norm = normalize_accession(accession)
    candidates = [
        row
        for row in generation.holdings
        if str(row["accession"]) == accession_norm
        and row.get("cusip") == normalized_cusip
        and not str(row.get("put_call") or "").strip()
    ]
    if not candidates:
        raise PilotRefusal(
            SECURITY_NOT_IN_FILING,
            f"cusip {normalized_cusip} is not present as a non-derivative row in accession "
            f"{accession_norm}",
        )
    if len(candidates) > 1:
        identities = sorted(f"infotable_sk={row['infotable_sk']}" for row in candidates)
        raise PilotRefusal(
            AMBIGUOUS_HOLDINGS_ROWS,
            f"multiple holdings rows match cusip {normalized_cusip} in accession "
            f"{accession_norm}: {identities}",
        )
    row = candidates[0]
    if str(row.get("ssh_prn_type") or "") != "SH":
        raise PilotRefusal(
            MEASURE_UNIT_UNSUPPORTED,
            f"ssh_prn_type {row.get('ssh_prn_type')!r} is not a share count (SH)",
        )
    raw_amount = row.get("ssh_prn_amt")
    text = str(raw_amount).strip() if raw_amount is not None else ""
    if not re.fullmatch(r"[0-9]+", text):
        raise Institutional13FAdapterError(f"ssh_prn_amt is not a strict integer: {raw_amount!r}")
    return row, int(text)


# --- Step 4: raw-receipt cross-check ----------------------------------------


def cross_check_raw_receipt(
    store: Any,
    *,
    filer_cik: str,
    filing_row: Mapping[str, Any],
):
    """Load the filing's raw evidence receipt and prove it matches the filing.

    Any disagreement on ``source_receipt_id``/``raw_sha256``/``accepted_at``/
    ``retained_at``/``report_period``/``filer_cik`` is a hard typed refusal
    (``source_receipt_mismatch``).  A genuinely missing/corrupt raw object is
    an owner exception and propagates untouched.
    """
    cik = normalize_cik(filer_cik)
    accession = str(filing_row["accession"])
    key = raw_receipt_key(cik, accession, str(filing_row["source_receipt_id"]))
    receipt, raw_bytes = load_raw_evidence(store, key)
    mismatches: list[str] = []
    if receipt.receipt_id != str(filing_row["source_receipt_id"]):
        mismatches.append("source_receipt_id")
    if receipt.raw_object.sha256 != str(filing_row["raw_sha256"]):
        mismatches.append("raw_sha256")
    if str(receipt.clocks.accepted_at) != str(filing_row["accepted_at"]):
        mismatches.append("accepted_at")
    if str(receipt.clocks.retained_at) != str(filing_row["retained_at"]):
        mismatches.append("retained_at")
    if str(receipt.clocks.report_period) != str(filing_row["report_period"]):
        mismatches.append("report_period")
    if receipt.filer_cik != cik:
        mismatches.append("filer_cik")
    if mismatches:
        raise PilotRefusal(
            SOURCE_RECEIPT_MISMATCH,
            f"raw receipt for accession {accession} disagrees with the filing row on: "
            f"{sorted(mismatches)}",
        )
    return receipt, raw_bytes


# --- K1 EvidenceRef construction (mirrors the K2-B wave-A test shape) -------

_K1_REPLAY_CUTOFFS = {
    axis: {"state": "unknown", "value": None, "grain": "date"}
    for axis in (
        "belief_or_build", "knowable", "observed", "review_due",
        "source_published", "system_recorded", "world_valid",
    )
}


def _raw_receipt_reference(*, receipt: Any) -> dict[str, Any]:
    filer_cik = str(receipt.filer_cik)
    accession = str(receipt.accession)
    reference: dict[str, Any] = {
        "schema": "evidence_foundation.reference.v1",
        "version": "1.0.0",
        "object_class": "world_observation",
        "owner_store": "institutional_13f.raw_receipt",
        "native_identity": {
            "filer_cik": filer_cik,
            "accession": accession,
            "receipt_id": receipt.receipt_id,
        },
        "native_schema": "institutional_13f.raw_evidence_receipt/v1",
        "native_digest": {"state": "known", "sha256": receipt.raw_object.sha256},
        "coverage_class": "source_release_snapshot_only",
        "freshness": {
            "state": "native_clock_bound", "clock_field": "clocks.retained_at", "policy_id": None,
        },
        "rights": {"state": "permitted", "policy_id": None},
        "authority_class": "fact",
        "subject": {"key_type": "institutional_manager_cik", "key": filer_cik},
        "secondary_subjects": [{"key_type": "accession", "key": accession}],
        "clocks": [
            {
                "class": "world_valid", "field": "clocks.report_period", "grain": "date",
                "value": str(receipt.clocks.report_period), "value_state": "known",
            },
            {
                "class": "source_published", "field": "clocks.accepted_at", "grain": "datetime",
                "value": str(receipt.clocks.accepted_at), "value_state": "known",
            },
            {
                "class": "system_recorded", "field": "clocks.retained_at", "grain": "datetime",
                "value": str(receipt.clocks.retained_at), "value_state": "known",
            },
        ],
        "provenance": {
            "pointer_only": True,
            "body_embedded": False,
            "owner_reader": "engine.institutional_census.models.RawEvidenceReceipt.from_json_bytes",
            "owner_reader_kind": "parser",
            "pointer": f"institutional-13f/raw/{filer_cik}/{accession}/{receipt.receipt_id}.json",
        },
        "relations": [],
        "missingness": {"state": "present", "reason": None, "zero_substituted": False},
        "correction": {
            "kind": "none", "predecessor_reference_ids": [], "clock_field": None,
            "chronology_state": "not_applicable", "append_only": True, "mutates_predecessor": False,
        },
        "replay": {
            "mode": "live", "cutoffs": deepcopy(_K1_REPLAY_CUTOFFS),
            "code_revision": None, "input_digest": None, "vintage_state": "owner_native",
        },
        "authority": deepcopy(ALL_FALSE_AUTHORITY),
    }
    reference["reference_id"] = compute_reference_id(reference)
    return validate_reference(reference)


def _catalog_generation_reference(*, generation: PublishedCatalogGeneration) -> dict[str, Any]:
    # generation_id is content-derived and re-verified on every decode
    # (CatalogGenerationManifest.__post_init__ recomputes and compares the
    # sha256 identity, mirroring RawEvidenceReceipt's own law), so the
    # explicit-generation_id read path in resolve_generation is thereby
    # digest-bound even though it never touches the current-pointer object.
    generation_id = generation.manifest.generation_id
    report_period = str(generation.manifest.clocks.report_period)
    manifest_sha256 = sha256(generation.manifest.to_json_bytes()).hexdigest()
    reference: dict[str, Any] = {
        "schema": "evidence_foundation.reference.v1",
        "version": "1.0.0",
        "object_class": "derived_view",
        "owner_store": "institutional_13f.catalog_generation",
        "native_identity": {"generation_id": generation_id, "report_period": report_period},
        "native_schema": "institutional_13f.catalog_generation_manifest/v1",
        "native_digest": {"state": "known", "sha256": manifest_sha256},
        "coverage_class": "immutable_generation",
        "freshness": {
            "state": "native_clock_bound", "clock_field": "clocks.published_at", "policy_id": None,
        },
        "rights": {"state": "permitted", "policy_id": None},
        "authority_class": "deterministic",
        "subject": {"key_type": "institutional_catalog_generation_id", "key": generation_id},
        "secondary_subjects": [],
        "clocks": [
            {
                "class": "world_valid", "field": "clocks.report_period", "grain": "date",
                "value": report_period, "value_state": "known",
            },
            {
                "class": "knowable", "field": "clocks.source_cutoff_at", "grain": "datetime",
                "value": str(generation.manifest.clocks.source_cutoff_at), "value_state": "known",
            },
            {
                "class": "belief_or_build", "field": "clocks.published_at", "grain": "datetime",
                "value": str(generation.manifest.clocks.published_at), "value_state": "known",
            },
        ],
        "provenance": {
            "pointer_only": True,
            "body_embedded": False,
            "owner_reader": "engine.institutional_census.catalog.load_catalog_generation",
            "owner_reader_kind": "direct",
            "pointer": f"institutional-13f/catalog/{report_period}/generations/{generation_id}/manifest.json",
        },
        "relations": [],
        "missingness": {"state": "present", "reason": None, "zero_substituted": False},
        "correction": {
            "kind": "none", "predecessor_reference_ids": [], "clock_field": None,
            "chronology_state": "not_applicable", "append_only": True, "mutates_predecessor": False,
        },
        "replay": {
            "mode": "live", "cutoffs": deepcopy(_K1_REPLAY_CUTOFFS),
            "code_revision": None, "input_digest": None, "vintage_state": "owner_native",
        },
        "authority": deepcopy(ALL_FALSE_AUTHORITY),
    }
    reference["reference_id"] = compute_reference_id(reference)
    return validate_reference(reference)


def _reference_binding(
    reference: Mapping[str, Any],
    *,
    valid_field: str,
    valid_value: str,
    available_field: str,
    available_value: str,
) -> dict[str, Any]:
    return {
        "reference_id": reference["reference_id"],
        "owner_store": reference["owner_store"],
        "native_identity": deepcopy(reference["native_identity"]),
        "valid_clock": {"field": valid_field, "value": valid_value},
        "available_clock": {"field": available_field, "value": available_value},
    }


def _period_binding(
    *,
    catalog_ref: Mapping[str, Any],
    raw_ref: Mapping[str, Any],
    generation: PublishedCatalogGeneration,
    filing_row: Mapping[str, Any],
    row: Mapping[str, Any],
) -> dict[str, Any]:
    report_period = str(generation.manifest.clocks.report_period)
    published_at = str(generation.manifest.clocks.published_at)
    retained_at = str(filing_row["retained_at"])
    return {
        "catalog_binding": _reference_binding(
            catalog_ref,
            valid_field="clocks.report_period", valid_value=report_period,
            available_field="clocks.published_at", available_value=published_at,
        ),
        "raw_receipt_binding": _reference_binding(
            raw_ref,
            valid_field="clocks.report_period", valid_value=report_period,
            available_field="clocks.retained_at", available_value=retained_at,
        ),
        "row": {
            "accession": str(row["accession"]),
            "infotable_sk": int(row["infotable_sk"]),
            "row_hash": str(row["row_hash"]),
            "cusip": str(row["cusip"]),
        },
    }


# --- K2-B recipe assembly -----------------------------------------------


_EPOCH_FROM = "2000-01-01T00:00:00Z"


def _open_interval() -> dict[str, Any]:
    return {
        "effective_from": _EPOCH_FROM, "effective_to": None,
        "valid_from": _EPOCH_FROM, "valid_to": None,
        "knowable_from": _EPOCH_FROM, "knowable_to": None,
    }


def _original_lineage() -> dict[str, Any]:
    return {"state": "original", "predecessor_epoch_id": None, "reason": None, "append_only": True}


_MANAGER_COMPLEX_EPOCH_REQUIRED_KEYS = ("manager_complex_id", "complex_epoch_id")
# vehicle_epoch's required keys mirror exactly what build_recipe reads out of
# it (decision_mode selects the measure kind; the rest is carried verbatim
# into the K2-B recipe) -- never the full K2-B vehicleEpoch schema, which
# lib.institutional_intelligence.validate owns.
_VEHICLE_EPOCH_REQUIRED_KEYS = (
    "vehicle_epoch_id", "decision_mode", "manager_complex_id", "complex_epoch_id", "vehicle_class",
)


def _epoch_string_fields_present(epoch: Mapping[str, Any], keys: tuple[str, ...]) -> bool:
    """True only when every one of ``keys`` is present on ``epoch`` as a
    non-empty string. Checks structural completeness of exactly the keys
    THIS ADAPTER itself consumes (see ``build_recipe``) -- never the full
    K2-B ``managerComplexEpoch``/``vehicleEpoch`` schema, which the K2-B
    compiler (``lib.institutional_intelligence.validate``) owns and enforces
    on its own terms once a recipe reaches it.
    """
    for key in keys:
        value = epoch.get(key)
        if not isinstance(value, str) or not value.strip():
            return False
    return True


def _epoch_status_contradicts_resolved(epoch: Mapping[str, Any]) -> bool:
    """True when an epoch claims ``resolution_state=="resolved"`` while its
    own ``status`` is ``"unresolved"`` -- self-contradictory.  K2-B's own
    semantic law (``lib/institutional_intelligence.py``,
    ``unresolved_complex_status_conflict``) already refuses the mirror case
    (``resolution_state=="unresolved"`` with ``status!="unresolved"``); this
    closes the other direction, which matters here because
    ``resolution_state=="resolved"`` is exactly what this validator treats
    as proof an epoch may be trusted at all.
    """
    return epoch.get("status") == "unresolved" and epoch.get("resolution_state") == "resolved"


def _verify_owner_semantics(
    owner_semantics: Any, *, cusip: str, cutoff: datetime
) -> tuple[Mapping[str, Any] | None, str]:
    """Strictly, atomically VERIFY one ``owner_semantics`` payload against
    this request's exact ``cusip``/``cutoff``. Returns ``(payload, "")`` only
    when a canonical owner verifier proves the binding; otherwise
    ``(None, reason)``, where ``reason`` names exactly what refused it.

    Stage 1 -- SHAPE (necessary, never sufficient on its own). Every check
    the pre-repair ``_validate_owner_semantics`` performed stays, unchanged,
    each now returning its OWN reason:

    * ``provenance``: a mapping with non-empty string ``owner`` and
      non-empty string ``reference_id`` (``OWNER_SEMANTICS_PROVENANCE_INVALID``);
    * ``security``: a mapping with non-empty string ``dataos_security_id``
      and non-empty string ``dataos_resolution``
      (``OWNER_SEMANTICS_SECURITY_INVALID``), where ADDITIONALLY (a)
      ``dataos_resolution`` is not the typed unresolved sentinel
      (``SECURITY_BINDING_UNRESOLVED`` -- the schema's own "not proven"
      value is never proof of resolution --
      ``OWNER_SEMANTICS_SECURITY_UNRESOLVED_SENTINEL``) and (b)
      ``dataos_security_id`` parses under the canonical Data OS grammar
      (``lib.dataos.identity.parse_id``) AND denotes a ``SEC:`` security
      identity specifically (``OWNER_SEMANTICS_SECURITY_NOT_OWNER_GRAMMAR`` --
      an ``ISS:`` issuer id, a bare listing key, or any other
      instrument-class id is not a security binding);
    * ``manager_complex_epoch`` / ``vehicle_epoch``: each a mapping whose own
      ``resolution_state`` is ``"resolved"``, whose ``status`` does not
      contradict that (see :func:`_epoch_status_contradicts_resolved`), and
      which carries non-empty string values for every key this adapter
      itself reads out of it -- never the full K2-B schema
      (``OWNER_SEMANTICS_MANAGER_EPOCH_INVALID`` /
      ``OWNER_SEMANTICS_VEHICLE_EPOCH_INVALID``).

    Any single shape defect anywhere -- missing, empty, wrong-typed,
    unresolved, structurally partial, or internally self-contradictory --
    refuses the WHOLE payload (never partially trusted), with no exception
    and no default ever filled in for a missing field.

    Stage 2 -- OWNER VERIFICATION (the repair). Shape checks alone were
    proven insufficient by adversarial review: a payload can satisfy every
    one of them while still being wrong (a parseable ``SEC:`` identity that
    names the WRONG security for ``cusip``; a vehicle epoch linking a
    ``manager_complex_id`` the manager epoch never claimed; a
    ``vehicle_class``/``decision_mode`` combination K2-B's own compiler
    would reject) -- none of Stage 1's checks can know the TRUTH of the
    mapping, only whether it is well-formed. A shape-valid payload is
    therefore handed to every verifier in ``_CANONICAL_OWNER_VERIFIERS`` in
    order; the first one that proves the binding for this exact
    cusip/cutoff/security id/epochs/provenance wins. That registry is EMPTY
    BY CONSTRUCTION, so a shape-valid payload always falls through to
    ``(None, OWNER_VERIFIER_ABSENT)`` -- there is nothing that could verify
    it, so nothing can unlock recipe construction, no matter how
    well-formed the payload looks. This is what makes the positive path
    unreachable BY CONSTRUCTION rather than by convention.

    This is the ONLY function in the module that may treat
    ``owner_semantics`` as authoritative. It never resolves, mints,
    derives, or maps a security identity itself -- Stage 1 only asks the
    Data OS identity owner whether a string a caller already supplied is
    even a well-formed identity of its own, and Stage 2 defers entirely to
    a registered owner verifier that does not exist today.
    """
    if not isinstance(owner_semantics, Mapping):
        return None, OWNER_SEMANTICS_MALFORMED
    provenance = owner_semantics.get("provenance")
    if not isinstance(provenance, Mapping):
        return None, OWNER_SEMANTICS_PROVENANCE_INVALID
    owner = provenance.get("owner")
    reference_id = provenance.get("reference_id")
    if not isinstance(owner, str) or not owner.strip():
        return None, OWNER_SEMANTICS_PROVENANCE_INVALID
    if not isinstance(reference_id, str) or not reference_id.strip():
        return None, OWNER_SEMANTICS_PROVENANCE_INVALID
    security = owner_semantics.get("security")
    if not isinstance(security, Mapping):
        return None, OWNER_SEMANTICS_SECURITY_INVALID
    dataos_security_id = security.get("dataos_security_id")
    dataos_resolution = security.get("dataos_resolution")
    if not isinstance(dataos_security_id, str) or not dataos_security_id.strip():
        return None, OWNER_SEMANTICS_SECURITY_INVALID
    if not isinstance(dataos_resolution, str) or not dataos_resolution.strip():
        return None, OWNER_SEMANTICS_SECURITY_INVALID
    # (R1, blocker repair 2026-09-03) The unresolved sentinel is never proof
    # of resolution, and a caller-supplied id that is not even a well-formed
    # SEC: security identity under the owner's own grammar cannot be a
    # security binding either. The commission forbids calling an unresolved
    # security binding positive; both checks below exist to make that
    # literally impossible, not just discouraged by convention.
    if dataos_resolution == SECURITY_BINDING_UNRESOLVED:
        return None, OWNER_SEMANTICS_SECURITY_UNRESOLVED_SENTINEL
    try:
        security_id_kind, _ = parse_id(dataos_security_id)
    except IdentityError:
        return None, OWNER_SEMANTICS_SECURITY_NOT_OWNER_GRAMMAR
    if security_id_kind != "security":
        return None, OWNER_SEMANTICS_SECURITY_NOT_OWNER_GRAMMAR
    manager_complex_epoch = owner_semantics.get("manager_complex_epoch")
    if not isinstance(manager_complex_epoch, Mapping):
        return None, OWNER_SEMANTICS_MANAGER_EPOCH_INVALID
    if manager_complex_epoch.get("resolution_state") != "resolved":
        return None, OWNER_SEMANTICS_MANAGER_EPOCH_INVALID
    if _epoch_status_contradicts_resolved(manager_complex_epoch):
        return None, OWNER_SEMANTICS_MANAGER_EPOCH_INVALID
    if not _epoch_string_fields_present(manager_complex_epoch, _MANAGER_COMPLEX_EPOCH_REQUIRED_KEYS):
        return None, OWNER_SEMANTICS_MANAGER_EPOCH_INVALID
    vehicle_epoch = owner_semantics.get("vehicle_epoch")
    if not isinstance(vehicle_epoch, Mapping):
        return None, OWNER_SEMANTICS_VEHICLE_EPOCH_INVALID
    if vehicle_epoch.get("resolution_state") != "resolved":
        return None, OWNER_SEMANTICS_VEHICLE_EPOCH_INVALID
    if _epoch_status_contradicts_resolved(vehicle_epoch):
        return None, OWNER_SEMANTICS_VEHICLE_EPOCH_INVALID
    if not _epoch_string_fields_present(vehicle_epoch, _VEHICLE_EPOCH_REQUIRED_KEYS):
        return None, OWNER_SEMANTICS_VEHICLE_EPOCH_INVALID

    # Stage 2: shape-valid. Nothing in this repository can verify it against
    # ground truth today -- see _CANONICAL_OWNER_VERIFIERS. This loop is
    # structurally live (a future owner populates the registry, not this
    # module), but with an empty registry it never executes its body.
    for verifier in _CANONICAL_OWNER_VERIFIERS:
        verified = verifier(
            owner_semantics=owner_semantics,
            cusip=cusip,
            cutoff=cutoff,
            security=security,
            manager_complex_epoch=manager_complex_epoch,
            vehicle_epoch=vehicle_epoch,
            provenance=provenance,
        )
        if verified is not None:
            return verified, ""
    return None, OWNER_VERIFIER_ABSENT


def _manager_denominator(
    *, generation: PublishedCatalogGeneration, filing_row: Mapping[str, Any]
) -> dict[str, Any]:
    """Owner-derived ``public_reported_sleeve`` breadth denominator for one filing.

    ``complete`` only when the decoded holdings-row count for the accession
    equals the filing's own ``table_entry_total`` AND ``confidential_omitted``
    is false.  ``partial`` only when the filer's own ``table_entry_total`` IS
    disclosed AND decoded_count is a lawful subset of it (decoded <= total) --
    the honest ``missing_positions`` count is then the real, known gap.

    Every other condition -- ``table_entry_total`` undisclosed, OR a decoded
    row count that EXCEEDS the filer's own reported total (an owner-data
    inconsistency this adapter never resolves or silently reinterprets) --
    yields ``state="unknown"`` with the only counts this adapter actually
    holds knowledge of: the rows it decoded for this accession.
    ``excluded_positions``/``missing_positions`` are asserted 0 under
    "unknown" only because this adapter makes no separate claim about them,
    never because it has proven zero are excluded or missing -- an excess of
    decoded rows over a disclosed total is NEVER labelled "excluded" (those
    rows were not excluded from anything; they are exactly what was decoded).
    """
    accession = str(filing_row["accession"])
    decoded_count = sum(1 for row in generation.holdings if str(row["accession"]) == accession)
    table_entry_total = filing_row.get("table_entry_total")
    confidential_omitted = filing_row.get("confidential_omitted")
    has_lawful_total = (
        isinstance(table_entry_total, int)
        and not isinstance(table_entry_total, bool)
        and decoded_count <= table_entry_total
    )
    if has_lawful_total:
        total_entry = int(table_entry_total)
        if decoded_count == total_entry and confidential_omitted is False:
            return {
                "kind": "public_reported_sleeve", "state": "complete",
                "total_positions": total_entry, "included_positions": total_entry,
                "excluded_positions": 0, "missing_positions": 0,
            }
        return {
            "kind": "public_reported_sleeve", "state": "partial",
            "total_positions": total_entry, "included_positions": decoded_count,
            "excluded_positions": 0, "missing_positions": total_entry - decoded_count,
        }
    return {
        "kind": "public_reported_sleeve", "state": "unknown",
        "total_positions": decoded_count, "included_positions": decoded_count,
        "excluded_positions": 0, "missing_positions": 0,
    }


def build_recipe(
    *,
    filer_cik: str,
    cusip: str,
    previous_binding: Mapping[str, Any],
    current_binding: Mapping[str, Any],
    current_raw_reference_id: str,
    manager_complex_epoch: Mapping[str, Any],
    vehicle_epoch: Mapping[str, Any],
    security: Mapping[str, Any],
    q_prev: int,
    q_now: int,
    denominator: Mapping[str, Any],
) -> dict[str, Any]:
    """Assemble one fully-specified K2-B manager-intent recipe from owner facts.

    Every field here is either a deterministic function of owner-READ 13F
    data (catalog/raw evidence references, holdings rows) or is carried
    VERBATIM from the owner-SUPPLIED ``manager_complex_epoch``/
    ``vehicle_epoch``/``security`` mappings -- the validated
    ``owner_semantics`` seam :func:`run_pilot` gates on before this function
    is ever called.  This function mints NO identity of its own: it no
    longer derives ANY manager-complex/vehicle identifier string from
    ``filer_cik`` (the prior, now-deleted defect keyed those identifiers
    directly off the filer CIK, laundering a filer identifier into a
    resolved manager-complex identity), and it no longer stamps
    ``resolution_state``/``status`` itself -- those come only from the
    owner-supplied epochs, verbatim.  ``filer_cik`` is accepted for
    call-site symmetry with the rest of this adapter's owner-read pipeline
    but is no longer used to construct identity of any kind.  There is
    still no parameter through which a caller could inject a *compiled*
    result -- the only inputs are the owner-derived bindings/epochs and the
    two share quantities, and :func:`run_pilot` always calls this with
    values it either computed itself from the store or received, already
    strictly validated, through the one ``owner_semantics`` seam.
    """
    del filer_cik  # retained for call-site symmetry; never used to mint identity.
    complex_id = str(manager_complex_epoch["manager_complex_id"])
    complex_epoch_id = str(manager_complex_epoch["complex_epoch_id"])
    vehicle_epoch_id = str(vehicle_epoch["vehicle_epoch_id"])
    decision_mode = str(vehicle_epoch["decision_mode"])

    normalized_cusip = str(cusip)
    # K2-B's own semantic validator (non_discretionary_vehicle_cannot_emit_
    # manager_intent) hard-rejects a manager_research_intent observation that
    # carries a *computable* share-change delta unless its vehicle is
    # discretionary -- it is a schema-level refusal, not merely a compiled
    # ineligible state.  A non-discretionary owner-supplied vehicle epoch is
    # therefore submitted with an honest "unavailable" measure: the adapter
    # still records the real observed q_prev/q_now in its own receipt
    # fields (never hidden), but does not assert a discretionary-
    # attributable delta the compiler's own contract forbids for this
    # vehicle.  The compiler then produces its own typed non-positive state
    # (``MANAGER_INTENT_INELIGIBLE_OR_INSUFFICIENT``) -- the adapter never
    # manufactures that state itself.
    measure = (
        {"kind": "reported_share_change", "q_prev": q_prev, "q_now": q_now}
        if decision_mode == "discretionary"
        else {"kind": "unavailable", "reason": "unsupported"}
    )
    observation = {
        "observation_id": "obs_owner_read_pilot",
        "evidence_basis": "source_backed_owner_row",
        "evidence_reference_id": current_raw_reference_id,
        "reference_binding": deepcopy(current_binding["raw_receipt_binding"]),
        "vehicle_epoch_id": vehicle_epoch_id,
        "subject_id": f"cusip:{normalized_cusip}",
        "theme_id": "theme_not_applicable",
        "theme_epoch_id": "theme_epoch_not_applicable",
        "plane": "manager_research_intent",
        "measure": measure,
        "denominator": dict(denominator),
        "correction": {
            "kind": "none", "predecessor_observation_id": None, "reason": None, "append_only": True,
        },
        "owner_row_binding": {
            "security": {
                "key_type": "cusip",
                "cusip": normalized_cusip,
                "dataos_security_id": security["dataos_security_id"],
                "dataos_resolution": security["dataos_resolution"],
            },
            "previous": deepcopy(previous_binding),
            "current": deepcopy(current_binding),
        },
    }

    trial_cutoff_at = current_binding["catalog_binding"]["available_clock"]["value"]
    reliability_row = {
        "manager_complex_id": complex_id,
        "complex_epoch_id": complex_epoch_id,
        "domain": "general",
        "horizon": "quarterly",
        "action": "reported_add",
        "eligibility_state": "insufficient",
        "maturity_state": "insufficient",
        "scored_state": "insufficient",
        "trial_cutoff_at": trial_cutoff_at,
        "maturity_cutoff_at": trial_cutoff_at,
        "trials": 0, "matured_trials": 0, "scored_trials": 0, "successes": 0,
        "prior_alpha": 1.0, "prior_beta": 1.0,
        "uncertainty_method": {
            "method": "beta_binomial_normal_approx", "version": "1.0.0", "confidence_level": 0.95,
        },
        "evaluation_owner": "Eval OS",
        "evaluation_mode": "prospective_only",
        "legacy_grade_imported": False,
    }

    recipe = {
        "schema": "institutional_intelligence.manager_intent_recipe.v1",
        "recipe_id": "",
        "authority": deepcopy(ALL_FALSE_AUTHORITY),
        "evidence_refs": [],  # filled by caller (run_pilot) with the 4 built refs
        "manager_complex_epochs": [deepcopy(dict(manager_complex_epoch))],
        "filer_epochs": [],
        "vehicle_epochs": [deepcopy(dict(vehicle_epoch))],
        "observations": [observation],
        "theme_comparisons": [],
        "campaign_transitions": [],
        "reliability": [reliability_row],
    }
    return recipe


# --- Receipt assembly ---------------------------------------------------


def _period_block(
    *,
    generation: PublishedCatalogGeneration,
    filing_row: Mapping[str, Any],
    row: Mapping[str, Any],
    raw_receipt: Any,
    raw_ref: Mapping[str, Any],
    catalog_ref: Mapping[str, Any],
    explicit_generation_id: bool,
) -> dict[str, Any]:
    # On the explicit-generation_id path, engine.institutional_census.catalog
    # ``_load_generation`` NEVER reads the current-pointer object -- it
    # hard-codes ``current_generation_id=generation_id`` (tautologically
    # itself) with ``pointer_updated=False``/``superseded=False``.  Emitting
    # those fabricated values as if they were a real pointer read would be
    # asserting knowledge this adapter never obtained.  A ``"not_read"``
    # state carries no such fields; only the current-pointer path, which
    # genuinely dereferences the pointer object, may report them.
    pointer_block: dict[str, Any] = (
        {"state": "not_read"}
        if explicit_generation_id
        else {
            "state": "read",
            "current_generation_id": generation.current_generation_id,
            "pointer_updated": bool(generation.pointer_updated),
            "superseded": bool(generation.superseded),
        }
    )
    return {
        "generation_id": generation.manifest.generation_id,
        "report_period": str(generation.manifest.clocks.report_period),
        "source_cutoff_at": str(generation.manifest.clocks.source_cutoff_at),
        "published_at": str(generation.manifest.clocks.published_at),
        "pointer": pointer_block,
        "filing": {
            "accession": str(filing_row["accession"]),
            "is_amendment": bool(filing_row["is_amendment"]),
            "amendment_number": filing_row.get("amendment_number"),
            "amendment_type": filing_row.get("amendment_type"),
            "lineage_state": str(filing_row["lineage_state"]),
            "accepted_at": str(filing_row["accepted_at"]),
            "retained_at": str(filing_row["retained_at"]),
            "table_entry_total": filing_row.get("table_entry_total"),
            "table_value_total_usd": filing_row.get("table_value_total_usd"),
            "confidential_omitted": filing_row.get("confidential_omitted"),
        },
        "row": {
            "infotable_sk": int(row["infotable_sk"]),
            "row_hash": str(row["row_hash"]),
            "cusip": str(row["cusip"]),
            "ssh_prn_amt": row.get("ssh_prn_amt"),
            "ssh_prn_type": row.get("ssh_prn_type"),
            "put_call": row.get("put_call"),
            "investment_discretion": row.get("investment_discretion"),
            "value_usd": row.get("value_usd"),
        },
        "raw_receipt": {
            "receipt_id": raw_receipt.receipt_id,
            "accession": raw_receipt.accession,
            "accepted_at": str(raw_receipt.clocks.accepted_at),
            "retained_at": str(raw_receipt.clocks.retained_at),
        },
        "k1_reference_ids": {"raw": raw_ref["reference_id"], "catalog": catalog_ref["reference_id"]},
    }


def _finalize(receipt_body: dict[str, Any]) -> dict[str, Any]:
    body_without_id = {key: value for key, value in receipt_body.items() if key != "receipt_id"}
    digest = sha256(canonical_json_bytes(body_without_id)).hexdigest()
    body_without_id["receipt_id"] = RECEIPT_ID_PREFIX + digest
    # Canonical round-trip proves the receipt is exact-canonical JSON and
    # gives byte-identical output for byte-identical inputs (determinism law).
    return canonical_round_trip(body_without_id)


def canonical_round_trip(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(canonical_json_bytes(value).decode("utf-8"))


def _request_block(request: PilotRequest) -> dict[str, Any]:
    return {
        "filer_cik": request.filer_cik,
        "cusip": request.cusip,
        "report_period_prev": request.report_period_prev,
        "report_period_now": request.report_period_now,
        "cutoff": request.cutoff.isoformat().replace("+00:00", "Z"),
        "generation_id_prev": request.generation_id_prev,
        "generation_id_now": request.generation_id_now,
    }


def _refusal_receipt(request: PilotRequest, refusal: PilotRefusal) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "receipt_id": "",
        "adapter_version": ADAPTER_VERSION,
        "persistence": "none",
        "owner_payloads_copied": False,
        "authority": dict(ALL_FALSE_AUTHORITY),
        "request": _request_block(request),
        "state": refusal.reason,
        "refusal": {"reason": refusal.reason, "detail": refusal.detail},
    }


def run_pilot(
    store: Any, request: PilotRequest, *, owner_semantics: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Execute one deterministic, read-only, two-period owner-read pilot.

    Returns a canonical-JSON receipt, one of three families:

    * a lawful typed refusal (missing, ambiguous, not-yet-knowable, or
      non-increasing report periods) -- unaffected by ``owner_semantics``,
      since these are checked before any owner-semantics binding is even
      inspected;
    * ``PILOT_OWNER_SEMANTICS_UNRESOLVED`` -- the full two-period owner read
      succeeded, but ``owner_semantics`` was not supplied, failed strict
      shape checks, or -- the repair -- failed owner VERIFICATION (see
      :func:`_verify_owner_semantics`).  No K2-B recipe is ever constructed
      on this path (``recipe``/``compiled`` are ``None``), and no
      caller-authored ``provenance`` is ever echoed onto the receipt; the
      receipt instead names the exact ``reason`` it refused for;
    * a compiled receipt embedding the K2-B compiler's own output verbatim
      -- ``PILOT_COMPILED`` when the compiler itself reached
      ``MANAGER_RESEARCH_INTENT_ELIGIBLE_CONTEXT``, else
      ``PILOT_COMPILED_NON_POSITIVE`` -- reached ONLY when
      :func:`_verify_owner_semantics` returns a VERIFIED payload, which
      (Sol review 5099850302 repair) requires a canonical owner verifier
      from ``_CANONICAL_OWNER_VERIFIERS``.  That registry is EMPTY BY
      CONSTRUCTION today, so this branch is UNREACHABLE by construction --
      see the module docstring.

    A genuine owner exception (store outage, digest mismatch, corrupt
    object) is never caught here and always propagates.
    """
    cutoff = request.cutoff
    if request.report_period_prev >= request.report_period_now:
        # Checked before any store read: a swapped or equal report-period
        # pair is a typed refusal, never left to surface later as an
        # untyped InstitutionalIntelligenceError out of validate_recipe().
        return _finalize(_refusal_receipt(
            request,
            PilotRefusal(
                REPORT_PERIODS_NOT_INCREASING,
                f"report_period_prev {request.report_period_prev!r} must be strictly earlier "
                f"than report_period_now {request.report_period_now!r}",
            ),
        ))
    try:
        generation_prev = resolve_generation(
            store,
            report_period=request.report_period_prev,
            cutoff=cutoff,
            generation_id=request.generation_id_prev,
        )
        generation_now = resolve_generation(
            store,
            report_period=request.report_period_now,
            cutoff=cutoff,
            generation_id=request.generation_id_now,
        )
        filing_prev = select_effective_filing(
            generation_prev,
            filer_cik=request.filer_cik,
            report_period=request.report_period_prev,
            cutoff=cutoff,
        )
        filing_now = select_effective_filing(
            generation_now,
            filer_cik=request.filer_cik,
            report_period=request.report_period_now,
            cutoff=cutoff,
        )
        row_prev, q_prev = select_security_row(
            generation_prev, accession=str(filing_prev["accession"]), cusip=request.cusip
        )
        row_now, q_now = select_security_row(
            generation_now, accession=str(filing_now["accession"]), cusip=request.cusip
        )
        raw_receipt_prev, _ = cross_check_raw_receipt(
            store, filer_cik=request.filer_cik, filing_row=filing_prev
        )
        raw_receipt_now, _ = cross_check_raw_receipt(
            store, filer_cik=request.filer_cik, filing_row=filing_now
        )
    except PilotRefusal as refusal:
        return _finalize(_refusal_receipt(request, refusal))

    raw_ref_prev = _raw_receipt_reference(receipt=raw_receipt_prev)
    catalog_ref_prev = _catalog_generation_reference(generation=generation_prev)
    raw_ref_now = _raw_receipt_reference(receipt=raw_receipt_now)
    catalog_ref_now = _catalog_generation_reference(generation=generation_now)

    previous_binding = _period_binding(
        catalog_ref=catalog_ref_prev, raw_ref=raw_ref_prev,
        generation=generation_prev, filing_row=filing_prev, row=row_prev,
    )
    current_binding = _period_binding(
        catalog_ref=catalog_ref_now, raw_ref=raw_ref_now,
        generation=generation_now, filing_row=filing_now, row=row_now,
    )

    # Everything above and below this line (periods, denominators, request,
    # persistence/authority envelope) is computed identically regardless of
    # whether the owner seam resolves -- ONLY the recipe/compile/state
    # differ, per the frozen K2-C semantic-owner repair.
    periods_block = {
        "previous": _period_block(
            generation=generation_prev, filing_row=filing_prev, row=row_prev,
            raw_receipt=raw_receipt_prev, raw_ref=raw_ref_prev, catalog_ref=catalog_ref_prev,
            explicit_generation_id=request.generation_id_prev is not None,
        ),
        "current": _period_block(
            generation=generation_now, filing_row=filing_now, row=row_now,
            raw_receipt=raw_receipt_now, raw_ref=raw_ref_now, catalog_ref=catalog_ref_now,
            explicit_generation_id=request.generation_id_now is not None,
        ),
    }
    denominators_block = {
        "previous": _manager_denominator(generation=generation_prev, filing_row=filing_prev),
        "current": _manager_denominator(generation=generation_now, filing_row=filing_now),
    }
    common_fields = {
        "schema": SCHEMA,
        "receipt_id": "",
        "adapter_version": ADAPTER_VERSION,
        "persistence": "none",
        "owner_payloads_copied": False,
        "authority": dict(ALL_FALSE_AUTHORITY),
        "request": _request_block(request),
        "periods": periods_block,
        "denominators": denominators_block,
    }

    # --- The owner-semantics gate (frozen spec point 4; Sol review 5099850302
    # repair) --------------------------------------------------------------
    # BEFORE any recipe construction: a semantic positive requires a
    # canonical owner VERIFIER (never a caller's own say-so) to prove both
    # the security owner seam and the manager/vehicle owner seam for this
    # exact request. Verification is atomic and fail-closed (see
    # _verify_owner_semantics) -- there is no partial-trust state. With
    # _CANONICAL_OWNER_VERIFIERS empty by construction, this branch is
    # ALWAYS taken today: the caller-authored provenance is NEVER echoed
    # onto this receipt (laundering an unverified claim through the receipt
    # is exactly the back door this repair exists to close), and the exact
    # refusal reason -- a shape defect, or OWNER_VERIFIER_ABSENT for a
    # shape-valid payload nothing could verify -- is named instead.
    verified_owner_semantics, refusal_reason = _verify_owner_semantics(
        owner_semantics, cusip=request.cusip, cutoff=cutoff
    )
    if verified_owner_semantics is None:
        body = {
            **common_fields,
            "state": OWNER_SEMANTICS_UNRESOLVED_STATE,
            "compiled_observation_state": None,
            "security_binding": {
                "key_type": "cusip",
                "cusip": request.cusip,
                "dataos_security_id": None,
                "dataos_resolution": SECURITY_BINDING_UNRESOLVED,
            },
            "measure": {"state": "not_compiled", "reason": "owner_semantics_unresolved"},
            "recipe": None,
            "compiled": None,
            "owner_semantics": {
                "security": {"resolved": False, "resolution": SECURITY_BINDING_UNRESOLVED},
                "manager_vehicle": {"resolved": False, "resolution": MANAGER_VEHICLE_BINDING_UNRESOLVED},
                "provenance": None,
                "reason": refusal_reason,
            },
        }
        return _finalize(body)

    # UNREACHABLE TODAY: _CANONICAL_OWNER_VERIFIERS is empty by construction
    # (see its own comment), so _verify_owner_semantics can never return a
    # non-None payload above, and control never reaches this line. Left in
    # place, structurally, as what a future owner wires a real verifier
    # into -- see the module docstring "Owner VERIFICATION gate".
    security = verified_owner_semantics["security"]
    manager_complex_epoch = verified_owner_semantics["manager_complex_epoch"]
    vehicle_epoch = verified_owner_semantics["vehicle_epoch"]

    recipe = build_recipe(
        filer_cik=request.filer_cik,
        cusip=request.cusip,
        previous_binding=previous_binding,
        current_binding=current_binding,
        current_raw_reference_id=raw_ref_now["reference_id"],
        manager_complex_epoch=manager_complex_epoch,
        vehicle_epoch=vehicle_epoch,
        security=security,
        q_prev=q_prev,
        q_now=q_now,
        denominator=denominators_block["current"],
    )
    recipe["evidence_refs"] = [raw_ref_prev, catalog_ref_prev, raw_ref_now, catalog_ref_now]
    recipe["recipe_id"] = compute_recipe_id(recipe)
    validate_recipe(recipe)
    cutoff_iso = cutoff.isoformat().replace("+00:00", "Z")
    compiled = compile_recipe(recipe, as_of=cutoff_iso)
    observation_receipt = next(
        event for event in compiled["events"] if event["observation_id"] == "obs_owner_read_pilot"
    )
    is_eligible = observation_receipt["state"] == "MANAGER_RESEARCH_INTENT_ELIGIBLE_CONTEXT"
    # The recipe's own observation measure kind (set in build_recipe from the
    # owner-supplied vehicle epoch's decision_mode) is the single source of
    # truth for whether a discretionary-attributable q_prev/q_now delta was
    # ever submitted to the compiler -- never re-derived from is_eligible,
    # which answers a different question (whether the compiler accepted it).
    measure_was_submitted = recipe["observations"][0]["measure"]["kind"] == "reported_share_change"
    top_measure: dict[str, Any] = (
        {"q_prev": q_prev, "q_now": q_now, "unit": "shares"}
        if measure_was_submitted
        else {"state": "not_compiled", "reason": "non_discretionary_vehicle"}
    )

    provenance = verified_owner_semantics["provenance"]
    body = {
        **common_fields,
        "state": POSITIVE_STATE if is_eligible else NON_POSITIVE_STATE,
        "compiled_observation_state": observation_receipt["state"],
        "security_binding": {
            "key_type": "cusip",
            "cusip": request.cusip,
            "dataos_security_id": str(security["dataos_security_id"]),
            "dataos_resolution": str(security["dataos_resolution"]),
        },
        "measure": top_measure,
        "recipe": recipe,
        "compiled": compiled,
        # (R3 repair 2026-09-03) The owner_semantics receipt block used to be
        # emitted ONLY on the unresolved path, where provenance is always
        # None -- the validated provenance.owner/reference_id were silently
        # discarded on every reached-a-recipe path, so two receipts proven
        # by two DIFFERENT owners could be byte-identical. Emitted here too,
        # verbatim, so provenance survives onto whichever state (POSITIVE or
        # NON_POSITIVE) this path reaches.
        "owner_semantics": {
            "security": {
                "resolved": True,
                "resolution": str(security["dataos_resolution"]),
            },
            "manager_vehicle": {"resolved": True, "resolution": "resolved"},
            "provenance": {
                "owner": str(provenance["owner"]),
                "reference_id": str(provenance["reference_id"]),
            },
            "reason": None,
        },
    }
    return _finalize(body)


# --- CLI ----------------------------------------------------------------


def _parse_cutoff(value: str | None) -> datetime:
    if value is None or value == "":
        return datetime.now(timezone.utc)
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "K2-C read-only institutional 13F owner-read pilot adapter. "
            "Reads two report-period catalog generations, cross-checks raw "
            "evidence, and compiles a deterministic K2-B manager-research-"
            "intent receipt. Performs no writes. This CLI has no flag for "
            "the owner_semantics seam (by design -- a hand-injected owner "
            "override would be a back door around the owner-proof gate), "
            "so its real-world outcome is always the "
            f"{OWNER_SEMANTICS_UNRESOLVED_STATE!r} terminal receipt, never "
            "a semantic positive."
        )
    )
    parser.add_argument("--filer-cik", required=True, help="Manager filer CIK (10 digits)")
    parser.add_argument("--cusip", required=True, help="Requested security CUSIP (9 chars)")
    parser.add_argument("--report-period-now", required=True, help="Current report period (YYYY-MM-DD)")
    parser.add_argument("--report-period-prev", required=True, help="Predecessor report period (YYYY-MM-DD)")
    parser.add_argument("--cutoff", default=None, help="Optional compile cutoff (ISO-8601 UTC); empty = now")
    parser.add_argument("--generation-id-now", default=None, help="Optional explicit current-period generation id")
    parser.add_argument("--generation-id-prev", default=None, help="Optional explicit previous-period generation id")
    parser.add_argument("--local-dir", default=None, help="Local test store directory (else dedicated env vars)")
    parser.add_argument("--receipt", required=True, help="Output path for the canonical receipt JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    try:
        request = PilotRequest(
            filer_cik=args.filer_cik,
            cusip=args.cusip,
            report_period_prev=args.report_period_prev,
            report_period_now=args.report_period_now,
            cutoff=_parse_cutoff(args.cutoff),
            generation_id_prev=args.generation_id_prev,
            generation_id_now=args.generation_id_now,
        )
        store = build_institutional_13f_store(local_dir=args.local_dir)
        receipt = run_pilot(store, request)
        Path(args.receipt).write_bytes(canonical_json_bytes(receipt))
    except Exception as exc:  # noqa: BLE001 - CLI boundary translates to an exit code.
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"state: {receipt['state']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
