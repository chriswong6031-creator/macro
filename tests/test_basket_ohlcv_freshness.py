"""Basket OHLCV membership lane + per-member staleness tripwire (2026-07-16 incident).

PR #776 switched the nightly fetch_basket_ohlcv call from membership mode to
--finviz-only; because an explicit universe REPLACES the membership default, 528 active
basket members' per-ticker parquets froze at 2026-06-29 for 11 sessions while the
aggregate as_of stayed fresh off the NDX/RUT names (build_baskets' whole-store check is
blind to a frozen subset by design). These tests pin:
  1. universe resolution — --members UNIONS membership into an explicit universe,
     membership stays the no-args default (and the #776 replace semantics stay explicit),
  2. the per-member census — >3-session laggards and missing files flagged (store-wide
     max as the ruler, non-members ignored), marker written, fresh store reads ok,
  3. the collect.py wiring — the nightly call keeps --members AND the independent
     census step, so the regression cannot silently return.

Run: .venv/bin/python -m pytest tests/test_basket_ohlcv_freshness.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from scripts.fetch_basket_ohlcv import (  # noqa: E402
    COLS,
    _resolve_universe,
    _sessions_behind,
    check_membership_staleness,
)


def _write_membership(tmp_path: Path, tickers: list[str]) -> None:
    p = tmp_path / "baskets" / "membership.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"baskets": {"b1": {"members": [{"ticker": t} for t in tickers]}}}))


def _write_ohlcv(tmp_path: Path, ticker: str, end: str, periods: int = 30) -> None:
    idx = pd.bdate_range(end=end, periods=periods)
    idx.name = "Date"
    df = pd.DataFrame({c: 1.0 for c in COLS}, index=idx)
    p = tmp_path / "baskets" / "ohlcv" / f"{ticker}.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p)


# ------------------------------------------------------------------ universe resolution
def test_resolve_universe_membership_is_default(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _write_membership(tmp_path, ["MEM1", "OVERLAP"])
    assert _resolve_universe([], [], False) == ["MEM1", "OVERLAP"]


def test_resolve_universe_explicit_replaces_membership(tmp_path, monkeypatch):
    # The #776 semantics, kept EXPLICIT: a finviz/ticker universe without --members
    # does NOT cover membership — the nightly call must pass --members.
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _write_membership(tmp_path, ["MEM1", "OVERLAP"])
    assert _resolve_universe([], ["FV1", "OVERLAP"], False) == ["FV1", "OVERLAP"]
    assert _resolve_universe(["X"], [], False) == ["X"]


def test_resolve_universe_members_flag_unions(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _write_membership(tmp_path, ["MEM1", "OVERLAP"])
    assert _resolve_universe([], ["FV1", "OVERLAP"], True) == ["FV1", "MEM1", "OVERLAP"]


# ------------------------------------------------------------------ staleness census
def test_sessions_behind_matches_incident_lag():
    # The real incident ruler: 2026-06-29 → 2026-07-15 is 11 NYSE sessions
    # (2026-07-03 is the observed July-4 holiday, weekends excluded).
    from datetime import date
    assert _sessions_behind(date(2026, 6, 29), date(2026, 7, 15)) == 11


def test_census_flags_stale_and_missing_members_only(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _write_membership(tmp_path, ["FRESH", "STALE", "MISSING"])
    _write_ohlcv(tmp_path, "FRESH", "2026-07-15")
    _write_ohlcv(tmp_path, "STALE", "2026-06-29")
    _write_ohlcv(tmp_path, "IDXOLD", "2026-07-01")   # non-member laggard: ignored

    payload = check_membership_staleness(ops_alert=False)
    assert payload["status"] == "stale"
    assert payload["store_max"] == "2026-07-15"
    assert payload["stale"] == {"STALE": {"last": "2026-06-29", "sessions_behind": 11}}
    assert payload["missing"] == ["MISSING"]
    assert "IDXOLD" not in payload["stale"]

    marker = json.loads((tmp_path / "quality" / "basket_ohlcv_freshness.json").read_text())
    assert marker["status"] == "stale" and marker["n_stale"] == 1


def test_census_threshold_is_strictly_greater(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _write_membership(tmp_path, ["FRESH", "LAG3", "LAG4"])
    _write_ohlcv(tmp_path, "FRESH", "2026-07-15")
    _write_ohlcv(tmp_path, "LAG3", "2026-07-10")     # 07-13/14/15 = 3 sessions: within
    _write_ohlcv(tmp_path, "LAG4", "2026-07-09")     # 4 sessions: stale

    payload = check_membership_staleness(ops_alert=False)
    assert set(payload["stale"]) == {"LAG4"}
    assert payload["stale"]["LAG4"]["sessions_behind"] == 4
    assert payload["n_behind_within_threshold"] == 1


def test_census_ok_when_fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _write_membership(tmp_path, ["A", "B"])
    _write_ohlcv(tmp_path, "A", "2026-07-15")
    _write_ohlcv(tmp_path, "B", "2026-07-15")

    payload = check_membership_staleness(ops_alert=False)
    assert payload["status"] == "ok"
    assert payload["stale"] == {} and payload["missing"] == []


def test_census_never_raises_on_empty_store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _write_membership(tmp_path, ["A"])
    payload = check_membership_staleness(ops_alert=False)
    assert payload["status"] == "no_store"


# ------------------------------------------------------------------ collect.py wiring pin
def test_collect_wiring_keeps_membership_and_census():
    src = (Path(__file__).resolve().parent.parent / "scripts" / "collect.py").read_text()
    # Membership coverage may be shaped as a dedicated membership-mode call (#2697) or a
    # --members union on the finviz call (#2698) — but a bare --finviz-only wiring is the
    # #776 regression (an explicit universe REPLACES membership; 528 files froze 11 sessions).
    covered = ("fetch_basket_ohlcv([])" in src) or ('"--members"' in src)
    assert covered, (
        "nightly fetch_basket_ohlcv wiring lost basket-membership coverage — an explicit "
        "--tickers/--finviz universe REPLACES the membership default (#776 regression)")
    assert "check_membership_staleness" in src, (
        "collect.py lost the independent per-member staleness census step")
