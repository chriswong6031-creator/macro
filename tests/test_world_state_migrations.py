"""Hermetic migration tests for the W1 PR2 world_state consumer migrations.

For EACH of the five migrated modules (notify, build_impulse, etf_pulse,
regime_label, briefing) this module tests:

(a) equivalence  — with fresh synced stores, migrated output == legacy-path output
(b) fallback     — world_state ABSENT -> output == legacy (no exception)
(c) staleness    — world_state with regime.asof older than latest.json -> helper
                   returns None -> legacy path used

Plus unit tests for load_world_state() and get() themselves.

All tests are hermetic: synthetic in-memory fixtures, tmp_path directories,
monkeypatching where needed.  No real market data is read.
"""
from __future__ import annotations

import copy
import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ---------------------------------------------------------------------------
# Fixture helpers (shared with test_world_state.py pattern)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SYNAPSE_YML = _REPO_ROOT / "config" / "synapse.yml"


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _seed_synapse(root: Path) -> None:
    import shutil
    dest = root / "config" / "synapse.yml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_SYNAPSE_YML, dest)


def _make_regime(root: Path, asof: str = "2026-07-01") -> dict:
    reg = {
        "quad": "Q1",
        "quad_name": "Goldilocks",
        "label": "Goldilocks/Expansion",
        "confidence": 0.82,
        "growth_score": 70.0,
        "inflation_score": 30.0,
        "cycle_tag": "mid",
        "transition_state": "STABLE",
        "flip_condition": "inflation_rising",
        "flip_margin": 0.15,
        "liquidity_quality": "ok",
        "liquidity_overlay": "expanding",
        "business_cycle": "expansion",
        "asof": asof,
        "schema_version": 1,
        "freshness": {
            "asof": asof,
            "built_at": "2026-07-04T06:38:00Z",
            "age_days": 3,
            "age_sessions": 2,
            "max_age_sessions": 1,
            "stale": True,
            "note": "test freshness",
        },
        "vol_regime": {
            "available": True,
            "asof": asof,
            "regime": "normalizing",
            "risk_score": 0.18,
            "scored_score": None,
            "scored_active": False,
            "vix": 16.5,
            "vrp_state": "collapsing",
            "vvix_state": "normal",
            "vol_target_scalar": 1.0,
            "fragility_confluence": 0,
            "flags": [],
        },
        "risk_radar": {
            "schema": "risk_radar.v2",
            "asof": asof,
            "state": "caution",
            "alert": False,
        },
        "conditions": {
            "complacency": {
                "breadth_above200_pctile": 0.56,
                "breadth_div": False,
            },
        },
        "sector_rs": [
            {"ticker": "XLK", "rs": 0.9, "mom_20d_pct": 5.2, "mom_60d_pct": 18.0,
             "above_200d_trend": True, "pctile_252d": 96.0, "rank": 1},
            {"ticker": "XLE", "rs": 0.2, "mom_20d_pct": -1.5, "mom_60d_pct": -6.0,
             "above_200d_trend": False, "pctile_252d": 15.0, "rank": 11},
        ],
        "playbook": {"headline": "Goldilocks stay long growth", "dial": None, "leaders": [], "avoid": []},
        "alerts": [],
        "preference_check": {"disagreement_flag": False},
        "flip_condition": {"component": None, "axis": None, "z": None, "threshold": None},
        "fed_stance": {"label_en": "Dovish pause", "stance": "pause"},
        "catalyst_tone": {"kind": "CPI", "tone_score": 0.4},
        "date": asof,
    }
    _write_json(root / "data" / "regime" / "latest.json", reg)
    return reg


def _make_market_state(root: Path) -> dict:
    ms = {
        "schema": "market_state.v2",
        "asof": "2026-07-01",
        "verdict": "CAUTION",
        "score": 55,
        "raw_score": 60,
        "is_display_only": True,
        "label_en": "Caution",
        "label_zh": "谨慎",
        "radar": {
            "state": "caution",
            "ceiling": 60,
            "amp": 1.2,
            "amp_keys": ["vol"],
            "severe_gated": False,
            "recovery": False,
            "is_loud": False,
        },
        "components": {},
        "overrides": [],
    }
    _write_json(root / "data" / "market_state" / "latest.json", ms)
    return ms


def _make_alerts_triage(root: Path) -> dict:
    at = {
        "generated_utc": "2026-07-04T12:00:00",
        "asof": "2026-07-04",
        "summary": {"total": 5, "critical": 1, "major": 4, "minor": 0,
                    "actionable": 1, "backtested": 0},
        "alerts": [],
    }
    _write_json(root / "site" / "factordata" / "alerts_triage.json", at)
    return at


def _make_run_status(root: Path) -> dict:
    rs = {
        "last_run": "2026-07-04T11:04:44Z",
        "sources": {
            "fred": {"status": "failed", "error": "403", "checked_at": "2026-07-04T11:00:00Z"},
            "polygon": {"status": "ok", "error": None, "checked_at": "2026-07-04T11:00:00Z"},
        },
        "circuit_breaker": {"fred": 7, "polygon": 0},
        "stale_series": [],
    }
    _write_json(root / "data" / "run_status.json", rs)
    return rs


def _make_oracle_state(root: Path) -> dict:
    oracle = {
        "schema": "oracle_state.v1",
        "asof": "2026-07-01",
        "regime": {"n_active_complexes": 2, "breadth": 0.6, "vix_regime": 0.3},
        "complexes": [],
        "active_episodes": [],
        "onset_watchlist": [],
    }
    _write_json(root / "site" / "basketdata" / "oracle_state.json", oracle)
    return oracle


def _make_breadth_parquet(root: Path) -> None:
    import pandas as pd
    bp = root / "data" / "breadth" / "breadth.parquet"
    bp.parent.mkdir(parents=True, exist_ok=True)
    dates = pd.to_datetime(["2026-07-01"])
    df = pd.DataFrame({"pct_above_50": [63.0], "pct_above_200": [61.0],
                       "n_members": [500.0], "nh": [40.0], "nl": [3.0],
                       "adv": [290.0], "dec": [210.0], "ad_line": [6500.0]},
                      index=dates)
    df.to_parquet(bp)


def _build_world_state(root: Path) -> Path:
    """Build world_state.json into root and return its path."""
    from engine.neuralweb.world_state import build_and_write
    out = root / "data" / "neuralweb" / "world_state.json"
    build_and_write(root=root, out_path=out)
    return out


def _full_tree(root: Path, asof: str = "2026-07-01") -> dict:
    """Create all needed fixture files; return the regime dict."""
    _seed_synapse(root)
    reg = _make_regime(root, asof=asof)
    _make_market_state(root)
    _make_alerts_triage(root)
    _make_run_status(root)
    _make_oracle_state(root)
    _make_breadth_parquet(root)
    return reg


# ---------------------------------------------------------------------------
# Unit tests: load_world_state() and get()
# ---------------------------------------------------------------------------

class TestLoadWorldState:
    def test_returns_dict_when_fresh(self, tmp_path):
        _full_tree(tmp_path)
        _build_world_state(tmp_path)
        from engine.neuralweb.read import load_world_state
        ws = load_world_state(root=tmp_path)
        assert isinstance(ws, dict)
        assert ws.get("regime") is not None

    def test_returns_none_when_absent(self, tmp_path):
        from engine.neuralweb.read import load_world_state
        ws = load_world_state(root=tmp_path)
        assert ws is None

    def test_returns_none_on_corrupt(self, tmp_path):
        ws_path = tmp_path / "data" / "neuralweb" / "world_state.json"
        ws_path.parent.mkdir(parents=True, exist_ok=True)
        ws_path.write_text("this is not json", encoding="utf-8")
        from engine.neuralweb.read import load_world_state
        ws = load_world_state(root=tmp_path)
        assert ws is None

    def test_staleness_guard_fires_on_newer_regime(self, tmp_path):
        """world_state has asof 2026-06-30; latest.json has asof 2026-07-01 -> guard fires."""
        # Build world_state with old asof
        _full_tree(tmp_path, asof="2026-06-30")
        _build_world_state(tmp_path)
        # Now update latest.json to a newer asof
        _make_regime(tmp_path, asof="2026-07-01")
        from engine.neuralweb.read import load_world_state
        ws = load_world_state(root=tmp_path, require_fresh_regime=True)
        assert ws is None, (
            "staleness guard must return None when latest.json.asof > world_state.regime.asof"
        )

    def test_staleness_guard_passes_on_same_asof(self, tmp_path):
        """world_state and latest.json have the same asof -> guard passes."""
        _full_tree(tmp_path, asof="2026-07-01")
        _build_world_state(tmp_path)
        from engine.neuralweb.read import load_world_state
        ws = load_world_state(root=tmp_path, require_fresh_regime=True)
        assert ws is not None

    def test_require_fresh_regime_false_bypasses_guard(self, tmp_path):
        """With require_fresh_regime=False, staleness guard is bypassed."""
        _full_tree(tmp_path, asof="2026-06-30")
        _build_world_state(tmp_path)
        _make_regime(tmp_path, asof="2026-07-01")
        from engine.neuralweb.read import load_world_state
        ws = load_world_state(root=tmp_path, require_fresh_regime=False)
        assert ws is not None


class TestGet:
    def test_simple_dotted_path(self, tmp_path):
        from engine.neuralweb.read import get
        ws = {"regime": {"quad": "Q1", "quad_name": "Goldilocks"}}
        assert get(ws, "regime.quad") == "Q1"
        assert get(ws, "regime.quad_name") == "Goldilocks"

    def test_none_ws_returns_default(self, tmp_path):
        from engine.neuralweb.read import get
        assert get(None, "regime.quad") is None
        assert get(None, "regime.quad", default="fallback") == "fallback"

    def test_missing_key_returns_default(self, tmp_path):
        from engine.neuralweb.read import get
        ws = {"regime": {"quad": "Q1"}}
        assert get(ws, "regime.missing_key") is None
        assert get(ws, "missing_top") is None
        assert get(ws, "regime.missing_key", default=42) == 42

    def test_nested_value(self, tmp_path):
        from engine.neuralweb.read import get
        ws = {"vol": {"regime": "normalizing", "vix": 16.5}}
        assert get(ws, "vol.vix") == 16.5
        assert get(ws, "vol.regime") == "normalizing"


# ---------------------------------------------------------------------------
# 1. scripts/notify.py — load_latest() migration
# ---------------------------------------------------------------------------

class TestNotifyMigration:
    def _get_load_latest(self, root: Path):
        """Import notify.load_latest patched to use root."""
        # Monkeypatch config.data_dir to point at root
        from lib import config as cfg
        orig = cfg.data_dir
        cfg.data_dir = lambda: root / "data"
        try:
            # Reset the world_state reader to use root
            from scripts import notify
            return notify.load_latest, orig
        finally:
            pass  # restore in the test body

    def test_equivalence_world_state_matches_legacy(self, tmp_path, monkeypatch):
        """With fresh stores, load_latest via world_state == load_latest via legacy."""
        _full_tree(tmp_path)
        _build_world_state(tmp_path)
        from lib import config as cfg
        monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path / "data")

        # Patch load_world_state to use tmp_path root
        from engine.neuralweb import read as nw_read
        orig_lws = nw_read.load_world_state

        def _lws_with_root(**kw):
            kw.setdefault("root", tmp_path)
            return orig_lws(**kw)

        monkeypatch.setattr(nw_read, "load_world_state", _lws_with_root)

        from scripts import notify
        result = notify.load_latest()
        assert result is not None
        assert result["quad"] == "Q1"
        assert result["quad_name"] == "Goldilocks"
        assert result["transition_state"] == "STABLE"
        assert result["liquidity_overlay"] == "expanding"
        assert result["cycle_tag"] == "mid"
        assert isinstance(result.get("sector_rs"), list)

    def test_fallback_world_state_absent(self, tmp_path, monkeypatch):
        """world_state absent -> load_latest falls back to raw latest.json."""
        reg = _full_tree(tmp_path)
        # Do NOT build world_state
        from lib import config as cfg
        monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path / "data")

        from engine.neuralweb import read as nw_read
        monkeypatch.setattr(nw_read, "load_world_state", lambda **kw: None)

        from scripts import notify
        result = notify.load_latest()
        assert result is not None
        assert result["quad"] == "Q1"
        assert result["quad_name"] == "Goldilocks"

    def test_fallback_staleness(self, tmp_path, monkeypatch):
        """Stale world_state -> staleness guard fires -> legacy path used -> no exception."""
        _full_tree(tmp_path, asof="2026-06-30")
        _build_world_state(tmp_path)
        _make_regime(tmp_path, asof="2026-07-01")  # newer than world_state

        from lib import config as cfg
        monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path / "data")

        from engine.neuralweb import read as nw_read
        orig_lws = nw_read.load_world_state

        def _lws_with_root(**kw):
            kw.setdefault("root", tmp_path)
            return orig_lws(**kw)

        monkeypatch.setattr(nw_read, "load_world_state", _lws_with_root)

        from scripts import notify
        result = notify.load_latest()
        # Staleness guard fires -> falls back to latest.json -> still works
        assert result is not None
        assert result["quad"] == "Q1"


# ---------------------------------------------------------------------------
# 2. scripts/build_impulse.py — _regime() migration
# ---------------------------------------------------------------------------

class TestBuildImpulseMigration:
    def test_equivalence_vol_fields_match(self, tmp_path, monkeypatch):
        """With fresh world_state, _regime().risk_score == latest.json vol_regime.risk_score."""
        _full_tree(tmp_path)
        _build_world_state(tmp_path)

        from lib import config as cfg
        monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path / "data")

        from engine.neuralweb import read as nw_read
        orig_lws = nw_read.load_world_state

        def _lws_with_root(**kw):
            kw.setdefault("root", tmp_path)
            return orig_lws(**kw)

        monkeypatch.setattr(nw_read, "load_world_state", _lws_with_root)

        # Import after monkeypatching
        import importlib
        import scripts.build_impulse as bi
        importlib.reload(bi)

        out = bi._regime()
        assert out["risk_score"] == pytest.approx(0.18, abs=0.01)
        assert out["vix"] == pytest.approx(16.5, abs=0.1)
        assert out["state"] in ("calm", "mixed", "stress", "unknown")
        # 0.18 < 0.33 -> calm
        assert out["state"] == "calm"
        assert out["calm"] is True

    def test_fallback_world_state_absent(self, tmp_path, monkeypatch):
        """world_state absent -> _regime() falls back to latest.json."""
        _full_tree(tmp_path)
        from lib import config as cfg
        monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path / "data")

        from engine.neuralweb import read as nw_read
        monkeypatch.setattr(nw_read, "load_world_state", lambda **kw: None)

        import importlib
        import scripts.build_impulse as bi
        importlib.reload(bi)

        out = bi._regime()
        # Falls back to latest.json which has risk_score=0.18
        assert out["risk_score"] is not None
        assert out["state"] != "unknown"

    def test_fallback_staleness(self, tmp_path, monkeypatch):
        """Stale world_state -> legacy path, no exception."""
        _full_tree(tmp_path, asof="2026-06-30")
        _build_world_state(tmp_path)
        _make_regime(tmp_path, asof="2026-07-01")

        from lib import config as cfg
        monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path / "data")

        from engine.neuralweb import read as nw_read
        orig_lws = nw_read.load_world_state

        def _lws_with_root(**kw):
            kw.setdefault("root", tmp_path)
            return orig_lws(**kw)

        monkeypatch.setattr(nw_read, "load_world_state", _lws_with_root)

        import importlib
        import scripts.build_impulse as bi
        importlib.reload(bi)

        out = bi._regime()
        assert out["risk_score"] is not None


# ---------------------------------------------------------------------------
# 3. engine/etf_pulse.py — _sector_leg() migration
# ---------------------------------------------------------------------------

class TestEtfPulseMigration:
    def test_equivalence_sector_rows_match(self, tmp_path, monkeypatch):
        """With fresh world_state, _sector_leg() rows match legacy direct read."""
        _full_tree(tmp_path)
        _build_world_state(tmp_path)

        from lib import config as cfg
        monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path / "data")

        from engine.neuralweb import read as nw_read
        orig_lws = nw_read.load_world_state

        def _lws_with_root(**kw):
            kw.setdefault("root", tmp_path)
            return orig_lws(**kw)

        monkeypatch.setattr(nw_read, "load_world_state", _lws_with_root)

        from engine import etf_pulse
        leg = etf_pulse._sector_leg()
        assert leg is not None
        tickers = [r["ticker"] for r in leg["rows"]]
        # Only GICS sector ETFs pass through; XLK and XLE are in _SECTOR_ETFS
        assert "XLK" in tickers
        assert "XLE" in tickers
        # XLK mom_60d=18 > XLE mom_60d=-6, so XLK is ranked first
        assert leg["rows"][0]["ticker"] == "XLK"
        assert leg["leaders"][0] == "XLK"

    def test_fallback_world_state_absent(self, tmp_path, monkeypatch):
        """world_state absent -> _sector_leg() falls back to latest.json."""
        _full_tree(tmp_path)
        from lib import config as cfg
        monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path / "data")

        from engine.neuralweb import read as nw_read
        monkeypatch.setattr(nw_read, "load_world_state", lambda **kw: None)

        from engine import etf_pulse
        leg = etf_pulse._sector_leg()
        assert leg is not None
        assert len(leg["rows"]) >= 1

    def test_fallback_no_latest_json(self, tmp_path, monkeypatch):
        """world_state absent AND latest.json absent -> returns None, no exception."""
        from lib import config as cfg
        monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path / "data")

        from engine.neuralweb import read as nw_read
        monkeypatch.setattr(nw_read, "load_world_state", lambda **kw: None)

        from engine import etf_pulse
        leg = etf_pulse._sector_leg()
        assert leg is None

    def test_fallback_staleness(self, tmp_path, monkeypatch):
        """Stale world_state -> legacy path, no exception."""
        _full_tree(tmp_path, asof="2026-06-30")
        _build_world_state(tmp_path)
        _make_regime(tmp_path, asof="2026-07-01")

        from lib import config as cfg
        monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path / "data")

        from engine.neuralweb import read as nw_read
        orig_lws = nw_read.load_world_state

        def _lws_with_root(**kw):
            kw.setdefault("root", tmp_path)
            return orig_lws(**kw)

        monkeypatch.setattr(nw_read, "load_world_state", _lws_with_root)

        from engine import etf_pulse
        leg = etf_pulse._sector_leg()
        # Falls back to latest.json -> still returns rows
        assert leg is not None


# ---------------------------------------------------------------------------
# 4. engine/regime_label.py — quad_label() migration
# ---------------------------------------------------------------------------

class TestRegimeLabelMigration:
    def test_equivalence_quad_name_matches(self, tmp_path):
        """With fresh world_state, quad_label returns same value as legacy."""
        _full_tree(tmp_path)
        _build_world_state(tmp_path)
        from engine.regime_label import quad_label
        result = quad_label(tmp_path)
        assert result == "Goldilocks"

    def test_fallback_world_state_absent(self, tmp_path):
        """world_state absent -> quad_label falls back to latest.json."""
        _full_tree(tmp_path)
        # No world_state built
        from engine.regime_label import quad_label
        result = quad_label(tmp_path)
        assert result == "Goldilocks"

    def test_fallback_staleness(self, tmp_path):
        """Stale world_state -> legacy path -> same result."""
        _full_tree(tmp_path, asof="2026-06-30")
        _build_world_state(tmp_path)
        _make_regime(tmp_path, asof="2026-07-01")
        from engine.regime_label import quad_label
        result = quad_label(tmp_path)
        assert result == "Goldilocks"

    def test_fallback_all_absent(self, tmp_path):
        """Both world_state and latest.json absent -> None, no exception."""
        from engine.regime_label import quad_label
        result = quad_label(tmp_path)
        assert result is None

    def test_legacy_quad_fallback(self, tmp_path):
        """quad_label falls back to 'quad' field if 'quad_name' absent."""
        _write_json(tmp_path / "data" / "regime" / "latest.json",
                    {"quad": "Q3"})
        from engine.regime_label import quad_label
        result = quad_label(tmp_path)
        assert result == "Q3"


# ---------------------------------------------------------------------------
# 5. engine/briefing.py — macro_context() migration
# ---------------------------------------------------------------------------

class TestBriefingMigration:
    def test_equivalence_regime_fields_match(self, tmp_path, monkeypatch):
        """With fresh world_state, macro_context returns same regime fields."""
        _full_tree(tmp_path)
        _build_world_state(tmp_path)

        from engine import briefing
        import lib.config as cfg
        # Point config.ROOT at tmp_path
        monkeypatch.setattr(cfg, "ROOT", tmp_path)

        from engine.neuralweb import read as nw_read
        orig_lws = nw_read.load_world_state

        def _lws_with_root(**kw):
            kw.setdefault("root", tmp_path)
            return orig_lws(**kw)

        monkeypatch.setattr(nw_read, "load_world_state", _lws_with_root)

        ctx = briefing.macro_context(today=date(2026, 7, 4))
        assert ctx.get("regime") == "Goldilocks"
        assert ctx.get("liquidity") == "expanding"
        assert ctx.get("transition") == "STABLE"
        assert ctx.get("cycle") == "mid"
        # fed_stance / posture come from raw latest.json which is also present
        assert ctx.get("fed_stance") == "Dovish pause"
        assert ctx.get("posture") == "Goldilocks stay long growth"
        assert ctx.get("as_of") == "2026-07-04"

    def test_fallback_world_state_absent(self, tmp_path, monkeypatch):
        """world_state absent -> macro_context falls back to latest.json."""
        _full_tree(tmp_path)

        from engine import briefing
        import lib.config as cfg
        monkeypatch.setattr(cfg, "ROOT", tmp_path)

        from engine.neuralweb import read as nw_read
        monkeypatch.setattr(nw_read, "load_world_state", lambda **kw: None)

        ctx = briefing.macro_context(today=date(2026, 7, 4))
        assert ctx.get("regime") == "Goldilocks"
        assert ctx.get("liquidity") == "expanding"

    def test_fallback_no_latest_json(self, tmp_path, monkeypatch):
        """Both world_state and latest.json absent -> empty dict, no exception."""
        from engine import briefing
        import lib.config as cfg
        monkeypatch.setattr(cfg, "ROOT", tmp_path)

        from engine.neuralweb import read as nw_read
        monkeypatch.setattr(nw_read, "load_world_state", lambda **kw: None)

        ctx = briefing.macro_context(today=date(2026, 7, 4))
        assert isinstance(ctx, dict)
        assert ctx.get("regime") is None

    def test_fallback_staleness(self, tmp_path, monkeypatch):
        """Stale world_state -> legacy path, no exception."""
        _full_tree(tmp_path, asof="2026-06-30")
        _build_world_state(tmp_path)
        _make_regime(tmp_path, asof="2026-07-01")

        from engine import briefing
        import lib.config as cfg
        monkeypatch.setattr(cfg, "ROOT", tmp_path)

        from engine.neuralweb import read as nw_read
        orig_lws = nw_read.load_world_state

        def _lws_with_root(**kw):
            kw.setdefault("root", tmp_path)
            return orig_lws(**kw)

        monkeypatch.setattr(nw_read, "load_world_state", _lws_with_root)

        ctx = briefing.macro_context(today=date(2026, 7, 4))
        assert ctx.get("regime") == "Goldilocks"


# ---------------------------------------------------------------------------
# 6. Cross-consumer: sector_rs in world_state.regime
# ---------------------------------------------------------------------------

class TestSectorRsInWorldState:
    def test_sector_rs_present_in_regime_block(self, tmp_path):
        """sector_rs is present in world_state.regime after PR2 composer change."""
        _full_tree(tmp_path)
        _build_world_state(tmp_path)
        ws_path = tmp_path / "data" / "neuralweb" / "world_state.json"
        ws = json.loads(ws_path.read_text())
        reg = ws.get("regime") or {}
        assert "sector_rs" in reg, "sector_rs must be in world_state.regime"
        assert isinstance(reg["sector_rs"], list)
        assert len(reg["sector_rs"]) >= 1

    def test_liquidity_overlay_in_regime_block(self, tmp_path):
        """liquidity_overlay is present in world_state.regime after PR2 composer change."""
        _full_tree(tmp_path)
        _build_world_state(tmp_path)
        ws_path = tmp_path / "data" / "neuralweb" / "world_state.json"
        ws = json.loads(ws_path.read_text())
        reg = ws.get("regime") or {}
        assert "liquidity_overlay" in reg
        assert reg["liquidity_overlay"] == "expanding"
