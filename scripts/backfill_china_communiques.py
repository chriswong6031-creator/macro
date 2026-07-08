"""Curated historical communiqué backfill — W1.1 of CHINA_INTEL_CYCLES_MASTERPLAN.

Three families:
  pboc_mpc    — PBoC Monetary Policy Committee quarterly readouts (2009→, ~69 docs)
  politburo_econ — Politburo economic-analysis meeting readouts (2016→, ~30-44 docs
                   given window coverage; ~4/yr)
  cewc        — Central Economic Work Conference annual readouts (2016→, ~10 docs;
                 CCTV-dead years incl. the 2017 CCTV gap are filled from curated
                 gov.cn mirrors [source=gov.cn]; the 2017 gap additionally keeps
                 an explicit gap-marker row documenting CCTV absence)

CCTV families are READOUT-only (not mention-level): an item must carry the
canonical readout title (中共中央政治局召开会议 / 中央经济工作会议在北京举行)
plus the convening phrase in the body; meeting_year derives from the BROADCAST
date (sanity-bounded 2016-2027), never from transcript text; one readout is
kept per meeting (earliest broadcast date, longest body).

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
    # meeting_quarter is null for politburo_econ/cewc — keep it nullable-int
    # (concat of int64 + None would otherwise coerce to float64).
    combined["meeting_quarter"] = combined["meeting_quarter"].astype("Int64")
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

# Candidate date windows for Politburo econ meetings per year. Ranges cover the
# measured spread of actual meeting dates 2016-2026: Apr 17 (2020) – Apr 30
# (2021/2024), Jul 24 (2017/2023) – Jul 31 (2018), the off-schedule Sep econ
# meeting (2024-09-26), Oct 28-31, Dec 6-13. Each window MUST stay within one
# month — _politburo_meeting_key identifies a meeting by (year, month).
_POLITBURO_WINDOWS: list[tuple[int, int, int, int]] = [
    (4, 15, 4, 30),
    (7, 24, 7, 31),
    (9, 24, 9, 30),
    (10, 25, 10, 31),
    (12, 5, 12, 15),
]

CCTV_START_YEAR = 2016
CCTV_BASE_URL = "https://tv.cctv.com/lm/xwlb/day/{ds}.shtml"

# Local CCTV archive (scripts/backfill_cctv_archive.py output, Mac-local /
# gitignored): monthly parquets named YYYY-MM.parquet with columns
# date/order_idx/title/content/fetch_status. Days covered there are read
# locally — zero network; uncovered days fall through to the network path.
CCTV_ARCHIVE_DIR = REPO_ROOT / "data" / "china_news" / "cctv_archive"

# Hard ceiling on one day's full-transcript fetch. Measured live 2026-07-06: an
# akshare news_cctv call with no timeout hung for ~4.5h and the run was killed
# with nothing persisted.
CCTV_FETCH_TIMEOUT_S = 300


def _call_with_timeout(fn, timeout_s: float, *args, **kwargs):
    """Run fn(*args, **kwargs) in a daemon thread with a hard timeout.

    Raises TimeoutError on expiry; re-raises fn's exception otherwise. A daemon
    thread (not ThreadPoolExecutor) is required: a hung worker must not block
    interpreter exit via concurrent.futures' atexit join.
    """
    import threading
    result: list = []
    error: list = []

    def _target() -> None:
        try:
            result.append(fn(*args, **kwargs))
        except Exception as exc:  # noqa: BLE001 — re-raised in caller thread
            error.append(exc)

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        raise TimeoutError(f"timed out after {timeout_s}s")
    if error:
        raise error[0]
    return result[0]

# Sanity bounds for broadcast-derived meeting_year. akshare news_cctv coverage
# starts 2016-02-03; the upper headroom guards against window/clock bugs ever
# producing future years (transcript TEXT years measured live spanned 1954→2030).
CCTV_YEAR_MIN = 2016
CCTV_YEAR_MAX = 2027


def broadcast_meeting_year(broadcast: date) -> int | None:
    """Meeting year for CCTV items = the broadcast date's year, sanity-bounded.

    Transcript text is full of spurious year mentions (historical references like
    1954年, forward targets like 2030年), so the broadcast date is the only
    trustworthy anchor: readouts air the evening the meeting concludes.
    Returns None when the broadcast year falls outside [CCTV_YEAR_MIN, CCTV_YEAR_MAX].
    """
    if CCTV_YEAR_MIN <= broadcast.year <= CCTV_YEAR_MAX:
        return broadcast.year
    return None


def plausible_meeting_date(text: str, broadcast: date,
                           max_back_days: int = 14, max_fwd_days: int = 1) -> str:
    """Extract a meeting date from transcript text, accepting it only when it is
    plausibly THIS meeting's date: within [broadcast - max_back_days,
    broadcast + max_fwd_days].

    Readout bodies usually date the meeting without a year (e.g. 4月30日召开会议)
    which _DATE_RE cannot match; full-form 年月日 dates that DO appear are mostly
    historical references or future effective dates. Out-of-window extractions
    fall back to the broadcast date itself.
    """
    iso = extract_meeting_date(text)
    if iso is not None:
        try:
            d = date.fromisoformat(iso)
        except ValueError:
            d = None
        if d is not None and -max_fwd_days <= (broadcast - d).days <= max_back_days:
            return iso
    return broadcast.isoformat()


def _cctv_date_range(start: date, end: date):
    """Yield dates from start to end inclusive."""
    d = start
    while d <= end:
        yield d
        from datetime import timedelta
        d += timedelta(days=1)


# --- Readout-vs-reference discrimination ----------------------------------
# A transcript item that merely MENTIONS 政治局 / 中央经济工作会议 (commentary,
# 精神传达, follow-up coverage, historical retrospectives) is NOT the meeting
# readout. Mention-level filters measured live 2026-07-06 yielded 57
# politburo_econ / 130 cewc items spanning 1954→2030. Readouts are identified
# by the canonical headline plus the convening phrase in the body.

# Full-Politburo readout headline. Note this does NOT match Standing-Committee
# readouts (中共中央政治局常务委员会召开会议) — 召开会议 must follow 政治局 directly.
_POLITBURO_READOUT_TITLE = "中共中央政治局召开会议"
# Body convening phrase: allows a dateline between 政治局 and 召开会议
# (e.g. 中共中央政治局4月30日召开会议) but rejects 常务委员会 via (?!常).
_POLITBURO_CONVENE_RE = re.compile(r"中共中央政治局(?!常)[^。；\n]{0,15}召开会议")

_CEWC_READOUT_TITLE_RE = re.compile(r"中央经济工作会议在(?:北京|京)(?:举行|召开|闭幕)")
_CEWC_CONVENE_RE = re.compile(r"中央经济工作会议[^。；\n]{0,30}在(?:北京|京)(?:举行|召开|闭幕)")


def _is_politburo_econ(title: str, content: str) -> bool:
    """READOUT filter: the item must BE the full-Politburo econ-meeting readout.

    Three gates:
      1. Title carries the canonical readout headline 中共中央政治局召开会议
         (excludes Standing-Committee readouts and mere references);
      2. Body contains the convening phrase 中共中央政治局[dateline]召开会议
         (falls back to the title when content is empty — Phase-1 title-only calls);
      3. The meeting is economic: 经济形势 or 经济工作 in title+body.

    Used for Phase-2 body-level filtering only.  For Phase-1 listing title
    pre-screening use _listing_may_be_politburo_econ() which is more permissive:
    short form titles like '中共中央政治局召开会议 习近平主持' lack the economic
    keyword — it often appears only in the body text.
    """
    if _POLITBURO_READOUT_TITLE not in title:
        return False
    if not _POLITBURO_CONVENE_RE.search(content or title):
        return False
    text = title + content
    return "经济形势" in text or "经济工作" in text


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
    """READOUT filter: the item must BE the CEWC readout, not a reference.

    Two gates: canonical headline 中央经济工作会议在(北京|京)(举行|召开|闭幕) in the
    title, plus the convening phrase in the body (e.g.
    中央经济工作会议12月11日至12日在北京举行; falls back to the title when
    content is empty). Rejects 解读/评论/精神传达 items that merely mention the
    conference.
    """
    if not _CEWC_READOUT_TITLE_RE.search(title):
        return False
    return bool(_CEWC_CONVENE_RE.search(content or title))


def _listing_may_be_cewc(title: str) -> bool:
    """Phase-1 listing pre-screen for CEWC: permissive mention-level check.

    Listing-page titles can be truncated or reformatted, so requiring the full
    canonical headline at Phase 1 could silently drop the real readout day.
    The strict _is_cewc() gate is applied at Phase 2 on full bodies.
    """
    return "中央经济工作会议" in title


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
        df = _call_with_timeout(ak.news_cctv, CCTV_FETCH_TIMEOUT_S, date=ds)
        if df is None or df.empty:
            return []
        return df.to_dict("records")
    except TimeoutError:
        log.warning("CCTV fetch for %s timed out after %ds — treated as fetch failure",
                    ds, CCTV_FETCH_TIMEOUT_S)
        return []
    except Exception as exc:  # noqa: BLE001
        log.warning("CCTV fetch failed for %s: %s", ds, exc)
        return []


def _archive_month_df(archive_dir_str: str, month: str) -> pd.DataFrame | None:
    """Load one YYYY-MM.parquet from the local CCTV archive (None if absent).

    Cached on (dir, month) so a 28-day probe window reads its month file once.

    listing_title (PR #1913) is read when the shard carries it and tolerated
    when absent: only the 2016-02→2019-03 backfill and future repairs populate
    it, so legacy shards lack the column entirely. The parquet schema is probed
    first so a legacy shard is read once, not read-fail-reread.
    """
    key = (archive_dir_str, month)
    if key in _ARCHIVE_MONTH_CACHE:
        return _ARCHIVE_MONTH_CACHE[key]
    path = Path(archive_dir_str) / f"{month}.parquet"
    df = None
    if path.exists():
        cols = ["date", "title", "content", "fetch_status"]
        try:
            import pyarrow.parquet as pq
            if "listing_title" in pq.ParquetFile(path).schema.names:
                cols = cols + ["listing_title"]
        except Exception:  # noqa: BLE001 — schema probe is best-effort
            pass
        df = pd.read_parquet(path, columns=cols)
    _ARCHIVE_MONTH_CACHE.clear()  # keep at most one month resident
    _ARCHIVE_MONTH_CACHE[key] = df
    return df


_ARCHIVE_MONTH_CACHE: dict[tuple[str, str], pd.DataFrame | None] = {}


def _archive_day_items(archive_dir: Path, dt: date, filter_fn,
                       prefetch_fn=None) -> list[dict] | None:
    """Return the day's transcript items from the local archive, or None when
    the day must go to the network instead.

    The archive may answer a day ONLY when it can prove presence or absence:
      - an intact (fetch_status=ok) row passes the strict filter_fn → presence
        proven, return the intact rows; or
      - the day has intact rows and ZERO stub rows → absence provable, return
        the intact rows (the scanner will find no match); or
      - the day HAS stub rows but every stub row carries a non-empty
        listing_title (PR #1913) and NONE of those real titles pass the
        permissive listing prescreen → absence provable from the listing alone,
        return the intact rows.
    Anything else → None (network fallback): a title-less stub row (legacy
    shard, or listing fetch failed) can silently hide the readout — measured
    live 2026-07-07: the 2019/2022/2024 CEWC readouts were all stub rows and a
    title-based stub check missed every one.

    prefetch_fn (title -> bool): the permissive Phase-1 listing prescreen used
    to test the stub rows' recorded listing titles. filter_fn(title, "") is too
    strict for short-form listing titles (the economic keyword lives only in the
    body), so we mirror _cctv_scan_dates: default to filter_fn(title, "") only
    when no prefetch_fn is supplied.

    The listing_title path is strictly opt-in per row: a stub row with an empty
    or absent listing_title (every legacy shard, and any day whose listing fetch
    failed) keeps the conservative network fallback.
    """
    df = _archive_month_df(str(archive_dir), dt.strftime("%Y-%m"))
    if df is None:
        return None
    day = df[df["date"] == dt.isoformat()]
    if day.empty:
        return None
    ok = day[day["fetch_status"] == "ok"]
    items = [{"title": t, "content": c} for t, c in zip(ok["title"], ok["content"])]
    if any(filter_fn(str(it["title"]), str(it["content"])) for it in items):
        return items
    if len(ok) < len(day):
        # Day has stub/error rows. Try to prove absence from the recorded
        # listing titles before conceding the whole day to the network.
        stubs = day[day["fetch_status"] != "ok"]
        listing_titles = (
            stubs["listing_title"].fillna("").astype(str).tolist()
            if "listing_title" in day.columns else []
        )
        # Opt-in per row: EVERY stub row must carry a non-empty listing_title.
        if listing_titles and all(listing_titles):
            prescreen = prefetch_fn if prefetch_fn is not None else (
                lambda t: filter_fn(t, "")
            )
            candidates = {
                t for lt in listing_titles for t in lt.split("\n") if t
            }
            if any(prescreen(t) for t in candidates):
                return None  # a real title may be the readout → fetch the body
            return items  # no listing title matches → absence proven, answer locally
        return None
    return items if items else None


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
    # Keep only real article links (…/YYYY/MM/DD/VIDE….shtml). A throttle /
    # soft-error page still renders nav <li><a> items; treating those as a
    # valid listing silently skipped real meeting days (measured live: the
    # 2018-07-31 politburo readout was missed by two consecutive runs). Zero
    # real items → [] so the caller falls back to the full-day fetch.
    return [(t, h) for t, h in results if "VIDE" in h]


def _cctv_scan_dates(session: Any, known_ids: set[str],
                     date_iter, filter_fn, family: str,
                     limit: int | None, dry_run: bool,
                     listing_prefetch_fn=None,
                     meeting_key_fn=None,
                     archive_dir: Path | None = None,
                     known_meeting_keys: set | None = None) -> list[dict]:
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

    meeting_key_fn (row dict → hashable): when provided, collapses the collected
    rows to ONE readout per meeting — a meeting airs across multiple items and
    days, so we keep the item on the EARLIEST broadcast date, longest body as
    tie-break within that date.

    archive_dir: when set, days covered by the local CCTV archive are read from
    the monthly parquets (zero network); only uncovered days go to the two-phase
    network path (see _archive_day_items for the fallback conditions).

    known_meeting_keys: meeting keys already present in the parquet from earlier
    runs. Needed for resumability: a prior run keeps only ONE item per meeting,
    so a re-scan would see the meeting's OTHER items (different doc_ids, not in
    known_ids) as new and re-add the meeting under a different item.
    """
    prefetch = listing_prefetch_fn if listing_prefetch_fn is not None else (
        lambda title: filter_fn(title, "")
    )

    rows: list[dict] = []
    checked = 0
    archive_days = 0
    fetch_failures: list[str] = []  # collected for end-of-run coverage report

    for dt in date_iter:
        if limit is not None and len(rows) >= limit:
            break
        ds = dt.strftime("%Y%m%d")

        # A probe day maps to exactly one prospective meeting within a family
        # scan — if that meeting is already in the parquet, skip the day
        # entirely (resumability without redundant fetches).
        if known_meeting_keys and meeting_key_fn is not None:
            prospective = meeting_key_fn(
                {"meeting_year": dt.year, "publish_date": dt.isoformat()}
            )
            if prospective in known_meeting_keys:
                log.debug("CCTV %s %s: meeting already collected — day skipped", family, ds)
                continue

        if dry_run:
            print(f"  [DRY-RUN {family}] probe {ds}")
            continue

        # Archive fast path: read the day locally when covered — zero network.
        items = None
        if archive_dir is not None:
            items = _archive_day_items(archive_dir, dt, filter_fn, prefetch_fn=prefetch)
            if items is not None:
                checked += 1
                archive_days += 1
                log.debug("CCTV %s %s: read %d items from local archive", family, ds, len(items))

        if items is None:
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
            # meeting_year/meeting_date anchor on the BROADCAST date, never on
            # transcript text: text-derived years span 1954→2030 (historical
            # references, forward targets).
            meeting_year = broadcast_meeting_year(dt)
            if meeting_year is None:
                log.warning(
                    "%s %s: broadcast year %d outside sanity bounds [%d, %d] — item skipped",
                    family, ds, dt.year, CCTV_YEAR_MIN, CCTV_YEAR_MAX,
                )
                continue
            meeting_date = plausible_meeting_date(content + title, dt)
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

    # Per-meeting dedup: a meeting airs across multiple items/days (re-airs,
    # split headlines). Keep ONE readout per meeting key — earliest broadcast
    # date wins; among same-date items, the longest body wins.
    if meeting_key_fn is not None and rows:
        selected: dict[Any, dict] = {}
        for r in rows:
            k = meeting_key_fn(r)
            cur = selected.get(k)
            if cur is None or (r["publish_date"], -len(r["body"])) < (
                cur["publish_date"], -len(cur["body"])
            ):
                selected[k] = r
        n_dropped = len(rows) - len(selected)
        if n_dropped:
            log.info("%s: per-meeting dedup dropped %d duplicate item(s) → %d meetings kept",
                     family, n_dropped, len(selected))
        if known_meeting_keys:
            n_before = len(selected)
            selected = {k: v for k, v in selected.items() if k not in known_meeting_keys}
            if len(selected) != n_before:
                log.info("%s: %d meeting(s) already in parquet from earlier runs — skipped",
                         family, n_before - len(selected))
        rows = sorted(selected.values(), key=lambda r: r["publish_date"])

    log.info("%s: checked %d dates (%d from local archive, %d via network), found %d readouts",
             family, checked, archive_days, checked - archive_days, len(rows))
    if fetch_failures:
        log.warning(
            "%s: %d full-fetch failures (items returned empty after title pre-screen): %s",
            family, len(fetch_failures), ", ".join(fetch_failures),
        )
    return rows


def _politburo_meeting_key(row: dict) -> tuple[int, int]:
    """One Politburo econ meeting per (year, window month).

    Every probe window in _POLITBURO_WINDOWS is contained within a single month,
    so (broadcast year, broadcast month) uniquely identifies the meeting.
    """
    return (int(row["meeting_year"]), int(row["publish_date"][5:7]))


def _cewc_meeting_key(row: dict) -> int:
    """One CEWC per calendar year (annual December conference)."""
    return int(row["meeting_year"])


def fetch_politburo_econ(session: Any, known_ids: set[str],
                          limit: int | None = None, dry_run: bool = False,
                          archive_dir: Path | None = None,
                          known_meeting_keys: set | None = None) -> list[dict]:
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
                            listing_prefetch_fn=_listing_may_be_politburo_econ,
                            meeting_key_fn=_politburo_meeting_key,
                            archive_dir=archive_dir,
                            known_meeting_keys=known_meeting_keys)


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

# Curated gov.cn mirrors for readouts the CCTV route CANNOT serve. Measured
# 2026-07-07: for these years the Xinwen Lianbo listing still shows the readout
# item, but the article page hangs/stubs (the local archive holds title-less
# stub rows for exactly these items, and live akshare drops them). The
# masterplan (W1.1) sanctions gov.cn/Xinhua mirrors for these families.
# 2017 additionally has no CCTV listing at all — the explicit gap row stays
# (it documents CCTV absence); the mirror supplies the text with source=gov.cn.
CEWC_GOVCN_FALLBACKS: dict[int, str] = {
    2017: "https://www.gov.cn/xinwen/2017-12/20/content_5248899.htm",
    2018: "https://www.gov.cn/xinwen/2018-12/21/content_5350934.htm",
    2019: "https://www.gov.cn/xinwen/2019-12/12/content_5460670.htm",
    2022: "https://www.gov.cn/xinwen/2022-12/16/content_5732408.htm",
}


def _fetch_govcn_readout(session: Any, year: int, url: str) -> dict | None:
    """Fetch one curated gov.cn CEWC readout page and build a parquet row.

    The page must still pass the strict _is_cewc readout gate — curation names
    the URL, it does not bypass the filter. Returns None (with a warning) on
    fetch failure or when the page does not yield a readout body.
    """
    try:
        content, ct = _get(session, url)
    except Exception as exc:  # noqa: BLE001
        log.warning("gov.cn fallback %d fetch failed %s: %s", year, url, exc)
        return None
    html = _decode_html(content, ct)
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    t = soup.find("title")
    if t:
        # Strip the site suffix (e.g. …_滚动新闻_中国政府网)
        title = re.sub(r"[_|].*$", "", t.get_text(strip=True)).strip()
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        title = h1.get_text(strip=True)

    container = (soup.find("div", class_="pages_content")
                 or soup.find("td", class_="b12c")
                 or soup)
    paras = [p.get_text(" ", strip=True) for p in container.find_all("p")
             if p.get_text(strip=True)]
    body = "\n".join(paras).strip()

    if not _is_cewc(title, body) or len(body) < 500:
        log.warning("gov.cn fallback %d: page did not yield a readout "
                    "(title=%r, body_len=%d) — skipped", year, title[:40], len(body))
        return None

    m = re.search(r"/(\d{4})-(\d{2})/(\d{2})/", url)
    page_date = date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None

    return {
        "doc_id": make_doc_id(url, title),
        "family": "cewc",
        "meeting_year": year,
        "meeting_quarter": None,
        "meeting_date": plausible_meeting_date(body, page_date) if page_date else None,
        "publish_date": page_date.isoformat() if page_date else None,
        "title": title,
        "body": body,
        "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "url": url,
        "source": "gov.cn",
        "_fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def fetch_cewc(session: Any, known_ids: set[str],
               limit: int | None = None, dry_run: bool = False,
               archive_dir: Path | None = None,
               known_meeting_keys: set | None = None) -> list[dict]:
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
                            _is_cewc, "cewc", limit, dry_run,
                            listing_prefetch_fn=_listing_may_be_cewc,
                            meeting_key_fn=_cewc_meeting_key,
                            archive_dir=archive_dir,
                            known_meeting_keys=known_meeting_keys)

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

    # Curated gov.cn fallbacks for CCTV-dead years (after gap emission, so the
    # 2017 CCTV gap marker is never suppressed by the mirror fill).
    years_present = {r["meeting_year"] for r in rows if r.get("source") != "explicit_gap"}
    if known_meeting_keys:
        years_present |= {int(k) for k in known_meeting_keys}
    for year, url in sorted(CEWC_GOVCN_FALLBACKS.items()):
        if year in years_present:
            continue
        if limit is not None and len([r for r in rows if r.get("source") != "explicit_gap"]) >= limit:
            break
        if dry_run:
            print(f"  [DRY-RUN cewc] gov.cn fallback {year}: {url}")
            continue
        row = _fetch_govcn_readout(session, year, url)
        if row is None:
            continue
        if row["doc_id"] in known_ids:
            continue
        rows.append(row)
        known_ids.add(row["doc_id"])
        log.info("cewc: gov.cn fallback filled %d | %s", year, row["title"][:60])

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
# pboc_mpc: 69 docs per live site footer as of 2026-07.
# politburo_econ: reconciled against known meeting dates within _POLITBURO_WINDOWS,
# 2016→2026-07 the windows contain ~34 meetings (regular Apr/Jul/Oct-ish/Dec
# cadence with skips in Congress/plenum months, plus the 2024-09-26 special
# meeting); floor 30 allows a few transient fetch misses.
# cewc: 2016-2025 = 10 real (CCTV + gov.cn mirrors for CCTV-dead years incl.
# the 2017 CCTV gap, which also keeps its explicit gap marker row); floor 9.
_FAMILY_EXPECTED_MIN = {
    "pboc_mpc": 60,        # ~69 per site, allow for 10% fetch failures
    "politburo_econ": 30,
    "cewc": 9,
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
        "--archive", type=Path, default=CCTV_ARCHIVE_DIR,
        help="Local CCTV archive dir (monthly YYYY-MM.parquet); days covered "
             "there are read locally instead of over the network "
             f"(default: {CCTV_ARCHIVE_DIR}; pass a non-existent path to disable)",
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

    archive_dir: Path | None = args.archive if args.archive.is_dir() else None
    if archive_dir is not None:
        log.info("Local CCTV archive enabled: %s", archive_dir)
    else:
        log.info("Local CCTV archive not found at %s — CCTV days go via network", args.archive)

    families_to_run = [args.family] if args.family else list(FAMILY_RUNNERS.keys())

    for family in families_to_run:
        log.info("=== Family: %s ===", family)
        runner = FAMILY_RUNNERS[family]
        kwargs: dict[str, Any] = {"limit": args.limit, "dry_run": args.dry_run}
        if family in ("politburo_econ", "cewc"):
            kwargs["archive_dir"] = archive_dir
            # Meeting keys already in the parquet: a re-run must not re-add a
            # meeting through a different item of the same broadcast (see
            # _cctv_scan_dates docstring).
            key_fn = _politburo_meeting_key if family == "politburo_econ" else _cewc_meeting_key
            if not existing_df.empty:
                fam_rows = existing_df[
                    (existing_df["family"] == family)
                    & (existing_df["source"] != "explicit_gap")
                ]
                kwargs["known_meeting_keys"] = {
                    key_fn(r) for r in fam_rows.to_dict("records")
                }
        try:
            new_rows = runner(session, known_ids, **kwargs)
        except Exception as exc:  # noqa: BLE001 — per-family isolation
            log.error("Family %s FAILED: %s", family, exc, exc_info=True)
            new_rows = []
        log.info("Family %s: +%d new rows", family, len(new_rows))
        # Checkpoint after each family: a later hang/kill must not lose earlier
        # families' work (measured live 2026-07-06: a 38-min run was killed
        # before the single end-of-run write and persisted nothing).
        if not args.dry_run and new_rows:
            existing_df = upsert_rows(existing_df, new_rows)
            save_parquet(existing_df, args.out)
            log.info("Checkpoint: %d total rows written to %s", len(existing_df), args.out)

    if args.dry_run:
        log.info("DRY-RUN: no parquet written")
        return

    final_df = upsert_rows(existing_df, [])
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
