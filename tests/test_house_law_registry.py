"""Tests for the house-law registry meta-guard.

Three test suites:
  1. Integration: real registry passes all passes against the real repo.
  2. Selftest: --selftest flag passes via subprocess.
  3. Docs idempotency: --emit-docs regenerating into a tempfile equals the committed
     docs file byte-for-byte.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_house_law_registry.py"
COMMITTED_DOCS = REPO_ROOT / "docs" / "HOUSE_LAW_CI_GUARD_SUITE.md"

sys.path.insert(0, str(REPO_ROOT))

from scripts.check_house_law_registry import (  # noqa: E402
    _load_workflow_jobs,
    pass_c_wiring as _pass_c,
)
from scripts.workflow_run_source import WorkflowRunSourceError  # noqa: E402


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + args,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


class TestRegistryIntegration:
    """The real registry must pass all passes against the real repo."""

    def test_real_registry_passes(self):
        result = _run([])
        assert result.returncode == 0, (
            f"check_house_law_registry.py exited {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
        # Should print a PASS summary line
        assert "house-law registry OK" in result.stdout, (
            f"Expected 'house-law registry OK' in output, got:\n{result.stdout}"
        )

    def test_summary_contains_counts(self):
        result = _run([])
        assert result.returncode == 0
        # Summary line format: "house-law registry OK — N laws, M enforced in CI, K discipline/spurious-only"
        assert "laws" in result.stdout
        assert "enforced in CI" in result.stdout


class TestSelftest:
    """--selftest flag must pass."""

    def test_selftest_passes(self):
        result = _run(["--selftest"])
        assert result.returncode == 0, (
            f"--selftest exited {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
        assert "selftest OK" in result.stdout, (
            f"Expected 'selftest OK' in output, got:\n{result.stdout}"
        )


class TestDocsIdempotency:
    """--emit-docs regenerating into a tempfile must equal the committed docs file byte-for-byte."""

    def test_emit_docs_idempotent(self):
        assert COMMITTED_DOCS.exists(), (
            f"Committed docs file {COMMITTED_DOCS} does not exist — "
            f"run `python3 scripts/check_house_law_registry.py --emit-docs` first"
        )

        committed_text = COMMITTED_DOCS.read_text()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, prefix="house_law_docs_test_"
        ) as f:
            tmp_path = f.name

        try:
            result = _run(["--emit-docs", tmp_path])
            assert result.returncode == 0, (
                f"--emit-docs exited {result.returncode}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )

            regenerated_text = Path(tmp_path).read_text()
            # Strip the date line before comparing (it changes daily)
            # The last line contains the generation date; strip it for idempotency
            def strip_date_line(text: str) -> str:
                lines = text.splitlines()
                # Remove lines that contain _Generated YYYY-MM-DD
                return "\n".join(
                    line for line in lines
                    if "_Generated " not in line
                )

            committed_stripped = strip_date_line(committed_text)
            regenerated_stripped = strip_date_line(regenerated_text)

            assert committed_stripped == regenerated_stripped, (
                "Regenerated docs do not match committed docs (ignoring date line).\n"
                "Run `python3 scripts/check_house_law_registry.py --emit-docs` to update.\n"
                f"First difference at character "
                f"{_first_diff_pos(committed_stripped, regenerated_stripped)}"
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_emit_docs_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = str(Path(tmpdir) / "subdir" / "test_docs.md")
            result = _run(["--emit-docs", out_path])
            assert result.returncode == 0
            assert Path(out_path).exists(), f"docs file not created at {out_path}"
            content = Path(out_path).read_text()
            assert "AUTO-GENERATED" in content
            assert "House Law CI Guard Suite" in content

    def test_emit_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = str(Path(tmpdir) / "registry.json")
            result = _run(["--emit-json", out_path])
            assert result.returncode == 0
            import json
            data = json.loads(Path(out_path).read_text())
            assert isinstance(data, list)
            assert len(data) > 0
            # Each entry should have law_id
            assert all("law_id" in e for e in data)


class TestWiringCensusSeesThroughExtraction:
    """MUTATION-grade: a hard law wired ONLY inside an extracted script body.

    The 512KB-cap diet (PR #5431) moved four ``run: |`` bodies out of daily.yml
    into ``scripts/ci/daily_*.sh``. Pass C reads step ``run:`` bodies to prove a
    registered guard is actually invoked, so an extracted body makes every guard
    inside it read as UNWIRED. The heal shipped at the time plumbed the one
    affected module back into the YAML as a validated argument — that fixed the
    single law and left the NEXT extraction to red again. This pins the general
    property instead: the census resolves the indirection, so a module that
    appears nowhere in the workflow text still satisfies wiring.

    The negative case is what makes this a pin rather than a tautology — drop the
    provenance marker and the census must RAISE, never quietly report the law
    unwired (a finding a future session would "fix" by weakening the registry).
    """

    WF = """\
name: synthetic
on:
  push:
jobs:
  engine:
    runs-on: ubuntu-latest
    steps:
      - name: inline builder
        run: |
          python -m scripts.build_inline_thing
      - name: extracted band
        run: bash scripts/ci/daily_extracted.sh
"""

    SCRIPT = (
        "#!/usr/bin/env bash\n"
        "# EXTRACTED-VERBATIM-FROM: .github/workflows/daily.yml\n"
        "set -e\n"
        "python -m scripts.check_synthetic_hard_law\n"
    )

    LAW_ID = "synthetic.extracted_wiring"

    def _build(self, tmp_path: Path, script_text: str) -> Path:
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "synthetic.yml").write_text(self.WF)
        ci_dir = tmp_path / "scripts" / "ci"
        ci_dir.mkdir(parents=True)
        (ci_dir / "daily_extracted.sh").write_text(script_text)
        (tmp_path / "scripts" / "check_synthetic_hard_law.py").write_text(
            "# --selftest\ndef main(): pass\n"
        )
        return tmp_path

    def _checks(self) -> list[dict]:
        return [
            {
                "law_id": self.LAW_ID,
                "summary": "A hard law invoked only from an extracted body",
                "source_ref": ["scripts/check_synthetic_hard_law.py"],
                "severity": "hard",
                "check_script": "scripts/check_synthetic_hard_law.py",
                "ci_wiring": [
                    {
                        "workflow": ".github/workflows/synthetic.yml",
                        "job": "engine",
                        "lane": "scheduled",
                    }
                ],
                "selftest": True,
                "allowlist": None,
                "ratchet": None,
                "known_limits": [],
                "owner_program": "test",
            }
        ]

    def test_module_only_in_the_extracted_script_satisfies_wiring(self, tmp_path):
        root = self._build(tmp_path, self.SCRIPT)
        # The guarantee is non-vacuous only while the module is absent from the YAML.
        assert "check_synthetic_hard_law" not in self.WF

        findings: list[str] = []
        _pass_c(self._checks(), root, findings)
        assert findings == [], (
            "the wiring census went blind to a guard invoked from an extracted "
            f"script body: {findings}"
        )

    def test_unresolvable_extraction_raises_instead_of_reporting_unwired(
        self, tmp_path
    ):
        root = self._build(
            tmp_path, self.SCRIPT.replace("# EXTRACTED-VERBATIM-FROM:", "# from:")
        )
        findings: list[str] = []
        with pytest.raises(WorkflowRunSourceError):
            _pass_c(self._checks(), root, findings)

    def test_live_daily_yml_keeps_the_delegated_theme_graph_law_wired(self):
        """The real case the argument plumbing was standing in for.

        ``scripts.check_theme_graph_contracts`` is invoked from inside
        ``scripts/ci/daily_engine_regional_desk_builders.sh`` and appears nowhere
        in daily.yml. If this reds, the seam broke — do NOT re-add an argument to
        the invocation line to paper over it.
        """
        daily = (REPO_ROOT / ".github" / "workflows" / "daily.yml").read_text()
        assert "check_theme_graph_contracts" not in daily, (
            "daily.yml names the delegated guard again — the census would then "
            "pass for the wrong reason and stop pinning the extraction seam"
        )
        jobs = _load_workflow_jobs(
            REPO_ROOT / ".github" / "workflows" / "daily.yml", REPO_ROOT
        )
        assert "check_theme_graph_contracts" in jobs["engine"]


def _first_diff_pos(a: str, b: str) -> int:
    for i, (ca, cb) in enumerate(zip(a, b)):
        if ca != cb:
            return i
    return min(len(a), len(b))
