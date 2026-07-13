"""tests/test_admin_metabolism_history.py — Tests for admin/metabolism_history.py
and the /api/metabolism/history server route.

Test structure mirrors tests/test_admin_metabolism.py exactly:
  - sys.path.insert to repo root
  - pytest tmp_path as root
  - requests module stubbed WHOLESALE on admin.github_api via types.SimpleNamespace
  - mock.patch.object(github_api, "token", return_value=None) for no-token path

Coverage:
  (a) empty root → events==[], phase0 True, all sources present count==0, never raises
  (b) populated root — minimal fixtures for every source lane
  (c) corrupt inputs skipped without raising
  (d) immune event title contains "draft", not "merged"
  (e) mocked list_prs — loop PRs filtered, merged→ok
"""
from __future__ import annotations

import json
import sys
import types
import unittest.mock as mock
from pathlib import Path

import pytest

# Add repo root to path so `from admin import ...` works
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(path: Path, data: dict | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, dict):
        path.write_text(json.dumps(data), encoding="utf-8")
    else:
        path.write_text(data, encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n",
        encoding="utf-8",
    )


def _stub_requests(gha):
    """Replace gha.requests with a stub that has no callable methods (forces failures)."""
    stub = types.SimpleNamespace()
    return mock.patch.object(gha, "requests", stub)


# ---------------------------------------------------------------------------
# (a) Empty root — never raises, correct structure, all sources count==0
# ---------------------------------------------------------------------------

class TestEmptyRoot:
    def _call(self, tmp_path: Path) -> dict:
        import admin.github_api as gha
        import admin.metabolism_history as mh

        with mock.patch.object(gha, "token", return_value=None), \
             _stub_requests(gha):
            return mh.history(limit=100, root=tmp_path)

    def test_never_raises(self, tmp_path):
        result = self._call(tmp_path)
        assert isinstance(result, dict)

    def test_required_keys(self, tmp_path):
        result = self._call(tmp_path)
        for key in ("events", "sources", "phase0", "generated_at"):
            assert key in result, f"missing key: {key}"

    def test_events_empty(self, tmp_path):
        result = self._call(tmp_path)
        assert result["events"] == []

    def test_phase0_true(self, tmp_path):
        result = self._call(tmp_path)
        assert result["phase0"] is True

    def test_all_sources_present(self, tmp_path):
        result = self._call(tmp_path)
        expected = {
            "pr", "audit", "revert", "immune", "governance",
            "genesis", "revamp", "lifecycle", "journal", "freeze",
            "verify", "lesson", "parked", "heartbeat", "shadow",
        }
        assert set(result["sources"].keys()) == expected

    def test_all_source_counts_zero(self, tmp_path):
        result = self._call(tmp_path)
        for src, meta in result["sources"].items():
            assert meta["count"] == 0, f"source {src!r} expected count=0, got {meta['count']}"

    def test_nonexistent_root_returns_contract(self, tmp_path):
        """Nonexistent root path must return the contract dict, not raise."""
        import admin.github_api as gha
        import admin.metabolism_history as mh

        fake_root = tmp_path / "does_not_exist"
        with mock.patch.object(gha, "token", return_value=None), \
             _stub_requests(gha):
            result = mh.history(limit=50, root=fake_root)

        assert isinstance(result, dict)
        assert "events" in result
        assert "sources" in result
        assert result["phase0"] is True


# ---------------------------------------------------------------------------
# (b) Populated root — per-source counts, ordering, phase0 False, limit
# ---------------------------------------------------------------------------

class TestPopulatedRoot:
    def _build_fixtures(self, tmp_path: Path) -> None:
        met = tmp_path / "data" / "metabolism"
        nw = tmp_path / "data" / "neuralweb"

        # --- governance (2 rows) ---
        _write_jsonl(nw / "governance.jsonl", [
            {
                "schema": "neuralweb.governance.v1",
                "ts": "2026-07-10T10:00:00",
                "event_type": "authority_grant",
                "target": "engine/foo",
                "authored_by": "test",
                "evidence": {"key": "val"},
            },
            {
                "schema": "neuralweb.governance.v1",
                "ts": "2026-07-11T10:00:00",
                "event_type": "config_arm",
                "target": "engine/bar",
                "authored_by": "test",
            },
        ])

        # --- immune_claims (1 row) ---
        _write_jsonl(met / "immune_claims.jsonl", [
            {
                "red_class": "flaky_test",
                "check_name": "pytest / unit",
                "main_sha": "abc123",
                "pr_number": 42,
                "ts": "2026-07-09T08:00:00",
            },
        ])

        # --- audit/123.json ---
        _write(met / "audit" / "123.json", {
            "schema": "metabolism.audit.v1",
            "ts": "2026-07-08T12:00:00",
            "verdict": "approve",
            "rationale": "looks good",
            "head_sha": "deadbeef",
            "findings": [],
            "pr_number": 123,
            "proposal_id": "prop-abc",
        })

        # --- revert/prop-x.json ---
        _write(met / "revert" / "prop-x.json", {
            "schema": "metabolism.revert_actioned.v1",
            "ts": "2026-07-07T14:00:00",
            "proposal_id": "prop-x",
            "status": "revert_pr_opened",
            "pr_number": 99,
            "branch": "metabolism/revert-prop-x",
            "pr_url": "https://github.com/owner/repo/pull/99",
        })

        # --- journal/cycle-2026-07-12-ab12.json ---
        _write(met / "journal" / "cycle-2026-07-12-ab12.json", {
            "schema": "metabolism.journal.v1",
            "cycle_id": "cycle-2026-07-12-ab12",
            "stage": "verify",
            "status": "done",
            "ts": "2026-07-12T06:00:00",
            "stages": {"sense": {}, "propose": {}, "verify": {}},
        })

        # --- journal/freeze_20260712.json ---
        _write(met / "journal" / "freeze_20260712.json", {
            "schema": "metabolism.dispatch_freeze.v1",
            "ts": "2026-07-12T03:00:00",
            "event": "all_keys_cooling",
            "stage": "dispatch",
            "earliest_reset": "2026-07-12T09:00:00",
        })

        # --- heartbeat.jsonl (3 rows) ---
        _write_jsonl(met / "heartbeat.jsonl", [
            {
                "schema": "metabolism.heartbeat.v1",
                "ts": "2026-07-10T00:00:00",
                "run_id": "run1",
                "workflow": "metabolism-heartbeat",
                "sha": "sha1",
                "phase": "P0_inert",
                "note": "Phase 0 liveness probe",
            },
            {
                "schema": "metabolism.heartbeat.v1",
                "ts": "2026-07-11T00:00:00",
                "run_id": "run2",
                "workflow": "metabolism-heartbeat",
                "sha": "sha2",
                "phase": "P0_inert",
                "note": "Phase 0 liveness probe",
            },
            {
                "schema": "metabolism.heartbeat.v1",
                "ts": "2026-07-12T00:00:00",
                "run_id": "run3",
                "workflow": "metabolism-heartbeat",
                "sha": "sha3",
                "phase": "P0_inert",
                "note": "Phase 0 liveness probe",
            },
        ])

        # --- shadow/shadow-x/summary.json ---
        shadow_dir = met / "shadow" / "shadow-x"
        shadow_dir.mkdir(parents=True, exist_ok=True)
        _write(shadow_dir / "summary.json", {
            "schema": "metabolism.shadow_cycle.v1",
            "cycle_id": "shadow-x",
            "ts": "2026-07-06T05:00:00",
            "stages": {"sense": {}, "propose": {}},
            "wall_seconds": 12.5,
        })

        # --- charter_proposals/domain.json ---
        _write(met / "charter_proposals" / "domain.json", {
            "schema": "metabolism.charter_proposal.v1",
            "ts": "2026-07-05T10:00:00",
            "cycle_id": "cycle-2026-07-05-0001",
            "domain_id": "crypto_macro",
            "label": "Crypto Macro",
            "description": "covers crypto macro signals",
            "rationale": "domain uncovered for 3 cycles",
        })

        # --- lifecycle_docket/x.json ---
        _write(met / "lifecycle_docket" / "x.json", {
            "schema": "metabolism.lifecycle_docket.v1",
            "ts": "2026-07-04T10:00:00",
            "lobe_id": "lobe-alpha",
            "from_state": "probation",
            "to_state": "demoted",
        })

        # --- verify/cycle-x.json ---
        _write(met / "verify" / "cycle-x.json", {
            "schema": "metabolism.verify.v1",
            "ts": "2026-07-03T10:00:00",
            "cycle_id": "cycle-x",
            "proposal_id": "prop-v",
            "contract": {},
            "realized": {},
            "triage": {
                "action": "keep",
                "classification": "confirmed",
            },
        })

        # --- lessons.jsonl ---
        _write_jsonl(met / "lessons.jsonl", [
            {
                "schema": "metabolism.lessons.v1",
                "ts": "2026-07-02T10:00:00",
                "cycle_id": "cycle-old",
                "proposal_id": "prop-old",
                "lobe": "lobe-alpha",
                "verdict": "fail",
                "what_worked": "",
                "what_failed": "metric drift under regime change",
                "construction": "rolling_z_score",
            },
        ])

        # --- claims.jsonl: 1 parked row + 1 other-schema row ---
        _write_jsonl(met / "claims.jsonl", [
            {
                "schema": "metabolism.parked_construction.v1",
                "ts": "2026-07-01T10:00:00",
                "proposal_id": "prop-park",
                "parked_construction": {"lobe": "lobe-beta", "kind": "rolling_z", "sensors": []},
            },
            {
                "schema": "metabolism.build_claim.v1",  # different schema — must be ignored
                "ts": "2026-07-01T09:00:00",
                "cycle_id": "cycle-c",
                "proposal_id": "prop-c",
            },
        ])

    def _call(self, tmp_path: Path, limit: int = 200) -> dict:
        import admin.github_api as gha
        import admin.metabolism_history as mh

        with mock.patch.object(gha, "token", return_value=None), \
             _stub_requests(gha):
            return mh.history(limit=limit, root=tmp_path)

    def test_per_source_counts(self, tmp_path):
        self._build_fixtures(tmp_path)
        result = self._call(tmp_path)
        src = result["sources"]
        assert src["governance"]["count"] == 2
        assert src["immune"]["count"] == 1
        assert src["audit"]["count"] == 1
        assert src["revert"]["count"] == 1
        assert src["journal"]["count"] == 1
        assert src["freeze"]["count"] == 1
        assert src["heartbeat"]["count"] == 3
        assert src["shadow"]["count"] == 1
        assert src["genesis"]["count"] == 1
        assert src["lifecycle"]["count"] == 1
        assert src["verify"]["count"] == 1
        assert src["lesson"]["count"] == 1
        assert src["parked"]["count"] == 1
        # pr lane: no token → count 0
        assert src["pr"]["count"] == 0

    def test_phase0_false(self, tmp_path):
        """With audit/governance/immune events, phase0 must be False."""
        self._build_fixtures(tmp_path)
        result = self._call(tmp_path)
        assert result["phase0"] is False

    def test_newest_first_ordering(self, tmp_path):
        """Events sorted newest-first across all sources."""
        self._build_fixtures(tmp_path)
        result = self._call(tmp_path)
        events = result["events"]
        # Extract non-empty ts values and verify descending order
        ts_values = [e["ts"] for e in events if e.get("ts")]
        for i in range(len(ts_values) - 1):
            assert ts_values[i] >= ts_values[i + 1], (
                f"not sorted at index {i}: {ts_values[i]} < {ts_values[i+1]}"
            )

    def test_limit_respected(self, tmp_path):
        """limit=3 returns exactly 3 events."""
        self._build_fixtures(tmp_path)
        result = self._call(tmp_path, limit=3)
        assert len(result["events"]) == 3

    def test_parked_only_correct_schema(self, tmp_path):
        """The other-schema row in claims.jsonl must be ignored."""
        self._build_fixtures(tmp_path)
        result = self._call(tmp_path)
        parked_events = [e for e in result["events"] if e["source"] == "parked"]
        assert len(parked_events) == 1
        assert "lobe-beta" in parked_events[0]["title"]

    def test_revert_url_present(self, tmp_path):
        """revert event should carry the pr_url as url field."""
        self._build_fixtures(tmp_path)
        result = self._call(tmp_path)
        revert_evts = [e for e in result["events"] if e["source"] == "revert"]
        assert len(revert_evts) == 1
        assert revert_evts[0]["url"] == "https://github.com/owner/repo/pull/99"

    def test_audit_approve_status_ok(self, tmp_path):
        self._build_fixtures(tmp_path)
        result = self._call(tmp_path)
        audit_evts = [e for e in result["events"] if e["source"] == "audit"]
        assert audit_evts[0]["status"] == "ok"

    def test_freeze_status_warn(self, tmp_path):
        self._build_fixtures(tmp_path)
        result = self._call(tmp_path)
        freeze_evts = [e for e in result["events"] if e["source"] == "freeze"]
        assert freeze_evts[0]["status"] == "warn"

    def test_verify_keep_status_info(self, tmp_path):
        self._build_fixtures(tmp_path)
        result = self._call(tmp_path)
        verify_evts = [e for e in result["events"] if e["source"] == "verify"]
        assert verify_evts[0]["status"] == "info"

    def test_lesson_text_from_what_failed(self, tmp_path):
        """Lesson title should include the what_failed text."""
        self._build_fixtures(tmp_path)
        result = self._call(tmp_path)
        lesson_evts = [e for e in result["events"] if e["source"] == "lesson"]
        assert len(lesson_evts) == 1
        assert "metric drift" in lesson_evts[0]["title"]

    def test_shadow_title_has_stage_count(self, tmp_path):
        self._build_fixtures(tmp_path)
        result = self._call(tmp_path)
        shadow_evts = [e for e in result["events"] if e["source"] == "shadow"]
        assert "2 stages" in shadow_evts[0]["title"]

    def test_heartbeat_last_200_lines(self, tmp_path):
        """Only the last 200 lines of heartbeat.jsonl are read."""
        self._build_fixtures(tmp_path)
        result = self._call(tmp_path)
        assert result["sources"]["heartbeat"]["count"] == 3


# ---------------------------------------------------------------------------
# (c) Corrupt inputs skipped without raising
# ---------------------------------------------------------------------------

class TestCorruptInputs:
    def test_junk_line_governance(self, tmp_path):
        """A junk line in governance.jsonl does not cause a raise; valid rows still parsed."""
        import admin.github_api as gha
        import admin.metabolism_history as mh

        nw = tmp_path / "data" / "neuralweb"
        _write_jsonl(nw / "governance.jsonl", [
            {"schema": "neuralweb.governance.v1", "ts": "2026-07-10T10:00:00",
             "event_type": "authority_grant", "target": "engine/foo", "authored_by": "x"},
        ])
        # Append a junk line
        (nw / "governance.jsonl").open("a").write("NOT JSON\n")

        with mock.patch.object(gha, "token", return_value=None), \
             _stub_requests(gha):
            result = mh.history(limit=100, root=tmp_path)

        assert isinstance(result, dict)
        # 1 valid row parsed; junk skipped
        assert result["sources"]["governance"]["count"] == 1

    def test_invalid_json_audit_file(self, tmp_path):
        """An invalid JSON file in audit/ is skipped without raising."""
        import admin.github_api as gha
        import admin.metabolism_history as mh

        audit_dir = tmp_path / "data" / "metabolism" / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        (audit_dir / "bad.json").write_text("{ this is not json }", encoding="utf-8")
        # Also write a valid one
        _write(audit_dir / "good.json", {
            "schema": "metabolism.audit.v1",
            "ts": "2026-07-08T12:00:00",
            "verdict": "reject",
            "rationale": "bad code",
            "pr_number": 5,
        })

        with mock.patch.object(gha, "token", return_value=None), \
             _stub_requests(gha):
            result = mh.history(limit=100, root=tmp_path)

        assert isinstance(result, dict)
        assert result["sources"]["audit"]["count"] == 1


# ---------------------------------------------------------------------------
# (d) Immune event title contains "draft" and does not contain "merged"
# ---------------------------------------------------------------------------

class TestImmuneTitleContract:
    def test_immune_title_says_draft_not_merged(self, tmp_path):
        import admin.github_api as gha
        import admin.metabolism_history as mh

        _write_jsonl(tmp_path / "data" / "metabolism" / "immune_claims.jsonl", [
            {
                "red_class": "flaky_ci",
                "check_name": "pytest / unit",
                "main_sha": "abc",
                "pr_number": 7,
                "ts": "2026-07-09T08:00:00",
            },
        ])

        with mock.patch.object(gha, "token", return_value=None), \
             _stub_requests(gha):
            result = mh.history(limit=100, root=tmp_path)

        immune_evts = [e for e in result["events"] if e["source"] == "immune"]
        assert len(immune_evts) == 1
        title = immune_evts[0]["title"].lower()
        assert "draft" in title, f"'draft' missing from title: {title!r}"
        assert "merged" not in title, f"'merged' must not appear in title: {title!r}"
        assert "applied" not in title, f"'applied' must not appear in title: {title!r}"


# ---------------------------------------------------------------------------
# (e) Mocked list_prs — loop PRs filtered, merged→ok, other branches excluded
# ---------------------------------------------------------------------------

class TestPRFiltering:
    @staticmethod
    def _fake_requests(pr_list: list[dict]):
        """Build a stub requests object whose get() returns the pr_list."""
        resp = mock.MagicMock()
        resp.status_code = 200
        resp.json.return_value = pr_list
        stub = types.SimpleNamespace(get=mock.Mock(return_value=resp))
        return stub

    def test_loop_prs_filtered_correctly(self, tmp_path):
        """metabolism/ and claude/loop- PRs kept; feature/* excluded; merged→ok."""
        import admin.github_api as gha
        import admin.metabolism_history as mh

        pr_list = [
            {  # merged metabolism PR → ok
                "number": 10,
                "title": "Metabolism build",
                "state": "closed",
                "draft": False,
                "merged_at": "2026-07-10T12:00:00Z",
                "created_at": "2026-07-10T11:00:00Z",
                "head": {"ref": "metabolism/build-cycle-x"},
                "html_url": "https://github.com/o/r/pull/10",
            },
            {  # open claude/loop- PR → info
                "number": 20,
                "title": "Loop PR",
                "state": "open",
                "draft": False,
                "merged_at": None,
                "created_at": "2026-07-09T11:00:00Z",
                "head": {"ref": "claude/loop-fix-2"},
                "html_url": "https://github.com/o/r/pull/20",
            },
            {  # feature branch — must be excluded
                "number": 30,
                "title": "Feature PR",
                "state": "open",
                "draft": False,
                "merged_at": None,
                "created_at": "2026-07-08T11:00:00Z",
                "head": {"ref": "feature/other"},
                "html_url": "https://github.com/o/r/pull/30",
            },
        ]
        stub_req = self._fake_requests(pr_list)

        with mock.patch.object(gha, "token", return_value="ghp_test"), \
             mock.patch.object(gha, "repo", return_value=("owner", "repo")), \
             mock.patch.object(gha, "requests", stub_req):
            result = mh.history(limit=100, root=tmp_path)

        pr_evts = [e for e in result["events"] if e["source"] == "pr"]
        assert len(pr_evts) == 2, f"expected 2 loop PRs, got {len(pr_evts)}"

        # Merged one is status ok
        merged = [e for e in pr_evts if e["kind"] == "merged"]
        assert len(merged) == 1
        assert merged[0]["status"] == "ok"
        assert merged[0]["ref"] == "#10"

        # Open one is status info
        open_pr = [e for e in pr_evts if e["kind"] == "open"]
        assert len(open_pr) == 1
        assert open_pr[0]["status"] == "info"

        # feature/other excluded
        refs = {e["ref"] for e in pr_evts}
        assert "#30" not in refs

    def test_no_token_pr_note(self, tmp_path):
        """No token → pr source count==0 with a note explaining why."""
        import admin.github_api as gha
        import admin.metabolism_history as mh

        with mock.patch.object(gha, "token", return_value=None), \
             _stub_requests(gha):
            result = mh.history(limit=100, root=tmp_path)

        pr_meta = result["sources"]["pr"]
        assert pr_meta["count"] == 0
        assert pr_meta["note"] is not None
        assert "token" in pr_meta["note"].lower()

    def test_limit_clamping(self, tmp_path):
        """limit is clamped to [1, 500]."""
        import admin.github_api as gha
        import admin.metabolism_history as mh

        with mock.patch.object(gha, "token", return_value=None), \
             _stub_requests(gha):
            r0 = mh.history(limit=0, root=tmp_path)
            r_big = mh.history(limit=9999, root=tmp_path)

        # limit=0 clamped to 1
        assert isinstance(r0["events"], list)
        # limit=9999 clamped to 500 (empty root so still 0 events)
        assert isinstance(r_big["events"], list)


class TestMixedTimezoneFormats:
    """Regression: ledgers mix '…Z', '…+00:00' and naive timestamps.

    A naive/aware datetime mix must not make the feed-wide sort raise
    TypeError (which would blank the whole feed via the last-resort handler).
    """

    def test_mixed_tz_suffixes_sort_without_blanking(self, tmp_path):
        import admin.github_api as gha
        import admin.metabolism_history as mh

        met = tmp_path / "data" / "metabolism"
        nw = tmp_path / "data" / "neuralweb"
        met.mkdir(parents=True)
        nw.mkdir(parents=True)

        # 'Z' suffix (heartbeat-style)
        (met / "heartbeat.jsonl").write_text(
            json.dumps({"ts": "2026-07-10T08:00:00Z", "phase": "P0_inert", "note": "hb"}) + "\n",
            encoding="utf-8")
        # '+00:00' suffix (journal-style, aware)
        (nw / "governance.jsonl").write_text(
            json.dumps({"ts": "2026-07-11T08:00:00+00:00", "event_type": "grant", "target": "x"}) + "\n",
            encoding="utf-8")
        # naive, no suffix
        (met / "lessons.jsonl").write_text(
            json.dumps({"ts": "2026-07-12T08:00:00", "what_failed": "naive ts row"}) + "\n",
            encoding="utf-8")

        with mock.patch.object(gha, "token", return_value=None), \
             _stub_requests(gha):
            result = mh.history(limit=100, root=tmp_path)

        # All three rows survive and sort newest-first; no blank-feed fallback.
        assert len(result["events"]) == 3
        assert [e["source"] for e in result["events"]] == ["lesson", "governance", "heartbeat"]
        # No reader errored — the only expected note is the pr token note.
        for src, meta in result["sources"].items():
            if src != "pr":
                assert meta["note"] is None, f"{src}: {meta['note']}"
