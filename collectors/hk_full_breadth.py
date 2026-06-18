"""Hong Kong FULL main-board breadth — additive full-market participation gauge.

The curated `hk_breadth` adapter (config["hk"]["sectors"], ~73 large caps) stays the
PRIMARY HK breadth gauge — it has multi-year history for the MA-based pct_above_50/200
and new-high/low series. This adapter is a SEPARATE, additive read of how the WHOLE HK
main board is participating today, computed from a single full-market spot snapshot:

  ak.stock_hk_main_board_spot_em()  — Eastmoney HK main-board spot, ~2000+ names.
                                      Columns include 代码 (code), 名称 (name),
                                      最新价 (last), 涨跌幅 (% change), 今开 (open),
                                      昨收 (prev close). SNAPSHOT-ONLY (no history).

OUTPUT (data/hk_full_breadth/breadth.parquet) — ONE row stamped today, accrue-forward
(store.upsert keeps prior days and overwrites today's row on a same-day re-run):
  n_members  — names with a usable % change today (the denominator)
  adv        — count up (% change > 0)
  dec        — count down (% change < 0)
  pct_up     — 100 * adv / n_members  (% of the board green)

We DELIBERATELY do NOT compute MA-based pct_above_50/200: a single snapshot has no
price history, so those would be meaningless. That dimension stays with the curated
`hk_breadth` series, which has the history to compute it honestly.

FRAGILE source: ak.stock_hk_main_board_spot_em() intermittently throws
RemoteDisconnected / 403 from the Eastmoney push2 endpoint, and is snapshot-only (no
backfill possible). This is therefore a SEPARATE adapter with self.expected_failure
set, so a break reports status 'blocked' and the circuit breaker isolates it from the
curated hk_breadth gauge (one flaky full-market snapshot must never knock out the
primary breadth read). akshare raises ConnectionError / RemoteDisconnected (not HTTP
status codes), so the call is wrapped in an explicit retry loop with backoff.
"""
from __future__ import annotations

import logging
import time
from datetime import date

import akshare as ak
import pandas as pd

from collectors.base import Adapter

log = logging.getLogger(__name__)

# Eastmoney spot columns we read (Chinese headers as returned by akshare).
_COL_CODE = "代码"
_COL_PCT = "涨跌幅"   # daily % change


class HkFullBreadthAdapter(Adapter):
    """Full HK main-board adv/dec participation, one accrue-forward row per run."""

    name = "hk_full_breadth"
    group = "hk_full_breadth"
    stale_after_days = 6   # snapshot-only; tolerate a long weekend / HK holiday
    # FRAGILE source (intermittent RemoteDisconnected/403, no backfill): report
    # 'blocked' instead of tripping the breaker, keeping it isolated from hk_breadth.
    expected_failure = "HK full main-board spot snapshot unavailable (Eastmoney flaky)"

    def __init__(self) -> None:
        self.retries = 3
        self.backoff_base = 3.0

    def _spot(self) -> pd.DataFrame:
        """One full-market spot pull, retried — akshare raises ConnectionError /
        RemoteDisconnected (not HTTP codes), so we retry the call explicitly."""
        last_exc: Exception | None = None
        for attempt in range(self.retries):
            try:
                raw = ak.stock_hk_main_board_spot_em()
                if raw is None or raw.empty:
                    raise ValueError("empty spot frame")
                return raw
            except Exception as e:  # noqa: BLE001 — retried, then surfaced
                last_exc = e
                if attempt < self.retries - 1:
                    wait = self.backoff_base * (2 ** attempt)
                    log.warning("hk_full_breadth spot attempt %d/%d failed (%s); "
                                "retry in %.0fs", attempt + 1, self.retries, e, wait)
                    time.sleep(wait)
        raise last_exc  # type: ignore[misc]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        # Snapshot-only source: full_history is a no-op (there is nothing to backfill);
        # every run appends exactly one row stamped today via store.upsert.
        raw = self._spot()
        if _COL_PCT not in raw.columns:
            raise ValueError(f"spot frame missing '{_COL_PCT}' column; "
                             f"got {list(raw.columns)[:12]}")

        pct = pd.to_numeric(raw[_COL_PCT], errors="coerce").dropna()
        # de-dupe by code so suspended/duplicate listings don't double-count
        if _COL_CODE in raw.columns:
            codes = raw.loc[pct.index, _COL_CODE]
            keep = ~codes.duplicated(keep="last")
            pct = pct[keep.to_numpy()]

        n_members = int(len(pct))
        if n_members < 100:
            # a few hundred names is the floor for a credible full-board read;
            # a near-empty snapshot means the endpoint half-failed
            raise ValueError(f"hk_full_breadth snapshot too sparse: {n_members} names")

        adv = int((pct > 0).sum())
        dec = int((pct < 0).sum())
        pct_up = round(100.0 * adv / n_members, 2) if n_members else float("nan")

        today = pd.Timestamp(date.today())   # sibling accrue-forward idiom; no deprecated utcnow
        df = pd.DataFrame(
            {"n_members": [n_members], "adv": [adv], "dec": [dec], "pct_up": [pct_up]},
            index=pd.DatetimeIndex([today]),
        )
        log.info("hk_full_breadth: %d names, adv %d / dec %d (%.1f%% up)",
                 n_members, adv, dec, pct_up)
        return {"breadth": df}
