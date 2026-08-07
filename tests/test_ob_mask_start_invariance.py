"""Is `scripts.grade_us_board._ob_mask` a function of the PRICE HISTORY, or of the
caller's SLICE of it?

`_ob_mask` is the incumbent episode's TARGET EXIT leg in `emit_ledger` — the 3D StochRSI
overbought flag that decides which bar an episode sells on, and therefore its realised
P&L in `site/factordata/us_track_ledger.json` (the Track-record dialog + the hero
win-rate/expectancy on the Track-record page). It reads `confluence_tiers._tf_bars(c, 3)`,
i.e. `daily.resample("3B")`, whose bin edges anchor to the SERIES' FIRST TIMESTAMP.

The grader calls it on the full ROLLING close cache, so as the cache's start rolls off
(smallcap/midcap `_closes_cache.parquet` moved 2023-06-27 -> 2023-07-03 across three
sessions in early Aug 2026), every 3D bucket in the whole history re-phases and flags from
weeks ago flip. Measured blast radius on the real panel:
`reports/ob_mask_track_record_blast_radius.md`.

TWO PROPERTIES, ONLY ONE OF WHICH HOLDS:

  CAUSAL   — a 3D bucket is only readable once complete, so this can never peek.
             `test_causal_trailing_truncation_never_moves_past_flags` pins it. GREEN today
             and expected green forever; it is the half of the docstring that was true.

  STABLE   — the mask on a given date should not depend on how much LEADING history the
             caller happened to hold. `test_start_invariance` pins it. RED today, so it is
             marked xfail(strict=True).

WHY strict=True. PR #4732 (`abs-session-2026-08-06`) migrates `_tf_bars` to an absolute
session anchor IN PLACE. `_ob_mask` imports `_tf_bars` directly, so that repair reaches
this consumer for free — and silently: `scripts/grade_us_board.py` is not in #4732's file
list, its blast-radius report never measures the track record, and R5's era stamp
propagates through `cascade`/`tier_stream`/`signal_gate`, none of which this path touches.

So the day the anchor lands, this xfail flips to XPASS and strict mode turns it RED. That
is the notification we want: every published historical number in the ledger changes on
that merge, and per the session-anchor ruling a graded-population change REQUIRES a new
era stamp rather than a silent recompute. The unblock procedure — drop the marker, stamp
the era, re-measure — is `research/US_TRACK_RECORD_ERA_BREAK_PROPOSAL.md`. Nothing here
changes a grading rule.

The series is synthetic and seeded so this pins the ANCHOR, not today's tape: a fixture cut
from the rolling cache would itself re-phase as the store rolls, which is the very defect
under test.

Run as a plain script:  python -m pytest tests/test_ob_mask_start_invariance.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.grade_us_board import _ob_mask  # noqa: E402

#: `_ob_mask` returns None under 200 bars; 700 clears that with room for the StochRSI
#: warm-up to decay well before the compared tail.
_N_BARS = 700

#: Compare on the trailing window only. A leading-bar drop also shifts the oscillator's
#: warm-up, which perturbs values near the series START under ANY anchor — including a
#: correct one. Production reads recent dates (episodes graded within weeks), so the tail
#: is both the honest comparison window and the one that matters.
_TAIL = 200

#: Multiples of the 3D bucket width preserve the phase even under the start-anchored grid,
#: so they are excluded — including them would make the xfail pass for the wrong reason.
_REPHASING_DROPS = (1, 2, 4, 5, 7)


def _series() -> pd.Series:
    """A deterministic price path with enough cyclicality to actually reach overbought."""
    rng = np.random.default_rng(20260806)
    idx = pd.bdate_range("2022-01-03", periods=_N_BARS)
    drift = rng.normal(0.0004, 0.018, _N_BARS)
    cycle = 0.05 * np.sin(np.arange(_N_BARS) * 2 * np.pi / 55)
    return pd.Series(100 * np.exp(np.cumsum(drift) + cycle), index=idx)


def _tail_disagreements(a: pd.Series, b: pd.Series) -> int:
    overlap = a.index.intersection(b.index)[-_TAIL:]
    return int((a.loc[overlap] != b.loc[overlap]).sum())


def test_the_fixture_actually_reaches_overbought() -> None:
    """Guards the two real assertions from passing vacuously on an all-False mask."""
    m = _ob_mask(_series())
    assert m is not None, "_ob_mask returned None — fixture is under the 200-bar floor"
    n_true = int(m.iloc[-_TAIL:].sum())
    assert n_true > 0, "no overbought flag in the compared tail — the test would be vacuous"
    assert n_true < _TAIL, "every tail bar overbought — degenerate fixture"


def test_causal_trailing_truncation_never_moves_past_flags() -> None:
    """CAUSAL: grading on an earlier night must not change what a later night reports for
    the SAME past date. This is the half of `_ob_mask`'s docstring that holds, and it is
    what makes the leg legitimate as an exit rule at all."""
    close = _series()
    full = _ob_mask(close)
    for cut in (1, 2, 3, 7, 20):
        earlier = _ob_mask(close.iloc[:-cut])
        overlap = earlier.index
        moved = int((full.loc[overlap] != earlier.loc[overlap]).sum())
        assert moved == 0, (
            f"dropping {cut} TRAILING bars moved {moved} past flags — `_ob_mask` would be "
            f"peeking, which no era stamp can excuse"
        )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "KNOWN DEFECT: _tf_bars resamples on start-anchored `3B` bins, so the mask depends "
        "on how much LEADING history the caller holds. Expected to XPASS once PR #4732 "
        "(abs-session-2026-08-06) lands — that XPASS is the tripwire: it means every "
        "published number in us_track_ledger.json just changed and the era break in "
        "research/US_TRACK_RECORD_ERA_BREAK_PROPOSAL.md is now due."
    ),
)
def test_start_invariance() -> None:
    """STABLE: the flag on a given date must be a function of the price history, never of
    the caller's window into it."""
    close = _series()
    full = _ob_mask(close)
    offenders = {}
    for k in _REPHASING_DROPS:
        moved = _tail_disagreements(full, _ob_mask(close.iloc[k:]))
        if moved:
            offenders[k] = moved
    assert not offenders, (
        f"dropping leading sessions re-phased the 3D grid and flipped tail flags: "
        f"{offenders} (drop -> flipped flags in the last {_TAIL} sessions). Each flip can "
        f"move an episode's exit bar and its published P&L."
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
