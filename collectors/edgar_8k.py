"""SEC EDGAR 8-K MATERIAL-EVENT collector — the filing-time latency channel.

8-K current reports are filed within ~4 business days of a material corporate event, so
they lead the news narrative AND the tape. This collector reads the structured SEC
submissions feed (data.sec.gov/submissions/CIK##########.json — keyless, the `items` field
is machine-readable, not text-parsed) for every narrative-basket member, keeps only MATERIAL
item codes (new material agreements, acquisitions, financings, leadership changes, Reg-FD /
other material events — NOT routine earnings 2.02 / voting 5.07 / exhibits 9.01), and writes:

  * data/edgar/material_8k_events.parquet  — append-only, key-deduped per accession (PIT +
      _first_seen). Per-TICKER convergence channel (engine.altdata `material_events`).
  * data/edgar/material_8k_velocity.parquet — derived per-BASKET count, recent-60d vs
      prior-60d (the 'theme_event' Divergence-Radar leg in engine.theme_activity).

The ONLY new source that touches all 31 themes — including the healthcare blind spot, where
FDA actions land as 8-K item 8.01. Keyless; reuses edgar.py's cached CIK map + fair-access UA.
Display / context only.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone

import pandas as pd
import requests

from collectors.base import Adapter, is_connection_error
from lib import config

log = logging.getLogger(__name__)

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{:010d}.json"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
# SEC fair-access requires a descriptive name + contact email; www.sec.gov 403s a UA without
# one (data.sec.gov is more lenient). RFC2606 placeholder — same pattern as edgar_trumpflow.
_SEC_UA = "macro-dashboard admin@macro-dashboard.example.com"


def _sec_get_json(url: str, retries: int = 3, timeout: int = 30) -> dict | None:
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(url, headers={"User-Agent": _SEC_UA, "Accept-Encoding": "gzip, deflate"}, timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    if last is not None and is_connection_error(last):
        raise last
    return None


def _company_tickers() -> dict | None:
    """SEC ticker->CIK file, cached locally (shared with collectors/edgar.py). Fetched with a
    fair-access UA so www.sec.gov doesn't 403; falls back to the cache on any fetch failure."""
    cache = config.data_dir() / "edgar" / "company_tickers.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text())
        except Exception:  # noqa: BLE001
            pass
    data = _sec_get_json(TICKERS_URL)
    if data:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(data))
    return data


def _cik_map(universe: list[str]) -> dict[str, int]:
    """ticker -> CIK from SEC company_tickers.json (exact + dash/dot variants)."""
    data = _company_tickers()
    if not data:
        return {}
    sec = {row["ticker"].upper(): int(row["cik_str"]) for row in data.values()}
    out: dict[str, int] = {}
    for t in universe:
        u = t.upper()
        for cand in (u, u.replace("-", "."), u.replace(".", "-"), u.split("-")[0], u.split(".")[0]):
            if cand in sec:
                out[t] = sec[cand]
                break
    return out
# material item codes worth a signal (activity, not routine housekeeping):
#   1.01 material definitive agreement · 2.01 completion of acquisition ·
#   2.03 creation of a direct financial obligation · 5.02 director/officer change ·
#   7.01 Reg-FD disclosure · 8.01 other material event (where FDA/major news lands)
MATERIAL_ITEMS = {"1.01", "2.01", "2.03", "5.02", "7.01", "8.01"}
_ITEM_RE = re.compile(r"\d\.\d{2}")
RECENT_D = 60
PRIOR_D = 60
PACE_S = 0.12  # SEC fair-access: <=10 req/s


def _membership() -> dict:
    try:
        return json.loads((config.data_dir() / "baskets" / "membership.json").read_text()).get("baskets", {})
    except Exception:  # noqa: BLE001
        return {}


def _universe(mem: dict) -> list[str]:
    seen, out = set(), []
    for b in mem.values():
        for m in b.get("members", []):
            t = m.get("ticker")
            if t and not m.get("removed") and t not in seen:
                seen.add(t)
                out.append(t)
    return out


class Edgar8KAdapter(Adapter):
    name = "edgar_8k"
    group = "edgar"
    stale_after_days = 5

    def _events_path(self):
        p = config.data_dir() / "edgar" / "material_8k_events.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def _velocity_path(self):
        return config.data_dir() / "edgar" / "material_8k_velocity.parquet"

    def _pull_ticker(self, ticker: str, cik: int) -> list[dict]:
        """Material-8K rows for one CIK from the structured submissions feed."""
        data = _sec_get_json(SUBMISSIONS_URL.format(int(cik)), retries=3)
        if not data:
            return []
        rec = (data.get("filings") or {}).get("recent") or {}
        forms = rec.get("form") or []
        out = []
        for i, form in enumerate(forms):
            if form != "8-K":
                continue
            raw = (rec.get("items") or [None] * len(forms))[i] or ""
            codes = set(_ITEM_RE.findall(raw))
            mat = sorted(codes & MATERIAL_ITEMS)
            if not mat:
                continue
            out.append({
                "ticker": ticker, "cik": int(cik), "form": form,
                "filing_date": (rec.get("filingDate") or [None] * len(forms))[i],
                "items": ",".join(mat),
                "accession": (rec.get("accessionNumber") or [None] * len(forms))[i],
            })
        return out

    def _merge_events(self, new: pd.DataFrame) -> pd.DataFrame:
        new = new.copy()
        new["_first_seen"] = datetime.now(timezone.utc).isoformat()
        path = self._events_path()
        if path.exists():
            old = pd.read_parquet(path)
            combined = pd.concat([old, new], ignore_index=True)
        else:
            combined = new
        combined = combined.drop_duplicates(subset=["accession"], keep="first").reset_index(drop=True)
        combined.to_parquet(path)
        return combined

    def _velocity(self, events: pd.DataFrame, mem: dict) -> pd.DataFrame:
        """Per-basket material-8K counts: recent RECENT_D days vs the prior PRIOR_D."""
        ev = events.copy()
        ev["d"] = pd.to_datetime(ev["filing_date"], errors="coerce")
        ev = ev[ev["d"].notna()]
        t0 = ev["d"].max() if not ev.empty else pd.Timestamp(datetime.now(timezone.utc).replace(tzinfo=None))
        rec_lo = t0 - pd.Timedelta(days=RECENT_D)
        pri_lo = t0 - pd.Timedelta(days=RECENT_D + PRIOR_D)
        rows = []
        for bid, b in mem.items():
            members = {m.get("ticker") for m in b.get("members", []) if m.get("ticker") and not m.get("removed")}
            if not members:
                continue
            sub = ev[ev["ticker"].isin(members)]
            rec = sub[(sub["d"] > rec_lo) & (sub["d"] <= t0)]
            pri = sub[(sub["d"] > pri_lo) & (sub["d"] <= rec_lo)]
            if rec.empty and pri.empty:
                continue
            covered = sorted(rec["ticker"].unique())
            rows.append({"basket_id": bid, "recent_count": int(len(rec)), "prior_count": int(len(pri)),
                         "n_members": int(len(covered)), "covered": ",".join(covered)})
        return pd.DataFrame(rows).set_index("basket_id") if rows else pd.DataFrame()

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        mem = _membership()
        universe = _universe(mem)
        if not universe:
            raise ValueError("edgar_8k: no basket members to scan")
        cikmap = _cik_map(universe)
        if not cikmap:
            raise ValueError("edgar_8k: could not map any ticker -> CIK (company_tickers.json unavailable)")

        events, errors = [], 0
        for ticker, cik in cikmap.items():
            try:
                events.extend(self._pull_ticker(ticker, cik))
                time.sleep(PACE_S)
            except Exception as e:  # noqa: BLE001
                errors += 1
                if is_connection_error(e):
                    raise  # host down -> fail fast, don't grind 345x
                log.debug("edgar_8k %s (CIK %s) failed: %s", ticker, cik, e)
                continue

        if not events:
            raise ValueError(f"edgar_8k: no material 8-K rows returned (errors={errors})")
        df = pd.DataFrame(events)
        merged = self._merge_events(df)
        velocity = self._velocity(merged, mem)
        if not velocity.empty:
            velocity.to_parquet(self._velocity_path())
        log.info("edgar_8k: %d/%d tickers mapped, +%d events scanned, %d total, %d baskets, %d errors",
                 len(cikmap), len(universe), len(df), len(merged), len(velocity), errors)
        ingest = pd.DataFrame(
            {"new_scanned": [len(df)], "total_rows": [len(merged)], "baskets": [len(velocity)]},
            index=[pd.Timestamp(datetime.now(timezone.utc).date())],
        )
        return {"edgar_8k__ingest": ingest}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    Edgar8KAdapter().fetch()
