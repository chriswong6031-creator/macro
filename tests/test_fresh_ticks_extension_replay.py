"""W5.2 FRESH_TICKS-extension replay — reproduction gate + counterfactual-eligibility unit tests.

Three things are pinned here, and they fail for different reasons on purpose.

1. **THE REPRODUCTION GATE.** The whole packet stands on S-B's measured cross-age table
   (``superintelligence_standins_results.json`` → ``S_B_confirmation.by_cross_age_ticks``:
   ticks 0/1/2 → 20.8% / 10.0% / 11.5% loser on n=53/30/26). If that table cannot be rebuilt
   from the committed stores, every number in the replay is being read against an anchor that
   has moved, and the honest response is to re-pin the frame at a fresh ``REPRO_ASOF`` and
   re-read — never to loosen the comparison. Store-dependent, so it SKIPS with a reason when
   the caches are absent (CI runners install minimal deps and carry no ``data/``); the PR body
   carries the local-run receipt in that case.

2. **THE COUNTERFACTUAL-ELIGIBILITY HELPER.** ``classify_states`` is where the whole
   construction lives: it decides which sessions the freshness extension would ADD, and a
   silent defect there would produce a confident, wrong verdict rather than an error. The
   three scenarios below are the three cases the construction has to get right — a cross that
   ages cleanly through the boundary, one whose 3D RSI-MACD falls back below its signal at
   tick 3 (``macd_bear`` — the "cross no longer intact" case), and one that survives to tick 3
   but goes overbought at tick 4 (``stoch_ob``). The second and third MUST NOT contribute a
   ticks-3/4 row: the counterfactual extends the freshness clock and nothing else, so a state
   that fails any veto leg is not an admission the gate was hiding.

3. **THE RECONSTRUCTION FIDELITY.** The leg streams the diagnostics read are a replication of
   ``tier_stream``'s leg composition. Section 3 pins that they reproduce the engine's own
   ``not_topped`` on every day and its ``ticks`` on every admitted day for a sample of real
   names — the check that makes the leg-mix table evidence rather than a parallel opinion.

Run: python3 -m pytest tests/test_fresh_ticks_extension_replay.py -q
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

AUDIT = ROOT / "research" / "prophet_us_audit"
REPLAY_PY = AUDIT / "fresh_ticks_extension_replay.py"
SB_FROZEN = AUDIT / "superintelligence_standins_results.json"
RETRO = ROOT / "data" / "us_board_ledger" / "retro_grades.parquet"
CLOSES = [ROOT / "data" / g / "_closes_cache.parquet"
          for g in ("breadth", "midcap_breadth", "smallcap_breadth")]

_stores_missing = [str(p.relative_to(ROOT)) for p in [RETRO, SB_FROZEN, *CLOSES]
                   if not p.exists()]
needs_stores = pytest.mark.skipif(
    bool(_stores_missing),
    reason=f"store-dependent; absent here: {', '.join(_stores_missing)}")


def _load_replay():
    """Import the research instrument by path (it lives outside any package)."""
    spec = importlib.util.spec_from_file_location("ftx_replay", REPLAY_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # note: chdir(REPO) at import, the standins idiom
    return mod


R = _load_replay()


# ─────────────────────────────────────────────────────────────────────────────
# 1. the reproduction gate
# ─────────────────────────────────────────────────────────────────────────────
#: What the cross-age table rebuilds to under the ABSOLUTE SESSION ANCHOR (era
#: ``abs-session-2026-08-06``, ruling
#: research/SESSION_ANCHOR_ABSOLUTE_CALENDAR_ADJUDICATION_BY_FABLE.md).
#:
#: S-B's frozen table was measured when the 2D/3D buckets were phased to each series' FIRST
#: timestamp. The anchor repair re-phases them, so a cross that was "0 ticks old" on the old
#: grid can be 1 tick old on the absolute one — and the table redistributes ACROSS tick
#: buckets while the population barely moves (109 -> 107 events). Measured:
#:
#:   ticks | frozen n -> rebuilt n | frozen loser% -> rebuilt loser%
#:      0  |    53    ->    43     |    20.8       ->   16.3
#:      1  |    30    ->    39     |    10.0       ->    7.7
#:      2  |    26    ->    25     |    11.5       ->    8.0
#:
#: The packet's DIRECTIONAL finding survives (loser rate still falls from tick 0 to tick 1
#: and stays low at 2; median excess still rises with cross age), but every CELL moved.
#: Per adjudication R5, a pre-era measurement is cited as pre-era and QUEUED for
#: re-measurement — never silently re-baked — so the frozen JSON is left untouched and this
#: gate now pins the post-era reproduction instead.
SB_POST_ERA = {
    0: {"n": 43, "loser_rate_pct": 16.3, "median_excess_dm_pp": 0.26},
    1: {"n": 39, "loser_rate_pct": 7.7, "median_excess_dm_pp": 1.5},
    2: {"n": 25, "loser_rate_pct": 8.0, "median_excess_dm_pp": 2.66},
}


@needs_stores
def test_reproduces_sb_cross_age_table_under_the_current_anchor():
    """The reproduction gate, re-pinned at the anchor era boundary.

    The gate's PURPOSE is unchanged and undiluted: the cross-age table must rebuild
    cell-for-cell from the committed stores, so that any further store drift or engine change
    reds here rather than silently re-anchoring every number in the replay. What changed is
    WHICH cells: the absolute session anchor moved them once, deliberately and measurably (see
    SB_POST_ERA), and that one movement is recorded rather than absorbed.

    NOT re-baked: ``superintelligence_standins_results.json`` still holds the PRE-era table
    and is asserted below to be untouched. The W5.2 packet's verdicts were read against those
    numbers and are QUEUED for a re-read at a fresh ``REPRO_ASOF`` (adjudication R5) — that
    re-read is a research decision, not something this suite may make by editing a frozen
    file. Do NOT widen this comparison to make a future drift pass.
    """
    gate = R.reproduce_sb(R.load_panel())
    rebuilt = {r["ticks"]: r for r in gate["rebuilt"]}
    for ticks, want in SB_POST_ERA.items():
        for field, value in want.items():
            assert rebuilt[ticks][field] == value, (
                f"cross-age cell (ticks={ticks}, {field}) is {rebuilt[ticks][field]}, "
                f"expected {value}. The stores or the engine moved AGAIN, on top of the "
                f"abs-session-2026-08-06 re-phase. Re-pin the frame at a fresh REPRO_ASOF and "
                f"re-read every verdict — do not widen this comparison.")
    # the FROZEN pre-era table must still be on disk unmodified: the era boundary is only
    # meaningful while both sides of it are readable.
    frozen = json.loads(SB_FROZEN.read_text())["S_B_confirmation"]["by_cross_age_ticks"]
    pre = {r["ticks"]: r for r in frozen}
    assert (pre[0]["n"], pre[1]["n"], pre[2]["n"]) == (53, 30, 26), (
        "the PRE-era frozen table was rewritten — a pre-era measurement is cited as pre-era "
        "and re-measured under a new REPRO_ASOF, never edited in place (R5)")
    assert (pre[0]["loser_rate_pct"], pre[1]["loser_rate_pct"],
            pre[2]["loser_rate_pct"]) == (20.8, 10.0, 11.5)


@needs_stores
def test_frozen_results_carry_a_passing_gate():
    """The committed results JSON must itself record a PASSing gate — a frozen artifact
    whose own reproduction check failed is not evidence."""
    out = AUDIT / "fresh_ticks_extension_replay_results.json"
    if not out.exists():
        pytest.skip("replay results not generated in this checkout")
    res = json.load(open(out))
    assert res["reproduction_gate"]["status"].startswith("PASS")
    assert res["reproduction_gate"]["cell_diffs"] == []
    checks = res["construction_checks"]
    assert checks["admitted_states_not_on_board_today"] == 0
    fid = checks["reconstruction_fidelity"]
    assert (fid["not_topped_mismatch"], fid["t1_ticks_mismatch"],
            fid["t2_ticks_mismatch"]) == (0, 0, 0)
    # every leg must fire at least once — a 0 here is the numpy `x is True` dead-leg trap
    dead = [k for k, v in checks["leg_fire_counts"].items() if v["days"] == 0]
    assert dead == [], f"dead admission/veto legs (never fired): {dead}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. the counterfactual-eligibility helper, on synthetic tick series
# ─────────────────────────────────────────────────────────────────────────────
LEG_COLS = ("stoch_ob", "stoch_bear", "macd_bear", "rsi_ok", "long_bias",
            "recent3", "confirm3", "recent2", "confirm2", "above200", "imm2",
            "t1_ticks", "t2_ticks")


def _synthetic(tick_seq, elig_ext, *, veto_leg=None, tier="T1"):
    """Build (gate, ext, legs) frames for one synthetic name's tick walk.

    ``tick_seq``   per-day age of the operative 3D cross (two daily bars per tick here).
    ``elig_ext``   per-day eligibility under the EXTENDED clock (the veto's verdict).
    ``veto_leg``   which leg is set True on the days ``elig_ext`` is False.
    The gate stream is derived the way the engine derives it: eligible iff the extended
    stream is eligible AND the age is inside the shipped FRESH_TICKS window.
    """
    idx = pd.bdate_range("2025-01-06", periods=len(tick_seq))
    ticks = np.array(tick_seq, dtype=float)
    ee = np.array(elig_ext, dtype=bool)
    ge = ee & (ticks <= R.GATE_TICKS)

    def stream(elig):
        return pd.DataFrame({
            "tier": np.where(elig, tier, None),
            "weight": np.where(elig, 0.9, 0.0),
            "ticks": np.where(elig, ticks, np.nan),
            "not_topped": ee, "eligible": elig,
            "sub": np.where(elig, "shallow", None),
        }, index=idx)

    legs = pd.DataFrame({c: False for c in LEG_COLS}, index=idx)
    for c in ("rsi_ok", "long_bias", "recent3", "confirm3", "recent2", "confirm2", "above200"):
        legs[c] = True
    legs["t1_ticks"] = ticks
    legs["t2_ticks"] = 99.0                       # T1 is the operative clock in all scenarios
    if veto_leg is not None:
        legs[veto_leg] = ~ee
    return stream(ge), stream(ee), legs


AGE_WALK = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6]
ADMITTING = {"admitted", "ext_marginal", "ext_relabel", "decay_marginal", "decay_relabel"}


def _assert_no_vetoed_session_admitted(out, ext):
    """The invariant read off the FINAL output, independent of any internal ordering: a
    session the extended stream refused can never land in a cohort the replay counts. The
    classifier reaches this two ways (the eligibility mask on tier/ticks, and the blocked
    overwrite), so asserting it on the output — not on one of the paths — is what keeps the
    check alive if either path is refactored away."""
    vetoed = ~ext["eligible"].astype(bool)
    assert not set(out.loc[vetoed, "cohort"].dropna()) & ADMITTING, (
        "a veto-blocked session was counted as an admission the freshness gate was hiding")


def test_cross_that_ages_cleanly_classifies_across_the_boundary():
    """Ticks 0-2 stay 'admitted'; 3-4 become the extension cohort; 5-6 are decay context."""
    gate, ext, legs = _synthetic(AGE_WALK, [True] * len(AGE_WALK))
    out = R.classify_states(gate, ext, legs)
    by_tick = out.groupby("ticks")["cohort"].agg(lambda s: sorted(set(s)))
    assert by_tick[0] == by_tick[1] == by_tick[2] == ["admitted"]
    assert by_tick[3] == by_tick[4] == ["ext_marginal"]
    assert by_tick[5] == by_tick[6] == ["decay_marginal"]
    # one uninterrupted cross → one episode, so tick 0 and tick 4 are pairable
    assert out["episode"].dropna().nunique() == 1
    # and the extension adds exactly the sessions the clock excluded, nothing else
    assert int((out["cohort"] == "ext_marginal").sum()) == 4


def test_cross_that_invalidates_at_tick_3_contributes_no_extension_row():
    """The 3D RSI-MACD falls back below its signal at tick 3 — the cross is no longer intact,
    so the freshness extension must NOT claim it. It is blocked, and attributed to macd_bear."""
    elig = [t <= 2 for t in AGE_WALK]
    gate, ext, legs = _synthetic(AGE_WALK, elig, veto_leg="macd_bear")
    out = R.classify_states(gate, ext, legs)
    assert "ext_marginal" not in set(out["cohort"].dropna())
    blocked = out[out["cohort"] == "blocked"]
    assert sorted(set(blocked["clock_ticks"])) == [3.0, 4.0, 5.0, 6.0]
    assert set(blocked["block_leg"]) == {"macd_bear"}
    assert int((out["cohort"] == "admitted").sum()) == 6      # ticks 0/1/2, two bars each
    _assert_no_vetoed_session_admitted(out, ext)


def test_cross_vetoed_at_tick_4_yields_tick_3_only():
    """Survives to tick 3 (a genuine extension row) then goes overbought at tick 4 — the
    tick-4 sessions are a veto story, not a freshness story, and must not be counted."""
    elig = [t <= 3 for t in AGE_WALK]
    gate, ext, legs = _synthetic(AGE_WALK, elig, veto_leg="stoch_ob")
    out = R.classify_states(gate, ext, legs)
    ext_rows = out[out["cohort"] == "ext_marginal"]
    assert sorted(set(ext_rows["ticks"])) == [3.0]
    blocked = out[out["cohort"] == "blocked"]
    assert sorted(set(blocked["clock_ticks"])) == [4.0, 5.0, 6.0]
    assert set(blocked["block_leg"]) == {"stoch_ob"}
    _assert_no_vetoed_session_admitted(out, ext)


def test_admitted_cohort_is_always_already_on_the_board():
    """The construction's load-bearing invariant: for ages inside FRESH_TICKS the extended
    stream and the shipped gate agree, so an 'admitted' row is never something the
    counterfactual invented. A violation means the knob moved more than the clock."""
    for elig in ([True] * len(AGE_WALK), [t <= 3 for t in AGE_WALK]):
        gate, ext, legs = _synthetic(AGE_WALK, elig, veto_leg="stoch_bear")
        out = R.classify_states(gate, ext, legs)
        assert bool(out.loc[out["cohort"] == "admitted", "on_board_now"].all())
        assert not bool(out.loc[out["cohort"] == "ext_marginal", "on_board_now"].any())


def test_new_cross_resets_the_episode():
    """A tick age that DROPS is a fresh cross, not the continuation of an aged one — pairing
    tick 4 of one cross with tick 0 of the next would fabricate the paired-entry result."""
    walk = [0, 1, 2, 3, 4, 0, 1, 2]
    gate, ext, legs = _synthetic(walk, [True] * len(walk))
    out = R.classify_states(gate, ext, legs)
    assert out["episode"].dropna().nunique() == 2


# ─────────────────────────────────────────────────────────────────────────────
# 3. reconstruction fidelity against the engine, on real series
# ─────────────────────────────────────────────────────────────────────────────
@needs_stores
def test_leg_reconstruction_matches_tier_stream_on_real_names():
    """The diagnostics' leg streams must be the engine's own legs, not a parallel opinion."""
    from engine import confluence_tiers as ct
    px = R.load_panel()
    names = [t for t in px.columns if px[t].notna().sum() >= ct.MIN_HISTORY][:12]
    assert names, "panel carried no name with enough history"
    total = {"days": 0, "not_topped_mismatch": 0,
             "t1_ticks_mismatch": 0, "t2_ticks_mismatch": 0}
    for t in names:
        s = px[t].dropna()
        legs = R.leg_streams(s)
        assert legs is not None
        f = R.fidelity_check(legs, ct.tier_stream(s, fresh_ticks=R.GATE_TICKS),
                             ct.tier_stream(s, fresh_ticks=R.EXT_TICKS))
        for k in total:
            total[k] += f[k]
    assert total["days"] > 0
    assert total["not_topped_mismatch"] == 0
    assert total["t1_ticks_mismatch"] == 0
    assert total["t2_ticks_mismatch"] == 0


@needs_stores
def test_extension_knob_only_widens_the_admitted_set():
    """tier_stream(fresh_ticks=EXT) must be a strict SUPERSET of the shipped gate's
    admissions — the counterfactual can add sessions, never remove one. If it ever removes
    one, the knob is not a pure clock extension and the whole comparison is void."""
    from engine import confluence_tiers as ct
    px = R.load_panel()
    names = [t for t in px.columns if px[t].notna().sum() >= ct.MIN_HISTORY][:12]
    for t in names:
        s = px[t].dropna()
        g = ct.tier_stream(s, fresh_ticks=R.GATE_TICKS)["eligible"].astype(bool)
        e = ct.tier_stream(s, fresh_ticks=R.EXT_TICKS)["eligible"].astype(bool)
        assert int((g & ~e).sum()) == 0, f"{t}: extension DROPPED an admitted session"
