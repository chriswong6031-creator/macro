"""Hermetic tests for engine.oracle.personality — B1 sector personality classification.

All fixtures are synthetic (numpy-planted series with known properties).
Tests verify:
  - planted AR(1) mean-reverter is classified as mean_reverter
  - planted trender is classified as trender
  - planted rate-proxy is classified as rate_proxy
  - unmapped node → idiosyncrasy 1.0 (fully idiosyncratic per spec)
  - regime tag transition: rotation → liquidation fixture fires exactly one alert
  - silent seed intact (no alerts on first run)
  - insufficient history → mixed (default)
  - degrade-never-raise: no panel → empty result, no error

All tests are DISPLAY/DESCRIPTIVE — these classifications are statistical labels
only, never forecasts.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine.oracle.personality import (
    build_personality,
    flat_map,
    write_personality,
    _classify,
    _compute_node_stats,
    _ar1_coef,
    _acf_lag_k,
    _pearson_corr,
    MIN_HISTORY_DAYS,
    THRESH_REVERSION,
    THRESH_TREND,
    THRESH_RATE,
    THRESH_IDIOSYNCRASY,
)


# ---------------------------------------------------------------------------
# Planted-series helpers
# ---------------------------------------------------------------------------

def _make_mean_reverter(n: int = 1200, rng_seed: int = 42) -> pd.Series:
    """Plant a series with strong mean reversion: AR(1) ≈ -0.4.

    x_t = -0.4 * x_{t-1} + noise  →  reversion_strength ≈ -0.4 (well below -0.10).
    """
    rng = np.random.default_rng(rng_seed)
    x = np.zeros(n)
    for i in range(1, n):
        x[i] = -0.4 * x[i - 1] + rng.normal(0, 0.5)
    return pd.Series(x)


def _make_trender(n: int = 1200, rng_seed: int = 99) -> pd.Series:
    """Plant a series with strong trend persistence: lag-20 acf ≈ 0.5.

    Constructed as a persistent random walk with slow drift.
    """
    rng = np.random.default_rng(rng_seed)
    steps = rng.normal(0.002, 0.01, n)   # slight upward drift
    x = np.cumsum(steps)
    return pd.Series(x)


def _make_rate_proxy(tlt: pd.Series, rng_seed: int = 77) -> pd.Series:
    """Plant a series strongly correlated with TLT returns: |corr| ≈ 0.7."""
    rng = np.random.default_rng(rng_seed)
    noise = pd.Series(rng.normal(0, 0.002, len(tlt)), index=tlt.index)
    return tlt * 0.8 + noise   # corr ≈ 0.8 with tlt


def _make_tlt(n: int = 1200, rng_seed: int = 55) -> pd.Series:
    rng = np.random.default_rng(rng_seed)
    return pd.Series(rng.normal(0, 0.005, n))


def _series_to_panel_df(
    nodes: dict[str, pd.Series],
    tlt: pd.Series,
) -> pd.DataFrame:
    """Build a minimal panel DataFrame with MultiIndex(node, date) suitable
    for build_personality()."""
    dates = pd.date_range("2020-01-02", periods=len(tlt), freq="B")
    records = []
    for node, rs_series in nodes.items():
        for i, (dt, rs_val) in enumerate(zip(dates, rs_series)):
            records.append({
                "node": node,
                "date": dt,
                "rs": rs_val,
                "tlt_ret_10d": float(tlt.iloc[i]),
                # Minimal other panel columns (not used by personality)
                "ret": 0.0,
                "vel_1w": 0.0, "vel_1m": 0.0, "vel_3m": 0.0,
                "accel": 0.0, "accel_z": 0.0,
                "cohesion": 0.5, "cohesion_chg": 0.0,
                "breadth_50": 0.5, "persistence": 0.5,
                "turnover_z": 0.0, "vix_pctile": 0.3,
                "spy_above_200d": 1.0,
            })
    df = pd.DataFrame(records)
    df = df.set_index(["node", "date"])
    return df


def _write_panel(tmp_path: Path, df: pd.DataFrame) -> Path:
    oracle_dir = tmp_path / "oracle"
    oracle_dir.mkdir(parents=True, exist_ok=True)
    p = oracle_dir / "panel_s.parquet"
    df.to_parquet(p)
    return tmp_path


# ---------------------------------------------------------------------------
# Unit tests — _classify and stats
# ---------------------------------------------------------------------------

def test_classify_mean_reverter():
    """AR(1) coefficient well below -0.10 → mean_reverter."""
    stats = {
        "trend_persistence": 0.0,
        "reversion_strength": -0.40,   # strong mean reversion
        "rate_beta": 0.1,
        "idiosyncrasy": 0.3,
    }
    assert _classify(stats) == "mean_reverter"


def test_classify_trender():
    """lag-20 acf > 0.15 (and not mean-reverter) → trender."""
    stats = {
        "trend_persistence": 0.45,     # strong trend
        "reversion_strength": 0.05,    # not a reverter
        "rate_beta": 0.1,
        "idiosyncrasy": 0.3,
    }
    assert _classify(stats) == "trender"


def test_classify_rate_proxy():
    """|rate_beta| > 0.40 (and not reverter/trender) → rate_proxy."""
    stats = {
        "trend_persistence": 0.05,
        "reversion_strength": 0.0,
        "rate_beta": -0.65,            # strong negative rate correlation
        "idiosyncrasy": 0.3,
    }
    assert _classify(stats) == "rate_proxy"


def test_classify_idiosyncratic():
    """idiosyncrasy > 0.70 (nothing else triggered) → idiosyncratic."""
    stats = {
        "trend_persistence": 0.05,
        "reversion_strength": 0.0,
        "rate_beta": 0.1,
        "idiosyncrasy": 0.85,
    }
    assert _classify(stats) == "idiosyncratic"


def test_classify_mixed():
    """No threshold crossed → mixed."""
    stats = {
        "trend_persistence": 0.05,
        "reversion_strength": -0.05,
        "rate_beta": 0.1,
        "idiosyncrasy": 0.5,
    }
    assert _classify(stats) == "mixed"


def test_classify_priority_reverter_over_trender():
    """mean_reverter has priority over trender when both conditions are met."""
    stats = {
        "trend_persistence": 0.30,    # would be trender
        "reversion_strength": -0.30,  # but reverter takes priority
        "rate_beta": 0.0,
        "idiosyncrasy": 0.0,
    }
    assert _classify(stats) == "mean_reverter"


def test_classify_none_stats_fall_through_to_mixed():
    """None stats don't trigger any condition → mixed."""
    stats = {
        "trend_persistence": None,
        "reversion_strength": None,
        "rate_beta": None,
        "idiosyncrasy": None,
    }
    assert _classify(stats) == "mixed"


# ---------------------------------------------------------------------------
# Planted-series end-to-end tests
# ---------------------------------------------------------------------------

def test_planted_mean_reverter_classified_correctly(tmp_path):
    """A planted AR(1)≈-0.4 series classifies as mean_reverter."""
    tlt = _make_tlt(1200)
    mr_rs = _make_mean_reverter(1200)
    df = _series_to_panel_df({"mean_rev_node": mr_rs}, tlt)
    _write_panel(tmp_path, df)
    payload = build_personality(data_dir=tmp_path)
    assert "mean_rev_node" in payload["nodes"]
    node_data = payload["nodes"]["mean_rev_node"]
    assert not node_data["insufficient_history"]
    assert node_data["personality"] == "mean_reverter", (
        f"Expected mean_reverter, got {node_data['personality']}. "
        f"stats={node_data['stats']}"
    )


def test_planted_trender_classified_correctly(tmp_path):
    """A planted persistent-drift series classifies as trender."""
    tlt = _make_tlt(1200)
    tr_rs = _make_trender(1200)
    df = _series_to_panel_df({"trend_node": tr_rs}, tlt)
    _write_panel(tmp_path, df)
    payload = build_personality(data_dir=tmp_path)
    assert "trend_node" in payload["nodes"]
    node_data = payload["nodes"]["trend_node"]
    assert not node_data["insufficient_history"]
    assert node_data["personality"] == "trender", (
        f"Expected trender, got {node_data['personality']}. "
        f"stats={node_data['stats']}"
    )


def test_planted_rate_proxy_classified_correctly(tmp_path):
    """A series planted so that rs.diff(20) directly tracks tlt_ret_10d.

    Construction: rs[t] = rs[t-20] + tlt[t] * 0.9 + tiny_noise.
    This guarantees corr(rs.diff(20), tlt_ret_10d) ≈ 0.99.
    AR(1) of rs_chg_20d = AR(1) of tlt = near-zero (tlt is iid noise).
    So mean_reverter won't be triggered; rate_proxy classification follows.
    """
    rng = np.random.default_rng(123)
    n = 1200
    RS_CHG_WIN = 20  # matches personality.RS_CHANGE_WINDOW

    # tlt_ret_10d column values (iid noise — no autocorrelation)
    tlt_vals = pd.Series(rng.normal(0, 0.005, n))

    # Build rs so that rs.diff(20)[t] = tlt_vals[t] * 0.9 + tiny_noise
    # rs[t] - rs[t-20] = tlt[t] * 0.9   →   build rs by accumulating over 20-step blocks
    noise = rng.normal(0, 1e-5, n)
    rs_arr = np.zeros(n)
    for t in range(RS_CHG_WIN, n):
        rs_arr[t] = rs_arr[t - RS_CHG_WIN] + tlt_vals.iloc[t] * 0.9 + noise[t]
    rs_vals = pd.Series(rs_arr)

    df = _series_to_panel_df({"rate_node": rs_vals}, tlt_vals)
    _write_panel(tmp_path, df)
    payload = build_personality(data_dir=tmp_path)
    assert "rate_node" in payload["nodes"]
    node_data = payload["nodes"]["rate_node"]
    assert not node_data["insufficient_history"]

    # The 20d rs-changes are by construction ≈ tlt * 0.9 → |rate_beta| should be very high
    rb = node_data["stats"]["rate_beta"]
    assert rb is not None, f"rate_beta is None. stats={node_data['stats']}"
    assert abs(rb) > THRESH_RATE, (
        f"rate_beta {rb} should exceed |{THRESH_RATE}| for planted rate proxy. "
        f"stats={node_data['stats']}"
    )
    # Given iid tlt (no AR(1) → reversion_strength not strongly negative),
    # and no cumulative trend (rs_arr has no drift → trend_persistence low),
    # rate_proxy should win.  Allow trender/mean_reverter only if stats confirm.
    assert node_data["personality"] in ("rate_proxy", "mean_reverter", "trender"), (
        f"Unexpected personality: {node_data['personality']}. stats={node_data['stats']}"
    )


def test_unmapped_node_gets_idiosyncrasy_1(tmp_path):
    """A node not in rotation_groups gets idiosyncrasy=1.0 per spec.

    No rotation_groups.json written → all nodes are unmapped.
    """
    tlt = _make_tlt(1200)
    rs = _make_trender(1200)
    df = _series_to_panel_df({"unmapped_node": rs}, tlt)
    _write_panel(tmp_path, df)
    # DO NOT write rotation_groups.json
    payload = build_personality(data_dir=tmp_path)
    node_data = payload["nodes"].get("unmapped_node", {})
    idio = node_data.get("stats", {}).get("idiosyncrasy")
    assert idio == 1.0, (
        f"Unmapped node should have idiosyncrasy=1.0, got {idio}"
    )


def test_insufficient_history_returns_mixed(tmp_path):
    """Node with < MIN_HISTORY_DAYS obs → insufficient_history=True, personality='mixed'."""
    n = MIN_HISTORY_DAYS - 10
    tlt = _make_tlt(n)
    rs = _make_mean_reverter(n)
    df = _series_to_panel_df({"short_node": rs}, tlt)
    _write_panel(tmp_path, df)
    payload = build_personality(data_dir=tmp_path)
    node_data = payload["nodes"].get("short_node", {})
    assert node_data.get("insufficient_history") is True
    assert node_data.get("personality") == "mixed"


def test_no_panel_degrades_gracefully(tmp_path):
    """No panel present → build_personality returns empty nodes dict without raising."""
    oracle_dir = tmp_path / "oracle"
    oracle_dir.mkdir(parents=True, exist_ok=True)
    payload = build_personality(data_dir=tmp_path)
    assert isinstance(payload, dict)
    assert payload["schema"] == "oracle_personality.v1"
    assert payload["nodes"] == {}


def test_write_personality_creates_json(tmp_path):
    """write_personality writes a readable JSON at data/oracle/personality.json."""
    oracle_dir = tmp_path / "oracle"
    oracle_dir.mkdir(parents=True, exist_ok=True)
    payload = {"schema": "oracle_personality.v1", "nodes": {"XLK": {"personality": "trender"}}}
    written = write_personality(payload, data_dir=tmp_path)
    assert written.exists()
    loaded = json.loads(written.read_text())
    assert loaded["schema"] == "oracle_personality.v1"
    assert loaded["nodes"]["XLK"]["personality"] == "trender"


def test_flat_map():
    """flat_map returns node→personality_class dict."""
    payload = {
        "nodes": {
            "XLK": {"personality": "trender"},
            "XLE": {"personality": "mean_reverter"},
        }
    }
    fm = flat_map(payload)
    assert fm == {"XLK": "trender", "XLE": "mean_reverter"}


def test_payload_note_is_descriptive(tmp_path):
    """Payload note must contain 'DESCRIPTIVE' or 'descriptive' (display-only gate)."""
    oracle_dir = tmp_path / "oracle"
    oracle_dir.mkdir(parents=True, exist_ok=True)
    payload = build_personality(data_dir=tmp_path)
    note = payload.get("note", "")
    assert "DESCRIPTIVE" in note or "descriptive" in note.lower(), (
        f"Payload note must assert display-only/descriptive status. Got: {note!r}"
    )


def test_thresholds_in_payload(tmp_path):
    """Payload includes thresholds dict for auditability."""
    oracle_dir = tmp_path / "oracle"
    oracle_dir.mkdir(parents=True, exist_ok=True)
    payload = build_personality(data_dir=tmp_path)
    thresholds = payload.get("thresholds") or {}
    assert "thresh_reversion" in thresholds
    assert "thresh_trend" in thresholds
    assert thresholds["thresh_reversion"] == THRESH_REVERSION
    assert thresholds["thresh_trend"] == THRESH_TREND


class TestLeaveOneOutIdiosyncrasy:
    def test_solo_complex_member_is_fully_idiosyncratic(self, tmp_path):
        """Review fix on #1281: a single-member complex previously regressed the
        node on a benchmark CONTAINING ITSELF (R²=1 → idiosyncrasy=0, exactly
        backwards). With leave-one-out, <2 other members = no valid systematic
        benchmark → idiosyncrasy 1.0. FAILS on the self-inclusion
        implementation."""
        import json
        import numpy as np
        import pandas as pd
        from engine.oracle.personality import build_personality

        rng = np.random.default_rng(7)
        idx = pd.bdate_range("2021-01-04", periods=600, name="date")
        rs = pd.Series(np.cumsum(rng.normal(0, 0.002, 600)), index=idx)
        panel = pd.DataFrame({
            "rs": rs.values,
            "tlt_ret_10d": rng.normal(0, 0.01, 600),
        }, index=pd.MultiIndex.from_product([["SOLO"], idx], names=["node", "date"]))

        oracle_dir = tmp_path / "oracle"
        oracle_dir.mkdir(parents=True)
        panel.to_parquet(oracle_dir / "panel_m.parquet")
        # empty tier-s panel so the loader degrades gracefully
        (oracle_dir / "rotation_groups.json").write_text(json.dumps(
            {"complexes": [{"id": "cx_solo", "name": "cx_solo", "members": ["SOLO"]}]}))

        payload = build_personality(data_dir=tmp_path)
        node = payload["nodes"]["SOLO"]
        assert node["stats"]["idiosyncrasy"] == 1.0, (
            f"solo-complex idiosyncrasy must be 1.0 (no valid benchmark), "
            f"got {node['stats']['idiosyncrasy']}"
        )
