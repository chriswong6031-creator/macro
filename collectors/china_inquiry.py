"""Exchange inquiry-letter collector for A-share names (CNInfo public endpoint).

Exchange inquiry letters (问询函/关注函) are regulatory enquiries from SZSE/SSE asking
companies to explain material disclosures, unusual financial moves, or news-price
divergences. Both the original letters and company replies are significant events:
  - Original letters (kind='letter')  flag a regulator concern before any resolution.
  - Company replies  (kind='reply')   indicate the company has acknowledged the enquiry.

akshare's inquiry wrapper has a persistent KeyError bug so we go direct to the CNInfo
public announcements API (the same endpoint the scout verified works without auth):
  POST http://www.cninfo.com.cn/new/hisAnnouncement/query
  form fields mirror the akshare source minimally.

Rolling 30-day window, cap 10 pages × 30 results = 300 rows per run.

Stored under data/china_inquiry/inquiry.parquet
({secCode, secName, announcementTitle, announcementTime (date), adjunctUrl, kind, asof}).

METADATA ONLY — PDFs are not downloaded; the page links to the CNInfo PDF adjunctUrl.
CONTEXT-ONLY. No body text extracted; no sentiment scored.
"""
from __future__ import annotations

import logging
import time
from datetime import date, timedelta

import pandas as pd

from lib import config

log = logging.getLogger("china_inquiry")

OUT = config.data_dir() / "china_inquiry" / "inquiry.parquet"

_CNINFO_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
_HEADERS = {
    "Referer": "http://www.cninfo.com.cn",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/x-www-form-urlencoded",
}
_PAGE_SIZE = 30
_MAX_PAGES = 10


def _col(cols: list[str], *needles: str) -> str | None:
    for c in cols:
        s = str(c)
        if all(n in s for n in needles):
            return c
    return None


def _classify_kind(title: str) -> str:
    """Classify announcement as original letter or company reply."""
    if not title:
        return "letter"
    t = str(title)
    if any(k in t for k in ("回复", "回复的公告", "关于回复", "复函")):
        return "reply"
    return "letter"


def _epoch_ms_to_date(ms) -> str | None:
    """Convert epoch-ms timestamp to YYYY-MM-DD string."""
    try:
        return pd.Timestamp(int(ms), unit="ms").strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return None


def _fetch_page(se_date: str, page_num: int) -> list[dict]:
    """Fetch one page of inquiry letters from CNInfo. Returns list of raw announcement dicts."""
    import requests
    data = {
        "column": "szse",
        "pageNum": str(page_num),
        "pageSize": str(_PAGE_SIZE),
        "searchkey": "问询函",
        "seDate": se_date,
        "stock": "",
        "tabName": "fulltext",
        "category": "",
        "plate": "",
        "isFRii": "true",
    }
    try:
        r = requests.post(_CNINFO_URL, headers=_HEADERS, data=data, timeout=15)
        r.raise_for_status()
        payload = r.json()
        announcements = payload.get("announcements") or []
        return announcements if isinstance(announcements, list) else []
    except Exception as e:  # noqa: BLE001
        log.warning("china inquiry: page %d fetch failed (%s)", page_num, e)
        return []


def refresh() -> int:
    """Fetch 30-day rolling window of inquiry letters + replies. Returns rows written (0 on failure)."""
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")

    # Idempotency
    if OUT.exists():
        try:
            if str(pd.read_parquet(OUT, columns=["asof"])["asof"].max()) >= today_str:
                log.info("china inquiry: cache already fresh (%s)", today_str)
                return 0
        except Exception:  # noqa: BLE001
            pass

    start_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    se_date = f"{start_date}~{today_str}"

    rows: list[dict] = []
    for page in range(1, _MAX_PAGES + 1):
        page_rows = _fetch_page(se_date, page)
        if not page_rows:
            break
        rows.extend(page_rows)
        time.sleep(1.2)
        if len(page_rows) < _PAGE_SIZE:
            # last page
            break

    if not rows:
        log.info("china inquiry: no results for window %s", se_date)
        # write empty parquet so idempotency works
        empty = pd.DataFrame(columns=["secCode", "secName", "announcementTitle",
                                       "announcementTime", "adjunctUrl",
                                       "announcementTypeName", "kind", "asof"])
        OUT.parent.mkdir(parents=True, exist_ok=True)
        empty.to_parquet(OUT, index=False)
        return 0

    records = []
    for ann in rows:
        sec_code  = str(ann.get("secCode")  or "")
        sec_name  = str(ann.get("secName")  or "")
        title     = str(ann.get("announcementTitle") or "")
        ann_time  = _epoch_ms_to_date(ann.get("announcementTime"))
        adj_url   = str(ann.get("adjunctUrl") or "")
        type_name = str(ann.get("announcementTypeName") or "")
        kind      = _classify_kind(title)
        records.append({
            "secCode":           sec_code,
            "secName":           sec_name,
            "announcementTitle": title,
            "announcementTime":  ann_time,
            "adjunctUrl":        adj_url,
            "announcementTypeName": type_name,
            "kind":              kind,
            "asof":              today_str,
        })

    df = pd.DataFrame(records)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    log.info("china inquiry: wrote %d rows (window %s) → %s", len(df), se_date, OUT)
    return len(df)


def main() -> int:
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    argparse.ArgumentParser(description="Fetch CNInfo exchange inquiry letters").parse_args()
    n = refresh()
    return 0 if n >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
