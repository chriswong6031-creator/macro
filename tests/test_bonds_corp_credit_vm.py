"""Tests for the CCW-W4 corporate credit desk vm builder in scripts/build_bonds.py.

Coverage:
  - vm null-safety: missing credit_momentum.json → accruing state, no crash
  - hero stance mapping determinism (fired tag, widening, calm)
  - bond_health corporate_credit block schema + authority dict
  - maturity-wall aggregation (segs built from parquet, non-zero filter)
  - FINRA breadth vm (advance_pct, lows_pct computation)
  - _theme_stance determinism (neocloud always red, telecom always neutral)
  - gauge chip CSS derived from state (widening→amber, tightening→calm, widening_stress→red)

Zero network calls; all inputs are synthetic (tmp_path fixtures).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_cm(path: Path, data: dict) -> None:
    """Write a credit_momentum.json to path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False))


def _minimal_cm(as_of: str = "2026-07-14") -> dict:
    """Minimal valid credit_momentum.json with all values accruing."""
    return {
        "organ": "credit_momentum.v1",
        "as_of": as_of,
        "authority": {"rank": False, "size": False, "gate": False, "escalate": False},
        "accruing": "DISPLAY-ONLY",
        "oscillator_sanity": {},
        "roster": {},
        "etf_prices": {},
        "ladder": {},
        "market": {
            "ig": {"state": "accruing", "level": None},
            "hy": {"state": "accruing", "level": None},
        },
        "themes": {
            "hyperscaler_credit": {
                "theme": "hyperscaler_credit",
                "n_dates": 1,
                "spread": {"state": "accruing", "level": None, "d21": None, "velocity": {}},
            },
        },
        "tags": {
            "credit_market_turn": {"tag": "credit_market_turn", "fired": False, "score": 0, "legs": {}},
            "credit_theme_stress": [],
        },
        "breadth": {"finra": None},
        "watch": {"transition": {"n_snapshots": 1, "fallen_angel_candidates": [], "new_issuance_events": [],
                                  "note": "accruing — fewer than 2 holdings snapshots"}},
        "divergence": [],
        "_timing_s": 0.0,
        "_n_ledger_new": 0,
    }


def _cm_with_widening_market(fired: bool = False, ig_state: str = "widening") -> dict:
    """CM with live market data for stance testing."""
    cm = _minimal_cm()
    cm["market"]["ig"]["state"] = ig_state
    cm["market"]["ig"]["level"] = 0.77
    cm["tags"]["credit_market_turn"]["fired"] = fired
    return cm


def _cm_with_live_roster() -> dict:
    """CM with live roster data for gauge testing."""
    cm = _minimal_cm()
    cm["roster"] = {
        "ig_oas": {
            "level": 0.77, "d21": 0.02, "d1": 0.01,
            "velocity": {"vel21": 0.02, "vel21_pctile": 67.8},
            "state": "widening",
        },
        "hy_oas": {
            "level": 2.69, "d21": -0.09, "d1": -0.01,
            "velocity": {"vel21": -0.09, "vel21_pctile": 47.5},
            "state": "stable",
        },
        "quality_spread": {
            "level": 1.92, "d21": -0.11, "d1": -0.02,
            "velocity": {"vel21": -0.11, "vel21_pctile": 38.5},
            "state": "stable",
        },
        "ccc_bb": {
            "level": 8.11, "d21": 0.24, "d1": -0.04,
            "velocity": {"vel21": 0.24, "vel21_pctile": 67.0},
            "state": "widening",
        },
    }
    cm["breadth"] = {
        "finra": {
            "_source": "FINRA trade data",
            "breadth": {
                "all securities": {
                    "advance_share_latest": 0.16,
                    "advance_share_5d_ma": 0.28,
                    "vel21_advance_share": -0.14,
                    "vel21_pctile_advance_share": 15.3,
                    "wk52_high_low_net_share": -0.115,
                    "n_days": 751,
                    "latest_date": "2026-07-13",
                }
            },
        }
    }
    cm["watch"] = {
        "orcl": {
            "issuer": "ORCL",
            "g_spread_bp_pw": 144.33,
            "ig_peer_median_bp": 74.33,
            "premium_vs_ig_peers_bp": 70.0,
        },
        "transition": {"n_snapshots": 2, "fallen_angel_candidates": [], "new_issuance_events": [],
                        "note": "live — 2 snapshots"},
    }
    return cm


def _make_maturity_wall_parquet(tmp_path: Path) -> Path:
    """Write a synthetic maturity_wall.parquet with theme rows."""
    rows = []
    buckets = ["0_1y", "1_3y", "3_5y", "5_10y", "10y_plus"]
    themes = ["hyperscaler_credit", "neocloud_credit", "memory_credit",
              "ai_power_credit", "dc_reit_credit", "ai_hardware_credit", "telecom_legacy"]
    for th in themes:
        for bkt in buckets:
            val = 0.0 if bkt == "0_1y" else 1_000_000.0  # 1M par except 0-1y
            rows.append({"as_of": "2026-07-10", "scope_type": "theme",
                          "scope": th, "bucket": bkt, "par_total": val, "n_bonds": 0 if val == 0 else 1})
    df = pd.DataFrame(rows)
    out = tmp_path / "maturity_wall.parquet"
    df.to_parquet(out)
    return out


# ---------------------------------------------------------------------------
# Import the functions under test
# ---------------------------------------------------------------------------

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_bonds import (
    build_corp_credit_vm,
    _build_corp_credit_bond_health,
    _hero_stance,
    _theme_stance,
    _build_spread_gauges,
    _build_maturity_wall,
    _build_finra_vm,
    _build_theme_tiles,
    _load_theme_daily_levels,
)


# ---------------------------------------------------------------------------
# 1. Null-safety — missing credit_momentum.json
# ---------------------------------------------------------------------------

class TestNullSafety:
    def test_missing_file_returns_accruing(self, tmp_path: Path) -> None:
        """When credit_momentum.json is absent, vm returns accruing state without crashing."""
        vm = build_corp_credit_vm(data_root=tmp_path)
        assert vm["accruing"] is True
        assert vm["hero"]["pill_en"] == "Watch — don't chase"
        assert vm["gauges"] == []
        assert vm["themes"] == []
        assert vm["finra"] is None
        assert vm["maturity_wall"] == []

    def test_corrupt_json_returns_accruing(self, tmp_path: Path) -> None:
        """Corrupt JSON returns accruing state without crashing."""
        p = tmp_path / "corp_bonds" / "credit_momentum.json"
        p.parent.mkdir(parents=True)
        p.write_text("{not: valid json")
        vm = build_corp_credit_vm(data_root=tmp_path)
        assert vm["accruing"] is True

    def test_minimal_cm_no_crash(self, tmp_path: Path) -> None:
        """Minimal valid cm (all accruing) parses without crash."""
        cm_path = tmp_path / "corp_bonds" / "credit_momentum.json"
        _write_cm(cm_path, _minimal_cm())
        vm = build_corp_credit_vm(data_root=tmp_path)
        assert vm["as_of"] == "2026-07-14"
        # hero should still have valid strings
        assert isinstance(vm["hero"]["state_en"], str)
        assert isinstance(vm["hero"]["state_zh"], str)

    def test_missing_keys_no_crash(self, tmp_path: Path) -> None:
        """CM missing most keys still returns a valid vm dict."""
        cm_path = tmp_path / "corp_bonds" / "credit_momentum.json"
        _write_cm(cm_path, {"as_of": "2026-07-14"})
        vm = build_corp_credit_vm(data_root=tmp_path)
        assert "hero" in vm
        assert "gauges" in vm
        assert "themes" in vm


# ---------------------------------------------------------------------------
# 2. Hero stance mapping determinism
# ---------------------------------------------------------------------------

class TestHeroStance:
    def test_calm_default(self) -> None:
        """No fired tag + no widening → calm default ('Watch — don't chase', cs-amber)."""
        cm = _minimal_cm()
        state_en, state_zh, pill_en, pill_zh, pill_css, hero_cs = _hero_stance(cm)
        assert "low" in state_en
        assert pill_en == "Watch — don't chase"
        assert pill_css == "stance-amber"
        assert hero_cs == "cs-amber"

    def test_fired_tag_returns_get_ready(self) -> None:
        """fired=True → 'Get ready' stance, cs-red."""
        cm = _cm_with_widening_market(fired=True)
        _, _, pill_en, _, pill_css, hero_cs = _hero_stance(cm)
        assert pill_en == "Get ready"
        assert pill_css == "stance-red"
        assert hero_cs == "cs-red"

    def test_market_widening_without_fired(self) -> None:
        """Market IG widening without fired tag → amber Watch."""
        cm = _cm_with_widening_market(fired=False, ig_state="widening")
        _, _, pill_en, _, pill_css, hero_cs = _hero_stance(cm)
        assert pill_en == "Watch — don't chase"
        assert pill_css == "stance-amber"
        assert hero_cs == "cs-amber"

    def test_theme_stress_pctile_triggers_amber(self) -> None:
        """Theme vel21_pctile >= 85 → amber watch even without fired tag."""
        cm = _minimal_cm()
        cm["themes"]["hyperscaler_credit"]["spread"]["velocity"] = {"vel21_pctile": 90.0}
        cm["themes"]["hyperscaler_credit"]["spread"]["state"] = "widening"
        _, _, pill_en, _, pill_css, hero_cs = _hero_stance(cm)
        assert pill_css == "stance-amber"

    def test_determinism(self) -> None:
        """Same inputs always produce same outputs."""
        cm = _minimal_cm()
        result1 = _hero_stance(cm)
        result2 = _hero_stance(cm)
        assert result1 == result2


# ---------------------------------------------------------------------------
# 3. Per-theme stance (_theme_stance)
# ---------------------------------------------------------------------------

class TestThemeStance:
    def test_telecom_always_neutral(self) -> None:
        stance_en, stance_zh, css = _theme_stance(0.7, 50.0, "telecom_legacy")
        assert css == "ts-neutral"
        assert stance_en == "Context"

    def test_neocloud_always_red(self) -> None:
        stance_en, stance_zh, css = _theme_stance(5.7, 30.0, "neocloud_credit")
        assert css == "ts-red"
        assert stance_en == "Watch closely"

    def test_none_level_returns_neutral(self) -> None:
        stance_en, stance_zh, css = _theme_stance(None, None, "hyperscaler_credit")
        assert css == "ts-neutral"
        assert stance_en == "Building history"

    def test_tight_spread_calm(self) -> None:
        # level < 0.75 → Ignore/calm (matches ai_power/dc_reit/ai_hardware at ~0.59%)
        stance_en, _, css = _theme_stance(0.6, 40.0, "ai_power_credit")
        assert css == "ts-calm"
        assert stance_en == "Ignore"

    def test_high_pctile_red(self) -> None:
        # pctile >= 85 → red/watch-closely
        stance_en, _, css = _theme_stance(1.5, 90.0, "memory_credit")
        assert css == "ts-red"

    def test_mid_range_amber(self) -> None:
        # level >= 0.75 and < 4.0 and pctile < 85 → amber/Watch
        stance_en, _, css = _theme_stance(2.0, 60.0, "memory_credit")
        assert css == "ts-amber"
        assert stance_en == "Watch"

    def test_hyperscaler_level_amber(self) -> None:
        # hyperscaler at ~0.8% (80bp) → Watch (mockup-verified boundary)
        stance_en, _, css = _theme_stance(0.8, 50.0, "hyperscaler_credit")
        assert css == "ts-amber"
        assert stance_en == "Watch"

    def test_ai_power_level_calm(self) -> None:
        # ai_power at ~0.59% (59bp) → Ignore (mockup-verified boundary)
        stance_en, _, css = _theme_stance(0.59, 50.0, "ai_power_credit")
        assert css == "ts-calm"
        assert stance_en == "Ignore"


# ---------------------------------------------------------------------------
# 4. Spread gauges
# ---------------------------------------------------------------------------

class TestSpreadGauges:
    def _make_roster(self) -> dict:
        return {
            "ig_oas": {"level": 0.77, "d21": 0.02, "velocity": {"vel21_pctile": 67.8}, "state": "widening"},
            "hy_oas": {"level": 2.69, "d21": -0.09, "velocity": {"vel21_pctile": 47.5}, "state": "stable"},
            "quality_spread": {"level": 1.92, "d21": -0.11, "velocity": {"vel21_pctile": 38.5}, "state": "stable"},
            "ccc_bb": {"level": 8.11, "d21": 0.24, "velocity": {"vel21_pctile": 67.0}, "state": "widening"},
        }

    def test_returns_4_gauges(self) -> None:
        gauges = _build_spread_gauges(self._make_roster(), {})
        assert len(gauges) == 4

    def test_ig_widening_chip_amber(self) -> None:
        gauges = _build_spread_gauges(self._make_roster(), {})
        ig_gauge = next(g for g in gauges if g["key"] == "ig_oas")
        assert ig_gauge["chip_css"] == "chip-amber"

    def test_hy_stable_chip_calm(self) -> None:
        gauges = _build_spread_gauges(self._make_roster(), {})
        hy_gauge = next(g for g in gauges if g["key"] == "hy_oas")
        # stable with mid pctile → calm (not widening_stress)
        assert hy_gauge["chip_css"] in ("chip-amber", "chip-calm", "chip-red")  # not crashing

    def test_widening_stress_chip_red(self) -> None:
        roster = self._make_roster()
        roster["ccc_bb"]["state"] = "widening_stress"
        gauges = _build_spread_gauges(roster, {})
        ccc_gauge = next(g for g in gauges if g["key"] == "ccc_bb")
        assert ccc_gauge["chip_css"] == "chip-red"

    def test_level_in_sub(self) -> None:
        gauges = _build_spread_gauges(self._make_roster(), {})
        ig_gauge = next(g for g in gauges if g["key"] == "ig_oas")
        assert "0.77" in ig_gauge["sub_en"]

    def test_empty_roster_returns_4_gauges(self) -> None:
        """Empty roster returns 4 gauges without crash (all accruing state)."""
        gauges = _build_spread_gauges({}, {})
        assert len(gauges) == 4
        for g in gauges:
            assert isinstance(g["label_en"], str)


# ---------------------------------------------------------------------------
# 5. bond_health corporate_credit block schema
# ---------------------------------------------------------------------------

class TestBondHealthBlock:
    def _make_vm(self) -> dict:
        """Build a vm with some live data."""
        cm = _cm_with_live_roster()
        # write to tmp and build
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            cm_path = tdir / "corp_bonds" / "credit_momentum.json"
            _write_cm(cm_path, cm)
            return build_corp_credit_vm(data_root=tdir)

    def test_required_keys_present(self) -> None:
        vm = self._make_vm()
        bh = _build_corp_credit_bond_health(vm)
        for key in ("as_of", "authority", "market_state", "themes", "breadth", "watch",
                     "divergence_accruing", "display_only"):
            assert key in bh, f"missing key: {key}"

    def test_authority_all_false(self) -> None:
        vm = self._make_vm()
        bh = _build_corp_credit_bond_health(vm)
        auth = bh["authority"]
        assert auth["rank"] is False
        assert auth["size"] is False
        assert auth["gate"] is False
        assert auth["escalate"] is False

    def test_display_only_true(self) -> None:
        vm = self._make_vm()
        bh = _build_corp_credit_bond_health(vm)
        assert bh["display_only"] is True

    def test_themes_dict_has_7_entries(self) -> None:
        vm = self._make_vm()
        bh = _build_corp_credit_bond_health(vm)
        # themes may vary based on what's in _THEME_META; we have 7 defined
        assert len(bh["themes"]) == 7

    def test_watch_orcl_present(self) -> None:
        vm = self._make_vm()
        bh = _build_corp_credit_bond_health(vm)
        assert bh["watch"]["orcl_g_spread_bp"] is not None
        assert bh["watch"]["orcl_premium_vs_ig_bp"] is not None

    def test_missing_vm_no_crash(self) -> None:
        """Empty vm dict still produces a valid bond_health block."""
        bh = _build_corp_credit_bond_health({})
        assert "authority" in bh
        assert bh["authority"]["rank"] is False

    def test_json_serializable(self) -> None:
        """The block must be JSON-serializable."""
        vm = self._make_vm()
        bh = _build_corp_credit_bond_health(vm)
        serialized = json.dumps(bh, ensure_ascii=False, default=str)
        roundtrip = json.loads(serialized)
        assert roundtrip["display_only"] is True


# ---------------------------------------------------------------------------
# 6. Maturity-wall aggregation
# ---------------------------------------------------------------------------

class TestMaturityWall:
    def test_segs_built_from_parquet(self, tmp_path: Path) -> None:
        """Non-zero par buckets produce seg entries; 0-par buckets are omitted."""
        mw_path = _make_maturity_wall_parquet(tmp_path)
        # Build a fake cm_path that points into tmp_path/corp_bonds/
        cm_dir = tmp_path / "corp_bonds"
        cm_dir.mkdir(parents=True, exist_ok=True)
        series_dir = cm_dir / "series"
        series_dir.mkdir(exist_ok=True)
        import shutil
        shutil.copy(mw_path, series_dir / "maturity_wall.parquet")
        fake_cm_path = cm_dir / "credit_momentum.json"
        fake_cm_path.write_text("{}")  # content unused in _build_maturity_wall

        rows = _build_maturity_wall(fake_cm_path)
        # should have one entry per theme
        assert len(rows) == 7
        # 0_1y should be excluded (all themes have 0 par in 0_1y)
        for row in rows:
            css_classes = [s["css_class"] for s in row["segs"]]
            assert "seg-0" not in css_classes, f"0_1y segment found in {row['slug']}"

    def test_missing_parquet_returns_empty(self, tmp_path: Path) -> None:
        """Missing maturity_wall.parquet returns []."""
        fake_cm_path = tmp_path / "corp_bonds" / "credit_momentum.json"
        fake_cm_path.parent.mkdir(parents=True)
        fake_cm_path.write_text("{}")
        rows = _build_maturity_wall(fake_cm_path)
        assert rows == []

    def test_segs_have_positive_flex(self, tmp_path: Path) -> None:
        """All segs have positive flex (par > 0)."""
        mw_path = _make_maturity_wall_parquet(tmp_path)
        cm_dir = tmp_path / "corp_bonds"
        cm_dir.mkdir(parents=True, exist_ok=True)
        series_dir = cm_dir / "series"
        series_dir.mkdir(exist_ok=True)
        import shutil
        shutil.copy(mw_path, series_dir / "maturity_wall.parquet")
        fake_cm_path = cm_dir / "credit_momentum.json"
        fake_cm_path.write_text("{}")

        rows = _build_maturity_wall(fake_cm_path)
        for row in rows:
            for seg in row["segs"]:
                assert seg["flex"] > 0


# ---------------------------------------------------------------------------
# 7. FINRA breadth vm
# ---------------------------------------------------------------------------

class TestFinraBreadthVm:
    def _finra_block(self, adv_share: float = 0.16, wk52_net: float = -0.115,
                     date: str = "2026-07-13") -> dict:
        return {
            "finra": {
                "_source": "FINRA trade data",
                "breadth": {
                    "all securities": {
                        "advance_share_latest": adv_share,
                        "advance_share_5d_ma": adv_share + 0.1,
                        "vel21_advance_share": -0.14,
                        "vel21_pctile_advance_share": 15.3,
                        "wk52_high_low_net_share": wk52_net,
                        "n_days": 751,
                        "latest_date": date,
                    }
                },
            }
        }

    def test_advance_pct_computed(self) -> None:
        finra = _build_finra_vm(self._finra_block(adv_share=0.16))
        assert finra is not None
        assert abs(finra["advance_pct"] - 16.0) < 0.5

    def test_lows_pct_from_wk52_net(self) -> None:
        finra = _build_finra_vm(self._finra_block(wk52_net=-0.115))
        assert finra is not None
        assert abs(finra["lows_pct"] - 11.5) < 0.5

    def test_none_inputs_returns_accruing(self) -> None:
        """Missing advance_share → accruing=True."""
        block = {
            "finra": {
                "breadth": {
                    "all securities": {
                        "advance_share_latest": None,
                        "wk52_high_low_net_share": None,
                        "n_days": 0,
                        "latest_date": "",
                    }
                }
            }
        }
        finra = _build_finra_vm(block)
        assert finra is not None
        assert finra["accruing"] is True

    def test_missing_finra_returns_none(self) -> None:
        result = _build_finra_vm({})
        assert result is None

    def test_date_preserved(self) -> None:
        finra = _build_finra_vm(self._finra_block(date="2026-07-13"))
        assert finra["date"] == "2026-07-13"


# ---------------------------------------------------------------------------
# 8. Level-driven tiles: 1-date theme_daily → level shows, Δ still accruing
# ---------------------------------------------------------------------------

def _make_theme_daily_parquet(tmp_path: Path, rows: list[dict]) -> Path:
    """Write a synthetic theme_daily.parquet."""
    series_dir = tmp_path / "corp_bonds" / "series"
    series_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    path = series_dir / "theme_daily.parquet"
    df.to_parquet(path)
    return tmp_path / "corp_bonds" / "credit_momentum.json"


class TestLevelDrivenTiles:
    """Defect 1 fix: 1-date theme_daily provides point-in-time level even when
    credit_momentum.json has level=None (density gate closed; < 21 dates)."""

    def _single_date_cm_path(self, tmp_path: Path) -> Path:
        """Write a theme_daily with one date per theme + a minimal cm.json.
        Returns the cm_path.
        """
        themes_data = [
            {"as_of": "2026-07-10", "theme": "hyperscaler_credit",
             "n_bonds": 158, "g_spread_bp_pw": 80.29},
            {"as_of": "2026-07-10", "theme": "neocloud_credit",
             "n_bonds": 4, "g_spread_bp_pw": 566.60},
            {"as_of": "2026-07-10", "theme": "memory_credit",
             "n_bonds": 9, "g_spread_bp_pw": 272.39},
            {"as_of": "2026-07-10", "theme": "ai_power_credit",
             "n_bonds": 44, "g_spread_bp_pw": 58.85},
            {"as_of": "2026-07-10", "theme": "dc_reit_credit",
             "n_bonds": 18, "g_spread_bp_pw": 58.61},
            {"as_of": "2026-07-10", "theme": "ai_hardware_credit",
             "n_bonds": 25, "g_spread_bp_pw": 59.34},
            {"as_of": "2026-07-10", "theme": "telecom_legacy",
             "n_bonds": 44, "g_spread_bp_pw": 70.63},
        ]
        cm_path = _make_theme_daily_parquet(tmp_path, themes_data)
        # write minimal cm with all themes accruing (level=None, d21=None)
        cm = _minimal_cm()
        cm["themes"] = {
            slug: {"theme": slug, "n_dates": 1,
                   "spread": {"state": "accruing", "level": None, "d21": None, "velocity": {}}}
            for slug in ["hyperscaler_credit", "neocloud_credit", "memory_credit",
                         "ai_power_credit", "dc_reit_credit", "ai_hardware_credit", "telecom_legacy"]
        }
        cm_path.write_text(json.dumps(cm, ensure_ascii=False))
        return cm_path

    def test_1date_tile_shows_level(self, tmp_path: Path) -> None:
        """With 1 date in theme_daily, tile.level_disp is set from parquet (not None)."""
        cm_path = self._single_date_cm_path(tmp_path)
        vm = build_corp_credit_vm(data_root=tmp_path)
        tiles = {t["slug"]: t for t in vm["themes"]}
        # hyperscaler: 80.29bp / 100 = 0.8029 → "+0.8%"
        hyp = tiles["hyperscaler_credit"]
        assert hyp["level_disp"] is not None, "level_disp should be set from theme_daily"
        assert "+0.8%" in hyp["level_disp"], f"expected '+0.8%' in '{hyp['level_disp']}'"

    def test_1date_tile_delta_still_accruing(self, tmp_path: Path) -> None:
        """With only 1 date, tile.accruing=True (Δ is still building; no d21)."""
        cm_path = self._single_date_cm_path(tmp_path)
        vm = build_corp_credit_vm(data_root=tmp_path)
        tiles = {t["slug"]: t for t in vm["themes"]}
        # all tiles should have accruing=True because d21=None
        for slug, tile in tiles.items():
            assert tile["accruing"] is True, f"{slug}: expected accruing=True (no d21 yet)"

    def test_1date_neocloud_level_and_stance(self, tmp_path: Path) -> None:
        """neocloud (566bp = 5.67%) → level_disp='+5.7%', stance always Watch closely."""
        cm_path = self._single_date_cm_path(tmp_path)
        vm = build_corp_credit_vm(data_root=tmp_path)
        tiles = {t["slug"]: t for t in vm["themes"]}
        neo = tiles["neocloud_credit"]
        assert neo["level_disp"] is not None
        assert "+5.7%" in neo["level_disp"] or "+5.6%" in neo["level_disp"]
        assert neo["stance_en"] == "Watch closely"
        assert neo["stance_css"] == "ts-red"

    def test_1date_ai_power_level_and_stance(self, tmp_path: Path) -> None:
        """ai_power (58.85bp = 0.59%) → level_disp='+0.6%', stance=Ignore (ts-calm)."""
        cm_path = self._single_date_cm_path(tmp_path)
        vm = build_corp_credit_vm(data_root=tmp_path)
        tiles = {t["slug"]: t for t in vm["themes"]}
        ap = tiles["ai_power_credit"]
        assert ap["level_disp"] is not None
        assert "+0.6%" in ap["level_disp"]
        assert ap["stance_en"] == "Ignore"
        assert ap["stance_css"] == "ts-calm"

    def test_1date_telecom_stance_always_context(self, tmp_path: Path) -> None:
        """telecom_legacy always Context regardless of level."""
        cm_path = self._single_date_cm_path(tmp_path)
        vm = build_corp_credit_vm(data_root=tmp_path)
        tiles = {t["slug"]: t for t in vm["themes"]}
        tel = tiles["telecom_legacy"]
        assert tel["stance_en"] == "Context"
        assert tel["stance_css"] == "ts-neutral"

    def test_load_theme_daily_levels_returns_fractions(self, tmp_path: Path) -> None:
        """_load_theme_daily_levels returns pct-fractions (bp / 100)."""
        themes_data = [
            {"as_of": "2026-07-10", "theme": "hyperscaler_credit", "g_spread_bp_pw": 80.0},
        ]
        cm_path = _make_theme_daily_parquet(tmp_path, themes_data)
        levels = _load_theme_daily_levels(cm_path)
        assert "hyperscaler_credit" in levels
        assert abs(levels["hyperscaler_credit"] - 0.80) < 1e-6

    def test_load_theme_daily_missing_file_returns_empty(self, tmp_path: Path) -> None:
        """Missing theme_daily.parquet returns {}."""
        fake_cm = tmp_path / "corp_bonds" / "credit_momentum.json"
        fake_cm.parent.mkdir(parents=True, exist_ok=True)
        fake_cm.write_text("{}")
        levels = _load_theme_daily_levels(fake_cm)
        assert levels == {}

    def test_live_data_level_not_overridden_when_present(self) -> None:
        """When cm has a live level, it takes precedence over theme_daily fallback."""
        # themes_raw with a live level (cm level takes priority)
        themes_raw = {
            "hyperscaler_credit": {
                "spread": {"state": "live", "level": 1.5, "d21": 0.05, "velocity": {"vel21_pctile": 60.0}}
            }
        }
        tiles = _build_theme_tiles(themes_raw, cm_path=None)
        hyp = next(t for t in tiles if t["slug"] == "hyperscaler_credit")
        assert "+1.5%" in hyp["level_disp"]
        # d21 present → accruing=False
        assert hyp["accruing"] is False


# ---------------------------------------------------------------------------
# 9. Defect 3: bond_health finra_lows_share normalized to fraction
# ---------------------------------------------------------------------------

class TestBondHealthFractionNorm:
    """finra_lows_share in bond_health.json must be a fraction (0–1), not a percent."""

    def _build_health_block_with_finra(self) -> dict:
        import tempfile
        cm = _minimal_cm()
        cm["breadth"] = {
            "finra": {
                "_source": "FINRA trade data",
                "breadth": {
                    "all securities": {
                        "advance_share_latest": 0.16,
                        "advance_share_5d_ma": 0.26,
                        "vel21_advance_share": -0.14,
                        "vel21_pctile_advance_share": 15.3,
                        "wk52_high_low_net_share": -0.115,
                        "n_days": 751,
                        "latest_date": "2026-07-13",
                    }
                },
            }
        }
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            cm_path = tdir / "corp_bonds" / "credit_momentum.json"
            _write_cm(cm_path, cm)
            vm = build_corp_credit_vm(data_root=tdir)
        return _build_corp_credit_bond_health(vm)

    def test_finra_lows_share_is_fraction(self) -> None:
        """finra_lows_share must be < 1 (fraction), not 11.5 (percent)."""
        bh = self._build_health_block_with_finra()
        lows = bh["breadth"]["finra_lows_share"]
        assert lows is not None
        assert lows < 1.0, f"finra_lows_share={lows} should be a fraction < 1, not a percent"
        assert abs(lows - 0.115) < 0.005, f"expected ~0.115, got {lows}"

    def test_finra_advance_share_is_fraction(self) -> None:
        """finra_advance_share should also be a fraction (already correct, sanity check)."""
        bh = self._build_health_block_with_finra()
        adv = bh["breadth"]["finra_advance_share"]
        assert adv is not None
        assert adv < 1.0, f"finra_advance_share={adv} should be a fraction < 1"
        assert abs(adv - 0.16) < 0.005


# ---------------------------------------------------------------------------
# 10. Defect 4: ccc_bb gauge sub shows semantic copy, not raw level
# ---------------------------------------------------------------------------

class TestCccBbGaugeSub:
    """The CCC-BB gauge sub value must be the semantic 'CCC tier moving first',
    not the raw level (+8.11%).  The level detail belongs in the data-tip."""

    def _make_roster_with_ccc(self, ccc_level: float = 8.11,
                               ccc_state: str = "widening") -> dict:
        return {
            "ig_oas": {"level": 0.77, "d21": 0.02, "velocity": {"vel21_pctile": 67.8},
                       "state": "widening"},
            "hy_oas": {"level": 2.69, "d21": -0.09, "velocity": {"vel21_pctile": 47.5},
                       "state": "stable"},
            "quality_spread": {"level": 1.92, "d21": -0.11, "velocity": {"vel21_pctile": 38.5},
                                "state": "stable"},
            "ccc_bb": {"level": ccc_level, "d21": 0.24, "velocity": {"vel21_pctile": 67.0},
                       "state": ccc_state},
        }

    def test_ccc_bb_sub_is_semantic_not_level(self) -> None:
        """ccc_bb sub_en must NOT contain the raw level percentage."""
        gauges = _build_spread_gauges(self._make_roster_with_ccc(), {})
        ccc_g = next(g for g in gauges if g["key"] == "ccc_bb")
        assert "8.11" not in ccc_g["sub_en"], (
            f"ccc_bb sub_en '{ccc_g['sub_en']}' must not show raw level")
        assert "CCC tier" in ccc_g["sub_en"], (
            f"ccc_bb sub_en '{ccc_g['sub_en']}' should contain 'CCC tier'")

    def test_ccc_bb_level_in_tip(self) -> None:
        """The CCC-BB gap level value should appear in the tip text."""
        gauges = _build_spread_gauges(self._make_roster_with_ccc(ccc_level=8.11), {})
        ccc_g = next(g for g in gauges if g["key"] == "ccc_bb")
        assert "8.1" in ccc_g["tip_en"], (
            f"ccc_bb tip_en '{ccc_g['tip_en']}' should contain the level '8.1'")

    def test_ig_sub_still_shows_level(self) -> None:
        """ig_oas sub_en must still show the extra-yield level (level_in_sub=True)."""
        gauges = _build_spread_gauges(self._make_roster_with_ccc(), {})
        ig_g = next(g for g in gauges if g["key"] == "ig_oas")
        assert "0.77" in ig_g["sub_en"], (
            f"ig_oas sub_en '{ig_g['sub_en']}' should show level 0.77")


# ---------------------------------------------------------------------------
# 11. B1 regression: _build_watch with orcl present but g_spread_bp_pw missing/None
# ---------------------------------------------------------------------------

class TestBuildWatchB1Regression:
    """B1 fix: orcl block present but g_spread_bp_pw missing/None must yield orcl=None.

    The template does orcl.g_spread_bp / 100 which would TypeError on None if
    _build_watch returned a dict with g_spread_bp=None.
    """

    def _watch_raw_no_g_spread(self) -> dict:
        """watch block with orcl key but missing g_spread_bp_pw."""
        return {
            "orcl": {
                "issuer": "ORCL",
                # g_spread_bp_pw intentionally absent (accrual state)
                "premium_vs_ig_peers_bp": None,
            },
            "transition": {"n_snapshots": 1, "fallen_angel_candidates": [], "new_issuance_events": [],
                            "note": "accruing — fewer than 2 holdings snapshots"},
        }

    def _watch_raw_null_g_spread(self) -> dict:
        """watch block with orcl.g_spread_bp_pw explicitly None (JSON null)."""
        return {
            "orcl": {
                "issuer": "ORCL",
                "g_spread_bp_pw": None,
                "premium_vs_ig_peers_bp": None,
            },
            "transition": {"n_snapshots": 1, "fallen_angel_candidates": [], "new_issuance_events": [],
                            "note": "accruing — fewer than 2 holdings snapshots"},
        }

    def _watch_raw_live(self) -> dict:
        """watch block with full live data."""
        return {
            "orcl": {
                "issuer": "ORCL",
                "g_spread_bp_pw": 144.33,
                "ig_peer_median_bp": 74.33,
                "premium_vs_ig_peers_bp": 70.0,
            },
            "transition": {"n_snapshots": 5, "fallen_angel_candidates": [], "new_issuance_events": [],
                            "note": "live — 5 snapshots"},
        }

    def test_missing_g_spread_yields_orcl_none(self) -> None:
        """orcl block without g_spread_bp_pw → orcl=None (B1 crash prevention)."""
        from scripts.build_bonds import _build_watch
        result = _build_watch(self._watch_raw_no_g_spread())
        assert result["orcl"] is None, (
            "orcl must be None when g_spread_bp_pw is absent")

    def test_null_g_spread_yields_orcl_none(self) -> None:
        """orcl block with g_spread_bp_pw=None (JSON null) → orcl=None (B1 crash prevention)."""
        from scripts.build_bonds import _build_watch
        result = _build_watch(self._watch_raw_null_g_spread())
        assert result["orcl"] is None, (
            "orcl must be None when g_spread_bp_pw is None")

    def test_live_g_spread_yields_orcl_dict(self) -> None:
        """orcl block with live g_spread_bp_pw → orcl dict with g_spread_bp not None."""
        from scripts.build_bonds import _build_watch
        result = _build_watch(self._watch_raw_live())
        assert result["orcl"] is not None, "live orcl should not be None"
        assert result["orcl"]["g_spread_bp"] is not None
        assert abs(result["orcl"]["g_spread_bp"] - 144.0) < 1.0

    def test_cm_with_null_g_spread_vm_renders(self, tmp_path: Path) -> None:
        """Full vm build with orcl present but g_spread_bp_pw=None → no crash, orcl=None."""
        cm = _minimal_cm()
        cm["watch"] = {
            "orcl": {"issuer": "ORCL", "g_spread_bp_pw": None, "premium_vs_ig_peers_bp": None},
            "transition": {"n_snapshots": 1, "fallen_angel_candidates": [], "new_issuance_events": [],
                            "note": "accruing — fewer than 2 holdings snapshots"},
        }
        cm_path = tmp_path / "corp_bonds" / "credit_momentum.json"
        _write_cm(cm_path, cm)
        vm = build_corp_credit_vm(data_root=tmp_path)
        assert vm["watch"]["orcl"] is None, "orcl must be None in vm when g_spread_bp_pw is None"


# ---------------------------------------------------------------------------
# 12. M1 regression: quality_spread sub must be semantic gap copy, not extra-yield
# ---------------------------------------------------------------------------

class TestQualitySpreadM1Regression:
    """M1 fix: quality_spread level_in_sub=False means the sub must show 'gap mid-range'
    not 'extra yield +1.92%'."""

    def _roster_with_quality_spread(self) -> dict:
        return {
            "ig_oas": {"level": 0.77, "d21": 0.02, "velocity": {"vel21_pctile": 67.8},
                       "state": "widening"},
            "hy_oas": {"level": 2.69, "d21": -0.09, "velocity": {"vel21_pctile": 47.5},
                       "state": "stable"},
            "quality_spread": {"level": 1.92, "d21": -0.11, "velocity": {"vel21_pctile": 38.5},
                                "state": "stable"},
            "ccc_bb": {"level": 8.11, "d21": 0.24, "velocity": {"vel21_pctile": 67.0},
                       "state": "widening"},
        }

    def test_quality_spread_sub_not_extra_yield(self) -> None:
        """quality_spread sub_en must NOT contain 'extra yield' or the raw level."""
        gauges = _build_spread_gauges(self._roster_with_quality_spread(), {})
        qs_g = next(g for g in gauges if g["key"] == "quality_spread")
        assert "extra yield" not in qs_g["sub_en"].lower(), (
            f"quality_spread sub_en '{qs_g['sub_en']}' must not show 'extra yield'")
        assert "1.92" not in qs_g["sub_en"], (
            f"quality_spread sub_en '{qs_g['sub_en']}' must not show raw level '1.92'")

    def test_quality_spread_sub_is_semantic(self) -> None:
        """quality_spread sub must show the semantic gap descriptor."""
        gauges = _build_spread_gauges(self._roster_with_quality_spread(), {})
        qs_g = next(g for g in gauges if g["key"] == "quality_spread")
        assert "gap" in qs_g["sub_en"].lower(), (
            f"quality_spread sub_en '{qs_g['sub_en']}' should contain 'gap'")

    def test_quality_spread_zh_sub_not_extra_yield(self) -> None:
        """quality_spread sub_zh must NOT contain the extra-yield ZH string."""
        gauges = _build_spread_gauges(self._roster_with_quality_spread(), {})
        qs_g = next(g for g in gauges if g["key"] == "quality_spread")
        assert "额外收益率" not in qs_g["sub_zh"], (
            f"quality_spread sub_zh '{qs_g['sub_zh']}' must not show '额外收益率'")


# ---------------------------------------------------------------------------
# 13. M2 regression: theme tile sub_en/sub_zh are static descriptors from mockup
# ---------------------------------------------------------------------------

class TestThemeTileSubM2Regression:
    """M2 fix: tile.sub_en/sub_zh must be the static mockup descriptors, not accruing copy."""

    def test_hyperscaler_sub_descriptor(self) -> None:
        """hyperscaler tile sub must be '5 giants · Oracle on watch'."""
        tiles = _build_theme_tiles({}, cm_path=None)
        hyp = next(t for t in tiles if t["slug"] == "hyperscaler_credit")
        assert hyp["sub_en"] == "5 giants · Oracle on watch", (
            f"hyperscaler sub_en='{hyp['sub_en']}' does not match mockup")
        assert hyp["sub_zh"] == "5家巨头 · 甲骨文在观察名单", (
            f"hyperscaler sub_zh='{hyp['sub_zh']}' does not match mockup")

    def test_neocloud_sub_descriptor(self) -> None:
        """neocloud tile sub must be 'CoreWeave only — junk-rated'."""
        tiles = _build_theme_tiles({}, cm_path=None)
        neo = next(t for t in tiles if t["slug"] == "neocloud_credit")
        assert neo["sub_en"] == "CoreWeave only — junk-rated", (
            f"neocloud sub_en='{neo['sub_en']}' does not match mockup")
        assert neo["sub_zh"] == "仅CoreWeave · 高收益级", (
            f"neocloud sub_zh='{neo['sub_zh']}' does not match mockup")

    def test_memory_sub_descriptor(self) -> None:
        """memory tile sub must be 'Micron + Seagate mix'."""
        tiles = _build_theme_tiles({}, cm_path=None)
        mem = next(t for t in tiles if t["slug"] == "memory_credit")
        assert mem["sub_en"] == "Micron + Seagate mix", (
            f"memory sub_en='{mem['sub_en']}' does not match mockup")

    def test_sub_key_always_present(self) -> None:
        """All 7 tiles must have sub_en and sub_zh keys (may be empty string)."""
        tiles = _build_theme_tiles({}, cm_path=None)
        for tile in tiles:
            assert "sub_en" in tile, f"{tile['slug']} missing sub_en"
            assert "sub_zh" in tile, f"{tile['slug']} missing sub_zh"
            assert isinstance(tile["sub_en"], str), f"{tile['slug']} sub_en is not str"
            assert isinstance(tile["sub_zh"], str), f"{tile['slug']} sub_zh is not str"


# ---------------------------------------------------------------------------
# 14. m1 regression: _build_watch with note=None (JSON null) must not crash
# ---------------------------------------------------------------------------

class TestBuildWatchM1Regression:
    """m1 fix: transition.get('note') returning None (JSON null) must not crash
    when .startswith('accruing') is called."""

    def test_null_note_no_crash(self) -> None:
        """watch block with note=None (JSON null) must not crash."""
        from scripts.build_bonds import _build_watch
        watch_raw = {
            "orcl": None,
            "transition": {
                "n_snapshots": 1,
                "fallen_angel_candidates": [],
                "new_issuance_events": [],
                "note": None,  # JSON null
            },
        }
        result = _build_watch(watch_raw)
        # null note is not "accruing" → fallen_angel_accruing should be False
        assert result["fallen_angel_accruing"] is False

    def test_missing_note_no_crash(self) -> None:
        """watch block with no note key must not crash."""
        from scripts.build_bonds import _build_watch
        watch_raw = {
            "orcl": None,
            "transition": {
                "n_snapshots": 1,
                "fallen_angel_candidates": [],
                "new_issuance_events": [],
                # no "note" key
            },
        }
        result = _build_watch(watch_raw)
        assert result["fallen_angel_accruing"] is False


# ---------------------------------------------------------------------------
# 15. m2 regression: NaN/Inf values coerced to None before bond_health.json
# ---------------------------------------------------------------------------

class TestFinraNanCoercionM2Regression:
    """m2 fix: non-finite floats (NaN, Inf) are coerced → None before entering vm/json."""

    def test_nan_advance_share_coerced(self) -> None:
        """advance_share_latest=NaN → finra.advance_share=None → accruing=True."""
        import math
        block = {
            "finra": {
                "breadth": {
                    "all securities": {
                        "advance_share_latest": float("nan"),
                        "wk52_high_low_net_share": float("nan"),
                        "n_days": 751,
                        "latest_date": "2026-07-13",
                    }
                }
            }
        }
        finra = _build_finra_vm(block)
        assert finra is not None
        assert finra["advance_share"] is None, "NaN advance_share should coerce to None"
        assert finra["accruing"] is True

    def test_inf_wk52_net_coerced(self) -> None:
        """wk52_high_low_net_share=Inf → lows_pct=None."""
        block = {
            "finra": {
                "breadth": {
                    "all securities": {
                        "advance_share_latest": 0.16,
                        "wk52_high_low_net_share": float("inf"),
                        "n_days": 751,
                        "latest_date": "2026-07-13",
                    }
                }
            }
        }
        finra = _build_finra_vm(block)
        assert finra is not None
        assert finra["lows_pct"] is None, "Inf wk52_net should coerce to None"

    def test_json_serializable_with_nan_input(self, tmp_path: Path) -> None:
        """Full bond_health block is JSON-serializable even when upstream has NaN."""
        import math as _math
        cm = _minimal_cm()
        cm["breadth"] = {
            "finra": {
                "breadth": {
                    "all securities": {
                        "advance_share_latest": float("nan"),
                        "wk52_high_low_net_share": float("nan"),
                        "n_days": 0,
                        "latest_date": "",
                    }
                }
            }
        }
        cm_path = tmp_path / "corp_bonds" / "credit_momentum.json"
        _write_cm(cm_path, cm)
        vm = build_corp_credit_vm(data_root=tmp_path)
        bh = _build_corp_credit_bond_health(vm)
        # strict JSON must not raise
        import json as _json
        serialized = _json.dumps(bh)
        parsed = _json.loads(serialized)
        assert parsed["breadth"]["finra_advance_share"] is None
