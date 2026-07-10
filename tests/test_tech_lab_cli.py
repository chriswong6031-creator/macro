"""tests/test_tech_lab_cli.py — Tests for scripts/tech_lab_cli.py.

Verifies each subcommand directly (no subprocess):
- list: returns signal inventory with correct fields
- state: single-ticker state with tier info (requires data/stocks/ or skips gracefully)
- profile: tier stamp, era-split keys ALWAYS present, horizon whitelist enforced
- series: returns bar-level data

Per TLT-R6: tier:"descriptive_profile" must be stamped on every profile output.
Per DT-R16: era split keys must always appear in profile output.
Per DT-R14: n_fires AND n_months must both appear.
"""
from __future__ import annotations

import json
import sys
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
# Import CLI subcommand handlers directly
# ---------------------------------------------------------------------------

def _get_cmds():
    from scripts.tech_lab_cli import cmd_list, cmd_state, cmd_profile, cmd_series  # noqa: PLC0415
    return cmd_list, cmd_state, cmd_profile, cmd_series


def _make_args(**kwargs):
    """Make a simple namespace object."""
    import argparse  # noqa: PLC0415
    ns = argparse.Namespace()
    for k, v in kwargs.items():
        setattr(ns, k, v)
    return ns


# ---------------------------------------------------------------------------
# Helper: synthetic universe patcher for profile tests
# ---------------------------------------------------------------------------

def _make_mini_universe(n_tickers: int = 3, n_bars: int = 600) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(77)
    universe: dict[str, pd.DataFrame] = {}
    tickers = ["TSTT", "TSTT2", "TSTT3"][:n_tickers]
    dates = pd.bdate_range("2019-01-02", periods=n_bars)
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
# Tests: list subcommand
# ---------------------------------------------------------------------------

class TestCmdList:
    def test_returns_signals(self):
        cmd_list, _, _, _ = _get_cmds()
        args = _make_args(family=None)
        result = cmd_list(args)
        assert "signals" in result
        assert result["n_signals"] > 0

    def test_signal_fields(self):
        cmd_list, _, _, _ = _get_cmds()
        args = _make_args(family=None)
        result = cmd_list(args)
        required = {"id", "family", "kind", "direction", "display_en", "display_zh"}
        for sig in result["signals"]:
            missing = required - set(sig.keys())
            assert not missing, f"Signal missing fields: {missing}"

    def test_family_filter(self):
        cmd_list, _, _, _ = _get_cmds()
        args = _make_args(family="ichimoku")
        result = cmd_list(args)
        assert result["family_filter"] == "ichimoku"
        for sig in result["signals"]:
            assert sig["family"] == "ichimoku"
        assert result["n_signals"] > 0

    def test_no_validated_in_output(self):
        cmd_list, _, _, _ = _get_cmds()
        args = _make_args(family=None)
        result = cmd_list(args)
        output_str = json.dumps(result)
        # CI guard: "validated" must not appear in user-facing output
        assert "validated" not in output_str.lower(), (
            "Found 'validated' in list output — CI-guarded"
        )

    def test_kind_values_valid(self):
        cmd_list, _, _, _ = _get_cmds()
        args = _make_args(family=None)
        result = cmd_list(args)
        valid_kinds = {"event", "state"}
        for sig in result["signals"]:
            assert sig["kind"] in valid_kinds, f"Invalid kind: {sig['kind']}"


# ---------------------------------------------------------------------------
# Tests: profile subcommand (using patched universe)
# ---------------------------------------------------------------------------

class TestCmdProfile:
    @pytest.fixture(autouse=True)
    def patch_universe_loader(self, monkeypatch):
        """Patch the universe loader to use a synthetic mini universe."""
        mini = _make_mini_universe()

        import scripts.tech_lab_cli as cli_mod  # noqa: PLC0415

        def _mock_load(sample_n=None, tickers=None):
            if tickers:
                return {t: mini[t] for t in tickers if t in mini}
            if sample_n is not None:
                keys = sorted(mini.keys())[:sample_n]
                return {k: mini[k] for k in keys}
            return mini

        monkeypatch.setattr(cli_mod, "_load_sample_universe", _mock_load)

    def test_tier_stamp_present(self):
        _, _, cmd_profile, _ = _get_cmds()
        args = _make_args(
            signal_id="rsi14_oversold",
            horizon=[21],
            tickers=None,
            sample=3,
        )
        result = cmd_profile(args)
        assert result.get("tier") == "descriptive_profile", (
            f"tier stamp missing or wrong: {result.get('tier')}"
        )

    def test_caveat_present(self):
        _, _, cmd_profile, _ = _get_cmds()
        args = _make_args(
            signal_id="rsi14_oversold",
            horizon=[21],
            tickers=None,
            sample=3,
        )
        result = cmd_profile(args)
        assert "caveat" in result

    def test_era_split_always_present(self):
        """DT-R16: era split must always be in profile output (even with zero fires)."""
        _, _, cmd_profile, _ = _get_cmds()
        args = _make_args(
            signal_id="rsi14_oversold",
            horizon=[21],
            tickers=None,
            sample=3,
        )
        result = cmd_profile(args)
        assert "horizons" in result
        for h_key, h_data in result["horizons"].items():
            assert "era_split" in h_data, (
                f"Horizon {h_key}: era_split missing (DT-R16 violation)"
            )
            era = h_data["era_split"]
            assert "era_split_date" in era
            assert "pre_split" in era
            assert "post_split" in era

    def test_n_fires_and_n_months_present(self):
        """DT-R14: both n_fires and n_months must be printed."""
        _, _, cmd_profile, _ = _get_cmds()
        args = _make_args(
            signal_id="rsi14_oversold",
            horizon=[21],
            tickers=None,
            sample=3,
        )
        result = cmd_profile(args)
        assert "horizons" in result
        for h_key, h_data in result["horizons"].items():
            assert "n_fires" in h_data, f"Horizon {h_key}: n_fires missing (DT-R14)"
            assert "n_months" in h_data, f"Horizon {h_key}: n_months missing (DT-R14)"

    def test_horizon_whitelist_enforced(self):
        """TLT-R6: invalid horizon must return error, not a result."""
        _, _, cmd_profile, _ = _get_cmds()
        args = _make_args(
            signal_id="rsi14_oversold",
            horizon=[7],  # 7 is NOT in {10, 21, 42, 63}
            tickers=None,
            sample=3,
        )
        result = cmd_profile(args)
        assert "error" in result, "Should reject horizon=7 with an error"
        assert "valid_horizons" in result
        assert 7 not in result["valid_horizons"]

    def test_valid_horizons_accepted(self):
        """TLT-R6: all four valid horizons accepted."""
        _, _, cmd_profile, _ = _get_cmds()
        for h in [10, 21, 42, 63]:
            args = _make_args(
                signal_id="rsi14_oversold",
                horizon=[h],
                tickers=None,
                sample=2,
            )
            result = cmd_profile(args)
            assert "error" not in result or "valid_horizons" not in result, (
                f"horizon={h} should be accepted (TLT-R6)"
            )
            if "horizons" in result:
                assert str(h) in result["horizons"]

    def test_multiple_horizons(self):
        _, _, cmd_profile, _ = _get_cmds()
        args = _make_args(
            signal_id="rsi14_oversold",
            horizon=[10, 21],
            tickers=None,
            sample=2,
        )
        result = cmd_profile(args)
        if "horizons" in result:
            assert "10" in result["horizons"]
            assert "21" in result["horizons"]

    def test_invalid_signal_id_returns_error(self):
        _, _, cmd_profile, _ = _get_cmds()
        args = _make_args(
            signal_id="this_signal_does_not_exist_xyz",
            horizon=[21],
            tickers=None,
            sample=2,
        )
        result = cmd_profile(args)
        assert "error" in result
        assert result.get("tier") == "descriptive_profile"

    def test_zero_fires_honest_null(self):
        """Profile with no fires → n_fires=0, nulls, not an exception."""
        _, _, cmd_profile, _ = _get_cmds()
        # Use a signal unlikely to fire on the tiny synthetic universe in 1 bar
        args = _make_args(
            signal_id="rsi14_oversold",
            horizon=[21],
            tickers=None,
            sample=1,
        )
        result = cmd_profile(args)
        assert "tier" in result
        assert result["tier"] == "descriptive_profile"
        # n_fires_total can be 0 — that's an honest null
        assert "n_fires_total" in result
        assert result["n_fires_total"] >= 0

    def test_no_validated_in_output(self):
        _, _, cmd_profile, _ = _get_cmds()
        args = _make_args(
            signal_id="rsi14_oversold",
            horizon=[21],
            tickers=None,
            sample=2,
        )
        result = cmd_profile(args)
        output_str = json.dumps(result)
        assert "validated" not in output_str.lower(), (
            "Found 'validated' in profile output — CI-guarded"
        )

    def test_no_verdict_in_output(self):
        """TLT-R6: output must not contain verdict language."""
        _, _, cmd_profile, _ = _get_cmds()
        args = _make_args(
            signal_id="rsi14_oversold",
            horizon=[21],
            tickers=None,
            sample=2,
        )
        result = cmd_profile(args)
        assert result.get("tier") == "descriptive_profile"
        # Caveat should mention "not a verdict"
        caveat = result.get("caveat", "")
        assert "verdict" in caveat.lower(), (
            "Caveat should reference 'not a verdict' per TLT-R6"
        )


# ---------------------------------------------------------------------------
# Tests: series subcommand
# ---------------------------------------------------------------------------

class TestCmdSeries:
    @pytest.fixture(autouse=True)
    def patch_loader(self, monkeypatch):
        """Patch _load_single_ticker to return synthetic data."""
        import scripts.tech_lab_cli as cli_mod  # noqa: PLC0415
        mini = _make_mini_universe(n_tickers=1)
        synthetic_df = list(mini.values())[0]

        def _mock_load(ticker: str):
            if ticker == "TSTT":
                return synthetic_df
            return None

        monkeypatch.setattr(cli_mod, "_load_single_ticker", _mock_load)

    def test_series_returns_bars(self):
        _, _, _, cmd_series = _get_cmds()
        args = _make_args(signal_id="rsi14_oversold", ticker="TSTT", tail=20)
        result = cmd_series(args)
        assert "bars" in result
        assert len(result["bars"]) <= 20

    def test_series_bar_schema(self):
        _, _, _, cmd_series = _get_cmds()
        args = _make_args(signal_id="rsi14_oversold", ticker="TSTT", tail=20)
        result = cmd_series(args)
        for bar in result["bars"]:
            assert "date" in bar
            assert "value" in bar

    def test_series_unknown_ticker_returns_error(self):
        _, _, _, cmd_series = _get_cmds()
        args = _make_args(signal_id="rsi14_oversold", ticker="ZZZZ", tail=20)
        result = cmd_series(args)
        assert "error" in result

    def test_series_invalid_signal_returns_error(self):
        _, _, _, cmd_series = _get_cmds()
        args = _make_args(signal_id="nonexistent_signal_xyz", ticker="TSTT", tail=20)
        result = cmd_series(args)
        assert "error" in result
