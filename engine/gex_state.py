"""engine/gex_state.py — Package C: GEX Structure State emitter.

Derives options_structure.gex_state/v1 dicts from data the gex board build ALREADY
computes: per-strike net GEX (via gex_model.build_model output), gamma flip,
call/put walls, magnet, max_pain, spot, and the per-name history parquets written by
the Cboe collector.

DESIGN CHOICES (documented here because some thresholds are OURS):
  • 6-state classifier thresholds: faithfully copied from gex_spec.md §6.2.
    nearFlip = dist < 0.2% of spot; closeFlip = dist < 0.5% of spot.
    Stability ratio (posGex / (posGex + |negGex|)) computed over strikes within ±20%
    of spot, matching the spec exactly.
  • Noise-floor guard (spec §6.1): if totalAbs < max(1000, spot * 100), returns
    gamma_regime="RANGE" with a warn flag rather than crashing — OURS.
  • pin_probability: documented heuristic from gex_spec §7.4. Uses the per-strike
    OI concentration model from the walls ladder (call_oi + put_oi per strike) and
    atm-proximity weighting.  Returns None for thin_chain / no_options tier.
  • cascade_trigger / upside_trigger: 75th-percentile intensity gate on negative /
    positive GEX strikes (spec §6.4). Returns None when there are fewer than 4
    candidate strikes (OURS — avoids spurious single-strike triggers).
  • gravity: implemented as spec §6.5 exactly.
  • stability_pct: computed from the walls ladder's per-strike net_mn values,
    filtered to strikes within ±20% of spot.
  • oi_delta_clusters: LIT as of the OIP E3 wave (2026-07-29) from the per-strike
    Polygon chain snapshots (data/polygon_gex/chains/{date}.parquet, stored since
    2026-06-15), NOT from the Cboe gex_<KEY>.parquet summary history — that store
    only ever carried 'spot' + 'net_gex_bn' per date and has no per-strike rows.
    Matched-contract day-over-day open-interest change, session-filtered, with a
    same-vintage refusal and vintage stamps.  All of that lives in
    engine/positioning_persistence.py; this module only shapes the payload.  Names
    outside the Polygon universe (SPX, NDX, RUT, GLD, TLT, HYG, NFLX, BABA, UBER,
    GME, ARKK among the board's keys) still get empty lists plus an honest note.
  • wall_persistence / net_gex_pctile / deep_history: additive OIP E3 fields —
    how long the heaviest open-interest strike either side of the price has held,
    where today's net dealer gamma sits in the name's OWN stored daily record, and
    the window/spread of the multi-year index rebuild for the four index ETFs it
    covers.  Young windows and staleness are printed in plain words, never hidden.
  • regime_passport: propagated verbatim from gex_engine._gamma_regime_passport via
    gex_model.build_model → summary['regime_passport'] → compute_gex_state source_passport.
    Falls back to _make_regime_passport (identical logic, basis='assumption') when the
    build_model caller omits it (test stubs / legacy paths).

EPISTEMIC LAWS (binding):
  • No "validated" wording anywhere in this module.
  • authority_tier='display' always (Package A contract §1).
  • LLMs may only de-escalate / narrate — never originate signals or escalations.
  • A thin_chain or no_options tier MUST NOT crash — returns None for that name,
    which the caller (build_gex_board) skips gracefully.

Package A contract (research/OPTIONS_SENSOR_CONTRACT.md) §1 governs the schema.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

# Index/ETF set — mirrors gex_engine._INDEX_PRODUCTS
_INDEX_PRODUCTS = frozenset({"SPX", "SPY", "QQQ", "NDX", "IWM", "RUT", "VIX", "DIA", "SPXW"})

# ── regime classifier thresholds (spec §6.2, verbatim) ───────────────────────
_NEAR_FLIP_PCT = 0.002   # |dist_to_flip_pct| / 100 < 0.2%
_CLOSE_FLIP_PCT = 0.005  # |dist_to_flip_pct| / 100 < 0.5%

# ── noise floor for the stability ratio (spec §6.1) ──────────────────────────
# If total absolute GEX within ±20% of spot is below this, the classifier
# returns RANGE as a safe fallback and sets a regime_noise_floor=True reliability flag.
# OURS: spec says UNKNOWN; we map that to RANGE + flag to avoid a 7th regime value
# that the schema validator would reject.
# Spec §6.1: max(1000, spot * 100) in raw dollars = max(0.001, spot * 100 / 1e6) in $mn.
# The constant term is 0.001 $mn ($1,000) — NOT 1.0 $mn ($1,000,000).
_NOISE_FLOOR_MULTIPLIER = 100.0  # noise_floor = max(0.001, spot * _NOISE_FLOOR_MULTIPLIER / 1e6)

# ── oi_delta hard-degrade note (only when the derivation itself is unavailable) ──
# The per-state honest notes live in engine/positioning_persistence.py; this pair is
# the last resort for "the reader could not run at all" (no pandas, no store dir, an
# unexpected error) so the payload still says something true instead of nothing.
# DUPLICATED ON PURPOSE from engine.positioning_persistence.OI_DELTA_UNAVAILABLE_*: this
# branch fires only when importing that module FAILS (no pandas), so it cannot import the
# strings either. tests/test_positioning_persistence.py pins the two pairs equal.
_OI_DELTA_UNAVAILABLE_EN = (
    "Open-interest change could not be read for this name, so no build or unwind "
    "strikes are shown."
)
_OI_DELTA_UNAVAILABLE_ZH = "本标的未平仓量变化暂时无法读取，因此不显示新增或平仓行权价。"


# ── regime passport ───────────────────────────────────────────────────────────

def _make_regime_passport(symbol: str | None, source_passport: dict | None = None) -> dict:
    """Copy the regime_passport verbatim from the engine summary when present;
    otherwise rebuild it from first principles (identical logic to
    gex_engine._gamma_regime_passport).

    The fallback uses basis='assumption' to match gex_engine._gamma_regime_passport
    exactly (not 'dealer-short-assumption').  In production the rebuild path should
    rarely fire because gex_model.build_model now propagates regime_passport from
    compute_gex into summary; this fallback exists only for test stubs and legacy callers.
    """
    if source_passport and isinstance(source_passport, dict) and source_passport.get("basis"):
        return dict(source_passport)
    is_index = bool(symbol) and str(symbol).upper() in _INDEX_PRODUCTS
    return {
        "basis": "assumption",
        "structurally_constant": (not is_index) if symbol else None,
        "is_index_product": is_index if symbol else None,
        "verdict": "display-only",
        "note": (
            "dealer long-call/short-put sign is an unobservable assumption; "
            + (
                "single-name gamma regime is a near-constant product attribute, not a "
                "time-varying signal (validator MIN_PER_BUCKET structurally unreachable)"
                if (symbol and not is_index)
                else "even for indices SPY vs SPX can contradict same-day — read as assumption, "
                "not observed"
            )
        ),
    }


# ── 6-state regime classifier (spec §6.2) ────────────────────────────────────

def _classify_regime(
    stability_ratio: float,
    dist_to_flip_abs_pct: float | None,
    flip_known: bool,
) -> str:
    """Faithful implementation of StrikeClassifier.classify() regime logic.

    Parameters
    ----------
    stability_ratio:
        posGex / (posGex + |negGex|) — float in [0, 1].
    dist_to_flip_abs_pct:
        |spot - flip| / spot as a fraction (NOT a percent; 0.01 = 1%).
        None when flip is unknown.
    flip_known:
        True when a valid gamma_flip level was computed.

    Returns one of: PIN | DRIFT | RANGE | TRANSITION | TREND | CASCADE
    """
    near_flip = flip_known and dist_to_flip_abs_pct is not None and dist_to_flip_abs_pct < _NEAR_FLIP_PCT
    close_flip = flip_known and dist_to_flip_abs_pct is not None and dist_to_flip_abs_pct < _CLOSE_FLIP_PCT

    if flip_known and near_flip:
        return "TRANSITION"
    elif stability_ratio > 0.75:
        return "DRIFT"
    elif stability_ratio > 0.65:
        return "PIN"
    elif stability_ratio > 0.55:
        return "RANGE"
    elif flip_known and close_flip and stability_ratio > 0.35:
        return "TRANSITION"
    elif stability_ratio > 0.45:
        return "RANGE"
    elif stability_ratio > 0.30:
        return "TREND"
    else:
        return "CASCADE"


# ── stability ratio (spec §6.1) ───────────────────────────────────────────────

def _stability_from_walls(by_strike: list[dict], spot: float) -> tuple[float | None, float | None, bool]:
    """Compute posGex, negGex, and stability_pct from the walls ladder.

    The walls ladder (gex_model.strike_walls) carries net_mn ($ million) per strike.
    We filter to within ±20% of spot per the spec, then compute the ratio.

    OURS (deviation from spec §6.1): spec sums over ALL strikes within ±20% of spot.
    The input walls.by_strike is produced by gex_model.strike_walls with
    wall_window_pct=0.12 (±12%) and wall_max_strikes=40 (top-40 by absolute dollar-gamma).
    The ±20% filter below is therefore a no-op — the input is already truncated to the
    ±12% heaviest-strike subset.  This means stability_pct is computed over a biased,
    heaviest-strike window that is narrower than the spec prescribes.  The deviation is
    documented here as OURS; sourcing stability from a full ±20% ladder would require
    passing the raw chain through separately and is deferred.

    Returns (stability_pct, stability_ratio, noise_floor_hit).
    """
    if not by_strike or not spot or spot <= 0:
        return None, None, True

    window_lo = spot * 0.80
    window_hi = spot * 1.20
    pos_gex = 0.0
    neg_gex = 0.0

    for row in by_strike:
        k = row.get("K")
        net_mn = row.get("net_mn")
        if k is None or net_mn is None:
            continue
        if k < window_lo or k > window_hi:
            continue
        if net_mn > 0:
            pos_gex += net_mn
        else:
            neg_gex += abs(net_mn)

    total_abs = pos_gex + neg_gex
    # Spec §6.1: max(1000, spot * 100) raw dollars → max(0.001, spot * 100 / 1e6) $mn.
    noise_floor = max(0.001, spot * _NOISE_FLOOR_MULTIPLIER / 1_000_000.0)  # in $mn
    if total_abs < noise_floor:
        return None, None, True  # noise_floor_hit=True

    ratio = pos_gex / total_abs
    stability_pct = round(ratio * 100.0, 1)
    return stability_pct, ratio, False


# ── pin probability (spec §7.4) ───────────────────────────────────────────────

def _pin_probability(by_strike: list[dict], spot: float, max_pain: float | None) -> float | None:
    """Compute a pin-probability heuristic following gex_spec §7.4.

    score_i = (callOI + putOI) * avgGamma / (1 + (|K - spot| / spot * 100)^2)
    probability = min(0.95, bestScore / totalScore)

    We use the by_strike ladder from gex_model which carries call_oi + put_oi and,
    since the gross-gamma fix (PR #1832 / feat/prophet-nightly), also call_gamma_mn
    and put_gamma_mn — the per-side unsigned dollar-gamma per strike aggregated across
    expiries.

    OURS (fidelity restored in feat/prophet-nightly): spec uses avgGamma =
    (callGamma + putGamma) / 2, which is an unsigned aggregate and is highest at
    balanced high-OI strikes (true pin strikes). We now use:
        avg_gamma = (call_gamma_mn + put_gamma_mn) / 2
    directly from the ladder.  When those fields are absent (legacy callers / thin
    stubs that only carry net_mn), we fall back to |net_mn| with an explicit comment
    noting the deviation. The fallback preserves backward-compat; all production paths
    through gex_model.strike_walls emit call_gamma_mn + put_gamma_mn since the same PR.

    Returns None when there are fewer than 3 usable strikes (thin chain guard).
    """
    if not by_strike or not spot or spot <= 0:
        return None

    scores: list[tuple[float, float]] = []  # (score, K)
    for row in by_strike:
        k = row.get("K")
        call_oi = row.get("call_oi") or 0
        put_oi = row.get("put_oi") or 0
        total_oi = call_oi + put_oi
        if k is None or total_oi <= 0:
            continue

        # Prefer spec-faithful gross gamma (call_gamma_mn + put_gamma_mn always >= 0)
        call_gamma_mn = row.get("call_gamma_mn")
        put_gamma_mn = row.get("put_gamma_mn")
        if call_gamma_mn is not None and put_gamma_mn is not None:
            avg_gamma = (call_gamma_mn + put_gamma_mn) / 2.0
        else:
            # Legacy fallback: |net_mn| under-ranks balanced strikes (see old OURS note)
            net_mn = row.get("net_mn")
            if net_mn is None:
                continue
            avg_gamma = abs(net_mn)

        if avg_gamma <= 0:
            continue

        dNorm = abs(k - spot) / (spot * 0.01)  # in units of 1% of spot
        score = (total_oi * avg_gamma) / (1.0 + dNorm ** 2)
        scores.append((score, k))

    if len(scores) < 3:
        return None

    total_score = sum(s for s, _ in scores)
    if total_score <= 0:
        return None

    best_score = max(s for s, _ in scores)
    prob = round(min(0.95, best_score / total_score), 3)
    return prob


# ── gravity (spec §6.5) ───────────────────────────────────────────────────────

def _gravity(by_strike: list[dict], spot: float) -> tuple[str | None, float | None]:
    """Compute gravity direction and gravUpPct following gex_spec §6.5.

    Returns (gravity_direction, gravity_up_pct).
    gravity_direction is "up" | "down" | None (when data absent or balanced).
    """
    if not by_strike or not spot or spot <= 0:
        return None, None

    # Estimate avgStep from the strike ladder spacing
    ks = sorted(r["K"] for r in by_strike if r.get("K") is not None)
    if len(ks) < 2:
        return None, None
    diffs = [ks[i + 1] - ks[i] for i in range(len(ks) - 1)]
    avg_step = sum(diffs) / len(diffs) if diffs else 1.0
    if avg_step <= 0:
        avg_step = 1.0

    pull_up = 0.0
    pull_down = 0.0

    for row in by_strike:
        k = row.get("K")
        net_mn = row.get("net_mn")
        if k is None or net_mn is None or k == spot:
            continue
        dist = abs(k - spot)
        weight = 1.0 / (dist + avg_step)
        if k > spot:
            if net_mn > 0:
                pull_up += net_mn * weight
            else:
                pull_down += (-net_mn) * weight
        else:  # k < spot
            if net_mn < 0:
                pull_down += (-net_mn) * weight
            else:
                pull_up += net_mn * weight

    total = pull_up + pull_down
    if total <= 0:
        return None, None

    grav_up_pct = round(pull_up / total * 100.0)
    grav_down_pct = 100 - grav_up_pct

    if grav_up_pct > 60:
        direction = "up"
    elif grav_down_pct > 60:
        direction = "down"
    else:
        direction = None  # neutral — not emitting "neutral" to match schema (None = neutral)

    return direction, float(grav_up_pct)


# ── cascade / upside triggers (spec §6.4) ────────────────────────────────────

def _triggers(
    by_strike: list[dict],
    spot: float,
    flip: float | None,
    call_wall: float | None,
    put_wall: float | None,
) -> tuple[float | None, float | None]:
    """Cascade trigger (below flip, heaviest negative-GEX strike) and upside trigger
    (above flip, heaviest positive-GEX strike).

    Mirrors spec §6.4:
      intensity = |net| / maxAbsNet
      proximity = 1 / (1 + distToFlip / avgStep)
      score = intensity * (0.6 + proximity * 0.4)
    Gate: 75th-percentile intensity of same-side negative strikes.
    Returns (cascade_trigger, upside_trigger); None when insufficient candidates.

    OURS: require ≥4 candidate strikes for the percentile gate to be meaningful.
    """
    if not by_strike or not spot or spot <= 0:
        return None, None

    ks = sorted(r["K"] for r in by_strike if r.get("K") is not None)
    if len(ks) < 2:
        return None, None
    diffs = [ks[i + 1] - ks[i] for i in range(len(ks) - 1)]
    avg_step = sum(diffs) / len(diffs) if diffs else 1.0
    if avg_step <= 0:
        avg_step = 1.0

    all_abs = [abs(r.get("net_mn") or 0.0) for r in by_strike if r.get("net_mn") is not None]
    max_abs = max(all_abs, default=0.0)
    if max_abs <= 0:
        return None, None

    flip_level = flip if (flip is not None and flip > 0) else spot  # use spot as proxy when unknown

    # ── cascade (below-flip, negative net) ──────────────────────────────────
    cascade_trigger: float | None = None
    neg_below = [r for r in by_strike
                 if r.get("K") is not None and r.get("net_mn") is not None
                 and r["K"] < flip_level and r["net_mn"] < 0]
    if len(neg_below) >= 4:
        intensities = [abs(r["net_mn"]) / max_abs for r in neg_below]
        sorted_int = sorted(intensities)
        gate = sorted_int[int(len(sorted_int) * 0.75)] if len(sorted_int) >= 4 else 0.05
        scored = []
        for r in neg_below:
            if r["K"] == put_wall:
                continue
            intensity = abs(r["net_mn"]) / max_abs
            if intensity < gate:
                continue
            prox = 1.0 / (1.0 + abs(r["K"] - flip_level) / avg_step)
            score = intensity * (0.6 + prox * 0.4)
            scored.append((score, r["K"]))
        if scored:
            cascade_trigger = max(scored, key=lambda x: x[0])[1]

    # ── upside (above-flip, positive net) ────────────────────────────────────
    upside_trigger: float | None = None
    pos_above = [r for r in by_strike
                 if r.get("K") is not None and r.get("net_mn") is not None
                 and r["K"] > flip_level and r["net_mn"] > 0]
    if len(pos_above) >= 4:
        intensities = [abs(r["net_mn"]) / max_abs for r in pos_above]
        sorted_int = sorted(intensities)
        gate = sorted_int[int(len(sorted_int) * 0.75)] if len(sorted_int) >= 4 else 0.05
        scored = []
        for r in pos_above:
            if r["K"] == call_wall:
                continue
            intensity = abs(r["net_mn"]) / max_abs
            if intensity < gate:
                continue
            prox = 1.0 / (1.0 + abs(r["K"] - flip_level) / avg_step)
            score = intensity * (0.6 + prox * 0.4)
            scored.append((score, r["K"]))
        if scored:
            upside_trigger = max(scored, key=lambda x: x[0])[1]

    return cascade_trigger, upside_trigger


# ── oi_delta clusters (from the per-strike chain snapshots) ───────────────────

def _oi_delta_clusters(key: str) -> dict:
    """Matched-contract day-over-day open-interest build / unwind strikes for `key`.

    Delegates to engine.positioning_persistence, which owns the store reads, the
    session filter, the same-vintage refusal and the plain-word notes.  A name the
    Polygon chain store does not cover — or a store that is absent entirely — comes
    back with empty lists and a note saying so; nothing here fabricates a zero.

    Returns {"new_oi": [...], "exit_oi": [...], "prior_snapshot", "latest_snapshot",
    "matched_contracts", "same_vintage", "note_en", "note_zh"}.  The two list keys
    are the pre-existing schema fields and keep their shape.
    """
    try:
        from engine import positioning_persistence as pp  # noqa: PLC0415
        return pp.load().clusters(key)
    except Exception as e:  # noqa: BLE001 — a store problem must never break a payload
        log.warning("gex_state: oi_delta_clusters unavailable for %s: %s", key, e)
        return {"new_oi": [], "exit_oi": [],
                "prior_snapshot": None, "latest_snapshot": None,
                "sessions_apart": None, "sessions_behind": None, "stale": False,
                "matched_contracts": 0, "same_vintage": False, "snapshot_spot": None,
                "note_en": _OI_DELTA_UNAVAILABLE_EN,
                "note_zh": _OI_DELTA_UNAVAILABLE_ZH}


def _spot_divergence(snapshot_spot: float | None, board_spot: float | None,
                     rows: list | None = None) -> tuple[str, str] | None:
    """EN/ZH disclosure when the snapshot source's price differs from the board's.

    Only the payload layer can compute this: the positioning module has the snapshot
    price, this function has the board's `spot`.

    TWO trigger conditions, per the review adjudication:
      * DISTANCE — the two prices differ by more than SPOT_DIVERGENCE_PCT (measured
        2026-07-29 over the 302 roots that emit a payload: median 0.582%, 97 past 2%,
        worst 18.6% — UCTT 77.50 snapshot vs 95.25 board);
      * DIRECTION — a listed strike falls BETWEEN the two prices, so sign(K - snapshot)
        != sign(K - board) and above/below reads the opposite way against the payload's
        own spot. This fires at ANY magnitude: a sign flip breaks the reader's mental
        model regardless of how small the gap is. Measured 99 of 2,259 emitted cluster
        rows are sign-flipped, and the distance threshold alone caught only 77.
    """
    try:
        from engine import positioning_persistence as pp  # noqa: PLC0415
        flip = pp.rows_cross_the_board_price(rows, snapshot_spot, board_spot)
        return pp.spot_divergence_note(snapshot_spot, board_spot, force=flip)
    except Exception as e:  # noqa: BLE001
        log.warning("gex_state: spot divergence note unavailable: %s", e)
        return None


def _wall_persistence(key: str, call_wall: float | None,
                      put_wall: float | None) -> dict | None:
    """How long the heaviest open-interest strike either side of the price has held.

    NOT a persistence count for this payload's call_wall / put_wall: those are
    dollar-gamma walls from the Cboe chain and no store has ever persisted a wall
    LEVEL, so a same-source count for them is not computable.  What IS emitted is the
    OPEN-INTEREST wall from the Polygon per-strike snapshots — signing-free, one source
    on both sides — plus `matches_board_wall` per side so a consumer can see when the
    two readings land on the same strike and when they do not.  Relabelling one as the
    other would be the mixed-source class.

    None when the chain store does not cover the name (the honest null — the field is
    simply absent from the payload rather than carrying a made-up count).
    """
    try:
        from engine import positioning_persistence as pp  # noqa: PLC0415
        block = pp.load().wall_persistence(key)
    except Exception as e:  # noqa: BLE001
        log.warning("gex_state: wall_persistence unavailable for %s: %s", key, e)
        return None
    if block is None:
        return None
    for side, board_level in (("call_side", call_wall), ("put_side", put_wall)):
        s = block.get(side)
        if not isinstance(s, dict):
            continue
        s = dict(s)
        oi_level = s.get("level")
        s["matches_board_wall"] = (
            None if (oi_level is None or board_level is None)
            else bool(abs(float(oi_level) - float(board_level)) < 1e-6))
        s["board_wall"] = (float(board_level) if board_level is not None else None)
        block[side] = s
    return block


def _own_history_percentile(model: dict, net_gex_bn: float | None) -> dict | None:
    """Where today's net dealer gamma sits in the name's OWN stored daily record."""
    try:
        from engine import positioning_persistence as pp  # noqa: PLC0415
        return pp.net_gex_percentile(model.get("history"), net_gex_bn)
    except Exception as e:  # noqa: BLE001
        log.warning("gex_state: net_gex percentile unavailable: %s", e)
        return None


def _deep_history(key: str) -> dict | None:
    """Window + spread of the multi-year index rebuild, for the roots it covers."""
    try:
        from engine import positioning_persistence as pp  # noqa: PLC0415
        return pp.deep_history_context(key)
    except Exception as e:  # noqa: BLE001
        log.warning("gex_state: deep history unavailable for %s: %s", key, e)
        return None


# ── main entry point ──────────────────────────────────────────────────────────

def compute_gex_state(
    model: dict,
    key: str,
    asof: str | None = None,
) -> dict | None:
    """Derive an options_structure.gex_state/v1 dict from a gex_model.build_model output.

    Parameters
    ----------
    model:
        The dict returned by gex_model.build_model() for one underlying.
        Must contain 'summary' and 'walls' keys.
    key:
        The underlying root symbol (e.g. "SPY", "NVDA").
    asof:
        ISO-8601 timestamp string.  If None, uses the current UTC time.

    Returns
    -------
    A dict conforming to options_structure.gex_state/v1, or None if the
    chain is too thin (tier="thin_chain" or "no_options") — caller skips
    gracefully; no crash.

    Thin-chain policy (OURS, documented here):
        tier="thin_chain" → returns None (no emission).
        tier="no_options" → returns None (no emission).
        Rationale: the six-state regime classifier is not reliable with fewer
        than the min_strikes threshold; emitting a RANGE/DRIFT read for a
        name with 4 strikes would mislead consumers.
    """
    if not model:
        return None

    summary = model.get("summary") or {}
    walls = model.get("walls") or {}

    tier = summary.get("tier")
    if tier in ("thin_chain", "no_options", None):
        log.debug("gex_state: %s skipped (tier=%s)", key, tier)
        return None

    spot = summary.get("spot")
    if not spot or spot <= 0:
        log.debug("gex_state: %s skipped (no spot)", key)
        return None

    by_strike = walls.get("by_strike") or []

    # ── stability ratio ───────────────────────────────────────────────────────
    stability_pct, stability_ratio, noise_floor_hit = _stability_from_walls(by_strike, spot)
    if stability_ratio is None:
        stability_ratio = 0.5  # safe fallback for regime classifier

    # ── gamma flip ────────────────────────────────────────────────────────────
    gamma_flip = summary.get("gamma_flip")
    dist_to_flip_pct = summary.get("dist_to_flip_pct")  # signed % (spot-flip)/spot*100
    flip_known = gamma_flip is not None and gamma_flip > 0

    # dist_to_flip_abs_pct: fraction (0.01 = 1% away) for the classifier
    dist_to_flip_abs_fraction: float | None = None
    if dist_to_flip_pct is not None and flip_known:
        dist_to_flip_abs_fraction = abs(dist_to_flip_pct) / 100.0

    # ── regime classification ─────────────────────────────────────────────────
    if noise_floor_hit:
        gamma_regime = "RANGE"
        log.debug("gex_state: %s noise-floor hit → RANGE", key)
    else:
        gamma_regime = _classify_regime(stability_ratio, dist_to_flip_abs_fraction, flip_known)

    # ── walls ─────────────────────────────────────────────────────────────────
    call_wall = walls.get("call_wall")
    put_wall = walls.get("put_wall")

    # ── magnet: use largest_oi from walls (HVL proxy) ────────────────────────
    magnet = walls.get("largest_oi") or summary.get("magnet_up") or summary.get("magnet_down")

    # ── max_pain ──────────────────────────────────────────────────────────────
    max_pain = summary.get("max_pain")

    # ── pin probability ───────────────────────────────────────────────────────
    pin_probability = _pin_probability(by_strike, spot, max_pain)

    # ── gravity ───────────────────────────────────────────────────────────────
    gravity_direction, gravity_up_pct = _gravity(by_strike, spot)

    # ── cascade / upside triggers ─────────────────────────────────────────────
    cascade_trigger, upside_trigger = _triggers(
        by_strike, spot, gamma_flip, call_wall, put_wall
    )

    # ── oi_delta_clusters + OIP E3 positioning persistence ───────────────────
    oi_delta_clusters = _oi_delta_clusters(key)
    wall_persistence = _wall_persistence(key, call_wall, put_wall)
    deep_history = _deep_history(key)

    # ── regime_passport (copy verbatim from engine summary) ──────────────────
    source_passport = summary.get("regime_passport")
    # gex_engine stores it on the compute_gex output; gex_model passes it through via
    # the 'summary' dict if the caller propagated it.  Fall back to rebuilding if absent.
    regime_passport = _make_regime_passport(key, source_passport)

    # ── asof ──────────────────────────────────────────────────────────────────
    if asof is None:
        asof = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    # ── assemble payload ──────────────────────────────────────────────────────
    net_gex_bn = summary.get("net_gex_bn")
    net_gex_pctile = _own_history_percentile(model, net_gex_bn)

    payload: dict[str, Any] = {
        "schema": "options_structure.gex_state/v1",
        "asof": asof,
        "root": str(key).upper(),
        "spot": float(spot) if spot is not None else None,
        "net_gex_bn": float(net_gex_bn) if net_gex_bn is not None else None,
        "gamma_regime": gamma_regime,
        "stability_pct": stability_pct,
        "gamma_flip": float(gamma_flip) if gamma_flip is not None else None,
        "dist_to_flip_pct": float(dist_to_flip_pct) if dist_to_flip_pct is not None else None,
        "call_wall": float(call_wall) if call_wall is not None else None,
        "put_wall": float(put_wall) if put_wall is not None else None,
        "magnet": float(magnet) if magnet is not None else None,
        "max_pain": float(max_pain) if max_pain is not None else None,
        "pin_probability": pin_probability,
        "gravity_direction": gravity_direction,
        "gravity_up_pct": gravity_up_pct,
        "cascade_trigger": float(cascade_trigger) if cascade_trigger is not None else None,
        "upside_trigger": float(upside_trigger) if upside_trigger is not None else None,
        # BACK-COMPAT: new_oi / exit_oi keep their names, position and list shape —
        # they were always present (always empty until the OIP E3 wave lit them).
        # Everything after them is ADDITIVE: vintage stamps + the plain-word EN/ZH
        # pair, so a consumer reading only the two lists is unaffected.
        "oi_delta_clusters": {
            "new_oi": oi_delta_clusters.get("new_oi", []),
            "exit_oi": oi_delta_clusters.get("exit_oi", []),
            "prior_snapshot": oi_delta_clusters.get("prior_snapshot"),
            "latest_snapshot": oi_delta_clusters.get("latest_snapshot"),
            "sessions_apart": oi_delta_clusters.get("sessions_apart"),
            "sessions_behind": oi_delta_clusters.get("sessions_behind"),
            "stale": bool(oi_delta_clusters.get("stale", False)),
            "matched_contracts": oi_delta_clusters.get("matched_contracts", 0),
            "same_vintage": bool(oi_delta_clusters.get("same_vintage", False)),
            # The price the row-level dist_pct values are measured against — the snapshot
            # source's own, NOT this payload's `spot` (which comes from the Cboe chain).
            "snapshot_spot": oi_delta_clusters.get("snapshot_spot"),
            "note_en": oi_delta_clusters.get("note_en"),
            "note_zh": oi_delta_clusters.get("note_zh"),
        },
        "regime_passport": regime_passport,
        "authority_tier": "display",
        "reliability": {
            "levels": "display-only-until-gate",
            "regime": "assumption-signed",
            # Open-interest CHANGE is the signing-free read in this payload: it is a
            # count of contracts, so it carries no dealer-sign assumption at all.
            "oi_delta": "reliable — matched-contract, signing-free open-interest change",
            "note": (
                "Direction soft — sign not NBBO-confirmed. "
                "All levels are descriptive maps, not forecasts. "
                + ("Regime noise-floor hit — RANGE used as safe fallback. "
                   if noise_floor_hit else "")
            ),
        },
    }

    # ── cross-source price disclosure (B1b) ──────────────────────────────────
    # Both positioning blocks measure strike distance and the above/below-price split
    # against the SNAPSHOT source's price (single-source internal consistency), while
    # this payload's top-level `spot` is the Cboe one. When the two diverge materially
    # the block says so in plain words rather than leaving a reader to discover that
    # dist_pct's sign disagrees with (K - spot).
    cluster_rows = (payload["oi_delta_clusters"]["new_oi"]
                    + payload["oi_delta_clusters"]["exit_oi"])
    div = _spot_divergence(oi_delta_clusters.get("snapshot_spot"), spot, cluster_rows)
    if div is not None:
        payload["oi_delta_clusters"]["spot_note_en"] = div[0]
        payload["oi_delta_clusters"]["spot_note_zh"] = div[1]

    # Additive, absent rather than faked when the source does not cover the name.
    if wall_persistence is not None:
        wall_rows = [s for s in (wall_persistence.get("call_side"),
                                 wall_persistence.get("put_side"))
                     if isinstance(s, dict) and s.get("level") is not None]
        wdiv = _spot_divergence(wall_persistence.get("snapshot_spot"), spot,
                                [{"K": s["level"]} for s in wall_rows])
        if wdiv is not None:
            wall_persistence["spot_note_en"] = wdiv[0]
            wall_persistence["spot_note_zh"] = wdiv[1]
        payload["wall_persistence"] = wall_persistence
    if net_gex_pctile is not None:
        payload["net_gex_pctile"] = net_gex_pctile
    if deep_history is not None:
        payload["deep_history"] = deep_history

    return payload
