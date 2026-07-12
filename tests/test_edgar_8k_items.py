"""Unit tests for LHB-W2b changes to collectors/edgar_8k.py.

Covers:
  (a) MATERIAL_ITEMS is exactly the 12-code set (LHB-R7 expansion)
  (b) LEGACY_VELOCITY_ITEMS is exactly the original 6 codes
  (c) _merge_events groupby-accession union: old row + new row with overlapping
      accession → single row, union items, min _first_seen, first non-null extras
  (d) brand-new accession keeps its own _first_seen
  (e) _velocity: items="2.04" contributes 0 to counts; "1.01,2.04" contributes;
      no crash on empty post-filter frames

No live network calls anywhere in this file.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collectors.edgar_8k as m8k  # noqa: E402


# ---------------------------------------------------------------------------
# (a) MATERIAL_ITEMS set — must be exactly 12 codes post-LHB-R7 expansion
# ---------------------------------------------------------------------------

class TestMaterialItems:
    EXPECTED = {"1.01", "1.02", "1.03", "2.01", "2.03", "2.04",
                "3.01", "3.02", "4.02", "5.02", "7.01", "8.01"}

    def test_exact_set(self):
        assert m8k.MATERIAL_ITEMS == self.EXPECTED

    def test_size(self):
        assert len(m8k.MATERIAL_ITEMS) == 12

    def test_new_codes_present(self):
        for code in ("1.02", "1.03", "2.04", "3.01", "3.02", "4.02"):
            assert code in m8k.MATERIAL_ITEMS, f"{code!r} missing from MATERIAL_ITEMS"

    def test_legacy_codes_still_present(self):
        for code in ("1.01", "2.01", "2.03", "5.02", "7.01", "8.01"):
            assert code in m8k.MATERIAL_ITEMS, f"{code!r} dropped from MATERIAL_ITEMS"

    def test_excluded_routine_codes_absent(self):
        # 2.02 (earnings) and 9.01 (exhibits) must never appear
        assert "2.02" not in m8k.MATERIAL_ITEMS
        assert "9.01" not in m8k.MATERIAL_ITEMS


# ---------------------------------------------------------------------------
# (b) LEGACY_VELOCITY_ITEMS — must be exactly the original 6 codes
# ---------------------------------------------------------------------------

class TestLegacyVelocityItems:
    EXPECTED = frozenset({"1.01", "2.01", "2.03", "5.02", "7.01", "8.01"})

    def test_exact_set(self):
        assert m8k.LEGACY_VELOCITY_ITEMS == self.EXPECTED

    def test_size(self):
        assert len(m8k.LEGACY_VELOCITY_ITEMS) == 6

    def test_is_frozenset(self):
        assert isinstance(m8k.LEGACY_VELOCITY_ITEMS, frozenset)

    def test_no_new_lhb_r7_codes(self):
        for code in ("1.02", "1.03", "2.04", "3.01", "3.02", "4.02"):
            assert code not in m8k.LEGACY_VELOCITY_ITEMS, (
                f"{code!r} must not appear in LEGACY_VELOCITY_ITEMS (velocity pinned pre-R7)"
            )


# ---------------------------------------------------------------------------
# Helpers used by merge + velocity tests
# ---------------------------------------------------------------------------

def _adapter(tmp_path):
    """Return an Edgar8KAdapter whose data_dir points to tmp_path."""
    adapter = m8k.Edgar8KAdapter()
    adapter._events_path = lambda: tmp_path / "edgar" / "material_8k_events.parquet"
    # Ensure parent directory exists
    (tmp_path / "edgar").mkdir(parents=True, exist_ok=True)
    return adapter


def _make_events(**overrides):
    """Build a minimal events DataFrame row."""
    base = {
        "ticker": "AAPL",
        "cik": 320193,
        "form": "8-K",
        "filing_date": "2026-01-15",
        "items": "1.01",
        "accession": "0001234567-26-000001",
    }
    base.update(overrides)
    return pd.DataFrame([base])


# ---------------------------------------------------------------------------
# (c) _merge_events groupby-union: old row (T1, ACME) + new row (T2, None)
#     → one row, items union, _first_seen=T1, counterparty=ACME
# ---------------------------------------------------------------------------

class TestMergeEventsGroupbyUnion:
    T1 = "2026-01-01T00:00:00+00:00"
    T2 = "2026-07-01T00:00:00+00:00"
    ACCESSION = "0001234567-26-000001"

    def _stored_row(self, tmp_path, items: str = "1.01"):
        """Write a pre-existing stored row with truncated items."""
        df = pd.DataFrame([{
            "ticker": "AAPL", "cik": 320193, "form": "8-K",
            "filing_date": "2026-01-01", "items": items,
            "accession": self.ACCESSION,
            "_first_seen": self.T1,
            "counterparty": "ACME",
            "amount_usd": None,
            "extraction_ok": None,
        }])
        path = tmp_path / "edgar" / "material_8k_events.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path)
        return path

    def test_items_union(self, tmp_path, monkeypatch):
        """items becomes the sorted union across duplicates — the stored row carries a
        code (5.02) ABSENT from the new row, so a take-the-new-row implementation fails
        this test (it is a true union, not a superset pass-through)."""
        self._stored_row(tmp_path, items="5.02")
        adapter = _adapter(tmp_path)

        new_df = pd.DataFrame([{
            "ticker": "AAPL", "cik": 320193, "form": "8-K",
            "filing_date": "2026-01-01", "items": "1.01,1.02",
            "accession": self.ACCESSION,
        }])
        # Monkeypatch datetime so _first_seen on new row is T2
        monkeypatch.setattr(
            m8k, "datetime",
            type("_DT", (), {
                "now": staticmethod(lambda tz=None: datetime.fromisoformat(self.T2)),
                "fromisoformat": staticmethod(datetime.fromisoformat),
            })(),
        )

        result = adapter._merge_events(new_df)
        assert len(result) == 1
        assert result.iloc[0]["items"] == "1.01,1.02,5.02"

    def test_first_seen_is_minimum(self, tmp_path, monkeypatch):
        """_first_seen is the earliest (minimum) timestamp across all duplicate rows."""
        self._stored_row(tmp_path)
        adapter = _adapter(tmp_path)

        new_df = pd.DataFrame([{
            "ticker": "AAPL", "cik": 320193, "form": "8-K",
            "filing_date": "2026-01-01", "items": "1.01,1.02",
            "accession": self.ACCESSION,
        }])
        monkeypatch.setattr(
            m8k, "datetime",
            type("_DT", (), {
                "now": staticmethod(lambda tz=None: datetime.fromisoformat(self.T2)),
                "fromisoformat": staticmethod(datetime.fromisoformat),
            })(),
        )

        result = adapter._merge_events(new_df)
        assert result.iloc[0]["_first_seen"] == self.T1

    def test_counterparty_first_nonnull_survives(self, tmp_path, monkeypatch):
        """counterparty from old row (non-null) survives even though new row has None."""
        self._stored_row(tmp_path)
        adapter = _adapter(tmp_path)

        new_df = pd.DataFrame([{
            "ticker": "AAPL", "cik": 320193, "form": "8-K",
            "filing_date": "2026-01-01", "items": "1.01,1.02",
            "accession": self.ACCESSION,
            "counterparty": None,
        }])
        monkeypatch.setattr(
            m8k, "datetime",
            type("_DT", (), {
                "now": staticmethod(lambda tz=None: datetime.fromisoformat(self.T2)),
                "fromisoformat": staticmethod(datetime.fromisoformat),
            })(),
        )

        result = adapter._merge_events(new_df)
        assert result.iloc[0]["counterparty"] == "ACME"


# ---------------------------------------------------------------------------
# (d) brand-new accession keeps its own _first_seen
# ---------------------------------------------------------------------------

class TestMergeEventsNewAccession:
    def test_new_accession_first_seen_unchanged(self, tmp_path, monkeypatch):
        """A brand-new accession not in the store gets its own _first_seen stamp."""
        adapter = _adapter(tmp_path)

        now_ts = "2026-07-12T10:00:00+00:00"
        monkeypatch.setattr(
            m8k, "datetime",
            type("_DT", (), {
                "now": staticmethod(lambda tz=None: datetime.fromisoformat(now_ts)),
                "fromisoformat": staticmethod(datetime.fromisoformat),
            })(),
        )

        new_df = pd.DataFrame([{
            "ticker": "MSFT", "cik": 789019, "form": "8-K",
            "filing_date": "2026-07-01", "items": "2.04",
            "accession": "9999999999-26-000099",
        }])
        result = adapter._merge_events(new_df)
        assert len(result) == 1
        assert result.iloc[0]["_first_seen"] == now_ts
        assert result.iloc[0]["ticker"] == "MSFT"

    def test_two_different_accessions_both_kept(self, tmp_path, monkeypatch):
        """Two distinct accessions produce two output rows."""
        adapter = _adapter(tmp_path)

        now_ts = "2026-07-12T10:00:00+00:00"
        monkeypatch.setattr(
            m8k, "datetime",
            type("_DT", (), {
                "now": staticmethod(lambda tz=None: datetime.fromisoformat(now_ts)),
                "fromisoformat": staticmethod(datetime.fromisoformat),
            })(),
        )

        new_df = pd.DataFrame([
            {"ticker": "AAPL", "cik": 320193, "form": "8-K",
             "filing_date": "2026-07-01", "items": "1.01",
             "accession": "0000000001-26-000001"},
            {"ticker": "MSFT", "cik": 789019, "form": "8-K",
             "filing_date": "2026-07-02", "items": "2.04",
             "accession": "0000000002-26-000002"},
        ])
        result = adapter._merge_events(new_df)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# (e) _velocity: new codes contribute 0; "1.01,2.04" contributes; empty-safe
# ---------------------------------------------------------------------------

class TestVelocityLegacyFilter:
    """Verify _velocity is pinned to LEGACY_VELOCITY_ITEMS."""

    def _make_mem(self, tickers):
        return {"basket_A": {"members": [{"ticker": t} for t in tickers]}}

    def _make_ev(self, rows):
        return pd.DataFrame(rows, columns=["ticker", "filing_date", "items"])

    def test_new_only_code_contributes_zero(self):
        """An event with items='2.04' (expansion-only) must NOT count in velocity."""
        adapter = m8k.Edgar8KAdapter()
        mem = self._make_mem(["AAPL"])
        # Use a recent filing date (velocity window is 60d from max)
        ev = self._make_ev([
            ("AAPL", "2026-07-10", "2.04"),
        ])
        result = adapter._velocity(ev, mem)
        # The basket should not appear at all (both recent and prior are empty)
        assert result.empty or result.iloc[0]["recent_count"] == 0

    def test_legacy_code_contributes_to_velocity(self):
        """An event with items='1.01' (legacy code) counts in velocity."""
        adapter = m8k.Edgar8KAdapter()
        mem = self._make_mem(["AAPL"])
        ev = self._make_ev([
            ("AAPL", "2026-07-10", "1.01"),
        ])
        result = adapter._velocity(ev, mem)
        assert not result.empty
        assert result.iloc[0]["recent_count"] == 1

    def test_mixed_items_legacy_plus_new_contributes(self):
        """items='1.01,2.04': row contains a legacy code, so it counts."""
        adapter = m8k.Edgar8KAdapter()
        mem = self._make_mem(["AAPL"])
        ev = self._make_ev([
            ("AAPL", "2026-07-10", "1.01,2.04"),
        ])
        result = adapter._velocity(ev, mem)
        assert not result.empty
        assert result.iloc[0]["recent_count"] == 1

    def test_empty_post_filter_frame_no_crash(self):
        """When all events are expansion-only codes, _velocity returns empty DataFrame
        without raising an exception."""
        adapter = m8k.Edgar8KAdapter()
        mem = self._make_mem(["AAPL", "MSFT"])
        ev = self._make_ev([
            ("AAPL", "2026-07-10", "2.04"),
            ("MSFT", "2026-07-09", "3.01"),
            ("AAPL", "2026-07-08", "1.03"),
        ])
        # Should not crash; result should be empty (no legacy codes)
        result = adapter._velocity(ev, mem)
        assert isinstance(result, pd.DataFrame)

    def test_expansion_items_only_returns_empty(self):
        """Frame with only LHB-R7 expansion codes produces empty velocity."""
        adapter = m8k.Edgar8KAdapter()
        mem = self._make_mem(["AAPL"])
        ev = self._make_ev([
            ("AAPL", "2026-07-10", "1.02"),
            ("AAPL", "2026-07-09", "1.03"),
            ("AAPL", "2026-07-08", "2.04"),
            ("AAPL", "2026-07-07", "3.01"),
            ("AAPL", "2026-07-06", "3.02"),
            ("AAPL", "2026-07-05", "4.02"),
        ])
        result = adapter._velocity(ev, mem)
        # After filtering, ev is empty → no baskets → empty DataFrame
        assert result.empty


# ---------------------------------------------------------------------------
# (f) Cross-module pin sync: every consumer frozen on the legacy six must agree.
#     engine/altdata.material_events feeds material_8k convergence ->
#     intel_discovery._LEADING_CHANNELS scoring; its firing bar must not shift
#     from the LHB-R7 collection expansion (data-lane change != signal change).
# ---------------------------------------------------------------------------
class TestLegacyPinSync:
    def test_altdata_pin_matches_collector_pin(self):
        from engine import altdata
        assert altdata._LEGACY_8K_ITEMS == m8k.LEGACY_VELOCITY_ITEMS

    def test_pins_are_the_original_six(self):
        from engine import altdata
        assert altdata._LEGACY_8K_ITEMS == frozenset(
            {"1.01", "2.01", "2.03", "5.02", "7.01", "8.01"}
        )

    def test_material_events_ignores_expansion_only_rows(self, tmp_path, monkeypatch):
        """A ticker with two expansion-only 8-Ks (3.01 + 2.04) must NOT reach the
        count>=2 convergence bar — pre-expansion those codes were not collected at all."""
        import pandas as pd
        from engine import altdata
        df = pd.DataFrame([
            {"ticker": "XYZ", "cik": 1, "form": "8-K", "filing_date": "2026-07-10",
             "items": "3.01", "accession": "a-1", "_first_seen": "2026-07-10T00:00:00+00:00"},
            {"ticker": "XYZ", "cik": 1, "form": "8-K", "filing_date": "2026-07-09",
             "items": "2.04", "accession": "a-2", "_first_seen": "2026-07-09T00:00:00+00:00"},
            {"ticker": "ABC", "cik": 2, "form": "8-K", "filing_date": "2026-07-10",
             "items": "1.01,2.04", "accession": "a-3", "_first_seen": "2026-07-10T00:00:00+00:00"},
        ])
        p = tmp_path / "edgar"
        p.mkdir(parents=True)
        df.to_parquet(p / "material_8k_events.parquet")
        monkeypatch.setattr(altdata.config, "data_dir", lambda: tmp_path)
        monkeypatch.setattr(altdata, "_now", lambda: pd.Timestamp("2026-07-11"))
        rows = altdata.material_events(window_days=30)
        by_ticker = {r["ticker"]: r for r in rows}
        assert "XYZ" not in by_ticker, "expansion-only rows must not count"
        assert by_ticker["ABC"]["count"] == 1
        assert "2.04" not in by_ticker["ABC"]["items"], "display items pinned to legacy"
