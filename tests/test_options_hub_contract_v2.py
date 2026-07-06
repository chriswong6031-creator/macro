"""tests/test_options_hub_contract_v2.py — hermetic tests for the PAYLOAD CONTRACT v2 additions.

Coverage:
  1.  iv_rank_all: null when < 60 observations
  2.  iv_rank_all: non-null and 0–100 when >= 60 observations
  3.  iv_rank_all vs iv_rank_252: full-history rank can differ from 252-day rank
  4.  coverage_days_all / since_all present in vol payload
  5.  _empty_vol has iv_rank_all / coverage_days_all / since_all fields
  6.  load_gex_history_v2: last 30 rows, correct column mapping
  7.  load_gex_history_v2: absent parquet → None (not error)
  8.  load_gex_history_v2: magnet_up → call_wall, magnet_down → put_wall
  9.  build_context_payload: index_gex populated from gex/latest.json
  10. build_context_payload: fear_greed populated from fear_greed.json
  11. build_context_payload: sector_etf_flows d1/w1 via flows_wide_fn fixture
  12. build_context_payload: gracefully absent inputs → no crash, partial result
  13. build_tickers_ctx: z null when history_n < 20
  14. build_tickers_ctx: z computed when history_n >= 20
  15. build_tickers_ctx: missing parquet → schema default with all z null
  16. build_oi_confirmed: empty when no feed/archive present
  17. build_oi_confirmed: intersection of prev notable ∩ today ΔOI
  18. build_oi_confirmed: contract in prev but NOT in today's movers → excluded
  19. nightly smoke: every CONTRACT v2 object degrades gracefully on missing inputs
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ── ensure repo root on path ──────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.options_hub import (
    _compute_iv_history,
    _empty_vol,
    build_context_payload,
    build_oi_confirmed,
    build_tickers_ctx,
    compute_vol,
    load_gex_history_v2,
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _make_greeks_row(
    root="SPY",
    expiration="2025-12-19",
    strike=500.0,
    right="C",
    date="2025-01-10",
    implied_vol=0.15,
    underlying_price=500.0,
    **kwargs,
) -> dict:
    return dict(
        root=root, expiration=expiration, strike=strike, right=right,
        date=date, implied_vol=implied_vol, underlying_price=underlying_price,
        delta=kwargs.get("delta", 0.5),
        gamma=kwargs.get("gamma", 0.01),
        vanna=kwargs.get("vanna", 0.001),
        charm=kwargs.get("charm", -0.002),
    )


def _build_greeks(n_days: int, asof: str, expiration="2025-12-19") -> pd.DataFrame:
    """Build a synthetic greeks frame with n_days of history."""
    dates = pd.bdate_range(end=asof, periods=n_days).strftime("%Y-%m-%d").tolist()
    rows = []
    for d in dates:
        for right in ("C", "P"):
            rows.append(_make_greeks_row(
                date=d, strike=500.0, right=right,
                implied_vol=0.15 + 0.001 * dates.index(d),
                underlying_price=500.0,
                expiration=expiration,
            ))
    return pd.DataFrame(rows)


def _build_closes(asof: str, n: int = 400) -> pd.Series:
    dates = pd.bdate_range(end=asof, periods=n).strftime("%Y-%m-%d")
    return pd.Series({d: 500.0 + float(i) for i, d in enumerate(dates)})


# --------------------------------------------------------------------------- #
# 1–4. iv_rank_all and coverage fields
# --------------------------------------------------------------------------- #

class TestIvRankAll:
    def test_iv_rank_all_null_when_fewer_than_60(self):
        """iv_rank_all must be None when < 60 observed sessions."""
        asof = "2025-04-30"
        greeks = _build_greeks(n_days=50, asof=asof)
        closes = _build_closes(asof)
        result = compute_vol(greeks, closes, asof, "SPY")
        assert result["iv_rank_all"] is None, (
            f"Expected None for <60 obs, got {result['iv_rank_all']}"
        )

    def test_iv_rank_all_non_null_when_ge_60(self):
        """iv_rank_all is non-null and in [0, 100] when >= 60 sessions."""
        asof = "2025-06-30"
        greeks = _build_greeks(n_days=80, asof=asof)
        closes = _build_closes(asof)
        result = compute_vol(greeks, closes, asof, "SPY")
        assert result["iv_rank_all"] is not None, "Expected non-null iv_rank_all for >=60 obs"
        assert 0.0 <= result["iv_rank_all"] <= 100.0

    def test_iv_rank_all_uses_more_history_than_252(self):
        """With >252 sessions, iv_rank_all uses ALL of them (may differ from iv_rank_252)."""
        asof = "2026-06-30"
        # Build 400 days (>252) with IV rising over time (today's IV is high)
        dates = pd.bdate_range(end=asof, periods=400).strftime("%Y-%m-%d").tolist()
        rows = []
        for i, d in enumerate(dates):
            # IV increases linearly: early dates have low IV, today has highest
            iv = 0.10 + 0.001 * i
            for right in ("C", "P"):
                rows.append(_make_greeks_row(
                    date=d, strike=500.0, right=right,
                    implied_vol=iv, underlying_price=500.0,
                    expiration="2027-01-15",
                ))
        greeks = pd.DataFrame(rows)
        closes = _build_closes(asof, n=500)
        result = compute_vol(greeks, closes, asof, "SPY")
        # iv_rank_252 uses only last 252 — today is highest of 252, so ~100
        # iv_rank_all uses all 400 — today is still highest (IV monotone)
        # Both should be non-null and >= 90 (today is very high in both windows)
        assert result["iv_rank_252"] is not None
        assert result["iv_rank_all"] is not None
        # coverage_days_all should reflect all 400 dates
        assert result["coverage_days_all"] >= 300, (
            f"coverage_days_all={result['coverage_days_all']} expected >=300"
        )

    def test_coverage_days_all_and_since_all_present(self):
        """coverage_days_all and since_all must be in the vol payload."""
        asof = "2025-05-30"
        greeks = _build_greeks(n_days=70, asof=asof)
        closes = _build_closes(asof)
        result = compute_vol(greeks, closes, asof, "SPY")
        assert "coverage_days_all" in result, "Missing coverage_days_all"
        assert "since_all" in result, "Missing since_all"
        assert isinstance(result["coverage_days_all"], int)
        assert result["coverage_days_all"] >= 60

    def test_empty_vol_has_iv_rank_all_fields(self):
        """_empty_vol must include the CONTRACT v2 fields (never KeyError on frontend)."""
        ev = _empty_vol("SPY", "2025-01-10")
        assert "iv_rank_all" in ev
        assert "coverage_days_all" in ev
        assert "since_all" in ev
        assert ev["iv_rank_all"] is None
        assert ev["coverage_days_all"] == 0
        assert ev["since_all"] is None


# --------------------------------------------------------------------------- #
# 5–8. GexPayload.history via load_gex_history_v2
# --------------------------------------------------------------------------- #

class TestGexHistory:
    def _write_summary(self, tmp_dir: Path, root: str, n_rows: int = 40) -> Path:
        """Write a synthetic polygon_gex summary parquet."""
        idx = pd.date_range("2026-05-01", periods=n_rows, freq="B")
        df = pd.DataFrame(
            {
                "spot": 500.0 + np.arange(n_rows, dtype=float),
                "net_gex_bn": np.random.randn(n_rows),
                "gamma_flip": 490.0 + np.random.randn(n_rows),
                "magnet_up": 510.0 + np.arange(n_rows, dtype=float),
                "magnet_down": 490.0 - np.arange(n_rows, dtype=float),
                "gamma_regime": ["long" if i % 2 == 0 else "short" for i in range(n_rows)],
            },
            index=idx,
        )
        p = tmp_dir / f"summary_{root}.parquet"
        df.to_parquet(p)
        return p

    def test_absent_parquet_returns_none(self, tmp_path):
        result = load_gex_history_v2("FAKEXYZ", tmp_path)
        assert result is None

    def test_returns_at_most_30_rows(self, tmp_path):
        self._write_summary(tmp_path, "SPY", n_rows=40)
        result = load_gex_history_v2("SPY", tmp_path)
        assert result is not None
        assert len(result) <= 30, f"Expected <=30 rows, got {len(result)}"

    def test_returns_30_rows_when_more_than_30_available(self, tmp_path):
        self._write_summary(tmp_path, "SPY", n_rows=40)
        result = load_gex_history_v2("SPY", tmp_path)
        assert result is not None
        assert len(result) == 30

    def test_column_mapping_magnet_to_wall(self, tmp_path):
        """magnet_up → call_wall; magnet_down → put_wall."""
        self._write_summary(tmp_path, "SPY", n_rows=10)
        result = load_gex_history_v2("SPY", tmp_path)
        assert result is not None
        for row in result:
            assert "call_wall" in row, "Missing call_wall (mapped from magnet_up)"
            assert "put_wall" in row, "Missing put_wall (mapped from magnet_down)"
            assert "magnet_up" not in row, "magnet_up should be renamed to call_wall"
            assert "magnet_down" not in row, "magnet_down should be renamed to put_wall"

    def test_required_history_fields(self, tmp_path):
        """Each history row must have date, net_gex_bn, gamma_flip, call_wall, put_wall, regime."""
        self._write_summary(tmp_path, "SPY", n_rows=5)
        result = load_gex_history_v2("SPY", tmp_path)
        assert result is not None
        required = ("date", "net_gex_bn", "gamma_flip", "call_wall", "put_wall", "regime")
        for row in result:
            for f in required:
                assert f in row, f"Missing field '{f}' in history row: {row}"

    def test_date_field_is_string(self, tmp_path):
        """date field in each history row must be a YYYY-MM-DD string."""
        self._write_summary(tmp_path, "SPY", n_rows=5)
        result = load_gex_history_v2("SPY", tmp_path)
        assert result is not None
        for row in result:
            assert isinstance(row["date"], str), f"date is not str: {row['date']}"
            assert len(row["date"]) == 10, f"date not YYYY-MM-DD: {row['date']}"

    def test_empty_parquet_returns_empty_list(self, tmp_path):
        """An existing but empty parquet returns [] (not None)."""
        p = tmp_path / "summary_EMPTY.parquet"
        pd.DataFrame().to_parquet(p)
        result = load_gex_history_v2("EMPTY", tmp_path)
        assert result == []


# --------------------------------------------------------------------------- #
# 9–12. build_context_payload
# --------------------------------------------------------------------------- #

class TestContextPayload:
    def _write_gex_latest(self, tmp_path: Path) -> Path:
        p = tmp_path / "latest.json"
        p.write_text(json.dumps({
            "asof": "2026-07-04",
            "source": "cboe_delayed",
            "indices": {
                "SPX": {
                    "spot": 7483.24,
                    "regime": "long",
                    "net_gex_bn": 29.71,
                    "gamma_flip": 7448.75,
                    "dist_to_flip_pct": 0.46,
                    "call_wall": 7550.0,
                    "put_wall": 7300.0,
                },
                "NDX": {
                    "spot": 29329.21,
                    "regime": "long",
                    "net_gex_bn": 1.02,
                    "gamma_flip": 29238.34,
                    "dist_to_flip_pct": 0.31,
                },
            },
        }), encoding="utf-8")
        return p

    def _write_fear_greed(self, tmp_path: Path) -> Path:
        p = tmp_path / "fear_greed.json"
        p.write_text(json.dumps({
            "dial": 54,
            "label_en": "Neutral",
            "label_zh": "中性",
        }), encoding="utf-8")
        return p

    def _flows_wide_fn(self) -> pd.DataFrame:
        """Synthetic flows_wide result."""
        idx = pd.date_range("2026-06-01", periods=10, freq="B")
        return pd.DataFrame({
            "XLK_flow_mn": np.random.randn(10) * 100,
            "XLF_flow_mn": np.random.randn(10) * 50,
        }, index=idx)

    def test_index_gex_populated(self, tmp_path):
        gex_path = self._write_gex_latest(tmp_path)
        fg_path = self._write_fear_greed(tmp_path)
        result = build_context_payload("2026-07-04", gex_path, fg_path)
        assert "index_gex" in result
        assert "SPX" in result["index_gex"]
        spx = result["index_gex"]["SPX"]
        assert spx["regime"] == "long"
        assert spx["net_gex_bn"] is not None

    def test_fear_greed_populated(self, tmp_path):
        gex_path = self._write_gex_latest(tmp_path)
        fg_path = self._write_fear_greed(tmp_path)
        result = build_context_payload("2026-07-04", gex_path, fg_path)
        assert "fear_greed" in result
        fg = result["fear_greed"]
        assert fg["dial"] == 54
        assert fg["label_en"] == "Neutral"

    def test_sector_etf_flows_d1_w1(self, tmp_path):
        gex_path = self._write_gex_latest(tmp_path)
        fg_path = self._write_fear_greed(tmp_path)
        result = build_context_payload(
            "2026-07-04", gex_path, fg_path,
            flows_wide_fn=self._flows_wide_fn,
        )
        assert "sector_etf_flows" in result
        flows = result["sector_etf_flows"]
        assert "XLK" in flows
        xlk = flows["XLK"]
        assert "d1" in xlk
        assert "w1" in xlk
        assert xlk["label"] == "proxy"

    def test_absent_gex_latest_no_crash(self, tmp_path):
        """Missing gex/latest.json: context.json still built (no index_gex)."""
        fg_path = self._write_fear_greed(tmp_path)
        result = build_context_payload(
            "2026-07-04",
            tmp_path / "nonexistent_latest.json",
            fg_path,
        )
        # Must not raise; index_gex may be absent or empty
        assert result["schema"] == "options_hub.context/v1"
        assert result.get("fear_greed") is not None  # fear_greed still loaded

    def test_absent_fear_greed_no_crash(self, tmp_path):
        """Missing fear_greed.json: context.json still built (no fear_greed)."""
        gex_path = self._write_gex_latest(tmp_path)
        result = build_context_payload(
            "2026-07-04",
            gex_path,
            tmp_path / "nonexistent_fear_greed.json",
        )
        assert result["schema"] == "options_hub.context/v1"
        assert "index_gex" in result  # index_gex still loaded

    def test_schema_field_present(self, tmp_path):
        gex_path = self._write_gex_latest(tmp_path)
        fg_path = self._write_fear_greed(tmp_path)
        result = build_context_payload("2026-07-04", gex_path, fg_path)
        assert result["schema"] == "options_hub.context/v1"
        assert result["asof"] == "2026-07-04"

    def test_completely_absent_inputs_no_crash(self, tmp_path):
        """All inputs missing → minimal payload, no exception."""
        result = build_context_payload(
            "2026-07-04",
            tmp_path / "missing1.json",
            tmp_path / "missing2.json",
        )
        assert result["schema"] == "options_hub.context/v1"


# --------------------------------------------------------------------------- #
# 13–15. build_tickers_ctx
# --------------------------------------------------------------------------- #

class TestTickersCtx:
    def _write_tape_flow(self, tmp_path: Path, root: str, n: int) -> Path:
        idx = pd.date_range("2026-01-01", periods=n, freq="B")
        df = pd.DataFrame(
            {
                "net_signed_premium": np.random.randn(n),
                "zerodte_share": np.random.uniform(0, 1, n),
                "short_dated_otm_call_share": np.random.uniform(0, 1, n),
                "vol_gt_oi_share": np.random.uniform(0, 1, n),
                "block_share": np.random.uniform(0, 0.5, n),
            },
            index=idx,
        )
        p = tmp_path / f"{root}.parquet"
        df.to_parquet(p)
        return p

    def test_z_null_when_history_n_lt_20(self, tmp_path):
        """All z fields must be null when < 20 sessions."""
        self._write_tape_flow(tmp_path, "SPY", n=10)
        result = build_tickers_ctx("SPY", "2026-07-04", tmp_path)
        assert result["history_n"] == 10
        for k, v in result["z"].items():
            assert v is None, f"z[{k}]={v} should be None for history_n < 20"

    def test_z_non_null_when_ge_20(self, tmp_path):
        """z fields are computed when >= 20 sessions."""
        self._write_tape_flow(tmp_path, "SPY", n=50)
        result = build_tickers_ctx("SPY", "2026-07-04", tmp_path)
        assert result["history_n"] >= 20
        # at least one z should be non-null (columns exist)
        non_null = [v for v in result["z"].values() if v is not None]
        assert len(non_null) > 0, f"All z are null despite history_n={result['history_n']}"

    def test_schema_fields_present(self, tmp_path):
        self._write_tape_flow(tmp_path, "SPY", n=5)
        result = build_tickers_ctx("SPY", "2026-07-04", tmp_path)
        assert result["schema"] == "options_hub.tickers_ctx/v1"
        assert result["root"] == "SPY"
        assert "z" in result
        expected_z_keys = {
            "net_signed_premium_z252",
            "zerodte_share_z252",
            "short_dated_otm_call_share_z252",
            "vol_gt_oi_share_z252",
            "block_share_z252",
        }
        assert set(result["z"].keys()) == expected_z_keys

    def test_missing_parquet_returns_schema_default(self, tmp_path):
        """Absent parquet → default payload, all z null, history_n=0."""
        result = build_tickers_ctx("FAKEXYZ", "2026-07-04", tmp_path)
        assert result["schema"] == "options_hub.tickers_ctx/v1"
        assert result["history_n"] == 0
        for v in result["z"].values():
            assert v is None

    def test_history_n_boundary_exactly_20(self, tmp_path):
        """Exactly 20 sessions → z should be computed."""
        self._write_tape_flow(tmp_path, "SPY", n=20)
        result = build_tickers_ctx("SPY", "2026-07-04", tmp_path)
        assert result["history_n"] >= 20
        # at least some z non-null
        non_null = [v for v in result["z"].values() if v is not None]
        assert len(non_null) > 0


# --------------------------------------------------------------------------- #
# 16–18. build_oi_confirmed
# --------------------------------------------------------------------------- #

class TestOiConfirmed:
    def _write_feed(self, tmp_path: Path, root_top_contracts: dict) -> Path:
        p = tmp_path / "feed_current.json"
        payload = {
            "schema": "live_flow.feed/v1",
            "root_top_contracts": root_top_contracts,
        }
        p.write_text(json.dumps(payload), encoding="utf-8")
        return p

    def _movers(self, contracts: list[dict]) -> dict:
        return {"schema": "options_hub.oi_movers/v1", "asof": "2026-07-04", "movers": contracts}

    def test_empty_when_no_feed(self, tmp_path):
        """No feed/archive in live_flow_out → empty confirmed list."""
        result = build_oi_confirmed("2026-07-04", tmp_path)
        assert result == []

    def test_intersection_match(self, tmp_path):
        """Contract in prev feed AND in today's movers → appears in confirmed."""
        self._write_feed(tmp_path, {
            "SPY": [
                {"right": "C", "expiration": "2026-09-19", "strike": 560.0,
                 "premium": 12000.0},
            ],
        })
        movers = self._movers([
            {"root": "SPY", "right": "C", "exp": "2026-09-19",
             "strike": 560.0, "d_oi": 5000, "mid": 5.5},
        ])
        result = build_oi_confirmed("2026-07-04", tmp_path, oi_movers_today=movers)
        assert len(result) == 1
        row = result[0]
        assert row["root"] == "SPY"
        assert row["right"] == "C"
        assert row["delta_oi"] == 5000

    def test_contract_not_in_movers_excluded(self, tmp_path):
        """Contract in prev feed but NOT in today's movers → excluded."""
        self._write_feed(tmp_path, {
            "SPY": [
                {"right": "C", "expiration": "2026-09-19", "strike": 560.0,
                 "premium": 12000.0},
            ],
        })
        movers = self._movers([
            # Different strike — should not match
            {"root": "SPY", "right": "C", "exp": "2026-09-19",
             "strike": 570.0, "d_oi": 3000, "mid": 4.0},
        ])
        result = build_oi_confirmed("2026-07-04", tmp_path, oi_movers_today=movers)
        assert result == [], f"Expected empty, got {result}"

    def test_empty_movers_returns_empty(self, tmp_path):
        """No today's movers → empty confirmed."""
        self._write_feed(tmp_path, {
            "SPY": [
                {"right": "C", "expiration": "2026-09-19", "strike": 560.0,
                 "premium": 5000.0},
            ],
        })
        result = build_oi_confirmed("2026-07-04", tmp_path, oi_movers_today=self._movers([]))
        assert result == []

    def test_confirmed_row_schema(self, tmp_path):
        """Each confirmed row has: root, right, exp, strike, prev_premium, delta_oi."""
        self._write_feed(tmp_path, {
            "QQQ": [
                {"right": "P", "expiration": "2026-08-21", "strike": 450.0,
                 "premium": 8000.0},
            ],
        })
        movers = self._movers([
            {"root": "QQQ", "right": "P", "exp": "2026-08-21",
             "strike": 450.0, "d_oi": -2000, "mid": 3.2},
        ])
        result = build_oi_confirmed("2026-07-04", tmp_path, oi_movers_today=movers)
        assert len(result) == 1
        row = result[0]
        for field in ("root", "right", "exp", "strike", "prev_premium", "delta_oi"):
            assert field in row, f"Missing field '{field}' in confirmed row"


# --------------------------------------------------------------------------- #
# 19. Nightly smoke: graceful degradation on ALL missing inputs
# --------------------------------------------------------------------------- #

class TestNightlySmoke:
    def test_all_contract_v2_objects_degrade_gracefully(self, tmp_path):
        """Every CONTRACT v2 object builder handles missing inputs without raising.

        Simulates a nightly run where ALL data paths are absent.
        """
        errors: list[str] = []

        # context.json
        try:
            ctx = build_context_payload(
                "2026-07-04",
                tmp_path / "missing_gex.json",
                tmp_path / "missing_fg.json",
            )
            assert ctx["schema"] == "options_hub.context/v1"
        except Exception as exc:
            errors.append(f"build_context_payload raised: {exc}")

        # tickers_ctx
        try:
            tctx = build_tickers_ctx("SPY", "2026-07-04", tmp_path)
            assert tctx["schema"] == "options_hub.tickers_ctx/v1"
        except Exception as exc:
            errors.append(f"build_tickers_ctx raised: {exc}")

        # oi_confirmed
        try:
            oi_conf = build_oi_confirmed("2026-07-04", tmp_path)
            assert isinstance(oi_conf, list)
        except Exception as exc:
            errors.append(f"build_oi_confirmed raised: {exc}")

        # load_gex_history_v2
        try:
            hist = load_gex_history_v2("NOEXIST", tmp_path)
            assert hist is None
        except Exception as exc:
            errors.append(f"load_gex_history_v2 raised: {exc}")

        assert not errors, "Graceful degradation failures:\n" + "\n".join(errors)

    def test_vol_payload_with_tiny_history_has_all_v2_fields(self):
        """Even a single-session greeks frame must produce all CONTRACT v2 vol fields."""
        asof = "2025-01-10"
        rows = [_make_greeks_row(date=asof, expiration="2025-06-20")]
        greeks = pd.DataFrame(rows)
        closes = pd.Series({"2025-01-09": 500.0, "2025-01-10": 500.0})
        result = compute_vol(greeks, closes, asof, "SPY")
        for field in ("iv_rank_all", "coverage_days_all", "since_all"):
            assert field in result, f"Missing CONTRACT v2 field: {field}"
        # With only 1 day, everything is null/0 — but the fields exist
        assert result["iv_rank_all"] is None
        assert result["coverage_days_all"] >= 0

    def test_compute_vol_all_nan_implied_vol_does_not_raise(self):
        """Regression: greeks frame with asof rows but all implied_vol NaN must not raise
        ValueError (5-tuple unpack). _compute_iv_history valid.empty branch must return
        5-tuple, not 2-tuple. Reproduces the stale `return [], None` early-exit bug."""
        import numpy as np
        asof = "2025-01-10"
        rows = [
            _make_greeks_row(date=asof, expiration="2025-06-20", implied_vol=float("nan")),
            _make_greeks_row(date=asof, expiration="2025-09-19", implied_vol=float("nan")),
        ]
        greeks = pd.DataFrame(rows)
        closes = pd.Series({"2025-01-09": 500.0, "2025-01-10": 500.0})
        # Must not raise ValueError: not enough values to unpack
        result = compute_vol(greeks, closes, asof, "SPY")
        assert isinstance(result, dict), "compute_vol must return a dict"
        for field in ("iv_rank_all", "coverage_days_all", "since_all"):
            assert field in result, f"Missing v2 field: {field}"
        assert result["iv_rank_all"] is None
        assert result["coverage_days_all"] == 0
        assert result["since_all"] is None
