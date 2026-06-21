"""Schedule 13D/13G beneficial-ownership sweep — the free EDGAR source behind
engine/beneficial_ownership.py's per-ticker ownership-regime read.

The special-situations desk's events store only sweeps a short window, so this
collector pulls SC 13D/13G(/A) directly from the EDGAR **daily index** over a
configurable lookback, maps the subject CIK→ticker via the SEC company_tickers
master, and (capped + paced) parses the FILED-BY entity from each filing's SGML
header so the engine can tag custodian/index filers (the aggregation guard).

Append-only, idempotent on accession → data/beneficial_ownership/filings.parquet.
Keyless; degrades to 'failed' only if EDGAR is unreachable.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from collectors.base import Adapter, is_connection_error
from lib import config

log = logging.getLogger(__name__)

_DAILY_IDX = "https://www.sec.gov/Archives/edgar/daily-index/{yr}/QTR{q}/form.{ds}.idx"
_ARCH = "https://www.sec.gov/Archives/edgar/data"
# the daily index spells these out ("SCHEDULE 13D/A"); normalize to the canonical
# short form ("SC 13D/A") that engine/beneficial_ownership.py matches on.
_IDX_FORMS = {
    "SCHEDULE 13D": "SC 13D", "SCHEDULE 13D/A": "SC 13D/A",
    "SCHEDULE 13G": "SC 13G", "SCHEDULE 13G/A": "SC 13G/A",
}
LOOKBACK_DAYS = 45            # calendar days swept per run (idempotent-merged)
MAX_ENRICH = 500              # filer-header fetches per run (newest-first)
GROUP = "beneficial_ownership"


def _cache_path():
    return config.data_dir() / GROUP / "filings.parquet"


def _sec_ua() -> str:
    """SEC fair-access requires a contact email in the UA (the default 'sponsors'
    UA 403s). Reuse the smart_money 13F UA which already carries one."""
    c = config.load()
    return ((c.get("smart_money", {}) or {}).get("user_agent")
            or "Macro Dashboard research longr2512@gmail.com")


def _cik_ticker() -> dict[int, str]:
    """Full SEC CIK→ticker master (reuses the edgar_8k cache/fetch)."""
    try:
        from collectors.edgar_8k import _company_tickers
        data = _company_tickers() or {}
    except Exception:  # noqa: BLE001
        return {}
    out: dict[int, str] = {}
    for e in (data.values() if isinstance(data, dict) else data):
        try:
            cik, tk = int(e.get("cik_str")), e.get("ticker")
        except (TypeError, ValueError):
            continue
        if tk:
            out.setdefault(cik, str(tk).upper())
    return out


def _qtr(d: date) -> int:
    return (d.month - 1) // 3 + 1


def parse_idx(text: str) -> list[dict]:
    """13D/13G rows from a form.YYYYMMDD.idx (fixed-width:
    Form | Company | CIK | Date Filed | File Name). PURE."""
    out: list[dict] = []
    lines = text.splitlines()
    start = next((i + 1 for i, ln in enumerate(lines) if set(ln.strip()) == {"-"}), 0)
    for ln in lines[start:]:
        if not ln.strip():
            continue
        parts = re.split(r"\s{2,}", ln.strip())
        if len(parts) < 5 or parts[0].strip() not in _IDX_FORMS:
            continue
        accession = Path(parts[-1].strip()).stem
        d = parts[-2].strip()
        out.append({
            "accession": accession,
            "form_type": _IDX_FORMS[parts[0].strip()],   # -> canonical "SC 13D/A"
            "company": " ".join(parts[1:-3]).strip(),
            "cik": parts[-3].strip(),
            "date_filed": f"{d[:4]}-{d[4:6]}-{d[6:8]}",
        })
    return out


def filer_from_header(text: str) -> str | None:
    """The FILED-BY reporting person from a filing's SGML header — the entity that
    crossed 5% (vs SUBJECT COMPANY = the issuer). First FILED-BY block wins. PURE."""
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if "FILED BY" in ln.upper():
            for ln2 in lines[i + 1:i + 10]:
                if "COMPANY CONFORMED NAME" in ln2.upper():
                    return ln2.split(":", 1)[1].strip() or None
    return None


class BeneficialOwnershipAdapter(Adapter):
    name = "beneficial_ownership"
    group = GROUP
    stale_after_days = 4

    def _business_days(self, n_cal: int) -> list[date]:
        today = datetime.now(timezone.utc).date()
        return [today - timedelta(days=i) for i in range(n_cal)
                if (today - timedelta(days=i)).weekday() < 5]

    def _fetch_header(self, cik: str, accession: str) -> str | None:
        acc_nodash = accession.replace("-", "")
        url = f"{_ARCH}/{cik}/{acc_nodash}/{accession}.txt"
        try:
            import requests
            r = requests.get(url, headers={"User-Agent": _sec_ua()},
                             timeout=30, stream=True)
            if r.status_code != 200:
                return None
            buf = ""
            for chunk in r.iter_content(chunk_size=4096, decode_unicode=True):
                buf += chunk if isinstance(chunk, str) else chunk.decode("latin-1", "ignore")
                if "</SEC-HEADER>" in buf or len(buf) > 16000:
                    break
            return buf
        except Exception as e:  # noqa: BLE001
            if is_connection_error(e):
                raise
            return None

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        cik_tk = _cik_ticker()
        cache_p = _cache_path()
        prev = pd.read_parquet(cache_p) if cache_p.exists() else pd.DataFrame()
        have = set(prev["accession"].astype(str)) if not prev.empty else set()

        # 1) sweep the daily index for new 13D/13G filings
        rows: list[dict] = []
        days = self._business_days(LOOKBACK_DAYS if not full_history else 270)
        idx_ok = 0
        for d in days:
            url = _DAILY_IDX.format(yr=d.year, q=_qtr(d), ds=d.strftime("%Y%m%d"))
            try:
                r = self.http_get(url, retries=2, timeout=30,
                                  headers={"User-Agent": _sec_ua()})
            except Exception as e:  # noqa: BLE001
                if is_connection_error(e) and idx_ok == 0:
                    raise
                continue                       # weekend/holiday/no-index -> skip
            idx_ok += 1
            for row in parse_idx(r.text):
                if row["accession"] in have:
                    continue
                row["ticker"] = cik_tk.get(int(row["cik"])) if row["cik"].isdigit() else None
                rows.append(row)
            time.sleep(0.1)

        # dedup within this run (a filing can appear once); newest-first for enrichment
        fresh = pd.DataFrame(rows)
        if not fresh.empty:
            fresh = fresh.drop_duplicates("accession").sort_values("date_filed", ascending=False)

        # 2) enrich filer from the SGML header (capped, paced)
        from engine.beneficial_ownership import classify_filer_type
        filers, ftypes = [], []
        enriched = 0
        for r in fresh.itertuples(index=False):
            name = None
            if enriched < MAX_ENRICH:
                hdr = self._fetch_header(str(r.cik), str(r.accession))
                if hdr:
                    name = filer_from_header(hdr)
                enriched += 1
                time.sleep(0.1)
            filers.append(name)
            ftypes.append(classify_filer_type(name))
        if not fresh.empty:
            fresh["filer"] = filers
            fresh["filer_type"] = ftypes
            fresh["_seen"] = datetime.now(timezone.utc).isoformat()

        if fresh.empty:
            if not prev.empty:
                hb = pd.DataFrame({"new": [0], "total": [len(prev)]},
                                  index=[pd.Timestamp(datetime.now(timezone.utc).date())])
                return {"beneficial_ownership__ingest": hb}
            raise RuntimeError("beneficial_ownership: no 13D/13G filings swept")

        combined = pd.concat([prev, fresh], ignore_index=True) if not prev.empty else fresh
        combined = combined.drop_duplicates("accession", keep="last").reset_index(drop=True)
        cache_p.parent.mkdir(parents=True, exist_ok=True)
        combined.to_parquet(cache_p)
        n_tk = int(fresh["ticker"].notna().sum())
        log.info("beneficial_ownership: +%d filings (%d→ticker, %d filer-enriched), cache=%d",
                 len(fresh), n_tk, enriched, len(combined))
        hb = pd.DataFrame({"new": [len(fresh)], "enriched": [enriched]},
                          index=[pd.Timestamp(datetime.now(timezone.utc).date())])
        return {"beneficial_ownership__ingest": hb}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    BeneficialOwnershipAdapter().fetch()
