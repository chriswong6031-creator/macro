"""Tests for the live-Prophet × Stage forward-shadow (engine.prophet_stage_shadow).

Coverage (>= 8, per the task contract):
  1. PIT tag correctness — the stage-at-entry tag uses ONLY pre-signal_date data
     (a future price spike after the entry must not change the tag → look-ahead guard).
  2. Idempotent tagging — a re-run NEVER changes an already-tagged id (PIT-fixed).
  3. EC strictly-before — the last_ec tag uses the most-recent call STRICTLY before entry.
  4. Nightly-gate on grading — a non-nightly run tags but does NOT advance grades;
     the nightly lane (COLLECT_LANE=nightly) does.
  5. Fail-open on absent OHLCV/EC/prophet stores — nulls + reason, never a crash.
  6. Summary schema + is_context_only/display_only — nulls printed, no fabricated rate.
  7. Matured-vs-immature partition — only entries whose horizon has elapsed grade.
  8. win = CLEAN_LIFTOFF reuse — the summary counts CLEAN_LIFTOFF as the win, reusing
     grading.TerminalState (same ruler as the backtest).
  9. Entry enumeration — active (index) + closed (ledger) + plan files union by id.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from engine import grading, prophet_stage_shadow as pss


# --------------------------------------------------------------------------- #
# Synthetic builders (reuse the fusion test's proven Stage-2 / bench shapes).  #
# --------------------------------------------------------------------------- #
def _bdays(start: str, n: int) -> pd.DatetimeIndex:
    return pd.bdate_range(start=start, periods=n)


def _stage2_series(n: int = 500, start: str = "2020-01-01") -> pd.Series:
    """A clean rising series that classifies Stage-2 (close > rising 30w SMA)."""
    idx = _bdays(start, n)
    base = np.linspace(100, 300, n)
    noise = np.sin(np.arange(n) / 9.0) * 2.0
    return pd.Series(base + noise, index=idx)


def _bench_series(n: int = 700, start: str = "2019-06-01") -> pd.Series:
    idx = _bdays(start, n)
    return pd.Series(np.linspace(100, 130, n), index=idx)


def _write_parquet(path, close: pd.Series, vol: pd.Series | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"close": close.values}, index=close.index)
    if vol is not None:
        df["volume"] = vol.values
    else:
        df["volume"] = 1_000_000.0
    df.to_parquet(path)


# A "mature + stageable" signal date: deep enough into a 700-bar series (from 2020-01-01)
# to have >= 45 completed weeks BEFORE it (so the stage classifies, not too-young) AND
# >= 126 forward bars AFTER it (so clean15_126 matures). Bar ~300 ≈ 2021-02-24.
MATURE_SIG = "2021-02-24"


def _make_store(tmp_path, entries, bench_n: int = 1100,
                price_builder=_stage2_series, price_n: int = 700):
    """Build a fake data_root + site_root with prophet stores and OHLCV parquets.

    entries: list of (id, asset, signal_date, source) — 'plan'|'index'|'ledger'.
    Returns (data_root, site_root).
    """
    data_root = tmp_path / "data"
    site_root = tmp_path / "site"
    (data_root / "prophet").mkdir(parents=True, exist_ok=True)
    (site_root / "prophet" / "plans").mkdir(parents=True, exist_ok=True)

    # bench (SPY)
    _write_parquet(data_root / "yahoo" / "SPY.parquet", _bench_series(bench_n))

    assets = {a for (_i, a, _s, _src) in entries}
    for a in assets:
        _write_parquet(data_root / "baskets" / "ohlcv" / f"{a}.parquet",
                       price_builder(price_n))

    plans, index_entries, ledger_rows = [], [], []
    for (pid, asset, sig, src) in entries:
        if src == "plan":
            plan = {"schema": "prophet.trade_plan/v1", "id": pid, "asset": asset,
                    "direction": "BULL", "signal_date": sig, "entry": 100.0}
            (site_root / "prophet" / "plans" / f"{pid}.json").write_text(json.dumps(plan))
            plans.append(pid)
        elif src == "index":
            index_entries.append({"id": pid, "asset": asset, "direction": "BULL",
                                  "_signal_date": sig, "entry": 100.0})
        elif src == "ledger":
            ledger_rows.append({"schema": "prophet.ledger/v1", "id": pid, "asset": asset,
                                "direction": "BULL", "signal_date": sig,
                                "outcome": "EXPIRED"})

    idx = {"schema": "prophet.index/v1", "asof": "2026-07-19", "plans": index_entries}
    (site_root / "prophet" / "index.json").write_text(json.dumps(idx))
    led = site_root  # placeholder
    with (data_root / "prophet" / "ledger.jsonl").open("w") as f:
        f.write("# prophet ledger\n")
        for r in ledger_rows:
            f.write(json.dumps(r) + "\n")
    return data_root, site_root


# --------------------------------------------------------------------------- #
# 1. PIT tag correctness — future price must not leak into the entry tag.       #
# --------------------------------------------------------------------------- #
def test_pit_tag_ignores_future(tmp_path, monkeypatch):
    from engine import weinstein_stage as ws
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)

    # A long rising series with the entry at bar 300 (>=45 completed weeks before it,
    # ~600 bars after) so a LONG post-entry crash tail is possible.
    n = 900
    idx = pd.bdate_range("2019-06-01", periods=n)
    base = np.linspace(100, 320, n) + np.sin(np.arange(n) / 9.0) * 2.0
    clean = pd.Series(base, index=idx)
    sig_ts = idx[300]
    sig = str(sig_ts.date())
    pid = f"AAA-BULL-{sig.replace('-', '')}"

    data_root, site_root = _make_store(tmp_path, [(pid, "AAA", sig, "plan")])
    _write_parquet(data_root / "baskets" / "ohlcv" / "AAA.parquet", clean)

    pss.tag_entries(root=data_root, site_root=site_root)
    stage1 = list(pss._load_ledger(data_root).values())[0]["stage_at_entry"]
    assert stage1 == 2, "the rising series must tag Stage-2 at entry"

    # DETONATE the future: a long declining crash tail AFTER the signal date.
    det = clean.copy()
    post = det.index > sig_ts
    det.loc[post] = np.linspace(det.loc[sig_ts], det.loc[sig_ts] * 0.1, int(post.sum()))

    # POSITIVE CONTROL (§7.1): a NAIVE last-bar read of the detonated FULL series WOULD
    # flip the stage (to Stage-4 declining) — so if the guard were absent, the tag would
    # change. This proves the test has power to catch a look-ahead leak.
    from engine import prophet_stage_fusion as psf
    naive_full = ws.classify(det, None,
                             psf.load_bench_close(data_root))["stage"]
    assert naive_full != stage1, "positive control void — detonation must move the last-bar stage"

    _write_parquet(data_root / "baskets" / "ohlcv" / "AAA.parquet", det)
    pss.ledger_path(data_root).unlink()  # force recompute on the detonated series
    pss.tag_entries(root=data_root, site_root=site_root)
    stage2 = list(pss._load_ledger(data_root).values())[0]["stage_at_entry"]

    # The GUARD: despite the detonated future, the entry-date tag is unchanged (truncated).
    assert stage2 == stage1, "future data leaked into the entry-date stage tag (guard failed)"


# --------------------------------------------------------------------------- #
# 2. Idempotent tagging — a re-run never changes an already-tagged id.          #
# --------------------------------------------------------------------------- #
def test_idempotent_tag(tmp_path, monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    data_root, site_root = _make_store(
        tmp_path, [("BBB-BULL-20210615", "BBB", "2021-06-15", "plan")])

    r1 = pss.tag_entries(root=data_root, site_root=site_root)
    row_before = dict(list(pss._load_ledger(data_root).values())[0])
    assert r1["n_tagged_now"] == 1

    # Mutate the underlying price AFTER tagging; a re-run must NOT re-tag (PIT-fixed).
    close = _stage2_series(500) * 0.01  # would classify very differently
    _write_parquet(data_root / "baskets" / "ohlcv" / "BBB.parquet", close)
    r2 = pss.tag_entries(root=data_root, site_root=site_root)
    row_after = dict(list(pss._load_ledger(data_root).values())[0])

    assert r2["n_tagged_now"] == 0, "an already-tagged id must not be re-tagged"
    assert row_after["stage_at_entry"] == row_before["stage_at_entry"]
    assert row_after == row_before, "the PIT tag must be immutable across re-runs"


# --------------------------------------------------------------------------- #
# 3. EC strictly-before — most-recent call with call_date < entry_date.         #
# --------------------------------------------------------------------------- #
def test_ec_strictly_before(tmp_path, monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    sig = "2021-06-15"
    data_root, site_root = _make_store(
        tmp_path, [("CCC-BULL-20210615", "CCC", sig, "plan")])

    # EC table: one call the day BEFORE (usable) and one ON the entry day (NOT usable).
    ec = pd.DataFrame({
        "document_ticker": ["CCC", "CCC", "CCC"],
        "call_date": pd.to_datetime(["2021-03-01", "2021-06-14", "2021-06-15"]),
        "earnings_call_sent": [10.0, 42.0, 99.0],
    })
    ec_path = tmp_path / "ec.parquet"
    ec.to_parquet(ec_path)

    pss.tag_entries(root=data_root, site_root=site_root, ec_path=ec_path)
    row = list(pss._load_ledger(data_root).values())[0]
    assert row["last_ec"] is not None
    assert row["last_ec"]["sent"] == 42.0, "must pick the most-recent call STRICTLY before entry"
    assert row["last_ec"]["call_date"] == "2021-06-14"


# --------------------------------------------------------------------------- #
# 4. Nightly-gate on grading — non-nightly tags but does NOT advance grades.     #
# --------------------------------------------------------------------------- #
def test_nightly_gate_on_grading(tmp_path, monkeypatch):
    # A mature + stageable entry (>=45 weeks before, >=126 bars after).
    sig = MATURE_SIG
    data_root, site_root = _make_store(
        tmp_path, [("DDD-BULL-20210224", "DDD", sig, "plan")])

    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    pss.tag_entries(root=data_root, site_root=site_root)

    # NON-nightly grade attempt → no advance.
    g_off = pss.grade_matured(root=data_root)
    assert g_off["gate_open"] is False
    assert g_off["advanced"] == 0
    row_off = list(pss._load_ledger(data_root).values())[0]
    assert row_off["terminal_state_clean15_126"] is None
    assert row_off["graded"] is False

    # NIGHTLY lane → advances.
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    g_on = pss.grade_matured(root=data_root)
    assert g_on["gate_open"] is True
    assert g_on["advanced"] >= 1
    row_on = list(pss._load_ledger(data_root).values())[0]
    assert row_on["terminal_state_clean15_126"] is not None
    assert row_on["graded"] is True
    # the clean rising series should be a CLEAN_LIFTOFF (reuses the grading ruler).
    assert row_on["terminal_state_clean15_126"] == grading.TerminalState.CLEAN_LIFTOFF


# --------------------------------------------------------------------------- #
# 5. Fail-open on absent OHLCV / EC / prophet stores.                           #
# --------------------------------------------------------------------------- #
def test_fail_open_absent_ohlcv(tmp_path, monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    sig = "2021-06-15"
    data_root, site_root = _make_store(
        tmp_path, [("EEE-BULL-20210615", "EEE", sig, "plan")])
    # remove the OHLCV parquet → tag must fail-open with nulls + reason, no crash.
    (data_root / "baskets" / "ohlcv" / "EEE.parquet").unlink()

    r = pss.tag_entries(root=data_root, site_root=site_root)  # must not raise
    assert r["n_tagged_now"] == 1
    row = list(pss._load_ledger(data_root).values())[0]
    assert row["stage_at_entry"] is None
    assert "no OHLCV" in (row["tag_reason"] or "")
    assert row["last_ec"] is None


def test_fail_open_absent_prophet_stores(tmp_path, monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    # completely empty roots — no plans, no index, no ledger.
    data_root = tmp_path / "data"
    site_root = tmp_path / "site"
    data_root.mkdir()
    site_root.mkdir()
    entries = pss.collect_prophet_entries(site_root, data_root)
    assert entries == []
    r = pss.tag_entries(root=data_root, site_root=site_root)  # must not raise
    assert r["n_entries"] == 0
    s = pss.summarize(root=data_root)  # must not raise on an empty ledger
    assert s["n_entries"] == 0


# --------------------------------------------------------------------------- #
# 6. Summary schema + is_context_only/display_only; nulls printed.              #
# --------------------------------------------------------------------------- #
def test_summary_schema_context_only(tmp_path, monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    data_root, site_root = _make_store(
        tmp_path, [("FFF-BULL-20210615", "FFF", "2021-06-15", "plan")])
    pss.tag_entries(root=data_root, site_root=site_root)
    s = pss.summarize(root=data_root)

    assert s["schema"] == "prophet_stage_shadow.v1"
    assert s["is_context_only"] is True
    assert s["display_only"] is True
    assert s["authority_tier"] == "display"
    assert "accruing" in s["accrual_disclaimer"]
    assert "2026-12" in s["accrual_disclaimer"]
    # nulls printed: with nothing matured, win_rate must be None (not a fabricated 0.0).
    assert s["split"]["stage2"]["clean15_126"]["win_rate"] is None
    # no forbidden 'validated' token, no trading verbs in the summary text blobs.
    blob = json.dumps(s).lower()
    assert "validated" not in blob
    for verb in (" buy ", " sell ", " short "):
        assert verb not in blob
    # the summary file is written to disk.
    assert pss.summary_path(data_root).exists()


# --------------------------------------------------------------------------- #
# 7. Matured-vs-immature partition — only elapsed-horizon entries grade.         #
# --------------------------------------------------------------------------- #
def test_matured_vs_immature_partition(tmp_path, monkeypatch):
    # Two entries on the SAME asset: one early (matured), one at the very end (immature).
    early = MATURE_SIG
    late_idx = _stage2_series(700).index[-2]
    late = str(late_idx.date())
    data_root, site_root = _make_store(tmp_path, [
        ("MAT-BULL-20210224", "MAT", early, "plan"),
        ("IMM-BULL-latex", "MAT", late, "index"),
    ])
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    pss.tag_entries(root=data_root, site_root=site_root)
    pss.grade_matured(root=data_root)

    rows = {r["id"]: r for r in pss._load_ledger(data_root).values()}
    mat = rows["MAT-BULL-20210224"]
    imm = rows["IMM-BULL-latex"]
    assert mat["terminal_state_clean15_126"] is not None, "the early entry must mature"
    assert imm["terminal_state_clean15_126"] is None, "the last-bar entry has no 126 forward bars"
    assert (imm.get("fwd") or {}).get("fwd_ret_126") is None


# --------------------------------------------------------------------------- #
# 8. win = CLEAN_LIFTOFF reuse (summary counts the grading ruler's win state).   #
# --------------------------------------------------------------------------- #
def test_win_is_clean_liftoff(tmp_path, monkeypatch):
    data_root, site_root = _make_store(
        tmp_path, [("WIN-BULL-20210224", "WIN", MATURE_SIG, "plan")])
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    pss.tag_entries(root=data_root, site_root=site_root)
    pss.grade_matured(root=data_root)
    s = pss.summarize(root=data_root)

    # WIN is Stage-2 and a CLEAN_LIFTOFF → stage2 split counts one win.
    s2 = s["split"]["stage2"]["clean15_126"]
    assert s2["n_matured"] == 1
    assert s2["n_win"] == 1
    assert s2["win_rate"] == pytest.approx(1.0)
    # the win state is exactly grading's CLEAN_LIFTOFF constant.
    row = pss._load_ledger(data_root)["WIN-BULL-20210224"]
    assert row["terminal_state_clean15_126"] == grading.TerminalState.CLEAN_LIFTOFF


def test_stopped_is_not_a_win(tmp_path, monkeypatch):
    """A falling series → STOPPED, which must NOT count as a CLEAN_LIFTOFF win."""
    def _falling(n=700, start="2020-01-01"):
        idx = _bdays(start, n)
        return pd.Series(np.linspace(300, 60, n), index=idx)
    data_root, site_root = _make_store(
        tmp_path, [("STP-BULL-20210224", "STP", MATURE_SIG, "plan")],
        price_builder=_falling)
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    pss.tag_entries(root=data_root, site_root=site_root)
    pss.grade_matured(root=data_root)
    row = pss._load_ledger(data_root)["STP-BULL-20210224"]
    # matured but not a win.
    assert row["terminal_state_clean15_126"] in (
        grading.TerminalState.STOPPED, grading.TerminalState.DEAD_MONEY,
        grading.TerminalState.CUSHIONED)
    assert row["terminal_state_clean15_126"] != grading.TerminalState.CLEAN_LIFTOFF


# --------------------------------------------------------------------------- #
# 9. Entry enumeration — active + closed + plan-file union, de-duped by id.      #
# --------------------------------------------------------------------------- #
def test_entry_enumeration_union(tmp_path, monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    data_root, site_root = _make_store(tmp_path, [
        ("P1-BULL-20210101", "P1", "2021-01-01", "plan"),
        ("I1-BULL-20210202", "I1", "2021-02-02", "index"),
        ("L1-BULL-20210303", "L1", "2021-03-03", "ledger"),
    ])
    # add a plan file whose id ALSO appears in the index → must de-dup to one.
    dup = {"schema": "prophet.trade_plan/v1", "id": "I1-BULL-20210202", "asset": "I1",
           "direction": "BULL", "signal_date": "2021-02-02"}
    (site_root / "prophet" / "plans" / "I1-BULL-20210202.json").write_text(json.dumps(dup))

    entries = pss.collect_prophet_entries(site_root, data_root)
    ids = sorted(e["id"] for e in entries)
    assert ids == ["I1-BULL-20210202", "L1-BULL-20210303", "P1-BULL-20210101"]
    # each carries an asset + signal_date.
    by_id = {e["id"]: e for e in entries}
    assert by_id["L1-BULL-20210303"]["signal_date"] == "2021-03-03"
    assert by_id["I1-BULL-20210202"]["asset"] == "I1"
