"""Tests for scripts/prophet_fusion_arena.py — the §9 validation harness.

WHAT THIS ENCODES.  PR-1a ships no model, so nothing here tests a result.  What is
tested is that each rule §9 registers is MECHANICAL — a typed refusal naming the thing
that broke — rather than a paragraph someone is expected to remember:

  §9.2  minimum-usable fold   -> FoldRefusal naming BOTH counts; the real 24-date frame
                                 refuses every fold, and that refusal is the spec
  §9.2  purge + embargo       -> no surviving train date's label window reaches the test
                                 window; the boundary is asserted, not described
  §9.1  PIT joins only        -> PITRefusal naming member + status, in a backtest frame,
                                 while the same member is lawful in a live frame
  §5.2  composite law         -> ForbiddenCompositeRefusal naming the decomposition
  §5.1  registry is the law   -> unregistered column refused; a column registered twice
                                 refuses the whole registry
  §9.1b fold-scoped normalize -> parameters fit on train only, frozen through transform
  §9.9  coverage / abstention -> nulls counted as unmeasured, floors marked, columns
                                 dropped from the run

MUTATION RECEIPTS — taken 2026-08-14 against this suite; each is the edit a careless
refactor actually makes, and the test it reds.  Re-take them by applying the edit and
running the named test.

  A. ``FoldNormalizer.transform`` recomputes the z parameters from the frame it is
     transforming (``(values - values.mean()) / values.std()``) instead of reading the
     frozen ``spec`` — the classic "normalize each frame by its own stats" leak.
     REDS  test_normalizer_params_are_fit_on_the_train_fold_only

  B. ``run_arena`` fits the normalizer on ``frame`` (the whole label frame) instead of
     ``train`` — the leak at the CALL SITE rather than inside the class.
     REDS  test_the_selftest_passes_end_to_end_and_exercises_every_refusal
           test_the_cli_selftest_exits_zero
     (the selftest's normalizer stage asserts n_fit_dates == n_train_dates)

  C. ``build_folds`` trains up to ``test_start`` instead of ``embargo_cut`` — purge and
     embargo silently removed.
     REDS  test_no_surviving_train_date_label_window_reaches_the_test_window
           test_a_constructed_overlap_lands_in_purged_and_not_in_train
           test_an_embargo_wider_than_the_horizon_adds_a_separate_reported_band

  D. ``family_coverage`` counts a null as a measured zero
     (``notna()`` -> ``fillna(0).ne(0)``).
     REDS  test_a_null_is_unmeasured_never_zero

Everything is synthetic and seeded; no network, no clock, no ``data/`` write.

Run: python3 -m pytest tests/test_prophet_fusion_arena.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import prophet_fusion_arena as ARENA  # noqa: E402
from scripts import prophet_fusion_labels as LABELS  # noqa: E402

SHIPPED_REGISTRY = ROOT / "research" / "prophet_fusion" / "families.yml"


@pytest.fixture(scope="module")
def registry(tmp_path_factory) -> ARENA.Registry:
    """The synthetic registry, loaded THROUGH the real loader (the loader is under test)."""
    return ARENA.load_registry(
        ARENA.write_synthetic_registry(tmp_path_factory.mktemp("registry")))


@pytest.fixture(scope="module")
def fixture_frame() -> pd.DataFrame:
    return ARENA.synthetic_frame()


@pytest.fixture(scope="module")
def labels(fixture_frame) -> LABELS.LabelFrame:
    return LABELS.build_labels(fixture_frame, frame_name=LABELS.FRAME_BOARD_LEDGER)


def write_registry(tmp_path: Path, doc: dict) -> Path:
    path = tmp_path / "families.yml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# §5.1 the registry is the law
# --------------------------------------------------------------------------- #

def test_absent_registry_is_a_hard_error_naming_the_file(tmp_path):
    with pytest.raises(ARENA.RegistryRefusal) as exc:
        ARENA.load_registry(tmp_path / "families.yml")
    assert "families.yml" in str(exc.value)
    assert "unregistered-feature refusal" in str(exc.value)


def test_wrong_schema_is_refused_naming_what_was_found(tmp_path):
    path = write_registry(tmp_path, {"schema": "something.else.v9", "families": {}})
    with pytest.raises(ARENA.RegistryRefusal) as exc:
        ARENA.load_registry(path)
    assert "something.else.v9" in str(exc.value)
    assert ARENA.REGISTRY_SCHEMA in str(exc.value)


def test_a_column_registered_in_two_families_refuses_the_registry(tmp_path):
    """§5.1: exactly one family, enforced by a test over the registry, not by prose."""
    path = write_registry(tmp_path, {
        "schema": ARENA.REGISTRY_SCHEMA,
        "families": {
            "F2": {"members": {"m1": {"pit_status": "pit", "columns": ["ext_z"]}}},
            "F8": {"members": {"m2": {"pit_status": "pit", "columns": ["ext_z"]}}},
        }})
    with pytest.raises(ARENA.RegistryRefusal) as exc:
        ARENA.load_registry(path)
    assert "ext_z" in str(exc.value) and "registered twice" in str(exc.value)
    assert "F2" in str(exc.value) and "F8" in str(exc.value)


def test_an_unknown_pit_status_is_refused_never_assumed_safe(tmp_path):
    path = write_registry(tmp_path, {
        "schema": ARENA.REGISTRY_SCHEMA,
        "families": {"F1": {"members": {"m": {"pit_status": "probably_fine",
                                              "columns": ["x"]}}}}})
    with pytest.raises(ARENA.RegistryRefusal) as exc:
        ARENA.load_registry(path)
    assert "probably_fine" in str(exc.value)
    assert "never assumed safe" in str(exc.value)


def test_registry_reads_both_the_mapping_and_the_list_shape(tmp_path):
    as_list = write_registry(tmp_path, {
        "schema": ARENA.REGISTRY_SCHEMA,
        "families": [{"family": "F1", "coverage_floor": 0.4,
                      "members": [{"name": "m", "pit_status": "pit",
                                   "columns": ["a", "b"]}]}],
        "forbidden_composites": [{"composite": "conviction",
                                  "decompose_to": [{"input": "leg", "family": "F1"}]}]})
    reg = ARENA.load_registry(as_list)
    assert reg.families["F1"].coverage_floor == 0.4
    assert reg.family_of("a") == "F1" and reg.family_of("b") == "F1"
    assert reg.forbidden["conviction"] == ("F1.leg",)


def test_the_shipped_registry_loads_and_is_lawful():
    """The sibling deliverable in this same PR — not skipped, because PR-1a ships both."""
    assert SHIPPED_REGISTRY.exists(), f"{SHIPPED_REGISTRY} is a PR-1a deliverable"
    reg = ARENA.load_registry(SHIPPED_REGISTRY)
    assert reg.schema.startswith(ARENA.REGISTRY_SCHEMA)
    assert len(reg.families) >= 8               # §5.1 F1..F8
    assert reg.pit_columns(), "registry homes no pit-clean column at all"
    assert reg.forbidden, "registry declares no forbidden composites (§5.2)"
    # every member's floor is a probability
    assert all(0.0 <= m.coverage_floor <= 1.0 for m in reg.members.values())


def test_the_shipped_registry_forbids_a_composite_the_ledger_actually_carries():
    """A live, non-synthetic instance of refusal 3: composite_z is in retro_grades."""
    reg = ARENA.load_registry(SHIPPED_REGISTRY)
    with pytest.raises(ARENA.ForbiddenCompositeRefusal) as exc:
        ARENA.check_features(reg, ["composite_z"])
    assert exc.value.column == "composite_z"
    assert exc.value.decompose_to, "a kill with no decomposition names no remedy"


# --------------------------------------------------------------------------- #
# §9.1 / §5.2 the contamination gate
# --------------------------------------------------------------------------- #

def test_snapshot_not_pit_is_refused_in_a_backtest_naming_member_and_status(registry):
    with pytest.raises(ARENA.PITRefusal) as exc:
        ARENA.check_features(registry, ["syn_short_interest"])
    assert exc.value.pit_status == ARENA.PIT_SNAPSHOT
    assert exc.value.member == "syn_short_interest" and exc.value.family == "F5"
    assert "historical row" in str(exc.value)


def test_forward_only_is_refused_in_a_backtest(registry):
    with pytest.raises(ARENA.PITRefusal) as exc:
        ARENA.check_features(registry, ["syn_forensic"])
    assert exc.value.pit_status == ARENA.PIT_FORWARD_ONLY


def test_pit_settlement_is_backtest_lawful_after_5705(tmp_path):
    """PR-3A / #5705: `pit_settlement` is REGISTERED VOCABULARY and now
    backtest-lawful.  Producer law is the 8th NYSE session after settlement,
    floored by stored knowable_date and capture_date — not settlement + 10
    calendar days.  Snapshot and forward-only stay refused.  PIT-lawful is not
    an estimability claim."""
    from lib.finra_knowable import KNOWABLE_LAG_SESSIONS
    assert KNOWABLE_LAG_SESSIONS == 8
    assert ARENA.PIT_SETTLEMENT in ARENA.PIT_STATUSES
    assert ARENA.PIT_SETTLEMENT in ARENA.BACKTEST_LAWFUL_STATUSES
    assert ARENA.BACKTEST_LAWFUL_STATUSES == frozenset(
        {ARENA.PIT_OK, ARENA.PIT_SETTLEMENT}
    )
    assert ARENA.PIT_SNAPSHOT not in ARENA.BACKTEST_LAWFUL_STATUSES
    assert ARENA.PIT_FORWARD_ONLY not in ARENA.BACKTEST_LAWFUL_STATUSES
    doc = {
        "schema": ARENA.REGISTRY_SCHEMA,
        "families": {
            "F5": {"coverage_floor": 0.5, "members": {
                "syn_si_pit": {"pit_status": ARENA.PIT_SETTLEMENT,
                               "columns": ["syn_si_days_to_cover"],
                               "availability_field": "syn_settlement_date"},
            }},
        },
    }
    path = tmp_path / "families.yml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    reg = ARENA.load_registry(path)
    gate = ARENA.check_features(reg, ["syn_si_days_to_cover"],
                                frame_kind=ARENA.FRAME_KIND_BACKTEST)
    assert "syn_si_days_to_cover" in gate.columns
    assert "syn_si_days_to_cover" in reg.pit_columns()
    live = ARENA.check_features(reg, ["syn_si_days_to_cover"],
                                frame_kind=ARENA.FRAME_KIND_LIVE)
    assert live.families == ("F5",)


def test_the_same_member_is_lawful_in_a_live_frame(registry):
    """A live read has no future to leak; the gate is frame-kind aware, not blanket."""
    gate = ARENA.check_features(registry, ["syn_short_interest"],
                                frame_kind=ARENA.FRAME_KIND_LIVE)
    assert gate.columns == ("syn_short_interest",) and gate.families == ("F5",)


def test_a_forbidden_composite_is_refused_with_its_decomposition_named(registry):
    with pytest.raises(ARENA.ForbiddenCompositeRefusal) as exc:
        ARENA.check_features(registry, ["syn_conviction"])
    assert "F2.syn_momentum_leg" in str(exc.value)


def test_an_unregistered_column_is_refused(registry):
    with pytest.raises(ARENA.UnregisteredFeatureRefusal) as exc:
        ARENA.check_features(registry, ["syn_momentum", "syn_unregistered"])
    assert exc.value.columns == ("syn_unregistered",)
    assert "anti-double-count" in str(exc.value)


def test_registering_a_forbidden_composite_does_not_launder_it(tmp_path):
    """Refusal ORDER: forbidden wins over registered, or the kill list is bypassable."""
    path = write_registry(tmp_path, {
        "schema": ARENA.REGISTRY_SCHEMA,
        "families": {"F2": {"members": {"m": {"pit_status": "pit",
                                              "columns": ["conviction"]}}}},
        "forbidden_composites": [{"composite": "conviction", "decompose_to": ["F2.leg"]}]})
    reg = ARENA.load_registry(path)
    with pytest.raises(ARENA.ForbiddenCompositeRefusal):
        ARENA.check_features(reg, ["conviction"])


def test_a_clean_feature_set_is_admitted_with_its_families_named(registry):
    gate = ARENA.check_features(registry, ["syn_momentum", "syn_theme_heat"])
    assert gate.families == ("F2", "F3")
    assert gate.frame_kind == ARENA.FRAME_KIND_BACKTEST


def test_an_unknown_frame_kind_is_refused(registry):
    with pytest.raises(ARENA.FusionRefusal):
        ARENA.check_features(registry, ["syn_momentum"], frame_kind="whatever")


# --------------------------------------------------------------------------- #
# §9.2 folds: purge, embargo, and the minimum-usable refusal
# --------------------------------------------------------------------------- #

def dates(n: int, start: str = "2025-01-01") -> list[str]:
    return [d.strftime("%Y-%m-%d") for d in pd.bdate_range(start=start, periods=n)]


def test_minimum_usable_fold_refusal_names_both_counts_and_both_minimums():
    with pytest.raises(ARENA.FoldRefusal) as exc:
        ARENA.build_folds(dates(70), horizon=10, n_folds=3, test_size=10)
    err = exc.value
    assert err.min_train == 60 and err.min_test == 10
    assert f"{err.n_train_dates} train dates" in str(err)
    assert f"{err.n_test_dates} test dates" in str(err)
    assert "never silently shrinks" in str(err)


def test_the_real_frames_depth_refuses_every_fold_and_that_is_the_spec():
    """The graded frame (24 dates on 2026-08-14) cannot be folded. §9.2 is not bent.

    The depth assertion is a THRESHOLD, not the literal 24: the store accrues, and a
    test that reds the night a date lands would be a scheduled red rather than a
    finding. When it does cross the threshold the message says what to re-read.
    """
    labels = LABELS.build_labels(frame_name=LABELS.FRAME_BOARD_LEDGER)
    longest = max(labels.horizons)
    needed = ARENA.MIN_TRAIN_DATES + ARENA.MIN_TEST_DATES + longest
    assert len(labels.dates) < needed, (
        f"the graded frame now carries {len(labels.dates)} dates (>= {needed}) — it may "
        f"be foldable at last. Re-read §9.2/§8.7 and update this test deliberately.")
    plan = ARENA.folds_for_labels(labels, strict=False)
    assert plan.receipt["n_folds_usable"] == 0
    assert plan.receipt["n_folds_refused"] == ARENA.DEFAULT_N_FOLDS
    assert plan.receipt["embargo"] == longest     # the LONGEST horizon graded, not 10
    assert all("minimum-usable-fold" in r["message"] for r in plan.refusals)


def test_strict_false_collects_the_refusals_instead_of_raising():
    plan = ARENA.build_folds(dates(70), horizon=10, n_folds=3, test_size=10,
                             strict=False)
    assert plan.folds == [] or len(plan.refusals) > 0
    assert len(plan.folds) + len(plan.refusals) == 3


def test_no_surviving_train_date_label_window_reaches_the_test_window():
    """The purge boundary, asserted as arithmetic rather than described in a docstring."""
    grid = dates(200)
    plan = ARENA.build_folds(grid, horizon=21, n_folds=3)
    assert plan.folds, "fixture should fold"
    index = {d: i for i, d in enumerate(grid)}
    for fold in plan.folds:
        first_test = index[fold.test_dates[0]]
        for train_date in fold.train_dates:
            assert index[train_date] + fold.horizon < first_test, (
                f"train date {train_date}'s H={fold.horizon} outcome window overlaps "
                f"test start {fold.test_dates[0]}")


def test_a_constructed_overlap_lands_in_purged_and_not_in_train():
    grid = dates(200)
    fold = ARENA.build_folds(grid, horizon=21, n_folds=1, test_size=20).folds[0]
    index = {d: i for i, d in enumerate(grid)}
    first_test = index[fold.test_dates[0]]
    overlapping = [d for d in grid if first_test - 21 <= index[d] < first_test]
    assert overlapping, "fixture must contain dates inside the label window"
    assert set(overlapping) <= set(fold.purged_dates)
    assert not set(overlapping) & set(fold.train_dates)


def test_an_embargo_wider_than_the_horizon_adds_a_separate_reported_band():
    grid = dates(220)
    narrow = ARENA.build_folds(grid, horizon=10, n_folds=1, test_size=20).folds[0]
    wide = ARENA.build_folds(grid, horizon=10, embargo=30, n_folds=1,
                             test_size=20).folds[0]
    assert narrow.embargo == 10 and wide.embargo == 30
    assert len(wide.embargoed_dates) == 20        # 30 - 10, the band beyond the labels
    assert len(narrow.embargoed_dates) == 0
    assert len(wide.train_dates) == len(narrow.train_dates) - 20


def test_the_embargo_is_sized_off_the_longest_horizon_in_the_frame(fixture_frame):
    labels = LABELS.build_labels(fixture_frame)
    assert labels.horizons == [10, 21]
    plan = ARENA.folds_for_labels(labels, strict=False)
    assert plan.receipt["embargo"] == 21, (
        "a fold containing H=21 rows must embargo >= 21 even when scored at H=10")


def test_test_windows_are_disjoint_and_walk_forward():
    plan = ARENA.build_folds(dates(300), horizon=10, n_folds=3)
    seen: set[str] = set()
    previous_end = ""
    for fold in plan.folds:
        assert not seen & set(fold.test_dates)
        seen |= set(fold.test_dates)
        assert fold.test_dates[0] > previous_end
        previous_end = fold.test_dates[-1]
        assert max(fold.train_dates) < min(fold.test_dates)


# --------------------------------------------------------------------------- #
# §9.1b fold-scoped normalization
# --------------------------------------------------------------------------- #

def norm_frame() -> tuple[pd.DataFrame, pd.DataFrame]:
    train = pd.DataFrame({"date": ["2025-01-01"] * 5, "x": [1.0, 2, 3, 4, 5]})
    test = pd.DataFrame({"date": ["2025-02-01"] * 3, "x": [100.0, 200, 300]})
    return train, test


def test_normalizer_params_are_fit_on_the_train_fold_only():
    """MUTATION RECEIPT: fit on pd.concat([train, test]) reds this test."""
    train, test = norm_frame()
    norm = ARENA.FoldNormalizer(method="z").fit(train, ["x"])
    full = pd.concat([train, test], ignore_index=True)
    assert norm.params["x"]["mean"] == pytest.approx(train["x"].mean())
    assert norm.params["x"]["mean"] != pytest.approx(full["x"].mean())
    assert norm.params["x"]["std"] == pytest.approx(train["x"].std(ddof=0))
    assert norm.params["x"]["n"] == 5
    # and the test fold is transformed BY those train parameters
    out = norm.transform(test)
    expected = (test["x"] - train["x"].mean()) / train["x"].std(ddof=0)
    assert out["x__norm"].tolist() == pytest.approx(expected.tolist())


def test_mutating_the_test_fold_cannot_move_the_frozen_parameters():
    train, test = norm_frame()
    norm = ARENA.FoldNormalizer(method="z").fit(train, ["x"])
    before = norm.fingerprint()
    norm.transform(test)
    norm.transform(test.assign(x=test["x"] * 10_000))
    assert norm.fingerprint() == before


def test_refitting_a_fitted_normalizer_is_refused():
    train, test = norm_frame()
    norm = ARENA.FoldNormalizer(method="z").fit(train, ["x"])
    with pytest.raises(ARENA.NormalizerRefusal) as exc:
        norm.fit(test, ["x"])
    assert "carried forward FROZEN" in str(exc.value)


def test_transform_before_fit_is_refused():
    _, test = norm_frame()
    with pytest.raises(ARENA.NormalizerRefusal):
        ARENA.FoldNormalizer(method="z").transform(test)


def test_percentile_transform_uses_the_train_grid_and_clips_out_of_range():
    train, test = norm_frame()
    norm = ARENA.FoldNormalizer(method="percentile").fit(train, ["x"])
    out = norm.transform(pd.DataFrame({"date": ["d"] * 3, "x": [-99.0, 3.0, 99.0]}))
    assert out["x__norm"].tolist() == pytest.approx([0.0, 0.6, 1.0])
    assert norm.params["x"]["n"] == 5


def test_an_unknown_normalizer_method_is_refused():
    train, _ = norm_frame()
    with pytest.raises(ARENA.NormalizerRefusal):
        ARENA.FoldNormalizer(method="quantum").fit(train, ["x"])


def test_a_degenerate_column_is_flagged_not_divided_by_zero():
    train = pd.DataFrame({"date": ["d"] * 4, "x": [7.0, 7.0, 7.0, 7.0]})
    norm = ARENA.FoldNormalizer(method="z").fit(train, ["x"])
    assert norm.params["x"]["degenerate"] is True and norm.params["x"]["std"] == 1.0
    assert np.isfinite(norm.transform(train)["x__norm"]).all()


# --------------------------------------------------------------------------- #
# §9.9 coverage + abstention
# --------------------------------------------------------------------------- #

def test_a_null_is_unmeasured_never_zero(registry):
    """MUTATION RECEIPT: notna() -> fillna(0).ne(0) in family_coverage reds this."""
    frame = pd.DataFrame({"syn_momentum": [1.0, 0.0, np.nan, 0.0]})
    table = ARENA.family_coverage(frame, registry, families=["F2"])
    # 3 of 4 measured; the two ZEROS are measured values, the one NULL is not
    assert table.loc[0, "coverage"] == pytest.approx(0.75)


def test_a_registered_column_absent_from_the_frame_is_zero_coverage_and_counted(registry):
    table = ARENA.family_coverage(pd.DataFrame({"other": [1.0]}), registry,
                                  families=["F2"])
    assert table.loc[0, "coverage"] == 0.0
    assert table.loc[0, "n_columns_absent"] == 1
    assert table.loc[0, "n_columns_present"] == 0
    assert bool(table.loc[0, "abstain"]) is True


def test_a_family_below_its_floor_is_marked_abstain_and_above_it_is_not(registry):
    thin = pd.DataFrame({"syn_attention": [1.0] + [np.nan] * 9})       # 0.10 coverage
    thick = pd.DataFrame({"syn_momentum": [1.0] * 10})                 # 1.00 coverage
    assert bool(ARENA.family_coverage(thin, registry,
                                      families=["F8"]).loc[0, "abstain"]) is True
    assert bool(ARENA.family_coverage(thick, registry,
                                      families=["F2"]).loc[0, "abstain"]) is False


def test_the_floor_comes_from_the_registry_not_from_a_constant(tmp_path):
    path = write_registry(tmp_path, {
        "schema": ARENA.REGISTRY_SCHEMA,
        "families": {"F1": {"coverage_floor": 0.05,
                            "members": {"m": {"pit_status": "pit", "columns": ["x"]}}}}})
    reg = ARENA.load_registry(path)
    frame = pd.DataFrame({"x": [1.0] + [np.nan] * 9})                  # 0.10 coverage
    row = ARENA.family_coverage(frame, reg, families=["F1"]).loc[0]
    assert row["coverage_floor"] == 0.05 and bool(row["abstain"]) is False


# --------------------------------------------------------------------------- #
# the feature-join seam
# --------------------------------------------------------------------------- #

def test_the_join_seam_refuses_before_a_single_value_is_copied(labels, registry):
    with pytest.raises(ARENA.PITRefusal):
        ARENA.join_features(labels, ARENA.synthetic_frame(), registry,
                            columns=["syn_short_interest"])


def test_the_join_reports_its_keys_and_match_rate(labels, registry, fixture_frame):
    merged, gate, receipt = ARENA.join_features(labels, fixture_frame, registry,
                                                columns=["syn_momentum"])
    assert receipt["join_keys"] == ["date", "ticker", "board_definition"]
    assert receipt["match_rate"] == 1.0
    assert receipt["coverage_after_join"]["syn_momentum"] == 1.0
    assert len(merged) == len(labels.frame)
    assert gate.families == ("F2",)


def test_an_unmatched_outcome_row_reads_null_not_zero(labels, registry, fixture_frame):
    partial = fixture_frame[fixture_frame["ticker"] != "SYN000"]
    merged, _, receipt = ARENA.join_features(labels, partial, registry,
                                             columns=["syn_momentum"])
    orphans = merged[merged["ticker"] == "SYN000"]
    assert len(orphans) > 0
    assert orphans["syn_momentum"].isna().all()
    assert receipt["match_rate"] < 1.0


def test_a_feature_frame_with_no_availability_column_is_refused(labels, registry,
                                                               fixture_frame):
    blind = fixture_frame.drop(columns=["as_of"])
    with pytest.raises(ARENA.FusionRefusal) as exc:
        ARENA.join_features(labels, blind, registry, columns=["syn_momentum"])
    assert "forward-accrual-only" in str(exc.value)
    assert "statutory lags" in str(exc.value)


# --------------------------------------------------------------------------- #
# §8.3 metric scaffold + the dummy challenger
# --------------------------------------------------------------------------- #

def metric_frame() -> pd.DataFrame:
    """Two dates whose row counts differ, so pooled != date-grouped."""
    rows = [{"date": "2025-01-01", "ticker": t, "score": s, "excess_spy": e}
            for t, s, e in [("A", 3.0, 0.05), ("B", 2.0, -0.02), ("C", 1.0, -0.30)]]
    rows += [{"date": "2025-01-02", "ticker": t, "score": s, "excess_spy": e}
             for t, s, e in [("D", 9.0, -0.11)]]
    return pd.DataFrame(rows)


def test_p_at_k_is_averaged_over_dates_not_pooled_over_rows():
    metrics = ARENA.score_by_date(metric_frame(), ks=(1,))
    # date 1: top-1 is A (+5%) -> 1.0 ; date 2: top-1 is D (-11%) -> 0.0 ; mean 0.5
    assert metrics["aggregate"]["p_at_1"] == pytest.approx(0.5)
    assert metrics["n_dates"] == 2


def test_the_ranking_tiebreak_is_ticker_alphabetical():
    frame = pd.DataFrame([{"date": "d", "ticker": t, "score": 0.0, "excess_spy": e}
                          for t, e in [("ZZZ", -0.5), ("AAA", 0.5)]])
    metrics = ARENA.score_by_date(frame, ks=(1,))
    assert metrics["per_date"][0]["top_1_mean_excess"] == pytest.approx(0.5)  # AAA first


def test_large_loser_rate_uses_the_frozen_minus_ten_point_threshold():
    metrics = ARENA.score_by_date(metric_frame(), ks=(1,))
    assert metrics["loser_threshold"] == LABELS.TAIL_LOSS == -0.10
    # date 1: 1 of 3 below -10pp ; date 2: 1 of 1 -> mean of (1/3, 1) = 2/3
    assert metrics["aggregate"]["large_loser_rate_top10"] == pytest.approx(2 / 3)


def test_metrics_are_stamped_dummy_and_promotion_barred_at_production():
    metrics = ARENA.score_by_date(metric_frame(), ks=(1,))
    assert metrics["dummy"] is True
    assert metrics["non_promotion_bearing"] is True
    assert metrics["deployed_composition"] is False
    assert "deployed composition" in metrics["composition_note"]


def test_a_null_outcome_row_is_dropped_from_the_metric_not_scored_as_zero():
    frame = pd.DataFrame([{"date": "d", "ticker": "A", "score": 2.0,
                           "excess_spy": np.nan},
                          {"date": "d", "ticker": "B", "score": 1.0,
                           "excess_spy": 0.04}])
    metrics = ARENA.score_by_date(frame, ks=(1, 2))
    assert np.isnan(metrics["per_date"][0]["p_at_1"])          # only row is unmeasured
    assert metrics["per_date"][0]["top_2_n_measured"] == 1
    assert metrics["per_date"][0]["top_2_mean_excess"] == pytest.approx(0.04)


def test_the_dummy_falls_back_to_a_constant_when_it_has_no_feature():
    frame = pd.DataFrame({"ticker": ["A", "B"], "x": [np.nan, np.nan]})
    assert ARENA.dummy_challenger(frame, feature=None).tolist() == [0.0, 0.0]
    assert ARENA.dummy_challenger(frame, feature="x").tolist() == [0.0, 0.0]


def test_a_null_feature_never_outranks_a_measured_one():
    frame = pd.DataFrame({"ticker": ["A", "B"], "x": [np.nan, -5.0]})
    scores = ARENA.dummy_challenger(frame, feature="x")
    assert scores.iloc[0] < scores.iloc[1]


# --------------------------------------------------------------------------- #
# the run + the CLI selftest
# --------------------------------------------------------------------------- #

def test_out_dir_inside_the_tracked_data_tree_is_refused():
    with pytest.raises(ARENA.OutputPathRefusal) as exc:
        ARENA._safe_out_dir(ROOT / "data" / "scratch_from_a_test")
    assert "research tier" in str(exc.value)


def test_out_dir_inside_the_tracked_site_tree_is_refused():
    with pytest.raises(ARENA.OutputPathRefusal):
        ARENA._safe_out_dir(ROOT / "site" / "scratch_from_a_test")


def test_run_arena_marks_abstention_and_drops_those_columns(labels, registry,
                                                            fixture_frame, tmp_path):
    receipt = ARENA.run_arena(
        labels, registry, features=["syn_momentum", "syn_attention"],
        feature_frame=fixture_frame, out_dir=tmp_path)
    assert len(receipt["fold_reports"]) == ARENA.DEFAULT_N_FOLDS
    for fold in receipt["fold_reports"]:
        assert "F8" in fold["abstaining_families"]
        assert fold["features_dropped_for_abstention"] == ["syn_attention"]
        assert fold["features_used"] == ["syn_momentum"]
        assert fold["metrics"]["n_dates"] == fold["n_test_dates"]
    assert (tmp_path / "arena_receipt.json").exists()
    assert (tmp_path / "coverage.csv").exists()


def test_run_arena_refuses_a_horizon_the_frame_does_not_carry(labels, registry,
                                                              fixture_frame):
    with pytest.raises(ARENA.FusionRefusal) as exc:
        ARENA.run_arena(labels, registry, features=["syn_momentum"],
                        feature_frame=fixture_frame, score_horizon=63)
    assert "chartered" in str(exc.value)


def test_run_arena_refuses_a_two_era_frame_before_it_scores_anything(registry):
    two_era = LABELS.build_labels(
        ARENA.synthetic_frame(price_bases=("adjusted", "unadjusted")))
    with pytest.raises(LABELS.PriceBasisPoolRefusal):
        ARENA.run_arena(two_era, registry, features=["syn_momentum"],
                        feature_frame=ARENA.synthetic_frame(
                            price_bases=("adjusted", "unadjusted")))


def test_the_selftest_passes_end_to_end_and_exercises_every_refusal(tmp_path):
    doc = ARENA.selftest(tmp_path)
    assert doc["ok"] is True, [s for s in doc["stages"] if not s["ok"]]
    assert len(doc["stages"]) == 11
    kinds = {line.split(":")[0] for line in doc["refusals_exercised"]}
    assert kinds == {"PriceBasisPoolRefusal", "PITRefusal",
                     "ForbiddenCompositeRefusal", "UnregisteredFeatureRefusal"}
    assert doc["real_registry"]["status"] == "loaded"


def test_the_selftest_is_deterministic(tmp_path):
    a = ARENA.selftest(tmp_path / "a")
    b = ARENA.selftest(tmp_path / "b")
    pick = lambda d: [s for s in d["stages"] if s["stage"] == "metrics"][0]["across_folds"]
    assert pick(a) == pick(b)


def test_the_cli_selftest_exits_zero(tmp_path):
    assert ARENA.main(["--selftest", "--out", str(tmp_path)]) == 0


def test_the_cli_survey_reports_the_refusals_without_raising(capsys):
    assert ARENA.main(["--survey"]) == 0
    out = capsys.readouterr().out
    assert "folds_usable=0" in out and "minimum-usable-fold" in out


def test_the_cli_check_registry_reads_the_shipped_file(capsys):
    assert ARENA.main(["--check-registry"]) == 0
    assert "registry ok" in capsys.readouterr().out
