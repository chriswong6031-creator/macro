"""The Prophet US program's nightly modules run OFF the engine job's critical path.

Moved 2026-08-06.  `daily.yml`'s `engine` job carries `timeout-minutes: 200` and has been
hitting it (run 30862763261, 08-03: 205m CANCELLED; run 31056495943, 08-06: 205m
CANCELLED), and a cancel skips `commit engine outputs` — so the night's accrual is
computed and then thrown away.  On 08-06 the doors emitter finished green at 04:45:27Z and
the miss-audit at 04:48:11Z; the job was cancelled at 05:37:19Z with the commit step never
started, and `data/prophet_doors`, `data/prophet_miss_audit` and `data/us_prophet_rank`
all still carry 2026-08-05 as their last advance.  Nothing in this program gates the
dashboard (`publish` needs ONLY `engine`), so the six post-board modules now live in
`us_prophet_ledgers`, a sibling of the `us_scan_tier` lane, reading the tree the engine and
scan-tier jobs COMMIT and committing their own ledgers.

What this module pins, and why each pin can actually fail:

1.  **Placement.** The six modules are in `us_prophet_ledgers` and NOT in `engine`.  A
    step re-added to `engine` rides the cancel again.
2.  **Ordering is real, not assumed.**  The new job `needs` both producers of the tree it
    reads — `engine` (which commits the candidate stamp, the name_score ledger, the board
    and the plans) and `us_scan_tier` (which commits the scan-tier artifact and the
    scan-tier candidate rows).
3.  **The lane gate still holds in the new job's environment.**  Five of the six modules
    refuse to advance unless `COLLECT_LANE=nightly`, which the *engine* job set at job
    level.  A move that dropped it would leave every step green and every ledger frozen —
    strictly worse than the slow version it replaced.  The behavioural half below drives
    the four pre-existing append APIs with the env unset and asserts they write nothing;
    B1's pre-read refusal is pinned in its reconciler suite.
4.  **Failure isolation is armed, not claimed.**  The moved steps lost their `|| true`:
    inside the deploy lane a crash had to be swallowed, here it must be visible.  Each
    module already degrades internally to a disclosed null, so a non-zero exit is a real
    crash.  `if: always()` on the later steps keeps a crashed sibling from silently
    stopping an independent ledger — that is NOT `continue-on-error`, and no step in this
    job may carry `continue-on-error`.
5.  **No cascade.**  `publish` must never depend on this job.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.workflow_run_source import resolve_run_source  # noqa: E402

DAILY = ROOT / ".github/workflows/daily.yml"
DAG = ROOT / "config/dag.yml"

JOB = "us_prophet_ledgers"

#: (module, the step-name fragment that names it).  Order is the dependency order the
#: lane must run them in.
MOVED = [
    ("scripts.emit_prophet_doors", "Prophet doors — accrue"),
    ("scripts.reconcile_us_candidate_episodes", "Prophet B1 — reconcile"),
    ("scripts.grade_prophet_doors", "Prophet doors — grade"),
    ("scripts.grade_us_prophet_candidates", "Prophet US full-population grades"),
    ("scripts.accrue_us_prophet_w3", "Prophet W3 paired-race ledger"),
    ("scripts.run_prophet_miss_audit", "Prophet miss-audit"),
]

#: The five whose forward advance ALSO gates on engine.ledger_lane (COLLECT_LANE=nightly)
#: on top of --nightly.  run_prophet_miss_audit gates on --nightly alone (it threads
#: `advance=` through instead), which is why it is deliberately absent here.
LANE_GATED = [
    "scripts.emit_prophet_doors",
    "scripts.reconcile_us_candidate_episodes",
    "scripts.grade_prophet_doors",
    "scripts.grade_us_prophet_candidates",
    "scripts.accrue_us_prophet_w3",
]


@pytest.fixture(scope="module")
def daily() -> dict:
    return yaml.safe_load(DAILY.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def job(daily) -> dict:
    assert JOB in daily["jobs"], (
        f"job '{JOB}' is gone — the Prophet modules have no off-engine home")
    return daily["jobs"][JOB]


def _runs(step: dict) -> str:
    # 512KB-cap diet: some bodies live in scripts/ci/ — resolve the effective
    # source so step-body assertions keep seeing what the step actually runs.
    return resolve_run_source(str(step.get("run") or ""), ROOT)


# --------------------------------------------------------------------------- #
# 1. placement
# --------------------------------------------------------------------------- #

class TestPlacement:

    @pytest.mark.parametrize("module,fragment", MOVED)
    def test_the_module_runs_in_the_off_engine_job(self, job, module, fragment):
        hits = [s for s in job["steps"] if f"python -m {module} --nightly" in _runs(s)]
        assert len(hits) == 1, (
            f"{module} must be invoked exactly once in '{JOB}' with --nightly")
        assert fragment in (hits[0].get("name") or ""), (
            f"{module}'s step name no longer says what it is ({fragment!r})")

    @pytest.mark.parametrize("module,_frag", MOVED)
    def test_the_module_is_not_back_on_the_engine_critical_path(
            self, daily, module, _frag):
        bodies = " ".join(_runs(s) for s in daily["jobs"]["engine"]["steps"])
        assert f"python -m {module}" not in bodies, (
            f"{module} is back in the engine job — it would ride the 200m-cap cancel "
            "that skips 'commit engine outputs' and discards the night's accrual")

    def test_the_lane_order_is_the_dependency_order(self, job):
        order = [i for i, s in enumerate(job["steps"])
                 for m, _ in MOVED if f"python -m {m} --nightly" in _runs(s)]
        assert order == sorted(order) and len(order) == len(MOVED)
        seq = [m for s in job["steps"] for m, _ in MOVED
               if f"python -m {m} --nightly" in _runs(s)]
        assert seq == [m for m, _ in MOVED], (
            "the doors grader reads the emitter's flags, and the miss-audit's "
            "priority_score_scorecard reads the W7 grade store — this order is a "
            "read-after-write chain, not a preference")


# --------------------------------------------------------------------------- #
# 2. the ordering is real: the new job waits on whoever COMMITS what it reads
# --------------------------------------------------------------------------- #

class TestReadsTheCommittedTree:

    def test_it_needs_both_producers_of_the_tree_it_reads(self, job):
        needs = job["needs"]
        needs = [needs] if isinstance(needs, str) else list(needs)
        assert "engine" in needs, (
            "the candidate stamp (build_stock_library inside build_site), "
            "data/name_score/us_calls.parquet, site/prophet/plans/*.json and "
            "site/factordata/us_standouts.json all reach main through the engine job's "
            "'commit engine outputs' step")
        assert "us_scan_tier" in needs, (
            "the miss-audit reads data/prophet_scan_tier/latest.json and the W7 grader "
            "reads the scan-tier rows appended to data/us_prophet_rank/candidates — both "
            "land through the us_scan_tier job's own commit")

    def test_it_checks_out_and_pulls_main(self, job):
        checkout = [s for s in job["steps"] if str(s.get("uses", "")).startswith(
            "actions/checkout")]
        assert checkout, f"{JOB} never checks out — it cannot read the committed tree"
        assert checkout[0].get("with", {}).get("ref") == "main"
        assert any("git pull origin main" in _runs(s) for s in job["steps"]), (
            "without the pull the checkout can predate the engine job's push")

    def test_the_engine_job_still_commits_what_this_job_reads(self, daily):
        commit = [s for s in daily["jobs"]["engine"]["steps"]
                  if (s.get("name") or "") == "commit engine outputs"]
        assert commit, "the engine commit step was renamed — re-verify the read chain"
        code = _runs(commit[0])
        assert re.search(r"^\s*git add data/ site/ reports/", code, re.M), (
            "the engine commit no longer broad-adds data/ + site/ — the candidate store, "
            "name_score ledger, board and plans this job reads may not reach main")


# --------------------------------------------------------------------------- #
# 3. the ledger lane gate — present in the workflow AND load-bearing in the code
# --------------------------------------------------------------------------- #

class TestLedgerLaneGate:

    def test_the_job_sets_the_nightly_lane_sentinel(self, job):
        assert (job.get("env") or {}).get("COLLECT_LANE") == "nightly", (
            "five of the six moved advancers gate on "
            "engine.ledger_lane.nightly_advance_enabled(); without this env they run "
            "green and write NOTHING — a silently frozen ledger is worse than a slow one")

    @pytest.mark.parametrize("module", LANE_GATED)
    def test_no_moved_step_overrides_the_sentinel(self, job, module):
        step = next(s for s in job["steps"]
                    if f"python -m {module} --nightly" in _runs(s))
        step_env = step.get("env") or {}
        assert step_env.get("COLLECT_LANE", "nightly") == "nightly", (
            f"{module}'s step env overrides the job-level lane sentinel")

    def test_the_gate_itself_reads_collect_lane(self, monkeypatch):
        from engine import ledger_lane
        monkeypatch.delenv("COLLECT_LANE", raising=False)
        monkeypatch.delenv("US_LANE", raising=False)
        assert ledger_lane.nightly_advance_enabled() is False
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        assert ledger_lane.nightly_advance_enabled() is True

    def test_off_lane_the_four_existing_appenders_write_nothing(self, tmp_path, monkeypatch):
        """The refutation half: drive each append with the sentinel unset.

        A workflow-side assertion about an env var is only worth what the gate behind it
        does.  Each of these returns 0 and leaves no file, so removing the env from
        daily.yml really does freeze the ledgers.
        """
        from engine import prophet_doors
        from engine import us_prophet_grades as upg
        from engine import us_prophet_w3 as w3
        from scripts import grade_prophet_doors as gpd

        monkeypatch.delenv("COLLECT_LANE", raising=False)
        monkeypatch.delenv("US_LANE", raising=False)

        flag = {"schema": "prophet_doors/v1", "as_of": "2026-08-06", "door": "T",
                "ticker": "AAA"}
        grade = {"stamp_date": "2026-01-05", "ticker": "AAA",
                 "board_definition": "d", "horizon": 10, "fwd_ret": 0.1}
        w3_row = {
            "schema": w3.SCHEMA_PAIRED, "stamp_date": "2026-08-18", "ticker": "AAA",
            "board_definition": w3.CANONICAL_BOARD, "selection_era": None,
            "anchor_era": None, "stage": "live", "prophet_score": 1.0, "score_rank": 1,
            "prophet_shadow_definition": w3.SHADOW_DEFINITION,
            "prophet_shadow_score": 1.0, "prophet_shadow_score_rank": 1,
            "horizon": 10, "excess_spy": 0.01, "benchmark": "SPY",
            "fill_date": "2026-08-19", "mark_date": "2026-09-02",
            "graded_asof": "2026-09-02", "source": "test",
        }

        assert prophet_doors.append_flags([flag], root=tmp_path) == 0
        assert prophet_doors.write_status({"asof": "2026-08-06"}, root=tmp_path) is False
        assert gpd.append_grades([grade], root=tmp_path) == 0
        assert upg.append_grades([grade], "2026-08-06", root=tmp_path) == 0
        assert w3.append_paired([w3_row], tmp_path)["written"] == 0
        assert w3.append_sessions([{
            "stamp_date": "2026-08-18",
            "liveness": w3.LIVENESS_MISSING,
            "reason": "gap",
        }], tmp_path)["written"] == 0
        assert w3.write_status({"schema": w3.SCHEMA_STATUS, "commissioned": False},
                               tmp_path) is False
        assert not list((tmp_path / "data").rglob("*")), (
            "an off-lane run left bytes in data/ — the gate is not the sole writer path")

        # ...and with the sentinel set, the very same calls DO advance.  Without this half
        # the assertions above would pass on a permanently-dead writer.
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        assert prophet_doors.append_flags([flag], root=tmp_path) == 1
        assert prophet_doors.write_status({"asof": "2026-08-06"}, root=tmp_path) is True
        assert gpd.append_grades([grade], root=tmp_path) == 1
        assert upg.append_grades([grade], "2026-08-06", root=tmp_path) == 1
        assert w3.append_paired([w3_row], tmp_path)["written"] == 1
        assert w3.append_sessions([{
            "stamp_date": "2026-08-18",
            "liveness": w3.LIVENESS_MISSING,
            "reason": "gap",
        }], tmp_path)["written"] == 1
        assert w3.write_status({"schema": w3.SCHEMA_STATUS, "commissioned": False},
                               tmp_path) is True

    def test_the_stores_the_commit_stages_are_the_stores_the_modules_write(self, job):
        """The add list is derived from the modules, not copied from the workflow."""
        from engine import prophet_doors, prophet_miss_audit
        from engine import us_prophet_grades as upg
        from engine import us_prophet_w3 as w3
        from scripts import grade_prophet_doors as gpd

        root = Path("/repo")
        written = {
            prophet_doors.flags_path(root),
            prophet_doors.status_path(root),
            gpd.grades_path(root),
            upg._store_dir(root),
            w3._store_dir(root),
            root / prophet_miss_audit.ARTIFACT_REL,
            root / prophet_miss_audit.FORWARD_LOG_REL,
        }
        commit = next(s for s in job["steps"]
                      if "git add" in _runs(s) and "git commit" in _runs(s))
        staged = re.findall(r"^\s*git add (?:-f )?(\S+)", _runs(commit), re.M)
        assert staged, "the commit step stages nothing"
        for path in sorted(written):
            rel = path.relative_to(root).as_posix()
            assert any(rel == p or rel.startswith(p.rstrip("/") + "/") for p in staged), (
                f"{rel} is written by a moved module but no `git add` covers it — an "
                "unstaged ledger row is a lost night, which is the defect this move fixes")


# --------------------------------------------------------------------------- #
# 4. failure isolation is armed, not merely asserted in a PR body
# --------------------------------------------------------------------------- #

class TestFailureIsolation:

    def test_no_step_in_the_job_carries_continue_on_error(self, job):
        offenders = [s.get("name") for s in job["steps"]
                     if s.get("continue-on-error") is True]
        assert not offenders, (
            f"{offenders}: the whole point of the move is that a Prophet failure is "
            "VISIBLE; continue-on-error puts it back under the rug")

    @pytest.mark.parametrize("module,_frag", MOVED)
    def test_the_moved_step_is_no_longer_masked_by_a_true_fallback(
            self, job, module, _frag):
        step = next(s for s in job["steps"]
                    if f"python -m {module} --nightly" in _runs(s))
        body = [ln.strip() for ln in _runs(step).splitlines()
                if ln.strip() and not ln.strip().startswith("#")]
        assert body == [f"python -m {module} --nightly"], (
            f"{module} is masked again ({body}) — inside the deploy lane the `|| true` "
            "was necessary; here it turns the isolated job into a permanently green one")

    def test_a_crashed_module_does_not_silently_stop_an_independent_ledger(self, job):
        """Later steps retain ``always()``; B1 additionally excludes manual dispatch."""
        moved_steps = [s for s in job["steps"]
                       if any(f"python -m {m} --nightly" in _runs(s) for m, _ in MOVED)]
        for step in moved_steps[1:]:
            condition = (step.get("if") or "").strip()
            expected = (
                "always() && github.event_name == 'schedule'"
                if "scripts.reconcile_us_candidate_episodes" in _runs(step)
                else "always()"
            )
            assert condition == expected, (
                f"{step.get('name')!r}: without always() a crashed sibling skips this "
                "module and its ledger silently stops advancing; B1 must also remain "
                "schedule-only")

    def test_the_commit_runs_even_when_a_module_failed(self, job):
        commit = next(s for s in job["steps"]
                      if "git add" in _runs(s) and "git commit" in _runs(s))
        assert (commit.get("if") or "").strip() == "always()", (
            "whatever DID advance must land: the next job's actions/checkout deletes the "
            "runner tree, so an uncommitted ledger row is a lost night — exactly how the "
            "engine job's cancel-skipped commit lost 2026-08-06")


# --------------------------------------------------------------------------- #
# 5. no cascade into the deploy
# --------------------------------------------------------------------------- #

class TestNoCascade:

    # daily.yml's `publish` GitHub Pages deploy job was RETIRED pre-private-cutover
    # (DEC:B1-MACRO-PRIVATE-CUTOVER; see tests/test_no_pages_publish.py for the
    # standing retirement guard) — there is no more deploy job for JOB to cascade
    # into. test_nothing_at_all_depends_on_this_job below is the general form of
    # this isolation claim and already covers every remaining job, `publish`
    # included were it to ever come back.

    def test_nothing_at_all_depends_on_this_job(self, daily):
        dependents = []
        for name, body in daily["jobs"].items():
            needs = body.get("needs") or []
            needs = [needs] if isinstance(needs, str) else list(needs)
            if JOB in needs:
                dependents.append(name)
        assert not dependents, (
            f"{dependents} now depend on {JOB} — the isolation claim in its comment is "
            "no longer true")


# --------------------------------------------------------------------------- #
# 6. dag declaration + conformance
# --------------------------------------------------------------------------- #

class TestDagDeclaration:

    def test_the_new_lane_is_declared_with_the_six_modules_in_order(self):
        dag = yaml.safe_load(DAG.read_text(encoding="utf-8"))
        lane = next((l for l in dag["lanes"]
                     if l["workflow"] == ".github/workflows/daily.yml"
                     and l["job"] == JOB), None)
        assert lane is not None, f"config/dag.yml declares no lane for {JOB}"
        assert [s.get("module") for s in lane["steps"]] == [m for m, _ in MOVED]
        for step in lane["steps"]:
            assert step.get("args") == ["--nightly"], (
                f"{step.get('id')}: the declared args lost --nightly, the sole-advancer flag")

    def test_the_engine_lane_no_longer_declares_them(self):
        dag = yaml.safe_load(DAG.read_text(encoding="utf-8"))
        lane = next(l for l in dag["lanes"]
                    if l["workflow"] == ".github/workflows/daily.yml"
                    and l["job"] == "engine")
        modules = {s.get("module") for s in lane["steps"]}
        assert not modules & {m for m, _ in MOVED}

    def test_conformance_is_green(self):
        from scripts.check_dag_conformance import run_conformance
        assert run_conformance(ROOT) == 0
