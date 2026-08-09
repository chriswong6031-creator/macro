"""tests/test_prophet_live_basis.py — ONE PRICE BASIS (Breathing Platform W-L0 gate 3).

The Prophet Live path joins three price planes and, until this gate, none of them said
which one it was on:

    armed edges      probed on the nightly store's SPLIT+DIVIDEND ADJUSTED closes
    the live tape    RAW vendor prints (Polygon snapshot / Yahoo spark)
    the ledger       divided the second by the first and called it a percentage

This file pins the vocabulary that names them, the per-pass assertion that the first two
still describe the same scale, and the arithmetic that stops the third from mixing them.
The reconciler's own dividend-day proof lives with the ledger law in
``tests/test_prophet_live_reconcile.py``; the evaluator's darking behaviour lives with
the degradation gates in ``tests/test_prophet_live_evaluator.py``. What is here is the
CROSS-MODULE contract — the part that breaks silently when one module is edited alone.

Nothing in this file reads a wall clock or a store.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.prophet_live import armed_pack as AP  # noqa: E402
from engine.prophet_live import interval as IV  # noqa: E402


def _entry(as_of_close: float, *, probed: bool = True) -> dict:
    return {"state": "near", "center_buyable": False, "as_of_close": as_of_close,
            "probed": probed, "buyable_in_band": True, "trigger_px": as_of_close * 1.02,
            "band_lo_px": 0.0, "band_hi_px": as_of_close * 1.15}


def _quote(price: float, prev: float | None) -> dict:
    return {"price": price, "prev_close": prev, "ts_ms": None, "source": "quotes"}


# ─────────────────────────────────────────────────────────────────────────────
# The vocabulary is ONE vocabulary
# ─────────────────────────────────────────────────────────────────────────────

def test_the_basis_names_are_distinct_and_non_empty():
    assert IV.ADJUSTED and IV.UNADJUSTED and IV.ADJUSTED != IV.UNADJUSTED


def test_the_live_quote_seam_is_named_raw_and_is_never_converted():
    """A live quote is a nominal print. Naming it adjusted, or converting it to the
    adjusted basis, would put a price on the tape that no exchange ever made."""
    assert IV.LIVE_QUOTE_ADJUSTMENT == IV.UNADJUSTED
    assert IV.DEFAULT_PACK_ADJUSTMENT == IV.ADJUSTED


def test_the_vocabulary_agrees_with_the_production_price_ladder():
    """``engine.price_ladder`` is the estate's arbiter of which stores are adjusted.
    ``interval`` cannot import it (pandas; the */5 lane installs none), so the two are
    pinned here instead — a third private definition of "adjusted" is exactly how two
    surfaces end up disagreeing about the same series.
    """
    pl = pytest.importorskip("engine.price_ladder")
    assert pl.is_adjusted("data_stocks") is True
    assert pl.is_adjusted("closes_cache_UNADJUSTED") is False
    # The four breadth caches are the population `universe_price_adjustment` labels
    # UNADJUSTED, and the ladder must still classify that family the same way.
    assert set(pl.CACHE_GROUPS) == {"breadth", "smallcap_breadth", "midcap_breadth",
                                    "russell_breadth"}


def test_the_library_labels_cache_names_unadjusted_and_per_name_stores_adjusted():
    """The universe is MIXED, and the map has to say so per ticker."""
    import scripts.build_stock_library as BSL

    BSL._UNIVERSE_TICKER_GROUP.clear()
    BSL._UNIVERSE_TICKER_GROUP.update({"AAA": "stocks_deep", "BBB": "russell_breadth",
                                       "CCC": "curated_extras", "DDD": "breadth"})
    got = BSL.universe_price_adjustment()
    assert got == {"AAA": IV.ADJUSTED, "BBB": IV.UNADJUSTED,
                   "CCC": IV.ADJUSTED, "DDD": IV.UNADJUSTED}
    BSL._UNIVERSE_TICKER_GROUP.clear()


def test_the_basis_field_is_not_the_liveness_rung_of_the_same_name():
    """``engine.live_quotes`` already owns ``price_basis`` for WHICH RUNG a quote came
    off (trade/minute/day/prev/regular) and ships it as the JSON key ``basis``. Reusing
    either name for the adjustment axis would put two unrelated meanings on one word in
    one payload, so neither of this module's values may collide with that vocabulary.
    """
    lq = pytest.importorskip("engine.live_quotes")
    rungs = set(getattr(lq, "PRICE_BASES", ()) or ("trade", "minute", "day", "prev",
                                                   "regular"))
    assert IV.ADJUSTED not in rungs and IV.UNADJUSTED not in rungs


# ─────────────────────────────────────────────────────────────────────────────
# The gap measurement
# ─────────────────────────────────────────────────────────────────────────────

def test_the_gap_is_zero_when_both_planes_agree():
    assert IV.basis_gap_pct(100.0, 100.0) == pytest.approx(0.0)


def test_a_dividend_sized_gap_is_measured_with_its_sign():
    # The store re-based a $100 close down by a $1 dividend; the feed still carries the
    # raw print. -1% is the dividend, and the sign says which plane moved.
    assert IV.basis_gap_pct(99.0, 100.0) == pytest.approx(-1.0)


@pytest.mark.parametrize("a,b", [(None, 100.0), (100.0, None), (100.0, 0.0),
                                 (0.0, 100.0), (-5.0, 100.0), ("x", 100.0),
                                 (float("nan"), 100.0), (float("inf"), 100.0)])
def test_an_unusable_leg_is_no_measurement_not_a_zero_gap(a, b):
    """None, never 0.0: "we could not compare" and "they agree" are different claims and
    only the second one is a pass."""
    assert IV.basis_gap_pct(a, b) is None


# ─────────────────────────────────────────────────────────────────────────────
# The per-pass audit
# ─────────────────────────────────────────────────────────────────────────────

def test_the_audit_counts_matched_and_mismatched_names_separately():
    names = {"AAA": _entry(100.0), "BBB": _entry(99.0)}
    q = {"AAA": _quote(101.0, 100.0), "BBB": _quote(99.5, 100.0)}
    got = IV.basis_audit(names, q, tol_pct=0.25)
    assert got["checked_n"] == 2
    assert got["unchecked_n"] == 0
    assert set(got["mismatched"]) == {"BBB"}
    assert got["mismatched"]["BBB"] == pytest.approx(-1.0)


def test_a_quote_without_a_previous_close_is_unchecked_never_passed():
    """The heatmap-derived rows carry ``prev_close: None`` by construction, so a feed
    that quietly stops publishing previous closes would otherwise produce a clean audit
    over zero evidence."""
    got = IV.basis_audit({"AAA": _entry(100.0)}, {"AAA": _quote(101.0, None)},
                         tol_pct=0.25)
    assert got == {"tol_pct": 0.25, "checked_n": 0, "unchecked_n": 1,
                   "gaps": {}, "mismatched": {}}


def test_a_name_with_no_quote_at_all_is_unchecked():
    got = IV.basis_audit({"AAA": _entry(100.0)}, {}, tol_pct=0.25)
    assert got["checked_n"] == 0 and got["unchecked_n"] == 1


def test_unprobed_names_are_not_audited():
    """They publish no ``as_of_close`` the evaluator acts on and are already outside
    ``states`` — counting them unchecked would inflate the one number that is supposed
    to mean "armed, and we could not verify it"."""
    got = IV.basis_audit({"AAA": _entry(100.0, probed=False)},
                         {"AAA": _quote(101.0, 100.0)}, tol_pct=0.25)
    assert got["checked_n"] == 0 and got["unchecked_n"] == 0


def test_every_measured_gap_is_handed_on_not_just_the_mismatches():
    """The tolerance is applied by the state machine, which can only apply it to gaps it
    is given. An audit that filtered would make ``_resolve_state``'s own threshold
    unreachable and a mutation to it would pass every test."""
    names = {"AAA": _entry(100.0), "BBB": _entry(99.0)}
    q = {"AAA": _quote(101.0, 100.0), "BBB": _quote(99.5, 100.0)}
    got = IV.basis_audit(names, q, tol_pct=0.25)
    assert set(got["gaps"]) == {"AAA", "BBB"}


# ─────────────────────────────────────────────────────────────────────────────
# The armed pack states its basis
# ─────────────────────────────────────────────────────────────────────────────

def _assemble(names: dict, adj: dict | None):
    return AP.assemble(names, as_of="2026-08-03", cfg=AP.pack_cfg(None), universe_n=2,
                       wanted_n=2, gate_calls=0, build_seconds=1.0, skipped={},
                       price_adjustment=adj)


def test_the_pack_states_the_basis_its_edges_are_prices_on():
    pack = _assemble({"AAA": {"state": "near", "probed": True}}, {"AAA": IV.ADJUSTED})
    assert pack["price_adjustment"] == IV.ADJUSTED


def test_only_the_off_default_names_carry_their_own_basis():
    names = {"AAA": {"state": "near", "probed": True},
             "BBB": {"state": "near", "probed": True}}
    pack = _assemble(names, {"AAA": IV.ADJUSTED, "BBB": IV.UNADJUSTED})
    assert "price_adjustment" not in pack["names"]["AAA"]
    assert pack["names"]["BBB"]["price_adjustment"] == IV.UNADJUSTED
    assert pack["meta"]["price_adjustment_counts"] == {IV.ADJUSTED: 1, IV.UNADJUSTED: 1}


def test_a_pack_with_no_provenance_map_counts_unknown_and_claims_nothing_per_name():
    """A missing map must not read as per-name agreement with the default: "we do not
    know this name's basis" and "this name is adjusted" are different claims."""
    pack = _assemble({"AAA": {"state": "near", "probed": True}}, None)
    assert pack["meta"]["price_adjustment_counts"] == {"unknown": 1}
    assert "price_adjustment" not in pack["names"]["AAA"]
