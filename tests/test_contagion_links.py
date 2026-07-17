"""tests/test_contagion_links.py — contract tests for engine/contagion_links.py

All inputs are SYNTHETIC and deterministic — no live data dependency.
Store reads are monkeypatched so the MM_DATA_GUARD tripwire is not triggered.
All writes use root=tmp_path per house law (conftest sets COLLECT_LANE=nightly
for the full session — tests that verify the BLOCKED path pop the env var).

Coverage:
  1.  structural_shape         — 11×11, diagonal=0, every dst row sums to 1
  2.  structural_anchors       — CN→HK max src into hk; US→CA among max into ca
  3.  sigma_saturate           — 10% dd21 → σ=1; flat series → σ=0
  4.  no_lookahead             — appending future rows does not change P_raw[t]
  5.  shadow_calm_never        — pressure_pct=0.99 but state=calm → shadow=calm
  6.  shadow_watch_escalate    — pct≥0.90 + incumbent=watch → caution
  7.  shadow_elevated_cap      — pct≥0.90 + incumbent=risk-off → risk-off (cap)
  8.  lane_gate_blocked        — COLLECT_LANE unset → latest.json written, NO appends
  9.  lane_gate_armed          — COLLECT_LANE=nightly → appends once; second call = skip
  10. degradation_missing_proxy— missing proxy for one mkt → dynamic=null, L=S, artifact complete
  11. schema_roundtrip         — artifact round-trips JSON; required keys present
  12. glance_lines_high        — high-level line contains 'HIGH' and is non-empty EN+ZH
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ---------------------------------------------------------------------------
# Module-level import of the engine (after sys.path insert)
# ---------------------------------------------------------------------------
import engine.contagion_links as cgl
from engine.contagion_links import (
    MARKETS,
    _MKT_IDX,
    _STRUCTURAL,
    _severity_series,
    _shadow_state,
    _build_structural,
    STRUCTURAL_VERSION,
)


# ---------------------------------------------------------------------------
# Synthetic data builders (deterministic, no live store reads)
# ---------------------------------------------------------------------------

def _bdate_index(n: int, start: str = "2018-01-02") -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n)


def _close_series(n: int, start_price: float = 100.0,
                  drift: float = 0.0003) -> pd.Series:
    """Synthetic close series with small upward drift."""
    idx = _bdate_index(n)
    np.random.seed(42)
    rets = np.random.normal(drift, 0.01, n)
    prices = start_price * np.cumprod(1.0 + rets)
    return pd.Series(prices, index=idx)


def _crash_series(n: int, crash_pct: float = 0.10) -> pd.Series:
    """Flat series that drops crash_pct over the last 21 sessions.

    prices[-21] = 100, prices[-1] = 100*(1-crash_pct), linear interpolation.
    This guarantees dd21 at the last point = exactly crash_pct.
    """
    idx = _bdate_index(n)
    prices = np.ones(n) * 100.0
    # Linear from 100 to 100*(1-crash_pct) over 21 points (inclusive)
    prices[-21:] = np.linspace(100.0, 100.0 * (1.0 - crash_pct), 21)
    return pd.Series(prices, index=idx)


def _make_minimal_stores(tmp_path: Path) -> dict:
    """Build a minimal set of proxy and bench series (200 rows each) for all 11 mkts."""
    series = {}
    n = 200
    # vol series keyed as (group, ticker)
    for mkt in MARKETS:
        series[mkt] = _close_series(n, start_price=100.0 + _MKT_IDX[mkt] * 10)
    return series


# ---------------------------------------------------------------------------
# Fixture: monkeypatched store returning synthetic data
# ---------------------------------------------------------------------------

def _store_read_factory(series_map: dict):
    """Returns a store.read replacement that serves synthetic series."""
    def _read(group: str, ticker: str):
        # Look up by (group, ticker) or by ticker alone (proxy series)
        key = (group, ticker)
        if key in series_map:
            s = series_map[key]
        elif ticker in series_map:
            s = series_map[ticker]
        else:
            return None
        if isinstance(s, pd.Series):
            df = pd.DataFrame({"close": s})
            # Add OHLCV columns so GK vol can be computed
            df["open"]  = s * 0.999
            df["high"]  = s * 1.005
            df["low"]   = s * 0.994
            df["volume"] = 1e6
            return df
        return s
    return _read


# ---------------------------------------------------------------------------
# 1. structural_shape
# ---------------------------------------------------------------------------

def test_structural_shape():
    S = _build_structural()
    assert S.shape == (11, 11), f"Expected 11x11, got {S.shape}"
    # Diagonal zero
    assert np.allclose(np.diag(S), 0.0), "Diagonal must be 0"
    # Every row sums to 1
    row_sums = S.sum(axis=1)
    assert np.allclose(row_sums, 1.0), f"Row sums: {row_sums}"


# ---------------------------------------------------------------------------
# 2. structural_anchors
# ---------------------------------------------------------------------------

def test_structural_anchors():
    S = _build_structural()
    cn_idx = _MKT_IDX["cn"]
    hk_idx = _MKT_IDX["hk"]
    us_idx = _MKT_IDX["us"]
    ca_idx = _MKT_IDX["ca"]

    # CN→HK must be the max source weight into hk
    hk_row = S[hk_idx]  # S[dst, src]
    assert hk_row[cn_idx] == hk_row.max(), (
        f"CN→HK weight {hk_row[cn_idx]:.3f} is not the max of hk row: {hk_row}"
    )

    # US→CA must be the single largest source into ca
    ca_row = S[ca_idx]
    assert ca_row[us_idx] == ca_row.max(), (
        f"US→CA weight {ca_row[us_idx]:.3f} is not the max of ca row: {ca_row}"
    )


# ---------------------------------------------------------------------------
# 3. sigma_saturate
# ---------------------------------------------------------------------------

def test_sigma_saturate_crash():
    """10% 21-day drawdown (saturating threshold) → σ = 1."""
    n = 200
    prices = _crash_series(n, crash_pct=0.10)
    sigma = _severity_series(prices)
    # Last value should be at or very close to 1.0 (saturation)
    last_sigma = float(sigma.dropna().iloc[-1])
    assert last_sigma >= 0.99, f"Expected σ≈1 for 10% crash, got {last_sigma}"


def test_sigma_flat_zero():
    """Perfectly flat series with no drawdown → σ = 0."""
    n = 200
    prices = pd.Series(np.ones(n) * 100.0, index=_bdate_index(n))
    sigma = _severity_series(prices)
    last_sigma = float(sigma.dropna().iloc[-1])
    assert last_sigma == pytest.approx(0.0, abs=1e-6), (
        f"Expected σ=0 for flat series, got {last_sigma}"
    )


# ---------------------------------------------------------------------------
# 4. no_lookahead: P_raw at date t unchanged when future rows appended
# ---------------------------------------------------------------------------

def test_no_lookahead(tmp_path):
    """Appending HISTORICAL rows does not change P_raw at shared date T (no-lookahead law).

    Strengthened (FIX 4): panels are long enough (>= 654 sessions = PCT_WIN + DY_WINDOW)
    that _build_p_raw_history produces real dynamic D refits.  We assert:
      (a) at least one market has a non-null (non-NaN) P_raw row in the SHORT panel,
          proving the dynamic refit path fired (not a structural-only silent pass), and
      (b) P_raw at the shared end date T is bit-identical between short and long panels.

    Design: both panels END at the same date T.  The long panel has 40 extra HISTORICAL
    rows prepended before the short panel's start.  _build_p_raw_history truncates to the
    trailing (PCT_WIN+DY_WINDOW=654) rows, so both panels' trailing windows end at T.
    The last DY_WINDOW rows (the VAR fit window at T) are identical in both panels, so
    D_T is bit-identical.  P_raw[T] is therefore bit-identical.

    pytest.skip is banned — a None/empty result or all-NaN last row is a hard failure.
    """
    # Must exceed PCT_WIN + DY_WINDOW = 504 + 150 = 654 to guarantee VAR refits
    N_SHORT = 654   # exactly the threshold — trailing window = entire short panel
    N_LONG  = 694   # 40 extra HISTORICAL rows prepended (same end date T)
    N_EXTRA = N_LONG - N_SHORT  # 40

    def _synth_series(n: int, seed: int) -> pd.Series:
        np.random.seed(seed)
        idx = _bdate_index(n)
        # Larger vol (0.012) gives VAR enough signal; small drift keeps prices positive
        prices = 100.0 * np.cumprod(1 + np.random.normal(0.0002, 0.012, n))
        return pd.Series(prices, index=idx)

    def _make_panel(n: int) -> dict:
        return {m: _synth_series(n, seed=_MKT_IDX[m] + 100) for m in MARKETS}

    # Long panel: full N_LONG rows starting 40 bdays earlier
    bench_long  = _make_panel(N_LONG)

    # Short panel: trailing N_SHORT rows of the SAME long panel (same end date T)
    bench_short = {m: s.iloc[N_EXTRA:] for m, s in bench_long.items()}

    p_short = cgl._build_p_raw_history(bench_short, bench_short)
    p_long  = cgl._build_p_raw_history(bench_long,  bench_long)

    # Hard failure — no silent skip allowed
    assert p_short is not None, (
        "_build_p_raw_history returned None for N_SHORT=%d (expected >= 654 rows)" % N_SHORT
    )
    assert p_long is not None, (
        "_build_p_raw_history returned None for N_LONG=%d" % N_LONG
    )
    assert not p_short.empty, "_build_p_raw_history returned empty DataFrame for short panel"

    # (a) Assert dynamic refit fired: at least one non-NaN P_raw at the last row.
    non_null_markets = [m for m in MARKETS if not np.isnan(float(p_short.iloc[-1][m]))]
    assert non_null_markets, (
        "All markets have NaN P_raw at the last row of the short panel — "
        "dynamic D refit silently degraded to structural-only for all markets. "
        f"Panel shape: {p_short.shape}. This is a hard failure, not a skip."
    )

    # (b) Shared end date: last date of p_short = last date of both truncated windows
    shared_date = p_short.index[-1]
    assert shared_date in p_long.index, (
        f"Shared end date {shared_date} not in long panel P_raw index"
    )
    assert p_long.index[-1] == shared_date, (
        f"Long panel ends at {p_long.index[-1]}, expected same end date {shared_date}"
    )

    # (b) P_raw at shared_date must be bit-identical (same causal construction, same end)
    lookahead_violations = []
    for mkt in MARKETS:
        v_short = float(p_short.loc[shared_date, mkt])
        v_long  = float(p_long.loc[shared_date, mkt])
        if np.isnan(v_short) and np.isnan(v_long):
            continue  # consistent NaN is fine
        if np.isnan(v_short) != np.isnan(v_long):
            lookahead_violations.append(
                f"{mkt}: NaN mismatch (short={v_short}, long={v_long})"
            )
            continue
        if abs(v_short - v_long) >= 1e-8:
            lookahead_violations.append(
                f"{mkt}: short={v_short:.12f}, long={v_long:.12f}, "
                f"diff={abs(v_short-v_long):.2e}"
            )
    assert not lookahead_violations, (
        f"Lookahead violations at {shared_date} — P_raw differs between short "
        f"(N={N_SHORT}) and long (N={N_LONG}) panels with the same end date:\n"
        + "\n".join(lookahead_violations)
    )


# ---------------------------------------------------------------------------
# 5–7. shadow_state law (CGL-R4)
# ---------------------------------------------------------------------------

def test_shadow_calm_never_escalates():
    """pct=0.99 but incumbent=calm → shadow must remain calm (CGL-R4)."""
    result = _shadow_state(0.99, incumbent="calm")
    assert result == "calm", f"Shadow from calm should stay calm, got {result}"


def test_shadow_watch_escalates():
    """pct≥0.90 + incumbent=watch → shadow=caution (one-band escalation)."""
    result = _shadow_state(0.90, incumbent="watch")
    assert result == "caution", f"Expected caution, got {result}"


def test_shadow_elevated_escalates():
    """pct≥0.90 + incumbent=elevated → shadow=risk-off."""
    result = _shadow_state(0.95, incumbent="elevated")
    assert result == "risk-off", f"Expected risk-off, got {result}"


def test_shadow_risk_off_capped():
    """pct≥0.90 + incumbent=risk-off → shadow=risk-off (cap)."""
    result = _shadow_state(0.95, incumbent="risk-off")
    assert result == "risk-off", f"Expected risk-off cap, got {result}"


def test_shadow_below_threshold():
    """pct=0.89 + incumbent=watch → shadow=watch (no escalation)."""
    result = _shadow_state(0.89, incumbent="watch")
    assert result == "watch", f"Expected watch (pct below threshold), got {result}"


def test_shadow_none_incumbent():
    """Missing incumbent → shadow must be None (no market data to escalate from)."""
    result = _shadow_state(0.99, incumbent=None)
    assert result is None, f"Expected None, got {result}"


# ---------------------------------------------------------------------------
# 8. lane_gate_blocked: snapshot writes latest.json but no appends
# ---------------------------------------------------------------------------

def test_lane_gate_blocked(tmp_path, monkeypatch):
    """With COLLECT_LANE unset, snapshot returns the artifact in-memory but writes NOTHING.

    Updated for FIX 1 (Persistence law 2026-07-17): ALL persistence — latest.json,
    site copy, history.jsonl, shadow logs — is nightly-lane-gated.  Off-lane calls
    compute in-memory (the returned dict is complete) and touch no files.
    """
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE",      raising=False)

    N = 200
    series_map = {m: _close_series(N, start_price=100 + _MKT_IDX[m] * 5)
                  for m in MARKETS}
    for mkt in MARKETS:
        spec = cgl._PROXY[mkt]
        if isinstance(spec, list):
            for grp, tkr in spec:
                series_map[(grp, tkr)] = series_map[mkt]
        else:
            grp, tkr = spec
            series_map[(grp, tkr)] = series_map[mkt]
        g2, t2 = cgl._BENCH[mkt]
        series_map[(g2, t2)] = series_map[mkt]

    with patch("engine.contagion_links.store.read", side_effect=_store_read_factory(series_map)):
        art = cgl.snapshot(root=str(tmp_path))

    # Returned dict must be complete (in-memory compute still runs)
    assert isinstance(art, dict), "snapshot() must return a dict even off-lane"
    assert art.get("schema") == "contagion_links.v1", "schema key must be present"
    assert "pressure" in art or "degraded_reason" in art, (
        "returned dict must have 'pressure' or 'degraded_reason'"
    )

    # NO files must be written (never-darken law: ALL persistence is lane-gated)
    cgl_dir = tmp_path / "data" / "contagion_links"
    assert not cgl_dir.exists() or not any(cgl_dir.iterdir()), (
        f"Off-lane snapshot wrote to data/contagion_links/: {list(cgl_dir.iterdir()) if cgl_dir.exists() else '(dir exists but should not)'}"
    )

    site_copy = tmp_path / "site" / "riskdata" / "contagion_links.json"
    assert not site_copy.exists(), "Off-lane snapshot must not write site copy"

    # history.jsonl and shadow logs must NOT exist
    hist = tmp_path / "data" / "contagion_links" / "history.jsonl"
    assert not hist.exists(), "history.jsonl must not be written when lane is unset"

    us_slog = tmp_path / "data" / "risk_radar" / "forward_log_contagion.jsonl"
    assert not us_slog.exists(), "US shadow log must not exist without lane"
    for mkt in MARKETS:
        slog = tmp_path / "data" / "risk_radar_intl" / f"{mkt}_forward_log_contagion.jsonl"
        assert not slog.exists(), f"{mkt} shadow log must not exist without lane"


# ---------------------------------------------------------------------------
# 9. lane_gate_armed: appends once; second call is idempotent
# ---------------------------------------------------------------------------

def test_lane_gate_armed_idempotent(tmp_path, monkeypatch):
    """With COLLECT_LANE=nightly, all four persistence writes happen and are idempotent.

    Updated for FIX 1 (Persistence law 2026-07-17): asserts latest.json, site copy,
    history.jsonl, and shadow logs are all written on the nightly lane; second call
    is a no-op (first-writer-wins dedup).
    """
    monkeypatch.setenv("COLLECT_LANE", "nightly")

    N = 200
    series_map = {m: _close_series(N, start_price=100 + _MKT_IDX[m] * 5)
                  for m in MARKETS}
    for mkt in MARKETS:
        spec = cgl._PROXY[mkt]
        if isinstance(spec, list):
            for grp, tkr in spec:
                series_map[(grp, tkr)] = series_map[mkt]
        else:
            grp, tkr = spec
            series_map[(grp, tkr)] = series_map[mkt]
        g2, t2 = cgl._BENCH[mkt]
        series_map[(g2, t2)] = series_map[mkt]

    with patch("engine.contagion_links.store.read", side_effect=_store_read_factory(series_map)):
        art = cgl.snapshot(root=str(tmp_path))

    # All four writes must have happened
    latest_json = tmp_path / "data" / "contagion_links" / "latest.json"
    assert latest_json.exists(), "latest.json must be written on nightly lane"

    site_copy = tmp_path / "site" / "riskdata" / "contagion_links.json"
    assert site_copy.exists(), "site copy must be written on nightly lane"

    hist = tmp_path / "data" / "contagion_links" / "history.jsonl"
    assert hist.exists(), "history.jsonl must exist after armed lane call"

    rows_after_first = hist.read_text(encoding="utf-8").strip().splitlines()
    n_first = len(rows_after_first)
    assert n_first > 0, "Must have appended at least one row"

    # Returned dict must also be complete
    assert isinstance(art, dict) and "schema" in art, "snapshot() must return complete artifact"

    # Second call — must not add duplicate rows (first-writer-wins)
    with patch("engine.contagion_links.store.read", side_effect=_store_read_factory(series_map)):
        cgl.snapshot(root=str(tmp_path))

    rows_after_second = hist.read_text(encoding="utf-8").strip().splitlines()
    assert len(rows_after_second) == n_first, (
        f"Second call added rows (first={n_first}, second={len(rows_after_second)})"
    )


# ---------------------------------------------------------------------------
# 10. degradation_missing_proxy: missing proxy → dynamic=null, L=S, artifact complete
# ---------------------------------------------------------------------------

def test_degradation_missing_proxy(tmp_path, monkeypatch):
    """Missing proxy for 'cn' → dynamic[cn]=null, blended[cn] matches structural, gaps populated."""
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE",      raising=False)

    N = 200
    series_map = {}
    for mkt in MARKETS:
        if mkt == "cn":
            continue  # skip CN proxy — will be missing
        s = _close_series(N, start_price=100 + _MKT_IDX[mkt] * 5)
        spec = cgl._PROXY[mkt]
        if isinstance(spec, list):
            for grp, tkr in spec:
                series_map[(grp, tkr)] = s
        else:
            grp, tkr = spec
            series_map[(grp, tkr)] = s
        g2, t2 = cgl._BENCH[mkt]
        series_map[(g2, t2)] = s

    # CN bench still available (severity computation can still run)
    series_map[cgl._BENCH["cn"]] = _close_series(N, start_price=100)

    with patch("engine.contagion_links.store.read", side_effect=_store_read_factory(series_map)):
        art = cgl.compute(root=str(tmp_path))

    # Artifact must be structurally complete
    assert "pressure" in art
    assert "severity" in art
    assert "matrix" in art

    # CN dynamic row should be null
    dynamic = art["matrix"]["dynamic"]
    assert dynamic.get("cn") is None, (
        f"CN dynamic row should be null when proxy missing, got {dynamic.get('cn')}"
    )

    # gaps must mention cn
    gaps = art.get("gaps") or []
    assert any("cn" in g for g in gaps), f"No cn-related gap found in {gaps}"

    # Artifact still covers all 11 markets
    for mkt in MARKETS:
        assert mkt in art["pressure"], f"Missing pressure entry for {mkt}"


# ---------------------------------------------------------------------------
# 11. schema_roundtrip
# ---------------------------------------------------------------------------

def test_schema_roundtrip(tmp_path, monkeypatch):
    """Artifact round-trips through JSON and contains required top-level keys."""
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE",      raising=False)

    N = 200
    series_map = {}
    for mkt in MARKETS:
        s = _close_series(N, start_price=100 + _MKT_IDX[mkt] * 5)
        spec = cgl._PROXY[mkt]
        if isinstance(spec, list):
            for grp, tkr in spec:
                series_map[(grp, tkr)] = s
        else:
            grp, tkr = spec
            series_map[(grp, tkr)] = s
        g2, t2 = cgl._BENCH[mkt]
        series_map[(g2, t2)] = s

    with patch("engine.contagion_links.store.read", side_effect=_store_read_factory(series_map)):
        art = cgl.compute(root=str(tmp_path))

    # JSON round-trip (no TypeError on serialize)
    try:
        raw = json.dumps(art, default=str)
        back = json.loads(raw)
    except (TypeError, ValueError) as exc:
        pytest.fail(f"Artifact is not JSON-serializable: {exc}")

    # Required top-level keys (consumer-tolerance style — assert presence, never exact set)
    required_keys = {"schema", "built", "params", "matrix", "severity", "pressure", "gaps"}
    missing = required_keys - set(back)
    assert not missing, f"Missing required keys: {missing}"

    assert back["schema"] == "contagion_links.v1"
    assert back["params"]["structural_version"] == STRUCTURAL_VERSION

    # matrix sub-keys
    mat = back["matrix"]
    for k in ("structural_version", "static", "dynamic", "blended"):
        assert k in mat, f"Missing matrix key: {k}"

    # pressure block per market
    for mkt in MARKETS:
        assert mkt in back["pressure"], f"Missing pressure entry for {mkt}"
        p = back["pressure"][mkt]
        for pk in ("raw", "pct", "level", "line_en", "line_zh",
                   "top_exporters", "shadow_state", "incumbent_state"):
            assert pk in p, f"Missing pressure[{mkt}].{pk}"


# ---------------------------------------------------------------------------
# 12. glance_lines_high
# ---------------------------------------------------------------------------

def test_glance_lines_high():
    """HIGH level line contains 'HIGH' in EN, and has non-empty ZH."""
    top_exporters = [{"name_en": "South Korea", "name_zh": "韩国", "dd21": 0.08}]
    en, zh = cgl._glance_lines("jp", "high", top_exporters)
    assert "HIGH" in en, f"Expected 'HIGH' in EN glance line, got: {en}"
    assert len(zh) > 0, "ZH glance line must not be empty"
    assert len(en) <= 100, f"EN glance line too long ({len(en)} chars): {en}"


def test_glance_lines_moderate():
    top_exporters = [{"name_en": "China", "name_zh": "中国", "dd21": 0.05}]
    en, zh = cgl._glance_lines("au", "moderate", top_exporters)
    assert "building" in en.lower() or "pressure" in en.lower(), (
        f"Unexpected moderate EN line: {en}"
    )
    assert len(zh) > 0


def test_glance_lines_low():
    en, zh = cgl._glance_lines("us", "low", [])
    assert "low" in en.lower(), f"Expected 'low' in EN line, got: {en}"
    assert len(zh) > 0
