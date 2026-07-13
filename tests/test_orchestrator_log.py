"""tests/test_orchestrator_log.py — Unit tests for engine.neuralweb.orchestrator_log (W-AI).

Covers:
 1. build_entry composes fields from health.json + daily_brief.json + the
    mastermind feedback summary (synthetic tmp-root fixtures). run_date is the
    CALENDAR date of the run (the injectable ``now``); the market-data date is
    carried separately as data_as_of (brief.as_of → health.as_of → run_date).
 2. build_entry never raises on an empty root (all inputs optional).
 3. record_run keep-first per run_date+workflow (same calendar day twice → one
    entry; different workflow same day → second entry). REGRESSION: a stale
    carried-forward brief (as_of = yesterday) must NOT collide with yesterday's
    entry — today's run still records, with data_as_of = yesterday.
 4. Review every N runs: config.yml orchestrator.review_every_n_runs=2 →
    second distinct run_date triggers a review row with window_runs=2 and
    deterministic trend strings.
 5. Site artifact written with schema + entries + reviews — valid JSON with the
    schema key whether or not the envelope stamp succeeded (unstamped fallback).
 6. _settings bounds (defaults, valid override, out-of-bounds rejected).
 7. load() read surface.
 8. build_review edge: empty entries list does not raise.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from engine.neuralweb.orchestrator_log import (  # noqa: E402
    ARTIFACT_ID,
    SCHEMA,
    _settings,
    build_entry,
    build_review,
    load,
    record_run,
)

_NOW = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_health(tmp_path: Path, *, as_of: str = "2026-07-10") -> dict:
    h = {
        "schema": "neuralweb.health.v1",
        "as_of": as_of,
        "overall_status": "ok",
        "summary_counts": {"total_lobes": 5, "fresh": 3, "stale": 2},
        "lobes": [{"id": f"lobe-{i}", "status": "fresh"} for i in range(5)],
        "cortex": {"status": "ok"},
    }
    p = tmp_path / "data" / "neuralweb" / "health.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(h), encoding="utf-8")
    return h


def _make_brief(tmp_path: Path, *, as_of: str = "2026-07-10") -> dict:
    b = {
        "schema": "neuralweb.daily_brief.v1",
        "as_of": as_of,
        "status": "ok",
        "what_changed": [
            {"kind": "lobe_refresh", "id": "a"},
            {"kind": "lobe_refresh", "id": "b"},
            {"kind": "as_of_advanced", "id": "system"},
        ],
        "what_contradicted": [{"id": "C1"}],
        "operator_attention": [{"priority": 2}, {"priority": 3}],
        "did_the_brain_run": {"cortex_status": "ok", "individual_tool_calls": 4},
        "_gaps": [],
    }
    p = tmp_path / "data" / "neuralweb" / "daily_brief.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(b), encoding="utf-8")
    return b


def _make_feedback(tmp_path: Path) -> dict:
    fb = {
        "schema": "neuralweb.mastermind_feedback_summary.v1",
        "state": "present",
        "gap_notes": [],
        "nudges": [
            {"code": "ctx_stale_run", "severity": "high"},
            {"code": "lobe_request_theme", "severity": "low"},
        ],
        "operator_directives": [{"id": "deadbeef01", "text": "look at radar"}],
    }
    p = tmp_path / "data" / "governance" / "mastermind_feedback_summary.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(fb), encoding="utf-8")
    return fb


def _make_full_root(tmp_path: Path, *, as_of: str = "2026-07-10") -> None:
    _make_health(tmp_path, as_of=as_of)
    _make_brief(tmp_path, as_of=as_of)
    _make_feedback(tmp_path)


def _make_config(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "config.yml"
    p.write_text(body, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 1. build_entry field composition
# ---------------------------------------------------------------------------

class TestBuildEntry:
    def test_run_date_is_calendar_date_of_now(self, tmp_path):
        """run_date keys on the injectable ``now`` (the run's calendar date),
        NOT on the brief's as_of."""
        _make_full_root(tmp_path)
        entry = build_entry(tmp_path, now=_NOW)
        assert entry["run_date"] == "2026-07-10"

    def test_run_date_from_now_even_when_brief_older(self, tmp_path):
        """Brief carries an older as_of — run_date must still be now's date."""
        _make_full_root(tmp_path, as_of="2026-07-08")
        entry = build_entry(tmp_path, now=_NOW)
        assert entry["run_date"] == "2026-07-10"

    def test_data_as_of_from_brief_as_of(self, tmp_path):
        _make_full_root(tmp_path, as_of="2026-07-09")
        entry = build_entry(tmp_path, now=_NOW)
        assert entry["data_as_of"] == "2026-07-09"

    def test_data_as_of_falls_back_to_health(self, tmp_path):
        """No brief → data_as_of comes from health.as_of."""
        _make_health(tmp_path, as_of="2026-07-08")
        _make_feedback(tmp_path)
        entry = build_entry(tmp_path, now=_NOW)
        assert entry["data_as_of"] == "2026-07-08"

    def test_data_as_of_falls_back_to_run_date(self, tmp_path):
        """Empty root → data_as_of degrades to the run_date itself."""
        entry = build_entry(tmp_path, now=_NOW)
        assert entry["data_as_of"] == entry["run_date"] == "2026-07-10"

    def test_workflow_default_daily(self, tmp_path):
        _make_full_root(tmp_path)
        entry = build_entry(tmp_path, now=_NOW)
        assert entry["workflow"] == "daily"

    def test_lobe_counts(self, tmp_path):
        _make_full_root(tmp_path)
        entry = build_entry(tmp_path, now=_NOW)
        assert entry["lobes_total"] == 5
        assert entry["lobes_stale"] == 2

    def test_overall_status(self, tmp_path):
        _make_full_root(tmp_path)
        entry = build_entry(tmp_path, now=_NOW)
        assert entry["overall_status"] == "ok"

    def test_what_changed_counts_and_kinds(self, tmp_path):
        _make_full_root(tmp_path)
        entry = build_entry(tmp_path, now=_NOW)
        assert entry["what_changed_n"] == 3
        assert entry["what_changed_kinds"] == {"lobe_refresh": 2, "as_of_advanced": 1}

    def test_contradictions_and_attention_counts(self, tmp_path):
        _make_full_root(tmp_path)
        entry = build_entry(tmp_path, now=_NOW)
        assert entry["contradictions_n"] == 1
        assert entry["operator_attention_n"] == 2

    def test_cortex_fields(self, tmp_path):
        _make_full_root(tmp_path)
        entry = build_entry(tmp_path, now=_NOW)
        assert entry["cortex_status"] == "ok"
        assert entry["cortex_tool_calls"] == 4

    def test_feedback_dialogue_fields(self, tmp_path):
        _make_full_root(tmp_path)
        entry = build_entry(tmp_path, now=_NOW)
        assert entry["feedback_state"] == "present"
        assert entry["nudges_n"] == 2
        assert entry["nudge_codes"] == ["ctx_stale_run", "lobe_request_theme"]
        assert entry["directives_n"] == 1

    def test_gaps_n_zero_on_clean_fixtures(self, tmp_path):
        _make_full_root(tmp_path)
        entry = build_entry(tmp_path, now=_NOW)
        assert entry["gaps_n"] == 0

    def test_produced_at_from_now(self, tmp_path):
        _make_full_root(tmp_path)
        entry = build_entry(tmp_path, now=_NOW)
        assert entry["produced_at"] == "2026-07-10T12:00:00Z"

    def test_summary_line_content(self, tmp_path):
        _make_full_root(tmp_path)
        entry = build_entry(tmp_path, now=_NOW)
        s = entry["summary"]
        assert "daily run 2026-07-10 (data through 2026-07-10)" in s
        assert "5 lobes (2 stale)" in s
        assert "3 changes" in s
        assert "1 contradictions" in s
        assert "cortex ok" in s
        assert "2 nudges" in s
        assert "1 directives" in s
        assert "(present)" in s

    def test_summary_line_shows_stale_data_date(self, tmp_path):
        """Stale brief → the summary names both the run date and the older data date."""
        _make_full_root(tmp_path, as_of="2026-07-09")
        entry = build_entry(tmp_path, now=_NOW)
        assert "daily run 2026-07-10 (data through 2026-07-09)" in entry["summary"]

    def test_empty_root_never_raises(self, tmp_path):
        """All inputs optional — an empty root degrades, never raises."""
        entry = build_entry(tmp_path, now=_NOW)
        assert entry["run_date"] == "2026-07-10"  # calendar date of now
        assert entry["data_as_of"] == "2026-07-10"  # degrades to run_date
        assert entry["lobes_total"] == 0
        assert entry["lobes_stale"] == 0
        assert entry["what_changed_n"] == 0
        assert entry["cortex_status"] == "unknown"
        assert entry["feedback_state"] == "absent"
        assert entry["nudges_n"] == 0
        assert entry["directives_n"] == 0

    def test_cortex_status_falls_back_to_health(self, tmp_path):
        """When did_the_brain_run has no cortex_status, health.cortex.status is used."""
        _make_full_root(tmp_path)
        bp = tmp_path / "data" / "neuralweb" / "daily_brief.json"
        b = json.loads(bp.read_text())
        b["did_the_brain_run"] = {}
        bp.write_text(json.dumps(b))
        entry = build_entry(tmp_path, now=_NOW)
        assert entry["cortex_status"] == "ok"


# ---------------------------------------------------------------------------
# 2. record_run — keep-first per run_date+workflow
# ---------------------------------------------------------------------------

class TestRecordRunKeepFirst:
    def test_first_run_appends_entry(self, tmp_path):
        _make_full_root(tmp_path)
        res = record_run(tmp_path, now=_NOW)
        assert res["entry"] is not None
        assert res["published"] is True
        rows = (tmp_path / "data" / "neuralweb" / "orchestrator_runlog.jsonl") \
            .read_text().strip().splitlines()
        assert len(rows) == 1

    def test_same_day_twice_keeps_first(self, tmp_path):
        _make_full_root(tmp_path)
        record_run(tmp_path, now=_NOW)
        res2 = record_run(tmp_path, now=_NOW)
        rows = (tmp_path / "data" / "neuralweb" / "orchestrator_runlog.jsonl") \
            .read_text().strip().splitlines()
        assert len(rows) == 1, "keep-first violated: same run_date+workflow duplicated"
        assert "review" not in res2, "no review may fire on a keep-first duplicate"
        assert res2["published"] is True  # site artifact still republished

    def test_different_workflow_same_day_appends(self, tmp_path):
        _make_full_root(tmp_path)
        record_run(tmp_path, workflow="daily", now=_NOW)
        record_run(tmp_path, workflow="asia", now=_NOW)
        rows = [json.loads(r) for r in
                (tmp_path / "data" / "neuralweb" / "orchestrator_runlog.jsonl")
                .read_text().strip().splitlines()]
        assert len(rows) == 2
        assert {r["workflow"] for r in rows} == {"daily", "asia"}

    def test_never_raises_on_empty_root(self, tmp_path):
        res = record_run(tmp_path, now=_NOW)
        # Empty root still composes a degraded entry and publishes
        assert res["entry"] is not None
        assert res["published"] is True

    def test_stale_brief_still_records_next_day(self, tmp_path):
        """REGRESSION (review 2026-07-13): a stale carried-forward brief (as_of =
        yesterday) must NOT make today's run collide with yesterday's entry.
        run_date keys on the calendar day; the stale market date lands in
        data_as_of instead."""
        _make_full_root(tmp_path, as_of="2026-07-09")
        record_run(tmp_path, now=datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc))
        # Next calendar day: the brief did NOT refresh (still as_of=2026-07-09)
        res2 = record_run(tmp_path, now=_NOW)  # 2026-07-10
        rows = [json.loads(r) for r in
                (tmp_path / "data" / "neuralweb" / "orchestrator_runlog.jsonl")
                .read_text().strip().splitlines()]
        assert len(rows) == 2, (
            "stale carried-forward brief collided with yesterday's entry — "
            "today's run went unrecorded"
        )
        assert rows[0]["run_date"] == "2026-07-09"
        assert rows[1]["run_date"] == "2026-07-10"
        assert res2["entry"]["run_date"] == "2026-07-10"
        assert res2["entry"]["data_as_of"] == "2026-07-09"


# ---------------------------------------------------------------------------
# 3. N-run review (config.yml orchestrator.review_every_n_runs=2)
# ---------------------------------------------------------------------------

class TestReviewEveryN:
    def _two_runs(self, tmp_path):
        _make_config(tmp_path, "orchestrator:\n  review_every_n_runs: 2\n")
        _make_full_root(tmp_path, as_of="2026-07-10")
        res1 = record_run(tmp_path, now=_NOW)
        _make_brief(tmp_path, as_of="2026-07-11")
        res2 = record_run(tmp_path, now=datetime(2026, 7, 11, 12, 0, 0, tzinfo=timezone.utc))
        return res1, res2

    def test_no_review_on_first_run(self, tmp_path):
        res1, _ = self._two_runs(tmp_path)
        assert "review" not in res1

    def test_review_fires_on_second_distinct_run(self, tmp_path):
        _, res2 = self._two_runs(tmp_path)
        assert "review" in res2, "review must fire when len(entries) % 2 == 0"
        review = res2["review"]
        assert review["window_runs"] == 2
        assert review["from_run"] == "2026-07-10"
        assert review["to_run"] == "2026-07-11"

    def test_review_completed_block(self, tmp_path):
        _, res2 = self._two_runs(tmp_path)
        completed = res2["review"]["completed"]
        assert completed["runs"] == 2
        assert completed["what_changed_total"] == 6  # 3 + 3
        assert completed["what_changed_kinds"] == {"lobe_refresh": 4, "as_of_advanced": 2}
        assert completed["directives_seen"] == 2  # 1 per run

    def test_review_assessment_trend_strings(self, tmp_path):
        _, res2 = self._two_runs(tmp_path)
        assessment = res2["review"]["assessment"]
        assert isinstance(assessment, list) and len(assessment) == 4
        joined = " | ".join(assessment)
        assert "stale lobes" in joined
        assert "bot nudges" in joined
        assert "cortex status latest: ok" in joined
        assert "operator attention items latest:" in joined
        # deterministic trend vocabulary
        for line in (assessment[0], assessment[3]):
            assert any(t in line for t in ("up", "down", "flat")), (
                f"trend word missing from assessment line: {line!r}"
            )
        # identical fixtures both days → flat trends, zero degraded runs
        assert "flat" in assessment[0]
        assert "degraded runs in window: 0/2" in assessment[2]

    def test_review_row_appended_to_ledger(self, tmp_path):
        self._two_runs(tmp_path)
        rp = tmp_path / "data" / "neuralweb" / "orchestrator_reviews.jsonl"
        assert rp.exists(), "orchestrator_reviews.jsonl not written"
        rows = [json.loads(r) for r in rp.read_text().strip().splitlines()]
        assert len(rows) == 1
        assert rows[0]["window_runs"] == 2

    def test_review_window_codes_deduped(self, tmp_path):
        _, res2 = self._two_runs(tmp_path)
        joined = " ".join(res2["review"]["assessment"])
        # both runs carry the same 2 nudge codes — the window list is deduped
        assert joined.count("ctx_stale_run") == 1

    def test_build_review_empty_entries_no_raise(self):
        review = build_review([], 5, now=_NOW)
        assert review["window_runs"] == 0
        assert review["from_run"] is None
        assert review["to_run"] is None


# ---------------------------------------------------------------------------
# 4. Site artifact (envelope stamp may fail → unstamped fallback still valid)
# ---------------------------------------------------------------------------

class TestSiteArtifact:
    def test_site_artifact_written_valid_json_with_schema(self, tmp_path):
        _make_full_root(tmp_path)
        res = record_run(tmp_path, now=_NOW)
        assert res["published"] is True
        site = tmp_path / "site" / "neuralwebdata" / "orchestrator_runlog.json"
        assert site.exists(), "site artifact not written"
        # Valid JSON with the schema key whether or not the stamp succeeded
        obj = json.loads(site.read_text(encoding="utf-8"))
        assert obj["schema"] == SCHEMA

    def test_site_artifact_entries_and_reviews_shape(self, tmp_path):
        _make_config(tmp_path, "orchestrator:\n  review_every_n_runs: 2\n")
        _make_full_root(tmp_path, as_of="2026-07-10")
        record_run(tmp_path, now=_NOW)
        _make_brief(tmp_path, as_of="2026-07-11")
        record_run(tmp_path, now=datetime(2026, 7, 11, 12, 0, 0, tzinfo=timezone.utc))
        obj = json.loads(
            (tmp_path / "site" / "neuralwebdata" / "orchestrator_runlog.json")
            .read_text(encoding="utf-8"))
        assert isinstance(obj["entries"], list) and len(obj["entries"]) == 2
        assert isinstance(obj["reviews"], list) and len(obj["reviews"]) == 1
        assert obj["n_entries_total"] == 2
        assert obj["as_of"] == "2026-07-11"
        assert obj["review_every_n_runs"] == 2
        assert obj["is_context_only"] is True

    def test_artifact_id_constant(self):
        assert ARTIFACT_ID == "neuralweb-orchestrator-runlog"
        assert SCHEMA == "neuralweb.orchestrator_runlog.v1"


# ---------------------------------------------------------------------------
# 5. _settings — config.yml orchestrator block with bounds
# ---------------------------------------------------------------------------

class TestSettings:
    def test_defaults_without_config(self, tmp_path):
        cfg = _settings(tmp_path)
        assert cfg["review_every_n_runs"] == 5
        assert cfg["site_rows"] == 60
        assert cfg["ingest_bot_feedback"] is True

    def test_valid_overrides_applied(self, tmp_path):
        _make_config(tmp_path,
                     "orchestrator:\n"
                     "  review_every_n_runs: 2\n"
                     "  site_rows: 30\n"
                     "  ingest_bot_feedback: false\n")
        cfg = _settings(tmp_path)
        assert cfg["review_every_n_runs"] == 2
        assert cfg["site_rows"] == 30
        assert cfg["ingest_bot_feedback"] is False

    def test_out_of_bounds_review_n_rejected(self, tmp_path):
        _make_config(tmp_path, "orchestrator:\n  review_every_n_runs: 1\n")
        assert _settings(tmp_path)["review_every_n_runs"] == 5
        _make_config(tmp_path, "orchestrator:\n  review_every_n_runs: 100\n")
        assert _settings(tmp_path)["review_every_n_runs"] == 5

    def test_out_of_bounds_site_rows_rejected(self, tmp_path):
        _make_config(tmp_path, "orchestrator:\n  site_rows: 5\n")
        assert _settings(tmp_path)["site_rows"] == 60
        _make_config(tmp_path, "orchestrator:\n  site_rows: 1000\n")
        assert _settings(tmp_path)["site_rows"] == 60

    def test_malformed_config_degrades_to_defaults(self, tmp_path):
        _make_config(tmp_path, ": not valid yaml : [")
        cfg = _settings(tmp_path)
        assert cfg["review_every_n_runs"] == 5
        assert cfg["site_rows"] == 60


# ---------------------------------------------------------------------------
# 6. load() read surface
# ---------------------------------------------------------------------------

class TestLoad:
    def test_load_empty_root(self, tmp_path):
        out = load(tmp_path)
        assert out["entries"] == []
        assert out["reviews"] == []
        assert out["settings"]["review_every_n_runs"] == 5

    def test_load_after_runs(self, tmp_path):
        _make_config(tmp_path, "orchestrator:\n  review_every_n_runs: 2\n")
        _make_full_root(tmp_path, as_of="2026-07-10")
        record_run(tmp_path, now=_NOW)
        _make_brief(tmp_path, as_of="2026-07-11")
        record_run(tmp_path, now=datetime(2026, 7, 11, 12, 0, 0, tzinfo=timezone.utc))
        out = load(tmp_path)
        assert len(out["entries"]) == 2
        assert len(out["reviews"]) == 1
        assert out["settings"]["review_every_n_runs"] == 2

    def test_load_limit(self, tmp_path):
        _make_full_root(tmp_path, as_of="2026-07-10")
        record_run(tmp_path, now=_NOW)
        _make_brief(tmp_path, as_of="2026-07-11")
        record_run(tmp_path, now=datetime(2026, 7, 11, 12, 0, 0, tzinfo=timezone.utc))
        out = load(tmp_path, limit=1)
        assert len(out["entries"]) == 1
        assert out["entries"][0]["run_date"] == "2026-07-11"
