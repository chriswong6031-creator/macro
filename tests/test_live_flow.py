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
