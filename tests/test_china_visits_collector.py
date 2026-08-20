"""Tests for collectors/china_visits.py — China institutional-visit tape (P1).

Pure/offline surface only — no network (this collector DERIVES from
china_filings' own store, it never calls CNInfo itself). Covers:
  - resolve_actor(): typed 'unresolved' default, deterministic exact-match,
    ontology_version stamped on every result (masterplan §5 exact-identity law)
  - _derive_row(): pure mapping, visitor fields typed 'not_yet_available'
    (metadata-first stage — RUL-4 never fetches PDF bodies)
  - write_visits/load_visits: dedup keep-FIRST on announcement_id, atomic
    write, unreadable-store ABORT (never silently replaces accrued history)
  - coverage_start: stamped once on first success, never rewritten
  - refresh(): filters china_filings' store to category=='institutional_visit',
    degrades to typed health states (no_coverage / source_failure / ok),
    and NEVER raises — including under an injected china_filings failure
    (isolation: lane survives, health goes loud)
  - ChinaVisitsAdapter.fetch(): sentinel summary frame carries a DatetimeIndex
    (required by base.validate())

Storage is redirected to tmp_path (monkeypatched lib.config.data_dir) so no
tracked parquet is ever dirtied.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collectors.china_filings as cf  # noqa: E402
import collectors.china_visits as cv  # noqa: E402
from lib import config  # noqa: E402


@pytest.fixture(autouse=True)
def _tmp_data_dir(tmp_path, monkeypatch):
    """Every test gets its own data dir — china_filings and china_visits
    share `config.data_dir()`, exactly as they do in production."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    yield tmp_path


def _filing_row(announcement_id: str, sec_code: str, title: str,
                 publish_ts: str, category: str = "institutional_visit",
                 exchange: str = "szse", adjunct_url: str = "/x.pdf") -> dict:
    return {
        "announcementId": announcement_id, "sec_code": sec_code,
        "sec_name": f"name-{sec_code}", "org_id": f"org-{sec_code}",
        "title": title, "publish_ts": publish_ts, "exchange": exchange,
        "category": category, "kind": None, "announcement_type_raw": "",
        "adjunct_url": adjunct_url, "adjunct_type": "PDF",
        "_collected_at": publish_ts,
    }


# --------------------------------------------------------------------------- #
# resolve_actor — identity resolution
# --------------------------------------------------------------------------- #

class TestResolveActor:
    def test_empty_string_is_unresolved(self):
        cls, ver = cv.resolve_actor("")
        assert cls == "unresolved"
        assert ver == cv.ONTOLOGY_VERSION

    def test_unknown_name_is_unresolved_never_fuzzy(self):
        cls, ver = cv.resolve_actor("某某私募基金管理有限公司")
        assert cls == "unresolved"
        assert ver == cv.ONTOLOGY_VERSION

    def test_deterministic_exact_match(self, monkeypatch):
        # Prove the resolution mechanism works for a FUTURE deterministic
        # mapping without asserting today's (deliberately empty) table.
        monkeypatch.setattr(cv, "_KNOWN_ACTORS", {"某已知机构": "class_1_concentrated"})
        cls, ver = cv.resolve_actor("某已知机构")
        assert cls == "class_1_concentrated"
        assert ver == cv.ONTOLOGY_VERSION

    def test_near_miss_does_not_fuzzy_match(self, monkeypatch):
        monkeypatch.setattr(cv, "_KNOWN_ACTORS", {"某已知机构": "class_1_concentrated"})
        cls, _ = cv.resolve_actor("某已知机构（分公司）")
        assert cls == "unresolved"


# --------------------------------------------------------------------------- #
# _derive_row — pure mapping
# --------------------------------------------------------------------------- #

class TestDeriveRow:
    def test_maps_fields_and_types_visitor_not_yet_available(self):
        filing = _filing_row("A1", "000001", "平安银行：投资者关系活动记录表",
                              "2026-08-19T09:00:00+08:00")
        row = cv._derive_row(filing, "2026-08-20T00:00:00+00:00")
        assert row["announcement_id"] == "A1"
        assert row["sec_code"] == "000001"
        assert row["source_published_at"] == "2026-08-19T09:00:00+08:00"
        assert row["system_recorded_at"] == "2026-08-20T00:00:00+00:00"
        assert row["visitor_raw"] == "not_yet_available"
        assert row["visitor_class"] == "not_yet_available"
        assert row["ontology_version"] == cv.ONTOLOGY_VERSION
        assert row["adjunct_url"] == "/x.pdf"


# --------------------------------------------------------------------------- #
# write_visits / load_visits — dedup, atomic write, unreadable-store abort
# --------------------------------------------------------------------------- #

class TestStore:
    def test_load_visits_empty_when_absent(self):
        df = cv.load_visits()
        assert df.empty
        assert list(df.columns) == list(cv._VISIT_COLUMNS)

    def test_write_then_load_roundtrip(self):
        row = cv._derive_row(_filing_row("A1", "000001", "t", "2026-08-19T09:00:00+08:00"),
                              "2026-08-20T00:00:00+00:00")
        n = cv.write_visits([row])
        assert n == 1
        df = cv.load_visits()
        assert len(df) == 1
        assert df.iloc[0]["announcement_id"] == "A1"

    def test_dedup_keep_first_on_announcement_id(self):
        row1 = cv._derive_row(_filing_row("A1", "000001", "title-v1", "2026-08-19T09:00:00+08:00"),
                               "2026-08-20T00:00:00+00:00")
        row2 = cv._derive_row(_filing_row("A1", "000001", "title-v2", "2026-08-19T09:00:00+08:00"),
                               "2026-08-21T00:00:00+00:00")
        n1 = cv.write_visits([row1])
        n2 = cv.write_visits([row2])
        assert n1 == 1
        assert n2 == 0   # duplicate announcement_id — keep-FIRST, no net-new
        df = cv.load_visits()
        assert len(df) == 1
        assert df.iloc[0]["title"] == "title-v1"   # first write wins, never overwritten

    def test_empty_rows_is_a_noop(self):
        assert cv.write_visits([]) == 0

    def test_unreadable_store_aborts_append(self, tmp_path):
        store_dir = tmp_path / cv.GROUP
        store_dir.mkdir(parents=True, exist_ok=True)
        bad_path = store_dir / "visits.parquet"
        bad_path.write_bytes(b"not a parquet file")

        row = cv._derive_row(_filing_row("A1", "000001", "t", "2026-08-19T09:00:00+08:00"),
                              "2026-08-20T00:00:00+00:00")
        n = cv.write_visits([row])
        assert n == 0
        # untouched — manual recovery, never silently replaced
        assert bad_path.read_bytes() == b"not a parquet file"


# --------------------------------------------------------------------------- #
# coverage_start — write-once
# --------------------------------------------------------------------------- #

class TestCoverageStart:
    def test_none_when_never_stamped(self):
        assert cv.read_coverage_start() is None

    def test_stamped_once_and_never_overwritten(self):
        cv._stamp_coverage_start_once("2026-08-20")
        assert cv.read_coverage_start() == "2026-08-20"
        cv._stamp_coverage_start_once("2026-09-01")   # later call — must not move
        assert cv.read_coverage_start() == "2026-08-20"


# --------------------------------------------------------------------------- #
# refresh() — derivation, health states, isolation
# --------------------------------------------------------------------------- #

class TestRefresh:
    def test_no_coverage_when_filings_store_absent(self):
        s = cv.refresh()
        assert s["status"] == "no_coverage"
        assert s["n_candidates"] == 0
        assert s["n_new"] == 0
        assert cv.read_health()["status"] == "no_coverage"
        # a run that never successfully read a source must NOT start coverage
        assert cv.read_coverage_start() is None

    def test_ok_derives_only_visit_category_rows(self):
        rows = [
            _filing_row("A1", "000001", "顺网科技：投资者关系活动记录表",
                        "2026-08-19T09:00:00+08:00", category="institutional_visit"),
            _filing_row("A2", "000002", "关于回购股份的公告",
                        "2026-08-19T10:00:00+08:00", category="buyback"),
            _filing_row("A3", "000003", "某公司特定对象调研纪要",
                        "2026-08-19T11:00:00+08:00", category="institutional_visit"),
        ]
        cf.write_filings(rows)

        s = cv.refresh()
        assert s["status"] == "ok"
        assert s["n_candidates"] == 2   # A1, A3 only — buyback excluded
        assert s["n_new"] == 2

        df = cv.load_visits()
        assert set(df["announcement_id"]) == {"A1", "A3"}
        assert cv.read_health()["status"] == "ok"
        assert cv.read_coverage_start() is not None

    def test_second_refresh_is_idempotent(self):
        rows = [_filing_row("A1", "000001", "投资者关系活动记录表",
                             "2026-08-19T09:00:00+08:00")]
        cf.write_filings(rows)
        s1 = cv.refresh()
        s2 = cv.refresh()
        assert s1["n_new"] == 1
        assert s2["n_new"] == 0   # same filings store, nothing new
        assert len(cv.load_visits()) == 1

    def test_corrupt_filings_store_is_source_failure_not_measured_no_event(self, tmp_path):
        # Simulate schema drift / corruption in the UPSTREAM store — not a
        # transport failure, but this plane's own read still failed.
        filings_dir = tmp_path / "china_filings"
        filings_dir.mkdir(parents=True, exist_ok=True)
        (filings_dir / "filings.parquet").write_bytes(b"not a parquet file")

        s = cv.refresh()
        assert s["status"] == "source_failure"
        assert s["n_candidates"] == 0
        assert s["n_new"] == 0
        health = cv.read_health()
        assert health["status"] == "source_failure"
        # LOUD: the failure is named in the persisted health record
        assert health.get("detail")
        # coverage must NOT start on a failed run — no false "we looked" claim
        assert cv.read_coverage_start() is None

    def test_injected_unexpected_failure_never_raises(self, monkeypatch):
        """Belt-and-suspenders: an unanticipated exception ANYWHERE inside
        refresh() (not just the known filings-read failure modes) must still
        degrade to a typed health record instead of escaping — the
        market-critical asia lane must survive any bug in this plane."""
        rows = [_filing_row("A1", "000001", "投资者关系活动记录表",
                             "2026-08-19T09:00:00+08:00")]
        cf.write_filings(rows)

        def _boom(*a, **kw):
            raise RuntimeError("simulated unexpected failure")
        monkeypatch.setattr(cv, "_derive_row", _boom)

        s = cv.refresh()   # must not raise
        assert s["status"] == "source_failure"
        assert cv.read_health()["status"] == "source_failure"
        # a run that blew up mid-derivation must not claim it looked
        assert cv.read_coverage_start() is None


# --------------------------------------------------------------------------- #
# ChinaVisitsAdapter — summary frame shape
# --------------------------------------------------------------------------- #

class TestAdapter:
    def test_fetch_returns_datetimeindex_summary(self):
        adapter = cv.ChinaVisitsAdapter()
        frames = adapter.fetch()
        assert "china_visits_summary" in frames
        summary = frames["china_visits_summary"]
        assert isinstance(summary.index, pd.DatetimeIndex)
        assert "n_candidates" in summary.columns
        assert "n_new" in summary.columns

    def test_fetch_never_raises_when_source_absent(self):
        adapter = cv.ChinaVisitsAdapter()
        frames = adapter.fetch()   # no filings store at all — must not raise
        assert frames["china_visits_summary"]["n_new"].iloc[0] == 0.0
