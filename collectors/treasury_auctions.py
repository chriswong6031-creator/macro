"""Treasury auction RESULTS collector — TreasuryDirect, keyless.

The DEMAND side of the Treasury market: how well each marketable auction clears. The
companion to engine/event_calendar's *upcoming* auction calendar — this fetches the
*results* (TA_WS/securities/auctioned): bid-to-cover, the indirect-bidder
(foreign/real-money) share, primary-dealer takedown, issue size & tenor.

Accrues to data/treasury_auctions/auctions.parquet, deduped on (cusip, auction_date)
so the reopenings of one CUSIP are kept as the distinct auctions they are (a 10y note
reopened across three months shares one CUSIP but is three auctions).

The endpoint returns the newest ~250 rows per security type regardless of `days`, so
one call backfills ~5y of coupons; older history then persists in our store as it
accrues forward. Powers the display-only "Treasury supply absorption" panel on the
bonds page (engine/treasury_supply.py) — supply-absorption CONTEXT, never scored.
"""
from __future__ import annotations

import logging
import re
from datetime import date

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

AUCTIONED = "https://www.treasurydirect.gov/TA_WS/securities/auctioned"
_TYPES = ("Bill", "Note", "Bond", "TIPS", "FRN")
_BENCH = (2, 3, 5, 7, 10, 20, 30)

# raw record field -> our column (all values arrive from the API as strings)
_NUM = {
    "highYield": "high_yield", "highInvestmentRate": "high_invest_rate",
    "interestRate": "interest_rate", "bidToCoverRatio": "bid_to_cover",
    "totalAccepted": "total_accepted", "offeringAmount": "offering_amount",
    "competitiveAccepted": "competitive_accepted",
    "primaryDealerAccepted": "primary_dealer_accepted",
    "directBidderAccepted": "direct_accepted",
    "indirectBidderAccepted": "indirect_accepted",
}


def _f(v) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def term_years(term: str) -> float | None:
    """'9-Year 11-Month' -> 9.917; '4-Week' -> 0.077; '26-Week' -> 0.5. None if unparseable.
    PURE — Treasury terms mix Year/Month/Week/Day units."""
    if not term:
        return None
    yrs = months = weeks = days = 0.0
    if (m := re.search(r"(\d+)\s*-?\s*Year", term)):
        yrs = float(m.group(1))
    if (m := re.search(r"(\d+)\s*-?\s*Month", term)):
        months = float(m.group(1))
    if (m := re.search(r"(\d+)\s*-?\s*Week", term)):
        weeks = float(m.group(1))
    if (m := re.search(r"(\d+)\s*-?\s*Day", term)):
        days = float(m.group(1))
    total = yrs + months / 12.0 + weeks / 52.0 + days / 365.0
    return round(total, 4) if total > 0 else None


def bench_tenor(yrs: float | None) -> int | None:
    """Nearest benchmark coupon tenor (years) for a >=1y security; None for bills (<1y). PURE."""
    if yrs is None or yrs < 1:
        return None
    return min(_BENCH, key=lambda b: abs(b - yrs))


def parse_record(rec: dict) -> dict | None:
    """One raw TreasuryDirect auctioned record -> our flat row. PURE.
    None when the record lacks a CUSIP or a parseable auction date."""
    cusip = (rec.get("cusip") or "").strip()
    ad = (rec.get("auctionDate") or "")[:10]
    if not cusip or not ad:
        return None
    try:
        adate = date.fromisoformat(ad)
    except ValueError:
        return None
    term = (rec.get("securityTerm") or "").strip()
    yrs = term_years(term)
    # `type` is the canonical instrument class (Bill/Note/Bond/TIPS/FRN/CMB); the API
    # labels TIPS & FRN as securityType "Note"/"Bond" (their legal form), so we MUST
    # classify on `type`, not securityType — else TIPS (real) pollute nominal buckets.
    row: dict = {
        "auction_date": pd.Timestamp(adate), "cusip": cusip,
        "klass": (rec.get("type") or rec.get("securityType") or "").strip(),
        "security_type": (rec.get("securityType") or "").strip(),
        "security_term": term, "tenor_years": yrs, "tenor": bench_tenor(yrs),
        "reopening": (rec.get("reopening") or "").strip().lower() == "yes",
    }
    for src, dst in _NUM.items():
        row[dst] = _f(rec.get(src))
    # bills carry the bond-equivalent yield in highInvestmentRate, not highYield
    if row.get("high_yield") is None:
        row["high_yield"] = row.get("high_invest_rate")
    return row


class TreasuryAuctionsAdapter(Adapter):
    name = "treasury_auctions"
    group = "treasury_auctions"
    stale_after_days = 10   # auctions cluster; a quiet week is normal

    def __init__(self) -> None:
        self.cfg = config.load().get("treasury_auctions", {}) or {}

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        if not self.cfg.get("enabled", True):
            raise RuntimeError("treasury_auctions disabled in config")
        days = int(self.cfg.get("history_days", 3650))
        types = self.cfg.get("types", _TYPES)
        rows: list[dict] = []
        ok_types = 0
        for t in types:
            try:
                r = self.http_get(AUCTIONED, retries=int(self.cfg.get("retries", 3)),
                                  params={"format": "json", "type": t, "days": days})
                data = r.json() or []
            except Exception as e:  # noqa: BLE001 — one type failing must not kill the rest
                log.warning("treasury_auctions: type %s fetch failed (%s)", t, e)
                continue
            if not isinstance(data, list):
                continue
            ok_types += 1
            for rec in data:
                row = parse_record(rec)
                if row is not None:
                    rows.append(row)
        if not rows:
            raise RuntimeError("no auction rows fetched")
        self._accrue(pd.DataFrame(rows))
        log.info("treasury_auctions: %d rows across %d/%d types", len(rows), ok_types, len(types))
        s = pd.DataFrame({"rows": [len(rows)]}, index=[pd.Timestamp(date.today())])
        return {"treasury_auction_runs": s}

    def _accrue(self, new: pd.DataFrame) -> None:
        p = config.data_dir() / "treasury_auctions" / "auctions.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            try:
                old = pd.read_parquet(p)
                new = pd.concat([old, new], ignore_index=True)
            except Exception as e:  # noqa: BLE001 — corrupt cache must not lose this run
                log.warning("auctions parquet unreadable (%s) — overwriting", e)
        # reopenings share a CUSIP across auction dates -> key on both, not CUSIP alone
        new = (new.drop_duplicates(subset=["cusip", "auction_date"], keep="last")
                  .sort_values("auction_date").reset_index(drop=True))
        new.to_parquet(p, index=False)
