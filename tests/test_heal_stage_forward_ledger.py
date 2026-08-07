"""Tests for scripts/heal_stage_forward_ledger.py — the data-plane session
restamp + duplicate quarantine heal (forward-ledger calendar-asof audit
2026-08-05).

Pins the executable spec:

  row date in that ticker's own frame index      -> HONEST, untouched
  otherwise                                     -> restamp to the latest index
                                                   date <= the stamp
  restamp onto an occupied (ticker, session)    -> QUARANTINE (never delete);
                                                   honest rows win, then
                                                   first-writer by file order
  no readable frame / no bar at-or-before stamp -> FAIL-CLOSED, nothing written

Every date is a PINNED weekday literal (no wall clock anywhere): the rule is
evidence arithmetic and must grade identically on any run day. The calendar
shape used throughout:

  2026-07-30 Thu   2026-07-31 Fri   2026-08-01 Sat   2026-08-02 Sun
  2026-08-03 Mon   2026-08-04 Tue

with a store frozen at Friday 2026-07-31 — the audited collection outage.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.heal_stage_forward_ledger import heal

# Pinned calendar (see module docstring).
THU = "2026-07-30"
FRI = "2026-07-31"
SAT = "2026-08-01"
SUN = "2026-08-02"
MON = "2026-08-03"
TUE = "2026-08-04"

#: A frame frozen at Friday — Sat/Sun/Mon/Tue were never sessions in it.
FROZEN_AT_FRIDAY = {"2026-07-28", "2026-07-29", THU, FRI}


def _row(date: str, ticker: str, **over) -> dict:
    row = {
        "date": date,
        "ticker": ticker,
        "sga_score": 64,
        "gate_tier": None,
        "weeks_in_stage": 7,
        "earnings_present": False,
        "sentiment": None,
        "performance": None,
    }
    row.update(over)
    return row


def _write_ledger(root: Path, rows: list[dict]) -> Path:
    p = root / "data" / "stage_analysis" / "forward_ledger.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


def _reader(index: dict[str, set[str]]):
    """Injectable frame reader over a pinned {ticker: sessions} fixture."""
    def _read(root: Path, ticker: str) -> set[str]:
        return set(index.get(ticker, set()))
    return _read


def _main_rows(root: Path) -> list[dict]:
    p = root / "data" / "stage_analysis" / "forward_ledger.jsonl"
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


def _quar_rows(root: Path) -> list[dict]:
    p = root / "data" / "stage_analysis" / "forward_ledger_quarantine.jsonl"
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


# ── the standard fixture: one honest run, then four re-descriptions ───────────

def _fixture_rows() -> list[dict]:
    return [
        _row(THU, "NVDA"),   # honest — Thursday is a session in the frame
        _row(FRI, "NVDA"),   # honest — Friday is a session in the frame
        _row(SAT, "NVDA"),   # Saturday stamp -> Friday -> already taken -> quar
        _row(SUN, "AVGO"),   # Sunday stamp -> Friday -> free -> RESTAMPED
        _row(MON, "AVGO"),   # Monday stamp (store frozen) -> Friday -> quar
        _row(TUE, "COST"),   # Tuesday stamp -> Friday -> free -> RESTAMPED
    ]


def _fixture_index() -> dict[str, set[str]]:
    return {t: set(FROZEN_AT_FRIDAY) for t in ("NVDA", "AVGO", "COST")}


# ── honest rows ───────────────────────────────────────────────────────────────

def test_honest_rows_are_untouched(tmp_path):
    _write_ledger(tmp_path, _fixture_rows())
    summary = heal(tmp_path, frame_sessions=_reader(_fixture_index()))

    assert summary["n_honest"] == 2
    honest = [r for r in _main_rows(tmp_path)
              if r["ticker"] == "NVDA" and r["date"] in (THU, FRI)]
    assert len(honest) == 2
    for r in honest:
        assert "session_inferred" not in r
        assert "original_date" not in r
        assert "session_source" not in r
        assert r["sga_score"] == 64        # payload never rewritten


# ── restamping ────────────────────────────────────────────────────────────────

def test_mislabeled_rows_are_restamped_to_the_true_session(tmp_path):
    _write_ledger(tmp_path, _fixture_rows())
    summary = heal(tmp_path, frame_sessions=_reader(_fixture_index()))

    assert summary["n_restamped"] == 2
    by_ticker = {r["ticker"]: r for r in _main_rows(tmp_path)
                 if r.get("session_inferred")}
    assert set(by_ticker) == {"AVGO", "COST"}
    assert by_ticker["AVGO"]["date"] == FRI
    assert by_ticker["AVGO"]["original_date"] == SUN
    assert by_ticker["COST"]["date"] == FRI
    assert by_ticker["COST"]["original_date"] == TUE
    for r in by_ticker.values():
        assert r["session_inferred"] is True
        assert r["session_source"] == "ticker_frame"


def test_restamp_walks_back_to_the_latest_bar_at_or_before_the_stamp(tmp_path):
    """A Tuesday stamp against a Thursday-frozen frame lands on Thursday, not
    on the newest bar of some other ticker."""
    _write_ledger(tmp_path, [_row(TUE, "SLOW")])
    heal(tmp_path, frame_sessions=_reader({"SLOW": {"2026-07-29", THU}}))
    assert _main_rows(tmp_path)[0]["date"] == THU


# ── quarantine ────────────────────────────────────────────────────────────────

def test_duplicate_restamps_are_quarantined_with_reason_and_pointer(tmp_path):
    _write_ledger(tmp_path, _fixture_rows())
    summary = heal(tmp_path, frame_sessions=_reader(_fixture_index()))

    assert summary["n_quarantined_now"] == 2
    quar = _quar_rows(tmp_path)
    assert {(q["ticker"], q["date"]) for q in quar} == {("NVDA", SAT), ("AVGO", MON)}
    for q in quar:
        assert "duplicate re-description" in q["quarantine_reason"]
        assert q["quarantined_kept_row"] == {"date": FRI, "ticker": q["ticker"]}
        assert q["quarantined_at"]
    # Nothing is deleted — the quarantined rows left main but still exist.
    assert {(r["ticker"], r["date"]) for r in _main_rows(tmp_path)} \
        .isdisjoint({("NVDA", SAT), ("AVGO", MON)})


def test_honest_row_wins_the_slot_over_a_restamp(tmp_path):
    """The honest Friday row keeps (NVDA, Friday) even though the Saturday row
    comes later in file order — honest rows are classified first."""
    _write_ledger(tmp_path, [_row(SAT, "NVDA"), _row(FRI, "NVDA")])
    heal(tmp_path, frame_sessions=_reader({"NVDA": set(FROZEN_AT_FRIDAY)}))

    main = _main_rows(tmp_path)
    assert len(main) == 1
    assert main[0]["date"] == FRI and "session_inferred" not in main[0]
    assert [q["date"] for q in _quar_rows(tmp_path)] == [SAT]


def test_first_writer_wins_between_two_restamps(tmp_path):
    """With no honest row in the slot, the FIRST mislabeled row by file order
    takes the session; the later one is quarantined."""
    _write_ledger(tmp_path, [_row(SAT, "AVGO"), _row(SUN, "AVGO")])
    heal(tmp_path, frame_sessions=_reader({"AVGO": set(FROZEN_AT_FRIDAY)}))

    main = _main_rows(tmp_path)
    assert len(main) == 1
    assert main[0]["original_date"] == SAT and main[0]["date"] == FRI
    assert [q["date"] for q in _quar_rows(tmp_path)] == [SUN]


def test_survivors_plus_quarantine_equals_input_count(tmp_path):
    rows = _fixture_rows()
    _write_ledger(tmp_path, rows)
    summary = heal(tmp_path, frame_sessions=_reader(_fixture_index()))

    assert summary["n_rows_in"] == len(rows)
    assert summary["n_survivors"] + summary["n_quarantined_now"] == len(rows)
    assert len(_main_rows(tmp_path)) + len(_quar_rows(tmp_path)) == len(rows)
    assert summary["n_honest"] + summary["n_restamped"] == summary["n_survivors"]


# ── per-original-date breakdown + meta provenance ─────────────────────────────

def test_summary_breaks_down_by_original_date(tmp_path):
    _write_ledger(tmp_path, _fixture_rows())
    summary = heal(tmp_path, frame_sessions=_reader(_fixture_index()))
    bd = summary["by_original_date"]

    assert bd[THU] == {"rows_in": 1, "honest": 1, "restamped": 0,
                       "quarantined": 0, "true_sessions": {}}
    assert bd[SAT]["quarantined"] == 1 and bd[SAT]["true_sessions"] == {FRI: 1}
    assert bd[SUN]["restamped"] == 1 and bd[SUN]["true_sessions"] == {FRI: 1}
    assert bd[TUE]["restamped"] == 1


def test_summary_reports_the_post_heal_observation_dates(tmp_path):
    """Which sessions the ledger still covers once labels become tape — the
    Sat/Sun/Mon/Tue stamps vanish as observation dates entirely."""
    _write_ledger(tmp_path, _fixture_rows())
    summary = heal(tmp_path, dry_run=True,
                   frame_sessions=_reader(_fixture_index()))

    assert summary["survivors_by_session"] == {THU: 1, FRI: 3}
    assert sum(summary["survivors_by_session"].values()) == summary["n_survivors"]


def test_meta_records_quarantine_pointer_gaps_and_the_pre_fix_stamp(tmp_path):
    _write_ledger(tmp_path, _fixture_rows())
    heal(tmp_path, frame_sessions=_reader(_fixture_index()))

    meta = json.loads(
        (tmp_path / "data/stage_analysis/forward_ledger_meta.json").read_text())
    assert meta["quarantine"]["file"] == "forward_ledger_quarantine.jsonl"
    assert meta["quarantine"]["n_rows"] == 2
    assert meta["quarantine"]["healed_by"] == "scripts/heal_stage_forward_ledger.py"
    assert meta["quarantine"]["last_heal"]
    # A reader must see WHY the dates moved without the commissioning session.
    assert "PT" in meta["pre_fix_stamp"] and "UTC" in meta["pre_fix_stamp"]
    assert "2026-08-04" in meta["pre_fix_stamp"]
    assert meta["residual"]
    # One known_gaps entry per distinct original date that moved.
    assert [g["session"] for g in meta["known_gaps"]] == [SAT, SUN, MON, TUE]
    assert all("not evidence about that session" in g["reason"]
               for g in meta["known_gaps"])


# ── fail-closed ───────────────────────────────────────────────────────────────

def test_fails_closed_on_a_ticker_with_no_readable_frame(tmp_path):
    p = _write_ledger(tmp_path, _fixture_rows())
    before = p.read_bytes()
    index = _fixture_index()
    del index["COST"]                       # unreadable / absent frame

    with pytest.raises(SystemExit):
        heal(tmp_path, frame_sessions=_reader(index))

    assert p.read_bytes() == before         # aborted before any write
    assert not (tmp_path / "data/stage_analysis/forward_ledger_quarantine.jsonl").exists()
    assert not (tmp_path / "data/stage_analysis/forward_ledger_meta.json").exists()


def test_fails_closed_when_no_bar_exists_at_or_before_the_stamp(tmp_path):
    p = _write_ledger(tmp_path, [_row("2026-07-01", "NEWLY")])
    before = p.read_bytes()

    with pytest.raises(SystemExit):
        heal(tmp_path, frame_sessions=_reader({"NEWLY": {THU, FRI}}))

    assert p.read_bytes() == before
    assert not (tmp_path / "data/stage_analysis/forward_ledger_quarantine.jsonl").exists()


# ── dry run + idempotence ─────────────────────────────────────────────────────

def test_dry_run_writes_nothing(tmp_path):
    p = _write_ledger(tmp_path, _fixture_rows())
    before = p.read_bytes()

    summary = heal(tmp_path, dry_run=True, frame_sessions=_reader(_fixture_index()))

    assert summary["dry_run"] is True
    assert summary["n_restamped"] == 2 and summary["n_quarantined_now"] == 2
    assert p.read_bytes() == before
    assert not (tmp_path / "data/stage_analysis/forward_ledger_quarantine.jsonl").exists()
    assert not (tmp_path / "data/stage_analysis/forward_ledger_meta.json").exists()


def test_rerun_is_a_no_op(tmp_path):
    _write_ledger(tmp_path, _fixture_rows())
    heal(tmp_path, frame_sessions=_reader(_fixture_index()))
    healed = (tmp_path / "data/stage_analysis/forward_ledger.jsonl").read_bytes()

    second = heal(tmp_path, frame_sessions=_reader(_fixture_index()))

    assert second["n_restamped"] == 0 and second["n_quarantined_now"] == 0
    assert second.get("note") == "already healed — nothing to do"
    assert (tmp_path / "data/stage_analysis/forward_ledger.jsonl").read_bytes() == healed
    assert len(_quar_rows(tmp_path)) == 2      # not re-appended


def test_missing_ledger_reports_an_error(tmp_path):
    summary = heal(tmp_path, frame_sessions=_reader({}))
    assert "error" in summary and "forward_ledger.jsonl" in summary["error"]
