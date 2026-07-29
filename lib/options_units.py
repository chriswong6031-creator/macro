"""Unit contracts for the options ingestion seams — the ×100 class, hit twice.

WHY THIS EXISTS.  The options stores mix two scales and nothing asserted which was
which, so a percent-vs-fraction flip could ride through a builder silently and land as
a plausible-looking number 100× off.  Measured contracts (real stores, 2026-07-29):

  FRACTION (0.0–~10)                            PERCENT / PERCENTAGE POINTS
  ─────────────────────────────────             ───────────────────────────────
  options_skew.atm_call_iv   0.084 … 1.885      polygon_gex.summary.dist_to_flip_pct
  options_skew.otm_put_iv    0.088 … 2.598          3.74 … 23.75
  options_skew.skew         -1.014 … 1.440      screener row iv30  (= iv30 × 100)
  options_ivspread.ivspread ±0.496              screener row skew_pp (= skew × 100)
  options_ivspread.ivspread_rel ±0.497          screener row ivspread_pp
  polygon_gex.summary.iv30   0.205 … 0.338      screener implied_move_30d_pct
  polygon_gex.chains.iv      0.0001 … 9.320

The trap the two historical incidents share: a unit test whose FIXTURE carries
percent-shaped IV (``iv30=28.5``) passes against a builder that multiplies by 100 —
because the fixture already encodes the bug.  So every check here is exercised against
BOTH shapes: a fixture-shaped frame and a prod-shaped one
(tests/test_options_unit_seams.py).

These helpers NEVER raise and NEVER modify values.  A flip is loud, not fatal: the store
may legitimately drift and a builder that hard-failed on it would take a page down.  The
annotation is a bare line-start ``print`` with ``flush=True`` — a logger prefix pushes
``::`` off column 0 and GitHub drops the annotation entirely (see
tests/test_gh_annotation_line_start.py).
"""
from __future__ import annotations

# An implied-vol FRACTION above this is almost certainly a percent value that was never
# divided down.  The widest real observation is chains.iv at 9.32 (932% IV — a genuine
# near-expiry blowout), so the floor sits above that with room, and a percent-shaped
# series has a median in the tens.
IV_FRACTION_MAX_MEDIAN = 3.0
# A percentage-point series should not have a median in the fractions — that is the
# reverse flip (someone divided by 100 twice, or forgot the multiply).  Calibration:
# dist_to_flip_pct's real cross-sectional median is 12.82, so a ÷100 flip lands at 0.128.
# 0.5 sits above that and below anything plausible: a true median under 0.5 would mean
# half the universe is pinned within half a percent of its gamma flip, which is itself
# worth an annotation.  (0.05 was the first value here and it was too loose to catch the
# flip it existed for — tests/test_options_unit_seams.py::
# TestPercentChecker::test_a_fraction_shaped_series_is_caught.)
PERCENT_MIN_MEDIAN = 0.5


def _median(values) -> float | None:
    """Median of the finite absolute values, or None when there is nothing to judge."""
    import math

    out = []
    for v in values:
        try:
            f = abs(float(v))
        except (TypeError, ValueError):
            continue
        if math.isfinite(f):
            out.append(f)
    if not out:
        return None
    out.sort()
    n = len(out)
    return out[n // 2] if n % 2 else (out[n // 2 - 1] + out[n // 2]) / 2.0


def check_iv_fraction(values, label: str) -> str | None:
    """Assert an implied-vol series is FRACTION-scaled.  Returns a message on a flip.

    ``0.28`` means 28% vol.  A median above :data:`IV_FRACTION_MAX_MEDIAN` says the
    series arrived already multiplied by 100, and every downstream ``× 100`` will render
    a 2,850% implied move.
    """
    med = _median(values)
    if med is None:
        return None
    if med > IV_FRACTION_MAX_MEDIAN:
        return (f"{label}: median |value| = {med:.4g}, which reads as PERCENT-scaled. "
                f"This seam's contract is FRACTION (0.28 = 28% vol); a downstream ×100 "
                f"will render values 100× too large.")
    return None


def check_percent_scale(values, label: str) -> str | None:
    """Assert a percentage / percentage-point series is PERCENT-scaled.

    The mirror of :func:`check_iv_fraction`: ``dist_to_flip_pct = 12.82`` means 12.82%.
    A median below :data:`PERCENT_MIN_MEDIAN` says the value is still a fraction and a
    surface will print "0.1%" where it means "12.8%".
    """
    med = _median(values)
    if med is None:
        return None
    if med < PERCENT_MIN_MEDIAN:
        return (f"{label}: median |value| = {med:.4g}, which reads as FRACTION-scaled. "
                f"This seam's contract is PERCENT (12.82 = 12.82%); the value is missing "
                f"its ×100 or was divided twice.")
    return None


def annotate(msg: str | None, *, title: str = "options-unit-seam") -> bool:
    """Emit a line-start GitHub annotation for a unit flip.  Returns True if it fired.

    Bare print, column 0, ``flush=True`` — never a logger (a ``"%(levelname)s "`` prefix
    makes GitHub silently drop the whole workflow command).
    """
    if not msg:
        return False
    print(f"::warning title={title}::{msg}", flush=True)
    return True


def guard_iv_fraction(values, label: str) -> bool:
    """check_iv_fraction + annotate.  True when a flip was reported."""
    return annotate(check_iv_fraction(values, label))


def guard_percent_scale(values, label: str) -> bool:
    """check_percent_scale + annotate.  True when a flip was reported."""
    return annotate(check_percent_scale(values, label))
