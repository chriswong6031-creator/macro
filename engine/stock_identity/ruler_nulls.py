"""Stock Identity W3A — mandatory localization nulls/controls (freeze §4.3, plan Task 3).

Three of the freeze's seven mandatory nulls/controls are ruler-side and built here:

1. **Count/dwell-matched random fire placement** (:func:`random_fire_null`,
   freeze §4.3 item 1) — every expert keeps its exact fire COUNT *and* its
   inter-fire gap MULTISET (dwell pattern): per ``(family_key, symbol)`` the
   ordered session-gap sequence between consecutive fires is permuted (seeded)
   and re-anchored at a seeded random start session within the symbol's own
   trading-calendar coverage (M11-regression — an EARLIER repair placed each
   fire independently and uniformly, which is count-matched but destroys the
   dwell/burstiness structure entirely; that is a *weaker*, differently-shaped
   null than the freeze's own "count/dwell-matched" requirement, not a stronger
   one).
2. **Grain/cadence null** (:func:`grain_cadence_null`) — a deterministic, seeded,
   trading-session-space circular shift that preserves cadence PHASE: one
   multiple ``K`` of the group's own grain period, drawn from the declared
   ``[63, 252]``-session range, is applied per ``(family_key, symbol)`` to every
   fire's ``signal_ts`` on the symbol's own trading calendar, wrapping within
   coverage (M4-regression — an EARLIER repair drew an unconstrained offset and
   collapsed ``signal_known_ts``/``signal_ts`` to the SAME shifted value, which
   breaks a weekly-grain group's weekday phase and destroys each event's own
   stamp lag; both are restored here: shifting ``signal_ts`` by a
   period-constrained ``K`` and reconstructing
   ``signal_known_ts = new_signal_ts + (orig_known_ts - orig_signal_ts)`` per
   event). **Weekday-phase MAJOR fix (delta-review third pass):** a period-5
   multiple of ``K`` is a multiple of the group's grain period, but on a REAL
   trading calendar (which carries holidays) a fixed number of SESSIONS is not
   a fixed number of CALENDAR WEEKS — the M4-regression fix above only
   *appeared* weekday-preserving because its own discriminating test used a
   holiday-free ``pd.bdate_range`` fixture, where session count and calendar
   weeks coincide exactly. :func:`grain_cadence_null` now explicitly searches
   for a ``K`` that lands the group's earliest ("anchor") fire on the SAME
   weekday, verifies every OTHER fire in the group also preserves its own
   weekday under that same ``K`` (bounded, deterministic-seeded retries over
   the nearest admissible multiples to the original draw), and — only if no
   admissible ``K`` makes every fire's weekday agree within the retry budget —
   falls back to the largest anchor-admissible multiple and marks that group's
   rows ``phase_preserved: false`` rather than silently claiming a phase
   preservation it did not actually verify.
3. **Equal-proximity comparison** (:func:`equal_proximity_control`) — pairs
   cross-family fires within the SAME episode AND SAME grain whose ATR-distance
   gap is within a declared tolerance (freeze review finding M2/M3 — the prior
   implementation paired fires globally across symbols/episodes/grains, which is
   not a "similarly-placed" comparison at all; M3-minor then added grain to the
   group key — a daily-cadence fire and a weekly-cadence fire landing at a
   similar ATR distance are not a "similarly-placed" comparison either, since
   their measurement windows differ).

No function here inspects per-name outcome rank to choose a parameter, expert or
neighborhood (``DNR:KILL-OUTCOME-AUDITION``); each null is a pure, seeded (where
randomness is involved) transform of the input, and every seed used is recorded
by the caller into the W3 registration artifact.
"""
from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd

__all__ = [
    "PROXIMITY_PAIR_COLUMNS",
    "GRAIN_PERIOD_SESSIONS",
    "GRAIN_CADENCE_PHASE_RETRY_BUDGET",
    "random_fire_null",
    "grain_cadence_null",
    "equal_proximity_control",
]

PROXIMITY_PAIR_COLUMNS: tuple[str, ...] = (
    "left_event_id", "right_event_id", "left_family_key", "right_family_key",
    "left_atr_dist", "right_atr_dist", "atr_dist_gap", "episode_id", "grain",
)

#: Deterministic seeded circular-shift offset range for the grain/cadence null
#: (freeze review finding M4) — in TRADING sessions, never calendar days.
GRAIN_CADENCE_NULL_MIN_SESSIONS = 63
GRAIN_CADENCE_NULL_MAX_SESSIONS = 252

#: Trading-session period implied by a W2 grain label (M4-regression) — the
#: closed set of grain strings W2's nine family groups actually emit
#: (`research/stock_identity/W3_RULER_REGISTRATION.md` §1.1: ``1D``, ``3D``,
#: ``2W``, ``W``, ``1D-state-over-2D/3D-buckets``). The grain/cadence null's
#: offset ``K`` must be a multiple of this period so the shift preserves cadence
#: PHASE (e.g. a weekly-grain group's weekday distribution), not merely
#: magnitude — an unconstrained offset can land a weekly fire on any weekday.
GRAIN_PERIOD_SESSIONS: dict[str, int] = {
    "1D": 1,
    "3D": 3,
    "W": 5,
    "2W": 10,
}

#: Bounded retry budget for the weekday-phase search (delta-review MAJOR
#: weekday-phase finding): the number of admissible-K candidates (nearest to
#: the original seeded draw first, deterministic tie-break) tried before
#: :func:`grain_cadence_null` gives up on an all-fires-agree K and falls back
#: to the largest anchor-admissible multiple with ``phase_preserved: false``.
GRAIN_CADENCE_PHASE_RETRY_BUDGET = 25


def _grain_period_sessions(grain: Any) -> int:
    """The session period for ``grain``, or ``1`` (no phase constraint) for any
    label outside :data:`GRAIN_PERIOD_SESSIONS` — e.g. the composite
    ``1D-state-over-2D/3D-buckets`` family label, which carries no single clean
    weekly/biweekly phase to preserve."""
    g = str(grain or "").strip().upper()
    return GRAIN_PERIOD_SESSIONS.get(g, 1)


def _symbol_calendar(bars_by_symbol: Mapping[str, pd.DataFrame] | None, symbol: str) -> pd.DatetimeIndex:
    if not bars_by_symbol:
        return pd.DatetimeIndex([])
    df = bars_by_symbol.get(symbol)
    if df is None or df.empty:
        return pd.DatetimeIndex([])
    return pd.DatetimeIndex(sorted(df.index.unique()))


def _ensure_signal_ts_and_known_ts(out: pd.DataFrame) -> pd.DataFrame:
    """Normalize ``signal_ts``/``signal_known_ts`` to datetime, defaulting a
    missing ``signal_ts`` to ``signal_known_ts`` (no lag) so both nulls below can
    always compute a stamp lag, even against a caller that only carries
    ``signal_known_ts``."""
    out["signal_known_ts"] = pd.to_datetime(out["signal_known_ts"])
    if "signal_ts" not in out.columns:
        out["signal_ts"] = out["signal_known_ts"]
    out["signal_ts"] = pd.to_datetime(out["signal_ts"])
    return out


def random_fire_null(
    events: pd.DataFrame, bars_by_symbol: Mapping[str, pd.DataFrame], seed: int,
) -> pd.DataFrame:
    """Count/dwell-matched random fire placement (freeze §4.3 item 1;
    M11-regression fix).

    For each ``(family_key, symbol)`` group: sort the group's fires by
    ``signal_ts``, convert each to its session-index position on the symbol's
    own trading calendar, and take the ordered sequence of inter-fire gaps (in
    trading sessions) between consecutive fires. That gap sequence is a
    MULTISET the null must preserve exactly (dwell-matched) while breaking
    correspondence to the real dates — so it is PERMUTED with the seeded RNG,
    then the permuted sequence is re-anchored at a seeded random start session
    drawn uniformly from every position at which the whole shifted sequence
    still fits within the calendar's coverage (wrapping forbidden). Because the
    total span of a gap sequence — ``sum(gaps)`` — is invariant under
    permutation, the real placement's own start position always lies in that
    feasible set (the real placement already fit), so a feasible anchor always
    exists; no rejection-sampling loop is needed, and the freeze's "if
    impossible, keep the real anchor" fallback is applied only as a defensive
    no-op guard against that invariant somehow not holding. Each event's own
    stamp lag (``signal_known_ts - signal_ts``) is preserved exactly as a
    timedelta, identically to :func:`grain_cadence_null`. Every placed
    ``signal_ts`` lands on an actual trading session by construction, since it
    is drawn FROM the calendar itself.

    The EARLIER repair (freeze review finding M11, prior pass) placed each fire
    independently and uniformly — count-matched, but it destroys the multiset
    of inter-fire gaps entirely, which is a *different and weaker* null than
    freeze §4.3 item 1's literal "count/dwell-matched" requirement.
    """
    if events is None or events.empty:
        return events.copy() if events is not None else events

    out = events.copy()
    out = _ensure_signal_ts_and_known_ts(out)
    stamp_lag = out["signal_known_ts"] - out["signal_ts"]
    rng = np.random.default_rng(seed)

    for (fam, sym), idx in out.groupby(["family_key", "symbol"]).groups.items():
        calendar = _symbol_calendar(bars_by_symbol, str(sym))
        n = len(calendar)
        sub = out.loc[idx]
        if n == 0:
            continue

        sub_sorted = sub.sort_values("signal_ts")
        sorted_index = sub_sorted.index
        positions = calendar.searchsorted(sub_sorted["signal_ts"].to_numpy(), side="left")
        positions = np.clip(positions, 0, n - 1).astype(np.int64)

        gaps = np.diff(positions)
        permuted_gaps = rng.permutation(gaps) if len(gaps) else gaps
        span = int(positions[-1] - positions[0]) if len(positions) else 0

        max_start = n - 1 - span
        if max_start < 0:
            # Defensive fallback only (freeze: "if impossible, keep the real
            # anchor and note it") — span is invariant under permutation and the
            # real placement already fit, so this should be unreachable.
            start = int(positions[0])
        else:
            start = int(rng.integers(0, max_start + 1))

        new_positions = start + np.concatenate([[0], np.cumsum(permuted_gaps)]).astype(np.int64)
        new_positions = np.clip(new_positions, 0, n - 1)
        new_signal_ts = calendar[new_positions]

        out.loc[sorted_index, "signal_ts"] = new_signal_ts
        out.loc[sorted_index, "signal_known_ts"] = (
            pd.DatetimeIndex(new_signal_ts) + stamp_lag.loc[sorted_index].to_numpy()
        )

    return out


def _weekday_preserving_offset(
    calendar: pd.DatetimeIndex,
    positions: np.ndarray,
    anchor_pos: int,
    period: int,
    lo: int,
    hi: int,
    m0: int,
    retry_budget: int,
) -> tuple[int, bool]:
    """Search ``[lo, hi]`` (multiples of ``period``, i.e. candidate offsets
    ``K = m * period``) for a ``K`` that lands EVERY fire in ``positions`` on
    its own original weekday, given the seeded draw ``m0`` as the search
    center (nearest-first, deterministic tie-break toward the smaller ``m``).

    Returns ``(k, phase_preserved)``. ``phase_preserved`` is ``True`` only when
    a ``K`` was found (within ``retry_budget`` candidates) that preserves
    EVERY fire's weekday — not merely the anchor's. If the retry budget is
    exhausted without such a ``K``, or no candidate even preserves the
    anchor's weekday, the largest anchor-admissible multiple is returned (or,
    in the pathological case where no multiple in range preserves even the
    anchor's weekday, the original unconstrained draw) with
    ``phase_preserved=False`` — the fallback is disclosed, never silently
    claimed as phase-preserving.
    """
    n = len(calendar)
    ms = np.arange(lo, hi + 1, dtype=np.int64)
    ks = ms * period
    anchor_new_positions = (anchor_pos + ks) % n
    anchor_weekday = calendar[anchor_pos].weekday()
    anchor_match = np.array(
        [calendar[int(p)].weekday() == anchor_weekday for p in anchor_new_positions]
    )
    admissible_ms = ms[anchor_match]

    if len(admissible_ms) == 0:
        # Pathological: no offset in the declared range preserves even the
        # anchor's weekday. Defensive last resort -- keep the original
        # unconstrained draw; never claim phase preservation.
        return int(m0) * period, False

    # Nearest-to-m0 first (deterministic: derives only from the seeded m0 and
    # the calendar, no further RNG draws needed), stable tie-break.
    order = admissible_ms[np.argsort(np.abs(admissible_ms - m0), kind="stable")]
    budget = min(retry_budget, len(order))
    for m in order[:budget]:
        k = int(m) * period
        new_positions = (positions + k) % n
        all_match = all(
            calendar[int(p2)].weekday() == calendar[int(p1)].weekday()
            for p1, p2 in zip(positions, new_positions)
        )
        if all_match:
            return k, True

    # Bounded retries exhausted: no K in range makes every fire agree on its
    # own weekday. Fall back to the largest anchor-admissible multiple and
    # disclose the failure via phase_preserved=False rather than shipping an
    # unverified phase claim.
    return int(admissible_ms.max()) * period, False


def grain_cadence_null(
    events: pd.DataFrame, bars_by_symbol: Mapping[str, pd.DataFrame], seed: int,
) -> pd.DataFrame:
    """Trading-session-space circular shift, phase- and stamp-lag-preserving
    (freeze review finding M4; M4-regression fix; weekday-phase MAJOR fix,
    delta-review third pass).

    Per ``(family_key, symbol)`` group, an offset ``K`` — constrained to a
    MULTIPLE of the group's own DOMINANT grain period in trading sessions
    (mode over the group's own ``grain`` values; :func:`_grain_period_sessions`;
    ``1D``->1, ``3D``->3, ``W``->5, ``2W``->10) and drawn from the declared
    ``[63, 252]``-session range — is searched (:func:`_weekday_preserving_offset`)
    so that EVERY fire in the group lands on its own ORIGINAL weekday, not
    merely a multiple-of-period session count. A fixed number of trading
    SESSIONS is not a fixed number of calendar WEEKS on a real (holiday-
    bearing) calendar, so period-multiple magnitude alone does not guarantee
    weekday phase; the search draws a seeded candidate ``K``, verifies every
    fire's weekday against it, and retries (bounded, deterministic) over the
    nearest admissible multiples before falling back to the largest
    anchor-admissible multiple and marking the group's rows
    ``phase_preserved: false`` if no fully-agreeing ``K`` is found — the
    guarantee is DISCLOSED per group, never silently claimed. Every fire's
    ``signal_ts`` in the group is then moved ``K`` sessions forward on that
    symbol's own trading calendar, wrapping within its coverage. KNOWN
    LIMITATION: this is a per-(family_key, symbol) grouping (the frozen
    shape), so a group that mixes multiple grains for the same symbol
    (observed in the real pilot cohort's ``sea_event_classes`` family) applies
    the DOMINANT grain's period to every fire in the group — a minority grain
    sharing that group does not get its own phase preserved.
    ``signal_known_ts`` is then reconstructed per event as
    ``new_signal_ts + (orig_known_ts - orig_signal_ts)`` — each event's own
    stamp lag is preserved EXACTLY as a timedelta, never collapsed to zero by
    setting both columns to the same shifted value (the M4-regression this fix
    closes). Every placed ``signal_ts`` lands on an actual trading session by
    construction (it is drawn FROM the calendar), so no null fire's
    ``signal_ts`` can ever fall on a non-session date; breaking correspondence
    to the specific episode anchors is the null's purpose.

    The output carries a ``phase_preserved`` column (nullable boolean): ``True``
    for every row in a group whose chosen ``K`` was verified to preserve every
    fire's weekday, ``False`` for a group that fell back to the
    largest-admissible-multiple guess, and ``<NA>`` for a group whose symbol
    had no trading calendar available (untouched, no shift applied at all).
    """
    if events is None or events.empty:
        return events.copy() if events is not None else events

    out = events.copy()
    out = _ensure_signal_ts_and_known_ts(out)
    stamp_lag = out["signal_known_ts"] - out["signal_ts"]
    rng = np.random.default_rng(seed)
    out["phase_preserved"] = pd.array([pd.NA] * len(out), dtype="boolean")

    for (fam, sym), idx in out.groupby(["family_key", "symbol"]).groups.items():
        calendar = _symbol_calendar(bars_by_symbol, str(sym))
        n = len(calendar)
        sub = out.loc[idx]
        if n == 0:
            continue

        # The GROUP's dominant grain (mode, not merely the first row -- a
        # deterministic and representative choice) decides the period. A
        # (family_key, symbol) group that mixes multiple grains (observed in
        # the real pilot cohort's `sea_event_classes` family) applies the
        # dominant grain's period to every fire in the group, per the frozen
        # per-(family_key, symbol) grouping -- a minority grain sharing that
        # group does not get its OWN phase preserved (documented limitation,
        # not silently redesigned into a finer (family_key, symbol, grain)
        # grouping, which would be a larger, separately-decided change).
        grain_val = (
            sub["grain"].mode().iloc[0]
            if "grain" in sub.columns and sub["grain"].notna().any()
            else None
        )
        period = max(1, min(_grain_period_sessions(grain_val), n))
        lo = -(-GRAIN_CADENCE_NULL_MIN_SESSIONS // period)  # ceil division
        hi = GRAIN_CADENCE_NULL_MAX_SESSIONS // period
        if hi < lo:
            hi = lo
        m0 = int(rng.integers(lo, hi + 1))

        positions = calendar.searchsorted(sub["signal_ts"].to_numpy(), side="left")
        positions = np.clip(positions, 0, n - 1).astype(np.int64)

        # The group's "anchor" fire (earliest signal_ts) is what the freeze
        # review's weekday-phase finding names -- the K search first lands
        # THIS fire on its own weekday, then verifies every other fire too.
        anchor_iloc = int(np.argmin(sub["signal_ts"].to_numpy()))
        anchor_pos = int(positions[anchor_iloc])

        k, phase_preserved = _weekday_preserving_offset(
            calendar, positions, anchor_pos, period, lo, hi, m0,
            GRAIN_CADENCE_PHASE_RETRY_BUDGET,
        )

        new_positions = (positions + k) % n
        new_signal_ts = calendar[new_positions]

        out.loc[sub.index, "signal_ts"] = new_signal_ts
        out.loc[sub.index, "signal_known_ts"] = (
            pd.DatetimeIndex(new_signal_ts) + stamp_lag.loc[sub.index].to_numpy()
        )
        out.loc[sub.index, "phase_preserved"] = phase_preserved

    return out


def equal_proximity_control(metrics: pd.DataFrame, tolerance_atr: float) -> tuple[pd.DataFrame, int]:
    """Pair cross-family fires that fired into the SAME episode AND SAME grain
    (freeze review finding M2/M3; M3-minor added grain to the group key) whose
    ``atr_dist`` (distance to anchor, ATR units) differ by no more than
    ``tolerance_atr``. Never pairs two fires from the same ``family_key`` (that
    would not be a cross-expert comparison), never emits a pair whose gap
    exceeds the declared tolerance, and never pairs fires from DIFFERENT
    episodes/symbols/grains — a "similarly-placed" comparison is only
    meaningful anchored to the same episode AND the same cadence (a
    daily-cadence fire and a weekly-cadence fire at a similar ATR distance are
    measured over different windows, so pairing them is not a genuine
    similarly-placed comparison either).

    A row with no ``grain`` value (``NaN``/missing) is treated as its own group
    (pandas ``groupby`` with ``dropna=False``) rather than silently coalesced
    with any other grain, so an ungraded/unknown grain never masquerades as a
    match. Each output pair row carries a ``grain`` column recording the
    (single, shared) grain that scoped the pair — a reader of the pair output
    alone can see which cadence bucket produced it, without rejoining
    ``metrics`` (NIT, delta-review third pass).

    Per-episode-and-grain fire counts are small (a handful at most), so no scan
    cap is needed once pairing is grouped by (episode, grain) — every candidate
    pair within a group is examined. Returns ``(pairs, truncated_count)``;
    ``truncated_count`` is always ``0`` under this grouped design (kept as an
    explicit return value, per the freeze review, rather than silently omitted)
    — a future defensive per-group cap would report a nonzero value here
    instead of dropping pairs silently.
    """
    empty = pd.DataFrame({c: pd.Series(dtype="object") for c in PROXIMITY_PAIR_COLUMNS})
    if (
        metrics is None or metrics.empty
        or "atr_dist" not in metrics.columns or "episode_id" not in metrics.columns
        or "grain" not in metrics.columns
    ):
        return empty, 0
    if tolerance_atr < 0:
        raise ValueError("tolerance_atr must be >= 0")

    rows: list[dict[str, Any]] = []
    truncated = 0
    for (episode_id, grain), group in metrics.dropna(subset=["atr_dist"]).groupby(
        ["episode_id", "grain"], dropna=False
    ):
        g = group.sort_values("atr_dist").reset_index(drop=True)
        n = len(g)
        atr = g["atr_dist"].to_numpy(dtype=float)
        fam = g["family_key"].to_numpy()
        eid = g["event_id"].to_numpy()
        for i in range(n):
            ai = atr[i]
            for j in range(i + 1, n):
                gap = atr[j] - ai
                if gap > tolerance_atr:
                    break  # sorted ascending: no further j can be within tolerance
                if fam[j] == fam[i]:
                    # same-family pairs are excluded from OUTPUT but never consume
                    # any scan budget (there is none to consume in this grouped,
                    # uncapped design) and never displace a legitimate pair.
                    continue
                rows.append({
                    "left_event_id": eid[i],
                    "right_event_id": eid[j],
                    "left_family_key": fam[i],
                    "right_family_key": fam[j],
                    "left_atr_dist": float(ai),
                    "right_atr_dist": float(atr[j]),
                    "atr_dist_gap": float(abs(gap)),
                    "episode_id": episode_id,
                    "grain": grain,
                })
    if not rows:
        return empty, truncated
    return pd.DataFrame(rows)[list(PROXIMITY_PAIR_COLUMNS)], truncated
