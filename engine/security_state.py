"""``security_state.v1`` — Market OS B1A pure, deterministic per-security compiler.

Scope (Chairman-dispatched B1A commission, 2026-08-24). This module compiles the
public, display-only ``security_state.v1`` contract (schema:
``contracts/market_os/security_state.v1.schema.json``) for exactly one golden
security — Apple Inc. common stock, ``SEC:US-XNAS-AAPL`` — over a plain-dict/
plain-row input surface. It is deliberately **instance-scoped**, not a general
identity resolver: see the ``NO_GENERAL_NAMESPACE_RENDERER`` disclosure below.

ZERO I/O, ZERO WALL-CLOCK. Every input this module reads is injected by the
caller (the producer stage, ``scripts/build_stock_library.py``) as a plain
dict/row/string — no parquet read, no HTTP fetch, no reading the live system
clock. The one narrow exception is loading this module's OWN frozen contract artifacts
(the ``security_state.v1`` JSON Schema for self-validation, and
``lib.evidence_foundation``'s own vocabulary/schema files, which that library
reads internally as part of K1 semantic validation) — that is contract
validation of a versioned, checked-in artifact, not owner/business I/O, and it
is the same pattern every ``lib.evidence_foundation`` caller in this repo
already depends on.

Public entry points:

* :func:`compile_security_state` — the compiler. Never raises for an EXPECTED
  degradation (identity refusal, an unpublished/unfetchable workspace, a
  rights-blocked K1 reference, conflicting K1 observations, ...): every one of
  those is a typed ``coverage_state`` in the output, per the "no null-means-
  neutral" law. It raises :class:`SecurityStateCompilationError` only for a
  genuinely malformed input a producer bug would produce.
* :func:`compile_security_state_failure` — a second pure builder the PRODUCER
  calls from its own exception-containment boundary when
  :func:`compile_security_state` itself raised. Never touches disk; the
  producer is the one that reads a prior ``site/stockdata/AAPL.json`` and
  passes its ``{generated_at, content_sha256}`` in as ``last_good``.

Identity receipt chain (R1-R9) — adjudicated 2026-08-24, re-derived here
exactly, never redesigned. See the docstring on :func:`_run_identity_chain`.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker, SchemaError

from lib.evidence_foundation import (
    ALL_FALSE_AUTHORITY,
    EvidenceFoundationError,
    compile_recipe,
    compute_block_id,
    compute_recipe_id,
    compute_reference_id,
)
from lib.dataos.identity import IdentityError, parse_listing_key
from lib.dataos.identity import security_id as _render_security_id

SCHEMA = "security_state.v1"
VERSION = "1.0.0"
SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "contracts"
    / "market_os"
    / "security_state.v1.schema.json"
)

# ---------------------------------------------------------------------------
# Instance-scoped pinned identity. Per the adjudicated B1A identity chain, this
# proof is scoped to the golden security ONLY (NO_GENERAL_NAMESPACE_RENDERER
# below) — it is not a general company_identity.v1 <-> Data OS bridge.
# ---------------------------------------------------------------------------
PINNED_SECURITY_ID = "SEC:US-XNAS-AAPL"
PINNED_ISSUER_ID = "ISS:US-XNAS-AAPL"
PINNED_LISTING_KEY = "US-XNAS-AAPL"
PINNED_TICKER = "AAPL"
PINNED_CIK = "0000320193"
PINNED_MIC = "XNAS"
PINNED_INCEPTION_CODE = "AAPL"

SECURITY_STATE_TICKERS = (PINNED_TICKER,)

_EVENT_ID_RE = re.compile(r"^evt_cik0000320193_\d{4}(?:q[1-4]|fy)_[a-z0-9]+$")
_WORKSPACE_SCHEMA = "event_workspace.v1"
_STALE_DAYS = 120
_EARNINGS_CADENCE_DAYS = 91  # ~1 fiscal quarter, deterministic calendar arithmetic

_EARNINGS_CONSUMER = {
    "workstream": "WS:MARKET-OS",
    "job": "build security_state.v1 for AAPL",
    "output_contract": "security_state.v1",
}

DISCLOSURES: tuple[str, ...] = (
    "CIK_LEG_UNOWNED_ACCESS: issuer_cik read from declared master artifacts "
    "(identity_seams.yml master.artifacts); SecurityIssuerRow omits the column",
    "NO_GENERAL_NAMESPACE_RENDERER: company_identity.v1 (xnas:AAPL) and Data OS "
    "(SEC:US-XNAS-AAPL) grammars are disjoint; this proof is instance-scoped to "
    "the golden security and refuses ambiguity",
    "ISSUERMASTER_CURRENT_IDENTITY_ONLY: no asof-scoped issuer lineage; proof is "
    "current-identity",
    "ALIAS_EPOCH_VALID_FROM: corroboration alias window start is a placeholder "
    "floor, not evidence",
)

# strongest_unresolved_fact rule v1, step 4 — fixed frozen order + plain-language
# {en, zh} text. Hand-authored, deterministic templates; never an LLM call.
_WARNING_ORDER: tuple[str, ...] = (
    "reaction_not_joined",
    "consensus_unlicensed",
    "collector_filing_unjoinable",
    "wire_record_not_found",
    "slides_absent",
    "questions_count_unstructured",
)
_WARNING_TEXT: dict[str, dict[str, str]] = {
    "reaction_not_joined": {
        "en": "Market reaction data has not been joined to this release yet.",
        "zh": "市场反应数据尚未与此次发布关联。",
    },
    "consensus_unlicensed": {
        "en": "Analyst consensus estimates are not licensed for this security.",
        "zh": "该证券的分析师一致预期数据未获授权。",
    },
    "collector_filing_unjoinable": {
        "en": "The underlying filing could not be joined to this event.",
        "zh": "基础备案文件无法与此事件关联。",
    },
    "wire_record_not_found": {
        "en": "No wire record was found for this release.",
        "zh": "未找到此次发布的通讯稿记录。",
    },
    "slides_absent": {
        "en": "No presentation slides are available for this release.",
        "zh": "此次发布没有可用的演示幻灯片。",
    },
    "questions_count_unstructured": {
        "en": "The Q&A question count could not be structured from the source.",
        "zh": "问答环节的问题数量无法从来源中结构化提取。",
    },
}

_PROPHET_REASON = "no current Prophet US owner output for this security"

_REQUIRED_LEGS: tuple[str, ...] = ("change",)
_OPTIONAL_LEGS: tuple[str, ...] = (
    "opportunity_context", "risk", "catalyst", "personal_impact", "evidence",
)
_NEUTRAL_STATES = frozenset({"AVAILABLE", "NOT_COVERED", "NOT_APPLICABLE"})
_SEVERITY = {
    "CONFLICTED": 6, "CORRECTED": 5, "UNAVAILABLE": 4, "RIGHTS_BLOCKED": 4,
    "STALE": 3, "PARTIAL": 2,
}
_SEVERITY_TO_DOMINANT = {6: "CONFLICTED", 5: "CORRECTED", 4: "UNAVAILABLE", 3: "STALE", 2: "PARTIAL"}

_K1_STATE_TO_COVERAGE = {
    "refused": "UNAVAILABLE",
    "abstained": "CONFLICTED",
    "partial": "PARTIAL",
    "corrected": "CORRECTED",
    "complete": "AVAILABLE",
}


class SecurityStateCompilationError(ValueError):
    """A genuinely malformed compiler input — never an expected degradation.

    Every EXPECTED failure mode (identity refusal, an unpublished/unfetchable
    workspace, a rights-blocked or conflicting K1 reference, an unsupported
    owner schema, ...) is represented as a typed ``coverage_state`` in the
    output, never as an exception. This is reserved for inputs so malformed
    that no typed refusal can be produced — a producer-side bug, not a product
    condition. The producer stage catches this and falls back to
    :func:`compile_security_state_failure`.
    """


# ---------------------------------------------------------------------------
# small shared helpers
# ---------------------------------------------------------------------------

def _null_to_none(value: object) -> object | None:
    """``None`` for ``None`` or a ``float('nan')`` cell; unchanged otherwise.

    Mirrors ``lib.dataos.identity._null_to_none`` — this module is a separate
    reader over the same nullable pandas-sourced columns and needs the same
    NaN-is-not-a-string discipline.
    """
    if value is None:
        return None
    if isinstance(value, float) and value != value:  # noqa: PLR0124 — NaN test
        return None
    return value


def _bilingual(en: str, zh: str) -> dict[str, str]:
    return {"en": en, "zh": zh}


def _leg_receipt(
    check: str, description: str, artifact: str, reader: str,
    values_read: Sequence[tuple[str, object]], result: str, code: str | None,
) -> dict[str, Any]:
    return {
        "check": check,
        "description": description,
        "artifact": artifact,
        "reader": reader,
        "values_read": [{"field": field, "value": _jsonable(value)} for field, value in values_read],
        "result": result,
        "code": code,
    }


def _equality(check: str, left: str, left_value: object, right: str, right_value: object) -> dict[str, Any]:
    left_value = _jsonable(left_value)
    right_value = _jsonable(right_value)
    return {
        "check": check, "left": left, "left_value": left_value,
        "right": right, "right_value": right_value, "equal": left_value == right_value,
    }


def _jsonable(value: object) -> str | int | float | bool | None:
    """Coerce a read value to the closed ``values_read``/``equalities`` union.

    ``values_read``/``left_value``/``right_value`` are schema-typed as
    ``string|number|boolean|null`` — a tuple/list read (e.g. R4's security set)
    is rendered as a stable, sorted, comma-joined string rather than smuggling
    a new JSON type into a closed contract.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (tuple, list, set, frozenset)):
        return ",".join(sorted(str(v) for v in value))
    return str(value)


def _content_sha256(state: Mapping[str, Any]) -> str:
    """Canonical-JSON sha256 over everything except the wall-clock fields.

    Excludes the top-level ``content_sha256`` (obviously — it is the digest
    being computed) and ``generated_at``, plus ``as_of.state_compiled_at``,
    which is defined below as a verbatim mirror of ``generated_at``: without
    also excluding the mirror, two compiles of otherwise-identical inputs at
    two different wall-clock moments would still hash differently, defeating
    the "content_sha256 stability under generated_at change" requirement.
    """
    payload = json.loads(
        json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    )
    payload.pop("content_sha256", None)
    payload.pop("generated_at", None)
    as_of = payload.get("as_of")
    if isinstance(as_of, dict):
        as_of.pop("state_compiled_at", None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return sha256(canonical.encode("utf-8")).hexdigest()


def _self_validate(state: Mapping[str, Any]) -> None:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, SchemaError) as exc:
        raise SecurityStateCompilationError(f"security_state.v1 schema unreadable: {exc}") from exc
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(state), key=lambda e: tuple(str(p) for p in e.absolute_path))
    if errors:
        codes = [
            f"{'.'.join(str(p) for p in e.absolute_path) or '$'}:{e.validator}"
            for e in errors
        ]
        raise SecurityStateCompilationError(
            "security_state.v1 self-validation failed: " + "; ".join(codes)
        )


# ---------------------------------------------------------------------------
# R1-R9 identity receipt chain
# ---------------------------------------------------------------------------

def _run_identity_chain(
    *,
    security_master_row: Mapping[str, Any] | None,
    issuer_master_rows: Sequence[Mapping[str, Any]],
    issuer_security_ids: Sequence[str],
    issuer_migration_matches: Sequence[Mapping[str, Any]],
    security_migration_matches: Sequence[Mapping[str, Any]],
    workspace: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Re-derive the adjudicated owner-backed identity chain (R1-R9), exactly.

    Every check is evaluated (never short-circuited) so the receipt always
    carries all nine legs — this is a receipt chain for audit, not a control-
    flow gate. Any R1-R8 failure blocks identity (``BLOCKED_IDENTITY_BRIDGE``);
    R9 is corroboration only and, on disagreement, types the leg ``DIVERGENT``
    and the whole proof ``PARTIAL`` WITHOUT failing R1-R8 (frozen spec, verbatim).
    """
    legs: list[dict[str, Any]] = []
    equalities: list[dict[str, Any]] = []
    refusals: list[str] = []
    row = security_master_row or {}

    # R1 — security_master row exists, active, not superseded ---------------
    sec_state = _null_to_none(row.get("security_state"))
    superseded_by = _null_to_none(row.get("superseded_by"))
    r1_pass = security_master_row is not None and sec_state is None and superseded_by is None
    legs.append(_leg_receipt(
        "R1", "security_master row exists, security_state/superseded_by both null",
        "data/reference/security_master.parquet",
        "scripts/build_stock_library.py::_read_identity_rows (declared master artifact)",
        [
            ("row_present", security_master_row is not None),
            ("security_state", sec_state), ("superseded_by", superseded_by),
        ],
        "pass" if r1_pass else "fail", None if r1_pass else "SECURITY_SUPERSEDED",
    ))
    if not r1_pass:
        refusals.append("SECURITY_SUPERSEDED")

    # R2 — row names the pinned issuer, RESOLVED -----------------------------
    row_issuer_id = _null_to_none(row.get("issuer_id"))
    row_issuer_state = _null_to_none(row.get("issuer_state"))
    r2_pass = row_issuer_id == PINNED_ISSUER_ID and row_issuer_state == "RESOLVED"
    equalities.append(_equality("R2", "row.issuer_id", row_issuer_id, "expected_issuer_id", PINNED_ISSUER_ID))
    legs.append(_leg_receipt(
        "R2", "security_master.issuer_id names the pinned issuer, issuer_state RESOLVED",
        "data/reference/security_master.parquet",
        "scripts/build_stock_library.py::_read_identity_rows",
        [("issuer_id", row_issuer_id), ("issuer_state", row_issuer_state)],
        "pass" if r2_pass else "fail", None if r2_pass else "IDENTITY_UNRESOLVED",
    ))
    if not r2_pass:
        refusals.append("IDENTITY_UNRESOLVED")

    # R3 — issuer_master carries exactly one active row for the pinned CIK --
    matching = [r for r in issuer_master_rows if _null_to_none(r.get("cik")) == PINNED_CIK]
    r3_row = matching[0] if len(matching) == 1 else None
    r3_status = _null_to_none(r3_row.get("status")) if r3_row else None
    r3_pass = r3_row is not None and r3_status == "active"
    equalities.append(_equality(
        "R3", "issuer_master matching row count", len(matching), "expected_count", 1,
    ))
    legs.append(_leg_receipt(
        "R3", "issuer_master carries exactly one active row for the pinned CIK",
        "data/reference/issuer_master.parquet",
        "scripts/build_stock_library.py::_read_identity_rows",
        [("cik", PINNED_CIK), ("matching_row_count", len(matching)), ("status", r3_status)],
        "pass" if r3_pass else "fail", None if r3_pass else "ISSUER_GROUP_AMBIGUOUS",
    ))
    if not r3_pass:
        refusals.append("ISSUER_GROUP_AMBIGUOUS")

    # R4 — the issuer's current security set is exactly the pinned security -
    security_set = sorted({str(s) for s in issuer_security_ids})
    r4_pass = security_set == [PINNED_SECURITY_ID]
    equalities.append(_equality(
        "R4", "issuer.security_set", security_set, "expected_security_set", [PINNED_SECURITY_ID],
    ))
    legs.append(_leg_receipt(
        "R4", "the pinned issuer's CURRENT security set is exactly {SEC:US-XNAS-AAPL}",
        "data/reference/security_master.parquet",
        "scripts/build_stock_library.py::_read_identity_rows",
        [("security_set", security_set), ("count", len(security_set))],
        "pass" if r4_pass else "fail", None if r4_pass else "ISSUER_GROUP_AMBIGUOUS",
    ))
    if not r4_pass:
        refusals.append("ISSUER_GROUP_AMBIGUOUS")

    # R5 — listing_key round-trips to security_id via lib.dataos.identity ---
    listing_key = _null_to_none(row.get("listing_key"))
    row_security_id = _null_to_none(row.get("security_id"))
    derived_security_id: str | None = None
    if listing_key:
        try:
            derived_security_id = _render_security_id(parse_listing_key(str(listing_key)))
        except IdentityError:
            derived_security_id = None
    r5_pass = bool(listing_key) and derived_security_id is not None and derived_security_id == row_security_id
    equalities.append(_equality(
        "R5", "parse_listing_key(row.listing_key)->security_id", derived_security_id,
        "row.security_id", row_security_id,
    ))
    legs.append(_leg_receipt(
        "R5", "listing_key round-trips to security_id via lib.dataos.identity.parse_listing_key",
        "data/reference/security_master.parquet",
        "lib.dataos.identity.parse_listing_key",
        [("listing_key", listing_key), ("derived_security_id", derived_security_id)],
        "pass" if r5_pass else "fail", None if r5_pass else "LISTING_KEY_INCOHERENT",
    ))
    if not r5_pass:
        refusals.append("LISTING_KEY_INCOHERENT")

    # R6 — zero matching rows in issuer_migrations/security_migrations ------
    r6_pass = not issuer_migration_matches and not security_migration_matches
    legs.append(_leg_receipt(
        "R6", "zero matching rows in issuer_migrations.parquet/security_migrations.parquet",
        "data/reference/issuer_migrations.parquet, data/reference/security_migrations.parquet",
        "scripts/build_stock_library.py::_read_identity_rows",
        [
            ("issuer_migration_matches", len(issuer_migration_matches)),
            ("security_migration_matches", len(security_migration_matches)),
        ],
        "pass" if r6_pass else "fail", None if r6_pass else "IDENTITY_CORRECTED",
    ))
    if not r6_pass:
        refusals.append("IDENTITY_CORRECTED")

    # R7 — workspace parity: event_id / company_id / filing cik -------------
    # Vacuous PASS when no workspace is available this cycle (no current
    # event / an owner fetch failure): R7/R8 cross-check a workspace body
    # AGAINST the master, so with no workspace there is nothing to
    # contradict — that is a content-availability gap the `change`/`catalyst`
    # legs report on their own, never an identity refusal. Only a workspace
    # that IS present and disagrees blocks the bridge.
    ws = workspace or {}
    workspace_available = workspace is not None
    event_id = _null_to_none(ws.get("event_id"))
    issuer_block = ws.get("issuer") if isinstance(ws.get("issuer"), Mapping) else {}
    company_id = _null_to_none(issuer_block.get("company_id"))
    completeness = ws.get("completeness") if isinstance(ws.get("completeness"), Mapping) else {}
    filing = completeness.get("filing") if isinstance(completeness.get("filing"), Mapping) else {}
    filing_key = filing.get("filing_key") if isinstance(filing.get("filing_key"), Mapping) else {}
    filing_cik = _null_to_none(filing_key.get("cik"))
    event_id_ok = bool(event_id) and _EVENT_ID_RE.fullmatch(str(event_id)) is not None
    company_id_ok = company_id == f"cik:{PINNED_CIK}"
    filing_cik_ok = filing_cik == PINNED_CIK
    r7_pass = (not workspace_available) or (event_id_ok and company_id_ok and filing_cik_ok)
    equalities.append(_equality("R7a", "workspace.event_id matches pattern", event_id_ok, "expected", True))
    equalities.append(_equality("R7b", "workspace.issuer.company_id", company_id, "expected_company_id", f"cik:{PINNED_CIK}"))
    equalities.append(_equality("R7c", "workspace.completeness.filing.filing_key.cik", filing_cik, "expected_cik", PINNED_CIK))
    legs.append(_leg_receipt(
        "R7", "workspace parity: event_id/company_id/filing cik all bind to the pinned CIK "
        "(vacuous pass when no workspace is available this cycle)",
        "event_workspace.v1 (owner-native workspace body)",
        "engine.neuralweb.company_intelligence_reader.load_workspace_with_disposition",
        [("workspace_available", workspace_available), ("event_id", event_id), ("company_id", company_id), ("filing_cik", filing_cik)],
        "pass" if r7_pass else "fail", None if r7_pass else "SUBJECT_NATIVE_PARITY_FAILED",
    ))
    if not r7_pass:
        refusals.append("SUBJECT_NATIVE_PARITY_FAILED")

    # R8 — master issuer_cik agrees with the workspace-native CIK -----------
    # Same vacuous-pass rule as R7 when no workspace is available.
    master_cik = _null_to_none(row.get("issuer_cik"))
    r8_pass = (not workspace_available) or (master_cik == PINNED_CIK and filing_cik_ok)
    equalities.append(_equality("R8", "master.issuer_cik", master_cik, "workspace_native_cik", filing_cik))
    legs.append(_leg_receipt(
        "R8", "master issuer_cik agrees with the workspace-native CIK "
        "(vacuous pass when no workspace is available this cycle)",
        "data/reference/security_master.parquet + event_workspace.v1",
        "scripts/build_stock_library.py::_read_identity_rows",
        [("workspace_available", workspace_available), ("master_issuer_cik", master_cik), ("workspace_native_cik", filing_cik)],
        "pass" if r8_pass else "fail", None if r8_pass else "IDENTITY_BRIDGE_DISAGREEMENT",
    ))
    if not r8_pass:
        refusals.append("IDENTITY_BRIDGE_DISAGREEMENT")

    # R9 — corroboration only; never gates R1-R8 -----------------------------
    listings = issuer_block.get("listings") if isinstance(issuer_block.get("listings"), list) else []
    primary = next(
        (item for item in listings if isinstance(item, Mapping) and item.get("is_primary") is True), None,
    )
    corroboration_state = "UNAVAILABLE"
    r9_divergent = False
    if primary is not None:
        alias_mic = _null_to_none(primary.get("mic"))
        alias_ticker = _null_to_none(primary.get("ticker"))
        master_mic = _null_to_none(row.get("mic"))
        master_inception = _null_to_none(row.get("inception_code"))
        agrees = alias_mic == master_mic and alias_ticker == master_inception
        corroboration_state = "AVAILABLE" if agrees else "DIVERGENT"
        r9_divergent = not agrees
        equalities.append(_equality(
            "R9", "workspace primary alias (mic,ticker)", f"{alias_mic}:{alias_ticker}",
            "master (mic,inception_code)", f"{master_mic}:{master_inception}",
        ))
    legs.append(_leg_receipt(
        "R9", "corroboration: workspace primary alias agrees with master (mic, inception_code)",
        "event_workspace.v1 issuer.listings[]",
        "engine.neuralweb.company_intelligence_reader.load_workspace_with_disposition",
        [("corroboration_state", corroboration_state)],
        "pass" if corroboration_state != "DIVERGENT" else "fail",
        None if corroboration_state != "DIVERGENT" else "CORROBORATION_DIVERGENT",
    ))

    if refusals:
        state = "BLOCKED_IDENTITY_BRIDGE"
    elif r9_divergent:
        state = "PARTIAL"
    else:
        state = "PROVEN"

    return {
        "state": state,
        "method": "owner_backed_chain.v1",
        "legs": legs,
        "equalities": equalities,
        "refusals": refusals,
        "disclosures": list(DISCLOSURES),
    }


# ---------------------------------------------------------------------------
# K1 (Evidence Foundation) runtime composition — earnings_change block only
# ---------------------------------------------------------------------------

def _build_k1_recipe(*, max_references: int = 1) -> dict[str, Any]:
    """The cik-native, zero-identity-join recipe proven by adjudication.

    ``max_references`` defaults to 1 (the production shape: one owner-native
    generation per compile). A caller may pass 2 ONLY to build a synthetic,
    test-only conflicting-observations scenario exercising this module's own
    K1-consumption mapping (:func:`_build_evidence_leg`) — K1's own conflict
    DETECTION mechanics are already proven by
    ``tests/test_evidence_foundation_product_contract.py`` and are not
    re-proven here.
    """
    recipe: dict[str, Any] = {
        "schema": "evidence_foundation.recipe.v1",
        "version": "1.0.0",
        "recipe_id": "",
        "recipe_name": "security_state.v1.earnings_change",
        "consumer": dict(_EARNINGS_CONSUMER),
        "subject_instance": {"key_type": "cik", "key": PINNED_CIK},
        "subject_key_types": ["cik"],
        "block_specs": [{
            "order": 1,
            "block_key": "earnings_change",
            "requirement": "required",
            "allowed_owner_stores": ["earnings.workspace_generation"],
            "allowed_object_classes": ["derived_view"],
            "evidence_class": "deterministic",
            "minimum_references": 1,
            "maximum_references": max_references,
            "on_absent": "refuse",
            "output_fields": ["change.event", "change.evidence"],
        }],
        "identity_joins": [],
        "refusal_degradation_rules": [
            {
                "code": "REQUIRED_BLOCK_ABSENT",
                "condition": "a required block has no valid owner-backed EvidenceBlock",
                "effect": "refuse",
            },
            {
                "code": "OPTIONAL_BLOCK_ABSENT",
                "condition": "an optional block has no valid owner-backed EvidenceBlock",
                "effect": "degrade",
            },
            {
                "code": "IDENTITY_UNRESOLVED",
                "condition": "the required subject join is unresolved or ambiguous",
                "effect": "refuse",
            },
            {
                "code": "RIGHTS_BLOCKED",
                "condition": "a required owner reference is rights blocked",
                "effect": "refuse",
            },
            {
                "code": "CONFLICTED_REQUIRED_BLOCK",
                "condition": "a required block retains unresolved conflicting observations",
                "effect": "abstain",
            },
        ],
        "dedup_dependence_rules": {
            "automatic_relation_types": [],
            "nonautomatic_relation_types": [
                "exact_duplicate", "same_fact", "same_event", "corroborates",
                "contradicts", "shares_upstream", "corrects", "supersedes", "projects",
            ],
            "reference_count_implies_independence": False,
        },
        "output_mappings": [
            {"output_field": "change.event", "block_key": "earnings_change", "when_unavailable": "refuse"},
            {"output_field": "change.evidence", "block_key": "earnings_change", "when_unavailable": "refuse"},
        ],
        "integrity": {
            "denominator_receipt_required": True,
            "dominant_degradation_required": True,
            "partial_may_look_complete": False,
            "confidence_requires_receipt": True,
            "correction_recompilation_required": True,
            "owner_payload_copy_allowed": False,
        },
        "authority": dict(ALL_FALSE_AUTHORITY),
    }
    recipe["recipe_id"] = compute_recipe_id(recipe)
    return recipe


def _build_k1_reference(
    *,
    generation_id: str,
    event_id: str,
    manifest_sha256: str | None,
    source_available_at: str | None,
    observed_at: str | None,
    generated_at: str | None,
    rights_blocked: bool = False,
    correction_kind: str = "none",
    predecessor_reference_ids: Sequence[str] = (),
    correction_clock_field: str | None = None,
) -> dict[str, Any]:
    """One ``earnings.workspace_generation`` owner-native EvidenceRef.

    Modeled field-for-field on the committed golden fixture
    ``tests/fixtures/evidence_foundation/earnings_workspace_valid.json`` — same
    owner, same subject/clock/replay shape — with only the identity/digest/
    clock VALUES substituted for the real, injected owner read.
    """
    reference: dict[str, Any] = {
        "schema": "evidence_foundation.reference.v1",
        "version": "1.0.0",
        "reference_id": "",
        "object_class": "derived_view",
        "owner_store": "earnings.workspace_generation",
        "native_identity": {"generation_id": generation_id, "event_id": event_id},
        "native_schema": _WORKSPACE_SCHEMA,
        "native_digest": (
            {"state": "known", "sha256": manifest_sha256}
            if manifest_sha256 else {"state": "unknown", "sha256": None}
        ),
        "coverage_class": "immutable_generation",
        "subject": {"key_type": "cik", "key": PINNED_CIK},
        "secondary_subjects": [],
        "clocks": [
            {
                "class": "knowable", "field": "lifecycle.source_available_at",
                "value_state": "known" if source_available_at else "unknown",
                "value": source_available_at, "grain": "datetime",
            },
            {
                "class": "observed", "field": "lifecycle.observed_at",
                "value_state": "known" if observed_at else "unknown",
                "value": observed_at, "grain": "datetime",
            },
            {
                "class": "belief_or_build", "field": "generated_at",
                "value_state": "known" if generated_at else "unknown",
                "value": generated_at, "grain": "datetime",
            },
        ],
        "provenance": {
            "pointer_only": True,
            "body_embedded": False,
            "owner_reader": "engine.company_intelligence.event_workspace.validate_event_workspace",
            "pointer": (
                f"company_intelligence/event_workspaces/generations/{generation_id}"
                f"/workspaces/{event_id}.json"
            ),
            "owner_reader_kind": "parser",
        },
        "relations": [],
        "missingness": (
            {"state": "absent", "reason": "rights_blocked", "zero_substituted": False}
            if rights_blocked else {"state": "present", "reason": None, "zero_substituted": False}
        ),
        "correction": {
            "kind": correction_kind,
            "predecessor_reference_ids": list(predecessor_reference_ids),
            "clock_field": correction_clock_field,
            "append_only": True,
            "mutates_predecessor": False,
            "chronology_state": (
                "not_applicable" if correction_kind == "none" else "owner_clock_order_not_verified"
            ),
        },
        "replay": {
            "mode": "live",
            "cutoffs": {
                clock_class: {"state": "unknown", "value": None, "grain": "datetime"}
                for clock_class in (
                    "world_valid", "source_published", "knowable", "observed",
                    "system_recorded", "belief_or_build", "review_due",
                )
            },
            "code_revision": None,
            "input_digest": None,
            "vintage_state": "owner_native",
        },
        "authority": dict(ALL_FALSE_AUTHORITY),
        "freshness": {"state": "unknown", "clock_field": None, "policy_id": None},
        "rights": (
            {"state": "rights_blocked", "policy_id": "market_os.k1.rights_default.v1"}
            if rights_blocked else {"state": "permitted", "policy_id": None}
        ),
        "authority_class": "deterministic",
    }
    reference["reference_id"] = compute_reference_id(reference)
    return reference


def _build_k1_block(references: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The ``earnings_change`` EvidenceBlock over 1..N already-built references.

    A hand-derivation of ``lib.evidence_foundation``'s own (private)
    ``_derived_block_facts`` restricted to what this module ever constructs:
    at most one ``contradicts`` relation per reference (the synthetic conflict
    test) and at most a rights-blocked absence (the rights-blocked test) — no
    dependence/correction relations are ever modelled here.
    :func:`lib.evidence_foundation.validate_block` independently re-derives and
    cross-checks every field below, so any mistake here fails loudly rather
    than silently.
    """
    reference_ids = [str(r["reference_id"]) for r in references]
    absent_ids = {r["reference_id"] for r in references if r["missingness"]["state"] == "absent"}
    included_ids = [rid for rid in reference_ids if rid not in absent_ids]
    rights_ids = {r["reference_id"] for r in references if r["rights"]["state"] == "rights_blocked"}
    corrected_ids = {r["reference_id"] for r in references if r["correction"]["kind"] != "none"}
    conflict_ids: set[str] = set()
    for reference in references:
        for relation in reference.get("relations") or ():
            if relation.get("type") == "contradicts" and relation.get("target_reference_id") in reference_ids:
                conflict_ids.add(reference["reference_id"])
                conflict_ids.add(relation["target_reference_id"])

    if rights_ids:
        coverage_state = "rights_blocked"
    elif conflict_ids:
        coverage_state = "conflicted"
    elif corrected_ids:
        coverage_state = "corrected"
    elif absent_ids:
        coverage_state = "unavailable" if not included_ids else "partial"
    else:
        # freshness is always "unknown" for this v1 owner (no policy_id is
        # established anywhere in this repo's K1 vocabulary yet) — matches
        # every committed golden K1 fixture, not a shortcut unique to this leg.
        coverage_state = "unknown"

    supported_state = {
        "complete": "supported", "partial": "partial", "unknown": "partial",
        "unavailable": "unavailable", "rights_blocked": "rights_blocked",
        "stale": "stale", "conflicted": "conflicted", "corrected": "corrected",
    }[coverage_state]

    # "missing" counts every absent reference regardless of reason — it is not
    # exclusive of "rights_blocked"/"stale"/"fallback" (those are independent
    # per-reason tallies over the same absent set), matching
    # lib.evidence_foundation._derived_block_facts exactly.
    missing = len(absent_ids)
    clock_entries = [
        {"reference_id": r["reference_id"], **dict(clock)}
        for r in references for clock in r["clocks"]
    ]

    block: dict[str, Any] = {
        "schema": "evidence_foundation.block.v1",
        "version": "1.0.0",
        "evidence_block_id": "",
        "block_key": "earnings_change",
        "consumer": dict(_EARNINGS_CONSUMER),
        "supported_claim": {
            "kind": "claim",
            "text": "The AAPL company-change leg is backed by owner-native event_workspace.v1 generation(s).",
            "state": supported_state,
        },
        "reference_ids": reference_ids,
        "owner_stores": ["earnings.workspace_generation"],
        "object_classes": ["derived_view"],
        "evidence_class": "deterministic",
        "clock_summary": {"collapsed": False, "entries": clock_entries},
        "coverage": {
            "state": coverage_state,
            "total": len(reference_ids),
            "included": len(included_ids),
            "excluded": len(reference_ids) - len(included_ids),
            "missing": missing,
            "stale": 0,
            "rights_blocked": len(rights_ids),
            "fallback": 0,
            "basis": (
                "all requested owner-reader fixture rows reconcile by native reference "
                "identity; freshness remains owner-policy dependent"
            ),
            "reconciliation_state": "reconciled",
        },
        "uncertainty": {"state": "none", "probability": None, "derivation_ref": None, "calibration_ref": None},
        "dependence": {"state": "independent", "independent_evidence_count": len(included_ids), "groups": []},
        "conflict_correction": {
            "state": "conflicted" if conflict_ids else ("corrected" if corrected_ids else "none"),
            "reference_ids": sorted(conflict_ids | corrected_ids),
        },
        "next_observable": {"state": "unknown", "description": None, "owner_clock_field": None},
        "permitted_consumers": ["security_state.v1"],
        "lineage": {"state": "original", "predecessor_block_ids": [], "invalidated_by_reference_ids": []},
        "authority": dict(ALL_FALSE_AUTHORITY),
    }
    block["evidence_block_id"] = compute_block_id(block)
    return block


def _build_evidence_leg(*, recipe_id: str | None, compilation: Mapping[str, Any] | None) -> dict[str, Any]:
    if compilation is None:
        return {
            "evidence_block_refs": [], "recipe_id": recipe_id, "compilation": None,
            "conflicts": [], "coverage_state": "UNAVAILABLE",
        }
    coverage_state = _K1_STATE_TO_COVERAGE.get(str(compilation.get("state")), "UNAVAILABLE")
    conflicts = list(compilation.get("block_ids") or []) if compilation.get("state") == "abstained" else []
    return {
        "evidence_block_refs": list(compilation.get("block_ids") or []),
        "recipe_id": recipe_id,
        "compilation": dict(compilation),
        "conflicts": conflicts,
        "coverage_state": coverage_state,
    }


# ---------------------------------------------------------------------------
# legs
# ---------------------------------------------------------------------------

def _build_change_leg(
    *,
    workspace: Mapping[str, Any] | None,
    workspace_disposition: str,
    event_id: str | None,
    generation_id: str | None,
    now_date: date,
) -> dict[str, Any]:
    if workspace is None or workspace_disposition != "found":
        reason = "not_published" if workspace_disposition == "not_published" else "fetch_failed"
        if reason == "not_published":
            summary = _bilingual(
                "No current earnings-change event is published for this security yet.",
                "该证券当前尚无已发布的财报变动事件。",
            )
        else:
            summary = _bilingual(
                "Change tracking unavailable this cycle (an owner fetch failure, not an absence).",
                "本轮未能读取变动追踪数据（属于读取失败，并非事件不存在）。",
            )
        return {
            "economic_episode_ref": None, "event_refs": [], "generation_id": None,
            "source_available_at": None, "observed_at": None, "summary": summary,
            "correction_state": "none", "coverage_state": "UNAVAILABLE", "workspace_warnings": [],
        }

    if workspace.get("schema") != _WORKSPACE_SCHEMA:
        return {
            "economic_episode_ref": event_id, "event_refs": [event_id] if event_id else [],
            "generation_id": generation_id, "source_available_at": None, "observed_at": None,
            "summary": _bilingual(
                "Change tracking unavailable: the owner workspace schema is not supported by this reader.",
                "变动追踪不可用：所有者工作区的 schema 不受本读取器支持。",
            ),
            "correction_state": "none", "coverage_state": "UNAVAILABLE", "workspace_warnings": [],
        }

    lifecycle = workspace.get("lifecycle") if isinstance(workspace.get("lifecycle"), Mapping) else {}
    fiscal = workspace.get("fiscal_period") if isinstance(workspace.get("fiscal_period"), Mapping) else {}
    source_available_at = _null_to_none(lifecycle.get("source_available_at"))
    observed_at = _null_to_none(lifecycle.get("observed_at"))
    lifecycle_state = _null_to_none(lifecycle.get("state")) or "unknown"
    correction_state = {"complete": "none", "corrected": "corrected", "superseded": "superseded"}.get(
        str(lifecycle_state), "none",
    )

    calendar_end = _null_to_none(fiscal.get("calendar_end"))
    stale = False
    if calendar_end:
        try:
            end_date = date.fromisoformat(str(calendar_end)[:10])
            stale = (now_date - end_date).days > _STALE_DAYS
        except ValueError:
            stale = False
    coverage_state = "STALE" if stale else "AVAILABLE"

    n_facts = len(workspace.get("facts") or [])
    n_deltas = len(workspace.get("deltas") or [])
    n_guidance = len(workspace.get("guidance") or [])
    quarter = fiscal.get("quarter")
    year = fiscal.get("year")
    period_label = f"Q{quarter} {year}" if quarter and year else "the latest period"
    summary = _bilingual(
        f"{period_label} results workspace is {lifecycle_state}: "
        f"{n_facts} fact(s), {n_deltas} delta(s), {n_guidance} guidance item(s).",
        f"{period_label} 财报工作区状态为 {lifecycle_state}："
        f"{n_facts} 项事实、{n_deltas} 项变动、{n_guidance} 项指引。",
    )
    warnings = [str(w) for w in (workspace.get("warnings") or [])]
    return {
        "economic_episode_ref": event_id,
        "event_refs": [event_id] if event_id else [],
        "generation_id": generation_id,
        "source_available_at": source_available_at,
        "observed_at": observed_at,
        "summary": summary,
        "correction_state": correction_state,
        "coverage_state": coverage_state,
        "workspace_warnings": warnings,
    }


def _build_opportunity_context_leg(*, blob: Mapping[str, Any]) -> dict[str, Any]:
    entry_signal = blob.get("entry_signal")
    null_reason = blob.get("entry_signal_null_reason")
    entry_available = entry_signal is not None
    prophet = {"ref": None, "state": "UNAVAILABLE", "reason": _PROPHET_REASON}
    entry = {
        "state": "AVAILABLE" if entry_available else "UNAVAILABLE",
        "available": entry_available,
        "null_reason": _null_to_none(null_reason) if not entry_available else None,
    }
    market_incorporation = {"ref": None, "state": "NOT_COVERED"}
    dislocation = {"ref": None, "state": "NOT_COVERED"}
    # This leg's own coverage_state tracks its one actionable sub-facet — entry
    # timing — never null-means-neutral (blob.entry_signal_null_reason is always
    # carried when absent). prophet/market_incorporation/dislocation are typed,
    # individually-disclosed sub-nulls (prophet UNAVAILABLE: could exist today
    # and does not; market_incorporation/dislocation NOT_COVERED: not modelled
    # by this build) that do not independently swing the leg's own rollup —
    # "prophet unavailable" is exercised by asserting that fixed sub-field
    # directly, not by an overall-leg severity swing.
    coverage_state = "AVAILABLE" if entry_available else "UNAVAILABLE"
    return {
        "prophet": prophet, "entry": entry,
        "market_incorporation": market_incorporation, "dislocation": dislocation,
        "coverage_state": coverage_state,
    }


def _strongest_unresolved_fact(
    *,
    conflicted_leg_names: Sequence[str],
    change_correction_state: str,
    change_coverage_state: str,
    workspace_warnings: Sequence[str],
) -> dict[str, Any]:
    """strongest_unresolved_fact rule v1 — first match wins, pinned by test."""
    if conflicted_leg_names:
        return {"state": "conflicted_leg", "leg": conflicted_leg_names[0], "code": None, "en": None, "zh": None}
    if change_correction_state in ("corrected", "superseded"):
        return {
            "state": "corrected_source", "leg": "change", "code": change_correction_state,
            "en": None, "zh": None,
        }
    if change_coverage_state in ("UNAVAILABLE", "STALE"):
        return {
            "state": "required_leg_degraded", "leg": "change", "code": change_coverage_state,
            "en": None, "zh": None,
        }
    for code in _WARNING_ORDER:
        if code in workspace_warnings:
            text = _WARNING_TEXT[code]
            return {"state": "workspace_warning", "leg": "change", "code": code, "en": text["en"], "zh": text["zh"]}
    return {"state": "unavailable", "leg": None, "code": None, "en": None, "zh": None}


def _build_risk_leg(
    *,
    blob: Mapping[str, Any],
    change_leg: Mapping[str, Any],
    evidence_leg: Mapping[str, Any],
    opportunity_leg: Mapping[str, Any],
) -> dict[str, Any]:
    conviction = blob.get("conviction") if isinstance(blob.get("conviction"), Mapping) else None
    cautions = [str(c) for c in ((conviction or {}).get("cautions") or [])]
    alerts = blob.get("alerts") if isinstance(blob.get("alerts"), Mapping) else None
    alert_refs: list[str] = []
    if alerts is not None:
        alert_refs = [
            f"alerts_n_recent:{alerts.get('n_recent', 0)}",
            f"alerts_n_total:{alerts.get('n_total', 0)}",
        ]
    risk_refs = [*cautions, *alert_refs]

    failed_gates: list[dict[str, str]] = []
    if not blob.get("entry_signal"):
        failed_gates.append({
            "code": "ENTRY_TIMING_UNAVAILABLE",
            "reason": str(blob.get("entry_signal_null_reason") or "not_assessed"),
        })
    ladder = blob.get("ladder") if isinstance(blob.get("ladder"), Mapping) else {}
    if ladder.get("dir") == "down":
        failed_gates.append({"code": "LADDER_DOWNTREND", "reason": "ladder.dir=down"})

    conflicted_leg_names = [
        name for name, leg in (("evidence", evidence_leg), ("opportunity_context", opportunity_leg))
        if leg.get("coverage_state") == "CONFLICTED"
    ]
    fact = _strongest_unresolved_fact(
        conflicted_leg_names=conflicted_leg_names,
        change_correction_state=str(change_leg["correction_state"]),
        change_coverage_state=str(change_leg["coverage_state"]),
        workspace_warnings=change_leg["workspace_warnings"],
    )
    coverage_state = "AVAILABLE" if (conviction is not None or alerts is not None) else "NOT_COVERED"
    return {
        "risk_refs": risk_refs, "failed_gates": failed_gates,
        "strongest_unresolved_fact": fact, "coverage_state": coverage_state,
    }


def _build_catalyst_leg(*, workspace: Mapping[str, Any] | None, workspace_disposition: str) -> dict[str, Any]:
    if workspace is None or workspace_disposition != "found":
        return {"next_observables": [], "deadlines": [], "coverage_state": "UNAVAILABLE"}
    fiscal = workspace.get("fiscal_period") if isinstance(workspace.get("fiscal_period"), Mapping) else {}
    calendar_end = _null_to_none(fiscal.get("calendar_end"))
    next_date: str | None = None
    if calendar_end:
        try:
            next_date = (date.fromisoformat(str(calendar_end)[:10]) + timedelta(days=_EARNINGS_CADENCE_DAYS)).isoformat()
        except ValueError:
            next_date = None
    if next_date is None:
        return {"next_observables": [], "deadlines": [], "coverage_state": "UNAVAILABLE"}
    observables = [{
        "kind": "expected_earnings",
        "date": next_date,
        "basis": "fiscal_period.calendar_end + ~1 fiscal quarter (91 days), deterministic calendar arithmetic",
    }]
    return {"next_observables": observables, "deadlines": [], "coverage_state": "AVAILABLE"}


def _build_personal_impact_leg() -> dict[str, Any]:
    return {"state": "NO_USER_CONTEXT", "user_exposure_overlay_ref": None, "coverage_state": "NOT_APPLICABLE"}


# ---------------------------------------------------------------------------
# coverage / dominant_degradation aggregation
# ---------------------------------------------------------------------------

def _build_coverage_and_dominant(legs: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Any], str]:
    missing_legs: list[str] = []
    stale_legs: list[str] = []
    rights_blocked_legs: list[str] = []
    conflicted_legs: list[str] = []
    required_available = 0
    optional_available = 0
    worst_severity = 0

    for name in (*_REQUIRED_LEGS, *_OPTIONAL_LEGS):
        state = legs[name]["coverage_state"]
        available = state in _NEUTRAL_STATES
        if name in _REQUIRED_LEGS:
            required_available += int(available)
        else:
            optional_available += int(available)
        if state == "UNAVAILABLE":
            missing_legs.append(name)
        elif state == "STALE":
            stale_legs.append(name)
        elif state == "RIGHTS_BLOCKED":
            rights_blocked_legs.append(name)
        elif state == "CONFLICTED":
            conflicted_legs.append(name)
        worst_severity = max(worst_severity, _SEVERITY.get(state, 0))

    dominant = _SEVERITY_TO_DOMINANT.get(worst_severity, "NONE")
    if worst_severity == 0:
        overall_state = "AVAILABLE"
    elif required_available < len(_REQUIRED_LEGS):
        overall_state = "UNAVAILABLE"
    else:
        overall_state = "PARTIAL"

    coverage = {
        "overall_state": overall_state,
        "required_legs_total": len(_REQUIRED_LEGS),
        "required_legs_available": required_available,
        "optional_legs_total": len(_OPTIONAL_LEGS),
        "optional_legs_available": optional_available,
        "missing_legs": missing_legs, "stale_legs": stale_legs,
        "rights_blocked_legs": rights_blocked_legs, "conflicted_legs": conflicted_legs,
    }
    return coverage, dominant


# ---------------------------------------------------------------------------
# public entry points
# ---------------------------------------------------------------------------

def compile_security_state(
    *,
    now: str,
    security_master_row: Mapping[str, Any] | None,
    workspace: Mapping[str, Any] | None,
    workspace_disposition: str,
    blob: Mapping[str, Any],
    issuer_master_rows: Sequence[Mapping[str, Any]] = (),
    issuer_security_ids: Sequence[str] = (),
    issuer_migration_matches: Sequence[Mapping[str, Any]] = (),
    security_migration_matches: Sequence[Mapping[str, Any]] = (),
    manifest_sha256: str | None = None,
) -> dict[str, Any]:
    """Compile ``security_state.v1`` for the pinned golden security (AAPL).

    Every argument is a plain dict/row/string the caller already read (or
    fabricated for a test) — this function performs no I/O and reads no wall
    clock; ``now`` is the injected "as of" instant. See the module docstring
    for the ZERO I/O boundary and :func:`_run_identity_chain` for R1-R9.
    """
    if not isinstance(blob, Mapping):
        raise SecurityStateCompilationError("blob must be a mapping")
    if workspace_disposition not in ("found", "not_published", "fetch_failed"):
        raise SecurityStateCompilationError(f"unknown workspace_disposition: {workspace_disposition!r}")
    try:
        now_dt = datetime.fromisoformat(str(now).replace("Z", "+00:00"))
    except ValueError as exc:
        raise SecurityStateCompilationError(f"now is not a valid ISO-8601 datetime: {now!r}") from exc

    identity_workspace = workspace if workspace_disposition == "found" else None
    identity_proof = _run_identity_chain(
        security_master_row=security_master_row,
        issuer_master_rows=issuer_master_rows,
        issuer_security_ids=issuer_security_ids,
        issuer_migration_matches=issuer_migration_matches,
        security_migration_matches=security_migration_matches,
        workspace=identity_workspace,
    )
    identity_blocked = identity_proof["state"] == "BLOCKED_IDENTITY_BRIDGE"

    event_id = generation_id = None
    if workspace_disposition == "found" and isinstance(workspace, Mapping):
        event_id = _null_to_none(workspace.get("event_id"))
        generation_id = _null_to_none(workspace.get("generation_id"))

    # Nothing downstream of an unproven identity may cite the workspace as
    # THIS security's evidence — "required change leg refuses" (frozen spec).
    effective_workspace = None if identity_blocked else workspace
    effective_disposition = "not_published" if identity_blocked else workspace_disposition

    change_leg = _build_change_leg(
        workspace=effective_workspace, workspace_disposition=effective_disposition,
        event_id=event_id, generation_id=generation_id, now_date=now_dt.date(),
    )
    if identity_blocked:
        change_leg = {
            **change_leg,
            "summary": _bilingual(
                "Change tracking refused: the security identity bridge could not be proven this cycle.",
                "变动追踪被拒绝：本轮无法证明证券身份链。",
            ),
        }

    if identity_blocked or effective_workspace is None or event_id is None or generation_id is None:
        recipe = _build_k1_recipe()
        compilation = compile_recipe(recipe, blocks=[], references={})
        evidence_leg = _build_evidence_leg(recipe_id=recipe["recipe_id"], compilation=compilation)
    else:
        lifecycle = effective_workspace.get("lifecycle") if isinstance(effective_workspace.get("lifecycle"), Mapping) else {}
        reference = _build_k1_reference(
            generation_id=str(generation_id), event_id=str(event_id),
            manifest_sha256=manifest_sha256,
            source_available_at=_null_to_none(lifecycle.get("source_available_at")),
            observed_at=_null_to_none(lifecycle.get("observed_at")),
            generated_at=_null_to_none(effective_workspace.get("generated_at")),
        )
        block = _build_k1_block([reference])
        recipe = _build_k1_recipe()
        try:
            compilation = compile_recipe(recipe, blocks=[block], references={reference["reference_id"]: reference})
        except EvidenceFoundationError as exc:
            raise SecurityStateCompilationError(f"K1 compilation failed: {exc}") from exc
        evidence_leg = _build_evidence_leg(recipe_id=recipe["recipe_id"], compilation=compilation)

    opportunity_leg = _build_opportunity_context_leg(blob=blob)
    catalyst_leg = _build_catalyst_leg(workspace=effective_workspace, workspace_disposition=effective_disposition)
    personal_impact_leg = _build_personal_impact_leg()
    risk_leg = _build_risk_leg(
        blob=blob, change_leg=change_leg, evidence_leg=evidence_leg, opportunity_leg=opportunity_leg,
    )

    legs = {
        "change": change_leg, "opportunity_context": opportunity_leg, "risk": risk_leg,
        "catalyst": catalyst_leg, "personal_impact": personal_impact_leg, "evidence": evidence_leg,
    }
    coverage, dominant = _build_coverage_and_dominant(legs)
    if identity_blocked:
        # Frozen spec, verbatim: any R1-R8 refusal forces dominant_degradation
        # UNAVAILABLE regardless of what the per-leg aggregation would say.
        dominant = "UNAVAILABLE"
        coverage = {**coverage, "overall_state": "UNAVAILABLE"}

    state: dict[str, Any] = {
        "schema": SCHEMA, "version": VERSION,
        "security_id": PINNED_SECURITY_ID, "issuer_id": PINNED_ISSUER_ID,
        "listing_key": PINNED_LISTING_KEY, "ticker_display": PINNED_TICKER,
        "generated_at": now, "content_sha256": "0" * 64,
        "as_of": {
            "market_at": _null_to_none(blob.get("asof")),
            "source_frontier_at": change_leg["source_available_at"],
            "state_compiled_at": now,
        },
        "authority": {
            "class": "context_only", "display_only": True, "can_rank": False,
            "can_gate": False, "can_size": False, "can_originate_signal": False, "can_execute": False,
        },
        "identity_proof": identity_proof,
        "coverage": coverage,
        "dominant_degradation": dominant,
        "legs": legs,
        "last_good": None,
    }
    state["content_sha256"] = _content_sha256(state)
    _self_validate(state)
    return state


def compile_security_state_failure(
    *, now: str, reason: str, last_good: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Pure fallback shell for the PRODUCER's own exception-containment boundary.

    Called by ``scripts/build_stock_library.py`` — never by
    :func:`compile_security_state` itself — when compilation raised.  Every leg
    is typed UNAVAILABLE/blocked; ``last_good`` threads through the compact
    ``{generated_at, content_sha256, reason}`` receipt of a prior-good snapshot
    the producer already had on disk (or stays null when there is none) so a
    compiler failure can never silently present as ``dominant_degradation:
    NONE`` (a mutation-kill this module is built to resist).
    """
    blocked_summary = _bilingual(
        "This security's state could not be compiled this cycle (a compiler failure, not an absence).",
        "本次未能编译该证券的状态（属于编译失败，并非事件不存在）。",
    )
    identity_proof = {
        "state": "BLOCKED_IDENTITY_BRIDGE", "method": "owner_backed_chain.v1",
        "legs": [], "equalities": [], "refusals": ["COMPILER_FAILURE"],
        "disclosures": list(DISCLOSURES),
    }
    change_leg = {
        "economic_episode_ref": None, "event_refs": [], "generation_id": None,
        "source_available_at": None, "observed_at": None, "summary": blocked_summary,
        "correction_state": "none", "coverage_state": "UNAVAILABLE", "workspace_warnings": [],
    }
    opportunity_leg = {
        "prophet": {"ref": None, "state": "UNAVAILABLE", "reason": _PROPHET_REASON},
        "entry": {"state": "UNAVAILABLE", "available": False, "null_reason": reason},
        "market_incorporation": {"ref": None, "state": "NOT_COVERED"},
        "dislocation": {"ref": None, "state": "NOT_COVERED"},
        "coverage_state": "UNAVAILABLE",
    }
    risk_leg = {
        "risk_refs": [], "failed_gates": [{"code": "COMPILER_FAILURE", "reason": reason}],
        "strongest_unresolved_fact": {"state": "unavailable", "leg": None, "code": None, "en": None, "zh": None},
        "coverage_state": "UNAVAILABLE",
    }
    catalyst_leg = {"next_observables": [], "deadlines": [], "coverage_state": "UNAVAILABLE"}
    personal_impact_leg = _build_personal_impact_leg()
    evidence_leg = {
        "evidence_block_refs": [], "recipe_id": None, "compilation": None,
        "conflicts": [], "coverage_state": "UNAVAILABLE",
    }
    legs = {
        "change": change_leg, "opportunity_context": opportunity_leg, "risk": risk_leg,
        "catalyst": catalyst_leg, "personal_impact": personal_impact_leg, "evidence": evidence_leg,
    }
    coverage = {
        "overall_state": "UNAVAILABLE",
        "required_legs_total": len(_REQUIRED_LEGS), "required_legs_available": 0,
        "optional_legs_total": len(_OPTIONAL_LEGS), "optional_legs_available": 0,
        "missing_legs": [*_REQUIRED_LEGS, *_OPTIONAL_LEGS],
        "stale_legs": [], "rights_blocked_legs": [], "conflicted_legs": [],
    }
    state: dict[str, Any] = {
        "schema": SCHEMA, "version": VERSION,
        "security_id": PINNED_SECURITY_ID, "issuer_id": PINNED_ISSUER_ID,
        "listing_key": PINNED_LISTING_KEY, "ticker_display": PINNED_TICKER,
        "generated_at": now, "content_sha256": "0" * 64,
        "as_of": {"market_at": None, "source_frontier_at": None, "state_compiled_at": now},
        "authority": {
            "class": "context_only", "display_only": True, "can_rank": False,
            "can_gate": False, "can_size": False, "can_originate_signal": False, "can_execute": False,
        },
        "identity_proof": identity_proof,
        "coverage": coverage,
        "dominant_degradation": "COMPILER_FAILURE",
        "legs": legs,
        "last_good": (
            {
                "generated_at": str(last_good["generated_at"]),
                "content_sha256": str(last_good["content_sha256"]),
                "reason": str(last_good.get("reason") or reason),
            } if last_good else None
        ),
    }
    state["content_sha256"] = _content_sha256(state)
    _self_validate(state)
    return state
