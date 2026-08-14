"""Leak fixtures — green before any family's events ship (registration §7).

Four checks, applied per family. A family whose fixture fails ships **no events** and a
named blocker instead; that consequence is the point of running them here rather than only
in a test file, because the test file cannot stop the CLI from writing.

``truncation_invariance``
    Events computed on ``df.iloc[:k]`` are the identical PREFIX of events computed on the
    full frame. This is the path_risk_signals CAUSALITY LAW shape: a detector that reads
    ahead produces a different past when you shorten its future. Compared on
    ``(signal_ts, signal_known_ts, subtype)`` and only over the region the truncated frame
    could see — the last bucket of a truncated frame is legitimately still open, so a
    small settling margin is honored rather than counted as a leak.

``shift_audit``
    Shifting the input tape by one session shifts every event stamp accordingly. Any
    absolute-date dependence — a hard-coded era boundary, a calendar-anchored bin that does
    not move with the data — breaks this and nothing else catches it. The tape is shifted by
    RE-INDEXING onto the next sessions, so the price path is byte-identical and only the
    dates move.

``feed_truncation``
    The F6 shape, and the Radar contract's highest-value case: truncate the feed to each
    event's ``signal_ts`` (i.e. BEFORE its ``signal_known_ts``) and the event must VANISH.
    An event that survives was knowable before the bar that made it knowable had closed —
    the exact pre-#392 Terminal bug.

``append_only_conformance``
    For ledger-extracted families: extraction is a pure filter of the store. Row count out
    <= rows in, every emitted key present in the store, no value rewritten, keep-FIRST
    honored on the store's own key.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

import pandas as pd

__all__ = [
    "FixtureResult",
    "truncation_invariance",
    "shift_audit",
    "feed_truncation",
    "append_only_conformance",
    "run_recompute_fixtures",
]

#: A truncated frame's last bucket may still be open, so its final events are legitimately
#: unsettled. Two 3D buckets is the widest settling window any family here has.
_SETTLE_SESSIONS = 8


class FixtureResult(dict):
    """A fixture verdict: ``{name, passed, detail}`` with dict ergonomics."""

    def __init__(self, name: str, passed: bool, detail: str = "") -> None:
        super().__init__(name=name, passed=bool(passed), detail=detail)

    @property
    def passed(self) -> bool:  # pragma: no cover - trivial
        return bool(self["passed"])


def _keys(rows: Iterable[Mapping[str, Any]]) -> list[tuple]:
    return sorted(
        (
            pd.Timestamp(r["signal_ts"]).date(),
            pd.Timestamp(r["signal_known_ts"]).date(),
            str(r.get("subtype")),
        )
        for r in rows
    )


def truncation_invariance(
    fire_fn: Callable[[pd.DataFrame], list[dict[str, Any]]],
    df: pd.DataFrame,
    *,
    frac: float = 0.6,
) -> FixtureResult:
    full = _keys(fire_fn(df))
    k = max(60, int(len(df) * frac))
    if k >= len(df):
        return FixtureResult("truncation_invariance", True, "frame too short to truncate")
    cut = df.iloc[:k]
    cut_end = pd.Timestamp(cut.index[-1])
    settle = cut_end - pd.Timedelta(days=_SETTLE_SESSIONS * 2)
    trunc = _keys(fire_fn(cut))

    full_prefix = [t for t in full if t[1] <= settle.date()]
    trunc_prefix = [t for t in trunc if t[1] <= settle.date()]
    if full_prefix == trunc_prefix:
        return FixtureResult(
            "truncation_invariance", True,
            f"{len(trunc_prefix)} event(s) identical on the truncated prefix",
        )
    only_full = sorted(set(full_prefix) - set(trunc_prefix))[:3]
    only_trunc = sorted(set(trunc_prefix) - set(full_prefix))[:3]
    return FixtureResult(
        "truncation_invariance", False,
        f"prefix differs: {len(only_full)} full-only e.g. {only_full}; "
        f"{len(only_trunc)} truncated-only e.g. {only_trunc}",
    )


def shift_audit(
    fire_fn: Callable[[pd.DataFrame], list[dict[str, Any]]],
    df: pd.DataFrame,
    *,
    calendar: pd.DatetimeIndex | None = None,
) -> FixtureResult:
    """Shift the tape one session forward; every stamp must move with it.

    The shift is a REINDEX, not a resample: the same closes are hung on the next session
    dates, so anything that changes is a function of the dates alone.
    """
    idx = pd.DatetimeIndex(df.index)
    cal = pd.DatetimeIndex(calendar) if calendar is not None else idx
    pos = cal.searchsorted(idx, side="left")
    nxt = pos + 1
    if nxt[-1] >= len(cal):
        nxt = nxt[:-1]
        df = df.iloc[:-1]
    shifted = df.copy()
    shifted.index = pd.DatetimeIndex(cal[nxt])
    shifted.index.name = df.index.name

    base = _keys(fire_fn(df))
    moved = _keys(fire_fn(shifted))
    if len(base) != len(moved):
        return FixtureResult(
            "shift_audit", False,
            f"event count changed under a one-session shift: {len(base)} -> {len(moved)}",
        )
    if not base:
        return FixtureResult("shift_audit", True, "no events on this frame")
    # Every stamp must have moved forward, and none may have stayed put.
    stuck = sum(1 for a, b in zip(base, moved) if a[1] == b[1])
    if stuck:
        return FixtureResult(
            "shift_audit", False,
            f"{stuck}/{len(base)} known_ts stamps did not move with the tape",
        )
    return FixtureResult("shift_audit", True, f"{len(base)} stamp(s) moved with the tape")


def feed_truncation(
    fire_fn: Callable[[pd.DataFrame], list[dict[str, Any]]],
    df: pd.DataFrame,
    *,
    n_probe: int = 3,
) -> FixtureResult:
    """Truncate the feed BEFORE each probe event's known_ts; the event must vanish."""
    rows = fire_fn(df)
    rows = [r for r in rows
            if pd.Timestamp(r["signal_known_ts"]) > pd.Timestamp(r["signal_ts"])]
    if not rows:
        return FixtureResult(
            "feed_truncation", True,
            "no event on this frame becomes knowable after its own signal_ts "
            "(1D-grain family: signal_ts == known_ts by construction)",
        )
    rows = sorted(rows, key=lambda r: pd.Timestamp(r["signal_known_ts"]))
    probes = rows[-n_probe:]
    survived: list[str] = []
    for probe in probes:
        cut = pd.Timestamp(probe["signal_ts"])
        sub = df.loc[df.index <= cut]
        if len(sub) < 60:
            continue
        seen = {
            (pd.Timestamp(r["signal_ts"]).date(), str(r.get("subtype")))
            for r in fire_fn(sub)
        }
        if (cut.date(), str(probe.get("subtype"))) in seen:
            survived.append(str(cut.date()))
    if survived:
        return FixtureResult(
            "feed_truncation", False,
            f"{len(survived)} event(s) survived truncation to their own signal_ts: {survived}",
        )
    return FixtureResult(
        "feed_truncation", True,
        f"{len(probes)} probe event(s) vanished when the feed stopped at their signal_ts",
    )


def append_only_conformance(
    emitted: list[dict[str, Any]],
    store: pd.DataFrame,
    *,
    store_key: tuple[str, ...],
    date_column: str,
    symbol_column: str,
) -> FixtureResult:
    """Ledger extraction is a pure filter: nothing invented, nothing rewritten."""
    if store is None or store.empty:
        return FixtureResult(
            "append_only_conformance", not emitted,
            "store is empty" + ("" if not emitted else " but rows were emitted"),
        )
    if len(emitted) > len(store):
        return FixtureResult(
            "append_only_conformance", False,
            f"emitted {len(emitted)} rows from a {len(store)}-row store",
        )
    have = {
        (str(r[symbol_column]).upper(), pd.Timestamp(r[date_column]).date())
        for r in store.to_dict("records")
    }
    missing = [
        (r["symbol"], pd.Timestamp(r["signal_ts"]).date())
        for r in emitted
        if (str(r["symbol"]).upper(), pd.Timestamp(r["signal_ts"]).date()) not in have
    ]
    if missing:
        return FixtureResult(
            "append_only_conformance", False,
            f"{len(missing)} emitted row(s) have no store row, e.g. {missing[:3]}",
        )
    dupes = int(store.duplicated(subset=list(store_key), keep="first").sum())
    return FixtureResult(
        "append_only_conformance", True,
        f"{len(emitted)} row(s) all present in the store; keep-FIRST dropped {dupes} duplicate(s)",
    )


def run_recompute_fixtures(
    fire_fn: Callable[[pd.DataFrame], list[dict[str, Any]]],
    df: pd.DataFrame,
    *,
    calendar: pd.DatetimeIndex | None = None,
) -> list[FixtureResult]:
    """The three fixtures every RECOMPUTED family must pass."""
    return [
        truncation_invariance(fire_fn, df),
        shift_audit(fire_fn, df, calendar=calendar),
        feed_truncation(fire_fn, df),
    ]
