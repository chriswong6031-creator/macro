"""GACC monthly trade detail — imports/exports BY COUNTRY (Region) (W3 CNH).

海关总署 publishes an English monthly bulletin whose table (2) is the full
partner-country breakdown of China's trade: for every counterparty, the month's
and the year-to-date total / exports / imports plus the YoY percentage change.
That is a different plane from the headline totals china_macro already carries —
it is the only free, keyless source that answers "which partner moved".

CONTEXT / DISPLAY TIER ONLY. Nothing here is scored, ranked, sized or promoted.

FIRST-VINTAGE PIT — read this before trusting a number: GACC REVISES these tables
silently at the SAME URL (a month republished weeks later can carry different
figures with no version marker anywhere on the page). This store therefore dedups
(period, country_en) keep-FIRST: what is on disk is the FIRST vintage we observed,
not the latest official figure. It is honest about when we saw what; it is NOT a
mirror of the current official table, and anyone needing the latest print must
re-fetch. The re-fetch path is deliberately absent from the nightly: a month whose
period is already stored is never re-downloaded.

VERIFIED TRANSPORT (live 2026-07-27, this runner):
  * Index: http://english.customs.gov.cn/statics/report/monthly.html
  * The month links in that index are UNQUOTED attributes
    (``<a href=http://english.customs.gov.cn/Statics/<uuid>.html>``), which is why
    the anchor regex accepts bare hrefs. Some NAV links on the same page are
    malformed (``http:/statics/...``, one slash) — never resolve hrefs naively.
  * The by-country row's title uses FULL-WIDTH parentheses:
    '（2）Imports and Exports by Country （Region） of Origin/Destination'.
  * Older years live at .../monthly<YEAR>.html; the CURRENT year is the plain
    monthly.html. The mapping is read off the page's own year-select JavaScript
    rather than guessed.
  * Publication lag is ~2–3 weeks (June 2026 landed mid-July 2026).
  * Cells that overflow Excel's column width are published literally as
    ``############``. They are DATA LOSS, not zero: they parse to NaN and are
    counted in the sentinel's n_nulls, never dropped and never zero-filled.

Politeness + budget: ≥1.1 s before every request to the single host, a monthly
cadence (a full current-year seed is ~6 fetches ≈ 15 s) and a ~100 s wall-clock
guard. A 0-row night is a success — most nights have no new month at all.
"""
from __future__ import annotations

import argparse
import logging
import math
import os
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger("china_trade_detail")

# ------------------------------------------------------------------ constants --

GROUP = "china_trade_detail"
INDEX_URL = "http://english.customs.gov.cn/statics/report/monthly.html"
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_PACE_S = 1.1
_JITTER_S = 0.3
_TIMEOUT = (10, 30)     # table (2) is ~230 KB
_BUDGET_S = 100.0
_MONTH_CAP = 12         # a whole year in one night is the largest legitimate pull

# The bulletin's own table-of-contents label for the by-country breakdown. Matched
# on the ASCII-safe fragments only: the live title carries FULL-WIDTH parentheses
# around （2） and （Region）, and a naive '(2)' match finds nothing.
_BY_COUNTRY_TOKENS = ("by Country", "Origin/Destination")

_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
           "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}

# Rows that are SUMS of other rows in the same table. The six continents print with
# a trailing colon ('Asia:'); the five named blocs do not, but the table's own Notes
# row enumerates them as compositions of member countries, so a consumer summing the
# non-aggregate rows would double-count them without this flag.
_BLOC_ROWS = frozenset({"TOTAL", "ASEAN", "EU", "APEC", "RCEP", "BRI"})

_COLUMNS: tuple[str, ...] = (
    "period",              # 'YYYY-MM' — the bulletin's own month
    "country_en",          # partner name as GACC prints it (the dedup key half)
    "is_aggregate",        # continent / bloc / TOTAL row — never sum these with the rest
    "total_month_kusd",    # every value column is thousands of USD (Unit:US$1,000)
    "total_cum_kusd",
    "exports_month_kusd",
    "exports_cum_kusd",
    "imports_month_kusd",
    "imports_cum_kusd",
    "pct_total",           # YoY % change, cumulative basis; negatives are real
    "pct_exports",
    "pct_imports",
    "source_url",
    "backfill",            # True only for rows written by the manual backfill() CLI
    "first_seen",          # FIRST observation — the first-vintage stamp
    "fetched_at",
)

_KEY = ["period", "country_en"]
_VALUE_FIELDS = ("total_month_kusd", "total_cum_kusd", "exports_month_kusd",
                 "exports_cum_kusd", "imports_month_kusd", "imports_cum_kusd",
                 "pct_total", "pct_exports", "pct_imports")

_SENTINEL_COLUMNS = ("n_new", "n_fetched", "n_failed", "n_nulls", "periods_seen")


# ------------------------------------------------------------------ paths / stores --

def _dir() -> Path:
    p = config.data_dir() / GROUP
    p.mkdir(parents=True, exist_ok=True)
    return p


def _store_path() -> Path:
    return _dir() / "by_country.parquet"


def _read_store(path: Path, columns: tuple[str, ...]) -> pd.DataFrame | None:
    """The store reindexed to ``columns``, an EMPTY frame when ABSENT, None when UNREADABLE.

    "absent" is the first night (append freely); "present but unreadable" means the
    accrued history is still on disk and we simply cannot see it — taking the
    empty-store branch there would replace all of it with tonight's rows. The caller
    ABORTS on None.
    """
    if not path.exists():
        return pd.DataFrame(columns=list(columns))
    try:
        return pd.read_parquet(path).reindex(columns=list(columns))
    except Exception as e:  # noqa: BLE001
        log.error("china_trade_detail: %s is present but UNREADABLE (%s)", path.name, e)
        return None


def _atomic_write(df: pd.DataFrame, path: Path) -> None:
    """Write ``df`` via a tmp sibling + os.replace — never a truncated store."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, path)
    except Exception:  # noqa: BLE001 — never leave a half-written sibling behind
        tmp.unlink(missing_ok=True)
        raise


def load_by_country() -> pd.DataFrame:
    """Existing by_country.parquet, or an empty frame with the canonical schema.

    A present-but-unreadable store also reads as empty HERE — a reader must not crash
    — but write_rows() checks readability separately and aborts, so the empty frame
    can never be written back over the real one.
    """
    df = _read_store(_store_path(), _COLUMNS)
    return pd.DataFrame(columns=list(_COLUMNS)) if df is None else df


def stored_periods() -> set[str]:
    """Periods already on disk — the diff set that decides which months to fetch."""
    df = load_by_country()
    if df.empty or "period" not in df.columns:
        return set()
    return {p for p in df["period"].astype(str) if p and p != "nan"}


def write_rows(rows: list[dict]) -> int:
    """Append by-country rows, dedup (period, country_en) keep-FIRST. Never raises.

    keep-FIRST is the whole point of the store (see the module docstring): GACC
    revises a published month silently at the same URL, so the first vintage we
    observed must survive any later re-parse. first_seen therefore never moves and
    fetched_at is simply the stamp of the run that first wrote the row.

    An existing-but-UNREADABLE store ABORTS the append (returns 0, file left in place
    for manual recovery) rather than being replaced by tonight's month.
    """
    if not rows:
        return 0
    try:
        existing = _read_store(_store_path(), _COLUMNS)
        if existing is None:
            log.error("china_trade_detail: ABORTING the by_country.parquet append — the "
                      "accrued store is unreadable and is left untouched for manual recovery")
            return 0
        new_df = pd.DataFrame(rows).reindex(columns=list(_COLUMNS))
        new_df["first_seen"] = new_df["first_seen"].fillna(new_df["fetched_at"])
        for c in _KEY:
            new_df[c] = new_df[c].fillna("").astype(str)
        if existing.empty:
            merged = new_df.drop_duplicates(subset=_KEY, keep="first")
            net_new = len(merged)
        else:
            for c in _KEY:
                existing[c] = existing[c].fillna("").astype(str)
            pre = len(existing.drop_duplicates(subset=_KEY))
            merged = pd.concat([existing, new_df], ignore_index=True)
            merged = merged.drop_duplicates(subset=_KEY, keep="first")
            net_new = len(merged) - pre
        merged = merged.sort_values(_KEY).reset_index(drop=True)
        _atomic_write(merged, _store_path())
        return int(net_new)
    except Exception as e:  # noqa: BLE001
        log.error("china_trade_detail.write_rows failed: %s", e)
        return 0


# ------------------------------------------------------------------ text helpers --

_SCRIPT_STYLE_RE = re.compile(r"(?is)<(script|style)[^>]*>.*?</\1>")
_TAG_RE = re.compile(r"(?s)<[^>]+>")
_WS_RE = re.compile(r"\s+")
_ENTITIES = (("&nbsp;", " "), ("&#160;", " "), ("&amp;", "&"), ("&lt;", "<"),
             ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'"))
# GACC numbers arrive as '699,151,163&nbsp;' — the entity is INSIDE the cell, so it
# must be unescaped before the number is read, not after.
OVERFLOW = "############"


def _cell(html_text: str) -> str:
    """One <td>'s inner HTML → plain collapsed text. PURE."""
    s = _TAG_RE.sub(" ", html_text or "")
    for a, b in _ENTITIES:
        s = s.replace(a, b)
    return _WS_RE.sub(" ", s).replace("\xa0", " ").strip()


def _plain(html_text: str) -> str:
    """Whole-fragment tag strip → collapsed text. PURE."""
    return _cell(_SCRIPT_STYLE_RE.sub(" ", html_text or ""))


def parse_value(text: str) -> float:
    """A GACC numeric cell → float, NaN when the cell carries no number. PURE.

    Two non-numeric states occur live and BOTH become NaN rather than 0:
      ``############``  Excel column-overflow: the real figure exists but the page
                        does not show it. A 0 here would silently delete the
                        largest cumulative totals in the table.
      ``-``             GACC's nil marker. Whether it means "zero" or "not
                        reported" is not stated anywhere in the bulletin, so it is
                        recorded as unknown; a fabricated 0 would be a claim the
                        source never made.
    Both are counted in the sentinel's n_nulls by count_nulls().
    """
    s = (text or "").replace(",", "").replace("\xa0", " ").strip()
    if not s or s == "-" or OVERFLOW in s:
        return float("nan")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return float("nan")
    try:
        return float(m.group(0))
    except ValueError:
        return float("nan")


# ------------------------------------------------------------------ index page --

# Bare hrefs are the live shape on this index (`<a href=http://…/Statics/<uuid>.html>`),
# so the quote group is optional and the backreference is empty in that case.
_ANCHOR_RE = re.compile(r"""(?is)<a\s[^>]*?href=(["']?)([^"'\s>]+)\1[^>]*>(.*?)</a>""")
_STATICS_RE = re.compile(r"(?i)^https?://[^/]*customs\.gov\.cn/Statics/[A-Za-z0-9\-]+\.html$")
_YEAR_JS_RE = re.compile(
    r"""(?is)val\(\)\s*==\s*["'](\d{4})["']\s*\)\s*\{\s*location\.replace\(\s*["']([^"']+)["']""")


def parse_year_map(html_text: str) -> dict[str, str]:
    """{'2026': '…/monthly.html', '2025': '…/monthly2025.html', …}. PURE.

    Read off the index page's OWN year-select JavaScript rather than reconstructed
    from a guessed pattern: the current year is served from the un-suffixed
    monthly.html while every past year gets a monthly<YEAR>.html, and that asymmetry
    is exactly the kind of thing a hand-rolled f-string gets wrong the January the
    site rolls over.
    """
    return {m.group(1): m.group(2) for m in _YEAR_JS_RE.finditer(html_text or "")}


def current_year(html_text: str) -> str:
    """The year the plain monthly.html is serving, or ''. PURE.

    Derived from the year map (the year whose target has no <YEAR> suffix) so the
    period stamped on a scraped month is the SITE's notion of the current year, never
    this machine's clock.
    """
    for year, url in parse_year_map(html_text).items():
        if re.search(r"/monthly\.html$", url or ""):
            return year
    return ""


def parse_month_index(html_text: str, base_url: str = INDEX_URL,
                      year: str = "") -> list[dict]:
    """The by-country row's month links as [{period, month, label, url}]. PURE.

    Only the ONE table row whose label carries both 'by Country' and
    'Origin/Destination' is read — the bulletin ships 19 table types on the same page
    and every one of them has its own Jan..Dec link set.
    """
    year = year or current_year(html_text) or ""
    out: list[dict] = []
    for tr in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", html_text or ""):
        label = _plain(tr)
        if not all(tok in label for tok in _BY_COUNTRY_TOKENS):
            continue
        for m in _ANCHOR_RE.finditer(tr):
            url = urljoin(base_url, m.group(2))
            if not _STATICS_RE.match(url):
                continue
            text = _plain(m.group(3)).strip().strip(".").lower()[:3]
            month = _MONTHS.get(text)
            if not month:
                continue
            out.append({"period": f"{year}-{month:02d}" if year else "",
                        "month": month,
                        "label": _plain(m.group(3)).strip(),
                        "url": url})
        break
    return out


# ------------------------------------------------------------------ table (2) --

_TITLE_PERIOD_RE = re.compile(r",\s*(\d{1,2})\.(\d{4})")


def parse_period(html_text: str) -> str:
    """'…Origin/Destination,6.2026' → '2026-06'; '' when absent. PURE.

    The month lives ONLY in the page title — the table body never repeats it — so a
    title the site reformats becomes an empty period, which the caller treats as an
    unusable page rather than filing rows under a guessed month.
    """
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html_text or "")
    if not m:
        return ""
    p = _TITLE_PERIOD_RE.search(_plain(m.group(1)))
    return f"{p.group(2)}-{int(p.group(1)):02d}" if p else ""


def parse_by_country(html_text: str, source_url: str = "",
                     fetched_at: str = "", backfill: bool = False) -> dict:
    """Table (2) → {period, rows, n_nulls, n_empty_key}. PURE, never raises.

    A data row is a <tr> with exactly 10 cells (country + 6 value columns + 3 percent
    columns); the title/unit/two header rows and the trailing Notes row have other
    widths and drop out on that test alone. A row whose country cell is EMPTY is
    DROPPED and counted, never stored: country_en is half the dedup key, so a keyless
    row would collapse the whole month into one row (W1 F7).
    """
    try:
        period = parse_period(html_text)
        rows: list[dict] = []
        n_empty_key = 0
        n_overflow = 0
        for tr in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", html_text or ""):
            cells = [_cell(td) for td in re.findall(r"(?is)<td[^>]*>(.*?)</td>", tr)]
            if len(cells) != 10:
                continue
            name = cells[0].strip()
            if not name:
                n_empty_key += 1
                continue
            n_overflow += sum(1 for c in cells[1:] if OVERFLOW in c)
            values = [parse_value(c) for c in cells[1:]]
            rows.append({
                "period": period,
                "country_en": name,
                "is_aggregate": bool(name.endswith(":") or name in _BLOC_ROWS),
                "total_month_kusd": values[0],
                "total_cum_kusd": values[1],
                "exports_month_kusd": values[2],
                "exports_cum_kusd": values[3],
                "imports_month_kusd": values[4],
                "imports_cum_kusd": values[5],
                "pct_total": values[6],
                "pct_exports": values[7],
                "pct_imports": values[8],
                "source_url": source_url,
                "backfill": bool(backfill),
                "first_seen": fetched_at,
                "fetched_at": fetched_at,
            })
        return {"period": period, "rows": rows,
                "n_nulls": count_nulls(rows), "n_empty_key": n_empty_key,
                # Split out from n_nulls on purpose: an overflowed cell means the
                # figure EXISTS and the page hid it (recoverable by re-fetching a
                # later republication), while a '-' is the source's own nil marker.
                # Same NaN, different follow-up.
                "n_overflow": n_overflow}
    except Exception as e:  # noqa: BLE001 — an unexpected page shape is a counted null
        log.warning("china_trade_detail: table parse failed (%s)", e)
        return {"period": "", "rows": [], "n_nulls": 0, "n_empty_key": 0,
                "n_overflow": 0}


def count_nulls(rows: list[dict]) -> int:
    """Value cells the bulletin did not give us a number for (############ or '-').

    Coverage nulls, printed by the sentinel rather than hidden: without this, a month
    published with half its cumulative column overflowed reads exactly like a month
    that was fully legible. PURE.
    """
    n = 0
    for r in rows:
        for f in _VALUE_FIELDS:
            v = r.get(f)
            if v is None or (isinstance(v, float) and math.isnan(v)):
                n += 1
    return n


# ------------------------------------------------------------------ HTTP --

def _headers() -> dict:
    return {"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"}


def _pace() -> None:
    """Politeness sleep before EVERY request: ≥1.1 s to the single upstream host."""
    time.sleep(_PACE_S + random.uniform(0.0, _JITTER_S))  # noqa: S311


def _clock() -> float:
    """Monotonic seconds. Indirected so the wall-clock guard is unit-testable."""
    return time.monotonic()


def _get(session, url: str) -> str:
    """Paced GET → decoded HTML. Raises on transport/HTTP failure."""
    _pace()
    r = session.get(url, headers=_headers(), timeout=_TIMEOUT)
    if r.status_code in (429, 500, 502, 503, 504):
        raise IOError(f"HTTP {r.status_code} from english.customs.gov.cn")
    r.raise_for_status()
    # Decoded straight from bytes rather than via r.text: the bulletin pages declare
    # UTF-8 in a <meta> tag but not in Content-Type, and requests then falls back to
    # ISO-8859-1 — which mangles the full-width （Region） the row matcher keys on.
    return r.content.decode("utf-8", errors="replace")


# ------------------------------------------------------------------ nightly refresh --

def _pull(session, months: list[dict], fetched_at: str, t0: float,
          backfill_flag: bool = False) -> tuple[list[dict], int, int, int, set[str]]:
    """Fetch + parse a list of month links. Returns (rows, n_fetched, n_failed, n_nulls, periods).

    Per-month try/except isolation: one unreachable month never sinks the rest, and a
    page whose title carries no period is skipped rather than filed under a guess.
    """
    rows: list[dict] = []
    n_fetched = n_failed = n_nulls = 0
    periods: set[str] = set()
    if len(months) > _MONTH_CAP:
        # A calendar year cannot exceed 12 months, so this only fires when the index
        # shape changed under us. LOUD rather than silent (W1 F3): a cap that trims
        # without saying so is how a plane quietly shrinks a month at a time.
        log.warning("china_trade_detail: %d month links offered but the cap is %d — "
                    "%d NOT fetched; the index shape has changed, check the "
                    "'（2）… by Country' row", len(months), _MONTH_CAP,
                    len(months) - _MONTH_CAP)
    for i, link in enumerate(months[:_MONTH_CAP]):
        if _clock() - t0 > _BUDGET_S:
            log.warning("china_trade_detail: %.0fs wall-clock guard hit after %d/%d "
                        "months — the remainder is picked up next run",
                        _BUDGET_S, i, len(months))
            break
        try:
            html_text = _get(session, link["url"])
        except Exception as e:  # noqa: BLE001 — per-month isolation
            n_failed += 1
            log.warning("china_trade_detail: %s failed: %s", link["url"], e)
            continue
        n_fetched += 1
        parsed = parse_by_country(html_text, link["url"], fetched_at, backfill_flag)
        period = parsed["period"] or link.get("period") or ""
        if not period or not parsed["rows"]:
            n_failed += 1
            log.warning("china_trade_detail: %s parsed to no usable rows (period=%r) — "
                        "counted, not stored", link["url"], period)
            continue
        # The page's OWN title wins over the index's month position: the index has
        # been observed pointing a month slot at a re-published neighbour.
        for r in parsed["rows"]:
            r["period"] = period
        rows.extend(parsed["rows"])
        n_nulls += parsed["n_nulls"] + parsed["n_empty_key"]
        periods.add(period)
        log.info("china_trade_detail: %s → %d rows (%d nulls)",
                 period, len(parsed["rows"]), parsed["n_nulls"])
    return rows, n_fetched, n_failed, n_nulls, periods


def refresh() -> dict:
    """Fetch the monthly index, download only months NOT already stored, append.

    The whole current year is legitimate on a first night (~6 pages, ~15 s); after
    that a normal night finds nothing new at all, which is a success (n_new=0), not a
    failure. Raises RuntimeError only when the INDEX itself failed at transport level.
    """
    import requests  # lazy — keeps import-time cost off the collect registry

    t0 = _clock()
    fetched_at = datetime.now(timezone.utc).isoformat()
    session = requests.Session()

    try:
        index_html = _get(session, INDEX_URL)
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"china_trade_detail: monthly index unreachable ({e})") from e

    months = parse_month_index(index_html, INDEX_URL)
    if not months:
        log.warning("china_trade_detail: the index carried NO by-country month links — "
                    "0-row night (check the '（2）… by Country' row label)")
        return {"n_new": 0, "n_fetched": 0, "n_failed": 1, "n_nulls": 0, "periods_seen": 0}

    known = stored_periods()
    pending = [m for m in months if m["period"] and m["period"] not in known]
    log.info("china_trade_detail: index lists %d month(s), %d not yet stored",
             len(months), len(pending))
    if not pending:
        return {"n_new": 0, "n_fetched": 0, "n_failed": 0, "n_nulls": 0,
                "periods_seen": 0}

    rows, n_fetched, n_failed, n_nulls, periods = _pull(session, pending, fetched_at, t0)
    n_new = write_rows(rows)
    log.info("china_trade_detail: fetched=%d failed=%d rows=%d net_new=%d periods=%s",
             n_fetched, n_failed, len(rows), n_new, sorted(periods))
    return {"n_new": n_new, "n_fetched": n_fetched, "n_failed": n_failed,
            "n_nulls": n_nulls, "periods_seen": len(periods)}


def backfill(years: list[str] | tuple[str, ...]) -> int:
    """MANUAL year backfill — NEVER called from fetch()/the adapter path.

    Older years live behind their own index (…/monthly<YEAR>.html), resolved from the
    CURRENT index's year-select map so the URL shape is never guessed. Rows are
    stamped backfill=True so the PIT tape can separate "observed near publication"
    from "recovered later", and the keep-FIRST dedup means a backfilled row can never
    overwrite one already on disk.
    """
    import requests  # lazy

    session = requests.Session()
    fetched_at = datetime.now(timezone.utc).isoformat()
    index_html = _get(session, INDEX_URL)
    year_map = parse_year_map(index_html)
    known = stored_periods()
    total = 0
    for year in years:
        url = year_map.get(str(year))
        if not url:
            log.warning("china_trade_detail backfill: no index for %s (have %s)",
                        year, sorted(year_map))
            continue
        try:
            page = _get(session, url)
        except Exception as e:  # noqa: BLE001
            log.warning("china_trade_detail backfill: %s index failed: %s", year, e)
            continue
        months = [m for m in parse_month_index(page, url, year=str(year))
                  if m["period"] and m["period"] not in known]
        rows, n_fetched, n_failed, _, periods = _pull(
            session, months, fetched_at, _clock(), backfill_flag=True)
        n = write_rows(rows)
        total += n
        log.info("china_trade_detail backfill %s: fetched=%d failed=%d rows=%d net_new=%d",
                 year, n_fetched, n_failed, len(rows), n)
    return total


# ------------------------------------------------------------------ adapter --

class ChinaTradeDetailAdapter(Adapter):
    """GACC by-country monthly trade detail (W3 CNH) — context/display tier, never scored.

    Wraps refresh() in the standard run_adapter / circuit-breaker machinery. Group
    ``china_trade_detail`` starts with ``china`` so it is auto-assigned to the asia
    lane (scripts/collect.py group_members). It stays OUT of ``_CONCURRENT_HOSTS``:
    the plane is monthly, so there is nothing to parallelise, and the serial phase is
    the cheapest place for a 6-page-a-month collector.

    fetch() returns a COVERAGE sentinel rather than a bare count, so
    data/china_trade_detail/refresh.parquet is a readable run ledger: n_new/n_fetched
    say what landed, n_failed what broke, n_nulls how many value cells the bulletin
    itself did not give us a number for (the ############ overflow artifact and GACC's
    '-' marker), and periods_seen how many months were written. What the sentinel does
    NOT prove is that a stored month matches the CURRENT official table — the store is
    first-vintage by design (see the module docstring).
    """

    name = "china_trade_detail"
    group = GROUP
    stale_after_days = 45   # monthly cadence + a ~2–3 week publication lag

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        s = refresh()
        # tz-NAIVE normalized UTC day (collectors/china_filings.py precedent).
        idx = pd.Timestamp.now("UTC").normalize().tz_localize(None)
        sentinel = pd.DataFrame({k: [float(s[k])] for k in _SENTINEL_COLUMNS}, index=[idx])
        sentinel.index.name = "collected_at"
        return {"refresh": sentinel}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--backfill", nargs="+", metavar="YEAR",
                    help="MANUAL year backfill (never nightly), e.g. --backfill 2024 2025")
    a = ap.parse_args()
    if a.backfill:
        print(f"china_trade_detail backfill: {backfill(a.backfill)} net-new rows")
        return 0
    s = refresh()
    print(f"china_trade_detail: {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
