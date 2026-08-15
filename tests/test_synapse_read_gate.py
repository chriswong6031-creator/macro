"""
tests/test_synapse_read_gate.py — Unit tests for the synapse read-gate scanner.

All tests operate on synthetic file trees (tmp_path) — no real disk reads
of the actual codebase. Tests exercise the scanner core via extra_files
injection, so CI does not depend on a full repo checkout for correctness
of the detection logic.

Test cases
----------
1. declared_consumer_is_clean
   A module listed in consumers[] produces no finding for that artifact.

2. undeclared_reader_produces_warn
   A module that contains the artifact path literal, but is NOT in
   consumers[] / producer / known_extra_writers, produces a WARN finding.

3. article2_undeclared_reader_produces_hard
   Same as above, but the module is mapped to an Article-2 surface
   (engine/alert_triage.py) → severity must be HARD.

4. baseline_suppresses_existing_finding
   A finding that appears in the loaded baseline dict is suppressed
   (n_suppressed increments, it is not returned as new).

5. stale_baseline_detection
   A baseline entry whose module+artifact_id no longer fires is
   reported as 'stale baseline entry — prune' (tested via the printed
   output of _report_findings).

6. selftest_passes
   The --selftest flag exits 0 against the real repo registry.

7. producer_is_excluded
   The registered producer of an artifact is not flagged.

8. known_extra_writer_is_excluded
   A module listed in known_extra_writers is not flagged.
"""
from __future__ import annotations

import io
import sys
import textwrap
from contextlib import redirect_stdout
from pathlib import Path

import pytest

# Repo root: two levels above tests/
REPO_ROOT = Path(__file__).resolve().parent.parent

# Ensure the repo is importable
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_synapse_reads import (  # noqa: E402
    Finding,
    _ARTICLE2_MAP,
    _baseline_key,
    _build_article2_modules,
    _load_baseline,
    _report_findings,
    _run_selftest,
    scan_findings,
    _prose_masked_source,
)
from engine.neuralweb.synapse import load_registry  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers — minimal synthetic registry
# ---------------------------------------------------------------------------


def _make_reg(
    path: str = "data/fake/artifact.json",
    producer: str = "engine/producer.py",
    consumers: list[str] | None = None,
    known_extra_writers: list[str] | None = None,
    article2_surfaces: list[str] | None = None,
) -> dict:
    """Build a minimal synthetic registry for a single artifact."""
    return {
        "meta": {
            "schema_version": 1,
            "description": "synthetic",
            "tier_vocabulary": ["display", "infrastructure"],
            "article2_surfaces": article2_surfaces or [],
        },
        "artifacts": {
            "fake-artifact": {
                "path": path,
                "format": "json",
                "producer": producer,
                "known_extra_writers": known_extra_writers or [],
                "owner_program": "test",
                "cadence": "daily-engine",
                "storage": "git",
                "asof_field": "asof",
                "freshness_sla_hours": 30,
                "schema": "none",
                "tier": "infrastructure",
                "weights": "none",
                "consumers": consumers or [],
            }
        },
    }


def _source_with_path(path: str) -> str:
    return textwrap.dedent(f"""\
        import json
        data = json.load(open("{path}"))
    """)


# ---------------------------------------------------------------------------
# Test 1: declared consumer is clean
# ---------------------------------------------------------------------------


def test_declared_consumer_is_clean(tmp_path: Path) -> None:
    """A declared consumer must produce zero findings."""
    reg = _make_reg(
        path="data/fake/artifact.json",
        producer="engine/producer.py",
        consumers=["engine/consumer.py"],
    )
    extra = {
        "engine/consumer.py": _source_with_path("data/fake/artifact.json"),
    }
    findings = scan_findings(tmp_path, reg=reg, extra_files=extra)
    assert findings == [], f"Expected no findings, got: {findings}"


# ---------------------------------------------------------------------------
# Test 2: undeclared reader -> WARN
# ---------------------------------------------------------------------------


def test_undeclared_reader_produces_warn(tmp_path: Path) -> None:
    """An undeclared reader (non-Article-2) must produce a WARN finding."""
    reg = _make_reg(
        path="data/fake/artifact.json",
        producer="engine/producer.py",
        consumers=[],
        article2_surfaces=[],  # no Article-2 surfaces registered
    )
    extra = {
        "engine/sneaky_reader.py": _source_with_path("data/fake/artifact.json"),
    }
    findings = scan_findings(tmp_path, reg=reg, extra_files=extra)
    assert len(findings) == 1
    f = findings[0]
    assert f.artifact_id == "fake-artifact"
    assert f.module == "engine/sneaky_reader.py"
    assert f.severity == "WARN"


# ---------------------------------------------------------------------------
# Test 3: Article-2 undeclared reader -> HARD
# ---------------------------------------------------------------------------


def test_article2_undeclared_reader_produces_hard(tmp_path: Path) -> None:
    """An undeclared reader that is an Article-2 surface must produce a HARD finding."""
    # alert_triage -> engine/alert_triage.py is our canonical Article-2 module
    art2_module = "engine/alert_triage.py"
    reg = _make_reg(
        path="data/fake/artifact.json",
        producer="engine/producer.py",
        consumers=[],
        article2_surfaces=["alert_triage"],  # registered in meta
    )
    extra = {
        art2_module: _source_with_path("data/fake/artifact.json"),
    }
    findings = scan_findings(tmp_path, reg=reg, extra_files=extra)
    hard = [f for f in findings if f.severity == "HARD"]
    assert len(hard) == 1, f"Expected 1 HARD finding, got: {findings}"
    assert hard[0].module == art2_module


# ---------------------------------------------------------------------------
# Test 4: baseline suppression works
# ---------------------------------------------------------------------------


def test_baseline_suppression(tmp_path: Path, capsys) -> None:
    """Findings present in the baseline must be counted as suppressed, not new."""
    f = Finding(
        module="engine/sneaky.py",
        artifact_id="fake-artifact",
        line_no=2,
        severity="WARN",
    )
    # Baseline dict keyed by module|artifact_id
    baseline = {_baseline_key(f): f.as_dict()}

    buf = io.StringIO()
    with redirect_stdout(buf):
        n_warn, n_hard = _report_findings([f], baseline, tmp_path)

    assert n_warn == 0
    assert n_hard == 0
    output = buf.getvalue()
    assert "baseline-suppressed" in output


# ---------------------------------------------------------------------------
# Test 5: stale baseline detection
# ---------------------------------------------------------------------------


def test_stale_baseline_detection(tmp_path: Path) -> None:
    """A baseline entry that no longer fires must be reported as 'stale baseline entry'."""
    stale = {
        "engine/old_reader.py|fake-artifact": {
            "module": "engine/old_reader.py",
            "artifact_id": "fake-artifact",
            "line_no": 5,
            "severity": "WARN",
        }
    }
    # No findings at all (the stale entry no longer fires)
    buf = io.StringIO()
    with redirect_stdout(buf):
        n_warn, n_hard = _report_findings([], stale, tmp_path)

    output = buf.getvalue()
    assert "stale baseline entry" in output
    assert "engine/old_reader.py" in output
    assert n_warn == 0
    assert n_hard == 0


# ---------------------------------------------------------------------------
# Test 6: selftest passes against the real registry
# ---------------------------------------------------------------------------


def test_selftest_passes() -> None:
    """The --selftest mode must exit 0 against the real repo registry."""
    rc = _run_selftest(REPO_ROOT)
    assert rc == 0, f"selftest returned non-zero exit code: {rc}"


# ---------------------------------------------------------------------------
# Test 7: producer is excluded
# ---------------------------------------------------------------------------


def test_producer_is_excluded(tmp_path: Path) -> None:
    """The registered producer must not be flagged as an undeclared reader."""
    reg = _make_reg(
        path="data/fake/artifact.json",
        producer="engine/producer.py",
        consumers=[],
    )
    extra = {
        "engine/producer.py": _source_with_path("data/fake/artifact.json"),
    }
    findings = scan_findings(tmp_path, reg=reg, extra_files=extra)
    assert findings == [], f"Producer was incorrectly flagged: {findings}"


# ---------------------------------------------------------------------------
# Test 8: known_extra_writer is excluded
# ---------------------------------------------------------------------------


def test_known_extra_writer_is_excluded(tmp_path: Path) -> None:
    """A module listed in known_extra_writers must not be flagged."""
    reg = _make_reg(
        path="data/fake/artifact.json",
        producer="engine/producer.py",
        consumers=[],
        known_extra_writers=[
            "scripts/extra_writer.py — hand-curated edits",
        ],
    )
    extra = {
        "scripts/extra_writer.py": _source_with_path("data/fake/artifact.json"),
    }
    findings = scan_findings(tmp_path, reg=reg, extra_files=extra)
    assert findings == [], f"known_extra_writer was incorrectly flagged: {findings}"


# ---------------------------------------------------------------------------
# Test 9: placeholder path normalized to dir prefix
# ---------------------------------------------------------------------------


def test_placeholder_path_normalized(tmp_path: Path) -> None:
    """For a pattern path like site/signals/<SYM>.json, search uses 'site/signals/'."""
    from scripts.check_synapse_reads import _normalize_search_path
    assert _normalize_search_path("site/signals/<SYM>.json") == "site/signals/"
    assert _normalize_search_path("data/regime/latest.json") == "data/regime/latest.json"


# ---------------------------------------------------------------------------
# Test 10: Article-2 module set builder
# ---------------------------------------------------------------------------


def test_article2_module_set_builder() -> None:
    """_build_article2_modules should return the correct set from the real registry."""
    reg = load_registry(REPO_ROOT)
    article2_modules = _build_article2_modules(REPO_ROOT, reg)
    # alert_triage is always declared in the real registry
    assert "engine/alert_triage.py" in article2_modules
    # board_ordering -> build_stock_library
    assert "scripts/build_stock_library.py" in article2_modules
    # top_setups -> build_site
    assert "scripts/build_site.py" in article2_modules


# ---------------------------------------------------------------------------
# Test 11: a MENTION is not a READ (prose masking)
# ---------------------------------------------------------------------------
#
# The gate scanned raw file text, so a registered path named in a DOCSTRING was
# reported as a consumer. On 2026-08-14 that hard-failed the fleet on a
# paragraph: scripts/build_stock_library.py::_name_score_asof explains a measured
# (date, ticker) join against data/name_score/us_calls.parquet — the read it
# describes lives in the grader — and the Article-2 tier turned that sentence
# into a money-path violation reddening `synapse-read-gate` for every PR.
#
# These cases pin BOTH directions. Masking that only proved "prose is silent"
# would be satisfied by a guard that had gone blind, so every silent case here
# is paired with a firing one that differs ONLY in whether the path reaches code.


def test_docstring_mention_alone_is_not_a_read(tmp_path: Path) -> None:
    """A path named only in a module docstring is a mention, not a consumer."""
    reg = _make_reg(path="data/fake/artifact.json", producer="engine/producer.py")
    extra = {
        "engine/prose_only.py": textwrap.dedent("""\
            \"\"\"Explains a join against data/fake/artifact.json without opening it.\"\"\"
            import json
            data = json.loads("{}")
        """),
    }
    assert scan_findings(tmp_path, reg=reg, extra_files=extra) == []


def test_comment_mention_alone_is_not_a_read(tmp_path: Path) -> None:
    """A path named only in a comment is a mention, not a consumer."""
    reg = _make_reg(path="data/fake/artifact.json", producer="engine/producer.py")
    extra = {
        "engine/comment_only.py": textwrap.dedent("""\
            import json
            # historically compared against data/fake/artifact.json
            data = json.loads("{}")
        """),
    }
    assert scan_findings(tmp_path, reg=reg, extra_files=extra) == []


def test_function_docstring_mention_alone_is_not_a_read(tmp_path: Path) -> None:
    """Function-level docstrings are masked too, not just the module docstring."""
    reg = _make_reg(path="data/fake/artifact.json", producer="engine/producer.py")
    extra = {
        "engine/fn_prose.py": textwrap.dedent("""\
            def explain():
                \"\"\"Describes data/fake/artifact.json for the reader.\"\"\"
                return 1
        """),
    }
    assert scan_findings(tmp_path, reg=reg, extra_files=extra) == []


def test_prose_masking_does_not_hide_a_real_read(tmp_path: Path) -> None:
    """The load-bearing case: prose AND a real read must still fire, at the CODE line.

    This is what stops the fix from being a blindfold — the file opens with a
    docstring naming the artifact and then actually reads it.
    """
    reg = _make_reg(path="data/fake/artifact.json", producer="engine/producer.py")
    extra = {
        "engine/prose_and_read.py": textwrap.dedent("""\
            \"\"\"Prose about data/fake/artifact.json.\"\"\"
            import json
            data = json.load(open("data/fake/artifact.json"))
        """),
    }
    findings = scan_findings(tmp_path, reg=reg, extra_files=extra)
    assert len(findings) == 1, f"real read was masked away: {findings}"
    assert findings[0].module == "engine/prose_and_read.py"
    # Line 1 is the docstring; the reported line must be the executable one.
    assert findings[0].line_no == 3, (
        "reported line must point at code, not at the masked docstring"
    )


def test_a_bare_string_assignment_is_still_a_read(tmp_path: Path) -> None:
    """Masking covers docstrings and comments ONLY — every other literal counts."""
    reg = _make_reg(path="data/fake/artifact.json", producer="engine/producer.py")
    extra = {
        "engine/assigns.py": 'PATH = "data/fake/artifact.json"\n',
    }
    findings = scan_findings(tmp_path, reg=reg, extra_files=extra)
    assert len(findings) == 1, "a path assigned to a variable is still a read"


def test_unparseable_module_fails_open(tmp_path: Path) -> None:
    """A module that will not parse keeps its OLD reach, never goes quietly blind."""
    reg = _make_reg(path="data/fake/artifact.json", producer="engine/producer.py")
    extra = {
        "engine/broken.py": 'def broken(:\n    x = "data/fake/artifact.json"\n',
    }
    findings = scan_findings(tmp_path, reg=reg, extra_files=extra)
    assert len(findings) == 1, "an unparseable file must still be scanned as before"


def test_the_shipped_build_stock_library_docstring_is_not_a_consumer() -> None:
    """Regression pin on the real file that reddened the fleet.

    scripts/build_stock_library.py names data/name_score/us_calls.parquet exactly
    once, inside _name_score_asof's docstring. If a future edit gives that module
    a genuine read, this test SHOULD start failing — the correct response is then
    to declare it a consumer in config/synapse.yml, not to loosen the mask.
    """
    source = (REPO_ROOT / "scripts" / "build_stock_library.py").read_text(
        encoding="utf-8", errors="replace"
    )
    needle = "data/name_score/us_calls.parquet"
    assert needle in source, "fixture drifted — the docstring mention is gone"
    assert needle not in _prose_masked_source(source), (
        "the only mention is prose; masking it must remove it from the code view"
    )
