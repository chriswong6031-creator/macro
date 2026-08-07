"""engine.marketing.edgar_earnings_wire — real-time SEC 8-K Item 2.02 earnings wire.

WHY THIS EXISTS. `earnings_feed.FreePollProvider` polls
``finviz.com/rss.ashx?v=3&auth=0``. That endpoint 301s to ``/rss?v=3&auth=0``
and returns a 404 HTML page. It has returned zero events for as long as the
lane has been armed, and the outbox has never held a single ``kind="earnings"``
item. The failure was invisible because the fetch exception is swallowed at
``logger.debug`` — so a dead feed and a quiet earnings calendar produce the
identical output, a green run reporting ``emitted=0 skipped=0``.

THE SOURCE. A US issuer announces results by filing an 8-K carrying Item 2.02
("Results of Operations and Financial Condition") with the press release as
Exhibit 99.1. EDGAR's ``getcurrent`` feed publishes that filing within seconds
of acceptance: measured 2026-08-04, entries were visible at 07:10:23 ET while
the clock read 07:11, and McDonald's Q2 8-K was accepted at 07:01:40 ET —
ahead of the wire accounts that posted the same numbers. It is free, needs no
key, and is the primary document rather than somebody's summary of it.

────────────────────────────────────────────────────────────────────────────
THE EXTRACTION RULE, AND WHY IT DECLINES SO OFTEN ON PURPOSE
────────────────────────────────────────────────────────────────────────────
Measured against the filings of one real morning (2026-08-04):

  * PROSE matching — flatten the release to text, regex the sentences — got
    roughly half the figures WRONG. Pfizer's revenue came back "500 million"
    (it bills ~$15B/quarter) and Merck's "161 million" (~$16.6B), because a
    release says "revenue" in a dozen sentences and only one of them is the
    consolidated number. McDonald's returned $3.32 when every wire account led
    with the $3.38 adjusted figure.

  * TABLE matching, first row whose label matches, document order — better,
    but read Caterpillar's revenue as 7,037 from a SEGMENT table. CAT bills
    ~$16B a quarter.

Neither error is acceptable. A post we never make is recoverable; a wrong
number under our name is not, and it is worse than the silence it replaces.

So this module uses a STRUCTURAL rule instead of a magnitude heuristic: the
consolidated statement of operations is the one table that carries BOTH a
revenue row and a per-share row. A segment breakdown has sales and no EPS. We
therefore accept figures ONLY from a table that yields both, and take the first
such table in document order.

On that morning's filings the rule produced:

    MCD  7,099 / 3.32   correct
    PFE 15,034 / -0.04  correct
    TDG  2,741 / 9.39   correct
    CAT  ——             DECLINED (segment tables only; EPS lives elsewhere)
    MRK  ——             DECLINED (same)

Three right, two declined, ZERO WRONG. Coverage is the thing to improve later
(CAT and MRK split revenue and EPS across adjacent tables, which a future pass
can pair); the zero-error floor is the thing to keep. `figures_from_tables`
returning None is a SUCCESS of this design, not a gap in it.

────────────────────────────────────────────────────────────────────────────
LOUD BY CONSTRUCTION
────────────────────────────────────────────────────────────────────────────
Every give-up path here prints a GitHub annotation and increments a counter
that the caller reports. That is the direct lesson of the dead Finviz feed: the
bug was not that the URL rotted — URLs rot — it was that nothing could tell the
difference between "the feed is gone" and "nobody reported today". A wire that
declines is fine. A wire that declines SILENTLY is the failure.

Annotations are emitted with a bare ``print("::warning ...", flush=True)`` and
never through a logger: every builder in this repo logs with a prefixing
format, so a logged annotation arrives as ``WARNING ::warning ...`` and GitHub
drops it (see tests/test_gh_annotation_line_start.py).

────────────────────────────────────────────────────────────────────────────
Public contract
────────────────────────────────────────────────────────────────────────────
Pure (no I/O, exhaustively tested):
    ``parse_current_feed``   Atom → [Filing]
    ``parse_tables``         HTML → tables as list-of-rows-of-cell-text
    ``cell_number``          one cell → float | None
    ``figures_from_tables``  tables → Figures | None      (the same-table rule)
    ``eps_is_plausible``     figure + consensus → bool    (the last tripwire)
    ``build_event``          figures + expectation → earnings_feed event dict

I/O (thin, injectable ``fetch`` everywhere so the suite never hits the network):
    ``EdgarEarningsProvider``  drop-in for ``earnings_feed.EarningsProvider``

The event dicts are exactly ``earnings_feed``'s documented schema, so
``fastlane.run_tick`` consumes them unchanged.
"""
from __future__ import annotations

import html as _html
import json
import re
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Iterable

from engine.earnings_release.binding import normalize_acceptance

SOURCE_ID = "edgar_8k_202"

# EDGAR's real-time "latest filings" feed. type=8-K narrows it at the server.
CURRENT_FEED_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K"
    "&company=&dateb=&owner=include&count=100&output=atom"
)
SUBMISSIONS_FMT = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_FMT = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}"

# SEC asks for a descriptive UA with contact details and caps traffic at 10 req/s.
# We poll one feed per tick and touch a filing only when its CIK is on today's
# calendar, which is far below that ceiling; the sleep is politeness, not a
# rate-limit workaround.
USER_AGENT = "MacroDashboard earnings wire contact@mastermind-x.com"
REQUEST_TIMEOUT_S = 12
POLITE_SLEEP_S = 0.12

ITEM_EARNINGS = "2.02"

# An EPS this large is not an EPS — it is a revenue line that matched a
# per-share label, or a share count. CAT's segment trap produced 7,037.
MAX_ABS_EPS = 100.0
# How far from consensus an extracted EPS may sit before we refuse to believe
# we read the right row. Deliberately generous: real prints swing to losses and
# real beats double the estimate. This is a "did we grab the wrong line" guard,
# not a surprise filter.
EPS_CONSENSUS_TOLERANCE = 10.0


# ─────────────────────────────────────────────────────────────────────────────
# Annotations
# ─────────────────────────────────────────────────────────────────────────────

def _warn(title: str, message: str) -> None:
    """Emit a GitHub annotation. Bare print, line-start, flushed — see module doc."""
    print(f"::warning title={title}::{message}", flush=True)


def _notice(title: str, message: str) -> None:
    print(f"::notice title={title}::{message}", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# Feed parsing (pure)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Filing:
    """One 8-K seen on the current-filings feed."""

    cik: int
    accession: str
    title: str = ""
    updated: str = ""

    @property
    def key(self) -> str:
        return f"{self.cik}:{self.accession}"


_CIK_IN_TITLE_RE = re.compile(r"\((\d{7,10})\)")
_ACCESSION_RE = re.compile(r"(\d{10}-?\d{2}-?\d{6})")


def parse_current_feed(xml_text: str) -> list[Filing]:
    """Parse EDGAR's getcurrent Atom feed into Filings.

    Returns [] on unparseable input rather than raising — a malformed feed is a
    source problem, and the caller's job is to keep polling, not to crash. The
    caller is told (the provider annotates an empty parse against a non-empty
    body).
    """
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return []

    ns = {"a": "http://www.w3.org/2005/Atom"}
    out: list[Filing] = []
    for entry in root.findall(".//a:entry", ns) or root.findall(".//entry"):
        def _text(tag: str) -> str:
            el = entry.find(f"a:{tag}", ns)
            if el is None:
                el = entry.find(tag)
            return (el.text or "").strip() if el is not None else ""

        title = _text("title")
        updated = _text("updated")

        link = entry.find("a:link", ns)
        if link is None:
            link = entry.find("link")
        href = (link.get("href") or "") if link is not None else ""

        m_cik = _CIK_IN_TITLE_RE.search(title)
        m_acc = _ACCESSION_RE.search(href) or _ACCESSION_RE.search(_text("id"))
        if not m_cik or not m_acc:
            continue

        raw = m_acc.group(1).replace("-", "")
        if len(raw) != 18:
            continue
        accession = f"{raw[:10]}-{raw[10:12]}-{raw[12:]}"
        out.append(
            Filing(cik=int(m_cik.group(1)), accession=accession,
                   title=title, updated=updated)
        )
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Table parsing (pure)
# ─────────────────────────────────────────────────────────────────────────────

class _TableReader(HTMLParser):
    """Collect <table>s as rows of cell text.

    Deliberately tolerant: EDGAR exhibits are machine-generated HTML with
    unclosed cells and nested markup, and `html.parser` in non-strict mode
    copes. Nested tables flatten into the enclosing one, which is harmless here
    because the same-table rule only ever asks whether a revenue row and a
    per-share row share a table.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    # A new <td> or <tr> IMPLICITLY closes the open one. EDGAR exhibits omit
    # closing tags routinely, and without these flushes each unclosed cell is
    # discarded when the next one opens — which silently empties whole rows and
    # turns a readable statement into "no table has both".
    def _flush_cell(self) -> None:
        if self._cell is not None and self._row is not None:
            self._row.append(_clean(self._cell))
        self._cell = None

    def _flush_row(self) -> None:
        self._flush_cell()
        if self._row is not None and self._table is not None:
            self._table.append(self._row)
        self._row = None

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag == "table":
            self._table = []
            self._row = None
            self._cell = None
        elif tag == "tr" and self._table is not None:
            self._flush_row()
            self._row = []
        elif tag in ("td", "th") and self._table is not None:
            if self._row is None:              # a cell outside any <tr>
                self._row = []
            self._flush_cell()
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and self._table is not None:
            self._flush_row()
            self.tables.append(self._table)
            self._table = None
        elif tag == "tr" and self._table is not None:
            self._flush_row()
        elif tag in ("td", "th"):
            self._flush_cell()

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def _clean(parts: list[str]) -> str:
    return re.sub(r"[\xa0\s]+", " ", "".join(parts)).strip()


_TAG_RE = re.compile(r"(?s)<[^>]+>")
_SCRIPT_RE = re.compile(r"(?is)<(script|style).*?</\1>")


def _visible_text(html_text: str) -> str:
    """Flatten HTML to its visible text — used only for period detection."""
    stripped = _TAG_RE.sub(" ", _SCRIPT_RE.sub(" ", html_text))
    return re.sub(r"[\xa0\s]+", " ", _html.unescape(stripped)).strip()


def parse_tables(html_text: str) -> list[list[list[str]]]:
    """HTML → [table][row][cell-text]. Returns [] on a parse failure."""
    reader = _TableReader()
    try:
        reader.feed(html_text)
        reader.close()
    except Exception:
        return reader.tables
    return reader.tables


_BARE_NUMBER_RE = re.compile(r"[\d,]+(?:\.\d+)?")


def cell_number(cell: str) -> float | None:
    """Parse one table cell to a number, or None.

    A trailing ``%`` returns None on purpose: percentage columns sit beside the
    level columns in these tables ("Revenues $7,099 $6,843 4 % 2 %") and taking
    one as the value would report the change as the level.

    Parentheses are the accounting negative, and the currency symbol lands on
    EITHER side of them — issuers write both ``$(0.04)`` and ``($0.04)``. The
    sign is decided from the parentheses after the symbol and spacing are
    removed, so neither order can turn a loss into a profit.
    """
    raw = (cell or "").replace("\xa0", " ").strip()
    if not raw or raw.endswith("%"):
        return None
    if raw in {"$", "%", "—", "–", "-", "N/A", "n/a", "*"}:
        return None
    body = raw.replace("$", "").replace(" ", "")
    negative = body.startswith("(") and body.endswith(")")
    body = body.strip("()")
    if not _BARE_NUMBER_RE.fullmatch(body):
        return None
    try:
        value = float(body.replace(",", ""))
    except ValueError:
        return None
    return -value if negative else value


# ─────────────────────────────────────────────────────────────────────────────
# The same-table rule (pure)
# ─────────────────────────────────────────────────────────────────────────────

# The label must END at the revenue keyword. Without the anchor,
# "Revenues from franchised restaurants" (a McDonald's SUB-line, $4,393) matches
# as readily as "Revenues" ($7,099) and sits earlier in some releases.
REVENUE_LABEL_RE = re.compile(
    r"^(?:total\s+|net\s+|consolidated\s+)*"
    r"(?:revenues?|net\s+sales|total\s+sales|net\s+revenues?)"
    r"\s*(?:\(\d+\)|\*+|:|—)?\s*$",
    re.I,
)
REVENUE_EXCLUDE_RE = re.compile(r"segment|per\s+share|growth|margin|expense", re.I)

# "Earnings per share-diluted" and "Reported(4) Diluted EPS/(LPS)" are per-share
# rows. "Weighted average shares outstanding-diluted" is a share COUNT that
# matched an earlier, looser pattern and produced 711.10 as an EPS.
EPS_LABEL_RE = re.compile(
    r"(?:earnings|income|loss|profit)\s*(?:\(loss\)\s*)?(?:\(lps\)\s*)?"
    r"per\s+(?:common\s+)?(?:diluted\s+)?share"
    r"|per\s+diluted\s+(?:common\s+)?share"
    r"|diluted\s+eps"
    r"|\beps\s*/?\s*\(?lps\)?",
    re.I,
)
EPS_EXCLUDE_RE = re.compile(
    r"weighted|outstanding|shares\s+used|dividend|book\s+value", re.I)

# THE BASIS PROBLEM. A sell-side consensus is set on ADJUSTED (non-GAAP)
# earnings; the consolidated statement of operations reports GAAP. They are
# different measures, and comparing one to the other does not merely add noise —
# it invents results. In one live run it read McDonald's as "in line" (GAAP
# 3.32 against a 3.32 estimate) when the quarter was a beat on the adjusted
# 3.38 every wire account printed, and it manufactured a cluster of 16-27%
# "misses" at companies that had not missed.
#
# The adjusted figure is stated too, in the non-GAAP reconciliation, and it is
# labelled. This finds it. When it is absent we do NOT fall back to comparing
# GAAP with an adjusted estimate — we mark the event uncomparable and let the
# composer report the figures without a verdict.
ADJUSTED_EPS_LABEL_RE = re.compile(
    r"(?:adjusted|non[-\s]?gaap|underlying|core)\b[^|]{0,40}?"
    r"(?:(?:earnings|income|eps)[^|]{0,20}per\s+(?:common\s+)?(?:diluted\s+)?share"
    r"|per\s+diluted\s+share|diluted\s+eps|\beps\b)",
    re.I,
)

_MAX_LABEL_LEN = 90


@dataclass(frozen=True)
class Figures:
    """Figures proven to come from ONE table of one filing."""

    revenue: float
    revenue_label: str
    eps: float
    eps_label: str
    table_index: int
    adjusted_eps: float | None = None
    adjusted_eps_label: str = ""

    @property
    def comparison_eps(self) -> float:
        """The figure a consensus estimate may be compared against.

        The adjusted number when the release states one, because that is the
        basis the estimate was set on; otherwise the GAAP figure, which the
        caller must then treat as uncomparable.
        """
        return self.adjusted_eps if self.adjusted_eps is not None else self.eps

    @property
    def basis(self) -> str:
        return "adjusted" if self.adjusted_eps is not None else "gaap"

    @property
    def eps_is_diluted(self) -> bool:
        """Whether the per-share row we took is the DILUTED one.

        Consensus estimates are quoted on diluted shares. A basic figure
        compared against a diluted estimate is not a small imprecision — it is
        a different number, always in our favour, which is the direction a
        publishing error must never be allowed to run.
        """
        return bool(_DILUTED_RE.search(self.eps_label))


_DILUTED_RE = re.compile(r"diluted", re.I)


def _scan_rows(
    table: list[list[str]],
    label_re: re.Pattern[str],
    exclude_re: re.Pattern[str],
    *,
    prefer_re: re.Pattern[str] | None = None,
) -> tuple[str, float] | None:
    """First row of *table* whose label matches and whose first number parses.

    ``prefer_re`` runs a preferring pass first. It exists for one reason: basic
    and diluted EPS sit in adjacent rows of the same statement, the market and
    every consensus estimate quote DILUTED, and taking whichever comes first
    published Ball's "Total basic earnings per share" and Kimberly-Clark's
    "Basic Earnings per Share" as though they were the diluted figure. Basic is
    a different, higher number — reporting it against a diluted consensus
    manufactures a beat.
    """
    def _first(match_pref: bool) -> tuple[str, float] | None:
        for row in table:
            if len(row) < 2:
                continue
            label = _html.unescape(row[0]).strip()
            if not label or len(label) > _MAX_LABEL_LEN:
                continue
            if exclude_re.search(label):
                continue
            if not label_re.search(label):
                continue
            if match_pref and prefer_re is not None and not prefer_re.search(label):
                continue
            for cell in row[1:]:
                value = cell_number(cell)
                if value is not None:
                    return label, value
        return None

    if prefer_re is not None:
        preferred = _first(True)
        if preferred is not None:
            return preferred
    return _first(False)


def figures_from_tables(tables: Iterable[list[list[str]]]) -> Figures | None:
    """Apply the same-table rule. None means "we could not prove it" — see module doc.

    The first table yielding BOTH a revenue row and a per-share row is the
    consolidated statement of operations. Returning the FIRST such table (rather
    than, say, the widest) is what keeps McDonald's on ``Revenues`` $7,099
    instead of the franchised-revenue sub-line further down the exhibit.
    """
    table_list = list(tables)
    for index, table in enumerate(table_list):
        revenue = _scan_rows(table, REVENUE_LABEL_RE, REVENUE_EXCLUDE_RE)
        if revenue is None:
            continue
        eps = _scan_rows(table, EPS_LABEL_RE, EPS_EXCLUDE_RE, prefer_re=_DILUTED_RE)
        if eps is None:
            continue
        # The adjusted figure lives in the non-GAAP reconciliation, which is a
        # DIFFERENT table from the statement of operations — so this one scan
        # deliberately ranges over the whole document. It is a labelled lookup,
        # not a positional guess: a row has to call itself adjusted to be read
        # as adjusted.
        adjusted = adjusted_eps_from_tables(table_list)
        return Figures(
            revenue=revenue[1], revenue_label=revenue[0],
            eps=eps[1], eps_label=eps[0], table_index=index,
            adjusted_eps=adjusted[1] if adjusted else None,
            adjusted_eps_label=adjusted[0] if adjusted else "",
        )
    return None


def adjusted_eps_from_tables(
    tables: Iterable[list[list[str]]],
) -> tuple[str, float] | None:
    """First labelled adjusted / non-GAAP per-share figure anywhere in the filing."""
    for table in tables:
        hit = _scan_rows(table, ADJUSTED_EPS_LABEL_RE, EPS_EXCLUDE_RE,
                         prefer_re=_DILUTED_RE)
        if hit is not None and abs(hit[1]) <= MAX_ABS_EPS:
            return hit
    return None


def eps_is_plausible(eps: float, *, consensus: float | None) -> tuple[bool, str]:
    """Last tripwire before a figure becomes a post.

    The same-table rule already refuses segment tables, so this is the belt to
    its braces: it catches a per-share label sitting on a row that is not a
    per-share row at all. Returns (ok, reason-when-not).
    """
    if eps != eps or eps in (float("inf"), float("-inf")):   # NaN / inf
        return False, "eps is not a finite number"
    if abs(eps) > MAX_ABS_EPS:
        return False, f"|eps| {abs(eps):,.2f} exceeds {MAX_ABS_EPS:,.0f} — not a per-share figure"
    if consensus is not None and consensus == consensus and consensus != 0:
        span = abs(consensus) * EPS_CONSENSUS_TOLERANCE
        if abs(eps - consensus) > span:
            return False, (
                f"eps {eps:,.2f} is more than {EPS_CONSENSUS_TOLERANCE:g}x consensus "
                f"{consensus:,.2f} away — probably the wrong row"
            )
    return True, ""


# A GAAP print and an adjusted consensus can differ honestly and by a lot — a
# real miss is real. But past this gap the likelier explanation is that we read
# a different MEASURE than the estimate was set against (one-off charges,
# amortisation, impairments), not that the company missed by that much. In one
# live run this shape produced "FIS 0.45 vs est 1.47" and "KMB 1.04 vs est
# 2.00": both would have published as catastrophic misses that did not happen.
MAX_CONSENSUS_DIVERGENCE = 0.45


def comparable_to_consensus(
    eps: float, *, consensus: float | None, basis: str = "gaap"
) -> tuple[bool, str]:
    """May this figure be compared to the calendar consensus at all?

    Two gates, and the first is the important one:

    * A GAAP figure is NOT comparable to an adjusted estimate. The estimate was
      set on a different measure, so any beat/miss drawn from it is an artifact
      of the mismatch. Only an ``adjusted`` basis is admitted for comparison.
    * Even on the right basis, a gulf this wide is more likely a mis-read row
      than a real result, so it is still declined.

    Returns (comparable, reason-when-not). No consensus at all is comparable:
    there is nothing to contradict, and the composer states the figure alone.
    """
    if consensus is None or consensus != consensus or consensus == 0:
        return True, ""
    if basis != "adjusted":
        return False, (
            "the release states only a GAAP per-share figure while the estimate "
            f"({consensus:,.2f}) is quoted on adjusted earnings — different measures"
        )
    divergence = abs(eps - consensus) / max(abs(consensus), 0.01)
    if divergence > MAX_CONSENSUS_DIVERGENCE:
        return False, (
            f"adjusted {eps:,.2f} against a {consensus:,.2f} estimate is "
            f"{divergence * 100:,.0f}% apart — probably the wrong row"
        )
    return True, ""


# ─────────────────────────────────────────────────────────────────────────────
# The calendar watchlist
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Expectation:
    """What we already knew about a name before it reported."""

    ticker: str
    cik: int
    session: str = "rth"           # premarket | postmarket | rth
    eps_forecast: float | None = None
    quarter: str | None = None


def _session_from_calendar(next_time: str) -> str:
    low = (next_time or "").lower()
    if "pre" in low:
        return "premarket"
    if "after" in low or "post" in low:
        return "postmarket"
    return "rth"


def load_calendar(day: date, *, root: Path) -> dict[str, Expectation]:
    """Names expected to report on *day*, keyed by ticker.

    Reads ``data/earnings/earnings.parquet`` — the Nasdaq-sourced calendar the
    nightly already maintains, which carries next_date, next_time and
    ``eps_forecast``. That consensus is why this lane can say "against $3.32
    expected" at all: nothing in the 8-K states the estimate.

    Returns {} (loudly) when the store is missing or unreadable. CIK is filled
    in by ``attach_ciks``.
    """
    path = Path(root) / "data" / "earnings" / "earnings.parquet"
    if not path.exists():
        _warn("edgar-earnings-calendar",
              f"{path} is missing — the wire has no watchlist and will match nothing")
        return {}
    try:
        import pandas as pd
    except Exception:
        _warn("edgar-earnings-calendar",
              "pandas is not installed — cannot read the earnings calendar")
        return {}
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:
        _warn("edgar-earnings-calendar", f"unreadable earnings calendar: {exc}")
        return {}

    wanted = day.isoformat()
    out: dict[str, Expectation] = {}
    for ticker, row in frame.iterrows():
        if str(row.get("next_date", ""))[:10] != wanted:
            continue
        forecast = row.get("eps_forecast")
        try:
            forecast = float(forecast)
            if forecast != forecast:                       # NaN
                forecast = None
        except (TypeError, ValueError):
            forecast = None
        symbol = str(ticker).strip().upper()
        if not symbol:
            continue
        out[symbol] = Expectation(
            ticker=symbol,
            cik=0,
            session=_session_from_calendar(str(row.get("next_time", ""))),
            eps_forecast=forecast,
        )
    if not out:
        _notice("edgar-earnings-calendar",
                f"no names on the calendar for {wanted} — the wire will idle")
    return out


def attach_ciks(
    expectations: dict[str, Expectation],
    cik_map: dict[str, int],
) -> dict[int, Expectation]:
    """Re-key the watchlist by CIK, dropping names we cannot map.

    A ticker with no CIK cannot be recognised on the filings feed, so it is
    reported rather than silently lost.
    """
    out: dict[int, Expectation] = {}
    unmapped: list[str] = []
    for ticker, exp in expectations.items():
        cik = cik_map.get(ticker.upper())
        if not cik:
            unmapped.append(ticker)
            continue
        out[int(cik)] = Expectation(
            ticker=exp.ticker, cik=int(cik), session=exp.session,
            eps_forecast=exp.eps_forecast, quarter=exp.quarter,
        )
    if unmapped:
        head = ", ".join(sorted(unmapped)[:12])
        _notice("edgar-earnings-cikmap",
                f"{len(unmapped)} calendar names have no CIK and cannot be matched: {head}")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Event construction (pure)
# ─────────────────────────────────────────────────────────────────────────────

def _quarter_label(period_end: str | None, when: datetime) -> str | None:
    if period_end:
        m = re.match(r"(\d{4})-(\d{2})", period_end)
        if m:
            year, month = int(m.group(1)), int(m.group(2))
            return f"Q{(month - 1) // 3 + 1} {year}"
    return None


def build_event(
    exp: Expectation,
    figures: Figures,
    *,
    when: datetime,
    accession: str,
    source_url: str = "",
    revenue_scale: float = 1e6,
    quarter: str | None = None,
    cik: int | None = None,
    acceptance_datetime: str = "",
    filing_date: str = "",
    form: str = "",
) -> dict[str, Any]:
    """Assemble an ``earnings_feed``-schema event.

    ``eps_est`` carries the calendar consensus. When we have none it mirrors the
    actual — the same convention ``earnings_feed`` used, which makes the surprise
    0.0 and the post read "in line" rather than inventing a beat.

    ``revenue_scale`` converts the statement's units to dollars. These tables are
    stated in millions ("Dollars in millions, except per share data") and the
    caller passes the scale it detected; the default is the near-universal case.

    TWO CLOCKS, AND THEY ARE NOT INTERCHANGEABLE (Wave 1B, contract freeze Q2).
    ``when`` is this process's wall clock at the moment it read the filing — it
    is what the downstream feed orders and dedupes on, so it keeps that meaning
    and ``when_semantics`` now says so out loud.  ``acceptance_datetime`` is the
    SEC's own acceptance timestamp for the filing, carried through unchanged.
    Only the second can support "no consumer outran the source"; before this
    wave the event carried only the first, and nothing recorded the difference.

    ``cik`` completes the canonical filing key.  Without it these events shared
    exactly ``ticker`` with the 8-K store — an alias with a validity window, not
    a durable key — and the two EDGAR planes could not be joined at all.
    """
    reported = figures.comparison_eps
    estimate = exp.eps_forecast if exp.eps_forecast is not None else reported
    resolved_cik = int(cik) if cik is not None else (int(exp.cik) if exp.cik else None)
    return {
        "id": f"{exp.ticker}-{accession}",
        "ticker": exp.ticker,
        "when": when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "when_semantics": "processing_wall_clock",
        "eps_actual": float(reported),
        "eps_est": float(estimate),
        "rev_actual": float(figures.revenue) * revenue_scale,
        "rev_est": None,                 # no consensus revenue in the calendar
        "quarter": quarter or _quarter_label(None, when),
        "source": SOURCE_ID,
        # Provenance — the filing is the receipt for every figure above.
        # (cik, accession) is the canonical filing key; the acceptance
        # timestamp and filing date are the SOURCE's, read from the same
        # submissions payload that confirmed Item 2.02.
        "cik": resolved_cik,
        "accession": accession,
        "filing_key": (
            f"{resolved_cik:010d}:{accession}" if resolved_cik is not None else ""
        ),
        "form": form,
        "filing_date": filing_date,
        "acceptance_datetime": acceptance_datetime,
        "acceptance_datetime_source": "sec_submissions.acceptanceDateTime",
        "source_url": source_url,
        "_session": exp.session,
        "_revenue_label": figures.revenue_label,
        "_eps_label": (figures.adjusted_eps_label or figures.eps_label),
        # The measure `eps_actual` is on. The composer MUST NOT frame a
        # beat/miss unless this reads "adjusted" — a GAAP figure against an
        # adjusted estimate is a different measure, not a result.
        "_eps_basis": figures.basis,
        "_eps_gaap": float(figures.eps),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Unit detection
# ─────────────────────────────────────────────────────────────────────────────

_UNITS_RE = re.compile(r"in\s+(thousands|millions|billions)", re.I)
_UNIT_SCALE = {"thousands": 1e3, "millions": 1e6, "billions": 1e9}

_TABLE_OPEN_RE = re.compile(r"<table\b", re.I)


def table_offsets(html_text: str) -> list[int]:
    """Character offset of each ``<table`` open tag, in document order.

    Parallel to ``parse_tables``' output, so a table's index can be turned back
    into a position in the source document.
    """
    return [m.start() for m in _TABLE_OPEN_RE.finditer(html_text)]


def revenue_scale_from(html_text: str, *, table_index: int | None = None) -> float:
    """Dollar multiplier for the units the chosen statement is stated in.

    A wrong scale is a 1000x error in a published figure — the worst class of
    mistake this module can make, because the number looks authoritative and is
    off by three orders of magnitude.

    Reading a fixed prefix of the document is not good enough. Trex states
    "($ in thousands, except per share data)" beside its statement roughly
    11,500 characters into the TEXT and much further into the HTML, so a
    head-only scan missed it and defaulted to millions: $418M was published as
    $418B. Filings also carry SEVERAL captions (income statement in thousands,
    a highlights table in millions), so the only caption that can be trusted is
    the one governing the table we actually read.

    So: when ``table_index`` is known, use the NEAREST caption at or before that
    table. Otherwise fall back to the first caption anywhere in the document,
    and to millions when there is none.
    """
    if table_index is not None:
        offsets = table_offsets(html_text)
        if 0 <= table_index < len(offsets):
            # Search the whole span up to the table and take the LAST caption:
            # captions precede the table they describe.
            preceding = [m for m in _UNITS_RE.finditer(html_text, 0, offsets[table_index])]
            if preceding:
                return _UNIT_SCALE[preceding[-1].group(1).lower()]
            following = _UNITS_RE.search(html_text, offsets[table_index])
            if following:
                return _UNIT_SCALE[following.group(1).lower()]
            return 1e6
    first = _UNITS_RE.search(html_text)
    return _UNIT_SCALE[first.group(1).lower()] if first else 1e6


# "Three Months Ended June 30, 2026" / "second quarter ended June 30, 2026" —
# the fiscal period the release actually covers.
_PERIOD_END_RE = re.compile(
    r"(?:three|3)\s+months\s+ended\s+([A-Z][a-z]+)\s+(\d{1,2}),?\s+(\d{4})"
    r"|quarter\s+ended\s+([A-Z][a-z]+)\s+(\d{1,2}),?\s+(\d{4})",
    re.I,
)
_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}


def period_end_from(text: str) -> str:
    """Fiscal period end stated by the release, as ``YYYY-MM-DD``, or "".

    EDGAR's ``reportDate`` for an 8-K is the date of the TRIGGERING EVENT, not
    the period being reported: Trex's Q2 filing carries reportDate 2026-08-04.
    Deriving a quarter from it labelled every Q2 release in one live run "Q3
    2026". The release itself states the period, so read it from there.
    """
    m = _PERIOD_END_RE.search(text)
    if not m:
        return ""
    month_name = (m.group(1) or m.group(4) or "").lower()
    day = m.group(2) or m.group(5)
    year = m.group(3) or m.group(6)
    month = _MONTHS.get(month_name)
    if not month or not day or not year:
        return ""
    return f"{int(year):04d}-{month:02d}-{int(day):02d}"


# ─────────────────────────────────────────────────────────────────────────────
# I/O
# ─────────────────────────────────────────────────────────────────────────────

Fetcher = Callable[[str], str]


def http_get(url: str) -> str:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"}
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S) as response:  # noqa: S310
        raw = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            import gzip
            raw = gzip.decompress(raw)
    return raw.decode("utf-8", errors="replace")


def load_cik_map(*, root: Path, fetch: Fetcher | None = None) -> dict[str, int]:
    """ticker → CIK, from the cached company_tickers.json, refreshed on demand."""
    cache = Path(root) / "data" / "edgar" / "company_tickers.json"
    payload: str | None = None
    if cache.exists():
        try:
            payload = cache.read_text(encoding="utf-8")
        except Exception:
            payload = None
    if payload is None:
        getter = fetch or http_get
        try:
            payload = getter("https://www.sec.gov/files/company_tickers.json")
        except Exception as exc:
            _warn("edgar-earnings-cikmap",
                  f"could not load company_tickers.json ({exc}) — the wire cannot match filings")
            return {}
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(payload, encoding="utf-8")
        except Exception:
            pass                      # a read-only checkout is not a wire failure
    try:
        data = json.loads(payload)
    except Exception as exc:
        _warn("edgar-earnings-cikmap", f"company_tickers.json is unparseable: {exc}")
        return {}
    out: dict[str, int] = {}
    rows = data.values() if isinstance(data, dict) else data
    for row in rows:
        try:
            out[str(row["ticker"]).strip().upper()] = int(row["cik_str"])
        except (KeyError, TypeError, ValueError):
            continue
    return out


@dataclass(frozen=True)
class SubmissionRecord:
    """What the SOURCE says about one filing.

    Every field here is EDGAR's own value.  ``acceptance_datetime`` in
    particular is the SEC's acceptance clock, not this process's — the two are
    hours to days apart on any real filing, and only the source's can support
    the claim that no consumer outran the source.
    """

    confirmed_earnings: bool = False
    period_end: str = ""
    form: str = ""
    filing_date: str = ""
    acceptance_datetime: str = ""
    found: bool = False


def submission_record(
    cik: int, accession: str, *, fetch: Fetcher | None = None
) -> SubmissionRecord:
    """Read the source's own record of one filing from the submissions JSON.

    Item membership is matched on EXACT comma-separated tokens: the field reads
    "2.02,9.01", and substring matching would also accept "12.02".

    The acceptance timestamp and filing date are read here, from the SAME
    request that already confirmed Item 2.02 — so carrying the source clock
    downstream costs nothing.  Before Wave 1B this function read the payload,
    threw those two fields away, and the wire stamped events with
    ``datetime.now()`` instead (contract freeze Q2).
    """
    getter = fetch or http_get
    try:
        payload = json.loads(getter(SUBMISSIONS_FMT.format(cik=cik)))
    except Exception as exc:
        _warn("edgar-earnings-submissions",
              f"CIK {cik}: submissions unreadable ({exc}) — cannot confirm Item 2.02")
        return SubmissionRecord()
    recent = (payload.get("filings") or {}).get("recent") or {}
    numbers = recent.get("accessionNumber") or []
    items = recent.get("items") or []
    reports = recent.get("reportDate") or []
    forms = recent.get("form") or []
    filed = recent.get("filingDate") or []
    accepted = recent.get("acceptanceDateTime") or []

    def _at(values: Any, index: int) -> str:
        try:
            return str(values[index]) if index < len(values) else ""
        except TypeError:
            return ""

    for index, number in enumerate(numbers):
        if number != accession:
            continue
        raw = _at(items, index)
        tokens = [t.strip() for t in raw.split(",")]
        return SubmissionRecord(
            confirmed_earnings=ITEM_EARNINGS in tokens,
            period_end=_at(reports, index),
            form=_at(forms, index),
            filing_date=_at(filed, index),
            acceptance_datetime=normalize_acceptance(_at(accepted, index)),
            found=True,
        )
    return SubmissionRecord()


def confirm_earnings_item(
    cik: int, accession: str, *, fetch: Fetcher | None = None
) -> tuple[bool, str]:
    """Back-compat shim over ``submission_record``.

    Kept because callers and tests hold this two-tuple shape; new code should
    read the record, which carries the source's clocks as well.
    """
    record = submission_record(cik, accession, fetch=fetch)
    return record.confirmed_earnings, record.period_end


_DOC_HREF_RE = re.compile(r'href="[^"]*/([^"/]+\.html?)"', re.I)
_EXHIBIT_HINT_RE = re.compile(r"ex.{0,4}99|99.{0,4}1|earn|press|release", re.I)


def press_release_documents(
    cik: int, accession: str, *, fetch: Fetcher | None = None
) -> list[str]:
    """Candidate exhibit URLs for a filing, most-likely first."""
    getter = fetch or http_get
    base = ARCHIVE_FMT.format(cik=cik, accession=accession.replace("-", ""))
    try:
        index_html = getter(base + "/")
    except Exception as exc:
        _warn("edgar-earnings-index", f"CIK {cik} {accession}: filing index unreadable ({exc})")
        return []
    names: list[str] = []
    for name in _DOC_HREF_RE.findall(index_html):
        if name not in names:
            names.append(name)
    hinted = [n for n in names if _EXHIBIT_HINT_RE.search(n)]
    ordered = hinted + [n for n in names if n not in hinted]
    return [f"{base}/{n}" for n in ordered]


@dataclass
class TickStats:
    """What one poll did — so a quiet wire can be told from a broken one."""

    feed_entries: int = 0
    watchlist_size: int = 0
    matched: int = 0
    confirmed_202: int = 0
    extracted: int = 0
    declined_no_table: int = 0
    declined_implausible: int = 0
    declined_basic_eps: int = 0
    declined_basis_mismatch: int = 0
    adjusted_basis: int = 0
    fetch_failures: int = 0
    events: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "feed_entries": self.feed_entries,
            "watchlist_size": self.watchlist_size,
            "matched": self.matched,
            "confirmed_202": self.confirmed_202,
            "extracted": self.extracted,
            "declined_no_table": self.declined_no_table,
            "declined_implausible": self.declined_implausible,
            "declined_basic_eps": self.declined_basic_eps,
            "declined_basis_mismatch": self.declined_basis_mismatch,
            "adjusted_basis": self.adjusted_basis,
            "fetch_failures": self.fetch_failures,
            "events": self.events,
        }


class EdgarEarningsProvider:
    """Drop-in ``earnings_feed.EarningsProvider`` backed by EDGAR.

    Fail-soft like every provider on that seam — ``fetch`` returns [] rather
    than raising — but never fail-SILENT: the reason is always annotated, and
    ``last_stats`` carries the tick's census for the caller to report.

    ``seen`` is the caller-owned dedupe set of accession keys. The fast lane has
    its own durable seen-ledger; this is only in-process protection against
    re-reading the same filing on the next poll.

    The injected HTTP getter is ``_get``, NOT ``fetch``: ``fetch(since)`` is the
    protocol method, and holding the getter under the same name would let an
    instance attribute shadow it — ``provider.fetch(datetime)`` would then call
    the HTTP getter with a datetime as its URL.
    """

    def __init__(
        self,
        *,
        root: Path,
        fetch: Fetcher | None = None,
        day: date | None = None,
        seen: set[str] | None = None,
        max_filings_per_tick: int = 40,
    ) -> None:
        self.root = Path(root)
        self._get: Fetcher = fetch or http_get
        self.day = day
        self.seen: set[str] = seen if seen is not None else set()
        self.max_filings_per_tick = max_filings_per_tick
        self.last_stats = TickStats()

    # -- helpers ---------------------------------------------------------

    def _watchlist(self, day: date) -> dict[int, Expectation]:
        calendar = load_calendar(day, root=self.root)
        if not calendar:
            return {}
        cik_map = load_cik_map(root=self.root, fetch=self._get)
        if not cik_map:
            return {}
        return attach_ciks(calendar, cik_map)

    def _extract(self, url: str) -> tuple[Figures | None, float, str]:
        body = self._get(url)
        figures = figures_from_tables(parse_tables(body))
        if figures is None:
            return None, 1e6, ""
        scale = revenue_scale_from(body, table_index=figures.table_index)
        return figures, scale, period_end_from(_visible_text(body))

    # -- the seam --------------------------------------------------------

    def fetch(self, since: datetime) -> list[dict[str, Any]]:
        """``EarningsProvider`` protocol entry point."""
        stats = TickStats()
        self.last_stats = stats
        now = datetime.now(timezone.utc)
        day = self.day or now.date()

        watchlist = self._watchlist(day)
        stats.watchlist_size = len(watchlist)
        if not watchlist:
            return []

        try:
            feed = self._get(CURRENT_FEED_URL)
        except Exception as exc:
            _warn("edgar-earnings-feed",
                  f"current-filings feed unreachable ({exc}) — no earnings can be detected this tick")
            stats.fetch_failures += 1
            return []

        filings = parse_current_feed(feed)
        stats.feed_entries = len(filings)
        if not filings and feed.strip():
            _warn("edgar-earnings-feed",
                  f"feed returned {len(feed)} bytes but no parseable entries — "
                  "EDGAR may have changed the format")
            return []

        events: list[dict[str, Any]] = []
        for filing in filings[: self.max_filings_per_tick]:
            exp = watchlist.get(filing.cik)
            if exp is None or filing.key in self.seen:
                continue
            stats.matched += 1
            self.seen.add(filing.key)

            record = submission_record(
                filing.cik, filing.accession, fetch=self._get)
            period_end = record.period_end
            time.sleep(POLITE_SLEEP_S)
            if not record.confirmed_earnings:
                continue
            stats.confirmed_202 += 1
            if not record.acceptance_datetime:
                # Fail-soft but never fail-silent: an event with no source
                # clock still ships, and the gap is named rather than papered
                # over with the processing clock.
                _notice("edgar-earnings-acceptance",
                        f"{exp.ticker} {filing.accession}: submissions payload carries no "
                        "acceptanceDateTime — the event ships with an empty source clock "
                        "rather than borrowing the processing clock")

            figures: Figures | None = None
            scale = 1e6
            source_url = ""
            stated_period = ""
            for url in press_release_documents(
                    filing.cik, filing.accession, fetch=self._get)[:3]:
                try:
                    figures, scale, stated_period = self._extract(url)
                except Exception as exc:
                    stats.fetch_failures += 1
                    _warn("edgar-earnings-exhibit",
                          f"{exp.ticker}: exhibit unreadable ({exc})")
                    continue
                finally:
                    time.sleep(POLITE_SLEEP_S)
                if figures is not None:
                    source_url = url
                    break

            if figures is None:
                stats.declined_no_table += 1
                _notice("edgar-earnings-declined",
                        f"{exp.ticker} {filing.accession}: no table carries BOTH a revenue row "
                        "and a per-share row — declining rather than guessing")
                continue

            ok, reason = eps_is_plausible(figures.eps, consensus=exp.eps_forecast)
            if not ok:
                stats.declined_implausible += 1
                _warn("edgar-earnings-implausible",
                      f"{exp.ticker} {filing.accession}: {reason} "
                      f"(row {figures.eps_label!r}) — dropped")
                continue

            if not figures.eps_is_diluted:
                stats.declined_basic_eps += 1
                _notice("edgar-earnings-basic-eps",
                        f"{exp.ticker} {filing.accession}: only a BASIC per-share row was found "
                        f"({figures.eps_label!r}); consensus is quoted diluted, so a comparison "
                        "would overstate the result — declining")
                continue

            comparable, why = comparable_to_consensus(
                figures.comparison_eps, consensus=exp.eps_forecast,
                basis=figures.basis)
            if not comparable:
                stats.declined_basis_mismatch += 1
                _notice("edgar-earnings-basis",
                        f"{exp.ticker} {filing.accession}: {why}; declining rather than "
                        "printing a beat or miss we cannot stand behind")
                continue
            if figures.basis == "adjusted":
                stats.adjusted_basis += 1

            stats.extracted += 1
            events.append(build_event(
                exp, figures, when=now, accession=filing.accession,
                source_url=source_url, revenue_scale=scale,
                quarter=_quarter_label(stated_period or period_end, now),
                cik=filing.cik,
                acceptance_datetime=record.acceptance_datetime,
                filing_date=record.filing_date,
                form=record.form,
            ))

        stats.events = len(events)
        return events

    # Back-compat alias: `earnings_feed.fetch_events(since, provider=...)` calls
    # `provider.fetch`, but callers holding this class directly read better with
    # the explicit name.
    fetch_events = fetch
