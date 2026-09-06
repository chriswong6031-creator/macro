"""``security_state.v1`` — Market OS B1A pure, deterministic per-security compiler.

Scope (Chairman-dispatched B1A commission, 2026-08-24; refusal-first second
subject added 2026-09-04). This module compiles the public, display-only
``security_state.v1`` contract (schema:
``contracts/market_os/security_state.v1.schema.json``) for the producer's
frozen AAPL/MSFT allowlist over a plain-dict/plain-row input surface. It is
deliberately **subject-scoped**, not a general identity resolver: a caller must
provide an immutable subject composed through the existing identity owners.

ZERO I/O, ZERO WALL-CLOCK. Every input this module reads is injected by the
caller (the producer stage, ``scripts/build_stock_library.py``) as a plain
dict/row/string — no parquet read, no HTTP fetch, no reading the live system
clock and no contract-file read. The producer loads the canonical
``security_state.v1`` schema once, prepares the Evidence Foundation K1 receipt
at its I/O boundary, and injects both in memory. The compiler independently
checks every subject-bearing K1 identity before using that receipt.

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
  producer is the one that reads the subject's prior
  ``site/stockdata/<ticker>.json`` and passes that full prior state for
  subject-bound ``last_good`` derivation.

Identity receipt chain (R1-R9) — adjudicated 2026-08-24, re-derived here
exactly, never redesigned. See the docstring on :func:`_run_identity_chain`.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker, SchemaError

from lib.evidence_foundation import (
    ALL_FALSE_AUTHORITY,
    compute_block_id,
    compute_recipe_id,
    compute_reference_id,
)
from lib.dataos.identity import IdentityError, parse_listing_key
from lib.dataos.identity import security_id as _render_security_id
from engine.company_intelligence.contracts import ContractError
from engine.company_intelligence.events import parse_canonical_event_id

SCHEMA = "security_state.v1"
VERSION = "1.0.0"
SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "contracts"
    / "market_os"
    / "security_state.v1.schema.json"
)

# ---------------------------------------------------------------------------
# AAPL remains the K1 semantic/ID stability control, while the producer now
# composes the subject for every enabled ticker from the existing Data OS owners.
# ---------------------------------------------------------------------------
PINNED_SECURITY_ID = "SEC:US-XNAS-AAPL"
PINNED_ISSUER_ID = "ISS:US-XNAS-AAPL"
PINNED_LISTING_KEY = "US-XNAS-AAPL"
PINNED_TICKER = "AAPL"
PINNED_CIK = "0000320193"
PINNED_MIC = "XNAS"
PINNED_INCEPTION_CODE = "AAPL"

SECURITY_STATE_TICKERS = (PINNED_TICKER, "MSFT")


@dataclass(frozen=True, slots=True)
class SecurityStateSubject:
    """One immutable security identity composed by the producer's owner reads.

    This is a value carrier, never a resolver.  The producer obtains every
    identifier through ``VendorAliasTable``/``IssuerMaster`` on one injected
    decision date; the pure compiler re-proves those values against its
    injected receipt rows and refuses disagreement.
    """

    security_id: str
    issuer_id: str
    listing_key: str
    ticker_display: str
    issuer_cik: str
    owner_evidence: tuple[tuple[str, str], ...]


# Explicit "no owner reader ran this cycle" evidence for the two frozen
# fallback subjects below (B2 / META-CEO ruling 2026-09-06). These subjects
# are selected ONLY when the owner-identity batch itself could not be read
# (``scripts/build_stock_library.py`` -- ``_ss_identity is None``), so their
# ``owner_evidence`` must never claim a reader executed or a decision date
# was used: no reader class/method name, no ISO date, no the-literal-word
# "fixture" presented as if it had been read. ``_require_subject`` still
# requires the four canonical keys to be present and non-empty strings, so
# the keys stay the same and only the VALUES become an explicit UNREAD
# marker. :func:`_owner_identity_unread` detects this marker so
# :func:`compile_security_state_failure` never lets a fallback subject's R8
# leg present a fabricated owner-backed PASS.
_OWNER_IDENTITY_UNREAD = "UNREAD: owner identity batch failed this cycle"

_UNREAD_OWNER_EVIDENCE: tuple[tuple[str, str], ...] = (
    ("decision_date", "unavailable"),
    ("alias_reader", _OWNER_IDENTITY_UNREAD),
    ("issuer_reader", _OWNER_IDENTITY_UNREAD),
    ("cik_reader", _OWNER_IDENTITY_UNREAD),
)


def _owner_identity_unread(owner_evidence: tuple[tuple[str, str], ...]) -> bool:
    """True when ``owner_evidence`` is the explicit UNREAD marker above.

    A real owner-composed subject
    (``scripts/security_state_producer.py::_read_security_state_identity_rows``)
    always stamps a real ISO ``decision_date`` and the real reader names, so
    it can never collide with this marker.
    """
    return dict(owner_evidence).get("alias_reader") == _OWNER_IDENTITY_UNREAD


AAPL_SUBJECT = SecurityStateSubject(
    security_id=PINNED_SECURITY_ID,
    issuer_id=PINNED_ISSUER_ID,
    listing_key=PINNED_LISTING_KEY,
    ticker_display=PINNED_TICKER,
    issuer_cik=PINNED_CIK,
    owner_evidence=_UNREAD_OWNER_EVIDENCE,
)

# MSFT mirror of the pinned AAPL fixture above, used ONLY as the subject for
# a typed failure shell when the owner-identity batch itself could not be
# read (M1 fix) — never as a substitute for a real owner-composed identity.
MSFT_SECURITY_ID = "SEC:US-XNAS-MSFT"
MSFT_ISSUER_ID = "ISS:US-XNAS-MSFT"
MSFT_LISTING_KEY = "US-XNAS-MSFT"
MSFT_CIK = "0000789019"

MSFT_SUBJECT = SecurityStateSubject(
    security_id=MSFT_SECURITY_ID,
    issuer_id=MSFT_ISSUER_ID,
    listing_key=MSFT_LISTING_KEY,
    ticker_display="MSFT",
    issuer_cik=MSFT_CIK,
    owner_evidence=_UNREAD_OWNER_EVIDENCE,
)

_WORKSPACE_SCHEMA = "event_workspace.v1"
_STALE_DAYS = 120
# The estimated next-earnings WINDOW (never a single precise date -- Sol
# blocker 6: no canonical earnings-calendar owner exists for this build).
# ~1 fiscal quarter (91d) +/- a 2-week band around calendar_end.
_EARNINGS_WINDOW_START_DAYS = 77
_EARNINGS_WINDOW_END_DAYS = 105
_EARNINGS_WINDOW_BASIS = (
    "deterministic Mastermind estimate: fiscal_period.calendar_end + ~1 fiscal "
    "quarter; no canonical earnings-calendar owner exists"
)

def _earnings_consumer(subject: SecurityStateSubject) -> dict[str, str]:
    return {
        "workstream": "WS:MARKET-OS",
        "job": f"build security_state.v1 for {subject.ticker_display}",
        "output_contract": "security_state.v1",
    }

DISCLOSURES: tuple[str, ...] = (
    "CIK_LEG_OWNER_BACKED_CURRENT_ONLY: issuer CIK read through canonical "
    "IssuerMaster.cik_of_issuer; current registrant evidence only, not historical lineage",
    "OWNER_COMPOSED_SUBJECT_CURRENT_ONLY: security_id, issuer_id, listing_key and "
    "ticker_display composed through current VendorAliasTable and IssuerMaster readers "
    "at one injected decision date",
    "ISSUERMASTER_CURRENT_IDENTITY_ONLY: no asof-scoped issuer lineage; proof is "
    "current-identity",
    "ALIAS_EPOCH_VALID_FROM: corroboration alias window start is a placeholder "
    "floor, not evidence",
)

# MAJOR-1 (round-3 review, 2026-09-06): the four ``DISCLOSURES`` strings above
# all assert that a CIK/alias/issuer reader ran this cycle at one injected
# decision date. That is true of a genuine owner-composed subject, but never
# true of the UNREAD fallback shell (``AAPL_SUBJECT`` / ``MSFT_SUBJECT``,
# selected only when the owner-identity batch itself could not be read) --
# no reader ran and no decision date was used, so none of ``DISCLOSURES``
# applies. ``compile_security_state_failure`` must publish this tuple
# instead of ``DISCLOSURES`` whenever :func:`_owner_identity_unread` is true.
# The schema pins ``identity_proof.disclosures`` to exactly 4 items
# ("contracts/market_os/security_state.v1.schema.json", out of scope for
# this diff), so this is a 1:1 UNREAD counterpart to each ``DISCLOSURES``
# entry rather than a single collapsed string.
UNREAD_DISCLOSURES: tuple[str, ...] = (
    "CIK_LEG_OWNER_UNREAD: issuer CIK was not read this cycle; the frozen "
    "pinned CIK is retained as-is and is not corroborated by any reader",
    "OWNER_COMPOSED_SUBJECT_UNREAD: security_id, issuer_id, listing_key and "
    "ticker_display are the frozen pinned fallback values; no reader ran "
    "this cycle and no decision date was used",
    "ISSUER_LINEAGE_UNREAD: no issuer lineage or current-identity check was "
    "performed this cycle",
    "ALIAS_EPOCH_UNREAD: no alias corroboration window was evaluated this "
    "cycle; the alias reader did not run",
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

# Decision Spine required axes (Sol blocker 1): state + change. legs.evidence
# REMAINS a leg but is supporting metadata for change's provenance, not its
# own Decision Spine axis -- it stays optional, as it always has.
_REQUIRED_LEGS: tuple[str, ...] = ("state", "change")
_OPTIONAL_LEGS: tuple[str, ...] = (
    "opportunity_context", "risk", "catalyst", "personal_impact", "evidence",
)
# NONBLOCKING (Sol blocker 7): a leg whose coverage_state does not itself
# represent a degradation -- AVAILABLE, or a disclosed non-applicability
# (NOT_APPLICABLE/NOT_COVERED). Deliberately looser than "available": a
# NOT_APPLICABLE personal_impact does not make the read look MORE complete
# than it is (it never counts toward *_legs_available), it only means that
# leg does not BLOCK overall_state.
_NONBLOCKING_STATES = frozenset({"AVAILABLE", "NOT_COVERED", "NOT_APPLICABLE"})
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


def _require_subject(subject: object) -> SecurityStateSubject:
    """Refuse ticker strings or partial dicts at the compiler boundary."""
    if not isinstance(subject, SecurityStateSubject):
        raise SecurityStateCompilationError(
            "an immutable owner-composed subject is required; a bare ticker is not identity"
        )
    scalar_values = (
        subject.security_id,
        subject.issuer_id,
        subject.listing_key,
        subject.ticker_display,
        subject.issuer_cik,
    )
    if not all(isinstance(value, str) and value.strip() == value and value for value in scalar_values):
        raise SecurityStateCompilationError("owner-composed subject fields must be non-empty strings")
    if len(subject.issuer_cik) != 10 or not subject.issuer_cik.isdigit():
        raise SecurityStateCompilationError("owner-composed subject issuer_cik must be ten digits")
    if subject.ticker_display != subject.ticker_display.upper():
        raise SecurityStateCompilationError("owner-composed subject ticker_display must be uppercase")
    if not subject.owner_evidence or any(
        not isinstance(item, tuple)
        or len(item) != 2
        or not all(isinstance(value, str) and value for value in item)
        for item in subject.owner_evidence
    ):
        raise SecurityStateCompilationError("owner-composed subject requires immutable owner evidence")
    evidence_keys = [key for key, _value in subject.owner_evidence]
    if len(set(evidence_keys)) != len(evidence_keys):
        raise SecurityStateCompilationError("owner-composed subject evidence keys must be unique")
    required_evidence = {"decision_date", "alias_reader", "issuer_reader", "cik_reader"}
    if not required_evidence.issubset(evidence_keys):
        raise SecurityStateCompilationError(
            "owner-composed subject evidence is missing a canonical owner receipt"
        )
    return subject


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
    # The injected alias decision date is an owner observation clock. Preserve
    # it in the public receipt, but exclude it from semantic content identity:
    # recompiling the same current bindings after midnight is a wall-clock-only
    # change. Reader provenance and every resolved identity value remain hashed.
    identity_proof = payload.get("identity_proof")
    if isinstance(identity_proof, dict):
        for leg in identity_proof.get("legs") or ():
            if not isinstance(leg, dict):
                continue
            values = leg.get("values_read")
            if isinstance(values, list):
                leg["values_read"] = [
                    value for value in values
                    if not (
                        isinstance(value, dict)
                        and value.get("field") == "owner_decision_date"
                    )
                ]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return sha256(canonical.encode("utf-8")).hexdigest()


def build_security_state_validator(schema: Mapping[str, Any]) -> Draft202012Validator:
    """Compile the producer-injected canonical schema without performing I/O."""
    if not isinstance(schema, Mapping):
        raise SecurityStateCompilationError("security_state.v1 schema must be a mapping")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise SecurityStateCompilationError(f"security_state.v1 schema invalid: {exc}") from exc
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _self_validate(
    state: Mapping[str, Any], *, validator: Draft202012Validator,
) -> None:
    if not isinstance(validator, Draft202012Validator):
        raise SecurityStateCompilationError(
            "security_state.v1 requires the producer-injected canonical validator"
        )
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
    subject: SecurityStateSubject,
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
    owner_receipt = [
        (f"owner_{key}", value)
        for key, value in sorted(subject.owner_evidence)
    ]
    legs.append(_leg_receipt(
        "R1", "security_master row exists, security_state/superseded_by both null",
        "data/reference/security_master.parquet",
        "scripts/build_stock_library.py::_read_security_state_identity_rows (declared master artifact)",
        [
            ("row_present", security_master_row is not None),
            ("security_state", sec_state), ("superseded_by", superseded_by),
            *owner_receipt,
        ],
        "pass" if r1_pass else "fail", None if r1_pass else "SECURITY_SUPERSEDED",
    ))
    if not r1_pass:
        refusals.append("SECURITY_SUPERSEDED")

    # R2 — row names the requested owner-composed issuer, RESOLVED -----------
    row_issuer_id = _null_to_none(row.get("issuer_id"))
    row_issuer_state = _null_to_none(row.get("issuer_state"))
    r2_pass = row_issuer_id == subject.issuer_id and row_issuer_state == "RESOLVED"
    equalities.append(_equality("R2", "row.issuer_id", row_issuer_id, "expected_issuer_id", subject.issuer_id))
    legs.append(_leg_receipt(
        "R2", "security_master.issuer_id names the owner-composed issuer, issuer_state RESOLVED",
        "data/reference/security_master.parquet",
        "scripts/build_stock_library.py::_read_security_state_identity_rows",
        [("issuer_id", row_issuer_id), ("issuer_state", row_issuer_state)],
        "pass" if r2_pass else "fail", None if r2_pass else "IDENTITY_UNRESOLVED",
    ))
    if not r2_pass:
        refusals.append("IDENTITY_UNRESOLVED")

    # R3 — one active issuer row binds both requested issuer and current CIK --
    matching = [r for r in issuer_master_rows if _null_to_none(r.get("cik")) == subject.issuer_cik]
    r3_row = matching[0] if len(matching) == 1 else None
    r3_status = _null_to_none(r3_row.get("status")) if r3_row else None
    r3_issuer_id = _null_to_none(r3_row.get("issuer_id")) if r3_row else None
    r3_pass = r3_row is not None and r3_status == "active" and r3_issuer_id == subject.issuer_id
    equalities.append(_equality(
        "R3", "issuer_master matching row count", len(matching), "expected_count", 1,
    ))
    legs.append(_leg_receipt(
        "R3", "issuer_master carries exactly one active row binding the owner-composed issuer and CIK",
        "data/reference/issuer_master.parquet",
        "scripts/build_stock_library.py::_read_security_state_identity_rows",
        [
            ("cik", subject.issuer_cik),
            ("matching_row_count", len(matching)),
            ("issuer_id", r3_issuer_id),
            ("status", r3_status),
        ],
        "pass" if r3_pass else "fail", None if r3_pass else "ISSUER_GROUP_AMBIGUOUS",
    ))
    if not r3_pass:
        refusals.append("ISSUER_GROUP_AMBIGUOUS")

    # R4 — the issuer's current security set is exactly the requested security
    security_set = sorted({str(s) for s in issuer_security_ids})
    r4_pass = security_set == [subject.security_id]
    equalities.append(_equality(
        "R4", "issuer.security_set", security_set, "expected_security_set", [subject.security_id],
    ))
    legs.append(_leg_receipt(
        "R4", f"the owner-composed issuer's CURRENT security set is exactly {{{subject.security_id}}}",
        "data/reference/security_master.parquet",
        "scripts/build_stock_library.py::_read_security_state_identity_rows",
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
    r5_pass = (
        bool(listing_key)
        and derived_security_id is not None
        and derived_security_id == row_security_id == subject.security_id
        and listing_key == subject.listing_key
    )
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
        "scripts/build_stock_library.py::_read_security_state_identity_rows",
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
    parsed_event_company_id: str | None = None
    if event_id:
        try:
            parsed_event_company_id, _period, _event_type = parse_canonical_event_id(event_id)
        except ContractError:  # canonical owner parser's declared refusal type (MINOR 4)
            parsed_event_company_id = None
    expected_company_id = f"cik:{subject.issuer_cik}"
    event_id_ok = parsed_event_company_id == expected_company_id
    company_id_ok = company_id == expected_company_id
    filing_cik_ok = filing_cik == subject.issuer_cik
    r7_pass = (not workspace_available) or (event_id_ok and company_id_ok and filing_cik_ok)
    equalities.append(_equality("R7a", "workspace.event_id matches pattern", event_id_ok, "expected", True))
    equalities.append(_equality("R7b", "workspace.issuer.company_id", company_id, "expected_company_id", expected_company_id))
    equalities.append(_equality("R7c", "workspace.completeness.filing.filing_key.cik", filing_cik, "expected_cik", subject.issuer_cik))
    legs.append(_leg_receipt(
        "R7", "workspace parity: event_id/company_id/filing cik all bind to the owner-composed CIK "
        "(vacuous pass when no workspace is available this cycle)",
        "event_workspace.v1 (owner-native workspace body)",
        "engine.neuralweb.company_intelligence_reader.load_workspace_with_disposition",
        [("workspace_available", workspace_available), ("event_id", event_id), ("company_id", company_id), ("filing_cik", filing_cik)],
        "pass" if r7_pass else "fail", None if r7_pass else "SUBJECT_NATIVE_PARITY_FAILED",
    ))
    if not r7_pass:
        refusals.append("SUBJECT_NATIVE_PARITY_FAILED")

    # R8 — master CIK always agrees with the owner-composed subject; a
    # present workspace must additionally agree.  The owner-to-subject edge
    # is never vacuous merely because no event is published this cycle.
    master_cik = _null_to_none(row.get("issuer_cik"))
    r8_pass = master_cik == subject.issuer_cik and (
        not workspace_available or filing_cik_ok
    )
    equalities.append(_equality(
        "R8", "master.issuer_cik", master_cik,
        "owner_subject.issuer_cik", subject.issuer_cik,
    ))
    legs.append(_leg_receipt(
        "R8", "master issuer_cik agrees with the owner-composed current CIK; "
        "a present workspace also agrees",
        "data/reference/security_master.parquet + event_workspace.v1",
        "scripts/build_stock_library.py::_read_security_state_identity_rows",
        [("workspace_available", workspace_available), ("master_issuer_cik", master_cik),
         ("subject_issuer_cik", subject.issuer_cik), ("workspace_native_cik", filing_cik)],
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
        try:
            subject_mic = parse_listing_key(subject.listing_key).mic
        except IdentityError:
            subject_mic = None
        agrees = alias_mic == subject_mic and alias_ticker == subject.ticker_display
        corroboration_state = "AVAILABLE" if agrees else "DIVERGENT"
        r9_divergent = not agrees
        equalities.append(_equality(
            "R9", "workspace primary alias (mic,ticker)", f"{alias_mic}:{alias_ticker}",
            "owner subject current alias (listing mic,ticker_display)",
            f"{subject_mic}:{subject.ticker_display}",
        ))
    legs.append(_leg_receipt(
        "R9", "corroboration: workspace primary alias agrees with the owner subject's current alias and listing venue",
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

def _build_k1_recipe(
    *, subject: SecurityStateSubject, max_references: int = 1,
) -> dict[str, Any]:
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
        "consumer": _earnings_consumer(subject),
        "subject_instance": {"key_type": "cik", "key": subject.issuer_cik},
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
    subject: SecurityStateSubject,
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
        "subject": {"key_type": "cik", "key": subject.issuer_cik},
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


def _build_k1_block(
    references: Sequence[Mapping[str, Any]], *, subject: SecurityStateSubject,
) -> dict[str, Any]:
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
        "consumer": _earnings_consumer(subject),
        "supported_claim": {
            "kind": "claim",
            "text": (
                f"The {subject.ticker_display} company-change leg is backed by "
                "owner-native event_workspace.v1 generation(s)."
            ),
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


def _consume_k1_bundle(
    *,
    bundle: Mapping[str, Any],
    subject: SecurityStateSubject,
    recipe: Mapping[str, Any],
    reference: Mapping[str, Any] | None,
    block: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    """Verify and consume a producer-prepared Evidence Foundation receipt.

    Evidence Foundation's public compiler validates its schemas from disk. The
    producer owns that I/O boundary and injects the resulting receipt here.
    This is a self-consistency check, not an independent derivation (MINOR 1
    review finding): the producer's own ``_prepare_security_state_k1_bundle``
    (``scripts/security_state_producer.py``) builds the injected bundle by
    calling this module's OWN private ``_build_k1_recipe`` /
    ``_build_k1_reference`` / ``_build_k1_block`` — the same functions this
    method re-derives its expected IDs from. What this check actually proves
    is that the bundle the producer handed back still agrees with what those
    builders produce for THIS subject, so a swapped or foreign bundle (one
    built for a different security, CIK, reference, or block) is refused here
    rather than silently consumed.
    """
    if not isinstance(bundle, Mapping):
        raise SecurityStateCompilationError("producer-prepared K1 bundle must be a mapping")
    expected_recipe_id = recipe["recipe_id"]
    if bundle.get("subject_cik") != subject.issuer_cik:
        raise SecurityStateCompilationError("producer-prepared K1 bundle subject CIK mismatch")
    if bundle.get("recipe_id") != expected_recipe_id:
        raise SecurityStateCompilationError("producer-prepared K1 bundle recipe mismatch")

    if reference is None or block is None:
        compilation = bundle.get("empty_compilation")
        expected_block_ids: list[str] = []
    else:
        found = bundle.get("found")
        if not isinstance(found, Mapping):
            raise SecurityStateCompilationError("producer-prepared K1 found receipt is missing")
        if found.get("reference_id") != reference["reference_id"]:
            raise SecurityStateCompilationError("producer-prepared K1 reference mismatch")
        if found.get("block_id") != block["evidence_block_id"]:
            raise SecurityStateCompilationError("producer-prepared K1 block mismatch")
        compilation = found.get("compilation")
        expected_block_ids = [str(block["evidence_block_id"])]

    if not isinstance(compilation, Mapping):
        raise SecurityStateCompilationError("producer-prepared K1 compilation is missing")
    if compilation.get("schema") != "evidence_foundation.recipe_compilation_receipt.v1":
        raise SecurityStateCompilationError("producer-prepared K1 compilation schema mismatch")
    if compilation.get("recipe_id") != expected_recipe_id:
        raise SecurityStateCompilationError("producer-prepared K1 compilation recipe mismatch")
    if compilation.get("consumer") != recipe["consumer"]:
        raise SecurityStateCompilationError("producer-prepared K1 compilation consumer mismatch")
    if compilation.get("block_ids") != expected_block_ids:
        raise SecurityStateCompilationError("producer-prepared K1 compilation block mismatch")
    if compilation.get("owner_payloads_persisted") is not False:
        raise SecurityStateCompilationError("producer-prepared K1 compilation persisted owner payloads")
    if compilation.get("authority") != ALL_FALSE_AUTHORITY:
        raise SecurityStateCompilationError("producer-prepared K1 compilation authority mismatch")
    return compilation


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

_STATE_LEG_REFS: tuple[str, ...] = ("ladder.state", "ladder.dir", "tech.chg_1d")
_DIRECTION_WORD = {"up": "up", "down": "down"}
_DIRECTION_WORD_ZH = {"up": "上行", "down": "下行"}


def _build_state_leg(*, blob: Mapping[str, Any]) -> dict[str, Any]:
    """Decision Spine ``legs.state`` (Sol blocker 1).

    EXISTING owner-native, deterministic, display-tier values read verbatim
    off the producer's ``rec`` -- the price ladder's own state/direction
    label, plus the day's raw price-change read. Zero arithmetic; never a
    score/rank/gate (``authority.can_*`` stays all-false regardless). This
    leg is independent of the earnings-workspace identity chain: a ladder
    read is not itself a claim about THIS cycle's earnings event, so it is
    never forced to UNAVAILABLE by a ``BLOCKED_IDENTITY_BRIDGE`` -- only the
    top-level ``dominant_degradation``/``coverage.overall_state`` are (see
    :func:`compile_security_state`).
    """
    ladder = blob.get("ladder") if isinstance(blob.get("ladder"), Mapping) else {}
    tech = blob.get("tech") if isinstance(blob.get("tech"), Mapping) else {}
    ladder_state = _null_to_none(ladder.get("state"))
    ladder_direction = _null_to_none(ladder.get("dir"))
    chg_1d = _null_to_none(tech.get("chg_1d"))

    values_read = [{"field": "tech.chg_1d", "value": _jsonable(chg_1d)}]

    if ladder_state is not None:
        direction_en = _DIRECTION_WORD.get(str(ladder_direction), "unclear")
        direction_zh = _DIRECTION_WORD_ZH.get(str(ladder_direction), "方向不明")
        summary = _bilingual(
            f"Ladder state: {ladder_state} ({direction_en}).",
            f"阶梯状态：{ladder_state}（{direction_zh}）。",
        )
        coverage_state = "AVAILABLE"
    else:
        summary = _bilingual(
            "No deterministic ladder state is available for this security yet.",
            "该证券当前没有可用的确定性阶梯状态。",
        )
        coverage_state = "UNAVAILABLE"

    return {
        "deterministic_state_refs": list(_STATE_LEG_REFS),
        "ladder_state": ladder_state,
        "ladder_direction": ladder_direction,
        "values_read": values_read,
        "summary": summary,
        "coverage_state": coverage_state,
    }


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
    """The next-earnings catalyst -- an ESTIMATED WINDOW, never a precise date
    (Sol blocker 6: presenting ``calendar_end + 91d`` as a single observed date
    labeled AVAILABLE overstated this leg's own honesty; no canonical
    earnings-calendar owner exists for this build). When the only observable
    this leg can offer is a non-authoritative estimate, coverage_state is
    PARTIAL -- it is never plain AVAILABLE."""
    if workspace is None or workspace_disposition != "found":
        return {"next_observables": [], "deadlines": [], "coverage_state": "UNAVAILABLE"}
    fiscal = workspace.get("fiscal_period") if isinstance(workspace.get("fiscal_period"), Mapping) else {}
    calendar_end = _null_to_none(fiscal.get("calendar_end"))
    window_start: str | None = None
    window_end: str | None = None
    if calendar_end:
        try:
            end_date = date.fromisoformat(str(calendar_end)[:10])
            window_start = (end_date + timedelta(days=_EARNINGS_WINDOW_START_DAYS)).isoformat()
            window_end = (end_date + timedelta(days=_EARNINGS_WINDOW_END_DAYS)).isoformat()
        except ValueError:
            window_start = window_end = None
    if window_start is None or window_end is None:
        return {"next_observables": [], "deadlines": [], "coverage_state": "UNAVAILABLE"}
    observables = [{
        "kind": "ESTIMATED_WINDOW",
        "window_start": window_start,
        "window_end": window_end,
        "authoritative": False,
        "basis": _EARNINGS_WINDOW_BASIS,
    }]
    return {"next_observables": observables, "deadlines": [], "coverage_state": "PARTIAL"}


def _build_personal_impact_leg() -> dict[str, Any]:
    return {"state": "NO_USER_CONTEXT", "user_exposure_overlay_ref": None, "coverage_state": "NOT_APPLICABLE"}


# ---------------------------------------------------------------------------
# coverage / dominant_degradation aggregation
# ---------------------------------------------------------------------------

def _build_coverage_and_dominant(legs: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Any], str]:
    """The coverage denominator block (Sol blocker 7).

    Six exact counts, never conflated: ``*_legs_available`` counts ONLY legs
    whose ``coverage_state`` is exactly ``AVAILABLE``; ``*_legs_nonblocking``
    additionally counts a disclosed ``NOT_APPLICABLE``/``NOT_COVERED`` leg --
    honestly nonblocking, never disguised as available. ``overall_state``'s
    UNAVAILABLE branch gates on the NONBLOCKING count (a required leg that is
    genuinely missing/stale/etc. blocks; a required leg can never itself be
    NOT_APPLICABLE/NOT_COVERED in this build, so the two counts agree there in
    practice, but the semantics stay distinct on purpose).
    """
    missing_legs: list[str] = []
    stale_legs: list[str] = []
    rights_blocked_legs: list[str] = []
    conflicted_legs: list[str] = []
    required_available = 0
    required_nonblocking = 0
    optional_available = 0
    optional_nonblocking = 0
    worst_severity = 0

    for name in (*_REQUIRED_LEGS, *_OPTIONAL_LEGS):
        state = legs[name]["coverage_state"]
        strictly_available = state == "AVAILABLE"
        nonblocking = state in _NONBLOCKING_STATES
        if name in _REQUIRED_LEGS:
            required_available += int(strictly_available)
            required_nonblocking += int(nonblocking)
        else:
            optional_available += int(strictly_available)
            optional_nonblocking += int(nonblocking)
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
    elif required_nonblocking < len(_REQUIRED_LEGS):
        overall_state = "UNAVAILABLE"
    else:
        overall_state = "PARTIAL"

    coverage = {
        "overall_state": overall_state,
        "required_legs_total": len(_REQUIRED_LEGS),
        "required_legs_available": required_available,
        "required_legs_nonblocking": required_nonblocking,
        "optional_legs_total": len(_OPTIONAL_LEGS),
        "optional_legs_available": optional_available,
        "optional_legs_nonblocking": optional_nonblocking,
        "missing_legs": missing_legs, "stale_legs": stale_legs,
        "rights_blocked_legs": rights_blocked_legs, "conflicted_legs": conflicted_legs,
    }
    return coverage, dominant


# ---------------------------------------------------------------------------
# public entry points
# ---------------------------------------------------------------------------

def compile_security_state(
    *,
    subject: SecurityStateSubject,
    validator: Draft202012Validator,
    k1_bundle: Mapping[str, Any],
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
    """Compile ``security_state.v1`` for one owner-composed security subject.

    Every argument is a plain dict/row/string the caller already read (or
    fabricated for a test) — this function performs no I/O and reads no wall
    clock; ``now`` is the injected "as of" instant. See the module docstring
    for the ZERO I/O boundary and :func:`_run_identity_chain` for R1-R9.
    """
    subject = _require_subject(subject)
    if not isinstance(blob, Mapping):
        raise SecurityStateCompilationError("blob must be a mapping")
    if str(blob.get("ticker") or "").strip().upper() != subject.ticker_display:
        raise SecurityStateCompilationError(
            "blob ticker does not match the immutable owner-composed subject"
        )
    if workspace_disposition not in ("found", "not_published", "fetch_failed"):
        raise SecurityStateCompilationError(f"unknown workspace_disposition: {workspace_disposition!r}")
    try:
        now_dt = datetime.fromisoformat(str(now).replace("Z", "+00:00"))
    except ValueError as exc:
        raise SecurityStateCompilationError(f"now is not a valid ISO-8601 datetime: {now!r}") from exc

    identity_workspace = workspace if workspace_disposition == "found" else None
    identity_proof = _run_identity_chain(
        subject=subject,
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
    effective_disposition = workspace_disposition

    change_leg = _build_change_leg(
        workspace=effective_workspace, workspace_disposition=effective_disposition,
        event_id=event_id, generation_id=generation_id, now_date=now_dt.date(),
    )
    if identity_blocked:
        # MINOR 2 (review finding): an identity-blocked subject must show the
        # IDENTITY refusal as the null cause on every disposition, not only
        # "found". Before this fix, a "not_published"/"fetch_failed"
        # disposition fell straight through to `_build_change_leg`'s own
        # workspace-level summary ("No current earnings-change event is
        # published" / "an owner fetch failure, not an absence") even though
        # the actual refusal was the identity chain, never the workspace read
        # — a glance-tier cause mislabel (the real refusal stays visible in
        # identity_proof either way, so this never hid the null itself).
        change_leg = {
            **change_leg,
            "summary": _bilingual(
                "Change tracking refused: the security identity bridge could not be proven this cycle.",
                "变动追踪被拒绝：本轮无法证明证券身份链。",
            ),
        }

    recipe = _build_k1_recipe(subject=subject)
    if identity_blocked or effective_workspace is None or event_id is None or generation_id is None:
        compilation = _consume_k1_bundle(
            bundle=k1_bundle, subject=subject, recipe=recipe,
            reference=None, block=None,
        )
        evidence_leg = _build_evidence_leg(recipe_id=recipe["recipe_id"], compilation=compilation)
    else:
        lifecycle = effective_workspace.get("lifecycle") if isinstance(effective_workspace.get("lifecycle"), Mapping) else {}
        reference = _build_k1_reference(
            subject=subject,
            generation_id=str(generation_id), event_id=str(event_id),
            manifest_sha256=manifest_sha256,
            source_available_at=_null_to_none(lifecycle.get("source_available_at")),
            observed_at=_null_to_none(lifecycle.get("observed_at")),
            generated_at=_null_to_none(effective_workspace.get("generated_at")),
        )
        block = _build_k1_block([reference], subject=subject)
        compilation = _consume_k1_bundle(
            bundle=k1_bundle, subject=subject, recipe=recipe,
            reference=reference, block=block,
        )
        evidence_leg = _build_evidence_leg(recipe_id=recipe["recipe_id"], compilation=compilation)

    state_leg = _build_state_leg(blob=blob)
    opportunity_leg = _build_opportunity_context_leg(blob=blob)
    catalyst_leg = _build_catalyst_leg(workspace=effective_workspace, workspace_disposition=effective_disposition)
    personal_impact_leg = _build_personal_impact_leg()
    risk_leg = _build_risk_leg(
        blob=blob, change_leg=change_leg, evidence_leg=evidence_leg, opportunity_leg=opportunity_leg,
    )

    legs = {
        "state": state_leg, "change": change_leg, "opportunity_context": opportunity_leg, "risk": risk_leg,
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
        "security_id": subject.security_id, "issuer_id": subject.issuer_id,
        "listing_key": subject.listing_key, "ticker_display": subject.ticker_display,
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
    _self_validate(state, validator=validator)
    return state


_LAST_GOOD_REASON = "prior cycle's committed security_state.v1"


def _prior_matches_subject(
    prior: Mapping[str, Any] | None, *, subject: SecurityStateSubject,
) -> bool:
    """True when ``prior``'s owner-composed CIK agrees with ``subject``.

    Reads the R8 leg's ``subject_issuer_cik`` value_read field when present
    (the shape this module now writes). A prior written before that field
    existed carries only ``master_issuer_cik`` on the same leg — one
    migration cycle accepts that as an equivalent identity match rather than
    treating every pre-existing state as a subject mismatch, which would
    silently drop every ticker's ``last_good`` on the first post-deploy
    failure (Sol blocker 4).

    A prior written by the PRE-PR code carries no R8 leg at all
    (``identity_proof.legs == []`` — the CIK receipt is new in this PR), so
    neither CIK set above is ever populated for it. The four top-level
    subject fields already matched above at that point — the strongest
    identity signal an old-format shell can offer — so a legacy
    ``COMPILER_FAILURE`` shell with no R-checks is accepted as a match for
    this one migration cycle (M2) rather than silently dropping
    ``last_good`` the first time this deploy sees a pre-existing failure
    shell. This is bounded to that exact legacy shape: any shell that DOES
    carry R-checks but simply lacks an R8 CIK value (a new-format shape this
    module would never itself produce) still falls through to the final
    ``return False``.
    """
    if not isinstance(prior, Mapping):
        return False
    if not all(
        prior.get(field) == getattr(subject, field)
        for field in ("security_id", "issuer_id", "listing_key", "ticker_display")
    ):
        return False
    identity_proof = prior.get("identity_proof")
    if not isinstance(identity_proof, Mapping):
        return False
    legs = identity_proof.get("legs") or ()
    subject_ciks: set[Any] = set()
    master_ciks: set[Any] = set()
    for leg in legs:
        if not (isinstance(leg, Mapping) and leg.get("check") == "R8"):
            continue
        for value in leg.get("values_read") or ():
            if not isinstance(value, Mapping):
                continue
            if value.get("field") == "subject_issuer_cik":
                subject_ciks.add(value.get("value"))
            elif value.get("field") == "master_issuer_cik":
                master_ciks.add(value.get("value"))
    if subject_ciks:
        return subject_ciks == {subject.issuer_cik}
    if master_ciks:
        return master_ciks == {subject.issuer_cik}
    if not legs and prior.get("dominant_degradation") == "COMPILER_FAILURE":
        return True
    return False


def _is_last_good_eligible(
    prior: Mapping[str, Any] | None, *, subject: SecurityStateSubject,
) -> bool:
    """Eligibility predicate for treating ``prior`` as this cycle's ``last_good``
    (Sol blocker 4).

    ``prior`` is the FULL prior ``security_state.v1`` read (never the compact
    ``last_good`` receipt shape). It is eligible ONLY when every one of these
    holds: it is a mapping whose ``schema`` is ``security_state.v1``, its
    ``identity_proof.state`` is ``PROVEN`` (a ``BLOCKED_IDENTITY_BRIDGE`` or
    ``PARTIAL`` identity proof is never eligible, even if its own
    ``dominant_degradation`` looks benign), and its own
    ``dominant_degradation`` is not ``COMPILER_FAILURE``. A failed prior state
    can therefore never silently become the next failure's "last complete
    read".
    """
    if not isinstance(prior, Mapping):
        return False
    if not _prior_matches_subject(prior, subject=subject):
        return False
    if prior.get("schema") != SCHEMA:
        return False
    identity_proof = prior.get("identity_proof")
    if not isinstance(identity_proof, Mapping) or identity_proof.get("state") != "PROVEN":
        return False
    if prior.get("dominant_degradation") == "COMPILER_FAILURE":
        return False
    return True


def derive_last_good(
    prior: Mapping[str, Any] | None, *, subject: SecurityStateSubject,
) -> dict[str, Any] | None:
    """The ``last_good`` a failure shell should carry, derived from the FULL
    prior ``security_state.v1`` read (Sol blocker 4).

    Three-way rule, in order:

    1. ``prior`` itself is eligible (:func:`_is_last_good_eligible`) -> snapshot
       it as the compact ``{generated_at, content_sha256, dominant_degradation,
       reason}`` receipt.
    2. ``prior`` is ineligible but itself already carries a ``last_good`` ->
       carry that receipt forward UNCHANGED. This is what makes a SECOND
       consecutive failure keep the ORIGINAL good read rather than losing it:
       failure #1's own ``last_good`` (a snapshot of the last success) is not
       overwritten by failure #1 itself, because failure #1 is never eligible
       (its ``dominant_degradation`` is ``COMPILER_FAILURE``).
    3. Otherwise -> ``None`` (no usable last-good anywhere in the chain).
    """
    if _is_last_good_eligible(prior, subject=subject):
        assert isinstance(prior, Mapping)  # narrows for the type checker
        return {
            "generated_at": str(prior["generated_at"]),
            "content_sha256": str(prior["content_sha256"]),
            "dominant_degradation": str(prior["dominant_degradation"]),
            "reason": _LAST_GOOD_REASON,
        }
    if _prior_matches_subject(prior, subject=subject):
        assert isinstance(prior, Mapping)
        carried = prior.get("last_good")
        if isinstance(carried, Mapping):
            return dict(carried)
    return None


def compile_security_state_failure(
    *, subject: SecurityStateSubject, validator: Draft202012Validator,
    now: str,
    prior_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Pure fallback shell for the PRODUCER's own exception-containment boundary.

    Called by ``scripts/build_stock_library.py`` — never by
    :func:`compile_security_state` itself — when compilation raised. Every leg
    is typed UNAVAILABLE/blocked (``personal_impact`` stays its permanent
    ``NOT_APPLICABLE``). ``prior_state`` is the FULL prior cycle's committed
    ``security_state.v1`` read (or ``None`` when there is none) — this
    function derives ``last_good`` from it via :func:`derive_last_good`'s
    eligibility predicate (Sol blocker 4), so a failed prior state can never
    become the next failure's "last complete read", and a compiler failure can
    never silently present as ``dominant_degradation: NONE`` (a mutation-kill
    this module is built to resist). No exception string or caller-supplied
    reason is accepted at this public-output boundary.
    """
    subject = _require_subject(subject)
    # MAJOR-2 (round-3 review, 2026-09-06): this reason string is public and
    # feeds both the opportunity-context null_reason and the risk failed_gate
    # below, so it must never claim owner identity was composed on the
    # UNREAD fallback path (no reader ran for that subject at all). Bound
    # after ``owner_unread`` is known, in plain consumer-facing language --
    # not the internal artifact name, "compiler", or "composed" jargon the
    # prior single string used. The schema types both destination fields as
    # a plain string ("contracts/market_os/security_state.v1.schema.json"),
    # so this stays EN-only; it is out of scope for this diff to add a
    # bilingual pair for those two fields.
    owner_unread = _owner_identity_unread(subject.owner_evidence)
    if owner_unread:
        public_reason = (
            "This security's information could not be updated this cycle "
            "because ownership data was unavailable."
        )
    else:
        public_reason = (
            "This security's information could not be finished this cycle "
            "after its ownership was confirmed."
        )
    blocked_summary = _bilingual(
        "This security's state could not be compiled this cycle (a compiler failure, not an absence).",
        "本次未能编译该证券的状态（属于编译失败，并非事件不存在）。",
    )
    # B2 (META-CEO ruling 2026-09-06): a fallback subject (AAPL_SUBJECT /
    # MSFT_SUBJECT, selected when the owner-identity batch itself failed)
    # never had an owner reader run this cycle. The R8 leg must say so —
    # result 'fail' with an OWNER_IDENTITY_UNREAD refusal code and no
    # fabricated reader names — rather than presenting a PASS that implies
    # VendorAliasTable/IssuerMaster were consulted and agreed. A genuine
    # owner-composed subject (compile_security_state raised for some OTHER
    # reason after identity was proven) still gets the honest PASS leg.
    # (``owner_unread`` was already computed above for ``public_reason``.)
    if owner_unread:
        r8_leg = _leg_receipt(
            "R8",
            "owner identity batch failed this cycle; no owner reader ran for "
            "this subject, so this failure shell retains only its frozen "
            "ticker/CIK and refuses to present an owner-backed identity pass",
            "SecurityStateSubject (frozen pinned fallback, not owner-composed)",
            "scripts/security_state_producer.py::_fallback_subject_for_ticker",
            [("subject_issuer_cik", subject.issuer_cik), ("owner_identity", "UNREAD")],
            "fail", "OWNER_IDENTITY_UNREAD",
        )
        equality_right_label = "fallback_subject.issuer_cik"
        refusals = ["COMPILER_FAILURE", "OWNER_IDENTITY_UNREAD"]
    else:
        r8_leg = _leg_receipt(
            "R8", "failure shell retains the owner-composed current CIK without claiming a full identity-chain pass",
            "SecurityStateSubject (producer-composed owner receipt)",
            "scripts/build_stock_library.py::_read_security_state_identity_rows",
            [
                ("subject_issuer_cik", subject.issuer_cik),
                *[(f"owner_{key}", value) for key, value in sorted(subject.owner_evidence)],
            ],
            "pass", None,
        )
        equality_right_label = "owner_subject.issuer_cik"
        refusals = ["COMPILER_FAILURE"]
    identity_proof = {
        "state": "BLOCKED_IDENTITY_BRIDGE", "method": "owner_backed_chain.v1",
        "legs": [r8_leg],
        "equalities": [_equality(
            "R8", "failure_shell.subject.issuer_cik", subject.issuer_cik,
            equality_right_label, subject.issuer_cik,
        )],
        "refusals": refusals,
        "disclosures": list(UNREAD_DISCLOSURES) if owner_unread else list(DISCLOSURES),
    }
    state_leg = {
        "deterministic_state_refs": list(_STATE_LEG_REFS),
        "ladder_state": None, "ladder_direction": None, "values_read": [],
        "summary": blocked_summary, "coverage_state": "UNAVAILABLE",
    }
    change_leg = {
        "economic_episode_ref": None, "event_refs": [], "generation_id": None,
        "source_available_at": None, "observed_at": None, "summary": blocked_summary,
        "correction_state": "none", "coverage_state": "UNAVAILABLE", "workspace_warnings": [],
    }
    opportunity_leg = {
        "prophet": {"ref": None, "state": "UNAVAILABLE", "reason": _PROPHET_REASON},
        "entry": {"state": "UNAVAILABLE", "available": False, "null_reason": public_reason},
        "market_incorporation": {"ref": None, "state": "NOT_COVERED"},
        "dislocation": {"ref": None, "state": "NOT_COVERED"},
        "coverage_state": "UNAVAILABLE",
    }
    risk_leg = {
        "risk_refs": [], "failed_gates": [{"code": "COMPILER_FAILURE", "reason": public_reason}],
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
        "state": state_leg, "change": change_leg, "opportunity_context": opportunity_leg, "risk": risk_leg,
        "catalyst": catalyst_leg, "personal_impact": personal_impact_leg, "evidence": evidence_leg,
    }
    coverage, _leg_derived_dominant = _build_coverage_and_dominant(legs)
    state: dict[str, Any] = {
        "schema": SCHEMA, "version": VERSION,
        "security_id": subject.security_id, "issuer_id": subject.issuer_id,
        "listing_key": subject.listing_key, "ticker_display": subject.ticker_display,
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
        "last_good": derive_last_good(prior_state, subject=subject),
    }
    state["content_sha256"] = _content_sha256(state)
    _self_validate(state, validator=validator)
    return state
