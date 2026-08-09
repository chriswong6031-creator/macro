"""`date` in data/china_zt_pool/pool.parquet is the TRADE date, never the run date.

Eastmoney's stock_zt_pool_em CLAMPS instead of 404-ing: asked for any date at or after the
last published session it serves THAT session's pool.  The collector used to walk back over
raw calendar days and stamp the date it had ASKED for, so a Saturday run relabelled Friday's
pool as Saturday — 11 of the store's 47 dates were non-sessions on 2026-08-08, each one
byte-identical to the session before it.

Pinned here, all offline (the vendor call is stubbed):
  • the session calendar comes from our OWN store (data/china_stocks_raw), holidays included;
  • a clamped weekend/holiday response is stamped with the SESSION date or not at all;
  • a re-run REPLACES that session's rows wholesale — freshest wins, a name that left the
    pool is retired, not stranded;
  • a re-run never drops another session (append-only ACROSS dates);
  • a missing older session is back-filled by a later run (the old walk-back lost 3);
  • scripts/heal_cn_zt_pool_dates re-keys legacy run-dated rows and refuses to collapse two
    payloads that actually differ.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config


# ── fixtures ──────────────────────────────────────────────────────────────────

# 2026-07-31 Fri, 08-03 Mon .. 08-07 Fri are sessions; 08-01/02 and 08-08/09 are weekends.
SESSIONS = ["2026-07-31", "2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07"]


def _raw_store(root: Path, sessions: list[str], names: int = 3) -> None:
    """A minimal data/china_stocks_raw — the collector's only session calendar."""
    d = root / "china_stocks_raw"
    d.mkdir(parents=True, exist_ok=True)
    idx = pd.to_datetime(sessions)
    for i in range(names):
        pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0,
                      "volume": 1}, index=idx).to_parquet(d / f"60000{i}.SS.parquet")


def _vendor_frame(tickers: list[str], seal: float = 1.0) -> pd.DataFrame:
    """A stock_zt_pool_em-shaped frame (substring column matching, as the parser does)."""
    return pd.DataFrame({
        "代码": tickers,
        "名称": [f"n{t}" for t in tickers],
        "连板数": [2] * len(tickers),
        "封板资金": [seal * 1e8] * len(tickers),
        "炸板次数": [0] * len(tickers),
        "换手率": [11.0] * len(tickers),
        "所属行业": ["半导体"] * len(tickers),
    })


@pytest.fixture()
def zt(tmp_path, monkeypatch):
    """china_zt_pool bound to a tmp data dir, with the vendor call under our control."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    import importlib
    from collectors import china_zt_pool as mod
    importlib.reload(mod)                      # OUT is resolved at import time
    _raw_store(tmp_path, SESSIONS)
    yield mod
    importlib.reload(mod)                      # never leave a tmp OUT bound for other suites


def _clamping_vendor(published: dict[str, pd.DataFrame]):
    """The vendor as measured: an unpublished/non-session date is served the newest pool."""
    newest = max(published)

    def _pool_for(yyyymmdd: str):
        iso = f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"
        if iso in published:
            return published[iso]
        return published[newest] if iso > newest else None
    return _pool_for


# ── the session calendar ──────────────────────────────────────────────────────

def test_session_calendar_reads_our_own_store(zt):
    assert set(zt.session_calendar()) == set(SESSIONS)


def test_candidates_are_sessions_only_newest_first(zt):
    cands = zt.candidate_sessions(_dt.date(2026, 8, 8), zt.session_calendar())
    assert cands[0] == "2026-08-07"                       # Saturday resolves DOWN to Friday
    assert cands == sorted(cands, reverse=True)
    assert not {"2026-08-08", "2026-08-01", "2026-08-02"} & set(cands)   # no weekend ever


def test_candidates_fall_back_to_weekdays_without_a_calendar(zt):
    cands = zt.candidate_sessions(_dt.date(2026, 8, 8), frozenset())
    assert "2026-08-08" not in cands and "2026-08-02" not in cands       # weekend still out
    assert "2026-08-07" in cands


# ── the defect: a Saturday run must not mint a Saturday session ───────────────

def test_saturday_run_stamps_the_friday_session(zt, monkeypatch):
    friday = _vendor_frame(["600001", "600002"])
    monkeypatch.setattr(zt, "_pool_for", _clamping_vendor({"2026-08-07": friday}))

    assert zt.refresh(anchor=_dt.date(2026, 8, 8)) == 2
    df = pd.read_parquet(zt.OUT)
    assert set(df["date"]) == {"2026-08-07"}              # NOT 2026-08-08
    assert set(df["date"]) <= set(SESSIONS)


def test_no_stored_date_is_ever_a_non_session(zt, monkeypatch):
    """The invariant, run over a week of daily collections including both weekend days."""
    published = {d: _vendor_frame([f"60000{i}" for i in range(1, 3 + n)])
                 for n, d in enumerate(SESSIONS)}
    monkeypatch.setattr(zt, "_pool_for", _clamping_vendor(published))
    for day in pd.date_range("2026-08-03", "2026-08-09"):
        zt.refresh(anchor=day.date())
    df = pd.read_parquet(zt.OUT)
    assert set(df["date"]) <= set(SESSIONS)
    assert "2026-08-08" not in set(df["date"]) and "2026-08-09" not in set(df["date"])


def test_clamped_pool_is_not_stamped_as_a_second_session(zt, monkeypatch):
    """A session the vendor has not published yet still serves the previous pool."""
    published = {"2026-08-06": _vendor_frame(["600001", "600002"])}
    monkeypatch.setattr(zt, "_pool_for", _clamping_vendor(published))
    zt.refresh(anchor=_dt.date(2026, 8, 6))
    # next session, vendor still serving 08-06's pool
    zt.refresh(anchor=_dt.date(2026, 8, 7))
    df = pd.read_parquet(zt.OUT)
    assert set(df["date"]) == {"2026-08-06"}             # 08-07 refused, not duplicated


# ── re-run semantics: replace the session, keep every other one ───────────────

def test_rerun_replaces_the_session_wholesale_freshest_wins(zt, monkeypatch):
    anchor = _dt.date(2026, 8, 7)
    monkeypatch.setattr(zt, "_pool_for",
                        _clamping_vendor({"2026-08-07": _vendor_frame(["600001", "600002"])}))
    zt.refresh(anchor=anchor)
    # the final pool is SMALLER — 600002 broke its seal after the partial scrape
    monkeypatch.setattr(zt, "_pool_for",
                        _clamping_vendor({"2026-08-07": _vendor_frame(["600001"], seal=9.0)}))
    zt.refresh(anchor=anchor)

    df = pd.read_parquet(zt.OUT)
    assert set(df["ticker"]) == {"600001.SS"}            # the retired name is GONE, not stranded
    assert len(df) == 1
    assert df["seal_fund_yi"].iloc[0] == pytest.approx(9.0)   # freshest wins


def test_rerun_never_drops_an_earlier_session(zt, monkeypatch):
    published = {"2026-08-06": _vendor_frame(["600001"]),
                 "2026-08-07": _vendor_frame(["600002", "600003"])}
    monkeypatch.setattr(zt, "_pool_for", _clamping_vendor(published))
    zt.refresh(anchor=_dt.date(2026, 8, 6))
    zt.refresh(anchor=_dt.date(2026, 8, 7))
    zt.refresh(anchor=_dt.date(2026, 8, 7))               # and again, same day

    df = pd.read_parquet(zt.OUT)
    assert sorted(df["date"].unique()) == ["2026-08-06", "2026-08-07"]
    assert len(df[df["date"] == "2026-08-06"]) == 1        # history intact


def test_a_session_missed_on_the_day_is_filled_by_a_later_run(zt, monkeypatch):
    """The old walk-back stopped at the newest populated date and skipped the gap forever."""
    published = {d: _vendor_frame([f"60000{i}"]) for i, d in enumerate(SESSIONS[-3:], start=1)}
    late = {k: v for k, v in published.items() if k != "2026-08-06"}
    monkeypatch.setattr(zt, "_pool_for", _clamping_vendor(late))       # 08-06 never published
    zt.refresh(anchor=_dt.date(2026, 8, 6))
    assert "2026-08-06" not in set(pd.read_parquet(zt.OUT)["date"])

    monkeypatch.setattr(zt, "_pool_for", _clamping_vendor(published))  # it lands later
    zt.refresh(anchor=_dt.date(2026, 8, 7))
    assert {"2026-08-06", "2026-08-07"} <= set(pd.read_parquet(zt.OUT)["date"])


# ── the one-time heal of the rows already on disk ─────────────────────────────

def _legacy_store(path: Path) -> None:
    """Friday's pool, then the same pool relabelled Saturday and Sunday (what shipped)."""
    body = [{"ticker": "600001.SS", "name": "a", "consec_boards": 2, "seal_fund_yi": 1.0,
             "failed_seals": 0, "turnover_pct": 10.0, "sector": "s"},
            {"ticker": "600002.SS", "name": "b", "consec_boards": 1, "seal_fund_yi": 2.0,
             "failed_seals": 1, "turnover_pct": 20.0, "sector": "s"}]
    rows = []
    for d, asof in (("2026-08-06", "2026-08-06"), ("2026-08-07", "2026-08-07"),
                    ("2026-08-08", "2026-08-08"), ("2026-08-09", "2026-08-09")):
        rows += [{**r, "date": d, "asof": asof} for r in body]
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def test_heal_rekeys_run_dated_rows_onto_their_session(tmp_path, zt):
    from scripts import heal_cn_zt_pool_dates as heal_mod
    p = tmp_path / "china_zt_pool" / "pool.parquet"
    _legacy_store(p)

    n, note = heal_mod.heal(p, zt.session_calendar(), write=True)
    df = pd.read_parquet(p)
    assert n == 4 and "re-keyed" in note
    assert sorted(df["date"].unique()) == ["2026-08-06", "2026-08-07"]
    assert len(df) == 4                                   # the two re-serves collapsed away
    # idempotent
    assert heal_mod.heal(p, zt.session_calendar(), write=True) == (0, "clean")


def test_heal_refuses_to_collapse_two_different_payloads(tmp_path, zt):
    from scripts import heal_cn_zt_pool_dates as heal_mod
    p = tmp_path / "china_zt_pool" / "pool.parquet"
    _legacy_store(p)
    df = pd.read_parquet(p)
    df.loc[df["date"] == "2026-08-08", "seal_fund_yi"] = 99.0     # not a re-serve
    df.to_parquet(p, index=False)

    n, note = heal_mod.heal(p, zt.session_calendar(), write=True)
    assert n == 0 and note.startswith("ABORT")
    assert len(pd.read_parquet(p)) == 8                            # untouched


def test_heal_recovers_a_session_that_was_only_ever_stored_run_dated(tmp_path, zt):
    from scripts import heal_cn_zt_pool_dates as heal_mod
    p = tmp_path / "china_zt_pool" / "pool.parquet"
    _legacy_store(p)
    df = pd.read_parquet(p)
    df = df[df["date"] != "2026-08-07"]                             # Friday itself never stored
    df.to_parquet(p, index=False)

    heal_mod.heal(p, zt.session_calendar(), write=True)
    out = pd.read_parquet(p)
    assert "2026-08-07" in set(out["date"])                         # relabelled, not dropped

