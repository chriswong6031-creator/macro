"""Narrative Ignition W2 — data collectors (collect lane only; no scoring math).

Three adapters:
  SubstackRssAdapter    — public RSS poll -> data/narrative/substack_posts.parquet
  HnAlgoliaAdapter      — HN Algolia ticker mentions -> data/narrative/hn_mentions.parquet
  Edgar8kVelocityAdapter — 8-K filing velocity per CIK -> data/narrative/edgar_8k_counts.parquet

All stores are append-only with explicit dedup. Every row carries fetch_date plus the
published/observed date (PIT contract). No auth, no rate-limit violations, no Citrini.

NAR-R10: stale/absent upstream -> log warning + return empty (never crash the pipeline).
Authority: display-tier only; no site/ artifact emitted this wave.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# ── Shared paths ──────────────────────────────────────────────────────────────
_NARRATIVE_DIR = "narrative"

SUBSTACK_PATH   = "substack_posts.parquet"
HN_PATH         = "hn_mentions.parquet"
EDGAR_8K_PATH   = "edgar_8k_counts.parquet"

# SEC fair-access User-Agent (matches edgar_8k.py pattern)
_SEC_UA = "macro-dashboard admin@macro-dashboard.example.com"
# Public RSS / HN UA
_PUBLIC_UA = "macro-dashboard-narrative/1.0 (research; public data only)"

# ── Registry loader ───────────────────────────────────────────────────────────

def _load_registry() -> dict:
    """Load config/narrative_sources.yml."""
    yml_path = Path(config.ROOT) / "config" / "narrative_sources.yml"
    if not yml_path.exists():
        raise FileNotFoundError(f"narrative_sources.yml not found: {yml_path}")
    import yaml  # noqa: PLC0415
    with yml_path.open() as f:
        return yaml.safe_load(f) or {}


def _narrative_dir() -> Path:
    p = config.data_dir() / _NARRATIVE_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── SubstackRssAdapter ────────────────────────────────────────────────────────

_SUBSTACK_COLS = ["feed_id", "url", "title", "published_date", "teaser_text", "fetch_date"]

_TEASER_MAX = 2048  # chars; NAR-R11 public content only


def _parse_rss(xml_text: str, feed_id: str, fetch_date: str) -> list[dict]:
    """Parse an RSS feed into rows. Returns [] on any parse error."""
    rows: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log.warning("narrative/rss: feed_id=%s XML parse error: %s", feed_id, exc)
        return rows

    # Handle both RSS 2.0 (<channel><item>) and Atom (<entry>)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = root.findall(".//item") or root.findall(".//atom:entry", ns)

    for item in items:
        def _text(tag: str, ns_tag: str | None = None) -> str:
            el = item.find(tag)
            if el is None and ns_tag:
                el = item.find(ns_tag, ns)
            return (el.text or "").strip() if el is not None else ""

        url   = _text("link") or _text("atom:link", "atom:link")
        # Atom <link> can be an attribute, not text
        if not url:
            link_el = item.find("atom:link", ns)
            if link_el is not None:
                url = link_el.get("href", "")
        title = _text("title")
        pub_raw = _text("pubDate") or _text("published") or _text("atom:published", "atom:published")
        desc  = _text("description") or _text("summary") or _text("atom:summary", "atom:summary")

        # Parse published_date
        pub_date: str | None = None
        if pub_raw:
            for fmt in (None,):  # try parsedate_to_datetime (RFC 2822 / ISO 8601)
                try:
                    pub_date = parsedate_to_datetime(pub_raw).strftime("%Y-%m-%d")
                    break
                except Exception:  # noqa: BLE001
                    pass
            if pub_date is None:
                # Fallback: try ISO8601 prefix
                try:
                    pub_date = pub_raw[:10]
                    datetime.strptime(pub_date, "%Y-%m-%d")
                except Exception:  # noqa: BLE001
                    pub_date = None

        if not url or not title:
            continue

        rows.append({
            "feed_id":       feed_id,
            "url":           url,
            "title":         title[:512],
            "published_date": pub_date,
            "teaser_text":   desc[:_TEASER_MAX],
            "fetch_date":    fetch_date,
        })
    return rows


class SubstackRssAdapter:
    """Poll public Substack RSS feeds -> data/narrative/substack_posts.parquet.

    Append-only; dedup on (feed_id, url). No auth; polite (serialized + timeout).
    Forward-only: first run captures posts available today; no backfill.
    NAR-R10: a failed feed is logged and skipped; the store is not corrupted.
    """

    name = "narrative_substack_rss"

    def fetch(self, timeout: int = 30, pace_s: float = 1.0) -> pd.DataFrame:
        """Fetch all configured RSS feeds. Returns new rows DataFrame."""
        import requests  # noqa: PLC0415

        reg = _load_registry()
        feeds = reg.get("substack_rss") or []
        if not feeds:
            log.warning("narrative/substack_rss: no feeds in registry")
            return pd.DataFrame(columns=_SUBSTACK_COLS)

        fetch_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        all_rows: list[dict] = []

        for feed in feeds:
            feed_id = feed.get("feed_id", "")
            rss_url = feed.get("rss_url", "")
            if not feed_id or not rss_url:
                continue
            try:
                r = requests.get(
                    rss_url,
                    timeout=timeout,
                    headers={"User-Agent": _PUBLIC_UA},
                )
                r.raise_for_status()
                rows = _parse_rss(r.text, feed_id, fetch_date)
                log.info("narrative/substack_rss: feed_id=%s rows=%d", feed_id, len(rows))
                all_rows.extend(rows)
            except Exception as exc:  # noqa: BLE001 — NAR-R10: never crash
                log.warning("narrative/substack_rss: feed_id=%s failed: %s", feed_id, exc)
            time.sleep(pace_s)

        new_df = pd.DataFrame(all_rows, columns=_SUBSTACK_COLS) if all_rows else pd.DataFrame(columns=_SUBSTACK_COLS)
        return self._upsert(new_df)

    def _upsert(self, new_df: pd.DataFrame) -> pd.DataFrame:
        """Append-only dedup on (feed_id, url). Returns total stored frame."""
        store_path = _narrative_dir() / SUBSTACK_PATH
        if store_path.exists():
            try:
                existing = pd.read_parquet(store_path)
            except Exception as exc:  # noqa: BLE001
                log.warning("narrative/substack_rss: corrupt store, rebuilding: %s", exc)
                existing = pd.DataFrame(columns=_SUBSTACK_COLS)
        else:
            existing = pd.DataFrame(columns=_SUBSTACK_COLS)

        if new_df.empty:
            return existing

        combined = pd.concat([existing, new_df], ignore_index=True)
        # Keep first occurrence per (feed_id, url) so existing stable rows are not overwritten
        combined = combined.drop_duplicates(subset=["feed_id", "url"], keep="first")
        combined = combined.reset_index(drop=True)
        combined.to_parquet(store_path, index=False)
        n_new = len(combined) - len(existing)
        log.info("narrative/substack_rss: +%d new rows (%d total)", max(n_new, 0), len(combined))
        return combined


# ── HnAlgoliaAdapter ─────────────────────────────────────────────────────────

_HN_COLS = ["ticker", "story_id", "title", "points", "num_comments", "created_at", "fetch_date"]
_HN_ALGOLIA_URL = "https://hn.algolia.com/api/v1/search"


def _query_hn(keyword: str, since_ts: int, timeout: int = 20) -> list[dict]:
    """Query HN Algolia for one keyword, return raw hit list. Returns [] on failure."""
    import requests  # noqa: PLC0415
    params = {
        "query": keyword,
        "tags": "story",
        "numericFilters": f"created_at_i>{since_ts}",
        "hitsPerPage": 100,
    }
    try:
        r = requests.get(
            _HN_ALGOLIA_URL,
            params=params,
            timeout=timeout,
            headers={"User-Agent": _PUBLIC_UA},
        )
        r.raise_for_status()
        return (r.json() or {}).get("hits") or []
    except Exception as exc:  # noqa: BLE001
        log.warning("narrative/hn: query=%r failed: %s", keyword, exc)
        return []


class HnAlgoliaAdapter:
    """HN Algolia story mentions -> data/narrative/hn_mentions.parquet.

    For each ticker's keyword set, queries the last 2 days of stories (nightly window).
    Dedup on (story_id, ticker). Points and num_comments are snapshot-at-fetch (not PIT
    historically, but each row carries the fetch_date for staleness tracking).
    """

    name = "narrative_hn_algolia"

    def fetch(self, window_days: int = 2, pace_s: float = 0.5) -> pd.DataFrame:
        """Fetch HN mentions for all registered tickers. Returns new rows DataFrame."""
        reg = _load_registry()
        hn_map: dict[str, list[str]] = reg.get("hn_keywords") or {}
        if not hn_map:
            log.warning("narrative/hn: no hn_keywords in registry")
            return pd.DataFrame(columns=_HN_COLS)

        fetch_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        since_ts = int((datetime.now(timezone.utc) - timedelta(days=window_days)).timestamp())

        all_rows: list[dict] = []
        for ticker, keywords in hn_map.items():
            seen_ids: set[str] = set()
            for kw in keywords:
                hits = _query_hn(kw, since_ts)
                for h in hits:
                    sid = str(h.get("objectID") or "")
                    if not sid or sid in seen_ids:
                        continue
                    seen_ids.add(sid)
                    created_raw = h.get("created_at") or ""
                    # created_at is ISO 8601 string
                    try:
                        created_at = datetime.fromisoformat(
                            created_raw.replace("Z", "+00:00")
                        ).strftime("%Y-%m-%dT%H:%M:%SZ")
                    except Exception:  # noqa: BLE001
                        created_at = created_raw[:20] if created_raw else None
                    all_rows.append({
                        "ticker":       ticker,
                        "story_id":     sid,
                        "title":        (h.get("title") or "")[:512],
                        "points":       int(h.get("points") or 0),
                        "num_comments": int(h.get("num_comments") or 0),
                        "created_at":   created_at,
                        "fetch_date":   fetch_date,
                    })
                time.sleep(pace_s)

        new_df = pd.DataFrame(all_rows, columns=_HN_COLS) if all_rows else pd.DataFrame(columns=_HN_COLS)
        return self._upsert(new_df)

    def _upsert(self, new_df: pd.DataFrame) -> pd.DataFrame:
        """Append-only dedup on (story_id, ticker). Returns total stored frame."""
        store_path = _narrative_dir() / HN_PATH
        if store_path.exists():
            try:
                existing = pd.read_parquet(store_path)
            except Exception as exc:  # noqa: BLE001
                log.warning("narrative/hn: corrupt store, rebuilding: %s", exc)
                existing = pd.DataFrame(columns=_HN_COLS)
        else:
            existing = pd.DataFrame(columns=_HN_COLS)

        if new_df.empty:
            return existing

        combined = pd.concat([existing, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["story_id", "ticker"], keep="first")
        combined = combined.reset_index(drop=True)
        combined.to_parquet(store_path, index=False)
        n_new = len(combined) - len(existing)
        log.info("narrative/hn: +%d new rows (%d total)", max(n_new, 0), len(combined))
        return combined


# ── Edgar8kVelocityAdapter ────────────────────────────────────────────────────

_EDGAR_COLS = ["ticker", "date", "n_8k", "fetch_date"]
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{:010d}.json"
_PACE_S = 0.12  # SEC fair-access <=10 req/s


def _sec_get_json(url: str, retries: int = 3, timeout: int = 30) -> dict | None:
    """Fetch a JSON URL with SEC fair-access UA. Returns None on failure."""
    import requests  # noqa: PLC0415
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(
                url,
                headers={"User-Agent": _SEC_UA, "Accept-Encoding": "gzip, deflate"},
                timeout=timeout,
            )
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    log.warning("edgar_8k_velocity: GET %s failed: %s", url, last)
    return None


def _company_tickers_map() -> dict[str, int]:
    """Build ticker->CIK map from cached company_tickers.json. Returns {} on failure."""
    cache = config.data_dir() / "edgar" / "company_tickers.json"
    if not cache.exists():
        log.warning("edgar_8k_velocity: company_tickers.json absent — CIK map empty")
        return {}
    try:
        data = json.loads(cache.read_text())
    except Exception as exc:  # noqa: BLE001
        log.warning("edgar_8k_velocity: could not parse company_tickers.json: %s", exc)
        return {}
    out: dict[str, int] = {}
    for row in data.values():
        tk = (row.get("ticker") or "").upper()
        cik = row.get("cik_str")
        if tk and cik:
            out[tk] = int(cik)
    return out


def _sp1500_universe() -> list[str]:
    """SP1500 large-cap-first universe from breadth constituents + basket membership.

    Mirrors the pattern used by polygon_news._breadth_universe_ranked().
    Returns deduplicated list (large-cap first).
    """
    ranked: list[str] = []
    seen: set[str] = set()
    for grp in ("breadth", "midcap_breadth", "smallcap_breadth"):
        p = config.data_dir() / grp / "constituents.parquet"
        if not p.exists():
            continue
        try:
            tickers = sorted(pd.read_parquet(p).index.astype(str))
        except Exception:  # noqa: BLE001
            continue
        for t in tickers:
            if t not in seen:
                seen.add(t)
                ranked.append(t)
    # Also include basket membership (for narrative-specific names)
    mem_path = config.data_dir() / "baskets" / "membership.json"
    if mem_path.exists():
        try:
            mem = json.loads(mem_path.read_text()).get("baskets", {})
            for b in mem.values():
                for m in b.get("members", []):
                    t = m.get("ticker")
                    if t and not m.get("removed") and t not in seen:
                        seen.add(t)
                        ranked.append(t)
        except Exception:  # noqa: BLE001
            pass
    return ranked


def _count_8ks_for_cik(cik: int, lookback_days: int) -> dict[str, int]:
    """Fetch EDGAR submissions for a CIK; return {date_str: n_8k} for 8-K filings
    within the lookback window. Returns {} on network failure (NAR-R10)."""
    data = _sec_get_json(_SUBMISSIONS_URL.format(cik))
    if not data:
        return {}
    rec = (data.get("filings") or {}).get("recent") or {}
    forms      = rec.get("form") or []
    file_dates = rec.get("filingDate") or []
    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()
    counts: dict[str, int] = {}
    for form, fd in zip(forms, file_dates):
        if form == "8-K" and fd >= cutoff:
            counts[fd] = counts.get(fd, 0) + 1
    return counts


class Edgar8kVelocityAdapter:
    """8-K filing velocity per ticker/day -> data/narrative/edgar_8k_counts.parquet.

    Uses the SP1500 large-cap slice (matching the polygon_news tiering).
    Stores (ticker, date, n_8k, fetch_date). Append-only; dedup on (ticker, date).
    NAR-R10: missing CIK or network failure -> skip ticker, log warning, never crash.
    """

    name = "narrative_edgar_8k_velocity"

    def fetch(self, lookback_days: int = 90) -> pd.DataFrame:
        """Fetch 8-K counts for the universe. Returns total stored frame."""
        reg = _load_registry()
        cfg_eb = reg.get("edgar_8k_velocity") or {}
        lookback_days = int(cfg_eb.get("lookback_days", lookback_days))
        pace_s = float(cfg_eb.get("pace_s", _PACE_S))

        universe = _sp1500_universe()
        if not universe:
            log.warning("edgar_8k_velocity: empty universe — no breadth/basket stores found")
            return pd.DataFrame(columns=_EDGAR_COLS)

        cik_map = _company_tickers_map()
        if not cik_map:
            log.warning("edgar_8k_velocity: CIK map empty — cannot fetch 8-K counts")
            return pd.DataFrame(columns=_EDGAR_COLS)

        fetch_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        all_rows: list[dict] = []
        mapped = 0

        for ticker in universe:
            cik = cik_map.get(ticker.upper())
            if cik is None:
                continue
            mapped += 1
            counts = _count_8ks_for_cik(cik, lookback_days)
            for d, n in counts.items():
                all_rows.append({
                    "ticker":     ticker,
                    "date":       d,
                    "n_8k":       n,
                    "fetch_date": fetch_date,
                })
            time.sleep(pace_s)

        log.info(
            "edgar_8k_velocity: universe=%d mapped=%d rows=%d",
            len(universe), mapped, len(all_rows),
        )
        new_df = pd.DataFrame(all_rows, columns=_EDGAR_COLS) if all_rows else pd.DataFrame(columns=_EDGAR_COLS)
        return self._upsert(new_df)

    def _upsert(self, new_df: pd.DataFrame) -> pd.DataFrame:
        """Append-only dedup on (ticker, date). Returns total stored frame."""
        store_path = _narrative_dir() / EDGAR_8K_PATH
        if store_path.exists():
            try:
                existing = pd.read_parquet(store_path)
            except Exception as exc:  # noqa: BLE001
                log.warning("edgar_8k_velocity: corrupt store, rebuilding: %s", exc)
                existing = pd.DataFrame(columns=_EDGAR_COLS)
        else:
            existing = pd.DataFrame(columns=_EDGAR_COLS)

        if new_df.empty:
            return existing

        combined = pd.concat([existing, new_df], ignore_index=True)
        # Keep the most-recent fetch for each (ticker, date) so count updates on re-runs
        combined = combined.sort_values("fetch_date").drop_duplicates(
            subset=["ticker", "date"], keep="last"
        )
        combined = combined.reset_index(drop=True)
        combined.to_parquet(store_path, index=False)
        n_new = len(combined) - len(existing)
        log.info("edgar_8k_velocity: +%d net rows (%d total)", max(n_new, 0), len(combined))
        return combined
