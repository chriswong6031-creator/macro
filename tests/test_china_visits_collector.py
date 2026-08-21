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
  - P1-R1 same-cycle derivation (Sol product ruling 2026-08-20): scripts/collect.py
    now runs china_visits in the SAME cninfo host-group thread as china_filings,
    immediately after it, so a single collect invocation consumes the SAME
    cycle's freshly-written filings store instead of the prior night's. Covers:
    the registry-order + concurrent-host-group contract (T6), same-run "ok"
    consumption end-to-end via scripts.collect.main() (T1), total/partial
    same-run china_filings failure degrading china_visits to a typed
    "upstream_degraded" health state without discarding positive rows (T2/T3),
    idempotency (T4), the `--only china_visits` committed-store proof/debug
    path staying network-free and "ok" (T5), and the dossier's
    engine.china_intel_hub._visit_block never reading a degraded upstream as a
    clean "measured_no_event" (T7).

Storage is redirected to tmp_path (monkeypatched lib.config.data_dir) so no
tracked parquet is ever dirtied. Tests that drive scripts.collect.main() end
to end additionally redirect lib.store.read_status/write_status (which
resolve via config.ROOT + config.load(), NOT config.data_dir(), so the
data_dir redirect alone does not cover them) and neutralize collect.py's
~11 always-on end-of-collect steps (news_vector, qledger backfill/grader,
cctv watcher, governance audits, cn_holder_sale_calendar, source_registry) —
none of those relate to china_visits, several resolve paths straight off
config.ROOT rather than config.data_dir(), and at least one performs real
network I/O, so leaving them live would risk network calls and writes into
the real repo's data/ tree from a unit test (sparse-worktree law).
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collectors.china_filings as cf  # noqa: E402
import collectors.china_visits as cv  # noqa: E402
from lib import config  # noqa: E402
from lib import store as _store  # noqa: E402


@pytest.fixture(autouse=True)
def _tmp_data_dir(tmp_path, monkeypatch):
    """Every test gets its own data dir — china_filings and china_visits
    share `config.data_dir()`, exactly as they do in production."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    yield tmp_path


@pytest.fixture(autouse=True)
def _isolate_run_status(tmp_path, monkeypatch):
    """scripts/collect.py's main() (and collectors.base's circuit-breaker
    state) read/write run_status.json via lib.store.read_status/write_status,
    which resolve through config.ROOT + config.load() directly — NOT
    config.data_dir() — so the _tmp_data_dir redirect above does not cover
    them. Any test that drives scripts.collect.main() must redirect this too,
    or it silently mutates the real repo's data/run_status.json (sparse-
    worktree law: never let an unredirected writer touch data/)."""
    import json as _json
    status_path = tmp_path / "_run_status.json"

    def _read_status():
        if not status_path.exists():
            return {}
        return _json.loads(status_path.read_text())

    def _write_status(status):
        status_path.write_text(_json.dumps(status, indent=2, default=str))

    monkeypatch.setattr(_store, "read_status", _read_status)
    monkeypatch.setattr(_store, "write_status", _write_status)
    yield


@pytest.fixture(autouse=True)
def _reset_last_run_outcome():
    """collectors.china_filings.LAST_RUN_OUTCOME is process-local, module-
    global state (P1-R1 same-cycle derivation contract) — reset it around
    every test so no test inherits another's outcome flag."""
    cf.LAST_RUN_OUTCOME = None
    yield
    cf.LAST_RUN_OUTCOME = None


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


class TestVisitKindLabel:
    def test_earnings_briefing(self):
        assert cv.visit_kind_label("2026年半年度业绩说明会公告") == ("earnings briefing", "业绩说明会")

    def test_analyst_meeting(self):
        assert cv.visit_kind_label("2026年度分析师会议纪要") == ("analyst meeting", "分析师会议")

    def test_site_visit(self):
        assert cv.visit_kind_label("关于接待特定对象调研的公告") == ("site visit", "特定对象调研")

    def test_ir_activity_record(self):
        assert cv.visit_kind_label("顺网科技：投资者关系活动记录表") == (
            "IR activity record", "投资者关系活动记录表")

    def test_generic_fallback_for_broad_survey_keyword(self):
        assert cv.visit_kind_label("机构调研情况登记表") == cv._VISIT_KIND_DEFAULT

    def test_empty_title_falls_back(self):
        assert cv.visit_kind_label("") == cv._VISIT_KIND_DEFAULT

    def test_specific_keyword_wins_over_generic(self):
        # A title carrying both 调研 and a specific family keyword must not
        # fall through to the generic label.
        label = cv.visit_kind_label("特定对象调研接待情况登记表")
        assert label == ("site visit", "特定对象调研")


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


# --------------------------------------------------------------------------- #
# P1-R1 same-cycle derivation — collectors.china_filings.LAST_RUN_OUTCOME
# --------------------------------------------------------------------------- #

class TestLastRunOutcomeFlag:
    """Unit coverage of the process-local outcome flag itself (collectors/
    china_filings.py). The end-to-end same-cycle consumption is proven by
    TestSameCycleDerivation below via a real scripts.collect.main() run."""

    def test_none_before_any_fetch_in_this_process(self):
        assert cf.LAST_RUN_OUTCOME is None

    def test_set_fail_closed_then_ok_on_clean_fetch(self, monkeypatch):
        """fetch() must FAIL-CLOSED the instant it starts (so an escape reads
        as a failed refresh, never as 'not run'), then land on ok=True after
        a clean two-exchange fetch."""
        seen: list[dict | None] = []

        def _fetch_exchange(self, exchange, date_range, session, collected_at):
            # Capture the fail-closed entry-state before this exchange's own
            # work would run — proves the flag was armed BEFORE fetch()
            # reached any per-exchange logic.
            seen.append(dict(cf.LAST_RUN_OUTCOME) if cf.LAST_RUN_OUTCOME else None)
            return []

        monkeypatch.setattr(cf.ChinaFilingsAdapter, "_fetch_exchange", _fetch_exchange)
        adapter = cf.ChinaFilingsAdapter()
        adapter.fetch()
        assert seen[0] is not None and seen[0]["ok"] is False   # fail-closed at entry
        assert cf.LAST_RUN_OUTCOME["ok"] is True                # clean run, no errors
        assert cf.LAST_RUN_OUTCOME["errors"] == []

    def test_set_not_ok_when_all_exchanges_fail(self, monkeypatch):
        def _fetch_exchange(self, exchange, date_range, session, collected_at):
            raise IOError("simulated CNInfo outage")
        monkeypatch.setattr(cf.ChinaFilingsAdapter, "_fetch_exchange", _fetch_exchange)
        adapter = cf.ChinaFilingsAdapter()
        with pytest.raises(RuntimeError):
            adapter.fetch()
        assert cf.LAST_RUN_OUTCOME["ok"] is False
        assert len(cf.LAST_RUN_OUTCOME["errors"]) == 2

    def test_set_not_ok_on_partial_exchange_failure_but_keeps_rows(self, monkeypatch):
        def _fetch_exchange(self, exchange, date_range, session, collected_at):
            if exchange == "sse":
                return [_filing_row("P1", "000001", "投资者关系活动记录表",
                                     "2026-08-19T09:00:00+08:00")]
            raise IOError("simulated szse outage")
        monkeypatch.setattr(cf.ChinaFilingsAdapter, "_fetch_exchange", _fetch_exchange)
        adapter = cf.ChinaFilingsAdapter()
        adapter.fetch()   # partial success — must not raise
        assert cf.LAST_RUN_OUTCOME["ok"] is False
        assert any("szse" in e for e in cf.LAST_RUN_OUTCOME["errors"])
        # positive rows are still on disk — a degraded run never discards them
        assert "P1" in set(cf.load_filings()["announcementId"])


# --------------------------------------------------------------------------- #
# P1-R1 same-cycle derivation — end-to-end via scripts.collect.main()
# --------------------------------------------------------------------------- #

_STUB_ROWS: dict[str, list[dict]] = {}
_STUB_FAILS: set[str] = set()


@pytest.fixture(autouse=True)
def _reset_stub_state():
    _STUB_ROWS.clear()
    _STUB_FAILS.clear()
    yield
    _STUB_ROWS.clear()
    _STUB_FAILS.clear()


def _raw_announcement(announcement_id: str, sec_code: str, sec_name: str,
                       title: str, ts_ms: int, adjunct_url: str = "/x.pdf") -> dict:
    """Raw-shaped CNInfo announcement dict — the input _parse_announcement()
    (collectors/china_filings.py) expects, mirroring what _fetch_page() would
    have returned in its 'announcements' list."""
    return {
        "announcementId": announcement_id,
        "secCode": sec_code,
        "secName": sec_name,
        "orgId": f"org-{sec_code}",
        "announcementTitle": title,
        "announcementTime": ts_ms,
        "announcementType": "",
        "adjunctUrl": adjunct_url,
        "adjunctType": "PDF",
    }


def _ts_ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).timestamp() * 1000)


class _StubChinaFilingsAdapter(cf.ChinaFilingsAdapter):
    """Overrides ONLY _fetch_exchange — real fetch() drives everything else:
    per-exchange isolation, real categorize() via cf._parse_announcement(),
    real write_filings(), real LAST_RUN_OUTCOME flag-setting (P1-R1). Per-test
    behavior lives in the module-level _STUB_ROWS/_STUB_FAILS above:
    scripts/collect.py's _run_one() instantiates the registry CLASS with no
    constructor args, so instance-level config can't be threaded through the
    registry — this mirrors the class-attribute-config idiom other collector
    test doubles in this suite use for the same reason."""

    def _fetch_exchange(self, exchange, date_range, session, collected_at):
        if exchange in _STUB_FAILS:
            raise IOError(f"simulated CNInfo failure for exchange={exchange}")
        raw = _STUB_ROWS.get(exchange, [])
        return [cf._parse_announcement(a, exchange, collected_at) for a in raw]


def _run_collect_main(monkeypatch, registry: dict, argv_tail: list[str]) -> int:
    """Drive scripts.collect.main() end to end against a synthetic registry,
    with COLLECT_LANE unset (T1's required precondition — us_scope stays False
    given --only is always set here) and every always-on end-of-collect step
    neutralized (see module docstring: none relate to china_visits, several
    resolve paths off config.ROOT rather than config.data_dir(), and at least
    one does real network I/O)."""
    import scripts.collect as collect_mod

    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.setattr(collect_mod, "all_adapters", lambda: dict(registry))
    monkeypatch.setattr(sys, "argv", ["collect", *argv_tail])

    import collectors.cn_holder_sale_calendar as _chsc
    import engine.news_vector as _nv
    import engine.source_registry as _sr
    import scripts.audit_claim_accountability as _aca
    import scripts.audit_grading_closure as _agc
    import scripts.audit_options_accrual as _aoa
    import scripts.audit_options_entry_coverage as _aoec
    import scripts.backfill_qledger_intel_hub as _bqih
    import scripts.build_operator_exposure_log as _boel
    import scripts.cctv_finalize_watcher as _cfw
    import scripts.grade_qledger as _gq

    monkeypatch.setattr(_nv, "ingest", lambda: None)
    monkeypatch.setattr(_bqih, "run",
                         lambda root, dry_run=False: {"n_registered": 0, "n_blocked": 0,
                                                       "n_rejected": 0})
    monkeypatch.setattr(_gq, "run_as_collect_step", lambda root=None: None)
    monkeypatch.setattr(_cfw, "run_as_collect_step", lambda root=None: None)
    monkeypatch.setattr(_agc, "run_as_collect_step", lambda: None)
    monkeypatch.setattr(_aca, "run_as_collect_step", lambda: None)
    monkeypatch.setattr(_aoa, "run_as_collect_step", lambda: None)
    monkeypatch.setattr(_aoec, "run_as_collect_step", lambda: None)
    monkeypatch.setattr(_boel, "run_as_collect_step", lambda: None)
    monkeypatch.setattr(_chsc, "collect", lambda force=False: pd.DataFrame())
    monkeypatch.setattr(_sr, "run_as_collect_step", lambda data_root=None, root=None: None)

    return collect_mod.main()


class TestSameCycleDerivation:
    """T1 — Sol's required acceptance test. A single collect.main() invocation
    over registry {china_filings, china_visits} must consume THIS run's
    freshly-written china_filings store, not a prior cycle's — proving both
    the same-cycle consumption AND the `--only china_filings,china_visits`
    dependency order (china_filings runs before china_visits within the
    shared cninfo host-group thread)."""

    def test_same_cycle_consumption_via_collect_main(self, monkeypatch):
        _STUB_ROWS["sse"] = [_raw_announcement(
            "V1", "600001", "name-600001", "顺网科技：投资者关系活动记录表",
            _ts_ms("2026-08-20T09:00:00+08:00"))]

        assert not cv._visits_path().exists()

        registry = {"china_filings": _StubChinaFilingsAdapter,
                    "china_visits": cv.ChinaVisitsAdapter}
        rc = _run_collect_main(monkeypatch, registry,
                                ["--only", "china_filings,china_visits", "--skip-quality"])

        assert rc == 0
        assert cv._visits_path().exists()
        df = cv.load_visits()
        assert "V1" in set(df["announcement_id"])
        assert cv.read_health()["status"] == "ok"
        assert cv.read_coverage_start() is not None


class TestUpstreamDegradedEndToEnd:
    """T2/T3 — a same-run china_filings failure (total or partial) must not
    be silently invisible to china_visits: it degrades to 'upstream_degraded'
    and freezes last_success_utc, but NEVER discards positive rows already
    derived this run."""

    def test_total_failure_keeps_prior_last_success_no_coverage(self, monkeypatch):
        # A committed filings store from a PRIOR (unrelated) successful night —
        # no institutional_visit rows in it, so this run's derivation has
        # nothing to add regardless of tonight's outcome. Without this, a
        # first-ever run would hit refresh()'s earlier "store not present yet"
        # branch (-> no_coverage) before ever reaching the same-run-outcome
        # check this test targets.
        cf.write_filings([_filing_row("A0", "000000", "关于回购股份的公告",
                                       "2026-08-18T09:00:00+08:00", category="buyback")])
        # A prior, established health baseline — seeded directly (not via a
        # real refresh()) so coverage.json is deliberately absent, matching
        # "no coverage.json created when none existed" below.
        cv._write_health("ok", "prior baseline run", success=True)
        prior_last_success = cv.read_health()["last_success_utc"]
        assert prior_last_success
        assert cv.read_coverage_start() is None

        _STUB_FAILS.update({"sse", "szse"})

        registry = {"china_filings": _StubChinaFilingsAdapter,
                    "china_visits": cv.ChinaVisitsAdapter}
        _run_collect_main(monkeypatch, registry,
                           ["--only", "china_filings,china_visits", "--skip-quality"])

        health = cv.read_health()
        assert health["status"] == "upstream_degraded"
        assert health["last_success_utc"] == prior_last_success   # frozen, not advanced
        assert cv.read_coverage_start() is None                   # never started on a failed run
        assert cv.load_visits().empty                             # no candidates this run

    def test_partial_failure_keeps_positive_rows_but_still_degrades(self, monkeypatch):
        cv._write_health("ok", "prior baseline run", success=True)
        prior_last_success = cv.read_health()["last_success_utc"]

        _STUB_ROWS["sse"] = [_raw_announcement(
            "V3", "600003", "name-600003", "某公司特定对象调研纪要",
            _ts_ms("2026-08-20T10:00:00+08:00"))]
        _STUB_FAILS.add("szse")

        registry = {"china_filings": _StubChinaFilingsAdapter,
                    "china_visits": cv.ChinaVisitsAdapter}
        _run_collect_main(monkeypatch, registry,
                           ["--only", "china_filings,china_visits", "--skip-quality"])

        # positive evidence: the row IS in visits.parquet
        assert "V3" in set(cv.load_visits()["announcement_id"])
        health = cv.read_health()
        assert health["status"] == "upstream_degraded"
        assert health["last_success_utc"] == prior_last_success   # not advanced


class TestSameCycleIdempotency:
    """T4 — running the same same-cycle invocation twice must not duplicate
    rows (keep-FIRST dedup on announcement_id, both at the china_filings and
    china_visits layers)."""

    def test_second_run_is_idempotent(self, monkeypatch):
        _STUB_ROWS["sse"] = [_raw_announcement(
            "V4", "600004", "name-600004", "顺网科技：投资者关系活动记录表",
            _ts_ms("2026-08-20T09:00:00+08:00"))]

        registry = {"china_filings": _StubChinaFilingsAdapter,
                    "china_visits": cv.ChinaVisitsAdapter}
        argv_tail = ["--only", "china_filings,china_visits", "--skip-quality"]
        _run_collect_main(monkeypatch, registry, argv_tail)
        n1 = len(cv.load_visits())
        _run_collect_main(monkeypatch, registry, argv_tail)
        n2 = len(cv.load_visits())

        assert n1 == 1
        assert n2 == n1


class TestOnlyChinaVisitsCommittedStorePath:
    """T5 — `--only china_visits` (proof/debug runs, LOCAL backfills) must
    NEVER attempt a china_filings fetch: china_filings did not run in this
    process, collectors.china_filings.LAST_RUN_OUTCOME stays None, and
    china_visits derives cleanly over whatever store is already committed."""

    def test_only_china_visits_never_fetches_and_derives_ok(self, monkeypatch):
        cf.write_filings([_filing_row("A9", "000009", "特定对象调研接待情况登记表",
                                       "2026-08-19T09:00:00+08:00")])

        def _boom(*a, **kw):
            raise AssertionError("network attempted")
        import requests
        monkeypatch.setattr(requests.sessions.Session, "request", _boom)

        registry = {"china_filings": cf.ChinaFilingsAdapter,
                    "china_visits": cv.ChinaVisitsAdapter}
        _run_collect_main(monkeypatch, registry, ["--only", "china_visits", "--skip-quality"])

        assert cf.LAST_RUN_OUTCOME is None   # china_filings never ran in this process
        assert "A9" in set(cv.load_visits()["announcement_id"])
        assert cv.read_health()["status"] == "ok"


# --------------------------------------------------------------------------- #
# T6 — registry order + concurrent-host-group membership (LOAD-BEARING)
# --------------------------------------------------------------------------- #

class TestRegistryOrderAndConcurrentMembership:
    """P1-R1's same-cycle contract depends on TWO facts about scripts/collect.py
    holding simultaneously: china_filings, china_visits, and china_irm all sit
    in the same 'cninfo' concurrent host-group (so they run in ONE thread,
    serially, never touching the akshare-unsafe serial C0 lane), AND the
    registry lists them in that exact order (china_filings -> china_visits ->
    china_irm), because concurrent_keys/groups preserve registry insertion
    order. Either fact breaking silently reintroduces the one-cycle latency
    this PR removes."""

    def test_registry_order_and_concurrent_membership(self):
        import scripts.collect as collect_mod

        assert collect_mod._CONCURRENT_HOSTS["china_filings"] == "cninfo"
        assert collect_mod._CONCURRENT_HOSTS["china_visits"] == "cninfo"
        assert collect_mod._CONCURRENT_HOSTS["china_irm"] == "cninfo"

        registry = collect_mod.all_adapters()
        keys = list(registry)
        assert keys.index("china_filings") < keys.index("china_visits") < keys.index("china_irm")

        serial_keys = [k for k in registry if k not in collect_mod._CONCURRENT_HOSTS]
        assert "china_filings" not in serial_keys
        assert "china_visits" not in serial_keys
        assert "china_irm" not in serial_keys


# --------------------------------------------------------------------------- #
# T7 — engine.china_intel_hub._visit_block: upstream_degraded handling
# --------------------------------------------------------------------------- #

class TestVisitBlockUpstreamDegraded:
    """health.status == 'upstream_degraded' must read like a stale refusal
    (never a clean 'measured_no_event', and never routed through the
    'source_failure' branch — tape history stays visible) when no rows exist
    for a name; rows present must still render normally either way, since a
    degraded upstream never discards positive evidence."""

    def _ctx(self, by_code):
        return {
            "by_code": by_code,
            "coverage_start": "2026-08-01",
            "health": {"status": "upstream_degraded",
                       "detail": "derived over a DEGRADED same-run china_filings refresh",
                       "last_success_utc": None},
        }

    def test_no_rows_reads_stale_never_measured_no_event_or_source_failure(self):
        from engine.china_intel_hub import _visit_block
        block = _visit_block("000001.SZ", self._ctx(by_code={}))
        assert block["state"] == "stale"
        assert block["state"] != "measured_no_event"
        assert block["state"] != "source_failure"

    def test_rows_present_render_normally_even_when_degraded(self):
        from engine.china_intel_hub import _visit_block
        row = {
            "sec_code": "000001", "title": "投资者关系活动记录表",
            "source_published_at": "2026-08-19T09:00:00+08:00",
            "visitor_raw": "not_yet_available", "visitor_class": "not_yet_available",
            "ontology_version": cv.ONTOLOGY_VERSION, "adjunct_url": "",
            "kind_en": "IR activity record", "kind_zh": "投资者关系活动记录表",
        }
        block = _visit_block("000001.SZ", self._ctx(by_code={"000001": [row]}))
        assert block["state"] == "ok"
        assert len(block["recent"]) == 1
        assert block["recent"][0]["title"] == "投资者关系活动记录表"
