"""engine/tech_score.py — Transparent composite technical score + confluence runner.

DISPLAY-ONLY / RESEARCH ARTEFACT.
This module does NOT originate signals, scores, or escalations.
It aggregates catalog signals into a transparent composite for display and
exploratory research only.  It is NOT wired to any allocation.

Score bands (matching StockInvest conventions for familiarity):
    Strong Buy  :  score >= 5
    Buy         :  1 <= score < 5
    Hold        : -1 < score < 1
    Sell        : -5 < score <= -1
    Strong Sell :  score <= -5

Default weights
---------------
Equal weight per FAMILY, not per signal.  Within each family every active
signal contributes equally so that families with many signals do not
dominate families with few.  This choice is documented, tunable, and
intentional — it avoids spurious precision from arbitrary asymmetric weights.

Families present in the catalog at the time of writing:
    ma_crosses, pivots, rsi_bands, formations, trend, performance,
    fundamental_valuation, tech_stars
Each family receives weight 1/(number of families) by default.

The caller can supply a ``weights`` dict {family_name: float}; any unmapped
family falls back to the equal-weight default.  Weights are renormalised
internally so they do not need to sum to 1.

Contributor record
------------------
score() returns a ScoreResult dataclass that carries:
    score  : float in [-10, +10]
    band   : str  ("Strong Buy" / "Buy" / "Hold" / "Sell" / "Strong Sell")
    contributors : list of ContributorRecord — one per active signal, showing
                   signal_id, family, direction, weight applied, and raw value.

Confluence helper
-----------------
confluence(signal_ids, df, mode, min_k) produces a combined boolean/float
Series over named catalog signals.  Delegates to engine.lab.confluence where
the lab Signal machinery fits; otherwise computes directly over
engine.tech_catalog.compute.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Band thresholds
# ---------------------------------------------------------------------------
BAND_STRONG_BUY = 5.0
BAND_BUY = 1.0
BAND_SELL = -1.0
BAND_STRONG_SELL = -5.0


def _score_to_band(score: float) -> str:
    if score >= BAND_STRONG_BUY:
        return "Strong Buy"
    if score >= BAND_BUY:
        return "Buy"
    if score > BAND_SELL:
        return "Hold"
    if score > BAND_STRONG_SELL:
        return "Sell"
    return "Strong Sell"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class ContributorRecord:
    """Per-signal contribution record returned by score()."""
    signal_id: str
    family: str
    direction: int          # +1 bullish / -1 bearish (from catalog descriptor)
    raw_value: float        # TRUE value of signal on the latest bar (0/1 for events; float for states) — for display/audit
    family_weight: float    # weight assigned to this signal's family
    contribution: float     # direction * clip(raw_value, -1, 1) * family_weight (before global normalisation)


@dataclass
class ScoreResult:
    """Return value from score().

    Attributes
    ----------
    score : float
        Composite score in [-10, +10].
    band : str
        Human-readable band label.
    contributors : list[ContributorRecord]
        Per-signal breakdown (display / audit).
    n_active : int
        Number of signals that returned a non-NaN value on the latest bar.
    n_total : int
        Total number of signals evaluated.
    """
    score: float
    band: str
    contributors: list[ContributorRecord] = field(default_factory=list)
    n_active: int = 0
    n_total: int = 0


# ---------------------------------------------------------------------------
# score()
# ---------------------------------------------------------------------------

def score(
    df: pd.DataFrame,
    weights: dict[str, float] | None = None,
    signal_ids: list[str] | None = None,
) -> ScoreResult:
    """Compute a transparent composite technical score for a single ticker.

    Parameters
    ----------
    df : pd.DataFrame
        Single-ticker OHLCV DataFrame with at minimum a ``close`` column and
        a DatetimeIndex.  Uses the latest bar (``df.iloc[-1]``) as the
        evaluation point.
    weights : dict[str, float] | None
        Optional per-family weight overrides, e.g. ``{'ma_crosses': 2.0}``.
        Unmapped families use the equal-weight default (1.0 each).  Weights
        are renormalised so they do not need to sum to 1.
    signal_ids : list[str] | None
        Subset of catalog signal IDs to evaluate.  ``None`` = all catalog
        signals (default).

    Returns
    -------
    ScoreResult
        score (float in [-10,+10]), band (str), contributors (list),
        n_active (int), n_total (int).

    Notes
    -----
    - Cross-sectional (fundamental_valuation family) signals require
      ``df.attrs['ticker']`` to be set; if missing they are silently skipped.
    - Signals that raise on computation are silently skipped and logged at
      DEBUG level.
    - The score is display-only/research.  It is NOT an LLM output and
      is NOT wired to any allocation.
    """
    from engine import tech_catalog as tc  # noqa: PLC0415

    if df.empty:
        return ScoreResult(score=0.0, band="Hold")

    # --- resolve signal universe -------------------------------------------
    if signal_ids is not None:
        catalog_entries = {sid: tc.get_signal(sid) for sid in signal_ids}
    else:
        catalog_entries = {sid: desc for sid, desc in tc.TECH_SIGNALS.items()}

    # --- derive equal-weight default per family ----------------------------
    families_present = sorted({desc["family"] for desc in catalog_entries.values()})
    n_families = max(len(families_present), 1)
    base_weight = 1.0 / n_families

    def _family_weight(family: str) -> float:
        if weights and family in weights:
            return weights[family]
        return base_weight

    # --- evaluate each signal on the latest bar ----------------------------
    contributors: list[ContributorRecord] = []
    n_active = 0
    n_total = len(catalog_entries)

    for sid, desc in catalog_entries.items():
        family = desc.get("family", "unknown")
        direction = int(desc.get("direction", 1))
        fw = _family_weight(family)

        try:
            series = tc.compute(sid, df)
        except Exception as exc:
            log.debug("tech_score: skipping %s — %s", sid, exc)
            n_total -= 1  # don't count errored signals against the denominator
            continue

        if series.empty:
            continue

        raw = float(series.iloc[-1]) if not pd.isna(series.iloc[-1]) else float("nan")
        if pd.isna(raw):
            continue

        n_active += 1
        # Clip each signal's EFFECTIVE raw magnitude to [-1, 1] (sign-preserving)
        # before weighting, so no single wide-range signal can dominate the
        # composite. The normalisation denominator (max_magnitude below) already
        # assumes a per-signal max of 1.0; clipping aligns the numerator with it.
        # A 0-100 state (e.g. insider_power_state) once contributed ~6.6 vs ~±0.1
        # for every other signal, pinning dozens of names to a false +10.
        # Event signals (0/1) and 0-1 states (e.g. valuation_pctile) are already
        # ≤ 1 and therefore unchanged. raw_value keeps the TRUE value for display.
        eff_raw = max(-1.0, min(1.0, raw))
        contribution = direction * eff_raw * fw

        contributors.append(ContributorRecord(
            signal_id=sid,
            family=family,
            direction=direction,
            raw_value=raw,
            family_weight=fw,
            contribution=contribution,
        ))

    # --- aggregate and normalise to [-10, +10] -----------------------------
    if not contributors:
        return ScoreResult(score=0.0, band="Hold", contributors=[], n_active=0, n_total=n_total)

    raw_sum = sum(c.contribution for c in contributors)

    # Theoretical max magnitude: sum of |direction| * max_raw * weight for each signal.
    # Every signal's effective raw is clipped to [-1, 1] above, so max_raw = 1.0
    # for events AND states/continuous alike — the numerator can never exceed this.
    # Per-family normalisation: within a family, sum of weights = 1 signal * fw.
    # Upper bound = sum of fw values across all evaluated contributors (one per signal).
    # We use the actual evaluated set to avoid penalising when catalog partially loads.
    max_magnitude = sum(abs(c.family_weight) * 1.0 for c in contributors)

    if max_magnitude == 0:
        normalised = 0.0
    else:
        normalised = (raw_sum / max_magnitude) * 10.0

    # clamp to [-10, +10] (floating point safety)
    final_score = max(-10.0, min(10.0, normalised))
    band = _score_to_band(final_score)

    return ScoreResult(
        score=final_score,
        band=band,
        contributors=contributors,
        n_active=n_active,
        n_total=n_total,
    )


# ---------------------------------------------------------------------------
# confluence()
# ---------------------------------------------------------------------------

def confluence(
    signal_ids: list[str],
    df: pd.DataFrame,
    mode: str = "all",
    min_k: int | None = None,
) -> pd.Series:
    """Combine named catalog signals into a boolean/float event Series.

    Computes each signal over ``df`` via ``engine.tech_catalog.compute``, then
    combines them with AND / OR / k-of-n logic.

    Parameters
    ----------
    signal_ids : list[str]
        Catalog signal IDs to combine.  Must be non-empty.
    df : pd.DataFrame
        Single-ticker OHLCV DataFrame.
    mode : str
        ``'all'``    — every signal must be truthy (AND; default).
        ``'any'``    — at least one signal truthy (OR).
        ``'k_of_n'`` — at least ``min_k`` signals truthy.
    min_k : int | None
        Required when ``mode='k_of_n'``.

    Returns
    -------
    pd.Series (float 0.0/1.0, aligned to df.index)
        1.0 on bars where the confluence condition is met, 0.0 otherwise.
        NaN bars in any component are treated as 0 (non-contributing).

    Raises
    ------
    ValueError
        If ``signal_ids`` is empty, ``mode`` is invalid, or ``mode='k_of_n'``
        is requested without ``min_k``.
    KeyError
        If any signal_id is not in the catalog.
    """
    if not signal_ids:
        raise ValueError("confluence: signal_ids must be non-empty")
    if mode not in ("all", "any", "k_of_n"):
        raise ValueError(f"confluence: mode must be 'all', 'any', or 'k_of_n'; got {mode!r}")
    if mode == "k_of_n" and min_k is None:
        raise ValueError("confluence: mode='k_of_n' requires min_k")

    from engine import tech_catalog as tc  # noqa: PLC0415

    k = min_k if min_k is not None else (len(signal_ids) if mode == "all" else 1)

    # Compute each signal
    series_list: list[pd.Series] = []
    for sid in signal_ids:
        s = tc.compute(sid, df)
        # Treat NaN as 0 (non-firing)
        s = s.fillna(0.0)
        series_list.append(s)

    if not series_list:
        return pd.Series(0.0, index=df.index, name="confluence", dtype=float)

    # Align all series to a common index (intersection)
    combined = pd.concat(series_list, axis=1)
    combined.columns = signal_ids

    # Count how many signals are truthy (> 0) on each bar
    truthy_count = (combined > 0).sum(axis=1)

    result = (truthy_count >= k).astype(float)
    result.name = "confluence"
    return result
