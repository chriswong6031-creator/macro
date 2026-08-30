"""Hermetic foundation for the FMS congressional-notification source triad.

Mirrors ``collectors/dod_budget.py``'s pure/live split (D6-A pattern): this
module is deterministic and has no network or object-storage code.  It knows
how to detect and normalize the source-native transmittal identity, parse the
three official surfaces' frozen text grammars (State PM-Bureau articles and
listing, DSCA historical articles, Federal Register 36(b) raw text), and
build/validate the receipt and observation rows the live acquisition adapter
(``collectors/fms_notifications_live.py``) durably writes.

Frozen law this module enforces (see
``research/defense_intelligence/DEFENSE_D6B1_FMS_IMPLEMENTATION_SPEC_2026-08-25.md``
and the D6-B0 freeze it amends):

* Stage is always ``congressional_notification`` — this module never computes
  a later stage or any review-period arithmetic.
* Identity is primarily the source-native transmittal number
  (``fms:transmittal:<yy-n>``); the fallback identity
  (``fms:urlpath:<sha256(path)[:24]>``) is used only when no surface prints a
  transmittal label anywhere.
* Amendment notices (letter-suffixed FR brackets, e.g. ``26-1C``) are
  classified and excluded — they never mint or touch a case. Correction
  notices attach to an existing case by exact transmittal; they never mint.
* A missing amount is always ``null``, never ``0``. Unknown layout fails
  closed to ``null`` plus a typed parse state — nothing here is LLM-derived.
"""
from __future__ import annotations

import hashlib
import html as _html
import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit

FMS_RECEIPT_CONTRACT = "government_revenue.fms_collection_receipt.v1"
FMS_OBSERVATION_CONTRACT = "government_revenue.fms_observation.v1"
SCHEMA_VERSION = "1.0.0"
IMMUTABLE_R2_PREFIX = "government-revenue/fms/sha256/"

SOURCE_SURFACES = ("state", "dsca", "federal_register")
OBSERVATION_KINDS = (
    "listing_article", "certification_pdf", "fr_raw_text",
    "fr_correction", "retraction_observed",
)
TRANSPORTS = ("cli", "browser_in_page_fetch_staged", "cli_residential_staged")


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------


def _canonical_json(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False, default=str,
    )


def _sha256(value: bytes | str) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def _sha256_json(value: object) -> str:
    return _sha256(_canonical_json(value))


def _utc_iso(value: str | datetime | None = None) -> str:
    if value is None:
        parsed = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must be offset-aware")
    return parsed.astimezone(timezone.utc).isoformat()


def _text(value: Any, *, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"missing {label}")
    return text


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value)


def _clean_text(value: str) -> str:
    unescaped = _html.unescape(_strip_tags(value))
    return re.sub(r"\s+", " ", unescaped).strip()


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------

_UNIT_MULTIPLIER = {"billion": 1_000_000_000, "million": 1_000_000}


def parse_money_amount(raw: str, unit: str) -> int:
    """Parse one printed ``$X (billion|million)`` figure to whole USD.

    Unknown/blank input is a hard refusal; the caller is responsible for
    treating "no match at all" (never call this) as the null value — this
    function never returns 0 for missing input (D6-B amount honesty, T10).
    """
    unit_key = str(unit or "").strip().casefold()
    if unit_key not in _UNIT_MULTIPLIER:
        raise ValueError(f"unrecognized FMS money unit: {unit!r}")
    number_text = str(raw or "").strip().replace(",", "")
    if not number_text:
        raise ValueError("missing FMS money amount")
    number = float(number_text)
    value = int(round(number * _UNIT_MULTIPLIER[unit_key]))
    if value <= 0:
        raise ValueError("FMS money amount must be positive")
    return value


# ---------------------------------------------------------------------------
# Identity: transmittal detection + normalization (freeze §6, spec §5)
# ---------------------------------------------------------------------------

# Unicode dash class: ASCII hyphen, hyphen (U+2010), non-breaking hyphen
# (U+2011), figure dash (U+2012), en dash (U+2013), em dash (U+2014),
# horizontal bar (U+2015) — spec §5 "tolerates unicode dash variants".
_DASH_CLASS = "\\-\u2010\u2011\u2012\u2013\u2014\u2015"
TRANSMITTAL_RE = re.compile(
    rf"transmittal\s*(?:no\.?|number|num\.?|#)?\s*[:\-]?\s*(\d{{2}})\s*[{_DASH_CLASS}]\s*(\d{{1,3}})",
    re.IGNORECASE,
)
FR_BRACKET_RE = re.compile(r"\[\s*Transmittal No\.\s*([A-Z0-9]+[A-Z0-9\-]*)\s*\]", re.IGNORECASE)
_ORIGINAL_BRACKET_RE = re.compile(r"^\d{2}-\d{1,3}$")


def normalize_transmittal(year: str, sequence: str) -> str:
    """Normalize ``<yy>-<n>``: year kept as printed, sequence's leading zeros stripped."""
    year_text = _text(year, label="transmittal year")
    if not re.fullmatch(r"\d{2}", year_text):
        raise ValueError(f"invalid FMS transmittal year: {year!r}")
    seq_text = _text(sequence, label="transmittal sequence")
    if not re.fullmatch(r"\d{1,3}", seq_text):
        raise ValueError(f"invalid FMS transmittal sequence: {sequence!r}")
    return f"{year_text}-{int(seq_text)}"


def detect_transmittals(text: str) -> dict[str, Any]:
    """Detect every distinct normalized transmittal number in free text.

    Returns ``{"transmittals": [...], "conflicted": bool}``; ``conflicted``
    is true when more than one distinct number is detected (freeze §6:
    "never a guess", T-series mis-key/conflict discipline).
    """
    found: list[str] = []
    for year, seq in TRANSMITTAL_RE.findall(text or ""):
        normalized = normalize_transmittal(year, seq)
        if normalized not in found:
            found.append(normalized)
    return {"transmittals": found, "conflicted": len(found) > 1}


def classify_fr_bracket(bracket: str) -> str:
    """Classify one FR ``[Transmittal No. ...]`` bracket value.

    ``original`` when the bracket is exactly ``YY-N`` (digits only);
    ``amendment`` for any letter-suffixed variant (``26-0G``, ``0M-25``, the
    "phantom 26-0" trap family) — spec §2/§5.
    """
    text = _text(bracket, label="FR transmittal bracket")
    return "original" if _ORIGINAL_BRACKET_RE.fullmatch(text) else "amendment"


def case_key_for_transmittal(transmittal: str) -> str:
    """Mint the case key for one transmittal, normalizing before minting.

    Defense-in-depth (spec §11b.10): every current caller already passes a
    value that has been through :func:`normalize_transmittal` (which strips
    leading zeros), but this function re-normalizes its own input so it can
    never mint two distinct case keys for the same transmittal (``26-013``
    and ``26-13``) regardless of what a future or indirect caller passes.
    """
    text = _text(transmittal, label="transmittal number")
    match = re.fullmatch(r"(\d{2})-(\d{1,3})", text)
    if not match:
        raise ValueError(f"invalid normalized FMS transmittal: {transmittal!r}")
    year, sequence = match.groups()
    return f"fms:transmittal:{normalize_transmittal(year, sequence)}"


def canonical_url_path(url: str) -> str:
    """Lowercased path, no scheme/host/query/fragment, one trailing slash."""
    parsed = urlsplit(_text(url, label="FMS source URL"))
    path = parsed.path.casefold()
    if not path.endswith("/"):
        path = path + "/"
    return path


def case_key_fallback(url: str) -> str:
    digest = _sha256(canonical_url_path(url))
    return f"fms:urlpath:{digest[:24]}"


# Formal-name honorific prefixes a source may or may not print ahead of a
# country's short name (e.g. title-prefix "Sweden" vs FR purchaser
# "Government of Sweden" for the SAME country, spec §5 amended customer_
# country precedence). Country-equality comparisons (mis-key guard,
# fallback<->recovery collision) compare the honorific-STRIPPED core so two
# differently-formal printings of the same country are never treated as a
# disagreement; the verbatim field values themselves are never altered.
_COUNTRY_HONORIFIC_PREFIXES = (
    "Government of", "Kingdom of", "Republic of", "Sultanate of",
    "Principality of", "State of", "Federation of", "Commonwealth of",
    "Emirate of", "Union of", "The",
)


def _country_core(text: str) -> str:
    normalized = text.strip()
    for prefix in _COUNTRY_HONORIFIC_PREFIXES:
        if normalized.casefold().startswith(prefix.casefold() + " "):
            normalized = normalized[len(prefix) + 1:]
            break
    return normalized.strip().casefold()


def check_mis_key(existing_country: str | None, new_country: str | None) -> bool:
    """True when two observations bound to the same case key disagree on country.

    Freeze §6 mis-key guard: a differing ``customer_country`` on an existing
    case key flags ``conflicted`` for review — never auto-merged, never
    silently accepted. Compares honorific-stripped cores (see
    ``_country_core``) so "Sweden" (title-prefix) and "Government of Sweden"
    (FR purchaser) for the same country are never a false mis-key.
    """
    if not existing_country or not new_country:
        return False
    return _country_core(existing_country) != _country_core(new_country)


def fallback_collision(country_a: str | None, country_b: str | None) -> bool:
    """True when a fallback-identity case and a recovery case share a country.

    Freeze §6 split-risk / spec §2 fallback<->recovery collision law: this
    NEVER auto-merges the two cases — it only signals that both must be
    flagged ``conflicted`` for review. Compares honorific-stripped cores so
    "Singapore" (title-prefix) and "Government of Singapore" (FR purchaser)
    are correctly recognized as the same country (census instance: FR 26-24
    <-> singapore-hellfire-missiles).
    """
    if not country_a or not country_b:
        return False
    return _country_core(country_a) == _country_core(country_b)


# ---------------------------------------------------------------------------
# State PM-Bureau article + listing grammar (spec §5)
# ---------------------------------------------------------------------------

_STATE_TITLE_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_STATE_PUBLISH_DATE_RE = re.compile(
    r'class="article-meta__publish-date">([^<]+)<', re.IGNORECASE
)
_MODIFIED_TIME_RE = re.compile(
    r'article:modified_time"?\s*content="([^"]+)"', re.IGNORECASE
)
_STATE_VALUE_RE = re.compile(
    r"(?:total\s+)?estimated\s+(?:total\s+)?(?:program\s+)?cost\s+"
    r"(?:for\s+the\s+case\s+)?(?:is|of)\s+(?:up\s+to\s+)?\$([\d,.]+)\s*(billion|million)",
    re.IGNORECASE,
)
# Title-prefix country grammar (amended, implementation-frozen, spec §5): the
# verbatim segment of the <h1> title before its first dash separator
# (" – " / " — " / " - " and bare unicode-dash variants) — the source's own
# printed "Country - Capability" format. Requires whitespace on both sides of
# the dash so an in-word hyphen (e.g. "F/A-18F", "Capability-3") never splits.
_TITLE_COUNTRY_SEPARATOR_RE = re.compile(r"\s+[\-‐‑‒–—―]\s+")
_CONTRACTOR_NONE_RE = re.compile(
    r"There is no principal contractor associated with this (?:potential|proposed) sale",
    re.IGNORECASE,
)
_CONTRACTOR_SENTENCE_RE = re.compile(
    r"The principal contractors?(?: for this (?:effort|case))? (?:will be|is|are)\s+(.+?)\.(?=\s|<|$)",
    re.IGNORECASE | re.DOTALL,
)
# Determination-sentence country grammar (NOT part of the frozen §5 grammar
# list — spec gives no explicit customer_country regex for State/DSCA;
# implemented here and documented as a deviation, validated against every
# fixture in tests/fixtures/fms/). A source-printed country phrase always
# begins with one of a small set of formal titles and is immediately
# followed, at the word boundary, by one of a small set of transition
# markers into the capability clause.
_COUNTRY_RE = re.compile(
    r"Foreign Military Sale to the "
    r"((?:" + "|".join(re.escape(p) for p in _COUNTRY_HONORIFIC_PREFIXES if p != "The") + r")"
    r"\s+[A-Z][\w'.\-]*(?:\s+[A-Z][\w'.\-]*)?"
    r"|United Arab Emirates|United Kingdom|United States)"
    r"(?=\s+(?:of\b|to\s+buy\b|to\s+purchase\b|for\b|to\s+the\b))"
)


def _extract_state_country(text: str) -> str | None:
    match = _COUNTRY_RE.search(text)
    return _clean_text(match.group(1)) if match else None


def split_title_country_prefix(title: str | None) -> str | None:
    """Verbatim country segment before the title's first dash separator.

    Spec §5 (amended): precedence rung (1) for ``customer_country`` on any
    surface that has a web post — "Country – Capability" is the sources' own
    printed title format (60/60 census articles yield a non-null prefix).
    Fails closed to ``None`` when no separator is found (no title at all, or
    a title lacking a dash) so the caller can fall through to rung (3).
    """
    if not title:
        return None
    parts = _TITLE_COUNTRY_SEPARATOR_RE.split(title, maxsplit=1)
    if len(parts) < 2:
        return None
    prefix = parts[0].strip()
    return prefix or None


def _resolve_web_country(title: str | None, body: str) -> str | None:
    """Country precedence rungs (1) title-prefix then (3) determination-sentence.

    Rung (2) — the FR join's ``(i) Prospective Purchaser`` — is not a web
    field and is applied at the case-building layer only for ``fr_only``
    cases (spec §4); a joined case's mis-key guard already compares this
    web-derived value against the FR purchaser and flags ``conflicted`` on
    material disagreement.
    """
    prefix = split_title_country_prefix(title)
    if prefix is not None:
        return prefix
    return _extract_state_country(body)


def _extract_value_with_conflict(text: str) -> tuple[int | None, bool]:
    """Return ``(value, conflicted)``; multiple DISTINCT parsed values fail
    closed to ``(None, True)`` (spec §5: "Multiple distinct values ⇒ null +
    conflicted"); zero matches is ``(None, False)`` (genuinely absent)."""
    distinct: set[int] = set()
    for raw, unit in _STATE_VALUE_RE.findall(text):
        try:
            distinct.add(parse_money_amount(raw, unit))
        except ValueError:
            continue
    if len(distinct) == 1:
        return next(iter(distinct)), False
    if len(distinct) > 1:
        return None, True
    return None, False


def _extract_contractors(text: str) -> tuple[list[dict[str, Any]], str | None]:
    if _CONTRACTOR_NONE_RE.search(text):
        note = _clean_text(_CONTRACTOR_NONE_RE.search(text).group(0)) + "."
        return [], note
    match = _CONTRACTOR_SENTENCE_RE.search(text)
    if not match:
        return [], None
    list_text = _clean_text(match.group(1))
    entries = [part.strip() for part in re.split(r";\s*|,\s+and\s+(?=[A-Z])", list_text) if part.strip()]
    contractors: list[dict[str, Any]] = []
    marker = ", located in "
    for entry in entries:
        idx = entry.find(marker)
        if idx == -1:
            contractors.append({
                "name_as_printed": entry, "location_as_printed": None,
                "identity_state": "not_reviewed", "issuer_ref": None,
            })
        else:
            contractors.append({
                "name_as_printed": entry[:idx].strip(),
                "location_as_printed": entry[idx + len(marker):].strip(),
                "identity_state": "not_reviewed", "issuer_ref": None,
            })
    return contractors, None


def parse_state_article(html_text: str, *, source_url: str) -> dict[str, Any]:
    """Deterministic extraction over one State PM-Bureau notice page.

    Unknown/absent fields fail closed to ``None`` rather than being guessed;
    this mirrors D6-A's "unknown layout fails closed" law.
    """
    text = str(html_text)
    clean_body = _clean_text(text)

    title_match = _STATE_TITLE_RE.search(text)
    title = _clean_text(title_match.group(1)) if title_match else None

    date_match = _STATE_PUBLISH_DATE_RE.search(text)
    web_publication_date = None
    if date_match:
        try:
            web_publication_date = datetime.strptime(
                date_match.group(1).strip(), "%B %d, %Y"
            ).date().isoformat()
        except ValueError:
            web_publication_date = None

    modified_match = _MODIFIED_TIME_RE.search(text)
    modified_time = modified_match.group(1).strip() if modified_match else None

    transmittal_info = detect_transmittals(clean_body)
    transmittal = (
        transmittal_info["transmittals"][0]
        if len(transmittal_info["transmittals"]) == 1
        else None  # zero -> fallback identity; >1 -> conflicted (caller inspects "conflicted")
    )

    value_usd, value_conflicted = _extract_value_with_conflict(clean_body)

    contractors, contractor_note = _extract_contractors(clean_body)
    customer_country = _resolve_web_country(title, clean_body)

    return {
        "source_surface": "state",
        "source_url": source_url,
        "transmittal_number": transmittal,
        "identity_conflicted": transmittal_info["conflicted"],
        "value_conflicted": value_conflicted,
        "title": title,
        "customer_country": customer_country,
        "official_web_publication_date": web_publication_date,
        "modified_time": modified_time,
        "estimated_notification_value": value_usd,
        "value_provenance": "state_body" if value_usd is not None else None,
        "currency": "USD",
        "source_caveat": None,  # census: State posts omit the caveat paragraph
        "contractors": contractors,
        "contractor_note": contractor_note,
    }


_LISTING_ITEM_RE = re.compile(
    r'<p class="collection-result__date">\s*([^<]*?)\s*</p>.*?'
    r'<a href="([^"]+)"[^>]*class="collection-result__link"[^>]*>\s*(.*?)\s*</a>',
    re.IGNORECASE | re.DOTALL,
)
_QUALIFYING_LABEL_RE = re.compile(r"foreign military sales:\s*congressional notification", re.IGNORECASE)


def parse_state_listing(html_text: str) -> list[dict[str, Any]]:
    """Extract every listing entry, flagging the qualifying-article predicate.

    Predicate (spec §14): a listing entry carrying the type label "FOREIGN
    MILITARY SALES: CONGRESSIONAL NOTIFICATION" — non-FMS PM releases share
    the same ``/releases/`` URL namespace and never qualify by URL shape
    alone.
    """
    entries: list[dict[str, Any]] = []
    for label, href, title in _LISTING_ITEM_RE.findall(html_text):
        entries.append({
            "source_url": href.strip(),
            "title": _clean_text(title),
            "label": _clean_text(label),
            "is_qualifying": bool(_QUALIFYING_LABEL_RE.search(label)),
        })
    return entries


# ---------------------------------------------------------------------------
# DSCA article grammar (spec §5)
# ---------------------------------------------------------------------------

_DSCA_DATELINE_RE = re.compile(
    r"WASHINGTON,\s+([A-Za-z]+\.?\s+\d{1,2},?\s+\d{4})", re.IGNORECASE
)
_DSCA_VALUE_RE = re.compile(
    r"estimated cost of \$([\d,.]+)\s*(billion|million)", re.IGNORECASE
)
_DSCA_CAVEAT_RE = re.compile(
    r"(The description and dollar value are for the highest estimated quantity.*?"
    r"if and when concluded\.)",
    re.IGNORECASE | re.DOTALL,
)
_DSCA_NEWS_DATE_RE = re.compile(r"NEWS\s*(?:</b>)?\s*\|\s*([A-Za-z]+\.?\s+\d{1,2},\s+\d{4})")


def _parse_month_day_year(text: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", text.strip())
    for fmt in ("%B %d, %Y", "%b. %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_dsca_article(html_text: str, *, source_url: str) -> dict[str, Any]:
    """Deterministic extraction over one staged DSCA historical notice page."""
    text = str(html_text)
    clean_body = _clean_text(text)

    title_match = _STATE_TITLE_RE.search(text)
    title = _clean_text(title_match.group(1)) if title_match else None

    transmittal_info = detect_transmittals(clean_body)
    transmittal = None
    if len(transmittal_info["transmittals"]) == 1:
        transmittal = transmittal_info["transmittals"][0]

    dateline_match = _DSCA_DATELINE_RE.search(clean_body)
    notification_date = _parse_month_day_year(dateline_match.group(1)) if dateline_match else None

    news_match = _DSCA_NEWS_DATE_RE.search(text)
    web_publication_date = _parse_month_day_year(news_match.group(1)) if news_match else None

    value_usd = None
    value_match = _DSCA_VALUE_RE.search(clean_body)
    if value_match:
        try:
            value_usd = parse_money_amount(value_match.group(1), value_match.group(2))
        except ValueError:
            value_usd = None

    caveat_match = _DSCA_CAVEAT_RE.search(clean_body)
    caveat = _clean_text(caveat_match.group(1)) if caveat_match else None

    contractors, contractor_note = _extract_contractors(clean_body)
    customer_country = _resolve_web_country(title, clean_body)

    return {
        "source_surface": "dsca",
        "source_url": source_url,
        "transmittal_number": transmittal,
        "identity_conflicted": transmittal_info["conflicted"],
        "title": title,
        "customer_country": customer_country,
        "official_notification_date": notification_date,
        "official_web_publication_date": web_publication_date,
        "estimated_notification_value": value_usd,
        "value_provenance": "dsca_body" if value_usd is not None else None,
        "currency": "USD",
        "source_caveat": caveat,
        "contractors": contractors,
        "contractor_note": contractor_note,
    }


# ---------------------------------------------------------------------------
# Federal Register raw-text grammar (spec §5)
# ---------------------------------------------------------------------------

_FR_PURCHASER_RE = re.compile(
    r"\(i\)\s*(?:\([A-Z]\)\s*)?Prospective Purchaser:\s*([^\n]+)", re.IGNORECASE
)
_FR_TOTAL_RE = re.compile(
    r"(?im)^\s*[^\w\s]{0,3}\s*TOTAL\.{2,}\s*\$\s*([\d,.]+)\s*(billion|million)\b"
)
_FR_DESCRIPTION_RE = re.compile(
    r"\(iii\)\s*(?:\([A-Z]\)\s*)?Description and Quantity.*?Purchase:\s*\n(.*?)\n\s*\(iv\)",
    re.IGNORECASE | re.DOTALL,
)
_FR_DELIVERED_RE = re.compile(
    r"\(vi{1,3}\)\s*(?:\([A-Z]\)\s*)?Date Report Delivered to Congress:\s*([A-Za-z]+ \d{1,2},\s*\d{4})",
    re.IGNORECASE,
)
_FR_CORRECTION_ACTION_RE = re.compile(
    r"ACTION:\s*Arms sales notice;\s*correction", re.IGNORECASE
)


def classify_fr_document(text: str) -> dict[str, Any]:
    """Classify one FR raw-text document: original / amendment / correction.

    Correction is decided FIRST from the ACTION line — a correction's own
    bracket is digit-only (it targets the transmittal it corrects) and would
    otherwise misclassify as ``original``.
    """
    bracket_match = FR_BRACKET_RE.search(text)
    if bracket_match is None:
        raise ValueError("FR document lacks a [Transmittal No. ...] bracket header")
    bracket = bracket_match.group(1).strip()
    if _FR_CORRECTION_ACTION_RE.search(text):
        return {"classification": "correction", "bracket": bracket}
    classification = classify_fr_bracket(bracket)
    result: dict[str, Any] = {"classification": classification, "bracket": bracket}
    if classification == "original":
        year, seq = re.fullmatch(r"(\d{2})-(\d{1,3})", bracket).groups()
        result["transmittal_number"] = normalize_transmittal(year, seq)
    return result


def parse_fr_document(text: str, *, source_url: str) -> dict[str, Any]:
    """Deterministic extraction over one FR 36(b) raw-text document.

    Amendment documents are classified but carry no purchaser/value/
    description/delivered-date extraction — spec §2: they never mint or
    touch a case, so their body fields are never consulted.
    """
    classification = classify_fr_document(text)
    result: dict[str, Any] = {
        "source_surface": "federal_register",
        "source_url": source_url,
        "classification": classification["classification"],
        "bracket": classification["bracket"],
        "transmittal_number": classification.get("transmittal_number"),
    }
    if classification["classification"] != "original":
        return result

    purchaser_match = _FR_PURCHASER_RE.search(text)
    result["customer_country"] = purchaser_match.group(1).strip() if purchaser_match else None

    value_usd = None
    total_match = _FR_TOTAL_RE.search(text)
    if total_match:
        try:
            value_usd = parse_money_amount(total_match.group(1), total_match.group(2))
        except ValueError:
            value_usd = None
    result["estimated_notification_value"] = value_usd
    result["value_provenance"] = "fr_total_estimated_value" if value_usd is not None else None
    result["currency"] = "USD"

    description_match = _FR_DESCRIPTION_RE.search(text)
    result["source_item_enumeration"] = (
        _clean_text(description_match.group(1)) if description_match else None
    )

    delivered_match = _FR_DELIVERED_RE.search(text)
    result["official_notification_date"] = (
        _parse_month_day_year(delivered_match.group(1)) if delivered_match else None
    )
    return result


# ---------------------------------------------------------------------------
# Receipts (D6-A field conventions, generalized for html/pdf/txt)
# ---------------------------------------------------------------------------

_RECEIPT_IDENTITY_KEYS = (
    "source_url", "response_sha256", "transport", "extractor_version", "parser_version",
)


def _receipt_identity(receipt: Mapping[str, Any]) -> str:
    fingerprint = {key: receipt.get(key) for key in (
        "source_url", "final_url", "response_sha256", "transport",
        "extractor_version", "parser_version", "observed_at",
    )}
    return "fms:" + _sha256_json(fingerprint)


def build_receipt(
    *,
    source_url: str,
    final_url: str,
    content: bytes,
    publisher: str,
    transport: str,
    content_type: str,
    http_status: int,
    observed_at: str | datetime,
    extractor_version: str,
    parser_version: str,
    r2_object_key: str | None,
) -> dict[str, Any]:
    if transport not in TRANSPORTS:
        raise ValueError(f"unrecognized FMS transport: {transport!r}")
    if not isinstance(content, bytes):
        raise ValueError("FMS receipt content must be bytes")
    receipt = {
        "contract": FMS_RECEIPT_CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "receipt_id": "",
        "observed_at": _utc_iso(observed_at),
        "publisher": _text(publisher, label="publisher"),
        "source_url": _text(source_url, label="source_url"),
        "final_url": _text(final_url, label="final_url"),
        "response_sha256": _sha256(content),
        "bytes": len(content),
        "http_status": int(http_status),
        "content_type": _text(content_type, label="content_type"),
        "transport": transport,
        "extractor_version": _text(extractor_version, label="extractor_version"),
        "parser_version": _text(parser_version, label="parser_version"),
        "r2_object_key": r2_object_key,
    }
    receipt["receipt_id"] = _receipt_identity(receipt)
    validate_receipt(receipt)
    return receipt


def validate_receipt(receipt: Mapping[str, Any]) -> None:
    required = {
        "contract", "schema_version", "receipt_id", "observed_at", "publisher",
        "source_url", "final_url", "response_sha256", "bytes", "http_status",
        "content_type", "transport", "extractor_version", "parser_version",
        "r2_object_key",
    }
    if set(receipt) != required:
        raise ValueError("FMS receipt shape mismatch")
    if receipt.get("contract") != FMS_RECEIPT_CONTRACT or receipt.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("FMS receipt contract mismatch")
    if receipt.get("transport") not in TRANSPORTS:
        raise ValueError("FMS receipt transport mismatch")
    sha = receipt.get("response_sha256")
    if not isinstance(sha, str) or not re.fullmatch(r"[a-f0-9]{64}", sha):
        raise ValueError("FMS receipt response_sha256 is invalid")
    if receipt.get("receipt_id") != _receipt_identity(receipt):
        raise ValueError("FMS receipt identity mismatch")
    if not isinstance(receipt.get("bytes"), int) or receipt["bytes"] < 0:
        raise ValueError("FMS receipt byte count is invalid")
    r2_key = receipt.get("r2_object_key")
    if r2_key is not None and (not isinstance(r2_key, str) or not r2_key.startswith(IMMUTABLE_R2_PREFIX)):
        raise ValueError("FMS receipt r2_object_key does not bind the immutable prefix")
    _utc_iso(receipt.get("observed_at"))


def receipt_is_duplicate(existing_receipts: Iterable[Mapping[str, Any]], candidate: Mapping[str, Any]) -> bool:
    """Same-URL-same-bytes idempotent no-op predicate (spec §3/§8)."""
    candidate_key = tuple(candidate.get(key) for key in _RECEIPT_IDENTITY_KEYS)
    for row in existing_receipts:
        if tuple(row.get(key) for key in _RECEIPT_IDENTITY_KEYS) == candidate_key:
            return True
    return False


def merge_receipts(existing: Iterable[Mapping[str, Any]], incoming: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, str] = {}
    records: list[dict[str, Any]] = []
    for row in list(existing) + list(incoming):
        validate_receipt(row)
        canonical = _canonical_json(dict(row))
        receipt_id = str(row["receipt_id"])
        previous = merged.get(receipt_id)
        if previous is not None and previous != canonical:
            raise ValueError("FMS receipt ID is bound to conflicting evidence")
        if previous is None:
            merged[receipt_id] = canonical
            records.append(dict(row))
    return records


# ---------------------------------------------------------------------------
# Observations (append-only case evidence, spec §3)
# ---------------------------------------------------------------------------


def _observation_identity(observation: Mapping[str, Any]) -> str:
    fingerprint = {key: observation.get(key) for key in (
        "case_key", "source_surface", "kind", "source_url", "response_sha256", "version",
    )}
    return "fmsobs:" + _sha256_json(fingerprint)


def build_observation(
    *,
    case_key: str,
    source_surface: str,
    kind: str,
    receipt: Mapping[str, Any],
    known_at: str | datetime,
    version: int,
    fields: Mapping[str, Any],
) -> dict[str, Any]:
    if source_surface not in SOURCE_SURFACES:
        raise ValueError(f"unrecognized FMS source_surface: {source_surface!r}")
    if kind not in OBSERVATION_KINDS:
        raise ValueError(f"unrecognized FMS observation kind: {kind!r}")
    validate_receipt(receipt)
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError("FMS observation version must be a positive integer")
    observation = {
        "contract": FMS_OBSERVATION_CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "observation_id": "",
        "case_key": _text(case_key, label="case_key"),
        "source_surface": source_surface,
        "kind": kind,
        "version": version,
        "source_url": receipt["source_url"],
        "response_sha256": receipt["response_sha256"],
        "bytes": receipt["bytes"],
        "transport": receipt["transport"],
        "receipt_id": receipt["receipt_id"],
        "observed_at": receipt["observed_at"],
        "known_at": _utc_iso(known_at),
        "r2_object_key": receipt["r2_object_key"],
        "fields": dict(fields),
    }
    observation["observation_id"] = _observation_identity(observation)
    validate_observation(observation)
    return observation


def validate_observation(observation: Mapping[str, Any]) -> None:
    required = {
        "contract", "schema_version", "observation_id", "case_key", "source_surface",
        "kind", "version", "source_url", "response_sha256", "bytes", "transport",
        "receipt_id", "observed_at", "known_at", "r2_object_key", "fields",
    }
    if set(observation) != required:
        raise ValueError("FMS observation shape mismatch")
    if observation.get("contract") != FMS_OBSERVATION_CONTRACT or observation.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("FMS observation contract mismatch")
    if observation.get("source_surface") not in SOURCE_SURFACES:
        raise ValueError("FMS observation source_surface mismatch")
    if observation.get("kind") not in OBSERVATION_KINDS:
        raise ValueError("FMS observation kind mismatch")
    if observation.get("observation_id") != _observation_identity(observation):
        raise ValueError("FMS observation identity mismatch")
    if not isinstance(observation.get("version"), int) or observation["version"] < 1:
        raise ValueError("FMS observation version is invalid")
    if not isinstance(observation.get("fields"), Mapping):
        raise ValueError("FMS observation fields must be an object")
    _utc_iso(observation.get("known_at"))
    _utc_iso(observation.get("observed_at"))


def append_observation_versions(
    existing: Iterable[Mapping[str, Any]], incoming: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Append-only merge keyed by (case_key, source_surface, source_url).

    Same URL + same bytes (``response_sha256``) is a receipted no-op — the
    candidate is dropped entirely, nothing is appended (spec §3/§8, T8).
    Same key + CHANGED bytes appends a new version; every predecessor row is
    preserved byte-for-byte and NEVER mutated (T8: "any in-place mutation of
    case history" fails this test).
    """
    result = [dict(row) for row in existing]
    latest_by_key: dict[tuple[str, str, str], tuple[int, str]] = {}
    for row in result:
        validate_observation(row)
        key = (row["case_key"], row["source_surface"], row["source_url"])
        version, sha = int(row["version"]), row["response_sha256"]
        prior = latest_by_key.get(key)
        if prior is None or version > prior[0]:
            latest_by_key[key] = (version, sha)
    for raw in incoming:
        candidate = dict(raw)
        validate_observation(candidate)
        key = (candidate["case_key"], candidate["source_surface"], candidate["source_url"])
        prior = latest_by_key.get(key)
        if prior is not None and prior[1] == candidate["response_sha256"]:
            continue  # idempotent no-op: identical bytes already retained
        next_version = (prior[0] + 1) if prior is not None else 1
        if candidate["version"] != next_version:
            candidate = dict(candidate)
            candidate["version"] = next_version
            candidate["observation_id"] = _observation_identity(candidate)
        result.append(candidate)
        latest_by_key[key] = (candidate["version"], candidate["response_sha256"])
    return result


# ---------------------------------------------------------------------------
# Identity supersession (freeze §6 "Supersession"; spec §16 test T9)
# ---------------------------------------------------------------------------


def apply_identity_supersession(
    *, fallback_case_key: str, transmittal: str, at: str | datetime,
) -> dict[str, Any]:
    """Build an append-only supersession record for a newly-discovered transmittal.

    Law (freeze §6): history is NEVER rewritten under the new key, and the
    new identity is NEVER backdated. This function only ever returns a
    record whose ``recorded_at`` is the caller-supplied "now" (``at``); it
    never touches ``fallback_case_key``'s prior observations, and the
    fallback key itself is never replaced — callers must alias, never
    reassign.
    """
    if not fallback_case_key.startswith("fms:urlpath:"):
        raise ValueError("identity supersession source must be a fallback case key")
    new_case_key = case_key_for_transmittal(transmittal)
    return {
        "kind": "identity_supersession",
        "fallback_case_key": fallback_case_key,
        "transmittal_number": transmittal,
        "new_case_key": new_case_key,
        "recorded_at": _utc_iso(at),
    }
