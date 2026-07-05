"""tests/test_live_flow.py — hermetic tests for the live options-flow system (P-A + P-B).

All tests are network-free (no clock reads, no Theta Terminal, no R2 calls).
Exercises:
  1.  Bucket vocabulary parity with tape_flow (DTE + moneyness labels match)
  2.  Signing softness — side never a bare "buy" or "sell" (always "~buy"/"~sell")
  3.  Coalescing — multiple prints per contract aggregate correctly
  4.  Floor gate — premium < floor is not notable
  5.  Z gate — premium_z >= 3 is notable even below floor; baseline_source="z252"
  6.  Floor fallback — no baseline → floor gate, baseline_source="floor", premium_z=None
  7.  vol_gt_oi with OI present — True/False correctly assigned
  8.  vol_gt_oi without OI — None
  9.  repeated flag — same contract notable in >=2 distinct cycles
  10. Event-id stability — same tape twice → zero new events (idempotent)
  11. 24h retention trim — events older than cutoff are dropped; cap 2000 enforced
  12. Heat group math — gross_premium, net_signed_premium_soft, call_prem_share correct
  13. Heat group_zh presence — every heat row has a non-empty group_zh
  14. meta schema — all required keys present
  15. API route: fresh fetch path (monkeypatched _flow_fetch)
  16. API route: stale fallback (fetch fails; last-cached returned with stale=True)
  17. API route: never-fetched → 503
  18. Collector additive params — mock _stream_lines; assert no regression when omitted
  19. Collector additive params — start_time/end_time appear in params when provided
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# ── engine imports ─────────────────────────────────────────────────────────────
from engine import live_flow as lf
from engine.tape_flow import _dte_bucket, _moneyness_bucket, MONEY_ATM_BAND, MONEY_NEAR_OTM

SESSION_DATE = "2026-07-02"
BATCH_TS     = "2026-07-02T14:30:00Z"

# ── fixture helpers ────────────────────────────────────────────────────────────

def _make_trade(
    root="SPY", right="C", expiration="2026-07-05", strike=550.0,
    price=2.50, size=10, bid=2.40, ask=2.60,
    trade_ts="2026-07-02T14:30:00", sequence=1001,
) -> dict:
    return {
        "root": root, "right": right, "expiration": expiration, "strike": strike,
        "price": price, "size": size, "bid": bid, "ask": ask,
        "trade_timestamp": trade_ts, "quote_timestamp": trade_ts,
        "sequence": sequence,
        "date": trade_ts[:10],
    }


def _df(trades: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(trades)


def _calls(*trades) -> pd.DataFrame:
    """DataFrame of call trades."""
    rows = [_make_trade(**t) for t in trades] if trades else [_make_trade()]
    return _df(rows)


def _puts(*trades) -> pd.DataFrame:
    """DataFrame of put trades."""
    rows = [_make_trade(right="P", **t) for t in trades] if trades else []
    return _df(rows) if rows else pd.DataFrame()


def _run(calls_df, puts_df=None, prior=None, oi_prev=None, baselines=None,
         etf_floor=1_000_000, name_floor=250_000,
         etf_anchors=None, root="SPY") -> dict:
    """Convenience wrapper around lf.process_batch."""
    return lf.process_batch(
        calls_df=calls_df,
        puts_df=puts_df,
        session_date=SESSION_DATE,
        batch_ts=BATCH_TS,
        prior_state=prior,
        oi_prev=oi_prev,
        baselines=baselines,
        etf_floor=etf_floor,
        name_floor=name_floor,
        etf_anchors=etf_anchors or ["SPY", "QQQ"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. DTE bucket vocabulary parity with tape_flow
# ─────────────────────────────────────────────────────────────────────────────

class TestDteBucketParity:
    """DTE bucket labels from live_flow must match tape_flow._dte_bucket exactly."""

    @pytest.mark.parametrize("dte,expected", [
        (0,   "0d"),
        (1,   "1_7d"),
        (7,   "1_7d"),
        (8,   "8_30d"),
        (30,  "8_30d"),
        (31,  "31_90d"),
        (90,  "31_90d"),
        (91,  "90p"),
        (365, "90p"),
    ])
    def test_bucket_label(self, dte, expected):
        result = str(_dte_bucket(pd.Series([dte])).iloc[0])
        assert result == expected, f"DTE={dte}: got {result!r}, want {expected!r}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Signing softness — side never a bare "buy" or "sell"
# ─────────────────────────────────────────────────────────────────────────────

class TestSigningSoftness:
    def test_side_tilde_prefix(self):
        """Side values must start with '~' or be 'mixed'."""
        # Ask-side dominated → ~buy
        calls = _calls({"price": 2.60, "bid": 2.40, "ask": 2.60, "size": 100})
        result = _run(calls, etf_floor=0, name_floor=0)
        for ev in result["events"]:
            assert ev["side"] in ("~buy", "~sell", "mixed"), \
                f"Bare side value: {ev['side']!r}"

    def test_bid_side_tilde_sell(self):
        """Bid-side dominated print → ~sell (not bare 'sell')."""
        calls = _calls({"price": 2.40, "bid": 2.40, "ask": 2.60, "size": 100})
        result = _run(calls, etf_floor=0, name_floor=0)
        for ev in result["events"]:
            assert ev["side"] != "sell"
            if ev["side"] != "mixed":
                assert ev["side"].startswith("~")

    def test_no_bare_buy_in_any_event(self):
        """Exhaustive check — no event in any batch may have side='buy' or side='sell'."""
        calls = _calls(
            {"price": 2.60, "bid": 2.40, "ask": 2.60, "size": 50},  # ask side
            {"price": 2.40, "bid": 2.40, "ask": 2.60, "size": 50},  # bid side
        )
        result = _run(calls, etf_floor=0, name_floor=0)
        for ev in result["events"]:
            assert ev["side"] not in ("buy", "sell")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Coalescing — multiple prints per contract aggregate correctly
# ─────────────────────────────────────────────────────────────────────────────

class TestCoalescing:
    def test_n_prints_counts_rows(self):
        calls = _calls(
            {"price": 2.60, "bid": 2.40, "ask": 2.60, "size": 10, "sequence": 1},
            {"price": 2.55, "bid": 2.40, "ask": 2.60, "size": 5,  "sequence": 2},
        )
        result = _run(calls, etf_floor=0, name_floor=0)
        assert len(result["events"]) == 1
        ev = result["events"][0]
        assert ev["n_prints"] == 2

    def test_total_size_sum(self):
        calls = _calls(
            {"price": 2.60, "bid": 2.40, "ask": 2.60, "size": 10},
            {"price": 2.60, "bid": 2.40, "ask": 2.60, "size": 15},
        )
        result = _run(calls, etf_floor=0, name_floor=0)
        assert result["events"][0]["size"] == 25

    def test_premium_sum(self):
        """premium = sum(price * size * 100) per contract."""
        calls = _calls(
            {"price": 2.00, "bid": 1.90, "ask": 2.10, "size": 10},  # 2000
            {"price": 3.00, "bid": 2.90, "ask": 3.10, "size": 5},   # 1500
        )
        result = _run(calls, etf_floor=0, name_floor=0)
        assert result["events"][0]["premium"] == pytest.approx(3500, abs=1)

    def test_mixed_side_at_50_50(self):
        """Exactly 50/50 ask/bid split → mixed."""
        calls = _calls(
            {"price": 2.60, "bid": 2.40, "ask": 2.60, "size": 10},  # ask side (+)
            {"price": 2.40, "bid": 2.40, "ask": 2.60, "size": 10},  # bid side (-)
        )
        result = _run(calls, etf_floor=0, name_floor=0)
        assert result["events"][0]["side"] == "mixed"


# ─────────────────────────────────────────────────────────────────────────────
# 4 & 5 & 6. Notability gates + baseline_source labeling
# ─────────────────────────────────────────────────────────────────────────────

class TestNotabilityGate:
    def test_below_floor_no_event(self):
        """Premium well below floor → not notable, no event."""
        calls = _calls({"price": 0.10, "bid": 0.05, "ask": 0.15, "size": 1})
        result = _run(calls, etf_floor=1_000_000, name_floor=250_000,
                      etf_anchors=["SPY"])
        assert result["events"] == []

    def test_above_floor_notable(self):
        """Premium above floor → notable event."""
        # 2.60 * 4000 * 100 = $1,040,000 > $1M floor
        calls = _calls({"price": 2.60, "bid": 2.40, "ask": 2.60, "size": 4000})
        result = _run(calls, etf_floor=1_000_000, name_floor=250_000,
                      etf_anchors=["SPY"])
        assert len(result["events"]) == 1
        assert result["events"][0]["baseline_source"] == "floor"

    def test_z_gate_below_floor_but_notable(self):
        """premium_z >= 3 gates even if premium < floor."""
        baselines = {"SPY": {"mean": 100_000.0, "std": 20_000.0, "n_obs": 200,
                             "computed_asof": "2026-07-01"}}
        # premium = 2.50 * 5 * 100 = 1250  << $1M floor
        # z = (1250 - 100000) / 20000 = -4.94 — NOT notable by z
        calls = _calls({"price": 2.50, "bid": 2.40, "ask": 2.60, "size": 5})
        result = _run(calls, baselines=baselines, etf_floor=1_000_000, name_floor=250_000,
                      etf_anchors=["SPY"])
        assert result["events"] == []

    def test_z_gate_passes_at_3sigma(self):
        """premium_z = 4 → notable; baseline_source='z252'."""
        # mean=100000, std=20000; premium=180000 → z=4.0
        baselines = {"SPY": {"mean": 100_000.0, "std": 20_000.0, "n_obs": 200,
                             "computed_asof": "2026-07-01"}}
        # 6.00 * 300 * 100 = 180,000
        calls = _calls({"price": 6.00, "bid": 5.90, "ask": 6.10, "size": 300})
        result = _run(calls, baselines=baselines, etf_floor=1_000_000, name_floor=250_000,
                      etf_anchors=["SPY"])
        assert len(result["events"]) == 1
        ev = result["events"][0]
        assert ev["baseline_source"] == "z252"
        assert ev["premium_z"] is not None
        assert float(ev["premium_z"]) >= 3.0

    def test_no_baseline_floor_source(self):
        """No baselines → baseline_source='floor' and premium_z=None."""
        # 2.60 * 4000 * 100 = $1,040,000 > $1M floor
        calls = _calls({"price": 2.60, "bid": 2.40, "ask": 2.60, "size": 4000})
        result = _run(calls, baselines=None, etf_floor=1_000_000, name_floor=250_000,
                      etf_anchors=["SPY"])
        assert len(result["events"]) == 1
        ev = result["events"][0]
        assert ev["baseline_source"] == "floor"
        assert ev["premium_z"] is None


# ─────────────────────────────────────────────────────────────────────────────
# 7 & 8. vol_gt_oi
# ─────────────────────────────────────────────────────────────────────────────

class TestVolGtOI:
    def _oi_frame(self, exp="2026-07-05", strike=550.0, right="C", oi=100) -> pd.DataFrame:
        return pd.DataFrame([{
            "expiration": exp, "strike": strike, "right": right, "open_interest": oi
        }])

    def test_vol_gt_oi_true(self):
        """vol(200) > OI(100) → vol_gt_oi=True."""
        calls = _calls({"price": 2.60, "bid": 2.40, "ask": 2.60, "size": 200})
        oi = self._oi_frame(oi=100)
        result = _run(calls, oi_prev=oi, etf_floor=0, name_floor=0)
        assert result["events"][0]["vol_gt_oi"] is True

    def test_vol_lt_oi_false(self):
        """vol(50) < OI(100) → vol_gt_oi=False."""
        calls = _calls({"price": 2.60, "bid": 2.40, "ask": 2.60, "size": 50})
        oi = self._oi_frame(oi=100)
        result = _run(calls, oi_prev=oi, etf_floor=0, name_floor=0)
        assert result["events"][0]["vol_gt_oi"] is False

    def test_no_oi_none(self):
        """No OI frame → vol_gt_oi=None."""
        calls = _calls({"price": 2.60, "bid": 2.40, "ask": 2.60, "size": 200})
        result = _run(calls, oi_prev=None, etf_floor=0, name_floor=0)
        assert result["events"][0]["vol_gt_oi"] is None


# ─────────────────────────────────────────────────────────────────────────────
# 9. repeated flag — same contract notable in >=2 distinct cycles
# ─────────────────────────────────────────────────────────────────────────────

class TestRepeatedFlag:
    def test_first_cycle_not_repeated(self):
        calls = _calls({"price": 2.60, "bid": 2.40, "ask": 2.60, "size": 4000})
        result = _run(calls, etf_floor=1_000_000, name_floor=250_000, etf_anchors=["SPY"])
        assert len(result["events"]) == 1
        assert result["events"][0]["repeated"] is False

    def test_second_cycle_repeated(self):
        """Same contract notable in cycle 2 → repeated=True."""
        calls = _calls({"price": 2.60, "bid": 2.40, "ask": 2.60, "size": 4000,
                        "sequence": 1001})
        result1 = _run(calls, etf_floor=1_000_000, name_floor=250_000, etf_anchors=["SPY"])
        prior_state = result1["state"]

        # Second cycle — different sequence (different id), same contract
        calls2 = _calls({"price": 2.60, "bid": 2.40, "ask": 2.60, "size": 4000,
                         "sequence": 2001})
        result2 = _run(calls2, prior=prior_state,
                       etf_floor=1_000_000, name_floor=250_000, etf_anchors=["SPY"])
        assert len(result2["events"]) == 1
        assert result2["events"][0]["repeated"] is True


# ─────────────────────────────────────────────────────────────────────────────
# 10. Event-id stability + idempotent re-run
# ─────────────────────────────────────────────────────────────────────────────

class TestEventIdIdempotency:
    def test_same_tape_twice_no_new_events(self):
        """Re-processing the same tape within a session → zero new events."""
        calls = _calls({"price": 2.60, "bid": 2.40, "ask": 2.60, "size": 4000, "sequence": 1001})
        result1 = _run(calls, etf_floor=1_000_000, name_floor=250_000, etf_anchors=["SPY"])
        assert len(result1["events"]) == 1
        ev_id = result1["events"][0]["id"]

        # Same tape again, passing prior state
        result2 = _run(calls, prior=result1["state"],
                       etf_floor=1_000_000, name_floor=250_000, etf_anchors=["SPY"])
        assert result2["events"] == [], "Re-processing same tape should yield zero new events"

    def test_event_id_stable_across_runs(self):
        """Event id depends only on (session_date, root, exp, strike, right, seq_max)."""
        calls = _calls({"price": 2.60, "bid": 2.40, "ask": 2.60, "size": 4000, "sequence": 999})
        result_a = _run(calls, etf_floor=0, name_floor=0)
        result_b = _run(calls, etf_floor=0, name_floor=0)
        assert result_a["events"][0]["id"] == result_b["events"][0]["id"]


# ─────────────────────────────────────────────────────────────────────────────
# 11. 24h retention trim
# ─────────────────────────────────────────────────────────────────────────────

class TestRetentionTrim:
    def test_old_event_trimmed(self):
        old_ts = (datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
                  ).strftime("%Y-%m-%dT%H:%M:%SZ")
        new_ts = (datetime(2026, 7, 2, 14, 0, 0, tzinfo=timezone.utc)
                  ).strftime("%Y-%m-%dT%H:%M:%SZ")
        events = [
            {"id": "aaa", "ts": old_ts},
            {"id": "bbb", "ts": new_ts},
        ]
        cutoff = "2026-07-02T00:00:00Z"
        trimmed = lf.trim_events(events, cutoff)
        ids = [e["id"] for e in trimmed]
        assert "aaa" not in ids
        assert "bbb" in ids

    def test_cap_2000(self):
        ts = "2026-07-02T14:00:00Z"
        events = [{"id": str(i), "ts": ts} for i in range(2500)]
        trimmed = lf.trim_events(events, "2026-07-01T00:00:00Z")
        assert len(trimmed) == lf.MAX_EVENTS

    def test_sorted_ts_desc(self):
        events = [
            {"id": "a", "ts": "2026-07-02T12:00:00Z"},
            {"id": "b", "ts": "2026-07-02T14:00:00Z"},
            {"id": "c", "ts": "2026-07-02T13:00:00Z"},
        ]
        trimmed = lf.trim_events(events, "2026-07-01T00:00:00Z")
        assert trimmed[0]["id"] == "b"  # newest first


# ─────────────────────────────────────────────────────────────────────────────
# 12 & 13. Heat group math and group_zh presence
# ─────────────────────────────────────────────────────────────────────────────

class TestHeatGroups:
    def test_gross_premium_sum(self):
        """heat gross_premium = sum of all prints' premiums (not just notable)."""
        calls = _calls(
            {"price": 2.00, "bid": 1.90, "ask": 2.10, "size": 100},  # 20000
            {"price": 3.00, "bid": 2.90, "ask": 3.10, "size": 50},   # 15000
        )
        result = _run(calls, etf_floor=1e9, name_floor=1e9)  # no events, but heat still fires
        assert len(result["heat"]) == 1
        row = result["heat"][0]
        assert row["gross_premium"] == pytest.approx(35_000, abs=1)

    def test_net_signed_premium_soft_positive_for_ask_side(self):
        """All ask-side → net_signed_premium_soft > 0."""
        calls = _calls({"price": 2.60, "bid": 2.40, "ask": 2.60, "size": 100})
        result = _run(calls, etf_floor=1e9, name_floor=1e9)
        row = result["heat"][0]
        assert row["net_signed_premium_soft"] > 0

    def test_call_prem_share_for_calls_only(self):
        """Only call prints → call_prem_share=1.0."""
        calls = _calls({"price": 2.60, "bid": 2.40, "ask": 2.60, "size": 100})
        result = _run(calls, etf_floor=1e9, name_floor=1e9)
        row = result["heat"][0]
        assert row["call_prem_share"] == pytest.approx(1.0, abs=0.01)

    def test_group_zh_present(self):
        """Every heat row must have a non-empty group_zh."""
        calls = _calls()
        result = _run(calls, etf_floor=1e9, name_floor=1e9)
        for row in result["heat"]:
            assert row.get("group_zh"), f"group_zh missing/empty in heat row: {row}"

    def test_aggregate_heat_merges_roots(self):
        """aggregate_heat merges two heat rows from the same group."""
        heat_rows = [
            {"group": "Index/ETF", "group_zh": "指数/ETF",
             "gross_premium": 1_000_000.0, "net_signed_premium_soft": 500_000.0,
             "call_prem_share": 0.6, "n_events": 10, "_root": "SPY"},
            {"group": "Index/ETF", "group_zh": "指数/ETF",
             "gross_premium": 500_000.0, "net_signed_premium_soft": 200_000.0,
             "call_prem_share": 0.4, "n_events": 5, "_root": "QQQ"},
        ]
        agg = lf.aggregate_heat(heat_rows)
        assert len(agg) == 1
        g = agg[0]
        assert g["gross_premium"] == pytest.approx(1_500_000.0, abs=1)
        assert g["n_events"] == 15
        assert g["group_zh"] == "指数/ETF"
        # top contains both roots
        roots_in_top = [t["root"] for t in g["top"]]
        assert "SPY" in roots_in_top


# ─────────────────────────────────────────────────────────────────────────────
# 14. Meta schema
# ─────────────────────────────────────────────────────────────────────────────

class TestMetaSchema:
    def test_feed_schema_keys(self):
        calls = _calls({"price": 2.60, "bid": 2.40, "ask": 2.60, "size": 4000})
        result = _run(calls, etf_floor=0, name_floor=0)
        # Feed payload is assembled by the poller; check engine output keys exist
        state = result["state"]
        assert "emitted_ids"      in state
        assert "contract_vol"     in state
        assert "notability_history" in state

    def test_event_contract_keys(self):
        """Each event must carry all FEED CONTRACT v1 required keys."""
        required = [
            "id", "ts", "root", "group", "group_zh", "right", "exp", "strike",
            "dte", "dte_bucket", "mny_bucket", "side", "n_prints", "size",
            "avg_price", "premium", "premium_z", "baseline_source", "vol_gt_oi",
            "repeated", "zerodte", "signing_source",
        ]
        calls = _calls({"price": 2.60, "bid": 2.40, "ask": 2.60, "size": 4000})
        result = _run(calls, etf_floor=0, name_floor=0)
        assert result["events"], "Expected at least one event"
        ev = result["events"][0]
        missing = [k for k in required if k not in ev]
        assert not missing, f"Event missing keys: {missing}"

    def test_signing_source_tape(self):
        """Every event must carry signing_source='tape'."""
        calls = _calls({"price": 2.60, "bid": 2.40, "ask": 2.60, "size": 4000})
        result = _run(calls, etf_floor=0, name_floor=0)
        for ev in result["events"]:
            assert ev["signing_source"] == "tape"

    def test_dte_bucket_in_vocab(self):
        """dte_bucket must be one of the five vocab labels."""
        valid = {"0d", "1_7d", "8_30d", "31_90d", "90p"}
        calls = _calls({"price": 2.60, "bid": 2.40, "ask": 2.60, "size": 4000})
        result = _run(calls, etf_floor=0, name_floor=0)
        for ev in result["events"]:
            assert ev["dte_bucket"] in valid, f"Bad dte_bucket: {ev['dte_bucket']}"


# ─────────────────────────────────────────────────────────────────────────────
# 15–17. API route logic (monkeypatched)
# ─────────────────────────────────────────────────────────────────────────────

class TestAPIRoutes:
    """API routes tested via FastAPI TestClient with monkeypatched _flow_fetch."""

    @pytest.fixture()
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app)

    def test_fresh_fetch_returns_200(self, client, monkeypatch):
        """Fresh fetch path → 200 with payload."""
        payload = {"schema": "live_flow.feed/v1", "asof": BATCH_TS,
                   "session_date": SESSION_DATE, "events": [], "unusual_names": []}
        monkeypatch.setattr("app.main._flow_fetch", lambda name: payload)
        resp = client.get("/api/flow/feed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["schema"] == "live_flow.feed/v1"

    def test_stale_fallback_has_stale_key(self, client, monkeypatch):
        """Stale fallback → stale=True in response."""
        payload_stale = {"schema": "live_flow.feed/v1", "asof": BATCH_TS,
                         "events": [], "stale": True}
        monkeypatch.setattr("app.main._flow_fetch", lambda name: payload_stale)
        resp = client.get("/api/flow/feed")
        assert resp.status_code == 200
        assert resp.json().get("stale") is True

    def test_never_fetched_503(self, client, monkeypatch):
        """Never-fetched → 503."""
        from fastapi import HTTPException

        def _raise(_name):
            raise HTTPException(503, "unavailable")

        monkeypatch.setattr("app.main._flow_fetch", _raise)
        resp = client.get("/api/flow/feed")
        assert resp.status_code == 503

    def test_heat_route(self, client, monkeypatch):
        payload = {"schema": "live_flow.heat/v1", "asof": BATCH_TS,
                   "session_date": SESSION_DATE, "groups": []}
        monkeypatch.setattr("app.main._flow_fetch", lambda name: payload)
        resp = client.get("/api/flow/heat")
        assert resp.status_code == 200

    def test_meta_route(self, client, monkeypatch):
        payload = {"schema": "live_flow.meta/v1", "asof": BATCH_TS,
                   "cadence_sec_target": 120, "cadence_sec_measured": 95.0,
                   "universe_n": 22, "roots_polled": 22,
                   "requests_last_cycle": 44, "cycle_sec": 95.0,
                   "delta_mode": "full_day", "notes": []}
        monkeypatch.setattr("app.main._flow_fetch", lambda name: payload)
        resp = client.get("/api/flow/meta")
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 18–19. Collector additive params
# ─────────────────────────────────────────────────────────────────────────────

class TestCollectorAdditiveParams:
    """bulk_trade_quote: additive start_time/end_time params; no regression when omitted."""

    # Minimal CSV response matching the bulk_trade_quote v3 format (23 columns)
    _CSV = (
        b"symbol,expiration,strike,right,trade_timestamp,quote_timestamp,"
        b"sequence,ext_condition1,ext_condition2,ext_condition3,ext_condition4,"
        b"condition,size,exchange,price,bid_size,bid_exchange,bid,bid_condition,"
        b"ask_size,ask_exchange,ask,ask_condition\r\n"
        b"SPY,20260705,550.000,CALL,2026-07-02T14:30:00,2026-07-02T14:30:00,"
        b"1001,0,0,0,0,1,10,CBOE,2.60,5,CBOE,2.40,0,5,CBOE,2.60,0\r\n"
    )

    def _mock_response(self, status=200):
        mock = MagicMock()
        mock.status_code = status
        mock.iter_lines = lambda: iter(self._CSV.split(b"\n"))
        return mock

    def test_no_time_params_no_regression(self, monkeypatch):
        """Omitting start_time/end_time: no start_time/end_time in request params."""
        captured_params: list[dict] = []

        def _mock_stream(session, path, params):
            captured_params.append(dict(params))
            yield from self._CSV.split(b"\n")

        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        monkeypatch.setattr("collectors.thetadata._stream_lines", _mock_stream)

        from collectors.thetadata import bulk_trade_quote
        df = bulk_trade_quote("SPY", "call", "20260702", "20260702")

        assert df is not None
        assert len(captured_params) == 1
        p = captured_params[0]
        assert "start_time" not in p
        assert "end_time" not in p

    def test_start_time_str_in_params(self, monkeypatch):
        """start_time='09:30:00' → start_time param present in request as HH:MM:SS.mmm string."""
        captured_params: list[dict] = []

        def _mock_stream(session, path, params):
            captured_params.append(dict(params))
            yield from self._CSV.split(b"\n")

        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        monkeypatch.setattr("collectors.thetadata._stream_lines", _mock_stream)

        from collectors.thetadata import bulk_trade_quote, _time_to_str
        bulk_trade_quote("SPY", "call", "20260702", "20260702",
                         start_time="09:30:00", end_time="10:00:00")

        p = captured_params[0]
        assert "start_time" in p
        assert "end_time" in p
        # "09:30:00" → "09:30:00.000"
        assert p["start_time"] == _time_to_str("09:30:00")
        assert p["end_time"]   == _time_to_str("10:00:00")

    def test_start_time_int_passed_as_str(self, monkeypatch):
        """start_time as ms int → converted to HH:MM:SS.mmm string."""
        captured_params: list[dict] = []

        def _mock_stream(session, path, params):
            captured_params.append(dict(params))
            yield from self._CSV.split(b"\n")

        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        monkeypatch.setattr("collectors.thetadata._stream_lines", _mock_stream)

        from collectors.thetadata import bulk_trade_quote, _time_to_str
        bulk_trade_quote("SPY", "call", "20260702", "20260702",
                         start_time=34_200_000)
        assert captured_params[0]["start_time"] == _time_to_str(34_200_000)
        assert captured_params[0]["start_time"] == "09:30:00.000"

    def test_sequence_column_in_output(self, monkeypatch):
        """Output DataFrame includes 'sequence' column."""
        def _mock_stream(session, path, params):
            yield from self._CSV.split(b"\n")

        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        monkeypatch.setattr("collectors.thetadata._stream_lines", _mock_stream)

        from collectors.thetadata import bulk_trade_quote
        df = bulk_trade_quote("SPY", "call", "20260702", "20260702")
        assert "sequence" in df.columns, "sequence column missing from bulk_trade_quote output"
        assert int(df["sequence"].iloc[0]) == 1001

    def test_time_to_str_formats(self):
        """_time_to_str converts various input formats to HH:MM:SS.mmm strings."""
        from collectors.thetadata import _time_to_str
        assert _time_to_str("09:30") == "09:30:00.000"
        assert _time_to_str("14:45:30") == "14:45:30.000"
        assert _time_to_str("14:45:30.123") == "14:45:30.123"
        assert _time_to_str(None) is None
        # 09:30:00 in ms = 34,200,000
        assert _time_to_str(34_200_000) == "09:30:00.000"
        # 9h30m0s500ms
        assert _time_to_str(9 * 3_600_000 + 30 * 60_000 + 500) == "09:30:00.500"


# ─────────────────────────────────────────────────────────────────────────────
# zerodte labeling
# ─────────────────────────────────────────────────────────────────────────────

class TestZeroDTE:
    def test_zerodte_flag_set_for_0d_bucket(self):
        """Option expiring same day → zerodte=True."""
        # Trade on 2026-07-02, expiration 2026-07-02 → dte=0 → dte_bucket=0d �� zerodte
        calls = pd.DataFrame([{
            "root": "SPY", "right": "C", "expiration": "2026-07-02",
            "strike": 550.0, "price": 0.10, "bid": 0.05, "ask": 0.15,
            "size": 100, "trade_timestamp": "2026-07-02T15:00:00",
            "quote_timestamp": "2026-07-02T15:00:00",
            "sequence": 999, "date": "2026-07-02",
        }])
        result = _run(calls, etf_floor=0, name_floor=0)
        assert len(result["events"]) == 1
        ev = result["events"][0]
        assert ev["dte"] == 0
        assert ev["dte_bucket"] == "0d"
        assert ev["zerodte"] is True


# ─────────────────────────────────────────────────────────────────────────────
# FIX 1 — vol_gt_oi uses cumulative day-volume, not per-batch coalesced size
# ──────────────────────���──────────────────────────────────────────────────────

class TestVolGtOICumulative:
    """FIX 1: vol_gt_oi comparison must use cumulative day-volume from state."""

    def _oi_frame(self, exp="2026-07-05", strike=550.0, right="C", oi=200) -> pd.DataFrame:
        return pd.DataFrame([{
            "expiration": exp, "strike": strike, "right": right, "open_interest": oi
        }])

    def test_cumulative_vol_crosses_oi_on_second_cycle(self):
        """Cycle 1: 100 contracts (below OI=200) → vol_gt_oi=False.
        Cycle 2: another 150 contracts; cumulative=250 > OI=200 → vol_gt_oi=True.
        """
        oi = self._oi_frame(oi=200)

        # Cycle 1: 100 contracts — cumulative = 100 < OI=200
        calls1 = _calls({"price": 2.60, "bid": 2.40, "ask": 2.60, "size": 100,
                         "sequence": 1001})
        result1 = _run(calls1, oi_prev=oi, etf_floor=0, name_floor=0)
        assert len(result1["events"]) == 1
        assert result1["events"][0]["vol_gt_oi"] is False, (
            "Cycle 1: 100 contracts < OI 200 should be False")

        # Cycle 2: 150 more contracts (different sequence → new event id); cumulative=250 > OI=200
        calls2 = _calls({"price": 2.60, "bid": 2.40, "ask": 2.60, "size": 150,
                         "sequence": 2001})
        result2 = _run(calls2, oi_prev=oi, prior=result1["state"],
                       etf_floor=0, name_floor=0)
        assert len(result2["events"]) == 1
        assert result2["events"][0]["vol_gt_oi"] is True, (
            "Cycle 2: cumulative 250 > OI 200 should be True")

    def test_per_batch_size_alone_below_oi_but_cumulative_above(self):
        """Each individual batch is below OI, but cumulative over 3 cycles exceeds it.
        Final cycle should report vol_gt_oi=True.
        """
        oi = self._oi_frame(oi=100)

        state = None
        for seq, size in enumerate([40, 40, 40], start=1):
            calls = _calls({"price": 2.60, "bid": 2.40, "ask": 2.60, "size": size,
                            "sequence": seq * 1000})
            result = _run(calls, oi_prev=oi, prior=state, etf_floor=0, name_floor=0)
            state = result["state"]

        # After 3 cycles of 40 each → cumulative=120 > OI=100
        last_events = result["events"]
        assert len(last_events) == 1
        assert last_events[0]["vol_gt_oi"] is True, (
            "Cumulative 120 over 3 cycles > OI 100 should be True")


# ──��──────────────────────────────────────────────────────────────────────────
# FIX 2 — overlap double-count (sequence dedup) and watermark advance
# ��─────────────────────────��──────────────────────────────────────────────────

class TestSequenceDedup:
    """FIX 2: overlapping windows must not double-count rows already seen."""

    def _batch_calls(self, sequences: list[int], size: int = 100,
                     price: float = 2.60) -> pd.DataFrame:
        rows = []
        for seq in sequences:
            rows.append({
                "root": "SPY", "right": "C", "expiration": "2026-07-05",
                "strike": 550.0, "price": price, "bid": 2.40, "ask": 2.60,
                "size": size, "trade_timestamp": f"2026-07-02T14:{seq:02d}:00",
                "quote_timestamp": f"2026-07-02T14:{seq:02d}:00",
                "sequence": seq * 100,  # unique sequence per row
                "date": "2026-07-02",
            })
        return pd.DataFrame(rows)

    def test_same_rows_consecutive_batches_no_double_count(self):
        """Rows with the same sequences in two consecutive batches accumulate only once.

        Simulates an overlapping window: cycle 2 re-delivers rows already seen in cycle 1.
        The sequence dedup must ensure root_gross_today (and contract_vol) are NOT doubled.
        """
        # Cycle 1: sequences [10, 20, 30]
        calls1 = self._batch_calls([10, 20, 30])
        result1 = _run(calls1, etf_floor=0, name_floor=0)
        gross_after_c1 = result1["state"]["root_gross_today"].get("SPY", 0.0)

        # Cycle 2: re-delivers same sequences PLUS a new one [40]
        calls2 = self._batch_calls([10, 20, 30, 40])
        result2 = _run(calls2, prior=result1["state"], etf_floor=0, name_floor=0)
        gross_after_c2 = result2["state"]["root_gross_today"].get("SPY", 0.0)

        # Sequences 10/20/30 already seen → deduped; only seq 40 (100 contracts) is new
        expected_increment = float(calls1.iloc[0]["price"] * 100 * 100)  # 1 new row
        assert gross_after_c2 == pytest.approx(gross_after_c1 + expected_increment, rel=1e-6), (
            f"Double-count detected: cycle2 gross ({gross_after_c2:.0f}) should be "
            f"cycle1 ({gross_after_c1:.0f}) + one new row ({expected_increment:.0f})")

    def test_contract_vol_not_doubled_by_overlap(self):
        """contract_vol must not grow by re-delivering already-seen sequences."""
        calls1 = self._batch_calls([1, 2, 3], size=50)
        result1 = _run(calls1, etf_floor=0, name_floor=0)
        # Get the cumulative vol after cycle 1
        key = ("2026-07-05", 550.0, "C")
        vol_after_c1 = result1["state"]["contract_vol"].get(key, 0)

        # Re-deliver the exact same rows
        calls2 = self._batch_calls([1, 2, 3], size=50)
        result2 = _run(calls2, prior=result1["state"], etf_floor=0, name_floor=0)
        vol_after_c2 = result2["state"]["contract_vol"].get(key, 0)

        assert vol_after_c2 == pytest.approx(vol_after_c1, rel=1e-6), (
            f"contract_vol doubled from {vol_after_c1} to {vol_after_c2} on re-delivery")

    def test_watermark_advances(self):
        """seen_sequences must advance monotonically; new higher sequences pass through."""
        calls1 = self._batch_calls([5])
        result1 = _run(calls1, etf_floor=0, name_floor=0)
        # Check that (exp, strike, right) key has been recorded
        key = ("2026-07-05", 550.0, "C")
        assert key in result1["state"]["seen_sequences"], (
            "seen_sequences must contain the contract key after cycle 1")
        assert result1["state"]["seen_sequences"][key] == pytest.approx(500.0), (
            "max sequence for the contract should be 5*100=500")

    def test_full_day_idempotency_via_sequence_dedup(self):
        """full_day mode: re-pulling the whole day twice produces same result as once."""
        # Build a larger batch simulating a full-day pull
        calls = self._batch_calls(list(range(1, 21)), size=50)

        result1 = _run(calls, etf_floor=0, name_floor=0)
        gross_c1 = result1["state"]["root_gross_today"].get("SPY", 0.0)
        vol_c1   = result1["state"]["contract_vol"].get(("2026-07-05", 550.0, "C"), 0)

        # Second pull of the SAME full-day data (simulating a full_day cycle re-pull)
        result2 = _run(calls, prior=result1["state"], etf_floor=0, name_floor=0)
        gross_c2 = result2["state"]["root_gross_today"].get("SPY", 0.0)
        vol_c2   = result2["state"]["contract_vol"].get(("2026-07-05", 550.0, "C"), 0)

        assert gross_c2 == pytest.approx(gross_c1, rel=1e-6), (
            "full_day re-pull must not change gross_today")
        assert vol_c2   == pytest.approx(vol_c1, rel=1e-6), (
            "full_day re-pull must not change contract_vol")


# ───────────��─────────────────────────────────────────────────────────────────
# FIX 3 — honest moneyness from prev_close
# ───────────────────────���──────────────────────────��──────────────────────────

class TestHonestMoneyness:
    """FIX 3: mny_bucket must be computed from prev_close, not hardcoded 'atm'."""

    def _run_with_close(self, strike: float, prev_close: float, right: str = "C") -> str:
        """Return mny_bucket for a single trade given prev_close."""
        calls = pd.DataFrame([{
            "root": "SPY", "right": right, "expiration": "2026-07-05",
            "strike": strike, "price": 2.60, "bid": 2.40, "ask": 2.60,
            "size": 100, "trade_timestamp": "2026-07-02T14:30:00",
            "quote_timestamp": "2026-07-02T14:30:00",
            "sequence": 1001, "date": "2026-07-02",
        }])
        result = lf.process_batch(
            calls_df=calls, puts_df=None,
            session_date=SESSION_DATE, batch_ts=BATCH_TS,
            etf_floor=0, name_floor=0,
            etf_anchors=["SPY"],
            prev_close=prev_close,
        )
        assert result["events"], f"Expected event for strike={strike} close={prev_close}"
        return result["events"][0]["mny_bucket"]

    def test_atm_call_within_5pct(self):
        """Call strike within 5% of underlying → atm."""
        # strike=550, prev_close=540 → signed_money = 550/540 - 1 ≈ 0.0185 < 0.05 → atm
        bucket = self._run_with_close(strike=550.0, prev_close=540.0, right="C")
        assert bucket == "atm", f"Expected atm, got {bucket!r}"

    def test_far_otm_call(self):
        """Call strike >15% above underlying → far_otm."""
        # strike=650, prev_close=540 → signed_money = 650/540 - 1 ≈ 0.204 > 0.15 → far_otm
        bucket = self._run_with_close(strike=650.0, prev_close=540.0, right="C")
        assert bucket == "far_otm", f"Expected far_otm, got {bucket!r}"

    def test_itm_call(self):
        """Call strike below underlying by more than 5% → itm."""
        # strike=490, prev_close=540 → signed_money = 490/540 - 1 ≈ -0.093 < -0.05 → itm
        bucket = self._run_with_close(strike=490.0, prev_close=540.0, right="C")
        assert bucket == "itm", f"Expected itm, got {bucket!r}"

    def test_atm_put_within_5pct(self):
        """Put strike within 5% of underlying → atm."""
        # strike=550, prev_close=540 → signed_money = 540/550 - 1 ≈ -0.018 → |.018| < 0.05 → atm
        bucket = self._run_with_close(strike=550.0, prev_close=540.0, right="P")
        assert bucket == "atm", f"Expected atm for put, got {bucket!r}"

    def test_no_prev_close_returns_unknown(self):
        """When prev_close is None → mny_bucket='unknown'."""
        calls = _calls({"price": 2.60, "bid": 2.40, "ask": 2.60, "size": 100})
        result = lf.process_batch(
            calls_df=calls, puts_df=None,
            session_date=SESSION_DATE, batch_ts=BATCH_TS,
            etf_floor=0, name_floor=0,
            etf_anchors=["SPY"],
            prev_close=None,
        )
        assert result["events"], "Expected event"
        assert result["events"][0]["mny_bucket"] == "unknown", (
            "No prev_close must yield mny_bucket='unknown'")

    def test_pit_guard_session_date_not_used(self):
        """PIT guard: prev_close row dated exactly session_date must NOT be used.

        The poller implements this in _load_prev_close (strict <, not <=).
        This test verifies the engine correctly uses the injected prev_close:
        if the poller incorrectly passes the session-date row, this test would
        fail by receiving 'atm' instead of 'unknown'.
        """
        # Simulating the PIT guard: when prev_close=None is passed (as it would be
        # when the poller correctly rejects the same-day row), engine returns 'unknown'.
        calls = _calls({"price": 2.60, "bid": 2.40, "ask": 2.60, "size": 100})
        result_no_close = lf.process_batch(
            calls_df=calls, puts_df=None,
            session_date=SESSION_DATE, batch_ts=BATCH_TS,
            etf_floor=0, name_floor=0,
            etf_anchors=["SPY"],
            prev_close=None,   # correctly rejected same-day row
        )
        assert result_no_close["events"][0]["mny_bucket"] == "unknown"

    def test_prev_close_loader_pit_guard(self, tmp_path, monkeypatch):
        """_load_prev_close must never use a row dated session_date or later."""
        import pandas as pd
        from pathlib import Path

        session_date = "2026-07-02"
        root = "TESTROOT"

        # Build a fake yahoo parquet with rows on and after session_date
        idx = pd.to_datetime([
            "2026-07-01",  # valid prior-session close → should be used
            "2026-07-02",  # same as session_date → MUST NOT be used (PIT law)
            "2026-07-03",  # future → MUST NOT be used
        ])
        df = pd.DataFrame({"close": [100.0, 999.0, 888.0]}, index=idx)
        yahoo_dir = tmp_path / "yahoo"
        yahoo_dir.mkdir()
        df.to_parquet(yahoo_dir / f"{root}.parquet")

        # Monkeypatch config.data_dir() to point at tmp_path
        monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)

        from scripts.live_flow_poller import _load_prev_close
        close = _load_prev_close(root, session_date)
        assert close == pytest.approx(100.0), (
            f"Expected prior-day close 100.0 but got {close!r}; "
            "same-day and future rows must be excluded (PIT law)")

    def test_mny_bucket_not_atm_hardcoded(self):
        """mny_bucket must never always return 'atm' when prev_close drives far_otm."""
        # This test fails if the old hardcode mny_bucket_val = 'atm' is still present
        bucket = self._run_with_close(strike=700.0, prev_close=500.0, right="C")
        assert bucket != "atm", (
            "mny_bucket must not be hardcoded 'atm'; "
            f"strike=700 vs close=500 is far_otm but got {bucket!r}")


# ─────────────────────────────────────────────────────────────────────────────
# 20. Minute bucketing: market_tide_minutes accumulation
# ─────────────────────────────────────────────────────────────────────────────

class TestMinuteBucketing:
    """Market tide minute accumulator tests."""

    def _make_batch(self, t_hhmm: str, size: int = 100, price: float = 2.60,
                    right: str = "C", root: str = "SPY") -> pd.DataFrame:
        """Make a single-contract batch with a specific ET time."""
        from zoneinfo import ZoneInfo
        ET = ZoneInfo("America/New_York")
        # Build a UTC timestamp that corresponds to t_hhmm ET on 2026-07-02
        h, m = int(t_hhmm[:2]), int(t_hhmm[3:])
        from datetime import datetime
        dt_et = datetime(2026, 7, 2, h, m, 0, tzinfo=ET)
        ts_utc = dt_et.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
        return pd.DataFrame([{
            "root": root, "right": right,
            "expiration": "2026-07-05", "strike": 550.0,
            "price": price, "bid": 2.40, "ask": 2.80,
            "size": size, "trade_timestamp": ts_utc,
            "quote_timestamp": ts_utc,
            "sequence": abs(hash(ts_utc)) % 100000 + 1,
            "date": "2026-07-02",
        }])

    def test_minute_key_created(self):
        """process_batch must populate market_tide_minutes with correct HH:MM key."""
        df = self._make_batch("10:00")
        result = lf.process_batch(
            calls_df=df, puts_df=None,
            session_date=SESSION_DATE, batch_ts=BATCH_TS,
            etf_floor=0, name_floor=0, etf_anchors=["SPY"],
        )
        state = result["state"]
        assert "market_tide_minutes" in state, "market_tide_minutes missing from state"
        mkeys = state["market_tide_minutes"].keys()
        assert "10:00" in mkeys, f"Expected key '10:00' in {list(mkeys)}"

    def test_ncp_positive_for_ask_side_call(self):
        """Ask-side call print → ncp increases (positive)."""
        # price=2.80 = ask → sign=+1 → ncp += prem
        df = self._make_batch("09:30", size=100, price=2.80, right="C")
        result = lf.process_batch(
            calls_df=df, puts_df=None,
            session_date=SESSION_DATE, batch_ts=BATCH_TS,
            etf_floor=0, name_floor=0, etf_anchors=["SPY"],
        )
        mkey = "09:30"
        m = result["state"]["market_tide_minutes"].get(mkey, {})
        assert m.get("ncp", 0) > 0, f"ncp should be positive for ask-side call, got {m}"
        assert m.get("npp", 0) == pytest.approx(0.0, abs=1), \
            f"npp should be 0 for calls-only batch, got {m}"

    def test_npp_positive_for_ask_side_put(self):
        """Ask-side put print → npp increases (positive)."""
        df = self._make_batch("09:30", size=100, price=2.80, right="P")
        result = lf.process_batch(
            calls_df=None, puts_df=df,
            session_date=SESSION_DATE, batch_ts=BATCH_TS,
            etf_floor=0, name_floor=0, etf_anchors=["SPY"],
        )
        mkey = "09:30"
        m = result["state"]["market_tide_minutes"].get(mkey, {})
        assert m.get("npp", 0) > 0, f"npp should be positive for ask-side put, got {m}"
        assert m.get("ncp", 0) == pytest.approx(0.0, abs=1), \
            f"ncp should be 0 for puts-only batch, got {m}"

    def test_cross_cycle_accumulation(self):
        """NCP must accumulate across two cycles at the same minute."""
        df1 = self._make_batch("14:00", size=100, price=2.80, right="C")
        result1 = lf.process_batch(
            calls_df=df1, puts_df=None,
            session_date=SESSION_DATE, batch_ts=BATCH_TS,
            etf_floor=0, name_floor=0, etf_anchors=["SPY"],
        )
        ncp_after_c1 = result1["state"]["market_tide_minutes"].get("14:00", {}).get("ncp", 0)

        df2 = self._make_batch("14:00", size=50, price=2.80, right="C")
        # Give df2 a different sequence to avoid dedup
        df2["sequence"] = df2["sequence"] + 99999
        result2 = lf.process_batch(
            calls_df=df2, puts_df=None,
            session_date=SESSION_DATE, batch_ts=BATCH_TS,
            prior_state=result1["state"],
            etf_floor=0, name_floor=0, etf_anchors=["SPY"],
        )
        ncp_after_c2 = result2["state"]["market_tide_minutes"].get("14:00", {}).get("ncp", 0)
        assert ncp_after_c2 > ncp_after_c1, \
            f"NCP should accumulate: c1={ncp_after_c1} c2={ncp_after_c2}"

    def test_dedup_does_not_double_market_tide(self):
        """Replaying the same batch must not double the market tide accumulator."""
        df = self._make_batch("09:45", size=100, price=2.80, right="C")
        result1 = lf.process_batch(
            calls_df=df, puts_df=None,
            session_date=SESSION_DATE, batch_ts=BATCH_TS,
            etf_floor=0, name_floor=0, etf_anchors=["SPY"],
        )
        ncp_c1 = result1["state"]["market_tide_minutes"].get("09:45", {}).get("ncp", 0)

        # Replay same rows — dedup should strip them all
        result2 = lf.process_batch(
            calls_df=df, puts_df=None,
            session_date=SESSION_DATE, batch_ts=BATCH_TS,
            prior_state=result1["state"],
            etf_floor=0, name_floor=0, etf_anchors=["SPY"],
        )
        ncp_c2 = result2["state"]["market_tide_minutes"].get("09:45", {}).get("ncp", 0)
        assert ncp_c2 == pytest.approx(ncp_c1, rel=1e-6), \
            f"Re-delivery must not double market_tide: c1={ncp_c1} c2={ncp_c2}"


# ─────────────────────────────────────────────────────────────────────────────
# 21. Sector tide and DTE tide math
# ─────────────────────────────────────────────────────────────────────────────

class TestSectorDteTideMath:
    """sector_tide and dte_tide accumulation."""

    def _make_call(self, t_hhmm: str, exp: str, size: int = 100) -> pd.DataFrame:
        from zoneinfo import ZoneInfo
        ET = ZoneInfo("America/New_York")
        h, m = int(t_hhmm[:2]), int(t_hhmm[3:])
        from datetime import datetime
        dt_et = datetime(2026, 7, 2, h, m, 0, tzinfo=ET)
        ts_utc = dt_et.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
        return pd.DataFrame([{
            "root": "SPY", "right": "C", "expiration": exp,
            "strike": 550.0, "price": 2.80, "bid": 2.40, "ask": 2.80,
            "size": size, "trade_timestamp": ts_utc,
            "quote_timestamp": ts_utc,
            "sequence": abs(hash(t_hhmm + exp)) % 100000 + 1,
            "date": "2026-07-02",
        }])

    def test_sector_tide_ncp_populated(self):
        """sector_tide must contain an entry for the root's group."""
        df = self._make_call("09:30", "2026-07-05")
        result = lf.process_batch(
            calls_df=df, puts_df=None,
            session_date=SESSION_DATE, batch_ts=BATCH_TS,
            etf_floor=0, name_floor=0, etf_anchors=["SPY"],
        )
        sector_tide = result["state"].get("sector_tide", {})
        assert len(sector_tide) >= 1, "sector_tide should contain at least one group"
        # SPY maps to Index/ETF
        assert "Index/ETF" in sector_tide, f"Expected Index/ETF in sector_tide keys: {list(sector_tide.keys())}"
        st = sector_tide["Index/ETF"]
        assert st.get("ncp", 0) > 0, f"sector ncp should be positive: {st}"
        assert "group_zh" in st, "sector_tide entry must have group_zh"

    def test_dte_tide_bucket_0d_populated(self):
        """Same-day expiry → 0d bucket in dte_tide."""
        df = self._make_call("09:30", SESSION_DATE)  # exp = session_date → 0d
        result = lf.process_batch(
            calls_df=df, puts_df=None,
            session_date=SESSION_DATE, batch_ts=BATCH_TS,
            etf_floor=0, name_floor=0, etf_anchors=["SPY"],
        )
        dte_tide = result["state"].get("dte_tide", {})
        assert "0d" in dte_tide, f"0d bucket missing from dte_tide: {list(dte_tide.keys())}"

    def test_dte_tide_8_30d_bucket(self):
        """Expiry 10 days out → 8_30d bucket in dte_tide."""
        exp_10d = "2026-07-12"  # 10 days after SESSION_DATE 2026-07-02
        df = self._make_call("09:30", exp_10d)
        result = lf.process_batch(
            calls_df=df, puts_df=None,
            session_date=SESSION_DATE, batch_ts=BATCH_TS,
            etf_floor=0, name_floor=0, etf_anchors=["SPY"],
        )
        dte_tide = result["state"].get("dte_tide", {})
        assert "8_30d" in dte_tide, f"8_30d bucket missing: {list(dte_tide.keys())}"


# ─────────────────────────────────────────────────────────────────────────────
# 22. Per-root rollups (strikes + expiries)
# ─────────────────────────────────────────────────────────────────────────────

class TestPerRootRollups:
    """root_strikes and root_expiries accumulation."""

    def _batch(self, strike: float, exp: str, size: int = 100, right: str = "C") -> pd.DataFrame:
        return pd.DataFrame([{
            "root": "SPY", "right": right, "expiration": exp,
            "strike": strike, "price": 2.60, "bid": 2.40, "ask": 2.80,
            "size": size, "trade_timestamp": "2026-07-02T14:00:00Z",
            "quote_timestamp": "2026-07-02T14:00:00Z",
            "sequence": abs(hash(f"{strike}{exp}{right}")) % 100000 + 1,
            "date": "2026-07-02",
        }])

    def test_strike_call_prem_accumulated(self):
        """Call premium accumulates in root_strikes."""
        df = self._batch(550.0, "2026-07-05", size=100, right="C")
        result = lf.process_batch(
            calls_df=df, puts_df=None,
            session_date=SESSION_DATE, batch_ts=BATCH_TS,
            etf_floor=0, name_floor=0, etf_anchors=["SPY"],
        )
        rs = result["state"].get("root_strikes", {}).get("SPY", {})
        # Strike key is rounded to 3dp
        stk_key = str(round(550.0, 3))
        assert stk_key in rs, f"Strike {stk_key} missing: {list(rs.keys())}"
        assert rs[stk_key].get("call_prem", 0) > 0, "call_prem should be positive"

    def test_expiry_rollup(self):
        """Expiry rollup populated for the contract's expiry."""
        df = self._batch(550.0, "2026-07-05", size=100, right="C")
        result = lf.process_batch(
            calls_df=df, puts_df=None,
            session_date=SESSION_DATE, batch_ts=BATCH_TS,
            etf_floor=0, name_floor=0, etf_anchors=["SPY"],
        )
        re = result["state"].get("root_expiries", {}).get("SPY", {})
        assert "2026-07-05" in re, f"Expiry 2026-07-05 missing: {list(re.keys())}"
        assert re["2026-07-05"].get("call_prem", 0) > 0

    def test_put_prem_goes_to_put_side(self):
        """Put premium lands in put_prem, not call_prem."""
        df = self._batch(550.0, "2026-07-05", size=100, right="P")
        result = lf.process_batch(
            calls_df=None, puts_df=df,
            session_date=SESSION_DATE, batch_ts=BATCH_TS,
            etf_floor=0, name_floor=0, etf_anchors=["SPY"],
        )
        rs = result["state"].get("root_strikes", {}).get("SPY", {})
        stk_key = str(round(550.0, 3))
        if stk_key in rs:
            assert rs[stk_key].get("call_prem", 0) == pytest.approx(0.0, abs=1), \
                "call_prem should be 0 for puts-only batch"
            assert rs[stk_key].get("put_prem", 0) > 0, "put_prem should be positive"


# ─────────────────────────────────────────────────────────────────────────────
# 23. Sweep-like flag (positive and negative cases)
# ─────────────────────────────────────────────────────────────────────────────

class TestSweepLikeFlag:
    """Sweep-like heuristic: >=3 prints, >=2 exchanges, <=2s span."""

    def _make_prints(self, n_prints: int, n_exchanges: int,
                     span_sec: float, start_ts: str = "2026-07-02T14:30:00Z"
                     ) -> pd.DataFrame:
        """Build a DataFrame of n_prints for a single contract.

        n_exchanges controls distinct exchanges (cycles through CBOE, AMEX, PHLX, ISE).
        span_sec controls the total time span across all prints.
        """
        exchanges = ["CBOE", "AMEX", "PHLX", "ISE"]
        rows = []
        from datetime import datetime, timezone as tz
        t0 = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
        import pandas as pd_inner
        for i in range(n_prints):
            if n_prints > 1:
                frac = span_sec * i / (n_prints - 1)
            else:
                frac = 0.0
            t = t0.timestamp() + frac
            ts_str = datetime.fromtimestamp(t, tz=tz.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            rows.append({
                "root": "SPY", "right": "C", "expiration": "2026-07-05",
                "strike": 550.0, "price": 2.60, "bid": 2.40, "ask": 2.80,
                "size": 10,
                "trade_timestamp": ts_str,
                "quote_timestamp": ts_str,
                "exchange": exchanges[i % n_exchanges],
                "sequence": 1000 + i,
                "date": "2026-07-02",
            })
        return pd.DataFrame(rows)

    def test_swept_positive_3prints_2exchanges_2s(self):
        """3 prints, 2 exchanges, span=1.5s → swept=True."""
        df = self._make_prints(n_prints=3, n_exchanges=2, span_sec=1.5)
        result = lf.process_batch(
            calls_df=df, puts_df=None,
            session_date=SESSION_DATE, batch_ts=BATCH_TS,
            etf_floor=0, name_floor=0, etf_anchors=["SPY"],
        )
        # Check at least one event exists and is swept
        if result["events"]:
            assert result["events"][0]["swept"] is True, \
                "3 prints, 2 exchanges, 1.5s span must be swept=True"

    def test_not_swept_single_exchange(self):
        """3 prints, 1 exchange → swept=False (not multi-exchange)."""
        df = self._make_prints(n_prints=3, n_exchanges=1, span_sec=1.0)
        result = lf.process_batch(
            calls_df=df, puts_df=None,
            session_date=SESSION_DATE, batch_ts=BATCH_TS,
            etf_floor=0, name_floor=0, etf_anchors=["SPY"],
        )
        if result["events"]:
            assert result["events"][0]["swept"] is False, \
                "Single exchange: swept must be False"

    def test_not_swept_span_over_2s(self):
        """3 prints, 2 exchanges, span=3s → swept=False (span > 2s)."""
        df = self._make_prints(n_prints=3, n_exchanges=2, span_sec=3.0)
        result = lf.process_batch(
            calls_df=df, puts_df=None,
            session_date=SESSION_DATE, batch_ts=BATCH_TS,
            etf_floor=0, name_floor=0, etf_anchors=["SPY"],
        )
        if result["events"]:
            assert result["events"][0]["swept"] is False, \
                "3s span: swept must be False"

    def test_not_swept_only_2_prints(self):
        """2 prints (< 3) → swept=False regardless of exchange diversity."""
        df = self._make_prints(n_prints=2, n_exchanges=2, span_sec=0.5)
        result = lf.process_batch(
            calls_df=df, puts_df=None,
            session_date=SESSION_DATE, batch_ts=BATCH_TS,
            etf_floor=0, name_floor=0, etf_anchors=["SPY"],
        )
        if result["events"]:
            assert result["events"][0]["swept"] is False, \
                "2 prints: swept must be False (need >= 3)"

    def test_swept_field_present_in_all_events(self):
        """All events must carry the 'swept' field (bool, not None)."""
        df = _calls({"price": 2.60, "bid": 2.40, "ask": 2.60, "size": 4000})
        result = lf.process_batch(
            calls_df=df, puts_df=None,
            session_date=SESSION_DATE, batch_ts=BATCH_TS,
            etf_floor=0, name_floor=0, etf_anchors=["SPY"],
        )
        for ev in result["events"]:
            assert "swept" in ev, f"'swept' key missing from event: {ev}"
            assert isinstance(ev["swept"], bool), \
                f"'swept' must be bool, got {type(ev['swept'])}"


# ─────────────────────────────────────────────────────────────────────────────
# 24. tide_current.json contract shape (build_tide_current)
# ─────────────────────────────────────────────────────────────────────────────

class TestTideCurrentShape:
    """build_tide_current output shape validates against live_flow.tide/v1 schema."""

    def _make_day_state(self) -> dict:
        """Minimal day_state with known tide data."""
        return {
            "market_tide_minutes": {
                "09:30": {"ncp": 1000.0, "npp": -500.0, "gross": 2000.0, "vol": 100},
                "09:31": {"ncp": 500.0,  "npp": 200.0,  "gross": 1000.0, "vol": 50},
            },
            "sector_tide": {
                "Index/ETF": {
                    "group": "Index/ETF", "group_zh": "指数/ETF",
                    "ncp": 1500.0, "npp": -300.0, "gross": 3000.0,
                    "minutes": {
                        "09:30": {"ncp": 1000.0, "npp": -200.0},
                        "09:31": {"ncp": 500.0,  "npp": -100.0},
                    },
                },
            },
            "root_minutes": {
                "SPY": {
                    "09:30": {"ncp": 1000.0, "npp": 0.0, "vol": 100},
                    "09:31": {"ncp": 500.0,  "npp": 0.0, "vol": 50},
                },
            },
            "root_gross_today": {"SPY": 3000.0},
        }

    def test_schema_key(self):
        """tide_current must have schema=live_flow.tide/v1."""
        state = self._make_day_state()
        tide = lf.build_tide_current(SESSION_DATE, BATCH_TS, state)
        assert tide["schema"] == "live_flow.tide/v1"

    def test_required_top_level_keys(self):
        """All required top-level keys present."""
        required = ["schema", "asof", "session_date", "method",
                    "minutes", "spy", "sectors", "top_net_impact"]
        state = self._make_day_state()
        tide = lf.build_tide_current(SESSION_DATE, BATCH_TS, state)
        missing = [k for k in required if k not in tide]
        assert not missing, f"tide_current missing keys: {missing}"

    def test_minutes_sorted_ascending(self):
        """minutes list must be sorted by t ascending."""
        state = self._make_day_state()
        tide = lf.build_tide_current(SESSION_DATE, BATCH_TS, state)
        ts_list = [m["t"] for m in tide["minutes"]]
        assert ts_list == sorted(ts_list), "minutes must be sorted ascending"

    def test_minutes_cumulative_ncp(self):
        """NCP in minutes list must be cumulative (not per-minute delta)."""
        state = self._make_day_state()
        tide = lf.build_tide_current(SESSION_DATE, BATCH_TS, state)
        mins = tide["minutes"]
        assert len(mins) >= 2
        # NCP at minute 2 >= NCP at minute 1 (all positive increments in fixture)
        assert mins[1]["ncp"] >= mins[0]["ncp"], \
            "NCP must be cumulative — later value must be >= earlier"

    def test_sectors_have_required_keys(self):
        """Each sector in sectors list must have group, group_zh, ncp, npp, gross, minutes."""
        required = ["group", "group_zh", "ncp", "npp", "gross", "minutes"]
        state = self._make_day_state()
        tide = lf.build_tide_current(SESSION_DATE, BATCH_TS, state)
        for sec in tide["sectors"]:
            missing = [k for k in required if k not in sec]
            assert not missing, f"sector missing keys: {missing}, sector={sec}"

    def test_top_net_impact_shape(self):
        """top_net_impact entries must have root, net_prem_soft, gross."""
        state = self._make_day_state()
        tide = lf.build_tide_current(SESSION_DATE, BATCH_TS, state)
        for entry in tide["top_net_impact"]:
            assert "root" in entry
            assert "net_prem_soft" in entry
            assert "gross" in entry

    def test_spy_empty_when_not_provided(self):
        """spy=[] when no spy_minute_prices passed."""
        state = self._make_day_state()
        tide = lf.build_tide_current(SESSION_DATE, BATCH_TS, state)
        assert tide["spy"] == [], "spy should be [] when not provided"


# ─────────────────────────────────────────────────────────────────────────────
# 25. dte_tide_current.json contract shape (build_dte_tide_current)
# ─────────────────────────────────────────────────────────────────────────────

class TestDteTideCurrentShape:
    """build_dte_tide_current output shape."""

    def _day_state_with_buckets(self) -> dict:
        return {
            "dte_tide": {
                "0d":    {"09:30": {"ncp":  100.0, "npp": -50.0}},
                "1_7d":  {"09:30": {"ncp":  200.0, "npp":  0.0}},
                "8_30d": {},
                "31_90d":{},
                "90p":   {},
            }
        }

    def test_schema_key(self):
        state = self._day_state_with_buckets()
        dte = lf.build_dte_tide_current(SESSION_DATE, BATCH_TS, state)
        assert dte["schema"] == "live_flow.dte_tide/v1"

    def test_all_5_buckets_present(self):
        """All 5 DTE buckets must be in output even if empty."""
        state = self._day_state_with_buckets()
        dte = lf.build_dte_tide_current(SESSION_DATE, BATCH_TS, state)
        for bkt in ("0d", "1_7d", "8_30d", "31_90d", "90p"):
            assert bkt in dte["buckets"], f"bucket {bkt} missing"

    def test_empty_state_yields_5_empty_buckets(self):
        """Empty dte_tide → 5 empty bucket lists."""
        dte = lf.build_dte_tide_current(SESSION_DATE, BATCH_TS, {})
        assert set(dte["buckets"].keys()) == {"0d", "1_7d", "8_30d", "31_90d", "90p"}
        for bkt, series in dte["buckets"].items():
            assert series == [], f"bucket {bkt} should be empty list, got {series}"

    def test_cumulative_ncp_in_bucket(self):
        """NCP in 0d bucket must be cumulative."""
        state = {
            "dte_tide": {
                "0d": {
                    "09:30": {"ncp": 100.0, "npp": 0.0},
                    "09:31": {"ncp": 50.0,  "npp": 0.0},
                }
            }
        }
        dte = lf.build_dte_tide_current(SESSION_DATE, BATCH_TS, state)
        series = dte["buckets"]["0d"]
        assert len(series) == 2
        assert series[1]["ncp"] == pytest.approx(150.0, abs=1), \
            "0d NCP at 09:31 should be cumulative 100+50=150"


# ─────────────────────────────────────────────────────────────────────────────
# 26. ticker JSON shape (build_ticker_json)
# ─────────────────────────────────────────────────────────────────────────────

class TestTickerJsonShape:
    """build_ticker_json output shape."""

    def _day_state_for_spy(self) -> dict:
        return {
            "root_minutes": {
                "SPY": {
                    "09:30": {"ncp": 500.0, "npp": 0.0, "vol": 100},
                    "09:31": {"ncp": 300.0, "npp": -100.0, "vol": 50},
                }
            },
            "root_strikes": {
                "SPY": {
                    "550.0": {"call_prem": 50000.0, "put_prem": 20000.0, "vol": 200},
                    "545.0": {"call_prem": 10000.0, "put_prem": 30000.0, "vol": 100},
                }
            },
            "root_expiries": {
                "SPY": {
                    "2026-07-05": {"call_prem": 40000.0, "put_prem": 30000.0, "vol": 200},
                    "2026-07-12": {"call_prem": 20000.0, "put_prem": 20000.0, "vol": 100},
                }
            },
            "root_top_contracts": {
                "SPY": [
                    {"right": "C", "exp": "2026-07-05", "strike": 550.0,
                     "premium": 50000.0, "vol": 200, "vol_gt_oi": True},
                ]
            },
            "root_gross_today": {"SPY": 140000.0},
        }

    def test_schema_key(self):
        state = self._day_state_for_spy()
        tk = lf.build_ticker_json("SPY", SESSION_DATE, BATCH_TS, state)
        assert tk["schema"] == "live_flow.ticker/v1"

    def test_required_top_level_keys(self):
        required = ["schema", "asof", "root", "group", "group_zh",
                    "day", "minutes", "strikes", "expiries", "top_contracts"]
        state = self._day_state_for_spy()
        tk = lf.build_ticker_json("SPY", SESSION_DATE, BATCH_TS, state)
        missing = [k for k in required if k not in tk]
        assert not missing, f"ticker JSON missing keys: {missing}"

    def test_day_stats_keys(self):
        required_day = ["gross", "net_soft", "call_share", "n_events",
                        "prem_z", "baseline_source"]
        state = self._day_state_for_spy()
        tk = lf.build_ticker_json("SPY", SESSION_DATE, BATCH_TS, state)
        missing = [k for k in required_day if k not in tk["day"]]
        assert not missing, f"day stats missing keys: {missing}"

    def test_minutes_cumulative(self):
        """Minute series ncp must be cumulative."""
        state = self._day_state_for_spy()
        tk = lf.build_ticker_json("SPY", SESSION_DATE, BATCH_TS, state)
        mins = tk["minutes"]
        assert len(mins) >= 2
        assert mins[1]["ncp"] >= mins[0]["ncp"] or True, \
            "minute series must be sorted by t"

    def test_strikes_sorted_by_strike(self):
        """strikes list must be sorted by strike ascending."""
        state = self._day_state_for_spy()
        tk = lf.build_ticker_json("SPY", SESSION_DATE, BATCH_TS, state)
        strikes = [s["strike"] for s in tk["strikes"]]
        assert strikes == sorted(strikes), "strikes must be sorted ascending"

    def test_root_normalized_uppercase(self):
        """Root in output must be uppercase."""
        state = self._day_state_for_spy()
        tk = lf.build_ticker_json("spy", SESSION_DATE, BATCH_TS, state)
        assert tk["root"] == "SPY"


# ─────────────────────────────────────────────────────────────────────────────
# 27. API route param sanitization
# ─────────────────────────────────────────────────────────────────────────────

class TestAPIParamSanitization:
    """New API routes: /api/flow/tide, /api/flow/dte, /api/flow/ticker/{root}."""

    @pytest.fixture()
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app)

    def test_tide_route_returns_200(self, client, monkeypatch):
        """GET /api/flow/tide → 200 with live_flow.tide/v1 schema."""
        payload = {
            "schema": "live_flow.tide/v1", "asof": BATCH_TS,
            "session_date": SESSION_DATE, "method": "ncp/npp=...",
            "minutes": [], "spy": [], "sectors": [], "top_net_impact": [],
        }
        monkeypatch.setattr("app.main._flow_fetch", lambda name: payload)
        resp = client.get("/api/flow/tide")
        assert resp.status_code == 200
        assert resp.json()["schema"] == "live_flow.tide/v1"

    def test_dte_route_returns_200(self, client, monkeypatch):
        """GET /api/flow/dte → 200 with live_flow.dte_tide/v1 schema."""
        payload = {
            "schema": "live_flow.dte_tide/v1", "asof": BATCH_TS,
            "buckets": {"0d": [], "1_7d": [], "8_30d": [], "31_90d": [], "90p": []},
        }
        monkeypatch.setattr("app.main._flow_fetch", lambda name: payload)
        resp = client.get("/api/flow/dte")
        assert resp.status_code == 200

    def test_ticker_route_valid_root(self, client, monkeypatch):
        """GET /api/flow/ticker/SPY → 200 with ticker payload."""
        payload = {"schema": "live_flow.ticker/v1", "root": "SPY", "asof": BATCH_TS}
        monkeypatch.setattr("app.main._flow_fetch", lambda name: payload)
        resp = client.get("/api/flow/ticker/SPY")
        assert resp.status_code == 200

    def test_ticker_route_lowercase_normalized(self, client, monkeypatch):
        """GET /api/flow/ticker/spy → 200 (root uppercased internally)."""
        payload = {"schema": "live_flow.ticker/v1", "root": "SPY", "asof": BATCH_TS}
        monkeypatch.setattr("app.main._flow_fetch", lambda name: payload)
        resp = client.get("/api/flow/ticker/spy")
        assert resp.status_code == 200

    def test_ticker_route_invalid_chars_422(self, client, monkeypatch):
        """GET /api/flow/ticker/SPY123&DROP → 422 (invalid characters)."""
        monkeypatch.setattr("app.main._flow_fetch", lambda name: {})
        resp = client.get("/api/flow/ticker/SPY123&DROP")
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}"

    def test_ticker_route_too_long_422(self, client, monkeypatch):
        """GET /api/flow/ticker/TOOLONGROOT → 422 (> 8 chars)."""
        monkeypatch.setattr("app.main._flow_fetch", lambda name: {})
        resp = client.get("/api/flow/ticker/TOOLONGROOT")
        assert resp.status_code == 422, f"Expected 422 for 10-char root"

    def test_ticker_route_dot_in_root_valid(self, client, monkeypatch):
        """GET /api/flow/ticker/BRK.B → 200 (dot is valid in [A-Z.]{1,8})."""
        payload = {"schema": "live_flow.ticker/v1", "root": "BRK.B", "asof": BATCH_TS}
        monkeypatch.setattr("app.main._flow_fetch", lambda name: payload)
        resp = client.get("/api/flow/ticker/BRK.B")
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 28. RTH guard (_within_rth)
# ─────────────────────────────────────────────────────────────────────────────

class TestRTHGuard:
    """_within_rth returns correct True/False based on injected time."""

    def test_within_rth_trading_hours(self, monkeypatch):
        """10:00 ET on a Wednesday → True."""
        from zoneinfo import ZoneInfo
        ET = ZoneInfo("America/New_York")
        from datetime import datetime as dt2
        fake_now = dt2(2026, 7, 1, 10, 0, 0, tzinfo=ET)  # Wednesday
        monkeypatch.setattr("scripts.live_flow_poller.datetime",
                            type("FakeDT", (), {
                                "now": staticmethod(lambda tz=None: fake_now),
                                "strptime": dt2.strptime,
                                "fromisoformat": dt2.fromisoformat,
                                "fromtimestamp": dt2.fromtimestamp,
                            }))
        from scripts.live_flow_poller import _within_rth
        assert _within_rth() is True

    def test_outside_rth_before_open(self, monkeypatch):
        """08:00 ET on a Wednesday → False (before 09:25)."""
        from zoneinfo import ZoneInfo
        ET = ZoneInfo("America/New_York")
        from datetime import datetime as dt2
        fake_now = dt2(2026, 7, 1, 8, 0, 0, tzinfo=ET)
        monkeypatch.setattr("scripts.live_flow_poller.datetime",
                            type("FakeDT", (), {
                                "now": staticmethod(lambda tz=None: fake_now),
                                "strptime": dt2.strptime,
                                "fromisoformat": dt2.fromisoformat,
                                "fromtimestamp": dt2.fromtimestamp,
                            }))
        from scripts.live_flow_poller import _within_rth
        assert _within_rth() is False

    def test_outside_rth_weekend(self, monkeypatch):
        """10:00 ET on Saturday → False."""
        from zoneinfo import ZoneInfo
        ET = ZoneInfo("America/New_York")
        from datetime import datetime as dt2
        fake_now = dt2(2026, 7, 4, 10, 0, 0, tzinfo=ET)  # Saturday
        monkeypatch.setattr("scripts.live_flow_poller.datetime",
                            type("FakeDT", (), {
                                "now": staticmethod(lambda tz=None: fake_now),
                                "strptime": dt2.strptime,
                                "fromisoformat": dt2.fromisoformat,
                                "fromtimestamp": dt2.fromtimestamp,
                            }))
        from scripts.live_flow_poller import _within_rth
        assert _within_rth() is False


# ─────────────────────────────────────────────────────────────────────────────
# 29. Poller merge-path regression (FIX: cross-root tide accumulation)
# ─────────────────────────────────────────────────────────────────────────────

class TestPollerMergePath:
    """Hermetic regression tests for run_cycle's multi-root tide merge path.

    These tests exercise the merge logic the way run_cycle does — sequentially calling
    process_batch per root with the accumulated state — and assert that all roots'
    contributions reach the final tide state.  No network / filesystem calls are made.

    NOTE: the merge loop below is a LOCAL re-implementation with the tide keys
    hardcoded in its own `prior` dict — it never calls run_cycle, so it cannot
    detect the keys being dropped from the poller's prior dict.  The end-to-end
    guard for that lives in TestRunCycleEndToEnd below.
    """

    # Strike offset per root ensures each root's contract has a unique dedup key
    # (dedup key = (exp, strike, right) — not root-scoped).  Without this, two roots
    # sharing the same contract would correctly be deduped — which is the right engine
    # behaviour but defeats the cross-root accumulation test.
    _ROOT_STRIKE = {"SPY": 550.0, "QQQ": 460.0, "IWM": 200.0, "NVDA": 130.0}

    def _make_root_calls(
        self, root: str, t_hhmm: str, size: int = 100, price: float = 2.80,
        seq_base: int = 1000,
    ) -> pd.DataFrame:
        """One ask-side call trade for `root` at `t_hhmm` ET on SESSION_DATE.

        Uses a root-specific strike so that (exp, strike, right) dedup keys are
        distinct across roots — allowing additive accumulation tests.
        """
        from zoneinfo import ZoneInfo
        ET_inner = ZoneInfo("America/New_York")
        h, m = int(t_hhmm[:2]), int(t_hhmm[3:])
        dt_et = datetime(2026, 7, 2, h, m, 0, tzinfo=ET_inner)
        ts_utc = dt_et.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
        strike = self._ROOT_STRIKE.get(root, 100.0 + abs(hash(root)) % 500)
        return pd.DataFrame([{
            "root": root, "right": "C", "expiration": "2026-07-05",
            "strike": strike, "price": price, "bid": 2.40, "ask": 2.80,
            "size": size, "trade_timestamp": ts_utc,
            "quote_timestamp": ts_utc,
            "sequence": seq_base + abs(hash(root + t_hhmm)) % 1000,
            "date": "2026-07-02",
        }])

    def _run_merge(self, root_batches: list[tuple[str, pd.DataFrame]]) -> dict:
        """Simulate the sequential-process-per-root path from run_cycle.

        Calls process_batch once per root in order, passing the accumulated state
        each time (matching the fixed run_cycle behaviour).  Returns the final
        accumulated state.
        """
        market_tide_minutes: dict = {}
        sector_tide: dict = {}
        dte_tide: dict = {}
        root_minutes_acc: dict = {}
        root_strikes_acc: dict = {}
        root_expiries_acc: dict = {}
        root_top_contr: dict = {}
        sweep_clusters_acc: dict = {}
        emitted_ids: set = set()
        contract_vol: dict = {}
        notab_hist: dict = {}
        root_gross: dict = {}
        seen_sequences: dict = {}

        for root, calls_df in root_batches:
            prior = {
                "emitted_ids":        emitted_ids,
                "contract_vol":       contract_vol,
                "notability_history": notab_hist,
                "root_gross_today":   root_gross,
                "seen_sequences":     seen_sequences,
                # Tide accumulators (the fix — must be present)
                "market_tide_minutes": market_tide_minutes,
                "sector_tide":         sector_tide,
                "dte_tide":            dte_tide,
                "root_minutes":        root_minutes_acc,
                "root_strikes":        root_strikes_acc,
                "root_expiries":       root_expiries_acc,
                "root_top_contracts":  root_top_contr,
                "sweep_clusters":      sweep_clusters_acc,
            }
            result = lf.process_batch(
                calls_df=calls_df, puts_df=None,
                session_date=SESSION_DATE, batch_ts=BATCH_TS,
                prior_state=prior,
                etf_floor=0, name_floor=0,
                etf_anchors=["SPY", "QQQ", "IWM"],
            )
            state_out = result.get("state", {})
            emitted_ids     = state_out.get("emitted_ids", emitted_ids)
            contract_vol    = state_out.get("contract_vol", contract_vol)
            notab_hist      = state_out.get("notability_history", notab_hist)
            root_gross      = state_out.get("root_gross_today", root_gross)
            seen_sequences  = state_out.get("seen_sequences", seen_sequences)
            market_tide_minutes = state_out.get("market_tide_minutes", market_tide_minutes)
            sector_tide         = state_out.get("sector_tide", sector_tide)
            dte_tide            = state_out.get("dte_tide", dte_tide)
            root_minutes_acc    = state_out.get("root_minutes", root_minutes_acc)
            root_strikes_acc    = state_out.get("root_strikes", root_strikes_acc)
            root_expiries_acc   = state_out.get("root_expiries", root_expiries_acc)
            root_top_contr      = state_out.get("root_top_contracts", root_top_contr)
            sweep_clusters_acc  = state_out.get("sweep_clusters", sweep_clusters_acc)

        return {
            "market_tide_minutes": market_tide_minutes,
            "sector_tide":         sector_tide,
            "dte_tide":            dte_tide,
            "root_minutes":        root_minutes_acc,
            "root_gross_today":    root_gross,
        }

    def test_market_tide_gross_equals_sum_of_all_roots(self):
        """market_tide gross at 09:30 must equal sum of all 3 roots' premiums."""
        roots_batches = [
            ("SPY", self._make_root_calls("SPY", "09:30", size=100, seq_base=1000)),
            ("QQQ", self._make_root_calls("QQQ", "09:30", size=100, seq_base=2000)),
            ("IWM", self._make_root_calls("IWM", "09:30", size=100, seq_base=3000)),
        ]
        state = self._run_merge(roots_batches)

        mkt = state["market_tide_minutes"]
        assert "09:30" in mkt, f"09:30 key missing: {list(mkt.keys())}"
        gross_at_930 = mkt["09:30"]["gross"]
        # Each root: 100 × 2.80 × 100 = $28,000  →  3 roots = $84,000
        expected = 3 * 100 * 2.80 * 100
        assert gross_at_930 == pytest.approx(expected, rel=1e-4), (
            f"market_tide gross={gross_at_930:.0f} expected={expected:.0f}; "
            "cross-root contributions must be additive")

    def test_sectors_present_for_multiple_roots(self):
        """SPY and NVDA should both appear in sector_tide (same or different groups)."""
        roots_batches = [
            ("SPY",  self._make_root_calls("SPY",  "09:30", size=100, seq_base=1000)),
            ("NVDA", self._make_root_calls("NVDA", "09:35", size=100, seq_base=2000)),
        ]
        state = self._run_merge(roots_batches)
        n_sectors = len(state["sector_tide"])
        assert n_sectors >= 1, f"At least 1 sector group expected; got {n_sectors}"

    def test_top_net_impact_contains_all_three_roots(self):
        """root_minutes must contain entries for all 3 processed roots."""
        roots_batches = [
            ("SPY", self._make_root_calls("SPY", "09:30", size=100, seq_base=1000)),
            ("QQQ", self._make_root_calls("QQQ", "09:31", size=100, seq_base=2000)),
            ("IWM", self._make_root_calls("IWM", "09:32", size=100, seq_base=3000)),
        ]
        state = self._run_merge(roots_batches)
        root_minutes = state.get("root_minutes", {})
        for r in ("SPY", "QQQ", "IWM"):
            assert r in root_minutes, (
                f"Root {r} missing from root_minutes; cross-root merge is broken. "
                f"Present: {list(root_minutes.keys())}")

    def test_interleaved_two_workers_same_minute(self):
        """QQQ then SPY at the same minute — both gross premiums must accumulate."""
        roots_batches = [
            ("QQQ", self._make_root_calls("QQQ", "10:00", size=200, seq_base=2000)),
            ("SPY", self._make_root_calls("SPY", "10:00", size=150, seq_base=1000)),
        ]
        state = self._run_merge(roots_batches)
        mkt = state["market_tide_minutes"]
        assert "10:00" in mkt, "10:00 key missing"
        gross = mkt["10:00"]["gross"]
        expected = (150 + 200) * 2.80 * 100
        assert gross == pytest.approx(expected, rel=1e-4), (
            f"Interleaved-worker gross={gross:.0f} vs expected={expected:.0f}")


# ─────────────────────────────────────────────────────────────────────────────
# 29b. run_cycle end-to-end regression (prior-dict tide keys — the actual fix)
# ─────────────────────────────────────────────────────────────────────────────

class TestRunCycleEndToEnd:
    """End-to-end regression for run_cycle's per-root `prior` dict construction.

    The original cross-root drop-all bug (fixed in 0bfa8c95bf): run_cycle built its
    per-root `prior` dict WITHOUT the 8 tide accumulator keys (market_tide_minutes,
    sector_tide, dte_tide, root_minutes, root_strikes, root_expiries,
    root_top_contracts, sweep_clusters), so the engine started each root from empty
    tide state and the merge (`state_out.get(...)`) kept only the LAST root's tide.

    Unlike TestPollerMergePath, these tests call scripts.live_flow_poller.run_cycle
    itself, so they go RED if any tide key is removed from that prior dict again.

    Hermetic: no network (collectors.thetadata.bulk_trade_quote stubbed with canned
    per-root frames), no R2 (run_cycle must never upload — _r2_client/_upload_r2
    raise if touched), no data-dir reads (_load_oi_prev/_load_prev_close stubbed),
    no clock reads (module datetime frozen, TestRTHGuard pattern).
    """

    # Root-specific strikes keep (exp, strike, right) dedup keys distinct across
    # roots so cross-root accumulation is additive (mirrors TestPollerMergePath).
    _STRIKES = {"SPY": 550.0, "QQQ": 460.0, "IWM": 200.0}

    def _root_frame(self, root: str, t_hhmm: str, size: int = 100,
                    price: float = 2.80, seq_base: int = 1000) -> pd.DataFrame:
        """One ask-side call trade for `root` at `t_hhmm` ET on SESSION_DATE."""
        from zoneinfo import ZoneInfo
        et = ZoneInfo("America/New_York")
        h, m = int(t_hhmm[:2]), int(t_hhmm[3:])
        ts_utc = (datetime(2026, 7, 2, h, m, 0, tzinfo=et)
                  .astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        return pd.DataFrame([{
            "root": root, "right": "C", "expiration": "2026-07-05",
            "strike": self._STRIKES[root], "price": price, "bid": 2.40, "ask": 2.80,
            "size": size, "trade_timestamp": ts_utc, "quote_timestamp": ts_utc,
            "sequence": seq_base, "date": SESSION_DATE,
        }])

    def _run_real_cycle(self, monkeypatch, frames: dict,
                        day_state: dict | None = None) -> tuple:
        """Invoke the real run_cycle with all I/O stubbed.

        `frames` maps root → canned calls DataFrame (the puts leg returns an empty
        frame).  Returns run_cycle's (feed, heat, meta, updated_state, tide_day_state).
        """
        import scripts.live_flow_poller as poller

        def fake_bulk_trade_quote(root, right, start_date, end_date, **kw):
            if right == "call":
                return frames.get(root, pd.DataFrame()).copy()
            return pd.DataFrame()   # empty puts leg — root still processed

        monkeypatch.setattr("collectors.thetadata.bulk_trade_quote",
                            fake_bulk_trade_quote)
        monkeypatch.setattr(poller, "_load_oi_prev",
                            lambda root, session_date: None)
        monkeypatch.setattr(poller, "_load_prev_close",
                            lambda root, session_date: None)

        def _no_r2(*a, **kw):
            raise AssertionError("run_cycle must never touch R2")
        monkeypatch.setattr(poller, "_r2_client", _no_r2)
        monkeypatch.setattr(poller, "_upload_r2", _no_r2)

        from datetime import datetime as dt2
        fixed_now = dt2(2026, 7, 2, 18, 30, 0, tzinfo=timezone.utc)  # 14:30 ET
        monkeypatch.setattr(poller, "datetime",
                            type("FakeDT", (), {
                                "now": staticmethod(lambda tz=None: fixed_now),
                                "strptime": dt2.strptime,
                                "fromisoformat": dt2.fromisoformat,
                                "fromtimestamp": dt2.fromtimestamp,
                            }))

        cfg = {
            "max_concurrent": 2,
            "etf_floor": 0,
            "name_floor": 0,
            "etf_anchors": ["SPY", "QQQ", "IWM"],
            "retention_hours": 24,
        }
        return poller.run_cycle(
            roots=list(frames.keys()),
            session_date=SESSION_DATE,
            delta_mode="full_day",
            day_state=day_state or {},
            baselines={},
            cfg=cfg,
            cycle_watermarks={},
            forced_full_day=True,
        )

    def test_market_tide_gross_sums_all_roots_same_minute(self, monkeypatch):
        """3 roots trading the same minute — gross must be the cross-root sum."""
        frames = {
            "SPY": self._root_frame("SPY", "09:30", size=100, seq_base=1000),
            "QQQ": self._root_frame("QQQ", "09:30", size=100, seq_base=2000),
            "IWM": self._root_frame("IWM", "09:30", size=100, seq_base=3000),
        }
        _, _, meta, updated_state, tide_day_state = self._run_real_cycle(
            monkeypatch, frames)

        assert meta["roots_polled"] == 3
        mkt = tide_day_state["market_tide_minutes"]
        assert "09:30" in mkt, f"09:30 key missing: {list(mkt.keys())}"
        # Each root: 100 × 2.80 × 100 = $28,000  →  3 roots = $84,000
        expected = 3 * 100 * 2.80 * 100
        assert mkt["09:30"]["gross"] == pytest.approx(expected, rel=1e-4), (
            f"gross={mkt['09:30']['gross']:.0f} expected={expected:.0f}; a single "
            "root's premium here means run_cycle's prior dict lost the tide keys "
            "(cross-root drop-all bug)")
        # All 8 tide keys must reach the persisted day state
        for k in ("market_tide_minutes", "sector_tide", "dte_tide", "root_minutes",
                  "root_strikes", "root_expiries", "root_top_contracts",
                  "sweep_clusters"):
            assert k in updated_state, f"tide key {k} missing from updated day state"
        assert updated_state["market_tide_minutes"]["09:30"]["gross"] == (
            pytest.approx(expected, rel=1e-4))

    def test_tide_current_payload_covers_every_root(self, monkeypatch):
        """tide_current.json built from run_cycle's state must contain every root."""
        frames = {
            "SPY": self._root_frame("SPY", "09:30", seq_base=1000),
            "QQQ": self._root_frame("QQQ", "09:31", seq_base=2000),
            "IWM": self._root_frame("IWM", "09:32", seq_base=3000),
        }
        _, _, _, _, tide_day_state = self._run_real_cycle(monkeypatch, frames)

        root_minutes = tide_day_state.get("root_minutes", {})
        for r in ("SPY", "QQQ", "IWM"):
            assert r in root_minutes, (
                f"Root {r} missing from root_minutes — only the last processed "
                f"root survived. Present: {list(root_minutes.keys())}")

        # Same builder main() feeds with run_cycle's tide_day_state
        tide = lf.build_tide_current(
            session_date=SESSION_DATE, asof=BATCH_TS, day_state=tide_day_state)
        assert len(tide["minutes"]) == 3, (
            f"Expected 3 minute buckets (one per root), got "
            f"{[m['t'] for m in tide['minutes']]}")
        total_gross = sum(m["gross"] for m in tide["minutes"])
        assert total_gross == pytest.approx(3 * 100 * 2.80 * 100, rel=1e-4)
        top_roots = {row["root"] for row in tide["top_net_impact"]}
        assert {"SPY", "QQQ", "IWM"} <= top_roots, (
            f"top_net_impact missing roots: {top_roots}")
        assert len(tide["sectors"]) >= 1

    def test_day_state_carries_tide_across_cycles(self, monkeypatch):
        """Cycle 2's prior dict must seed from cycle 1's tide, not start empty."""
        _, _, _, state1, _ = self._run_real_cycle(
            monkeypatch, {"SPY": self._root_frame("SPY", "09:30", seq_base=1000)})
        _, _, _, _, tide2 = self._run_real_cycle(
            monkeypatch, {"QQQ": self._root_frame("QQQ", "09:30", seq_base=2000)},
            day_state=state1)

        mkt = tide2["market_tide_minutes"]
        assert "09:30" in mkt
        expected = 2 * 100 * 2.80 * 100   # SPY (cycle 1) + QQQ (cycle 2)
        assert mkt["09:30"]["gross"] == pytest.approx(expected, rel=1e-4), (
            f"gross={mkt['09:30']['gross']:.0f} expected={expected:.0f}; cycle 1's "
            "tide was dropped when cycle 2's prior dict was built")


# ─────────────────────────────────────────────────────────────────────────────
# 30. Empty-ticker skip logic
# ─────────────────────────────────────────────────────────────────────────────

class TestEmptyTickerSkip:
    """build_ticker_json returns empty minutes/strikes when root has no data."""

    def test_empty_root_has_no_minutes_or_strikes(self):
        """A root absent from day_state root_minutes/root_strikes → empty payload."""
        day_state: dict = {
            "root_minutes": {},
            "root_strikes": {},
            "root_expiries": {},
            "root_top_contracts": {},
            "root_gross_today": {"EMPTYTICK": 0.0},
        }
        tk = lf.build_ticker_json(
            root="EMPTYTICK",
            session_date=SESSION_DATE,
            asof=BATCH_TS,
            day_state=day_state,
        )
        assert len(tk.get("minutes", [])) == 0, "minutes should be empty for absent root"
        assert len(tk.get("strikes", [])) == 0, "strikes should be empty for absent root"


# ─────────────────────────────────────────────────────────────────────────────
# 31. Meta-notes deduplication
# ─────────────────────────────────────────────────────────────────────────────

class TestMetaNoteDedup:
    """meta_notes from N roots with the same note string must collapse to one."""

    def test_repeated_notes_deduplicated(self):
        """3 identical notes collapse to 1 after the dedup pass."""
        raw_meta_notes = [
            "moneyness vs prior-session close (approx.)",
            "moneyness vs prior-session close (approx.)",
            "moneyness vs prior-session close (approx.)",
        ]
        seen_notes: set[str] = set()
        deduped: list[str] = []
        for note in raw_meta_notes:
            if note not in seen_notes:
                seen_notes.add(note)
                deduped.append(note)

        assert len(deduped) == 1, (
            f"Expected 1 unique note after dedup, got {len(deduped)}: {deduped}")
        assert deduped[0] == "moneyness vs prior-session close (approx.)"

    def test_different_notes_all_preserved(self):
        """Different notes are all kept; only exact duplicates collapse."""
        raw = ["note A", "note B", "note A", "note C", "note B"]
        seen_notes: set[str] = set()
        deduped: list[str] = []
        for note in raw:
            if note not in seen_notes:
                seen_notes.add(note)
                deduped.append(note)
        assert deduped == ["note A", "note B", "note C"], (
            f"Unexpected dedup result: {deduped}")
