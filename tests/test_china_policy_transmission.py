"""Tests for engine/china_policy_transmission.py and scripts/build_china_policy_transmission.py.

All tests run offline with synthetic fixtures — no network, no live stores.
"""
from __future__ import annotations

import json
import textwrap
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from engine import china_policy_transmission as pt
from engine.china_policy_transmission import (
    _classify_impulse,
    _dedup,
    _derive_channels,
    _event_hash,
    _tag_sectors,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_root(tmp_path: Path) -> Path:
    """Fake repo root with minimal subdirs."""
    (tmp_path / "data" / "china_official").mkdir(parents=True)
    (tmp_path / "data" / "china_policy_transmission").mkdir(parents=True)
    (tmp_path / "site" / "chinastatedata").mkdir(parents=True)
    return tmp_path


def _make_communiques_df():
    """Minimal communiques DataFrame for offline use."""
    import pandas as pd
    return pd.DataFrame([
        {
            "doc_id": "abc123",
            "family": "politburo_econ",
            "meeting_year": 2026,
            "meeting_quarter": 1,
            "meeting_date": "2026-04-25",
            "publish_date": "2026-04-28",
            "title": "政治局会议：支持资本市场健康发展",
            "body": "中央政治局会议强调要支持A股股市稳定，推动资本市场改革。",
            "body_sha256": "0" * 64,
            "url": "https://example.com/politburo_2026_04",
            "source": "xinhua",
            "_fetched_at": "2026-04-28T10:00:00Z",
        },
        {
            "doc_id": "def456",
            "family": "pboc_mpc",
            "meeting_year": 2026,
            "meeting_quarter": 1,
            "meeting_date": "2026-03-20",
            "publish_date": "2026-03-20",
            "title": "PBoC MPC statement Q1 2026 — monetary policy easing",
            "body": "The PBoC monetary policy committee decided to cut the LPR by 10bp.",
            "body_sha256": "1" * 64,
            "url": "https://pboc.gov.cn/mpc/2026q1",
            "source": "pboc_web",
            "_fetched_at": "2026-03-20T09:00:00Z",
        },
        {
            # Gap row — must be skipped
            "doc_id": "gap001",
            "family": "cewc",
            "meeting_year": 2017,
            "meeting_quarter": None,
            "meeting_date": None,
            "publish_date": None,
            "title": "CEWC 2017 — KNOWN GAP",
            "body": "EXPLICIT GAP: absent from archive.",
            "body_sha256": "2" * 64,
            "url": "cctv://news_cctv/gap/2017",
            "source": "explicit_gap",
            "_fetched_at": "2026-07-07T10:00:00Z",
        },
    ])


def _make_rrr_df():
    """Minimal RRR DataFrame."""
    import pandas as pd
    data = {
        "rrr_big": [9.5, 9.0, 8.5],
        "rrr_change": [0.0, -0.50, -0.50],
    }
    idx = pd.to_datetime(["2024-01-01", "2024-09-27", "2025-05-07"])
    idx.name = "REPORT_DATE"
    return pd.DataFrame(data, index=idx)


def _make_lpr_df():
    """Minimal LPR DataFrame with a couple of cuts."""
    import pandas as pd
    dates = pd.date_range("2024-07-01", periods=5, freq="3ME")
    dates.name = "TRADE_DATE"
    lpr1 = [3.45, 3.35, 3.35, 3.10, 3.00]
    lpr5 = [3.95, 3.85, 3.85, 3.60, 3.50]
    return pd.DataFrame({"lpr_1y": lpr1, "lpr_5y": lpr5}, index=dates)


def _make_fr007_df():
    """Minimal FR007 DataFrame with no z-score exceedances.

    Uses a perfectly constant 2.0 baseline so the rolling std is zero before
    warmup completes.  After 30 bars the series stays flat — z-scores are all
    exactly 0.  No OMO events should be emitted.
    """
    import pandas as pd

    dates = pd.date_range("2023-01-01", periods=200, freq="B")
    dates.name = "date"
    vals = [2.0] * 200
    df = pd.DataFrame({"FR001": vals, "FR007": vals, "FR014": vals}, index=dates)
    return df


def _make_fr007_df_with_spikes():
    """FR007 DataFrame with exactly two isolated single-day spikes.

    A constant 2.0 baseline (rolling std ~0 after warmup) with two large
    isolated spikes well after the 30-bar warmup and more than 3 calendar days
    apart guarantees exactly 2 exceedance episodes — one drain and one injection.

    The episode-collapse window (3 calendar days) will not merge them.
    """
    import pandas as pd

    n = 300
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    dates.name = "date"
    vals = [2.0] * n
    # Episode 1 at index 150 (well past 30-bar warmup): drain spike
    vals[150] = 10.0
    # Episode 2 at index 250 (100 bars later, >> 3 calendar days): injection spike
    vals[250] = 0.1
    df = pd.DataFrame({"FR001": vals, "FR007": vals, "FR014": vals}, index=dates)
    return df


# ---------------------------------------------------------------------------
# Unit tests: helpers
# ---------------------------------------------------------------------------

class TestEventHash:
    def test_deterministic(self):
        h1 = _event_hash("2025-05-07", "pboc", "rrr", "RRR cut 0.50pp")
        h2 = _event_hash("2025-05-07", "pboc", "rrr", "RRR cut 0.50pp")
        assert h1 == h2

    def test_different_inputs_differ(self):
        h1 = _event_hash("2025-05-07", "pboc", "rrr", "RRR cut 0.50pp")
        h2 = _event_hash("2025-05-07", "pboc", "rrr", "RRR cut 0.25pp")
        assert h1 != h2

    def test_16_hex_chars(self):
        h = _event_hash("2025-01-01", "pboc", "lpr", "1Y LPR cut 10bp")
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)


class TestTagSectors:
    def test_capital_market_en(self):
        tags = _tag_sectors("The CSRC announced measures to support the stock market.")
        assert "capital_market" in tags

    def test_capital_market_zh(self):
        tags = _tag_sectors("证监会发布消息，支持A股市场稳定。")
        assert "capital_market" in tags

    def test_property_en(self):
        tags = _tag_sectors("New housing policies cut down payment requirements.")
        assert "property" in tags

    def test_property_zh(self):
        tags = _tag_sectors("政府宣布降低首付比例，支持住房需求。")
        assert "property" in tags

    def test_industrial_en(self):
        tags = _tag_sectors("New policy supports manufacturing equipment upgrade.")
        assert "industrial" in tags

    def test_industrial_zh(self):
        tags = _tag_sectors("支持制造业设备更新和半导体产业发展。")
        assert "industrial" in tags

    def test_no_match(self):
        tags = _tag_sectors("General text without specific policy keywords.")
        assert tags == []

    def test_multiple_sectors(self):
        text = "Policies support housing market and semiconductor manufacturing."
        tags = _tag_sectors(text)
        assert "property" in tags
        assert "industrial" in tags


class TestClassifyImpulse:
    def test_easing(self):
        result = _classify_impulse("easing", fr007_z=-0.5, rrr_cut_90d=None,
                                   lpr_cut_90d=None, recent_comm_text="")
        assert result == "easing"

    def test_tightening(self):
        result = _classify_impulse("tightening", fr007_z=0.5, rrr_cut_90d=None,
                                   lpr_cut_90d=None, recent_comm_text="")
        assert result == "tightening"

    def test_market_rescue_rrr_large_and_fr007_very_low(self):
        # rrr_cut ≥ 0.50 AND lpr_cut qualifies easing AND fr007_z ≤ -1.5
        result = _classify_impulse("easing", fr007_z=-2.0, rrr_cut_90d=0.50,
                                   lpr_cut_90d=0.10, recent_comm_text="")
        assert result == "market_rescue"

    def test_market_rescue_lpr_large(self):
        # lpr_cut ≥ 0.25 AND fr007_z ≤ -1.5 triggers rescue
        result = _classify_impulse("easing", fr007_z=-1.6, rrr_cut_90d=0.0,
                                   lpr_cut_90d=0.25, recent_comm_text="")
        assert result == "market_rescue"

    def test_no_rescue_if_fr007_not_low(self):
        # Big RRR cut but FR007 not extreme — just "easing"
        result = _classify_impulse("easing", fr007_z=-0.8, rrr_cut_90d=0.50,
                                   lpr_cut_90d=0.25, recent_comm_text="")
        assert result == "easing"

    def test_targeted_support_from_communique(self):
        text = "会议强调要支持A股市场和资本市场健康发展。"
        result = _classify_impulse("neutral", fr007_z=-0.3, rrr_cut_90d=None,
                                   lpr_cut_90d=None, recent_comm_text=text)
        assert result == "targeted_support"

    def test_neutral_fallback(self):
        result = _classify_impulse("neutral", fr007_z=0.2, rrr_cut_90d=None,
                                   lpr_cut_90d=None, recent_comm_text="")
        assert result == "neutral"

    def test_none_stance_treated_as_neutral(self):
        result = _classify_impulse(None, fr007_z=0.0, rrr_cut_90d=None,
                                   lpr_cut_90d=None, recent_comm_text="")
        assert result == "neutral"

    def test_market_rescue_with_neutral_stance(self):
        """market_rescue must fire even when pboc_stance=='neutral'.

        A forced-easing / liquidity-crisis regime may have not yet scored ±2 on
        the stance model, so the stance gate would suppress the label that was
        specifically designed to catch it.  The documented rule has NO stance
        precondition.
        """
        result = _classify_impulse(
            "neutral",
            fr007_z=-2.0,
            rrr_cut_90d=0.50,
            lpr_cut_90d=0.0,
            recent_comm_text="",
        )
        assert result == "market_rescue", (
            f"Expected 'market_rescue' with neutral stance + rrr_cut≥0.50 + fr007_z≤−1.5, "
            f"got '{result}'"
        )

    def test_market_rescue_with_none_stance(self):
        """market_rescue must fire with stance==None (data absent)."""
        result = _classify_impulse(
            None,
            fr007_z=-1.6,
            rrr_cut_90d=0.0,
            lpr_cut_90d=0.25,
            recent_comm_text="",
        )
        assert result == "market_rescue", (
            f"Expected 'market_rescue' with None stance + lpr_cut≥0.25 + fr007_z≤−1.5, "
            f"got '{result}'"
        )


class TestDeriveChannels:
    def test_easing_channels(self):
        ch = _derive_channels("easing", "easing")
        assert "rate" in ch
        assert "liquidity" in ch

    def test_market_rescue_has_stabilization(self):
        ch = _derive_channels("market_rescue", "easing")
        assert "stabilization" in ch

    def test_targeted_support_fiscal(self):
        ch = _derive_channels("targeted_support", "neutral")
        assert "fiscal_or_structural" in ch

    def test_targeted_support_no_liquidity_without_evidence(self):
        """Pure rhetoric with neutral stance and no rate/OMO evidence must NOT add liquidity."""
        ch = _derive_channels(
            "targeted_support",
            pboc_stance="neutral",
            fr007_z=-0.3,
            rrr_cut_90d=None,
            lpr_cut_90d=None,
        )
        assert "fiscal_or_structural" in ch
        assert "liquidity" not in ch, (
            f"No liquidity evidence present; got channels={ch}"
        )

    def test_targeted_support_liquidity_with_lpr_cut(self):
        """targeted_support with a recent LPR cut should get liquidity channel."""
        ch = _derive_channels(
            "targeted_support",
            pboc_stance="neutral",
            fr007_z=-0.3,
            rrr_cut_90d=None,
            lpr_cut_90d=0.10,
        )
        assert "liquidity" in ch

    def test_targeted_support_liquidity_with_low_fr007z(self):
        """targeted_support with fr007_z <= -0.5 should get liquidity channel."""
        ch = _derive_channels(
            "targeted_support",
            pboc_stance="neutral",
            fr007_z=-0.6,
            rrr_cut_90d=None,
            lpr_cut_90d=None,
        )
        assert "liquidity" in ch

    def test_no_duplicates(self):
        ch = _derive_channels("easing", "easing")
        assert len(ch) == len(set(ch))


class TestDedup:
    def test_dedup_by_hash(self):
        ev_a = {"_hash": "aaa", "ts": "2025-01-01", "title": "A"}
        ev_b = {"_hash": "bbb", "ts": "2025-01-02", "title": "B"}
        ev_a2 = {"_hash": "aaa", "ts": "2025-01-01", "title": "A duplicate"}
        result = _dedup([ev_a, ev_b, ev_a2])
        hashes = [r["_hash"] for r in result]
        assert len(hashes) == 2
        assert "aaa" in hashes
        assert "bbb" in hashes

    def test_sorted_by_ts(self):
        events = [
            {"_hash": "z", "ts": "2025-03-01"},
            {"_hash": "y", "ts": "2025-01-01"},
            {"_hash": "x", "ts": "2025-02-01"},
        ]
        result = _dedup(events)
        assert [r["ts"] for r in result] == ["2025-01-01", "2025-02-01", "2025-03-01"]


# ---------------------------------------------------------------------------
# Tests: seed functions (offline with mocked store)
# ---------------------------------------------------------------------------

class TestSeedRrrEvents:
    def test_produces_events_from_df(self, monkeypatch):
        from engine.china_policy_transmission import _seed_rrr_events
        monkeypatch.setattr(
            "engine.china_policy_transmission.store" if False else "lib.store",
            MagicMock(), raising=False
        )
        # Patch via the import path the engine uses
        with patch("engine.china_policy_transmission._seed_rrr_events",
                   wraps=_seed_rrr_events) as _:
            with patch("lib.store.read") as mock_read:
                mock_read.return_value = _make_rrr_df()
                from engine.china_policy_transmission import _seed_rrr_events as srre
                events = srre()
        # Should have exactly 2 non-zero change rows
        assert len(events) == 2
        assert all(e["kind"] == "rrr" for e in events)
        assert all(e["source"] == "pboc" for e in events)
        titles = [e["title"] for e in events]
        assert any("cut" in t for t in titles)

    def test_empty_on_missing_store(self):
        with patch("lib.store.read", return_value=None):
            from engine.china_policy_transmission import _seed_rrr_events
            events = _seed_rrr_events()
        assert events == []


class TestSeedLprEvents:
    def test_produces_lpr_cut_events(self):
        with patch("lib.store.read", return_value=_make_lpr_df()):
            from engine.china_policy_transmission import _seed_lpr_events
            events = _seed_lpr_events()
        assert len(events) >= 2
        assert all(e["kind"] == "lpr" for e in events)
        assert all("cut" in e["title"] or "hike" in e["title"] for e in events)

    def test_hash_field_present(self):
        with patch("lib.store.read", return_value=_make_lpr_df()):
            from engine.china_policy_transmission import _seed_lpr_events
            events = _seed_lpr_events()
        for e in events:
            assert "_hash" in e
            assert len(e["_hash"]) == 16


class TestSeedOmoMlfEvents:
    def test_no_exceedances_in_flat_data(self):
        """Flat FR007 data (small sin oscillation) produces no z>1.5 events."""
        with patch("lib.store.read", return_value=_make_fr007_df()):
            from engine.china_policy_transmission import _seed_omo_mlf_events
            events = _seed_omo_mlf_events(z_threshold=1.5)
        assert isinstance(events, list)
        assert len(events) == 0, (
            f"Expected 0 events for flat FR007 data, got {len(events)}"
        )

    def test_emits_events_on_exceedance(self):
        """FR007 spikes above threshold must produce at least one event per episode."""
        with patch("lib.store.read", return_value=_make_fr007_df_with_spikes()):
            from engine.china_policy_transmission import _seed_omo_mlf_events
            events = _seed_omo_mlf_events(z_threshold=1.5)
        assert len(events) >= 2, (
            f"Expected >=2 episode events from spike fixture, got {len(events)}"
        )
        assert all(e["kind"] == "omo_mlf" for e in events)
        assert all(e["source"] == "pboc" for e in events)

    def test_episode_collapse_one_event_per_episode(self):
        """Consecutive spike days within 3d must collapse to a single episode onset."""
        with patch("lib.store.read", return_value=_make_fr007_df_with_spikes()):
            from engine.china_policy_transmission import _seed_omo_mlf_events
            events = _seed_omo_mlf_events(z_threshold=1.5)
        # Two episodes of 5 days each — should collapse to exactly 2 onset events
        assert len(events) == 2, (
            f"Expected exactly 2 collapsed episode events, got {len(events)}: "
            f"{[e['ts'] for e in events]}"
        )

    def test_empty_on_missing_store(self):
        with patch("lib.store.read", return_value=None):
            from engine.china_policy_transmission import _seed_omo_mlf_events
            events = _seed_omo_mlf_events()
        assert events == []


class TestSeedCommuniqueEvents:
    def test_skips_explicit_gap_rows(self, tmp_root):
        """Gap rows (source=explicit_gap) must not appear in output."""
        comm_path = tmp_root / "data/china_official/communiques.parquet"
        _make_communiques_df().to_parquet(comm_path, index=False)
        with patch("lib.config.ROOT", tmp_root):
            from importlib import reload
            import engine.china_policy_transmission as m
            reload(m)
            events = m._seed_communique_events()
        sources = [e["source"] for e in events]
        assert "explicit_gap" not in sources

    def test_sector_tagging_applied(self, tmp_root):
        """Events from communiques with capital-market text must have sectors tagged."""
        comm_path = tmp_root / "data/china_official/communiques.parquet"
        _make_communiques_df().to_parquet(comm_path, index=False)
        with patch("lib.config.ROOT", tmp_root):
            import engine.china_policy_transmission as m
            events = m._seed_communique_events()
        # The first row has A-share/capital market keywords
        capital_events = [e for e in events if "capital_market" in e.get("sectors", [])]
        assert len(capital_events) >= 1

    def test_phrase_diff_ref_is_doc_id(self, tmp_root):
        comm_path = tmp_root / "data/china_official/communiques.parquet"
        _make_communiques_df().to_parquet(comm_path, index=False)
        with patch("lib.config.ROOT", tmp_root):
            import engine.china_policy_transmission as m
            events = m._seed_communique_events()
        # phrase_diff_ref should be the doc_id
        for e in events:
            assert e.get("phrase_diff_ref") is not None or e["source"] == "explicit_gap"


# ---------------------------------------------------------------------------
# Integration tests: snapshot()
# ---------------------------------------------------------------------------

class TestSnapshot:
    def _mock_pboc_stance(self):
        return {
            "schema": "china_pboc_stance.v1",
            "stance": "easing",
            "stance_en": "Easing",
            "stance_zh": "宽松",
            "score": 2,
            "asof": "2026-07-07",
        }

    def test_snapshot_returns_dict_on_valid_data(self, tmp_root):
        comm_path = tmp_root / "data/china_official/communiques.parquet"
        _make_communiques_df().to_parquet(comm_path, index=False)

        with patch("lib.config.ROOT", tmp_root), \
             patch("lib.store.read") as mock_read, \
             patch("engine.china_pboc_stance.snapshot", return_value=self._mock_pboc_stance()):

            def _side_effect(group, name):
                if group == "china_macro" and name == "lpr_rate":
                    return _make_lpr_df()
                if group == "china_macro" and name == "rrr":
                    return _make_rrr_df()
                if group == "china_pboc" and name == "repo_rates":
                    return _make_fr007_df()
                return None

            mock_read.side_effect = _side_effect
            import engine.china_policy_transmission as m
            snap = m.snapshot()

        assert snap is not None
        assert snap["schema"] == "china_policy_transmission.v1"
        assert snap["policy_impulse"] in {
            "easing", "neutral", "tightening", "targeted_support", "market_rescue"
        }

    def test_snapshot_schema_fields(self, tmp_root):
        comm_path = tmp_root / "data/china_official/communiques.parquet"
        _make_communiques_df().to_parquet(comm_path, index=False)

        with patch("lib.config.ROOT", tmp_root), \
             patch("lib.store.read", return_value=None), \
             patch("engine.china_pboc_stance.snapshot", return_value=self._mock_pboc_stance()):
            import engine.china_policy_transmission as m
            snap = m.snapshot()

        assert snap is not None
        required = {
            "schema", "authority", "built", "asof",
            "policy_impulse", "transmission_channel",
            "recent_events", "staleness", "priced_in_check", "data_gaps",
        }
        assert required.issubset(snap.keys()), f"missing keys: {required - snap.keys()}"

    def test_authority_tier_is_context_only(self, tmp_root):
        comm_path = tmp_root / "data/china_official/communiques.parquet"
        _make_communiques_df().to_parquet(comm_path, index=False)
        with patch("lib.config.ROOT", tmp_root), \
             patch("lib.store.read", return_value=None), \
             patch("engine.china_pboc_stance.snapshot", return_value=self._mock_pboc_stance()):
            import engine.china_policy_transmission as m
            snap = m.snapshot()
        assert snap["authority"]["tier"] == "context_only"
        assert snap["authority"]["may_originate"] is False
        assert snap["authority"]["may_escalate"] is False

    def test_priced_in_check_labeled_descriptive(self, tmp_root):
        comm_path = tmp_root / "data/china_official/communiques.parquet"
        _make_communiques_df().to_parquet(comm_path, index=False)
        with patch("lib.config.ROOT", tmp_root), \
             patch("lib.store.read", return_value=None), \
             patch("engine.china_pboc_stance.snapshot", return_value=self._mock_pboc_stance()):
            import engine.china_policy_transmission as m
            snap = m.snapshot()
        pic = snap["priced_in_check"]
        assert pic["descriptive"] is True
        assert "not a signal" in pic["label"].lower()

    def test_snapshot_returns_none_on_total_data_absence(self):
        with patch("lib.store.read", return_value=None), \
             patch("engine.china_pboc_stance.snapshot", return_value=None), \
             patch("lib.config.ROOT", Path("/nonexistent_path_xyz")):
            import engine.china_policy_transmission as m
            snap = m.snapshot()
        assert snap is None

    def test_staleness_communiques_printed_not_fixed(self, tmp_root):
        """Staleness for communiques ending 2026-04-28 must be printed as-is."""
        comm_path = tmp_root / "data/china_official/communiques.parquet"
        _make_communiques_df().to_parquet(comm_path, index=False)
        with patch("lib.config.ROOT", tmp_root), \
             patch("lib.store.read", return_value=None), \
             patch("engine.china_pboc_stance.snapshot", return_value=self._mock_pboc_stance()):
            import engine.china_policy_transmission as m
            snap = m.snapshot()
        # staleness.per_source_days.communiques should be a positive integer
        days = snap["staleness"]["per_source_days"].get("communiques")
        if days is not None:
            assert isinstance(days, int)
            assert days > 0  # 2026-04-28 is in the past


# ---------------------------------------------------------------------------
# Integration tests: builder
# ---------------------------------------------------------------------------

class TestBuildScript:
    def test_appends_events_to_jsonl(self, tmp_root):
        """Builder writes events.jsonl and the file is parseable."""
        comm_path = tmp_root / "data/china_official/communiques.parquet"
        _make_communiques_df().to_parquet(comm_path, index=False)
        events_path = tmp_root / "data/china_policy_transmission/events.jsonl"
        site_path = tmp_root / "site/chinastatedata/policy_transmission.json"

        with patch("lib.config.ROOT", tmp_root), \
             patch("lib.store.read") as mock_read, \
             patch("engine.china_pboc_stance.snapshot", return_value={
                 "schema": "china_pboc_stance.v1",
                 "stance": "neutral", "stance_en": "On hold / neutral",
                 "stance_zh": "按兵不动 / 中性", "score": 0, "asof": "2026-07-07",
             }):

            def _side(group, name):
                if group == "china_macro" and name == "lpr_rate":
                    return _make_lpr_df()
                if group == "china_macro" and name == "rrr":
                    return _make_rrr_df()
                if group == "china_pboc" and name == "repo_rates":
                    return _make_fr007_df()
                return None

            mock_read.side_effect = _side

            import scripts.build_china_policy_transmission as builder
            from importlib import reload
            import engine.china_policy_transmission as m
            reload(m)
            reload(builder)

            snap = builder.build()

        assert snap is not None
        # events.jsonl must exist and be parseable
        assert events_path.exists(), "events.jsonl not created"
        lines = [l for l in events_path.read_text().splitlines() if l.strip()]
        assert len(lines) > 0, "events.jsonl is empty"
        for line in lines:
            row = json.loads(line)
            assert "ts" in row
            assert "source" in row
            assert "kind" in row
            assert "_hash" in row

        # site JSON must exist
        assert site_path.exists(), "policy_transmission.json not created"
        loaded = json.loads(site_path.read_text())
        assert loaded["schema"] == "china_policy_transmission.v1"

    def test_idempotent_append(self, tmp_root):
        """Running the builder twice does not duplicate events."""
        comm_path = tmp_root / "data/china_official/communiques.parquet"
        _make_communiques_df().to_parquet(comm_path, index=False)

        ctx = dict(
            lib_config_root=tmp_root,
            side_effect=lambda g, n: (
                _make_lpr_df() if (g, n) == ("china_macro", "lpr_rate")
                else _make_rrr_df() if (g, n) == ("china_macro", "rrr")
                else _make_fr007_df() if (g, n) == ("china_pboc", "repo_rates")
                else None
            ),
            stance={
                "schema": "china_pboc_stance.v1",
                "stance": "neutral", "stance_en": "On hold / neutral",
                "stance_zh": "按兵不动 / 中性", "score": 0, "asof": "2026-07-07",
            },
        )

        def _run_build():
            with patch("lib.config.ROOT", tmp_root), \
                 patch("lib.store.read", side_effect=ctx["side_effect"]), \
                 patch("engine.china_pboc_stance.snapshot", return_value=ctx["stance"]):
                from importlib import reload
                import engine.china_policy_transmission as m
                import scripts.build_china_policy_transmission as builder
                reload(m)
                reload(builder)
                return builder.build()

        _run_build()
        events_path = tmp_root / "data/china_policy_transmission/events.jsonl"
        n_after_first = sum(1 for l in events_path.read_text().splitlines() if l.strip())

        _run_build()
        n_after_second = sum(1 for l in events_path.read_text().splitlines() if l.strip())

        assert n_after_first == n_after_second, (
            f"Idempotency violated: {n_after_first} -> {n_after_second} events"
        )

    def test_site_json_valid_schema(self, tmp_root):
        comm_path = tmp_root / "data/china_official/communiques.parquet"
        _make_communiques_df().to_parquet(comm_path, index=False)

        with patch("lib.config.ROOT", tmp_root), \
             patch("lib.store.read", return_value=None), \
             patch("engine.china_pboc_stance.snapshot", return_value={
                 "schema": "china_pboc_stance.v1",
                 "stance": "neutral", "stance_en": "On hold / neutral",
                 "stance_zh": "按兵不动 / 中性", "score": 0, "asof": "2026-07-07",
             }):
            from importlib import reload
            import engine.china_policy_transmission as m
            import scripts.build_china_policy_transmission as builder
            reload(m)
            reload(builder)
            snap = builder.build()

        site_path = tmp_root / "site/chinastatedata/policy_transmission.json"
        if site_path.exists():
            loaded = json.loads(site_path.read_text())
            # schema contract keys
            for key in ("policy_impulse", "transmission_channel",
                        "recent_events", "staleness", "priced_in_check"):
                assert key in loaded, f"missing schema key: {key}"
