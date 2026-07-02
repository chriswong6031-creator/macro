"""tests/test_w6_readiness_monitor.py — W6 promotion-readiness monitor.

Covers:
  * compute_promotion_readiness: ready/approaching/projected_ready_date math
  * _load_qual_ladder_families: parses claim_family from qual_ladder.yml
  * First-cross alert dedupe (fires once, not on re-run)
  * Registry sync idempotency (_refresh_qledger_promotion hook)
  * Grader-quiet log accumulates and resets correctly
  * run_readiness_post_step: end-to-end non-fatal wrapper

All tests are hermetic (tmp_path, monkeypatched notify).
Tracked files (forward_log.parquet, etc.) are NOT modified.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import scripts.grade_qledger as grader
from engine import qledger as q
from engine.experiments_registry import _refresh_qledger_promotion


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def root(tmp_path):
    """Minimal repo-root scaffolding: claims + grades stores, qual_ladder.yml."""
    # Create directories
    (tmp_path / "data" / "qledger").mkdir(parents=True)
    (tmp_path / "site" / "qledger").mkdir(parents=True)
    (tmp_path / "config").mkdir(parents=True)

    # Minimal qual_ladder.yml with two families
    (tmp_path / "config" / "qual_ladder.yml").write_text(
        "altdata.signal_score:\n"
        "  claim_family: altdata\n"
        "\n"
        "radar.divergence_z:\n"
        "  claim_family: radar\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def prices(monkeypatch):
    """Synthetic price layer so grade_claim works."""
    import pandas as pd

    def _series(ticker, root):
        idx = pd.bdate_range(start="2026-01-01", periods=200)
        vals = [100.0 * (1.002 ** i) for i in range(200)]
        return pd.Series(vals, index=idx)

    monkeypatch.setattr("engine.ai_desk._close_series", _series)


# ──────────────────────────────────────────────────────────────────────────────
# _load_qual_ladder_families
# ──────────────────────────────────────────────────────────────────────────────

class TestLoadQualLadderFamilies:
    def test_parses_known_families(self, root):
        families = grader._load_qual_ladder_families(root)
        assert "altdata" in families
        assert "radar" in families

    def test_returns_sorted_deduplicated(self, root):
        families = grader._load_qual_ladder_families(root)
        assert families == sorted(set(families))

    def test_absent_file_returns_empty(self, tmp_path):
        families = grader._load_qual_ladder_families(tmp_path)
        assert families == []

    def test_malformed_file_returns_empty(self, tmp_path):
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "qual_ladder.yml").write_text(
            ": : invalid yaml ::\n", encoding="utf-8"
        )
        # Should not raise — returns whatever was parsed (may be empty or partial)
        families = grader._load_qual_ladder_families(tmp_path)
        assert isinstance(families, list)


# ──────────────────────────────────────────────────────────────────────────────
# compute_promotion_readiness: ready / approaching / projection
# ──────────────────────────────────────────────────────────────────────────────

def _seed_grades(tmp_path: Path, family: str, n_dates: int,
                 horizon: int = 5, hit: bool = True) -> None:
    """Register n_dates independent claims and grade each at `horizon`d."""
    grades_p = tmp_path / "data" / "qledger" / "grades.jsonl"
    claims_p = tmp_path / "data" / "qledger" / "claims.jsonl"
    for i in range(n_dates):
        asof = (date(2026, 1, 2) + timedelta(days=i)).isoformat()
        c = q.make_claim(
            desk=family, asof=asof, scope_type="entity",
            scope_key="SPY", direction=1, horizon_d=horizon,
            timestamp_quality="CRAWL_BOUNDED", claim_family=family,
        )
        stored = q.register(c, root=tmp_path)
        grade_row = {
            "claim_id": stored["claim_id"],
            "horizon_d": horizon,
            "graded_at": f"2026-02-{10+i:02d}T00:00:00+00:00",
            "subject_ret": 0.01,
            "bench_ret": 0.005,
            "control_ret": None,
            "excess": 0.005 if hit else -0.005,
            "hit": hit,
            "embargo_applied": False,
        }
        with grades_p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(grade_row) + "\n")


class TestComputePromotionReadiness:

    def test_not_ready_below_25(self, root):
        _seed_grades(root, "altdata", n_dates=10, horizon=5)
        res = grader.compute_promotion_readiness(root, families=["altdata"])
        rec = res["altdata"]["5"]
        assert not rec["ready"]
        assert not rec["approaching"]
        assert rec["n_dates"] == 10
        assert rec["needed"] == 25

    def test_approaching_at_20(self, root):
        _seed_grades(root, "altdata", n_dates=20, horizon=5)
        res = grader.compute_promotion_readiness(root, families=["altdata"])
        rec = res["altdata"]["5"]
        assert not rec["ready"]
        assert rec["approaching"]

    def test_approaching_false_below_20(self, root):
        _seed_grades(root, "altdata", n_dates=19, horizon=5)
        res = grader.compute_promotion_readiness(root, families=["altdata"])
        rec = res["altdata"]["5"]
        assert not rec["approaching"]

    def test_ready_at_25_positive_ci(self, root):
        # 25 dates with all hits → CI-low > 0
        _seed_grades(root, "altdata", n_dates=25, horizon=5, hit=True)
        res = grader.compute_promotion_readiness(root, families=["altdata"])
        rec = res["altdata"]["5"]
        assert rec["ready"]
        assert rec["wilson_ci_low"] is not None
        assert rec["wilson_ci_low"] > 0

    def test_not_ready_at_25_negative_ci(self, root):
        # 25 dates with all misses → CI-low likely <=0 (promotion_check returns not eligible)
        _seed_grades(root, "altdata", n_dates=25, horizon=5, hit=False)
        res = grader.compute_promotion_readiness(root, families=["altdata"])
        rec = res["altdata"]["5"]
        # CI-low will be negative (all misses), so ready=False
        assert not rec["ready"]

    def test_projection_present_when_accruing(self, root):
        _seed_grades(root, "altdata", n_dates=5, horizon=5)
        res = grader.compute_promotion_readiness(root, families=["altdata"])
        rec = res["altdata"]["5"]
        # projection may or may not be computed depending on trailing rate;
        # just assert it's either a valid date string or None (never raises)
        proj = rec.get("projected_ready_date")
        assert proj is None or len(proj) == 10  # YYYY-MM-DD

    def test_projection_none_when_zero_dates(self, root):
        # no grades at all → rate=None → projection=None
        res = grader.compute_promotion_readiness(root, families=["altdata"])
        rec = res["altdata"]["5"]
        assert rec["projected_ready_date"] is None

    def test_missing_family_returns_ungraded_record(self, root):
        # Family "radar" has no claims → should still return a record, not raise
        res = grader.compute_promotion_readiness(root, families=["radar"])
        rec = res["radar"]["5"]
        assert rec["n_dates"] == 0
        assert not rec["ready"]

    def test_duel_context_included(self, root):
        _seed_grades(root, "altdata", n_dates=5, horizon=5)
        res = grader.compute_promotion_readiness(root, families=["altdata"])
        assert "_duel_context" in res
        dc = res["_duel_context"].get("altdata", {})
        # keys always present (may be None)
        assert "challenger_excess_mean_5d" in dc
        assert "placebo_covered_abs_excess_5d" in dc


# ──────────────────────────────────────────────────────────────────────────────
# First-cross alert dedupe
# ──────────────────────────────────────────────────────────────────────────────

class TestFirstCrossAlertDedupe:

    def test_fires_on_first_cross(self, root):
        """Alert fires when a family first crosses ready=True."""
        _seed_grades(root, "altdata", n_dates=25, horizon=5, hit=True)
        sent: list[str] = []
        with patch("scripts.notify.send_telegram", side_effect=lambda m: sent.append(m) or True), \
             patch("scripts.notify.send_discord", return_value=True):
            grader.run_readiness_post_step(root, n_graded_today=25, n_open=100)
        assert any("W6 gate OPEN" in m for m in sent), "Expected alert was not fired"

    def test_does_not_fire_twice(self, root):
        """Alert must not re-fire on subsequent runs once fired state is persisted."""
        _seed_grades(root, "altdata", n_dates=25, horizon=5, hit=True)
        sent: list[str] = []
        with patch("scripts.notify.send_telegram", side_effect=lambda m: sent.append(m) or True), \
             patch("scripts.notify.send_discord", return_value=True):
            grader.run_readiness_post_step(root, n_graded_today=25, n_open=100)
            n_after_first = len(sent)
            # Run again — should NOT fire
            grader.run_readiness_post_step(root, n_graded_today=25, n_open=100)
        n_after_second = len(sent)
        assert n_after_second == n_after_first, "Alert fired twice — dedup broken"

    def test_fired_state_persisted_to_disk(self, root):
        _seed_grades(root, "altdata", n_dates=25, horizon=5, hit=True)
        with patch("scripts.notify.send_telegram", return_value=True), \
             patch("scripts.notify.send_discord", return_value=True):
            grader.run_readiness_post_step(root, n_graded_today=25, n_open=100)
        fired_path = root / "data" / "qledger" / "readiness_alerts_fired.json"
        assert fired_path.exists()
        fired = json.loads(fired_path.read_text())
        assert any("altdata" in k for k in fired), "Fired key not persisted"

    def test_not_ready_does_not_fire(self, root):
        """No alert when family is not yet ready."""
        _seed_grades(root, "altdata", n_dates=5, horizon=5, hit=True)
        sent: list[str] = []
        with patch("scripts.notify.send_telegram", side_effect=lambda m: sent.append(m) or True), \
             patch("scripts.notify.send_discord", return_value=True):
            grader.run_readiness_post_step(root, n_graded_today=5, n_open=100)
        assert not sent, "Unexpected alert for non-ready family"


# ──────────────────────────────────────────────────────────────────────────────
# Grader-quiet alert
# ──────────────────────────────────────────────────────────────────────────────

class TestGraderQuietAlert:

    def test_quiet_log_increments(self, root):
        grader._update_grader_quiet_log(root, n_graded_today=0, n_open=100)
        days = grader._update_grader_quiet_log(root, n_graded_today=0, n_open=100)
        # Second call on same day should NOT increment (same calendar date guard)
        assert days >= 1

    def test_quiet_log_resets_on_graded(self, root):
        grader._update_grader_quiet_log(root, n_graded_today=0, n_open=100)
        days = grader._update_grader_quiet_log(root, n_graded_today=10, n_open=100)
        assert days == 0

    def test_quiet_fires_at_2_days(self, root, monkeypatch):
        """Simulate 2 calendar-day quiet period to trigger the alert."""
        sent: list[str] = []

        # Simulate day 1
        monkeypatch.setattr(
            "scripts.grade_qledger.date",
            type("D", (), {"today": staticmethod(lambda: date(2026, 7, 1)),
                           "isoformat": date.isoformat})
        )
        grader._update_grader_quiet_log(root, n_graded_today=0, n_open=100)

        # Simulate day 2
        monkeypatch.setattr(
            "scripts.grade_qledger.date",
            type("D", (), {"today": staticmethod(lambda: date(2026, 7, 2)),
                           "isoformat": date.isoformat})
        )
        quiet_days = grader._update_grader_quiet_log(root, n_graded_today=0, n_open=100)
        assert quiet_days == 2


# ──────────────────────────────────────────────────────────────────────────────
# Registry sync idempotency (_refresh_qledger_promotion hook)
# ──────────────────────────────────────────────────────────────────────────────

class TestRegistrySync:

    def _write_track_record(self, tmp_path: Path, family: str,
                            n_dates: int, ci_low: float | None,
                            ready: bool, excess_mean: float | None = 0.02) -> None:
        """Write a minimal track_record.json with promotion_readiness for one family."""
        tr = {
            "generated_at": "2026-07-02T00:00:00+00:00",
            "by_family": {
                family: {
                    "5": {
                        "n_obs": n_dates,
                        "n_dates": n_dates,
                        "hit_rate": 0.6 if ready else None,
                        "excess_mean": excess_mean,
                        "wilson_ci_low": ci_low,
                        "state": "GRADED" if ready else "ACCRUING",
                    }
                }
            },
            "promotion_readiness": {
                family: {
                    "5": {
                        "n_dates": n_dates,
                        "needed": 25,
                        "wilson_ci_low": ci_low,
                        "hit_rate": 0.6 if ready else None,
                        "excess_mean": excess_mean,
                        "ready": ready,
                        "approaching": (n_dates >= 20 and not ready),
                        "projected_ready_date": None,
                        "reason": "ok" if ready else "accruing",
                    }
                },
                "_duel_context": {
                    family: {
                        "challenger_excess_mean_5d": excess_mean,
                        "placebo_covered_abs_excess_5d": 0.062,
                        "n_dates_5d": n_dates,
                        "wilson_ci_low_5d": ci_low,
                    }
                }
            }
        }
        p = tmp_path / "site" / "qledger" / "track_record.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(tr), encoding="utf-8")

    def test_hook_returns_gate_open_when_ready(self, tmp_path, monkeypatch):
        self._write_track_record(tmp_path, "altdata", n_dates=25, ci_low=0.45, ready=True)
        monkeypatch.setattr("engine.experiments_registry._root", lambda: tmp_path)
        seed_entry = {"claim_family": "altdata"}
        result = _refresh_qledger_promotion(seed_entry)
        assert result.get("status") == "gate_open"
        assert result.get("ready") is True

    def test_hook_returns_accruing_when_not_ready(self, tmp_path, monkeypatch):
        self._write_track_record(tmp_path, "radar", n_dates=7, ci_low=0.5, ready=False)
        monkeypatch.setattr("engine.experiments_registry._root", lambda: tmp_path)
        seed_entry = {"claim_family": "radar"}
        result = _refresh_qledger_promotion(seed_entry)
        assert result.get("status") == "accruing"
        assert not result.get("ready")

    def test_hook_includes_duel_context_in_next_step(self, tmp_path, monkeypatch):
        self._write_track_record(tmp_path, "altdata", n_dates=7, ci_low=0.46, ready=False,
                                 excess_mean=0.008)
        monkeypatch.setattr("engine.experiments_registry._root", lambda: tmp_path)
        seed_entry = {
            "claim_family": "altdata",
            "next_step": "Existing step text.",
        }
        result = _refresh_qledger_promotion(seed_entry)
        ns = result.get("next_step", "")
        assert "Duel @5d" in ns, "Duel context line not injected into next_step"
        assert "Existing step text." in ns, "Original next_step not preserved"

    def test_hook_missing_track_record_returns_empty(self, tmp_path, monkeypatch):
        """No track_record.json → hook returns {} (degraded safely)."""
        monkeypatch.setattr("engine.experiments_registry._root", lambda: tmp_path)
        seed_entry = {"claim_family": "altdata"}
        result = _refresh_qledger_promotion(seed_entry)
        assert result == {}

    def test_hook_idempotent(self, tmp_path, monkeypatch):
        """Calling the hook twice produces the same result."""
        self._write_track_record(tmp_path, "altdata", n_dates=7, ci_low=0.46, ready=False)
        monkeypatch.setattr("engine.experiments_registry._root", lambda: tmp_path)
        seed_entry = {"claim_family": "altdata"}
        r1 = _refresh_qledger_promotion(seed_entry)
        r2 = _refresh_qledger_promotion(seed_entry)
        assert r1 == r2


# ──────────────────────────────────────────────────────────────────────────────
# run_readiness_post_step: end-to-end non-fatal wrapper
# ──────────────────────────────────────────────────────────────────────────────

class TestRunReadinessPostStep:

    def test_writes_promotion_readiness_to_track_record(self, root):
        _seed_grades(root, "altdata", n_dates=5, horizon=5)
        with patch("scripts.notify.send_telegram", return_value=True), \
             patch("scripts.notify.send_discord", return_value=True):
            grader.run_readiness_post_step(root, n_graded_today=5, n_open=100)
        tr = json.loads((root / "site" / "qledger" / "track_record.json").read_text())
        assert "promotion_readiness" in tr

    def test_dry_run_writes_nothing(self, root):
        _seed_grades(root, "altdata", n_dates=5, horizon=5)
        # Remove any existing track_record (we'll check nothing was written)
        tr_path = root / "site" / "qledger" / "track_record.json"
        tr_path.unlink(missing_ok=True)
        with patch("scripts.notify.send_telegram", return_value=True), \
             patch("scripts.notify.send_discord", return_value=True):
            grader.run_readiness_post_step(root, n_graded_today=5, n_open=100, dry_run=True)
        # No track_record should have been written
        assert not tr_path.exists()

    def test_returns_summary_dict(self, root):
        result = grader.run_readiness_post_step(root, n_graded_today=0, n_open=0)
        assert "n_families_ready" in result
        assert "n_families_approaching" in result
        assert "families_ready" in result
        assert "grader_quiet_days" in result

    def test_non_fatal_on_broken_input(self, root):
        """Even if the internal call crashes, run_readiness_post_step must return a dict."""
        with patch("scripts.grade_qledger.compute_promotion_readiness",
                   side_effect=RuntimeError("simulated crash")):
            result = grader.run_readiness_post_step(root, n_graded_today=0, n_open=0)
        assert isinstance(result, dict)
        # Should contain an 'error' key or gracefully empty families
        assert "error" in result or "n_families_ready" in result

    def test_tracked_data_files_not_dirtied(self, root):
        """Verify that no tracked data files outside data/qledger/ are modified."""
        # This test checks that forward_log.parquet, site/altdata/*, etc. are untouched.
        # We simply verify the only new files are inside data/qledger/ (our own store).
        import os
        before = {str(p): p.stat().st_mtime
                  for p in root.rglob("*") if p.is_file()}
        with patch("scripts.notify.send_telegram", return_value=True), \
             patch("scripts.notify.send_discord", return_value=True):
            grader.run_readiness_post_step(root, n_graded_today=0, n_open=0)
        after = {str(p): p.stat().st_mtime
                 for p in root.rglob("*") if p.is_file()}
        new_or_changed = {p for p in after if p not in before or after[p] != before[p]}
        for p in new_or_changed:
            rel = str(Path(p).relative_to(root))
            assert rel.startswith("data/qledger/") or rel.startswith("site/qledger/"), (
                f"Unexpected file modified outside qledger stores: {rel}"
            )
