"""SEC Form-4 insider-transaction collector (Phase 4 conviction layer).

The SEC publishes "Insider Transactions Data Sets" — one zip per quarter holding
TSV tables for every Form 3/4/5: SUBMISSION (accession -> issuer ticker, filing
date) and NONDERIV_TRANS (the actual transactions: code, shares, price,
acquired/disposed). One download therefore lets us aggregate NET OPEN-MARKET
insider buying vs selling per issuer for an entire quarter — the conviction
signal the passive-ETF residual cannot give.

The bulk sets are published quarterly, so this is a SLOW read of the most recent
COMPLETED quarter (not real-time). We keep only open-market purchases (code P)
and sales (code S) — grants, option exercises and gifts are excluded as noise —
and map the issuer ticker onto our universe. Written ticker-indexed to
data/sec_insider/insider.parquet; cached (the quarterly file changes rarely).
"""
from __future__ import annotations

import io
import json
import logging
import zipfile
from datetime import datetime, timezone

import pandas as pd

from lib import config

log = logging.getLogger(__name__)


def _cfg() -> dict:
    return config.load()["sec_insider"]


def _headers() -> dict:
    return {"User-Agent": _cfg()["user_agent"]}


def _candidate_quarters(n: int) -> list[str]:
    """['2026q2','2026q1',...] newest-first (calendar quarters; the build resolves
    which is actually published by trying them in order)."""
    now = datetime.now(timezone.utc)
    y, q = now.year, (now.month - 1) // 3 + 1
    out = []
    for _ in range(n):
        out.append(f"{y}q{q}")
        q -= 1
        if q == 0:
            q, y = 4, y - 1
    return out


def _download_quarter() -> tuple[str, zipfile.ZipFile] | None:
    import requests
    for q in _candidate_quarters(_cfg()["lookback_quarters"]):
        url = _cfg()["zip_url"].format(q=q)
        try:
            r = requests.get(url, headers=_headers(), timeout=90)
            if r.status_code == 200 and r.content[:2] == b"PK":
                return q, zipfile.ZipFile(io.BytesIO(r.content))
        except Exception as e:  # noqa: BLE001
            log.debug("insider zip %s failed: %s", q, e)
    return None


def _read_tsv(zf: zipfile.ZipFile, name: str, usecols: list[str]) -> pd.DataFrame:
    fn = next((n for n in zf.namelist() if n.upper().endswith(name.upper())), None)
    if not fn:
        return pd.DataFrame()
    with zf.open(fn) as fh:
        df = pd.read_csv(fh, sep="\t", dtype=str, usecols=lambda c: c.upper() in
                         {u.upper() for u in usecols}, on_bad_lines="skip")
    df.columns = [c.upper() for c in df.columns]
    return df


def _universe() -> set[str]:
    out: set[str] = set()
    for grp in ("breadth", "smallcap_breadth", "midcap_breadth"):
        p = config.data_dir() / grp / "_closes_cache.parquet"
        if p.exists():
            out.update(pd.read_parquet(p).columns)
    return out


def fetch_insider(force: bool = False, max_age_days: int = 7) -> pd.DataFrame | None:
    cache = config.data_dir() / "sec_insider" / "insider.parquet"
    cache.parent.mkdir(parents=True, exist_ok=True)
    if not force and cache.exists():
        age = (datetime.now(timezone.utc).timestamp() - cache.stat().st_mtime) / 86400.0
        if age < max_age_days:
            log.info("insider cache fresh (%.1fd)", age)
            return pd.read_parquet(cache)

    dl = _download_quarter()
    if not dl:
        log.warning("sec insider: no quarterly dataset reachable (sec.gov blocked?)")
        return pd.read_parquet(cache) if cache.exists() else None
    quarter, zf = dl
    out = _parse(quarter, zf, _universe())
    if out is None or out.empty:
        return pd.read_parquet(cache) if cache.exists() else None
    out.to_parquet(cache)
    (config.data_dir() / "sec_insider" / "_meta.json").write_text(
        json.dumps({"built": datetime.now(timezone.utc).isoformat(), "quarter": quarter,
                    "n": int(len(out))}))
    log.info("sec insider: %d universe issuers, quarter %s", len(out), quarter)
    return out


def _parse(quarter: str, zf: "zipfile.ZipFile", universe: set[str] | None) -> pd.DataFrame | None:
    """Aggregate net OPEN-MARKET insider buying/selling per issuer from a quarter's
    SUBMISSION + NONDERIV_TRANS tables. Pure (no I/O) so it is unit-testable with a
    synthetic zip."""
    sub = _read_tsv(zf, "SUBMISSION.tsv",
                    ["ACCESSION_NUMBER", "FILING_DATE", "ISSUERTRADINGSYMBOL", "ISSUERNAME"])
    trans = _read_tsv(zf, "NONDERIV_TRANS.tsv",
                      ["ACCESSION_NUMBER", "TRANS_CODE", "TRANS_SHARES",
                       "TRANS_PRICEPERSHARE", "TRANS_ACQUIRED_DISP_CD"])
    if sub.empty or trans.empty:
        log.warning("sec insider: missing SUBMISSION/NONDERIV_TRANS in %s", quarter)
        return None

    codes = set(_cfg()["open_market_codes"])
    trans = trans[trans["TRANS_CODE"].isin(codes)].copy()
    for c in ("TRANS_SHARES", "TRANS_PRICEPERSHARE"):
        trans[c] = pd.to_numeric(trans[c], errors="coerce")
    trans["usd"] = (trans["TRANS_SHARES"] * trans["TRANS_PRICEPERSHARE"]).abs()
    trans = trans[trans["usd"] >= _cfg()["min_trade_usd"]]

    df = trans.merge(sub[["ACCESSION_NUMBER", "ISSUERTRADINGSYMBOL"]],
                     on="ACCESSION_NUMBER", how="left")
    df = df.dropna(subset=["ISSUERTRADINGSYMBOL"])
    df["ticker"] = df["ISSUERTRADINGSYMBOL"].str.upper().str.strip()
    if df.empty:
        return None

    g = df.groupby("ticker")
    out = pd.DataFrame({
        "buy_usd": g.apply(lambda x: x.loc[x["TRANS_CODE"] == "P", "usd"].sum()),
        "sell_usd": g.apply(lambda x: x.loc[x["TRANS_CODE"] == "S", "usd"].sum()),
        "n_buys": g.apply(lambda x: int((x["TRANS_CODE"] == "P").sum())),
        "n_sells": g.apply(lambda x: int((x["TRANS_CODE"] == "S").sum())),
    })
    out["net_usd"] = out["buy_usd"] - out["sell_usd"]
    out["quarter"] = quarter
    if universe:
        out = out[out.index.isin(universe)]
    return out[(out["buy_usd"] > 0) | (out["sell_usd"] > 0)]
