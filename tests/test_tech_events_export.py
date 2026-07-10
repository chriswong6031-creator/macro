"""tests/test_tech_events_export.py — Tests for the tech_events export (TLT-R3).

Verifies:
- Schema compliance: every per-ticker JSON has the required top-level keys.
- window_start is present and is a valid ISO date string.
- PIT integrity: every fire date <= last bar date for that ticker.
- Fire dates are real bar dates (not invented dates).
- Signals dict structure: each entry has dir/kind/fires/state keys.
- lab_exempt families (fundamental_valuation, insider) appear with fires=[] if included.
- _index.json is written and has generated_utc + tickers dict.

Run: python -m pytest tests/test_tech_events_export.py -q
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import os
os.chdir(_REPO_ROOT)


# ---------------------------------------------------------------------------
# Helper: minimal synthetic universe for the export path
# ---------------------------------------------------------------------------

def _make_mini_universe(n_tickers: int = 3, n_bars: int = 600) -> dict[str, pd.DataFrame]:
    """Build a synthetic universe with enough bars for indicator warmup."""
    rng = np.random.default_rng(99)
    universe: dict[str, pd.DataFrame] = {}
    tickers = ["AAAA", "BBBB", "CCCC"][:n_tickers]
    start = pd.Timestamp("2020-01-02")
    dates = pd.bdate_range(start, periods=n_bars)
    for ticker in tickers:
        close = 100.0 * np.cumprod(1.0 + rng.normal(0.0003, 0.012, size=n_bars))
        high = close * (1.0 + rng.uniform(0.001, 0.02, size=n_bars))
        low = close * (1.0 - rng.uniform(0.001, 0.02, size=n_bars))
        vol = rng.lognormal(15.5, 0.4, n_bars)
        df = pd.DataFrame(
            {"open": close, "high": high, "low": low, "close": close, "volume": vol},
            index=dates,
        )
        df.attrs["ticker"] = ticker
        universe[ticker] = df
    return universe


# ---------------------------------------------------------------------------
# Integration: run the export path on --sample 3 into tmp
# ---------------------------------------------------------------------------

class TestTechEventsExportIntegration:
    """Run build_all with sample universe, write tech_events, assert schema."""

    @pytest.fixture(scope="class")
    def export_result(self, tmp_path_factory):
        """Run the full export pipeline on a mini universe and return (tmp_dir, events)."""
        from scripts.build_tech_lab_data import build_all, write_tech_events  # noqa: PLC0415
        from engine import tech_catalog as tc  # noqa: PLC0415
        from engine import tech_score  # noqa: PLC0415
        from engine import tech_stars  # noqa: PLC0415

        tmp_dir = tmp_path_factory.mktemp("tech_events_test")

        universe = _make_mini_universe(n_tickers=3, n_bars=600)
        df_spx = pd.DataFrame({"close": pd.Series(dtype=float)})
        name_map = {t: t for t in universe.keys()}

        screener, lab, te_by_ticker = build_all(
            universe, tc, tech_score, tech_stars, df_spx, name_map,
        )
        events_dir = write_tech_events(te_by_ticker, tmp_dir)
        return tmp_dir, te_by_ticker, events_dir, universe

    def test_index_json_exists(self, export_result):
        tmp_dir, te_by_ticker, events_dir, universe = export_result
        index_path = events_dir / "_index.json"
        assert index_path.exists(), "_index.json not written"

    def test_index_schema(self, export_result):
        tmp_dir, te_by_ticker, events_dir, universe = export_result
        index_path = events_dir / "_index.json"
        with open(index_path) as f:
            idx = json.load(f)
        assert "generated_utc" in idx
        assert "tickers" in idx
        assert isinstance(idx["tickers"], dict)
        # Should have entries for our mini universe tickers
        for ticker in universe.keys():
            assert ticker in idx["tickers"]

    def test_per_ticker_files_exist(self, export_result):
        tmp_dir, te_by_ticker, events_dir, universe = export_result
        for ticker in universe.keys():
            p = events_dir / f"{ticker}.json"
            assert p.exists(), f"Missing file for {ticker}"

    def test_per_ticker_schema(self, export_result):
        tmp_dir, te_by_ticker, events_dir, universe = export_result
        required_keys = {"ticker", "generated_utc", "window_start", "signals"}
        for ticker in universe.keys():
            with open(events_dir / f"{ticker}.json") as f:
                d = json.load(f)
            missing = required_keys - set(d.keys())
            assert not missing, f"{ticker}: missing keys {missing}"
            assert d["ticker"] == ticker
            # window_start is a valid date string
            _dt = datetime.strptime(d["window_start"], "%Y-%m-%d")
            assert isinstance(d["signals"], dict)

    def test_signal_entry_schema(self, export_result):
        tmp_dir, te_by_ticker, events_dir, universe = export_result
        signal_required = {"dir", "kind", "fires", "state"}
        for ticker in universe.keys():
            with open(events_dir / f"{ticker}.json") as f:
                d = json.load(f)
            for sid, sig_data in d["signals"].items():
                missing = signal_required - set(sig_data.keys())
                assert not missing, f"{ticker}/{sid}: missing keys {missing}"
                assert sig_data["kind"] in {"event", "state"}
                assert sig_data["state"] in {0, 1}
                assert sig_data["dir"] in {-1, 0, 1}
                assert isinstance(sig_data["fires"], list)

    def test_pit_integrity(self, export_result):
        """Every fire date must be <= last bar date for that ticker."""
        tmp_dir, te_by_ticker, events_dir, universe = export_result
        for ticker, df in universe.items():
            last_bar = str(df.index[-1].date())
            with open(events_dir / f"{ticker}.json") as f:
                d = json.load(f)
            for sid, sig_data in d["signals"].items():
                for fire_date_str in sig_data["fires"]:
                    assert fire_date_str <= last_bar, (
                        f"PIT violation: {ticker}/{sid} fire {fire_date_str} > "
                        f"last bar {last_bar}"
                    )

    def test_fire_dates_are_real_bar_dates(self, export_result):
        """Fire dates must be actual trading days (in the ticker's index)."""
        tmp_dir, te_by_ticker, events_dir, universe = export_result
        for ticker, df in universe.items():
            bar_dates = {str(d.date()) for d in df.index}
            with open(events_dir / f"{ticker}.json") as f:
                d_json = json.load(f)
            for sid, sig_data in d_json["signals"].items():
                for fire_date_str in sig_data["fires"]:
                    assert fire_date_str in bar_dates, (
                        f"{ticker}/{sid}: fire date {fire_date_str} is not a real bar date"
                    )

    def test_window_start_is_past(self, export_result):
        """window_start should be approximately 3 years before now."""
        tmp_dir, te_by_ticker, events_dir, universe = export_result
        ticker = list(universe.keys())[0]
        with open(events_dir / f"{ticker}.json") as f:
            d = json.load(f)
        ws_dt = datetime.strptime(d["window_start"], "%Y-%m-%d").date()
        today = date.today()
        diff_years = (today - ws_dt).days / 365.25
        # Should be approximately 3 years (allow ±1 day rounding)
        assert 2.99 <= diff_years <= 3.01, (
            f"window_start {ws_dt} is not ~3 years before today ({today}), diff={diff_years:.3f}y"
        )

    def test_lab_exempt_families_fires_empty(self, export_result):
        """Lab-exempt families (fundamental_valuation, insider) appear only when state==1,
        and their fires list must be empty (no bar-level fires).
        """
        tmp_dir, te_by_ticker, events_dir, universe = export_result
        from engine import tech_catalog as tc  # noqa: PLC0415
        exempt_families = {"fundamental_valuation", "insider"}
        exempt_sids = {
            s["signal_id"] for s in tc.list_signals()
            if s.get("family", "") in exempt_families
        }
        for ticker in universe.keys():
            with open(events_dir / f"{ticker}.json") as f:
                d = json.load(f)
            for sid, sig_data in d["signals"].items():
                if sid in exempt_sids:
                    assert sig_data["fires"] == [], (
                        f"{ticker}/{sid}: exempt family signal should have fires=[]"
                    )

    def test_index_n_fires_nonnegative(self, export_result):
        """n_fires_total per ticker in the index must be >= 0."""
        tmp_dir, te_by_ticker, events_dir, universe = export_result
        with open(events_dir / "_index.json") as f:
            idx = json.load(f)
        for ticker, n_fires in idx["tickers"].items():
            assert isinstance(n_fires, int)
            assert n_fires >= 0

    def test_zero_fires_signals_omitted(self, export_result):
        """Signals with zero fires AND state==0 should be absent from the output."""
        tmp_dir, te_by_ticker, events_dir, universe = export_result
        for ticker in universe.keys():
            with open(events_dir / f"{ticker}.json") as f:
                d = json.load(f)
            for sid, sig_data in d["signals"].items():
                # If it's included, either fires is non-empty OR state==1
                has_fires = len(sig_data["fires"]) > 0
                has_state = sig_data["state"] == 1
                assert has_fires or has_state, (
                    f"{ticker}/{sid}: zero fires AND state==0 should be omitted"
                )
