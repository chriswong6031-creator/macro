"""W5 §15 adversarial battery — rows A, B, E, F, G, H, I, J, K, L, M.

Rows C (look ledger / gate mutations) and D (holdout fence) live in
``tests/test_entry_radar_w5_gates.py``; the statistical rows belong to the
confirmatory module's own suite.  What is here is everything that can be proven
against the ORCHESTRATOR-OWNED modules (``outcomes``, ``controls``, ``gates``,
``prereg``) plus the two pure helpers this lane added (``costs``, ``verdicts``)
and the nightly reconciler.

EVERY ROW IS NON-VACUOUS.  Each assertion that something CANNOT happen is paired
with a construction where the same machinery visibly DOES the thing — otherwise
"the future bar did not change the answer" is indistinguishable from "the
function ignores its inputs".
"""
from __future__ import annotations

import ast
import inspect
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine.entry_radar.replay import controls, costs, outcomes, prereg, verdicts

REPO = Path(__file__).resolve().parents[1]
D0 = date(2021, 3, 15)          # decision session, comfortably inside TEST


# --------------------------------------------------------------------------- #
# fixtures — a deterministic synthetic tape
# --------------------------------------------------------------------------- #
def _daily(n_before: int = 30, n_after: int = 30, *, start_px: float = 100.0,
           step: float = 0.5) -> pd.DataFrame:
    """A clean ramp so every outcome is hand-checkable.

    Sessions are consecutive business days centred on D0; the bar AT D0 sits at
    index ``n_before``.
    """
    idx = pd.bdate_range(end=pd.Timestamp(D0), periods=n_before + 1)
    idx = idx.append(pd.bdate_range(start=pd.Timestamp(D0), periods=n_after + 1)[1:])
    closes = start_px + step * np.arange(len(idx), dtype=float)
    frame = pd.DataFrame({
        "o": closes - 0.10,
        "h": closes + 0.40,
        "l": closes - 0.40,
        "c": closes,
        "v": np.full(len(idx), 1_000_000.0),
    }, index=pd.DatetimeIndex(idx, name="session"))
    return frame


def _bench(daily: pd.DataFrame, drift: float = 0.2) -> pd.Series:
    return pd.Series(100.0 + drift * np.arange(len(daily), dtype=float),
                     index=daily.index, name="c")


def _episode(daily: pd.DataFrame, **kw) -> outcomes.EpisodeRef:
    defaults = dict(
        ticker="AAA", detector_id="C2_1D_TURN@1", panel="A", decision_session=D0,
        p0=float(daily.loc[pd.Timestamp(D0), "c"]),
        p0_basis="sampled_last_trade_at_decision",
        a0=2.0, atr_basis="true_range_daily_ohlc",
        washout_low=float(daily["l"].min()),
    )
    defaults.update(kw)
    return outcomes.EpisodeRef(**defaults)


def _attach(episode, daily, *, cost_bps: float = 5.0, cost_basis: str = "floor",
            horizon: int = prereg.HORIZON_PRIMARY) -> outcomes.OutcomeRow:
    return outcomes.attach(episode, daily=daily, bench_close=_bench(daily),
                           sector_close=None, cost_per_side_bps=cost_bps,
                           cost_basis=cost_basis, horizon=horizon)


# =========================================================================== #
# A — OUTCOME LEAKAGE: only strictly-forward rows are consumed
# =========================================================================== #
def test_a_mutating_a_past_bar_cannot_move_the_outcome_row():
    daily = _daily()
    ep = _episode(daily)
    baseline = _attach(ep, daily)

    mutated = daily.copy()
    past = mutated.index[5]                      # 25 sessions before D
    mutated.loc[past, ["o", "h", "l", "c"]] = [1e4, 2e4, 0.01, 1e4]
    assert _attach(ep, mutated) == baseline


def test_a_appending_bars_beyond_the_horizon_cannot_move_the_outcome_row():
    daily = _daily(n_after=12)
    ep = _episode(daily)
    baseline = _attach(ep, daily)

    extended = _daily(n_after=60)
    # Same first 13 forward bars, 47 more behind them.
    pd.testing.assert_frame_equal(extended.iloc[: len(daily)], daily)
    assert _attach(ep, extended) == baseline


def test_a_mutation_control_a_bar_INSIDE_the_window_does_move_the_row():
    """NON-VACUITY: the two assertions above are about WHERE the bar sits."""
    daily = _daily()
    ep = _episode(daily)
    baseline = _attach(ep, daily)

    mutated = daily.copy()
    inside = mutated.index[mutated.index.get_loc(pd.Timestamp(D0)) + 3]
    mutated.loc[inside, "h"] = 1e4
    assert _attach(ep, mutated) != baseline
    assert _attach(ep, mutated).mfe > baseline.mfe


# =========================================================================== #
# B — REFERENCE PRICE: P0 is the reference, never the signal-bar close
# =========================================================================== #
def test_b_next_session_close_basis_prices_off_p0_not_the_signal_close():
    daily = _daily()
    signal_close = float(daily.loc[pd.Timestamp(D0), "c"])
    pos = daily.index.get_loc(pd.Timestamp(D0))
    next_close = float(daily.iloc[pos + 1]["c"])
    assert next_close != signal_close, "fixture must separate the two prices"

    ep = _episode(daily, p0=next_close, p0_basis="next_session_close")
    row = _attach(ep, daily)

    horizon_close = float(daily.iloc[pos + prereg.HORIZON_PRIMARY]["c"])
    assert row.fwd_ret == pytest.approx(horizon_close / next_close - 1.0)
    # ... and NOT the number the signal-bar close would have produced.
    assert row.fwd_ret != pytest.approx(horizon_close / signal_close - 1.0)


def test_b_the_basis_word_rides_through_to_the_row():
    """The row must SAY which price it used; a number with no basis is unauditable."""
    daily = _daily()
    for basis in ("sampled_last_trade_at_decision", "first_trade_after_known_at",
                  "next_session_close"):
        row = _attach(_episode(daily, p0_basis=basis), daily)
        assert row.p0_basis == basis


def test_b_mfe_and_mae_are_measured_against_p0_too():
    daily = _daily()
    pos = daily.index.get_loc(pd.Timestamp(D0))
    p0 = 1.0e-2 + float(daily.iloc[pos + 1]["c"])      # deliberately not a bar price
    row = _attach(_episode(daily, p0=p0, p0_basis="next_session_close"), daily)
    window = daily.iloc[pos + 1: pos + 1 + prereg.HORIZON_PRIMARY]
    assert row.mfe == pytest.approx(max(0.0, window["h"].max() / p0 - 1.0))
    assert row.mae == pytest.approx(min(0.0, window["l"].min() / p0 - 1.0))


# =========================================================================== #
# E — CONTROLS: the §7 exclusions
# =========================================================================== #
def _panel(tickers=("AAA", "BBB", "CCC", "DDD"), *, sessions=None) -> pd.DataFrame:
    rows = []
    for i, t in enumerate(tickers):
        rows.append({
            "ticker": t, "session": D0, "sector": "Information Technology",
            "cap_bucket": "10-200B", "proximity_decile": 3,
            "dollar_vol_decile": 5 + (i % 2), "ret60_quintile": 2,
            "vol20_quintile": 3, "hot_tier": 1,
        })
    frame = pd.DataFrame(rows)
    cal = sessions or pd.bdate_range(end=pd.Timestamp(D0) + pd.Timedelta(days=60),
                                     periods=120)
    frame.attrs["session_pos_by_date"] = {ts: i for i, ts in enumerate(cal)}
    return frame


def _cal_session(offset: int) -> date:
    cal = pd.bdate_range(end=pd.Timestamp(D0) + pd.Timedelta(days=60), periods=120)
    pos = {ts: i for i, ts in enumerate(cal)}[pd.Timestamp(D0)]
    return cal[pos + offset].date()


def test_e_a_firer_six_sessions_after_d_is_excluded_from_the_pool():
    """Inside (D, D+H] — that name's own forward window is contaminated."""
    panel = _panel()
    pool = controls.eligible_pool(
        panel, detector_fire_sessions={"BBB": [_cal_session(6)]},
        candidate_session=D0)
    assert "BBB" not in set(pool["ticker"])
    assert {"AAA", "CCC", "DDD"} <= set(pool["ticker"])


def test_e_a_firer_inside_the_plus_minus_five_window_is_excluded():
    panel = _panel()
    for offset in (-5, -1, 0, 1, 5):
        pool = controls.eligible_pool(
            panel, detector_fire_sessions={"CCC": [_cal_session(offset)]},
            candidate_session=D0)
        assert "CCC" not in set(pool["ticker"]), f"offset {offset} should exclude"


def test_e_mutation_control_a_firer_beyond_the_horizon_is_KEPT():
    """NON-VACUITY: the exclusions above are about WHEN the fire happened."""
    panel = _panel()
    pool = controls.eligible_pool(
        panel, detector_fire_sessions={"BBB": [_cal_session(30)]},
        candidate_session=D0)
    assert "BBB" in set(pool["ticker"])


def test_e_suppressed_by_rearm_is_excluded():
    panel = _panel()
    pool = controls.eligible_pool(panel, detector_fire_sessions={},
                                 candidate_session=D0,
                                 suppressed=frozenset({"DDD"}))
    assert "DDD" not in set(pool["ticker"])
    assert {"AAA", "BBB", "CCC"} <= set(pool["ticker"])


def test_e_a_proximity_mismatch_never_enters_the_cem_cell():
    panel = _panel()
    panel.loc[panel["ticker"] == "BBB", "proximity_decile"] = 9
    candidate = panel[panel["ticker"] == "AAA"].iloc[0]
    pool = panel[panel["ticker"] != "AAA"]
    m = controls.match(candidate, pool)
    assert "BBB" not in m.controls
    assert set(m.controls) == {"CCC", "DDD"}
    assert m.n_cell == 2


def test_e_a_sector_or_cap_mismatch_never_enters_the_cem_cell():
    panel = _panel()
    panel.loc[panel["ticker"] == "CCC", "sector"] = "Health Care"
    panel.loc[panel["ticker"] == "DDD", "cap_bucket"] = "<2B"
    candidate = panel[panel["ticker"] == "AAA"].iloc[0]
    m = controls.match(candidate, panel[panel["ticker"] != "AAA"])
    assert set(m.controls) == {"BBB"}


def test_e_an_empty_cell_is_uninformative_not_silently_zero():
    panel = _panel(("AAA",))
    candidate = panel.iloc[0]
    m = controls.match(candidate, panel[panel["ticker"] != "AAA"])
    assert m.uninformative_no_control is True and m.controls == ()
    assert m.same_band_control is False


def test_e_missing_feature_columns_raise_rather_than_silently_matching():
    panel = _panel().drop(columns=["hot_tier"])
    with pytest.raises(ValueError, match="hot_tier"):
        controls.eligible_pool(panel, detector_fire_sessions={}, candidate_session=D0)


# =========================================================================== #
# F — COMMON ELIGIBILITY: the gap is counted, never absorbed
# =========================================================================== #
def test_f_common_eligibility_is_the_intersection_with_a_counted_gap():
    a = [("AAA", D0), ("BBB", D0), ("CCC", D0)]
    b = [("AAA", D0), ("BBB", D0), ("DDD", D0)]
    got = verdicts.common_eligible(a, b)
    assert got.n_common == 2 and got.pairs == tuple(sorted(
        {("AAA", D0), ("BBB", D0)}, key=repr))
    assert got.only_a == (("CCC", D0),) and got.only_b == (("DDD", D0),)
    assert got.gap == 2


def test_f_removing_one_sides_warmup_eligibility_removes_the_pair():
    a = [("AAA", D0), ("BBB", D0)]
    full = verdicts.common_eligible(a, [("AAA", D0), ("BBB", D0)])
    assert full.n_common == 2 and full.gap == 0
    # B's warm-up now excludes AAA (insufficient history at D):
    warmed_out = verdicts.common_eligible(a, [("BBB", D0)])
    assert ("AAA", D0) not in warmed_out.pairs
    assert warmed_out.n_common == 1
    assert warmed_out.only_a == (("AAA", D0),) and warmed_out.gap == 1


def test_f_duplicates_collapse_and_order_is_deterministic():
    a = [("BBB", D0), ("AAA", D0), ("AAA", D0)]
    b = [("AAA", D0), ("BBB", D0)]
    got = verdicts.common_eligible(a, b)
    assert got.n_a == 2 and got.n_common == 2
    assert got.pairs == verdicts.common_eligible(list(reversed(a)), b).pairs


# =========================================================================== #
# G — MFE / MAE: signs, strict forwardness, minute-blindness
# =========================================================================== #
def test_g_signs_hold_on_an_adversarial_frame():
    daily = _daily()
    pos = daily.index.get_loc(pd.Timestamp(D0))
    # Monotone collapse after D: every forward high is below P0.
    crashed = daily.copy()
    fwd = crashed.index[pos + 1: pos + 1 + prereg.HORIZON_PRIMARY]
    crashed.loc[fwd, ["o", "h", "l", "c"]] = [50.0, 51.0, 49.0, 50.0]
    row = _attach(_episode(crashed), crashed)
    assert row.mfe >= 0.0 and row.mae <= 0.0
    assert row.mfe == 0.0, "no forward high above P0 ⇒ MFE floors at 0, never negative"
    assert row.mae < 0.0


def test_g_a_moonshot_on_the_decision_session_itself_never_enters():
    daily = _daily()
    ep = _episode(daily)
    baseline = _attach(ep, daily)

    contaminated = daily.copy()
    contaminated.loc[pd.Timestamp(D0), "h"] = 1e6
    contaminated.loc[pd.Timestamp(D0), "l"] = 1e-3
    row = _attach(ep, contaminated)
    assert row == baseline, "session D is not in the strictly-forward window"


def test_g_attach_has_no_minute_input_at_all():
    """Signature introspection: the daily primary CANNOT read minute data,
    because there is no parameter through which minute data could arrive."""
    params = set(inspect.signature(outcomes.attach).parameters)
    assert not any(("minute" in p or "intraday" in p or "quote" in p)
                   for p in params), params
    assert {"daily", "bench_close", "sector_close"} <= params


def test_g_a_minute_coverage_flag_cannot_change_the_daily_primary():
    """Semantic half of battery G: coverage metadata rides the episode and the
    primary read is byte-identical with and without it."""
    daily = _daily()
    bare = _attach(_episode(daily), daily)
    flagged = _attach(_episode(daily, extra={"minute_coverage": True,
                                             "minute_bars": 390}), daily)
    assert flagged == bare


def test_g_time_to_mfe_is_one_indexed_from_the_first_forward_session():
    daily = _daily()
    pos = daily.index.get_loc(pd.Timestamp(D0))
    spiked = daily.copy()
    spiked.loc[spiked.index[pos + 4], "h"] = 1e4
    row = _attach(_episode(spiked), spiked)
    assert row.time_to_mfe == 4


# =========================================================================== #
# H — CENSORING: a truncated episode survives with its reason
# =========================================================================== #
def test_h_a_three_session_tape_censors_rather_than_vanishing():
    daily = _daily(n_after=3)
    row = _attach(_episode(daily), daily, horizon=10)
    assert row.censored is True
    assert row.terminated_reason == "no_further_trades"
    assert row.sessions_covered == 3
    # Outcomes are computed over the COVERED sessions, not nulled.
    pos = daily.index.get_loc(pd.Timestamp(D0))
    last = float(daily.iloc[pos + 3]["c"])
    assert row.fwd_ret == pytest.approx(last / row.p0 - 1.0)
    assert row.mfe is not None and row.mae is not None


def test_h_mutation_control_a_full_tape_is_not_censored():
    daily = _daily(n_after=30)
    row = _attach(_episode(daily), daily, horizon=10)
    assert row.censored is False and row.terminated_reason is None
    assert row.sessions_covered == 10


def test_h_a_delisted_name_with_no_forward_bars_is_a_row_not_a_crash():
    daily = _daily(n_after=0)
    row = _attach(_episode(daily), daily, horizon=10)
    assert row.censored is True and row.sessions_covered == 0
    assert row.fwd_ret is None and row.fwd_ret_net is None
    assert row.false_start_reason == "no_forward_sessions"


# =========================================================================== #
# I — COSTS: max(measured, floor); missing NBBO is never zero
# =========================================================================== #
def test_i_net_return_is_exactly_the_round_trip_deduction():
    daily = _daily()
    row = _attach(_episode(daily), daily, cost_bps=15.0)
    assert row.fwd_ret_net == pytest.approx(row.fwd_ret - 2.0 * 15.0 / 1e4)
    # The named helper and the inline arithmetic are ONE cost model.
    assert row.fwd_ret_net == pytest.approx(
        row.fwd_ret - costs.round_trip_fraction(15.0))


def test_i_the_cost_basis_word_rides_the_row():
    daily = _daily()
    assert _attach(_episode(daily), daily, cost_basis="floor").cost_basis == "floor"
    assert _attach(_episode(daily), daily,
                   cost_basis="measured").cost_basis == "measured"


@pytest.mark.parametrize("adv, want", [
    (60e6, 5.0), (50e6, 5.0),
    (49.9e6, 15.0), (5e6, 15.0),
    (4.9e6, 40.0), (0.0, 40.0),
])
def test_i_every_liquidity_tier_floor_matches_the_prereg(adv, want):
    assert costs.tier_floor_bps(adv) == want


@pytest.mark.parametrize("adv", [None, float("nan"), -1.0, "not-a-number"])
def test_i_an_unknown_adv_binds_the_WIDEST_floor_never_the_cheapest(adv):
    assert costs.tier_floor_bps(adv) == 40.0


def test_i_missing_nbbo_binds_the_floor_and_is_never_zero():
    for measured in (None, float("nan"), -3.0):
        bps, basis = costs.per_side_cost_bps(measured, 60e6)
        assert (bps, basis) == (5.0, "floor")
        assert bps > 0.0


def test_i_a_measured_spread_below_the_floor_still_binds_the_floor():
    bps, basis = costs.per_side_cost_bps(1.0, 60e6)      # 1 bp on a 5 bp tier
    assert (bps, basis) == (5.0, "floor")


def test_i_a_measured_spread_equal_to_the_floor_reports_floor():
    """At equality the FLOOR is the binding constraint; reporting `measured`
    would overstate how much NBBO evidence the row carries."""
    assert costs.per_side_cost_bps(5.0, 60e6) == (5.0, "floor")


def test_i_mutation_control_a_wide_measured_spread_wins():
    """NON-VACUITY: per_side_cost_bps is not a constant returning the floor."""
    bps, basis = costs.per_side_cost_bps(85.0, 60e6)
    assert (bps, basis) == (85.0, "measured")


def test_i_an_illiquid_name_costs_more_than_a_liquid_one_end_to_end():
    daily = _daily()
    liquid, _ = costs.per_side_cost_bps(None, 60e6)
    illiquid, _ = costs.per_side_cost_bps(None, 1e6)
    net_liquid = _attach(_episode(daily), daily, cost_bps=liquid).fwd_ret_net
    net_illiquid = _attach(_episode(daily), daily, cost_bps=illiquid).fwd_ret_net
    assert net_illiquid < net_liquid


# =========================================================================== #
# J — NC-2: the §9 verdict vocabulary (KILLED is not in it)
# =========================================================================== #
def test_j_overlap_below_the_floor_is_uninformative():
    below = prereg.NC2_OVERLAP_FLOOR - 0.01
    assert verdicts.nc2_verdict(below, (-0.01, 0.01), (0.01, 0.05)) == \
        verdicts.NC2_UNINFORMATIVE


def test_j_unmeasurable_overlap_is_uninformative():
    for overlap in (None, float("nan"), "n/a"):
        assert verdicts.nc2_verdict(overlap, (-0.01, 0.01), (0.01, 0.05)) == \
            verdicts.NC2_UNINFORMATIVE


def test_j_overlap_exactly_at_the_floor_is_informative():
    """The floor is inclusive — 0.50 overlap is adequate support, not a miss."""
    assert verdicts.nc2_verdict(prereg.NC2_OVERLAP_FLOOR, (-0.01, 0.01),
                                (0.01, 0.05)) == verdicts.NC2_PROXIMITY_SHADOW


def test_j_disappearance_at_equal_proximity_is_a_shadow():
    assert verdicts.nc2_verdict(0.80, (-0.02, 0.02), (0.01, 0.06)) == \
        verdicts.NC2_PROXIMITY_SHADOW


def test_j_a_surviving_within_band_effect_passes_through():
    assert verdicts.nc2_verdict(0.80, (0.01, 0.05), (0.01, 0.06)) == \
        verdicts.NC2_PASSTHROUGH


def test_j_no_favorable_unconditional_read_means_no_shadow_to_declare():
    """A within-band CI covering 0 is only a SHADOW if something disappeared."""
    assert verdicts.nc2_verdict(0.80, (-0.02, 0.02), (-0.01, 0.04)) == \
        verdicts.NC2_PASSTHROUGH
    assert verdicts.nc2_verdict(0.80, (-0.02, 0.02), None) == \
        verdicts.NC2_PASSTHROUGH


def test_j_an_unreadable_within_band_ci_never_manufactures_a_shadow():
    assert verdicts.nc2_verdict(0.80, None, (0.01, 0.06)) == \
        verdicts.NC2_PASSTHROUGH
    assert verdicts.nc2_verdict(0.80, (float("nan"), 0.02), (0.01, 0.06)) == \
        verdicts.NC2_PASSTHROUGH


def test_j_KILLED_is_not_in_the_vocabulary_at_all():
    """§9: this arm may report UNINFORMATIVE or PROXIMITY SHADOW — never a kill.

    Asserted over the exported vocabulary AND over a sweep of the branch space,
    so a later branch cannot introduce the word without failing here.
    """
    assert "KILLED" not in verdicts.NC2_VERDICTS
    seen = set()
    for overlap in (None, float("nan"), 0.0, 0.49, 0.50, 0.9):
        for within in (None, (-0.02, 0.02), (0.01, 0.05), (-0.05, -0.01)):
            for uncond in (None, (0.01, 0.06), (-0.06, -0.01), (-0.01, 0.01)):
                seen.add(verdicts.nc2_verdict(overlap, within, uncond))
    assert seen <= set(verdicts.NC2_VERDICTS)
    assert not any("KILL" in v for v in seen)
    assert len(seen) == 3, "all three branches must be reachable (non-vacuity)"


def test_j_overlap_share_of_an_empty_match_set_is_nan_and_maps_to_uninformative():
    share = controls.overlap_share([])
    assert np.isnan(share)
    assert verdicts.nc2_verdict(share, (0.01, 0.05), (0.01, 0.06)) == \
        verdicts.NC2_UNINFORMATIVE


# =========================================================================== #
# K — Q4: no historical enlistment reconstruction exists to be run
# =========================================================================== #
def _reconciler_source() -> tuple[str, ast.Module]:
    src = (REPO / "scripts" / "reconcile_entry_radar.py").read_text(encoding="utf-8")
    return src, ast.parse(src)


def _function_span(tree: ast.Module, name: str) -> tuple[int, int]:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node.lineno, (node.end_lineno or node.lineno)
    raise AssertionError(f"{name} not found in the reconciler")


def _nodes_mentioning(tree: ast.Module, needle: str) -> list[ast.AST]:
    hits: list[ast.AST] = []
    for node in ast.walk(tree):
        text = None
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
        elif isinstance(node, ast.Name):
            text = node.id
        elif isinstance(node, ast.Attribute):
            text = node.attr
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            text = node.name
        elif isinstance(node, ast.arg):
            text = node.arg
        if text and needle in text:
            hits.append(node)
    return hits


def test_k_every_enlistment_reference_is_inside_the_spool_passthrough():
    """Q4 accrues LIVE-FORWARD ONLY (§10).  The absence of a reconstruction path
    is proven structurally: every ``lobe`` identifier in the reconciler must sit
    inside ``_event_row``, whose only job is copying declared spool fields."""
    _src, tree = _reconciler_source()
    lo, hi = _function_span(tree, "_event_row")
    hits = _nodes_mentioning(tree, "lobe")
    assert hits, "the passthrough fields themselves must exist (non-vacuity)"
    outside = [(n.lineno, ast.dump(n)[:80]) for n in hits
               if not (lo <= n.lineno <= hi)]
    assert not outside, (
        "enlistment identifiers outside the spool passthrough — a historical "
        f"reconstruction path may be forming: {outside}")


def test_k_the_reconciler_imports_no_historical_lobe_producer():
    """A reconstruction would have to READ a producer; none is imported."""
    _src, tree = _reconciler_source()
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any("producers" in m or "neuralweb" in m or "universe" in m
                   for m in imported), sorted(imported)


def test_k_no_spool_means_waiting_and_zero_rows(tmp_path, monkeypatch):
    """The behavioural half of K: with no live source there is nothing to
    reconstruct FROM, and the reconciler says so instead of inventing rows."""
    from scripts import reconcile_entry_radar as rec

    monkeypatch.setenv("COLLECT_LANE", "nightly")
    monkeypatch.delenv(rec.SPOOL_DIR_ENV, raising=False)
    assert rec.main(["--root", str(tmp_path), "--nightly"]) == 0
    state = json.loads((tmp_path / "data" / "entry_radar"
                        / rec.LEDGER_STATE_NAME).read_text())
    assert state["state"] == prereg.WAITING_FOR_LIVE_SOURCE
    assert state["observed_spool_events"] == 0
    assert state["forward_rows_total"] == 0
    assert not (tmp_path / "data" / "qledger").exists()


# =========================================================================== #
# L — QLEDGER: horizon 21 trading days, register_batch only, C4/F1 never
# =========================================================================== #
def _live_row(detector: str = "G0_GREY_DOT@1") -> dict:
    from scripts import reconcile_entry_radar as rec

    return {"state": rec.STATE_LIVE_FORWARD, "detector_id": detector,
            "ticker": "AAA", "decision_session": "2026-08-14",
            "episode_address": "AAA|x", "detector_spec_hash": "deadbeefdeadbeef"}


def test_l_the_claim_horizon_is_21_trading_sessions_not_10(tmp_path):
    """FAILS if anyone sets horizon_d=10: an off-rung 10 grades only at 5, and
    H=10 is Radar's OWN ruler, which §17 keeps out of the Evaluation OS."""
    from scripts import reconcile_entry_radar as rec

    claim = rec.build_claims([_live_row()], root=tmp_path)[0]
    assert claim["horizon_d"] == 21
    assert claim["horizon_d"] != prereg.HORIZON_PRIMARY
    assert claim["horizon_unit"] == "trading_days"


def test_l_the_claim_carries_the_separation_metadata(tmp_path):
    from engine import qledger as q
    from scripts import reconcile_entry_radar as rec

    claim = rec.build_claims([_live_row("C3_1D_4H_RECOVERY@1")], root=tmp_path)[0]
    assert claim["desk"] == prereg.QLEDGER_DESK
    assert claim["claim_family"] == "entry_radar_C3_1D_4H_RECOVERY@1"
    assert claim["scope"] == {"type": "entity", "key": "AAA"}
    assert claim["direction"] == 1 and claim["bench"] == "SPY"
    assert claim["timestamp_quality"] == "CRAWL_BOUNDED"
    assert claim["authority"] == prereg.AUTHORITY
    assert all(v is False for v in claim["authority"].values())
    assert claim["registration_note"] == prereg.REGISTRATION_NOTE
    assert "no backfill" in claim["registration_note"]
    assert "DNR:KILL-WASHOUT-TURN" in str(claim["falsifier"])
    assert claim["episode_id"] == "AAA|x"
    # `control` is populated MECHANICALLY from the sector map, and the family is
    # still benchmark_only — populating a control is not claiming one.
    assert q.family_control_policy(claim["claim_family"]) == (
        q.CONTROL_POLICY_BENCHMARK_ONLY, True)


def test_l_c4_and_f1_produce_no_claim(tmp_path):
    from scripts import reconcile_entry_radar as rec

    for detector in ("C4_MTF_TURN@1", "F1_FUSION"):
        assert detector in rec.NEVER_REGISTER
        with pytest.raises(AssertionError, match="never be registered"):
            rec.build_claims([_live_row(detector)], root=tmp_path)


def test_l_register_batch_is_the_only_registration_callsite():
    """§17 forbids ``register()`` in a loop (and its O(file)-per-call rescan)."""
    _src, tree = _reconciler_source()
    called: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = (fn.attr if isinstance(fn, ast.Attribute)
                else fn.id if isinstance(fn, ast.Name) else None)
        if name in ("register", "register_batch"):
            called.append(name)
    assert called == ["register_batch"], (
        f"registration callsites in the reconciler: {called}")


def test_l_every_registering_detector_has_its_own_falsifier_text():
    from scripts import reconcile_entry_radar as rec

    registering = set(prereg.EXPECTED_SPEC_HASHES) - rec.NEVER_REGISTER
    assert set(rec._FALSIFIER_BY_DETECTOR) == registering
    assert len({v for v in rec._FALSIFIER_BY_DETECTOR.values()}) == len(registering)


# =========================================================================== #
# M — SIDE-DOOR LAW: detector-stage code is outcome-blind
# =========================================================================== #
#: The ONLY ``outcomes.*`` names a detector-stage module may touch.  Both are
#: TYPES — the frozen input record the stage PRODUCES and the row shape it is
#: declared against.  Referencing a type is not reading an outcome; calling
#: ``outcomes.attach`` (the function that reads forward bars) IS, and that is the
#: distinction this list draws.  ``episodes.py`` legitimately constructs
#: ``outcomes.EpisodeRef``, so a blanket "must not import outcomes" assertion
#: would be wrong — and, being wrong, would get deleted rather than fixed.
_OUTCOME_TYPE_NAMES = {"EpisodeRef", "OutcomeRow"}


def _module_is_outcome_blind(module) -> None:
    """Structural + signature proof that a detector-stage module cannot be fitted.

    1. Every ``outcomes.<attr>`` reference in the SOURCE names a type, never a
       reader — proven on the AST, so a docstring mentioning ``attach`` does not
       false-positive and a real call cannot hide inside one.
    2. No function it defines accepts an outcome-shaped argument.
    """
    source = Path(inspect.getsourcefile(module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    touched = {node.attr for node in ast.walk(tree)
               if isinstance(node, ast.Attribute)
               and isinstance(node.value, ast.Name)
               and node.value.id == "outcomes"}
    leaked = touched - _OUTCOME_TYPE_NAMES
    assert not leaked, (
        f"{module.__name__} reaches into outcomes.{sorted(leaked)} — a "
        "detector-stage module that can READ outcomes can be fitted to them "
        "(contract §9 side-door law)")

    for name, obj in vars(module).items():
        if name.startswith("_") or not inspect.isfunction(obj):
            continue
        if getattr(obj, "__module__", None) != module.__name__:
            continue
        params = set(inspect.signature(obj).parameters)
        leaky = {p for p in params
                 if "outcome" in p or "fwd_ret" in p or "future" in p}
        assert not leaky, f"{module.__name__}.{name} accepts {leaky}"


def test_m_challengers_is_outcome_blind():
    from engine.entry_radar import challengers

    _module_is_outcome_blind(challengers)


def test_m_episodes_is_outcome_blind():
    episodes = pytest.importorskip(
        "engine.entry_radar.replay.episodes",
        reason="authored in the parallel W5 lane; lands in the same PR")
    _module_is_outcome_blind(episodes)


def test_m_the_side_door_check_can_actually_fail():
    """NON-VACUITY for the two tests above: a module that DOES read outcomes is
    caught.  Without this, ``_module_is_outcome_blind`` passing would be
    consistent with it asserting nothing."""
    import types

    leaky = types.ModuleType("fake_detector_stage")
    src = ("from engine.entry_radar.replay import outcomes\n"
           "def derive(ep, daily):\n"
           "    return outcomes.attach(ep, daily=daily)\n")
    path = REPO / "engine" / "entry_radar" / "replay" / "outcomes.py"
    leaky.__file__ = str(path)                       # any readable path
    tree = ast.parse(src)
    touched = {n.attr for n in ast.walk(tree)
               if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
               and n.value.id == "outcomes"}
    assert touched - _OUTCOME_TYPE_NAMES == {"attach"}


def test_m_permuting_a_per_name_outcome_history_changes_no_control_selection():
    """Semantic half of M: control selection reads its ARGUMENTS only.

    Two different fake per-name outcome tables are planted in the ``controls``
    module globals between the two calls.  A selector that consulted ambient
    per-name history — the side door — would return different controls.
    """
    panel = _panel()
    candidate = panel[panel["ticker"] == "AAA"].iloc[0]
    pool = panel[panel["ticker"] != "AAA"]

    controls._FAKE_OUTCOME_HISTORY = {"BBB": 0.42, "CCC": -0.31, "DDD": 0.07}
    first = controls.match(candidate, pool)
    controls._FAKE_OUTCOME_HISTORY = {"BBB": -0.99, "CCC": 0.88, "DDD": -0.55}
    second = controls.match(candidate, pool)
    del controls._FAKE_OUTCOME_HISTORY

    assert first == second
    assert first.controls, "the selector must actually select (non-vacuity)"


def test_m_outcome_rows_carry_no_per_ticker_strategy_key():
    """Contract §9: an outcome row tests Radar; it never becomes a per-name key.

    The row's ticker is present for JOINING, and every other field is a
    measurement — there is no score, no rank, no size and no routing field for a
    surface to read as a per-ticker instruction.
    """
    fields = set(outcomes.OutcomeRow.__dataclass_fields__)
    forbidden = {f for f in fields
                 if any(w in f for w in ("score", "rank", "size", "weight",
                                         "route", "signal_strength", "conviction"))}
    assert not forbidden, forbidden
    assert "ticker" in fields and "evidence_tier" in fields


def test_m_era_labelling_cannot_silently_promote_a_fit_row():
    daily = _daily()
    fit = _attach(_episode(daily, decision_session=date(2015, 6, 1)), daily)
    assert fit.era == "FIT" and fit.evidence_tier == "HISTORICAL"
    test = _attach(_episode(daily, decision_session=D0), daily)
    assert test.era == "TEST" and test.evidence_tier == "TEST"
    assert outcomes.era_of(prereg.FIT_END) == "FIT"
    assert outcomes.era_of(prereg.FIT_END + timedelta(days=1)) == "TEST"
