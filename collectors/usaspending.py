"""USAspending federal contract awards -> monthly obligations per ticker.

The ONE non-price observable behind the Divergence Radar (engine/radar.py): "is
the government actually spending money on this theme's companies?" — laid against
price/relative-strength so the radar can flag where free observables DIVERGE from
what the tape already prices (the variant-perception edge), and stay silent when
they agree.

Source: USAspending.gov `spending_over_time` (KEYLESS public API). For each curated
federally-exposed recipient (data/usaspending/recipient_aliases.json) we pull the
monthly obligated $ on prime CONTRACT awards (award_type_codes A/B/C/D) over a
trailing window and store a wide LONG-history frame data/usaspending/obligations.parquet
([month x ticker] -> obligated USD). Append-only via store.upsert.

HONEST caveats (surfaced on the page): awards are LAGGED (the most recent 1-2 months
are incomplete and the radar drops them); recipient_search_text is a fuzzy substring
match; coverage is NARROW by design (defense / space / nuclear / uranium / DoD
critical-minerals / gov-software only). Display-only context, never a trade trigger.
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

SOT_URL = "https://api.usaspending.gov/api/v2/search/spending_over_time/"
CONTRACT_TYPES = ["A", "B", "C", "D"]  # definitive contract, purchase/delivery order, BPA call
REQUEST_PACING_S = 0.3


def _aliases_path():
    return config.data_dir() / "usaspending" / "recipient_aliases.json"


def load_aliases() -> dict:
    """{ticker: {"name": str, "search": str}} curated federal-exposure map."""
    p = _aliases_path()
    if not p.exists():
        return {}
    try:
        return (json.loads(p.read_text()) or {}).get("recipients", {})
    except Exception:  # noqa: BLE001
        return {}


def _period_to_ts(tp: dict):
    """USAspending monthly buckets are keyed by federal {fiscal_year, month} where
    `month` is the FISCAL-year index (1 = October, ... 12 = September), NOT the
    calendar month — e.g. FY2026 month 9 == June 2026. Convert to a calendar
    month-start: fiscal months 1-3 (Oct-Dec) fall in the PRIOR calendar year."""
    try:
        fy = int(tp.get("fiscal_year"))
        fm = int(tp.get("month"))
    except (TypeError, ValueError):
        return None
    if not 1 <= fm <= 12:
        return None
    cal_month = ((fm + 8) % 12) + 1        # fm 1->10 (Oct), 4->1 (Jan), 12->9 (Sep)
    cal_year = fy - 1 if fm <= 3 else fy
    return pd.Timestamp(year=cal_year, month=cal_month, day=1)


class UsaspendingAdapter(Adapter):
    name = "usaspending"
    group = "usaspending"
    stale_after_days = 45  # monthly + lagged source; refreshing more often is no-op churn

    def _post(self, url: str, body: dict, retries: int = 3, timeout: int = 60) -> dict | None:
        headers = {
            "User-Agent": config.load()["sponsors"]["user_agent"],
            "Content-Type": "application/json",
        }
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                r = requests.post(url, json=body, headers=headers, timeout=timeout)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
                r.raise_for_status()
                return r.json()
            except Exception as e:  # noqa: BLE001 — retried, then surfaced
                last_exc = e
                if attempt < retries - 1:
                    time.sleep(2.0 * (attempt + 1))
        raise last_exc  # type: ignore[misc]

    def _recipient_monthly(self, search: str, start: str, end: str) -> pd.Series | None:
        body = {
            "group": "month",
            "filters": {
                "time_period": [{"start_date": start, "end_date": end}],
                "recipient_search_text": [search],
                "award_type_codes": CONTRACT_TYPES,
            },
        }
        data = self._post(SOT_URL, body)
        if not data:
            return None
        rows: dict[pd.Timestamp, float] = {}
        for r in data.get("results", []) or []:
            ts = _period_to_ts(r.get("time_period") or {})
            amt = r.get("aggregated_amount")
            if ts is not None and amt is not None:
                try:
                    rows[ts] = float(amt)
                except (TypeError, ValueError):
                    continue
        if not rows:
            return None
        return pd.Series(rows).sort_index()

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        aliases = load_aliases()
        if not aliases:
            raise ValueError("usaspending: recipient_aliases.json missing or empty")
        months = 60 if full_history else 24
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=int(months * 30.5))

        frames: list[pd.Series] = []
        errors = 0
        for tkr, meta in aliases.items():
            search = (meta or {}).get("search") or (meta or {}).get("name") or tkr
            try:
                ser = self._recipient_monthly(search, start.isoformat(), end.isoformat())
                time.sleep(REQUEST_PACING_S)
            except Exception as e:  # noqa: BLE001
                errors += 1
                if is_connection_error(e):
                    raise  # host unreachable -> fail the whole source fast, don't grind 40x
                log.warning("usaspending %s (%s) failed: %s", tkr, search, e)
                continue
            if ser is not None and not ser.empty:
                frames.append(ser.rename(tkr))

        if not frames:
            raise ValueError(f"usaspending: no recipient series returned (errors={errors})")

        wide = pd.concat(frames, axis=1).sort_index()
        log.info("usaspending: %d/%d recipients, %d months, %d errors",
                 len(frames), len(aliases), len(wide), errors)
        self._write_meta(len(frames), len(aliases), errors, wide)
        return {"obligations": wide}

    def _write_meta(self, n_ok: int, n_total: int, errors: int, wide: pd.DataFrame) -> None:
        p = config.data_dir() / "usaspending" / "_meta.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            p.write_text(json.dumps({
                "built": datetime.now(timezone.utc).isoformat(),
                "recipients_ok": n_ok,
                "recipients_total": n_total,
                "errors": errors,
                "months": int(len(wide)),
                "last_month": str(wide.index.max().date()) if len(wide) else None,
            }, indent=2))
        except Exception as e:  # noqa: BLE001 — sidecar is best-effort
            log.debug("usaspending meta write failed: %s", e)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    frames = UsaspendingAdapter().fetch(full_history=False)
    df = frames["obligations"]
    print(f"\nobligations frame: {df.shape[0]} months x {df.shape[1]} recipients")
    print("recipients:", ", ".join(df.columns))
    print("\nlast 6 months ($M):")
    print((df.tail(6) / 1e6).round(1).to_string())
