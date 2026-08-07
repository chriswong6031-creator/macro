"""Adjusted-first price ladder for PRODUCTION graders — one basis for both legs.

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
      ``data/russell_breadth/_closes_cache.parquet``

Every benchmark this house grades against (SPY, the GICS sector ETFs) is available ONLY
adjusted, so a cache-priced name measured against one books its OWN distribution as a
loss. Measured receipt (2026-06-22, CFG): the cache reads ``67.9900`` and
``data/baskets/ohlcv`` reads ``67.5514`` — a 0.649% gap that is exactly CFG's quarterly
dividend. Names with no post-rebuild ex-date (JPM, KO) agree to the cent across all four
sources, which is why the defect reads as noise until it is looked for by name.

THE EXPOSURE IS A BOUNDED TAIL, NOT ALL HISTORY
-----------------------------------------------
The caches are not "never adjusted" — they are re-based at a full rebuild and accrue raw
rows after it. Swept over 1,227 names with an adjusted counterpart (#4698): 72.1% are
bit-identical across their whole overlap, and of those that diverge the FIRST divergence
clusters at p05 ``2026-05-13`` / median ``2026-06-01``. So a window that closes before the
last rebuild carries ZERO bias and a June–July 2026 window carries all of it. Do not
restate this as "every historical price is wrong".

A SECOND-ORDER CONSEQUENCE: CACHE-PRICED RESULTS ARE NOT REPRODUCIBLE
---------------------------------------------------------------------
Because a rebuild re-bases the cache in place, the same (ticker, date) can read
differently on two dates. ``PNC`` at 2026-06-22 read ``234.71`` in the 2026-07-01 commit
and ``232.85`` on 2026-08-06. A grader that re-computes a matured historical row from the
cache therefore RESTATES it — silently — every time the cache moves under it. Measured on
this repo 2026-08-06: re-running ``scripts/grade_us_board.py`` against the shipped ledger
would have moved 75 already-published rows, 19 of them materially (worst −1.94pp on
``LPG`` 2026-06-18 H5). That is why callers stamp the basis on the row and why an already
graded row is never re-priced.

USAGE
=====
    from engine.price_ladder import resolve_close, close_panel, overlay_adjusted

    r = resolve_close("CFG", asof="2026-07-31", start="2025-01-01")
    r.series        # pd.Series | None
    r.price_source  # "baskets_ohlcv"|"yahoo"|"data_stocks"|"baskets_extras"|"closes_cache_UNADJUSTED"
    r.adjusted      # True unless the ladder fell through to a cache
    r.tried         # every rung attempted, in order — the disclosed ladder
    r.reason        # populated only when series is None

    px, prov = close_panel(tickers, asof="2026-07-31", start="2023-06-27")
    panel, prov = overlay_adjusted(cache_panel, tickers)   # re-base an existing panel

Coverage still comes first: the ladder falls THROUGH to the unadjusted cache rather than
dropping a name, because dropping an unpriced name deletes exactly the population a study
exists to measure. The fallback is stamped and counted so it can never be silent.

``data_dir`` is injectable on every entry point so the tests build a synthetic store and
run with no repo data.

PROVENANCE / MIGRATION
======================
The ladder semantics here are the ones audited in PR #4698, whose research-tier copy is
``research/prophet_us_audit/price_ladder.py``. This module is the PRODUCTION home; when
#4698 lands, that research copy should re-export from here rather than keep a second
implementation. ``tests/test_price_ladder.py::test_research_copy_matches_production``
pins the two against each other whenever both are present.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import pandas as pd

__all__ = [
    "ADJUSTED_SOURCES", "UNADJUSTED_SOURCES", "LADDER", "CACHE_GROUPS",
    "Resolved", "resolve_close", "close_panel", "overlay_adjusted", "is_adjusted",
    "default_data_dir", "make_books",
]

# ladder order is the contract: adjusted rungs first, cache last, null after that.
#
# `baskets_extras` (data/baskets/extras.parquet) is the wide OFF-INDEX close store, and it
# IS adjusted: scripts/fetch_basket_extras.py downloads it with `auto_adjust=True`. That
# is not taken on the docstring's word — measured 2026-08-06, on all 400 names carried by
# BOTH extras and baskets/ohlcv the two frames are bit-identical (max relative difference
# 0.00e+00). It sits last among the adjusted rungs because it is a ~3y wide frame while
# the per-name rungs carry deep history.
#
# What it does NOT do, measured rather than assumed: it recovers ZERO of the 154
# board-admitted names that still fall through to the raw cache. Extras exists for names
# OUTSIDE the index caches, and those 154 are in-index names the per-name adjusted stores
# simply do not carry — a real, standing coverage hole (20.6% of freshly-graded us_board
# rows) that this ladder DISCLOSES per row rather than closes. The rung is here because
# scripts/prophet_postmortem.py resolves its off-index universe through it, and moving
# that site onto the shared ladder must not cost it coverage.
ADJUSTED_SOURCES = ("baskets_ohlcv", "yahoo", "data_stocks", "baskets_extras")
UNADJUSTED_SOURCES = ("closes_cache_UNADJUSTED",)
LADDER = ADJUSTED_SOURCES + UNADJUSTED_SOURCES

#: Cache groups, in the precedence `scripts/build_stock_library.universe` uses. A name
#: present in two caches must resolve to the same series here as it does there.
CACHE_GROUPS = ("breadth", "smallcap_breadth", "midcap_breadth", "russell_breadth")

# per-name file rungs: (source tag, path template relative to data_dir)
_FILE_RUNGS = (
    ("baskets_ohlcv", "baskets/ohlcv/{t}.parquet"),
    ("yahoo", "yahoo/{t}.parquet"),
    ("data_stocks", "stocks/{t}.parquet"),
)

_CLOSE_COLS = ("close", "close_price")


def default_data_dir() -> str:
    """The repo's configured data root — resolved lazily so importing this module in a
    test that never touches the real store costs nothing and cannot fail on config."""
    from lib import config
    return str(config.data_dir())


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


class _WideBook:
    """Lazily-loaded, memoized view over one or more wide [date x ticker] close frames.

    These frames are ~700–1,500 columns; loading them per name would dominate a panel
    build, and loading them at import time would make a run pay for a rung it never uses.
    First frame carrying the ticker wins, in the order given.
    """

    def __init__(self, paths: tuple[str, ...],
                 preloaded: "list[pd.DataFrame] | None" = None):
        self._paths = paths
        # A caller that already holds these frames (prophet_postmortem loads the caches
        # for its own calendar) injects them rather than paying a second wide read — and,
        # more importantly, so the ladder and the caller can never disagree about what
        # "the cache" contains.
        self._frames: list[pd.DataFrame] | None = None
        if preloaded is not None:
            self._frames = [f for f in preloaded if f is not None and not f.empty]

    def frames(self) -> list[pd.DataFrame]:
        if self._frames is None:
            out = []
            for p in self._paths:
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


class _Books:
    """The two wide-frame rungs a resolution may need, built lazily and shared across a
    whole panel so the caches and the extras frame are each read at most once."""

    def __init__(self, data_dir: str, groups: tuple[str, ...],
                 cache_frames: "list[pd.DataFrame] | None" = None):
        self.extras = _WideBook((os.path.join(data_dir, "baskets", "extras.parquet"),))
        self.cache = _WideBook(
            tuple(os.path.join(data_dir, g, "_closes_cache.parquet") for g in groups),
            preloaded=cache_frames)


def make_books(data_dir: str | None = None, *, groups: tuple[str, ...] = CACHE_GROUPS,
               cache_frames: "list[pd.DataFrame] | None" = None) -> "_Books":
    """Build a shared rung cache to hand to repeated ``resolve_close`` calls.

    ``cache_frames`` injects an already-loaded breadth panel so a caller that needs the
    caches for its own purposes does not read them twice — and so the ladder resolves the
    SAME cache the caller is reasoning about.
    """
    dd = default_data_dir() if data_dir is None else data_dir
    return _Books(dd, groups, cache_frames=cache_frames)


def resolve_close(
    ticker: str,
    *,
    asof: str | pd.Timestamp | None = None,
    start: str | pd.Timestamp | None = None,
    data_dir: str | None = None,
    allow_unadjusted: bool = True,
    groups: tuple[str, ...] = CACHE_GROUPS,
    min_last: str | pd.Timestamp | None = None,
    _book: "_Books | None" = None,
) -> Resolved:
    """Resolve one name's close series ADJUSTED-FIRST, with the ladder disclosed.

    Rungs, in order: ``baskets_ohlcv`` → ``yahoo`` → ``data_stocks`` → ``baskets_extras``
    → ``closes_cache_UNADJUSTED`` → null. Every rung attempted is recorded in ``tried``
    whether it hit or missed, so a resolution can always be replayed.

    ``allow_unadjusted=False`` stops the ladder after the adjusted rungs and returns a
    null with a reason — use it when a study would rather lose a name than mix bases.

    ``min_last`` is the last session the caller needs covered. A rung that hits but ENDS
    BEFORE it is treated as a MISS, so the walk continues — through the remaining
    ADJUSTED rungs first, and then to the cache. Measured 2026-08-06:
    ``data/baskets/ohlcv`` stops at 2026-07-10 for ARWR/FN/HL and 2026-07-21 for TR while
    the caches run to 07-31. ``FN`` is recovered from ``yahoo`` (2026-08-04) — same basis,
    more history, strictly better. The other three have no adjusted alternative, so they
    take the COMPLETE cache stamped ``unadjusted`` rather than lose the window: those
    three are bit-identical to the cache across their whole 762-session overlap, so the
    stale rung protects nothing, and preferring it deleted two names from the
    postmortem's loser cohort outright. Coverage-with-disclosure beats a vanished row.
    When ``min_last`` is None (the default) the first hit wins and no extra file is read.
    """
    dd = default_data_dir() if data_dir is None else data_dir
    t = str(ticker)
    tried: list[str] = []
    books = _book if _book is not None else _Books(dd, groups)
    want = pd.Timestamp(min_last) if min_last is not None else None
    best: Resolved | None = None

    def _consider(s: pd.Series | None, src: str) -> Resolved | None:
        """Return a Resolved to hand back now, or None to keep walking."""
        nonlocal best
        if s is None:
            return None
        if want is None or s.index.max() >= want:
            return Resolved(t, s, src, True, list(tried))
        if best is None or s.index.max() > best.series.index.max():
            best = Resolved(t, s, src, True, list(tried))
        return None

    for src, tmpl in _FILE_RUNGS:
        tried.append(src)
        hit = _consider(
            _clip(_read_file_close(os.path.join(dd, tmpl.format(t=t))), asof, start), src)
        if hit is not None:
            return hit

    tried.append("baskets_extras")
    hit = _consider(_clip(books.extras.get(t), asof, start), "baskets_extras")
    if hit is not None:
        return hit

    if not allow_unadjusted:
        if best is not None:
            best.tried = list(tried)
            best.reason = (f"every adjusted rung ends before {want.date()}; "
                           f"freshest is {best.series.index.max().date()}")
            return best
        return Resolved(t, None, None, None, tried,
                        reason=("absent from every ADJUSTED source "
                                f"({', '.join(ADJUSTED_SOURCES)}) and "
                                "allow_unadjusted=False"))

    tried.append("closes_cache_UNADJUSTED")
    s = _clip(books.cache.get(t), asof, start)

    # A stale adjusted rung is a MISS, not a winner. Returning a series that stops before
    # the caller's window LOSES REAL BARS to buy a basis guarantee that, for these names,
    # protects nothing: measured 2026-08-06, HL/ARWR/TR are bit-identical (ratio 1.0000)
    # between cache and baskets/ohlcv across their whole 762-session overlap — the store
    # is simply stale, there is no distribution to correct — and preferring it dropped
    # HL@2026-07-01 and TR@2026-07-10 out of the postmortem's LOSER cohort entirely.
    # Silently deleting a loser is a far worse failure than pricing it on a disclosed
    # unadjusted basis, and it is the same coverage-first rule the rest of this ladder
    # follows. The fallback is stamped `unadjusted` and its `reason` names the staleness,
    # so it is never silent.
    if s is not None and (want is None or best is None or s.index.max() >= want):
        r = Resolved(t, s, "closes_cache_UNADJUSTED", False, tried)
        if best is not None:
            r.reason = (f"adjusted rungs all end before {want.date()} "
                        f"(freshest {best.price_source} @ "
                        f"{best.series.index.max().date()}); took the complete "
                        "UNADJUSTED cache rather than drop the window")
        return r

    if best is not None:
        # no usable cache either — a stale adjusted series still beats nothing
        best.tried = list(tried)
        best.reason = (f"every source ends before {want.date()}; freshest adjusted is "
                       f"{best.series.index.max().date()}")
        return best

    if s is not None:
        return Resolved(t, s, "closes_cache_UNADJUSTED", False, tried)

    return Resolved(t, None, None, None, tried,
                    reason=f"absent from every source on the ladder ({', '.join(LADDER)})")


def _provenance(stamp, counts, unadjusted, unresolved, *, asof, start, n_requested):
    return {
        "ladder": list(LADDER),
        "adjusted_sources": list(ADJUSTED_SOURCES),
        "unadjusted_sources": list(UNADJUSTED_SOURCES),
        "asof": str(asof) if asof is not None else None,
        "start": str(start) if start is not None else None,
        "n_requested": n_requested,
        "resolved_from": counts,
        "price_source": stamp,
        "names_on_unadjusted_basis": len(unadjusted),
        "unadjusted_tickers": sorted(unadjusted),
        "unresolved_tickers": sorted(unresolved),
    }


def close_panel(
    tickers,
    *,
    asof: str | pd.Timestamp | None = None,
    start: str | pd.Timestamp | None = None,
    data_dir: str | None = None,
    allow_unadjusted: bool = True,
    groups: tuple[str, ...] = CACHE_GROUPS,
) -> tuple[pd.DataFrame, dict]:
    """Wide close panel over ``tickers`` on the adjusted-first ladder.

    Returns ``(panel, provenance)``. The provenance carries a per-name ``price_source``
    stamp, per-rung counts, and the names that fell through to the unadjusted cache —
    counted and listed, never hidden, so a downstream reader can see how much of a
    result rests on a mixed basis.
    """
    dd = default_data_dir() if data_dir is None else data_dir
    books = _Books(dd, groups)
    cols: dict[str, pd.Series] = {}
    stamp: dict[str, str | None] = {}
    counts = {k: 0 for k in LADDER}
    counts["unresolved"] = 0
    unresolved: list[str] = []
    unadjusted: list[str] = []

    names = list(dict.fromkeys(map(str, tickers)))          # de-dupe, keep order
    for tk in names:
        r = resolve_close(tk, asof=asof, start=start, data_dir=dd,
                          allow_unadjusted=allow_unadjusted, groups=groups, _book=books)
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
    prov = _provenance(stamp, counts, unadjusted, unresolved,
                       asof=asof, start=start, n_requested=len(names))
    prov["panel_names"] = int(panel.shape[1]) if not panel.empty else 0
    prov["panel_sessions"] = int(panel.shape[0]) if not panel.empty else 0
    if not panel.empty:
        prov["panel_range"] = [str(panel.index.min().date()), str(panel.index.max().date())]
    return panel, prov


def overlay_adjusted(
    panel: pd.DataFrame,
    tickers,
    *,
    asof: str | pd.Timestamp | None = None,
    start: str | pd.Timestamp | None = None,
    data_dir: str | None = None,
    groups: tuple[str, ...] = CACHE_GROUPS,
) -> tuple[pd.DataFrame, dict]:
    """Re-base the named columns of an EXISTING panel onto the adjusted ladder.

    For callers that already hold a wide cache panel and must keep its column set and
    index semantics intact (row counts, coverage denominators, downstream ``.columns``
    consumers) while correcting the VALUES of the names they actually price.

    Only ``tickers`` are touched. A name with no adjusted counterpart keeps its existing
    column and is stamped ``closes_cache_UNADJUSTED`` — coverage is never traded for
    basis purity. A name absent from the panel and resolvable on an adjusted rung is
    ADDED, so this also covers the admitted-but-uncached case.

    Returns ``(panel, provenance)``; the provenance is the same shape ``close_panel``
    emits, plus ``n_columns_rebased``.
    """
    dd = default_data_dir() if data_dir is None else data_dir
    books = _Books(dd, groups)
    base = pd.DataFrame() if panel is None else panel
    names = list(dict.fromkeys(map(str, tickers)))

    stamp: dict[str, str | None] = {}
    counts = {k: 0 for k in LADDER}
    counts["unresolved"] = 0
    unresolved: list[str] = []
    unadjusted: list[str] = []
    replacement: dict[str, pd.Series] = {}

    for tk in names:
        # Adjusted rungs only: a miss must leave the existing cache column in place
        # rather than overwrite it with the same cache series read a second way.
        r = resolve_close(tk, asof=asof, start=start, data_dir=dd,
                          allow_unadjusted=False, groups=groups, _book=books)
        if r.ok:
            stamp[tk] = r.price_source
            counts[r.price_source] += 1
            replacement[tk] = r.series
            continue
        # fall back to whatever basis the panel already carries for this name
        in_panel = tk in getattr(base, "columns", []) and base[tk].notna().any()
        if in_panel or books.cache.get(tk) is not None:
            stamp[tk] = "closes_cache_UNADJUSTED"
            counts["closes_cache_UNADJUSTED"] += 1
            unadjusted.append(tk)
        else:
            stamp[tk] = None
            counts["unresolved"] += 1
            unresolved.append(tk)

    if replacement:
        add = pd.DataFrame(replacement)
        if base is None or getattr(base, "empty", True):
            out = add.sort_index()
        else:
            keep = base.drop(columns=[c for c in replacement if c in base.columns])
            out = pd.concat([keep, add], axis=1).sort_index()
        out = out.loc[:, ~out.columns.duplicated()]
    else:
        out = base

    prov = _provenance(stamp, counts, unadjusted, unresolved,
                       asof=asof, start=start, n_requested=len(names))
    prov["n_columns_rebased"] = len(replacement)
    prov["panel_names"] = int(out.shape[1]) if not getattr(out, "empty", True) else 0
    prov["panel_sessions"] = int(out.shape[0]) if not getattr(out, "empty", True) else 0
    return out, prov
