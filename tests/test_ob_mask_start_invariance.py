"""Is `scripts.grade_us_board._ob_mask` a function of the PRICE HISTORY, or of the
caller's SLICE of it?

`_ob_mask` is the incumbent episode's TARGET EXIT leg in `emit_ledger` — the 3D StochRSI
overbought flag that decides which bar an episode sells on, and therefore its realised
P&L in `site/factordata/us_track_ledger.json` (the Track-record dialog + the hero
win-rate/expectancy on the Track-record page). It reads `confluence_tiers._tf_bars(c, 3)`.

HISTORICALLY that was `daily.resample("3B")`, whose bin edges anchored to the SERIES' FIRST
TIMESTAMP. The grader calls it on the full ROLLING close cache, so as the cache's start
rolled off (smallcap/midcap `_closes_cache.parquet` moved 2023-06-27 -> 2023-07-03 across
three sessions in early Aug 2026), every 3D bucket in the whole history re-phased and flags
from weeks ago flipped. Measured blast radius on the real panel:
`reports/ob_mask_track_record_blast_radius.md`.

TWO PROPERTIES — BOTH HOLD AS OF 2026-08-07:

  CAUSAL   — a 3D bucket is only readable once complete, so this can never peek.
             `test_causal_trailing_truncation_never_moves_past_flags` pins it. GREEN in both
             eras; it is the half of the docstring that was always true.

  STABLE   — the mask on a given date must not depend on how much LEADING history the
             caller happened to hold. `test_start_invariance` pins it. Was RED (marked
             xfail(strict=True)); GREEN since the absolute anchor landed.

THE TRIPWIRE FIRED — history of this file. `test_start_invariance` shipped as
`xfail(strict=True)` in PR #4747 (`4b98aeb7123`) so that it would flip to XPASS — i.e. RED —
the moment PR #4732 (`2a0c5e27184`, `abs-session-2026-08-06`) migrated `_tf_bars` to an
absolute session anchor IN PLACE. `_ob_mask` imports `_tf_bars` directly, so that repair
reached this consumer for free and silently: `scripts/grade_us_board.py` is not in #4732's
file list, its blast-radius report never measures the track record, and R5's era stamp
propagates through `cascade`/`tier_stream`/`signal_gate`, none of which this path touches.

The two PRs merged 28 SECONDS APART (00:11:05 and 00:11:33 on 2026-08-07), each green
against a base that did not contain the other, so the tripwire never spent a day armed — it
went red on main on arrival. The marker is dropped here because a fired tripwire is spent:
it has delivered its notification, and leaving it red blocks every unrelated PR in the repo
without advancing the thing it was notifying about.

WHAT IS STILL OUTSTANDING (this file no longer tracks it — do not read green here as done):
the era break in `research/US_TRACK_RECORD_ERA_BREAK_PROPOSAL.md` is DUE and UNEXECUTED.
`site/factordata/us_track_ledger.json` carries NO `meta.anchor_era`, and its §0.1 gate
requires an operator/Fable ruling before any recompute — not a builder's call, so it is not
made here. What keeps that safe for now is that the shipped artifact is still frozen at
`as_of 2026-07-31` on PRE-anchor numbers (`expectancy_pct 1.19`, `win_pct 63.6`), so nothing
has silently re-baked yet. The moment the US board lane unfreezes and the nightly re-grades,
those public numbers move under the new grid with no era stamp — which is the silent
re-bake R5 forbids. Nothing here changes a grading rule.

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
#: so they are excluded — including them would have made the xfail pass for the wrong
#: reason, and would now weaken the regression guard in exactly the same way.
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


def test_start_invariance() -> None:
    """STABLE: the flag on a given date must be a function of the price history, never of
    the caller's window into it.

    The `xfail(strict=True)` tripwire this test carried has FIRED and is spent (see the
    module docstring). It is now a live REGRESSION guard: `_tf_bars` is absolute-anchored,
    so any future change that re-introduces a caller-window dependence — a revert, or a new
    resample-based grid on this path — fails here instead of silently moving published P&L.
    """
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
