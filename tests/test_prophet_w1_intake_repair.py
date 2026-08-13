"""tests/test_prophet_w1_intake_repair.py — Prophet US W1 plan-intake repair.

Three changes, each pinned separately
(research/PROPHET_US_TREND_INTELLIGENCE_MASTERPLAN_BY_FABLE.md §5 W1):

  1. ORDER — `select_candidates` ranks by the us_prophet_v1 priority score
     (`row["prophet"]["score"]`, engine/us_board_rank.py #4331) instead of raw
     `conviction.score`.  This is a SCORED change; it cites the Grade-A
     "Primary sort key" ruling in research/US_BOARD_MEASUREMENT.md (retro board/
     conviction order P@1 0.20 vs alpha-order 0.60).  Rows with no numeric
     priority score fall back to the OLD key, below every scored row.

  2. BLOCK — an OPEN plan on the same ticker+direction blocks re-origination.
     The plan id carries signal_date, so a fresh signal used to originate a
     SECOND plan for a name that was already live (10 ticker+direction pairs
     held duplicate open plans on 2026-08-03; PI held three).

  3. INDEX HYGIENE — every shipped plan carries `age_days` + a plain-word
     `pulse`/`pulse_zh`, and the index carries `active_count_by_age`.  Additive
     only: no plan is removed or re-ordered (population fence G0.4).

THE POPULATION FENCE, AND WHAT SUPERSEDED IT (ANTICIPATION A1, 2026-08-08)
--------------------------------------------------------------------------
W1's "ordering only" claim was that the ADMITTED population — the rows clearing
the band / act_level / score / dir / entry_signal gates — is byte-identical to
the pre-W1 rule.  `_old_select` below is that rule, copied verbatim, and it used
to be asserted against the LIVE `select_candidates`.

ANTICIPATION §6.2 A1 deliberately moved the population: admission is now a STATUS
CLASS (patience = bounce_wait/wait_pullback/hold, confirmation = buy_now/partial)
and the act-level gate is gone.  The W1 fence is therefore re-pointed rather than
deleted — `_old_select` is now asserted against `engine.prophet_bridge.legacy_admitted`,
the frozen copy of the same rule that keeps feeding the zero-authority shadow
ledger, so W1's guarantee is still pinned against the thing that still makes it.
`TestA1MovedThePopulationDeliberately` pins the move itself, so a silent
regression back to the act-level gate fails here too.

Everything else in this file — the priority-score ordering, the legacy fallback,
the re-origination block, index hygiene — is untouched by A1 and still live.

The uncapped half of W1's own repair (P4, then #5071's lossless origination) is
also untouched: live `originate_plans` requests the uncapped population and
originates every surviving row, so the 12-row helper sample below is a research
slice and never an opportunity gate.
"""
from __future__ import annotations

import json
import random
import sys
from collections.abc import Mapping
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

# ── repo path ─────────────────────────────────────────────────────────────────
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import scripts.build_prophet as bp  # noqa: E402
from engine.prophet_bridge import (  # noqa: E402
    LEGACY_N_CANDIDATES,
    N_CANDIDATES,
    legacy_admitted,
    originate_plans,
    plan_key,
    select_candidates,
)

@pytest.fixture(autouse=True)
def _arena_writes_to_tmp(tmp_path, monkeypatch):
    """Send the Prophet Arena's ledgers to tmp for every test in this file.

    `build_prophet.main()` calls `engine.prophet_arena.run_arena(..., repo_root=_REPO)`,
    which writes `data/prophet_arena/{C0..C6}.jsonl` + `scoreboard.json`. The `bp.main()`
    harness below carefully redirects STANDOUTS_PATH / SITE_PROPHET / PLANS_DIR /
    STATES_DIR / INDEX_PATH / LEDGER_* and neuters `write_showcase` — but the arena hook
    landed after that list was written and was never added to it, so the suite rewrote
    seven TRACKED files. MM_DATA_GUARD forced ci-pack-3 to exit 1 on a step reporting
    "942 passed", which is why it read as a mystery rather than a test failure.

    Redirects `repo_root` rather than stubbing `run_arena` out, so the hook still executes
    end-to-end here; the arena's own behaviour is covered by tests/test_prophet_arena.py.
    Autouse because `bp.main()` is reached from several tests, and the next one added
    would silently reintroduce the write.
    """
    import engine.prophet_arena as arena

    real = arena.run_arena
    monkeypatch.setattr(
        arena, "run_arena",
        lambda *a, **kw: real(*a, **{**kw, "repo_root": tmp_path}))


COMMITTED_STANDOUTS = _REPO / "site" / "factordata" / "us_standouts.json"
SEEDS = (0, 1, 2, 3, 5, 7, 11, 13, 17, 23, 42, 1337)


# ---------------------------------------------------------------------------
# The pre-W1 rule, copied VERBATIM from engine/prophet_bridge.py@origin/main.
# Re-implemented rather than imported so the comparison is against the shipped
# behaviour and survives every later edit to the live function.
#
# "Verbatim" was FALSE for the tier_cascade clause below, and silently so from
# #5071 (which added it to `select_candidates`) through #5105 (which re-pointed
# this copy at `legacy_admitted` without porting it).  Two rules that differ by
# a filter nothing on the board can trip are indistinguishable from two rules
# that agree, so the fence read green for two PRs and detonated the night the
# first discriminating row arrived: `us_standouts.json` as_of 2026-08-12 carries
# SWX at `signal.tier_cascade == "T4"` -- the first non-T1/T2/T3 buy row ever
# published (histogram that night: T1 35, T2 28, T4 1, absent 8).  The engine was
# right and stayed right; this copy admitted 24 rows where the frozen rule admits
# 23, and `test_committed_artifact_admits_the_identical_rows` correctly said so.
#
# The clause is part of the rule being copied, not an implementation detail: it
# predates the freeze (pre-A1 `select_candidates` carried it with the comment
# "actionable contract has always been T1-T3 (signal_gate.BUYABLE_TIERS)") and
# `legacy_admitted`'s own docstring names it. Restoring it makes the transcription
# true rather than loosening what the fence asserts. It is a no-op on every
# synthetic fixture here -- `_buy()` emits no `signal` block at all -- so the only
# call sites it can move are the two that read the committed artifact.
# ---------------------------------------------------------------------------

def _old_select(standouts: dict, n: int = N_CANDIDATES) -> list[dict]:
    gate_go: bool = standouts.get("gate_go", False)
    buys: list[dict] = standouts.get("buy", [])

    selected: list[dict] = []
    for b in buys:
        es = b.get("entry_signal")
        if not es:
            continue
        if b.get("dir", "up") != "up":
            continue
        conv = b.get("conviction") or {}
        band = conv.get("band", "")
        score = conv.get("score", 0) or 0
        act_level = es.get("act_level", 0) or 0

        if band == "low":
            continue

        # Rows predating `tier_cascade` keep their prior behaviour (the clause is
        # skipped when the key is absent or null), which is why this was invisible.
        signal = b.get("signal")
        if isinstance(signal, Mapping):
            signal_tier = signal.get("tier_cascade")
            if signal_tier is not None and signal_tier not in ("T1", "T2", "T3"):
                continue

        if gate_go:
            if not (act_level >= 2):
                continue
        else:
            if not (act_level >= 2 or score >= 60):
                continue

        selected.append(b)

    selected.sort(key=lambda x: (
        -(x.get("conviction") or {}).get("score", 0),
        -((x.get("entry_signal") or {}).get("act_level") or 0),
        str(x.get("ticker") or ""),
    ))
    return selected[:n]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_UNCAPPED = 10 ** 9  # "no cap" — isolates the FILTERS from the [:n] slice


def _buy(
    ticker: str,
    *,
    priority: float | None = None,
    score: int = 70,
    act_level: int = 3,
    band: str = "neutral",
    dir_: str = "up",
    spot: float = 100.0,
    anchor: str | None = "2026-07-02",
    entry_signal: dict | None = "keep",  # type: ignore[assignment]
) -> dict:
    """One `us_standouts.json["buy"]` row.

    `priority=None` emits NO `prophet` block at all — a pre-us_prophet_v1 row.
    """
    row: dict = {
        "ticker": ticker,
        "dir": dir_,
        "conviction": {
            "score": score,
            "band": band,
            "drivers": ["momentum"],
            "cautions": ["macro risk"],
            "trust_tier": {"en": "tier-2"},
        },
        "entry_signal": {
            "act_level": act_level,
            "status": "partial",
            "spot": spot,
            "chase_above": spot * 1.03,
            "atr_pct": 2.0,
            "entry_grade": "solid",
        },
        "hold": {"state": "HOLD", "anchor": anchor, "invalidation": spot * 0.9},
    }
    if entry_signal != "keep":
        row["entry_signal"] = entry_signal
    if priority is not None:
        row["prophet"] = {"version": "us_prophet_v1", "score": priority}
    return row


def _standouts(buys: list[dict], *, gate_go: bool = True, as_of: str = "2026-07-02") -> dict:
    return {
        "as_of": as_of,
        "staleness": {
            "price_through": as_of, "delayed": False, "unknown": False,
            "basis": "panel_majority",
            "inputs": {"panel": {"mixed_vintage": False}},
        },
        "gate_go": gate_go,
        "buy": buys,
    }


def _tickers(rows: list[dict]) -> list[str]:
    return [str(r.get("ticker")) for r in rows]


@pytest.fixture(scope="module")
def committed() -> dict:
    """The real nightly artifact — the operator's review surface for this change."""
    if not COMMITTED_STANDOUTS.exists():
        pytest.skip("committed us_standouts.json absent")
    return json.loads(COMMITTED_STANDOUTS.read_text(encoding="utf-8"))


# ===========================================================================
# 1a. POPULATION FENCE — the filters did not move
# ===========================================================================

class TestAdmittedPopulationIsUnchanged:
    """W1's fence, re-pointed at the FROZEN copy of the rule it was written against.

    `legacy_admitted` is the pre-W1 gate verbatim and is what the ANTICIPATION §6.5
    shadow ledger runs every night, so pinning it here keeps W1's guarantee alive on
    the only code path that still claims it.
    """

    def test_committed_artifact_admits_the_identical_rows(self, committed):
        """Same input, same admitted population — for the LEGACY gate."""
        old = _old_select(committed, n=_UNCAPPED)
        new = legacy_admitted(committed)
        assert {id(r) for r in old} == {id(r) for r in new}, (
            "the frozen legacy gate drifted from the pre-W1 rule it copies")
        assert sorted(_tickers(old)) == sorted(_tickers(new))

    def test_the_committed_fixture_actually_filters_something(self, committed):
        """Keeps the test above honest: if every buy row were admitted, an identical
        population would prove nothing about the gates."""
        admitted = legacy_admitted(committed)
        assert 0 < len(admitted) < len(committed["buy"]), (
            "the committed artifact admits everything (or nothing) — the population "
            "equality assertion above has gone vacuous")

    @pytest.mark.parametrize("gate_go", [True, False])
    def test_every_gate_leg_admits_identically(self, gate_go):
        """Each exclusion path — band, act_level, score, dir, null entry_signal — is
        exercised, and the pre-W1 rule and the frozen copy agree row-for-row."""
        buys = [
            _buy("BANDLOW", priority=99.0, score=95, act_level=3, band="low"),
            _buy("ACT1LOWSCORE", priority=98.0, score=40, act_level=1),
            _buy("ACT1HIGHSCORE", priority=97.0, score=65, act_level=1),
            _buy("BEAR", priority=96.0, score=90, act_level=3, dir_="down"),
            _buy("NOENTRY", priority=95.0, score=90, act_level=3, entry_signal=None),
            _buy("CLEAN", priority=10.0, score=61, act_level=2),
            _buy("LEGACY", priority=None, score=88, act_level=3),
        ]
        s = _standouts(buys, gate_go=gate_go)
        assert sorted(_tickers(legacy_admitted(s))) == \
               sorted(_tickers(_old_select(s, n=_UNCAPPED)))
        # And the fixture really does exclude — otherwise the equality is trivial.
        admitted = set(_tickers(legacy_admitted(s)))
        assert {"BANDLOW", "ACT1LOWSCORE", "BEAR", "NOENTRY"}.isdisjoint(admitted)
        assert "CLEAN" in admitted and "LEGACY" in admitted
        assert ("ACT1HIGHSCORE" in admitted) is (gate_go is False)

    def test_capped_membership_is_identical_when_the_pool_fits(self):
        """When the admitted pool does not overflow N_CANDIDATES, the shipped
        candidate SET is identical too — the only thing that moved is its order."""
        buys = [_buy(f"T{i:02d}", priority=float(i), score=100 - i, act_level=3)
                for i in range(N_CANDIDATES - 2)]
        s = _standouts(buys)
        old, new = _old_select(s, n=_UNCAPPED), select_candidates(s)
        assert set(_tickers(old)) == set(_tickers(new))
        assert _tickers(old) != _tickers(new), (
            "the fixture no longer re-orders anything — it cannot show that a set "
            "equality survives a genuine ordering change")

    def test_the_helper_sample_and_the_frozen_shadow_cap(self):
        """Research comparisons keep their old slice; live origination passes n=None.

        A1's other half — "cap 12→16, sector cap 4" — is SUPERSEDED by #5071's
        lossless origination and is deliberately NOT ported: there is no positional
        plan-origination cap at all any more, so widening one would be re-introducing
        the thing that was removed.  The LEGACY arm's cap stays frozen at the old
        value so the shadow ledger keeps grading the book the old gate would have
        built.
        """
        assert N_CANDIDATES == 12
        assert LEGACY_N_CANDIDATES == 12
        buys = [_buy(f"T{i:02d}", priority=float(90 - i), score=90 - i) for i in range(30)]
        assert len(select_candidates(_standouts(buys))) == N_CANDIDATES


# ===========================================================================
# 1a-bis. A1 moved the population ON PURPOSE — pinned so it cannot drift back
# ===========================================================================

class TestA1MovedThePopulationDeliberately:
    """The counterpart to the fence above: the live gate is NOT the legacy gate.

    Without this, a regression that reinstated `act_level >= 2` would leave every
    remaining assertion in this file green.
    """

    def test_the_live_gate_admits_patience_the_legacy_gate_cannot_reach(self):
        buys = [_buy("PATIENCE", priority=90.0, score=5, act_level=0)]
        buys[0]["entry_signal"]["status"] = "bounce_wait"
        buys[0]["dir"] = "caution"
        s = _standouts(buys, gate_go=True)
        assert _tickers(select_candidates(s, n=_UNCAPPED)) == ["PATIENCE"]
        assert legacy_admitted(s) == []

    def test_the_live_gate_refuses_buy_soon_the_legacy_gate_admitted(self):
        buys = [_buy("SOON", priority=90.0, score=90, act_level=2)]
        buys[0]["entry_signal"]["status"] = "buy_soon"
        s = _standouts(buys, gate_go=True)
        assert select_candidates(s, n=_UNCAPPED) == []
        assert _tickers(legacy_admitted(s)) == ["SOON"]

    def test_the_committed_artifact_shows_the_move(self, committed):
        live = {t for t in _tickers(select_candidates(committed, n=_UNCAPPED))}
        legacy = {t for t in _tickers(legacy_admitted(committed))}
        assert live != legacy, (
            "the live and legacy gates agree on the committed board — either A1 "
            "regressed or the board no longer carries a patience cohort")


# ===========================================================================
# 1b. ORDER — priority score is the primary key
# ===========================================================================

class TestPriorityScoreOrdersIntake:

    def test_priority_score_outranks_conviction_score(self):
        """The change itself: the row the BOARD ranks first is picked first, even
        when the conviction score says the opposite."""
        buys = [
            _buy("CONVICTION_KING", priority=40.0, score=95),
            _buy("PRIORITY_KING", priority=90.0, score=41),
        ]
        assert _tickers(select_candidates(_standouts(buys))) == \
               ["PRIORITY_KING", "CONVICTION_KING"]
        assert _tickers(_old_select(_standouts(buys))) == \
               ["CONVICTION_KING", "PRIORITY_KING"], "fixture no longer separates the keys"

    def test_the_committed_artifact_really_reorders(self, committed):
        """Fixture-can-see-the-defect: if old and new ever agree on the real board,
        every assertion in this class has gone vacuous on live data."""
        old, new = _tickers(_old_select(committed)), _tickers(select_candidates(committed))
        assert old != new, (
            "old and new orders match on the committed artifact — either prophet.score "
            "has become a monotone function of conviction.score, or the new key is not "
            "being read at all")

    def test_ties_break_on_act_level_then_ticker(self):
        buys = [
            _buy("ZZ", priority=80.0, score=10, act_level=3),
            _buy("AA", priority=80.0, score=99, act_level=3),
            _buy("MM", priority=80.0, score=50, act_level=2),
        ]
        assert _tickers(select_candidates(_standouts(buys))) == ["AA", "ZZ", "MM"]

    def test_the_order_is_invariant_under_input_shuffle(self):
        """Determinism: the artifact's incoming buy[] order must never decide a tie."""
        letters = "ABCDEFGHIJ"
        buys = ([_buy(f"H{i}", priority=float(95 - i), score=i) for i in range(9)]
                + [_buy(f"TIE_{c}", priority=70.0, score=50, act_level=2)
                   for c in reversed(letters)])
        # Derived from the cap, never hardcoded: this test is about the TIE-BREAK,
        # and a literal slice silently stops slicing the tie group when the cap moves.
        expected_ties = [f"TIE_{c}" for c in letters][:N_CANDIDATES - 9]
        assert 0 < len(expected_ties) < len(letters), "the cap must slice the tie group"
        baseline = _tickers(select_candidates(_standouts(buys)))
        assert baseline[9:] == expected_ties, "the cap must slice the tie group"
        for seed in SEEDS:
            rows = [dict(b) for b in buys]
            random.Random(seed).shuffle(rows)
            assert _tickers(select_candidates(_standouts(rows))) == baseline, \
                f"selection moved under shuffle seed {seed}"

    def test_a_missing_ticker_still_sorts_without_raising(self):
        rows = [_buy("MMMM", priority=75.0), _buy("AAAA", priority=75.0)]
        rows.append({k: v for k, v in _buy("X", priority=75.0).items() if k != "ticker"})
        got = select_candidates(_standouts(rows))
        assert [r.get("ticker") for r in got] == [None, "AAAA", "MMMM"]


# ===========================================================================
# 1c. LEGACY FALLBACK — a pre-v1 artifact behaves exactly as it does today
# ===========================================================================

class TestLegacyRowsSelfHeal:

    def test_a_wholly_legacy_artifact_selects_byte_identically(self):
        """No prophet block anywhere → the shipped list is the OLD list, in order."""
        buys = [_buy(f"L{i}", priority=None, score=90 - i * 3, act_level=(i % 2) + 2)
                for i in range(20)]
        s = _standouts(buys)
        assert _tickers(select_candidates(s)) == _tickers(_old_select(s))

    def test_legacy_rows_sort_below_every_scored_row(self):
        """Even a 99-conviction legacy row yields to the weakest priority-scored one:
        mixing the two keys in one ranking would compare incomparable numbers."""
        buys = [
            _buy("LEGACY_HIGH", priority=None, score=99),
            _buy("SCORED_LOW", priority=1.0, score=5),
        ]
        assert _tickers(select_candidates(_standouts(buys))) == ["SCORED_LOW", "LEGACY_HIGH"]

    def test_legacy_rows_keep_the_old_order_among_themselves(self):
        buys = [
            _buy("SCORED", priority=50.0, score=1),
            _buy("LEG_LOW", priority=None, score=20, act_level=3),
            _buy("LEG_HIGH", priority=None, score=80, act_level=2),
            _buy("LEG_MID", priority=None, score=50, act_level=2),
        ]
        assert _tickers(select_candidates(_standouts(buys))) == \
               ["SCORED", "LEG_HIGH", "LEG_MID", "LEG_LOW"]

    @pytest.mark.parametrize("bad", [
        None, "88.9", True, False, float("nan"), float("inf"), {"score": 1}, [],
    ])
    def test_an_unusable_priority_score_falls_back_instead_of_ranking(self, bad):
        """A string/bool/NaN score must not be coerced into a rank — `True` would
        read as 1.0 and a NaN would make the sort order undefined."""
        buys = [
            _buy("BAD", priority=None, score=99),
            _buy("GOOD", priority=2.0, score=1),
        ]
        buys[0]["prophet"] = {"version": "us_prophet_v1", "score": bad}
        assert _tickers(select_candidates(_standouts(buys))) == ["GOOD", "BAD"]

    def test_a_prophet_block_that_is_not_a_dict_is_ignored(self):
        row = _buy("WEIRD", priority=None, score=99)
        row["prophet"] = "us_prophet_v1"
        buys = [row, _buy("GOOD", priority=2.0, score=1)]
        assert _tickers(select_candidates(_standouts(buys))) == ["GOOD", "WEIRD"]

    def test_a_zero_priority_score_is_a_score_not_a_missing_one(self):
        """0.0 is a real rank (the floor), not an absent key — a `score or None`
        style read would silently demote every floored row to the legacy tier."""
        buys = [_buy("ZERO", priority=0.0, score=1), _buy("LEGACY", priority=None, score=99)]
        assert _tickers(select_candidates(_standouts(buys))) == ["ZERO", "LEGACY"]


# ===========================================================================
# 2. RE-ORIGINATION BLOCK — one open plan per ticker+direction
# ===========================================================================

def _write_standouts(tmp_path: Path, buys: list[dict], **kw) -> Path:
    path = tmp_path / "us_standouts.json"
    path.write_text(json.dumps(_standouts(buys, **kw)), encoding="utf-8")
    return path


class TestOpenPlanKeys:
    """`build_prophet.open_plan_keys` — closure comes from the forward ledger."""

    def test_open_plans_produce_keys_and_closed_ones_do_not(self):
        plans = {
            "CLF-BULL-20260701": {"asset": "CLF", "direction": "BULL"},
            "CLF-BULL-20260715": {"asset": "CLF", "direction": "BULL"},
            "PI-BULL-20260620":  {"asset": "PI", "direction": "BULL"},
        }
        assert bp.open_plan_keys(plans, set()) == {"CLF-BULL", "PI-BULL"}
        assert bp.open_plan_keys(plans, {"PI-BULL-20260620"}) == {"CLF-BULL"}
        assert bp.open_plan_keys(plans, set(plans)) == set()

    def test_direction_is_part_of_the_key(self):
        plans = {
            "AAPL-BULL-20260701": {"asset": "AAPL", "direction": "BULL"},
            "AAPL-BEAR-20260701": {"asset": "AAPL", "direction": "BEAR"},
        }
        assert bp.open_plan_keys(plans, set()) == {"AAPL-BULL", "AAPL-BEAR"}

    def test_a_plan_missing_its_asset_or_direction_is_skipped_not_crashed(self):
        plans = {
            "BROKEN-1": {"direction": "BULL"},
            "BROKEN-2": {"asset": "AAPL"},
            "OK": {"asset": "aapl", "direction": "bull"},
        }
        assert bp.open_plan_keys(plans, set()) == {"AAPL-BULL"}  # and case-normalised

    def test_plan_key_normalises_case_and_whitespace(self):
        assert plan_key(" clf ", "bull") == plan_key("CLF", "BULL") == "CLF-BULL"


class TestReoriginationBlock:

    def test_an_open_plan_blocks_a_fresh_signal_on_the_same_name(self, tmp_path):
        """The defect, reproduced: a NEW signal_date on a live name used to originate
        a second plan and burn one of the 12 slots."""
        # `as_of` matches the run date: the board a nightly reads is the board that
        # nightly built.  Leaving it at the 2026-07-02 default made the run 9 sessions
        # ahead of its own artifact, which the A1 publication-lag guard correctly
        # refuses to price (these synthetic tickers have no price history to re-derive
        # from) — a fixture artefact, not the behaviour under test here.
        path = _write_standouts(
            tmp_path,
            [_buy("CLF", priority=90.0, anchor="2026-07-15"),
             _buy("NEWNAME", priority=80.0, anchor="2026-07-15")],
            as_of="2026-07-15",
        )
        stats: dict = {}
        plans = originate_plans(
            path, "2026-07-15", set(), None,
            active_keys={"CLF-BULL"}, intake_stats=stats,
        )
        assert [p["asset"] for p in plans] == ["NEWNAME"]
        assert stats["reorigination_blocked"] == 1
        assert stats["reorigination_blocked_keys"] == ["CLF-BULL"]

    def test_the_same_input_without_the_block_originates_both(self, tmp_path):
        """Counterfactual — proves the fixture's CLF row is otherwise admissible, so
        the assertion above pins the block and not an unrelated exclusion."""
        path = _write_standouts(
            tmp_path,
            [_buy("CLF", priority=90.0, anchor="2026-07-15"),
             _buy("NEWNAME", priority=80.0, anchor="2026-07-15")],
            as_of="2026-07-15",
        )
        plans = originate_plans(path, "2026-07-15", set(), None)
        assert sorted(p["asset"] for p in plans) == ["CLF", "NEWNAME"]

    def test_a_closed_plan_frees_the_slot(self, tmp_path):
        """`open_plan_keys` drops a ledger-closed plan, so the name is originatable
        again — the block is a while-active hold, not a permanent ban."""
        existing = {"CLF-BULL-20260601": {"asset": "CLF", "direction": "BULL"}}
        path = _write_standouts(
            tmp_path, [_buy("CLF", priority=90.0, anchor="2026-07-15")],
            as_of="2026-07-15",
        )
        blocked = originate_plans(
            path, "2026-07-15", set(),
            active_keys=bp.open_plan_keys(existing, set()),
        )
        assert blocked == []
        admitted = originate_plans(
            path, "2026-07-15", set(),
            active_keys=bp.open_plan_keys(existing, {"CLF-BULL-20260601"}),
        )
        assert [p["asset"] for p in admitted] == ["CLF"]

    def test_same_id_suppression_is_not_counted_as_a_block(self, tmp_path):
        """The disclosure must count the NEW failure mode only.  A candidate whose id
        already exists was always suppressed; folding it in would inflate the number
        the operator reads."""
        path = _write_standouts(tmp_path, [_buy("CLF", priority=90.0, anchor="2026-07-02")])
        stats: dict = {}
        plans = originate_plans(
            path, "2026-07-02", {"CLF-BULL-20260702"}, None,
            active_keys={"CLF-BULL"}, intake_stats=stats,
        )
        assert plans == []
        assert stats["reorigination_blocked"] == 0

    def test_the_block_is_off_by_default(self, tmp_path):
        """`active_keys=None` keeps every pre-W1 caller (and every prior test) intact."""
        path = _write_standouts(
            tmp_path, [_buy("CLF", priority=90.0, anchor="2026-07-15")],
            as_of="2026-07-15",
        )
        stats: dict = {}
        plans = originate_plans(path, "2026-07-15", set(), None, intake_stats=stats)
        assert [p["asset"] for p in plans] == ["CLF"]
        assert stats["reorigination_blocked"] == 0

    def test_stats_are_reported_even_when_nothing_was_blocked(self, tmp_path):
        """A missing key would read as "no disclosure" rather than "zero skips"."""
        path = _write_standouts(
            tmp_path, [_buy("AAA", priority=90.0, anchor="2026-07-15")],
            as_of="2026-07-15",
        )
        stats: dict = {}
        originate_plans(path, "2026-07-15", set(), None,
                        active_keys={"ZZZ-BULL"}, intake_stats=stats)
        assert stats["reorigination_blocked"] == 0
        assert stats["reorigination_blocked_keys"] == []
        # Every disposition is explicit even though live origination has no cap.
        assert stats["admitted"] == 1
        assert stats["duplicate_id_blocked"] == 0
        assert stats["eligible_after_skips"] == 1
        assert stats["cap"] is None
        assert stats["cap_applied"] is False
        assert stats["truncated"] == 0
        assert stats["validation_failed"] == 0
        assert stats["originated"] == 1
        assert stats["unaccounted"] == 0
        assert stats["lossless"] is True

    def test_every_survivor_below_the_old_cutoff_originates(self, tmp_path):
        """Duplicates and open plans are dispositions, not reasons to stop at row 12."""
        buys = [
            _buy(
                f"T{i:02d}",
                priority=float(100 - i),
                anchor="2026-07-15",
                spot=100.0 + i,
            )
            for i in range(N_CANDIDATES + 6)
        ]
        path = _write_standouts(tmp_path, buys, as_of="2026-07-15")
        stats: dict = {}
        plans = originate_plans(
            path,
            "2026-07-15",
            {"T00-BULL-20260715"},
            None,
            active_keys={"T01-BULL"},
            intake_stats=stats,
        )

        assert len(plans) == len(buys) - 2 > N_CANDIDATES
        assert [plan["asset"] for plan in plans][-1] == f"T{len(buys) - 1:02d}"
        assert stats["duplicate_id_blocked"] == 1
        assert stats["reorigination_blocked"] == 1
        assert stats["eligible_after_skips"] == len(plans)
        assert stats["originated"] == len(plans)
        assert stats["truncated"] == 0
        assert stats["lossless"] is True


# ===========================================================================
# 3. INDEX HYGIENE — aging + pulse
# ===========================================================================

class TestAgeAndPulse:

    @pytest.mark.parametrize("signal_date,asof,expected", [
        ("2026-07-01", "2026-07-31", 30),
        ("2026-07-31", "2026-07-31", 0),
        ("2026-08-05", "2026-07-31", 0),      # clamped, never negative
        (None, "2026-07-31", None),
        ("garbage", "2026-07-31", None),
        ("2026-07-01T00:00:00Z", "2026-07-31", 30),
    ])
    def test_age_days(self, signal_date, asof, expected):
        assert bp._age_days(signal_date, asof) == expected

    @pytest.mark.parametrize("age,bucket", [
        (0, "le_7d"), (7, "le_7d"), (8, "d8_21d"), (21, "d8_21d"),
        (22, "gt_21d"), (138, "gt_21d"), (None, "unknown"),
    ])
    def test_age_bucket_boundaries(self, age, bucket):
        assert bp._age_bucket(age) == bucket

    def test_pulse_reads_like_the_brief(self):
        assert bp._plan_pulse(32, "triggered_pre_t1", "Stalling")[0] == \
               "32d · triggered · stalling"

    def test_pulse_ships_a_zh_pair(self):
        en, zh = bp._plan_pulse(32, "triggered_pre_t1", "Stalling")
        assert en and zh and zh != en
        assert en.count(" · ") == zh.count(" · ")

    def test_pulse_never_prints_a_raw_phase_slug(self):
        """Glance-tier word law: `triggered_pre_t1` is an internal state name."""
        for phase in [*bp._PHASE_WORD, "some_future_phase", ""]:
            en, zh = bp._plan_pulse(10, phase, "Stalling")
            for text in (en, zh):
                assert "_" not in text, f"raw slug leaked for phase={phase!r}: {text!r}"

    def test_an_unknown_phase_drops_its_leg_rather_than_guessing(self):
        assert bp._plan_pulse(10, "some_future_phase", "Stalling")[0] == "10d · stalling"

    def test_an_untranslated_state_drops_from_BOTH_halves(self):
        """A one-sided drop would ship an EN-only chip to a ZH reader."""
        en, zh = bp._plan_pulse(10, "overtime", "Brand New State")
        assert en == "10d · overtime"
        assert zh == "10天 · 超时"

    def test_pulse_degrades_to_empty_rather_than_half_built(self):
        assert bp._plan_pulse(None, None, None) == ("", "")
        assert bp._plan_pulse(None, "nonsense", "Nonsense") == ("", "")

    @pytest.mark.parametrize("outcome,en,zh", [
        ("T1_HIT", "closed · hit first target", "已结 · 达到首个目标"),
        ("T2_HIT", "closed · hit second target", "已结 · 达到第二目标"),
        ("INVALIDATED", "closed · stopped out", "已结 · 止损离场"),
        ("EXPIRED", "closed · timed out", "已结 · 到期未达标"),
    ])
    def test_a_closed_plan_pulses_its_outcome(self, outcome, en, zh):
        assert bp._plan_pulse(138, "overtime", "Overtime Stall",
                              closed=True, outcome=outcome) == (en, zh)

    def test_a_closed_pulse_never_narrates_phase_or_human_state(self):
        """The defect this closes: the management engine keeps stating a closed plan,
        so its phase/human_state keep updating and the pulse read as a live thesis."""
        for phase in bp._PHASE_WORD:
            for state in bp._HUMAN_STATE_ZH:
                en, zh = bp._plan_pulse(138, phase, state,
                                        closed=True, outcome="INVALIDATED")
                assert en == "closed · stopped out"
                assert zh == "已结 · 止损离场"

    def test_a_closed_pulse_drops_the_age_leg(self):
        """age_days counts to TODAY, so on a dead plan it grows forever and would
        read as "still running for 138 days"."""
        assert "138d" not in bp._plan_pulse(
            138, "overtime", "Overtime Stall", closed=True, outcome="EXPIRED")[0]

    @pytest.mark.parametrize("outcome", [None, "", "SOME_NEW_OUTCOME", "t1_hit "])
    def test_an_unnamed_outcome_still_reads_as_closed(self, outcome):
        """Losing the outcome word must never resurrect the plan — `closed` is the
        load-bearing half.  A case/whitespace variant still resolves."""
        en, zh = bp._plan_pulse(50, "triggered_pre_t1", "Stalling",
                                closed=True, outcome=outcome)
        assert en.startswith("closed") and zh.startswith("已结")
        assert "stalling" not in en
        if outcome == "t1_hit ":
            assert en == "closed · hit first target"

    def test_an_open_plan_pulse_is_untouched_by_the_closed_path(self):
        assert bp._plan_pulse(32, "triggered_pre_t1", "Stalling", closed=False) == \
               bp._plan_pulse(32, "triggered_pre_t1", "Stalling")

    def test_no_outcome_slug_reaches_the_pulse(self):
        """`T1_HIT` is a ledger enum, not language (glance-tier word law)."""
        for outcome in [*bp._OUTCOME_WORD, "UNMAPPED_THING"]:
            for text in bp._plan_pulse(9, "at_t1", "T1 Hit — Holding",
                                       closed=True, outcome=outcome):
                assert "_" not in text and outcome.lower() not in text.lower()


class TestLedgerOutcomeReader:
    """`_load_closed_outcomes` — ONE ledger read serving the block and the index."""

    def test_ids_map_to_their_outcomes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bp, "LEDGER_DIR", tmp_path)
        monkeypatch.setattr(bp, "LEDGER_PATH", tmp_path / "ledger.jsonl")
        bp.LEDGER_PATH.write_text(
            "# header comment\n"
            '{"id": "A-BULL-20260701", "outcome": "T1_HIT"}\n'
            "\n"
            '{"id": "B-BULL-20260701", "outcome": "EXPIRED"}\n'
            "not json at all\n"
            '{"id": "C-BULL-20260701"}\n',
            encoding="utf-8")
        assert bp._load_closed_outcomes() == {
            "A-BULL-20260701": "T1_HIT",
            "B-BULL-20260701": "EXPIRED",
            "C-BULL-20260701": "",
        }
        # The id-set reader stays exactly what advance_ledger's guard expects.
        assert bp._load_closed_ids() == {
            "A-BULL-20260701", "B-BULL-20260701", "C-BULL-20260701"}

    def test_a_duplicate_row_keeps_the_FIRST_close(self, tmp_path, monkeypatch):
        """_determine_outcome is first-trigger-closes; a later row cannot rewrite it."""
        monkeypatch.setattr(bp, "LEDGER_DIR", tmp_path)
        monkeypatch.setattr(bp, "LEDGER_PATH", tmp_path / "ledger.jsonl")
        bp.LEDGER_PATH.write_text(
            '{"id": "A-BULL-20260701", "outcome": "T1_HIT"}\n'
            '{"id": "A-BULL-20260701", "outcome": "INVALIDATED"}\n',
            encoding="utf-8")
        assert bp._load_closed_outcomes() == {"A-BULL-20260701": "T1_HIT"}

    def test_an_absent_ledger_is_empty_not_fatal(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bp, "LEDGER_PATH", tmp_path / "nope.jsonl")
        assert bp._load_closed_outcomes() == {}
        assert bp._load_closed_ids() == set()

    def test_the_invalidated_echo_is_collapsed(self):
        assert bp._plan_pulse(45, "invalidated", "Invalidated")[0] == "45d · invalidated"

    def test_every_human_state_the_engine_emits_has_a_zh_pair(self):
        """Pins the map against its producer: a new human_state added to
        prophet_management without a translation would silently drop the leg.

        The literals are read out of the AST, not off the source lines — one of the
        returns is a ternary with two literals on one line, and a line-wise reader
        would silently "find" a single mangled state and pass.
        """
        import ast  # noqa: PLC0415
        import inspect  # noqa: PLC0415

        import engine.prophet_management as pm  # noqa: PLC0415

        tree = ast.parse(inspect.getsource(pm._human_state))
        emitted = {
            node.value
            for ret in ast.walk(tree) if isinstance(ret, ast.Return)
            for node in ast.walk(ret.value) if isinstance(ret.value, ast.AST)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        assert len(emitted) >= 12, (
            f"only {len(emitted)} human_state literals found — the extraction broke, "
            "so this test is no longer reading its producer")
        missing = emitted - set(bp._HUMAN_STATE_ZH)
        assert not missing, f"human_state values with no ZH pair: {sorted(missing)}"


# ---------------------------------------------------------------------------
# End-to-end index emission (tmp_path; the real site/ and data/ are never touched)
# ---------------------------------------------------------------------------

def _run_main(tmp_path: Path, buys: list[dict], *, asof: str,
              seed_plans: dict[str, dict] | None = None,
              ledger: dict[str, str] | None = None) -> dict:
    """Run build_prophet.main() against tmp_path and return the written index.json."""
    standouts_path = _write_standouts(tmp_path, buys, gate_go=False, as_of=asof)

    saved = {name: getattr(bp, name) for name in
             ("STANDOUTS_PATH", "SITE_PROPHET", "PLANS_DIR", "STATES_DIR",
              "INDEX_PATH", "LEDGER_PATH", "LEDGER_DIR", "write_showcase")}
    try:
        bp.STANDOUTS_PATH = standouts_path
        bp.SITE_PROPHET = tmp_path / "site" / "prophet"
        bp.PLANS_DIR = bp.SITE_PROPHET / "plans"
        bp.STATES_DIR = bp.SITE_PROPHET / "states"
        bp.INDEX_PATH = bp.SITE_PROPHET / "index.json"
        bp.LEDGER_DIR = tmp_path / "data" / "prophet"
        bp.LEDGER_PATH = bp.LEDGER_DIR / "ledger.jsonl"
        # write_showcase binds its out_path default at def time, so the module
        # constant cannot redirect it — it would write the REAL showcase.json.
        bp.write_showcase = lambda: None

        bp.PLANS_DIR.mkdir(parents=True, exist_ok=True)
        for plan_id, plan in (seed_plans or {}).items():
            (bp.PLANS_DIR / f"{plan_id}.json").write_text(json.dumps(plan), encoding="utf-8")
        if ledger:
            bp.LEDGER_DIR.mkdir(parents=True, exist_ok=True)
            bp.LEDGER_PATH.write_text(
                "\n".join(json.dumps({"schema": "prophet.ledger/v1", "id": plan_id,
                                      "outcome": outcome})
                          for plan_id, outcome in ledger.items()) + "\n",
                encoding="utf-8")

        prices = pd.DataFrame(
            {"close": [100.0 + i for i in range(40)],
             "high": [100.0 + i for i in range(40)],
             "low": [100.0 + i for i in range(40)]},
            index=pd.date_range("2026-06-01", periods=40, freq="B"),
        )
        with patch.object(sys, "argv", ["build_prophet", "--date", asof]), \
             patch("scripts.build_prophet._load_price_history_for_management",
                   return_value=prices):
            bp.main()
        return json.loads(bp.INDEX_PATH.read_text(encoding="utf-8"))
    finally:
        for name, value in saved.items():
            setattr(bp, name, value)


def _seed_plan(plan_id: str, ticker: str, signal_date: str) -> dict:
    return {
        "schema": "prophet.trade_plan/v1",
        "id": plan_id,
        "asof": signal_date,
        "asset": ticker,
        "direction": "BULL",
        "thesis": "seeded plan",
        "source_engines": ["us_standouts_buy_lane"],
        "trigger": 100.0,
        "entry": 100.0,
        "invalidation": 90.0,
        "targets": [115.0, 130.0],
        "horizon_days": 45,
        "min_hold_days": 10,
        "tranche": 1,
        "option_contract": None,
        "authority_tier": "display",
        "signal_date": signal_date,
        "_signal_date": signal_date,
        "_conviction_score": 50,
    }


class TestIndexHygieneEndToEnd:

    def test_every_shipped_plan_carries_an_age_and_a_pulse(self, tmp_path):
        index = _run_main(
            tmp_path,
            [_buy("AAPL", priority=88.0, anchor="2026-07-31", spot=120.0)],
            asof="2026-08-03",
            seed_plans={"OLDIE-BULL-20260318": _seed_plan(
                "OLDIE-BULL-20260318", "OLDIE", "2026-03-18")},
        )
        assert index["plans"], "no plans shipped — the assertions below would be vacuous"
        by_id = {p["id"]: p for p in index["plans"]}
        assert by_id["AAPL-BULL-20260731"]["age_days"] == 3
        assert by_id["OLDIE-BULL-20260318"]["age_days"] == 138
        for plan in index["plans"]:
            assert set(plan) >= {"age_days", "phase", "pulse", "pulse_zh"}
            assert plan["pulse"] and plan["pulse_zh"]
            assert str(plan["age_days"]) + "d" in plan["pulse"]

    def test_age_buckets_sum_to_active_count(self, tmp_path):
        index = _run_main(
            tmp_path,
            [_buy("AAPL", priority=88.0, anchor="2026-07-31", spot=120.0)],
            asof="2026-08-03",
            seed_plans={
                "FRESH-BULL-20260801": _seed_plan("FRESH-BULL-20260801", "FRESH", "2026-08-01"),
                "MID-BULL-20260720": _seed_plan("MID-BULL-20260720", "MID", "2026-07-20"),
                "OLDIE-BULL-20260318": _seed_plan("OLDIE-BULL-20260318", "OLDIE", "2026-03-18"),
            },
        )
        buckets = index["active_count_by_age"]
        assert set(buckets) == set(bp.AGE_BUCKET_KEYS)
        assert sum(buckets.values()) == index["active_count"] == len(index["plans"])
        assert buckets["le_7d"] >= 2 and buckets["d8_21d"] >= 1 and buckets["gt_21d"] >= 1

    def test_the_index_discloses_the_blocked_reoriginations(self, tmp_path):
        """The operator must be able to read, from the artifact alone, how many
        candidates the block held back tonight."""
        index = _run_main(
            tmp_path,
            [_buy("CLF", priority=90.0, anchor="2026-07-31", spot=120.0),
             _buy("NEWNAME", priority=80.0, anchor="2026-07-31", spot=120.0)],
            asof="2026-08-03",
            seed_plans={"CLF-BULL-20260601": _seed_plan(
                "CLF-BULL-20260601", "CLF", "2026-06-01")},
        )
        intake = index["intake"]
        assert intake["reorigination_blocked"] == 1
        assert intake["reorigination_blocked_keys"] == ["CLF-BULL"]
        assert intake["open_plan_keys"] == 1
        assert intake["mode"] == "lossless"
        assert intake["cap"] is None
        assert intake["cap_applied"] is False
        assert intake["truncated"] == 0
        assert intake["validation_failures"] == []
        assert intake["originated"] == 1
        assert intake["unaccounted"] == 0
        assert intake["lossless"] is True
        assert "CLF-BULL-20260731" not in {p["id"] for p in index["plans"]}
        assert "NEWNAME-BULL-20260731" in {p["id"] for p in index["plans"]}

        new = next(p for p in index["plans"] if p["id"] == "NEWNAME-BULL-20260731")
        assert new["formation_date"] == new["signal_date"] == "2026-07-31"
        assert new["price_basis_date"] == new["entry_date"] == "2026-08-03"
        assert new["recorded_at"] == new["plan_asof"] == "2026-08-03"

    def test_a_closed_plan_lets_the_name_back_in(self, tmp_path):
        index = _run_main(
            tmp_path,
            [_buy("CLF", priority=90.0, anchor="2026-07-31", spot=120.0)],
            asof="2026-08-03",
            seed_plans={"CLF-BULL-20260601": _seed_plan(
                "CLF-BULL-20260601", "CLF", "2026-06-01")},
            ledger={"CLF-BULL-20260601": "EXPIRED"},
        )
        assert index["intake"]["reorigination_blocked"] == 0
        assert "CLF-BULL-20260731" in {p["id"] for p in index["plans"]}

    def test_no_plan_is_dropped_or_re_ordered_by_the_new_fields(self, tmp_path):
        """Population fence G0.4 on the artifact side: the index still ships every
        plan it can state, still sorted by (conviction desc, id asc)."""
        seeds = {f"S{i}-BULL-20260701": _seed_plan(f"S{i}-BULL-20260701", f"S{i}", "2026-07-01")
                 for i in range(5)}
        index = _run_main(
            tmp_path,
            [_buy("AAPL", priority=88.0, anchor="2026-07-31", spot=120.0)],
            asof="2026-08-03", seed_plans=seeds,
        )
        assert index["active_count"] == len(seeds) + 1
        ids = [p["id"] for p in index["plans"]]
        assert sorted(ids) == sorted([*seeds, "AAPL-BULL-20260731"])
        assert ids == [p["id"] for p in sorted(
            index["plans"], key=lambda e: (-(e.get("_conviction_score") or 0), e["id"]))]

    def test_a_ledger_closed_plan_is_flagged_and_pulses_as_closed(self, tmp_path):
        """The amendment: a closed plan keeps getting stated by the management engine,
        so without the flag it is indistinguishable from a live one on the surface."""
        index = _run_main(
            tmp_path,
            [_buy("AAPL", priority=88.0, anchor="2026-07-31", spot=120.0)],
            asof="2026-08-03",
            seed_plans={
                "DEAD-BULL-20260601": _seed_plan("DEAD-BULL-20260601", "DEAD", "2026-06-01"),
                "WON-BULL-20260610": _seed_plan("WON-BULL-20260610", "WON", "2026-06-10"),
                "LIVE-BULL-20260720": _seed_plan("LIVE-BULL-20260720", "LIVE", "2026-07-20"),
            },
            ledger={"DEAD-BULL-20260601": "INVALIDATED", "WON-BULL-20260610": "T1_HIT"},
        )
        by_id = {p["id"]: p for p in index["plans"]}

        dead = by_id["DEAD-BULL-20260601"]
        assert dead["closed"] is True
        assert dead["pulse"] == "closed · stopped out"
        assert dead["pulse_zh"] == "已结 · 止损离场"
        assert by_id["WON-BULL-20260610"]["pulse"] == "closed · hit first target"

        live = by_id["LIVE-BULL-20260720"]
        assert live["closed"] is False
        assert live["pulse"] and "closed" not in live["pulse"]
        assert str(live["age_days"]) + "d" in live["pulse"]

        # age_days survives on the closed row — it is raw data; only the plain-word
        # line must not imply the thesis is still running.
        assert dead["age_days"] == 63

    def test_open_count_and_the_age_buckets_stay_coherent(self, tmp_path):
        """`active_count` semantics are FIXED (downstream consumers read that
        population); `open_count` is the live subset carved out of it."""
        index = _run_main(
            tmp_path,
            [_buy("AAPL", priority=88.0, anchor="2026-07-31", spot=120.0)],
            asof="2026-08-03",
            seed_plans={
                "DEAD-BULL-20260601": _seed_plan("DEAD-BULL-20260601", "DEAD", "2026-06-01"),
                "WON-BULL-20260610": _seed_plan("WON-BULL-20260610", "WON", "2026-06-10"),
                "LIVE-BULL-20260720": _seed_plan("LIVE-BULL-20260720", "LIVE", "2026-07-20"),
            },
            ledger={"DEAD-BULL-20260601": "INVALIDATED", "WON-BULL-20260610": "T1_HIT"},
        )
        closed = [p for p in index["plans"] if p["closed"]]
        assert index["active_count"] == len(index["plans"]) == 4
        assert len(closed) == 2
        assert index["open_count"] == index["active_count"] - len(closed) == 2
        # Buckets still census the WHOLE shipped population, closed rows included —
        # they are in plans[], so excluding them would under-report the surface.
        assert sum(index["active_count_by_age"].values()) == index["active_count"]

    def test_open_count_equals_active_count_when_the_ledger_is_empty(self, tmp_path):
        """Guards the inverse: an unread ledger must not silently mark rows closed."""
        index = _run_main(
            tmp_path, [_buy("AAPL", priority=88.0, anchor="2026-07-31", spot=120.0)],
            asof="2026-08-03",
            seed_plans={"LIVE-BULL-20260720": _seed_plan(
                "LIVE-BULL-20260720", "LIVE", "2026-07-20")})
        assert index["open_count"] == index["active_count"] == 2
        assert not any(p["closed"] for p in index["plans"])

    def test_the_index_note_and_intake_basis_avoid_the_forbidden_claim(self, tmp_path):
        index = _run_main(
            tmp_path, [_buy("AAPL", priority=88.0, anchor="2026-07-31", spot=120.0)],
            asof="2026-08-03")
        blob = json.dumps(index["intake"]) + json.dumps(index["active_count_by_age"])
        assert "validated" not in blob.lower() and "已验证" not in blob
