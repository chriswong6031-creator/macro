"""Tests for the market-response model and the lawful-regime feature layer.

Organised around the failures these two modules exist to prevent, not around
their public surface — a test that ``forecast()`` returns a float proves nothing.
The tests that matter here are the REFUSALS:

* the ownership tests assert that a BioCatalyst-owned probability is refused BY
  NAME, because a model that quietly regresses on an approval prior produces a
  number that reads exactly like a market edge;
* the typed-target tests assert BOTH directions — a binary target carries a
  probability key and a continuous one does not — because "continuous has no
  probability key" is vacuous if nothing in the module ever emits one;
* the uncertainty tests assert a RAISE on a generic label, because the three
  uncertainties differ by a large factor and a reader cannot tell them apart from
  the numbers alone;
* the regime tests assert that no public callable returns a scalar fusing several
  axes, at runtime rather than by reading the source, because renaming a
  composite does not make it lawful.

Everything is synthetic, offline, and writes nothing outside ``tmp_path``.
"""
from __future__ import annotations

import ast
import inspect
import math
import numbers
import pathlib
import re
from datetime import date

import pytest

from engine.seasonality import model as M
from engine.seasonality import regime as R

MODEL_SOURCE = pathlib.Path(M.__file__)
REGIME_SOURCE = pathlib.Path(R.__file__)

CUTOFF = date(2026, 6, 1)
ASOF = date(2026, 6, 20)


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def _obs(n=240, *, n_issuers=20, n_clusters=40, binary=True, seed=7,
         constant=None, spread=0.05):
    """A synthetic market-response panel with declared issuer/cluster structure."""
    import random

    rng = random.Random(seed)
    rows = []
    for i in range(n):
        if constant is not None:
            value = float(constant)
        elif binary:
            value = 1.0 if rng.random() < 0.55 else 0.0
        else:
            value = rng.gauss(0.012, spread)
        rows.append({
            "value": value,
            "issuer": f"ISS{i % n_issuers}",
            "event_type": ["pdufa", "readout", "adcom"][i % 3],
            "therapeutic_class": ["onc", "cns", "immu", "cardio"][i % 4],
            "date_cluster": f"2026-W{i % n_clusters:02d}",
        })
    return rows


@pytest.fixture
def binary_panel():
    return _obs(binary=True)


@pytest.fixture
def continuous_panel():
    return _obs(binary=False)


def _forecast(panel, kind, **kw):
    target = {"name": f"{kind}_target", "kind": kind, "horizon_days": 5}
    target.update(kw.pop("target_extra", {}))
    params = {"data_cutoff": CUTOFF, "asof": ASOF}
    params.update(kw)
    return M.forecast(target=target, observations=panel, **params)


# =========================================================================== #
# THE OWNERSHIP LAW
# =========================================================================== #
CLINICAL_PROBABILITY_FEATURES = [
    "p_phase3_success",
    "approval_probability",
    "readout_success_prior",
    "ptrs",
    "pos",
    "likelihood_of_approval",
    "hazard_rate_readout",
    "p_pdufa_on_time",
    "phase2_success_prob",
    "prob_of_approval",
    "approval_p",
    "trial_success_likelihood",
]

#: The same owner probabilities written in spreadsheet vocabulary. A screen that
#: only knows the word "probability" stamps every one of these ``lawful``.
RATE_SHAPED_CLINICAL_FEATURES = [
    "phase3_success_rate",
    "historical_approval_rate",
    "crl_rate",
    "expected_approval",
    "trial_win_pct",
    "endpoint_hit_ratio",
    "readout_success_share",
    "approval_frequency",
    "phase2_success_percentage",
    "readout_slip_propensity",
]

LAWFUL_MARKET_FEATURES = [
    "p_up_5d",
    "prob_barrier_hit",
    "drawdown_probability",
    "days_to_pdufa",
    "pdufa_date",
    "clinical_hold_flag",
    "pre_event_runup_20d",
    "realized_vol_20d",
    "vol_regime",
    "issuer_size_bucket",
    # the calendar survives the RATE screen: a date is not a rate
    "expected_readout_date",
    "expected_pdufa_date",
    "days_to_next_adcom",
    "readout_window_month",
]


@pytest.mark.parametrize("name", CLINICAL_PROBABILITY_FEATURES)
def test_clinical_probability_feature_is_refused_by_name(name):
    """A raw clinical/regulatory probability may never be a Seasonality feature.

    BioCatalyst owns event occurrence/timing and event outcome. This is the
    single test the ownership law exists for.
    """
    verdict = M.classify_feature(name)
    assert verdict["is_owner_probability"] is True, f"{name} slipped through the screen"
    assert verdict["owner"] == "biocatalyst"
    assert verdict["family"] in ("event_occurrence_timing", "event_outcome")

    with pytest.raises(M.OwnerProbabilityFeatureError) as exc:
        M.require_lawful_features({name: 0.7, "p_up_5d": 0.3})
    # Refused BY NAME — a refusal that does not say which field is unactionable.
    assert name in str(exc.value)
    assert "biocatalyst" in str(exc.value).lower()


@pytest.mark.parametrize("name", LAWFUL_MARKET_FEATURES)
def test_market_response_and_known_calendar_state_stay_lawful(name):
    """The calendar is lawful; the clinical odds are not.

    A known fact about WHEN a catalyst is scheduled is exactly what a
    market-response model conditions on. Over-refusing it would gut the module.
    """
    verdict = M.classify_feature(name)
    assert verdict["is_owner_probability"] is False, f"{name} was wrongly refused"
    assert verdict["family"] == M.OWNED_FAMILY
    assert M.require_lawful_features({name: 1.0})["refused"] == []


@pytest.mark.parametrize("name", RATE_SHAPED_CLINICAL_FEATURES)
def test_a_clinical_probability_written_as_a_RATE_is_refused_too(name):
    """``phase3_success_rate`` and ``p_phase3_success`` are the same number.

    Only the second one looks like a probability, and a name screen that reads
    only the word "probability" stamps the first one ``lawful`` — which is how an
    approval prior ends up in a market-response feature dict wearing a percent
    sign.
    """
    verdict = M.classify_feature(name)
    assert verdict["is_owner_probability"] is True, f"{name} slipped through the screen"
    assert verdict["owner"] == "biocatalyst"
    with pytest.raises(M.OwnerProbabilityFeatureError) as exc:
        M.require_lawful_features({name: 0.5})
    assert name in str(exc.value)


def test_a_rate_shaped_clinical_feature_never_reaches_a_forecast(binary_panel):
    """The screen runs BEFORE anything is estimated, for rate-shaped names too."""
    with pytest.raises(M.OwnerProbabilityFeatureError):
        _forecast(binary_panel, "binary",
                  features={"phase3_success_rate": 0.62,
                            "historical_approval_rate": 0.41})


@pytest.mark.parametrize("axis", sorted(
    a for axes in R.DISPLAY_ONLY_AXES.values() for a in axes))
def test_a_positioning_or_financing_axis_is_never_a_model_feature(axis):
    """The ceiling regime.py enforces on its axis path binds at the MODEL
    boundary too — otherwise ``short_interest_pct`` is refused as an axis and
    admitted as a feature in the same run."""
    verdict = M.classify_feature(axis)
    assert verdict["is_display_context_only"] is True, f"{axis} was admitted as a feature"
    screen = M.screen_features({axis: 1.0})
    assert screen["lawful"] == []
    assert screen["refused"][0]["reason"] == (
        "positioning_or_financing_axis_is_display_context_only")
    assert screen["context_only"][0]["authority"] == "display_context"
    with pytest.raises(M.OwnerProbabilityFeatureError):
        M.require_lawful_features({axis: 1.0})


def test_the_display_only_list_is_read_from_regime_not_copied():
    """Two copies of a list are two lists that drift."""
    assert M.display_context_axes() == frozenset(
        a for axes in R.DISPLAY_ONLY_AXES.values() for a in axes)


def test_forecast_refuses_an_owner_probability_before_estimating_anything(binary_panel):
    with pytest.raises(M.OwnerProbabilityFeatureError):
        _forecast(binary_panel, "binary", features={"approval_probability": 0.8})


def test_owner_probability_default_is_false_and_this_module_never_flips_it():
    """The flag exists, defaults False, and no call site in the module raises it."""
    sig = inspect.signature(M.forecast)
    assert sig.parameters["allow_owner_probability_feature"].default is False
    assert inspect.signature(M.screen_features).parameters[
        "allow_owner_probability_feature"].default is False
    # AST, not a text scan: the docstrings DESCRIBE the flag, and a grep would
    # either trip on the prose or be loosened until it stopped catching anything.
    tree = ast.parse(MODEL_SOURCE.read_text(encoding="utf-8"))
    flips = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for kw in node.keywords
        if kw.arg == "allow_owner_probability_feature"
        and isinstance(kw.value, ast.Constant) and kw.value.value is True
    ]
    assert not flips, "this module must never flip the owner-probability lock for itself"


def _owner_artifact(name="approval_probability", **over):
    """A fully well-formed owner artifact: versioned, calibrated, read-only, and
    carrying a preregistration that NAMES this exact feature."""
    envelope = {
        "owner": "biocatalyst", "artifact_version": "v3",
        "calibration_version": "cal-v2", "preregistration_id": "PREREG-77",
        "preregistration_features": [name], "read_only": True,
    }
    envelope.update(over)
    return envelope


def test_owner_probability_needs_a_wellformed_artifact_even_when_allowed():
    """The flag lowers a lock; it does not remove the wall."""
    # allowed, but the artifact is not versioned/calibrated/read-only/preregistered
    screen = M.screen_features(
        {"approval_probability": 0.7},
        allow_owner_probability_feature=True,
        owner_artifacts={"approval_probability": {"owner": "biocatalyst"}},
    )
    assert screen["refused"], "a malformed owner artifact must still be refused"
    assert screen["refused"][0]["reason"] == "owner_artifact_malformed"
    assert "missing:artifact_version" in screen["refused"][0]["artifact_defects"]

    ok = M.screen_features(
        {"approval_probability": 0.7},
        allow_owner_probability_feature=True,
        owner_artifacts={"approval_probability": _owner_artifact()},
    )
    assert ok["refused"] == []
    assert ok["admitted_owner_probability"][0]["name"] == "approval_probability"


def test_the_preregistration_must_NAME_the_feature_not_merely_exist():
    """"A preregistration naming it" is a MEMBERSHIP test.

    A non-blank ``preregistration_id`` names nothing: ``"-"`` used to satisfy the
    check, which is the hole ``regime.interaction_eligibility`` closes by testing
    ``primary_interactions``. The same standard applies here.
    """
    # an id that names nothing
    weak = M.screen_features(
        {"approval_probability": 0.7},
        allow_owner_probability_feature=True,
        owner_artifacts={"approval_probability": _owner_artifact(
            preregistration_id="-", preregistration_features=None)},
    )
    assert weak["refused"], "an id with no named features is not a preregistration"
    assert "missing:preregistration_features" in weak["refused"][0]["artifact_defects"]

    # a real preregistration that names a DIFFERENT feature
    wrong = M.screen_features(
        {"approval_probability": 0.7},
        allow_owner_probability_feature=True,
        owner_artifacts={"approval_probability": _owner_artifact(
            preregistration_features=["ptrs"])},
    )
    assert wrong["refused"]
    assert ("preregistration_does_not_name:approval_probability"
            in wrong["refused"][0]["artifact_defects"])


def test_a_wellformed_owner_artifact_is_context_only_while_the_flag_is_down():
    """Display/context is the DEFAULT authority for an owner probability."""
    screen = M.screen_features(
        {"approval_probability": 0.7},
        owner_artifacts={"approval_probability": _owner_artifact()},
    )
    assert screen["refused"], "still refused as a FEATURE"
    assert screen["refused"][0]["reason"] == (
        "owner_probability_as_feature_requires_preregistration")
    assert screen["context_only"][0]["authority"] == "display_context"
    # and the refusal is BINDING on every entry point that estimates anything —
    # the context listing is readable from screen_features and nowhere else.
    with pytest.raises(M.OwnerProbabilityFeatureError):
        M.require_lawful_features(
            {"approval_probability": 0.7},
            owner_artifacts={"approval_probability": _owner_artifact()})


def test_this_module_estimates_no_hazard_and_no_approval_probability():
    """Structural: no public entry point named for owner family 1 or 2."""
    forbidden = re.compile(r"hazard|approval|readout_success|time_to_event", re.I)
    public = [n for n in dir(M) if not n.startswith("_") and callable(getattr(M, n))]
    assert not [n for n in public if forbidden.search(n)]


# =========================================================================== #
# TYPED TARGETS — both directions, so neither assertion is vacuous
# =========================================================================== #
def _has_key(payload, key):
    """Recursive key search — a forced probability nested three levels down is
    still a forced probability."""
    if isinstance(payload, dict):
        if key in payload:
            return True
        return any(_has_key(v, key) for v in payload.values())
    if isinstance(payload, (list, tuple)):
        return any(_has_key(v, key) for v in payload)
    return False


def test_binary_target_returns_a_probability(binary_panel):
    """The positive half of the pair below. Without it, the 'continuous has no
    probability key' test would pass on a module that never emits one at all."""
    out = _forecast(binary_panel, "binary")
    assert out["abstained"] is False
    assert out["kind"] == "probability"
    assert "probability" in out
    assert out["probability"] == out["value"]
    assert 0.0 <= out["value"] <= 1.0


@pytest.mark.parametrize("kind", ["continuous", "distributional"])
def test_continuous_target_returns_no_probability_field(continuous_panel, kind):
    """A continuous target has no probability interpretation, so it never gets a
    probability field — not at the top level and not nested anywhere."""
    out = _forecast(continuous_panel, kind)
    assert out["abstained"] is False
    assert out["kind"] in ("expectation", "quantiles", "distribution")
    assert "probability" not in out
    assert not _has_key(out, "probability"), "a probability leaked into a continuous payload"


def test_target_kinds_map_to_declared_output_kinds(binary_panel, continuous_panel):
    assert _forecast(binary_panel, "binary")["kind"] in M.TARGET_KIND_OUTPUTS["binary"]
    assert _forecast(continuous_panel, "continuous")["kind"] in (
        M.TARGET_KIND_OUTPUTS["continuous"])
    for form in M.TARGET_KIND_OUTPUTS["distributional"]:
        out = _forecast(continuous_panel, "distributional",
                        target_extra={"form": form})
        assert out["kind"] == form


def test_unknown_target_kind_raises(binary_panel):
    with pytest.raises(M.TargetKindError):
        _forecast(binary_panel, "vibes")


def test_distributional_output_carries_quantiles_and_an_edge_per_quantile(continuous_panel):
    out = _forecast(continuous_panel, "distributional")
    assert set(out["quantiles"]) == set(out["baseline"]) == set(out["edge"])
    qs = [out["quantiles"][k] for k in sorted(out["quantiles"], key=float)]
    assert qs == sorted(qs), "quantiles must be monotone in the level"


def test_a_borrowed_shape_reports_NO_edge_rather_than_a_structural_zero(continuous_panel):
    """When the cell borrows the pooled shape, cell-minus-pool is exactly 0.0 at
    every quantile BY CONSTRUCTION. Printing that as ``edge`` reads as a measured
    "no edge" — a null the data never produced."""
    out = _forecast(continuous_panel, "distributional", cell=NARROW_CELL,
                    target_extra={"form": "distribution"})
    assert out["uncertainty"]["outcome_quantiles"]["borrowed_from_pool"] is True
    assert out["edge"] is None
    assert "zero by construction" in out["edge_note"]
    # and the sample under `distribution` is the SAME one the quantiles came from
    dist = out["distribution"]
    assert dist["borrowed_from_pool"] is True
    assert dist["basis"] == "pooled_sample"
    assert dist["n"] == out["n_obs"] != dist["n_cell_obs"]
    assert len(dist["samples"]) == dist["n"]
    # the quantiles really are quantiles OF THIS sample
    assert min(dist["samples"]) <= out["quantiles"]["0.05"] <= max(dist["samples"])
    assert out["quantiles"]["0.5"] == pytest.approx(
        M._quantile(dist["samples"], 0.5))


# =========================================================================== #
# UNCERTAINTY SEMANTICS
# =========================================================================== #
#: Hard-coded, NOT read from the module. The parametrized test below reads
#: ``M.FORBIDDEN_UNCERTAINTY_LABELS``, so deleting a word from that constant
#: deletes the test case instead of failing it — the collection count drops and
#: the suite stays green. This list is the membership assertion that makes the
#: blocklist non-shrinkable.
MUST_BE_FORBIDDEN = {
    "interval", "ci", "band", "bands", "range", "bounds", "error", "error_bar",
    "uncertainty", "conf", "confidence", "spread",
}

#: Same shape of defect on the positive list: a parametrized test sourced from
#: ``UNCERTAINTY_SEMANTICS`` cannot notice a semantics being REMOVED.
MUST_BE_NAMED_SEMANTICS = ("parameter_ci", "predictive_interval", "outcome_quantiles")


def test_the_forbidden_label_list_may_never_shrink():
    """The blocklist test below is parametrized FROM the blocklist.

    Removing ``interval`` from ``FORBIDDEN_UNCERTAINTY_LABELS`` drops a test case
    rather than failing one, so the narrowing is invisible. This assertion is the
    one that fails.
    """
    missing = MUST_BE_FORBIDDEN - set(M.FORBIDDEN_UNCERTAINTY_LABELS)
    assert not missing, f"the banned-uncertainty-label list lost {sorted(missing)}"


def test_the_named_semantics_are_exactly_these_three():
    assert tuple(M.UNCERTAINTY_SEMANTICS) == MUST_BE_NAMED_SEMANTICS


def test_a_bare_interval_raises_by_hand_not_by_parametrization():
    """Hard-coded on purpose: this case survives any edit to the constants."""
    with pytest.raises(M.UncertaintySemanticsError):
        M.make_uncertainty("interval", lo=0.1, hi=0.2)
    with pytest.raises(M.UncertaintySemanticsError):
        M.make_uncertainty("ci", lo=0.1, hi=0.2)
    with pytest.raises(M.UncertaintySemanticsError):
        M.make_uncertainty("confidence", lo=0.1, hi=0.2)


@pytest.mark.parametrize("label", sorted(MUST_BE_FORBIDDEN))
def test_generic_uncertainty_label_raises(label):
    """`interval` and its siblings name NOTHING."""
    with pytest.raises(M.UncertaintySemanticsError) as exc:
        M.make_uncertainty(label, lo=0.1, hi=0.2)
    assert "parameter_ci" in str(exc.value)


def test_generic_uncertainty_key_raises_in_a_block():
    with pytest.raises(M.UncertaintySemanticsError):
        M.validate_uncertainty({"interval": {"semantics": "interval", "lo": 0, "hi": 1}})


def test_uncertainty_key_and_payload_must_agree():
    with pytest.raises(M.UncertaintySemanticsError):
        M.validate_uncertainty({"parameter_ci": {"semantics": "predictive_interval"}})


@pytest.mark.parametrize("semantics", MUST_BE_NAMED_SEMANTICS)
def test_named_uncertainty_semantics_are_accepted(semantics):
    payload = M.make_uncertainty(semantics, lo=0.1, hi=0.2)
    assert payload["semantics"] == semantics
    assert M.validate_uncertainty({semantics: payload})


def test_every_emitted_uncertainty_names_its_semantics(binary_panel, continuous_panel):
    for out in (_forecast(binary_panel, "binary"),
                _forecast(continuous_panel, "continuous"),
                _forecast(continuous_panel, "distributional")):
        assert out["uncertainty"], "an output with no uncertainty block is not honest"
        for key, payload in out["uncertainty"].items():
            assert key in M.UNCERTAINTY_SEMANTICS
            assert payload["semantics"] == key


def test_predictive_interval_is_wider_than_the_parameter_ci(continuous_panel):
    """The two are not interchangeable, and the test pins WHICH is wider."""
    out = _forecast(continuous_panel, "continuous")
    ci = out["uncertainty"]["parameter_ci"]
    pi = out["uncertainty"]["predictive_interval"]
    assert (pi["hi"] - pi["lo"]) > (ci["hi"] - ci["lo"])


def test_unsupported_confidence_level_raises(binary_panel):
    with pytest.raises(M.SeasonalityModelError):
        _forecast(binary_panel, "binary", ci_level=0.877)


# =========================================================================== #
# SHADOW TIER — binding on every artifact including abstentions
# =========================================================================== #
def test_every_model_artifact_carries_shadow_tier(binary_panel, continuous_panel):
    """The forward ledger has 28 registrations and ZERO matured grades. Nothing
    here is promoted and no availability flag moves."""
    payloads = [
        _forecast(binary_panel, "binary"),
        _forecast(continuous_panel, "continuous"),
        _forecast(continuous_panel, "distributional"),
        _forecast([], "binary"),                                    # abstention
        _forecast(binary_panel, "binary", asof=date(2027, 6, 20)),  # abstention
        M.screen_features({"p_up_5d": 1.0}),
    ]
    for payload in payloads:
        assert payload["tier"] == "shadow", payload.get("reason")
    assert M.TIER == "shadow"


def test_regime_artifacts_carry_shadow_tier():
    ctx = R.read_regime_context(
        {"vol_regime": {"value": "high", "known_at": "2026-06-01"}}, asof=ASOF)
    assert ctx["tier"] == "shadow"
    assert R.interaction_eligibility("vol_regime", None)["tier"] == "shadow"
    assert R.TIER == "shadow"


# =========================================================================== #
# BASELINES ARE ALWAYS VISIBLE
# =========================================================================== #
def test_baselines_are_returned_and_a_challenger_never_replaces_them(binary_panel):
    plain = _forecast(binary_panel, "binary")
    challenged = _forecast(binary_panel, "binary",
                           challenger={"name": "gbm_v2", "value": 0.71})
    for out in (plain, challenged):
        assert set(out["baselines"]) >= {
            "empirical_pooled", "empirical_cell", "shrunk_cell", "grand",
            "declared_benchmark", "benchmark_value", "ladder"}
    # The challenger is reported ALONGSIDE, and the baselines are byte-identical.
    assert plain["baselines"]["empirical_pooled"] == challenged["baselines"]["empirical_pooled"]
    assert plain["baselines"]["grand"] == challenged["baselines"]["grand"]
    assert plain["challenger"] is None
    assert challenged["challenger"]["name"] == "gbm_v2"
    assert challenged["challenger"]["vs_declared_benchmark"] == pytest.approx(
        0.71 - challenged["baselines"]["benchmark_value"])
    # and the headline value is still the transparent baseline, not the challenger
    assert challenged["value"] == plain["value"]


def test_edge_is_value_minus_the_declared_benchmark(binary_panel):
    out = _forecast(binary_panel, "binary")
    assert out["edge"] == pytest.approx(out["value"] - out["baseline"])
    assert out["baseline"] == pytest.approx(out["baselines"]["benchmark_value"])
    assert out["declared_benchmark"] in M.BENCHMARKS


def test_there_is_no_pick_the_best_baseline_path(binary_panel):
    with pytest.raises(M.SeasonalityModelError):
        _forecast(binary_panel, "binary", declared_benchmark="whichever_wins")


# =========================================================================== #
# HIERARCHICAL POOLING
# =========================================================================== #
def test_pooling_ladder_is_returned_in_full(binary_panel):
    pool = M.hierarchical_pooling(binary_panel)
    assert list(pool["levels"]) == list(M.POOLING_LEVELS)
    for level in M.POOLING_LEVELS:
        for cell in pool["levels"][level].values():
            assert {"raw", "n", "n_eff", "weight", "parent", "shrunk"} <= set(cell)


def test_shrinkage_pulls_a_thin_cell_toward_its_parent():
    """A thin cell must not outvote its parent — that is the whole point."""
    thin = M.shrunk_baseline([1.0, 1.0], parent=0.4, shrinkage_k=24.0, n_eff=2.0)
    fat = M.shrunk_baseline([1.0] * 500, parent=0.4, shrinkage_k=24.0, n_eff=500.0)
    assert thin["value"] < 0.5, "a 2-observation cell moved the estimate too far"
    assert fat["value"] > 0.9, "a 500-observation cell should dominate its parent"
    assert thin["weight"] < fat["weight"]


def test_shrinkage_runs_on_effective_n_not_row_count():
    """100 rows inside one week are one macro draw. Passing the row count would
    let a single busy week outvote the parent."""
    by_rows = M.shrunk_baseline([1.0] * 100, parent=0.3, n_eff=100.0)
    by_clusters = M.shrunk_baseline([1.0] * 100, parent=0.3, n_eff=1.0)
    assert by_clusters["value"] < by_rows["value"]


def test_effective_sample_size_collapses_to_clusters_at_icc_one():
    assert M.effective_sample_size(200, 40, icc=1.0) == pytest.approx(40.0)
    assert M.effective_sample_size(200, 40, icc=0.0) == pytest.approx(200.0)
    assert M.effective_sample_size(0, 10) == 0.0


def test_forecast_reports_effective_n_as_clusters_by_default(binary_panel):
    out = _forecast(binary_panel, "binary")
    assert out["effective_n"] == pytest.approx(float(out["n_date_clusters"]))
    assert out["n_obs"] == len(binary_panel)
    assert out["icc"] == 1.0


# =========================================================================== #
# PROVENANCE ON EVERY PAYLOAD
# =========================================================================== #
REQUIRED_PROVENANCE = {
    "effective_n", "n_issuers", "n_date_clusters", "extrapolation",
    "calibration_version", "model_version", "data_cutoff", "asof",
    "abstained", "reason", "tier", "schema", "build_floors",
}


def test_every_payload_carries_the_full_provenance_block(binary_panel, continuous_panel):
    payloads = [
        _forecast(binary_panel, "binary"),
        _forecast(continuous_panel, "continuous"),
        _forecast(continuous_panel, "distributional"),
        _forecast([], "binary"),
        _forecast(_obs(n=40, n_clusters=5), "binary"),
        _forecast(binary_panel, "binary", asof=date(2027, 1, 1)),
    ]
    for payload in payloads:
        missing = REQUIRED_PROVENANCE - set(payload)
        assert not missing, f"payload missing {missing}: reason={payload.get('reason')}"
        assert payload["model_version"] == M.MODEL_VERSION
        assert payload["data_cutoff"] == CUTOFF.isoformat()


def test_uncalibrated_is_a_visible_null_not_a_placeholder(binary_panel):
    out = _forecast(binary_panel, "binary")
    assert out["calibration_version"] == M.UNCALIBRATED_VERSION == "uncalibrated-v0"
    stamped = _forecast(binary_panel, "binary", calibration_version="cal-2026-08")
    assert stamped["calibration_version"] == "cal-2026-08"


# =========================================================================== #
# ABSTENTIONS — named, never a number
# =========================================================================== #
def test_no_observations_abstains(binary_panel):
    out = _forecast([], "binary")
    assert out["abstained"] is True
    assert out["reason"] == M.ABSTAIN_NO_OBSERVATIONS
    assert out["value"] is None and out["kind"] is None


def test_thin_effective_n_abstains():
    """240 rows crammed into 5 clusters is 5 independent observations."""
    out = _forecast(_obs(n=240, n_clusters=5), "binary")
    assert out["abstained"] is True
    assert out["reason"] == M.ABSTAIN_THIN_EFFECTIVE_N
    assert "date clusters" in out["detail"]


def test_thin_issuers_abstains():
    out = _forecast(_obs(n=240, n_issuers=4, n_clusters=40), "binary")
    assert out["abstained"] is True
    assert out["reason"] == M.ABSTAIN_THIN_ISSUERS


def test_thin_date_clusters_abstains():
    """With icc=0 the effective-N gate passes on row count, so the DATE CLUSTER
    floor is the one that has to fire — otherwise it is unreachable dead code."""
    out = _forecast(_obs(n=240, n_issuers=20, n_clusters=6), "binary", icc=0.0)
    assert out["abstained"] is True
    assert out["reason"] == M.ABSTAIN_THIN_DATE_CLUSTERS


def test_stale_panel_abstains(binary_panel):
    out = _forecast(binary_panel, "binary", asof=date(2027, 6, 20))
    assert out["abstained"] is True
    assert out["reason"] == M.ABSTAIN_STALE_DATA
    assert out["data_age_days"] > M.MAX_DATA_AGE_DAYS


def test_extrapolation_outside_declared_support_abstains(binary_panel):
    out = _forecast(binary_panel, "binary",
                    features={"pre_event_runup_20d": 0.9},
                    support={"pre_event_runup_20d": (-0.3, 0.3)})
    assert out["abstained"] is True
    assert out["reason"] == M.ABSTAIN_EXTRAPOLATIVE
    assert out["extrapolation"]["outside_declared_support"] is True
    assert out["extrapolation"]["outside_features"][0]["feature"] == "pre_event_runup_20d"


def test_inside_declared_support_does_not_abstain(binary_panel):
    out = _forecast(binary_panel, "binary",
                    features={"pre_event_runup_20d": 0.1},
                    support={"pre_event_runup_20d": (-0.3, 0.3)})
    assert out["abstained"] is False
    assert out["extrapolation"]["outside_declared_support"] is False


def test_cell_backoff_is_flagged_but_does_not_abstain(binary_panel):
    """Shrinkage handles an unobserved cell honestly, so it is FLAGGED and the
    forecast proceeds — the flag is the disclosure, not a refusal."""
    out = _forecast(binary_panel, "binary",
                    cell={"therapeutic_class": "onc", "event_type": "pdufa",
                          "issuer": "NOT_IN_PANEL"})
    assert out["abstained"] is False
    assert out["extrapolation"]["cell_backoff"] is True
    assert out["extrapolation"]["flagged"] is True


def test_constant_binary_outcome_is_structurally_broken():
    out = _forecast(_obs(constant=1.0), "binary")
    assert out["abstained"] is True
    assert out["reason"] == M.ABSTAIN_STRUCTURALLY_BROKEN


def test_zero_variance_continuous_outcome_is_structurally_broken():
    out = _forecast(_obs(constant=0.02, binary=False), "continuous")
    assert out["abstained"] is True
    assert out["reason"] == M.ABSTAIN_STRUCTURALLY_BROKEN


def test_non_binary_values_on_a_binary_target_are_unestimable():
    out = _forecast(_obs(binary=False), "binary")
    assert out["abstained"] is True
    assert out["reason"] == M.ABSTAIN_UNESTIMABLE_TARGET


def test_every_abstention_reason_is_a_declared_constant(binary_panel):
    cases = [
        _forecast([], "binary"),
        _forecast(_obs(n=240, n_clusters=5), "binary"),
        _forecast(_obs(n=240, n_issuers=4, n_clusters=40), "binary"),
        _forecast(_obs(n=240, n_issuers=20, n_clusters=6), "binary", icc=0.0),
        _forecast(binary_panel, "binary", asof=date(2027, 6, 20)),
        _forecast(binary_panel, "binary", data_cutoff=date(2026, 12, 31)),
        _forecast(_obs(constant=1.0), "binary"),
        _forecast(_obs(binary=False), "binary"),
    ]
    seen = {c["reason"] for c in cases}
    assert seen <= set(M.ABSTENTION_REASONS)
    assert len(seen) >= 7, "the abstention ladder collapsed onto too few reasons"
    for case in cases:
        assert case["schema"] == M.ABSTENTION_SCHEMA
        assert case["detail"], "an abstention with no detail is not auditable"


def test_a_thin_cell_borrows_its_width_from_the_pool_and_says_so(continuous_panel):
    """A one-row cell has sd 0; a zero-width predictive interval would be a lie."""
    out = _forecast(continuous_panel, "continuous",
                    cell={"therapeutic_class": "onc"},
                    levels=("therapeutic_class",))
    assert out["abstained"] is False
    pi = out["uncertainty"]["predictive_interval"]
    assert pi["hi"] > pi["lo"]
    assert "borrowed_from_pool" in pi


def test_a_panel_that_extends_PAST_the_decision_moment_abstains(binary_panel):
    """Staleness is one-sided by construction, so the lookahead needs its own
    branch: a data_cutoff AFTER asof produced a negative data_age_days that
    nothing read, and the forecast went out on data nobody could have had."""
    out = _forecast(binary_panel, "binary", data_cutoff=date(2026, 12, 31),
                    asof=date(2026, 6, 20))
    assert out["abstained"] is True
    assert out["reason"] == M.ABSTAIN_FUTURE_DATA_CUTOFF
    assert out["value"] is None
    assert out["data_age_days"] < 0
    assert "lookahead" in out["detail"]


# =========================================================================== #
# THE CELL THE PUBLISHED NUMBER ACTUALLY DESCRIBES
# =========================================================================== #
NARROW_CELL = {"therapeutic_class": "onc", "event_type": "pdufa", "issuer": "ISS0"}


def test_the_payload_states_the_size_of_the_cell_it_published(binary_panel):
    """BUILD_FLOORS gate the POOLED panel; ``value`` describes the CELL.

    Those are different samples and the cell is far thinner. Without these keys
    the only disclosed sample size is the pooled one, and a reader cannot tell
    that the interval beside it was computed on two effective observations.
    """
    out = _forecast(binary_panel, "binary", cell=NARROW_CELL)
    assert out["abstained"] is False
    for key in ("n_cell_obs", "effective_n_cell", "n_cell_date_clusters",
                "thin_cell", "cell_floors"):
        assert key in out, f"the payload does not disclose {key}"
    assert out["n_cell_obs"] < out["n_obs"], "the fixture must exercise a narrow cell"
    assert out["cell_floors"]["n_cell_obs"] == out["n_cell_obs"]
    assert out["cell_floors"]["effective_n_cell"] == out["effective_n_cell"]
    # THE binding assertion: the disclosed cell size is the one the interval was
    # actually computed on, not a decorative number next to it.
    assert out["uncertainty"]["parameter_ci"]["n_eff"] == out["effective_n_cell"]


def test_a_cell_below_the_build_floor_is_disclosed_rather_than_advertised_as_gated(
        binary_panel):
    """The floors were applied to the pool. Say so, and say the cell missed them."""
    out = _forecast(binary_panel, "binary", cell=NARROW_CELL)
    assert out["effective_n"] >= M.BUILD_FLOORS["min_effective_n"], "pool clears"
    assert out["effective_n_cell"] < M.BUILD_FLOORS["min_effective_n"], "cell does not"
    assert out["thin_cell"] is True
    assert out["cell_floors"]["meets_build_floors"] is False
    assert out["cell_floors"]["floors_applied_to"] == "pooled_panel"
    # a cell that DOES clear the floor says so too, so the flag is not a constant
    fat = _forecast(binary_panel, "binary", cell={"therapeutic_class": "onc"},
                    levels=("therapeutic_class",), icc=0.0)
    assert fat["thin_cell"] is False
    assert fat["cell_floors"]["meets_build_floors"] is True


REQUIRED_ESTIMATE_KEYS = {"n_cell_obs", "effective_n_cell", "n_cell_date_clusters",
                          "thin_cell", "cell_floors"}


def test_every_estimate_carries_the_cell_disclosure(binary_panel, continuous_panel):
    for out in (_forecast(binary_panel, "binary"),
                _forecast(continuous_panel, "continuous"),
                _forecast(continuous_panel, "distributional")):
        missing = REQUIRED_ESTIMATE_KEYS - set(out)
        assert not missing, f"estimate payload missing {missing}"


# =========================================================================== #
# THE PARAMETER CI DESCRIBES THE ESTIMATOR IT IS PRINTED NEXT TO
# =========================================================================== #
def test_the_binary_parameter_ci_and_the_point_estimate_come_from_ONE_model():
    """The published value is the SHRUNK cell rate.

    ``shrunk_baseline`` is exactly the posterior mean of a Beta prior centred on
    the parent carrying ``shrinkage_k`` pseudo-observations, so the coherent
    interval is that posterior's own. A Wilson interval — derived for an OBSERVED
    proportion — fed the shrunk point but the raw cell's n_eff is centred on one
    estimator and widthed for another, and covers neither.
    """
    out = _forecast(_obs(n=240), "binary", cell=NARROW_CELL)
    ci = out["uncertainty"]["parameter_ci"]
    assert ci["basis"] == "beta_posterior_of_the_shrinkage_prior"
    a, b = ci["posterior_alpha"], ci["posterior_beta"]
    # the posterior MEAN is the number printed as `value` — that is what makes
    # this one model rather than two.
    assert a / (a + b) == pytest.approx(out["value"], abs=1e-6)
    assert ci["lo"] < out["value"] < ci["hi"]
    assert 0.0 <= ci["lo"] < ci["hi"] <= 1.0


def test_the_interval_knows_about_the_prior_the_point_was_shrunk_with():
    """Stronger shrinkage means more prior information, so a NARROWER posterior.

    A Wilson interval on the raw cell's n_eff cannot see ``shrinkage_k`` at all,
    so this relation is the one that separates the two constructions.
    """
    weak = _forecast(_obs(n=240), "binary", cell=NARROW_CELL, shrinkage_k=4.0)
    strong = _forecast(_obs(n=240), "binary", cell=NARROW_CELL, shrinkage_k=240.0)
    w = weak["uncertainty"]["parameter_ci"]
    s = strong["uncertainty"]["parameter_ci"]
    assert (s["hi"] - s["lo"]) < (w["hi"] - w["lo"])


def test_the_unshrunk_cell_rate_is_reported_beside_the_shrunk_one():
    """A reader who wants the CELL's own rate must not have to read a shrunk one
    and guess which estimand the interval covers."""
    out = _forecast(_obs(n=240), "binary", cell=NARROW_CELL)
    ci = out["uncertainty"]["parameter_ci"]
    for key in ("raw_cell_rate", "raw_cell_wilson_lo", "raw_cell_wilson_hi",
                "shrinkage_weight", "prior_parent", "prior_pseudo_observations"):
        assert key in ci, f"the interval does not disclose {key}"
    assert ci["raw_cell_wilson_lo"] < ci["raw_cell_wilson_hi"]
    assert "SHRUNK CELL RATE" in ci["note"]
    # the two estimands really are different on this cell
    assert ci["raw_cell_rate"] != pytest.approx(out["value"], abs=1e-6)


def test_the_continuous_parameter_ci_runs_on_the_shrunken_estimator_too():
    out = _forecast(_obs(n=240, binary=False), "continuous", cell=NARROW_CELL)
    ci = out["uncertainty"]["parameter_ci"]
    assert ci["basis"] == "normal_posterior_on_effective_n_plus_shrinkage_pseudo_obs"
    # the raw cell's own SE is disclosed alongside and is WIDER: the shrunk mean
    # borrows the parent's strength, and pretending otherwise overstates the
    # precision of a number that is mostly parent.
    assert ci["raw_cell_se"] > ci["se"]
    assert "raw_cell_mean" in ci


@pytest.mark.parametrize("x", [0.05, 0.25, 0.5, 0.75, 0.95])
def test_the_incomplete_beta_matches_its_closed_forms(x):
    """Pure-stdlib special function, pinned against arithmetic anyone can check:
    I_x(1,1) = x, I_x(2,1) = x^2, I_x(1,2) = 1-(1-x)^2."""
    assert M._betainc_regularized(x, 1.0, 1.0) == pytest.approx(x, abs=1e-10)
    assert M._betainc_regularized(x, 2.0, 1.0) == pytest.approx(x * x, abs=1e-10)
    assert M._betainc_regularized(x, 1.0, 2.0) == pytest.approx(
        1 - (1 - x) ** 2, abs=1e-10)
    assert M._beta_quantile(x, 1.0, 1.0) == pytest.approx(x, abs=1e-8)
    assert M._beta_quantile(x, 2.0, 1.0) == pytest.approx(math.sqrt(x), abs=1e-8)
    # a symmetric Beta has its median at 0.5, whatever the concentration
    assert M._beta_quantile(0.5, 3.7, 3.7) == pytest.approx(0.5, abs=1e-8)


def test_the_posterior_interval_narrows_as_the_cell_grows():
    thin = M.shrunk_rate_interval(0.6, 4.0, 0.3, 24.0, 0.90)
    fat = M.shrunk_rate_interval(0.6, 400.0, 0.3, 24.0, 0.90)
    assert (fat["hi"] - fat["lo"]) < (thin["hi"] - thin["lo"])
    # and a fat cell's posterior mean has essentially left the parent behind
    assert fat["shrinkage_weight"] > 0.9 and thin["shrinkage_weight"] < 0.2


# =========================================================================== #
# REGIME — no fused scalar, ever
# =========================================================================== #
MULTI_AXIS_RAW = {
    "regime_at_entry": {"value": "risk_on", "known_at": "2026-06-01"},
    "vol_regime": {"value": "high", "known_at": "2026-06-01"},
    "rate_pressure": {"value": "tight", "known_at": "2026-06-01"},
    "xbi_trend_state": {"value": "downtrend", "known_at": "2026-06-01"},
    "issuer_size_bucket": {"value": "smid", "known_at": "2026-06-01"},
}

COMPOSITE_KEY = re.compile(
    r"^(regime_)?(score|composite|fused|rating|index|grade|verdict|reliability)$", re.I)


def test_no_regime_function_returns_a_scalar_combining_axes():
    """DNR:KILL-REGIME-SCORECARD / DNR:KILL-COMPOSITE-REGIME-RELIABILITY-MONITOR /
    DNR:KILL-PER-SIGNAL-FAMILY-RELIABILITY. Checked at RUNTIME on a multi-axis
    input, not by reading the source — renaming a composite does not make it
    lawful, and a source scan is exactly what a rename defeats."""
    coverage = _meter_report({a: _axis_verdict(True) for a in MULTI_AXIS_RAW})
    prereg = {"id": "P1", "version": "1",
              "primary_interactions": [f"market_response_x_{a}" for a in MULTI_AXIS_RAW]}
    returns = [
        R.read_regime_context(MULTI_AXIS_RAW, asof=ASOF),
        R.require_lawful_axes(MULTI_AXIS_RAW, asof=ASOF),
        R.interaction_eligibility("regime_at_entry", coverage, prereg),
        R.conditional_estimate_or_context("regime_at_entry", coverage, prereg,
                                          estimator=lambda: {"beta": 0.1}),
    ]
    for payload in returns:
        assert isinstance(payload, dict), "a regime read must never return a bare number"
        assert not isinstance(payload, numbers.Number)
        for key in payload:
            assert not COMPOSITE_KEY.match(str(key)), f"composite-looking key {key!r}"


def test_read_regime_context_keeps_every_axis_separate():
    ctx = R.read_regime_context(MULTI_AXIS_RAW, asof=ASOF)
    assert set(ctx["axes"]) == set(MULTI_AXIS_RAW)
    # Each axis is its own entry with its own family and provenance; there is no
    # cross-axis aggregate anywhere in the payload.
    for axis, entry in ctx["axes"].items():
        assert entry["axis"] == axis
        assert entry["family"] in set(R.AUTHORIZED_AXES) | set(R.DISPLAY_ONLY_AXES)
        assert entry["pit_adapter"]
    numeric_scalars = [v for v in ctx.values() if isinstance(v, float)]
    assert not numeric_scalars, f"unexpected scalar in a regime context: {numeric_scalars}"


def test_no_public_regime_callable_returns_a_number():
    """RUNTIME, not a name scan.

    A name scan is exactly what a rename defeats — which is the failure the
    module docstring names — so every public callable is INVOKED with a
    multi-axis input and its return asserted to be a per-axis mapping, never a
    scalar.
    """
    coverage = _meter_report({a: _axis_verdict(True) for a in MULTI_AXIS_RAW})
    prereg = {"id": "P1", "version": "1", "registered_at": "2026-05-01",
              "primary_interactions": [f"market_response_x_{a}" for a in MULTI_AXIS_RAW]}
    axis = "regime_at_entry"
    # Every public callable, with the arguments that make it do its most
    # composite-looking work.
    calls = {
        "read_regime_context": lambda: R.read_regime_context(MULTI_AXIS_RAW, asof=ASOF),
        "require_lawful_axes": lambda: R.require_lawful_axes(MULTI_AXIS_RAW, asof=ASOF),
        "axis_family": lambda: R.axis_family(axis),
        "axis_authority": lambda: R.axis_authority(axis),
        "interaction_eligibility": lambda: R.interaction_eligibility(axis, coverage, prereg),
        "conditional_estimate_or_context": lambda: R.conditional_estimate_or_context(
            axis, coverage, prereg, estimator=lambda: {"beta": 0.1},
            context={"value": "risk_on"}),
        "coverage_report_defects": lambda: R.coverage_report_defects(coverage),
        "assess_axis_coverage": None,  # needs pandas; covered by its own test
    }
    probed = set()
    for name in dir(R):
        if name.startswith("_"):
            continue
        obj = getattr(R, name)
        if not callable(obj) or inspect.isclass(obj):
            continue
        if getattr(obj, "__module__", R.__name__) != R.__name__:
            continue  # typing/stdlib re-exports, not this module's surface
        assert name in calls, (
            f"{name} is a new public regime callable with no runtime probe — add one, "
            "because a source scan is what a rename defeats")
        if calls[name] is None:
            continue
        result = calls[name]()
        probed.add(name)
        assert not isinstance(result, numbers.Number), (
            f"{name} returned a bare number on a multi-axis input")
        if isinstance(result, dict):
            for key, value in result.items():
                assert not (COMPOSITE_KEY.match(str(key))
                            and isinstance(value, numbers.Number)), (
                    f"{name} returned a composite-looking scalar {key!r}")
    assert len(probed) >= 6, "the probe stopped exercising the module"


def test_an_unauthorized_axis_never_passes_the_interaction_gate():
    """The allowlist is an allowlist, not a denylist of positioning keys.

    An invented axis has ``axis_authority() is None``: it is neither
    display-context nor authorized, and falling through to "conditionable" is how
    ``regime_composite_v2`` becomes eligible for an interaction estimate.
    """
    axis = "regime_composite_v2"
    assert R.axis_authority(axis) is None
    gate = R.interaction_eligibility(
        axis, _coverage(axis, True),
        {"id": "P", "primary_interactions": [f"market_response_x_{axis}"]})
    assert gate["eligible"] is False
    assert gate["reason"] == R.ABSTAIN_AXIS_UNAUTHORIZED
    out = R.conditional_estimate_or_context(
        axis, _coverage(axis, True),
        {"id": "P", "primary_interactions": [f"market_response_x_{axis}"]},
        estimator=lambda: {"beta": 0.1})
    assert out["abstained"] is True and out["estimate"] is None


def test_a_hand_written_coverage_report_is_refused():
    """The gate binds on the METER's report, not on a caller's assertion.

    ``{"status": "ok", "axes": {"vol_regime": {"estimable": True}}}`` is four
    keystrokes and it used to open the gate.
    """
    axis = "regime_at_entry"
    prereg = {"id": "P", "primary_interactions": [f"market_response_x_{axis}"]}
    stub = {"status": "ok", "axes": {axis: {"estimable": True, "verdict": "estimable"}}}
    gate = R.interaction_eligibility(axis, stub, prereg)
    assert gate["eligible"] is False
    assert gate["reason"] == R.ABSTAIN_COVERAGE_NOT_FROM_METER
    assert gate["coverage_report_defects"]

    # a report with the right envelope but a bare per-axis verdict is refused too
    half = _meter_report({axis: {"estimable": True, "verdict": "estimable"}})
    gate = R.interaction_eligibility(axis, half, prereg)
    assert gate["eligible"] is False
    assert gate["reason"] == R.ABSTAIN_COVERAGE_NOT_FROM_METER

    # ...and so is the mirror image: real per-axis verdicts copied out of a real
    # report, wrapped in an envelope that never came from the meter. Without this
    # case the two provenance checks cover for each other and either one can be
    # deleted with the suite green.
    no_gates = _meter_report({axis: _axis_verdict(True)})
    no_gates.pop("gates")
    gate = R.interaction_eligibility(axis, no_gates, prereg)
    assert gate["eligible"] is False
    assert gate["reason"] == R.ABSTAIN_COVERAGE_NOT_FROM_METER
    assert any("gates" in d for d in gate["coverage_report_defects"])


def test_the_real_house_meter_passes_the_provenance_check():
    """The other half of the pair above: the check must ACCEPT the real meter.

    Without this, tightening the marker list would silently make every real
    report unusable and the suite would still be green.
    """
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame({
        "date": pd.date_range("2020-01-31", periods=60, freq="ME"),
        "regime_at_entry": ["risk_on", "risk_off"] * 30,
    })
    report = R.assess_axis_coverage(frame, "regime_at_entry")
    assert R.coverage_report_defects(report) == []
    gate = R.interaction_eligibility(
        "regime_at_entry", report,
        {"id": "P", "primary_interactions": ["market_response_x_regime_at_entry"]})
    assert gate["eligible"] is True, gate.get("detail")


def test_an_estimator_that_returns_a_fused_scalar_is_refused():
    """The gate authorizes an interaction on ONE axis.

    It does not constrain what the estimator computes, so the estimate is
    screened on the way out — otherwise the one lawful door hands back exactly
    the composite regime verdict DNR:KILL-REGIME-SCORECARD forbids.
    """
    axis = "regime_at_entry"
    prereg = {"id": "P", "primary_interactions": [f"market_response_x_{axis}"]}
    with pytest.raises(R.RegimeFeatureError) as exc:
        R.conditional_estimate_or_context(
            axis, _coverage(axis, True), prereg,
            estimator=lambda: {"fused_score": 0.71})
    assert "fusion" in str(exc.value).lower()
    assert "KILL-REGIME-SCORECARD" in str(exc.value)

    # a per-axis estimate that DECLARES several axes as its inputs is the same
    # fusion with the scalar renamed
    with pytest.raises(R.RegimeFeatureError):
        R.conditional_estimate_or_context(
            axis, _coverage(axis, True), prereg,
            estimator=lambda: {"beta": 0.71,
                               "axes": ["vol_regime", "dealer_gamma_state",
                                        "short_interest_pct", "rate_pressure"]})

    # and the lawful single-axis estimate still comes back
    ok = R.conditional_estimate_or_context(
        axis, _coverage(axis, True), prereg,
        estimator=lambda: {"beta": 0.42, "axes": [axis]})
    assert ok["abstained"] is False
    assert ok["estimate"]["beta"] == 0.42


def test_a_stale_or_undated_preregistration_is_refused_when_asof_is_supplied():
    """"Fresh" was in the docstring and nowhere in the code: a preregistration
    written years earlier passed identically to one written last month."""
    axis = "regime_at_entry"
    name = f"market_response_x_{axis}"
    fresh = {"id": "P", "registered_at": "2026-05-01", "primary_interactions": [name]}
    stale = {"id": "P", "registered_at": "2019-01-01", "primary_interactions": [name]}
    undated = {"id": "P", "primary_interactions": [name]}

    ok = R.interaction_eligibility(axis, _coverage(axis, True), fresh, asof=ASOF)
    assert ok["eligible"] is True
    assert ok["preregistration_freshness"].startswith("fresh:")

    old = R.interaction_eligibility(axis, _coverage(axis, True), stale, asof=ASOF)
    assert old["eligible"] is False
    assert old["reason"] == R.ABSTAIN_PREREGISTRATION_STALE

    none = R.interaction_eligibility(axis, _coverage(axis, True), undated, asof=ASOF)
    assert none["eligible"] is False
    assert none["reason"] == R.ABSTAIN_PREREGISTRATION_UNDATED

    after = R.interaction_eligibility(
        axis, _coverage(axis, True),
        {"id": "P", "registered_at": "2026-12-01", "primary_interactions": [name]},
        asof=ASOF)
    assert after["eligible"] is False
    assert after["reason"] == R.ABSTAIN_PREREGISTRATION_STALE


def test_freshness_is_reported_as_NOT_CHECKED_when_there_is_no_asof():
    """Freshness has no meaning without a decision moment to be fresh AT, so the
    payload says the check did not run rather than implying it passed."""
    axis = "regime_at_entry"
    gate = R.interaction_eligibility(
        axis, _coverage(axis, True),
        {"id": "P", "registered_at": "2001-01-01",
         "primary_interactions": [f"market_response_x_{axis}"]})
    assert gate["eligible"] is True
    assert gate["preregistration_freshness"] == "not_checked:no_asof_supplied"


def test_positioning_and_financing_stay_display_context_only():
    for family, axes in R.DISPLAY_ONLY_AXES.items():
        for axis in axes:
            assert R.axis_authority(axis) == R.DISPLAY_CONTEXT
            # A VALID coverage report and a naming preregistration: the
            # display/context ceiling still wins.
            gate = R.interaction_eligibility(
                axis, _coverage(axis, True),
                {"primary_interactions": [f"market_response_x_{axis}"]})
            assert gate["eligible"] is False
            assert gate["reason"] == R.ABSTAIN_AXIS_DISPLAY_ONLY


def test_unauthorized_axis_is_refused_by_name():
    ctx = R.read_regime_context(
        {"p_approval": {"value": 0.7, "known_at": "2026-06-01"},
         "my_new_alpha_factor": {"value": 1.0, "known_at": "2026-06-01"}}, asof=ASOF)
    assert {r["axis"] for r in ctx["refused"]} == {"p_approval", "my_new_alpha_factor"}
    assert all(r["reason"] == R.REFUSE_UNAUTHORIZED for r in ctx["refused"])
    with pytest.raises(R.RegimeFeatureError) as exc:
        R.require_lawful_axes({"p_approval": {"value": 0.7, "known_at": "2026-06-01"}},
                              asof=ASOF)
    assert "p_approval" in str(exc.value)


def test_a_value_not_knowable_at_asof_is_refused():
    """A regime read stamped after the decision produces a plausible conditional
    table that could never have been acted on."""
    ctx = R.read_regime_context(
        {"vol_regime": {"value": "high", "known_at": "2026-06-30"}}, asof=ASOF)
    assert ctx["axes"] == {}
    assert ctx["refused"][0]["reason"] == R.REFUSE_NOT_PIT


def test_axis_without_a_reviewed_pit_adapter_is_refused():
    ctx = R.read_regime_context(
        {"vol_regime": {"value": "high", "known_at": "2026-06-01"}},
        asof=ASOF, adapters={})
    assert ctx["refused"][0]["reason"] == R.REFUSE_NO_ADAPTER


# =========================================================================== #
# REGIME — the interaction gate, BOTH paths
# =========================================================================== #
def _axis_verdict(estimable, verdict="estimable"):
    """One per-axis verdict shaped like the house meter's."""
    return {
        "axis": "x", "estimable": estimable, "verdict": verdict,
        "reason": "3 states, thinnest spans 41 months" if estimable
                  else "only one state observed",
        "coverage": 0.99, "n_states": 3 if estimable else 1,
        "min_state_months": 41 if estimable else 2,
        "n_rows_total": 600, "n_rows_stamped": 594, "months_total": 60,
    }


def _meter_report(axes):
    """A coverage report carrying the provenance ``assess()`` stamps.

    The gate refuses a hand-written ``{"status": "ok", "axes": {...}}`` (see
    ``test_a_hand_written_coverage_report_is_refused``), so the fixtures have to
    look like the meter's own output — and
    ``test_the_real_house_meter_passes_the_provenance_check`` pins this shape
    against the real ``assess()`` so the two cannot drift apart.
    """
    return {
        "axes": dict(axes),
        "estimable_axes": [a for a, r in axes.items() if r["estimable"]],
        "any_estimable": any(r["estimable"] for r in axes.values()),
        "n_rows": 600,
        "status": "ok",
        "gates": {"min_coverage": 0.8, "min_states": 2, "min_months_per_state": 18},
        "note": "months, not rows, are the independent unit",
    }


def _coverage(axis, estimable, verdict="estimable"):
    return _meter_report({axis: _axis_verdict(estimable, verdict)})


def test_interaction_eligible_only_when_estimable_and_preregistered():
    axis = "regime_at_entry"
    name = f"market_response_x_{axis}"
    prereg = {"id": "PREREG-9", "version": "2", "primary_interactions": [name]}
    gate = R.interaction_eligibility(axis, _coverage(axis, True), prereg)
    assert gate["eligible"] is True
    assert gate["reason"] is None
    assert gate["preregistration_id"] == "PREREG-9"
    assert gate["coverage_verdict"] == "estimable"


def test_interaction_abstains_when_the_axis_is_not_estimable():
    axis = "vol_regime"
    prereg = {"id": "P", "primary_interactions": [f"market_response_x_{axis}"]}
    gate = R.interaction_eligibility(axis, _coverage(axis, False, "single_state"), prereg)
    assert gate["eligible"] is False
    assert gate["reason"] == R.ABSTAIN_AXIS_NOT_ESTIMABLE
    assert "single_state" in gate["detail"]


def test_interaction_abstains_when_no_preregistration_names_it():
    axis = "regime_at_entry"
    for prereg in (None, {}, {"primary_interactions": ["market_response_x_vol_regime"]}):
        gate = R.interaction_eligibility(axis, _coverage(axis, True), prereg)
        assert gate["eligible"] is False
        assert gate["reason"] == R.ABSTAIN_NO_PREREGISTRATION


def test_a_sibling_axis_being_estimable_says_nothing_about_this_one():
    """The gate binds on THAT EXACT AXIS."""
    prereg = {"primary_interactions": ["market_response_x_vol_regime"]}
    gate = R.interaction_eligibility("vol_regime", _coverage("regime_at_entry", True),
                                     prereg)
    assert gate["eligible"] is False
    assert gate["reason"] == R.ABSTAIN_AXIS_NOT_IN_REPORT


def test_missing_coverage_report_is_treated_as_not_estimable():
    for report in (None, {}, {"status": "unavailable"}):
        gate = R.interaction_eligibility("regime_at_entry", report,
                                         {"primary_interactions":
                                          ["market_response_x_regime_at_entry"]})
        assert gate["eligible"] is False
        assert gate["reason"] == R.ABSTAIN_COVERAGE_UNAVAILABLE


def test_ineligible_path_shows_context_and_never_builds_the_estimate():
    """The estimator is a zero-arg callable so the ineligible path cannot even
    compute a number that would then have to be discarded."""
    calls = []

    def estimator():
        calls.append(1)
        return {"beta": 0.42}

    out = R.conditional_estimate_or_context(
        "vol_regime", _coverage("vol_regime", False, "single_state"),
        {"primary_interactions": ["market_response_x_vol_regime"]},
        estimator=estimator, context={"value": "high"})
    assert out["abstained"] is True
    assert out["estimate"] is None
    assert out["context"] == {"value": "high"}
    assert out["reason"] == R.ABSTAIN_AXIS_NOT_ESTIMABLE
    assert calls == [], "the estimator ran on the ineligible path"


def test_eligible_path_runs_the_estimator():
    axis = "regime_at_entry"
    out = R.conditional_estimate_or_context(
        axis, _coverage(axis, True),
        {"id": "P", "primary_interactions": [f"market_response_x_{axis}"]},
        estimator=lambda: {"beta": 0.42})
    assert out["abstained"] is False
    assert out["estimate"] == {"beta": 0.42}


def test_governing_kills_are_cited_by_key_not_by_row_number():
    """Registry row numbers shift on every append; keys do not."""
    for key in R.GOVERNING_KILLS:
        assert key.startswith("DNR:KILL-")
    source = REGIME_SOURCE.read_text(encoding="utf-8")
    for key in R.GOVERNING_KILLS:
        assert key in source
    assert not re.search(r"DO_NOT_REBUILD\.md[:\s]*(line\s*)?\d+", source)


def test_coverage_meter_is_imported_lazily():
    """regime.py stays stdlib so a thin runner can read context without pandas."""
    tree = ast.parse(REGIME_SOURCE.read_text(encoding="utf-8"))
    module_level = [
        n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))
    ]
    names = {getattr(n, "module", "") or "" for n in module_level}
    names |= {a.name for n in module_level for a in n.names}
    assert not any("regime_conditioning_coverage" in n for n in names), (
        "the coverage meter needs pandas; it must resolve inside the function"
    )
    assert not any(n.split(".")[0] in ("numpy", "pandas") for n in names)


def test_assess_axis_coverage_delegates_to_the_house_meter():
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame({
        "date": pd.date_range("2020-01-31", periods=60, freq="ME"),
        "regime_at_entry": ["risk_on", "risk_off"] * 30,
    })
    report = R.assess_axis_coverage(frame, "regime_at_entry")
    assert report["status"] == "ok"
    assert report["axes"]["regime_at_entry"]["estimable"] is True


# =========================================================================== #
# module hygiene
# =========================================================================== #
def test_model_is_pure_stdlib():
    """The thin ingestion runners import engine.seasonality without numpy/pandas."""
    source = MODEL_SOURCE.read_text(encoding="utf-8")
    assert "import numpy" not in source and "import pandas" not in source


def test_no_module_writes_to_disk_or_reads_a_wall_clock():
    for path in (MODEL_SOURCE, REGIME_SOURCE):
        source = path.read_text(encoding="utf-8")
        assert "open(" not in source, f"{path.name} touches the filesystem"
        assert "datetime.now" not in source and "date.today" not in source, (
            f"{path.name} reads a wall clock; asof is an argument")


def test_every_public_symbol_is_exported():
    import types

    for module in (M, R):
        public = {
            name for name, obj in vars(module).items()
            if not name.startswith("_")
            and not isinstance(obj, types.ModuleType)
            and getattr(obj, "__module__", module.__name__) == module.__name__
        }
        undeclared = public - set(module.__all__)
        assert not undeclared, f"{module.__name__} leaks {sorted(undeclared)}"


def test_determinism(binary_panel):
    import json

    a = json.dumps(_forecast(binary_panel, "binary"), sort_keys=True, default=str)
    b = json.dumps(_forecast(binary_panel, "binary"), sort_keys=True, default=str)
    assert a == b


def test_wilson_interval_is_not_wald_at_the_edge():
    """Biotech rates live near the edges, where Wald produces bounds outside [0,1]."""
    lo, hi = M._wilson(0.02, 30, 0.90)
    assert 0.0 <= lo < hi <= 1.0
    assert lo > 0.0, "a Wald interval would go negative here"
    assert not math.isnan(hi)
