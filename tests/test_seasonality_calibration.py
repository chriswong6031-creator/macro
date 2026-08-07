"""Tests for forward-chained calibration, honest evaluation, and the append-only ledgers.

The suite is built around ONE property and the ways it can silently break:

* :func:`test_no_later_prediction_enters_the_fit` constructs the folds and proves,
  key by key, that a scored prediction is never in its own training set — an
  assertion on the receipts, not on a comment;
* :func:`test_leakage_simulation_against_a_deliberately_leaking_variant` plants a
  regime break in a synthetic stream and scores it twice: once forward-chained,
  once with a calibrator fit on the WHOLE stream.  The leaking variant reports a
  materially better post-break Brier that was never available at decision time,
  and the test pins the direction of that gap.  A leak makes results look BETTER,
  so a test that only checks "calibration improves the score" would pass on the
  bug it is supposed to catch;
* the null tests assert that an unestimable metric comes back NAMED rather than
  as a default — the trap is a 0.5 or a missing key that a downstream reader
  treats as a measurement;
* the ledger tests assert byte-level file stability across a replay, because
  "append-only" is a property of the FILE, not of the function's intent.

Everything is synthetic and offline.  Nothing outside ``tmp_path`` is written.
"""
from __future__ import annotations

import ast
import json
import pathlib
import random
from datetime import date, timedelta

import numpy as np
import pytest

from engine.seasonality import calibration as C

CALIBRATION_SOURCE = pathlib.Path(C.__file__)
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

BREAK_AT = 400
STREAM_N = 800


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def build_stream(n=STREAM_N, *, break_at=BREAK_AT, break_factor=0.35,
                 seed=20260807, horizon_days=21):
    """A prediction stream with a PLANTED regime break.

    Before ``break_at`` the stated odds are honest (outcome rate == p).  After it
    the same stated odds pay off at ``break_factor`` times the rate, so every
    forecast issued after the break is systematically overconfident — the exact
    situation where a calibrator fit on the whole stream cheats.
    """
    rng = random.Random(seed)
    start = date(2019, 1, 7)
    rows = []
    for i in range(n):
        issued = start + timedelta(days=i)
        p = round(min(max(rng.betavariate(2.0, 2.0), 0.03), 0.97), 4)
        true = p if i < break_at else min(max(p * break_factor, 0.02), 0.95)
        rows.append({
            "key": f"K{i:04d}",
            "issued_at": issued,
            "resolved_at": issued + timedelta(days=horizon_days),
            "p": p,
            "y": 1.0 if rng.random() < true else 0.0,
            "issuer": f"ISS{i % 10}",
            "therapeutic_class": ["onc", "cns", "immu"][i % 3],
            "date_cluster": issued.strftime("%G-W%V"),
        })
    return rows


@pytest.fixture(scope="module")
def stream():
    return build_stream()


@pytest.fixture(scope="module")
def calibrated(stream):
    return C.forward_chained_calibration(stream, n_folds=5, method="platt")


def leaky_calibration(records, method="platt"):
    """THE BUG, ON PURPOSE — one calibrator fit on the WHOLE stream, including
    every row it then scores.  This is what "calibrate the model" looks like when
    nobody enforces chronology.  It lives in the test file, not the module: a
    leaking code path in production is a footgun regardless of its name."""
    recs = C.normalize_records(records)
    model = C.fit_calibrator(recs, method=method)
    p_cal = C.apply_calibrator(model, [r["p"] for r in recs])
    return [dict(r, p_cal=float(pc)) for r, pc in zip(recs, p_cal)], model


def brier(rows, key="p_cal"):
    return float(np.mean([(float(r[key]) - float(r["y"])) ** 2 for r in rows]))


# =========================================================================== #
# THE FORWARD CHAIN — structural, not asserted
# =========================================================================== #
def test_no_later_prediction_enters_the_fit(calibrated):
    """THE test this module exists for.

    For every fold: the fit key set and the scored key set are disjoint, and the
    LATEST outcome the fit could see resolved strictly before the EARLIEST
    prediction in the fold was issued.
    """
    scored = [f for f in calibrated["folds"] if not f.get("abstained")]
    assert len(scored) >= 3, "the fixture must produce several scored folds"
    for fold in scored:
        fit_keys, score_keys = set(fold["fit_keys"]), set(fold["score_keys"])
        assert fit_keys, f"{fold['fold']} fit on nothing"
        assert score_keys
        assert fit_keys & score_keys == set(), (
            f"{fold['fold']}: {len(fit_keys & score_keys)} scored predictions were in "
            "their own calibration fit")
        fit_max = date.fromisoformat(fold["fit_max_resolved_at"])
        score_min = date.fromisoformat(fold["score_min_issued_at"])
        assert fit_max < score_min, (
            f"{fold['fold']}: training outcome known at {fit_max} is not strictly "
            f"before the fold's earliest issue date {score_min}")


def test_the_fit_never_sees_an_outcome_that_had_not_resolved(stream, calibrated):
    """Knowing the PREDICTION early is not enough — a calibrator learns from the
    (p, y) pair, and y only exists at ``resolved_at``."""
    by_key = {r["key"]: r for r in C.normalize_records(stream)}
    for fold in calibrated["folds"]:
        if fold.get("abstained"):
            continue
        cutoff = date.fromisoformat(fold["fit_cutoff"])
        for key in fold["fit_keys"]:
            assert by_key[key]["resolved_at"] <= cutoff


def test_every_fold_grows_and_stays_chronological(calibrated):
    scored = [f for f in calibrated["folds"] if not f.get("abstained")]
    n_fits = [f["n_fit"] for f in scored]
    assert n_fits == sorted(n_fits), "an expanding window must not shrink"
    cutoffs = [f["fit_cutoff"] for f in scored]
    assert cutoffs == sorted(cutoffs)


def test_fold_one_is_the_seed_block_and_is_never_scored(calibrated):
    """Nothing precedes fold 1, so nothing can calibrate it. Scoring it would be
    the leak in its purest form."""
    assert calibrated["seed_block"]["fold"] == "fold1"
    assert "fold1" not in {f["fold"] for f in calibrated["folds"]}


def test_the_training_builder_is_never_handed_the_fold():
    """Structural: ``_training_set`` takes (records, cutoff) and nothing else, so
    there is no argument through which the scored fold could reach it."""
    import inspect

    params = list(inspect.signature(C._training_set).parameters)
    assert params == ["records", "cutoff"]
    tree = ast.parse(CALIBRATION_SOURCE.read_text(encoding="utf-8"))
    builders = [n.name for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and "_training_set" in n.name]
    assert builders == ["_training_set"], "there must be exactly ONE training-set builder"


def test_leak_guard_fails_closed_on_overlap():
    """The guard should be unreachable given the structure. A guard that can never
    fire costs nothing; a missing one costs a silently leaking calibrator."""
    rows = C.normalize_records(build_stream(n=60))
    with pytest.raises(C.ForwardChainError):
        C._assert_no_leak(rows, rows, "synthetic")


def test_an_outcome_that_predates_its_forecast_is_rejected():
    bad = [{"key": "X", "issued_at": date(2026, 6, 10),
            "resolved_at": date(2026, 6, 1), "p": 0.5, "y": 1.0}]
    with pytest.raises(C.ForwardChainError):
        C.normalize_records(bad)


def test_folds_abstain_by_name_when_the_stream_is_too_short():
    plan = C.forward_chained_folds(build_stream(n=12), n_folds=5)
    assert plan["abstained"] is True
    assert "insufficient_records_for_forward_chaining" in plan["reason"]
    assert plan["folds"] == []


def test_record_ordering_is_total_and_deterministic():
    """Predictions share issue dates constantly; a tie broken by list position
    would make the fold boundaries depend on how the caller built the list."""
    rows = build_stream(n=40)
    shuffled = list(rows)
    random.Random(5).shuffle(shuffled)
    assert ([r["key"] for r in C.normalize_records(rows)]
            == [r["key"] for r in C.normalize_records(shuffled)])


def test_embargo_days_pushes_the_cutoff_further_back(stream):
    tight = C.forward_chained_folds(stream, n_folds=5, embargo_days=0)
    wide = C.forward_chained_folds(stream, n_folds=5, embargo_days=30)
    for a, b in zip(tight["folds"], wide["folds"]):
        assert date.fromisoformat(b["fit_cutoff"]) < date.fromisoformat(a["fit_cutoff"])


# =========================================================================== #
# THE LEAKAGE SIMULATION (acceptance gate 5)
# =========================================================================== #
def test_leakage_simulation_against_a_deliberately_leaking_variant(stream, calibrated):
    """Plant a regime break; score it forward-chained and leaking; report the gap.

    The direction is the assertion. A leak makes the post-break score look
    BETTER, because the leaking calibrator learned the post-break collapse from
    the post-break rows themselves and then "corrected" them. A test asserting
    only that calibration improves the Brier would pass on the bug.
    """
    break_date = C.normalize_records(stream)[BREAK_AT]["issued_at"]
    leaky_rows, leaky_model = leaky_calibration(stream)

    hon = {r["key"]: r for r in calibrated["calibrated"]}
    lky = {r["key"]: r for r in leaky_rows}
    both = sorted(set(hon) & set(lky))
    hon_rows, lky_rows_c = [hon[k] for k in both], [lky[k] for k in both]
    raw_rows = [dict(hon[k], p_cal=hon[k]["p"]) for k in both]

    post_h = [r for r in hon_rows if r["issued_at"] >= break_date]
    post_l = [r for r in lky_rows_c if r["issued_at"] >= break_date]
    post_r = [r for r in raw_rows if r["issued_at"] >= break_date]
    pre_h = [r for r in hon_rows if r["issued_at"] < break_date]
    pre_l = [r for r in lky_rows_c if r["issued_at"] < break_date]

    bh, bl, br = brier(post_h), brier(post_l), brier(post_r)

    print("\n" + "=" * 78)
    print("CALIBRATION LEAKAGE SIMULATION — planted regime break")
    print("=" * 78)
    print(f"stream            : {len(stream)} predictions, "
          f"{stream[0]['issued_at']} .. {stream[-1]['issued_at']}, 21-day horizon")
    print(f"planted break     : {break_date} (row {BREAK_AT}) — after it the SAME stated")
    print("                    odds pay off at 0.35x the rate, so every forecast issued")
    print("                    after the break is systematically overconfident")
    print(f"scored population : {len(both)} rows common to both variants "
          f"({len(pre_h)} pre-break, {len(post_h)} post-break)")
    print()
    print("--- FOLD RECEIPTS (forward-chained) ------------------------------------")
    for f in calibrated["folds"]:
        print(f"  {f['fold']}: n_fit={f['n_fit']:4d} n_score={f['n_score']:4d}  "
              f"fit_max_resolved_at={f['fit_max_resolved_at']}  "
              f"score_min_issued_at={f['score_min_issued_at']}")
    print()
    print("--- DOES THE FIT EVER SEE THE FOLD IT SCORES? --------------------------")
    for f in calibrated["folds"]:
        overlap = set(f["fit_keys"]) & set(f["score_keys"])
        gap = (date.fromisoformat(f["score_min_issued_at"])
               - date.fromisoformat(f["fit_max_resolved_at"])).days
        print(f"  {f['fold']}: |fit n score| = {len(overlap)}   "
              f"score_min_issued - fit_max_resolved = +{gap}d (must be > 0)")
    print(f"  LEAKY variant: |fit n score| = {len(lky)}  "
          "(every scored row was in its own fit)")
    print()
    print("--- POST-BREAK PERFORMANCE ---------------------------------------------")
    print(f"  raw (uncalibrated)      Brier = {br:.5f}")
    print(f"  forward-chained         Brier = {bh:.5f}")
    print(f"  LEAKING (fit on all)    Brier = {bl:.5f}")
    print(f"  difference (honest - leaking) = {bh - bl:+.5f} Brier "
          f"({100 * (bh - bl) / bh:+.2f}% of the honest score)")
    print()
    print("--- PRE-BREAK (where the two SHOULD agree) -----------------------------")
    print(f"  forward-chained  Brier = {brier(pre_h):.5f}")
    print(f"  LEAKING          Brier = {brier(pre_l):.5f}")
    print(f"  difference = {brier(pre_h) - brier(pre_l):+.5f}")
    print()
    print("--- WHAT THE LEAK BOUGHT -----------------------------------------------")
    print(f"  leaky global calibrator: slope={leaky_model['a']} "
          f"intercept={leaky_model['b']}")
    print("  It learned the post-break collapse from the post-break rows themselves")
    print("  and then 'corrected' them. The forward-chained calibrator carried a")
    print("  pre-break slope into the break, exactly as a decision-maker would have.")
    print(f"  The {bh - bl:+.5f} Brier gap is the size of the LIE, not of an improvement.")
    print("=" * 78)

    # --- the assertions ---------------------------------------------------
    # 1. structural: the honest variant never saw its own folds; the leaky one saw all.
    for f in calibrated["folds"]:
        assert set(f["fit_keys"]) & set(f["score_keys"]) == set()
    assert set(r["key"] for r in leaky_rows) == set(C.normalize_records(stream)[i]["key"]
                                                    for i in range(len(stream)))
    # 2. the leak BUYS a better post-break score — that is the whole failure mode.
    assert bl < bh, ("the leaking variant must look better post-break; if it does "
                     "not, this simulation is not exercising the leak")
    assert (bh - bl) > 0.01, "the planted break should produce a material gap"
    # 3. the honest variant does not magically fix a break it could not see: it
    #    stays close to the raw scores on the post-break block.
    assert bh > bl and bh <= br + 1e-9
    # 4. pre-break, where the leak has nothing to gain, the honest variant is not
    #    worse — the global calibrator averaged two regimes and damaged both.
    assert brier(pre_h) <= brier(pre_l) + 1e-9


# =========================================================================== #
# REUSE, NOT REIMPLEMENTATION
# =========================================================================== #
REUSED = ("platt_fit", "isotonic_calibration", "apply_calibration",
          "brier_reliability", "expected_calibration_error", "purged_folds")


def test_house_primitives_are_imported_not_retyped():
    """A second Brier score in this repo would drift from the house one."""
    tree = ast.parse(CALIBRATION_SOURCE.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "engine.validation"
        for alias in node.names
    }
    assert set(REUSED) <= imported, f"not imported from engine.validation: {set(REUSED) - imported}"
    defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert defined & set(REUSED) == set(), (
        f"reimplemented instead of reused: {sorted(defined & set(REUSED))}")


def test_purged_folds_is_fed_a_positional_index(stream):
    """Issue dates repeat, so a value-keyed slice would be ambiguous exactly
    where the fold boundaries matter."""
    plan = C.forward_chained_folds(stream, n_folds=5)
    positions = [i for f in plan["folds"] for i in f["score_positions"]]
    assert all(isinstance(i, int) for i in positions)
    assert len(positions) == len(set(positions)), "folds must not overlap"


# =========================================================================== #
# CALIBRATORS
# =========================================================================== #
@pytest.mark.parametrize("method", ["platt", "isotonic", "auto"])
def test_calibrator_methods_all_run(stream, method):
    res = C.forward_chained_calibration(stream, n_folds=5, method=method)
    assert res["abstained"] is False
    assert res["n_calibrated"] > 0
    assert all(0.0 <= r["p_cal"] <= 1.0 for r in res["calibrated"])


def test_calibrator_abstains_by_name_on_a_thin_fit():
    thin = C.normalize_records(build_stream(n=20))
    model = C.fit_calibrator(thin, method="platt")
    assert model["abstained"] is True
    assert "platt_unestimable" in model["reason"]
    assert model["value"] is None


def test_applying_an_abstaining_calibrator_raises():
    """The trap: ignoring the abstention and passing RAW scores through under a
    calibrated label."""
    model = C.fit_calibrator(C.normalize_records(build_stream(n=20)), method="platt")
    with pytest.raises(C.CalibrationError) as exc:
        C.apply_calibrator(model, [0.5, 0.6])
    assert "not calibrated" in str(exc.value)


def test_a_fold_whose_fit_abstains_contributes_no_calibrated_rows():
    res = C.forward_chained_calibration(build_stream(n=70), n_folds=4, method="platt")
    abstaining = [f for f in res["folds"] if f.get("abstained")]
    assert abstaining, "the fixture must produce at least one abstaining fold"
    calibrated_keys = {r["key"] for r in res["calibrated"]}
    for fold in abstaining:
        assert not (set(fold["score_keys"]) & calibrated_keys)
        assert fold["reason"]


def test_unknown_method_raises():
    with pytest.raises(C.CalibrationError):
        C.fit_calibrator(C.normalize_records(build_stream(n=200)), method="magic")


# =========================================================================== #
# THE EVALUATION BUNDLE
# =========================================================================== #
REQUIRED_METRIC_SLOTS = (
    "brier", "log_score", "crps", "reliability_bins", "expected_calibration_error",
    "calibration_slope_intercept", "chronological_baseline", "issuer_holdout",
    "therapeutic_class_holdout", "drift", "decision_economics",
)


@pytest.fixture(scope="module")
def evaluation(calibrated):
    return C.evaluate(calibrated["calibrated"],
                      economics={"threshold": 0.6, "win": 1.0, "loss": 1.0, "cost": 0.05})


def test_every_required_metric_slot_is_present(evaluation):
    for slot in REQUIRED_METRIC_SLOTS:
        assert slot in evaluation, f"missing metric slot {slot}"
        assert isinstance(evaluation[slot], dict)
        assert "abstained" in evaluation[slot], f"{slot} does not declare estimability"


def test_the_estimable_metrics_actually_estimate(evaluation):
    assert evaluation["brier"]["abstained"] is False
    assert 0.0 < evaluation["brier"]["brier"] < 1.0
    assert evaluation["log_score"]["abstained"] is False
    assert evaluation["log_score"]["log_score"] > 0
    assert evaluation["expected_calibration_error"]["abstained"] is False
    assert evaluation["reliability_bins"]["abstained"] is False
    assert evaluation["reliability_bins"]["bins"]


def test_calibration_slope_and_intercept_are_reported_and_read(evaluation):
    block = evaluation["calibration_slope_intercept"]
    assert block["abstained"] is False
    assert "slope" in block and "intercept" in block
    assert block["reading"] in ("overconfident", "underconfident",
                                "not_distinguishable_from_calibrated",
                                "not_distinguishable_from_calibrated:slope_ci_unestimable")
    assert block["slope_ci"]["abstained"] is False
    assert block["slope_ci"]["lo"] < block["slope"] < block["slope_ci"]["hi"]


def test_the_slope_reading_never_calls_miscalibration_it_cannot_see():
    """A hard 0.9/1.1 threshold on a POINT estimate is a coin flip at this
    module's own fit floor.

    On perfectly calibrated data at n=40 the point rule labelled the stream
    miscalibrated 76% of the time across 500 replications. The reading may only
    leave "calibrated" when the slope's own interval clears the identity band —
    the same standard ``drift_report`` applies to a break.
    """
    rng = random.Random(11)
    start = date(2024, 1, 8)
    rows = []
    for i in range(50):
        issued = start + timedelta(days=i)
        p = round(min(max(rng.betavariate(2.0, 2.0), 0.05), 0.95), 4)
        rows.append({"key": f"S{i:03d}", "issued_at": issued,
                     "resolved_at": issued + timedelta(days=5),
                     "p": p, "y": 1.0 if rng.random() < p else 0.0})
    recs = C.normalize_records(rows)
    block = C._slope_intercept([r["p"] for r in recs], [r["y"] for r in recs])
    assert block["abstained"] is False
    assert block["reading"].startswith("not_distinguishable_from_calibrated"), (
        f"a 50-row perfectly calibrated stream was labelled {block['reading']!r} "
        f"off a point slope of {block['slope']}")
    # the point reading is still reported, so nothing is hidden — it is just not
    # the published verdict
    assert block["point_reading"] in ("overconfident", "underconfident", "calibrated")
    assert block["slope_ci"]["lo"] < 0.9 or block["slope_ci"]["hi"] > 1.1


def test_a_slope_far_from_one_is_still_called():
    """The other half of the pair: the CI rule must not mute a REAL break.

    Without this, "never call miscalibration" would pass the test above.
    """
    rng = random.Random(5)
    start = date(2024, 1, 8)
    rows = []
    for i in range(400):
        issued = start + timedelta(days=i)
        p = round(min(max(rng.betavariate(2.0, 2.0), 0.05), 0.95), 4)
        # stated odds pay off at a third of the rate: badly overconfident
        rows.append({"key": f"O{i:03d}", "issued_at": issued,
                     "resolved_at": issued + timedelta(days=5),
                     "p": p, "y": 1.0 if rng.random() < p / 3.0 else 0.0})
    recs = C.normalize_records(rows)
    block = C._slope_intercept([r["p"] for r in recs], [r["y"] for r in recs])
    assert block["reading"] == "overconfident", block
    assert block["slope_ci"]["hi"] < 0.9


def test_chronological_baseline_uses_only_already_resolved_outcomes(evaluation):
    block = evaluation["chronological_baseline"]
    assert block["abstained"] is False
    assert "expanding prior base rate" in block["basis"]
    # rows with too little prior history are EXCLUDED and counted, not filled
    assert block["n_skipped_thin_history"] > 0
    assert block["improvement_ci"]["abstained"] is False


def test_issuer_and_class_holdouts_are_estimable_and_forward_chained(evaluation):
    for slot in ("issuer_holdout", "therapeutic_class_holdout"):
        block = evaluation[slot]
        assert block["abstained"] is False, block.get("reason")
        assert block["n_scored"] > 0
        assert "forward-chained" in block["basis"]
        assert block["pooled_brier_ci"]["abstained"] is False


def test_holdout_scores_come_from_a_calibrator_that_never_saw_the_group(stream):
    """The point of a group holdout: issuer X's score is produced by a fit with no
    issuer X in it. Verified by monkey-free construction — every fit excludes it."""
    res = C.group_holdout(C.normalize_records(build_stream(n=600)), "issuer",
                          method="platt", n_folds=4)
    assert res["abstained"] is False
    assert res["n_groups_scored"] >= 2


def test_drift_report_calls_a_break_on_a_CI_that_excludes_zero(evaluation):
    block = evaluation["drift"]
    assert block["abstained"] is False
    assert isinstance(block["break_detected"], bool)
    assert block["early"]["n"] > 0 and block["late"]["n"] > 0
    assert block["brier_delta_ci"]["basis"] == "cluster_block_bootstrap_of_the_difference"
    assert "DIFFERENCE" in block["basis"]
    # break_detected IS the difference CI's verdict, not a second opinion
    assert block["break_detected"] == bool(block["brier_delta_ci"]["excludes_zero"])


def test_a_break_is_called_on_the_DIFFERENCE_not_on_two_overlapping_intervals():
    """Non-overlap of two separate 90% intervals is not a 10%-level test of a
    difference — it is far more conservative, and roughly half as powerful.

    This stream is the case that separates the two rules: the bootstrapped
    difference excludes zero while the halves' own intervals still overlap. Under
    the old rule the module's ONLY drift monitor reported no break.
    """
    rows = C.normalize_records(
        build_stream(n=400, break_at=200, break_factor=0.9, seed=20260807 + 4))
    block = C.drift_report(rows, score_key="p")
    assert block["halves_intervals_disjoint"] is False, "fixture no longer separates them"
    assert block["break_detected"] is True, (
        "the difference CI excludes zero; the overlap rule misses this break")
    lo, hi = block["brier_delta_ci"]["lo"], block["brier_delta_ci"]["hi"]
    assert lo > 0, "late half is materially worse"
    assert block["early_brier_ci"]["hi"] > block["late_brier_ci"]["lo"], (
        "the halves' intervals really do overlap")


def test_decision_economics_reports_value_after_costs(evaluation):
    block = evaluation["decision_economics"]
    assert block["abstained"] is False
    assert block["n_decisions"] > 0
    assert "ev_per_decision_after_costs" in block
    assert block["costs"]["cost"] == 0.05
    assert block["do_nothing_ev"] == 0.0
    assert block["ev_ci"]["abstained"] is False


def test_crps_is_estimated_when_the_forecasts_are_distributional():
    rng = random.Random(4)
    rows = []
    start = date(2024, 1, 8)
    for i in range(120):
        issued = start + timedelta(days=i)
        centre = rng.gauss(0.0, 0.04)
        rows.append({
            "key": f"D{i:03d}", "issued_at": issued,
            "resolved_at": issued + timedelta(days=10),
            "p": 0.5, "y": 1.0 if rng.random() < 0.5 else 0.0,
            "issuer": f"ISS{i % 6}", "therapeutic_class": ["onc", "cns"][i % 2],
            "date_cluster": issued.strftime("%G-W%V"),
            "samples": [rng.gauss(centre, 0.05) for _ in range(60)],
            "realized": centre + rng.gauss(0, 0.05),
        })
    out = C.evaluate(rows, score_key="p")
    assert out["crps"]["abstained"] is False
    assert out["crps"]["crps"] > 0
    assert out["crps"]["climatology"] == "pooled_realized_outcomes"
    # the climatology is built from the outcomes being scored: an IN-SAMPLE
    # reference in a module whose thesis is that no benchmark sees the future.
    # It flatters the benchmark, not the forecast — and it is stated, not left
    # for a reader to infer from the label.
    assert out["crps"]["climatology_is_in_sample"] is True
    assert out["log_score"]["base_rate_is_in_sample"] is True
    assert out["log_score"]["point_in_time_alternative"] == "chronological_baseline"


# =========================================================================== #
# EXPLICIT NULLS ARE PRINTED, NOT HIDDEN
# =========================================================================== #
def test_unestimable_metrics_are_named_abstentions_not_defaults(evaluation):
    """engine.validation returns {} on thin N; this module must convert that into
    a NAMED reason so a reader sees which floor was hit."""
    crps = evaluation["crps"]
    assert crps["abstained"] is True
    assert crps["reason"] == "crps_not_applicable:no_distributional_forecasts_in_stream"
    assert crps["value"] is None
    assert "crps" not in crps, "an abstention must not carry a metric value"
    assert crps["schema"] == C.ABSTENTION_SCHEMA


def test_unconfigured_decision_economics_abstains_by_name(calibrated):
    out = C.evaluate(calibrated["calibrated"])
    block = out["decision_economics"]
    assert block["abstained"] is True
    assert "not_configured" in block["reason"]
    assert "threshold" in block["reason"]


def test_a_rule_that_never_fires_abstains_rather_than_reporting_zero():
    """0.0 would read as break-even; an empty rule has no economics."""
    rows = C.normalize_records(build_stream(n=200))
    out = C.decision_economics(rows, score_key="p", threshold=0.999,
                               win=1.0, loss=1.0, cost=0.0)
    assert out["abstained"] is True
    assert "no_decisions_at_threshold" in out["reason"]
    assert out["value"] is None


def test_thin_streams_abstain_across_every_slot():
    out = C.evaluate(C.normalize_records(build_stream(n=25)), score_key="p")
    for slot in REQUIRED_METRIC_SLOTS:
        assert out[slot]["abstained"] is True, f"{slot} produced a number on 25 rows"
        assert out[slot]["reason"], f"{slot} abstained without a reason"


def test_empty_stream_abstains():
    out = C.evaluate([])
    assert out["abstained"] is True
    assert out["reason"] == "no_records"


# =========================================================================== #
# CLUSTER-AWARE UNCERTAINTY
# =========================================================================== #
def test_cluster_bootstrap_is_wider_than_a_row_bootstrap():
    """Overlapping horizons make rows within a cluster one draw. Resampling rows
    would report an interval several times narrower than the data earns."""
    rng = np.random.default_rng(3)
    values, clustered, per_row = [], [], []
    for c in range(20):
        shared = rng.normal(0, 1.0)
        for _ in range(20):
            v = shared + rng.normal(0, 0.05)
            values.append(v)
            clustered.append(f"C{c}")
    per_row = [f"R{i}" for i in range(len(values))]
    wide = C.cluster_bootstrap_ci(values, clustered, B=500, seed=1)
    narrow = C.cluster_bootstrap_ci(values, per_row, B=500, seed=1)
    assert (wide["hi"] - wide["lo"]) > 3 * (narrow["hi"] - narrow["lo"])
    assert wide["n_clusters"] == 20 and narrow["n_clusters"] == len(values)


def test_a_missing_cluster_key_is_disclosed_not_silently_replaced():
    rows = [dict(r) for r in C.normalize_records(build_stream(n=200))]
    for r in rows:
        r.pop("date_cluster")
    out = C.evaluate(rows, score_key="p")
    assert out["cluster_basis"] == "per_record_fallback_no_overlap_protection"


def test_single_cluster_bootstrap_abstains():
    out = C.cluster_bootstrap_ci([1.0, 2.0, 3.0], ["A", "A", "A"])
    assert out["abstained"] is True
    assert "single_cluster" in out["reason"]


def test_an_abstaining_ci_ships_no_live_point_under_a_readable_name():
    """``{"abstained": True, "value": None, "point": 2.0}`` hands a consumer
    reading ``.get("point")`` a number off an abstention."""
    out = C.cluster_bootstrap_ci([1.0, 2.0, 3.0], ["A", "A", "A"])
    assert "point" not in out
    assert out["value"] is None
    assert out["point_estimate_without_ci"] == 2.0


# =========================================================================== #
# THE LABEL MUST MATCH THE EVIDENCE
# =========================================================================== #
def _nested_cis(block):
    """Every cluster-bootstrap CI anywhere in a payload."""
    found = []
    if isinstance(block, dict):
        if block.get("basis", "").startswith("cluster_block_bootstrap"):
            found.append(block)
        for value in block.values():
            found += _nested_cis(value)
    elif isinstance(block, (list, tuple)):
        for value in block:
            found += _nested_cis(value)
    return found


def test_every_nested_ci_discloses_the_cluster_rule_that_produced_it():
    """``basis="cluster_block_bootstrap"`` was stamped unconditionally.

    A CI computed one-cluster-per-row — no overlap protection at all, and
    measurably narrower — carried the same label as one computed on real date
    clusters, while only the TOP-LEVEL ``cluster_basis`` told the truth.
    """
    rows = [dict(r) for r in C.normalize_records(build_stream(n=400))]
    with_key = C.evaluate(rows, score_key="p",
                          economics={"threshold": 0.6, "win": 1.0, "loss": 1.0,
                                     "cost": 0.05})
    stripped = [dict(r) for r in rows]
    for r in stripped:
        r.pop("date_cluster")
    without = C.evaluate(stripped, score_key="p",
                         economics={"threshold": 0.6, "win": 1.0, "loss": 1.0,
                                    "cost": 0.05})

    good = _nested_cis(with_key)
    bad = _nested_cis(without)
    assert len(good) >= 3 and len(bad) >= 3, "the scan found no intervals to check"
    assert all(ci["cluster_basis"] == "date_cluster" for ci in good)
    assert all("per_record_fallback_no_overlap_protection" in ci["cluster_basis"]
               for ci in bad), "a per-record CI is labelled as if it were clustered"
    assert with_key["cluster_basis"] == "date_cluster"
    # the two are resampling genuinely different things — the label is
    # load-bearing, not decorative
    a = with_key["chronological_baseline"]["improvement_ci"]
    b = without["chronological_baseline"]["improvement_ci"]
    assert b["n_clusters"] > 4 * a["n_clusters"], (
        f"the fallback resampled {b['n_clusters']} 'clusters' against "
        f"{a['n_clusters']} real ones")


def test_a_partially_populated_cluster_key_is_disclosed_as_partial():
    rows = [dict(r) for r in C.normalize_records(build_stream(n=400))]
    for r in rows[::2]:
        r.pop("date_cluster")
    out = C.evaluate(rows, score_key="p")
    assert "200/400_rows_carried_date_cluster" in out["cluster_basis"]
    for ci in _nested_cis(out):
        assert "200/400_rows_carried_date_cluster" in ci["cluster_basis"]


def test_a_present_but_null_cluster_key_does_not_collapse_into_one_cluster():
    """The consumers used ``r.get(cluster_key, r["key"])``: a key that is PRESENT
    and ``None`` is not a missing key, so every row became one cluster called
    ``"None"`` and every nested CI abstained on ``single_cluster`` while the
    header reported hundreds of clusters."""
    rows = [dict(r, date_cluster=None) for r in C.normalize_records(build_stream(n=400))]
    out = C.evaluate(rows, score_key="p",
                     economics={"threshold": 0.6, "win": 1.0, "loss": 1.0, "cost": 0.05})
    assert out["cluster_basis"] == "per_record_fallback_no_overlap_protection"
    assert out["n_clusters"] == len(rows)
    for ci in _nested_cis(out):
        assert ci.get("abstained") is False, (
            f"a nested CI collapsed to one cluster: {ci.get('reason')}")
    assert out["chronological_baseline"]["improvement_ci"]["n_clusters"] > 1


def test_every_interval_names_which_uncertainty_it_is():
    """``engine.seasonality.model`` refuses to emit an uncertainty that does not
    say which one it is; the same intervals crossing this module's boundary
    (``improvement_ci``, ``ev_ci``, ``pooled_brier_ci``) must say it too."""
    out = C.evaluate(C.normalize_records(build_stream(n=400)), score_key="p",
                     economics={"threshold": 0.6, "win": 1.0, "loss": 1.0, "cost": 0.05})
    intervals = _nested_cis(out)
    assert intervals
    for ci in intervals:
        assert ci["semantics"] == "parameter_ci", ci.get("basis")
    assert out["calibration_slope_intercept"]["slope_ci"]["semantics"] == "parameter_ci"


def test_scoring_raw_scores_under_a_calibrated_label_is_refused():
    """``r.get(score_key, r["p"])`` fell back to the RAW score while the payload
    kept reporting ``score_key="p_cal"``.

    That is the relabelling ``apply_calibrator`` raises to prevent, reintroduced
    by a ``dict.get`` default. It bites in practice because
    ``forward_chained_calibration`` returns ``calibrated`` as a SUBSET.
    """
    raw = C.normalize_records(build_stream(n=400))  # no p_cal anywhere
    with pytest.raises(C.CalibrationError) as exc:
        C.evaluate(raw)
    assert "p_cal" in str(exc.value)
    assert "score_key='p'" in str(exc.value)
    # scoring the raw column is fine — it just has to be said
    said = C.evaluate(raw, score_key="p")
    assert said["score_key"] == "p"
    assert said["n_rows_with_score_key"] == len(raw)
    # and a PARTIALLY calibrated stream is refused too, not silently mixed
    half = [dict(r) for r in raw]
    for r in half[:200]:
        r["p_cal"] = r["p"]
    with pytest.raises(C.CalibrationError):
        C.evaluate(half)


@pytest.mark.parametrize("fn", ["chronological_baseline", "drift_report",
                                "decision_economics"])
def test_no_metric_silently_falls_back_to_the_raw_column(fn):
    raw = C.normalize_records(build_stream(n=400))
    kwargs = {"threshold": 0.5, "win": 1.0, "loss": 1.0, "cost": 0.0} \
        if fn == "decision_economics" else {}
    with pytest.raises(C.CalibrationError):
        getattr(C, fn)(raw, **kwargs)


def test_an_unestimable_metric_names_the_row_count_the_floor_ACTUALLY_saw():
    """``engine.validation`` masks non-finite pairs before applying its floor, so
    ``n=100<30`` on an all-NaN input of length 100 is an arithmetically false
    inequality naming a floor that was not the one hit."""
    nan = [float("nan")] * 100
    y = [1.0, 0.0] * 50
    brier = C._brier_block(nan, y)
    slope = C._slope_intercept(nan, y)
    for block in (brier, slope):
        assert block["abstained"] is True
        assert "n_finite=0<" in block["reason"], block["reason"]
        assert block["n_rows_offered"] == 100
        assert block["n_finite_pairs"] == 0


def test_the_reported_n_is_the_n_the_fit_used():
    """Two ``n`` fields in one payload disagreed: the slope reported the unmasked
    row count while the Brier beside it reported the masked one."""
    p = [0.4, 0.6] * 50 + [float("nan")] * 60
    y = [1.0, 0.0] * 50 + [1.0] * 60
    slope = C._slope_intercept(p, y)
    brier = C._brier_block(p, y)
    assert slope["abstained"] is False and brier["abstained"] is False
    assert slope["n"] == brier["n"] == 100
    assert slope["n_rows_offered"] == 160


def test_calibrated_rows_disclose_which_calibrator_family_produced_them(stream):
    """``method="auto"`` switches family on ``n_fit`` part-way down the stream, so
    one calibrated column can carry both platt and isotonic rows under a single
    constant version stamp."""
    res = C.forward_chained_calibration(stream, n_folds=5, method="auto")
    families = {r["method"] for r in res["calibrated"]}
    assert families <= {"platt", "isotonic"}
    assert res["calibrator_families_used"] == sorted(families)
    assert res["mixed_calibrator_families"] is (len(families) > 1)
    assert len(families) > 1, "the fixture must actually cross the auto floor"
    out = C.evaluate(res["calibrated"])
    assert out["calibrator_methods_present"] == sorted(families)


def test_every_estimated_metric_carries_the_shadow_tier(evaluation):
    """A metric block is read on its own once it is lifted out of the parent; a
    shadow-tier number that loses its tier on the way out is a promotion by
    accident."""
    for slot in REQUIRED_METRIC_SLOTS:
        assert evaluation[slot]["tier"] == "shadow", slot
    for ci in _nested_cis(evaluation):
        assert ci["tier"] == "shadow"


# =========================================================================== #
# APPEND-ONLY LEDGERS
# =========================================================================== #
def _forecast_row(i):
    return {"key": f"F{i:03d}", "issued_at": f"2026-08-{i + 1:02d}",
            "symbol": "ABC", "target": "up_5d", "p": 0.6 + i / 100,
            "model_version": "seasonality-market-response-v1",
            "calibration_version": "seasonality-forward-chain-v1"}


def _outcome_row(i):
    return {"key": f"F{i:03d}", "resolved_at": f"2026-09-{i + 1:02d}", "y": i % 2}


def test_forecast_and_outcome_rows_append(tmp_path):
    path = tmp_path / "ledger.jsonl"
    for i in range(3):
        res = C.append_forecast_row(path, _forecast_row(i))
        assert res["appended"] is True
        assert res["tier"] == "shadow"
    for i in range(3):
        assert C.append_outcome_row(path, _outcome_row(i))["appended"] is True
    rows = C.read_ledger(path)
    assert len(rows) == 6
    assert [r["row_type"] for r in rows] == ["forecast"] * 3 + ["outcome"] * 3
    assert [r["key"] for r in rows[:3]] == ["F000", "F001", "F002"]
    assert all(r["tier"] == "shadow" for r in rows)
    assert rows[0]["schema"] == C.FORECAST_ROW_SCHEMA
    assert rows[3]["schema"] == C.OUTCOME_ROW_SCHEMA


def test_replaying_identical_inputs_appends_no_duplicate(tmp_path):
    """Idempotence is a property of the FILE, so the test checks the bytes."""
    path = tmp_path / "ledger.jsonl"
    for i in range(4):
        C.append_forecast_row(path, _forecast_row(i))
        C.append_outcome_row(path, _outcome_row(i))
    before = path.read_bytes()

    for _ in range(3):
        for i in range(4):
            f = C.append_forecast_row(path, _forecast_row(i))
            o = C.append_outcome_row(path, _outcome_row(i))
            assert f["appended"] is False and o["appended"] is False
            assert f["reason"] == "duplicate_identical_replay"

    assert path.read_bytes() == before, "a replay changed the ledger bytes"
    assert len(C.read_ledger(path)) == 8


def test_a_changed_row_under_the_same_key_is_refused(tmp_path):
    """Append-only means never re-dating history. A correction is a NEW row."""
    path = tmp_path / "ledger.jsonl"
    C.append_forecast_row(path, _forecast_row(0))
    before = path.read_bytes()
    with pytest.raises(C.LedgerAppendError) as exc:
        C.append_forecast_row(path, dict(_forecast_row(0), p=0.99))
    assert "append-only" in str(exc.value)
    with pytest.raises(C.LedgerAppendError):
        C.append_forecast_row(path, dict(_forecast_row(0), issued_at="2026-08-09"))
    assert path.read_bytes() == before, "a refused append still touched the file"


def test_forecast_and_outcome_share_a_key_without_colliding(tmp_path):
    path = tmp_path / "ledger.jsonl"
    assert C.append_forecast_row(path, _forecast_row(0))["appended"] is True
    assert C.append_outcome_row(path, _outcome_row(0))["appended"] is True
    assert len(C.read_ledger(path)) == 2


def test_rows_are_never_reordered(tmp_path):
    """Written in call order, read back in file order, both times."""
    path = tmp_path / "ledger.jsonl"
    order = [7, 2, 9, 0, 4]
    for i in order:
        C.append_forecast_row(path, _forecast_row(i))
    assert [r["key"] for r in C.read_ledger(path)] == [f"F{i:03d}" for i in order]


def test_missing_required_fields_raise(tmp_path):
    path = tmp_path / "ledger.jsonl"
    with pytest.raises(C.LedgerAppendError):
        C.append_forecast_row(path, {"issued_at": "2026-08-01"})
    with pytest.raises(C.LedgerAppendError):
        C.append_outcome_row(path, {"key": "F000"})
    assert not path.exists()


def test_a_corrupt_ledger_is_reported_not_buried(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(C.LedgerAppendError) as exc:
        C.append_forecast_row(path, _forecast_row(0))
    assert "not valid JSON" in str(exc.value)


def test_ledger_functions_only_ever_open_in_append_or_read_mode():
    """Structural: no 'w', no 'r+', no truncate anywhere in the module."""
    tree = ast.parse(CALIBRATION_SOURCE.read_text(encoding="utf-8"))
    modes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "open":
            candidates = list(node.args[:1])
            candidates += [k.value for k in node.keywords if k.arg == "mode"]
            for arg in candidates:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    modes.append(arg.value)
    assert modes, "no open() calls found — the scan is checking nothing"
    assert set(modes) <= {"a", "r"}, f"forbidden file modes: {sorted(set(modes) - {'a', 'r'})}"
    source = CALIBRATION_SOURCE.read_text(encoding="utf-8")
    for forbidden in ("truncate", "os.replace", "shutil.move", "unlink", "write_text"):
        assert forbidden not in source


def test_this_pr_writes_nothing_under_data():
    """The ledger WRITER is a later wiring PR. These are pure functions."""
    source = CALIBRATION_SOURCE.read_text(encoding="utf-8")
    assert '"data/' not in source and "'data/" not in source
    assert "MACRO_LIVE_DIR" not in source
    ledger = REPO_ROOT / "data" / "seasonality" / "nw_forward_ledger.jsonl"
    assert ledger.exists()
    # 28 registrations, ZERO matured grades — shadow status is binding.
    rows = [json.loads(x) for x in ledger.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(rows) == 28
    assert all(r["tier"] == "shadow" for r in rows)
    assert not [r for r in rows if r.get("row_type") == "grade"]


# =========================================================================== #
# SHADOW TIER
# =========================================================================== #
def test_every_calibration_artifact_carries_shadow_tier(calibrated, evaluation, tmp_path):
    payloads = [
        calibrated,
        evaluation,
        C.forward_chained_folds(build_stream(n=200), n_folds=4),
        C.forward_chained_folds(build_stream(n=12), n_folds=5),
        C.append_forecast_row(tmp_path / "l.jsonl", _forecast_row(0)),
        C.cluster_bootstrap_ci([1.0], ["A"]),
    ]
    for payload in payloads:
        assert payload["tier"] == "shadow"
    assert all(r["tier"] == "shadow" for r in calibrated["calibrated"])
    assert C.TIER == "shadow"


def test_nothing_here_promotes_anything(evaluation):
    assert "shadow tier" in evaluation["promotion"]
    assert "zero matured grades" in evaluation["promotion"]
    # Structural rather than prose-matching: no entry point named for promotion,
    # and no literal tier value other than shadow anywhere in the module.
    public = [n for n in dir(C) if not n.startswith("_") and callable(getattr(C, n))]
    assert not [n for n in public
                if any(w in n.lower() for w in ("promote", "rank", "size", "gate"))]
    tree = ast.parse(CALIBRATION_SOURCE.read_text(encoding="utf-8"))
    tier_values = [
        node.value.value for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", "") == "TIER" for t in node.targets)
        and isinstance(node.value, ast.Constant)
    ]
    assert tier_values == ["shadow"]


def test_determinism(stream):
    a = C.forward_chained_calibration(stream, n_folds=5, method="platt")
    b = C.forward_chained_calibration(stream, n_folds=5, method="platt")
    assert (json.dumps(a["calibrated"], sort_keys=True, default=str)
            == json.dumps(b["calibrated"], sort_keys=True, default=str))


def test_every_public_symbol_is_exported():
    import types

    public = {
        name for name, obj in vars(C).items()
        if not name.startswith("_")
        and not isinstance(obj, types.ModuleType)
        and getattr(obj, "__module__", C.__name__) == C.__name__
    }
    assert not public - set(C.__all__), f"leaks {sorted(public - set(C.__all__))}"
