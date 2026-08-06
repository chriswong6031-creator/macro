"""Quant Lab — the honesty contract, pinned.

Most of these tests exist because the defect they guard against SHIPPED during the build
and was caught by running the code, not by reading it. Each one names its incident so a
future edit that reintroduces the bug fails with the reason attached rather than a bare
assertion.

See research/QUANT_LAB_MASTERPLAN_FINTEL_RECREATION.md §0 for the acceptance gates.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.quant_lab import score, specs, study


# ---------------------------------------------------------------------------------------
# Registry honesty (gates §1, §2)
# ---------------------------------------------------------------------------------------
def test_every_model_has_sourced_provenance():
    for key, spec in specs.MODELS.items():
        assert spec["provenance"], f"{key} has no provenance"
        for src in spec["provenance"]:
            assert src in specs.SOURCES, f"{key} cites unknown source {src!r}"
            s = specs.SOURCES[src]
            assert s.get("url") and s.get("publisher"), f"source {src} is missing url/publisher"


def test_non_faithful_legs_must_name_their_distortion():
    """Gate §2. A stand-in whose distortion is unnamed is a lie of omission — the reader
    cannot tell which direction the number is wrong in."""
    for key, spec in specs.MODELS.items():
        for leg in spec["legs"]:
            if leg["fidelity"] != "faithful":
                assert leg["distortion"], (
                    f"{key}.{leg['key']} is graded {leg['fidelity']!r} with no named "
                    f"distortion")


def test_inferred_legs_are_flagged_not_passed_off_as_vendor_spec():
    """Fintel grounds 3 of QV's 6 legs (3y avg ROIC, its growth, 3y avg EBIT/EV — the
    quantities named in the AMR readout). The other 3 are OUR inference from the published
    lineage and must never render as though the vendor stated them."""
    qv = specs.MODELS["fintel_qv"]
    inferred = [x for x in qv["legs"] if not x["vendor_disclosed"]]
    assert len(inferred) == 3, "QV's disclosed/inferred split changed — re-check the sources"
    for leg in inferred:
        assert not leg["vendor_definition"], (
            f"{leg['key']} is marked inferred but carries a vendor_definition")


def test_fidelity_grades_are_from_the_known_set():
    for key, spec in specs.MODELS.items():
        for leg in spec["legs"]:
            assert leg["fidelity"] in ("faithful", "proxy", "absent"), \
                f"{key}.{leg['key']} has unknown fidelity {leg['fidelity']!r}"


def test_qvo_stays_ungradeable_until_a_real_13f_feed_lands():
    """MEASURED at 1.3% coverage. If someone later flips this leg to `proxy` without
    landing a full 13F aggregate, QVO silently becomes a QV board wearing a QVO label."""
    qvo = specs.MODELS["fintel_qvo"]
    fs = next(x for x in qvo["legs"] if x["key"] == "fund_sentiment")
    assert fs["fidelity"] == "absent", (
        "fund_sentiment was re-graded — QVO is only recreatable with a full 13F register, "
        "not 53 curated funds")


# ---------------------------------------------------------------------------------------
# Point-in-time law (gate §3)
# ---------------------------------------------------------------------------------------
def test_non_pit_store_is_excluded_by_name_with_a_reason():
    """statements.parquet is our RICHEST schema and would improve every EV leg, which is
    exactly why its exclusion must be explicit rather than remembered."""
    s = specs.SUBSTRATE["edgar_statements"]
    assert s["point_in_time"] is False
    assert "FETCH" in s["pit_key"] or "fetch" in s["pit_key"].lower()
    assert "LIVE MODE ONLY" in s["note"]


def test_the_two_pit_stores_declare_a_real_date_key():
    for k in ("edgar_fundamentals_panel", "edgar_statements_quarterly"):
        s = specs.SUBSTRATE[k]
        assert s["point_in_time"] is True
        assert s["pit_key"], f"{k} claims PIT with no key"


# ---------------------------------------------------------------------------------------
# Scoring law
# ---------------------------------------------------------------------------------------
def _toy(n=200, seed=0):
    rng = np.random.default_rng(seed)
    idx = [f"T{i:03d}" for i in range(n)]
    return pd.DataFrame({"a": rng.normal(size=n), "b": rng.normal(size=n),
                         "c": rng.normal(size=n)}, index=idx)


def test_blend_then_rank_and_rank_then_blend_agree_on_ORDER():
    """They are monotone transforms of each other. This is pinned because `rule_divergence`
    originally compared these two and reported 20/20 overlap on every input — a vacuous
    check that looked like a passing one."""
    L = _toy()
    a = score.composite(L, rule="blend_then_rank")["score"].dropna()
    b = score.composite(L, rule="rank_then_blend")["score"].dropna()
    j = pd.concat([a, b], axis=1).dropna()
    assert j.iloc[:, 0].rank().corr(j.iloc[:, 1].rank()) == pytest.approx(1.0, abs=1e-9)


def test_z_then_rank_can_actually_reorder():
    """The genuinely different basis. If this ever ties to 1.0 the divergence report has
    gone vacuous again."""
    L = _toy()
    L.loc["T000", "a"] = 500.0                       # one extreme leg
    a = score.composite(L, rule="blend_then_rank")["score"]
    b = score.composite(L, rule="z_then_rank")["score"]
    j = pd.concat([a.rename("p"), b.rename("z")], axis=1).dropna()
    assert j["p"].rank().corr(j["z"].rank()) < 0.999


def test_rank_then_blend_is_bounded_by_its_inputs_but_blend_then_rank_is_not():
    """The arithmetic behind the vendor-rule finding."""
    L = _toy()
    r = score.composite(L, rule="rank_then_blend")
    legmax = r["leg_pct"].max(axis=1)
    ok = r["score"].dropna()
    assert (ok <= legmax.reindex(ok.index) + 1e-9).all(), \
        "a convex blend of percentiles exceeded its own max — the bound is broken"


def test_missing_legs_are_renormalised_never_imputed_to_the_median():
    """Imputing the median would reward missing data, which on this panel correlates with
    being small and thinly covered."""
    L = _toy(n=100)
    L.loc["T000", "b"] = np.nan
    r = score.composite(L, min_legs=2)
    assert not np.isnan(r["blend"]["T000"]), "a name with 2 of 3 legs should still score"
    assert r["n_legs_used"]["T000"] == 2


def test_min_legs_floor_blocks_thinly_evaluated_names():
    """INCIDENT: the first scorer ran min_legs=2 on a 6-leg model, so YOU/PTON/DBX (3 legs
    each) outranked ADBE (6 legs). A name must be judged on most of the model to be ranked
    by the model."""
    assert specs is not None
    assert score.default_min_legs(6) == 4
    assert score.default_min_legs(3) == 2
    assert score.default_min_legs(2) == 2
    L = _toy(n=100)
    L.loc["T000", ["b", "c"]] = np.nan               # 1 of 3 legs
    r = score.composite(L)                            # default floor = 2
    assert np.isnan(r["score"]["T000"]), "a 1-of-3 name was scored despite the floor"


def test_percentile_needs_a_real_cross_section():
    small = pd.Series(np.arange(5.0), index=list("abcde"))
    assert score.percentile_score(small, min_n=20).isna().all()


def test_unknown_rule_raises():
    with pytest.raises(ValueError):
        score.composite(_toy(), rule="vibes")


# ---------------------------------------------------------------------------------------
# The vendor-rule reverse engineering (§2 of the masterplan)
# ---------------------------------------------------------------------------------------
def test_published_totals_exceed_their_own_subscores():
    """The load-bearing refutation of a convex weighted average. Exactly MCEM and WSM."""
    assert score.exceeds_all_subscores() == ["MCEM", "WSM"]


def test_fitted_rule_reproduces_the_published_numbers_and_is_labelled_local():
    f = score.fit_observed_weights()
    assert f["r2"] > 0.99 and f["max_abs_resid"] < 1.0
    assert f["weight_sum"] > 1.0, \
        "weights summing above 1 is the re-percentiling fingerprint — it should survive"
    assert f["weights"]["value"] > f["weights"]["quality"] > f["weights"]["momentum"]
    assert "n=10" in f["caveat"] and "LOCAL" in f["caveat"].upper()


# ---------------------------------------------------------------------------------------
# Study verdicts (gates §5, §6)
# ---------------------------------------------------------------------------------------
def test_negative_ic_is_never_reported_as_a_survivor():
    """INCIDENT: the first harness labelled the QV composite `survives_fdr` on
    mean_ic = -0.031, t = -2.43, q = 0.035 — i.e. it reported 'the model works' about a
    signal that ranked winners BELOW losers."""
    v = study._verdict({"n_dates": 12, "mean_ic": -0.031, "t_hac": -2.43}, 0.035)
    assert v == "inverted", f"a significantly anti-predictive signal was graded {v!r}"


def test_positive_ic_clearing_fdr_survives():
    assert study._verdict({"n_dates": 12, "mean_ic": 0.031, "t_hac": 2.43}, 0.035) == "survives_fdr"


def test_thin_history_reports_insufficient_rather_than_a_p_value():
    assert study._verdict({"n_dates": 3, "mean_ic": 0.2, "t_hac": 9.0}, 0.001) == "insufficient"
    assert study._verdict({"n_dates": 0}, None) == "no_data"


def test_insignificant_negative_is_null_not_inverted():
    assert study._verdict({"n_dates": 12, "mean_ic": -0.004, "t_hac": -0.3}, 0.8) == "null"


def test_verdict_vocabulary_is_closed():
    for args in (({"n_dates": 0}, None), ({"n_dates": 3, "mean_ic": 0.1}, None),
                 ({"n_dates": 12, "mean_ic": 0.03, "t_hac": 2.4}, 0.02),
                 ({"n_dates": 12, "mean_ic": -0.03, "t_hac": -2.4}, 0.02),
                 ({"n_dates": 12, "mean_ic": 0.03, "t_hac": 2.4}, 0.9),
                 ({"n_dates": 12, "mean_ic": 0.001, "t_hac": 0.1}, 0.9)):
        assert study._verdict(*args) in study.VERDICTS


# ---------------------------------------------------------------------------------------
# Leg resolution (gate §6)
# ---------------------------------------------------------------------------------------
def test_ref_model_legs_expand_so_a_composite_cannot_wear_a_parent_name():
    """INCIDENT: QVM's first leg IS the QV model, not a column. Unexpanded, the scorer
    dropped it and QVM collapsed to plain 6-month momentum — then reported `survives_fdr`
    under the QVM name on an IC identical to momentum's."""
    qv = specs.resolve_leg_keys("fintel_qv")
    qvm = specs.resolve_leg_keys("fintel_qvm")
    assert "qv_composite" not in qvm, "the ref leg was not expanded"
    assert set(qv).issubset(set(qvm)), "QVM lost QV's legs"
    assert "momentum_6m" in qvm
    assert len(qvm) == len(qv) + 1


def test_resolved_weights_normalise_and_keep_momentum_a_light_tilt():
    qvm = specs.resolve_leg_keys("fintel_qvm")
    assert sum(qvm.values()) == pytest.approx(1.0, abs=1e-9)
    fitted = specs.MODELS["fintel_qvm"]["combination"]["weights"]["momentum"]
    assert qvm["momentum_6m"] == pytest.approx(fitted, abs=1e-9), \
        "momentum should carry the FITTED vendor tilt, not equal footing with 6 legs"
    assert qvm["momentum_6m"] < min(v for k, v in qvm.items() if k != "momentum_6m") * 1.01


def test_absent_legs_are_dropped_from_resolution():
    """QVO's fund_sentiment is `absent`, so it must not silently enter a blend."""
    assert "fund_sentiment" not in specs.resolve_leg_keys("fintel_qvo")


def test_circular_ref_models_raise_rather_than_recurse_forever():
    saved = specs.MODELS["fintel_qv"]["legs"]
    try:
        specs.MODELS["fintel_qv"]["legs"] = [
            dict(saved[0], key="loop", ref_model="fintel_qvm", fidelity="proxy")]
        with pytest.raises(ValueError):
            specs.resolve_leg_keys("fintel_qvm")
    finally:
        specs.MODELS["fintel_qv"]["legs"] = saved


# ---------------------------------------------------------------------------------------
# Standing limits must travel with the numbers (gate §7)
# ---------------------------------------------------------------------------------------
def test_standing_limits_name_survivorship_universe_history_and_tier():
    L = study.STANDING_LIMITS
    for k in ("survivorship", "universe", "history", "tier"):
        assert L.get(k), f"standing limit {k} went missing"
    assert "display-tier" in L["tier"].lower()
    assert "rank" in L["tier"].lower()


def test_universe_gap_records_the_finding_that_decides_integration():
    g = specs.UNIVERSE_GAP
    assert g["our_fundamentals_universe"] < g["our_price_universe"], \
        "the binding universe is FUNDAMENTALS coverage, not price coverage"
    assert g["published_leaders_in_our_fundamentals_panel"] < g["published_leaders_tested"]
    assert g["fintel_screened"] > g["our_fundamentals_universe"] * 10


def test_decile_spread_refuses_a_thin_cross_section():
    sig = pd.Series(np.arange(12.0), index=[f"T{i}" for i in range(12)])
    assert study.decile_spread(sig, sig) is None
