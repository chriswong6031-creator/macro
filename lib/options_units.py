"""Unit contracts for the options ingestion seams — the ×100 class, hit twice.

WHY THIS EXISTS.  The options stores mix two scales and nothing asserted which was
which, so a percent-vs-fraction flip could ride through a builder silently and land as
a plausible-looking number 100× off.

MEASURED CONTRACTS (whole family, real stores, 2026-07-29 — an earlier draft of this
docstring quoted a single ticker's range and understated all three):

  scale        column                                  min       median      max
  -----------  ------------------------------------    --------  --------    -------
  FRACTION     options_skew.atm_call_iv                 0.084     0.469       1.885
  (LEVEL)      options_skew.otm_put_iv                  0.088     0.487       2.598
               polygon_gex.summary.iv30                 0.00188   0.4708      1.7378
               polygon_gex.chains.iv                    0.000074  0.5256      9.3198
  FRACTION     options_skew.skew                       -1.014     0.0356      1.440
  (DIFFERENCE) options_ivspread.ivspread               -0.496     0.0349      0.494
               options_ivspread.ivspread_rel           -0.491     0.0336      0.497
  PERCENT      polygon_gex.summary.dist_to_flip_pct   -24.86      4.205      25.00
               (30.9% of rows are NEGATIVE; |value| median 7.13)
               + every screener row field ending _pct / _pp (the post-×100 side)

TWO THRESHOLDS, NOT ONE.  A single fraction threshold cannot serve both kinds.  Measured
margin of a whole-store ×100 flip against a 3.0 threshold: IV **levels** clear it by
15.6–16.3×, IV **differences** by only 1.12–1.19× — skew's flipped median is 3.56 against
a 3.0 bar.  A difference is two orders of magnitude smaller than a level, so it gets its
own bar.

GUARD THE LATEST CROSS-SECTION, NOT THE WHOLE STORE.  The realistic flip is a vendor or
builder change that lands on the NEWEST vintage while years of correct history sit behind
it.  Measured on both stores: a newest-vintage-only ×100 flip moves the whole-store median
from 0.0356 to 0.0376 — **missed on all five columns** — while the latest cross-section
median goes 0.0436 → 3.95 and is caught on all five.  Whole-store medians dilute exactly
the flip this module exists to catch, so callers pass the `latest` rows they already
computed for the join.

Every check is exercised against BOTH shapes — hand-built fixture frames AND the real
stores — and against a SIMULATED newest-vintage flip, because both historical incidents
survived tests whose fixtures encoded the bug (tests/test_options_unit_seams.py).

These helpers NEVER raise and NEVER modify values.  A flip is loud, not fatal: the store
may legitimately drift and a builder that hard-failed on it would take a page down.  The
annotation is a bare line-start ``print`` with ``flush=True`` — a logger prefix pushes
``::`` off column 0 and GitHub drops the annotation entirely (see
tests/test_gh_annotation_line_start.py).
"""
from __future__ import annotations

# ── IV LEVELS (an implied vol: 0.28 = 28% vol) ────────────────────────────────
# Highest genuine median observed is chains.iv at 0.53; the widest single value is 9.32
# (932% near-expiry vol), which the median-keyed test tolerates.  A percent-shaped level
# has a median in the tens (46.9 measured), so 3.0 sits ~6× above genuine and ~15× below
# a flip.
IV_LEVEL_MAX_MEDIAN = 3.0

# ── IV DIFFERENCES (skew, ivspread: a difference of two vols) ─────────────────
# Genuine medians are 0.034–0.044 and the widest single value is 1.44.  A ×100 flip of the
# latest cross-section lands at 3.8–4.0.  0.5 sits ~11× above genuine and ~7.6× below a
# flip — where a shared 3.0 bar left only 1.12–1.19×.  A cross-sectional MEDIAN |skew| of
# 0.5 would mean 50 vol points of skew on the median name, which is not a market state.
IV_DIFF_MAX_MEDIAN = 0.5

# ── PERCENT / PERCENTAGE POINTS (12.82 = 12.82%) ─────────────────────────────
# Calibration: dist_to_flip_pct's real whole-family |value| median is 7.13, so a ÷100 flip
# lands at 0.0713.  0.5 sits above that and below anything plausible: a true median under
# 0.5 would mean half the universe pinned within half a percent of its gamma flip, which
# is itself worth an annotation.  (0.05 was the first value here and was too loose to
# catch the flip it existed for — tests/test_options_unit_seams.py::
# TestPercentChecker::test_a_fraction_shaped_series_is_caught.)
PERCENT_MIN_MEDIAN = 0.5

# Back-compat alias: the first draft shipped one fraction threshold under this name.
IV_FRACTION_MAX_MEDIAN = IV_LEVEL_MAX_MEDIAN

_KIND_MAX = {"level": IV_LEVEL_MAX_MEDIAN, "difference": IV_DIFF_MAX_MEDIAN}


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


def check_iv_fraction(values, label: str, kind: str = "level") -> str | None:
    """Assert an implied-vol series is FRACTION-scaled.  Returns a message on a flip.

    ``kind="level"`` for a vol (``0.28`` = 28% vol); ``kind="difference"`` for a spread
    or skew (a difference of two vols, two orders of magnitude smaller — see the module
    docstring for why they cannot share a threshold).

    Pass the LATEST CROSS-SECTION where one exists: a whole-store median dilutes a
    newest-vintage flip below any usable threshold (measured miss on both stores).
    """
    ceiling = _KIND_MAX.get(kind, IV_LEVEL_MAX_MEDIAN)
    med = _median(values)
    if med is None:
        return None
    if med > ceiling:
        return (f"{label}: median |value| = {med:.4g} over the {kind} ceiling {ceiling}, "
                f"which reads as PERCENT-scaled. This seam's contract is FRACTION "
                f"(0.28 = 28% vol); a downstream x100 will render values 100x too large.")
    return None


def check_iv_level(values, label: str) -> str | None:
    """:func:`check_iv_fraction` for an IV LEVEL."""
    return check_iv_fraction(values, label, kind="level")


def check_iv_difference(values, label: str) -> str | None:
    """:func:`check_iv_fraction` for an IV DIFFERENCE (skew / ivspread)."""
    return check_iv_fraction(values, label, kind="difference")


def check_percent_scale(values, label: str) -> str | None:
    """Assert a percentage / percentage-point series is PERCENT-scaled.

    The mirror of :func:`check_iv_fraction`: ``dist_to_flip_pct = 12.82`` means 12.82%.
    A median below :data:`PERCENT_MIN_MEDIAN` says the value is still a fraction and a
    surface will print "0.1%" where it means "12.8%".  Judged on |value| — this column is
    signed (30.9% of rows negative).
    """
    med = _median(values)
    if med is None:
        return None
    if med < PERCENT_MIN_MEDIAN:
        return (f"{label}: median |value| = {med:.4g} under the percent floor "
                f"{PERCENT_MIN_MEDIAN}, which reads as FRACTION-scaled. This seam's "
                f"contract is PERCENT (12.82 = 12.82%); the value is missing its x100 "
                f"or was divided twice.")
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


def guard_iv_level(values, label: str) -> bool:
    """check_iv_level + annotate.  True when a flip was reported."""
    return annotate(check_iv_level(values, label))


def guard_iv_difference(values, label: str) -> bool:
    """check_iv_difference + annotate.  True when a flip was reported."""
    return annotate(check_iv_difference(values, label))


def guard_iv_fraction(values, label: str, kind: str = "level") -> bool:
    """check_iv_fraction + annotate.  True when a flip was reported."""
    return annotate(check_iv_fraction(values, label, kind=kind))


def guard_percent_scale(values, label: str) -> bool:
    """check_percent_scale + annotate.  True when a flip was reported."""
    return annotate(check_percent_scale(values, label))
