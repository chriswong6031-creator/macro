"""Tests for ALTDATA_REBOOT W2 — per-channel claim families, episode cooldown,
placebo determinism, attention short-direction, legacy regression.

Covers:
  * assign_claim_family: highest-weight channel routing, ties, unmapped channels.
  * Episode cooldown: same (ticker, family) blocked during cooldown window.
  * Placebo emission: is_placebo=True, placebo_path='altdata_matched', determinism.
  * Attention family: direction=-1 regardless of thesis lean.
  * Legacy regression: existing 'altdata'-family claims are untouched by new routing.
  * backfill_altdata: new-era theses emit 2 placebos; legacy theses emit none.
  * _load_placebo_universe: parquet load path (MAJOR-1).
  * _placebo_tickers stable under membership changes (MAJOR-2a).
  * emit-once guard prevents duplicate placebos (MAJOR-2b).
  * Fade check semantics graded correctly through desk_scorer (MINOR-1).
  * Per-(ticker, family) active dedup (MINOR-2).
  * 6 newly mapped channels (MINOR-3).
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from engine.altdata_ledger import (
    FAMILY_COOLDOWN_BD,
    FAMILY_DIRECTION_OVERRIDE,
    FAMILY_HORIZON_D,
    _cooldown_blocked,
    assign_claim_family,
)
from engine import qledger as q


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


# ---------------------------------------------------------------------------
# 1. assign_claim_family — highest-weight channel routing
# ---------------------------------------------------------------------------

class TestAssignClaimFamily:
    def test_insider_cluster_is_mid(self):
        # insider_cluster weight=1.00 — highest in mid family
        assert assign_claim_family(["insider_cluster"]) == "altdata_mid"

    def test_gov_contract_accel_is_event(self):
        # gov_contract_accel weight=0.90
        assert assign_claim_family(["gov_contract_accel"]) == "altdata_event"

    def test_special_situation_is_event(self):
        assert assign_claim_family(["special_situation"]) == "altdata_event"

    def test_material_8k_is_event(self):
        assert assign_claim_family(["material_8k"]) == "altdata_event"

    def test_darkpool_accum_is_flow(self):
        assert assign_claim_family(["darkpool_accum"]) == "altdata_flow"

    def test_unusual_options_is_flow(self):
        assert assign_claim_family(["unusual_options"]) == "altdata_flow"

    def test_congress_cluster_is_slow(self):
        # congress_cluster weight=0.80 → slow
        assert assign_claim_family(["congress_cluster"]) == "altdata_slow"

    def test_trump_is_slow(self):
        assert assign_claim_family(["trump"]) == "altdata_slow"

    def test_lobbying_is_slow(self):
        assert assign_claim_family(["lobbying"]) == "altdata_slow"

    def test_patent_cluster_is_slow(self):
        assert assign_claim_family(["patent_cluster"]) == "altdata_slow"

    def test_retail_buzz_is_attention(self):
        assert assign_claim_family(["retail_buzz"]) == "altdata_attention"

    def test_empty_channels_defaults_to_event(self):
        assert assign_claim_family([]) == "altdata_event"

    def test_highest_weight_wins_over_family_order(self):
        # special_situation (0.40, event) + insider_cluster (1.00, mid)
        # insider_cluster is higher weight → mid
        assert assign_claim_family(["special_situation", "insider_cluster"]) == "altdata_mid"

    def test_highest_weight_wins_event_over_slow(self):
        # fda_approval (0.80, event) + congress_cluster (0.80, slow) — tied weight;
        # first channel encountered in sorted order wins; we just verify it returns
        # one of the valid families (not unmapped).
        fam = assign_claim_family(["fda_approval", "congress_cluster"])
        assert fam in ("altdata_event", "altdata_slow")

    def test_cnbc_pick_routes_to_mid(self):
        # 'cnbc_pick' (weight=0.25) is now explicitly mapped to altdata_mid
        # (attention-adjacent but altdata_attention is dormant; mid-horizon safer)
        fam = assign_claim_family(["cnbc_pick"])
        assert fam == "altdata_mid"

    def test_genuinely_unmapped_routes_to_mid(self):
        # A truly unknown channel routes to altdata_mid (safe mid-horizon fallback)
        fam = assign_claim_family(["__totally_unknown_channel__"])
        assert fam == "altdata_mid"

    def test_mixed_with_retail_buzz_and_higher_channel(self):
        # special_situation (0.40) > retail_buzz (0.15) → event, not attention
        fam = assign_claim_family(["special_situation", "retail_buzz"])
        assert fam == "altdata_event"

    def test_sole_retail_buzz_is_attention(self):
        assert assign_claim_family(["retail_buzz"]) == "altdata_attention"


# ---------------------------------------------------------------------------
# 2. Family configuration constants
# ---------------------------------------------------------------------------

class TestFamilyConstants:
    def test_event_horizon_is_21(self):
        assert FAMILY_HORIZON_D["altdata_event"] == 21

    def test_flow_horizon_is_21(self):
        assert FAMILY_HORIZON_D["altdata_flow"] == 21

    def test_mid_horizon_is_63(self):
        assert FAMILY_HORIZON_D["altdata_mid"] == 63

    def test_slow_horizon_is_63(self):
        assert FAMILY_HORIZON_D["altdata_slow"] == 63

    def test_attention_horizon_is_5(self):
        assert FAMILY_HORIZON_D["altdata_attention"] == 5

    def test_attention_direction_override_is_minus_one(self):
        assert FAMILY_DIRECTION_OVERRIDE["altdata_attention"] == -1

    def test_other_families_have_no_direction_override(self):
        for fam in ("altdata_event", "altdata_flow", "altdata_mid", "altdata_slow"):
            assert FAMILY_DIRECTION_OVERRIDE.get(fam) is None

    def test_cooldown_equals_horizon_d(self):
        # The cooldown window equals the family's horizon_d (pre-registered rule).
        for fam, hd in FAMILY_HORIZON_D.items():
            assert FAMILY_COOLDOWN_BD[fam] == hd, f"cooldown mismatch for {fam}"


# ---------------------------------------------------------------------------
# 3. Episode cooldown
# ---------------------------------------------------------------------------

class TestEpisodeCooldown:
    def _make_thesis(self, ticker, family, check_by):
        return {
            "ticker": ticker,
            "claim_family": family,
            "check_by": check_by,
            "state_asof": "2026-06-01",
        }

    def test_expired_within_cooldown_blocks(self):
        # Family=altdata_event, cooldown=21 business days.
        # check_by=2026-06-01 + 21 bd ≈ 2026-07-01; asof=2026-06-15 (within cooldown).
        rows = [self._make_thesis("AAPL", "altdata_event", "2026-06-01")]
        blocked = _cooldown_blocked(rows, "2026-06-15")
        assert ("AAPL", "altdata_event") in blocked

    def test_expired_after_cooldown_not_blocked(self):
        # check_by=2026-01-01 → cooldown ends ~2026-02-01; asof=2026-06-01 → not blocked.
        rows = [self._make_thesis("AAPL", "altdata_event", "2026-01-01")]
        blocked = _cooldown_blocked(rows, "2026-06-01")
        assert ("AAPL", "altdata_event") not in blocked

    def test_open_thesis_not_in_cooldown(self):
        # check_by in the future → _active_subjects handles this; cooldown should not fire.
        rows = [self._make_thesis("AAPL", "altdata_event", "2026-12-31")]
        blocked = _cooldown_blocked(rows, "2026-07-12")
        # Not blocked by cooldown (window still open — handled by _active_subjects).
        assert ("AAPL", "altdata_event") not in blocked

    def test_different_ticker_not_blocked(self):
        rows = [self._make_thesis("AAPL", "altdata_event", "2026-06-01")]
        blocked = _cooldown_blocked(rows, "2026-06-15")
        # MSFT has no thesis → not blocked
        assert ("MSFT", "altdata_event") not in blocked

    def test_different_family_not_blocked(self):
        rows = [self._make_thesis("AAPL", "altdata_event", "2026-06-01")]
        blocked = _cooldown_blocked(rows, "2026-06-15")
        # Same ticker, different family → not blocked
        assert ("AAPL", "altdata_slow") not in blocked

    def test_empty_rows_no_blocks(self):
        assert _cooldown_blocked([], "2026-07-12") == set()


# ---------------------------------------------------------------------------
# 4. Placebo determinism (via backfill_altdata)
# ---------------------------------------------------------------------------

class TestPlacoboEmission:
    """Tests that placebo claims are emitted with correct flags and deterministically."""

    def _make_new_era_thesis(self, ticker="CARR", asof="2026-07-12"):
        return {
            "id": f"{asof}-{ticker}-altconv",
            "ticker": ticker,
            "state_asof": asof,
            "lean": "overweight",
            "conviction": "low",
            "horizon_d": 21,
            "claim_family": "altdata_event",
            "channels": ["special_situation"],
            "falsifier": {
                "text": f"{ticker} fails to beat SPY.",
                "check": {"kind": "rel_return", "subject_ticker": ticker,
                           "vs": "SPY", "op": "<", "threshold": -0.05, "horizon_d": 21},
            },
            "check_by": "2026-08-09",
            "entry_levels": {ticker: 100.0, "SPY": 700.0},
            "status": "open",
        }

    def test_new_era_thesis_emits_two_placebos(self, tmp_path):
        from scripts.backfill_qledger_us import backfill_altdata
        _write_jsonl(tmp_path / "data" / "altdata" / "theses.jsonl",
                     [self._make_new_era_thesis()])
        backfill_altdata(tmp_path)
        claims = q.load_claims(tmp_path)
        placebo_claims = [c for c in claims if c.get("is_placebo")]
        assert len(placebo_claims) == 2

    def test_placebos_have_correct_flags(self, tmp_path):
        from scripts.backfill_qledger_us import backfill_altdata
        _write_jsonl(tmp_path / "data" / "altdata" / "theses.jsonl",
                     [self._make_new_era_thesis()])
        backfill_altdata(tmp_path)
        claims = q.load_claims(tmp_path)
        placebos = [c for c in claims if c.get("is_placebo")]
        for p in placebos:
            assert p["is_placebo"] is True
            assert p.get("placebo_path") == "altdata_matched"

    def test_placebo_tickers_are_deterministic(self, tmp_path):
        from scripts.backfill_qledger_us import backfill_altdata, _placebo_tickers
        universe = ["AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA"]
        result1 = _placebo_tickers("2026-07-12", "CARR", "altdata_event",
                                   {"CARR"}, universe, n=2)
        result2 = _placebo_tickers("2026-07-12", "CARR", "altdata_event",
                                   {"CARR"}, universe, n=2)
        assert result1 == result2  # same seed → same result

    def test_placebo_tickers_exclude_real_ticker(self, tmp_path):
        from scripts.backfill_qledger_us import _placebo_tickers
        universe = ["AAPL", "MSFT", "CARR", "GOOGL", "META"]
        result = _placebo_tickers("2026-07-12", "CARR", "altdata_event",
                                  {"CARR"}, universe, n=2)
        assert "CARR" not in result

    def test_placebo_same_family_as_real(self, tmp_path):
        from scripts.backfill_qledger_us import backfill_altdata
        _write_jsonl(tmp_path / "data" / "altdata" / "theses.jsonl",
                     [self._make_new_era_thesis()])
        backfill_altdata(tmp_path)
        claims = q.load_claims(tmp_path)
        real = [c for c in claims if not c.get("is_placebo")]
        placebos = [c for c in claims if c.get("is_placebo")]
        assert real, "no real claim found"
        real_family = real[0].get("claim_family")
        for p in placebos:
            assert p.get("claim_family") == real_family

    def test_placebo_same_horizon_as_real(self, tmp_path):
        from scripts.backfill_qledger_us import backfill_altdata
        _write_jsonl(tmp_path / "data" / "altdata" / "theses.jsonl",
                     [self._make_new_era_thesis()])
        backfill_altdata(tmp_path)
        claims = q.load_claims(tmp_path)
        real = [c for c in claims if not c.get("is_placebo")]
        placebos = [c for c in claims if c.get("is_placebo")]
        assert real
        for p in placebos:
            assert p["horizon_d"] == real[0]["horizon_d"]

    def test_two_runs_idempotent(self, tmp_path):
        from scripts.backfill_qledger_us import backfill_altdata
        _write_jsonl(tmp_path / "data" / "altdata" / "theses.jsonl",
                     [self._make_new_era_thesis()])
        backfill_altdata(tmp_path)
        backfill_altdata(tmp_path)
        claims = q.load_claims(tmp_path)
        # 1 real + 2 placebo, no duplicates
        assert len(claims) == 3


# ---------------------------------------------------------------------------
# 5. Attention family — direction=-1 (reversion construction)
# ---------------------------------------------------------------------------

class TestAttentionFamily:
    def _make_attention_thesis(self, asof="2026-07-12"):
        return {
            "id": f"{asof}-WSB-altconv",
            "ticker": "GME",
            "state_asof": asof,
            "lean": "overweight",   # thesis lean is bullish ...
            "conviction": "low",
            "horizon_d": 5,
            "claim_family": "altdata_attention",  # ... but family overrides to -1
            "channels": ["retail_buzz"],
            "falsifier": {
                "text": "GME fails to beat SPY.",
                "check": {"kind": "rel_return", "subject_ticker": "GME",
                           "vs": "SPY", "op": "<", "threshold": -0.05, "horizon_d": 5},
            },
            "check_by": "2026-07-19",
            "entry_levels": {"GME": 25.0, "SPY": 700.0},
            "status": "open",
        }

    def test_attention_direction_is_minus_one_even_with_overweight_lean(self, tmp_path):
        from scripts.backfill_qledger_us import backfill_altdata
        _write_jsonl(tmp_path / "data" / "altdata" / "theses.jsonl",
                     [self._make_attention_thesis()])
        backfill_altdata(tmp_path)
        claims = q.load_claims(tmp_path)
        real = [c for c in claims if not c.get("is_placebo")]
        assert real, "no real claim found"
        assert real[0]["direction"] == -1, "attention must fade (direction=-1)"

    def test_attention_horizon_is_5(self, tmp_path):
        from scripts.backfill_qledger_us import backfill_altdata
        _write_jsonl(tmp_path / "data" / "altdata" / "theses.jsonl",
                     [self._make_attention_thesis()])
        backfill_altdata(tmp_path)
        claims = q.load_claims(tmp_path)
        real = [c for c in claims if not c.get("is_placebo")]
        assert real
        assert real[0]["horizon_d"] == 5

    def test_attention_claim_family_tag(self, tmp_path):
        from scripts.backfill_qledger_us import backfill_altdata
        _write_jsonl(tmp_path / "data" / "altdata" / "theses.jsonl",
                     [self._make_attention_thesis()])
        backfill_altdata(tmp_path)
        claims = q.load_claims(tmp_path)
        real = [c for c in claims if not c.get("is_placebo")]
        assert real
        assert real[0].get("claim_family") == "altdata_attention"


# ---------------------------------------------------------------------------
# 6. Legacy regression — existing 'altdata'-family claims are untouched
# ---------------------------------------------------------------------------

class TestLegacyRegression:
    def _make_legacy_thesis(self, asof="2026-06-19"):
        """A pre-activation thesis (no claim_family in source)."""
        return {
            "id": f"{asof}-CARR-altconv",
            "ticker": "CARR",
            "state_asof": asof,
            "lean": "overweight",
            "conviction": "low",
            "horizon_d": 63,
            # NOTE: no claim_family field (legacy)
            "channels": ["congress_buy"],
            "falsifier": {
                "text": "CARR fails to beat SPY.",
                "check": {"kind": "rel_return", "subject_ticker": "CARR",
                           "vs": "SPY", "op": "<", "threshold": -0.05, "horizon_d": 63},
            },
            "check_by": "2026-09-18",
            "entry_levels": {"CARR": 71.81, "SPY": 746.74},
            "status": "open",
        }

    def test_legacy_thesis_registers_as_altdata_family(self, tmp_path):
        from scripts.backfill_qledger_us import backfill_altdata
        _write_jsonl(tmp_path / "data" / "altdata" / "theses.jsonl",
                     [self._make_legacy_thesis()])
        backfill_altdata(tmp_path)
        claims = q.load_claims(tmp_path)
        real = [c for c in claims if not c.get("is_placebo")]
        assert real, "no claim registered"
        assert real[0].get("claim_family") == "altdata", (
            "legacy thesis must stay in 'altdata' family (no retro-tagging)"
        )

    def test_legacy_thesis_emits_no_placebos(self, tmp_path):
        from scripts.backfill_qledger_us import backfill_altdata
        _write_jsonl(tmp_path / "data" / "altdata" / "theses.jsonl",
                     [self._make_legacy_thesis()])
        backfill_altdata(tmp_path)
        claims = q.load_claims(tmp_path)
        placebos = [c for c in claims if c.get("is_placebo")]
        assert len(placebos) == 0, "legacy theses must not emit placebos"

    def test_legacy_claim_count_is_one(self, tmp_path):
        from scripts.backfill_qledger_us import backfill_altdata
        _write_jsonl(tmp_path / "data" / "altdata" / "theses.jsonl",
                     [self._make_legacy_thesis()])
        backfill_altdata(tmp_path)
        claims = q.load_claims(tmp_path)
        assert len(claims) == 1

    def test_legacy_horizon_d_preserved(self, tmp_path):
        from scripts.backfill_qledger_us import backfill_altdata
        _write_jsonl(tmp_path / "data" / "altdata" / "theses.jsonl",
                     [self._make_legacy_thesis()])
        backfill_altdata(tmp_path)
        claims = q.load_claims(tmp_path)
        real = [c for c in claims if not c.get("is_placebo")]
        assert real
        assert real[0]["horizon_d"] == 63, "legacy horizon_d must be preserved"


# ---------------------------------------------------------------------------
# 7. Mixed: legacy + new-era in same run
# ---------------------------------------------------------------------------

class TestMixedLegacyAndNewEra:
    def test_mixed_run_correct_totals(self, tmp_path):
        from scripts.backfill_qledger_us import backfill_altdata
        legacy = {
            "id": "2026-06-19-CARR-altconv",
            "ticker": "CARR",
            "state_asof": "2026-06-19",  # pre-activation
            "lean": "overweight",
            "horizon_d": 63,
            "channels": ["congress_buy"],
            "falsifier": {"text": "x", "check": {"kind": "rel_return"}},
            "check_by": "2026-09-18",
            "entry_levels": {"CARR": 71.81, "SPY": 746.74},
            "status": "open",
        }
        new_era = {
            "id": "2026-07-12-NVDA-altconv",
            "ticker": "NVDA",
            "state_asof": "2026-07-12",  # activation date
            "lean": "overweight",
            "horizon_d": 21,
            "claim_family": "altdata_event",
            "channels": ["material_8k"],
            "falsifier": {"text": "x", "check": {"kind": "rel_return"}},
            "check_by": "2026-08-09",
            "entry_levels": {"NVDA": 900.0, "SPY": 700.0},
            "status": "open",
        }
        _write_jsonl(tmp_path / "data" / "altdata" / "theses.jsonl", [legacy, new_era])
        backfill_altdata(tmp_path)
        claims = q.load_claims(tmp_path)
        real = [c for c in claims if not c.get("is_placebo")]
        placebos = [c for c in claims if c.get("is_placebo")]
        assert len(real) == 2     # one legacy + one new-era
        assert len(placebos) == 2  # only new-era emits 2 placebos

    def test_idempotent_mixed_run(self, tmp_path):
        from scripts.backfill_qledger_us import backfill_altdata
        legacy = {
            "id": "2026-06-19-CARR-altconv", "ticker": "CARR",
            "state_asof": "2026-06-19", "lean": "overweight", "horizon_d": 63,
            "channels": ["congress_buy"],
            "falsifier": {"text": "x", "check": {"kind": "rel_return"}},
            "check_by": "2026-09-18",
            "entry_levels": {"CARR": 71.81, "SPY": 746.74}, "status": "open",
        }
        new_era = {
            "id": "2026-07-12-NVDA-altconv", "ticker": "NVDA",
            "state_asof": "2026-07-12", "lean": "overweight", "horizon_d": 21,
            "claim_family": "altdata_event", "channels": ["material_8k"],
            "falsifier": {"text": "x", "check": {"kind": "rel_return"}},
            "check_by": "2026-08-09",
            "entry_levels": {"NVDA": 900.0, "SPY": 700.0}, "status": "open",
        }
        _write_jsonl(tmp_path / "data" / "altdata" / "theses.jsonl", [legacy, new_era])
        backfill_altdata(tmp_path)
        first_count = len(q.load_claims(tmp_path))
        backfill_altdata(tmp_path)
        assert len(q.load_claims(tmp_path)) == first_count


# ---------------------------------------------------------------------------
# 8. MAJOR-1: _load_placebo_universe parquet load path
# ---------------------------------------------------------------------------

class TestLoadPlaceboUniverse:
    """_load_placebo_universe must load from membership.parquet and select
    active sp500 members as the liquid subset."""

    def setup_method(self):
        import scripts.backfill_qledger_us as bq
        bq._PLACEBO_UNIVERSE = None

    def teardown_method(self):
        # Restore cache to None so later tests aren't affected by a small fixture universe.
        import scripts.backfill_qledger_us as bq
        bq._PLACEBO_UNIVERSE = None

    def _write_parquet(self, path: Path, rows: list[dict]) -> None:
        import pandas as pd
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_parquet(path, index=False)

    def test_loads_active_sp500_from_parquet(self, tmp_path):
        from scripts.backfill_qledger_us import _load_placebo_universe
        import scripts.backfill_qledger_us as bq
        # Reset module-level cache
        bq._PLACEBO_UNIVERSE = None

        rows = [
            {"ticker": "AAPL", "group": "sp500", "name": "Apple", "sector": "IT",
             "first_seen": "2026-01-01", "last_seen": "2026-07-12", "active": True},
            {"ticker": "MSFT", "group": "sp500", "name": "Microsoft", "sector": "IT",
             "first_seen": "2026-01-01", "last_seen": "2026-07-12", "active": True},
            # sp600 member — should be excluded (not sp500)
            {"ticker": "SMCAP", "group": "sp600", "name": "Small Co", "sector": "IT",
             "first_seen": "2026-01-01", "last_seen": "2026-07-12", "active": True},
            # inactive sp500 — should be excluded
            {"ticker": "OLD", "group": "sp500", "name": "Old Co", "sector": "IT",
             "first_seen": "2026-01-01", "last_seen": "2026-06-01", "active": False},
        ]
        self._write_parquet(tmp_path / "data" / "universe" / "membership.parquet", rows)
        universe = _load_placebo_universe(tmp_path)
        assert "AAPL" in universe
        assert "MSFT" in universe
        assert "SMCAP" not in universe, "sp600 must be excluded"
        assert "OLD" not in universe, "inactive must be excluded"

    def test_fallback_when_parquet_absent(self, tmp_path):
        from scripts.backfill_qledger_us import _load_placebo_universe, _PLACEBO_UNIVERSE_FALLBACK
        import scripts.backfill_qledger_us as bq
        bq._PLACEBO_UNIVERSE = None
        # No parquet file written
        universe = _load_placebo_universe(tmp_path)
        assert universe == _PLACEBO_UNIVERSE_FALLBACK

    def test_parquet_load_cached(self, tmp_path):
        """Second call returns same object (no re-read)."""
        from scripts.backfill_qledger_us import _load_placebo_universe
        import scripts.backfill_qledger_us as bq
        bq._PLACEBO_UNIVERSE = None
        rows = [
            {"ticker": "AAPL", "group": "sp500", "name": "Apple", "sector": "IT",
             "first_seen": "2026-01-01", "last_seen": "2026-07-12", "active": True},
        ]
        import pandas as pd
        (tmp_path / "data" / "universe").mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_parquet(tmp_path / "data" / "universe" / "membership.parquet", index=False)
        u1 = _load_placebo_universe(tmp_path)
        u2 = _load_placebo_universe(tmp_path)
        assert u1 is u2, "universe must be cached (same object on second call)"


# ---------------------------------------------------------------------------
# 9. MAJOR-2a: _placebo_tickers stable under membership changes
# ---------------------------------------------------------------------------

class TestPlaceboTickerStability:
    """Draw must be stable per (thesis, k) under unrelated membership changes."""

    def test_stable_under_unrelated_membership_addition(self):
        from scripts.backfill_qledger_us import _placebo_tickers
        universe_v1 = ["AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "JPM"]
        # v2 adds an unrelated ticker in the middle (alphabetically)
        universe_v2 = ["AAPL", "BNEW", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "JPM"]

        result_v1 = _placebo_tickers("2026-07-12", "CARR", "altdata_event", {"CARR"}, universe_v1, n=2)
        result_v2 = _placebo_tickers("2026-07-12", "CARR", "altdata_event", {"CARR"}, universe_v2, n=2)
        assert result_v1 == result_v2, (
            f"draw should be stable under membership addition: v1={result_v1} v2={result_v2}"
        )

    def test_stable_under_unrelated_membership_removal(self):
        from scripts.backfill_qledger_us import _placebo_tickers
        universe_full = ["AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "JPM", "UNH"]
        universe_minus = ["AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "UNH"]  # JPM removed

        result_full = _placebo_tickers("2026-07-12", "CARR", "altdata_event", {"CARR"}, universe_full, n=2)
        result_minus = _placebo_tickers("2026-07-12", "CARR", "altdata_event", {"CARR"}, universe_minus, n=2)
        # The removed ticker (JPM) shouldn't have been selected — if it wasn't, results should match
        if "JPM" not in result_full:
            assert result_full == result_minus, (
                f"removing an un-selected ticker should not change the draw: "
                f"full={result_full} minus={result_minus}"
            )


# ---------------------------------------------------------------------------
# 10. MAJOR-2b: emit-once guard — no duplicate placebos across nightly runs
# ---------------------------------------------------------------------------

class TestEmitOnceGuard:
    """Placebos for a thesis must never accumulate across runs."""

    def _make_new_era_thesis(self, ticker="CARR", source_id=None, asof="2026-07-12"):
        if source_id is None:
            source_id = f"{asof}-{ticker}-altconv"
        return {
            "id": source_id,
            "ticker": ticker,
            "state_asof": asof,
            "lean": "overweight",
            "conviction": "low",
            "horizon_d": 21,
            "claim_family": "altdata_event",
            "channels": ["special_situation"],
            "falsifier": {
                "text": f"{ticker} fails to beat SPY.",
                "check": {"kind": "rel_return", "subject_ticker": ticker,
                           "vs": "SPY", "op": "<", "threshold": -0.05, "horizon_d": 21},
            },
            "check_by": "2026-08-09",
            "entry_levels": {ticker: 100.0, "SPY": 700.0},
            "status": "open",
        }

    def _reset_universe_cache(self):
        import scripts.backfill_qledger_us as bq
        bq._PLACEBO_UNIVERSE = None

    def test_second_run_does_not_add_placebos(self, tmp_path):
        """After first run (3 claims: 1 real + 2 placebo), second run must not
        add more placebos — emit-once guard should detect existing placebos."""
        from scripts.backfill_qledger_us import backfill_altdata
        self._reset_universe_cache()
        _write_jsonl(tmp_path / "data" / "altdata" / "theses.jsonl",
                     [self._make_new_era_thesis()])
        backfill_altdata(tmp_path)
        first_total = len(q.load_claims(tmp_path))
        assert first_total == 3, f"expected 3 claims (1 real + 2 placebo), got {first_total}"

        self._reset_universe_cache()
        backfill_altdata(tmp_path)
        second_total = len(q.load_claims(tmp_path))
        assert second_total == 3, (
            f"emit-once guard failed: second run grew claims from {first_total} to {second_total}"
        )

    def test_ten_runs_idempotent_placebo_count(self, tmp_path):
        """Multiple runs must not accumulate placebos."""
        from scripts.backfill_qledger_us import backfill_altdata
        _write_jsonl(tmp_path / "data" / "altdata" / "theses.jsonl",
                     [self._make_new_era_thesis()])
        for _ in range(5):
            self._reset_universe_cache()
            backfill_altdata(tmp_path)
        claims = q.load_claims(tmp_path)
        placebos = [c for c in claims if c.get("is_placebo")]
        assert len(placebos) == 2, (
            f"emit-once guard: expected 2 placebos after 5 runs, got {len(placebos)}"
        )


# ---------------------------------------------------------------------------
# 11. MINOR-1: fade-check semantics graded correctly through desk_scorer
# ---------------------------------------------------------------------------

class TestFadeCheckSemantics:
    """The attention family emits op='>' with positive threshold.
    desk_scorer.eval_rel_return must grade a fade claim correctly:
      - If the stock FALLS vs SPY (realized < 0): fade is CORRECT → hit
        (realized NOT > +threshold → not falsified)
      - If the stock RISES vs SPY (realized > +threshold): fade is BROKEN → miss
        (realized > +threshold → falsified)
    """

    def test_fade_check_has_correct_op_and_threshold(self, tmp_path):
        """build_theses with attention family must emit op='>' with positive threshold."""
        from engine.altdata_ledger import build_theses, FAMILY_DIRECTION_OVERRIDE
        import scripts.backfill_qledger_us as bq
        bq._PLACEBO_UNIVERSE = None

        by_ticker = {
            "tickers": {
                "GME": {
                    "convergence_score": 2,
                    "channels": ["retail_buzz"],
                    "trump_linked": False,
                },
            }
        }

        import pandas as pd
        import unittest.mock as mock
        from engine import ai_desk as _desk
        from datetime import date

        # Patch price layer so the ticker is scorable
        def _fake_level(ticker, root, asof):
            return {"GME": 25.0, "SPY": 700.0}.get(ticker)

        with mock.patch.object(_desk, "_level_asof", side_effect=_fake_level):
            theses = build_theses(by_ticker, root=tmp_path, today=date(2026, 7, 12))

        assert theses, "expected at least one thesis for GME retail_buzz"
        thesis = theses[0]
        check = thesis["falsifier"]["check"]
        assert check["op"] == ">", (
            f"attention fade must emit op='>' not '{check['op']}'"
        )
        assert check["threshold"] > 0, (
            f"attention fade threshold must be positive (got {check['threshold']})"
        )

    def test_fade_check_grades_falling_stock_as_hit(self):
        """realized < 0 (stock fell vs SPY) → fade is correct → NOT falsified → hit."""
        from engine.desk_scorer import eval_rel_return
        import unittest.mock as mock
        from engine import ai_desk as _desk

        # Fade check: falsified if realized > +0.05
        check = {"kind": "rel_return", "subject_ticker": "GME", "vs": "SPY",
                 "op": ">", "threshold": 0.05}
        # GME drops 10%, SPY flat → realized = -0.10 → NOT > 0.05 → not falsified → hit
        def _fake_close(ticker, root, check_by):
            return {"GME": 22.5, "SPY": 700.0}[ticker]  # GME -10%

        with mock.patch("engine.desk_scorer.close_at", side_effect=_fake_close):
            with mock.patch("engine.desk_scorer.start_level",
                            side_effect=lambda t, e, r, a: {"GME": 25.0, "SPY": 700.0}.get(t)):
                result = eval_rel_return(
                    check,
                    entry={"GME": 25.0, "SPY": 700.0},
                    root=None,
                    asof="2026-07-12",
                    check_by="2026-07-19",
                )
        assert result is not None
        assert result["outcome"] == "hit", (
            f"fade: falling stock should be a hit, got '{result['outcome']}'"
        )

    def test_fade_check_grades_rising_stock_as_miss(self):
        """realized > +threshold (stock rose vs SPY) → fade broken → miss."""
        from engine.desk_scorer import eval_rel_return
        import unittest.mock as mock

        # Fade check: falsified if realized > +0.05
        check = {"kind": "rel_return", "subject_ticker": "GME", "vs": "SPY",
                 "op": ">", "threshold": 0.05}
        # GME +20%, SPY flat → realized = +0.20 → +0.20 > 0.05 → falsified → miss
        def _fake_close(ticker, root, check_by):
            return {"GME": 30.0, "SPY": 700.0}[ticker]  # GME +20%

        with mock.patch("engine.desk_scorer.close_at", side_effect=_fake_close):
            with mock.patch("engine.desk_scorer.start_level",
                            side_effect=lambda t, e, r, a: {"GME": 25.0, "SPY": 700.0}.get(t)):
                result = eval_rel_return(
                    check,
                    entry={"GME": 25.0, "SPY": 700.0},
                    root=None,
                    asof="2026-07-12",
                    check_by="2026-07-19",
                )
        assert result is not None
        assert result["outcome"] == "miss", (
            f"fade: rising stock should be a miss (fade broken), got '{result['outcome']}'"
        )


# ---------------------------------------------------------------------------
# 12. MINOR-2: per-(ticker, family) active dedup
# ---------------------------------------------------------------------------

class TestPerFamilyActiveDedup:
    """_active_subjects must return (ticker, family) pairs, not bare tickers.
    A ticker with an open thesis in one family must NOT block a new thesis
    in a different family.
    """

    def test_active_subjects_returns_ticker_family_pairs(self):
        from engine.altdata_ledger import _active_subjects
        rows = [
            {"ticker": "GME", "claim_family": "altdata_event", "check_by": "2026-12-31"},
            {"ticker": "AAPL", "claim_family": "altdata_slow", "check_by": "2026-12-31"},
        ]
        active = _active_subjects(rows, "2026-07-12")
        assert ("GME", "altdata_event") in active
        assert ("AAPL", "altdata_slow") in active
        # Pure ticker (non-tuple) must NOT be in the set
        assert "GME" not in active
        assert "AAPL" not in active

    def test_same_ticker_different_family_both_active(self):
        from engine.altdata_ledger import _active_subjects
        rows = [
            {"ticker": "AAPL", "claim_family": "altdata_event", "check_by": "2026-12-31"},
            {"ticker": "AAPL", "claim_family": "altdata_slow", "check_by": "2026-12-31"},
        ]
        active = _active_subjects(rows, "2026-07-12")
        assert ("AAPL", "altdata_event") in active
        assert ("AAPL", "altdata_slow") in active

    def test_same_ticker_open_in_one_family_does_not_block_other(self):
        from engine.altdata_ledger import _active_subjects
        rows = [
            {"ticker": "AAPL", "claim_family": "altdata_event", "check_by": "2026-12-31"},
        ]
        active = _active_subjects(rows, "2026-07-12")
        assert ("AAPL", "altdata_event") in active
        # Not open in slow → should NOT be in active
        assert ("AAPL", "altdata_slow") not in active

    def test_expired_thesis_not_active(self):
        from engine.altdata_ledger import _active_subjects
        rows = [
            {"ticker": "AAPL", "claim_family": "altdata_event", "check_by": "2026-01-01"},
        ]
        active = _active_subjects(rows, "2026-07-12")
        assert ("AAPL", "altdata_event") not in active

    def test_legacy_family_uses_altdata_default(self):
        """Rows with no claim_family default to 'altdata' family in the tuple."""
        from engine.altdata_ledger import _active_subjects
        rows = [
            {"ticker": "CARR", "check_by": "2026-12-31"},  # no claim_family
        ]
        active = _active_subjects(rows, "2026-07-12")
        assert ("CARR", "altdata") in active


# ---------------------------------------------------------------------------
# 13. MINOR-3: newly mapped channels route correctly
# ---------------------------------------------------------------------------

class TestNewlyMappedChannels:
    """The 6 channels that were previously unmapped must now route correctly."""

    def test_github_momentum_routes_to_mid(self):
        # dev-adoption momentum builds over weeks-months (W2 review correction)
        assert assign_claim_family(["github_momentum"]) == "altdata_mid"

    def test_hf_model_momentum_routes_to_mid(self):
        assert assign_claim_family(["hf_model_momentum"]) == "altdata_mid"

    def test_earnings_beat_routes_to_event(self):
        assert assign_claim_family(["earnings_beat"]) == "altdata_event"

    def test_cnbc_pick_routes_to_mid(self):
        assert assign_claim_family(["cnbc_pick"]) == "altdata_mid"

    def test_news_sentiment_routes_to_mid(self):
        assert assign_claim_family(["news_sentiment"]) == "altdata_mid"

    def test_bill_catalyst_routes_to_slow(self):
        assert assign_claim_family(["bill_catalyst"]) == "altdata_slow"

    def test_genuinely_unknown_channel_routes_to_mid(self):
        """Truly unknown channels must route to altdata_mid (not altdata_event)."""
        result = assign_claim_family(["totally_unknown_channel_xyz"])
        assert result == "altdata_mid", (
            f"unknown channels must route to altdata_mid (safer mid-horizon fallback), "
            f"got '{result}'"
        )
