"""Tests for engine/options_dislocation.py — the options information-dislocation layer.

The tests that matter here are not the happy-path ones. They pin the three properties that
make this layer honest, each written so it FAILS if the property is removed:

  * neutralisation actually strips implied-vol level (the whole method),
  * the gate cannot open below its power floor, and rejects a wrong-signed predictor
    however strong it is,
  * the reads stay categorical — no liftable fused pre-gate score (RO-2 / Signal Commons R3).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from engine import options_dislocation as D  # noqa: E402


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def _chain(underlying="XYZ", spot=100.0, asof="2026-06-21",
           iv_front=0.50, iv_mid=0.40, iv_back=0.30,
           call_oi=100, put_oi=100, volume=10):
    """A three-expiry chain spanning the front/mid/back buckets, with controllable
    per-side OI so the positioning tilt can be driven deliberately."""
    rows = []
    for exp, days, iv in (("2026-06-28", 7, iv_front),
                          ("2026-07-21", 30, iv_mid),
                          ("2026-09-21", 90, iv_back)):
        t = days / 365.0
        rows += [
            dict(underlying=underlying, expiry=exp, K=spot, T=t, is_call=True, iv=iv,
                 delta=0.50, gamma=0.01, oi=call_oi, volume=volume, spot=spot, asof=asof),
            dict(underlying=underlying, expiry=exp, K=spot, T=t, is_call=False, iv=iv,
                 delta=-0.50, gamma=0.01, oi=put_oi, volume=volume, spot=spot, asof=asof),
            dict(underlying=underlying, expiry=exp, K=spot * 0.95, T=t, is_call=False,
                 iv=iv + 0.05, delta=-0.25, gamma=0.01, oi=put_oi, volume=volume,
                 spot=spot, asof=asof),
        ]
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# primitives
# --------------------------------------------------------------------------- #
def test_term_slope_is_front_minus_back():
    m = D.compute_primitives(_chain(iv_mid=0.40, iv_back=0.30))
    assert m["iv30"] == pytest.approx(0.40, abs=1e-6)
    assert m["iv_back"] == pytest.approx(0.30, abs=1e-6)
    assert m["term_slope"] == pytest.approx(0.10, abs=1e-6)


def test_expected_move_scales_with_iv_and_sqrt_time():
    m = D.compute_primitives(_chain(iv_mid=0.40))
    # the engine rounds emitted floats to 6dp
    assert m["em30"] == pytest.approx(0.40 * np.sqrt(30.0 / 365.0), abs=1e-6)


def test_oi_tilt_signs_with_the_heavier_side():
    call_heavy = D.compute_primitives(_chain(call_oi=900, put_oi=100))
    put_heavy = D.compute_primitives(_chain(call_oi=100, put_oi=900))
    assert call_heavy["oi_tilt"] > 0 and put_heavy["oi_tilt"] < 0


def test_primitives_degrade_to_none_never_raise():
    assert D.compute_primitives(None) is None
    assert D.compute_primitives(pd.DataFrame()) is None
    # a chain with only expired rows has no usable tenor
    bad = _chain()
    bad["T"] = 0.0
    assert D.compute_primitives(bad) is None


def test_missing_leg_yields_null_not_a_fabricated_neutral():
    """A chain with no back-month must leave term_slope NULL — never 0.0, which a reader
    would misread as 'flat term structure' rather than 'not measured'."""
    c = _chain()
    c = c[c["expiry"] != "2026-09-21"]
    m = D.compute_primitives(c)
    assert m["iv30"] is not None
    assert m["term_slope"] is None


# --------------------------------------------------------------------------- #
# neutralisation — the core method
# --------------------------------------------------------------------------- #
def _xs_panel(n=60, seed=0):
    rng = np.random.default_rng(seed)
    iv = rng.uniform(0.15, 0.90, n)
    return pd.DataFrame({
        "date": ["2026-06-21"] * n,
        "underlying": [f"N{i}" for i in range(n)],
        "iv30": iv,
        "log_spot": rng.uniform(2.0, 6.0, n),
        # a feature that is a pure monotone re-labelling of IV level: information-free
        "fake": iv * 3.0 + 1.0,
        # a feature genuinely independent of IV level
        "real": rng.normal(0, 1, n),
    })


def test_neutralisation_annihilates_a_pure_iv_level_repackage():
    """The headline finding this engine exists to prevent: a feature that is only IV level
    wearing a hat must have ~no residual left after neutralisation."""
    P = D.neutralise(_xs_panel(), ["fake", "real"])
    assert np.nanstd(P["n_fake"]) < 1e-6, "a monotone function of iv30 must neutralise to zero"


def test_neutralisation_preserves_a_genuinely_independent_feature():
    P = D.neutralise(_xs_panel(), ["fake", "real"])
    assert np.nanstd(P["n_real"]) > 0.05, "an IV-independent feature must survive"


def test_neutralisation_refuses_a_too_thin_cross_section():
    """A residual computed from a handful of names is noise, not a neutralisation."""
    thin = _xs_panel(n=D._MIN_XS - 1)
    P = D.neutralise(thin, ["real"])
    assert P["n_real"].notna().sum() == 0


# --------------------------------------------------------------------------- #
# reads stay categorical — RO-2 / Signal Commons R3
# --------------------------------------------------------------------------- #
_FUSED_FAMILIES = ("directional_option_information", "volatility_disagreement",
                   "option_stock_confirmation", "dealer_positioning_fragility")


def test_fused_families_never_emit_a_liftable_number():
    """RO-2 forbids a fused pre-gate composite 'anywhere a reader can lift it'. Each
    multi-primitive family must therefore expose a STRING verdict plus its named parts —
    never a float a caller could rank on."""
    row = {"n_ivspread": 0.4, "n_d5_ivspread": 0.4, "n_skew": -0.4,
           "n_term_slope": -0.3, "n_d5_term_slope": 0.3,
           "strike_conc": 0.3, "expiry_conc": 0.3, "turnover": 2.0,
           "stock_state": "up", "n_skew_accel": -0.2, "event_em_gap": 0.1}
    r = D.reads(row)
    for fam in _FUSED_FAMILIES:
        assert isinstance(r[fam]["read"], str), f"{fam} must be categorical"
        assert not isinstance(r[fam].get("score"), (int, float)), f"{fam} must carry no score"
        assert r[fam]["parts"], f"{fam} must name its contributing primitives"


def test_single_primitive_measures_may_carry_a_number():
    """Only genuinely single-primitive measures are lawful as numbers — they are not fusions."""
    r = D.reads({"n_skew_accel": -0.2, "event_em_gap": 0.35})
    assert r["skew_acceleration"] == pytest.approx(-0.2)
    assert r["event_expected_move_gap"] == pytest.approx(0.35)


def test_reads_go_null_not_neutral_when_nothing_is_measurable():
    r = D.reads({})
    assert r["directional_option_information"]["read"] == "null"
    assert r["volatility_disagreement"]["read"] == "null"
    assert r["skew_acceleration"] is None


def test_confirmation_flips_with_the_stock_side():
    """option_stock_confirmation must actually read the stock leg — if it ignored it, both
    calls below would return the same verdict."""
    bullish_opts = {"n_ivspread": 0.4, "n_d5_ivspread": 0.4, "n_skew": 0.4}
    up = D.reads({**bullish_opts, "stock_state": "up"})["option_stock_confirmation"]["read"]
    down = D.reads({**bullish_opts, "stock_state": "down"})["option_stock_confirmation"]["read"]
    assert {up, down} == {"confirms", "contradicts"}


def test_fragility_is_declared_not_a_return_predictor():
    """Concentration died as a return predictor under neutralisation; it survives only as a
    hazard read. That distinction must be machine-readable, not just prose."""
    r = D.reads({"strike_conc": 0.4, "expiry_conc": 0.4, "turnover": 3.0})
    assert r["dealer_positioning_fragility"]["is_return_predictor"] is False
    assert r["dealer_positioning_fragility"]["read"] == "brittle"


# --------------------------------------------------------------------------- #
# measured nulls are printed, not hidden
# --------------------------------------------------------------------------- #
def test_trade_direction_features_are_printed_as_nulls_with_evidence():
    """The proposal's headline features are unbuildable here. They must appear as explicit
    nulls carrying WHY — silently omitting them would read as 'not considered'."""
    for k in ("buyer_initiated_call_volume", "buyer_initiated_put_volume",
              "opening_vs_closing_trades", "delta_weighted_directional_volume"):
        n = D.MEASURED_NULLS[k]
        assert n["state"] in ("unavailable_entitlement", "null_measured")
        assert n["why"] and n["substitute_tested"]


def test_no_signed_direction_primitive_is_scored():
    """RO-9 keeps direction unreliable for every non-tape source. No trade-direction-derived
    primitive may appear in the pre-registered (i.e. gate-eligible) sign map."""
    banned = ("buyer", "signed", "initiated", "dw_tilt", "v_tilt")
    for prim in D.PREREG_SIGNS:
        assert not any(b in prim for b in banned), f"{prim} implies trade-direction signing"


def test_prereg_signs_are_pinned():
    """These signs are the gate's pre-registration. Pinning them here makes a sign change a
    deliberate, reviewed act rather than a silent re-labelling of a failed result."""
    assert D.PREREG_SIGNS == {
        "oi_tilt": -1, "d5_ivspread": +1, "d5_term_slope": +1,
        "skew_accel": -1, "skew": -1, "ivspread": +1, "term_slope": -1,
    }


# --------------------------------------------------------------------------- #
# the gate cannot open early, and rejects a wrong-signed predictor
# --------------------------------------------------------------------------- #
def _synthetic_ledger(n_dates, n_names=40, planted_sign=0, seed=3):
    """A panel with a plantable cross-sectional predictor. planted_sign=-1 plants a signal
    carrying oi_tilt's PRE-REGISTERED sign; +1 plants the OPPOSITE.

    The signal must LEAD the return: the value recorded on date d is applied as drift to the
    spots of d+1 onward. (Recording the signal on the same bar it already moved would make
    the planted IC zero and quietly turn every gate test below into a no-op.)
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-01-01", periods=n_dates).strftime("%Y-%m-%d").tolist()
    names = [f"N{i}" for i in range(n_names)]
    rows = []
    spots = {u: 100.0 for u in names + ["SPY"]}
    pending = {u: 0.0 for u in names}          # drift earned by the PREVIOUS date's signal
    for d in dates:
        for u in names + ["SPY"]:
            drift = 0.0 if u == "SPY" else pending[u]
            spots[u] *= float(np.exp(drift + rng.normal(0, 0.004)))
        sig = {u: float(rng.normal()) for u in names}
        for u in names:
            rows.append({"date": d, "underlying": u, "spot": spots[u],
                         "n_oi_tilt": sig[u], "iv30": 0.3, "log_spot": np.log(spots[u])})
            pending[u] = planted_sign * sig[u] * 0.01
        rows.append({"date": d, "underlying": "SPY", "spot": spots["SPY"],
                     "n_oi_tilt": np.nan, "iv30": 0.3, "log_spot": np.log(spots["SPY"])})
    P = pd.DataFrame(rows)
    for c in D.PREREG_SIGNS:
        if f"n_{c}" not in P.columns:
            P[f"n_{c}"] = np.nan
    return P


def _run_gate(monkeypatch, tmp_path, panel):
    import scripts.validate_options_dislocation as G
    monkeypatch.setattr(G.D, "load_history", lambda: panel)
    monkeypatch.setattr(G.config, "data_dir", lambda: tmp_path)
    G.main()
    return json.loads((tmp_path / "options_dislocation" / "validation_gate.json").read_text())


def test_gate_stays_shut_below_the_power_floor_even_with_a_strong_signal(monkeypatch, tmp_path):
    """The load-bearing guard. A 40-date panel carrying a planted, correctly-signed,
    overwhelming predictor must STILL not score — the floor is a precondition, not a
    tiebreak. Delete the floor and this test fails."""
    g = _run_gate(monkeypatch, tmp_path, _synthetic_ledger(40, planted_sign=-1))
    assert g["scored"] is False
    assert g["scored_primitives"] == []
    assert "insufficient_history" in g["status"]


def test_gate_rejects_a_strong_predictor_with_the_wrong_sign(monkeypatch, tmp_path):
    """Sign discipline: a powerful predictor pointing OPPOSITE its pre-registration is a
    failed hypothesis, not a discovery. With ample history it must still not score."""
    g = _run_gate(monkeypatch, tmp_path, _synthetic_ledger(150, planted_sign=+1))
    # the panel really does clear the floor — so the refusal below is about SIGN, not power
    assert g["n_dates"] >= g["min_dates"] and g["n_names"] >= g["min_names"]
    assert g["scored"] is False, "a wrong-signed predictor must never score"
    h5 = g["results"]["oi_tilt"]["by_horizon"]["5"]
    assert h5["sign_ok"] is False


def test_gate_can_open_on_a_long_correctly_signed_panel(monkeypatch, tmp_path):
    """The gate must not be decorative — with enough history and the pre-registered sign it
    DOES open. Without this, all the shut-gate tests above would pass on a gate hard-wired
    to refuse."""
    g = _run_gate(monkeypatch, tmp_path, _synthetic_ledger(150, planted_sign=-1))
    assert g["scored"] is True
    assert "oi_tilt" in g["scored_primitives"]


# --------------------------------------------------------------------------- #
# payload contract
# --------------------------------------------------------------------------- #
def test_payload_is_context_only_and_carries_its_nulls():
    payload = D.build_snapshot(panel=pd.DataFrame())
    assert payload["is_context_only"] is True
    assert payload["scored"] is False
    assert payload["measured_nulls"], "printed nulls must ship in the payload"
    assert payload["neutralised_against"] == list(D._CONTROLS)


def test_payload_never_claims_validation():
    """CI law: 'validated' is forbidden in user-facing text."""
    blob = json.dumps(D.build_snapshot(panel=pd.DataFrame())).lower()
    assert "validated" not in blob
