"""Tripwire for DNR:HOLD-FACTOR-UNIVERSE-WIDENING.

`engine.equity_factors` scores every leg as a WINSORIZED CROSS-SECTIONAL z, so the
population is the yardstick, and `composite_rank` is the board TIEBREAK
(scripts/build_stock_library.py, scripts/build_site.py) — rank authority, not display
tier. Pooling the Russell 2000 into `_UNIVERSE_GROUPS["broad"]` re-orders the names
already on the page: composite Spearman 0.703 WITHIN the same 1,354 incumbents, 74.7%
change decile, the composite top-10 keeps 2 of 10.

So the widening is held pending the pre-registration in
`research/FACTOR_UNIVERSE_WIDENING_CHARTER.md` §11. These tests make that hold
executable instead of advisory — a registry row nothing enforces is a comment.

They are deliberately NOT mirrors of the constant: test 1 reads the shipped tuple
directly, and test 2 is CONDITIONAL — it does not forbid the widening forever, it
forbids the *non-deterministic* widening (see charter §7: the Russell closes cache is
the only one of the four US closes caches gitignored, absent in every ci.yml pack and
on cold clones, and the same hazard already left a permanent hole in the name-score
PIT ledger — scripts/build_stock_library.py:686).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

CHARTER = "research/FACTOR_UNIVERSE_WIDENING_CHARTER.md"
ROW_KEY = "HOLD-FACTOR-UNIVERSE-WIDENING"
IGNORE_LINE = "data/russell_breadth/_closes_cache.parquet"


def _universe_groups() -> dict:
    from engine.equity_factors import _UNIVERSE_GROUPS
    return _UNIVERSE_GROUPS


def test_pooled_widening_is_held():
    """The shipped factor universe must not pool the Russell 2000 into `broad`."""
    groups = _universe_groups()
    assert "russell_breadth" not in groups["broad"], (
        "engine/equity_factors.py::_UNIVERSE_GROUPS['broad'] now pools the Russell 2000.\n"
        f"That is HELD by DNR:{ROW_KEY} — it is a PROMOTION-tier change, not a config bump:\n"
        "  * composite_rank is the board TIEBREAK (rank authority), and\n"
        "  * measured cost: composite Spearman 0.703 within the SAME incumbent names,\n"
        "    74.7% change decile, composite top-10 survives 2/10, value top-20 survives 1/20.\n"
        f"Ship the frozen-reference form (Option D) or bring the pre-registration in {CHARTER} §11.\n"
        "Reproduce: python3 scripts/factor_universe_widening_phase0.py --stage churn"
    )


def test_a_widening_must_bring_a_tracked_closes_cache():
    """CONDITIONAL, fail-closed: whoever widens must first make the price panel
    deterministic. This test goes green the moment the cache is tracked — it gates the
    unsafe widening, never the safe one."""
    groups = _universe_groups()
    widened = any("russell_breadth" in grp for grp in groups.values())
    if not widened:
        return
    ignored = [ln.strip() for ln in (REPO / ".gitignore").read_text().splitlines()
               if ln.strip() == IGNORE_LINE]
    assert not ignored, (
        f"_UNIVERSE_GROUPS reads russell_breadth while {IGNORE_LINE} is still gitignored.\n"
        "That cache is restored only by daily.yml / closing-bell.yml via actions/cache and by\n"
        "NO ci.yml pack, so the factor cross-section — and therefore the board tiebreak —\n"
        "would differ per host and per cache eviction. Its three S&P siblings and its own\n"
        f"high/low/volume siblings are all tracked. See {CHARTER} §7."
    )


def test_the_hold_is_still_on_the_registry():
    """The tripwire cites a registry row; deleting the row must be a deliberate registry
    edit (which the blocklist-regen guard then picks up), not a silent drift."""
    registry = (REPO / "research" / "DO_NOT_REBUILD.md").read_text()
    assert ROW_KEY in registry, (
        f"DNR:{ROW_KEY} has left research/DO_NOT_REBUILD.md while this tripwire still "
        "enforces it. Retire the row and this suite together, with the ruling that lifts "
        f"the hold recorded in {CHARTER}."
    )
    assert (REPO / CHARTER).exists(), f"{CHARTER} is missing — the hold cites it as its ruling."
