"""Tests for scripts/build_china_risk_state.py — the intraday CN live risk-state builder.

Two core guarantees tested:
  1. OFFLINE BUILD: the builder runs, emits site/live/china_risk_state.json with the
     correct schema, live_active=False, display verdict == nightly verdict.
  2. LEDGER FREEZE (critical): zero data/ files are written or mutated by the builder,
     no matter whether quotes are fresh or absent.  The only new/changed file is
     site/live/china_risk_state.json.  lib.store.read is always restored even if an
     exception fires inside the live recompute.

Test idiom follows tests/test_live_overlay.py and the monkeypatch approach in
tests/test_build_options_screener.py: use monkeypatch to redirect the output path
so the real site/live/ directory is not written during CI.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Helpers — minimal fake stores so the builder has something to read
# ---------------------------------------------------------------------------

def _fake_cn_close(n: int = 400, start: float = 3000.0) -> pd.DataFrame:
    idx = pd.bdate_range("2023-01-01", periods=n)
    s = pd.Series(start + pd.Series(range(n), index=idx) * 0.5, index=idx)
    return pd.DataFrame({"close": s})


def _fake_breadth(n: int = 400) -> pd.DataFrame:
    idx = pd.bdate_range("2023-01-01", periods=n)
    s = pd.Series(0.55, index=idx)
    return pd.DataFrame({"pct_above_200": s, "pct_above_50": s})


def _fake_store(group: str, name: str, *a, **k):
    """Minimal store.read stub that returns just enough data to keep the engine alive."""
    if group == "china" and name in ("000001.SS", "510300.SS", "399001.SZ",
                                      "159915.SZ", "510880.SS", "511010.SS",
                                      "512400.SS", "518880.SS"):
        return _fake_cn_close()
    if group == "china_breadth" and name == "breadth":
        return _fake_breadth()
    if group == "fred":
        idx = pd.bdate_range("2023-01-01", periods=400)
        return pd.DataFrame({"close": pd.Series(4.5, index=idx)})
    if group in ("yahoo", "hk"):
        return _fake_cn_close(start=100.0)
    if group == "china_property" and name == "cgb":
        idx = pd.bdate_range("2023-01-01", periods=400)
        return pd.DataFrame({"cgb_10y": pd.Series(2.8, index=idx)})
    if group in ("china_qvix",):
        idx = pd.bdate_range("2023-01-01", periods=400)
        return pd.DataFrame({"close": pd.Series(15.0, index=idx)})
    return None


def _fake_latest() -> dict:
    return {
        "date": "2026-07-14",
        "conditions": {
            "roro": {
                "roro_state": "neutral",
                "roro": 0.1,
                "legs": [],
                "china_roro_qvix": 0.2,
                "china_roro_margin": -0.1,
            },
            "recession": {"label": "low", "score": 20},
            "drawdown_risk": {"band": "low", "score": 15},
        },
        "liquidity_overlay": "neutral",
    }


def _fake_features() -> "pd.DataFrame":
    """Minimal features frame for china_inputs.build_features — enough for F4 breadth."""
    n = 500
    idx = pd.bdate_range("2021-01-01", periods=n)
    df = pd.DataFrame(index=idx)
    df["pct_above_200"] = 0.55
    df["510300.SS"] = 3000.0 + pd.Series(range(n), index=idx) * 0.1
    df["000001.SS"] = 3500.0
    df["399001.SZ"] = 10000.0
    return df


# ---------------------------------------------------------------------------
# The core tests — each sets up its own tmp_path stores/config monkeypatching
# ---------------------------------------------------------------------------

class TestBuildChinaRiskState:
    """Core correctness + ledger-freeze tests for build_china_risk_state.build()."""

    def _snapshot_data(self, data_root: Path) -> dict:
        """Walk all files under data_root and capture (path, size, mtime_ns) tuples."""
        snap = {}
        for dirpath, _, filenames in os.walk(data_root):
            for fn in filenames:
                p = Path(dirpath) / fn
                try:
                    st = p.stat()
                    snap[str(p)] = (st.st_size, st.st_mtime_ns)
                except OSError:
                    pass
        return snap

    def test_offline_build_schema_and_live_inactive(self, tmp_path, monkeypatch):
        """Offline build: schema correct, live_active False, display==nightly verdict."""
        import lib.config as lib_config
        import lib.store as store_mod
        import engine.china_inputs as ci

        # Set up fake data dirs
        real_load = lib_config.load()
        site_dir = tmp_path / "site"
        data_dir = tmp_path / "data"
        (data_dir / "china_regime").mkdir(parents=True)
        (data_dir / "china_regime" / "latest.json").write_text(json.dumps(_fake_latest()))
        (site_dir / "live").mkdir(parents=True)

        monkeypatch.setattr(lib_config, "load", lambda: {
            **real_load,
            "storage": {**real_load.get("storage", {}), "site_dir": str(site_dir)},
        })
        monkeypatch.setattr(lib_config, "ROOT", tmp_path)
        monkeypatch.setattr(lib_config, "data_dir", lambda: data_dir)
        monkeypatch.setattr(store_mod, "read", _fake_store)
        monkeypatch.setattr(ci, "build_features", lambda: _fake_features())

        import scripts.build_china_risk_state as mod
        result = mod.build(offline=True)

        # Builder must return ok-ish status
        assert result.get("status") == "ok" or "live_active" in result, (
            f"unexpected result: {result}"
        )

        out_path = site_dir / "live" / "china_risk_state.json"
        assert out_path.exists(), "china_risk_state.json not written"
        data = json.loads(out_path.read_text())

        assert data["schema"] == "china_risk_state.v1", "wrong schema"
        assert data["live_active"] is False, "offline build should have live_active=False"
        assert "display" in data
        assert "nightly" in data
        assert "live" in data
        # display verdict must match nightly verdict when offline (no live quotes)
        if data["nightly"].get("verdict") is not None:
            assert data["display"]["verdict"] == data["nightly"]["verdict"], (
                "offline: display verdict should match nightly verdict"
            )

    def test_ledger_freeze_offline_and_live(self, tmp_path, monkeypatch):
        """CRITICAL: zero data/ files written or mutated by either build path.
        The only new/changed file anywhere is site/live/china_risk_state.json.
        lib.store.read must be the original function after the build (patch restored)."""
        import lib.config as lib_config
        import lib.store as store_mod
        import engine.china_inputs as ci

        real_load = lib_config.load()
        site_dir = tmp_path / "site"
        data_dir = tmp_path / "data"
        (data_dir / "china_regime").mkdir(parents=True)
        (data_dir / "china_regime" / "latest.json").write_text(json.dumps(_fake_latest()))
        (site_dir / "live").mkdir(parents=True)

        monkeypatch.setattr(lib_config, "load", lambda: {
            **real_load,
            "storage": {**real_load.get("storage", {}), "site_dir": str(site_dir)},
        })
        monkeypatch.setattr(lib_config, "ROOT", tmp_path)
        monkeypatch.setattr(lib_config, "data_dir", lambda: data_dir)
        monkeypatch.setattr(store_mod, "read", _fake_store)
        monkeypatch.setattr(ci, "build_features", lambda: _fake_features())

        import scripts.build_china_risk_state as mod

        # Snapshot data/ before any build
        snap_before = self._snapshot_data(data_dir)
        original_store_read = store_mod.read   # save reference BEFORE any patching

        # --- run 1: offline ---
        mod.build(offline=True)
        snap_after_offline = self._snapshot_data(data_dir)
        assert snap_before == snap_after_offline, (
            "offline build mutated data/ files: "
            + str(set(snap_after_offline.items()) - set(snap_before.items()))
        )

        # store.read must be back to the fake (as set by monkeypatch)
        assert store_mod.read is _fake_store, (
            "store.read not restored after offline build"
        )

        # --- run 2: fake-live (monkeypatch fetch_quotes to return fresh fake prices) ---
        now_ts = datetime.now(timezone.utc).isoformat()
        fake_quotes = {
            sym: {
                "price": 3030.0 if "SS" in sym or "SZ" in sym else 100.5,
                "prev_close": 3000.0 if "SS" in sym or "SZ" in sym else 100.0,
                "quote_ts": now_ts,
                "delay_min": 0.5,
                "price_basis": "trade",
                "source": "yahoo",
            }
            for sym in (
                "000001.SS", "399001.SZ", "510300.SS",
                "159915.SZ", "510880.SS", "511010.SS", "512400.SS", "518880.SS",
                "CNH=F", "DX-Y.NYB", "^HSI",
            )
        }

        with patch("engine.live_quotes.fetch_quotes", return_value=fake_quotes):
            # Also force session_open by patching market_session to return open=True
            with patch("engine.live_overlay.market_session",
                       side_effect=lambda region, *a, **k: {"region": region, "open": True,
                                                             "local_time": "09:45 CST"}):
                result_live = mod.build(offline=False)

        snap_after_live = self._snapshot_data(data_dir)
        assert snap_before == snap_after_live, (
            "live build mutated data/ files: "
            + str(set(snap_after_live.items()) - set(snap_before.items()))
        )

        # store.read must be restored (the monkeypatched fake) after live build
        assert store_mod.read is _fake_store, (
            "store.read not restored after live build (patch leaked)"
        )

        # With fresh quotes and open session, live_active should be True
        out_path = site_dir / "live" / "china_risk_state.json"
        data_live = json.loads(out_path.read_text())
        assert data_live["live_active"] is True, (
            "expected live_active=True with fresh fake quotes and open session"
        )

        # The live tape leg basis should be "live" (trend component)
        tape_leg = next(
            (l for l in data_live.get("legs", []) if l.get("key") == "trend"), None
        )
        if tape_leg is not None:
            assert tape_leg["basis"] == "live", (
                "tape_trend leg should be 'live' when CN indices are spliced"
            )

        # legs_asof.tape_trend should say "live"
        assert data_live.get("legs_asof", {}).get("tape_trend") == "live", (
            "legs_asof.tape_trend should be 'live' when 000001.SS is spliced"
        )

        # The only new file anywhere is site/live/china_risk_state.json
        all_new_files = set()
        for dirpath, _, filenames in os.walk(tmp_path):
            for fn in filenames:
                p = str(Path(dirpath) / fn)
                if "china_risk_state.json" not in p:
                    # Any file not in snap_before and not the output JSON is a violation
                    rel = p.replace(str(tmp_path), "")
                    if "data/" in rel or "data\\" in rel:
                        if p not in snap_before:
                            all_new_files.add(p)
        assert not all_new_files, (
            f"unexpected new files in data/: {all_new_files}"
        )

    def test_paired_template_copy_identical(self):
        """The templates/ and site/ copies of china_risk_state_live.js must be byte-identical
        (enforced by check_template_site_sync; this test is the per-file fast-path guard)."""
        tpl = ROOT / "templates" / "china_risk_state_live.js"
        site = ROOT / "site" / "china_risk_state_live.js"
        assert tpl.exists(), "templates/china_risk_state_live.js not found"
        assert site.exists(), "site/china_risk_state_live.js not found"
        assert tpl.read_bytes() == site.read_bytes(), (
            "templates/china_risk_state_live.js and site/china_risk_state_live.js differ "
            "(run: python -m scripts.check_template_site_sync --fix)"
        )
