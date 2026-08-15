"""§9 NC-2 verdict mapping and the §12/§13 common-eligibility diagnostic.

Two pure functions, both deliberately OUTSIDE the statistical assembly module:
they encode LANGUAGE LAW, not statistics, and language law is what an adversarial
reviewer needs to be able to read in isolation.

THE §9 LANGUAGE LAW (why ``KILLED`` is not in this module's vocabulary)
-----------------------------------------------------------------------
The NC-2 proximity arm can reach exactly three states, and none of them is a
kill:

  * ``UNINFORMATIVE`` — overlap below the frozen 0.50 floor (or unmeasurable).
    No common support is NOT a proximity shadow: with too few same-band controls
    the arm has not tested the counterfactual at all, so it may not speak.
  * ``PROXIMITY_SHADOW`` — adequate overlap AND the apparent edge disappears at
    equal proximity (the within-band CI covers 0 where the unconditional CI
    excluded 0 favorably).  Reported as a shadow, never as detector edge, and
    ``DNR:KILL-WASHOUT-TURN`` is confronted by name wherever it is reported.
  * ``PASSTHROUGH`` — adequate overlap and the within-band read does not
    dissolve the unconditional one.  This is NOT a clearance of
    ``DNR:KILL-WASHOUT-TURN`` territory and no W5 surface may say it is.

``KILLED`` is absent from :data:`NC2_VERDICTS` on purpose, and a test asserts the
absence — an arm that cannot say a word cannot have that word slip in through a
later branch.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Hashable, Iterable, Sequence

from engine.entry_radar.replay import prereg

#: The complete NC-2 vocabulary.  ``KILLED`` is deliberately NOT a member.
NC2_UNINFORMATIVE = "UNINFORMATIVE"
NC2_PROXIMITY_SHADOW = "PROXIMITY_SHADOW"
NC2_PASSTHROUGH = "PASSTHROUGH"
NC2_VERDICTS: tuple[str, ...] = (NC2_UNINFORMATIVE, NC2_PROXIMITY_SHADOW,
                                 NC2_PASSTHROUGH)


def _ci_covers_zero(ci: Sequence[float] | None) -> bool | None:
    """True/False for a well-formed (low, high); None when unreadable.

    An unreadable CI is NOT quietly treated as "covers zero" — the caller
    decides, and :func:`nc2_verdict` treats it as non-shadow so the arm never
    manufactures a shadow verdict out of a missing number.
    """
    if ci is None:
        return None
    try:
        low, high = float(ci[0]), float(ci[1])
    except (TypeError, ValueError, IndexError):
        return None
    if not (math.isfinite(low) and math.isfinite(high)):
        return None
    return low <= 0.0 <= high


def _ci_excludes_zero_favorably(ci: Sequence[float] | None) -> bool:
    """True iff the CI lies STRICTLY above zero (a favorable unconditional read)."""
    if ci is None:
        return False
    try:
        low, high = float(ci[0]), float(ci[1])
    except (TypeError, ValueError, IndexError):
        return False
    if not (math.isfinite(low) and math.isfinite(high)):
        return False
    return low > 0.0


def nc2_verdict(overlap_share: float | None,
                excess_within_band_ci: Sequence[float] | None,
                unconditional_ci: Sequence[float] | None = None) -> str:
    """Map one NC-2 read to its §9 verdict word.

    ``overlap_share`` is ``controls.overlap_share(matches)`` — the share of
    candidates carrying >= 1 same-band control.  Below
    ``prereg.NC2_OVERLAP_FLOOR`` (or NaN/None/unreadable) the answer is
    ``UNINFORMATIVE`` and NOTHING else is consulted: an arm with no common
    support has not run, so neither CI may be read as evidence about it.

    ``unconditional_ci`` carries the pre-band read.  It is the third parameter
    rather than folded into the second because the SHADOW branch is a claim
    about a DISAPPEARANCE — "the edge that was there unconditionally is not
    there at equal proximity" — and a disappearance cannot be evaluated from the
    within-band interval alone.  Absent (the default), no shadow can be
    declared; the read passes through.
    """
    floor = float(prereg.NC2_OVERLAP_FLOOR)
    if overlap_share is None:
        return NC2_UNINFORMATIVE
    try:
        overlap = float(overlap_share)
    except (TypeError, ValueError):
        return NC2_UNINFORMATIVE
    if not math.isfinite(overlap) or overlap < floor:
        return NC2_UNINFORMATIVE

    within_covers_zero = _ci_covers_zero(excess_within_band_ci)
    if within_covers_zero and _ci_excludes_zero_favorably(unconditional_ci):
        return NC2_PROXIMITY_SHADOW
    return NC2_PASSTHROUGH


@dataclass(frozen=True)
class CommonEligibility:
    """§13 row 13 — the common-eligibility gap diagnostic, as data.

    ``pairs`` is the deterministic sorted intersection; the three counts are the
    GAP the diagnostic exists to publish.  A pair present on one side only is
    never silently dropped — it is counted here, which is the whole point: two
    detectors compared over different eligible sets are not being compared.
    """

    pairs: tuple[Hashable, ...]
    n_a: int
    n_b: int
    n_common: int
    only_a: tuple[Hashable, ...]
    only_b: tuple[Hashable, ...]

    @property
    def gap(self) -> int:
        """Pairs eligible on exactly one side — the number the §13 cell prints."""
        return len(self.only_a) + len(self.only_b)


def common_eligible(pairs_a: Iterable[Hashable],
                    pairs_b: Iterable[Hashable]) -> CommonEligibility:
    """Intersect two detectors' eligible ``(ticker, session)`` pair sets.

    Deterministic: every tuple is sorted by its own ``repr`` so a set's iteration
    order can never reach a published table.  Duplicates on either side collapse
    (a pair is eligible or it is not; it is not eligible twice), and the ``n_a``/
    ``n_b`` counts report the DISTINCT sizes for the same reason.

    Battery F: removing one side's warm-up eligibility for a pair removes the
    pair from ``pairs`` and adds it to the corresponding ``only_*`` gap list.
    """
    set_a = set(pairs_a)
    set_b = set(pairs_b)
    common = tuple(sorted(set_a & set_b, key=repr))
    return CommonEligibility(
        pairs=common,
        n_a=len(set_a),
        n_b=len(set_b),
        n_common=len(common),
        only_a=tuple(sorted(set_a - set_b, key=repr)),
        only_b=tuple(sorted(set_b - set_a, key=repr)),
    )


__all__ = ["NC2_UNINFORMATIVE", "NC2_PROXIMITY_SHADOW", "NC2_PASSTHROUGH",
           "NC2_VERDICTS", "nc2_verdict", "CommonEligibility", "common_eligible"]
