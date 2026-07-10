"""tests/test_stocktable_hk_data.py — W8-G HK table view serialization tests.

Validates:
  1. Serialization completeness: every configured HK column key is present (or None)
     on every row produced by the Jinja data-block logic.
  2. No ordering mutation: the row array order is byte-identical to the input order
     from setups.buy.
  3. HK-specific field access patterns (nested .conviction.score, .southbound.accum_z,
     etc.) are null-safe and produce the correct flat field.
  4. No mcap/cap_bucket/days_since_signal fabrication: absent fields stay absent/None.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ── HK table column keys (mirrors the JS cols schema in hk.html.j2 W8-G block) ──

HK_TABLE_ROW_KEYS = [
    "ticker",
    "name",
    "name_zh",       # bilingual name for ZH users
    "sector",
    "sector_zh",
    "price",
    "off_high",
    "conviction",    # flattened from conviction.score
    "alpha",
    "edge_z",
    "sb_z",          # flattened from southbound.accum_z
    "sb_own",        # flattened from southbound.own_pct
    "ah_z",          # flattened from ah_value.z
    "ah_cheap",      # flattened from ah_value.cheap (bool)
    "group",
    "align_tier",
    "washout_2w",    # bool
    # NOTE: dir/entry_status/buy_zone_lo/buy_zone_hi removed — dead payload (no column consumes them)
]

# Keys that must NOT be fabricated on HK rows (CN-specific enrichment or removed dead payload)
HK_ABSENT_KEYS = ["mcap", "cap_bucket", "days_since_signal", "stage", "zone", "tier",
                  "dir", "entry_status", "buy_zone_lo", "buy_zone_hi"]


def _serialize_hk_row(n: dict) -> dict:
    """Mirror the Jinja2 dict construction in hk.html.j2 W8-G data block.
    Produces the flat row dict exactly as the template does, null-safe.

    Removed from payload (dead fields — no column consumes them):
      dir, entry_status, buy_zone_lo, buy_zone_hi

    Added:
      name_zh — bilingual Chinese company name for ZH-mode users
    """
    conv = n.get("conviction") or {}
    sb = n.get("southbound") or {}
    ah = n.get("ah_value") or {}
    return {
        "ticker":       n.get("ticker", ""),
        "name":         n.get("name") or "",
        "name_zh":      n.get("name_zh") or "",
        "sector":       n.get("sector") or "",
        "sector_zh":    n.get("sector_zh") or "",
        "price":        n.get("price"),
        "off_high":     n.get("off_high"),
        "conviction":   conv.get("score"),
        "alpha":        n.get("alpha"),
        "edge_z":       n.get("edge_z"),
        "sb_z":         sb.get("accum_z"),
        "sb_own":       sb.get("own_pct"),
        "ah_z":         ah.get("z"),
        "ah_cheap":     bool(ah.get("cheap")),
        "group":        n.get("group") or "setting_up",
        "align_tier":   n.get("align_tier") or "",
        "washout_2w":   bool(n.get("washout_2w")),
    }


# ── fixtures ──────────────────────────────────────────────────────────────────

def _make_hk_buy_row(ticker: str = "0700.HK", group: str = "entry_open") -> dict:
    """A realistic HK setups.buy row with all optional sub-dicts present."""
    return {
        "ticker": ticker,
        "name": f"{ticker} Name",
        "name_zh": f"{ticker} 名称",
        "sector": "Technology",
        "sector_zh": "科技",
        "price": 345.60,
        "off_high": -18.2,
        "alpha": 1.23,
        "edge_z": 0.88,
        "group": group,
        "align_tier": "aligned",
        "dir": "up",           # source field (consumed by grid cards), not serialized to table row
        "washout_2w": True,
        "conviction": {
            "score": 74,
            "verdict": "Bullish edge",
            "verdict_zh": "看涨优势",
            "composite_z": 0.91,
        },
        "southbound": {
            "accum_z": 1.42,
            "own_pct": 8.3,
            "label": "accumulating",
        },
        "ah_value": {
            "z": 2.11,
            "cheap": True,
            "premium_pct": -15.0,
        },
        "entry_signal": {
            "status": "buy_now",
            "headline": "Buy now",
            "headline_zh": "立即买入",
            "buy_zone": {"low": 340.0, "high": 348.0, "pct_from_spot": -1.5},
        },
    }


def _make_hk_buy_row_sparse(ticker: str = "0001.HK") -> dict:
    """A minimal HK buy row — no sub-dicts (conviction/southbound/ah_value/entry_signal absent)."""
    return {
        "ticker": ticker,
        "name": "Minimal Corp",
        "sector": "Utilities",
        "price": 50.0,
        "group": "setting_up",
        "dir": "flat",
    }


# ── 1. serialization completeness ─────────────────────────────────────────────

class TestHKSerializationCompleteness:
    def test_full_row_has_all_keys(self):
        """A full HK row serializes with all expected column keys."""
        row = _make_hk_buy_row()
        ser = _serialize_hk_row(row)
        for k in HK_TABLE_ROW_KEYS:
            assert k in ser, f"Key '{k}' missing from serialized HK row"

    def test_sparse_row_has_all_keys_with_none(self):
        """A sparse HK row (absent sub-dicts) serializes with all keys; missing fields are None or falsy."""
        row = _make_hk_buy_row_sparse()
        ser = _serialize_hk_row(row)
        for k in HK_TABLE_ROW_KEYS:
            assert k in ser, f"Key '{k}' missing from sparse serialized HK row"
        # nested fields default to None when sub-dict absent
        assert ser["conviction"] is None
        assert ser["sb_z"] is None
        assert ser["sb_own"] is None
        assert ser["ah_z"] is None
        assert ser["ah_cheap"] is False  # bool(None) = False
        assert ser["washout_2w"] is False
        assert ser["name_zh"] == ""

    def test_cn_fields_not_fabricated(self):
        """HK serialization must not produce CN-specific fields (mcap, cap_bucket, days_since_signal, etc.)."""
        row = _make_hk_buy_row()
        ser = _serialize_hk_row(row)
        for k in HK_ABSENT_KEYS:
            assert k not in ser, f"CN-specific field '{k}' must not appear on HK serialized row"

    def test_none_fields_json_null(self):
        """None fields serialize as JSON null, not 0 or sentinel."""
        row = _make_hk_buy_row_sparse()
        ser = _serialize_hk_row(row)
        s = json.dumps(ser, default=str)
        parsed = json.loads(s)
        assert parsed["conviction"] is None
        assert parsed["sb_z"] is None
        assert parsed["ah_z"] is None
        assert parsed["price"] is not None  # price present in sparse row

    def test_conviction_score_extracted(self):
        """conviction.score from nested dict is flattened to top-level 'conviction' key."""
        row = _make_hk_buy_row()
        ser = _serialize_hk_row(row)
        assert ser["conviction"] == 74

    def test_southbound_z_extracted(self):
        """southbound.accum_z is flattened to sb_z."""
        row = _make_hk_buy_row()
        ser = _serialize_hk_row(row)
        assert ser["sb_z"] == pytest.approx(1.42)

    def test_ah_value_extracted(self):
        """ah_value.z and ah_value.cheap are flattened."""
        row = _make_hk_buy_row()
        ser = _serialize_hk_row(row)
        assert ser["ah_z"] == pytest.approx(2.11)
        assert ser["ah_cheap"] is True

    def test_name_zh_extracted(self):
        """name_zh is present in serialized row for bilingual name column rendering."""
        row = _make_hk_buy_row()
        ser = _serialize_hk_row(row)
        assert ser["name_zh"] == "0700.HK 名称"

    def test_name_zh_absent_defaults_to_empty(self):
        """Missing name_zh field defaults to empty string (falls back to EN name in JS)."""
        row = {"ticker": "0001.HK", "name": "CK Hutchison"}
        ser = _serialize_hk_row(row)
        assert ser["name_zh"] == ""

    def test_dead_fields_absent(self):
        """dir/entry_status/buy_zone_lo/buy_zone_hi must NOT appear in serialized row (removed as dead payload)."""
        row = _make_hk_buy_row()
        ser = _serialize_hk_row(row)
        for dead in ("dir", "entry_status", "buy_zone_lo", "buy_zone_hi"):
            assert dead not in ser, f"Dead field '{dead}' must not appear in serialized HK row"

    def test_group_defaults_to_setting_up(self):
        """Missing 'group' field defaults to 'setting_up' (not None)."""
        row = {"ticker": "0001.HK", "name": "X"}
        ser = _serialize_hk_row(row)
        assert ser["group"] == "setting_up"

    def test_washout_2w_bool(self):
        """washout_2w is always a bool, never None."""
        for val in [True, False, None, 0, 1]:
            row = {"ticker": "X", "washout_2w": val}
            ser = _serialize_hk_row(row)
            assert isinstance(ser["washout_2w"], bool), f"washout_2w must be bool for input {val!r}"


# ── 2. no ordering mutation ────────────────────────────────────────────────────

class TestHKNoOrderingMutation:
    def _serialize_rows(self, rows: list[dict]) -> list[dict]:
        return [_serialize_hk_row(r) for r in rows]

    def test_buy_order_unchanged_three_rows(self):
        """Serializing a buy list must not reorder the rows."""
        rows = [
            _make_hk_buy_row("0700.HK", "entry_open"),
            _make_hk_buy_row("0005.HK", "setting_up"),
            _make_hk_buy_row("0001.HK", "setting_up"),
        ]
        ser = self._serialize_rows(rows)
        assert [r["ticker"] for r in ser] == ["0700.HK", "0005.HK", "0001.HK"]

    def test_sparse_rows_order_unchanged(self):
        """Sparse rows (no sub-dicts) must preserve order."""
        rows = [
            _make_hk_buy_row_sparse("0001.HK"),
            _make_hk_buy_row_sparse("0002.HK"),
            _make_hk_buy_row_sparse("0003.HK"),
        ]
        ser = self._serialize_rows(rows)
        assert [r["ticker"] for r in ser] == ["0001.HK", "0002.HK", "0003.HK"]

    def test_mixed_rows_order_unchanged(self):
        """Mix of full and sparse rows must preserve order."""
        rows = [
            _make_hk_buy_row("0700.HK"),
            _make_hk_buy_row_sparse("0001.HK"),
            _make_hk_buy_row("2269.HK"),
        ]
        ser = self._serialize_rows(rows)
        assert [r["ticker"] for r in ser] == ["0700.HK", "0001.HK", "2269.HK"]

    def test_single_row_order_unchanged(self):
        """A single-row list remains a single-row list."""
        rows = [_make_hk_buy_row("0981.HK")]
        ser = self._serialize_rows(rows)
        assert len(ser) == 1
        assert ser[0]["ticker"] == "0981.HK"

    def test_empty_rows_yields_empty(self):
        """An empty buy list serializes to an empty list."""
        assert self._serialize_rows([]) == []


# ── 3. HK-specific field null-safety edge cases ───────────────────────────────

class TestHKNullSafety:
    def test_empty_conviction_dict_safe(self):
        """An empty conviction dict does not raise; score returns None."""
        row = {"ticker": "X", "conviction": {}}
        ser = _serialize_hk_row(row)
        assert ser["conviction"] is None

    def test_empty_southbound_dict_safe(self):
        """An empty southbound dict does not raise; sb_z returns None."""
        row = {"ticker": "X", "southbound": {}}
        ser = _serialize_hk_row(row)
        assert ser["sb_z"] is None
        assert ser["sb_own"] is None

    def test_empty_ah_value_dict_safe(self):
        """An empty ah_value dict does not raise; ah_z/ah_cheap return None/False."""
        row = {"ticker": "X", "ah_value": {}}
        ser = _serialize_hk_row(row)
        assert ser["ah_z"] is None
        assert ser["ah_cheap"] is False

    def test_entry_signal_field_not_in_output(self):
        """entry_signal sub-dict is NOT serialized into the table row (removed as dead payload).
        Source rows may still carry it for the grid-card rendering path — that is fine."""
        row = {"ticker": "X", "entry_signal": {"status": "buy_soon",
                                                "buy_zone": {"low": 10.0, "high": 12.0}}}
        ser = _serialize_hk_row(row)
        assert "entry_status" not in ser
        assert "buy_zone_lo" not in ser
        assert "buy_zone_hi" not in ser

    def test_name_zh_empty_string_when_absent(self):
        """name_zh absent on source row → empty string in serialized row (JS falls back to EN name)."""
        row = {"ticker": "X", "name": "Test Corp"}
        ser = _serialize_hk_row(row)
        assert ser["name_zh"] == ""

    def test_ah_cheap_false_when_missing(self):
        """ah_value.cheap absent → ah_cheap = False (not None)."""
        row = {"ticker": "X", "ah_value": {"z": 0.5}}
        ser = _serialize_hk_row(row)
        assert ser["ah_cheap"] is False
        assert ser["ah_z"] == pytest.approx(0.5)

    def test_ticker_missing_defaults_to_empty(self):
        """A row without ticker gets ticker='' — does not raise."""
        row = {"name": "NoTicker Corp"}
        ser = _serialize_hk_row(row)
        assert ser["ticker"] == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
