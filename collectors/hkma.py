"""HKMA peg-funding mechanics — the Hong Kong liquidity drain behind the peg.

The single most HK-unique signal there is: when the HKD hits the 7.85 weak-side
Convertibility Undertaking, the HKMA sells USD / buys HKD to defend it, which
mechanically *shrinks* the banking system's Aggregate Balance — the real cause of
HIBOR spikes and HSI funding headwinds. The USDHKD level alone (already collected)
shows the peg position; this adds the actual mechanics.

Source: HKMA's keyless public Open API (api.hkma.gov.hk), daily-monetary-statistics.
One GET returns the Aggregate (closing) Balance, overnight + 1-month HIBOR, the
trade-weighted HKD index (TWI), the base rate, and the convertibility band — all
HK-native, current to the latest business day, no key. Verified 2026-06-13
(closing_balance 53,886; HIBOR-O/N 1.97; see research/HK_DATA_AUDIT.md).

Stored under group `hkma`, one parquet `interbank_liquidity`:
  agg_balance (HK$mn) · hibor_on · hibor_1m · twi · base_rate
"""
from __future__ import annotations

import logging

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

# HKMA record field -> stored column
FIELDS = {
    "closing_balance": "agg_balance",
    "hibor_overnight": "hibor_on",
    "hibor_fixing_1m": "hibor_1m",
    "twi": "twi",
    "disc_win_base_rate": "base_rate",
}


class HkmaAdapter(Adapter):
    name = "hkma"
    group = "hkma"
    stale_after_days = 4    # daily series, but HK holidays + publish lag

    def __init__(self) -> None:
        self.cfg = config.load()["hk"]["hkma"]

    def _page(self, segment: str, offset: int, limit: int) -> list[dict]:
        url = f"{self.cfg['base_url']}/{segment}?offset={offset}&limit={limit}"
        r = self.http_get(url, retries=self.cfg.get("retries", 3), timeout=40)
        return (r.json().get("result") or {}).get("records") or []

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        # the HKMA API caps page size at 100 regardless of the requested limit, so
        # walk by the count actually returned (NOT the requested limit) until empty.
        limit = 100
        max_pages = 200 if full_history else 1   # 200*100 = full daily history (since ~2009)
        rows: list[dict] = []
        offset = 0
        for _ in range(max_pages):
            recs = self._page(self.cfg["liquidity_segment"], offset, limit)
            if not recs:
                break
            rows.extend(recs)
            offset += len(recs)
            if len(recs) < limit:
                break
        if not rows:
            raise RuntimeError("hkma: no records returned")

        raw = pd.DataFrame(rows)
        if "end_of_date" not in raw.columns:
            raise RuntimeError(f"hkma: unexpected schema {list(raw.columns)[:8]}")
        out = pd.DataFrame(index=pd.to_datetime(raw["end_of_date"]))
        for src, col in FIELDS.items():
            if src in raw.columns:
                out[col] = pd.to_numeric(raw[src], errors="coerce").to_numpy()
        out = out.dropna(how="all").sort_index()
        if out.empty or "agg_balance" not in out.columns:
            raise RuntimeError("hkma: no usable columns parsed")
        log.info("hkma: %d rows %s->%s (agg_balance latest %.0f)", len(out),
                 out.index.min().date(), out.index.max().date(),
                 float(out["agg_balance"].dropna().iloc[-1]))
        return {"interbank_liquidity": out}
