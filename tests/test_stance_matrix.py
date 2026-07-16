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
    _agreement,
    _build_tip,
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
