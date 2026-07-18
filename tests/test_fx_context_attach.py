"""MSX-1 consumer lane — tests for:
  1. lib/forex_link new helpers (dollar_lean, state_changes, stress_radar)
  2. lib/forex_link.attach_fx_context — the real shared helper (not a mirror)

Run: python3 -m pytest tests/test_fx_context_attach.py -x -q
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Minimal latest.json fixture that covers all keys consumed by the attach logic
# ---------------------------------------------------------------------------
MINIMAL_LATEST = {
    "asof": "2026-07-17",
    "date": "Jul 17, 2026",
    "dollar_desk": {
        "lean": "soft",
        "lean_zh": "偏软",
        "triple_red": False,
        "trend": "down",
        "liquidity_dir": "contracting",
        "fed_path_lean": "dovish",
    },
    "transmission": {
        "usd_dir": "weakening",
        "corr": {"GC=F": -0.42},
        "unstable": [],
        "headwind_for": [],
        "tailwind_for": [],
    },
    "regime_radar": {
        "as_of": "2026-07-17",
        "dominant": None,
        "active": [],
        "intensity": {
            "carry_unwind": 8.0,
            "dollar_wrecking_ball": 12.5,
            "em_crisis_capital_flight": 3.2,
            "haven_flight_risk_off": 0.0,
            "reflation_risk_on": 0.0,
            "intervention_risk": 0.0,
        },
    },
    "pairs": {
        "USDCNH": {
            "label": "USD/CNH",
            "quote": 7.24,
            "chg": 0.01,
            "action": "watch",
            "score": 45,
            # MSX-1 additions (producer lane — may be absent in pre-nightly builds)
            "cnh_basis_bps": -32.5,
            "cnh_basis_state": "neutral",
        },
        "EURUSD": {"label": "EUR/USD", "quote": 1.085, "chg": -0.003, "action": "hold", "score": 50},
    },
    "state_changes": {
        "smile_regime": {"current": "mixed", "prev": "risk-off", "changed_on": "2026-07-10", "days_in_state": 7},
        "lean": {"current": "soft", "prev": "mixed", "changed_on": "2026-07-15", "days_in_state": 2},
    },
}

# STALE fixture: forex asof < page date (e.g. forex from yesterday, page for today)
STALE_LATEST = {
    **MINIMAL_LATEST,
    "asof": "2026-07-16",  # one day behind the page's 07-17
}


@pytest.fixture()
def latest_json(tmp_path) -> Path:
    """Write MINIMAL_LATEST to a tmp dir and return the path."""
    p = tmp_path / "forex" / "latest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(MINIMAL_LATEST))
    return p


@pytest.fixture()
def stale_latest_json(tmp_path) -> Path:
    p = tmp_path / "forex" / "latest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(STALE_LATEST))
    return p


# ---------------------------------------------------------------------------
# 1. lib/forex_link — new helpers
# ---------------------------------------------------------------------------
class TestDollarLean:
    def test_returns_desk_block_with_usd_dir(self, monkeypatch, latest_json):
        from lib import config, forex_link
        monkeypatch.setattr(config, "data_dir", lambda: latest_json.parent.parent)
        # clear cached module state by calling _latest directly
        blk = forex_link.dollar_lean()
        assert blk is not None
        assert blk["lean"] == "soft"
        assert blk["usd_dir"] == "weakening"   # merged from transmission
        assert blk["triple_red"] is False

    def test_returns_none_when_file_absent(self, monkeypatch, tmp_path):
        from lib import config, forex_link
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path / "nonexistent")
        assert forex_link.dollar_lean() is None

    def test_accepts_preloaded_dict(self):
        from lib import forex_link
        blk = forex_link.dollar_lean(fx=MINIMAL_LATEST)
        assert blk is not None
        assert blk["usd_dir"] == "weakening"

    def test_returns_none_when_dollar_desk_absent(self):
        from lib import forex_link
        assert forex_link.dollar_lean(fx={}) is None
        assert forex_link.dollar_lean(fx={"pairs": {}}) is None


class TestStateChanges:
    def test_returns_state_changes_block(self, monkeypatch, latest_json):
        from lib import config, forex_link
        monkeypatch.setattr(config, "data_dir", lambda: latest_json.parent.parent)
        sc = forex_link.state_changes()
        assert sc is not None
        assert "smile_regime" in sc
        assert sc["lean"]["current"] == "soft"

    def test_returns_none_when_absent(self):
        from lib import forex_link
        assert forex_link.state_changes(fx={}) is None
        assert forex_link.state_changes(fx={"dollar_desk": {}}) is None

    def test_accepts_preloaded_dict(self):
        from lib import forex_link
        sc = forex_link.state_changes(fx=MINIMAL_LATEST)
        assert sc is not None and "lean" in sc


class TestStressRadar:
    def test_returns_regime_radar_block(self, monkeypatch, latest_json):
        from lib import config, forex_link
        monkeypatch.setattr(config, "data_dir", lambda: latest_json.parent.parent)
        rr = forex_link.stress_radar()
        assert rr is not None
        assert rr["as_of"] == "2026-07-17"
        assert rr["intensity"]["dollar_wrecking_ball"] == 12.5

    def test_returns_none_when_absent(self):
        from lib import forex_link
        assert forex_link.stress_radar(fx={}) is None

    def test_scenarios_key_optional(self):
        """Pre-MSX-1 shape (no scenarios key) must degrade silently."""
        from lib import forex_link
        rr = forex_link.stress_radar(fx=MINIMAL_LATEST)
        # scenarios not yet in fixture — caller must use .get()
        assert rr.get("scenarios") is None  # absent = None, not KeyError


class TestLatestHelper:
    def test_parses_file(self, monkeypatch, latest_json):
        from lib import config, forex_link
        monkeypatch.setattr(config, "data_dir", lambda: latest_json.parent.parent)
        d = forex_link._latest()
        assert d.get("asof") == "2026-07-17"

    def test_returns_empty_dict_when_file_absent(self, monkeypatch, tmp_path):
        from lib import config, forex_link
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path / "nowhere")
        assert forex_link._latest() == {}

    def test_returns_empty_dict_on_malformed_json(self, monkeypatch, tmp_path):
        from lib import config, forex_link
        p = tmp_path / "forex" / "latest.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{bad json")
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        assert forex_link._latest() == {}


# ---------------------------------------------------------------------------
# 2. attach_fx_context — exercises the REAL shared helper
# ---------------------------------------------------------------------------
def _make_rd() -> dict:
    """Minimal radar dict that market_state_snapshot would produce."""
    return {
        "state": "calm",
        "score": 20,
        "label_en": "Calm",
        "label_zh": "平静",
        "scares": [],
    }


class TestAttachFxContext:
    """All tests exercise lib.forex_link.attach_fx_context directly."""

    def test_attach_populates_expected_keys(self, monkeypatch, latest_json):
        from lib import config, forex_link
        monkeypatch.setattr(config, "data_dir", lambda: latest_json.parent.parent)
        rd = _make_rd()
        forex_link.attach_fx_context(rd, page_asof="2026-07-17")
        assert "fx_context" in rd
        fxc = rd["fx_context"]
        assert fxc["cnh_basis_bps"] == -32.5
        assert fxc["cnh_basis_state"] == "neutral"
        assert fxc["usd_dir"] == "weakening"
        assert fxc["as_of"] == "2026-07-17"
        assert fxc["stale"] is False

    def test_wrecking_ball_intensity_absent_from_payload(self, monkeypatch, latest_json):
        """wrecking_ball_intensity must not appear in the attach payload (rendered nowhere)."""
        from lib import config, forex_link
        monkeypatch.setattr(config, "data_dir", lambda: latest_json.parent.parent)
        rd = _make_rd()
        forex_link.attach_fx_context(rd, page_asof="2026-07-17")
        assert "wrecking_ball_intensity" not in rd.get("fx_context", {})

    def test_attach_absent_when_no_forex_data(self, monkeypatch, tmp_path):
        """When latest.json is absent, radar dict must be untouched."""
        from lib import config, forex_link
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path / "nonexistent")
        rd = _make_rd()
        forex_link.attach_fx_context(rd, page_asof="2026-07-17")
        assert "fx_context" not in rd

    def test_stale_flag_set_when_forex_asof_behind(self, monkeypatch, stale_latest_json):
        """forex asof (2026-07-16) < page asof (2026-07-17) → stale=True."""
        from lib import config, forex_link
        monkeypatch.setattr(config, "data_dir", lambda: stale_latest_json.parent.parent)
        rd = _make_rd()
        forex_link.attach_fx_context(rd, page_asof="2026-07-17")
        assert "fx_context" in rd
        fxc = rd["fx_context"]
        assert fxc["stale"] is True
        assert fxc["built_date"] == "2026-07-16"

    def test_not_stale_when_asof_equal(self, monkeypatch, latest_json):
        """forex asof == page asof → stale=False."""
        from lib import config, forex_link
        monkeypatch.setattr(config, "data_dir", lambda: latest_json.parent.parent)
        rd = _make_rd()
        forex_link.attach_fx_context(rd, page_asof="2026-07-17")
        assert rd["fx_context"]["stale"] is False
        assert "built_date" not in rd["fx_context"]

    def test_none_page_asof_no_stale_flag(self, monkeypatch, latest_json):
        """page_asof=None must not trigger stale=True (str(None) trap guard)."""
        from lib import config, forex_link
        monkeypatch.setattr(config, "data_dir", lambda: latest_json.parent.parent)
        rd = _make_rd()
        forex_link.attach_fx_context(rd, page_asof=None)
        # attach should succeed (data present) but stale must remain False
        assert "fx_context" in rd
        assert rd["fx_context"]["stale"] is False

    def test_empty_page_asof_no_stale_flag(self, monkeypatch, latest_json):
        """page_asof='' must not trigger stale=True."""
        from lib import config, forex_link
        monkeypatch.setattr(config, "data_dir", lambda: latest_json.parent.parent)
        rd = _make_rd()
        forex_link.attach_fx_context(rd, page_asof="")
        assert "fx_context" in rd
        assert rd["fx_context"]["stale"] is False

    def test_cnh_keys_absent_when_pair_missing(self, monkeypatch, tmp_path):
        """USDCNH pair absent → cnh_basis_bps/state are None, not KeyError."""
        from lib import config, forex_link
        payload = {**MINIMAL_LATEST, "pairs": {}}
        p = tmp_path / "forex" / "latest.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload))
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        rd = _make_rd()
        forex_link.attach_fx_context(rd, page_asof="2026-07-17")
        fxc = rd["fx_context"]
        assert fxc["cnh_basis_bps"] is None
        assert fxc["cnh_basis_state"] is None

    def test_cnh_basis_keys_absent_in_pair(self, monkeypatch, tmp_path):
        """Pre-MSX-1 USDCNH (no cnh_basis_* keys) → both None, other keys still populated."""
        from lib import config, forex_link
        payload = {
            **MINIMAL_LATEST,
            "pairs": {"USDCNH": {"label": "USD/CNH", "quote": 7.24}},
        }
        p = tmp_path / "forex" / "latest.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload))
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        rd = _make_rd()
        forex_link.attach_fx_context(rd, page_asof="2026-07-17")
        fxc = rd["fx_context"]
        assert fxc["cnh_basis_bps"] is None
        assert fxc["cnh_basis_state"] is None
        assert fxc["usd_dir"] == "weakening"

    def test_fail_open_no_exception_on_bad_data(self, monkeypatch, tmp_path):
        """Malformed payload must never raise — attach either succeeds or silently skips."""
        from lib import config, forex_link
        payload = {"dollar_desk": "not-a-dict", "transmission": None}
        p = tmp_path / "forex" / "latest.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload))
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        rd = _make_rd()
        try:
            forex_link.attach_fx_context(rd, page_asof="2026-07-17")
        except Exception as e:  # noqa: BLE001
            pytest.fail(f"attach raised unexpectedly: {e}")
