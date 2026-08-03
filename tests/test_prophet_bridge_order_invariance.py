"""tests/test_prophet_bridge_order_invariance.py — the bridge intake is order-invariant.

`engine.prophet_bridge.select_candidates` reads `us_standouts.json["buy"]` and returns the
plans the Prophet lane will originate. Its sort key was `(-score, -act_level)`, which is NOT a
total order: any two rows tied on both legs were left in the ARTIFACT's incoming order by
Python's stable sort. That made the intake silently producer-dependent — a board re-emitted
with `buy[]` in a different order could originate a DIFFERENT set of plans, with different
plan IDs, on identical data. The fix appends `ticker` as the final key.

Everything here shuffles the INPUT and asserts the OUTPUT does not move; the source itself
contains no shuffling. Three things are pinned:

  A. Order stability   — the returned ticker sequence is byte-identical across seeds.
  B. Cutoff membership — when more rows tie than fit in `n`, WHICH rows survive `[:n]` is
                         also fixed (the failure that actually changes what gets traded).
  C. Key precedence    — ticker is the LAST key: score still beats act_level, and act_level
                         still beats ticker. A ticker leg promoted too early would pass A+B
                         while silently re-ranking the board.

Plus a counterfactual (`TestTheFixtureCanSeeTheDefect`) that runs the OLD two-leg key over the
same shuffles and asserts it DOES drift — without it, A and B would pass on a fixture whose
rows never actually tie, and the test would be pinning nothing.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

# ── repo path ─────────────────────────────────────────────────────────────────
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.prophet_bridge import N_CANDIDATES, select_candidates  # noqa: E402

SEEDS = (0, 1, 2, 3, 5, 7, 11, 13, 17, 23, 42, 1337)


# ---------------------------------------------------------------------------
# Fixture (data only — the function under test is imported)
# ---------------------------------------------------------------------------

def _buy(ticker: str, *, score: int, act_level: int, band: str = "neutral",
         dir_: str = "up") -> dict:
    """One `us_standouts.json["buy"]` row, trimmed to the fields the pick rule reads."""
    return {
        "ticker": ticker,
        "dir": dir_,
        "conviction": {"score": score, "band": band},
        "entry_signal": {"act_level": act_level, "status": "partial", "spot": 100.0},
    }


def _standouts(buys: list[dict], *, gate_go: bool = True) -> dict:
    return {"as_of": "2026-07-31", "gate_go": gate_go, "buy": buys}


# Nine rows with distinct scores — the uncontested head of the board.
_HEAD = [_buy(f"H{i}", score=95 - i, act_level=3) for i in range(9)]
# Eight rows tied on BOTH legs — only (N_CANDIDATES - 9) = 3 of them fit.
# Deliberately listed Z→A so an order-dependent implementation picks the WRONG three.
_TIED = [_buy(f"TIE_{ch}", score=70, act_level=2)
         for ch in reversed("ABCDEFGH")]
# Three rows that must never be reached (the cutoff is spent above them).
_TAIL = [_buy(f"L{i}", score=61 + i, act_level=2) for i in range(3)]

_BUYS = _HEAD + _TIED + _TAIL

_EXPECTED_HEAD = [f"H{i}" for i in range(9)]
_EXPECTED_TIED = ["TIE_A", "TIE_B", "TIE_C"]


def _shuffled(seed: int) -> list[dict]:
    rows = [dict(b) for b in _BUYS]
    random.Random(seed).shuffle(rows)
    return rows


def _tickers(rows: list[dict]) -> list[str]:
    return [r["ticker"] for r in rows]


# ---------------------------------------------------------------------------
# A. Order stability
# ---------------------------------------------------------------------------

class TestSelectionIsOrderInvariant:

    def test_shuffled_input_yields_an_identical_selection(self):
        """The whole point: shuffle `buy[]`, get the same list every time."""
        baseline = _tickers(select_candidates(_standouts(_BUYS)))
        for seed in SEEDS:
            got = _tickers(select_candidates(_standouts(_shuffled(seed))))
            assert got == baseline, f"selection moved under shuffle seed {seed}"

    def test_the_reversed_artifact_is_the_same_selection(self):
        """The adversarial permutation, named explicitly — a producer that emits the
        board bottom-up must not change a single pick."""
        assert (_tickers(select_candidates(_standouts(list(reversed(_BUYS)))))
                == _tickers(select_candidates(_standouts(_BUYS))))

    def test_the_selection_is_the_expected_deterministic_list(self):
        """Pin the VALUE, not just its stability — a `select_candidates` that returned
        [] or the input unchanged would satisfy the equality tests above."""
        got = _tickers(select_candidates(_standouts(_BUYS)))
        assert got == _EXPECTED_HEAD + _EXPECTED_TIED
        assert len(got) == N_CANDIDATES

    def test_tied_rows_come_back_in_ticker_order(self):
        """Two rows tied on both legs sort A→Z, whichever way they arrive."""
        pair = [_buy("ZZZZ", score=88, act_level=3), _buy("AAAA", score=88, act_level=3)]
        assert _tickers(select_candidates(_standouts(pair))) == ["AAAA", "ZZZZ"]
        assert _tickers(select_candidates(_standouts(pair[::-1]))) == ["AAAA", "ZZZZ"]


# ---------------------------------------------------------------------------
# B. Cutoff membership — the failure that changes what gets traded
# ---------------------------------------------------------------------------

class TestCutoffMembershipIsOrderInvariant:

    def test_which_tied_rows_survive_the_cap_is_fixed(self):
        """`selected[:n]` slices a tie group. If the tie is order-resolved, the plans
        ORIGINATED differ between two emissions of the same board."""
        for seed in SEEDS:
            got = _tickers(select_candidates(_standouts(_shuffled(seed))))
            survivors = [t for t in got if t.startswith("TIE_")]
            assert survivors == _EXPECTED_TIED, f"cutoff membership moved on seed {seed}"

    def test_the_fixture_really_overfills_the_cap(self):
        """Keeps the test above honest: if the tie group ever fits entirely inside `n`,
        the slice stops discriminating and the assertion becomes vacuous."""
        assert len(_TIED) > N_CANDIDATES - len(_HEAD) > 0

    def test_every_tied_row_is_individually_selectable(self):
        """And that the losers lose on the CAP, not on the gate — a tie member that was
        being filtered out would make the membership assertion trivially true."""
        for row in _TIED:
            solo = _tickers(select_candidates(_standouts([row])))
            assert solo == [row["ticker"]]


# ---------------------------------------------------------------------------
# C. Key precedence — ticker is the LAST leg
# ---------------------------------------------------------------------------

class TestTickerIsTheFinalKeyOnly:

    def test_score_still_outranks_ticker(self):
        buys = [_buy("AAAA", score=60, act_level=3), _buy("ZZZZ", score=90, act_level=3)]
        assert _tickers(select_candidates(_standouts(buys))) == ["ZZZZ", "AAAA"]

    def test_act_level_still_outranks_ticker(self):
        buys = [_buy("AAAA", score=80, act_level=2), _buy("ZZZZ", score=80, act_level=3)]
        assert _tickers(select_candidates(_standouts(buys))) == ["ZZZZ", "AAAA"]

    def test_a_missing_ticker_sorts_without_raising(self):
        """Real artifacts have shipped rows with no ticker; the key must degrade, not
        crash the whole Prophet intake on a TypeError."""
        buys = [_buy("MMMM", score=75, act_level=3), _buy("AAAA", score=75, act_level=3)]
        buys.append({k: v for k, v in _buy("X", score=75, act_level=3).items()
                     if k != "ticker"})
        got = select_candidates(_standouts(buys))
        assert [r.get("ticker") for r in got] == [None, "AAAA", "MMMM"]


# ---------------------------------------------------------------------------
# The counterfactual — proof this fixture can see the defect
# ---------------------------------------------------------------------------

class TestTheFixtureCanSeeTheDefect:

    @staticmethod
    def _old_rule(buys: list[dict]) -> list[str]:
        """The pre-fix key, verbatim: `(-score, -act_level)` with no identity leg.
        Admission is not re-implemented — every fixture row passes the gate_go=True
        rule (act_level >= 2, band != 'low'), which the class above proves per-row."""
        rows = list(buys)
        rows.sort(key=lambda x: (
            -(x.get("conviction") or {}).get("score", 0),
            -((x.get("entry_signal") or {}).get("act_level") or 0),
        ))
        return [r["ticker"] for r in rows[:N_CANDIDATES]]

    def test_the_two_leg_key_drifts_on_the_same_shuffles(self):
        """If this ever stops drifting, the fixture has lost its ties and every
        order-invariance assertion above has quietly become a tautology."""
        seen = {tuple(self._old_rule(_shuffled(seed))) for seed in SEEDS}
        assert len(seen) > 1, (
            "the pre-fix sort key produced ONE selection across every shuffle — the "
            "fixture no longer contains a (score, act_level) tie, so it can no longer "
            "detect an order-dependent intake")

    def test_the_two_leg_key_also_drifts_at_the_cutoff(self):
        """Not just cosmetic reordering — the pre-fix key changes WHICH rows ship."""
        seen = {frozenset(self._old_rule(_shuffled(seed))) for seed in SEEDS}
        assert len(seen) > 1, (
            "the pre-fix sort key selected the same MEMBERSHIP under every shuffle — "
            "the tie group no longer straddles the N_CANDIDATES cutoff")
