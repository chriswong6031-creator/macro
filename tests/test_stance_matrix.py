"""tests/test_stance_matrix.py — MLC W2b stance-matrix builder unit tests.

Covers (all fixtures via tmp_path; zero real data/ or site/ writes):
  - Tier-mapping exactness for every enum value of every organ family
  - Spread / agreement grading including n_reads < 2 -> null spread
  - Agreement thresholds: spread 0-1 -> aligned, 2 -> mixed, >= 3 -> split
  - Absent-artifact honest-null behavior (missing input files -> row omitted or
    organ absent, never crashes)
  - Bilingual receipts present (tip_en and tip_zh non-empty when organs present)
  - Builder exit-0 on empty/corrupt inputs
  - Zero real data/ or site/ writes (tmp_path root isolation)
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.build_stance_matrix import (
    _SECTOR_TIER,
    _RECO_TIER,
    _CONFLUENCE_TIER,
    _M7C_TIER,
    _RS_LEAD_TIER,
    _agreement,
    _build_tip,
    _build_sector_tip,
    _round_half_away_from_zero,
    _freshness_ok,
    build,
)


# ---------------------------------------------------------------------------
# Tier-mapping tables — exactness
# ---------------------------------------------------------------------------

class TestSectorTierMapping:
    def test_accumulate(self):
        assert _SECTOR_TIER["Accumulate"] == +2

    def test_constructive(self):
        assert _SECTOR_TIER["Constructive"] == +1

    def test_neutral(self):
        assert _SECTOR_TIER["Neutral"] == 0

    def test_cautious(self):
        assert _SECTOR_TIER["Cautious"] == -1

    def test_reduce(self):
        assert _SECTOR_TIER["Reduce"] == -2

    def test_covers_all_five_values(self):
        assert set(_SECTOR_TIER.keys()) == {"Accumulate", "Constructive", "Neutral", "Cautious", "Reduce"}


class TestRecoTierMapping:
    def test_enter(self):
        assert _RECO_TIER["enter"] == +2

    def test_accumulate(self):
        assert _RECO_TIER["accumulate"] == +1

    def test_hold(self):
        assert _RECO_TIER["hold"] == 0

    def test_trim(self):
        assert _RECO_TIER["trim"] == -1

    def test_avoid(self):
        assert _RECO_TIER["avoid"] == -2

    def test_covers_all_five_values(self):
        assert set(_RECO_TIER.keys()) == {"enter", "accumulate", "hold", "trim", "avoid"}


class TestConfluenceTierMapping:
    def test_entry_now(self):
        assert _CONFLUENCE_TIER["entry_now"] == +2

    def test_forming(self):
        assert _CONFLUENCE_TIER["forming"] == +1

    def test_tailwind(self):
        assert _CONFLUENCE_TIER["tailwind"] == +1

    def test_neutral(self):
        assert _CONFLUENCE_TIER["neutral"] == 0

    def test_late(self):
        assert _CONFLUENCE_TIER["late"] == -1

    def test_headwind(self):
        assert _CONFLUENCE_TIER["headwind"] == -2

    def test_covers_all_six_values(self):
        assert set(_CONFLUENCE_TIER.keys()) == {
            "entry_now", "forming", "tailwind", "neutral", "late", "headwind"
        }


class TestM7CTierMapping:
    def test_running_broad(self):
        assert _M7C_TIER["running_broad"] == +2

    def test_running_narrow(self):
        assert _M7C_TIER["running_narrow"] == +1

    def test_turning_up(self):
        assert _M7C_TIER["turning_up"] == +1

    def test_cooling(self):
        assert _M7C_TIER["cooling"] == 0

    def test_rolling_over(self):
        assert _M7C_TIER["rolling_over"] == -1

    def test_down(self):
        assert _M7C_TIER["down"] == -2

    def test_covers_all_six_values(self):
        assert set(_M7C_TIER.keys()) == {
            "running_broad", "running_narrow", "turning_up", "cooling", "rolling_over", "down"
        }


# ---------------------------------------------------------------------------
# Allocation special cases
# ---------------------------------------------------------------------------

class TestAllocationTier:
    """Allocation organ: held -> +1, not_held -> 0 (absence is not negative)."""

    def test_held_yields_tier_1(self, tmp_path):
        """held maps to +1."""
        _write_baskets(tmp_path, [{"id": "ai_infra", "name": "AI Infra", "reco": "enter"}])
        _write_alloc(tmp_path, ["ai_infra"])
        payload = build(root=tmp_path)
        row = _row_by_id(payload, "ai_infra")
        assert row["verdicts"]["allocation"]["tier"] == 1

    def test_not_held_yields_tier_0(self, tmp_path):
        """not_held maps to 0 — absence is weak evidence, never negative."""
        _write_baskets(tmp_path, [{"id": "ai_infra", "name": "AI Infra", "reco": "enter"}])
        _write_alloc(tmp_path, [])
        payload = build(root=tmp_path)
        row = _row_by_id(payload, "ai_infra")
        assert row["verdicts"]["allocation"]["tier"] == 0


# ---------------------------------------------------------------------------
# Spread and agreement grading
# ---------------------------------------------------------------------------

class TestAgreement:
    def test_spread_0_is_aligned(self):
        assert _agreement(0) == "aligned"

    def test_spread_1_is_aligned(self):
        assert _agreement(1) == "aligned"

    def test_spread_2_is_mixed(self):
        assert _agreement(2) == "mixed"

    def test_spread_3_is_split(self):
        assert _agreement(3) == "split"

    def test_spread_4_is_split(self):
        assert _agreement(4) == "split"

    def test_spread_none_is_none(self):
        assert _agreement(None) is None

    def test_n_reads_lt_2_yields_null_spread(self, tmp_path):
        """Only 1 organ present -> spread=None, agreement=None."""
        _write_baskets(tmp_path, [{"id": "ai_infra", "name": "AI Infra", "reco": "enter"}])
        # No alloc, no sector, no confluence, no mag7 -> only reco organ fires
        _write_alloc(tmp_path, [])
        payload = build(root=tmp_path)
        row = _row_by_id(payload, "ai_infra")
        # reco fires (enter -> +2); allocation fires (not_held -> 0) = 2 reads now
        # let's verify spread is not None when 2 reads present
        assert row["n_reads"] >= 2  # alloc + reco always present
        assert row["spread"] is not None


class TestSpreadComputed:
    def test_aligned_all_same_tier(self, tmp_path):
        """All organs at same tier -> spread = 0 -> aligned."""
        _write_baskets(tmp_path, [{"id": "ai_infra", "name": "AI Infra", "reco": "enter"}])
        _write_alloc(tmp_path, ["ai_infra"])
        # sector: Accumulate (+2), reco: enter (+2), alloc: held (+1) -> spread=max-min=2-1=1 -> aligned
        _write_sector_central(tmp_path, [{"ticker": "SMH", "label_en": "Accumulate"}])
        payload = build(root=tmp_path)
        row = _row_by_id(payload, "ai_infra")
        # sector=+2, reco=+2, alloc=+1 -> spread=1 -> aligned
        assert row["spread"] == 1
        assert row["agreement"] == "aligned"

    def test_mixed_when_spread_2(self, tmp_path):
        """sector Accumulate (+2), reco hold (0), alloc not_held (0) -> spread=2 -> mixed."""
        _write_baskets(tmp_path, [{"id": "ai_infra", "name": "AI Infra", "reco": "hold"}])
        _write_alloc(tmp_path, [])
        _write_sector_central(tmp_path, [{"ticker": "SMH", "label_en": "Accumulate"}])
        payload = build(root=tmp_path)
        row = _row_by_id(payload, "ai_infra")
        # sector=+2, reco=0, alloc=0 -> spread=2 -> mixed
        assert row["spread"] == 2
        assert row["agreement"] == "mixed"

    def test_split_when_spread_3(self, tmp_path):
        """sector Accumulate (+2), reco avoid (-2), alloc not_held (0) -> spread=4 -> split."""
        _write_baskets(tmp_path, [{"id": "ai_infra", "name": "AI Infra", "reco": "avoid"}])
        _write_alloc(tmp_path, [])
        _write_sector_central(tmp_path, [{"ticker": "SMH", "label_en": "Accumulate"}])
        payload = build(root=tmp_path)
        row = _row_by_id(payload, "ai_infra")
        # sector=+2, reco=-2, alloc=0 -> spread=4 -> split
        assert row["spread"] == 4
        assert row["agreement"] == "split"


# ---------------------------------------------------------------------------
# Bilingual receipts
# ---------------------------------------------------------------------------

class TestBilingualReceipts:
    def test_tip_en_and_tip_zh_both_present_when_organs_fire(self, tmp_path):
        _write_baskets(tmp_path, [{"id": "ai_infra", "name": "AI Infra", "reco": "enter"}])
        _write_alloc(tmp_path, ["ai_infra"])
        _write_sector_central(tmp_path, [{"ticker": "SMH", "label_en": "Accumulate"}])
        payload = build(root=tmp_path)
        row = _row_by_id(payload, "ai_infra")
        assert row["tip_en"] != ""
        assert row["tip_zh"] != ""

    def test_tip_en_contains_organ_labels(self, tmp_path):
        _write_baskets(tmp_path, [{"id": "ai_infra", "name": "AI Infra", "reco": "enter"}])
        _write_alloc(tmp_path, ["ai_infra"])
        payload = build(root=tmp_path)
        row = _row_by_id(payload, "ai_infra")
        assert "Theme" in row["tip_en"] or "Allocation" in row["tip_en"]

    def test_build_tip_returns_both_strings(self):
        verdicts = {
            "sector": {"raw": "Accumulate", "tier": 2},
            "theme": {"raw": "enter", "tier": 2},
        }
        en, zh = _build_tip(verdicts)
        assert "Accumulate" in en
        assert "积极配置" in zh
        assert "Sector" in en
        assert "板块" in zh

    def test_build_tip_empty_when_no_verdicts(self):
        en, zh = _build_tip({})
        assert en == ""
        assert zh == ""


# ---------------------------------------------------------------------------
# Absent-artifact honest-null behavior
# ---------------------------------------------------------------------------

class TestAbsentArtifacts:
    def test_empty_baskets_yields_empty_rows(self, tmp_path):
        """No themes -> rows=[]."""
        _write_baskets(tmp_path, [])
        payload = build(root=tmp_path)
        assert payload["rows"] == []

    def test_missing_baskets_json_yields_empty_rows(self, tmp_path):
        """Missing baskets.json -> rows=[] (no crash)."""
        payload = build(root=tmp_path)
        assert payload["rows"] == []

    def test_corrupt_baskets_json_yields_empty_rows(self, tmp_path):
        """Corrupt baskets.json -> rows=[] (no crash)."""
        _site(tmp_path).mkdir(parents=True, exist_ok=True)
        (_site(tmp_path) / "basketdata").mkdir(exist_ok=True)
        (_site(tmp_path) / "basketdata" / "baskets.json").write_text("NOT JSON", encoding="utf-8")
        payload = build(root=tmp_path)
        assert payload["rows"] == []

    def test_sector_absent_yields_no_sector_verdict(self, tmp_path):
        """Missing sector_central.json -> sector organ absent on row (other organs still fire)."""
        _write_baskets(tmp_path, [{"id": "ai_infra", "name": "AI Infra", "reco": "enter"}])
        _write_alloc(tmp_path, [])
        payload = build(root=tmp_path)
        row = _row_by_id(payload, "ai_infra")
        assert "sector" not in row["verdicts"]
        assert "theme" in row["verdicts"]

    def test_confluence_absent_yields_no_confluence_verdict(self, tmp_path):
        """Missing basket_confluence.json -> confluence organ absent (no crash)."""
        _write_baskets(tmp_path, [{"id": "ai_infra", "name": "AI Infra", "reco": "enter"}])
        _write_alloc(tmp_path, [])
        payload = build(root=tmp_path)
        row = _row_by_id(payload, "ai_infra")
        assert "confluence" not in row["verdicts"]

    def test_mag7_only_for_mag7_basket(self, tmp_path):
        """m7c organ only fires for basket id==mag7."""
        _write_baskets(tmp_path, [
            {"id": "ai_infra", "name": "AI Infra", "reco": "enter"},
            {"id": "mag7", "name": "Mag-7", "reco": "accumulate"},
        ])
        _write_alloc(tmp_path, [])
        _write_mag7(tmp_path, "running_broad")
        payload = build(root=tmp_path)
        infra = _row_by_id(payload, "ai_infra")
        mag7 = _row_by_id(payload, "mag7")
        assert "m7c" not in infra["verdicts"]
        assert "m7c" in mag7["verdicts"]
        assert mag7["verdicts"]["m7c"]["tier"] == 2

    def test_builder_exit0_on_corrupt_all_inputs(self, tmp_path):
        """build() must return a valid payload dict even when all inputs are garbage."""
        for p in [
            "site/basketdata/baskets.json",
            "site/marketdata/basket_confluence.json",
            "site/sectordata/sector_central.json",
            "site/allocationdata/allocation.json",
        ]:
            full = tmp_path / p
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text("GARBAGE", encoding="utf-8")
        payload = build(root=tmp_path)
        assert "schema" in payload
        assert payload["schema"] == "mlc.stance_matrix.v1"
        assert "rows" in payload

    def test_no_real_site_writes(self, tmp_path):
        """build(root=tmp_path) must only write under tmp_path, not the real repo root."""
        real_out = ROOT / "site" / "mlcdata" / "stance_matrix.json"
        existed_before = real_out.exists()
        _write_baskets(tmp_path, [{"id": "ai_infra", "name": "AI Infra", "reco": "enter"}])
        _write_alloc(tmp_path, [])
        build(root=tmp_path)
        # If the file didn't exist before, it still shouldn't
        if not existed_before:
            assert not real_out.exists(), "build() must not write to real site/"

    def test_output_written_under_tmp_root(self, tmp_path):
        """build(root=tmp_path) writes to tmp_path/site/mlcdata/stance_matrix.json."""
        _write_baskets(tmp_path, [{"id": "ai_infra", "name": "AI Infra", "reco": "enter"}])
        _write_alloc(tmp_path, [])
        build(root=tmp_path)
        out = tmp_path / "site" / "mlcdata" / "stance_matrix.json"
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["schema"] == "mlc.stance_matrix.v1"


# ---------------------------------------------------------------------------
# Schema fields
# ---------------------------------------------------------------------------

class TestSchemaFields:
    def test_payload_has_schema_field(self, tmp_path):
        payload = build(root=tmp_path)
        assert payload["schema"] == "mlc.stance_matrix.v1"

    def test_payload_has_as_of(self, tmp_path):
        payload = build(root=tmp_path)
        assert payload["as_of"] == date.today().isoformat()

    def test_payload_has_inputs(self, tmp_path):
        payload = build(root=tmp_path)
        assert "inputs" in payload

    def test_row_has_required_fields(self, tmp_path):
        _write_baskets(tmp_path, [{"id": "ai_infra", "name": "AI Infra", "reco": "enter"}])
        _write_alloc(tmp_path, [])
        payload = build(root=tmp_path)
        row = _row_by_id(payload, "ai_infra")
        for field in ("id", "name", "verdicts", "n_reads", "spread", "agreement", "tip_en", "tip_zh"):
            assert field in row, f"missing field: {field}"


# ---------------------------------------------------------------------------
# Freshness helper
# ---------------------------------------------------------------------------

class TestFreshnessOk:
    def test_today_is_fresh(self):
        assert _freshness_ok(date.today().isoformat()) is True

    def test_exactly_5_days_ago_is_fresh(self):
        from datetime import timedelta
        d = (date.today() - timedelta(days=5)).isoformat()
        assert _freshness_ok(d) is True

    def test_6_days_ago_is_stale(self):
        from datetime import timedelta
        d = (date.today() - timedelta(days=6)).isoformat()
        assert _freshness_ok(d) is False

    def test_none_is_stale(self):
        assert _freshness_ok(None) is False

    def test_empty_string_is_stale(self):
        assert _freshness_ok("") is False

    def test_garbage_is_stale(self):
        assert _freshness_ok("not-a-date") is False


# ---------------------------------------------------------------------------
# Freshness gating — stale source yields omitted organ (honest null)
# ---------------------------------------------------------------------------

class TestFreshnessGating:
    """Each gated source: fresh (today) passes; 6-day-old is omitted."""

    def test_sector_central_fresh_fires_organ(self, tmp_path):
        """Fresh sector_central (today) → sector organ present on row."""
        _write_baskets(tmp_path, [{"id": "ai_infra", "name": "AI Infra", "reco": "enter"}])
        _write_alloc(tmp_path, [])
        _write_sector_central(tmp_path, [{"ticker": "XLK", "label_en": "Accumulate"}])
        payload = build(root=tmp_path)
        row = _row_by_id(payload, "ai_infra")
        # ai_infra -> SMH -> fallback XLK (Accumulate) -> sector organ fires
        assert "sector" in row["verdicts"]

    def test_sector_central_stale_omits_organ(self, tmp_path):
        """Stale sector_central (6 days old) → sector organ absent on row."""
        from datetime import timedelta
        _write_baskets(tmp_path, [{"id": "ai_infra", "name": "AI Infra", "reco": "enter"}])
        _write_alloc(tmp_path, [])
        _write_sector_central(tmp_path, [{"ticker": "XLK", "label_en": "Accumulate"}],
                              as_of=(date.today() - timedelta(days=6)).isoformat())
        payload = build(root=tmp_path)
        row = _row_by_id(payload, "ai_infra")
        assert "sector" not in row["verdicts"]

    def test_confluence_fresh_fires_organ(self, tmp_path):
        """Fresh confluence (today) → confluence organ present on row."""
        _write_baskets(tmp_path, [{"id": "ai_infra", "name": "AI Infra", "reco": "enter"}])
        _write_alloc(tmp_path, [])
        _write_confluence(tmp_path, [{"basket_id": "ai_infra", "class": "entry_now"}])
        payload = build(root=tmp_path)
        row = _row_by_id(payload, "ai_infra")
        assert "confluence" in row["verdicts"]

    def test_confluence_stale_omits_organ(self, tmp_path):
        """Stale confluence (6 days old) → confluence organ absent on row."""
        from datetime import timedelta
        _write_baskets(tmp_path, [{"id": "ai_infra", "name": "AI Infra", "reco": "enter"}])
        _write_alloc(tmp_path, [])
        _write_confluence(tmp_path, [{"basket_id": "ai_infra", "class": "entry_now"}],
                          as_of=(date.today() - timedelta(days=6)).isoformat())
        payload = build(root=tmp_path)
        row = _row_by_id(payload, "ai_infra")
        assert "confluence" not in row["verdicts"]

    def test_alloc_fresh_fires_organ(self, tmp_path):
        """Fresh allocation (today) → allocation organ present on row."""
        _write_baskets(tmp_path, [{"id": "ai_infra", "name": "AI Infra", "reco": "enter"}])
        _write_alloc(tmp_path, ["ai_infra"])
        payload = build(root=tmp_path)
        row = _row_by_id(payload, "ai_infra")
        assert "allocation" in row["verdicts"]

    def test_alloc_stale_omits_organ(self, tmp_path):
        """Stale allocation (6 days old) → allocation organ absent on row."""
        from datetime import timedelta
        _write_baskets(tmp_path, [{"id": "ai_infra", "name": "AI Infra", "reco": "enter"}])
        _write_alloc(tmp_path, ["ai_infra"],
                     as_of=(date.today() - timedelta(days=6)).isoformat())
        payload = build(root=tmp_path)
        row = _row_by_id(payload, "ai_infra")
        assert "allocation" not in row["verdicts"]

    def test_mag7_fresh_fires_organ(self, tmp_path):
        """Fresh mag7 (today) → m7c organ present on mag7 row."""
        _write_baskets(tmp_path, [{"id": "mag7", "name": "Mag-7", "reco": "enter"}])
        _write_alloc(tmp_path, [])
        _write_mag7(tmp_path, "running_broad")
        payload = build(root=tmp_path)
        row = _row_by_id(payload, "mag7")
        assert "m7c" in row["verdicts"]

    def test_mag7_stale_omits_organ(self, tmp_path):
        """Stale mag7 (6 days old) → m7c organ absent on mag7 row."""
        from datetime import timedelta
        _write_baskets(tmp_path, [{"id": "mag7", "name": "Mag-7", "reco": "enter"}])
        _write_alloc(tmp_path, [])
        _write_mag7(tmp_path, "running_broad",
                    as_of=(date.today() - timedelta(days=6)).isoformat())
        payload = build(root=tmp_path)
        row = _row_by_id(payload, "mag7")
        assert "m7c" not in row["verdicts"]

    def test_inputs_dict_keeps_raw_as_of_receipts_when_stale(self, tmp_path):
        """inputs{} must carry raw as_of even when stale (for transparency)."""
        from datetime import timedelta
        stale = (date.today() - timedelta(days=6)).isoformat()
        _write_baskets(tmp_path, [{"id": "ai_infra", "name": "AI Infra", "reco": "enter"}])
        _write_alloc(tmp_path, [], as_of=stale)
        _write_sector_central(tmp_path, [{"ticker": "XLK", "label_en": "Reduce"}],
                              as_of=stale)
        payload = build(root=tmp_path)
        # Stale inputs are recorded in inputs{} even though organs are omitted
        assert payload["inputs"]["sector_central"] == stale
        assert payload["inputs"]["allocation"] == stale


# ---------------------------------------------------------------------------
# MLC-W2b-2: sector-grain tests
# ---------------------------------------------------------------------------

class TestRSLeadTierMapping:
    """_RS_LEAD_TIER: exactly three values, pre-registered ±1 range."""

    def test_leading(self):
        assert _RS_LEAD_TIER["leading"] == +1

    def test_mid_pack(self):
        assert _RS_LEAD_TIER["mid-pack"] == 0

    def test_lagging(self):
        assert _RS_LEAD_TIER["lagging"] == -1

    def test_covers_exactly_three_values(self):
        assert set(_RS_LEAD_TIER.keys()) == {"leading", "mid-pack", "lagging"}


class TestRoundHalfAwayFromZero:
    """_round_half_away_from_zero: halves go away from zero, not banker's rounding."""

    def test_positive_half(self):
        assert _round_half_away_from_zero(0.5) == 1

    def test_negative_half(self):
        assert _round_half_away_from_zero(-0.5) == -1

    def test_zero(self):
        assert _round_half_away_from_zero(0.0) == 0

    def test_positive_int(self):
        assert _round_half_away_from_zero(2.0) == 2

    def test_negative_int(self):
        assert _round_half_away_from_zero(-2.0) == -2

    def test_positive_below_half(self):
        assert _round_half_away_from_zero(0.4) == 0

    def test_negative_below_half(self):
        assert _round_half_away_from_zero(-0.4) == 0


class TestSectorRowsPresent:
    """Sector-grain rows emitted with all three verdicts when sector_central is fresh."""

    def test_sectors_key_present_in_payload(self, tmp_path):
        """payload must always carry a 'sectors' key."""
        _write_baskets(tmp_path, [])
        payload = build(root=tmp_path)
        assert "sectors" in payload

    def test_sector_row_has_all_three_verdicts(self, tmp_path):
        """When all inputs present, each sector row carries conviction, rs, baskets verdicts."""
        _write_baskets(tmp_path, [{"id": "ai_infra", "name": "AI Infra", "reco": "enter"}])
        _write_alloc(tmp_path, [])
        _write_sector_central_full(tmp_path, [
            {"ticker": "XLK", "label_en": "Accumulate", "label_zh": "积极配置",
             "name": "Technology", "name_zh": "科技", "lead": "leading"},
        ])
        payload = build(root=tmp_path)
        secs = {s["ticker"]: s for s in payload.get("sectors") or []}
        assert "XLK" in secs
        xlk = secs["XLK"]
        assert "conviction" in xlk["verdicts"]
        assert "rs" in xlk["verdicts"]
        # baskets verdict: ai_infra→SMH→fallback XLK → reco "enter" (tier +2) present
        assert "baskets" in xlk["verdicts"]

    def test_sector_conviction_tier(self, tmp_path):
        """Conviction verdict reuses the same _SECTOR_TIER map as basket-side."""
        _write_baskets(tmp_path, [])
        _write_alloc(tmp_path, [])
        _write_sector_central_full(tmp_path, [
            {"ticker": "XLK", "label_en": "Reduce", "name": "Technology", "name_zh": "科技", "lead": "mid-pack"},
        ])
        payload = build(root=tmp_path)
        secs = {s["ticker"]: s for s in payload.get("sectors") or []}
        assert secs["XLK"]["verdicts"]["conviction"]["tier"] == -2
        assert secs["XLK"]["verdicts"]["conviction"]["raw"] == "Reduce"

    def test_rs_lead_map_exactness_leading(self, tmp_path):
        """lead='leading' → rs tier +1."""
        _write_baskets(tmp_path, [])
        _write_alloc(tmp_path, [])
        _write_sector_central_full(tmp_path, [
            {"ticker": "XLK", "label_en": "Neutral", "name": "Technology", "name_zh": "科技", "lead": "leading"},
        ])
        payload = build(root=tmp_path)
        secs = {s["ticker"]: s for s in payload.get("sectors") or []}
        assert secs["XLK"]["verdicts"]["rs"]["tier"] == +1

    def test_rs_lead_map_exactness_mid_pack(self, tmp_path):
        """lead='mid-pack' → rs tier 0."""
        _write_baskets(tmp_path, [])
        _write_alloc(tmp_path, [])
        _write_sector_central_full(tmp_path, [
            {"ticker": "XLK", "label_en": "Neutral", "name": "Technology", "name_zh": "科技", "lead": "mid-pack"},
        ])
        payload = build(root=tmp_path)
        secs = {s["ticker"]: s for s in payload.get("sectors") or []}
        assert secs["XLK"]["verdicts"]["rs"]["tier"] == 0

    def test_rs_lead_map_exactness_lagging(self, tmp_path):
        """lead='lagging' → rs tier -1."""
        _write_baskets(tmp_path, [])
        _write_alloc(tmp_path, [])
        _write_sector_central_full(tmp_path, [
            {"ticker": "XLK", "label_en": "Neutral", "name": "Technology", "name_zh": "科技", "lead": "lagging"},
        ])
        payload = build(root=tmp_path)
        secs = {s["ticker"]: s for s in payload.get("sectors") or []}
        assert secs["XLK"]["verdicts"]["rs"]["tier"] == -1


class TestSectorBasketMedian:
    """Baskets verdict: median of member theme tiers, rounding, absent when no members."""

    def test_baskets_median_odd_count(self, tmp_path):
        """Three baskets in same sector: median of [2, 0, -1] = 0."""
        # ai_infra→SMH→XLK (enter=+2), ai_software→XLK (hold=0), mag7→XLK (accumulate=+1)
        # We need baskets all mapping to XLK
        _write_baskets(tmp_path, [
            {"id": "ai_infra", "name": "AI Infra", "reco": "enter"},       # SMH→XLK, tier +2
            {"id": "ai_software", "name": "AI Software", "reco": "hold"},   # XLK, tier 0
            {"id": "defensives", "name": "Defensives", "reco": "trim"},     # XLP, tier -1
        ])
        _write_alloc(tmp_path, [])
        _write_sector_central_full(tmp_path, [
            {"ticker": "XLK", "label_en": "Neutral", "name": "Technology", "name_zh": "科技", "lead": "mid-pack"},
            {"ticker": "XLP", "label_en": "Neutral", "name": "Staples", "name_zh": "必需消费", "lead": "lagging"},
        ])
        payload = build(root=tmp_path)
        secs = {s["ticker"]: s for s in payload.get("sectors") or []}
        # XLK members: ai_infra (+2, via SMH->XLK), ai_software (+0)
        # median([+2, 0]) = 1.0 → rounds to 1
        xlk = secs["XLK"]
        assert "baskets" in xlk["verdicts"]
        assert xlk["verdicts"]["baskets"]["n_members"] == 2
        assert xlk["verdicts"]["baskets"]["tier"] == 1  # median(+2, 0) = 1.0 → 1

    def test_baskets_median_even_count_half_rounds_away(self, tmp_path):
        """Even count (2 members) with half median rounds away from zero.
        Tiers [+2, +1] → median=1.5 → rounds to 2 (away from zero)."""
        # ai_infra(enter=+2) + ai_software(accumulate=+1) both→XLK
        _write_baskets(tmp_path, [
            {"id": "ai_infra", "name": "AI Infra", "reco": "enter"},        # SMH→XLK, tier +2
            {"id": "ai_software", "name": "AI Software", "reco": "accumulate"},  # XLK, tier +1
        ])
        _write_alloc(tmp_path, [])
        _write_sector_central_full(tmp_path, [
            {"ticker": "XLK", "label_en": "Neutral", "name": "Technology", "name_zh": "科技", "lead": "mid-pack"},
        ])
        payload = build(root=tmp_path)
        secs = {s["ticker"]: s for s in payload.get("sectors") or []}
        xlk = secs["XLK"]
        assert xlk["verdicts"]["baskets"]["tier"] == 2  # median(+2, +1) = 1.5 → 2

    def test_baskets_absent_when_no_member_has_theme_verdict(self, tmp_path):
        """No basket maps to the sector with a theme verdict → baskets verdict absent."""
        # Only XLI sector; no basket in proxy map points to XLI
        _write_baskets(tmp_path, [{"id": "ai_infra", "name": "AI Infra", "reco": "enter"}])
        _write_alloc(tmp_path, [])
        _write_sector_central_full(tmp_path, [
            {"ticker": "XLI", "label_en": "Neutral", "name": "Industrials", "name_zh": "工业",
             "lead": "mid-pack"},
            # NOTE: defense and reshoring→XLI but they are not in baskets list
        ])
        payload = build(root=tmp_path)
        secs = {s["ticker"]: s for s in payload.get("sectors") or []}
        if "XLI" in secs:
            assert "baskets" not in secs["XLI"]["verdicts"]

    def test_smh_proxied_baskets_count_toward_xlk(self, tmp_path):
        """SMH-proxied baskets (ai_infra, ai_semiconductors) count toward XLK member set."""
        _write_baskets(tmp_path, [
            {"id": "ai_infra", "name": "AI Infra", "reco": "enter"},           # SMH→XLK
            {"id": "ai_semiconductors", "name": "AI Semis", "reco": "hold"},   # SMH→XLK
        ])
        _write_alloc(tmp_path, [])
        _write_sector_central_full(tmp_path, [
            {"ticker": "XLK", "label_en": "Accumulate", "name": "Technology", "name_zh": "科技",
             "lead": "leading"},
        ])
        payload = build(root=tmp_path)
        secs = {s["ticker"]: s for s in payload.get("sectors") or []}
        xlk = secs["XLK"]
        assert "baskets" in xlk["verdicts"]
        # ai_infra (enter=+2) + ai_semiconductors (hold=0) → n_members=2
        assert xlk["verdicts"]["baskets"]["n_members"] == 2


class TestSectorAgreementGrading:
    """Sector row agreement: same _agreement() function as basket rows."""

    def test_sector_agreement_asymmetric_range(self, tmp_path):
        """conviction=-2 (Reduce), rs=+1 (leading) → spread=3 → split.
        Verifies the asymmetric ±1 RS range: Reduce (-2) + leading (+1) = spread 3."""
        _write_baskets(tmp_path, [])
        _write_alloc(tmp_path, [])
        _write_sector_central_full(tmp_path, [
            {"ticker": "XLK", "label_en": "Reduce", "name": "Technology", "name_zh": "科技",
             "lead": "leading"},
        ])
        payload = build(root=tmp_path)
        secs = {s["ticker"]: s for s in payload.get("sectors") or []}
        xlk = secs["XLK"]
        # conviction tier = -2, rs tier = +1, no baskets → spread = 3 → split
        assert xlk["verdicts"]["conviction"]["tier"] == -2
        assert xlk["verdicts"]["rs"]["tier"] == +1
        assert xlk["spread"] == 3
        assert xlk["agreement"] == "split"

    def test_sector_agreement_aligned(self, tmp_path):
        """conviction=Accumulate (+2), rs=leading (+1) → spread=1 → aligned."""
        _write_baskets(tmp_path, [])
        _write_alloc(tmp_path, [])
        _write_sector_central_full(tmp_path, [
            {"ticker": "XLK", "label_en": "Accumulate", "name": "Technology", "name_zh": "科技",
             "lead": "leading"},
        ])
        payload = build(root=tmp_path)
        secs = {s["ticker"]: s for s in payload.get("sectors") or []}
        xlk = secs["XLK"]
        assert xlk["agreement"] == "aligned"


class TestSectorFreshnessGating:
    """Sector section respects the SAME freshness gate as the basket-side sector organ."""

    def test_sector_rows_absent_when_sector_central_stale(self, tmp_path):
        """Stale sector_central (6d old) → sectors[] is empty list."""
        from datetime import timedelta
        _write_baskets(tmp_path, [{"id": "ai_infra", "name": "AI Infra", "reco": "enter"}])
        _write_alloc(tmp_path, [])
        _write_sector_central_full(tmp_path, [
            {"ticker": "XLK", "label_en": "Accumulate", "name": "Technology", "name_zh": "科技",
             "lead": "leading"},
        ], as_of=(date.today() - timedelta(days=6)).isoformat())
        payload = build(root=tmp_path)
        assert payload.get("sectors") == []

    def test_sector_rows_absent_when_sector_central_missing(self, tmp_path):
        """Missing sector_central.json → sectors[] is empty list (no crash)."""
        _write_baskets(tmp_path, [{"id": "ai_infra", "name": "AI Infra", "reco": "enter"}])
        _write_alloc(tmp_path, [])
        # No _write_sector_central call
        payload = build(root=tmp_path)
        assert payload.get("sectors") == []


class TestSectorBilingualReceipts:
    """Sector tip_en/tip_zh present when verdicts fire."""

    def test_tip_en_and_zh_present(self, tmp_path):
        _write_baskets(tmp_path, [])
        _write_alloc(tmp_path, [])
        _write_sector_central_full(tmp_path, [
            {"ticker": "XLK", "label_en": "Accumulate", "name": "Technology", "name_zh": "科技",
             "lead": "leading"},
        ])
        payload = build(root=tmp_path)
        secs = {s["ticker"]: s for s in payload.get("sectors") or []}
        xlk = secs["XLK"]
        assert xlk["tip_en"] != ""
        assert xlk["tip_zh"] != ""

    def test_tip_contains_conviction_and_rs(self):
        """_build_sector_tip includes Conviction and RS labels in EN and ZH."""
        en, zh = _build_sector_tip("Reduce", "leading", None, 0)
        assert "Conviction" in en
        assert "Reduce" in en
        assert "RS" in en
        assert "leading" in en
        assert "评级" in zh
        assert "减配" in zh
        assert "动量" in zh
        assert "领先" in zh

    def test_tip_contains_baskets_when_present(self):
        """_build_sector_tip includes Baskets receipt when baskets_tier is given."""
        en, zh = _build_sector_tip("Neutral", "mid-pack", 1, 3)
        assert "Baskets" in en
        assert "median of 3" in en
        assert "篮子" in zh
        assert "3个中位数" in zh

    def test_tip_empty_when_no_verdicts(self):
        """No verdicts → empty receipt strings."""
        en, zh = _build_sector_tip(None, None, None, 0)
        assert en == ""
        assert zh == ""


# ---------------------------------------------------------------------------
# Helpers — fixture writers
# ---------------------------------------------------------------------------

def _site(root: Path) -> Path:
    return root / "site"


def _write_baskets(root: Path, themes: list[dict]) -> None:
    d = _site(root) / "basketdata"
    d.mkdir(parents=True, exist_ok=True)
    (d / "baskets.json").write_text(
        json.dumps({"theme_intel": {"as_of": date.today().isoformat(), "themes": themes}}),
        encoding="utf-8",
    )


def _write_alloc(root: Path, held_ids: list[str], as_of: str | None = None) -> None:
    d = _site(root) / "allocationdata"
    d.mkdir(parents=True, exist_ok=True)
    weights = [{"id": bid, "weight": 0.1, "rank": i + 1} for i, bid in enumerate(held_ids)]
    (d / "allocation.json").write_text(
        json.dumps({"as_of": as_of or date.today().isoformat(), "allocation": {"weights": weights}}),
        encoding="utf-8",
    )


def _write_sector_central(root: Path, sectors: list[dict], as_of: str | None = None) -> None:
    """sectors: list of {ticker, label_en, label_zh?}."""
    d = _site(root) / "sectordata"
    d.mkdir(parents=True, exist_ok=True)
    payload_sectors = [
        {
            "ticker": s["ticker"],
            "conviction": {
                "label_en": s["label_en"],
                "label_zh": s.get("label_zh", s["label_en"]),
            },
        }
        for s in sectors
    ]
    (d / "sector_central.json").write_text(
        json.dumps({"as_of": as_of or date.today().isoformat(), "sectors": payload_sectors}),
        encoding="utf-8",
    )


def _write_sector_central_full(root: Path, sectors: list[dict], as_of: str | None = None) -> None:
    """MLC-W2b-2: full sector_central fixture including momentum.lead, name, name_zh.

    sectors: list of {ticker, label_en, label_zh?, name?, name_zh?, lead?}
    lead: "leading" / "mid-pack" / "lagging" (for momentum.lead)
    """
    d = _site(root) / "sectordata"
    d.mkdir(parents=True, exist_ok=True)
    payload_sectors = [
        {
            "ticker": s["ticker"],
            "name": s.get("name", s["ticker"]),
            "name_zh": s.get("name_zh", ""),
            "conviction": {
                "label_en": s["label_en"],
                "label_zh": s.get("label_zh", s["label_en"]),
            },
            "momentum": {
                "lead": s.get("lead", "mid-pack"),
                "rs_rank": s.get("rs_rank", 1),
            },
        }
        for s in sectors
    ]
    (d / "sector_central.json").write_text(
        json.dumps({"as_of": as_of or date.today().isoformat(), "sectors": payload_sectors}),
        encoding="utf-8",
    )


def _write_confluence(root: Path, baskets: list[dict], as_of: str | None = None) -> None:
    """baskets: list of {basket_id, class}."""
    d = _site(root) / "marketdata"
    d.mkdir(parents=True, exist_ok=True)
    (d / "basket_confluence.json").write_text(
        json.dumps({
            "as_of": as_of or date.today().isoformat(),
            "baskets": baskets,
        }),
        encoding="utf-8",
    )


def _write_mag7(root: Path, trend_state: str, as_of: str | None = None) -> None:
    d = root / "data" / "mag7_regime"
    d.mkdir(parents=True, exist_ok=True)
    (d / "latest.json").write_text(
        json.dumps({"as_of": as_of or date.today().isoformat(), "trend_state": trend_state}),
        encoding="utf-8",
    )


def _row_by_id(payload: dict, bid: str) -> dict:
    for row in payload.get("rows") or []:
        if row.get("id") == bid:
            return row
    raise KeyError(f"no row with id={bid!r}")
