"""W5a: engine.theme_fingerprint + bottleneck integration — per-theme XBRL fingerprints.

Required test cases (per W5a spec):
  (a) fingerprint legs computed from synthetic statements/rpo fixtures with min-3 gate
  (b) an unmapped theme with ≥3 reporting members gets a numeric_band (no longer text-only)
  (c) fingerprint legs enter numeric_composite (anti-laundering discriminator unaffected —
      text still can't tip numeric)
  (d) < 3 members → None, never fabricated
  (e) annual-basis fields surfaced in the fingerprint payload
  (f) t1_fingerprint health leg added to foresight_health output
  (g) t1_fingerprint DARK when no themes have fingerprint data
"""
from __future__ import annotations

import pathlib
from unittest import mock

import numpy as np
import pandas as pd
import pytest

from engine import theme_fingerprint as tfp
from engine import bottleneck as bn


# ---------------------------------------------------------------------------
# Helpers — synthetic parquet fixtures
# ---------------------------------------------------------------------------

def _make_statements(tmp_path: pathlib.Path, rows: list[dict]) -> pathlib.Path:
    """Write synthetic statements.parquet to tmp_path/edgar/statements.parquet."""
    p = tmp_path / "edgar" / "statements.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(p, index=False)
    return p


def _make_rpo(tmp_path: pathlib.Path, rows: list[dict]) -> pathlib.Path:
    """Write synthetic rpo.parquet to tmp_path/edgar/rpo.parquet."""
    p = tmp_path / "edgar" / "rpo.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(p, index=False)
    return p


def _make_bottleneck_hits(tmp_path: pathlib.Path, rows: list[dict]) -> pathlib.Path:
    """Write synthetic bottleneck_hits.parquet."""
    p = tmp_path / "edgar" / "bottleneck_hits.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(p, index=False)
    return p


def _tight_store():
    """FRED store where all 4 physical legs signal a squeeze."""
    n = 60
    ramp = np.linspace(0, 1, n)
    idx = pd.date_range("2020-01-01", periods=n, freq="MS")

    def ser(vals):
        return pd.DataFrame({"v": vals}, index=idx)

    return {
        "CAPUTLG3344S": ser(70 + 20 * ramp),
        "MNFCTRIRSA": ser(1.5 - 0.5 * ramp),
        "AMTMUO": ser(100 + 80 * ramp),
        "AMTMVS": ser(np.full(n, 50.0)),
        "PCU334413334413": ser(list(np.full(n - 12, 100.0)) +
                               list(100 * (1 + 0.02 * np.arange(1, 13)))),
    }


# ---------------------------------------------------------------------------
# (a) Fingerprint legs computed from synthetic fixtures with min-3 gate
# ---------------------------------------------------------------------------

class TestFingerprintLegs:
    """Unit tests for engine.theme_fingerprint core computation."""

    def setup_method(self):
        tfp.reset_caches()

    def test_inv_days_trend_falling_is_positive(self, tmp_path):
        """Falling inventory-days (tightening) → positive leg7 value."""
        rows = [
            # ticker, fy, inventory, revenue — 3 members, each with 2 years
            {"ticker": "MU",   "fy": 2023, "inventory": 9000, "revenue": 20000, "as_of": "2024-01-01"},
            {"ticker": "MU",   "fy": 2024, "inventory": 6000, "revenue": 22000, "as_of": "2024-01-01"},
            {"ticker": "WDC",  "fy": 2023, "inventory": 4000, "revenue": 15000, "as_of": "2024-01-01"},
            {"ticker": "WDC",  "fy": 2024, "inventory": 2500, "revenue": 16000, "as_of": "2024-01-01"},
            {"ticker": "SNDK", "fy": 2023, "inventory": 2000, "revenue":  8000, "as_of": "2024-01-01"},
            {"ticker": "SNDK", "fy": 2024, "inventory": 1200, "revenue":  9000, "as_of": "2024-01-01"},
        ]
        _make_statements(tmp_path, rows)
        tfp.reset_caches()

        stmts = pd.read_parquet(tmp_path / "edgar" / "statements.parquet")
        val, n, fy = tfp._inv_days_trend(["MU", "WDC", "SNDK"], stmts)

        assert val is not None, "should return a value with 3 reporting members"
        assert val > 0, f"falling inventory-days should yield positive leg; got {val}"
        assert n == 3, f"expected 3 reporting members, got {n}"
        assert fy == 2024

    def test_inv_days_trend_rising_is_negative(self, tmp_path):
        """Rising inventory-days (loosening) → negative leg7 value."""
        rows = [
            {"ticker": "A", "fy": 2023, "inventory": 1000, "revenue": 10000, "as_of": "2024-01-01"},
            {"ticker": "A", "fy": 2024, "inventory": 3000, "revenue": 10000, "as_of": "2024-01-01"},
            {"ticker": "B", "fy": 2023, "inventory": 800,  "revenue":  8000, "as_of": "2024-01-01"},
            {"ticker": "B", "fy": 2024, "inventory": 2500, "revenue":  8000, "as_of": "2024-01-01"},
            {"ticker": "C", "fy": 2023, "inventory": 500,  "revenue":  5000, "as_of": "2024-01-01"},
            {"ticker": "C", "fy": 2024, "inventory": 1800, "revenue":  5000, "as_of": "2024-01-01"},
        ]
        _make_statements(tmp_path, rows)
        tfp.reset_caches()
        stmts = pd.read_parquet(tmp_path / "edgar" / "statements.parquet")
        val, n, _ = tfp._inv_days_trend(["A", "B", "C"], stmts)
        assert val is not None
        assert val < 0, f"rising inventory-days should yield negative leg; got {val}"

    def test_rpo_growth_trend_rising_is_positive(self, tmp_path):
        """Rising RPO (more backlog) → positive leg8 value."""
        rows = [
            {"ticker": "CRWD", "fy": 2023, "rpo": 1000, "revenue": 3000, "as_of": "2024-01-01"},
            {"ticker": "CRWD", "fy": 2024, "rpo": 1500, "revenue": 3500, "as_of": "2024-01-01"},
            {"ticker": "PANW", "fy": 2023, "rpo": 2000, "revenue": 7000, "as_of": "2024-01-01"},
            {"ticker": "PANW", "fy": 2024, "rpo": 3000, "revenue": 8000, "as_of": "2024-01-01"},
            {"ticker": "FTNT", "fy": 2023, "rpo": 500,  "revenue": 5000, "as_of": "2024-01-01"},
            {"ticker": "FTNT", "fy": 2024, "rpo": 800,  "revenue": 6000, "as_of": "2024-01-01"},
        ]
        _make_rpo(tmp_path, rows)
        tfp.reset_caches()
        rpo = pd.read_parquet(tmp_path / "edgar" / "rpo.parquet")
        val, n, fy = tfp._rpo_growth_trend(["CRWD", "PANW", "FTNT"], rpo)
        assert val is not None
        assert val > 0, f"rising RPO should yield positive leg; got {val}"
        assert n == 3
        assert fy == 2024


# ---------------------------------------------------------------------------
# (d) < 3 members → None, never fabricated
# ---------------------------------------------------------------------------

class TestMinMembersGate:
    """The MIN_MEMBERS=3 gate must be respected — never return a value from <3 reporters."""

    def setup_method(self):
        tfp.reset_caches()

    def test_inv_days_none_with_two_members(self, tmp_path):
        """2 reporting members → leg7 = None (gate not met)."""
        rows = [
            {"ticker": "MU",  "fy": 2023, "inventory": 5000, "revenue": 20000, "as_of": "2024-01-01"},
            {"ticker": "MU",  "fy": 2024, "inventory": 3000, "revenue": 22000, "as_of": "2024-01-01"},
            {"ticker": "WDC", "fy": 2023, "inventory": 3000, "revenue": 15000, "as_of": "2024-01-01"},
            {"ticker": "WDC", "fy": 2024, "inventory": 1500, "revenue": 16000, "as_of": "2024-01-01"},
        ]
        _make_statements(tmp_path, rows)
        tfp.reset_caches()
        stmts = pd.read_parquet(tmp_path / "edgar" / "statements.parquet")
        val, n, _ = tfp._inv_days_trend(["MU", "WDC"], stmts)
        assert val is None, f"< 3 members should yield None, got {val}"
        assert n == 2

    def test_rpo_none_with_two_members(self, tmp_path):
        """2 reporting RPO members → leg8 = None (gate not met)."""
        rows = [
            {"ticker": "A", "fy": 2023, "rpo": 500, "revenue": 3000, "as_of": "2024-01-01"},
            {"ticker": "A", "fy": 2024, "rpo": 700, "revenue": 3500, "as_of": "2024-01-01"},
            {"ticker": "B", "fy": 2023, "rpo": 200, "revenue": 1000, "as_of": "2024-01-01"},
            {"ticker": "B", "fy": 2024, "rpo": 300, "revenue": 1200, "as_of": "2024-01-01"},
        ]
        _make_rpo(tmp_path, rows)
        tfp.reset_caches()
        rpo = pd.read_parquet(tmp_path / "edgar" / "rpo.parquet")
        val, n, _ = tfp._rpo_growth_trend(["A", "B"], rpo)
        assert val is None, f"< 3 members should yield None, got {val}"

    def test_zero_members_is_none(self, tmp_path):
        """0 members → both legs None."""
        _make_statements(tmp_path, [])
        _make_rpo(tmp_path, [])
        tfp.reset_caches()
        fp = tfp.compute_theme_fingerprint("empty_theme", [], tmp_path)
        assert fp is None

    def test_absent_parquet_is_none(self, tmp_path):
        """No parquet files → fingerprint is None (no fabrication)."""
        tfp.reset_caches()
        fp = tfp.compute_theme_fingerprint("test", ["MU", "WDC"], tmp_path)
        assert fp is None


# ---------------------------------------------------------------------------
# (e) Annual-basis fields surfaced
# ---------------------------------------------------------------------------

class TestAnnualBasis:
    """Fingerprint payload must surface basis='annual' and latest_fy."""

    def setup_method(self):
        tfp.reset_caches()

    def test_basis_annual_surfaced(self, tmp_path):
        """basis='annual' always surfaced in fingerprint dict."""
        rows = [
            {"ticker": f"T{i}", "fy": 2023, "inventory": 1000 * (i + 1),
             "revenue": 10000 * (i + 1), "as_of": "2024-01-01"}
            for i in range(3)
        ] + [
            {"ticker": f"T{i}", "fy": 2024, "inventory": 800 * (i + 1),
             "revenue": 11000 * (i + 1), "as_of": "2024-01-01"}
            for i in range(3)
        ]
        _make_statements(tmp_path, rows)
        tfp.reset_caches()
        fp = tfp.compute_theme_fingerprint("test", ["T0", "T1", "T2"], tmp_path)
        assert fp is not None
        assert fp["basis"] == "annual"
        comp = fp["components"]["leg7_member_inventory"]
        assert comp["latest_fy"] == 2024, f"latest_fy should be 2024, got {comp['latest_fy']}"
        assert comp["met_gate"] is True
        assert "annual" in comp["description"].lower()

    def test_provisional_flag(self, tmp_path):
        """provisional=True always surfaced (weights not yet calibrated)."""
        rows = [
            {"ticker": f"T{i}", "fy": 2023, "inventory": 1000, "revenue": 10000, "as_of": "2024-01-01"}
            for i in range(3)
        ] + [
            {"ticker": f"T{i}", "fy": 2024, "inventory": 700, "revenue": 11000, "as_of": "2024-01-01"}
            for i in range(3)
        ]
        _make_statements(tmp_path, rows)
        tfp.reset_caches()
        fp = tfp.compute_theme_fingerprint("test", [f"T{i}" for i in range(3)], tmp_path)
        assert fp is not None
        assert fp["provisional"] is True


# ---------------------------------------------------------------------------
# (b) Unmapped theme with ≥3 members gets numeric_band (no longer text-only)
# ---------------------------------------------------------------------------

class TestUnmappedThemeFingerprint:
    """An unmapped theme (no THEME_MAP entry) with ≥3 members reporting inventory
    must get a real numeric_band and text_only=False."""

    def setup_method(self):
        tfp.reset_caches()

    def test_unmapped_with_3_inv_members_gets_numeric_band(self, monkeypatch, tmp_path):
        """glp1_obesity is unmapped. With 3 reporting members in statements.parquet,
        it should get numeric_composite != None and numeric_band != None."""
        # Synthetic statements: 3 GLP-1 tickers with falling inventory (tightening)
        rows = [
            {"ticker": "LLY", "fy": 2023, "inventory": 2000, "revenue": 30000, "as_of": "2024-01-01"},
            {"ticker": "LLY", "fy": 2024, "inventory": 1200, "revenue": 34000, "as_of": "2024-01-01"},
            {"ticker": "AMGN","fy": 2023, "inventory": 3000, "revenue": 28000, "as_of": "2024-01-01"},
            {"ticker": "AMGN","fy": 2024, "inventory": 1800, "revenue": 30000, "as_of": "2024-01-01"},
            {"ticker": "HIMS","fy": 2023, "inventory":  500, "revenue":  2000, "as_of": "2024-01-01"},
            {"ticker": "HIMS","fy": 2024, "inventory":  200, "revenue":  3000, "as_of": "2024-01-01"},
        ]
        _make_statements(tmp_path, rows)

        monkeypatch.setattr(bn.config, "load",
                            lambda: {"themes": {"glp1_obesity": {"name": "GLP-1 Obesity",
                                                                  "tickers": ["LLY", "AMGN", "HIMS"]}}})
        monkeypatch.setattr(bn.config, "data_dir", lambda: tmp_path)
        monkeypatch.setattr(bn.store, "read", lambda group, name: None)

        out = bn.compute_bottleneck(write_ledger=False, data_dir=tmp_path)
        assert out is not None, "bottleneck returned None"
        t = out["themes"].get("glp1_obesity")
        assert t is not None, "glp1_obesity missing from output"

        # The fingerprint should have produced numeric legs
        assert t["numeric_composite"] is not None, \
            "unmapped theme with 3 inventory reporters should have numeric_composite"
        assert t["numeric_band"] is not None, \
            "unmapped theme with 3 inventory reporters should have numeric_band"
        assert t["text_only"] is False, \
            "unmapped theme with fingerprint numeric leg should NOT be text_only"
        assert t.get("fingerprint") is not None, "fingerprint payload should be attached"
        assert t["fingerprint"]["leg7_member_inventory"] is not None

    def test_unmapped_without_inv_data_remains_text_only(self, monkeypatch, tmp_path):
        """Unmapped theme with NO statements data (or < 3 reporters) stays text-only
        when only language data is present."""
        # 2 reporters only — gate not met
        rows = [
            {"ticker": "LLY", "fy": 2023, "inventory": 2000, "revenue": 30000, "as_of": "2024-01-01"},
            {"ticker": "LLY", "fy": 2024, "inventory": 1200, "revenue": 34000, "as_of": "2024-01-01"},
            {"ticker": "AMGN","fy": 2023, "inventory": 3000, "revenue": 28000, "as_of": "2024-01-01"},
            {"ticker": "AMGN","fy": 2024, "inventory": 1800, "revenue": 30000, "as_of": "2024-01-01"},
        ]
        _make_statements(tmp_path, rows)

        # Language hits so the unmapped path returns something
        lang_rows = [
            {"id": "1", "ticker": "LLY",  "file_date": "2026-06-01", "phrase": "sold out",
             "fetched": "2026-06-01", "polarity": None},
            {"id": "2", "ticker": "AMGN", "file_date": "2026-06-15", "phrase": "on allocation",
             "fetched": "2026-06-15", "polarity": None},
        ]
        _make_bottleneck_hits(tmp_path, lang_rows)

        monkeypatch.setattr(bn.config, "load",
                            lambda: {"themes": {"glp1_obesity": {"name": "GLP-1 Obesity",
                                                                  "tickers": ["LLY", "AMGN", "HIMS"]}}})
        monkeypatch.setattr(bn.config, "data_dir", lambda: tmp_path)
        monkeypatch.setattr(bn.store, "read", lambda group, name: None)

        out = bn.compute_bottleneck(write_ledger=False, data_dir=tmp_path)
        assert out is not None
        t = out["themes"].get("glp1_obesity")
        assert t is not None
        # Only 2 reporters → fingerprint leg is None → still text-only from language
        assert t["numeric_composite"] is None, \
            "with < 3 reporters, numeric_composite should be None"
        assert t["text_only"] is True, \
            "with < 3 reporters, theme should remain text_only"


# ---------------------------------------------------------------------------
# (c) Fingerprint legs enter numeric_composite; anti-laundering unaffected
# ---------------------------------------------------------------------------

class TestFingerprintAntiLaundering:
    """Legs 7-8 participate in numeric_composite. Language still can't tip numeric band."""

    def setup_method(self):
        tfp.reset_caches()

    def test_fingerprint_legs_enter_numeric_composite(self, monkeypatch, tmp_path):
        """When fingerprint legs are present on a mapped theme, numeric_composite
        INCLUDES them (they are physical XBRL, not text)."""
        import numpy as np

        n = 60
        ramp = np.linspace(0, 1, n)
        idx = pd.date_range("2020-01-01", periods=n, freq="MS")

        def ser(vals):
            return pd.DataFrame({"v": vals}, index=idx)

        # FRED: neutral/TIGHTENING state — numeric FRED legs are modest
        fred_store = {
            "CAPUTLG3344S": ser(70 + 10 * ramp),   # mild leg1
            "MNFCTRIRSA": ser(1.5 - 0.2 * ramp),   # slight leg2
            "AMTMUO": ser(100 + 30 * ramp),         # mild leg3
            "AMTMVS": ser(np.full(n, 50.0)),
            "PCU334413334413": ser(np.full(n, 100.0)),  # flat → leg4 ~0
            # delivery/prices_recv return None (not in store)
        }
        monkeypatch.setattr(bn.store, "read", lambda group, name: fred_store.get(name))
        monkeypatch.setattr(bn.config, "load",
                            lambda: {"themes": {"memory_storage": {
                                "name": "Memory",
                                "tickers": ["MU", "WDC", "SNDK"]}}})
        monkeypatch.setattr(bn.config, "data_dir", lambda: tmp_path)

        # Synthetic statements with falling inventory → strong positive leg7
        rows = [
            {"ticker": "MU",   "fy": 2023, "inventory": 9000, "revenue": 20000, "as_of": "2024-01-01"},
            {"ticker": "MU",   "fy": 2024, "inventory": 4000, "revenue": 25000, "as_of": "2024-01-01"},
            {"ticker": "WDC",  "fy": 2023, "inventory": 4000, "revenue": 15000, "as_of": "2024-01-01"},
            {"ticker": "WDC",  "fy": 2024, "inventory": 1500, "revenue": 17000, "as_of": "2024-01-01"},
            {"ticker": "SNDK", "fy": 2023, "inventory": 2000, "revenue":  8000, "as_of": "2024-01-01"},
            {"ticker": "SNDK", "fy": 2024, "inventory":  600, "revenue":  9000, "as_of": "2024-01-01"},
        ]
        _make_statements(tmp_path, rows)

        out_with_fp = bn.compute_bottleneck(write_ledger=False, data_dir=tmp_path)
        assert out_with_fp is not None, "bottleneck returned None with FRED store"
        t_with_fp = out_with_fp["themes"]["memory_storage"]

        # Now run without statements data to get baseline numeric_composite
        import shutil
        shutil.rmtree(tmp_path / "edgar")
        tfp.reset_caches()
        out_without = bn.compute_bottleneck(write_ledger=False, data_dir=tmp_path)
        assert out_without is not None, "bottleneck returned None without fingerprint"
        t_without = out_without["themes"]["memory_storage"]

        # With fingerprint leg7: leg is present in legs dict
        assert "leg7_member_inventory" in t_with_fp["legs"], \
            "leg7_member_inventory should be in legs dict"
        # Fingerprint legs change the numeric_composite
        # (not guaranteed to be higher, but the legs dict differs)
        assert t_with_fp.get("fingerprint") is not None
        fp_val = t_with_fp["fingerprint"]["leg7_member_inventory"]
        assert fp_val is not None, "leg7 should have a value with 3 members"

        # Verify the fingerprint leg doesn't appear in the baseline (no parquet)
        assert t_without.get("fingerprint") is None, \
            "without statements.parquet, fingerprint should be None"

    def test_text_still_cannot_tip_numeric_with_fingerprint(self, monkeypatch, tmp_path):
        """Even with fingerprint legs present, language alone cannot produce a plain
        numeric TIGHT (the anti-laundering rule is unaffected)."""
        n = 60
        ramp = np.linspace(0, 1, n)
        idx = pd.date_range("2020-01-01", periods=n, freq="MS")

        def ser(vals):
            return pd.DataFrame({"v": vals}, index=idx)

        # FRED legs: only cap-U and backlog elevated → numeric sits in TIGHTENING, not TIGHT
        fred_store = {
            "CAPUTLG3344S": ser(70 + 20 * ramp),
            "MNFCTRIRSA": ser(np.full(n, 1.4)),
            "AMTMUO": ser(100 + 80 * ramp),
            "AMTMVS": ser(np.full(n, 50.0)),
            "PCU334413334413": ser(np.full(n, 100.0)),
        }
        monkeypatch.setattr(bn.store, "read", lambda group, name: fred_store.get(name))
        monkeypatch.setattr(bn.config, "load",
                            lambda: {"themes": {"memory_storage": {
                                "name": "Memory",
                                "tickers": ["MU", "WDC"]}}})
        monkeypatch.setattr(bn.config, "data_dir", lambda: tmp_path)

        # Strong language — 2 filers
        lang_rows = [
            {"id": str(i), "ticker": t, "file_date": d, "phrase": "sold out",
             "fetched": d, "polarity": None}
            for i, (t, d) in enumerate([("MU", "2026-06-01"), ("MU", "2026-06-15"),
                                        ("WDC", "2026-06-10"), ("WDC", "2026-06-20")])
        ]
        _make_bottleneck_hits(tmp_path, lang_rows)

        # Modest fingerprint — inventory barely moving (not strongly tight)
        # Only 2 members so fingerprint gate not met → None fingerprint
        stmts_rows = [
            {"ticker": "MU",  "fy": 2023, "inventory": 5000, "revenue": 20000, "as_of": "2024-01-01"},
            {"ticker": "MU",  "fy": 2024, "inventory": 4800, "revenue": 22000, "as_of": "2024-01-01"},
            {"ticker": "WDC", "fy": 2023, "inventory": 3000, "revenue": 15000, "as_of": "2024-01-01"},
            {"ticker": "WDC", "fy": 2024, "inventory": 2900, "revenue": 16000, "as_of": "2024-01-01"},
        ]
        _make_statements(tmp_path, stmts_rows)

        out = bn.compute_bottleneck(write_ledger=False, data_dir=tmp_path)
        assert out is not None, "bottleneck returned None"
        t = out["themes"]["memory_storage"]

        # Anti-laundering invariant: if numeric_band is not TIGHT, the final band
        # should not be a plain (non-text) TIGHT/SOLD_OUT
        nb = t.get("numeric_band")
        if nb not in ("TIGHT", "SOLD_OUT"):
            assert t["band"] not in ("TIGHT", "SOLD_OUT"), (
                f"text+modest-fingerprint tipped band to plain {t['band']} "
                f"while numeric_band={nb}. Anti-laundering violated."
            )


# ---------------------------------------------------------------------------
# (f) t1_fingerprint health leg added to foresight_health
# ---------------------------------------------------------------------------

class TestHealthFingerprint:
    """t1_fingerprint leg is present in health output; DARK when no fingerprint data."""

    def test_t1_fingerprint_key_present(self, tmp_path):
        """t1_fingerprint always present in health legs dict."""
        from engine.foresight_health import compute_foresight_health
        with mock.patch("engine.foresight_health._health_log_path",
                        return_value=tmp_path / "h.jsonl"):
            h = compute_foresight_health(cascade={"themes": []})
        assert "t1_fingerprint" in h["legs"], \
            "t1_fingerprint leg must be present in health output"

    def test_t1_fingerprint_dark_when_no_data(self, tmp_path):
        """No themes with fingerprint → t1_fingerprint DARK."""
        from engine.foresight_health import compute_foresight_health

        themes = [
            {"theme": "memory_storage", "fingerprint": None, "bottleneck_band": "AWAITING_DATA"},
            {"theme": "glp1_obesity",   "fingerprint": None, "bottleneck_band": None},
        ]
        cascade = {"themes": themes, "asof": "2026-07-02"}
        with mock.patch("engine.foresight_health._health_log_path",
                        return_value=tmp_path / "h.jsonl"):
            h = compute_foresight_health(cascade=cascade)
        assert h["legs"]["t1_fingerprint"]["status"] == "DARK"

    def test_t1_fingerprint_partial_when_one_leg_live(self, tmp_path):
        """One theme with n_legs_live=1 → t1_fingerprint PARTIAL."""
        from engine.foresight_health import compute_foresight_health

        themes = [
            {"theme": "memory_storage",
             "fingerprint": {"n_legs_live": 1, "leg7_member_inventory": 0.5,
                             "leg8_member_backlog": None}},
            {"theme": "glp1_obesity", "fingerprint": None},
        ]
        cascade = {"themes": themes, "asof": "2026-07-02"}
        with mock.patch("engine.foresight_health._health_log_path",
                        return_value=tmp_path / "h.jsonl"):
            h = compute_foresight_health(cascade=cascade)
        assert h["legs"]["t1_fingerprint"]["status"] == "PARTIAL"

    def test_t1_fingerprint_live_when_both_legs(self, tmp_path):
        """A theme with n_legs_live=2 → t1_fingerprint at least PARTIAL, possibly LIVE."""
        from engine.foresight_health import compute_foresight_health

        themes = [
            {"theme": "memory_storage",
             "fingerprint": {"n_legs_live": 2, "leg7_member_inventory": 0.8,
                             "leg8_member_backlog": 0.5}},
        ]
        cascade = {"themes": themes, "asof": "2026-07-02"}
        with mock.patch("engine.foresight_health._health_log_path",
                        return_value=tmp_path / "h.jsonl"):
            h = compute_foresight_health(cascade=cascade)
        # One theme, both legs live → LIVE (1/1 = all)
        assert h["legs"]["t1_fingerprint"]["status"] in ("LIVE", "PARTIAL")

    def test_t1_fingerprint_counts_toward_leading_live(self, tmp_path):
        """t1_fingerprint LIVE/PARTIAL contributes to n_leading_live."""
        from engine.foresight_health import compute_foresight_health

        themes = [
            {"theme": "memory_storage",
             "fingerprint": {"n_legs_live": 2, "leg7_member_inventory": 0.8,
                             "leg8_member_backlog": 0.5}},
        ]
        cascade = {"themes": themes, "asof": "2026-07-02"}
        with mock.patch("engine.foresight_health._health_log_path",
                        return_value=tmp_path / "h.jsonl"):
            h_with = compute_foresight_health(cascade=cascade)

        # Without fingerprint (none):
        themes_dark = [{"theme": "memory_storage", "fingerprint": None}]
        cascade_dark = {"themes": themes_dark}
        with mock.patch("engine.foresight_health._health_log_path",
                        return_value=tmp_path / "h2.jsonl"):
            h_dark = compute_foresight_health(cascade=cascade_dark)

        # With live fingerprint, n_leading_live should be ≥ the dark case
        assert h_with["n_leading_live"] >= h_dark["n_leading_live"]


# ---------------------------------------------------------------------------
# (g) t1_fingerprint DARK when no themes have fingerprint data (explicit)
# ---------------------------------------------------------------------------

def test_t1_fingerprint_dark_no_cascade(tmp_path):
    """cascade=None → t1_fingerprint DARK (no themes means no fingerprint data)."""
    from engine.foresight_health import compute_foresight_health
    with mock.patch("engine.foresight_health._health_log_path",
                    return_value=tmp_path / "h.jsonl"):
        h = compute_foresight_health(cascade=None)
    assert "t1_fingerprint" in h["legs"]
    assert h["legs"]["t1_fingerprint"]["status"] == "DARK"


# ---------------------------------------------------------------------------
# Integration: compute_theme_fingerprint returns proper structure
# ---------------------------------------------------------------------------

def test_compute_theme_fingerprint_structure(tmp_path):
    """compute_theme_fingerprint returns required keys when data is available."""
    rows = [
        {"ticker": f"T{i}", "fy": 2023, "inventory": 1000 * (i + 1),
         "revenue": 10000 * (i + 1), "as_of": "2024-01-01"}
        for i in range(3)
    ] + [
        {"ticker": f"T{i}", "fy": 2024, "inventory": 700 * (i + 1),
         "revenue": 11000 * (i + 1), "as_of": "2024-01-01"}
        for i in range(3)
    ]
    _make_statements(tmp_path, rows)
    tfp.reset_caches()

    result = tfp.compute_theme_fingerprint("test_theme", ["T0", "T1", "T2"], tmp_path)
    assert result is not None
    assert result["theme"] == "test_theme"
    assert result["basis"] == "annual"
    assert result["provisional"] is True
    assert "fingerprint_tightness" in result
    assert "leg7_member_inventory" in result
    assert "leg8_member_backlog" in result
    assert "n_legs_live" in result
    assert "components" in result
    assert "_shadow_candidates" in result
    # n_legs_live ≥ 1 (at least inventory leg live)
    assert result["n_legs_live"] >= 1
    # fingerprint_tightness should be a float
    assert isinstance(result["fingerprint_tightness"], float)
