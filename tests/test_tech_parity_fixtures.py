"""tests/test_tech_parity_fixtures.py — Determinism guard for parity fixtures (TLT-R5).

Verifies that regenerating the fixtures from scratch produces byte-identical output
to what is committed in tests/fixtures/tech_parity/. This ensures:
  1. The committed fixtures are reproducible.
  2. Any engine change that changes indicator output causes a CI failure, which
     signals to the Terminal team that they need to update TypeScript indicatorMath.

Also verifies fixture internal consistency:
  - All arrays have the correct length (n_bars).
  - Null entries only appear during warmup windows.
  - First non-null values appear at the expected warmup offsets.

Run: python -m pytest tests/test_tech_parity_fixtures.py -q
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import os
os.chdir(_REPO_ROOT)

_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "tech_parity"


# ---------------------------------------------------------------------------
# Helper: load committed fixture
# ---------------------------------------------------------------------------

def _load_fixture(name: str) -> dict:
    path = _FIXTURE_DIR / name
    assert path.exists(), f"Fixture missing: {path}. Run: python scripts/build_tech_parity_fixtures.py"
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Determinism guard: regenerate and compare byte-by-byte
# ---------------------------------------------------------------------------

class TestFixtureDeterminism:
    """Regenerating fixtures must produce byte-identical output to committed files."""

    @pytest.fixture(scope="class")
    def regenerated_dir(self, tmp_path_factory):
        """Run the fixture builder into a temp dir and return the path."""
        from scripts.build_tech_parity_fixtures import build_fixtures  # noqa: PLC0415
        tmp = tmp_path_factory.mktemp("parity_regen")
        build_fixtures(tmp)
        return tmp

    def _read_bytes(self, path: Path) -> bytes:
        with open(path, "rb") as f:
            return f.read()

    @pytest.mark.parametrize("filename", [
        "ohlcv.json",
        "expected_ichimoku.json",
        "expected_ribbon.json",
        "expected_rsi.json",
        "expected_bollinger.json",
        "expected_m2.json",
    ])
    def test_byte_identical(self, regenerated_dir, filename):
        """Regenerated file must be byte-identical to the committed fixture."""
        committed_path = _FIXTURE_DIR / filename
        regen_path = regenerated_dir / filename

        assert committed_path.exists(), f"Committed fixture missing: {committed_path}"
        assert regen_path.exists(), f"Regenerated fixture missing: {regen_path}"

        committed = self._read_bytes(committed_path)
        regenerated = self._read_bytes(regen_path)

        assert committed == regenerated, (
            f"Fixture {filename} is NOT byte-identical after regeneration. "
            f"Engine change detected — update committed fixture with: "
            f"python scripts/build_tech_parity_fixtures.py"
        )


# ---------------------------------------------------------------------------
# Structural checks on committed fixtures
# ---------------------------------------------------------------------------

class TestFixtureStructure:
    """Verify the structure of the committed fixture files."""

    def test_ohlcv_fields(self):
        d = _load_fixture("ohlcv.json")
        assert "n_bars" in d
        assert "rng_seed" in d
        assert d["rng_seed"] == 42
        assert "dates" in d
        assert len(d["dates"]) == d["n_bars"]
        for col in ["open", "high", "low", "close", "volume"]:
            assert col in d
            assert len(d[col]) == d["n_bars"]

    def test_ohlcv_n_bars(self):
        d = _load_fixture("ohlcv.json")
        assert d["n_bars"] >= 500, "Expected at least 500 bars"

    def test_ohlcv_hlc_consistency(self):
        """High >= Close >= Low for all bars."""
        d = _load_fixture("ohlcv.json")
        for i, (h, c, l) in enumerate(zip(d["high"], d["close"], d["low"])):
            assert h >= c, f"Bar {i}: high={h} < close={c}"
            assert c >= l, f"Bar {i}: close={c} < low={l}"

    def test_ichimoku_fields(self):
        d = _load_fixture("expected_ichimoku.json")
        n_bars = _load_fixture("ohlcv.json")["n_bars"]
        for key in ["tenkan", "kijun", "span_a", "span_b", "chikou"]:
            assert key in d, f"Missing key: {key}"
            assert len(d[key]) == n_bars, f"{key}: expected {n_bars} bars"

    def test_ichimoku_warmup_nulls(self):
        """Tenkan (period=9) should have nulls in first 8 bars."""
        d = _load_fixture("expected_ichimoku.json")
        tenkan = d["tenkan"]
        # First 8 bars should be null (rolling(9, min_periods=9) needs 9 complete bars)
        for i in range(8):
            assert tenkan[i] is None, f"Tenkan bar {i} should be null (warmup)"

    def test_ichimoku_kijun_warmup(self):
        """Kijun (period=26) should have nulls in first 25 bars."""
        d = _load_fixture("expected_ichimoku.json")
        kijun = d["kijun"]
        for i in range(25):
            assert kijun[i] is None, f"Kijun bar {i} should be null (warmup)"

    def test_rsi_fields(self):
        d = _load_fixture("expected_rsi.json")
        n_bars = _load_fixture("ohlcv.json")["n_bars"]
        for key in ["rsi_7", "rsi_14", "rsi_21"]:
            assert key in d, f"Missing key: {key}"
            assert len(d[key]) == n_bars

    def test_rsi_range(self):
        """RSI values should be in [0, 100] where non-null."""
        d = _load_fixture("expected_rsi.json")
        for key in ["rsi_7", "rsi_14", "rsi_21"]:
            for i, v in enumerate(d[key]):
                if v is not None:
                    assert 0.0 <= v <= 100.0, (
                        f"{key}[{i}]={v} out of range [0,100]"
                    )

    def test_rsi_warmup_nulls(self):
        """RSI-14 first non-null after warmup (period 14)."""
        d = _load_fixture("expected_rsi.json")
        rsi14 = d["rsi_14"]
        # First 14 values should all be null (the SMA-seeded RMA needs n bars)
        for i in range(14):
            assert rsi14[i] is None, f"rsi_14[{i}] should be null (warmup)"
        # Bar 14 should have a value
        assert rsi14[14] is not None, "rsi_14[14] should be non-null"

    def test_ribbon_fields(self):
        d = _load_fixture("expected_ribbon.json")
        n_bars = _load_fixture("ohlcv.json")["n_bars"]
        for key in ["fast_ema", "slow_ema", "ribbon_state"]:
            assert key in d, f"Missing key: {key}"
            assert len(d[key]) == n_bars

    def test_ribbon_state_values(self):
        """Ribbon state must be in {-1, 0, 1} or null."""
        d = _load_fixture("expected_ribbon.json")
        valid = {-1.0, 0.0, 1.0, -1, 0, 1}
        for i, v in enumerate(d["ribbon_state"]):
            if v is not None:
                assert v in valid, f"ribbon_state[{i}]={v} not in {{-1,0,1}}"

    def test_bollinger_fields(self):
        d = _load_fixture("expected_bollinger.json")
        n_bars = _load_fixture("ohlcv.json")["n_bars"]
        for key in ["upper", "mid", "lower"]:
            assert key in d, f"Missing key: {key}"
            assert len(d[key]) == n_bars

    def test_bollinger_band_order(self):
        """upper >= mid >= lower where non-null."""
        d = _load_fixture("expected_bollinger.json")
        for i, (u, m, l) in enumerate(zip(d["upper"], d["mid"], d["lower"])):
            if u is not None and m is not None and l is not None:
                assert u >= m, f"Bollinger[{i}]: upper={u} < mid={m}"
                assert m >= l, f"Bollinger[{i}]: mid={m} < lower={l}"

    def test_bollinger_warmup_nulls(self):
        """Bollinger (period=20) should have nulls in first 19 bars."""
        d = _load_fixture("expected_bollinger.json")
        mid = d["mid"]
        for i in range(19):
            assert mid[i] is None, f"Bollinger mid[{i}] should be null (warmup)"

    def test_params_documented(self):
        """Each fixture should document its _params."""
        for name in ["expected_ichimoku.json", "expected_ribbon.json",
                     "expected_rsi.json", "expected_bollinger.json",
                     "expected_m2.json"]:
            d = _load_fixture(name)
            assert "_params" in d, f"{name}: missing _params documentation"

    # ---- expected_m2.json structural checks --------------------------------

    def test_m2_fields(self):
        """expected_m2.json has all required array keys."""
        d = _load_fixture("expected_m2.json")
        n_bars = _load_fixture("ohlcv.json")["n_bars"]
        for key in ["rolling_vwap_n20", "week_anchored_vwap",
                    "anchored_vwap_pos50", "rolling_poc_w126_b24"]:
            assert key in d, f"expected_m2.json: missing key {key}"
            assert len(d[key]) == n_bars, \
                f"expected_m2.json {key}: expected {n_bars} bars, got {len(d[key])}"

    def test_m2_volume_profile_final_present(self):
        """volume_profile_final key is present and non-null."""
        d = _load_fixture("expected_m2.json")
        assert "volume_profile_final" in d, "expected_m2.json: missing volume_profile_final"
        vp = d["volume_profile_final"]
        assert vp is not None, "volume_profile_final should be non-null for 500 bars"
        for key in ("poc", "va_low", "va_high", "total_volume", "bin_edges",
                    "bin_volumes", "window_used"):
            assert key in vp, f"volume_profile_final: missing key {key}"

    def test_m2_rolling_vwap_warmup_nulls(self):
        """rolling_vwap_n20: first 19 bars null (warmup = n-1 = 19)."""
        d = _load_fixture("expected_m2.json")
        rv = d["rolling_vwap_n20"]
        for i in range(19):
            assert rv[i] is None, f"rolling_vwap_n20[{i}] should be null (warmup)"
        assert rv[19] is not None, "rolling_vwap_n20[19] should be non-null"

    def test_m2_anchored_vwap_pos50_warmup_nulls(self):
        """anchored_vwap_pos50: bars 0..49 are null (before anchor)."""
        d = _load_fixture("expected_m2.json")
        av = d["anchored_vwap_pos50"]
        for i in range(50):
            assert av[i] is None, f"anchored_vwap_pos50[{i}] should be null (before anchor)"
        assert av[50] is not None, "anchored_vwap_pos50[50] should be non-null"

    def test_m2_rolling_poc_warmup_nulls(self):
        """rolling_poc_w126_b24: first 126 bars null (warmup = window = 126)."""
        d = _load_fixture("expected_m2.json")
        rp = d["rolling_poc_w126_b24"]
        for i in range(126):
            assert rp[i] is None, f"rolling_poc_w126_b24[{i}] should be null (warmup)"
        assert rp[126] is not None, "rolling_poc_w126_b24[126] should be non-null"

    def test_m2_week_anchored_vwap_no_leading_nulls(self):
        """week_anchored_vwap has no warmup: first bar is always non-null."""
        d = _load_fixture("expected_m2.json")
        wv = d["week_anchored_vwap"]
        assert wv[0] is not None, "week_anchored_vwap[0] should be non-null (no warmup)"

    def test_m2_rolling_vwap_positive_values(self):
        """rolling_vwap values (where non-null) should be positive (price > 0)."""
        d = _load_fixture("expected_m2.json")
        for i, v in enumerate(d["rolling_vwap_n20"]):
            if v is not None:
                assert v > 0.0, f"rolling_vwap_n20[{i}]={v} should be positive"

    def test_m2_volume_profile_va_gte_70pct(self):
        """volume_profile_final: VA volume >= 70% of total."""
        d = _load_fixture("expected_m2.json")
        vp = d["volume_profile_final"]
        assert vp is not None
        edges = vp["bin_edges"]
        bin_vols = vp["bin_volumes"]
        va_low = vp["va_low"]
        va_high = vp["va_high"]
        total = vp["total_volume"]
        included = sum(
            bv for i, bv in enumerate(bin_vols)
            if edges[i] >= va_low - 1e-9 and edges[i + 1] <= va_high + 1e-9
        )
        assert included >= 0.70 * total, \
            f"VA volume {included} < 70% of {total}"
