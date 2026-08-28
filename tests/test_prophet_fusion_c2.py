"""The PR-2 C2 harness is enforced by this file, not by its own prose.

WHAT IS PINNED, AND WHY EACH CLAIM EXISTS.

  * DETERMINISM.  A research artifact nobody can reproduce is an anecdote.  Two runs of
    the same CLI over the same inputs must produce BYTE-IDENTICAL JSON — which is also
    why the report carries no wall-clock stamp.

  * REGISTERED BEFORE OUTCOMES (§8.2/§9.8).  The seeds, the grid, the model classes, the
    variance-floor echo and the BH test count must byte-PRECEDE every outcome block in
    the serialized document.  A multiplicity count written after the p-values were seen
    is not a registration, and byte offsets are the only form of that claim a reader can
    check without trusting anyone.

  * THE FOLD REFUSAL (§9.2), AND NO FALLBACK.  24 dates cannot satisfy 60 train / 10 test
    at a 21-session embargo.  The report must carry the refusal VERBATIM, expose NO
    coefficients, and — the part that actually matters — the fit function must RAISE when
    handed an empty fold plan.  A harness with an in-sample fallback reports the weaker
    number under the stronger number's name the first time someone forgets the caveat.

  * THE FAMILY BUDGET (§5.1/§10.6), STRUCTURALLY.  Every evidence column in the design
    matrix is one family's score.  A raw member column must RAISE by name — otherwise a
    family with four correlated siblings buys four votes and the anti-double-count budget
    is defeated by copy-paste.

  * THE GOVERNED SIGN.  Evidence coefficients are bounded >= 0 after orientation.  A
    planted ANTI-oriented family must be pinned at exactly 0.0: the fit may shrink a
    family to nothing, never re-point it against its filed direction on outcome data.

  * THE VARIANCE FLOOR (DSC:COVERAGE-FLOOR-MEASURES-PRESENCE-NOT-VARIANCE), BOTH HALVES.
    A near-constant member must read `vote_inert`; a genuinely sparse-but-VARIABLE member
    must PASS.  The second half is the falsifier — a floor that fails every sparse member
    is not measuring variance, it is measuring sparsity under a new name.  And the floor
    is READ FROM THE REGISTRY: moving the registry's number must move the verdict, or the
    amendment binds nothing.

  * THE RESIDUALIZER IS FROZEN.  Mutating TEST-fold outcomes must not move the fitted
    parameters' fingerprint.  That is a proof no test statistic reached the fit, not a
    promise that none did.

  * SIGN LAW (§9.5), STRUCTURALLY.  The census and design builders are handed a frame with
    the outcome columns removed and re-check it at entry; a builder that cannot reach the
    label cannot audition against it.

Run: python3 -m pytest tests/test_prophet_fusion_c2.py -q
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import prophet_fusion_c2 as c2                        # noqa: E402
from scripts.prophet_fusion_arena import (                         # noqa: E402
    FoldPlan, load_registry,
)
from scripts.prophet_fusion_labels import LabelFrame               # noqa: E402

LEDGER = ROOT / "data" / "us_board_ledger" / "retro_grades.parquet"
SNAPSHOTS = ROOT / "data" / "us_board_ledger" / "snapshots.jsonl"
REPORT_PATH = ROOT / "research" / "prophet_fusion" / "pr2_c2" / "report.json"
# These two are named in unrun-picks-boards exclusive paths. A new
# research/prophet_fusion path literal here must be named there too, or
# pack-1's curated-closure ratchet reds (legacy-job-workflow-yaml).
ERA_KEYS = ROOT / "research" / "prophet_fusion" / "pr2_c2" / "era_frame_keys.parquet"
ERA_PIN = ROOT / "research" / "prophet_fusion" / "pr2_c2" / "era_frame_pin.json"
PR1B_REPORT = (ROOT / "research" / "prophet_fusion" / "pr1b_baseline_race"
               / "report.json")

#: The sparse-worktree idiom the sibling suites use: `data/` is omitted by default
#: (`config/sparse_worktree.json`), so a real-frame test skips CLEANLY with the opt-in
#: command rather than failing as an artifact of the checkout.
NEEDS_REAL_FRAME = pytest.mark.skipif(
    not (LEDGER.exists() and SNAPSHOTS.exists()),
    reason=("real frame absent (sparse worktree omits data/); opt in with "
            "`python3 scripts/worktree_sparse.py full`"))


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def registry():
    return load_registry()


@pytest.fixture(scope="module")
def floor():
    return c2.load_variance_floor()


@pytest.fixture(scope="module")
def synthetic_bundle(tmp_path_factory):
    """ONE synthetic build, shared by every test that only inspects it.

    Built through the on-disk registry (``load_registry`` + ``load_variance_floor``), so
    the loaders are part of what these tests exercise rather than being bypassed.
    """
    target = tmp_path_factory.mktemp("c2_synth")
    registry_path = c2.write_synthetic_registry(target)
    syn_registry = load_registry(registry_path)
    syn_floor = c2.load_variance_floor(registry_path)
    flags = c2.registry_member_flags(registry_path)
    frame = c2.synthetic_c2_frame()
    census = c2.estimability_census(frame, syn_registry, syn_floor, member_flags=flags,
                                    serve_slab=None, serve_label="synthetic")
    scores, receipt = c2.build_family_scores(frame, census, membership="score")
    plan = c2.folds_for_labels(frame.labels, strict=False)
    return {"dir": target, "registry_path": registry_path, "registry": syn_registry,
            "floor": syn_floor, "frame": frame, "census": census, "scores": scores,
            "receipt": receipt, "plan": plan}


@pytest.fixture(scope="module")
def real_report():
    """ONE real-frame run, shared by every test that only INSPECTS the artifact."""
    if not (LEDGER.exists() and SNAPSHOTS.exists()):
        pytest.skip("real frame absent (sparse worktree omits data/)")
    return c2.run_c2()


@pytest.fixture(scope="module")
def real_census(real_report):
    return real_report["estimability_census"]


@pytest.fixture(scope="module")
def registered_report():
    """The COMMITTED PR-2 artifact — what was REGISTERED, never a live re-run.

    Construction of those same numbers is `era_report`: a rebuild from the LIVE ledger
    inner-joined to the committed (date, ticker, horizon) pin.  An as-of cutoff does
    not recover the vintage (maturation lands inside the window; DSC:GRADED-BOARD-
    LEDGER-ACCRUES-BY-HORIZON).  Structural claims that hold at ANY vintage keep using
    `real_report`.
    """
    if not REPORT_PATH.exists():
        pytest.skip("PR-2 report not committed yet")
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def registered_census(registered_report):
    return registered_report["estimability_census"]


def _pin_ledger_to_registered_era(raw: pd.DataFrame, keys: pd.DataFrame) -> pd.DataFrame:
    """Keep live rows whose (date, ticker, horizon) was in the PR-2 frame.

    Unique tickers per date are unchanged by maturation; only later horizons accrue.
    Inner-joining on that grain recovers the registered 4,077 rows from the grown
    ledger without rewriting ``data/`` and without an as-of cutoff.
    """
    work = raw.copy()
    work["_pin_date"] = work["as_of"].astype(str).str.slice(0, 10)
    work["_pin_ticker"] = work["ticker"].astype(str)
    work["_pin_h"] = work["horizon"].astype(int)
    pin = keys.rename(columns={"date": "_pin_date", "ticker": "_pin_ticker",
                               "horizon": "_pin_h"})
    pinned = work.merge(pin, on=["_pin_date", "_pin_ticker", "_pin_h"], how="inner")
    return pinned.drop(columns=["_pin_date", "_pin_ticker", "_pin_h"])


def _snapshots_for_dates(src: Path, dates: set[str], dest: Path) -> Path:
    """Keep snapshot payloads for the pinned era's board dates only."""
    with src.open(encoding="utf-8") as handle, dest.open("w", encoding="utf-8") as out:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            as_of = str(doc.get("as_of") or "")[:10]
            if as_of in dates:
                out.write(line)
                out.write("\n")
    return dest


@pytest.fixture(scope="module")
def era_report(tmp_path_factory):
    """Rebuild C2 on the PR-1b / PR-2 registered-era frame, not the grown live ledger.

    DEC:FUSION-C2-TEST-ERA-IS-REGISTERED-VINTAGE — Option B.  Published research
    numbers stay frozen; the harness is re-run against the row-identity pin.
    """
    if not (LEDGER.exists() and SNAPSHOTS.exists() and ERA_KEYS.exists()
            and ERA_PIN.exists()):
        pytest.skip("real frame or era pin absent (sparse worktree omits data/); "
                    "opt in with `python3 scripts/worktree_sparse.py add data`")
    pin = json.loads(ERA_PIN.read_text(encoding="utf-8"))
    keys = pd.read_parquet(ERA_KEYS)
    raw = _pin_ledger_to_registered_era(pd.read_parquet(LEDGER), keys)
    assert len(raw) == pin["n_rows_expected"], (
        f"era pin recovered {len(raw)} rows, registered {pin['n_rows_expected']} — "
        "a rewrite of settled grade keys, not lawful accrual")
    dest = tmp_path_factory.mktemp("c2_era") / "snapshots.jsonl"
    dates = set(keys["date"].astype(str))
    _snapshots_for_dates(SNAPSHOTS, dates, dest)
    return c2.run_c2(raw=raw, snapshots_path=dest)


@pytest.fixture(scope="module")
def era_census(era_report):
    return era_report["estimability_census"]


def _all_keys(node) -> set[str]:
    """Every mapping KEY in a nested document.

    Used instead of a substring scan because the REGISTERED block legitimately describes
    the penalty on the coefficients in prose — registering how a fit would be penalized is
    not the same act as publishing a fitted number, and a test that cannot tell them apart
    would force the registration to go unwritten.
    """
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(str(key))
            found |= _all_keys(value)
    elif isinstance(node, list):
        for value in node:
            found |= _all_keys(value)
    return found


def _run_cli(out_dir: Path) -> Path:
    result = subprocess.run(
        [sys.executable, "-m", "scripts.prophet_fusion_c2", "--out", str(out_dir)],
        cwd=str(ROOT), capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr[-3000:]
    return out_dir / "report.json"


# --------------------------------------------------------------------------- #
# 1. determinism
# --------------------------------------------------------------------------- #

class TestDeterminism:
    @NEEDS_REAL_FRAME
    def test_report_is_byte_identical_across_runs(self, tmp_path):
        """A research artifact nobody can reproduce is an anecdote."""
        first = _run_cli(tmp_path / "one")
        second = _run_cli(tmp_path / "two")
        assert first.read_bytes() == second.read_bytes()

    @NEEDS_REAL_FRAME
    def test_report_carries_no_wall_clock(self, real_report):
        """The determinism above is only possible because of this; pin it directly."""
        blob = json.dumps(real_report)
        for banned in ("generated_at", "timestamp", "run_at", "as_of_utc", "created_at",
                       "produced_at"):
            assert f'"{banned}"' not in blob, (
                f"{banned!r} would make the artifact non-reproducible; the date belongs "
                f"in the doc and in git")

    def test_the_module_never_reads_the_wall_clock(self):
        """Structural: no clock call can leak into a report-bound value if none exists."""
        source = (ROOT / "scripts" / "prophet_fusion_c2.py").read_text(encoding="utf-8")
        for banned in ("datetime.now", "datetime.utcnow", "time.time(", "date.today"):
            assert banned not in source, f"{banned} in a module whose artifact must be reproducible"


# --------------------------------------------------------------------------- #
# 2. registered before outcomes
# --------------------------------------------------------------------------- #

class TestRegisteredBeforeOutcomes:
    @NEEDS_REAL_FRAME
    def test_registered_block_byte_precedes_outcome_blocks(self, tmp_path, real_report):
        """Byte offsets, because that is the only form of this claim a reader can check."""
        path = c2.write_report(real_report, tmp_path)
        blob = path.read_text(encoding="utf-8")
        registered = blob.index('"registered"')
        for outcome in ('"estimability_census"', '"redundancy"', '"cmi"',
                        '"incremental"', '"what_does_x_add"', '"c2_fit"'):
            assert registered < blob.index(outcome), (
                f"{outcome} precedes the registered block — a grid, a seed or a "
                f"multiplicity count written after the outcomes is not a registration")
        assert blob.index('"cmi"') < blob.index('"what_does_x_add"')

    @NEEDS_REAL_FRAME
    def test_registered_block_carries_the_whole_registration(self, real_report):
        registered = real_report["registered"]
        assert registered["seeds"]["bootstrap"] == 20260814
        assert registered["seeds"]["cmi_permutation"] == 20260818
        assert "NONE" in registered["seeds"]["c2_inner_split"]
        assert registered["grid"]["alpha"] == list(c2.C2_ALPHAS)
        assert registered["grid"]["l1_ratio"] == list(c2.C2_L1_RATIOS)
        assert registered["grid"]["size"] == 9
        assert registered["c2_model_classes"] == list(c2.C2_MODEL_CLASSES)
        assert isinstance(registered["fdr"]["n_tests"], int)
        assert registered["variance_floor_spec"]["min_dates_with_variation_share"] == 0.5
        assert registered["redundancy_cell_minimums"][
            "min_non_null_pairs_within_a_date"] == 30


# --------------------------------------------------------------------------- #
# 3. the §9.2 fold refusal, and the absence of a fallback
# --------------------------------------------------------------------------- #

class TestFoldRefusal:
    @NEEDS_REAL_FRAME
    def test_real_frame_refuses_and_embeds_verbatim(self, real_report):
        fit = real_report["c2_fit"]
        assert fit["status"] == "refused_no_lawful_folds"
        assert fit["n_usable_folds"] == 0
        verbatim = fit["refusal_verbatim"]
        assert "§9.2 minimum-usable-fold" in verbatim
        assert "minimum 60" in verbatim and "minimum 10" in verbatim
        assert "horizon=21 embargo=21" in verbatim
        assert "never silently shrinks one" in verbatim
        assert not (_all_keys(fit) & {"coefficients", "evidence_coefficients"}), (
            "a refused fit that still printed coefficients would be an in-sample read "
            "wearing a cross-fitted label")
        assert real_report["incremental"]["crossfit"]["status"] == "refused_no_lawful_folds"
        assert real_report["folds"]["n_usable_folds"] == 0

    def test_no_in_sample_fallback_exists(self, synthetic_bundle):
        """The fit seam RAISES on an empty fold plan — there is no other branch."""
        bundle = synthetic_bundle
        with pytest.raises(c2.FitRefusal, match="ZERO usable folds"):
            c2.fit_c2_over_folds(bundle["frame"], bundle["registry"], bundle["census"],
                                 [], head="elastic_net_logistic_nonneg")
        with pytest.raises(c2.FitRefusal, match="ZERO usable folds"):
            c2.crossfit_incremental(bundle["frame"], bundle["scores"], [],
                                    families=c2.census_families_in_score(bundle["census"]))

    def test_the_refusal_path_emits_the_would_have_entered_receipt(self, synthetic_bundle):
        """A refusal that does not say what it refused to fit is unfalsifiable."""
        bundle = synthetic_bundle
        empty = FoldPlan(folds=[], refusals=[{"message": "synthetic refusal"}], receipt={})
        block = c2.c2_fit_block(bundle["frame"], bundle["registry"], bundle["census"],
                                empty)
        assert block["status"] == "refused_no_lawful_folds"
        assert block["refusal_verbatim"] == "synthetic refusal"
        assert block["would_have_entered"]["families"]
        assert not (_all_keys(block) & {"coefficients", "evidence_coefficients"})


# --------------------------------------------------------------------------- #
# 4. the family budget (§10.6)
# --------------------------------------------------------------------------- #

class TestFamilyBudget:
    def test_design_matrix_is_one_column_per_family_plus_missingness(self,
                                                                    synthetic_bundle):
        bundle = synthetic_bundle
        design = c2.build_design_matrix(bundle["frame"], bundle["registry"],
                                        bundle["census"])
        families = c2.census_families_in_design(bundle["census"])
        assert design.columns[0] == "intercept"
        assert list(design.columns[1:1 + len(families)]) == [f"{f}__score" for f in families]
        assert list(design.columns[1 + len(families):]) == [f"{f}__absent" for f in families]
        assert design.matrix.shape[1] == 1 + 2 * len(families)
        # Every evidence column maps 1:1 onto a family; no member column survives.
        for column in design.columns[1:1 + len(families)]:
            assert column.removesuffix("__score") in bundle["census"]["families"]
        for member in bundle["registry"].columns:
            assert member not in design.columns

    def test_a_raw_member_column_raises_by_name(self, synthetic_bundle):
        """The budget is defeated by copy-paste unless this raises."""
        bundle = synthetic_bundle
        families = c2.census_families_in_design(bundle["census"])
        with pytest.raises(c2.DesignMatrixRefusal, match="raw MEMBER column"):
            c2.assert_family_grain(["syn_pos"], bundle["registry"], families)
        smuggled = bundle["scores"].copy()
        smuggled["syn_pos"] = 0.5                      # a raw member column, injected
        with pytest.raises(c2.DesignMatrixRefusal, match="raw MEMBER column"):
            c2.build_design_matrix(bundle["frame"], bundle["registry"], bundle["census"],
                                   fam_scores=smuggled,
                                   missing=bundle["receipt"]["missing"])

    def test_a_family_with_two_members_still_buys_one_column(self, synthetic_bundle):
        """The planted family carries a correlated sibling and still gets ONE vote."""
        bundle = synthetic_bundle
        body = bundle["census"]["families"]["FP_PLANTED_POSITIVE"]
        assert len(body["design_matrix_members"]) == 2
        design = c2.build_design_matrix(bundle["frame"], bundle["registry"],
                                        bundle["census"])
        assert sum(1 for c in design.columns if c.startswith("FP_PLANTED_POSITIVE")) == 2
        assert "FP_PLANTED_POSITIVE__score" in design.columns
        assert "FP_PLANTED_POSITIVE__absent" in design.columns


# --------------------------------------------------------------------------- #
# 5. the sign law, structurally
# --------------------------------------------------------------------------- #

class TestSignLaw:
    def test_builders_never_see_outcomes(self, synthetic_bundle, floor):
        """Hand a builder an outcome column and it must RAISE (§9.5)."""
        bundle = synthetic_bundle
        leaked = bundle["frame"].features.copy()
        leaked["excess_spy"] = 0.01
        poisoned = c2.C2Frame(features=leaked, outcomes=bundle["frame"].outcomes,
                              g0=bundle["frame"].g0, signs=bundle["frame"].signs,
                              labels=bundle["frame"].labels)
        flags = c2.registry_member_flags(bundle["registry_path"])
        with pytest.raises(Exception, match="outcome column"):
            c2.estimability_census(poisoned, bundle["registry"], bundle["floor"],
                                   member_flags=flags)
        with pytest.raises(Exception, match="outcome column"):
            c2.build_design_matrix(poisoned, bundle["registry"], bundle["census"])
        with pytest.raises(Exception, match="outcome column"):
            c2.member_percentiles(poisoned, ["syn_pos"])

    def test_an_unsigned_column_cannot_be_aggregated(self, synthetic_bundle):
        """Reading a direction off this frame's outcomes is the audition §9.8 forbids."""
        bundle = synthetic_bundle
        with pytest.raises(c2.C2Refusal, match="no REGISTERED sign"):
            c2.member_percentiles(bundle["frame"], ["syn_unsigned"])


# --------------------------------------------------------------------------- #
# 6. the governed non-negativity bound
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def fitted_heads(synthetic_bundle):
    bundle = synthetic_bundle
    return {head: c2.fit_c2_over_folds(bundle["frame"], bundle["registry"],
                                       bundle["census"], bundle["plan"].folds, head=head)
            for head in c2.C2_MODEL_CLASSES}


class TestSignConstraint:
    @pytest.mark.parametrize("head", list(c2.C2_MODEL_CLASSES))
    def test_anti_oriented_family_pins_at_zero(self, fitted_heads, head):
        rows = [r for r in fitted_heads[head]["folds"] if r["status"] == "fitted"]
        assert rows
        for row in rows:
            coefficient = row["evidence_coefficients"]["FA_ANTI_ORIENTED__score"]
            assert float(coefficient) == 0.0, (
                "the anti-oriented family's coefficient escaped the w>=0 bound — the fit "
                "re-pointed a governed family against its filed direction on outcome data")
            assert "FA_ANTI_ORIENTED__score" in row[
                "coefficients_pinned_at_zero_by_the_nonneg_bound"]

    @pytest.mark.parametrize("head", list(c2.C2_MODEL_CLASSES))
    def test_planted_positive_family_recovers_positive_coef(self, fitted_heads, head):
        rows = [r for r in fitted_heads[head]["folds"] if r["status"] == "fitted"]
        for row in rows:
            assert row["evidence_coefficients"]["FP_PLANTED_POSITIVE__score"] > 0.0

    def test_the_inner_grid_choice_is_recorded_and_inside_the_registered_grid(
        self, fitted_heads
    ):
        for head, fitted in fitted_heads.items():
            for row in fitted["folds"]:
                if row["status"] != "fitted":
                    continue
                chosen = row["inner_selection"]["chosen"]
                assert chosen["alpha"] in c2.C2_ALPHAS
                assert chosen["l1_ratio"] in c2.C2_L1_RATIOS
                assert len(row["inner_selection"]["grid"]) == c2.C2_GRID_SIZE
                assert row["inner_selection"]["embargo_dates_between"] == c2.PRIMARY_HORIZON

    def test_dropping_the_bound_would_let_the_anti_family_go_negative(self,
                                                                     synthetic_bundle):
        """The bound is load-bearing, not decorative — prove the unbounded fit differs."""
        bundle = synthetic_bundle
        design = c2.build_design_matrix(bundle["frame"], bundle["registry"],
                                        bundle["census"])
        outcome = bundle["frame"].outcome_slice(c2.PRIMARY_HORIZON)
        joined = design.keys.merge(outcome, on=["date", "ticker"], how="left")
        y = (pd.to_numeric(joined["excess_spy"], errors="coerce") > 0).to_numpy("float64")
        index = design.columns.index("FA_ANTI_ORIENTED__score")
        unbounded = c2.fit_c2_head(design.matrix, y, design.dates,
                                   head="elastic_net_logistic_nonneg", alpha=0.0,
                                   l1_ratio=0.0, evidence_index=(),
                                   missingness_index=design.missingness_index)
        assert unbounded["theta"][index] < 0.0, (
            "the fixture's anti-oriented family is not actually anti-correlated, so the "
            "bound test above would pass vacuously")


# --------------------------------------------------------------------------- #
# 7. the variance floor — BOTH halves of the DSC falsifier
# --------------------------------------------------------------------------- #

def _member(census, family):
    return census["families"][family]["members"][0]


class TestVarianceFloor:
    def test_near_constant_member_is_vote_inert(self, synthetic_bundle):
        member = _member(synthetic_bundle["census"], "FI_NEAR_CONSTANT")
        axis = member["variance_axis"]["syn_inert"]
        assert member["vote_inert"] is True
        assert "vote_inert" in member["reasons"]
        assert axis["variation_share"] < 0.5
        assert member["in_family_score"] is False
        assert member["in_design_matrix"] is False

    def test_sparse_but_variable_member_passes(self, synthetic_bundle):
        """The falsifier's own acceptance test: sparsity alone must NOT fail the floor."""
        member = _member(synthetic_bundle["census"], "FS_SPARSE_VARIABLE")
        axis = member["variance_axis"]["syn_sparse"]
        assert member["vote_inert"] is False
        assert member["in_family_score"] is True
        assert axis["variation_share"] >= 0.5
        fired = (synthetic_bundle["frame"].features["syn_sparse"] == True).mean()  # noqa: E712
        assert 0.02 <= float(fired) <= 0.10, (
            "the fixture's 'sparse' member is not sparse, so this half proves nothing")

    def test_floor_is_read_from_registry_not_hardcoded(self, tmp_path):
        """Move the registry's number and the verdict must move with it."""
        strict_dir = tmp_path / "strict"
        strict_dir.mkdir()
        strict_path = c2.write_synthetic_registry(
            strict_dir, overrides={"min_dates_with_variation_share": 0.99})
        strict_floor = c2.load_variance_floor(strict_path)
        assert strict_floor.min_dates_with_variation_share == 0.99
        registry = load_registry(strict_path)
        flags = c2.registry_member_flags(strict_path)
        frame = c2.synthetic_c2_frame()
        census = c2.estimability_census(frame, registry, strict_floor, member_flags=flags,
                                        serve_slab=None)
        member = _member(census, "FS_SPARSE_VARIABLE")
        assert member["vote_inert"] is True, (
            "the sparse-but-variable member survived a 0.99 floor — the harness is not "
            "reading the registry's number at all")

    def test_a_registry_without_the_block_refuses(self, tmp_path):
        """Fail closed: a silently defaulted floor is an amendment that binds nothing."""
        doc = yaml.safe_load(
            (ROOT / "research" / "prophet_fusion" / "families.yml").read_text("utf-8"))
        doc["semantics"].pop("variance_floor_spec")
        path = tmp_path / "no_floor.yml"
        path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
        with pytest.raises(c2.C2Refusal, match="variance_floor_spec is missing"):
            c2.load_variance_floor(path)

    @NEEDS_REAL_FRAME
    def test_news_burst_is_vote_inert_on_the_real_frame(self, real_census):
        """The measured PR-1b pathology the amendment exists for — PRINTED, not asserted."""
        member = next(m for m in real_census["families"]["F8_ATTENTION_CROWDING"]["members"]
                      if m["vote_column"] == "news_burst")
        assert member["vote_inert"] is True
        assert member["in_family_score"] is False
        assert member["variance_axis"]["news_burst"]["variation_share"] < 0.5
        # DISCLOSED, never hidden: the inert member still appears in the census and in the
        # redundancy matrices (registry variance_floor_spec.retained_in).
        assert member["coverage"]["used_for_floor"] >= 0.5


# --------------------------------------------------------------------------- #
# 8. serving-dead exclusion
# --------------------------------------------------------------------------- #

class TestServingDead:
    @NEEDS_REAL_FRAME
    def test_insider_cluster_is_excluded_from_fit_with_reason(self, real_report,
                                                              real_census):
        member = next(m for m in real_census["families"]["F5_FLOW_POSITIONING"]["members"]
                      if m["member"] == "F5_FLOW_POSITIONING.insider_panel")
        assert member["serving_dead"] is True
        assert member["reasons"] == ["serving_dead"]
        assert member["in_design_matrix"] is False
        # C1 RACED IT; C2 MAY NOT FIT IT.  Both dispositions in one row.
        assert member["in_family_score"] is True
        excluded = real_report["c2_fit"]["would_have_entered"]["excluded_members"]
        row = next(r for r in excluded if r["member"] == "F5_FLOW_POSITIONING.insider_panel")
        assert "serving_dead" in row["reasons"]
        assert "insider_cluster" not in real_report["c2_fit"]["would_have_entered"][
            "members_per_family"]["F5_FLOW_POSITIONING"]

    @NEEDS_REAL_FRAME
    def test_the_f5_row_carries_the_member_level_dispositions(self, real_report):
        row = next(r for r in real_report["what_does_x_add"]["rows"]
                   if r["family"] == "F5_FLOW_POSITIONING")
        detail = {m["member"]: m for m in row["members"]}
        insider = detail["F5_FLOW_POSITIONING.insider_panel"]
        assert insider["c1_raced"] is True and insider["c2_fit_eligible"] is False
        chip = detail["F5_FLOW_POSITIONING.smart_money_board_chip"]
        assert chip["c1_raced"] is True and chip["c2_fit_eligible"] is True


# --------------------------------------------------------------------------- #
# 9. conditional mutual information
# --------------------------------------------------------------------------- #

class TestCMI:
    def test_below_minimums_refuses_not_estimable(self):
        thin = pd.DataFrame({
            "date": ["d1"] * 20 + ["d2"] * 20,
            "x_bin": [0.0, 1.0, 2.0, 1.0] * 10,
            "z_bin": [0.0, 1.0, 2.0, 0.0] * 10,
            "y": [1.0, 0.0] * 20,
        })
        cell = c2.cmi_cell(thin, family="FX", horizon=10, b=5)
        assert cell["status"] == "NOT_ESTIMABLE"
        assert "40 measured rows < 300" in cell["reason"]
        assert "2 dates < 8" in cell["reason"]
        assert cell["n_rows"] == 40 and cell["n_dates"] == 2

    def test_an_empty_z_bin_refuses(self):
        frame = pd.DataFrame({
            "date": [f"d{i//40:02d}" for i in range(400)],
            "x_bin": [float(i % 3) for i in range(400)],
            "z_bin": [float(i % 2) for i in range(400)],     # bin 2 never occurs
            "y": [float(i % 2) for i in range(400)],
        })
        cell = c2.cmi_cell(frame, family="FX", horizon=10, b=5)
        assert cell["status"] == "NOT_ESTIMABLE"
        assert "Z-bin(s) [2] empty" in cell["reason"]

    @NEEDS_REAL_FRAME
    def test_h21_refuses_on_real_frame(self, era_report):
        """7 graded dates at H=21 cannot support the estimator; print it, do not fit it."""
        cells = [c for c in era_report["cmi"]["cells"] if c["horizon"] == 21]
        assert cells
        for cell in cells:
            assert cell["status"] == "NOT_ESTIMABLE"
            assert "7 dates < 8" in cell["reason"]

    @NEEDS_REAL_FRAME
    def test_primary_horizon_is_estimable_and_carries_its_null(self, real_report):
        cells = [c for c in real_report["cmi"]["cells"]
                 if c["horizon"] == c2.PRIMARY_HORIZON]
        assert cells and all(c["status"] == "estimated" for c in cells)
        for cell in cells:
            assert cell["permutation_seed"] == 20260818
            assert cell["null_mean_bits"] is not None
            assert cell["excess_bits"] is not None
            assert 0.0 <= cell["p_one_sided"] <= 1.0
            assert cell["tier"] == "descriptive_in_sample_counterfactual"

    def test_permutation_null_is_seeded(self, synthetic_bundle):
        bundle = synthetic_bundle
        first = c2.cmi_block(bundle["frame"], bundle["scores"],
                             families=["FP_PLANTED_POSITIVE"], b=40)
        second = c2.cmi_block(bundle["frame"], bundle["scores"],
                              families=["FP_PLANTED_POSITIVE"], b=40)
        assert [c["null_mean_bits"] for c in first["cells"]] == \
               [c["null_mean_bits"] for c in second["cells"]]
        other = c2.cmi_block(bundle["frame"], bundle["scores"],
                             families=["FP_PLANTED_POSITIVE"], b=40, seed=1234)
        assert [c["null_mean_bits"] for c in other["cells"]] != \
               [c["null_mean_bits"] for c in first["cells"]]

    def test_permutation_is_stratified_within_date_and_z_bin(self):
        """The null must destroy the X-Y association and NOTHING else."""
        rng = np.random.default_rng(7)
        values = rng.integers(0, 3, size=600)
        strata = rng.integers(0, 12, size=600)
        permuted = c2.permute_within_strata(values, strata, rng)
        assert not np.array_equal(values, permuted)
        for stratum in np.unique(strata):
            mask = strata == stratum
            assert sorted(values[mask].tolist()) == sorted(permuted[mask].tolist()), (
                "the permutation moved a value across strata — that destroys the X-Z "
                "dependence the statistic conditions on, so the null would be testing a "
                "different hypothesis than the observed statistic")


# --------------------------------------------------------------------------- #
# 10. the cross-fitted residualization harness
# --------------------------------------------------------------------------- #

class TestCrossfit:
    def test_residualizer_params_frozen_against_test_mutation(self, synthetic_bundle):
        bundle = synthetic_bundle
        fold = bundle["plan"].folds[0]
        work = c2._residual_frame(bundle["frame"], bundle["scores"], c2.PRIMARY_HORIZON)
        before = c2.Residualizer().fit(work[work["date"].isin(set(fold.train_dates))])

        mutated = bundle["frame"].outcomes.copy()
        mask = mutated["date"].isin(set(fold.test_dates))
        assert int(mask.sum()) > 0
        mutated.loc[mask, "excess_spy"] = mutated.loc[mask, "excess_spy"] * -11.0 + 5.0
        poisoned = c2.C2Frame(features=bundle["frame"].features, outcomes=mutated,
                              g0=bundle["frame"].g0, signs=bundle["frame"].signs,
                              labels=LabelFrame(frame=mutated.copy(), receipt={}))
        after_frame = c2._residual_frame(poisoned, bundle["scores"], c2.PRIMARY_HORIZON)
        after = c2.Residualizer().fit(
            after_frame[after_frame["date"].isin(set(fold.train_dates))])

        assert before.fingerprint() == after.fingerprint(), (
            "the residualizer's frozen parameters moved when TEST-fold outcomes moved — "
            "a test statistic reached the fit")
        assert before.params == after.params

    def test_a_residualizer_refuses_to_refit(self, synthetic_bundle):
        bundle = synthetic_bundle
        fold = bundle["plan"].folds[0]
        work = c2._residual_frame(bundle["frame"], bundle["scores"], c2.PRIMARY_HORIZON)
        train = work[work["date"].isin(set(fold.train_dates))]
        fitted = c2.Residualizer().fit(train)
        with pytest.raises(c2.C2Refusal, match="already fitted"):
            fitted.fit(train)

    def test_planted_incremental_recovered_and_noise_covers_zero(self, synthetic_bundle):
        bundle = synthetic_bundle
        families = c2.census_families_in_score(bundle["census"])
        result = c2.crossfit_incremental(bundle["frame"], bundle["scores"],
                                         bundle["plan"].folds, families=families,
                                         bootstrap_b=400)
        planted = result["per_family"]["FP_PLANTED_POSITIVE"]
        noise = result["per_family"]["FN_PURE_NOISE"]
        assert planted["mean"] > 0 and planted["ci95"][0] > 0, (
            "the harness did not recover a family that was planted with a real edge")
        assert noise["ci95"][0] <= 0 <= noise["ci95"][1], (
            "the harness manufactured an incremental effect for a pure-noise family")
        for row in result["folds"]:
            if row["status"] == "fitted":
                assert set(row["residualizer"]["params"]) == {"a", "b"}
                assert row["residualizer"]["fingerprint"]


# --------------------------------------------------------------------------- #
# 11. BH-FDR bookkeeping
# --------------------------------------------------------------------------- #

def _fixture_inputs(pvalues, effects):
    """A minimal census/descriptive/cmi triple with KNOWN p-values.

    Deliberately routed through the module's OWN table builder rather than through
    race.benjamini_hochberg: what is being pinned is that `what_does_x_add` consumes the
    p-vector it registered and applies the adjustment, not that BH itself is correct
    (race's suite owns that).
    """
    families = {}
    cells = []
    for index, (p, effect) in enumerate(zip(pvalues, effects)):
        key = f"FX{index}"
        families[key] = {
            "family": key, "name": key, "coverage_floor": 0.5, "n_members": 1,
            "n_members_wired": 1, "eligible_for_design_matrix": True,
            "design_matrix_members": [f"col{index}"],
            "family_score_members": [f"col{index}"], "structural_note": None,
            "members": [{"member": f"{key}.m", "family": key, "columns": [f"col{index}"],
                         "columns_present_on_frame": [f"col{index}"],
                         "vote_column": f"col{index}", "verdict": "eligible",
                         "reasons": ["eligible"], "in_family_score": True,
                         "in_design_matrix": True, "variance_axis": {}, "vote_inert": False,
                         "cross_sectional": True}],
        }
        cells.append({
            "family": key, "horizon": c2.PRIMARY_HORIZON,
            "tier": "descriptive_in_sample_counterfactual", "n_rows": 500,
            "spearman_vs_outcome": {"mean": effect, "ci95": [None, None]},
            "partial_spearman_given_g0": {"mean": effect, "ci95": [effect - 0.01,
                                                                  effect + 0.01]},
            "status": "estimated",
            "p_t": p, "p_normal": p / 2.0, "t_stat": 2.0, "df": 19,
            "p_method": "fixture", "n_dates_partial": 20,
            "min_dates": c2.DESCRIPTIVE_MIN_DATES,
        })
    census = {"families": families}
    descriptive = {"cells": cells}
    cmi = {"cells": []}
    power = {"minimum_detectable_delta_p_at_5_inherited": 0.174}
    return census, descriptive, cmi, power


class TestFDR:
    def test_bh_bookkeeping_matches_registered_count(self):
        # The vector is chosen so a MISSING adjustment changes the answer: p=0.04 clears a
        # raw alpha=0.05 and does NOT clear BH's threshold.  A fixture where raw and
        # adjusted agree would let the adjustment be deleted without reddening anything.
        pvalues = [0.001, 0.02, 0.04, 0.80]
        effects = [0.15, -0.12, 0.02, -0.01]
        census, descriptive, cmi, power = _fixture_inputs(pvalues, effects)
        table = c2.what_does_x_add(census, descriptive, cmi, "refused_no_lawful_folds",
                                   power, n_tests=len(pvalues))
        assert table["n_tests_registered"] == table["n_tests_consumed"] == 4
        verdicts = {row["family"]: row["verdict"] for row in table["rows"]}
        # BH at alpha=0.05 over [0.001, 0.02, 0.04, 0.80]: i/m*alpha = [.0125, .025,
        # .0375, .05]; the largest i passing is i=2 (0.02 <= 0.025), so the first two
        # reject and p=0.04 does NOT — where an unadjusted table would have rejected it.
        assert verdicts["FX0"] == "incremental_positive"
        assert verdicts["FX1"] == "incremental_negative"
        assert verdicts["FX2"] == "null_unresolved", (
            "p=0.04 was rejected — the BH adjustment was skipped and the raw alpha used")
        assert verdicts["FX3"] == "null_unresolved"
        assert table["n_rejections"] == 2
        adjusted = {row["family"]: row["p_adj"] for row in table["rows"]}
        assert adjusted["FX2"] > 0.04, "p_adj must exceed the raw p under BH"
        # The verdict keys on p_t; p_normal rides beside it and is never read.
        for row in table["rows"]:
            assert row["verdict_keys_on"] == "p_t"
            assert row["p_t"] is not None and row["p_normal"] is not None
            assert row["p_t"] != row["p_normal"], (
                "the fixture's two references are identical, so this test could not "
                "detect the table reading the wrong one")

    def test_skipping_the_adjustment_would_change_the_verdicts(self):
        """The adjustment is load-bearing: a raw-p table would reject a third family."""
        pvalues = [0.001, 0.02, 0.04, 0.80]
        census, descriptive, cmi, power = _fixture_inputs(pvalues, [0.1] * 4)
        table = c2.what_does_x_add(census, descriptive, cmi, "refused", power, n_tests=4)
        assert table["n_rejections"] == 2
        assert sum(1 for p in pvalues if p <= 0.05) == 3

    def test_a_mismatched_registered_count_raises(self):
        census, descriptive, cmi, power = _fixture_inputs([0.01, 0.5], [0.1, 0.1])
        with pytest.raises(c2.C2Refusal, match="BH bookkeeping breach"):
            c2.what_does_x_add(census, descriptive, cmi, "refused", power, n_tests=7)

    @NEEDS_REAL_FRAME
    def test_the_registered_count_comes_from_the_feature_side_census(self, real_report):
        registered = real_report["registered"]["fdr"]["n_tests"]
        table = real_report["what_does_x_add"]
        assert registered == table["n_tests_registered"] == table["n_tests_consumed"]
        assert registered == len(c2.census_families_in_score(
            real_report["estimability_census"]))

    @NEEDS_REAL_FRAME
    def test_secondary_horizons_are_bookkept_separately(self, real_report):
        secondary = real_report["what_does_x_add_secondary_horizons"]
        assert set(secondary) == {"5", "21"}
        for body in secondary.values():
            assert body["tier"] == "secondary"
            assert "SEPARATELY BOOKKEPT" in body["law"]


# --------------------------------------------------------------------------- #
# 12. the governed table
# --------------------------------------------------------------------------- #

class TestWhatDoesXAddTable:
    @NEEDS_REAL_FRAME
    def test_every_family_has_a_row_with_verdict_tier_and_power(self, real_report,
                                                                registry):
        rows = real_report["what_does_x_add"]["rows"]
        assert {row["family"] for row in rows} == set(registry.families)
        for row in rows:
            assert row["verdict"] in c2.VERDICT_VOCABULARY
            assert row["tier"]
            assert row["power_note"] and "REFUSED" in row["power_note"]
            assert row["crossfit_status"] == "refused_no_lawful_folds"
            assert "cmi" in row
            assert row["reason"]

    @NEEDS_REAL_FRAME
    def test_verdict_vocabulary_is_closed(self, real_report):
        seen = {row["verdict"] for row in real_report["what_does_x_add"]["rows"]}
        assert seen <= set(c2.VERDICT_VOCABULARY)
        assert real_report["what_does_x_add"]["vocabulary"] == list(c2.VERDICT_VOCABULARY)

    @NEEDS_REAL_FRAME
    def test_the_structural_and_the_absent_are_not_blurred(self, real_report):
        rows = {row["family"]: row for row in real_report["what_does_x_add"]["rows"]}
        assert rows["F6_MACRO_REGIME"]["verdict"] == "not_estimable"
        assert "structurally_excluded" in rows["F6_MACRO_REGIME"]["sub_reasons"]
        for family in ("F3_THEME_STRUCTURE", "F7_QUALITY_FUNDAMENTAL"):
            assert rows[family]["verdict"] == "insufficient_coverage"
            assert "absent_from_frame" in rows[family]["sub_reasons"]
        assert rows["F8_ATTENTION_CROWDING"]["verdict"] == "not_estimable"
        assert "vote_inert" in rows["F8_ATTENTION_CROWDING"]["sub_reasons"]

    @NEEDS_REAL_FRAME
    def test_the_descriptive_tier_reproduces_pr1b_section_9_4(self, era_report):
        """Parity is asserted against the PR-1b ARTIFACT, never against typed literals.

        A hand-copied number pins the transcription, not the construction: if PR-1b is
        ever re-run and its own cells move, a literal keeps passing while the two
        artifacts silently disagree. Both reports are on disk — compare them.
        Construction here is the era-pinned rebuild, not the grown live ledger.
        """
        pr1b = json.loads(PR1B_REPORT.read_text(encoding="utf-8"))
        theirs = {row["family"]: row for row in
                  pr1b["c1_analysis"]["incremental_over_champion"]}
        ours = {cell["family"]: cell for cell in
                era_report["incremental"]["descriptive"]["score_membership"]["cells"]
                if cell["horizon"] == c2.PRIMARY_HORIZON}
        shared = sorted(set(theirs) & set(ours))
        assert shared, "no family is present in both artifacts — parity is unasserted"
        for family in shared:
            for block in ("partial_spearman_given_g0", "spearman_vs_outcome"):
                assert ours[family][block]["mean"] == pytest.approx(
                    theirs[family][block]["mean"], abs=5e-4), (
                    f"{family}.{block} diverged from PR-1b's committed artifact — the "
                    f"score-membership construction is supposed to BE PR-1b §9.4's")
                assert ours[family][block]["n_dates"] == theirs[family][block]["n_dates"]

    @NEEDS_REAL_FRAME
    def test_the_verdict_keys_on_t_and_both_references_are_printed(self, era_report):
        """F-1: the normal reference decided the draft's only rejection. Pin the fix."""
        table = era_report["what_does_x_add"]
        assert table["verdict_keys_on"] == "p_t"
        assert "t" in table["p_method"] and "not immaterial" in table["p_method"].lower()
        measured = [row for row in table["rows"] if row["p_t"] is not None]
        assert measured
        for row in measured:
            assert row["p_normal"] is not None
            assert row["verdict_keys_on"] == "p_t"
            # The t is the more conservative reference at these block counts; if a row
            # ever showed p_t < p_normal the instrument would not be what it claims.
            assert row["p_t"] > row["p_normal"]
            assert row["p_adj"] >= row["p_t"]
        f5 = next(r for r in table["rows"] if r["family"] == "F5_FLOW_POSITIONING")
        assert f5["p_normal"] == pytest.approx(0.0134, abs=5e-4)
        assert f5["p_t"] == pytest.approx(0.0268, abs=5e-4)
        assert f5["p_adj"] == pytest.approx(0.0804, abs=5e-4)
        assert f5["verdict"] == "null_unresolved", (
            "F5 rejects again — the table is reading the normal reference")
        assert table["n_rejections"] == 0

    @NEEDS_REAL_FRAME
    def test_design_membership_rides_beside_every_verdict(self, era_report):
        """F-2: F5's registered score includes the serving-dead insider_cluster."""
        rows = {row["family"]: row for row in era_report["what_does_x_add"]["rows"]}
        f5 = rows["F5_FLOW_POSITIONING"]
        design = f5["design_membership_effect"]
        assert design["status"] == "estimated"
        assert design["members"] == ["smartmoney_add"]
        assert design["differs_from_score_membership"] is True
        assert design["effect_partial_rho_given_g0"] == pytest.approx(0.052269, abs=5e-4)
        assert design["ci95"][0] == pytest.approx(-0.00256, abs=5e-4)
        assert design["ci95"][1] == pytest.approx(0.11086, abs=5e-4)
        assert design["n_dates"] == 12
        # The verdict stays on the REGISTERED construction; the disclosure is not a
        # second test and is deliberately outside the BH bookkeeping.
        assert f5["membership"] == "score"
        assert f5["n_dates"] == 15
        assert "not a second test" in design["not_bh_adjusted"]
        # A family whose two member sets agree must say so rather than look different.
        f2 = rows["F2_MOMENTUM_EXTENSION"]["design_membership_effect"]
        assert f2["differs_from_score_membership"] is False
        assert f2["effect_partial_rho_given_g0"] == pytest.approx(
            rows["F2_MOMENTUM_EXTENSION"]["effect_partial_rho_given_g0"], abs=1e-9)

    @NEEDS_REAL_FRAME
    def test_the_design_membership_block_is_computed_over_the_fit_eligible_set(
        self, real_report
    ):
        block = real_report["incremental"]["descriptive"]
        assert set(block) >= {"score_membership", "design_membership", "law"}
        assert block["score_membership"]["membership"] == "score"
        assert block["design_membership"]["membership"] == "design"
        assert block["design_membership"]["members_per_family"][
            "F5_FLOW_POSITIONING"] == ["smartmoney_add"]
        assert sorted(block["score_membership"]["members_per_family"][
            "F5_FLOW_POSITIONING"]) == ["insider_cluster", "smartmoney_add"]

    @NEEDS_REAL_FRAME
    def test_multiplicity_sensitivity_is_reported(self, era_report):
        """F-3: a floor that lowers the test count must answer with the other table."""
        block = era_report["what_does_x_add"]["sensitivity"]
        assert block["variant"] == "vote_inert_members_retained"
        assert block["requested_n_tests"] == 4
        assert "F8_ATTENTION_CROWDING" in block["families_retained"]
        assert "0.50" in block["law"] and "not a tuned quantity" in block["law"]
        # The frame cannot supply the 4th test: F8's retained cell is itself below the
        # registered depth minimum, and the block says so with its count.
        refused = {row["family"]: row for row in block["refused_below_min_dates"]}
        assert "F8_ATTENTION_CROWDING" in refused
        assert refused["F8_ATTENTION_CROWDING"]["n_dates"] == 6
        assert block["n_tests"] == 3 and block["n_rejections"] == 0
        # ...so the m=4 question is settled by bounding F8's hypothetical p at both ends.
        for bound in block["m4_bounds"].values():
            assert bound["m"] == 4
            assert bound["n_real_family_rejections"] == 0
        assert block["m4_conclusion"] == "no REAL family rejects at either extreme"


# --------------------------------------------------------------------------- #
# 13. redundancy
# --------------------------------------------------------------------------- #

class TestRedundancy:
    def test_cell_minimums_enforced(self):
        thin = pd.DataFrame({
            "date": ["d1"] * 10 + ["d2"] * 10,
            "left": list(np.arange(20, dtype="float64")),
            "right": list(np.arange(20, dtype="float64") * 2.0),
        })
        cell = c2._spearman_cell(thin, "left", "right")
        assert cell["status"] == "NOT_ESTIMABLE"
        assert cell["n_dates_counted"] == 0
        assert cell["n_pairs_median"] == 10.0
        assert cell["min_pairs_per_date"] == 30 and cell["min_dates"] == 5

    def test_a_cell_with_enough_dates_and_pairs_is_estimated(self):
        rng = np.random.default_rng(3)
        rows = []
        for date in range(8):
            left = rng.normal(size=40)
            rows.extend({"date": f"d{date}", "left": float(left[i]),
                         "right": float(left[i] + rng.normal(0, 0.4))}
                        for i in range(40))
        cell = c2._spearman_cell(pd.DataFrame(rows), "left", "right", b=200)
        assert cell["status"] == "estimated"
        assert cell["n_dates_counted"] == 8
        assert cell["mean"] > 0.5

    @NEEDS_REAL_FRAME
    def test_known_edges_table_covers_every_registry_edge(self, real_report):
        edges = real_report["redundancy"]["known_edges"]
        assert len(edges) == len(c2.registry_known_edges())
        for edge in edges:
            assert edge["pair"] and edge["relation"] and edge["source"]
            status = edge["measurement"]["status"]
            if status == "NOT_MEASURABLE":
                assert edge["missing_side"], (
                    "an unmeasurable edge must NAME the missing side, or the registry's "
                    "'re-measured in PR-2' promise is unauditable")
                assert edge["reason"]

    @NEEDS_REAL_FRAME
    def test_frame1_cells_are_single_cross_section_tier_and_never_pooled(self,
                                                                        real_report):
        block = real_report["redundancy"]["frame1_stamp_20260807"]
        assert block["status"] == "present"
        assert "never" in block["tier_law"].lower()
        measured = 0
        for family, body in block["families"].items():
            if body.get("status") == "structurally_excluded":
                continue
            for cell in body.get("cells", []):
                assert cell["tier"] == "single_cross_section"
                assert "ci95" not in cell and "mean" not in cell
                measured += 1
        assert measured > 0
        assert real_report["redundancy"]["frame1_scan_stamps"], "scan tier must ride too"

    @NEEDS_REAL_FRAME
    def test_an_inert_member_still_appears_in_the_within_family_block(self, real_report):
        """Inertness is DISCLOSED, never hidden (registry variance_floor_spec)."""
        within = real_report["redundancy"]["frame2_within_family"]
        flagged = [c for c in within if c["left_vote_inert"] or c["right_vote_inert"]]
        assert flagged, "no inert member survived into the within-family block"


# --------------------------------------------------------------------------- #
# 14. the selftest, as the CI-visible machinery receipt
# --------------------------------------------------------------------------- #

class TestSelftest:
    def test_selftest_passes_end_to_end(self, tmp_path):
        doc = c2.selftest(tmp_path / "selftest")
        failed = [stage["name"] for stage in doc["stages"] if not stage["ok"]]
        assert not failed, f"selftest stages failed: {failed}"
        assert doc["ok"] is True
        names = [stage["name"] for stage in doc["stages"]]
        for required in ("census", "variance_floor_near_constant_is_vote_inert",
                         "variance_floor_sparse_but_variable_passes", "redundancy_blocks",
                         "cmi_estimable_on_synthetic_depth", "folds_exist",
                         "residualizer_frozen_against_test_fold_mutation",
                         "crossfit_recovers_planted_and_covers_zero_for_noise",
                         "c2_fit_sign_constraint_and_grid",
                         "c2_raw_p_at_5_beats_the_noise_family",
                         "report_writes_and_reruns_byte_identical"):
            assert required in names

    def test_the_cli_selftest_exits_zero(self):
        result = subprocess.run(
            [sys.executable, "-m", "scripts.prophet_fusion_c2", "--selftest"],
            cwd=str(ROOT), capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-2000:]
        assert "RESULT : PASS" in result.stdout


# --------------------------------------------------------------------------- #
# 15. zero authority
# --------------------------------------------------------------------------- #

class TestAuthority:
    @NEEDS_REAL_FRAME
    def test_report_carries_all_false_authority_and_labels(self, real_report):
        assert real_report["schema"] == "prophet_fusion.pr2_c2.v1"
        assert real_report["authority"] == {
            "can_rank": False, "can_size": False, "can_gate": False,
            "can_originate_signal": False, "can_escalate": False}
        assert real_report["non_promotion_bearing"] is True
        assert real_report["counterfactual_replay"] is True
        assert real_report["survivorship"]["frame2"].startswith("reconstructed curated")
        assert "promotion-barred" in real_report["survivorship"]["price_basis"]
        assert real_report["horizons_available"] == [5, 10, 21]
        assert real_report["selftest_receipt"]["ran"] is False

    def test_the_out_dir_may_never_be_a_tracked_store(self):
        for tracked in ("data", "data/us_board_ledger", "site", "site/assets"):
            with pytest.raises(c2.C2Refusal, match="research tooling never writes"):
                c2._safe_out_dir(tracked)


# --------------------------------------------------------------------------- #
# 16. the committed artifact (skipped until it exists)
# --------------------------------------------------------------------------- #

class TestCommittedReport:
    @pytest.mark.skipif(not REPORT_PATH.exists(), reason="report not committed yet")
    def test_the_committed_report_is_the_refused_shape(self):
        doc = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        assert doc["schema"] == "prophet_fusion.pr2_c2.v1"
        assert doc["c2_fit"]["status"] == "refused_no_lawful_folds"
        assert doc["incremental"]["crossfit"]["status"] == "refused_no_lawful_folds"
        assert not (_all_keys(doc["c2_fit"]) & {"coefficients", "evidence_coefficients"})
        assert doc["authority"]["can_rank"] is False

    @pytest.mark.skipif(not REPORT_PATH.exists(), reason="report not committed yet")
    def test_the_committed_report_carries_no_fitted_coefficient_at_all(self):
        """No real-frame coefficient exists anywhere in the artifact, under any key."""
        doc = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        # `registered.grid.inner_selection` is deliberately NOT in this set: describing
        # how a fold WOULD be selected is the registration, and a test that forbade the
        # word would force the registration to go unwritten.  What must be absent is any
        # fitted VALUE — a coefficient, a chosen point in the grid, a test-fold metric.
        forbidden = {"evidence_coefficients", "coefficients", "theta", "chosen", "heads",
                     "coefficients_pinned_at_zero_by_the_nonneg_bound",
                     "test_fold_raw_order"}
        leaked = sorted(_all_keys(doc) & forbidden)
        assert not leaked, f"{leaked} reached a REFUSED real-frame report"

# --------------------------------------------------------------------------- #
# 17. the registered descriptive depth minimum (review F-7)
# --------------------------------------------------------------------------- #

class TestDescriptiveMinDates:
    def test_the_minimum_is_registered_and_self_consistent_with_cmi(self, real_report):
        assert c2.DESCRIPTIVE_MIN_DATES == c2.CMI_MIN_DATES == 8
        block = real_report["registered"]["descriptive_minimums"]
        assert block["min_date_blocks"] == 8
        assert block["equal_to_cmi_min_dates"] is True

    def test_a_thin_cell_refuses_with_its_count(self):
        reference = c2.date_blocked_p([0.1, 0.2, -0.05, 0.3, 0.11, 0.02, 0.07])
        assert reference["status"] == "NOT_ESTIMABLE"
        assert reference["p_t"] is None and reference["p_normal"] is None
        assert reference["n_dates"] == 7 and reference["min_dates"] == 8
        assert "7 date-blocks < the registered descriptive minimum 8" in reference["reason"]

    def test_an_estimable_cell_carries_both_references_and_t_is_conservative(self):
        values = [0.10, 0.14, -0.02, 0.21, 0.08, 0.17, 0.05, 0.12, 0.19, 0.03]
        reference = c2.date_blocked_p(values)
        assert reference["status"] == "estimated"
        assert reference["df"] == len(values) - 1
        assert reference["p_t"] > reference["p_normal"], (
            "the t must be the more conservative reference at these block counts")

    @NEEDS_REAL_FRAME
    def test_h21_secondary_table_is_empty_because_every_cell_refuses(self, era_report):
        """7/7/4 date-blocks cannot support a two-sided p of either shape."""
        table = era_report["what_does_x_add_secondary_horizons"]["21"]
        assert table["n_tests"] == 0
        assert table["rows"] == []
        refused = {row["family"]: row for row in table["refused_below_min_dates"]}
        assert set(refused) == {"F2_MOMENTUM_EXTENSION", "F4_CATALYST_EVENT",
                                "F5_FLOW_POSITIONING"}
        assert refused["F2_MOMENTUM_EXTENSION"]["n_dates"] == 7
        assert refused["F5_FLOW_POSITIONING"]["n_dates"] == 7
        assert refused["F4_CATALYST_EVENT"]["n_dates"] == 4
        for row in refused.values():
            assert row["min_dates"] == 8

    @NEEDS_REAL_FRAME
    def test_h5_secondary_table_still_reports_and_keys_on_t(self, real_report):
        table = real_report["what_does_x_add_secondary_horizons"]["5"]
        assert table["n_tests"] == 3 and table["verdict_keys_on"] == "p_t"
        for row in table["rows"]:
            assert row["p_t"] is not None and row["p_normal"] is not None


# --------------------------------------------------------------------------- #
# 18. null-semantics on the variance axis (review F-9) and the train/serve
#     ratio's like-for-like comparison (review F-10)
# --------------------------------------------------------------------------- #

_NULL_ENCODED_REGISTRY = {
    "schema": "prophet_fusion.families.v1",
    "coverage_floor": 0.50,
    "semantics": {"variance_floor_spec": {
        "axis": "within_date_distinct_nonnull_oriented_values",
        "min_distinct_values_per_date": 2,
        "min_dates_with_variation_share": 0.50,
        "excluded_from": ["family_vote_aggregation", "fitted_design_matrices"],
        "retained_in": ["census"]}},
    "families": {"FEV_EVENT": {"title": "Null-encoded event flag", "members": {
        # measured_negative AND null-encoded: the producer answers "no event" by writing
        # NOTHING, which is the shape the presence floor already special-cases.
        "null_encoded_event": {"pit_status": "pit", "columns": ["syn_event"],
                               "null_semantics": "measured_negative",
                               "coverage_probe": True}}}},
}


def _null_encoded_frame(n_dates: int = 20, n_tickers: int = 40, seed: int = 11):
    """A sparse event flag whose negatives are NULLS, not explicit False."""
    rng = np.random.default_rng(seed)
    rows, outcomes = [], []
    for index in range(n_dates):
        date = f"E{index:03d}"
        fires = set(int(t) for t in rng.choice(n_tickers, size=2, replace=False))
        for ticker_index in range(n_tickers):
            ticker = f"EV{ticker_index:03d}"
            rows.append({"date": date, "ticker": ticker,
                         "syn_event": True if ticker_index in fires else None})
            outcomes.append({"date": date, "ticker": ticker, "horizon": 10,
                             "excess_spy": float(rng.normal(0, 0.05))})
    features = pd.DataFrame(rows)
    frame = pd.DataFrame(outcomes)
    return c2.C2Frame(
        features=features, outcomes=frame,
        g0=features[["date", "ticker"]].assign(g0_score=0.0),
        signs={"syn_event": c2.RegisteredSign(
            column="syn_event", family="FEV_EVENT", sign=+1, kind="flag",
            source="fixture")},
        labels=LabelFrame(frame=frame, receipt={}))


def _null_encoded_census(tmp_path, serve_slab=None):
    path = tmp_path / "null_encoded.yml"
    path.write_text(yaml.safe_dump(_NULL_ENCODED_REGISTRY, sort_keys=False),
                    encoding="utf-8")
    registry = load_registry(path)
    floor = c2.load_variance_floor(path)
    flags = c2.registry_member_flags(path)
    frame = _null_encoded_frame()
    census = c2.estimability_census(frame, registry, floor, member_flags=flags,
                                    serve_slab=serve_slab)
    return census["families"]["FEV_EVENT"]["members"][0]


class TestNullSemanticsOnTheVarianceAxis:
    def test_a_null_encoded_event_flag_is_not_vote_inert(self, tmp_path):
        """F-9: counting only non-nulls sees ONE value and kills a live event channel."""
        member = _null_encoded_census(tmp_path)
        axis = member["variance_axis"]["syn_event"]
        assert member["null_semantics"] == "measured_negative"
        assert member["coverage"]["n_explicit_negative_values"] == 0
        assert axis["null_counts_as_a_measured_value"] is True
        assert axis["variation_share"] == 1.0, (
            "the null state is this member's measured negative, so a date on which the "
            "flag fired carries TWO distinct values, not one")
        assert member["vote_inert"] is False
        assert "vote_inert" not in member["reasons"]

    def test_the_credit_is_withheld_when_negatives_are_stored_explicitly(self,
                                                                        synthetic_bundle):
        """The guard's other side: an explicit-False member must NOT be credited twice."""
        inert = _member(synthetic_bundle["census"], "FI_NEAR_CONSTANT")
        axis = inert["variance_axis"]["syn_inert"]
        assert axis["null_counts_as_a_measured_value"] is False
        assert inert["vote_inert"] is True

    @NEEDS_REAL_FRAME
    def test_news_burst_is_unchanged_by_the_null_semantics_fix(self, era_census):
        """news_burst stores 1,474 explicit False, so its 0.333 / inert read must hold."""
        member = next(m for m in era_census["families"]["F8_ATTENTION_CROWDING"]["members"]
                      if m["vote_column"] == "news_burst")
        axis = member["variance_axis"]["news_burst"]
        assert member["coverage"]["n_explicit_negative_values"] == 1474
        assert axis["null_counts_as_a_measured_value"] is False
        assert axis["variation_share"] == pytest.approx(0.3333, abs=1e-3)
        assert member["vote_inert"] is True


class TestRegisteredEraPin:
    """Option B: reconstruct the PR-2 frame from the grown ledger by row identity.

    An as-of cutoff is the wrong pin (DSC:GRADED-BOARD-LEDGER-ACCRUES-BY-HORIZON).
    The live frame is still checked by TestTheLedgerAccruesRatherThanRewrites.
    """

    @NEEDS_REAL_FRAME
    def test_the_key_pin_recovers_the_registered_row_count_from_the_grown_ledger(self):
        pin = json.loads(ERA_PIN.read_text(encoding="utf-8"))
        keys = pd.read_parquet(ERA_KEYS)
        raw = _pin_ledger_to_registered_era(pd.read_parquet(LEDGER), keys)
        assert len(keys) == pin["n_keys"]
        assert len(raw) == pin["n_rows_expected"] == 4077
        dates = raw["as_of"].astype(str).str.slice(0, 10)
        assert dates.nunique() == pin["n_dates"] == 24
        assert [str(dates.min()), str(dates.max())] == pin["date_range"]
        by_h = {int(h): int(n) for h, n in
                pd.DataFrame({"d": dates, "h": raw["horizon"].astype(int)})
                .drop_duplicates().groupby("h")["d"].nunique().items()}
        assert by_h == {int(k): int(v) for k, v in pin["horizon_n_dates"].items()}

    @NEEDS_REAL_FRAME
    def test_an_as_of_cutoff_does_not_recover_the_registered_vintage(self):
        pin = json.loads(ERA_PIN.read_text(encoding="utf-8"))
        live = pd.read_parquet(LEDGER)
        cut = live[live["as_of"].astype(str).str.slice(0, 10) <= pin["date_range"][1]]
        assert len(cut) > pin["n_rows_expected"], (
            "as-of cutoff recovered the vintage — the pin would be a date cut, "
            "which DSC:GRADED-BOARD-LEDGER-ACCRUES-BY-HORIZON measured as wrong")


class TestTheLedgerAccruesRatherThanRewrites:
    """The registered artifact is frozen; its INPUT is not — and that is lawful.

    This is the guard that replaces the literal-vs-rebuild assertions the vintage-bound
    tests used to carry.  Those could not survive maturation; this one is written in the
    only terms that hold at every vintage: the graded ledger may only ACCRUE over the
    frame PR-2 registered.  A board date may gain horizons, and new board dates may
    arrive.  What may NOT happen is a rewrite of settled history — and if one does, this
    reds by name instead of the study silently reporting different numbers under the
    registered numbers' heading.

    Measured 2026-08-18: 4,077 -> 4,566 rows and 24 -> 25 dates, entirely from H=21
    maturing on 07-15, H=10 on 07-30/07-31, and the 08-07 board arriving.  Unique tickers
    per affected date did not move (64/147/142 before and after), which is what separates
    maturation from a double-collected board.
    """

    @NEEDS_REAL_FRAME
    def test_the_live_frame_only_grows_over_the_registered_one(self, registered_report):
        registered = registered_report["frames"]["frame2_graded_board"]["labels_receipt"]
        live = c2.build_c2_frame().labels.receipt

        assert live["rows_in"] >= registered["rows_in"], (
            "the graded ledger LOST rows against the registered frame — accrual only")
        assert live["n_dates"] >= registered["n_dates"]
        assert live["date_range"][0] == registered["date_range"][0], (
            "the registered window's first board date moved — that is a rewrite of "
            "settled history, not maturation")
        assert live["date_range"][1] >= registered["date_range"][1]

    @NEEDS_REAL_FRAME
    def test_the_frozen_pre_era_price_basis_population_never_moves(self,
                                                                  registered_report):
        """`unverified_pre_20260806` is closed by date, so its count is a rewrite alarm.

        Rows stamped before the 08-06 price-basis era can never be re-graded into a
        different basis; every re-adjustment lands on `adjusted`/`unadjusted`.  So this
        one count is invariant while the other three legitimately grow, which makes it a
        falsifier that a moving frame cannot trip on its own.
        """
        registered = registered_report["frames"]["frame2_graded_board"]["labels_receipt"]
        frozen = registered["strata"]["counts"]["price_basis"]["unverified_pre_20260806"]
        live = c2.build_c2_frame().labels.receipt
        assert live["strata"]["counts"]["price_basis"]["unverified_pre_20260806"] == frozen


class TestTrainServeRatio:
    def test_the_ratio_is_raw_notna_on_both_sides(self, tmp_path):
        """F-10: pairing a semantic 1.0 with a raw serve share doubles the threshold."""
        serve = pd.DataFrame({"syn_event": [True, None, None, None] * 10})
        member = _null_encoded_census(tmp_path, serve_slab=serve)
        train_serve = member["train_serve"]
        # The semantic figure (what the presence FLOOR reads) is 1.0 for this member...
        assert train_serve["train_coverage_semantic"] == 1.0
        assert member["coverage"]["used_for_floor"] == 1.0
        # ...but the RATIO compares raw non-null on both sides: 0.25 serve vs 0.05 train.
        assert train_serve["train_coverage"] == pytest.approx(0.05, abs=1e-6)
        assert train_serve["serve_coverage"] == pytest.approx(0.25, abs=1e-6)
        assert "like-for-like" in train_serve["train_coverage_basis"]
        assert "excluded_train_serve_skew" not in member["reasons"], (
            "the semantic 1.0 was used as the ratio's denominator, which doubles the "
            "exclusion threshold for exactly the members whose nulls mean something")

    @NEEDS_REAL_FRAME
    def test_alpha_is_not_excluded_by_a_mismatched_column_set(self, real_census):
        member = next(m for m in real_census["families"]["F2_MOMENTUM_EXTENSION"]["members"]
                      if m["member"] == "F2_MOMENTUM_EXTENSION.residual_alpha")
        train_serve = member["train_serve"]
        assert train_serve["columns_measured"] == ["alpha"]
        assert train_serve["serve_coverage"] == pytest.approx(0.930111, abs=1e-5)
        assert member["verdict"] == "eligible"


# --------------------------------------------------------------------------- #
# 19. the two NITs, and the pit_settlement admission ripple (#5705 / PR-3A)
# --------------------------------------------------------------------------- #

class TestPermutationPEstimator:
    @NEEDS_REAL_FRAME
    def test_cmi_p_can_never_be_exactly_zero(self, real_report):
        """(1 + #{null >= observed}) / (B + 1): the observed draw counts itself.

        The producer writes p_one_sided through _round(..., 6) (prophet_fusion_race._round,
        scripts/prophet_fusion_c2.py). At the estimator floor (#{null >= observed} == 0)
        the raw p is exactly 1/(B+1) — for B=500, 0.001996007984..., which rounds to
        0.001996, strictly BELOW the unrounded floor. Comparing a 6dp-rounded value
        against an unrounded bound is a false floor violation, not a real one, so the
        floor comparison must be rounded the same way the producer rounds its output —
        never the other way around: this file refuses to re-stamp registered PR-2
        evidence, so the producer's rounding stays exactly as registered."""
        estimated = [c for c in real_report["cmi"]["cells"] if c["status"] == "estimated"]
        assert estimated
        for cell in estimated:
            assert cell["p_one_sided_estimator"] == "(1 + #{null >= observed}) / (B + 1)"
            floor = round(1.0 / (cell["permutation_b"] + 1), 6)
            assert cell["p_one_sided"] >= floor
            assert cell["p_one_sided"] > 0.0


class TestUnresolvableEdgeSpec:
    @NEEDS_REAL_FRAME
    def test_a_family_range_in_a_member_position_is_not_a_measurement_gap(self,
                                                                          real_report):
        edges = real_report["redundancy"]["known_edges"]
        ranged = [e for e in edges
                  if e["measurement"]["status"] == "unresolvable_pair_spec"]
        assert len(ranged) == 1
        edge = ranged[0]
        assert edge["unresolvable_sides"] == ["F1_TECHNICAL_CONFLUENCE..F4_CATALYST_EVENT"]
        assert "registry edit" in edge["reason"]
        # It must NOT be counted among the edges that would flip to a measurement.
        for other in edges:
            if other is edge:
                continue
            assert other["measurement"]["status"] in ("NOT_MEASURABLE", "estimated",
                                                      "NOT_ESTIMABLE")


class TestPitSettlementAdmission:
    """RIPPLE: #5705 reconciled the producer; PR-3A admits pit_settlement.
    Admission is a PIT gate, not an estimability claim, and does not assert that
    short_interest enters a family score or a C2 fit on this shallow frame."""

    def test_the_suite_reads_the_gate_rather_than_assuming_it(self):
        from scripts.prophet_fusion_arena import BACKTEST_LAWFUL_STATUSES, PIT_OK, PIT_SETTLEMENT
        assert PIT_SETTLEMENT in BACKTEST_LAWFUL_STATUSES
        assert BACKTEST_LAWFUL_STATUSES == frozenset({PIT_OK, PIT_SETTLEMENT})

    @NEEDS_REAL_FRAME
    def test_short_interest_is_backtest_lawful_and_still_not_an_admission_of_estimability(
        self, real_report, real_census,
    ):
        member = next(m for m in real_census["families"]["F5_FLOW_POSITIONING"]["members"]
                      if m["member"] == "F5_FLOW_POSITIONING.short_interest")
        assert member["pit_status"] == "pit_settlement"
        assert member["backtest_lawful"] is True
        assert "not_backtest_pit" not in member["reasons"]
        # Remaining snapshot/forward-only members stay disclosed, never admitted.
        block = real_report["redundancy"]["frame1_stamp_20260807"]["families"][
            "F5_FLOW_POSITIONING"]
        unlawful = block.get("members_measured_but_not_backtest_lawful") or []
        assert not any("short_interest" in str(item) for item in unlawful)
        assert "NEVER an admission" in block["pit_disclosure"]


# --------------------------------------------------------------------------- #
# the doc's hand-written tables are machine-checked against the artifact
# (adversarial review F-4: the first draft of the wave doc mis-transcribed three
# CMI cells; this pin makes that class of error red instead of shipped)
# --------------------------------------------------------------------------- #

DOC_PATH = ROOT / "research" / "prophet_fusion" / "PR2_C2_REDUNDANCY.md"


@NEEDS_REAL_FRAME
class TestDocTablesMatchTheArtifact:
    def _doc(self):
        return DOC_PATH.read_text(encoding="utf-8")

    def test_the_cmi_table_cells_match_report_json(self, era_report):
        """§5's table prints `excess (p)` per family x horizon; every printed pair
        must equal the artifact's cell rounded to the doc's own precision."""
        doc = self._doc()
        cells = {(c["family"], int(c["horizon"])): c
                 for c in era_report["cmi"]["cells"]}
        import re
        row_re = re.compile(
            r"^\|\s*(F\d)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*$", re.M)
        fam_map = {"F2": "F2_MOMENTUM_EXTENSION", "F4": "F4_CATALYST_EVENT",
                   "F5": "F5_FLOW_POSITIONING"}
        found = 0
        for match in row_re.finditer(doc):
            short = match.group(1)
            if short not in fam_map:
                continue
            fam = fam_map[short]
            for horizon, text in ((5, match.group(2)), (10, match.group(3))):
                cell = cells[(fam, horizon)]
                text = text.replace("\u2212", "-")   # the doc's typographic minus
                pair = re.search(r"([+\-]\d+\.\d+)\s*\((\d+\.\d+)\)", text)
                assert pair, f"doc row {short} H={horizon} carries no `excess (p)` pair"
                assert float(pair.group(1)) == pytest.approx(
                    cell["excess_bits"], abs=5e-5), (short, horizon, "excess")
                assert float(pair.group(2)) == pytest.approx(
                    cell["p_one_sided"], abs=5e-4), (short, horizon, "p")
            assert "NOT_ESTIMABLE" in match.group(4), (short, "H=21 must refuse")
            found += 1
        assert found == 3, f"expected 3 CMI doc rows, matched {found}"

    def test_the_what_does_x_add_table_matches_report_json(self, era_report):
        """§7's measured rows print `p_t / p_normal / p_adj`; each must equal the
        artifact's row at the doc's 3-decimal precision, and the doc's verdict
        word must be the artifact's verdict."""
        doc = self._doc()
        rows = {r["family"]: r for r in era_report["what_does_x_add"]["rows"]}
        import re
        fam_map = {"F2": "F2_MOMENTUM_EXTENSION", "F4": "F4_CATALYST_EVENT",
                   "F5": "F5_FLOW_POSITIONING"}
        found = 0
        for line in doc.splitlines():
            match = re.match(r"^\|\s*(F\d)\s*\|\s*\**`(\w+)`\**", line)
            if not match or match.group(1) not in fam_map:
                continue
            fam = fam_map[match.group(1)]
            row = rows[fam]
            assert match.group(2) == row["verdict"], (fam, "verdict")
            triple = re.search(
                r"\**(\d+\.\d+)\**\s*/\s*(\d+\.\d+)\s*/\s*\**(\d+\.\d+)\**", line)
            assert triple, (fam, "p triple missing")
            assert float(triple.group(1)) == pytest.approx(row["p_t"], abs=5e-4)
            assert float(triple.group(2)) == pytest.approx(row["p_normal"], abs=5e-4)
            assert float(triple.group(3)) == pytest.approx(row["p_adj"], abs=5e-4)
            found += 1
        assert found == 3, f"expected 3 measured what_does_x_add doc rows, matched {found}"
        assert "**Zero rejections.**" in doc
        assert era_report["what_does_x_add"]["n_rejections"] == 0
