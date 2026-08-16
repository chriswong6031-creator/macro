"""Panel assembly and the replay session calendar (prereg §2).

TWO DECLARED UNIVERSES, and nothing invents a third:

* **Panel-A** — the curated deep store ``data/stocks/*.parquet`` (split+dividend,
  H/L/C/V, 1999+).  C1/C2/C3 replay here, plus the §13-row-16 basis-fidelity
  check.  Disclosure that rides every Panel-A table: curated, currently-covered,
  large-cap-tilted.
* **Panel-B** — the broad stock-library universe (``data/universe/membership.parquet``),
  price-served by the vendor daily plane.  G0/C5/C4-features/incumbent replay here.
  Disclosure: **current-constituent** membership; names delisted before run date are
  absent, which FLATTERS washout-buying results.

PURE-ENGINE LAW.  This module reads parquet files under an injected ``root`` and
does nothing else — no network, no wall clock, no environment, no writes.  Daily
frames arrive through an injected ``loader`` (:func:`load_panel_daily`), which is
what keeps the vendor client in ``scripts/`` and CI network-free.

THE SESSION CALENDAR IS BENCH-ONLY, ON PURPOSE
-----------------------------------------------
:func:`session_calendar` reads the BENCH frame (SPY) and nothing else.  A union
over a mixed asset directory inherits weekend rows from crypto/FX/futures, and the
damage is silent and two-fold: positional horizons span 5/7 of their label (a
"21-session" window becomes 15 equity sessions), and a calendar-derived date
landing on a weekend row makes ``searchsorted`` return THAT row — dropping a large
share of sample dates without a single error.  The bench index is additionally
filtered to Mon–Fri, so even a bench series contaminated upstream cannot put a
Saturday into the replay's session positions.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Mapping, Sequence

import pandas as pd

#: The benchmark whose sessions ARE the replay calendar (§7 bench leg is SPY).
BENCH = "SPY"

PANEL_A = "A"
PANEL_B = "B"

#: Disclosure strings §2 requires on every table of each panel.  Kept here so a
#: results writer cannot paraphrase them into something weaker.
PANEL_DISCLOSURE = {
    PANEL_A: ("Panel-A is a curated, currently-covered, large-cap-tilted set; "
              "results generalize only with that caveat."),
    PANEL_B: ("Panel-B membership is CURRENT-CONSTITUENT: names delisted before the "
              "run date are absent, which flatters washout-buying results."),
}


class PanelError(RuntimeError):
    """A panel source is missing or malformed.  Named, never silently empty."""


# --------------------------------------------------------------------------- #
# name lists
# --------------------------------------------------------------------------- #
def panel_a_names(root: str | Path) -> list[str]:
    """Panel-A: the curated store's stems, sorted.

    Refuses on an absent/empty directory rather than returning ``[]`` — an empty
    Panel-A would make every Panel-A read vacuously "no episodes", which is the
    coverage-blindness failure this repo has shipped before.
    """
    stocks = Path(root) / "data" / "stocks"
    if not stocks.is_dir():
        raise PanelError(f"Panel-A source {stocks} is not a directory (sparse "
                         f"worktree? `python3 scripts/worktree_sparse.py add data`)")
    names = sorted(p.stem for p in stocks.glob("*.parquet"))
    if not names:
        raise PanelError(f"Panel-A source {stocks} holds no parquet files")
    return names


def panel_b_names(root: str | Path) -> list[str]:
    """Panel-B: distinct tickers in the stock-library membership table, sorted."""
    frame = _membership(root)
    names = sorted({str(t).strip() for t in frame["ticker"].dropna() if str(t).strip()})
    if not names:
        raise PanelError("membership.parquet carries no tickers")
    return names


def _membership(root: str | Path) -> pd.DataFrame:
    path = Path(root) / "data" / "universe" / "membership.parquet"
    if not path.exists():
        raise PanelError(f"Panel-B source {path} is missing")
    frame = pd.read_parquet(path)
    if "ticker" not in frame.columns:
        raise PanelError(f"{path} has no 'ticker' column")
    return frame


def sector_of(root: str | Path) -> dict[str, str]:
    """ticker -> GICS sector name (§7's CEM cell needs it for every panel member).

    Source order is the prereg's: ``data/universe/membership.parquet`` (qledger's
    own ``sector_of_ticker`` source), then ``data/breadth/ticker_sectors.parquet``
    for names the membership table does not sector.  A name in neither is simply
    ABSENT from the mapping — the caller records ``sector=None`` and the CEM cell
    refuses to match it, which is the honest outcome; inventing an "Unknown"
    sector would silently pool unrelated names into one cell.
    """
    out: dict[str, str] = {}
    fallback = Path(root) / "data" / "breadth" / "ticker_sectors.parquet"
    if fallback.exists():
        frame = pd.read_parquet(fallback)
        if {"ticker", "sector"}.issubset(frame.columns):
            for t, s in zip(frame["ticker"], frame["sector"]):
                if pd.notna(t) and pd.notna(s):
                    out[str(t).strip()] = str(s).strip()
    try:
        primary = _membership(root)
    except PanelError:
        return out
    if "sector" in primary.columns:
        for t, s in zip(primary["ticker"], primary["sector"]):
            if pd.notna(t) and pd.notna(s) and str(s).strip():
                out[str(t).strip()] = str(s).strip()   # primary wins
    return out


# --------------------------------------------------------------------------- #
# frames
# --------------------------------------------------------------------------- #
def load_panel_daily(names: Sequence[str],
                     loader: Callable[[str], pd.DataFrame | None],
                     ) -> dict[str, pd.DataFrame]:
    """Load one daily frame per name through an INJECTED loader.

    ``loader`` is the vendor client's daily reader (Panel-B, and Panel-A's
    C1/C2/C3 confirmed-daily history — §4) or a curated ``data/stocks`` reader
    (Panel-A G0/C5 detector math).  Returning ``None`` means "this name has no
    usable history" and the name is simply absent from the result: the caller
    counts the gap in the §13-row-14 refusal census.  Empty frames are dropped for
    the same reason — a zero-row frame downstream reads as a computable name with
    no signal, which is a different (and false) statement.
    """
    out: dict[str, pd.DataFrame] = {}
    for name in names:
        frame = loader(name)
        if frame is None or not len(frame):
            continue
        frame = frame.copy()
        frame.index = pd.DatetimeIndex(frame.index).normalize()
        out[str(name)] = frame.sort_index()
    return out


def session_calendar(frames: Mapping[str, pd.DataFrame] | pd.DataFrame,
                     *, bench: str = BENCH) -> pd.DatetimeIndex:
    """The replay's session index — the BENCH frame's sessions, weekends removed.

    ``frames`` may be the whole panel mapping (the bench key is picked out of it)
    or the bench frame directly.  Every other name is IGNORED: see the module
    docstring — a union over mixed assets inherits weekend rows and silently
    rescales every positional horizon.

    Raises :class:`PanelError` when the bench is absent, because a replay with no
    calendar cannot compute a single §7 window and must not proceed on a guess.
    """
    if isinstance(frames, pd.DataFrame):
        frame = frames
    else:
        if bench not in frames:
            raise PanelError(
                f"session calendar needs the bench frame {bench!r}; got "
                f"{sorted(frames)[:8]}{'…' if len(frames) > 8 else ''}. The calendar is "
                f"NEVER a union over the panel — non-equity rows would put weekends "
                f"into the session index")
        frame = frames[bench]
    index = pd.DatetimeIndex(pd.Index(frame.index)).normalize()
    index = index[~index.duplicated(keep="first")].sort_values()
    equity = index[index.dayofweek < 5]
    if equity.empty:
        raise PanelError(f"bench {bench!r} contributed no weekday sessions")
    return pd.DatetimeIndex(equity, name="session")


class SessionPositions(dict):
    """``Timestamp -> ordinal`` lookup that is safe to SHARE instead of copy.

    A plain dict here costs the W5 replay hours.  pandas propagates
    ``DataFrame.attrs`` through ``NDFrame.__finalize__``, which **deep-copies**
    the attrs payload on every metadata-propagating operation — so every column
    access, comparison and boolean mask inside ``controls.eligible_pool`` /
    ``controls.match`` re-copied this entire session map, once per operation,
    once per episode.  Measured on a 300-name x 600-session panel (400 episodes):
    92% of ``_attach_and_match``'s runtime was ``copy.deepcopy`` under
    ``__finalize__``, 74M deepcopy calls, and the cost grows with the panel's
    session count — which is why the definitive full-era runs spent CPU-hours
    where the arithmetic is milliseconds.

    Copying buys nothing: the map is derived, read-only substrate.  This subclass
    makes that a PROPERTY rather than a hope — mutation is refused, which is what
    makes returning ``self`` from ``__deepcopy__`` provably safe.  Every read
    behaviour (``get`` / ``in`` / ``len`` / iteration / equality against a plain
    dict) is dict's own, unchanged, so ``controls._session_offset`` and the panel
    attrs contract see exactly what they saw before.
    """

    __slots__ = ()

    def _immutable(self, *_args, **_kwargs):
        raise TypeError(
            "SessionPositions is read-only: it is shared (never deep-copied) "
            "across every frame derived from a feature panel, so an in-place "
            "edit would silently retune the +/-5-session control exclusion for "
            "already-derived frames.  Build a new mapping instead.")

    __setitem__ = _immutable
    __delitem__ = _immutable
    __ior__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable

    def __copy__(self) -> "SessionPositions":
        return self

    def __deepcopy__(self, memo) -> "SessionPositions":  # noqa: ANN001
        return self

    def __reduce__(self):
        # Rebuild through the constructor: the blocked ``__setitem__``/``update``
        # would otherwise break the default dict-subclass unpickling path (and
        # ProcessPool hand-off).
        return (self.__class__, (dict(self),))


def session_positions(calendar: pd.DatetimeIndex) -> SessionPositions:
    """``Timestamp -> ordinal position`` — what ``controls._session_offset`` reads.

    Attached to a feature panel as ``attrs["session_pos_by_date"]``.  Positions are
    over the BENCH calendar, so "±5 sessions" means five TRADING sessions for every
    name, including one that did not trade on some of them.
    """
    return SessionPositions(
        (pd.Timestamp(ts), pos) for pos, ts in enumerate(pd.DatetimeIndex(calendar)))


def common_eligible(frames: Mapping[str, pd.DataFrame], *, warmup: int,
                    ) -> dict[str, pd.Timestamp]:
    """First session at which each name has ``warmup`` confirmed bars (§2).

    The §2 common-eligibility law needs one of these per detector warm-up; the
    eligibility GAP between two detectors is then a set difference the caller
    reports beside every cross-detector read, never a silent inner join.
    """
    out: dict[str, pd.Timestamp] = {}
    for name, frame in frames.items():
        index = pd.DatetimeIndex(frame.index)
        if len(index) >= int(warmup) > 0:
            out[name] = pd.Timestamp(index[int(warmup) - 1])
    return out


__all__ = ["BENCH", "PANEL_A", "PANEL_B", "PANEL_DISCLOSURE", "PanelError",
           "SessionPositions", "panel_a_names", "panel_b_names", "sector_of",
           "load_panel_daily", "session_calendar", "session_positions",
           "common_eligible"]
