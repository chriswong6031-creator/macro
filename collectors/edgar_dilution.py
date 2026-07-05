"""SEC EDGAR dilution / refinancing-wall collector.

Sweeps the EDGAR daily-index (form.YYYYMMDD.idx) for shelf registrations
(S-3, S-3ASR, S-3/A) and prospectus supplements (424B1–B5) — the filings
that signal primary equity issuance or refinancing events.

S-3 / 424B* are absent from EFTS full-text search (verified), so this uses
the daily-index sweep pattern from collectors/beneficial_ownership.py:141-166.

Output: append-only data/edgar/dilution_events.parquet, deduped by accession.
Columns: accession, cik, ticker, form, filing_date (PIT stamp), _first_seen (UTC iso).

Pacing: 0.12s between requests; retries 3 with 1.5*(attempt+1) backoff.
UA: from collectors.edgar via edgar._cfg()['user_agent'].

Backfill: trailing ~90 calendar days on first run; nightly accrual forward.
Registered in scripts/collect.py as host='sec', _SLOW member.

Display-only principle: this store is context for bottom_sensors.py — it ranks,
gates, and alerts nothing.  Deduplication is within our own store only (424B4/B5
appear in ipo_prospectus.py, special_situations.py, edgar_trumpflow.py with
different purposes; we do not touch their stores).
"""
from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from collectors.base import Adapter, is_connection_error

log = logging.getLogger(__name__)

# EDGAR daily-index URL — same pattern as beneficial_ownership.py
_DAILY_IDX = "https://www.sec.gov/Archives/edgar/daily-index/{yr}/QTR{q}/form.{ds}.idx"

# Forms we care about (dilution / refinancing-wall signals).
# The daily index spells forms with exact names — no normalisation needed here
# because we map them to canonical short forms in our store.
_SHELF_FORMS = {
    "S-3",
    "S-3ASR",
    "S-3/A",
}
_PROSPECTUS_FORMS = {
    "424B1",
    "424B2",
    "424B3",
    "424B4",
    "424B5",
}
_ALL_FORMS = _SHELF_FORMS | _PROSPECTUS_FORMS

# Trailing calendar days swept on first run (bounded backfill).
LOOKBACK_DAYS_FIRST = 90
# Incremental window for subsequent nightly runs (idempotent-merged).
LOOKBACK_DAYS_NIGHTLY = 7

GROUP = "edgar"
_STORE_FILE = "dilution_events.parquet"

_PACE_S = 0.12  # SEC fair-access: ≤10 req/s


def _store_path() -> Path:
    from lib import config
    return config.data_dir() / GROUP / _STORE_FILE


def _ua() -> str:
    """SEC-compliant UA via edgar._cfg() — the edgar_13f/edgar.py pattern."""
    try:
        from collectors.edgar import _cfg
        return _cfg()["user_agent"]
    except Exception:  # noqa: BLE001
        # Fallback: edgar.py may not be importable in tests without full config.
        return "Macro Dashboard research longr2512@gmail.com"


def _qtr(d: date) -> int:
    return (d.month - 1) // 3 + 1


def _cik_map() -> dict[int, str]:
    """CIK → ticker from SEC company_tickers.json (edgar_8k.py pattern)."""
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


def parse_dilution_idx(text: str) -> list[dict]:
    """Extract dilution-relevant rows from a form.YYYYMMDD.idx.

    The daily index is fixed-width text:
      Form Type | Company Name | CIK | Date Filed | File Name

    Returns list of dicts with keys: accession, cik, form, filing_date.
    PURE function — no network calls.
    """
    out: list[dict] = []
    lines = text.splitlines()
    # Skip header lines (up to and including the separator line of dashes)
    start = next((i + 1 for i, ln in enumerate(lines) if set(ln.strip()) == {"-"}), 0)
    for ln in lines[start:]:
        if not ln.strip():
            continue
        # Fixed-width fields are separated by 2+ spaces.
        parts = re.split(r"\s{2,}", ln.strip())
        if len(parts) < 5:
            continue
        form_raw = parts[0].strip()
        if form_raw not in _ALL_FORMS:
            continue
        # File path is the last field; stem = accession number with dashes
        file_path = parts[-1].strip()
        accession = Path(file_path).stem  # e.g. "0001234567-23-000001"
        date_str = parts[-2].strip()      # YYYYMMDD
        cik_str = parts[-3].strip()
        out.append({
            "accession": accession,
            "cik": cik_str,
            "form": form_raw,
            "filing_date": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}",
        })
    return out


class EdgarDilutionAdapter(Adapter):
    """Nightly SEC daily-index sweep for S-3/S-3ASR/S-3/A and 424B1-B5 filings."""

    name = "edgar_dilution"
    group = GROUP
    stale_after_days = 4

    def _business_days(self, n_cal: int) -> list[date]:
        today = datetime.now(timezone.utc).date()
        return [
            today - timedelta(days=i)
            for i in range(n_cal)
            if (today - timedelta(days=i)).weekday() < 5
        ]

    def _fetch_idx(self, d: date, ua: str) -> list[dict] | None:
        """Fetch one daily-index file and parse dilution rows.  Returns None on skip."""
        url = _DAILY_IDX.format(yr=d.year, q=_qtr(d), ds=d.strftime("%Y%m%d"))
        retries = 3
        last_exc = None
        for attempt in range(retries):
            try:
                r = self.http_get(url, retries=1, timeout=30,
                                  headers={"User-Agent": ua,
                                           "Accept-Encoding": "gzip, deflate"})
                return parse_dilution_idx(r.text)
            except Exception as e:  # noqa: BLE001
                last_exc = e
                if is_connection_error(e):
                    raise
                if attempt < retries - 1:
                    time.sleep(1.5 * (attempt + 1))
        # Non-connection failure (e.g. 404 for a weekend/holiday) → skip
        log.debug("edgar_dilution: idx skip %s: %s", d, last_exc)
        return None

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        ua = _ua()
        cik_tk = _cik_map()

        store_p = _store_path()
        prev = pd.read_parquet(store_p) if store_p.exists() else pd.DataFrame()
        have: set[str] = set(prev["accession"].astype(str)) if not prev.empty else set()

        # First run (no existing store): backfill ~90 days.
        # Subsequent runs: 7-day window (idempotent-safe because we dedup by accession).
        lookback = LOOKBACK_DAYS_FIRST if prev.empty else LOOKBACK_DAYS_NIGHTLY
        days = self._business_days(lookback)

        rows: list[dict] = []
        idx_ok = 0
        now_iso = datetime.now(timezone.utc).isoformat()

        for d in days:
            parsed = self._fetch_idx(d, ua)
            if parsed is None:
                continue
            idx_ok += 1
            for row in parsed:
                if row["accession"] in have:
                    continue
                cik_int = int(row["cik"]) if row["cik"].isdigit() else None
                row["ticker"] = cik_tk.get(cik_int) if cik_int is not None else None
                row["_first_seen"] = now_iso
                rows.append(row)
            time.sleep(_PACE_S)

        if not rows:
            if not prev.empty:
                hb = pd.DataFrame(
                    {"new": [0], "total": [len(prev)]},
                    index=[pd.Timestamp(datetime.now(timezone.utc).date())],
                )
                return {"edgar_dilution__ingest": hb}
            if idx_ok == 0:
                raise RuntimeError("edgar_dilution: no daily-index files fetched")
            # idx fetched but zero new rows (all already seen)
            hb = pd.DataFrame(
                {"new": [0], "total": [0]},
                index=[pd.Timestamp(datetime.now(timezone.utc).date())],
            )
            return {"edgar_dilution__ingest": hb}

        fresh = pd.DataFrame(rows)
        fresh = fresh.drop_duplicates("accession", keep="last")
        # Ensure consistent column order
        fresh = fresh[["accession", "cik", "ticker", "form", "filing_date", "_first_seen"]]

        combined = (
            pd.concat([prev, fresh], ignore_index=True) if not prev.empty else fresh
        )
        combined = combined.drop_duplicates("accession", keep="last").reset_index(drop=True)

        # Atomic write: tmp + replace
        store_p.parent.mkdir(parents=True, exist_ok=True)
        tmp_p = store_p.with_suffix(".tmp.parquet")
        combined.to_parquet(tmp_p)
        tmp_p.replace(store_p)

        n_tk = int(fresh["ticker"].notna().sum())
        log.info(
            "edgar_dilution: +%d filings (%d→ticker, %d idx-days), cache=%d",
            len(fresh), n_tk, idx_ok, len(combined),
        )
        hb = pd.DataFrame(
            {"new": [len(fresh)], "ticker_mapped": [n_tk]},
            index=[pd.Timestamp(datetime.now(timezone.utc).date())],
        )
        return {"edgar_dilution__ingest": hb}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    EdgarDilutionAdapter().fetch()
