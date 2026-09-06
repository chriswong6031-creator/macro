"""Contract tests for the K2-C read-only institutional 13F owner-read adapter.

Every fixture store is built at test time through the OWNER's own publish
APIs (``engine.institutional_census.storage.publish_raw_evidence``,
``engine.institutional_census.catalog.prepare_catalog_generation`` /
``publish_catalog_generation``) into a tmp-dir ``LocalStore`` -- mirroring the
pattern in ``tests/test_institutional_13f_catalog.py`` and
``tests/test_institutional_manager_intent_contract.py``.  No network I/O; no
second store/reader is created; the adapter itself performs no writes.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from engine.institutional_census.catalog import (
    holding_bucket_role,
    load_catalog_generation,
    prepare_catalog_generation,
    publish_catalog_generation,
)
from engine.institutional_census.models import (
    Institutional13FError,
    canonical_json_bytes,
)
from engine.institutional_census.storage import publish_raw_evidence
from engine.research_vault.r2_store import LocalStore

from types import SimpleNamespace

from lib.institutional_13f_adapter import (
    AMBIGUOUS_FILING_LINEAGE,
    AMBIGUOUS_HOLDINGS_ROWS,
    AMENDMENT_COMPOSITION_UNSUPPORTED,
    CUSIP_GRAMMAR_INVALID,
    FILING_NOT_FOUND,
    GENERATION_NOT_KNOWABLE_AT_CUTOFF,
    MANAGER_VEHICLE_BINDING_UNRESOLVED,
    MEASURE_UNIT_UNSUPPORTED,
    OWNER_SEMANTICS_UNRESOLVED_STATE,
    OWNER_VERIFIER_ABSENT,
    POSITIVE_STATE,
    REPORT_PERIODS_NOT_INCREASING,
    SECURITY_BINDING_UNRESOLVED,
    SECURITY_NOT_IN_FILING,
    SOURCE_RECEIPT_MISMATCH,
    Institutional13FAdapterError,
    PilotRequest,
    build_recipe,
    _manager_denominator,
    _open_interval,
    _original_lineage,
    main as adapter_main,
    resolve_generation,
    run_pilot,
)
import lib.institutional_13f_adapter as adapter_module


FILER_CIK = "0001792167"
CUSIP = "037833100"
OTHER_CUSIP = "999999999"
PERIOD_PREV = "2026-03-31"
PERIOD_NOW = "2026-06-30"

ACCESSION_PREV = "0001792167-26-000001"
ACCEPTED_PREV = "2026-04-10T12:00:00Z"
RETAINED_PREV = "2026-04-10T12:05:00Z"
CUTOFF_PREV = "2026-04-12T00:00:00Z"
PUBLISHED_PREV = "2026-04-15T00:00:00Z"

ACCESSION_NOW = "0001792167-26-000002"
ACCEPTED_NOW = "2026-07-10T12:00:00Z"
RETAINED_NOW = "2026-07-10T12:05:00Z"
CUTOFF_NOW = "2026-07-12T00:00:00Z"
PUBLISHED_NOW = "2026-07-15T00:00:00Z"

DEFAULT_CUTOFF = datetime(2026, 8, 1, tzinfo=timezone.utc)


# --- Fixture builders (owner publish APIs only) -----------------------------


def _digest(seed: str) -> str:
    return sha256(seed.encode("utf-8")).hexdigest()


def _publish_raw(
    store,
    *,
    accession: str,
    report_period: str,
    accepted_at: str,
    retained_at: str,
    seed: str,
    filer_cik: str = FILER_CIK,
    form: str = "13F-HR",
):
    return publish_raw_evidence(
        store,
        accession=accession,
        filer_cik=filer_cik,
        form=form,
        report_period=report_period,
        accepted_at=accepted_at,
        retained_at=retained_at,
        source_url=(
            f"https://www.sec.gov/Archives/edgar/data/{int(filer_cik)}/"
            f"{accession.replace('-', '')}/index.json"
        ),
        payload=f"raw-fixture:{seed}".encode("utf-8"),
        producer_version="k2c-fixture/1.0.0",
    )


def _filing_row(
    *,
    accession: str,
    report_period: str,
    accepted_at: str,
    retained_at: str,
    receipt,
    filer_cik: str = FILER_CIK,
    is_amendment: bool = False,
    amendment_number: int | None = None,
    amendment_type: str | None = None,
    amends_accession: str | None = None,
    lineage_state: str = "original",
    table_entry_total: int | None = 2,
    table_value_total_usd: int | None = 2000,
    confidential_omitted: bool | None = False,
    form: str = "13F-HR",
    source_receipt_id: str | None = None,
    raw_sha256: str | None = None,
) -> dict:
    return {
        "accession": accession,
        "filer_cik": filer_cik,
        "filer_name": f"Fixture Manager {filer_cik}",
        "form": form,
        "filing_date": accepted_at[:10],
        "accepted_at": accepted_at,
        "report_period": report_period,
        "report_type": "13F HOLDINGS REPORT",
        "form13f_file_number": "028-00001",
        "is_amendment": is_amendment,
        "amendment_number": amendment_number,
        "amendment_type": amendment_type,
        "amends_accession": amends_accession,
        "lineage_state": lineage_state,
        "confidential_omitted": confidential_omitted,
        "table_entry_total": table_entry_total,
        "table_value_total_usd": table_value_total_usd,
        "other_manager_count": 0,
        "source_receipt_id": (
            source_receipt_id if source_receipt_id is not None else receipt.receipt_id
        ),
        "normalization_id": "norm_" + _digest(accession),
        "raw_sha256": raw_sha256 if raw_sha256 is not None else receipt.raw_object.sha256,
        "first_seen_at": accepted_at,
        "retained_at": retained_at,
        "parser_version": "k2c-fixture/1.0.0",
        "quality_state": "valid",
    }


def _holding_row(
    *,
    accession: str,
    sk: int,
    cusip: str,
    ssh_prn_amt: str | None = "100",
    ssh_prn_type: str | None = "SH",
    put_call: str | None = None,
    investment_discretion: str | None = "SOLE",
    value_usd: int | None = 1000,
) -> dict:
    return {
        "accession": accession,
        "infotable_sk": sk,
        "name_of_issuer": f"Issuer {cusip}",
        "title_of_class": "COM",
        "cusip": cusip,
        "figi": None,
        "value_reported": str(value_usd) if value_usd is not None else None,
        "value_unit": "USD",
        "value_usd": value_usd,
        "ssh_prn_amt": ssh_prn_amt,
        "ssh_prn_type": ssh_prn_type,
        "put_call": put_call,
        "investment_discretion": investment_discretion,
        "other_manager": None,
        "voting_authority_sole": 100,
        "voting_authority_shared": 0,
        "voting_authority_none": 0,
        "row_hash": _digest(f"{accession}:{sk}:{cusip}:{ssh_prn_amt}:{put_call}:{ssh_prn_type}"),
    }


def _publish_generation(
    store,
    *,
    report_period: str,
    filings: list[dict],
    holdings: list[dict],
    source_receipt_ids: list[str],
    published_at: str,
    source_cutoff_at: str,
    managers: tuple = (),
):
    prepared = prepare_catalog_generation(
        report_period=report_period,
        source_cutoff_at=source_cutoff_at,
        published_at=published_at,
        producer_version="k2c-fixture/1.0.0",
        filings=filings,
        holdings=holdings,
        manager_relationships=list(managers),
        source_receipt_ids=sorted(set(source_receipt_ids)),
        coverage={"state": "rolling", "discovered_filings": len(filings), "complete": True},
    )
    return publish_catalog_generation(store, prepared)


def _publish_standard_prev(store) -> None:
    """Publish an ordinary, uncontested predecessor-period filing+catalog."""
    receipt_prev = _publish_raw(
        store, accession=ACCESSION_PREV, report_period=PERIOD_PREV,
        accepted_at=ACCEPTED_PREV, retained_at=RETAINED_PREV, seed="prev",
    )
    filing_prev = _filing_row(
        accession=ACCESSION_PREV, report_period=PERIOD_PREV,
        accepted_at=ACCEPTED_PREV, retained_at=RETAINED_PREV, receipt=receipt_prev,
    )
    holdings_prev = [
        _holding_row(accession=ACCESSION_PREV, sk=1, cusip=CUSIP, ssh_prn_amt="100"),
        _holding_row(accession=ACCESSION_PREV, sk=2, cusip=OTHER_CUSIP, ssh_prn_amt="50"),
    ]
    _publish_generation(
        store, report_period=PERIOD_PREV, filings=[filing_prev], holdings=holdings_prev,
        source_receipt_ids=[receipt_prev.receipt_id],
        published_at=PUBLISHED_PREV, source_cutoff_at=CUTOFF_PREV,
    )


def _build_world(tmp_path: Path, *, q_now: str = "140",
                  investment_discretion: str = "SOLE") -> LocalStore:
    """The default lawful two-period world: one filer, one clean filing each."""
    store = LocalStore(tmp_path / "store")
    _publish_standard_prev(store)

    receipt_now = _publish_raw(
        store, accession=ACCESSION_NOW, report_period=PERIOD_NOW,
        accepted_at=ACCEPTED_NOW, retained_at=RETAINED_NOW, seed="now",
    )
    filing_now = _filing_row(
        accession=ACCESSION_NOW, report_period=PERIOD_NOW,
        accepted_at=ACCEPTED_NOW, retained_at=RETAINED_NOW, receipt=receipt_now,
    )
    holdings_now = [
        _holding_row(
            accession=ACCESSION_NOW, sk=1, cusip=CUSIP, ssh_prn_amt=q_now,
            investment_discretion=investment_discretion,
        ),
        _holding_row(accession=ACCESSION_NOW, sk=2, cusip=OTHER_CUSIP, ssh_prn_amt="60"),
    ]
    _publish_generation(
        store, report_period=PERIOD_NOW, filings=[filing_now], holdings=holdings_now,
        source_receipt_ids=[receipt_now.receipt_id],
        published_at=PUBLISHED_NOW, source_cutoff_at=CUTOFF_NOW,
    )
    return store


def _request(**overrides) -> PilotRequest:
    fields = dict(
        filer_cik=FILER_CIK,
        cusip=CUSIP,
        report_period_prev=PERIOD_PREV,
        report_period_now=PERIOD_NOW,
        cutoff=DEFAULT_CUTOFF,
    )
    fields.update(overrides)
    return PilotRequest(**fields)


# --- STRUCTURAL owner_semantics fixture --------------------------------------
#
# The ONE structural fixture used by this suite: a SHAPE-VALID owner_semantics
# payload -- every field this adapter itself reads is present, well-typed,
# and internally consistent. Sol review 5099850302 (2026-09-03) established
# that shape-validity is NECESSARY but never SUFFICIENT: this fixture (used
# as-is, or with one field mutated to be internally contradictory) can no
# longer reach a semantic positive under ANY mutation, because
# _CANONICAL_OWNER_VERIFIERS is empty by construction -- there is nothing in
# this repository that could verify ANY payload, however well-shaped, is
# TRUE. Its only remaining use is to prove the shape gate still accepts a
# well-formed payload's SHAPE while the (now-mandatory) owner-verification
# stage still refuses it -- see test_owner_semantics_contradiction_cannot_
# prove_a_positive and the other Sol-review hostile regressions below. It is
# NOT evidence that any production owner (Data OS / K2-B) can supply these
# values today -- see test_no_repo_producer_supplies_owner_manager_
# vehicle_epochs and DEC-K2C-SECURITY-BINDING-IS-OWNER-NATIVE-CUSIP. Every
# ID here is deliberately NOT filer/CIK-derived (a "structural_test_owner"
# stem, not "filer_<CIK>"), so it can never be mistaken for the repaired
# defect it exists to rule out. ``dataos_security_id`` is
# "SEC:US-XNAS-STRUCTURALTEST" -- a syntactically well-formed SEC: security
# identity under lib.dataos.identity's own grammar (a real MIC, an
# alphanumeric code), NOT a claim that this listing exists on any real
# venue; it exists only to satisfy the shape gate's grammar check (R1,
# 2026-09-03) without being mistaken for a real security.


def _structural_owner_semantics(
    *, decision_mode: str = "discretionary", vehicle_class: str = "concentrated_discretionary_active",
) -> dict:
    manager_complex_epoch = {
        "manager_complex_id": "mcx_structural_test_owner",
        "complex_epoch_id": "mce_structural_test_owner_v1",
        "interval": _open_interval(),
        "status": "active",
        "resolution_state": "resolved",
        "decision_mode": decision_mode,
        "actor_identity": {
            "role": "institution_or_manager_complex",
            "ontology_source": "B0_MANAGER_COMPLEX_DRAFT",
            "raw_actor_string": "STRUCTURAL TEST FIXTURE OWNER",
            "original_ontology_version": "structural-fixture/1.0.0",
            "resolution_state": "resolved",
            "remap_lineage": _original_lineage(),
        },
        "lineage": _original_lineage(),
    }
    vehicle_epoch = {
        "vehicle_id": "veh_structural_test_owner",
        "vehicle_epoch_id": "vie_structural_test_owner_v1",
        "manager_complex_id": "mcx_structural_test_owner",
        "complex_epoch_id": "mce_structural_test_owner_v1",
        "interval": _open_interval(),
        "status": "active",
        "resolution_state": "resolved",
        "decision_mode": decision_mode,
        "vehicle_class": vehicle_class,
        "lineage": _original_lineage(),
    }
    return {
        "provenance": {"owner": "structural_test_fixture", "reference_id": "structural-fixture-001"},
        "security": {
            "dataos_security_id": "SEC:US-XNAS-STRUCTURALTEST",
            "dataos_resolution": "alias_table_resolved",
        },
        "manager_complex_epoch": manager_complex_epoch,
        "vehicle_epoch": vehicle_epoch,
    }


# --- (a) happy path -----------------------------------------------------


def test_happy_path_two_period_read_compiles(tmp_path: Path) -> None:
    """Repaired truth (K2-C semantic-owner repair, 2026-09-03; blocker+MAJOR
    repair per Sol review 5099850302, 2026-09-03).

    A clean two-period world with SOLE discretion and NO owner-supplied
    security/manager/vehicle binding can no longer reach a semantic
    positive -- only the owner-unresolved terminal receipt. This test's
    original adverse intent (prove the full read pipeline assembles a
    correct, byte-bounded, persistence-honest receipt) is preserved; its
    original oracle (``state == POSITIVE_STATE``) is now exactly the
    defect this repair exists to kill. There is no positive-path oracle
    left anywhere in this suite: the owner-verifier registry
    (``_CANONICAL_OWNER_VERIFIERS``) is empty by construction, so
    ``POSITIVE_STATE`` is unreachable regardless of what ``owner_semantics``
    a caller supplies -- see test_no_canonical_owner_verifier_is_registered
    and the hostile regressions below.
    """
    store = _build_world(tmp_path)
    receipt = run_pilot(store, _request())

    assert receipt["schema"] == "institutional_intelligence.owner_read_receipt/v1"
    assert receipt["state"] == OWNER_SEMANTICS_UNRESOLVED_STATE
    assert receipt["state"] != POSITIVE_STATE
    assert receipt["compiled_observation_state"] is None
    assert receipt["recipe"] is None
    assert receipt["compiled"] is None
    assert receipt["measure"] == {"state": "not_compiled", "reason": "owner_semantics_unresolved"}
    assert receipt["denominators"]["current"]["state"] == "complete"
    assert receipt["denominators"]["previous"]["state"] == "complete"
    assert receipt["periods"]["current"]["filing"]["accession"] == ACCESSION_NOW
    assert receipt["periods"]["previous"]["filing"]["accession"] == ACCESSION_PREV
    # The raw owner fact is still honestly present -- SOLE never disappears,
    # it simply feeds no semantics anywhere any more.
    assert receipt["periods"]["current"]["row"]["investment_discretion"] == "SOLE"
    assert receipt["persistence"] == "none"
    assert receipt["owner_payloads_copied"] is False
    assert receipt["authority"] == {
        "can_rank": False, "can_gate": False, "can_size": False,
        "can_originate": False, "can_open_entry": False,
    }
    assert receipt["security_binding"] == {
        "key_type": "cusip", "cusip": CUSIP,
        "dataos_security_id": None,
        "dataos_resolution": SECURITY_BINDING_UNRESOLVED,
    }
    assert receipt["owner_semantics"] == {
        "security": {"resolved": False, "resolution": SECURITY_BINDING_UNRESOLVED},
        "manager_vehicle": {"resolved": False, "resolution": MANAGER_VEHICLE_BINDING_UNRESOLVED},
        "provenance": None,
        # (Sol review 5099850302 repair) owner_semantics was never supplied
        # at all here -- the shape gate's first check (not even a Mapping)
        # is what refused it, not the empty verifier registry.
        "reason": adapter_module.OWNER_SEMANTICS_MALFORMED,
    }
    assert receipt["receipt_id"].startswith("i13fpilot_")
    assert receipt["periods"]["previous"]["pointer"]["state"] == "read"
    assert receipt["periods"]["current"]["pointer"]["state"] == "read"
    assert len(canonical_json_bytes(receipt)) < 256 * 1024


# --- (b) determinism ------------------------------------------------------


def test_determinism_same_inputs_are_byte_identical(tmp_path: Path) -> None:
    store = _build_world(tmp_path)
    first = run_pilot(store, _request())
    second = run_pilot(store, _request())

    assert first == second
    assert first["receipt_id"] == second["receipt_id"]
    assert canonical_json_bytes(first) == canonical_json_bytes(second)

    # Determinism also holds when a shape-valid owner_semantics is supplied
    # (Sol review 5099850302 repair supersedes the old "owner-resolved path"
    # framing -- the shape-valid structural fixture is STILL refused, by the
    # empty verifier registry, so this now proves determinism of the
    # unresolved-by-registry-absence branch): identical store + request +
    # owner_semantics -> byte-identical receipt and receipt_id. Fresh dicts
    # each call rule out identity reuse.
    first_shaped = run_pilot(store, _request(), owner_semantics=_structural_owner_semantics())
    second_shaped = run_pilot(store, _request(), owner_semantics=_structural_owner_semantics())
    assert first_shaped == second_shaped
    assert first_shaped["receipt_id"] == second_shaped["receipt_id"]
    assert canonical_json_bytes(first_shaped) == canonical_json_bytes(second_shaped)
    assert first_shaped["state"] == OWNER_SEMANTICS_UNRESOLVED_STATE
    assert first_shaped["owner_semantics"]["reason"] == OWNER_VERIFIER_ABSENT


# --- (c) explicit generation_id binds a superseded/older generation --------


def test_explicit_generation_id_binds_the_exact_older_generation(tmp_path: Path) -> None:
    store = _build_world(tmp_path)
    generation_a = resolve_generation(store, report_period=PERIOD_NOW, cutoff=DEFAULT_CUTOFF)

    other_accession = "0009999999-26-000099"
    other_receipt = _publish_raw(
        store, accession=other_accession, report_period=PERIOD_NOW,
        accepted_at="2026-07-20T12:00:00Z", retained_at="2026-07-20T12:05:00Z",
        seed="sibling", filer_cik="0009999999",
    )
    other_filing = _filing_row(
        accession=other_accession, report_period=PERIOD_NOW,
        accepted_at="2026-07-20T12:00:00Z", retained_at="2026-07-20T12:05:00Z",
        receipt=other_receipt, filer_cik="0009999999",
    )
    other_holdings = [_holding_row(accession=other_accession, sk=1, cusip=OTHER_CUSIP, ssh_prn_amt="5")]

    filings_b = list(generation_a.filings) + [other_filing]
    holdings_b = list(generation_a.holdings) + other_holdings
    receipt_ids_b = sorted({str(row["source_receipt_id"]) for row in filings_b})
    generation_b = _publish_generation(
        store, report_period=PERIOD_NOW, filings=filings_b, holdings=holdings_b,
        source_receipt_ids=receipt_ids_b,
        published_at="2026-07-25T00:00:00Z", source_cutoff_at="2026-07-22T00:00:00Z",
    )
    assert generation_b.generation_id != generation_a.generation_id
    assert generation_b.current_generation_id == generation_b.generation_id

    # The pointer now resolves to generation B; pin generation A explicitly.
    # (Sol review 5099850302 repair) periods/pointer/filing/row are computed
    # identically by run_pilot regardless of whether the owner seam ever
    # resolves -- ONLY recipe/compiled/state differ -- so this test's real
    # subject (generation pinning, orthogonal to the owner-seam repair)
    # stays fully provable on the now-only-reachable unresolved receipt; no
    # owner_semantics is supplied at all.
    receipt = run_pilot(
        store, _request(cutoff=datetime(2026, 8, 1, tzinfo=timezone.utc),
                        generation_id_now=generation_a.generation_id),
    )
    assert receipt["state"] == OWNER_SEMANTICS_UNRESOLVED_STATE
    assert receipt["periods"]["current"]["generation_id"] == generation_a.generation_id
    assert receipt["periods"]["current"]["filing"]["accession"] == ACCESSION_NOW

    # Finding 3: the explicit-generation_id path never dereferenced the
    # current-pointer object -- catalog._load_generation hard-codes
    # current_generation_id/pointer_updated/superseded for that path, so the
    # receipt must say "not_read", never assert those fabricated values.
    assert receipt["periods"]["current"]["pointer"] == {"state": "not_read"}
    # The previous period was resolved via the ordinary current-pointer read
    # (no generation_id_prev pinned), so it genuinely dereferenced the
    # pointer and may report the real fields.
    assert receipt["periods"]["previous"]["pointer"]["state"] == "read"
    assert "current_generation_id" in receipt["periods"]["previous"]["pointer"]
    assert "pointer_updated" in receipt["periods"]["previous"]["pointer"]
    assert "superseded" in receipt["periods"]["previous"]["pointer"]


# --- (d) generation published after cutoff ---------------------------------


def test_generation_published_after_cutoff_is_refused(tmp_path: Path) -> None:
    store = _build_world(tmp_path)
    cutoff = datetime(2026, 7, 1, tzinfo=timezone.utc)  # before PUBLISHED_NOW (2026-07-15)

    receipt = run_pilot(store, _request(cutoff=cutoff))

    assert receipt["state"] == GENERATION_NOT_KNOWABLE_AT_CUTOFF
    assert receipt["refusal"]["reason"] == GENERATION_NOT_KNOWABLE_AT_CUTOFF
    assert "compiled" not in receipt
    assert "measure" not in receipt


# --- (e) filing accepted after cutoff: chosen typed law = filing_not_found -


def test_filing_not_yet_filed_for_current_period_is_filing_not_found(tmp_path: Path) -> None:
    """Documented typed-law choice for case (e).

    ``prepare_catalog_generation`` enforces ``max(accepted_at, retained_at)
    <= source_cutoff_at <= published_at`` for every filing row it accepts.
    Consequently a generation that IS knowable at some cutoff can never
    contain a filing that individually is NOT knowable at that same cutoff --
    publishing a generation already proves every one of its filings was
    accepted/retained no later than its own ``published_at``.  A too-recent
    filing therefore always manifests as either ``generation_not_knowable_at_
    cutoff`` (case d, the containing generation itself is too new) or, as
    modeled here, ``filing_not_found`` (the filer simply has no row yet in
    a catalog generation that IS already knowable -- e.g. the quarter just
    closed and other managers have filed but this one has not).
    ``not_yet_knowable`` is retained in the adapter as a defensive typed
    constant for a future owner extension that might relax this invariant,
    but is not independently reachable through this owner's current write
    path and is therefore not exercised here.
    """
    store = LocalStore(tmp_path / "store")
    _publish_standard_prev(store)

    other_accession = "0009999999-26-000001"
    other_receipt = _publish_raw(
        store, accession=other_accession, report_period=PERIOD_NOW,
        accepted_at=ACCEPTED_NOW, retained_at=RETAINED_NOW,
        seed="sibling-now", filer_cik="0009999999",
    )
    other_filing = _filing_row(
        accession=other_accession, report_period=PERIOD_NOW,
        accepted_at=ACCEPTED_NOW, retained_at=RETAINED_NOW,
        receipt=other_receipt, filer_cik="0009999999",
    )
    other_holdings = [_holding_row(accession=other_accession, sk=1, cusip=OTHER_CUSIP, ssh_prn_amt="10")]
    _publish_generation(
        store, report_period=PERIOD_NOW, filings=[other_filing], holdings=other_holdings,
        source_receipt_ids=[other_receipt.receipt_id],
        published_at=PUBLISHED_NOW, source_cutoff_at=CUTOFF_NOW,
    )

    receipt = run_pilot(store, _request())

    assert receipt["state"] == FILING_NOT_FOUND
    assert "compiled" not in receipt


# --- (f) missing predecessor period catalog --------------------------------


def test_missing_predecessor_catalog_is_typed_refusal_never_zero(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store")
    # Only the "now" period is ever published; PERIOD_PREV has no catalog at all.
    receipt_now = _publish_raw(
        store, accession=ACCESSION_NOW, report_period=PERIOD_NOW,
        accepted_at=ACCEPTED_NOW, retained_at=RETAINED_NOW, seed="now",
    )
    filing_now = _filing_row(
        accession=ACCESSION_NOW, report_period=PERIOD_NOW,
        accepted_at=ACCEPTED_NOW, retained_at=RETAINED_NOW, receipt=receipt_now,
    )
    holdings_now = [
        _holding_row(accession=ACCESSION_NOW, sk=1, cusip=CUSIP, ssh_prn_amt="140"),
        _holding_row(accession=ACCESSION_NOW, sk=2, cusip=OTHER_CUSIP, ssh_prn_amt="60"),
    ]
    _publish_generation(
        store, report_period=PERIOD_NOW, filings=[filing_now], holdings=holdings_now,
        source_receipt_ids=[receipt_now.receipt_id],
        published_at=PUBLISHED_NOW, source_cutoff_at=CUTOFF_NOW,
    )

    receipt = run_pilot(store, _request())

    assert receipt["state"] == FILING_NOT_FOUND
    assert "measure" not in receipt
    assert "compiled" not in receipt


# --- (g) amendment lineage visibility switches on cutoff -------------------


def test_amendment_known_after_cutoff_is_invisible_then_supersedes(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store")
    _publish_standard_prev(store)

    receipt_orig = _publish_raw(
        store, accession=ACCESSION_NOW, report_period=PERIOD_NOW,
        accepted_at=ACCEPTED_NOW, retained_at=RETAINED_NOW, seed="now-orig",
    )
    filing_orig = _filing_row(
        accession=ACCESSION_NOW, report_period=PERIOD_NOW,
        accepted_at=ACCEPTED_NOW, retained_at=RETAINED_NOW, receipt=receipt_orig,
    )
    holdings_orig = [
        _holding_row(accession=ACCESSION_NOW, sk=1, cusip=CUSIP, ssh_prn_amt="140"),
        _holding_row(accession=ACCESSION_NOW, sk=2, cusip=OTHER_CUSIP, ssh_prn_amt="60"),
    ]
    generation_a = _publish_generation(
        store, report_period=PERIOD_NOW, filings=[filing_orig], holdings=holdings_orig,
        source_receipt_ids=[receipt_orig.receipt_id],
        published_at=PUBLISHED_NOW, source_cutoff_at=CUTOFF_NOW,
    )

    amendment_accession = "0001792167-26-000003"
    accepted_amend = "2026-07-20T12:00:00Z"
    retained_amend = "2026-07-20T12:05:00Z"
    receipt_amend = _publish_raw(
        store, accession=amendment_accession, report_period=PERIOD_NOW,
        accepted_at=accepted_amend, retained_at=retained_amend, seed="now-amend",
    )
    filing_amend = _filing_row(
        accession=amendment_accession, report_period=PERIOD_NOW,
        accepted_at=accepted_amend, retained_at=retained_amend, receipt=receipt_amend,
        is_amendment=True, amendment_number=1, amendment_type="RESTATEMENT",
        amends_accession=ACCESSION_NOW, lineage_state="amendment_restatement",
    )
    holdings_amend = [
        _holding_row(accession=amendment_accession, sk=1, cusip=CUSIP, ssh_prn_amt="150"),
        _holding_row(accession=amendment_accession, sk=2, cusip=OTHER_CUSIP, ssh_prn_amt="65"),
    ]
    generation_b = _publish_generation(
        store, report_period=PERIOD_NOW,
        filings=[filing_orig, filing_amend], holdings=holdings_orig + holdings_amend,
        source_receipt_ids=[receipt_orig.receipt_id, receipt_amend.receipt_id],
        published_at="2026-07-25T00:00:00Z", source_cutoff_at="2026-07-22T00:00:00Z",
    )

    # (Sol review 5099850302 repair) periods/filing/row are computed
    # identically by run_pilot regardless of whether the owner seam ever
    # resolves -- ONLY recipe/compiled/state differ -- so this test's real
    # subject (amendment-chain visibility switching on cutoff, orthogonal to
    # the owner-seam repair) stays fully provable on the now-only-reachable
    # unresolved receipt; no owner_semantics is supplied at all. The
    # q_now == 150 fact moves from the (now unreachable) top-level
    # ``measure`` block to the honestly-always-present per-period row.

    # Before the amendment exists (generation A is the only knowable option).
    cutoff_before = datetime(2026, 7, 16, tzinfo=timezone.utc)
    receipt_before = run_pilot(
        store, _request(cutoff=cutoff_before, generation_id_now=generation_a.generation_id),
    )
    assert receipt_before["state"] == OWNER_SEMANTICS_UNRESOLVED_STATE
    assert receipt_before["periods"]["current"]["filing"]["accession"] == ACCESSION_NOW
    assert receipt_before["periods"]["current"]["filing"]["is_amendment"] is False

    # After the amendment is knowable: the chain tip (the restatement) is used.
    cutoff_after = datetime(2026, 8, 1, tzinfo=timezone.utc)
    receipt_after = run_pilot(
        store, _request(cutoff=cutoff_after, generation_id_now=generation_b.generation_id),
    )
    assert receipt_after["state"] == OWNER_SEMANTICS_UNRESOLVED_STATE
    assert receipt_after["periods"]["current"]["filing"]["accession"] == amendment_accession
    assert receipt_after["periods"]["current"]["filing"]["is_amendment"] is True
    assert receipt_after["periods"]["current"]["row"]["ssh_prn_amt"] == "150"


# --- (h) non-restatement amendment tip -------------------------------------


def test_non_restatement_amendment_tip_is_unsupported(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store")
    _publish_standard_prev(store)

    receipt_orig = _publish_raw(
        store, accession=ACCESSION_NOW, report_period=PERIOD_NOW,
        accepted_at=ACCEPTED_NOW, retained_at=RETAINED_NOW, seed="now-orig-h",
    )
    filing_orig = _filing_row(
        accession=ACCESSION_NOW, report_period=PERIOD_NOW,
        accepted_at=ACCEPTED_NOW, retained_at=RETAINED_NOW, receipt=receipt_orig,
    )
    holdings_orig = [
        _holding_row(accession=ACCESSION_NOW, sk=1, cusip=CUSIP, ssh_prn_amt="140"),
        _holding_row(accession=ACCESSION_NOW, sk=2, cusip=OTHER_CUSIP, ssh_prn_amt="60"),
    ]
    amendment_accession = "0001792167-26-000004"
    accepted_amend = "2026-07-20T12:00:00Z"
    retained_amend = "2026-07-20T12:05:00Z"
    receipt_amend = _publish_raw(
        store, accession=amendment_accession, report_period=PERIOD_NOW,
        accepted_at=accepted_amend, retained_at=retained_amend, seed="now-amend-h",
    )
    filing_amend = _filing_row(
        accession=amendment_accession, report_period=PERIOD_NOW,
        accepted_at=accepted_amend, retained_at=retained_amend, receipt=receipt_amend,
        is_amendment=True, amendment_number=1, amendment_type="NEW HOLDINGS",
        amends_accession=ACCESSION_NOW, lineage_state="amendment_new_holdings",
        table_entry_total=1, table_value_total_usd=500,
    )
    holdings_amend = [_holding_row(accession=amendment_accession, sk=1, cusip="111111119", ssh_prn_amt="10")]
    generation = _publish_generation(
        store, report_period=PERIOD_NOW,
        filings=[filing_orig, filing_amend], holdings=holdings_orig + holdings_amend,
        source_receipt_ids=[receipt_orig.receipt_id, receipt_amend.receipt_id],
        published_at="2026-07-25T00:00:00Z", source_cutoff_at="2026-07-22T00:00:00Z",
    )

    receipt = run_pilot(
        store,
        _request(cutoff=datetime(2026, 8, 1, tzinfo=timezone.utc), generation_id_now=generation.generation_id),
    )

    assert receipt["state"] == AMENDMENT_COMPOSITION_UNSUPPORTED


# --- (i) cusip absent -------------------------------------------------------


def test_cusip_absent_is_security_not_in_filing(tmp_path: Path) -> None:
    store = _build_world(tmp_path)
    receipt = run_pilot(store, _request(cusip="111111111"))
    assert receipt["state"] == SECURITY_NOT_IN_FILING


# --- (j) two rows same cusip -------------------------------------------------


def test_duplicate_cusip_rows_is_ambiguous_holdings_rows(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store")
    _publish_standard_prev(store)

    receipt_now = _publish_raw(
        store, accession=ACCESSION_NOW, report_period=PERIOD_NOW,
        accepted_at=ACCEPTED_NOW, retained_at=RETAINED_NOW, seed="now-dup",
    )
    filing_now = _filing_row(
        accession=ACCESSION_NOW, report_period=PERIOD_NOW,
        accepted_at=ACCEPTED_NOW, retained_at=RETAINED_NOW, receipt=receipt_now,
        table_entry_total=3, table_value_total_usd=3000,
    )
    holdings_now = [
        _holding_row(accession=ACCESSION_NOW, sk=1, cusip=CUSIP, ssh_prn_amt="140"),
        _holding_row(accession=ACCESSION_NOW, sk=2, cusip=CUSIP, ssh_prn_amt="10"),
        _holding_row(accession=ACCESSION_NOW, sk=3, cusip=OTHER_CUSIP, ssh_prn_amt="60"),
    ]
    _publish_generation(
        store, report_period=PERIOD_NOW, filings=[filing_now], holdings=holdings_now,
        source_receipt_ids=[receipt_now.receipt_id],
        published_at=PUBLISHED_NOW, source_cutoff_at=CUTOFF_NOW,
    )

    receipt = run_pilot(store, _request())
    assert receipt["state"] == AMBIGUOUS_HOLDINGS_ROWS


# --- (k) put_call-only rows -------------------------------------------------


def test_put_call_only_row_is_security_not_in_filing(tmp_path: Path) -> None:
    """Design section 4/5.3 already resolves this deterministically:

    put_call-set rows are excluded from selection BEFORE the 0/1/many count
    is taken, so a CUSIP that only appears on a derivative row falls through
    to the same zero-remaining-rows branch as an absent CUSIP.
    """
    store = LocalStore(tmp_path / "store")
    _publish_standard_prev(store)

    receipt_now = _publish_raw(
        store, accession=ACCESSION_NOW, report_period=PERIOD_NOW,
        accepted_at=ACCEPTED_NOW, retained_at=RETAINED_NOW, seed="now-putcall",
    )
    filing_now = _filing_row(
        accession=ACCESSION_NOW, report_period=PERIOD_NOW,
        accepted_at=ACCEPTED_NOW, retained_at=RETAINED_NOW, receipt=receipt_now,
    )
    holdings_now = [
        _holding_row(accession=ACCESSION_NOW, sk=1, cusip=CUSIP, ssh_prn_amt="140", put_call="PUT"),
        _holding_row(accession=ACCESSION_NOW, sk=2, cusip=OTHER_CUSIP, ssh_prn_amt="60"),
    ]
    _publish_generation(
        store, report_period=PERIOD_NOW, filings=[filing_now], holdings=holdings_now,
        source_receipt_ids=[receipt_now.receipt_id],
        published_at=PUBLISHED_NOW, source_cutoff_at=CUTOFF_NOW,
    )

    receipt = run_pilot(store, _request())
    assert receipt["state"] == SECURITY_NOT_IN_FILING


# --- (l) ssh_prn_type PRN ----------------------------------------------------


def test_prn_measure_type_is_measure_unit_unsupported(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store")
    _publish_standard_prev(store)

    receipt_now = _publish_raw(
        store, accession=ACCESSION_NOW, report_period=PERIOD_NOW,
        accepted_at=ACCEPTED_NOW, retained_at=RETAINED_NOW, seed="now-prn",
    )
    filing_now = _filing_row(
        accession=ACCESSION_NOW, report_period=PERIOD_NOW,
        accepted_at=ACCEPTED_NOW, retained_at=RETAINED_NOW, receipt=receipt_now,
    )
    holdings_now = [
        _holding_row(accession=ACCESSION_NOW, sk=1, cusip=CUSIP, ssh_prn_amt="140", ssh_prn_type="PRN"),
        _holding_row(accession=ACCESSION_NOW, sk=2, cusip=OTHER_CUSIP, ssh_prn_amt="60"),
    ]
    _publish_generation(
        store, report_period=PERIOD_NOW, filings=[filing_now], holdings=holdings_now,
        source_receipt_ids=[receipt_now.receipt_id],
        published_at=PUBLISHED_NOW, source_cutoff_at=CUTOFF_NOW,
    )

    receipt = run_pilot(store, _request())
    assert receipt["state"] == MEASURE_UNIT_UNSUPPORTED


# --- (m) tampered stored object ----------------------------------------------


def test_tampered_holdings_object_raises_owner_exception(tmp_path: Path) -> None:
    store = _build_world(tmp_path)
    generation = load_catalog_generation(store, report_period=PERIOD_NOW)
    bucket_role = holding_bucket_role(ACCESSION_NOW)
    descriptor = next(item for item in generation.manifest.artifacts if item.role == bucket_role)
    object_path = store.root / descriptor.object_key
    data = bytearray(object_path.read_bytes())
    data[-1] ^= 0xFF
    object_path.write_bytes(bytes(data))

    with pytest.raises(Institutional13FError):
        run_pilot(store, _request())


# --- (n) filing/receipt cross-check mismatch ---------------------------------


def test_source_receipt_mismatch_is_hard_refusal(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store")
    _publish_standard_prev(store)

    receipt_now = _publish_raw(
        store, accession=ACCESSION_NOW, report_period=PERIOD_NOW,
        accepted_at=ACCEPTED_NOW, retained_at=RETAINED_NOW, seed="now-mismatch",
    )
    wrong_sha256 = _digest("this-is-not-the-real-raw-payload-digest")
    filing_now = _filing_row(
        accession=ACCESSION_NOW, report_period=PERIOD_NOW,
        accepted_at=ACCEPTED_NOW, retained_at=RETAINED_NOW, receipt=receipt_now,
        raw_sha256=wrong_sha256,
    )
    holdings_now = [
        _holding_row(accession=ACCESSION_NOW, sk=1, cusip=CUSIP, ssh_prn_amt="140"),
        _holding_row(accession=ACCESSION_NOW, sk=2, cusip=OTHER_CUSIP, ssh_prn_amt="60"),
    ]
    _publish_generation(
        store, report_period=PERIOD_NOW, filings=[filing_now], holdings=holdings_now,
        source_receipt_ids=[receipt_now.receipt_id],
        published_at=PUBLISHED_NOW, source_cutoff_at=CUTOFF_NOW,
    )

    receipt = run_pilot(store, _request())
    assert receipt["state"] == SOURCE_RECEIPT_MISMATCH
    assert "raw_sha256" in receipt["refusal"]["detail"]


# --- (o)/(p) REMOVED (Sol review 5099850302 repair, 2026-09-03) ------------
#
# ``test_non_sole_discretion_compiles_non_positive_via_the_compiler`` and
# ``test_compiled_output_is_uninjectable_and_matches_independent_recompute``
# both reached the K2-B compiler through ``run_pilot(..., owner_semantics=
# _structural_owner_semantics())`` and asserted on ``receipt["compiled"]``.
# That path is now unreachable by construction (``_CANONICAL_OWNER_
# VERIFIERS`` is empty) -- run_pilot never returns a non-None ``compiled``
# for ANY caller-supplied owner_semantics, so both tests' premises are gone,
# not merely their oracle. ``build_recipe``/``validate_recipe``/
# ``compile_recipe`` remain directly callable (see the module docstring --
# "the structure a future owner wires into"); the STRUCTURAL fixture that
# used to prove they compose correctly through ``run_pilot`` is retired
# along with them, per the commission's "remove the positive-reaching
# structural-fixture test(s)" instruction. PilotRequest's own field surface
# (no override/compiled channel) is still asserted independently in
# test_no_repo_producer_supplies_owner_manager_vehicle_epochs and the
# ``_verify_owner_semantics`` signature checks below.


# --- extra: malformed cusip grammar (named in section 5.3, not lettered) ---


def test_malformed_cusip_is_cusip_grammar_invalid(tmp_path: Path) -> None:
    store = _build_world(tmp_path)
    receipt = run_pilot(store, _request(cusip="short"))
    assert receipt["state"] == CUSIP_GRAMMAR_INVALID


def test_generation_id_pinned_but_still_too_new_is_refused(tmp_path: Path) -> None:
    """generation_not_knowable_at_cutoff applies to an EXPLICIT id too."""
    store = _build_world(tmp_path)
    generation_now = resolve_generation(store, report_period=PERIOD_NOW, cutoff=DEFAULT_CUTOFF)
    receipt = run_pilot(
        store,
        _request(
            cutoff=datetime(2026, 7, 1, tzinfo=timezone.utc),
            generation_id_now=generation_now.generation_id,
        ),
    )
    assert receipt["state"] == GENERATION_NOT_KNOWABLE_AT_CUTOFF


# --- (q) CLI end-to-end -----------------------------------------------------


def test_cli_end_to_end_positive_and_refusal(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Repaired truth (frozen spec point 8): the CLI has no owner_semantics
    channel -- deliberately, since a human-supplied override would be the
    exact back door this repair exists to close. Its real-world outcome on
    a clean two-period world is therefore always the owner-unresolved
    terminal receipt, never a semantic positive.
    """
    store = _build_world(tmp_path)

    receipt_path = tmp_path / "receipt.json"
    exit_code = adapter_main([
        "--filer-cik", FILER_CIK,
        "--cusip", CUSIP,
        "--report-period-now", PERIOD_NOW,
        "--report-period-prev", PERIOD_PREV,
        "--cutoff", "2026-08-01T00:00:00Z",
        "--local-dir", str(store.root),
        "--receipt", str(receipt_path),
    ])
    assert exit_code == 0
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert payload["state"] == OWNER_SEMANTICS_UNRESOLVED_STATE
    assert payload["recipe"] is None
    assert payload["compiled"] is None
    out = capsys.readouterr().out
    assert f"state: {OWNER_SEMANTICS_UNRESOLVED_STATE}" in out

    refusal_path = tmp_path / "refusal.json"
    exit_code_refusal = adapter_main([
        "--filer-cik", FILER_CIK,
        "--cusip", "111111111",
        "--report-period-now", PERIOD_NOW,
        "--report-period-prev", PERIOD_PREV,
        "--cutoff", "2026-08-01T00:00:00Z",
        "--local-dir", str(store.root),
        "--receipt", str(refusal_path),
    ])
    assert exit_code_refusal == 0
    refusal_payload = json.loads(refusal_path.read_text(encoding="utf-8"))
    assert refusal_payload["state"] == SECURITY_NOT_IN_FILING
    out_refusal = capsys.readouterr().out
    assert f"state: {SECURITY_NOT_IN_FILING}" in out_refusal


def test_cli_missing_required_argument_exits_nonzero(tmp_path: Path) -> None:
    # No store was ever built at this local_dir and no env vars are set:
    # build_institutional_13f_store still succeeds (LocalStore just mkdirs),
    # and the pointer read for PERIOD_PREV is a clean absence -> a LAWFUL
    # filing_not_found receipt, exit 0.  To exercise a genuine non-zero exit
    # we omit a required CLI argument instead (argparse contract failure,
    # which argparse enforces by raising SystemExit(2) directly).
    with pytest.raises(SystemExit) as excinfo:
        adapter_main([
            "--filer-cik", FILER_CIK,
            "--cusip", CUSIP,
            "--report-period-now", PERIOD_NOW,
            # --report-period-prev deliberately omitted
            "--local-dir", str(tmp_path / "store"),
            "--receipt", str(tmp_path / "receipt.json"),
        ])
    assert excinfo.value.code != 0


def test_cli_store_outage_like_missing_env_exits_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # No --local-dir and no dedicated env vars configured: the owner's own
    # build_institutional_13f_store refuses fail-closed (an incomplete R2
    # configuration is a contract error, never silently treated as a local
    # dry run).  The CLI boundary must turn that into a non-zero exit.
    for name in (
        "INSTITUTIONAL_13F_R2_ENDPOINT",
        "INSTITUTIONAL_13F_R2_ACCESS_KEY_ID",
        "INSTITUTIONAL_13F_R2_SECRET_ACCESS_KEY",
        "INSTITUTIONAL_13F_R2_BUCKET",
    ):
        monkeypatch.delenv(name, raising=False)

    exit_code = adapter_main([
        "--filer-cik", FILER_CIK,
        "--cusip", CUSIP,
        "--report-period-now", PERIOD_NOW,
        "--report-period-prev", PERIOD_PREV,
        "--receipt", str(tmp_path / "receipt.json"),
    ])
    assert exit_code == 1


# --- adversarial review repair: Finding 4 (MAJOR) ----------------------------
#
# A swapped or equal report-period pair used to escape as an untyped
# InstitutionalIntelligenceError raised from validate_recipe() deep inside
# run_pilot's happy path (outside the typed PilotRefusal envelope) -- the
# CLI's broad exception boundary turned that into exit 1 with no receipt at
# all.  This is now a typed refusal checked before any store read.


def test_swapped_report_periods_is_a_typed_refusal_not_an_exception(tmp_path: Path) -> None:
    store = _build_world(tmp_path)
    receipt = run_pilot(
        store, _request(report_period_prev=PERIOD_NOW, report_period_now=PERIOD_PREV)
    )
    assert receipt["state"] == REPORT_PERIODS_NOT_INCREASING
    assert receipt["refusal"]["reason"] == REPORT_PERIODS_NOT_INCREASING
    assert "compiled" not in receipt
    assert "measure" not in receipt


def test_equal_report_periods_is_a_typed_refusal_not_an_exception(tmp_path: Path) -> None:
    store = _build_world(tmp_path)
    receipt = run_pilot(
        store, _request(report_period_prev=PERIOD_NOW, report_period_now=PERIOD_NOW)
    )
    assert receipt["state"] == REPORT_PERIODS_NOT_INCREASING


def test_swapped_and_equal_report_periods_produce_typed_receipts_via_cli(tmp_path: Path) -> None:
    store = _build_world(tmp_path)

    swapped_path = tmp_path / "swapped.json"
    exit_code_swapped = adapter_main([
        "--filer-cik", FILER_CIK,
        "--cusip", CUSIP,
        "--report-period-now", PERIOD_PREV,
        "--report-period-prev", PERIOD_NOW,
        "--cutoff", "2026-08-01T00:00:00Z",
        "--local-dir", str(store.root),
        "--receipt", str(swapped_path),
    ])
    assert exit_code_swapped == 0
    swapped_payload = json.loads(swapped_path.read_text(encoding="utf-8"))
    assert swapped_payload["state"] == REPORT_PERIODS_NOT_INCREASING

    equal_path = tmp_path / "equal.json"
    exit_code_equal = adapter_main([
        "--filer-cik", FILER_CIK,
        "--cusip", CUSIP,
        "--report-period-now", PERIOD_NOW,
        "--report-period-prev", PERIOD_NOW,
        "--cutoff", "2026-08-01T00:00:00Z",
        "--local-dir", str(store.root),
        "--receipt", str(equal_path),
    ])
    assert exit_code_equal == 0
    equal_payload = json.loads(equal_path.read_text(encoding="utf-8"))
    assert equal_payload["state"] == REPORT_PERIODS_NOT_INCREASING


# --- adversarial review repair: Finding 8 (NOTE) -----------------------------


def test_source_receipt_retained_at_mismatch_is_hard_refusal(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store")
    _publish_standard_prev(store)

    receipt_now = _publish_raw(
        store, accession=ACCESSION_NOW, report_period=PERIOD_NOW,
        accepted_at=ACCEPTED_NOW, retained_at=RETAINED_NOW, seed="now-retained-mismatch",
    )
    filing_now = _filing_row(
        accession=ACCESSION_NOW, report_period=PERIOD_NOW,
        accepted_at=ACCEPTED_NOW, retained_at="2026-07-10T12:09:00Z",
        receipt=receipt_now,
    )
    holdings_now = [
        _holding_row(accession=ACCESSION_NOW, sk=1, cusip=CUSIP, ssh_prn_amt="140"),
        _holding_row(accession=ACCESSION_NOW, sk=2, cusip=OTHER_CUSIP, ssh_prn_amt="60"),
    ]
    _publish_generation(
        store, report_period=PERIOD_NOW, filings=[filing_now], holdings=holdings_now,
        source_receipt_ids=[receipt_now.receipt_id],
        published_at=PUBLISHED_NOW, source_cutoff_at=CUTOFF_NOW,
    )

    receipt = run_pilot(store, _request())
    assert receipt["state"] == SOURCE_RECEIPT_MISMATCH
    assert "retained_at" in receipt["refusal"]["detail"]


# --- adversarial review repair: ambiguous_filing_lineage tie -----------------


def test_ambiguous_filing_lineage_tie_is_refused(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store")
    _publish_standard_prev(store)

    receipt_a = _publish_raw(
        store, accession=ACCESSION_NOW, report_period=PERIOD_NOW,
        accepted_at=ACCEPTED_NOW, retained_at=RETAINED_NOW, seed="now-tie-a",
    )
    filing_a = _filing_row(
        accession=ACCESSION_NOW, report_period=PERIOD_NOW,
        accepted_at=ACCEPTED_NOW, retained_at=RETAINED_NOW, receipt=receipt_a,
    )
    accession_b = "0001792167-26-000005"
    receipt_b = _publish_raw(
        store, accession=accession_b, report_period=PERIOD_NOW,
        accepted_at=ACCEPTED_NOW, retained_at=RETAINED_NOW, seed="now-tie-b",
    )
    filing_b = _filing_row(
        accession=accession_b, report_period=PERIOD_NOW,
        accepted_at=ACCEPTED_NOW, retained_at=RETAINED_NOW, receipt=receipt_b,
    )
    holdings_now = [
        _holding_row(accession=ACCESSION_NOW, sk=1, cusip=CUSIP, ssh_prn_amt="140"),
        _holding_row(accession=accession_b, sk=1, cusip=CUSIP, ssh_prn_amt="140"),
    ]
    _publish_generation(
        store, report_period=PERIOD_NOW, filings=[filing_a, filing_b], holdings=holdings_now,
        source_receipt_ids=[receipt_a.receipt_id, receipt_b.receipt_id],
        published_at=PUBLISHED_NOW, source_cutoff_at=CUTOFF_NOW,
    )

    receipt = run_pilot(store, _request())
    assert receipt["state"] == AMBIGUOUS_FILING_LINEAGE


# --- adversarial review repair: Finding 12 (MINOR) ---------------------------
#
# _manager_denominator used to assert total=included=decoded/missing=0 under
# a genuinely-unknown table_entry_total (an honest shape) AND, separately,
# mislabel an excess-rows condition (decoded > table_entry_total) as
# "partial" with the excess counted as excluded_positions -- rows that were
# in fact successfully decoded, not excluded from anything.


def test_manager_denominator_unknown_total_uses_honest_observed_counts() -> None:
    generation = SimpleNamespace(holdings=[
        {"accession": ACCESSION_NOW}, {"accession": ACCESSION_NOW}, {"accession": OTHER_CUSIP},
    ])
    filing_row = {"accession": ACCESSION_NOW, "table_entry_total": None, "confidential_omitted": None}
    result = _manager_denominator(generation=generation, filing_row=filing_row)
    assert result == {
        "kind": "public_reported_sleeve", "state": "unknown",
        "total_positions": 2, "included_positions": 2,
        "excluded_positions": 0, "missing_positions": 0,
    }


def test_manager_denominator_excess_decoded_rows_is_unknown_never_excluded() -> None:
    generation = SimpleNamespace(holdings=[
        {"accession": ACCESSION_NOW}, {"accession": ACCESSION_NOW}, {"accession": ACCESSION_NOW},
    ])
    filing_row = {"accession": ACCESSION_NOW, "table_entry_total": 1, "confidential_omitted": False}
    result = _manager_denominator(generation=generation, filing_row=filing_row)
    assert result["state"] == "unknown"
    assert result["excluded_positions"] == 0
    assert result["total_positions"] == 3
    assert result["included_positions"] == 3
    assert result["missing_positions"] == 0


def test_manager_denominator_partial_when_decoded_is_a_lawful_subset() -> None:
    generation = SimpleNamespace(holdings=[{"accession": ACCESSION_NOW}])
    filing_row = {"accession": ACCESSION_NOW, "table_entry_total": 2, "confidential_omitted": False}
    result = _manager_denominator(generation=generation, filing_row=filing_row)
    assert result == {
        "kind": "public_reported_sleeve", "state": "partial",
        "total_positions": 2, "included_positions": 1,
        "excluded_positions": 0, "missing_positions": 1,
    }


# ==============================================================================
# K2-C semantic-owner repair (2026-09-03) -- new falsifiers
#
# Commissioned by merged Macro #6710 / DEC-ALPHA-K2C-K3D-CURRENT-DEPENDENCY-
# STATE-2026-08-28. A semantic positive now requires BOTH owner seams
# (security identity AND manager/vehicle epochs) to be proven, atomically,
# through run_pilot(..., owner_semantics=...). See the module docstring in
# lib/institutional_13f_adapter.py for the full repaired law.
# ==============================================================================


def test_sole_discretion_alone_cannot_reach_a_positive(tmp_path: Path) -> None:
    """The exact defect this repair exists to kill: a SOLE 13F row with no
    owner-supplied security/manager/vehicle binding must never yield
    PILOT_COMPILED or MANAGER_RESEARCH_INTENT_ELIGIBLE_CONTEXT.
    """
    store = _build_world(tmp_path)  # default investment_discretion="SOLE"
    receipt = run_pilot(store, _request())

    assert receipt["state"] == OWNER_SEMANTICS_UNRESOLVED_STATE
    assert receipt["state"] != POSITIVE_STATE
    assert receipt["compiled_observation_state"] != "MANAGER_RESEARCH_INTENT_ELIGIBLE_CONTEXT"
    assert receipt["compiled_observation_state"] is None


def test_unresolved_security_binding_kills_the_positive(tmp_path: Path) -> None:
    store = _build_world(tmp_path)
    receipt = run_pilot(store, _request())

    assert receipt["security_binding"]["dataos_security_id"] is None
    assert receipt["state"] != POSITIVE_STATE
    assert receipt["recipe"] is None
    assert receipt["compiled"] is None


def test_cik_is_not_manager_complex_identity(tmp_path: Path) -> None:
    """No mcx_filer_<CIK> / mce_filer_<CIK> / veh_filer_<CIK> / vie_filer_<CIK>
    synthetic resolved identity can support a positive, whether no
    ``owner_semantics`` is supplied at all or a shape-valid one is supplied
    and refused by the empty owner-verifier registry (Sol review 5099850302
    repair -- both are now the SAME receipt family:
    ``OWNER_SEMANTICS_UNRESOLVED_STATE``, differing only in ``reason``).
    """
    store = _build_world(tmp_path)
    unresolved_receipt = run_pilot(store, _request())
    shape_valid_but_unverified_receipt = run_pilot(
        store, _request(), owner_semantics=_structural_owner_semantics()
    )

    for receipt in (unresolved_receipt, shape_valid_but_unverified_receipt):
        assert receipt["state"] == OWNER_SEMANTICS_UNRESOLVED_STATE
        serialized = json.dumps(receipt)
        for forbidden in ("mcx_filer_", "mce_filer_", "veh_filer_", "vie_filer_"):
            assert forbidden not in serialized, f"{forbidden!r} leaked into the receipt"


def test_investment_discretion_never_selects_vehicle_semantics(tmp_path: Path) -> None:
    """SOLE, SHARED, DEFINED, NONE, and None investment_discretion ALL
    produce the same owner-unresolved terminal state -- the field is
    reported honestly but selects nothing. ``_vehicle_decision``, the
    function that used to make that (illegitimate) selection, no longer
    exists on the module at all.

    An empty-string value is EXCLUDED from the constructed-store cases: the
    owner's own catalog write path
    (``engine.institutional_census.catalog._string``, via
    ``prepare_catalog_generation``) refuses an empty string as invalid
    input ("must be a bounded non-empty string") for a nullable field, so a
    real owner-published holdings row can never literally carry
    ``investment_discretion=""`` -- only a genuinely-absent (``None``)
    value or a real non-empty string. That refusal is exercised directly
    below without going through the full owner store/generation pipeline
    (which would otherwise raise before ``run_pilot`` is ever reached),
    proving the same "selects nothing" law without violating the "every
    fixture store is built through the owner's own publish APIs" house rule.
    """
    import lib.institutional_13f_adapter as adapter_module

    assert not hasattr(adapter_module, "_vehicle_decision")

    discretion_values = ["SOLE", "sole ", "SHARED", "DEFINED", "NONE", None]
    for index, discretion in enumerate(discretion_values):
        store = _build_world(tmp_path / f"world_{index}", investment_discretion=discretion)
        receipt = run_pilot(store, _request())
        assert receipt["state"] == OWNER_SEMANTICS_UNRESOLVED_STATE, discretion

    # The empty-string case: since the owner's own store refuses to persist
    # it, prove instead that build_recipe -- the ONE function that used to
    # read investment_discretion to select vehicle semantics -- no longer
    # even accepts an investment_discretion argument of ANY value, empty
    # string included. There is no code path left through which "" (or
    # anything else read from a 13F row) could select vehicle semantics.
    import inspect

    assert "investment_discretion" not in inspect.signature(build_recipe).parameters


def _drop(mapping: dict, key: str) -> dict:
    out = dict(mapping)
    out.pop(key, None)
    return out


_OWNER_SEMANTICS_DEFECTS = [
    pytest.param(lambda os: _drop(os, "provenance"), id="missing_provenance"),
    pytest.param(
        lambda os: {**os, "provenance": {**os["provenance"], "owner": ""}}, id="empty_provenance_owner",
    ),
    pytest.param(lambda os: _drop(os, "security"), id="missing_security"),
    pytest.param(
        lambda os: {**os, "security": {**os["security"], "dataos_security_id": None}},
        id="security_id_none",
    ),
    pytest.param(lambda os: _drop(os, "vehicle_epoch"), id="missing_vehicle_epoch"),
    pytest.param(
        lambda os: {**os, "vehicle_epoch": {**os["vehicle_epoch"], "resolution_state": "unresolved"}},
        id="vehicle_epoch_unresolved",
    ),
    pytest.param(
        lambda os: {
            **os,
            "manager_complex_epoch": {**os["manager_complex_epoch"], "resolution_state": "unresolved"},
        },
        id="manager_complex_epoch_unresolved",
    ),
    pytest.param(lambda _os: "not-a-mapping", id="non_mapping"),
    # --- R1/R2 repair (2026-09-03) new discriminators ------------------------
    pytest.param(
        lambda os: {
            **os,
            "security": {**os["security"], "dataos_resolution": SECURITY_BINDING_UNRESOLVED},
        },
        id="security_unresolved_sentinel",
    ),
    pytest.param(
        lambda os: {**os, "security": {**os["security"], "dataos_security_id": "not-an-identity"}},
        id="security_id_not_owner_grammar",
    ),
    pytest.param(
        lambda os: {**os, "security": {**os["security"], "dataos_security_id": "SEC:"}},
        id="security_id_not_owner_grammar_empty_listing",
    ),
    pytest.param(
        lambda os: {
            **os,
            "security": {**os["security"], "dataos_security_id": "ISS:US-XNAS-STRUCTURALTEST"},
        },
        id="security_id_not_owner_grammar_issuer_not_security",
    ),
    pytest.param(
        lambda os: {
            **os,
            "manager_complex_epoch": _drop(os["manager_complex_epoch"], "manager_complex_id"),
        },
        id="manager_epoch_missing_manager_complex_id",
    ),
    pytest.param(
        lambda os: {**os, "vehicle_epoch": _drop(os["vehicle_epoch"], "vehicle_class")},
        id="vehicle_epoch_missing_vehicle_class",
    ),
    pytest.param(
        lambda os: {
            **os,
            "manager_complex_epoch": {**os["manager_complex_epoch"], "status": "unresolved"},
        },
        id="epoch_status_unresolved_but_resolution_state_resolved",
    ),
]


@pytest.mark.parametrize("mutate", _OWNER_SEMANTICS_DEFECTS)
def test_owner_semantics_partial_or_unprovenanced_is_refused(tmp_path: Path, mutate) -> None:
    """Fail-closed, atomic validation (frozen spec point 3): ANY single
    defect anywhere in owner_semantics makes the WHOLE payload unresolved --
    never partially trusted, and never a recipe.
    """
    store = _build_world(tmp_path)
    owner_semantics = mutate(_structural_owner_semantics())
    receipt = run_pilot(store, _request(), owner_semantics=owner_semantics)

    assert receipt["state"] == OWNER_SEMANTICS_UNRESOLVED_STATE
    assert receipt["recipe"] is None
    assert receipt["compiled"] is None
    assert receipt["owner_semantics"]["security"]["resolved"] is False
    assert receipt["owner_semantics"]["manager_vehicle"]["resolved"] is False
    assert receipt["owner_semantics"]["provenance"] is None


def test_unresolved_security_sentinel_cannot_prove_a_positive(tmp_path: Path) -> None:
    """The blocker this repair exists to kill (adversarial review finding,
    2026-09-03). The prior head's ``_validate_owner_semantics`` checked BOTH
    K2-B epochs for ``resolution_state == "resolved"`` but checked the
    security seam only for non-emptiness -- so
    ``dataos_resolution == SECURITY_BINDING_UNRESOLVED`` (the schema's own
    UNRESOLVED sentinel), paired with a non-empty but otherwise arbitrary
    ``dataos_security_id`` and two fully resolved epochs, was accepted as
    proof of resolution and reached ``state == POSITIVE_STATE``. That is
    verbatim the commission's ``do_not_redo`` clause "Do not call an
    unresolved security binding positive." A well-formed
    ``dataos_security_id`` is supplied here specifically so this test
    isolates the sentinel defect alone -- not a grammar defect.
    """
    store = _build_world(tmp_path)
    owner_semantics = _structural_owner_semantics()
    owner_semantics = {
        **owner_semantics,
        "security": {
            **owner_semantics["security"],
            "dataos_resolution": SECURITY_BINDING_UNRESOLVED,
        },
    }
    receipt = run_pilot(store, _request(), owner_semantics=owner_semantics)

    assert receipt["state"] == OWNER_SEMANTICS_UNRESOLVED_STATE
    assert receipt["state"] != POSITIVE_STATE
    assert receipt["recipe"] is None
    assert receipt["compiled"] is None
    assert receipt["owner_semantics"]["security"]["resolved"] is False


def test_partial_owner_epoch_is_refused_not_raised(tmp_path: Path) -> None:
    """A structurally partial epoch (present, ``resolution_state=="resolved"``,
    but missing a key ``build_recipe`` itself reads) must be refused with the
    typed unresolved receipt -- never a bare ``KeyError`` escaping out of
    ``build_recipe`` through ``run_pilot``. Before R2, the validator checked
    only ``resolution_state``, so this exact payload reached ``build_recipe``
    and raised ``KeyError: 'vehicle_class'``.
    """
    store = _build_world(tmp_path)
    owner_semantics = _structural_owner_semantics()
    partial_vehicle_epoch = _drop(owner_semantics["vehicle_epoch"], "vehicle_class")
    owner_semantics = {**owner_semantics, "vehicle_epoch": partial_vehicle_epoch}

    receipt = run_pilot(store, _request(), owner_semantics=owner_semantics)

    assert receipt["state"] == OWNER_SEMANTICS_UNRESOLVED_STATE
    assert receipt["recipe"] is None
    assert receipt["compiled"] is None
    assert receipt["owner_semantics"]["manager_vehicle"]["resolved"] is False


# ==============================================================================
# K2-C blocker + MAJOR repair (Sol review 5099850302, 2026-09-03) -- new
# hostile regressions. Every payload below is SHAPE-VALID under every check
# _verify_owner_semantics performs (sentinel resolution, SEC: grammar,
# epoch resolution_state, required epoch fields, status/resolution_state
# contradiction) -- proven reproducible bugs on head 339a5c3c39e0, where a
# shape-only validator either wrongly reached POSITIVE_STATE or let an
# uncaught InstitutionalIntelligenceError escape run_pilot from
# validate_recipe() AFTER build_recipe() had already run. None of these
# tests pass because of a NEW bespoke conflict check -- see the module
# docstring "Owner VERIFICATION gate": the empty _CANONICAL_OWNER_VERIFIERS
# registry refuses ALL of them, well-shaped or not, because nothing in this
# repository can verify any payload is TRUE.
# ==============================================================================


def test_parseable_but_wrong_sec_identity_cannot_prove_a_positive(tmp_path: Path) -> None:
    """BLOCKER (finding 1). "SEC:US-XNYS-TOTALLYOTHER" is a syntactically
    well-formed SEC: security identity (a real MIC, an alphanumeric code) --
    it parses cleanly under lib.dataos.identity.parse_id -- but it is NOT
    the binding for the requested CUSIP 037833100 (nothing has ever proven
    that it is). On head 339a5c3c39e0 this was accepted as proof of
    resolution and reached PILOT_COMPILED, because the pre-repair validator
    could only check the id's GRAMMAR, never its TRUTH.
    """
    store = _build_world(tmp_path)
    owner_semantics = _structural_owner_semantics()
    owner_semantics = {
        **owner_semantics,
        "security": {
            "dataos_security_id": "SEC:US-XNYS-TOTALLYOTHER",
            "dataos_resolution": "alias_table_resolved",
        },
        "provenance": {"owner": "caller_fabricated_owner", "reference_id": "caller-fabricated-001"},
    }
    receipt = run_pilot(store, _request(cusip=CUSIP), owner_semantics=owner_semantics)

    assert receipt["state"] == OWNER_SEMANTICS_UNRESOLVED_STATE
    assert receipt["recipe"] is None
    assert receipt["compiled"] is None
    # Every shape check passed (well-formed SEC: id, non-empty provenance,
    # two resolved epochs) -- what refused it is the empty owner-verifier
    # registry, not a lucky shape check. This is the architectural point.
    assert receipt["owner_semantics"]["reason"] == OWNER_VERIFIER_ABSENT
    assert receipt["owner_semantics"]["provenance"] is None


def test_fabricated_provenance_cannot_prove_a_positive(tmp_path: Path) -> None:
    """A well-shaped but entirely made-up provenance -- arbitrary non-empty
    ``owner``/``reference_id`` strings -- is exactly as unprovable as any
    other caller claim: nothing verifies WHO supplied a payload either.
    """
    store = _build_world(tmp_path)
    owner_semantics = _structural_owner_semantics()
    owner_semantics = {
        **owner_semantics,
        "provenance": {"owner": "anyone_can_type_this_string", "reference_id": "made-up-reference-001"},
    }
    receipt = run_pilot(store, _request(), owner_semantics=owner_semantics)

    assert receipt["state"] == OWNER_SEMANTICS_UNRESOLVED_STATE
    assert receipt["recipe"] is None
    assert receipt["compiled"] is None
    assert receipt["owner_semantics"]["reason"] == OWNER_VERIFIER_ABSENT
    assert receipt["owner_semantics"]["provenance"] is None


def test_rich_provenance_is_not_admitted_and_never_echoed(tmp_path: Path) -> None:
    """MAJOR (finding 3). A provenance payload carrying extra fields
    (``owner_clock``, ``evidence_refs``) that LOOK like real K1 evidence
    machinery is still just caller-authored text -- shape validation only
    requires non-empty ``owner``/``reference_id`` strings, so extra fields
    are neither rejected nor required. It must still refuse (nothing
    verifies it), and -- the finding this test exists to kill -- it must
    never be echoed back onto the receipt, extra fields included.
    """
    store = _build_world(tmp_path)
    owner_semantics = _structural_owner_semantics()
    owner_semantics = {
        **owner_semantics,
        "provenance": {
            "owner": "structural_test_fixture",
            "reference_id": "structural-fixture-001",
            "owner_clock": "2026-09-03T00:00:00Z",
            "evidence_refs": ["k1ref_fabricated_001", "k1ref_fabricated_002"],
        },
    }
    receipt = run_pilot(store, _request(), owner_semantics=owner_semantics)

    assert receipt["state"] == OWNER_SEMANTICS_UNRESOLVED_STATE
    assert receipt["recipe"] is None
    assert receipt["compiled"] is None
    assert receipt["owner_semantics"]["provenance"] is None
    serialized = json.dumps(receipt)
    assert "owner_clock" not in serialized
    assert "k1ref_fabricated" not in serialized


_OWNER_SEMANTICS_CONTRADICTIONS = [
    pytest.param(
        lambda os: {**os, "manager_complex_epoch": _drop(os["manager_complex_epoch"], "interval")},
        id="missing_manager_interval",
    ),
    pytest.param(
        lambda os: {
            **os,
            "manager_complex_epoch": {
                **os["manager_complex_epoch"],
                "actor_identity": {
                    **os["manager_complex_epoch"]["actor_identity"],
                    "resolution_state": "unresolved",
                },
            },
        },
        id="actor_epoch_resolution_state_conflict",
    ),
    pytest.param(
        lambda os: {
            **os,
            "manager_complex_epoch": {**os["manager_complex_epoch"], "decision_mode": "discretionary"},
            "vehicle_epoch": {
                **os["vehicle_epoch"], "decision_mode": "discretionary", "vehicle_class": "broad_passive",
            },
        },
        id="vehicle_class_decision_mode_conflict",
    ),
    pytest.param(
        lambda os: {
            **os,
            "vehicle_epoch": {
                **os["vehicle_epoch"],
                "complex_epoch_id": "mce_a_different_epoch_the_manager_never_claimed",
            },
        },
        id="vehicle_complex_link_conflict",
    ),
    pytest.param(
        lambda os: {
            **os,
            "vehicle_epoch": {**os["vehicle_epoch"], "manager_complex_id": "mcx_a_different_manager_identity"},
        },
        id="manager_vehicle_identity_mismatch",
    ),
]


@pytest.mark.parametrize("mutate", _OWNER_SEMANTICS_CONTRADICTIONS)
def test_owner_semantics_contradiction_cannot_prove_a_positive(tmp_path: Path, mutate) -> None:
    """Hostile regressions (Sol review 5099850302, 2026-09-03). Each payload
    here is a real, internally contradictory owner claim that -- on head
    339a5c3c39e0 -- either reached ``POSITIVE_STATE`` outright or escaped
    ``run_pilot`` as an uncaught ``InstitutionalIntelligenceError`` raised
    from ``validate_recipe`` AFTER ``build_recipe`` had already run (proven
    by direct reproduction against that head; see the worker packet
    evidence). The repair does not add a bespoke check for any one of
    these -- see the module docstring: with the owner-verifier registry
    empty by construction, ``build_recipe``/``compile_recipe`` are
    unreachable for ANY payload, contradictory or not, so no
    partial/contradictory epoch can ever reach construction (finding 2),
    and nothing can raise validate_recipe's errors after it.
    """
    store = _build_world(tmp_path)
    owner_semantics = mutate(_structural_owner_semantics())
    receipt = run_pilot(store, _request(), owner_semantics=owner_semantics)

    assert receipt["state"] == OWNER_SEMANTICS_UNRESOLVED_STATE
    assert receipt["recipe"] is None
    assert receipt["compiled"] is None
    assert receipt["owner_semantics"]["reason"] == OWNER_VERIFIER_ABSENT


def test_no_canonical_owner_verifier_is_registered() -> None:
    """S1 (frozen spec): the owner-blocked discriminator. Records the
    current owner-primitive gap -- K2-C has NOT populated this registry,
    and per its own comment, never may: only the owning programs (Data OS /
    Stock Identity for the security axis, Institutional Intelligence / K2-B
    for manager/vehicle) may, in their own waves. This is NOT a production
    positive; it is what keeps the positive path unreachable by
    construction while it stays empty.
    """
    assert adapter_module._CANONICAL_OWNER_VERIFIERS == ()


def test_varying_provenance_no_longer_distinguishes_unresolved_receipts(tmp_path: Path) -> None:
    """SUPERSEDES the pre-repair "R3" law this test used to assert (the
    positive path used to survive a caller's ``provenance.owner``/
    ``reference_id`` onto the receipt, making two receipts proven by two
    DIFFERENT owners byte-DIFFERENT). Sol review 5099850302 (2026-09-03)
    established that echoing ANY caller-authored provenance onto a receipt
    is itself a laundering surface -- see the module docstring "Owner
    VERIFICATION gate" and frozen spec point (S4). With the positive path
    unreachable, provenance is NEVER echoed (S4): two owner_semantics
    payloads that differ ONLY in provenance now refuse for the exact same
    reason (``OWNER_VERIFIER_ABSENT`` -- neither payload's provenance was
    ever inspected past its own shape) and are therefore BYTE-IDENTICAL,
    sharing one ``receipt_id``. This is the intended, honest consequence of
    S4, not a regression: a receipt_id can no longer be used to infer WHO
    claimed to supply an owner binding, because no claim is ever admitted.
    """
    store = _build_world(tmp_path)
    owner_semantics_a = _structural_owner_semantics()
    owner_semantics_b = {
        **owner_semantics_a,
        "provenance": {"owner": "a_different_structural_owner", "reference_id": "structural-fixture-002"},
    }

    receipt_a = run_pilot(store, _request(), owner_semantics=owner_semantics_a)
    receipt_b = run_pilot(store, _request(), owner_semantics=owner_semantics_b)

    assert receipt_a["state"] == OWNER_SEMANTICS_UNRESOLVED_STATE
    assert receipt_b["state"] == OWNER_SEMANTICS_UNRESOLVED_STATE
    assert receipt_a["owner_semantics"]["reason"] == OWNER_VERIFIER_ABSENT
    assert receipt_b["owner_semantics"]["reason"] == OWNER_VERIFIER_ABSENT
    assert receipt_a["owner_semantics"]["provenance"] is None
    assert receipt_b["owner_semantics"]["provenance"] is None
    assert receipt_a["receipt_id"] == receipt_b["receipt_id"]
    assert receipt_a == receipt_b


def test_no_repo_producer_supplies_owner_manager_vehicle_epochs() -> None:
    """OWNER-BLOCKED discriminator (records a repo-fact, NOT a production
    positive). What this actually does (R5b correction, 2026-09-03 -- the
    prior docstring said "Greps the repository", which overclaimed the
    check's real reach): it regex-greps exactly FIVE top-level directories
    (``lib``, ``engine``, ``scripts``, ``collectors``, ``app`` -- not
    ``tests``, ``data``, ``docs``, ``config``, ``contracts``, or the repo
    root) for ONE syntactic form -- a dict-literal key immediately followed
    by ``:`` and a ``[`` on the same match (``"manager_complex_epochs": [``
    or ``"vehicle_epochs": [``, single- or double-quoted). Known blind
    spots this does NOT catch: a list built via ``.append()``/comprehension
    and assigned to the key afterward; the key and value split across
    non-matching whitespace/newlines the regex does not tolerate; a
    producer reached through a helper function or f-string rather than a
    literal dict key; any non-``.py`` file; and any producer outside the
    five searched directories. The only producer this specific check found
    is this adapter's own module -- the exact module this repair now forces
    to require its ONE owner seam (``run_pilot(..., owner_semantics=...)``)
    instead of authoring these epochs itself. That means no current
    canonical institutional/K2-B owner can fill the seam today under THIS
    check's coverage; this is an owner-primitive gap per the commission's
    owner-primitive-blocker contract, NOT evidence a production positive is
    currently reachable, and NOT proof no other producer exists anywhere in
    the repository.
    """
    import inspect

    import lib.institutional_13f_adapter as adapter_module

    root = Path(adapter_module.__file__).resolve().parents[1]
    search_dirs = ["lib", "engine", "scripts", "collectors", "app"]
    pattern = re.compile(r"""["'](manager_complex_epochs|vehicle_epochs)["']\s*:\s*\[""")
    producers: set[str] = set()
    for directory in search_dirs:
        base = root / directory
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if pattern.search(text):
                producers.add(str(path.relative_to(root)))
    assert producers == {"lib/institutional_13f_adapter.py"}

    # The one producer must itself now REQUIRE the missing owner seam rather
    # than self-minting identity -- this is what turns "no producer exists"
    # from a silent gap into a typed, provable refusal.
    signature = inspect.signature(run_pilot)
    assert "owner_semantics" in signature.parameters


def test_authority_stays_false_on_every_path(tmp_path: Path) -> None:
    """(Sol review 5099850302 repair) ``recipe``/``compiled`` are always
    ``None`` now -- the owner-verifier registry is empty by construction --
    so there is no ``recipe["authority"]``/``compiled["authority"]`` left to
    check independently; the top-level ``authority`` envelope is the only
    surface, and it stays all-false whether or not owner_semantics is
    supplied.
    """
    store = _build_world(tmp_path)
    all_false = {
        "can_rank": False, "can_gate": False, "can_size": False,
        "can_originate": False, "can_open_entry": False,
    }
    unresolved_receipt = run_pilot(store, _request())
    assert unresolved_receipt["authority"] == all_false
    assert unresolved_receipt["recipe"] is None
    assert unresolved_receipt["compiled"] is None

    shape_valid_but_unverified_receipt = run_pilot(
        store, _request(), owner_semantics=_structural_owner_semantics()
    )
    assert shape_valid_but_unverified_receipt["authority"] == all_false
    assert shape_valid_but_unverified_receipt["recipe"] is None
    assert shape_valid_but_unverified_receipt["compiled"] is None
