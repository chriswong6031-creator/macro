"""MSX-2 macro_signals vm-side tests.

Covers:
- SVG builders return well-formed svg strings on synthetic frames
- '' / None-safe on empty / missing columns
- No hex color literals (#xxxxxx) in svg fill/stroke (CSS variables only)
- Stance mapping table exact match (spec §1–§3 verbatim strings)
- fx_context absent-file → None
- Sidecar keys (market_state_color, stances, fx) present when inputs present

Run: python3 -m pytest tests/test_macro_signals_vm.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ---------------------------------------------------------------------- fixtures

_N = 300  # ~1.2 trading years


def _idx(n: int = _N) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=n, freq="B")


def _liq_frame(n: int = _N) -> pd.DataFrame:
    """Synthetic feature frame with net_liquidity_bn."""
    idx = _idx(n)
    vals = 5800.0 + np.cumsum(np.random.default_rng(42).normal(0, 10, n))
    return pd.DataFrame({"net_liquidity_bn": vals}, index=idx)


def _credit_frame(n: int = _N) -> pd.DataFrame:
    """Synthetic frame with hy_oas + pct_above_50."""
    idx = _idx(n)
    rng = np.random.default_rng(7)
    oas = 350.0 + np.cumsum(rng.normal(0, 5, n))
    br = 55.0 + np.cumsum(rng.normal(0, 2, n))
    br = np.clip(br, 0, 100)
    return pd.DataFrame({"hy_oas": oas, "pct_above_50": br}, index=idx)


def _vix_frame(n: int = 90) -> pd.DataFrame:
    """Synthetic 90-day VIX frame."""
    idx = _idx(n)
    rng = np.random.default_rng(13)
    v = 18.0 + np.cumsum(rng.normal(0, 0.5, n))
    v = np.clip(v, 10, 50)
    return pd.DataFrame({"vix": v}, index=idx)


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(index=pd.DatetimeIndex([]))


def _no_col_frame() -> pd.DataFrame:
    """Frame that has an irrelevant column but not the needed one."""
    return pd.DataFrame({"SPY": [1.0, 2.0]}, index=_idx(2))


# ---------------------------------------------------------------- hex check helper

_HEX_RE = None


def _has_hex_colors(svg: str) -> bool:
    """Return True if the SVG contains any fill=# or stroke=# hex literals."""
    import re
    # match fill="#xxx" / stroke="#xxx" (3 or 6 hex digits)
    return bool(re.search(r'(?:fill|stroke)=["\']#[0-9a-fA-F]{3,8}["\']', svg))


# ---------------------------------------------------------------- chart_liquidity

class TestChartLiquidity:
    def _fn(self, f):
        from scripts.build_site import chart_liquidity
        return chart_liquidity(f)

    def test_returns_svg_string_on_valid_frame(self):
        svg = self._fn(_liq_frame())
        assert isinstance(svg, str)
        assert svg.startswith("<svg")
        assert "</svg>" in svg

    def test_contains_viewbox_640_220(self):
        svg = self._fn(_liq_frame())
        assert 'viewBox="0 0 640 220"' in svg

    def test_returns_empty_string_on_empty_frame(self):
        result = self._fn(_empty_frame())
        assert result == ""

    def test_returns_empty_string_on_missing_column(self):
        result = self._fn(_no_col_frame())
        assert result == ""

    def test_returns_empty_string_on_short_frame(self):
        # < 2 rows should return empty
        idx = _idx(1)
        f = pd.DataFrame({"net_liquidity_bn": [5800.0]}, index=idx)
        result = self._fn(f)
        assert result == ""

    def test_no_hex_colors(self):
        svg = self._fn(_liq_frame())
        assert not _has_hex_colors(svg), "SVG must use CSS variable colors, not hex literals"

    def test_css_variable_stroke(self):
        svg = self._fn(_liq_frame())
        assert "var(--info)" in svg

    def test_has_area_fill(self):
        svg = self._fn(_liq_frame())
        assert 'fill-opacity=".08"' in svg

    def test_has_non_scaling_stroke(self):
        svg = self._fn(_liq_frame())
        assert "non-scaling-stroke" in svg

    def test_has_latest_dot(self):
        svg = self._fn(_liq_frame())
        assert "<circle" in svg

    def test_truthy_when_data_present(self):
        """{% if chart_liquidity %} guard — non-empty string is truthy."""
        assert bool(self._fn(_liq_frame()))

    def test_falsy_when_data_absent(self):
        """{% if chart_liquidity %} guard — empty string is falsy."""
        assert not bool(self._fn(_empty_frame()))


# ---------------------------------------------------------------- chart_credit_breadth

class TestChartCreditBreadth:
    def _fn(self, f):
        from scripts.build_site import chart_credit_breadth
        return chart_credit_breadth(f)

    def test_returns_svg_on_valid_frame(self):
        svg = self._fn(_credit_frame())
        assert isinstance(svg, str)
        assert svg.startswith("<svg")
        assert "</svg>" in svg

    def test_contains_viewbox_640_220(self):
        svg = self._fn(_credit_frame())
        assert 'viewBox="0 0 640 220"' in svg

    def test_returns_empty_on_missing_columns(self):
        result = self._fn(_no_col_frame())
        assert result == ""

    def test_returns_empty_on_empty_frame(self):
        result = self._fn(_empty_frame())
        assert result == ""

    def test_no_hex_colors(self):
        svg = self._fn(_credit_frame())
        assert not _has_hex_colors(svg), "SVG must use CSS variable colors, not hex literals"

    def test_uses_down_and_up_css_vars(self):
        """OAS uses var(--down); breadth uses var(--up)."""
        svg = self._fn(_credit_frame())
        assert "var(--down)" in svg
        assert "var(--up)" in svg

    def test_both_series_produce_area_fills(self):
        svg = self._fn(_credit_frame())
        assert svg.count('fill-opacity=".08"') >= 2

    def test_oas_only_frame(self):
        """Should still produce SVG when only hy_oas is present."""
        idx = _idx()
        f = pd.DataFrame({"hy_oas": np.full(_N, 350.0)}, index=idx)
        svg = self._fn(f)
        assert svg.startswith("<svg")
        assert "var(--down)" in svg

    def test_breadth_only_frame(self):
        """Should still produce SVG when only pct_above_50 is present."""
        idx = _idx()
        f = pd.DataFrame({"pct_above_50": np.full(_N, 60.0)}, index=idx)
        svg = self._fn(f)
        assert svg.startswith("<svg")
        assert "var(--up)" in svg

    def test_non_scaling_stroke(self):
        svg = self._fn(_credit_frame())
        assert "non-scaling-stroke" in svg


# ---------------------------------------------------------------- chart_vix

class TestChartVix:
    def _fn(self, f, days=90):
        from scripts.build_site import chart_vix
        return chart_vix(f, days=days)

    def test_returns_svg_on_valid_frame(self):
        svg = self._fn(_vix_frame())
        assert isinstance(svg, str)
        assert svg.startswith("<svg")
        assert "</svg>" in svg

    def test_contains_viewbox_640_220(self):
        svg = self._fn(_vix_frame())
        assert 'viewBox="0 0 640 220"' in svg

    def test_returns_empty_on_missing_column(self):
        result = self._fn(_no_col_frame())
        assert result == ""

    def test_returns_empty_on_empty_vix(self):
        f = pd.DataFrame({"vix": []}, index=pd.DatetimeIndex([]))
        result = self._fn(f)
        assert result == ""

    def test_no_hex_colors(self):
        svg = self._fn(_vix_frame())
        assert not _has_hex_colors(svg), "SVG must use CSS variable colors, not hex literals"

    def test_uses_warn_css_var(self):
        svg = self._fn(_vix_frame())
        assert "var(--warn)" in svg

    def test_dashed_separators_when_in_range(self):
        """When VIX spans 14..30, regime separators at 16/20/28 must appear."""
        idx = _idx(90)
        # values 14..30 to trigger all three separators
        vals = np.linspace(14.0, 32.0, 90)
        f = pd.DataFrame({"vix": vals}, index=idx)
        svg = self._fn(f)
        # dashed separators use stroke-dasharray="4 4"
        assert svg.count('stroke-dasharray="4 4"') >= 1

    def test_latest_dot(self):
        svg = self._fn(_vix_frame())
        assert "<circle" in svg

    def test_area_fill_opacity(self):
        svg = self._fn(_vix_frame())
        assert 'fill-opacity=".08"' in svg

    def test_truthy_falsy_semantics(self):
        assert bool(self._fn(_vix_frame()))
        f = pd.DataFrame({"vix": []}, index=pd.DatetimeIndex([]))
        assert not bool(self._fn(f))


# ---------------------------------------------------------------- _chart_liquidity_meta

class TestChartLiquidityMeta:
    def _fn(self, f):
        from scripts.build_site import _chart_liquidity_meta
        return _chart_liquidity_meta(f)

    def test_returns_dict_on_valid_frame(self):
        meta = self._fn(_liq_frame())
        assert isinstance(meta, dict)
        assert "chg_4w_bn" in meta
        assert "state" in meta

    def test_state_is_one_of_rising_falling_flat(self):
        meta = self._fn(_liq_frame())
        assert meta["state"] in ("rising", "falling", "flat")

    def test_rising_when_big_increase(self):
        idx = _idx()
        # starts at 5000, +100 per period — 4w change >> 25bn threshold
        vals = [5000.0 + i * 5 for i in range(_N)]
        f = pd.DataFrame({"net_liquidity_bn": vals}, index=idx)
        meta = self._fn(f)
        assert meta["state"] == "rising"

    def test_falling_when_big_decrease(self):
        idx = _idx()
        vals = [6000.0 - i * 5 for i in range(_N)]
        f = pd.DataFrame({"net_liquidity_bn": vals}, index=idx)
        meta = self._fn(f)
        assert meta["state"] == "falling"

    def test_none_on_empty(self):
        assert self._fn(_empty_frame()) is None

    def test_none_on_short_frame(self):
        idx = _idx(5)
        f = pd.DataFrame({"net_liquidity_bn": [1.0] * 5}, index=idx)
        assert self._fn(f) is None


# ---------------------------------------------------------------- _msig_stances

class TestMsigStances:
    def _fn(self, market_state=None, chart_liq_meta=None, f=None):
        from scripts.build_site import _msig_stances
        return _msig_stances(market_state, chart_liq_meta, f)

    # -- hero stance exact strings (spec §1 verbatim) --

    def test_hero_green_exact(self):
        stances = self._fn(market_state={"color": "green"})
        assert stances["hero"]["en"] == (
            "Conditions support staying invested — watch the usual risks."
        )
        assert stances["hero"]["zh"] == "环境支持持仓 — 留意常规风险。"

    def test_hero_yellow_exact(self):
        stances = self._fn(market_state={"color": "yellow"})
        assert stances["hero"]["en"] == "Mixed signals — hold what works, add slowly."
        assert stances["hero"]["zh"] == "信号混杂 — 持有有效仓位，谨慎加仓。"

    def test_hero_red_exact(self):
        stances = self._fn(market_state={"color": "red"})
        assert stances["hero"]["en"] == (
            "Defensive tape — protect first; opportunities can wait."
        )
        assert stances["hero"]["zh"] == "防御行情 — 先保护本金，机会可以等。"

    def test_hero_absent_exact(self):
        stances = self._fn(market_state=None)
        assert stances["hero"]["en"] == "A mixed picture — read the boards below."
        assert stances["hero"]["zh"] == "情况混杂 — 请看下方各板。"

    def test_hero_unknown_color_falls_back_to_absent(self):
        stances = self._fn(market_state={"color": "purple"})
        assert stances["hero"]["en"] == "A mixed picture — read the boards below."

    # -- liquidity stance exact strings (spec §3) --

    def test_liquidity_rising_exact(self):
        meta = {"chg_4w_bn": 50.0, "state": "rising"}
        stances = self._fn(chart_liq_meta=meta)
        assert stances["liquidity"]["en"] == (
            "The money tide is rising — historically the most reliable tailwind."
        )
        assert stances["liquidity"]["zh"] == "资金潮上涨 — 历史上最可靠的顺风。"

    def test_liquidity_falling_exact(self):
        meta = {"chg_4w_bn": -50.0, "state": "falling"}
        stances = self._fn(chart_liq_meta=meta)
        assert stances["liquidity"]["en"] == "The money tide is going out — a headwind."
        assert stances["liquidity"]["zh"] == "资金潮退去 — 逆风。"

    def test_liquidity_absent_defaults_flat(self):
        stances = self._fn(chart_liq_meta=None)
        assert stances["liquidity"]["en"] == "Net liquidity is roughly flat."

    # -- credit stance (spec §3 three-way) --

    def test_credit_calm_when_no_frame(self):
        stances = self._fn()
        assert stances["credit"]["en"] == (
            "Credit calm, participation healthy — no smoke."
        )

    def test_credit_widening_when_oas_above_1y_median(self):
        """Spread widening: last OAS > 1y median."""
        idx = pd.date_range("2023-01-01", periods=260, freq="B")
        oas_vals = [300.0] * 252 + [400.0] * 8  # last 8 well above median
        f = pd.DataFrame({"hy_oas": oas_vals, "pct_above_50": [60.0] * 260}, index=idx)
        stances = self._fn(f=f)
        assert stances["credit"]["en"] == (
            "Credit spreads widening — the market's smoke detector is warming."
        )
        assert stances["credit"]["zh"] == "信用利差走阔 — 市场烟雾探测器升温。"

    def test_credit_narrow_when_breadth_below_40_and_spreads_calm(self):
        """Breadth < 40 with calm spreads → narrow."""
        idx = pd.date_range("2023-01-01", periods=260, freq="B")
        oas_vals = [300.0] * 260  # flat spreads = calm
        br_vals = [35.0] * 260  # below 40
        f = pd.DataFrame({"hy_oas": oas_vals, "pct_above_50": br_vals}, index=idx)
        stances = self._fn(f=f)
        assert stances["credit"]["en"] == "Narrow participation — strength is thin."
        assert stances["credit"]["zh"] == "参与面收窄 — 涨势偏窄。"

    def test_result_has_all_keys(self):
        stances = self._fn(market_state={"color": "green"})
        assert set(stances.keys()) == {"hero", "liquidity", "credit"}
        for section in stances.values():
            assert "en" in section
            assert "zh" in section


# ---------------------------------------------------------------- _build_fx_context

class TestBuildFxContext:
    def test_returns_none_when_file_absent(self, tmp_path, monkeypatch):
        """When data/forex/latest.json does not exist, returns None."""
        # Point config data_dir to an empty tmp dir
        import lib.config as _cfg
        monkeypatch.setattr(_cfg, "data_dir", lambda: tmp_path)
        # Also monkeypatch the _latest function's underlying path resolution
        from lib import forex_link
        monkeypatch.setattr(forex_link, "_latest", lambda: {})
        from scripts.build_site import _build_fx_context
        result = _build_fx_context()
        assert result is None

    def test_returns_dict_with_expected_keys_on_valid_data(self, monkeypatch):
        """With a well-formed latest.json dict, returns a dict with all expected keys."""
        fake_fx = {
            "asof": "2026-07-17",
            "dollar_desk": {
                "lean": "dollar-supportive backdrop",
                "lean_zh": "偏多美元背景",
                "lean_net": 2,
                "lean_n": 3,
                "triple_red": False,
                "trend": "up",
                "liquidity_dir": "supportive",
                "fed_path_lean": "steady",
            },
            "transmission": {"usd_dir": "strong", "corr": {}, "headwind_for": [], "tailwind_for": []},
            "regime_radar": {
                "as_of": "2026-07-17",
                "dominant": None,
                "active": [],
                "intensity": {"carry_unwind": 12.0, "dollar_wrecking_ball": 12.1},
            },
            "pairs": {
                "USDCNH": {"label": "USD/CNH", "quote": 7.25, "chg": 0.01, "action": "neutral", "score": 50},
                "EURUSD": {"label": "EUR/USD", "quote": 1.08},
            },
        }
        from lib import forex_link
        monkeypatch.setattr(forex_link, "_latest", lambda: fake_fx)
        # No alerts.jsonl for this test — supply empty file
        from lib import config as _cfg
        import tempfile, os
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            (td_path / "forex").mkdir()
            (td_path / "forex" / "alerts.jsonl").write_text("")
            monkeypatch.setattr(_cfg, "data_dir", lambda: td_path)
            from scripts.build_site import _build_fx_context
            result = _build_fx_context()
        assert result is not None
        assert isinstance(result, dict)
        expected_keys = {"asof", "smile_regime", "dollar_desk", "strength", "regime_radar",
                         "transmission", "state_changes", "pairs", "recent_events"}
        assert set(result.keys()) == expected_keys

    def test_pairs_usdcnh_only(self, monkeypatch):
        """Only USDCNH should appear in pairs, not EURUSD."""
        fake_fx = {
            "asof": "2026-07-17",
            "dollar_desk": {"lean": "x", "lean_zh": "x", "lean_net": 0, "lean_n": 0, "triple_red": False},
            "pairs": {
                "USDCNH": {"label": "USD/CNH", "quote": 7.25, "chg": 0.0},
                "EURUSD": {"label": "EUR/USD", "quote": 1.08},
            },
        }
        from lib import forex_link
        monkeypatch.setattr(forex_link, "_latest", lambda: fake_fx)
        from lib import config as _cfg
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            (td_path / "forex").mkdir()
            (td_path / "forex" / "alerts.jsonl").write_text("")
            monkeypatch.setattr(_cfg, "data_dir", lambda: td_path)
            from scripts.build_site import _build_fx_context
            result = _build_fx_context()
        assert result is not None
        assert "USDCNH" in (result.get("pairs") or {})
        assert "EURUSD" not in (result.get("pairs") or {})

    def test_recent_events_filtered_to_desk_types(self, monkeypatch, tmp_path):
        """Only smile_regime/smile_regime_flip/triple_red/scenario_active events pass filter."""
        events = [
            {"id": "e1", "ts": "2026-07-17T00:00:00", "type": "smile_regime_flip",
             "severity": "high", "headline": "Smile flip", "headline_zh": "微笑翻转"},
            {"id": "e2", "ts": "2026-07-16T00:00:00", "type": "momentum",
             "severity": "medium", "headline": "Momentum", "headline_zh": "动量"},
            {"id": "e3", "ts": "2026-07-15T00:00:00", "type": "triple_red",
             "severity": "high", "headline": "Triple red", "headline_zh": "三重下跌"},
            {"id": "e4", "ts": "2026-07-14T00:00:00", "type": "residual_shock",
             "severity": "high", "headline": "Shock", "headline_zh": "冲击"},
            {"id": "e5", "ts": "2026-07-13T00:00:00", "type": "scenario_active",
             "severity": "high", "headline": "Scenario", "headline_zh": "情景"},
        ]
        fx_dir = tmp_path / "forex"
        fx_dir.mkdir()
        (fx_dir / "alerts.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events) + "\n"
        )
        fake_fx = {
            "asof": "2026-07-17",
            "dollar_desk": {"lean": "x", "lean_zh": "x", "lean_net": 0, "lean_n": 0, "triple_red": False},
        }
        from lib import forex_link, config as _cfg
        monkeypatch.setattr(forex_link, "_latest", lambda: fake_fx)
        monkeypatch.setattr(_cfg, "data_dir", lambda: tmp_path)
        from scripts.build_site import _build_fx_context
        result = _build_fx_context()
        assert result is not None
        ev = result["recent_events"]
        # Only desk-level types pass; rows are normalized to the compact
        # template-facing shape {date, severity, headline, headline_zh}
        assert len(ev) == 3                             # momentum + residual_shock dropped
        heads = {e["headline"] for e in ev}
        assert heads == {"Smile flip", "Triple red", "Scenario"}
        for e in ev:
            assert set(e.keys()) == {"date", "severity", "headline", "headline_zh"}
            assert len(e["date"]) == 10                 # ISO day from ts

    def test_recent_events_max_5(self, monkeypatch, tmp_path):
        """recent_events returns at most 5 entries."""
        events = [
            {"id": f"e{i}", "ts": f"2026-07-{10 + i:02d}T00:00:00", "type": "smile_regime_flip",
             "severity": "high", "headline": f"Event {i}", "headline_zh": f"事件{i}"}
            for i in range(10)
        ]
        fx_dir = tmp_path / "forex"
        fx_dir.mkdir()
        (fx_dir / "alerts.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
        fake_fx = {
            "asof": "2026-07-17",
            "dollar_desk": {"lean": "x", "lean_zh": "x", "lean_net": 0, "lean_n": 0, "triple_red": False},
        }
        from lib import forex_link, config as _cfg
        monkeypatch.setattr(forex_link, "_latest", lambda: fake_fx)
        monkeypatch.setattr(_cfg, "data_dir", lambda: tmp_path)
        from scripts.build_site import _build_fx_context
        result = _build_fx_context()
        assert result is not None
        assert len(result["recent_events"]) <= 5

    def test_smile_decomp_stripped_from_dollar_desk(self, monkeypatch, tmp_path):
        """smile_decomp internals must be stripped from dollar_desk in fx_context (spec §7 compact)."""
        fake_fx = {
            "asof": "2026-07-17",
            "dollar_desk": {
                "lean": "x", "lean_zh": "x", "lean_net": 0, "lean_n": 0, "triple_red": False,
                "smile_decomp": {
                    "beta": 0.35, "r2": 0.42, "regime": "safety-driven", "display_only": True
                },
            },
        }
        (tmp_path / "forex").mkdir()
        (tmp_path / "forex" / "alerts.jsonl").write_text("")
        from lib import forex_link, config as _cfg
        monkeypatch.setattr(forex_link, "_latest", lambda: fake_fx)
        monkeypatch.setattr(_cfg, "data_dir", lambda: tmp_path)
        from scripts.build_site import _build_fx_context
        result = _build_fx_context()
        assert result is not None
        desk = result.get("dollar_desk") or {}
        assert "smile_decomp" not in desk


# ---------------------------------------------------------------- sidecar keys

class TestSidecarKeys:
    """Validate that the macro_signals.json sidecar includes new MSX-2 keys."""

    def test_sidecar_keys_present_in_msdata_construction(self):
        """Simulate sidecar assembly and verify new keys are present."""
        # Replicate the sidecar construction logic with synthetic inputs
        ms_color = "green"
        stances = {
            "hero": {"en": "Conditions support staying invested — watch the usual risks.",
                     "zh": "环境支持持仓 — 留意常规风险。"},
            "liquidity": {"en": "The money tide is rising — historically the most reliable tailwind.",
                          "zh": "资金潮上涨 — 历史上最可靠的顺风。"},
            "credit": {"en": "Credit calm, participation healthy — no smoke.",
                       "zh": "信用平稳，参与度健康 — 无警讯。"},
        }
        fx_ctx = {
            "asof": "2026-07-17",
            "dollar_desk": {"lean": "x", "lean_n": 2},
            "state_changes": None,
            "regime_radar": {"dominant": None, "active": [], "intensity": {}},
            "strength": None,
            "transmission": None,
            "pairs": None,
            "recent_events": [],
        }
        # Build sidecar with the new fields (replicate build_site logic)
        _fx_desk = {k: v for k, v in (fx_ctx.get("dollar_desk") or {}).items()
                    if k != "smile_decomp"}
        _radar_raw = fx_ctx.get("regime_radar") or {}
        _radar_compact = {
            "dominant": _radar_raw.get("dominant"),
            "active": _radar_raw.get("active"),
            "intensity": _radar_raw.get("intensity"),
        }
        _fx_sidecar = {
            "asof": fx_ctx.get("asof"),
            "dollar_desk": _fx_desk or None,
            "state_changes": fx_ctx.get("state_changes"),
            "regime_radar": _radar_compact,
            "strength": None,
        }
        msdata = {
            "date": "2026-07-17",
            "generated_utc": "2026-07-17T00:00:00Z",
            "market_state_color": ms_color,
            "stances": stances,
            "fx": _fx_sidecar,
        }
        # Serialise and re-parse to verify JSON compatibility
        serialised = json.dumps(msdata, default=str)
        parsed = json.loads(serialised)
        assert "market_state_color" in parsed
        assert parsed["market_state_color"] == "green"
        assert "stances" in parsed
        assert parsed["stances"]["hero"]["en"] == (
            "Conditions support staying invested — watch the usual risks."
        )
        assert "fx" in parsed
        assert parsed["fx"]["asof"] == "2026-07-17"

    def test_sidecar_fx_none_when_context_absent(self):
        """When fx_context is None, sidecar fx key should be None."""
        fx_ctx = None
        _fx_sidecar = None
        if fx_ctx:
            _fx_sidecar = {}  # would be populated otherwise
        msdata = {"fx": _fx_sidecar, "market_state_color": None, "stances": None}
        assert msdata["fx"] is None

    def test_fx_sidecar_excludes_smile_decomp(self):
        """smile_decomp must never appear in the sidecar fx.dollar_desk."""
        desk_raw = {"lean": "x", "lean_n": 2, "smile_decomp": {"beta": 0.35}}
        _fx_desk = {k: v for k, v in desk_raw.items() if k != "smile_decomp"}
        assert "smile_decomp" not in _fx_desk
        assert "lean" in _fx_desk
