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
})

OBSERVATION_FIELDS = ("price_per_share", "currency", "consideration",
                      "stated_premium_pct", "expected_close")

# date precision labels, coarsest last; only `exact_date` may drive days-to-close
PRECISION_EXACT_DATE = "exact_date"
PRECISION_MONTH = "month"
PRECISION_QUARTER = "quarter"
PRECISION_HALF = "half_year"
PRECISION_TEXT = "text_only"
PRECISION_EXACT_NUMERIC = "exact_numeric"

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
                      doc_id: object = None, body_truncated: bool = False) -> dict:
    """Identity of the exact bytes an observation was read from.

    `body_sha256` binds the observation to content, not to a URL: an accession whose body is
    re-fetched and differs must not silently keep the old numbers (SOURCE_HASH_MISMATCH).
    """
    digest = body_sha256 or (_sha256(body) if body is not None else None)
    return {
        "cik": str(cik) if cik is not None else None,
        "form_type": str(form_type) if form_type is not None else None,
        "accession": str(accession) if accession is not None else None,
        "filing_date": str(filing_date) if filing_date is not None else None,
        "source_url": str(source_url) if source_url is not None else None,
        "body_sha256": digest,
        "body_chars": len(body) if body is not None else None,
        "body_truncated": bool(body_truncated),
        "acquired_at": str(acquired_at) if acquired_at is not None else None,
        "doc_id": str(doc_id) if doc_id is not None else "full_submission_text",
    }


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
                   extraction_revision: str = EXTRACTION_REVISION) -> str:
    """Deterministic id over (bytes, field, span, value, revision).

    Byte-stability is the whole point: re-running an identical build re-derives identical ids,
    so an append-only ledger de-duplicates instead of growing a duplicate row every night.
    """
    payload = _canonical({
        "accession": source.get("accession"),
        "body_sha256": source.get("body_sha256"),
        "doc_id": locator.get("doc_id"),
        "start": locator.get("start"),
        "end": locator.get("end"),
        "excerpt_sha256": locator.get("excerpt_sha256"),
        "field": field,
        "normalized": normalized,
        "revision": extraction_revision,
    })
    return _sha256(payload)[:32]


def make_observation(*, source: dict, field: str, normalized: object, raw: object,
                     locator: dict, precision: str, status: str = "observed",
                     unit: str | None = None, currency: str | None = None,
                     currency_basis: str | None = None, note: str | None = None,
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
                         extraction_revision=extraction_revision)
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

_PREMIUM_RE = re.compile(
    r"premium\s+of\s+(?:approximately\s+|about\s+|roughly\s+)?(?P<a>\d{1,4}(?:\.\d+)?)\s*%|"
    r"(?P<b>\d{1,4}(?:\.\d+)?)\s*%\s+premium", re.I)

_QUARTER_WORD = {"first": 1, "1st": 1, "second": 2, "2nd": 2,
                 "third": 3, "3rd": 3, "fourth": 4, "4th": 4}


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
    """Immutable term observations for one filing body. Declines rather than guesses.

    Conflicts are PRESERVED, not resolved: two disagreeing spans both come back with
    `status="ambiguous"` so the receipt shows what the filing actually said.
    """
    if not text:
        return []
    obs: list[dict] = []

    def _emit(field, normalized, raw, locator, precision, status="observed", **kw):
        obs.append(make_observation(source=source, field=field, normalized=normalized, raw=raw,
                                    locator=locator, precision=precision, status=status,
                                    recorded_at=recorded_at, **kw))

    # ---- price per share (and the currency that names it)
    cands = _price_candidates(text)
    share_vals = {c["value"] for c in cands if c["unit"] == "share"}
    ads_vals = {c["value"] for c in cands if c["unit"] == "ADS"}
    # per-ADS and per-share wording for different amounts means the security identity is not
    # resolved by the document alone — refuse rather than pick the one that fits the ticker
    conflicted = len(share_vals) > 1 or (share_vals and ads_vals and share_vals != ads_vals)
    for c in cands:
        loc = evidence_locator(text, c["start"], c["end"], doc_id=source.get("doc_id") or
                               "full_submission_text")
        iso, basis = _resolve_currency(c["ccy_token"], text, listing_currency)
        status = "ambiguous" if conflicted else "observed"
        note = "conflicting_per_share_values" if conflicted else None
        _emit("price_per_share", c["value"], loc["excerpt"], loc, PRECISION_EXACT_NUMERIC,
              status=status, unit=c["unit"], currency=iso, currency_basis=basis, note=note)
        _emit("currency", iso, c["ccy_token"], loc, PRECISION_TEXT,
              status="observed" if iso else "ambiguous", currency=iso, currency_basis=basis,
              note=None if iso else basis)

    # ---- consideration
    contingent = _CONTINGENT_RE.search(text)
    mixed = _MIXED_RE.search(text)
    cash, stock = _CASH_RE.search(text), _STOCK_RE.search(text)
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
        loc = evidence_locator(text, con_m.start(), con_m.end(),
                               doc_id=source.get("doc_id") or "full_submission_text")
        _emit("consideration", value, loc["excerpt"], loc, PRECISION_TEXT)

    # ---- stated premium (a claim the filing makes, never a substitute for a computed number)
    pm = _PREMIUM_RE.search(text)
    if pm:
        pct = _num(pm.group("a") or pm.group("b"))
        if pct is not None:
            loc = evidence_locator(text, pm.start(), min(len(text), pm.end() + 120),
                                   doc_id=source.get("doc_id") or "full_submission_text")
            _emit("stated_premium_pct", round(pct, 4), loc["excerpt"], loc,
                  PRECISION_EXACT_NUMERIC, note="stated_by_filing")

    # ---- expected close
    closes = _close_candidates(text)
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
        loc = evidence_locator(text, c["start"], c["end"],
                               doc_id=source.get("doc_id") or "full_submission_text")
        _emit("expected_close", c["normalized"], loc["excerpt"], loc, c["precision"],
              status=status, note=note)
    return obs


# ------------------------------------------------------------------ current-term compiler

def _sort_key(o: dict) -> tuple:
    src = o.get("source") or {}
    return (str(src.get("filing_date") or ""), str(src.get("accession") or ""))


def compile_current_terms(observations: list[dict] | None) -> dict:
    """Deterministically choose the current term set under accession/amendment precedence.

    Append-only history is never edited: a later accession SUPERSEDES an earlier value for a
    field, a `retracted` observation removes it, and two disagreeing observations inside the
    same accession are a conflict the compiler refuses to resolve.
    """
    raw_rows = [o for o in (observations or []) if isinstance(o, dict) and o.get("field")]
    # an observation that cannot name its bytes is not source-bound, whatever else it carries:
    # dropping the digest or the accession must NOT leave a green machine context behind
    rows = [o for o in raw_rows
            if (o.get("source") or {}).get("body_sha256") and (o.get("source") or {}).get("accession")]
    unbound = len(raw_rows) - len(rows)
    if not rows:
        return {"status": "unavailable",
                "reasons": ["SOURCE_BYTES_UNAVAILABLE"] if unbound else ["TERM_NOT_FOUND"],
                "terms": {}, "evidence": {}, "accession": None, "amendment_chain": []}
    chain = sorted({(str((o.get("source") or {}).get("filing_date") or ""),
                     str((o.get("source") or {}).get("accession") or "")) for o in rows})
    terms: dict = {}
    evidence: dict = {}
    reasons: list[str] = []
    superseded = {o.get("supersedes_observation_id") for o in rows if o.get("supersedes_observation_id")}

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
        evidence[field] = {
            "observation_id": win.get("observation_id"),
            "accession": (win.get("source") or {}).get("accession"),
            "source_url": (win.get("source") or {}).get("source_url"),
            "body_sha256": (win.get("source") or {}).get("body_sha256"),
            "locator": {k: v for k, v in (win.get("locator") or {}).items() if k != "excerpt"},
            "precision": win.get("precision"),
            "unit": win.get("unit"),
            "currency_basis": win.get("currency_basis"),
            "extraction_revision": win.get("extraction_revision"),
        }
        if field == "price_per_share":
            terms["price_unit"] = win.get("unit")
            terms["price_currency_basis"] = win.get("currency_basis")
            if win.get("currency") and "currency" not in terms:
                terms.setdefault("_price_currency", win.get("currency"))
        if field == "expected_close":
            terms["expected_close_precision"] = win.get("precision")
        if field == "stated_premium_pct":
            terms["stated_premium_basis"] = win.get("raw")

    if terms.get("_price_currency") and not terms.get("currency"):
        terms["currency"] = terms.pop("_price_currency")
    terms.pop("_price_currency", None)
    if unbound:
        reasons.append("SOURCE_BYTES_UNAVAILABLE")
    status = "ambiguous" if reasons else ("observed" if terms else "unavailable")
    if status == "unavailable" and not reasons:
        reasons = ["TERM_NOT_FOUND"]
    return {"status": status, "reasons": sorted(set(reasons)), "terms": terms,
            "evidence": evidence, "accession": chain[-1][1] if chain else None,
            "amendment_chain": [{"filing_date": d, "accession": a} for d, a in chain]}


# ------------------------------------------------------------------ typed price inputs

def price_input(*, ticker: object, session: object, value: object, currency: object,
                basis: object = "close_raw", source_artifact: object = None,
                sessions_behind: int | None = None, expected_session: object = None,
                calendar_id: object = None, recorded_at: object = None) -> dict:
    """One price observation with the clocks that make it usable or not.

    `sessions_behind` is supplied by the caller that owns the exchange calendar — a pure module
    must not invent one. A bare "last non-null row" carries none of this, which is exactly why
    it was never freshness proof.
    """
    return {
        "ticker": str(ticker) if ticker is not None else None,
        "session": str(session) if session is not None else None,
        "expected_session": str(expected_session) if expected_session is not None else None,
        "sessions_behind": None if sessions_behind is None else int(sessions_behind),
        "value": _num(value),
        "currency": str(currency).upper() if currency else None,
        "basis": str(basis) if basis else None,
        "calendar_id": str(calendar_id) if calendar_id is not None else None,
        "source_artifact": str(source_artifact) if source_artifact is not None else None,
        "recorded_at": str(recorded_at) if recorded_at is not None else None,
    }


def _usable(p: dict | None) -> bool:
    return bool(p and _num(p.get("value")) and _num(p.get("value")) > 0 and p.get("session"))


# ------------------------------------------------------------------ the one reducer

def _result(state: str, reasons: list[str], **extra) -> dict:
    if state not in QUALITY_STATES:
        raise ValueError(f"unknown quality state: {state}")
    bad = [r for r in reasons if r not in REASONS]
    if bad:
        raise ValueError(f"unknown failure reason(s): {bad}")
    out = {
        "schema": "special_situations.cash_deal_economics.v1",
        "quality_state": state,
        "reasons": sorted(set(reasons)),
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
        "expected_close": None, "expected_close_precision": None,
        "days_to_close": None, "annualized_pct": None,
        "calc_asof": None, "evidence": {}, "accession": None,
    }
    out.update(extra)
    return out


def reduce_cash_deal(compiled: dict | None, *, category: object = None, stage: object = None,
                     live_price: dict | None = None, reference_price: dict | None = None,
                     availability_session: object = None, asof: date | None = None,
                     ticker: object = None) -> dict:
    """The single closed eligibility + calculation contract. Every consumer reads THIS.

    Four separately named numbers, never collapsed into one "premium":
      stated_premium_pct            what the filing itself claims;
      filing_reference_premium_pct  offer vs the last session strictly BEFORE SEC availability;
      live_gross_spread_pct         offer vs the latest usable close;
      annualized_pct                only when an exact close DATE was directly observed.
    """
    compiled = compiled or {}
    terms = dict(compiled.get("terms") or {})
    evidence = compiled.get("evidence") or {}
    accession = compiled.get("accession")
    asof = asof or _today()
    base = {"evidence": evidence, "accession": accession, "calc_asof": asof.isoformat(),
            "expected_close": terms.get("expected_close"),
            "expected_close_precision": terms.get("expected_close_precision"),
            "stated_premium_pct": _num(terms.get("stated_premium_pct")),
            "stated_premium_basis": terms.get("stated_premium_basis")}

    if category is not None and str(category) not in ARB_CATEGORIES:
        return _result(QUALITY_INELIGIBLE, ["INELIGIBLE_CATEGORY"], **base)
    if stage and str(stage).strip().lower() in TERMINAL_STAGES:
        return _result(QUALITY_TERMINAL, ["TERMINAL_DEAL"], **base)

    status = compiled.get("status")
    if status == "unavailable":
        return _result(QUALITY_SOURCE_UNAVAILABLE,
                       list(compiled.get("reasons") or ["TERM_NOT_FOUND"]), **base)
    if status == "ambiguous":
        return _result(QUALITY_AMBIGUOUS,
                       list(compiled.get("reasons") or ["TERM_AMBIGUOUS"]), **base)

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
        return _result(QUALITY_AMBIGUOUS, ["TERM_AMBIGUOUS"], **base)
    base.update({"offer_price": round(offer, 4), "currency": currency,
                 "price_unit": terms.get("price_unit") or "share"})

    if not _usable(live_price):
        return _result(QUALITY_CALCULATION_UNAVAILABLE, ["PRICE_MISSING"], **base)
    if (live_price.get("currency") or "").upper() != currency:
        return _result(QUALITY_AMBIGUOUS, ["CURRENCY_MISMATCH"], **base)

    live_session = _iso_date(live_price.get("session"))
    if live_session and live_session > asof:
        base.update({"live_session": live_price.get("session"),
                     "price_basis": live_price.get("basis")})
        return _result(QUALITY_CALCULATION_UNAVAILABLE, ["PRICE_STALE"],
                       price_clock="future_session", **base)

    if reference_price and _usable(reference_price):
        if (reference_price.get("basis") or None) != (live_price.get("basis") or None):
            return _result(QUALITY_CALCULATION_UNAVAILABLE, ["PRICE_BASIS_UNRESOLVED"], **base)
        if (reference_price.get("currency") or "").upper() != currency:
            return _result(QUALITY_AMBIGUOUS, ["CURRENCY_MISMATCH"], **base)

    lp = _num(live_price.get("value"))
    reasons: list[str] = []
    base.update({
        "live_price": round(lp, 4), "live_session": live_price.get("session"),
        "live_source": live_price.get("source_artifact"),
        "sessions_behind": live_price.get("sessions_behind"),
        "price_basis": live_price.get("basis"),
        "live_gross_spread_pct": round((offer / lp - 1.0) * 100, 2),
    })

    # filing-reference premium — the reference session must be strictly BEFORE the first
    # verified SEC availability session, or the number is not a pre-filing comparison at all
    avail = _iso_date(availability_session)
    ref_session = _iso_date((reference_price or {}).get("session"))
    if reference_price and _usable(reference_price) and avail and ref_session and ref_session < avail:
        rp = _num(reference_price.get("value"))
        base.update({
            "filing_reference_premium_pct": round((offer / rp - 1.0) * 100, 2),
            "reference_session": reference_price.get("session"),
            "reference_price": round(rp, 4),
            "reference_source": reference_price.get("source_artifact"),
        })
    else:
        reasons.append("REFERENCE_SESSION_UNRESOLVED")

    # days-to-close + annualization: exact observed DATE only. A month, quarter or half-year
    # stays a window; it is never resolved to a day and then compounded.
    precision = terms.get("expected_close_precision")
    if precision == PRECISION_EXACT_DATE:
        days = days_to_close(terms.get("expected_close"), asof)
        if days:
            base["days_to_close"] = int(days)
            base["annualized_pct"] = round(((offer / lp) ** (365.0 / int(days)) - 1.0) * 100, 1)
        else:
            reasons.append("DATE_PRECISION_INSUFFICIENT")
    else:
        reasons.append("DATE_PRECISION_INSUFFICIENT")

    behind = live_price.get("sessions_behind")
    if behind is not None and int(behind) > 0:
        return _result(QUALITY_STALE_PRICE, reasons + ["PRICE_STALE"], **base)

    result = _result(QUALITY_VERIFIED, reasons, **base)
    # orderable == fully verified AND exact-date AND current price. Nothing else may be
    # coerced into the annualized-ordered list.
    result["orderable"] = result["annualized_pct"] is not None
    # visible disclosure, never a clamp: an extreme value is published with its receipts so a
    # human can audit it, rather than silently banded away
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


def market_currency(ticker: object) -> str:
    """Quote currency for a (possibly exchange-suffixed) ticker; USD for a bare US symbol."""
    t = str(ticker or "")
    suf = t.rsplit(".", 1)[-1].upper() if "." in t else ""
    return _SUFFIX_CCY.get(suf, "USD")


def _today() -> date:
    return datetime.now().date()
