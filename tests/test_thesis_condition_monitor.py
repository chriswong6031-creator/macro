"""Tests for engine/thesis_condition_monitor.py (F11 packet B-F11-1).

All RED-first, no network: every IO function is monkeypatched.
"""
from __future__ import annotations

import json
import os
import re

import pytest

from engine import thesis_condition_monitor as monitor
from engine import falsifier_tripwires as ft
from scripts import run_thesis_condition_monitor as entry


THESIS_ID = "11111111-1111-1111-1111-111111111111"
USER_ID = "22222222-2222-2222-2222-222222222222"
TRIPWIRE_ID = "tw_aapl_breadth"


def _thesis(version=1, subject_ref=None):
    return {
        "id": THESIS_ID,
        "user_id": USER_ID,
        "current_version": version,
        "subject_ref": subject_ref
        or {
            "schema": "mastermind.thesis-subject-ref/v1",
            "kind": "issuer",
            "owner": "data_os.security_master",
            "key": "AAPL",
            "identity_state": "resolved",
            "listing": {"symbol": "AAPL", "mic": "XNAS", "security_id": "sec1"},
            "display": "Apple Inc.",
        },
    }


def _version_row(version=1, title="AAPL breadth thesis"):
    return {
        "thesis_id": THESIS_ID,
        "user_id": USER_ID,
        "version": version,
        "content": {
            "schema": "mastermind.thesis-content/v1",
            "title": title,
            "statement": "x",
            "catalysts": [],
            "falsifiers": ["breadth rolls over"],
            "risks": [],
            "horizon": "6m",
            "effective_at": "2026-01-01T00:00:00Z",
            "revision_note": "",
        },
    }


def _tripwire_entry(tw_version=1, scope="ticker", tickers=("AAPL",), cycle=None):
    return {
        "id": TRIPWIRE_ID,
        "version": tw_version,
        "cycle": cycle,
        "scope": scope,
        "tickers": list(tickers),
        "claim": "Breadth confirms the cyclical low",
        "direction": "refutes",
        "coverage": "full",
    }


def _latch_state(tw_version=1, state="FIRED", fired_on="2026-09-05", latched=True):
    return {TRIPWIRE_ID: {"version": tw_version, "state": state, "fired_on": fired_on, "latched": latched}}


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch):
    monkeypatch.setattr(monitor, "SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setattr(monitor, "SUPABASE_URL", "https://example.supabase.co")
    yield


def _patch_reads(monkeypatch, *, theses, versions_rows, existing_ids, posted):
    def fake_read_active_theses(limit):
        return monitor.TypedRead(monitor.READ_OK if theses else monitor.READ_OK_ZERO, theses)

    def fake_read_current_versions(pairs):
        return monitor.TypedRead(
            monitor.READ_OK if versions_rows else monitor.READ_OK_ZERO, versions_rows
        )

    def fake_read_existing_fire_ids(ids):
        rows = [{"fire_event_id": i} for i in existing_ids]
        return monitor.TypedRead(monitor.READ_OK if rows else monitor.READ_OK_ZERO, rows)

    def fake_enqueue(rows, *, dry_run):
        if dry_run:
            return (0, 0, None)
        posted.extend(rows)
        return (len(rows), 0, None)

    monkeypatch.setattr(monitor, "read_active_theses", fake_read_active_theses)
    monkeypatch.setattr(monitor, "read_current_versions", fake_read_current_versions)
    monkeypatch.setattr(monitor, "read_existing_fire_ids", fake_read_existing_fire_ids)
    monkeypatch.setattr(monitor, "enqueue", fake_enqueue)


def _patch_tripwire_view(monkeypatch, entries, latch_state):
    monkeypatch.setattr(monitor, "load_tripwire_view", lambda: (entries, latch_state, None))


def test_new_fire_enqueues_exactly_one_row(monkeypatch):
    _patch_tripwire_view(monkeypatch, [_tripwire_entry()], _latch_state())
    posted = []
    _patch_reads(
        monkeypatch,
        theses=[_thesis()],
        versions_rows=[_version_row()],
        existing_ids=[],
        posted=posted,
    )
    result = monitor.run(dry_run=False)
    assert result.enqueued_n == 1
    assert len(posted) == 1
    assert posted[0]["status"] == "pending"
    assert posted[0]["channel"] == "email"


def test_replay_enqueues_nothing(monkeypatch):
    _patch_tripwire_view(monkeypatch, [_tripwire_entry()], _latch_state())
    fid = monitor.fire_event_id(
        thesis_id=THESIS_ID, thesis_version=1, tripwire_id=TRIPWIRE_ID,
        tripwire_version=1, fired_on="2026-09-05",
    )
    posted = []
    _patch_reads(
        monkeypatch, theses=[_thesis()], versions_rows=[_version_row()],
        existing_ids=[fid], posted=posted,
    )
    result = monitor.run(dry_run=False)
    assert result.enqueued_n == 0
    assert result.duplicate_n == 1
    assert posted == []


def test_sticky_fired_without_new_transition_enqueues_nothing(monkeypatch):
    _patch_tripwire_view(monkeypatch, [_tripwire_entry()], _latch_state())
    fid = monitor.fire_event_id(
        thesis_id=THESIS_ID, thesis_version=1, tripwire_id=TRIPWIRE_ID,
        tripwire_version=1, fired_on="2026-09-05",
    )
    posted = []
    _patch_reads(
        monkeypatch, theses=[_thesis()], versions_rows=[_version_row()],
        existing_ids=[fid], posted=posted,
    )
    r1 = monitor.run(dry_run=False)
    r2 = monitor.run(dry_run=False)
    assert r1.duplicate_n == 1 and r2.duplicate_n == 1
    assert posted == []


def test_version_bump_mints_a_new_fire_event_id(monkeypatch):
    _patch_tripwire_view(monkeypatch, [_tripwire_entry(tw_version=2)], _latch_state(tw_version=2))
    old_fid = monitor.fire_event_id(
        thesis_id=THESIS_ID, thesis_version=1, tripwire_id=TRIPWIRE_ID,
        tripwire_version=1, fired_on="2026-09-05",
    )
    posted = []
    _patch_reads(
        monkeypatch, theses=[_thesis()], versions_rows=[_version_row()],
        existing_ids=[old_fid], posted=posted,
    )
    result = monitor.run(dry_run=False)
    assert result.enqueued_n == 1
    assert posted[0]["fire_event_id"] != old_fid


def test_only_the_newest_thesis_revision_is_notified(monkeypatch):
    _patch_tripwire_view(monkeypatch, [_tripwire_entry()], _latch_state())
    posted = []
    _patch_reads(
        monkeypatch,
        theses=[_thesis(version=2)],
        versions_rows=[_version_row(version=1, title="old"), _version_row(version=2, title="new")],
        existing_ids=[],
        posted=posted,
    )
    result = monitor.run(dry_run=False)
    assert result.enqueued_n == 1
    assert posted[0]["payload"]["thesis_version"] == 2
    assert "new" in posted[0]["payload"]["summary_plain"]
    assert "old" not in posted[0]["payload"]["summary_plain"]


def test_fire_event_id_is_deterministic_and_field_sensitive():
    base = dict(thesis_id=THESIS_ID, thesis_version=1, tripwire_id=TRIPWIRE_ID,
                tripwire_version=1, fired_on="2026-09-05")
    a = monitor.fire_event_id(**base)
    b = monitor.fire_event_id(**base)
    assert a == b
    for key, val in [("thesis_id", "x"), ("thesis_version", 2), ("tripwire_id", "y"),
                     ("tripwire_version", 2), ("fired_on", "2026-09-06")]:
        variant = dict(base)
        variant[key] = val
        assert monitor.fire_event_id(**variant) != a


def test_payload_is_plain_language():
    window = _tripwire_entry()
    payload = monitor.compose_payload(
        thesis={"id": THESIS_ID, "version": 1, "title": "AAPL breadth thesis"},
        window=window, subject=("ticker", "AAPL"), evidence_base=monitor.EVIDENCE_BASE,
    )
    expected = (
        "The window you were watching for “AAPL breadth thesis” has closed: "
        f"{monitor.plain_condition(window)}. What to look at: "
        f"{monitor.EVIDENCE_BASE}/cycle.html"
    )
    assert payload["summary_plain"] == expected


def test_payload_never_contains_banned_vocabulary():
    banned = ("falsif", "refut", "证伪", "tripwire", "read_", "fire_event_id",
              "idem_key", "alert_outbox", "::", "outcome=")
    for direction in ("refutes", "confirms"):
        window = _tripwire_entry()
        window["direction"] = direction
        payload = monitor.compose_payload(
            thesis={"id": THESIS_ID, "version": 1, "title": "AAPL breadth thesis"},
            window=window, subject=("ticker", "AAPL"), evidence_base=monitor.EVIDENCE_BASE,
        )
        haystack = " ".join([
            payload["subject"], payload["summary_plain"], payload["condition_plain"],
            payload["ticker"],
        ]).lower()
        for term in banned:
            assert term not in haystack, f"banned term {term!r} in {haystack!r}"


def test_tables_absent_yields_read_unavailable_and_zero_enqueue(monkeypatch):
    _patch_tripwire_view(monkeypatch, [_tripwire_entry()], _latch_state())

    def fake_read_active_theses(limit):
        return monitor.TypedRead(monitor.READ_UNAVAILABLE, None, "table_absent")

    monkeypatch.setattr(monitor, "read_active_theses", fake_read_active_theses)
    result = monitor.run(dry_run=False)
    assert result.read_state == monitor.READ_UNAVAILABLE
    assert result.error_class == "table_absent"
    assert result.enqueued_n == 0


def test_missing_credentials_is_typed_not_a_crash(monkeypatch):
    monkeypatch.setattr(monitor, "SUPABASE_SERVICE_ROLE_KEY", "")
    _patch_tripwire_view(monkeypatch, [_tripwire_entry()], _latch_state())
    result = monitor.run(dry_run=False)
    assert result.outcome == "unavailable"
    assert result.error_class == "no_credentials"


def test_entry_point_exits_zero_and_warns_at_line_start(monkeypatch, capsys):
    _patch_tripwire_view(monkeypatch, [_tripwire_entry()], _latch_state())
    monkeypatch.setattr(monitor, "SUPABASE_SERVICE_ROLE_KEY", "")
    monkeypatch.delenv("THESIS_MONITOR_ENABLE", raising=False)
    rc = entry.main([])
    assert rc == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert any(line.startswith("::warning") for line in lines)
    assert any(line.startswith("thesis-monitor: outcome=") for line in lines)


def test_dormant_by_default_forces_dry_run(monkeypatch):
    monkeypatch.delenv("THESIS_MONITOR_ENABLE", raising=False)
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return monitor.MonitorResult(
            outcome="ok", read_state=monitor.READ_OK, error_class=None,
            evaluated_n=0, matched_n=0, enqueued_n=0, duplicate_n=0,
            no_coverage_n=0, unmappable_n=0, run_id="x",
        )

    monkeypatch.setattr(monitor, "run", fake_run)
    entry.main([])
    assert captured["dry_run"] is True


def test_no_data_or_site_writes():
    src = open(monitor.__file__, encoding="utf-8").read()
    assert "write_text(" not in src
    assert "to_parquet(" not in src
    assert "to_csv(" not in src
    # No local file WRITE anywhere -- forbid any open()/Path call in write/append
    # mode. (The prior assertion `"open(" not in src or "open(req" in src` was
    # tautological: `urllib.request.urlopen(req, ...)` already contains the
    # substring "open(req", so the guard could never fail regardless of what
    # else the module did.) Reads of the committed JSON go through
    # `f_path.read_text()` / `s_path.read_text()`, which take no mode arg.
    write_mode_pattern = re.compile(r"""open\([^)]*['"][wax]""")
    assert not write_mode_pattern.search(src), "found a write/append-mode open() call"
    assert ".write_bytes(" not in src


def test_corrupt_falsifiers_json_is_typed_read_unavailable(monkeypatch, tmp_path):
    bad = tmp_path / "falsifiers.json"
    bad.write_text("{not json")
    monkeypatch.setattr(monitor.config, "ROOT", tmp_path)
    monkeypatch.setattr(monitor.ft, "_FALSIFIERS_JSON", "falsifiers.json")
    result = monitor.run(dry_run=False)
    assert result.read_state == monitor.READ_UNAVAILABLE
    assert result.error_class == "corrupt_falsifiers_json"
    assert result.enqueued_n == 0


def test_missing_falsifiers_file_is_ok_zero_not_an_error(monkeypatch, tmp_path):
    # A file that has simply never been rendered yet is a normal empty state,
    # not an error -- must not collapse identically with a CORRUPT file.
    monkeypatch.setattr(monitor.config, "ROOT", tmp_path)
    monkeypatch.setattr(monitor.ft, "_FALSIFIERS_JSON", "does_not_exist.json")
    entries, state, error_class = monitor.load_tripwire_view()
    assert error_class is None
    assert entries == []


def test_window_fired_before_thesis_creation_does_not_backfire(monkeypatch):
    _patch_tripwire_view(monkeypatch, [_tripwire_entry()], _latch_state(fired_on="2026-01-01"))
    posted = []
    thesis = _thesis()
    thesis["created_at"] = "2026-06-01T00:00:00Z"  # created AFTER the historical fire
    _patch_reads(
        monkeypatch, theses=[thesis], versions_rows=[_version_row()],
        existing_ids=[], posted=posted,
    )
    result = monitor.run(dry_run=False)
    assert result.enqueued_n == 0
    assert posted == []


def test_window_fired_after_thesis_creation_still_enqueues(monkeypatch):
    _patch_tripwire_view(monkeypatch, [_tripwire_entry()], _latch_state(fired_on="2026-09-05"))
    posted = []
    thesis = _thesis()
    thesis["created_at"] = "2026-01-01T00:00:00Z"  # created BEFORE the fire
    _patch_reads(
        monkeypatch, theses=[thesis], versions_rows=[_version_row()],
        existing_ids=[], posted=posted,
    )
    result = monitor.run(dry_run=False)
    assert result.enqueued_n == 1


def test_display_never_uses_a_raw_cycle_slug():
    window = _tripwire_entry(scope="cycle", cycle="long_bonds", tickers=())
    payload = monitor.compose_payload(
        thesis={"id": THESIS_ID, "version": 1, "title": "rates thesis"},
        window=window, subject=("cycle", "long_bonds"), evidence_base=monitor.EVIDENCE_BASE,
    )
    assert "long_bonds" not in payload["subject"]
    assert "long_bonds" not in payload["summary_plain"]
    # A cycle subject's display label is not a tradable ticker symbol.
    assert payload["ticker"] is None


def test_dry_run_reports_planned_not_enqueued(monkeypatch):
    _patch_tripwire_view(monkeypatch, [_tripwire_entry()], _latch_state())
    _patch_reads(
        monkeypatch, theses=[_thesis()], versions_rows=[_version_row()],
        existing_ids=[], posted=[],
    )
    result = monitor.run(dry_run=True)
    assert result.enqueued_n == 0
    assert result.planned_n == 1


def test_real_committed_falsifiers_join_and_stay_plain_language():
    """Loads the ACTUAL committed data/cycle_ontology/falsifiers.json through
    load_tripwire_view (not a synthetic fixture) and proves a real cycle-scoped
    falsifier CAN join to a Thesis Object shaped per the reviewed migration
    (owner='macro.theme_registry', kind='theme'), and that every real claim +
    claim_zh in the corpus composes into plain language with no banned term."""
    entries, _state, error_class = monitor.load_tripwire_view()
    assert error_class is None
    assert len(entries) > 0, "expected the committed falsifiers corpus to be non-empty"
    zh_covered = 0
    for e in entries:
        cycle = e.get("cycle")
        if not cycle:
            continue
        subject = ("cycle", str(cycle).lower())
        fake_window = dict(e)
        fake_window["fired_on"] = "2026-09-05"
        payload = monitor.compose_payload(
            thesis={"id": THESIS_ID, "version": 1, "title": "watch"},
            window=fake_window, subject=subject, evidence_base=monitor.EVIDENCE_BASE,
        )
        haystack = " ".join(
            str(payload.get(k, "")) for k in
            ("subject", "summary_plain", "condition_plain", "summary_plain_zh", "condition_plain_zh")
        ).lower()
        for term in monitor._BANNED_TERMS:
            assert term not in haystack, f"banned term {term!r} in real-data payload {haystack!r}"
        assert str(cycle) not in payload["subject"]  # no raw slug
        if e.get("claim_zh"):
            zh_covered += 1
            assert payload.get("summary_plain_zh"), "expected a zh variant when claim_zh is present"
    assert zh_covered > 0, "expected at least one real falsifier to carry claim_zh"


def test_no_coverage_subject_is_disclosed_not_fabricated(monkeypatch):
    _patch_tripwire_view(monkeypatch, [_tripwire_entry(tickers=("MSFT",))], _latch_state())
    posted = []
    _patch_reads(
        monkeypatch, theses=[_thesis()], versions_rows=[_version_row()],
        existing_ids=[], posted=posted,
    )
    result = monitor.run(dry_run=False)
    assert result.no_coverage_n == 1
    assert result.enqueued_n == 0
    assert posted == []


def test_unmappable_subject_ref_is_counted_not_guessed(monkeypatch):
    _patch_tripwire_view(monkeypatch, [_tripwire_entry()], _latch_state())
    posted = []
    bad_thesis = _thesis(subject_ref={"kind": "unknown", "owner": "nowhere"})
    _patch_reads(
        monkeypatch, theses=[bad_thesis], versions_rows=[_version_row()],
        existing_ids=[], posted=posted,
    )
    result = monitor.run(dry_run=False)
    assert result.unmappable_n == 1
    assert result.enqueued_n == 0


def test_ticker_and_cycle_matching():
    ticker_window = _tripwire_entry(scope="ticker", tickers=("AAPL",))
    cycle_window = _tripwire_entry(scope="cycle", cycle="gold_real_rate", tickers=())
    assert monitor.match_windows(("ticker", "AAPL"), [ticker_window, cycle_window]) == [ticker_window]
    assert monitor.match_windows(("cycle", "gold_real_rate"), [ticker_window, cycle_window]) == [cycle_window]
    assert monitor.match_windows(("ticker", "AAPL"), [cycle_window]) == []


def test_schema_mismatch_on_insert_is_typed(monkeypatch):
    _patch_tripwire_view(monkeypatch, [_tripwire_entry()], _latch_state())

    def fake_enqueue(rows, *, dry_run):
        return (0, 0, "schema_mismatch")

    _patch_reads(
        monkeypatch, theses=[_thesis()], versions_rows=[_version_row()],
        existing_ids=[], posted=[],
    )
    monkeypatch.setattr(monitor, "enqueue", fake_enqueue)
    result = monitor.run(dry_run=False)
    assert result.outcome == "unavailable"
    assert result.error_class == "schema_mismatch"


def test_evidence_url_is_absolute_on_site_host():
    payload = monitor.compose_payload(
        thesis={"id": THESIS_ID, "version": 1, "title": "t"},
        window=_tripwire_entry(), subject=("ticker", "AAPL"), evidence_base=monitor.EVIDENCE_BASE,
    )
    assert payload["evidence_url"].startswith("https://www.mastermind-x.com/")


def test_tripwire_path_constants_exist():
    assert hasattr(ft, "_STATE_JSON")
    assert hasattr(ft, "_FALSIFIERS_JSON")


def test_read_state_literals_match_the_f08_vocabulary():
    assert monitor.READ_OK == "READ_OK"
    assert monitor.READ_OK_ZERO == "READ_OK_ZERO"
    assert monitor.READ_NO_COVERAGE == "READ_NO_COVERAGE"
    assert monitor.READ_UNAVAILABLE == "READ_UNAVAILABLE"
