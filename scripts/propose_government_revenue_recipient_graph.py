"""Propose — never publish — recipient-to-issuer mappings from official documents only.

Wave 9D expands Government Revenue issuer attribution beyond the single reviewed
PLTR mapping.  The wave forbids deriving a mapping from ``discovery_query_ticker``,
fuzzy name similarity, a web-search snippet, or an LLM assertion, so the only
legitimate construction left is an EXACT join between two official documents:

    SEC ``company_tickers.json``      ticker -> CIK              (SEC's own authority)
    SEC ``submissions`` API           CIK -> latest 10-K         (lookup only)
    SEC EDGAR archive ``index.json``  10-K -> EX-21 filename     (lookup only)
    SEC 10-K primary document         the registrant itself
    SEC EX-21 exhibit                 subsidiary legal names
    USAspending award record          recipient_name + recipient_uei

This module performs that join and emits a CANDIDATE graph plus a human review
worksheet.  It is a discovery step, not a publish step.

Failure modes this file exists to prevent
-----------------------------------------

**A proposal that masquerades as a published graph.**  The v1 contract's
``reviewState`` enum is closed at ``confirmed | reviewed | analyst_approved``;
there is deliberately no ``proposed`` state, and the top-level key set is a
closed 13 keys, so a candidate cannot carry an extra ``status`` field and still
load.  A candidate is therefore marked in the four places that survive a copy:

1. It is written to a caller-supplied output directory under the explicit name
   ``recipient_graph_candidate.json``.  :func:`guard_output_path` refuses any
   destination that resolves to the canonical graph, or that merely shares its
   file name, so ``--out-dir data/government_revenue`` cannot overwrite it and a
   later ``cp`` cannot be excused as a typo.
2. ``graph_id`` is minted in a candidate namespace,
   ``recipient-graph:candidate:<date>:<slug>``, never ``:reviewed:``.  ``graph_id``
   is free text that no code parses, but it is echoed verbatim into the load
   result, the candidate queue envelope, and the coverage artifact — so a
   candidate that ever reached production would name itself there.
3. The review worksheet is a separate document carrying
   ``review_state: awaiting_analyst_review`` and the promotion command.
4. This module never writes the canonical graph and never imports the curate
   script.  ``scripts/curate_government_revenue_recipient_graph.py`` remains the
   single writer registered in ``config/dag.yml`` / ``config/synapse.yml``.

The row-level ``verification_state`` is nonetheless ``"reviewed"``, because the
contract offers no weaker word and the document must load cleanly for the analyst
to inspect it.  Read it as *the assertion the analyst is being asked to make*,
not as a claim that anyone has made it.  It is inert until a human runs the
curate script against the canonical path.

**A normalizer that quietly merges two distinct businesses.**  The join is exact
equality after :func:`normalize_legal_name`, which only reconciles how the SAME
legal name is punctuated across two official documents: case, punctuation,
four corporate-form spellings (Incorporated/Corporation/Company/Limited), and a
leading article.  There is no edit distance, no token-set overlap, no substring
containment, and no similarity score.  A reviewer can read the twelve lines of
that function and see that it cannot merge "Prestige Aerospace LLC" into
"General Electric Company".  The leading-article rule is the only rule that
deletes a token, and it earns its place with a paired control: it recovers the
Boeing edges ("THE BOEING COMPANY" vs registrant "BOEING CO") while leaving GE at
zero.

**A discovery ticker leaking back in as attribution.**  The award pool is joined
GLOBALLY, not per discovery ticker: a recipient row's ``ticker`` column (which
came from a curated fuzzy-name discovery query) is carried into the worksheet as
review metadata only and is never a condition for proposing an edge.

**A zero reported as a to-do.**  An issuer with no proposed edge gets a NAMED
cause.  GE's five collected recipients are genuinely other companies, so GE's
answer is ``no_exact_match`` — "no exact issuer evidence" — which is a finished
result, not ``mapping_needed``.  BWXT collected nothing at all, which is an
upstream collection gap (``no_collected_recipients``), a different problem with a
different owner.

**A zero that is really an extractor bug wearing a finished verdict.**  The
sentence ``no_exact_match`` carries — "this is a finished answer, not an
outstanding mapping task" — is only true if the EX-21 names the join never saw
were genuinely not there.  An earlier revision of this file discarded any line
ending in "Incorporated" (a noise pattern) and could not match a dotted "L.P."
(the tail vocabulary was undotted), which made the real Huntington Ingalls
Incorporated → ``C3NLZNSMU254`` edge unreachable while the tool asserted HII was
finished.  Both filters now run against :func:`normalize_legal_name` of the line
rather than the raw line, and every issuer's worksheet row carries
``ex21_lines_extracted`` / ``ex21_lines_rejected`` with samples, so the zero
arrives with the receipt that makes it checkable instead of merely asserted.

**A test suite that silently reaches the network.**  All byte access goes through
one injectable ``fetch(url) -> bytes`` seam.  Every URL requested is recorded in
``Proposal.fetch_log``, so a test can assert that the injected fetcher was the
only source of bytes.

Usage::

    python3 -m scripts.propose_government_revenue_recipient_graph \
      --out-dir /tmp/govrev-wave9d \
      --user-agent "MastermindX Government Revenue research (contact: you@example.com)"

SEC requires a descriptive User-Agent carrying a real contact, so ``--user-agent``
has no default: an operator supplies their own or the run refuses to start.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import json
import re
import sys
import time
import unicodedata
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import quote, urlparse

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.government_revenue.entity_resolution import (  # noqa: E402
    AUTHORITY,
    RECIPIENT_GRAPH_CONTRACT,
    RECIPIENT_GRAPH_SCHEMA_VERSION,
    load_recipient_entity_graph,
)


CANONICAL_GRAPH_PATH = _ROOT / "data" / "government_revenue" / "recipient_entity_graph.json"
DEFAULT_AWARDS_PATH = _ROOT / "data" / "government_revenue" / "awards.parquet"
DEFAULT_ENTITIES_PATH = _ROOT / "data" / "government_revenue" / "entities.json"

CANDIDATE_GRAPH_FILENAME = "recipient_graph_candidate.json"
WORKSHEET_JSON_FILENAME = "recipient_graph_review_worksheet.json"
WORKSHEET_MARKDOWN_FILENAME = "recipient_graph_review_worksheet.md"

PROPOSAL_CONTRACT = "government_recipient_graph_proposal_worksheet.v0"
PROPOSAL_SCHEMA_VERSION = "0.1.0"
CANDIDATE_GRAPH_ID_PREFIX = "recipient-graph:candidate:"

SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SEC_ARCHIVE_INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/index.json"
SEC_ARCHIVE_FILE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{name}"
USASPENDING_AWARD_URL = "https://api.usaspending.gov/api/v2/awards/{award_id}/"

# ``data.sec.gov`` is deliberately absent from the runtime's evidence host
# allow-list, so the submissions API may be read for LOOKUP but its URL must
# never appear on an evidence row.  These are the hosts the loader will accept.
EVIDENCE_HOSTS = {
    "SEC": {"www.sec.gov", "sec.gov"},
    "USAspending.gov": {"api.usaspending.gov", "www.usaspending.gov", "usaspending.gov"},
}

# Every reason an issuer can end a run with zero proposed edges.  Each names a
# DIFFERENT owner and a DIFFERENT next action; none of them is "mapping needed".
NO_EDGE_CAUSES = (
    "ticker_not_in_sec_registry",
    "sec_lookup_failed",
    "no_10k_filing",
    "no_ex21_exhibit",
    "registrant_name_not_in_filing",
    "no_collected_recipients",
    "no_exact_match",
    "all_candidate_identifiers_withheld",
)

# Reasons an individual exact match is refused after the name join succeeded.
WITHHELD_CAUSES = (
    "identifier_claimed_by_multiple_issuers",
    "identifier_maps_to_multiple_entities",
    "no_award_receipt_before_as_of",
    "award_receipt_missing_identifier",
    "award_receipt_fetch_failed",
)

_UEI = re.compile(r"^[A-HJ-NP-Z0-9]{12}$")
_TICKER = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")

# The complete corporate-form vocabulary.  Each entry reconciles two spellings of
# ONE form; nothing here can rewrite a distinguishing word.
_CORPORATE_FORMS = {
    "incorporated": "inc",
    "inc": "inc",
    "corporation": "corp",
    "corp": "corp",
    "company": "co",
    "co": "co",
    "limited": "ltd",
    "ltd": "ltd",
}
_LEADING_ARTICLE = "the"

NORMALIZATION_RULES = (
    "Unicode NFKC, then lowercase.",
    "Every character outside [a-z0-9&] becomes a space; runs of spaces collapse.",
    "Corporate-form spelling only: incorporated->inc, corporation->corp, "
    "company->co, limited->ltd.",
    "A single leading article 'the' is dropped when at least one token remains.",
    "Nothing else. No edit distance, no token-set overlap, no substring "
    "containment, no similarity score.",
)

FORBIDDEN_MAPPING_INPUTS = (
    "discovery_query_ticker",
    "fuzzy or approximate name similarity",
    "web-search snippets",
    "LLM assertion",
)

# EX-21 layout is not standardised, so extraction is generous and the MATCH is
# strict.  An over-broad candidate that matches nothing costs nothing; a missed
# candidate silently shrinks coverage — and, because a zero is published as a
# FINISHED verdict here, a missed candidate publishes a false one.
#
# BOTH patterns are applied to ``normalize_legal_name(line)``, never to the raw
# line.  Testing the raw line is what made "Huntington Ingalls Incorporated"
# unreachable twice over: ``\binc\b`` cannot match "Incorporated", and a noise
# pattern ``incorporat\w*\s*$`` then deleted the line even if the tail were
# fixed.  Normalizing first makes the two spellings of one corporate form a
# single token ("Incorporated" -> ``inc``, "Corporation" -> ``corp``) and turns a
# dotted form into its own tokens ("L.P." -> ``l p``), which is the only shape in
# which either can be matched at all.
_EX21_NAME_TAIL = re.compile(
    r"(?:^|\s)(?:"
    # The four forms normalize_legal_name itself reconciles.
    r"inc|corp|co|ltd|"
    # Undotted and dotted spellings of the remaining common forms.  A dotted
    # spelling survives normalization as separate single-letter tokens.
    r"llc|l l c|lp|l p|llp|l l p|plc|p l c|pllc|p l l c|"
    r"nv|n v|bv|b v|sa|s a|ag|a g|srl|s r l|sas|s a s|kg|k g|"
    r"gmbh|pty|pte|sarl|spa|oy|ab|as|kk|"
    # Words that end a legal name often enough to be worth a candidate.
    r"holdings|technologies|systems|international|group|partnership|trust"
    r")$"
)
_EX21_NOISE = re.compile(
    r"(subsidiar|exhibit|jurisdiction|place of|state of|country of|"
    r"organi[sz]ation|percentage|ownership of)"
)
_EX21_LIST_MARKER = re.compile(r"^(?:\(?\d{1,3}[.)]|[•●*\-–—])\s+")
# EDGAR's archive listing carries a ``type`` field, but it is ``text.gif`` for
# every document in a real filing (verified against GE, BA, and PLTR 2025 10-Ks),
# so the file NAME is the only signal.  The exhibit token may sit anywhere in the
# name: GE files ``ex21subsidiariesofregistra.htm``, BA files
# ``a202512dec3110kex21.htm``, PLTR files ``a2025fyexhibit211.htm``.  Anchoring
# the token to the extension — as an earlier revision of this file did — reported
# GE as "no EX-21 exhibit" when the exhibit was right there, which sends an
# analyst to EDGAR instead of closing the issuer out.
# ``x`` belongs in the separator class alongside the punctuation.  EDGAR uses a
# bare ``x`` where a filename cannot carry a dot, which this module already knew
# for the PREFIX position (``pltr-20251231xex211.htm``) but not for the position
# BETWEEN the exhibit word and its number: Textron files
# ``q4202510k-exx21.htm``, and ``[-_.]?`` cannot match that ``x``.  The live
# 2026-08-07 run therefore reported TXT as ``no_ex21_exhibit`` — "Accession
# 000021734626000006 carries no EX-21 attachment" — against a filing whose EX-21
# is right there, losing every Textron edge and asserting something untrue.  That
# is the same shape as the extractor defect one function later: a silent filter
# turning a finished verdict into a phantom errand.  Widening to ``[-_.x]?`` does
# not loosen the sibling fence, verified against real EDGAR names: ex22...,
# ex1012, exhibit231, ex232..., ex311..., ex321... all still fail the pattern.
_EX21_FILENAME = re.compile(r"ex(?:hibit)?[-_.x]?21", re.IGNORECASE)
_EX21_EXTENSIONS = (".htm", ".html", ".txt")


# ---------------------------------------------------------------------------
# Normalization and extraction
# ---------------------------------------------------------------------------


def normalize_legal_name(name: str | None) -> str:
    """Reconcile punctuation and corporate-form spelling of ONE legal name.

    This is the entire join rule, and it is deliberately short enough to audit in
    one sitting.  It reconciles how the same legal name is written across two
    official documents ("Palantir USG, Inc." in an EX-21 vs "PALANTIR USG INC" in
    a USAspending award record).  It cannot merge two distinct businesses because
    it never deletes, reorders, abbreviates, or approximates a distinguishing
    token: the only token it can remove is a leading English article, and the
    only tokens it rewrites are four corporate forms whose two spellings mean the
    same thing.

    ``&`` survives as its own token and is NOT rewritten to "and" — treating a
    conjunction as interchangeable would be a semantic guess, not a spelling fix.
    """
    text = unicodedata.normalize("NFKC", name or "")
    text = html.unescape(text)
    text = text.lower()
    text = re.sub(r"[^a-z0-9&]+", " ", text)
    tokens = [_CORPORATE_FORMS.get(token, token) for token in text.split()]
    if len(tokens) > 1 and tokens[0] == _LEADING_ARTICLE:
        tokens = tokens[1:]
    return " ".join(tokens)


@dataclass(frozen=True)
class Ex21Extraction:
    """What an EX-21 body yielded, and what it cost to get there.

    ``rejected`` exists so a ``no_exact_match`` zero can be AUDITED instead of
    believed.  Only lines that were plausible candidates (inside the length
    window, and carrying at least one normalized token) are recorded — a
    jurisdiction cell or a page number is not a discarded name, and burying the
    real discards among those would make the counter as unreadable as no counter.
    """

    names: list[str]
    rejected: list[dict[str, str]]

    @property
    def rejected_samples(self) -> list[dict[str, str]]:
        return self.rejected[:5]


def extract_ex21_lines(document: str) -> Ex21Extraction:
    """Pull candidate subsidiary legal names out of an EX-21 exhibit body.

    Returns display spellings, sorted and de-duplicated, alongside the plausible
    lines that were discarded and why.  The caller normalizes the survivors for
    the join; keeping the raw spelling here means the worksheet can show an
    analyst the exact string the SEC document carried.

    Both filters run against the NORMALIZED line (see ``_EX21_NAME_TAIL``):
    tested against the raw line they cannot see "Incorporated" or a dotted
    "L.P." at all, which is how a real Huntington Ingalls edge went missing
    under a verdict that called the search finished.
    """
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", document, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    names: set[str] = set()
    rejected: dict[str, str] = {}
    for raw_line in text.split("\n"):
        line = re.sub(r"\s+", " ", raw_line).strip()
        line = _EX21_LIST_MARKER.sub("", line).strip()
        if not 4 <= len(line) <= 120:
            continue
        normalized = normalize_legal_name(line)
        if not normalized:
            continue
        if _EX21_NOISE.search(normalized) is not None:
            rejected.setdefault(line, "matched_noise_filter")
            continue
        if _EX21_NAME_TAIL.search(normalized) is None:
            rejected.setdefault(line, "no_recognised_corporate_form_tail")
            continue
        names.add(line)
    return Ex21Extraction(
        names=sorted(names),
        rejected=[
            {"line": line, "reason": reason}
            for line, reason in sorted(rejected.items())
            if line not in names
        ],
    )


def extract_ex21_names(document: str) -> list[str]:
    """The survivors alone — :func:`extract_ex21_lines` also reports the discards."""
    return extract_ex21_lines(document).names


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "unnamed"


# ---------------------------------------------------------------------------
# Clock helpers
# ---------------------------------------------------------------------------


def _iso(moment: datetime) -> str:
    """RFC3339 with an explicit UTC offset — the only shape the loader accepts."""
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _iso_midnight(day: date) -> str:
    return f"{day.isoformat()}T00:00:00+00:00"


def _as_date(value: Any) -> date | None:
    """Coerce a parquet/JSON date cell to a plain UTC date, or None."""
    if value is None or value != value:  # NaN/NaT are never equal to themselves.
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# The single network seam
# ---------------------------------------------------------------------------


Fetch = Callable[[str], bytes]


class HttpFetcher:
    """The only component in this module that opens a socket.

    Kept as a tiny callable so tests can replace it wholesale with a dictionary
    of committed fixtures.  SEC's fair-access policy asks for a descriptive
    User-Agent carrying a real contact and for paced requests; a generic agent is
    answered with 403s, so an empty or contactless agent fails fast here rather
    than halfway through a 21-issuer walk.
    """

    def __init__(self, user_agent: str, *, pace_seconds: float = 0.35, timeout: int = 45) -> None:
        agent = (user_agent or "").strip()
        if len(agent) < 12 or ("@" not in agent and "http" not in agent.lower()):
            raise ValueError(
                "SEC requires a descriptive User-Agent carrying a contact address, "
                "e.g. 'MastermindX Government Revenue research (contact: you@example.com)'"
            )
        self.user_agent = agent
        self.pace_seconds = max(0.0, float(pace_seconds))
        self.timeout = timeout
        self._last_request_at: float | None = None

    def __call__(self, url: str) -> bytes:
        if self._last_request_at is not None and self.pace_seconds:
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < self.pace_seconds:
                time.sleep(self.pace_seconds - elapsed)
        request = urllib.request.Request(
            url,
            headers={"User-Agent": self.user_agent, "Accept-Encoding": "gzip"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = response.read()
            if response.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
        self._last_request_at = time.monotonic()
        return body


class MappingFetcher:
    """A fetcher backed by an in-memory ``{url: bytes}`` mapping.

    Used by the test suite so no test can reach the network even if a URL
    template changes.  An unknown URL raises rather than returning empty bytes:
    an empty body would hash cleanly and ship as evidence for nothing.
    """

    def __init__(self, documents: Mapping[str, bytes]) -> None:
        self.documents = dict(documents)
        self.served: list[str] = []

    def __call__(self, url: str) -> bytes:
        if url not in self.documents:
            raise FileNotFoundError(f"no offline fixture for {url}")
        self.served.append(url)
        return self.documents[url]


def load_fixture_fetcher(fixture_dir: Path) -> MappingFetcher:
    """Build a :class:`MappingFetcher` from ``<fixture_dir>/url_map.json``."""
    url_map = json.loads((fixture_dir / "url_map.json").read_text(encoding="utf-8"))
    return MappingFetcher(
        {url: (fixture_dir / name).read_bytes() for url, name in sorted(url_map.items())}
    )


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


AWARD_FIELDS = (
    "ticker",
    "recipient_name",
    "recipient_uei",
    "generated_award_id",
    "start_date",
    "base_obligation_date",
)


def _award_records(path: Path) -> list[Mapping[str, Any]]:
    """The raw award panel, from parquet or from an equivalent JSON list.

    Pandas is imported inside the parquet branch rather than at module scope so
    the test suite (which injects plain dictionaries, and drives the CLI off the
    committed JSON fixture) never needs it.  The JSON branch is not a second
    source of truth: it carries the same columns and goes through the same
    validation two lines down.
    """
    if path.suffix.lower() == ".json":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"{path} must hold a list of award records")
        records = [dict(record) for record in payload]
        missing = sorted(
            {column for record in records for column in AWARD_FIELDS if column not in record}
        )
        if missing:
            raise ValueError(f"awards panel is missing join columns: {missing}")
        return records

    import pandas as pd  # noqa: PLC0415 - deliberately lazy; see docstring.

    frame = pd.read_parquet(path)
    missing = [column for column in AWARD_FIELDS if column not in frame.columns]
    if missing:
        raise ValueError(f"awards panel is missing join columns: {sorted(missing)}")
    return frame[list(AWARD_FIELDS)].to_dict("records")


def load_award_rows(path: Path) -> list[dict[str, Any]]:
    """Read the collected USAspending award panel down to the join columns."""
    rows: list[dict[str, Any]] = []
    for record in _award_records(path):
        rows.append(
            {
                "ticker": (str(record["ticker"]).strip() if record["ticker"] else None),
                "recipient_name": (
                    str(record["recipient_name"]).strip() if record["recipient_name"] else None
                ),
                "recipient_uei": (
                    str(record["recipient_uei"]).strip() if record["recipient_uei"] else None
                ),
                "generated_award_id": (
                    str(record["generated_award_id"]).strip()
                    if record["generated_award_id"]
                    else None
                ),
                "start_date": _as_date(record["start_date"]),
                "base_obligation_date": _as_date(record["base_obligation_date"]),
            }
        )
    return rows


def load_scope_tickers(path: Path) -> list[str]:
    """Read the configured Government Revenue issuer scope.

    This list decides WHICH issuers are researched.  It never decides what any
    recipient maps to: the ticker->CIK binding comes from SEC's own registry and
    the recipient join comes from exact document names.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    entities = payload.get("entities") or {}
    return sorted(ticker for ticker in entities if _TICKER.fullmatch(str(ticker)))


# ---------------------------------------------------------------------------
# Proposal
# ---------------------------------------------------------------------------


@dataclass
class Proposal:
    """A candidate graph, its review worksheet, and the byte provenance."""

    graph: dict[str, Any]
    worksheet: dict[str, Any]
    fetch_log: list[str] = field(default_factory=list)


def _latest_10k(submissions: Mapping[str, Any]) -> dict[str, Any] | None:
    """Select the most recently filed 10-K, breaking ties deterministically."""
    recent = ((submissions.get("filings") or {}).get("recent")) or {}
    forms = recent.get("form") or []
    best: dict[str, Any] | None = None
    for index, form in enumerate(forms):
        if str(form).strip().upper() != "10-K":
            continue
        accession = str((recent.get("accessionNumber") or [None] * len(forms))[index] or "")
        candidate = {
            "accession": accession.replace("-", ""),
            "filing_date": str((recent.get("filingDate") or [""] * len(forms))[index] or ""),
            "report_date": str((recent.get("reportDate") or [""] * len(forms))[index] or ""),
            "primary_document": str(
                (recent.get("primaryDocument") or [""] * len(forms))[index] or ""
            ),
        }
        if not candidate["accession"] or not candidate["primary_document"]:
            continue
        key = (candidate["filing_date"], candidate["accession"])
        if best is None or key > (best["filing_date"], best["accession"]):
            best = candidate
    return best


def select_ex21_filename(index_document: Mapping[str, Any]) -> str | None:
    """Pick the EX-21 attachment from an EDGAR archive directory listing.

    Any name containing "index" is excluded first, because the exhibit pattern is
    a substring match: EDGAR writes real exhibits as ``pltr-...xex211.htm`` (the
    ``x`` is a separator, so a letter boundary before ``ex`` is not available),
    and ``index21.htm`` therefore *contains* ``ex21``.  An EDGAR index page
    silently parsed as an exhibit yields a document full of headings and zero
    subsidiaries — a coverage hole that reads as "this issuer has no
    subsidiaries" rather than as a bug.

    Sibling exhibits do not collide: ``ex22listofsubsidiaryguaran.htm``,
    ``a202512dec3110kex1012.htm``, and ``a2025q4exhibit231.htm`` all fail the
    pattern because the digits immediately after the exhibit word are not ``21``.
    The one residual ambiguity is a filing that names Exhibit *2.1* ``ex21.htm``
    while carrying no Exhibit 21; that fails SAFE, because the extracted names
    then match no recipient at all and the issuer is reported as
    ``no_exact_match`` rather than gaining a fabricated edge.  Ties are broken by
    sorted order so a re-run is byte-identical.
    """
    items = ((index_document.get("directory") or {}).get("item")) or []
    names = sorted(str(item.get("name") or "") for item in items)
    for name in names:
        lowered = name.lower()
        if "index" in lowered or not lowered.endswith(_EX21_EXTENSIONS):
            continue
        if _EX21_FILENAME.search(name):
            return name
    return None


def _evidence_row(
    *,
    evidence_id: str,
    publisher: str,
    evidence_class: str,
    record_id: str,
    url: str,
    body: bytes,
    claim_scopes: Sequence[str],
    known_at: str,
    valid_from: str,
    retrieved_at: str,
) -> dict[str, Any]:
    """One content-addressed receipt.

    ``retrieved_at`` is the moment the bytes actually arrived, recorded at the
    fetch — NOT the run stamp.  Deriving it from ``known_at`` (as an earlier
    revision did) makes every receipt assert a retrieval that did not happen the
    moment ``--as-of`` names any day but today, which is the one field in this
    document a reader has no way to check.
    """
    host = (urlparse(url).hostname or "").lower()
    if urlparse(url).scheme != "https" or host not in EVIDENCE_HOSTS.get(publisher, set()):
        # The runtime rejects this at load time; refusing here names the mistake
        # while the offending URL is still in hand.
        raise ValueError(f"{publisher} evidence URL is not on the allow-listed host set: {url}")
    if not retrieved_at:
        raise ValueError(f"no recorded fetch time for {url}; it was never read through the seam")
    digest = hashlib.sha256(body).hexdigest()
    return {
        "evidence_id": evidence_id,
        "source_ref": f"recipient-evidence:sha256:{digest}",
        "publisher": publisher,
        "evidence_class": evidence_class,
        "record_id": record_id,
        "url": url,
        "content_sha256": digest,
        "byte_length": len(body),
        "retrieved_at": retrieved_at,
        "claim_scopes": sorted(set(claim_scopes)),
        "known_at": known_at,
        "valid_from": valid_from,
        "valid_to": None,
    }


def _filing_names_the_registrant(body: bytes, registrant_name: str) -> bool:
    """Does the cited 10-K actually contain the registrant it is cited for?

    The comparison runs through :func:`normalize_legal_name` on both sides, so
    the SEC's registry spelling ("LOCKHEED MARTIN CORP") matches the cover page's
    ("Lockheed Martin Corporation") and the tag soup between the words does not
    defeat it — markup becomes whitespace on both sides of the join rule this
    module already documents.  It is a containment test on purpose: the cover
    page carries the name inside a much longer document.

    The SEC registry appends a state-of-incorporation suffix to some names
    ("L3HARRIS TECHNOLOGIES, INC. /DE/") that no filing repeats, so the
    suffix-free spelling is accepted too.  This only widens what counts as the
    registrant's own name in its own filing; it is NOT a join key, and nothing
    here can make one company's filing vouch for another's.
    """
    keys = {
        key
        for key in (
            normalize_legal_name(registrant_name),
            normalize_legal_name(re.sub(r"\s*/[A-Za-z]{2}/\s*$", "", registrant_name)),
        )
        if key
    }
    if not keys:
        return False
    haystack = f" {normalize_legal_name(body.decode('utf-8', 'ignore'))} "
    return any(f" {key} " in haystack for key in keys)


def _temporal(known_at: str, valid_from: str, evidence_refs: Sequence[str]) -> dict[str, Any]:
    return {
        "known_at": known_at,
        "valid_from": valid_from,
        "valid_to": None,
        "evidence_refs": sorted(set(evidence_refs)),
    }


def _issuer_graph_rows(
    *,
    issuer: Mapping[str, Any],
    issuer_claims: Sequence[dict[str, Any]],
    stamp: str,
    published_ueis: set[str],
    retrieved_at_by_url: Mapping[str, str],
) -> dict[str, list[dict[str, Any]]]:
    """Turn one issuer's documents and admitted claims into graph rows.

    Kept separate from the walk so the shape of what gets PROPOSED can be read
    without also reading how it was discovered.  Every row this returns is
    ``verification_state: "reviewed"`` because the contract has no weaker word —
    see the module docstring for why that is not a claim of review.

    Two structural rules earn their own note:

    * The registrant legal entity and its ``issuer_legal_entity`` edge are always
      emitted, even when the registrant carries no UEI of its own.  An EX-21
      subsidiary needs a parent to walk through to reach the company terminal;
      without it the resolver returns ``ownership_path_missing``.
    * A normalized name that already belongs to the registrant never also becomes
      a subsidiary.  The registrant-wins rule below is the worksheet's role and
      document attribution; the structural guarantee that one entity never holds
      both an ``issuer_legal_entity`` and a ``wholly_owned`` edge is the
      ``key == registrant_key`` skip in the ownership loop.
    * Every ``edge_id`` is derived from the DE-DUPLICATED ``entity_id``, never
      from ``_slug(key)`` directly.  Two normalized names can slug to one string
      ("alpha & beta llc" and "alpha beta llc" both slug to ``alpha-beta-llc``);
      the entity ids get a ``-2`` suffix, and an edge id minted independently
      from the slug would collide, which fails admission as ``duplicate_edge_id``
      and makes the WHOLE 21-issuer candidate unloadable over one issuer's
      punctuation.
    """
    ticker = issuer["ticker"]
    slug = ticker.lower()
    valid_from = _iso_midnight(issuer["report_date"])
    evidence: list[dict[str, Any]] = []
    companies: list[dict[str, Any]] = []
    legal_entities: list[dict[str, Any]] = []
    identifiers: list[dict[str, Any]] = []
    ownership_edges: list[dict[str, Any]] = []
    worksheet_edges: list[dict[str, Any]] = []

    tenk_evidence_id = f"evidence:{slug}-sec-10k"
    ex21_evidence_id = f"evidence:{slug}-sec-ex21"
    evidence.append(
        _evidence_row(
            evidence_id=tenk_evidence_id,
            publisher="SEC",
            evidence_class="official_filing",
            record_id=f"sec:{issuer['cik']}:{issuer['accession']}:{issuer['primary_document']}",
            url=issuer["tenk_url"],
            body=issuer["tenk_body"],
            claim_scopes=["public_company", "legal_entity", "ownership"],
            known_at=stamp,
            valid_from=valid_from,
            retrieved_at=retrieved_at_by_url.get(issuer["tenk_url"], ""),
        )
    )
    evidence.append(
        _evidence_row(
            evidence_id=ex21_evidence_id,
            publisher="SEC",
            evidence_class="official_filing",
            record_id=f"sec:{issuer['cik']}:{issuer['accession']}:{issuer['ex21_document']}",
            url=issuer["ex21_url"],
            body=issuer["ex21_body"],
            claim_scopes=["legal_entity", "ownership"],
            known_at=stamp,
            valid_from=valid_from,
            retrieved_at=retrieved_at_by_url.get(issuer["ex21_url"], ""),
        )
    )

    company_id = f"central:{ticker}"
    companies.append(
        {
            "company_id": company_id,
            "ticker": ticker,
            "verification_state": "reviewed",
            **_temporal(stamp, valid_from, [tenk_evidence_id]),
        }
    )

    registrant_key = normalize_legal_name(issuer["registrant_name"])
    registrant_entity_id = f"legal:{slug}:{_slug(registrant_key)}"
    entity_ids: dict[str, str] = {registrant_key: registrant_entity_id}
    used_ids = {registrant_entity_id}
    for claim in sorted(issuer_claims, key=lambda row: (row["normalized_name"], row["uei"])):
        key = claim["normalized_name"]
        if key in entity_ids:
            continue
        # Two different normalized names can slug to one string ("a & b" and
        # "a and b"); a duplicate entity_id would fail admission outright.
        candidate_id = f"legal:{slug}:{_slug(key)}"
        suffix = 2
        while candidate_id in used_ids:
            candidate_id = f"legal:{slug}:{_slug(key)}-{suffix}"
            suffix += 1
        entity_ids[key] = candidate_id
        used_ids.add(candidate_id)

    # Edge ids ride on the de-duplicated entity ids, so a slug collision that the
    # loop above already resolved cannot reappear one field later.
    edge_ids = {
        # ``legal:<ticker>:<slug>`` -> ``<relationship>:<ticker>:<slug>``, so the
        # de-duplicating ``-2`` suffix travels with it.
        key: (
            f"issuer-identity:{entity_id.split(':', 1)[1]}"
            if key == registrant_key
            else f"ownership:{entity_id.split(':', 1)[1]}"
        )
        for key, entity_id in entity_ids.items()
    }

    award_refs_by_key: dict[str, list[str]] = {}
    for claim in issuer_claims:
        award_evidence_id = f"evidence:{slug}-usaspending-{claim['uei'].lower()}"
        evidence.append(
            _evidence_row(
                evidence_id=award_evidence_id,
                publisher="USAspending.gov",
                evidence_class="official_award",
                record_id=claim["award_id"],
                url=claim["award_url"],
                body=claim["award_body"],
                claim_scopes=["legal_entity", "exact_identifier", "ownership"],
                known_at=stamp,
                valid_from=_iso_midnight(claim["award_valid_from"]),
                retrieved_at=retrieved_at_by_url.get(claim["award_url"], ""),
            )
        )
        award_refs_by_key.setdefault(claim["normalized_name"], []).append(award_evidence_id)
        claim["evidence_ids"] = [
            tenk_evidence_id if claim["sec_role"] == "sec_registrant" else ex21_evidence_id,
            award_evidence_id,
        ]

    legal_entities.append(
        {
            "entity_id": registrant_entity_id,
            "canonical_name": issuer["registrant_name"],
            "verification_state": "reviewed",
            **_temporal(
                stamp, valid_from, [tenk_evidence_id, *award_refs_by_key.get(registrant_key, [])]
            ),
        }
    )
    ownership_edges.append(
        {
            "edge_id": edge_ids[registrant_key],
            "child_entity_id": registrant_entity_id,
            "parent_company_id": company_id,
            "relationship": "issuer_legal_entity",
            "economic_share": 1.0,
            "verification_state": "reviewed",
            **_temporal(stamp, valid_from, [tenk_evidence_id]),
        }
    )

    for key in sorted(entity_ids):
        if key == registrant_key:
            continue
        refs = [ex21_evidence_id, *award_refs_by_key.get(key, [])]
        display = next(
            claim["sec_name"] for claim in issuer_claims if claim["normalized_name"] == key
        )
        legal_entities.append(
            {
                "entity_id": entity_ids[key],
                "canonical_name": display,
                "verification_state": "reviewed",
                **_temporal(stamp, valid_from, refs),
            }
        )
        ownership_edges.append(
            {
                "edge_id": edge_ids[key],
                "child_entity_id": entity_ids[key],
                "parent_entity_id": registrant_entity_id,
                "relationship": "wholly_owned",
                "economic_share": 1.0,
                "verification_state": "reviewed",
                **_temporal(stamp, valid_from, refs),
            }
        )

    for claim in sorted(issuer_claims, key=lambda row: row["uei"]):
        key = claim["normalized_name"]
        entity_id = entity_ids[key]
        identifier_id = f"identifier:{slug}:{claim['uei'].lower()}"
        identifiers.append(
            {
                "identifier_id": identifier_id,
                "entity_id": entity_id,
                "namespace": "sam_uei",
                "value": claim["uei"],
                "verification_state": "reviewed",
                **_temporal(stamp, valid_from, [claim["evidence_ids"][-1]]),
            }
        )
        worksheet_edges.append(
            {
                "ticker": ticker,
                "company_id": company_id,
                "proposed_uei": claim["uei"],
                "sec_source_name": claim["sec_name"],
                "sec_source_role": claim["sec_role"],
                "sec_source_document": claim["sec_document"],
                "usaspending_recipient_names": claim["usaspending_recipient_names"],
                "normalized_join_key": key,
                "discovery_tickers_on_matched_rows": claim["discovery_tickers"],
                "discovery_ticker_agrees_with_proposal": claim["discovery_tickers"] == [ticker],
                "already_in_published_graph": claim["uei"] in published_ueis,
                "graph_rows": {
                    "legal_entity_id": entity_id,
                    "identifier_id": identifier_id,
                    "ownership_edge_id": edge_ids[key],
                },
                "evidence": [
                    {
                        "evidence_id": row["evidence_id"],
                        "publisher": row["publisher"],
                        "evidence_class": row["evidence_class"],
                        "record_id": row["record_id"],
                        "url": row["url"],
                        "content_sha256": row["content_sha256"],
                        "byte_length": row["byte_length"],
                    }
                    for row in evidence
                    if row["evidence_id"] in claim["evidence_ids"]
                ],
            }
        )

    return {
        "evidence": evidence,
        "companies": companies,
        "legal_entities": legal_entities,
        "identifiers": identifiers,
        "ownership_edges": ownership_edges,
        "worksheet_edges": worksheet_edges,
    }


def propose_recipient_graph(
    *,
    tickers: Sequence[str],
    award_rows: Sequence[Mapping[str, Any]],
    fetch: Fetch,
    known_at: datetime,
    graph_slug: str = "defense",
    published_graph: Mapping[str, Any] | None = None,
    now: Callable[[], datetime] | None = None,
) -> Proposal:
    """Build a candidate graph and its review worksheet from official documents.

    ``known_at`` is injected rather than read from the wall clock so a test can
    pin output bytes; it supplies the knowledge cutoff (which awards and filings
    a replay is allowed to have seen) and the floor for the run stamp.

    ``now`` is the SEPARATE clock that timestamps each fetch.  Every evidence
    row's ``retrieved_at`` is the moment its bytes arrived, so a receipt records
    an observation rather than repeating the run's own stamp; injecting it keeps
    the emitted bytes deterministic for a test.  Because a document cannot be
    read after the graph that cites it was known, the run stamp is
    ``max(known_at, last fetch)`` — with a backdated ``--as-of`` the stamp is the
    real completion time, and the cutoff stays where the operator put it.

    Economic validity (``valid_from``) comes from the documents themselves — the
    10-K period-of-report date for SEC-sourced claims and the award start date
    for the award receipt.
    """
    if known_at.tzinfo is None:
        raise ValueError("known_at must be timezone-aware")
    clock = now or (lambda: datetime.now(timezone.utc))
    cutoff = known_at.astimezone(timezone.utc).date()

    fetch_log: list[str] = []
    fetch_moments: list[datetime] = []
    retrieved_at_by_url: dict[str, str] = {}

    def _get(url: str) -> bytes:
        fetch_log.append(url)
        body = fetch(url)
        moment = clock()
        if moment.tzinfo is None:
            raise ValueError("the fetch clock must return a timezone-aware datetime")
        fetch_moments.append(moment)
        # First read wins: a URL read twice is the same document, and the receipt
        # should name when it was first observed.
        retrieved_at_by_url.setdefault(url, _iso(moment))
        return body

    def _get_json(url: str) -> Any:
        return json.loads(_get(url).decode("utf-8"))

    registry = _get_json(SEC_COMPANY_TICKERS_URL)
    cik_by_ticker: dict[str, int] = {}
    for row in (registry or {}).values():
        ticker = str((row or {}).get("ticker") or "").strip().upper()
        try:
            cik = int((row or {}).get("cik_str"))
        except (TypeError, ValueError):
            continue
        if ticker:
            cik_by_ticker.setdefault(ticker, cik)

    # --- the recipient pool, joined globally -------------------------------
    # Keyed by normalized recipient name so the discovery ticker cannot be a
    # precondition for a proposed edge.
    pool: dict[str, dict[str, list[Mapping[str, Any]]]] = {}
    collected_by_ticker: dict[str, int] = {}
    for row in award_rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        if ticker:
            collected_by_ticker[ticker] = collected_by_ticker.get(ticker, 0) + 1
        name = str(row.get("recipient_name") or "").strip()
        uei = str(row.get("recipient_uei") or "").strip().upper()
        if not name or not _UEI.fullmatch(uei):
            continue
        pool.setdefault(normalize_legal_name(name), {}).setdefault(uei, []).append(row)

    published_ueis: set[str] = set()
    for row in (published_graph or {}).get("identifiers", []) or []:
        if str(row.get("namespace") or "") == "sam_uei":
            published_ueis.add(str(row.get("value") or "").strip().upper())

    # --- per-issuer document walk ------------------------------------------
    issuers: dict[str, dict[str, Any]] = {}
    no_edge: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []

    for ticker in sorted({str(t).strip().upper() for t in tickers if str(t).strip()}):
        cik = cik_by_ticker.get(ticker)
        if cik is None:
            no_edge.append(
                {
                    "ticker": ticker,
                    "cause": "ticker_not_in_sec_registry",
                    "cause_detail": "SEC company_tickers.json carries no CIK for this ticker.",
                }
            )
            continue
        try:
            submissions = _get_json(SEC_SUBMISSIONS_URL.format(cik=cik))
            filing = _latest_10k(submissions)
            if filing is None:
                no_edge.append(
                    {
                        "ticker": ticker,
                        "cik": cik,
                        "cause": "no_10k_filing",
                        "cause_detail": "No 10-K in the SEC recent-submissions window.",
                    }
                )
                continue
            report_date = _as_date(filing["report_date"]) or _as_date(filing["filing_date"])
            if report_date is None or report_date > cutoff:
                no_edge.append(
                    {
                        "ticker": ticker,
                        "cik": cik,
                        "cause": "sec_lookup_failed",
                        "cause_detail": (
                            "Latest 10-K carries no usable period-of-report date at or "
                            f"before {cutoff.isoformat()}."
                        ),
                    }
                )
                continue
            index_document = _get_json(
                SEC_ARCHIVE_INDEX_URL.format(cik=cik, accession=filing["accession"])
            )
            ex21_name = select_ex21_filename(index_document)
            if ex21_name is None:
                no_edge.append(
                    {
                        "ticker": ticker,
                        "cik": cik,
                        "cause": "no_ex21_exhibit",
                        "cause_detail": (
                            f"Accession {filing['accession']} carries no EX-21 attachment; "
                            "subsidiary legal names cannot be read from an official document."
                        ),
                    }
                )
                continue
            tenk_url = SEC_ARCHIVE_FILE_URL.format(
                cik=cik, accession=filing["accession"], name=filing["primary_document"]
            )
            ex21_url = SEC_ARCHIVE_FILE_URL.format(
                cik=cik, accession=filing["accession"], name=ex21_name
            )
            tenk_body = _get(tenk_url)
            ex21_body = _get(ex21_url)
        except Exception as exc:  # noqa: BLE001 - a lookup failure is a reported state.
            no_edge.append(
                {
                    "ticker": ticker,
                    "cik": cik,
                    "cause": "sec_lookup_failed",
                    "cause_detail": f"{type(exc).__name__}: {str(exc)[:200]}",
                }
            )
            continue

        registrant_name = str(submissions.get("name") or "").strip()
        registrant_key = normalize_legal_name(registrant_name)
        if not registrant_key:
            # An unnamed registrant would still emit a legal-entity row, and one
            # blank canonical_name fails admission as ``missing_entity_display_name``
            # for the WHOLE candidate.  Name it here, for this issuer only.
            no_edge.append(
                {
                    "ticker": ticker,
                    "cik": cik,
                    "cause": "sec_lookup_failed",
                    "cause_detail": (
                        "The SEC submissions record carries no registrant name, so this "
                        "issuer has no legal entity to anchor an ownership walk. This is a "
                        "lookup gap at data.sec.gov, not a matching gap."
                    ),
                }
            )
            continue
        if not _filing_names_the_registrant(tenk_body, registrant_name):
            # The registrant name is read from data.sec.gov/submissions, a host
            # deliberately absent from the evidence allow-list — it is a lookup,
            # not a citation.  The 10-K is what gets CITED for public_company /
            # legal_entity / ownership, so the 10-K must actually name the
            # registrant or the citation is decoration.  This is the same rule the
            # award side enforces as ``award_receipt_missing_identifier``.
            no_edge.append(
                {
                    "ticker": ticker,
                    "cik": cik,
                    "cause": "registrant_name_not_in_filing",
                    "cause_detail": (
                        f"The fetched 10-K primary document {filing['primary_document']} "
                        f"does not name the registrant ({registrant_name}) it would be "
                        "cited for, so no SEC document supports the issuer identity."
                    ),
                }
            )
            continue

        sec_names: dict[str, dict[str, str]] = {
            registrant_key: {
                "display_name": registrant_name,
                "role": "sec_registrant",
                "sec_document": filing["primary_document"],
            }
        }
        ex21 = extract_ex21_lines(ex21_body.decode("utf-8", "ignore"))
        for subsidiary in ex21.names:
            key = normalize_legal_name(subsidiary)
            if not key or key in sec_names:
                # The registrant wins the key so the worksheet attributes the row
                # to the 10-K rather than the exhibit.  (The structural guarantee
                # that no entity holds both an issuer_legal_entity and a
                # wholly_owned edge is the registrant skip in _issuer_graph_rows.)
                continue
            sec_names[key] = {
                "display_name": subsidiary,
                "role": "ex21_subsidiary",
                "sec_document": ex21_name,
            }

        matched = 0
        for key in sorted(sec_names):
            for uei in sorted(pool.get(key, {})):
                rows = pool[key][uei]
                claims.append(
                    {
                        "ticker": ticker,
                        "normalized_name": key,
                        "uei": uei,
                        "sec_name": sec_names[key]["display_name"],
                        "sec_role": sec_names[key]["role"],
                        "sec_document": sec_names[key]["sec_document"],
                        "usaspending_recipient_names": sorted(
                            {str(row.get("recipient_name") or "").strip() for row in rows}
                        ),
                        "discovery_tickers": sorted(
                            {
                                str(row.get("ticker") or "").strip().upper()
                                for row in rows
                                if str(row.get("ticker") or "").strip()
                            }
                        ),
                        "rows": rows,
                    }
                )
                matched += 1

        issuers[ticker] = {
            "ticker": ticker,
            "cik": cik,
            "registrant_name": registrant_name,
            "accession": filing["accession"],
            "report_date": report_date,
            "primary_document": filing["primary_document"],
            "ex21_document": ex21_name,
            "tenk_url": tenk_url,
            "ex21_url": ex21_url,
            "tenk_body": tenk_body,
            "ex21_body": ex21_body,
            "sec_names": sec_names,
            "ex21_name_count": sum(
                1 for row in sec_names.values() if row["role"] == "ex21_subsidiary"
            ),
            # The extractor's own coverage, carried so a zero can be audited
            # rather than believed.  See the module docstring: a filter that
            # silently drops a real subsidiary turns "no exact issuer evidence"
            # into a false statement, and a count with samples is what lets a
            # reader tell the two apart without re-running the tool.
            "ex21_census": {
                "ex21_document": ex21_name,
                "ex21_lines_extracted": len(ex21.names),
                "ex21_lines_rejected": len(ex21.rejected),
                "ex21_rejected_samples": ex21.rejected_samples,
            },
        }
        if matched == 0:
            if collected_by_ticker.get(ticker, 0) == 0:
                no_edge.append(
                    {
                        "ticker": ticker,
                        "cik": cik,
                        "cause": "no_collected_recipients",
                        "cause_detail": (
                            "The collected USAspending award panel holds zero rows for this "
                            "issuer's discovery scope. This is an upstream COLLECTION gap, "
                            "not a matching gap — nothing was available to join against."
                        ),
                        "sec_names_considered": len(sec_names),
                        **issuers[ticker]["ex21_census"],
                    }
                )
            else:
                no_edge.append(
                    {
                        "ticker": ticker,
                        "cik": cik,
                        "cause": "no_exact_match",
                        "cause_detail": (
                            "No exact issuer evidence: not one collected recipient name equals "
                            "this registrant or any EX-21 subsidiary under the documented "
                            "normalization. The collected recipients are other companies. "
                            "This is a finished answer, not an outstanding mapping task — "
                            f"read it against the {len(ex21.names)} EX-21 name(s) extracted and "
                            f"the {len(ex21.rejected)} line(s) rejected, both listed here."
                        ),
                        "sec_names_considered": len(sec_names),
                        "collected_rows_in_discovery_scope": collected_by_ticker.get(ticker, 0),
                        **issuers[ticker]["ex21_census"],
                    }
                )

    # --- global identifier reconciliation ----------------------------------
    # A UEI is a single external identity.  If two issuers, or two entities of one
    # issuer, both claim it, the graph would fail admission with
    # ``ambiguous_exact_identifier_path``; refusing it here fails closed WITH a
    # reason an analyst can act on instead of shipping a graph that will not load.
    withheld: list[dict[str, Any]] = []
    by_uei: dict[str, list[dict[str, Any]]] = {}
    for claim in claims:
        by_uei.setdefault(claim["uei"], []).append(claim)

    admitted: list[dict[str, Any]] = []
    for uei in sorted(by_uei):
        group = by_uei[uei]
        owners = {claim["ticker"] for claim in group}
        entities = {(claim["ticker"], claim["normalized_name"]) for claim in group}
        if len(owners) > 1:
            withheld.append(
                {
                    "uei": uei,
                    "cause": "identifier_claimed_by_multiple_issuers",
                    "cause_detail": (
                        "Exact name matches under two issuers claim the same UEI: "
                        f"{sorted(owners)}. Withheld pending analyst adjudication."
                    ),
                    "tickers": sorted(owners),
                }
            )
            continue
        if len(entities) > 1:
            withheld.append(
                {
                    "uei": uei,
                    "cause": "identifier_maps_to_multiple_entities",
                    "cause_detail": (
                        "One UEI matched two distinct legal names for the same issuer: "
                        f"{sorted(name for _, name in entities)}."
                    ),
                    "tickers": sorted(owners),
                }
            )
            continue
        # A group of more than one claim must differ in ticker or in normalized
        # name — and both of those were just withheld above — so exactly one
        # claim reaches here.  Asserted rather than silently indexed: a future
        # refactor that lets duplicates through would otherwise drop rows without
        # a word.  (An earlier revision reconciled the group with a _merge_claims
        # helper that was, for this reason, unreachable; it was deleted.)
        assert len(group) == 1, f"unreconciled duplicate claim group for {uei}"
        admitted.append(group[0])

    # --- award receipts for the admitted identifiers ------------------------
    proposed: list[dict[str, Any]] = []
    for claim in admitted:
        # One representative award per identifier: the lowest award id among the
        # collected rows that carry an id and an economic start date at or before
        # the cutoff.  Selecting by id keeps a re-run byte-identical; the cutoff
        # keeps a future-dated award from becoming evidence the replay could not
        # have known.
        receipts = []
        for row in claim["rows"]:
            candidate_id = str(row.get("generated_award_id") or "").strip()
            started = _as_date(row.get("start_date")) or _as_date(row.get("base_obligation_date"))
            if candidate_id and started is not None and started <= cutoff:
                receipts.append((candidate_id, started))
        if not receipts:
            withheld.append(
                {
                    "uei": claim["uei"],
                    "cause": "no_award_receipt_before_as_of",
                    "cause_detail": (
                        "No collected award for this recipient carries an award id and a start "
                        f"date at or before {cutoff.isoformat()}, so no official award receipt "
                        "can be cited for the exact identifier."
                    ),
                    "tickers": [claim["ticker"]],
                }
            )
            continue
        award_id, award_started = min(receipts, key=lambda receipt: receipt[0])
        award_url = USASPENDING_AWARD_URL.format(award_id=quote(award_id, safe=""))
        try:
            award_body = _get(award_url)
        except Exception as exc:  # noqa: BLE001 - a fetch failure is a reported state.
            withheld.append(
                {
                    "uei": claim["uei"],
                    "cause": "award_receipt_fetch_failed",
                    "cause_detail": f"{type(exc).__name__}: {str(exc)[:200]}",
                    "tickers": [claim["ticker"]],
                }
            )
            continue
        if claim["uei"] not in award_body.decode("utf-8", "ignore").upper():
            # The receipt must itself carry the identifier it is cited for.
            # Without this the graph would cite a document that says nothing
            # about the UEI, which is exactly the unfalsifiable evidence the
            # lobe's admission gates exist to refuse.
            withheld.append(
                {
                    "uei": claim["uei"],
                    "cause": "award_receipt_missing_identifier",
                    "cause_detail": (
                        f"The fetched award record {award_id} does not contain the UEI it "
                        "would be cited for."
                    ),
                    "tickers": [claim["ticker"]],
                }
            )
            continue
        claim = dict(claim)
        claim["award_id"] = award_id
        claim["award_url"] = award_url
        claim["award_body"] = award_body
        claim["award_valid_from"] = award_started
        proposed.append(claim)

    # --- assemble the candidate graph --------------------------------------
    # Computed here, after the last fetch: a graph cannot be KNOWN before the
    # bytes that establish it arrived, so the stamp floors at the newest receipt.
    # Under an injected clock that returns times at or before ``known_at`` — every
    # test — the stamp is ``known_at`` exactly and the output bytes are pinned.
    stamp = _iso(max([known_at, *fetch_moments]))
    active_tickers = sorted({claim["ticker"] for claim in proposed})
    rows: dict[str, list[dict[str, Any]]] = {
        key: []
        for key in (
            "evidence",
            "companies",
            "legal_entities",
            "identifiers",
            "ownership_edges",
            "worksheet_edges",
        )
    }
    for ticker in active_tickers:
        for key, produced in _issuer_graph_rows(
            issuer=issuers[ticker],
            issuer_claims=[claim for claim in proposed if claim["ticker"] == ticker],
            stamp=stamp,
            published_ueis=published_ueis,
            retrieved_at_by_url=retrieved_at_by_url,
        ).items():
            rows[key].extend(produced)
    worksheet_edges = rows["worksheet_edges"]

    graph_id = f"{CANDIDATE_GRAPH_ID_PREFIX}{cutoff.isoformat()}:{graph_slug}"
    graph = {
        "contract": RECIPIENT_GRAPH_CONTRACT,
        "schema_version": RECIPIENT_GRAPH_SCHEMA_VERSION,
        "graph_id": graph_id,
        "graph_known_at": stamp,
        "graph_effective_at": stamp,
        "evidence": sorted(rows["evidence"], key=lambda row: row["evidence_id"]),
        "companies": sorted(rows["companies"], key=lambda row: row["company_id"]),
        "legal_entities": sorted(rows["legal_entities"], key=lambda row: row["entity_id"]),
        "identifiers": sorted(rows["identifiers"], key=lambda row: row["identifier_id"]),
        "ownership_edges": sorted(rows["ownership_edges"], key=lambda row: row["edge_id"]),
        "blocks": [],
        "conflicts": [],
        "overrides": [],
    }

    fully_withheld = sorted(
        {claim["ticker"] for claim in claims}
        - {claim["ticker"] for claim in proposed}
        - {row["ticker"] for row in no_edge}
    )
    for ticker in fully_withheld:
        no_edge.append(
            {
                "ticker": ticker,
                "cik": issuers[ticker]["cik"],
                "cause": "all_candidate_identifiers_withheld",
                "cause_detail": (
                    "Every exact name match for this issuer was withheld; see "
                    "withheld_identifiers for the per-identifier reason."
                ),
                **issuers[ticker]["ex21_census"],
            }
        )

    # Checked AFTER the last cause is appended: an invariant that runs before the
    # final writer cannot see what the final writer produced.
    for row in no_edge:
        assert row["cause"] in NO_EDGE_CAUSES, row["cause"]
    for row in withheld:
        assert row["cause"] in WITHHELD_CAUSES, row["cause"]

    worksheet = {
        "contract": PROPOSAL_CONTRACT,
        "schema_version": PROPOSAL_SCHEMA_VERSION,
        "review_state": "awaiting_analyst_review",
        "authority": dict(AUTHORITY),
        "generated_known_at": stamp,
        "candidate_graph_id": graph_id,
        "candidate_graph_is_unpublished": True,
        "canonical_graph_path": "data/government_revenue/recipient_entity_graph.json",
        "promotion": {
            "publisher": "scripts/curate_government_revenue_recipient_graph.py",
            "command": (
                "python3 -m scripts.curate_government_revenue_recipient_graph "
                f"--input <reviewed-graph.json> --as-of {cutoff.isoformat()}"
            ),
            "analyst_must": [
                "Re-mint graph_id from recipient-graph:candidate:… to "
                "recipient-graph:reviewed:… once the rows are actually reviewed.",
                "Merge with the currently published graph rather than replacing it; "
                "already_in_published_graph flags the overlap.",
                "Read every proposed edge below against its cited evidence URLs and "
                "delete the rows that do not survive.",
                "Update the structural counts asserted in "
                "tests/test_government_revenue_recipient_graph.py in the same change.",
            ],
        },
        "method": {
            "identity_source": "SEC company_tickers.json (ticker -> CIK)",
            "issuer_documents": "latest 10-K primary document + its EX-21 exhibit",
            "recipient_source": "collected USAspending award panel (recipient_name + recipient_uei)",
            "join_rule": "exact equality of normalized legal names",
            "normalization_rules": list(NORMALIZATION_RULES),
            "forbidden_inputs": list(FORBIDDEN_MAPPING_INPUTS),
            "discovery_ticker_role": (
                "scope selection and review metadata only; never a condition for an edge"
            ),
            "award_receipt_rule": (
                "the fetched award record must itself contain the UEI it is cited for"
            ),
        },
        "counts": {
            "issuers_requested": len({str(t).strip().upper() for t in tickers if str(t).strip()}),
            "issuers_with_proposed_edges": len(active_tickers),
            "proposed_identifier_edges": len(worksheet_edges),
            "proposed_legal_entities": len(graph["legal_entities"]),
            "issuers_without_edges": len(no_edge),
            "withheld_identifiers": len(withheld),
            "documents_fetched": len(fetch_log),
            "ex21_lines_extracted": sum(
                row["ex21_census"]["ex21_lines_extracted"] for row in issuers.values()
            ),
            "ex21_lines_rejected": sum(
                row["ex21_census"]["ex21_lines_rejected"] for row in issuers.values()
            ),
        },
        # The extractor's coverage for EVERY issuer whose EX-21 was read, not just
        # the ones that ended at zero: a reader checking a zero needs the same
        # number from an issuer that succeeded to know what normal looks like.
        "ex21_extraction": [
            {"ticker": ticker, **issuers[ticker]["ex21_census"]} for ticker in sorted(issuers)
        ],
        "proposed_edges": sorted(
            worksheet_edges, key=lambda row: (row["ticker"], row["proposed_uei"])
        ),
        "issuers_without_edges": sorted(no_edge, key=lambda row: (row["cause"], row["ticker"])),
        "withheld_identifiers": sorted(withheld, key=lambda row: (row["cause"], row["uei"])),
        "already_published_identifiers": sorted(
            row["proposed_uei"] for row in worksheet_edges if row["already_in_published_graph"]
        ),
        "limitations": [
            "This is a CANDIDATE. No row here has been reviewed by a human, and "
            "verification_state='reviewed' records the assertion the analyst is being "
            "asked to make, not one that has been made.",
            "valid_from on every SEC-sourced claim is the 10-K period-of-report date. "
            "Widen it only with evidence that the relationship held earlier.",
            "Ownership relationships are proposed as wholly_owned because an EX-21 lists "
            "significant subsidiaries without economic share. A partial or joint-venture "
            "holding must be corrected by the analyst before publication.",
            "An issuer reported with no_exact_match has no exact issuer evidence; that is a "
            "finished answer, not an outstanding mapping task.",
        ],
    }
    return Proposal(graph=graph, worksheet=worksheet, fetch_log=fetch_log)


# ---------------------------------------------------------------------------
# Rendering and output
# ---------------------------------------------------------------------------


def render_worksheet_markdown(worksheet: Mapping[str, Any]) -> str:
    """Render the worksheet as the document an analyst actually reads."""
    lines: list[str] = []
    counts = worksheet["counts"]
    lines.append("# Recipient entity graph — CANDIDATE for analyst review")
    lines.append("")
    lines.append(
        f"**Review state:** `{worksheet['review_state']}` · "
        f"**candidate graph id:** `{worksheet['candidate_graph_id']}`"
    )
    lines.append("")
    lines.append(
        "Nothing here is published. The canonical graph "
        f"(`{worksheet['canonical_graph_path']}`) is untouched and is written only by "
        f"`{worksheet['promotion']['publisher']}`."
    )
    lines.append("")
    lines.append(
        f"- Issuers requested: **{counts['issuers_requested']}** · "
        f"with proposed edges: **{counts['issuers_with_proposed_edges']}** · "
        f"without: **{counts['issuers_without_edges']}**"
    )
    lines.append(
        f"- Proposed identifier edges: **{counts['proposed_identifier_edges']}** · "
        f"withheld identifiers: **{counts['withheld_identifiers']}** · "
        f"documents fetched: **{counts['documents_fetched']}**"
    )
    lines.append("")

    lines.append("## How a proposed edge was derived")
    lines.append("")
    method = worksheet["method"]
    lines.append(f"- Ticker identity: {method['identity_source']}")
    lines.append(f"- Issuer documents: {method['issuer_documents']}")
    lines.append(f"- Recipient names: {method['recipient_source']}")
    lines.append(f"- Join: {method['join_rule']}")
    lines.append(f"- Award receipt: {method['award_receipt_rule']}")
    lines.append(f"- Discovery ticker: {method['discovery_ticker_role']}")
    lines.append("")
    lines.append("Normalization, in full:")
    lines.append("")
    for rule in method["normalization_rules"]:
        lines.append(f"1. {rule}")
    lines.append("")
    lines.append(f"Never used: {', '.join(method['forbidden_inputs'])}.")
    lines.append("")

    lines.append("## Proposed edges")
    lines.append("")
    if not worksheet["proposed_edges"]:
        lines.append("_None._")
        lines.append("")
    for edge in worksheet["proposed_edges"]:
        lines.append(f"### {edge['ticker']} → `{edge['proposed_uei']}`")
        lines.append("")
        lines.append(f"- SEC name ({edge['sec_source_role']}): **{edge['sec_source_name']}**")
        lines.append(f"- SEC document: `{edge['sec_source_document']}`")
        lines.append(
            "- USAspending recipient name(s): "
            + ", ".join(f"**{name}**" for name in edge["usaspending_recipient_names"])
        )
        lines.append(f"- Normalized join key: `{edge['normalized_join_key']}`")
        lines.append(
            "- Discovery ticker on the matched rows: "
            f"{', '.join(edge['discovery_tickers_on_matched_rows']) or 'none'}"
            + ("" if edge["discovery_ticker_agrees_with_proposal"] else "  ← DISAGREES, read closely")
        )
        if edge["already_in_published_graph"]:
            lines.append("- **Already present in the published graph** — merge, do not duplicate.")
        lines.append(
            "- Graph rows: "
            f"`{edge['graph_rows']['legal_entity_id']}` · "
            f"`{edge['graph_rows']['identifier_id']}` · "
            f"`{edge['graph_rows']['ownership_edge_id']}`"
        )
        lines.append("- Evidence:")
        for source in edge["evidence"]:
            lines.append(
                f"    - `{source['evidence_id']}` ({source['publisher']}, "
                f"{source['evidence_class']}, {source['byte_length']} bytes, "
                f"sha256 `{source['content_sha256'][:16]}…`) {source['url']}"
            )
        lines.append("")

    lines.append("## Issuers with no proposed edge, and why")
    lines.append("")
    if not worksheet["issuers_without_edges"]:
        lines.append("_None._")
        lines.append("")
    else:
        lines.append("| Issuer | Cause | EX-21 names kept / rejected | What it means |")
        lines.append("| --- | --- | --- | --- |")
        for row in worksheet["issuers_without_edges"]:
            detail = str(row["cause_detail"]).replace("|", "\\|")
            if "ex21_lines_extracted" in row:
                census = f"{row['ex21_lines_extracted']} / {row['ex21_lines_rejected']}"
            else:
                census = "no exhibit read"
            lines.append(f"| {row['ticker']} | `{row['cause']}` | {census} | {detail} |")
        lines.append("")
        # A zero is published here as a FINISHED verdict, so the lines the
        # extractor threw away are printed next to it rather than left in JSON.
        for row in worksheet["issuers_without_edges"]:
            for sample in row.get("ex21_rejected_samples") or []:
                lines.append(
                    f"- {row['ticker']} discarded EX-21 line "
                    f"`{str(sample['line']).replace('|', chr(92) + '|')}` "
                    f"({sample['reason']})"
                )
        lines.append("")

    if worksheet["withheld_identifiers"]:
        lines.append("## Identifiers withheld after an exact name match")
        lines.append("")
        lines.append("| UEI | Issuer(s) | Cause | Detail |")
        lines.append("| --- | --- | --- | --- |")
        for row in worksheet["withheld_identifiers"]:
            detail = str(row["cause_detail"]).replace("|", "\\|")
            lines.append(
                f"| `{row['uei']}` | {', '.join(row['tickers'])} | `{row['cause']}` | {detail} |"
            )
        lines.append("")

    lines.append("## To publish")
    lines.append("")
    for step in worksheet["promotion"]["analyst_must"]:
        lines.append(f"- [ ] {step}")
    lines.append("")
    lines.append("```")
    lines.append(worksheet["promotion"]["command"])
    lines.append("```")
    lines.append("")
    lines.append("## Limitations")
    lines.append("")
    for limitation in worksheet["limitations"]:
        lines.append(f"- {limitation}")
    lines.append("")
    return "\n".join(lines)


def guard_output_path(path: Path) -> Path:
    """Refuse any destination that is, or could be mistaken for, the canonical graph.

    Name equality is checked as well as path identity: a candidate sitting
    anywhere on disk under the canonical file name is one ``cp`` away from
    replacing a reviewed artifact with an unreviewed one, and the copy leaves no
    trace of which file was which.
    """
    resolved = path.resolve()
    if resolved == CANONICAL_GRAPH_PATH.resolve() or resolved.name == CANONICAL_GRAPH_PATH.name:
        raise ValueError(
            "this proposal tool never writes the canonical recipient graph; "
            f"refusing {path}. Publish with "
            "scripts/curate_government_revenue_recipient_graph.py instead."
        )
    return resolved


def write_proposal(proposal: Proposal, out_dir: Path) -> dict[str, Path]:
    """Write the candidate graph and both worksheet renderings; never the canonical file."""
    out_dir = Path(out_dir)
    paths = {
        "candidate_graph": out_dir / CANDIDATE_GRAPH_FILENAME,
        "worksheet_json": out_dir / WORKSHEET_JSON_FILENAME,
        "worksheet_markdown": out_dir / WORKSHEET_MARKDOWN_FILENAME,
    }
    for path in paths.values():
        guard_output_path(path)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths["candidate_graph"].write_text(
        json.dumps(proposal.graph, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    paths["worksheet_json"].write_text(
        json.dumps(proposal.worksheet, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    paths["worksheet_markdown"].write_text(
        render_worksheet_markdown(proposal.worksheet), encoding="utf-8"
    )
    return paths


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Iterable[str] | None = None, *, fetch: Fetch | None = None) -> int:
    """Run the walk, PROVE the candidate loads, then write it.

    ``fetch`` is injectable so the CLI surface itself — argument handling, the
    admission gate, the exit code, the annotation — can be exercised offline.
    Left unset it is the paced :class:`HttpFetcher`, the only component here that
    opens a socket.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Propose a candidate recipient entity graph from official SEC and "
            "USAspending documents. Never writes the canonical graph."
        )
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--user-agent",
        required=True,
        help=(
            "SEC fair-access User-Agent carrying a real contact, e.g. "
            "'MastermindX Government Revenue research (contact: you@example.com)'"
        ),
    )
    parser.add_argument(
        "--tickers",
        nargs="*",
        help="Issuer scope; defaults to data/government_revenue/entities.json.",
    )
    parser.add_argument("--awards", type=Path, default=DEFAULT_AWARDS_PATH)
    parser.add_argument("--entities", type=Path, default=DEFAULT_ENTITIES_PATH)
    parser.add_argument(
        "--published-graph",
        type=Path,
        default=CANONICAL_GRAPH_PATH,
        help="Read-only; used to flag identifiers already published.",
    )
    parser.add_argument(
        "--as-of",
        help="Inclusive UTC knowledge cutoff (YYYY-MM-DD); defaults to now.",
    )
    parser.add_argument("--graph-slug", default="defense")
    parser.add_argument("--pace-seconds", type=float, default=0.35)
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.as_of:
        known_at = datetime.fromisoformat(f"{args.as_of}T12:00:00+00:00")
    else:
        known_at = datetime.now(timezone.utc).replace(microsecond=0)

    cutoff = known_at.astimezone(timezone.utc).date()
    tickers = args.tickers or load_scope_tickers(args.entities)
    award_rows = load_award_rows(args.awards)
    published_graph = None
    if args.published_graph and Path(args.published_graph).exists():
        published_graph = json.loads(Path(args.published_graph).read_text(encoding="utf-8"))

    proposal = propose_recipient_graph(
        tickers=tickers,
        award_rows=award_rows,
        fetch=fetch or HttpFetcher(args.user_agent, pace_seconds=args.pace_seconds),
        known_at=known_at,
        graph_slug=args.graph_slug,
        published_graph=published_graph,
    )

    # The tool's own output is checked against the SAME admission gate the curate
    # script will apply, BEFORE anything is written.  Without this the failure
    # mode is a run that prints success over a document that cannot be loaded at
    # all — one slug collision, one blank registrant name, and the analyst is the
    # one who discovers it, days later, with no cause named.
    #
    # The as-of used HERE is the graph's own knowledge stamp, not ``--as-of``.
    # ``--as-of`` is the INPUT cutoff (which filings and awards a run is allowed
    # to have seen); the graph is stamped when its last document actually
    # arrived, so asking whether it loads "as of the cutoff" would only ever
    # re-measure the gap between the two clocks.  The curate script applies its
    # own as-of at publish time.
    stamped_on = str(proposal.graph["graph_known_at"])[:10]
    loaded = load_recipient_entity_graph(proposal.graph, as_of=stamped_on)
    if loaded.get("error_codes"):
        print(
            "::error title=govrev-recipient-proposal-unloadable::"
            + "the proposed candidate does not pass recipient-graph admission: "
            + ", ".join(str(code) for code in loaded["error_codes"]),
            flush=True,
        )
        print(
            "candidate REFUSED, nothing written: "
            f"status={loaded.get('status')} error_codes={loaded['error_codes']}"
        )
        return 2

    paths = write_proposal(proposal, args.out_dir)

    counts = proposal.worksheet["counts"]
    blocked = proposal.worksheet["issuers_without_edges"]
    if blocked:
        # A bare print: an annotation routed through a logger is prefixed with
        # the level and GitHub silently drops it.
        print(
            "::warning title=govrev-recipient-proposal-no-edges::"
            + f"{len(blocked)} issuer(s) produced no proposed edge: "
            + ", ".join(f"{row['ticker']}={row['cause']}" for row in blocked),
            flush=True,
        )
    print(
        f"candidate graph proposed: id={proposal.graph['graph_id']} "
        f"issuers={counts['issuers_with_proposed_edges']}/{counts['issuers_requested']} "
        f"edges={counts['proposed_identifier_edges']} "
        f"withheld={counts['withheld_identifiers']} "
        f"admission={loaded.get('status')} "
        f"known_at={proposal.graph['graph_known_at']} cutoff={cutoff.isoformat()} "
        f"ex21_lines={counts['ex21_lines_extracted']}kept/"
        f"{counts['ex21_lines_rejected']}rejected"
    )
    for label in ("candidate_graph", "worksheet_json", "worksheet_markdown"):
        print(f"  {label}: {paths[label]}")
    print("  NOT PUBLISHED — review the worksheet, then run the curate script.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
