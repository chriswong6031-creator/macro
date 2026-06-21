"""Simpler Grants.gov FOA (Funding Opportunity Announcement) collector — the EARLIEST
federal-money signal.

Grant FOAs (DOE/IRA/CHIPS/NSF/DARPA/NIH notices of funding opportunity) are posted weeks to
months BEFORE any award is obligated on USAspending — so this leads the contracts/assistance
signal for energy / nuclear / semiconductor / quantum / space themes by a wide margin. It is a
THEME-level observable only: pre-award there is no recipient ticker, so it feeds the Divergence
Radar (engine.theme_activity 'grants_foa' theme_event leg), not the per-ticker convergence kernel.

Source: POST https://api.simpler.grants.gov/v1/opportunities/search (header X-API-Key). A free
key is minutes away via a Login.gov account at simpler.grants.gov/developer. GATED: with no
GRANTS_GOV_API_KEY the adapter reports 'blocked' (never a hard failure), the parquet is absent,
and the radar source is silently skipped — it activates the moment the key lands.

Output: data/grants_gov/foa_velocity.parquet — pre-aggregated per-basket {recent_count,
prior_count} (recent FOA_RECENT_D days vs the prior window), the 'theme_event' frame the fuser
reads. CFDA -> basket mapping is curated in data/grants_gov/cfda_themes.json.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from collectors.base import Adapter, is_connection_error
from lib import config

log = logging.getLogger(__name__)

SEARCH_URL = "https://api.simpler.grants.gov/v1/opportunities/search"
FOA_RECENT_D = 90      # FOAs are lumpy (a big round then silence) -> wide windows
FOA_PRIOR_D = 90
PAGE_SIZE = 100
MAX_PAGES = 20


def _cfda_themes() -> dict[str, list[str]]:
    p = config.data_dir() / "grants_gov" / "cfda_themes.json"
    if not p.exists():
        return {}
    try:
        return (json.loads(p.read_text()) or {}).get("cfda", {})
    except Exception:  # noqa: BLE001
        return {}


def velocity(opps: list[dict], cfda_map: dict[str, list[str]], *, today=None) -> pd.DataFrame:
    """Pure: roll a list of opportunity dicts up to per-basket recent-vs-prior FOA counts.
    Each opp -> its CFDA listing(s) -> basket(s); counted once per basket per opp."""
    if not opps or not cfda_map:
        return pd.DataFrame()
    t0 = pd.Timestamp(today) if today is not None else pd.Timestamp(datetime.now(timezone.utc).date())
    rec_lo = t0 - pd.Timedelta(days=FOA_RECENT_D)
    pri_lo = t0 - pd.Timedelta(days=FOA_RECENT_D + FOA_PRIOR_D)
    counts: dict[str, list[int]] = {}  # basket -> [recent, prior]
    for o in opps:
        listings = o.get("opportunity_assistance_listings") or []
        cfdas = {str(l.get("assistance_listing_number")).strip() for l in listings if l.get("assistance_listing_number")}
        baskets = {b for c in cfdas for b in cfda_map.get(c, [])}
        if not baskets:
            continue
        post = pd.to_datetime((o.get("summary") or {}).get("post_date"), errors="coerce")
        if pd.isna(post):
            continue
        if rec_lo < post <= t0:
            slot = 0
        elif pri_lo < post <= rec_lo:
            slot = 1
        else:
            continue
        for b in baskets:
            counts.setdefault(b, [0, 0])[slot] += 1
    rows = [{"basket_id": b, "recent_count": rc, "prior_count": pc, "n_members": 0, "covered": ""}
            for b, (rc, pc) in counts.items() if rc or pc]
    return pd.DataFrame(rows).set_index("basket_id") if rows else pd.DataFrame()


class GrantsGovAdapter(Adapter):
    name = "grants_gov"
    group = "grants_gov"
    stale_after_days = 10

    def __init__(self) -> None:
        self.api_key = config.secret("GRANTS_GOV_API_KEY")
        if not self.api_key:
            self.expected_failure = "GRANTS_GOV_API_KEY not set"

    def _search_page(self, cfdas: list[str], start: str, end: str, offset: int) -> dict | None:
        body = {
            "filters": {
                "assistance_listing_number": {"one_of": cfdas},
                "post_date": {"start_date": start, "end_date": end},
            },
            "pagination": {"page_offset": offset, "page_size": PAGE_SIZE,
                           "sort_order": [{"order_by": "post_date", "sort_direction": "descending"}]},
        }
        r = requests.post(SEARCH_URL, json=body, timeout=60,
                          headers={"X-API-Key": self.api_key, "Content-Type": "application/json",
                                   "User-Agent": config.load()["sponsors"]["user_agent"]})
        if r.status_code in (429, 500, 502, 503, 504):
            raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
        r.raise_for_status()
        return r.json()

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        if not self.api_key:
            raise RuntimeError("GRANTS_GOV_API_KEY not set")
        cfda_map = _cfda_themes()
        if not cfda_map:
            raise ValueError("grants_gov: cfda_themes.json missing or empty")
        cfdas = sorted(cfda_map)
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=FOA_RECENT_D + FOA_PRIOR_D + 14)  # small cushion

        opps: list[dict] = []
        for page in range(1, MAX_PAGES + 1):
            try:
                data = self._search_page(cfdas, start.isoformat(), end.isoformat(), page)
            except Exception as e:  # noqa: BLE001
                if is_connection_error(e):
                    raise
                log.warning("grants_gov page %d failed: %s", page, e)
                break
            batch = (data or {}).get("data") or []
            opps.extend(batch)
            if len(batch) < PAGE_SIZE:
                break

        if not opps:
            raise RuntimeError("grants_gov: search returned no opportunities (check key/filters)")

        vel = velocity(opps, cfda_map)
        if not vel.empty:
            p = config.data_dir() / "grants_gov" / "foa_velocity.parquet"
            p.parent.mkdir(parents=True, exist_ok=True)
            vel.to_parquet(p)
        log.info("grants_gov: %d FOAs over %d CFDAs -> %d baskets", len(opps), len(cfdas), len(vel))
        ingest = pd.DataFrame(
            {"foas": [len(opps)], "baskets": [len(vel)]},
            index=[pd.Timestamp(datetime.now(timezone.utc).date())],
        )
        return {"grants_gov__ingest": ingest}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    GrantsGovAdapter().fetch()
