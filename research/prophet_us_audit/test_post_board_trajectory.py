"""Unit tests for the post-board-trajectory departure detector and its classifier.

Synthetic board sequences only — no repo data, no network. The four cases the
commissioning brief names, plus the traps this instrument can actually fall into:

  * a CLEAN departure (present on d, absent on d+1) is one departure;
  * a GAP is not a departure — when the lane key is absent from a board (no board
    written, or the lane not yet born), a name present either side of it must NOT be
    read as having left and come back. This is the outage trap: the frame ends
    2026-07-31 and 08-01..08-05 carry no board at all;
  * a RE-ENTRY after a real departure is two episodes, not one, and the gap is measured
    in BOARD dates rather than calendar days;
  * a DELISTING is kept and flagged, never dropped — dropping a name that stops printing
    deletes exactly the losers a post-departure study exists to find;
  * an episode ending on the LAST board date is CENSORED, not departed;
  * ``x is True`` on a numpy bool is ALWAYS False (memory:
    numpy-bool-is-true-deadens-a-feature-leg), so every truth test goes through
    ``_truthy``;
  * the era detector must fire ONCE per construction change — a level test smears across
    the window unless it is de-smeared, and a one-day delta test fires on ordinary churn.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def _load():
    """Import the instrument by path (it lives outside any package)."""
    cwd = os.getcwd()
    spec = importlib.util.spec_from_file_location(
        "post_board_trajectory", Path(__file__).resolve().parent / "post_board_trajectory.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # module chdir()s to REPO at import
    os.chdir(cwd)
    return mod


PBT = _load()

DATES = ["2026-07-01", "2026-07-02", "2026-07-06", "2026-07-07", "2026-07-08"]


# ------------------------------------------------------------------ fixtures --
def _row(as_of, ticker, *, lane="buy", family="v1", position=0, entry_status="buy_now",
         eligible=True, ticks=1, cycle_blocked=False, tier_cascade="T1",
         sector="Industrials", rank_by="confluence"):
    return {"as_of": as_of, "family": family, "lane": lane, "position": position,
            "ticker": ticker, "sector": sector, "state": "FRESH BUY", "urgency": "now",
            "dir": "up", "align_tier": "aligned", "alpha": 0.0,
            "entry_status": entry_status, "act_level": 1,
            "eligible": eligible, "tier": "take", "sig_reason": "", "above200": True,
            "weekly_bull": True, "ticks": ticks, "tier_cascade": tier_cascade,
            "conv_score": 50, "conv_band": "medium", "cycle_blocked": cycle_blocked,
            "rank_pctile": 50, "trust_tier": None, "source": "test",
            "_rank_by": rank_by}


def _frames(rows, dates=None, lane="buy", family="v1"):
    """(rows, presence) for a lane present on every date in ``dates``."""
    dates = dates or DATES
    rdf = pd.DataFrame(rows).drop(columns=["_rank_by"], errors="ignore")
    pres = pd.DataFrame([
        {"family": family, "lane": lane, "as_of": d, "source": "test",
         "n": int(sum(1 for r in rows if r["as_of"] == d)), "rank_by": "confluence"}
        for d in dates])
    return rdf, pres


# ------------------------------------------------------- 1. clean departure --
def test_clean_departure_is_one_departure_with_the_next_board_as_drop_date():
    rows = [_row(d, "AAA") for d in DATES[:3]]          # 07-01, 07-02, 07-06
    rows += [_row(d, "BBB") for d in DATES]             # never leaves
    rdf, pres = _frames(rows)
    eps = PBT.build_episodes(rdf, pres)
    a = eps[eps.ticker == "AAA"]
    assert len(a) == 1
    ep = a.iloc[0]
    assert bool(ep["departed"]) is True
    assert ep["first_seen"] == "2026-07-01"
    assert ep["last_seen"] == "2026-07-06"
    # the drop date is the next BOARD date, which is what a holder could act on
    assert ep["drop_date"] == "2026-07-07"
    assert int(ep["board_days"]) == 3


def test_episode_ending_on_the_final_board_date_is_censored_not_departed():
    """The frame ends 2026-07-31 and no board exists after it. Reading those names as
    departures would invent 152 exits out of an outage."""
    rows = [_row(d, "AAA") for d in DATES]
    rdf, pres = _frames(rows)
    eps = PBT.build_episodes(rdf, pres)
    ep = eps.iloc[0]
    assert bool(ep["departed"]) is False
    assert ep["drop_date"] is None
    dep = PBT.classify(eps, rdf, {})
    assert dep.iloc[0]["dep_class"] == "censored_frame_end"


# --------------------------------------------------- 2. a gap is not an exit --
def test_missing_board_date_is_not_a_departure():
    """No board written on 07-06: the lane key is absent, so the date is not in the
    lane's sequence and a name present either side of it never left."""
    present = ["2026-07-01", "2026-07-02", "2026-07-07", "2026-07-08"]
    rows = [_row(d, "AAA") for d in present]
    rdf, pres = _frames(rows, dates=present)           # 07-06 absent from presence
    eps = PBT.build_episodes(rdf, pres)
    assert len(eps) == 1, "a calendar gap must not split an episode"
    assert bool(eps.iloc[0]["departed"]) is False      # ends on the last board date
    assert int(eps.iloc[0]["board_days"]) == 4


def test_lane_present_but_empty_does_depart_everyone():
    """The mirror case: the lane KEY exists and the list is empty. That is a real exit
    for every name in it, and must not be confused with the key being absent."""
    rows = [_row(d, "AAA") for d in DATES[:2]]
    rdf, pres = _frames(rows, dates=DATES)             # lane present on all 5 dates
    eps = PBT.build_episodes(rdf, pres)
    assert bool(eps.iloc[0]["departed"]) is True
    assert eps.iloc[0]["drop_date"] == "2026-07-06"


# ------------------------------------------------------------- 3. re-entry ---
def test_reentry_after_departure_is_two_episodes():
    rows = [_row(d, "AAA") for d in ["2026-07-01", "2026-07-02", "2026-07-08"]]
    rdf, pres = _frames(rows, dates=DATES)
    eps = PBT.build_episodes(rdf, pres).sort_values("episode_ix")
    assert len(eps) == 2
    first, second = eps.iloc[0], eps.iloc[1]
    assert bool(first["departed"]) is True and first["drop_date"] == "2026-07-06"
    assert bool(second["reentry"]) is True
    assert bool(second["departed"]) is False           # 07-08 is the last board date
    # the gap is counted in BOARD dates (07-06, 07-07), not calendar days
    assert int(second["boards_out_before_reentry"]) == 2
    assert bool(first["reentry"]) is False


# ------------------------------------------------------------ 4. delisting ---
def _panel(px: pd.DataFrame, bench: pd.Series):
    return PBT.Panel(px, str(px.index.max().date()), bench=bench)


def test_delisted_name_is_kept_and_flagged_truncated_not_dropped():
    idx = pd.bdate_range("2026-06-01", periods=30)
    bench = pd.Series(np.linspace(100.0, 110.0, len(idx)), index=idx)
    alive = pd.Series(np.linspace(50.0, 60.0, len(idx)), index=idx)
    dead = alive.copy()
    dead.iloc[15:] = np.nan                            # stops printing at bar 15
    px = pd.DataFrame({"ALIVE": alive, "DEAD": dead, "PAD": alive * 1.01})
    p = _panel(px, bench)

    anchor = str(idx[5].date())
    got = p.excess("DEAD", anchor, 10)                 # horizon lands after the last print
    assert got is not None and got["status"] == "ok", "a delisted name must not vanish"
    assert bool(got["truncated"]) is True
    assert got["sessions_priced"] < 10
    # liquidated at the last print: the terminal price is the last real close
    last = float(dead.dropna().iloc[-1])
    exp = ((last / float(dead.loc[idx[5]]) - 1.0)
           - (float(bench.iloc[15]) / float(bench.iloc[5]) - 1.0)) * 100.0
    assert got["excess_spy_pp"] == pytest.approx(exp, abs=1e-6)

    ok = p.excess("ALIVE", anchor, 10)
    assert bool(ok["truncated"]) is False and ok["sessions_priced"] == 10


def test_immature_horizon_returns_none_and_is_not_confused_with_unpriced():
    """A horizon past the end of the frame is a BUDGET fact. Booking it as unpriced (or
    as a zero) would manufacture observations — H=42/63 have n=0 on the real frame for
    exactly this reason, and that must stay visible as immaturity."""
    idx = pd.bdate_range("2026-06-01", periods=12)
    bench = pd.Series(np.linspace(100.0, 105.0, len(idx)), index=idx)
    px = pd.DataFrame({"AAA": pd.Series(np.linspace(10.0, 12.0, len(idx)), index=idx)})
    p = _panel(px, bench)
    assert p.excess("AAA", str(idx[8].date()), 10) is None       # off the end
    assert p.excess("AAA", str(idx[0].date()), 10)["status"] == "ok"
    assert p.excess("ZZZ", str(idx[0].date()), 5)["status"] == "unpriced"


# ------------------------------------------------- 5. class assignment logic --
def _classify_one(**state):
    """One departing name on 07-02, with the state it carried at last appearance."""
    rows = [_row("2026-07-01", "AAA", **state), _row("2026-07-02", "AAA", **state),
            _row("2026-07-01", "KEEP"), _row("2026-07-02", "KEEP"),
            _row("2026-07-06", "KEEP")]
    rdf, pres = _frames(rows, dates=DATES[:3])
    eps = PBT.build_episodes(rdf, pres)
    dep = PBT.classify(eps, rdf, {})
    return dep[dep.ticker == "AAA"].iloc[0]


def test_ran_status_classifies_as_ran_advanced():
    r = _classify_one(entry_status="hold")             # in engine _RAN_STATUSES
    assert r["dep_class"] == "ran_advanced"
    assert bool(r["flag_ran"]) is True


def test_stamped_veto_classifies_as_veto_blocked_and_outranks_freshness():
    r = _classify_one(entry_status="buy_now", cycle_blocked=True, ticks=5)
    assert r["dep_class"] == "veto_blocked"
    assert bool(r["flag_fresh_edge"]) is True, "the overlapping flag still records itself"


def test_aged_cross_classifies_as_freshness_edge():
    r = _classify_one(entry_status="buy_now", ticks=PBT.FRESH_TICKS)
    assert r["dep_class"] == "freshness_edge"


def test_eligible_false_is_gate_ineligible_not_veto_blocked():
    """Before 2026-07-17 `eligible=False` was the MODAL state of the buy lane. Calling it
    a veto there would be a misassignment, and a misassigned class is worse than an
    honest unknown."""
    r = _classify_one(entry_status="buy_now", eligible=False, ticks=0, tier_cascade="T1")
    assert r["dep_class"] == "gate_ineligible"
    assert bool(r["flag_veto"]) is False


def test_still_eligible_absent_is_the_vale_class():
    r = _classify_one(entry_status="buy_now", eligible=True, ticks=0, cycle_blocked=False)
    assert r["dep_class"] == "still_eligible_absent"


def test_absent_gate_state_is_its_own_class_never_silently_bucketed():
    r = _classify_one(entry_status=None, eligible=None, ticks=None, tier_cascade=None)
    assert r["dep_class"] == "gate_state_absent"
    assert bool(r["flag_gate_absent"]) is True


def test_lane_move_outranks_state_classes():
    """A name that shows up in another lane on the drop date did not leave the board."""
    rows = [_row("2026-07-01", "AAA", entry_status="hold"),
            _row("2026-07-02", "AAA", entry_status="hold"),
            _row("2026-07-06", "AAA", lane="watch", entry_status="hold")]
    rdf = pd.DataFrame(rows).drop(columns=["_rank_by"], errors="ignore")
    pres = pd.DataFrame(
        [{"family": "v1", "lane": "buy", "as_of": d, "n": 1, "rank_by": "confluence"}
         for d in DATES[:3]]
        + [{"family": "v1", "lane": "watch", "as_of": d, "n": 1, "rank_by": "confluence"}
           for d in DATES[:3]])
    eps = PBT.build_episodes(rdf, pres)
    dep = PBT.classify(eps, rdf, {})
    buy_ep = dep[(dep.ticker == "AAA") & (dep.lane == "buy")].iloc[0]
    assert buy_ep["dep_class"] == "lane_move"
    assert buy_ep["move_to"] == "watch"


def test_era_break_outranks_every_state_class():
    rows = [_row("2026-07-01", "AAA", entry_status="hold"),
            _row("2026-07-02", "AAA", entry_status="hold"),
            _row("2026-07-01", "KEEP"), _row("2026-07-02", "KEEP"),
            _row("2026-07-06", "KEEP")]
    rdf, pres = _frames(rows, dates=DATES[:3])
    breaks = {("v1", "buy"): {"2026-07-06": ["rank_by A -> B"]}}
    dep = PBT.classify(PBT.build_episodes(rdf, pres), rdf, breaks)
    r = dep[dep.ticker == "AAA"].iloc[0]
    assert r["dep_class"] == "roster_break"
    assert r["era_break_trigger"] == "rank_by A -> B"


def test_every_departure_gets_exactly_one_class_from_the_declared_vocabulary():
    """No departure may fall through the ladder into a null class."""
    vocab = set(PBT._CLASS_ORDER) | {"censored_frame_end"}
    for state in ({"entry_status": "hold"}, {"eligible": False}, {"cycle_blocked": True},
                  {"ticks": 9}, {"entry_status": None, "eligible": None, "ticks": None},
                  {"tier_cascade": "T4", "entry_status": "buy_now", "ticks": 0}):
        r = _classify_one(**state)
        assert r["dep_class"] in vocab
        assert isinstance(r["dep_class"], str) and r["dep_class"]


# ------------------------------------------------------ 6. era-break detector --
def _presence(sizes: dict, rank_by: dict | None = None, lane="buy"):
    rank_by = rank_by or {}
    return pd.DataFrame([
        {"family": "v1", "lane": lane, "as_of": d, "n": n,
         "rank_by": rank_by.get(d, "confluence")}
        for d, n in sizes.items()])


def _rows_for(sizes: dict, eligible=True, lane="buy"):
    out = []
    for d, n in sizes.items():
        for i in range(n):
            out.append(_row(d, f"T{i}", lane=lane, position=i, eligible=eligible))
    return pd.DataFrame(out).drop(columns=["_rank_by"], errors="ignore")


def test_a_cap_change_fires_exactly_one_break_not_a_smear():
    """A LEVEL test straddles the break: without de-smearing, the three dates around one
    cap cut all trip it (06-24/25/26/29 for the single 06-25 cut on the real board)."""
    days = [f"2026-07-{d:02d}" for d in (1, 2, 3, 6, 7, 8, 9, 10)]
    sizes = dict(zip(days, [120, 120, 120, 33, 34, 35, 33, 34]))
    breaks = PBT.detect_era_breaks(_rows_for(sizes), _presence(sizes))
    hit = breaks.get(("v1", "buy"), {})
    assert list(hit) == ["2026-07-06"], f"expected one break date, got {list(hit)}"


def test_gradual_drift_is_not_a_construction_break():
    """A board quietly emptying over a week is DRIFT. Misfiling it as a roster break
    would move real signal departures into the construction bucket and hide them.

    The level shift here CLEARS both size gates (100 -> 20 is 80 names and 80%), so only
    the step-share test can reject it: no single day carries 60% of the move. A weaker
    fixture (40 -> 16 in fours) never reaches either gate and would pass against a
    detector with the step test deleted — measured, not assumed.
    """
    days = [f"2026-07-{d:02d}" for d in (1, 2, 3, 6, 7, 8, 9, 10, 13)]
    sizes = dict(zip(days, [100, 100, 100, 80, 60, 40, 20, 20, 20]))
    breaks = PBT.detect_era_breaks(_rows_for(sizes), _presence(sizes))
    assert breaks.get(("v1", "buy"), {}) == {}, "a week-long slide is not a cap change"


def test_small_lane_churn_is_not_a_cap_change():
    """The real 2026-07-08 case: an 18-name lane drops to 10. That is 44% — over the
    relative gate — but 8 names, so only the ABSOLUTE floor rejects it. Without the
    floor, ordinary churn in a 10-20 name lane manufactures construction seams and eats
    the signal departures on those dates."""
    days = [f"2026-07-{d:02d}" for d in (1, 2, 3, 6, 7, 8)]
    sizes = dict(zip(days, [18, 18, 18, 10, 10, 10]))
    breaks = PBT.detect_era_breaks(_rows_for(sizes), _presence(sizes))
    assert breaks.get(("v1", "buy"), {}) == {}
    # ...and the SAME shape at scale IS a cap change, so the floor is not just an off switch
    big = dict(zip(days, [180, 180, 180, 100, 100, 100]))
    hit = PBT.detect_era_breaks(_rows_for(big), _presence(big)).get(("v1", "buy"), {})
    assert list(hit) == ["2026-07-06"]


def test_null_rank_by_does_not_fire_a_break_on_every_date():
    """`nan != nan` fired a false break on EVERY v2 board date until rank_by was
    normalised — 21 phantom construction seams on a 22-date lane."""
    days = [f"2026-07-{d:02d}" for d in (1, 2, 3, 6, 7)]
    sizes = dict.fromkeys(days, 8)
    pres = _presence(sizes)
    pres["rank_by"] = np.nan
    assert PBT.detect_era_breaks(_rows_for(sizes), pres).get(("v1", "buy"), {}) == {}


def test_two_cap_steps_inside_one_window_collapse_to_the_first_KNOWN_LIMITATION():
    """Pins a known limitation rather than a desired behaviour.

    The run-collapse keeps one date per contiguous candidate run. When TWO genuine cap
    steps fall within ERA_WINDOW of each other (100 -> 60 -> 20 here), both are inside
    one run and only the first is emitted — the second construction change is silently
    folded into the first. On the real frame the two cap changes are 20 board dates apart
    (2026-06-25 and 2026-07-28) and the third seam fires through rank_by, which is exact
    and never collapsed, so this cannot bite there. It would bite on a future board that
    re-caps twice in a week, and the fix would be a per-step changepoint pass, not a
    threshold tweak. If this test ever starts failing with BOTH dates present, that is
    the improvement landing — update the assertion, do not delete it.
    """
    days = [f"2026-07-{d:02d}" for d in (1, 2, 3, 6, 7, 8, 9, 10)]
    sizes = dict(zip(days, [100, 100, 100, 60, 60, 20, 20, 20]))
    hit = PBT.detect_era_breaks(_rows_for(sizes), _presence(sizes)).get(("v1", "buy"), {})
    assert list(hit) == ["2026-07-06"], (
        "documented limitation: the second step (2026-07-08) is folded into the first")


def test_rank_by_change_is_an_exact_dated_break():
    days = [f"2026-07-{d:02d}" for d in (1, 2, 3, 6, 7)]
    sizes = dict.fromkeys(days, 20)
    rb = {d: ("conviction" if d < "2026-07-03" else "confluence") for d in days}
    hit = PBT.detect_era_breaks(_rows_for(sizes), _presence(sizes, rb)).get(("v1", "buy"), {})
    assert list(hit) == ["2026-07-03"]
    assert "rank_by conviction -> confluence" in hit["2026-07-03"][0]


# ------------------------------------------------------------- 7. the traps --
def test_truthy_survives_numpy_bools():
    """``x is True`` on a numpy bool is ALWAYS False. A classifier written that way
    silently reads every numpy-typed flag as absent and the class quietly empties."""
    assert PBT._truthy(np.bool_(True)) is True
    assert PBT._truthy(np.bool_(False)) is False
    assert (np.bool_(True) is True) is False, "the trap this guards is still real"
    assert PBT._truthy(None) is False and PBT._truthy(np.nan) is False
    assert PBT._is_false(np.bool_(False)) is True
    assert PBT._is_false(None) is False, "absent is not False — it is its own class"
    assert PBT._is_false(np.nan) is False


def test_empty_class_is_reported_with_a_zero_fire_count_not_omitted():
    """A silently absent class reads as 'nothing to see'; a printed n=0 reads as a hole."""
    idx = pd.bdate_range("2026-06-01", periods=30)
    bench = pd.Series(np.linspace(100.0, 110.0, len(idx)), index=idx)
    px = pd.DataFrame({"AAA": pd.Series(np.linspace(10.0, 11.0, len(idx)), index=idx),
                       "KEEP": pd.Series(np.linspace(10.0, 12.0, len(idx)), index=idx)})
    p = _panel(px, bench)
    d0, d1, d2 = (str(idx[i].date()) for i in (0, 1, 2))
    rows = [_row(d0, "AAA", entry_status="hold"), _row(d1, "AAA", entry_status="hold"),
            _row(d0, "KEEP"), _row(d1, "KEEP"), _row(d2, "KEEP")]
    rdf, pres = _frames(rows, dates=[d0, d1, d2])
    dep = PBT.classify(PBT.build_episodes(rdf, pres), rdf, {})
    out = PBT.grade(dep, p, {"AAA": "Industrials"})
    by_class = out["per_horizon"]["H5"]["by_class"]
    assert by_class["ran_advanced"]["n"] == 1
    for absent in ("veto_blocked", "still_eligible_absent", "roster_break"):
        assert by_class[absent]["n"] == 0
        assert by_class[absent]["fire_count"] == 0
        assert "EMPTY CLASS" in by_class[absent]["note"]


def test_loser_threshold_and_thin_flag_are_stated_in_every_block():
    b = PBT.stats_block([-5.0, -1.0, 2.0], [-5.0, -1.0, 2.0], ["A", "B", "C"])
    assert b["loser_rate_pct"] == pytest.approx(100 * 1 / 3, abs=0.1)
    assert b["thin"] is True and "THIN CELL" in b["thin_note"]
    assert PBT.LOSER_PP == -3.0


def test_half_split_reports_unrunnable_rather_than_a_vacuous_pass():
    """A cohort drawn from ONE date cannot be split in time; saying 'stable' there would
    be a vacuous pass."""
    one = ["2026-07-01"] * 6
    out = PBT.half_split(one, [1.0] * 6, [0.0] * 6, list("ABCDEF"))
    assert "UNRUNNABLE" in out["note"]
    two = ["2026-07-01"] * 3 + ["2026-07-08"] * 3
    out2 = PBT.half_split(two, [1.0, 2.0, 3.0, -1.0, -2.0, -3.0], [0.0] * 6, list("ABCDEF"))
    assert out2["distinct_dates"] == 2
    assert bool(out2["sign_flip_across_halves"]) is True


def test_contiguous_runs():
    assert PBT._contiguous_runs([0, 1, 2, 5, 6, 9]) == [[0, 1, 2], [5, 6], [9]]
    assert PBT._contiguous_runs([]) == []
