"""SAM.gov contract-OPPORTUNITY collector — the earliest federal procurement signal.

Pre-solicitations and solicitations are posted on SAM.gov weeks to 12+ months before a contract
award appears on USAspending — so this leads even the contracts radar leg for defense / space /
semiconductor / nuclear / critical-minerals themes. It is THEME-level only (pre-award has no
awardee ticker): each NAICS code maps to basket(s), and the count of EARLY notices (recent vs
prior) is the observable.

Source: GET https://api.sam.gov/opportunities/v2/search (api_key, ncode single NAICS, ptype,
postedFrom/To MM/dd/yyyy). GATED: a free key needs a SAM.gov entity registration, so absent
SAM_API_KEY the adapter reports 'blocked' and the radar 'sam_presolicitation' theme_event leg is
silently skipped — it activates the moment the key lands.

Output: data/sam_gov/opp_velocity.parquet — pre-aggregated per-basket {recent_count, prior_count}.
NAICS -> basket map: data/sam_gov/naics_themes.json.

W0d addition: new_programs() pure function detects first-ever-seen NAICS codes per basket and
writes a ledger (data/sam_gov/naics_seen.json) used by engine/theme_activity._load_new_program_events()
to surface new-program regime annotations.  Appends new events to data/theme_activity/program_ledger.parquet.
Limitation: the velocity() function (and its on-disk output) remains count-only — new_programs()
requires the full raw opps list, available only inside fetch().
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from collectors.base import Adapter, is_connection_error
from lib import config

log = logging.getLogger(__name__)

SEARCH_URL = "https://api.sam.gov/opportunities/v2/search"
RECENT_D = 90
PRIOR_D = 90
# notice types that are EARLY (pre-award); SAM `type` is a full string — substring match.
EARLY_TYPES = ("presol", "solicitation", "sources sought", "combined")


def _naics_themes() -> dict[str, list[str]]:
    p = config.data_dir() / "sam_gov" / "naics_themes.json"
    if not p.exists():
        return {}
    try:
        return (json.loads(p.read_text()) or {}).get("naics", {})
    except Exception:  # noqa: BLE001
        return {}


def new_programs(opps: list[dict], naics_map: dict[str, list[str]],
                 seen_path: Path) -> list[dict]:
    """Pure (except disk I/O): detect first-ever-seen NAICS codes per basket.

    Reads the persistent seen_path JSON ({basket_id: [naics, ...]}) and emits an event dict
    for each NAICS code that is new for a basket this run.  Writes the updated set back to
    seen_path.  Idempotent: re-running with the same opps produces [] after the first call.

    Returns a list of {basket_id, naics_or_cfda, source, first_seen_date, title, type} dicts
    for all newly-seen codes.  Empty when opps or naics_map is empty."""
    if not opps or not naics_map:
        return []
    seen: dict[str, list[str]] = {}
    if seen_path.exists():
        try:
            seen = json.loads(seen_path.read_text()) or {}
        except Exception:  # noqa: BLE001
            seen = {}
    events: list[dict] = []
    today_str = str(pd.Timestamp.now().date())
    for o in opps:
        naics = str(o.get("naicsCode") or "").strip()
        if not naics:
            continue
        baskets = naics_map.get(naics) or naics_map.get(naics[:6]) or []
        for b in baskets:
            known = seen.setdefault(b, [])
            if naics not in known:
                known.append(naics)
                events.append({
                    "basket_id": b,
                    "naics_or_cfda": naics,
                    "source": "sam_gov",
                    "first_seen_date": today_str,
                    "title": str(o.get("title") or "")[:120],
                    "type": str(o.get("type") or ""),
                })
    if events:
        seen_path.parent.mkdir(parents=True, exist_ok=True)
        seen_path.write_text(json.dumps(seen, indent=2))
    return events


def velocity(opps: list[dict], naics_map: dict[str, list[str]], *, today=None) -> pd.DataFrame:
    """Pure: roll early-notice opportunities up to per-basket recent-vs-prior counts via NAICS."""
    if not opps or not naics_map:
        return pd.DataFrame()
    t0 = pd.Timestamp(today) if today is not None else pd.Timestamp(datetime.now(timezone.utc).date())
    rec_lo, pri_lo = t0 - pd.Timedelta(days=RECENT_D), t0 - pd.Timedelta(days=RECENT_D + PRIOR_D)
    counts: dict[str, list[int]] = {}
    for o in opps:
        typ = str(o.get("type") or "").lower()
        if not any(t in typ for t in EARLY_TYPES):
            continue
        naics = str(o.get("naicsCode") or "").strip()
        baskets = naics_map.get(naics) or naics_map.get(naics[:6]) or []
        if not baskets:
            continue
        posted = pd.to_datetime(o.get("postedDate"), errors="coerce")
        if pd.isna(posted):
            continue
        if rec_lo < posted <= t0:
            slot = 0
        elif pri_lo < posted <= rec_lo:
            slot = 1
        else:
            continue
        for b in baskets:
            counts.setdefault(b, [0, 0])[slot] += 1
    rows = [{"basket_id": b, "recent_count": rc, "prior_count": pc, "n_members": 0, "covered": ""}
            for b, (rc, pc) in counts.items() if rc or pc]
    return pd.DataFrame(rows).set_index("basket_id") if rows else pd.DataFrame()


class SamGovAdapter(Adapter):
    name = "sam_gov"
    group = "sam_gov"
    stale_after_days = 10

    def __init__(self) -> None:
        self.api_key = config.secret("SAM_API_KEY")
        if not self.api_key:
            self.expected_failure = "SAM_API_KEY not set"

    def _search(self, naics: str, posted_from: str, posted_to: str) -> list[dict]:
        params = {"api_key": self.api_key, "ncode": naics, "limit": 1000,
                  "postedFrom": posted_from, "postedTo": posted_to}
        r = self.http_get(SEARCH_URL, params=params, retries=2, timeout=60)
        return (r.json() or {}).get("opportunitiesData", [])

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        if not self.api_key:
            raise RuntimeError("SAM_API_KEY not set")
        naics_map = _naics_themes()
        if not naics_map:
            raise ValueError("sam_gov: naics_themes.json missing or empty")
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=RECENT_D + PRIOR_D + 10)
        pf, pt = start.strftime("%m/%d/%Y"), end.strftime("%m/%d/%Y")
        opps, errors = [], 0
        for naics in naics_map:
            try:
                opps.extend(self._search(naics, pf, pt))
                time.sleep(0.5)
            except Exception as e:  # noqa: BLE001
                if is_connection_error(e):
                    raise
                errors += 1
                log.debug("sam_gov NAICS %s: %s", naics, e)
                continue
        if not opps:
            raise RuntimeError(f"sam_gov: no opportunities ({len(naics_map)} NAICS, {errors} errors)")
        vel = velocity(opps, naics_map)
        if not vel.empty:
            p = config.data_dir() / "sam_gov" / "opp_velocity.parquet"
            p.parent.mkdir(parents=True, exist_ok=True)
            vel.to_parquet(p)
        # W0d: new-program detection — first-seen NAICS per basket; appends to program_ledger
        seen_path = config.data_dir() / "sam_gov" / "naics_seen.json"
        np_events = new_programs(opps, naics_map, seen_path)
        if np_events:
            ledger_path = config.data_dir() / "theme_activity" / "program_ledger.parquet"
            ledger_path.parent.mkdir(parents=True, exist_ok=True)
            new_df = pd.DataFrame(np_events)
            if ledger_path.exists():
                existing = pd.read_parquet(ledger_path)
                new_df = pd.concat([existing, new_df], ignore_index=True)
            new_df.to_parquet(ledger_path, index=False)
            log.info("sam_gov: %d new NAICS programs detected", len(np_events))
        log.info("sam_gov: %d opportunities over %d NAICS -> %d baskets, %d errors",
                 len(opps), len(naics_map), len(vel), errors)
        ingest = pd.DataFrame({"opps": [len(opps)], "baskets": [len(vel)]},
                              index=[pd.Timestamp(end)])
        return {"sam_gov__ingest": ingest}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    SamGovAdapter().fetch()
