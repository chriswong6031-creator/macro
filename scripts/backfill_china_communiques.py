"""Curated historical communiqué backfill — W1.1 of CHINA_INTEL_CYCLES_MASTERPLAN.

Three families:
  pboc_mpc    — PBoC Monetary Policy Committee quarterly readouts (2009→, ~69 docs)
  politburo_econ — Politburo economic-analysis meeting readouts (2016→, ~35-40 docs)
  cewc        — Central Economic Work Conference annual readouts (2016→, ~10 docs)

Output: data/china_official/communiques.parquet (keep-FIRST on doc_id)

Schema
------
  doc_id         : str   sha256(url + "|" + title)
  family         : str   pboc_mpc | politburo_econ | cewc
  meeting_year   : int
  meeting_quarter: int | null   (Q1–Q4; null for politburo_econ/cewc)
  meeting_date   : str | null   ISO-8601 date (YYYY-MM-DD) when extractable
  publish_date   : str | null   ISO-8601 date when extractable
  title          : str
  body           : str
  body_sha256    : str
  url            : str
  source         : str
  _fetched_at    : str   ISO-8601 UTC

Usage
-----
  # Full backfill (all families):
  python scripts/backfill_china_communiques.py

  # Single family:
  python scripts/backfill_china_communiques.py --family pboc_mpc

  # Limit per family (useful for testing):
  python scripts/backfill_china_communiques.py --limit 3

  # Dry-run (print discovered URLs, no fetch):
  python scripts/backfill_china_communiques.py --dry-run

  # Force re-fetch even if doc already exists:
  python scripts/backfill_china_communiques.py --force

Pacing
------
  pbc.gov.cn requests: >=1.5s + jitter (configurable via PACE_MIN / PACE_JITTER).
  CCTV/akshare requests: >=1.0s + jitter between days.

NOT registered in nightly collect — manual/Mac lane only (RUL-9).
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import random
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = REPO_ROOT / "data" / "china_official" / "communiques.parquet"

# ---------------------------------------------------------------------------
# Browser UA (gov.cn / pbc.gov.cn are UA-sensitive — same as china_official_corpora.py)
# ---------------------------------------------------------------------------
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_HEADERS = {"User-Agent": _BROWSER_UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}

# ---------------------------------------------------------------------------
# Pacing
# ---------------------------------------------------------------------------
PACE_MIN = 1.5
PACE_JITTER = 1.0    # uniform[0, PACE_JITTER] added to PACE_MIN

# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------
_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
_YEAR_RE = re.compile(r"(\d{4})年")
_QUARTER_RE = re.compile(r"第([一二三四])季度")
_QUARTER_MAP = {"一": 1, "二": 2, "三": 3, "四": 4}

# PBoC EasyPortal CMS pagination href pattern:
# Recent era:  /zhengcehuobisi/125207/3870933/3870936/<uuid>/index.html
# Older era:   /goutongjiaoliu/113456/113469/<19-digit-id>/index.html
_PBOC_HREF_RE = re.compile(
    r'/(?:zhengcehuobisi/125207/3870933/3870936/[0-9a-f]+|goutongjiaoliu/113456/113469/\d+)/index\.html'
)

# Charset detection (same pattern as china_official_corpora.py)
_META_CHARSET_RE = re.compile(rb"""<meta[^>]+charset=["']?\s*([a-zA-Z0-9_\-]+)""", re.I)

log = logging.getLogger("backfill_communiques")

SCHEMA_COLS = [
    "doc_id", "family", "meeting_year", "meeting_quarter",
    "meeting_date", "publish_date", "title", "body", "body_sha256",
    "url", "source", "_fetched_at",
]


# ---------------------------------------------------------------------------
# Encoding helpers
# ---------------------------------------------------------------------------

def _decode_html(content: bytes, content_type: str = "") -> str:
    """Decode HTML bytes honouring real charset (gb2312/gbk → gb18030)."""
    enc = None
    m = re.search(r"charset=([\w\-]+)", content_type or "", re.I)
    if m:
        enc = m.group(1)
    if not enc:
        mm = _META_CHARSET_RE.search(content[:4096])
        if mm:
            enc = mm.group(1).decode("ascii", "ignore")
    enc = (enc or "utf-8").strip().lower()
    if enc in {"gb2312", "gbk", "gb-2312"}:
        enc = "gb18030"
    try:
        return content.decode(enc, errors="replace")
    except (LookupError, TypeError):
        return content.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Date / quarter extraction helpers
# ---------------------------------------------------------------------------

def extract_meeting_date(text: str) -> str | None:
    """Extract first 中文 date (e.g. 2009年3月15日) as ISO string."""
    m = _DATE_RE.search(text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            return None
    return None


def extract_meeting_year(text: str) -> int | None:
    """Extract meeting year from title or body."""
    m = _YEAR_RE.search(text)
    return int(m.group(1)) if m else None


def extract_quarter(text: str) -> int | None:
    """Extract quarter (1–4) from title or body."""
    m = _QUARTER_RE.search(text)
    return _QUARTER_MAP.get(m.group(1)) if m else None


def make_doc_id(url: str, title: str) -> str:
    """sha256(url|title) — deterministic document identity."""
    raw = f"{url}|{title}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Parquet I/O (keep-FIRST on doc_id)
# ---------------------------------------------------------------------------

def load_existing(path: Path) -> pd.DataFrame:
    if path.exists():
        return pd.read_parquet(path)
    return pd.DataFrame(columns=SCHEMA_COLS)


def save_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, compression="zstd", index=False)


def existing_doc_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    df = pd.read_parquet(path, columns=["doc_id"])
    return set(df["doc_id"].tolist())


def upsert_rows(existing_df: pd.DataFrame, new_rows: list[dict]) -> pd.DataFrame:
    """Add new_rows; keep-FIRST (existing rows win on doc_id collision)."""
    if not new_rows:
        return existing_df
    new_df = pd.DataFrame(new_rows, columns=SCHEMA_COLS)
    combined = pd.concat([existing_df, new_df], ignore_index=True)
    combined = combined.drop_duplicates(subset=["doc_id"], keep="first")
    combined = combined.sort_values(["family", "meeting_year", "meeting_quarter"],
                                    na_position="last").reset_index(drop=True)
    return combined


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _get(session: Any, url: str, *, pace: bool = True) -> tuple[bytes, str]:
    """GET url → (content_bytes, content_type). Paces if pace=True."""
    if pace:
        wait = PACE_MIN + random.uniform(0, PACE_JITTER)
        time.sleep(wait)
    resp = session.get(url, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.content, resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# FAMILY 1: PBoC MPC quarterly readouts
# ---------------------------------------------------------------------------

PBOC_INDEX_URL = (
    "https://www.pbc.gov.cn/zhengcehuobisi/125207/3870933/3870936/index.html"
)
PBOC_BASE = "https://www.pbc.gov.cn"
PBOC_SOURCE = "pbc.gov.cn"

# EasyPortal pagination: page N is a sibling file named <hash>-N.html.
# The hash 'af7dde41' is the known live value but is not guaranteed stable across
# CMS redeploys.  We match ANY 8-hex-char prefix so a changed hash is discovered
# rather than silently yielding zero pages.
_PBOC_PAGE_HREF_RE = re.compile(r'([0-9a-f]{8})-(\d+)\.html')

# Strict YYYY-MM-DD validation for CMS publish-date spans
_HUI12_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _pboc_page_urls(html: str, base_url: str) -> list[str]:
    """Parse the EasyPortal page-footer links for <hash>-N.html pattern and
    synthesise the FULL page range, filling any gaps.

    The PBoC listing page's footer only links to some page numbers (e.g. -2 and
    -4 are present but -3 is absent).  This function:
      (a) Collects all (prefix, N) pairs from every <hash>-N.html href found;
      (b) For each distinct prefix, generates ALL pages from 2 up to the highest
          N discovered, filling gaps;
      (c) Also iterates over every listing page already fetched and extends the
          range if a later page reveals a higher N (handled at call-site via
          repeated calls — see fetch_pboc_mpc).

    Matches any 8-hex-char prefix, not the hardcoded 'af7dde41', so a CMS
    redeploy that changes the hash is detected rather than silently returning
    zero pages and truncating the backfill to page 1 only.

    Returns deduplicated sibling URLs for pages 2..maxN in ascending order.
    Page 1 (index.html) is always handled separately by the caller.
    """
    dir_url = base_url.rsplit("/", 1)[0]

    # Collect max N per prefix
    prefix_max: dict[str, int] = {}
    for m in _PBOC_PAGE_HREF_RE.finditer(html):
        prefix, n_str = m.group(1), m.group(2)
        n = int(n_str)
        if n >= 2:  # page 1 = index.html (handled by caller)
            prefix_max[prefix] = max(prefix_max.get(prefix, 2), n)

    pages: list[str] = []
    for prefix, max_n in sorted(prefix_max.items()):
        for k in range(2, max_n + 1):
            url = f"{dir_url}/{prefix}-{k}.html"
            if url not in pages:
                pages.append(url)

    return pages


def _parse_listing_entries(html: str) -> list[tuple[str, str | None]]:
    """Parse a PBoC listing page and return [(href, publish_date_or_None)].

    For each anchor whose href matches _PBOC_HREF_RE, capture the adjacent
    ``<span class="hui12">YYYY-MM-DD</span>`` immediately following the anchor
    in the same <td>.  The date is validated strictly as YYYY-MM-DD; if absent
    or malformed, publish_date_or_None is None.

    Uses BeautifulSoup (already imported in _pboc_fetch_article).
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    results: list[tuple[str, str | None]] = []
    seen_hrefs: set[str] = set()

    for a in soup.find_all("a", href=_PBOC_HREF_RE):
        href = a["href"]
        if href in seen_hrefs:
            continue
        seen_hrefs.add(href)

        # Look for the hui12 span in the same parent td (or immediate parent)
        publish_date: str | None = None
        parent = a.parent  # typically <td> or <font> inside <td>
        # Walk up at most 2 levels to find a td
        for _ in range(3):
            if parent is None:
                break
            span = parent.find("span", class_="hui12")
            if span:
                raw = span.get_text(strip=True)
                if _HUI12_DATE_RE.match(raw):
                    # Additional validation: parse as a real date
                    try:
                        year, month, day = raw.split("-")
                        date(int(year), int(month), int(day))  # raises ValueError on bad date
                        publish_date = raw
                    except ValueError:
                        publish_date = None
                break
            parent = parent.parent

        results.append((href, publish_date))

    return results


def _pboc_article_hrefs(html: str) -> list[str]:
    """Extract article hrefs matching _PBOC_HREF_RE from a listing page."""
    return list(dict.fromkeys(_PBOC_HREF_RE.findall(html)))


def _pboc_fetch_article(
    session: Any,
    href: str,
    listing_publish_date: str | None = None,
) -> dict | None:
    """Fetch a PBoC MPC article and return a row dict or None on failure.

    listing_publish_date: YYYY-MM-DD string captured from the listing page's
    ``<span class="hui12">`` adjacent to the article link.  When present this
    is used as publish_date (more reliable than body-text extraction).
    meeting_date logic is unchanged — it is always derived from body text.
    """
    url = urljoin(PBOC_BASE, href)
    try:
        content, ct = _get(session, url)
    except Exception as exc:
        log.warning("PBOC fetch failed %s: %s", url, exc)
        return None
    html = _decode_html(content, ct)
    # Extract title from <title> tag or <h1>
    title_m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
    h1_m = re.search(r"<h1[^>]*>([^<]+)</h1>", html, re.I)
    title = ""
    if title_m:
        title = title_m.group(1).strip()
    elif h1_m:
        title = h1_m.group(1).strip()
    # Clean title of site suffix
    title = re.sub(r"[-_|].*$", "", title).strip() if title else ""

    # Extract body text from div.zoom1 p elements
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    zoom = soup.find("div", class_="zoom1") or soup.find("div", class_="zoom")
    if zoom:
        paras = [p.get_text(separator=" ", strip=True) for p in zoom.find_all("p") if p.get_text(strip=True)]
    else:
        # Fallback: main content divs
        paras = [p.get_text(separator=" ", strip=True) for p in soup.find_all("p") if p.get_text(strip=True)]
        paras = paras[:10]  # Limit fallback to avoid nav text

    body = "\n".join(paras).strip()
    if not body:
        log.warning("PBOC empty body at %s", url)
        return None

    meeting_date = extract_meeting_date(title + " " + body)
    meeting_year = extract_meeting_year(title + " " + body) or (
        int(re.search(r"(\d{4})", url).group(1)) if re.search(r"(\d{4})", url) else None
    )
    meeting_quarter = extract_quarter(title + " " + body)

    # If still no year, try from href path
    if meeting_year is None:
        yr_m = re.search(r"/(20\d{2})/", href)
        if yr_m:
            meeting_year = int(yr_m.group(1))

    if not title:
        title = f"PBoC MPC Meeting {meeting_year} Q{meeting_quarter}"

    doc_id = make_doc_id(url, title)
    body_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # publish_date: use listing CMS stamp if available (most reliable); fall back
    # to body-extracted meeting_date as a rough approximation.
    publish_date = listing_publish_date if listing_publish_date is not None else meeting_date

    return {
        "doc_id": doc_id,
        "family": "pboc_mpc",
        "meeting_year": meeting_year,
        "meeting_quarter": meeting_quarter,
        "meeting_date": meeting_date,
        "publish_date": publish_date,
        "title": title,
        "body": body,
        "body_sha256": body_sha256,
        "url": url,
        "source": PBOC_SOURCE,
        "_fetched_at": fetched_at,
    }


def fetch_pboc_mpc(session: Any, known_ids: set[str],
                   limit: int | None = None, dry_run: bool = False) -> list[dict]:
    """Discover all PBoC MPC article URLs then fetch each.

    Page-range synthesis: the footer of page 1 may only link to a SUBSET of
    pages (e.g. -2 and -4 but not -3).  We:
      1. Parse page 1 footer hrefs → initial page list;
      2. Fetch each discovered page and re-parse ITS footer, extending the
         max-N when a later page reveals a higher page number;
      3. Any gap between 2 and maxN is synthesised and fetched.
    This ensures years 2011–2015 (on pages 3–4 of the CMS) are not skipped.

    Listing publish dates: each listing page is parsed with _parse_listing_entries()
    which returns (href, publish_date_or_None) pairs.  The listing CMS stamp is
    threaded through to _pboc_fetch_article as listing_publish_date so that the
    parquet publish_date column is populated from the reliable CMS stamp rather
    than from body-text date extraction.
    """
    log.info("PBOC MPC: fetching index %s", PBOC_INDEX_URL)
    try:
        content, ct = _get(session, PBOC_INDEX_URL, pace=False)
    except Exception as exc:
        log.error("PBOC index fetch failed: %s", exc)
        return []
    html = _decode_html(content, ct)

    # --- Page-range synthesis ---
    # Start from hrefs found on page 1; build a frontier of pages to fetch.
    # As each page is fetched we re-parse its footer and extend the range.
    dir_url = PBOC_INDEX_URL.rsplit("/", 1)[0]

    # prefix → max_N discovered so far
    prefix_max: dict[str, int] = {}

    def _update_prefix_max(page_html: str) -> None:
        for m in _PBOC_PAGE_HREF_RE.finditer(page_html):
            pfx, n_str = m.group(1), m.group(2)
            n = int(n_str)
            if n >= 2:
                prefix_max[pfx] = max(prefix_max.get(pfx, 2), n)

    _update_prefix_max(html)  # seed from page 1

    # href → listing publish_date (str or None)
    listing_dates: dict[str, str | None] = {}

    def _harvest_listing(page_html: str) -> None:
        for href, pub in _parse_listing_entries(page_html):
            if href not in listing_dates:
                listing_dates[href] = pub

    _harvest_listing(html)  # harvest page 1

    if not prefix_max:
        log.warning(
            "PBOC MPC: only 1 listing page discovered — pagination hrefs not found. "
            "The CMS hash prefix may have changed or the index structure differs. "
            "Backfill will cover page 1 only; expect ~%d docs total but may fetch far fewer. "
            "Verify %s manually and update _PBOC_PAGE_HREF_RE if the hash changed.",
            69, PBOC_INDEX_URL,
        )

    # Fetch all pages 2..maxN (re-checking maxN after each page in case footer
    # reveals a higher N, though in practice the PBoC site is static).
    fetched_extra: set[str] = set()
    # Loop until we've fetched everything up to the current known max
    changed = True
    while changed:
        changed = False
        for prefix, max_n in list(prefix_max.items()):
            for k in range(2, max_n + 1):
                page_url = f"{dir_url}/{prefix}-{k}.html"
                if page_url in fetched_extra:
                    continue
                fetched_extra.add(page_url)
                changed = True
                try:
                    pcontent, pct = _get(session, page_url)
                    page_html = _decode_html(pcontent, pct)
                except Exception as exc:
                    log.warning("PBOC pagination fetch failed %s: %s", page_url, exc)
                    continue
                _update_prefix_max(page_html)
                _harvest_listing(page_html)
                hrefs_on_page = _pboc_article_hrefs(page_html)
                log.info("PBOC MPC: page %s → %d article hrefs", page_url, len(hrefs_on_page))

    all_page_urls = [PBOC_INDEX_URL] + sorted(fetched_extra)
    log.info("PBOC MPC: fetched %d listing pages total (1 index + %d extra)",
             len(all_page_urls), len(fetched_extra))
    log.info("PBOC MPC: %d unique hrefs with listing dates captured", len(listing_dates))

    # Build unique hrefs list preserving discovery order
    all_hrefs_ordered: list[str] = []
    seen_hrefs: set[str] = set()
    # Order: page 1 entries first (already in listing_dates from _harvest_listing),
    # then page 2..N in page order.  listing_dates is insertion-ordered (Python 3.7+).
    for href in listing_dates:
        if href not in seen_hrefs:
            seen_hrefs.add(href)
            all_hrefs_ordered.append(href)

    log.info("PBOC MPC: %d unique article hrefs discovered", len(all_hrefs_ordered))
    if dry_run:
        for h in all_hrefs_ordered:
            print(f"  [DRY-RUN pboc_mpc] {urljoin(PBOC_BASE, h)}")
        return []

    rows: list[dict] = []
    for i, href in enumerate(all_hrefs_ordered):
        if limit is not None and len(rows) >= limit:
            log.info("PBOC MPC: limit=%d reached", limit)
            break
        # Pass the listing CMS publish date so the parquet column is populated
        listing_pub = listing_dates.get(href)
        row = _pboc_fetch_article(session, href, listing_publish_date=listing_pub)
        if row is None:
            continue
        if row["doc_id"] in known_ids:
            log.debug("PBOC MPC: skipping existing %s", row["doc_id"][:16])
            continue
        rows.append(row)
        known_ids.add(row["doc_id"])
        log.info("PBOC MPC [%d/%d]: %s | yr=%s Q=%s pub=%s",
                 i + 1, len(all_hrefs_ordered), row["title"][:60],
                 row["meeting_year"], row["meeting_quarter"], row["publish_date"])
    return rows


# ---------------------------------------------------------------------------
# FAMILY 2 & 3: CCTV transcript scanning
# ---------------------------------------------------------------------------

POLITBURO_SOURCE = "cctv_news"

# Candidate date windows for Politburo econ meetings per year:
# ~Apr 25-30, ~Jul 28-31, ~Oct 25-31, ~Dec 5-15
_POLITBURO_WINDOWS: list[tuple[int, int, int, int]] = [
    (4, 25, 4, 30),
    (7, 28, 7, 31),
    (10, 25, 10, 31),
    (12, 5, 12, 15),
]

CCTV_START_YEAR = 2016
CCTV_BASE_URL = "https://tv.cctv.com/lm/xwlb/day/{ds}.shtml"


def _cctv_date_range(start: date, end: date):
    """Yield dates from start to end inclusive."""
    d = start
    while d <= end:
        yield d
        from datetime import timedelta
        d += timedelta(days=1)


def _is_politburo_econ(title: str, content: str) -> bool:
    """Filter: item must mention 政治局 AND (经济形势 OR 经济工作).

    Used for Phase-2 body-level filtering only.  For Phase-1 listing title
    pre-screening use _listing_may_be_politburo_econ() which is more permissive:
    short form titles like '中共中央政治局召开会议' contain 政治局 but not the
    economic keyword — the keyword often appears only in the body text.
    """
    text = title + content
    return "政治局" in text and ("经济形势" in text or "经济工作" in text)


def _listing_may_be_politburo_econ(title: str) -> bool:
    """Phase-1 title pre-screen: any Politburo meeting headline is worth fetching.

    Real Xinwen Lianbo listing titles for Politburo econ meetings are frequently
    the short form '中共中央政治局召开会议 习近平主持' — the economic keyword is
    only in the body.  Requiring both keywords at Phase 1 silently drops those days.

    Pre-screen: fetch full bodies for any day whose listing contains a headline
    with 政治局; the strict _is_politburo_econ() filter is applied at Phase 2.
    """
    return "政治局" in title


def _is_cewc(title: str, content: str) -> bool:
    """Filter: item must mention 中央经济工作会议."""
    text = title + content
    return "中央经济工作会议" in text


def _extract_politburo_meeting_date(content: str) -> str | None:
    """Extract the meeting date from Politburo readout text."""
    return extract_meeting_date(content)


def _cctv_fetch_day(ds: str) -> list[dict]:
    """Call akshare news_cctv(date=ds) and return raw rows.

    This is the slow path — it fetches every article body. Only called when
    the listing page indicates a matching title (see _cctv_fast_scan).
    """
    try:
        import akshare as ak
    except ImportError as e:
        raise RuntimeError(f"akshare not available: {e}") from e
    try:
        df = ak.news_cctv(date=ds)
        if df is None or df.empty:
            return []
        return df.to_dict("records")
    except Exception as exc:  # noqa: BLE001
        log.warning("CCTV fetch failed for %s: %s", ds, exc)
        return []


def _cctv_listing_titles(session: Any, ds: str) -> list[tuple[str, str]]:
    """Fast path: fetch only the CCTV 新闻联播 listing page for one date.

    Returns a list of (title, article_url) tuples extracted from the listing
    page. This takes ~1 HTTP request vs ~16 for news_cctv(). We use this to
    pre-screen dates: only call news_cctv() if a title passes the keyword filter.

    Returns empty list on any fetch/parse error (caller falls through to full fetch).
    """
    url = CCTV_BASE_URL.format(ds=ds)
    try:
        wait = PACE_MIN + random.uniform(0, PACE_JITTER)
        time.sleep(wait)
        resp = session.get(url, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        html = resp.text
    except Exception as exc:
        log.debug("CCTV listing fetch failed %s: %s", ds, exc)
        return []

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    results: list[tuple[str, str]] = []
    for li in soup.find_all("li"):
        a = li.find("a")
        if not a:
            continue
        title = a.get_text(strip=True)
        href = a.get("href", "")
        if title and href:
            results.append((title, href))
    return results


def _cctv_scan_dates(session: Any, known_ids: set[str],
                     date_iter, filter_fn, family: str,
                     limit: int | None, dry_run: bool,
                     listing_prefetch_fn=None) -> list[dict]:
    """Generic CCTV date scanner. Uses two-phase fetch: titles-first, bodies-only-on-match.

    Phase 1: GET listing page → extract titles (1 request/day).  A day proceeds
             to Phase 2 if ANY listing title passes listing_prefetch_fn(title).
             Falls back to the strict filter_fn(title, "") when no prefetch_fn is
             supplied.  Listing fetch failures are treated conservatively: the full
             body fetch is attempted regardless (so network hiccups don't silently
             drop real meetings).

    Phase 2: only for pre-screened days: call news_cctv() for full bodies, then
             apply the strict filter_fn(title, content).

    The two-function design solves the coverage-honesty problem: short-form listing
    titles like '中共中央政治局召开会议' contain 政治局 but not the economic keyword
    which appears only in the body.  A single filter applied to title-only would
    silently drop those meetings.
    """
    prefetch = listing_prefetch_fn if listing_prefetch_fn is not None else (
        lambda title: filter_fn(title, "")
    )

    rows: list[dict] = []
    checked = 0
    fetch_failures: list[str] = []  # collected for end-of-run coverage report

    for dt in date_iter:
        if limit is not None and len(rows) >= limit:
            break
        ds = dt.strftime("%Y%m%d")

        if dry_run:
            print(f"  [DRY-RUN {family}] probe {ds}")
            continue

        # Phase 1: fast title scan
        listing = _cctv_listing_titles(session, ds)
        checked += 1

        if not listing:
            # Listing fetch failed — fall through to full fetch as safety.
            # This path covers both network hiccups and genuine missing days; we
            # attempt the full fetch so real meetings are not silently dropped.
            title_match = True
            log.debug("CCTV %s %s: listing fetch failed/empty — attempting full fetch", family, ds)
        else:
            # Phase 1 pre-screen: use the permissive prefetch function, NOT the
            # strict filter, so short-form titles don't cause silent drops.
            title_match = any(prefetch(title) for title, _ in listing)

        if not title_match:
            log.debug("CCTV %s %s: no title match, skip", family, ds)
            continue

        # Phase 2: full body fetch (slow — akshare fetches every article)
        log.info("CCTV %s %s: title match found, fetching full transcript", family, ds)
        items = _cctv_fetch_day(ds)
        if not items:
            fetch_failures.append(ds)
            log.warning("CCTV %s %s: full fetch returned no items (fetch failure or empty)", family, ds)

        for item in items:
            title = str(item.get("title", ""))
            content = str(item.get("content", ""))
            if not filter_fn(title, content):
                continue
            url = f"cctv://news_cctv/{ds}"
            doc_id = make_doc_id(url, title)
            if doc_id in known_ids:
                log.debug("%s: skipping existing %s", family, doc_id[:16])
                continue
            body = f"{title}\n{content}".strip()
            body_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
            meeting_date = extract_meeting_date(content + title) or dt.isoformat()
            meeting_year = extract_meeting_year(content + title) or dt.year
            fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            row = {
                "doc_id": doc_id,
                "family": family,
                "meeting_year": meeting_year,
                "meeting_quarter": None,
                "meeting_date": meeting_date,
                "publish_date": dt.isoformat(),
                "title": title,
                "body": body,
                "body_sha256": body_sha256,
                "url": url,
                "source": POLITBURO_SOURCE,
                "_fetched_at": fetched_at,
            }
            rows.append(row)
            known_ids.add(doc_id)
            log.info("%s: %s | meeting_date=%s", family, title[:60], meeting_date)

    log.info("%s: checked %d dates, found %d readouts", family, checked, len(rows))
    if fetch_failures:
        log.warning(
            "%s: %d full-fetch failures (items returned empty after title pre-screen): %s",
            family, len(fetch_failures), ", ".join(fetch_failures),
        )
    return rows


def fetch_politburo_econ(session: Any, known_ids: set[str],
                          limit: int | None = None, dry_run: bool = False) -> list[dict]:
    """Scan CCTV candidate dates for Politburo econ-meeting readouts."""
    today = date.today()
    all_dates: list[date] = []
    for year in range(CCTV_START_YEAR, today.year + 1):
        for mo_start, d_start, mo_end, d_end in _POLITBURO_WINDOWS:
            try:
                start_dt = date(year, mo_start, d_start)
                # Clamp end day to valid month length
                import calendar
                max_day = calendar.monthrange(year, mo_end)[1]
                end_dt = date(year, mo_end, min(d_end, max_day))
            except ValueError:
                continue
            if start_dt > today:
                continue
            end_dt = min(end_dt, today)
            all_dates.extend(_cctv_date_range(start_dt, end_dt))

    return _cctv_scan_dates(session, known_ids, iter(all_dates),
                            _is_politburo_econ, "politburo_econ", limit, dry_run,
                            listing_prefetch_fn=_listing_may_be_politburo_econ)


# ---------------------------------------------------------------------------
# FAMILY 3: CEWC via CCTV transcripts
# ---------------------------------------------------------------------------

CEWC_SOURCE = "cctv_news"

# CEWC probe window: Dec 10-23
_CEWC_MONTH = 12
_CEWC_DAY_START = 10
_CEWC_DAY_END = 23

# Known gap: 2017 is absent from CCTV
CEWC_KNOWN_GAPS = {2017}


def fetch_cewc(session: Any, known_ids: set[str],
               limit: int | None = None, dry_run: bool = False) -> list[dict]:
    """Scan CCTV for CEWC readouts. Emits an explicit gap row for CEWC_KNOWN_GAPS."""
    today = date.today()
    all_dates: list[date] = []
    for year in range(CCTV_START_YEAR, today.year + 1):
        start_dt = date(year, _CEWC_MONTH, _CEWC_DAY_START)
        end_dt = date(year, _CEWC_MONTH, _CEWC_DAY_END)
        if start_dt > today:
            continue
        end_dt = min(end_dt, today)
        all_dates.extend(_cctv_date_range(start_dt, end_dt))

    rows = _cctv_scan_dates(session, known_ids, iter(all_dates),
                            _is_cewc, "cewc", limit, dry_run)

    # Emit explicit gap row(s) for known gaps
    years_found = {r["meeting_year"] for r in rows if r.get("source") != "explicit_gap"}
    for gap_year in sorted(CEWC_KNOWN_GAPS):
        gap_url = f"cctv://news_cctv/gap/{gap_year}"
        gap_title = f"CEWC {gap_year} — KNOWN GAP (absent from CCTV archive)"
        gap_doc_id = make_doc_id(gap_url, gap_title)
        if gap_doc_id not in known_ids and gap_year not in years_found:
            gap_body = (
                f"EXPLICIT GAP: The {gap_year} Central Economic Work Conference readout "
                f"is absent from the CCTV news_cctv archive. "
                f"This row was emitted intentionally so the gap is documented, not silently omitted."
            )
            rows.append({
                "doc_id": gap_doc_id,
                "family": "cewc",
                "meeting_year": gap_year,
                "meeting_quarter": None,
                "meeting_date": None,
                "publish_date": None,
                "title": gap_title,
                "body": gap_body,
                "body_sha256": hashlib.sha256(gap_body.encode("utf-8")).hexdigest(),
                "url": gap_url,
                "source": "explicit_gap",
                "_fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })
            known_ids.add(gap_doc_id)
            log.info("cewc: emitted explicit gap row for %d", gap_year)

    log.info("cewc: found %d readouts (+%d gap rows)",
             len([r for r in rows if r.get("source") != "explicit_gap"]),
             len([r for r in rows if r.get("source") == "explicit_gap"]))
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

FAMILY_RUNNERS = {
    "pboc_mpc": fetch_pboc_mpc,
    "politburo_econ": fetch_politburo_econ,
    "cewc": fetch_cewc,
}

# Soft expected minimums (real docs only, no gap rows).
# These are conservative lower bounds — used for coverage-honesty warnings only,
# not hard failures — so a partial run (--limit / --family) is not penalised.
# pboc_mpc: 69 docs per live site footer as of 2026-07; politburo_econ: ~30-44
# depends on window coverage; cewc: 9 real + 1 gap (2016-2025 with 2017 gap).
_FAMILY_EXPECTED_MIN = {
    "pboc_mpc": 60,        # ~69 per site, allow for 10% fetch failures
    "politburo_econ": 28,  # ~35-44 expected; 28 is a conservative floor
    "cewc": 8,             # 2016-2025 = 10y minus 2017 gap = 9 real; floor 8
}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Curated communique backfill — W1.1")
    parser.add_argument(
        "--family", choices=list(FAMILY_RUNNERS.keys()),
        help="Run a single family only (default: all)",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Maximum new rows per family (useful for smoke testing)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print discovered URLs, do not fetch body or write parquet",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-fetch even if doc_id already exists in parquet",
    )
    parser.add_argument(
        "--out", type=Path, default=OUT_PATH,
        help=f"Output parquet path (default: {OUT_PATH})",
    )
    parser.add_argument(
        "--verbose", action="store_true",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    import requests
    session = requests.Session()

    existing_df = load_existing(args.out)
    known_ids: set[str] = set() if args.force else set(existing_df["doc_id"].tolist() if not existing_df.empty else [])
    log.info("Loaded %d existing rows (known_ids=%d)", len(existing_df), len(known_ids))

    families_to_run = [args.family] if args.family else list(FAMILY_RUNNERS.keys())
    all_new_rows: list[dict] = []

    for family in families_to_run:
        log.info("=== Family: %s ===", family)
        runner = FAMILY_RUNNERS[family]
        try:
            new_rows = runner(session, known_ids, limit=args.limit, dry_run=args.dry_run)
        except Exception as exc:  # noqa: BLE001 — per-family isolation
            log.error("Family %s FAILED: %s", family, exc, exc_info=True)
            new_rows = []
        all_new_rows.extend(new_rows)
        log.info("Family %s: +%d new rows", family, len(new_rows))

    if args.dry_run:
        log.info("DRY-RUN: no parquet written")
        return

    final_df = upsert_rows(existing_df, all_new_rows)
    save_parquet(final_df, args.out)

    # Size check
    size_mb = args.out.stat().st_size / 1_048_576
    log.info("Wrote %d total rows to %s (%.2f MB)", len(final_df), args.out, size_mb)
    if size_mb >= 20:
        log.warning("Parquet size %.2f MB >= 20 MB; consider gitignoring", size_mb)

    # Summary with coverage-honesty reconciliation
    # Failures accumulated per family are not surfaced here because _cctv_scan_dates
    # logs them inline; the summary provides expected-vs-actual counts so an operator
    # can spot material shortfalls without scrolling past individual warnings.
    print("\n=== Backfill summary ===")
    coverage_warnings: list[str] = []
    for fam in (args.family,) if args.family else list(FAMILY_RUNNERS.keys()):
        subset = final_df[final_df["family"] == fam] if not final_df.empty else pd.DataFrame()
        real = subset[subset["source"] != "explicit_gap"] if not subset.empty else subset
        gaps = subset[subset["source"] == "explicit_gap"] if not subset.empty else subset
        if subset.empty:
            print(f"  {fam}: 0 rows")
            continue
        min_yr = real["meeting_year"].min() if not real.empty else "n/a"
        max_yr = real["meeting_year"].max() if not real.empty else "n/a"
        n_real = len(real)
        line = (
            f"  {fam}: {n_real} docs (year {min_yr}–{max_yr})"
            + (f" + {len(gaps)} explicit gap row(s)" if not gaps.empty else "")
        )
        exp_min = _FAMILY_EXPECTED_MIN.get(fam)
        if exp_min is not None and not args.limit:
            # Only check when running the full backfill (not --limit smoke test)
            line += f"  [expected >= {exp_min}]"
            if n_real < exp_min:
                warn = (
                    f"COVERAGE WARNING: {fam} has {n_real} docs but expected >= {exp_min}. "
                    f"Check logs for fetch failures — some quarters/meetings may be missing."
                )
                coverage_warnings.append(warn)
                line += "  *** BELOW MINIMUM ***"
        print(line)
    print(f"  Total: {len(final_df)} rows | {size_mb:.2f} MB")

    if coverage_warnings:
        print("\n=== Coverage warnings ===")
        for w in coverage_warnings:
            print(f"  {w}")
        log.warning("Coverage shortfalls detected — review fetch logs for failures")


if __name__ == "__main__":
    main()
