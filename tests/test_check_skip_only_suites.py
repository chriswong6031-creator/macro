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
    suite = next(iter(ROOT.glob("tests/test_chart_render_inline.py")))
    thin = _fixture_jobs(
        ("thin", f"pytest tests/{suite.name}", "pip install pytest pyyaml")
    )
    rows = [r for r in GUARD.census(thin) if r["test"] == suite.name]
    assert rows and all(r["status"] == "SKIP-ONLY" for r in rows)

    paired = thin + _fixture_jobs(
        ("fat", f"pytest tests/{suite.name}",
         "pip install pytest pandas numpy pyarrow pyyaml")
    )
    rows = [r for r in GUARD.census(paired) if r["test"] == suite.name]
    assert rows and all(r["status"] == "OK" for r in rows)


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
