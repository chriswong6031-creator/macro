"""SEC EDGAR → employee headcount per stock, from the 10-K text (Demand Desk L2;
memory demand-desk-divergence).

WHY headcount, not live postings. Live job-posting counts are a genuine 2-6mo
LEADING demand proxy, but there is no free, reliable, per-company source for them
(scraping job boards is fragile + ToS-bound; keyed APIs like Adzuna only do noisy
keyword matching). What IS free and reliable: every 10-K discloses headcount in
Item 1 ("as of <date> we had approximately N employees"). Headcount GROWTH is the
company's revealed hiring bet — a real, management-independent demand-confidence
signal — though ANNUAL and COINCIDENT (companies hire with/just after demand),
not leading. So engine/demand_chain.hiring_read frames it as a coincident
cross-read (display-only, never a scored thesis), exactly like the housing chain.

Deterministic regex extraction (no LLM, no key): the disclosure phrasing is
standardized enough that a small pattern set covers most filers; names it can't
parse simply yield no rows. Pulls the last few 10-Ks per name to build a series.
Writes data/edgar/headcount.parquet (ticker, fy, employees, as_of). Cached 90d.
"""
from __future__ import annotations

import json
import logging
import re
import time

import pandas as pd

from collectors.edgar_facts import _cik_map, _get_json
from lib import config

log = logging.getLogger("edgar_headcount")

SUBMISSIONS = "https://data.sec.gov/submissions/CIK{:010d}.json"
DOC = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
# Baskets where hiring tracks demand (growth / tech / consumer-growth complex).
HC_BASKETS = ("ai_software", "non_ai_software", "ai_agents", "ai_neoclouds",
              "ai_semiconductors", "ai_infra")
N_FILINGS = 3               # last N 10-Ks → up to 3-year headcount series
MAX_DOC = 1_400_000         # Item 1 (Human Capital) is early; fetch only the head via Range
PACE = 0.7                  # gentle pacing — full 10-K docs are heavy; respect SEC fair-access

_PATTERNS = [
    r"approximately\s+([\d,]{3,9})\s+(?:full-time\s+)?(?:employees|people|team members)",
    r"had\s+([\d,]{3,9})\s+(?:full-time\s+)?(?:employees|people|team members)",
    r"employed\s+approximately\s+([\d,]{3,9})",
    r"workforce\s+of\s+approximately\s+([\d,]{3,9})",
    r"([\d,]{4,9})\s+(?:full-time\s+)?employees\s+(?:worldwide|globally)",
]


def _cache_path():
    p = config.data_dir() / "edgar" / "headcount.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _archive_ua() -> str:
    """www.sec.gov/Archives enforces SEC fair-access strictly: the UA must carry a
    contact EMAIL (the data.sec.gov API is lenient and does not). Use the configured
    edgar.user_agent if it already has one; else append a generic, non-personal
    contact so the doc fetch isn't 403'd."""
    ua = config.load()["edgar"]["user_agent"]
    return ua if "@" in ua else ua + " macro-dashboard@users.noreply.github.com"


def _fetch_text(url: str) -> str | None:
    import requests
    ua = _archive_ua()
    try:
        # Range-limit the download to the doc head (Item 1 sits early) — lighter on
        # SEC + on us. Servers that ignore Range return 200/full; we still cap below.
        r = requests.get(url, headers={"User-Agent": ua, "Range": f"bytes=0-{MAX_DOC}"}, timeout=40)
        if r.status_code not in (200, 206) or not r.text:
            return None
        html = r.text[:MAX_DOC]
    except Exception:  # noqa: BLE001
        return None
    txt = re.sub(r"<[^>]+>", " ", html)
    txt = re.sub(r"&[a-z]+;", " ", txt)
    return re.sub(r"\s+", " ", txt)


def _extract(txt: str) -> int | None:
    for p in _PATTERNS:
        m = re.search(p, txt, re.I)
        if m:
            try:
                n = int(m.group(1).replace(",", ""))
            except ValueError:
                continue
            if 50 <= n <= 5_000_000:        # sanity bounds
                return n
    return None


def _headcount_for(cik: int) -> dict[int, int]:
    """{fiscal_year: employees} from the last N 10-Ks of one filer."""
    sub = _get_json(SUBMISSIONS.format(cik))
    time.sleep(PACE)
    if not sub:
        return {}
    rec = (sub.get("filings") or {}).get("recent") or {}
    forms, accs, docs, rpts = (rec.get("form") or [], rec.get("accessionNumber") or [],
                               rec.get("primaryDocument") or [], rec.get("reportDate") or [])
    out: dict[int, int] = {}
    seen = 0
    for i, form in enumerate(forms):
        if form != "10-K":
            continue
        seen += 1
        if seen > N_FILINGS:
            break
        try:
            fy = int(str(rpts[i])[:4])
        except (ValueError, IndexError):
            continue
        url = DOC.format(cik=cik, acc=accs[i].replace("-", ""), doc=docs[i])
        txt = _fetch_text(url)
        time.sleep(PACE)
        if not txt:
            continue
        n = _extract(txt)
        if n is not None:
            out.setdefault(fy, n)
    return out


def _universe() -> list[str]:
    p = config.data_dir() / "baskets" / "membership.json"
    if not p.exists():
        return []
    baskets = (json.loads(p.read_text()).get("baskets") or {})
    out: set[str] = set()
    for slug in HC_BASKETS:
        for m in (baskets.get(slug, {}).get("members") or []):
            if not m.get("removed") and m.get("ticker"):
                out.add(m["ticker"])
    return sorted(out)


def fetch_headcount(max_new: int = 60, tickers: list[str] | None = None) -> pd.DataFrame:
    """Drip headcount into data/edgar/headcount.parquet. Best-effort: re-fetches
    names absent or older than ~90 days; never raises."""
    cache = _cache_path()
    existing = pd.read_parquet(cache) if cache.exists() else pd.DataFrame()
    cik = _cik_map()
    universe = tickers or _universe()
    now = pd.Timestamp.now("UTC").tz_localize(None)

    def stale(t: str) -> bool:
        if existing.empty or t not in set(existing.get("ticker", [])):
            return True
        rows = existing[existing["ticker"] == t]
        try:
            return (now - pd.to_datetime(rows["as_of"]).max()).days >= 90
        except Exception:  # noqa: BLE001
            return True

    todo = [t for t in universe if t in cik and stale(t)][:max_new]
    log.info("edgar_headcount: %d in universe, %d with CIK, fetching %d", len(universe), len(cik), len(todo))
    fresh = []
    for t in todo:
        try:
            for fy, n in _headcount_for(cik[t]).items():
                fresh.append({"ticker": t, "fy": int(fy), "employees": int(n), "as_of": now.isoformat()})
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.debug("headcount %s failed: %s", t, e)
    if fresh:
        fdf = pd.DataFrame(fresh)
        keep = existing[~existing["ticker"].isin(fdf["ticker"])] if not existing.empty else existing
        out = pd.concat([keep, fdf], ignore_index=True)
        out.to_parquet(cache, index=False)
    else:
        out = existing
    n_t = out["ticker"].nunique() if not out.empty else 0
    log.info("edgar_headcount: cache now %d names, %d ticker-years", n_t, len(out))
    return out


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    fetch_headcount()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
