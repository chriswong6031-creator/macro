"""US board ledger — a graded row is a POINT-IN-TIME CLAIM and is never restated.

WHY THIS EXISTS
===============
The breadth close caches are re-based IN PLACE, so the same (ticker, date) reads
differently on different days: `PNC` at 2026-06-22 read 234.71 in the 2026-07-01 commit
and 232.85 on 2026-08-06. `_merge_into_store` was keep-FRESH on the dedup key and
justified it as "a deterministic re-computation from prices" — a premise the store's own
mutability makes false. Measured 2026-08-06: re-running the grader against the shipped
ledger moved 75 already-published rows, 19 of them materially, worst −1.94pp (LPG
2026-06-18 H5). A track record that silently rewrites its own history is worse than one
that discloses a basis change.

So price-derived columns are frozen at first grade, and the two price bases are separated
by a STAMP rather than by re-grading: `price_basis == PRE_ERA_BASIS` is era 1 (priced
from the raw cache at grade time, basis unverified), "adjusted"/"unadjusted" is era 2.

Every test here runs on synthetic frames and NEVER skips — this contract must hold on a
CI runner with no `data/`, which is exactly where a ledger guard is cheapest to break.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import grade_us_board as G  # noqa: E402

KEYS = G._DEDUP_KEYS


def _row(**kw):
    base = dict(as_of="2026-06-17", ticker="PNC", lane="buy", horizon=5,
                entry_date="2026-06-18", ret=0.055809, spy_ret=-0.02377,
                excess_spy=0.079579, etf_ret=0.01, excess_sector=0.045,
                sector_etf="XLF", mae_close_excess_spy=-0.01,
                mae_close_excess_sector=-0.01, fwd_mfe_5=0.06,
                terminal_state_clean15_126="x", terminal_state_clean8_21="y",
                post_cushion_breach=False, archetype="alpha", board_tenure_days=3)
    base.update(kw)
    return base


def _frame(*rows):
    return pd.DataFrame(list(rows))


# --------------------------------------------------------------------------- #
# 1. the freeze
# --------------------------------------------------------------------------- #
def test_a_graded_row_is_not_repriced_when_the_cache_moves():
    """THE regression. Same key, different price — the stored measurement must win."""
    stored = _frame(_row())                                   # graded 2026-07-01
    fresh = _frame(_row(ret=0.047458, excess_spy=0.071228,    # cache drifted since
                        price_source="baskets_ohlcv", price_basis="adjusted"))
    out = G._freeze_graded_prices(fresh, stored, KEYS)
    assert float(out.iloc[0]["ret"]) == pytest.approx(0.055809), (
        "the published return was restated — this is the defect, not the fix")
    assert float(out.iloc[0]["excess_spy"]) == pytest.approx(0.079579)


@pytest.mark.parametrize("col,new", [
    ("entry_date", "2026-06-19"), ("spy_ret", 0.5), ("etf_ret", 0.5),
    ("excess_sector", 0.5), ("mae_close_excess_spy", -0.9), ("fwd_mfe_5", 0.99),
    ("terminal_state_clean15_126", "MUTATED"), ("post_cushion_breach", True),
    ("sector_etf", "XLK"),
])
def test_every_price_derived_column_is_frozen(col, new):
    """One column left out of _FROZEN_PRICE_COLS is one number that keeps silently
    restating. Enumerated so adding a price-derived column without freezing it fails."""
    stored = _frame(_row())
    fresh = _frame(_row(**{col: new}))
    out = G._freeze_graded_prices(fresh, stored, KEYS)
    assert out.iloc[0][col] == stored.iloc[0][col], f"{col} was restated"


def test_an_unscored_row_that_matured_still_takes_the_fresh_grade():
    """The freeze must not stop the nightly doing its job: a row whose stored `ret` is
    null has no point-in-time claim to protect."""
    stored = _frame(_row(ret=None, excess_spy=None))
    fresh = _frame(_row(ret=0.0474, excess_spy=0.0712,
                        price_source="baskets_ohlcv", price_basis="adjusted"))
    out = G._freeze_graded_prices(fresh, stored, KEYS)
    assert float(out.iloc[0]["ret"]) == pytest.approx(0.0474)
    assert out.iloc[0]["price_basis"] == "adjusted", "a first grade is era 2"


def test_a_brand_new_row_is_untouched():
    stored = _frame(_row(ticker="OTHER"))
    fresh = _frame(_row(ret=0.0474, price_source="baskets_ohlcv",
                        price_basis="adjusted"))
    out = G._freeze_graded_prices(fresh, stored, KEYS)
    assert float(out.iloc[0]["ret"]) == pytest.approx(0.0474)
    assert out.iloc[0]["price_basis"] == "adjusted"


def test_annotations_still_accrue_onto_a_frozen_row():
    """Freezing the MEASUREMENT must not freeze the row. Schema-union and the regime /
    archetype backfills depend on non-price columns still reaching historical rows."""
    stored = _frame(_row(archetype=None, board_tenure_days=None))
    fresh = _frame(_row(ret=0.047458, archetype="coiled", board_tenure_days=9))
    out = G._freeze_graded_prices(fresh, stored, KEYS)
    assert float(out.iloc[0]["ret"]) == pytest.approx(0.055809), "price frozen"
    assert out.iloc[0]["archetype"] == "coiled", "annotation must still land"
    assert out.iloc[0]["board_tenure_days"] == 9


# --------------------------------------------------------------------------- #
# 2. the era marker
# --------------------------------------------------------------------------- #
def test_a_pre_era_row_is_stamped_unverified_not_given_this_ladders_stamp():
    """A row frozen at a value THIS ladder did not compute must not claim this ladder's
    basis. The store, not the fresh row, decides which era a row belongs to."""
    stored = _frame(_row())                       # no price_basis column at all
    fresh = _frame(_row(price_source="baskets_ohlcv", price_basis="adjusted"))
    out = G._freeze_graded_prices(fresh, stored, KEYS)
    assert out.iloc[0]["price_basis"] == G.PRE_ERA_BASIS
    # null, not "the rung this run happened to pick" — pandas may render it NaN or None
    # depending on the column's dtype, and the contract is nullness either way.
    assert pd.isna(out.iloc[0]["price_source"])


def test_an_era_two_row_keeps_its_own_stamp_on_a_later_run():
    """Once a row is graded under the new ladder its stamp is part of the frozen claim —
    it must not decay to 'unverified' on the next nightly."""
    stored = _frame(_row(price_source="baskets_ohlcv", price_basis="adjusted"))
    fresh = _frame(_row(ret=0.9, price_source="yahoo", price_basis="unadjusted"))
    out = G._freeze_graded_prices(fresh, stored, KEYS)
    assert out.iloc[0]["price_basis"] == "adjusted"
    assert out.iloc[0]["price_source"] == "baskets_ohlcv"
    assert float(out.iloc[0]["ret"]) == pytest.approx(0.055809)


def test_the_two_eras_are_separable_by_one_column():
    """The whole point of the marker: old and new rows must be told apart without
    archaeology."""
    stored = _frame(_row(), _row(ticker="CL"))
    fresh = _frame(_row(price_basis="adjusted", price_source="baskets_ohlcv"),
                   _row(ticker="CL", price_basis="adjusted", price_source="baskets_ohlcv"),
                   _row(ticker="NEW", price_basis="adjusted", price_source="baskets_ohlcv"))
    out = G._freeze_graded_prices(fresh, stored, KEYS)
    era1 = out[out["price_basis"] == G.PRE_ERA_BASIS]
    era2 = out[out["price_basis"] == "adjusted"]
    assert len(era1) == 2 and len(era2) == 1
    assert set(era1["ticker"]) == {"PNC", "CL"} and set(era2["ticker"]) == {"NEW"}


def test_the_boundary_date_is_stated():
    assert G.PRICE_BASIS_ERA_BOUNDARY == "2026-08-06"
    assert "20260806" in G.PRE_ERA_BASIS


# --------------------------------------------------------------------------- #
# 3. degrade-safety — the freeze must never take down a nightly
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("stored,fresh", [
    (pd.DataFrame(), None),                       # first ever run
    (None, None),                                 # no store
])
def test_empty_inputs_are_a_no_op(stored, fresh):
    f = _frame(_row())
    out = G._freeze_graded_prices(f, stored if stored is not None else pd.DataFrame(), KEYS)
    assert len(out) == 1 and float(out.iloc[0]["ret"]) == pytest.approx(0.055809)


def test_a_store_with_no_ret_column_is_a_no_op():
    stored = pd.DataFrame([{k: _row()[k] for k in KEYS}])
    out = G._freeze_graded_prices(_frame(_row(ret=0.9)), stored, KEYS)
    assert float(out.iloc[0]["ret"]) == pytest.approx(0.9)


def test_duplicate_stored_keys_do_not_explode_the_frame():
    """A store that already carries a duplicated key must not fan the merge out."""
    stored = _frame(_row(), _row(ret=0.01))       # same key twice
    out = G._freeze_graded_prices(_frame(_row(ret=0.9)), stored, KEYS)
    assert len(out) == 1, "the freeze must not multiply rows"


def test_the_frozen_count_is_reported():
    stored = _frame(_row())
    out = G._freeze_graded_prices(_frame(_row(ret=0.9)), stored, KEYS)
    assert out.attrs.get("frozen_rows") == 1


# --------------------------------------------------------------------------- #
# 4. the stamp is actually emitted by the grader
# --------------------------------------------------------------------------- #
def test_frozen_price_cols_covers_what_grade_boards_computes_from_prices():
    """Guards the enumeration itself: every column the row builder derives from the close
    panel has to be in the frozen set, or it silently restates."""
    for col in ("ret", "spy_ret", "excess_spy", "etf_ret", "excess_sector",
                "mae_close_excess_spy", "mae_close_excess_sector", "entry_date",
                "terminal_state_clean15_126", "terminal_state_clean8_21",
                "post_cushion_breach", "price_source", "price_basis"):
        assert col in G._FROZEN_PRICE_COLS, col
    for h in (5, 10, 21, 63):
        assert f"fwd_mfe_{h}" in G._FROZEN_PRICE_COLS


def test_regime_and_context_columns_are_deliberately_not_frozen():
    """The complement: these are annotations and MUST keep accruing onto historical rows,
    or the regime/archetype backfills silently stop working."""
    for col in ("rate_pressure", "quad_hard_label", "archetype", "board_tenure_days",
                "vector_asof", "risk_radar_state"):
        assert col not in G._FROZEN_PRICE_COLS, col
