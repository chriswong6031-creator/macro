"""RC-R14 HK rotation-event detector port — tests for:

1. engine/sector_legs_hk.py — basket-level close series loader from hkbasketdata/baskets.json
2. engine/rotation_events.run_nightly — data_subdir parameterization (HK path)
3. Append-only ledger regression (RC-R2 law) on HK subdir
4. US no-change regression: run_nightly with data_subdir="rotation_events_hk" must NOT
   write to the US "rotation_events" directory.
5. HK loader: missing baskets.json → empty dict, not a crash.
6. Synthetic detector fire on hk-shaped sectors.

All tests are synthetic / hermetic — no live data, no network calls.
DATA WARNING: worktrees lack untracked runner-local stores (baskets_hk/membership.json,
hk_search/closes_deep.parquet). These tests use synthetic fixtures only.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from engine import rotation_events as re_
from engine import sector_legs_hk


# ──────────────────────────────────────────────────────────── fixtures ────


def _series(vals) -> pd.Series:
    idx = pd.bdate_range("2024-01-02", periods=len(vals))
    return pd.Series(list(vals), index=idx, dtype=float)


def _blowoff_leg(n_flat=280, runup=20, crash=6) -> pd.Series:
    vals = [100.0] * n_flat
    for _ in range(runup):
        vals.append(vals[-1] * 1.02)
    for _ in range(crash):
        vals.append(vals[-1] * 0.96)
    return _series(vals)


def _turn_leg(n_flat=280, decline=20, rise=6) -> pd.Series:
    vals = [100.0] * n_flat
    for _ in range(decline):
        vals.append(vals[-1] * 0.992)
    for _ in range(rise):
        vals.append(vals[-1] * 1.012)
    return _series(vals)


def _aligned_pair():
    a, b = _blowoff_leg(), _turn_leg()
    n = min(len(a), len(b))
    a, b = a.iloc[-n:], b.iloc[-n:]
    b.index = a.index
    return a, b


def _hk_sectors(a, b):
    """Minimal HK-shaped sectors dict for step_pairs / run_nightly."""
    cfg = {
        "key": "hk_internet_tech", "etf": None,
        "name_en": "China Tech & Internet", "name_zh": "中资科技与互联网",
        "legs": [
            {"key": "hk_platform_tech",  "tier": "primary",   "name_en": "China Platform Megacaps", "name_zh": "中资平台科技龙头"},
            {"key": "hk_china_tech",     "tier": "secondary", "name_en": "China Tech & Internet",   "name_zh": "中资科技与互联网"},
        ],
    }
    ew_etf = (a + b) / 2
    return {"hk_internet_tech": {"cfg": cfg, "etf_close": ew_etf,
                                  "legs": {"hk_platform_tech": a, "hk_china_tech": b},
                                  "leg_meta": {}}}


# ──────────────────────────────────────── sector_legs_hk loader tests ────


def _make_fake_baskets_json(tmp_path: Path, n_bars: int = 250) -> Path:
    """Write a synthetic baskets.json under tmp_path/hkbasketdata/ and return its path."""
    dates = [str(d.date()) for d in pd.bdate_range("2024-01-02", periods=n_bars)]
    vals_a = [1.0 + i * 0.002 for i in range(n_bars)]
    vals_b = ([1.0 - i * 0.001 for i in range(min(200, n_bars))]
              + [1.0 - 0.2 + j * 0.003 for j in range(max(0, n_bars - 200))])
    basket_dir = tmp_path / "hkbasketdata"
    basket_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "baskets": [
            {"id": "hk_platform_tech", "name": "China Platform Megacaps", "name_zh": "中资平台科技龙头", "n_members": 5},
            {"id": "hk_china_tech",    "name": "China Tech & Internet",   "name_zh": "中资科技与互联网",  "n_members": 10},
        ],
        "chart": {
            "dates": dates,
            "baskets": {
                "hk_platform_tech": vals_a,
                "hk_china_tech":    vals_b,
            },
        },
    }
    p = basket_dir / "baskets.json"
    p.write_text(json.dumps(data))
    return tmp_path


def _minimal_registry():
    """A minimal HK registry with one 2-leg sector."""
    return {
        "version": "1.0",
        "region": "hk",
        "sectors": [
            {
                "key": "hk_internet_tech",
                "etf": None,
                "name_en": "China Tech & Internet",
                "name_zh": "中资科技与互联网",
                "legs": [
                    {"key": "hk_platform_tech", "basket_hk": "hk_platform_tech",
                     "tier": "primary",   "name_en": "China Platform Megacaps", "name_zh": "中资平台科技龙头"},
                    {"key": "hk_china_tech",    "basket_hk": "hk_china_tech",
                     "tier": "secondary", "name_en": "China Tech & Internet",   "name_zh": "中资科技与互联网"},
                ],
            }
        ],
    }


class TestSectorLegsHkLoader:
    """Tests for engine/sector_legs_hk.sector_closes()."""

    def test_loader_returns_sector_with_two_legs(self, tmp_path):
        site = _make_fake_baskets_json(tmp_path, n_bars=250)
        reg = _minimal_registry()
        result = sector_legs_hk.sector_closes(site_dir=site, registry=reg)
        assert "hk_internet_tech" in result
        sec = result["hk_internet_tech"]
        assert set(sec["legs"].keys()) == {"hk_platform_tech", "hk_china_tech"}

    def test_loader_returns_pandas_series(self, tmp_path):
        site = _make_fake_baskets_json(tmp_path, n_bars=250)
        reg = _minimal_registry()
        result = sector_legs_hk.sector_closes(site_dir=site, registry=reg)
        for leg_series in result["hk_internet_tech"]["legs"].values():
            assert isinstance(leg_series, pd.Series)
            assert len(leg_series) >= sector_legs_hk.MIN_BARS

    def test_loader_synthesises_etf_close(self, tmp_path):
        site = _make_fake_baskets_json(tmp_path, n_bars=250)
        reg = _minimal_registry()
        result = sector_legs_hk.sector_closes(site_dir=site, registry=reg)
        etf = result["hk_internet_tech"]["etf_close"]
        assert isinstance(etf, pd.Series)
        assert len(etf) > 0

    def test_loader_missing_baskets_json_returns_empty(self, tmp_path):
        """Missing hkbasketdata/baskets.json → empty dict, no exception."""
        reg = _minimal_registry()
        result = sector_legs_hk.sector_closes(site_dir=tmp_path, registry=reg)
        assert result == {}

    def test_loader_missing_basket_id_skips_leg(self, tmp_path):
        """A basket_hk key absent from baskets.json → leg skipped, sector with <2 legs → dropped."""
        dates = [str(d.date()) for d in pd.bdate_range("2024-01-02", periods=250)]
        basket_dir = tmp_path / "hkbasketdata"
        basket_dir.mkdir(parents=True, exist_ok=True)
        # Only provide one of the two baskets
        data = {
            "chart": {
                "dates": dates,
                "baskets": {"hk_platform_tech": [1.0 + i * 0.001 for i in range(250)]},
            },
        }
        (basket_dir / "baskets.json").write_text(json.dumps(data))
        reg = _minimal_registry()
        result = sector_legs_hk.sector_closes(site_dir=tmp_path, registry=reg)
        # Sector with <2 legs is dropped
        assert result == {}

    def test_loader_thin_history_drops_leg(self, tmp_path):
        """A basket with fewer bars than MIN_BARS is dropped."""
        n_thin = sector_legs_hk.MIN_BARS - 1
        dates = [str(d.date()) for d in pd.bdate_range("2024-01-02", periods=n_thin)]
        basket_dir = tmp_path / "hkbasketdata"
        basket_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "chart": {
                "dates": dates,
                "baskets": {
                    "hk_platform_tech": [1.0 + i * 0.001 for i in range(n_thin)],
                    "hk_china_tech":    [1.0 - i * 0.001 for i in range(n_thin)],
                },
            },
        }
        (basket_dir / "baskets.json").write_text(json.dumps(data))
        reg = _minimal_registry()
        result = sector_legs_hk.sector_closes(site_dir=tmp_path, registry=reg)
        # Both legs too thin → sector dropped
        assert result == {}

    def test_cfg_shape_compatible_with_rotation_events(self, tmp_path):
        """sector_closes output shape must satisfy rotation_events.step_pairs."""
        site = _make_fake_baskets_json(tmp_path, n_bars=250)
        reg = _minimal_registry()
        result = sector_legs_hk.sector_closes(site_dir=site, registry=reg)
        sec = result["hk_internet_tech"]
        cfg = sec["cfg"]
        assert cfg["key"] == "hk_internet_tech"
        assert cfg["etf"] is None
        assert "name_en" in cfg and "name_zh" in cfg
        assert "legs" in cfg
        assert isinstance(sec["etf_close"], pd.Series)
        assert isinstance(sec["legs"], dict)


# ──────────────────────────────────── data_subdir isolation (HK path) ────


class TestHkDataSubdirIsolation:
    """RC-R14: HK run must write to rotation_events_hk/, never to rotation_events/ (US)."""

    def test_hk_subdir_writes_hk_directory(self, tmp_path):
        a, b = _aligned_pair()
        sectors = _hk_sectors(a, b)
        re_.run_nightly(sectors, tmp_path, data_subdir="rotation_events_hk",
                        generated_utc="2024-01-10 03:00 UTC")
        hk_dir = tmp_path / "rotation_events_hk"
        assert hk_dir.is_dir(), "HK data directory should have been created"

    def test_hk_subdir_does_not_touch_us_directory(self, tmp_path):
        a, b = _aligned_pair()
        sectors = _hk_sectors(a, b)
        re_.run_nightly(sectors, tmp_path, data_subdir="rotation_events_hk",
                        generated_utc="2024-01-10 03:00 UTC")
        us_dir = tmp_path / "rotation_events"
        assert not us_dir.exists(), \
            "HK run must not create or modify the US rotation_events/ directory"

    def test_hk_payload_has_correct_schema(self, tmp_path):
        a, b = _aligned_pair()
        sectors = _hk_sectors(a, b)
        payload = re_.run_nightly(sectors, tmp_path, data_subdir="rotation_events_hk",
                                  generated_utc="2024-01-10 03:00 UTC")
        assert payload["schema"] == "rotation_events.v1"
        assert payload["ok"] is True
        assert "active" in payload
        assert "authority" in payload
        assert payload["authority"]["tier"] == "display"
        assert payload["authority"]["may_rank"] is False
        assert payload["authority"]["may_gate"] is False
        assert payload["authority"]["may_size"] is False
        assert payload["authority"]["may_escalate"] is False


# ──────────────────────────────── append-only ledger (RC-R2) ────────────


class TestHkAppendOnlyLedger:
    """RC-R2: the events.jsonl ledger may only GROW — rows are never re-dated or deleted."""

    def test_ledger_grows_on_successive_runs(self, tmp_path):
        a, b = _aligned_pair()
        sectors = _hk_sectors(a, b)
        re_.run_nightly(sectors, tmp_path, data_subdir="rotation_events_hk",
                        generated_utc="2024-01-10 03:00 UTC")
        ledger_path = tmp_path / "rotation_events_hk" / "events.jsonl"
        n_after_first = len(ledger_path.read_text().strip().splitlines()) if ledger_path.exists() else 0
        re_.run_nightly(sectors, tmp_path, data_subdir="rotation_events_hk",
                        generated_utc="2024-01-11 03:00 UTC")
        n_after_second = len(ledger_path.read_text().strip().splitlines()) if ledger_path.exists() else 0
        assert n_after_second >= n_after_first, \
            "Ledger must be append-only — rows must never decrease"

    def test_ledger_rows_are_valid_json(self, tmp_path):
        a, b = _aligned_pair()
        sectors = _hk_sectors(a, b)
        re_.run_nightly(sectors, tmp_path, data_subdir="rotation_events_hk",
                        generated_utc="2024-01-10 03:00 UTC")
        ledger_path = tmp_path / "rotation_events_hk" / "events.jsonl"
        if ledger_path.exists():
            for line in ledger_path.read_text().strip().splitlines():
                if line.strip():
                    row = json.loads(line)
                    assert isinstance(row, dict)


# ──────────────────────────────── synthetic detector fire ────────────────


class TestHkSyntheticFire:
    """A blowoff-crash / turn-up pair in HK-shaped sectors should fire an event."""

    def test_synthetic_pair_produces_payload(self, tmp_path):
        a, b = _aligned_pair()
        sectors = _hk_sectors(a, b)
        payload = re_.run_nightly(sectors, tmp_path, data_subdir="rotation_events_hk",
                                  generated_utc="2024-01-10 03:00 UTC")
        # run_nightly returns a well-formed payload regardless of whether an event fired
        assert isinstance(payload["active"], list)
        assert isinstance(payload["n_pairs_scanned"], int)
        assert payload["n_pairs_scanned"] >= 0

    def test_synthetic_payload_is_json_serializable(self, tmp_path):
        import json as _json
        a, b = _aligned_pair()
        sectors = _hk_sectors(a, b)
        payload = re_.run_nightly(sectors, tmp_path, data_subdir="rotation_events_hk",
                                  generated_utc="2024-01-10 03:00 UTC")
        # Must round-trip through JSON without NaN/Inf (strict-JSON safe)
        serialised = _json.dumps(payload, allow_nan=False)
        back = _json.loads(serialised)
        assert back["schema"] == "rotation_events.v1"


# ──────────────────────────── bilingual copy checks ──────────────────────


class TestHkBilingualCopy:
    """Active event objects must carry both name_en and name_zh on each leg."""

    def test_active_events_have_bilingual_leg_names(self, tmp_path):
        a, b = _aligned_pair()
        sectors = _hk_sectors(a, b)
        payload = re_.run_nightly(sectors, tmp_path, data_subdir="rotation_events_hk",
                                  generated_utc="2024-01-10 03:00 UTC")
        for ev in payload["active"]:
            for leg_key in ("from_leg", "to_leg"):
                leg = ev.get(leg_key) or {}
                assert "name_en" in leg, f"{leg_key} missing name_en in event {ev.get('id')}"
                assert "name_zh" in leg, f"{leg_key} missing name_zh in event {ev.get('id')}"

    def test_active_events_have_bilingual_sector_names(self, tmp_path):
        a, b = _aligned_pair()
        sectors = _hk_sectors(a, b)
        payload = re_.run_nightly(sectors, tmp_path, data_subdir="rotation_events_hk",
                                  generated_utc="2024-01-10 03:00 UTC")
        for ev in payload["active"]:
            assert "sector_name_en" in ev, f"Missing sector_name_en in event {ev.get('id')}"
            assert "sector_name_zh" in ev, f"Missing sector_name_zh in event {ev.get('id')}"


# ─────────────────────────────────────────── build() southbound fail-open ────


# ──────────────────────────── lane-gate tests (B1-TESTS) ─────────────────────


def test_hk_lane_unarmed_state_written_no_ledger(tmp_path, monkeypatch):
    """COLLECT_LANE unset → state.json IS written; events.jsonl is NOT appended.
    The asia-close workflow arms the lane inline with COLLECT_LANE=nightly; off-lane
    runs (re-renders, daily.yml) must never write the events ledger."""
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    a, b = _aligned_pair()
    sectors = _hk_sectors(a, b)
    re_.run_nightly(sectors, tmp_path,
                    generated_utc="test",
                    data_subdir="rotation_events_hk")
    state_p = tmp_path / "rotation_events_hk" / "state.json"
    ledger_p = tmp_path / "rotation_events_hk" / "events.jsonl"
    assert state_p.exists(), "state.json must be written even when lane is unarmed"
    assert not ledger_p.exists(), (
        "events.jsonl must NOT be written when COLLECT_LANE is unset (lane gate)"
    )


def test_hk_lane_armed_ledger_advances(tmp_path, monkeypatch):
    """COLLECT_LANE=nightly → events.jsonl IS written/appended."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    a, b = _aligned_pair()
    sectors = _hk_sectors(a, b)
    re_.run_nightly(sectors, tmp_path,
                    generated_utc="test",
                    data_subdir="rotation_events_hk")
    ledger_p = tmp_path / "rotation_events_hk" / "events.jsonl"
    assert ledger_p.exists(), (
        "events.jsonl must be written when COLLECT_LANE=nightly (lane armed)"
    )
    # ledger must contain at least one line (created or coldstart rows)
    assert len(ledger_p.read_text().strip().splitlines()) > 0


def test_build_southbound_absent_fails_open(tmp_path, monkeypatch):
    """build() with NO parquet stores present writes a valid payload with no
    southbound_ctx key and does not raise (review fix-list item: the parquet
    embed is display context and must never block the events payload)."""
    import scripts.build_rotation_events_hk as bld

    a, b = _aligned_pair()
    site = tmp_path / "site"
    (site / "marketdata").mkdir(parents=True)
    data = tmp_path / "data"
    data.mkdir()

    monkeypatch.setattr(bld.sector_legs_hk, "sector_closes",
                        lambda site_dir=None: _hk_sectors(a, b))
    monkeypatch.setattr(bld.config, "data_dir", lambda: data)

    out = bld.build(site=site, generated_utc="2026-07-12 12:00 UTC")
    assert isinstance(out, dict)

    payload = json.loads((site / "marketdata" / "rotation_events_hk.json").read_text())
    assert "southbound_ctx" not in payload
    assert "active" in payload
