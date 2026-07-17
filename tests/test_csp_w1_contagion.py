"""tests/test_csp_w1_contagion.py — CSP-W1 hermetic unit tests.

Coverage:
  1.  compose_all_sources_present     — all sources present → correct fields
  2.  compose_all_missing             — all sources absent → fail-soft, no raise
  3.  compose_immature_only_logs      — forward logs present but < 5 prior rows
                                        → mature=False, still emitted in alert list
  4.  compose_mature_logs             — >= 5 prior rows → mature=True
  5.  compose_no_alert_logs           — alert=False rows excluded from intl list
  6.  compose_origin_complex_intact   — leadership state=INTACT → origin_complex=None
  7.  compose_origin_complex_broken   — leadership state=BROKEN → origin_complex="ai_hardware"
  8.  compose_display_only            — display_only=True always
  9.  compose_is_context_only         — is_context_only=True always
  10. block_contagion_null_when_absent — _block_contagion returns None when ws=None
  11. block_contagion_null_degraded    — _block_contagion returns None when all null
  12. block_contagion_present          — _block_contagion returns block when data present
  13. block_honesty_note               — honesty_note contains "accruing"
  14. dynamic_market_order_extra       — extra markets appear after core four, sorted
  15. dynamic_market_order_stable      — core four always first in correct order
  16. dynamic_market_order_missing_sc  — missing scorecard → falls back to core four only
  17. summarize_contagion_absent_ws    — _summarize_contagion when world_state absent
  18. summarize_contagion_present      — _summarize_contagion reads world_state.contagion_regime
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.neuralweb.world_state import _compose_contagion_regime
from engine.neuralweb.brief_context import _block_contagion
from engine.neuralweb.mastermind_context import (
    _summarize_contagion,
    _summarize_risk_radar_reliability,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _dc_payload(state: str = "SLIPPING") -> dict:
    return {
        "schema": "deterioration_cascade.v1",
        "asof": "2026-07-16",
        "state": state,
        "n_alert": 2,
        "n_escalating": 1,
        "d3_alert": 1,
        "n_mature": 3,
        "alerts": ["cn", "hk"],
        "immature": ["tw", "kr"],
    }


def _lc_payload(state: str = "BROKEN") -> dict:
    return {
        "schema": "leadership_crack.v1",
        "asof": "2026-07-15",
        "state": state,
        "z_vel": -0.74,
        "med_dd": -0.25,
        "state_since": "2026-07-07",
    }


def _ir_payload(two_tier_state: str = "contained") -> dict:
    return {
        "built": "2026-07-17T03:38:26Z",
        "two_tier": {
            "state": two_tier_state,
        },
    }


def _forward_log_row(asof: str, alert: bool, state: str = "watch") -> str:
    return json.dumps({
        "asof": asof,
        "market": "kr",
        "state": state,
        "alert": alert,
        "top_score": 59,
    })


def _seed_all_sources(root: Path, dc_state: str = "SLIPPING", lc_state: str = "BROKEN",
                      ir_two_tier: str = "contained") -> None:
    """Seed all three source artifacts into tmp root."""
    _write(root / "data" / "deterioration_cascade" / "latest.json", _dc_payload(dc_state))
    _write(root / "data" / "leadership_crack" / "latest.json", _lc_payload(lc_state))
    _write(root / "data" / "intl_risk" / "latest.json", _ir_payload(ir_two_tier))


# ---------------------------------------------------------------------------
# Tests: _compose_contagion_regime
# ---------------------------------------------------------------------------

class TestComposeContagionRegime:

    def test_all_sources_present(self, tmp_path):
        _seed_all_sources(tmp_path)
        # Add a mature intl forward log (>= 5 prior rows)
        fwd_dir = tmp_path / "data" / "risk_radar_intl"
        fwd_dir.mkdir(parents=True, exist_ok=True)
        rows = (
            # 5 prior rows with earlier asof
            _forward_log_row("2026-07-10", True) + "\n" +
            _forward_log_row("2026-07-11", True) + "\n" +
            _forward_log_row("2026-07-12", True) + "\n" +
            _forward_log_row("2026-07-13", True) + "\n" +
            _forward_log_row("2026-07-14", True) + "\n" +
            # last row (latest asof)
            _forward_log_row("2026-07-16", True) + "\n"
        )
        _write_text(fwd_dir / "kr_forward_log.jsonl", rows)

        result = _compose_contagion_regime(root=tmp_path)

        assert result["state"] == "SLIPPING"
        assert result["leadership_state"] == "BROKEN"
        assert result["origin_complex"] == "ai_hardware"
        assert result["us_spillover"] == "contained"
        assert result["n_alert"] == 2
        assert result["d3_alert"] == 1
        assert result["n_mature"] == 3
        assert result["asof"] == "2026-07-16"
        assert result["display_only"] is True
        assert result["is_context_only"] is True
        assert isinstance(result["immature"], list)
        assert isinstance(result["degraded"], list)
        # kr should appear in the alert list as mature
        markets = result["intl_markets_in_alert"]
        assert len(markets) == 1
        assert markets[0]["market"] == "kr"
        assert markets[0]["mature"] is True

    def test_all_missing(self, tmp_path):
        """All sources absent — fail-soft, no raise, all fields null."""
        result = _compose_contagion_regime(root=tmp_path)

        assert result["state"] is None
        assert result["leadership_state"] is None
        assert result["us_spillover"] is None
        assert result["origin_complex"] is None
        assert result["intl_markets_in_alert"] == []
        assert result["display_only"] is True
        assert len(result["degraded"]) >= 2  # at least dc + lc missing

    def test_immature_only_logs(self, tmp_path):
        """Forward log has < 5 prior rows — mature=False, still emitted."""
        _seed_all_sources(tmp_path)
        fwd_dir = tmp_path / "data" / "risk_radar_intl"
        fwd_dir.mkdir(parents=True, exist_ok=True)
        # Only 2 prior rows (< 5 threshold)
        rows = (
            _forward_log_row("2026-07-14", True) + "\n" +
            _forward_log_row("2026-07-15", True) + "\n" +
            _forward_log_row("2026-07-16", True) + "\n"
        )
        _write_text(fwd_dir / "kr_forward_log.jsonl", rows)

        result = _compose_contagion_regime(root=tmp_path)
        markets = result["intl_markets_in_alert"]
        assert len(markets) == 1
        assert markets[0]["mature"] is False

    def test_mature_logs(self, tmp_path):
        """Exactly 5 prior rows with earlier asof — mature=True."""
        _seed_all_sources(tmp_path)
        fwd_dir = tmp_path / "data" / "risk_radar_intl"
        fwd_dir.mkdir(parents=True, exist_ok=True)
        rows = "\n".join([
            _forward_log_row("2026-07-10", True),
            _forward_log_row("2026-07-11", True),
            _forward_log_row("2026-07-12", True),
            _forward_log_row("2026-07-13", True),
            _forward_log_row("2026-07-14", True),
            _forward_log_row("2026-07-16", True),  # latest
        ]) + "\n"
        _write_text(fwd_dir / "kr_forward_log.jsonl", rows)

        result = _compose_contagion_regime(root=tmp_path)
        markets = result["intl_markets_in_alert"]
        assert len(markets) == 1
        assert markets[0]["mature"] is True

    def test_no_alert_logs_excluded(self, tmp_path):
        """Markets with alert=False in last row are excluded from intl list."""
        _seed_all_sources(tmp_path)
        fwd_dir = tmp_path / "data" / "risk_radar_intl"
        fwd_dir.mkdir(parents=True, exist_ok=True)
        rows = (
            _forward_log_row("2026-07-14", False) + "\n" +
            _forward_log_row("2026-07-16", False) + "\n"  # alert=False
        )
        _write_text(fwd_dir / "kr_forward_log.jsonl", rows)

        result = _compose_contagion_regime(root=tmp_path)
        assert result["intl_markets_in_alert"] == []

    def test_origin_complex_intact(self, tmp_path):
        """Leadership state=INTACT → origin_complex=None."""
        _seed_all_sources(tmp_path, lc_state="INTACT")
        result = _compose_contagion_regime(root=tmp_path)
        assert result["origin_complex"] is None

    def test_origin_complex_broken(self, tmp_path):
        """Leadership state=BROKEN → origin_complex='ai_hardware'."""
        _seed_all_sources(tmp_path, lc_state="BROKEN")
        result = _compose_contagion_regime(root=tmp_path)
        assert result["origin_complex"] == "ai_hardware"

    def test_origin_complex_cracking(self, tmp_path):
        """Leadership state=CRACKING (not INTACT) → origin_complex='ai_hardware'."""
        _seed_all_sources(tmp_path, lc_state="CRACKING")
        result = _compose_contagion_regime(root=tmp_path)
        assert result["origin_complex"] == "ai_hardware"

    def test_display_only_always_true(self, tmp_path):
        """display_only=True even when all sources missing."""
        result = _compose_contagion_regime(root=tmp_path)
        assert result.get("display_only") is True

    def test_is_context_only_always_true(self, tmp_path):
        """is_context_only=True even when all sources missing."""
        result = _compose_contagion_regime(root=tmp_path)
        assert result.get("is_context_only") is True


# ---------------------------------------------------------------------------
# Tests: _block_contagion (brief_context)
# ---------------------------------------------------------------------------

class TestBlockContagion:

    def _ws_with_contagion(self, state: str = "SLIPPING",
                           leadership_state: str = "BROKEN") -> dict:
        return {
            "contagion_regime": {
                "state": state,
                "origin_complex": "ai_hardware" if leadership_state != "INTACT" else None,
                "intl_markets_in_alert": [{"market": "kr", "mature": True}],
                "leadership_state": leadership_state,
                "leadership_detail": {"z_vel": -0.74, "med_dd": -0.25},
                "n_alert": 2,
                "d3_alert": 1,
                "n_mature": 3,
                "immature": ["tw"],
                "us_spillover": "contained",
                "asof": "2026-07-16",
                "degraded": [],
                "display_only": True,
                "is_context_only": True,
            }
        }

    def test_null_when_ws_none(self):
        """_block_contagion returns None when ws=None."""
        assert _block_contagion(None) is None

    def test_null_when_all_null(self):
        """_block_contagion returns None when state/leadership/spillover all null."""
        ws = {
            "contagion_regime": {
                "state": None,
                "leadership_state": None,
                "us_spillover": None,
                "intl_markets_in_alert": [],
                "display_only": True,
            }
        }
        assert _block_contagion(ws) is None

    def test_present_when_state_available(self):
        """_block_contagion returns a block when state is non-null."""
        ws = self._ws_with_contagion()
        block = _block_contagion(ws)
        assert block is not None
        assert block["state"] == "SLIPPING"
        assert block["leadership_state"] == "BROKEN"
        assert block["us_spillover"] == "contained"

    def test_honesty_note_present(self):
        """honesty_note contains 'accruing' per #2752 chip idiom."""
        ws = self._ws_with_contagion()
        block = _block_contagion(ws)
        assert block is not None
        assert "accruing" in block.get("honesty_note", "")

    def test_display_only_true(self):
        ws = self._ws_with_contagion()
        block = _block_contagion(ws)
        assert block is not None
        assert block.get("display_only") is True

    def test_is_context_only_true(self):
        ws = self._ws_with_contagion()
        block = _block_contagion(ws)
        assert block is not None
        assert block.get("is_context_only") is True

    def test_markets_compact(self):
        """intl_markets_in_alert is present with market + mature keys."""
        ws = self._ws_with_contagion()
        block = _block_contagion(ws)
        assert block is not None
        markets = block.get("intl_markets_in_alert", [])
        assert len(markets) == 1
        assert markets[0]["market"] == "kr"
        assert markets[0]["mature"] is True


# ---------------------------------------------------------------------------
# Tests: dynamic market order in _summarize_risk_radar_reliability
# ---------------------------------------------------------------------------

class TestDynamicMarketOrder:

    def _scorecard(self, extra_markets: list[str] | None = None) -> dict:
        """Build a minimal scorecard with core four + optional extras."""
        markets: dict = {}
        for mkt in ("us", "cn", "hk", "ca") + tuple(extra_markets or []):
            markets[mkt] = {
                "monitoring": {"log_fresh": True, "latest_asof": "2026-07-16"},
                "alerts": {"n_alerts": 5, "n_graded": 5, "n_ungraded": 0},
                "precision": {"hit_rate": 0.8, "n": 5},
                "graded_rows": [],
            }
        return {
            "schema": "risk_radar_scorecard.v1",
            "generated_at": "2026-07-17T00:00:00Z",
            "markets": markets,
        }

    def test_extra_markets_appear(self, tmp_path):
        """Extra markets from scorecard appear after core four."""
        sc = self._scorecard(extra_markets=["kr", "jp", "tw"])
        sc_path = tmp_path / "site" / "riskdata" / "scorecard.json"
        _write(sc_path, sc)

        lobe, gap = _summarize_risk_radar_reliability(tmp_path)
        assert gap is None
        market_keys = list(lobe["markets"].keys())
        # Core four must be first
        assert market_keys[:4] == ["us", "cn", "hk", "ca"]
        # Extra markets sorted alphabetically
        extra = market_keys[4:]
        assert extra == sorted(extra)
        assert set(extra) == {"jp", "kr", "tw"}

    def test_order_stable_with_no_extra(self, tmp_path):
        """No extra markets — order is exactly us/cn/hk/ca."""
        sc = self._scorecard()
        sc_path = tmp_path / "site" / "riskdata" / "scorecard.json"
        _write(sc_path, sc)

        lobe, gap = _summarize_risk_radar_reliability(tmp_path)
        assert gap is None
        assert list(lobe["markets"].keys()) == ["us", "cn", "hk", "ca"]

    def test_missing_scorecard_gap(self, tmp_path):
        """Missing scorecard → fail-soft with gap note, empty lobe."""
        lobe, gap = _summarize_risk_radar_reliability(tmp_path)
        assert lobe == {}
        assert gap is not None
        assert "absent" in gap.lower() or "unreadable" in gap.lower()

    def test_core_four_present_even_if_extra(self, tmp_path):
        """All 11 markets — core four first, then 7 extras sorted."""
        all_markets = ["us", "cn", "hk", "ca", "kr", "jp", "tw", "in", "au", "gb", "ez"]
        sc = self._scorecard(extra_markets=[m for m in all_markets if m not in ("us", "cn", "hk", "ca")])
        sc_path = tmp_path / "site" / "riskdata" / "scorecard.json"
        _write(sc_path, sc)

        lobe, gap = _summarize_risk_radar_reliability(tmp_path)
        keys = list(lobe["markets"].keys())
        assert keys[:4] == ["us", "cn", "hk", "ca"]
        assert keys[4:] == sorted(["kr", "jp", "tw", "in", "au", "gb", "ez"])


# ---------------------------------------------------------------------------
# Tests: _summarize_contagion (mastermind_context)
# ---------------------------------------------------------------------------

class TestSummarizeContagion:

    def _world_state_with_contagion(self, state: str = "SLIPPING") -> dict:
        return {
            "contagion_regime": {
                "state": state,
                "origin_complex": "ai_hardware",
                "intl_markets_in_alert": [{"market": "kr", "mature": True, "asof": "2026-07-16"}],
                "leadership_state": "BROKEN",
                "leadership_detail": {"z_vel": -0.74, "med_dd": -0.25, "state_since": "2026-07-07"},
                "n_alert": 2,
                "d3_alert": 1,
                "n_mature": 3,
                "immature": ["tw"],
                "us_spillover": "contained",
                "asof": "2026-07-16",
                "degraded": [],
                "display_only": True,
                "is_context_only": True,
            }
        }

    def test_absent_world_state(self, tmp_path):
        """world_state.json absent → empty lobe with gap note."""
        lobe, gap = _summarize_contagion(tmp_path)
        assert lobe == {}
        assert gap is not None

    def test_present(self, tmp_path):
        """world_state.contagion_regime present → lobe populated."""
        ws = self._world_state_with_contagion()
        ws_path = tmp_path / "data" / "neuralweb" / "world_state.json"
        _write(ws_path, ws)

        lobe, gap = _summarize_contagion(tmp_path)
        assert gap is None
        assert lobe["state"] == "SLIPPING"
        assert lobe["leadership_state"] == "BROKEN"
        assert lobe["us_spillover"] == "contained"
        assert lobe["is_context_only"] is True
        assert lobe["display_only"] is True
        assert "accruing" in lobe.get("honesty_note", "")

    def test_absent_contagion_sub_block(self, tmp_path):
        """world_state exists but has no contagion_regime → gap note."""
        ws = {"verdict": {"verdict": "NEUTRAL"}}
        ws_path = tmp_path / "data" / "neuralweb" / "world_state.json"
        _write(ws_path, ws)

        lobe, gap = _summarize_contagion(tmp_path)
        assert lobe == {}
        assert gap is not None
        assert "pre-CSP" in gap or "absent" in gap.lower()
