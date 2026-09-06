"""Regression contract for Canada board-ledger health projection.

The Canada builder may render in closing-bell and other read-only lanes.  Those
lanes are deliberately unable to advance the durable forward ledger; that
expected no-op must not become a customer-visible write-failure banner.

These tests exercise the real ``scripts.build_canada._canada_board_ledger``
function.  They preserve the opposite safety boundary too: when the canonical
nightly lane is armed, a zero-row append or exception remains a loud error.
"""
from __future__ import annotations

from pathlib import Path

import engine.board_ledger as board_ledger
import engine.board_shadow as board_shadow
import engine.track_ledger as track_ledger
from scripts import build_canada as build_canada


def _setups() -> dict:
    """Small real-shape board sufficient for the production ledger adapter."""
    return {
        "buy": [
            {
                "ticker": "TEST.TO",
                "group": "setting_up",
                "alpha": 0.75,
                "price": 100.0,
                "signal": {},
                "conviction": {},
                "entry_signal": {},
            }
        ],
        "watch": [],
    }


def _is_error(row: dict) -> bool:
    return row.get("status") == "ERROR"


def _stub_read_side(monkeypatch, tmp_path: Path) -> dict[str, int]:
    """Keep scorecard/history reads live while preventing repository writes."""
    seen = {"scorecard": 0, "grade": 0, "track": 0, "shadow": 0}

    def scorecard(_market: str) -> dict:
        seen["scorecard"] += 1
        return {"status": "accruing"}

    def grade(_market: str) -> dict:
        seen["grade"] += 1
        return {"available": False}

    def track_document(*_args, **_kwargs) -> dict:
        seen["track"] += 1
        return {"meta": {"n_total": 0}, "rows": []}

    def shadow_write(*_args, **_kwargs) -> None:
        seen["shadow"] += 1

    monkeypatch.setattr(board_ledger, "scorecard", scorecard)
    monkeypatch.setattr(board_ledger, "grade", grade)
    monkeypatch.setattr(track_ledger, "from_board_ledger_grade", track_document)
    monkeypatch.setattr(track_ledger, "atomic_write", lambda *_a, **_k: None)
    monkeypatch.setattr(board_shadow, "write_shadow", shadow_write)
    monkeypatch.setattr(
        build_canada.config,
        "load",
        lambda: {"storage": {"site_dir": str(tmp_path)}},
    )
    return seen


def test_off_nightly_render_skips_append_without_false_error(
    monkeypatch, tmp_path: Path
) -> None:
    """A read-only render must neither attempt an append nor report failure."""
    setups = _setups()
    seen = _stub_read_side(monkeypatch, tmp_path)
    append_calls: list[tuple] = []

    def append_board(*args, **kwargs) -> int:
        append_calls.append((args, kwargs))
        return 0

    monkeypatch.setattr(build_canada, "_ledger_advance_enabled", lambda: False)
    monkeypatch.setattr(board_ledger, "append_board", append_board)

    health = build_canada._canada_board_ledger(
        setups, {"date": "2026-09-03"}
    )

    assert append_calls == [], "off-nightly renders must not enter the append path"
    assert not any(_is_error(row) for row in health), health
    assert setups["board_track"] == {"status": "accruing"}
    assert seen["scorecard"] == 1
    assert seen["grade"] == 1
    assert seen["track"] == 1
    assert seen["shadow"] == 1


def test_armed_nightly_zero_append_remains_loud(
    monkeypatch, tmp_path: Path
) -> None:
    """An armed nightly lane returning zero is still a real health failure."""
    setups = _setups()
    _stub_read_side(monkeypatch, tmp_path)
    monkeypatch.setattr(build_canada, "_ledger_advance_enabled", lambda: True)
    monkeypatch.setattr(board_ledger, "append_board", lambda *_a, **_k: 0)

    health = build_canada._canada_board_ledger(
        setups, {"date": "2026-09-03"}
    )

    errors = [row for row in health if _is_error(row)]
    assert len(errors) == 1
    assert errors[0]["rows"] == 0
    assert "append wrote 0 rows" in errors[0]["en"]


def test_armed_nightly_success_is_healthy(monkeypatch, tmp_path: Path) -> None:
    """A successful authorized append must not create a health finding."""
    setups = _setups()
    _stub_read_side(monkeypatch, tmp_path)
    monkeypatch.setattr(build_canada, "_ledger_advance_enabled", lambda: True)
    monkeypatch.setattr(board_ledger, "append_board", lambda *_a, **_k: 1)

    health = build_canada._canada_board_ledger(
        setups, {"date": "2026-09-03"}
    )

    assert not any(_is_error(row) for row in health), health


def test_armed_nightly_exception_remains_loud(monkeypatch, tmp_path: Path) -> None:
    """Exceptions in the authorized append path remain customer-visible errors."""
    setups = _setups()
    _stub_read_side(monkeypatch, tmp_path)
    monkeypatch.setattr(build_canada, "_ledger_advance_enabled", lambda: True)

    def explode(*_args, **_kwargs) -> int:
        raise RuntimeError("synthetic append failure")

    monkeypatch.setattr(board_ledger, "append_board", explode)

    health = build_canada._canada_board_ledger(
        setups, {"date": "2026-09-03"}
    )

    errors = [row for row in health if _is_error(row)]
    assert len(errors) == 1
    assert "FAILED" in errors[0]["en"]
