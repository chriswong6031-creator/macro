"""Tests for the china_visits dossier block in engine/china_intel_hub.py (P1).

Descriptive-only surface — NO score, NO rank input (masterplan §11.4 serial
firewall). Covers:
  - _ticker_to_sec_code: SZ/SS mapping, HK/malformed → None (not_applicable)
  - _visit_block: each reachable house failure state (masterplan §9.3):
    not_applicable, no_coverage, source_failure, stale, measured_no_event, ok
  - first_seen_since_coverage_start is flagged on the EARLIEST row only, and
    a name first seen mid-coverage still reads "since coverage start", never
    "first ever"
  - _load_visits_context degrades safely against a real (empty) store
  - build() integration: the visits block appears on command rows and never
    moves opportunity_score/edge_remaining/stage (score neutrality)
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import china_intel_hub as hub  # noqa: E402
from lib import config  # noqa: E402


# --------------------------------------------------------------------------- #
# _ticker_to_sec_code
# --------------------------------------------------------------------------- #

class TestTickerToSecCode:
    def test_sz_ticker(self):
        assert hub._ticker_to_sec_code("000001.SZ") == ("000001", "szse")

    def test_ss_ticker(self):
        assert hub._ticker_to_sec_code("600519.SS") == ("600519", "sse")

    def test_hk_ticker_is_none(self):
        assert hub._ticker_to_sec_code("0700.HK") is None

    def test_no_dot_is_none(self):
        assert hub._ticker_to_sec_code("000001") is None

    def test_empty_is_none(self):
        assert hub._ticker_to_sec_code("") is None
        assert hub._ticker_to_sec_code(None) is None


# --------------------------------------------------------------------------- #
# _visit_block — house failure-state taxonomy
# --------------------------------------------------------------------------- #

def _ctx(by_code=None, coverage_start=None, health=None):
    return {"by_code": by_code or {}, "coverage_start": coverage_start,
            "health": health or {}}


class TestVisitBlockStates:
    def test_not_applicable_for_hk_ticker(self):
        block = hub._visit_block("0700.HK", _ctx(coverage_start="2026-08-01",
                                                    health={"status": "ok"}))
        assert block["state"] == "not_applicable"
        assert block["recent"] == []

    def test_no_coverage_when_never_started(self):
        block = hub._visit_block("000001.SZ", _ctx(coverage_start=None,
                                                       health={"status": "no_coverage"}))
        assert block["state"] == "no_coverage"
        assert block["recent"] == []

    def test_source_failure_takes_priority(self):
        block = hub._visit_block("000001.SZ", _ctx(
            coverage_start="2026-08-01",
            health={"status": "source_failure", "detail": "filings store unreadable"}))
        assert block["state"] == "source_failure"
        assert "unreadable" in block["detail"]
        assert block["recent"] == []

    def test_measured_no_event_when_healthy_and_absent(self):
        fresh = datetime.now(timezone.utc).isoformat()
        block = hub._visit_block("000001.SZ", _ctx(
            coverage_start="2026-08-01",
            health={"status": "ok", "last_success_utc": fresh}))
        assert block["state"] == "measured_no_event"
        assert block["recent"] == []
        # honest — never claims a real-world "first ever"
        assert "since coverage start" in block["detail"]

    def test_stale_when_healthy_but_last_success_old(self):
        old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        block = hub._visit_block("000001.SZ", _ctx(
            coverage_start="2026-08-01",
            health={"status": "ok", "last_success_utc": old}))
        assert block["state"] == "stale"
        assert block["recent"] == []
        assert block["stale_days"] == 10

    def test_ok_with_rows_carries_typed_visitor_fields(self):
        rows = [{
            "announcement_id": "A1", "sec_code": "000001",
            "title": "平安银行：投资者关系活动记录表",
            "source_published_at": "2026-08-19T09:00:00+08:00",
            "visitor_raw": "not_yet_available", "visitor_class": "not_yet_available",
            "ontology_version": "B0_DRAFT_pin-3d12412e561e", "adjunct_url": "/x.pdf",
        }]
        fresh = datetime.now(timezone.utc).isoformat()
        block = hub._visit_block("000001.SZ", _ctx(
            by_code={"000001": rows}, coverage_start="2026-08-01",
            health={"status": "ok", "last_success_utc": fresh}))
        assert block["state"] == "ok"
        assert len(block["recent"]) == 1
        r = block["recent"][0]
        assert r["visitor_raw"] == "not_yet_available"
        assert r["visitor_class"] == "not_yet_available"
        assert r["ontology_version"] == "B0_DRAFT_pin-3d12412e561e"
        assert r["first_seen_since_coverage_start"] is True   # the only row = earliest
        assert r["kind_en"] == "investor visit"    # default fallback (row carries no kind_*)
        assert r["kind_zh"] == "机构调研"

    def test_ok_row_propagates_kind_label_from_load_visits_context(self):
        # Simulates what _load_visits_context() actually attaches per row.
        rows = [{
            "announcement_id": "A2", "sec_code": "000002",
            "title": "关于接待特定对象调研的公告",
            "source_published_at": "2026-08-19T09:00:00+08:00",
            "visitor_raw": "not_yet_available", "visitor_class": "not_yet_available",
            "ontology_version": "v1", "adjunct_url": "",
            "kind_en": "site visit", "kind_zh": "特定对象调研",
        }]
        fresh = datetime.now(timezone.utc).isoformat()
        block = hub._visit_block("000002.SZ", _ctx(
            by_code={"000002": rows}, coverage_start="2026-08-01",
            health={"status": "ok", "last_success_utc": fresh}))
        assert block["recent"][0]["kind_en"] == "site visit"
        assert block["recent"][0]["kind_zh"] == "特定对象调研"

    def test_first_seen_flag_only_on_earliest_row(self):
        rows = [
            {"announcement_id": "A1", "sec_code": "000001", "title": "t1",
             "source_published_at": "2026-08-05T09:00:00+08:00",
             "visitor_raw": "not_yet_available", "visitor_class": "not_yet_available",
             "ontology_version": "v1", "adjunct_url": ""},
            {"announcement_id": "A2", "sec_code": "000001", "title": "t2",
             "source_published_at": "2026-08-15T09:00:00+08:00",
             "visitor_raw": "not_yet_available", "visitor_class": "not_yet_available",
             "ontology_version": "v1", "adjunct_url": ""},
        ]
        fresh = datetime.now(timezone.utc).isoformat()
        block = hub._visit_block("000001.SZ", _ctx(
            by_code={"000001": rows}, coverage_start="2026-08-01",
            health={"status": "ok", "last_success_utc": fresh}))
        by_id = {r["title"]: r["first_seen_since_coverage_start"] for r in block["recent"]}
        assert by_id["t1"] is True
        assert by_id["t2"] is False

    def test_mid_coverage_first_sighting_still_says_since_not_ever(self):
        # A name whose ONLY observed row lands well after coverage_start —
        # must still be labeled "since coverage start", never "first ever".
        rows = [{"announcement_id": "A9", "sec_code": "000009", "title": "mid",
                  "source_published_at": "2026-08-18T09:00:00+08:00",
                  "visitor_raw": "not_yet_available", "visitor_class": "not_yet_available",
                  "ontology_version": "v1", "adjunct_url": ""}]
        fresh = datetime.now(timezone.utc).isoformat()
        block = hub._visit_block("000009.SZ", _ctx(
            by_code={"000009": rows}, coverage_start="2026-08-01",  # coverage started earlier
            health={"status": "ok", "last_success_utc": fresh}))
        assert block["recent"][0]["first_seen_since_coverage_start"] is True
        # the wording itself never claims "first ever" anywhere in the block
        assert "first ever" not in str(block).lower()

    def test_never_raises_on_malformed_ctx(self):
        # A visit_ctx missing keys entirely must degrade, never crash.
        block = hub._visit_block("000001.SZ", {})
        assert block["state"] in {"no_coverage", "source_failure"}


# --------------------------------------------------------------------------- #
# _load_visits_context — degrades against a real (empty) store
# --------------------------------------------------------------------------- #

class TestLoadVisitsContext:
    def test_empty_store_is_no_coverage(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        ctx = hub._load_visits_context()
        assert ctx["by_code"] == {}
        assert ctx["coverage_start"] is None
        assert ctx["health"]["status"] == "no_coverage"

    def test_after_a_real_refresh_ctx_reflects_it(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        import collectors.china_filings as cf
        import collectors.china_visits as cv

        cf.write_filings([{
            "announcementId": "A1", "sec_code": "000001", "sec_name": "n",
            "org_id": "o", "title": "投资者关系活动记录表",
            "publish_ts": "2026-08-19T09:00:00+08:00", "exchange": "szse",
            "category": "institutional_visit", "kind": None,
            "announcement_type_raw": "", "adjunct_url": "/x.pdf",
            "adjunct_type": "PDF", "_collected_at": "2026-08-19T09:00:00+08:00",
        }])
        s = cv.refresh()
        assert s["status"] == "ok"

        ctx = hub._load_visits_context()
        assert ctx["coverage_start"] is not None
        assert ctx["health"]["status"] == "ok"
        assert "000001" in ctx["by_code"]
        # kind label is attached at load time, not left for the template to guess
        assert ctx["by_code"]["000001"][0]["kind_en"] == "IR activity record"
        assert ctx["by_code"]["000001"][0]["kind_zh"] == "投资者关系活动记录表"


# --------------------------------------------------------------------------- #
# build() integration — visits block present, score neutrality
# --------------------------------------------------------------------------- #

def _altdata_row(ticker, convergence=0.85, conviction100=90):
    return {"ticker": ticker, "name": ticker, "convergence": convergence,
            "conviction100": conviction100, "reasons": [], "flags": [], "side": "accumulate"}


class TestBuildIntegration:
    def test_visits_block_present_on_every_command_row(self, monkeypatch):
        altdata = {
            "schema": "china_altdata.v1", "is_context_only": True,
            "asof": "2026-08-20", "n_universe": 1, "n_triple": 0,
            "triple": [], "top": [_altdata_row("600519.SS")],
            "bottom": [], "crowding_flags": [],
        }

        def _mock_read(rel):
            if "chinaaltdata" in rel:
                return altdata
            return None

        monkeypatch.setattr(hub, "_read_json", _mock_read)
        monkeypatch.setattr(hub, "_load_closes_and_benchmark", lambda: (None, None))
        monkeypatch.setattr(hub, "_append_snapshot_ledger", lambda *a, **kw: None)
        monkeypatch.setattr(hub, "_load_visits_context",
                             lambda: {"by_code": {}, "coverage_start": None,
                                       "health": {"status": "no_coverage"}})

        result = hub.build(today=date(2026, 8, 20))
        assert len(result["command"]) >= 1
        for d in result["command"]:
            assert "visits" in d
            assert d["visits"]["state"] in {
                "not_applicable", "no_coverage", "source_failure", "stale",
                "measured_no_event", "ok",
            }

    def test_visit_data_never_moves_opportunity_or_stage(self, monkeypatch):
        """Score neutrality: identical desk inputs must produce byte-identical
        opportunity_score/edge_remaining/stage whether the visit tape is
        empty or carries rows — visits are descriptive, never a signal."""
        altdata = {
            "schema": "china_altdata.v1", "is_context_only": True,
            "asof": "2026-08-20", "n_universe": 1, "n_triple": 0,
            "triple": [], "top": [_altdata_row("600519.SS")],
            "bottom": [], "crowding_flags": [],
        }

        def _mock_read(rel):
            if "chinaaltdata" in rel:
                return altdata
            return None

        monkeypatch.setattr(hub, "_read_json", _mock_read)
        monkeypatch.setattr(hub, "_load_closes_and_benchmark", lambda: (None, None))
        monkeypatch.setattr(hub, "_append_snapshot_ledger", lambda *a, **kw: None)

        monkeypatch.setattr(hub, "_load_visits_context",
                             lambda: {"by_code": {}, "coverage_start": None,
                                       "health": {"status": "no_coverage"}})
        no_visits = hub.build(today=date(2026, 8, 20))

        fresh = datetime.now(timezone.utc).isoformat()
        monkeypatch.setattr(hub, "_load_visits_context", lambda: {
            "by_code": {"600519": [{
                "announcement_id": "A1", "sec_code": "600519", "title": "t",
                "source_published_at": "2026-08-19T09:00:00+08:00",
                "visitor_raw": "not_yet_available", "visitor_class": "not_yet_available",
                "ontology_version": "v1", "adjunct_url": "",
            }]},
            "coverage_start": "2026-08-01",
            "health": {"status": "ok", "last_success_utc": fresh},
        })
        with_visits = hub.build(today=date(2026, 8, 20))

        d0 = no_visits["command"][0]
        d1 = with_visits["command"][0]
        assert d0["opportunity_score"] == d1["opportunity_score"]
        assert d0["edge_remaining"] == d1["edge_remaining"]
        assert d0["stage"] == d1["stage"]
        assert d0["lean"] == d1["lean"]
        # the visits block itself DID change, proving the fixture took effect
        assert d0["visits"]["state"] != d1["visits"]["state"]
