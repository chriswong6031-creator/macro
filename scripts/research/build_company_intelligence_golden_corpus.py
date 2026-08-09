#!/usr/bin/env python3
"""Build the Company Intelligence golden corpus (Earnings/Company Event Suite R0-D).

WHAT THIS IS.  A frozen benchmark that Wave 1's event/document/claim convergence
layer is graded against.  It is *not* a signal, a ranking, or an input to any
shipped number: every authority flag in the manifest is false and the artifact is
``research_only``.

WHAT IS REAL AND WHAT IS SYNTHETIC.  Ticker symbols and issuer names are public
identifiers and are real.  Every document BODY is synthetic prose written for this
corpus -- no third-party transcript, press release, or filing text is copied into
the repository, and the corpus deliberately stores minimal synthetic excerpts plus
real cryptographic hashes rather than bulk raw sources.  CIK numbers, accession
numbers, and generation ids are format-valid but synthetic; they exercise the
identity SHAPE without asserting a fact about a real filing.

WHAT IS LOAD-BEARING.  Every hash in the corpus is a real sha256 over bytes that
are committed here, computed with the SAME functions the production path uses
(``engine.earnings_narrative.contracts.canonical_transcript_body_bytes`` for
transcript bodies, ``receipt_for_span`` for exact-span receipts).  A receipt that
cannot be byte-replayed against its committed body is worthless, so the replay
suite re-derives every one of them.

DETERMINISM.  This builder is pure: no clock, no network, no randomness beyond a
seeded ``random.Random``.  Re-running it must reproduce the committed bytes
exactly; ``tests/test_company_intelligence_golden_corpus.py`` asserts that, so an
edit here without a re-run goes red.

Usage::

    python3 scripts/research/build_company_intelligence_golden_corpus.py          # write
    python3 scripts/research/build_company_intelligence_golden_corpus.py --check  # verify
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import random
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from engine.company_intelligence.contracts import (  # noqa: E402
    AUTHORITY,
    CONTEXT_SCHEMA,
    MANIFEST_SCHEMA,
    PUBLIC_METRICS,
    stable_event_id,
)
from engine.company_intelligence.contracts import event_key as cie_event_key  # noqa: E402
from engine.earnings_narrative.contracts import (  # noqa: E402
    TERMINAL_TRANSCRIPT_SCHEMA,
    canonical_transcript_body_bytes,
    receipt_for_span,
    sha256_bytes,
)
from engine.earnings_narrative.contracts import event_key as narrative_event_key  # noqa: E402

CORPUS_SCHEMA = "company_intelligence.golden_corpus/v1"
# Frozen on purpose: a benchmark whose manifest changes on every rebuild cannot be
# hash-gated.  Bump only when the corpus is deliberately re-cut.
GENERATED_UTC = "2026-08-06T00:00:00+00:00"
SEED = 20260806

MANIFEST_PATH = ROOT / "research" / "company_intelligence" / "GOLDEN_CORPUS_MANIFEST.json"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "company_intelligence"
BUILDER_REL = "scripts/research/build_company_intelligence_golden_corpus.py"

ISSUERS_FIXTURE = "golden_corpus_issuers.v1.json"
DOCUMENTS_FIXTURE = "golden_corpus_documents.v1.json"
CONTEXTS_FIXTURE = "golden_corpus_v1_contexts.v1.json"
MANIFESTS_FIXTURE = "golden_corpus_v1_manifests.v1.json"
EDGAR_FIXTURE = "golden_corpus_edgar_identity.v1.json"

# ─────────────────────────────────────────────────────────────────────────────
# Difficulty taxonomy.  Every class named in the R0-D ticket is here, plus the
# EDGAR identity join, which the ticket calls out as the hardest one in the
# program and which no existing code can perform at all today.
# ─────────────────────────────────────────────────────────────────────────────

# class -> (target case count, expected v2 outcome, one-line definition)
DIFFICULTY_CLASSES: dict[str, tuple[int, str, str]] = {
    "fiscal_year_ambiguity": (
        16, "exact_receipt",
        "The issuer's fiscal label and the calendar period disagree; a Q4 call in "
        "January belongs to the PRIOR fiscal year for some issuers and the next for others.",
    ),
    "amendment": (
        16, "exact_receipt",
        "A later filing/revision corrects an earlier one for the same logical event. "
        "Event identity must survive; every derivative built on the old revision must be invalidated.",
    ),
    "duplicate_release": (
        14, "duplicate_collapsed",
        "The same release reaches the estate twice (wire + EDGAR exhibit, or a re-issued "
        "newswire copy). Two documents, ONE event -- a second event would inflate coverage.",
    ),
    "share_class": (
        16, "exact_receipt",
        "One issuer, several listed share classes. Claims belong to the ISSUER; the listing "
        "is a projection. Today both id schemes are ticker-keyed, so a share class mints a second event.",
    ),
    "dual_listing": (
        20, "exact_receipt",
        "One issuer listed on several venues (ADR + home line). Same event, different symbol, "
        "different reporting currency, sometimes a different reporting calendar.",
    ),
    "gaap_vs_non_gaap": (
        16, "exact_receipt",
        "The same metric name carries two bases in one document. A number without an explicit "
        "basis is absent, not guessed.",
    ),
    "units_currency": (
        14, "exact_receipt",
        "Thousands vs millions vs billions, reporting currency vs presentation currency, "
        "percent vs basis points. A unitless number is absent.",
    ),
    "bank_basis": (
        12, "exact_receipt",
        "Bank reporting has no 'revenue' line in the industrial sense: net interest income, "
        "non-interest income, provisions, NIM, CET1. A generic revenue extractor silently mis-reads these.",
    ),
    "insurer_basis": (
        10, "exact_receipt",
        "Insurer reporting is premium/combined-ratio/reserve-development shaped; "
        "'operating earnings' is an industry non-GAAP measure with a defined reconciliation.",
    ),
    "reit_basis": (
        12, "exact_receipt",
        "REIT headline earnings are FFO/AFFO/NOI, not EPS. Mapping FFO onto EPS is a "
        "category error that survives every numeric sanity check.",
    ),
    "missing_transcript": (
        14, "typed_absence",
        "The release exists, the call transcript does not (no call held, embargoed, or "
        "provider gap). Must render a typed absence, never an empty string or a guess.",
    ),
    "missing_release": (
        12, "typed_absence",
        "A transcript exists with no machine-readable release/8-K bound to it. Numeric "
        "claims have no primary document to point at.",
    ),
    "pdf_table": (
        14, "exact_receipt",
        "The number lives only in a PDF table cell. The receipt must address a CELL "
        "(page, table, row, column), not a text span; a scanned-image table is a typed absence.",
    ),
    "changed_slide_family": (
        12, "typed_absence",
        "The issuer's slide deck drops, renames, or restructures a recurring exhibit. "
        "The prior series must not be silently continued onto a different definition.",
    ),
    "speaker_role_error": (
        12, "exact_receipt",
        "The transcript's speaker/role attribution is wrong or unresolved (analyst tagged as "
        "management, operator tagged as CFO). The SPAN stays exact; the ROLE is a separate correctable field.",
    ),
    "future_dated_quarantine": (
        10, "quarantined",
        "The record carries a period or timestamp later than the observation time. It must be "
        "quarantined, never published -- this is the shape that lets a consumer outrun its source.",
    ),
    "edgar_identity_join": (
        14, "typed_absence",
        "The two EDGAR readers in this estate capture DISJOINT keys for the same filing "
        "(see manifest.known_limits) and cannot be joined today.",
    ),
}

EXPECTED_OUTCOMES = frozenset({"exact_receipt", "typed_absence", "quarantined", "duplicate_collapsed"})

# An exact receipt is not one shape.  A number in a PDF supplement is addressed by
# CELL and one on a slide by REGION; only a spoken/written text span is addressable
# by the byte-span receipt that exists in code today.  Committing a text-span receipt
# for a table-cell case would quietly assert the number lives somewhere it does not.
RECEIPT_LOCATOR_KINDS = {"pdf_table": "table_cell", "changed_slide_family": "slide_region"}
DEFAULT_LOCATOR_KIND = "text_span"

# The corpus's frozen observation time.  Everything at or before it is observable;
# anything after it is unobservable and must be quarantined, never published.
OBSERVED_AT = "2026-08-06T00:00:00+00:00"
OBSERVED_DATE = OBSERVED_AT[:10]
OBSERVED_YEARS = (2024, 2025, 2026)
FUTURE_YEARS = (2027, 2028)

# Classes restricted to a matching issuer kind.
CLASS_KIND: dict[str, str] = {
    "bank_basis": "bank",
    "insurer_basis": "insurer",
    "reit_basis": "reit",
    "share_class": "multi_class",
    "dual_listing": "dual_listed",
}

# ─────────────────────────────────────────────────────────────────────────────
# Issuer registry.  Real symbols; synthetic CIKs; fiscal-year-end months chosen to
# make the fiscal-ambiguity class genuinely ambiguous rather than decorative.
# (ticker, display name, kind, fiscal-year-end month, extra listings)
# ─────────────────────────────────────────────────────────────────────────────

_BANKS = [
    ("JPM", "JPMorgan Chase & Co."), ("BAC", "Bank of America Corporation"),
    ("WFC", "Wells Fargo & Company"), ("C", "Citigroup Inc."),
    ("GS", "The Goldman Sachs Group, Inc."), ("MS", "Morgan Stanley"),
    ("USB", "U.S. Bancorp"), ("PNC", "The PNC Financial Services Group, Inc."),
    ("TFC", "Truist Financial Corporation"), ("SCHW", "The Charles Schwab Corporation"),
    ("BK", "The Bank of New York Mellon Corporation"), ("STT", "State Street Corporation"),
]
_INSURERS = [
    ("PGR", "The Progressive Corporation"), ("ALL", "The Allstate Corporation"),
    ("TRV", "The Travelers Companies, Inc."), ("CB", "Chubb Limited"),
    ("AIG", "American International Group, Inc."), ("MET", "MetLife, Inc."),
    ("PRU", "Prudential Financial, Inc."), ("AFL", "Aflac Incorporated"),
    ("HIG", "The Hartford Insurance Group, Inc."), ("CINF", "Cincinnati Financial Corporation"),
]
_REITS = [
    ("O", "Realty Income Corporation"), ("SPG", "Simon Property Group, Inc."),
    ("PLD", "Prologis, Inc."), ("AMT", "American Tower Corporation"),
    ("EQIX", "Equinix, Inc."), ("PSA", "Public Storage"),
    ("VTR", "Ventas, Inc."), ("WELL", "Welltower Inc."),
    ("DLR", "Digital Realty Trust, Inc."), ("AVB", "AvalonBay Communities, Inc."),
    ("EQR", "Equity Residential"), ("IRM", "Iron Mountain Incorporated"),
]
# Multi-share-class issuers: (primary, name, [(ticker, class label)])
_MULTI_CLASS = [
    ("GOOGL", "Alphabet Inc.", [("GOOGL", "A"), ("GOOG", "C")]),
    ("BRK.B", "Berkshire Hathaway Inc.", [("BRK.A", "A"), ("BRK.B", "B")]),
    ("FOXA", "Fox Corporation", [("FOXA", "A"), ("FOX", "B")]),
    ("LEN", "Lennar Corporation", [("LEN", "A"), ("LEN.B", "B")]),
    ("HEI", "HEICO Corporation", [("HEI", "common"), ("HEI.A", "A")]),
    ("MOG.A", "Moog Inc.", [("MOG.A", "A"), ("MOG.B", "B")]),
    ("CWEN", "Clearway Energy, Inc.", [("CWEN", "C"), ("CWEN.A", "A")]),
    ("UHAL", "U-Haul Holding Company", [("UHAL", "common"), ("UHAL.B", "N")]),
]
# Dual-listed issuers: (primary/ADR, name, home line, home MIC, reporting currency)
_DUAL_LISTED = [
    ("RY", "Royal Bank of Canada", "RY.TO", "XTSE", "CAD"),
    ("BHP", "BHP Group Limited", "BHP.AX", "XASX", "USD"),
    ("SHEL", "Shell plc", "SHEL.L", "XLON", "USD"),
    ("BP", "BP p.l.c.", "BP.L", "XLON", "USD"),
    ("TSM", "Taiwan Semiconductor Manufacturing Company Limited", "2330.TW", "XTAI", "TWD"),
    ("RIO", "Rio Tinto Group", "RIO.L", "XLON", "USD"),
    ("UL", "Unilever PLC", "UL.L", "XLON", "EUR"),
    ("AZN", "AstraZeneca PLC", "AZN.L", "XLON", "USD"),
    ("HSBC", "HSBC Holdings plc", "0005.HK", "XHKG", "USD"),
    ("SAP", "SAP SE", "SAP.DE", "XETR", "EUR"),
]
# General issuers, with the fiscal-year-end month that makes their labelling hard.
_GENERAL = [
    ("AAPL", "Apple Inc.", 9), ("MSFT", "Microsoft Corporation", 6),
    ("NVDA", "NVIDIA Corporation", 1), ("AMZN", "Amazon.com, Inc.", 12),
    ("META", "Meta Platforms, Inc.", 12), ("TSLA", "Tesla, Inc.", 12),
    ("AVGO", "Broadcom Inc.", 10), ("AMD", "Advanced Micro Devices, Inc.", 12),
    ("MU", "Micron Technology, Inc.", 8), ("QCOM", "QUALCOMM Incorporated", 9),
    ("ORCL", "Oracle Corporation", 5), ("CRM", "Salesforce, Inc.", 1),
    ("ADBE", "Adobe Inc.", 11), ("NOW", "ServiceNow, Inc.", 12),
    ("PANW", "Palo Alto Networks, Inc.", 7), ("ANET", "Arista Networks, Inc.", 12),
    ("IBM", "International Business Machines Corporation", 12), ("INTC", "Intel Corporation", 12),
    ("TXN", "Texas Instruments Incorporated", 12), ("ADI", "Analog Devices, Inc.", 10),
    ("LRCX", "Lam Research Corporation", 6), ("AMAT", "Applied Materials, Inc.", 10),
    ("KLAC", "KLA Corporation", 6), ("MRVL", "Marvell Technology, Inc.", 1),
    ("CSCO", "Cisco Systems, Inc.", 7), ("ACN", "Accenture plc", 8),
    ("INTU", "Intuit Inc.", 7), ("SNPS", "Synopsys, Inc.", 10),
    ("CDNS", "Cadence Design Systems, Inc.", 12), ("WDAY", "Workday, Inc.", 1),
    ("TEAM", "Atlassian Corporation", 6), ("DDOG", "Datadog, Inc.", 12),
    ("SNOW", "Snowflake Inc.", 1), ("NET", "Cloudflare, Inc.", 12),
    ("CRWD", "CrowdStrike Holdings, Inc.", 1), ("ZS", "Zscaler, Inc.", 7),
    ("MDB", "MongoDB, Inc.", 1), ("HUBS", "HubSpot, Inc.", 12),
    ("OKTA", "Okta, Inc.", 1), ("TWLO", "Twilio Inc.", 12),
    ("SHOP", "Shopify Inc.", 12), ("PYPL", "PayPal Holdings, Inc.", 12),
    ("ABNB", "Airbnb, Inc.", 12), ("UBER", "Uber Technologies, Inc.", 12),
    ("DASH", "DoorDash, Inc.", 12), ("RBLX", "Roblox Corporation", 12),
    ("PLTR", "Palantir Technologies Inc.", 12), ("SPOT", "Spotify Technology S.A.", 12),
    ("WMT", "Walmart Inc.", 1), ("COST", "Costco Wholesale Corporation", 8),
    ("TGT", "Target Corporation", 1), ("HD", "The Home Depot, Inc.", 1),
    ("LOW", "Lowe's Companies, Inc.", 1), ("NKE", "NIKE, Inc.", 5),
    ("SBUX", "Starbucks Corporation", 9), ("MCD", "McDonald's Corporation", 12),
    ("PG", "The Procter & Gamble Company", 6), ("KO", "The Coca-Cola Company", 12),
    ("PEP", "PepsiCo, Inc.", 12), ("CVS", "CVS Health Corporation", 12),
    ("UNH", "UnitedHealth Group Incorporated", 12), ("JNJ", "Johnson & Johnson", 12),
    ("PFE", "Pfizer Inc.", 12), ("MRK", "Merck & Co., Inc.", 12),
    ("LLY", "Eli Lilly and Company", 12), ("ABBV", "AbbVie Inc.", 12),
    ("XOM", "Exxon Mobil Corporation", 12), ("CVX", "Chevron Corporation", 12),
    ("COP", "ConocoPhillips", 12), ("CAT", "Caterpillar Inc.", 12),
    ("DE", "Deere & Company", 10), ("BA", "The Boeing Company", 12),
    ("GE", "GE Aerospace", 12), ("HON", "Honeywell International Inc.", 12),
    ("UPS", "United Parcel Service, Inc.", 12), ("FDX", "FedEx Corporation", 5),
    ("DAL", "Delta Air Lines, Inc.", 12), ("UAL", "United Airlines Holdings, Inc.", 12),
]

_MIC_PRIMARY = "XNAS"

_ROLE_POOL = [
    ("Chief Executive Officer", "management"),
    ("Chief Financial Officer", "management"),
    ("Head of Investor Relations", "management"),
    ("Analyst, Ridgeline Research", "analyst"),
    ("Analyst, Kestrel Securities", "analyst"),
    ("Operator", "operator"),
]


def _cik(ticker: str) -> int:
    """Format-valid, deterministic, SYNTHETIC CIK. Not a real EDGAR identifier."""
    return 1_000_000 + int(sha256(ticker.encode("utf-8")).hexdigest()[:8], 16) % 700_000


def _accession(ticker: str, salt: str, fiscal_year: int) -> str:
    """EDGAR accession SHAPE: <10-digit filer cik>-<2-digit year>-<6-digit sequence>."""
    digest = sha256(f"{ticker}|{salt}".encode("utf-8")).hexdigest()
    sequence = int(digest[10:16], 16) % 10**6
    return f"{_cik(ticker):010d}-{fiscal_year % 100:02d}-{sequence:06d}"


def build_issuers() -> list[dict[str, Any]]:
    issuers: list[dict[str, Any]] = []

    def add(primary: str, name: str, kind: str, fy_end: int, listings: list[dict[str, Any]],
            reporting_currency: str = "USD") -> None:
        issuers.append({
            "issuer_id": "iss_" + sha256(primary.encode("utf-8")).hexdigest()[:16],
            "display_name": name,
            "kind": kind,
            "primary_ticker": primary,
            "fiscal_year_end_month": fy_end,
            "reporting_currency": reporting_currency,
            "cik_synthetic": _cik(primary),
            "listings": listings,
        })

    def common(ticker: str, mic: str = _MIC_PRIMARY, share_class: str = "common",
               primary: bool = True, currency: str = "USD") -> dict[str, Any]:
        return {"ticker": ticker, "mic": mic, "share_class": share_class,
                "is_primary": primary, "trading_currency": currency}

    for ticker, name in _BANKS:
        add(ticker, name, "bank", 12, [common(ticker, "XNYS")])
    for ticker, name in _INSURERS:
        add(ticker, name, "insurer", 12, [common(ticker, "XNYS")])
    for ticker, name in _REITS:
        add(ticker, name, "reit", 12, [common(ticker, "XNYS")])
    for primary, name, classes in _MULTI_CLASS:
        add(primary, name, "multi_class", 12, [
            common(t, "XNYS" if "." in t else _MIC_PRIMARY, label, t == primary)
            for t, label in classes
        ])
    for adr, name, home, home_mic, currency in _DUAL_LISTED:
        add(adr, name, "dual_listed", 12, [
            common(adr, "XNYS", "ADR", True, "USD"),
            common(home, home_mic, "ordinary", False, currency),
        ], reporting_currency=currency)
    for ticker, name, fy_end in _GENERAL:
        add(ticker, name, "general", fy_end, [common(ticker)])

    issuers.sort(key=lambda row: row["primary_ticker"])
    return issuers


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic document bodies.  Written for this corpus; no third-party text.
# ─────────────────────────────────────────────────────────────────────────────

_SEGMENT_TEMPLATES = {
    "general": (
        "Total revenue was {revenue} for the quarter, and non-GAAP diluted earnings per share "
        "were {eps}. Operating margin finished at {margin}. We are guiding next quarter to a "
        "range of {guide_low} to {guide_high}."
    ),
    "bank": (
        "Net interest income was {revenue} for the quarter and the net interest margin was "
        "{margin}. Provision for credit losses was {reserve}, and our CET1 ratio ended the "
        "period at {ratio}."
    ),
    "insurer": (
        "Net premiums written were {revenue} and the combined ratio was {ratio}. Operating "
        "earnings per share, which excludes realized investment gains, were {eps}. Prior-year "
        "reserve development was favourable by {reserve}."
    ),
    "reit": (
        "Funds from operations were {revenue} for the quarter, or {eps} per diluted share. "
        "Same-store net operating income grew {margin}, and we are narrowing full-year AFFO "
        "guidance to {eps_low} to {eps_high} per share."
    ),
}

_ANALYST_TEMPLATE = (
    "Thanks for taking the question. Can you walk through how much of the {margin} move is mix "
    "versus pricing, and whether you expect the same input costs to carry into next quarter?"
)

_OPERATOR_TEMPLATE = (
    "Good afternoon and welcome to the {name} {period} earnings conference call. All participants "
    "will be in listen-only mode. Please note this event is being recorded."
)


# Per-kind magnitude envelopes.  Realism matters here: a corpus whose bank prints a
# 56% net interest margin trains nobody's extractor and teaches a reviewer nothing.
# (headline $bn low, high), (margin/growth %, tenths), (ratio %, tenths), ($mm low, high)
_ENVELOPE = {
    "general": ((10, 1_800), (60, 480), None, None),        # revenue $1.0-180.0bn, op margin 6-48%
    "bank":    ((15, 260), (15, 46), (105, 156), (50, 2_800)),  # NII, NIM 1.5-4.6%, CET1 10.5-15.6%, provision
    "insurer": ((15, 190), (15, 46), (880, 1_052), (20, 460)),       # NPW, --, combined ratio, PYD
    "reit":    ((2, 26), (5, 92), None, None),              # FFO $0.2-2.6bn, same-store NOI 0.5-9.2%
}


def build_document(issuer: dict[str, Any], ticker: str, fiscal_year: int, fiscal_quarter: int,
                   call_date: str, rng: random.Random) -> dict[str, Any]:
    """A ``mastermind.tx/v1``-shaped synthetic transcript body."""
    kind = issuer["kind"] if issuer["kind"] in _SEGMENT_TEMPLATES else "general"
    period = f"Q{fiscal_quarter} {fiscal_year}"
    headline, margin_band, ratio_band, small_band = _ENVELOPE[kind]

    revenue = rng.randrange(*headline) / 10
    # Guidance is a RANGE anchored on the headline, built numerically so low never
    # exceeds high and neither is an order of magnitude away from what was reported.
    guide_lo = revenue * (1 + rng.randrange(-8, 5) / 100)
    guide_hi = guide_lo * (1 + rng.randrange(2, 10) / 100)
    eps = rng.randrange(35, 1_450) / 100 if kind != "reit" else rng.randrange(30, 320) / 100
    eps_lo = eps * (1 + rng.randrange(-6, 3) / 100)
    eps_hi = eps_lo * (1 + rng.randrange(3, 12) / 100)

    fields = {
        "revenue": f"${revenue:,.1f} billion",
        "eps": f"${eps:.2f}",
        "margin": f"{rng.randrange(*margin_band) / 10:.1f}%",
        "guide_low": f"${guide_lo:,.1f} billion",
        "guide_high": f"${guide_hi:,.1f} billion",
        "eps_low": f"${eps_lo:.2f}",
        "eps_high": f"${eps_hi:.2f}",
        "ratio": f"{rng.randrange(*ratio_band) / 10:.1f}%" if ratio_band else "",
        "reserve": f"${rng.randrange(*small_band):,} million" if small_band else "",
        "name": issuer["display_name"], "period": period,
    }
    speakers = [
        ("Operator", "Operator", _OPERATOR_TEMPLATE.format(**fields)),
        ("Dana Whitfield", "Chief Executive Officer",
         f"{issuer['display_name']} closed {period} with demand broadly in line with the plan we "
         f"laid out ninety days ago, and we exited the quarter with the cost base we committed to."),
        ("Miren Okafor", "Chief Financial Officer", _SEGMENT_TEMPLATES[kind].format(**fields)),
        ("Priya Raghunathan", "Analyst, Ridgeline Research", _ANALYST_TEMPLATE.format(**fields)),
    ]
    return {
        "schema": TERMINAL_TRANSCRIPT_SCHEMA,
        "ticker": ticker,
        "id": f"{fiscal_year}Q{fiscal_quarter}",
        "period": period,
        "date": call_date,
        "title": f"{issuer['display_name']} {period} Earnings Call",
        "segments": [{"speaker": s, "role": r, "text": t} for s, r, t in speakers],
    }


def _quotable_span(segment_text: str, rng: random.Random) -> tuple[int, int, str]:
    """Pick a sentence-aligned UTF-8 byte span inside one segment."""
    raw = segment_text.encode("utf-8")
    sentences: list[tuple[int, int]] = []
    start = 0
    for index, char in enumerate(raw):
        if char != ord("."):
            continue
        # "$120.5 billion" and "62.0%" both contain a period that is not a sentence
        # end.  Require a non-digit before it and a space (or end of text) after.
        if index and raw[index - 1:index].isdigit():
            continue
        if index + 1 < len(raw) and raw[index + 1:index + 2] != b" ":
            continue
        sentences.append((start, index + 1))
        start = index + 2 if index + 1 < len(raw) else index + 1
    if not sentences:
        sentences = [(0, len(raw))]
    chosen_start, chosen_end = sentences[rng.randrange(len(sentences))]
    while chosen_start < chosen_end and raw[chosen_start:chosen_start + 1] == b" ":
        chosen_start += 1
    return chosen_start, chosen_end, raw[chosen_start:chosen_end].decode("utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Case construction
# ─────────────────────────────────────────────────────────────────────────────

_QUARTER_CALL_DAY = {1: ("02", "12"), 2: ("05", "07"), 3: ("08", "06"), 4: ("11", "04")}


def _call_date(fiscal_year: int, fiscal_quarter: int, offset: int) -> str:
    month, day = _QUARTER_CALL_DAY[fiscal_quarter]
    return f"{fiscal_year}-{month}-{int(day) + (offset % 14):02d}"


def _pick_period(cls: str, ticker: str, index: int,
                 used: set[tuple[str, int, int]]) -> tuple[int, int, str]:
    """Choose an unused (fiscal_year, fiscal_quarter) with the right observability.

    A 2026-Q3 call lands in August, AFTER the corpus's frozen observation time, so it
    is not an observable record at all — only the future_dated_quarantine class may
    hold one.  Filtering here rather than trusting the year keeps the quarantine class
    the only future-dated one in the corpus, which is what makes it isolate anything.
    """
    want_future = cls == "future_dated_quarantine"
    years = FUTURE_YEARS if want_future else OBSERVED_YEARS
    candidates = [(year, quarter) for year in years for quarter in (1, 2, 3, 4)]
    for step in range(len(candidates)):
        fiscal_year, fiscal_quarter = candidates[(index + step) % len(candidates)]
        if (ticker, fiscal_year, fiscal_quarter) in used:
            continue
        call_date = _call_date(fiscal_year, fiscal_quarter, index)
        if (call_date > OBSERVED_DATE) is want_future:
            return fiscal_year, fiscal_quarter, call_date
    raise SystemExit(f"no {'future' if want_future else 'observable'} period left for {ticker}")


def _class_label(cls: str, issuer: dict[str, Any], ticker: str) -> str:
    name = issuer["display_name"]
    fy_end = issuer["fiscal_year_end_month"]
    return {
        "fiscal_year_ambiguity":
            f"{name} closes its fiscal year in month {fy_end:02d}; the calendar quarter of this "
            f"call maps to a DIFFERENT fiscal label than a December-year issuer's would.",
        "amendment":
            f"{ticker} filed an amended release after the original; the amended revision restates "
            f"one reported figure while the logical event is unchanged.",
        "duplicate_release":
            f"{ticker}'s release arrived twice (newswire copy and EDGAR exhibit) with different "
            f"document hashes and the same content payload.",
        "share_class":
            f"{ticker} is one listed class of {name}; the sibling class reports the identical "
            f"issuer event under a different symbol.",
        "dual_listing":
            f"{ticker} is one venue line of {name}; the home line reports the same event in "
            f"{issuer['reporting_currency']}.",
        "gaap_vs_non_gaap":
            f"{ticker} reports the headline metric on both a GAAP and a non-GAAP basis in the "
            f"same document, with a reconciliation table between them.",
        "units_currency":
            f"{ticker} presents the figure in a scale/currency that differs from the estate's "
            f"normalized presentation; the raw number is ambiguous without its unit.",
        "bank_basis":
            f"{name} has no industrial revenue line; the comparable figure is net interest income "
            f"plus non-interest income, and the margin figure is NIM.",
        "insurer_basis":
            f"{name} reports premiums and a combined ratio; 'operating earnings' is a defined "
            f"industry non-GAAP measure, not GAAP net income.",
        "reit_basis":
            f"{name} reports FFO/AFFO per share; mapping that onto EPS silently changes the "
            f"definition of the series.",
        "missing_transcript":
            f"{ticker} published the release for this period but no call transcript is available.",
        "missing_release":
            f"{ticker} has a transcript for this period with no machine-readable release bound "
            f"to it, so numeric claims have no primary document.",
        "pdf_table":
            f"{ticker}'s figure appears only inside a PDF supplement table cell, not in any "
            f"text span.",
        "changed_slide_family":
            f"{ticker} restructured its recurring slide exhibit this period; the prior series "
            f"definition does not carry forward.",
        "speaker_role_error":
            f"{ticker}'s transcript mis-attributes at least one speaker role; the span is exact "
            f"but the role field is wrong.",
        "future_dated_quarantine":
            f"{ticker} carries a period/timestamp later than the observation time and must be "
            f"quarantined rather than published.",
        "edgar_identity_join":
            f"{ticker}'s 8-K is seen by both EDGAR readers in this estate under disjoint keys "
            f"(cik+filing_date vs cik+accession), so the two views cannot be joined.",
    }[cls]


def _outcome_for(cls: str, index: int) -> str:
    """The class default, with the deliberate exceptions the ticket calls for."""
    default = DIFFICULTY_CLASSES[cls][1]
    if cls == "pdf_table" and index % 5 == 4:
        # A scanned-image table cannot yield a cell receipt.
        return "typed_absence"
    if cls == "speaker_role_error" and index % 6 == 5:
        # An unresolvable speaker means the claim cannot be attributed at all.
        return "typed_absence"
    if cls == "changed_slide_family" and index % 4 == 3:
        # The retained families still resolve to an exact cell.
        return "exact_receipt"
    # edgar_identity_join has NO exception, on purpose.  Its finding is homogeneous:
    # every pair's two readers share `ticker` and nothing else, so not one row carries
    # observable duplication evidence.  A positional `duplicate_collapsed` here (this
    # builder carried one until 2026-08-07) is gradeable only by its answer key, which
    # is the one thing a benchmark may never require -- and the EDGAR fixture's own
    # open_contract_question says so: "every edgar_identity_join case is a typed
    # absence".  `duplicate_collapsed` stays in the vocabulary because duplicate_release
    # earns it with fourteen two-revision cases.
    if cls == "amendment" and index % 8 == 7:
        # The amendment arrived with a period later than observation time.
        return "quarantined"
    if cls == "missing_release" and index % 6 == 5:
        return "quarantined"
    return default


def _assert_duplicates_carry_their_evidence(cases: list[dict[str, Any]]) -> None:
    """Every ``duplicate_collapsed`` case must ship the duplicate it collapses.

    Keyed on the OUTCOME, not the difficulty class, which is exactly the hole the
    positional edgar_identity_join rule fell through: CIE-GC-0227/0234 were labelled
    duplicates while carrying a single ``release`` revision, so nothing observable
    separated them from the twelve typed-absence siblings and only the answer key
    could grade them.  An outcome that rests on nothing does not belong in a frozen
    benchmark, and this refuses to write one.
    """
    offenders: list[str] = []
    for case in cases:
        if case["expected_v2_outcome"] != "duplicate_collapsed":
            continue
        revisions = case["document_revisions"]
        if len(revisions) < 2:
            offenders.append(case["case_id"])
            continue
        duplicate = revisions[1]
        if (duplicate["document_kind"] != "release_duplicate"
                or duplicate["source_sha256"] == revisions[0]["source_sha256"]
                or duplicate["supersedes_source_sha256"] != revisions[0]["source_sha256"]):
            offenders.append(case["case_id"])
    if offenders:
        raise SystemExit(
            "duplicate_collapsed with no duplication evidence (needs a revision 2 of kind "
            "'release_duplicate' whose supersedes_source_sha256 is revision 1's "
            f"source_sha256): {', '.join(offenders)}"
        )


def build_cases(issuers: list[dict[str, Any]], rng: random.Random) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for issuer in issuers:
        by_kind.setdefault(issuer["kind"], []).append(issuer)

    documents: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []
    used_events: set[tuple[str, int, int]] = set()
    general_cursor = 0

    for cls in DIFFICULTY_CLASSES:
        count, _, _ = DIFFICULTY_CLASSES[cls]
        kind = CLASS_KIND.get(cls)
        pool = by_kind[kind] if kind else issuers
        for index in range(count):
            if kind:
                issuer = pool[index % len(pool)]
            else:
                issuer = issuers[general_cursor % len(issuers)]
                general_cursor += 1

            listings = issuer["listings"]
            if cls in {"share_class", "dual_listing"}:
                # Walk the SIBLING symbol on each successive pass over the pool.
                # `index % len(listings)` looks right and is wrong: the pools are
                # even-sized, so issuer i is only ever revisited at the same parity
                # and one listing per issuer would never be used — which is the whole
                # point of these two classes.
                listing = listings[(index // len(pool)) % len(listings)]
            else:
                listing = listings[0]
            ticker = listing["ticker"]

            # future_dated_quarantine must actually BE future-dated relative to the
            # corpus's frozen observation time.  A class that is only a label cannot
            # grade the behaviour it exists to grade.
            fiscal_year, fiscal_quarter, call_date = _pick_period(cls, ticker, index, used_events)
            used_events.add((ticker, fiscal_year, fiscal_quarter))

            outcome = _outcome_for(cls, index)
            locator_kind = (
                RECEIPT_LOCATOR_KINDS.get(cls, DEFAULT_LOCATOR_KIND)
                if outcome == "exact_receipt" else None
            )
            case_id = f"CIE-GC-{len(cases) + 1:04d}"

            transcript_present = cls != "missing_transcript"
            release_present = cls != "missing_release"

            document_id: str | None = None
            receipt: dict[str, Any] | None = None
            if transcript_present:
                body = build_document(issuer, ticker, fiscal_year, fiscal_quarter, call_date, rng)
                if cls == "speaker_role_error":
                    # The defect this class exists for: the CFO's numeric segment is
                    # attributed to an analyst.  The span stays byte-exact.
                    body["segments"][2]["role"] = "Analyst, Kestrel Securities"
                body_bytes = canonical_transcript_body_bytes(body)
                body_sha = sha256_bytes(body_bytes)
                document_id = "doc_" + sha256(
                    f"{ticker}|{fiscal_year}Q{fiscal_quarter}|{cls}".encode("utf-8")
                ).hexdigest()[:20]
                documents.append({
                    "document_id": document_id,
                    "ticker": ticker,
                    "transcript_id": f"{fiscal_year}Q{fiscal_quarter}",
                    "document_kind": "transcript",
                    "body_sha256": body_sha,
                    "body_bytes": len(body_bytes),
                    "provenance": "synthetic",
                    "body": body,
                })
                if locator_kind == DEFAULT_LOCATOR_KIND:
                    segment_index = 2
                    segment_text = body["segments"][segment_index]["text"]
                    start, end, text = _quotable_span(segment_text, rng)
                    receipt = receipt_for_span(
                        source_sha256=body_sha,
                        segment_index=segment_index,
                        segment_text=segment_text,
                        start_byte=start,
                        end_byte=end,
                        text=text,
                    )

            revisions = [{
                "revision": 1,
                "document_kind": "release" if release_present else "transcript_only",
                "source_sha256": sha256(f"{case_id}|r1".encode("utf-8")).hexdigest(),
                "supersedes_source_sha256": None,
                "accession_synthetic": _accession(ticker, f"{case_id}-r1", fiscal_year),
            }]
            if cls in {"amendment", "duplicate_release"}:
                revisions.append({
                    "revision": 2,
                    "document_kind": "release_amendment" if cls == "amendment" else "release_duplicate",
                    "source_sha256": sha256(f"{case_id}|r2".encode("utf-8")).hexdigest(),
                    "supersedes_source_sha256": revisions[0]["source_sha256"],
                    "accession_synthetic": _accession(ticker, f"{case_id}-r2", fiscal_year),
                })

            # A quarantined case must carry the evidence of its own violation, or a
            # grader can only take the label's word for it.
            quarantine = None
            if outcome == "quarantined":
                if cls == "future_dated_quarantine":
                    quarantine = {
                        "observed_at": OBSERVED_AT,
                        "offending_field": "event.call_date",
                        "record_timestamp": f"{call_date}T00:00:00+00:00",
                        "reason": "the fiscal period ends after the observation time",
                    }
                else:
                    quarantine = {
                        "observed_at": OBSERVED_AT,
                        "offending_field": "document_revision.acceptance_datetime",
                        "record_timestamp": f"{FUTURE_YEARS[0]}-03-04T13:22:00+00:00",
                        "reason": "the document revision is stamped after the observation time",
                    }

            cases.append({
                "case_id": case_id,
                "difficulty_class": cls,
                "difficult": True,
                "label": _class_label(cls, issuer, ticker),
                "issuer_id": issuer["issuer_id"],
                "issuer_kind": issuer["kind"],
                "display_name": issuer["display_name"],
                "ticker": ticker,
                "listing_mic": listing["mic"],
                "share_class": listing["share_class"],
                "trading_currency": listing["trading_currency"],
                "reporting_currency": issuer["reporting_currency"],
                "fiscal_year": fiscal_year,
                "fiscal_quarter": fiscal_quarter,
                "fiscal_year_end_month": issuer["fiscal_year_end_month"],
                "call_date": call_date,
                # BOTH id schemes, committed, so a change to either minting function goes red.
                "event_key_company_intelligence": cie_event_key(ticker, fiscal_year, fiscal_quarter, call_date),
                "event_id_company_intelligence": stable_event_id(ticker, fiscal_year, fiscal_quarter, call_date),
                "transcript_id": f"{fiscal_year}Q{fiscal_quarter}",
                "event_key_earnings_narrative": narrative_event_key(
                    {"ticker": ticker, "transcript_id": f"{fiscal_year}Q{fiscal_quarter}"}
                ),
                "transcript_present": transcript_present,
                "release_present": release_present,
                "excerpt_document_id": document_id,
                "receipt": receipt,
                "document_revisions": revisions,
                # v1 hard-codes claim_citations_pending == True everywhere.  This is the
                # value Wave 1 must produce INSTEAD, per case.
                "v1_claim_citations_pending": True,
                "expected_v2_outcome": outcome,
                "expected_receipt_locator_kind": locator_kind,
                "expected_event_identity": "preserved",
                "quarantine": quarantine,
            })

    _assert_duplicates_carry_their_evidence(cases)
    return cases, documents


# ─────────────────────────────────────────────────────────────────────────────
# v1-shaped payloads for the REAL validators
# ─────────────────────────────────────────────────────────────────────────────

def _v1_source(kind: str, status: str, url: str | None, precision: str,
               receipt: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"source_ref": kind, "kind": kind, "status": status,
            "citation_precision": precision, "url": url, "receipt": receipt}


def _v1_event(ticker: str, name: str, fiscal_year: int, fiscal_quarter: int, call_date: str,
              tags: list[str], with_overlay: bool) -> dict[str, Any]:
    metrics = {metric: (0.25 if with_overlay or metric in {"revenue_growth_pct", "eps_growth_pct"} else None)
               for metric in sorted(PUBLIC_METRICS)}
    sources = [
        _v1_source("earnings_history", "present", "https://issuer.example/ir/release", "document",
                   {"source_hash": sha256(f"{ticker}{fiscal_year}{fiscal_quarter}".encode()).hexdigest(),
                    "source_date": call_date}),
        _v1_source("transcript", "present",
                   f"/data/tx/{ticker}/{fiscal_year}Q{fiscal_quarter}.json.gz", "document"),
    ]
    if with_overlay:
        sources.insert(1, _v1_source("score_overlay", "metadata_only", None, "metadata"))
    lineage_ref = "earnings_history"
    return {
        "event_id": stable_event_id(ticker, fiscal_year, fiscal_quarter, call_date),
        "ticker": ticker,
        "fiscal_year": fiscal_year,
        "fiscal_quarter": fiscal_quarter,
        "call_date": call_date,
        "summary": f"{name} reported Q{fiscal_quarter} {fiscal_year} results.",
        "highlights": [f"Reported Q{fiscal_quarter} {fiscal_year}."],
        "positive_highlights": ["Cost base held to plan."],
        "negative_highlights": [],
        "key_quote": "We exited the quarter with the cost base we committed to.",
        "tags": tags,
        "metrics": metrics,
        "field_lineage": {
            "summary": lineage_ref,
            "key_quote": "transcript",
            "metrics": {metric: (lineage_ref if value is not None else None)
                        for metric, value in metrics.items()},
            "positive_highlights": [lineage_ref],
            "negative_highlights": [],
            "highlights": [lineage_ref],
            "tags": {tag: lineage_ref for tag in tags},
        },
        "previous_event_deltas": {metric: None for metric in sorted(PUBLIC_METRICS)},
        "sources": sources,
        "claim_citations_pending": True,
    }


def _v1_context(ticker: str, name: str, status: str, events: list[dict[str, Any]],
                warnings: list[str], missing_sources: list[str]) -> dict[str, Any]:
    newest_tags = set(events[0]["tags"]) if events else set()
    prior_tags = set(events[1]["tags"]) if len(events) > 1 else set()
    timeline: list[dict[str, Any]] = []
    for tag in sorted({t for event in events for t in event["tags"]}):
        carrying = [event for event in events if tag in event["tags"]]
        timeline.append({
            "tag": tag,
            "first_event_id": carrying[-1]["event_id"],
            "last_event_id": carrying[0]["event_id"],
            "event_count": len(carrying),
            "status": "persistent" if tag in newest_tags & prior_tags
                      else ("added" if tag in newest_tags - prior_tags else "dropped"),
        })
    transcript_events = sum(
        1 for event in events
        if any(s["kind"] == "transcript" and s["status"] == "present" for s in event["sources"])
    )
    overlay_events = sum(
        1 for event in events if any(s["kind"] == "score_overlay" for s in event["sources"])
    )
    return {
        "schema": CONTEXT_SCHEMA,
        "authority": AUTHORITY,
        "generated_at": "2026-08-06T00:00:00Z",
        "generation_id": sha256(ticker.encode("utf-8")).hexdigest()[:24],
        "company": {"ticker": ticker, "display_name": name, "exchange": None},
        "status": status,
        "latest_event_id": events[0]["event_id"] if events else None,
        "latest_event": events[0] if events else None,
        "history": events,
        "topics": {
            "timeline": timeline,
            "added": sorted(newest_tags - prior_tags),
            "dropped": sorted(prior_tags - newest_tags),
            "persistent": sorted(newest_tags & prior_tags),
        },
        "source_completeness": {
            "earnings_history": {"status": "present" if events else "missing", "event_count": len(events)},
            "score_overlay": {"status": "metadata_only" if overlay_events else "missing",
                              "event_count": overlay_events},
            "transcripts": {"status": "present" if transcript_events else "missing",
                            "event_count": transcript_events},
        },
        "warnings": warnings,
        "missing_sources": missing_sources,
        "transport_lineage": {
            "earnings_manifest": {"generation_id": "b" * 24, "sha256": "c" * 64},
            "tx_index": {"generation_id": "d" * 24, "sha256": "e" * 64,
                         "schema": "mastermind.tx-index/v1"},
            "builder": "company_intelligence.v1",
        },
    }


def build_v1_contexts() -> dict[str, Any]:
    ready = _v1_context(
        "AAPL", "Apple Inc.", "ready",
        [
            _v1_event("AAPL", "Apple Inc.", 2026, 2, "2026-05-07", ["services", "margins"], True),
            _v1_event("AAPL", "Apple Inc.", 2026, 1, "2026-02-12", ["services", "supply_chain"], True),
        ],
        [], [],
    )
    partial = _v1_context(
        "JPM", "JPMorgan Chase & Co.", "partial",
        [_v1_event("JPM", "JPMorgan Chase & Co.", 2026, 1, "2026-02-12", ["net_interest_income"], False)],
        ["transcripts_partial"], ["transcripts_for_some_events"],
    )
    stale = _v1_context(
        "O", "Realty Income Corporation", "stale",
        [_v1_event("O", "Realty Income Corporation", 2025, 4, "2025-11-04", ["ffo"], False)],
        ["freshness_reference_missing"], [],
    )
    not_covered = _v1_context("MOG.A", "Moog Inc.", "not_covered", [],
                              ["earnings_history_missing"], ["earnings_history"])
    return {
        "schema": "company_intelligence.golden_corpus_v1_contexts/v1",
        "note": (
            "v1-shaped contexts that MUST round-trip through the real "
            "engine.company_intelligence.contracts.validate_context. Synthetic bodies; the "
            "event_id values are minted by the real stable_event_id(). Their purpose is to make "
            "a schema drift in contracts.py break this benchmark loudly rather than silently."
        ),
        "contexts": [
            {"case_ref": "v1ctx-ready", "expected": "valid", "context": ready},
            {"case_ref": "v1ctx-partial", "expected": "valid", "context": partial},
            {"case_ref": "v1ctx-stale", "expected": "valid", "context": stale},
            {"case_ref": "v1ctx-not-covered", "expected": "valid", "context": not_covered},
        ],
    }


def build_v1_manifests() -> dict[str, Any]:
    def manifest(status: str, companies: int, events: int, latest: str | None,
                 files: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
        return {
            "schema": MANIFEST_SCHEMA,
            "generation_id": sha256(f"{status}{companies}".encode()).hexdigest()[:24],
            "generated_at": "2026-08-06T00:00:00Z",
            "company_count": companies,
            "event_count": events,
            "latest_event_date": latest,
            "source": {
                "earnings_manifest": {
                    "generation_id": "b" * 24, "sha256": "c" * 64,
                    "observed_counts": {"history_rows": events, "history_tickers": companies,
                                        "score_rows": 0, "score_tickers": 0},
                },
                "tx_index": {"generation_id": "d" * 24, "sha256": "e" * 64,
                             "schema": "mastermind.tx-index/v1"},
            },
            "files": files,
            "status": status,
            "warnings": warnings,
            "operational": {"history_rows_rejected": 0},
        }

    ready = manifest("ready", 2, 3, "2026-05-07", {
        "companies/AAPL.json": {"sha256": "a" * 64, "bytes": 4096},
        "companies/JPM.json": {"sha256": "b" * 64, "bytes": 2048},
    }, [])
    degraded = manifest("degraded", 1, 1, "2025-11-04",
                        {"companies/O.json": {"sha256": "f" * 64, "bytes": 1024}},
                        ["transcripts_partial"])
    empty = manifest("empty", 0, 0, None, {}, ["earnings_history_missing"])
    return {
        "schema": "company_intelligence.golden_corpus_v1_manifests/v1",
        "note": (
            "v1-shaped manifests that MUST round-trip through the real validate_manifest(). "
            "Note the vocabulary split recorded in the corpus manifest's known_limits: manifest "
            "status is {ready, degraded, empty} while context status is "
            "{ready, partial, stale, not_covered} -- two inline set literals, no shared enum."
        ),
        "manifests": [
            {"case_ref": "v1man-ready", "expected": "valid", "manifest": ready},
            {"case_ref": "v1man-degraded", "expected": "valid", "manifest": degraded},
            {"case_ref": "v1man-empty", "expected": "valid", "manifest": empty},
        ],
    }


def build_edgar_identity(cases: list[dict[str, Any]], issuers: list[dict[str, Any]]) -> dict[str, Any]:
    """The disjoint-key EDGAR pairs — the program's hardest identity join.

    ``collectors/edgar_earnings_8k.py`` emits {ticker, cik, filing_date,
    acceptance_datetime, items} and captures NO accession number.
    ``engine/marketing/edgar_earnings_wire.py`` emits id=f"{ticker}-{accession}"
    and accession, but NO cik, NO filing_date, and its ``when`` is wall-clock at
    processing time rather than a source timestamp.  The intersection of the two
    key sets is {ticker} alone, which is not an event key.
    """
    by_id = {issuer["issuer_id"]: issuer for issuer in issuers}
    pairs = []
    for case in cases:
        if case["difficulty_class"] != "edgar_identity_join":
            continue
        issuer = by_id[case["issuer_id"]]
        accession = case["document_revisions"][0]["accession_synthetic"]
        pairs.append({
            "case_ref": case["case_id"],
            "ticker": case["ticker"],
            "expected_v2_outcome": case["expected_v2_outcome"],
            # Shape emitted by collectors/edgar_earnings_8k.py:242-248
            "collector_edgar_earnings_8k_row": {
                "ticker": case["ticker"],
                "cik": issuer["cik_synthetic"],
                "filing_date": case["call_date"],
                "acceptance_datetime": f"{case['call_date']}T21:07:14.000Z",
                "items": "2.02,9.01",
            },
            # Shape emitted by engine/marketing/edgar_earnings_wire.py:148-159
            "engine_edgar_earnings_wire_row": {
                "id": f"{case['ticker']}-{accession}",
                "accession": accession,
                "ticker": case["ticker"],
                "when": "2026-08-06T00:00:00+00:00",
                "when_semantics": "wall_clock_at_processing_not_source_timestamp",
            },
            "joinable_keys_today": ["ticker"],
            "missing_for_join": {
                "collector_edgar_earnings_8k": ["accession"],
                "engine_edgar_earnings_wire": ["cik", "filing_date", "acceptance_datetime"],
            },
        })
    return {
        "schema": "company_intelligence.golden_corpus_edgar_identity/v1",
        "note": (
            "Synthetic CIKs and accession numbers in format-valid shape; the KEY SETS are the "
            "real ones emitted by the two readers named in each row. No EDGAR document text is "
            "stored. The finding this fixture pins: the two readers share only `ticker`, which "
            "cannot key an event, so no join exists today at any level."
        ),
        "open_contract_question": (
            "Wave 1 must decide the canonical filing key. The corpus's position: "
            "(cik, accession) is the only correction-stable pair, so edgar_earnings_8k must "
            "capture accession and edgar_earnings_wire must capture cik + the SOURCE acceptance "
            "timestamp. Until then every edgar_identity_join case is a typed absence."
        ),
        "pairs": pairs,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Assembly
# ─────────────────────────────────────────────────────────────────────────────

def _dump(payload: object) -> bytes:
    return (json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n").encode("utf-8")


def build_corpus() -> dict[str, bytes]:
    """Return {repo-relative path: file bytes}. Pure and deterministic."""
    rng = random.Random(SEED)
    issuers = build_issuers()
    cases, documents = build_cases(issuers, rng)

    issuer_ids_in_cases = {case["issuer_id"] for case in cases}
    if len(issuer_ids_in_cases) < 100:
        raise SystemExit(f"corpus understrength: {len(issuer_ids_in_cases)} issuers < 100")
    if sum(1 for case in cases if case["difficult"]) < 200:
        raise SystemExit(f"corpus understrength: {len(cases)} difficult events < 200")

    fixtures: dict[str, bytes] = {
        ISSUERS_FIXTURE: _dump({
            "schema": "company_intelligence.golden_corpus_issuers/v1",
            "note": (
                "Real, public ticker symbols and issuer names. CIKs are SYNTHETIC but "
                "format-valid (see cik_synthetic). fiscal_year_end_month drives the "
                "fiscal_year_ambiguity class and is the issuer's published fiscal calendar."
            ),
            "issuer_count": len(issuers),
            "issuers": issuers,
        }),
        DOCUMENTS_FIXTURE: _dump({
            "schema": "company_intelligence.golden_corpus_documents/v1",
            "note": (
                "Synthetic mastermind.tx/v1 transcript bodies written for this corpus. NO "
                "third-party transcript, release, or filing text is stored anywhere in this "
                "repository. Every body_sha256 is a REAL sha256 over the committed body, "
                "computed with the production "
                "engine.earnings_narrative.contracts.canonical_transcript_body_bytes, so an "
                "exact-span receipt in the manifest replays byte-for-byte against it."
            ),
            "document_count": len(documents),
            "documents": documents,
        }),
        CONTEXTS_FIXTURE: _dump(build_v1_contexts()),
        MANIFESTS_FIXTURE: _dump(build_v1_manifests()),
        EDGAR_FIXTURE: _dump(build_edgar_identity(cases, issuers)),
    }

    counts_by_class = {cls: sum(1 for case in cases if case["difficulty_class"] == cls)
                       for cls in DIFFICULTY_CLASSES}
    counts_by_outcome = {outcome: sum(1 for case in cases if case["expected_v2_outcome"] == outcome)
                         for outcome in sorted(EXPECTED_OUTCOMES)}

    manifest = {
        "schema": CORPUS_SCHEMA,
        "schema_version": 1,
        "generated_utc": GENERATED_UTC,
        "title": "Company Intelligence golden corpus (Earnings/Company Event Suite R0-D)",
        "purpose": (
            "The frozen benchmark Wave 1's event/document/claim convergence layer is graded "
            "against. Every case names the outcome Wave 1 must produce where v1 today emits an "
            "unconditional claim_citations_pending: true."
        ),
        # Authority: this is benchmark material. It ranks nothing, sizes nothing,
        # gates nothing, alerts nothing.
        "authority": "context_only",
        "research_only": True,
        "may_rank": False,
        "may_size": False,
        "may_gate": False,
        "may_alert": False,
        "note": (
            "PROVENANCE. Ticker symbols and issuer display names are public identifiers and are "
            "real. Every document body is SYNTHETIC prose written for this corpus -- no "
            "third-party transcript, press release, or filing body is copied into this "
            "repository, in line with the R0-D instruction to store hashes and minimal permitted "
            "excerpts rather than raw sources. CIK numbers, accession numbers, generation ids and "
            "transport lineage hashes are format-valid but synthetic. Everything hashed here is "
            "hashed for real: fixture sha256 values are over the committed bytes, transcript "
            "body_sha256 values use the production canonical_transcript_body_bytes(), and every "
            "exact-span receipt is produced by the production receipt_for_span(), which replays "
            "the byte slice and raises if it disagrees."
        ),
        "builder": {
            "path": BUILDER_REL,
            "sha256": sha256((ROOT / BUILDER_REL).read_bytes()).hexdigest(),
            "deterministic": True,
            "seed": SEED,
            "reproduce": f"python3 {BUILDER_REL}",
        },
        "id_schemes": {
            "company_intelligence": {
                "event_key": "engine/company_intelligence/contracts.py::event_key -> '{TICKER}|{YEAR}|Q{QUARTER}'",
                "event_id": "engine/company_intelligence/contracts.py::stable_event_id -> 'cie_' + sha256(event_key)[:24]",
                "call_date_hashed": False,
                "correction_stable": True,
            },
            "earnings_narrative": {
                "event_key": "engine/earnings_narrative/contracts.py::event_key -> '{TICKER}/{TRANSCRIPT_ID}'",
                "transcript_id_pattern": "^\\d{4}Q[1-4]$",
                "correction_stable": True,
            },
            "reconciliation": (
                "Both schemes are pure functions of the SAME (ticker, fiscal_year, "
                "fiscal_quarter) triple; neither hashes a source date or revision. Every case "
                "below carries both, and the contract suite recomputes both from the triple, so "
                "a change to either minting function goes red here."
            ),
        },
        "difficulty_classes": {
            cls: {
                "definition": DIFFICULTY_CLASSES[cls][2],
                "default_expected_v2_outcome": DIFFICULTY_CLASSES[cls][1],
                "case_count": counts_by_class[cls],
            }
            for cls in DIFFICULTY_CLASSES
        },
        "expected_v2_outcome_vocabulary": {
            "exact_receipt": "Resolves to event_id -> document_revision -> exact span/cell/page.",
            "typed_absence": "No receipt is derivable; the surface must render a typed, named absence.",
            "quarantined": "The record must not be published at all (future-dated or unobservable).",
            "duplicate_collapsed": "Two documents, one logical event; the second must not mint an event.",
        },
        "expected_receipt_locator_kinds": {
            "text_span": (
                "A UTF-8 byte span inside one mastermind.tx/v1 segment. The ONLY receipt shape "
                "any code in this estate emits today (earnings_narrative receipt_for_span), and "
                "the only kind for which this corpus commits a replayable receipt."
            ),
            "table_cell": (
                "A PDF/supplement table cell addressed by page, table, row and column. No code "
                "emits this yet; the corpus declares the SHAPE Wave 1 must produce and commits "
                "no receipt, because a text-span receipt would assert the number lives in prose."
            ),
            "slide_region": (
                "A page region on a deck exhibit. No code emits this yet; declared, not committed."
            ),
        },
        "counts": {
            "issuers_registered": len(issuers),
            "issuers_with_cases": len(issuer_ids_in_cases),
            "cases": len(cases),
            "difficult_events": sum(1 for case in cases if case["difficult"]),
            "distinct_event_ids": len({case["event_id_company_intelligence"] for case in cases}),
            "cases_with_exact_span_receipt": sum(1 for case in cases if case["receipt"] is not None),
            "documents": len(documents),
            "by_difficulty_class": counts_by_class,
            "by_expected_v2_outcome": counts_by_outcome,
            "by_expected_receipt_locator_kind": {
                kind: sum(1 for case in cases if case["expected_receipt_locator_kind"] == kind)
                for kind in ("text_span", "table_cell", "slide_region")
            },
        },
        "required_minimums": {"issuers": 100, "difficult_events": 200},
        "observation_time": {
            "observed_at": OBSERVED_AT,
            "meaning": (
                "The corpus's frozen 'now'. Every quarantined case carries a "
                "record_timestamp strictly after this instant, so the violation is "
                "checkable rather than merely labelled. Availability timestamps must "
                "prove no consumer outran its source (Wave 1 acceptance)."
            ),
        },
        "fixtures": {
            f"tests/fixtures/company_intelligence/{name}": {
                "sha256": sha256(blob).hexdigest(),
                "bytes": len(blob),
            }
            for name, blob in sorted(fixtures.items())
        },
        "known_limits": [
            {
                "key": "status-vocabularies-are-inline-set-literals",
                "finding": (
                    "Five DIFFERENT status vocabularies exist as inline set literals with no "
                    "shared enum: context status {ready, partial, stale, not_covered} "
                    "(contracts.py:432); manifest status {ready, degraded, empty} "
                    "(contracts.py:623); per-source status {present, metadata_only, missing} "
                    "(contracts.py:338); source_completeness block {present, metadata_only, "
                    "missing, partial} (contracts.py:557); health replay {empty, degraded, ready} "
                    "(health.py:99,103,136-139). A consumer cannot switch on 'status' without "
                    "knowing which of the five it holds."
                ),
                "wave1_implication": "The versioned convergence layer should mint ONE typed status enum and adapt the five.",
            },
            {
                "key": "blocked-rights-does-not-exist-in-code",
                "finding": (
                    "`blocked_rights` is a PLANNED Wave-7 status value. It appears in no "
                    "vocabulary in engine/company_intelligence/ or engine/earnings_narrative/ "
                    "today. This corpus does not use it and no case expects it."
                ),
                "wave1_implication": "Do not treat blocked_rights as an existing state to adapt.",
            },
            {
                "key": "claim-citations-pending-is-a-hard-v1-invariant",
                "finding": (
                    "validate_context RAISES unless event.claim_citations_pending is exactly True "
                    "(contracts.py:501-502); views.py:461 sets the literal; "
                    "app/company_intelligence.py:58 and "
                    "engine/neuralweb/company_intelligence_reader.py:402 project it. It is a "
                    "document-level availability statement, never span-level lineage."
                ),
                "wave1_implication": (
                    "Replacing it is a v2 schema change with a new reader, not an in-place edit. "
                    "Each case's expected_v2_outcome is the value that must replace it."
                ),
            },
            {
                "key": "edgar-readers-capture-disjoint-keys",
                "finding": (
                    "collectors/edgar_earnings_8k.py:242-248 emits {ticker, cik, filing_date, "
                    "acceptance_datetime, items} and NO accession. "
                    "engine/marketing/edgar_earnings_wire.py:148-159 emits {id, accession, ...} "
                    "with NO cik, NO filing_date, and a wall-clock `when`. Their key sets "
                    "intersect only on `ticker`."
                ),
                "wave1_implication": (
                    "No filing-level join exists today. See "
                    "tests/fixtures/company_intelligence/golden_corpus_edgar_identity.v1.json."
                ),
            },
            {
                "key": "both-id-schemes-are-ticker-keyed",
                "finding": (
                    "Both event keys start from a TICKER, so one issuer's two share classes "
                    "(GOOGL/GOOG, BRK.A/BRK.B) mint TWO event ids for ONE issuer event, and an "
                    "ADR plus its home line mint two more. The corpus's share_class and "
                    "dual_listing cases carry both symbols deliberately."
                ),
                "wave1_implication": (
                    "The canonical event_id must key on ISSUER, not listing, or coverage and "
                    "theme breadth inflate by construction."
                ),
            },
        ],
        "limitations": [
            "Synthetic bodies. The corpus proves CONTRACT behaviour (identity, receipts, absence "
            "typing, quarantine), not extraction accuracy against real filings.",
            "PDF-table and slide-family cases are declared, not rendered: no PDF or PPTX bytes "
            "are stored. Their expected outcome describes the receipt SHAPE (page/table/row/col) "
            "Wave 1 must emit, and the corpus cannot verify a real PDF parser.",
            "CIK and accession values are synthetic; the corpus grades the identity JOIN, never "
            "a lookup against live EDGAR.",
            "Fiscal-year-end months are the issuers' published fiscal calendars, but the corpus "
            "asserts no specific real reported figure for any period.",
            "The corpus is a benchmark, not a gauntlet: nothing here promotes any signal to "
            "authority, and no case may be cited as evidence for a ranking, size, or gate.",
        ],
        "wave1_open_questions": [
            "Which identity is canonical: (issuer_id, fiscal_year, fiscal_quarter) or "
            "(listing, fiscal_year, fiscal_quarter)? Both current schemes pick the listing; every "
            "share_class and dual_listing case in this corpus is evidence that this inflates counts.",
            "What is the canonical filing key, given the two EDGAR readers capture disjoint key "
            "sets? The corpus's position is (cik, accession).",
            "What replaces claim_citations_pending: a per-claim receipt union, or an event-level "
            "state? The corpus commits a per-CASE expected outcome, which presumes a per-claim answer.",
            "Does a fiscal label live on the event or on the document? A dual-listed issuer can "
            "publish the same event under two reporting calendars.",
            "Which of the five status vocabularies becomes the typed enum, and what happens to "
            "the four adapters?",
        ],
        "cases": cases,
    }

    out: dict[str, bytes] = {
        f"tests/fixtures/company_intelligence/{name}": blob for name, blob in fixtures.items()
    }
    out["research/company_intelligence/GOLDEN_CORPUS_MANIFEST.json"] = _dump(manifest)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="verify the committed corpus matches a fresh build; write nothing")
    args = parser.parse_args(argv)

    built = build_corpus()
    if args.check:
        stale = [rel for rel, blob in sorted(built.items())
                 if not (ROOT / rel).is_file() or (ROOT / rel).read_bytes() != blob]
        if stale:
            print("STALE (re-run this builder):", flush=True)
            for rel in stale:
                print(f"  {rel}", flush=True)
            return 1
        print(f"corpus is current: {len(built)} files", flush=True)
        return 0

    for rel, blob in sorted(built.items()):
        path = ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
        print(f"wrote {rel} ({len(blob):,} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
