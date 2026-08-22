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
    """collectors.china_filings.LAST_RUN_OUTCOME and LAST_KEY_INTEGRITY are
    process-local, module-global state (P1-R1 same-cycle derivation contract
    / P1-R2 key-integrity contract) — reset BOTH around every test so no
    test inherits another's outcome flag. monkeypatch.setattr does NOT
    restore a module global the code ASSIGNS to (only attributes it
    patched), so a test in THIS file that calls cf.write_filings(...)
    directly (many do — they seed china_filings' store to drive china_
    visits' derivation) leaves cf.LAST_KEY_INTEGRITY dirty for whichever
    test runs next, in THIS file or any other file collected after it in
    the same process (correction, 2026-08-22 — LAST_KEY_INTEGRITY was
    previously left out of this fixture's reset, unlike tests/
    test_china_filings_collector.py's own equivalent fixture, which resets
    both)."""
    cf.LAST_RUN_OUTCOME = None
    cf.LAST_KEY_INTEGRITY = None
    yield
    cf.LAST_RUN_OUTCOME = None
    cf.LAST_KEY_INTEGRITY = None


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
        # -1, NOT 0: a REFUSAL is a distinct signal from "0 net-new, wrote
        # fine" (correction, 2026-08-22) — refresh() must be able to tell
        # them apart rather than certifying the plane healthy on a write it
        # never actually performed.
        assert n == -1
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


# --------------------------------------------------------------------------- #
# P1-R2 (2026-08-22, DSC:CHINA-VISITS-UNTYPED-ANNOUNCEMENT-ID-DROP) —
# account_candidates: the pure accounting function that replaced the bare
# comprehension `[_derive_row(f, ts) for f in candidates if f.get(...)]`.
# --------------------------------------------------------------------------- #

class TestAccountCandidates:
    def test_valid_plus_missing_id_candidate(self):
        candidates = [
            _filing_row("A1", "000001", "投资者关系活动记录表", "2026-08-19T09:00:00+08:00"),
            {**_filing_row("A2", "000002", "特定对象调研纪要", "2026-08-19T10:00:00+08:00"),
             "announcementId": None},
        ]
        acc = cv.account_candidates(candidates, "2026-08-20T00:00:00+00:00", cf.key_anomaly)
        assert acc["eligible"] == 2
        assert acc["represented"] == 1
        assert acc["typed_exclusions"] == 1
        assert acc["exclusions_by_type"] == {"missing": 1}
        assert acc["rows"][0]["announcement_id"] == "A1"

    def test_multiple_missing_ids_prove_no_silent_collapse(self):
        """At least 3 malformed candidates in one batch — typed_exclusions
        must report 3, never 1."""
        candidates = [
            {**_filing_row(f"B{i}", f"00000{i}", "机构调研情况登记表",
                            "2026-08-19T09:00:00+08:00"), "announcementId": ""}
            for i in range(3)
        ]
        acc = cv.account_candidates(candidates, "2026-08-20T00:00:00+00:00", cf.key_anomaly)
        assert acc["represented"] == 0
        assert acc["typed_exclusions"] == 3
        assert acc["exclusions_by_type"] == {"empty": 3}

    def test_none_id_excluded(self):
        candidates = [{**_filing_row("C1", "000001", "t", "2026-08-19T09:00:00+08:00"),
                        "announcementId": None}]
        acc = cv.account_candidates(candidates, "2026-08-20T00:00:00+00:00", cf.key_anomaly)
        assert acc["typed_exclusions"] == 1
        assert acc["exclusions_by_type"] == {"missing": 1}

    def test_empty_string_id_excluded(self):
        candidates = [{**_filing_row("C2", "000001", "t", "2026-08-19T09:00:00+08:00"),
                        "announcementId": ""}]
        acc = cv.account_candidates(candidates, "2026-08-20T00:00:00+00:00", cf.key_anomaly)
        assert acc["exclusions_by_type"] == {"empty": 1}

    def test_whitespace_ids_excluded(self):
        candidates = [
            {**_filing_row("C3", "000001", "t", "2026-08-19T09:00:00+08:00"),
             "announcementId": " "},
            {**_filing_row("C4", "000002", "t", "2026-08-19T09:00:00+08:00"),
             "announcementId": "\t"},
            {**_filing_row("C5", "000003", "t", "2026-08-19T09:00:00+08:00"),
             "announcementId": "　"},
        ]
        acc = cv.account_candidates(candidates, "2026-08-20T00:00:00+00:00", cf.key_anomaly)
        assert acc["exclusions_by_type"] == {"whitespace": 3}

    def test_nan_ids_excluded(self):
        candidates = [
            {**_filing_row("C6", "000001", "t", "2026-08-19T09:00:00+08:00"),
             "announcementId": float("nan")},
            {**_filing_row("C7", "000002", "t", "2026-08-19T09:00:00+08:00"),
             "announcementId": pd.NA},
            {**_filing_row("C8", "000003", "t", "2026-08-19T09:00:00+08:00"),
             "announcementId": pd.NaT},
        ]
        acc = cv.account_candidates(candidates, "2026-08-20T00:00:00+00:00", cf.key_anomaly)
        assert acc["exclusions_by_type"] == {"nan": 3}

    def test_valid_rows_preserved_beside_malformed_ones(self):
        candidates = [
            _filing_row("D1", "000001", "投资者关系活动记录表", "2026-08-19T09:00:00+08:00"),
            {**_filing_row("D2", "000002", "t", "2026-08-19T09:00:00+08:00"),
             "announcementId": ""},
            _filing_row("D3", "000003", "特定对象调研纪要", "2026-08-19T10:00:00+08:00"),
        ]
        acc = cv.account_candidates(candidates, "2026-08-20T00:00:00+00:00", cf.key_anomaly)
        assert acc["represented"] == 2
        assert {r["announcement_id"] for r in acc["rows"]} == {"D1", "D3"}

    def test_identity_recovery_string_format(self):
        candidates = [{**_filing_row("E1", "600001", "顺网科技：投资者关系活动记录表",
                                      "2026-08-19T09:00:00+08:00"),
                       "announcementId": None}]
        acc = cv.account_candidates(candidates, "2026-08-20T00:00:00+00:00", cf.key_anomaly)
        assert acc["excluded_identities"] == [
            "600001|2026-08-19T09:00:00+08:00|顺网科技：投资者关系活动记录表"
        ]

    def test_identity_list_capped_at_five(self):
        candidates = [
            {**_filing_row(f"F{i}", f"00000{i}", "t", "2026-08-19T09:00:00+08:00"),
             "announcementId": ""}
            for i in range(8)
        ]
        acc = cv.account_candidates(candidates, "2026-08-20T00:00:00+00:00", cf.key_anomaly)
        assert acc["typed_exclusions"] == 8
        assert len(acc["excluded_identities"]) == 5

    def test_pure_no_io(self):
        candidates = [_filing_row("G1", "000001", "t", "2026-08-19T09:00:00+08:00")]
        cv.account_candidates(candidates, "2026-08-20T00:00:00+00:00", cf.key_anomaly)


# --------------------------------------------------------------------------- #
# P1-R2 — refresh(): mechanical identity check, typed exclusion end to end
# --------------------------------------------------------------------------- #

class TestRefreshKeyIntegrity:
    def test_valid_plus_missing_candidate_typed_excluded(self):
        cf.write_filings([_filing_row("H1", "000001", "投资者关系活动记录表",
                                       "2026-08-19T09:00:00+08:00")])
        # Seed a pre-existing malformed row DIRECTLY into the accrued filings
        # store (bypassing write_filings' own exclusion) so china_visits must
        # independently exclude it — proving the visits-side guard does not
        # merely rely on the filings-side guard never letting one through.
        existing = cf.load_filings()
        bad = _filing_row("H2", "000002", "特定对象调研纪要", "2026-08-19T10:00:00+08:00")
        bad["announcementId"] = None
        seed = pd.concat([existing, pd.DataFrame([bad])], ignore_index=True)
        seed.to_parquet(cf._store_path(), index=False)

        s = cv.refresh()
        # P1-R3: a typed exclusion ALONE no longer degrades the run (D1
        # reversal) — it becomes a durable, company-scoped coverage
        # exception instead. See TestCoverageExceptionsP1R3 for the ledger
        # assertions.
        assert s["status"] == "ok"
        assert s["n_represented"] == 1
        assert s["n_excluded"] == 1
        # The anomaly this plane OBSERVES from the committed store is "nan",
        # never "missing". The conversion happens at pd.DataFrame CONSTRUCTION,
        # NOT at the parquet round-trip: the key column is a pandas string
        # dtype whose NA sentinel is nan, so a raw None is already nan before
        # anything is written, and the round-trip is a no-op (pre-write and
        # post-read values are identical — independently verified 2026-08-22
        # after an earlier version of this comment blamed pyarrow). Consequence
        # worth keeping in view: "missing" is unreachable at every
        # frame-mediated boundary and can only fire on the raw-dict new_rows
        # path, which is exactly what makes _parse_announcement's None default
        # load-bearing there and nowhere else. A genuinely absent key never
        # reaches the accrued store anyway, because write_filings() already
        # excludes it — this is the SAME exclusion, independently proven at
        # THIS boundary instead.
        assert s["exclusions"] == {"nan": 1}
        assert "H1" in set(cv.load_visits()["announcement_id"])
        assert "H2" not in set(cv.load_visits()["announcement_id"])

    def test_multiple_missing_ids_counted_not_collapsed(self):
        """The counter (n_excluded / exclusions) must report 3, never 1."""
        existing = cf.load_filings()
        bad_rows = []
        for i in range(3):
            r = _filing_row(f"J{i}", f"00000{i}", "机构调研情况登记表",
                             "2026-08-19T09:00:00+08:00")
            r["announcementId"] = ""
            bad_rows.append(r)
        seed = pd.concat([existing, pd.DataFrame(bad_rows)], ignore_index=True)
        seed.to_parquet(cf._store_path(), index=False)

        s = cv.refresh()
        assert s["n_excluded"] == 3
        assert s["exclusions"] == {"empty": 3}
        assert cv.load_visits().empty   # zero well-keyed candidates this run

    def _seed_one_malformed(self, announcement_id):
        """A single malformed candidate row, WITH a valid sibling row in the
        same write — a lone all-null column lets pyarrow round-trip the
        Python sentinel type-preserved (None survives as None), which is not
        representative of a real accrued store where the column is object-
        dtype-with-strings; a sibling forces the realistic, empirically
        stable round-trip (verified: None/nan/pd.NA/pd.NaT all normalize to
        float NaN when a real string shares the column)."""
        sib = _filing_row("K0", "000099", "投资者关系活动记录表", "2026-08-18T09:00:00+08:00")
        r = _filing_row("K1", "000001", "投资者关系活动记录表", "2026-08-19T09:00:00+08:00")
        r["announcementId"] = announcement_id
        pd.DataFrame([sib, r]).reindex(columns=list(cf._COLUMNS)).to_parquet(
            cf._store_path(), index=False
        )

    def test_none_candidate_excluded(self):
        self._seed_one_malformed(None)
        s = cv.refresh()
        assert s["n_excluded"] == 1
        # See _seed_one_malformed's docstring: a committed-store round-trip
        # normalizes a raw None to "nan", not "missing" — both are typed
        # exclusions; "missing" itself is unit-covered pre-storage by
        # TestAccountCandidates.test_none_id_excluded and
        # tests/test_china_filings_collector.py::TestKeyAnomaly.
        assert s["exclusions"] == {"nan": 1}
        # only the valid sibling (K0) survives; K1 (malformed) excluded
        assert set(cv.load_visits()["announcement_id"]) == {"K0"}

    def test_empty_string_candidate_excluded(self):
        self._seed_one_malformed("")
        s = cv.refresh()
        assert s["exclusions"] == {"empty": 1}
        assert set(cv.load_visits()["announcement_id"]) == {"K0"}

    def test_whitespace_candidates_excluded(self):
        for bad in (" ", "\t", "　"):
            self._seed_one_malformed(bad)
            s = cv.refresh()
            assert s["exclusions"] == {"whitespace": 1}, bad
            assert set(cv.load_visits()["announcement_id"]) == {"K0"}

    def test_nan_candidates_excluded(self):
        for bad in (float("nan"), pd.NA, pd.NaT):
            self._seed_one_malformed(bad)
            s = cv.refresh()
            assert s["n_excluded"] == 1, bad
            assert s["exclusions"] == {"nan": 1}, bad
            assert set(cv.load_visits()["announcement_id"]) == {"K0"}

    def test_valid_rows_preserved_beside_malformed_ones_same_run(self):
        """The good visit row IS written to visits.parquet in the SAME run
        that harvests the malformed one as a coverage exception (P1-R3: a
        typed exclusion alone no longer degrades the run — D1 reversal)."""
        good = _filing_row("L1", "000001", "投资者关系活动记录表", "2026-08-19T09:00:00+08:00")
        bad = _filing_row("L2", "000002", "特定对象调研纪要", "2026-08-19T10:00:00+08:00")
        bad["announcementId"] = ""
        pd.DataFrame([good, bad]).reindex(columns=list(cf._COLUMNS)).to_parquet(
            cf._store_path(), index=False
        )
        s = cv.refresh()
        assert s["status"] == "ok"
        assert "L1" in set(cv.load_visits()["announcement_id"])
        assert "L2" not in set(cv.load_visits()["announcement_id"])
        exc = cv.load_coverage_exceptions()
        assert len(exc) == 1
        assert exc.iloc[0]["status"] == "open"
        assert exc.iloc[0]["sec_code"] == "000002"

    def test_lane_survives_and_health_goes_loud(self, capsys):
        """refresh() returns without raising; the exclusion is still LOUD
        (a line-start GitHub annotation fires) even though P1-R3 no longer
        degrades the run's overall health for a typed exclusion alone —
        the loud signal and the health status are now independent."""
        self._seed_one_malformed(None)
        s = cv.refresh()   # must not raise
        assert s["status"] == "ok"
        assert cv.read_health()["status"] == "ok"
        out = capsys.readouterr().out
        lines = [ln for ln in out.splitlines() if ln.startswith("::")]
        assert lines, f"no line-start GitHub annotation found: {out!r}"
        assert "china-visits-malformed-announcement-id" in lines[0]

    def test_health_carries_candidate_accounting_on_ok_path(self):
        """P1-R2 §C.7: a CLEAN run's own health.json also carries the
        arithmetic — auditable from the collector's own receipts. P1-R3
        additionally nests a zero-state coverage_exceptions receipt."""
        cf.write_filings([_filing_row("M1", "000001", "投资者关系活动记录表",
                                       "2026-08-19T09:00:00+08:00")])
        s = cv.refresh()
        assert s["status"] == "ok"
        acc = cv.read_health()["candidate_accounting"]
        assert acc == {
            "eligible": 1, "represented_downstream": 1,
            "typed_exclusions": 0, "exclusions_by_type": {},
            "coverage_exceptions": {
                "open": 0, "open_scoped": 0, "open_unscoped": 0,
                "new_this_run": 0, "reaffirmed_this_run": 0,
                "resolved_this_run": 0, "readable": True,
            },
        }

    def test_health_carries_candidate_accounting_with_a_typed_exclusion(self):
        """P1-R3: a typed exclusion no longer degrades the run (D1
        reversal), but health.json's candidate_accounting still reports the
        arithmetic AND the new coverage_exceptions receipt shows the fresh
        open, company-scoped exception it minted."""
        self._seed_one_malformed("")   # K0 (valid) + K1 (malformed) — see helper docstring
        s = cv.refresh()
        assert s["status"] == "ok"
        acc = cv.read_health()["candidate_accounting"]
        assert acc == {
            "eligible": 2, "represented_downstream": 1,
            "typed_exclusions": 1, "exclusions_by_type": {"empty": 1},
            "coverage_exceptions": {
                "open": 1, "open_scoped": 1, "open_unscoped": 0,
                "new_this_run": 1, "reaffirmed_this_run": 0,
                "resolved_this_run": 0, "readable": True,
            },
        }


# --------------------------------------------------------------------------- #
# P1-R2 — measured absence cannot advance under typed exclusions
# --------------------------------------------------------------------------- #

class TestMeasuredAbsenceCanAdvanceUnderATypedExclusion:
    """P1-R2's test class name was TestMeasuredAbsenceCannotAdvance and
    asserted the OPPOSITE of what P1-R3 now requires — that was exactly D1
    (frozen spec §0): a single pre-existing/typed unkeyed row froze
    last_success_utc and left coverage_start unstamped FOREVER (or, if it
    landed before the first success, the plane never started at all). P1-R3
    reverses this: a typed exclusion, taken ALONE, must no longer be a
    global cause of upstream_degraded — it becomes a durable, company-scoped
    coverage exception instead (engine/china_intel_hub.py's _visit_block()
    suppresses measured_no_event for just that company)."""

    def test_D1_regression_first_run_with_malformed_row_still_starts_coverage(self):
        """The WORST case named in the frozen spec §0: a malformed row lands
        BEFORE the plane's first-ever successful run. Under #6229 this
        latched no_coverage forever — coverage_start never stamped, the
        plane never started at all. Under P1-R3 the run is 'ok',
        coverage_start stamps, and the malformed observation becomes an
        open, company-scoped exception instead."""
        assert cv.read_coverage_start() is None

        r = _filing_row("N1", "000001", "投资者关系活动记录表", "2026-08-19T09:00:00+08:00")
        r["announcementId"] = None
        pd.DataFrame([r]).reindex(columns=list(cf._COLUMNS)).to_parquet(
            cf._store_path(), index=False
        )
        s = cv.refresh()
        assert s["status"] == "ok"
        assert cv.read_health()["last_success_utc"] is not None
        assert cv.read_coverage_start() is not None   # the plane STARTS

        exc = cv.load_coverage_exceptions()
        assert len(exc) == 1
        assert exc.iloc[0]["status"] == "open"
        assert exc.iloc[0]["sec_code"] == "000001"

    def test_D1_regression_does_not_freeze_an_already_running_plane(self):
        """The second half of the #6229 latch: a malformed row arriving on
        an ALREADY-COVERED plane must not freeze last_success_utc either —
        every LATER run must not stay upstream_degraded forever just
        because typed_exclusions >= 1 fired once."""
        cv._write_health("ok", "prior baseline run", success=True)
        prior_last_success = cv.read_health()["last_success_utc"]
        cv._stamp_coverage_start_once("2026-08-01")
        coverage_before = cv.read_coverage_start()

        r = _filing_row("N2", "000002", "投资者关系活动记录表", "2026-08-19T09:00:00+08:00")
        r["announcementId"] = None
        pd.DataFrame([r]).reindex(columns=list(cf._COLUMNS)).to_parquet(
            cf._store_path(), index=False
        )
        s = cv.refresh()
        assert s["status"] == "ok"
        health = cv.read_health()
        assert health["last_success_utc"] != prior_last_success   # ADVANCES now
        assert cv.read_coverage_start() == coverage_before        # unchanged (already stamped)


# --------------------------------------------------------------------------- #
# P1-R2 §C.1 — collectors.china_filings import failure fails CLOSED
# --------------------------------------------------------------------------- #

class TestImportFailureFailsClosed:
    def test_import_failure_writes_source_failure_never_derives_blind(self, monkeypatch):
        """Pre-P1-R2 this degraded to same_run_outcome=None and proceeded to
        derive over the committed store. Now it must fail CLOSED: this plane
        can no longer verify its own accounting without china_filings'
        key_anomaly predicate.

        refresh() does `from collectors import china_filings as _cf` — a
        narrow, targeted __import__ patch is the only seam available for a
        function-local import statement (collectors.china_filings is already
        cached in sys.modules from this test module's own top-level import,
        so removing the module or the package attribute would not force a
        re-import failure)."""
        cf.write_filings([_filing_row("O1", "000001", "投资者关系活动记录表",
                                       "2026-08-19T09:00:00+08:00")])

        import builtins
        real_import = builtins.__import__

        def _fake_dunder_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "collectors" and fromlist and "china_filings" in fromlist:
                raise ImportError("simulated import failure")
            return real_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", _fake_dunder_import)

        s = cv.refresh()
        assert s["status"] == "source_failure"
        assert cv.load_visits().empty   # never derived
        health = cv.read_health()
        assert health["status"] == "source_failure"
        assert "import failed" in health["detail"]
        assert cv.read_coverage_start() is None


# --------------------------------------------------------------------------- #
# P1-R2 §C.6 — cause composition: both same-run-degraded AND typed exclusions
# --------------------------------------------------------------------------- #

class TestCauseComposition:
    def test_both_causes_named_in_one_record(self):
        """P1-R3 §9: typed key exclusions are NO LONGER a GLOBAL cause —
        the two causes that CAN still compose are a same-run china_filings
        TRANSPORT degradation and an unreadable coverage-exception ledger."""
        cf.LAST_RUN_OUTCOME = {
            "ok": False, "errors": ["sse: simulated outage"],
            "per_exchange": {}, "at": "t0",
            "key_integrity": {"excluded_total": 0, "excluded_by_type": {},
                               "preexisting_unkeyed": 0, "excluded_rows": [], "at": "t0"},
            "transport_ok": False, "key_integrity_known": True,
        }
        cf.write_filings([_filing_row("P1", "000001", "投资者关系活动记录表",
                                       "2026-08-19T09:00:00+08:00")])
        # Corrupt the coverage-exception ledger directly (present-but-
        # unreadable, the second global cause).
        cv._exceptions_path().write_bytes(b"not a parquet file")

        s = cv.refresh()
        assert s["status"] == "upstream_degraded"
        detail = cv.read_health()["detail"]
        assert "TRANSPORT degradation" in detail
        assert "coverage-exception ledger is present but unreadable" in detail


# --------------------------------------------------------------------------- #
# P1-R2 §11b — MUTATION GUARD: under-reporting account_candidates refuses ok
# --------------------------------------------------------------------------- #

class TestAccountingMutationGuard:
    def test_underreporting_account_candidates_refuses_clean_write(self, monkeypatch):
        """MUTATION GUARD: if account_candidates under-reported (represented
        + typed_exclusions < eligible), refresh() must refuse a clean 'ok',
        write 'source_failure' instead, and store NOTHING — trusting an
        accounting that doesn't add up is exactly the failure mode this
        mechanical identity check exists to catch."""
        cf.write_filings([_filing_row("Q1", "000001", "投资者关系活动记录表",
                                       "2026-08-19T09:00:00+08:00")])

        def _underreport(candidates, system_recorded_at, key_anomaly):
            return {"eligible": len(candidates), "rows": [], "represented": 0,
                    "typed_exclusions": 0, "exclusions_by_type": {},
                    "excluded_identities": []}
        monkeypatch.setattr(cv, "account_candidates", _underreport)

        s = cv.refresh()
        assert s["status"] == "source_failure"
        assert cv.read_health()["status"] == "source_failure"
        assert cv.load_visits().empty


# --------------------------------------------------------------------------- #
# T7 extension — P1-R2: hub state under a same-run typed-exclusion degrade
# --------------------------------------------------------------------------- #

class TestVisitBlockScopedExceptionP1R3(TestVisitBlockUpstreamDegraded):
    """Extends TestVisitBlockUpstreamDegraded (T7, same-run TRANSPORT
    degradation — unaffected by P1-R3 and still valid). Adds the P1-R3 end-
    to-end scenario (frozen spec §12 hostile items 1+2): a typed key
    exclusion for ONE company must suppress measured_no_event ONLY for that
    company (state 'not_yet_available', frozen spec §10) while an unrelated,
    genuinely clean company in the SAME run still reads 'measured_no_event'
    — proven end to end via a real refresh(), not just a synthetic ctx dict.
    This SUPERSEDES the P1-R2 test of the same shape
    (test_typed_exclusion_degrade_reads_stale_end_to_end), which asserted
    the OLD, now-reversed D1 behavior (freeze + 'stale' for every name)."""

    def test_scoped_exception_blocks_only_the_affected_company_end_to_end(self):
        from engine.china_intel_hub import _load_visits_context, _visit_block

        # Establish coverage_start via a genuine clean run FIRST — the hub's
        # _visit_block() checks `if not coverage_start: return "no_coverage"`
        # before it ever looks at health.status, so a realistic read
        # requires a real prior successful run, not just a hand-written
        # health.json (real-world: P1 has been live for days before a
        # malformed key ever shows up).
        cf.write_filings([_filing_row("R0", "000000", "投资者关系活动记录表",
                                       "2026-08-18T09:00:00+08:00")])
        s0 = cv.refresh()
        assert s0["status"] == "ok"
        prior_last_success = cv.read_health()["last_success_utc"]
        coverage_start_before = cv.read_coverage_start()
        assert coverage_start_before is not None

        # Append a malformed candidate for Company A (999999) to the accrued
        # store (not replace) — representative of a real accrued multi-row
        # store.
        existing = cf.load_filings()
        bad = _filing_row("R1", "999999", "投资者关系活动记录表", "2026-08-19T09:00:00+08:00")
        bad["announcementId"] = ""
        seed = pd.concat([existing, pd.DataFrame([bad])], ignore_index=True)
        seed.to_parquet(cf._store_path(), index=False)

        s = cv.refresh()
        # P1-R3 (D1 reversal): the run is 'ok' — a typed exclusion ALONE no
        # longer freezes the plane.
        assert s["status"] == "ok"
        assert cv.read_health()["last_success_utc"] != prior_last_success   # ADVANCES
        assert cv.read_coverage_start() == coverage_start_before             # unchanged

        ctx = _load_visits_context()

        # Hostile item 1: Company A (999999, the excluded company) — its own
        # absence cannot be confirmed.
        block_a = _visit_block("999999.SZ", ctx)
        assert block_a["state"] == "not_yet_available"
        assert block_a["state"] != "measured_no_event"
        assert block_a.get("coverage_exception", {}).get("scope") == "company"

        # Hostile item 2: Company B (000001, uninvolved, no rows, genuinely
        # clean in the SAME run) — CAN still produce measured_no_event.
        block_b = _visit_block("000001.SZ", ctx)
        assert block_b["state"] == "measured_no_event"


# --------------------------------------------------------------------------- #
# P1-R3 (durable scoped key-exclusion recovery, frozen spec) — pure-function
# coverage: fingerprint law (§4), upsert law (§7), reconciliation (§6).
# --------------------------------------------------------------------------- #

def _obs_row(**overrides) -> dict:
    """A raw china_filings-shaped row dict, as consumed by
    observation_fingerprint()/_exception_fields()/reconcile_exceptions()."""
    base = {
        "exchange": "szse", "sec_code": "000001", "org_id": "org1",
        "title": "投资者关系活动记录表", "publish_ts": "2026-08-19T09:00:00+08:00",
        "announcement_type_raw": "", "adjunct_url": "/x.pdf", "adjunct_type": "PDF",
        "category": "institutional_visit",
    }
    base.update(overrides)
    return base


class TestFingerprintLaw:
    def test_version_prefix(self):
        fp = cv.observation_fingerprint(_obs_row())
        assert fp.startswith("obsfp1:")

    def test_deterministic(self):
        r = _obs_row()
        assert cv.observation_fingerprint(r) == cv.observation_fingerprint(dict(r))

    def test_announcement_id_excluded_from_fingerprint(self):
        r1 = {**_obs_row(), "announcementId": "A1"}
        r2 = {**_obs_row(), "announcementId": "A2"}
        assert cv.observation_fingerprint(r1) == cv.observation_fingerprint(r2)

    def test_collected_at_excluded_from_fingerprint(self):
        r1 = {**_obs_row(), "_collected_at": "t1"}
        r2 = {**_obs_row(), "_collected_at": "t2"}
        assert cv.observation_fingerprint(r1) == cv.observation_fingerprint(r2)

    def test_sec_name_excluded_from_fingerprint(self):
        """sec_name is mutable (ST/rename) — excluding it means a rename
        must not break dedup across the SAME underlying observation."""
        r1 = {**_obs_row(), "sec_name": "旧名"}
        r2 = {**_obs_row(), "sec_name": "*ST新名"}
        assert cv.observation_fingerprint(r1) == cv.observation_fingerprint(r2)

    def test_kind_excluded_from_fingerprint(self):
        r1 = {**_obs_row(), "kind": "letter"}
        r2 = {**_obs_row(), "kind": None}
        assert cv.observation_fingerprint(r1) == cv.observation_fingerprint(r2)

    def test_title_change_produces_a_different_fingerprint(self):
        r1 = _obs_row(title="A")
        r2 = _obs_row(title="B")
        assert cv.observation_fingerprint(r1) != cv.observation_fingerprint(r2)

    def test_sec_code_change_produces_a_different_fingerprint(self):
        r1 = _obs_row(sec_code="000001")
        r2 = _obs_row(sec_code="000002")
        assert cv.observation_fingerprint(r1) != cv.observation_fingerprint(r2)

    def test_never_raises_on_hostile_input(self):
        for bad in (
            {}, {"exchange": float("nan")}, {"sec_code": pd.NA},
            {"title": pd.NaT}, {"org_id": ["not", "a", "scalar"]},
        ):
            cv.observation_fingerprint(bad)   # must not raise

    def test_two_distinct_unfingerprintable_rows_never_collide(self):
        """Mutation-guard shape for the believed-unreachable except branch:
        even if _fp_norm() somehow raised for two DIFFERENT rows, the
        fallback path must not fold them onto one shared sentinel fingerprint
        — that would silently merge two distinct observations into one
        ledger row, the exact drop_duplicates collapse this program exists
        to prevent, one level up."""
        import collectors.china_visits as _cv_mod

        def _raising_fp_norm(v):
            raise RuntimeError("simulated _fp_norm failure")

        orig = _cv_mod._fp_norm
        _cv_mod._fp_norm = _raising_fp_norm
        try:
            fp1 = cv.observation_fingerprint(_obs_row(title="row one"))
            fp2 = cv.observation_fingerprint(_obs_row(title="row two"))
            assert fp1 != fp2
        finally:
            _cv_mod._fp_norm = orig


class TestIsObservationFingerprint:
    def test_true_for_a_real_fingerprint_value(self):
        fp = cv.observation_fingerprint(_obs_row())
        assert cv.is_observation_fingerprint(fp) is True

    def test_false_for_a_real_cninfo_announcement_id(self):
        assert cv.is_observation_fingerprint("1223456789") is False

    def test_false_for_none(self):
        assert cv.is_observation_fingerprint(None) is False

    def test_false_for_non_string(self):
        assert cv.is_observation_fingerprint(12345) is False
        assert cv.is_observation_fingerprint(float("nan")) is False


class TestIsUnscopedSecCode:
    def test_empty_string_is_unscoped(self):
        assert cv.is_unscoped_sec_code("") is True

    def test_none_is_unscoped(self):
        assert cv.is_unscoped_sec_code(None) is True

    def test_nan_is_unscoped(self):
        assert cv.is_unscoped_sec_code(float("nan")) is True

    def test_nat_is_unscoped(self):
        assert cv.is_unscoped_sec_code(pd.NaT) is True

    def test_pd_na_is_unscoped_and_never_raises(self):
        assert cv.is_unscoped_sec_code(pd.NA) is True

    def test_literal_nan_derived_strings_are_unscoped(self):
        """Defense-in-depth against a pre-fix `x or ""` idiom (NaN is
        TRUTHY in Python) or a hand-written/legacy ledger row."""
        for literal in ("nan", "NaN", "NaT", "None", "<NA>"):
            assert cv.is_unscoped_sec_code(literal) is True, literal

    def test_real_code_is_scoped(self):
        assert cv.is_unscoped_sec_code("000001") is False


class TestExceptionFieldsNaNRobustness:
    """Correction (2026-08-22): `x or ""` does not handle NaN — NaN is
    TRUTHY in Python, so str(float('nan') or "").strip() yields the literal
    3-char string 'nan' and pd.NA or "" raises TypeError outright.
    _exception_fields() must normalize every string field with _fp_norm()."""

    def test_nan_sec_code_normalizes_to_empty_not_literal_nan(self):
        row = _obs_row(sec_code=float("nan"))
        fields = cv._exception_fields(row, "visits_candidate", cf.key_anomaly)
        assert fields["sec_code"] == ""
        assert fields["sec_code"] != "nan"

    def test_nat_sec_code_normalizes_to_empty(self):
        row = _obs_row(sec_code=pd.NaT)
        fields = cv._exception_fields(row, "visits_candidate", cf.key_anomaly)
        assert fields["sec_code"] == ""

    def test_pd_na_sec_code_never_raises(self):
        row = _obs_row(sec_code=pd.NA)
        fields = cv._exception_fields(row, "visits_candidate", cf.key_anomaly)  # must not raise
        assert fields["sec_code"] == ""

    def test_nan_title_and_sec_name_persist_as_empty_not_literal_nan(self):
        row = _obs_row(title=float("nan"), sec_name=float("nan"))
        fields = cv._exception_fields(row, "visits_candidate", cf.key_anomaly)
        assert fields["title"] == ""
        assert fields["sec_name"] == ""

    def test_nan_org_id_exchange_and_adjunct_fields_persist_as_empty(self):
        row = _obs_row(org_id=float("nan"), exchange=pd.NaT,
                        adjunct_url=float("nan"), adjunct_type=pd.NA,
                        announcement_type_raw=float("nan"), category=float("nan"))
        fields = cv._exception_fields(row, "visits_candidate", cf.key_anomaly)
        for key in ("org_id", "exchange", "adjunct_url", "adjunct_type",
                    "announcement_type_raw", "category"):
            assert fields[key] == "", key


class TestUpsertExceptions:
    def _obs(self, fp="obsfp1:" + "a" * 64, sec_code="000001"):
        return {
            "observation_fingerprint": fp, "fingerprint_version": "obsfp1",
            "sec_code": sec_code, "sec_name": "n", "org_id": "o",
            "exchange": "szse", "title": "t", "source_published_at": "ts",
            "announcement_type_raw": "", "adjunct_url": "", "adjunct_type": "",
            "category": "institutional_visit", "key_anomaly": "empty",
            "origin": "visits_candidate",
        }

    def test_new_fingerprint_inserted_open(self):
        df, n_new, n_reaff = cv.upsert_exceptions(None, [self._obs()], "t0")
        assert n_new == 1 and n_reaff == 0
        assert len(df) == 1
        row = df.iloc[0]
        assert row["status"] == "open"
        assert row["observed_count"] == 1
        assert row["first_seen_utc"] == "t0"
        assert row["last_seen_utc"] == "t0"
        assert row["resolved_announcement_id"] == ""
        assert row["resolved_utc"] == ""

    def test_reaffirm_existing_fingerprint(self):
        df1, _, _ = cv.upsert_exceptions(None, [self._obs()], "t0")
        df2, n_new, n_reaff = cv.upsert_exceptions(df1, [self._obs()], "t1")
        assert n_new == 0 and n_reaff == 1
        assert len(df2) == 1
        row = df2.iloc[0]
        assert row["observed_count"] == 2
        assert row["first_seen_utc"] == "t0"   # NEVER rewritten
        assert row["last_seen_utc"] == "t1"    # reaffirmed

    def test_hostile_item6_repeated_re_pulls_never_mint_n_rows(self):
        """Frozen spec §12 item 6: 5 re-pulls of the SAME malformed
        observation -> ONE durable exception, observed_count incrementing."""
        df = None
        for i in range(5):
            df, _, _ = cv.upsert_exceptions(df, [self._obs()], f"t{i}")
        assert len(df) == 1
        assert df.iloc[0]["observed_count"] == 5

    def test_reaffirm_resolved_fingerprint_does_not_reopen(self):
        df1, _, _ = cv.upsert_exceptions(None, [self._obs()], "t0")
        records = df1.to_dict("records")
        records[0]["status"] = "resolved"
        records[0]["resolved_announcement_id"] = "REAL1"
        records[0]["resolved_utc"] = "t1"
        resolved_df = pd.DataFrame(records)
        df2, n_new, n_reaff = cv.upsert_exceptions(resolved_df, [self._obs()], "t2")
        assert n_new == 0 and n_reaff == 1
        row = df2.iloc[0]
        assert row["status"] == "resolved"            # NOT reopened
        assert row["resolved_announcement_id"] == "REAL1"
        assert row["observed_count"] == 2

    def test_intra_batch_duplicate_fingerprints_count_as_one_insert_one_reaffirm(self):
        df, n_new, n_reaff = cv.upsert_exceptions(None, [self._obs(), self._obs()], "t0")
        assert n_new == 1 and n_reaff == 1
        assert len(df) == 1
        assert df.iloc[0]["observed_count"] == 2

    def test_distinct_fingerprints_produce_distinct_rows(self):
        df, n_new, n_reaff = cv.upsert_exceptions(
            None, [self._obs(fp="obsfp1:" + "a" * 64), self._obs(fp="obsfp1:" + "b" * 64)], "t0"
        )
        assert n_new == 2 and n_reaff == 0
        assert len(df) == 2

    def test_pure_no_io(self):
        cv.upsert_exceptions(None, [self._obs()], "t0")   # no filesystem access


class TestReconcileExceptions:
    def _exc_df(self, fp="obsfp1:" + "a" * 64, sec_code="000001", status="open"):
        rec = {
            "observation_fingerprint": fp, "fingerprint_version": "obsfp1",
            "sec_code": sec_code, "sec_name": "n", "org_id": "o",
            "exchange": "szse", "title": "t", "source_published_at": "ts",
            "announcement_type_raw": "", "adjunct_url": "", "adjunct_type": "",
            "category": "institutional_visit", "key_anomaly": "empty",
            "origin": "visits_candidate", "first_seen_utc": "t0", "last_seen_utc": "t0",
            "observed_count": 1, "status": status, "resolved_announcement_id": "",
            "resolved_utc": "",
        }
        return pd.DataFrame([rec])

    def _candidate(self, ann_id, **overrides):
        base = {"announcementId": ann_id, "exchange": "szse", "sec_code": "000001",
                "org_id": "o", "title": "t", "publish_ts": "ts",
                "announcement_type_raw": "", "adjunct_url": "", "adjunct_type": "",
                "category": "institutional_visit"}
        base.update(overrides)
        return base

    def test_hostile_item7_exact_single_match_resolves_with_the_real_id(self):
        cand = self._candidate("REAL1")
        fp = cv.observation_fingerprint(cand)
        df = self._exc_df(fp=fp)
        result, n_resolved = cv.reconcile_exceptions(df, [cand], "t1")
        assert n_resolved == 1
        row = result.iloc[0]
        assert row["status"] == "resolved"
        assert row["resolved_announcement_id"] == "REAL1"
        assert row["resolved_utc"] == "t1"

    def test_hostile_item8_ambiguous_two_different_ids_stays_open(self):
        cand_a = self._candidate("REAL1")
        cand_b = self._candidate("REAL2")
        fp = cv.observation_fingerprint(cand_a)
        assert fp == cv.observation_fingerprint(cand_b)   # same fingerprint fields
        df = self._exc_df(fp=fp)
        result, n_resolved = cv.reconcile_exceptions(df, [cand_a, cand_b], "t1")
        assert n_resolved == 0
        assert result.iloc[0]["status"] == "open"
        assert result.iloc[0]["resolved_announcement_id"] == ""

    def test_hostile_item8_non_exact_match_never_fuzzy_resolves(self):
        fp = cv.observation_fingerprint(self._candidate("REAL1"))
        df = self._exc_df(fp=fp)
        different = self._candidate("REAL9", title="a slightly different title")
        result, n_resolved = cv.reconcile_exceptions(df, [different], "t1")
        assert n_resolved == 0
        assert result.iloc[0]["status"] == "open"

    def test_zero_matches_stays_open(self):
        df = self._exc_df(fp="obsfp1:" + "c" * 64)
        result, n_resolved = cv.reconcile_exceptions(df, [self._candidate("REAL1")], "t1")
        assert n_resolved == 0
        assert result.iloc[0]["status"] == "open"

    def test_fix_duplicate_rows_with_the_same_real_announcement_id_still_resolves(self):
        """FIX (2026-08-22, second correction): the SAME real announcementId
        appearing TWICE among well_keyed_candidates (a duplicate row in the
        accrued store, a pre-dedup historical row) is ONE canonical match,
        not two plausible ones. Counting ROWS instead of DISTINCT ids would
        classify this as ambiguous and leave it open FOREVER — a permanent,
        unexitable per-company suppression with no in-code exit, exactly
        the D1 failure mode this whole wave exists to remove, reintroduced
        one layer down."""
        cand = self._candidate("REAL1")
        fp = cv.observation_fingerprint(cand)
        df = self._exc_df(fp=fp)
        result, n_resolved = cv.reconcile_exceptions(df, [cand, dict(cand)], "t1")
        assert n_resolved == 1
        assert result.iloc[0]["status"] == "resolved"
        assert result.iloc[0]["resolved_announcement_id"] == "REAL1"

    def test_resolved_rows_are_kept_forever_never_rewritten_away(self):
        df = self._exc_df(status="resolved")
        result, n_resolved = cv.reconcile_exceptions(df, [], "t1")
        assert n_resolved == 0
        assert len(result) == 1
        assert result.iloc[0]["status"] == "resolved"   # untouched, kept

    def test_candidate_with_null_announcement_id_is_skipped_not_fabricated(self):
        """FIX: a malformed candidate leaking into well_keyed_candidates
        (should never happen per the caller contract, but this function is
        public/pure and defensive) must never mint a fake 'None'/'nan' id —
        that would be a SYNTHETIC canonical identity, forbidden outright."""
        cand_null = self._candidate(None)
        fp = cv.observation_fingerprint(cand_null)
        df = self._exc_df(fp=fp)
        result, n_resolved = cv.reconcile_exceptions(df, [cand_null], "t1")
        assert n_resolved == 0
        assert result.iloc[0]["status"] == "open"
        assert result.iloc[0]["resolved_announcement_id"] == ""

    def test_empty_exceptions_df_short_circuits(self):
        empty = pd.DataFrame(columns=list(cv._EXCEPTION_COLUMNS))
        result, n_resolved = cv.reconcile_exceptions(empty, [self._candidate("REAL1")], "t1")
        assert n_resolved == 0
        assert result.empty


# --------------------------------------------------------------------------- #
# P1-R3 — refresh()-level end-to-end coverage: hostile items 3/4/5(+D2)/6/10,
# the cost guard, and the write_visits() mutation guard (item 12).
# --------------------------------------------------------------------------- #

class TestP1RelevanceFilterEndToEnd:
    def test_hostile_item3_malformed_non_visit_filing_does_not_mint_exception(self, monkeypatch):
        """A malformed row OUTSIDE institutional_visit with a REAL (non-
        blank) title must not globally poison P1: no exception minted, the
        plane stays 'ok'. Exercised via a REAL same-cycle china_filings ->
        china_visits run — account_candidates() already narrows to
        category=='institutional_visit' before it ever sees a candidate, so
        origin='visits_candidate' can never exercise this branch; only
        origin='filings_boundary' (which spans every category) can."""
        _STUB_ROWS["sse"] = [
            _raw_announcement("", "000002", "name-000002", "关于回购股份的公告",
                               _ts_ms("2026-08-19T10:00:00+08:00")),
            _raw_announcement("Q1", "000001", "name-000001", "投资者关系活动记录表",
                               _ts_ms("2026-08-19T09:00:00+08:00")),
        ]
        registry = {"china_filings": _StubChinaFilingsAdapter,
                    "china_visits": cv.ChinaVisitsAdapter}
        rc = _run_collect_main(monkeypatch, registry,
                                ["--only", "china_filings,china_visits", "--skip-quality"])
        assert rc == 0
        assert cv.read_health()["status"] == "ok"
        assert cv.load_coverage_exceptions().empty   # no exception minted


class TestUnscopedExceptionEndToEnd:
    def test_hostile_item4_no_usable_company_identifier_blocks_globally(self, monkeypatch):
        _STUB_ROWS["sse"] = [
            _raw_announcement("", "", "", "特定对象调研纪要",
                               _ts_ms("2026-08-19T10:00:00+08:00")),
        ]
        # An established coverage baseline first.
        cf.write_filings([_filing_row("R0", "000000", "投资者关系活动记录表",
                                       "2026-08-18T09:00:00+08:00")])
        s0 = cv.refresh()
        assert s0["status"] == "ok"

        registry = {"china_filings": _StubChinaFilingsAdapter,
                    "china_visits": cv.ChinaVisitsAdapter}
        rc = _run_collect_main(monkeypatch, registry,
                                ["--only", "china_filings,china_visits", "--skip-quality"])
        assert rc == 0
        assert cv.read_health()["status"] == "ok"

        exc = cv.load_coverage_exceptions()
        assert len(exc) == 1
        assert exc.iloc[0]["sec_code"] == ""
        assert exc.iloc[0]["status"] == "open"

        from engine.china_intel_hub import _load_visits_context, _visit_block
        ctx = _load_visits_context()
        assert ctx["unscoped_exceptions"] == 1
        # An UNINVOLVED company with NO rows at all (000000/R0 has a real
        # row from the baseline seed, so it would render 'ok' with a
        # coverage_exception attached — the no-rows branch is what proves
        # the GLOBAL, plane-wide block) reads not_yet_available.
        block = _visit_block("999999.SZ", ctx)
        assert block["state"] == "not_yet_available"
        assert block["state"] != "measured_no_event"
        assert block["coverage_exception"]["scope"] == "plane"

        # The company WITH rows still renders them — positive evidence is
        # never hidden — but also carries the plane-wide coverage_exception,
        # since completeness cannot be asserted while ANY exclusion's
        # company is unknown.
        block_with_rows = _visit_block("000000.SZ", ctx)
        assert block_with_rows["state"] == "ok"
        assert len(block_with_rows["recent"]) == 1
        assert block_with_rows["coverage_exception"]["scope"] == "plane"


class TestExceptionDurabilityAcrossCleanRuns:
    def test_hostile_item5_and_D2_regression_exception_survives_aging_out(self, monkeypatch):
        """Hostile item 5 / D2 regression (frozen spec §0): once minted, an
        exception must NOT require re-observation to stay open. Night 1
        mints it (the observation is freshly excluded); nights 2-5 NEVER
        re-observe it (simulating the observation aging out of china_
        filings' 3-day re-pull window) but the exception must REMAIN open
        and continue to block Company A — exactly the durable memory #6229
        lacked."""
        _STUB_ROWS["sse"] = [
            _raw_announcement("", "555555", "name-555555", "特定对象调研纪要",
                               _ts_ms("2026-08-19T10:00:00+08:00")),
        ]
        registry = {"china_filings": _StubChinaFilingsAdapter,
                    "china_visits": cv.ChinaVisitsAdapter}
        rc = _run_collect_main(monkeypatch, registry,
                                ["--only", "china_filings,china_visits", "--skip-quality"])
        assert rc == 0
        exc = cv.load_coverage_exceptions()
        assert len(exc) == 1
        assert exc.iloc[0]["sec_code"] == "555555"
        assert exc.iloc[0]["observed_count"] == 1

        # Nights 2-5: the observation NEVER reappears.
        _STUB_ROWS.clear()
        for _ in range(4):
            rc = _run_collect_main(monkeypatch, registry,
                                    ["--only", "china_filings,china_visits", "--skip-quality"])
            assert rc == 0
            assert cv.read_health()["status"] == "ok"

        exc_after = cv.load_coverage_exceptions()
        assert len(exc_after) == 1
        assert exc_after.iloc[0]["status"] == "open"
        assert exc_after.iloc[0]["observed_count"] == 1   # never reaffirmed again

        from engine.china_intel_hub import _load_visits_context, _visit_block
        ctx = _load_visits_context()
        block = _visit_block("555555.SZ", ctx)
        assert block["state"] == "not_yet_available"
        assert block["state"] != "measured_no_event"   # the FALSE clean D2 describes

    def test_hostile_item6_repeated_reaffirm_via_visits_candidate_origin(self):
        """Item 6 via origin='visits_candidate': the SAME persisted
        malformed row is re-observed every night from the accrued filings
        store — must reaffirm ONE ledger row, never mint N."""
        sib = _filing_row("K0", "000099", "投资者关系活动记录表", "2026-08-18T09:00:00+08:00")
        bad = _filing_row("K1", "000001", "投资者关系活动记录表", "2026-08-19T09:00:00+08:00")
        bad["announcementId"] = ""
        pd.DataFrame([sib, bad]).reindex(columns=list(cf._COLUMNS)).to_parquet(
            cf._store_path(), index=False
        )
        for _ in range(3):
            s = cv.refresh()
            assert s["status"] == "ok"
        exc = cv.load_coverage_exceptions()
        assert len(exc) == 1
        assert exc.iloc[0]["observed_count"] == 3


class TestReconciliationResolvesOnAWellKeyedFiling:
    def test_hostile_item7_end_to_end_resolution_via_refresh(self):
        """A malformed observation is excluded tonight; a LATER night's
        well-keyed filing sharing the same fingerprint fields resolves it
        end to end through refresh() (not just the pure reconcile_
        exceptions() unit)."""
        # Night 1: malformed, minted.
        bad = _filing_row("X1", "000001", "投资者关系活动记录表", "2026-08-19T09:00:00+08:00")
        bad["announcementId"] = ""
        pd.DataFrame([bad]).reindex(columns=list(cf._COLUMNS)).to_parquet(
            cf._store_path(), index=False
        )
        s1 = cv.refresh()
        assert s1["status"] == "ok"
        exc1 = cv.load_coverage_exceptions()
        assert len(exc1) == 1
        assert exc1.iloc[0]["status"] == "open"

        # Night 2: the SAME observation, now with a real announcementId,
        # replaces the malformed row in the accrued store (representative
        # of CNInfo re-serving the same content correctly).
        good = _filing_row("REAL777", "000001", "投资者关系活动记录表",
                            "2026-08-19T09:00:00+08:00")
        pd.DataFrame([good]).reindex(columns=list(cf._COLUMNS)).to_parquet(
            cf._store_path(), index=False
        )
        s2 = cv.refresh()
        assert s2["status"] == "ok"
        exc2 = cv.load_coverage_exceptions()
        assert len(exc2) == 1
        assert exc2.iloc[0]["status"] == "resolved"
        assert exc2.iloc[0]["resolved_announcement_id"] == "REAL777"

        from engine.china_intel_hub import _load_visits_context, _visit_block
        ctx = _load_visits_context()
        # A resolved exception no longer suppresses this company — positive
        # rows are present, so the state reads 'ok', not 'not_yet_available'.
        block = _visit_block("000001.SZ", ctx)
        assert block["state"] == "ok"
        assert "coverage_exception" not in block


class TestLedgerUnreadableEndToEnd:
    def test_hostile_item10_present_but_unreadable_ledger_fails_closed(self):
        """The ledger is corrupted (present but unreadable): refresh()
        ABORTS the ledger write (never overwritten), still writes
        visits.parquet (positive evidence is real), and degrades to
        'upstream_degraded'. The hub then blocks measured_no_event for
        EVERY name via exceptions_readable=False."""
        # A genuine prior successful run FIRST — _visit_block() checks
        # `if not coverage_start: return "no_coverage"` before it ever
        # reaches the exception logic, so a real "not_yet_available" read
        # requires coverage to have already started (real-world: P1 runs
        # for days before a ledger ever corrupts).
        cf.write_filings([_filing_row("Y0", "000000", "投资者关系活动记录表",
                                       "2026-08-18T09:00:00+08:00")])
        s0 = cv.refresh()
        assert s0["status"] == "ok"
        coverage_start_before = cv.read_coverage_start()
        assert coverage_start_before is not None

        good = _filing_row("Y1", "000001", "投资者关系活动记录表", "2026-08-19T09:00:00+08:00")
        existing = cf.load_filings()
        seed = pd.concat([existing, pd.DataFrame([good])], ignore_index=True)
        seed.to_parquet(cf._store_path(), index=False)
        cv._exceptions_path().write_bytes(b"not a parquet file")
        before = cv._exceptions_path().read_bytes()

        s = cv.refresh()
        assert s["status"] == "upstream_degraded"
        detail = cv.read_health()["detail"]
        assert "coverage-exception ledger is present but unreadable" in detail
        # positive evidence is STILL written
        assert "Y1" in set(cv.load_visits()["announcement_id"])
        # the corrupt ledger is left BYTE-IDENTICAL — never overwritten
        assert cv._exceptions_path().read_bytes() == before
        assert cv.read_coverage_start() == coverage_start_before   # unchanged

        from engine.china_intel_hub import _load_visits_context, _visit_block
        ctx = _load_visits_context()
        assert ctx["exceptions_readable"] is False
        # An uninvolved, otherwise-clean ticker with no rows still cannot
        # confirm absence. FIX (correction, 2026-08-22): the scoped/unscoped
        # coverage-exception branch is evaluated BEFORE the generic
        # upstream_degraded branch (it is strictly more specific, and
        # "upstream was degraded" would be FALSE ON THE FACTS here — only a
        # sidecar ledger was unreadable, transport was fine) — so this reads
        # 'not_yet_available', scope 'plane', never the generic 'stale'.
        block = _visit_block("999999.SZ", ctx)
        assert block["state"] == "not_yet_available"
        assert block["state"] != "measured_no_event"
        assert block["state"] != "stale"
        assert block["coverage_exception"]["scope"] == "plane"


class TestCostGuardSkipsReconciliationOnEmptyLedger:
    def test_reconcile_exceptions_not_called_when_zero_open_exceptions(self, monkeypatch):
        """The COST GUARD (frozen spec §6): reconciliation must be SKIPPED
        entirely — never even called — when there are zero open exceptions,
        the normal case forever. Proven by making reconcile_exceptions()
        raise if invoked: a clean run with no exclusions at all must not
        touch it."""
        def _boom(*a, **kw):
            raise AssertionError("reconcile_exceptions() must not be called "
                                  "when there are zero open exceptions")
        monkeypatch.setattr(cv, "reconcile_exceptions", _boom)

        cf.write_filings([_filing_row("Z1", "000001", "投资者关系活动记录表",
                                       "2026-08-19T09:00:00+08:00")])
        s = cv.refresh()   # must not raise
        assert s["status"] == "ok"


class TestWriteVisitsFirewallMutationGuard:
    def test_hostile_item12_fingerprint_as_announcement_id_is_refused(self, capsys):
        """MUTATION GUARD: making the observation fingerprint become
        announcement_id (or any canonical identity) is KILLED — write_visits
        refuses the WHOLE append, the store is left untouched, and a
        line-start ::error annotation fires."""
        fp = cv.observation_fingerprint(_obs_row())
        good = cv._derive_row(_filing_row("W1", "000001", "投资者关系活动记录表",
                                           "2026-08-19T09:00:00+08:00"),
                               "2026-08-20T00:00:00+00:00")
        poisoned = dict(good)
        poisoned["announcement_id"] = fp   # the mutation this guard KILLS

        n = cv.write_visits([good, poisoned])
        assert n == -1   # REFUSED, distinct from "0 net-new, wrote fine"
        assert cv.load_visits().empty   # store left UNTOUCHED — not even the good row
        out = capsys.readouterr().out
        lines = [ln for ln in out.splitlines() if ln.startswith("::")]
        assert lines, f"no line-start GitHub annotation found: {out!r}"
        assert lines[0].startswith("::error")
        assert "china-visits-fingerprint-identity-breach" in lines[0]

    def test_a_real_announcement_id_is_never_refused(self):
        """Real CNInfo ids are numeric strings — the firewall must never
        false-positive on normal operation."""
        good = cv._derive_row(_filing_row("REAL999", "000001", "投资者关系活动记录表",
                                           "2026-08-19T09:00:00+08:00"),
                               "2026-08-20T00:00:00+00:00")
        n = cv.write_visits([good])
        assert n == 1
        assert "REAL999" in set(cv.load_visits()["announcement_id"])


class TestWriteVisitsRefusalDegradesHealthEndToEnd:
    """FIX (correction, 2026-08-22): write_visits() returning -1 (REFUSED)
    for the unreadable-store ABORT or the canonical-identity firewall must
    be VISIBLE to refresh()'s health instrument — never fall through to a
    clean 'ok' that stamps coverage_start / advances last_success_utc over
    a store the run knowingly refused to write. Proven end to end through
    a real refresh() call, not just the write_visits() unit above."""

    def test_fingerprint_breach_end_to_end_degrades_health_and_freezes_coverage(self):
        poison_id = cv.observation_fingerprint({
            "exchange": "szse", "sec_code": "000001", "org_id": "o", "title": "t",
            "publish_ts": "ts", "announcement_type_raw": "", "adjunct_url": "",
            "adjunct_type": "", "category": "institutional_visit",
        })
        row = _filing_row(poison_id, "000001", "投资者关系活动记录表",
                           "2026-08-19T09:00:00+08:00")
        pd.DataFrame([row]).reindex(columns=list(cf._COLUMNS)).to_parquet(
            cf._store_path(), index=False
        )
        assert cv.read_coverage_start() is None

        s = cv.refresh()
        assert s["status"] == "upstream_degraded"
        assert s["n_new"] == 0   # the -1 sentinel never leaks into the count
        health = cv.read_health()
        assert health["status"] == "upstream_degraded"
        assert "REFUSED" in health["detail"]
        assert cv.read_coverage_start() is None   # never stamped
        assert cv.load_visits().empty              # store left untouched

    def test_unreadable_visits_store_end_to_end_degrades_health_and_freezes_coverage(self):
        good = _filing_row("V1", "000001", "投资者关系活动记录表", "2026-08-19T09:00:00+08:00")
        pd.DataFrame([good]).reindex(columns=list(cf._COLUMNS)).to_parquet(
            cf._store_path(), index=False
        )
        cv._visits_path().write_bytes(b"not a parquet file")   # present-but-unreadable
        assert cv.read_coverage_start() is None

        s = cv.refresh()
        assert s["status"] == "upstream_degraded"
        assert s["n_new"] == 0
        health = cv.read_health()
        assert health["status"] == "upstream_degraded"
        assert "REFUSED" in health["detail"]
        assert cv.read_coverage_start() is None
        assert cv._visits_path().read_bytes() == b"not a parquet file"   # untouched

    def test_refusal_freezes_last_success_utc_on_an_already_running_plane(self):
        cv._write_health("ok", "prior baseline run", success=True)
        prior_last_success = cv.read_health()["last_success_utc"]

        good = _filing_row("V2", "000001", "投资者关系活动记录表", "2026-08-19T09:00:00+08:00")
        pd.DataFrame([good]).reindex(columns=list(cf._COLUMNS)).to_parquet(
            cf._store_path(), index=False
        )
        cv._visits_path().write_bytes(b"not a parquet file")

        s = cv.refresh()
        assert s["status"] == "upstream_degraded"
        assert cv.read_health()["last_success_utc"] == prior_last_success   # frozen
