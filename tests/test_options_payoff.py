"""tests/test_options_payoff.py — deterministic payoff/scenario/greeks-drift engine.

Data law: synthetic only. Every chain frame here is built in-memory with pandas
carrying EXACTLY the engine.thetadata_store.chain() columns. Never reads data/,
never calls chain() against a real store, never writes into data/ (sparse
worktrees omit data/; its absence is a profile artifact, never evidence).
"""
from __future__ import annotations

import ast
import dataclasses
import math

import numpy as np
import pandas as pd
import pytest

import engine.options_payoff as op
from engine.intraday_greeks import bs_price

# ── shared fixtures ──────────────────────────────────────────────────────────────────
CHAIN_COLUMNS = [
    "root", "expiration", "strike", "right", "date",
    "open", "high", "low", "close", "volume", "count", "bid_eod", "ask_eod",
    "open_interest",
    "implied_vol", "delta", "theta", "vega", "rho",
    "iv_error",
]


def _chain_row(**overrides) -> dict:
    base = dict(
        root="TEST", expiration="2026-12-18", strike=100.0, right="C", date="2026-09-01",
        open=5.0, high=5.5, low=4.5, close=5.0, volume=10.0, count=5,
        bid_eod=4.9, ask_eod=5.1, open_interest=50.0,
        implied_vol=0.2, delta=0.5, theta=-0.01, vega=0.1, rho=0.05, iv_error=0.0,
    )
    base.update(overrides)
    return base


def _chain_frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=CHAIN_COLUMNS)


def _leg(right, strike, expiration, qty, *, entry=None, multiplier=100.0, iv=0.2) -> op.Leg:
    return op.Leg(
        right=right, strike=strike, expiration=expiration, qty=qty,
        entry_price=entry, multiplier=multiplier, iv=iv,
    )


# ── 1 ────────────────────────────────────────────────────────────────────────────────
def test_long_call_expiry_payoff_matches_intrinsic():
    K = 100.0
    premium = 5.0
    qty = 1
    leg = _leg("C", K, "2026-12-18", qty, entry=premium)
    structure = op.structure_from_legs([leg], root="TEST", asof_date="2026-09-01")

    spots = [80.0, 100.0, 110.0, 130.0]
    curve = op.expiry_payoff(structure, spots)

    expected = tuple((max(S - K, 0.0) - premium) * 100.0 * qty for S in spots)
    assert curve.pnl == pytest.approx(expected)


# ── 2 ────────────────────────────────────────────────────────────────────────────────
def test_put_call_parity_of_a_synthetic_forward():
    S, K, T, sigma, r, q = 100.0, 100.0, 0.5, 0.2, op.DEFAULT_R, op.DEFAULT_Q
    C = float(bs_price(S, K, T, sigma, True, r, q))
    P = float(bs_price(S, K, T, sigma, False, r, q))

    lhs = C - P
    rhs = S * math.exp(-q * T) - K * math.exp(-r * T)
    assert lhs == pytest.approx(rhs, abs=1e-9)

    # Expiration ~6 months out from the as-of date used below (2026-09-01 -> ~2027-03-03).
    expiry = "2027-03-03"
    legs = [
        _leg("C", K, expiry, 1, entry=C),
        _leg("P", K, expiry, -1, entry=P),
    ]
    structure = op.structure_from_legs(legs, root="TEST", asof_date="2026-09-01")
    # $1 steps so each diff is directly the per-$1-of-spot slope (== multiplier == 100),
    # per the acceptance line "the resulting expiry_payoff is linear in S with slope 100".
    spots = [98.0, 99.0, 100.0, 101.0, 102.0]
    curve = op.expiry_payoff(structure, spots)

    diffs = [curve.pnl[i + 1] - curve.pnl[i] for i in range(len(spots) - 1)]
    for d in diffs:
        assert d == pytest.approx(100.0, abs=1e-6)


# ── 3 ────────────────────────────────────────────────────────────────────────────────
def test_vertical_spread_max_loss_and_gain_are_bounded_floats():
    legs = [
        _leg("C", 100.0, "2026-12-18", 1, entry=4.0),
        _leg("C", 110.0, "2026-12-18", -1, entry=1.0),
    ]
    structure = op.structure_from_legs(legs, root="TEST", asof_date="2026-09-01")
    summary = op.structure_summary(structure, base_spot=100.0, evaluation_date="2026-09-01")

    assert summary.max_gain == pytest.approx(700.0)
    assert summary.max_loss == pytest.approx(-300.0)
    assert isinstance(summary.max_gain, float)
    assert isinstance(summary.max_loss, float)
    assert summary.breakevens == pytest.approx((103.0,))


# ── 4 ────────────────────────────────────────────────────────────────────────────────
def test_naked_short_call_max_loss_is_the_unbounded_marker():
    leg = _leg("C", 100.0, "2026-12-18", -1, entry=5.0)
    structure = op.structure_from_legs([leg], root="TEST", asof_date="2026-09-01")
    summary = op.structure_summary(structure, base_spot=100.0, evaluation_date="2026-09-01")

    assert summary.max_loss is op.UNBOUNDED
    assert isinstance(summary.max_loss, str)
    assert not isinstance(summary.max_loss, float)


# ── 5 ────────────────────────────────────────────────────────────────────────────────
def test_scenario_grid_is_monotonic_in_spot_for_a_long_call():
    leg = _leg("C", 100.0, "2026-12-18", 1, entry=5.0)
    structure = op.structure_from_legs([leg], root="TEST", asof_date="2026-09-01")

    grid = op.scenario_grid(
        structure,
        base_spot=100.0,
        spot_shocks=[-0.1, -0.05, 0.0, 0.05, 0.1],
        vol_shocks=[-0.05, 0.0, 0.05],
        days_forward=5,
        evaluation_date="2026-09-01",
    )

    for row in grid.pnl:
        for a, b in zip(row, row[1:]):
            assert b >= a - 1e-9


# ── 6 ────────────────────────────────────────────────────────────────────────────────
def test_greeks_drift_net_delta_matches_finite_difference():
    # Chosen so a +/-0.5% central spot bump on the shared pricer meets rtol=1e-4:
    # 1y-out vertical, 20% vol, K=95/105 around a 100 base spot.
    legs = [
        _leg("C", 95.0, "2027-09-01", 1, entry=8.0),
        _leg("C", 105.0, "2027-09-01", -1, entry=3.0),
    ]
    structure = op.structure_from_legs(legs, root="TEST", asof_date="2026-09-01")
    evaluation_date = "2026-09-01"
    base_spot = 100.0

    drift = op.greeks_drift(
        structure, base_spot=base_spot, days_forward=[0], evaluation_date=evaluation_date
    )
    net_delta = drift.points[0].net.delta
    assert net_delta is not None

    def structure_value(S: float) -> float:
        eval_d = op._parse_date(evaluation_date)
        total = 0.0
        for leg in legs:
            exp_d = op._parse_date(leg.expiration)
            T = (exp_d - eval_d).days / 365.0
            total += leg.qty * leg.multiplier * float(
                bs_price(S, leg.strike, T, leg.iv, leg.right == "C", op.DEFAULT_R, op.DEFAULT_Q)
            )
        return total

    h = 0.005 * base_spot
    fd_delta = (structure_value(base_spot + h) - structure_value(base_spot - h)) / (2 * h)

    assert net_delta == pytest.approx(fd_delta, rel=1e-4)


# ── 7 ────────────────────────────────────────────────────────────────────────────────
def test_greeks_come_from_engine_greeks_not_a_local_copy(monkeypatch):
    legs = [
        _leg("C", 100.0, "2026-12-18", 1, entry=5.0),
        _leg("P", 100.0, "2026-12-18", 1, entry=4.0),
    ]
    structure = op.structure_from_legs(legs, root="TEST", asof_date="2026-09-01")

    calls = []
    real_bs_greeks = op.bs_greeks

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return real_bs_greeks(*args, **kwargs)

    monkeypatch.setattr(op, "bs_greeks", spy)

    op.greeks_drift(structure, base_spot=100.0, days_forward=[0, 5], evaluation_date="2026-09-01")

    assert len(calls) >= len(legs)

    # AST scan: the module defines no closed-form Black-Scholes primitive of its own.
    source = open(op.__file__.replace(".pyc", ".py")).read()
    tree = ast.parse(source)
    forbidden_names = {"ncdf", "npdf", "_d1d2", "d1", "d2", "_norm_cdf"}
    defined_names = {
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert not (defined_names & forbidden_names)

    uses_erf = any(
        (isinstance(node, ast.Attribute) and node.attr == "erf")
        or (isinstance(node, ast.Name) and node.id == "erf")
        for node in ast.walk(tree)
    )
    assert not uses_erf


# ── 8 ────────────────────────────────────────────────────────────────────────────────
def test_missing_iv_abstains_only_the_vol_dependent_outputs():
    legs = [
        _leg("C", 100.0, "2026-12-18", 1, entry=4.0, iv=0.2),
        _leg("C", 110.0, "2026-12-18", -1, entry=1.0, iv=None),
    ]
    structure = op.structure_from_legs(legs, root="TEST", asof_date="2026-09-01")

    all_leg_codes = {s.code for leg in structure.legs for s in leg.states}
    assert "LEG_IV_MISSING" in all_leg_codes

    grid = op.scenario_grid(
        structure, base_spot=100.0, spot_shocks=[0.0], vol_shocks=[0.0],
        days_forward=0, evaluation_date="2026-09-01",
    )
    assert grid.pnl[0][0] is None
    assert "LEG_IV_MISSING" in grid.cell_states[0][0]

    drift = op.greeks_drift(
        structure, base_spot=100.0, days_forward=[0], evaluation_date="2026-09-01"
    )
    missing_leg_greeks = drift.points[0].per_leg[1]
    assert missing_leg_greeks.delta is None
    assert missing_leg_greeks.gamma is None
    assert missing_leg_greeks.vega is None
    assert "LEG_IV_MISSING" in missing_leg_greeks.states

    # The expiry payoff needs no vol, no rate, no time — it is still fully populated.
    curve = op.expiry_payoff(structure, [90.0, 100.0, 110.0, 120.0])
    assert all(v is not None and not math.isnan(v) for v in curve.pnl)


# ── 9 ────────────────────────────────────────────────────────────────────────────────
def test_missing_multiplier_keeps_per_unit_payoff_and_nulls_the_dollars():
    legs = [
        _leg("C", 100.0, "2026-12-18", 1, entry=4.0, multiplier=None),
        _leg("C", 110.0, "2026-12-18", -1, entry=1.0, multiplier=100.0),
    ]
    structure = op.structure_from_legs(legs, root="TEST", asof_date="2026-09-01")
    curve = op.expiry_payoff(structure, [90.0, 100.0, 110.0, 120.0])

    all_codes = {s.code for s in curve.states}
    assert "MULTIPLIER_UNKNOWN" in all_codes
    assert curve.cost is None
    assert all(v is None for v in curve.pnl)
    assert all(isinstance(v, float) and not math.isnan(v) for v in curve.pnl_per_unit)


# ── 10 ───────────────────────────────────────────────────────────────────────────────
def test_typed_nulls_are_printed_with_receipts():
    # crossed quote
    df = _chain_frame([_chain_row(bid_eod=5.5, ask_eod=5.1)])
    s = op.structure_from_chain(
        df, root="TEST", asof_date="2026-09-01",
        leg_specs=[{"right": "C", "strike": 100.0, "expiration": "2026-12-18", "qty": 1}],
        multipliers=[100.0],
    )
    codes = {st.code for st in s.legs[0].states}
    assert "QUOTE_CROSSED" in codes
    for st in s.legs[0].states:
        assert st.receipt

    # zero bid
    df2 = _chain_frame([_chain_row(bid_eod=0.0, ask_eod=5.1)])
    s2 = op.structure_from_chain(
        df2, root="TEST", asof_date="2026-09-01",
        leg_specs=[{"right": "C", "strike": 100.0, "expiration": "2026-12-18", "qty": 1}],
        multipliers=[100.0],
    )
    assert any(st.code == "ZERO_BID_LIQUIDITY" for st in s2.legs[0].states)

    # NaN OI -> liquidity unknown, never OK
    df3 = _chain_frame([_chain_row(open_interest=np.nan)])
    s3 = op.structure_from_chain(
        df3, root="TEST", asof_date="2026-09-01",
        leg_specs=[{"right": "C", "strike": 100.0, "expiration": "2026-12-18", "qty": 1}],
        multipliers=[100.0],
    )
    summary3 = op.structure_summary(s3, base_spot=100.0, evaluation_date="2026-09-01")
    assert summary3.liquidity == "LIQUIDITY_UNKNOWN"

    # empty frame -> CHAIN_EMPTY, never raises
    df4 = _chain_frame([])
    s4 = op.structure_from_chain(
        df4, root="TEST", asof_date="2026-09-01",
        leg_specs=[{"right": "C", "strike": 100.0, "expiration": "2026-12-18", "qty": 1}],
        multipliers=[100.0],
    )
    assert any(st.code == "CHAIN_EMPTY" for st in s4.states)

    # stale asof (5 days old)
    df5 = _chain_frame([_chain_row(date="2026-08-27")])
    s5 = op.structure_from_chain(
        df5, root="TEST", asof_date="2026-08-27",
        leg_specs=[{"right": "C", "strike": 100.0, "expiration": "2026-12-18", "qty": 1}],
        multipliers=[100.0],
    )
    summary5 = op.structure_summary(s5, base_spot=100.0, evaluation_date="2026-09-01")
    assert any(st.code == "CHAIN_STALE" for st in summary5.states)

    # past expiry
    df6 = _chain_frame([_chain_row(expiration="2026-08-01")])
    s6 = op.structure_from_chain(
        df6, root="TEST", asof_date="2026-09-01",
        leg_specs=[{"right": "C", "strike": 100.0, "expiration": "2026-08-01", "qty": 1}],
        multipliers=[100.0],
    )
    summary6 = op.structure_summary(s6, base_spot=100.0, evaluation_date="2026-09-01")
    assert any(st.code == "EXPIRY_PASSED" for st in summary6.states)

    # every NullState.receipt across everything above is non-empty
    for structure in (s, s2, s3, s4, s5, s6):
        for st in structure.states:
            assert st.receipt
        for leg in structure.legs:
            for st in leg.states:
                assert st.receipt

    for summary in (summary3, summary5, summary6):
        if not summary.prerequisites_met:
            assert len(summary.states) > 0


# ── 11 ───────────────────────────────────────────────────────────────────────────────
def test_assumption_block_and_evidence_recipe_are_versioned_and_input_bound():
    leg = _leg("C", 100.0, "2026-12-18", 1, entry=5.0)
    structure = op.structure_from_legs([leg], root="TEST", asof_date="2026-09-01")

    ab = op.assumption_block(structure, r=op.DEFAULT_R, q=op.DEFAULT_Q)
    for f in dataclasses.fields(ab):
        value = getattr(ab, f.name)
        assert value not in (None, "", ())

    recipe1 = op.evidence_recipe(structure, r=op.DEFAULT_R, q=op.DEFAULT_Q)
    recipe2 = op.evidence_recipe(structure, r=op.DEFAULT_R, q=op.DEFAULT_Q)
    recipe3 = op.evidence_recipe(structure, r=0.05, q=op.DEFAULT_Q)

    assert recipe1["authority"]["entry_authority"] == "none"
    assert recipe1["inputs_hash"] == recipe2["inputs_hash"]
    assert recipe1["inputs_hash"] != recipe3["inputs_hash"]


# ── 12 ───────────────────────────────────────────────────────────────────────────────
def test_structure_from_chain_on_a_synthetic_frame():
    df = _chain_frame([_chain_row()])
    assert list(df.columns) == CHAIN_COLUMNS

    structure = op.structure_from_chain(
        df, root="TEST", asof_date="2026-09-01",
        leg_specs=[
            {"right": "C", "strike": 100.0, "expiration": "2026-12-18", "qty": 1},
            {"right": "P", "strike": 95.0, "expiration": "2026-12-18", "qty": 1},
        ],
        multipliers=[100.0, 100.0],
    )
    # second spec absent from the frame -> LEG_NOT_IN_CHAIN, no raise
    assert any(st.code == "LEG_NOT_IN_CHAIN" for st in structure.legs[1].states)

    df_other_root = _chain_frame([_chain_row(root="OTHER")])
    structure2 = op.structure_from_chain(
        df_other_root, root="TEST", asof_date="2026-09-01",
        leg_specs=[{"right": "C", "strike": 100.0, "expiration": "2026-12-18", "qty": 1}],
        multipliers=[100.0],
    )
    assert any(st.code == "IDENTITY_MISMATCH" for st in structure2.legs[0].states)


# ── 13 ───────────────────────────────────────────────────────────────────────────────
def test_no_entry_or_sizing_fields_exist():
    FORBIDDEN_TOKENS = {
        "rank", "score", "rating", "conviction", "recommend", "signal", "size",
        "sizing", "allocation", "weight", "target", "stop", "action", "buy",
        "sell", "best", "top", "preferred",
    }
    WHITELIST = {"entry_price"}
    # Spec §7 pins these four literal keys, verbatim, inside evidence_recipe()'s
    # "authority" block, each valued the string "none" — the mechanism by which this
    # module DISCLOSES zero entry/ranking/sizing authority (spec §10 ceiling
    # statement). "ranking"/"sizing" collide with the FORBIDDEN_TOKENS "rank"/"sizing"
    # under a token-set scan; excluding exactly these disclosure keys (never their
    # sibling recipe fields, and never any dataclass field) keeps the scan strict
    # everywhere a real entry/rank/size DATA field could hide while accommodating the
    # spec's own required disclosure vocabulary. See PR body / DEVIATIONS: this is a
    # narrow, documented spec self-consistency call, not a silent redesign.
    AUTHORITY_DISCLOSURE_KEYS = {
        "entry_authority", "ranking_authority", "sizing_authority", "llm_origination",
    }

    names: set[str] = set()
    for _, obj in vars(op).items():
        if isinstance(obj, type) and dataclasses.is_dataclass(obj):
            for f in dataclasses.fields(obj):
                names.add(f.name.lower())

    def collect_keys(value, out):
        if isinstance(value, dict):
            for k, v in value.items():
                out.add(str(k).lower())
                collect_keys(v, out)
        elif isinstance(value, (list, tuple)):
            for v in value:
                collect_keys(v, out)

    leg = _leg("C", 100.0, "2026-12-18", 1, entry=5.0)
    structure = op.structure_from_legs([leg], root="TEST", asof_date="2026-09-01")
    recipe = op.evidence_recipe(structure, r=op.DEFAULT_R, q=op.DEFAULT_Q)
    collect_keys(recipe, names)

    names -= WHITELIST
    names -= AUTHORITY_DISCLOSURE_KEYS
    hits = set()
    for name in names:
        tokens = set(name.split("_")) | {name}
        hits |= (tokens & FORBIDDEN_TOKENS)
    assert not hits, f"forbidden token(s) found in field/key names: {hits}"

    # The four disclosure keys must still be present and must still literally say "none".
    leg_for_disclosure = _leg("C", 100.0, "2026-12-18", 1, entry=5.0)
    struct_for_disclosure = op.structure_from_legs(
        [leg_for_disclosure], root="TEST", asof_date="2026-09-01"
    )
    disclosure_recipe = op.evidence_recipe(struct_for_disclosure, r=op.DEFAULT_R, q=op.DEFAULT_Q)
    for key in AUTHORITY_DISCLOSURE_KEYS:
        assert disclosure_recipe["authority"][key] == "none"

    assert not any(
        n.startswith(("rank_", "score_", "recommend")) for n in dir(op)
    )


# ── 14 ───────────────────────────────────────────────────────────────────────────────
def test_shape_classification_is_descriptive_only():
    def leg(right, strike, expiration, qty):
        return _leg(right, strike, expiration, qty)

    known_cases = [
        [leg("C", 100.0, "2026-12-18", 1)],
        [leg("C", 100.0, "2026-12-18", 1), leg("C", 110.0, "2026-12-18", -1)],
        [leg("C", 100.0, "2026-12-18", 1), leg("C", 100.0, "2027-01-15", -1)],
        [leg("C", 100.0, "2026-12-18", 1), leg("C", 110.0, "2027-01-15", -1)],
        [leg("C", 100.0, "2026-12-18", 1), leg("P", 100.0, "2026-12-18", 1)],
        [leg("C", 105.0, "2026-12-18", 1), leg("P", 95.0, "2026-12-18", 1)],
        [leg("P", 95.0, "2026-12-18", 1), leg("C", 105.0, "2026-12-18", -1)],
        [
            leg("C", 95.0, "2026-12-18", 1),
            leg("C", 100.0, "2026-12-18", -2),
            leg("C", 105.0, "2026-12-18", 1),
        ],
    ]
    for legs in known_cases:
        shape = op.classify_shape(legs)
        assert shape in op.SHAPES

    # unknown geometry -> "custom", never a raise
    unknown = [
        leg("C", 95.0, "2026-12-18", 1),
        leg("C", 100.0, "2026-12-18", 1),
        leg("C", 105.0, "2026-12-18", 1),
    ]
    assert op.classify_shape(unknown) == "custom"
    assert op.classify_shape([]) == "custom"
