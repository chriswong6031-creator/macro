"""FOMC statement collector — the substrate the statement-diff desk reads.

WHY THIS EXISTS. The press wire (engine/marketing/press_lane.py) already sees the
Fed's own RSS the moment a statement drops, and breaking_relevance already grades
the headline. What neither had was the STATEMENT: the wire carries a title and a
link, so the only post the house could write about the most-watched macro event of
the quarter was a headline relay. The diff desk's whole substrate is the text —
what the Committee changed since last meeting is the story, and it cannot be read
off a headline.

WHAT THIS MODULE OWNS (and nothing else):
  • the decision calendar        — READ from engine.event_calendar, never duplicated
  • the statement URL pattern    — federalreserve.gov monetary policy press releases
  • extraction                   — HTML in, clean statement paragraphs out (pure)
  • the store                    — data/fomc/statements/<YYYY-MM-DD>.txt
  • the ledger                   — data/fomc/statements.jsonl (append-only)

The diff lives in engine/marketing/fomc_diff.py, the writing in fomc_desk.py and
the card in fomc_card.py. This module never calls a model and never posts.

REFUSE RATHER THAN GUESS. :func:`extract_statement` returns [] on anything it
cannot positively identify as an FOMC statement body, and :func:`fetch_statement`
returns None on every network or parse failure. A desk handed [] writes nothing —
which is the correct output for a page the Fed reformatted under us, and is very
much better than a confident post about paragraphs we mis-sliced.

NETWORK. One GET, hard timeout, byte cap, no retries of our own (the press tick
runs every 5 minutes, so the retry is the next tick). Never raises.
"""
from __future__ import annotations

import hashlib
import html as _html
import json
import logging
import os
import re
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# The decision calendar
# ─────────────────────────────────────────────────────────────────────────────
#
# READ FROM event_calendar, DO NOT RESTATE. `engine.event_calendar._FOMC` is the
# repo's transcription of the Fed-published 2026 decision dates and it already
# feeds the dashboard calendar, the commodities watch list and (via
# engine/event_window.py) the factor-era phase classifier. A second copy here
# would be a fourth reader of a third list, and the module docstring of
# event_calendar exists precisely because two copies of the FOMC schedule had
# already disagreed once in this repo.
#
# The literal below is a FALLBACK for a checkout where that import fails, not a
# second source of truth: tests/test_marketing_fomc_desk.py pins it EQUAL to
# event_calendar._FOMC, so a 2027 refresh that touches one and not the other
# fails a test instead of silently splitting the calendar in two.
#
# Source: Federal Reserve, "Meeting calendars and information" —
# https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
# Each 2026 meeting is two days; the DECISION day is the second, and the
# statement is released at 14:00 ET. Remaining as of 2026-08-08: Sep 15-16,
# Oct 27-28, Dec 8-9 (i.e. the 09-16 / 10-28 / 12-09 rows below).
_FOMC_2026_FALLBACK: tuple[str, ...] = (
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
)

#: The statement is released at 14:00 ET on the decision day (Fed practice since
#: the 2013 move from 14:15). Kept as data because the desk's "did the statement
#: land yet" question is a clock question and the answer must be readable.
STATEMENT_RELEASE_ET = "14:00"

#: Where the store lives, relative to the repo root.
#:
#: UNDER data/marketing/ ON PURPOSE, AND THIS IS LOAD-BEARING.
#: `.github/workflows/marketing-press-wire.yml` runs this desk on ubuntu with a
#: SPARSE CHECKOUT every 5 minutes, and its cone is engine/scripts/lib/config/
#: data-marketing/site-live. A store at `data/fomc/` is outside that cone, so on
#: a live decision day the prior statement and the ledger would simply not be on
#: disk: every tick would read [] for the baseline, refuse for
#: `no_prior_statement`, re-fetch federalreserve.gov, and throw the result away
#: at job end — 288 GETs, zero posts, no idempotency (the ledger never survives a
#: tick either), and the NEXT meeting left with no baseline as well.
#:
#: `data/marketing` is already in the cone, so the read path costs nothing. The
#: WRITE path still has to be declared: the workflow stages only this lane's own
#: paths (its "ledger law" comment), so `data/marketing/fomc` is named in its
#: `git add` list. Both halves are pinned by
#: tests/test_marketing_fomc_desk.py::test_press_wire_workflow_covers_the_store,
#: because this coupling is invisible from inside the module and it is exactly
#: what would have shipped a silently dead lane.
STORE_ROOT = Path("data") / "marketing" / "fomc"
STORE_DIR = STORE_ROOT / "statements"
LEDGER_PATH = STORE_ROOT / "statements.jsonl"

#: Monetary-policy press releases are `monetary<YYYYMMDD>a.htm`. The trailing
#: `a` is the Fed's own release-letter suffix (the Implementation Note that ships
#: beside the statement is `a1`), stable across every announcement in the
#: archive we read.
_URL_TEMPLATE = ("https://www.federalreserve.gov/newsevents/pressreleases/"
                 "monetary{ymd}a.htm")

_FETCH_TIMEOUT_S = 12
_MAX_BYTES = 4 * 1024 * 1024
_UA = "MastermindFOMCBot/1.0 (+https://mastermind-x.com)"

# ─────────────────────────────────────────────────────────────────────────────
# Extraction
# ─────────────────────────────────────────────────────────────────────────────

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_P_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)
_WS_RE = re.compile(r"\s+")

#: Chrome that lives INSIDE the article container on federalreserve.gov and is
#: not statement text. Matched on a lowercased prefix, so a paragraph that merely
#: mentions one of these phrases mid-sentence is kept.
_BOILERPLATE_PREFIXES: tuple[str, ...] = (
    "for media inquiries",
    "implementation note issued",
    "board of governors of the federal reserve system",
    "20th street and constitution avenue",
    "last update",
    "please enable javascript",
    "an official website",
    "official websites use",
    "secure .gov websites use",
    "the federal reserve, the central bank of the united states",
    "share",
    "for release at",
)

#: A body we will accept as an FOMC statement must say this. It is the one token
#: every statement in the archive carries and no nav fragment does, so it is the
#: cheap positive identification that turns a mis-slice into a refusal.
_REQUIRED_TOKEN = "committee"


def _clean_paragraph(raw: str) -> str:
    """One <p> body -> collapsed plain text ("" when it holds nothing)."""
    text = _TAG_RE.sub(" ", raw)
    text = _html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def extract_statement(html_text: str) -> list[str]:
    """Statement paragraphs from a Fed press-release page. [] = refused.

    PURE — no network, no filesystem, no clock. Tested directly against the two
    committed fixtures.

    The slice is structural rather than positional: the page's statement body is
    the second ``col-xs-12 col-sm-8`` column inside ``<div id="article">`` (the
    first is the heading block carrying the date, the title and the share
    widget), and everything above ``<div id="article">`` is site navigation —
    which on this page is 44 paragraphs of it. A positional "drop the first N
    paragraphs" rule would work today and break the first time the Fed adds a
    menu item, so it is not used.

    Returns [] rather than a partial body when the container is missing, when
    fewer than two paragraphs survive, or when nothing in the result names the
    Committee. A desk handed [] writes nothing.
    """
    if not html_text or "<" not in html_text:
        return []

    body = html_text
    idx = body.find('<div id="article"')
    if idx < 0:
        # No article container. Every page in the archive has one, so this is a
        # page shape we do not understand — refuse rather than parse the nav.
        return []
    body = body[idx:]

    # Trim the site footer if it is inside our slice.
    for marker in ('<div id="footer', '<footer'):
        cut = body.lower().find(marker)
        if cut > 0:
            body = body[:cut]
            break

    # Skip the heading block: date, <h3> title and the share dropdown. The
    # statement column follows it and carries the same bootstrap class.
    head = body.find('class="heading')
    if head >= 0:
        col = body.find('class="col-xs-12 col-sm-8', head + 1)
        if col > 0:
            body = body[col:]

    body = _SCRIPT_STYLE_RE.sub(" ", body)

    out: list[str] = []
    for raw in _P_RE.findall(body):
        text = _clean_paragraph(raw)
        if not text:
            continue
        low = text.lower()
        if any(low.startswith(p) for p in _BOILERPLATE_PREFIXES):
            continue
        out.append(text)

    if len(out) < 2:
        return []
    if not any(_REQUIRED_TOKEN in p.lower() for p in out):
        return []
    return out


def statement_text(paragraphs: list[str]) -> str:
    """The canonical stored form: paragraphs joined by a blank line."""
    return "\n\n".join(p.strip() for p in paragraphs if p and p.strip())


def statement_sha(text: str) -> str:
    """sha256 of the canonical text. The ledger's revision detector."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Calendar
# ─────────────────────────────────────────────────────────────────────────────

def decision_dates(year: int | None = None) -> list[str]:
    """Every known FOMC decision date as YYYY-MM-DD, ascending.

    Read from engine.event_calendar._FOMC when importable (the repo's single
    transcription of the Fed calendar), else the pinned fallback above.
    """
    dates: list[str] = []
    try:
        from engine.event_calendar import _FOMC  # noqa: PLC0415
        dates = [str(d) for d, _sep in _FOMC]
    except Exception:  # noqa: BLE001 — a leaf calendar must never break the wire
        dates = list(_FOMC_2026_FALLBACK)
    dates = sorted({d for d in dates if _parse_date(d) is not None})
    if year is not None:
        dates = [d for d in dates if d.startswith(f"{int(year):04d}-")]
    return dates


def _parse_date(value: object) -> date | None:
    """YYYY-MM-DD (or a date/datetime) -> date. None when unreadable."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def is_decision_day(when: object) -> bool:
    """Is *when* an FOMC decision day (the second day of a meeting)?"""
    d = _parse_date(when)
    return bool(d) and d.isoformat() in set(decision_dates())


def prior_decision_date(when: object, *, root: Path | str | None = None) -> str | None:
    """The decision date immediately BEFORE *when*. None when unknown.

    Tries the calendar first, then the store — which is what carries the answer
    across a year boundary. The January meeting's predecessor is the previous
    December's, and the calendar in this repo is transcribed one year at a time,
    so for that one meeting a year the store is the only source that has it. When
    neither knows, the answer is None and the desk refuses: a diff against the
    wrong meeting is worse than no diff.
    """
    d = _parse_date(when)
    if d is None:
        return None
    target = d.isoformat()

    earlier = [x for x in decision_dates() if x < target]
    if earlier:
        return earlier[-1]

    stored = [x for x in stored_dates(root) if x < target]
    if stored:
        return stored[-1]
    return None


def statement_url(when: object) -> str | None:
    """The federalreserve.gov press-release URL for a decision date."""
    d = _parse_date(when)
    if d is None:
        return None
    return _URL_TEMPLATE.format(ymd=d.strftime("%Y%m%d"))


# ─────────────────────────────────────────────────────────────────────────────
# Store + ledger
# ─────────────────────────────────────────────────────────────────────────────

def _root(root: Path | str | None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parents[2]


def store_path(when: object, root: Path | str | None = None) -> Path | None:
    """Absolute path of the stored statement text for a decision date."""
    d = _parse_date(when)
    if d is None:
        return None
    return _root(root) / STORE_DIR / f"{d.isoformat()}.txt"


def ledger_path(root: Path | str | None = None) -> Path:
    return _root(root) / LEDGER_PATH


def read_statement(when: object, root: Path | str | None = None) -> list[str]:
    """Stored statement paragraphs for a date. [] when absent/unreadable."""
    path = store_path(when, root)
    if path is None or not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        log.warning("fomc_statements: unreadable store %s: %s", path, exc)
        return []
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def ledger_rows(root: Path | str | None = None) -> list[dict]:
    """Every ledger row, oldest first. [] when the ledger does not exist."""
    path = ledger_path(root)
    if not path.exists():
        return []
    rows: list[dict] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except OSError as exc:
        log.warning("fomc_statements: unreadable ledger %s: %s", path, exc)
    return rows


def stored_dates(root: Path | str | None = None) -> list[str]:
    """Decision dates the ledger knows about, ascending."""
    return sorted({str(r.get("date") or "") for r in ledger_rows(root)
                   if _parse_date(r.get("date")) is not None})


def is_collected(when: object, root: Path | str | None = None) -> bool:
    """Does the ledger already carry a row for this meeting?

    THIS IS THE DESK'S IDEMPOTENCY. The ledger row is written once, at the END
    of a desk firing, so a crash mid-firing leaves no row and the next 5-minute
    tick retries; a completed firing leaves a row and every later tick no-ops.
    One firing per meeting, and the store is the thing that remembers.
    """
    d = _parse_date(when)
    if d is None:
        return False
    return d.isoformat() in set(stored_dates(root))


def _atomic_write(path: Path, text: str) -> bool:
    """Write *text* to *path* atomically. False on failure (never raises)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return True
    except Exception as exc:  # noqa: BLE001 — a store write may not break the wire
        log.warning("fomc_statements: write failed for %s: %s", path, exc)
        return False


def append_ledger(row: dict, root: Path | str | None = None) -> bool:
    """Append one row to the append-only ledger. False on failure."""
    path = ledger_path(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("fomc_statements: ledger append failed: %s", exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Fetch
# ─────────────────────────────────────────────────────────────────────────────

def fetch_page(url: str, *, timeout_s: int = _FETCH_TIMEOUT_S) -> str | None:
    """GET *url* and return the decoded body. None on ANY failure.

    One attempt. The press wire ticks every 5 minutes, so a retry loop here
    would only turn a Fed hiccup into a slower tick; the next tick IS the retry.
    """
    if not url or not str(url).lower().startswith(("http://", "https://")):
        return None
    try:
        import urllib.request  # noqa: PLC0415

        req = urllib.request.Request(str(url), headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
            raw = resp.read(_MAX_BYTES + 1)
        if len(raw) > _MAX_BYTES:
            log.warning("fomc_statements: %s exceeded the %d byte cap", url, _MAX_BYTES)
            return None
        return raw.decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001 — a dead fetch must not break the wire
        log.warning("fomc_statements: fetch failed for %s (%s: %s)",
                    url, type(exc).__name__, exc)
        return None


def collect(
    when: object,
    *,
    url: str | None = None,
    root: Path | str | None = None,
    now: datetime | None = None,
    timeout_s: int = _FETCH_TIMEOUT_S,
    html_text: str | None = None,
    dry_run: bool = False,
) -> dict | None:
    """Fetch, extract and STORE the statement for a decision date.

    Writes ``data/marketing/fomc/statements/<date>.txt``. Does NOT write the
    ledger — that row is the desk's own record of a completed firing and is
    appended by :func:`record_collection` after the posts are enqueued, so an
    interrupted firing retries on the next tick instead of being remembered as
    done.

    `dry_run` suppresses the store write. It is not a nicety: the press wire has a
    `--dry-run` mode, and a dry tick that wrote the store would OVERWRITE the
    baseline the next real meeting diffs against — a read-only rehearsal silently
    mutating the one file the lane's product depends on.

    `url` overrides the derived press-release URL (the press wire hands us the
    link straight off the Fed's RSS item, which is more authoritative than a
    pattern). `html_text` skips the network entirely and is how the tests and
    the committed fixtures drive this.

    Returns {date, url, fetched_at, sha, paragraphs, text} or None.
    """
    d = _parse_date(when)
    if d is None:
        return None
    date_str = d.isoformat()
    resolved_url = str(url or statement_url(date_str) or "")

    page = html_text if html_text is not None else fetch_page(
        resolved_url, timeout_s=timeout_s)
    if not page:
        return None

    paragraphs = extract_statement(page)
    if not paragraphs:
        print("::warning title=fomc-statement-unreadable::"
              f"{date_str}: the press-release page at {resolved_url} yielded no "
              "statement body — the desk writes nothing this tick", flush=True)
        return None

    text = statement_text(paragraphs)
    if not dry_run:
        path = store_path(date_str, root)
        if path is not None:
            _atomic_write(path, text + "\n")

    ts = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "date": date_str,
        "url": resolved_url,
        "fetched_at": ts,
        "sha": statement_sha(text),
        "paragraphs": paragraphs,
        "text": text,
    }


def record_collection(
    collected: dict,
    *,
    root: Path | str | None = None,
    extra: dict | None = None,
) -> bool:
    """Append the ledger row that marks this meeting DONE.

    Called once, after the desk has finished (whatever the outcome), so the row
    is a record of a completed firing rather than of a successful fetch. `extra`
    carries the desk's own outcome fields (what was emitted, which writer mode
    produced it) so one row answers both "do we have the statement" and "did we
    already post about it".
    """
    if not isinstance(collected, dict) or not collected.get("date"):
        return False
    row = {
        "date": str(collected.get("date")),
        "url": str(collected.get("url") or ""),
        "fetched_at": str(collected.get("fetched_at") or ""),
        "sha": str(collected.get("sha") or ""),
        "paragraphs": len(collected.get("paragraphs") or []),
        "chars": len(str(collected.get("text") or "")),
    }
    if isinstance(extra, dict):
        row.update(extra)
    return append_ledger(row, root)
