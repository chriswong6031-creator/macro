"""Guards for recovering the event spool the 2026-08 outage never published.

The rows this path produces enter `data/prophet_live/forward.parquet`, which is the
entire evidence base for "acting at the intraday cross beats the graded next-close
fill". A fabricated row joined to real closes is indistinguishable from a genuine one
forever, so every check here is fail-CLOSED: the recovery refuses rather than accruing
anything it cannot prove came from the production evaluator's own output.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import prophet_live_journal_recovery as R
from scripts import reconcile_prophet_live as RC

PID = "python[123456]"


def _pass(ts: str, n: int, *, pid: str = PID, pack: str = "2026-08-24") -> str:
    return (f"2026-08-25T13:28:12+00:00 host {pid}: prophet-live pass={ts} "
            f"pack_as_of={pack} quotes=2081@2026-08-25T13:27:39.438048+00:00 "
            f"src=vps_local(quotes_full.json+quotes.json) states={{'dark': 1}} "
            f"dark={{'no_quote': 1}} events={n}")


def _event(kind: str, ticker: str, *, pid: str = PID, px: str = "18.01",
           frm: str = "None", passes: str = "1", age: str = "5.9") -> str:
    return (f"2026-08-25T13:28:12+00:00 host {pid}: prophet-live EVENT {kind} "
            f"{ticker} px={px} from={frm} passes={passes} age={age}m")


# --------------------------------------------------------------------------
# Parsing is exact, and self-checking
# --------------------------------------------------------------------------

def test_events_are_read_back_verbatim():
    sessions, stats = R.parse("\n".join([
        _pass("2026-08-25T13:28:04Z", 1),
        _event("forming", "PCG", px="18.01", frm="None", passes="1", age="5.9"),
    ]))
    assert stats["events_total"] == 1
    row = sessions["2026-08-25"][0]
    assert row["ticker"] == "PCG" and row["kind"] == "forming"
    assert row["price"] == 18.01 and row["passes"] == 1
    assert row["quote_age_min"] == 5.9 and row["from"] is None
    # ts is the PASS clock, never the log-write clock: the journal line is stamped
    # 13:28:12 and the pass ran at 13:28:04, and the ledger anchors on the latter.
    assert row["ts"] == "2026-08-25T13:28:04Z"
    assert row["session_et"] == "2026-08-25" and row["pack_as_of"] == "2026-08-24"


def test_a_pass_that_disagrees_with_its_own_event_count_is_refused():
    """The pass line independently declares `events=N`. That is the only reason a log
    can be trusted as a complete source, so a disagreement must never accrue."""
    _, stats = R.parse("\n".join([
        _pass("2026-08-25T13:28:04Z", 3),   # declares 3
        _event("forming", "PCG"),           # prints 1
    ]))
    assert stats["mismatched_passes"], "a count mismatch must be reported"
    assert stats["events_total"] == 0, "and nothing from that pass may be accrued"


def test_event_lines_with_no_pass_line_are_reported():
    _, stats = R.parse(_event("forming", "PCG", pid="python[999]"))
    assert stats["orphan_event_lines"] == 1


def test_passes_are_grouped_by_pid_not_adjacency():
    """Two passes interleaved in the log must not borrow each other's events."""
    lines = [
        _pass("2026-08-25T13:28:04Z", 1, pid="python[111]"),
        _pass("2026-08-25T13:33:04Z", 1, pid="python[222]"),
        _event("forming", "AAA", pid="python[111]"),
        _event("at_risk", "BBB", pid="python[222]"),
    ]
    sessions, stats = R.parse("\n".join(lines))
    assert not stats["mismatched_passes"]
    by_ts = {r["ticker"]: r["ts"] for r in sessions["2026-08-25"]}
    assert by_ts["AAA"] == "2026-08-25T13:28:04Z"
    assert by_ts["BBB"] == "2026-08-25T13:33:04Z"


# --------------------------------------------------------------------------
# `entered` is recovered only where production's own output settles it
# --------------------------------------------------------------------------

def test_board_only_kind_determines_entered_board():
    """at_risk is emitted only inside `if on_board:` (live_states.py:616-654)."""
    sessions, _ = R.parse("\n".join([
        _pass("2026-08-25T13:28:04Z", 2),
        _event("at_risk", "AAA"), _event("forming", "AAA"),
    ]))
    assert {r["entered"] for r in sessions["2026-08-25"]} == {"board"}


def test_cross_only_kind_determines_entered_cross():
    """crossing_unconfirmed is emitted only in the cross branch (live_states.py:698)."""
    sessions, _ = R.parse("\n".join([
        _pass("2026-08-25T13:28:04Z", 2),
        _event("crossing_unconfirmed", "BBB"), _event("forming", "BBB"),
    ]))
    assert {r["entered"] for r in sessions["2026-08-25"]} == {"cross"}


def test_ambiguous_names_stay_null_and_are_never_defaulted():
    """`forming` and `confirming_into_close` occur on BOTH branches. Absence of
    evidence is not evidence of "cross" -- guessing here would silently decide the
    ledger's headline cross-vs-board population (the ~108-board-rows-to-2-crosses
    receipt in live_states.transitions)."""
    sessions, stats = R.parse("\n".join([
        _pass("2026-08-25T13:28:04Z", 2),
        _event("forming", "CCC"), _event("confirming_into_close", "CCC"),
    ]))
    assert all(r["entered"] is None for r in sessions["2026-08-25"])
    assert stats["entered_null"] == 1 and stats["entered_determined"] == 0


def test_a_contradicting_name_is_refused_not_resolved_by_precedence():
    """One name emitting both a board-only and a cross-only kind would mean the branch
    mapping is wrong. That is a reason to stop, not to pick a winner."""
    sessions, stats = R.parse("\n".join([
        _pass("2026-08-25T13:28:04Z", 2),
        _event("at_risk", "DDD"), _event("crossing_unconfirmed", "DDD"),
    ]))
    assert stats["entered_contradictions"] == ["2026-08-25/DDD"]
    assert all(r["entered"] is None for r in sessions["2026-08-25"])


def test_cli_refuses_on_any_integrity_failure(tmp_path):
    journal = tmp_path / "j.txt"
    journal.write_text("\n".join([_pass("2026-08-25T13:28:04Z", 5), _event("forming", "PCG")]))
    rc = R.main(["--journal", str(journal), "--out", str(tmp_path / "out"), "--execute"])
    assert rc == 3, "a mismatched pass must exit nonzero"
    assert not (tmp_path / "out").exists(), "and must stage nothing"


def test_the_recovery_tool_never_writes_the_ledger():
    """LEDGER LAW D10: reconcile_prophet_live is the sole writer of forward.parquet."""
    src = Path(R.__file__).read_text()
    assert "forward.parquet" not in src.replace(
        "data/prophet_live/forward.parquet (LEDGER LAW D10)", "")


# --------------------------------------------------------------------------
# The pending reader is fail-closed
# --------------------------------------------------------------------------

def _stage(tmp_path: Path, session: str = "2026-08-25", *, schema: str | None = None,
           rows: list[dict] | None = None, name: str | None = None) -> Path:
    d = tmp_path / "pending"
    d.mkdir(exist_ok=True)
    payload = {
        "schema": schema or RC.PENDING_SCHEMA,
        "session_et": session,
        "events": rows if rows is not None else [{
            "ticker": "PCG", "kind": "forming", "ts": f"{session}T13:28:04Z",
            "session_et": session, "pack_as_of": "2026-08-24", "price": 18.01,
            "passes": 1, "from": None, "entered": None, "quote_age_min": 5.9,
            "session_phase": "rth"}],
    }
    (d / f"{name or session}.json").write_text(json.dumps(payload))
    return d


def test_pending_rows_carry_the_spool_row_shape(tmp_path):
    loaded = RC.load_pending(_stage(tmp_path))
    row = loaded["2026-08-25"][0]
    assert row["ticker"] == "PCG"
    assert row["_spool_key"].startswith("pending:"), "provenance must stay visible"


def test_pending_refuses_a_foreign_schema(tmp_path):
    with pytest.raises(ValueError, match="schema"):
        RC.load_pending(_stage(tmp_path, schema="something.else/v1"))


def test_pending_refuses_a_filename_session_mismatch(tmp_path):
    with pytest.raises(ValueError, match="filename"):
        RC.load_pending(_stage(tmp_path, session="2026-08-25", name="2026-08-24"))


def test_pending_refuses_a_row_from_another_session(tmp_path):
    rows = [{"ticker": "PCG", "kind": "forming", "session_et": "2026-08-24"}]
    with pytest.raises(ValueError, match="disagrees"):
        RC.load_pending(_stage(tmp_path, rows=rows))


def test_pending_refuses_a_row_missing_identity(tmp_path):
    with pytest.raises(ValueError, match="ticker/kind"):
        RC.load_pending(_stage(tmp_path, rows=[{"session_et": "2026-08-25"}]))


def test_pending_enforces_the_ledger_floor(tmp_path):
    """Belt-and-braces for B4 applies to pending input exactly as to the spool."""
    with pytest.raises(ValueError, match="ledger floor"):
        RC.load_pending(_stage(tmp_path, session="2026-07-29"))


def test_pending_ignores_receipt_files(tmp_path):
    d = _stage(tmp_path)
    (d / "_recovery_receipt.json").write_text(json.dumps({"schema": "receipt"}))
    assert list(RC.load_pending(d)) == ["2026-08-25"]


def test_pending_and_spool_are_mutually_exclusive_in_one_run():
    """Mixing sources in one run makes 'which source wrote this row' unanswerable."""
    import inspect
    src = inspect.getsource(RC.run)
    assert "if pending_dir is not None:" in src and "else:" in src
    assert src.index("load_pending(") < src.index("spool_sessions(")
