"""close_pass_slo_report — the evening board's acceptance record (W-L1, PR-C).

WHAT THESE PIN
--------------
The report is the instrument the three-consecutive-session live acceptance will
be graded with, so its failure modes are grading failures, not display bugs:

  * a session with NO stamp must be a ROW, not a gap. Iterating the record's own
    keys steps straight over the evening the board never published and reports a
    streak that never happened — the gate passing on its own missing data.
  * an unmeasured field must print ``—``. A 0 in ``close→cand`` claims the board
    was built the instant the close landed, which is a statement about the
    pipeline that nothing measured.
  * ``sla_met`` is READ from the append-only record and ``product_slo_met`` is
    COMPUTED from the recorded instant. The report is not the authority on the
    gate it reports.
  * a record written before the decomposition existed must still grade. The file
    lives on the VPS across deploys, so the first post-upgrade pass opens a file
    the previous version wrote.

Fixture numbers are the real Fri 2026-08-14 board (published 23:19:14.286019Z =
19:19 ET, 22 admitted of 253 evaluated from a 1,763 universe) plus two synthetic
neighbours that exercise the legacy and never-published shapes.
"""
from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts import close_pass_host_runner as HOST
from scripts import close_pass_slo_report as R
from scripts import freshness_sentinel as FS

#: Saturday 2026-08-15 10:00Z. The last COMPLETED session is Friday 08-14, so
#: the rows walk back 08-14, 08-13, 08-12 — and 08-12 is deliberately unstamped.
NOW = datetime(2026, 8, 15, 10, 0, tzinfo=timezone.utc)

#: The real Friday board, decomposed. 20:15Z close → 23:19Z build → 23:30Z
#: visible: 19:30 ET, so the 18:30 SLA is MISSED and says nothing about where
#: the 3h04m before the build went. That is the gap this report exists to close.
FRIDAY = {
    "first_fresh_at": "2026-08-14T23:30:00+00:00",
    "first_fresh_et": "19:30", "by_et": "18:30", "met": False,
    "latency": {"close_observed_at": "2026-08-14T20:15:00Z",
                "board_generated_at": "2026-08-14T23:19:14.286019Z",
                "first_user_visible_at": "2026-08-14T23:30:00+00:00",
                "close_to_candidate_sec": 11054.3,
                "candidate_to_visible_sec": 645.7,
                "visible_resolution_sec": 1800},
    "coverage": {"universe_n": 1763, "evaluated_n": 253, "admitted_n": 22},
    "provenance": {"close_source": "store",
                   "close_basis": "split_dividend_adjusted",
                   "close_finalized": True},
    "skipped": {"no_todays_bar": 1508, "delisted": 2, "corp_action_today": 3},
}
#: A stamp exactly as the pre-PR-C sentinel wrote it — four keys, no legs.
LEGACY_THURSDAY = {
    "first_fresh_at": "2026-08-13T22:00:00+00:00",
    "first_fresh_et": "18:00", "by_et": "18:30", "met": True,
}

RECORD = {
    "schema": FS.FIRST_FRESH_SCHEMA,
    "updated_at": "2026-08-14T23:30:00+00:00",
    # 2026-08-12 is ABSENT on purpose: the evening the board never published.
    "sessions": {
        "2026-08-13": {R.SURFACE_ID: LEGACY_THURSDAY},
        "2026-08-14": {R.SURFACE_ID: FRIDAY},
    },
}


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    (tmp_path / "first_fresh.json").write_text(json.dumps(RECORD))
    return tmp_path


@pytest.fixture(autouse=True)
def _off_host(monkeypatch, tmp_path_factory):
    """No test may read this machine's REAL close-pass receipts.

    Not hypothetical: the bootstrap leg's first run on the Mac Studio that owns
    ``com.macro.closepass`` graded the live ``~/Library/Application Support``
    receipts and turned four unrelated latency assertions red. A report whose
    default source is host state must be pinned away from it, or the suite
    passes or fails on which machine ran it.
    """
    monkeypatch.setenv("CLOSE_PASS_HOST_SUPPORT",
                       str(tmp_path_factory.mktemp("no-host-receipts")))


def _receipts(tmp_path: Path, *receipts: dict) -> Path:
    """A receipts directory holding exactly the runs given, as the runner writes
    them: one JSON per session, named for the session."""
    runs = tmp_path / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    for receipt in receipts:
        (runs / f"{receipt['session']}.json").write_text(json.dumps(receipt))
    return runs


def _receipt(session: str, **boot) -> dict:
    """One host run receipt at the CURRENT schema, clean unless told otherwise."""
    identity = {"path": "/Users/x/Library/Application Support/macro-closepass/"
                        + HOST.RUNNER_BASENAME,
                "file_sha256": "a" * 64, "mtime": "2026-08-15T19:54:03+00:00",
                "is_installed_copy": True, "installed_path": "/Users/x/…",
                "installed_file_sha256": "a" * 64, "main_file_sha256": "a" * 64,
                "matches_main": True, "commits_behind": 0,
                "detail": "byte-identical to origin/main's scripts/"
                          + HOST.RUNNER_BASENAME}
    identity.update(boot)
    return {"schema": HOST.RECEIPT_SCHEMA, "session": session,
            "outcome": "published", "bootstrap": identity}


def _run(state: Path, **kw) -> tuple[int, str]:
    out = io.StringIO()
    rc = R.run(now=kw.pop("now", NOW), state_dir=state,
               sessions=kw.pop("sessions", 3), as_json=kw.pop("as_json", False),
               with_r2=kw.pop("with_r2", False),
               r2_base=kw.pop("r2_base", "https://example.invalid"),
               out=out, **kw)
    return rc, out.getvalue()


# --------------------------------------------------------------------------- #
# The golden table
# --------------------------------------------------------------------------- #
#: A path that cannot exist, so the golden's bootstrap footer is a fixed string
#: rather than whatever tmpdir the run happened to get. The NOT-MEASURED shape is
#: deliberately the golden one: off the host — which is where CI reads this — the
#: leg has nothing to see, and what it prints then is exactly the line that must
#: never be mistaken for a pass.
GOLDEN_RUNS = Path("/nonexistent/macro-closepass/runs")

GOLDEN = """\
session     close  built  visible  close→cand  cand→vis  eval/univ  admit  source  final  SLA 18:30  SLO 16:15  bootstrap
----------  -----  -----  -------  ----------  --------  ---------  -----  ------  -----  ---------  ---------  ---------
2026-08-14  16:15  19:19  19:30    11,054s     646s      253/1763   22     store   yes    MISSED     MISSED     —
2026-08-13  —      —      18:00    —           —         —          —      —       —      met        MISSED     —
2026-08-12  —      —      —        —           —         —          —      —       —      MISSED     MISSED     —

1/3 sessions met the 18:30 ET SLA; 0/3 met the 16:15 ET product SLO.
'visible' is observed on the sentinel's 30-minute cadence, so cand→vis is known to that resolution, no better.
— = not measured. Times are ET on the session's own day (+1 = the following morning).
bootstrap: NOT MEASURED — no host receipt under /nonexistent/macro-closepass/runs for any reported session. Run this on the host that owns com.macro.closepass, or pass --receipts-dir.
"""


def test_the_acceptance_table_is_the_golden_shape(state_dir):
    rc, text = _run(state_dir, receipts_dir=GOLDEN_RUNS)
    assert text == GOLDEN
    assert rc == 1              # one MISSED session ⇒ the wave is not accepted


def test_the_table_decomposes_the_evening_the_sla_verdict_could_not_explain(
        state_dir):
    """The whole motivation, read off the row: 18:30 MISSED, and now you can see
    that 3h04m of it was gone before the payload existed and 11 minutes after."""
    _, text = _run(state_dir)
    friday = [line for line in text.splitlines() if line.startswith("2026-08-14")][0]
    assert "16:15" in friday and "19:19" in friday and "19:30" in friday
    assert "11,054s" in friday and "646s" in friday
    assert "253/1763" in friday and "MISSED" in friday


# --------------------------------------------------------------------------- #
# A session with no stamp
# --------------------------------------------------------------------------- #
def test_an_unpublished_session_is_a_row_not_a_gap(state_dir):
    """Walking the record's own keys would step over 08-12 entirely and report
    two graded sessions where three were asked for — the gate passing on the
    strength of its own missing data."""
    _, text = _run(state_dir)
    sessions = [line.split()[0] for line in text.splitlines()
                if line.startswith("2026-")]
    assert sessions == ["2026-08-14", "2026-08-13", "2026-08-12"]


def test_an_unstamped_session_grades_MISSED_and_agrees_with_the_sentinel_streak(
        state_dir):
    """No stamp means no pass observed the board live that evening.
    ``freshness_sentinel.sla_streak`` already grades it that way; a report that
    were more lenient would accept a wave the gate itself refuses."""
    rc, text = _run(state_dir, as_json=True)
    rows = {row["session"]: row for row in json.loads(text)["sessions"]}
    assert rows["2026-08-12"]["stamped"] is False
    assert rows["2026-08-12"]["sla_met"] is False
    assert rows["2026-08-12"]["product_slo_met"] is False
    assert rc == 1

    # Same verdict on the same session, from the sentinel's own streak walker.
    streak, streak_rows = FS.sla_streak(RECORD, R.SURFACE_ID, NOW)
    by_session = {row["session"]: row["met"] for row in streak_rows}
    assert by_session["2026-08-12"] is False       # unstamped ⇒ not met, there too
    assert by_session["2026-08-14"] is False and by_session["2026-08-13"] is True
    assert streak == 0          # 08-14 is the newest session and it MISSED


def test_an_empty_record_grades_every_session_missed_rather_than_passing(tmp_path):
    """The failure direction that matters. A report that treated "no data" as
    "no failures" would hand a green acceptance to an estate that published
    nothing at all."""
    rc, text = _run(tmp_path)
    assert rc == 1
    assert "0/3 sessions met" in text
    assert text.count("MISSED") == 6        # 3 sessions × 2 gates


# --------------------------------------------------------------------------- #
# Never a fabricated value
# --------------------------------------------------------------------------- #
def test_every_unmeasured_field_prints_an_em_dash_and_never_a_zero(state_dir):
    """A 0 in close→cand claims the board was built the instant the close
    landed. Nothing measured that, and the difference is the whole point."""
    _, text = _run(state_dir)
    thursday = [line for line in text.splitlines() if line.startswith("2026-08-13")][0]
    assert "0s" not in thursday and " 0 " not in thursday
    assert thursday.count(R.ABSENT) >= 7     # every producer-side column

    _, raw = _run(state_dir, as_json=True)
    row = {r["session"]: r for r in json.loads(raw)["sessions"]}["2026-08-13"]
    for key in ("close_observed_at", "board_generated_at", "close_to_candidate_sec",
                "candidate_to_visible_sec", "evaluated_n", "universe_n",
                "admitted_n", "close_source", "close_finalized"):
        assert row[key] is None, key


def test_a_legacy_stamp_still_grades_its_sla_and_its_visible_instant(state_dir):
    """Version tolerance in the direction that happens: the file on the VPS was
    written by the previous release. ``first_fresh_at`` IS the first-visible
    instant under its older name, so the two columns that need no new fields
    stay gradeable."""
    _, raw = _run(state_dir, as_json=True)
    row = {r["session"]: r for r in json.loads(raw)["sessions"]}["2026-08-13"]
    assert row["sla_met"] is True
    assert row["first_user_visible_at"] == LEGACY_THURSDAY["first_fresh_at"]
    assert row["product_slo_met"] is False        # 18:00 ET is past 16:15
    assert row["visible_resolution_sec"] is None  # honestly unknown, not 1800


# --------------------------------------------------------------------------- #
# The two verdict columns have different owners
# --------------------------------------------------------------------------- #
def test_the_sla_verdict_is_read_from_the_record_and_never_recomputed(tmp_path):
    """The stamp is append-only and "when did this FIRST read fresh" has exactly
    one answer. A report free to recompute it is a report free to disagree with
    the thing being accepted."""
    lying = dict(FRIDAY, met=True)               # record says met; 19:30 ET says no
    (tmp_path / "first_fresh.json").write_text(json.dumps(
        {"sessions": {"2026-08-14": {R.SURFACE_ID: lying}}}))
    _, raw = _run(tmp_path, sessions=1, as_json=True)
    row = json.loads(raw)["sessions"][0]
    assert row["sla_met"] is True                # the record's verdict, verbatim
    assert row["product_slo_met"] is False       # computed here, and disagrees


def test_the_product_slo_is_computed_here_so_the_target_can_move(tmp_path):
    """The 16:15 target is this report's question, not the sentinel's. Moving it
    must not require re-stamping history — which is only true while the column
    is derived from the recorded instant rather than stored beside it."""
    assert R.PRODUCT_SLO_BY_ET == "16:15" and R.SLA_BY_ET == "18:30"
    early = dict(FRIDAY, met=True,
                 latency=dict(FRIDAY["latency"],
                              first_user_visible_at="2026-08-14T20:10:00+00:00"))
    (tmp_path / "first_fresh.json").write_text(json.dumps(
        {"sessions": {"2026-08-14": {R.SURFACE_ID: early}}}))
    rc, raw = _run(tmp_path, sessions=1, as_json=True)
    row = json.loads(raw)["sessions"][0]
    assert row["product_slo_met"] is True         # 16:10 ET beats 16:15
    assert rc == 0                               # both gates met ⇒ accepted


def test_a_next_morning_publish_is_marked_and_never_reads_as_the_earliest_row(
        tmp_path):
    """01:30 ET prints as the best evening in the table unless the row says out
    loud that it is a different day."""
    overnight = dict(FRIDAY, met=False,
                     latency=dict(FRIDAY["latency"],
                                  first_user_visible_at="2026-08-15T05:30:00+00:00"))
    (tmp_path / "first_fresh.json").write_text(json.dumps(
        {"sessions": {"2026-08-14": {R.SURFACE_ID: overnight}}}))
    _, text = _run(tmp_path, sessions=1)
    assert "01:30+1" in text
    _, raw = _run(tmp_path, sessions=1, as_json=True)
    assert json.loads(raw)["sessions"][0]["product_slo_met"] is False


def test_no_tzdata_reports_unknown_rather_than_a_missed_verdict(tmp_path, monkeypatch):
    """A box with no timezone database must not answer in UTC: 20:47Z would read
    as "missed 18:30" on an evening the board made with 100 minutes to spare.
    Unknown is its own word, and it must not share a cell with a failure."""
    monkeypatch.setattr(FS, "_et", lambda stamp: None)
    (tmp_path / "first_fresh.json").write_text(json.dumps(
        {"sessions": {"2026-08-14": {R.SURFACE_ID: dict(FRIDAY, met=None)}}}))
    _, text = _run(tmp_path, sessions=1)
    friday = [line for line in text.splitlines() if line.startswith("2026-08-14")][0]
    assert "MISSED" not in friday
    assert friday.rstrip().endswith(R.ABSENT)
    _, raw = _run(tmp_path, sessions=1, as_json=True)
    assert json.loads(raw)["sessions"][0]["product_slo_met"] is None


# --------------------------------------------------------------------------- #
# --with-r2
# --------------------------------------------------------------------------- #
#: The live board as published, verbatim in the fields this report reads. No
#: close provenance: the sibling lane that adds it is not merged.
LIVE_BOARD = {
    "schema": "us_board_provisional/v1", "as_of": "2026-08-14",
    "built_at": "2026-08-14T23:19:14.286019Z", "lane": "closepass",
    "meta": {"universe_n": 1763, "evaluated_n": 253, "admitted_n": 22,
             "skipped": {"no_todays_bar": 1508, "delisted": 2}},
}


def _board_fetcher(payload=LIVE_BOARD, **kw):
    def fetch(url, *, want_body):
        assert url.endswith(R.BOARD_R2_KEY), url
        assert want_body is True
        return FS.FetchResult(status=200, body=json.dumps(payload), **kw)
    return fetch


def test_with_r2_fills_the_producer_columns_and_never_the_reader_one(tmp_path):
    """The board says when it was BUILT. Only the sentinel can say when a reader
    could first SEE it, and a report that let the producer answer that question
    would grade the gate on the wrong witness."""
    rc, raw = _run(tmp_path, sessions=1, as_json=True, with_r2=True,
                   fetcher=_board_fetcher())
    row = json.loads(raw)["sessions"][0]
    assert row["board_generated_at"] == "2026-08-14T23:19:14.286019Z"
    assert row["evaluated_n"] == 253 and row["universe_n"] == 1763
    assert row["admitted_n"] == 22
    # The reader-side leg is untouched — and so the gate is still unmet.
    assert row["first_user_visible_at"] is None
    assert row["candidate_to_visible_sec"] is None
    assert row["sla_met"] is False and rc == 1
    # …and the row says where its facts came from.
    assert row["facts_from"] == "r2_board"


def test_with_r2_leaves_a_board_with_no_close_stamp_honestly_unmeasured(tmp_path):
    """Today's published board carries no ``close_observed_at``. Reading it must
    not manufacture the leg that field is the input to."""
    _, raw = _run(tmp_path, sessions=1, as_json=True, with_r2=True,
                  fetcher=_board_fetcher())
    row = json.loads(raw)["sessions"][0]
    assert row["close_observed_at"] is None
    assert row["close_to_candidate_sec"] is None
    assert row["close_source"] is None


def test_with_r2_computes_the_close_leg_once_the_sibling_lane_lands(tmp_path):
    payload = dict(LIVE_BOARD, meta=dict(
        LIVE_BOARD["meta"], close_observed_at="2026-08-14T20:15:00Z",
        close_source="store", close_basis="split_dividend_adjusted",
        close_finalized=True))
    _, raw = _run(tmp_path, sessions=1, as_json=True, with_r2=True,
                  fetcher=_board_fetcher(payload))
    row = json.loads(raw)["sessions"][0]
    assert row["close_to_candidate_sec"] == 11054.3
    assert row["close_source"] == "store" and row["close_finalized"] is True


def test_a_stamped_session_is_never_overwritten_by_the_r2_read(state_dir):
    """The record is the observer and the board is the producer. A merge that
    let a re-read board overwrite a stamped session would let the producer
    rewrite the acceptance evidence."""
    other = dict(LIVE_BOARD, built_at="2026-08-14T18:00:00Z",
                 meta=dict(LIVE_BOARD["meta"], admitted_n=999,
                           close_observed_at="2026-08-14T17:00:00Z"))
    _, raw = _run(state_dir, as_json=True, with_r2=True,
                  fetcher=_board_fetcher(other))
    row = {r["session"]: r for r in json.loads(raw)["sessions"]}["2026-08-14"]
    assert row["board_generated_at"] == "2026-08-14T23:19:14.286019Z"
    assert row["admitted_n"] == 22
    assert row["facts_from"] == "sentinel_record"


def test_an_unreadable_r2_board_leaves_columns_unmeasured_and_never_crashes(
        tmp_path, capsys):
    def dead(url, *, want_body):
        return FS.FetchResult(error="URLError: connection refused")

    rc, raw = _run(tmp_path, sessions=1, as_json=True, with_r2=True, fetcher=dead)
    assert rc == 1
    assert json.loads(raw)["sessions"][0]["board_generated_at"] is None
    assert "R2 board unread" in capsys.readouterr().err


def test_a_non_json_r2_body_is_not_a_crash(tmp_path, capsys):
    def html(url, *, want_body):
        return FS.FetchResult(status=200, body="<html>error</html>")

    rc, _ = _run(tmp_path, sessions=1, as_json=True, with_r2=True, fetcher=html)
    assert rc == 1 and "not JSON" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# Exit codes — "I could not measure" never shares one with "it passed"
# --------------------------------------------------------------------------- #
def test_an_all_green_window_exits_zero(tmp_path):
    good = {
        "first_fresh_at": "2026-08-14T20:20:00+00:00",
        "first_fresh_et": "16:20", "by_et": "18:30", "met": True,
        "latency": dict(FRIDAY["latency"],
                        first_user_visible_at="2026-08-14T20:10:00+00:00"),
        "coverage": FRIDAY["coverage"], "provenance": FRIDAY["provenance"],
    }
    (tmp_path / "first_fresh.json").write_text(json.dumps(
        {"sessions": {"2026-08-14": {R.SURFACE_ID: good}}}))
    rc, text = _run(tmp_path, sessions=1)
    assert rc == 0 and "1/1 sessions met the 18:30 ET SLA" in text


def test_zero_requested_sessions_exits_two_rather_than_reporting_success(tmp_path):
    """Nothing to grade is not an acceptance."""
    rc, _ = _run(tmp_path, sessions=0)
    assert rc == 2


def test_no_session_calendar_exits_two_and_prints_no_table(tmp_path, monkeypatch,
                                                           capsys):
    """The calendar is what makes a missing session visible. Without it there is
    no honest report to print, and printing an empty one would read as clean."""
    def broken(*_a, **_kw):
        raise RuntimeError("no calendar")

    monkeypatch.setattr(R, "build_rows", broken)
    rc, text = _run(tmp_path)
    assert rc == 2 and text == ""
    assert "cannot walk the session calendar" in capsys.readouterr().err


def test_the_json_mode_carries_every_column_the_table_shows(state_dir):
    """The machine-readable mode is the same measurement, not a subset — an
    acceptance recorded from --json must be re-derivable into the table."""
    _, raw = _run(state_dir, as_json=True)
    doc = json.loads(raw)
    assert doc["schema"] == "close_pass.slo_report/v2"
    assert doc["sla_by_et"] == "18:30" and doc["product_slo_by_et"] == "16:15"
    assert doc["surface"] == R.SURFACE_ID
    for _, key, _ in R.COLUMNS:
        assert key in doc["sessions"][0], key
    # Raw instants live here; the table renders them as ET clock times.
    assert doc["sessions"][0]["board_generated_at"].endswith("Z")
    # The bootstrap leg is a first-class part of the record, not a printed
    # afterthought: a machine-read acceptance must carry the verdict that can
    # invalidate it, plus the per-session detail behind each cell.
    assert doc["bootstrap_verdict"]["state"] == "unmeasured"
    assert "bootstrap_detail" in doc["sessions"][0]


def test_the_report_grades_the_close_pass_board_and_no_other_surface(state_dir):
    """One surface on purpose. A report that quietly averaged several would
    grade a gate nobody set."""
    assert R.SURFACE_ID == "us_board_provisional"
    assert R.SURFACE_ID in {s["id"] for s in FS.SURFACES}
    mixed = json.loads(json.dumps(RECORD))
    mixed["sessions"]["2026-08-12"] = {"prophet_us": {"met": True, "by_et": "18:30"}}
    (state_dir / "first_fresh.json").write_text(json.dumps(mixed))
    _, raw = _run(state_dir, as_json=True)
    row = {r["session"]: r for r in json.loads(raw)["sessions"]}["2026-08-12"]
    assert row["stamped"] is False and row["sla_met"] is False


# --------------------------------------------------------------------------- #
# The bootstrap leg — "is the code that fires the clock the code we merged?"
#
# WHY THIS IS A GRADING LEG AND NOT A LOG LINE. The launchd clock executes a
# SNAPSHOT frozen into Application Support by the installer, never this
# repository. On 2026-08-18 PR #5862 merged as af416e4a1066 and the host went on
# executing the pre-fix bytes from Aug 15 — visible in nothing the estate owns,
# because the only vintage any receipt compared to anything was the LANE's, which
# is reset to origin/main every run and is therefore always fresh no matter how
# old the file computing it is. A session graded green on plumbing nobody
# deployed is an unmeasured session that happened to work.
# --------------------------------------------------------------------------- #
def _green(session: str) -> dict:
    """A session that met both gates — so the bootstrap leg is the ONLY thing
    that can fail the report, which is what makes these assertions about it."""
    return {"first_fresh_at": f"{session}T20:10:00+00:00",
            "first_fresh_et": "16:10", "by_et": "18:30", "met": True,
            "latency": {"close_observed_at": f"{session}T20:00:00Z",
                        "board_generated_at": f"{session}T20:05:00Z",
                        "first_user_visible_at": f"{session}T20:10:00+00:00",
                        "close_to_candidate_sec": 300.0,
                        "candidate_to_visible_sec": 300.0,
                        "visible_resolution_sec": 1800},
            "coverage": FRIDAY["coverage"], "provenance": FRIDAY["provenance"]}


def _green_state(tmp_path: Path, *sessions: str) -> Path:
    (tmp_path / "first_fresh.json").write_text(json.dumps(
        {"sessions": {s: {R.SURFACE_ID: _green(s)} for s in sessions}}))
    return tmp_path


def test_a_drifted_bootstrap_fails_the_report_even_when_both_gates_are_met(tmp_path):
    """The whole point: two green gates and a red report.

    Fri 08-14's board could hit 16:10 ET on a snapshot three commits stale and
    every existing column would say the wave is acceptable. The exit code has to
    disagree, or the leg is decoration.
    """
    state = _green_state(tmp_path, "2026-08-14")
    runs = _receipts(tmp_path, _receipt("2026-08-14", matches_main=False,
                                        commits_behind=3,
                                        main_file_sha256="b" * 64,
                                        detail="the executing bootstrap is NOT "
                                               "origin/main's scripts/"
                                               + HOST.RUNNER_BASENAME))
    rc, text = _run(state, sessions=1, receipts_dir=runs)
    assert rc == 1, text
    row = [ln for ln in text.splitlines() if ln.startswith("2026-08-14")][0]
    assert "met" in row and "BEHIND 3" in row      # both gates met, plumbing stale
    footer = [ln for ln in text.splitlines() if ln.startswith("BOOTSTRAP DRIFT")]
    assert len(footer) == 1, text
    # The remedy travels with the finding. There is no self-heal by design, so a
    # finding without the command is a finding nobody can act on.
    assert "bash scripts/install_closepass_launchd.sh" in footer[0]
    assert "Merging does not deploy" in footer[0]


def test_a_receipt_written_before_the_check_existed_is_itself_drift(tmp_path):
    """THE MERGED-BUT-NOT-DEPLOYED DETECTOR, and it needs no cooperation from the
    stale bootstrap it is detecting.

    A snapshot old enough to predate this block writes a receipt with no
    ``bootstrap`` key at all — which is not "unknown", it is proof: the code that
    wrote it is older than the code reading it. That is precisely the state the
    host sat in from 2026-08-15 to 2026-08-18 while every instrument read green.
    """
    state = _green_state(tmp_path, "2026-08-14")
    runs = _receipts(tmp_path, {"schema": "close_pass.host_run/v1",
                                "session": "2026-08-14", "outcome": "published",
                                "runner_sha": "cde03d71de97",
                                "code_sha": "af416e4a1066" + "0" * 28})
    rc, text = _run(state, sessions=1, receipts_dir=runs)
    assert rc == 1, text
    assert "OLD-SCHEMA" in text
    assert "bash scripts/install_closepass_launchd.sh" in text


def test_only_the_newest_receipt_grades_but_the_history_still_prints(tmp_path):
    """A healed host goes green on the next session, not five sessions later.

    Grading the whole window would hold the report red for as long as the window
    is wide, which is how a leg gets ignored. The older evening genuinely did run
    a stale bootstrap and that stays visible in its own row — printed, not graded.
    """
    state = _green_state(tmp_path, "2026-08-14", "2026-08-13")
    runs = _receipts(tmp_path,
                     _receipt("2026-08-13", matches_main=False, commits_behind=4),
                     _receipt("2026-08-14"))
    rc, text = _run(state, sessions=2, receipts_dir=runs)
    assert rc == 0, text
    rows = {ln.split()[0]: ln for ln in text.splitlines() if ln.startswith("2026-")}
    assert rows["2026-08-14"].endswith("ok")
    assert "BEHIND 4" in rows["2026-08-13"]        # history is not erased
    assert "matched origin/main on 2026-08-14" in text


def test_a_verdict_the_run_could_not_resolve_is_unverified_and_not_ok(tmp_path):
    """``None`` is not a pass. A run whose fetch failed compared its bootstrap to
    a stale reference and says so; rendering that as ``ok`` would certify exactly
    the nights the detector could not see."""
    state = _green_state(tmp_path, "2026-08-14")
    runs = _receipts(tmp_path, _receipt("2026-08-14", matches_main=None,
                                        commits_behind=None,
                                        detail="byte-identical to the lane's "
                                               "origin/main, but this run's fetch "
                                               "failed (code_stale)"))
    rc, text = _run(state, sessions=1, receipts_dir=runs)
    row = [ln for ln in text.splitlines() if ln.startswith("2026-08-14")][0]
    assert row.endswith(R.BOOT_UNKNOWN) and "ok" not in row.split()[-1]
    assert "UNVERIFIED" in text and "not a clean bill" in text
    # Unknown is not drift either — it must not fail a wave on missing evidence.
    assert rc == 0, text


def test_no_receipt_at_all_says_where_it_looked_instead_of_passing_quietly(tmp_path):
    """Off the host this leg can see nothing, and the line it prints then is the
    one that must never read as a pass. It also names the directory, so the fix
    ("run it on the Studio", "--receipts-dir") is in the output rather than in
    somebody's memory."""
    state = _green_state(tmp_path, "2026-08-14")
    rc, text = _run(state, sessions=1, receipts_dir=tmp_path / "nowhere")
    assert rc == 0                                  # missing evidence ≠ a finding
    assert "bootstrap: NOT MEASURED" in text
    assert str(tmp_path / "nowhere") in text
    assert R.bootstrap_verdict([{"session": "2026-08-14", "bootstrap": R.ABSENT}],
                               tmp_path)["state"] == "unmeasured"


def test_an_unreadable_receipt_is_absent_rather_than_a_crash(tmp_path):
    """This report grades the clock; it must not be stoppable BY the clock. A
    truncated receipt (a run killed mid-write) drops to ``—`` and the latency
    table — which does not depend on it at all — still renders."""
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "2026-08-14.json").write_text("{not json")
    assert R.read_receipts(runs) == {}
    state = _green_state(tmp_path, "2026-08-14")
    rc, text = _run(state, sessions=1, receipts_dir=runs)
    assert rc == 0 and "NOT MEASURED" in text


def test_the_receipts_default_to_the_runners_own_support_dir(monkeypatch, tmp_path):
    """One definition of where receipts live, resolved through the runner itself.

    A second literal here could drift from the writer's, and the report would
    then grade a directory nobody writes to — a detector that is green because it
    is looking in the wrong place.
    """
    monkeypatch.setenv("CLOSE_PASS_HOST_SUPPORT", str(tmp_path / "support"))
    assert R.default_receipts_dir() == tmp_path / "support" / "runs"
    assert R.default_receipts_dir().parent == HOST.support_dir()


def test_the_remedy_is_printed_exactly_once_however_the_finding_arrived(tmp_path):
    """One command, one place to read it.

    The runner's own annotation has to stand alone in a launchd log with no
    footer beneath it, so its ``detail`` carries the remedy. Copying that detail
    into a footer that also states the remedy printed the same command twice in
    one sentence — noise that trains a reader to skim the line that matters.
    """
    state = _green_state(tmp_path, "2026-08-14")
    from_runner = ("the executing bootstrap is NOT origin/main's scripts/"
                   f"{HOST.RUNNER_BASENAME} — 2 commit(s) to that file are not "
                   "deployed; re-run scripts/install_closepass_launchd.sh")
    runs = _receipts(tmp_path, _receipt("2026-08-14", matches_main=False,
                                        commits_behind=2, detail=from_runner))
    rc, text = _run(state, sessions=1, receipts_dir=runs)
    footer = [ln for ln in text.splitlines() if ln.startswith("BOOTSTRAP DRIFT")][0]
    assert rc == 1
    assert footer.count("install_closepass_launchd.sh") == 1, footer

    # ...and when the finding is the report's own (a pre-check receipt), the
    # footer supplies the command the receipt could not have carried.
    runs2 = _receipts(tmp_path / "b", {"schema": "close_pass.host_run/v1",
                                       "session": "2026-08-14"})
    _, text2 = _run(state, sessions=1, receipts_dir=runs2)
    footer2 = [ln for ln in text2.splitlines() if ln.startswith("BOOTSTRAP DRIFT")][0]
    assert footer2.count("install_closepass_launchd.sh") == 1, footer2
