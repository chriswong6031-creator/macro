"""MRI PR-I — display-only enrichments for the release_forecast.v2 artifact.

Four pure functions called by scripts/build_release_forecast.py after projections
are built. All are fail-open: any exception → return None, caller logs and continues.

BINDINGS (MRI-R15 / MRI-R16 / MRI-R17 / MRI-R22):
  - display_only=True: no field here gates, scores, or sizes any position.
  - No LLM calls, no origination of values.
  - Market-implied read (R16) is NEVER fused into model math — context only.
  - Reaction-sensitivity (R17) is a pure lookup; no regression, no positioning inputs.
  - Expectation read (R22) is NEVER fused into model math — context only.

--------
1. compute_surprise_distribution (MRI-R15)
--------
Given a projection dict (containing quantile fields p10..p90 and surprise_skew.sigma)
and a benchmark median, compute the probability mass of the model's predictive
distribution that falls:
  - ABOVE the inline band top:  p_hot   (hotter than expected)
  - BELOW the inline band bottom: p_cold (cooler than expected)
  - WITHIN the ±0.35σ band:     p_inline

Approximation method (documented per §MRI-R15 spec):
  We model the CDF with a piecewise-linear interpolation through the five empirical
  quantile points:
      (p10, 0.10), (p25, 0.25), (p50, 0.50), (p75, 0.75), (p90, 0.90)
  Beyond the tails we EXTEND the outermost slope linearly, clamped so the CDF
  approaches 0.0 below and 1.0 above; we cap the extension at ±4σ from the
  benchmark median to avoid unbounded extrapolation on heavy-tail quantiles.

  P(X <= x) for x outside [p10, p90] is extrapolated as:
    lower tail: slope = (0.25 - 0.10) / (p25 - p10) applied leftward from p10
    upper tail: slope = (0.90 - 0.75) / (p90 - p75) applied rightward from p90
  Both are clamped to [0.0, 1.0].

  Integration of p_hot, p_cold, p_inline is performed by evaluating the CDF at the
  band boundaries (lo = bench - 0.35σ, hi = bench + 0.35σ):
    p_inline = CDF(hi) - CDF(lo)
    p_cold   = CDF(lo)
    p_hot    = 1.0 - CDF(hi)

  The three values are renormalized to sum exactly to 1.0.

Caveats / limitations:
  - Piecewise-linear CDF with 5 knots is a coarse approximation; the true
    distribution is unknown. Provides directional signal only.
  - Tail extrapolation is sensitive to the slope of the outermost quantile segment.
    If p10≈p25 or p75≈p90, slope can be very steep — the ±4σ cap prevents runaway.
  - The inline band width (±0.35σ) is fixed per §3.4 of the masterplan.

--------
2. get_market_implied_benchmark (MRI-R16)
--------
Reads data/prediction_markets/snapshots.parquet and finds the row(s) for the
configured event_key(s) for CPI / NFP, returning a structured implied-expectation
dict. Returns None if no matching rows exist (snapshots accrue nightly).

Context only — never fed into model math.

--------
3. get_reaction_sensitivity (MRI-R17)
--------
Pure lookup of research/release_playbook/results/playbook_v1.json.
Returns historical market-sensitivity means for h1 hot/cold buckets, 2021plus era.
Prefers regime-conditioned cell if current regime matches and n>=8.

--------
4. compute_expectation_read (MRI-R22)
--------
Given our point forecast, a subset of the benchmark_set that constitutes the
EXPECTATION SET (cleveland_nowcast + market-implied central value from Kalshi/
Polymarket), and sigma_scale_pp, compute whether we are above / below / aligned
with market+nowcast expectations.

Expectation set:
  - cleveland_nowcast (CPI family only)
  - Kalshi implied_median (preferred) or Polymarket 'implied' if numeric

Trend benchmarks (naive_prior, trailing_3m, ar_model) are NOT part of this set.

Read:
  expectation_median = median of available expectation values
  delta_pp           = point - expectation_median
  standardized       = delta_pp / sigma_scale_pp
  tag                = 'above_expectations' if standardized > +0.35
                       'below_expectations' if standardized < -0.35
                       'aligned' otherwise

Returns {tag, delta_pp (4dp), standardized (2dp), expectation_median, sources, n_sources}
or None when:
  - expectation set is empty (no expectation sources available)
  - point is None or sigma_scale_pp is None/zero
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────
_INLINE_HALF_WIDTH_SIGMA = 0.35   # ±σ band per MRI §3.4
_TAIL_SIGMA_CAP = 4.0             # cap tail extension beyond ±4σ from benchmark
_ERA_LABEL = "2021plus"           # exact string used in playbook_v1.json
_REGIME_MIN_N = 8                 # prefer regime cell only if n >= this

# MRI-R33 STALE-ENRICH-1/2: TTL staleness gates for enrichment sources.
# A stale source nulls the field with a stale reason; never silently extrapolates.
_KALSHI_TTL_DAYS = 5              # Kalshi / market-implied ≤5d old else null
_MARKET_IMPLIED_TTL_DAYS = 5      # same rule for Polymarket snapshots


def _check_parquet_staleness(path: Path, ttl_days: float) -> str | None:
    """Return a stale reason string if path is older than ttl_days, else None.

    Checks file mtime; returns None if file is fresh or does not exist
    (caller handles absent file via empty result, not staleness).
    """
    if not path.exists():
        return None  # absence handled by caller (returns None result)
    age_days = (time.time() - path.stat().st_mtime) / 86400.0
    if age_days > ttl_days:
        return (
            f"stale: file last updated {age_days:.1f}d ago "
            f"(TTL={ttl_days}d, MRI-R33 STALE-ENRICH)"
        )
    return None


# ── 1. Surprise distribution (MRI-R15) ────────────────────────────────────────

def _piecewise_cdf(x: float, knots: list[tuple[float, float]]) -> float:
    """Evaluate the piecewise-linear CDF at x.

    knots: sorted list of (value, prob) pairs. Extrapolation beyond the outer
    knots uses the slope of the nearest outer segment, clamped to [0, 1].
    """
    xs = [k[0] for k in knots]
    ps = [k[1] for k in knots]

    # Exact match
    if x <= xs[0]:
        # Left tail: extrapolate leftward using slope of first segment
        if len(xs) >= 2 and (xs[1] - xs[0]) != 0:
            slope = (ps[1] - ps[0]) / (xs[1] - xs[0])
        else:
            slope = 0.0
        return max(0.0, ps[0] + slope * (x - xs[0]))

    if x >= xs[-1]:
        # Right tail: extrapolate rightward using slope of last segment
        if len(xs) >= 2 and (xs[-1] - xs[-2]) != 0:
            slope = (ps[-1] - ps[-2]) / (xs[-1] - xs[-2])
        else:
            slope = 0.0
        return min(1.0, ps[-1] + slope * (x - xs[-1]))

    # Interior: find bracketing segment and interpolate
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            seg_w = xs[i + 1] - xs[i]
            if seg_w == 0:
                return ps[i]
            t = (x - xs[i]) / seg_w
            return ps[i] + t * (ps[i + 1] - ps[i])

    return 0.5  # fallback (should not reach)


def compute_surprise_distribution(
    projection: dict[str, Any],
    benchmark_median: float,
    sigma: float,
) -> dict[str, float] | None:
    """Compute p_hot / p_cold / p_inline from projection quantiles.

    Args:
        projection: dict with keys p10, p25, p50, p75, p90 (all numeric or None).
        benchmark_median: the benchmark median (e.g. median of naive_prior, trailing_3m, etc.)
        sigma: trailing-24-realized-surprise σ (from surprise_skew.sigma).

    Returns:
        {p_hot, p_cold, p_inline} rounded to 2dp, summing to 1.0 ±0.01,
        or None if any required input is missing / invalid.
    """
    try:
        p10 = projection.get("p10")
        p25 = projection.get("p25")
        p50 = projection.get("p50")
        p75 = projection.get("p75")
        p90 = projection.get("p90")

        # Require all five quantiles and sigma
        if any(v is None for v in [p10, p25, p50, p75, p90]):
            return None
        if sigma is None or sigma <= 0:
            return None

        p10, p25, p50, p75, p90 = float(p10), float(p25), float(p50), float(p75), float(p90)
        sigma = float(sigma)
        benchmark_median = float(benchmark_median)

        # Validate quantile ordering (allow small ties from rounding)
        quantiles = [p10, p25, p50, p75, p90]
        for i in range(len(quantiles) - 1):
            if quantiles[i] > quantiles[i + 1] + 1e-9:
                log.debug(
                    "compute_surprise_distribution: quantiles not monotone %s > %s",
                    quantiles[i], quantiles[i + 1],
                )
                return None

        # Build knots
        knots: list[tuple[float, float]] = [
            (p10, 0.10),
            (p25, 0.25),
            (p50, 0.50),
            (p75, 0.75),
            (p90, 0.90),
        ]

        # Inline band boundaries: ±0.35σ around benchmark median
        half = _INLINE_HALF_WIDTH_SIGMA * sigma
        lo = benchmark_median - half
        hi = benchmark_median + half

        # Cap tail evaluation at ±4σ from benchmark to avoid wild extrapolation
        lo_capped = max(lo, benchmark_median - _TAIL_SIGMA_CAP * sigma)
        hi_capped = min(hi, benchmark_median + _TAIL_SIGMA_CAP * sigma)
        # (lo/hi only reach beyond ±4σ if someone passes a very small sigma — unlikely)
        lo = lo_capped
        hi = hi_capped

        cdf_lo = _piecewise_cdf(lo, knots)
        cdf_hi = _piecewise_cdf(hi, knots)

        p_cold = float(np.clip(cdf_lo, 0.0, 1.0))
        p_inline_raw = float(np.clip(cdf_hi - cdf_lo, 0.0, 1.0))
        p_hot = float(np.clip(1.0 - cdf_hi, 0.0, 1.0))

        # Renormalize to sum to 1.0
        total = p_cold + p_inline_raw + p_hot
        if total <= 0:
            return None
        p_cold = round(p_cold / total, 2)
        p_inline = round(p_inline_raw / total, 2)
        p_hot = round(p_hot / total, 2)

        # Final clamp rounding residual so sum == 1.00
        residual = round(1.0 - (p_cold + p_inline + p_hot), 2)
        p_inline = round(p_inline + residual, 2)

        return {"p_hot": p_hot, "p_cold": p_cold, "p_inline": p_inline}

    except Exception as exc:
        log.debug("compute_surprise_distribution failed: %s", exc)
        return None


# ── 2. Market-implied benchmark (MRI-R16) ────────────────────────────────────

# event_key → (release family, pick strategy)
# These map to the new config.yml event keys (cpi_print, nfp_print).
_RELEASE_EVENT_KEYS: dict[str, str] = {
    "cpi_headline": "cpi_print",
    "cpi_core": "cpi_print",
    "nfp": "nfp_print",
}


# Kalshi bracket-ladder store (collectors/kalshi_releases.py, #1876).
# Summary rows carry implied_median per (asof_date, release_type, period).
_KALSHI_RELEASE_MAP = {
    "cpi_headline": "cpi",   # Kalshi KXCPI tracks headline MoM only
    "nfp": "nfp",
    "claims": "claims",
}


def get_kalshi_implied(
    release_type: str,
    period: str | None,
    kalshi_path: Path,
) -> dict | None:
    """Return the latest Kalshi implied read for (release_type, period), or None.

    MRI-R33 STALE-ENRICH-1: if the Kalshi parquet is older than 5 days, returns a
    stale-annotated null dict ({source, stale_reason}) rather than a stale value.

    Reads summary rows (is_summary=True) from the first-seen snapshot store and
    returns the most recent asof_date's implied_median for the matching period.
    Context only — never fused into model math (MRI-R16). implied_mean is not
    stored upstream by design (open-ended ladder; tail assumption dishonest).
    """
    try:
        kalshi_type = _KALSHI_RELEASE_MAP.get(release_type)
        if kalshi_type is None or period is None or not kalshi_path.exists():
            return None
        # MRI-R33: TTL staleness gate — null with reason if > 5 days old
        stale_reason = _check_parquet_staleness(kalshi_path, _KALSHI_TTL_DAYS)
        if stale_reason:
            log.warning("get_kalshi_implied: %s", stale_reason)
            return {"source": "kalshi", "implied_median": None, "stale_reason": stale_reason}
        df = pd.read_parquet(kalshi_path)
        if df.empty or "is_summary" not in df.columns:
            return None
        sub = df[
            (df["is_summary"] == True)  # noqa: E712 — parquet bool column
            & (df["release_type"] == kalshi_type)
            & (df["period"] == str(period))
        ]
        sub = sub[sub["implied_median"].notna()]
        if sub.empty:
            return None
        row = sub.sort_values("asof_date").iloc[-1]
        return {
            "source": "kalshi",
            "event_ticker": row.get("event_ticker"),
            "implied_median": float(row["implied_median"]),
            "p_above_lowest_strike": (
                float(row["p_above_lowest_strike"])
                if pd.notna(row.get("p_above_lowest_strike")) else None
            ),
            "n_brackets": int(row["n_brackets"]) if pd.notna(row.get("n_brackets")) else None,
            "asof": str(row["asof_date"]),
        }
    except Exception:
        return None


def get_market_implied_benchmark(
    release_type: str,
    release_date_str: str | None,
    snapshots_path: Path,
) -> dict | None:
    """Return market-implied benchmark dict for a release, or None if absent.

    MRI-R33 STALE-ENRICH-2: if the snapshots parquet is older than 5 days, returns a
    stale-annotated null dict ({source, stale_reason}) rather than a stale value.

    Reads the latest snapshot for the matching event_key (cpi_print / nfp_print),
    picks the row with the end_date nearest to (and >= ) release_date_str, and
    derives an implied read from the highest-probability outcome.

    The result is context only — never fused into model math (MRI-R16).

    Returns:
        {source, event_key, event_title, implied, prob_top, asof} or None.
    """
    try:
        event_key = _RELEASE_EVENT_KEYS.get(release_type)
        if event_key is None:
            return None  # claims and unknown releases: no market event

        if not snapshots_path.exists():
            return None

        # MRI-R33: TTL staleness gate — null with reason if > 5 days old
        stale_reason = _check_parquet_staleness(snapshots_path, _MARKET_IMPLIED_TTL_DAYS)
        if stale_reason:
            log.warning("get_market_implied_benchmark: %s", stale_reason)
            return {"source": "market_implied", "implied": None, "stale_reason": stale_reason}

        df = pd.read_parquet(snapshots_path)
        if df.empty:
            return None

        # Filter to the target event_key
        mask = df["event_key"] == event_key
        sub = df[mask]
        if sub.empty:
            return None

        # Latest snapshot_date
        latest_snapshot = str(sub["snapshot_date"].max())
        sub = sub[sub["snapshot_date"] == latest_snapshot]

        # If release_date is given, prefer end_date >= release_date (nearest)
        if release_date_str:
            fut = sub[sub["end_date"] >= release_date_str[:10]]
            if not fut.empty:
                nearest_end = str(fut["end_date"].min())
                sub = fut[fut["end_date"] == nearest_end]
            # Else fall through to all rows for this event_key / snapshot_date

        if sub.empty:
            return None

        # Top outcome by prob
        top_row = sub.loc[sub["prob"].idxmax()]
        event_title = str(top_row.get("event_title", ""))
        implied_outcome = str(top_row.get("outcome", ""))
        prob_top = float(top_row.get("prob", 0.0))
        source = str(top_row.get("source", "polymarket"))

        return {
            "source": source,
            "event_key": event_key,
            "event_title": event_title,
            "implied": implied_outcome,
            "prob_top": round(prob_top, 4),
            "asof": latest_snapshot,
        }

    except Exception as exc:
        log.debug("get_market_implied_benchmark(%s) failed: %s", release_type, exc)
        return None


# ── 3. Reaction-sensitivity chip (MRI-R17) ───────────────────────────────────

def get_reaction_sensitivity(
    release_type: str,
    playbook_path: Path,
    current_regime: str | None = None,
) -> dict | None:
    """Return h1 reaction-sensitivity chip from playbook_v1 for a release type.

    Looks up 2021plus era, h1 horizon, hot and cold buckets, and returns mean
    values for dgs10_bp and spy_pct. Prefers a regime-conditioned cell if the
    current_regime matches an available cell with n >= 8; otherwise uses the
    era-level (regime=null) cell.

    Pure lookup — no regression, no positioning inputs (MRI-R17).

    Returns:
        {
            dgs10_h1_hot_bp, dgs10_h1_cold_bp,
            spy_h1_hot_pct, spy_h1_cold_pct,
            era_basis, regime_cells_used, note
        }
        or None if playbook file is missing or release family not found.
    """
    try:
        # Map release_type → playbook release family
        release_family_map = {
            "cpi_headline": "cpi",
            "cpi_core": "cpi",
            "nfp": "nfp",
        }
        release_family = release_family_map.get(release_type)
        if release_family is None:
            return None

        if not playbook_path.exists():
            log.debug("get_reaction_sensitivity: playbook not found at %s", playbook_path)
            return None

        with open(playbook_path, encoding="utf-8") as fh:
            import json
            cells: list[dict] = json.load(fh)

        if not isinstance(cells, list):
            return None

        def _pick_cell(
            cells: list[dict],
            release: str,
            bucket: str,
            outcome: str,
            era: str,
            regime: str | None,
        ) -> dict | None:
            """Return the best matching cell: regime-conditioned (n>=8) else era-only."""
            # Regime-conditioned cell
            if regime is not None:
                rc = [
                    c for c in cells
                    if c.get("release") == release
                    and c.get("bucket") == bucket
                    and c.get("outcome") == outcome
                    and c.get("horizon") == "h1"
                    and c.get("era") == era
                    and c.get("regime") == regime
                    and (c.get("n") or 0) >= _REGIME_MIN_N
                ]
                if rc:
                    return rc[0]
            # Fall back to era-level (regime=null)
            base = [
                c for c in cells
                if c.get("release") == release
                and c.get("bucket") == bucket
                and c.get("outcome") == outcome
                and c.get("horizon") == "h1"
                and c.get("era") == era
                and c.get("regime") is None
            ]
            return base[0] if base else None

        regime_cells_used = False
        fields: dict[str, float | None] = {}

        for bucket in ("hot", "cold"):
            for outcome_key, field_prefix in [
                ("dgs10_bp", f"dgs10_h1_{bucket}"),
                ("spy_pct", f"spy_h1_{bucket}"),
            ]:
                cell = _pick_cell(
                    cells, release_family, bucket, outcome_key,
                    _ERA_LABEL, current_regime,
                )
                if cell is None:
                    fields[field_prefix] = None
                    continue

                # Check if we're using a regime-conditioned cell
                if cell.get("regime") is not None:
                    regime_cells_used = True

                mean_val = cell.get("mean")
                fields[field_prefix] = round(float(mean_val), 4) if mean_val is not None else None

        note = (
            "Historical means from playbook_v1 2021plus era; regime-conditioned cells used."
            if regime_cells_used
            else "Historical means from playbook_v1 2021plus era; regime=null cells."
        )

        return {
            "dgs10_h1_hot_bp": fields.get("dgs10_h1_hot"),
            "dgs10_h1_cold_bp": fields.get("dgs10_h1_cold"),
            "spy_h1_hot_pct": fields.get("spy_h1_hot"),
            "spy_h1_cold_pct": fields.get("spy_h1_cold"),
            "era_basis": _ERA_LABEL,
            "regime_cells_used": regime_cells_used,
            "note": note,
        }

    except Exception as exc:
        log.debug("get_reaction_sensitivity(%s) failed: %s", release_type, exc)
        return None


# ── 4. Expectation read (MRI-R22) ─────────────────────────────────────────────

# Band threshold matches the inline band in compute_surprise_distribution (MRI-R15 §3.4)
_EXPECTATION_BAND_THRESHOLD = 0.35  # ±σ


def compute_expectation_read(
    point: float | None,
    expectation_values: dict[str, float | None],
    sigma_scale_pp: float | None,
) -> dict | None:
    """Compute the expectation read for a projected release print (MRI-R22).

    Args:
        point: our point forecast value (pp units, same scale as expectation_values).
        expectation_values: dict mapping source name → value (float or None).
            Valid EXPECTATION SET members are:
              'cleveland_nowcast' — Cleveland Fed nowcast (CPI family only)
              'kalshi'            — Kalshi implied_median (preferred market source)
              'polymarket'        — Polymarket numeric implied value (fallback)
            Trend benchmark keys (naive_prior, trailing_3m, ar_model) are ignored.
        sigma_scale_pp: trailing realized-surprise standard deviation in pp units.
            Same as surprise_skew.sigma_scale_pp from the projection artifact.

    Returns:
        {
          'tag':                'above_expectations' | 'below_expectations' | 'aligned',
          'delta_pp':           float (4 dp), our point - expectation_median,
          'standardized':       float (2 dp), delta_pp / sigma_scale_pp,
          'expectation_median': float, median of available expectation values,
          'sources':            [str], names of sources used (in input order),
          'n_sources':          int,
        }
        or None when:
          - expectation set is empty (all values None or dict empty)
          - point is None
          - sigma_scale_pp is None or <= 0

    Display-only — must never be fused into model math (MRI-R22 binding).
    """
    try:
        if point is None:
            return None
        if sigma_scale_pp is None or sigma_scale_pp <= 0:
            return None

        point_f = float(point)
        sigma_f = float(sigma_scale_pp)

        # Only EXPECTATION SET sources are eligible; trend benchmarks are excluded.
        _EXPECTATION_KEYS = ("cleveland_nowcast", "kalshi", "polymarket")

        sources: list[str] = []
        values: list[float] = []
        for key in _EXPECTATION_KEYS:
            if key in expectation_values:
                v = expectation_values[key]
                if v is not None and np.isfinite(float(v)):
                    sources.append(key)
                    values.append(float(v))

        if not values:
            return None  # empty expectation set → null read

        expectation_median = float(np.median(values))
        delta_pp = point_f - expectation_median
        standardized = delta_pp / sigma_f

        if standardized > _EXPECTATION_BAND_THRESHOLD:
            tag = "above_expectations"
        elif standardized < -_EXPECTATION_BAND_THRESHOLD:
            tag = "below_expectations"
        else:
            tag = "aligned"

        return {
            "tag": tag,
            "delta_pp": round(delta_pp, 4),
            "standardized": round(standardized, 2),
            "expectation_median": round(expectation_median, 4),
            "sources": sources,
            "n_sources": len(sources),
        }

    except Exception as exc:
        log.debug("compute_expectation_read failed: %s", exc)
        return None
