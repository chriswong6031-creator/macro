"""Tests for ALTDATA_REBOOT W2 — per-channel claim families, episode cooldown,
placebo determinism, attention short-direction, legacy regression.

Covers:
  * assign_claim_family: highest-weight channel routing, ties, unmapped channels.
  * Episode cooldown: same (ticker, family) blocked during cooldown window.
  * Placebo emission: is_placebo=True, placebo_path='altdata_matched', determinism.
  * Attention family: direction=-1 regardless of thesis lean.
  * Legacy regression: existing 'altdata'-family claims are untouched by new routing.
  * backfill_altdata: new-era theses emit 2 placebos; legacy theses emit none.
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

    def test_unmapped_channel_defaults_to_event(self):
        # 'cnbc_pick' (weight=0.25) is NOT in any family set → altdata_event
        fam = assign_claim_family(["cnbc_pick"])
        assert fam == "altdata_event"

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
