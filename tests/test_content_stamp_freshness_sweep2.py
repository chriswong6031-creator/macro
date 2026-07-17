"""Regression tests for the second #2690 frozen-cache sweep (follow-up to the
fix/mtime-committed-artifact-gates PR).

Bug class: a freshness/staleness judgment on a GIT-COMMITTED artifact keyed
off file mtime. On CI self-hosted runners a checkout rewrites files with
mtime = checkout time, so a frozen artifact always looks freshly written and
the gate never fires (or never re-fetches). Every test here builds the
poisoned combination — STALE content stamp + FRESH file mtime — and asserts
the code now reads the content stamp.

Covers:
  1. build_release_forecast enricher_staleness → content-date columns
  2. build_release_forecast snapshot GC → embedded asof (keep-if-unreadable)
  3. risk_brain / narrative_brain interval gate → embedded as_of
  4. check_hazard_model_freshness → embedded built_at
  5. audit_fred_groups._is_fresh → newest observation date (cadence-aware)
  6. build_sector_map same-day skip → committed build-stamp sidecar
  7. metabolism insight_bus.artifact_age_hours → content stamp first
  8. cctv_finalize_watcher monthly top-up → newest tone-history content date
"""
from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest


def _touch_now(p: Path) -> None:
    """Give `p` a FRESH mtime (now) — simulating a CI checkout rewrite."""
    os.utime(p, (time.time(), time.time()))


# ---------------------------------------------------------------------------
# 1. enricher_staleness content stamps
# ---------------------------------------------------------------------------

class TestEnricherStalenessContentStamp:
    def test_kalshi_stale_content_fresh_mtime_reads_stale(self, tmp_path: Path):
        import scripts.build_release_forecast as producer

        pm = tmp_path / "data" / "prediction_markets"
        pm.mkdir(parents=True)
        old = (date.today() - timedelta(days=40)).isoformat()
        pd.DataFrame({"asof_date": [old, old], "release_type": ["CPI", "CPI"]}
                     ).to_parquet(pm / "kalshi_releases.parquet", index=False)
        _touch_now(pm / "kalshi_releases.parquet")

        stamp = producer._newest_content_stamp(pm / "kalshi_releases.parquet", "asof_date")
        assert stamp == old, f"expected content date {old}, got {stamp}"

    def test_cleveland_uses_first_seen_asof(self, tmp_path: Path):
        import scripts.build_release_forecast as producer

        p = tmp_path / "nowcast.parquet"
        pd.DataFrame({"first_seen_asof": ["2026-06-01", "2026-06-20"],
                      "value": [1.0, 2.0]}).to_parquet(p, index=False)
        _touch_now(p)
        assert producer._newest_content_stamp(p, "first_seen_asof") == "2026-06-20"

    def test_unreadable_column_is_none(self, tmp_path: Path):
        import scripts.build_release_forecast as producer

        p = tmp_path / "x.parquet"
        pd.DataFrame({"other": [1]}).to_parquet(p, index=False)
        assert producer._newest_content_stamp(p, "asof_date") is None


# ---------------------------------------------------------------------------
# 2. snapshot GC by embedded asof
# ---------------------------------------------------------------------------

class TestSnapshotGCEmbeddedAsof:
    def test_old_asof_fresh_mtime_is_deleted(self, tmp_path: Path):
        import scripts.build_release_forecast as producer

        snaps = tmp_path / "input_snapshots"
        snaps.mkdir()
        old_snap = snaps / "CPI_2026-05-01_first_2026-04-30_v1.json"
        old_snap.write_text(json.dumps({"asof": (date.today() - timedelta(days=45)).isoformat()}))
        _touch_now(old_snap)  # fresh checkout mtime must NOT protect it

        fresh_snap = snaps / "CPI_2026-07-15_first_2026-07-14_v1.json"
        fresh_snap.write_text(json.dumps({"asof": date.today().isoformat()}))

        deleted = producer._run_snapshot_gc(snaps, [], date.today())
        assert deleted == 1
        assert not old_snap.exists()
        assert fresh_snap.exists()

    def test_stampless_snapshot_is_kept(self, tmp_path: Path):
        """Deletion is destructive — an unreadable/stamp-less snapshot is KEPT."""
        import scripts.build_release_forecast as producer

        snaps = tmp_path / "input_snapshots"
        snaps.mkdir()
        stampless = snaps / "CPI_2020-01-01_first_2020-01-01_v1.json"
        stampless.write_text(json.dumps({"features": {}}))  # no asof

        deleted = producer._run_snapshot_gc(snaps, [], date.today())
        assert deleted == 0
        assert stampless.exists()

    def test_permanent_refs_still_protected(self, tmp_path: Path):
        import scripts.build_release_forecast as producer

        snaps = tmp_path / "input_snapshots"
        snaps.mkdir()
        witness = snaps / "CPI_2026-01-15_first_2026-01-14_v1.json"
        witness.write_text(json.dumps({"asof": "2026-01-14"}))
        ledger = [{
            "row_type": "projection", "release": "CPI", "period": "2025-12",
            "release_date": "2026-01-15", "asof_night": "2026-01-14",
            "input_snapshot_ref": f"input_snapshots/{witness.name}",
        }]
        deleted = producer._run_snapshot_gc(snaps, ledger, date.today())
        assert deleted == 0
        assert witness.exists()


# ---------------------------------------------------------------------------
# 3. brain interval gates
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mod_name,site_rel", [
    ("engine.risk_brain", Path("site") / "riskdata" / "risk_brain.json"),
    ("engine.narrative_brain", Path("site") / "basketdata" / "narrative_brain.json"),
])
class TestBrainIntervalGate:
    def _setup(self, tmp_path, mod_name, site_rel, as_of):
        import importlib
        mod = importlib.import_module(mod_name)
        site = tmp_path / site_rel
        site.parent.mkdir(parents=True, exist_ok=True)
        site.write_text(json.dumps({"schema": "test.v1", "as_of": as_of}))
        _touch_now(site)  # checkout-fresh mtime
        return mod, site

    def test_stale_asof_fresh_mtime_regenerates(self, tmp_path, monkeypatch,
                                                mod_name, site_rel):
        """A committed note whose as_of is older than interval_days must NOT be
        returned from the gate, even with a checkout-fresh mtime."""
        old = (date.today() - timedelta(days=10)).isoformat()
        mod, _ = self._setup(tmp_path, mod_name, site_rel, old)
        monkeypatch.setattr(mod, "_cfg", lambda: {"enabled": True, "interval_days": 3})
        # Regeneration path reached ⇒ gather_evidence is called; make it a
        # clean early-exit sentinel so run() returns None (never the cached note).
        called = {"n": 0}

        def _fake_gather(*a, **k):
            called["n"] += 1
            return None
        monkeypatch.setattr(mod, "gather_evidence", _fake_gather)

        out = mod.run(persist=False, root=tmp_path)
        assert called["n"] == 1, "stale as_of must fall through to regeneration"
        assert out is None

    def test_fresh_asof_returns_cached_without_regenerating(self, tmp_path, monkeypatch,
                                                            mod_name, site_rel):
        mod, _ = self._setup(tmp_path, mod_name, site_rel, date.today().isoformat())
        monkeypatch.setattr(mod, "_cfg", lambda: {"enabled": True, "interval_days": 3})
        monkeypatch.setattr(mod, "gather_evidence",
                            lambda *a, **k: pytest.fail("gate should have returned cached note"))
        out = mod.run(persist=False, root=tmp_path)
        assert isinstance(out, dict) and out.get("schema") == "test.v1"

    def test_missing_asof_regenerates(self, tmp_path, monkeypatch, mod_name, site_rel):
        import importlib
        mod = importlib.import_module(mod_name)
        site = tmp_path / site_rel
        site.parent.mkdir(parents=True, exist_ok=True)
        site.write_text(json.dumps({"schema": "test.v1"}))  # no as_of ⇒ stale
        monkeypatch.setattr(mod, "_cfg", lambda: {"enabled": True, "interval_days": 3})
        monkeypatch.setattr(mod, "gather_evidence", lambda *a, **k: None)
        assert mod.run(persist=False, root=tmp_path) is None


# ---------------------------------------------------------------------------
# 4. hazard model freshness tripwire
# ---------------------------------------------------------------------------

class TestHazardBuiltAtStamp:
    def _hazard_dir(self, tmp_path: Path, built_at: str | None) -> Path:
        hz = tmp_path / "hazard"
        hz.mkdir()
        pd.DataFrame({"x": [1]}).to_parquet(hz / "panel_price_test1.parquet")
        model = {"turn_def_version": "price_test1",
                 "ledger": {d: {h: {"verdict": "PASS"} for h in ("1m", "3m", "6m")}
                            for d in ("up", "down")}}
        if built_at is not None:
            model["built_at"] = built_at
        (hz / "model_price_test1.json").write_text(json.dumps(model))
        _touch_now(hz / "model_price_test1.json")
        return hz

    def test_stale_built_at_fresh_mtime_flags(self, tmp_path: Path):
        from scripts.check_hazard_model_freshness import check
        old = (datetime.now(timezone.utc) - timedelta(days=150)).isoformat()
        findings = check(self._hazard_dir(tmp_path, old), max_stale_days=100)
        assert any("150d old" in f or "d old (> 100d)" in f for f in findings), findings

    def test_missing_built_at_flags_stale(self, tmp_path: Path):
        from scripts.check_hazard_model_freshness import check
        findings = check(self._hazard_dir(tmp_path, None), max_stale_days=100)
        assert any("no readable built_at" in f for f in findings), findings

    def test_recent_built_at_clean(self, tmp_path: Path):
        from scripts.check_hazard_model_freshness import check
        now = datetime.now(timezone.utc).isoformat()
        assert check(self._hazard_dir(tmp_path, now), max_stale_days=100) == []


# ---------------------------------------------------------------------------
# 5. FRED groups audit
# ---------------------------------------------------------------------------

class TestFredAuditContentDate:
    def test_frozen_daily_series_fresh_mtime_is_stale(self, tmp_path: Path):
        from scripts.audit_fred_groups import _is_fresh
        idx = pd.date_range(end=pd.Timestamp.today() - pd.Timedelta(days=90), periods=30)
        p = tmp_path / "FROZEN.parquet"
        pd.DataFrame({"v": range(30)}, index=idx).to_parquet(p)
        _touch_now(p)  # checkout-fresh mtime must not mask the frozen content
        assert _is_fresh(p, date.today(), stale_days=45) is False

    def test_quarterly_series_gets_cadence_slack(self, tmp_path: Path):
        """A healthy quarterly series (last obs ~80d ago) must NOT read stale."""
        from scripts.audit_fred_groups import _is_fresh
        idx = pd.date_range(end=pd.Timestamp.today() - pd.Timedelta(days=80),
                            periods=12, freq="QS")
        p = tmp_path / "GDPQ.parquet"
        pd.DataFrame({"v": range(12)}, index=idx).to_parquet(p)
        assert _is_fresh(p, date.today(), stale_days=45) is True

    def test_fresh_daily_series_is_fresh(self, tmp_path: Path):
        from scripts.audit_fred_groups import _is_fresh
        idx = pd.date_range(end=pd.Timestamp.today() - pd.Timedelta(days=2), periods=30)
        p = tmp_path / "LIVE.parquet"
        pd.DataFrame({"v": range(30)}, index=idx).to_parquet(p)
        assert _is_fresh(p, date.today(), stale_days=45) is True

    def test_undated_parquet_is_stale(self, tmp_path: Path):
        from scripts.audit_fred_groups import _is_fresh
        p = tmp_path / "NODATE.parquet"
        pd.DataFrame({"v": [1, 2]}).to_parquet(p)  # RangeIndex — no dates
        assert _is_fresh(p, date.today(), stale_days=45) is False


# ---------------------------------------------------------------------------
# 6. sector map build stamp
# ---------------------------------------------------------------------------

class TestSectorMapBuildStamp:
    def _wire(self, tmp_path: Path, monkeypatch):
        import scripts.build_sector_map as bsm
        from lib import config
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        monkeypatch.setattr(bsm, "_load_gics", lambda: {"AAPL": ("Technology", "gics")})
        monkeypatch.setattr(bsm, "_load_sic_text", lambda: {})
        monkeypatch.setattr(bsm, "_load_sic_numeric", lambda: {})
        return bsm

    def test_stale_stamp_fresh_mtimes_rebuilds(self, tmp_path: Path, monkeypatch):
        """Yesterday's stamp ⇒ rebuild, no matter what the mtimes say (the old
        make-style source-vs-output comparison read equal checkout mtimes as
        'up to date' and froze the map)."""
        bsm = self._wire(tmp_path, monkeypatch)
        breadth = tmp_path / "breadth"
        breadth.mkdir(parents=True)
        pd.DataFrame({"ticker": ["OLD"], "sector": ["Energy"], "source": ["gics"]}
                     ).to_parquet(breadth / "ticker_sectors.parquet", index=False)
        (breadth / "ticker_sectors_meta.json").write_text(json.dumps(
            {"built_asof": (date.today() - timedelta(days=1)).isoformat()}))
        _touch_now(breadth / "ticker_sectors.parquet")

        df = bsm.build(force=False)
        assert list(df["ticker"]) == ["AAPL"], "stale stamp must trigger a rebuild"
        meta = json.loads((breadth / "ticker_sectors_meta.json").read_text())
        assert meta["built_asof"] == date.today().isoformat()

    def test_todays_stamp_skips_rebuild(self, tmp_path: Path, monkeypatch):
        bsm = self._wire(tmp_path, monkeypatch)
        monkeypatch.setattr(bsm, "_load_gics",
                            lambda: pytest.fail("same-day stamp should skip the rebuild"))
        breadth = tmp_path / "breadth"
        breadth.mkdir(parents=True)
        pd.DataFrame({"ticker": ["KEEP"], "sector": ["Energy"], "source": ["gics"]}
                     ).to_parquet(breadth / "ticker_sectors.parquet", index=False)
        (breadth / "ticker_sectors_meta.json").write_text(json.dumps(
            {"built_asof": date.today().isoformat()}))

        df = bsm.build(force=False)
        assert list(df["ticker"]) == ["KEEP"]

    def test_missing_stamp_rebuilds(self, tmp_path: Path, monkeypatch):
        bsm = self._wire(tmp_path, monkeypatch)
        breadth = tmp_path / "breadth"
        breadth.mkdir(parents=True)
        pd.DataFrame({"ticker": ["OLD"], "sector": ["Energy"], "source": ["gics"]}
                     ).to_parquet(breadth / "ticker_sectors.parquet", index=False)
        # no sidecar at all ⇒ stamp-less ⇒ rebuild
        df = bsm.build(force=False)
        assert list(df["ticker"]) == ["AAPL"]


# ---------------------------------------------------------------------------
# 7. metabolism artifact age helper
# ---------------------------------------------------------------------------

class TestArtifactAgeHours:
    def test_stale_stamp_fresh_mtime_reads_old(self, tmp_path: Path):
        from engine.metabolism.insight_bus import artifact_age_hours
        p = tmp_path / "artifact.json"
        old = (datetime.now(timezone.utc) - timedelta(hours=100)).isoformat()
        p.write_text(json.dumps({"produced_at": old}))
        _touch_now(p)
        age = artifact_age_hours(p, datetime.now(timezone.utc).timestamp())
        assert age is not None and 99 < age < 101

    def test_fresh_stamp_old_mtime_reads_fresh(self, tmp_path: Path):
        """Mirror image: content truth also protects against a stale mtime."""
        from engine.metabolism.insight_bus import artifact_age_hours
        p = tmp_path / "artifact.json"
        p.write_text(json.dumps(
            {"produced_at": datetime.now(timezone.utc).isoformat()}))
        past = time.time() - 200 * 3600
        os.utime(p, (past, past))
        age = artifact_age_hours(p, datetime.now(timezone.utc).timestamp())
        assert age is not None and age < 1

    def test_date_only_stamp_falls_back_to_mtime(self, tmp_path: Path):
        """Date-only as_of is coarser than hour SLAs — mtime stays authoritative."""
        from engine.metabolism.insight_bus import artifact_age_hours
        p = tmp_path / "artifact.json"
        p.write_text(json.dumps({"as_of": date.today().isoformat()}))
        past = time.time() - 5 * 3600
        os.utime(p, (past, past))
        age = artifact_age_hours(p, datetime.now(timezone.utc).timestamp())
        assert age is not None and 4.5 < age < 5.5

    def test_non_json_uses_mtime(self, tmp_path: Path):
        from engine.metabolism.insight_bus import artifact_age_hours
        p = tmp_path / "store.parquet"
        p.write_bytes(b"x")
        past = time.time() - 3 * 3600
        os.utime(p, (past, past))
        age = artifact_age_hours(p, datetime.now(timezone.utc).timestamp())
        assert age is not None and 2.5 < age < 3.5


# ---------------------------------------------------------------------------
# 8. CCTV tone-history monthly top-up
# ---------------------------------------------------------------------------

class TestCctvMonthlyTopupContentGate:
    def _wire(self, tmp_path: Path, monkeypatch, last_obs_days_ago: int):
        import scripts.cctv_finalize_watcher as watcher
        tone = tmp_path / "cctv_tone_history.parquet"
        idx = pd.date_range(end=pd.Timestamp.today() - pd.Timedelta(days=last_obs_days_ago),
                            periods=10)
        pd.DataFrame({"tone": range(10)}, index=idx).to_parquet(tone)
        _touch_now(tone)  # checkout-fresh mtime must not decide anything
        monkeypatch.setattr(watcher, "TONE_HISTORY_PATH", tone)
        return watcher

    def test_stale_content_fresh_mtime_rebuilds(self, tmp_path: Path, monkeypatch, caplog):
        """60d-old newest observation + checkout-fresh mtime ⇒ the top-up gate
        opens (dry_run stops before the heavy rebuild; the log line after the
        gate is the observable)."""
        watcher = self._wire(tmp_path, monkeypatch, last_obs_days_ago=60)
        with caplog.at_level("INFO", logger=watcher.log.name):
            watcher._monthly_topup(tmp_path, dry_run=True)
        assert any("rebuilding from shards" in m for m in caplog.messages), caplog.messages

    def test_fresh_content_skips(self, tmp_path: Path, monkeypatch, caplog):
        watcher = self._wire(tmp_path, monkeypatch, last_obs_days_ago=2)
        # Old mtime + fresh content: content wins, no rebuild.
        past = time.time() - 90 * 86400
        os.utime(tmp_path / "cctv_tone_history.parquet", (past, past))
        with caplog.at_level("DEBUG", logger=watcher.log.name):
            watcher._monthly_topup(tmp_path, dry_run=True)
        assert not any("rebuilding from shards" in m for m in caplog.messages), caplog.messages
        assert any("skipping" in m for m in caplog.messages), caplog.messages
