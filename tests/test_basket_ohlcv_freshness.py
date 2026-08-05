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
    _membership_tickers,
    _removed_members,
    _resolve_universe,
    _sessions_behind,
    check_membership_staleness,
)


def _write_membership(tmp_path: Path, tickers: list[str]) -> None:
    p = tmp_path / "baskets" / "membership.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"baskets": {"b1": {"members": [{"ticker": t} for t in tickers]}}}))


def _write_membership_rows(tmp_path: Path, baskets: dict[str, list[dict]]) -> None:
    """Membership with explicit member ROWS (so `removed` stamps can be exercised)."""
    p = tmp_path / "baskets" / "membership.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"baskets": {k: {"members": v} for k, v in baskets.items()}}))


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


# ------------------------------------------ removed/delisted members (BLD, 2026-08-05)
# BLD (TopBuild) was acquired by QXO — merger completed 2026-07-01, NYSE trading suspended
# before the open that day, renamed QXO Insulation LLC, Form 15-12G deregistration
# 2026-07-13. Its tape CANNOT resume: holders got cash + QXO stock, so no successor ticker
# carries BLD's price series. It read as an unexplained 22-session red line for a month
# because the census judged EVERY membership row, including exited ones — while its own
# docstring claimed "active". These pin the exit ledger as the census's ruler, and pin
# that an exited-and-stopped tape is DISCLOSED rather than silently dropped.
def test_active_only_drops_wholly_removed_but_keeps_cross_listed(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _write_membership_rows(tmp_path, {
        "housing": [{"ticker": "LIVE"}, {"ticker": "GONE", "removed": "2026-07-01"}],
        # Cross-listed exits (12 of the 15 live rows are these): active is per-TICKER, not
        # per-row. Pinned in BOTH row orders — a per-ROW filter that merely discards on a
        # `removed` row passes when the active row comes LAST and fails when it comes
        # first, so one ordering alone leaves the guard half-open.
        "crypto": [{"ticker": "AFTER", "removed": "2026-06-18"}],       # removed, then live
        "fintech": [{"ticker": "AFTER"}, {"ticker": "BEFORE"}],
        "defense": [{"ticker": "BEFORE", "removed": "2026-06-18"}],     # live, then removed
    })
    assert _membership_tickers(active_only=True) == ["AFTER", "BEFORE", "LIVE"]
    # the FETCH universe is unchanged — a removed member's history still refreshes/repairs
    assert _membership_tickers() == ["AFTER", "BEFORE", "GONE", "LIVE"]
    assert _resolve_universe([], [], False) == ["AFTER", "BEFORE", "GONE", "LIVE"]
    assert set(_removed_members()) == {"GONE"}


def test_census_discloses_removed_member_instead_of_flagging_it(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _write_membership_rows(tmp_path, {"housing": [
        {"ticker": "LIVE"},
        {"ticker": "GONE", "removed": "2026-07-01", "rationale": "DELISTED: acquired"},
    ]})
    _write_ohlcv(tmp_path, "LIVE", "2026-07-15")
    _write_ohlcv(tmp_path, "GONE", "2026-06-29")     # 11 sessions behind: would have been stale

    payload = check_membership_staleness(ops_alert=False)
    # not a broken pull -> green, and OUT of the stale count entirely
    assert payload["status"] == "ok"
    assert payload["stale"] == {} and payload["missing"] == []
    assert payload["n_members"] == 1                  # active membership is the ruler
    # ...but never invisible: the marker EXPLAINS it
    assert payload["inactive"]["GONE"] == {
        "last": "2026-06-29", "sessions_behind": 11,
        "removed": "2026-07-01", "rationale": "DELISTED: acquired"}
    marker = json.loads((tmp_path / "quality" / "basket_ohlcv_freshness.json").read_text())
    assert marker["inactive"]["GONE"]["removed"] == "2026-07-01"


def test_census_does_not_disclose_a_removed_member_whose_tape_is_fresh(tmp_path, monkeypatch):
    # 12 of the 15 exits are curation moves on names that still trade — they must not
    # clutter the disclosure, which is reserved for tapes that have actually STOPPED.
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _write_membership_rows(tmp_path, {"housing": [
        {"ticker": "LIVE"},
        {"ticker": "EXITED_AT_MAX", "removed": "2026-06-18"},
        {"ticker": "EXITED_LAGGING", "removed": "2026-06-18"},
    ]})
    _write_ohlcv(tmp_path, "LIVE", "2026-07-15")
    _write_ohlcv(tmp_path, "EXITED_AT_MAX", "2026-07-15")     # at the store max
    _write_ohlcv(tmp_path, "EXITED_LAGGING", "2026-07-14")    # 1 session behind: still trading

    payload = check_membership_staleness(ops_alert=False)
    # a tape that is merely BEHIND (not stopped) is not a delisting — the same
    # >threshold ruler the active set uses decides what counts as "stopped"
    assert payload["status"] == "ok" and payload["inactive"] == {}


def test_census_still_flags_a_stale_ACTIVE_member(tmp_path, monkeypatch):
    # the guard must not become a blanket amnesty — an un-removed laggard stays red
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _write_membership_rows(tmp_path, {"housing": [
        {"ticker": "LIVE"}, {"ticker": "BROKEN"},
        {"ticker": "GONE", "removed": "2026-07-01"}]})
    _write_ohlcv(tmp_path, "LIVE", "2026-07-15")
    _write_ohlcv(tmp_path, "BROKEN", "2026-06-29")
    _write_ohlcv(tmp_path, "GONE", "2026-06-29")

    payload = check_membership_staleness(ops_alert=False)
    assert payload["status"] == "stale"
    assert set(payload["stale"]) == {"BROKEN"} and set(payload["inactive"]) == {"GONE"}


def test_bld_is_stamped_removed_in_live_membership():
    """BLD cannot trade again — if the row is still there it MUST carry its exit stamp.
    Un-removing it silently restores the permanent red line."""
    p = Path(__file__).resolve().parent.parent / "data" / "baskets" / "membership.json"
    rows = [m for b in json.loads(p.read_text())["baskets"].values()
            for m in b.get("members", []) if m.get("ticker") == "BLD"]
    for m in rows:
        assert m.get("removed"), (
            "BLD (TopBuild) was delisted 2026-07-01 (acquired by QXO, renamed QXO "
            "Insulation LLC, Form 15-12G 2026-07-13) — no successor ticker carries its "
            "price series, so an un-removed BLD row is a permanent staleness red line")
        assert "DELIST" in (m.get("rationale") or "").upper(), (
            "BLD's exit must DISCLOSE the delisting, not read as a curation swap")


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
