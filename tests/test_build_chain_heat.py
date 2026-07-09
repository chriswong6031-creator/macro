"""tests/test_build_chain_heat.py — unit tests for the chain-heat envelope wrapper.

Tests the pure parts of scripts/build_chain_heat.py:
  - build_envelope: shape, key renames, nullable fields
  - _enrich_events: side → ask_share mapping
  - end-to-end: aggregate_chain_heat + build_envelope integration (no I/O)
"""
from __future__ import annotations

import pytest

from scripts.build_chain_heat import build_envelope, _enrich_events, _SIDE_TO_ASK_SHARE
from engine.options_structure import aggregate_chain_heat


# ─── helpers ──────────────────────────────────────────────────────────────────

def _make_events(n: int, root: str = "SMH", right: str = "C", exp: str = "2026-09-18",
                 strike: float = 530.0, premium: float = 1_500_000.0,
                 side: str = "~buy") -> list[dict]:
    """Produce n synthetic feed/v1 events."""
    return [
        {
            "id": f"ev{i}",
            "ts": f"2026-07-08T1{i % 6}:00:00Z",
            "root": root,
            "right": right,
            "exp": exp,
            "strike": strike,
            "premium": premium,
            "side": side,
        }
        for i in range(n)
    ]


# ─── _enrich_events ───────────────────────────────────────────────────────────

class TestEnrichEvents:
    def test_buy_side_mapped(self):
        events = [{"side": "~buy"}]
        out = _enrich_events(events)
        assert out[0]["ask_share"] == pytest.approx(0.80)

    def test_sell_side_mapped(self):
        events = [{"side": "~sell"}]
        out = _enrich_events(events)
        assert out[0]["ask_share"] == pytest.approx(0.20)

    def test_mixed_side_mapped(self):
        events = [{"side": "mixed"}]
        out = _enrich_events(events)
        assert out[0]["ask_share"] == pytest.approx(0.50)

    def test_none_side_stays_none(self):
        events = [{"side": None}]
        out = _enrich_events(events)
        assert out[0]["ask_share"] is None

    def test_existing_ask_share_not_overwritten(self):
        events = [{"side": "~buy", "ask_share": 0.42}]
        out = _enrich_events(events)
        assert out[0]["ask_share"] == pytest.approx(0.42)

    def test_original_not_mutated(self):
        events = [{"side": "~buy"}]
        _enrich_events(events)
        assert "ask_share" not in events[0]


# ─── build_envelope ───────────────────────────────────────────────────────────

class TestBuildEnvelope:
    def _minimal_campaign(self, right: str = "CALL") -> dict:
        return {
            "option_symbol": "SMH   260918C00530000",
            "ticker": "SMH",
            "right": right,
            "strike": 530.0,
            "expiry": "2026-09-18",
            "dte": 71,
            "total_premium_mn": 5.0,
            "alert_count": 4,
            "span_minutes": 45.0,
            "first_seen": "2026-07-08T09:35:00Z",
            "last_seen": "2026-07-08T10:20:00Z",
            "ask_share": 0.80,
            "lean": "accumulation",
            "direction_reliability": "soft",
            "authority_tier": "display",
        }

    def test_schema_key(self):
        env = build_envelope([], "2026-07-08", "2026-07-08T20:00:00Z")
        assert env["schema"] == "options_flow.chain_heat/v1"

    def test_required_top_level_keys(self):
        env = build_envelope([], "2026-07-08", "2026-07-08T20:00:00Z")
        for key in ("schema", "asof", "session_date", "threshold_mn",
                    "note_en", "note_zh", "campaigns"):
            assert key in env, f"missing top-level key: {key!r}"

    def test_session_date_and_asof_threaded(self):
        env = build_envelope([], "2026-07-08", "2026-07-08T20:00:00Z")
        assert env["session_date"] == "2026-07-08"
        assert env["asof"] == "2026-07-08T20:00:00Z"

    def test_threshold_mn_default(self):
        env = build_envelope([], "2026-07-08", "2026-07-08T20:00:00Z")
        assert env["threshold_mn"] == 3

    def test_right_renamed_to_type(self):
        campaigns = [self._minimal_campaign("CALL")]
        env = build_envelope(campaigns, "2026-07-08", "2026-07-08T20:00:00Z")
        c = env["campaigns"][0]
        assert "type" in c, "'type' key missing from campaign"
        assert "right" not in c, "'right' should be renamed to 'type'"
        assert c["type"] == "CALL"

    def test_right_renamed_put(self):
        campaigns = [self._minimal_campaign("PUT")]
        env = build_envelope(campaigns, "2026-07-08", "2026-07-08T20:00:00Z")
        assert env["campaigns"][0]["type"] == "PUT"

    def test_last_seen_removed(self):
        campaigns = [self._minimal_campaign()]
        env = build_envelope(campaigns, "2026-07-08", "2026-07-08T20:00:00Z")
        assert "last_seen" not in env["campaigns"][0]

    def test_note_added_as_null(self):
        campaigns = [self._minimal_campaign()]
        env = build_envelope(campaigns, "2026-07-08", "2026-07-08T20:00:00Z")
        c = env["campaigns"][0]
        assert "note" in c
        assert c["note"] is None

    def test_existing_note_preserved(self):
        campaign = self._minimal_campaign()
        campaign["note"] = "Sustained sweep"
        env = build_envelope([campaign], "2026-07-08", "2026-07-08T20:00:00Z")
        assert env["campaigns"][0]["note"] == "Sustained sweep"

    def test_note_en_not_validated(self):
        """'validated' must never appear in note_en (CI-enforced law)."""
        env = build_envelope([], "2026-07-08", "2026-07-08T20:00:00Z")
        assert "validated" not in env.get("note_en", "").lower()
        assert "validated" not in env.get("note_zh", "").lower()

    def test_empty_campaigns(self):
        env = build_envelope([], "2026-07-08", "2026-07-08T20:00:00Z")
        assert env["campaigns"] == []

    def test_original_campaigns_not_mutated(self):
        campaign = self._minimal_campaign()
        original_keys = set(campaign.keys())
        build_envelope([campaign], "2026-07-08", "2026-07-08T20:00:00Z")
        assert set(campaign.keys()) == original_keys


# ─── end-to-end: aggregate + wrap ─────────────────────────────────────────────

class TestEndToEnd:
    """Ensure aggregate_chain_heat + build_envelope produce a well-formed artifact."""

    def _feed_events(self) -> list[dict]:
        """Two campaigns: SMH Put 530 (big, buy-side) and QQQ Call 640 (smaller, sell)."""
        base = []
        # Campaign A: SMH 530P — 5 events × $1.5M = $7.5M, ~buy
        base += _make_events(5, root="SMH", right="P", exp="2026-09-18",
                              strike=530.0, premium=1_500_000.0, side="~buy")
        # Campaign B: QQQ 640C — 3 events × $1.5M = $4.5M, ~sell
        base += _make_events(3, root="QQQ", right="C", exp="2026-09-18",
                              strike=640.0, premium=1_500_000.0, side="~sell")
        # Too-small campaign: AAPL 200C — 1 event × $1M = $1M (below 3M gate)
        base += _make_events(1, root="AAPL", right="C", exp="2026-09-18",
                              strike=200.0, premium=1_000_000.0, side="~buy")
        return base

    def test_two_campaigns_above_threshold(self):
        events = _enrich_events(self._feed_events())
        raw = aggregate_chain_heat(events, min_premium_mn=3.0, min_alerts=2,
                                   session_date="2026-07-08")
        env = build_envelope(raw, "2026-07-08", "2026-07-08T20:00:00Z")
        # AAPL below gate, so 2 campaigns expected
        assert len(env["campaigns"]) == 2

    def test_sorted_by_premium_descending(self):
        events = _enrich_events(self._feed_events())
        raw = aggregate_chain_heat(events, min_premium_mn=3.0, min_alerts=2,
                                   session_date="2026-07-08")
        env = build_envelope(raw, "2026-07-08", "2026-07-08T20:00:00Z")
        prems = [c["total_premium_mn"] for c in env["campaigns"]]
        assert prems == sorted(prems, reverse=True)

    def test_type_field_present_not_right(self):
        events = _enrich_events(self._feed_events())
        raw = aggregate_chain_heat(events, min_premium_mn=3.0, min_alerts=2,
                                   session_date="2026-07-08")
        env = build_envelope(raw, "2026-07-08", "2026-07-08T20:00:00Z")
        for c in env["campaigns"]:
            assert "type" in c and "right" not in c
            assert c["type"] in ("CALL", "PUT")

    def test_buy_side_lean_accumulation(self):
        events = _enrich_events(self._feed_events())
        raw = aggregate_chain_heat(events, min_premium_mn=3.0, min_alerts=2,
                                   session_date="2026-07-08")
        env = build_envelope(raw, "2026-07-08", "2026-07-08T20:00:00Z")
        smh_campaign = next(c for c in env["campaigns"] if c["ticker"] == "SMH")
        # SMH was all ~buy → ask_share=0.80 → accumulation
        assert smh_campaign["lean"] == "accumulation"

    def test_sell_side_lean_distribution(self):
        events = _enrich_events(self._feed_events())
        raw = aggregate_chain_heat(events, min_premium_mn=3.0, min_alerts=2,
                                   session_date="2026-07-08")
        env = build_envelope(raw, "2026-07-08", "2026-07-08T20:00:00Z")
        qqq_campaign = next(c for c in env["campaigns"] if c["ticker"] == "QQQ")
        # QQQ was all ~sell → ask_share=0.20 → distribution
        assert qqq_campaign["lean"] == "distribution"

    def test_dte_computed(self):
        events = _enrich_events(self._feed_events())
        raw = aggregate_chain_heat(events, min_premium_mn=3.0, min_alerts=2,
                                   session_date="2026-07-08")
        env = build_envelope(raw, "2026-07-08", "2026-07-08T20:00:00Z")
        for c in env["campaigns"]:
            assert c["dte"] is not None and c["dte"] > 0

    def test_required_campaign_keys(self):
        """Every campaign must carry all keys the UI component reads."""
        ui_keys = {
            "option_symbol", "ticker", "type", "strike", "expiry", "dte",
            "total_premium_mn", "alert_count", "span_minutes", "first_seen",
            "ask_share", "lean", "direction_reliability", "authority_tier", "note",
        }
        events = _enrich_events(self._feed_events())
        raw = aggregate_chain_heat(events, min_premium_mn=3.0, min_alerts=2,
                                   session_date="2026-07-08")
        env = build_envelope(raw, "2026-07-08", "2026-07-08T20:00:00Z")
        for i, c in enumerate(env["campaigns"]):
            missing = ui_keys - set(c.keys())
            assert not missing, f"campaign[{i}] missing keys: {missing}"
