"""IPO lock-up terms from EDGAR prospectuses — the Phase-2 overhang data.

The most CAPTURABLE IPO leg (research/IPO_RADAR.md) is the 180-day lock-up expiry:
a deterministic, free-from-the-prospectus date with documented one-sided supply
pressure (Field & Hanka: ~−1.5% / −3% VC-backed 3-day drift, ~40% volume spike).
We read the lock-up length straight from the final prospectus:

  ticker -> CIK            www.sec.gov/files/company_tickers.json (keyless)
  CIK -> filings           data.sec.gov/submissions/CIK{10}.json (keyless, laxer host)
  pick 424B4/424B1/S-1     the final-prospectus form
  fetch the document       www.sec.gov/Archives/... (ENFORCES SEC fair-access: the
                           UA MUST carry a contact email or it 403s — we reuse the
                           email-bearing smart_money.user_agent the 13F collector
                           already uses for the same host)
  regex the lock-up days   "...lock-up... 180 days..." -> 180 (90/180/360 etc.)

DISPLAY-ONLY: the lock-up date feeds an avoid/de-risk calendar, never a score (the
drift is not exploitable net of borrow costs — borrow is scarce/expensive in the
lock-up). Best-effort + capped + cached (data/ipo/lockups.parquet); never raises so
the build survives a walled IP. Driven by scripts/build_ipo (not scripts/collect),
like collectors/ipo_calendar.
"""
from __future__ import annotations

import json
import logging
import re
import time
from collections import Counter
from datetime import datetime, timezone

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{:010d}.json"
ARCHIVE_DOC = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
# final-prospectus forms in preference order (424B* = priced; S-1/F-1 = registration)
PROSPECTUS_FORMS = ("424B4", "424B1", "424B3", "424B5", "424B2",
                    "S-1/A", "S-1", "F-1/A", "F-1")
PLAUSIBLE_LOCKUP = {60, 90, 120, 150, 180, 270, 360, 365}
# High-confidence lock-up-LENGTH phrasings. Tried first because modern lock-ups bury
# early-release triggers ("...released after 90 days if the price exceeds...") next to
# the word "lock-up", which poisons a naive proximity count (Reddit: real 180, proximity
# says 90; these canonical patterns score 180×4 vs 90×2 → 180).
_CANON_PATTERNS = (
    r"lock[- ]?up period of (?:approximately\s*)?(\d{2,3})\s*days",
    r"(\d{2,3})[- ]day lock[- ]?up period",
    r"(\d{2,3})[- ]day lock[- ]?up",
    r"period of (\d{2,3})\s*days (?:after|from|following)[^.]{0,70}?"
    r"(?:prospectus|offering|closing|listing)",
    r"(\d{2,3})\s*days after the date of this prospectus",
    r"(\d{2,3})\s*day restricted period",
)


def _data_dir():
    p = config.data_dir() / "ipo"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _ua() -> str:
    cfg = config.load()
    # www.sec.gov/Archives needs an email-bearing UA; smart_money's is set for exactly
    # this host. Fall back to the edgar UA (works on data.sec.gov) if absent.
    return (cfg.get("smart_money", {}).get("user_agent")
            or cfg.get("edgar", {}).get("user_agent")
            or "Macro Dashboard IPO Radar research@example.org")


def _headers() -> dict:
    return {"User-Agent": _ua(), "Accept-Encoding": "gzip, deflate"}


def _get(session, url: str, timeout: int = 60, retries: int = 2):
    for attempt in range(retries):
        try:
            r = session.get(url, headers=_headers(), timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code in (403, 404):
                return r            # terminal: don't retry a WAF/not-found
        except Exception as e:  # noqa: BLE001
            if attempt == retries - 1:
                log.debug("ipo_prospectus GET failed %s: %s", url[-40:], e)
                return None
            time.sleep(1.0 * (attempt + 1))
    return None


def _ticker_cik_map(session, refresh_days: int = 7) -> dict[str, int]:
    cache = _data_dir() / "ticker_cik.json"
    if cache.exists():
        age = (datetime.now(timezone.utc).timestamp() - cache.stat().st_mtime) / 86400
        if age < refresh_days:
            try:
                return {k: int(v) for k, v in json.loads(cache.read_text()).items()}
            except Exception:  # noqa: BLE001
                pass
    r = _get(session, TICKERS_URL, timeout=30)
    if r is None or r.status_code != 200:
        # fall back to a stale cache if we have one
        if cache.exists():
            try:
                return {k: int(v) for k, v in json.loads(cache.read_text()).items()}
            except Exception:  # noqa: BLE001
                return {}
        return {}
    out: dict[str, int] = {}
    try:
        for row in r.json().values():
            t = str(row.get("ticker", "")).upper().strip()
            if t:
                out[t] = int(row["cik_str"])
    except Exception:  # noqa: BLE001
        return {}
    cache.write_text(json.dumps(out))
    return out


def _find_prospectus(session, cik: int) -> dict | None:
    r = _get(session, SUBMISSIONS.format(cik), timeout=30)
    if r is None or r.status_code != 200:
        return None
    try:
        rec = r.json()["filings"]["recent"]
    except Exception:  # noqa: BLE001
        return None
    forms, accs = rec.get("form", []), rec.get("accessionNumber", [])
    docs, dates = rec.get("primaryDocument", []), rec.get("filingDate", [])
    for pref in PROSPECTUS_FORMS:
        for i, f in enumerate(forms):
            if f == pref and i < len(docs) and docs[i]:
                return {"form": f, "accession": accs[i], "doc": docs[i],
                        "filing_date": dates[i] if i < len(dates) else None}
    return None


def parse_lockup_days(html: str) -> int | None:
    """The lock-up length disclosed in the prospectus. Tries high-confidence
    lock-up-length phrasings first (Counter across them), then falls back to a
    plausible day-count near any 'lock-up' mention. None when nothing is found."""
    t = re.sub(r"<[^>]+>", " ", html)
    t = re.sub(r"\s+", " ", t)

    canon: list[int] = []
    for pat in _CANON_PATTERNS:
        for d in re.findall(pat, t, re.I):
            di = int(d)
            if di in PLAUSIBLE_LOCKUP:
                canon.append(di)
    if canon:
        return Counter(canon).most_common(1)[0][0]

    prox: list[int] = []
    for m in re.finditer(r"lock[- ]?up", t, re.I):
        window = t[m.start():m.start() + 400]
        for d in re.findall(r"\b(\d{2,3})\b[\s-]?day", window):
            di = int(d)
            if di in PLAUSIBLE_LOCKUP:
                prox.append(di)
    if not prox:
        return None
    return Counter(prox).most_common(1)[0][0]


def _cache_path():
    return _data_dir() / "lockups.parquet"


def load_lockups() -> pd.DataFrame:
    p = _cache_path()
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_parquet(p)
    if "ticker" in df.columns:
        df = df.set_index("ticker")
    return df


def fetch_lockups(tickers: list[str], cap: int = 12, refresh_days: int = 30) -> pd.DataFrame:
    """Resolve + parse lock-up days for `tickers` (capped per run, cached). Reuses
    fresh cache rows; best-effort and never raises."""
    import requests
    tickers = [str(t).upper().strip() for t in tickers if t]
    existing = load_lockups()
    session = requests.Session()

    def fresh(t: str) -> bool:
        if existing.empty or t not in existing.index:
            return False
        ts = existing.loc[t].get("as_of")
        try:
            return (datetime.now(timezone.utc) - pd.to_datetime(ts)).days < refresh_days
        except Exception:  # noqa: BLE001
            return False

    todo = [t for t in dict.fromkeys(tickers) if not fresh(t)][:cap]
    if not todo:
        return existing

    cmap = _ticker_cik_map(session)
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for t in todo:
        cik = cmap.get(t)
        if not cik:
            rows.append({"ticker": t, "cik": None, "form": None, "filing_date": None,
                         "lockup_days": None, "source": "cik-not-found", "as_of": now})
            continue
        pros = _find_prospectus(session, cik)
        if not pros:
            rows.append({"ticker": t, "cik": cik, "form": None, "filing_date": None,
                         "lockup_days": None, "source": "no-prospectus", "as_of": now})
            continue
        url = ARCHIVE_DOC.format(cik=cik, acc=pros["accession"].replace("-", ""), doc=pros["doc"])
        d = _get(session, url, timeout=60)
        days = parse_lockup_days(d.text) if (d is not None and d.status_code == 200) else None
        src = (f"{pros['form']} prospectus" if days is not None
               else ("blocked" if (d is not None and d.status_code == 403) else "lockup-not-found"))
        rows.append({"ticker": t, "cik": cik, "form": pros["form"],
                     "filing_date": pros["filing_date"], "lockup_days": days,
                     "source": src, "as_of": now})
        time.sleep(0.3)

    fresh_df = pd.DataFrame(rows).set_index("ticker")
    if not existing.empty:
        out = pd.concat([existing[~existing.index.isin(fresh_df.index)], fresh_df])
    else:
        out = fresh_df
    out.to_parquet(_cache_path())
    n_ok = int(out["lockup_days"].notna().sum()) if "lockup_days" in out else 0
    log.info("ipo_prospectus: lockups cache now %d names (%d with parsed days)", len(out), n_ok)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    import sys
    ts = [t.upper() for t in (sys.argv[1:] or ["SPCX", "RDDT", "ARM"])]
    df = fetch_lockups(ts, cap=len(ts), refresh_days=0)
    for t in ts:
        if t in df.index:
            r = df.loc[t]
            print(f"{t:6} cik={r['cik']} {r['form']} {r['filing_date']} "
                  f"lockup={r['lockup_days']} ({r['source']})")
