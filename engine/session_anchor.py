"""The ABSOLUTE session-calendar anchor every timeframe bucket is measured against.

Binding ruling: ``research/SESSION_ANCHOR_ABSOLUTE_CALENDAR_ADJUDICATION_BY_FABLE.md``
(R1-R3, era ``abs-session-2026-08-06``).

WHY THIS EXISTS. ``confluence_tiers._tf_bars`` used ``daily.resample("2B"/"3B")``, whose
bin edges anchor to the SERIES' FIRST timestamp. Every 2D/3D leg — tier crosses, freshness
ticks, the not-topped veto — therefore depended on how much LEADING history the caller
handed in: one dropped leading bar flipped the tier on 13/232 data/stocks names and the veto
on 27/232, and the two production loaders (data/stocks, 1960s-start; data/baskets/ohlcv,
2014-start) disagreed on live buyability the same night (NUE/PEP/WMT buyable from one store
only; ECL/SW inverted). A verdict must be a function of the PRICE HISTORY, never of the
caller's slice.

THE REPAIR. Bucket by the position of each session in a FIXED REFERENCE SESSION INDEX:

    position(d) = R.searchsorted(d, side="left")     bucket(d) = position(d) // n

``position`` is a function of ``(reference, date)`` ONLY — never of the series — so any two
callers holding any two windows of the same name agree bar-for-bar on every bucket.

REJECTED ALTERNATIVES (adjudication §The defect). ``resample(origin=...)`` has no effect on
non-tick freqs (verified, RuntimeWarning). A calendar busday anchor (``np.busday_count // n``)
re-introduces the holiday mis-split ``engine/canon.py::resample_sessions`` was built to
eliminate — ~80% of NVDA signal dates relocated on calendar bins (audit #7).

WHY THE US REFERENCE IS RULES, NOT DATA (R1). ``lib.nyse_calendar`` is pure stdlib
arithmetic: zero data dependencies (engine tests and CI packs need no store), identical in
every lane (nightly, intraday, tests), and immune to vendor-revision re-phasing — a silently
revised historical row in a data-derived reference would re-phase every bucket after it,
reintroducing the audited disease THROUGH the cure. CN/HK/CA have no rules module, so they
read an index that never halts (Shanghai Composite / HSI / TSX composite), refreshed nightly
beside the name stores.

NO FALLBACK CHAIN (house law: a fallback chain hides absence from every rung). A missing
CN/HK/CA reference store raises ``FileNotFoundError``. It never degrades to the US reference:
a CN name silently bucketed on NYSE sessions would be wrong in a way nothing downstream could
see. An UNMAPPED market string routes to US openly and is disclosed in the adjudication (R1),
which is a different thing from a missing store answered with a guess.

Import-time side effects: none. The US reference is built on first call, not at import.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from lib import nyse_calendar

#: Ticker suffix -> market key (R1/R3). Everything else is US; see :func:`market_for_ticker`.
MARKET_SUFFIX = {".SS": "CN", ".SZ": "CN", ".HK": "HK", ".TO": "CA", ".V": "CA"}

#: Reference session source per non-US market, relative to ``lib.config.data_dir()``.
#: Canonical repo paths: ``data/china/000001.SS.parquet`` (Shanghai Composite, 1997->),
#: ``data/hk/_HSI.parquet`` (1986->), ``data/canada/_GSPTSE.parquet`` (1979->). Each is an
#: INDEX — it never halts, so its session set is the market's session set, refreshed nightly
#: by the same collection pass that refreshes the name stores.
_REF_STORES = {
    "CN": "china/000001.SS.parquet",
    "HK": "hk/_HSI.parquet",
    "CA": "canada/_GSPTSE.parquet",
}

#: US reference epoch. The deepest daily store in this repo starts 1962, so the
#: before-start branch of :func:`session_positions` is unreachable for US in practice.
US_EPOCH = date(1950, 1, 3)
#: Forward horizon. The reference must always cover today (and any same-week forward stamp),
#: so the beyond-end extension never triggers for US. Extending the END cannot move the
#: position of any PAST date — ``searchsorted`` counts from R[0] — so this horizon is free.
US_FORWARD_DAYS = 400

#: market -> reference sessions. Built once per process, on first use.
_REF_CACHE: dict[str, pd.DatetimeIndex] = {}


def market_for_ticker(ticker) -> str:
    """Market key for a ticker, by suffix (R3). Unknown/None/empty -> ``"US"``.

    The board callers (US/CN/HK/CA/Intl) all route through ``signal_gate.gate``, which infers
    the market here and passes it down — so a board needs no edit to get the right calendar.
    An unmapped suffix (the intl library) resolves to US openly: start-invariance holds under
    ANY fixed reference, and only bucket-edge placement around off-calendar holidays is
    approximate — the same approximation the old ``"3B"`` bins applied to EVERY market.
    """
    if not ticker:
        return "US"
    t = str(ticker).strip().upper()
    for suffix, market in MARKET_SUFFIX.items():
        if t.endswith(suffix):
            return market
    return "US"


def _market_key(market: str | None) -> str:
    """Normalize a market argument. Unknown strings -> ``"US"`` (R1, disclosed)."""
    m = str(market or "US").strip().upper()
    return m if (m == "US" or m in _REF_STORES) else "US"


def _data_root() -> Path:
    """The repo's data dir — resolved through ``lib.config`` so the reference index can never
    come from a different tree than the prices it phases. Imported LAZILY: the US path must
    stay free of config.yml/yaml (CI packs install minimal deps), and only the CN/HK/CA
    branch reaches disk. An unimportable config is raised, not papered over with a guess."""
    from lib import config
    return config.data_dir()


def _us_reference() -> pd.DatetimeIndex:
    """US sessions from the RULES (R1) — no store is read, ever."""
    sessions = nyse_calendar.sessions_between(
        US_EPOCH, date.today() + timedelta(days=US_FORWARD_DAYS))
    return pd.DatetimeIndex(pd.to_datetime(sessions))


def _store_reference(market: str) -> pd.DatetimeIndex:
    """Sessions of a non-US market's reference index store (R1). Raises if it is absent —
    NEVER falls back to another market's calendar."""
    rel = _REF_STORES[market]
    path = _data_root() / rel
    if not path.exists():
        raise FileNotFoundError(
            f"session_anchor: the {market} session reference {path} is missing — "
            f"{market} bucketing cannot be anchored without it")
    idx = pd.read_parquet(path).index
    if not isinstance(idx, pd.DatetimeIndex):
        raise ValueError(
            f"session_anchor: the {market} session reference {path} is not date-indexed "
            f"(got {type(idx).__name__}) — it cannot supply a session calendar")
    return _normalize(idx).unique().sort_values()


def reference_sessions(market: str = "US") -> pd.DatetimeIndex:
    """The fixed, ascending session index bucket positions are counted against.

    Cached per process per market: US is rule-computed on first call (~12 ms for 19.6k
    sessions), CN/HK/CA are read from their index store LAZILY, so a US-only lane (and every
    CI pack) touches no disk at all.
    """
    m = _market_key(market)
    got = _REF_CACHE.get(m)
    if got is None:
        got = _us_reference() if m == "US" else _store_reference(m)
        _REF_CACHE[m] = got
    return got


def _normalize(idx) -> pd.DatetimeIndex:
    """Dates as tz-naive midnights — the form both sides of ``searchsorted`` must share."""
    di = idx if isinstance(idx, pd.DatetimeIndex) else pd.DatetimeIndex(pd.to_datetime(idx))
    if di.tz is not None:
        di = di.tz_localize(None)
    return di.normalize()


def _dense_rank(values: np.ndarray) -> np.ndarray:
    """0-based DENSE rank (ties share a rank) — equal dates must share a position."""
    return pd.Series(values).rank(method="dense").to_numpy().astype(np.int64) - 1


def session_positions(idx: pd.DatetimeIndex, market: str = "US") -> np.ndarray:
    """Absolute position of each date in the market's reference session index (int64).

    ``position(d) = R.searchsorted(d, side="left")``. The whole start-invariance property
    rests on this being a function of ``(reference, date)`` alone.

    THE THREE EDGES, all deterministic and series-independent:

    * **d in R** — the ordinary case: its exact ordinal.
    * **d absent from R** (a synthetic bdate fixture's Saturday, an off-calendar intl
      session) — takes the position of the NEXT reference session, so it buckets with the
      session that follows it rather than landing anywhere the series start could influence.
    * **d beyond R's end** (a stale CN/HK/CA reference beside a fresher name store; a
      rules-US impossibility, since the US reference runs 400 days forward) — per-series rank
      extension: ``len(R) + rank among the series' own post-reference dates``. Exact whenever
      the gap is <=1 session or the name traded every gap session, which is the live case:
      the reference store refreshes nightly beside the name stores. Divergence is confined to
      the stale window and heals on the next refresh.
    * **d before R's start** — currently unreachable (deepest input 1962 vs the 1950 US
      epoch; CN 2021 > 1997; HK 2008 > 1986). Guarded by the same rank rule MIRRORED: the
      series' own pre-reference dates take ``-1, -2, ...`` backwards from R[0], so bucketing
      stays consecutive across the seam. Approximate, documented, not silently wrong.
    """
    R = reference_sessions(market)
    d = _normalize(idx)
    if len(d) == 0:
        return np.zeros(0, dtype=np.int64)
    pos = np.asarray(R.searchsorted(d, side="left"), dtype=np.int64)
    if len(R) == 0:
        return pos
    dv = d.to_numpy()
    beyond = dv > R[-1].to_numpy()
    if beyond.any():
        pos[beyond] = len(R) + _dense_rank(dv[beyond])
    before = dv < R[0].to_numpy()
    if before.any():
        r = _dense_rank(dv[before])
        pos[before] = r - (int(r.max()) + 1)      # ..., -2, -1 immediately below position 0
    return pos
