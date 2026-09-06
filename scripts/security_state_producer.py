"""Owner I/O and orchestration for the ``security_state.v1`` producer.

The pure compiler and its business rules remain in ``engine.security_state``.
This module only acquires canonical owner inputs, contains dependency failures,
and invokes that compiler with caller-injected roots, dates, clocks, validators,
subjects, records, and prior state.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import pandas as pd


log = logging.getLogger("stock_library")


def _read_security_state_identity_rows(
    data_dir: Path,
    tickers: tuple[str, ...],
    *,
    decision_date: date,
) -> tuple[dict[str, dict], dict[str, str]]:
    """Compose subject-bound compiler inputs from the canonical identity owners.

    Each declared artifact is loaded exactly once for the whole allowlist. A
    ticker is resolved through ``VendorAliasTable`` at one injected decision
    date; its issuer and CIK are then read through ``IssuerMaster``. The raw
    rows are retained only as compiler proof inputs — they never allocate or
    infer an identity independently of those owner APIs.
    """
    from engine.security_state import SecurityStateCompilationError, SecurityStateSubject
    from lib.dataos.identity import IdentityError, IssuerMaster, VendorAliasTable

    ref = data_dir / "reference"
    security_master = pd.read_parquet(ref / "security_master.parquet")
    vendor_aliases = pd.read_parquet(ref / "vendor_aliases.parquet")
    issuer_master = pd.read_parquet(ref / "issuer_master.parquet")
    issuer_migrations = pd.read_parquet(ref / "issuer_migrations.parquet")
    security_migrations = pd.read_parquet(ref / "security_migrations.parquet")

    security_records = security_master.to_dict("records")
    alias_owner = VendorAliasTable.from_records(vendor_aliases.to_dict("records"))
    issuer_owner = IssuerMaster.from_records(security_records)
    security_rows: dict[str, dict] = {}
    for row in security_records:
        security_id = str(row.get("security_id") or "")
        if not security_id:
            continue
        if security_id in security_rows:
            raise SecurityStateCompilationError(
                f"duplicate security master row for {security_id!r}"
            )
        security_rows[security_id] = row

    issuer_master_rows = issuer_master.to_dict("records")
    issuer_migration_rows = issuer_migrations.to_dict("records")
    security_migration_rows = security_migrations.to_dict("records")
    inputs: dict[str, dict] = {}
    failures: dict[str, str] = {}
    for ticker in tickers:
        try:
            if not isinstance(ticker, str) or not ticker or ticker != ticker.upper():
                raise SecurityStateCompilationError(
                    f"security_state ticker must be a non-empty uppercase string, got {ticker!r}"
                )
            security_id = alias_owner.resolve("store", ticker, decision_date)
            if security_id is None:
                raise SecurityStateCompilationError(
                    f"VendorAliasTable has no current store binding for {ticker} on {decision_date}"
                )
            reverse_ticker = alias_owner.vendor_symbol_for("store", security_id, decision_date)
            if reverse_ticker != ticker:
                raise SecurityStateCompilationError(
                    f"VendorAliasTable round-trip mismatch for {ticker}: {reverse_ticker!r}"
                )

            security_master_row = security_rows.get(security_id)
            if security_master_row is None:
                raise SecurityStateCompilationError(
                    f"security master has no row for owner-resolved {security_id}"
                )
            issuer_id = issuer_owner.issuer_of_security(security_id)
            issuer_cik = issuer_owner.cik_of_issuer(issuer_id) if issuer_id else None
            issuer_security_ids = issuer_owner.securities_of_issuer(issuer_id) if issuer_id else ()
            listing_key = security_master_row.get("listing_key")
            if not issuer_id or not issuer_cik or not isinstance(listing_key, str) or not listing_key:
                raise SecurityStateCompilationError(
                    f"owner identity is incomplete for {ticker}: "
                    f"issuer_id={issuer_id!r}, issuer_cik={issuer_cik!r}, listing_key={listing_key!r}"
                )

            subject = SecurityStateSubject(
                security_id=security_id,
                issuer_id=issuer_id,
                listing_key=listing_key,
                ticker_display=ticker,
                issuer_cik=issuer_cik,
                owner_evidence=(
                    ("decision_date", decision_date.isoformat()),
                    ("alias_reader", "VendorAliasTable.resolve(store)"),
                    ("issuer_reader", "IssuerMaster.issuer_of_security"),
                    ("cik_reader", "IssuerMaster.cik_of_issuer"),
                ),
            )
            inputs[ticker] = {
                "subject": subject,
                "security_master_row": security_master_row,
                "issuer_master_rows": issuer_master_rows,
                "issuer_security_ids": issuer_security_ids,
                "issuer_migration_matches": [
                    row for row in issuer_migration_rows if row.get("security_id") == security_id
                ],
                "security_migration_matches": [
                    row for row in security_migration_rows if row.get("security_id") == security_id
                ],
            }
        except (IdentityError, SecurityStateCompilationError) as exc:
            # Subject-specific owner refusal is isolated. The shared artifacts
            # and owner indexes were already constructed above; failures there
            # remain batch-fatal because no target can be trusted.
            failures[ticker] = str(exc)
    return inputs, failures


def _select_security_state_targets(to_write: list[tuple[str, dict]]) -> list[tuple[str, dict]]:
    """Return only the frozen allowlist, preserving the producer's row order."""
    from engine.security_state import SECURITY_STATE_TICKERS

    return [
        (ticker, rec)
        for ticker, rec in to_write
        if ticker == rec.get("ticker") and ticker in SECURITY_STATE_TICKERS
    ]


def _mismatched_security_state_targets(to_write: list[tuple[str, dict]]) -> list[tuple[str, dict]]:
    """Allow-listed tickers whose record's own ``ticker`` disagrees with the
    write-loop key (MINOR 3 review finding).

    ``_select_security_state_targets`` silently drops these from its
    returned list, which — per this stage's own M1 rationale — leaves the
    record's ``security_state`` key fully absent: that reads downstream as
    "nothing built" rather than "build failed", exactly the hazard M1 was
    written to close for the owner-identity-read-failure path. This is a
    companion selector, never called in the ordinary case (a producer-side
    bug, not an expected condition): the caller emits a typed failure shell
    for every ticker this returns instead of dropping it silently.
    """
    from engine.security_state import SECURITY_STATE_TICKERS

    return [
        (ticker, rec)
        for ticker, rec in to_write
        if ticker in SECURITY_STATE_TICKERS and ticker != rec.get("ticker")
    ]


def _fallback_subject_for_ticker(ticker: str):
    """The frozen pinned subject to use as a failure shell's subject when
    the owner-identity batch itself could not be read (M1). Only the two
    allow-listed tickers ever reach this path (``_select_security_state_targets``
    filters upstream); an unexpected ticker is a programmer error.
    """
    from engine import security_state as ss

    if ticker == ss.PINNED_TICKER:
        return ss.AAPL_SUBJECT
    if ticker == "MSFT":
        return ss.MSFT_SUBJECT
    raise ss.SecurityStateCompilationError(
        f"no pinned fallback subject for ticker {ticker!r}"
    )


def _load_security_state_validator(schema_path: Path):
    """Read and validate the canonical contract exactly once per producer run."""
    from engine import security_state as ss

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        return ss.build_security_state_validator(schema)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ss.SecurityStateCompilationError) as exc:
        raise ss.SecurityStateCompilationError(
            f"security_state.v1 schema unreadable or invalid: {type(exc).__name__}"
        ) from exc


def _compile_security_state_failure_for_exception(
    *, subject, now: str, diagnostic: Exception, validator, prior_state: dict | None,
) -> dict:
    """Keep private diagnostics out of the public failure object and its hash."""
    from engine import security_state as ss

    # The caller logs ``diagnostic`` at the private operator boundary. Only a
    # fixed typed class crosses into the public compiler.
    del diagnostic
    return ss.compile_security_state_failure(
        subject=subject, validator=validator, now=now,
        prior_state=prior_state,
    )


def _prepare_security_state_k1_bundle(
    *, subject, workspace: dict | None, disposition: str, manifest_sha256: str | None,
) -> dict:
    """Run Evidence Foundation validation at the producer I/O boundary.

    The security-state compiler receives only the resulting in-memory receipt
    and independently re-derives its subject-bearing IDs. This keeps schema
    file acquisition out of the pure compiler without duplicating K1 logic.
    """
    from engine import security_state as ss
    from lib.evidence_foundation import compile_recipe

    recipe = ss._build_k1_recipe(subject=subject)
    empty = compile_recipe(recipe, blocks=[], references={})
    found = None
    if disposition == "found" and isinstance(workspace, dict):
        event_id = workspace.get("event_id")
        generation_id = workspace.get("generation_id")
        if event_id and generation_id:
            lifecycle = workspace.get("lifecycle") if isinstance(workspace.get("lifecycle"), dict) else {}
            reference = ss._build_k1_reference(
                subject=subject,
                generation_id=str(generation_id), event_id=str(event_id),
                manifest_sha256=manifest_sha256,
                source_available_at=lifecycle.get("source_available_at"),
                observed_at=lifecycle.get("observed_at"),
                generated_at=workspace.get("generated_at"),
            )
            block = ss._build_k1_block([reference], subject=subject)
            compilation = compile_recipe(
                recipe, blocks=[block], references={reference["reference_id"]: reference},
            )
            found = {
                "reference_id": reference["reference_id"],
                "block_id": block["evidence_block_id"],
                "compilation": compilation,
            }
    return {
        "subject_cik": subject.issuer_cik,
        "recipe_id": recipe["recipe_id"],
        "empty_compilation": empty,
        "found": found,
    }


def _compile_security_state_for_ticker(
    ticker: str,
    rec: dict,
    *,
    now: str,
    identity: dict,
    validator,
    find_event_id,
    load_workspace,
    fetch_manifest,
) -> dict:
    """Compile one security's state after bounded owner/dependency reads.

    Budget: exactly one extra R2 fetch beyond
    ``load_workspace_with_disposition`` (the generation manifest, for the K1
    ``native_digest``). A failed manifest read only degrades that digest to
    ``unknown``; it is never fatal to the change leg.
    """
    from engine import security_state as ss
    subject = identity.get("subject")
    if not isinstance(subject, ss.SecurityStateSubject) or subject.ticker_display != ticker:
        raise ss.SecurityStateCompilationError(
            f"owner-composed subject does not match requested ticker {ticker!r}"
        )
    workspace, disposition, manifest_sha256 = None, "not_published", None
    try:
        event_id = find_event_id(f"cik:{subject.issuer_cik}")
    except Exception as discovery_exc:  # noqa: BLE001 — discovery failure is not clean absence
        log.debug("security_state.v1 event discovery failed for %s (%s)", ticker, discovery_exc)
        event_id = None
        disposition = "fetch_failed"
    if event_id:
        workspace, disposition = load_workspace(event_id)
        generation_id = str((workspace or {}).get("generation_id") or "")
        if workspace is not None and disposition == "found" and generation_id:
            try:
                manifest = fetch_manifest(generation_id)
                entry = (manifest.get("files") or {}).get(f"workspaces/{event_id}.json")
                if isinstance(entry, dict):
                    manifest_sha256 = entry.get("sha256")
            except Exception as manifest_exc:  # noqa: BLE001 — digest degrades to unknown, never fatal
                log.debug("security_state.v1 manifest fetch failed for %s (%s)", ticker, manifest_exc)
    k1_bundle = _prepare_security_state_k1_bundle(
        subject=subject, workspace=workspace, disposition=disposition,
        manifest_sha256=manifest_sha256,
    )
    return ss.compile_security_state(
        validator=validator, now=now, workspace=workspace, workspace_disposition=disposition,
        blob=rec, manifest_sha256=manifest_sha256, k1_bundle=k1_bundle, **identity,
    )


def _read_prior_security_state(outdir: Path, ticker: str) -> dict | None:
    """Read the previous cycle's full committed ``security_state.v1``.

    The caller passes this unreduced state directly to
    ``compile_security_state_failure``. Eligibility and compact last-good
    derivation remain pure business logic owned by ``engine.security_state``.
    """
    path = outdir / f"{ticker}.json"
    if not path.exists():
        return None
    try:
        prior_state = json.loads(path.read_text()).get("security_state")
        return prior_state if isinstance(prior_state, dict) else None
    except Exception:  # noqa: BLE001 — no usable prior is not fatal
        return None
