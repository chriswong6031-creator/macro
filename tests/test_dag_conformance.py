"""Neural Web W5a — DAG conformance tests.

Tests:
1. Parser unit tests on REAL workflow excerpts (copied as fixtures)
2. Differ tests on synthetic fixtures
3. Selftest invocation (proves GREEN/RED scenarios)
4. Live conformance test — config/dag.yml matches the LIVE workflows (the
   load-bearing assertion that reds when someone edits a lane without updating dag.yml).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure the scripts package is importable from the repo root
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.check_dag_conformance import (
    Step,
    _diff_lane,
    _extract_modules_from_run,
    _extract_steps_from_run,
    _parse_dag_yml,
    _parse_workflow,
    _run_selftest,
    run_conformance,
)


# ---------------------------------------------------------------------------
# Fixtures — real workflow excerpts (copied verbatim from live files)
# ---------------------------------------------------------------------------

# Excerpt from daily.yml engine job: the run_py spine pattern
DAILY_ENGINE_SPINE_EXCERPT = """
run_py() {
  local label="$1"; local mod="$2"
  echo "::group::$label"
  python -m "$mod" > /tmp/step.log 2>&1; local rc=$?
  cat /tmp/step.log
  echo "::endgroup::"
}
run_py "regime engine (engine.run)" engine.run
run_py "S&P allocation vector (build_spvector)" scripts.build_spvector
run_py "alternative data desk (build_alt_data)" scripts.build_alt_data
run_py "13F smart-money tracker (build_smart_money)" scripts.build_smart_money
run_py "macro dashboard + US stocks (build_site)" scripts.build_site
run_py "buy board 2.0 shadow (build_stock_board_v2)" scripts.build_stock_board_v2
run_py "impulse tracker (build_impulse)" scripts.build_impulse
run_py "congressional trades desk (build_congress)" scripts.build_congress
run_py "thematic foresight desk (build_foresight)" scripts.build_foresight
exit 0
"""

# Excerpt from daily.yml engine job: the parallel band pattern
DAILY_ENGINE_BAND_EXCERPT = """
brun() {
  local slug="$1" label="$2" mod="$3"; shift 3
  local t0 t1 rc
  t0=$(date +%s)
  { echo "$label"; python -m "$mod" "$@" 2>&1; } > "$ART/$slug.log"; rc=$?
  t1=$(date +%s)
  echo "$rc"          > "$ART/$slug.rc"
  echo "$((t1 - t0))" > "$ART/$slug.sec"
}
cl_markets() {
  brun commodities  "build commodity vector (build_commodities)"         scripts.build_commodities
  brun spr          "build strategic reserves (build_spr)"               scripts.build_spr
  brun forex        "build forex vector (build_forex)"                   scripts.build_forex
  brun bonds        "build bonds & bond-health (build_bonds)"            scripts.build_bonds
  brun crossasset   "cross-asset vector (build_crossasset)"              scripts.build_crossasset
  brun transmission "rate & inflation transmission (build_transmission)" scripts.build_transmission
  brun discovery    "discovery leaderboard (build_discovery)"            scripts.build_discovery
}
cl_gex() {
  brun gex_board    "GEX magnets board (build_gex_board)"        scripts.build_gex_board
  brun vol_regime   "index vol-regime (build_vol_regime)"        scripts.build_vol_regime
  brun options_flow "options flow desk (build_options_flow)"     scripts.build_options_flow
  brun options_skew "single-name IV skew (build_options_skew)"   scripts.build_options_skew
  brun options_ivspread "single-name IV spread (build_options_ivspread)" scripts.build_options_ivspread
}
cl_baskets() {
  brun baskets     "thematic baskets (build_baskets)"        scripts.build_baskets
  brun subsector_conf "subsector confluence desk" scripts.build_subsector_confluence
  brun subsector_conf_ndx "nasdaq-100 subsector confluence desk" scripts.build_subsector_confluence --nasdaq
  brun subsector_conf_rut "russell-2000 subsector confluence desk" scripts.build_subsector_confluence --russell
  brun cohort_metrics "W0.4 cohort metrics" scripts.build_cohort_metrics
  brun news        "news suite (build_news)"                 scripts.build_news
  brun methodology "methodology page (build_methodology)"    scripts.build_methodology
}
cl_special() { brun special "special situations desk" scripts.build_special_situations; }
cl_misc() {
  brun seasonality   "factor seasonality (build_seasonality)"      scripts.build_seasonality
  brun reports       "research reports section (build_reports)"     scripts.build_reports
  brun cycle         "cycle intelligence page (build_cycle)"        scripts.build_cycle
  brun sectorcyc     "sector cycle intelligence (build_sector_cycles)" scripts.build_sector_cycles
  brun countrycyc    "country cycle intelligence (build_country_cycles)" scripts.build_country_cycles
  brun policy_intent "policy intent desk (policy_intent_desk)"      engine.policy_intent_desk
  brun policy_watch  "fed & policy watch (build_policy_watch)"      scripts.build_policy_watch
  brun index_changes "S&P index changes (build_index_changes)"     scripts.build_index_changes
}
cl_markets & cl_gex & cl_baskets & cl_special & cl_misc &
wait
exit 0
"""

# Excerpt from engine-render.yml: the named function composition pattern (W5a: central added)
ENGINE_RENDER_COMPOSITION_EXCERPT = """
spine() {
  run_py "S&P allocation vector (build_spvector)"        scripts.build_spvector
  run_py "alternative data desk (build_alt_data)"        scripts.build_alt_data
  run_py "13F smart-money tracker (build_smart_money)"   scripts.build_smart_money
  run_py "macro dashboard + US stocks (build_site)"      scripts.build_site
  run_py "buy board 2.0 shadow (build_stock_board_v2)"   scripts.build_stock_board_v2
  run_py "congressional trades desk (build_congress)"    scripts.build_congress
}
hub() { run_py "bitcoin vector + landing hub (build_vector)" scripts.build_vector; }
central() { run_py "US sector central intelligence (build_sector_central)" scripts.build_sector_central; }
case "$SCOPE" in
  all)
    spine; band; central; hub; us_pages; libs ;;
esac
exit 0
"""

# Excerpt from render.yml: central() function definition and call
RENDER_CENTRAL_EXCERPT = """
central() { run_py "US sector central intelligence (build_sector_central)" scripts.build_sector_central; }
case "$SCOPE" in
  all)
    spine; band; central; hub; us_pages; libs ;;
esac
exit 0
"""

# Excerpt from intraday-fastpath.yml
FASTPATH_EXCERPT = """
python -m scripts.refresh_regime_if_stale
python -m scripts.build_live_overlay
python -m scripts.build_risk_state
"""


# ---------------------------------------------------------------------------
# 1. Parser unit tests on real workflow excerpts
# ---------------------------------------------------------------------------

class TestParserRealExcerpts:
    def test_run_py_spine_extracts_modules(self):
        modules = _extract_modules_from_run(DAILY_ENGINE_SPINE_EXCERPT)
        assert "engine.run" in modules
        assert "scripts.build_spvector" in modules
        assert "scripts.build_site" in modules
        assert "scripts.build_foresight" in modules

    def test_brun_cluster_extracts_modules(self):
        modules = _extract_modules_from_run(DAILY_ENGINE_BAND_EXCERPT)
        # cl_markets
        assert "scripts.build_commodities" in modules
        assert "scripts.build_spr" in modules
        assert "scripts.build_discovery" in modules
        # cl_gex
        assert "scripts.build_gex_board" in modules
        assert "scripts.build_vol_regime" in modules
        # cl_baskets
        assert "scripts.build_baskets" in modules
        assert "scripts.build_subsector_confluence" in modules
        assert "scripts.build_cohort_metrics" in modules
        # cl_misc
        assert "scripts.build_sector_cycles" in modules
        assert "engine.policy_intent_desk" in modules

    def test_python_m_direct_extracts(self):
        modules = _extract_modules_from_run(FASTPATH_EXCERPT)
        assert "scripts.refresh_regime_if_stale" in modules
        assert "scripts.build_live_overlay" in modules
        assert "scripts.build_risk_state" in modules

    def test_composition_detects_central(self):
        """Parser fix: single-line function definition `central() { run_py ... }` must NOT
        be consumed by the composition branch.  The inner run_py module is extracted directly.

        The composition branch now checks that the keyword is NOT immediately followed by '('
        before treating the line as a composition call.  This makes build_sector_central
        and build_vector visible to the conformance checker in render + engine-render lanes.
        """
        modules = _extract_modules_from_run(RENDER_CENTRAL_EXCERPT)
        # After the parser fix, the inner module IS extracted from the function body
        assert "scripts.build_sector_central" in modules
        # The composition CALL line still emits __segment__ tokens
        assert "__segment__central" in modules

    def test_composition_detects_central_in_engine_render(self):
        """Parser fix: hub() and central() single-line definitions in engine-render yield
        their inner modules, not just segment tokens."""
        modules = _extract_modules_from_run(ENGINE_RENDER_COMPOSITION_EXCERPT)
        # Inner modules are extracted from the function definitions
        assert "scripts.build_sector_central" in modules
        assert "scripts.build_vector" in modules
        # Composition CALL line still emits segment tokens
        assert "__segment__central" in modules
        assert "__segment__hub" in modules


# ---------------------------------------------------------------------------
# 2. Differ tests
# ---------------------------------------------------------------------------

class TestDiffer:
    def test_green_exact_match(self):
        declared = ["scripts.a", "scripts.b", "scripts.c"]
        actual = ["scripts.a", "scripts.b", "scripts.c"]
        errors = _diff_lane(declared, actual, "fake/lane", [])
        assert errors == []

    def test_red_missing_from_actual(self):
        declared = ["scripts.a", "scripts.b", "scripts.c"]
        actual = ["scripts.a", "scripts.b"]   # c missing
        errors = _diff_lane(declared, actual, "fake/lane", [])
        assert any("scripts.c" in e for e in errors)

    def test_red_extra_in_actual(self):
        declared = ["scripts.a", "scripts.b"]
        actual = ["scripts.a", "scripts.b", "scripts.extra"]
        errors = _diff_lane(declared, actual, "fake/lane", [])
        assert any("scripts.extra" in e for e in errors)

    def test_green_with_documented_divergence(self):
        """A module absent from actual is covered by a divergence entry -> no error."""
        declared = ["scripts.a", "scripts.build_gex_board"]
        actual = ["scripts.a"]  # build_gex_board absent
        divergences = [
            {
                "lanes": ["engine-render"],
                "differs": "cl_gex omits scripts.build_gex_board",
                "reason": "live network",
            }
        ]
        errors = _diff_lane(declared, actual, "engine-render / engine-render", divergences)
        assert errors == [], f"Expected no errors but got: {errors}"

    def test_suspect_divergence_counts_as_covered(self):
        """A suspect divergence covers the mismatch (no hard error), just visible."""
        declared = ["scripts.a", "scripts.b"]
        actual = ["scripts.a"]  # b missing
        divergences = [
            {
                "lanes": ["render"],
                "differs": "scripts.b omitted",
                "status": "suspect",
                "note": "needs review",
            }
        ]
        errors = _diff_lane(declared, actual, "render / render", divergences)
        assert errors == [], f"Suspect divergence should cover the mismatch: {errors}"

    def test_segment_tokens_not_flagged(self):
        """Virtual __segment__xxx tokens from composition parsing are ignored."""
        declared = ["scripts.a", "scripts.b"]
        actual = ["scripts.a", "scripts.b", "__segment__spine", "__segment__band"]
        errors = _diff_lane(declared, actual, "fake/lane", [])
        assert errors == []

    def test_red_serial_reorder(self):
        """Reordering two serial steps (both present but wrong order) must RED."""
        declared = [
            Step(id="a", module="scripts.a", cluster=None),
            Step(id="b", module="scripts.b", cluster=None),
            Step(id="c", module="scripts.c", cluster=None),
        ]
        actual = [
            Step(id="", module="scripts.b", cluster=None),  # swapped
            Step(id="", module="scripts.a", cluster=None),  # swapped
            Step(id="", module="scripts.c", cluster=None),
        ]
        errors = _diff_lane(declared, actual, "fake/lane", [])
        assert errors, "Expected RED on reorder but got GREEN"
        assert any("ORDER" in e or "order" in e.lower() for e in errors), (
            f"Expected order-mismatch error but got: {errors}"
        )

    def test_red_cluster_member_migrated(self):
        """Moving a module from one cluster to another must RED."""
        declared = [
            Step(id="band", module="scripts.mod_x1", cluster="cl_x"),
            Step(id="band", module="scripts.mod_x2", cluster="cl_x"),
            Step(id="band", module="scripts.mod_y1", cluster="cl_y"),
        ]
        actual = [
            Step(id="", module="scripts.mod_x1", cluster="cl_x"),
            Step(id="", module="scripts.mod_x2", cluster="cl_y"),  # migrated to cl_y
            Step(id="", module="scripts.mod_y1", cluster="cl_y"),
        ]
        errors = _diff_lane(declared, actual, "fake/lane", [])
        assert errors, "Expected RED on cluster member migration but got GREEN"
        assert any("MIGRATED" in e or "migrated" in e.lower() for e in errors), (
            f"Expected cluster-migration error but got: {errors}"
        )

    def test_green_serial_reorder_covered_by_divergence(self):
        """A reorder covered by a divergence entry must remain GREEN."""
        declared = [
            Step(id="a", module="scripts.a", cluster=None),
            Step(id="b", module="scripts.b", cluster=None),
        ]
        actual = [
            Step(id="", module="scripts.b", cluster=None),
            Step(id="", module="scripts.a", cluster=None),
        ]
        divergences = [
            {
                "lanes": ["fake"],
                "differs": "scripts.a and scripts.b reordered",
                "reason": "test",
            }
        ]
        errors = _diff_lane(declared, actual, "fake / lane", divergences)
        assert errors == [], f"Covered reorder should be GREEN but got: {errors}"


# ---------------------------------------------------------------------------
# 2b. Parser-driven positive-control test (regression guard for the parser fix)
# ---------------------------------------------------------------------------

class TestParserDrivenPositiveControl:
    """Positive-control tests that exercise the FULL parse→diff pipeline against
    a real (or near-real) workflow file.

    This class of test would have caught the original blocker: hub() and central()
    function definitions consumed as __segment__ tokens, making build_sector_central
    and build_vector invisible to the conformance checker.  The existing RED-b/RED-c
    tests feed hand-built Step lists into the differ and bypass the parser entirely.
    """

    def test_remove_central_from_engine_render_causes_red(self, tmp_path):
        """Parser-driven positive control: remove central() definition from a copy of
        engine-render.yml and assert the conformance check exits RED naming build_sector_central.

        This test would have caught the original blocker: without the parser fix, the
        central() definition line was consumed as __segment__central and build_sector_central
        was never extracted, so its absence was invisible to the checker.
        """
        import shutil
        import yaml

        # --- set up a minimal dag that declares build_sector_central as a serial step ---
        dag_fixture = {
            "meta": {"schema_version": 1, "granularity": "workflow-step"},
            "lanes": [
                {
                    "workflow": str(tmp_path / "engine-render.yml"),
                    "job": "engine-render",
                    "steps": [
                        {"id": "build_sector_central", "module": "scripts.build_sector_central"},
                    ],
                }
            ],
            "divergences": [],
            "modules": [],
        }
        dag_path = tmp_path / "dag.yml"
        dag_path.write_text(yaml.dump(dag_fixture))

        # --- copy real engine-render.yml into tmp_path ---
        real_wf = REPO_ROOT / ".github" / "workflows" / "engine-render.yml"
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        shutil.copy(real_wf, wf_dir / "engine-render.yml")

        # --- parse the UNMODIFIED workflow: build_sector_central MUST be found ---
        job_steps = _parse_workflow(wf_dir / "engine-render.yml")
        assert "engine-render" in job_steps, "engine-render job not found in parsed workflow"
        actual_modules = [s.module for s in job_steps["engine-render"]]
        assert "scripts.build_sector_central" in actual_modules, (
            "build_sector_central NOT found in unmodified engine-render.yml parse — "
            "the parser fix is not working correctly"
        )

        # --- now remove central() definition AND its call from the composition line ---
        wf_text = (wf_dir / "engine-render.yml").read_text()
        # Remove the single-line central() function definition
        wf_text_no_central = "\n".join(
            line for line in wf_text.splitlines()
            if not line.strip().startswith("central()")
        )
        # Also remove 'central' from the composition call line so it's a real absence
        wf_text_no_central = wf_text_no_central.replace(
            "spine; band; central; hub; us_pages; libs",
            "spine; band; hub; us_pages; libs",
        )
        (wf_dir / "engine-render.yml").write_text(wf_text_no_central)

        # --- parse modified workflow: build_sector_central must be ABSENT ---
        job_steps_mod = _parse_workflow(wf_dir / "engine-render.yml")
        actual_modules_mod = [s.module for s in job_steps_mod["engine-render"]]
        assert "scripts.build_sector_central" not in actual_modules_mod, (
            "build_sector_central still found after removing central() — "
            "the test fixture modification did not work"
        )

        # --- diff: declared has build_sector_central; actual does not -> RED ---
        from scripts.check_dag_conformance import _parse_dag_yml
        declared_lanes, divergences = _parse_dag_yml(dag_path)
        assert len(declared_lanes) == 1

        declared_steps = declared_lanes[0].steps
        actual_steps = job_steps_mod["engine-render"]
        lane_key = f"{declared_lanes[0].workflow} / {declared_lanes[0].job}"
        errors = _diff_lane(declared_steps, actual_steps, lane_key, divergences)

        assert errors, (
            "Expected RED (build_sector_central absent) but got GREEN. "
            "This means the conformance checker would silently miss a missing sector_central."
        )
        assert any("build_sector_central" in e for e in errors), (
            f"RED error found but does not name build_sector_central: {errors}"
        )


# ---------------------------------------------------------------------------
# 3. Self-test invocation
# ---------------------------------------------------------------------------

class TestSelftest:
    def test_selftest_passes(self):
        """The checker's own synthetic GREEN/RED scenarios must all pass."""
        rc = _run_selftest()
        assert rc == 0, "check_dag_conformance --selftest returned non-zero"


# ---------------------------------------------------------------------------
# 4. Live conformance — the load-bearing assertion
# ---------------------------------------------------------------------------

class TestLiveConformance:
    def test_dag_yml_matches_live_workflows(self):
        """config/dag.yml must match the live .github/workflows/ files.

        This is the gate that reds CI when someone edits a lane without updating dag.yml.
        """
        rc = run_conformance(REPO_ROOT, verbose=False)
        assert rc == 0, (
            "DAG conformance check FAILED — config/dag.yml is out of sync with the live "
            "workflow files.  Update config/dag.yml (or add a divergences entry if the "
            "difference is intentional), then re-run this test."
        )

    def test_dag_yml_parses(self):
        """config/dag.yml must be valid YAML with the expected top-level keys."""
        dag_path = REPO_ROOT / "config" / "dag.yml"
        assert dag_path.exists(), f"config/dag.yml not found at {dag_path}"
        lanes, divergences = _parse_dag_yml(dag_path)
        assert len(lanes) > 0, "dag.yml declares no lanes"
        assert isinstance(divergences, list), "dag.yml divergences must be a list"

    def test_suspect_divergences_are_few(self):
        """Suspect divergences must not grow — only shrinks allowed."""
        dag_path = REPO_ROOT / "config" / "dag.yml"
        import yaml
        raw = yaml.safe_load(dag_path.read_text())
        suspect = [d for d in raw.get("divergences", []) if d.get("status") == "suspect"]
        # At W5a adoption there are 2 suspect entries; this bound may only decrease.
        assert len(suspect) <= 2, (
            f"Suspect divergence count increased ({len(suspect)} > 2). "
            "The suspect list only shrinks — either fix the drift or add a documented "
            "divergence entry with a cited reason."
        )

    def test_all_documented_divergences_have_evidence(self):
        """Every documented divergence must cite a file:line evidence field."""
        dag_path = REPO_ROOT / "config" / "dag.yml"
        import yaml
        raw = yaml.safe_load(dag_path.read_text())
        missing_evidence = []
        for div in raw.get("divergences", []):
            if div.get("status") == "suspect":
                continue  # suspect entries have a note, not evidence
            if not div.get("evidence"):
                missing_evidence.append(div.get("differs", "<unnamed>")[:80])
        assert missing_evidence == [], (
            f"Documented divergences missing 'evidence' field: {missing_evidence}"
        )
