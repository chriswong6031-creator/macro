"""Ingest the captured Special Situations Digest archive into our database.

ONE-TIME normalization of the digest snapshot (issues #1–19, 4,471 situations)
captured under research/_recon_raw/ into a single queryable parquet at
data/special_situations/digest_db.parquet.

Purpose (private, internal): a ready-to-use backfill + the benchmark "answer key"
we grade our own EDGAR pipeline against, and the universe for near-term backtests
(ticker × category × issue_date → forward returns). The going-forward LIVE source
is our own EDGAR collector — this snapshot is the bootstrap, not a recurring feed.

Deterministic — no network, no LLM. Run: python -m scripts.ingest_digest_db
"""
from __future__ import annotations

import glob
import json
import re
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from lib import config

RAW = config.ROOT / "research" / "_recon_raw"
OUT = config.data_dir() / "special_situations" / "digest_db.parquet"
ISSUE1_DATE = date(2026, 2, 8)            # issue #1 Sunday; weekly cadence thereafter

_MULT = {"K": 1e-3, "M": 1.0, "B": 1e3, "T": 1e6}


def _parse_usd_m(s) -> float | None:
    """'$153M'/'$12.9B'/'$2M' -> value in $M (USD only; non-$ currencies -> None)."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if not s.startswith("$"):
        return None                       # keep currency-tagged caps out of the USD column
    m = re.search(r"([\d.]+)\s*([KMBT])?", s.replace(",", ""))
    if not m:
        return None
    try:
        return round(float(m.group(1)) * _MULT.get((m.group(2) or "M").upper(), 1.0), 3)
    except ValueError:
        return None


def _parse_price(s) -> tuple[float | None, str | None]:
    """'CAD 31.76' -> (31.76, 'CAD'); '$5.20' -> (5.20, 'USD')."""
    if not s or not isinstance(s, str):
        return None, None
    s = s.strip()
    ccy = None
    if s.startswith("$"):
        ccy = "USD"
    else:
        mc = re.match(r"([A-Za-z]{3})\s", s)
        if mc:
            ccy = mc.group(1).upper()
    mv = re.search(r"([\d.]+)", s.replace(",", ""))
    val = float(mv.group(1)) if mv else None
    return val, ccy


def _parse_metrics(m) -> dict[str, float]:
    """'Fwd P/E: 10.4x · EV/EBITDA: 5.8x · EV/Sales: 3.0x · EV/GP: 9.5x (FY2026)' -> cols."""
    out: dict[str, float] = {}
    if not m or not isinstance(m, str):
        return out
    key = {"fwd p/e": "fwd_pe", "ntm p/e": "fwd_pe", "ev/ebitda": "ev_ebitda",
           "fwd ev/ebitda": "ev_ebitda", "ntm ev/ebitda": "ev_ebitda",
           "ev/sales": "ev_sales", "ev/gp": "ev_gp"}
    for part in m.split("·"):
        if ":" not in part:
            continue
        lab, _, val = part.partition(":")
        lab = re.sub(r"\(.*?\)", "", lab).strip().lower()
        col = key.get(lab)
        if not col:
            continue
        mv = re.search(r"([\d.]+)", val)
        if mv:
            out.setdefault(col, float(mv.group(1)))
    return out


_SRC_RULES = [
    ("SEC EDGAR", ("sec.gov",)),
    ("Canada SEDAR+", ("sedarplus.ca", "sedar.com")),
    ("UK RNS/LSE", ("londonstockexchange", "investegate", "rns-pdf")),
    ("Australia ASX", ("asx.com.au", "announcements.asx")),
    ("Japan EDINET/TDnet", ("edinet-fsa", "tdnet", "jpx.co.jp")),
    ("HK HKEX", ("hkexnews", "hkex.com.hk")),
    ("Korea DART", ("dart.fss.or.kr", "kind.krx")),
    ("China CNINFO", ("cninfo.com.cn",)),
    ("India BSE/NSE", ("bseindia", "nseindia")),
    ("Newswire", ("businesswire", "prnewswire", "globenewswire", "newsfilecorp", "accesswire", "cision")),
    ("Data platform", ("tradingview", "finance.yahoo", "simplywall", "morningstar", "tikr",
                       "tipranks", "marketscreener", "markitdigital", "stocktitan", "scanx", "whalesbook")),
]


def _bucket(u) -> tuple[str | None, str]:
    if not u or not isinstance(u, str):
        return None, "(none)"
    try:
        host = urlparse(u).netloc.lower().replace("www.", "")
    except ValueError:
        return host if (host := "") else "(bad)", "(bad)"  # pragma: no cover
    for label, doms in _SRC_RULES:
        if any(d in host for d in doms):
            return label, host
    return "Other/IR/exchange", host


def ingest() -> pd.DataFrame:
    idx = json.loads((RAW / "archive-index.json").read_text())["items"]
    details: dict[str, dict] = {}
    for f in glob.glob(str(RAW / "details" / "*.json")):
        details.update(json.loads(Path(f).read_text()))

    rows = []
    for r in idx:
        d = details.get(str(r["id"]), {})
        mets = _parse_metrics(d.get("m"))
        px, ccy = _parse_price(d.get("px"))
        bucket, host = _bucket(d.get("u"))
        issue = r.get("i")
        idate = (ISSUE1_DATE + timedelta(days=(int(issue) - 1) * 7)).isoformat() if issue else None
        rows.append({
            "id": r["id"], "company": r.get("c"), "ticker": r.get("t"),
            "country": r.get("co"), "category": r.get("cat"),
            "issue": issue, "issue_date": idate, "headline": r.get("hk"),
            "market_cap_musd": _parse_usd_m(r.get("mc")), "mc_raw": r.get("mc"),
            "ev_musd": _parse_usd_m(r.get("ev")), "ev_raw": r.get("ev"),
            "price": px, "price_ccy": ccy,
            "sector": r.get("sec") or d.get("ind"), "industry": d.get("ind"),
            "ev_sales": mets.get("ev_sales"), "ev_gp": mets.get("ev_gp"),
            "fwd_pe": mets.get("fwd_pe"), "ev_ebitda": mets.get("ev_ebitda"),
            "business_desc": d.get("biz"), "summary": d.get("s"),
            "source_url": d.get("u"), "source_domain": host, "source_bucket": bucket,
        })
    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    return df


def main() -> int:
    if not (RAW / "archive-index.json").exists():
        print(f"raw capture not found at {RAW} — nothing to ingest")
        return 1
    df = ingest()
    print(f"[ingested] {len(df)} situations -> {OUT}")
    print(f"  issues {df.issue.min()}–{df.issue.max()} · {df.country.nunique()} countries · {df.category.nunique()} categories")
    cov = {c: f"{df[c].notna().mean()*100:.0f}%" for c in
           ["ticker", "market_cap_musd", "price", "ev_ebitda", "summary", "industry", "issue_date"]}
    print(f"  coverage: {cov}")
    print(f"  US situations: {(df.country=='US').sum()} · with ticker: {df[df.country=='US'].ticker.notna().sum()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
