"""engine/entry_radar/live_pack.py — the frozen evaluation substrate (W4, §7.1).

BOUNDARY (contract §2), stated before anything else
---------------------------------------------------
Nothing here is a detector.  Every firing decision in this module is delegated to
the UNMODIFIED W3 code path (``indicator_core`` → ``challengers`` → ``four_hour``);
this module freezes what those functions read and inverts their conditions into
price levels.  No spec block is defined here, no ``spec_hash`` is computed here,
and a drift between the published hashes and the registry REFUSES the build
rather than publishing a pack attributed to a detector that has moved.

WHY A PACK EXISTS AT ALL (contract §7.1, W4 design §1)
-------------------------------------------------------
§7.1's law is that **the intraday lane never re-derives a signal from a mutable
store**.  A mid-session store move (a corporate-action re-adjustment, a late
backfill, a wrong-session series) does not merely stale an oscillator — it
*fabricates crossings*, which is why §5's stale-pack row demands ``unavailable``
for the whole cycle rather than a best-effort read.  So the substrate is frozen
ONCE, off-RTH, per name:

  ``as_of_close``               the basis-audit anchor (§5 price-basis row)
  ``last_confirmed``            per-name, and may LAG ``as_of`` — such a name is
                                ``stale`` downstream through W3's own
                                :func:`challengers.freshness_state`, never
                                silently current
  ``atr14_prior_confirmed``     via :func:`indicator_core.atr14` on the frozen
                                frame — the house ATR, never a second one
  ``confirmed_k`` / ``confirmed_d``  canonical StochRSI on the frozen closes;
                                feeds the §10 re-arm ledger and C3's daily-leg
                                receipt
  ``c1_arm_price`` / ``c2a_cross_price``  the inverted thresholds

THE INVERSION IS A BISECTION AGAINST THE W3 ORACLE, NOT A FORMULA
------------------------------------------------------------------
There is no closed form for "the close at which %K crosses 20": %K is an SMA(3)
over a rolling-extreme transform of an RMA-seeded RSI.  Rather than derive a
second implementation — the exact defect ``indicator_core``'s docstring exists to
prevent — the boundary is found by BISECTING the same function the live lane will
run.  ``_oracle_kd`` mirrors :func:`challengers.build_observation_path`'s series
construction line for line (confirmed closes through ``as_of`` plus ONE appended
row indexed at the NEXT session — §7.1's measured append-not-replace law), so a
threshold and the reading it predicts cannot disagree by construction.

§7.1's two hardenings are implemented, not optional:

  (1) **degenerate cases are explicit** — a bracket over which no price reaches
      the condition emits ``no_threshold_exists`` with one of four named reasons
      (``flat_rsi_nan`` · ``always_true`` · ``never_true`` · ``non_monotone``),
      never an absent or unbounded level;
  (2) the **stale-pack gate** is the caller's (:func:`pack_is_fresh`); this module
      refuses to pretend a pack is current.

EXACTNESS AT THE BOUNDARY.  C1's arm is a STRICT ``K < 20`` and C2a's cross is a
STRICT ``K > D``, so "the price where it flips" is ambiguous unless the oracle's
verdict AT the returned level is recorded.  ``condition_at_boundary`` is that
verdict, and the evaluator's cross-check reads
``condition(p) == (p < price) or (p == price and condition_at_boundary)`` for a
``below`` threshold (mirrored for ``above``).

THE PROOF PACK IS A FALSIFICATION INSTRUMENT (W4 design §1, commission amendment)
---------------------------------------------------------------------------------
:func:`build_inversion_proof` probes every load-bearing frozen boundary from BOTH
sides and refuses to publish a pack whose thresholds disagree with the oracle.
It tunes nothing, optimises nothing, reads no forward outcome, ranks nothing and
never touches a spec hash — a failing case marks the pack ``proof_failed`` and
the RTH evaluator refuses the cycle.  The proof re-derives each verdict FROM the
oracle rather than from the stored threshold, which is what makes a corrupted
threshold detectable at all (a receipt written from the variable it checks cannot
fail).

WHAT THIS MODULE MAY WRITE
--------------------------
The pack and its pointer, under an INJECTED ``state_dir`` (production:
``/var/lib/macro-live/state/entry_radar``).  Never ``data/`` — no ``data/`` path
literal appears in this file, and the daily store arrives through the injected
``store_reader`` so the engine cannot reach it directly.  No network, no wall
clock: ``as_of``, ``built_at`` and ``now`` are always passed in.

W4/W5 FIREWALL.  No forward return, MFE/MAE, hit rate, grade or detector
comparison exists here.  Every field is knowable at ``as_of``.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import pandas as pd

from engine import session_anchor
from engine.entry_radar import challengers as ch
from engine.entry_radar import detectors as dt
from engine.entry_radar import indicator_core as ic
from engine.entry_radar.contracts import iso
from engine.entry_radar.entry_events import EntryEventError, sha16
from engine.entry_radar.four_hour import four_hour_turn
from engine.session_digest import session_window_et

SCHEMA_LIVE_PACK = "entry_radar.live_pack/v2"
SCHEMA_INVERSION_PROOF = "entry_radar.inversion_proof/v1"

#: The RETIRED v1 label, kept ONLY so :func:`load_pack` can tell a genuinely
#: pre-W4.1 manifest (no ``schema`` key at all) apart from a v2 one instead of
#: defaulting a missing field to the CURRENT schema — which would mislabel a
#: pack that was never carrying ``confirmed_lanes`` as if it were.
_SCHEMA_LIVE_PACK_V1 = "entry_radar.live_pack/v1"

#: The honest default for a ticker the confirmed-lane source never covered — no
#: slice directory configured, this ticker's slice absent, or a caller-supplied
#: row that failed to normalize.  Same reason word the RTH reader has always
#: published (W4.1, was previously unreachable because no writer ever populated
#: the field this reads).
_UNAVAILABLE_LANE_ROW: dict[str, Any] = {
    "availability": "unavailable", "reason": "slice_store_unconfigured"}

#: The six PUBLISHED detector identities (W4 design §0, W3 #5724).  Held as
#: literals so a spec block edited anywhere in the package REFUSES the pack build
#: instead of silently re-attributing every level in it to a different detector.
PUBLISHED_SPEC_HASHES: dict[str, str] = {
    "C1_1D_LIVE_WASHOUT@1": "f0bbd6cf3a6e2339",
    "C2_1D_TURN@1": "d8ba60a25cfa7400",
    "C3_1D_4H_RECOVERY@1": "d54dc1e55c4261c8",
    "C4_MTF_TURN@1": "dce21ac680233ee2",
    "C5_BOTTOM_WATCH@1": "13dec66345a0376c",
    "G0_GREY_DOT@1": "9be89a8acc8b905c",
}

#: The bisection bracket, as multiples of ``as_of_close``.  CHOSEN AND DOCUMENTED
#: rather than unbounded (§7.1 hardening 1): a next-session print below 1% or
#: above 3x the prior close is outside anything the U.S. tape produces without a
#: corporate action — and a corporate action is exactly the case the §5 basis
#: audit refuses before a threshold is ever consulted.  A condition unreachable
#: inside the bracket is ``no_threshold_exists``, never an extrapolated level.
BRACKET_LOW_MULTIPLE = 0.01
BRACKET_HIGH_MULTIPLE = 3.0

#: Bisection stops when the bracket is this narrow RELATIVE to ``as_of_close``.
BISECTION_REL_TOLERANCE = 1e-6

#: Hard iteration ceiling.  ~22 halvings reach the tolerance from the bracket
#: above; the cap exists so a pathological oracle cannot spin, not as a budget.
BISECTION_MAX_ITERATIONS = 200

#: Monotonicity is VERIFIED on a coarse grid before any bisection.  §7.1 asserts
#: K, D and K-D are monotone in the appended close; this module does not take
#: that on trust, because bisecting a non-monotone margin returns a confident
#: wrong level.
MONOTONICITY_GRID_POINTS = 24

#: Slack on the monotonicity check, relative to the margin's own scale — float
#: noise in a 19k-bar RMA chain is not a reversal.
MONOTONICITY_REL_SLACK = 1e-9

#: The four named degeneracies.  FROZEN: a fifth reason is a visible diff.
DEGENERATE_REASONS: tuple[str, ...] = (
    "flat_rsi_nan", "always_true", "never_true", "non_monotone")

#: §5 price-basis row.  The prophet-live interval contract audits the pack's
#: adjusted ``as_of_close`` against the feed's RAW ``prevClose`` at this tolerance
#: (``engine/prophet_live/live_states.py`` interval basis audit, shape-cited
#: only — Radar imports nothing from Prophet).  Past it the name goes dark; it is
#: never applied as a correction.
BASIS_TOLERANCE_PCT = 0.25

#: The proof's both-sides offset, relative to the boundary.  100x the bisection
#: tolerance, so a passing probe cannot be an artefact of the bracket width.
PROOF_EPSILON_REL = 1e-4

#: Packs kept on disk.  Three = today's, the prior session's (a restart after a
#: failed build still has a lawful predecessor to refuse against) and one spare.
PACK_RETENTION = 3

_PACK_DIRNAME = "pack"
_MANIFEST_NAME = "manifest.json"
_SUBSTRATE_NAME = "substrate.parquet"
#: A POINTER FILE, not a symlink.  ``os.replace`` onto a small JSON file is
#: atomic on every filesystem this lane runs on, survives an rsync/backup round
#: trip, and is readable by an operator with ``cat``; a dangling symlink after a
#: partial restore is silent.  The pointer carries ``pack_hash`` too, so a reader
#: can detect a pointer that outlived its directory.
_POINTER_NAME = "current.json"

_SUBSTRATE_COLUMNS: tuple[str, ...] = ("high", "low", "close")


class LivePackError(EntryEventError):
    """A malformed pack input or an illegal pack operation."""


class SpecHashDrift(LivePackError):
    """A registered detector hash no longer equals its published identity."""


# ---------------------------------------------------------------------------
# calendar helpers (arithmetic only — no price is read on any of these paths)
# ---------------------------------------------------------------------------

def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def next_reference_session(session: date | str, *, market: str = "US") -> date | None:
    """The reference session immediately AFTER ``session``, or None past the edge.

    The mirror of :func:`challengers.prior_reference_session`, read from the same
    ``engine.session_anchor.reference_sessions`` calendar every Radar bucket rides
    — so "the session this pack is for" is a calendar fact, not a property of
    whichever rows a store happened to hold.
    """
    reference = session_anchor.reference_sessions(market)
    stamp = pd.Timestamp(_as_date(session)).normalize()
    position = int(reference.searchsorted(stamp, side="right"))
    if position >= len(reference):
        return None
    return reference[position].date()


# ---------------------------------------------------------------------------
# the spec-hash gate
# ---------------------------------------------------------------------------

def registered_spec_hashes() -> dict[str, str]:
    """The registry's CURRENT hash for each published detector id."""
    return {did: dt.get_spec(did).spec_hash for did in sorted(PUBLISHED_SPEC_HASHES)}


def assert_published_spec_hashes() -> dict[str, str]:
    """Raise ``SpecHashDrift`` unless every registered hash IS its published one.

    Called at the top of :func:`build_pack`, before a single price is read.  A
    pack is a set of levels attributed to six named detectors; publishing one
    under a hash nobody agreed to is how a later result stops being attributable
    to the thing that produced it.
    """
    registered = registered_spec_hashes()
    drift = {did: (PUBLISHED_SPEC_HASHES[did], registered.get(did))
             for did in sorted(PUBLISHED_SPEC_HASHES)
             if registered.get(did) != PUBLISHED_SPEC_HASHES[did]}
    if drift:
        detail = ", ".join(f"{did}: published {want} != registry {got}"
                           for did, (want, got) in sorted(drift.items()))
        raise SpecHashDrift(
            f"detector spec_hash drift — REFUSING to build a pack ({detail}).  Every "
            f"level in a pack is attributed to a named detector identity; publishing "
            f"levels under a hash that moved silently re-attributes every result they "
            f"later produce (W4 design §0, contract §18 A5.0 correction protocol)")
    return registered


# ---------------------------------------------------------------------------
# the oracle — the SAME construction the live path will run
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class OracleFrame:
    """One name's frozen substrate, ready to be probed at a candidate price.

    Holds exactly what :func:`challengers.build_observation_path` holds at the top
    of its per-tape loop: the confirmed closes as a float array, their index, and
    the session the provisional bar would be APPENDED at.  Keeping the three
    together is what makes ``_oracle_kd`` a line-for-line mirror rather than a
    re-derivation.
    """

    ticker: str
    closes: np.ndarray
    index: pd.DatetimeIndex
    next_session_ts: pd.Timestamp

    def kd(self, price: float) -> tuple[float | None, float | None]:
        """``(K, D)`` at the appended provisional close ``price``, or ``(None, None)``."""
        series = pd.Series(
            np.append(self.closes, float(price)),
            index=self.index.append(pd.DatetimeIndex([self.next_session_ts])))
        k_series, d_series = ic.stoch_rsi_kd(series)
        return ic.last_finite(k_series), ic.last_finite(d_series)


def _c1_margin(frame: OracleFrame, price: float) -> float | None:
    """``OVERSOLD - K(price)``.  Positive ⇒ ``K < 20`` ⇒ C1 arms.  NON-INCREASING."""
    k, _d = frame.kd(price)
    return None if k is None else float(ic.OVERSOLD) - float(k)


def _c2a_margin(frame: OracleFrame, price: float) -> float | None:
    """``K(price) - D(price)``.  Positive ⇒ ``K > D``.  NON-DECREASING.

    This inverts only the CURRENT half of A5.3's ``c2a`` predicate; the
    ``K_prev <= D_prev`` half is a property of the live path and is evaluated by
    the unmodified :func:`challengers.run_c2`, never by a level.
    """
    k, d = frame.kd(price)
    if k is None or d is None:
        return None
    return float(k) - float(d)


# ---------------------------------------------------------------------------
# threshold solutions
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ThresholdSolution:
    """One inverted condition, as a first-class receipt (W4 design §1).

    ``price is None`` ⇔ ``no_threshold_exists`` — there is no third state, and no
    unbounded sentinel.  ``bracket_verdict`` carries the CONSTANT verdict for the
    two saturation degeneracies (``always_true``/``never_true``) so a live
    evaluator still has an unambiguous answer instead of a hole.
    """

    condition: str
    predicate: str
    direction: str
    price: float | None
    condition_at_boundary: bool | None
    no_threshold_exists: bool
    reason: str | None
    bracket_low: float | None
    bracket_high: float | None
    bracket_verdict: bool | None = None
    iterations: int = 0
    rel_tolerance: float = BISECTION_REL_TOLERANCE

    def __post_init__(self) -> None:
        if self.direction not in ("below", "above"):
            raise LivePackError(f"threshold direction {self.direction!r} must be "
                                f"'below' or 'above'")
        if self.no_threshold_exists:
            if self.price is not None:
                raise LivePackError(
                    f"{self.condition}: no_threshold_exists with a price {self.price!r} "
                    f"— the two states are exclusive")
            if self.reason not in DEGENERATE_REASONS:
                raise LivePackError(
                    f"{self.condition}: degenerate reason {self.reason!r} not in "
                    f"{list(DEGENERATE_REASONS)} — §7.1 requires an EXPLICIT named "
                    f"degeneracy, never an absent or unbounded level")
        elif self.price is None:
            raise LivePackError(
                f"{self.condition}: a solved threshold with no price is exactly the "
                f"'absent level' §7.1 hardening 1 forbids")

    def holds_at(self, price: float) -> bool | None:
        """The predicted verdict at ``price``, or None when no level was solved.

        The evaluator's cross-check reads this and compares it to the oracle's own
        boolean; disagreement is a ``pack_integrity`` refusal for that name.
        """
        if self.no_threshold_exists:
            return self.bracket_verdict
        assert self.price is not None
        if float(price) == float(self.price):
            return self.condition_at_boundary
        return (float(price) < float(self.price) if self.direction == "below"
                else float(price) > float(self.price))

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition": self.condition,
            "predicate": self.predicate,
            "direction": self.direction,
            "price": self.price,
            "condition_at_boundary": self.condition_at_boundary,
            "no_threshold_exists": self.no_threshold_exists,
            "reason": self.reason,
            "bracket_low": self.bracket_low,
            "bracket_high": self.bracket_high,
            "bracket_verdict": self.bracket_verdict,
            "iterations": self.iterations,
            "rel_tolerance": self.rel_tolerance,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> ThresholdSolution:
        return cls(**{k: raw.get(k) for k in (
            "condition", "predicate", "direction", "price", "condition_at_boundary",
            "no_threshold_exists", "reason", "bracket_low", "bracket_high",
            "bracket_verdict", "iterations", "rel_tolerance")})


def _degenerate(condition: str, predicate: str, direction: str, reason: str, *,
                low: float | None, high: float | None,
                verdict: bool | None = None) -> ThresholdSolution:
    return ThresholdSolution(
        condition=condition, predicate=predicate, direction=direction, price=None,
        condition_at_boundary=None, no_threshold_exists=True, reason=reason,
        bracket_low=low, bracket_high=high, bracket_verdict=verdict)


def solve_threshold(margin: Callable[[float], float | None], *, condition: str,
                    predicate: str, anchor: float | None, decreasing: bool,
                    low_multiple: float = BRACKET_LOW_MULTIPLE,
                    high_multiple: float = BRACKET_HIGH_MULTIPLE,
                    rel_tolerance: float = BISECTION_REL_TOLERANCE,
                    grid_points: int = MONOTONICITY_GRID_POINTS,
                    ) -> ThresholdSolution:
    """Bisect ``margin`` for its sign change, or name the degeneracy.

    ``margin(p) > 0`` IS the condition.  ``decreasing`` says which way the margin
    runs in price — C1's ``20 - K`` falls as the close rises (condition holds
    BELOW the level), C2a's ``K - D`` rises (condition holds ABOVE it).

    ORDER MATTERS: monotonicity is checked on a coarse grid FIRST.  Bisection on a
    non-monotone margin converges happily onto a confident wrong number, and a
    wrong level that looks solved is worse than an honest ``no_threshold_exists``.
    """
    direction = "below" if decreasing else "above"
    if anchor is None or not np.isfinite(anchor) or anchor <= 0:
        return _degenerate(condition, predicate, direction, "flat_rsi_nan",
                           low=None, high=None)
    low = float(anchor) * float(low_multiple)
    high = float(anchor) * float(high_multiple)
    if not (high > low):
        return _degenerate(condition, predicate, direction, "flat_rsi_nan",
                           low=low, high=high)

    grid = np.linspace(low, high, max(3, int(grid_points)))
    values: list[float] = []
    for price in grid:
        got = margin(float(price))
        if got is None or not np.isfinite(got):
            # The oscillator itself is unavailable over the bracket — a flat-RSI
            # NaN window, or a history still inside the indicator's own warm-up.
            # Not a level, and emphatically not a False.
            return _degenerate(condition, predicate, direction, "flat_rsi_nan",
                               low=low, high=high)
        values.append(float(got))

    scale = max(1.0, max(abs(v) for v in values))
    slack = scale * MONOTONICITY_REL_SLACK
    diffs = np.diff(np.asarray(values, dtype=float))
    monotone = bool((diffs <= slack).all()) if decreasing else bool((diffs >= -slack).all())
    if not monotone:
        return _degenerate(condition, predicate, direction, "non_monotone",
                           low=low, high=high)

    lo_true, hi_true = values[0] > 0.0, values[-1] > 0.0
    if lo_true and hi_true:
        return _degenerate(condition, predicate, direction, "always_true",
                           low=low, high=high, verdict=True)
    if not lo_true and not hi_true:
        return _degenerate(condition, predicate, direction, "never_true",
                           low=low, high=high, verdict=False)

    # Exactly one endpoint satisfies the condition; the monotone margin has one
    # sign change between them.  ``true_end`` is the endpoint the condition holds
    # at, ``false_end`` the other.
    true_end, false_end = (low, high) if lo_true else (high, low)
    tolerance = abs(float(anchor)) * float(rel_tolerance)
    iterations = 0
    while abs(false_end - true_end) > tolerance and iterations < BISECTION_MAX_ITERATIONS:
        mid = 0.5 * (true_end + false_end)
        got = margin(mid)
        if got is None or not np.isfinite(got):
            return _degenerate(condition, predicate, direction, "flat_rsi_nan",
                               low=low, high=high)
        if float(got) > 0.0:
            true_end = mid
        else:
            false_end = mid
        iterations += 1

    boundary = 0.5 * (true_end + false_end)
    got = margin(boundary)
    if got is None or not np.isfinite(got):
        return _degenerate(condition, predicate, direction, "flat_rsi_nan",
                           low=low, high=high)
    return ThresholdSolution(
        condition=condition, predicate=predicate, direction=direction,
        price=float(boundary), condition_at_boundary=bool(float(got) > 0.0),
        no_threshold_exists=False, reason=None, bracket_low=low, bracket_high=high,
        bracket_verdict=None, iterations=iterations, rel_tolerance=float(rel_tolerance))


# ---------------------------------------------------------------------------
# basis audit (§5 price-basis row) — the helper the evaluator calls per pass
# ---------------------------------------------------------------------------

def basis_audit(as_of_close: float | None, prev_close: float | None, *,
                tolerance_pct: float = BASIS_TOLERANCE_PCT) -> dict[str, Any]:
    """Adjusted pack close vs the feed's RAW prior close (§5 price-basis row).

    Returns the whole receipt — both closes, the gap and the tolerance — because
    a bare boolean cannot be audited later, and because a name refused for a
    basis gap must be able to show the numbers that refused it.

    ``mismatch`` is None when either close is missing: a comparison we could not
    make is not a comparison that passed.  Equality with the tolerance PASSES
    (§5 says "past tolerance"), which is the boundary the proof battery probes.
    """
    tol = float(tolerance_pct)
    try:
        anchor = float(as_of_close) if as_of_close is not None else None
        other = float(prev_close) if prev_close is not None else None
    except (TypeError, ValueError):
        anchor = other = None
    if anchor is None or other is None or not np.isfinite(anchor) \
            or not np.isfinite(other) or anchor <= 0:
        return {"as_of_close": as_of_close, "prev_close": prev_close,
                "gap_pct": None, "tolerance_pct": tol, "mismatch": None,
                "reason": "basis_unavailable"}
    gap = abs(anchor - other) / anchor * 100.0
    return {"as_of_close": anchor, "prev_close": other, "gap_pct": float(gap),
            "tolerance_pct": tol, "mismatch": bool(gap > tol), "reason": None}


# ---------------------------------------------------------------------------
# the pack
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PackName:
    """One probe-set name's frozen row.  Everything here is knowable at ``as_of``."""

    ticker: str
    as_of_close: float | None
    last_confirmed: str | None
    freshness: str
    atr14_prior_confirmed: float | None
    confirmed_k: float | None
    confirmed_d: float | None
    confirmed_bars: int
    substrate_fingerprint: str
    c1_arm_price: ThresholdSolution
    c2a_cross_price: ThresholdSolution

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "as_of_close": self.as_of_close,
            "last_confirmed": self.last_confirmed,
            "freshness": self.freshness,
            "atr14_prior_confirmed": self.atr14_prior_confirmed,
            "confirmed_k": self.confirmed_k,
            "confirmed_d": self.confirmed_d,
            "confirmed_bars": self.confirmed_bars,
            "substrate_fingerprint": self.substrate_fingerprint,
            "c1_arm_price": self.c1_arm_price.to_dict(),
            "c2a_cross_price": self.c2a_cross_price.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> PackName:
        return cls(
            ticker=str(raw["ticker"]),
            as_of_close=raw.get("as_of_close"),
            last_confirmed=raw.get("last_confirmed"),
            freshness=str(raw.get("freshness") or "unavailable"),
            atr14_prior_confirmed=raw.get("atr14_prior_confirmed"),
            confirmed_k=raw.get("confirmed_k"),
            confirmed_d=raw.get("confirmed_d"),
            confirmed_bars=int(raw.get("confirmed_bars") or 0),
            substrate_fingerprint=str(raw.get("substrate_fingerprint") or ""),
            c1_arm_price=ThresholdSolution.from_dict(raw["c1_arm_price"]),
            c2a_cross_price=ThresholdSolution.from_dict(raw["c2a_cross_price"]))


@dataclass(frozen=True, slots=True)
class LivePack:
    """The nightly frozen substrate for ONE session.

    ``substrate`` holds the frozen frames themselves; ``names`` holds the derived
    receipts.  ``pack_hash`` covers everything FIRING-RELEVANT and nothing else —
    see :func:`compute_pack_hash` for the exact, enumerated coverage.
    """

    schema: str
    as_of: str
    next_session: str
    built_at: str
    price_basis: str
    spec_hashes: dict[str, str]
    probe_set: dict[str, Any]
    names: tuple[PackName, ...]
    substrate: dict[str, pd.DataFrame] = field(default_factory=dict)
    substrate_missing: tuple[dict[str, Any], ...] = ()
    pack_hash: str = ""
    proof: dict[str, Any] | None = None
    #: (v2) per-ticker ``{g0: {...}, c5: {...}}`` confirmed-bar lane rows —
    #: see :func:`confirmed_lanes_snapshot`.  Always populated (never absent),
    #: honestly ``unavailable`` when no confirmed-lane source was supplied.
    confirmed_lanes: dict[str, Any] = field(default_factory=dict)

    def by_ticker(self) -> dict[str, PackName]:
        return {row.ticker: row for row in self.names}

    @property
    def proof_failed(self) -> bool:
        """True when a proof ran and FAILED.  An unrun proof is not a pass."""
        return bool(self.proof is not None and not self.proof.get("pass"))

    def manifest(self) -> dict[str, Any]:
        """The JSON-safe pack record.  ``substrate`` rides the parquet sidecar."""
        return {
            "schema": self.schema,
            "as_of": self.as_of,
            "next_session": self.next_session,
            "built_at": self.built_at,
            "price_basis": self.price_basis,
            "spec_hashes": dict(self.spec_hashes),
            "probe_set": _jsonable(self.probe_set),
            "names": [row.to_dict() for row in self.names],
            "substrate_missing": [dict(row) for row in self.substrate_missing],
            "pack_hash": self.pack_hash,
            "proof": _jsonable(self.proof) if self.proof is not None else None,
            "proof_failed": self.proof_failed,
            "confirmed_lanes": _jsonable(self.confirmed_lanes),
        }

    def with_proof(self, proof: Mapping[str, Any]) -> LivePack:
        """A copy carrying ``proof``.  ``pack_hash`` is UNCHANGED by construction.

        The proof is a statement ABOUT the pack; folding it into the pack's own
        identity would mean a re-verified pack was a different pack.
        """
        return LivePack(
            schema=self.schema, as_of=self.as_of, next_session=self.next_session,
            built_at=self.built_at, price_basis=self.price_basis,
            spec_hashes=dict(self.spec_hashes), probe_set=dict(self.probe_set),
            names=self.names, substrate=dict(self.substrate),
            substrate_missing=self.substrate_missing, pack_hash=self.pack_hash,
            proof=dict(proof), confirmed_lanes=dict(self.confirmed_lanes))


def _jsonable(value: Any) -> Any:
    """Recursively coerce to JSON-safe values, with non-finite floats as None."""
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (np.floating, float)):
        got = float(value)
        return None if not np.isfinite(got) else got
    if isinstance(value, (np.integer, int)) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def substrate_fingerprint(frame: pd.DataFrame) -> str:
    """sha16 over the frozen rows — the pin a later store move cannot survive.

    Rows are ``[iso_session, high, low, close]`` with non-finite values as None,
    so a NaN high (a blank-OHLC name) fingerprints stably instead of hashing a
    value that compares unequal to itself.
    """
    rows: list[list[Any]] = []
    index = pd.DatetimeIndex(frame.index)
    for position in range(len(frame)):
        row: list[Any] = [index[position].date().isoformat()]
        for column in _SUBSTRATE_COLUMNS:
            try:
                value = float(frame[column].iloc[position])
            except (TypeError, ValueError):
                value = float("nan")
            row.append(None if not np.isfinite(value) else value)
        rows.append(row)
    return sha16(rows)


def _normalize_confirmed_lane_row(raw: Any) -> dict[str, Any]:
    """One ticker's ``{g0, c5}`` confirmed-lane row, honestly defaulted.

    A row that is not a mapping, or names an unrecognised ``availability``
    value, becomes the same ``slice_store_unconfigured`` shape the RTH reader
    has always published — the null law applied AT THE PACK BOUNDARY, so a
    malformed nightly-builder input can never reach a live reader as a
    plausible-looking "available" row.
    """
    if not isinstance(raw, Mapping):
        return {"g0": dict(_UNAVAILABLE_LANE_ROW), "c5": dict(_UNAVAILABLE_LANE_ROW)}
    out: dict[str, Any] = {}
    for lane in ("g0", "c5"):
        row = raw.get(lane)
        if isinstance(row, Mapping) and row.get("availability") in ("available",
                                                                     "unavailable"):
            out[lane] = _jsonable(dict(row))
        else:
            out[lane] = dict(_UNAVAILABLE_LANE_ROW)
    return out


def confirmed_lanes_snapshot(confirmed_lanes: Mapping[str, Any] | None,
                             tickers: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Normalize the caller-supplied confirmed-lane map to EVERY probe ticker.

    ``confirmed_lanes`` is the nightly builder's own per-ticker G0/C5 read of the
    Terminal slice store (:func:`scripts.entry_radar_live_pack.slice_lanes`,
    reshaped by that script's own adapter) — this module names no slice path and
    performs no IO to produce it, exactly as ``store_reader`` keeps daily-store
    IO out of this module.  ``None`` (no confirmed-lane source given at all) or a
    ticker missing from the map both fall to the honest unavailable default —
    never a silently absent ticker, which is what made the RTH reader's own
    fallback unreachable before W4.1 (no writer ever populated
    ``probe_set["nightly_lanes"]``).
    """
    source = confirmed_lanes if isinstance(confirmed_lanes, Mapping) else {}
    return {str(t): _normalize_confirmed_lane_row(source.get(str(t)))
            for t in tickers}


def compute_pack_hash(*, schema: str, as_of: str, next_session: str, price_basis: str,
                      spec_hashes: Mapping[str, str], probe_tickers: Sequence[str],
                      names: Sequence[PackName],
                      confirmed_lanes: Mapping[str, Any] | None = None) -> str:
    """sha256/16 over the pack's FIRING-RELEVANT content.  Coverage, enumerated:

      * ``schema``, ``as_of``, ``next_session``, ``price_basis`` — the session gate
        and the basis every level is quoted on;
      * the six ``spec_hashes`` — the identities the levels are attributed to;
      * the probe-set TICKER LIST (sorted) — which names the cycle covers;
      * per name: the ``substrate_fingerprint`` (the frozen bytes), the derived
        confirmed values a detector reads (``as_of_close``, ATR, K, D, bars),
        ``last_confirmed``/``freshness`` (a stale name must not hash equal to a
        current one), and BOTH threshold receipts in full;
      * (v2) ``confirmed_lanes`` — the per-ticker G0/C5 confirmed-bar
        availability rows.  These are firing-relevant to the confirmed-bar
        lanes exactly as the six inverted thresholds are to C1/C2a: a pack
        whose slice read moved must not hash equal to one whose did not.

    DELIBERATELY EXCLUDED: ``built_at`` (rebuilding the same session's pack a
    minute later is the same pack) and ``proof`` (a statement about the pack, not
    part of it).  Everything a name could FIRE on is inside; nothing that merely
    records when the build ran is.
    """
    lanes = confirmed_lanes_snapshot(confirmed_lanes, probe_tickers)
    payload = {
        "schema": schema,
        "as_of": as_of,
        "next_session": next_session,
        "price_basis": price_basis,
        "spec_hashes": {k: spec_hashes[k] for k in sorted(spec_hashes)},
        "probe_tickers": sorted(str(t) for t in probe_tickers),
        "names": [_jsonable(row.to_dict()) for row in
                  sorted(names, key=lambda r: r.ticker)],
        "confirmed_lanes": {t: lanes[t] for t in sorted(lanes)},
    }
    return sha16(payload)


def probe_set_snapshot(probe_set: Any) -> dict[str, Any]:
    """Tickers + an admission-provenance SUMMARY, embedded in the pack.

    Accepts a :class:`universe.ProbeSet`, its serialised form, or a bare sequence
    of tickers (what a test hands in).  The summary is counts by admission layer
    and reason code — never a collapsed badge and never a rank: §16 A1's
    no-flattening law governs the probe set itself, and the pack embeds a
    SUMMARY of it precisely so nobody mistakes the pack for the probe set.
    """
    records: list[Mapping[str, Any]] = []
    tickers: list[str] = []
    market_session: str | None = None
    source = "ticker_sequence"

    raw: Any = probe_set
    if hasattr(probe_set, "to_dict") and hasattr(probe_set, "records"):
        raw = probe_set.to_dict()
    if isinstance(raw, Mapping):
        source = "probe_set"
        market_session = raw.get("market_session")
        for row in raw.get("records") or ():
            if isinstance(row, Mapping):
                records.append(row)
                tickers.append(str(row.get("ticker") or ""))
        if not records:
            tickers = [str(t) for t in (raw.get("tickers") or ())]
    else:
        tickers = [str(t) for t in (raw or ())]

    layers: dict[str, int] = {}
    reasons: dict[str, int] = {}
    for row in records:
        for layer in row.get("admission_layers") or ():
            layers[str(layer)] = layers.get(str(layer), 0) + 1
        for reason in row.get("admission_reasons") or ():
            code = str((reason or {}).get("reason_code") or "unrecorded") \
                if isinstance(reason, Mapping) else "unrecorded"
            reasons[code] = reasons.get(code, 0) + 1

    tickers = sorted({t for t in tickers if t})
    return {
        "source": source,
        "market_session": market_session,
        "count": len(tickers),
        "tickers": tickers,
        "admission": {"layers": dict(sorted(layers.items())),
                      "reason_codes": dict(sorted(reasons.items()))},
    }


def _frozen_frame(frame: pd.DataFrame, *, ticker: str, next_session: date,
                  price_basis: str, vintage: str) -> pd.DataFrame:
    """Validate through ``DailyHistory`` and cut to rows at/before ``as_of``.

    The cut is ``confirmed_through(next_session)`` — rows STRICTLY BEFORE the
    session the pack is for — so the pack's freeze and W3's own knowability law
    are literally the same line of code, not two implementations that agree
    today.  ``DailyHistory`` also refuses a duplicated or unsorted index, which is
    a doubled bar inside every rolling window if it slips through.
    """
    missing = [c for c in _SUBSTRATE_COLUMNS if c not in frame.columns]
    if missing:
        raise LivePackError(f"{ticker}: store frame is missing column(s) {missing}")
    kept = frame.loc[:, list(_SUBSTRATE_COLUMNS)].astype(float)
    history = ch.DailyHistory(frame=kept, price_basis=price_basis, vintage=vintage)
    return history.confirmed_through(next_session)


def build_pack(*, probe_set: Any, store_reader: Callable[[str], pd.DataFrame | None],
               as_of: date | str, built_at: datetime | str,
               price_basis: str = ch.BASIS_ADJUSTED, market: str = "US",
               vintage: str = "",
               confirmed_lanes: Mapping[str, Any] | None = None) -> LivePack:
    """Freeze one session's evaluation substrate for the whole probe set.

    ``store_reader`` is INJECTED: production hands in a reader over the daily
    store, tests hand in synthetic frames, and this module names no store path at
    all.  A name the reader cannot serve lands in ``substrate_missing`` with its
    reason and is never silently dropped (§6's "escalate, don't truncate").

    ``confirmed_lanes`` is likewise INJECTED (v2): the nightly builder's own
    per-ticker G0/C5 read of the Terminal slice store, or None when it has
    nothing to report.  This module performs no slice IO and names no slice
    path — :func:`confirmed_lanes_snapshot` normalizes whatever is handed in to
    every probe ticker, honestly ``unavailable`` for one this pass never
    covered.

    Refuses loudly, before reading a price, when a registered detector hash has
    drifted from its published identity.
    """
    spec_hashes = assert_published_spec_hashes()
    as_of_date = _as_date(as_of)
    next_session = next_reference_session(as_of_date, market=market)
    if next_session is None:
        raise LivePackError(
            f"no reference session follows {as_of_date.isoformat()} — the pack is built "
            f"FOR the next session and cannot be stamped past the calendar's edge")
    snapshot = probe_set_snapshot(probe_set)
    built_stamp = built_at if isinstance(built_at, str) else (iso(built_at) or "")

    names: list[PackName] = []
    substrate: dict[str, pd.DataFrame] = {}
    missing: list[dict[str, Any]] = []

    for ticker in snapshot["tickers"]:
        try:
            frame = store_reader(ticker)
        except Exception as exc:  # noqa: BLE001 — one unreadable name is not an outage
            missing.append({"ticker": ticker, "reason": "store_read_failed",
                            "detail": str(exc)})
            continue
        if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
            missing.append({"ticker": ticker, "reason": "substrate_absent",
                            "detail": "store returned no rows"})
            continue
        try:
            frozen = _frozen_frame(frame, ticker=ticker, next_session=next_session,
                                   price_basis=price_basis, vintage=vintage)
        except (ch.ChallengerError, LivePackError) as exc:
            missing.append({"ticker": ticker, "reason": "substrate_rejected",
                            "detail": str(exc)})
            continue
        if frozen.empty:
            missing.append({"ticker": ticker, "reason": "substrate_absent",
                            "detail": f"no confirmed rows at or before "
                                      f"{as_of_date.isoformat()}"})
            continue

        substrate[ticker] = frozen
        names.append(_pack_name(ticker, frozen, next_session=next_session,
                                market=market))

    lane_rows = confirmed_lanes_snapshot(confirmed_lanes, snapshot["tickers"])

    pack_hash = compute_pack_hash(
        schema=SCHEMA_LIVE_PACK, as_of=as_of_date.isoformat(),
        next_session=next_session.isoformat(), price_basis=price_basis,
        spec_hashes=spec_hashes, probe_tickers=snapshot["tickers"], names=names,
        confirmed_lanes=lane_rows)

    return LivePack(
        schema=SCHEMA_LIVE_PACK, as_of=as_of_date.isoformat(),
        next_session=next_session.isoformat(), built_at=built_stamp,
        price_basis=price_basis, spec_hashes=dict(spec_hashes), probe_set=snapshot,
        names=tuple(sorted(names, key=lambda r: r.ticker)), substrate=substrate,
        substrate_missing=tuple(missing), pack_hash=pack_hash,
        confirmed_lanes=lane_rows)


def _pack_name(ticker: str, frozen: pd.DataFrame, *, next_session: date,
               market: str) -> PackName:
    """Derive one name's receipts from its frozen frame.  No IO, no clock."""
    index = pd.DatetimeIndex(frozen.index)
    last_confirmed = index[-1].date()
    freshness = ch.freshness_state(last_confirmed, next_session, market=market)

    closes = frozen["close"].astype(float)
    as_of_close = ic.last_finite(closes)
    # The ATR available while the NEXT session is open is the one that closed at
    # this frame's last bar — computed on the CUT frame exactly as
    # ``build_observation_path`` does, so today's eventual range is never loaded.
    atr_prior = ic.last_finite(ic.atr14(frozen["high"], frozen["low"], frozen["close"]))
    k_series, d_series = ic.stoch_rsi_kd(closes)
    confirmed_k = ic.last_finite(k_series)
    confirmed_d = ic.last_finite(d_series)

    oracle = OracleFrame(
        ticker=ticker, closes=closes.to_numpy(dtype=float), index=index,
        next_session_ts=pd.Timestamp(next_session).normalize())

    c1 = solve_threshold(
        lambda price: _c1_margin(oracle, price),
        condition="c1_arm_price", predicate=f"K_T < {ic.OVERSOLD} (A5.2 arm condition)",
        anchor=as_of_close, decreasing=True)
    c2a = solve_threshold(
        lambda price: _c2a_margin(oracle, price),
        condition="c2a_cross_price",
        predicate="K_T > D_T (the current half of A5.3's c2a; the K_prev <= D_prev "
                  "half is a path property and is never inverted into a level)",
        anchor=as_of_close, decreasing=False)

    return PackName(
        ticker=ticker, as_of_close=as_of_close,
        last_confirmed=last_confirmed.isoformat(), freshness=freshness,
        atr14_prior_confirmed=atr_prior, confirmed_k=confirmed_k,
        confirmed_d=confirmed_d, confirmed_bars=int(len(closes)),
        substrate_fingerprint=substrate_fingerprint(frozen),
        c1_arm_price=c1, c2a_cross_price=c2a)


# ---------------------------------------------------------------------------
# the inversion PROOF battery (W4 design §1; PIT-W4-19)
# ---------------------------------------------------------------------------

def _case(family: str, name: str, *, boundary: Any, direction: str, expected: Any,
          observed: Any) -> dict[str, Any]:
    return {"family": family, "case": name, "boundary": _jsonable(boundary),
            "direction": direction, "expected": _jsonable(expected),
            "observed": _jsonable(observed), "pass": bool(expected == observed)}


def _proof_threshold_cases(pack: LivePack) -> list[dict[str, Any]]:
    """(a) Every solved level, probed from BOTH sides against the oracle itself.

    Deliberately re-derives the verdict from :class:`OracleFrame` rather than from
    ``ThresholdSolution.holds_at`` alone: a check that reads only the stored level
    is a receipt written from the variable it checks, and cannot fail when the
    level is the thing that is wrong.
    """
    out: list[dict[str, Any]] = []
    for row in pack.names:
        frame = pack.substrate.get(row.ticker)
        if frame is None:
            continue
        index = pd.DatetimeIndex(frame.index)
        oracle = OracleFrame(
            ticker=row.ticker, closes=frame["close"].astype(float).to_numpy(dtype=float),
            index=index, next_session_ts=pd.Timestamp(pack.next_session).normalize())
        for solution, margin in ((row.c1_arm_price, _c1_margin),
                                 (row.c2a_cross_price, _c2a_margin)):
            if solution.no_threshold_exists or solution.price is None:
                continue
            level = float(solution.price)
            for side, probe in (("below", level * (1.0 - PROOF_EPSILON_REL)),
                                ("above", level * (1.0 + PROOF_EPSILON_REL)),
                                ("at", level)):
                got = margin(oracle, probe)
                observed = None if got is None else bool(got > 0.0)
                expected = solution.holds_at(probe)
                out.append(_case("threshold_boundary",
                                 f"{row.ticker}:{solution.condition}:{side}",
                                 boundary=level, direction=side,
                                 expected=expected, observed=observed))
    return out


#: The proof's synthetic morphology.  A pure trend is NOT usable: a perfectly
#: linear close series has a CONSTANT RSI, so its StochRSI rolling extremes
#: coincide and %K is NaN everywhere — the ``flat_rsi_nan`` degeneracy, which is
#: a real case but not the one a boundary probe needs.  A deterministic ripple on
#: the trend gives the oscillator something to be about, with no randomness
#: anywhere (the proof must be byte-reproducible).
_SYNTHETIC_RIPPLE_PCT = 0.04
_SYNTHETIC_RIPPLE_PERIOD = 11.0


def _synthetic_daily(n: int, *, start: float, step: float,
                     end_session: date) -> pd.DataFrame:
    """A deterministic OHLC frame ending at ``end_session``.  No randomness."""
    reference = session_anchor.reference_sessions("US")
    position = int(reference.searchsorted(pd.Timestamp(end_session).normalize(),
                                          side="right"))
    sessions = reference[max(0, position - n):position]
    closes = np.array(
        [(start + step * i)
         * (1.0 + _SYNTHETIC_RIPPLE_PCT
            * float(np.sin(2.0 * np.pi * i / _SYNTHETIC_RIPPLE_PERIOD)))
         for i in range(len(sessions))], dtype=float)
    return pd.DataFrame(
        {"high": closes * 1.01, "low": closes * 0.99, "close": closes},
        index=pd.DatetimeIndex(sessions))


def _flat_tape(session: date, price: float) -> ch.SessionTape:
    """A one-print RTH tape at ``price`` — the cheapest lawful session tape."""
    open_dt, _close_dt = session_window_et(session)
    return ch.SessionTape(
        session=session,
        minutes=(ch.MinuteBar(start=open_dt + timedelta(minutes=1), open=price,
                              high=price, low=price, close=price),),
        price_basis=ch.BASIS_ADJUSTED, vintage="inversion-proof")


def _proof_micro_path_cases(next_session: date) -> list[dict[str, Any]]:
    """(b) State micro-paths driven through the UNMODIFIED run_c1 / run_c2.

    Two synthetic names — one in a long decline, one in a long advance — each
    solved for its OWN C1 boundary and then evaluated at the probe prices through
    the real evaluator.  Three shapes are covered, and a degeneracy is probed
    just as hard as a level is:

      solved level     arm just BELOW it, refuse just ABOVE it
      ``never_true``   refuse at BOTH ends of the bracket
      ``always_true``  arm at BOTH ends of the bracket

    The pre-arm law rides along: whenever C1 does not arm, no C2 variant may
    fire — asserted from :func:`challengers.run_c2`'s own output, not from a
    restatement of the rule.
    """
    out: list[dict[str, Any]] = []
    prior = ch.prior_reference_session(next_session)
    if prior is None:
        return out
    for label, start, step in (("decline", 220.0, -1.0), ("advance", 60.0, 1.0)):
        frame = _synthetic_daily(180, start=start, step=step, end_session=prior)
        if frame.empty:
            continue
        history = ch.DailyHistory(frame=frame, price_basis=ch.BASIS_ADJUSTED,
                                  vintage="inversion-proof")
        frozen = history.confirmed_through(next_session)
        ticker = f"PROOF_{label.upper()}"
        oracle = OracleFrame(
            ticker=ticker,
            closes=frozen["close"].astype(float).to_numpy(dtype=float),
            index=pd.DatetimeIndex(frozen.index),
            next_session_ts=pd.Timestamp(next_session).normalize())
        anchor = ic.last_finite(frozen["close"].astype(float))
        solution = solve_threshold(
            lambda price, _o=oracle: _c1_margin(_o, price),
            condition="c1_arm_price", predicate=f"K_T < {ic.OVERSOLD}",
            anchor=anchor, decreasing=True)

        if solution.no_threshold_exists:
            if solution.reason not in ("always_true", "never_true"):
                # A warm-up or non-monotone degeneracy carries no lawful probe.
                continue
            expected = bool(solution.reason == "always_true")
            probes = (("bracket_low", float(solution.bracket_low or 0.0), expected),
                      ("bracket_high", float(solution.bracket_high or 0.0), expected))
            boundary: Any = solution.reason
        else:
            level = float(solution.price or 0.0)
            probes = (("below", level * (1.0 - PROOF_EPSILON_REL), True),
                      ("above", level * (1.0 + PROOF_EPSILON_REL), False))
            boundary = level

        for side, price, expected in probes:
            path = ch.build_observation_path(
                ticker=ticker, daily=history, tapes=[_flat_tape(next_session, price)])
            run = ch.run_c1(path)
            armed = run.episode is not None
            out.append(_case("state_micro_path", f"{label}:c1_arm:{side}",
                             boundary=boundary, direction=side, expected=expected,
                             observed=armed))
            c2 = ch.run_c2(path, run.episode)
            fired = sorted(v for v, stamps in c2.fires.items() if stamps)
            if not armed:
                out.append(_case("state_micro_path", f"{label}:c2_pre_arm:{side}",
                                 boundary=boundary, direction=side, expected=[],
                                 observed=fired))
    return out


def _proof_rearm_cases() -> list[dict[str, Any]]:
    """(c) §10's re-arm rule at both of its boundaries, through ``rearm_eligible``."""
    floor = float(ch.REARM_K_FLOOR)
    runs = int(ch.REARM_K_SESSIONS)
    cap = int(ch.REARM_MAX_SESSIONS)
    eps = 1e-9
    cases = [
        ("k_at_floor", [floor] * runs, 0, False),
        ("k_just_above_floor", [floor + eps] * runs, 0, True),
        ("k_above_floor_one_short", [floor + eps] * (runs - 1), 0, False),
        ("k_run_broken_by_none", ([floor + eps] * (runs - 1)) + [None]
         + [floor + eps], 0, False),
        ("sessions_below_cap", [], cap - 1, False),
        ("sessions_at_cap", [], cap, True),
        ("sessions_above_cap", [], cap + 1, True),
    ]
    out: list[dict[str, Any]] = []
    for name, ks, elapsed, expected in cases:
        observed = ch.rearm_eligible(ks, elapsed)
        out.append(_case("rearm", name, boundary={"floor": floor, "runs": runs,
                                                  "max_sessions": cap},
                         direction="both", expected=expected, observed=observed))
    return out


def _c2f_observation(rebound: float | None, *, atr_value: float | None,
                     observed_at: str) -> ch.Observation:
    """A single lawful observation carrying exactly the rebound c2f measures."""
    low = 100.0
    return ch.Observation(
        ticker="PROOF_C2F", observed_at=observed_at, market_session="2026-01-02",
        interval_start=observed_at, availability="provisional",
        bar_state="provisional",
        sampled_close=None if rebound is None else low + rebound,
        running_sampled_low=None if rebound is None else low,
        running_minute_low=None, k=30.0, d=29.0, hist=0.1,
        source_bar_time="2026-01-02", source_bar_known_at=None,
        data_vintage="inversion-proof", price_basis=ch.BASIS_ADJUSTED,
        daily_price_basis=ch.BASIS_ADJUSTED, atr_prior_confirmed=atr_value,
        atr_basis=None if atr_value is None else "wilder_atr14[proof]",
        confirmed_bars=300)


def _proof_c2f_cases() -> list[dict[str, Any]]:
    """(d) c2f's ``0.5 x ATR`` rebound at its boundary, through :func:`run_c2`.

    Driven through the REAL evaluator (eligibility, availability, the null law
    and all) rather than by poking the variant's private predicate: the thing
    under test is what the live lane will actually execute.
    """
    atr = 4.0
    threshold = ch.C2F_ATR_MULTIPLE * atr
    eps = 1e-9
    armed_at = "2026-01-02T14:35:00Z"
    cases = [
        ("rebound_at_threshold", threshold, atr, True),
        ("rebound_below_threshold", threshold - eps, atr, False),
        ("rebound_above_threshold", threshold + eps, atr, True),
        ("atr_missing_is_null", threshold, None, None),
        ("atr_non_positive_is_null", threshold, 0.0, None),
    ]
    out: list[dict[str, Any]] = []
    for name, rebound, atr_value, expected in cases:
        episode = ch.DetectorEpisode(ticker="PROOF_C2F",
                                     detector_id=ch.C1_DETECTOR_ID)
        episode.first_armed_at = armed_at
        run = ch.run_c2([_c2f_observation(rebound, atr_value=atr_value,
                                          observed_at="2026-01-02T15:00:00Z")],
                        episode)
        observed = next((r.condition_met for r in run.readings
                         if r.variant == "c2f_rebound_atr"), "no_reading")
        out.append(_case("c2f_rebound", name,
                         boundary={"atr": atr, "multiple": ch.C2F_ATR_MULTIPLE,
                                   "threshold": threshold},
                         direction="both", expected=expected, observed=observed))
    return out


def _hist_tail(closes: Sequence[float]) -> tuple[float, float, float] | None:
    """The last three finite RSI-MACD histogram values of ``closes``, or None.

    Computed through :func:`indicator_core.rsi_macd_hist` — the same indicator
    :func:`four_hour.four_hour_turn` reads, but extracted independently of the
    detector's own ``finite_tail`` + predicate wiring, so the two can disagree.
    """
    hist = ic.rsi_macd_hist(pd.Series(list(closes), dtype=float))
    return ic.finite_tail(hist, 3)


def _proof_c3_turn_cases() -> list[dict[str, Any]]:
    """(e) C3's 3-point turn predicate at EACH inequality boundary.

    ``H_T > H_prev`` is STRICT and ``H_prev <= H_prev2`` is INCLUSIVE, and both
    are probed against :func:`four_hour.four_hour_turn` itself:

      * the slope boundary is SOLVED — the final 4H close is bisected until
        ``H_T == H_prev`` (an EMA chain is causal, so ``H_prev``/``H_prev2`` do
        not move with it) and the detector is then run at that level ± eps;
      * the trough inequality is probed on both sides by using two prefixes
        whose ``H_prev``/``H_prev2`` ordering differs, with the final close held
        above the slope boundary.

    ``expected`` is computed from the INDEPENDENTLY extracted histogram triple,
    never from the detector's own answer.
    """
    out: list[dict[str, Any]] = []
    base = 100.0

    def ripple(i: int) -> float:
        return 1.0 + _SYNTHETIC_RIPPLE_PCT * float(
            np.sin(2.0 * np.pi * i / _SYNTHETIC_RIPPLE_PERIOD))

    prefixes = {
        # A long slide into a V — the histogram troughs, so H_prev <= H_prev2.
        "trough": [(base - 0.6 * i) * ripple(i) for i in range(110)]
                  + [base - 66.0, base - 63.0],
        # A steady advance — the histogram is still rising, so H_prev > H_prev2.
        "rally": [(base + 0.6 * i) * ripple(i) for i in range(112)],
    }
    for label, prefix in prefixes.items():
        anchor = float(prefix[-1])

        def margin(price: float, _p=prefix) -> float | None:
            tail = _hist_tail([*_p, price])
            return None if tail is None else float(tail[2] - tail[1])

        solution = solve_threshold(
            margin, condition="c3_slope_boundary",
            predicate="H4_T > H4_prev (A5.4 turn primitive, strict)",
            anchor=anchor, decreasing=False)
        if solution.no_threshold_exists or solution.price is None:
            out.append(_case("c3_turn", f"{label}:slope_boundary_unsolved",
                             boundary=solution.reason, direction="n/a",
                             expected=True,
                             observed=solution.reason in DEGENERATE_REASONS))
            continue
        level = float(solution.price)
        for side, price in (("below", level * (1.0 - PROOF_EPSILON_REL)),
                            ("above", level * (1.0 + PROOF_EPSILON_REL))):
            closes = [*prefix, price]
            tail = _hist_tail(closes)
            if tail is None:
                continue
            prev2, prev, now = tail
            expected = bool(now > prev and prev <= prev2)
            observed = four_hour_turn(pd.Series(closes, dtype=float))
            out.append(_case("c3_turn", f"{label}:turn:{side}",
                             boundary={"level": level, "prev2": prev2, "prev": prev},
                             direction=side, expected=expected, observed=observed))
    # The warm-up law: fewer than three finite histogram points is None, never
    # False — a warm-up counted as a non-fire is a measured non-fire that never
    # happened.
    short = pd.Series([1.0, 2.0], dtype=float)
    out.append(_case("c3_turn", "warmup_is_null", boundary=2, direction="n/a",
                     expected=None, observed=four_hour_turn(short)))
    return out


def _proof_basis_cases() -> list[dict[str, Any]]:
    """(f) The §5 basis tolerance at its boundary, through :func:`basis_audit`."""
    anchor = 100.0
    tol = BASIS_TOLERANCE_PCT
    cases = [
        ("gap_at_tolerance", anchor * (1.0 - tol / 100.0), False),
        ("gap_just_above_tolerance", anchor * (1.0 - (tol + 1e-4) / 100.0), True),
        ("gap_just_below_tolerance", anchor * (1.0 - (tol - 1e-4) / 100.0), False),
        ("gap_zero", anchor, False),
    ]
    out: list[dict[str, Any]] = []
    for name, prev_close, expected in cases:
        observed = basis_audit(anchor, prev_close)["mismatch"]
        out.append(_case("basis_tolerance", name,
                         boundary={"tolerance_pct": tol}, direction="both",
                         expected=expected, observed=observed))
    out.append(_case("basis_tolerance", "missing_close_is_null",
                     boundary={"tolerance_pct": tol}, direction="n/a",
                     expected=None, observed=basis_audit(anchor, None)["mismatch"]))
    return out


def build_inversion_proof(pack: LivePack) -> dict[str, Any]:
    """The nightly falsification battery.  Bounded, deterministic, outcome-blind.

    Every case straddles ONE frozen boundary in BOTH directions and records
    ``{case, boundary, direction, expected, observed, pass}``.  ANY failure marks
    the pack ``proof_failed``; the RTH evaluator then refuses the whole cycle,
    because an evaluator that disagrees with the levels it is about to compare
    against must not run.

    It tunes nothing, optimises nothing, reads no forward outcome, ranks nothing
    and never touches a spec hash.
    """
    next_session = _as_date(pack.next_session)
    cases: list[dict[str, Any]] = []
    cases += _proof_threshold_cases(pack)
    cases += _proof_micro_path_cases(next_session)
    cases += _proof_rearm_cases()
    cases += _proof_c2f_cases()
    cases += _proof_c3_turn_cases()
    cases += _proof_basis_cases()

    by_family: dict[str, dict[str, int]] = {}
    for case in cases:
        block = by_family.setdefault(case["family"], {"total": 0, "failed": 0})
        block["total"] += 1
        if not case["pass"]:
            block["failed"] += 1
    failures = [case for case in cases if not case["pass"]]
    return {
        "schema": SCHEMA_INVERSION_PROOF,
        "as_of": pack.as_of,
        "pack_hash": pack.pack_hash,
        "cases_total": len(cases),
        "failures": failures,
        "by_family": dict(sorted(by_family.items())),
        "pass": not failures,
    }


# ---------------------------------------------------------------------------
# persistence — an INJECTED state dir, never ``data/``
# ---------------------------------------------------------------------------

def pack_root(state_dir: Path | str) -> Path:
    return Path(state_dir) / _PACK_DIRNAME


def pointer_path(state_dir: Path | str) -> Path:
    return pack_root(state_dir) / _POINTER_NAME


def _substrate_frame(pack: LivePack) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for ticker in sorted(pack.substrate):
        frame = pack.substrate[ticker]
        index = pd.DatetimeIndex(frame.index)
        for position in range(len(frame)):
            row = {"ticker": ticker,
                   "session": index[position].date().isoformat()}
            for column in _SUBSTRATE_COLUMNS:
                row[column] = float(frame[column].iloc[position])
            rows.append(row)
    if not rows:
        return pd.DataFrame(columns=["ticker", "session", *_SUBSTRATE_COLUMNS])
    return pd.DataFrame(rows)


def save_pack(pack: LivePack, state_dir: Path | str, *,
              retention: int = PACK_RETENTION) -> Path:
    """Write ``pack/<as_of>/`` and swap the ``current`` pointer atomically.

    The whole session directory is built in a sibling temp dir and moved into
    place with ``os.replace``, so a reader never sees a manifest without its
    substrate.  The pointer is swapped LAST and only after the directory is
    complete — the order that makes a crashed build invisible instead of
    half-visible.
    """
    root = pack_root(state_dir)
    root.mkdir(parents=True, exist_ok=True)
    final = root / pack.as_of

    staging = Path(tempfile.mkdtemp(prefix=f".{pack.as_of}.", dir=root))
    try:
        (staging / _MANIFEST_NAME).write_text(
            json.dumps(pack.manifest(), sort_keys=True, separators=(",", ":"),
                       allow_nan=False),
            encoding="utf-8")
        _substrate_frame(pack).to_parquet(staging / _SUBSTRATE_NAME, index=False)
        if final.exists():
            shutil.rmtree(final)
        os.replace(staging, final)
        staging = None  # type: ignore[assignment]
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)

    pointer = {"as_of": pack.as_of, "pack_hash": pack.pack_hash,
               "manifest": f"{_PACK_DIRNAME}/{pack.as_of}/{_MANIFEST_NAME}",
               "built_at": pack.built_at}
    tmp_pointer = root / f".{_POINTER_NAME}.tmp"
    tmp_pointer.write_text(json.dumps(pointer, sort_keys=True, separators=(",", ":")),
                           encoding="utf-8")
    os.replace(tmp_pointer, root / _POINTER_NAME)

    prune_packs(state_dir, retention=retention)
    return final


def prune_packs(state_dir: Path | str, *, retention: int = PACK_RETENTION) -> list[str]:
    """Keep the newest ``retention`` session directories; report what was pruned.

    The pointer's own session is never pruned, whatever the retention says — a
    pointer to a directory this function deleted is the one failure mode a
    retention sweep must not create.
    """
    root = pack_root(state_dir)
    if not root.is_dir():
        return []
    current = None
    try:
        current = json.loads((root / _POINTER_NAME).read_text(encoding="utf-8")).get("as_of")
    except (OSError, ValueError):
        current = None
    sessions = sorted((p.name for p in root.iterdir()
                       if p.is_dir() and not p.name.startswith(".")), reverse=True)
    keep = set(sessions[:max(1, int(retention))])
    if current:
        keep.add(str(current))
    pruned: list[str] = []
    for name in sessions:
        if name in keep:
            continue
        shutil.rmtree(root / name, ignore_errors=True)
        pruned.append(name)
    return pruned


def load_pack(state_dir: Path | str, *, as_of: str | None = None) -> LivePack | None:
    """Read the current pack (or a named session), or None when there is none."""
    root = pack_root(state_dir)
    session = as_of
    if session is None:
        try:
            session = json.loads(
                (root / _POINTER_NAME).read_text(encoding="utf-8")).get("as_of")
        except (OSError, ValueError):
            return None
    if not session:
        return None
    manifest_path = root / str(session) / _MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    substrate: dict[str, pd.DataFrame] = {}
    substrate_path = root / str(session) / _SUBSTRATE_NAME
    if substrate_path.exists():
        flat = pd.read_parquet(substrate_path)
        for ticker, block in flat.groupby("ticker", sort=True):
            frame = block.set_index(pd.DatetimeIndex(pd.to_datetime(block["session"])))
            substrate[str(ticker)] = frame.loc[:, list(_SUBSTRATE_COLUMNS)].astype(float)

    # A missing/empty `schema` field means this manifest predates the field
    # entirely — that is a v1 pack, never the CURRENT `SCHEMA_LIVE_PACK`
    # (N4): defaulting it to "whatever v2 currently is" would present a pack
    # that never carried `confirmed_lanes` as though it did.
    raw_confirmed_lanes = manifest.get("confirmed_lanes") or {}
    return LivePack(
        schema=str(manifest.get("schema") or _SCHEMA_LIVE_PACK_V1),
        as_of=str(manifest["as_of"]), next_session=str(manifest["next_session"]),
        built_at=str(manifest.get("built_at") or ""),
        price_basis=str(manifest.get("price_basis") or ch.BASIS_ADJUSTED),
        spec_hashes=dict(manifest.get("spec_hashes") or {}),
        probe_set=dict(manifest.get("probe_set") or {}),
        names=tuple(PackName.from_dict(row) for row in manifest.get("names") or ()),
        substrate=substrate,
        substrate_missing=tuple(dict(row) for row in
                                manifest.get("substrate_missing") or ()),
        pack_hash=str(manifest.get("pack_hash") or ""),
        # (S1) Routed through the SAME normalizer `build_pack` uses — a torn or
        # hand-repaired manifest row must not reach the live reader verbatim;
        # this is the production read path, and the module's own firewall
        # claim (confirmed_lanes_snapshot's docstring) is only true if EVERY
        # entry point normalizes, not just the write path.
        confirmed_lanes=confirmed_lanes_snapshot(
            raw_confirmed_lanes, list(raw_confirmed_lanes)),
        proof=manifest.get("proof"))


def pack_is_fresh(pack: LivePack | None, now: datetime) -> bool:
    """§5's stale-pack gate: ``pack.as_of == expected_last_session(now)``.

    ``now`` is INJECTED.  A stale pack does not merely age a reading — a
    wrong-session series FABRICATES crossings, which is why the matrix row
    demands ``unavailable`` for the whole cycle rather than a best-effort read.
    """
    if pack is None:
        return False
    from lib.nyse_calendar import expected_last_session  # noqa: PLC0415
    return str(pack.as_of) == expected_last_session(now).isoformat()
