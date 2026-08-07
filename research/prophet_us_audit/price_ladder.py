"""Adjusted-first price ladder for research instruments — one basis for both legs.

WHY THIS MODULE EXISTS
======================
An excess return is ``name_return − benchmark_return``. That subtraction is only
meaningful when both legs are priced on the SAME adjustment basis. The repo carries two
families and they are NOT interchangeable:

  ADJUSTED (back-adjusted for distributions; prior history is re-scaled when a name goes
  ex-distribution)
      ``data/baskets/ohlcv/<T>.parquet`` · ``data/yahoo/<T>.parquet`` · ``data/stocks/<T>.parquet``

  UNADJUSTED (raw closes accrued forward; re-based only at an infrequent full rebuild)
      ``data/breadth/_closes_cache.parquet``
      ``data/midcap_breadth/_closes_cache.parquet``
      ``data/smallcap_breadth/_closes_cache.parquet``

Mixing them puts a distribution-shaped bias into every excess number. Measured receipt
(2026-06-22, CFG): the cache reads ``67.9900`` and ``data/baskets/ohlcv`` reads
``67.5514`` — a 0.649% gap that is exactly CFG's 2026-07-01 quarterly dividend. Both
sources agree to the cent at 2026-07-07, after the ex-date. SPY is only available
adjusted, so a cache-priced name measured against SPY books its OWN distribution as a
loss. Names with no post-rebuild ex-date (JPM, KO, ALB, CEG) agree exactly across all
four sources, which is why the defect reads as noise until it is looked for by name.

THE EXPOSURE IS A BOUNDED TAIL, NOT ALL HISTORY
-----------------------------------------------
The caches are not "never adjusted" — they are re-based at a full rebuild and accrue raw
rows after it. Swept over 1,227 names with ≥200 overlapping sessions: 885 (72.1%) are
bit-identical to the adjusted store across their whole overlap, and of the 342 that
diverge the FIRST divergence clusters at p05 ``2026-05-13`` / median ``2026-06-01``
(2 pre-2026 one-offs aside). A quarterly payer under a never-rebuilt cache would show
~12 steps over three years; the observed maximum is 8 and the median is 0. So a window
that closes before the last rebuild carries ZERO bias, and a June–July 2026 window
carries all of it. Do not restate this as "every historical price is wrong".

USAGE
=====
    from price_ladder import resolve_close, close_panel

    r = resolve_close("CFG", asof="2026-07-31", start="2025-01-01")
    r.series        # pd.Series | None
    r.price_source  # "baskets_ohlcv" | "yahoo" | "data_stocks" | "closes_cache_UNADJUSTED"
    r.adjusted      # True unless the ladder fell through to a cache
    r.tried         # every rung attempted, in order — the disclosed ladder
    r.reason        # populated only when series is None

    px, prov = close_panel(tickers, asof="2026-07-31", start="2023-06-27")
    prov["resolved_from"]                    # per-rung counts
    prov["names_on_unadjusted_basis"]        # printed, never hidden
    prov["price_source"]["CFG"]              # per-name stamp

Coverage still comes first: the ladder falls THROUGH to the unadjusted cache rather than
dropping a name, because dropping an unpriced name deletes exactly the population a study
exists to measure. The fallback is stamped and counted so it can never be silent.

``data_dir`` is injectable on every entry point so the tests build a synthetic store and
run with no repo data.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import pandas as pd

__all__ = [
    "ADJUSTED_SOURCES", "UNADJUSTED_SOURCES", "LADDER", "CACHE_GROUPS",
    "Resolved", "resolve_close", "close_panel", "is_adjusted",
]

# ladder order is the contract: adjusted rungs first, cache last, null after that
ADJUSTED_SOURCES = ("baskets_ohlcv", "yahoo", "data_stocks")
UNADJUSTED_SOURCES = ("closes_cache_UNADJUSTED",)
LADDER = ADJUSTED_SOURCES + UNADJUSTED_SOURCES
CACHE_GROUPS = ("breadth", "midcap_breadth", "smallcap_breadth")

# per-name file rungs: (source tag, path template relative to data_dir)
_FILE_RUNGS = (
    ("baskets_ohlcv", "baskets/ohlcv/{t}.parquet"),
    ("yahoo", "yahoo/{t}.parquet"),
    ("data_stocks", "stocks/{t}.parquet"),
)

_CLOSE_COLS = ("close", "close_price")


def is_adjusted(source: str | None) -> bool | None:
    """True/False for a known source tag, None for an unknown or absent one."""
    if source in ADJUSTED_SOURCES:
        return True
    if source in UNADJUSTED_SOURCES:
        return False
    return None


@dataclass
class Resolved:
    """One name's close series plus the disclosed provenance of how it was found."""

    ticker: str
    series: pd.Series | None
    price_source: str | None
    adjusted: bool | None
    tried: list[str] = field(default_factory=list)
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.series is not None and not self.series.empty


def _read_file_close(path: str) -> pd.Series | None:
    """Close column from a per-name parquet, or None when unusable.

    Never raises on a bad file: one corrupt parquet must not take down a whole panel,
    and the caller records the rung as tried-and-failed either way.
    """
    if not os.path.exists(path):
        return None
    try:
        d = pd.read_parquet(path)
    except (OSError, ValueError, ImportError):
        return None
    col = next((c for c in _CLOSE_COLS if c in getattr(d, "columns", ())), None)
    if col is None:
        return None
    s = pd.to_numeric(d[col], errors="coerce").dropna()
    if s.empty:
        return None
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _clip(s: pd.Series | None, asof, start) -> pd.Series | None:
    if s is None:
        return None
    if start is not None:
        s = s[s.index >= pd.Timestamp(start)]
    if asof is not None:
        s = s[s.index <= pd.Timestamp(asof)]
    return s if not s.empty else None


class _CacheBook:
    """Lazily-loaded, memoized view over the three breadth close caches.

    The caches are wide frames (~1,500 columns); loading them per name would dominate a
    panel build, and loading them at import time would make an adjusted-only run pay for
    a rung it never uses.
    """

    def __init__(self, data_dir: str, groups: tuple[str, ...]):
        self._data_dir = data_dir
        self._groups = groups
        self._frames: list[pd.DataFrame] | None = None

    def frames(self) -> list[pd.DataFrame]:
        if self._frames is None:
            out = []
            for g in self._groups:
                p = os.path.join(self._data_dir, g, "_closes_cache.parquet")
                if not os.path.exists(p):
                    continue
                try:
                    c = pd.read_parquet(p)
                except (OSError, ValueError, ImportError):
                    continue
                c.index = pd.to_datetime(c.index)
                out.append(c.sort_index())
            self._frames = out
        return self._frames

    def get(self, ticker: str) -> pd.Series | None:
        for c in self.frames():
            if ticker in c.columns:
                s = pd.to_numeric(c[ticker], errors="coerce").dropna()
                if not s.empty:
                    return s
        return None


def resolve_close(
    ticker: str,
    *,
    asof: str | pd.Timestamp | None = None,
    start: str | pd.Timestamp | None = None,
    data_dir: str = "data",
    allow_unadjusted: bool = True,
    groups: tuple[str, ...] = CACHE_GROUPS,
    _book: "_CacheBook | None" = None,
) -> Resolved:
    """Resolve one name's close series ADJUSTED-FIRST, with the ladder disclosed.

    Rungs, in order: ``baskets_ohlcv`` → ``yahoo`` → ``data_stocks`` →
    ``closes_cache_UNADJUSTED`` → null. Every rung attempted is recorded in
    ``tried`` whether it hit or missed, so a resolution can always be replayed.

    ``allow_unadjusted=False`` stops the ladder after the adjusted rungs and returns a
    null with a reason — use it when a study would rather lose a name than mix bases.
    """
    t = str(ticker)
    tried: list[str] = []
    for src, tmpl in _FILE_RUNGS:
        tried.append(src)
        s = _clip(_read_file_close(os.path.join(data_dir, tmpl.format(t=t))), asof, start)
        if s is not None:
            return Resolved(t, s, src, True, tried)

    if not allow_unadjusted:
        return Resolved(t, None, None, None, tried,
                        reason=("absent from every ADJUSTED source "
                                f"({', '.join(ADJUSTED_SOURCES)}) and "
                                "allow_unadjusted=False"))

    tried.append("closes_cache_UNADJUSTED")
    book = _book if _book is not None else _CacheBook(data_dir, groups)
    s = _clip(book.get(t), asof, start)
    if s is not None:
        return Resolved(t, s, "closes_cache_UNADJUSTED", False, tried)

    return Resolved(t, None, None, None, tried,
                    reason=f"absent from every source on the ladder ({', '.join(LADDER)})")


def close_panel(
    tickers,
    *,
    asof: str | pd.Timestamp | None = None,
    start: str | pd.Timestamp | None = None,
    data_dir: str = "data",
    allow_unadjusted: bool = True,
    groups: tuple[str, ...] = CACHE_GROUPS,
) -> tuple[pd.DataFrame, dict]:
    """Wide close panel over ``tickers`` on the adjusted-first ladder.

    Returns ``(panel, provenance)``. The provenance carries a per-name ``price_source``
    stamp, per-rung counts, and the names that fell through to the unadjusted cache —
    counted and listed, never hidden, so a downstream reader can see how much of a
    result rests on a mixed basis.
    """
    book = _CacheBook(data_dir, groups)
    cols: dict[str, pd.Series] = {}
    stamp: dict[str, str | None] = {}
    counts = {k: 0 for k in LADDER}
    counts["unresolved"] = 0
    unresolved: list[str] = []
    unadjusted: list[str] = []

    for tk in dict.fromkeys(map(str, tickers)):          # de-dupe, keep order
        r = resolve_close(tk, asof=asof, start=start, data_dir=data_dir,
                          allow_unadjusted=allow_unadjusted, groups=groups, _book=book)
        stamp[tk] = r.price_source
        if not r.ok:
            counts["unresolved"] += 1
            unresolved.append(tk)
            continue
        counts[r.price_source] += 1
        cols[tk] = r.series
        if r.adjusted is False:
            unadjusted.append(tk)

    panel = pd.DataFrame(cols).sort_index() if cols else pd.DataFrame()
    prov = {
        "ladder": list(LADDER),
        "adjusted_sources": list(ADJUSTED_SOURCES),
        "unadjusted_sources": list(UNADJUSTED_SOURCES),
        "asof": str(asof) if asof is not None else None,
        "start": str(start) if start is not None else None,
        "n_requested": len(dict.fromkeys(map(str, tickers))),
        "resolved_from": counts,
        "price_source": stamp,
        "names_on_unadjusted_basis": len(unadjusted),
        "unadjusted_tickers": sorted(unadjusted),
        "unresolved_tickers": sorted(unresolved),
        "panel_names": int(panel.shape[1]) if not panel.empty else 0,
        "panel_sessions": int(panel.shape[0]) if not panel.empty else 0,
    }
    if not panel.empty:
        prov["panel_range"] = [str(panel.index.min().date()), str(panel.index.max().date())]
    return panel, prov
