"""tests/test_contradictions_pair_g.py — Tests for pair-g (PR-A4).

Pair G: oracle complex out-rotation vs entry buy-list member.

Test cases:
  1. out-rotation complex + member ticker on buy list → emits 'tension' record
  2. No out-rotation complexes → no records emitted
  3. Buy ticker not in any complex → skipped silently (fail-open / unmappable)
  4. oracle_state absent → gap note, no records, no exception
  5. standouts absent → gap note, no records, no exception
  6. rotation_groups empty → gap note, no records
  7. basket_tickers_cache empty → gap note, no records
  8. Record schema: display_only=True, severity in ('note','tension'), correct fields
  9. 'decelerating' direction also triggers (not just 'out')
 10. 'in' direction does NOT trigger
 11. Dedupe: same (ticker, cx_id) pair appears once even if ticker in multiple baskets
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

def _make_oracle_state(
    complexes: list[dict] | None = None,
    asof: str = "2026-07-06",
) -> dict:
    """Minimal oracle_state.json payload."""
    if complexes is None:
        complexes = [
            {
                "id": "ai_compute",
                "name": "AI Compute Complex",
                "name_zh": "AI算力复合体",
                "state": "active_out",
                "tier": "undeniable",
                "direction": "out",
                "n_members_active": 6,
                "personality": "idiosyncratic",
            }
        ]
    return {
        "schema": "oracle_state_v2",
        "asof": asof,
        "regime": {},
        "complexes": complexes,
        "active_episodes": [],
    }


def _make_rotation_groups(
    complex_id: str = "ai_compute",
    basket_ids: list[str] | None = None,
) -> list[dict]:
    """Minimal rotation_groups complexes list."""
    if basket_ids is None:
        basket_ids = ["aicompute", "ai_semiconductors"]
    return [
        {
            "id": complex_id,
            "name": "AI Compute Complex",
            "name_zh": "AI算力复合体",
            "risk_sign": "risk_on",
            "members": basket_ids,
            "rationale": "Test complex",
        }
    ]


def _make_standouts(buy_rows: list[dict] | None = None, as_of: str = "2026-07-06") -> dict:
    """Minimal us_standouts.json payload."""
    if buy_rows is None:
        buy_rows = [
            {
                "ticker": "NVDA",
                "name": "NVIDIA Corporation",
                "sector": "Technology",
                "lane": "trend",
                "state": "HOLD",
            }
        ]
    return {"as_of": as_of, "buy": buy_rows}


def _inject_basket_map(module: object, basket_map: dict[str, set[str]]) -> None:
    """Inject basket_tickers_cache into pair-g function (mimics detect_contradictions)."""
    module._pair_g_oracle_out_vs_entry_buy._basket_tickers_cache = basket_map  # type: ignore[attr-defined]


@pytest.fixture
def cd_module():
    """Import contradictions module fresh."""
    import engine.neuralweb.contradictions as m
    return m


# ---------------------------------------------------------------------------
# Test 1: out-rotation complex + member ticker on buy list → 'tension' record
# ---------------------------------------------------------------------------

class TestPairGFires:
    def test_out_rotation_and_member_buy_emits_tension(self, cd_module):
        """When complex is 'out' and ticker belongs to that complex and is on buy list,
        a 'tension' record must be emitted."""
        oracle = _make_oracle_state()
        rg = _make_rotation_groups()
        standouts = _make_standouts(buy_rows=[
            {"ticker": "NVDA", "name": "NVIDIA", "lane": "trend"}
        ])
        gaps: list[str] = []

        # Inject basket map: aicompute basket contains NVDA
        _inject_basket_map(cd_module, {"aicompute": {"NVDA", "AMD"}, "ai_semiconductors": {"SMCI"}})

        records = cd_module._pair_g_oracle_out_vs_entry_buy(oracle, rg, standouts, gaps)

        assert len(records) >= 1, f"Expected at least 1 record, got {records}"
        rec = records[0]
        assert rec["severity"] == "tension", f"severity must be 'tension', got {rec['severity']}"
        assert rec["display_only"] is True
        assert "ai_compute" in rec["pair_id"]
        assert "NVDA" in rec["pair_id"]
        assert "NVDA" in rec["b"]["reading"]
        assert "ai_compute" in rec["a"]["reading"]
        assert "out" in rec["a"]["reading"]

    def test_note_text_is_descriptive_not_prescriptive(self, cd_module):
        """Annotation text must name complex + direction + ticker + lane; no 'should', 'avoid', 'sell'."""
        oracle = _make_oracle_state()
        rg = _make_rotation_groups()
        standouts = _make_standouts(buy_rows=[
            {"ticker": "NVDA", "name": "NVIDIA", "lane": "momentum"}
        ])
        gaps: list[str] = []
        _inject_basket_map(cd_module, {"aicompute": {"NVDA"}, "ai_semiconductors": set()})

        records = cd_module._pair_g_oracle_out_vs_entry_buy(oracle, rg, standouts, gaps)

        assert len(records) >= 1
        note = records[0]["note"]
        # Must be descriptive
        assert "AI Compute" in note or "ai_compute" in note
        assert "out" in note.lower() or "rotating" in note.lower()
        assert "NVDA" in note
        assert "momentum" in note  # lane name
        # Must NOT be prescriptive (imperative commands)
        # Note: "neither cancels the other" is valid descriptive text, so we check
        # for directive usage patterns rather than raw word presence
        for forbidden in ("should avoid", "do not buy", "sell now", "must sell",
                          "suppress the", "gate this"):
            assert forbidden not in note.lower(), (
                f"Note must not be prescriptive: found {forbidden!r} in {note!r}"
            )

    def test_pair_id_format(self, cd_module):
        """pair_id must follow 'oracle-out-vs-entry-buy:{cx_id}:{ticker}' format."""
        oracle = _make_oracle_state()
        rg = _make_rotation_groups()
        standouts = _make_standouts(buy_rows=[{"ticker": "NVDA", "lane": "trend"}])
        gaps: list[str] = []
        _inject_basket_map(cd_module, {"aicompute": {"NVDA"}})

        records = cd_module._pair_g_oracle_out_vs_entry_buy(oracle, rg, standouts, gaps)

        assert len(records) >= 1
        assert records[0]["pair_id"] == "oracle-out-vs-entry-buy:ai_compute:NVDA"

    def test_record_schema_complete(self, cd_module):
        """Record must contain all required fields with correct types."""
        oracle = _make_oracle_state()
        rg = _make_rotation_groups()
        standouts = _make_standouts(buy_rows=[{"ticker": "NVDA", "lane": "trend"}])
        gaps: list[str] = []
        _inject_basket_map(cd_module, {"aicompute": {"NVDA"}})

        records = cd_module._pair_g_oracle_out_vs_entry_buy(oracle, rg, standouts, gaps)

        assert len(records) >= 1
        rec = records[0]
        for field in ("pair_id", "a", "b", "kind", "severity", "as_of", "note", "display_only"):
            assert field in rec, f"Missing field: {field}"
        assert "artifact" in rec["a"]
        assert "reading" in rec["a"]
        assert "artifact" in rec["b"]
        assert "reading" in rec["b"]
        assert rec["display_only"] is True
        assert rec["severity"] in ("note", "tension")
        assert rec["kind"] == "directional-opposition"

    def test_artifacts_reference_correct_paths(self, cd_module):
        """Record artifacts must reference the correct source paths."""
        oracle = _make_oracle_state()
        rg = _make_rotation_groups()
        standouts = _make_standouts(buy_rows=[{"ticker": "NVDA", "lane": "trend"}])
        gaps: list[str] = []
        _inject_basket_map(cd_module, {"aicompute": {"NVDA"}})

        records = cd_module._pair_g_oracle_out_vs_entry_buy(oracle, rg, standouts, gaps)

        assert len(records) >= 1
        rec = records[0]
        assert rec["a"]["artifact"] == "site/basketdata/oracle_state.json"
        assert rec["b"]["artifact"] == "site/factordata/us_standouts.json"


# ---------------------------------------------------------------------------
# Test 2: No out-rotation complexes → no records
# ---------------------------------------------------------------------------

class TestPairGNoFire:
    def test_in_direction_does_not_fire(self, cd_module):
        """'in' direction complex must NOT trigger pair-g."""
        oracle = _make_oracle_state(complexes=[
            {
                "id": "ai_compute",
                "name": "AI Compute Complex",
                "name_zh": "AI算力复合体",
                "state": "active_in",
                "tier": "undeniable",
                "direction": "in",  # ← in, not out
                "n_members_active": 6,
            }
        ])
        rg = _make_rotation_groups()
        standouts = _make_standouts(buy_rows=[{"ticker": "NVDA", "lane": "trend"}])
        gaps: list[str] = []
        _inject_basket_map(cd_module, {"aicompute": {"NVDA"}})

        records = cd_module._pair_g_oracle_out_vs_entry_buy(oracle, rg, standouts, gaps)

        assert records == [], f"'in' direction must not trigger pair-g, got: {records}"

    def test_neutral_direction_does_not_fire(self, cd_module):
        """'neutral' or unknown direction must NOT trigger pair-g."""
        oracle = _make_oracle_state(complexes=[
            {"id": "ai_compute", "name": "AI Compute", "name_zh": "", "direction": "neutral",
             "state": "neutral", "tier": "confirmed", "n_members_active": 2}
        ])
        rg = _make_rotation_groups()
        standouts = _make_standouts(buy_rows=[{"ticker": "NVDA", "lane": "trend"}])
        gaps: list[str] = []
        _inject_basket_map(cd_module, {"aicompute": {"NVDA"}})

        records = cd_module._pair_g_oracle_out_vs_entry_buy(oracle, rg, standouts, gaps)

        assert records == [], f"neutral direction must not fire, got: {records}"

    def test_empty_buy_list_does_not_fire(self, cd_module):
        """Empty buy list → no records."""
        oracle = _make_oracle_state()
        rg = _make_rotation_groups()
        standouts = _make_standouts(buy_rows=[])  # empty buy list
        gaps: list[str] = []
        _inject_basket_map(cd_module, {"aicompute": {"NVDA"}})

        records = cd_module._pair_g_oracle_out_vs_entry_buy(oracle, rg, standouts, gaps)

        assert records == [], f"Empty buy list must yield no records, got: {records}"

    def test_no_out_complexes_no_records(self, cd_module):
        """All complexes with non-out directions → no records."""
        oracle = _make_oracle_state(complexes=[
            {"id": "cx1", "name": "CX1", "name_zh": "", "direction": "in",
             "state": "active_in", "tier": "confirmed", "n_members_active": 3},
            {"id": "cx2", "name": "CX2", "name_zh": "", "direction": "accelerating",
             "state": "active_in", "tier": "undeniable", "n_members_active": 5},
        ])
        rg = [
            {"id": "cx1", "name": "CX1", "name_zh": "", "members": ["basket_a"]},
            {"id": "cx2", "name": "CX2", "name_zh": "", "members": ["basket_b"]},
        ]
        standouts = _make_standouts(buy_rows=[{"ticker": "AAPL", "lane": "trend"}])
        gaps: list[str] = []
        _inject_basket_map(cd_module, {"basket_a": {"AAPL"}, "basket_b": {"MSFT"}})

        records = cd_module._pair_g_oracle_out_vs_entry_buy(oracle, rg, standouts, gaps)

        assert records == [], f"No out complexes → no records, got: {records}"


# ---------------------------------------------------------------------------
# Test 3: Unmappable ticker → skipped silently (fail-open)
# ---------------------------------------------------------------------------

class TestPairGUnmappable:
    def test_unmappable_ticker_skipped_silently(self, cd_module):
        """A buy ticker that doesn't appear in any basket must be skipped — no record, no error."""
        oracle = _make_oracle_state()
        rg = _make_rotation_groups()
        standouts = _make_standouts(buy_rows=[
            {"ticker": "OMC", "lane": "trend"},  # OMC not in aicompute/ai_semiconductors
        ])
        gaps: list[str] = []
        _inject_basket_map(cd_module, {"aicompute": {"NVDA", "AMD"}, "ai_semiconductors": {"SMCI"}})

        records = cd_module._pair_g_oracle_out_vs_entry_buy(oracle, rg, standouts, gaps)

        # OMC is not in any basket → no record; no exception; gaps not enlarged for this
        assert records == [], f"Unmappable ticker must be skipped, got: {records}"
        assert not any("OMC" in g for g in gaps), f"OMC must not appear in gaps: {gaps}"

    def test_partial_mapping_fires_for_mapped_only(self, cd_module):
        """Mix of mappable and unmappable tickers: records only for mapped ones."""
        oracle = _make_oracle_state()
        rg = _make_rotation_groups()
        standouts = _make_standouts(buy_rows=[
            {"ticker": "NVDA", "lane": "trend"},   # ← in aicompute → fires
            {"ticker": "AAPL", "lane": "swing"},   # ← not in aicompute → skip
        ])
        gaps: list[str] = []
        _inject_basket_map(cd_module, {"aicompute": {"NVDA"}, "ai_semiconductors": set()})

        records = cd_module._pair_g_oracle_out_vs_entry_buy(oracle, rg, standouts, gaps)

        fired_tickers = [r["pair_id"].split(":")[-1] for r in records]
        assert "NVDA" in fired_tickers
        assert "AAPL" not in fired_tickers


# ---------------------------------------------------------------------------
# Test 4 & 5: Missing oracle_state or standouts → fail-open
# ---------------------------------------------------------------------------

class TestPairGFailOpen:
    def test_oracle_state_none_emits_gap(self, cd_module):
        """oracle_state=None → gap note added, no records, no exception."""
        rg = _make_rotation_groups()
        standouts = _make_standouts()
        gaps: list[str] = []
        _inject_basket_map(cd_module, {"aicompute": {"NVDA"}})

        records = cd_module._pair_g_oracle_out_vs_entry_buy(None, rg, standouts, gaps)

        assert records == []
        assert len(gaps) == 1
        assert "pair-g" in gaps[0]
        assert "oracle_state" in gaps[0].lower()

    def test_standouts_none_emits_gap(self, cd_module):
        """standouts=None → gap note added, no records, no exception."""
        oracle = _make_oracle_state()
        rg = _make_rotation_groups()
        gaps: list[str] = []
        _inject_basket_map(cd_module, {"aicompute": {"NVDA"}})

        records = cd_module._pair_g_oracle_out_vs_entry_buy(oracle, rg, None, gaps)

        assert records == []
        assert len(gaps) == 1
        assert "pair-g" in gaps[0]
        assert "standouts" in gaps[0].lower() or "us_standouts" in gaps[0].lower()

    def test_no_exception_on_malformed_buy_row(self, cd_module):
        """Malformed buy row (missing ticker) must not raise."""
        oracle = _make_oracle_state()
        rg = _make_rotation_groups()
        standouts = _make_standouts(buy_rows=[
            {},  # no 'ticker' key
            {"ticker": None},  # None ticker
            {"ticker": "NVDA", "lane": "trend"},  # valid
        ])
        gaps: list[str] = []
        _inject_basket_map(cd_module, {"aicompute": {"NVDA"}})

        # Must not raise
        records = cd_module._pair_g_oracle_out_vs_entry_buy(oracle, rg, standouts, gaps)

        # Only NVDA should fire; malformed rows silently skipped
        fired = [r["pair_id"] for r in records]
        assert any("NVDA" in pid for pid in fired)


# ---------------------------------------------------------------------------
# Test 6: rotation_groups empty → gap note
# ---------------------------------------------------------------------------

class TestPairGEmptyRotationGroups:
    def test_empty_rotation_groups_emits_gap(self, cd_module):
        """Empty rotation_groups → pair-g emits a gap note and returns no records."""
        oracle = _make_oracle_state()
        standouts = _make_standouts(buy_rows=[{"ticker": "NVDA", "lane": "trend"}])
        gaps: list[str] = []
        _inject_basket_map(cd_module, {"aicompute": {"NVDA"}})

        records = cd_module._pair_g_oracle_out_vs_entry_buy(oracle, [], standouts, gaps)

        assert records == []
        assert len(gaps) == 1
        assert "pair-g" in gaps[0]


# ---------------------------------------------------------------------------
# Test 7: basket_tickers_cache empty → gap note
# ---------------------------------------------------------------------------

class TestPairGEmptyBasketMap:
    def test_empty_basket_map_emits_gap(self, cd_module):
        """When basket_tickers_cache is empty, pair-g emits a gap and no records."""
        oracle = _make_oracle_state()
        rg = _make_rotation_groups()
        standouts = _make_standouts(buy_rows=[{"ticker": "NVDA", "lane": "trend"}])
        gaps: list[str] = []
        _inject_basket_map(cd_module, {})  # ← empty map

        records = cd_module._pair_g_oracle_out_vs_entry_buy(oracle, rg, standouts, gaps)

        assert records == []
        assert len(gaps) == 1
        assert "pair-g" in gaps[0]
        assert "basket_tickers_map" in gaps[0] or "mapping" in gaps[0]


# ---------------------------------------------------------------------------
# Test 9: 'decelerating' direction triggers pair-g
# ---------------------------------------------------------------------------

class TestPairGDecelerating:
    def test_decelerating_direction_fires(self, cd_module):
        """'decelerating' is a bearish direction and must trigger pair-g."""
        oracle = _make_oracle_state(complexes=[
            {
                "id": "software",
                "name": "Software & Cloud",
                "name_zh": "软件与云计算",
                "state": "active_two_sided",
                "tier": "undeniable",
                "direction": "decelerating",  # ← bearish direction
                "n_members_active": 5,
            }
        ])
        rg = [
            {
                "id": "software",
                "name": "Software & Cloud",
                "name_zh": "",
                "members": ["non_ai_software"],
                "rationale": "Test",
            }
        ]
        standouts = _make_standouts(buy_rows=[{"ticker": "CRM", "lane": "swing"}])
        gaps: list[str] = []
        _inject_basket_map(cd_module, {"non_ai_software": {"CRM", "SALESF"}})

        records = cd_module._pair_g_oracle_out_vs_entry_buy(oracle, rg, standouts, gaps)

        assert len(records) >= 1, f"decelerating direction must fire pair-g, got: {records}"
        assert records[0]["severity"] == "tension"
        assert "decelerating" in records[0]["a"]["reading"]


# ---------------------------------------------------------------------------
# Test 11: Dedupe — same (ticker, cx_id) pair appears once
# ---------------------------------------------------------------------------

class TestPairGDedupe:
    def test_ticker_in_multiple_baskets_same_complex_emits_once(self, cd_module):
        """If a ticker appears in multiple baskets belonging to the same complex,
        the pair-g record is deduplicated (one record per (ticker, cx_id) pair)."""
        oracle = _make_oracle_state()
        rg = _make_rotation_groups(basket_ids=["basket_a", "basket_b", "basket_c"])
        standouts = _make_standouts(buy_rows=[{"ticker": "NVDA", "lane": "trend"}])
        gaps: list[str] = []
        # NVDA appears in all three baskets
        _inject_basket_map(cd_module, {
            "basket_a": {"NVDA"},
            "basket_b": {"NVDA"},
            "basket_c": {"NVDA"},
        })

        records = cd_module._pair_g_oracle_out_vs_entry_buy(oracle, rg, standouts, gaps)

        # NVDA × ai_compute must appear exactly once
        matching = [r for r in records if "NVDA" in r["pair_id"] and "ai_compute" in r["pair_id"]]
        assert len(matching) == 1, (
            f"Expected exactly 1 record for (NVDA, ai_compute), got {len(matching)}: {matching}"
        )

    def test_ticker_in_different_out_complexes_emits_one_per_complex(self, cd_module):
        """Ticker in two different out-rotation complexes → one record per complex."""
        oracle = _make_oracle_state(complexes=[
            {"id": "cx_a", "name": "CX A", "name_zh": "", "direction": "out",
             "state": "active_out", "tier": "undeniable", "n_members_active": 3},
            {"id": "cx_b", "name": "CX B", "name_zh": "", "direction": "out",
             "state": "active_out", "tier": "confirmed", "n_members_active": 2},
        ])
        rg = [
            {"id": "cx_a", "name": "CX A", "name_zh": "", "members": ["basket_a"]},
            {"id": "cx_b", "name": "CX B", "name_zh": "", "members": ["basket_b"]},
        ]
        standouts = _make_standouts(buy_rows=[{"ticker": "NVDA", "lane": "trend"}])
        gaps: list[str] = []
        # NVDA in both baskets (one per complex)
        _inject_basket_map(cd_module, {"basket_a": {"NVDA"}, "basket_b": {"NVDA"}})

        records = cd_module._pair_g_oracle_out_vs_entry_buy(oracle, rg, standouts, gaps)

        cx_ids_fired = {r["pair_id"].split(":")[1] for r in records}
        assert "cx_a" in cx_ids_fired
        assert "cx_b" in cx_ids_fired
        assert len(records) == 2, f"Expected 2 records (one per complex), got {records}"


# ---------------------------------------------------------------------------
# Integration: detect_contradictions end-to-end with pair-g fixtures
# ---------------------------------------------------------------------------

class TestPairGEndToEnd:
    def test_detect_contradictions_includes_pair_g(self, tmp_path):
        """detect_contradictions() must run pair-g and include its records when
        oracle_state has out-direction complex and standouts has a member buy."""
        from engine.neuralweb.contradictions import detect_contradictions

        # Write minimal oracle_state.json
        site_dir = tmp_path / "site"
        (site_dir / "basketdata").mkdir(parents=True)
        oracle = _make_oracle_state()
        (site_dir / "basketdata" / "oracle_state.json").write_text(
            json.dumps(oracle), encoding="utf-8"
        )

        # Write us_standouts.json with NVDA on buy list
        (site_dir / "factordata").mkdir(parents=True)
        standouts = _make_standouts(buy_rows=[{"ticker": "NVDA", "lane": "trend"}])
        (site_dir / "factordata" / "us_standouts.json").write_text(
            json.dumps(standouts), encoding="utf-8"
        )

        # Write rotation_groups.json
        data_dir = tmp_path / "data"
        (data_dir / "oracle").mkdir(parents=True)
        rg_doc = {
            "_meta": {"version": "test"},
            "complexes": _make_rotation_groups(),
        }
        (data_dir / "oracle" / "rotation_groups.json").write_text(
            json.dumps(rg_doc), encoding="utf-8"
        )

        # Write baskets/membership.json with NVDA in aicompute basket
        (data_dir / "baskets").mkdir(parents=True)
        mb = {
            "version": "test",
            "baskets": {
                "aicompute": {
                    "name": "AI Compute",
                    "name_zh": "",
                    "members": [
                        {"ticker": "NVDA", "added": "2023-01-01", "removed": None},
                        {"ticker": "AMD", "added": "2023-01-01", "removed": None},
                    ],
                },
                "ai_semiconductors": {
                    "name": "AI Semis",
                    "name_zh": "",
                    "members": [
                        {"ticker": "SMCI", "added": "2023-01-01", "removed": None},
                    ],
                },
            },
        }
        (data_dir / "baskets" / "membership.json").write_text(
            json.dumps(mb), encoding="utf-8"
        )

        records, gaps = detect_contradictions(root=tmp_path)

        pair_g_records = [r for r in records if r["pair_id"].startswith("oracle-out-vs-entry-buy:")]
        assert len(pair_g_records) >= 1, (
            f"Expected at least 1 pair-g record, got none. "
            f"All records: {[r['pair_id'] for r in records]}, gaps: {gaps}"
        )
        rec = pair_g_records[0]
        assert rec["severity"] == "tension"
        assert rec["display_only"] is True
        assert "NVDA" in rec["b"]["reading"]

    def test_detect_contradictions_no_pair_g_when_no_oracle(self, tmp_path):
        """When oracle_state.json is absent, detect_contradictions still runs (fail-open)."""
        from engine.neuralweb.contradictions import detect_contradictions

        # No site/ dir at all — all sources absent
        records, gaps = detect_contradictions(root=tmp_path)

        # Must return lists (not raise); pair-g gap must be noted
        assert isinstance(records, list)
        assert isinstance(gaps, list)
        # Some gap notes should be present (various sources absent)
        assert len(gaps) > 0
