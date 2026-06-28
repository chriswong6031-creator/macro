"""Stooq free daily-close fallback for US names the primary feed (Yahoo) refuses.

Yahoo intermittently 404s specific *live* large-caps — observed Marsh & McLennan
(MMC) and Fiserv (FI), which Yahoo serves only under stale/garbled symbols (MRSH,
FISV) — so they never reach data/yahoo and silently drop out of the searchable
stock library. Stooq's free daily CSV covers US listings and fills those gaps.

IP-GATED: Stooq HTML-blocks some IPs (it returns the site page instead of the
CSV); then this returns None and the caller keeps whatever it had. It is reachable
from CI, which is where the nightly build runs. Returns a tz-naive
DataFrame[close, volume] to match the yahoo store schema. Best-effort, never raises.
"""
from __future__ import annotations

import io
import logging

import pandas as pd

log = logging.getLogger(__name__)

_UA = {"User-Agent": "Mozilla/5.0 (macro-dashboard research)"}
_URL = "https://stooq.com/q/d/l/?s={sym}.us&i=d"


def stooq_daily(ticker: str) -> pd.DataFrame | None:
    """Daily close+volume history for a US ticker as a tz-naive frame, or None when
    Stooq is blocked / has no data. Symbols are lower-cased and class shares keep
    the dash Stooq's ``.us`` feed expects (BRK-B -> brk-b)."""
    import requests
    sym = str(ticker).strip().lower().replace(".", "-")
    if not sym:
        return None
    try:
        r = requests.get(_URL.format(sym=sym), headers=_UA, timeout=25)
    except Exception as e:  # noqa: BLE001 — network/DNS error -> treat as unavailable
        log.debug("stooq %s: %s", ticker, e)
        return None
    txt = (r.text or "").strip()
    # a real CSV starts with the "Date,Open,High,Low,Close,Volume" header; an IP
    # block / unknown symbol returns an HTML page or empty body instead
    if r.status_code != 200 or not txt.lower().startswith("date"):
        return None
    try:
        raw = pd.read_csv(io.StringIO(txt))
    except Exception as e:  # noqa: BLE001
        log.debug("stooq %s parse: %s", ticker, e)
        return None
    if "Close" not in raw or len(raw) < 2:
        return None
    out = pd.DataFrame(index=pd.to_datetime(raw["Date"], errors="coerce"))
    out["close"] = pd.to_numeric(raw["Close"], errors="coerce").to_numpy()
    out["volume"] = (pd.to_numeric(raw["Volume"], errors="coerce").to_numpy()
                     if "Volume" in raw else pd.NA)
    out = out[out.index.notna()]
    out = out[~out.index.duplicated(keep="last")].sort_index().dropna(subset=["close"])
    if getattr(out.index, "tz", None) is not None:
        out.index = out.index.tz_localize(None)
    return out if not out.empty else None
