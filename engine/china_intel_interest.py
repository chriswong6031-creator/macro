"""CHINA INTELLIGENCE INTEREST — the BOARD-INDEPENDENT interest composite (v4 R1).

The China Prophet v4 board ranks by INTERESTINGNESS and gates by ENTRY.  This
module owns the first half: a deterministic ``intel_interest_score`` in ``[0, 100]``
built from China Intelligence's *upstream evidence* only.  It owns no admission
decision, no lane, and no display shelf — :mod:`engine.china_board_rank` remains the
sole live ranking authority and decides what, if anything, this evidence does to the
board.

WHY A SEPARATE SCORER RATHER THAN THE HUB'S ``opportunity_score``
----------------------------------------------------------------
:mod:`engine.china_intel_hub` fuses five desks, and one of those desks IS the Prophet
board (``site/factordata/china_standouts.json``).  Its ``opportunity_score`` therefore
carries the board's own output back into itself through four separate terms.  Ranking
the board by that number would close a feedback loop: names would rank highly partly
because they already rank highly.  This module re-derives the composite from the same
upstream evidence with every board-derived term STRUCTURALLY ABSENT — not zeroed, not
down-weighted, but never computed and never available to compute:

  * ``board_row`` direction (hub ``_dirs``: board membership read as a bullish desk)
  * board label → edge fraction (hub ``_edge_remaining``: the ``_LABEL_EDGE`` leg)
  * the board-ABSENT bonus (hub ``_edge_remaining``: ``0.75`` for "crowd hasn't found it")
  * board direction inside the leading-vs-lagging gap (hub ``_leading_gap``: ``lag_up``)
  * any Prophet score or rank, in any leg, at any weight

See :data:`BOARD_DERIVED_TERMS_EXCLUDED`.  ``tests/test_china_intel_interest.py`` pins
the fence structurally: this module never reads the board artifact and never reads the
hub's own command artifact.

WHAT REMAINS (upstream evidence, not Prophet's own output)
----------------------------------------------------------
signal core (altdata convergence/conviction, else radar strength) · price trajectory
(off-high room, RS vs CSI300, 20d extension) · special-situation overhang penalties ·
altdata crowding penalty · falsifier penalty · leading-desk information.  The
composite keeps the hub's INTELLIGENCE_HUB_V2 shape so the two numbers stay readable
against each other:

    interest = 100 × signal_core × falsifier_penalty × edge_remaining × gap_mult

CONTEXT TIER.  This is a display/ordering-tier composite: it orders names that the
v3 entry machinery has ALREADY admitted, and it can neither admit a name nor veto one.
It has accrued no forward record of its own and claims none; promotion to any
gate/size authority is a separate pre-registered question.

NULLS ARE NOT ZEROS.  A name the desks have never seen has no interest score — it is
returned as ``basis="unavailable"`` with ``score=None``, and the board falls back to
its v3 priority under an explicit ``intel_interest_basis="fallback_v3"`` stamp.
Fabricating a zero would sink every uncovered name beneath every covered one on
evidence that was never gathered.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Iterable, Mapping

log = logging.getLogger(__name__)

INTEREST_DEFINITION = "cn_intel_interest_v1"

#: Board-derived terms of the hub composite that are structurally absent here.  The
#: names are the hub's own, so a reader can diff the two scorers leg by leg.
BOARD_DERIVED_TERMS_EXCLUDED = (
    "board_row_direction",       # china_intel_hub._dirs -> dirs["board"]
    "board_label_edge",          # china_intel_hub._edge_remaining -> _LABEL_EDGE leg
    "board_absent_bonus",        # china_intel_hub._edge_remaining -> "not on buy-board"
    "board_lagging_desk_gap",    # china_intel_hub._leading_gap -> lag_up
    "prophet_score",
    "prophet_rank",
    "hub_opportunity_score",
)

#: Basis values stamped on every board row.  ``measured`` means the composite was
#: computed from real board-independent evidence; ``fallback_v3`` means it was not
#: computable and the row keeps its v3 priority.
BASIS_MEASURED = "measured"
BASIS_FALLBACK = "fallback_v3"

# Signal-core scaling — the hub's constants, kept identical so the two composites stay
# comparable.  Altdata convergence is the one calibrated CN cross-sectional signal;
# radar alone is weaker and is discounted accordingly.  Neither ever reaches 1.0.
_ALTDATA_CORE_SCALE = 0.85
_RADAR_CORE_SCALE = 0.60

# Falsifier penalty (hub parity): one flat multiplicative haircut when any
# disconfirming observation stands unanswered.  Never compounds.
_FALSIFIER_PENALTY = 0.85
_WEAK_CONVERGENCE_MAX = 0.4

# Leading-gap multiplier (hub parity): ±15% per net leading desk, clamped to ±2.
_GAP_STEP = 0.15
_GAP_CLAMP = 2

# Edge-remaining component weights (hub parity, board legs removed).
_W_OFF_HIGH = 0.6
_W_RS = 0.7
_W_EXTENSION = 0.6
_W_UNLOCK_LARGE = 0.8
_W_UNLOCK = 0.5
_W_PLEDGE = 0.6
_W_CROWDING = 0.7
_EXTENSION_RET20_MIN = 12.0

_UNAVAILABLE_NO_DESK = "no_desk_evidence"
_UNAVAILABLE_NO_EDGE = "no_edge_evidence"


def _clamp01(value: float) -> float:
    return 0.0 if value < 0 else 1.0 if value > 1 else value


def _f(value: Any) -> float | None:
    """Float or ``None``.  Booleans and containers are not numbers here."""
    if value is None or isinstance(value, (dict, list, bool)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


# ── Signal core ───────────────────────────────────────────────────────────── #

def _signal_core(altdata_row: Mapping[str, Any] | None,
                 radar_row: Mapping[str, Any] | None) -> tuple[float, str | None]:
    """Return ``(core, source)`` — the leading-desk signal strength in ``[0, 1]``.

    Altdata wins when present because convergence is rank-normalised cross-sectionally
    over the full CN universe; radar is a sector-level read crosswalked to members and
    is discounted.  A desk that is present but reads zero yields a genuine measured
    zero — evidence of nothing interesting, which is NOT the same as absence of
    evidence (that is :data:`BASIS_FALLBACK`).

    DIRECTIONAL, AND DELIBERATELY UNLIKE THE HUB.  ``china_intel_hub._dossier`` takes
    ``abs(convergence)`` because it ranks a TWO-SIDED command list where direction is
    carried separately by ``lean``/``stage``.  The Prophet board is a one-sided BUY
    shelf, so magnitude-without-direction is the wrong core here: measured 2026-08-15,
    60 of the 116 live board names read ``distribute``, and an unsigned core put the
    three most strongly-distributed names in the top three slots — the desk's own
    verdict inverted.  Only the accumulate side buys interest; a distribute read is a
    measured zero, and ``conviction100`` (an UNSIGNED magnitude, ``china_altdata``:
    ``to_100(abs(conv) × …)``) is credited only when the side agrees.  Do not
    "restore hub parity" here without re-reading this paragraph.
    """
    if altdata_row is not None:
        conv_up = max(0.0, _f(altdata_row.get("convergence")) or 0.0)
        c100 = (_f(altdata_row.get("conviction100")) or 0.0
                if altdata_row.get("side") == "accumulate" else 0.0)
        return _clamp01(max(conv_up, c100 / 100.0) * _ALTDATA_CORE_SCALE), "altdata"
    if radar_row is not None:
        strength = (_f(radar_row.get("strength")) or 0.0
                    if radar_row.get("sign") == "positive" else 0.0)
        return _clamp01(strength * _RADAR_CORE_SCALE), "radar"
    return 0.0, None


# ── Edge remaining (board legs removed) ───────────────────────────────────── #

def _edge_remaining(altdata_row: Mapping[str, Any] | None,
                    special_flags: Mapping[str, Any] | None,
                    traj: Mapping[str, Any] | None) -> dict[str, Any]:
    """How much of the move is still AHEAD, in ``[0, 1]``, from non-board evidence.

    Returns ``{"score": float|None, "n_components": int, "drivers": [...]}``.  A
    ``None`` score means NO edge evidence existed at all — the hub's 0.4 default is
    deliberately NOT taken here, because with the board legs removed an empty
    component list is genuinely empty rather than merely board-less, and awarding a
    middling constant to a name we know nothing about is the fabrication this module
    exists to avoid.
    """
    comps: list[tuple[float, float, str]] = []   # (weight, score, driver)
    traj = traj or {}
    rolling_over = bool(traj.get("rolling_over"))

    # Off-high room: the further below the trailing high, the more room remains.  A
    # name that is BOTH off its high and rolling over is falling, not coiled.
    off_high = _f(traj.get("off_high_pct"))
    if off_high is not None:
        score = 0.1 if rolling_over else _clamp01(0.15 + (-off_high) / 22.0)
        comps.append((_W_OFF_HIGH, score,
                      f"{off_high:.0f}% off high (falling)" if rolling_over
                      else f"{off_high:.0f}% off high"))

    # RS vs CSI300: relative strength already spent is edge already taken.
    rs_20 = _f(traj.get("rs_20d"))
    if rs_20 is not None:
        comps.append((_W_RS,
                      _clamp01(1.0 - max(rs_20, 0.0) / 35.0) if rs_20 > 0 else 1.0,
                      f"RS {rs_20:+.1f}% vs CSI300 (20d)"))

    # A large recent run is priced in.
    ret_20 = _f(traj.get("ret_20d"))
    if ret_20 is not None and ret_20 > _EXTENSION_RET20_MIN:
        comps.append((_W_EXTENSION, _clamp01(1.0 - ret_20 / 30.0),
                      f"{ret_20:.0f}% 20d return (extended)"))

    # Special-situation overhang: supply the tape has not absorbed yet.
    if special_flags:
        if special_flags.get("unlock_large"):
            comps.append((_W_UNLOCK_LARGE, 0.15, "large unlock overhang"))
        elif special_flags.get("unlock"):
            comps.append((_W_UNLOCK, 0.30, "unlock overhang"))
        if special_flags.get("pledge_stress"):
            comps.append((_W_PLEDGE, 0.10, "pledge stress"))

    # Crowding: positioning already in the name.
    if altdata_row and altdata_row.get("flags"):
        flags = altdata_row.get("flags") or []
        if any("crowd" in str(flag).lower() for flag in flags):
            comps.append((_W_CROWDING, 0.15, "altdata crowding flag"))

    if not comps:
        return {"score": None, "n_components": 0, "drivers": []}

    weight_sum = sum(w for w, _s, _d in comps)
    score = sum(w * s for w, s, _d in comps) / weight_sum
    ranked = sorted(comps, key=lambda comp: comp[1], reverse=True)
    drivers = [comp[2] for comp in ranked[:2]]
    if len(comps) > 2 and ranked[-1][1] < 0.30:
        drivers.append("drag: " + ranked[-1][2])
    return {"score": round(_clamp01(score), 3), "n_components": len(comps),
            "drivers": drivers}


# ── Leading gap (board excluded from the lagging side) ────────────────────── #

def _leading_gap(altdata_row: Mapping[str, Any] | None,
                 radar_row: Mapping[str, Any] | None) -> dict[str, int]:
    """Leading desks up, lagging desks still quiet = pre-consensus.

    ``lead_up`` counts the LEADING desks (altdata, radar) pointing up.  ``lag_up``
    counts LAGGING desks pointing up — and the board, the hub's second lagging desk,
    is excluded by construction here.  The news desk computes no sentiment
    (``china_intel_hub._dirs``: news direction is always ``None``), so today ``lag_up``
    is structurally 0 and ``gap == lead_up``.  It is kept as an explicit subtraction so
    that a future lagging desk WITH a direction wires in without re-deriving the law.
    """
    lead_up = 0
    if altdata_row is not None and altdata_row.get("side") == "accumulate":
        lead_up += 1
    if radar_row is not None and radar_row.get("sign") == "positive":
        lead_up += 1
    lag_up = 0   # board excluded by construction; news carries no direction
    return {"lead_up": lead_up, "lag_up": lag_up, "gap": lead_up - lag_up}


# ── Falsifier ─────────────────────────────────────────────────────────────── #

def _falsifiers(altdata_row: Mapping[str, Any] | None,
                radar_row: Mapping[str, Any] | None,
                special_flags: Mapping[str, Any] | None,
                traj: Mapping[str, Any] | None) -> list[str]:
    """Unanswered disconfirming observations.  Internal receipt wording only.

    These strings are NOT user-facing: front-facing surfaces never print falsifier or
    refutation language (operator 2026-07-27, #3821).  They exist so the ordering
    receipt can say why a name was haircut.
    """
    out: list[str] = []
    traj = traj or {}
    if traj.get("rolling_over"):
        out.append("price rolling over (20d drawdown + RS falling)")
    if altdata_row is not None:
        conv = _f(altdata_row.get("convergence"))
        if (conv is not None and altdata_row.get("side") == "accumulate"
                and conv < _WEAK_CONVERGENCE_MAX):
            out.append("weak altdata convergence")
    if radar_row is not None:
        reliability = radar_row.get("reliability")
        if isinstance(reliability, Mapping) and reliability.get("basis") == "unproven":
            out.append("radar signal unproven (0 resolved outcomes)")
    if special_flags:
        if special_flags.get("unlock_large"):
            out.append("large lock-up unlock imminent")
        if special_flags.get("pledge_stress"):
            out.append("pledge stress overhang")
    return out


# ── The composite ─────────────────────────────────────────────────────────── #

def interest_score(
    *,
    altdata_row: Mapping[str, Any] | None = None,
    radar_row: Mapping[str, Any] | None = None,
    special_flags: Mapping[str, Any] | None = None,
    traj: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The pure, deterministic, board-independent interest composite for ONE name.

    No I/O, no globals, no clock: identical inputs always produce an identical record.
    Every input is upstream evidence — nothing derived from the Prophet board or from
    :mod:`engine.china_intel_hub`'s own composite may be passed in (see
    :data:`BOARD_DERIVED_TERMS_EXCLUDED`).

    Returns a record whose ``basis`` is either :data:`BASIS_MEASURED` (``score`` is a
    float in ``[0, 100]``) or :data:`BASIS_FALLBACK` (``score`` is ``None`` and the
    caller must order the name by its v3 priority instead).  Two conditions produce a
    fallback, both recorded in ``unavailable_reason``:

    * ``no_desk_evidence`` — neither leading desk has ever seen the name.
    * ``no_edge_evidence`` — a desk has seen it, but no edge component could be formed
      (no price plane, no overhang, no crowding), so the composite has no second half.
    """
    core, core_source = _signal_core(altdata_row, radar_row)
    if core_source is None:
        return _unavailable(_UNAVAILABLE_NO_DESK)

    edge = _edge_remaining(altdata_row, special_flags, traj)
    if edge["score"] is None:
        return _unavailable(_UNAVAILABLE_NO_EDGE, signal_core=round(core, 3),
                            signal_source=core_source)

    gap = _leading_gap(altdata_row, radar_row)
    gap_mult = 1.0 + _GAP_STEP * max(-_GAP_CLAMP, min(_GAP_CLAMP, gap["gap"]))

    falsifiers = _falsifiers(altdata_row, radar_row, special_flags, traj)
    falsifier_penalty = _FALSIFIER_PENALTY if falsifiers else 1.0

    score = 100.0 * core * falsifier_penalty * edge["score"] * gap_mult
    return {
        "definition": INTEREST_DEFINITION,
        "basis": BASIS_MEASURED,
        "score": round(max(0.0, min(100.0, score)), 2),
        "signal_core": round(core, 3),
        "signal_source": core_source,
        "edge_remaining": edge["score"],
        "edge_components": edge["n_components"],
        "gap": gap["gap"],
        "lead_up": gap["lead_up"],
        "gap_mult": round(gap_mult, 3),
        "falsifier_penalty": falsifier_penalty,
        "falsifiers": falsifiers,
        "drivers": edge["drivers"],
        "excludes": list(BOARD_DERIVED_TERMS_EXCLUDED),
    }


def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    record = {
        "definition": INTEREST_DEFINITION,
        "basis": BASIS_FALLBACK,
        "score": None,
        "unavailable_reason": reason,
        "drivers": [],
        "excludes": list(BOARD_DERIVED_TERMS_EXCLUDED),
    }
    record.update(extra)
    return record


# ── Evidence loading (upstream producers only) ────────────────────────────── #

def altdata_rows() -> list[dict]:
    """The FULL per-ticker altdata convergence universe, computed in process.

    Deliberately NOT ``site/chinaaltdata/by_ticker.json``: that artifact is a top-30 /
    bottom-30 display slice (measured 2026-08-15: 89 tickers, 0 of which were on the
    116-row board), and it is written by a builder that runs AFTER the board in
    ``asia-close.yml``, so reading it would give the board a stale 30-name sample.
    ``china_altdata`` recomputes from the CN data stores in ~1.8s over ~5.3k names and
    covered 116/116 board rows on the same date.  ``[]`` on any failure.
    """
    try:
        from engine import china_altdata
        return list(china_altdata.full_rows())
    except Exception as exc:  # noqa: BLE001 — evidence is additive, never fatal
        log.warning("china_intel_interest: altdata rows unavailable (%s)", exc)
        return []


def radar_by_ticker() -> dict[str, dict]:
    """Divergence-radar rows crosswalked to member tickers, via the hub's own readers.

    The hub's INPUT loaders are reused rather than copied so the two scorers can never
    drift on what "the radar said".  What is deliberately NOT reused is the hub's
    composite: no ``opportunity_score``, no dossier, no command artifact.
    """
    try:
        from engine import china_intel_hub as hub
        rows = hub._load_radar_by_sector()
        return {str(k).upper().strip(): v
                for k, v in (hub._build_radar_by_ticker(rows) or {}).items()}
    except Exception as exc:  # noqa: BLE001
        log.warning("china_intel_interest: radar rows unavailable (%s)", exc)
        return {}


def special_by_ticker() -> dict[str, dict]:
    """Special-situation flags (unlock / pledge overhang) keyed by ticker."""
    try:
        from engine import china_intel_hub as hub
        return {str(k).upper().strip(): v
                for k, v in (hub._load_special_by_ticker() or {}).items()}
    except Exception as exc:  # noqa: BLE001
        log.warning("china_intel_interest: special flags unavailable (%s)", exc)
        return {}


def build_interest_map(
    tickers: Iterable[str],
    *,
    altdata_by: Mapping[str, Mapping[str, Any]] | None = None,
    radar_by: Mapping[str, Mapping[str, Any]] | None = None,
    special_by: Mapping[str, Mapping[str, Any]] | None = None,
    traj_by: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, dict]:
    """Score every requested ticker.  Returns ``{TICKER: interest record}``.

    Every evidence map is injectable so callers (the board builder, the operator proof,
    tests) can supply what they already hold rather than re-reading it.  Any map left
    ``None`` is loaded from its upstream producer; the price plane is loaded only for
    names a desk actually saw, because a name with no desk evidence falls back to v3
    regardless of what its price did.

    Never raises: a total evidence failure returns every ticker as ``fallback_v3``,
    which orders the board exactly as v3 would have.
    """
    wanted = [str(t).upper().strip() for t in tickers if str(t or "").strip()]
    if altdata_by is None:
        altdata_by = {str(r.get("ticker") or "").upper().strip(): r
                      for r in altdata_rows() if r.get("ticker")}
    if radar_by is None:
        radar_by = radar_by_ticker()
    if special_by is None:
        special_by = special_by_ticker()

    covered = [t for t in wanted if t in altdata_by or t in radar_by]
    if traj_by is None:
        traj_by = _trajectories(covered)

    out: dict[str, dict] = {}
    for ticker in wanted:
        out[ticker] = interest_score(
            altdata_row=altdata_by.get(ticker),
            radar_row=radar_by.get(ticker),
            special_flags=special_by.get(ticker),
            traj=(traj_by or {}).get(ticker),
        )
    return out


def _trajectories(tickers: Iterable[str]) -> dict[str, dict]:
    """Per-name CSI300-relative price trajectories, via the hub's price reader.

    Measured 2026-08-15: ~0.7 ms/name over the CN close panel, so the full ~1.7k
    candidate set costs ~1.2s on the render path.  ``{}`` on any failure — every
    affected name then takes the ``no_edge_evidence`` fallback rather than a
    manufactured edge.
    """
    tickers = list(tickers)
    if not tickers:
        return {}
    try:
        from engine import china_intel_hub as hub
        closes, bench = hub._load_closes_and_benchmark()
        out: dict[str, dict] = {}
        for ticker in tickers:
            traj = hub._price_trajectory(ticker, closes, bench)
            if traj:
                out[ticker] = traj
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("china_intel_interest: price trajectories unavailable (%s)", exc)
        return {}


def coverage(interest_map: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Honest coverage receipt for the ordering contract.

    ``measured`` names are ordered by their interest score; ``fallback_v3`` names keep
    their v3 priority.  A board where every name falls back is a board ordered exactly
    as v3 ordered it, and this receipt is how that is visible rather than silent.
    """
    total = len(interest_map)
    measured = [r for r in interest_map.values() if r.get("basis") == BASIS_MEASURED]
    reasons: dict[str, int] = {}
    for record in interest_map.values():
        if record.get("basis") != BASIS_MEASURED:
            key = str(record.get("unavailable_reason") or "unknown")
            reasons[key] = reasons.get(key, 0) + 1
    scores = sorted(float(r["score"]) for r in measured if r.get("score") is not None)
    return {
        "definition": INTEREST_DEFINITION,
        "n_rows": total,
        "n_measured": len(measured),
        "n_fallback_v3": total - len(measured),
        "measured_rate_pct": round(100.0 * len(measured) / total, 1) if total else 0.0,
        "fallback_reasons": dict(sorted(reasons.items())),
        "score_min": scores[0] if scores else None,
        "score_median": scores[len(scores) // 2] if scores else None,
        "score_max": scores[-1] if scores else None,
    }
