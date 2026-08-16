"""CN-PR-2 — asia-close arming wiring + keep-first ledger + confirmation receipt."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from engine.prophet_live import cn_reconcile as CR
from scripts import reconcile_cn_live as drv

UTC = timezone.utc
ROOT = Path(__file__).resolve().parent.parent
ASIA = (ROOT / ".github" / "workflows" / "asia-close.yml").read_text(encoding="utf-8")


def test_asia_close_arms_and_reconciles_with_a_bounded_nonfatal_step() -> None:
    assert "scripts.build_cn_live_pack" in ASIA
    assert "scripts.reconcile_cn_live" in ASIA
    assert "--asia" in ASIA
    assert "timeout-minutes: 12" in ASIA
    # The arming/reconcile pair must not be able to red the asia job.
    assert ASIA.count("continue-on-error: true") >= 2
    assert "CN_LANE: asia" in ASIA


def test_merge_keeps_the_first_confirmed_and_fills_later_nulls() -> None:
    existing = [{
        "date": "2026-08-18", "ticker": "600519.SS", "kind": "forming",
        "confirmed": True, "first_px": 10.0, "cross_px": 10.0,
        "next_close_fill": None,
    }]
    incoming = [{
        "date": "2026-08-18", "ticker": "600519.SS", "kind": "forming",
        "confirmed": False, "first_px": 11.0, "cross_px": 11.0,
        "next_close_fill": 10.5,
    }]
    got = CR.merge_rows(existing, incoming)
    assert len(got) == 1
    assert got[0]["confirmed"] is True
    assert got[0]["first_px"] == 10.0
    assert got[0]["cross_px"] == 10.0
    assert got[0]["next_close_fill"] == 10.5


def test_pre_floor_rows_are_dropped() -> None:
    got = CR.merge_rows([], [{
        "date": "2026-08-01", "ticker": "000001.SZ", "kind": "forming",
        "first_px": 1.0,
    }])
    assert got == []


def test_events_to_rows_keep_the_first_cross() -> None:
    events = [
        {"ticker": "600519.SS", "kind": "forming", "ts": "A", "px": 10.0},
        {"ticker": "600519.SS", "kind": "forming", "ts": "B", "px": 11.0},
        {"ticker": "000001.SZ", "kind": "faded", "ts": "C", "px": 8.0},
    ]
    rows = CR.events_to_rows(events, session="2026-08-18", confirmed={"600519.SS"})
    by = {(r["ticker"], r["kind"]): r for r in rows}
    assert by[("600519.SS", "forming")]["first_px"] == 10.0
    assert by[("600519.SS", "forming")]["last_px"] == 11.0
    assert by[("600519.SS", "forming")]["occurrences"] == 2
    assert by[("600519.SS", "forming")]["confirmed"] is True
    assert by[("000001.SZ", "faded")]["confirmed"] is False


def test_confirmation_receipt_same_session() -> None:
    board = {"lanes": {
        "featured": [{"ticker": "AAA"}],
        "more_actionable": [{"ticker": "BBB"}],
        "forming": [{"ticker": "CCC"}],
    }}
    standouts = {
        "as_of": "2026-08-18",
        "buy": [{"ticker": "AAA"}],
        "more_actionable": [{"ticker": "BBB"}, {"ticker": "DDD"}],
        "forming": [],
    }
    rec = CR.confirmation_receipt(board, standouts, session="2026-08-18")
    assert rec is not None
    assert rec["schema"] == CR.RECEIPT_SCHEMA
    assert rec["confirmed"] == ["AAA", "BBB"]
    assert rec["dropped"] == ["CCC"]
    assert rec["detail"]["added"] == ["DDD"]
    assert rec["n_confirmed"] + rec["n_adjusted"] + rec["n_dropped"] == rec["n_total"]


def test_confirmation_receipt_refuses_a_behind_night() -> None:
    board = {"lanes": {"featured": [{"ticker": "AAA"}]}}
    standouts = {"as_of": "2026-08-17", "buy": [{"ticker": "AAA"}]}
    assert CR.confirmation_receipt(board, standouts, session="2026-08-18") is None
    assert CR.confirmation_receipt(None, standouts, session="2026-08-17") is None


def test_featured_vs_buy_is_confirmed_not_adjusted() -> None:
    board = {"lanes": {"featured": [{"ticker": "AAA"}]}}
    standouts = {"as_of": "2026-08-18", "buy": [{"ticker": "AAA"}]}
    rec = CR.confirmation_receipt(board, standouts, session="2026-08-18")
    assert rec is not None and rec["confirmed"] == ["AAA"] and rec["adjusted"] == []


def test_driver_refuses_to_write_off_the_asia_lane(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("CN_LANE", raising=False)
    out = tmp_path / "forward.parquet"
    rc = drv.run_asia(
        pack_path=None, events_path=None, close_board_path=None,
        standouts_path=tmp_path / "missing.json", out_path=out,
        now=datetime(2026, 8, 18, 10, 0, tzinfo=UTC),
    )
    assert rc == 0
    assert not out.exists()


def test_driver_writes_ledger_and_receipt(tmp_path, monkeypatch) -> None:
    pytest.importorskip("pandas")
    monkeypatch.setenv("CN_LANE", "asia")
    events = tmp_path / "events.json"
    events.write_text(json.dumps({
        "session": "2026-08-18",
        "events": [
            {"ticker": "600519.SS", "kind": "forming", "ts": "A", "px": 10.0},
        ],
    }), encoding="utf-8")
    board = tmp_path / "board.json"
    board.write_text(json.dumps({
        "session": "2026-08-18",
        "close_board": {"lanes": {"featured": [{"ticker": "600519.SS"}]}},
    }), encoding="utf-8")
    standouts = tmp_path / "standouts.json"
    standouts.write_text(json.dumps({
        "as_of": "2026-08-18",
        "buy": [{"ticker": "600519.SS"}],
        "more_actionable": [],
        "forming": [],
    }), encoding="utf-8")
    out = tmp_path / "forward.parquet"
    rc = drv.run_asia(
        pack_path=None, events_path=events, close_board_path=board,
        standouts_path=standouts, out_path=out,
        now=datetime(2026, 8, 18, 10, 0, tzinfo=UTC),
    )
    assert rc == 0
    assert out.exists()
    receipt = json.loads((tmp_path / "cn_board_confirmation.json").read_text())
    assert receipt["confirmed"] == ["600519.SS"]
    # Second pass is idempotent and cannot un-confirm.
    rc = drv.run_asia(
        pack_path=None, events_path=events, close_board_path=board,
        standouts_path=standouts, out_path=out,
        now=datetime(2026, 8, 18, 10, 5, tzinfo=UTC),
    )
    assert rc == 0
    import pandas as pd
    frame = pd.read_parquet(out)
    assert len(frame) == 1
    assert bool(frame.iloc[0]["confirmed"]) is True


def test_cli_requires_asia() -> None:
    with pytest.raises(SystemExit) as exc:
        drv.main([])
    assert exc.value.code == 2
