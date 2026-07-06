"""tests/test_build_operator_exposure_log.py — W-EX operator exposure log tests.

NEXT3 §5.2 / RUL-U6.  All fixtures are synthetic (tmp_path only).
No real data files are read.

Coverage:
  - missing-artifact handling: each surface returns 0 rows gracefully
  - alert-null rr_banner: file present with {"alert": null} → 0 rows (by design)
  - asof-spelling: rr_banner uses "asof" (no underscore) for the date field
  - dedup: same (surface, surface_id, as_of) not appended twice
  - 90-day bounding in summary: rows older than 90 days excluded from counts
  - unknown-lane counting: unexpected lane in standouts is counted, never dropped
  - experiment come_back_due: come_back_on <= as_of → exposure_kind = come_back_due
  - experiment standing: come_back_on > as_of → exposure_kind = standing/new
  - new-row detection: first appearance of a (surface, surface_id, as_of) → "new"
  - run_as_collect_step: never raises even when artifacts are all missing
  - summary schema: required keys present, generated_at is ISO
  - no "validated" string anywhere in output rows or summary
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

import scripts.build_operator_exposure_log as boel


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def _make_root(tmp_path: Path) -> Path:
    """Return a synthetic repo root with required directory structure."""
    (tmp_path / "site" / "marketdata").mkdir(parents=True)
    (tmp_path / "site" / "factordata").mkdir(parents=True)
    (tmp_path / "site").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "governance").mkdir(parents=True)
    (tmp_path / "data" / "operator").mkdir(parents=True)
    return tmp_path


def _write_experiments(root: Path, as_of: str, experiments: list[dict]) -> None:
    _write_json(
        root / "site" / "marketdata" / "experiments.json",
        {"schema": "experiments_registry.v1", "as_of": as_of, "experiments": experiments},
    )


def _write_standouts(root: Path, as_of: str, buy: list[dict], watch: list[dict]) -> None:
    _write_json(
        root / "site" / "factordata" / "us_standouts.json",
        {"as_of": as_of, "buy": buy, "watch": watch, "lane_counts": {}},
    )


def _write_wh_banner(root: Path, alerts: list[dict]) -> None:
    _write_json(
        root / "site" / "wh_banner.json",
        {"schema": "wh_banner.v1", "alerts": alerts},
    )


def _write_rr_banner(root: Path, asof: str, alert: dict | None) -> None:
    _write_json(
        root / "site" / "rr_banner.json",
        {"schema": "rr_banner.v1", "asof": asof, "alert": alert},
    )


def _load_log(root: Path) -> list[dict]:
    p = root / "data" / "operator" / "exposure_log.jsonl"
    return boel._load_jsonl(p)


def _load_summary(root: Path) -> dict:
    p = root / "data" / "governance" / "operator_exposure_summary.json"
    return json.loads(p.read_text())


# ---------------------------------------------------------------------------
# Test: missing artifacts
# ---------------------------------------------------------------------------

class TestMissingArtifacts:
    """Each surface missing → 0 rows, no crash, summary still written."""

    def test_all_missing(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        # Write only rr_banner so the run doesn't need a date fallback
        _write_rr_banner(root, "2026-07-01", None)
        result = boel.run(root=root)
        assert result["n_new_rows"] == 0
        assert result["n_unknown_lanes"] == 0
        summary = _load_summary(root)
        assert summary["n_rows_in_window"] == 0

    def test_experiments_missing(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        _write_standouts(root, "2026-07-01", [], [])
        _write_wh_banner(root, [])
        _write_rr_banner(root, "2026-07-01", None)
        result = boel.run(root=root)
        assert result["n_new_rows"] == 0

    def test_standouts_missing(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        _write_experiments(root, "2026-07-01", [])
        _write_wh_banner(root, [])
        _write_rr_banner(root, "2026-07-01", None)
        result = boel.run(root=root)
        assert result["n_new_rows"] == 0

    def test_wh_banner_missing(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        _write_experiments(root, "2026-07-01", [])
        _write_standouts(root, "2026-07-01", [], [])
        _write_rr_banner(root, "2026-07-01", None)
        result = boel.run(root=root)
        assert result["n_new_rows"] == 0

    def test_rr_banner_missing(self, tmp_path: Path) -> None:
        """rr_banner is always present in production; missing is an anomaly but must not crash."""
        root = _make_root(tmp_path)
        _write_experiments(root, "2026-07-01", [])
        _write_standouts(root, "2026-07-01", [], [])
        _write_wh_banner(root, [])
        # deliberately omit rr_banner
        result = boel.run(root=root)
        assert result["n_new_rows"] == 0


# ---------------------------------------------------------------------------
# Test: rr_banner — alert null vs active
# ---------------------------------------------------------------------------

class TestRrBanner:
    def test_alert_null_emits_zero_rows(self, tmp_path: Path) -> None:
        """rr_banner with {"alert": null} → 0 rows (exposure signal = alert != null)."""
        root = _make_root(tmp_path)
        _write_rr_banner(root, "2026-07-02", None)
        _write_wh_banner(root, [])
        _write_experiments(root, "2026-07-02", [])
        _write_standouts(root, "2026-07-02", [], [])
        result = boel.run(root=root)
        rows = _load_log(root)
        rr_rows = [r for r in rows if r["surface"] == "alert_rr"]
        assert len(rr_rows) == 0
        assert result["n_new_rows"] == 0

    def test_active_alert_emits_one_row(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        _write_rr_banner(root, "2026-07-02", {"id": "rr-extreme-2026-07-02", "level": "extreme"})
        _write_wh_banner(root, [])
        _write_experiments(root, "2026-07-02", [])
        _write_standouts(root, "2026-07-02", [], [])
        boel.run(root=root)
        rows = _load_log(root)
        rr_rows = [r for r in rows if r["surface"] == "alert_rr"]
        assert len(rr_rows) == 1
        r = rr_rows[0]
        assert r["surface_id"] == "rr-extreme-2026-07-02"
        assert r["as_of"] == "2026-07-02"
        assert r["schema"] == "operator_exposure.v1"


# ---------------------------------------------------------------------------
# Test: asof spelling
# ---------------------------------------------------------------------------

class TestAsofSpelling:
    def test_rr_banner_uses_asof_no_underscore(self, tmp_path: Path) -> None:
        """rr_banner date field is 'asof', not 'as_of'."""
        root = _make_root(tmp_path)
        # Write a banner that uses the correct 'asof' spelling
        rr_data = {"schema": "rr_banner.v1", "asof": "2026-07-05", "alert": {"id": "rr-test-1"}}
        _write_json(root / "site" / "rr_banner.json", rr_data)
        _write_wh_banner(root, [])
        _write_experiments(root, "2026-07-05", [])
        _write_standouts(root, "2026-07-05", [], [])
        boel.run(root=root)
        rows = _load_log(root)
        rr_rows = [r for r in rows if r["surface"] == "alert_rr"]
        assert len(rr_rows) == 1
        assert rr_rows[0]["as_of"] == "2026-07-05"

    def test_rr_banner_missing_asof_field_skips_row(self, tmp_path: Path) -> None:
        """If 'asof' is missing but alert != null, emit 0 rows (not a crash)."""
        root = _make_root(tmp_path)
        # Note: wrong spelling 'as_of' — reader must handle this gracefully
        rr_data = {"schema": "rr_banner.v1", "as_of": "2026-07-05", "alert": {"id": "rr-bad"}}
        _write_json(root / "site" / "rr_banner.json", rr_data)
        _write_wh_banner(root, [])
        _write_experiments(root, "2026-07-05", [])
        _write_standouts(root, "2026-07-05", [], [])
        result = boel.run(root=root)
        rows = _load_log(root)
        rr_rows = [r for r in rows if r["surface"] == "alert_rr"]
        # 'asof' not found → 0 rows (warning emitted but no crash)
        assert len(rr_rows) == 0


# ---------------------------------------------------------------------------
# Test: dedup
# ---------------------------------------------------------------------------

class TestDedup:
    def test_same_triplet_not_appended_twice(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        exp = [{"id": "my-exp", "name": "x", "come_back_on": "2027-01-01"}]
        _write_experiments(root, "2026-07-01", exp)
        _write_standouts(root, "2026-07-01", [], [])
        _write_wh_banner(root, [])
        _write_rr_banner(root, "2026-07-01", None)

        boel.run(root=root)
        rows_after_first = _load_log(root)

        boel.run(root=root)
        rows_after_second = _load_log(root)

        # The log must have the same row count after both runs
        assert len(rows_after_second) == len(rows_after_first)

    def test_different_as_of_appends_again(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)

        # Day 1
        _write_experiments(root, "2026-07-01", [{"id": "my-exp", "come_back_on": "2027-01-01"}])
        _write_standouts(root, "2026-07-01", [], [])
        _write_wh_banner(root, [])
        _write_rr_banner(root, "2026-07-01", None)
        boel.run(root=root)
        rows_day1 = _load_log(root)

        # Day 2 — same experiment, different as_of
        _write_experiments(root, "2026-07-02", [{"id": "my-exp", "come_back_on": "2027-01-01"}])
        _write_standouts(root, "2026-07-02", [], [])
        _write_rr_banner(root, "2026-07-02", None)
        boel.run(root=root)
        rows_day2 = _load_log(root)

        # Day 2 adds a new row (different as_of → different dedup key)
        assert len(rows_day2) == len(rows_day1) + 1


# ---------------------------------------------------------------------------
# Test: 90-day bounding
# ---------------------------------------------------------------------------

class TestSummaryBounding:
    def test_old_rows_excluded_from_summary(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)

        # Seed the log with a very old row (200 days ago)
        old_date = (date.today() - timedelta(days=200)).isoformat()
        recent_date = (date.today() - timedelta(days=5)).isoformat()

        old_row = {
            "schema": "operator_exposure.v1",
            "ts_logged": "2025-01-01T00:00:00+00:00",
            "as_of": old_date,
            "surface": "experiment",
            "surface_id": "old-exp",
            "artifact": "site/marketdata/experiments.json",
            "exposure_kind": "standing",
        }
        _write_jsonl(root / "data" / "operator" / "exposure_log.jsonl", [old_row])

        # Fresh run with a recent artifact
        _write_experiments(root, recent_date, [{"id": "new-exp", "come_back_on": "2027-01-01"}])
        _write_standouts(root, recent_date, [], [])
        _write_wh_banner(root, [])
        _write_rr_banner(root, recent_date, None)
        boel.run(root=root)

        summary = _load_summary(root)
        # The old row should not appear in the 90-day window
        days_in_summary = {entry["as_of"] for entry in summary["by_day"]}
        assert old_date not in days_in_summary

    def test_recent_rows_included(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        recent_date = (date.today() - timedelta(days=5)).isoformat()
        _write_experiments(root, recent_date, [{"id": "exp-A", "come_back_on": "2027-01-01"}])
        _write_standouts(root, recent_date, [], [])
        _write_wh_banner(root, [])
        _write_rr_banner(root, recent_date, None)
        boel.run(root=root)

        summary = _load_summary(root)
        assert summary["n_rows_in_window"] >= 1
        days = {entry["as_of"] for entry in summary["by_day"]}
        assert recent_date in days


# ---------------------------------------------------------------------------
# Test: unknown lane counting
# ---------------------------------------------------------------------------

class TestUnknownLane:
    def test_unknown_lane_counted_not_dropped(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        as_of = "2026-07-01"
        _write_experiments(root, as_of, [])
        # Put a ticker with an unknown lane in the buy list
        _write_standouts(root, as_of, [
            {"ticker": "XYZ", "lane": "mystery_lane"},
        ], [])
        _write_wh_banner(root, [])
        _write_rr_banner(root, as_of, None)

        result = boel.run(root=root)
        assert result["n_unknown_lanes"] >= 1
        # The row must still be in the log (not dropped)
        rows = _load_log(root)
        xyz_rows = [r for r in rows if "XYZ" in r.get("surface_id", "") or
                    r.get("surface", "").startswith("board_")]
        assert len(xyz_rows) >= 1

    def test_known_lanes_not_counted_as_unknown(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        as_of = "2026-07-01"
        _write_experiments(root, as_of, [])
        _write_standouts(root, as_of, [
            {"ticker": "AAPL", "lane": "continuation"},
            {"ticker": "GNL", "lane": "bottoming"},
        ], [
            {"ticker": "WMT", "lane": "watch"},
        ])
        _write_wh_banner(root, [])
        _write_rr_banner(root, as_of, None)
        result = boel.run(root=root)
        assert result["n_unknown_lanes"] == 0

    def test_known_lane_surfaces(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        as_of = "2026-07-01"
        _write_experiments(root, as_of, [])
        _write_standouts(root, as_of, [
            {"ticker": "AAPL", "lane": "continuation"},
            {"ticker": "GNL", "lane": "bottoming"},
        ], [
            {"ticker": "WMT", "lane": "watch"},
        ])
        _write_wh_banner(root, [])
        _write_rr_banner(root, as_of, None)
        boel.run(root=root)
        rows = _load_log(root)
        board_rows = [r for r in rows if r["surface"].startswith("board_")]
        surfaces = {r["surface"] for r in board_rows}
        assert "board_buy" in surfaces
        assert "board_watch" in surfaces


# ---------------------------------------------------------------------------
# Test: exposure_kind for experiments
# ---------------------------------------------------------------------------

class TestExposureKind:
    def test_come_back_due(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        as_of = "2026-07-06"
        # come_back_on is today or in the past → come_back_due
        _write_experiments(root, as_of, [{"id": "exp-overdue", "come_back_on": "2026-07-06"}])
        _write_standouts(root, as_of, [], [])
        _write_wh_banner(root, [])
        _write_rr_banner(root, as_of, None)
        boel.run(root=root)
        rows = _load_log(root)
        exp_rows = [r for r in rows if r["surface"] == "experiment"]
        assert len(exp_rows) == 1
        assert exp_rows[0]["exposure_kind"] == "come_back_due"

    def test_standing_experiment(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        as_of = "2026-07-06"
        # come_back_on is in the future → standing or new (depends on first appearance)
        _write_experiments(root, as_of, [{"id": "exp-future", "come_back_on": "2027-01-01"}])
        _write_standouts(root, as_of, [], [])
        _write_wh_banner(root, [])
        _write_rr_banner(root, as_of, None)
        boel.run(root=root)
        rows = _load_log(root)
        exp_rows = [r for r in rows if r["surface"] == "experiment"]
        assert len(exp_rows) == 1
        # First appearance → "new"
        assert exp_rows[0]["exposure_kind"] == "new"

    def test_come_back_due_not_downgraded_on_second_run(self, tmp_path: Path) -> None:
        """A come_back_due row that was already written must not be re-appended."""
        root = _make_root(tmp_path)
        as_of = "2026-07-06"
        _write_experiments(root, as_of, [{"id": "exp-due", "come_back_on": "2026-07-06"}])
        _write_standouts(root, as_of, [], [])
        _write_wh_banner(root, [])
        _write_rr_banner(root, as_of, None)
        boel.run(root=root)
        boel.run(root=root)
        rows = _load_log(root)
        exp_rows = [r for r in rows if r["surface"] == "experiment"]
        assert len(exp_rows) == 1  # deduped; not appended twice


# ---------------------------------------------------------------------------
# Test: run_as_collect_step never raises
# ---------------------------------------------------------------------------

class TestRunAsCollectStep:
    def test_never_raises_on_missing_everything(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        # run_as_collect_step uses default root (repo parent) which won't exist
        # — it must not raise
        boel.run_as_collect_step()  # should not raise

    def test_never_raises_on_broken_json(self, tmp_path: Path, monkeypatch) -> None:
        root = _make_root(tmp_path)
        # Write a broken JSON file
        (root / "site" / "marketdata" / "experiments.json").write_text("not json")
        _write_standouts(root, "2026-07-01", [], [])
        _write_wh_banner(root, [])
        _write_rr_banner(root, "2026-07-01", None)

        # Monkeypatch the default root resolution
        import unittest.mock as mock
        with mock.patch("scripts.build_operator_exposure_log.run", side_effect=RuntimeError("boom")):
            boel.run_as_collect_step()  # must not raise even with a crash


# ---------------------------------------------------------------------------
# Test: summary schema
# ---------------------------------------------------------------------------

class TestSummarySchema:
    def test_required_keys_present(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        _write_experiments(root, "2026-07-01", [])
        _write_standouts(root, "2026-07-01", [], [])
        _write_wh_banner(root, [])
        _write_rr_banner(root, "2026-07-01", None)
        boel.run(root=root)
        summary = _load_summary(root)
        for key in ("schema", "generated_at", "window_days", "n_rows_in_window", "by_day"):
            assert key in summary, f"Missing key: {key}"
        assert summary["schema"] == "operator_exposure_summary.v1"
        assert summary["window_days"] == 90

    def test_generated_at_is_iso(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        _write_experiments(root, "2026-07-01", [])
        _write_standouts(root, "2026-07-01", [], [])
        _write_wh_banner(root, [])
        _write_rr_banner(root, "2026-07-01", None)
        boel.run(root=root)
        summary = _load_summary(root)
        gen = summary["generated_at"]
        from datetime import datetime, timezone
        # Should parse without error
        datetime.fromisoformat(gen)


# ---------------------------------------------------------------------------
# Test: no "validated" string in outputs
# ---------------------------------------------------------------------------

class TestNoValidatedString:
    def test_no_validated_in_rows(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        _write_experiments(root, "2026-07-01", [{"id": "exp-a", "come_back_on": "2027-01-01"}])
        _write_standouts(root, "2026-07-01", [{"ticker": "AAPL", "lane": "continuation"}], [])
        _write_wh_banner(root, [{"id": "wh-1", "published_at": "2026-07-01T12:00:00+00:00"}])
        _write_rr_banner(root, "2026-07-01", {"id": "rr-1"})
        boel.run(root=root)
        rows = _load_log(root)
        for row in rows:
            row_str = json.dumps(row)
            assert "validated" not in row_str.lower(), (
                f"'validated' found in row: {row_str}"
            )

    def test_no_validated_in_summary(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        _write_experiments(root, "2026-07-01", [])
        _write_standouts(root, "2026-07-01", [], [])
        _write_wh_banner(root, [])
        _write_rr_banner(root, "2026-07-01", None)
        boel.run(root=root)
        summary_text = (root / "data" / "governance" / "operator_exposure_summary.json").read_text()
        assert "validated" not in summary_text.lower()


# ---------------------------------------------------------------------------
# Test: surface_id for board rows is sha1[:12]
# ---------------------------------------------------------------------------

class TestSurfaceIdFormat:
    def test_board_surface_id_is_sha1_12(self, tmp_path: Path) -> None:
        import hashlib
        root = _make_root(tmp_path)
        as_of = "2026-07-01"
        _write_experiments(root, as_of, [])
        _write_standouts(root, as_of, [{"ticker": "AAPL", "lane": "continuation"}], [])
        _write_wh_banner(root, [])
        _write_rr_banner(root, as_of, None)
        boel.run(root=root)
        rows = _load_log(root)
        board_rows = [r for r in rows if r["surface"] == "board_buy"]
        assert len(board_rows) == 1
        expected_id = hashlib.sha1(f"{as_of}|continuation|AAPL".encode()).hexdigest()[:12]
        assert board_rows[0]["surface_id"] == expected_id

    def test_experiment_surface_id_is_verbatim(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        _write_experiments(root, "2026-07-01", [{"id": "my-special-exp", "come_back_on": "2027-01-01"}])
        _write_standouts(root, "2026-07-01", [], [])
        _write_wh_banner(root, [])
        _write_rr_banner(root, "2026-07-01", None)
        boel.run(root=root)
        rows = _load_log(root)
        exp_rows = [r for r in rows if r["surface"] == "experiment"]
        assert len(exp_rows) == 1
        assert exp_rows[0]["surface_id"] == "my-special-exp"


# ---------------------------------------------------------------------------
# Test: wh_banner alert id verbatim
# ---------------------------------------------------------------------------

class TestWhBanner:
    def test_alert_id_verbatim(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        alert_id = "wh-2026-07-01-some-event"
        _write_experiments(root, "2026-07-01", [])
        _write_standouts(root, "2026-07-01", [], [])
        _write_wh_banner(root, [{
            "id": alert_id,
            "published_at": "2026-07-01T10:00:00+00:00",
        }])
        _write_rr_banner(root, "2026-07-01", None)
        boel.run(root=root)
        rows = _load_log(root)
        wh_rows = [r for r in rows if r["surface"] == "alert_wh"]
        assert len(wh_rows) == 1
        assert wh_rows[0]["surface_id"] == alert_id

    def test_published_at_used_as_as_of(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path)
        _write_experiments(root, "2026-07-05", [])
        _write_standouts(root, "2026-07-05", [], [])
        _write_wh_banner(root, [{
            "id": "wh-test",
            "published_at": "2026-06-30T15:12:06+00:00",
        }])
        _write_rr_banner(root, "2026-07-05", None)
        boel.run(root=root)
        rows = _load_log(root)
        wh_rows = [r for r in rows if r["surface"] == "alert_wh"]
        assert len(wh_rows) == 1
        assert wh_rows[0]["as_of"] == "2026-06-30"
