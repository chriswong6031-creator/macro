"""Tests for scripts/heal_basket_turn_ledger.py — forward-ledger audit 2026-08-05.

The heal re-keys data/basket_turn/ledger.jsonl off the DATA PLANE: a row whose
`date` is not a session any of its basket's member frames actually carries was
stamped from the calendar, not the tape.  Such a row is either restamped to the
session the run really read, or — when that session already carries a row for
the same basket — quarantined as a duplicate re-description.  Nothing is ever
deleted.

Covers:
  (1) quarantine branch — reason, kept-row pointer, meta block, no row lost
  (2) restamp branch — date/as_of moved to the true session + session_inferred
  (3) fail-closed — no readable member frame → SystemExit, ledger untouched
  (4) fail-closed — no member bar at or before the stamp → SystemExit
  (5) idempotency — a healed ledger yields "already healed — nothing to do"
  (6) --dry-run writes nothing

Every fixture date is a pinned weekday; nothing here reads the wall clock.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import heal_basket_turn_ledger as HEAL

# ── pinned fixture dates ───────────────────────────────────────────────────────
_TAPE_SESSION = "2026-07-15"   # Wednesday — the fixture store's newest bar
_STALE_STAMP  = "2026-07-16"   # Thursday — a calendar date the tape never had
_BEFORE_STORE = "2026-07-10"   # Friday — earlier than every fixture bar


# ── fixture helpers ────────────────────────────────────────────────────────────

def _write_stock_parquet(path: Path, end: str, n: int = 3) -> None:
    """Write a close parquet whose LAST business-day bar is `end`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    idx = pd.bdate_range(end=end, periods=n)
    pd.DataFrame({"close": [100.0 + i for i in range(n)]}, index=idx).to_parquet(path)


def _write_membership(root: Path, tickers: list[str], basket_id: str = "mag7") -> None:
    p = root / "data" / "baskets"
    p.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": "1",
        "baskets": {
            basket_id: {
                "members": [
                    {"ticker": tk, "added": _TAPE_SESSION, "removed": None} for tk in tickers
                ]
            }
        },
    }
    (p / "membership.json").write_text(json.dumps(payload), encoding="utf-8")


def _row(basket_id: str, date_str: str, state: str = "WATCH", k: int = 2) -> dict:
    return {
        "date": date_str,
        "basket_id": basket_id,
        "state": state,
        "k": k,
        "legs": {"impulse_day": True, "rs_z": False, "breadth_surge": False,
                 "volume_confirm": True, "complex_confirm": False,
                 "shock_relative_bid": False},
        "as_of": date_str,
    }


def _write_ledger(root: Path, rows: list[dict]) -> Path:
    p = root / "data" / "basket_turn"
    p.mkdir(parents=True, exist_ok=True)
    f = p / "ledger.jsonl"
    f.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return f


def _read_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _standard_store(root: Path) -> None:
    """One basket, one member, three bars ending at the pinned tape session."""
    _write_membership(root, ["M1"])
    _write_stock_parquet(root / "data" / "stocks" / "M1.parquet", _TAPE_SESSION)


# ── (1) quarantine branch ──────────────────────────────────────────────────────

def test_quarantines_duplicate_redescription(tmp_path):
    """A stale-stamped row whose true session is already recorded is quarantined."""
    _standard_store(tmp_path)
    ledger_p = _write_ledger(tmp_path, [
        _row("mag7", _TAPE_SESSION),                    # honest
        _row("mag7", _STALE_STAMP, state="DOWNGRADE"),  # frozen-store re-description
    ])

    summary = HEAL.heal(tmp_path)

    assert summary["n_quarantined_now"] == 1
    assert summary["n_restamped"] == 0
    assert summary["n_survivors"] == 1
    # never-delete law: every input row is still on disk somewhere
    assert summary["n_survivors"] + summary["n_quarantined_now"] == summary["n_rows_in"]

    survivors = _read_jsonl(ledger_p)
    assert len(survivors) == 1
    assert survivors[0]["date"] == _TAPE_SESSION
    assert survivors[0]["state"] == "WATCH", "the honest row is the one kept"
    assert "session_inferred" not in survivors[0]

    quar = _read_jsonl(tmp_path / "data" / "basket_turn" / "ledger_quarantine.jsonl")
    assert len(quar) == 1
    assert quar[0]["date"] == _STALE_STAMP, "the quarantined row keeps its original stamp"
    assert "duplicate re-description" in quar[0]["quarantine_reason"]
    assert quar[0]["quarantined_kept_row"] == {"date": _TAPE_SESSION, "basket_id": "mag7"}
    assert quar[0]["quarantined_at"]

    meta = json.loads((tmp_path / "data" / "basket_turn" / "ledger_meta.json").read_text())
    assert meta["quarantine"]["file"] == "ledger_quarantine.jsonl"
    assert meta["quarantine"]["n_rows"] == 1
    assert meta["quarantine"]["healed_by"] == "scripts/heal_basket_turn_ledger.py"
    gaps = {g["session"] for g in meta["known_gaps"]}
    assert gaps == {_STALE_STAMP}
    assert "unknowable from committed data" in meta["known_gaps"][0]["reason"]


# ── (2) restamp branch ─────────────────────────────────────────────────────────

def test_restamps_when_true_session_is_free(tmp_path):
    """A stale-stamped row with no row at its true session is restamped in place."""
    _standard_store(tmp_path)
    ledger_p = _write_ledger(tmp_path, [_row("mag7", _STALE_STAMP)])

    summary = HEAL.heal(tmp_path)

    assert summary["n_restamped"] == 1
    assert summary["n_quarantined_now"] == 0
    assert summary["n_survivors"] == 1

    rows = _read_jsonl(ledger_p)
    assert len(rows) == 1
    assert rows[0]["date"] == _TAPE_SESSION
    assert rows[0]["as_of"] == _TAPE_SESSION
    assert rows[0]["session_inferred"] is True

    assert not (tmp_path / "data" / "basket_turn" / "ledger_quarantine.jsonl").exists()
    meta = json.loads((tmp_path / "data" / "basket_turn" / "ledger_meta.json").read_text())
    assert [g["session"] for g in meta["known_gaps"]] == [_STALE_STAMP]


# ── (3) fail-closed: no readable member frame ─────────────────────────────────

def test_fail_closed_when_basket_has_no_member_frames(tmp_path):
    """Zero readable member frames → abort the whole heal, write nothing."""
    _write_membership(tmp_path, ["GHOST"])   # no GHOST.parquet on disk
    ledger_p = _write_ledger(tmp_path, [_row("mag7", _STALE_STAMP)])
    before = ledger_p.read_bytes()

    with pytest.raises(SystemExit) as exc:
        HEAL.heal(tmp_path)

    assert "FAIL-CLOSED" in str(exc.value)
    assert ledger_p.read_bytes() == before, "ledger must be untouched"
    assert not (tmp_path / "data" / "basket_turn" / "ledger_quarantine.jsonl").exists()
    assert not (tmp_path / "data" / "basket_turn" / "ledger_meta.json").exists()


# ── (4) fail-closed: no member bar at or before the stamp ─────────────────────

def test_fail_closed_when_no_bar_at_or_before_the_stamp(tmp_path):
    """A stamp older than every bar has no inferable session → abort."""
    _standard_store(tmp_path)
    ledger_p = _write_ledger(tmp_path, [_row("mag7", _BEFORE_STORE)])
    before = ledger_p.read_bytes()

    with pytest.raises(SystemExit) as exc:
        HEAL.heal(tmp_path)

    assert "FAIL-CLOSED" in str(exc.value)
    assert ledger_p.read_bytes() == before


# ── (5) idempotency ───────────────────────────────────────────────────────────

def test_second_run_is_a_no_op(tmp_path):
    """Re-running the heal on a healed ledger changes nothing."""
    _standard_store(tmp_path)
    ledger_p = _write_ledger(tmp_path, [
        _row("mag7", _TAPE_SESSION),
        _row("mag7", _STALE_STAMP, state="DOWNGRADE"),
    ])

    HEAL.heal(tmp_path)
    quar_p = tmp_path / "data" / "basket_turn" / "ledger_quarantine.jsonl"
    ledger_bytes, quar_bytes = ledger_p.read_bytes(), quar_p.read_bytes()

    summary2 = HEAL.heal(tmp_path)

    assert summary2["n_quarantined_now"] == 0
    assert summary2["n_restamped"] == 0
    assert summary2["note"] == "already healed — nothing to do"
    assert ledger_p.read_bytes() == ledger_bytes
    assert quar_p.read_bytes() == quar_bytes


# ── (6) --dry-run ─────────────────────────────────────────────────────────────

def test_dry_run_writes_nothing(tmp_path):
    """--dry-run reports the same counts but touches no file."""
    _standard_store(tmp_path)
    ledger_p = _write_ledger(tmp_path, [
        _row("mag7", _TAPE_SESSION),
        _row("mag7", _STALE_STAMP, state="DOWNGRADE"),
    ])
    before = ledger_p.read_bytes()

    summary = HEAL.heal(tmp_path, dry_run=True)

    assert summary["dry_run"] is True
    assert summary["n_quarantined_now"] == 1
    assert ledger_p.read_bytes() == before
    assert not (tmp_path / "data" / "basket_turn" / "ledger_quarantine.jsonl").exists()
    assert not (tmp_path / "data" / "basket_turn" / "ledger_meta.json").exists()


# ── missing inputs are reported, not raised ───────────────────────────────────

def test_missing_ledger_reports_error(tmp_path):
    summary = HEAL.heal(tmp_path)
    assert "error" in summary
    assert "ledger.jsonl" in summary["error"]
