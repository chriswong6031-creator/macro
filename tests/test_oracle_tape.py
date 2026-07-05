"""Tests for Oracle W5.1 — Operator Tape Journal CLI.

Covers:
  A. add/list round-trip in a tmp dir
  B. same-second duplicate-id suffix (::2)
  C. review-inbox merge view shows tape rows (additive, separate group)
  D. missing tape file tolerated silently in oracle_review_inbox

All fixtures are SYNTHETIC — no real data files, no network.
"""
from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _oracle_dir(tmp_path: Path) -> Path:
    d = tmp_path / "oracle"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _tape_path(tmp_path: Path) -> Path:
    return tmp_path / "oracle" / "operator_tape.jsonl"


def _call_add(tmp_path: Path, nodes: str, direction: str, note: str,
              tickers: str | None = None, invalidation: str | None = None,
              conviction: int | None = None) -> dict:
    """Invoke oracle_tape add subcommand and return the written row."""
    from scripts.oracle_tape import _cmd_add

    argv = [
        "--nodes", nodes,
        "--direction", direction,
        "--note", note,
    ]
    if tickers is not None:
        argv += ["--tickers", tickers]
    if invalidation is not None:
        argv += ["--invalidation", invalidation]
    if conviction is not None:
        argv += ["--conviction", str(conviction)]
    argv += ["--data-dir", str(tmp_path)]

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--nodes", required=True)
    parser.add_argument("--direction", required=True, choices=["in", "out"])
    parser.add_argument("--note", required=True)
    parser.add_argument("--tickers", default=None)
    parser.add_argument("--invalidation", default=None)
    parser.add_argument("--conviction", type=int, default=None)
    parser.add_argument("--data-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    captured = StringIO()
    with mock.patch("sys.stdout", captured):
        rc = _cmd_add(args, tmp_path)

    assert rc == 0, f"_cmd_add returned {rc}"
    output = captured.getvalue().strip()
    return json.loads(output)


def _call_list(tmp_path: Path, pending: bool = False) -> list[dict]:
    """Invoke oracle_tape list subcommand and return raw rows from the file."""
    from scripts.oracle_tape import _load_rows, _tape_path as _tp
    tape_path = _tp(tmp_path)
    rows = _load_rows(tape_path)
    rows = [r for r in rows if r.get("type") == "operator_tape"]
    if pending:
        rows = [r for r in rows if r.get("converted") is None]
    return rows


# ---------------------------------------------------------------------------
# A. add/list round-trip
# ---------------------------------------------------------------------------

def test_add_list_roundtrip(tmp_path: Path) -> None:
    """add writes a row; list returns it with correct fields."""
    _oracle_dir(tmp_path)

    row = _call_add(
        tmp_path,
        nodes="XLK,XLC",
        direction="in",
        note="Tech breaking out of 3-week base",
        tickers="MSFT,NVDA",
        invalidation="Close below 200d MA on XLK",
        conviction=4,
    )

    # Field presence and types
    assert row["type"] == "operator_tape"
    assert row["id"].startswith("tape::")
    assert row["direction"] == "in"
    assert row["nodes"] == ["XLK", "XLC"]
    assert row["note"] == "Tech breaking out of 3-week base"
    assert row["tickers"] == ["MSFT", "NVDA"]
    assert row["invalidation"] == "Close below 200d MA on XLK"
    assert row["conviction"] == 4
    assert row["converted"] is None
    assert "pit_stamp" in row

    # round-trip: list sees the row
    rows = _call_list(tmp_path)
    assert len(rows) == 1
    assert rows[0]["id"] == row["id"]

    # pending filter also shows it (converted is null)
    pending = _call_list(tmp_path, pending=True)
    assert len(pending) == 1


def test_add_minimal(tmp_path: Path) -> None:
    """add works with only required flags; optional fields are null/empty."""
    _oracle_dir(tmp_path)

    row = _call_add(
        tmp_path,
        nodes="XLE",
        direction="out",
        note="Energy stalling at resistance",
    )

    assert row["tickers"] == []
    assert row["invalidation"] is None
    assert row["conviction"] is None
    assert row["converted"] is None
    assert row["nodes"] == ["XLE"]
    assert row["direction"] == "out"


def test_add_multiple_rows(tmp_path: Path) -> None:
    """Multiple add calls each append a separate row."""
    _oracle_dir(tmp_path)

    _call_add(tmp_path, nodes="XLK", direction="in", note="First obs")
    _call_add(tmp_path, nodes="XLE", direction="out", note="Second obs")
    _call_add(tmp_path, nodes="XLF,XLC", direction="in", note="Third obs", conviction=3)

    rows = _call_list(tmp_path)
    assert len(rows) == 3
    notes = [r["note"] for r in rows]
    assert "First obs" in notes
    assert "Second obs" in notes
    assert "Third obs" in notes


# ---------------------------------------------------------------------------
# B. same-second duplicate-id suffix (::2, ::3)
# ---------------------------------------------------------------------------

def test_same_second_dedup_suffix(tmp_path: Path) -> None:
    """Two adds in the same UTC second get distinct ids: base and base::2."""
    from scripts import oracle_tape as ot

    _oracle_dir(tmp_path)

    # Freeze time: both calls see the same timestamp
    frozen_ts = "2026-07-05T10:00:00Z"
    import datetime as _dt

    class _FrozenDT:
        @staticmethod
        def now(tz=None):
            return _dt.datetime(2026, 7, 5, 10, 0, 0, tzinfo=_dt.timezone.utc)

    with mock.patch.object(ot, "datetime", _FrozenDT):
        row1 = _call_add(tmp_path, nodes="XLK", direction="in", note="Obs one")
        row2 = _call_add(tmp_path, nodes="XLC", direction="in", note="Obs two")

    assert row1["id"] != row2["id"], "Same-second adds must get distinct ids"
    # First should be the base (no suffix), second should have ::2
    base = "tape::2026-07-05T10-00-00"
    assert row1["id"] == base, f"Expected base id '{base}', got '{row1['id']}'"
    assert row2["id"] == f"{base}::2", f"Expected '{base}::2', got '{row2['id']}'"


def test_same_second_triple_dedup(tmp_path: Path) -> None:
    """Three adds in the same second: base, ::2, ::3."""
    from scripts import oracle_tape as ot

    _oracle_dir(tmp_path)

    import datetime as _dt

    class _FrozenDT:
        @staticmethod
        def now(tz=None):
            return _dt.datetime(2026, 7, 5, 11, 0, 0, tzinfo=_dt.timezone.utc)

    with mock.patch.object(ot, "datetime", _FrozenDT):
        row1 = _call_add(tmp_path, nodes="XLK", direction="in", note="A")
        row2 = _call_add(tmp_path, nodes="XLC", direction="in", note="B")
        row3 = _call_add(tmp_path, nodes="XLE", direction="out", note="C")

    ids = {row1["id"], row2["id"], row3["id"]}
    assert len(ids) == 3, f"Expected 3 distinct ids, got {ids}"
    base = "tape::2026-07-05T11-00-00"
    assert base in ids
    assert f"{base}::2" in ids
    assert f"{base}::3" in ids


# ---------------------------------------------------------------------------
# C. review-inbox merge view shows tape rows
# ---------------------------------------------------------------------------

def _write_inbox(oracle_dir: Path, rows: list[dict]) -> None:
    """Write synthetic hypothesis_inbox.jsonl."""
    inbox = oracle_dir / "hypothesis_inbox.jsonl"
    inbox.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _write_tape(oracle_dir: Path, rows: list[dict]) -> None:
    """Write synthetic operator_tape.jsonl (with schema_note header)."""
    tape = oracle_dir / "operator_tape.jsonl"
    header = {"type": "schema_note", "note": "seed header"}
    all_rows = [header] + rows
    tape.write_text("\n".join(json.dumps(r) for r in all_rows) + "\n", encoding="utf-8")


def test_review_inbox_shows_tape_rows(tmp_path: Path, capsys) -> None:
    """oracle_review_inbox loads tape rows and prints them in a separate group."""
    oracle_dir = _oracle_dir(tmp_path)

    # Inbox has one sentinel row
    inbox_rows = [{
        "id": "sentinel::panel_drift::2026-07-01T00:00:00Z",
        "type": "sentinel",
        "pit_stamp": "2026-07-01T00:00:00Z",
        "converted": None,
        "detail_en": "Drift detected on XLK",
        "detail_zh": "drift zh",
    }]
    _write_inbox(oracle_dir, inbox_rows)

    # Tape has two operator_tape rows
    tape_rows = [
        {
            "id": "tape::2026-07-05T09-00-00",
            "type": "operator_tape",
            "pit_stamp": "2026-07-05T09:00:00Z",
            "nodes": ["XLK"],
            "direction": "in",
            "note": "Tech breakout observed",
            "tickers": ["MSFT"],
            "invalidation": "Break below 200d",
            "conviction": 4,
            "converted": None,
        },
        {
            "id": "tape::2026-07-05T10-00-00",
            "type": "operator_tape",
            "pit_stamp": "2026-07-05T10:00:00Z",
            "nodes": ["XLE"],
            "direction": "out",
            "note": "Energy stalling",
            "tickers": [],
            "invalidation": None,
            "conviction": None,
            "converted": None,
        },
    ]
    _write_tape(oracle_dir, tape_rows)

    # Run review inbox with --data-dir pointing at tmp_path
    import importlib
    import scripts.oracle_review_inbox as ri
    importlib.reload(ri)

    with mock.patch("sys.argv", ["oracle_review_inbox.py", "--data-dir", str(tmp_path)]):
        # Patch data_dir so we don't need a real config
        with mock.patch("lib.config.data_dir", return_value=tmp_path):
            rc = ri.main()

    assert rc == 0

    captured = capsys.readouterr()
    out = captured.out

    # Tape section header must be present
    assert "operator_tape" in out, f"Expected 'operator_tape' in output:\n{out}"

    # Both tape rows must appear
    assert "Tech breakout observed" in out, f"Expected tape note in output:\n{out}"
    assert "Energy stalling" in out, f"Expected second tape note in output:\n{out}"

    # Inbox row must still appear
    assert "sentinel" in out, f"Expected inbox sentinel row in output:\n{out}"


def test_review_inbox_tape_pending_filter(tmp_path: Path, capsys) -> None:
    """With --pending, converted tape rows are hidden; unconverted still shown."""
    oracle_dir = _oracle_dir(tmp_path)

    # Empty inbox
    (oracle_dir / "hypothesis_inbox.jsonl").write_text("", encoding="utf-8")

    tape_rows = [
        {
            "id": "tape::2026-07-05T08-00-00",
            "type": "operator_tape",
            "pit_stamp": "2026-07-05T08:00:00Z",
            "nodes": ["XLV"],
            "direction": "in",
            "note": "Healthcare recovering",
            "tickers": [],
            "invalidation": None,
            "conviction": 2,
            "converted": "2026-07-05",  # already converted
        },
        {
            "id": "tape::2026-07-05T09-00-00",
            "type": "operator_tape",
            "pit_stamp": "2026-07-05T09:00:00Z",
            "nodes": ["XLK"],
            "direction": "in",
            "note": "Tech still pending",
            "tickers": [],
            "invalidation": None,
            "conviction": None,
            "converted": None,  # pending
        },
    ]
    _write_tape(oracle_dir, tape_rows)

    import importlib
    import scripts.oracle_review_inbox as ri
    importlib.reload(ri)

    # --pending is the default (show_all=False → pending_only=True)
    with mock.patch("sys.argv", ["oracle_review_inbox.py", "--data-dir", str(tmp_path)]):
        with mock.patch("lib.config.data_dir", return_value=tmp_path):
            rc = ri.main()

    assert rc == 0
    captured = capsys.readouterr()
    out = captured.out

    # Pending note must appear
    assert "Tech still pending" in out, f"Pending tape row missing:\n{out}"
    # Converted note must NOT appear under --pending
    assert "Healthcare recovering" not in out, f"Converted tape row should be hidden:\n{out}"


# ---------------------------------------------------------------------------
# D. missing tape file tolerated silently
# ---------------------------------------------------------------------------

def test_review_inbox_missing_tape_file(tmp_path: Path, capsys) -> None:
    """If operator_tape.jsonl does not exist, review-inbox does not crash."""
    oracle_dir = _oracle_dir(tmp_path)

    # Inbox has one row; tape file does NOT exist
    inbox_rows = [{
        "id": "sentinel::panel_drift::2026-07-01T00:00:00Z",
        "type": "sentinel",
        "pit_stamp": "2026-07-01T00:00:00Z",
        "converted": None,
        "detail_en": "Drift detected",
        "detail_zh": "drift zh",
    }]
    _write_inbox(oracle_dir, inbox_rows)
    # Confirm tape file is absent
    assert not (oracle_dir / "operator_tape.jsonl").exists()

    import importlib
    import scripts.oracle_review_inbox as ri
    importlib.reload(ri)

    with mock.patch("sys.argv", ["oracle_review_inbox.py", "--data-dir", str(tmp_path)]):
        with mock.patch("lib.config.data_dir", return_value=tmp_path):
            rc = ri.main()

    assert rc == 0, "review-inbox must exit 0 when tape file is missing"

    captured = capsys.readouterr()
    out = captured.out
    # Inbox rows still shown
    assert "sentinel" in out, f"Inbox rows should appear even without tape file:\n{out}"


def test_tape_load_missing_file_silent() -> None:
    """_load_tape_rows returns [] without raising when file is missing."""
    from scripts.oracle_review_inbox import _load_tape_rows
    rows = _load_tape_rows(Path("/tmp/definitely_does_not_exist_oracle_tape_xyz.jsonl"))
    assert rows == []


# ---------------------------------------------------------------------------
# E. schema_note header row is ignored by readers
# ---------------------------------------------------------------------------

def test_schema_note_skipped_in_list(tmp_path: Path) -> None:
    """schema_note header row in tape file is not returned by _load_tape_rows."""
    oracle_dir = _oracle_dir(tmp_path)
    tape = oracle_dir / "operator_tape.jsonl"
    schema_note = {"type": "schema_note", "note": "header"}
    op_row = {
        "id": "tape::2026-07-05T09-00-00",
        "type": "operator_tape",
        "pit_stamp": "2026-07-05T09:00:00Z",
        "nodes": ["XLK"],
        "direction": "in",
        "note": "real obs",
        "tickers": [],
        "invalidation": None,
        "conviction": None,
        "converted": None,
    }
    tape.write_text(
        json.dumps(schema_note) + "\n" + json.dumps(op_row) + "\n",
        encoding="utf-8",
    )

    from scripts.oracle_review_inbox import _load_tape_rows
    rows = _load_tape_rows(tape)
    assert len(rows) == 1
    assert rows[0]["type"] == "operator_tape"
    assert rows[0]["note"] == "real obs"


def test_schema_note_skipped_in_cli_list(tmp_path: Path) -> None:
    """oracle_tape list does not display schema_note rows."""
    oracle_dir = _oracle_dir(tmp_path)

    # Write tape with only a schema_note (simulates empty-but-committed file)
    tape = oracle_dir / "operator_tape.jsonl"
    tape.write_text(
        json.dumps({"type": "schema_note", "note": "seed"}) + "\n",
        encoding="utf-8",
    )

    from scripts.oracle_tape import _load_rows
    rows = _load_rows(tape)
    # _load_rows returns all rows including schema_note
    op_rows = [r for r in rows if r.get("type") == "operator_tape"]
    assert op_rows == [], "No operator_tape rows expected when file has only schema_note"


# ---------------------------------------------------------------------------
# F. conviction validation (1-5 guard)
# ---------------------------------------------------------------------------

def test_conviction_out_of_range(tmp_path: Path) -> None:
    """--conviction outside 1-5 returns exit code 1."""
    from scripts.oracle_tape import _cmd_add

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--nodes", required=True)
    parser.add_argument("--direction", required=True, choices=["in", "out"])
    parser.add_argument("--note", required=True)
    parser.add_argument("--tickers", default=None)
    parser.add_argument("--invalidation", default=None)
    parser.add_argument("--conviction", type=int, default=None)
    parser.add_argument("--data-dir", type=Path, default=None)

    _oracle_dir(tmp_path)
    args = parser.parse_args([
        "--nodes", "XLK",
        "--direction", "in",
        "--note", "test",
        "--conviction", "6",
        "--data-dir", str(tmp_path),
    ])

    rc = _cmd_add(args, tmp_path)
    assert rc == 1, f"Expected exit code 1 for conviction=6, got {rc}"
