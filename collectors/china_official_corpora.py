"""China official policy corpora — the primary-source tape the Communiqué Diff runs on.

KEYLESS · DISPLAY/CONTEXT-ONLY · PACED · CACHED · CHECKPOINTED. This collector is
the W4 B1 foundation (spec research/QUALITATIVE_INTELLIGENCE_UPGRADE_BY_FABLE.md
D9 / Appendix P4): it fetches DISCRETE, DATED documents of official Chinese policy
language from five organs and stores their raw text + a body_sha256 + fetch
metadata so engine/communique_diff.py can diff canonical formulas across a trailing
window.

Sources (all free, keyless, browser-UA — gov.cn is IP-reputation-sensitive [P4],
so we send a browser User-Agent, the FREDGRAPH_UA gotcha pattern, and pace between
requests):

  (a) State Council   gov.cn/zhengce/ latest releases (policy documents)
  (b) PBOC            pbc.gov.cn paginated announcement archive
  (c) NDRC            ndrc.gov.cn leaf tz/ notice dirs (index dirs are JS stubs —
                      we target the article LEAVES per [P4])
  (d) CSRC            csrc.gov.cn common_list news
  (e) People's Daily  paper.people.com.cn/rmrb layout page — the front-page ARTICLE
                      ORDER is editorial prominence (order = the signal, D9)

Each fetched document row carries:
  organ, doc_id, title, url, body, body_sha256, seendate (doc date when parseable),
  _crawled_at (WE stamp it once at the fetch boundary — PIT discipline), lang="zh",
  timestamp_quality, layout_rank (People's Daily front-page order; -1 elsewhere).

Storage: date-keyed parquet under data/china_official/ (one file per crawl day,
keep-FIRST on doc_id so the first print of a document wins and a re-edit never
overwrites the original body/hash — the Missing-Tape body-hash leg, D8). The
adapter ALSO emits qbus rows (lang=zh, TIER1, PUBLISHER_STATED/CRAWL_BOUNDED,
body_sha256 set) so the same documents fatten the unified item store and the
Missing-Tape baseline.

akshare is NOT used here — these are direct HTML fetches (requests + bs4, both
already in the tree). Every organ is isolated in its own try/except so one drifting
site never sinks the others; the adapter degrades to "fewer documents" rather than
taking the run (or the build) down. Nothing here is ever a scoring input.

See the `china_official` block in config.yml.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

SCHEMA = "china_official.v1"

# Browser UA — gov.cn / pbc.gov.cn are IP-reputation + UA sensitive ([P4]); a
# library UA gets 403'd. The FREDGRAPH_UA gotcha pattern: send a real browser UA.
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# --------------------------------------------------------------------------- #
# Organ index pages — each yields a list of dated document LEAVES. `kind` selects
# the parse strategy; `layout` marks the People's Daily front-page ordering source
# (article order = editorial prominence, D9). `domain` is used to keep only same-
# site article links (drop nav/cross-site chrome).
# --------------------------------------------------------------------------- #
ORGANS: list[dict] = [
    {"organ": "state_council", "name": "State Council 国务院",
     "url": "https://www.gov.cn/zhengce/",
     "domain": "gov.cn", "kind": "index", "theme": "policy"},
    {"organ": "pboc", "name": "PBOC 人民银行",
     "url": "http://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html",
     "domain": "pbc.gov.cn", "kind": "index", "theme": "monetary"},
    {"organ": "ndrc", "name": "NDRC 发改委",
     "url": "https://www.ndrc.gov.cn/xxgk/zcfb/tz/",
     "domain": "ndrc.gov.cn", "kind": "index", "theme": "policy"},
    {"organ": "csrc", "name": "CSRC 证监会",
     "url": "http://www.csrc.gov.cn/csrc/c100028/common_list.shtml",
     "domain": "csrc.gov.cn", "kind": "index", "theme": "markets"},
    {"organ": "peoples_daily", "name": "People's Daily 人民日报",
     "url": "",   # resolved per-day to the rmrb layout page (node_01 = front page)
     "domain": "people.com.cn", "kind": "layout", "theme": "politics"},
]

# --------------------------------------------------------------------------- #
# encoding + text helpers (mirrors china_news._decode_page — native CN portals
# frequently serve gb2312/gbk without an HTTP charset).
# --------------------------------------------------------------------------- #
_META_CHARSET_RE = re.compile(
    rb"""<meta[^>]+charset=["']?\s*([a-zA-Z0-9_\-]+)""", re.I)
_WS_RE = re.compile(r"\s+")
_DATE_RE = re.compile(r"(20\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})")
_SCRIPT_STYLE_RE = re.compile(r"(?is)<(script|style)[^>]*>.*?</\1>")
_TAG_RE = re.compile(r"(?s)<[^>]+>")


def _decode(content: bytes, content_type: str = "") -> str:
    """Decode HTML bytes honoring the real charset (gb2312/gbk → gb18030). PURE."""
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


def _strip_html(html_text: str) -> str:
    """Very small tag stripper → collapsed plain text. PURE (no bs4 dep)."""
    s = _SCRIPT_STYLE_RE.sub(" ", html_text or "")
    s = _TAG_RE.sub(" ", s)
    # unescape the handful of entities that survive into body text
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                 ("&gt;", ">"), ("&quot;", '"'), ("&#160;", " ")):
        s = s.replace(a, b)
    return _WS_RE.sub(" ", s).strip()


def _doc_date(text: str) -> str:
    """First YYYY-MM-DD-ish date in text → ISO date, or ''. PURE."""
    m = _DATE_RE.search(text or "")
    if not m:
        return ""
    try:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return date(y, mo, d).isoformat()
    except (ValueError, TypeError):
        return ""


def body_sha256(body: str) -> str:
    """sha256 hex of a body (empty body → ''). PURE. Shared convention with qbus."""
    if not body:
        return ""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _same_site(href: str, domain: str) -> bool:
    """True if href's host ends with the organ domain (drop cross-site chrome). PURE."""
    try:
        host = urlsplit(href).netloc.lower()
    except (ValueError, TypeError):
        return False
    if not host:
        return True  # relative link on the same page
    host = host[4:] if host.startswith("www.") else host
    return host == domain or host.endswith("." + domain) or domain in host


def _peoples_daily_url(d: date) -> str:
    """The rmrb layout page for a given day. node_01 == front page == prominence.
    e.g. paper.people.com.cn/rmrb/pc/layout/202607/02/node_01.html"""
    return (f"http://paper.people.com.cn/rmrb/pc/layout/"
            f"{d.strftime('%Y%m')}/{d.strftime('%d')}/node_01.html")


# --------------------------------------------------------------------------- #
# link extraction — pure, regex-based (bs4 optional; we do not require it here so
# the collector has no hard bs4 dependency). Returns [{title, href}] in DOCUMENT
# ORDER (order is load-bearing for People's Daily prominence — D9).
# --------------------------------------------------------------------------- #
_ANCHOR_RE = re.compile(r'(?is)<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>')


def extract_links(html_text: str, base_url: str, domain: str,
                  min_title: int = 6) -> list[dict]:
    """Anchors from an index/layout page as [{title, href}] in document order.
    Same-site only, title ≥ min_title chars, deduped on href (keep first =
    highest on page). PURE — the ORDER of the returned list is the page order,
    which the layout parser reads as editorial prominence."""
    out: list[dict] = []
    seen: set[str] = set()
    for m in _ANCHOR_RE.finditer(html_text or ""):
        href_raw, inner = m.group(1), m.group(2)
        title = _WS_RE.sub(" ", _TAG_RE.sub(" ", inner)).strip()
        if len(title) < min_title:
            continue
        href = urljoin(base_url, href_raw)
        if not _same_site(href, domain):
            continue
        if href in seen:
            continue
        # skip obvious non-article chrome
        low = href.lower()
        if any(x in low for x in ("javascript:", "mailto:", "#")):
            continue
        seen.add(href)
        out.append({"title": title, "href": href})
    return out


def _doc_id(organ: str, url: str, title: str) -> str:
    """Stable 16-char id for a document (keep-FIRST key). PURE."""
    basis = f"{organ}|{url}|{title}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# storage — date-keyed parquet, keep-FIRST on doc_id
# --------------------------------------------------------------------------- #
_COLUMNS: tuple[str, ...] = (
    "doc_id", "organ", "organ_name", "title", "url", "body", "body_sha256",
    "seendate", "_crawled_at", "lang", "timestamp_quality", "theme",
    "layout_rank",
)


def _store_dir() -> Path:
    p = config.data_dir() / "china_official"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _day_path(d: date) -> Path:
    return _store_dir() / f"corpus_{d.isoformat()}.parquet"


def write_day(rows: list[dict], d: date) -> Path | None:
    """Append `rows` to the date-keyed parquet for day `d`, keep-FIRST on doc_id.
    Returns the path, or None on failure. Never raises."""
    try:
        if not rows:
            return None
        path = _day_path(d)
        new_df = pd.DataFrame(rows).reindex(columns=list(_COLUMNS))
        if path.exists():
            existing = pd.read_parquet(path).reindex(columns=list(_COLUMNS))
            merged = pd.concat([existing, new_df], ignore_index=True)
        else:
            merged = new_df
        merged = merged.drop_duplicates(subset=["doc_id"], keep="first")
        merged = merged.sort_values(
            ["organ", "layout_rank", "doc_id"]).reset_index(drop=True)
        merged.to_parquet(path, index=False)
        return path
    except Exception as e:  # noqa: BLE001
        log.error("china_official.write_day(%s) failed: %s", d, e)
        return None


def read_corpus(days: int | None = None) -> pd.DataFrame | None:
    """Read the accrued corpus (all date-keyed parquets, or the most recent
    `days`). Returns a concatenated DataFrame sorted by _crawled_at, or None.
    Never raises."""
    try:
        files = sorted(_store_dir().glob("corpus_*.parquet"))
        if not files:
            return None
        if days is not None and days > 0:
            files = files[-days:]
        frames = []
        for f in files:
            try:
                frames.append(pd.read_parquet(f).reindex(columns=list(_COLUMNS)))
            except Exception:  # noqa: BLE001
                continue
        if not frames:
            return None
        out = pd.concat(frames, ignore_index=True)
        out = out.drop_duplicates(subset=["doc_id"], keep="first")
        return out.sort_values(["_crawled_at", "doc_id"]).reset_index(drop=True)
    except Exception as e:  # noqa: BLE001
        log.error("china_official.read_corpus failed: %s", e)
        return None


# --------------------------------------------------------------------------- #
# qbus emit
# --------------------------------------------------------------------------- #
def _to_qbus_rows(rows: list[dict]) -> list[dict]:
    """Map corpus rows → qbus item rows (lang=zh, TIER1, body_sha256 set)."""
    qrows: list[dict] = []
    for r in rows:
        # A document with a parseable publisher date is PUBLISHER_STATED; a bare
        # crawl (People's Daily layout, no in-page date) is CRAWL_BOUNDED. Derive
        # from seendate authoritatively so the qbus tq always agrees with the
        # timestamp we actually have (never trust a possibly-stale stored value).
        tq = "PUBLISHER_STATED" if r.get("seendate") else "CRAWL_BOUNDED"
        qrows.append({
            "desk": "china_official",
            "source": r.get("organ", ""),
            "source_tier": 1,   # 官方 primary sources are TIER1
            "lang": "zh",
            "url": r.get("url", ""),
            "title": r.get("title", ""),
            "body_sha256": r.get("body_sha256", ""),
            "seendate": r.get("seendate", ""),
            "_crawled_at": r.get("_crawled_at", ""),
            "timestamp_quality": tq,
            "entities": [],
            "themes": [r.get("theme")] if r.get("theme") else [],
            "importance_raw": 0.0,
        })
    return qrows


def emit_to_qbus(rows: list[dict]) -> int:
    """Emit corpus rows to the unified qbus item store (keep-FIRST, idempotent).
    Returns the count emitted; 0 on failure. Never raises."""
    if not rows:
        return 0
    try:
        from engine import qbus
        qrows = _to_qbus_rows(rows)
        qbus.append_items(qrows, assign_keys=True)
        return len(qrows)
    except Exception as e:  # noqa: BLE001
        log.warning("china_official: qbus emit failed (%s) — continuing", e)
        return 0


# --------------------------------------------------------------------------- #
# HTTP — paced, checkpointed
# --------------------------------------------------------------------------- #
def _get(url: str, timeout: int = 15) -> tuple[str, str] | None:
    """(decoded_html, content_type) for a URL, or None. Browser UA. Never raises."""
    try:
        import requests
    except Exception:  # noqa: BLE001
        return None
    try:
        r = requests.get(url, timeout=timeout,
                         headers={"User-Agent": _BROWSER_UA,
                                  "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6"})
        if r.status_code != 200 or not r.content:
            return None
        ct = r.headers.get("Content-Type", "")
        return _decode(r.content, ct), ct
    except Exception as e:  # noqa: BLE001
        log.debug("china_official GET %s failed: %s", url, e)
        return None


def _fetch_organ(organ: dict, today: date, cfg: dict,
                 crawled_at: str, pace: float) -> list[dict]:
    """Fetch one organ's recent document leaves → corpus rows. Isolated;
    returns [] on any failure. Paces between leaf fetches (politeness)."""
    max_docs = int(cfg.get("max_docs_per_organ", 12))
    fetch_bodies = bool(cfg.get("fetch_bodies", True))
    is_layout = organ.get("kind") == "layout"

    index_url = _peoples_daily_url(today) if is_layout else organ["url"]
    got = _get(index_url, timeout=int(cfg.get("timeout_s", 15)))
    if got is None:
        log.debug("china_official: index fetch failed for %s", organ["organ"])
        return []
    index_html, _ = got
    links = extract_links(index_html, index_url, organ["domain"],
                          min_title=int(cfg.get("min_title", 6)))[:max_docs]
    if not links:
        return []

    rows: list[dict] = []
    for rank, ln in enumerate(links):
        title = ln["title"]
        url = ln["href"]
        body = ""
        seendate = ""
        if fetch_bodies:
            if pace:
                time.sleep(pace)
            leaf = _get(url, timeout=int(cfg.get("timeout_s", 15)))
            if leaf is not None:
                body = _strip_html(leaf[0])[:int(cfg.get("max_body_chars", 20000))]
                seendate = _doc_date(body) or _doc_date(url)
        seendate = seendate or _doc_date(url)
        tq = "PUBLISHER_STATED" if seendate else "CRAWL_BOUNDED"
        rows.append({
            "doc_id": _doc_id(organ["organ"], url, title),
            "organ": organ["organ"],
            "organ_name": organ["name"],
            "title": title,
            "url": url,
            "body": body,
            "body_sha256": body_sha256(body),
            "seendate": seendate,
            "_crawled_at": crawled_at,
            "lang": "zh",
            "timestamp_quality": tq,
            "theme": organ.get("theme", "policy"),
            # People's Daily front-page order = editorial prominence (D9); -1
            # for organs where order carries no prominence signal.
            "layout_rank": rank if is_layout else -1,
        })
    return rows


class ChinaOfficialCorporaAdapter(Adapter):
    """Fetch → store (date-keyed parquet) → emit to qbus. The runner wraps fetch()
    with retry/breaker; a bad organ degrades to fewer docs, never a crash."""

    name = "china_official_corpora"
    group = "china_official"
    stale_after_days = 4   # policy documents are irregular but multiple/week across 5 organs

    def __init__(self) -> None:
        self.cfg = (config.load().get("china_official", {}) or {})

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        """Fetch the current documents from every organ, persist them to the
        date-keyed parquet, emit to qbus. Returns a summary frame for the runner's
        status reporting. Raises only if EVERY organ failed (a tracked adapter
        failure the circuit breaker sees)."""
        cfg = self.cfg
        if not cfg.get("enabled", True):
            raise RuntimeError("china_official_corpora: disabled in config")

        today = datetime.now().date()
        # _crawled_at stamped ONCE at the ingest boundary (PIT discipline).
        crawled_at = datetime.now(timezone.utc).isoformat()
        pace = float(cfg.get("request_pace_s", 1.0))

        organs = cfg.get("organs") or ORGANS
        all_rows: list[dict] = []
        per_organ: dict[str, int] = {}
        failures = 0
        for organ in organs:
            try:
                rows = _fetch_organ(organ, today, cfg, crawled_at, pace)
                per_organ[organ["organ"]] = len(rows)
                all_rows.extend(rows)
                if not rows:
                    failures += 1
                if pace:
                    time.sleep(pace)   # inter-organ politeness pause
            except Exception as e:  # noqa: BLE001 — per-organ isolation
                failures += 1
                per_organ[organ.get("organ", "?")] = 0
                log.debug("china_official organ %s failed: %s",
                          organ.get("organ"), e)

        if not all_rows:
            raise RuntimeError(
                f"china_official_corpora: no documents fetched across "
                f"{len(organs)} organs ({failures} failures)")

        write_day(all_rows, today)
        n_bus = emit_to_qbus(all_rows)
        log.info("china_official: %d docs across %d organs (%s) → %d qbus",
                 len(all_rows), len(organs), per_organ, n_bus)

        # Summary frame for the runner. The Adapter contract requires a
        # DatetimeIndex so that validate() / store.upsert() can call
        # pd.to_datetime(df.index) without raising a DateParseError.
        # Previous code did .set_index("organ") which left string labels
        # ("state_council", "pboc", …) as the index — causing:
        #   DateParseError: Unknown datetime string format, unable to parse: state_council
        # Fix: pivot so the crawl timestamp is the index and each organ
        # becomes its own numeric column (n_docs_<organ>).
        idx = pd.Timestamp(crawled_at)
        summary = pd.DataFrame(
            {f"n_docs_{k}": [float(v)] for k, v in per_organ.items()},
            index=[idx],
        )
        summary.index.name = "crawled_at"
        return {"china_official_summary": summary}
