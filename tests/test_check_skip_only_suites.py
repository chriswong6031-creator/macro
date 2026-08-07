"""Unit tests for the SKIP-ONLY suite guard.

The guard's value is entirely in what it *detects*, so most of these tests seed a
defect and assert it goes red — a detector that silently stops detecting reports a
clean repo forever, which is worse than no guard at all.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

SPEC = importlib.util.spec_from_file_location(
    "check_skip_only_suites", ROOT / "scripts" / "check_skip_only_suites.py"
)
assert SPEC and SPEC.loader
GUARD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GUARD
SPEC.loader.exec_module(GUARD)


# ── gate detection ───────────────────────────────────────────────────────────

def _gates(tmp_path: Path, source: str) -> dict[str, list[str]]:
    path = tmp_path / "test_fixture.py"
    path.write_text(source)
    return GUARD.skip_gates(path)


def test_direct_importorskip_is_a_gate(tmp_path: Path) -> None:
    gates = _gates(tmp_path, 'import pytest\n\n\ndef test_x():\n'
                             '    pytest.importorskip("pandas")\n')
    assert "pandas" in gates


def test_importorskip_inside_a_helper_is_still_a_gate(tmp_path: Path) -> None:
    """tests/test_chart_render_m2.py wraps the call in pytest_importorskip_soft."""
    gates = _gates(
        tmp_path,
        "import pytest\n\n\n"
        "def pytest_importorskip_soft(name):\n"
        "    return pytest.importorskip(name)\n\n\n"
        "def test_x():\n"
        '    pytest_importorskip_soft("scipy")\n',
    )
    assert "scipy" in gates


def test_try_import_probe_read_by_skipif_is_a_gate(tmp_path: Path) -> None:
    gates = _gates(
        tmp_path,
        "import pytest\n\n"
        "try:\n"
        "    import jinja2\n"
        "    _HAVE = True\n"
        "except ImportError:\n"
        "    _HAVE = False\n\n\n"
        '@pytest.mark.skipif(not _HAVE, reason="no jinja2")\n'
        "def test_x():\n"
        "    pass\n",
    )
    assert "jinja2" in gates


def test_in_body_skip_on_a_probe_flag_is_a_gate(tmp_path: Path) -> None:
    """tests/test_staleness_replay.py skips inside the body, not at collection."""
    gates = _gates(
        tmp_path,
        "import pytest\n\n"
        "try:\n"
        "    import scripts.replay_standout_pipeline as _rsp\n"
        "    _HAS = True\n"
        "except Exception:\n"
        "    _HAS = False\n\n\n"
        "def test_x():\n"
        "    if not _HAS:\n"
        '        pytest.skip("absent")\n',
    )
    assert "scripts.replay_standout_pipeline" in gates


def test_artifact_and_binary_skips_are_not_gates(tmp_path: Path) -> None:
    """A missing parquet or a missing `node` is not something pip can install."""
    gates = _gates(
        tmp_path,
        "import pytest\n"
        "import shutil\n"
        "from pathlib import Path\n\n"
        "_PANEL = Path('data/panel.parquet')\n"
        "_HAS_NODE = shutil.which('node') is not None\n\n\n"
        '@pytest.mark.skipif(not _PANEL.exists(), reason="no panel")\n'
        "def test_a():\n"
        "    pass\n\n\n"
        '@pytest.mark.skipif(not _HAS_NODE, reason="no node")\n'
        "def test_b():\n"
        "    pass\n",
    )
    assert gates == {}


# ── install-line semantics ───────────────────────────────────────────────────

def test_distribution_names_map_to_import_names() -> None:
    modules = GUARD.provided_modules(GUARD.install_packages("pip install pyyaml pillow"))
    assert {"yaml", "PIL"} <= modules
    assert "pyyaml" not in modules


def test_hard_dependencies_are_closed_over() -> None:
    modules = GUARD.provided_modules(GUARD.install_packages("pip install pytest pandas"))
    assert "numpy" in modules, "pandas cannot import without numpy"
    assert "pyarrow" not in modules, "pandas does NOT pull a parquet engine"


def test_requirements_file_expands() -> None:
    modules = GUARD.provided_modules(
        GUARD.install_packages("pip install -r requirements.txt")
    )
    assert {"pandas", "yaml", "boto3", "sklearn"} <= modules


def test_no_install_line_means_stdlib_only() -> None:
    assert GUARD.install_packages(None) is None
    modules = GUARD.provided_modules(None)
    assert "json" in modules and "pandas" not in modules


def test_only_run_steps_name_tests_not_path_filters() -> None:
    """ci.yml lists ~1100 test files under on.pull_request.paths. If those counted
    as coverage, every suite in the repo would read as satisfied by ci-pack."""
    jobs = GUARD.workflow_jobs()
    ci_pack = [j for j in jobs if j["job"].endswith("::ci-pack")]
    assert ci_pack, "ci.yml must still declare the ci-pack matrix job"
    assert all(not j["tests"] for j in ci_pack)


# ── first-party gates resolve to what they actually need ─────────────────────

def test_first_party_gate_resolves_to_its_third_party_closure() -> None:
    needs = GUARD.required_modules("engine.indicators_m2")
    assert "numpy" in needs
    assert "engine" not in needs, "the file is always in the checkout"


def test_stdlib_is_never_something_a_job_must_install() -> None:
    assert GUARD.required_modules("os") == set()


def test_lazy_imports_do_not_count_as_module_level(tmp_path: Path) -> None:
    import ast

    tree = ast.parse(
        "import json\n\n"
        "try:\n"
        "    import optional_thing\n"
        "except ImportError:\n"
        "    optional_thing = None\n\n\n"
        "def f():\n"
        "    import pandas\n"
        "    return pandas\n"
    )
    found = GUARD._module_level_imports(tree)
    assert found == {"json"}


# ── end-to-end verdicts ──────────────────────────────────────────────────────

def _fixture_jobs(*specs: tuple[str, str, str | None]) -> list[dict]:
    return [GUARD._job_view(jid, "fixture.yml", run, install)
            for jid, run, install in specs]


def test_thin_only_lane_reads_skip_only_and_the_pair_repairs_it() -> None:
    """The #3760 shape, end to end: seeded defect red, seeded fix green."""
    rel = "tests/test_chart_render_inline.py"
    assert (ROOT / rel).is_file()
    thin = _fixture_jobs(("thin", f"pytest {rel}", "pip install pytest pyyaml"))
    rows = [r for r in GUARD.census(thin) if r["test"] == rel]
    assert rows and all(r["status"] == "SKIP-ONLY" for r in rows)

    paired = thin + _fixture_jobs(
        ("fat", f"pytest {rel}", "pip install pytest pandas numpy pyarrow pyyaml")
    )
    rows = [r for r in GUARD.census(paired) if r["test"] == rel]
    assert rows and all(r["status"] == "OK" for r in rows)


# ── scope: the whole tree, not tests/ (#4693) ────────────────────────────────

def test_rows_are_keyed_by_repo_relative_path() -> None:
    """A basename stopped identifying a suite the moment scope left tests/."""
    rows = GUARD.census()
    assert rows
    assert all("/" in r["test"] for r in rows)


def test_a_research_resident_suite_is_in_scope() -> None:
    """The suites this guard could not see: written beside their instrument
    because the packet that shipped them was fenced to files-only."""
    discovered = set(GUARD.discover_suites())
    assert "research/prophet_us_audit/test_label_grading_battery.py" in discovered
    assert "research/signal_engine/test_buy_filters.py" in discovered


def test_a_seeded_suite_outside_tests_reads_skip_only_when_its_lane_is_thin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mutation, end to end, one directory over from where it used to work.

    Before the widening this produced NO rows at all: the suite was outside
    `tests/`, so the census never looked at it and the gate stayed green while every
    one of its tests skipped in the only job that named it. Verified against the
    real tree during #4693 — the pre-change guard reported `SKIP-ONLY 0` and exited
    0 with exactly this suite seeded and wired into `workflow-yaml`.
    """
    rel = "research/packet/test_seeded_guard.py"
    seeded = tmp_path / rel
    seeded.parent.mkdir(parents=True)
    seeded.write_text(
        "import pytest\n\n\n"
        "def test_needs_pandas():\n"
        '    pytest.importorskip("pandas")\n'
    )
    monkeypatch.setattr(GUARD, "ROOT", tmp_path)
    monkeypatch.setattr(GUARD, "discover_suites", lambda: [rel])

    thin = _fixture_jobs(("thin", f"pytest {rel}", "pip install pytest pyyaml"))
    rows = [r for r in GUARD.census(thin) if r["test"] == rel]
    assert rows, "a suite outside tests/ must be censused at all"
    assert all(r["status"] == "SKIP-ONLY" for r in rows)

    paired = thin + _fixture_jobs(
        ("fat", f"pytest {rel}", "pip install pytest pandas pyyaml")
    )
    rows = [r for r in GUARD.census(paired) if r["test"] == rel]
    assert rows and all(r["status"] == "OK" for r in rows)


def test_a_test_shaped_cli_instrument_is_never_censused() -> None:
    """Widening by FILENAME would have added three permanent false work items."""
    discovered = set(GUARD.discover_suites())
    for rel in (
        "research/cn_prophet_audit/sector_intel_exante_test.py",
        "research/signal_engine/test_breadth_consume.py",
        "research/signal_engine/test_buyfilter.py",
    ):
        assert (ROOT / rel).is_file(), f"{rel} moved; re-derive the classification"
        assert rel not in discovered


@pytest.mark.parametrize(
    "run_text,expected",
    [
        # The spelling every run: step in this repo actually uses.
        ("python -m pytest tests/test_ci_pack.py -q", {"tests/test_ci_pack.py"}),
        # Outside tests/ — unnameable before the widening.
        ("python -m pytest research/signal_engine/test_buy_filters.py -q",
         {"research/signal_engine/test_buy_filters.py"}),
        ("python -m pytest scripts/research/test_run_w4_controls_fingerprints.py -q",
         {"scripts/research/test_run_w4_controls_fingerprints.py"}),
        # The *_test.py shape pytest also collects.
        ("python -m pytest research/pkt/thing_test.py -q",
         {"research/pkt/thing_test.py"}),
        # A leading ./ is the same file.
        ("python -m pytest ./tests/test_ci_pack.py -q", {"tests/test_ci_pack.py"}),
    ],
)
def test_run_step_parsing_keeps_the_directory(run_text: str, expected: set) -> None:
    assert GUARD._job_view("j", "f.yml", run_text, None)["tests"] == expected


def test_a_job_naming_one_directorys_suite_does_not_claim_another() -> None:
    """Basename-only matching credited `tests/test_x.py` with running
    `research/a/test_x.py`. With scope beyond tests/ that is a wrong answer, not a
    harmless one — it would mark a genuinely dark suite as covered."""
    jobs = _fixture_jobs(
        ("names-tests-copy", "pytest tests/test_buy_filters.py",
         "pip install pytest")
    )
    rows = [r for r in GUARD.census(jobs)
            if r["test"] == "research/signal_engine/test_buy_filters.py"]
    assert all(not r["naming_jobs"] for r in rows)


def test_a_suite_no_job_names_is_unrun_not_skip_only() -> None:
    rows = GUARD.census(_fixture_jobs(("none", "echo hi", "pip install pytest")))
    assert rows and all(r["status"] == "UNRUN" for r in rows)


def test_repo_is_clean(capsys: pytest.CaptureFixture[str]) -> None:
    """The gate itself, against the real workflows. Any new skip-only suite fails
    here — the whole point of the guard."""
    assert GUARD.main([]) == 0, capsys.readouterr().out


def test_annotations_start_the_line(capsys: pytest.CaptureFixture[str]) -> None:
    """House law: GitHub drops `::error` unless it starts the line, so the guard
    must print bare, never through a logger."""
    assert GUARD.main(["--selftest"]) == 0
    for line in capsys.readouterr().out.splitlines():
        if "::error" in line or "::warning" in line:
            assert line.startswith("::"), line
