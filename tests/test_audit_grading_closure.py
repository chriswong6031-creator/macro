"""Tests for scripts/audit_grading_closure.py — grading-closure standing audit.

NW Rails PR-6 (R2 audit).  Uses synthetic temp-dir ledgers to verify:
  - verdict classification for each of CLOSED / GRADER-STARVED / LOG-ONLY
  - absent-store handling (absent-by-design vs absent-locally)
  - parquet and JSONL ledger reading
  - JSON + markdown output writing
  - run_as_collect_step never raises

All assertions are on observable outputs (verdict field, JSON file contents,
markdown table) — not on internal implementation details.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pandas as pd
import pytest

import scripts.audit_grading_closure as agc

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _make_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows))


def _make_parquet(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def _run_single(tmp_path: Path, spec: dict) -> dict:
    """Run audit_entry for one synthetic spec rooted at tmp_path."""
    return agc.audit_entry(spec, tmp_path)


# ---------------------------------------------------------------------------
# VERDICT: LOG-ONLY — grader=None
# ---------------------------------------------------------------------------

class TestLogOnly:
    def test_jsonl_present_no_grader(self, tmp_path: Path) -> None:
        ledger_path = tmp_path / "data" / "test_log.jsonl"
        _make_jsonl(ledger_path, [
            {"asof": "2026-01-01", "val": 1.0, "graded": None},
            {"asof": "2026-01-02", "val": 2.0, "graded": None},
        ])
        spec = {
            "key": "test_log_only",
            "path": "data/test_log.jsonl",
            "format": "jsonl",
            "grader": None,
            "grade_field": "graded",
            "grade_ts_field": None,
            "tune_step": False,
            "storage_note": None,
        }
        result = _run_single(tmp_path, spec)
        assert result["verdict"] == "LOG-ONLY"
        assert result["n_logged"] == 2
        assert result["n_graded"] == 0
        assert result["storage"] == "present"
        assert result["grader_wired"] == "N"
        assert result["tune_step"] == "N"

    def test_parquet_present_no_grader(self, tmp_path: Path) -> None:
        p = tmp_path / "data" / "test.parquet"
        _make_parquet(p, [{"date": "2026-01-01", "band": "HIGH"}] * 5)
        spec = {
            "key": "log_only_parquet",
            "path": "data/test.parquet",
            "format": "parquet",
            "grader": None,
            "grade_field": None,
            "grade_ts_field": None,
            "tune_step": False,
            "storage_note": None,
        }
        result = _run_single(tmp_path, spec)
        assert result["verdict"] == "LOG-ONLY"
        assert result["n_logged"] == 5
        assert result["grader_wired"] == "N"


# ---------------------------------------------------------------------------
# VERDICT: GRADER-STARVED — grader wired, n_graded == 0
# ---------------------------------------------------------------------------

class TestGraderStarved:
    def test_jsonl_no_grades_yet(self, tmp_path: Path) -> None:
        ledger_path = tmp_path / "data" / "risk_radar" / "forward_log.jsonl"
        _make_jsonl(ledger_path, [
            {"asof": "2026-01-01", "state": "RISK-OFF", "graded": None},
            {"asof": "2026-01-08", "state": "RISK-ON",  "graded": None},
        ])
        spec = {
            "key": "risk_radar_forward_log",
            "path": "data/risk_radar/forward_log.jsonl",
            "format": "jsonl",
            "grader": "engine/risk_radar_audit.py",
            "grade_field": "graded",
            "grade_ts_field": None,
            "tune_step": False,
            "storage_note": None,
        }
        result = _run_single(tmp_path, spec)
        assert result["verdict"] == "GRADER-STARVED"
        assert result["n_logged"] == 2
        assert result["n_graded"] == 0
        assert result["grader_wired"] == "Y:engine/risk_radar_audit.py"

    def test_parquet_grade_col_all_null(self, tmp_path: Path) -> None:
        p = tmp_path / "data" / "board_ledger" / "hk_board.parquet"
        _make_parquet(p, [
            {"date": "2026-01-01", "ticker": "0700.HK", "fwd_mfe_21": None},
            {"date": "2026-01-02", "ticker": "9988.HK", "fwd_mfe_21": None},
        ])
        spec = {
            "key": "board_ledger_hk",
            "path": "data/board_ledger/hk_board.parquet",
            "format": "parquet",
            "grader": "engine/board_ledger.py",
            "grade_field": "fwd_mfe_21",
            "grade_ts_field": None,
            "tune_step": False,
            "storage_note": None,
        }
        result = _run_single(tmp_path, spec)
        assert result["verdict"] == "GRADER-STARVED"
        assert result["n_logged"] == 2
        assert result["n_graded"] == 0

    def test_tune_step_reflected(self, tmp_path: Path) -> None:
        ledger_path = tmp_path / "data" / "market_state" / "forward_log.jsonl"
        _make_jsonl(ledger_path, [{"asof": "2026-01-01", "graded": None}])
        spec = {
            "key": "market_state_forward_log",
            "path": "data/market_state/forward_log.jsonl",
            "format": "jsonl",
            "grader": "engine/market_state_audit.py",
            "grade_field": "graded",
            "grade_ts_field": None,
            "tune_step": True,   # tune_step wired
            "storage_note": None,
        }
        result = _run_single(tmp_path, spec)
        assert result["verdict"] == "GRADER-STARVED"
        assert result["tune_step"] == "Y"

    def test_absent_store_no_storage_note(self, tmp_path: Path) -> None:
        spec = {
            "key": "missing_ledger",
            "path": "data/does_not_exist.jsonl",
            "format": "jsonl",
            "grader": "engine/some_grader.py",
            "grade_field": "graded",
            "grade_ts_field": None,
            "tune_step": False,
            "storage_note": None,
        }
        result = _run_single(tmp_path, spec)
        assert result["verdict"] == "GRADER-STARVED"
        assert result["storage"] == "absent-locally"
        assert result["n_logged"] == 0
        assert result["n_graded"] == 0


# ---------------------------------------------------------------------------
# VERDICT: CLOSED — grader wired + n_graded > 0
# ---------------------------------------------------------------------------

class TestClosed:
    def test_jsonl_all_graded(self, tmp_path: Path) -> None:
        ledger_path = tmp_path / "data" / "qledger" / "grades.jsonl"
        rows = [
            {"claim_id": "c1", "horizon_d": 21, "graded_at": "2026-06-01T10:00:00+00:00",
             "excess": 0.03, "hit": True},
            {"claim_id": "c2", "horizon_d": 21, "graded_at": "2026-06-15T10:00:00+00:00",
             "excess": -0.01, "hit": False},
        ]
        _make_jsonl(ledger_path, rows)
        spec = {
            "key": "qledger_grades",
            "path": "data/qledger/grades.jsonl",
            "format": "jsonl",
            "grader": "scripts/grade_qledger.py",
            "grade_field": "graded_at",
            "grade_ts_field": "graded_at",
            "tune_step": False,
            "storage_note": None,
        }
        result = _run_single(tmp_path, spec)
        assert result["verdict"] == "CLOSED"
        assert result["n_logged"] == 2
        assert result["n_graded"] == 2
        assert result["last_graded_at"] == "2026-06-15T10:00:00+00:00"
        assert result["grader_wired"] == "Y:scripts/grade_qledger.py"

    def test_parquet_some_graded(self, tmp_path: Path) -> None:
        p = tmp_path / "data" / "signal_archive" / "track_record.parquet"
        _make_parquet(p, [
            {"ticker": "AAPL", "fwd_ret_20": 0.05},
            {"ticker": "MSFT", "fwd_ret_20": -0.02},
            {"ticker": "GOOG", "fwd_ret_20": None},   # pending
        ])
        spec = {
            "key": "signal_archive_track_record",
            "path": "data/signal_archive/track_record.parquet",
            "format": "parquet",
            "grader": "engine/track_record.py",
            "grade_field": "fwd_ret_20",
            "grade_ts_field": None,
            "tune_step": False,
            "storage_note": None,
        }
        result = _run_single(tmp_path, spec)
        assert result["verdict"] == "CLOSED"
        assert result["n_logged"] == 3
        assert result["n_graded"] == 2

    def test_jsonl_partial_graded(self, tmp_path: Path) -> None:
        """Mixed graded/pending rows — still CLOSED as long as at least one graded."""
        p = tmp_path / "data" / "froth_fragility" / "log.jsonl"
        _make_jsonl(p, [
            {"asof": "2026-01-01", "graded": {"worst_dd": -0.12, "vix_jump": 1.4}},
            {"asof": "2026-04-01", "graded": None},  # pending
        ])
        spec = {
            "key": "froth_fragility_log",
            "path": "data/froth_fragility/log.jsonl",
            "format": "jsonl",
            "grader": "engine/froth_fragility.py",
            "grade_field": "graded",
            "grade_ts_field": None,
            "tune_step": False,
            "storage_note": None,
        }
        result = _run_single(tmp_path, spec)
        assert result["verdict"] == "CLOSED"
        assert result["n_graded"] == 1
        assert result["n_logged"] == 2


# ---------------------------------------------------------------------------
# ABSENT-BY-DESIGN handling
# ---------------------------------------------------------------------------

class TestAbsentByDesign:
    def test_absent_with_storage_note(self, tmp_path: Path) -> None:
        spec = {
            "key": "oracle_reversion_forward",
            "path": "data/oracle/reversion_forward",
            "format": "parquet_dir",
            "grader": "scripts/oracle_reversion_forward_ledger.py",
            "grade_field": "matured",
            "grade_ts_field": None,
            "tune_step": False,
            "storage_note": "absent-by-design: seeded only after first reversion compound passes gauntlet",
        }
        result = _run_single(tmp_path, spec)
        assert result["verdict"] == "GRADER-STARVED"
        assert "absent-by-design" in result["storage"]
        assert result["n_logged"] == 0
        assert result["n_graded"] == 0

    def test_log_only_absent_no_note(self, tmp_path: Path) -> None:
        spec = {
            "key": "orphan_log",
            "path": "data/some/absent_log.jsonl",
            "format": "jsonl",
            "grader": None,
            "grade_field": None,
            "grade_ts_field": None,
            "tune_step": False,
            "storage_note": None,
        }
        result = _run_single(tmp_path, spec)
        assert result["verdict"] == "LOG-ONLY"
        assert result["storage"] == "absent-locally"


# ---------------------------------------------------------------------------
# parquet_dir format (oracle reversion_forward)
# ---------------------------------------------------------------------------

class TestParquetDir:
    def test_parquet_dir_with_graded_files(self, tmp_path: Path) -> None:
        d = tmp_path / "data" / "oracle" / "reversion_forward"
        d.mkdir(parents=True)
        _make_jsonl(d / "compound_a.jsonl", [
            {"compound_id": "a", "fire_date": "2026-01-15", "matured": True,  "ret_exit": 0.04},
            {"compound_id": "a", "fire_date": "2026-02-15", "matured": False, "ret_exit": None},
        ])
        _make_jsonl(d / "compound_b.jsonl", [
            {"compound_id": "b", "fire_date": "2026-01-20", "matured": True, "ret_exit": -0.01},
        ])
        spec = {
            "key": "oracle_reversion_forward",
            "path": "data/oracle/reversion_forward",
            "format": "parquet_dir",
            "grader": "scripts/oracle_reversion_forward_ledger.py",
            "grade_field": "matured",
            "grade_ts_field": None,
            "tune_step": False,
            "storage_note": None,
        }
        result = _run_single(tmp_path, spec)
        assert result["verdict"] == "CLOSED"
        assert result["n_logged"] == 3        # 2 in compound_a + 1 in compound_b
        assert result["n_graded"] == 2        # matured=True in both compounds


# ---------------------------------------------------------------------------
# Full run() — JSON and markdown outputs
# ---------------------------------------------------------------------------

class TestRunOutputs:
    def _build_mini_root(self, tmp_path: Path) -> Path:
        """Minimal fake repo with two ledgers: one CLOSED, one LOG-ONLY."""
        # CLOSED: qledger grades
        grades_p = tmp_path / "data" / "qledger" / "grades.jsonl"
        _make_jsonl(grades_p, [
            {"claim_id": "x1", "graded_at": "2026-06-01T00:00:00+00:00", "hit": True},
        ])
        # LOG-ONLY: breadth_divergence
        bd_p = tmp_path / "data" / "breadth_divergence" / "forward_log.parquet"
        _make_parquet(bd_p, [{"date": "2026-01-01", "band": "HIGH"}])
        # Also needed by qledger_claims sidecar lookup: empty claims.jsonl
        claims_p = tmp_path / "data" / "qledger" / "claims.jsonl"
        _make_jsonl(claims_p, [{"desk": "d1", "asof": "2026-06-01", "horizon_d": 21}])
        return tmp_path

    def test_json_written(self, tmp_path: Path) -> None:
        root = self._build_mini_root(tmp_path)
        payload = agc.run(root=root, write=True)
        json_path = root / "data" / "governance" / "grading_closure.json"
        assert json_path.exists(), "grading_closure.json was not written"
        loaded = json.loads(json_path.read_text())
        assert loaded["schema"] == "grading_closure.v1"
        assert "ledgers" in loaded
        assert "n_closed" in loaded
        assert "n_log_only" in loaded

    def test_markdown_written(self, tmp_path: Path) -> None:
        root = self._build_mini_root(tmp_path)
        agc.run(root=root, write=True)
        md_path = root / "docs" / "GRADING_CLOSURE.md"
        assert md_path.exists(), "GRADING_CLOSURE.md was not written"
        md_text = md_path.read_text()
        # table header row must be present
        assert "| Ledger |" in md_text
        assert "CLOSED" in md_text or "GRADER-STARVED" in md_text or "LOG-ONLY" in md_text

    def test_check_mode_no_writes(self, tmp_path: Path) -> None:
        root = self._build_mini_root(tmp_path)
        payload = agc.run(root=root, write=False)
        json_path = root / "data" / "governance" / "grading_closure.json"
        md_path = root / "docs" / "GRADING_CLOSURE.md"
        assert not json_path.exists(), "json should not be written in check mode"
        assert not md_path.exists(), "md should not be written in check mode"
        assert isinstance(payload, dict)
        assert "ledgers" in payload

    def test_payload_structure(self, tmp_path: Path) -> None:
        root = self._build_mini_root(tmp_path)
        payload = agc.run(root=root, write=False)
        assert payload["n_ledgers"] == len(agc.INVENTORY)
        assert isinstance(payload["ledgers"], list)
        for r in payload["ledgers"]:
            assert "key" in r
            assert "verdict" in r
            assert r["verdict"] in ("CLOSED", "GRADER-STARVED", "LOG-ONLY")
            assert "n_logged" in r
            assert "n_graded" in r
            assert "grader_wired" in r
            assert isinstance(r["graders"], list)
            assert r["tune_step"] in ("Y", "N")


# ---------------------------------------------------------------------------
# run_as_collect_step never raises
# ---------------------------------------------------------------------------

class TestCollectStepResilience:
    def test_never_raises_on_broken_root(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Simulate a crash inside run() and confirm the collect step doesn't propagate it."""
        def _broken_run(*args, **kwargs):
            raise RuntimeError("simulated audit crash")
        monkeypatch.setattr(agc, "run", _broken_run)
        # Must not raise:
        agc.run_as_collect_step()

    def test_never_raises_on_missing_data(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """With an empty tmp_path as root all stores absent — should silently finish."""
        import scripts.audit_grading_closure as _agc
        original_run = _agc.run

        def _patched_run(*args, **kwargs):
            # call with empty tmp_path root so all ledger files are absent
            return original_run(root=tmp_path, write=False)

        monkeypatch.setattr(_agc, "run", _patched_run)
        _agc.run_as_collect_step()  # must not raise


# ---------------------------------------------------------------------------
# Inventory completeness: every spec has required keys
# ---------------------------------------------------------------------------

class TestInventorySchema:
    REQUIRED = {"key", "path", "format", "graders", "grade_field",
                "grade_ts_field", "tune_step", "storage_note"}

    def test_all_specs_have_required_keys(self) -> None:
        for spec in agc.INVENTORY:
            missing = self.REQUIRED - spec.keys()
            assert not missing, f"spec {spec.get('key')!r} missing keys: {missing}"

    def test_all_keys_unique(self) -> None:
        keys = [s["key"] for s in agc.INVENTORY]
        assert len(keys) == len(set(keys)), f"duplicate keys: {[k for k in keys if keys.count(k) > 1]}"

    def test_all_formats_known(self) -> None:
        known = {"jsonl", "parquet", "parquet_dir", "json"}
        for spec in agc.INVENTORY:
            assert spec["format"] in known, f"{spec['key']}: unknown format {spec['format']!r}"


# ---------------------------------------------------------------------------
# One-to-many grader mapping (2026-08-14)
# ---------------------------------------------------------------------------
# The inventory used to map each ledger to exactly ONE grader. data/china_sector_cycles/
# forward_log.parquet named only engine/china_sector_cycles_grader.py — which publishes
# to site/chinasectordata/cycles_scorecard.json — while the n_graded this audit reports
# for that ledger is read out of data/china_sector_cycles/scorecards/, written by the
# SHARED scripts/grade_promises.py (china_sector_cycles is in its ENGINES list, graded
# on the same gates as the US/country siblings). An evidence-gathering session reading
# the audit was told the promise-grader did not cover CN. These tests pin the fix.

def _grade_promises_engines() -> list[str]:
    """Read the real ENGINES list out of scripts/grade_promises.py.

    Parsed with ast rather than imported: the module pulls pandas and
    engine.promise_graders at import time, and this guard must stay cheap and
    independent of whether those import cleanly.
    """
    src = (REPO_ROOT / "scripts" / "grade_promises.py").read_text()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "ENGINES":
                    return list(ast.literal_eval(node.value))
    raise AssertionError("ENGINES not found in scripts/grade_promises.py")


class TestGraderMapping:
    def test_spec_graders_normalises_both_shapes(self) -> None:
        """`graders` list is canonical; `grader` stays a working legacy alias."""
        assert agc.spec_graders({"graders": ["a.py", "b.py"]}) == ["a.py", "b.py"]
        assert agc.spec_graders({"grader": "a.py"}) == ["a.py"]
        assert agc.spec_graders({"grader": None}) == []
        assert agc.spec_graders({"graders": []}) == []
        assert agc.spec_graders({}) == []
        assert agc.spec_graders({"graders": "a.py"}) == ["a.py"]      # bare string
        assert agc.spec_graders({"graders": ["a.py", "a.py"]}) == ["a.py"]  # deduped

    def test_grader_wired_renders_every_module(self) -> None:
        """grader_wired keeps its 'Y' prefix (build_measurement's RUL-4 test) and
        names EVERY wired module, not just the first."""
        assert agc._grader_wired([]) == "N"
        assert agc._grader_wired(["a.py"]) == "Y:a.py"
        assert agc._grader_wired(["a.py", "b.py"]) == "Y:a.py,b.py"

    def test_multi_grader_entry_reports_all_graders(self, tmp_path: Path) -> None:
        """An entry with two graders reports both, and still verdicts as wired."""
        ledger = tmp_path / "data" / "multi" / "log.jsonl"
        _make_jsonl(ledger, [{"id": 1, "graded": True}])
        result = _run_single(tmp_path, {
            "key": "multi_grader_ledger",
            "path": "data/multi/log.jsonl",
            "format": "jsonl",
            "graders": ["engine/first_grader.py", "scripts/second_grader.py"],
            "grade_field": "graded",
            "grade_ts_field": None,
            "tune_step": False,
            "storage_note": None,
        })
        assert result["graders"] == ["engine/first_grader.py", "scripts/second_grader.py"]
        assert result["grader_wired"] == "Y:engine/first_grader.py,scripts/second_grader.py"
        assert result["verdict"] == "CLOSED"

    def test_every_declared_grader_module_exists(self) -> None:
        """A renamed or deleted grader must not keep reading as wired."""
        missing = [
            (spec["key"], g)
            for spec in agc.INVENTORY
            for g in agc.spec_graders(spec)
            if not (REPO_ROOT / g).is_file()
        ]
        assert not missing, f"inventory names grader modules that do not exist: {missing}"

    def test_promise_graded_engines_are_all_in_the_inventory(self) -> None:
        """Every engine scripts/grade_promises.py grades must be a mapped ledger.

        This is the check that was missing: adding an engine to ENGINES without
        wiring its forward log here leaves the audit reading that engine's
        scorecard-derived n_graded with no idea who produced it.
        """
        engines = _grade_promises_engines()
        mapped = set(agc.PROMISE_SCORECARD_ENGINES.values())
        assert set(engines) == mapped, (
            f"scripts/grade_promises.py ENGINES={sorted(engines)} but "
            f"PROMISE_SCORECARD_ENGINES maps {sorted(mapped)} — wire the new engine "
            f"into scripts/audit_grading_closure.py"
        )

    def test_promise_graded_ledgers_name_the_promise_grader(self) -> None:
        """Every ledger whose n_graded comes from a promises scorecard must name
        scripts/grade_promises.py among its graders — the exact defect fixed here."""
        by_key = {s["key"]: s for s in agc.INVENTORY}
        for key in agc.PROMISE_SCORECARD_ENGINES:
            assert key in by_key, f"{key} is mapped to a scorecard dir but is not in INVENTORY"
            graders = agc.spec_graders(by_key[key])
            assert agc.PROMISE_GRADER in graders, (
                f"{key} reads its n_graded from data/"
                f"{agc.PROMISE_SCORECARD_ENGINES[key]}/scorecards/ (written by "
                f"{agc.PROMISE_GRADER}) but does not name it in `graders`: {graders}"
            )

    def test_china_sector_cycles_names_both_graders(self) -> None:
        """Regression pin for the reported defect."""
        spec = next(s for s in agc.INVENTORY
                    if s["key"] == "china_sector_cycles_forward_log")
        graders = agc.spec_graders(spec)
        assert "engine/china_sector_cycles_grader.py" in graders
        assert "scripts/grade_promises.py" in graders

    def test_scorecard_engine_map_is_not_a_substring_test(self) -> None:
        """'sector' is a substring of BOTH sector_cycles_forward_log and
        china_sector_cycles_forward_log — the old branch resolved china to the US
        directory. Pin that each key maps to its OWN engine directory."""
        for key, engine in agc.PROMISE_SCORECARD_ENGINES.items():
            assert key == f"{engine}_forward_log", (
                f"{key} maps to data/{engine}/ — the map and the ledger key disagree"
            )


class TestMarkdownMultiGrader:
    def test_md_table_lists_every_grader(self, tmp_path: Path) -> None:
        """The rendered table must show both modules, each backticked."""
        payload = {
            "schema": "grading_closure.v1",
            "generated_at": "2026-08-14T00:00:00+00:00",
            "n_ledgers": 1, "n_closed": 1, "n_grader_starved": 0, "n_log_only": 0,
            "ledgers": [{
                "key": "china_sector_cycles_forward_log",
                "path": "data/china_sector_cycles/forward_log.parquet",
                "storage": "present",
                "grader_wired": "Y:engine/china_sector_cycles_grader.py,scripts/grade_promises.py",
                "graders": ["engine/china_sector_cycles_grader.py",
                            "scripts/grade_promises.py"],
                "n_logged": 10, "n_graded": 5,
                "last_graded_at": None, "tune_step": "N", "verdict": "CLOSED",
            }],
        }
        agc._write_md(payload, tmp_path)
        md = (tmp_path / "docs" / "GRADING_CLOSURE.md").read_text()
        assert "`engine/china_sector_cycles_grader.py`" in md
        assert "`scripts/grade_promises.py`" in md
        row = next(l for l in md.splitlines() if l.startswith("| `china_sector_cycles"))
        assert row.count("`") >= 6, f"both graders must be backticked separately: {row}"
        assert not re.search(r"`[^`]+,[^`]+`", row), (
            f"graders must not be rendered as one comma-joined path: {row}"
        )
