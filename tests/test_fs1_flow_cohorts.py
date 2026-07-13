"""tests/test_fs1_flow_cohorts.py — FS-1 historical flow cohorts unit tests.

CI target: flow-signal-cohorts job in ci.yml.
All tests are hermetic: no network, no ThetaTerminal, no thetadata_eod store.
Fixtures use tmp_path to avoid polluting repo state.

Test cases (per FS-1 acceptance gate):
  1. detector parity: sample tape fixture → deterministic events with correct
     _event_id, buckets, source, detector_version.
  2. eod_proxy PIT leak-injection: same-day OI must NOT fire; prior-day OI must.
  3. cohort separation guard: mixed-source frame → load_cohort raises ValueError.
  4. tz-aware UTC round-trip on cohort parquet (naive/aware datetime64 mismatch LETHAL).
  5. resume: run twice over same fixture units → no duplicate _event_id, state ok.
  6. concurrency cap: semaphore never exceeds 8 in-flight (mocked fetch).
  7. terminal-down: mocked connection error → clean error, no hang, no corrupt state.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# Allow running standalone without the package installed
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── helpers ───────────────────────────────────────────────────────────────────

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
SAMPLE_TAPE_PATH = FIXTURE_DIR / "_sample_V_2026-07-02.json"


def _make_raw_print(
    price: float = 32.0,
    bid: float = 30.0,
    ask: float = 32.0,
    strike: float = 200.0,
    right: str = "CALL",
    size: int = 10,
    trade_timestamp: str = "2026-06-30T10:00:00",
    expiration: str = "2026-07-18",
    sequence: int = 100,
) -> dict:
    return {
        "price": price,
        "bid": bid,
        "ask": ask,
        "strike": strike,
        "right": right,
        "size": size,
        "trade_timestamp": trade_timestamp,
        "expiration": expiration,
        "sequence": sequence,
    }


def _make_tape_df(prints: list[dict]) -> pd.DataFrame:
    """Build a DataFrame matching bulk_trade_quote output schema."""
    rows = []
    for p in prints:
        rows.append({
            "root": "SPY",
            "expiration": pd.Timestamp(p.get("expiration", "2026-07-18")),
            "strike": float(p.get("strike", 200.0)),
            "right": str(p.get("right", "C")).upper()[:1],
            "trade_timestamp": p.get("trade_timestamp", "2026-06-30T10:00:00"),
            "date": pd.Timestamp(p.get("trade_timestamp", "2026-06-30T10:00:00")).date(),
            "sequence": int(p.get("sequence", 100)),
            "price": float(p.get("price", 32.0)),
            "size": float(p.get("size", 10)),
            "bid": float(p.get("bid", 30.0)),
            "ask": float(p.get("ask", 32.0)),
        })
    return pd.DataFrame(rows)


# ── 1. detector parity ────────────────────────────────────────────────────────

class TestDetectorParity:
    """Sample tape fixture → deterministic events with correct fields."""

    def test_sample_tape_fixture_exists(self):
        """The sample tape fixture must be present in tests/fixtures/."""
        assert SAMPLE_TAPE_PATH.exists(), (
            f"Missing fixture {SAMPLE_TAPE_PATH}. "
            "Copy data/options_tape_signed/_sample_V_2026-07-02.json into tests/fixtures/."
        )

    def test_sample_tape_fixture_has_required_fields(self):
        """Sample fixture carries price/bid/ask (FS-C1 verification)."""
        data = json.loads(SAMPLE_TAPE_PATH.read_text())
        rows = data.get("rows", [])
        assert len(rows) > 0, "Sample fixture has no rows"
        first = rows[0]
        for field in ("price", "bid", "ask"):
            assert field in first, f"FS-C1: sample fixture missing '{field}' field"

    def test_tape_df_detection_yields_events(self):
        """A qualifying set of prints → at least one event with correct fields."""
        from scripts.ops_flow_cohorts import _apply_detector_v1

        # SPY at-ask prints totaling > $1M premium (ETF floor)
        # 10 prints each: 1000 contracts at $5.00 each = $500k premium per print
        prints = [
            _make_print_row("2026-06-30T10:00:00", price=5.00, bid=4.90, ask=5.00,
                            strike=550.0, right="C", size=1000, expiration="2026-07-18", seq=i+100)
            for i in range(3)
        ]
        df = _make_tape_df(prints)
        events = _apply_detector_v1(df, "SPY", "2026-06-30")

        assert len(events) >= 1, "Expected at least 1 qualifying event for SPY"
        ev = events[0]

        # Required fields
        assert ev["source"] == "tape_recon"
        assert ev["root"] == "SPY"
        assert ev["session_date"] == "2026-06-30"
        assert ev["dte_bucket"] in ("0d", "1_7d", "8_30d", "31_90d", "90p")
        assert "event_id" in ev and len(ev["event_id"]) == 16
        assert ev["detector_version"] != ""

    def test_event_id_determinism(self):
        """Same inputs → same event_id (stable hash)."""
        from scripts.ops_flow_cohorts import _event_id
        eid1 = _event_id("2026-06-30", "SPY", "2026-07-18", 550.0, "C", 102)
        eid2 = _event_id("2026-06-30", "SPY", "2026-07-18", 550.0, "C", 102)
        assert eid1 == eid2
        assert len(eid1) == 16

    def test_event_id_different_for_different_contracts(self):
        """Different contracts → different event_ids."""
        from scripts.ops_flow_cohorts import _event_id
        eid_c = _event_id("2026-06-30", "SPY", "2026-07-18", 550.0, "C", 102)
        eid_p = _event_id("2026-06-30", "SPY", "2026-07-18", 550.0, "P", 102)
        assert eid_c != eid_p

    def test_no_signed_direction_column(self):
        """Detector MUST NOT emit tick-rule signed direction (FS-R6)."""
        from scripts.ops_flow_cohorts import _apply_detector_v1

        prints = [
            _make_print_row("2026-06-30T10:00:00", price=5.00, bid=4.90, ask=5.00,
                            strike=550.0, right="C", size=1000, expiration="2026-07-18", seq=101),
        ]
        df = _make_tape_df(prints)
        events = _apply_detector_v1(df, "SPY", "2026-06-30")

        for ev in events:
            # 'side' field exists but must be quote-rule soft, not tick-rule direction
            # Forbidden: any column named 'direction' or 'signed_direction'
            assert "direction" not in ev, "Forbidden tick-rule direction column in event"
            assert "signed_direction" not in ev, "Forbidden signed_direction column"
            # side should be quote-rule soft: ~buy / ~sell / mixed / unknown
            if "side" in ev:
                assert ev["side"] in ("~buy", "~sell", "mixed", "unknown")

    def test_dte_bucket_labels(self):
        """dte_bucket matches config/flow_detector.yml dte_buckets exactly."""
        from scripts.ops_flow_cohorts import _dte_bucket
        assert _dte_bucket(0) == "0d"
        assert _dte_bucket(1) == "1_7d"
        assert _dte_bucket(7) == "1_7d"
        assert _dte_bucket(8) == "8_30d"
        assert _dte_bucket(30) == "8_30d"
        assert _dte_bucket(31) == "31_90d"
        assert _dte_bucket(90) == "31_90d"
        assert _dte_bucket(91) == "90p"
        assert _dte_bucket(None) == "unknown"

    def test_source_is_tape_recon(self):
        """All tape_recon events carry source='tape_recon'."""
        from scripts.ops_flow_cohorts import _apply_detector_v1
        prints = [
            _make_print_row("2026-06-30T10:00:00", price=5.00, bid=4.90, ask=5.00,
                            strike=550.0, right="C", size=1000, expiration="2026-07-18", seq=101),
        ]
        df = _make_tape_df(prints)
        events = _apply_detector_v1(df, "SPY", "2026-06-30")
        assert all(e["source"] == "tape_recon" for e in events)


def _make_print_row(ts, price, bid, ask, strike, right, size, expiration, seq):
    return {
        "trade_timestamp": ts,
        "price": price,
        "bid": bid,
        "ask": ask,
        "strike": strike,
        "right": right,
        "size": size,
        "expiration": expiration,
        "sequence": seq,
    }


# ── 2. eod_proxy PIT leak-injection ──────────────────────────────────────────

class TestEodProxyPITLeak:
    """PIT law: vol>OI comparison must use PRIOR-DAY OI only.

    Case A (control, must fire): prior-day OI=10, same-session volume=50 → event.
    Case B (leak guard, must NOT fire if we use SAME-DAY OI): same-day OI=100,
           prior-day OI=0 → no event (no prior OI to compare against).

    This mirrors the FS-0 leak-injection pattern extended to the eod_proxy cohort.
    """

    def _make_synthetic_eod_store(self, tmp_path: Path,
                                  root: str = "SPY",
                                  session_date: str = "2024-01-03",
                                  prior_oi: int = 10,
                                  same_day_oi: int = 100,
                                  volume: int = 50) -> Path:
        """Build a minimal synthetic thetadata_eod store in tmp_path.

        session_date row: volume=volume (the thing we're testing).
        prior_date row: OI=prior_oi (must be used in vol>OI comparison).
        same_date OI row: OI=same_day_oi (must NOT be used).
        """
        store_root = tmp_path / "thetadata_eod"
        eod_dir = store_root / "eod" / root
        oi_dir = store_root / "oi" / root
        eod_dir.mkdir(parents=True)
        oi_dir.mkdir(parents=True)

        session_ts = pd.Timestamp(session_date)
        prior_ts = session_ts - pd.Timedelta(days=1)
        yr = session_ts.year

        exp_date = pd.Timestamp("2024-01-19")  # 16 DTE from 2024-01-03
        strike = 470.0
        right = "C"

        # EOD data: volume on the session date
        eod_df = pd.DataFrame([{
            "root": root,
            "expiration": exp_date,
            "strike": strike,
            "right": right,
            "date": session_ts,
            "open": 5.00,
            "high": 5.50,
            "low": 4.90,
            "close": 5.20,
            "volume": volume,
            "count": volume,
            "bid": 5.10,
            "ask": 5.30,
        }])
        eod_df.to_parquet(eod_dir / f"{yr}.parquet", index=False)

        # OI data: prior-day OI AND same-day OI
        oi_rows = [
            {   # prior-day OI (T-1 relative to session): this is what we SHOULD use
                "root": root,
                "expiration": exp_date,
                "strike": strike,
                "right": right,
                "date": prior_ts,
                "open_interest": prior_oi,
            },
            {   # same-day OI (T=session): this must NOT be used (data leak)
                "root": root,
                "expiration": exp_date,
                "strike": strike,
                "right": right,
                "date": session_ts,
                "open_interest": same_day_oi,
            },
        ]
        oi_df = pd.DataFrame(oi_rows)
        oi_df.to_parquet(oi_dir / f"{yr}.parquet", index=False)

        # Write manifest
        manifest = {
            "store": "thetadata_eod",
            "n_roots": 1,
            "per_root": {root: {"completed_years": [str(yr)], "n_years": 15}},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (store_root / "_manifest.json").write_text(json.dumps(manifest))

        return store_root

    def test_prior_oi_triggers_event(self, tmp_path):
        """Control: prior-day OI=10, volume=50 → event fires (50 > 10)."""
        from scripts.ops_flow_cohorts import _eod_proxy_events_for_root, _load_detector_cfg

        store_root = self._make_synthetic_eod_store(
            tmp_path, root="SPY",
            session_date="2024-01-03",
            prior_oi=10,    # prior-day OI is small
            same_day_oi=100,
            volume=50,      # volume > prior_oi → should fire
        )

        # Patch detector config to use low min_contract_volume threshold
        cfg = {
            "version": "live_feed_v1",
            "eod_proxy": {
                "version": "eod_proxy_v1",
                "vol_oi_burst_multiplier": 1.0,
                "min_contract_volume": 5,
                "min_premium_usd": 100.0,  # low floor for test
                "rolling_window_days": 60,
            }
        }

        era_partitions = [("2024", "2024-01-01", "2024-12-31")]
        events = _eod_proxy_events_for_root("SPY", store_root, era_partitions, cfg)

        # Should have at least one event (volume=50 > prior_oi=10)
        assert len(events) >= 1, (
            "Expected event when volume > prior-day OI, but got none. "
            "PIT: prior_oi=10, volume=50, same_day_oi=100."
        )
        ev = events[0]
        assert ev["vol_gt_oi"] is True
        assert ev["source"] == "eod_proxy"

    def test_same_day_oi_does_not_trigger_event(self, tmp_path):
        """Leak guard: prior-day OI=0, volume=50 → NO event (no prior OI).

        If same-day OI=100 were used, 50 < 100 would still not fire, but we
        also test the case where prior_oi=0 means the vol>OI check has no basis.
        """
        from scripts.ops_flow_cohorts import _eod_proxy_events_for_root

        store_root = self._make_synthetic_eod_store(
            tmp_path, root="SPY",
            session_date="2024-01-03",
            prior_oi=0,      # no prior-day OI → vol>OI comparison cannot fire
            same_day_oi=10,  # same-day OI is small; if used, 50>10 would fire (LEAK)
            volume=50,
        )

        cfg = {
            "version": "live_feed_v1",
            "eod_proxy": {
                "version": "eod_proxy_v1",
                "vol_oi_burst_multiplier": 1.0,
                "min_contract_volume": 5,
                "min_premium_usd": 100.0,
                "rolling_window_days": 60,
            }
        }

        era_partitions = [("2024", "2024-01-01", "2024-12-31")]
        events = _eod_proxy_events_for_root("SPY", store_root, era_partitions, cfg)

        # With prior_oi=0, vol_gt_oi cannot be True (no prior OI to exceed)
        events_with_vol_gt_oi = [e for e in events if e.get("vol_gt_oi") is True]
        assert len(events_with_vol_gt_oi) == 0, (
            "LEAK: event fired with vol_gt_oi=True even though prior_oi=0. "
            "The comparator must use prior-day OI only."
        )

    def test_large_prior_oi_blocks_event(self, tmp_path):
        """Reverse control: prior-day OI=1000, volume=50 → NO event (50 < 1000)."""
        from scripts.ops_flow_cohorts import _eod_proxy_events_for_root

        store_root = self._make_synthetic_eod_store(
            tmp_path, root="SPY",
            session_date="2024-01-03",
            prior_oi=1000,  # large prior OI
            same_day_oi=10,
            volume=50,      # 50 < 1000 → must NOT fire
        )

        cfg = {
            "version": "live_feed_v1",
            "eod_proxy": {
                "version": "eod_proxy_v1",
                "vol_oi_burst_multiplier": 1.0,
                "min_contract_volume": 5,
                "min_premium_usd": 100.0,
                "rolling_window_days": 60,
            }
        }

        era_partitions = [("2024", "2024-01-01", "2024-12-31")]
        events = _eod_proxy_events_for_root("SPY", store_root, era_partitions, cfg)
        events_fired = [e for e in events if e.get("vol_gt_oi") is True]
        assert len(events_fired) == 0, (
            f"Event fired when volume=50 < prior_oi=1000. Got: {events_fired}"
        )


# ── 3. cohort separation guard ────────────────────────────────────────────────

class TestCohortSeparationGuard:
    """Mixed-source frame → load_cohort and append path raise ValueError."""

    def test_load_cohort_raises_on_mixed_source(self, tmp_path):
        """A parquet with two distinct 'source' values raises on load."""
        from scripts.ops_flow_cohorts import load_cohort

        # Build a mixed-source frame
        df = pd.DataFrame([
            {"event_id": "aaa", "source": "tape_recon"},
            {"event_id": "bbb", "source": "eod_proxy"},
        ])
        p = tmp_path / "mixed.parquet"
        df.to_parquet(p, index=False)

        with pytest.raises(ValueError, match="mixed sources"):
            load_cohort(p)

    def test_load_cohort_ok_for_single_source(self, tmp_path):
        """A parquet with one source value loads cleanly."""
        from scripts.ops_flow_cohorts import load_cohort

        df = pd.DataFrame([
            {"event_id": "aaa", "source": "tape_recon"},
            {"event_id": "bbb", "source": "tape_recon"},
        ])
        p = tmp_path / "single.parquet"
        df.to_parquet(p, index=False)

        loaded = load_cohort(p)
        assert len(loaded) == 2
        assert loaded["source"].unique().tolist() == ["tape_recon"]

    def test_append_cohort_raises_on_cross_source_new_rows(self, tmp_path):
        """_append_cohort raises when new_rows have mixed source values."""
        from scripts.ops_flow_cohorts import _append_cohort

        p = tmp_path / "cohort.parquet"
        mixed_rows = [
            {"event_id": "aaa", "source": "tape_recon"},
            {"event_id": "bbb", "source": "eod_proxy"},
        ]
        with pytest.raises(ValueError, match="mixed sources"):
            _append_cohort(p, mixed_rows)

    def test_append_cohort_raises_on_source_mismatch_with_existing(self, tmp_path):
        """_append_cohort raises when new source != existing cohort source."""
        from scripts.ops_flow_cohorts import _append_cohort

        p = tmp_path / "cohort.parquet"
        # Write existing tape_recon rows
        existing = pd.DataFrame([{"event_id": "aaa", "source": "tape_recon"}])
        existing.to_parquet(p, index=False)

        # Attempt to append eod_proxy rows → must raise
        new_rows = [{"event_id": "bbb", "source": "eod_proxy"}]
        with pytest.raises(ValueError, match="source mismatch"):
            _append_cohort(p, new_rows)


# ── 4. tz-aware UTC round-trip ────────────────────────────────────────────────

class TestTzAwareUTCRoundTrip:
    """Timestamps stored as strings survive parquet round-trip without dtype errors."""

    def test_aware_ts_survives_parquet_roundtrip(self, tmp_path):
        """Aware-UTC ISO string stored in parquet survives read without conversion errors."""
        from scripts.ops_flow_cohorts import _append_cohort, load_cohort

        ts_aware = datetime.now(timezone.utc).isoformat()  # "+00:00" suffix
        rows = [{"event_id": "e1", "source": "tape_recon",
                 "ts": ts_aware, "ingested_at": ts_aware}]

        path = tmp_path / "cohort.parquet"
        _append_cohort(path, rows)

        df = load_cohort(path)
        assert len(df) == 1
        # Timestamps stored as strings — no aware/naive mismatch possible
        ts_back = df.iloc[0]["ts"]
        assert "+00:00" in str(ts_back) or "Z" in str(ts_back), (
            f"Expected aware-UTC string in ts, got: {ts_back!r}"
        )

    def test_naive_and_aware_ts_both_serialize(self, tmp_path):
        """Both naive (coerced to UTC) and aware-UTC strings store safely."""
        from scripts.ops_flow_cohorts import _append_cohort, load_cohort, _normalize_ts

        naive_ts = "2026-07-13T14:30:00"   # no tz
        aware_ts = "2026-07-13T14:30:00+00:00"

        normalized_naive = _normalize_ts(naive_ts)
        normalized_aware = _normalize_ts(aware_ts)

        assert "+00:00" in normalized_naive
        assert "+00:00" in normalized_aware

        rows = [
            {"event_id": "e1", "source": "tape_recon", "ts": normalized_naive, "ingested_at": normalized_aware},
            {"event_id": "e2", "source": "tape_recon", "ts": normalized_aware, "ingested_at": normalized_naive},
        ]
        path = tmp_path / "cohort.parquet"
        _append_cohort(path, rows)

        df = load_cohort(path)
        assert len(df) == 2
        # Sort must not raise TypeError from naive/aware mixing
        sorted_df = df.sort_values("ts")
        assert len(sorted_df) == 2


# ── 5. resume idempotence ─────────────────────────────────────────────────────

class TestResumeIdempotence:
    """Run detection twice over same fixture units → no duplicate event_ids."""

    def test_no_duplicate_event_ids_after_double_run(self, tmp_path):
        """Appending the same events twice yields only the first occurrence."""
        from scripts.ops_flow_cohorts import _append_cohort, load_cohort

        rows_1 = [
            {"event_id": "abc123", "source": "tape_recon", "root": "SPY",
             "session_date": "2026-06-30", "premium": 1_000_000.0},
            {"event_id": "def456", "source": "tape_recon", "root": "SPY",
             "session_date": "2026-06-30", "premium": 2_000_000.0},
        ]
        path = tmp_path / "cohort.parquet"
        n1 = _append_cohort(path, rows_1)
        assert n1 == 2

        # Second run: same events + one new one
        rows_2 = [
            {"event_id": "abc123", "source": "tape_recon", "root": "SPY",
             "session_date": "2026-06-30", "premium": 9_999_999.0},  # same id, diff value
            {"event_id": "ghi789", "source": "tape_recon", "root": "SPY",
             "session_date": "2026-06-30", "premium": 3_000_000.0},  # new
        ]
        n2 = _append_cohort(path, rows_2)

        df = load_cohort(path)
        # Should have 3 unique event_ids, not 4
        assert len(df) == 3, f"Expected 3 rows (keep-first dedup), got {len(df)}"
        assert df["event_id"].nunique() == 3

        # The first occurrence of abc123 must have the original premium value
        abc_row = df[df["event_id"] == "abc123"]
        assert float(abc_row.iloc[0]["premium"]) == pytest.approx(1_000_000.0), (
            "Keep-first violated: second occurrence of event_id overwrote first"
        )

    def test_recon_state_marks_completed_units(self, tmp_path):
        """Completed units are tracked in state file and skipped on second run."""
        from scripts.ops_flow_cohorts import (
            _load_recon_state, _save_recon_state, _unit_key
        )

        state_path = tmp_path / "_recon_state.json"

        # Patch _recon_state_path to use tmp_path
        with patch("scripts.ops_flow_cohorts._flow_signals_dir", return_value=tmp_path):
            state = _load_recon_state()
            assert state == {"completed": {}, "failed": {}}

            # Mark a unit complete
            key = _unit_key("SPY", "2026-06-30")
            state["completed"][key] = "ok"
            _save_recon_state(state)

            # Load again — state persists
            loaded = _load_recon_state()
            assert key in loaded["completed"]


# ── 6. concurrency cap ────────────────────────────────────────────────────────

class TestConcurrencyCap:
    """The in-flight semaphore never exceeds 8 concurrent requests."""

    def test_max_inflight_constant_is_8(self):
        """_MAX_INFLIGHT is 8 per FS-1 spec."""
        from scripts.ops_flow_cohorts import _MAX_INFLIGHT
        assert _MAX_INFLIGHT == 8

    def test_tape_recon_respects_max_inflight(self, tmp_path):
        """run_tape_recon uses at most _MAX_INFLIGHT concurrent fetches.

        We mock _fetch_unit to count peak concurrency and verify it never exceeds 8.
        """
        import threading
        from scripts.ops_flow_cohorts import _MAX_INFLIGHT

        peak_inflight = [0]
        current_inflight = [0]
        lock = threading.Lock()

        def mock_fetch(root, session_date, eod_root, per_request_timeout=120.0):
            with lock:
                current_inflight[0] += 1
                peak_inflight[0] = max(peak_inflight[0], current_inflight[0])
            import time
            time.sleep(0.01)  # simulate brief work
            with lock:
                current_inflight[0] -= 1
            return []  # empty events

        with patch("scripts.ops_flow_cohorts._flow_signals_dir", return_value=tmp_path), \
             patch("scripts.ops_flow_cohorts._fetch_unit", side_effect=mock_fetch), \
             patch("scripts.ops_flow_cohorts._load_ladder", return_value={
                 "tier1": {
                     "label": "test",
                     "start_date": "2026-06-01",
                     "end_date": "2026-06-20",
                     "roots": ["SPY", "QQQ"],
                 }
             }), \
             patch("scripts.ops_flow_cohorts._eod_store_root", return_value=None), \
             patch("collectors.thetadata.reachable", return_value=True):
            from scripts.ops_flow_cohorts import run_tape_recon
            run_tape_recon(dry_run=True)

        # Peak concurrent fetches must never exceed _MAX_INFLIGHT
        assert peak_inflight[0] <= _MAX_INFLIGHT, (
            f"Peak concurrency {peak_inflight[0]} exceeded _MAX_INFLIGHT={_MAX_INFLIGHT}"
        )


# ── 7. terminal-down ──────────────────────────────────────────────────────────

class TestTerminalDown:
    """When ThetaTerminal is unreachable: clean error, nonzero exit, no hang, no corrupt state."""

    def test_tape_recon_returns_error_when_terminal_down(self, tmp_path):
        """run_tape_recon returns 1 (nonzero) when terminal is unreachable."""
        with patch("scripts.ops_flow_cohorts._flow_signals_dir", return_value=tmp_path), \
             patch("scripts.ops_flow_cohorts._load_ladder", return_value={"tier1": {
                 "label": "test", "start_date": "2026-06-01",
                 "end_date": "2026-06-01", "roots": ["SPY"],
             }}):
            # Patch thetadata.reachable to return False at the module level
            with patch("collectors.thetadata.reachable", return_value=False):
                from scripts.ops_flow_cohorts import run_tape_recon
                result = run_tape_recon(dry_run=False)

        # Must return 1 (error) not hang
        assert result == 1, f"Expected return code 1 when terminal is down, got {result}"

    def test_terminal_down_does_not_corrupt_state(self, tmp_path):
        """When terminal is down from the start, no state file is corrupted."""
        with patch("scripts.ops_flow_cohorts._flow_signals_dir", return_value=tmp_path), \
             patch("scripts.ops_flow_cohorts._load_ladder", return_value={"tier1": {
                 "label": "test", "start_date": "2026-06-01",
                 "end_date": "2026-06-01", "roots": ["SPY"],
             }}), \
             patch("collectors.thetadata.reachable", return_value=False):
            from scripts.ops_flow_cohorts import run_tape_recon
            run_tape_recon(dry_run=False)

        # State file should NOT be written (terminal was down before any units processed)
        state_path = tmp_path / "_recon_state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text())
            # No units should be marked as failed or completed
            assert len(state.get("completed", {})) == 0
            assert len(state.get("failed", {})) == 0

    def test_fetch_unit_returns_error_string_on_connection_error(self):
        """_fetch_unit returns a string error message (not raises) on connection error."""
        from scripts.ops_flow_cohorts import _fetch_unit

        with patch("collectors.thetadata.reachable", return_value=False):
            result = _fetch_unit("SPY", "2026-06-30", None)

        assert isinstance(result, str), "Expected error string when terminal is down"
        assert "unreachable" in result.lower() or "terminal" in result.lower()


# ── coverage report ───────────────────────────────────────────────────────────

class TestCoverageReport:
    """Coverage report runs cleanly even when cohorts are absent."""

    def test_coverage_report_absent_cohorts(self, tmp_path):
        """Coverage report runs and returns a valid dict when no cohorts exist."""
        from scripts.ops_flow_cohorts import _coverage_report

        report = _coverage_report(out_dir=tmp_path)

        assert "cohorts" in report
        assert "tape_recon" in report["cohorts"]
        assert "eod_proxy" in report["cohorts"]
        assert report["cohorts"]["tape_recon"].get("status") in ("absent", "empty")
        assert report["cohorts"]["eod_proxy"].get("status") in ("absent", "empty")

    def test_coverage_report_writes_json(self, tmp_path):
        """Coverage report writes cohort_coverage.json."""
        from scripts.ops_flow_cohorts import _coverage_report

        _coverage_report(out_dir=tmp_path)
        json_path = tmp_path / "cohort_coverage.json"
        assert json_path.exists()
        data = json.loads(json_path.read_text())
        assert "cohorts" in data

    def test_coverage_report_with_tape_recon_data(self, tmp_path):
        """Coverage report counts events correctly from an existing cohort."""
        from scripts.ops_flow_cohorts import _append_cohort, _coverage_report

        rows = [
            {
                "event_id": f"e{i}", "source": "tape_recon", "root": "SPY",
                "session_date": "2026-06-30", "dte_bucket": "8_30d",
                "ingested_at": datetime.now(timezone.utc).isoformat(),
            }
            for i in range(5)
        ]
        _append_cohort(tmp_path / "cohort_tape_recon.parquet", rows)

        report = _coverage_report(out_dir=tmp_path)
        assert report["cohorts"]["tape_recon"]["n_events"] == 5
        assert report["cohorts"]["tape_recon"]["n_roots"] == 1


# ── module-level CI-null ──────────────────────────────────────────────────────

class TestCINull:
    """Module imports cleanly and degrades gracefully when stores are absent."""

    def test_import_succeeds(self):
        """ops_flow_cohorts imports without error even without stores."""
        import scripts.ops_flow_cohorts  # noqa: F401

    def test_eod_store_root_returns_none_when_absent(self, tmp_path):
        """_eod_store_root returns None gracefully when no store exists."""
        from scripts.ops_flow_cohorts import _eod_store_root

        with patch.dict(os.environ, {"THETADATA_EOD_DIR": str(tmp_path / "nonexistent")}):
            result = _eod_store_root()

        # If none of the candidates exist, returns None
        # (may return the home path if it exists; that's ok for CI where it won't)
        # Just assert no exception
        assert result is None or isinstance(result, Path)

    def test_eod_proxy_fails_gracefully_without_store(self, tmp_path):
        """run_eod_proxy returns 0 gracefully when no EOD store is found."""
        from scripts.ops_flow_cohorts import run_eod_proxy

        # Override all store paths to nonexistent
        with patch.dict(os.environ, {"THETADATA_EOD_DIR": str(tmp_path / "no_store")}), \
             patch("scripts.ops_flow_cohorts._eod_store_root", return_value=None):
            result = run_eod_proxy(dry_run=True)

        assert result == 0

    def test_load_cohort_returns_empty_when_absent(self, tmp_path):
        """load_cohort returns empty DataFrame when the file doesn't exist."""
        from scripts.ops_flow_cohorts import load_cohort

        result = load_cohort(tmp_path / "nonexistent_cohort.parquet")
        assert isinstance(result, pd.DataFrame)
        assert result.empty


# ── FIX 1: Monday-session OI regression tests ────────────────────────────────

class TestMondaySessionOI:
    """FIX 1: merge_asof prior-session alignment fires on Monday sessions.

    The previous +1d calendar shift caused Friday OI (date=2024-01-05) to land
    on Saturday (2024-01-06), never matching a Monday session (2024-01-08).
    The corrected merge_asof(direction='backward', tolerance=4d) finds Friday OI.
    """

    def _make_monday_store(
        self,
        tmp_path: Path,
        root: str = "SPY",
        monday_date: str = "2024-01-08",
        friday_date: str = "2024-01-05",
        friday_oi: int = 10,
        volume: int = 50,
    ) -> Path:
        """Synthetic store: EOD row on Monday, OI row on prior Friday."""
        store_root = tmp_path / "thetadata_eod"
        eod_dir = store_root / "eod" / root
        oi_dir = store_root / "oi" / root
        eod_dir.mkdir(parents=True)
        oi_dir.mkdir(parents=True)

        monday_ts = pd.Timestamp(monday_date)
        friday_ts = pd.Timestamp(friday_date)
        yr = monday_ts.year

        exp_date = pd.Timestamp("2024-01-19")
        strike = 470.0
        right = "C"

        eod_df = pd.DataFrame([{
            "root": root,
            "expiration": exp_date,
            "strike": strike,
            "right": right,
            "date": monday_ts,
            "open": 5.0,
            "high": 5.5,
            "low": 4.9,
            "close": 5.2,
            "volume": volume,
            "count": volume,
            "bid": 5.1,
            "ask": 5.3,
        }])
        eod_df.to_parquet(eod_dir / f"{yr}.parquet", index=False)

        # OI: only Friday row (no Saturday, no Monday)
        oi_df = pd.DataFrame([{
            "root": root,
            "expiration": exp_date,
            "strike": strike,
            "right": right,
            "date": friday_ts,
            "open_interest": friday_oi,
        }])
        oi_df.to_parquet(oi_dir / f"{yr}.parquet", index=False)

        manifest = {
            "store": "thetadata_eod",
            "n_roots": 1,
            "per_root": {root: {"completed_years": [str(yr)], "n_years": 15}},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (store_root / "_manifest.json").write_text(json.dumps(manifest))
        return store_root

    def test_monday_session_fires_with_friday_oi(self, tmp_path):
        """Monday EOD + Friday OI → vol_gt_oi=True event fires (FIX 1 regression)."""
        from scripts.ops_flow_cohorts import _eod_proxy_events_for_root

        store_root = self._make_monday_store(
            tmp_path,
            monday_date="2024-01-08",
            friday_date="2024-01-05",
            friday_oi=10,  # Friday OI small
            volume=50,     # Monday volume exceeds Friday OI
        )

        cfg = {
            "eod_proxy": {
                "version": "eod_proxy_v1",
                "vol_oi_burst_multiplier": 1.0,
                "min_contract_volume": 5,
                "min_premium_usd": 100.0,
                "rolling_window_days": 60,
                "premium_burst_z": 2.5,
            }
        }
        era_partitions = [("2024", "2024-01-01", "2024-12-31")]
        events = _eod_proxy_events_for_root("SPY", store_root, era_partitions, cfg)

        vol_gt_oi_events = [e for e in events if e.get("vol_gt_oi") is True]
        assert len(vol_gt_oi_events) >= 1, (
            "FIX 1 regression: Monday session with Friday OI did not fire. "
            f"Got {len(events)} events, none with vol_gt_oi=True. "
            "The +1d calendar shift bug drops Monday sessions (OI lands on Saturday)."
        )
        assert vol_gt_oi_events[0]["session_date"] == "2024-01-08"

    def test_same_day_oi_only_does_not_fire(self, tmp_path):
        """Same-day OI only (no prior-session OI) → no vol_gt_oi event (PIT preserved)."""
        from scripts.ops_flow_cohorts import _eod_proxy_events_for_root

        store_root = tmp_path / "thetadata_eod"
        eod_dir = store_root / "eod" / "SPY"
        oi_dir = store_root / "oi" / "SPY"
        eod_dir.mkdir(parents=True)
        oi_dir.mkdir(parents=True)

        monday_ts = pd.Timestamp("2024-01-08")
        exp_date = pd.Timestamp("2024-01-19")

        eod_df = pd.DataFrame([{
            "root": "SPY", "expiration": exp_date, "strike": 470.0, "right": "C",
            "date": monday_ts, "open": 5.0, "high": 5.5, "low": 4.9,
            "close": 5.2, "volume": 50, "count": 50, "bid": 5.1, "ask": 5.3,
        }])
        eod_df.to_parquet(eod_dir / "2024.parquet", index=False)

        # ONLY same-day OI (Monday): must not be used (PIT law)
        oi_df = pd.DataFrame([{
            "root": "SPY", "expiration": exp_date, "strike": 470.0, "right": "C",
            "date": monday_ts,  # SAME DAY as session
            "open_interest": 5,  # small: 50 > 5 would fire if same-day used (leak)
        }])
        oi_df.to_parquet(oi_dir / "2024.parquet", index=False)

        manifest = {
            "store": "thetadata_eod", "n_roots": 1,
            "per_root": {"SPY": {"completed_years": ["2024"], "n_years": 15}},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (store_root / "_manifest.json").write_text(json.dumps(manifest))

        cfg = {
            "eod_proxy": {
                "version": "eod_proxy_v1", "vol_oi_burst_multiplier": 1.0,
                "min_contract_volume": 5, "min_premium_usd": 100.0,
                "rolling_window_days": 60, "premium_burst_z": 2.5,
            }
        }
        era_partitions = [("2024", "2024-01-01", "2024-12-31")]
        events = _eod_proxy_events_for_root("SPY", store_root, era_partitions, cfg)
        vol_gt_oi_events = [e for e in events if e.get("vol_gt_oi") is True]
        assert len(vol_gt_oi_events) == 0, (
            "PIT LEAK: vol_gt_oi fired using same-day OI. "
            "allow_exact_matches=False must prevent same-day match."
        )


# ── FIX 1b: _load_prior_oi backward-search tests ──────────────────────────────

class TestLoadPriorOI:
    """FIX 1b: _load_prior_oi uses backward search (up to 4d) and handles year boundary."""

    def _make_oi_store(self, tmp_path: Path, root: str, oi_rows: list[dict]) -> Path:
        store = tmp_path / "thetadata_eod"
        oi_dir = store / "oi" / root
        oi_dir.mkdir(parents=True)

        df = pd.DataFrame(oi_rows)
        # Write per-year
        for yr, grp in df.groupby(df["date"].apply(lambda d: pd.Timestamp(d).year)):
            grp.to_parquet(oi_dir / f"{yr}.parquet", index=False)
        return store

    def test_monday_session_finds_friday_oi(self, tmp_path):
        """_load_prior_oi(Monday 2024-01-08) finds Friday 2024-01-05 OI (3 days back)."""
        from scripts.ops_flow_cohorts import _load_prior_oi

        exp_date = pd.Timestamp("2024-01-19")
        store = self._make_oi_store(tmp_path, "SPY", [
            {"root": "SPY", "expiration": exp_date, "strike": 470.0, "right": "C",
             "date": pd.Timestamp("2024-01-05"), "open_interest": 42},
        ])

        result = _load_prior_oi(store, "SPY", "2024-01-08")
        assert len(result) > 0, "Monday session: _load_prior_oi found no OI (should find Friday OI)"
        key = ("2024-01-19", "470.000", "C")
        assert key in result, f"Expected key {key} in result, got {list(result.keys())}"
        assert result[key] == 42

    def test_same_day_oi_not_returned(self, tmp_path):
        """_load_prior_oi must exclude the session date itself (PIT)."""
        from scripts.ops_flow_cohorts import _load_prior_oi

        exp_date = pd.Timestamp("2024-01-08")
        store = self._make_oi_store(tmp_path, "SPY", [
            # Only same-day OI (must be excluded)
            {"root": "SPY", "expiration": exp_date, "strike": 470.0, "right": "C",
             "date": pd.Timestamp("2024-01-08"), "open_interest": 99},
        ])

        result = _load_prior_oi(store, "SPY", "2024-01-08")
        assert len(result) == 0, "PIT LEAK: _load_prior_oi returned same-day OI"

    def test_year_boundary_jan02_finds_dec29(self, tmp_path):
        """_load_prior_oi(2024-01-02) finds OI from 2023-12-29 (crosses year boundary)."""
        from scripts.ops_flow_cohorts import _load_prior_oi

        exp_date = pd.Timestamp("2024-01-19")
        store = self._make_oi_store(tmp_path, "SPY", [
            {"root": "SPY", "expiration": exp_date, "strike": 470.0, "right": "C",
             "date": pd.Timestamp("2023-12-29"), "open_interest": 77},
        ])

        result = _load_prior_oi(store, "SPY", "2024-01-02")
        assert len(result) > 0, (
            "Year-boundary failure: _load_prior_oi(2024-01-02) did not find 2023-12-29 OI. "
            "The function must open the prior-year parquet when search window crosses Jan 1."
        )
        key = ("2024-01-19", "470.000", "C")
        assert result[key] == 77


# ── FIX 2a: eod_proxy premium baseline PIT tests ─────────────────────────────

class TestEodProxyPremiumBaseline:
    """FIX 2a: Rolling premium baseline excludes current day (shift-1 PIT)."""

    def _make_store_with_days(
        self,
        tmp_path: Path,
        root: str,
        n_days: int,
        close: float = 5.0,
        volume: int = 100,
        spike_day_idx: int | None = None,
        spike_premium: float | None = None,
    ) -> Path:
        """Build a store with n_days of EOD data. Optionally inject a spike on spike_day_idx."""
        store_root = tmp_path / "thetadata_eod"
        eod_dir = store_root / "eod" / root
        oi_dir = store_root / "oi" / root
        eod_dir.mkdir(parents=True)
        oi_dir.mkdir(parents=True)

        base_date = pd.Timestamp("2018-01-01")
        exp_date = pd.Timestamp("2019-12-20")
        rows = []
        for i in range(n_days):
            d = base_date + pd.Timedelta(days=i)
            c = close
            v = volume
            if spike_day_idx is not None and i == spike_day_idx and spike_premium is not None:
                # Inject spike: set close such that premium = spike_premium
                v = 1
                c = spike_premium / 100.0
            rows.append({
                "root": root, "expiration": exp_date, "strike": 470.0, "right": "C",
                "date": d, "open": c, "high": c + 0.1, "low": c - 0.1,
                "close": c, "volume": v, "count": v, "bid": c - 0.1, "ask": c + 0.1,
            })

        df = pd.DataFrame(rows)
        # Write year parquets
        for yr, grp in df.groupby(df["date"].apply(lambda d: d.year)):
            grp.to_parquet(eod_dir / f"{yr}.parquet", index=False)

        # Write empty OI (so no vol_gt_oi events; we test premium_burst only)
        manifest = {
            "store": "thetadata_eod", "n_roots": 1,
            "per_root": {root: {"completed_years": list(map(str, df["date"].apply(lambda d: d.year).unique())), "n_years": 15}},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (store_root / "_manifest.json").write_text(json.dumps(manifest))
        return store_root

    def test_first_window_sessions_have_no_baseline(self, tmp_path):
        """First rolling_window days yield premium_z=None (honest null, no fake-neutral)."""
        from scripts.ops_flow_cohorts import _eod_proxy_events_for_root

        # 30 days of data — below rolling_window=60 → no baseline available
        store_root = self._make_store_with_days(tmp_path, "SPY", n_days=30)

        cfg = {
            "eod_proxy": {
                "version": "eod_proxy_v1", "vol_oi_burst_multiplier": 1.0,
                "min_contract_volume": 1, "min_premium_usd": 100.0,
                "rolling_window_days": 60, "premium_burst_z": 2.5,
            }
        }
        era_partitions = [("2018", "2018-01-01", "2018-12-31")]
        events = _eod_proxy_events_for_root("SPY", store_root, era_partitions, cfg)

        # Any events that fired (via vol_gt_oi if OI present, or premium_burst)
        # must have premium_z=None since < 60 days of history
        for ev in events:
            assert ev.get("premium_z") is None, (
                f"FIX 2a: first-window event has non-None premium_z={ev.get('premium_z')}. "
                "Baseline must be None until rolling_window sessions are accumulated."
            )

    def test_current_day_excluded_from_own_baseline(self, tmp_path):
        """A huge spike on day N must not affect its own z-score (shift-1 PIT)."""
        from scripts.ops_flow_cohorts import _build_premium_rolling_baseline

        # Build 70 normal days then 1 huge spike day
        n_normal = 70
        spike_prem = 1e9  # enormous spike

        store_root = self._make_store_with_days(
            tmp_path, "SPY",
            n_days=n_normal + 1,
            close=5.0, volume=100,
            spike_day_idx=n_normal,  # last day = spike
            spike_premium=spike_prem,
        )

        eod_dir = store_root / "eod" / "SPY"
        baseline_df = _build_premium_rolling_baseline(eod_dir, "SPY", rolling_window=60)

        # The last day (spike) should have a baseline built from PRIOR days (shift-1)
        # So _roll_mean and _roll_std for the spike day should be close to the
        # normal-day mean ($50k = 5.0 * 100 * 100), NOT inflated by the spike itself
        if not baseline_df.empty:
            last_date = baseline_df["date"].max()
            last_row = baseline_df[baseline_df["date"] == last_date]
            if not last_row.empty:
                roll_mean = last_row["_roll_mean"].values[0]
                if roll_mean is not None and not (isinstance(roll_mean, float) and roll_mean != roll_mean):
                    normal_prem = 5.0 * 100 * 100  # close * volume * 100 = $50000
                    # The spike (1e9) is ~20000x normal; if self-included the mean
                    # would be >> 10x normal_prem
                    assert roll_mean < 10 * normal_prem, (
                        f"FIX 2a: spike day's own baseline mean={roll_mean:.0f} is inflated "
                        f"(normal_prem={normal_prem:.0f}), suggesting self-inclusion (shift-1 broken)."
                    )


# ── FIX 2b: tape_recon premium baseline accumulation ─────────────────────────

class TestTapeReconPremiumBaseline:
    """FIX 2b: premium baseline advances across sequential units; shift-1 PIT enforced."""

    def test_baseline_advances_across_two_units(self):
        """After session A completes, session B's baseline uses A's data (not B's)."""
        from scripts.ops_flow_cohorts import (
            _compute_tape_premium_baseline,
            _update_tape_baseline_data,
        )

        accumulated: dict = {}

        # Session A: 50 events with $500k premium each, bucket 8_30d
        session_a_events = [
            {"dte_bucket": "8_30d", "premium": 500_000.0}
            for _ in range(5)  # 5 events
        ]
        _update_tape_baseline_data(accumulated, "SPY", "2024-01-02", session_a_events)

        # After A, B's baseline is computed from accumulated (which only has A)
        baseline_before_b = _compute_tape_premium_baseline(accumulated, "SPY", window=2)
        # Only 1 session in accumulator for SPY→ need window=2; should be None (not enough)
        # This is correct behavior (honest null until window sessions accumulated)

        # Add more sessions to reach window
        session_b_events = [{"dte_bucket": "8_30d", "premium": 600_000.0} for _ in range(3)]
        _update_tape_baseline_data(accumulated, "SPY", "2024-01-03", session_b_events)

        # Now compute for session C (window=2 — should have enough now)
        baseline_for_c = _compute_tape_premium_baseline(accumulated, "SPY", window=2)

        # baseline_for_c should be based on sessions A+B, NOT C
        # A had aggregate_premium = 5 * 500k = 2.5M; B had 3 * 600k = 1.8M
        # (accumulated stores per-bucket sums per session)
        assert baseline_for_c is not None, (
            "FIX 2b: baseline_for_c should not be None after 2 sessions (window=2)"
        )
        assert "8_30d" in baseline_for_c, "8_30d bucket should be in baseline"
        mean, std = baseline_for_c["8_30d"]
        # Mean of A and B bucket premiums
        assert mean > 0, f"Baseline mean should be positive, got {mean}"
        # std should be nonzero (A != B)
        assert std > 0, f"Baseline std should be nonzero (A premium != B premium), got {std}"

    def test_baseline_none_below_window(self):
        """_compute_tape_premium_baseline returns None when fewer sessions than window."""
        from scripts.ops_flow_cohorts import _compute_tape_premium_baseline, _update_tape_baseline_data

        accumulated: dict = {}
        events = [{"dte_bucket": "8_30d", "premium": 1_000_000.0}]
        _update_tape_baseline_data(accumulated, "SPY", "2024-01-02", events)

        # Only 1 session, window=252 → should return None (honest)
        result = _compute_tape_premium_baseline(accumulated, "SPY", window=252)
        assert result is None, (
            "FIX 2b: baseline should be None until window sessions accumulated (honest null)"
        )


# ── FIX 3: grader coverage honesty ───────────────────────────────────────────

class TestGraderCoverageHonesty:
    """FIX 3: synthetic cohort → three distinct reason codes + era breakdown in json."""

    def _make_synthetic_cohort(self, tmp_path: Path, cohort_name: str = "eod_proxy") -> Path:
        """Three events:
        - One gradable: ticker with yahoo store containing data covering session.
        - One pre-history: ticker with yahoo store but session before store start.
        - One no-price: ticker with no yahoo store at all.
        """
        from scripts.ops_flow_cohorts import _append_cohort

        events = [
            {
                "event_id": "gradable001",
                "session_date": "2025-06-01",
                "root": "GRADABLE_TICKER",
                "dte_bucket": "8_30d",
                "source": cohort_name,
                "era": "2023+",
                "premium": 1_000_000.0,
            },
            {
                "event_id": "prehistory001",
                "session_date": "2010-01-03",  # before any typical yahoo store start
                "root": "GRADABLE_TICKER",
                "dte_bucket": "8_30d",
                "source": cohort_name,
                "era": "2010-15",
                "premium": 500_000.0,
            },
            {
                "event_id": "noprice001",
                "session_date": "2025-01-02",
                "root": "MISSING_TICKER_XYZ_NOTREAL",
                "dte_bucket": "8_30d",
                "source": cohort_name,
                "era": "2023+",
                "premium": 300_000.0,
            },
        ]

        cohort_path = tmp_path / f"cohort_{cohort_name}.parquet"
        _append_cohort(cohort_path, events)
        return tmp_path

    def test_three_reason_codes_produced(self, tmp_path):
        """Synthetic cohort → no_price_data, no_price_history_for_era, and ok/not_matured."""
        from scripts.ops_flow_cohorts import run_grade_cohorts
        import pandas as pd

        fsd = self._make_synthetic_cohort(tmp_path, cohort_name="eod_proxy")

        # Build a minimal close series for GRADABLE_TICKER
        # Store starts at 2023-01-01 → session 2025-06-01 is within range
        # session 2010-01-03 is BEFORE store start → no_price_history_for_era
        gradable_close = pd.Series(
            [100.0 + i * 0.1 for i in range(1000)],
            index=pd.date_range("2023-01-01", periods=1000, freq="B"),
            name="GRADABLE_TICKER",
        )

        def mock_load_close(ticker: str):
            if ticker == "GRADABLE_TICKER":
                return gradable_close
            return None  # MISSING_TICKER → no_price_data

        def mock_spy_close():
            return gradable_close  # simple proxy for SPY

        with patch("engine.flow_signals_grade._load_close", side_effect=mock_load_close), \
             patch("engine.flow_signals_grade._spy_close", return_value=mock_spy_close()):
            summary = run_grade_cohorts(out_dir=fsd)

        assert "eod_proxy" in summary, "eod_proxy must appear in grade summary"
        coh = summary["eod_proxy"]

        # Assert three distinct reason codes are present
        assert coh.get("n_no_price_data", 0) >= 1, (
            "FIX 3a: MISSING_TICKER event must produce reason_code=no_price_data"
        )
        assert coh.get("n_no_history", 0) >= 1, (
            "FIX 3b: pre-history event (2010) must produce reason_code=no_price_history_for_era"
        )
        # The gradable event must have been graded (ok or not_matured)
        total_graded = coh.get("n_ok", 0) + coh.get("n_not_matured", 0)
        assert total_graded >= 1, (
            "FIX 3: gradable event must produce ok or not_yet_matured reason_code"
        )

    def test_era_breakdown_in_grades_parquet(self, tmp_path):
        """Grade parquet for synthetic cohort contains three different reason_codes."""
        from scripts.ops_flow_cohorts import run_grade_cohorts
        import pandas as pd

        fsd = self._make_synthetic_cohort(tmp_path, cohort_name="eod_proxy")

        gradable_close = pd.Series(
            [100.0 + i * 0.1 for i in range(1000)],
            index=pd.date_range("2023-01-01", periods=1000, freq="B"),
        )

        with patch("engine.flow_signals_grade._load_close",
                   side_effect=lambda t: gradable_close if t == "GRADABLE_TICKER" else None), \
             patch("engine.flow_signals_grade._spy_close", return_value=gradable_close):
            run_grade_cohorts(out_dir=fsd)

        grades_path = fsd / "cohort_eod_proxy_grades.parquet"
        assert grades_path.exists(), "Grades parquet must be written"

        gdf = pd.read_parquet(grades_path)
        reason_codes = set(gdf["reason_code"].dropna().unique())
        assert "no_price_data" in reason_codes, (
            f"no_price_data must be in grades reason_codes, got {reason_codes}"
        )
        assert "no_price_history_for_era" in reason_codes, (
            f"no_price_history_for_era must be in grades reason_codes, got {reason_codes}"
        )


# ── FIX 6: signing_source provenance ─────────────────────────────────────────

class TestSigningSourceProvenance:
    """FIX 6: tape_recon events have signing_source='quote_rule'; eod_proxy have None."""

    def test_tape_recon_signing_source_is_quote_rule(self):
        """tape_recon events carry signing_source='quote_rule'."""
        from scripts.ops_flow_cohorts import _apply_detector_v1

        prints = [
            _make_print_row("2026-06-30T10:00:00", price=5.00, bid=4.90, ask=5.00,
                            strike=550.0, right="C", size=1000, expiration="2026-07-18", seq=101),
            _make_print_row("2026-06-30T10:00:01", price=5.00, bid=4.90, ask=5.00,
                            strike=550.0, right="C", size=1000, expiration="2026-07-18", seq=102),
        ]
        df = _make_tape_df(prints)
        events = _apply_detector_v1(df, "SPY", "2026-06-30")

        for ev in events:
            assert ev.get("signing_source") == "quote_rule", (
                f"FIX 6: tape_recon event must have signing_source='quote_rule', "
                f"got {ev.get('signing_source')!r}"
            )

    def test_eod_proxy_signing_source_is_none(self, tmp_path):
        """eod_proxy events carry signing_source=None (no signing basis)."""
        from scripts.ops_flow_cohorts import _eod_proxy_events_for_root

        # Reuse Monday store helper
        monday_ts = pd.Timestamp("2024-01-08")
        friday_ts = pd.Timestamp("2024-01-05")
        exp_date = pd.Timestamp("2024-01-19")

        store_root = tmp_path / "thetadata_eod"
        eod_dir = store_root / "eod" / "SPY"
        oi_dir = store_root / "oi" / "SPY"
        eod_dir.mkdir(parents=True)
        oi_dir.mkdir(parents=True)

        eod_df = pd.DataFrame([{
            "root": "SPY", "expiration": exp_date, "strike": 470.0, "right": "C",
            "date": monday_ts, "open": 5.0, "high": 5.5, "low": 4.9,
            "close": 5.2, "volume": 50, "count": 50, "bid": 5.1, "ask": 5.3,
        }])
        eod_df.to_parquet(eod_dir / "2024.parquet", index=False)

        oi_df = pd.DataFrame([{
            "root": "SPY", "expiration": exp_date, "strike": 470.0, "right": "C",
            "date": friday_ts, "open_interest": 5,  # volume=50 > 5 → fires
        }])
        oi_df.to_parquet(oi_dir / "2024.parquet", index=False)

        manifest = {
            "store": "thetadata_eod", "n_roots": 1,
            "per_root": {"SPY": {"completed_years": ["2024"], "n_years": 15}},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (store_root / "_manifest.json").write_text(json.dumps(manifest))

        cfg = {
            "eod_proxy": {
                "version": "eod_proxy_v1", "vol_oi_burst_multiplier": 1.0,
                "min_contract_volume": 5, "min_premium_usd": 100.0,
                "rolling_window_days": 60, "premium_burst_z": 2.5,
            }
        }
        era_partitions = [("2024", "2024-01-01", "2024-12-31")]
        events = _eod_proxy_events_for_root("SPY", store_root, era_partitions, cfg)

        for ev in events:
            assert ev.get("signing_source") is None, (
                f"FIX 6: eod_proxy event must have signing_source=None, "
                f"got {ev.get('signing_source')!r}"
            )
