#!/usr/bin/env python3
"""Backfill historical ETF holdings snapshots from sponsors that expose DATED
daily holdings files — so the ETF flow-radar page has real share-decision data
immediately, instead of waiting weeks for the daily collector to accrue snapshots.

Today only Global X qualifies: assets.globalxetfs.com/funds/holdings/
<fund>_full-holdings_YYYYMMDD.csv is a free, dated, full-holdings CSV (with
"Shares Held"). SSGA/Invesco serve current-only (no date in the URL) so they
can't be backfilled and rely on forward collection.

Writes one snapshot per fund per available trading day to
data/etf_holdings/<TICKER>/<YYYY-MM-DD>.parquet (the same schema the daily
collector writes), which collectors.holdings.active_changes_dir then diffs.

Usage: python scripts/backfill_etf.py [days_back]   (default 60 calendar days)
"""
from __future__ import annotations

import io
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.etf_holdings import GLOBALX_CSV, EtfHoldingsAdapter  # noqa: E402
from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("backfill_etf")


def _parse_globalx(text: str, ticker: str) -> tuple[pd.DataFrame, str] | None:
    """Parse one Global X dated holdings CSV (same logic as the live collector)."""
    lines = text.splitlines()
    hdr = next((k for k, ln in enumerate(lines)
                if ln.lower().startswith("% of net assets")
                or ln.lower().startswith('"% of net assets')), None)
    if hdr is None:
        return None
    asof = None
    for ln in lines[:hdr]:
        if "as of" in ln.lower():
            try:
                asof = str(pd.to_datetime(ln.lower().split("as of")[1].strip()).date())
            except (ValueError, TypeError):
                pass
    df = pd.read_csv(io.StringIO("\n".join(lines[hdr:])))
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    wcol = next((c for c in df.columns if "net_assets" in c or "weight" in c), None)
    scol = next((c for c in df.columns if "shares" in c), None)
    mcol = next((c for c in df.columns if "market_value" in c), None)
    out = EtfHoldingsAdapter._normalize(df, ticker, asof or "", wcol=wcol, scol=scol, mcol=mcol)
    if out is None or out.empty:
        return None
    return out, (asof or "")


def backfill(days_back: int = 60) -> dict[str, int]:
    adapter = EtfHoldingsAdapter()
    universe = config.load()["etf_holdings"]["universe"]
    gx = [t for t, s in universe.items() if s.get("sponsor") == "globalx"]
    outroot = config.data_dir() / "etf_holdings"
    ua = {"User-Agent": "Mozilla/5.0 (research)"}
    written: dict[str, int] = {}
    for ticker in gx:
        d = outroot / ticker
        d.mkdir(parents=True, exist_ok=True)
        existing = {p.stem for p in d.glob("*.parquet")}
        got = 0
        for back in range(0, days_back + 1):
            ymd = (date.today() - timedelta(days=back)).strftime("%Y%m%d")
            url = GLOBALX_CSV.format(fund=ticker.lower(), ymd=ymd)
            try:
                r = adapter.http_get(url, retries=1, timeout=20, headers=ua)
            except Exception:  # noqa: BLE001 — 404 on weekends/holidays; skip
                continue
            res = _parse_globalx(r.text, ticker)
            if not res:
                continue
            snap, asof = res
            if not asof:
                asof = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}"
            if asof in existing:
                continue
            snap.to_parquet(d / f"{asof}.parquet")
            existing.add(asof)
            got += 1
        written[ticker] = got
        log.info("%s: +%d snapshots (%d total)", ticker, got, len(list(d.glob('*.parquet'))))
    return written


def backfill_roundhill(days_back: int = 60) -> dict[str, int]:
    """Backfill Roundhill funds. One dated MASTER CSV per date covers all funds, so
    fetch each date once (cached on the adapter) and slice out every configured fund."""
    adapter = EtfHoldingsAdapter()
    universe = config.load()["etf_holdings"]["universe"]
    rh = [t for t, s in universe.items() if s.get("sponsor") == "roundhill"]
    if not rh:
        return {}
    outroot = config.data_dir() / "etf_holdings"
    for t in rh:
        (outroot / t).mkdir(parents=True, exist_ok=True)
    existing = {t: {p.stem for p in (outroot / t).glob("*.parquet")} for t in rh}
    written = {t: 0 for t in rh}
    for back in range(0, days_back + 1):
        mdy = (date.today() - timedelta(days=back)).strftime("%m%d%Y")
        master = adapter._roundhill_master(mdy)
        if master is None:
            continue
        for t in rh:
            sub = master[master["Account"].astype(str).str.strip() == t]
            if sub.empty:
                continue
            try:
                asof = str(pd.to_datetime(sub["Date"].iloc[0]).date())
            except (ValueError, TypeError):
                continue
            if asof in existing[t]:
                continue
            df = sub.rename(columns={"StockTicker": "ticker", "SecurityName": "name",
                                     "Weightings": "weight", "Shares": "shares",
                                     "MarketValue": "market_value"})
            df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
            snap = EtfHoldingsAdapter._normalize(df, t, asof, wcol="weight",
                                                 scol="shares", mcol="market_value")
            if snap is None or snap.empty:
                continue
            snap.to_parquet(outroot / t / f"{asof}.parquet")
            existing[t].add(asof)
            written[t] += 1
    for t, n in written.items():
        log.info("%s: +%d snapshots (%d total)", t, n, len(list((outroot / t).glob('*.parquet'))))
    return written


def backfill_amplify(days_back: int = 300) -> dict[str, int]:
    """Backfill Amplify funds from the public Firestore feed: the collection lists
    ~9 months of dated holdings docs, so pull every date within the window that we
    don't already have. Reuses the live adapter's doc parser."""
    adapter = EtfHoldingsAdapter()
    universe = config.load()["etf_holdings"]["universe"]
    amp = [t for t, s in universe.items() if s.get("sponsor") == "amplify"]
    if not amp:
        return {}
    outroot = config.data_dir() / "etf_holdings"
    written: dict[str, int] = {}
    cutoff = (pd.Timestamp(date.today()) - pd.Timedelta(days=days_back)).date()
    for ticker in amp:
        d = outroot / ticker
        d.mkdir(parents=True, exist_ok=True)
        existing = {p.stem for p in d.glob("*.parquet")}
        base = ("https://firestore.googleapis.com/v1/projects/amplify-etfs-data-feed/"
                f"databases/(default)/documents/funds/{ticker}/holdings")
        key = universe[ticker].get("api_key", "AIzaSyCibhGo4lu8ZALtBvf_ZT351BDMUPqOYjc")
        try:
            listing = adapter._ua_get(
                f"{base}?mask.fieldPaths=asOfDate&pageSize=400&key={key}", timeout=45).json()
        except Exception as e:  # noqa: BLE001
            log.warning("amplify %s: listing failed: %s", ticker, e)
            continue
        got = 0
        for doc in (listing.get("documents") or []):
            did = doc.get("name", "").rsplit("/", 1)[-1]
            if not did or did in existing:
                continue
            try:
                if pd.to_datetime(did).date() < cutoff:
                    continue
            except (ValueError, TypeError):
                continue
            try:
                full = adapter._ua_get(f"{base}/{did}?key={key}", timeout=45).json()
                snap = EtfHoldingsAdapter._parse_amplify_doc(full, ticker, did)
            except Exception:  # noqa: BLE001 — one date must not kill the rest
                continue
            if snap is None or snap.empty:
                continue
            asof = str(snap["as_of"].iloc[0]) if "as_of" in snap.columns else did
            if asof in existing:
                continue
            snap.to_parquet(d / f"{asof}.parquet")
            existing.add(asof)
            got += 1
        written[ticker] = got
        log.info("%s: +%d snapshots (%d total)", ticker, got, len(list(d.glob('*.parquet'))))
    return written


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    res = {**backfill(n), **backfill_roundhill(n), **backfill_amplify(max(n, 300))}
    print("backfilled:", {k: v for k, v in res.items()})
    print("total new snapshots:", sum(res.values()))
