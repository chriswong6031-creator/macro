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

import pytest  # noqa: E402

from lib import config, delisted_symbols  # noqa: E402
from scripts.fetch_basket_ohlcv import (  # noqa: E402
    COLS,
    MAINTAINED_FINVIZ_FILTERS,
    _membership_tickers,
    _removed_members,
    _absent_from_all_rungs,
    _resolve_universe,
    _sessions_behind,
    _store_tickers,
    check_membership_staleness,
)


@pytest.fixture(autouse=True)
def _clear_ledger_cache():
    """`delisted_symbols.ledger()` is lru_cached and reads a REPO-ABSOLUTE path, so a test
    that repoints it would otherwise leak its fixture into every later test in the process
    (and inherit the live ledger itself). Cleared on both sides."""
    delisted_symbols.ledger.cache_clear()
    yield
    delisted_symbols.ledger.cache_clear()


def _write_ledger(tmp_path: Path, monkeypatch, rows: dict[str, dict]) -> None:
    """Point the exit ledger at a fixture. Rows need the four fields lib/delisted_symbols
    requires (`company`, `last_session`, `delisted_on`, `reason`) or they are dropped."""
    p = tmp_path / "delisted_symbols.yml"
    body = ["symbols:"]
    for t, r in rows.items():
        body.append(f"  {t}:")
        for k, v in r.items():
            body.append(f"    {k}: {'null' if v is None else repr(str(v))}")
    p.write_text("\n".join(body) + "\n")
    monkeypatch.setattr(delisted_symbols, "LEDGER_PATH", p)
    delisted_symbols.ledger.cache_clear()


def _exit_row(**over) -> dict:
    row = {"company": "Gone Corp", "last_session": "2026-07-01",
           "delisted_on": "2026-07-02", "reason": "acquisition"}
    row.update(over)
    return row


def _write_finviz(tmp_path: Path, flt: str, tickers: list[str]) -> None:
    p = tmp_path / "finviz_screener" / f"{flt}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"rows": [{"ticker": t} for t in tickers]}))


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


# ------------------------ delisted BEFORE anyone curated the row (MAG/GATO, 2026-08-07)
# BLD above is the ordinary shape: a live member whose security later stopped existing, so
# its history is real and worth repairing — which is why the FETCH universe deliberately
# keeps removed members. MAG and GATO are the other shape. Both had already been acquired
# when silver_miners was curated on 2026-08-05 (MAG: Pan American Silver, Form 25-NSE
# 2025-09-04; GATO: First Majestic Silver, Form 25-NSE 2025-01-16 — and both acquirers are
# themselves members of the sleeve). There is no history on disk to repair and the vendor
# can never return one, so keeping them in the fetch universe would request two dead
# symbols nightly forever. They were also the ONLY two members of any basket with no price
# series on any rung, which is why the all-rungs census was screaming about a hole no
# fetch could ever fill.
def test_a_member_delisted_before_curation_leaves_the_fetch_universe(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _write_membership_rows(tmp_path, {"silver_miners": [
        {"ticker": "LIVE"},
        # ordinary exit: removed, but its tape existed — stays in the FETCH universe
        {"ticker": "GONE", "removed": "2026-07-01"},
        # never traded as a member: out of BOTH universes
        {"ticker": "DEAD", "removed": "2025-09-04", "delisted_before_curation": True},
    ]})
    assert _membership_tickers(active_only=True) == ["LIVE"]
    assert _membership_tickers() == ["GONE", "LIVE"]
    assert _resolve_universe([], [], False) == ["GONE", "LIVE"]


def test_mag_and_gato_are_stamped_delisted_in_live_membership():
    """Un-stamping either row silently puts a dead symbol back on the nightly request
    list and re-arms the all-rungs coverage alarm on a hole nothing can fill."""
    p = Path(__file__).resolve().parent.parent / "data" / "baskets" / "membership.json"
    rows = {m["ticker"]: m for b in json.loads(p.read_text())["baskets"].values()
            for m in b.get("members", []) if m.get("ticker") in {"MAG", "GATO"}}
    assert set(rows) == {"MAG", "GATO"}
    for t, m in rows.items():
        assert m.get("removed"), f"{t} lost its exit stamp"
        assert m.get("delisted_before_curation") is True
        assert "25-NSE" in (m.get("rationale") or ""), (
            f"{t}'s exit must carry its SEC exchange-delisting receipt")
    # the LIVE file, not a fixture: neither symbol may reach the nightly request list
    live_universe = set(_membership_tickers())
    assert not ({"MAG", "GATO"} & live_universe)
# ------------------------------------------------- absent from ALL rungs (2026-08-05)
# Absence from THIS store is graceful degradation — engine/basket_index falls through to
# data/stocks, data/china_stocks and data/yahoo. Absence from every rung is data loss: the
# basket renders and grades on N-1 members and its coverage receipt just rounds down. MMC
# was dark on all four for seven months (Marsh renamed MMC->MRSH 2026-01-14) and the only
# tell was a "structural" line in a coverage receipt.
def _write_rung(tmp_path: Path, rung: tuple[str, ...], ticker: str) -> None:
    p = tmp_path.joinpath(*rung) / f"{ticker}.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"close": [1.0]}, index=pd.DatetimeIndex(["2026-07-15"], name="Date")).to_parquet(p)


def test_absent_from_all_rungs_ignores_names_a_fallback_covers(tmp_path):
    _write_rung(tmp_path, ("stocks",), "COVERED_US")
    _write_rung(tmp_path, ("china_stocks",), "600519.SS")
    _write_rung(tmp_path, ("yahoo",), "COVERED_Y")
    dark = _absent_from_all_rungs(
        ["COVERED_US", "600519.SS", "COVERED_Y", "DARK"], tmp_path)
    assert dark == ["DARK"]


def test_census_warns_loudly_only_for_members_dark_on_every_rung(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _write_membership(tmp_path, ["FRESH", "FALLBACK", "DARK"])
    _write_ohlcv(tmp_path, "FRESH", "2026-07-15")
    _write_rung(tmp_path, ("yahoo",), "FALLBACK")     # missing here, but covered downstream

    payload = check_membership_staleness(ops_alert=False)
    assert payload["missing"] == ["DARK", "FALLBACK"]      # both absent from THIS store
    assert payload["absent_all_rungs"] == ["DARK"]         # only one is actual loss
    assert payload["n_absent_all_rungs"] == 1

    lines = [ln for ln in capsys.readouterr().out.splitlines() if "no-price-series" in ln]
    assert len(lines) == 1, "the all-rungs disclosure must be emitted exactly once"
    # GitHub drops an annotation that does not START the line — a logger prefix ("WARNING
    # ::warning ...") reviews as an alarm, runs clean, and produces nothing in the summary.
    assert lines[0].startswith("::warning title=basket-member-no-price-series::")
    assert "DARK" in lines[0] and "FALLBACK" not in lines[0]
    assert "lib/ticker_aliases" in lines[0], "the disclosure must name the usual repair"


def test_census_silent_on_all_rungs_when_every_member_resolves(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _write_membership(tmp_path, ["A", "B"])
    _write_ohlcv(tmp_path, "A", "2026-07-15")
    _write_rung(tmp_path, ("stocks",), "B")

    payload = check_membership_staleness(ops_alert=False)
    assert payload["absent_all_rungs"] == []
    assert "no-price-series" not in capsys.readouterr().out


# ============================== fetch-universe drift (2026-08-20) ==============================
# The finviz screener JSONs are re-pulled nightly, so an index reconstitution silently shrank
# the maintained set — and nothing ever fetched the dropped names again, so their parquets
# froze FOREVER while engine/stage_analysis.build_universe() (which globs the store) kept
# classifying them as live. Measured that day: 2,782 files, 183 stale, 179 of them outside
# `membership ∪ finviz(idx_ndx, idx_rut)`, 110 frozen on 2026-07-10 alone. A live vendor probe
# of that cluster returned a CURRENT tape for 10 of 10 sampled names (ARWR/AXSM/BBIO/BE/AAOI/…),
# so those tapes were never dead — merely unrequested. Two halves are pinned below: the store
# now maintains itself (--store), and the census can finally SEE the whole store it owns.
def test_store_leg_keeps_a_reconstitution_dropout_in_the_fetch_universe(tmp_path, monkeypatch):
    """THE CURE. A name on disk that no membership row and no index universe still claims
    must stay in the fetch universe — otherwise leaving an index freezes its file forever."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _write_membership(tmp_path, ["MEM1"])
    _write_ohlcv(tmp_path, "DROPPED", "2026-07-10")     # the 07-10 reconstitution shape
    _write_ohlcv(tmp_path, "MEM1", "2026-07-15")

    assert _store_tickers() == ["DROPPED", "MEM1"]
    # without the store leg the dropped name is invisible to the fetch — the bug
    assert _resolve_universe([], ["FV1"], False) == ["FV1"]
    # with it, the name keeps being maintained and its tape can advance again
    assert _resolve_universe([], ["FV1"], False, True) == ["DROPPED", "FV1", "MEM1"]


def test_store_leg_does_not_resurrect_a_resolved_exit(tmp_path, monkeypatch):
    """The one lawful way out of the fetch universe. A security that stopped existing can
    never return, and requesting it nightly forever parks a permanent entry in the
    missing-symbol warning — which is what trains a reader to ignore the next real outage."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _write_membership(tmp_path, ["MEM1", "DEADMEM"])
    _write_ohlcv(tmp_path, "DEADSTORE", "2026-07-01")
    _write_ledger(tmp_path, monkeypatch, {"DEADSTORE": _exit_row(), "DEADMEM": _exit_row()})

    # every derived leg is filtered — store (+finviz), and membership when it is unioned in
    assert _resolve_universe([], ["DEADFV"], False, True) == ["DEADFV"], (
        "a resolved exit must leave the store leg")
    assert _resolve_universe([], ["DEADFV"], True, True) == ["DEADFV", "MEM1"], (
        "...and the membership leg")
    assert _resolve_universe([], [], False) == ["MEM1"], (
        "...including the no-args membership default the nightly's first call uses")


def test_an_explicit_ticker_request_still_honours_a_dead_symbol(tmp_path, monkeypatch):
    """Asking for a dead symbol BY NAME is a deliberate backfill/debug act, not the
    nightly's standing request list — only the derived legs are filtered."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _write_membership(tmp_path, ["MEM1"])
    _write_ledger(tmp_path, monkeypatch, {"DEAD": _exit_row()})
    assert _resolve_universe(["DEAD"], [], False) == ["DEAD"]


def test_census_sends_an_unsponsored_laggard_to_its_own_bucket(tmp_path, monkeypatch):
    """The 179. Sponsored-and-lagging is an OUTAGE; unsponsored-and-lagging is a name an
    index dropped. They are separated because their cures differ — and because the old
    census reported `n_stale: 1` on a store holding 183 stale files by seeing neither."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _write_membership(tmp_path, ["MEM1"])
    _write_ohlcv(tmp_path, "MEM1", "2026-07-15")
    _write_ohlcv(tmp_path, "ORPHAN", "2026-06-29")      # on disk, claimed by nobody

    payload = check_membership_staleness(ops_alert=False)
    assert payload["stale"] == {}, "an orphan is not a broken pull"
    assert payload["unsponsored"] == {"ORPHAN": {"last": "2026-06-29", "sessions_behind": 11}}
    assert payload["n_unsponsored_stale"] == 1
    assert payload["n_store_files"] == 2, "the census must judge the whole store"
    # ...and it does NOT turn the top line red: the genuinely-stopped tail can only be
    # cleared by curating exit rows, and a status that stays red until someone does is a
    # status nobody reads.
    assert payload["status"] == "ok"


def test_census_flags_a_stale_name_sponsored_only_by_a_declared_index(tmp_path, monkeypatch):
    """The NDX/Russell blind spot. A broken pull on an index name was invisible for as long
    as this census existed — it asked the 702 active members and nothing else."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _write_membership(tmp_path, ["MEM1"])
    _write_finviz(tmp_path, MAINTAINED_FINVIZ_FILTERS[0], ["IDXNAME"])
    _write_ohlcv(tmp_path, "MEM1", "2026-07-15")
    _write_ohlcv(tmp_path, "IDXNAME", "2026-06-29")

    payload = check_membership_staleness(ops_alert=False)
    assert set(payload["stale"]) == {"IDXNAME"}
    assert payload["unsponsored"] == {}, "a declared index universe DOES sponsor a name"
    assert payload["n_sponsored"] == 2
    assert payload["status"] == "stale"


def test_census_reads_the_declared_filters_not_the_fetch_call(tmp_path, monkeypatch, capsys):
    """The #776 property, preserved. A census parameterised from the fetch's own argv goes
    blind exactly when the fetch loses a universe — the failure it exists to catch. The
    filters are DECLARED in-module, so a screener that resolves to nothing is reported as
    such instead of quietly shrinking the ruler and re-labelling its names as orphans."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _write_membership(tmp_path, ["MEM1"])
    _write_ohlcv(tmp_path, "MEM1", "2026-07-15")

    payload = check_membership_staleness(ops_alert=False)
    assert payload["maintained_finviz_filters"] == list(MAINTAINED_FINVIZ_FILTERS)
    assert payload["finviz_unresolved"] == list(MAINTAINED_FINVIZ_FILTERS)
    lines = [ln for ln in capsys.readouterr().out.splitlines() if "finviz-unresolved" in ln]
    assert len(lines) == 1 and lines[0].startswith("::warning title=basket-ohlcv-finviz-unresolved::")
    assert "screener pull" in lines[0], "the disclosure must separate a failed pull from a recon"


def test_census_discloses_a_resolved_exit_at_any_lag_and_never_alarms_on_it(tmp_path, monkeypatch):
    """The AVB shape. AvalonBay was acquired 2026-08-17 with a well-formed exit row already
    in the ledger, yet on 2026-08-20 its store tip sat ONE session behind the max because
    the vendor flat-forwards a dead symbol — under the threshold, so nothing had flagged it,
    and days from becoming BLD's permanent red line a second time. Nothing read the ledger."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _write_membership(tmp_path, ["MEM1", "PADDED", "LONGDEAD"])
    _write_ohlcv(tmp_path, "MEM1", "2026-07-15")
    _write_ohlcv(tmp_path, "PADDED", "2026-07-14")      # 1 session behind: under threshold
    _write_ohlcv(tmp_path, "LONGDEAD", "2026-06-29")    # 11 behind: would have been stale
    _write_ledger(tmp_path, monkeypatch, {
        "PADDED": _exit_row(last_session="2026-07-09", delisted_on="2026-07-10"),
        "LONGDEAD": _exit_row()})

    payload = check_membership_staleness(ops_alert=False)
    assert payload["status"] == "ok"
    assert payload["stale"] == {} and payload["unsponsored"] == {}
    assert payload["n_retired"] == 2
    # the TRUE tape end is reported next to the store tip, so padding reads as padding
    assert payload["retired"]["PADDED"]["last"] == "2026-07-14"
    assert payload["retired"]["PADDED"]["last_session"] == "2026-07-09"
    assert payload["retired"]["PADDED"]["delisted_on"] == "2026-07-10"
    assert payload["retired"]["LONGDEAD"]["sessions_behind"] == 11
    # a resolved exit is never ALSO reported as a curator exit — one disposition per name
    assert payload["inactive"] == {}


def test_census_unsponsored_annotation_starts_the_line_and_names_both_cures(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _write_membership(tmp_path, ["MEM1"])
    _write_ohlcv(tmp_path, "MEM1", "2026-07-15")
    _write_ohlcv(tmp_path, "ORPHAN", "2026-06-29")

    check_membership_staleness(ops_alert=False)
    lines = [ln for ln in capsys.readouterr().out.splitlines() if "unsponsored-stale" in ln]
    assert len(lines) == 1
    # GitHub silently drops an annotation that does not START the line (a logger prefix
    # reviews as an alarm, runs clean, and produces nothing in the Actions summary).
    assert lines[0].startswith("::warning title=basket-ohlcv-unsponsored-stale::")
    assert "ORPHAN" in lines[0]
    assert "delisted_symbols.yml" in lines[0], "must name the retire cure"
    assert "re-sponsorship" in lines[0], "must name the re-add cure"


def test_census_is_silent_on_unsponsored_when_the_store_is_maintained(tmp_path, monkeypatch, capsys):
    """Post-cure steady state: --store keeps an index drop-out's tape moving, so a name
    that merely lost its sponsor is a COUNT, not an alarm."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _write_membership(tmp_path, ["MEM1"])
    _write_ohlcv(tmp_path, "MEM1", "2026-07-15")
    _write_ohlcv(tmp_path, "DROPPED_BUT_FETCHED", "2026-07-15")   # self-healed

    payload = check_membership_staleness(ops_alert=False)
    assert payload["n_unsponsored_stale"] == 0 and payload["n_unsponsored_fresh"] == 1
    assert "unsponsored-stale" not in capsys.readouterr().out


def test_live_store_is_not_judged_by_the_membership_subset():
    """The regression that let 179 orphaned files reach production, pinned against the LIVE
    store: the census reported `n_stale: 1` over 2,782 files because its ruler was the 702
    active members. Any future narrowing of the ruler back to membership fails here."""
    odir = Path(__file__).resolve().parent.parent / "data" / "baskets" / "ohlcv"
    if not odir.is_dir() or not any(odir.glob("*.parquet")):
        pytest.skip("deep OHLCV store not checked out (sparse worktree)")
    payload = check_membership_staleness(ops_alert=False)
    assert payload["n_store_files"] == len(list(odir.glob("*.parquet")))
    assert payload["n_store_files"] > payload["n_members"], (
        "the store is larger than the membership subset — the census must judge the store")
    assert payload["n_sponsored"] >= payload["n_members"]


# ------------------------------------------------------------------ collect.py wiring pin
def test_collect_wiring_maintains_the_store_itself():
    """Without --store on a nightly call, a name an index drops is never fetched again and
    its parquet freezes forever while Stage keeps classifying it (179 files, 2026-08-20)."""
    src = (Path(__file__).resolve().parent.parent / "scripts" / "collect.py").read_text()
    assert '"--store"' in src, (
        "nightly fetch_basket_ohlcv wiring lost the --store leg — an index reconstitution "
        "silently orphans every name it drops, and nothing refetches it")


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
