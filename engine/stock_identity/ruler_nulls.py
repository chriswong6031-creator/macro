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
2. **Grain/cadence null** (:func:`grain_cadence_null`, Ruling 3 of Sol's PR-3 seal
   law, SI-W3A-RULER-V1) — a deterministic, seeded, trading-session-space shift
   in TWO stages per ``(family_key, symbol)`` group: (a) one shared BASE shift
   ``K`` — a multiple of the group's own grain period, drawn from the declared
   ``[63, 252]``-session range, identical to every fire in the group (unchanged
   from the prior design); then (b) EACH fire is independently snapped from its
   own post-base-shift position to the NEAREST actual trading session carrying
   that fire's own ORIGINAL weekday, bounded to an absolute snap of at most
   :data:`GRAIN_CADENCE_SNAP_BOUND_SESSIONS` (4) trading sessions, deterministic
   tie-break toward the EARLIER candidate session when two land at the same
   absolute distance. This is an EXPLICIT, DECLARED design change (Ruling 3):
   the null is now exact-cadence-PHASE (every non-unestimable row lands on its
   own original weekday, exactly) with a declared BOUNDED GAP PERTURBATION —
   it is explicitly NOT dwell-matched (per-fire independent snapping can move
   different fires in a group by different amounts, so the inter-fire SESSION
   GAP multiset is no longer preserved exactly; only :func:`random_fire_null`
   (null #1) carries the exact count/dwell law). The prior design (a single
   per-group search for a ``K`` that made EVERY fire agree on weekday
   simultaneously, falling back to an unverified guess when none existed) is
   superseded: on a real pilot-scale cohort, weekly-grain groups routinely span
   MULTIPLE YEARS, and no ``K`` within the frozen ``[63, 252]``-session range
   can achieve full-group weekday agreement for them (a structural property of
   the frozen session-range/shared-K design, verified by brute force,
   documented in ``W3_RULER_REGISTRATION.md`` §6.2/§6.10) — the per-fire snap
   makes phase preservation achievable per fire regardless of group span, at
   the declared cost of a small (≤4-session), disclosed, per-fire gap
   perturbation. Event COUNT, event IDENTITY (``event_id``), each event's own
   stamp lag (``signal_known_ts - signal_ts``), and the group's CHRONOLOGICAL
   fire order are all still preserved exactly. If the snap search finds no
   lawful same-weekday target within the bound for any fire in the group, or
   the independently-snapped positions would collide or invert the group's
   chronological order, the WHOLE group is marked cadence-null
   ``cadence_null_state = "unestimable"`` (typed column) and left UNTOUCHED
   (original ``signal_ts``/``signal_known_ts`` preserved) rather than forcing a
   broken or silently-incoherent shift. Per-row ``phase_preserved`` and
   ``snap_sessions`` are published, plus group/summary gap-distortion
   statistics (the distribution of ``|snap_sessions|``, per-group max, and the
   unestimable-group count) via :func:`grain_cadence_null_summary`.
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
    "GRAIN_CADENCE_SNAP_BOUND_SESSIONS",
    "GRAIN_CADENCE_NULL_MIN_SESSIONS",
    "GRAIN_CADENCE_NULL_MAX_SESSIONS",
    "random_fire_null",
    "grain_cadence_null",
    "grain_cadence_null_summary",
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

#: Ruling 3 (SI-W3A-RULER-V1 PR-3 seal law) — the absolute bound, in trading
#: sessions, on the per-fire snap :func:`grain_cadence_null` may apply AFTER
#: the group's shared base shift ``K`` to land a fire on its own original
#: weekday. Declared and frozen; never widened at runtime to rescue a group
#: that would otherwise go ``cadence_null_state = "unestimable"``.
GRAIN_CADENCE_SNAP_BOUND_SESSIONS = 4


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


def _snap_to_own_weekday(
    calendar: pd.DatetimeIndex, shifted_pos: int, target_weekday: int, bound: int,
) -> tuple[int | None, int | None]:
    """Ruling 3: search sessions within ``[shifted_pos - bound, shifted_pos +
    bound]`` (clipped to the calendar) for the one carrying ``target_weekday``
    closest to ``shifted_pos``. Deterministic tie-break: at equal absolute
    distance the EARLIER (smaller-position) session wins, so offsets are tried
    smaller-magnitude-first and, within a magnitude, earlier-before-later.

    Returns ``(new_pos, snap_sessions)`` — ``snap_sessions`` is the SIGNED
    delta ``new_pos - shifted_pos`` (published per-row, so the pre-snap base
    position is always reconstructible as ``new_pos - snap_sessions``). Returns
    ``(None, None)`` when no session within the bound carries the target
    weekday — "no lawful target exists for some fire" (Ruling 3), which the
    caller turns into a whole-group ``cadence_null_state = "unestimable"``.
    """
    n = len(calendar)
    if n == 0:
        return None, None
    shifted_pos = min(max(int(shifted_pos), 0), n - 1)
    for offset in range(0, bound + 1):
        candidates = (shifted_pos,) if offset == 0 else (shifted_pos - offset, shifted_pos + offset)
        for cand in candidates:
            if 0 <= cand < n and calendar[cand].weekday() == target_weekday:
                return cand, cand - shifted_pos
    return None, None


def grain_cadence_null(
    events: pd.DataFrame, bars_by_symbol: Mapping[str, pd.DataFrame], seed: int,
) -> pd.DataFrame:
    """Ruling 3 (SI-W3A-RULER-V1 PR-3 seal law): trading-session base shift
    PLUS a bounded per-fire weekday snap, stamp-lag- and order-preserving.

    Per ``(family_key, symbol)`` group: (1) draw ONE shared base shift ``K`` —
    a multiple of the group's own DOMINANT grain period in trading sessions
    (mode over the group's own ``grain`` values; :func:`_grain_period_sessions`;
    ``1D``->1, ``3D``->3, ``W``->5, ``2W``->10), drawn from the declared
    ``[63, 252]``-session range, identical to the prior design's draw — and
    apply it circularly to every fire's position; (2) INDEPENDENTLY snap each
    fire from its own post-``K`` position to the nearest actual trading session
    carrying that fire's own ORIGINAL weekday
    (:func:`_snap_to_own_weekday`), bounded to
    :data:`GRAIN_CADENCE_SNAP_BOUND_SESSIONS` (4) sessions each way, earlier
    session wins ties. This is a DECLARED design change from the prior
    single-shared-K weekday search (Ruling 3): real pilot-scale weekly-grain
    groups span multiple years, so no single ``K`` in ``[63, 252]`` sessions
    can weekday-align every fire in such a group simultaneously (a structural
    property of the frozen session-range/shared-K design, verified by brute
    force -- ``W3_RULER_REGISTRATION.md`` §6.2/§6.10); per-fire snapping makes
    exact weekday preservation achievable per fire regardless of group span,
    at the cost of a small, DECLARED, per-fire gap perturbation -- the null is
    exact-cadence-PHASE but explicitly NOT dwell-matched (only
    :func:`random_fire_null`, null #1, carries the exact count/dwell law).

    No fire is ever dropped: event COUNT and event IDENTITY (``event_id``) are
    always preserved. Each event's own stamp lag
    (``signal_known_ts - signal_ts``) is preserved EXACTLY as a timedelta.
    Within a successfully-shifted group the fires' CHRONOLOGICAL ORDER (by
    original ``signal_ts``) is verified preserved in the new positions -- a
    STRICT increase is required, so two originally-distinct fires snapping to
    the SAME session (a collision) or snapping out of their original relative
    order (an inversion) both refuse the group's shift.

    If ANY fire in the group has no lawful same-weekday target within the
    snap bound, OR the group's snapped positions collide or invert
    chronological order, the WHOLE group is marked
    ``cadence_null_state = "unestimable"`` and left COMPLETELY UNTOUCHED
    (original ``signal_ts``/``signal_known_ts`` preserved) rather than forcing
    an incoherent or partially-broken shift.

    Three published columns:

    * ``cadence_null_state`` (string) -- ``"applied"`` (the group's shift+snap
      succeeded and was applied), ``"unestimable"`` (collision/inversion/no
      lawful target -- group left untouched), or ``"no_calendar"`` (the
      symbol had no trading calendar available at all -- group left untouched,
      identical to the prior design's convention).
    * ``phase_preserved`` (nullable boolean) -- ``True`` for every row of an
      ``"applied"`` group (weekday preservation is verified by construction
      for every such row), ``<NA>`` otherwise.
    * ``snap_sessions`` (nullable Int64) -- the signed per-fire snap distance
      (stage 2 only, sessions) for every row of an ``"applied"`` group,
      ``<NA>`` otherwise. :func:`grain_cadence_null_summary` derives the
      group/summary gap-distortion statistics from this column.
    """
    if events is None or events.empty:
        return events.copy() if events is not None else events

    out = events.copy()
    out = _ensure_signal_ts_and_known_ts(out)
    stamp_lag = out["signal_known_ts"] - out["signal_ts"]
    rng = np.random.default_rng(seed)
    out["phase_preserved"] = pd.array([pd.NA] * len(out), dtype="boolean")
    out["snap_sessions"] = pd.array([pd.NA] * len(out), dtype="Int64")
    out["cadence_null_state"] = pd.array(["no_calendar"] * len(out), dtype="object")

    for (fam, sym), idx in out.groupby(["family_key", "symbol"]).groups.items():
        calendar = _symbol_calendar(bars_by_symbol, str(sym))
        n = len(calendar)
        sub = out.loc[idx]
        if n == 0:
            continue  # cadence_null_state stays "no_calendar" for this group

        # The GROUP's dominant grain (mode, not merely the first row -- a
        # deterministic and representative choice) decides the base-shift
        # period. A (family_key, symbol) group that mixes multiple grains
        # (observed in the real pilot cohort's `sea_event_classes` family)
        # applies the dominant grain's period to every fire in the group, per
        # the frozen per-(family_key, symbol) grouping (documented limitation,
        # unchanged from the prior design).
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
        k = m0 * period

        positions = calendar.searchsorted(sub["signal_ts"].to_numpy(), side="left")
        positions = np.clip(positions, 0, n - 1).astype(np.int64)
        original_weekdays = [calendar[int(p)].weekday() for p in positions]
        shifted_positions = (positions + k) % n

        new_positions = np.empty(len(positions), dtype=np.int64)
        snap_sessions = np.empty(len(positions), dtype=np.int64)
        lawful = True
        for i, (sp, wd) in enumerate(zip(shifted_positions, original_weekdays)):
            np_pos, snap = _snap_to_own_weekday(
                calendar, int(sp), wd, GRAIN_CADENCE_SNAP_BOUND_SESSIONS,
            )
            if np_pos is None:
                lawful = False
                break
            new_positions[i] = np_pos
            snap_sessions[i] = snap

        if lawful:
            # Chronological-order + collision check: taken in their ORIGINAL
            # signal_ts order, the group's new positions must never INVERT
            # (a later fire snapping before an earlier one) and must never
            # introduce a NEW collision (two originally-DISTINCT positions
            # snapping to the same session). A pair that was ALREADY tied in
            # the original data (two fires sharing one signal_ts) is exempt
            # from the no-new-collision check -- they were indistinguishable
            # in time before this null ran too, so a tied snap is not a
            # distortion this check exists to catch.
            order_idx = np.argsort(positions, kind="stable")
            ordered_orig = positions[order_idx]
            ordered_new = new_positions[order_idx]
            if len(ordered_new) >= 2:
                orig_diff = np.diff(ordered_orig)
                new_diff = np.diff(ordered_new)
                inversion = np.any(new_diff < 0)
                new_collision = np.any((orig_diff > 0) & (new_diff == 0))
                if inversion or new_collision:
                    lawful = False

        if not lawful:
            out.loc[sub.index, "cadence_null_state"] = "unestimable"
            # phase_preserved/snap_sessions stay <NA>; signal_ts/signal_known_ts
            # stay at their original (untouched) values -- never force a
            # broken or partially-incoherent shift.
            continue

        new_signal_ts = calendar[new_positions]
        out.loc[sub.index, "signal_ts"] = new_signal_ts
        out.loc[sub.index, "signal_known_ts"] = (
            pd.DatetimeIndex(new_signal_ts) + stamp_lag.loc[sub.index].to_numpy()
        )
        out.loc[sub.index, "phase_preserved"] = True
        out.loc[sub.index, "snap_sessions"] = snap_sessions
        out.loc[sub.index, "cadence_null_state"] = "applied"

    return out


def grain_cadence_null_summary(out: pd.DataFrame) -> dict[str, Any]:
    """Ruling 3: group/summary gap-distortion statistics for a
    :func:`grain_cadence_null` output — the distribution of ``|snap_sessions|``
    (the per-fire distance from the shared base shift to its own
    weekday-matched landing session) plus the count of groups/rows marked
    ``cadence_null_state == "unestimable"``. Surfaced in the W3A build
    summary alongside the null's row-level output (Ruling 3's "group/summary
    gap-distortion statistics ... in the null output and build summary")."""
    empty = {
        "n_rows": 0, "n_rows_applied": 0, "n_rows_unestimable": 0,
        "n_rows_no_calendar": 0, "n_groups_unestimable": 0,
        "snap_sessions_abs_mean": None, "snap_sessions_abs_median": None,
        "snap_sessions_abs_max": None, "snap_sessions_abs_p95": None,
        "per_group_max_abs_snap_sessions": {},
    }
    if out is None or out.empty or "cadence_null_state" not in out.columns:
        return empty

    state = out["cadence_null_state"]
    n_rows_applied = int((state == "applied").sum())
    n_rows_unestimable = int((state == "unestimable").sum())
    n_rows_no_calendar = int((state == "no_calendar").sum())

    n_groups_unestimable = 0
    per_group_max: dict[str, float] = {}
    if {"family_key", "symbol"} <= set(out.columns):
        for (fam, sym), sub in out.groupby(["family_key", "symbol"]):
            if bool((sub["cadence_null_state"] == "unestimable").any()):
                n_groups_unestimable += 1
            applied = sub.loc[sub["cadence_null_state"] == "applied", "snap_sessions"]
            if not applied.empty:
                abs_vals = pd.to_numeric(applied, errors="coerce").dropna().abs()
                if len(abs_vals):
                    per_group_max[f"{fam}::{sym}"] = float(abs_vals.max())

    snaps = pd.to_numeric(out.loc[state == "applied", "snap_sessions"], errors="coerce").dropna()
    abs_snaps = snaps.abs()
    return {
        "n_rows": int(len(out)),
        "n_rows_applied": n_rows_applied,
        "n_rows_unestimable": n_rows_unestimable,
        "n_rows_no_calendar": n_rows_no_calendar,
        "n_groups_unestimable": n_groups_unestimable,
        "snap_sessions_abs_mean": float(abs_snaps.mean()) if len(abs_snaps) else None,
        "snap_sessions_abs_median": float(abs_snaps.median()) if len(abs_snaps) else None,
        "snap_sessions_abs_max": float(abs_snaps.max()) if len(abs_snaps) else None,
        "snap_sessions_abs_p95": (
            float(np.percentile(abs_snaps.to_numpy(dtype=float), 95, method="linear"))
            if len(abs_snaps) else None
        ),
        "per_group_max_abs_snap_sessions": per_group_max,
    }


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
