"""Empirical null base rate for the desks' `hit` endpoint (engine/desk_placebo.py).

`hit` means "the falsifier did not trigger", so its null is nowhere near one-half. These
tests pin the placebo sweeps against series whose answer is known by construction, plus the
statistics (exact Poisson-binomial, non-overlapping window count, Holm) the promotion gate
leans on.
"""
from __future__ import annotations

import json
import sys
import tempfile
from math import comb
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import desk_placebo as dp  # noqa: E402


def _new_root():
    return Path(tempfile.mkdtemp())


def _write_prices(root, ticker, values, start="2020-01-01"):
    d = root / "data" / "yahoo"
    d.mkdir(parents=True, exist_ok=True)
    idx = pd.bdate_range(start, periods=len(values))
    pd.DataFrame({"close": values}, index=idx).to_parquet(d / f"{ticker}.parquet")


# --------------------------------------------------------------------------- #
# the sweeps
# --------------------------------------------------------------------------- #
def test_rel_return_null_is_one_when_the_falsifier_can_never_trigger():
    """A subject that always beats its benchmark is never falsified by "underperforms by 5%".
    The null hit-rate is 1.0 — the endpoint carries no information at all here, which is
    exactly the leniency a 0.5 bar would have scored as a perfect edge."""
    root = _new_root()
    _write_prices(root, "UP", [100 * (1.001 ** i) for i in range(400)])
    _write_prices(root, "FLAT", [100.0] * 400)
    get = dp._series_cache(root)
    res = dp.placebo_rel_return(
        get, {"subject_ticker": "UP", "vs": "FLAT", "op": "<", "threshold": -0.05},
        "2020-06-01", "2020-06-29")
    assert res["p_hit"] == 1.0
    assert res["p_dir"] == 1.0
    assert res["window_bd"] == 20


def test_rel_return_null_tracks_the_threshold():
    """Same instrument, looser falsifier → higher null. The bar has to move with it."""
    root = _new_root()
    _write_prices(root, "DOWN", [100 * (0.999 ** i) for i in range(400)])
    _write_prices(root, "FLAT", [100.0] * 400)
    get = dp._series_cache(root)
    tight = dp.placebo_rel_return(
        get, {"subject_ticker": "DOWN", "vs": "FLAT", "op": "<", "threshold": -0.01},
        "2020-06-01", "2020-06-29")
    loose = dp.placebo_rel_return(
        get, {"subject_ticker": "DOWN", "vs": "FLAT", "op": "<", "threshold": -0.50},
        "2020-06-01", "2020-06-29")
    assert tight["p_hit"] == 0.0        # a 2% drift always breaches a 1% floor
    assert loose["p_hit"] == 1.0        # nothing ever breaches a 50% floor
    assert tight["p_dir"] == 0.0


def test_level_null_is_harsh_not_lenient():
    """The fade-fear endpoint runs the other way: "never made a new high above entry" is
    hard, so its null sits BELOW one-half. A single 0.5 bar is wrong in both directions."""
    root = _new_root()
    _write_prices(root, "VIX", [20 + i * 0.01 for i in range(400)])   # monotone up
    get = dp._series_cache(root)
    res = dp.placebo_level(get, {"subject_ticker": "VIX"}, "2020-06-01", "2020-06-15")
    assert res["p_hit"] == 0.0          # always makes a new high → always falsified
    assert res["p_dir"] == 0.0


def test_level_null_matches_max_close_between_window():
    """The sweep must use the same exclusive-start window as desk_scorer.max_close_between,
    or the null describes a different endpoint than the one that was graded."""
    root = _new_root()
    # flat, with one spike 3 bars after each entry — inside a 5-bar window, outside a 2-bar one
    vals = [10.0] * 400
    for i in range(3, 400, 40):
        vals[i] = 12.0
    _write_prices(root, "SPIKE", vals)
    get = dp._series_cache(root)
    wide = dp.placebo_level(get, {"subject_ticker": "SPIKE"}, "2020-06-01", "2020-06-08")
    assert 0.0 < wide["p_hit"] < 1.0


def test_sweeps_need_enough_history():
    root = _new_root()
    _write_prices(root, "SHORT", [100.0] * 20)
    get = dp._series_cache(root)
    assert dp.placebo_level(get, {"subject_ticker": "SHORT"}, "2020-01-06", "2020-01-10") is None
    assert dp.placebo_rel_return(
        get, {"subject_ticker": "SHORT", "vs": None, "op": "<", "threshold": -0.05},
        "2020-01-06", "2020-01-10") is None


def test_missing_ticker_yields_no_null_rather_than_a_guess():
    get = dp._series_cache(_new_root())
    assert dp.placebo_level(get, {"subject_ticker": "NOPE"}, "2020-06-01", "2020-06-08") is None


# --------------------------------------------------------------------------- #
# statistics
# --------------------------------------------------------------------------- #
def test_poisson_binomial_matches_binomial_when_probabilities_are_equal():
    ps = [0.8] * 10
    for k in range(11):
        expect = sum(comb(10, j) * 0.8 ** j * 0.2 ** (10 - j) for j in range(k, 11))
        assert abs(dp.poisson_binomial_sf(ps, k) - expect) < 1e-12


def test_poisson_binomial_handles_unequal_probabilities():
    # P(X >= 2) for p = [0.5, 0.5] is 0.25; for [1.0, 0.5] it is 0.5
    assert abs(dp.poisson_binomial_sf([0.5, 0.5], 2) - 0.25) < 1e-12
    assert abs(dp.poisson_binomial_sf([1.0, 0.5], 2) - 0.5) < 1e-12
    assert dp.poisson_binomial_sf([0.3, 0.7], 0) == 1.0
    assert dp.poisson_binomial_sf([], 1) == 1.0


def test_a_lenient_null_makes_a_high_hit_rate_unremarkable():
    """11 of 13 looks impressive against 0.5 and is nothing against the real null."""
    lenient = dp.poisson_binomial_sf([0.83] * 13, 11)
    coin = dp.poisson_binomial_sf([0.5] * 13, 11)
    assert lenient > 0.4          # unremarkable
    assert coin < 0.02            # what the old bar "saw"


def test_independent_blocks_counts_non_overlapping_windows():
    # three theses logged days apart, each graded over the following month → one look
    overlapping = [("2026-06-15", "2026-07-13"), ("2026-06-17", "2026-07-15"),
                   ("2026-06-18", "2026-07-16")]
    assert dp.independent_blocks(overlapping) == 1
    # the same three, spaced so no window touches another → three looks
    spaced = [("2026-01-01", "2026-01-31"), ("2026-02-01", "2026-02-28"),
              ("2026-03-01", "2026-03-31")]
    assert dp.independent_blocks(spaced) == 3
    assert dp.independent_blocks([]) == 0
    assert dp.independent_blocks([(None, "2026-01-01"), ("2026-02-01", None)]) == 0


def test_holm_adjustment_is_monotone_and_steps_down():
    adj = dp.holm_adjust({"a": 0.01, "b": 0.02, "c": 0.04})
    assert adj["a"] == 0.03                      # 3 x 0.01
    assert adj["b"] == 0.04                      # 2 x 0.02
    assert adj["c"] == 0.04                      # monotone: cannot drop below its predecessor
    assert dp.holm_adjust({"a": 0.01, "b": None})["b"] is None
    assert dp.holm_adjust({"a": 0.01, "b": None})["a"] == 0.01   # only one test in the family
    assert dp.holm_adjust({"a": 0.9, "b": 0.9})["a"] == 1.0      # capped


# --------------------------------------------------------------------------- #
# end to end
# --------------------------------------------------------------------------- #
def _write_desk(root, slug, theses, scored=None):
    d = root / "data" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "theses.jsonl").write_text("".join(json.dumps(t) + "\n" for t in theses))
    if scored is not None:
        (d / "scored.jsonl").write_text("".join(json.dumps(s) + "\n" for s in scored))


def _thesis(tid, asof, check_by, ticker="UP", vs="FLAT"):
    return {"id": tid, "state_asof": asof, "check_by": check_by,
            "falsifier": {"check": {"kind": "rel_return", "subject_ticker": ticker,
                                    "vs": vs, "op": "<", "threshold": -0.05}}}


def test_null_baseline_pairs_outcomes_to_their_own_nulls():
    root = _new_root()
    _write_prices(root, "UP", [100 * (1.001 ** i) for i in range(500)])
    _write_prices(root, "FLAT", [100.0] * 500)
    theses = [_thesis(f"t{i}", "2021-01-04", "2021-02-01") for i in range(3)]
    scored = [{"id": f"t{i}", "outcome": "hit", "directionally_correct": True} for i in range(3)]
    _write_desk(root, "ai_desk", theses, scored)
    track = {"overall": {"n": 3, "hits": 3, "hit_rate": 1.0, "dir_accuracy": 1.0}}
    res = dp.null_baseline(root, "ai_desk", track, "2021-03-01")
    assert res["available"] is True and res["mix_source"] == "scored"
    assert res["n"] == 3 and res["null_hit_rate"] == 1.0
    assert res["p_hit"] == 1.0          # 3/3 against a null of 1.0 is no evidence whatsoever
    assert res["independent_blocks"] == 1
    assert res["coverage"] == 1.0


def test_null_baseline_falls_back_to_the_elapsed_ledger():
    """scored.jsonl is untracked for some desks; the graded population is still recoverable
    from the ledger's elapsed, machine-checkable theses."""
    root = _new_root()
    _write_prices(root, "UP", [100 * (1.001 ** i) for i in range(500)])
    _write_prices(root, "FLAT", [100.0] * 500)
    _write_desk(root, "stock_desk", [
        _thesis("a", "2021-01-04", "2021-02-01"),
        _thesis("b", "2021-03-01", "2021-03-29"),
        _thesis("c", "2021-06-01", "2021-12-01"),        # not yet elapsed
    ])
    track = {"overall": {"n": 2, "hits": 2, "hit_rate": 1.0, "dir_accuracy": 1.0}}
    res = dp.null_baseline(root, "stock_desk", track, "2021-04-01")
    assert res["mix_source"] == "ledger_elapsed"
    assert res["n"] == 2 and res["available"] is True
    assert res["independent_blocks"] == 2


def test_mismatched_population_refuses_to_pair_but_still_reports_the_null():
    """Fail closed: never test one population's hits against another population's null. The
    measured null is still surfaced — display accrues, promotion does not."""
    root = _new_root()
    _write_prices(root, "UP", [100 * (1.001 ** i) for i in range(500)])
    _write_prices(root, "FLAT", [100.0] * 500)
    _write_desk(root, "stock_desk", [_thesis("a", "2021-01-04", "2021-02-01")])
    track = {"overall": {"n": 45, "hits": 29, "hit_rate": 0.644, "dir_accuracy": 0.333}}
    res = dp.null_baseline(root, "stock_desk", track, "2021-04-01")
    assert res["available"] is False
    assert "cannot pair" in res["reason"]
    assert res["null_hit_rate"] == 1.0          # measured, and still printed
    assert res["coverage"] is not None and res["coverage"] < 1.0


def _theme_thesis(tid, asof, check_by):
    """thematic_desk's shape: a `theme_rel_return` predicate, which this module has no
    placebo sweep for (its scorer prices region-aware stores and reads the exit close at or
    AFTER check_by, so the rel_return sweep would not be measuring the graded endpoint)."""
    return {"id": tid, "state_asof": asof, "check_by": check_by,
            "falsifier": {"check": {"kind": "theme_rel_return", "theme_id": "ai_compute",
                                    "subject_ticker": "UP", "vs": "FLAT", "group": "yahoo",
                                    "op": "<", "threshold": -0.05}}}


def test_unsweepable_predicate_kind_is_named_not_reported_as_a_missing_ledger():
    """thematic_desk has a 141-row ledger, writes no scored.jsonl, and grades a kind with no
    placebo sweep. The old disclosure for every empty case was 'no thesis ledger to
    reconstruct the graded predicates from' — false here, and a null we cannot measure has to
    say what actually stopped us."""
    root = _new_root()
    _write_desk(root, "thematic_desk", [
        _theme_thesis("a", "2021-01-04", "2021-02-01"),
        _theme_thesis("b", "2021-01-05", "2021-02-02"),
        {"id": "c", "state_asof": "2021-01-06", "check_by": "2021-02-03",
         "falsifier": {"check": {"kind": "soft", "reason": "no scalar etf_proxy"}}},
    ])
    track = {"overall": {"n": 21, "hits": 12, "hit_rate": 0.571, "dir_accuracy": 0.429}}
    res = dp.null_baseline(root, "thematic_desk", track, "2021-04-01")
    assert res["available"] is False                       # fails closed
    assert res["null_hit_rate"] is None                    # nothing measured to print
    assert "no placebo sweep exists" in res["reason"]
    # itemised by kind, so the reader can see what would need a sweep (and what never will)
    assert "2 theme_rel_return" in res["reason"] and "1 soft" in res["reason"]
    assert "rel_return / level can be swept" in res["reason"]
    assert "no thesis ledger" not in res["reason"]


def test_ledger_elapsed_population_larger_than_the_track_record_fails_closed():
    """thematic_desk's live divergence: 30 elapsed theses against 21 decided outcomes, because
    its scorer expires the ones it cannot price. Even with a sweep for its kind, the extra
    rows must never be paired to the track record's hits."""
    root = _new_root()
    _write_prices(root, "UP", [100 * (1.001 ** i) for i in range(500)])
    _write_prices(root, "FLAT", [100.0] * 500)
    _write_desk(root, "stock_desk", [_thesis("a", "2021-01-04", "2021-02-01"),
                                     _thesis("b", "2021-02-08", "2021-03-08"),
                                     _thesis("c", "2021-03-09", "2021-03-29")])
    track = {"overall": {"n": 2, "hits": 2, "hit_rate": 1.0, "dir_accuracy": 1.0}}
    res = dp.null_baseline(root, "stock_desk", track, "2021-04-01")
    assert res["mix_source"] == "ledger_elapsed" and res["n"] == 3
    assert res["available"] is False and "cannot pair" in res["reason"]
    assert res["p_hit"] is None                            # no test on a mismatched pairing
    assert res["null_hit_rate"] is not None                # but the measured null still prints


def test_scored_rows_orphaned_from_the_ledger_say_so():
    root = _new_root()
    _write_desk(root, "ai_desk", [_thesis("a", "2021-01-04", "2021-02-01")],
                scored=[{"id": "gone", "outcome": "hit", "directionally_correct": True}])
    res = dp.null_baseline(root, "ai_desk", {"overall": {"n": 1, "hits": 1}}, "2021-04-01")
    assert res["available"] is False
    assert "absent from the thesis ledger" in res["reason"]


def test_null_baseline_degrades_without_raising():
    root = _new_root()
    assert dp.null_baseline(root, "ai_desk", {}, "2021-01-01")["available"] is False
    assert dp.null_baseline(root, "ai_desk", {"overall": {"n": 12}},
                            "2021-01-01")["available"] is False
    assert dp.null_baseline(root, "nope", None, "2021-01-01")["null_hit_rate"] is None
