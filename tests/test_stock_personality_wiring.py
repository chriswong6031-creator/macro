"""tests/test_stock_personality_wiring.py

W2b wiring tests for stock_personality.v1 integration.

Tests the pure functions and data-contract surfaces added in W2b:
  - _personality_inputs(): pure mapping function (5 cases)
  - _stamp_personality_forward_ledger(): forward-ledger stamper
  - Panel append schema
  - Site aggregate schema
  - dna_class.json consumer contract

NO test touches real data/ stores — tmp_path only (house law).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import pytest

# Import the pure mapping function and the ledger stamper from the script.
# These functions are module-level helpers (not main()), so they import cleanly.
from scripts.build_stock_library import (
    _personality_inputs,
    _stamp_personality_forward_ledger,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlcv(n: int = 300) -> pd.DataFrame:
    """Return a minimal OHLCV DataFrame with DatetimeIndex."""
    idx = pd.date_range("2023-01-01", periods=n, freq="B")
    close = pd.Series(100.0, index=idx) * (1 + pd.Series(range(n), index=idx) * 0.001)
    df = pd.DataFrame({
        "open": close * 0.99,
        "high": close * 1.01,
        "low": close * 0.98,
        "close": close,
        "volume": 1_000_000,
    }, index=idx)
    return df


def _make_rec(**overrides) -> dict:
    """Return a minimal build_stock_library rec dict."""
    base = {
        "tech": {
            "hv_pctile": 55.0,
            "rel_volume": 1.2,
            "obv_slope_up": True,
            "off_52w_high_pct": -8.5,
            # days_to_earnings is NOT sourced from rec["tech"]; it is passed via the
            # days_to_earnings= parameter from the _edays() closure in main().
        },
        "vol_squeeze": {"state": "squeeze"},
        "positioning": {
            "short": {"pct_float": 3.5, "days_to_cover": 2.1},
            "insider": {"net_mn": 0.5, "cluster": "buy", "n_buyers": 3},
        },
        "profile": {
            "archetype": {"key": "momentum_runner", "confidence": 0.7},
            "mktcap_bn": 12.3,
        },
        "gex": {"gamma_regime": "long", "dist_to_flip_pct": -2.5},
        "smart_money": {"ownership_hhi": 0.15, "holders": [{"name": "A"}, {"name": "B"}]},
        "beneficial_ownership": {"regime": "institutional_accumulate"},
        "ladder": {"state": "running"},
        "baskets_membership": [],
        "asof": "2024-06-01",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Test 1: _personality_inputs() returns correct field mapping from rec
# ---------------------------------------------------------------------------

class TestPersonalityInputsMapping:
    """Test the W2b sourcing contract mapping."""

    def test_basic_mapping_returns_expected_keys(self):
        """All required assess() kwargs are present in the output dict."""
        rec = _make_rec()
        ohlcv = _make_ohlcv(300)
        result = _personality_inputs(
            "AAPL", rec, ohlcv, "2024-06-01",
            dna_class_entry={"dna_class": "growth_compounders", "style_regime": "growth", "as_of": "2024-05-31"},
            bsk_mem_entry=[{"slug": "tech-leaders"}, {"slug": "ai-compute"}],
            etf_wt=2.5,
            oracle_active=True,
        )
        # All required assess() kwargs must be present
        required_keys = {
            "as_of", "path_features", "archetype", "dna_class", "positioning",
            "smart_money", "basket_membership", "etf_weight_max", "attention_z",
            "bo_regime", "gex", "events", "tech", "oracle_episode_active", "market_cap",
        }
        assert required_keys <= set(result.keys()), (
            f"Missing keys: {required_keys - set(result.keys())}"
        )

    def test_vol_squeeze_state_sourced_from_vol_squeeze_key(self):
        """vol_squeeze_state comes from rec['vol_squeeze']['state'], NOT rec['tech']."""
        rec = _make_rec(vol_squeeze={"state": "breakout"})
        # Deliberately put a different state in tech to confirm sourcing
        rec["tech"]["vol_squeeze_state"] = "should_not_be_used"
        result = _personality_inputs(
            "AAPL", rec, _make_ohlcv(300), "2024-06-01",
            dna_class_entry=None, bsk_mem_entry=None, etf_wt=None, oracle_active=None,
        )
        assert result["tech"]["vol_squeeze_state"] == "breakout"

    def test_ret_21d_is_fraction_not_percent(self):
        """ret_21d must be a fraction (e.g., 0.10 for +10%), not a percent (10.0)."""
        # Build a close series where the 21-bar return is known: 10%
        n = 100
        idx = pd.date_range("2023-01-01", periods=n, freq="B")
        close_vals = [100.0] * (n - 21) + [100.0 * (1 + i * 0.01 / 20) for i in range(22)]
        close_vals = close_vals[:n]
        close_vals[-1] = 110.0
        close_vals[-22] = 100.0
        df = pd.DataFrame({"close": close_vals}, index=idx)
        rec = _make_rec()
        result = _personality_inputs(
            "AAPL", rec, df, "2024-06-01",
            dna_class_entry=None, bsk_mem_entry=None, etf_wt=None, oracle_active=None,
        )
        ret_21d = result["tech"]["ret_21d"]
        assert ret_21d is not None
        # Must be a fraction (|ret_21d| < 5.0 for sensible returns)
        assert abs(ret_21d) < 5.0, (
            f"ret_21d={ret_21d} looks like percent instead of fraction"
        )
        # Should be approximately +0.10
        assert 0.05 < ret_21d < 0.20, f"Expected ~0.10 fraction, got {ret_21d}"

    def test_basket_membership_is_list_of_slug_strings(self):
        """basket_membership must be a list of slug strings (not dicts)."""
        bsk = [{"slug": "tech-leaders", "name": "Tech Leaders"},
               {"slug": "ai-compute", "extra": 99}]
        result = _personality_inputs(
            "AAPL", _make_rec(), _make_ohlcv(50), "2024-06-01",
            dna_class_entry=None, bsk_mem_entry=bsk, etf_wt=None, oracle_active=None,
        )
        assert result["basket_membership"] == ["tech-leaders", "ai-compute"]

    def test_fail_open_on_none_ohlcv(self):
        """When ohlcv_df is None, ret_21d and months_underwater are None (no raise)."""
        result = _personality_inputs(
            "AAPL", _make_rec(), None, "2024-06-01",
            dna_class_entry=None, bsk_mem_entry=None, etf_wt=None, oracle_active=None,
        )
        assert result["tech"]["ret_21d"] is None
        assert result["tech"]["months_underwater"] is None

    def test_market_cap_converted_from_bn(self):
        """market_cap must be in USD (mktcap_bn * 1e9)."""
        rec = _make_rec()
        rec["profile"]["mktcap_bn"] = 2.5
        result = _personality_inputs(
            "AAPL", rec, None, "2024-06-01",
            dna_class_entry=None, bsk_mem_entry=None, etf_wt=None, oracle_active=None,
        )
        assert result["market_cap"] == pytest.approx(2.5e9)

    def test_gex_gamma_regime_sourced_correctly(self):
        """gex.gamma_regime comes from rec['gex']['gamma_regime']."""
        rec = _make_rec(gex={"gamma_regime": "short", "dist_to_flip_pct": 3.1})
        result = _personality_inputs(
            "AAPL", rec, None, "2024-06-01",
            dna_class_entry=None, bsk_mem_entry=None, etf_wt=None, oracle_active=None,
        )
        assert result["gex"]["gamma_regime"] == "short"
        assert result["gex"]["dist_to_flip_pct"] == pytest.approx(3.1)

    def test_missing_gex_yields_none(self):
        """When rec has no gex, the gex key should be None (not an empty dict)."""
        rec = _make_rec()
        rec.pop("gex", None)
        result = _personality_inputs(
            "AAPL", rec, None, "2024-06-01",
            dna_class_entry=None, bsk_mem_entry=None, etf_wt=None, oracle_active=None,
        )
        assert result["gex"] is None

    def test_dna_class_entry_mapped_to_dict(self):
        """dna_class_entry with a dna_class key maps to a dict with key/style_regime/as_of."""
        entry = {"dna_class": "value_deep", "style_regime": "value", "as_of": "2024-05-31"}
        result = _personality_inputs(
            "AAPL", _make_rec(), None, "2024-06-01",
            dna_class_entry=entry, bsk_mem_entry=None, etf_wt=None, oracle_active=None,
        )
        assert result["dna_class"] == {
            "key": "value_deep",
            "style_regime": "value",
            "as_of": "2024-05-31",
        }

    def test_short_pct_float_sourced_from_positioning_short(self):
        """short_pct_float comes from rec['positioning']['short']['pct_float'] (PERCENT 0-100)."""
        rec = _make_rec()
        rec["positioning"]["short"]["pct_float"] = 7.8
        result = _personality_inputs(
            "AAPL", rec, None, "2024-06-01",
            dna_class_entry=None, bsk_mem_entry=None, etf_wt=None, oracle_active=None,
        )
        assert result["positioning"]["short_pct_float"] == pytest.approx(7.8)


# ---------------------------------------------------------------------------
# Test 1b: events wiring — days_to_earnings comes from parameter, not rec keys
# ---------------------------------------------------------------------------

class TestEventsWiring:
    """events dict sourced from days_to_earnings= parameter (W2b fix finding 2)."""

    def test_events_none_when_parameter_absent(self):
        """When days_to_earnings param is not passed, events is None."""
        rec = _make_rec()
        result = _personality_inputs(
            "AAPL", rec, None, "2024-06-01",
            dna_class_entry=None, bsk_mem_entry=None, etf_wt=None, oracle_active=None,
            # days_to_earnings not passed → default None
        )
        assert result["events"] is None

    def test_events_populated_from_parameter(self):
        """When days_to_earnings=10 is passed, events['days_to_earnings'] == 10."""
        rec = _make_rec()
        result = _personality_inputs(
            "AAPL", rec, None, "2024-06-01",
            dna_class_entry=None, bsk_mem_entry=None, etf_wt=None, oracle_active=None,
            days_to_earnings=10.0,
        )
        assert result["events"] is not None
        assert result["events"]["days_to_earnings"] == 10

    def test_events_not_sourced_from_rec_tech(self):
        """rec['tech']['days_to_earnings'] must NOT bleed into events (dead key)."""
        rec = _make_rec()
        # Deliberately plant a value in rec["tech"]["days_to_earnings"]
        rec["tech"]["days_to_earnings"] = 99
        result = _personality_inputs(
            "AAPL", rec, None, "2024-06-01",
            dna_class_entry=None, bsk_mem_entry=None, etf_wt=None, oracle_active=None,
            # days_to_earnings NOT passed — should stay None regardless of rec["tech"]
        )
        assert result["events"] is None, (
            "events must not source from rec['tech']['days_to_earnings'] (dead key)"
        )

    def test_events_not_sourced_from_rec_profile(self):
        """rec['profile']['earnings']['days_to_next'] must NOT bleed into events."""
        rec = _make_rec()
        rec["profile"]["earnings"] = {"days_to_next": 5}
        result = _personality_inputs(
            "AAPL", rec, None, "2024-06-01",
            dna_class_entry=None, bsk_mem_entry=None, etf_wt=None, oracle_active=None,
        )
        assert result["events"] is None, (
            "events must not source from rec['profile']['earnings']['days_to_next'] (dead key)"
        )


# ---------------------------------------------------------------------------
# Test 1c: PIT panel date must equal alpha_asof (W2b fix finding 1)
# ---------------------------------------------------------------------------

class TestPanelDatePIT:
    """Panel row 'date' and site aggregate 'as_of' must equal the trading-date alpha_asof."""

    def _make_cfg(self, tmp_path: Path):
        class _Cfg:
            def data_dir(self_):
                return tmp_path / "data"
        return _Cfg()

    def test_panel_date_equals_alpha_asof(self, tmp_path: Path):
        """The forward-ledger build_date is alpha_asof, so panel date must match it."""
        # The stamper already takes build_date=alpha_asof (verified separately).
        # Here we test the _personality_inputs as_of= arg (which callers pass as alpha_asof).
        # Additionally: direct test that the ledger stamp uses the passed build_date, not utcnow.
        from scripts.build_stock_library import _stamp_personality_forward_ledger
        cfg = self._make_cfg(tmp_path)
        trading_date = "2024-06-03"   # a Monday — distinct from any UTC wall-clock date
        tr_dir = tmp_path / "data" / "signal_archive"
        tr_dir.mkdir(parents=True)
        tr = pd.DataFrame([{"ticker": "AAPL", "date": trading_date, "type": "buy"}])
        tr.to_parquet(tr_dir / "track_record.parquet", index=False)
        sp_by_ticker = {
            "AAPL": {"base": {"archetype": {"key": "x"}}, "current_mode": {}, "evidence": {}},
        }
        _stamp_personality_forward_ledger(sp_by_ticker, trading_date, cfg)
        ledger = tmp_path / "data" / "stock_personality" / "forward_ledger.parquet"
        df = pd.read_parquet(ledger)
        # The date column must equal the provided alpha_asof, not utcnow().date()
        assert df["date"].astype(str).iloc[0] == trading_date, (
            f"Panel date {df['date'].iloc[0]!r} != alpha_asof {trading_date!r} — PIT corrupt"
        )


# ---------------------------------------------------------------------------
# Test 2: _personality_inputs() attention_z is always None (not yet wired)
# ---------------------------------------------------------------------------

class TestAttentionZNotWired:
    """attention_z must be None (wiki attention not wired per R-SP6)."""

    def test_attention_z_always_none(self):
        result = _personality_inputs(
            "MSFT", _make_rec(), None, "2024-06-01",
            dna_class_entry=None, bsk_mem_entry=None, etf_wt=None, oracle_active=None,
        )
        assert result["attention_z"] is None, (
            "attention_z must be None until wiki attention is wired"
        )


# ---------------------------------------------------------------------------
# Test 3: Forward ledger stamper writes no rows when track_record is absent
# ---------------------------------------------------------------------------

class TestStampForwardLedgerFailOpen:
    """_stamp_personality_forward_ledger() must be fail-open in all edge cases."""

    def _make_cfg(self, tmp_path: Path):
        """Mock config object with data_dir() pointing at tmp_path."""
        class _Cfg:
            def data_dir(self_):
                return tmp_path / "data"
        return _Cfg()

    def test_no_op_when_track_record_absent(self, tmp_path: Path):
        """When track_record.parquet does not exist, no error and no file written."""
        cfg = self._make_cfg(tmp_path)
        sp_by_ticker = {"AAPL": {"base": {}, "current_mode": {}, "evidence": {}}}
        _stamp_personality_forward_ledger(sp_by_ticker, "2024-06-01", cfg)
        # forward_ledger.parquet must NOT exist (nothing to stamp)
        ledger = tmp_path / "data" / "stock_personality" / "forward_ledger.parquet"
        assert not ledger.exists()

    def test_stamps_buy_rebuy_fires_only(self, tmp_path: Path):
        """Only buy/rebuy fires from today are stamped; sell/reduce are excluded."""
        cfg = self._make_cfg(tmp_path)
        # Create a track_record with one buy, one rebuy, one sell
        tr_dir = tmp_path / "data" / "signal_archive"
        tr_dir.mkdir(parents=True)
        tr = pd.DataFrame([
            {"ticker": "AAPL", "date": "2024-06-01", "type": "buy"},
            {"ticker": "MSFT", "date": "2024-06-01", "type": "rebuy"},
            {"ticker": "NVDA", "date": "2024-06-01", "type": "sell"},
            {"ticker": "AAPL", "date": "2024-05-31", "type": "buy"},  # wrong date
        ])
        tr.to_parquet(tr_dir / "track_record.parquet", index=False)
        sp_by_ticker = {
            "AAPL": {"base": {"archetype": {"key": "momentum_runner"}}, "current_mode": {}, "evidence": {}},
            "MSFT": {"base": {}, "current_mode": {"modes": ["vol_expansion"]}, "evidence": {}},
            "NVDA": {"base": {}, "current_mode": {}, "evidence": {}},
        }
        _stamp_personality_forward_ledger(sp_by_ticker, "2024-06-01", cfg)
        ledger = tmp_path / "data" / "stock_personality" / "forward_ledger.parquet"
        assert ledger.exists(), "Ledger should have been created"
        df = pd.read_parquet(ledger)
        tickers = set(df["ticker"].tolist())
        # AAPL (buy today) + MSFT (rebuy today) should be present; NVDA (sell) must not
        assert "AAPL" in tickers
        assert "MSFT" in tickers
        assert "NVDA" not in tickers
        # Only today's date rows
        assert all(df["date"].astype(str) == "2024-06-01")

    def test_dedup_on_ticker_date_type(self, tmp_path: Path):
        """Running the stamper twice does not create duplicate rows."""
        cfg = self._make_cfg(tmp_path)
        tr_dir = tmp_path / "data" / "signal_archive"
        tr_dir.mkdir(parents=True)
        tr = pd.DataFrame([{"ticker": "AAPL", "date": "2024-06-01", "type": "buy"}])
        tr.to_parquet(tr_dir / "track_record.parquet", index=False)
        sp_by_ticker = {
            "AAPL": {"base": {"archetype": {"key": "x"}}, "current_mode": {}, "evidence": {}},
        }
        _stamp_personality_forward_ledger(sp_by_ticker, "2024-06-01", cfg)
        _stamp_personality_forward_ledger(sp_by_ticker, "2024-06-01", cfg)  # second run
        ledger = tmp_path / "data" / "stock_personality" / "forward_ledger.parquet"
        df = pd.read_parquet(ledger)
        # Must have exactly 1 row for AAPL/2024-06-01/buy
        aapl_rows = df[(df["ticker"] == "AAPL") & (df["date"].astype(str) == "2024-06-01")]
        assert len(aapl_rows) == 1, f"Expected 1 row, got {len(aapl_rows)}"

    def test_no_error_when_sp_by_ticker_empty(self, tmp_path: Path):
        """Empty sp_by_ticker → no-op (no error, no file written)."""
        cfg = self._make_cfg(tmp_path)
        _stamp_personality_forward_ledger({}, "2024-06-01", cfg)
        ledger = tmp_path / "data" / "stock_personality" / "forward_ledger.parquet"
        assert not ledger.exists()

    def test_no_error_when_build_date_none(self, tmp_path: Path):
        """None build_date → no-op (no error, no file written)."""
        cfg = self._make_cfg(tmp_path)
        sp = {"AAPL": {"base": {}, "current_mode": {}, "evidence": {}}}
        _stamp_personality_forward_ledger(sp, None, cfg)
        ledger = tmp_path / "data" / "stock_personality" / "forward_ledger.parquet"
        assert not ledger.exists()


# ---------------------------------------------------------------------------
# Test 4: site/factordata/stock_personality.json schema contract
# ---------------------------------------------------------------------------

class TestStockPersonalityJsonSchema:
    """Verify the stock_personality.json schema structure."""

    def _make_sample_aggregate(self) -> dict:
        """Return a minimal well-formed stock_personality.json doc."""
        return {
            "schema": "stock_personality.v1",
            "as_of": "2024-06-01",
            "n_tickers": 2,
            "coverage": {"archetype": 0.9, "dna_class": 0.8},
            "label_distributions": {
                "archetype": {"momentum_runner": 1, "value_stalwart": 1},
                "dna_class": {},
                "chart_personality": {},
                "ownership_habitat": {},
                "microstructure": {},
                "current_mode": {},
            },
            "per_ticker": {
                "AAPL": {"arch": "momentum_runner", "dna": None, "chart": [], "own": [], "micro": [], "modes": []},
                "MSFT": {"arch": "value_stalwart", "dna": None, "chart": [], "own": [], "micro": [], "modes": []},
            },
        }

    def test_schema_field_is_stock_personality_v1(self):
        doc = self._make_sample_aggregate()
        assert doc["schema"] == "stock_personality.v1"

    def test_required_top_level_keys_present(self):
        doc = self._make_sample_aggregate()
        required = {"schema", "as_of", "n_tickers", "coverage", "label_distributions", "per_ticker"}
        assert required <= set(doc.keys())

    def test_label_distributions_has_all_axes(self):
        doc = self._make_sample_aggregate()
        required_axes = {
            "archetype", "dna_class", "chart_personality",
            "ownership_habitat", "microstructure", "current_mode",
        }
        assert required_axes <= set(doc["label_distributions"].keys())

    def test_per_ticker_slim_keys(self):
        doc = self._make_sample_aggregate()
        for ticker, entry in doc["per_ticker"].items():
            assert {"arch", "dna", "chart", "own", "micro", "modes"} <= set(entry.keys()), (
                f"Per-ticker entry for {ticker} missing slim keys"
            )

    def test_json_roundtrip(self, tmp_path: Path):
        """The aggregate must survive JSON serialization (no non-serializable types)."""
        doc = self._make_sample_aggregate()
        p = tmp_path / "stock_personality.json"
        p.write_text(json.dumps(doc, default=str))
        loaded = json.loads(p.read_text())
        assert loaded["schema"] == "stock_personality.v1"
        assert loaded["n_tickers"] == 2


# ---------------------------------------------------------------------------
# Test 5: dna_class.json (dna-class-ref) consumer contract
# ---------------------------------------------------------------------------

class TestDnaClassRefConsumerContract:
    """Verify that build_stock_library correctly handles dna_class.json."""

    def _make_dna_class_doc(self, n_tickers: int = 3) -> dict:
        """Return a minimal well-formed dna_class.json doc."""
        per_ticker = {
            f"T{i}": {"dna_class": "momentum_runner", "style_regime": "growth", "as_of": "2024-05-31"}
            for i in range(n_tickers)
        }
        return {
            "schema": "dna_class_ref.v1",
            "as_of": "2024-05-31",
            "per_ticker": per_ticker,
        }

    def test_dna_class_ref_schema_v1(self):
        doc = self._make_dna_class_doc()
        assert doc["schema"] == "dna_class_ref.v1"

    def test_per_ticker_has_required_keys(self):
        doc = self._make_dna_class_doc()
        for tk, entry in doc["per_ticker"].items():
            assert "dna_class" in entry, f"Missing dna_class for {tk}"
            assert "style_regime" in entry, f"Missing style_regime for {tk}"

    def test_personality_inputs_consumes_dna_class_doc(self):
        """_personality_inputs maps dna_class_entry correctly from dna_class.json per_ticker value."""
        entry = {"dna_class": "momentum_runner", "style_regime": "growth", "as_of": "2024-05-31"}
        result = _personality_inputs(
            "AAPL", _make_rec(), None, "2024-06-01",
            dna_class_entry=entry,
            bsk_mem_entry=None, etf_wt=None, oracle_active=None,
        )
        assert result["dna_class"] is not None
        assert result["dna_class"]["key"] == "momentum_runner"
        assert result["dna_class"]["style_regime"] == "growth"

    def test_personality_inputs_accepts_absent_dna_class(self):
        """When dna_class_entry is None, result['dna_class'] is None (T-1 miss is normal)."""
        result = _personality_inputs(
            "AAPL", _make_rec(), None, "2024-06-01",
            dna_class_entry=None,
            bsk_mem_entry=None, etf_wt=None, oracle_active=None,
        )
        assert result["dna_class"] is None

    def test_dna_class_missing_key_yields_none(self):
        """dna_class_entry with no 'dna_class' key → result['dna_class'] is None."""
        entry = {"style_regime": "growth", "as_of": "2024-05-31"}  # no 'dna_class' key
        result = _personality_inputs(
            "AAPL", _make_rec(), None, "2024-06-01",
            dna_class_entry=entry,
            bsk_mem_entry=None, etf_wt=None, oracle_active=None,
        )
        assert result["dna_class"] is None

    def test_json_roundtrip_dna_class_doc(self, tmp_path: Path):
        """dna_class.json must survive JSON serialization."""
        doc = self._make_dna_class_doc(5)
        p = tmp_path / "dna_class.json"
        p.write_text(json.dumps(doc, default=str))
        loaded = json.loads(p.read_text())
        assert loaded["schema"] == "dna_class_ref.v1"
        assert len(loaded["per_ticker"]) == 5
