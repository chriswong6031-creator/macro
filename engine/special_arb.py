"""Evidence-bound cash-deal economics for the Special Situations desk (F09-1 — context only).

For an announced fixed-CASH acquisition, tender offer or going-private the premium and the
spread are directly observable facts of a public filing — but only if every number can name
the filing bytes it came from. This module is the ONE pure owner (no IO) of:

  * `special_situations.deal_term_observation.v1` — immutable, source-bound term observations
    carrying exact evidence locators (document, character offsets, excerpt digest) and
    amendment/correction lineage;
  * deterministic extraction of those observations from public EDGAR filing text, which may
    decline coverage but must never publish a false precise value;
  * the current-term compiler (accession/amendment precedence, conflict detection);
  * `reduce_cash_deal()` — the single closed calculation/eligibility contract every consumer
    uses, returning four SEPARATELY NAMED numbers plus a typed quality state;
  * `select_ordered_context()` — the single ordered-projection owner shared by
    `mastermind_emit()` and `special_sits_intel.build_context_feed()`.

Three rules the previous lane broke, and why they are enforced here rather than downstream:

1. A model has ZERO numeric authority. `llm_terms` are candidate/context only (`parse_terms`);
   a number reaches a consumer only through an observation bound to source bytes.
2. Missingness never becomes a number. A month-only close stays a window with
   `days_to_close=None`; it is never resolved to month-end and then annualized.
3. No clamp, no cap, no ticker exception. An absurd spread is a symptom of a stale price, a
   terminal deal or a mis-extracted term — each of which now has its own visible state — so
   the fix is the receipt, not a band that hides the number.

Nothing here is scored, ranked as a signal, or sized. `is_signal` is False by construction.
"""
from __future__ import annotations

import calendar
import hashlib
import json
import re
from datetime import date, datetime

OBSERVATION_SCHEMA = "special_situations.deal_term_observation.v1"
EXTRACTION_METHOD = "deterministic_regex_span"
EXTRACTION_REVISION = "det.v1"
FORMULA_REVISION = "premium.v1"

# only these categories have a fixed deal price to compare against
ARB_CATEGORIES = frozenset({"Acquisitions", "Tender Offers", "Going-Private"})

# a deal in any of these lifecycle states is no longer live and leaves the current context
TERMINAL_STAGES = frozenset({
    "closed", "completed", "terminated", "withdrawn", "expired", "abandoned", "rejected",
})

# ------------------------------------------------------------------ closed vocabularies

QUALITY_VERIFIED = "VERIFIED"
QUALITY_STALE_PRICE = "STALE_PRICE"
QUALITY_AMBIGUOUS = "AMBIGUOUS"
QUALITY_NOT_FIXED_CASH = "NOT_FIXED_CASH"
QUALITY_TERMINAL = "TERMINAL"
QUALITY_SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
QUALITY_INELIGIBLE = "INELIGIBLE_CATEGORY"
QUALITY_CALCULATION_UNAVAILABLE = "CALCULATION_UNAVAILABLE"

QUALITY_STATES = frozenset({
    QUALITY_VERIFIED, QUALITY_STALE_PRICE, QUALITY_AMBIGUOUS, QUALITY_NOT_FIXED_CASH,
    QUALITY_TERMINAL, QUALITY_SOURCE_UNAVAILABLE, QUALITY_INELIGIBLE,
    QUALITY_CALCULATION_UNAVAILABLE,
})

# every visible failure the vertical may report; anything else is a bug, not a state
REASONS = frozenset({
    "SOURCE_BYTES_UNAVAILABLE", "SOURCE_HASH_MISMATCH", "TERM_NOT_FOUND", "TERM_AMBIGUOUS",
    "CONFLICTING_AMENDMENT", "RETRACTED", "TERMINAL_DEAL", "NOT_FIXED_CASH",
    "CURRENCY_MISMATCH", "PRICE_MISSING", "PRICE_STALE", "PRICE_BASIS_UNRESOLVED",
    "REFERENCE_SESSION_UNRESOLVED", "DATE_PRECISION_INSUFFICIENT", "CALCULATION_UNAVAILABLE",
    "PARTIAL_GENERATION", "CONSUMER_DIVERGENCE", "PATH_COLLISION",
    "DAILY_PRODUCTION_GATE_BLOCKED", "EFFECT_UNKNOWN", "INELIGIBLE_CATEGORY",
    # F09-1 repair (Sol review 5099936758): each names a way a number used to look exact
    # while its evidence did not support it.
    "INTEGRITY_FAILED",                 # a ledger row failed re-validation against its own digest
    "IDENTITY_UNRESOLVED",             # listing/security or transaction identity not proven
    "SOURCE_TRUNCATED",                # body was cut; absence of a conflict is not evidence
    "STATED_PREMIUM_BASIS_UNRESOLVED", # a percentage with no captured comparator
    "CALENDAR_RECEIPT_MISSING",        # freshness asserted without the independent calendar owner
    # F09-1 CRITICAL repair (Sol reviews 5102199556 / 5102373399 + reviewer STOP addendum)
    "PRICE_RECEIPT_INVALID",           # a receipt whose own arithmetic/identity does not re-derive
    "LISTING_UNSUPPORTED",             # not an exact resolved U.S. cash-equity listing on XNYS
    "TRANSACTION_SCOPE_UNRESOLVED",    # no deterministic current-transaction evidence scope
})

# Informational gaps that legitimately coexist with a VERIFIED row. They are NOT failures and
# must not appear in `reasons`: a VERIFIED row carrying "…UNRESOLVED" in its failure list is how
# a partial receipt read as a complete one (Sol review 5102373399, "closed-state cleanup").
WARNINGS = frozenset({
    "REFERENCE_SESSION_UNRESOLVED", "DATE_PRECISION_INSUFFICIENT",
    "STATED_PREMIUM_BASIS_UNRESOLVED",
})

# ------------------------------------------------------------------ narrow V1 price boundary
#
# V1 admits exactly ONE price provenance, pinned to the owner ruling of 2026-09-03: the existing
# per-ticker U.S. Yahoo store, which deliberately fetches `auto_adjust=False` and documents
# `close_price` as split-adjusted / dividend-UNadjusted — the structure-math basis. Every other
# committed panel (breadth, bt_prices, arb_prices, Canada/intl/HK search) is written
# `auto_adjust=True`, so labelling any of them a raw close is a FALSE receipt, and a false
# receipt is how a back-adjusted reference close silently inflated a filing-reference premium.
#
# The owner blobs are the REVIEWED ones. Pinning them is deliberately fail-closed: if either
# owner's basis or calendar semantics move, every row declines visibly instead of inheriting
# semantics nobody re-read. `tests/test_special_arb.py` asserts these equal the repository's
# current blobs, so drift is a loud test failure, never a silent coverage collapse.
PRICE_BASIS_SPLIT_ADJ = "split_adjusted_dividend_unadjusted"
PRICE_BASES = frozenset({PRICE_BASIS_SPLIT_ADJ})
PRICE_COLUMN = "close_price"
PRICE_COLUMNS = frozenset({PRICE_COLUMN})
PRICE_WRITER_OWNER = "collectors/yahoo.py"
PRICE_WRITER_BLOB = "7e41bb66d921b43bee6253f316bb1849e2c3e72b"
CALENDAR_OWNER = "lib/nyse_calendar.py"
CALENDAR_BLOB = "0ece6439ffe4b081ee7a268fe99b69e1de1216a3"
CALENDAR_REVISION = "nyse_calendar.v1"
US_CALENDAR_ID = "XNYS"
PRICE_ARTIFACT_RE = re.compile(r"^yahoo/[A-Z][A-Z0-9]{0,9}\.parquet$")

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX32 = re.compile(r"^[0-9a-f]{32}$")
_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# An exact canonical U.S. cash-equity root. A dot or a dash is a foreign suffix (ARX.TO, 0700.HK)
# or a share class (BRK.B) — both outside V1 — and the old `raw.split(".")[0]` fallback is what
# let a foreign target be priced from a same-root U.S. column.
_US_ROOT = re.compile(r"^[A-Z][A-Z0-9]{0,4}$")

OBSERVATION_FIELDS = ("price_per_share", "currency", "consideration",
                      "stated_premium_pct", "expected_close")

# date precision labels, coarsest last; only `exact_date` may drive days-to-close
PRECISION_EXACT_DATE = "exact_date"
PRECISION_MONTH = "month"
PRECISION_QUARTER = "quarter"
PRECISION_HALF = "half_year"
PRECISION_TEXT = "text_only"
PRECISION_EXACT_NUMERIC = "exact_numeric"

# Normalized-projection revision. An observation records WHICH projection of the raw source it
# was read from, because offsets are only meaningful against that exact projection.
PROJECTION_REVISION = "strip_markup.v1"
COMPLETENESS_COMPLETE = "complete"
COMPLETENESS_TRUNCATED = "truncated"
COMPLETENESS_UNKNOWN = "unknown"

_STATUS = frozenset({"observed", "ambiguous", "deferred", "retracted"})


# ------------------------------------------------------------------ small helpers

def _num(v: object) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f      # drop NaN


def _sha256(s: str | bytes) -> str:
    b = s.encode("utf-8", "replace") if isinstance(s, str) else s
    return hashlib.sha256(b).hexdigest()


def _canonical(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _iso_date(v: object) -> date | None:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    s = str(v or "").strip()[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


# ------------------------------------------------------------------ source + evidence

def source_descriptor(*, cik: object, form_type: object, accession: object,
                      filing_date: object, source_url: object, body: str | None = None,
                      body_sha256: str | None = None, acquired_at: object = None,
                      doc_id: object = None, body_truncated: bool = False,
                      raw_sha256: str | None = None, raw_bytes: int | None = None,
                      acceptance_datetime: object = None,
                      resolved_listing: object = None,
                      projection_revision: str = PROJECTION_REVISION) -> dict:
    """Identity of the exact bytes an observation was read from.

    Two receipts, not one. `raw_sha256`/`raw_bytes` identify the COMPLETE retained source object;
    `body_sha256`/`projection_revision` identify the normalized projection the character offsets
    actually index. The old contract hashed a `_strip_markup(raw)[:40000]` projection and then
    labelled it `full_submission_text` — so a conflicting price past the cut was invisible, and
    "no conflict found" was a claim the evidence never supported.

    `acceptance_datetime` is the SEC acceptance / system-availability timestamp parsed from the
    source bytes. A date-only `filing_date` cannot separate a premarket filing from an
    after-close one, and therefore cannot fix a reference session.
    """
    digest = body_sha256 or (_sha256(body) if body is not None else None)
    completeness = (COMPLETENESS_TRUNCATED if body_truncated
                    else (COMPLETENESS_COMPLETE if raw_sha256 else COMPLETENESS_UNKNOWN))
    return {
        "cik": str(cik) if cik is not None else None,
        "form_type": str(form_type) if form_type is not None else None,
        "accession": str(accession) if accession is not None else None,
        "filing_date": str(filing_date) if filing_date is not None else None,
        "acceptance_datetime": str(acceptance_datetime) if acceptance_datetime else None,
        "source_url": str(source_url) if source_url is not None else None,
        "raw_sha256": raw_sha256,
        "raw_bytes": int(raw_bytes) if raw_bytes is not None else None,
        "body_sha256": digest,
        "body_chars": len(body) if body is not None else None,
        "body_truncated": bool(body_truncated),
        "completeness": completeness,
        "projection_revision": projection_revision,
        "acquired_at": str(acquired_at) if acquired_at is not None else None,
        # The resolved listing receipt, in the SAME evidence chain as the bytes. A bare "$" may
        # only become an observed USD price when the listing was actually resolved, so the
        # resolution has to travel with the observation rather than being re-inferred later.
        "resolved_listing": str(resolved_listing) if resolved_listing else None,
        "doc_id": str(doc_id) if doc_id is not None else "normalized_projection",
    }


_MARKUP_SCRIPT = re.compile(r"(?is)<(script|style)\b.*?</\1>")
_MARKUP_TAG = re.compile(r"(?s)<[^>]+>")
_MARKUP_ENTITY = re.compile(r"&#?\w+;")
_MARKUP_WS = re.compile(r"\s+")


def normalized_projection(raw: str) -> str:
    """The ONE versioned normalized projection (`PROJECTION_REVISION`) offsets are read against.

    Owned here, in the pure module, and imported by the acquisition collector — because a
    locator is only meaningful against an EXACT projection, and two implementations of "strip the
    markup" are two projections. The ledger reader re-derives this from the retained raw object
    at load time and refuses any row whose offsets do not land where it says they do.
    """
    out = _MARKUP_SCRIPT.sub(" ", raw)
    out = _MARKUP_TAG.sub(" ", out)
    out = _MARKUP_ENTITY.sub(" ", out)
    return _MARKUP_WS.sub(" ", out).strip()


# Everything about a row that carries meaning but is NOT inside the observation digest. A
# forger who edits one of these and reseals the id passes `validate_observation()`, so the
# rebind compares the whole tuple against what the deterministic extractor actually authored
# from the retained bytes. `status` is in here on purpose: flipping a `deferred` out-of-scope
# price to `observed` is how a rejected background proposal would become the live offer.
_SEMANTIC_KEYS = ("field", "status", "normalized", "unit", "currency", "currency_basis",
                  "precision", "stated_basis", "note")


def _semantic_tuple(obs: dict) -> tuple:
    loc = obs.get("locator") or {}
    return (loc.get("start"), loc.get("end"),
            tuple(_canonical(obs.get(k)) for k in _SEMANTIC_KEYS))


def authored_terms(projection: str, *, listing_currency: str | None = None) -> set[tuple]:
    """Every term the deterministic extractor authors from THESE bytes, as semantic tuples.

    The closure the digest cannot provide. `observation_id` covers the span and the value, so a
    moved offset or an altered number breaks the id — but only until the forger recomputes it,
    and `validate_observation()` re-derives that id from the row's OWN fields, so a resealed row
    is self-consistent by construction. Measured: a row resealed with `normalized=999.0` while
    its locator still pointed at the true "$25.00 … per share" span passed every check and
    reached VERIFIED. A row is admissible only if the extractor, re-run over the verified
    projection, actually produces it.
    """
    stub = {"accession": "_", "doc_id": "normalized_projection",
            "projection_revision": PROJECTION_REVISION, "body_sha256": None}
    return {_semantic_tuple(o) for o in
            extract_term_observations(projection, source=stub,
                                      listing_currency=listing_currency)}


def _source_authority_reasons(obs: dict, receipt: dict, event: dict | None) -> list[str]:
    """Re-bind the meaning-bearing source fields to owners OUTSIDE the row. [] when clean.

    Sealing a field into `observation_id` stops a silent edit; it does not stop a forger who
    edits and reseals. Resealing is not authorization, so each of these is compared against a
    party that has no reason to agree with the row:

    * `acceptance_datetime` -> the retained ACQUISITION RECEIPT's own parsed canonical UTC. This
      is the clock `_reference_price()` uses to pick the session before the filing, so premarket
      and after-close resolve to different sessions and a row that can move it can move the
      published filing-reference premium.
    * `filing_date` -> the canonical Special Situations EVENT for that exact accession.
      `compile_current_terms()` orders candidates by this value, so a row that can move it can
      make a superseded term current.
    * `resolved_listing` (and the row's own `currency`) -> the canonical event listing, itself
      admitted only when the per-ticker Yahoo `close_price` owner proves it. Otherwise a row
      could assert a U.S. listing for a foreign target and let a bare `$` self-authorize as USD.

    Absent an event this fails CLOSED: an observation whose accession has no canonical event is
    not a row whose clock and listing anyone can vouch for.
    """
    src = obs.get("source") or {}
    reasons: list[str] = []

    def _s(v):
        return str(v) if v not in (None, "") else None

    if _s(src.get("acceptance_datetime")) != _s(receipt.get("acceptance_datetime")):
        reasons.append("SOURCE_CLOCK_MISMATCH")
    if event is None:
        reasons.append("EVENT_AUTHORITY_UNAVAILABLE")
        return sorted(set(reasons))
    if _s(src.get("filing_date")) != _s(event.get("filing_date")):
        reasons.append("SOURCE_CLOCK_MISMATCH")
    if _s(src.get("resolved_listing")) != _s(event.get("resolved_listing")):
        reasons.append("LISTING_AUTHORITY_MISMATCH")
    # the row's own currency may never exceed what the canonical listing proves
    row_ccy, canon_ccy = _s(obs.get("currency")), _s(event.get("currency"))
    if row_ccy is not None and row_ccy != canon_ccy:
        reasons.append("LISTING_AUTHORITY_MISMATCH")
    return sorted(set(reasons))


def rebind_observation(obs: dict, *, raw_bytes: bytes, receipt: dict,
                       accession: object = None,
                       authored: set[tuple] | None = None,
                       event: dict | None = None) -> list[str]:
    """Re-open the retained bytes and prove the row descends from them. [] when clean.

    This is the check the old runtime did not have. `validate_observation()` proves a row is
    internally self-consistent — it re-derives the id from the row's OWN fields — so a forger who
    edits a value, moves a span, rewrites the source metadata and then recomputes the id passes
    it. Nothing in the loader ever re-read the retained object or the normalized projection the
    offsets claim to index, and the extractor was still reading a legacy 40k `.txt`, so the seam
    between "the bytes I hashed" and "the document I claimed" was never inspected by anyone.

    Here the raw object is re-digested, the projection is re-derived from the verified bytes, and
    the locator span and excerpt digest are re-read out of that projection. A row that survives
    this cannot have been authored by anything other than the retained filing.
    """
    src = obs.get("source") or {}
    loc = obs.get("locator") or {}
    reasons: list[str] = []
    if not isinstance(raw_bytes, (bytes, bytearray)) or not raw_bytes:
        return ["SOURCE_BYTES_UNAVAILABLE"]
    raw_digest = hashlib.sha256(bytes(raw_bytes)).hexdigest()
    if raw_digest != receipt.get("raw_sha256") or raw_digest != src.get("raw_sha256"):
        reasons.append("SOURCE_HASH_MISMATCH")
    if len(raw_bytes) != receipt.get("raw_bytes") or len(raw_bytes) != src.get("raw_bytes"):
        reasons.append("SOURCE_HASH_MISMATCH")
    revision = src.get("projection_revision")
    if revision != PROJECTION_REVISION or receipt.get("projection_revision") != PROJECTION_REVISION:
        reasons.append("SOURCE_HASH_MISMATCH")
    if src.get("completeness") != COMPLETENESS_COMPLETE or receipt.get("truncated"):
        reasons.append("SOURCE_TRUNCATED")
    if accession is not None and (str(src.get("accession")) != str(accession)
                                  or str(receipt.get("accession")) != str(accession)):
        reasons.append("IDENTITY_UNRESOLVED")
    if str(src.get("doc_id") or "") != str(receipt.get("doc_id") or src.get("doc_id") or ""):
        reasons.append("IDENTITY_UNRESOLVED")
    # clock and listing authority, re-derived from the receipt and the canonical event rather
    # than accepted from the row. Runs on BOTH runtime readers so neither is the lenient one.
    reasons.extend(_source_authority_reasons(obs, receipt, event))
    if reasons:
        return sorted(set(reasons))

    projection = normalized_projection(bytes(raw_bytes).decode("utf-8", "replace"))
    if _sha256(projection) != src.get("body_sha256") or \
            _sha256(projection) != receipt.get("projection_sha256"):
        return ["SOURCE_HASH_MISMATCH"]
    if len(projection) != receipt.get("projection_chars"):
        return ["SOURCE_HASH_MISMATCH"]
    start, end = loc.get("start"), loc.get("end")
    if not isinstance(start, int) or not isinstance(end, int) or isinstance(start, bool) \
            or isinstance(end, bool) or not (0 <= start < end <= len(projection)):
        return ["SOURCE_HASH_MISMATCH"]          # a locator outside the document it cites
    if _sha256(projection[start:end]) != loc.get("excerpt_sha256"):
        return ["SOURCE_HASH_MISMATCH"]
    stored_excerpt = loc.get("excerpt")
    if stored_excerpt is not None and stored_excerpt != projection[start:end]:
        return ["SOURCE_HASH_MISMATCH"]
    if authored is None:
        authored = authored_terms(projection, listing_currency=obs.get("currency"))
    if _semantic_tuple(obs) not in authored:
        # the span and the digests are honest, but this is not a term these bytes say
        return ["SOURCE_HASH_MISMATCH"]
    return []


def evidence_locator(text: str, start: int, end: int, *, doc_id: str = "full_submission_text",
                     section: str | None = None) -> dict:
    """Exact span receipt: where in the body, and a digest of the excerpt itself."""
    excerpt = text[start:end]
    return {
        "doc_id": doc_id,
        "section": section,
        "start": int(start),
        "end": int(end),
        "excerpt": excerpt,
        "excerpt_sha256": _sha256(excerpt),
    }


def observation_id(*, source: dict, field: str, locator: dict, normalized: object,
                   extraction_revision: str = EXTRACTION_REVISION,
                   prior_observation_id: object = None,
                   supersedes_observation_id: object = None,
                   correction_reason: object = None) -> str:
    """Deterministic id over a CLOSED digest shape — CORRECTION LINEAGE INCLUDED.

    Closed on purpose: every element that could change the meaning of the value is inside the
    digest, so a row whose value, span, projection or source object was altered cannot keep its
    id. That is what makes `validate_observation` a real integrity check rather than a
    schema-label check.

    The correction relation is inside the digest for the same reason, and it is the sharper half:
    while `prior_observation_id` / `supersedes_observation_id` / `correction_reason` sat OUTSIDE
    the digest, `link_supersession()` recomputed the id and got the SAME string back — a no-op —
    so a hand-forged relation field kept a valid id, validated True, and pulled an unrelated
    accession's price into a VERIFIED deal (reproduced: offer 250.00, spread +1150%). A relation
    that can change without changing the identity is not an identity; it is an authorization
    boundary anyone can cross.
    """
    payload = _canonical([
        "special_situations.deal_term_observation.v1",
        source.get("accession"),
        source.get("raw_sha256"),
        source.get("body_sha256"),
        source.get("projection_revision"),
        # MEANING-BEARING source fields. These three decide which session a filing-reference
        # premium is drawn from (`acceptance_datetime`), which observation is CURRENT when two
        # compete (`filing_date`), and whether a bare `$` may become USD (`resolved_listing`).
        # While they sat outside the digest a row could rewrite its own clock or listing and
        # keep a valid id. Being inside the digest is necessary and NOT sufficient — a forger
        # can reseal — which is why `rebind_observation()` additionally re-binds each of them to
        # an owner outside the row: the retained acquisition receipt and the canonical event.
        source.get("filing_date"),
        source.get("acceptance_datetime"),
        source.get("resolved_listing"),
        locator.get("doc_id"),
        locator.get("start"),
        locator.get("end"),
        locator.get("excerpt_sha256"),
        field,
        normalized,
        extraction_revision,
        prior_observation_id,
        supersedes_observation_id,
        correction_reason,
    ])
    return _sha256(payload)[:32]


def _relation_of(obs: dict) -> tuple[object, object, object]:
    return (obs.get("prior_observation_id"), obs.get("supersedes_observation_id"),
            obs.get("correction_reason"))


def reseal(obs: dict) -> dict:
    """Re-derive an observation's id from its own current contents.

    The ONE lawful way to mint a row that carries a correction relation. Used by
    `link_supersession()` and by the mutant suite, so a test can build a row that is internally
    sealed yet semantically illegal (dangling predecessor, cycle) and prove the LINEAGE checks —
    not merely the digest — are what refuse it.
    """
    out = dict(obs)
    prior, supersedes, reason = _relation_of(out)
    out["observation_id"] = observation_id(
        source=out.get("source") or {}, field=out.get("field"),
        locator=out.get("locator") or {}, normalized=out.get("normalized"),
        extraction_revision=out.get("extraction_revision") or EXTRACTION_REVISION,
        prior_observation_id=prior, supersedes_observation_id=supersedes,
        correction_reason=reason)
    return out


def validate_observation(obs: object, projection: str | None = None) -> bool:
    """Re-derive the row's identity from its own contents; optionally re-read its span.

    The previous loader trusted a `schema` string and nothing else, so a hand-edited value, a
    moved offset or a forged digest all rode through into published economics. Returns False
    rather than raising: a ledger is untrusted input, and one bad row must degrade the
    projection visibly instead of killing the build.
    """
    if not isinstance(obs, dict) or obs.get("schema") != OBSERVATION_SCHEMA:
        return False
    src, loc = obs.get("source"), obs.get("locator")
    if not isinstance(src, dict) or not isinstance(loc, dict):
        return False
    if obs.get("field") not in OBSERVATION_FIELDS or obs.get("status") not in _STATUS:
        return False
    oid = obs.get("observation_id")
    if not isinstance(oid, str) or not _HEX32.match(oid):
        return False                          # closed id shape: 32 lower-case hex, nothing else
    prior, supersedes, reason = _relation_of(obs)
    for link in (prior, supersedes):
        if link is not None and not (isinstance(link, str) and _HEX32.match(link)):
            return False
    # V1 carries ONE relation per row, so the two link fields must agree, and a relation without
    # a stated reason is an unexplained rewrite of a deal's economics.
    if (prior is None) != (supersedes is None) or prior != supersedes:
        return False
    if prior is not None and not (isinstance(reason, str) and reason.strip()):
        return False
    if prior is None and reason is not None:
        return False
    if prior is not None and prior == oid:
        return False                          # a row cannot supersede itself
    try:
        expected = observation_id(
            source=src, field=obs["field"], locator=loc, normalized=obs.get("normalized"),
            extraction_revision=obs.get("extraction_revision") or EXTRACTION_REVISION,
            prior_observation_id=prior, supersedes_observation_id=supersedes,
            correction_reason=reason)
    except Exception:  # noqa: BLE001
        return False
    if expected != oid:
        return False
    if projection is not None:
        start, end = loc.get("start"), loc.get("end")
        if not isinstance(start, int) or not isinstance(end, int):
            return False
        if _sha256(projection[start:end]) != loc.get("excerpt_sha256"):
            return False
        if _sha256(projection) != src.get("body_sha256"):
            return False
    return True


def validate_lineage(rows: list[dict]) -> list[str]:
    """Lineage integrity across a POPULATION of rows. Returns failure reasons, [] when clean.

    A sealed digest proves a row was not edited; it says nothing about whether the relation it
    asserts is real. These four checks are what the digest cannot do:

    * **existence** — a link naming an id no row carries is dangling, and a dangling link is the
      shape a forger uses to reach outside the evidence set;
    * **same field / same lineage** — a price may only supersede a price;
    * **direction** — a successor must not pre-date its predecessor;
    * **acyclicity** — a cycle has no current term at all, so "newest wins" silently picks one.
    """
    by_id = {}
    for o in rows:
        oid = o.get("observation_id")
        if isinstance(oid, str):
            by_id.setdefault(oid, o)
    reasons: list[str] = []
    edges: dict[str, str] = {}
    for o in rows:
        prior, _, _ = _relation_of(o)
        if prior is None:
            continue
        pred = by_id.get(prior)
        if pred is None:
            reasons.append("INTEGRITY_FAILED")          # dangling predecessor
            continue
        if pred.get("field") != o.get("field"):
            reasons.append("INTEGRITY_FAILED")          # cross-field "correction"
            continue
        if _sort_key(pred) > _sort_key(o):
            reasons.append("INTEGRITY_FAILED")          # a successor older than its predecessor
            continue
        edges[str(o.get("observation_id"))] = prior
    # acyclicity: walk each successor chain, bounded by the population size
    for start in list(edges):
        seen, cur, steps = {start}, edges.get(start), 0
        while cur is not None and steps <= len(edges) + 1:
            if cur in seen:
                reasons.append("INTEGRITY_FAILED")      # cycle
                break
            seen.add(cur)
            cur = edges.get(cur)
            steps += 1
    return sorted(set(reasons))


def _lineage_component(rows: list[dict], accession: str) -> list[dict]:
    """The rows of the EXACT connected lineage containing `accession`, and nothing else.

    The compiler used to admit an entire multi-accession bucket the moment ANY supersession
    matched ANY id in it, so one valid amendment link legalized every other accession that
    happened to be in the same issuer bucket. Reachability is computed over validated
    supersession edges only, in both directions, starting from the requested accession's own
    rows — an accession with no edge chain to it is simply not part of this transaction.
    """
    by_id = {str(o.get("observation_id")): o for o in rows}
    adj: dict[str, set[str]] = {}
    for o in rows:
        prior, _, _ = _relation_of(o)
        oid = str(o.get("observation_id"))
        if prior and prior in by_id:
            adj.setdefault(oid, set()).add(prior)
            adj.setdefault(prior, set()).add(oid)
    frontier = [str(o.get("observation_id")) for o in rows
                if str((o.get("source") or {}).get("accession")) == str(accession)]
    seen = set(frontier)
    while frontier:
        cur = frontier.pop()
        for nxt in adj.get(cur, ()):  # noqa: B007
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    return [o for o in rows if str(o.get("observation_id")) in seen]


def link_supersession(newer: list[dict], older: list[dict]) -> list[dict]:
    """Stamp an EXPLICIT source-linked supersession from `older` onto `newer`, per field.

    Deal lineage is opt-in and evidenced. Sharing an issuer, or carrying an `/A` form type, is
    not a relation — it is a coincidence of the filer, and treating it as one is how two
    unrelated transactions came to share a price.
    """
    by_field = {}
    for o in older:
        if o.get("field") and o.get("observation_id"):
            by_field.setdefault(o["field"], o["observation_id"])
    out = []
    for o in newer:
        prior = by_field.get(o.get("field"))
        if not prior:
            out.append(o)
            continue
        linked = reseal(dict(o, prior_observation_id=prior, supersedes_observation_id=prior,
                             correction_reason=o.get("correction_reason") or "supersedes_prior"))
        out.append(linked)
    return out


def make_observation(*, source: dict, field: str, normalized: object, raw: object,
                     locator: dict, precision: str, status: str = "observed",
                     unit: str | None = None, currency: str | None = None,
                     currency_basis: str | None = None, note: str | None = None,
                     stated_basis: str | None = None,
                     prior_observation_id: str | None = None,
                     supersedes_observation_id: str | None = None,
                     correction_reason: str | None = None,
                     recorded_at: object = None,
                     extraction_method: str = EXTRACTION_METHOD,
                     extraction_revision: str = EXTRACTION_REVISION) -> dict:
    """One immutable field observation. Never mutated — a correction is a NEW record."""
    if field not in OBSERVATION_FIELDS:
        raise ValueError(f"unknown observation field: {field}")
    if status not in _STATUS:
        raise ValueError(f"unknown observation status: {status}")
    oid = observation_id(source=source, field=field, locator=locator, normalized=normalized,
                         extraction_revision=extraction_revision,
                         prior_observation_id=prior_observation_id,
                         supersedes_observation_id=supersedes_observation_id,
                         correction_reason=correction_reason)
    return {
        "schema": OBSERVATION_SCHEMA,
        "observation_id": oid,
        "prior_observation_id": prior_observation_id,
        "supersedes_observation_id": supersedes_observation_id,
        "status": status,
        "field": field,
        "normalized": normalized,
        "raw": raw,
        "unit": unit,
        "currency": currency,
        "currency_basis": currency_basis,
        "stated_basis": stated_basis,
        "precision": precision,
        "note": note,
        "source": dict(source),
        "locator": dict(locator),
        "extraction_method": extraction_method,
        "extraction_revision": extraction_revision,
        "correction_reason": correction_reason,
        # separately versioned receipt time — the only field allowed to move between two
        # otherwise byte-identical rebuilds
        "recorded_at": str(recorded_at) if recorded_at is not None else None,
    }


# ------------------------------------------------------------------ deterministic extraction
#
# Precision over recall, always. A span is published only when it is anchored to an explicit
# per-share phrase AND its neighbourhood is free of the figures that look like an offer price
# but are not: dividends, redemption/exercise/conversion prices, aggregate deal values, notes.
# Declining to extract is a normal, reportable outcome; a confident wrong number is not.

_NUM = r"\d[\d,]*(?:\.\d+)?"

_CCY_MAP = {
    "US$": "USD", "U.S.$": "USD", "USD": "USD",
    "C$": "CAD", "CA$": "CAD", "CAD": "CAD",
    "HK$": "HKD", "HKD": "HKD",
    "A$": "AUD", "AUD": "AUD",
    "S$": "SGD", "SGD": "SGD",
    "NT$": "TWD",
    "£": "GBP", "GBP": "GBP",
    "€": "EUR", "EUR": "EUR",
    "¥": "JPY", "JPY": "JPY",
    "$": None,                     # a bare dollar sign names no currency on its own
}
# longest-first so "US$" wins over "$" and "CAD" over "CA$"
_CCY_ALT = "|".join(re.escape(k) for k in sorted(_CCY_MAP, key=len, reverse=True))

# other-currency markers that make a bare "$" genuinely ambiguous inside one document
_FOREIGN_DOLLAR_RE = re.compile(r"C\$|CA\$|HK\$|A\$|S\$|NT\$|R\$|\bCAD\b|\bHKD\b|\bAUD\b|\bSGD\b|\bTWD\b",
                                re.I)

_SHARE_UNIT = (r"(?:American\s+Depositary\s+(?:Shares?|Receipts?)|ADSs?\b|ADRs?\b|"
               r"ordinary\s+shares?|common\s+shares?|shares?\s+of\s+(?:its\s+)?common\s+stock|"
               r"common\s+stock|shares?)")

# "$25.00 per share", "$25.00 in cash for each share", "US$3.50 per ADS"
_PPS_FWD = re.compile(
    rf"(?P<ccy>{_CCY_ALT})\s*(?P<amt>{_NUM})"
    rf"(?P<gap>[^.;:!?\d]{{0,45}}?)\s*(?:per|for\s+each)\s+(?P<unit>{_SHARE_UNIT})", re.I)
# "purchase price per share of $25.00"
_PPS_REV = re.compile(
    rf"per\s+(?P<unit>{_SHARE_UNIT})(?P<gap>[^.;:!?\d]{{0,45}}?)\s*"
    rf"(?P<ccy>{_CCY_ALT})\s*(?P<amt>{_NUM})", re.I)

# a scale word right after the amount means it was a total, not a per-share price
_SCALE_RE = re.compile(r"^\s*(?:million|billion|bn\b|mm\b|m\b)", re.I)

_NEG_RE = re.compile(
    r"dividend|distribution|redemption|redeem|exercise\s+price|strike\s+price|"
    r"conversion\s+price|warrant|par\s+value|liquidation\s+preference|per\s+unit|"
    r"aggregate|enterprise\s+value|total\s+(?:equity|transaction|deal)\s+value|"
    r"principal\s+amount|interest\s+rate|book\s+value|net\s+asset\s+value|"
    r"subscription\s+price|offering\s+price|initial\s+public\s+offering|private\s+placement|"
    r"\bPIPE\b|stock\s+option|restricted\s+stock|\bRSUs?\b|severance|reverse\s+stock\s+split|"
    r"purchase\s+price\s+of\s+the\s+notes", re.I)
_NEG_WINDOW = 160

_CASH_RE = re.compile(r"\ball[-\s]cash\b|\bin\s+cash\b|\bcash\s+consideration\b|\bfor\s+cash\b",
                      re.I)
_STOCK_RE = re.compile(r"\ball[-\s]stock\b|\bstock[-\s]for[-\s]stock\b|\bexchange\s+ratio\b",
                       re.I)
_MIXED_RE = re.compile(r"cash\s+and\s+(?:shares?|stock)|cash[-\s]and[-\s]stock", re.I)
_CONTINGENT_RE = re.compile(
    r"contingent\s+value\s+right|\bCVRs?\b|(?:stock|cash|mixed)\s+election|"
    r"election\s+to\s+receive|\bcollar\b", re.I)

_CLOSE_ANCHOR = re.compile(
    r"(?:expected|anticipated|projected)\s+to\s+(?:be\s+)?"
    r"(?:close|closed|complete|completed|consummate|consummated|occur)|"
    r"(?:closing|completion|consummation)\s+(?:of\s+the\s+\w+\s+)?is\s+expected|"
    r"expects?\s+to\s+(?:close|complete|consummate)", re.I)
_CLOSE_WINDOW = 160

_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December")
_MONTH_ALT = "|".join(_MONTHS)
_DATE_EXACT = re.compile(rf"(?:on\s+or\s+about\s+)?({_MONTH_ALT})\s+(\d{{1,2}}),?\s+(\d{{4}})", re.I)
_DATE_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_DATE_MONTH = re.compile(rf"({_MONTH_ALT})\s+(?:of\s+)?(\d{{4}})", re.I)
_DATE_QUARTER = re.compile(
    r"(first|second|third|fourth|1st|2nd|3rd|4th)\s+quarter\s+of\s+(\d{4})|"
    r"\bQ([1-4])\s*(?:of\s+)?(\d{4})", re.I)
_DATE_HALF = re.compile(r"(first|second)\s+half\s+of\s+(\d{4})", re.I)
_DATE_VAGUE = re.compile(r"year[-\s]end|coming\s+months|(?:late|early|mid)[-\s]\d{4}|"
                         r"end\s+of\s+(?:the\s+)?year", re.I)

# A filing is not one transaction. A fairness opinion, a background section, a financing
# paragraph or a superseded proposal can each contain cash/CVR/exchange-ratio language that has
# nothing to do with the live deal.
#
# The previous scope was anchored on the FIRST price candidate and then cut at the nearest
# section boundary — which is how a rejected 2025 "$48.00 in cash per share" proposal sitting
# under "Background of the Merger" became the live consideration of a current all-stock merger
# (reproduced: VERIFIED, offer 48.00, spread +20%, consideration `cash`). Anchoring on a price
# means the document decides which transaction it is describing by whichever number appears
# first, which is not transaction identity at all.
#
# Scope is now STRUCTURAL and computed before any price is looked at: the document is split at
# every section cue, sections whose ROLE cannot originate current consideration are
# disqualified outright, and the current transaction is the first admissible section carrying an
# explicit current-transaction anchor. A price outside that section can never be the offer.
_SECTION_CUE = re.compile(
    r"Background\s+of\s+the\b|Opinion\s+of\b|Risk\s+Factors\b|Item\s+\d+(?:\.\d+)?\b|"
    r"Certain\s+Relationships\b|Interests\s+of\b|Prior\s+[Pp]roposals?\b|"
    r"Reasons\s+for\s+the\b|Financing\s+of\s+the\b|Employment\s+Agreements?\b",
    re.I)

# sections that may NEVER originate a current price / currency / consideration / premium / close
_EXCLUDED_SECTION = re.compile(
    r"Background\s+of\s+the\b|Opinion\s+of\b|Risk\s+Factors\b|"
    r"Certain\s+Relationships\b|Interests\s+of\b|Prior\s+[Pp]roposals?\b|"
    r"Financing\s+of\s+the\b|Employment\s+Agreements?\b", re.I)

# An explicit statement that THIS document is describing a live transaction. CLOSED vocabulary:
# every alternative is a phrase a filing uses to assert a transaction, never a proxy for one.
#
# Completeness here is load-bearing in a way it was not before 2026-09-04. While
# `current_transaction_scope()` ended in `(anchored or admissible)[0]`, an unmatched-but-real
# formulation still resolved — through the fallback — so a gap in this vocabulary was invisible.
# Removing that fallback (Sol semantic addendum, carrier edge 1788494850.137529) made the gap
# load-bearing and immediately exposed four corpus filings that state a current transaction in
# words this pattern did not carry: "each common share WILL BE ACQUIRED for $32.00", "holders
# WILL RECEIVE $9.00 in cash per share", and "the PREVIOUSLY ANNOUNCED MERGER providing for
# $21.00". Those are current transactions by any reading; only the phrasing was uncovered.
#
# The distinction that matters, and the one Sol's ruling turns on: widening THIS vocabulary
# still requires an explicit anchor, so scope remains something the document asserts. Restoring
# the fallback would instead make DOCUMENT ORDER the authority. A missing phrase is a recall
# bug; a fallback is a false-precision bug. Add phrases here when a real filing formulation is
# missed — never a heuristic that resolves scope without one.
_CURRENT_TXN_ANCHOR = re.compile(
    r"Agreement\s+and\s+Plan\s+of\b|merger\s+agreement\b|"
    r"(?:will|shall)\s+be\s+(?:converted|cancelled|exchanged|acquired)\b|"
    r"(?:will|shall)\s+receive\b|right\s+to\s+receive\b|"
    r"previously\s+announced\s+(?:merger|transaction|offer|acquisition)\b|"
    r"plan\s+of\s+arrangement\b|tender\s+offer\b|offer\s+to\s+purchase\b|"
    r"all[-\s]cash\b|all[-\s]stock\b|stock[-\s]for[-\s]stock\b|exchange\s+ratio\b|"
    r"business\s+combination\b|combination\b|has\s+agreed\s+to\s+acquire\b|"
    r"agreed\s+to\s+an\b|entered\s+into\b", re.I)

# a stated premium is only meaningful with its comparator; "35% premium" alone is a number
# with no semantics, and it must never stand in for the computed filing-reference premium
_PREMIUM_BASIS_RE = re.compile(
    r"\b(?:to|over|above)\s+the\s+(?P<basis>[^.;:]{0,90}?(?:closing\s+price|close|"
    r"volume[-\s]weighted\s+average\s+price|VWAP|average\s+(?:closing\s+)?price|"
    r"unaffected\s+price)[^.;:]{0,60})", re.I)

_PREMIUM_RE = re.compile(
    r"premium\s+of\s+(?:approximately\s+|about\s+|roughly\s+)?(?P<a>\d{1,4}(?:\.\d+)?)\s*%|"
    r"(?P<b>\d{1,4}(?:\.\d+)?)\s*%\s+premium", re.I)

_QUARTER_WORD = {"first": 1, "1st": 1, "second": 2, "2nd": 2,
                 "third": 3, "3rd": 3, "fourth": 4, "4th": 4}


def document_sections(text: str) -> list[dict]:
    """The document split at every section cue, each span labelled with its role.

    Deterministic and price-independent: the boundaries come from the document's own structure,
    so which spans may originate current economics is settled before a single number is read.
    """
    cuts = [(m.start(), m.group(0)) for m in _SECTION_CUE.finditer(text)]
    bounds = [(0, None)] + cuts
    out: list[dict] = []
    for i, (start, cue) in enumerate(bounds):
        end = bounds[i + 1][0] if i + 1 < len(bounds) else len(text)
        if end <= start:
            continue
        out.append({"start": start, "end": end, "cue": cue,
                    "excluded": bool(cue and _EXCLUDED_SECTION.match(cue))})
    return out


def current_transaction_scope(text: str) -> tuple[int, int] | None:
    """The ONE evidence span the current transaction's terms may be read from, or None.

    The first admissible section carrying an explicit current-transaction ANCHOR — and nothing
    else. Never a disqualified section, never "wherever the first price happens to be", and
    never the first admissible section merely because it came first.

    That last fallback used to be `(anchored or admissible)[0]`, which reads as conservative and
    is not: an unanchored section is not a proven current transaction, so selecting it makes
    DOCUMENT ORDER the authority for which deal a published price belongs to. A filing whose
    only per-share number sits in an unanchored `Item` — a prior proposal, a competing bid, a
    financing recital — would publish that number as the current offer. Low recall is lawful
    here; publishing terms from an unanchored section is not, which is why the honest answer is
    None and the caller's `TRANSACTION_SCOPE_UNRESOLVED` decline.
    """
    admissible = [sec for sec in document_sections(text) if not sec["excluded"]]
    if not admissible:
        return None
    anchored = [sec for sec in admissible
                if _CURRENT_TXN_ANCHOR.search(text, sec["start"], sec["end"])]
    if not anchored:
        return None
    return anchored[0]["start"], anchored[0]["end"]


def _neg_context(text: str, start: int, end: int) -> str | None:
    """The disqualifying phrase near a candidate span, if any."""
    lo, hi = max(0, start - _NEG_WINDOW), min(len(text), end + _NEG_WINDOW)
    m = _NEG_RE.search(text[lo:hi])
    return m.group(0) if m else None


def _unit_of(raw_unit: str) -> str:
    u = raw_unit.lower()
    return "ADS" if ("depositary" in u or u.startswith("ads") or u.startswith("adr")) else "share"


def _price_candidates(text: str) -> list[dict]:
    """Every per-share money span that survives the negative lexicon, with exact offsets."""
    out: list[dict] = []
    seen: set[tuple[int, int]] = set()
    for rx in (_PPS_FWD, _PPS_REV):
        for m in rx.finditer(text):
            span = (m.start(), m.end())
            if span in seen:
                continue
            if _SCALE_RE.match(text[m.end("amt"):m.end("amt") + 12]):
                continue                                   # "$3.2 billion ... per share"
            neg = _neg_context(text, m.start(), m.end())
            if neg:
                continue                                   # dividend / redemption / aggregate …
            val = _num(m.group("amt").replace(",", ""))
            if val is None or val <= 0:
                continue
            seen.add(span)
            out.append({
                "value": val,
                "ccy_token": m.group("ccy"),
                "unit": _unit_of(m.group("unit")),
                "start": m.start(),
                "end": m.end(),
            })
    return out


def _resolve_currency(token: str, text: str, listing_currency: str | None) -> tuple[str | None, str]:
    """ISO currency for a matched money token, plus HOW it was established.

    A bare "$" is admitted only where it cannot be anything else: the document carries no other
    dollar qualifier and the security is listed in USD. Anything less returns None — the mutant
    this refuses is a `.TO` deal priced in C$ compared against a USD close.
    """
    iso = _CCY_MAP.get(token.upper() if token.upper() in _CCY_MAP else token)
    if iso:
        return iso, "explicit_token"
    if _FOREIGN_DOLLAR_RE.search(text):
        return None, "bare_dollar_document_ambiguous"
    if (listing_currency or "").upper() == "USD":
        return "USD", "bare_dollar_unambiguous_usd_listing"
    return None, "bare_dollar_unresolved_listing"


def _close_candidates(text: str) -> list[dict]:
    """Expected-close spans anchored to an explicit closing expectation, with a precision label.

    A date elsewhere in the filing (the agreement date, a record date, a fiscal year end) is not
    a close date, so only text following a closing anchor is even looked at.
    """
    out: list[dict] = []
    for anchor in _CLOSE_ANCHOR.finditer(text):
        lo = anchor.end()
        window = text[lo:lo + _CLOSE_WINDOW]
        for rx, precision in ((_DATE_ISO, PRECISION_EXACT_DATE), (_DATE_EXACT, PRECISION_EXACT_DATE),
                              (_DATE_QUARTER, PRECISION_QUARTER), (_DATE_HALF, PRECISION_HALF),
                              (_DATE_MONTH, PRECISION_MONTH), (_DATE_VAGUE, PRECISION_TEXT)):
            m = rx.search(window)
            if not m:
                continue
            norm = _normalize_close(m, precision)
            if norm is None:
                continue
            out.append({
                "normalized": norm,
                "precision": precision,
                "start": anchor.start(),
                "end": lo + m.end(),
            })
            break                       # finest precision available at this anchor wins
    return out


def _normalize_close(m: re.Match, precision: str) -> str | None:
    """Normalized close value. A window stays a WINDOW — never resolved to a day."""
    try:
        if precision == PRECISION_EXACT_DATE:
            if m.re is _DATE_ISO:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            else:
                mo = _MONTHS.index(m.group(1).capitalize()) + 1
                d, y = int(m.group(2)), int(m.group(3))
            if not (1 <= mo <= 12 and 1 <= d <= calendar.monthrange(y, mo)[1]):
                return None
            return f"{y:04d}-{mo:02d}-{d:02d}"
        if precision == PRECISION_QUARTER:
            if m.group(1):
                q, y = _QUARTER_WORD.get(m.group(1).lower()), int(m.group(2))
            else:
                q, y = int(m.group(3)), int(m.group(4))
            return f"{y:04d}-Q{q}" if q else None
        if precision == PRECISION_HALF:
            h = 1 if m.group(1).lower() == "first" else 2
            return f"{int(m.group(2)):04d}-H{h}"
        if precision == PRECISION_MONTH:
            mo = _MONTHS.index(m.group(1).capitalize()) + 1
            return f"{int(m.group(2)):04d}-{mo:02d}"
        return m.group(0).strip().lower()
    except (ValueError, IndexError, AttributeError):
        return None


def extract_term_observations(text: str | None, *, source: dict,
                              listing_currency: str | None = None,
                              recorded_at: object = None) -> list[dict]:
    """Immutable term observations for one filing projection. Declines rather than guesses.

    Every field resolves inside ONE transaction evidence scope anchored on the price span, so
    unrelated cash, CVR or exchange-ratio language elsewhere in the document cannot classify the
    live deal. Conflicts are preserved, not resolved.
    """
    if not text:
        return []
    obs: list[dict] = []
    doc_id = source.get("doc_id") or "normalized_projection"
    scope_bounds = current_transaction_scope(text)
    if scope_bounds is None:
        return []                     # no admissible section: nothing here can be current
    lo, hi = scope_bounds

    def _emit(field, normalized, raw, locator, precision, status="observed", **kw):
        obs.append(make_observation(source=source, field=field, normalized=normalized, raw=raw,
                                    locator=locator, precision=precision, status=status,
                                    recorded_at=recorded_at, **kw))

    # ---- price per share, read ONLY inside the current-transaction scope
    all_cands = _price_candidates(text)
    cands = [c for c in all_cands if lo <= c["start"] and c["end"] <= hi]
    outside = [c for c in all_cands if c not in cands]
    share_vals = {c["value"] for c in cands if c["unit"] == "share"}
    ads_vals = {c["value"] for c in cands if c["unit"] == "ADS"}
    conflicted = len(share_vals) > 1 or (share_vals and ads_vals and share_vals != ads_vals)
    for c in cands:
        loc = evidence_locator(text, c["start"], c["end"], doc_id=doc_id)
        iso, basis = _resolve_currency(c["ccy_token"], text, listing_currency)
        status = "ambiguous" if conflicted else "observed"
        note = "conflicting_per_share_values" if conflicted else None
        _emit("price_per_share", c["value"], loc["excerpt"], loc, PRECISION_EXACT_NUMERIC,
              status=status, unit=c["unit"], currency=iso, currency_basis=basis, note=note)
        _emit("currency", iso, c["ccy_token"], loc, PRECISION_TEXT,
              status="observed" if iso else "ambiguous", currency=iso, currency_basis=basis,
              note=None if iso else basis)
    # Out-of-scope prices are RECORDED, never compiled: a rejected prior proposal is real
    # evidence about the filing and must stay visible, but `deferred` rows are not live terms,
    # so nothing here can originate the current offer.
    for c in outside:
        loc = evidence_locator(text, c["start"], c["end"], doc_id=doc_id)
        _emit("price_per_share", c["value"], loc["excerpt"], loc, PRECISION_EXACT_NUMERIC,
              status="deferred", unit=c["unit"],
              note="outside_current_transaction_scope")

    scope = text[lo:hi]

    # ---- consideration, inside the transaction scope only
    contingent = _CONTINGENT_RE.search(scope)
    mixed = _MIXED_RE.search(scope)
    cash, stock = _CASH_RE.search(scope), _STOCK_RE.search(scope)
    con_m = contingent or mixed or cash or stock
    if con_m:
        if contingent:
            value = "contingent"
        elif mixed or (cash and stock):
            value = "cash+stock"
        elif cash:
            value = "cash"
        else:
            value = "stock"
        loc = evidence_locator(text, lo + con_m.start(), lo + con_m.end(), doc_id=doc_id)
        _emit("consideration", value, loc["excerpt"], loc, PRECISION_TEXT)

    # ---- stated premium: publishable ONLY with its captured comparator
    stated = []
    for pm in _PREMIUM_RE.finditer(scope):
        pct = _num(pm.group("a") or pm.group("b"))
        if pct is None:
            continue
        tail = scope[pm.end():pm.end() + 200]
        bm = _PREMIUM_BASIS_RE.search(tail)
        if not bm:
            continue                       # a percentage with no comparator has no semantics
        stated.append((round(pct, 4), " ".join(bm.group("basis").split()),
                       lo + pm.start(), lo + pm.end() + bm.end()))
    distinct = {(v, b) for v, b, _, _ in stated}
    if len(distinct) == 1:
        v, b, a_start, a_end = stated[0]
        loc = evidence_locator(text, a_start, min(len(text), a_end), doc_id=doc_id)
        _emit("stated_premium_pct", v, loc["excerpt"], loc, PRECISION_EXACT_NUMERIC,
              note="stated_by_filing", stated_basis=b)
    # 0 comparators, or 2+ disagreeing ones, publish nothing: the filing's claim is unusable,
    # which is separate from — and never a substitute for — our computed numbers.

    # ---- expected close, inside the transaction scope
    closes = [dict(c, start=c["start"] + lo, end=c["end"] + lo) for c in _close_candidates(scope)]
    exact = {c["normalized"] for c in closes if c["precision"] == PRECISION_EXACT_DATE}
    coarse = {c["normalized"] for c in closes if c["precision"] != PRECISION_EXACT_DATE}
    if len(exact) > 1 or (not exact and len(coarse) > 1):
        chosen, status, note = closes, "ambiguous", "conflicting_expected_close"
    elif exact:
        chosen = [c for c in closes if c["precision"] == PRECISION_EXACT_DATE][:1]
        status, note = "observed", None
    else:
        chosen, status, note = closes[:1], "observed", None
    for c in chosen:
        loc = evidence_locator(text, c["start"], c["end"], doc_id=doc_id)
        _emit("expected_close", c["normalized"], loc["excerpt"], loc, c["precision"],
              status=status, note=note)
    return obs


# ------------------------------------------------------------------ current-term compiler

def _sort_key(o: dict) -> tuple:
    src = o.get("source") or {}
    return (str(src.get("filing_date") or ""), str(src.get("accession") or ""))


def compile_current_terms(observations: list[dict] | None, *, accession: object = None) -> dict:
    """Deterministically choose the current term set, failing closed on identity and integrity.

    Four rules the previous versions broke:

    1. **Every row is re-validated.** A schema label is not integrity. A row whose value, span,
       projection, source receipt OR correction relation was altered no longer matches its own
       closed digest, and the whole compile degrades to INTEGRITY_FAILED rather than quietly
       publishing the survivors.
    2. **An accession is an isolated transaction.** Grouping by issuer CIK let two unrelated
       deals share a price. Multiple accessions may only form one lineage through an EXPLICIT
       source-linked supersession; an `/A` form or a shared filer proves nothing.
    3. **Only the EXACT connected lineage of the requested accession is compiled.** Pass
       `accession` — the Special Situations event id — and the compile walks validated
       supersession edges out from that accession's own rows. The previous version admitted the
       whole multi-accession bucket the moment ANY supersession matched ANY id in it, so one
       lawful amendment link legalized an unrelated third accession sitting in the same bucket.
       A lineage is not a bucket that happens to contain one real edge.
    4. **A truncated projection cannot be conflict-free.** Absence of a second price inside a
       cut body is not evidence, so the compile carries the truncation forward and the reducer
       refuses to call it VERIFIED.
    """
    raw_rows = [o for o in (observations or []) if isinstance(o, dict) and o.get("field")]
    if not raw_rows:
        return {"status": "unavailable", "reasons": ["TERM_NOT_FOUND"], "terms": {},
                "evidence": {}, "accession": None, "amendment_chain": []}

    invalid = [o for o in raw_rows if not validate_observation(o)]
    rows = [o for o in raw_rows if o not in invalid]
    rows = [o for o in rows
            if (o.get("source") or {}).get("body_sha256") and (o.get("source") or {}).get("accession")]
    unbound = len(raw_rows) - len(invalid) - len(rows)
    if invalid:
        return {"status": "ambiguous", "reasons": ["INTEGRITY_FAILED"], "terms": {},
                "evidence": {}, "accession": None, "amendment_chain": [],
                "integrity": {"rows": len(raw_rows), "invalid": len(invalid)}}
    lineage_reasons = validate_lineage(rows)
    if lineage_reasons:
        return {"status": "ambiguous", "reasons": lineage_reasons, "terms": {},
                "evidence": {}, "accession": None, "amendment_chain": [],
                "integrity": {"rows": len(raw_rows), "lineage": "invalid"}}
    if accession is not None:
        rows = _lineage_component(rows, str(accession))
    if not rows:
        return {"status": "unavailable",
                "reasons": ["SOURCE_BYTES_UNAVAILABLE"] if unbound else ["TERM_NOT_FOUND"],
                "terms": {}, "evidence": {}, "accession": None, "amendment_chain": []}

    # --- transaction identity: one accession, or one explicitly linked lineage
    superseded = {o.get("supersedes_observation_id") for o in rows if o.get("supersedes_observation_id")}
    accessions = {str((o.get("source") or {}).get("accession")) for o in rows}
    chain = sorted({(str((o.get("source") or {}).get("filing_date") or ""),
                     str((o.get("source") or {}).get("accession") or "")) for o in rows})
    if len(accessions) > 1:
        ids = {o.get("observation_id") for o in rows}
        linked = {o.get("supersedes_observation_id") for o in rows} & ids
        if not linked:
            return {"status": "ambiguous", "reasons": ["IDENTITY_UNRESOLVED"], "terms": {},
                    "evidence": {}, "accession": None,
                    "amendment_chain": [{"filing_date": d, "accession": a} for d, a in chain],
                    "identity": {"accessions": sorted(accessions),
                                 "reason": "no explicit source-linked supersession"}}

    terms: dict = {}
    evidence: dict = {}
    reasons: list[str] = []
    truncated = any((o.get("source") or {}).get("completeness") == COMPLETENESS_TRUNCATED
                    for o in rows)
    unknown_completeness = any((o.get("source") or {}).get("completeness") == COMPLETENESS_UNKNOWN
                               for o in rows)

    for field in OBSERVATION_FIELDS:
        same = [o for o in rows if o.get("field") == field
                and o.get("observation_id") not in superseded]
        if not same:
            continue
        newest = max(_sort_key(o) for o in same)
        current = [o for o in same if _sort_key(o) == newest]
        if any(o.get("status") == "retracted" for o in current):
            reasons.append("RETRACTED")
            continue
        if any(o.get("status") == "ambiguous" for o in current):
            reasons.append("TERM_AMBIGUOUS")
            continue
        live = [o for o in current if o.get("status") == "observed"]
        if not live:
            continue
        values = {_canonical(o.get("normalized")) for o in live}
        if len(values) > 1:
            reasons.append("CONFLICTING_AMENDMENT" if len({_sort_key(o) for o in live}) > 1
                           else "TERM_AMBIGUOUS")
            continue
        win = live[0]
        terms[field] = win.get("normalized")
        src = win.get("source") or {}
        evidence[field] = {
            "observation_id": win.get("observation_id"),
            "accession": src.get("accession"),
            "source_url": src.get("source_url"),
            "raw_sha256": src.get("raw_sha256"),
            "body_sha256": src.get("body_sha256"),
            "projection_revision": src.get("projection_revision"),
            "completeness": src.get("completeness"),
            "acceptance_datetime": src.get("acceptance_datetime"),
            "locator": {k: v for k, v in (win.get("locator") or {}).items() if k != "excerpt"},
            "precision": win.get("precision"),
            "unit": win.get("unit"),
            "currency_basis": win.get("currency_basis"),
            "extraction_revision": win.get("extraction_revision"),
        }
        if field == "price_per_share":
            terms["price_unit"] = win.get("unit")
            terms["price_currency_basis"] = win.get("currency_basis")
            if win.get("currency"):
                terms.setdefault("_price_currency", win.get("currency"))
        if field == "expected_close":
            terms["expected_close_precision"] = win.get("precision")
        if field == "stated_premium_pct":
            terms["stated_premium_basis"] = win.get("stated_basis")

    if terms.get("_price_currency") and not terms.get("currency"):
        terms["currency"] = terms.pop("_price_currency")
    terms.pop("_price_currency", None)
    if truncated:
        reasons.append("SOURCE_TRUNCATED")
    terms["source_completeness"] = (COMPLETENESS_TRUNCATED if truncated else
                                    COMPLETENESS_UNKNOWN if unknown_completeness else
                                    COMPLETENESS_COMPLETE)
    if unbound:
        reasons.append("SOURCE_BYTES_UNAVAILABLE")
    status = "ambiguous" if [r for r in reasons if r != "SOURCE_TRUNCATED"] else (
        "observed" if len([k for k in terms if not k.startswith("source_")]) else "unavailable")
    if status == "unavailable" and not reasons:
        reasons = ["TERM_NOT_FOUND"]
    return {"status": status, "reasons": sorted(set(reasons)), "terms": terms,
            "evidence": evidence, "accession": chain[-1][1] if chain else None,
            "amendment_chain": [{"filing_date": d, "accession": a} for d, a in chain]}


# ------------------------------------------------------------------ typed price inputs

def price_input(*, ticker: object, session: object, value: object, currency: object,
                basis: object = None, source_artifact: object = None,
                sessions_behind: int | None = None, expected_session: object = None,
                calendar_id: object = None, recorded_at: object = None,
                calendar_owner: object = None, calendar_revision: object = None,
                calendar_blob: object = None, artifact_sha256: object = None,
                artifact_bytes: object = None, column: object = None,
                listing: object = None, writer_owner: object = None,
                writer_blob: object = None,
                sessions_unique_monotonic: object = None,
                values_finite_positive: object = None,
                read_validated: object = None) -> dict:
    """One price observation with the clocks and receipts that make it usable or not.

    There is NO basis default. `basis="close_raw"` used to be this function's own fallback, so
    the false-raw fiction lived in the PURE owner and not only in the producer: any caller that
    simply omitted the basis received a receipt asserting a raw close it had never proven.
    Unstated is now unstated, and unstated is `PRICE_BASIS_UNRESOLVED`.

    Everything here is a CLAIM. `validate_price_receipt()` re-derives every part of it that can
    be re-derived — expected session, sessions behind, digest shape, closed vocabularies — so a
    caller-authored `sessions_behind=0` beside a 2020 session is caught by arithmetic rather
    than trusted. The two facts a pure owner cannot recompute (whether the series' sessions were
    unique and monotonic, and whether its values were finite and positive) are carried as
    explicit named booleans the producer must set from the artifact it actually read.
    """
    return {
        "ticker": str(ticker) if ticker is not None else None,
        "listing": str(listing) if listing is not None else None,
        "session": str(session) if session is not None else None,
        "expected_session": str(expected_session) if expected_session is not None else None,
        "sessions_behind": None if sessions_behind is None else int(sessions_behind),
        "value": _num(value),
        "currency": str(currency).upper() if currency else None,
        "basis": str(basis) if basis else None,
        "column": str(column) if column is not None else None,
        "calendar_id": str(calendar_id) if calendar_id is not None else None,
        "calendar_owner": str(calendar_owner) if calendar_owner is not None else None,
        "calendar_revision": str(calendar_revision) if calendar_revision is not None else None,
        "calendar_blob": str(calendar_blob) if calendar_blob is not None else None,
        "source_artifact": str(source_artifact) if source_artifact is not None else None,
        "artifact_sha256": str(artifact_sha256) if artifact_sha256 is not None else None,
        "artifact_bytes": None if artifact_bytes is None else int(artifact_bytes),
        "writer_owner": str(writer_owner) if writer_owner is not None else None,
        "writer_blob": str(writer_blob) if writer_blob is not None else None,
        "sessions_unique_monotonic": (None if sessions_unique_monotonic is None
                                      else bool(sessions_unique_monotonic)),
        "values_finite_positive": (None if values_finite_positive is None
                                   else bool(values_finite_positive)),
        "read_validated": None if read_validated is None else bool(read_validated),
        "recorded_at": str(recorded_at) if recorded_at is not None else None,
    }


def resolve_us_listing(ticker: object) -> str | None:
    """The exact canonical U.S. cash-equity root, or None.

    V1's whole boundary. A dot or a dash means a foreign suffix (`ARX.TO`, `0700.HK`) or a share
    class (`BRK.B`) — both outside V1 — and the old producer's `raw.split(".")[0]` fallback let a
    foreign target be priced from a same-root U.S. column with the currency then inferred from
    the selected column rather than the resolved listing. Nothing about this function derives a
    CURRENCY: USD comes from the resolved listing's own Yahoo store semantics, never from ticker
    syntax.
    """
    t = str(ticker or "").strip().upper()
    return t if t and _US_ROOT.fullmatch(t) else None


def validate_price_receipt(p: dict | None, *, now_utc, ticker: object = None) -> list[str]:
    """Independently re-derive a price receipt's truth. Returns failure reasons, [] when clean.

    The reducer used to check only that certain receipt KEYS were present, trust the caller's
    `sessions_behind`, never compare `session` against `expected_session`, and accept any string
    as a basis. Measured consequences at head a88c12f2: `session=2020-01-02` +
    `expected_session=2026-06-01` + `sessions_behind=0` reached VERIFIED; so did
    `basis="totally_made_up_basis"`; so did a genuinely five-sessions-stale close whose caller
    simply declared zero.

    Everything below is recomputed from `now_utc` through the approved calendar owner
    (`lib/nyse_calendar`, pure date arithmetic — no IO) or checked against a closed vocabulary.
    """
    if not p:
        return ["PRICE_MISSING"]
    from lib import nyse_calendar

    reasons: list[str] = []
    val = _num(p.get("value"))
    if val is None or val <= 0:
        reasons.append("PRICE_MISSING")

    # --- closed vocabularies: basis, column, writer, calendar, artifact shape
    if p.get("basis") not in PRICE_BASES:
        reasons.append("PRICE_BASIS_UNRESOLVED")
    if p.get("column") not in PRICE_COLUMNS:
        reasons.append("PRICE_BASIS_UNRESOLVED")
    if p.get("writer_owner") != PRICE_WRITER_OWNER or p.get("writer_blob") != PRICE_WRITER_BLOB:
        reasons.append("PRICE_BASIS_UNRESOLVED")
    if p.get("calendar_owner") != CALENDAR_OWNER or p.get("calendar_blob") != CALENDAR_BLOB \
            or p.get("calendar_revision") != CALENDAR_REVISION:
        reasons.append("CALENDAR_RECEIPT_MISSING")
    if p.get("calendar_id") != US_CALENDAR_ID or p.get("listing") != US_CALENDAR_ID:
        reasons.append("LISTING_UNSUPPORTED")

    # --- exact artifact identity: a path is a location, a digest+length is an identity
    digest = p.get("artifact_sha256")
    if not (isinstance(digest, str) and _HEX64.match(digest)):
        reasons.append("PRICE_RECEIPT_INVALID")
    nbytes = p.get("artifact_bytes")
    if not (isinstance(nbytes, int) and not isinstance(nbytes, bool) and nbytes > 0):
        reasons.append("PRICE_RECEIPT_INVALID")

    # --- listing / ticker / artifact agreement
    listing_ticker = resolve_us_listing(p.get("ticker"))
    if listing_ticker is None:
        reasons.append("LISTING_UNSUPPORTED")
    if ticker is not None and resolve_us_listing(ticker) != listing_ticker:
        reasons.append("LISTING_UNSUPPORTED")
    artifact = str(p.get("source_artifact") or "")
    if not PRICE_ARTIFACT_RE.match(artifact) or (
            listing_ticker and artifact != f"yahoo/{listing_ticker}.parquet"):
        reasons.append("PRICE_BASIS_UNRESOLVED")

    # --- the producer's own read validation of the artifact it opened
    if p.get("read_validated") is not True or p.get("sessions_unique_monotonic") is not True \
            or p.get("values_finite_positive") is not True:
        reasons.append("PRICE_RECEIPT_INVALID")

    # --- clocks, recomputed rather than accepted
    session = _iso_date(p.get("session"))
    if session is None or not _ISO_DAY.match(str(p.get("session") or "")):
        return sorted(set(reasons + ["PRICE_RECEIPT_INVALID"]))
    try:
        expected = nyse_calendar.expected_last_session(now_utc)
        behind = int(nyse_calendar.sessions_behind(session, now_utc))
    except Exception:  # noqa: BLE001
        return sorted(set(reasons + ["CALENDAR_RECEIPT_MISSING"]))
    if str(p.get("expected_session") or "") != expected.isoformat():
        reasons.append("PRICE_RECEIPT_INVALID")     # the receipt's own expected session is wrong
    if p.get("sessions_behind") != behind:
        reasons.append("PRICE_RECEIPT_INVALID")     # a caller-authored freshness conclusion
    if session > expected:
        # not "stale" — a receipt asserting a session the market has not finished is invalid,
        # and an invalid clock publishes no number at all
        reasons.extend(["PRICE_RECEIPT_INVALID", "PRICE_STALE"])
    elif behind > 0:
        reasons.append("PRICE_STALE")               # latest must be EXACTLY expected for VERIFIED
    return sorted(set(reasons))


def _usable(p: dict | None) -> bool:
    return bool(p and _num(p.get("value")) and _num(p.get("value")) > 0 and p.get("session"))


# ------------------------------------------------------------------ the one reducer

def _result(state: str, reasons: list[str], warnings: list[str] | None = None, **extra) -> dict:
    """One closed result shape.

    `reasons` is the FAILURE channel and `warnings` is the informational one. They are separate
    because a VERIFIED row used to ship `REFERENCE_SESSION_UNRESOLVED` inside its own failure
    list — a state that reads, to every consumer, as a verified number that also failed. The
    invariant is enforced here rather than trusted: a VERIFIED row carries no failure reason.
    """
    if state not in QUALITY_STATES:
        raise ValueError(f"unknown quality state: {state}")
    reasons = sorted(set(reasons))
    warnings = sorted(set(warnings or []))
    bad = [r for r in reasons if r not in REASONS]
    if bad:
        raise ValueError(f"unknown failure reason(s): {bad}")
    bad_w = [w for w in warnings if w not in WARNINGS]
    if bad_w:
        raise ValueError(f"unknown warning(s): {bad_w}")
    if state == QUALITY_VERIFIED and reasons:
        raise ValueError(f"a VERIFIED row cannot carry failure reasons: {reasons}")
    out = {
        "schema": "special_situations.cash_deal_economics.v1",
        "quality_state": state,
        "reasons": reasons,
        "warnings": warnings,
        "formula_revision": FORMULA_REVISION,
        "extraction_revision": EXTRACTION_REVISION,
        "is_context_only": True,
        "is_signal": False,
        "orderable": False,
        "offer_price": None, "currency": None, "price_unit": None,
        "stated_premium_pct": None, "stated_premium_basis": None,
        "filing_reference_premium_pct": None, "reference_session": None,
        "reference_price": None, "reference_source": None,
        "live_gross_spread_pct": None, "live_session": None, "live_price": None,
        "live_source": None, "sessions_behind": None, "price_basis": None,
        "live_artifact_sha256": None, "expected_session": None, "calendar_owner": None,
        "calendar_revision": None, "acceptance_datetime": None, "source_completeness": None,
        "calc_now_utc": None,
        "expected_close": None, "expected_close_precision": None,
        "days_to_close": None, "annualized_pct": None,
        "calc_asof": None, "evidence": {}, "accession": None,
    }
    out.update(extra)
    return out


_REQUIRED = object()


def reduce_cash_deal(compiled: dict | None, *, now_utc=_REQUIRED, category: object = None,
                     stage: object = None, live_price: dict | None = None,
                     reference_price: dict | None = None, market_session: date | None = None,
                     ticker: object = None) -> dict:
    """The single closed eligibility + calculation contract. Every consumer reads THIS.

    `now_utc` is REQUIRED and explicit. Host-local `date.today()` is not a market clock, and a
    build that cannot state its own time cannot state how stale a price is.

    The filing-reference premium needs the SEC acceptance / system-availability timestamp from
    the source bytes: a date-only `date_filed` cannot separate a premarket filing (reference =
    prior session) from an after-close one (reference = that day's session), so date-only input
    yields REFERENCE_SESSION_UNRESOLVED rather than a plausible wrong comparison.
    """
    if now_utc is _REQUIRED:
        raise TypeError("reduce_cash_deal() requires an explicit now_utc market clock")
    compiled = compiled or {}
    terms = dict(compiled.get("terms") or {})
    evidence = compiled.get("evidence") or {}
    accession = compiled.get("accession")
    asof = market_session or (now_utc.date() if hasattr(now_utc, "date") else now_utc)
    base = {"evidence": evidence, "accession": accession, "calc_asof": asof.isoformat(),
            "calc_now_utc": now_utc.isoformat() if hasattr(now_utc, "isoformat") else str(now_utc),
            "source_completeness": terms.get("source_completeness"),
            "expected_close": terms.get("expected_close"),
            "expected_close_precision": terms.get("expected_close_precision"),
            "stated_premium_pct": _num(terms.get("stated_premium_pct")),
            "stated_premium_basis": terms.get("stated_premium_basis")}

    if category is not None and str(category) not in ARB_CATEGORIES:
        return _result(QUALITY_INELIGIBLE, ["INELIGIBLE_CATEGORY"], **base)
    if stage and str(stage).strip().lower() in TERMINAL_STAGES:
        return _result(QUALITY_TERMINAL, ["TERMINAL_DEAL"], **base)

    status = compiled.get("status")
    compiled_reasons = list(compiled.get("reasons") or [])
    if status == "unavailable":
        return _result(QUALITY_SOURCE_UNAVAILABLE, compiled_reasons or ["TERM_NOT_FOUND"], **base)
    if status == "ambiguous":
        state = (QUALITY_SOURCE_UNAVAILABLE if "INTEGRITY_FAILED" in compiled_reasons
                 else QUALITY_AMBIGUOUS)
        return _result(state, compiled_reasons or ["TERM_AMBIGUOUS"], **base)

    consideration = str(terms.get("consideration") or "").lower()
    if consideration != "cash":
        return _result(QUALITY_NOT_FIXED_CASH, ["NOT_FIXED_CASH"], **base)

    offer = _num(terms.get("price_per_share"))
    if offer is None or offer <= 0:
        return _result(QUALITY_SOURCE_UNAVAILABLE, ["TERM_NOT_FOUND"], **base)
    if (terms.get("price_unit") or "share") != "share":
        return _result(QUALITY_AMBIGUOUS, ["TERM_AMBIGUOUS"], **base)
    currency = (terms.get("currency") or "").upper() or None
    if not currency:
        return _result(QUALITY_AMBIGUOUS, ["IDENTITY_UNRESOLVED"], **base)
    base.update({"offer_price": round(offer, 4), "currency": currency,
                 "price_unit": terms.get("price_unit") or "share"})

    # V1 admits exactly one listing family, and USD comes from that resolved listing — never
    # from ticker syntax, and never from whichever price column happened to be selected.
    if ticker is not None and resolve_us_listing(ticker) is None:
        return _result(QUALITY_AMBIGUOUS, ["LISTING_UNSUPPORTED"], **base)
    if currency != "USD":
        return _result(QUALITY_AMBIGUOUS, ["LISTING_UNSUPPORTED"], **base)

    if not _usable(live_price):
        return _result(QUALITY_CALCULATION_UNAVAILABLE, ["PRICE_MISSING"], **base)

    # Every receipt claim that CAN be re-derived is re-derived, before any number is published.
    receipt_reasons = validate_price_receipt(live_price, now_utc=now_utc, ticker=ticker)
    if (live_price.get("currency") or "").upper() != currency:
        receipt_reasons = sorted(set(receipt_reasons + ["CURRENCY_MISMATCH"]))
    behind = None
    try:
        from lib import nyse_calendar as _cal
        _sess = _iso_date(live_price.get("session"))
        behind = int(_cal.sessions_behind(_sess, now_utc)) if _sess else None
    except Exception:  # noqa: BLE001
        behind = None
    # A receipt that is merely BEHIND is still a true receipt: the spread stays visible and
    # simply never enters the ordered book. A receipt that does not re-derive publishes no
    # number at all — there is nothing to be visible about.
    stale_only = receipt_reasons == ["PRICE_STALE"]
    if receipt_reasons and not stale_only:
        base.update({"live_session": live_price.get("session"),
                     "price_basis": live_price.get("basis"),
                     "sessions_behind": behind,
                     "expected_session": live_price.get("expected_session"),
                     "live_source": live_price.get("source_artifact"),
                     "live_artifact_sha256": live_price.get("artifact_sha256")})
        state = (QUALITY_AMBIGUOUS if "CURRENCY_MISMATCH" in receipt_reasons
                 else QUALITY_CALCULATION_UNAVAILABLE)
        return _result(state, receipt_reasons, **base)

    if reference_price and _usable(reference_price):
        if (reference_price.get("basis") or None) != (live_price.get("basis") or None):
            return _result(QUALITY_CALCULATION_UNAVAILABLE, ["PRICE_BASIS_UNRESOLVED"], **base)
        if (reference_price.get("currency") or "").upper() != currency:
            return _result(QUALITY_AMBIGUOUS, ["CURRENCY_MISMATCH"], **base)

    lp = _num(live_price.get("value"))
    reasons: list[str] = [r for r in compiled_reasons if r == "SOURCE_TRUNCATED"]
    warnings: list[str] = []
    base.update({
        "live_price": round(lp, 4), "live_session": live_price.get("session"),
        "live_source": live_price.get("source_artifact"),
        "live_artifact_sha256": live_price.get("artifact_sha256"),
        "sessions_behind": behind,                     # RECOMPUTED, not the receipt's claim
        "expected_session": live_price.get("expected_session"),
        "calendar_owner": live_price.get("calendar_owner"),
        "calendar_revision": live_price.get("calendar_revision"),
        "price_basis": live_price.get("basis"),
        "live_gross_spread_pct": round((offer / lp - 1.0) * 100, 2),
    })

    # filing-reference premium: needs an exact acceptance time AND a session strictly before it
    acceptance = None
    for ev in evidence.values():
        if ev.get("acceptance_datetime"):
            acceptance = ev["acceptance_datetime"]
            break
    ref_session = _iso_date((reference_price or {}).get("session"))
    avail_session = _iso_date(acceptance) if acceptance else None
    # An exact acceptance MOMENT is what makes a reference session defensible. A same-day
    # session is valid for an after-close filing and invalid for a premarket one, and only the
    # timestamp can tell those apart — which is why a date-only value resolves nothing at all.
    acceptance_has_time = bool(acceptance) and "T" in str(acceptance)
    if acceptance_has_time and reference_price and _usable(reference_price) and ref_session and \
            avail_session and ref_session <= avail_session:
        rp = _num(reference_price.get("value"))
        base.update({
            "filing_reference_premium_pct": round((offer / rp - 1.0) * 100, 2),
            "reference_session": reference_price.get("session"),
            "reference_price": round(rp, 4),
            "reference_source": reference_price.get("source_artifact"),
            "acceptance_datetime": acceptance,
        })
    else:
        warnings.append("REFERENCE_SESSION_UNRESOLVED")

    if terms.get("stated_premium_pct") is not None and not terms.get("stated_premium_basis"):
        warnings.append("STATED_PREMIUM_BASIS_UNRESOLVED")

    precision = terms.get("expected_close_precision")
    if precision == PRECISION_EXACT_DATE:
        days = days_to_close(terms.get("expected_close"), asof)
        if days:
            base["days_to_close"] = int(days)
            base["annualized_pct"] = round(((offer / lp) ** (365.0 / int(days)) - 1.0) * 100, 1)
        else:
            warnings.append("DATE_PRECISION_INSUFFICIENT")
    else:
        warnings.append("DATE_PRECISION_INSUFFICIENT")

    # a cut body cannot be declared conflict-free, so it cannot be VERIFIED
    if "SOURCE_TRUNCATED" in reasons or \
            terms.get("source_completeness") != COMPLETENESS_COMPLETE:
        return _result(QUALITY_CALCULATION_UNAVAILABLE,
                       sorted(set(reasons + ["SOURCE_TRUNCATED"])), warnings, **base)
    if stale_only:
        return _result(QUALITY_STALE_PRICE, sorted(set(reasons + ["PRICE_STALE"])),
                       warnings, **base)
    if reasons:
        return _result(QUALITY_CALCULATION_UNAVAILABLE, reasons, warnings, **base)

    result = _result(QUALITY_VERIFIED, [], warnings, **base)
    result["orderable"] = result["annualized_pct"] is not None
    if result["annualized_pct"] is not None and abs(result["annualized_pct"]) >= 1000.0:
        result["extreme_value"] = True
    return result


# ------------------------------------------------------------------ one ordered projection

def select_ordered_context(rows: list[dict] | None, *, block: str = "arb",
                           limit: int = 5) -> tuple[list[dict], dict]:
    """The single ordered risk-arb projection + its visible degraded census.

    `mastermind_emit()` and `special_sits_intel.build_context_feed()` both call this, which is
    what ends the divergence where one consumer excluded a row the other ranked first.
    """
    rows = list(rows or [])
    counts: dict = {"considered": 0, "verified": 0, "ordered": 0, "excluded": 0, "by_state": {}}
    ordered: list[dict] = []
    for r in rows:
        econ = r.get(block)
        if not isinstance(econ, dict) or not econ.get("quality_state"):
            continue
        counts["considered"] += 1
        state = econ["quality_state"]
        counts["by_state"][state] = counts["by_state"].get(state, 0) + 1
        if state == QUALITY_VERIFIED:
            counts["verified"] += 1
        if econ.get("orderable") and econ.get("annualized_pct") is not None:
            ordered.append(r)
        else:
            counts["excluded"] += 1
    # null annualized values are never coerced to zero — they are not in this list at all
    ordered.sort(key=lambda r: (r.get(block) or {}).get("annualized_pct"), reverse=True)
    ordered = ordered[:limit]
    counts["ordered"] = len(ordered)
    return ordered, counts


def context_row(row: dict, *, block: str = "arb") -> dict:
    """Projection of one ordered row — every number carries its receipts."""
    e = row.get(block) or {}
    return {
        "ticker": row.get("ticker"), "company": row.get("company"),
        "category": row.get("category"),
        "offer_price": e.get("offer_price"), "currency": e.get("currency"),
        "stated_premium_pct": e.get("stated_premium_pct"),
        "filing_reference_premium_pct": e.get("filing_reference_premium_pct"),
        "reference_session": e.get("reference_session"),
        "live_gross_spread_pct": e.get("live_gross_spread_pct"),
        "live_session": e.get("live_session"), "live_price": e.get("live_price"),
        "sessions_behind": e.get("sessions_behind"), "price_basis": e.get("price_basis"),
        "days_to_close": e.get("days_to_close"), "annualized_pct": e.get("annualized_pct"),
        "expected_close": e.get("expected_close"),
        "expected_close_precision": e.get("expected_close_precision"),
        "quality_state": e.get("quality_state"), "reasons": e.get("reasons") or [],
        "warnings": e.get("warnings") or [],
        "accession": e.get("accession"), "source_url": (e.get("evidence") or {})
            .get("price_per_share", {}).get("source_url"),
        "formula_revision": e.get("formula_revision"),
        "calc_asof": e.get("calc_asof"),
        "display_order_basis": "annualized_pct",
        "is_context_only": True, "is_signal": False,
        "extreme_value": bool(e.get("extreme_value")),
    }


# ------------------------------------------------------------------ retained helpers
#
# `parse_terms` survives as CANDIDATE/CONTEXT ONLY: the model lane may still describe a deal,
# but nothing it produces reaches a published number without an observation above.

_CONSIDERATION = {"cash", "stock", "cash+stock", "other", "contingent"}


def parse_terms(obj: object) -> dict:
    """Normalize an LLM `deal_terms` object. CANDIDATE ONLY — never numeric authority."""
    if not isinstance(obj, dict):
        return {}
    out: dict = {}
    pps = _num(obj.get("price_per_share"))
    if pps is not None and pps > 0:
        out["price_per_share"] = pps
    cur = obj.get("currency")
    if cur:
        out["currency"] = str(cur).strip().upper()[:3]
    con = str(obj.get("consideration") or "").strip().lower()
    if con in _CONSIDERATION:
        out["consideration"] = con
    prem = _num(obj.get("premium_pct"))
    if prem is not None:
        out["premium_pct"] = round(prem, 1)
    ec = obj.get("expected_close")
    if isinstance(ec, str) and re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", ec.strip()):
        out["expected_close"] = ec.strip()
    bf = _num(obj.get("break_fee_musd"))
    if bf is not None and bf >= 0:
        out["break_fee_musd"] = bf
    out["_candidate_only"] = True
    return out


def days_to_close(expected_close: str | None, asof: date | None = None) -> int | None:
    """Calendar days to an EXACT observed close date. A YYYY-MM window returns None.

    The removed month-end resolution is the defect this vertical exists to kill: it turned an
    unobserved day into a precise denominator and then compounded a spread over it.
    """
    s = str(expected_close or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return None
    d = _iso_date(s)
    if d is None:
        return None
    delta = (d - (asof or _today())).days
    return delta if delta > 0 else None


_SUFFIX_CCY = {
    "": "USD", "TO": "CAD", "V": "CAD", "L": "GBP", "T": "JPY", "HK": "HKD", "AX": "AUD",
    "NS": "INR", "BO": "INR", "DE": "EUR", "PA": "EUR", "MI": "EUR", "AS": "EUR", "MC": "EUR",
    "BR": "EUR", "LS": "EUR", "IR": "EUR", "HE": "EUR", "VI": "EUR", "KS": "KRW", "TW": "TWD",
    "ST": "SEK", "OL": "NOK", "SW": "CHF", "CO": "DKK",
}


def market_currency(ticker: object) -> str | None:
    """Quote currency for a resolved listing, or None when the listing is not resolved.

    NOT ON THE VERIFIED PATH. Retained for the display/candidate lanes only. It answers from
    ticker SYNTAX — "USD" for any dotless symbol, so `BABA` and `ADS1` both came back USD — and
    the narrow V1 verified path derives USD from the resolved listing's own Yahoo store instead
    (`resolve_us_listing` + `validate_price_receipt`). Nothing here may gate a published number.

    The old default returned "USD" for anything it did not recognise — including the empty
    string. A raw collector event does not carry the engine-resolved listing, so that default
    silently minted a US listing for unresolved and foreign names and let a bare `$` become an
    observed USD price. Unresolved is now a state, not a guess.
    """
    t = str(ticker or "").strip()
    if not t:
        return None
    if "." in t:
        return _SUFFIX_CCY.get(t.rsplit(".", 1)[-1].upper())     # unknown suffix -> None
    return "USD" if re.fullmatch(r"[A-Za-z][A-Za-z0-9\-]{0,9}", t) else None


def _today() -> date:
    return datetime.now().date()
