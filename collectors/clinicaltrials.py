"""ClinicalTrials.gov Phase-3 pipeline collector — keyless biotech catalyst layer.

For the healthcare themes (obesity_glp1, managed_care, pharma in defensives) the late-stage
clinical PIPELINE is a non-price catalyst the political/contract feeds never see. This pulls the
ClinicalTrials.gov v2 API (clinicaltrials.gov/api/v2/studies — keyless) for Phase-3 studies per
curated INDUSTRY sponsor and records two events per ticker:

  * Phase-3 START  — a new Phase-3 registration (StudyFirstPostDate) — pipeline advancing.
  * Trial HALT     — overallStatus TERMINATED/SUSPENDED/WITHDRAWN (or a whyStopped reason) — a
                     RISK flag (recorded + surfaced as a caution; NOT scored into the bullish
                     convergence weight, by design).

Output: data/clinicaltrials/trials.parquet — append-only, key-deduped per (nct, status). Feeds
the convergence kernel's clinical_phase3_start channel; halts ride the by_ticker record as a
caution metric. Display / context only.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

import pandas as pd

from collectors.base import Adapter, is_connection_error
from lib import config

log = logging.getLogger(__name__)

STUDIES_URL = "https://clinicaltrials.gov/api/v2/studies"
FIELDS = ("NCTId,BriefTitle,OverallStatus,Phase,LeadSponsorName,LeadSponsorClass,"
          "StudyFirstPostDate,LastUpdatePostDate,WhyStopped")
HALT_STATUSES = {"TERMINATED", "SUSPENDED", "WITHDRAWN"}
PACE_S = 0.3


def _sponsor_map() -> dict[str, str]:
    p = config.data_dir() / "clinicaltrials" / "sponsor_ticker.json"
    if not p.exists():
        return {}
    try:
        return (json.loads(p.read_text()) or {}).get("sponsors", {})
    except Exception:  # noqa: BLE001
        return {}


def parse_studies(studies: list[dict], ticker: str) -> list[dict]:
    """Pure: flatten v2 studies into rows for INDUSTRY-sponsored Phase-3 trials."""
    rows = []
    for s in studies or []:
        ps = s.get("protocolSection", {})
        idm, st = ps.get("identificationModule", {}), ps.get("statusModule", {})
        sp, ds = ps.get("sponsorCollaboratorsModule", {}), ps.get("designModule", {})
        if (sp.get("leadSponsor", {}).get("class") or "").upper() != "INDUSTRY":
            continue
        status = (st.get("overallStatus") or "").upper()
        rows.append({
            "ticker": ticker, "nct": idm.get("nctId"),
            "title": (idm.get("briefTitle") or "")[:160],
            "status": status, "phases": ",".join(ds.get("phases", []) or []),
            "first_post": (st.get("studyFirstPostDateStruct") or {}).get("date"),
            "last_update": (st.get("lastUpdatePostDateStruct") or {}).get("date"),
            "why_stopped": (st.get("whyStopped") or None),
            "is_halt": status in HALT_STATUSES,
        })
    return rows


class ClinicalTrialsAdapter(Adapter):
    name = "clinicaltrials"
    group = "clinicaltrials"
    stale_after_days = 7

    def _query(self, sponsor: str) -> list[dict]:
        params = {"query.spons": sponsor, "filter.advanced": "AREA[Phase]PHASE3",
                  "pageSize": 100, "fields": FIELDS, "sort": "LastUpdatePostDate:desc"}
        r = self.http_get(STUDIES_URL, params=params, retries=2, timeout=40)
        return (r.json() or {}).get("studies", [])

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        smap = _sponsor_map()
        if not smap:
            raise ValueError("clinicaltrials: sponsor_ticker.json missing or empty")
        rows, errors = [], 0
        for ticker, term in smap.items():
            try:
                rows.extend(parse_studies(self._query(term), ticker))
                time.sleep(PACE_S)
            except Exception as e:  # noqa: BLE001
                if is_connection_error(e):
                    raise
                errors += 1
                log.debug("clinicaltrials %s (%s): %s", ticker, term, e)
                continue
        if not rows:
            raise RuntimeError(f"clinicaltrials: no Phase-3 studies ({len(smap)} sponsors, {errors} errors)")
        new = pd.DataFrame(rows)
        new["_first_seen"] = datetime.now(timezone.utc).isoformat()
        path = config.data_dir() / "clinicaltrials" / "trials.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        combined = pd.concat([pd.read_parquet(path), new], ignore_index=True) if path.exists() else new
        combined = combined.drop_duplicates(subset=["nct", "status"], keep="first").reset_index(drop=True)
        combined.to_parquet(path)
        n_halt = int(new["is_halt"].sum())
        log.info("clinicaltrials: %d sponsors, +%d rows (%d halts), %d total, %d errors",
                 len(smap), len(new), n_halt, len(combined), errors)
        ingest = pd.DataFrame({"new_rows": [len(new)], "total_rows": [len(combined)]},
                              index=[pd.Timestamp(datetime.now(timezone.utc).date())])
        return {"clinicaltrials__ingest": ingest}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ClinicalTrialsAdapter().fetch()
