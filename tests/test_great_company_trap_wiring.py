"""tests/test_great_company_trap_wiring.py — B1: crowding_z wiring in stock_fundamentals.

Tests three properties:

  1. _load_basket_crowding_z_map — None-safe when files are missing; correctly
     builds {ticker: max_crowding_z} when files exist (in-memory, no real disk).

  2. _compute_trap_block — crowding_z passes through when supplied; block is
     None-safe when all inputs are unavailable; does NOT return None when only
     crowding_z is available (crowding alone is a valid reason to emit the block).

  3. Schema guard — the great_company_trap block carries the required display-only
     firewall stamps and never carries scoring keys.

All tests are deterministic and I/O-free (mocking / monkeypatching disk reads).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine import stock_fundamentals as SF  # noqa: E402
from engine.moat_falsifiers import great_company_trap  # noqa: E402


# ── 1. _load_basket_crowding_z_map ────────────────────────────────────────────

class TestLoadBasketCrowdingZMap:
    """_load_basket_crowding_z_map degrades to {} when files are absent."""

    def test_returns_empty_when_alloc_missing(self, tmp_path):
        """When allocation.json does not exist the map is {}."""
        with patch("engine.stock_fundamentals.config") as mock_cfg:
            mock_cfg.ROOT = tmp_path          # no site/allocationdata/ subdirs created
            mock_cfg.data_dir.return_value = tmp_path
            result = SF._load_basket_crowding_z_map()
        assert result == {}

    def test_returns_empty_when_membership_missing(self, tmp_path):
        """When membership.json is absent but allocation.json exists → {}."""
        import json
        alloc_dir = tmp_path / "site" / "allocationdata"
        alloc_dir.mkdir(parents=True)
        alloc = {"ranks": [{"id": "ai", "crowding": {"crowding_z": 1.5}}]}
        (alloc_dir / "allocation.json").write_text(json.dumps(alloc))
        # data/baskets/ NOT created → membership.json absent
        with patch("engine.stock_fundamentals.config") as mock_cfg:
            mock_cfg.ROOT = tmp_path
            mock_cfg.data_dir.return_value = tmp_path  # no baskets subdir
            result = SF._load_basket_crowding_z_map()
        assert result == {}

    def test_correctly_maps_ticker_to_crowding_z(self, tmp_path):
        """Ticker in a basket whose crowding_z=1.5 gets crowding_z=1.5."""
        import json
        alloc_dir = tmp_path / "site" / "allocationdata"
        alloc_dir.mkdir(parents=True)
        alloc = {"ranks": [{"id": "ai", "crowding": {"crowding_z": 1.5}}]}
        (alloc_dir / "allocation.json").write_text(json.dumps(alloc))

        baskets_dir = tmp_path / "baskets"
        baskets_dir.mkdir(parents=True)
        membership = {
            "baskets": {
                "ai": {"members": [{"ticker": "NVDA"}, {"ticker": "AMD"}]}
            }
        }
        (baskets_dir / "membership.json").write_text(json.dumps(membership))

        with patch("engine.stock_fundamentals.config") as mock_cfg:
            mock_cfg.ROOT = tmp_path
            mock_cfg.data_dir.return_value = tmp_path
            result = SF._load_basket_crowding_z_map()

        assert result.get("NVDA") == pytest.approx(1.5)
        assert result.get("AMD") == pytest.approx(1.5)

    def test_max_crowding_z_across_baskets(self, tmp_path):
        """Ticker in two baskets gets the MAX crowding_z."""
        import json
        alloc_dir = tmp_path / "site" / "allocationdata"
        alloc_dir.mkdir(parents=True)
        alloc = {
            "ranks": [
                {"id": "ai",   "crowding": {"crowding_z": 0.8}},
                {"id": "semis","crowding": {"crowding_z": 2.1}},
            ]
        }
        (alloc_dir / "allocation.json").write_text(json.dumps(alloc))

        baskets_dir = tmp_path / "baskets"
        baskets_dir.mkdir(parents=True)
        membership = {
            "baskets": {
                "ai":    {"members": [{"ticker": "NVDA"}]},
                "semis": {"members": [{"ticker": "NVDA"}, {"ticker": "TSM"}]},
            }
        }
        (baskets_dir / "membership.json").write_text(json.dumps(membership))

        with patch("engine.stock_fundamentals.config") as mock_cfg:
            mock_cfg.ROOT = tmp_path
            mock_cfg.data_dir.return_value = tmp_path
            result = SF._load_basket_crowding_z_map()

        # NVDA is in both — should get 2.1 (max)
        assert result.get("NVDA") == pytest.approx(2.1)
        # TSM is only in semis — should get 2.1
        assert result.get("TSM") == pytest.approx(2.1)

    def test_removed_members_excluded(self, tmp_path):
        """Members flagged removed=True are not included."""
        import json
        alloc_dir = tmp_path / "site" / "allocationdata"
        alloc_dir.mkdir(parents=True)
        alloc = {"ranks": [{"id": "ai", "crowding": {"crowding_z": 1.5}}]}
        (alloc_dir / "allocation.json").write_text(json.dumps(alloc))

        baskets_dir = tmp_path / "baskets"
        baskets_dir.mkdir(parents=True)
        membership = {
            "baskets": {
                "ai": {"members": [
                    {"ticker": "NVDA"},
                    {"ticker": "OLD", "removed": True},   # must not appear
                ]}
            }
        }
        (baskets_dir / "membership.json").write_text(json.dumps(membership))

        with patch("engine.stock_fundamentals.config") as mock_cfg:
            mock_cfg.ROOT = tmp_path
            mock_cfg.data_dir.return_value = tmp_path
            result = SF._load_basket_crowding_z_map()

        assert "NVDA" in result
        assert "OLD" not in result

    def test_baskets_without_crowding_z_skipped(self, tmp_path):
        """Baskets whose crowding_z is null/absent do not add entries."""
        import json
        alloc_dir = tmp_path / "site" / "allocationdata"
        alloc_dir.mkdir(parents=True)
        alloc = {
            "ranks": [
                {"id": "ai",    "crowding": {"crowding_z": None}},   # null → skip
                {"id": "clean", "crowding": {}},                      # absent → skip
                {"id": "semis", "crowding": {"crowding_z": 1.2}},
            ]
        }
        (alloc_dir / "allocation.json").write_text(json.dumps(alloc))

        baskets_dir = tmp_path / "baskets"
        baskets_dir.mkdir(parents=True)
        membership = {
            "baskets": {
                "ai":    {"members": [{"ticker": "NVDA"}]},
                "clean": {"members": [{"ticker": "NEE"}]},
                "semis": {"members": [{"ticker": "TSM"}]},
            }
        }
        (baskets_dir / "membership.json").write_text(json.dumps(membership))

        with patch("engine.stock_fundamentals.config") as mock_cfg:
            mock_cfg.ROOT = tmp_path
            mock_cfg.data_dir.return_value = tmp_path
            result = SF._load_basket_crowding_z_map()

        assert "NVDA" not in result   # null crowding_z → not included
        assert "NEE" not in result    # absent crowding_z → not included
        assert result.get("TSM") == pytest.approx(1.2)


# ── 2. _compute_trap_block ────────────────────────────────────────────────────

class TestComputeTrapBlock:
    """_compute_trap_block passes crowding_z through and is None-safe."""

    def _minimal_rev(self, ticker: str, direction: str = "downgrading") -> dict:
        return {ticker: {"direction": direction}}

    def _minimal_insider(self, ticker: str, net_usd_mn: float = -1.0) -> dict:
        return {ticker: {"net_usd_mn": net_usd_mn}}

    def test_crowding_z_passed_through_when_supplied(self):
        """When crowding_z=1.5 is supplied, legs['crowding']['value'] == 1.5."""
        result = SF._compute_trap_block(
            "AAPL",
            analyst_rev={},
            insider=self._minimal_insider("AAPL"),
            crowding_z=1.5,
        )
        assert result is not None
        assert result["legs"]["crowding"]["value"] == pytest.approx(1.5)
        assert result["legs"]["crowding"]["fired"] is True
        assert result["legs"]["crowding"]["available"] is True

    def test_crowding_z_none_shows_unavailable(self):
        """When crowding_z=None, leg is available=False and fired=False."""
        result = SF._compute_trap_block(
            "AAPL",
            analyst_rev={},
            insider=self._minimal_insider("AAPL"),
            crowding_z=None,
        )
        assert result is not None
        assert result["legs"]["crowding"]["available"] is False
        assert result["legs"]["crowding"]["fired"] is False

    def test_returns_none_when_all_inputs_none(self):
        """When all three inputs are unavailable, block is suppressed (None)."""
        result = SF._compute_trap_block(
            "AAPL",
            analyst_rev={},      # no revision for AAPL
            insider={},          # no insider for AAPL
            crowding_z=None,
        )
        assert result is None

    def test_crowding_z_alone_emits_block(self):
        """crowding_z alone (insider/revision missing) is enough to emit the block."""
        result = SF._compute_trap_block(
            "AAPL",
            analyst_rev={},
            insider={},
            crowding_z=0.5,
        )
        assert result is not None
        # crowding leg below threshold — does not fire but block is present
        assert result["legs"]["crowding"]["available"] is True
        assert result["legs"]["crowding"]["fired"] is False

    def test_crowding_z_above_threshold_fires(self):
        """crowding_z >= 1.0 (CROWDED_Z) causes crowding leg to fire."""
        result = SF._compute_trap_block(
            "NVDA",
            analyst_rev={},
            insider={},
            crowding_z=1.0,
        )
        assert result is not None
        assert result["legs"]["crowding"]["fired"] is True
        assert result["trap_signals_present"] is True

    def test_default_crowding_z_is_none(self):
        """Calling without crowding_z= defaults to None (no crowding leg)."""
        result = SF._compute_trap_block(
            "X",
            analyst_rev={},
            insider=self._minimal_insider("X"),
        )
        assert result is not None
        assert result["legs"]["crowding"]["available"] is False

    def test_non_fatal_with_bad_insider_type(self):
        """Bad net_usd_mn type (string) degrades insider_net_usd to None; block
        still emits because revision_direction is valid."""
        result = SF._compute_trap_block(
            "BAD",
            analyst_rev={"BAD": {"direction": "downgrading"}},
            insider={"BAD": {"net_usd_mn": "not-a-number"}},  # bad type → None
            crowding_z=None,
        )
        # revision_direction = "downgrading" is available → block emitted, not None
        assert result is not None
        assert result["legs"]["revision_direction"]["fired"] is True
        # insider leg should be unavailable (conversion failed)
        assert result["legs"]["insider_net"]["available"] is False


# ── 3. Schema guard ───────────────────────────────────────────────────────────

class TestTrapBlockSchema:
    """great_company_trap blocks carry firewall stamps; no scoring keys."""

    REQUIRED_KEYS = {"trap_signals_present", "de_escalation_reason", "legs",
                     "inputs_used", "_horizon_role", "_display_only", "_version"}
    FORBIDDEN_KEYS = {"escalate", "escalation", "score_boost", "buy",
                      "upgrade_signal", "score", "rank"}

    def _make_block(self, **kw):
        return great_company_trap(**kw)

    def test_required_keys_present(self):
        r = self._make_block(crowding_z=1.5, insider_net_usd=-600_000,
                             revision_direction="downgrading")
        assert self.REQUIRED_KEYS <= set(r.keys()), (
            f"Missing keys: {self.REQUIRED_KEYS - set(r.keys())}"
        )

    def test_no_scoring_keys(self):
        r = self._make_block(crowding_z=1.5, revision_direction="downgrading")
        bad = self.FORBIDDEN_KEYS & set(r.keys())
        assert not bad, f"Forbidden scoring keys found: {bad}"

    def test_horizon_role_hold_thesis(self):
        r = self._make_block()
        assert r["_horizon_role"] == "hold_thesis"

    def test_display_only_true(self):
        r = self._make_block()
        assert r["_display_only"] is True

    def test_legs_schema(self):
        r = self._make_block(crowding_z=0.3, insider_net_usd=100_000,
                             revision_direction="stable")
        for leg_name in ("crowding", "insider_net", "revision_direction"):
            leg = r["legs"][leg_name]
            assert "fired" in leg, f"{leg_name}: missing 'fired'"
            assert "available" in leg, f"{leg_name}: missing 'available'"
            assert "value" in leg, f"{leg_name}: missing 'value'"
            assert "threshold" in leg, f"{leg_name}: missing 'threshold'"

    def test_inputs_used_verbatim(self):
        r = self._make_block(crowding_z=1.8, insider_net_usd=-750_000,
                             revision_direction="downgrading")
        assert r["inputs_used"]["crowding_z"] == pytest.approx(1.8)
        assert r["inputs_used"]["insider_net_usd"] == -750_000
        assert r["inputs_used"]["revision_direction"] == "downgrading"
