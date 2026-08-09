"""GEX board artifacts share one settled US-equity session date."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from lib.gex_state_index import build_index
from scripts import build_gex_board as bg


def test_weekday_after_settlement_resolves_to_same_day_session():
    instant = datetime(2026, 7, 30, 22, 0, tzinfo=timezone.utc)  # Thu 18:00 ET
    assert bg._resolve_session(instant) == date(2026, 7, 30)


def test_weekday_before_settlement_resolves_to_prior_session():
    instant = datetime(2026, 7, 30, 19, 0, tzinfo=timezone.utc)  # Thu 15:00 ET
    assert bg._resolve_session(instant) == date(2026, 7, 29)


def test_weekend_resolves_to_friday_session():
    instant = datetime(2026, 8, 1, 15, 0, tzinfo=timezone.utc)  # Sat 11:00 ET
    assert bg._resolve_session(instant) == date(2026, 7, 31)


def test_exchange_holiday_resolves_to_previous_session():
    instant = datetime(2026, 9, 7, 22, 0, tzinfo=timezone.utc)  # Labor Day
    assert bg._resolve_session(instant) == date(2026, 9, 4)


def test_payload_manifest_archive_and_receipt_share_session(tmp_path, monkeypatch):
    session = date(2026, 7, 31)
    seen_meta = {}

    def fake_model(chain, spot, cfg, *, meta, history):
        seen_meta.update(meta)
        return {
            "summary": {
                "spot": spot,
                "regime": "long",
                "tier": "full",
                "net_gex_bn": 1.2,
                "gamma_flip": 499.0,
                "dist_to_flip_pct": 0.2,
                "iv30": 15.0,
                "call_wall": 510.0,
                "put_wall": 490.0,
                "max_pain": 500.0,
                "put_call_oi_ratio": 1.1,
                "n_strikes": 20,
                "top_oi_share": 0.2,
            },
            "expected_move": {"daily_pct": 1.0},
            "walls": {"by_strike": []},
        }

    monkeypatch.setattr(bg, "_fetch_chain", lambda adapter, sym: (object(), 500.0))
    monkeypatch.setattr("engine.gex_model.build_model", fake_model)
    monkeypatch.setattr(bg, "_history", lambda key: [])

    class Adapter:
        cfg = {"gex": {}}

    row = {"sym": "SPY", "key": "SPY", "en": "S&P 500 ETF", "zh": "", "grp": "ETF"}
    model, manifest = bg._build_one(Adapter(), row, session)
    assert seen_meta["asof"] == "2026-07-31"
    assert manifest["asof"] == "2026-07-31"

    bg._write_archive_snapshot([manifest], tmp_path, session)
    archive = json.loads((tmp_path / "gex" / "latest.json").read_text())
    assert archive["asof"] == "2026-07-31"

    state = bg._compute_and_write_gex_state(model, "SPY", tmp_path / "state", session)
    assert state is not None
    assert state["asof"] == "2026-07-31T16:00:00-04:00"
    state_index = build_index(tmp_path / "state")
    assert state_index["rows"]["SPY"]["asof"] == "2026-07-31"


def test_builder_has_no_independent_calendar_date_stamps():
    source = Path(bg.__file__).read_text()
    assert "date.today()" not in source
    assert "nyse_calendar.session_date()" not in source
