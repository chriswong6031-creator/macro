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
    # SEC fair-access wants a descriptive UA with a real contact. A real address
    # (preferred) can be supplied privately via SEC_CONTACT_EMAIL without committing
    # it; otherwise fall back to the example.com placeholder in config (NB: a UA
    # containing 'github.com' is 403'd by SEC's WAF). The Accept header keeps us off
    # the bot heuristics that return the rate-threshold page.
    import os
    contact = os.environ.get("SEC_CONTACT_EMAIL")
    ua = f"Macro Dashboard Research {contact}" if contact else _cfg()["user_agent"]
    return {"User-Agent": ua, "Accept": "application/zip, */*"}


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


def _built_age_days(meta_p) -> float | None:
    """Age of the insider cache in days, from _meta.json's `built` stamp —
    NEVER file mtime. On CI runners a checkout rewrites files with
    mtime = checkout time, so a committed months-old cache always looks
    brand-new by mtime and the refresh short-circuits forever (the
    polygon-universe frozen-cache class, #2690; this cache froze at its
    2026-06-14 fill the same way). _meta.json is written only on a
    successful fetch, so it IS the fetch-date stamp. Missing/unreadable
    meta returns None — the caller treats that as stale and refetches."""
    try:
        built = json.loads(meta_p.read_text()).get("built")
        if not built:
            return None
        built_dt = datetime.fromisoformat(str(built))
        if built_dt.tzinfo is None:
            built_dt = built_dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - built_dt).total_seconds() / 86400.0
    except Exception as e:  # noqa: BLE001
        log.warning("sec insider: cannot read built stamp from %s (%s) — treating as stale",
                    meta_p, e)
        return None


def fetch_insider(force: bool = False, max_age_days: int = 7) -> pd.DataFrame | None:
    cache = config.data_dir() / "sec_insider" / "insider.parquet"
    cache.parent.mkdir(parents=True, exist_ok=True)
    if not force and cache.exists():
        age = _built_age_days(cache.parent / "_meta.json")
        if age is not None and age < max_age_days:
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


# =============================================================================
# Point-in-time PANEL backfill (Phase-0 factor research).
#
# The aggregate above is a single-quarter leaderboard. To VALIDATE insider
# buying as a cross-sectional alpha factor we need the per-transaction history
# keyed on the FILING_DATE (when the trade became public — the only leak-free
# alignment date), plus the reporting owner's identity and role. Those let us
# build the signals the literature says actually carry edge: opportunistic-vs-
# routine (Cohen–Malloy–Pomorski), distinct-insider CLUSTERS, role weighting,
# and size-normalisation — none of which a net-dollar sum can express.
#
# Written long to data/sec_insider/insider_panel.parquet, with each quarter
# cached under data/sec_insider/panel/<q>.parquet so the backfill is resumable
# and the multi-GB of raw zips are parsed-then-discarded (never kept on disk).
# =============================================================================

_DATE_FMT = "%d-%b-%Y"  # SEC bulk dates look like '31-MAR-2025'
# Originals only — amendments (4/A, 5/A) restate an earlier filing and would
# double-count the same open-market trade.
_PANEL_FORMS = {"4", "5"}
# Owner-role tokens are comma-joined in RPTOWNER_RELATIONSHIP, e.g.
# 'Director,Officer,TenPercentOwner'.
_PANEL_COLS = [
    "ticker", "issuer_cik", "filing_date", "trans_date", "rptownercik",
    "code", "direct", "is_officer", "is_director", "is_tenpct", "title",
    "shares", "price", "usd", "quarter",
]


def _quarters_from(start: str) -> list[str]:
    """['2006q1','2006q2',...,<current>] oldest-first from a 'YYYYqN' start."""
    sy, sq = int(start[:4]), int(start[5])
    now = datetime.now(timezone.utc)
    ey, eq = now.year, (now.month - 1) // 3 + 1
    out, y, q = [], sy, sq
    while (y, q) <= (ey, eq):
        out.append(f"{y}q{q}")
        q += 1
        if q == 5:
            q, y = 1, y + 1
    return out


_SESSION = None


def _session():
    global _SESSION
    if _SESSION is None:
        import requests
        _SESSION = requests.Session()
        _SESSION.headers.update(_headers())
    return _SESSION


def _get_zip(quarter: str, retries: int = 8) -> tuple[str, "zipfile.ZipFile"] | None:
    """Download one quarter's form345 zip. Distinguishes a transient 403 'Request
    Rate Threshold Exceeded' (patient exponential backoff) from a real 404 (quarter
    not published / before the data set began -> permanent skip, returns None).

    SEC throttles per source IP; on a shared egress IP unrelated traffic can push
    the aggregate over the 10 req/s ceiling, so the backoff is generous (up to ~60s
    a try, with jitter) and the loop is long — this is a slow background backfill."""
    import random
    import time
    url = _cfg()["zip_url"].format(q=quarter)
    for attempt in range(retries):
        try:
            r = _session().get(url, timeout=120)
        except Exception as e:  # noqa: BLE001
            log.debug("insider panel %s attempt %d errored: %s", quarter, attempt, e)
            time.sleep(min(60.0, 5.0 * (attempt + 1)))
            continue
        if r.status_code == 200 and r.content[:2] == b"PK":
            return quarter, zipfile.ZipFile(io.BytesIO(r.content))
        if r.status_code == 404:
            return None  # genuinely absent — caller skips permanently
        # 403 rate-threshold or any other transient: patient backoff with jitter
        wait = min(60.0, 5.0 * (1.7 ** attempt)) + random.uniform(0, 2.0)
        log.debug("insider panel %s status %d (attempt %d, wait %.0fs)",
                  quarter, r.status_code, attempt, wait)
        time.sleep(wait)
    log.warning("insider panel %s: exhausted retries", quarter)
    return None


def _parse_panel(quarter: str, zf: "zipfile.ZipFile") -> pd.DataFrame:
    """Per-transaction long panel of open-market insider trades for one quarter.
    Pure (no I/O) so it is unit-testable against a synthetic zip."""
    sub = _read_tsv(zf, "SUBMISSION.tsv",
                    ["ACCESSION_NUMBER", "FILING_DATE", "DOCUMENT_TYPE",
                     "ISSUERCIK", "ISSUERTRADINGSYMBOL"])
    own = _read_tsv(zf, "REPORTINGOWNER.tsv",
                    ["ACCESSION_NUMBER", "RPTOWNERCIK", "RPTOWNER_RELATIONSHIP",
                     "RPTOWNER_TITLE"])
    trans = _read_tsv(zf, "NONDERIV_TRANS.tsv",
                      ["ACCESSION_NUMBER", "TRANS_DATE", "TRANS_CODE",
                       "TRANS_SHARES", "TRANS_PRICEPERSHARE",
                       "DIRECT_INDIRECT_OWNERSHIP"])
    if sub.empty or trans.empty or own.empty:
        log.warning("sec insider panel: missing table(s) in %s", quarter)
        return pd.DataFrame(columns=_PANEL_COLS)

    sub = sub[sub["DOCUMENT_TYPE"].isin(_PANEL_FORMS)]
    codes = set(_cfg()["open_market_codes"])
    trans = trans[trans["TRANS_CODE"].isin(codes)].copy()
    for c in ("TRANS_SHARES", "TRANS_PRICEPERSHARE"):
        trans[c] = pd.to_numeric(trans[c], errors="coerce")
    trans["usd"] = (trans["TRANS_SHARES"] * trans["TRANS_PRICEPERSHARE"]).abs()
    trans = trans[trans["usd"] >= _cfg()["min_trade_usd"]]
    if trans.empty:
        return pd.DataFrame(columns=_PANEL_COLS)

    # One Form-4 usually has a single reporting owner; joint filers are rare, so
    # keep the first owner per accession for a clean 1:1 identity/role join.
    own = own.drop_duplicates("ACCESSION_NUMBER")
    df = (trans.merge(sub, on="ACCESSION_NUMBER", how="inner")
                .merge(own, on="ACCESSION_NUMBER", how="left"))
    df = df.dropna(subset=["ISSUERTRADINGSYMBOL"])
    if df.empty:
        return pd.DataFrame(columns=_PANEL_COLS)

    df["ticker"] = df["ISSUERTRADINGSYMBOL"].str.upper().str.strip()
    df["filing_date"] = pd.to_datetime(df["FILING_DATE"], format=_DATE_FMT, errors="coerce")
    df["trans_date"] = pd.to_datetime(df["TRANS_DATE"], format=_DATE_FMT, errors="coerce")
    rel = df["RPTOWNER_RELATIONSHIP"].fillna("")
    df["is_officer"] = rel.str.contains("Officer", case=False)
    df["is_director"] = rel.str.contains("Director", case=False)
    df["is_tenpct"] = rel.str.contains("TenPercent", case=False)
    df["direct"] = df["DIRECT_INDIRECT_OWNERSHIP"].eq("D")
    df["quarter"] = quarter
    out = df.rename(columns={
        "ISSUERCIK": "issuer_cik", "RPTOWNERCIK": "rptownercik",
        "RPTOWNER_TITLE": "title", "TRANS_CODE": "code",
        "TRANS_SHARES": "shares", "TRANS_PRICEPERSHARE": "price",
    })[_PANEL_COLS]
    return out.dropna(subset=["filing_date"]).reset_index(drop=True)


def backfill_panel(start: str = "2006q1", force: bool = False,
                   sleep_s: float = 0.4) -> pd.DataFrame | None:
    """Resumable backfill of the per-transaction insider panel from `start` to the
    current quarter. Each quarter is cached to data/sec_insider/panel/<q>.parquet
    and skipped on re-run unless `force`. Returns the concatenated panel (also
    written to insider_panel.parquet)."""
    import time
    base = config.data_dir() / "sec_insider"
    pdir = base / "panel"
    pdir.mkdir(parents=True, exist_ok=True)

    quarters = _quarters_from(start)
    log.info("insider panel backfill: %d quarters %s..%s", len(quarters), quarters[0], quarters[-1])
    for q in quarters:
        qcache = pdir / f"{q}.parquet"
        if qcache.exists() and not force:
            continue
        dl = _get_zip(q)
        if dl is None:
            log.info("insider panel: %s unavailable (skip)", q)
            continue
        _, zf = dl
        part = _parse_panel(q, zf)
        part.to_parquet(qcache)
        log.info("insider panel: %s -> %d transactions", q, len(part))
        time.sleep(sleep_s)  # respect SEC fair-access pacing between quarters

    parts = []
    for q in quarters:
        qcache = pdir / f"{q}.parquet"
        if qcache.exists():
            df = pd.read_parquet(qcache)
            if not df.empty:
                parts.append(df)
    if not parts:
        log.warning("insider panel: no quarters parsed")
        return None
    panel = pd.concat(parts, ignore_index=True).sort_values("filing_date").reset_index(drop=True)
    panel.to_parquet(base / "insider_panel.parquet")
    (base / "_panel_meta.json").write_text(json.dumps({
        "built": datetime.now(timezone.utc).isoformat(),
        "quarters": [q for q in quarters if (pdir / f"{q}.parquet").exists()],
        "n_transactions": int(len(panel)),
        "n_tickers": int(panel["ticker"].nunique()),
        "date_min": str(panel["filing_date"].min().date()),
        "date_max": str(panel["filing_date"].max().date()),
    }, indent=2))
    log.info("insider panel: %d transactions, %d tickers, %s..%s",
             len(panel), panel["ticker"].nunique(),
             panel["filing_date"].min().date(), panel["filing_date"].max().date())
    return panel
