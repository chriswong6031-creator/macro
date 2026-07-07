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
  • oi_delta_clusters: derived from day-over-day gex_<KEY>.parquet history (stored
    by lib.store); empty lists when history is unavailable or too short.  The
    per-name parquet carries 'spot' + 'net_gex_bn' per date — the by-strike history
    is NOT stored (the daily collector only writes the summary row), so oi_delta
    computation falls back to empty lists with a note.
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

# ── oi_delta fallback note ────────────────────────────────────────────────────
_OI_DELTA_NOTE = (
    "Day-over-day per-strike OI history not stored by the daily collector; "
    "per-strike oi_delta_clusters require the Cboe strike-level parquet — "
    "falling back to empty lists."
)


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


# ── oi_delta clusters (from history parquet) ──────────────────────────────────

def _oi_delta_clusters(key: str) -> dict:
    """Attempt to derive new_oi / exit_oi clusters from per-strike day-over-day history.

    The daily Cboe collector writes SUMMARY-level rows to data/cboe/gex_<KEY>.parquet
    (columns: spot, net_gex_bn, …) — it does NOT write per-strike OI snapshots.
    Without per-strike historical data we cannot compute strike-level OI deltas.

    Returns {"new_oi": [], "exit_oi": [], "note": <str>} when history is unavailable
    or the parquet lacks per-strike OI columns.  A future collector upgrade that writes
    a strike-level table would plug in here.
    """
    return {"new_oi": [], "exit_oi": [], "note": _OI_DELTA_NOTE}


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

    # ── oi_delta_clusters ─────────────────────────────────────────────────────
    oi_delta_clusters = _oi_delta_clusters(key)

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
        "oi_delta_clusters": {
            "new_oi": oi_delta_clusters.get("new_oi", []),
            "exit_oi": oi_delta_clusters.get("exit_oi", []),
        },
        "regime_passport": regime_passport,
        "authority_tier": "display",
        "reliability": {
            "levels": "display-only-until-gate",
            "regime": "assumption-signed",
            "note": (
                "Direction soft — sign not NBBO-confirmed. "
                "All levels are descriptive maps, not forecasts. "
                + ("Regime noise-floor hit — RANGE used as safe fallback. "
                   if noise_floor_hit else "")
            ),
        },
    }

    return payload
