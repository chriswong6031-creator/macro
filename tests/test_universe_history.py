"""Point-in-time index-membership ledger (go-forward survivorship fix). Pins the
upsert semantics (present refreshes last_seen; dropped freezes it + goes inactive)
and the as_of reconstruction, on a temp ledger (no real data dir needed)."""
from __future__ import annotations

import pandas as pd
import pytest

from engine import universe_history as uh


@pytest.fixture
def temp_ledger(tmp_path, monkeypatch):
    led = tmp_path / "membership.parquet"
    monkeypatch.setattr(uh, "_ledger_path", lambda: led)
    return led


def _constituents(monkeypatch, members):
    df = pd.DataFrame({"ticker": members, "group": "sp500",
                       "name": members, "sector": "—"})
    monkeypatch.setattr(uh, "_current_constituents", lambda: df)


def test_first_run_seeds_all_active(temp_ledger, monkeypatch):
    _constituents(monkeypatch, ["AAA", "BBB", "CCC"])
    led = uh.update_membership("2026-01-01")
    assert led["active"].all() and len(led) == 3
    assert (led["first_seen"] == pd.Timestamp("2026-01-01")).all()


def test_dropped_member_goes_inactive_with_frozen_last_seen(temp_ledger, monkeypatch):
    _constituents(monkeypatch, ["AAA", "BBB", "CCC"])
    uh.update_membership("2026-01-01")
    _constituents(monkeypatch, ["AAA", "BBB", "DDD"])     # CCC dropped, DDD added
    led = uh.update_membership("2026-02-01").set_index("ticker")
    assert led.loc["CCC", "active"] == False              # noqa: E712 — dropped
    assert led.loc["CCC", "last_seen"] == pd.Timestamp("2026-01-01")   # frozen at last membership
    assert led.loc["DDD", "active"] == True and led.loc["DDD", "first_seen"] == pd.Timestamp("2026-02-01")
    assert led.loc["AAA", "last_seen"] == pd.Timestamp("2026-02-01")   # refreshed


def test_as_of_members_reconstructs_point_in_time(temp_ledger, monkeypatch):
    # daily-style confirmations advance last_seen (gaps are conservatively excluded —
    # as_of returns only members CONFIRMED on a run spanning the date).
    _constituents(monkeypatch, ["AAA", "BBB", "CCC"])
    uh.update_membership("2026-01-01")
    uh.update_membership("2026-01-15")                    # CCC still present -> last_seen=Jan15
    _constituents(monkeypatch, ["AAA", "BBB", "DDD"])
    uh.update_membership("2026-02-01")                    # CCC dropped, DDD added
    jan = uh.as_of_members("2026-01-15")
    assert "CCC" in jan and "DDD" not in jan              # CCC confirmed Jan15, DDD not yet
    feb = uh.as_of_members("2026-02-01")
    assert "DDD" in feb and "CCC" not in feb              # DDD in, CCC frozen at Jan15


def test_as_of_empty_ledger():
    # no monkeypatch of _ledger_path here, but load returns None on a missing file in tmp
    assert uh.as_of_members("2026-01-01", ledger=pd.DataFrame(columns=uh.LEDGER_COLS)) == []


def test_dropped_members_returns_inactive(temp_ledger, monkeypatch):
    _constituents(monkeypatch, ["AAA", "BBB", "CCC"])
    uh.update_membership("2026-01-01")
    _constituents(monkeypatch, ["AAA", "BBB"])            # CCC dropped -> inactive
    uh.update_membership("2026-02-01")
    assert uh.dropped_members() == ["CCC"]
    assert uh.dropped_members(ledger=pd.DataFrame(columns=uh.LEDGER_COLS)) == []


def test_edgar_universe_retains_dropped(temp_ledger, monkeypatch, tmp_path):
    # the EDGAR fundamentals universe must KEEP a name after it drops from the index,
    # so the panel doesn't silently lose delisted fundamentals (survivorship).
    _constituents(monkeypatch, ["AAA", "BBB", "CCC"])
    uh.update_membership("2026-01-01")
    _constituents(monkeypatch, ["AAA", "BBB"])
    uh.update_membership("2026-02-01")
    from collectors import edgar
    from lib import config as _cfg
    monkeypatch.setattr(_cfg, "data_dir", lambda: tmp_path)   # no breadth caches -> empty "current"
    uni = edgar._universe_tickers()
    assert "CCC" in uni                                       # dropped name retained for fundamentals
