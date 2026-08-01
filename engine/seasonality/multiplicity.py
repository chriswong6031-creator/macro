"""Selection-aware multiple-testing primitives for seasonality research.

Dense start-date × horizon scans produce highly dependent hypotheses.  The two
helpers here cover the first honest layers without pretending independence:

* Benjamini-Yekutieli adjusted p-values for a registered, finite panel under
  arbitrary dependence.
* Westfall-Young-style maxT adjusted p-values from a caller-supplied null matrix
  whose rows preserve the dependence across the complete scan.

The bootstrap/resampling policy remains the caller's responsibility.  For a
calendar scan it should use synchronized circular shifts or stationary blocks;
for catalyst studies it should resample issuer/date clusters.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Sequence


def _p_values(values: Iterable[float], name: str) -> list[float]:
    out: list[float] = []
    for index, raw in enumerate(values):
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError(f"{name}[{index}] must be a number in [0, 1]")
        value = float(raw)
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError(f"{name}[{index}] must be a finite number in [0, 1]")
        out.append(value)
    if not out:
        raise ValueError(f"{name} cannot be empty")
    return out


def benjamini_yekutieli(p_values: Iterable[float]) -> list[float]:
    """Return BY step-up adjusted p-values in the original order.

    BY controls false discovery rate under arbitrary dependence by multiplying
    the ordinary BH factor by the harmonic number ``sum(1 / i, i=1..m)``.
    The reverse cumulative minimum enforces monotonic adjusted values.
    """
    values = _p_values(p_values, "p_values")
    m = len(values)
    harmonic = math.fsum(1.0 / rank for rank in range(1, m + 1))
    ordered = sorted(enumerate(values), key=lambda item: (item[1], item[0]))

    adjusted_sorted = [1.0] * m
    running = 1.0
    for position in range(m - 1, -1, -1):
        _original_index, value = ordered[position]
        rank = position + 1
        candidate = min(1.0, value * m * harmonic / rank)
        running = min(running, candidate)
        adjusted_sorted[position] = running

    adjusted = [1.0] * m
    for position, (original_index, _value) in enumerate(ordered):
        adjusted[original_index] = adjusted_sorted[position]
    return adjusted


def max_t_adjusted_p_values(
    observed_statistics: Sequence[float],
    null_statistics: Sequence[Sequence[float]],
    *,
    two_sided: bool = True,
) -> list[float]:
    """Return familywise maxT p-values for a complete scan.

    ``null_statistics`` is shaped ``[n_resamples][n_hypotheses]``.  Each row
    must be generated jointly so overlap and cross-asset dependence are kept.
    The finite-sample ``(+1)/(B+1)`` correction prevents a reported zero.
    """
    if not observed_statistics:
        raise ValueError("observed_statistics cannot be empty")
    observed: list[float] = []
    for index, raw in enumerate(observed_statistics):
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError(f"observed_statistics[{index}] must be numeric")
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError(f"observed_statistics[{index}] must be finite")
        observed.append(abs(value) if two_sided else value)

    maxima: list[float] = []
    expected_width = len(observed)
    for row_index, row in enumerate(null_statistics):
        if len(row) != expected_width:
            raise ValueError(
                f"null_statistics[{row_index}] has width {len(row)}; expected {expected_width}"
            )
        numeric_row: list[float] = []
        for column_index, raw in enumerate(row):
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ValueError(f"null_statistics[{row_index}][{column_index}] must be numeric")
            value = float(raw)
            if not math.isfinite(value):
                raise ValueError(f"null_statistics[{row_index}][{column_index}] must be finite")
            numeric_row.append(abs(value) if two_sided else value)
        maxima.append(max(numeric_row))
    if not maxima:
        raise ValueError("null_statistics cannot be empty")

    denominator = len(maxima) + 1
    return [
        (1 + sum(maximum >= statistic for maximum in maxima)) / denominator
        for statistic in observed
    ]
