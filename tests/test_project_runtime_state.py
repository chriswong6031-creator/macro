"""Hermetic contracts for the private project runtime-state collector."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from jsonschema import ValidationError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.project_runtime_state import (  # noqa: E402
    PrivacyViolation,
    SystemEvidenceReader,
    TopologyError,
    assert_private_safe,
    canonical_json,
    collect_runtime_state,
    freshness_state,
    load_topology,
    render_markdown,
    snapshot_expired,
    validate_snapshot,
    write_private_atomic,
)

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
SHA = {
    "macro": "1" * 40,
    "terminal": "2" * 40,
    "portfolio": "3" * 40,
}


class FakeReader:
    """Records only read operations and returns bounded synthetic evidence."""

    def __init__(self):
        self.units: dict[str, dict[str, str]] = {}
        self.json: dict[str, object] = {}
        self.jsonl: dict[str, list[object]] = {}
        self.http: dict[str, tuple[int | None, object]] = {}
        self.text_http: dict[str, tuple[int | None, str | None]] = {}
        self.mtimes: dict[str, datetime] = {}
        self.crontab = ""
        self.calls: list[tuple[str, object]] = []

    def path(self, value):
        self.calls.append(("path", str(value)))
        return Path(str(value))

    def run(self, argv, *, timeout=8.0):
        self.calls.append(("run", tuple(argv)))
        if argv[:2] == ["systemctl", "show"]:
            unit = argv[2]
            fields = self.units.get(unit)
            if fields is None:
                return 0, "LoadState=not-found\n"
            return 0, "".join(f"{key}={value}\n" for key, value in fields.items())
        if "rev-parse" in argv:
            path = argv[argv.index("-C") + 1]
            repo = "macro" if path.endswith("macro") else "terminal" if "terminal" in path else "portfolio"
            return 0, SHA[repo] + "\n"
        if "rev-list" in argv:
            return 0, "0\n"
        if "ls-remote" in argv:
            repo = "portfolio" if "Mastermind.git" in argv[-2] else "terminal" if "terminal" in argv[-2] else "macro"
            return 0, f"{SHA[repo]}\t{argv[-1]}\n"
        if argv == ["crontab", "-l"]:
            return (0, self.crontab) if self.crontab else (1, "")
        raise AssertionError(f"unexpected command: {argv!r}")

    def read_text(self, path, *, max_bytes=2_000_000):
        self.calls.append(("read_text", str(path)))
        return None

    def read_json(self, path):
        self.calls.append(("read_json", str(path)))
        return self.json.get(str(path))

    def read_jsonl(self, path, *, tail=100):
        self.calls.append(("read_jsonl", str(path)))
        return self.jsonl.get(str(path), [])[-tail:]

    def mtime(self, path):
        self.calls.append(("mtime", str(path)))
        return self.mtimes.get(str(path))

    def http_json(self, url, *, timeout=5.0):
        self.calls.append(("http_get", str(url)))
        return self.http.get(str(url), (None, None))

    def http_text(self, url, *, timeout=5.0):
        self.calls.append(("http_get", str(url)))
        return self.text_http.get(str(url), (None, None))


def _topology() -> dict:
    return {
        "schema": "mastermind.production_topology.v1",
        "project_id": "mastermind-x",
        "environment": "production",
        "runtime_state_policy": {"visibility": "private_authenticated"},
        "repositories": [
            {
                "id": repo,
                "branch": "main" if repo == "macro" else "master",
                "deployed_probe": {"kind": "git_head", "path": f"/opt/{'mastermind' if repo == 'portfolio' else repo}"},
                "canonical_probe": {"kind": "git_ref", "path": f"/opt/{'mastermind' if repo == 'portfolio' else repo}", "ref": "origin/main" if repo == "macro" else "origin/master"},
                "runtime_probe": {"kind": "none"},
            }
            for repo in ("macro", "terminal", "portfolio")
        ],
        "services": [{
            "id": "macro.api", "repo": "macro", "owner": "macro-admin",
            "kind": "api_service", "host_class": "vps", "units": ["macro-api.service"],
            "expected_state": "active",
        }],
        "scheduled_systems": [{
            "id": "macro.daily", "repo": "macro", "owner": "macro-admin", "host_class": "vps",
            "probe": {
                "kind": "artifact", "path": "/opt/macro/data/daily.json",
                "last_run_field": "finished_at", "last_success_field": "finished_at",
                "outcome_field": "outcome",
            },
            "expected_state": "scheduled",
        }],
        "data_planes": [{
            "id": "macro.safe_plane", "repo": "macro", "owner": "macro-admin",
            "probe": {
                "kind": "json_file", "path": "/opt/macro/data/plane.json",
                "timestamp_field": "generated_at", "status_field": "ok", "max_age_seconds": 3600,
                "direct_status_map": {"true": "healthy", "false": "degraded"},
                "metric_fields": {"row_count": "count"},
            },
        }],
        "bridges": [{
            "id": "macro.to_terminal", "producer_repo": "macro", "consumer_repo": "terminal",
            "owner": "macro-admin", "authority": "display_only",
            "probe": {
                "kind": "json_file", "path": "/opt/terminal/bridge.json",
                "timestamp_field": "published_at", "status_field": "stale", "max_age_seconds": 3600,
                "direct_status_map": {"true": "stale", "false": "healthy"},
            },
        }],
        "storage": [{
            "id": "terminal.schema", "repo": "terminal", "owner": "macro-admin",
            "kind": "database", "expected_schema": "0006", "probe": {"kind": "schema_contract_only"},
        }],
        "providers": [{
            "id": "macro.ai_pool", "repo": "macro", "owner": "macro-admin",
            "probe": {
                "kind": "provider_jsonl", "path": "/opt/macro/data/provider.jsonl",
                "roles": {"p": "primary", "f": "fallback"}, "role_field": "role",
                "ok_field": "ok", "timestamp_field": "ts",
            },
        }],
    }


def _reader() -> FakeReader:
    reader = FakeReader()
    reader.units["macro-api.service"] = {
        "LoadState": "loaded", "ActiveState": "active", "SubState": "running",
        "UnitFileState": "enabled", "Result": "success", "NRestarts": "0",
        "ExecMainStartTimestamp": "2026-08-11T11:00:00Z",
    }
    reader.json["/opt/macro/data/daily.json"] = {
        "finished_at": "2026-08-11T11:55:00Z", "outcome": "success",
    }
    # Hostile fields are intentionally present in source evidence. Positive
    # selection must keep them out of both canonical output forms.
    reader.json["/opt/macro/data/plane.json"] = {
        "generated_at": "2026-08-11T11:59:00Z", "ok": True, "count": 12,
        "api_key": "sk-do-not-leak", "error": "Bearer also-do-not-leak",
        "provider_attempts": [{"request_id": "private"}],
    }
    reader.json["/opt/terminal/bridge.json"] = {
        "published_at": "2026-08-11T11:58:00Z", "stale": False,
        "email": "person@example.test", "detail": "credentialed source body",
    }
    reader.jsonl["/opt/macro/data/provider.jsonl"] = [
        {"ts": "2026-08-11T11:50:00Z", "role": "p", "ok": False, "detail": "sk-private"},
        {"ts": "2026-08-11T11:51:00Z", "role": "f", "ok": True, "request_id": "private"},
    ]
    return reader


def test_golden_snapshot_validates_is_deterministic_and_never_leaks_hostile_fields():
    reader = _reader()
    first = collect_runtime_state(_topology(), reader=reader, now=NOW, mode="fixture")
    second = collect_runtime_state(_topology(), reader=_reader(), now=NOW, mode="fixture")

    assert canonical_json(first) == canonical_json(second)
    assert render_markdown(first) == render_markdown(second)
    validate_snapshot(first, ROOT / "contracts/runtime/mastermind.runtime_state.v1.schema.json")
    combined = canonical_json(first) + render_markdown(first)
    for forbidden in ("sk-do-not-leak", "Bearer", "person@example.test", "request_id", "provider_attempts"):
        assert forbidden not in combined
    # Primary down with a working fallback is visible and never false-green.
    assert first["providers"][0]["state"] == "degraded"
    assert first["providers"][0]["fallback_state"] == "healthy"
    assert not any(kind in {"post", "write", "restart"} for kind, _ in reader.calls)


def test_missing_required_unit_is_named_and_counted_not_false_green():
    reader = _reader()
    reader.units.pop("macro-api.service")
    state = collect_runtime_state(_topology(), reader=reader, now=NOW, mode="fixture")

    assert state["services"][0]["state"] == "missing"
    assert state["services"][0]["units"][0]["state"] == "not_found"
    assert "macro.api" in state["coverage"]["missing_ids"]
    assert any(issue["component_id"] == "macro.api" for issue in state["issues"])


def test_freshness_distinguishes_missing_stale_and_future_evidence():
    assert freshness_state(None, now=NOW, max_age_seconds=60) == "missing"
    assert freshness_state(NOW - timedelta(seconds=61), now=NOW, max_age_seconds=60) == "stale"
    assert freshness_state(NOW - timedelta(seconds=60), now=NOW, max_age_seconds=60) == "healthy"
    assert freshness_state(NOW + timedelta(minutes=6), now=NOW, max_age_seconds=60) == "indeterminate"


def test_first_fresh_threshold_cannot_be_hidden_by_a_green_top_level_status():
    topology = _topology()
    topology["data_planes"][0]["probe"].update({
        "minimum_field": "sla.board.consecutive_met", "minimum_value": 5,
    })
    reader = _reader()
    reader.json["/opt/macro/data/plane.json"]["sla"] = {"board": {"consecutive_met": 0}}
    state = collect_runtime_state(topology, reader=reader, now=NOW, mode="fixture")
    assert state["data_planes"][0]["state"] == "degraded"


def test_explicit_no_change_receipt_is_not_mislabeled_stalled():
    reader = _reader()
    reader.json["/opt/macro/data/daily.json"] = {
        "finished_at": "2026-08-11T11:55:00Z", "outcome": "no_change",
    }
    state = collect_runtime_state(_topology(), reader=reader, now=NOW, mode="fixture")
    job = state["scheduled_systems"][0]
    assert job["state"] == "ran_no_change"
    assert job["run_outcome"] == "ran_no_change"


def test_scheduler_aggregate_names_a_failed_critical_job_without_copying_its_error():
    topology = _topology()
    topology["scheduled_systems"] = [{
        "id": "portfolio.scheduler", "repo": "portfolio", "owner": "macro-admin",
        "host_class": "vps", "expected_state": "scheduled",
        "probe": {
            "kind": "scheduler_api", "url": "http://127.0.0.1:8001/api/scheduler",
            "jobs": ["daily", "publish"], "last_run_field": "last_started",
            "last_finished_field": "last_finished", "outcome_field": "last_status",
            "next_expected_field": "next_run_time",
        },
    }]
    reader = _reader()
    reader.http["http://127.0.0.1:8001/api/scheduler"] = (200, {"jobs": [
        {"id": "daily", "last_started": "2026-08-11T10:00:00Z", "last_finished": "2026-08-11T10:01:00Z", "last_status": "ok", "next_run_time": "2026-08-12T10:00:00Z"},
        {"id": "publish", "last_started": "2026-08-11T11:00:00Z", "last_finished": "2026-08-11T11:01:00Z", "last_status": "error", "next_run_time": "2026-08-12T11:00:00Z", "error": "Bearer private"},
    ]})
    state = collect_runtime_state(topology, reader=reader, now=NOW, mode="fixture")
    job = state["scheduled_systems"][0]
    assert job["state"] == "failed"
    assert job["run_outcome"] == "failed"
    assert "Bearer private" not in canonical_json(state)


def test_scheduler_skip_is_named_not_due_instead_of_false_green():
    topology = _topology()
    topology["scheduled_systems"] = [{
        "id": "portfolio.daily", "repo": "portfolio", "owner": "macro-admin",
        "host_class": "vps", "expected_state": "scheduled",
        "probe": {
            "kind": "scheduler_api", "url": "http://127.0.0.1:8001/api/scheduler",
            "job_id": "daily", "last_run_field": "last_finished",
            "outcome_field": "last_status", "next_expected_field": "next_run_time",
        },
    }]
    reader = _reader()
    reader.http["http://127.0.0.1:8001/api/scheduler"] = (200, {"jobs": [{
        "id": "daily", "last_started": "2026-08-11T11:00:00Z",
        "last_finished": "2026-08-11T11:01:00Z", "last_status": "skip",
        "next_run_time": "2026-08-12T11:00:00Z",
    }]})
    job = collect_runtime_state(topology, reader=reader, now=NOW, mode="fixture")["scheduled_systems"][0]
    assert job["run_outcome"] == "skipped"
    assert job["state"] == "not_due"


def test_unregistered_scheduler_row_with_old_success_cannot_false_green():
    topology = _topology()
    topology["scheduled_systems"] = [{
        "id": "portfolio.daily", "repo": "portfolio", "owner": "macro-admin",
        "host_class": "vps", "expected_state": "scheduled",
        "probe": {
            "kind": "scheduler_api", "url": "http://127.0.0.1:8001/api/scheduler",
            "job_id": "daily", "last_run_field": "last_finished",
            "outcome_field": "last_status", "next_expected_field": "next_run_time",
        },
    }]
    reader = _reader()
    reader.http["http://127.0.0.1:8001/api/scheduler"] = (200, {"jobs": [{
        "id": "daily", "last_started": "2026-07-01T11:00:00Z",
        "last_finished": "2026-07-01T11:01:00Z", "last_status": "ok",
        "next_run_time": None,
    }]})
    job = collect_runtime_state(topology, reader=reader, now=NOW, mode="fixture")["scheduled_systems"][0]
    assert job["run_outcome"] == "succeeded"
    assert job["state"] == "indeterminate"

    reader.http["http://127.0.0.1:8001/api/scheduler"][1]["jobs"][0]["next_run_time"] = "2026-08-12T11:00:00Z"
    job = collect_runtime_state(topology, reader=reader, now=NOW, mode="fixture")["scheduled_systems"][0]
    assert job["state"] == "stale"


def test_disabled_scheduler_contract_surfaces_accidental_registration():
    topology = _topology()
    topology["scheduled_systems"] = [{
        "id": "portfolio.sync", "repo": "portfolio", "owner": "macro-admin",
        "host_class": "vps", "expected_state": "disabled",
        "probe": {
            "kind": "scheduler_api", "url": "http://127.0.0.1:8001/api/scheduler",
            "job_id": "sync", "last_run_field": "last_finished",
            "outcome_field": "last_status", "next_expected_field": "next_run_time",
        },
    }]
    reader = _reader()
    row = {
        "id": "sync", "last_started": "2026-08-11T11:00:00Z",
        "last_finished": "2026-08-11T11:01:00Z", "last_status": "ok",
        "next_run_time": None,
    }
    reader.http["http://127.0.0.1:8001/api/scheduler"] = (200, {"jobs": [row]})
    job = collect_runtime_state(topology, reader=reader, now=NOW, mode="fixture")["scheduled_systems"][0]
    assert job["state"] == "disabled"

    row["next_run_time"] = "2026-08-12T11:00:00Z"
    job = collect_runtime_state(topology, reader=reader, now=NOW, mode="fixture")["scheduled_systems"][0]
    assert job["state"] == "degraded"


def test_release_sha_and_bridge_failure_are_component_scoped():
    reader = _reader()
    reader.json["/opt/terminal/bridge.json"]["stale"] = True
    state = collect_runtime_state(_topology(), reader=reader, now=NOW, mode="fixture")

    assert {row["deployed_sha"] for row in state["releases"]} == set(SHA.values())
    assert state["services"][0]["state"] == "healthy"
    assert state["bridges"][0]["state"] == "stale"
    assert any(issue["component_type"] == "bridge" for issue in state["issues"])


def test_configured_runtime_identity_cannot_false_green_when_version_is_absent():
    topology = _topology()
    portfolio = next(row for row in topology["repositories"] if row["id"] == "portfolio")
    portfolio["runtime_probe"] = {"kind": "http_json", "url": "http://127.0.0.1:8001/health"}
    state = collect_runtime_state(topology, reader=_reader(), now=NOW, mode="fixture")
    release = next(row for row in state["releases"] if row["id"] == "portfolio")
    assert release["deployed_sha"] == release["canonical_branch_sha"]
    assert release["runtime_sha"] is None
    assert release["state"] == "indeterminate"


def test_ancient_every_minute_timer_is_stale_even_if_still_enabled():
    topology = _topology()
    topology["scheduled_systems"] = [{
        "id": "macro.fast", "repo": "macro", "owner": "macro-admin", "host_class": "vps",
        "probe": {"kind": "systemd_timer", "unit": "macro-fast.timer"},
        "expected_state": "active", "cadence": "every_minute",
    }]
    reader = _reader()
    reader.units["macro-fast.timer"] = {
        "LoadState": "loaded", "ActiveState": "active", "SubState": "waiting",
        "UnitFileState": "enabled", "Result": "success", "NRestarts": "0",
        "LastTriggerUSec": "2026-08-11T10:00:00Z",
        "NextElapseUSecRealtime": "2026-08-11T12:01:00Z",
    }
    reader.units["macro-fast.service"] = {
        "LoadState": "loaded", "ActiveState": "inactive", "SubState": "dead",
        "UnitFileState": "static", "Result": "success", "NRestarts": "0",
    }
    state = collect_runtime_state(topology, reader=reader, now=NOW, mode="fixture")
    assert state["scheduled_systems"][0]["state"] == "stale"


def test_missing_required_timer_is_missing_but_installed_unarmed_timer_is_operator_armed():
    topology = _topology()
    topology["scheduled_systems"] = [{
        "id": "macro.fast", "repo": "macro", "owner": "macro-admin", "host_class": "vps",
        "probe": {"kind": "systemd_timer", "unit": "macro-fast.timer"},
        "expected_state": "active", "cadence": "every_minute",
    }]
    reader = _reader()
    state = collect_runtime_state(topology, reader=reader, now=NOW, mode="fixture")
    assert state["scheduled_systems"][0]["state"] == "missing"
    assert state["coverage"]["missing_ids"] == ["macro.fast"]

    topology["scheduled_systems"][0]["expected_state"] = "operator_armed"
    reader.units["macro-fast.timer"] = {
        "LoadState": "loaded", "ActiveState": "inactive", "SubState": "dead",
        "UnitFileState": "disabled", "Result": "success", "NRestarts": "0",
    }
    state = collect_runtime_state(topology, reader=reader, now=NOW, mode="fixture")
    assert state["scheduled_systems"][0]["state"] == "operator_armed"

    reader.run = lambda argv, timeout=8.0: (127, "")
    state = collect_runtime_state(topology, reader=reader, now=NOW, mode="fixture")
    assert state["scheduled_systems"][0]["state"] == "indeterminate"


def test_synced_checkout_does_not_hide_a_missing_release_cron():
    topology = _topology()
    topology["scheduled_systems"] = [{
        "id": "macro.release_update", "repo": "macro", "owner": "macro-admin",
        "host_class": "vps", "expected_state": "active",
        "probe": {
            "kind": "release_match", "deployed_repo": "/opt/macro",
            "canonical_ref": "origin/main", "required_cron_id": "macro_update",
        },
    }]
    state = collect_runtime_state(topology, reader=_reader(), now=NOW, mode="fixture")
    assert state["scheduled_systems"][0]["state"] == "failed"

    reader = _reader()
    reader.crontab = "*/3 * * * * /usr/local/bin/macro-update >> /var/log/macro-update.log 2>&1\n"
    state = collect_runtime_state(topology, reader=reader, now=NOW, mode="fixture")
    assert state["scheduled_systems"][0]["state"] == "indeterminate"
    assert state["scheduled_systems"][0]["last_success"] is None


def test_unknown_repo_ownership_is_explicitly_unresolved():
    topology = _topology()
    topology["services"][0]["repo"] = "mystery"
    state = collect_runtime_state(topology, reader=_reader(), now=NOW, mode="fixture")
    assert state["services"][0]["repo"] == "unresolved"
    assert state["coverage"]["state"] == "degraded"
    assert state["coverage"]["unresolved_owner_ids"] == ["macro.api"]


def test_privacy_guard_catches_a_post_collection_mutation():
    state = collect_runtime_state(_topology(), reader=_reader(), now=NOW, mode="fixture")
    state["services"][0]["api_key"] = "sk-mutated"
    with pytest.raises(PrivacyViolation):
        assert_private_safe(state)


def test_admin_failure_envelope_never_copies_exception_text(monkeypatch):
    from admin import runtime_state

    def explode(_path):
        raise RuntimeError("Bearer sk-do-not-return person@example.test")

    monkeypatch.setattr(runtime_state, "load_topology", explode)
    payload, code = runtime_state.snapshot()
    assert code == 503
    assert payload == {
        "schema": "mastermind.runtime_state.error.v1",
        "project_id": "mastermind-x",
        "state": "indeterminate",
        "reason_code": "collection_failed",
    }


def test_private_atomic_write_replaces_prior_snapshot_and_locks_mode(tmp_path):
    target = tmp_path / "project_runtime_state.json"
    target.write_text("prior")
    write_private_atomic(target, "new\n")
    assert target.read_text() == "new\n"
    assert target.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob(".project_runtime_state.json.*"))


def test_snapshot_self_expiry_is_explicit():
    state = collect_runtime_state(_topology(), reader=_reader(), now=NOW, mode="fixture", valid_for_seconds=300)
    assert state["checked_at"] == "2026-08-11T12:00:00Z"
    assert state["valid_until"] == "2026-08-11T12:05:00Z"
    assert json.loads(canonical_json(state))["valid_until"] == "2026-08-11T12:05:00Z"


def test_old_provider_attempts_are_stale_even_when_the_last_attempt_succeeded():
    topology = _topology()
    topology["providers"][0]["probe"]["max_age_seconds"] = 60
    reader = _reader()
    reader.jsonl["/opt/macro/data/provider.jsonl"] = [
        {"ts": "2026-08-11T11:00:00Z", "role": "p", "ok": True},
    ]
    state = collect_runtime_state(topology, reader=reader, now=NOW, mode="fixture")
    assert state["providers"][0]["state"] == "stale"


def test_full_topology_names_every_portfolio_scheduler_job_and_validates_locally():
    topology = load_topology(ROOT / "config/production_topology.yml")
    jobs = {
        row["probe"]["job_id"]
        for row in topology["scheduled_systems"]
        if row["id"].startswith("portfolio.") and row["probe"].get("kind") == "scheduler_api"
    }
    assert jobs == {
        "macro_refresh", "daily_mark", "daily_loop", "autonomous_daily", "etf_daily",
        "heavyweight_daily", "china_daily", "hk_daily", "settle_pending",
        "settle_brain_asia", "watch_us_overnight", "watch_asia_overnight",
        "derisk_us_intraday", "prewarm_marks", "publish_macro_snapshot", "cio_weekly",
        "improvement_agenda_weekly", "loop_maintenance", "experiment_maturity",
        "portfolio_risk_compose", "portfolio_risk_daily", "vps_state_sync",
    }


def test_duplicate_topology_ids_fail_closed_before_coverage_is_built():
    topology = _topology()
    topology["services"].append(dict(topology["services"][0]))
    with pytest.raises(TopologyError, match="duplicate services ids"):
        collect_runtime_state(topology, reader=_reader(), now=NOW, mode="fixture")


def test_newer_unfinished_scheduler_run_exceeds_runtime_contract_and_fails():
    topology = _topology()
    topology["scheduled_systems"] = [{
        "id": "portfolio.daily", "repo": "portfolio", "owner": "macro-admin",
        "host_class": "vps", "expected_state": "scheduled",
        "probe": {
            "kind": "scheduler_api", "url": "http://127.0.0.1:8001/api/scheduler",
            "job_id": "daily", "last_run_field": "last_finished",
            "outcome_field": "last_status", "next_expected_field": "next_run_time",
            "max_run_seconds": 3600,
        },
    }]
    reader = _reader()
    reader.http["http://127.0.0.1:8001/api/scheduler"] = (200, {"jobs": [{
        "id": "daily", "last_started": "2026-08-11T03:00:00Z",
        "last_finished": "2026-08-10T03:01:00Z", "last_status": "ok",
        "next_run_time": "2026-08-12T03:00:00Z",
    }]})
    job = collect_runtime_state(topology, reader=reader, now=NOW, mode="fixture")["scheduled_systems"][0]
    assert job["run_outcome"] == "in_progress"
    assert job["state"] == "failed"

    reader.http["http://127.0.0.1:8001/api/scheduler"][1]["jobs"][0]["last_started"] = "2026-08-11T11:30:00Z"
    active = collect_runtime_state(topology, reader=reader, now=NOW, mode="fixture")
    assert active["scheduled_systems"][0]["state"] == "in_progress"
    validate_snapshot(active, ROOT / "contracts/runtime/mastermind.runtime_state.v1.schema.json")


def test_publication_timestamp_wins_over_date_only_source_watermark_for_recency():
    topology = _topology()
    topology["data_planes"][0]["probe"]["as_of_field"] = "as_of"
    reader = _reader()
    reader.json["/opt/macro/data/plane.json"]["as_of"] = "2026-08-10"
    state = collect_runtime_state(topology, reader=reader, now=NOW, mode="fixture")
    assert state["data_planes"][0]["state"] == "healthy"
    assert state["data_planes"][0]["freshness_basis"] == "timestamp"


def test_latest_provider_attempt_controls_bucket_state_not_any_old_success():
    reader = _reader()
    reader.jsonl["/opt/macro/data/provider.jsonl"] = [
        {"ts": "2026-08-11T11:49:00Z", "role": "p", "ok": True},
        {"ts": "2026-08-11T11:50:00Z", "role": "p", "ok": False},
        {"ts": "2026-08-11T11:51:00Z", "role": "f", "ok": True},
    ]
    provider = collect_runtime_state(_topology(), reader=reader, now=NOW, mode="fixture")["providers"][0]
    assert provider["primary_state"] == "failed"
    assert provider["fallback_state"] == "healthy"
    assert provider["state"] == "degraded"


def test_stale_fallback_does_not_make_a_fresh_primary_failure_look_operational():
    topology = _topology()
    topology["providers"][0]["probe"]["max_age_seconds"] = 3600
    reader = _reader()
    reader.jsonl["/opt/macro/data/provider.jsonl"] = [
        {"ts": "2026-08-10T11:00:00Z", "role": "f", "ok": True},
        {"ts": "2026-08-11T11:59:00Z", "role": "p", "ok": False},
    ]
    provider = collect_runtime_state(topology, reader=reader, now=NOW, mode="fixture")["providers"][0]
    assert provider["primary_state"] == "failed"
    assert provider["fallback_state"] == "stale"
    assert provider["state"] == "stale"


def test_jsonl_tail_remains_visible_after_generic_small_receipt_size_cap(tmp_path):
    ledger = tmp_path / "provider.jsonl"
    ledger.write_text(
        json.dumps({"padding": "x" * 2_100_000}) + "\n"
        + json.dumps({"ts": "2026-08-11T11:59:00Z", "rung": "codex", "ok": False}) + "\n"
        + json.dumps({"ts": "2026-08-11T12:00:00Z", "rung": "deepseek", "ok": True}) + "\n"
    )
    reader = SystemEvidenceReader(mode="local", repo_root=tmp_path)
    rows = reader.read_jsonl(ledger, tail=2)
    assert [row["rung"] for row in rows] == ["codex", "deepseek"]


def test_metrics_schema_rejects_innocuous_arbitrary_source_text():
    state = collect_runtime_state(_topology(), reader=_reader(), now=NOW, mode="fixture")
    state["data_planes"][0]["metrics"]["message"] = "vendor internal label"
    assert_private_safe(state)
    with pytest.raises(ValidationError):
        validate_snapshot(state, ROOT / "contracts/runtime/mastermind.runtime_state.v1.schema.json")


@pytest.mark.parametrize("non_finite", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_metrics_never_enter_canonical_json(non_finite):
    reader = _reader()
    reader.json["/opt/macro/data/plane.json"]["count"] = non_finite
    state = collect_runtime_state(_topology(), reader=reader, now=NOW, mode="fixture")
    assert "row_count" not in state["data_planes"][0]["metrics"]

    state["data_planes"][0]["metrics"]["row_count"] = non_finite
    with pytest.raises(PrivacyViolation, match="non-finite"):
        canonical_json(state)
    with pytest.raises(PrivacyViolation, match="non-finite"):
        validate_snapshot(state, ROOT / "contracts/runtime/mastermind.runtime_state.v1.schema.json")


def test_expired_snapshot_is_machine_detectable_and_visibly_marked():
    state = collect_runtime_state(_topology(), reader=_reader(), now=NOW, mode="fixture", valid_for_seconds=300)
    evaluated = NOW + timedelta(minutes=6)
    assert snapshot_expired(state, at=evaluated)
    assert "EXPIRED" in render_markdown(state, evaluated_at=evaluated)
    state["valid_until"] = "2000-01-01T00:00:00Z"
    assert "EXPIRED" in render_markdown(state)
