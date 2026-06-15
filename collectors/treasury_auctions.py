"""Treasury auction RESULTS collector (free, keyless) — coupon-auction demand for the
DISPLAY-ONLY absorption panel (engine.auction_stress, bonds page).

Phase-0 verdict (scripts/auction_stress_phase0.py, 1,362 coupon auctions 2008-2026):
the demand signal is REAL but priced within the session — contemporaneous IC vs the
auction-day yield move is +0.28, yet the FORWARD IC is ~-0.07 (the WRONG sign vs the
"weak auction => higher yields" thesis — a mean-reversion snapback), and the long end
has no forward signal at all. So this data is shown as coincident CONTEXT only and is
never scored or propagated.

STORAGE: this is EVENT data (many auctions per day, keyed by CUSIP), not a date-unique
time series, so it can't go through lib.store (whose upsert forces a unique datetime
index). It manages its own append-only parquet — data/treasury_auctions/
auction_results.parquet — merged on CUSIP (new wins, old rows always kept). Refreshed
from scripts.collect as an additive, never-fatal step.

SOURCE: TreasuryDirect TA_WS /securities/search?startDate&endDate&type — returns full
auction results incl. bidToCoverRatio, indirect/direct/primary-dealer accepted $, and
the high yield. Nominal coupons only (Note + Bond); bills are money-market and TIPS/FRN
are excluded. The true auction TAIL (stop-out minus when-issued) needs paid WI data and
is intentionally omitted — we keep only the demand metrics that are free.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

import pandas as pd
import requests

from lib import config

# TreasuryDirect TA_WS has no UA gating, but send a descriptive one anyway.
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) macro-dashboard/research"
_PARQUET = "auction_results.parquet"
_RAW_FIELDS = {
    "cusip": "cusip", "type": "securityType", "term": "securityTerm",
    "auction_date": "auctionDate", "btc": "bidToCoverRatio",
    "indirect": "indirectBidderAccepted", "direct": "directBidderAccepted",
    "dealer": "primaryDealerAccepted", "accepted": "totalAccepted",
    "offering": "offeringAmount", "high_yield": "highYield",
}


def _cfg() -> dict:
    return config.load()["auction_stress"]


def _path():
    p = config.data_dir() / "treasury_auctions" / _PARQUET
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _term_to_tenor(term: str, tenors) -> int | None:
    """'9-Year 11-Month' -> 10, '29-Year 10-Month' -> 30, '7-Year' -> 7. Maps
    reopenings to their on-the-run tenor; returns None if no standard tenor is within
    1.5y (e.g. a stray bill term)."""
    if not term:
        return None
    yrs = re.findall(r"(\d+)-Year", term)
    mos = re.findall(r"(\d+)-Month", term)
    dec = (int(yrs[0]) if yrs else 0) + (int(mos[0]) if mos else 0) / 12.0
    if dec <= 0:
        return None
    near = min(tenors, key=lambda t: abs(t - dec))
    return int(near) if abs(near - dec) <= 1.5 else None


def _fetch_window(base: str, start: str, end: str, typ: str) -> list[dict]:
    r = requests.get(f"{base}/search",
                     params={"startDate": start, "endDate": end, "type": typ, "format": "json"},
                     headers={"User-Agent": _UA}, timeout=40)
    r.raise_for_status()
    return r.json()


def _parse(recs: list[dict], tenors) -> pd.DataFrame:
    if not recs:
        return pd.DataFrame()
    df = pd.DataFrame([{k: r.get(v) for k, v in _RAW_FIELDS.items()} for r in recs])
    for c in ("btc", "indirect", "direct", "dealer", "accepted", "offering", "high_yield"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # utc=True then drop tz -> robust whether the API returns naive or aware stamps
    df["auction_date"] = pd.to_datetime(df["auction_date"], errors="coerce", utc=True).dt.tz_localize(None).dt.normalize()
    df["tenor"] = df["term"].map(lambda t: _term_to_tenor(t, tenors))
    df = df.dropna(subset=["tenor", "auction_date", "btc", "accepted"])
    df = df[df["accepted"] > 0].copy()
    df["tenor"] = df["tenor"].astype(int)
    df["indirect_share"] = df["indirect"] / df["accepted"]
    df["dealer_share"] = df["dealer"] / df["accepted"]
    df["direct_share"] = df["direct"] / df["accepted"]
    return df.dropna(subset=["indirect_share", "dealer_share"])


def _merge(old: pd.DataFrame | None, new: pd.DataFrame) -> pd.DataFrame | None:
    if new is None or new.empty:
        return old
    combined = new if (old is None or old.empty) else pd.concat([old, new], ignore_index=True)
    combined["auction_date"] = pd.to_datetime(combined["auction_date"])
    return (combined.dropna(subset=["cusip", "auction_date"])
            .sort_values("auction_date")
            .drop_duplicates(subset="cusip", keep="last")   # later (this fetch) wins
            .reset_index(drop=True))


def refresh(full_history: bool = False) -> int:
    """Fetch coupon-auction results and merge into the cached parquet. Returns the
    cached row count. Per-window failures are swallowed (degrade, never crash collect)."""
    cfg = _cfg()
    base, tenors = cfg["base_url"], cfg["tenors"]
    old = load_results()
    today = date.today()
    if full_history or old is None or old.empty:
        windows = [(f"{y}-01-01", f"{y}-12-31") for y in range(int(cfg["start_year"]), today.year + 1)]
    else:                                                    # incremental: last ~400 days
        windows = [(str(today - timedelta(days=400)), str(today))]
    recs: list[dict] = []
    for start, end in windows:
        for typ in cfg["types"]:
            try:
                recs.extend(_fetch_window(base, start, end, typ))
            except Exception:  # noqa: BLE001 — one window failing must not lose the rest
                continue
    merged = _merge(old, _parse(recs, tenors))
    if merged is not None and not merged.empty:
        merged.to_parquet(_path())
        return len(merged)
    return 0 if merged is None else len(merged)


def load_results() -> pd.DataFrame | None:
    p = _path()
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return None
