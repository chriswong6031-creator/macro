"""Stock Connect flows (沪深港通) — the canonical Stock Connect source.

Keyless Eastmoney datacenter history report (RPT_MUTUAL_DEAL_HISTORY, live-verified
2026-06-13), paginated to the full daily history back to 2014-11-17. This is the SINGLE
source for Stock Connect flows: the old china_macro._connect_flow path (push2his
kamt.kline — long dead, northbound a frozen placeholder) has been removed in favour of
this dedicated collector, which serves a clean daily series:

  southbound (MUTUAL_TYPE 006)  mainland buying Hong Kong — FULLY LIVE: all five
                                columns (net, buy, sell, turnover, hold_mktcap)
                                still post daily. A direct mainland risk-on/off gauge.
  northbound (MUTUAL_TYPE 005)  foreign buying A-shares — PARTLY RETIRED. Per column:

                                  net, buy, sell  RETIRED after 2024-08-16. The
                                    Apr-2024 CSRC rule amendment ended SSE/SZSE daily
                                    northbound flow disclosure; all three died together
                                    (not just net), last datapoint 2024-08-16. This is
                                    permanent and is NOT a bug to repair — pre-2024
                                    history is kept because it is informative.
                                  turnover  LIVE daily, unaffected by the rule change.
                                  hold_mktcap  QUARTER-END ONLY since 2024-09.
                                    Aggregate northbound holdings now post on quarter
                                    ends alone; upstream emits a literal 0 on every
                                    non-disclosure day in between. Zero is impossible
                                    for a cumulative holdings level (~19,000亿 at the
                                    freeze), so _frame_from_rows coerces 0 -> NaN.
                                    450 such fake zeros were healed out of the store
                                    on 2026-08-04; the coercion protects the forward
                                    path, because store.upsert merges
                                    new.combine_first(old) and a NaN in a fresh fetch
                                    can never displace a stored 0.0.

Those per-column facts are declared as ColumnContracts (see ChinaConnectAdapter
below), so a column that dies or resurrects raises a GitHub annotation instead of
hiding inside a frame kept "fresh" by its live siblings — which is exactly how the
death of net/buy/sell sat unnoticed for ~2 years behind a live turnover.

Stored under group `china_connect`. Net flow is consumed downstream as a z-score /
rolling cumulative (scale-invariant), so the raw source units are non-load-bearing.
"""
from __future__ import annotations

import logging

import pandas as pd

from collectors.base import Adapter, ColumnContract

log = logging.getLogger(__name__)

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_BASE = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_REFERER = "https://data.eastmoney.com/"
_YI = 1e8

# series -> MUTUAL_TYPE (combined legs: 005 north, 006 south)
_LEGS = {"southbound": "006", "northbound": "005"}
# stored_col -> (source_field, scale)
_FIELDS = {
    "net":         ("NET_DEAL_AMT", 1.0),     # daily net (buy - sell); z-scored downstream
    "buy":         ("BUY_AMT", 1.0),
    "sell":        ("SELL_AMT", 1.0),
    "turnover":    ("DEAL_AMT", 1.0),
    "hold_mktcap": ("HOLD_MARKET_CAP", _YI),  # cumulative holdings, normalised to 亿元
}

# Northbound flow disclosure ended here — regulatory, permanent, not repairable.
_NB_RETIRED = "2024-08-16"
_NB_RETIRED_NOTE = ("SSE/SZSE ended daily northbound flow disclosure (Apr-2024 CSRC "
                    "rule change; effective after 2024-08-16) — history before that "
                    "date is kept and is still informative.")
# A daily leg gets 3 cadences of slack (3 x stale_after_days=6), which rides out the
# Chinese New Year and Golden Week closures without crying wolf.
_DAILY_DARK_DAYS = 18
# hold_mktcap posts on quarter ends only (~91d apart); 120d leaves room for a late post
# while still catching a quarter that never arrives at all.
_QUARTERLY_DARK_DAYS = 120


def _frame_from_rows(rows: list[dict]) -> pd.DataFrame:
    """Shape raw Eastmoney rows into the stored per-leg frame.

    Pure — no HTTP, no paging — so the field mapping, the 亿 scaling and the
    hold_mktcap zero coercion are unit-testable without a network round trip.
    Returns a possibly-EMPTY frame; the caller decides whether that is fatal.
    """
    raw = pd.DataFrame(rows)
    idx = pd.to_datetime(raw["TRADE_DATE"])
    out = pd.DataFrame(index=idx)
    for stored, (src, scale) in _FIELDS.items():
        if src in raw.columns:
            col = pd.to_numeric(raw[src], errors="coerce").to_numpy()
            out[stored] = col / scale if scale != 1.0 else col
    if "hold_mktcap" in out.columns:
        # Upstream emits a literal 0 for HOLD_MARKET_CAP on every non-disclosure day
        # since aggregate holdings went quarter-end-only (2024-09). Zero is IMPOSSIBLE
        # for this series — it is a cumulative holdings LEVEL (~19,000亿 at the
        # Aug-2024 freeze), so a 0 is always an upstream artifact, never an
        # observation. Coerce at the source: store.upsert merges
        # new.combine_first(old), so a NaN in a fresh fetch can never displace a
        # stored 0.0 — once a zero lands it is permanent, and only a one-time store
        # heal (done 2026-08-04) can remove it. Fixing the reader alone would leave
        # the store lying.
        out["hold_mktcap"] = out["hold_mktcap"].mask(out["hold_mktcap"] == 0.0)
    return out.dropna(how="all").sort_index()


class ChinaConnectAdapter(Adapter):
    name = "china_connect"
    group = "china_connect"
    stale_after_days = 6   # daily; northbound may be permanently null going forward

    # Per-column truth, so no column can die quietly inside a live frame. The
    # retired ones are SILENT in their expected all-null steady state and only
    # speak up if upstream ever resumes disclosure (see collectors/base.ColumnContract).
    column_contracts = {
        "northbound": {
            "net":  ColumnContract(retired=_NB_RETIRED, note=_NB_RETIRED_NOTE),
            "buy":  ColumnContract(retired=_NB_RETIRED, note=_NB_RETIRED_NOTE),
            "sell": ColumnContract(retired=_NB_RETIRED, note=_NB_RETIRED_NOTE),
            "turnover": ColumnContract(
                max_dark_days=_DAILY_DARK_DAYS,
                note="Northbound turnover survived the Aug-2024 flow-disclosure "
                     "retirement and is still posted daily; if it stops, the "
                     "northbound leg has no live column left."),
            "hold_mktcap": ColumnContract(
                max_dark_days=_QUARTERLY_DARK_DAYS,
                note="Aggregate northbound holdings are quarter-end-only since "
                     "2024-09; a miss here means a whole quarter went unreported."),
        },
        "southbound": {
            col: ColumnContract(
                max_dark_days=_DAILY_DARK_DAYS,
                note="Southbound is fully live daily — unlike northbound it was not "
                     "touched by the 2024 disclosure change, so any dark column here "
                     "is a real outage to investigate, not a retirement.")
            for col in _FIELDS
        },
    }

    def __init__(self) -> None:
        self.retries = 3

    def _headers(self) -> dict:
        return {"User-Agent": _UA, "Referer": _REFERER}

    def _leg(self, mutual_type: str, full_history: bool) -> pd.DataFrame:
        page_size = 2000 if full_history else 90   # API caps each page at 2000 rows
        rows: list[dict] = []
        page_no = 1
        while True:
            params = {"reportName": "RPT_MUTUAL_DEAL_HISTORY", "columns": "ALL",
                      "pageSize": page_size, "sortColumns": "TRADE_DATE", "sortTypes": -1,
                      "pageNumber": page_no, "filter": f'(MUTUAL_TYPE="{mutual_type}")'}
            r = self.http_get(_BASE, params=params, retries=self.retries,
                              headers=self._headers(), timeout=30)
            result = (r.json() or {}).get("result") or {}
            data = result.get("data") or []
            rows.extend(data)
            # full backfill walks every page back to 2014-11-17; an incremental run
            # is satisfied by the single newest page
            if not full_history or not data or page_no >= (result.get("pages") or 1):
                break
            page_no += 1
        if not rows:
            raise ValueError(f"type {mutual_type}: empty result")
        out = _frame_from_rows(rows)
        if out.empty:
            raise ValueError(f"type {mutual_type}: no usable rows")
        return out

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
        errors: list[str] = []
        for name, mtype in _LEGS.items():
            try:
                frames[name] = self._leg(mtype, full_history)
            except Exception as e:  # noqa: BLE001 — northbound may legitimately be empty now
                errors.append(f"{name}: {e}")
                log.warning("china_connect %s failed: %s", name, e)
        if not frames:
            raise RuntimeError("china_connect: all legs failed — " + " | ".join(errors))
        if errors:
            log.info("china_connect: %d/%d legs ok (skipped: %s)",
                     len(frames), len(frames) + len(errors), "; ".join(errors))
        return frames
