"""Per-stock identity + business description for the analyzer's Profile panel
(Phase 2 of research/STOCK_FUNDAMENTALS_PLAN.md).

Two keyless, free, near-static sources — best-effort and cached (refreshed
slowly; descriptions barely move):

  SEC EDGAR submissions   data.sec.gov/submissions/CIK{10}.json
                          → SIC industry text, listing exchange, HQ city/state
  Wikipedia REST summary  en.wikipedia.org/api/rest_v1/page/summary/{title}
                          (resolved via the opensearch endpoint)
                          → a one-paragraph "what it does" business description

Writes data/profile/profiles.parquet (ticker-indexed: description, sic_description,
exchange, hq, name, source, as_of). engine/stock_fundamentals reads it into the
Profile block; a missing row just leaves those chips empty (the page already
guards for that). Resumable: only tickers absent from the cache (or older than
refresh_days) are fetched, capped at max_new per run, so a weekly job drips
through the universe without hammering either host. Nothing here can fail the
build — callers wrap it and per-ticker errors are skipped.

HONESTY (shown on the page): descriptions are Wikipedia extracts (community-
sourced, may lag); the SEC business address is the filing address, not
necessarily operational HQ; SIC is the SEC industry code, not a GICS sub-industry.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from urllib.parse import quote

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# Wikipedia asks for a descriptive UA with contact. SEC's data.sec.gov blocks
# (403) the email-laden form but accepts the simple edgar UA already in config —
# so SEC reuses config.edgar.user_agent, Wikipedia uses WIKI_UA.
WIKI_UA = "macro-dashboard research (chriswong6031-creator) macro-dashboard@users.noreply.github.com"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{:010d}.json"
WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"
WIKI_OPENSEARCH = ("https://en.wikipedia.org/w/api.php?action=opensearch"
                   "&search={}&limit=1&namespace=0&format=json")
REFRESH_DAYS = 120


def _cache_path():
    p = config.data_dir() / "profile" / "profiles.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _get(url: str, headers: dict, retries: int = 3, timeout: int = 20):
    import requests
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r
        except Exception as e:  # noqa: BLE001 — best-effort per source
            if attempt == retries - 1:
                log.debug("profile GET failed %s: %s", url.split("?")[0][-48:], e)
                return None
            time.sleep(1.2 * (attempt + 1))
    return None


def _universe() -> dict[str, str]:
    """{ticker: company name} from the breadth constituents (same set edgar uses)."""
    out: dict[str, str] = {}
    for grp in ("breadth", "smallcap_breadth", "midcap_breadth"):
        p = config.data_dir() / grp / "constituents.parquet"
        if p.exists():
            meta = pd.read_parquet(p)
            for t, row in meta.iterrows():
                out.setdefault(str(t), str(row.get("name", t)))
    return out


def _cik_map() -> dict[str, int]:
    """ticker -> CIK. Primary: the CIKs edgar already resolved in
    data/edgar/fundamentals.parquet. Fallback: the SEC company_tickers.json cache."""
    out: dict[str, int] = {}
    fp = config.data_dir() / "edgar" / "fundamentals.parquet"
    if fp.exists():
        try:
            df = pd.read_parquet(fp, columns=["cik"])
            for t, row in df.iterrows():
                c = row.get("cik")
                if pd.notna(c):
                    out[str(t)] = int(c)
        except Exception:  # noqa: BLE001
            pass
    cache = config.data_dir() / "edgar" / "company_tickers.json"
    if len(out) < 100 and cache.exists():
        try:
            data = json.loads(cache.read_text())
            sec = {row["ticker"].upper(): int(row["cik_str"]) for row in data.values()}
            for t in _universe():
                u = t.upper()
                for cand in (u, u.replace("-", "."), u.replace(".", "-"),
                             u.split("-")[0], u.split(".")[0]):
                    if cand in sec:
                        out.setdefault(t, sec[cand])
                        break
        except Exception:  # noqa: BLE001
            pass
    return out


def _sec_submission(cik: int) -> dict:
    """SIC text, listing exchange, HQ city/state from the SEC submissions doc."""
    ua = config.load()["edgar"]["user_agent"]
    r = _get(SUBMISSIONS.format(cik), {"User-Agent": ua, "Accept-Encoding": "gzip, deflate"})
    time.sleep(0.12)                       # SEC fair-access pacing (<10 req/s)
    if r is None:
        return {}
    try:
        d = r.json()
    except Exception:  # noqa: BLE001
        return {}
    exch = d.get("exchanges") or []
    addr = (d.get("addresses") or {}).get("business") or {}
    hq = ", ".join(p for p in (addr.get("city"), addr.get("stateOrCountry")) if p) or None
    return {"sic_description": (d.get("sicDescription") or None),
            "exchange": (exch[0] if exch else None), "hq": hq,
            "name": d.get("name") or None}


def _trim(extract: str, max_sentences: int = 2, max_chars: int = 320) -> str:
    """First couple of sentences of a Wikipedia extract, length-capped."""
    extract = " ".join((extract or "").split())
    if not extract:
        return ""
    parts, out = extract.split(". "), ""
    for i, s in enumerate(parts):
        nxt = out + s + (". " if i < len(parts) - 1 else "")
        if i >= max_sentences or len(nxt) > max_chars:
            break
        out = nxt
    out = out.strip()
    return out if out else extract[:max_chars]


def _wiki_description(name: str) -> str | None:
    """One-paragraph business description via Wikipedia REST, resolving the page
    title through opensearch first (company names rarely match a title exactly)."""
    headers = {"User-Agent": WIKI_UA, "Accept": "application/json"}
    title = None
    r = _get(WIKI_OPENSEARCH.format(quote(name)), headers)
    time.sleep(0.05)
    if r is not None:
        try:
            os_res = r.json()
            if isinstance(os_res, list) and len(os_res) >= 2 and os_res[1]:
                title = os_res[1][0]
        except Exception:  # noqa: BLE001
            title = None
    if not title:
        title = name
    r = _get(WIKI_SUMMARY.format(quote(title.replace(" ", "_"))) + "?redirect=true", headers)
    time.sleep(0.05)
    if r is None:
        return None
    try:
        s = r.json()
    except Exception:  # noqa: BLE001
        return None
    if s.get("type") == "disambiguation":
        return None
    desc = _trim(s.get("extract") or "")
    return desc or None


def fetch_profiles(force: bool = False, max_new: int = 250,
                   tickers: list[str] | None = None) -> pd.DataFrame:
    """Fetch (resumably) identity + descriptions for the universe; merge into the
    cache and return the wide ticker-indexed table. Best-effort: a host being down
    just leaves rows unfetched for the next run."""
    cache = _cache_path()
    existing = pd.read_parquet(cache) if cache.exists() else pd.DataFrame()
    cik = _cik_map()
    names = _universe()
    universe = tickers or list(names) or list(existing.index)

    def stale(t: str) -> bool:
        if force or existing.empty or t not in existing.index:
            return True
        ts = existing.loc[t].get("as_of")
        try:
            age = (datetime.now(timezone.utc) - pd.to_datetime(ts)).days
        except Exception:  # noqa: BLE001
            return True
        return age > REFRESH_DAYS

    todo = [t for t in universe if stale(t)][:max_new]
    log.info("equity_profile: %d universe, %d stale → fetching %d (cap %d)",
             len(universe), sum(stale(t) for t in universe), len(todo), max_new)

    rows = []
    now = datetime.now(timezone.utc).isoformat()
    for t in todo:
        rec: dict = {"ticker": t, "name": names.get(t, t), "as_of": now}
        if t in cik:
            rec.update(_sec_submission(cik[t]))
        wiki_name = rec.get("name") or names.get(t, t)
        rec["description"] = _wiki_description(wiki_name)
        rec["source"] = "wikipedia+sec"
        rows.append(rec)

    fresh = pd.DataFrame(rows).set_index("ticker") if rows else pd.DataFrame()
    if not existing.empty and not fresh.empty:
        out = pd.concat([existing[~existing.index.isin(fresh.index)], fresh])
    else:
        out = fresh if not fresh.empty else existing
    if not out.empty:
        out.to_parquet(cache)
    log.info("equity_profile: cache now %d tickers (%d with a description)",
             len(out), int(out["description"].notna().sum()) if "description" in out else 0)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    import sys
    ts = sys.argv[1:] or None
    df = fetch_profiles(force=bool(ts), max_new=10, tickers=ts)
    cols = [c for c in ("name", "sic_description", "exchange", "hq", "description") if c in df.columns]
    for t in (ts or list(df.index)[:5]):
        if t in df.index:
            r = df.loc[t]
            print(f"\n{t}: {r.get('name')}  [{r.get('exchange')} · {r.get('sic_description')} · {r.get('hq')}]")
            print(" ", (r.get("description") or "(no description)"))
