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


# ---------------------------------------------------------------------------
# Coverage chips are CURRENT-STATE claims and must be read, not stamped. They were
# hardcoded at 1,552 names / 4-of-10 leaders; W2-A (#4688) widened the panel past
# 2,800, which would have left the shipped page asserting a filings coverage it no
# longer has and naming CMT/KRT as uncovered when both are now in the panel.
# ---------------------------------------------------------------------------

def _panel(tmp_path, tickers):
    d = tmp_path / "edgar"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"ticker": list(tickers), "fy": [2025] * len(tickers)}).to_parquet(
        d / "fundamentals_panel.parquet")


def test_coverage_chips_follow_a_widened_panel(tmp_path, monkeypatch):
    from engine.quant_lab import page as page_mod
    # STRL/IESC/WSM were covered pre-W2-A; CMT/KRT are the two the copy called out
    # as having no fundamentals at all, and are the two the widening recovered.
    _panel(tmp_path, ["STRL", "IESC", "WSM", "CMT", "KRT"] + [f"X{i}" for i in range(2821)])
    monkeypatch.setattr(page_mod.config, "data_dir", lambda: tmp_path)
    g = page_mod._universe_gap()
    assert g["our_fundamentals_universe"] == 2826
    assert g["published_leaders_in_our_fundamentals_panel"] == 5
    assert page_mod._substrate()["edgar_fundamentals_panel"]["tickers"] == 2826


def test_frozen_study_stamps_do_not_move_with_the_panel(tmp_path, monkeypatch):
    # The study's IC numbers were computed on the 1,552-name panel; those facts are
    # history and must NOT be rewritten when the live panel grows.
    from engine.quant_lab import page as page_mod
    _panel(tmp_path, [f"X{i}" for i in range(2826)])
    monkeypatch.setattr(page_mod.config, "data_dir", lambda: tmp_path)
    g = page_mod._universe_gap()
    assert g["our_fundamentals_universe_at_study"] == 1552
    assert g["published_leaders_in_our_fundamentals_panel_at_study"] == 3
    assert specs.UNIVERSE_GAP["our_fundamentals_universe"] == 1552, \
        "the module constant must not be mutated — it is the fallback"


def test_coverage_falls_back_when_the_panel_is_unreadable(tmp_path, monkeypatch):
    from engine.quant_lab import page as page_mod
    monkeypatch.setattr(page_mod.config, "data_dir", lambda: tmp_path / "absent")
    g = page_mod._universe_gap()
    assert g["our_fundamentals_universe"] == specs.UNIVERSE_GAP["our_fundamentals_universe"]
    assert page_mod._substrate()["edgar_fundamentals_panel"]["tickers"] == 1552


def test_assembled_payload_carries_the_live_coverage_not_the_stamp(tmp_path, monkeypatch):
    # Pins the WIRING, not just the helper: build_payload() must hand the template the
    # live-derived gap. Without this, reverting the payload to specs.UNIVERSE_GAP passes
    # every other test in this block while the page ships the stale chip again.
    from engine.quant_lab import page as page_mod
    _panel(tmp_path, ["STRL", "IESC", "WSM", "CMT", "KRT"] + [f"X{i}" for i in range(2821)])
    monkeypatch.setattr(page_mod.config, "data_dir", lambda: tmp_path)
    payload = page_mod.build_payload()
    assert payload["universe_gap"]["our_fundamentals_universe"] == 2826
    assert payload["universe_gap"]["published_leaders_in_our_fundamentals_panel"] == 5
    assert payload["substrate"]["edgar_fundamentals_panel"]["tickers"] == 2826


def test_published_leaders_list_matches_its_own_denominator():
    # The numerator counted AMR — an 11th name from a separate article — against a
    # denominator of 10, which is what made the stamped figure 4 rather than 3.
    g = specs.UNIVERSE_GAP
    assert len(g["published_leaders"]) == g["published_leaders_tested"]
    assert "AMR" not in g["published_leaders"]


def test_decile_spread_refuses_a_thin_cross_section():
    sig = pd.Series(np.arange(12.0), index=[f"T{i}" for i in range(12)])
    assert study.decile_spread(sig, sig) is None


# =======================================================================================
# Options dislocation registration
#
# Every test below pins a defect that actually occurred while wiring this family in, not a
# hypothetical. The panel is six weeks of one regime, so the standing risk here is not a
# wrong number — it is a number that LOOKS decided.
# =======================================================================================
def test_options_legs_are_generated_from_the_imported_prereg_not_a_second_copy():
    """There must be exactly ONE pre-registration. A restated sign map here would be free to
    drift away from the one engine/options_dislocation.py's dormant gate actually tests."""
    from engine.options_dislocation import MEASURED_NULLS, PREREG_SIGNS
    legs = {x["key"]: x for x in specs.MODELS["options_dislocation"]["legs"]}
    for k in PREREG_SIGNS:
        assert k in legs, f"pre-registered primitive {k!r} has no leg"
        assert legs[k]["fidelity"] != "absent"
    for k in MEASURED_NULLS:
        assert k in legs, f"measured null {k!r} is not disclosed as a leg"
        assert legs[k]["fidelity"] == "absent"
    assert len(legs) == len(PREREG_SIGNS) + len(MEASURED_NULLS)


def test_a_new_prereg_primitive_fails_loudly_instead_of_shipping_a_missing_leg():
    """The drift guard has to FIRE. A leg table that silently ignored an added primitive
    would ship a page that omits it while claiming to enumerate the family."""
    import engine.quant_lab.specs as specs_mod
    orig = dict(specs_mod.PREREG_SIGNS)
    try:
        specs_mod.PREREG_SIGNS["a_brand_new_primitive"] = +1
        with pytest.raises(ValueError, match="out of step with PREREG_SIGNS"):
            specs_mod._options_dislocation_legs()
    finally:
        specs_mod.PREREG_SIGNS.clear()
        specs_mod.PREREG_SIGNS.update(orig)


def test_all_five_measured_nulls_are_printed_not_just_the_entitlement_blocked_three():
    """Three nulls are blocked by entitlements; two were MEASURED dead. Shipping only the
    first three is the easy half of 'nulls printed, not hidden' to lose."""
    legs = {x["key"]: x for x in specs.MODELS["options_dislocation"]["legs"]}
    for k in ("delta_weighted_directional_volume", "synthetic_stock_price_deviation"):
        assert legs[k]["fidelity"] == "absent"
        assert legs[k]["distortion"], f"{k} is absent with no evidence attached"
    assert "0.41" in legs["buyer_initiated_call_volume"]["distortion"]
    assert "RO-10" in legs["opening_vs_closing_trades"]["distortion"]


def test_options_family_ships_no_fused_composite_anywhere():
    """RO-2 / Signal Commons R3: a fused escalating score is a FORBIDDEN shape pre-gate.
    The failure mode is a reader lifting one number off the page, so the guard is that no
    such number exists — not that it is merely labelled carefully."""
    spec = specs.MODELS["options_dislocation"]
    assert spec["combination"]["rule"] == "none_categorical"
    assert "weights" not in spec["combination"]
    r = study.study_options_dislocation()
    assert "composite" not in r, "a composite IS the forbidden fused score"
    assert r["verdict"] == "per_primitive"
    for k, v in r["legs"].items():
        assert "score" not in v and "rank" not in v, f"{k} carries a liftable score"


def test_options_ledger_is_pit_but_names_its_run_date_stamping():
    """It passes the statements.parquet test (real per-date stamps, not five fetch times) —
    but the stamp is the COLLECTOR RUN date, and a green 'Yes' pill next to an unqualified
    key would hide that. Measured: 9 of 41 stamps repeat the prior session."""
    s = specs.SUBSTRATE["options_dislocation_snapshots"]
    assert s["point_in_time"] is True
    assert "RUN date" in s["pit_key"]
    assert "32 distinct market sessions" in s["pit_key"]


def test_duplicate_run_date_stamps_are_collapsed_to_real_sessions():
    """A weekend run re-reads Friday's chain under a new stamp. Counting those as separate
    dates enters one cross-section up to three times and shrinks every standard error."""
    hist = pd.DataFrame({
        "date": ["2026-06-19"] * 6 + ["2026-06-20"] * 6 + ["2026-06-22"] * 6,
        "underlying": list("ABCDEF") * 3,
        "spot": [10.0, 11, 12, 13, 14, 15] * 2 + [20.0, 21, 22, 23, 24, 25],
    })
    keep = study.options_sessions(hist)
    assert keep == ["2026-06-19", "2026-06-22"], \
        "the re-stamped Saturday copy of Friday's chain was scored as its own session"


def test_overlapping_daily_windows_are_counted_as_independent_ones():
    """THE load-bearing one. `_verdict`'s n<8 floor assumes independent observations, true of
    the quarterly grid it was written for. On a daily h=5 panel consecutive cross-sections
    share 4 of their 5 forward days, and scored naively EVERY primitive on the first ledger
    came back `survives_fdr` — seven significant-looking factors out of six weeks of one
    regime."""
    r = study.study_options_dislocation()
    assert r["legs"], "no primitives scored at all"
    for k, v in r["legs"].items():
        if not v.get("n_dates"):
            continue
        assert v["n_independent_windows"] <= v["n_dates"] // r["horizon_d"] + 1
        assert v["verdict"] == "insufficient", (
            f"{k} reported {v['verdict']!r} on a single-regime six-week panel — the "
            f"overlap correction is not being applied")
        assert v.get("verdict_uncorrected"), \
            f"{k} does not publish what the uncorrected reading would have been"


def test_every_model_verdict_has_a_display_label():
    """`per_primitive` had no entry in the template's VERD map, so the page rendered a grey
    'No data' pill on a model with 27 scored dates."""
    import re
    from pathlib import Path
    from lib import config
    tpl = (Path(config.ROOT) / "templates" / "quant_lab.html.j2").read_text()
    block = tpl.split("{% set VERD =", 1)[1].split("} %}", 1)[0]
    labelled = set(re.findall(r"'([a-z_]+)':\s*\(", block))
    produced = set(study.VERDICTS) | {"degenerate", "per_primitive"}
    assert produced <= labelled, f"verdicts with no display label: {sorted(produced - labelled)}"


# ---------------------------------------------------------------------------------------
# METHOD cards — external proposals that are not per-name rankers
# ---------------------------------------------------------------------------------------
REQUIRED_METHOD_FIELDS = (
    "name", "proposer", "source_kind", "one_line", "shape", "proposal_says",
    "not_a_ranker_because", "our_test", "result_artifact", "harness",
    "provenance", "house_rulings", "still_live", "reopen_when",
)


def test_every_method_declares_the_full_contract():
    for key, spec in specs.METHODS.items():
        for f in REQUIRED_METHOD_FIELDS:
            assert spec.get(f), f"method {key} is missing {f!r}"


def test_method_provenance_is_named_even_when_there_is_no_url():
    """A relayed proposal has no public URL. It may still be cited — but only if the
    publisher is named AND the claim is quoted verbatim, so the thing we tested is on the
    record beside what we measured. A url=None source with no quote would be an unfalsifiable
    attribution."""
    for key, spec in specs.METHODS.items():
        assert spec["provenance"], f"method {key} has no provenance"
        for src in spec["provenance"]:
            assert src in specs.SOURCES, f"method {key} cites unknown source {src!r}"
            s = specs.SOURCES[src]
            assert s.get("publisher"), f"source {src} names no publisher"
            if not s.get("url"):
                assert len(spec["proposal_says"]) > 120, (
                    f"method {key} cites URL-less source {src} without quoting the claim")
                assert s.get("why"), f"URL-less source {src} must explain why it has no URL"


def test_method_specs_carry_no_numbers():
    """THE anti-staleness rule for this shelf. Every measurement lives in the result
    artifact, written by the harness; a statistic hand-typed into the registry outlives the
    recompute that would have corrected it and nothing here can tell it went stale."""
    def scan(node, path):
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            raise AssertionError(f"numeric literal {node!r} in METHODS spec at {path} — "
                                 f"measurements belong in the result artifact")
        if isinstance(node, dict):
            for k, v in node.items():
                scan(v, f"{path}.{k}")
        elif isinstance(node, (list, tuple)):
            for i, v in enumerate(node):
                scan(v, f"{path}[{i}]")
    for key, spec in specs.METHODS.items():
        scan(spec, key)


def test_method_rulings_name_a_registry_row_and_a_verdict():
    for key, spec in specs.METHODS.items():
        for r in spec["house_rulings"]:
            assert r.get("row") and r.get("verdict") and r.get("why"), (
                f"method {key} has an unsourced ruling: {r}")


def test_method_key_lookup_raises_on_typo():
    with pytest.raises(KeyError):
        specs.method("no_such_method")


# ---------------------------------------------------------------------------------------
# METHOD card rendering — each of these defects was caught by rendering the page
# ---------------------------------------------------------------------------------------
def _render(payload_overrides: dict | None = None) -> str:
    from jinja2 import Environment, FileSystemLoader
    from engine.quant_lab import page as ql_page
    p = ql_page.build_payload()
    p.update(payload_overrides or {})
    env = Environment(loader=FileSystemLoader("templates"))
    return env.get_template("quant_lab.html.j2").render(**p, generated_utc="2026-01-01T00:00Z")


def _method_section(html: str) -> str:
    i = html.find("Methods that do not pick names")
    j = html.find("EVIDENCE: the combination rule")
    assert i != -1, "the methods shelf did not render"
    return html[i:j if j > i else len(html)]


def test_a_small_nonzero_coverage_never_renders_as_zero_percent():
    """INCIDENT: 0.4% coverage rendered as "0%", which reads as "never recorded" — the
    opposite of the finding. The axis IS stamped; it is stamped far too thinly to use."""
    seg = _method_section(_render())
    assert "0.4%" in seg, "0.4% coverage was rounded away"
    import re
    rows = re.findall(r"quad_hard_label.*?</tr>", seg, re.S)
    assert rows and ">0%<" not in rows[0], "a stamped axis was rendered as 0% coverage"


def test_an_axis_seen_in_one_state_says_so_even_when_coverage_fails_first():
    """The gate fails on coverage first, but "only ever one state" is the deeper
    disqualifier: a conditional expectation over one observed state is undefined. The page
    must name that rather than the milder "barely recorded"."""
    seg = _method_section(_render())
    import re
    for axis in ("vol_regime", "rate_pressure"):
        row = re.findall(rf"{axis}.*?</tr>", seg, re.S)
        assert row, f"{axis} row missing"
        assert "Only ever one state" in row[0], f"{axis} did not disclose its single state"


def test_a_missing_result_artifact_claims_nothing():
    """A card whose measurement file is absent must say so — never let the spec's prose
    imply a measurement that was not made."""
    from engine.quant_lab import page as ql_page
    p = ql_page.build_payload()
    for m in p["methods"]:
        m["result"], m["has_result"] = {}, False
    seg = _method_section(_render({"methods": p["methods"]}))
    assert "nothing is claimed here" in seg
    assert "What we found" not in seg, "a card with no artifact still showed a finding"


def test_method_verdict_uses_the_shared_verdict_vocabulary():
    """One vocabulary, defined once — a method card must not invent its own verdict words."""
    seg = _method_section(_render())
    assert "No signal" in seg and "无信号" in seg


def test_the_shelf_states_why_these_methods_are_not_ranked_like_models():
    seg = _method_section(_render())
    assert "not scored like the models above" in seg
    assert "no per-name score" in seg


# =======================================================================================
# Null contract — non-finite sentinels must never reach the model board
# (Wave-2 bug: site/quant_lab.html rendered bare "nan" — 46 occurrences — because
# `_fmt()`'s `isinstance(v, (int, float))` guard is True for float("nan") too, so a
# leg's per-name percentile (NaN when that name lacks the raw leg — the normal shape
# of `score_mod.composite()`'s leg_pct, see _weighted_blend's docstring on renormalised
# scoring) sailed straight through into the template. `_fmt()` is the producing-boundary
# fix; the num()/pct0()/pctfine() macros are the second-layer guard. These tests drive
# the REAL build_payload() -> _live_board() -> _fmt() -> template path with a synthetic
# panel carrying every non-finite shape, and assert none of them leak into the board.
# =======================================================================================
import re


def test_fmt_normalizes_every_non_finite_shape_and_preserves_zero():
    from engine.quant_lab import page as page_mod
    for bad in (float("nan"), pd.NA, pd.NaT, float("inf"), float("-inf"),
                "not-a-number", None, True, False):
        assert page_mod._fmt(bad, 2) is None, f"_fmt({bad!r}) leaked a sentinel"
    assert page_mod._fmt(0, 4) == 0
    assert page_mod._fmt(0.0, 4) == 0.0
    assert page_mod._fmt(42.567, 2) == 42.57


def _leg_keys():
    from engine.quant_lab import specs as specs_mod
    return [x["key"] for x in specs_mod.MODELS["fintel_qv"]["legs"]]


def _synthetic_legs_and_mktcap():
    """A 44-name synthetic panel for the fintel_qv board: 40 background names with a
    clean linear spread (so percentile ranks are deterministic) plus 4 planted names
    that dominate every leg (guaranteeing top-15 inclusion) and each carry ONE
    deliberately non-finite cell — TOPNAN's last leg is NaN (the realistic "name is
    missing this one raw leg" shape), NANCAP's/ZEROCAP's market caps are NaN/0."""
    keys = _leg_keys()
    bg = [f"BG{i:02d}" for i in range(40)]
    L = pd.DataFrame({k: [float(i) for i in range(40)] for k in keys}, index=bg)
    special = {
        "TOPNAN": {k: 500.0 for k in keys},
        "NANCAP": {k: 490.0 for k in keys},
        "ZEROCAP": {k: 480.0 for k in keys},
        "REALTOP": {k: 470.0 for k in keys},
    }
    special["TOPNAN"][keys[-1]] = float("nan")   # name missing its raw last leg
    for tkr, row in special.items():
        L.loc[tkr] = row
    mktcap = pd.Series({
        **{t: 1e9 for t in bg},
        "TOPNAN": 2e9, "REALTOP": 3e9,
        "NANCAP": float("nan"), "ZEROCAP": 0.0,
    })
    return L, mktcap


def _stub_compute_legs():
    L, mktcap = _synthetic_legs_and_mktcap()
    return {"legs": L, "mktcap": mktcap, "asof": "2026-08-19",
            "n_universe": len(L), "coverage": {}, "years": 3, "tax_rate": 0.21}


def test_live_board_replaces_nan_leg_with_none_not_a_float(monkeypatch):
    """Direct check on the payload (pre-template): a name's missing raw leg must come
    through _live_board() as None, never as a NaN float object."""
    from engine.quant_lab import page as page_mod
    monkeypatch.setattr(page_mod.legs_mod, "compute_legs", _stub_compute_legs)
    payload = page_mod.build_payload()
    board = next(m["board"] for m in payload["models"] if m["key"] == "fintel_qv")
    assert board is not None
    row = next(r for r in board["rows"] if r["ticker"] == "TOPNAN")
    missing_key = _leg_keys()[-1]
    assert row["legs"][missing_key] is None
    cap_row = next(r for r in board["rows"] if r["ticker"] == "NANCAP")
    assert cap_row["mktcap_bn"] is None
    zero_row = next(r for r in board["rows"] if r["ticker"] == "ZEROCAP")
    assert zero_row["mktcap_bn"] == 0.0          # a real 0 market cap, not null


def test_quant_lab_full_render_board_has_no_non_finite_sentinel(monkeypatch):
    """Render the FULL quant_lab.html.j2 page against the synthetic panel and scan just
    the fintel_qv model-board <tr> rows (not the whole page — the page's disclosure
    prose legitimately contains "infrastructure"-shaped words) for a leaked sentinel."""
    from engine.quant_lab import page as page_mod
    monkeypatch.setattr(page_mod.legs_mod, "compute_legs", _stub_compute_legs)
    html = _render()

    sentinel_re = re.compile(r"(?<![a-zA-Z])(nan|-?inf)(?![a-zA-Z])", re.IGNORECASE)
    for tkr in ("TOPNAN", "NANCAP", "ZEROCAP", "REALTOP"):
        m = re.search(rf"<td[^>]*>{tkr}</td>.*?</tr>", html, re.DOTALL)
        assert m, f"board row for {tkr} not found in rendered page"
        row_html = m.group(0)
        leaked = sentinel_re.search(row_html)
        assert leaked is None, (
            f"non-finite sentinel {leaked.group(0)!r} leaked into {tkr}'s board row: "
            f"{row_html!r}")

    # the missing leg cell degrades to the muted null glyph, not a blank/garbage cell
    m = re.search(r"<td[^>]*>TOPNAN</td>.*?</tr>", html, re.DOTALL)
    assert '<span class="muted">—</span>' in m.group(0)


def test_quant_lab_zero_mktcap_survives_as_real_value(monkeypatch):
    """A legitimate 0 market cap must render as a real "0.0", never promoted to the
    missing-data em-dash (the same cell that renders '—' for a genuinely missing cap)."""
    from engine.quant_lab import page as page_mod
    monkeypatch.setattr(page_mod.legs_mod, "compute_legs", _stub_compute_legs)
    html = _render()

    zero_row = re.search(r"<td[^>]*>ZEROCAP</td>.*?</tr>", html, re.DOTALL).group(0)
    nan_row = re.search(r"<td[^>]*>NANCAP</td>.*?</tr>", html, re.DOTALL).group(0)
    assert '<span class="muted">—</span>' not in zero_row.split("</tr>")[0], zero_row
    assert "0.0" in zero_row
    assert '<span class="muted">—</span>' in nan_row   # the genuinely-missing cap IS null


def test_num_macro_is_non_finite_safe_even_if_fmt_is_bypassed(monkeypatch):
    """Second-layer defensive check on the macros themselves, INDEPENDENT of _fmt: plant
    raw non-finite floats straight into a real board row (as if a future producer
    regressed and skipped `_fmt` entirely) and render the full page — num()/pct0()/
    pctfine() must still degrade to the null glyph rather than trust the input.

    (A template-snippet render via `{% import ... as q %}` was tried first, but Jinja
    executes the WHOLE imported template body on import — not just the macro defs — so
    it immediately hit `live.asof` from the page's top-level markup and failed with an
    unrelated UndefinedError. Mutating a real payload and rendering the full page avoids
    that entirely while still exercising the macros exactly as production does.)"""
    from jinja2 import Environment, FileSystemLoader
    from engine.quant_lab import page as page_mod
    monkeypatch.setattr(page_mod.legs_mod, "compute_legs", _stub_compute_legs)
    p = page_mod.build_payload()
    m = next(mm for mm in p["models"] if mm["key"] == "fintel_qv")
    assert m["board"] is not None and m["board"]["rows"]

    row = dict(m["board"]["rows"][0])
    leg0 = next(iter(row["legs"]))
    row["ticker"] = "BYPASSCHK"
    row["score"] = float("nan")
    row["mktcap_bn"] = float("inf")
    row["legs"] = {**row["legs"], leg0: float("-inf")}
    board = dict(m["board"])
    board["rows"] = [row] + list(m["board"]["rows"][1:])
    models = [dict(mm, board=board) if mm["key"] == "fintel_qv" else mm for mm in p["models"]]

    env = Environment(loader=FileSystemLoader("templates"))
    html = env.get_template("quant_lab.html.j2").render(
        **{**p, "models": models}, generated_utc="2026-01-01T00:00Z")

    row_html = re.search(r"<td[^>]*>BYPASSCHK</td>.*?</tr>", html, re.DOTALL).group(0)
    assert "nan" not in row_html.lower() and "inf" not in row_html.lower(), row_html
    # score/mktcap/leg0 were forcibly set to NaN/+inf/-inf above (bypassing _fmt); the
    # macros alone must still null all three (>= not == : the underlying synthetic
    # TOPNAN-shaped row may already carry its own legitimately-null leg, which is fine)
    assert row_html.count('<span class="muted">—</span>') >= 3
