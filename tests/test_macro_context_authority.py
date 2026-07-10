"""Authority test wall for PR-B R5 macro lobes and bridge summarizer (§5.5).

All tests are hermetic: synthetic fixture trees, no real market data.

Tests
-----
1.  display_only_on_every_new_lobe  — all R5 lobes carry display_only=True
2.  assert_no_authority_world_state — no Article-2 keys / authority booleans
3.  assert_no_authority_mastermind  — same for bridge artifact
4.  five_bridge_booleans_false      — all five can_* booleans remain False
5.  no_article2_keys_in_new_lobes   — per-lobe Article-2 surface key absence
6.  per_source_missing_file_failopen — each source missing -> gap, no raise
7.  to_iso_format_coverage          — ISO date, display string, ISO datetime, None
8.  no_new_names_in_macro_weather   — tickers in macro_weather are whitelisted
9.  macro_weather_gap_when_snapshot_absent — macro_weather returns gap without snapshot
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

# ─── constants ────────────────────────────────────────────────────────────────

_NOW = datetime(2026, 7, 5, 12, 0, 0, tzinfo=timezone.utc)

# Article-2 surface keys (RUL-M2)
_ARTICLE_2_KEYS = frozenset({
    "alert_triage",
    "board_ordering",
    "top_setups",
    "attention_queue",
    "push_floor",
})

# Five authority booleans
_AUTHORITY_BOOLEANS = frozenset({
    "can_add_candidates",
    "can_raise_size",
    "can_lower_size",
    "can_block_entry",
    "can_force_exit",
})

# Macro ETF / futures root whitelist (RUL-M8)
# These are admissible as macro-level records, NOT candidate names.
_MACRO_TICKER_WHITELIST_PATTERNS = (
    re.compile(r"^(XLB|XLC|XLE|XLF|XLI|XLK|XLP|XLRE|XLU|XLV|XLY)$"),  # SPDR sectors
    re.compile(r"^(QQQ|SPY|IWM|DIA|IWF|IWD)$"),                          # broad indices
    re.compile(r"^(TLT|IEF|SHY|TIP|HYG|LQD)$"),                          # bond ETFs
    re.compile(r"^(GLD|SLV|IAU|PDBC|DBC)$"),                              # commodity ETFs
    re.compile(r"^(FXI|EEM|VWO|EFA|IEFA)$"),                              # intl equity
    re.compile(r"^(GC=F|CL=F|SI=F|HG=F|NG=F|ZC=F|ZS=F|ZW=F)$"),          # futures
    re.compile(r"^(VIX|MOVE|DXY|EURUSD|USDJPY|GBPUSD|AUDUSD|USDCNH)$"),  # macro indices/fx
    re.compile(r"^[A-Z]{2,5}=F$"),  # generic futures root
    re.compile(r"^(EUR|JPY|GBP|AUD|CAD|CNH|CHF|NZD)$"),  # FX codes
    re.compile(r"^(Gold|Copper|Silver|Oil|Gas|Wheat|Corn|Soy)$"),  # commodity display names
    re.compile(r"^(EM|USD assets|USD assets)$"),  # FX/macro groupings
)

# Sectors / asset groups that may appear in headwind_for / tailwind_for
_MACRO_GROUP_PATTERN = re.compile(
    r"^(EM|DM|Asia|Europe|Latam|G10|Commodities?|Equities?|Bonds?|Credit|Gold|Oil)$",
    re.IGNORECASE,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SYNAPSE_YML = _REPO_ROOT / "config" / "synapse.yml"


# ─── fixture helpers ──────────────────────────────────────────────────────────

def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _seed_synapse(root: Path) -> None:
    import shutil
    dest = root / "config" / "synapse.yml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_SYNAPSE_YML, dest)


def _build_minimal_tree(root: Path) -> None:
    """Minimal hermetic fixture tree with all six R5 sources present."""
    _seed_synapse(root)

    # market_state
    _write_json(root / "data" / "market_state" / "latest.json", {
        "schema": "market_state.v2", "asof": "2026-07-05",
        "verdict": "CAUTION", "score": 55, "raw_score": 60,
        "is_display_only": True, "label_en": "Caution", "label_zh": "谨慎",
        "radar": {"state": "caution", "ceiling": 60, "amp": 1.0, "amp_keys": [],
                  "severe_gated": False, "recovery": False, "is_loud": False},
    })

    # regime
    _write_json(root / "data" / "regime" / "latest.json", {
        "quad": "Q1", "quad_name": "Goldilocks", "label": "Goldilocks",
        "confidence": 0.8, "growth_score": 70.0, "inflation_score": 30.0,
        "cycle_tag": "mid", "transition_state": "STABLE", "flip_condition": None,
        "flip_margin": 0.15, "liquidity_quality": "ok", "business_cycle": "expansion",
        "liquidity_overlay": "expanding", "sector_rs": [], "asof": "2026-07-05",
        "schema_version": 1,
        "freshness": {"asof": "2026-07-05", "built_at": "2026-07-05T06:00:00Z",
                      "age_days": 0, "stale": False},
        "risk_radar": {"schema": "risk_radar.v2", "asof": "2026-07-05",
                       "state": "calm", "alert": False, "dominant_scare": None, "scares": []},
        "vol_regime": {"available": True, "asof": "2026-07-05", "regime": "normalizing",
                       "risk_score": -0.1, "scored_score": None, "scored_active": False,
                       "vix": 14.0, "vrp_state": "normal", "vvix_state": "normal",
                       "vol_target_scalar": 1.0, "fragility_confluence": 0, "flags": []},
        "conditions": {"complacency": {"breadth_above200_pctile": 0.6, "breadth_div": False}},
    })

    # run_status
    _write_json(root / "data" / "run_status.json", {
        "last_run": "2026-07-05T06:00:00Z",
        "sources": {"polygon": {"status": "ok", "error": None, "checked_at": "2026-07-05T06:00:00Z"}},
        "circuit_breaker": {}, "stale_series": [],
    })

    # alerts_triage
    _write_json(root / "site" / "factordata" / "alerts_triage.json", {
        "generated_utc": "2026-07-05T06:00:00Z", "asof": "2026-07-05",
        "summary": {"total": 0, "critical": 0, "major": 0, "minor": 0,
                    "actionable": 0, "backtested": 0, "by_source": {}},
        "alerts": [],
    })

    # R5 sources
    _write_json(root / "data" / "transmission" / "latest.json", {
        "asof": "2026-07-05", "state": {}, "scored_status": {"en": "Display-only."},
        "calibrated": True,
        "headwinds": [{"asset": "XLU", "verdict": "headwind", "net": -0.4}],
        "tailwinds": [{"asset": "XLK", "verdict": "tailwind", "net": 0.3}],
        "yield_curve": {
            "regime": {"key": "bear_flattener", "label": "Bear Flattener"},
            "recession": {"risk": "low", "ntfs": "no signal"},
            "shape": {"slope_2s10s": 0.31},
        },
    })

    _write_json(root / "data" / "forex" / "latest.json", {
        "date": "Jul 05, 2026", "regime": "dollar_bull", "risk": "risk_on",
        "favored": ["EUR"],
        "dollar_desk": {"lean": "neutral", "real_rate_regime": "positive",
                        "usd_valuation": "overvalued", "trend": "declining",
                        "fed_path_lean": "hawkish", "liquidity_dir": "tightening"},
        "transmission": {"usd_dir": "down", "headwind_for": ["EM"], "tailwind_for": [],
                         "unstable": False},
        "regime_radar": {"as_of": "2026-07-05", "dominant": "dollar_bull", "active": []},
    })

    _write_json(root / "data" / "bonds" / "bond_health.json", {
        "as_of": "2026-07-05", "health_score": 85, "health_label": "healthy",
        "cycle_phase": "late", "recession_risk": 3.9, "drawdown_risk": 15.1,
        "alarms": [], "verdict_en": "Healthy.", "drivers_for": {},
        "fed_path": {"policy_rate": 5.25, "implied_bp_12m": -75.0, "implied_cuts_12m": 3},
        "bond_compass": {"duration": "short", "curve_trade": "steepener"},
        "bond_cross_asset": {"verdict_en": "Supportive."},
    })

    _write_json(root / "data" / "china_regime" / "latest.json", {
        "date": "2026-07-05", "quad": "Q3", "quad_name": "Stagflation",
        "cycle_tag": "mid", "confidence": 0.185, "liquidity_overlay": "neutral",
        "pending_quad": "Q2",
    })

    _write_json(root / "data" / "hk_regime" / "latest.json", {
        "date": "2026-07-05", "quad": "Q4", "quad_name": "Growth-scare",
        "cycle_tag": "mid", "confidence": 0.083, "liquidity_overlay": "neutral",
        "pending_quad": "Q3", "risk_state": "Neutral", "peg_state": "weak-side",
    })

    _write_json(root / "data" / "canada_regime" / "latest.json", {
        "date": "2026-07-05", "quad": "Q1", "quad_name": "Goldilocks",
        "cycle_tag": "late", "confidence": 0.305, "liquidity_overlay": "neutral",
        "pending_quad": "Q4",
    })

    _write_json(root / "data" / "commodity" / "latest.json", {
        "date": "Jul 05, 2026", "regime": "Goldilocks", "favored": ["Gold"],
        "assets": {
            "gold": {"label": "Gold", "trend": "up", "action": "hold", "conviction": "high"},
        },
    })

    _write_json(root / "site" / "intelligence" / "briefing.json", {
        "as_of": "2026-07-05", "n_universe": 100, "n_priority": 5,
        "n_actionable": 2, "n_divergences": 10,
        "macro_context": {"regime": "Q1", "posture": "neutral", "fed_stance": "hawkish"},
        "priority_queue": [
            {"ticker": "AAPL", "priority": 1, "lean": "long", "read": "Breakout."},
        ],
    })

    # Empty transitions.jsonl (PR-C creates this file; empty is valid)
    p = root / "data" / "macro_snapshots" / "transitions.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("", encoding="utf-8")


def _build_minimal_tree_with_snapshot(root: Path) -> None:
    """Same as _build_minimal_tree but also writes macro_snapshots/latest.json
    and world_state.json so _summarize_macro_weather has data."""
    _build_minimal_tree(root)

    # world_state.json (minimal)
    ws = {
        "fx_dollar": {"regime": "dollar_bull",
                      "dollar_desk": {"trend": "declining"},
                      "transmission": {"usd_dir": "down", "headwind_for": ["EM"],
                                       "tailwind_for": []}},
        "rates_transmission": {"headwinds": [{"asset": "XLU", "verdict": "headwind", "net": -0.4}],
                                "tailwinds": [{"asset": "XLK", "verdict": "tailwind", "net": 0.3}],
                                "yield_curve": {"regime": {"key": "bear_flattener"},
                                                "recession": {"risk": "low"}}},
        "rates_credit": {"health_label": "healthy", "cycle_phase": "late"},
        "commodity_context": {"regime": "Goldilocks", "favored": ["Gold"]},
        "macro_deltas": {"transitions": [], "n_transitions_14d": 0, "display_only": True},
        "contradictions": {"n": 0, "by_severity": {}, "top_pair_ids": [],
                           "gaps": [], "display_only": True},
    }
    _write_json(root / "data" / "neuralweb" / "world_state.json", ws)

    snapshot = {
        "schema": "macro_snapshot.v1.1",
        "asof": "2026-07-05",
        "macro_context_id": "abc123def456789a",
        "labels": {
            "us": {"us_quad": "Q1"},
            "china": {"china_quad": "Q3"},
            "hk": {"hk_quad": "Q4"},
            "canada": {"canada_quad": "Q1"},
        },
        "sources": {},
        "gaps": [],
        "display_only": True,
    }
    _write_json(root / "data" / "macro_snapshots" / "latest.json", snapshot)


# ─── helper: collect all string scalars in a nested structure ─────────────────

def _collect_strings(obj: Any) -> list[str]:
    """Recursively collect all string values from a nested dict/list."""
    out: list[str] = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            out.extend(_collect_strings(v))
    elif isinstance(obj, list):
        for item in obj:
            out.extend(_collect_strings(item))
    return out


def _is_whitelisted_macro_ticker(s: str) -> bool:
    """Return True if *s* is a whitelisted macro ETF / futures / FX ticker."""
    s = s.strip()
    for pattern in _MACRO_TICKER_WHITELIST_PATTERNS:
        if pattern.match(s):
            return True
    if _MACRO_GROUP_PATTERN.match(s):
        return True
    return False


# ─── fixture: crossasset/latest.json with flows block ────────────────────────

def _write_crossasset_fixture(root: Path) -> None:
    """Write a minimal data/crossasset/latest.json fixture with a flows block."""
    _write_json(root / "data" / "crossasset" / "latest.json", {
        "date": "2026-07-05",
        "regime": "mixed / no clear trend",
        "breadth": 0.1,
        "favored": ["equity_us"],
        "correlation": "converging",
        "asof": "2026-07-05",
        "flows": {
            "schema": "crossasset_flows.v1",
            "display_only": True,
            "correlation": {
                "verdict": "converging",
                "absorption_pctile": 0.55,
                "n_markets": 6,
            },
            "breadth": 0.1,
            "trend_top": [
                {"asset": "equity_us", "trend": "up", "z": 0.5},
                {"asset": "gold", "trend": "up", "z": 0.3},
            ],
            "intermarket": [
                {"pair": "copper_gold", "ratio": 0.22, "trend": "mid"},
                {"pair": "stocks_gold", "ratio": 2.1, "trend": "elevated"},
            ],
            "carry": {
                "rows": [{"key": "rates_term", "state": "positive carry", "value": 0.5}],
                "note": "Context only.",
            },
            "leadlag": {"verdict": "contemporaneous", "links": []},
            "global_liquidity": {"asof": "2026-07-05", "state": "expanding",
                                 "accel": "steady", "total_usd_tn": 22.5},
            "funding_stress": {"asof": "2026-07-05", "state": "calm",
                               "score": 25, "spread_bp": 2.1},
            "note": "display-only regime read",
        },
    })


# ─── Test 1: display_only on every new lobe ──────────────────────────────────

class TestDisplayOnly:
    """Every R5+R6 world_state lobe must carry display_only=True."""

    _NEW_LOBES = (
        "rates_transmission",
        "fx_dollar",
        "rates_credit",
        "global_regimes",
        "commodity_context",
        "intelligence",
        "macro_deltas",
        "cross_asset_flows",
    )

    def test_display_only_all_lobes(self, tmp_path):
        from engine.neuralweb.world_state import build_world_state
        _build_minimal_tree(tmp_path)
        _write_crossasset_fixture(tmp_path)
        payload = build_world_state(root=tmp_path, now=_NOW)
        for lobe_key in self._NEW_LOBES:
            assert lobe_key in payload, f"lobe {lobe_key!r} missing from payload"
            assert payload[lobe_key].get("display_only") is True, (
                f"{lobe_key!r}: display_only is not True"
            )

    def test_factor_weather_still_display_only(self, tmp_path):
        from engine.neuralweb.world_state import build_world_state
        _build_minimal_tree(tmp_path)
        payload = build_world_state(root=tmp_path, now=_NOW)
        assert payload["factor_weather"].get("display_only") is True

    def test_cross_asset_flows_display_only_is_true(self, tmp_path):
        """cross_asset_flows carries display_only=True (RUL-CA-1)."""
        from engine.neuralweb.world_state import build_world_state
        _build_minimal_tree(tmp_path)
        _write_crossasset_fixture(tmp_path)
        payload = build_world_state(root=tmp_path, now=_NOW)
        lobe = payload.get("cross_asset_flows") or {}
        assert lobe.get("display_only") is True, "cross_asset_flows.display_only must be True"


# ─── Test 2 + 3: assert_no_authority ─────────────────────────────────────────

class TestNoAuthority:
    """assert_no_authority returns [] on built artifacts."""

    def test_world_state_no_authority_violations(self, tmp_path):
        from engine.neuralweb.world_state import build_world_state
        from engine.neuralweb._law import assert_no_authority
        _build_minimal_tree(tmp_path)
        payload = build_world_state(root=tmp_path, now=_NOW)
        violations = assert_no_authority(payload)
        assert violations == [], f"world_state authority violations: {violations}"

    def test_mastermind_no_authority_violations(self, tmp_path):
        from engine.neuralweb.mastermind_context import build_context
        from engine.neuralweb._law import assert_no_authority
        # _build_minimal_tree provides synapse.yml + necessary files
        _build_minimal_tree(tmp_path)
        # Add minimal mastermind sources
        _write_json(tmp_path / "site" / "factordata" / "us_standouts.json",
                    {"buy": [], "watch": [], "laggards": []})
        _write_json(tmp_path / "site" / "altdata" / "mastermind.json",
                    {"signals": [], "broken_signals": []})
        _write_json(tmp_path / "site" / "basketdata" / "radar_ticker.json", {"rows": []})
        _write_json(tmp_path / "site" / "neuralwebdata" / "bottom_sensors.json",
                    {"as_of": "2026-07-05", "rows": [], "n_rows": 0})

        payload = build_context(root=tmp_path, now=_NOW)
        violations = assert_no_authority(payload)
        assert violations == [], f"mastermind authority violations: {violations}"


# ─── Test 4: five bridge booleans false ──────────────────────────────────────

class TestBridgeBooleansFalse:
    def test_authority_booleans_all_false(self, tmp_path):
        from engine.neuralweb.mastermind_context import build_context
        _build_minimal_tree(tmp_path)
        _write_json(tmp_path / "site" / "factordata" / "us_standouts.json",
                    {"buy": [], "watch": [], "laggards": []})
        _write_json(tmp_path / "site" / "altdata" / "mastermind.json",
                    {"signals": [], "broken_signals": []})
        _write_json(tmp_path / "site" / "basketdata" / "radar_ticker.json", {"rows": []})
        _write_json(tmp_path / "site" / "neuralwebdata" / "bottom_sensors.json",
                    {"as_of": "2026-07-05", "rows": [], "n_rows": 0})
        payload = build_context(root=tmp_path, now=_NOW)
        auth = payload.get("authority") or {}
        for key in _AUTHORITY_BOOLEANS:
            assert auth.get(key) is False, f"authority.{key} should be False"


# ─── Test 5: no Article-2 keys in any new lobe ───────────────────────────────

class TestNoArticle2Keys:
    _NEW_LOBES = (
        "rates_transmission",
        "fx_dollar",
        "rates_credit",
        "global_regimes",
        "commodity_context",
        "intelligence",
        "macro_deltas",
        "cross_asset_flows",
    )

    def test_no_article2_keys(self, tmp_path):
        from engine.neuralweb.world_state import build_world_state
        _build_minimal_tree(tmp_path)
        _write_crossasset_fixture(tmp_path)
        payload = build_world_state(root=tmp_path, now=_NOW)
        for lobe_key in self._NEW_LOBES:
            lobe = payload.get(lobe_key) or {}
            found = _ARTICLE_2_KEYS & set(_collect_strings(list(lobe.keys())))
            assert not found, (
                f"{lobe_key!r} contains Article-2 surface key(s): {found}"
            )


# ─── Test 6: per-source missing-file fail-open ───────────────────────────────

class TestPerSourceFailOpen:
    """Each R5 source missing individually → gap entry, others unaffected, no raise."""

    def _payload_without(self, tmp_path: Path, skip_file: str) -> dict:
        from engine.neuralweb.world_state import build_world_state
        _build_minimal_tree(tmp_path)
        target = tmp_path / skip_file
        if target.exists():
            target.unlink()
        return build_world_state(root=tmp_path, now=_NOW)

    def test_missing_transmission(self, tmp_path):
        payload = self._payload_without(tmp_path, "data/transmission/latest.json")
        assert payload["rates_transmission"].get("display_only") is True
        assert any("transmission" in g for g in payload["gaps"])

    def test_missing_forex(self, tmp_path):
        payload = self._payload_without(tmp_path, "data/forex/latest.json")
        assert payload["fx_dollar"].get("display_only") is True
        assert any("forex" in g for g in payload["gaps"])

    def test_missing_bond_health(self, tmp_path):
        payload = self._payload_without(tmp_path, "data/bonds/bond_health.json")
        assert payload["rates_credit"].get("display_only") is True
        assert any("bond" in g for g in payload["gaps"])

    def test_missing_china_regime(self, tmp_path):
        payload = self._payload_without(tmp_path, "data/china_regime/latest.json")
        assert payload["global_regimes"].get("display_only") is True
        assert any("china_regime" in g for g in payload["gaps"])

    def test_missing_hk_regime(self, tmp_path):
        payload = self._payload_without(tmp_path, "data/hk_regime/latest.json")
        assert payload["global_regimes"].get("display_only") is True
        assert any("hk_regime" in g for g in payload["gaps"])

    def test_missing_canada_regime(self, tmp_path):
        payload = self._payload_without(tmp_path, "data/canada_regime/latest.json")
        assert payload["global_regimes"].get("display_only") is True
        assert any("canada_regime" in g for g in payload["gaps"])

    def test_missing_commodity(self, tmp_path):
        payload = self._payload_without(tmp_path, "data/commodity/latest.json")
        assert payload["commodity_context"].get("display_only") is True
        assert any("commodity" in g for g in payload["gaps"])

    def test_missing_briefing(self, tmp_path):
        payload = self._payload_without(tmp_path, "site/intelligence/briefing.json")
        assert payload["intelligence"].get("display_only") is True
        assert any("briefing" in g or "intelligence" in g for g in payload["gaps"])

    def test_missing_transitions(self, tmp_path):
        """transitions.jsonl absent -> gap entry + null macro_deltas (expected)."""
        payload = self._payload_without(
            tmp_path, "data/macro_snapshots/transitions.jsonl"
        )
        assert payload["macro_deltas"].get("display_only") is True
        assert any("transitions" in g or "macro_snapshots" in g for g in payload["gaps"])

    def test_no_raise_any_source_missing(self, tmp_path):
        """All R5 sources missing simultaneously — no exception, display_only preserved."""
        from engine.neuralweb.world_state import build_world_state
        _build_minimal_tree(tmp_path)
        for f in [
            "data/transmission/latest.json",
            "data/forex/latest.json",
            "data/bonds/bond_health.json",
            "data/china_regime/latest.json",
            "data/hk_regime/latest.json",
            "data/canada_regime/latest.json",
            "data/commodity/latest.json",
            "site/intelligence/briefing.json",
        ]:
            p = tmp_path / f
            if p.exists():
                p.unlink()
        payload = build_world_state(root=tmp_path, now=_NOW)
        for lobe_key in ("rates_transmission", "fx_dollar", "rates_credit",
                         "global_regimes", "commodity_context", "intelligence"):
            assert payload[lobe_key].get("display_only") is True, (
                f"{lobe_key} should still have display_only=True when source absent"
            )


# ─── Test 7: to_iso format coverage ──────────────────────────────────────────

class TestToIso:
    def test_iso_date_passthrough(self):
        from engine.neuralweb._dates import to_iso
        assert to_iso("2026-07-05") == "2026-07-05"

    def test_display_string(self):
        from engine.neuralweb._dates import to_iso
        assert to_iso("Jul 05, 2026") == "2026-07-05"

    def test_iso_datetime(self):
        from engine.neuralweb._dates import to_iso
        assert to_iso("2026-07-05T12:00:00Z") == "2026-07-05"

    def test_none_returns_none(self):
        from engine.neuralweb._dates import to_iso
        assert to_iso(None) is None

    def test_empty_string_returns_none(self):
        from engine.neuralweb._dates import to_iso
        assert to_iso("") is None

    def test_unrecognised_returns_none(self):
        from engine.neuralweb._dates import to_iso
        assert to_iso("not-a-date") is None

    def test_iso_date_with_space_separator(self):
        from engine.neuralweb._dates import to_iso
        assert to_iso("2026-07-05 06:00:00") == "2026-07-05"

    def test_single_digit_day(self):
        from engine.neuralweb._dates import to_iso
        assert to_iso("Jul 5, 2026") == "2026-07-05"


# ─── Test 8: no-new-names in macro_weather ───────────────────────────────────

class TestNoNewNamesInMacroWeather:
    """No single-name ticker outside the macro ETF/futures whitelist may appear
    in the macro_weather lobe (RUL-M8 / §5.5 no-new-names extension).

    What counts as a "single name": a ticker-like string matching /^[A-Z]{1,5}$/
    that does NOT appear in the whitelist.
    """

    _SINGLE_NAME_RE = re.compile(r"^[A-Z]{1,5}$")

    def _is_suspect_ticker(self, s: str) -> bool:
        """Return True if *s* looks like a single-name ticker AND is NOT whitelisted."""
        s = s.strip()
        if not self._SINGLE_NAME_RE.match(s):
            return False
        return not _is_whitelisted_macro_ticker(s)

    def test_macro_weather_no_new_names(self, tmp_path):
        from engine.neuralweb.mastermind_context import _summarize_macro_weather
        _build_minimal_tree_with_snapshot(tmp_path)
        lobe, gap = _summarize_macro_weather(tmp_path)
        if gap:
            pytest.skip(f"macro_weather returned gap (expected if snapshot absent): {gap}")
        all_strings = _collect_strings(lobe)
        suspect = [s for s in all_strings if self._is_suspect_ticker(s)]
        assert suspect == [], (
            f"macro_weather contains non-whitelisted single-name ticker(s): {suspect}"
        )


# ─── Test 9: macro_weather returns gap when snapshot absent ──────────────────

class TestMacroWeatherGapOnAbsentSnapshot:
    def test_gap_when_no_snapshot(self, tmp_path):
        from engine.neuralweb.mastermind_context import _summarize_macro_weather
        _build_minimal_tree(tmp_path)
        # transitions.jsonl is present from _build_minimal_tree
        # but macro_snapshots/latest.json is NOT present
        lobe, gap = _summarize_macro_weather(tmp_path)
        assert gap is not None, "expected a gap string when snapshot absent"
        assert isinstance(gap, str) and gap, "gap should be a non-empty string"
        assert lobe == {} or lobe is not None  # lobe can be empty dict

    def test_no_gap_when_snapshot_present(self, tmp_path):
        from engine.neuralweb.mastermind_context import _summarize_macro_weather
        _build_minimal_tree_with_snapshot(tmp_path)
        lobe, gap = _summarize_macro_weather(tmp_path)
        assert gap is None, f"expected no gap with snapshot present; got: {gap}"
        assert lobe.get("display_only") is True
        assert lobe.get("macro_context_id") == "abc123def456789a"


# ─── Test 10: law module unit tests ──────────────────────────────────────────

class TestLaw:
    def test_display_only_sets_flag(self):
        from engine.neuralweb._law import display_only
        d = {"a": 1}
        result = display_only(d)
        assert result["display_only"] is True
        assert result is d  # mutates in place and returns same dict

    def test_assert_no_authority_clean(self):
        from engine.neuralweb._law import assert_no_authority
        clean = {"foo": "bar", "nested": {"baz": 42}}
        assert assert_no_authority(clean) == []

    def test_assert_no_authority_catches_boolean(self):
        from engine.neuralweb._law import assert_no_authority
        bad = {"can_add_candidates": True}
        violations = assert_no_authority(bad)
        assert any("can_add_candidates" in v for v in violations)

    def test_assert_no_authority_false_boolean_ok(self):
        from engine.neuralweb._law import assert_no_authority
        ok = {"can_add_candidates": False}
        assert assert_no_authority(ok) == []

    def test_assert_no_authority_catches_article2(self):
        from engine.neuralweb._law import assert_no_authority
        bad = {"alert_triage": [1, 2, 3]}
        violations = assert_no_authority(bad)
        assert any("alert_triage" in v for v in violations)

    def test_assert_no_authority_catches_scored_path_surfaces(self):
        from engine.neuralweb._law import assert_no_authority
        bad = {"scored_path_surfaces": ["some_surface"]}
        violations = assert_no_authority(bad)
        assert any("scored_path_surfaces" in v for v in violations)

    def test_assert_no_authority_empty_scored_path_surfaces_ok(self):
        from engine.neuralweb._law import assert_no_authority
        ok = {"scored_path_surfaces": []}
        assert assert_no_authority(ok) == []

    def test_assert_no_authority_nested(self):
        from engine.neuralweb._law import assert_no_authority
        nested = {"lobes": {"market": {"can_force_exit": True}}}
        violations = assert_no_authority(nested)
        assert any("can_force_exit" in v for v in violations)


# ─── Tests 11–15: R6 cross_asset_flows authority wall ────────────────────────

class TestCrossAssetFlowsAuthority:
    """R6 authority wall: cross_asset_flows lobe — RUL-CA-1 enforcement."""

    def test_cross_asset_flows_assert_no_authority(self, tmp_path):
        """assert_no_authority returns [] for cross_asset_flows."""
        from engine.neuralweb.world_state import build_world_state
        from engine.neuralweb._law import assert_no_authority
        _build_minimal_tree(tmp_path)
        _write_crossasset_fixture(tmp_path)
        payload = build_world_state(root=tmp_path, now=_NOW)
        lobe = payload.get("cross_asset_flows") or {}
        violations = assert_no_authority(lobe)
        assert violations == [], f"cross_asset_flows authority violations: {violations}"

    def test_cross_asset_flows_no_article2_keys(self, tmp_path):
        """No Article-2 surface keys present in cross_asset_flows."""
        from engine.neuralweb.world_state import build_world_state
        _build_minimal_tree(tmp_path)
        _write_crossasset_fixture(tmp_path)
        payload = build_world_state(root=tmp_path, now=_NOW)
        lobe = payload.get("cross_asset_flows") or {}
        found = _ARTICLE_2_KEYS & set(_collect_strings(list(lobe.keys())))
        assert not found, f"cross_asset_flows contains Article-2 key(s): {found}"

    def test_cross_asset_flows_absent_source_per_lobe_gap(self, tmp_path):
        """data/crossasset/latest.json absent → per-lobe gap, other lobes unaffected."""
        from engine.neuralweb.world_state import build_world_state
        _build_minimal_tree(tmp_path)
        # Do NOT write crossasset fixture — file is absent
        payload = build_world_state(root=tmp_path, now=_NOW)
        # cross_asset_flows lobe must have display_only=True even when source absent
        lobe = payload.get("cross_asset_flows") or {}
        assert lobe.get("display_only") is True, (
            "cross_asset_flows.display_only must be True even when source absent"
        )
        # other lobes must still be present and unaffected
        for other in ("rates_transmission", "fx_dollar", "rates_credit",
                      "global_regimes", "commodity_context"):
            assert payload.get(other) is not None, (
                f"{other} should be present even when crossasset source absent"
            )
        # gap should mention crossasset
        assert any("crossasset" in g for g in payload["gaps"]), (
            "expected a gap entry mentioning 'crossasset' when source absent"
        )

    def test_macro_weather_with_cross_asset_block_size(self, tmp_path):
        """macro_weather serialized < 200 KB with the new cross_asset sub-block."""
        from engine.neuralweb.mastermind_context import _summarize_macro_weather
        _build_minimal_tree_with_snapshot(tmp_path)
        # Also write crossasset fixture + wire into world_state.json
        _write_crossasset_fixture(tmp_path)
        # Patch world_state.json to include cross_asset_flows
        ws_path = tmp_path / "data" / "neuralweb" / "world_state.json"
        import json as _json
        ws = _json.loads(ws_path.read_text())
        ws["cross_asset_flows"] = {
            "regime": "mixed / no clear trend",
            "correlation": {"verdict": "converging", "absorption_pctile": 0.55, "n_markets": 6},
            "intermarket": [{"pair": "copper_gold", "ratio": 0.22, "trend": "mid"}],
            "breadth": 0.1,
            "leadlag": {"verdict": "contemporaneous", "n_links": 0},
            "display_only": True,
        }
        ws_path.write_text(_json.dumps(ws))
        lobe, gap = _summarize_macro_weather(tmp_path)
        if gap:
            pytest.skip(f"macro_weather returned gap: {gap}")
        serialized = _json.dumps(lobe)
        assert len(serialized.encode("utf-8")) < 200 * 1024, (
            f"macro_weather exceeds 200 KB: {len(serialized.encode('utf-8'))} bytes"
        )
        # cross_asset sub-block must be present
        assert "cross_asset" in lobe, "macro_weather must include 'cross_asset' sub-block"

    def test_macro_weather_cross_asset_no_new_names(self, tmp_path):
        """cross_asset sub-block in macro_weather has no non-whitelisted tickers."""
        from engine.neuralweb.mastermind_context import _summarize_macro_weather
        _build_minimal_tree_with_snapshot(tmp_path)
        _write_crossasset_fixture(tmp_path)
        import json as _json
        ws_path = tmp_path / "data" / "neuralweb" / "world_state.json"
        ws = _json.loads(ws_path.read_text())
        ws["cross_asset_flows"] = {
            "regime": "mixed / no clear trend",
            "correlation": {"verdict": "converging", "absorption_pctile": 0.55, "n_markets": 6},
            "intermarket": [{"pair": "copper_gold", "ratio": 0.22, "trend": "mid"}],
            "breadth": 0.1,
            "leadlag": {"verdict": "contemporaneous", "n_links": 0},
            "display_only": True,
        }
        ws_path.write_text(_json.dumps(ws))
        lobe, gap = _summarize_macro_weather(tmp_path)
        if gap:
            pytest.skip(f"macro_weather returned gap: {gap}")
        single_name_re = re.compile(r"^[A-Z]{1,5}$")
        ca_block = lobe.get("cross_asset") or {}
        ca_strings = _collect_strings(ca_block)
        suspect = [
            s for s in ca_strings
            if single_name_re.match(s) and not _is_whitelisted_macro_ticker(s)
        ]
        assert suspect == [], (
            f"cross_asset sub-block contains non-whitelisted ticker(s): {suspect}"
        )
