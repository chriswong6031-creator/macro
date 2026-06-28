"""EDGAR scarcity-language EMERGENCE sweep — the theme-DISCOVERY collector
(research/THEMATIC_FORESIGHT_INSTITUTIONAL_UPGRADE.md §6).

THE GAP THIS CLOSES. collectors/edgar_fts.py and edgar_guidance.py both filter their EDGAR
hits to the curated theme universe (tickers already in config `themes:`), so by construction
they can only ever CONFIRM the 18 themes we already named. They are structurally blind to a
theme forming OUTSIDE the list — exactly the pre-13D state (the words "sold out for two
years" appeared in memory/DRAM filings before the theme had a name or a basket).

This collector inverts the logic: it sweeps the same physical-scarcity vocabulary across ALL
of EDGAR (NO universe filter) and enriches each filer with its SIC industry code (SEC
submissions doc). engine/theme_emergence.py then clusters the hits by industry and surfaces
industries where a cluster of *un-tracked* companies is independently reporting scarcity —
a bottleneck forming before it is a tracked theme. We detect the CONDITION; the theme reveals
itself from the cluster of filers.

Bounded + drip + cached (mirrors edgar_fts / edgar_guidance): keyless efts.sec.gov for the
language sweep, keyless data.sec.gov/submissions for SIC, <10 req/s pacing, caps pages and
per-run SIC lookups, resumable. Writes data/edgar/emergence_hits.parquet (ticker, cik,
phrase, form, file_date, sic, sic_desc) + data/edgar/cik_sic.json (the drip cache). Network
failure is non-fatal — the discovery engine simply returns None.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, timedelta

import pandas as pd

from collectors.edgar_facts import _get_json
from collectors.edgar_fts import _parse_hit, _theme_universe
from lib import config

log = logging.getLogger("edgar_emergence")

FTS_URL = "https://efts.sec.gov/LATEST/search-index"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{:010d}.json"
FORMS = "10-K,10-Q,8-K"

# the physical-scarcity / bottleneck signature — the words a company says when an input it
# sells or buys is running short. A CLUSTER of unrelated filers saying these = a theme forming.
SCARCITY_PHRASES = [
    "sold out", "on allocation", "capacity constrained", "supply constrained",
    "unable to meet demand", "demand exceeds supply", "longer lead times",
    "extended lead times", "record backlog", "tight supply", "double ordering",
    "allocate supply", "constrained capacity", "expedite fees",
]
MAX_PAGES = 5              # 10 hits/page -> up to 50 most-recent hits per phrase
LOOKBACK_DAYS = 400        # window swept (engine uses recent-vs-baseline within this)
STALE_DAYS = 7
MAX_SIC_LOOKUPS = 180      # cap submissions fetches per run (drip; the cache fills over runs)


def _hits_path():
    p = config.data_dir() / "edgar" / "emergence_hits.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _sic_cache_path():
    return config.data_dir() / "edgar" / "cik_sic.json"


def _load_sic_cache() -> dict:
    p = _sic_cache_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return {}


def _save_sic_cache(cache: dict) -> None:
    try:
        _sic_cache_path().write_text(json.dumps(cache, separators=(",", ":")))
    except Exception as e:  # noqa: BLE001
        log.warning("cik_sic cache write failed: %s", e)


def _fetch_sic(cik: str) -> dict | None:
    """SIC code + description for one CIK from the SEC submissions doc. None on failure."""
    try:
        d = _get_json(SUBMISSIONS_URL.format(int(cik)), retries=2)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(d, dict):
        return None
    sic = d.get("sic")
    return {"sic": str(sic) if sic else None,
            "sic_desc": (d.get("sicDescription") or None),
            "name": (d.get("name") or None)}


def _is_stale(p) -> bool:
    if not p.exists():
        return True
    try:
        df = pd.read_parquet(p)
        if df.empty or "fetched" not in df.columns:
            return True
        newest = pd.to_datetime(df["fetched"]).max().date()
        return (date.today() - newest).days >= STALE_DAYS
    except Exception:  # noqa: BLE001
        return True


def fetch_emergence_hits(force: bool = False, phrases: list[str] | None = None,
                         max_sic_lookups: int = MAX_SIC_LOOKUPS) -> pd.DataFrame | None:
    """Sweep scarcity language across ALL of EDGAR (no universe filter), enrich with SIC,
    upsert the cache. Returns the frame, or the existing cache when fresh / on total failure."""
    p = _hits_path()
    if not force and not _is_stale(p):
        log.info("edgar_emergence cache fresh; skipping refresh")
        return pd.read_parquet(p) if p.exists() else None

    enddt = date.today()
    startdt = enddt - timedelta(days=LOOKBACK_DAYS)
    rows: list[dict] = []
    first_request = True
    for phrase in (phrases or SCARCITY_PHRASES):
        for page in range(MAX_PAGES):
            url = (f'{FTS_URL}?q="{phrase.replace(" ", "+")}"&forms={FORMS}'
                   f"&startdt={startdt}&enddt={enddt}&from={page * 10}")
            data = _get_json(url, retries=1 if first_request else 3)
            if data is None and first_request:
                log.warning("edgar_emergence: EDGAR unreachable; keeping existing cache")
                return pd.read_parquet(p) if p.exists() else None
            first_request = False
            hits = ((data or {}).get("hits") or {}).get("hits") or []
            if not hits:
                break
            for h in hits:
                rec = _parse_hit(h)          # NB: NO universe filter — that is the whole point
                if rec and rec.get("ticker"):
                    rec["phrase"] = phrase
                    rows.append(rec)
            time.sleep(0.15)
            if len(hits) < 10:
                break
    if not rows:
        log.info("edgar_emergence: no scarcity-language hits this sweep")
        return pd.read_parquet(p) if p.exists() else None

    new = pd.DataFrame(rows)
    today = date.today().isoformat()
    new["fetched"] = today

    # --- SIC enrichment (drip + cache) ---
    cache = _load_sic_cache()
    need = [c for c in new["cik"].dropna().astype(str).unique() if c not in cache]
    fetched = 0
    for c in need:
        if fetched >= max_sic_lookups:
            break
        info = _fetch_sic(c)
        if info is not None:
            cache[c] = info
            fetched += 1
            time.sleep(0.12)               # SEC fair-access pacing
    if fetched:
        _save_sic_cache(cache)
    new["sic"] = new["cik"].astype(str).map(lambda c: (cache.get(c) or {}).get("sic"))
    new["sic_desc"] = new["cik"].astype(str).map(lambda c: (cache.get(c) or {}).get("sic_desc"))

    if p.exists():
        try:
            old = pd.read_parquet(p)
            new = pd.concat([old, new], ignore_index=True)
        except Exception:  # noqa: BLE001
            pass
    new = new.drop_duplicates(subset=["id", "phrase"]).reset_index(drop=True)
    new.to_parquet(p, index=False)
    log.info("edgar_emergence: %d scarcity hits cached (+%d SIC lookups) -> %s",
             len(new), fetched, p)
    return new


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    df = fetch_emergence_hits(force=True)
    if df is not None:
        known = _theme_universe()
        df = df.copy()
        df["known"] = df["ticker"].isin(known)
        print(f"rows: {len(df)} | distinct filers: {df['ticker'].nunique()} | "
              f"new (untracked): {df.loc[~df['known'], 'ticker'].nunique()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
