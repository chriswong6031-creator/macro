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

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_house_law_registry.py"
COMMITTED_DOCS = REPO_ROOT / "docs" / "HOUSE_LAW_CI_GUARD_SUITE.md"


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


def _first_diff_pos(a: str, b: str) -> int:
    for i, (ca, cb) in enumerate(zip(a, b)):
        if ca != cb:
            return i
    return min(len(a), len(b))
