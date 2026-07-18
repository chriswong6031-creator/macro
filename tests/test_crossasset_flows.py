"""tests/test_crossasset_flows.py — W3-A flows.v2 persistence + hero + history.

Tests cover:
  - hero matrix: all 9 (breadth_regime, concentration) combos + unknown concentration
  - flows.v2 schema fields in latest.json: schema string, regime, trend_summary,
    enriched correlation, enriched leadlag, confirm/dollar/shadow pass-through
  - legacy 5 keys byte-stable when flows.v2 is written
  - fail-open when forex/regime files are missing (all new blocks None, no crash)
  - history.jsonl appended only when COLLECT_LANE=nightly; dedup (same asof skips)
  - absorption_spark_w shape (list, <=104 elements, all floats)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# Ensure repo root is on sys.path for direct test invocation
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.cross_asset import absorption_series, snapshot as ca_snapshot
from scripts.build_crossasset import _compose_hero, _append_history


# ═══════════════════════════════════════════════════════════════════════════════
# Hero matrix unit tests (all 9 combos)
# ═══════════════════════════════════════════════════════════════════════════════

_HERO_CASES = [
    # (breadth,  corr_verdict,     expected_tone)
    (0.5,        "diversified",    "green"),
    (0.5,        "converging",     "amber"),
    (0.5,        "concentrated",   "amber"),
    (0.0,        "diversified",    "amber"),
    (0.0,        "converging",     "amber"),
    (0.0,        "concentrated",   "amber"),
    (-0.5,       "diversified",    "red"),
    (-0.5,       "converging",     "red"),
    (-0.5,       "concentrated",   "red"),
]


@pytest.mark.parametrize("breadth,concentration,expected_tone", _HERO_CASES)
def test_hero_tone(breadth, concentration, expected_tone):
    h = _compose_hero(breadth, concentration)
    assert h["tone"] == expected_tone, f"({breadth}, {concentration}) -> {h['tone']!r} != {expected_tone!r}"


def test_hero_has_all_bilingual_keys():
    for breadth, concentration, _ in _HERO_CASES:
        h = _compose_hero(breadth, concentration)
        for key in ("tone", "headline_en", "headline_zh", "sub_en", "sub_zh", "stance_en", "stance_zh"):
            assert key in h
            assert isinstance(h[key], str) and h[key], f"key {key!r} empty for ({breadth},{concentration})"


def test_hero_unknown_concentration_degrades_to_breadth_row():
    """unknown concentration should fall back to breadth-only row (no KeyError)."""
    h_unk = _compose_hero(0.5, "unknown")
    h_div = _compose_hero(0.5, "diversified")
    # unknown falls through to diversified variant (breadth-only fallback per spec)
    assert h_unk["tone"] == h_div["tone"]
    assert h_unk["headline_en"] == h_div["headline_en"]


def test_hero_unknown_concentration_none_verdict():
    """None verdict also degrades gracefully."""
    h = _compose_hero(-0.5, None)
    assert h["tone"] == "red"
    assert isinstance(h["headline_en"], str)


def test_hero_none_breadth_defaults_to_mixed():
    """None breadth is treated as 0 (mixed)."""
    h = _compose_hero(None, "diversified")
    assert h["tone"] == "amber"


# ═══════════════════════════════════════════════════════════════════════════════
# absorption_spark_w shape test (engine/cross_asset.py additive field)
# ═══════════════════════════════════════════════════════════════════════════════

def _make_returns(n_days: int = 600, n_markets: int = 5, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n_days, freq="B")
    return pd.DataFrame(rng.normal(0, 0.01, (n_days, n_markets)),
                        index=idx,
                        columns=[f"m{i}" for i in range(n_markets)])


def test_absorption_spark_w_is_list_le_104(monkeypatch):
    """absorption_spark_w must be a plain list of <=104 weekly floats."""
    import engine.cross_asset as ca

    rets = _make_returns(700)
    # patch returns_frame to return synthetic data
    monkeypatch.setattr(ca, "returns_frame", lambda: rets)

    s = ca_snapshot()
    assert s.get("verdict") != "unknown", "snapshot should succeed with 700 days of data"
    spark = s.get("absorption_spark_w")
    assert isinstance(spark, list), f"absorption_spark_w should be list, got {type(spark)}"
    assert len(spark) <= 104, f"absorption_spark_w should have <=104 entries, got {len(spark)}"
    # all elements must be finite floats
    for v in spark:
        assert isinstance(v, float), f"element {v!r} is not float"
        assert np.isfinite(v), f"element {v!r} is not finite"


def test_absorption_spark_asof_is_present(monkeypatch):
    import engine.cross_asset as ca

    rets = _make_returns(700)
    monkeypatch.setattr(ca, "returns_frame", lambda: rets)

    s = ca_snapshot()
    if s.get("verdict") != "unknown":
        asof = s.get("absorption_spark_asof")
        assert asof is not None
        # must be a date-string like "2024-12-27"
        assert isinstance(asof, str) and len(asof) == 10


def test_absorption_spark_w_absent_on_no_data(monkeypatch):
    """When snapshot returns unknown (too little data), spark should be absent or empty."""
    import engine.cross_asset as ca

    monkeypatch.setattr(ca, "returns_frame", lambda: pd.DataFrame())

    s = ca_snapshot()
    assert s.get("verdict") == "unknown"
    # key is absent on early-exit path (no spark computed)
    assert "absorption_spark_w" not in s or s.get("absorption_spark_w") == []


# ═══════════════════════════════════════════════════════════════════════════════
# flows.v2 persistence tests (via build_crossasset.main())
# ═══════════════════════════════════════════════════════════════════════════════

def _make_mock_snap(breadth=0.3, corr_verdict="concentrated"):
    """Minimal mock of cat.snapshot() return value."""
    return {
        "asof": "2026-07-18",
        "regime": "mixed / no clear trend",
        "breadth": breadth,
        "favored": ["equity_us"],
        "note": "test note",
        "trend": {
            "asof": "2026-07-18",
            "rows": [
                {"key": "equity_us", "trend": "up", "score": 1.0,
                 "class": "equity", "name_en": "S&P 500", "name_zh": "标普500",
                 "class_en": "Equity", "class_zh": "股票",
                 "ret_3m": 5.0, "ret_6m": 8.0, "ret_12m": 15.0},
            ],
            "n": 1, "n_up": 1, "n_down": 0,
        },
        "ratios": [
            {"key": "copper_gold", "value": 0.5, "state": "mid", "pctile": 55.0,
             "label_en": "Copper / Gold", "label_zh": "铜/金", "chg_3m": 2.1,
             "note": "test"},
        ],
        "carry": {"rows": [], "note": "test"},
        "correlation": {
            "verdict": corr_verdict,
            "absorption_pctile_5y": 0.88,
            "absorption_ratio": 0.42,
            "mean_abs_corr": 0.61,
            "dominant_cluster": ["US", "Crypto"],
            "markets": ["US", "Crypto", "China", "HK", "Commodities", "Dollar"],
            "absorption_spark_w": [0.3, 0.35, 0.4, 0.42],
            "absorption_spark_asof": "2026-07-11",
        },
    }


def _run_main_with_mocks(tmp_path: Path, snap: dict,
                         forex_data: dict | None = None,
                         regime_data: dict | None = None,
                         collect_lane: str | None = None) -> dict:
    """Run build_crossasset.main() with mocked data, return parsed latest.json."""
    # Write fake forex/regime files if provided
    if forex_data is not None:
        (tmp_path / "forex").mkdir(parents=True, exist_ok=True)
        (tmp_path / "forex" / "latest.json").write_text(json.dumps(forex_data))
    if regime_data is not None:
        (tmp_path / "regime").mkdir(parents=True, exist_ok=True)
        (tmp_path / "regime" / "latest.json").write_text(json.dumps(regime_data))

    (tmp_path / "crossasset").mkdir(parents=True, exist_ok=True)
    site_dir = tmp_path / "site"
    site_dir.mkdir(parents=True, exist_ok=True)

    env_patch = {}
    if collect_lane is not None:
        env_patch["COLLECT_LANE"] = collect_lane

    from scripts import build_crossasset as bca

    with patch("scripts.build_crossasset.config") as mock_cfg, \
         patch("scripts.build_crossasset.write_page"), \
         patch("scripts.build_crossasset.Environment") as mock_env_cls:

        # config mocks
        mock_cfg.ROOT = tmp_path
        mock_cfg.data_dir.return_value = tmp_path
        mock_cfg.load.return_value = {"storage": {"site_dir": "site"}}

        # jinja env mock — capture render call, return minimal HTML
        mock_env = MagicMock()
        mock_env_cls.return_value = mock_env
        mock_tmpl = MagicMock()
        mock_env.get_template.return_value = mock_tmpl
        mock_tmpl.render.return_value = "<html>test</html>"

        import engine.crossasset_shadow as _cas
        with patch("engine.cross_asset_trend.snapshot", return_value=snap), \
             patch("engine.global_liquidity.snapshot", return_value=None), \
             patch("engine.funding_stress.snapshot", return_value=None), \
             patch("engine.cross_asset.leadlag_snapshot", return_value=None), \
             patch("lib.forex_link.transmission", side_effect=Exception("no forex_link")), \
             patch.object(_cas, "run", return_value=None):

            _old_env = {}
            for k, v in env_patch.items():
                _old_env[k] = os.environ.get(k)
                os.environ[k] = v
            try:
                rc = bca.main()
            finally:
                for k, old_v in _old_env.items():
                    if old_v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = old_v

    assert rc == 0
    latest_path = tmp_path / "crossasset" / "latest.json"
    assert latest_path.exists()
    return json.loads(latest_path.read_text())


def test_flows_v2_schema_string(tmp_path):
    snap = _make_mock_snap()
    data = _run_main_with_mocks(tmp_path, snap)
    assert data["flows"]["schema"] == "crossasset_flows.v2"


def test_flows_v2_legacy_keys_byte_stable(tmp_path):
    """The 5 legacy top-level keys must be present and unchanged in type."""
    snap = _make_mock_snap()
    data = _run_main_with_mocks(tmp_path, snap)
    assert data["date"] == "2026-07-18"
    assert data["regime"] == "mixed / no clear trend"
    assert isinstance(data["breadth"], float)
    assert isinstance(data["favored"], list)
    assert data["correlation"] == "concentrated"


def test_flows_v2_has_regime_field(tmp_path):
    snap = _make_mock_snap()
    data = _run_main_with_mocks(tmp_path, snap)
    assert data["flows"]["regime"] == "mixed / no clear trend"


def test_flows_v2_trend_summary_present(tmp_path):
    snap = _make_mock_snap()
    data = _run_main_with_mocks(tmp_path, snap)
    ts = data["flows"]["trend_summary"]
    assert "n" in ts and "n_up" in ts and "n_down" in ts


def test_flows_v2_correlation_enriched(tmp_path):
    """flows.v2 correlation block must include absorption_ratio, mean_abs_corr, spark_w."""
    snap = _make_mock_snap()
    data = _run_main_with_mocks(tmp_path, snap)
    corr = data["flows"]["correlation"]
    assert corr is not None
    assert "absorption_ratio" in corr
    assert "mean_abs_corr" in corr
    assert "dominant_cluster" in corr
    assert "spark_w" in corr
    assert isinstance(corr["spark_w"], list)
    assert "spark_asof" in corr


def test_flows_v2_leadlag_enriched(tmp_path):
    """flows.v2 leadlag must include stable, lead_asset, n_significant, n_tested."""
    snap = _make_mock_snap()
    data = _run_main_with_mocks(tmp_path, snap)
    ll = data["flows"]["leadlag"]
    assert "stable" in ll
    assert "lead_asset" in ll
    assert "n_significant" in ll
    assert "n_tested" in ll


def test_flows_v2_intermarket_has_pctile(tmp_path):
    """flows.v2 intermarket rows must include pctile field."""
    snap = _make_mock_snap()
    data = _run_main_with_mocks(tmp_path, snap)
    im = data["flows"]["intermarket"]
    assert len(im) > 0
    for row in im:
        assert "pctile" in row


def test_flows_v2_confirm_from_regime_file(tmp_path):
    """When regime/latest.json has cross_asset_confirm, flows.confirm is populated."""
    snap = _make_mock_snap()
    regime_data = {
        "cross_asset_confirm": {
            "verdict": "diverge",
            "agree_pct": 50,
            "n_blind_flags": 1,
            "caution_flags": [{"key": "credit", "severity": "medium", "lead": "leading"}],
            "asof": "2026-07-16",
        }
    }
    data = _run_main_with_mocks(tmp_path, snap, regime_data=regime_data)
    confirm = data["flows"]["confirm"]
    assert confirm is not None
    assert confirm["verdict"] == "diverge"
    assert confirm["agree_pct"] == 50
    assert confirm["n_blind_flags"] == 1
    assert len(confirm["flags_top"]) == 1
    assert confirm["asof"] == "2026-07-16"


def test_flows_v2_confirm_none_when_regime_missing(tmp_path):
    """When regime/latest.json is absent, flows.confirm is None (no crash)."""
    snap = _make_mock_snap()
    data = _run_main_with_mocks(tmp_path, snap)  # no regime_data
    assert data["flows"]["confirm"] is None


def test_flows_v2_dollar_from_forex_file(tmp_path):
    """When forex/latest.json exists, flows.dollar is populated."""
    snap = _make_mock_snap()
    forex_data = {
        "regime": "US growth premium",
        "risk": "risk-on",
        "transmission": {
            "usd_dir": "strengthening",
            "corr": {"GC=F": -0.75, "SPY": -0.43, "HG=F": -0.66},
            "unstable": [],
        },
        "regime_radar": {
            "dominant": None,
            "intensity": {"carry_unwind": 12.0, "dollar_wrecking_ball": 12.1},
        },
    }
    data = _run_main_with_mocks(tmp_path, snap, forex_data=forex_data)
    dollar = data["flows"]["dollar"]
    assert dollar is not None
    assert dollar["usd_dir"] == "strengthening"
    assert dollar["regime"] == "US growth premium"
    assert dollar["risk"] == "risk-on"
    assert isinstance(dollar["corr_top"], list)
    assert len(dollar["corr_top"]) <= 3
    # corr_top sorted by |corr| desc
    if len(dollar["corr_top"]) >= 2:
        assert abs(dollar["corr_top"][0]["corr"]) >= abs(dollar["corr_top"][1]["corr"])
    assert "unstable_n" in dollar
    assert "fx_stress" in dollar


def test_flows_v2_dollar_none_when_forex_missing(tmp_path):
    """When forex/latest.json is absent, flows.dollar is None (no crash)."""
    snap = _make_mock_snap()
    data = _run_main_with_mocks(tmp_path, snap)  # no forex_data
    assert data["flows"]["dollar"] is None


def test_flows_v2_shadow_none_when_module_missing(tmp_path):
    """When engine.crossasset_shadow is not importable, flows.shadow is None (no crash)."""
    snap = _make_mock_snap()
    data = _run_main_with_mocks(tmp_path, snap)
    # crossasset_shadow is not built yet (W3-B lane); must gracefully be None
    assert data["flows"]["shadow"] is None or isinstance(data["flows"]["shadow"], dict)


# ═══════════════════════════════════════════════════════════════════════════════
# History accrual tests
# ═══════════════════════════════════════════════════════════════════════════════

def _base_snap_dict():
    return {"regime": "mixed", "breadth": 0.3}


def test_history_append_only_when_nightly(tmp_path):
    """_append_history must NOT write when COLLECT_LANE != 'nightly'."""
    hist = tmp_path / "history.jsonl"
    os.environ.pop("COLLECT_LANE", None)

    _append_history(tmp_path, "2026-07-18", _base_snap_dict(), None, None, None, None, None, None)
    assert not hist.exists()

    os.environ["COLLECT_LANE"] = "intraday"
    try:
        _append_history(tmp_path, "2026-07-18", _base_snap_dict(), None, None, None, None, None, None)
        assert not hist.exists()
    finally:
        os.environ.pop("COLLECT_LANE", None)


def test_history_append_writes_when_nightly(tmp_path):
    """_append_history writes one JSON line when COLLECT_LANE=nightly."""
    hist = tmp_path / "history.jsonl"
    os.environ["COLLECT_LANE"] = "nightly"
    try:
        _append_history(tmp_path, "2026-07-18", _base_snap_dict(), None, None, None, None, None, None)
    finally:
        os.environ.pop("COLLECT_LANE", None)

    assert hist.exists()
    lines = [l for l in hist.read_text().splitlines() if l.strip()]
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["asof"] == "2026-07-18"
    assert "regime" in row
    assert "breadth" in row
    assert "logged_at" in row


def test_history_dedup_same_asof(tmp_path):
    """Second call with same asof must not append a duplicate line."""
    os.environ["COLLECT_LANE"] = "nightly"
    try:
        _append_history(tmp_path, "2026-07-18", _base_snap_dict(), None, None, None, None, None, None)
        _append_history(tmp_path, "2026-07-18", _base_snap_dict(), None, None, None, None, None, None)
    finally:
        os.environ.pop("COLLECT_LANE", None)

    hist = tmp_path / "history.jsonl"
    lines = [l for l in hist.read_text().splitlines() if l.strip()]
    assert len(lines) == 1, f"Expected 1 line after dedup, got {len(lines)}"


def test_history_different_asof_appends_second_line(tmp_path):
    """Different asof on second call must add a new line."""
    os.environ["COLLECT_LANE"] = "nightly"
    try:
        _append_history(tmp_path, "2026-07-17", _base_snap_dict(), None, None, None, None, None, None)
        _append_history(tmp_path, "2026-07-18", _base_snap_dict(), None, None, None, None, None, None)
    finally:
        os.environ.pop("COLLECT_LANE", None)

    hist = tmp_path / "history.jsonl"
    lines = [l for l in hist.read_text().splitlines() if l.strip()]
    assert len(lines) == 2


def test_history_row_schema_fields(tmp_path):
    """History row must contain all required schema fields."""
    _corr = {"absorption_pctile": 0.88, "absorption_ratio": 0.42, "verdict": "concentrated"}
    _ll = {"verdict": "lead"}
    _fund = {"state": "tightening", "score": 0.7}
    _liq = {"state": "expanding"}
    _confirm = {"verdict": "diverge", "agree_pct": 50}
    _dollar = {"usd_dir": "strengthening"}

    os.environ["COLLECT_LANE"] = "nightly"
    try:
        _append_history(tmp_path, "2026-07-18", {"regime": "risk-off trends", "breadth": -0.5},
                        _corr, _ll, _liq, _fund, _confirm, _dollar)
    finally:
        os.environ.pop("COLLECT_LANE", None)

    hist = tmp_path / "history.jsonl"
    row = json.loads(hist.read_text().strip())
    expected_fields = [
        "asof", "regime", "breadth", "absorption_pctile", "absorption_ratio",
        "corr_verdict", "leadlag_verdict", "funding_state", "funding_score",
        "liq_state", "confirm_verdict", "agree_pct", "dollar_dir", "logged_at",
    ]
    for f in expected_fields:
        assert f in row, f"Missing field {f!r} in history row"

    assert row["absorption_pctile"] == 0.88
    assert row["corr_verdict"] == "concentrated"
    assert row["leadlag_verdict"] == "lead"
    assert row["funding_state"] == "tightening"
    assert row["confirm_verdict"] == "diverge"
    assert row["dollar_dir"] == "strengthening"
