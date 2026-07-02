"""Wave 2b tests for engine.demand_capex — per-tier lag, per-name divergence,
RPO supplier confirmer, sign honesty, and cascade-compat output-contract regression.
"""
from __future__ import annotations

import pytest

import engine.demand_capex as dx
from engine import demand_chain as dc


# ── Shared fixtures ────────────────────────────────────────────────────────────

# A pool signal with 4 years of data (2022=100B → 2025=300B, trend accelerating).
# All tiers share this CURRENT read; tier lag is metadata only (transmission_lag_q).
RICH_SIG_SERIES = [[2022, 100.0], [2023, 120.0], [2024, 200.0], [2025, 300.0]]
RICH_SIG = {
    "ai_datacenter": {
        "yoy_pct": 50.0,
        "yoy_prev_pct": 66.7,
        "trend": "accelerating",
        "total_latest_bn": 300.0,
        "fy_latest": 2025,
        "spenders": ["MSFT", "GOOGL", "AMZN", "META", "ORCL"],
        "series": RICH_SIG_SERIES,
    }
}

# A short signal with only 2 data points — can't shift lagged or indirect
SHORT_SIG = {
    "ai_datacenter": {
        "yoy_pct": 69.0,
        "yoy_prev_pct": None,
        "trend": "peaking",
        "total_latest_bn": 378.7,
        "fy_latest": 2025,
        "spenders": ["MSFT", "GOOGL", "AMZN", "META"],
        "series": [[2024, 270.0], [2025, 378.7]],
    }
}

MINIMAL_THEMES = {
    "memory_storage": {"name": "Memory"},
    "ai_semiconductors": {"name": "AI Semis"},
    "semicap_equipment": {"name": "WFE"},
    "data_center_power": {"name": "DC Power"},
    "grid_electrification": {"name": "Grid"},
    "nuclear_power": {"name": "Nuclear"},
}


def _patch(monkeypatch, sig=None, themes=None, membership=None, revisions=None, rpo=None,
           track_record=None):
    """Centralised monkeypatch for all demand_capex dependencies."""
    monkeypatch.setattr(dx, "_statements", lambda: object())  # non-None sentinel
    monkeypatch.setattr(dc, "compute_signals", lambda df: sig if sig is not None else RICH_SIG)
    monkeypatch.setattr(dx.config, "load", lambda: {"themes": themes or MINIMAL_THEMES})
    monkeypatch.setattr(dx, "_membership_map", lambda: membership if membership is not None else {
        "memory_storage": ["MU", "WDC", "STX", "SNDK"],
        "ai_semiconductors": ["NVDA", "AVGO", "AMD"],
        "semicap_equipment": ["AMAT", "LRCX", "KLAC"],
        "data_center_power": ["VRT", "ETN", "POWL"],
        "grid_electrification": [],
        "nuclear_power": ["CEG", "VST", "TLN", "NRG", "BWXT"],
    })
    monkeypatch.setattr(dx, "_revisions_map", lambda: revisions if revisions is not None else {})
    monkeypatch.setattr(dx, "_rpo_cache", lambda: rpo if rpo is not None else {})
    monkeypatch.setattr(dx, "_chain_track_record", lambda: track_record)


# ── (a) One current band for all tiers; lag is METADATA, never a band shift ───

class TestPerTierLag:
    """Review-corrected semantics: every tier shares ONE current pool band; the tier
    transmission lag (~quarters) is metadata (transmission_lag_q + lag_note). The old
    annual-shift approach re-read the 2023 capex dip as the power themes' CURRENT
    demand — the exact inverse of the truth — and was review-rejected."""

    def test_all_tiers_share_current_band(self, monkeypatch):
        _patch(monkeypatch, sig=RICH_SIG)
        out = dx.compute_demand_capex()
        bands = {v["demand_band"] for v in out["themes"].values()}
        assert bands == {"ACCELERATING"}, (
            f"All tiers must share the CURRENT pool band; got {bands}"
        )

    def test_transmission_lag_metadata_by_tier(self, monkeypatch):
        _patch(monkeypatch, sig=RICH_SIG)
        out = dx.compute_demand_capex()
        assert out["themes"]["memory_storage"]["transmission_lag_q"] == 0      # direct
        assert out["themes"]["semicap_equipment"]["transmission_lag_q"] == 1   # lagged
        assert out["themes"]["data_center_power"]["transmission_lag_q"] == 2   # indirect
        assert "lag" in out["themes"]["data_center_power"]["lag_note"]

    def test_no_inverted_read_regression(self, monkeypatch):
        """REGRESSION GUARD (review blocker): a strongly positive current pool
        (capex_yoy > 0) must NEVER coexist with a CONTRACTING band on any tier —
        the inverted-read class where 2-year-stale data was reported as current."""
        _patch(monkeypatch, sig=RICH_SIG)
        out = dx.compute_demand_capex()
        for theme, v in out["themes"].items():
            if (v.get("capex_yoy") or 0) > 0:
                assert v["demand_band"] != "CONTRACTING", (
                    f"{theme}: CONTRACTING band next to capex_yoy="
                    f"{v['capex_yoy']} — inverted read"
                )


# ── (b) Short history degrades honestly (band always the real current read) ───

class TestShortHistory:
    """Short pool history changes nothing about the band (it is always the current
    read); lag metadata is static per tier."""

    def test_short_history_degrades_gracefully(self, monkeypatch):
        _patch(monkeypatch, sig=SHORT_SIG)
        out = dx.compute_demand_capex()
        assert out is not None

    def test_short_history_no_fabrication(self, monkeypatch):
        """The band is the real current read — never None, never a made-up value."""
        _patch(monkeypatch, sig=SHORT_SIG)
        out = dx.compute_demand_capex()
        for theme, v in out["themes"].items():
            assert v["demand_band"] in dx._BAND.values(), (
                f"{theme}: demand_band {v['demand_band']!r} is not a valid band string"
            )

    def test_short_history_lag_metadata_unaffected(self, monkeypatch):
        _patch(monkeypatch, sig=SHORT_SIG)
        out = dx.compute_demand_capex()
        assert out["themes"]["data_center_power"]["transmission_lag_q"] == 2


# ── (c) Divergence share with min-3 gate ──────────────────────────────────────

class TestDivergenceShare:
    """divergence_share = n_ahead / n_covered when n_covered >= 3, else None."""

    def _make_revs(self, tickers, breadth_val):
        """Create revisions dict — all tickers get the same breadth/drift."""
        return {t: {"breadth": breadth_val, "est_chg_30d": breadth_val * 3.0,
                    "est_chg_90d": breadth_val * 5.0}
                for t in tickers}

    def test_divergence_share_with_3_covered(self, monkeypatch):
        """3 covered members: 2 ahead → share = 2/3."""
        # Trend is "accelerating" (pool up). If consensus_dir = "flat", div = ahead_of_consensus.
        # If consensus_dir = "rising", div = aligned.
        # breadth=0.0 → score=0 → "flat" → divergence = ahead_of_consensus (pool up, cons flat)
        # breadth=0.9 → score=2 → "rising" → divergence = aligned
        revs = {
            "AMAT": {"breadth": 0.0, "est_chg_30d": 0.0, "est_chg_90d": 0.0},   # ahead
            "LRCX": {"breadth": 0.0, "est_chg_30d": 0.0, "est_chg_90d": 0.0},   # ahead
            "KLAC": {"breadth": 0.9, "est_chg_30d": 5.0, "est_chg_90d": 5.0},   # aligned
        }
        _patch(monkeypatch, sig=RICH_SIG, revisions=revs, membership={
            "memory_storage": [], "ai_semiconductors": [],
            "semicap_equipment": ["AMAT", "LRCX", "KLAC"],
            "data_center_power": [], "grid_electrification": [], "nuclear_power": [],
        })
        out = dx.compute_demand_capex()
        t = out["themes"]["semicap_equipment"]
        assert t["n_covered"] == 3
        assert t["n_ahead"] == 2
        assert t["divergence_share"] == pytest.approx(2 / 3, rel=1e-3)

    def test_divergence_share_none_below_min_3(self, monkeypatch):
        """Fewer than 3 covered → divergence_share is None."""
        revs = {
            "AMAT": {"breadth": 0.0, "est_chg_30d": 0.0, "est_chg_90d": 0.0},
            "LRCX": {"breadth": 0.0, "est_chg_30d": 0.0, "est_chg_90d": 0.0},
        }
        _patch(monkeypatch, sig=RICH_SIG, revisions=revs, membership={
            "memory_storage": [], "ai_semiconductors": [],
            "semicap_equipment": ["AMAT", "LRCX"],  # only 2 covered
            "data_center_power": [], "grid_electrification": [], "nuclear_power": [],
        })
        out = dx.compute_demand_capex()
        assert out["themes"]["semicap_equipment"]["divergence_share"] is None

    def test_divergence_share_none_when_no_revision_data(self, monkeypatch):
        """Members with no revision data are not counted as covered."""
        _patch(monkeypatch, sig=RICH_SIG, revisions={},  # no revisions for anyone
               membership={
                   "memory_storage": ["MU", "WDC", "STX"],
                   "ai_semiconductors": [], "semicap_equipment": [],
                   "data_center_power": [], "grid_electrification": [], "nuclear_power": [],
               })
        out = dx.compute_demand_capex()
        # No coverage → n_covered=0 → divergence_share=None
        t = out["themes"]["memory_storage"]
        assert t["n_covered"] == 0
        assert t["divergence_share"] is None

    def test_divergence_n_fields_present(self, monkeypatch):
        """n_ahead, n_at_risk, n_covered always present in output."""
        _patch(monkeypatch, sig=RICH_SIG)
        out = dx.compute_demand_capex()
        for theme, v in out["themes"].items():
            assert "n_ahead" in v, f"{theme} missing n_ahead"
            assert "n_at_risk" in v, f"{theme} missing n_at_risk"
            assert "n_covered" in v, f"{theme} missing n_covered"
            assert "divergence_share" in v, f"{theme} missing divergence_share"

    def test_divergence_reuses_demand_chain_function(self):
        """Verify the _divergence function in demand_chain is directly importable and
        is the same function used (not a copy) — import test."""
        from engine.demand_chain import _divergence
        # ahead_of_consensus: pool up, consensus flat
        assert _divergence("accelerating", "flat") == "ahead_of_consensus"
        # aligned: pool up, consensus rising
        assert _divergence("accelerating", "rising") == "aligned"
        # consensus_at_risk: pool contracting, consensus rising
        assert _divergence("contracting", "rising") == "consensus_at_risk"


# ── (d) RPO absent → None, no raise ──────────────────────────────────────────

class TestRPOConfirmer:
    """RPO supplier confirmer: None when cache is absent or members not in cache."""

    def test_rpo_absent_gives_none(self, monkeypatch):
        """Empty RPO cache → rpo_growth_yoy=None, rpo_n=0 — no raise."""
        _patch(monkeypatch, sig=RICH_SIG, rpo={})
        out = dx.compute_demand_capex()
        for theme, v in out["themes"].items():
            assert v["rpo_growth_yoy"] is None, f"{theme}: expected rpo_growth_yoy None"
            assert v["rpo_n"] == 0, f"{theme}: expected rpo_n 0"

    def test_rpo_members_not_in_cache_gives_none(self, monkeypatch):
        """Members not in RPO cache → None."""
        rpo = {"MSFT": [{"fy": 2024, "rpo": 100e9, "revenue": 200e9},
                        {"fy": 2025, "rpo": 120e9, "revenue": 250e9}]}
        _patch(monkeypatch, sig=RICH_SIG, rpo=rpo,
               membership={
                   "memory_storage": ["MU", "WDC"],   # not in RPO cache
                   "ai_semiconductors": [], "semicap_equipment": [],
                   "data_center_power": [], "grid_electrification": [], "nuclear_power": [],
               })
        out = dx.compute_demand_capex()
        # MU/WDC not in RPO cache → None
        assert out["themes"]["memory_storage"]["rpo_growth_yoy"] is None

    def test_rpo_computed_when_members_in_cache(self, monkeypatch):
        """When members are in the RPO cache with ≥2 years, rpo_growth_yoy is computed."""
        # NVDA: rpo 100→150 = +50%; AVGO: rpo 80→120 = +50%; AMD: rpo 50→80 = +60%
        # median of [50, 50, 60] = 50.0
        rpo = {
            "NVDA": [{"fy": 2024, "rpo": 100e9, "revenue": 200e9},
                     {"fy": 2025, "rpo": 150e9, "revenue": 250e9}],
            "AVGO": [{"fy": 2024, "rpo": 80e9, "revenue": 160e9},
                     {"fy": 2025, "rpo": 120e9, "revenue": 200e9}],
            "AMD": [{"fy": 2024, "rpo": 50e9, "revenue": 100e9},
                    {"fy": 2025, "rpo": 80e9, "revenue": 160e9}],
        }
        _patch(monkeypatch, sig=RICH_SIG, rpo=rpo, membership={
            "memory_storage": [], "semicap_equipment": [],
            "ai_semiconductors": ["NVDA", "AVGO", "AMD"],
            "data_center_power": [], "grid_electrification": [], "nuclear_power": [],
        })
        out = dx.compute_demand_capex()
        t = out["themes"]["ai_semiconductors"]
        assert t["rpo_n"] == 3
        assert t["rpo_growth_yoy"] == pytest.approx(50.0, rel=1e-2)

    def test_rpo_single_year_gives_none(self, monkeypatch):
        """Only one year in RPO cache → can't compute YoY → None."""
        rpo = {"NVDA": [{"fy": 2025, "rpo": 100e9, "revenue": 200e9}]}
        _patch(monkeypatch, sig=RICH_SIG, rpo=rpo, membership={
            "memory_storage": [], "semicap_equipment": [],
            "ai_semiconductors": ["NVDA"],
            "data_center_power": [], "grid_electrification": [], "nuclear_power": [],
        })
        out = dx.compute_demand_capex()
        assert out["themes"]["ai_semiconductors"]["rpo_growth_yoy"] is None


# ── (e) Output contract: cascade-compat regression ────────────────────────────

class TestOutputContract:
    """The cascade consumes the output via existing keys. These must never be
    renamed or removed; new keys may be added. Tests verify both old keys are
    present with correct types AND new W2b keys are present."""

    # Pre-existing top-level keys + types
    TOP_LEVEL_REQUIRED = {
        "asof": (str, type(None)),
        "source": str,
        "pool_bn": (float, int, type(None)),
        "pool_yoy": (float, int, type(None)),
        "pool_trend": (str, type(None)),
        "n_themes": int,
        "themes": dict,
        "note": str,
    }
    # Pre-existing per-theme keys + types
    THEME_REQUIRED = {
        "name": str,
        "demand_band": str,
        "strength": str,
        "capex_yoy": (float, int, type(None)),
        "capex_yoy_prev": (float, int, type(None)),
        "capex_trend": (str, type(None)),
        "total_latest_bn": (float, int, type(None)),
        "fy_latest": (int, type(None)),
        "customers": (list, type(None)),
    }
    # Wave 2b new per-theme keys + types
    W2B_THEME_KEYS = {
        "transmission_lag_q": int,
        "n_ahead": int,
        "n_at_risk": int,
        "n_covered": int,
        "divergence_share": (float, type(None)),
        "rpo_growth_yoy": (float, int, type(None)),
        "rpo_n": int,
    }
    # Wave 2b new top-level keys
    W2B_TOP_LEVEL = {
        "sign_note": str,
        "chain_track_record": (dict, type(None)),
    }

    def test_existing_top_level_keys_present(self, monkeypatch):
        _patch(monkeypatch, sig=RICH_SIG)
        out = dx.compute_demand_capex()
        for key, expected_type in self.TOP_LEVEL_REQUIRED.items():
            assert key in out, f"Missing top-level key: {key}"
            assert isinstance(out[key], expected_type), (
                f"Top-level key {key!r}: expected {expected_type}, got {type(out[key])}"
            )

    def test_existing_per_theme_keys_present(self, monkeypatch):
        _patch(monkeypatch, sig=RICH_SIG)
        out = dx.compute_demand_capex()
        for theme, v in out["themes"].items():
            for key, expected_type in self.THEME_REQUIRED.items():
                assert key in v, f"Theme {theme!r} missing key: {key}"
                assert isinstance(v[key], expected_type), (
                    f"Theme {theme!r} key {key!r}: expected {expected_type}, got {type(v[key])}"
                )

    def test_w2b_top_level_keys_present(self, monkeypatch):
        _patch(monkeypatch, sig=RICH_SIG, track_record={"schema": "test"})
        out = dx.compute_demand_capex()
        for key, expected_type in self.W2B_TOP_LEVEL.items():
            assert key in out, f"Missing W2b top-level key: {key}"
            assert isinstance(out[key], expected_type), (
                f"W2b top-level key {key!r}: expected {expected_type}, got {type(out[key])}"
            )

    def test_w2b_per_theme_keys_present(self, monkeypatch):
        _patch(monkeypatch, sig=RICH_SIG)
        out = dx.compute_demand_capex()
        for theme, v in out["themes"].items():
            for key, expected_type in self.W2B_THEME_KEYS.items():
                assert key in v, f"Theme {theme!r} missing W2b key: {key}"
                assert isinstance(v[key], expected_type), (
                    f"Theme {theme!r} W2b key {key!r}: expected {expected_type}, "
                    f"got {type(v[key])}"
                )

    def test_none_without_statements(self, monkeypatch):
        """Existing behaviour: None returned when statements are unavailable."""
        monkeypatch.setattr(dx, "_statements", lambda: None)
        assert dx.compute_demand_capex() is None

    def test_none_when_signal_empty(self, monkeypatch):
        """Existing behaviour: None returned when ai_datacenter signal is absent."""
        _patch(monkeypatch, sig={})
        assert dx.compute_demand_capex() is None

    def test_non_ai_theme_excluded(self, monkeypatch):
        """Existing behaviour: cybersecurity (not in AI_CAPEX_THEMES) excluded."""
        _patch(monkeypatch, sig=RICH_SIG, themes={
            **MINIMAL_THEMES, "cybersecurity": {"name": "Cyber"}
        })
        out = dx.compute_demand_capex()
        assert "cybersecurity" not in out["themes"]

    def test_demand_band_is_string_not_none(self, monkeypatch):
        """demand_band must be a string from _BAND values, never None."""
        _patch(monkeypatch, sig=RICH_SIG)
        out = dx.compute_demand_capex()
        valid_bands = set(dx._BAND.values())
        for theme, v in out["themes"].items():
            assert v["demand_band"] in valid_bands, (
                f"{theme}: demand_band {v['demand_band']!r} not in {valid_bands}"
            )

    def test_sign_note_mentions_cooper_gulen_schill(self, monkeypatch):
        """sign_note must acknowledge the Cooper-Gulen-Schill citation."""
        _patch(monkeypatch, sig=RICH_SIG)
        out = dx.compute_demand_capex()
        assert "Cooper" in out["sign_note"] or "Cooper-Gulen-Schill" in out["sign_note"]

    def test_sign_note_references_demand_ledger(self, monkeypatch):
        """sign_note must reference engine/demand_ledger.py as the validation vehicle."""
        _patch(monkeypatch, sig=RICH_SIG)
        out = dx.compute_demand_capex()
        assert "demand_ledger" in out["sign_note"]
