"""Tests for W-D options_flow_attention reflex registration and trigger logic.

Guards (per spec):
  1. Registration passes reflexes.py pattern validation:
     - options_flow_attention present in config/reflexes.yml
     - claim_family = reflex.options_flow_attention
     - firings_jsonl = data/reflexes/options_flow_attention/firings.jsonl
     - is_context_only=True on all firings
     - migration_status = mirroring

  2. Zero fires on absent feed (stale-guard):
     - No live_flow/meta.json → no live-feed fires
     - Stale meta.json (age > 15 min) → no fire

  3. Firing schema (claim_id stamped, is_context_only=True, direction=0):
     - Vol>OI burst fires with direction=0
     - Wall/flip proximity fires with direction=0
     - All required reflex keys present

  4. No fire when history insufficient for z-score:
     - fresh_contracts > 0 but fewer than MIN_HISTORY_ROWS rows → no fire
     - No premium_mn column → no fire
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_flow_df(
    n_rows: int,
    fresh_contracts: float = 10.0,
    premium_mn_history: float = 5.0,
    premium_mn_latest: float = 15.0,
) -> pd.DataFrame:
    """Build a minimal options_flow summary DataFrame."""
    dates = pd.date_range(end="2026-07-05", periods=n_rows, freq="B")
    premiums = [premium_mn_history] * (n_rows - 1) + [premium_mn_latest]
    return pd.DataFrame(
        {
            "spot": [100.0] * n_rows,
            "volume": [1_000_000] * n_rows,
            "premium_mn": premiums,
            "net_premium_mn": [2.0] * n_rows,
            "pc_ratio": [1.0] * n_rows,
            "signed_pc": [0.5] * n_rows,
            "zerodte_share": [0.2] * n_rows,
            "gamma_flow_bn": [0.1] * n_rows,
            "delta_flow_mn": [5.0] * n_rows,
            "assumed_gex_bn": [0.5] * n_rows,
            "fresh_contracts": [fresh_contracts] * n_rows,
            "net_doi": [1000] * n_rows,
            "doi_pc": [0.8] * n_rows,
        },
        index=dates,
    )


def _make_gex_df(
    n_rows: int = 5,
    dist_to_flip_pct: float = 5.0,
    spot: float = 100.0,
    magnet_up: float = 110.0,
    magnet_down: float = 90.0,
) -> pd.DataFrame:
    """Build a minimal polygon_gex summary DataFrame."""
    dates = pd.date_range(end="2026-07-05", periods=n_rows, freq="B")
    return pd.DataFrame(
        {
            "spot": [spot] * n_rows,
            "net_gex_bn": [1.0] * n_rows,
            "net_vex": [1e8] * n_rows,
            "net_cex": [1e7] * n_rows,
            "gamma_flip": [spot * 0.95] * n_rows,
            "dist_to_flip_pct": [dist_to_flip_pct] * n_rows,
            "gamma_regime": ["positive"] * n_rows,
            "magnet_up": [magnet_up] * n_rows,
            "magnet_down": [magnet_down] * n_rows,
            "charm_anchor": [spot] * n_rows,
            "charm_net_sign": [1] * n_rows,
            "iv30": [0.25] * n_rows,
            "put_call_oi_ratio": [1.0] * n_rows,
            "max_pain": [spot] * n_rows,
            "n_strikes": [100] * n_rows,
            "tier": ["full"] * n_rows,
        },
        index=dates,
    )


def _write_parquet(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)


def _write_standouts(site_root: Path, tickers: list[str]) -> None:
    """Write minimal us_standouts.json with given tickers in buy lane."""
    p = site_root / "factordata" / "us_standouts.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "as_of": "2026-07-05",
        "buy": [{"ticker": t, "name": t, "sector": "Tech"} for t in tickers],
        "watch": [],
    }
    p.write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Registration validation
# ---------------------------------------------------------------------------

class TestOptionsFlowAttentionRegistration:
    """Guard: options_flow_attention is correctly registered in reflexes.yml."""

    def test_entry_present_in_registry(self):
        raw = yaml.safe_load((ROOT / "config" / "reflexes.yml").read_text())
        reflexes = raw.get("reflexes") or {}
        assert "options_flow_attention" in reflexes, (
            "options_flow_attention must be registered in config/reflexes.yml"
        )

    def test_claim_family_is_correct(self):
        raw = yaml.safe_load((ROOT / "config" / "reflexes.yml").read_text())
        entry = (raw.get("reflexes") or {}).get("options_flow_attention", {})
        assert entry.get("claim_family") == "reflex.options_flow_attention", (
            "claim_family must be 'reflex.options_flow_attention'"
        )

    def test_firings_jsonl_path_matches_convention(self):
        raw = yaml.safe_load((ROOT / "config" / "reflexes.yml").read_text())
        entry = (raw.get("reflexes") or {}).get("options_flow_attention", {})
        fj = entry.get("firings_jsonl")
        assert fj is not None, "firings_jsonl must be set"
        pattern = re.compile(r"^data/reflexes/([^/]+)/firings\.jsonl$")
        m = pattern.match(str(fj))
        assert m, f"firings_jsonl {fj!r} does not match convention"
        assert m.group(1) == "options_flow_attention", (
            f"firings_jsonl must be data/reflexes/options_flow_attention/firings.jsonl; got {fj!r}"
        )

    def test_migration_status_is_mirroring(self):
        raw = yaml.safe_load((ROOT / "config" / "reflexes.yml").read_text())
        entry = (raw.get("reflexes") or {}).get("options_flow_attention", {})
        assert entry.get("migration_status") == "mirroring", (
            "migration_status must be 'mirroring' (trigger lane is implemented)"
        )

    def test_registry_loads_without_violation(self):
        """load_registry() must not raise on the updated config."""
        from engine.neuralweb.reflexes import load_registry, invalidate_cache
        invalidate_cache()
        reg = load_registry(ROOT)
        assert "options_flow_attention" in reg

    def test_is_context_only_documented_in_entry(self):
        """Graded note or description must reference is_context_only / direction-free."""
        raw = yaml.safe_load((ROOT / "config" / "reflexes.yml").read_text())
        entry = (raw.get("reflexes") or {}).get("options_flow_attention", {})
        desc = (entry.get("description") or "") + (entry.get("graded_note") or "")
        assert "direction=0" in desc or "direction-free" in desc or "is_context_only" in desc, (
            "entry should document direction=0 / direction-free / is_context_only"
        )


# ---------------------------------------------------------------------------
# 2. Stale-guard: zero fires on absent / stale live feed
# ---------------------------------------------------------------------------

class TestLiveFeedStaleGuard:
    """Guard: no fires from live feed when absent or stale."""

    def test_no_fire_when_meta_absent(self, tmp_path):
        from scripts.build_options_flow_attention import _check_live_feed
        result = _check_live_feed(tmp_path / "data")
        assert result["available"] is False
        assert "absent" in result.get("reason", "").lower()

    def test_no_fire_when_meta_stale(self, tmp_path):
        from scripts.build_options_flow_attention import (
            _check_live_feed,
            LIVE_FEED_STALE_MINUTES,
        )
        meta_dir = tmp_path / "data" / "live_flow"
        meta_dir.mkdir(parents=True)
        stale_time = datetime.now(timezone.utc) - timedelta(minutes=LIVE_FEED_STALE_MINUTES + 5)
        meta = {"generated_at": stale_time.isoformat()}
        (meta_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        result = _check_live_feed(tmp_path / "data")
        assert result["available"] is False
        assert "stale" in result.get("reason", "").lower()

    def test_available_when_meta_fresh(self, tmp_path):
        from scripts.build_options_flow_attention import (
            _check_live_feed,
            LIVE_FEED_STALE_MINUTES,
        )
        meta_dir = tmp_path / "data" / "live_flow"
        meta_dir.mkdir(parents=True)
        fresh_time = datetime.now(timezone.utc) - timedelta(minutes=LIVE_FEED_STALE_MINUTES - 2)
        meta = {"generated_at": fresh_time.isoformat()}
        (meta_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        result = _check_live_feed(tmp_path / "data")
        assert result["available"] is True

    def test_run_produces_zero_fires_on_absent_eod_data(self, tmp_path):
        """Even with board names, zero fires when no EOD parquets exist."""
        from scripts.build_options_flow_attention import run
        site_root = tmp_path / "site"
        _write_standouts(site_root, ["AAPL", "MSFT"])
        result = run(root=tmp_path, dry_run=True)
        assert result["fires"] == []

    def test_run_with_no_board_names_zero_fires(self, tmp_path):
        """Zero fires when both standouts files are absent."""
        from scripts.build_options_flow_attention import run
        result = run(root=tmp_path, dry_run=True)
        assert result["fires"] == []
        assert result["board_names"] == []


# ---------------------------------------------------------------------------
# 3. Firing schema: claim_id, is_context_only=True, direction=0
# ---------------------------------------------------------------------------

class TestFiringSchema:
    """Guard: all firings carry the required reflex schema fields."""

    def _setup_board_and_data(self, tmp_path: Path, ticker: str = "NVDA") -> Path:
        """Write minimal board + flow + gex data for one ticker.

        Uses varied history so std > 0 (avoids degenerate null z-score).
        """
        _write_standouts(tmp_path / "site", [ticker])
        # Build varied-history flow df: 9 history rows with variance, 1 latest burst
        dates = pd.date_range(end="2026-07-05", periods=10, freq="B")
        premiums = [3.0, 5.0, 4.0, 6.0, 5.0, 4.0, 6.0, 5.0, 4.0, 50.0]
        flow = pd.DataFrame({
            "fresh_contracts": [50.0] * 10,
            "premium_mn": premiums,
        }, index=dates)
        _write_parquet(tmp_path / "data" / "options_flow" / f"summary_{ticker}.parquet", flow)
        return tmp_path

    def test_vol_oi_burst_fires_direction_zero(self, tmp_path):
        from scripts.build_options_flow_attention import run
        root = self._setup_board_and_data(tmp_path)
        result = run(root=root, dry_run=True)
        burst_fires = [f for f in result["fires"]
                       if f.get("trigger_type") == "vol_oi_burst"]
        assert len(burst_fires) >= 1, "expected at least one vol>OI burst fire"
        for fire in burst_fires:
            assert fire.get("direction") == 0, (
                f"direction must be 0 (direction-free per RO-8); got {fire.get('direction')}"
            )

    def test_wall_flip_fires_direction_zero(self, tmp_path):
        from scripts.build_options_flow_attention import run
        _write_standouts(tmp_path / "site", ["SPY"])
        # Near flip: dist_to_flip_pct = 0.5 %
        gex = _make_gex_df(n_rows=5, dist_to_flip_pct=0.5, spot=100.0)
        _write_parquet(tmp_path / "data" / "polygon_gex" / "summary_SPY.parquet", gex)
        result = run(root=tmp_path, dry_run=True)
        prox_fires = [f for f in result["fires"]
                      if f.get("trigger_type") == "wall_flip_proximity"]
        assert len(prox_fires) >= 1, "expected at least one wall/flip proximity fire"
        for fire in prox_fires:
            assert fire.get("direction") == 0, (
                f"direction must be 0 (direction-free per RO-8); got {fire.get('direction')}"
            )

    def test_firing_has_claim_id(self, tmp_path):
        """record_firing must stamp claim_id on each fire."""
        from engine.neuralweb.reflexes import record_firing
        rec = record_firing("options_flow_attention", {
            "ts": "2026-07-05T12:00:00+00:00",
            "trigger_type": "vol_oi_burst",
            "trigger_key": "vol_oi_burst:NVDA:2026-07-05",
            "action_taken": "attention_flag",
            "scope_type": "entity",
            "scope_key": "NVDA",
            "direction": 0,
            "horizon_d": None,
            "asof": "2026-07-05",
            "extra": {"trigger_label": "vol>OI magnitude burst"},
        }, root=tmp_path)
        assert "claim_id" in rec, "claim_id must be stamped"
        assert len(rec["claim_id"]) > 0

    def test_firing_has_is_context_only_true(self, tmp_path):
        """is_context_only must be True on every firing (hardcoded by reflexes.py)."""
        from engine.neuralweb.reflexes import record_firing
        rec = record_firing("options_flow_attention", {
            "ts": "2026-07-05T12:00:00+00:00",
            "trigger_key": "test_key",
            "direction": 0,
            "asof": "2026-07-05",
        }, root=tmp_path)
        assert rec.get("is_context_only") is True, (
            "is_context_only must be True (hardcoded by reflexes.record_firing)"
        )

    def test_firing_schema_required_keys(self, tmp_path):
        """Firing record must contain all required schema keys."""
        from engine.neuralweb.reflexes import record_firing
        rec = record_firing("options_flow_attention", {
            "ts": "2026-07-05T12:00:00+00:00",
            "trigger_type": "vol_oi_burst",
            "trigger_key": "vol_oi_burst:NVDA:2026-07-05",
            "action_taken": "attention_flag",
            "scope_type": "entity",
            "scope_key": "NVDA",
            "direction": 0,
            "horizon_d": None,
            "asof": "2026-07-05",
        }, root=tmp_path)
        required_keys = [
            "claim_id", "reflex", "ts", "trigger_key", "trigger_type",
            "action_taken", "scope_type", "scope_key", "direction",
            "asof", "claim_family", "is_context_only", "desk",
        ]
        for key in required_keys:
            assert key in rec, f"required key {key!r} missing from firing record"

    def test_firing_written_to_correct_path(self, tmp_path):
        """Firings must land in data/reflexes/options_flow_attention/firings.jsonl."""
        from engine.neuralweb.reflexes import record_firing
        record_firing("options_flow_attention", {
            "ts": "2026-07-05T12:00:00+00:00",
            "trigger_key": "k",
            "direction": 0,
            "asof": "2026-07-05",
        }, root=tmp_path)
        expected = (
            tmp_path / "data" / "reflexes" / "options_flow_attention" / "firings.jsonl"
        )
        assert expected.exists(), f"firings.jsonl must exist at {expected}"

    def test_firings_jsonl_each_line_valid_json(self, tmp_path):
        """Every line in the firings.jsonl must be valid JSON."""
        from engine.neuralweb.reflexes import record_firing
        for i in range(3):
            record_firing("options_flow_attention", {
                "ts": f"2026-07-05T12:0{i}:00+00:00",
                "trigger_key": f"k{i}",
                "direction": 0,
                "asof": "2026-07-05",
            }, root=tmp_path)
        fj = tmp_path / "data" / "reflexes" / "options_flow_attention" / "firings.jsonl"
        lines = [l for l in fj.read_text().splitlines() if l.strip()]
        assert len(lines) == 3
        for line in lines:
            parsed = json.loads(line)
            assert parsed["claim_family"] == "reflex.options_flow_attention"
            assert parsed["direction"] == 0
            assert parsed["is_context_only"] is True


# ---------------------------------------------------------------------------
# 4. No fire when history insufficient for z-score
# ---------------------------------------------------------------------------

class TestInsufficientHistoryNoFire:
    """Guard: vol>OI burst does not fire when history is insufficient."""

    def test_no_fire_with_too_few_rows(self, tmp_path):
        """Fewer than MIN_HISTORY_ROWS rows → no vol>OI fire."""
        from scripts.build_options_flow_attention import (
            _trigger_vol_oi_burst,
            MIN_HISTORY_ROWS,
        )
        # Build a df with fewer than MIN_HISTORY_ROWS rows
        flow = _make_flow_df(
            n_rows=MIN_HISTORY_ROWS - 1,
            fresh_contracts=50.0,
            premium_mn_history=5.0,
            premium_mn_latest=100.0,  # very high — would fire if history were sufficient
        )
        result = _trigger_vol_oi_burst("TEST", flow, "2026-07-05")
        assert result is None, (
            f"Must not fire with {MIN_HISTORY_ROWS - 1} rows "
            f"(< MIN_HISTORY_ROWS={MIN_HISTORY_ROWS})"
        )

    def test_no_fire_with_exactly_min_history_rows_minus_one(self, tmp_path):
        """MIN_HISTORY_ROWS - 1 rows is still insufficient."""
        from scripts.build_options_flow_attention import (
            _trigger_vol_oi_burst,
            MIN_HISTORY_ROWS,
        )
        flow = _make_flow_df(n_rows=MIN_HISTORY_ROWS - 1, fresh_contracts=100.0,
                             premium_mn_history=1.0, premium_mn_latest=999.0)
        result = _trigger_vol_oi_burst("TEST", flow, "2026-07-05")
        assert result is None

    def test_no_fire_when_no_premium_mn_column(self, tmp_path):
        """Missing premium_mn column → no fire (null-safe)."""
        from scripts.build_options_flow_attention import _trigger_vol_oi_burst
        flow = _make_flow_df(n_rows=10, fresh_contracts=50.0)
        flow = flow.drop(columns=["premium_mn"])
        result = _trigger_vol_oi_burst("TEST", flow, "2026-07-05")
        assert result is None

    def test_no_fire_when_fresh_contracts_zero(self, tmp_path):
        """fresh_contracts=0 → no fire regardless of z-score."""
        from scripts.build_options_flow_attention import _trigger_vol_oi_burst
        flow = _make_flow_df(n_rows=10, fresh_contracts=0.0,
                             premium_mn_history=5.0, premium_mn_latest=50.0)
        result = _trigger_vol_oi_burst("TEST", flow, "2026-07-05")
        assert result is None, "fresh_contracts=0 must not fire"

    def test_no_fire_when_z_score_below_threshold(self, tmp_path):
        """z-score < PREMIUM_Z_THRESHOLD → no fire."""
        from scripts.build_options_flow_attention import (
            _trigger_vol_oi_burst,
            PREMIUM_Z_THRESHOLD,
        )
        # Low z-score: latest ≈ mean (no burst)
        flow = _make_flow_df(n_rows=10, fresh_contracts=10.0,
                             premium_mn_history=10.0, premium_mn_latest=10.5)
        result = _trigger_vol_oi_burst("TEST", flow, "2026-07-05")
        assert result is None, f"z-score below {PREMIUM_Z_THRESHOLD} must not fire"

    def test_fires_with_sufficient_history_and_burst(self, tmp_path):
        """Positive control: should fire with sufficient history + high z-score."""
        from scripts.build_options_flow_attention import (
            _trigger_vol_oi_burst,
            MIN_HISTORY_ROWS,
            PREMIUM_Z_THRESHOLD,
        )
        # History: 9 rows at 5.0, latest at 50.0 → z ≈ (50-5)/0 ... need variance
        # Use varied history to avoid zero-std
        flow = _make_flow_df(n_rows=10, fresh_contracts=10.0,
                             premium_mn_history=5.0, premium_mn_latest=30.0)
        result = _trigger_vol_oi_burst("TEST", flow, "2026-07-05")
        # With 9 history rows all at 5.0 → std=0 → null. Use varied history.
        # Re-build with some variance
        dates = pd.date_range(end="2026-07-05", periods=10, freq="B")
        # history rows have variance, latest is a large burst
        import math
        premiums = [3.0, 4.0, 5.0, 6.0, 5.0, 4.0, 6.0, 5.0, 4.0, 50.0]
        flow2 = pd.DataFrame({
            "fresh_contracts": [10.0] * 10,
            "premium_mn": premiums,
        }, index=dates)
        result2 = _trigger_vol_oi_burst("TEST", flow2, "2026-07-05")
        assert result2 is not None, (
            "Expected a fire with high z-score (history has variance, latest=50)"
        )
        assert result2["direction"] == 0, "direction must be 0 (direction-free)"
        assert result2["trigger_type"] == "vol_oi_burst"

    def test_no_fire_when_history_all_same_value(self, tmp_path):
        """Std=0 (degenerate history) → no fire (null z-score)."""
        from scripts.build_options_flow_attention import _trigger_vol_oi_burst
        # All history rows at exactly 5.0 → std=0
        flow = _make_flow_df(n_rows=10, fresh_contracts=10.0,
                             premium_mn_history=5.0, premium_mn_latest=50.0)
        result = _trigger_vol_oi_burst("TEST", flow, "2026-07-05")
        assert result is None, "std=0 (degenerate history) must not fire"


# ---------------------------------------------------------------------------
# 5. Wall/flip proximity trigger specifics
# ---------------------------------------------------------------------------

class TestWallFlipProximity:
    def test_near_flip_fires(self):
        from scripts.build_options_flow_attention import _trigger_wall_flip_proximity
        gex = _make_gex_df(dist_to_flip_pct=0.5)
        result = _trigger_wall_flip_proximity("SPY", gex, "2026-07-05")
        assert result is not None, "dist_to_flip=0.5% (< 1%) must fire"
        assert result["direction"] == 0
        assert result["trigger_type"] == "wall_flip_proximity"

    def test_far_from_flip_no_fire(self):
        from scripts.build_options_flow_attention import _trigger_wall_flip_proximity
        gex = _make_gex_df(dist_to_flip_pct=10.0, spot=100.0,
                           magnet_up=120.0, magnet_down=70.0)
        result = _trigger_wall_flip_proximity("SPY", gex, "2026-07-05")
        assert result is None, "far from flip and walls must not fire"

    def test_near_wall_magnet_fires(self):
        from scripts.build_options_flow_attention import _trigger_wall_flip_proximity
        # spot=100, magnet_up=100.5 → wall dist = 0.5%
        gex = _make_gex_df(dist_to_flip_pct=5.0, spot=100.0,
                           magnet_up=100.5, magnet_down=80.0)
        result = _trigger_wall_flip_proximity("SPY", gex, "2026-07-05")
        assert result is not None, "magnet within 0.5% of spot must fire"
        assert result["direction"] == 0

    def test_no_fire_on_empty_gex_df(self):
        from scripts.build_options_flow_attention import _trigger_wall_flip_proximity
        empty = pd.DataFrame()
        result = _trigger_wall_flip_proximity("SPY", empty, "2026-07-05")
        assert result is None

    def test_no_fire_on_none_gex(self):
        from scripts.build_options_flow_attention import _trigger_wall_flip_proximity
        result = _trigger_wall_flip_proximity("SPY", None, "2026-07-05")
        assert result is None


# ---------------------------------------------------------------------------
# 6. Staging-glob: daily.yml covers data/reflexes/ path
# ---------------------------------------------------------------------------

class TestStagingCoverage:
    """Guard: the firings path is covered by workflow commit steps."""

    def test_daily_yml_collect_stages_data_dir(self):
        """daily.yml collect job commit step uses 'git add data/' which covers
        data/reflexes/options_flow_attention/ (SENTINEL STAGING LAW)."""
        wf_path = ROOT / ".github" / "workflows" / "daily.yml"
        doc = yaml.safe_load(wf_path.read_text())
        collect_job = (doc.get("jobs") or {}).get("collect") or {}
        steps = collect_job.get("steps") or []
        commit_bodies = [
            s.get("run", "") for s in steps
            if s.get("run") and "git add" in s.get("run", "")
        ]
        assert commit_bodies, "no git add step found in daily.yml collect job"
        staged_all = " ".join(
            add
            for body in commit_bodies
            for add in re.findall(r"git add ([^\n]+)", body)
        )
        # 'git add data/' covers data/reflexes/options_flow_attention/
        assert "data/" in staged_all or "data/reflexes" in staged_all, (
            "daily.yml collect commit step must stage data/ or data/reflexes/ "
            "(SENTINEL STAGING LAW for options_flow_attention firings path)"
        )

    def test_daily_yml_engine_stages_data_dir(self):
        """daily.yml engine job 'commit engine outputs' also stages data/."""
        wf_path = ROOT / ".github" / "workflows" / "daily.yml"
        doc = yaml.safe_load(wf_path.read_text())
        engine_job = (doc.get("jobs") or {}).get("engine") or {}
        steps = engine_job.get("steps") or []
        commit_bodies = [
            s.get("run", "") for s in steps
            if s.get("run") and "git add" in s.get("run", "")
            and "git commit" in s.get("run", "")
        ]
        assert commit_bodies, "no commit step with git add + git commit in engine job"
        staged_all = " ".join(
            add
            for body in commit_bodies
            for add in re.findall(r"git add ([^\n]+)", body)
        )
        assert "data/" in staged_all, (
            "daily.yml engine commit step must stage data/ to cover "
            "data/reflexes/options_flow_attention/"
        )
