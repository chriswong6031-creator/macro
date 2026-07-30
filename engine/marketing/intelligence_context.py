"""engine.marketing.intelligence_context — Intelligence Desk V2 §D.3.

Program: **Intelligence Desk V2** (``research/agentic_media/
INTELLIGENCE_DESK_V2_BY_FABLE.md``), acceptance gate D.3 and the §2 payload
contract's ``engine_context`` rows.

WHAT THIS IS
------------
A desk story names tickers. This module joins those tickers against the
REPO-COMMITTED engine artifacts the rest of the marketing lobe already reads —
congressional disclosures, Form-4 insider filings, and the earnings calendar —
and turns the hits into at most three plain bilingual lines::

    {"kind": "congress", "line_en": "Congress: 2 buy filings on NVDA in the "
                                    "past 45 days",
     "line_zh": "国会：过去 45 天 NVDA 有 2 笔买入申报",
     "as_of": "2026-07-27"}

**NO LLM ANYWHERE IN THIS MODULE.** These are engine facts. They are counted
from artifact rows, phrased by a fixed template in both languages, and stamped
with the artifact's own date. The phrasing pass
(``engine.marketing.intelligence_llm``) never sees them and never writes them.

THE FRESHNESS LAW (gate D.3)
----------------------------
A stale artifact is SKIPPED, never served as a fresh fact. Every row that
contributes to a line must carry its own date inside ``fresh_days`` of the
tick's clock, so an artifact that stopped updating produces no line at all
rather than a confident sentence about last quarter. That is not hypothetical:
``data/earnings/earnings.parquet`` is mostly a 2026-06-19 read today (3 of 1364
rows refreshed), and the per-row ``as_of`` gate is what keeps the other 1361
off the desk.

A count is only ever taken across rows from ONE artifact read. Nothing here
combines a number from one as_of with a number from another.

IMPORT-CLOSURE LAW
------------------
**stdlib only at module import.** ``pandas``, ``congress_feed`` and
``insider_feed`` are imported lazily inside the loaders: the thin
marketing-engine CI lane has no pandas, and the desk's own import closure is
stdlib-only so the 75-second daemon can always import it. Every loader is
fail-soft — a missing file, an unreadable frame, or no pandas at all returns an
empty list and the caller simply attaches no context.

Public API
----------
    attach_engine_context(packets, cfg, *, root, now) -> int
    context_rows(tickers, *, root, now, fresh_days, max_lines) -> list[dict]
    congress_line(rows, ticker, *, now, fresh_days) -> dict | None
    insider_line(rows, ticker, *, now, fresh_days) -> dict | None
    earnings_line(rows, ticker, *, now, fresh_days) -> dict | None
    load_congress_rows(root, *, since) -> list[dict]
    load_insider_rows(root, *, since) -> list[dict]
    load_earnings_rows(root) -> list[dict]
    reset_cache() -> None
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

log = logging.getLogger(__name__)


CONGRESS_REL = "data/quiver/congress.parquet"
INSIDERS_REL = "data/quiver/insiders.parquet"
EARNINGS_REL = "data/earnings/earnings.parquet"

#: §2 contract: at most three rows, each with its own as_of.
DEFAULT_MAX_LINES = 3
#: How old an artifact row may be and still be a fact about "now".
DEFAULT_FRESH_DAYS = 45
#: Fixed order — the desk reads the same way every night.
KINDS: tuple[str, ...] = ("congress", "insider", "earnings")

#: A static tuple, never ``strftime``: ``%B`` is locale-sensitive and this is
#: published copy.
_MONTHS_EN: tuple[str, ...] = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

#: The calendar's raw timing slugs, mapped to plain words in both languages. An
#: unmapped value (including "time-not-supplied") drops the clause rather than
#: printing a slug — raw slugs are banned from user-facing copy by house law.
_EARNINGS_TIME: dict[str, tuple[str, str]] = {
    "time-pre-market": ("pre-market", "盘前"),
    "time-after-hours": ("after hours", "盘后"),
}

#: Quiver's congress `Transaction` column. "Sale (Full)" / "Sale (Partial)" are
#: both sales; "Exchange" is neither and is deliberately uncounted.
_BUY_WORDS = ("purchase",)
_SELL_WORDS = ("sale", "sell")

#: Form-4 open-market purchase: transaction code P, acquired (not disposed).
_PURCHASE_CODE = "P"
_ACQUIRED_CODE = "A"


# ─────────────────────────────────────────────────────────────────────────────
# Small helpers
# ─────────────────────────────────────────────────────────────────────────────

def _utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _as_date(value: object) -> date | None:
    """The date head of any stamp the artifacts use. None when unparseable."""
    raw = str(value or "").strip()
    if len(raw) < 10:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _ticker(value: object) -> str:
    return str(value or "").strip().upper().lstrip("$")


def _plural(count: int, one: str, many: str) -> str:
    return one if count == 1 else many


def _display_date(when: date, *, today: date) -> tuple[str, str]:
    """("July 30", "7月30日"), with the year attached when it is not this one."""
    month_en = _MONTHS_EN[when.month - 1]
    if when.year == today.year:
        return f"{month_en} {when.day}", f"{when.month}月{when.day}日"
    return (f"{month_en} {when.day}, {when.year}",
            f"{when.year}年{when.month}月{when.day}日")


def _row(kind: str, line_en: str, line_zh: str, as_of: date) -> dict:
    return {
        "kind": kind,
        "line_en": line_en,
        "line_zh": line_zh,
        "as_of": as_of.isoformat(),
    }


def _in_window(when: date | None, *, today: date, fresh_days: int) -> bool:
    """Inside the freshness window, and not from the future.

    A future-dated row is a data fault (a clerk typo, a bad parse), and a fault
    must not become a confident sentence on the desk.
    """
    if when is None:
        return False
    age = (today - when).days
    return 0 <= age <= max(0, fresh_days)


# ─────────────────────────────────────────────────────────────────────────────
# Line builders — PURE (no I/O, no clock beyond the `now` handed in)
# ─────────────────────────────────────────────────────────────────────────────

def congress_line(rows: Iterable[dict], ticker: str, *, now: datetime,
                  fresh_days: int = DEFAULT_FRESH_DAYS) -> dict | None:
    """Congressional disclosures on one ticker inside the freshness window.

    Counts BUY and SELL filings separately from the rows' own ``Transaction``
    values, and stamps the line with the newest ``ReportDate`` it counted — a
    date the artifact itself carries, never our clock.
    """
    today = _utc(now).date()
    want = _ticker(ticker)
    if not want:
        return None
    buys = sells = 0
    newest: date | None = None
    for row in rows or ():
        if not isinstance(row, dict) or _ticker(row.get("Ticker")) != want:
            continue
        reported = _as_date(row.get("ReportDate"))
        if not _in_window(reported, today=today, fresh_days=fresh_days):
            continue
        action = str(row.get("Transaction") or "").strip().lower()
        if action.startswith(_BUY_WORDS):
            buys += 1
        elif action.startswith(_SELL_WORDS):
            sells += 1
        else:
            continue
        if newest is None or (reported is not None and reported > newest):
            newest = reported
    if newest is None or (buys == 0 and sells == 0):
        return None

    window = f"in the past {fresh_days} days"
    window_zh = f"过去 {fresh_days} 天"
    if buys and sells:
        line_en = (f"Congress: {buys} buy and {sells} sell filings "
                   f"on {want} {window}")
        line_zh = f"国会：{window_zh} {want} 有 {buys} 笔买入、{sells} 笔卖出申报"
    elif buys:
        line_en = (f"Congress: {buys} buy "
                   f"{_plural(buys, 'filing', 'filings')} on {want} {window}")
        line_zh = f"国会：{window_zh} {want} 有 {buys} 笔买入申报"
    else:
        line_en = (f"Congress: {sells} sell "
                   f"{_plural(sells, 'filing', 'filings')} on {want} {window}")
        line_zh = f"国会：{window_zh} {want} 有 {sells} 笔卖出申报"
    return _row("congress", line_en, line_zh, newest)


def insider_line(rows: Iterable[dict], ticker: str, *, now: datetime,
                 fresh_days: int = DEFAULT_FRESH_DAYS) -> dict | None:
    """Form-4 OPEN-MARKET purchases on one ticker inside the window.

    Only transaction code P with an acquired flag — the same test
    ``insider_feed._is_purchase`` applies. Grants, option exercises and
    tax-withholding dispositions are not somebody choosing to buy.
    """
    today = _utc(now).date()
    want = _ticker(ticker)
    if not want:
        return None
    buys = 0
    newest: date | None = None
    for row in rows or ():
        if not isinstance(row, dict) or _ticker(row.get("Ticker")) != want:
            continue
        if str(row.get("TransactionCode") or "").strip().upper() != _PURCHASE_CODE:
            continue
        if str(row.get("AcquiredDisposedCode") or "").strip().upper() != _ACQUIRED_CODE:
            continue
        # The FILING date is what the artifact can prove it knew; the
        # transaction date can trail it by days.
        filed = _as_date(row.get("fileDate")) or _as_date(row.get("Date"))
        if not _in_window(filed, today=today, fresh_days=fresh_days):
            continue
        buys += 1
        if newest is None or (filed is not None and filed > newest):
            newest = filed
    if not buys or newest is None:
        return None
    line_en = (f"Insiders: {buys} open-market "
               f"{_plural(buys, 'buy', 'buys')} at {want} "
               f"in the past {fresh_days} days")
    line_zh = f"内部人：过去 {fresh_days} 天 {want} 有 {buys} 笔公开市场买入"
    return _row("insider", line_en, line_zh, newest)


def earnings_line(rows: Iterable[dict], ticker: str, *, now: datetime,
                  fresh_days: int = DEFAULT_FRESH_DAYS) -> dict | None:
    """The next scheduled report for one ticker, from a FRESH calendar row.

    Each calendar row carries its own ``as_of``, and most of them are months
    behind at any given time. The row's own stamp is therefore both the gate and
    the line's as_of: a ticker whose entry was last refreshed in June gets no
    line, even though its ``next_date`` column is populated.
    """
    today = _utc(now).date()
    want = _ticker(ticker)
    if not want:
        return None
    for row in rows or ():
        if not isinstance(row, dict) or _ticker(row.get("ticker")) != want:
            continue
        as_of = _as_date(row.get("as_of"))
        if not _in_window(as_of, today=today, fresh_days=fresh_days):
            continue
        when = _as_date(row.get("next_date"))
        if when is None or when < today:
            # A report already in the past is history, not timing.
            continue
        day_en, day_zh = _display_date(when, today=today)
        slot = _EARNINGS_TIME.get(str(row.get("next_time") or "").strip().lower())
        if slot:
            line_en = f"Earnings: {want} reports {day_en}, {slot[0]}"
            line_zh = f"财报：{want} 将于 {day_zh} 发布财报，{slot[1]}"
        else:
            line_en = f"Earnings: {want} reports {day_en}"
            line_zh = f"财报：{want} 将于 {day_zh} 发布财报"
        return _row("earnings", line_en, line_zh, as_of)
    return None


_LINE_BUILDERS = {
    "congress": congress_line,
    "insider": insider_line,
    "earnings": earnings_line,
}


# ─────────────────────────────────────────────────────────────────────────────
# Loaders — the only I/O, memoised on the artifact's own mtime
# ─────────────────────────────────────────────────────────────────────────────

#: {cache key: (stamp, rows)}. The daemon is a long-lived process polling every
#: 75 s while these artifacts change once a night, so re-reading a 100k-row
#: parquet per tick would be pure waste. The stamp is (mtime_ns, size, window),
#: so a rewritten artifact invalidates itself.
_CACHE: dict[str, tuple[tuple, list[dict]]] = {}


def reset_cache() -> None:
    """Drop the memo. For tests and long-running dry runs."""
    _CACHE.clear()


def _stat_stamp(path: Path, extra: object) -> tuple | None:
    try:
        info = path.stat()
    except OSError:
        return None
    return (info.st_mtime_ns, info.st_size, str(extra))


def _memoised(key: str, path: Path, extra: object, build) -> list[dict]:
    stamp = _stat_stamp(path, extra)
    if stamp is None:
        return []
    hit = _CACHE.get(key)
    if hit is not None and hit[0] == stamp:
        return hit[1]
    try:
        rows = build()
    except Exception as exc:  # noqa: BLE001 — an unreadable artifact is a skip
        log.warning("[intelligence_context] %s unreadable (%s: %s) — skipped",
                    path.name, type(exc).__name__, exc)
        rows = []
    _CACHE[key] = (stamp, rows)
    return rows


def load_congress_rows(root: Path | str | None, *, since: date) -> list[dict]:
    """Congress disclosures reported on/after `since`, as plain dicts.

    Reuses ``congress_feed``'s own loader and its ``records`` cleaner — the one
    place pandas types leave a frame — rather than keeping a second reader that
    could disagree about what ``<NA>`` means.
    """
    path = Path(root or ".") / CONGRESS_REL

    def _build() -> list[dict]:
        from engine.marketing import congress_feed  # noqa: PLC0415
        df = congress_feed.load_congress(root)
        if df is None or not len(df):
            return []
        narrowed = df[df["ReportDate"].astype(str).str[:10] >= since.isoformat()]
        return congress_feed.records(narrowed)

    return _memoised("congress", path, since.isoformat(), _build)


def load_insider_rows(root: Path | str | None, *, since: date) -> list[dict]:
    """Form-4 OPEN-MARKET purchases filed on/after `since`, as plain dicts.

    The purchase mask is applied in pandas: the window alone leaves ~27k rows,
    and materialising those as dicts every tick is the kind of quiet cost a
    75-second daemon cannot afford.
    """
    path = Path(root or ".") / INSIDERS_REL

    def _build() -> list[dict]:
        from engine.marketing import congress_feed, insider_feed  # noqa: PLC0415
        df = insider_feed.load_insiders(root)
        if df is None or not len(df):
            return []
        mask = (
            (df["fileDate"].astype(str).str[:10] >= since.isoformat())
            & (df["TransactionCode"].astype(str).str.upper() == _PURCHASE_CODE)
            & (df["AcquiredDisposedCode"].astype(str).str.upper() == _ACQUIRED_CODE)
        )
        return congress_feed.records(df[mask])

    return _memoised("insider", path, since.isoformat(), _build)


def load_earnings_rows(root: Path | str | None) -> list[dict]:
    """The earnings calendar as ``[{ticker, next_date, next_time, as_of}]``.

    The frame is indexed BY TICKER (no ticker column), which is why this does not
    reuse a feed loader: ``earnings_feed`` is the live poller for earnings
    EVENTS, not a reader of the nightly calendar store.
    """
    path = Path(root or ".") / EARNINGS_REL

    def _build() -> list[dict]:
        import pandas as pd  # noqa: PLC0415
        df = pd.read_parquet(path)
        if not len(df):
            return []
        has_time = "next_time" in df.columns
        has_asof = "as_of" in df.columns
        out: list[dict] = []
        for index, symbol in enumerate(df.index.astype(str)):
            out.append({
                "ticker": str(symbol),
                "next_date": str(df["next_date"].iloc[index]),
                "next_time": str(df["next_time"].iloc[index]) if has_time else "",
                "as_of": str(df["as_of"].iloc[index]) if has_asof else "",
            })
        return out

    return _memoised("earnings", path, "all", _build)


# ─────────────────────────────────────────────────────────────────────────────
# Assembly
# ─────────────────────────────────────────────────────────────────────────────

def context_rows(tickers: Iterable[str], *, root: Path | str | None,
                 now: datetime, fresh_days: int = DEFAULT_FRESH_DAYS,
                 max_lines: int = DEFAULT_MAX_LINES) -> list[dict]:
    """At most `max_lines` engine-fact rows for one story's tickers.

    One line per kind at most, in the fixed order congress / insider / earnings.
    Within a kind the FIRST ticker that yields a line wins, so a two-ticker story
    reads as one clear fact rather than a pile.
    """
    names = [_ticker(t) for t in (tickers or ()) if _ticker(t)]
    if not names or max_lines <= 0:
        return []
    today = _utc(now).date()
    since = today - timedelta(days=max(0, fresh_days))

    out: list[dict] = []
    for kind in KINDS:
        if len(out) >= max_lines:
            break
        try:
            # One read per kind per call; the module memo makes every read after
            # the first packet of a tick a dict lookup.
            if kind == "congress":
                rows = load_congress_rows(root, since=since)
            elif kind == "insider":
                rows = load_insider_rows(root, since=since)
            else:
                rows = load_earnings_rows(root)
        except Exception as exc:  # noqa: BLE001 — a loader fault is a skip
            log.warning("[intelligence_context] %s load failed (%s: %s)",
                        kind, type(exc).__name__, exc)
            continue
        if not rows:
            continue
        builder = _LINE_BUILDERS[kind]
        for name in names:
            try:
                line = builder(rows, name, now=now, fresh_days=fresh_days)
            except Exception as exc:  # noqa: BLE001
                log.warning("[intelligence_context] %s line failed for %s "
                            "(%s: %s)", kind, name, type(exc).__name__, exc)
                line = None
            if line:
                out.append(line)
                break
    return out[:max_lines]


def attach_engine_context(packets: list, cfg: dict | None, *,
                          root: Path | str | None,
                          now: datetime | None = None) -> int:
    """Attach `engine_context` to this tick's desk packets, in place.

    Default OFF in code: deleting `wire.intelligence.engine_context` must disarm
    the join, never silently arm it. Returns the number of packets that gained at
    least one line. Never raises — a context fault must never stop the desk sink.
    """
    rows = [p for p in (packets or []) if isinstance(p, dict)]
    block = cfg if isinstance(cfg, dict) else {}
    if isinstance(block.get("engine_context"), dict):
        block = block["engine_context"]
    if not rows or not bool(block.get("enabled", False)):
        return 0

    def _num(key: str, default: int) -> int:
        try:
            return int(block.get(key, default))
        except (TypeError, ValueError):
            return default

    max_lines = _num("max_lines", DEFAULT_MAX_LINES)
    fresh_days = _num("fresh_days", DEFAULT_FRESH_DAYS)
    stamp = _utc(now) if isinstance(now, datetime) else datetime.now(timezone.utc)

    filled = 0
    for packet in rows:
        try:
            lines = context_rows(
                packet.get("tickers") or [], root=root, now=stamp,
                fresh_days=fresh_days, max_lines=max_lines,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("[intelligence_context] context join skipped (%s: %s)",
                        type(exc).__name__, exc)
            continue
        if lines:
            packet["engine_context"] = lines
            filled += 1
    return filled


__all__ = [
    "CONGRESS_REL",
    "DEFAULT_FRESH_DAYS",
    "DEFAULT_MAX_LINES",
    "EARNINGS_REL",
    "INSIDERS_REL",
    "KINDS",
    "attach_engine_context",
    "congress_line",
    "context_rows",
    "earnings_line",
    "insider_line",
    "load_congress_rows",
    "load_earnings_rows",
    "load_insider_rows",
    "reset_cache",
]
