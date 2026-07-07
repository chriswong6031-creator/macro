"""
tests/test_ruling_graph.py — Test suite for the Ruling Graph v1 infrastructure.

Tests
-----
1.  yaml_loads          — config/ruling_graph.yml loads without YAML error
2.  schema_vocab_valid  — build module's validator returns no errors on the real graph
3.  source_quotes_present — every source_quote is a verbatim substring of source_doc
4.  check_flag_passes   — build_ruling_graph.py --check passes (committed outputs match)
5.  determinism_json    — generate JSON twice → identical bytes
6.  determinism_md      — generate MD twice → identical bytes
7.  public_json_no_internal — site JSON contains only public_research rows
8.  public_json_no_denylist — site JSON contains no denylist tokens
9.  selftest_passes     — check_ruling_conflicts.py --selftest exits 0
10. w2_respects_today   — RULING_GRAPH_TODAY env changes W2 expired-clock detection
11. cl_rows_present     — RUL-CL-1 through RUL-CL-14 all exist and are nondelegable
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Repo root and paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_RULING_YML = _REPO_ROOT / "config" / "ruling_graph.yml"
_OUT_JSON = _REPO_ROOT / "site" / "neuralwebdata" / "ruling_graph.json"
_OUT_MD = _REPO_ROOT / "docs" / "NEURAL_WEB_CASE_LAW.md"

# ---------------------------------------------------------------------------
# Import build module
# ---------------------------------------------------------------------------
_build_spec = importlib.util.spec_from_file_location(
    "build_ruling_graph",
    _REPO_ROOT / "scripts" / "build_ruling_graph.py",
)
_build_mod = importlib.util.module_from_spec(_build_spec)  # type: ignore[arg-type]
_build_spec.loader.exec_module(_build_mod)  # type: ignore[union-attr]

# Import conflict checker module
_conflict_spec = importlib.util.spec_from_file_location(
    "check_ruling_conflicts",
    _REPO_ROOT / "scripts" / "check_ruling_conflicts.py",
)
_conflict_mod = importlib.util.module_from_spec(_conflict_spec)  # type: ignore[arg-type]
_conflict_spec.loader.exec_module(_conflict_mod)  # type: ignore[union-attr]

validate = _build_mod.validate
_emit_json = _build_mod._emit_json
_emit_md = _build_mod._emit_md
_check_w2 = _conflict_mod._check_w2


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def raw_data() -> dict:
    """Load the raw YAML once for the module."""
    with _RULING_YML.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="module")
def rulings(raw_data: dict) -> list[dict]:
    return raw_data.get("rulings", [])


@pytest.fixture(scope="module")
def meta(raw_data: dict) -> dict:
    return raw_data.get("meta", {})


# ---------------------------------------------------------------------------
# Test 1: YAML loads
# ---------------------------------------------------------------------------

def test_yaml_loads():
    """config/ruling_graph.yml must load without YAML parse error."""
    assert _RULING_YML.exists(), f"ruling_graph.yml not found at {_RULING_YML}"
    with _RULING_YML.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    assert isinstance(data, dict), "ruling_graph.yml must parse to a dict"
    assert "meta" in data, "ruling_graph.yml must have a meta block"
    assert "rulings" in data, "ruling_graph.yml must have a rulings block"
    assert isinstance(data["rulings"], list), "rulings must be a list"


# ---------------------------------------------------------------------------
# Test 2: Schema / vocab validation clean (build module validator)
# ---------------------------------------------------------------------------

def test_schema_vocab_valid(raw_data: dict):
    """build_ruling_graph.validate() must return no errors on the real graph."""
    errors = validate(raw_data, _REPO_ROOT)
    assert errors == [], (
        f"Validator found {len(errors)} error(s):\n"
        + "\n".join(f"  {e}" for e in errors)
    )


# ---------------------------------------------------------------------------
# Test 3: Source quotes present verbatim in source_doc
# ---------------------------------------------------------------------------

def test_source_quotes_present(rulings: list[dict]):
    """Every source_quote must be a verbatim (whitespace-normalized) substring of source_doc."""
    failures = []
    for r in rulings:
        rid = r.get("ruling_id", "<missing>")
        sq = r.get("source_quote")
        sd = r.get("source_doc")
        if not sq or not sd:
            continue
        src_path = _REPO_ROOT / sd
        if not src_path.exists():
            failures.append(f"{rid}: source_doc not found: {sd}")
            continue
        src_text = src_path.read_text(encoding="utf-8", errors="replace")
        sq_norm = " ".join(sq.split())
        src_norm = " ".join(src_text.split())
        if sq_norm not in src_norm:
            failures.append(
                f"{rid}: source_quote not found in {sd}. "
                f"First 80 chars: {sq_norm[:80]!r}"
            )
    assert not failures, (
        f"{len(failures)} source_quote failure(s):\n"
        + "\n".join(f"  {f}" for f in failures)
    )


# ---------------------------------------------------------------------------
# Test 4: --check flag passes (committed outputs match regeneration)
# ---------------------------------------------------------------------------

def test_check_flag_passes():
    """build_ruling_graph.py --check must exit 0 (committed outputs match YAML)."""
    result = subprocess.run(
        [sys.executable, str(_REPO_ROOT / "scripts" / "build_ruling_graph.py"), "--check"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"build_ruling_graph.py --check failed (exit {result.returncode}):\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )


# ---------------------------------------------------------------------------
# Test 5+6: Determinism — two consecutive generations must be byte-identical
# ---------------------------------------------------------------------------

def test_determinism_json(raw_data: dict):
    """Generating the JSON twice must produce identical strings."""
    first = _emit_json(raw_data, _RULING_YML)
    second = _emit_json(raw_data, _RULING_YML)
    assert first == second, "JSON generation is not deterministic"


def test_determinism_md(raw_data: dict):
    """Generating the Markdown twice must produce identical strings."""
    first = _emit_md(raw_data, _RULING_YML)
    second = _emit_md(raw_data, _RULING_YML)
    assert first == second, "Markdown generation is not deterministic"


# ---------------------------------------------------------------------------
# Test 7: Public JSON contains only public_research rows
# ---------------------------------------------------------------------------

def test_public_json_no_internal():
    """site/neuralwebdata/ruling_graph.json must contain only public_research rows."""
    assert _OUT_JSON.exists(), f"Public JSON not found at {_OUT_JSON}"
    with _OUT_JSON.open(encoding="utf-8") as fh:
        data = json.load(fh)
    public_rows = data.get("rulings", [])
    bad = [r.get("ruling_id", "<missing>") for r in public_rows
           if r.get("privacy_class") != "public_research"]
    assert not bad, (
        f"Site JSON contains non-public_research rows: {bad}"
    )


# ---------------------------------------------------------------------------
# Test 8: Public JSON contains no denylist tokens
# ---------------------------------------------------------------------------

def test_public_json_no_denylist(raw_data: dict):
    """site/neuralwebdata/ruling_graph.json must not contain any denylist tokens."""
    assert _OUT_JSON.exists(), f"Public JSON not found at {_OUT_JSON}"
    denylist = [t.lower() for t in raw_data.get("meta", {}).get("public_token_denylist", [])]
    site_text = _OUT_JSON.read_text(encoding="utf-8").lower()
    hits = [t for t in denylist if t in site_text]
    assert not hits, (
        f"Site JSON contains denylist token(s): {hits} (RUL-CL-9)"
    )


# ---------------------------------------------------------------------------
# Test 9: check_ruling_conflicts.py --selftest exits 0
# ---------------------------------------------------------------------------

def test_selftest_passes():
    """check_ruling_conflicts.py --selftest must exit 0."""
    result = subprocess.run(
        [sys.executable, str(_REPO_ROOT / "scripts" / "check_ruling_conflicts.py"), "--selftest"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"check_ruling_conflicts.py --selftest failed (exit {result.returncode}):\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )


# ---------------------------------------------------------------------------
# Test 10: W2 respects RULING_GRAPH_TODAY
# ---------------------------------------------------------------------------

def test_w2_respects_today():
    """RULING_GRAPH_TODAY env must control the W2 expired-clock detection date."""
    fake_data = {
        "meta": {},
        "rulings": [
            {
                "ruling_id": "TEST-PAST-CLOCK",
                "come_back_on": "2020-01-01",
                "experiment_ref": None,
                "status": "deferred",
            },
            {
                "ruling_id": "TEST-FUTURE-CLOCK",
                "come_back_on": "2099-01-01",
                "experiment_ref": None,
                "status": "deferred",
            },
        ],
    }

    old_env = os.environ.get("RULING_GRAPH_TODAY")
    os.environ["RULING_GRAPH_TODAY"] = "2026-07-06"
    try:
        findings = _check_w2(fake_data, _REPO_ROOT)
    finally:
        if old_env is None:
            os.environ.pop("RULING_GRAPH_TODAY", None)
        else:
            os.environ["RULING_GRAPH_TODAY"] = old_env

    past_fired = any(f.get("ruling_id") == "TEST-PAST-CLOCK" for f in findings)
    future_fired = any(f.get("ruling_id") == "TEST-FUTURE-CLOCK" for f in findings)
    assert past_fired, "W2 should fire for come_back_on=2020-01-01 when today=2026-07-06"
    assert not future_fired, "W2 should NOT fire for come_back_on=2099-01-01 when today=2026-07-06"


# ---------------------------------------------------------------------------
# Test 11: RUL-CL-1 through RUL-CL-14 present and nondelegable
# ---------------------------------------------------------------------------

def test_cl_rows_present_and_nondelegable(rulings: list[dict]):
    """RUL-CL-1 through RUL-CL-14 must all exist and have nondelegable=True."""
    ruling_map = {r.get("ruling_id"): r for r in rulings}
    expected_ids = [f"RUL-CL-{i}" for i in range(1, 15)]
    missing = [rid for rid in expected_ids if rid not in ruling_map]
    assert not missing, f"Missing CL ruling IDs: {missing}"

    not_nondelegable = [
        rid for rid in expected_ids
        if not ruling_map[rid].get("nondelegable")
    ]
    assert not not_nondelegable, (
        f"CL rows that are not marked nondelegable=True: {not_nondelegable}"
    )
