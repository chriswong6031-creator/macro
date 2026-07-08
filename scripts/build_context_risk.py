"""scripts/build_context_risk.py — Personality risk lens (W3, nw-context-intelligence).

DISPLAY-ONLY. This artifact ANNOTATES surfaces; it may never rank, size, or gate
any decision surface (Article 2, R-CI1, R-CI7). Numbers always carry n and the
survivorship watermark. The word "validated" appears nowhere in program surfaces.

Writes (atomic temp+rename per build_covariance_spine pattern):
    data/neuralweb/context_risk.json         (primary; git-committed)
    site/neuralwebdata/context_risk.json     (site mirror; same content)

Always exits 0. Never crashes the cortex job.

Usage:
    python -m scripts.build_context_risk [--root REPO_ROOT]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("build_context_risk")

# ---------------------------------------------------------------------------
# Authoritative constants — transcribed from field guide §1/§3
# ---------------------------------------------------------------------------
from engine.neuralweb.context_risk_constants import (  # noqa: E402
    ARCHETYPE_FINGERPRINTS,
    ARCHETYPE_QUAD_MEDIAN,
    ARCHETYPE_QUAD_P10,
    ARCHETYPE_LIQUIDITY_MEDIAN,
    MIN_N_ADEQUATE,
)

_SURVIVORSHIP_WATERMARK = (
    "223-name survivorship-biased deep corpus (larger/established names); "
    "commodity_sensitive absent; small-n caveat on quality_compounder (3 tickers) "
    "and dividend_defensive (4 tickers). Do not generalize to full 1,722-name universe."
)

_AUTHORITY_BLOCK = {
    "tier": "display",
    "horizon_role": "context",
    "weights": "none",
    "scored_path_surfaces": [],
    "article2_law": (
        "This artifact ANNOTATES and may never rank, size, gate, or raise attention "
        "floors (Article 2, R-CI1, R-CI7). Promotion to authority requires "
        "pre-registration and a post-registration gauntlet."
    ),
    "survivorship_watermark": _SURVIVORSHIP_WATERMARK,
}


def _repo_root(given: Path | None) -> Path:
    if given is not None:
        return given.resolve()
    return Path(__file__).resolve().parent.parent


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON atomically via temp file + rename (covariance_spine pattern)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".tmp_{path.name}_",
        suffix=".json",
        delete=False,
    ) as tf:
        tf.write(text)
        tmp_path = Path(tf.name)
    tmp_path.replace(path)


# ---------------------------------------------------------------------------
# Input loaders — all fail-open
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict | None:
    """Load JSON from path; return None on any failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("build_context_risk: failed to load %s — %s", path, exc)
        return None


def _load_standouts(root: Path) -> dict:
    """Load us_standouts.json; return empty dict on failure."""
    path = root / "site" / "factordata" / "us_standouts.json"
    d = _load_json(path)
    if not isinstance(d, dict):
        return {}
    return {
        "buy": d.get("buy") or [],
        "watch": d.get("watch") or [],
        "laggards": d.get("laggards") or [],
        "as_of": d.get("as_of"),
        "_path": str(path),
    }


def _load_personality(root: Path) -> dict:
    """Load stock_personality.json; return empty dict on failure."""
    path = root / "site" / "factordata" / "stock_personality.json"
    d = _load_json(path)
    if not isinstance(d, dict):
        return {}
    return {
        "per_ticker": d.get("per_ticker") or {},
        "label_distributions": d.get("label_distributions") or {},
        "n_tickers": d.get("n_tickers"),
        "as_of": d.get("as_of"),
        "_path": str(path),
    }


def _load_regime(root: Path) -> dict:
    """Load site/regime_timeline.json; return current quad+liq; fail-open."""
    path = root / "site" / "regime_timeline.json"
    d = _load_json(path)
    if not isinstance(d, dict):
        return {}
    dates = d.get("dates") or []
    quads = d.get("quad") or []
    liqs = d.get("liq") or []
    if not dates:
        return {"as_of": None, "quad": None, "liq": None}
    last_idx = len(dates) - 1
    return {
        "as_of": dates[last_idx],
        "quad": quads[last_idx] if last_idx < len(quads) else None,
        "liq": liqs[last_idx] if last_idx < len(liqs) else None,
        "_path": str(path),
    }


# ---------------------------------------------------------------------------
# Composition helpers
# ---------------------------------------------------------------------------

def _archetype_of(ticker_data: dict) -> str | None:
    """Return archetype label for a ticker's personality record; None if absent."""
    return ticker_data.get("arch")


def _compute_composition(
    members: list[dict],
    per_ticker: dict,
    universe_label_dist: dict,
    universe_total: int,
) -> dict:
    """Compute archetype/chart share for members and ratio vs universe.

    Returns:
        {
          "n_members": int,
          "n_unlabeled": int,
          "archetype": {<arch>: {"member_share": float, "universe_share": float, "ratio": float, "n": int}, ...},
          "chart": {...same shape...},
          "unlabeled_tickers": [str, ...],
        }
    """
    member_tickers = [m.get("ticker") for m in members if m.get("ticker")]
    n_members = len(member_tickers)

    arch_counter: Counter = Counter()
    chart_counter: Counter = Counter()
    unlabeled: list[str] = []

    for ticker in member_tickers:
        rec = per_ticker.get(ticker) or {}
        arch = rec.get("arch")
        charts = rec.get("chart") or []
        if arch:
            arch_counter[arch] += 1
        elif not arch and not charts:
            unlabeled.append(ticker)
        # Use first chart label if arch is missing too
        if not arch:
            if charts:
                chart_counter[charts[0]] += 1
            else:
                unlabeled.append(ticker) if ticker not in unlabeled else None
        else:
            if charts:
                chart_counter[charts[0]] += 1

    arch_total = sum(arch_counter.values()) or 1
    chart_total = sum(chart_counter.values()) or 1

    # Universe shares
    univ_arch_dist = universe_label_dist.get("archetype") or {}
    univ_chart_dist = universe_label_dist.get("chart_personality") or {}
    univ_arch_total = sum(univ_arch_dist.values()) or 1
    univ_chart_total = sum(univ_chart_dist.values()) or 1

    def _ratio(member_share: float, univ_share: float) -> float | None:
        if univ_share == 0:
            return None
        return round(member_share / univ_share, 3)

    arch_result: dict = {}
    all_arches = set(arch_counter) | set(univ_arch_dist)
    for arch in all_arches:
        m_n = arch_counter.get(arch, 0)
        m_share = round(m_n / arch_total, 4)
        u_share = round(univ_arch_dist.get(arch, 0) / univ_arch_total, 4)
        arch_result[arch] = {
            "member_n": m_n,
            "member_share": m_share,
            "universe_share": u_share,
            "ratio": _ratio(m_share, u_share),
        }

    chart_result: dict = {}
    all_charts = set(chart_counter) | set(univ_chart_dist)
    for chart in all_charts:
        m_n = chart_counter.get(chart, 0)
        m_share = round(m_n / chart_total, 4)
        u_share = round(univ_chart_dist.get(chart, 0) / univ_chart_total, 4)
        chart_result[chart] = {
            "member_n": m_n,
            "member_share": m_share,
            "universe_share": u_share,
            "ratio": _ratio(m_share, u_share),
        }

    return {
        "n_members": n_members,
        "n_unlabeled": len(set(unlabeled)),
        "archetype": arch_result,
        "chart": chart_result,
        "unlabeled_tickers": sorted(set(unlabeled)),
    }


def _weighted_risk_profile(
    composition: dict,
    n_members: int,
) -> dict:
    """Compute equal-weight aggregation of per-archetype fingerprints.

    Weights each archetype by its member share. Returns weighted medians of:
    vol, beta, maxdd, pct_never_recover_1yr, and dispersion (disp).
    """
    arch_shares = composition.get("archetype") or {}

    # Only compute over labeled archetypes that appear in fingerprint table
    weighted_vol = 0.0
    weighted_beta = 0.0
    weighted_maxdd = 0.0
    weighted_pnr = 0.0
    weighted_disp = 0.0
    weight_sum = 0.0
    n_archetypes_used = 0

    for arch, cell in arch_shares.items():
        fp = ARCHETYPE_FINGERPRINTS.get(arch)
        if fp is None:
            continue
        share = cell.get("member_share", 0.0)
        if share <= 0:
            continue
        weighted_vol += fp["vol_med"] * share
        weighted_beta += fp["beta_med"] * share
        weighted_maxdd += fp["maxdd_med"] * share
        weighted_pnr += fp["pct_never_recover_1yr"] * share
        weighted_disp += fp["disp"] * share
        weight_sum += share
        n_archetypes_used += 1

    if weight_sum == 0:
        return {
            "available": False,
            "note": "no labeled archetype members; fingerprint aggregation not possible",
        }

    # Normalise by actual labeled weight (may be <1 if some unlabeled)
    return {
        "available": True,
        "n_archetypes_used": n_archetypes_used,
        "labeled_weight_sum": round(weight_sum, 4),
        "note": (
            "equal-weight aggregation of per-archetype fingerprints weighted by "
            "archetype share among board members; survivorship-biased deep corpus constants"
        ),
        "weighted_vol_med": round(weighted_vol / weight_sum, 4),
        "weighted_beta_med": round(weighted_beta / weight_sum, 4),
        "weighted_maxdd_med": round(weighted_maxdd / weight_sum, 4),
        "weighted_pct_never_recover_1yr": round(weighted_pnr / weight_sum, 4),
        "weighted_disp": round(weighted_disp / weight_sum, 4),
        "label_trust_note": (
            "Weighted dispersion reflects mix of high-trust (financial disp=0.162) "
            "and low-trust (speculative_unprofitable disp=0.544) types; "
            "high weighted_disp means label-level statistics explain little per-name outcome"
        ),
    }


def _regime_conditional_read(
    composition: dict,
    quad: str | None,
    liq: str | None,
) -> dict:
    """Weighted median 21d fwd and P10 tail for the current quad (quad-only read).

    Regime read uses ARCHETYPE_QUAD_MEDIAN and ARCHETYPE_QUAD_P10 (quad-only matrix).
    The liquidity state is recorded as context but does NOT condition the weighted
    statistics — per-archetype liquidity-conditioned medians (ARCHETYPE_LIQUIDITY_MEDIAN)
    are available in constants but are not yet aggregated in this block.

    Only uses cells the field guide marks as adequate (n >= MIN_N_ADEQUATE).
    Inadequate cells print insufficient_n.

    P10 disclaimer: weighted_p10_21d is a per-type share-weighted average of marginal
    worst-decile returns; NOT a portfolio P10 — diversification and cross-type
    correlation are not modeled.

    Returns:
        {
          "quad": str | None,
          "liq": str | None,
          "weighted_median_21d": float | None,
          "weighted_p10_21d": float | None,
          "p10_interpretation": str,   # fixed disclaimer (F2)
          "covered_weight": float | None,  # fraction of board weight over adequate cells (F6)
          "note": str,
          "per_archetype": {...},
        }
    """
    arch_shares = composition.get("archetype") or {}

    if not quad:
        return {
            "available": False,
            "quad": None,
            "liq": None,
            "note": "quad unknown — regime-conditional read not available",
        }

    per_arch: dict = {}
    w_med_sum = 0.0
    w_p10_sum = 0.0
    weight_sum = 0.0
    p10_weight_sum = 0.0  # F1: separate denominator for P10 — only incremented when p10_val is not None
    total_board_weight = sum(
        cell.get("member_share", 0.0)
        for cell in arch_shares.values()
        if cell.get("member_share", 0.0) > 0
    )
    covered_weight = 0.0  # F6: fraction of board weight over adequate cells
    insufficient_cells: list[str] = []

    for arch, cell in arch_shares.items():
        share = cell.get("member_share", 0.0)
        if share <= 0:
            continue
        if arch not in ARCHETYPE_QUAD_MEDIAN:
            per_arch[arch] = {"note": "not_in_field_guide", "share": share}
            continue

        quad_cell = ARCHETYPE_QUAD_MEDIAN[arch].get(quad)
        p10_val = ARCHETYPE_QUAD_P10.get(arch, {}).get(quad)

        if quad_cell is None:
            per_arch[arch] = {"note": f"quad_{quad}_not_in_table", "share": share}
            continue

        n = quad_cell.get("n", 0)
        if n < MIN_N_ADEQUATE:
            per_arch[arch] = {
                "note": "insufficient_n",
                "n": n,
                "min_n_adequate": MIN_N_ADEQUATE,
                "share": share,
            }
            insufficient_cells.append(arch)
            continue

        med = quad_cell.get("med")
        per_arch[arch] = {
            "median_21d": med,
            "p10_21d": p10_val,
            "n": n,
            "share": share,
        }
        if med is not None:
            w_med_sum += med * share
            weight_sum += share
        if p10_val is not None:
            w_p10_sum += p10_val * share
            p10_weight_sum += share  # F1: track separately from median weight_sum
        covered_weight += share  # F6: this cell is adequate

    # Liquidity context (table 3 in field guide — quad-only; liquidity-conditioned
    # per-archetype median available in ARCHETYPE_LIQUIDITY_MEDIAN but not computed
    # here because the world_state context block carries only the quad × liquidity
    # regime read; a dedicated liquidity-conditioned table is not yet wired)
    liq_note = None
    if liq and liq in ("expanding", "neutral", "contracting"):
        liq_note = (
            f"Current liquidity state: {liq}. "
            "Regime read is quad-only (ARCHETYPE_QUAD_MEDIAN); "
            "per-archetype liquidity-conditioned medians (ARCHETYPE_LIQUIDITY_MEDIAN) "
            "are available in constants but not yet aggregated in this block."
        )

    # F6: covered_weight fraction
    covered_weight_fraction = (
        round(covered_weight / total_board_weight, 4) if total_board_weight > 0 else None
    )

    # F2: disclaimer note required on the regime_conditional block
    _p10_disclaimer = (
        "per-type share-weighted average of marginal worst-decile returns; "
        "NOT a portfolio P10 — diversification and cross-type correlation are not modeled."
    )

    result: dict = {
        "available": weight_sum > 0,
        "quad": quad,
        "liq": liq,
        "n_min_adequate_threshold": MIN_N_ADEQUATE,
        "n_insufficient_cells": len(insufficient_cells),
        "per_archetype": per_arch,
        "note": (
            "Weighted median/P10 computed only over archetype cells with n >= "
            f"{MIN_N_ADEQUATE} (field guide adequacy floor). "
            f"{len(insufficient_cells)} cells printed as insufficient_n."
        ),
        "p10_interpretation": _p10_disclaimer,  # F2: fixed disclaimer
        "covered_weight": covered_weight_fraction,  # F6
    }

    if weight_sum > 0:
        result["weighted_median_21d"] = round(w_med_sum / weight_sum, 4)
        # F1: divide by p10_weight_sum (not weight_sum) so None P10 cells don't dilute
        # F3: condition on p10_weight_sum > 0 (not != 0, mirroring the median guard)
        result["weighted_p10_21d"] = (
            round(w_p10_sum / p10_weight_sum, 4) if p10_weight_sum > 0 else None
        )
    else:
        result["weighted_median_21d"] = None
        result["weighted_p10_21d"] = None
        result["note"] += " All archetype cells had insufficient_n."

    if liq_note:
        result["liquidity_context"] = liq_note

    if covered_weight_fraction is not None and covered_weight_fraction < 1.0:
        result["covered_weight_note"] = (
            f"Only {covered_weight_fraction:.0%} of board archetype weight falls on "
            "cells with adequate n; weighted statistics cover a partial board."
        )

    return result


def _compute_flags(
    members: list[dict],
    per_ticker: dict,
) -> dict:
    """Compute boolean risk flags across board members."""
    n_members = len(members)
    if n_members == 0:
        return {"n_members": 0, "note": "no members"}

    n_tinderbox = 0
    n_negative_gamma_trend = 0
    n_event_override = 0
    n_distribution_mode = 0
    n_unlabeled_arch = 0

    for m in members:
        ticker = m.get("ticker")
        if not ticker:
            continue
        rec = per_ticker.get(ticker) or {}
        own = rec.get("own") or []
        modes = rec.get("modes") or []
        if "short_interest_tinderbox" in own:
            n_tinderbox += 1
        if "negative_gamma_trend" in own:
            n_negative_gamma_trend += 1
        if "event_override" in modes:
            n_event_override += 1
        if "distribution" in modes:
            n_distribution_mode += 1
        if not rec.get("arch"):
            n_unlabeled_arch += 1

    return {
        "n_members": n_members,
        "n_tinderbox": n_tinderbox,
        "n_negative_gamma_trend": n_negative_gamma_trend,
        "n_event_override": n_event_override,
        "n_distribution_mode": n_distribution_mode,
        "n_unlabeled_arch": n_unlabeled_arch,
        "tinderbox_share": round(n_tinderbox / n_members, 4),
        "negative_gamma_trend_share": round(n_negative_gamma_trend / n_members, 4),
        "event_override_share": round(n_event_override / n_members, 4),
        "distribution_mode_share": round(n_distribution_mode / n_members, 4),
        "unlabeled_arch_share": round(n_unlabeled_arch / n_members, 4),
    }


def _top_overweights(composition: dict, n: int = 3) -> list[dict]:
    """Return top-n overweighted archetypes by ratio (ratio > 1 = overweight vs universe)."""
    arch_cells = composition.get("archetype") or {}
    ranked = sorted(
        [
            (arch, cell)
            for arch, cell in arch_cells.items()
            if cell.get("ratio") is not None and cell.get("ratio", 0) > 0
            and cell.get("member_n", 0) > 0
        ],
        key=lambda kv: kv[1].get("ratio", 0),
        reverse=True,
    )
    return [
        {
            "archetype": arch,
            "ratio": cell.get("ratio"),
            "member_share": cell.get("member_share"),
            "universe_share": cell.get("universe_share"),
            "member_n": cell.get("member_n"),
        }
        for arch, cell in ranked[:n]
    ]


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_context_risk(root: Path | str | None = None) -> dict:
    """Compute the full personality risk lens artifact.

    Returns the payload dict. Always returns a valid dict (fail-open).
    """
    repo = Path(root).resolve() if root else Path(__file__).resolve().parent.parent
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")

    # Load inputs
    standouts = _load_standouts(repo)
    personality = _load_personality(repo)
    regime = _load_regime(repo)

    per_ticker = personality.get("per_ticker") or {}
    label_dist = personality.get("label_distributions") or {}

    # Universe total for composition ratios
    univ_arch_dist = label_dist.get("archetype") or {}
    universe_total = sum(univ_arch_dist.values()) or 0

    # Missing inputs → degrade gracefully
    missing_inputs: list[str] = []
    if not standouts:
        missing_inputs.append("site/factordata/us_standouts.json")
    if not per_ticker:
        missing_inputs.append("site/factordata/stock_personality.json")
    if not regime:
        missing_inputs.append("site/regime_timeline.json")

    available = len(missing_inputs) == 0

    buy_members = standouts.get("buy") or []
    all_members = (
        buy_members
        + (standouts.get("watch") or [])
        + (standouts.get("laggards") or [])
    )

    # Compose sections
    board_composition = _compute_composition(buy_members, per_ticker, label_dist, universe_total) if available else {}
    all_lanes_composition = _compute_composition(all_members, per_ticker, label_dist, universe_total) if available else {}
    universe_composition = _compute_composition(
        [{"ticker": t} for t in per_ticker],
        per_ticker,
        label_dist,
        universe_total,
    ) if available else {}

    quad = regime.get("quad")
    liq = regime.get("liq")

    board_risk_profile = _weighted_risk_profile(board_composition, len(buy_members)) if available else {"available": False, "note": "missing inputs"}
    board_regime_read = _regime_conditional_read(board_composition, quad, liq) if available else {"available": False, "note": "missing inputs"}
    board_flags = _compute_flags(buy_members, per_ticker) if available else {"note": "missing inputs"}
    board_top_overweights = _top_overweights(board_composition) if available else []

    all_lanes_risk_profile = _weighted_risk_profile(all_lanes_composition, len(all_members)) if available else {"available": False, "note": "missing inputs"}
    all_lanes_regime_read = _regime_conditional_read(all_lanes_composition, quad, liq) if available else {"available": False, "note": "missing inputs"}
    all_lanes_flags = _compute_flags(all_members, per_ticker) if available else {"note": "missing inputs"}

    payload = {
        "schema": "neuralweb.context_risk.v1",
        "as_of": now_str,
        "display_only": True,
        "available": available,
        "authority": _AUTHORITY_BLOCK,
        "inputs": {
            "us_standouts_as_of": standouts.get("as_of"),
            "stock_personality_as_of": personality.get("as_of"),
            "regime_as_of": regime.get("as_of"),
            "n_personality_tickers": personality.get("n_tickers"),
        },
        "missing_inputs": missing_inputs,
        "regime_context": {
            "quad": quad,
            "liq": liq,
            "as_of": regime.get("as_of"),
        },
        "board_buy_lane": {
            "n_members": len(buy_members),
            "composition": board_composition,
            "weighted_risk_profile": board_risk_profile,
            "regime_conditional": board_regime_read,
            "flags": board_flags,
            "top_overweights": board_top_overweights,
        },
        "all_lanes": {
            "n_members": len(all_members),
            "composition": all_lanes_composition,
            "weighted_risk_profile": all_lanes_risk_profile,
            "regime_conditional": all_lanes_regime_read,
            "flags": all_lanes_flags,
        },
        "universe": {
            "n_members": len(per_ticker),
            "composition": universe_composition,
            "note": (
                "Universe composition = all tickers in stock_personality.json per_ticker; "
                "risk profile and regime read not computed for universe (reference denominator only)"
            ),
        },
        "honesty": {
            "survivorship_watermark": _SURVIVORSHIP_WATERMARK,
            "label_trust_note": (
                "Dispersion within archetype-year varies > 3x across types (speculative_unprofitable "
                "0.544 vs financial 0.162). High-dispersion type statistics describe a distribution "
                "of outcomes, not a prediction for any specific name."
            ),
            "constants_source": "engine/neuralweb/context_risk_constants.py (transcribed from STOCK_PERSONALITY_FIELD_GUIDE.md 2026-07-07)",
            "as_of_note": "n counts are from the 223-name deep corpus study (FY2009-2026); they are NOT the current board n",
        },
    }

    if not available:
        log.warning(
            "build_context_risk: available=False due to missing inputs: %s",
            missing_inputs,
        )

    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build nw-context-intelligence W3 personality risk lens (display-only)."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repo root (default: auto-detected from script location).",
    )
    args = parser.parse_args(argv)
    root = _repo_root(args.root)

    try:
        payload = build_context_risk(root=root)
    except Exception as exc:  # noqa: BLE001
        log.error("build_context_risk: build failed — %s", exc)
        # Write fail-open artifact so world_state can still read a valid JSON
        payload = {
            "schema": "neuralweb.context_risk.v1",
            "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
            "display_only": True,
            "available": False,
            "authority": _AUTHORITY_BLOCK,
            "missing_inputs": ["build_failed"],
            "error": str(exc),
        }

    data_path = root / "data" / "neuralweb" / "context_risk.json"
    site_path = root / "site" / "neuralwebdata" / "context_risk.json"

    try:
        _atomic_write_json(data_path, payload)
        log.info("build_context_risk: wrote %s", data_path)
    except Exception as exc:  # noqa: BLE001
        log.error("build_context_risk: write to data path failed — %s", exc)
        return 0  # non-fatal

    try:
        _atomic_write_json(site_path, payload)
        log.info("build_context_risk: wrote %s", site_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("build_context_risk: site mirror write failed — %s", exc)

    # Summary log line
    board = payload.get("board_buy_lane") or {}
    rr = board.get("regime_conditional") or {}
    quad = (payload.get("regime_context") or {}).get("quad")
    liq = (payload.get("regime_context") or {}).get("liq")
    n_board = board.get("n_members", 0)
    wp10 = rr.get("weighted_p10_21d")
    wmed = rr.get("weighted_median_21d")
    top_ow = board.get("top_overweights") or []
    top_ow_str = ", ".join(
        f"{x['archetype']}×{x['ratio']}" for x in top_ow[:3]
    ) if top_ow else "n/a"
    log.info(
        "build_context_risk: n_board=%d quad=%s liq=%s wmed21d=%s wp10_21d=%s top_overweights=[%s]",
        n_board, quad, liq, wmed, wp10, top_ow_str,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
