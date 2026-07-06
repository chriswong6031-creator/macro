"""CNInfo A-share filing / announcement metadata collector (W3.2).

Metadata-only (RUL-4): title, category, ticker, URL, publish-time.
No PDF bodies are ever fetched. Store: data/china_filings/filings.parquet,
keep-FIRST on announcementId. Full stream ~700K rows/yr; this PR collects
forward-only (last 7 days, idempotent re-pull).

VERIFIED ENDPOINT (both SSE + SZSE, including inquiry letters):
    POST http://www.cninfo.com.cn/new/hisAnnouncement/query
    Content-Type: application/x-www-form-urlencoded
    column=sse|szse, tabName=fulltext, seDate=YYYY-MM-DD~YYYY-MM-DD
Response: totalAnnouncement, totalpages, hasMore, announcements[]

Category normalizer: title-keyword → category. Priority order is encoded in
CATEGORY_PRIORITY so investigation > inquiry_letter > other. First-match-wins.

Pacing: 1.5 s + jitter between page requests.
"""
from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

# ------------------------------------------------------------------ constants --

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_REFERER = (
    "http://www.cninfo.com.cn/new/commonUrl/pageByCode"
    "?code=cninfo-tips-announcement"
)
_ENDPOINT = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
_PAGE_SIZE = 30
_NIGHTLY_LOOKBACK_DAYS = 3   # idempotent re-pull: previous 3 calendar days
_INITIAL_LOOKBACK_DAYS = 7   # first-run bootstrap: last 7 days
_PACE_S = 1.5
_JITTER_S = 0.4              # ± uniform jitter on top of _PACE_S

_EXCHANGES = ("sse", "szse")

# ------------------------------------------------------------------ parquet store --

_COLUMNS = (
    "announcementId",
    "sec_code",
    "sec_name",
    "org_id",
    "title",
    "publish_ts",       # ISO8601, Asia/Shanghai timezone
    "exchange",
    "category",
    "kind",             # nullable; non-null only for inquiry_letter family
    "announcement_type_raw",
    "adjunct_url",
    "adjunct_type",
    "_collected_at",
)


def _store_path() -> Path:
    p = config.data_dir() / "china_filings"
    p.mkdir(parents=True, exist_ok=True)
    return p / "filings.parquet"


def load_filings() -> pd.DataFrame:
    """Read existing parquet, or return an empty frame with the canonical schema."""
    path = _store_path()
    if path.exists():
        try:
            return pd.read_parquet(path).reindex(columns=list(_COLUMNS))
        except Exception as e:  # noqa: BLE001
            log.warning("china_filings: could not read existing parquet: %s", e)
    return pd.DataFrame(columns=list(_COLUMNS))


def write_filings(new_rows: list[dict]) -> int:
    """Append rows to filings.parquet, keep-FIRST on announcementId.

    Returns the count of net-new rows written (0 when all duplicates).
    Never raises — failures are logged and silently skipped.
    """
    if not new_rows:
        return 0
    try:
        path = _store_path()
        new_df = pd.DataFrame(new_rows).reindex(columns=list(_COLUMNS))
        existing = load_filings()
        if existing.empty:
            # No existing store: dedup within the new batch itself, then write.
            merged = new_df.drop_duplicates(subset=["announcementId"], keep="first")
            net_new = len(merged)
        else:
            pre_count = existing["announcementId"].nunique()
            merged = pd.concat([existing, new_df], ignore_index=True)
            merged = merged.drop_duplicates(subset=["announcementId"], keep="first")
            post_count = merged["announcementId"].nunique()
            net_new = post_count - pre_count
        merged = merged.sort_values(
            ["publish_ts", "announcementId"], na_position="last"
        ).reset_index(drop=True)
        merged.to_parquet(path, index=False)
        return net_new
    except Exception as e:  # noqa: BLE001
        log.error("china_filings.write_filings failed: %s", e)
        return 0


# ------------------------------------------------------------------ category normalizer --

# Priority-ordered list: (category_key, [zh_keywords]).
# First match wins. Higher entries outrank lower ones.
# Rationale for order: investigation > inquiry_letter rank above generic
# operational categories (buyback, pledge) so that a filing that is both an
# inquiry letter AND mentions 回购 is classified as inquiry_letter, not buyback.
CATEGORY_PRIORITY: list[tuple[str, list[str]]] = [
    ("investigation",       ["立案"]),
    ("inquiry_letter",      ["问询函", "监管函", "关注函"]),
    ("delisting_risk",      ["退市"]),
    ("earnings_preann",     ["业绩预告", "预增", "预减", "预盈", "预亏", "业绩快报"]),
    ("restructuring",       ["重组", "重大资产"]),
    ("major_contract",      ["重大合同", "中标"]),
    ("buyback",             ["回购"]),
    ("pledge",              ["质押"]),
    ("holder_change_down",  ["减持"]),
    ("holder_change_up",    ["增持"]),
]
_OTHER = "other"

# Inquiry-family kind sub-classification keywords.
# Precedence (first-match-wins within the inquiry family):
#   attachment (专项说明/核查意见) > reply (回函/回复/答复) > letter (exchange-issued, default)
# kind is None for all non-inquiry_letter categories.
_KIND_ATTACHMENT_KW = ("专项说明", "核查意见", "专项核查意见")
_KIND_REPLY_KW = ("回函", "回复", "答复")


def classify_kind(title: str) -> str | None:
    """Return the inquiry-letter sub-kind for a title, or None if not applicable.

    Only called when the enclosing category is 'inquiry_letter'. Within that
    family precedence is: attachment > reply > letter (default).

      'letter'     — exchange-issued inquiry (问询函/监管函/关注函), the default
      'reply'      — company reply (回函/回复/答复)
      'attachment' — third-party verification / specialist note (专项说明/核查意见)

    Pure function; unit-testable without any I/O.
    """
    if any(kw in title for kw in _KIND_ATTACHMENT_KW):
        return "attachment"
    if any(kw in title for kw in _KIND_REPLY_KW):
        return "reply"
    return "letter"


def categorize(title: str) -> str:
    """Map an announcement title to a category key (first-match-wins).

    Priority order: investigation > inquiry_letter > delisting_risk >
    earnings_preann > restructuring > major_contract > buyback > pledge >
    holder_change_down > holder_change_up > other.

    Pure function; unit-testable without any I/O.
    """
    for category, keywords in CATEGORY_PRIORITY:
        if any(kw in title for kw in keywords):
            return category
    return _OTHER


# ------------------------------------------------------------------ HTTP --

def _headers() -> dict:
    return {
        "User-Agent": _BROWSER_UA,
        "Referer": _REFERER,
        "Content-Type": "application/x-www-form-urlencoded",
    }


def _pace() -> None:
    """Sleep _PACE_S + uniform jitter (politeness)."""
    time.sleep(_PACE_S + random.uniform(-_JITTER_S, _JITTER_S))  # noqa: S311


def _unix_ms_to_iso(ts_ms: int | float | None) -> str:
    """Convert Unix-millisecond timestamp to ISO8601 Asia/Shanghai string.

    Returns '' on any failure (malformed row should not crash the collector).
    Pure except for timezone import.
    """
    if ts_ms is None:
        return ""
    try:
        from zoneinfo import ZoneInfo  # noqa: PLC0415 — lazy
        tz = ZoneInfo("Asia/Shanghai")
        dt = datetime.fromtimestamp(float(ts_ms) / 1000.0, tz=tz)
        return dt.isoformat()
    except Exception:  # noqa: BLE001
        return ""


def _fetch_page(
    exchange: str,
    date_range: str,
    page_num: int,
    session,
) -> dict:
    """POST one page to the CNInfo endpoint. Returns the parsed JSON dict.

    Raises on HTTP error or JSON parse failure so the per-exchange try/except
    in the caller can isolate the exchange.
    """
    data = (
        f"pageNum={page_num}&pageSize={_PAGE_SIZE}"
        f"&column={exchange}&tabName=fulltext"
        f"&plate=&stock=&searchkey=&secid=&category=&trade="
        f"&seDate={date_range}&sortName=&sortType=&isHLtitle=True"
    )
    r = session.post(
        _ENDPOINT,
        data=data,
        headers=_headers(),
        timeout=30,
    )
    if r.status_code in (429, 500, 502, 503, 504):
        raise IOError(f"HTTP {r.status_code} from CNInfo exchange={exchange}")
    r.raise_for_status()
    return r.json()


def _parse_announcement(ann: dict, exchange: str, collected_at: str) -> dict:
    """Map one raw announcement dict → canonical row dict. Pure (no I/O)."""
    title = ann.get("announcementTitle") or ""
    ts_ms = ann.get("announcementTime")
    cat = categorize(title)
    kind: str | None = classify_kind(title) if cat == "inquiry_letter" else None
    return {
        "announcementId": ann.get("announcementId", ""),
        "sec_code": ann.get("secCode", ""),
        "sec_name": ann.get("secName", ""),
        "org_id": ann.get("orgId", ""),
        "title": title,
        "publish_ts": _unix_ms_to_iso(ts_ms),
        "exchange": exchange,
        "category": cat,
        "kind": kind,
        "announcement_type_raw": ann.get("announcementType", ""),
        "adjunct_url": ann.get("adjunctUrl", ""),  # relative path — stored as-is, NEVER fetched
        "adjunct_type": ann.get("adjunctType", ""),
        "_collected_at": collected_at,
    }


# ------------------------------------------------------------------ adapter --

class ChinaFilingsAdapter(Adapter):
    """CNInfo A-share filing / announcement metadata collector.

    Nightly: queries the last _NIGHTLY_LOOKBACK_DAYS calendar days from both
    SSE and SZSE. Each exchange is isolated in its own try/except so a CNInfo
    temporary outage on one exchange never sinks the other. Results are
    deduplicated by announcementId (keep-FIRST) and stored to a single
    filings.parquet.

    The adapter returns a summary DataFrame with a DatetimeIndex (required by
    the base validate() / store.upsert() contract — see china_official_corpora
    fix for precedent).
    """

    name = "china_filings"
    group = "china_filings"  # auto-routed to asia lane by 'china_' prefix
    stale_after_days = 4     # filings are released daily; >4 days = stale

    def _date_range(self, full_history: bool = False) -> str:
        """Return the seDate range string 'YYYY-MM-DD~YYYY-MM-DD'."""
        today = datetime.now(timezone.utc).date()
        lookback = _INITIAL_LOOKBACK_DAYS if full_history else _NIGHTLY_LOOKBACK_DAYS
        start = today - timedelta(days=lookback)
        return f"{start.isoformat()}~{today.isoformat()}"

    def _fetch_exchange(
        self,
        exchange: str,
        date_range: str,
        session,
        collected_at: str,
    ) -> list[dict]:
        """Paginate through all announcement pages for one exchange.

        Each page is paced at 1.5 s + jitter. Returns a list of canonical row dicts.
        Raises on persistent failure so the per-exchange isolation in fetch() fires.
        """
        rows: list[dict] = []
        page_num = 1
        while True:
            payload = _fetch_page(exchange, date_range, page_num, session)
            anns = payload.get("announcements") or []
            for ann in anns:
                rows.append(_parse_announcement(ann, exchange, collected_at))

            total_pages = int(payload.get("totalpages") or 1)
            # Terminate only when we have consumed all pages per totalpages.
            # hasMore is NOT used as a termination guard: CNInfo's hisAnnouncement
            # endpoint returns hasMore=false inconsistently mid-pagination (known
            # CNInfo quirk), so `or not has_more` would silently truncate a
            # multi-page day to only the first 30 rows.
            if page_num >= total_pages:
                break
            page_num += 1
            _pace()

        log.info(
            "china_filings: exchange=%s date_range=%s pages=%d rows=%d",
            exchange, date_range, page_num, len(rows),
        )
        return rows

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        """Fetch filing metadata from SSE + SZSE, store, return summary frame.

        Per-exchange try/except isolation: one exchange failure never kills the
        other. Raises only when BOTH exchanges fail (circuit breaker sees it).

        Returns a summary DataFrame with a DatetimeIndex (required by the
        base.validate() contract — must be pd.to_datetime-parseable).
        """
        import requests  # lazy import

        date_range = self._date_range(full_history)
        collected_at = datetime.now(timezone.utc).isoformat()

        session = requests.Session()
        all_rows: list[dict] = []
        per_exchange: dict[str, int] = {}
        errors: list[str] = []

        for exchange in _EXCHANGES:
            try:
                rows = self._fetch_exchange(
                    exchange, date_range, session, collected_at
                )
                per_exchange[exchange] = len(rows)
                all_rows.extend(rows)
                _pace()  # inter-exchange pause
            except Exception as e:  # noqa: BLE001 — per-exchange isolation
                errors.append(f"{exchange}: {e}")
                per_exchange[exchange] = 0
                log.warning(
                    "china_filings: exchange=%s failed: %s", exchange, e
                )

        if not all_rows and errors:
            raise RuntimeError(
                "china_filings: all exchanges failed — " + " | ".join(errors)
            )

        net_new = write_filings(all_rows)
        log.info(
            "china_filings: %d raw rows collected, %d net-new stored (%s)",
            len(all_rows), net_new, per_exchange,
        )

        # Summary frame — DatetimeIndex is required by base.validate() /
        # store.upsert(). Follow china_official_corpora precedent (line 468):
        # strip tz-awareness so the index is tz-naive.  Mixing tz-aware with
        # any tz-naive parquet already on disk causes combine_first to raise
        # "Cannot join tz-naive with tz-aware DatetimeIndex".
        idx = pd.Timestamp(collected_at).tz_convert(None)
        summary = pd.DataFrame(
            {f"n_rows_{ex}": [float(per_exchange.get(ex, 0))]
             for ex in _EXCHANGES},
            index=[idx],
        )
        summary["n_rows_total"] = float(len(all_rows))
        summary["n_net_new"] = float(net_new)
        summary.index.name = "collected_at"
        return {"china_filings_summary": summary}


# ------------------------------------------------------------------ CLI (backfill) --

def _cli_backfill(start: str, end: str, categories: list[str]) -> None:
    """Backfill filing metadata for a date range, optionally filtered by category.

    Designed for targeted manual backfills (inquiry_letter + earnings_preann
    only). DOES NOT run as part of nightly — invoke manually on the Mac.

    Usage:
        python -m collectors.china_filings --backfill 2024-01-01 2024-12-31 \\
            --categories inquiry_letter,earnings_preann
    """
    import requests  # lazy

    log.info(
        "china_filings backfill: start=%s end=%s categories=%s",
        start, end, categories,
    )
    date_range = f"{start}~{end}"
    collected_at = datetime.now(timezone.utc).isoformat()
    session = requests.Session()

    adapter = ChinaFilingsAdapter()
    all_rows: list[dict] = []
    for exchange in _EXCHANGES:
        try:
            rows = adapter._fetch_exchange(
                exchange, date_range, session, collected_at
            )
            if categories:
                rows = [r for r in rows if r["category"] in categories]
            all_rows.extend(rows)
            log.info("china_filings backfill: %s → %d rows", exchange, len(rows))
            _pace()
        except Exception as e:  # noqa: BLE001
            log.warning(
                "china_filings backfill: exchange=%s failed: %s", exchange, e
            )

    net_new = write_filings(all_rows)
    print(
        f"Backfill complete: {len(all_rows)} rows fetched, "
        f"{net_new} net-new written."
    )


if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO)
    p = argparse.ArgumentParser(description="CNInfo filings collector CLI")
    p.add_argument("--backfill", nargs=2, metavar=("START", "END"),
                   help="Backfill date range YYYY-MM-DD YYYY-MM-DD")
    p.add_argument("--categories", default="",
                   help="Comma-separated categories to keep (empty = all)")
    p.add_argument("--full-history", action="store_true",
                   help="Nightly run with extended lookback (7 days)")
    args = p.parse_args()

    if args.backfill:
        start_date, end_date = args.backfill
        cats = [c.strip() for c in args.categories.split(",") if c.strip()]
        _cli_backfill(start_date, end_date, cats)
        sys.exit(0)

    # Default: run nightly adapter
    from collectors.base import run_adapter
    result = run_adapter(ChinaFilingsAdapter(), full_history=args.full_history)
    print(f"status={result.status} rows={result.rows} last_date={result.last_date}")
    if result.error:
        print(f"error={result.error}", file=sys.stderr)
        sys.exit(1)
