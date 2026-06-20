"""openFDA Drugs@FDA approval collector — the healthcare blind spot Quiver can't see.

Drug approvals are hard, dated public catalysts that the political/insider/contract feeds miss
entirely. This pulls the Drugs@FDA dataset (api.fda.gov/drug/drugsfda.json — KEYLESS at
1,000 req/day, plenty for ~20 sponsor queries; FDA_API_KEY optional for a higher cap) per
curated drug-maker sponsor and records two catalyst events per ticker:

  * NEW approval        — an ORIGINAL application reaching status AP (a newly approved product;
                          class TYPE 1/2 = a new molecular entity, the strongest tell).
  * LABEL expansion     — a SUPPLEMENT with class EFFICACY reaching AP (an sNDA that widens the
                          addressable market — e.g. a GLP-1 getting a new indication).

Feeds the per-ticker alt-data convergence kernel (fda_approval / fda_label_expansion channels).
Output: data/openfda/approvals.parquet — append-only, key-deduped per
(application_number, submission_status_date, submission_type). Sponsor->ticker map is curated in
data/openfda/sponsor_ticker.json. Display / context only; never raises into the build.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from collectors.base import Adapter, is_connection_error
from lib import config

log = logging.getLogger(__name__)

DRUGSFDA_URL = "https://api.fda.gov/drug/drugsfda.json"
PACE_S = 0.4  # keyless openFDA: 240 req/min, 1000/day — gentle pacing


def _sponsor_map() -> dict[str, str]:
    p = config.data_dir() / "openfda" / "sponsor_ticker.json"
    if not p.exists():
        return {}
    try:
        return (json.loads(p.read_text()) or {}).get("sponsors", {})
    except Exception:  # noqa: BLE001
        return {}


def _classify(sub_type: str, status: str, klass: str) -> str | None:
    """Map a Drugs@FDA submission to a catalyst kind, or None if it isn't one."""
    if (status or "").upper() != "AP":
        return None
    st = (sub_type or "").upper()
    kl = (klass or "").upper()
    if st == "ORIG":
        return "approval"                               # a newly approved product
    if st == "SUPPL" and "EFFICACY" in kl:
        return "label_expansion"                        # sNDA widening the indication
    return None                                         # LABELING / MANUF / routine -> ignore


def parse_results(results: list[dict], ticker: str, sponsor_token: str, *, since: str) -> list[dict]:
    """Pure: flatten one sponsor's Drugs@FDA results into catalyst rows >= `since` (YYYYMMDD)."""
    rows = []
    for app in results or []:
        appno = app.get("application_number")
        brand = None
        for prod in app.get("products") or []:
            if prod.get("brand_name"):
                brand = prod["brand_name"]
                break
        for sub in app.get("submissions") or []:
            date = (sub.get("submission_status_date") or "")[:8]
            if not date or date < since:
                continue
            kind = _classify(sub.get("submission_type"), sub.get("submission_status"), sub.get("submission_class_code"))
            if not kind:
                continue
            rows.append({
                "ticker": ticker, "sponsor": app.get("sponsor_name") or sponsor_token,
                "application_number": appno, "submission_type": sub.get("submission_type"),
                "class_code": sub.get("submission_class_code"), "status_date": date,
                "kind": kind, "drug_name": brand,
            })
    return rows


class OpenFdaAdapter(Adapter):
    name = "openfda"
    group = "openfda"
    stale_after_days = 7

    def __init__(self) -> None:
        self.api_key = config.secret("FDA_API_KEY")  # optional — keyless works at 1k/day

    def _events_path(self):
        p = config.data_dir() / "openfda" / "approvals.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def _query(self, token: str, since: str, until: str) -> list[dict]:
        params = {
            "search": f'sponsor_name:"{token}" AND submissions.submission_status_date:[{since} TO {until}]',
            "limit": 100,
        }
        if self.api_key:
            params["api_key"] = self.api_key
        # openFDA returns 404 for ZERO matches (a normal state for clinical-stage names) — treat
        # that as empty, never an error to retry. Only retry the genuine transient codes.
        headers = {"User-Agent": config.load()["sponsors"]["user_agent"]}
        last = None
        for attempt in range(3):
            try:
                r = requests.get(DRUGSFDA_URL, params=params, headers=headers, timeout=40)
                if r.status_code == 404:
                    return []
                if r.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
                r.raise_for_status()
                return (r.json() or {}).get("results", [])
            except Exception as e:  # noqa: BLE001
                last = e
                if attempt < 2:
                    time.sleep(2.0 * (attempt + 1))
        raise last  # type: ignore[misc]

    def _merge(self, new: pd.DataFrame) -> pd.DataFrame:
        new = new.copy()
        new["_first_seen"] = datetime.now(timezone.utc).isoformat()
        path = self._events_path()
        if path.exists():
            combined = pd.concat([pd.read_parquet(path), new], ignore_index=True)
        else:
            combined = new
        combined = combined.drop_duplicates(
            subset=["application_number", "status_date", "submission_type"], keep="first"
        ).reset_index(drop=True)
        combined.to_parquet(path)
        return combined

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        smap = _sponsor_map()
        if not smap:
            raise ValueError("openfda: sponsor_ticker.json missing or empty")
        days = 365 * 5 if full_history else 400
        end = datetime.now(timezone.utc).date()
        since = (end - timedelta(days=days)).strftime("%Y%m%d")
        until = end.strftime("%Y%m%d")

        rows, errors, hits = [], 0, 0
        for ticker, token in smap.items():
            try:
                results = self._query(token, since, until)
                hits += 1 if results else 0
                rows.extend(parse_results(results, ticker, token, since=since))
                time.sleep(PACE_S)
            except Exception as e:  # noqa: BLE001
                # openFDA returns 404 for zero matches (clinical-stage names) — not an error
                if is_connection_error(e):
                    raise
                errors += 1
                log.debug("openfda %s (%s): %s", ticker, token, e)
                continue

        if not rows:
            # not a hard failure: no recent approvals across the watched sponsors is a valid state
            log.info("openfda: no approval/label-expansion events in window (%d sponsors, %d errors)",
                     len(smap), errors)
            ingest = pd.DataFrame({"events": [0], "sponsors_hit": [hits]},
                                  index=[pd.Timestamp(end)])
            return {"openfda__ingest": ingest}

        merged = self._merge(pd.DataFrame(rows))
        n_appr = sum(1 for r in rows if r["kind"] == "approval")
        log.info("openfda: +%d events (%d new approvals, %d label-exp) from %d/%d sponsors, %d total, %d errors",
                 len(rows), n_appr, len(rows) - n_appr, hits, len(smap), len(merged), errors)
        ingest = pd.DataFrame({"events": [len(rows)], "total_rows": [len(merged)], "sponsors_hit": [hits]},
                              index=[pd.Timestamp(end)])
        return {"openfda__ingest": ingest}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    OpenFdaAdapter().fetch(full_history=True)
