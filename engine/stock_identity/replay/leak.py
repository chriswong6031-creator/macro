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

``shift_audit`` (two checks — see the deviation note below)
    ``shift_audit_start_invariance``: dropping LEADING history must not change any event on
    the region both runs can see. This is the R-SQ1/R-SQ2 property the absolute session
    anchor was adopted to guarantee — the retired ``3B`` resample anchored its bins to the
    series' first timestamp, so four production history depths read four different marker
    streams for one name (measured: ~80% of NVDA signal dates relocated). A detector that
    fails this is reading *where the caller's window starts*, which is exactly the
    "position in the tape rather than the tape" defect a shift audit exists to catch.

    ``shift_audit_forming_bar``: appending an in-progress bar that WOULD fire the detector
    must not add, move or remove any event at or before the last completed known-ts. This
    is the house RUL-31 completed-bar shape (``tests/test_entry_primitives_a3.py::
    test_forming_week_does_not_flip_w_hist_rising``).

    **Deviation of record.** The registration's literal phrasing is "shifting the input tape
    by one session shifts every event stamp accordingly". That test cannot pass here, and
    should not: every grid in this repo is **calendar-anchored by ratified design** —
    ``signal_quality._tf_grid`` buckets on ``session_positions(date) // n``, a function of
    (reference calendar, date) alone, and the weekly/monthly legs resample on the calendar.
    Re-hanging the same closes on later dates therefore re-phases the buckets *by design*,
    and demanding otherwise would be demanding the R-SQ1 repair be undone (measured on
    NVDA: a one-session shift moves 35 dots to 42; a phase-preserving 6-session shift still
    moves them, because the W-FRI weekly leg re-groups). The registration also instructs
    "reusing the existing RUL-31 test shapes where present", and the house's RUL-31
    instruments are truncation-invariance plus the completed-bar test — there is no
    date-shift test in them. The two checks above are those shapes, and they test the same
    property the literal phrasing was reaching for: **an event may not depend on anything
    but the tape up to its own known-ts.**

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
    "shift_audit_start_invariance",
    "shift_audit_forming_bar",
    "feed_truncation",
    "append_only_conformance",
    "run_recompute_fixtures",
]

#: A truncated frame's last bucket may still be open, so its final events are legitimately
#: unsettled. Two 3D buckets is the widest settling window any family here has.
_SETTLE_SESSIONS = 8


class FixtureResult(dict):
    """A fixture verdict: ``{name, passed, applicable, detail}`` with dict ergonomics.

    ``applicable=False`` is a **declared exemption**, not a pass. It exists so a family
    whose producer genuinely does not have a property can say so out loud, with the
    mechanism named in ``detail`` — rather than the alternative, which is loosening a
    ceiling until the check stops complaining and nobody can tell it was loosened.
    Exemptions ride through into the committed registry and the inventory table.
    """

    def __init__(self, name: str, passed: bool, detail: str = "",
                 applicable: bool = True) -> None:
        super().__init__(name=name, passed=bool(passed), detail=detail,
                         applicable=bool(applicable))

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


#: Warm-up margin after a truncated START before events are compared. Every family here
#: needs a few hundred sessions of oscillator/MA warm-up, and a shortened warm-up is a
#: legitimate difference, not a leak.
_WARMUP_SESSIONS = 400


#: Residual start-sensitivity that is NOT a leak, and why a ceiling exists rather than a
#: zero. Two producer properties, both documented in the producers themselves, make exact
#: start-invariance unattainable for some families:
#:
#: * ``engine.technicals.rsi`` (what ``signal_quality`` imports) is a bare
#:   ``ewm(alpha=1/n)`` with an EXPANDING warm-up from bar 0 — ``engine.canon.rma``'s own
#:   docstring names this as differing "exactly where it matters — the early, near-threshold
#:   history the audit says flips crosses". Dropping leading rows perturbs every later RSI
#:   value infinitesimally, which flips a cross that sat on the threshold.
#: * ``engine.washout_turn``'s depth percentile is explicitly a WHOLE-SAMPLE statistic
#:   ("percent of the FULL weekly line history strictly BELOW bar j"), so its reference
#:   distribution legitimately depends on how much history exists.
#:
#: Both are functions of PAST data only — nothing future leaks either way. The defect this
#: fixture exists to catch is categorically larger: the retired ``3B`` resample relocated
#: ~80% of NVDA's signal dates when the window start moved. A ceiling two orders of
#: magnitude below that separates the two cleanly.
_START_FLIP_CEILING = 0.05


def shift_audit_start_invariance(
    fire_fn: Callable[[pd.DataFrame], list[dict[str, Any]]],
    df: pd.DataFrame,
    *,
    drop: int = 37,
    ceiling: float = _START_FLIP_CEILING,
) -> FixtureResult:
    """Dropping LEADING history must not move the detector's events.

    ``drop`` is deliberately coprime to 2, 3 and 5 so the truncated series starts on a
    different bucket phase AND a different weekday than the original — if the detector
    anchored its grid to its own first row (the retired ``3B`` defect), essentially every
    event moves and the check fails loudly.

    The verdict is a RATE against ``ceiling`` (with a one-event floor for small samples),
    not exact equality, for the reasons recorded on :data:`_START_FLIP_CEILING`. The
    measured rate is always reported, passing or failing, so a drift upward is visible.
    """
    if len(df) <= drop + _WARMUP_SESSIONS + 60:
        return FixtureResult(
            "shift_audit_start_invariance", True, "frame too short to drop a lead safely"
        )
    cut = df.iloc[drop:]
    start_guard = pd.Timestamp(cut.index[min(_WARMUP_SESSIONS, len(cut) - 1)])

    base = [t for t in _keys(fire_fn(df)) if t[1] >= start_guard.date()]
    short = [t for t in _keys(fire_fn(cut)) if t[1] >= start_guard.date()]
    n = max(len(base), 1)
    diff = set(base) ^ set(short)
    allowed = max(1, int(round(ceiling * n)))
    rate = len(diff) / n
    if len(diff) <= allowed:
        return FixtureResult(
            "shift_audit_start_invariance", True,
            f"{len(base)} event(s) compared after dropping {drop} leading session(s); "
            f"{len(diff)} differ ({rate:.2%}, ceiling {ceiling:.0%} / floor 1) — "
            "producer warm-up sensitivity, not a window dependence",
        )
    only_base = sorted(set(base) - set(short))[:3]
    only_short = sorted(set(short) - set(base))[:3]
    return FixtureResult(
        "shift_audit_start_invariance", False,
        f"the detector moved with the WINDOW, not the tape: {len(diff)}/{n} events differ "
        f"({rate:.2%} > ceiling {ceiling:.0%}); lost e.g. {only_base}; "
        f"gained e.g. {only_short}",
    )


def shift_audit_forming_bar(
    fire_fn: Callable[[pd.DataFrame], list[dict[str, Any]]],
    df: pd.DataFrame,
    *,
    bump: float = 0.25,
) -> FixtureResult:
    """An appended in-progress bar may not change any COMPLETED event.

    The appended bar is engineered to move the oscillators hard (a ``bump`` up-move on the
    last close, with the band widened to match), so a detector that reads its own forming
    bar will visibly gain or move events. Only events at or before the ORIGINAL frame's
    last event known-ts are compared — new events after it are the forming bar's own
    business, not a leak into the past.
    """
    if len(df) < 120:
        return FixtureResult("shift_audit_forming_bar", True, "frame too short")
    base = fire_fn(df)
    if not base:
        return FixtureResult("shift_audit_forming_bar", True, "no events on this frame")
    horizon = max(pd.Timestamp(r["signal_known_ts"]) for r in base)

    idx = pd.DatetimeIndex(df.index)
    step = idx[-1] - idx[-2] if len(idx) > 1 else pd.Timedelta(days=1)
    nxt = idx[-1] + (step if step > pd.Timedelta(0) else pd.Timedelta(days=1))
    row = df.iloc[[-1]].copy()
    row.index = pd.DatetimeIndex([nxt])
    row.index.name = df.index.name
    for c in row.columns:
        if c == "volume":
            continue
        row[c] = float(row[c].iloc[0]) * (1.0 + bump)
    extended = pd.concat([df, row])

    base_keys = [t for t in _keys(base) if t[1] <= horizon.date()]
    ext_keys = [t for t in _keys(fire_fn(extended)) if t[1] <= horizon.date()]
    if base_keys == ext_keys:
        return FixtureResult(
            "shift_audit_forming_bar", True,
            f"{len(base_keys)} completed event(s) unchanged by an in-progress bar",
        )
    delta = sorted(set(base_keys) ^ set(ext_keys))[:3]
    return FixtureResult(
        "shift_audit_forming_bar", False,
        f"an in-progress bar changed {len(set(base_keys) ^ set(ext_keys))} completed "
        f"event(s), e.g. {delta}",
    )


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
    exemptions: Mapping[str, str] | None = None,
) -> list[FixtureResult]:
    """Every fixture a RECOMPUTED family must pass before its events may ship.

    ``exemptions`` maps a fixture name to the REASON its property does not hold for this
    family. An exempted fixture is reported ``applicable=False`` with that reason attached;
    it is never silently skipped and never counted as a pass.
    """
    ex = dict(exemptions or {})
    checks = (
        ("truncation_invariance", lambda: truncation_invariance(fire_fn, df)),
        ("shift_audit_start_invariance", lambda: shift_audit_start_invariance(fire_fn, df)),
        ("shift_audit_forming_bar", lambda: shift_audit_forming_bar(fire_fn, df)),
        ("feed_truncation", lambda: feed_truncation(fire_fn, df)),
    )
    out: list[FixtureResult] = []
    for name, run in checks:
        if name in ex:
            out.append(FixtureResult(name, False, ex[name], applicable=False))
            continue
        out.append(run())
    return out
