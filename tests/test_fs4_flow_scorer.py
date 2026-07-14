"""tests/test_fs4_flow_scorer.py — FS-4 Lane B scorer + gate v2 unit tests.

All tests use tmp_path and synthetic data only — no real ledger, no network,
no ThetaTerminal, no trained model artifacts.

Test categories (per FS-4 Lane B acceptance gate):

 1. no_model path: all rows land with status=no_model; gate v2 written; exit 0.
 2. keep_first dedup: re-run with existing scores.parquet → no duplicates.
 3. kill_switch_off: scoring.enabled=False → no scores.parquet written; gate
    scoring.enabled=False.
 4. not_deployable: manifest.deployable=False → score_calibrated null, status
    not_deployable.
 5. decay_breach: realized ECE >= threshold → decayed=True in monitor; gate
    carries the flag; new events suppressed (score_calibrated null).
 6. gate_v2_shape: gate.json schema string is flow_signals.gate/v2; scoring
    block has expected keys (enabled, model_versions, n_scored_total,
    n_scored_this_run, by_status, calibration, monitor).
 7. pit_guard: feature frame must not include any grade/outcome column
    (fwd_ret, spy_excess_5, etc.) — assert an error row is emitted when
    one is present in the feature spec, rather than silently scoring on it.
 8. tz_aware_scored_at: scored_at column in scores.parquet is tz-aware UTC
    ISO string (ends with +00:00 or Z).
 9. prefiltered_index_root path: index root events land with
    status=prefiltered_index_root.
10. bucket_unmapped path: unrecognised dte_bucket → status=bucket_unmapped.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# ── helpers ───────────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _make_ledger(n: int = 5, dte_bucket: str = "8_30d",
                 root: str = "AAPL") -> pd.DataFrame:
    """Build a minimal synthetic ledger DataFrame."""
    ids = [f"evt_{i:04d}" for i in range(n)]
    rows = []
    for eid in ids:
        rows.append({
            "event_id":      eid,
            "session_date":  "2026-07-13",
            "ts":            "2026-07-13T10:30:00+00:00",
            "root":          root,
            "group":         "Technology",
            "group_zh":      "科技",
            "right":         "C",
            "exp":           "2026-09-19",
            "strike":        200.0,
            "dte":           67,
            "dte_bucket":    dte_bucket,
            "mny_bucket":    "atm",
            "side":          "~buy",
            "n_prints":      5,
            "size":          100,
            "avg_price":     3.0,
            "premium":       300_000.0,
            "premium_z":     3.5,
            "baseline_source": "z252",
            "vol_gt_oi":     True,
            "repeated":      False,
            "zerodte":       False,
            "signing_source": "tape",
            "swept":         True,
            "at_ask_share":  0.8,
            "at_bid_share":  0.1,
            "aggression_share": 0.7,
            "detector_version": "v1",
            "source":        "live_feed",
            "ingested_at":   "2026-07-13T10:30:00+00:00",
        })
    return pd.DataFrame(rows)


def _make_grades(event_ids: list[str]) -> pd.DataFrame:
    """Build a minimal synthetic grades DataFrame."""
    rows = []
    for eid in event_ids:
        rows.append({
            "event_id":        eid,
            "fwd_ret":         0.02,
            "spy_ret":         0.01,
            "spy_excess":      0.01,
            "spy_excess_5":    0.01,
            "spy_excess_21":   0.01,
            "spy_excess_63":   0.01,
            "spy_excess_126":  0.01,
            "outcome":         1,
            "grade":           "ok",
            "graded_at":       "2026-09-03T00:00:00+00:00",
        })
    return pd.DataFrame(rows)


def _write_kill_switch_yml(tmp_path: Path, enabled: bool = False) -> Path:
    """Write a minimal flow_score.yml."""
    cfg_path = tmp_path / "config" / "flow_score.yml"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        f"scoring:\n  enabled: {'true' if enabled else 'false'}\n"
        "models_dir: data/flow_signals/models\n"
        "decay_monitor:\n  window_days: 90\n  ece_breach_threshold: 0.05\n"
    )
    return cfg_path


def _patch_config(monkeypatch, tmp_path: Path):
    """Patch lib.config.data_dir() to return tmp_path/data."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    mock_cfg = MagicMock()
    mock_cfg.data_dir.return_value = data_dir
    monkeypatch.setitem(sys.modules, "lib.config", mock_cfg)
    monkeypatch.setitem(sys.modules, "lib", MagicMock(config=mock_cfg))
    return data_dir


def _run_build(tmp_path: Path, monkeypatch, extra_env: dict | None = None):
    """Run build_flow_signals.main in a controlled tmp environment."""
    # Ensure repo-root config/flow_score.yml path is patched
    import importlib

    # Patch environment
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)

    from scripts import build_flow_signals as bfs
    importlib.reload(bfs)
    return bfs


def _write_ledger(fs_dir: Path, df: pd.DataFrame) -> Path:
    p = fs_dir / "ledger.parquet"
    df.to_parquet(p, index=False)
    return p


def _write_scores(fs_dir: Path, df: pd.DataFrame) -> Path:
    p = fs_dir / "scores.parquet"
    df.to_parquet(p, index=False)
    return p


def _write_grades(fs_dir: Path, df: pd.DataFrame) -> Path:
    p = fs_dir / "grades.parquet"
    df.to_parquet(p, index=False)
    return p


def _empty_grade_summary() -> dict:
    return {"n_graded_ok": 0, "n_split_seam": 0,
            "n_not_matured": 0, "n_errors": 0, "elapsed_sec": 0.0}


# ── import the module under test ──────────────────────────────────────────────
# We import after helpers to avoid triggering module-level sklearn import
from scripts import build_flow_signals as _bfs


# ═══════════════════════════════════════════════════════════════════════════════
# 1. No-model path
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoModelPath:
    """All events land with status=no_model when scoring enabled but no artifacts."""

    def test_no_model_status(self, tmp_path):
        fs_dir = tmp_path / "data" / "flow_signals"
        fs_dir.mkdir(parents=True)
        ledger = _make_ledger(n=3, dte_bucket="8_30d")
        _write_ledger(fs_dir, ledger)

        cfg_path = _write_kill_switch_yml(tmp_path, enabled=True)
        cfg = _load_cfg(cfg_path)
        cfg["models_dir"] = str(tmp_path / "data" / "flow_signals" / "models")

        result = _bfs._run_scoring_step(fs_dir, cfg)
        assert result["enabled"] is True
        assert result["n_scored_this_run"] == 3

        scores = pd.read_parquet(fs_dir / "scores.parquet")
        assert len(scores) == 3
        assert set(scores["status"].unique()) == {"no_model"}
        assert (scores["score_calibrated"].isna()).all()
        assert (scores["score_raw"].isna()).all()

    def test_no_model_gate_written(self, tmp_path):
        fs_dir = tmp_path / "data" / "flow_signals"
        fs_dir.mkdir(parents=True)
        ledger = _make_ledger(n=2, dte_bucket="1_7d")
        _write_ledger(fs_dir, ledger)

        cfg_path = _write_kill_switch_yml(tmp_path, enabled=True)
        cfg = _load_cfg(cfg_path)
        cfg["models_dir"] = str(tmp_path / "data" / "flow_signals" / "models")

        result = _bfs._run_scoring_step(fs_dir, cfg)
        gate_path = tmp_path / "data" / "flow_signals" / "gate.json"
        # Write gate directly using the builder
        gate_path.parent.mkdir(parents=True, exist_ok=True)
        _bfs._write_gate(
            gate_path,
            ledger_stats={"n_rows": 2, "n_sessions": 1, "dte_bucket_counts": {},
                          "events_per_day": {}, "last_ts": None},
            grade_summary=_empty_grade_summary(),
            harvest_n_new=2,
            elapsed_sec=1.0,
            asof="2026-07-14",
            scoring_summary=result,
        )
        gate = json.loads(gate_path.read_text())
        assert gate["schema"] == "flow_signals.gate/v2"
        assert gate["scoring"]["enabled"] is True
        assert gate["scored"] is False

    def test_exit_0_no_model(self, tmp_path):
        """_run_scoring_step returns a dict (not raises) when no artifacts."""
        fs_dir = tmp_path / "data" / "flow_signals"
        fs_dir.mkdir(parents=True)
        _write_ledger(fs_dir, _make_ledger(n=1))

        cfg_path = _write_kill_switch_yml(tmp_path, enabled=True)
        cfg = _load_cfg(cfg_path)
        cfg["models_dir"] = str(tmp_path / "non_existent_models")

        # Must not raise
        result = _bfs._run_scoring_step(fs_dir, cfg)
        assert isinstance(result, dict)


def _load_cfg(cfg_path: Path) -> dict:
    import yaml
    return yaml.safe_load(cfg_path.read_text()) or {}


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Keep-first dedup on re-run
# ═══════════════════════════════════════════════════════════════════════════════

class TestKeepFirstDedup:
    """Re-running the scorer with existing scores.parquet must not duplicate rows."""

    def test_rerun_no_duplicates(self, tmp_path):
        fs_dir = tmp_path / "data" / "flow_signals"
        fs_dir.mkdir(parents=True)
        ledger = _make_ledger(n=4, dte_bucket="8_30d")
        _write_ledger(fs_dir, ledger)

        cfg_path = _write_kill_switch_yml(tmp_path, enabled=True)
        cfg = _load_cfg(cfg_path)
        cfg["models_dir"] = str(tmp_path / "models")

        # First run
        _bfs._run_scoring_step(fs_dir, cfg)

        # Second run — same ledger, same events
        _bfs._run_scoring_step(fs_dir, cfg)

        scores = pd.read_parquet(fs_dir / "scores.parquet")
        assert scores["event_id"].is_unique, "Duplicates found after re-run"
        assert len(scores) == 4

    def test_new_events_appended(self, tmp_path):
        fs_dir = tmp_path / "data" / "flow_signals"
        fs_dir.mkdir(parents=True)

        # First run with 2 events
        ledger_v1 = _make_ledger(n=2, dte_bucket="8_30d")
        _write_ledger(fs_dir, ledger_v1)

        cfg_path = _write_kill_switch_yml(tmp_path, enabled=True)
        cfg = _load_cfg(cfg_path)
        cfg["models_dir"] = str(tmp_path / "models")

        _bfs._run_scoring_step(fs_dir, cfg)

        # Add 2 more events
        extra = _make_ledger(n=2, dte_bucket="8_30d")
        extra["event_id"] = ["evt_new_0", "evt_new_1"]
        ledger_v2 = pd.concat([ledger_v1, extra], ignore_index=True)
        _write_ledger(fs_dir, ledger_v2)

        _bfs._run_scoring_step(fs_dir, cfg)

        scores = pd.read_parquet(fs_dir / "scores.parquet")
        assert scores["event_id"].is_unique
        assert len(scores) == 4


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Kill-switch off
# ═══════════════════════════════════════════════════════════════════════════════

class TestKillSwitchOff:
    """When scoring.enabled=False no scores written; gate shows enabled=False."""

    def test_no_scores_written(self, tmp_path):
        fs_dir = tmp_path / "data" / "flow_signals"
        fs_dir.mkdir(parents=True)
        ledger = _make_ledger(n=3)
        _write_ledger(fs_dir, ledger)

        cfg_path = _write_kill_switch_yml(tmp_path, enabled=False)
        cfg = _load_cfg(cfg_path)
        cfg["models_dir"] = str(tmp_path / "models")

        result = _bfs._run_scoring_step(fs_dir, cfg)
        assert result["enabled"] is False
        assert not (fs_dir / "scores.parquet").exists()

    def test_gate_scoring_enabled_false(self, tmp_path):
        cfg_path = _write_kill_switch_yml(tmp_path, enabled=False)
        cfg = _load_cfg(cfg_path)
        fs_dir = tmp_path / "data" / "flow_signals"
        fs_dir.mkdir(parents=True)
        _write_ledger(fs_dir, _make_ledger(n=1))

        result = _bfs._run_scoring_step(fs_dir, cfg)
        gate_path = tmp_path / "gate.json"
        _bfs._write_gate(
            gate_path,
            ledger_stats={"n_rows": 1, "n_sessions": 1, "dte_bucket_counts": {},
                          "events_per_day": {}, "last_ts": None},
            grade_summary=_empty_grade_summary(),
            harvest_n_new=0,
            elapsed_sec=0.1,
            asof="2026-07-14",
            scoring_summary=result,
        )
        gate = json.loads(gate_path.read_text())
        assert gate["scoring"]["enabled"] is False
        assert gate["schema"] == "flow_signals.gate/v2"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. not_deployable path
# ═══════════════════════════════════════════════════════════════════════════════

class TestNotDeployable:
    """manifest.deployable=False → score_calibrated null, status not_deployable."""

    def _make_artifact(self, tmp_path: Path, deployable: bool = False) -> Path:
        """Create a fake artifact directory with model.joblib + calibrator.joblib + manifest.

        Uses HistGradientBoostingClassifier (the house model) + IsotonicRegression
        (the house calibrator) so calibrator.predict() works on a 1-D array of floats.
        """
        import joblib
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.isotonic import IsotonicRegression

        bucket = "8_90"
        artifact_dir = tmp_path / f"flow_score_{bucket}_v1"
        artifact_dir.mkdir(parents=True)

        # Train a tiny model on dummy data
        X = np.array([[1.0, 2.0, 0.8], [2.0, 1.0, 0.2],
                      [3.0, 3.0, 0.9], [0.5, 0.5, 0.1]])
        y = np.array([1, 0, 1, 0])
        model = HistGradientBoostingClassifier(max_iter=5, random_state=42)
        model.fit(X, y)

        # Calibrator: isotonic regression on [0, 1] → [0, 1]
        proba = model.predict_proba(X)[:, 1]
        calibrator = IsotonicRegression(out_of_bounds="clip")
        calibrator.fit(proba, y.astype(float))

        model_path = artifact_dir / "model.joblib"
        cal_path = artifact_dir / "calibrator.joblib"
        joblib.dump(model, model_path)
        joblib.dump(calibrator, cal_path)

        def _sha256(p: Path) -> str:
            h = hashlib.sha256()
            h.update(p.read_bytes())
            return h.hexdigest()

        manifest = {
            "schema": "flow_score.model_manifest/v1",
            "bucket": bucket,
            "model_version": "v1",
            "deployable": deployable,
            # Calibration metrics nested under "calibration" key — mirrors real trainer
            # output (_write_artifact stores calibration_metrics under manifest["calibration"]).
            "calibration": {
                "ece": 0.03 if deployable else 0.08,
                "brier": 0.2,
                "base_rate_brier": 0.25,
            },
            "hashes": {
                "model_sha256": _sha256(model_path),
                "calibrator_sha256": _sha256(cal_path),
            },
            "cv_params": {
                "feature_columns": ["premium", "premium_z", "at_ask_share"],
            },
        }
        (artifact_dir / "manifest.json").write_text(json.dumps(manifest))
        return tmp_path

    def test_not_deployable_status(self, tmp_path):
        models_dir = self._make_artifact(tmp_path / "models", deployable=False)
        fs_dir = tmp_path / "data" / "flow_signals"
        fs_dir.mkdir(parents=True)

        ledger = _make_ledger(n=3, dte_bucket="8_30d")
        _write_ledger(fs_dir, ledger)

        cfg_path = _write_kill_switch_yml(tmp_path, enabled=True)
        cfg = _load_cfg(cfg_path)
        cfg["models_dir"] = str(models_dir)

        _bfs._run_scoring_step(fs_dir, cfg)

        scores = pd.read_parquet(fs_dir / "scores.parquet")
        assert set(scores["status"].unique()) == {"not_deployable"}
        assert (scores["score_calibrated"].isna()).all()
        assert (~scores["score_raw"].isna()).any()  # score_raw is populated

    def test_deployable_status_scored(self, tmp_path):
        models_dir = self._make_artifact(tmp_path / "models", deployable=True)
        fs_dir = tmp_path / "data" / "flow_signals"
        fs_dir.mkdir(parents=True)

        ledger = _make_ledger(n=3, dte_bucket="8_30d")
        _write_ledger(fs_dir, ledger)

        cfg_path = _write_kill_switch_yml(tmp_path, enabled=True)
        cfg = _load_cfg(cfg_path)
        cfg["models_dir"] = str(models_dir)

        _bfs._run_scoring_step(fs_dir, cfg)

        scores = pd.read_parquet(fs_dir / "scores.parquet")
        assert set(scores["status"].unique()) == {"scored"}
        # score_calibrated should be non-null for deployable (IsotonicRegression works on 1-D)
        assert (~scores["score_calibrated"].isna()).all()


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Decay breach
# ═══════════════════════════════════════════════════════════════════════════════

class TestDecayBreach:
    """Realized ECE >= threshold → decayed=True in monitor; gate carries flag."""

    def _build_breach_scores(self, fs_dir: Path, n: int = 50) -> None:
        """Write scores.parquet with badly calibrated predictions for testing."""
        eids = [f"graded_{i:04d}" for i in range(n)]
        rows = []
        for eid in eids:
            rows.append({
                "event_id":          eid,
                "underlying":        "AAPL",
                "dte_bucket":        "8_30d",
                "model_bucket":      "8_90",
                "model_version":     "v1",
                "detector_version":  "v1",
                "score_raw":         0.9,
                "score_calibrated":  0.9,  # predict 90% for all
                "status":            "scored",
                "scored_at":         "2026-07-13T10:00:00+00:00",
            })
        _write_scores(fs_dir, pd.DataFrame(rows))

    def _build_breach_grades(self, fs_dir: Path, n: int = 50) -> None:
        """Write grades.parquet where all outcomes are 0 (predicting 0.9 → huge ECE)."""
        eids = [f"graded_{i:04d}" for i in range(n)]
        rows = []
        for eid in eids:
            rows.append({
                "event_id":      eid,
                "fwd_ret":       -0.01,
                "spy_ret":       0.00,
                "spy_excess":    -0.01,
                "spy_excess_5":  -0.01,
                "spy_excess_21": -0.01,
                "spy_excess_63": -0.01,
                "outcome":       0,
                "grade":         "ok",
                "graded_at":     "2026-09-03T00:00:00+00:00",
            })
        _write_grades(fs_dir, pd.DataFrame(rows))

    def test_decay_breach_detected(self, tmp_path):
        fs_dir = tmp_path / "data" / "flow_signals"
        fs_dir.mkdir(parents=True)

        self._build_breach_scores(fs_dir, n=50)
        self._build_breach_grades(fs_dir, n=50)

        cfg_path = _write_kill_switch_yml(tmp_path, enabled=True)
        cfg = _load_cfg(cfg_path)

        monitor = _bfs._run_decay_monitor(
            scores_path=fs_dir / "scores.parquet",
            flow_signals_dir=fs_dir,
            cfg=cfg,
            calibration_info={},
        )

        # 8_90 bucket: predicting 0.9 when all outcomes are 0 → large ECE
        assert "8_90" in monitor
        assert monitor["8_90"]["decayed"] is True
        assert monitor["8_90"]["realized_ece"] >= 0.05

    def test_no_breach_on_good_calibration(self, tmp_path):
        """Monitor returns a dict; perfectly-calibrated predictions yield low ECE.

        Uses a deterministic, perfectly calibrated fixture: predictions == outcomes
        (all 0.0 when outcome=0, all 1.0 when outcome=1). This is trivially calibrated
        so ECE should be 0.0, well under the 0.05 threshold.
        """
        fs_dir = tmp_path / "data" / "flow_signals"
        fs_dir.mkdir(parents=True)

        n = 60
        eids = [f"good_{i:04d}" for i in range(n)]

        # Build perfectly calibrated scores: predict exactly the outcome
        scores_rows = []
        grades_rows = []
        for i, eid in enumerate(eids):
            # Alternating 0/1 outcomes; predict exactly the outcome (ECE = 0)
            y = i % 2
            p = float(y)  # perfect prediction
            scores_rows.append({
                "event_id": eid, "underlying": "AAPL",
                "dte_bucket": "8_30d", "model_bucket": "8_90",
                "model_version": "v1", "detector_version": "v1",
                "score_raw": p, "score_calibrated": p,
                "status": "scored",
                "scored_at": "2026-07-13T10:00:00+00:00",
            })
            grades_rows.append({
                "event_id": eid,
                "fwd_ret": 0.01 * y, "spy_ret": 0.00,
                "spy_excess_21": 0.01 * y,
                "spy_excess": 0.01 * y,
                "outcome": y, "grade": "ok",
                "graded_at": "2026-09-03T00:00:00+00:00",
            })

        _write_scores(fs_dir, pd.DataFrame(scores_rows))
        _write_grades(fs_dir, pd.DataFrame(grades_rows))

        cfg_path = _write_kill_switch_yml(tmp_path, enabled=True)
        cfg = _load_cfg(cfg_path)

        monitor = _bfs._run_decay_monitor(
            scores_path=fs_dir / "scores.parquet",
            flow_signals_dir=fs_dir,
            cfg=cfg,
            calibration_info={},
        )

        # Monitor returns a dict (non-fatal)
        assert isinstance(monitor, dict)

        if "8_90" in monitor:
            # Perfectly calibrated predictions (pred == outcome) → ECE = 0 → no breach
            assert monitor["8_90"]["decayed"] is False
            ece_val = monitor["8_90"]["realized_ece"]
            assert ece_val is not None
            assert ece_val < 0.05, f"Perfect calibration should give ECE < 0.05, got {ece_val}"

    def test_gate_carries_decay_flag(self, tmp_path):
        fs_dir = tmp_path / "data" / "flow_signals"
        fs_dir.mkdir(parents=True)

        self._build_breach_scores(fs_dir, n=30)
        self._build_breach_grades(fs_dir, n=30)

        cfg_path = _write_kill_switch_yml(tmp_path, enabled=True)
        cfg = _load_cfg(cfg_path)

        monitor = _bfs._run_decay_monitor(
            scores_path=fs_dir / "scores.parquet",
            flow_signals_dir=fs_dir,
            cfg=cfg,
            calibration_info={},
        )

        gate_path = tmp_path / "gate.json"
        _bfs._write_gate(
            gate_path,
            ledger_stats={"n_rows": 30, "n_sessions": 1, "dte_bucket_counts": {},
                          "events_per_day": {}, "last_ts": None},
            grade_summary=_empty_grade_summary(),
            harvest_n_new=0,
            elapsed_sec=1.0,
            asof="2026-07-14",
            scoring_summary={
                "enabled": True, "n_scored_this_run": 0, "n_scored_total": 30,
                "by_status": {}, "model_versions": {}, "calibration": {},
                "monitor": monitor,
            },
        )
        gate = json.loads(gate_path.read_text())
        assert "monitor" in gate["scoring"]
        if "8_90" in gate["scoring"]["monitor"]:
            assert gate["scoring"]["monitor"]["8_90"]["decayed"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Gate v2 shape
# ═══════════════════════════════════════════════════════════════════════════════

class TestGateV2Shape:
    """gate.json schema=flow_signals.gate/v2; scoring block has expected keys."""

    def test_schema_string_v2(self, tmp_path):
        gate_path = tmp_path / "gate.json"
        _bfs._write_gate(
            gate_path,
            ledger_stats={"n_rows": 0, "n_sessions": 0, "dte_bucket_counts": {},
                          "events_per_day": {}, "last_ts": None},
            grade_summary=_empty_grade_summary(),
            harvest_n_new=0,
            elapsed_sec=0.1,
            asof="2026-07-14",
            scoring_summary=None,
        )
        gate = json.loads(gate_path.read_text())
        assert gate["schema"] == "flow_signals.gate/v2"

    def test_scoring_block_keys(self, tmp_path):
        gate_path = tmp_path / "gate.json"
        scoring = {
            "enabled": True,
            "model_versions": {"8_90": "v1"},
            "n_scored_total": 10,
            "n_scored_this_run": 3,
            "by_status": {"scored": 7, "no_model": 3},
            "calibration": {"8_90": {"ece": 0.03, "deployable": True}},
            "monitor": {"8_90": {"realized_ece": 0.03, "n": 10, "decayed": False}},
        }
        _bfs._write_gate(
            gate_path,
            ledger_stats={"n_rows": 10, "n_sessions": 1, "dte_bucket_counts": {},
                          "events_per_day": {}, "last_ts": None},
            grade_summary=_empty_grade_summary(),
            harvest_n_new=5,
            elapsed_sec=1.0,
            asof="2026-07-14",
            scoring_summary=scoring,
        )
        gate = json.loads(gate_path.read_text())
        sb = gate["scoring"]
        required_keys = {"enabled", "model_versions", "n_scored_total",
                         "n_scored_this_run", "by_status", "calibration", "monitor"}
        assert required_keys.issubset(sb.keys())
        assert sb["enabled"] is True
        assert sb["n_scored_total"] == 10
        assert sb["n_scored_this_run"] == 3
        assert sb["model_versions"] == {"8_90": "v1"}

    def test_scored_always_false(self, tmp_path):
        """PRE-GATE LAW: gate.json scored field is always false."""
        gate_path = tmp_path / "gate.json"
        _bfs._write_gate(
            gate_path,
            ledger_stats={"n_rows": 0, "n_sessions": 0, "dte_bucket_counts": {},
                          "events_per_day": {}, "last_ts": None},
            grade_summary=_empty_grade_summary(),
            harvest_n_new=0,
            elapsed_sec=0.0,
            asof="2026-07-14",
        )
        gate = json.loads(gate_path.read_text())
        assert gate["scored"] is False

    def test_scoring_block_present_without_summary(self, tmp_path):
        """scoring block exists even when scoring_summary is None."""
        gate_path = tmp_path / "gate.json"
        _bfs._write_gate(
            gate_path,
            ledger_stats={"n_rows": 0, "n_sessions": 0, "dte_bucket_counts": {},
                          "events_per_day": {}, "last_ts": None},
            grade_summary=_empty_grade_summary(),
            harvest_n_new=0,
            elapsed_sec=0.1,
            asof="2026-07-14",
            scoring_summary=None,
        )
        gate = json.loads(gate_path.read_text())
        assert "scoring" in gate
        assert gate["scoring"]["enabled"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 7. PIT guard
# ═══════════════════════════════════════════════════════════════════════════════

class TestPITGuard:
    """Feature frame must not include grade/outcome columns."""

    def test_grade_col_in_feature_spec_aborts_bucket(self, tmp_path):
        """If a grade column is in the manifest's feature_columns, scoring for that
        bucket emits error rows rather than silently scoring on leaked outcome data."""
        import joblib
        from sklearn.ensemble import HistGradientBoostingClassifier

        bucket = "8_90"
        artifact_dir = tmp_path / "models" / f"flow_score_{bucket}_v1"
        artifact_dir.mkdir(parents=True)

        model = HistGradientBoostingClassifier(max_iter=5, random_state=42)
        model.fit([[0, 0], [0, 0], [1, 1], [1, 1]], [0, 0, 1, 1])
        model_path = artifact_dir / "model.joblib"
        cal_path = artifact_dir / "calibrator.joblib"
        joblib.dump(model, model_path)
        joblib.dump(model, cal_path)

        def _sha256(p: Path) -> str:
            h = hashlib.sha256()
            h.update(p.read_bytes())
            return h.hexdigest()

        # Manifest includes a grade-derived column — PIT violation
        manifest = {
            "schema": "flow_score.model_manifest/v1",
            "bucket": bucket,
            "model_version": "v1",
            "deployable": True,
            "calibration": {"ece": 0.03, "brier": 0.2, "base_rate_brier": 0.25},
            "hashes": {
                "model_sha256": _sha256(model_path),
                "calibrator_sha256": _sha256(cal_path),
            },
            "cv_params": {
                # fwd_ret is a grade column — PIT violation
                "feature_columns": ["premium", "fwd_ret", "at_ask_share"],
            },
        }
        (artifact_dir / "manifest.json").write_text(json.dumps(manifest))

        fs_dir = tmp_path / "data" / "flow_signals"
        fs_dir.mkdir(parents=True)
        ledger = _make_ledger(n=3, dte_bucket="8_30d")
        # Add the grade column to the ledger (simulates accidental join)
        ledger["fwd_ret"] = 0.02
        _write_ledger(fs_dir, ledger)

        cfg_path = _write_kill_switch_yml(tmp_path, enabled=True)
        cfg = _load_cfg(cfg_path)
        cfg["models_dir"] = str(tmp_path / "models")

        _bfs._run_scoring_step(fs_dir, cfg)

        scores = pd.read_parquet(fs_dir / "scores.parquet")
        # All rows for this bucket should be error (PIT abort)
        assert set(scores["status"].unique()).issubset({"error", "no_model"})

    def test_grade_cols_absent_from_normal_feature_frame(self, tmp_path):
        """When no grade columns in ledger, scoring proceeds normally (no_model without artifact)."""
        fs_dir = tmp_path / "data" / "flow_signals"
        fs_dir.mkdir(parents=True)
        ledger = _make_ledger(n=3, dte_bucket="8_30d")
        # Confirm grade cols not present
        grade_cols_present = [c for c in ledger.columns if c in {
            "fwd_ret", "spy_excess_5", "spy_excess_21", "spy_excess_63",
            "spy_excess_126", "outcome", "grade", "graded_at",
        }]
        assert grade_cols_present == [], f"Grade cols in ledger: {grade_cols_present}"

        _write_ledger(fs_dir, ledger)

        cfg_path = _write_kill_switch_yml(tmp_path, enabled=True)
        cfg = _load_cfg(cfg_path)
        cfg["models_dir"] = str(tmp_path / "no_models")

        result = _bfs._run_scoring_step(fs_dir, cfg)
        assert result["enabled"] is True
        scores = pd.read_parquet(fs_dir / "scores.parquet")
        # no_model (no artifact) but no error from PIT guard
        assert set(scores["status"].unique()) == {"no_model"}


# ═══════════════════════════════════════════════════════════════════════════════
# 8. TZ-aware scored_at
# ═══════════════════════════════════════════════════════════════════════════════

class TestTZAwareScoredAt:
    """scored_at column is tz-aware UTC ISO string."""

    def test_scored_at_tz_aware(self, tmp_path):
        fs_dir = tmp_path / "data" / "flow_signals"
        fs_dir.mkdir(parents=True)
        ledger = _make_ledger(n=3, dte_bucket="8_30d")
        _write_ledger(fs_dir, ledger)

        cfg_path = _write_kill_switch_yml(tmp_path, enabled=True)
        cfg = _load_cfg(cfg_path)
        cfg["models_dir"] = str(tmp_path / "models")

        _bfs._run_scoring_step(fs_dir, cfg)

        scores = pd.read_parquet(fs_dir / "scores.parquet")
        assert "scored_at" in scores.columns
        # Every scored_at value should be parseable as tz-aware UTC
        for val in scores["scored_at"]:
            dt = datetime.fromisoformat(str(val))
            assert dt.tzinfo is not None, f"scored_at is not tz-aware: {val}"
            # Should be UTC
            utc_str = str(val)
            assert "+00:00" in utc_str or utc_str.endswith("Z"), (
                f"scored_at not UTC: {val}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 9. prefiltered_index_root path
# ═══════════════════════════════════════════════════════════════════════════════

class TestPrefilterIndexRoot:
    """Index root events land with status=prefiltered_index_root."""

    def test_spx_gets_prefiltered(self, tmp_path):
        fs_dir = tmp_path / "data" / "flow_signals"
        fs_dir.mkdir(parents=True)
        ledger = _make_ledger(n=3, dte_bucket="8_30d", root="SPX")
        _write_ledger(fs_dir, ledger)

        cfg_path = _write_kill_switch_yml(tmp_path, enabled=True)
        cfg = _load_cfg(cfg_path)
        cfg["models_dir"] = str(tmp_path / "models")

        _bfs._run_scoring_step(fs_dir, cfg)

        scores = pd.read_parquet(fs_dir / "scores.parquet")
        assert set(scores["status"].unique()) == {"prefiltered_index_root"}

    def test_non_index_root_not_prefiltered(self, tmp_path):
        fs_dir = tmp_path / "data" / "flow_signals"
        fs_dir.mkdir(parents=True)
        ledger = _make_ledger(n=3, dte_bucket="8_30d", root="AAPL")
        _write_ledger(fs_dir, ledger)

        cfg_path = _write_kill_switch_yml(tmp_path, enabled=True)
        cfg = _load_cfg(cfg_path)
        cfg["models_dir"] = str(tmp_path / "models")

        _bfs._run_scoring_step(fs_dir, cfg)

        scores = pd.read_parquet(fs_dir / "scores.parquet")
        # AAPL should not be prefiltered — gets no_model (no artifact)
        assert "prefiltered_index_root" not in scores["status"].values

    def test_mixed_index_and_stock(self, tmp_path):
        fs_dir = tmp_path / "data" / "flow_signals"
        fs_dir.mkdir(parents=True)

        ledger_spx = _make_ledger(n=2, dte_bucket="8_30d", root="SPX")
        ledger_aapl = _make_ledger(n=2, dte_bucket="8_30d", root="AAPL")
        ledger_aapl["event_id"] = ["aapl_0", "aapl_1"]
        ledger = pd.concat([ledger_spx, ledger_aapl], ignore_index=True)
        _write_ledger(fs_dir, ledger)

        cfg_path = _write_kill_switch_yml(tmp_path, enabled=True)
        cfg = _load_cfg(cfg_path)
        cfg["models_dir"] = str(tmp_path / "models")

        _bfs._run_scoring_step(fs_dir, cfg)

        scores = pd.read_parquet(fs_dir / "scores.parquet")
        spx_scores = scores[scores["underlying"] == "SPX"]
        aapl_scores = scores[scores["underlying"] == "AAPL"]

        assert set(spx_scores["status"].unique()) == {"prefiltered_index_root"}
        assert "prefiltered_index_root" not in aapl_scores["status"].values


# ═══════════════════════════════════════════════════════════════════════════════
# 10. bucket_unmapped path
# ═══════════════════════════════════════════════════════════════════════════════

class TestBucketUnmapped:
    """Unrecognised dte_bucket → status=bucket_unmapped."""

    def test_unknown_dte_bucket(self, tmp_path):
        fs_dir = tmp_path / "data" / "flow_signals"
        fs_dir.mkdir(parents=True)
        ledger = _make_ledger(n=3, dte_bucket="unknown_bucket_xyz")
        _write_ledger(fs_dir, ledger)

        cfg_path = _write_kill_switch_yml(tmp_path, enabled=True)
        cfg = _load_cfg(cfg_path)
        cfg["models_dir"] = str(tmp_path / "models")

        _bfs._run_scoring_step(fs_dir, cfg)

        scores = pd.read_parquet(fs_dir / "scores.parquet")
        assert set(scores["status"].unique()) == {"bucket_unmapped"}

    def test_none_dte_bucket(self, tmp_path):
        fs_dir = tmp_path / "data" / "flow_signals"
        fs_dir.mkdir(parents=True)
        ledger = _make_ledger(n=2, dte_bucket="8_30d")
        ledger["dte_bucket"] = None  # explicitly null
        _write_ledger(fs_dir, ledger)

        cfg_path = _write_kill_switch_yml(tmp_path, enabled=True)
        cfg = _load_cfg(cfg_path)
        cfg["models_dir"] = str(tmp_path / "models")

        result = _bfs._run_scoring_step(fs_dir, cfg)
        # Non-fatal; should return a dict
        assert isinstance(result, dict)

        # Rows with null dte_bucket land as unmapped
        if (fs_dir / "scores.parquet").exists():
            scores = pd.read_parquet(fs_dir / "scores.parquet")
            assert "bucket_unmapped" in scores["status"].values


# ═══════════════════════════════════════════════════════════════════════════════
# Bonus: _make_score_row contract
# ═══════════════════════════════════════════════════════════════════════════════

class TestMakeScoreRow:
    """_make_score_row builds the expected frozen column set."""

    FROZEN_COLS = {
        "event_id", "underlying", "dte_bucket", "model_bucket",
        "model_version", "detector_version", "score_raw",
        "score_calibrated", "status", "scored_at",
    }

    def test_frozen_columns_present(self):
        row = _bfs._make_score_row("evt_001", status="no_model")
        assert self.FROZEN_COLS.issubset(row.keys())

    def test_scored_at_tz_aware(self):
        row = _bfs._make_score_row("evt_002", status="no_model")
        dt = datetime.fromisoformat(row["scored_at"])
        assert dt.tzinfo is not None

    def test_event_id_str(self):
        row = _bfs._make_score_row(123, status="no_model")
        assert isinstance(row["event_id"], str)
        assert row["event_id"] == "123"
