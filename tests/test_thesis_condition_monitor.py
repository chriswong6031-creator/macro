"""Tests for engine/thesis_condition_monitor.py (F11 packet B-F11-1).

All RED-first, no network: every IO function is monkeypatched. Two suites are
marked `needs_full_checkout("data")` because they read the actual committed
`data/cycle_ontology/falsifiers.json` -- they SKIP (not fail) in a sparse
session worktree; opt in with `python3 scripts/worktree_sparse.py add data`.
"""
from __future__ import annotations

import json
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


def _version_row(version=1, title="AAPL breadth thesis", falsifiers=("breadth rolls over",)):
    return {
        "thesis_id": THESIS_ID,
        "user_id": USER_ID,
        "version": version,
        "content": {
            "schema": "mastermind.thesis-content/v1",
            "title": title,
            "statement": "x",
            "catalysts": [],
            "falsifiers": list(falsifiers),
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
    """Stateful fakes (META-CEO RULING M2): `existing_state` grows with every
    row a live `enqueue()` call actually posts, so a SECOND `monitor.run()`
    call genuinely sees what the first one wrote -- unlike a static fixture,
    which would let two runs post the same row twice without ever failing."""
    existing_state = set(existing_ids)

    def fake_read_active_theses(limit):
        return monitor.TypedRead(monitor.READ_OK if theses else monitor.READ_OK_ZERO, theses)

    def fake_read_current_versions(pairs):
        return monitor.TypedRead(
            monitor.READ_OK if versions_rows else monitor.READ_OK_ZERO, versions_rows
        )

    def fake_read_existing_fire_ids(ids):
        rows = [{"fire_event_id": i} for i in ids if i in existing_state]
        return monitor.TypedRead(monitor.READ_OK if rows else monitor.READ_OK_ZERO, rows)

    def fake_enqueue(rows, *, dry_run):
        if dry_run:
            return (0, 0, None)
        posted.extend(rows)
        for row in rows:
            existing_state.add(row["fire_event_id"])
        return (len(rows), 0, None)

    monkeypatch.setattr(monitor, "read_active_theses", fake_read_active_theses)
    monkeypatch.setattr(monitor, "read_current_versions", fake_read_current_versions)
    monkeypatch.setattr(monitor, "read_existing_fire_ids", fake_read_existing_fire_ids)
    monkeypatch.setattr(monitor, "enqueue", fake_enqueue)
    return existing_state


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
    assert posted[0]["alert_id"] == monitor.synthetic_alert_id(THESIS_ID)


def test_replay_enqueues_nothing(monkeypatch):
    _patch_tripwire_view(monkeypatch, [_tripwire_entry()], _latch_state())
    fid = monitor.fire_event_id(
        thesis_id=THESIS_ID, tripwire_id=TRIPWIRE_ID,
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


def test_two_consecutive_runs_enqueue_exactly_once(monkeypatch):
    """META-CEO RULING M2: a genuine end-to-end 'two evaluations -> one row'
    proof, starting from existing_ids=[] (nothing preseeded) -- the first run
    must post, and the SECOND run, seeing what the first one actually wrote
    via the stateful fake, must post nothing."""
    _patch_tripwire_view(monkeypatch, [_tripwire_entry()], _latch_state())
    posted = []
    _patch_reads(
        monkeypatch, theses=[_thesis()], versions_rows=[_version_row()],
        existing_ids=[], posted=posted,
    )
    r1 = monitor.run(dry_run=False)
    r2 = monitor.run(dry_run=False)
    assert r1.enqueued_n == 1
    assert r2.enqueued_n == 0
    assert r2.duplicate_n == 1
    assert len(posted) == 1


def test_sticky_fired_without_new_transition_enqueues_nothing(monkeypatch):
    """Distinct from test_replay_enqueues_nothing: the sticky/already-FIRED
    latch is preseeded as already-notified (existing_ids=[fid]) and TWO
    separate evaluation runs both see it via the stateful fake -- proving the
    sticky window stays silent across repeated nightly evaluations, not just
    a single call (MAJOR-2)."""
    _patch_tripwire_view(monkeypatch, [_tripwire_entry()], _latch_state())
    fid = monitor.fire_event_id(
        thesis_id=THESIS_ID, tripwire_id=TRIPWIRE_ID,
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
        thesis_id=THESIS_ID, tripwire_id=TRIPWIRE_ID,
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
        versions_rows=[
            _version_row(version=1, title="old", falsifiers=("old condition",)),
            _version_row(version=2, title="new", falsifiers=("new condition",)),
        ],
        existing_ids=[],
        posted=posted,
    )
    result = monitor.run(dry_run=False)
    assert result.enqueued_n == 1
    assert posted[0]["payload"]["thesis_version"] == 2
    assert "new condition" in posted[0]["payload"]["summary_plain"]
    assert "old condition" not in posted[0]["payload"]["summary_plain"]


def test_fire_event_id_is_deterministic_and_field_sensitive():
    base = dict(thesis_id=THESIS_ID, tripwire_id=TRIPWIRE_ID,
                tripwire_version=1, fired_on="2026-09-05")
    a = monitor.fire_event_id(**base, thesis_version=1)
    b = monitor.fire_event_id(**base, thesis_version=1)
    assert a == b
    # META-CEO RULING B3 (inverted from round-2): thesis_version is DISPLAY
    # ONLY and must NOT change the id -- a thesis amendment must not re-fire
    # an already-notified (tripwire_id, tripwire_version, fired_on) transition.
    assert monitor.fire_event_id(**base, thesis_version=2) == a
    assert monitor.fire_event_id(**base) == a  # thesis_version omitted entirely
    for key, val in [("thesis_id", "x"), ("tripwire_id", "y"),
                     ("tripwire_version", 2), ("fired_on", "2026-09-06")]:
        variant = dict(base)
        variant[key] = val
        assert monitor.fire_event_id(**variant, thesis_version=1) != a


def test_payload_condition_plain_is_the_users_own_falsifier_verbatim():
    """META-CEO RULING B1 (blocker 1): condition_plain is the USER's own
    falsifier text, byte-verbatim -- never the engine's tripwire `claim`."""
    window = _tripwire_entry()
    payload = monitor.compose_payload(
        thesis={"id": THESIS_ID, "version": 1, "title": "AAPL breadth thesis",
                "falsifiers": ["breadth rolls over decisively."]},
        window=window, subject=("ticker", "AAPL"), evidence_base=monitor.EVIDENCE_BASE,
    )
    assert payload["condition_plain"] == "breadth rolls over decisively."
    assert payload["condition_plain"] != window["claim"]
    assert window["claim"] not in payload["summary_plain"]
    assert payload["engine_window_plain"] == window["claim"]


def test_condition_plain_is_byte_verbatim_no_rstrip():
    """META-CEO RULING MINOR-1: no .rstrip() of any kind -- a trailing period
    or trailing whitespace in the user's own text must survive exactly."""
    window = _tripwire_entry()
    trailing = "breadth rolls over.  "
    assert monitor.user_condition_text([trailing]) == trailing
    payload = monitor.compose_payload(
        thesis={"id": THESIS_ID, "version": 1, "title": "t", "falsifiers": [trailing]},
        window=window, subject=("ticker", "AAPL"), evidence_base=monitor.EVIDENCE_BASE,
    )
    assert trailing in payload["condition_plain"]
    assert payload["condition_plain"] == trailing


def test_condition_plain_joins_multiple_falsifiers_verbatim():
    result = monitor.user_condition_text(["first condition", "second condition"])
    assert result == "first condition; second condition"
    # A single falsifier gets no separator artifact.
    assert monitor.user_condition_text(["only one"]) == "only one"


def test_no_falsifiers_states_so_plainly():
    """META-CEO RULING B1: a thesis with no falsifiers says so plainly rather
    than fabricating or omitting the condition line."""
    window = _tripwire_entry()
    payload = monitor.compose_payload(
        thesis={"id": THESIS_ID, "version": 1, "title": "AAPL breadth thesis", "falsifiers": []},
        window=window, subject=("ticker", "AAPL"), evidence_base=monitor.EVIDENCE_BASE,
    )
    assert payload["condition_plain"] == ""
    assert "Your thesis lists no conditions yet." in payload["summary_plain"]
    assert "你的论点尚未列出任何条件。" in payload["summary_plain_zh"]
    assert payload["condition_plain_zh"] == ""


def test_glance_sentence_matches_the_ruling_template_en_and_zh():
    window = _tripwire_entry(scope="cycle", cycle="long_bonds", tickers=())
    payload = monitor.compose_payload(
        thesis={"id": THESIS_ID, "version": 1, "title": "My rates thesis",
                "falsifiers": ["10y real yield breaks back below 1.5%"]},
        window=window, subject=("cycle", "long_bonds"), evidence_base=monitor.EVIDENCE_BASE,
    )
    assert payload["summary_plain"] == (
        'A window we watch for Long Bonds has closed. Your thesis "My rates thesis" '
        "lists: 10y real yield breaks back below 1.5%."
    )
    assert "Long Bonds" in payload["summary_plain_zh"]
    assert "My rates thesis" in payload["summary_plain_zh"]
    assert "10y real yield breaks back below 1.5%" in payload["summary_plain_zh"]
    assert monitor.TRANSLATION_PENDING_ZH_MARKER in payload["summary_plain_zh"]


def test_payload_never_contains_banned_vocabulary():
    banned = ("falsif", "refut", "证伪", "tripwire", "read_", "fire_event_id",
              "idem_key", "alert_outbox", "::", "outcome=",
              "cuts against", "supports the read")
    glance_keys = ("subject", "subject_zh", "summary_plain", "summary_plain_zh",
                   "condition_plain", "condition_plain_zh", "ticker")
    for direction in ("refutes", "confirms"):
        window = _tripwire_entry()
        window["direction"] = direction
        payload = monitor.compose_payload(
            thesis={"id": THESIS_ID, "version": 1, "title": "AAPL breadth thesis",
                    "falsifiers": ["breadth turns negative"]},
            window=window, subject=("ticker", "AAPL"), evidence_base=monitor.EVIDENCE_BASE,
        )
        haystack = " ".join(str(payload.get(k) or "") for k in glance_keys).lower()
        for term in banned:
            assert term not in haystack, f"banned term {term!r} in {haystack!r}"


def test_payload_never_infers_engine_direction_stance():
    """META-CEO RULING (round-2 blocker, still binding): the payload must
    never glue a register sentence derived from the tripwire's engine-side
    `direction` onto the user's message."""
    banned_exact = (
        "cuts against the read",
        "supports the read",
        "falsifier",
        "refuted",
        "证伪",
    )
    glance_keys = ("subject", "subject_zh", "summary_plain", "summary_plain_zh",
                   "condition_plain", "condition_plain_zh", "ticker")
    for direction in ("refutes", "confirms"):
        window = _tripwire_entry()
        window["direction"] = direction
        payload = monitor.compose_payload(
            thesis={"id": THESIS_ID, "version": 1, "title": "AAPL breadth thesis",
                    "falsifiers": ["breadth turns negative"]},
            window=window, subject=("ticker", "AAPL"), evidence_base=monitor.EVIDENCE_BASE,
        )
        haystack = json.dumps({k: payload.get(k) for k in glance_keys}, ensure_ascii=False).lower()
        for term in banned_exact:
            assert term not in haystack, f"banned term {term!r} in payload {haystack!r}"


def test_subject_names_the_display_not_the_engine_slug():
    window = _tripwire_entry(scope="cycle", cycle="long_bonds", tickers=())
    payload = monitor.compose_payload(
        thesis={"id": THESIS_ID, "version": 1, "title": "My rates thesis", "falsifiers": []},
        window=window, subject=("cycle", "long_bonds"), evidence_base=monitor.EVIDENCE_BASE,
    )
    assert payload["subject"] == "A window we watch for Long Bonds has closed"
    assert "long_bonds" not in payload["subject"]
    assert "subject_zh" in payload and "Long Bonds" in payload["subject_zh"]


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


def test_entry_point_exits_zero_and_warns_with_literal_read_unavailable_token(monkeypatch, capsys):
    """META-CEO RULING MINOR-3: the ::warning line prints the literal typed
    READ_UNAVAILABLE token, not only the error_class."""
    _patch_tripwire_view(monkeypatch, [_tripwire_entry()], _latch_state())
    monkeypatch.setattr(monitor, "SUPABASE_SERVICE_ROLE_KEY", "")
    monkeypatch.delenv("THESIS_MONITOR_ENABLE", raising=False)
    rc = entry.main([])
    assert rc == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    warning_lines = [line for line in lines if line.startswith("::warning")]
    assert warning_lines, "expected a ::warning line at the start of some output line"
    assert any("READ_UNAVAILABLE" in line for line in warning_lines)
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
    # mode. Reads of the committed JSON go through `f_path.read_text()` /
    # `s_path.read_text()`, which take no mode arg.
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
        thesis={"id": THESIS_ID, "version": 1, "title": "rates thesis", "falsifiers": []},
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


def test_alert_id_is_synthetic_uuid_stable_per_thesis():
    """META-CEO RULING M1: alert_id is a deterministic synthetic value derived
    from 'thesis:<thesis_id>' -- `alert_outbox.alert_id` is typed `uuid`
    (terminal PR #513, 0013_alert_runs_outbox.sql), so the literal string is
    rendered through uuid5 rather than stored raw. Stable across repeated
    calls for the same thesis; different for a different thesis."""
    import uuid as uuid_mod
    a = monitor.synthetic_alert_id(THESIS_ID)
    b = monitor.synthetic_alert_id(THESIS_ID)
    assert a == b
    uuid_mod.UUID(a)  # must parse as a real UUID -- would raise otherwise
    assert monitor.synthetic_alert_id("other-thesis") != a


def test_enqueued_row_columns_match_alert_outbox_schema_byte_for_byte(monkeypatch):
    """META-CEO RULING M1: the enqueued row's keys are a subset of
    `public.alert_outbox`'s real column names (terminal PR #513,
    0013_alert_runs_outbox.sql) -- no invented column, no misspelling."""
    _ALERT_OUTBOX_COLUMNS = {
        "id", "user_id", "alert_id", "fire_event_id", "channel", "status",
        "payload", "attempts", "last_error", "deliver_after", "delivered_at",
        "created_at",
    }
    _patch_tripwire_view(monkeypatch, [_tripwire_entry()], _latch_state())
    posted = []
    _patch_reads(
        monkeypatch, theses=[_thesis()], versions_rows=[_version_row()],
        existing_ids=[], posted=posted,
    )
    monitor.run(dry_run=False)
    assert posted, "expected a row to have been enqueued"
    row_keys = set(posted[0].keys())
    assert row_keys <= _ALERT_OUTBOX_COLUMNS, f"unknown column(s): {row_keys - _ALERT_OUTBOX_COLUMNS}"
    assert {"user_id", "alert_id", "fire_event_id", "channel", "status", "payload", "attempts"} <= row_keys


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
    # META-CEO RULING MINOR-4: READ_NO_COVERAGE is actually USED, not dead.
    assert result.read_state == monitor.READ_NO_COVERAGE
    assert result.outcome == "no_coverage"


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
        thesis={"id": THESIS_ID, "version": 1, "title": "t", "falsifiers": []},
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


def test_run_id_differs_across_real_invocations(monkeypatch):
    """META-CEO RULING MINOR-5: run_id must come from a real now_utc, not a
    constant default -- two calls with no explicit --now must differ."""
    _patch_tripwire_view(monkeypatch, [_tripwire_entry()], _latch_state())
    _patch_reads(
        monkeypatch, theses=[_thesis()], versions_rows=[_version_row()],
        existing_ids=[], posted=[],
    )
    ticks = iter(["2026-09-06T00:00:00+00:00", "2026-09-06T00:00:01+00:00"])
    monkeypatch.setattr(monitor, "_now_utc_iso", lambda: next(ticks))
    r1 = monitor.run(dry_run=True)
    r2 = monitor.run(dry_run=True)
    assert r1.run_id != r2.run_id


@pytest.mark.needs_full_checkout("data")
def test_real_committed_falsifiers_join_and_stay_plain_language():
    """Loads the ACTUAL committed data/cycle_ontology/falsifiers.json through
    load_tripwire_view (not a synthetic fixture) and proves a real cycle-scoped
    falsifier CAN join to a Thesis Object shaped per the reviewed migration
    (owner='macro.theme_registry', kind='theme'), and that every composed
    glance-tier field stays plain language with no banned term -- using a
    plain, jargon-free USER falsifier (the engine's own real claim text is
    exercised only through engine_window_plain, never the glance tier)."""
    entries, _state, error_class = monitor.load_tripwire_view()
    assert error_class is None
    assert len(entries) > 0, "expected the committed falsifiers corpus to be non-empty"
    cycles_covered = 0
    for e in entries:
        cycle = e.get("cycle")
        if not cycle:
            continue
        subject = ("cycle", str(cycle).lower())
        fake_window = dict(e)
        fake_window["fired_on"] = "2026-09-05"
        payload = monitor.compose_payload(
            thesis={"id": THESIS_ID, "version": 1, "title": "watch",
                    "falsifiers": ["a plain condition with no jargon"]},
            window=fake_window, subject=subject, evidence_base=monitor.EVIDENCE_BASE,
        )
        cycles_covered += 1
        haystack = " ".join(
            str(payload.get(k, "")) for k in
            ("subject", "subject_zh", "summary_plain", "summary_plain_zh",
             "condition_plain", "condition_plain_zh")
        ).lower()
        for term in monitor._BANNED_TERMS + ("cuts against", "supports the read"):
            assert term not in haystack, f"banned term {term!r} in real-data payload {haystack!r}"
        assert str(cycle) not in payload["subject"]  # no raw slug
        # engine_window_plain still carries the real claim -- proves the
        # corpus actually flowed through, not a vacuous pass.
        assert payload["engine_window_plain"] == e.get("claim", "")
    assert cycles_covered > 0, "expected at least one real falsifier scoped to a cycle"


# META-CEO RULING M3: the raw engine claim (stats, tildes, abbreviations like
# SOX/DRAM/ASP) is Tier-2 detail only -- extend the banned-vocab test with a
# digit+tilde pattern and a real abbreviation list, run against the real corpus.
_DIGIT_TILDE_RE = re.compile(r"~[\d,]+")
_JARGON_ABBREVIATIONS = ("SOX", "DRAM", "ASP")


@pytest.mark.needs_full_checkout("data")
def test_real_corpus_engine_jargon_never_leaks_into_glance_tier():
    entries, _state, error_class = monitor.load_tripwire_view()
    assert error_class is None
    assert len(entries) > 0
    checked_tilde = 0
    checked_abbrev = 0
    for e in entries:
        cycle = e.get("cycle")
        if not cycle:
            continue
        subject = ("cycle", str(cycle).lower())
        fake_window = dict(e)
        fake_window["fired_on"] = "2026-09-05"
        payload = monitor.compose_payload(
            thesis={"id": THESIS_ID, "version": 1, "title": "watch",
                    "falsifiers": ["a plain condition with no jargon"]},
            window=fake_window, subject=subject, evidence_base=monitor.EVIDENCE_BASE,
        )
        glance = " ".join(
            str(payload.get(k, "")) for k in
            ("subject", "subject_zh", "summary_plain", "summary_plain_zh",
             "condition_plain", "condition_plain_zh")
        )
        claim = e.get("claim", "")
        if _DIGIT_TILDE_RE.search(claim):
            checked_tilde += 1
            assert not _DIGIT_TILDE_RE.search(glance), (
                f"digit+tilde engine jargon leaked into glance tier for {e.get('id')}"
            )
        for abbrev in _JARGON_ABBREVIATIONS:
            if abbrev in claim:
                checked_abbrev += 1
                assert abbrev not in glance, (
                    f"abbreviation {abbrev!r} leaked into glance tier for {e.get('id')}"
                )
        # Tier-2 field DOES carry the raw claim -- proves this isn't vacuous.
        assert payload["engine_window_plain"] == claim
    assert checked_tilde > 0, "expected the real corpus to exercise a digit+tilde claim"
    assert checked_abbrev > 0, "expected the real corpus to exercise an abbreviation"
