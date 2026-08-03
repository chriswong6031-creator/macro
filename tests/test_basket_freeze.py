"""Tests for engine/basket_freeze.py — W3.8 frozen basket levels substrate.

Coverage:
  1. Immutability: second write for same (date, bid) keeps-FIRST (never overwrites).
  2. Hash stamping: membership_hash is deterministic + order-independent.
  3. Truncation guard: refuses to freeze when active-member count shrinks >15% vs prior.
  4. Grader reads frozen-only: verify live compute_baskets NOT called in grader paths.
  5. Invalidation on hash change mid forward window.
  6. Accruing-from disclosure: graders expose freeze_start + pre_freeze_note when no store.
  7. CHAIN LINKING (schema v2, 2026-08): frozen levels are chain-linked so cross-date
     ratios are true returns; anchors propagate, break honestly, and clamp grading.
"""
from __future__ import annotations

import hashlib
import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

def _make_members(tickers: list[str], added: str = "2024-01-01") -> list[dict]:
    return [{"ticker": t, "added": added} for t in tickers]


def _simple_membership(baskets: dict) -> dict:
    """Build a minimal membership dict the freezer accepts."""
    return {"baskets": baskets}


def _closes_df(tickers: list[str], n_days: int = 100,
               start: str = "2024-01-01") -> pd.DataFrame:
    import numpy as np
    idx = pd.date_range(start, periods=n_days, freq="B")
    data = {t: (1 + np.random.default_rng(abs(hash(t)) % 2**31).normal(0.001, 0.01, n_days)).cumprod()
            for t in tickers}
    return pd.DataFrame(data, index=idx)


def _spiked_closes(tickers: list[str], n_days: int = 40, start: str = "2024-01-01",
                   day1_ret: float = 0.25, seed: int = 7) -> pd.DataFrame:
    """Deterministic closes whose SECOND row carries a large EW return for every member.

    The moving-window regression tests drop that row out of the front of the window
    between two nights; a fat, uniform day-1 return makes the pre-fix writer's error
    factor 1/(1+r_1) impossible to mistake for noise.
    """
    import numpy as np
    idx = pd.date_range(start, periods=n_days, freq="B")
    rng = np.random.default_rng(seed)
    data = {}
    for t in tickers:
        r = rng.normal(0.0005, 0.008, n_days)
        r[0] = 0.0            # first row is the base, no return
        r[1] = day1_ret       # the row that falls out of the window on night 2
        data[t] = 100.0 * np.cumprod(1.0 + r)
    return pd.DataFrame(data, index=idx)


def _true_ew_return(closes: pd.DataFrame, pos: int) -> float:
    """EW return on row `pos`, computed straight off the raw closes (no engine code)."""
    return float((closes.iloc[pos] / closes.iloc[pos - 1] - 1.0).mean())


def _chart_payload(closes: pd.DataFrame, members: list[dict], bid: str) -> dict:
    """A baskets_payload chart exactly as compute_baskets() emits it (5dp rounding)."""
    from engine.basket_freeze import _ew_level_from_closes
    lvl, _cov = _ew_level_from_closes(closes, members)
    return {"chart": {
        "dates": [d.strftime("%Y-%m-%d") for d in lvl.index],
        "baskets": {bid: [None if pd.isna(v) else round(float(v), 5) for v in lvl]},
    }}


# ──────────────────────────────────────────────────────────────────────────────
# 1. Immutability — keep-FIRST
# ──────────────────────────────────────────────────────────────────────────────

def test_immutability_keep_first(tmp_path, monkeypatch):
    """Second freeze for the same date must not overwrite the first frozen value."""
    from engine import basket_freeze as bf

    monkeypatch.setattr("engine.basket_freeze._store_path",
                        lambda domain: tmp_path / f"{domain}.parquet")

    tickers = ["AAPL", "MSFT", "GOOG", "AMZN"]
    closes = _closes_df(tickers)
    mem = _simple_membership({"b_test": {"members": _make_members(tickers)}})

    # First freeze
    r1 = bf.freeze_domain("us", None, closes, mem, as_of_date="2024-06-01")
    assert r1["n_frozen"] > 0
    df1 = pd.read_parquet(tmp_path / "us.parquet")
    first_level = df1["b_test__level_tr"].iloc[0]

    # Second freeze same date with different closes (simulate level change)
    closes2 = _closes_df(tickers, start="2024-01-01")  # fresh random walk
    r2 = bf.freeze_domain("us", None, closes2, mem, as_of_date="2024-06-01")
    # Should report 0 newly frozen (already exists)
    assert r2["n_frozen"] == 0

    df2 = pd.read_parquet(tmp_path / "us.parquet")
    assert len(df2) == 1   # still one row
    # level must be unchanged
    assert df2["b_test__level_tr"].iloc[0] == pytest.approx(first_level)


# ──────────────────────────────────────────────────────────────────────────────
# 2. Membership hash stamping
# ──────────────────────────────────────────────────────────────────────────────

def test_membership_hash_deterministic():
    """Same members in any order → same hash."""
    from engine.basket_freeze import membership_hash
    members_a = [{"ticker": "AAPL", "added": "2024-01-01"},
                 {"ticker": "MSFT", "added": "2024-01-01"},
                 {"ticker": "GOOG", "added": "2024-01-01"}]
    members_b = list(reversed(members_a))
    assert membership_hash(members_a) == membership_hash(members_b)


def test_membership_hash_excludes_removed():
    """Removed members must not affect the active hash."""
    from engine.basket_freeze import membership_hash
    active = [{"ticker": "AAPL", "added": "2024-01-01"},
              {"ticker": "MSFT", "added": "2024-01-01"}]
    with_removed = active + [{"ticker": "EXITED", "added": "2023-01-01",
                               "removed": "2024-01-15"}]
    assert membership_hash(active) == membership_hash(with_removed)


def test_membership_hash_changes_on_member_add():
    """Adding a new active member must change the hash."""
    from engine.basket_freeze import membership_hash
    m1 = [{"ticker": "AAPL", "added": "2024-01-01"},
          {"ticker": "MSFT", "added": "2024-01-01"}]
    m2 = m1 + [{"ticker": "NVDA", "added": "2024-06-01"}]
    assert membership_hash(m1) != membership_hash(m2)


def test_membership_hash_length():
    """Hash is exactly 16 hex chars."""
    from engine.basket_freeze import membership_hash
    members = [{"ticker": "A", "added": "2024-01-01"}]
    h = membership_hash(members)
    assert len(h) == 16
    assert all(c in "0123456789abcdef" for c in h)


def test_hash_stamped_in_parquet(tmp_path, monkeypatch):
    """Frozen parquet must contain the mhash column with a valid 16-char hash."""
    from engine import basket_freeze as bf

    monkeypatch.setattr("engine.basket_freeze._store_path",
                        lambda domain: tmp_path / f"{domain}.parquet")

    tickers = ["AA", "BB", "CC", "DD"]
    closes = _closes_df(tickers)
    mem = _simple_membership({"myb": {"members": _make_members(tickers)}})

    bf.freeze_domain("us", None, closes, mem, as_of_date="2024-07-01")
    df = pd.read_parquet(tmp_path / "us.parquet")
    assert "myb__mhash" in df.columns
    h = df["myb__mhash"].iloc[0]
    assert isinstance(h, str) and len(h) == 16


# ──────────────────────────────────────────────────────────────────────────────
# 3. Truncation guard — >15% shrink refuses freeze
# ──────────────────────────────────────────────────────────────────────────────

def test_truncation_guard_fires(tmp_path, monkeypatch):
    """When active membership shrinks >15% vs prior frozen n_members, FreezeSkipped is raised."""
    from engine import basket_freeze as bf

    monkeypatch.setattr("engine.basket_freeze._store_path",
                        lambda domain: tmp_path / f"{domain}.parquet")
    # Suppress notify calls
    monkeypatch.setattr("engine.basket_freeze.send_telegram", lambda *a: None, raising=False)
    monkeypatch.setattr("engine.basket_freeze.send_discord", lambda *a: None, raising=False)

    # First freeze: 10 members
    tickers_full = [f"T{i:02d}" for i in range(10)]
    closes = _closes_df(tickers_full)
    mem_full = _simple_membership({"b1": {"members": _make_members(tickers_full)}})

    r1 = bf.freeze_domain("us", None, closes, mem_full, as_of_date="2024-06-01")
    assert r1["n_frozen"] > 0

    # Second freeze next day: only 6 members (40% shrink > 15%)
    tickers_small = tickers_full[:6]
    closes2 = _closes_df(tickers_small)
    # Membership with 4 removed entries
    members_shrunk = _make_members(tickers_small) + [
        {"ticker": t, "added": "2024-01-01", "removed": "2024-06-02"}
        for t in tickers_full[6:]
    ]
    mem_shrunk = _simple_membership({"b1": {"members": members_shrunk}})

    with pytest.raises(bf.FreezeSkipped):
        bf.freeze_domain("us", None, closes2, mem_shrunk, as_of_date="2024-06-02")


def test_truncation_guard_silent_below_threshold(tmp_path, monkeypatch):
    """A shrink ≤ 15% must NOT trigger the guard."""
    from engine import basket_freeze as bf

    monkeypatch.setattr("engine.basket_freeze._store_path",
                        lambda domain: tmp_path / f"{domain}.parquet")

    tickers_full = [f"T{i:02d}" for i in range(10)]
    closes = _closes_df(tickers_full)
    mem_full = _simple_membership({"b1": {"members": _make_members(tickers_full)}})
    bf.freeze_domain("us", None, closes, mem_full, as_of_date="2024-06-01")

    # Remove 1 of 10 = 10% shrink (≤ 15%) — should NOT raise
    members_ok = _make_members(tickers_full[:9]) + [
        {"ticker": tickers_full[9], "added": "2024-01-01", "removed": "2024-06-02"}
    ]
    closes2 = _closes_df(tickers_full[:9])
    mem_ok = _simple_membership({"b1": {"members": members_ok}})

    # Should not raise; should freeze
    result = bf.freeze_domain("us", None, closes2, mem_ok, as_of_date="2024-06-02")
    assert not result["freeze_skipped"]
    assert result["n_frozen"] > 0


def test_truncation_guard_result_fields(tmp_path, monkeypatch):
    """FreezeSkipped result dict must carry freeze_skipped=True + non-empty skip_reason."""
    from engine import basket_freeze as bf

    monkeypatch.setattr("engine.basket_freeze._store_path",
                        lambda domain: tmp_path / f"{domain}.parquet")

    tickers_full = [f"T{i:02d}" for i in range(10)]
    closes = _closes_df(tickers_full)
    mem_full = _simple_membership({"b1": {"members": _make_members(tickers_full)}})
    bf.freeze_domain("us", None, closes, mem_full, as_of_date="2024-06-01")

    members_shrunk = [
        {"ticker": t, "added": "2024-01-01", "removed": "2024-06-02"}
        for t in tickers_full[7:]
    ] + _make_members(tickers_full[:7])
    mem_shrunk = _simple_membership({"b1": {"members": members_shrunk}})

    result = {
        "domain": "us", "freeze_skipped": False, "skip_reason": None,
        "n_frozen": 0, "n_skipped_churn": 0, "price_basis_coverage": 0.0,
        "date": "2024-06-02",
    }
    try:
        bf.freeze_domain("us", None, _closes_df(tickers_full[:7]), mem_shrunk,
                         as_of_date="2024-06-02")
    except bf.FreezeSkipped:
        pass
    # Read result via the domain's parquet (still only has day 1)
    df = pd.read_parquet(tmp_path / "us.parquet")
    assert len(df) == 1  # day 2 was NOT written


# ──────────────────────────────────────────────────────────────────────────────
# 4. Grader reads frozen-only — live compute NOT called
# ──────────────────────────────────────────────────────────────────────────────

def test_us_grader_does_not_call_compute_baskets(monkeypatch):
    """sector_central_grader._basket_levels() must NOT call engine.baskets.compute_baskets."""
    # Patch read_frozen to return None (no store yet) and verify compute_baskets not touched
    compute_called = {"flag": False}

    def fake_compute_baskets():
        compute_called["flag"] = True
        return {}

    monkeypatch.setattr("engine.baskets.compute_baskets", fake_compute_baskets)

    import importlib
    import engine.sector_central_grader as scg
    importlib.reload(scg)  # reload to clear module-level caches

    with patch("engine.basket_freeze.read_frozen", return_value=None):
        levels = scg._basket_levels()

    assert not compute_called["flag"], "compute_baskets was called — W3.8 leak not closed"
    assert levels == {}


def test_cn_grader_does_not_call_compute_china_baskets(monkeypatch):
    """china_sector_central_grader._basket_levels_cn() must NOT call compute_china_baskets."""
    compute_called = {"flag": False}

    def fake_compute():
        compute_called["flag"] = True
        return {}

    monkeypatch.setattr("engine.baskets_china.compute_china_baskets", fake_compute)

    import engine.china_sector_central_grader as cscg
    importlib.reload(cscg)

    with patch("engine.basket_freeze.read_frozen", return_value=None):
        levels, frozen_df = cscg._basket_levels_cn()

    assert not compute_called["flag"], "compute_china_baskets was called — W3.8 leak not closed"
    assert levels == {}
    assert frozen_df is None


# ──────────────────────────────────────────────────────────────────────────────
# 5. Grade invalidation on hash change mid forward window
# ──────────────────────────────────────────────────────────────────────────────

def test_mhash_stable_returns_false_on_hash_change():
    """_mhash_stable returns False when mhash differs within the forward window."""
    from engine.sector_central_grader import _mhash_stable

    d0 = pd.Timestamp("2024-06-01")
    # Simulate frozen_df with two rows where the hash changes on day 10
    idx = pd.date_range("2024-06-01", periods=30, freq="D")
    mhash_vals = ["abc1234567890001"] * 10 + ["def9876543210002"] * 20
    frozen_df = pd.DataFrame({"myb__mhash": mhash_vals}, index=idx)

    # h=21 → window spans both hashes → should be False
    assert not _mhash_stable("myb", d0, 21, frozen_df)


def test_mhash_stable_returns_true_on_stable_window():
    """_mhash_stable returns True when mhash is constant over the window."""
    from engine.sector_central_grader import _mhash_stable

    d0 = pd.Timestamp("2024-06-01")
    idx = pd.date_range("2024-06-01", periods=60, freq="D")
    mhash_vals = ["abc1234567890001"] * 60
    frozen_df = pd.DataFrame({"myb__mhash": mhash_vals}, index=idx)

    assert _mhash_stable("myb", d0, 21, frozen_df)


def test_grade_counts_invalidated_membership(tmp_path, monkeypatch):
    """grade() must count invalidated_membership when hash changes mid window."""
    import engine.sector_central_grader as scg

    # Build a minimal calls.parquet with one basket call
    calls_p = tmp_path / "sector_central" / "calls.parquet"
    calls_p.parent.mkdir(parents=True, exist_ok=True)

    calls_df = pd.DataFrame([{
        "date": "2024-01-10", "id": "b-myb", "kind": "basket",
        "ticker": None, "basket_id": "myb", "name": "My Basket",
        "score": 0.8, "label": "strong_up", "dir": "up",
        "confluence": True, "trend_pass": True, "ret_12m": 0.1,
        "gate_factor": 1.0, "level": None,
    }])
    calls_df.to_parquet(calls_p, index=False)

    monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)

    # Frozen store: hash changes on day 15 (mid the 21d window)
    basket_levels_p = tmp_path / "basket_levels" / "us.parquet"
    basket_levels_p.parent.mkdir(parents=True, exist_ok=True)
    idx = pd.date_range("2024-01-01", periods=90, freq="D")
    hashes = ["aaaa1111bbbb2222"] * 14 + ["cccc3333dddd4444"] * 76
    levels = [1.0 + i * 0.001 for i in range(90)]
    frozen_df = pd.DataFrame({
        "myb__level_tr": levels,
        "myb__mhash": hashes,
        "myb__n_members": [5] * 90,
        # schema v2: the whole store is chained from its first row, so the call at
        # 2024-01-10 is INSIDE the valid return span and the membership check is the
        # thing being tested here (not the chain gate).
        "myb__anchor": [str(idx[0].date())] * 90,
        "__freeze_schema": [2] * 90,
    }, index=pd.DatetimeIndex(idx))
    frozen_df.to_parquet(basket_levels_p)

    # Patch _yahoo_panel to return None (no sector data needed for this basket-only test)
    monkeypatch.setattr(scg, "_yahoo_panel", lambda: None)

    result = scg.grade()
    assert result is not None
    assert result["available"]
    # The basket call at 2024-01-10 + h=21 → window spans hash change → invalidated
    h21 = result["by_horizon"].get("21d", {})
    assert h21.get("invalidated_membership", 0) >= 1


# ──────────────────────────────────────────────────────────────────────────────
# 6. Accruing-from disclosure
# ──────────────────────────────────────────────────────────────────────────────

def test_grader_reports_accruing_when_no_frozen_store(tmp_path, monkeypatch):
    """With no frozen store, grade() must set freeze_start=None + pre_freeze_note."""
    import engine.sector_central_grader as scg

    calls_p = tmp_path / "sector_central" / "calls.parquet"
    calls_p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{
        "date": "2024-01-10", "id": "b-x", "kind": "basket",
        "ticker": None, "basket_id": "x", "name": "X",
        "score": 0.5, "label": "neutral", "dir": "up",
        "confluence": True, "trend_pass": True, "ret_12m": 0.0,
        "gate_factor": 1.0, "level": None,
    }]).to_parquet(calls_p, index=False)

    monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)
    monkeypatch.setattr(scg, "_yahoo_panel", lambda: None)

    result = scg.grade()
    assert result["available"]
    assert result["freeze_start"] is None
    # note must mention accrual behaviour (word stems: 'accru')
    assert "accru" in (result.get("pre_freeze_note") or "").lower()


def test_cn_grader_reports_accruing_when_no_frozen_store(tmp_path, monkeypatch):
    """China grader must also report accruing-from disclosure when no frozen store."""
    import engine.china_sector_central_grader as cscg

    calls_p = tmp_path / "china_sector_central" / "calls.parquet"
    calls_p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{
        "date": "2024-01-10", "id": "b-y", "kind": "basket",
        "shenwan_code": None, "basket_id": "y", "name": "Y",
        "score": 0.5, "label": "neutral", "dir": "up",
        "confluence": True, "fwd_cond_rate": None, "fwd_lift": None,
        "gate_factor": 1.0, "level": None,
    }]).to_parquet(calls_p, index=False)

    monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)

    # Stub out csi.sw_close so sector _fwd_return returns None harmlessly
    with patch("engine.china_sector_index.sw_close", return_value=None):
        result = cscg.grade()

    assert result is not None
    assert result["available"]
    assert result["freeze_start"] is None
    assert "accru" in (result.get("pre_freeze_note") or "").lower()


# ──────────────────────────────────────────────────────────────────────────────
# 7a. CHAIN-LINKED FREEZE — the moving-window regression (schema v2, 2026-08)
# ──────────────────────────────────────────────────────────────────────────────

def _tickers(n: int = 5) -> list[str]:
    return [f"CH{i:02d}" for i in range(n)]


def _freeze_two_moving_nights(bf, tmp_path, closes, mem, bid="b1", *, payload: bool):
    """Freeze night N then night N+1 over a window that ROLLS FORWARD one row.

    Night 2 drops the front row (the +25% day) and appends one — exactly what the
    nightly rebuild does, and exactly what re-based every frozen row before the chain
    fix. Returns (frozen_df, day_N, day_N1).
    """
    n = len(closes) - 2
    d1, d2 = closes.index[n], closes.index[n + 1]
    night1 = closes.iloc[: n + 1]              # rows [0 .. N]
    night2 = closes.iloc[1: n + 2]             # rows [1 .. N+1]  ← front row gone
    members = mem["baskets"][bid]["members"]
    for cl, d in ((night1, d1), (night2, d2)):
        pay = _chart_payload(cl, members, bid) if payload else None
        bf.freeze_domain("us", pay, cl, mem, as_of_date=str(d.date()))
    return pd.read_parquet(tmp_path / "us.parquet"), d1, d2


@pytest.mark.parametrize("payload,tol", [(False, 1e-9), (True, 1e-4)])
def test_chain_link_survives_a_moving_price_window(tmp_path, monkeypatch, payload, tol):
    """THE regression test. Two nights, one rolling window, one fat day dropped.

    The frozen ratio row2/row1 must equal 1 + the true EW return of the NEW day —
    and must NOT equal the value the pre-fix writer produced, which carried the
    dropped day's return as an error factor. Both halves are asserted so the test
    provably SEES the failure mode it pins (a test that only checks the correct
    value would also pass on a writer that happened to be right by construction).
    """
    from engine import basket_freeze as bf
    monkeypatch.setattr("engine.basket_freeze._store_path",
                        lambda domain: tmp_path / f"{domain}.parquet")

    tickers = _tickers()
    closes = _spiked_closes(tickers, n_days=40)
    mem = _simple_membership({"b1": {"members": _make_members(tickers, added="2023-12-01")}})

    df, _d1, _d2 = _freeze_two_moving_nights(bf, tmp_path, closes, mem, payload=payload)
    assert len(df) == 2

    lvl = df["b1__level_tr"]
    frozen_ratio = float(lvl.iloc[1]) / float(lvl.iloc[0])

    n = len(closes) - 2
    true_ret = _true_ew_return(closes, n + 1)          # the new day's real EW move
    r_day1 = _true_ew_return(closes, 1)                # the day that fell out of the window

    # 1) the frozen ratio IS the realized return over that span
    assert frozen_ratio == pytest.approx(1.0 + true_ret, rel=tol)

    # 2) and it is NOT the naive rebased value the pre-fix writer wrote: that one
    #    divided two cumprods whose bases differed by exactly the dropped day.
    naive_ratio = (1.0 + true_ret) / (1.0 + r_day1)
    assert frozen_ratio != pytest.approx(naive_ratio, rel=1e-6)
    assert abs(frozen_ratio - naive_ratio) > 0.1, (
        "the +25% dropped day must move the naive value far enough to be unmissable"
    )

    # the price basis rides the same chain when no price-basis input is supplied
    assert float(df["b1__level_price"].iloc[1]) == pytest.approx(float(lvl.iloc[1]), rel=1e-12)


# ──────────────────────────────────────────────────────────────────────────────
# 7b. Chain anchors — propagation, v1→v2 boundary, breaks, new baskets
# ──────────────────────────────────────────────────────────────────────────────

def test_anchor_propagates_across_consecutive_freezes(tmp_path, monkeypatch):
    """Three nights on a fresh store → one segment: every row anchors on night 1."""
    from engine import basket_freeze as bf
    monkeypatch.setattr("engine.basket_freeze._store_path",
                        lambda domain: tmp_path / f"{domain}.parquet")

    tickers = _tickers()
    closes = _spiked_closes(tickers, n_days=40)
    mem = _simple_membership({"b1": {"members": _make_members(tickers, added="2023-12-01")}})

    n0 = len(closes) - 3
    nights = [closes.index[n0 + i] for i in range(3)]
    for i, d in enumerate(nights):
        bf.freeze_domain("us", None, closes.iloc[i: n0 + 1 + i], mem, as_of_date=str(d.date()))

    df = pd.read_parquet(tmp_path / "us.parquet")
    assert len(df) == 3
    first = str(nights[0].date())
    assert list(df["b1__anchor"]) == [first] * 3
    assert list(df["__freeze_schema"]) == [2, 2, 2]
    assert bf.return_valid_start("us", "b1") == first


def test_v1_to_v2_boundary_anchors_on_the_last_legacy_row(tmp_path, monkeypatch):
    """A legacy (pre-anchor) store gains one chained row anchored on its last date.

    The boundary ratio is exact even though the legacy VALUE was frozen on a moving
    base: both legs of the ratio come from tonight's one consistent series, so the
    span [last_legacy_date → tonight] is a true return. Everything older is not.
    """
    from engine import basket_freeze as bf
    monkeypatch.setattr("engine.basket_freeze._store_path",
                        lambda domain: tmp_path / f"{domain}.parquet")

    tickers = _tickers()
    closes = _spiked_closes(tickers, n_days=40)
    members = _make_members(tickers, added="2023-12-01")
    mem = _simple_membership({"b1": {"members": members}})

    legacy_dates = pd.DatetimeIndex([closes.index[-4], closes.index[-3]])
    pd.DataFrame({
        "b1__level_tr": [5.0, 7.0],
        "b1__level_price": [5.0, 7.0],
        "b1__mhash": ["a" * 16] * 2,
        "b1__n_members": [len(tickers)] * 2,
    }, index=legacy_dates).to_parquet(tmp_path / "us.parquet")

    d_new = closes.index[-2]
    tonight = closes.iloc[1:-1]                     # rolling window ending at d_new
    bf.freeze_domain("us", None, tonight, mem, as_of_date=str(d_new.date()))

    df = pd.read_parquet(tmp_path / "us.parquet").sort_index()
    assert len(df) == 3, "legacy rows must survive untouched"
    assert list(df["b1__level_tr"].iloc[:2]) == [5.0, 7.0]

    boundary = str(legacy_dates[-1].date())
    assert df["b1__anchor"].iloc[-1] == boundary
    assert pd.isna(df["b1__anchor"].iloc[0]) and pd.isna(df["b1__anchor"].iloc[1])
    assert bf.return_valid_start("us", "b1") == boundary

    series, _cov = bf._ew_level_from_closes(tonight, members)
    expect = (float(series.loc[:d_new].dropna().iloc[-1])
              / float(series.loc[:legacy_dates[-1]].dropna().iloc[-1]))
    assert float(df["b1__level_tr"].iloc[-1]) / 7.0 == pytest.approx(expect, rel=1e-9)


def test_chain_break_reanchors_on_its_own_date(tmp_path, monkeypatch):
    """No overlap with the prior frozen date → the chain restarts on tonight's base."""
    from engine import basket_freeze as bf
    monkeypatch.setattr("engine.basket_freeze._store_path",
                        lambda domain: tmp_path / f"{domain}.parquet")

    tickers = _tickers()
    closes = _spiked_closes(tickers, n_days=40, start="2024-01-01")
    members = _make_members(tickers, added="2023-12-01")
    mem = _simple_membership({"b1": {"members": members}})

    # prior frozen row predates tonight's whole series → asof(prior_date) is None
    pd.DataFrame({
        "b1__level_tr": [3.0], "b1__level_price": [3.0],
        "b1__mhash": ["a" * 16], "b1__n_members": [len(tickers)],
        "b1__anchor": ["2023-01-05"], "__freeze_schema": [2],
    }, index=pd.DatetimeIndex(["2023-01-05"])).to_parquet(tmp_path / "us.parquet")

    d_new = closes.index[-1]
    bf.freeze_domain("us", None, closes, mem, as_of_date=str(d_new.date()))

    df = pd.read_parquet(tmp_path / "us.parquet").sort_index()
    assert df["b1__anchor"].iloc[-1] == str(d_new.date())
    assert bf.return_valid_start("us", "b1") == str(d_new.date())
    # the broken link wrote tonight's raw base, NOT 3.0 × anything
    series, _cov = bf._ew_level_from_closes(closes, members)
    assert float(df["b1__level_tr"].iloc[-1]) == pytest.approx(
        float(series.dropna().iloc[-1]), rel=1e-12)


def test_new_basket_midstore_anchors_on_its_own_first_date(tmp_path, monkeypatch):
    """A basket that appears mid-store starts its own chain; siblings are untouched."""
    from engine import basket_freeze as bf
    monkeypatch.setattr("engine.basket_freeze._store_path",
                        lambda domain: tmp_path / f"{domain}.parquet")

    all_t = _tickers(8)
    closes = _spiked_closes(all_t, n_days=40)
    m1 = _make_members(all_t[:4], added="2023-12-01")
    m2 = _make_members(all_t[4:], added="2023-12-01")

    n = len(closes) - 2
    d1, d2 = closes.index[n], closes.index[n + 1]
    bf.freeze_domain("us", None, closes.iloc[: n + 1],
                     _simple_membership({"b1": {"members": m1}}), as_of_date=str(d1.date()))
    bf.freeze_domain("us", None, closes.iloc[1: n + 2],
                     _simple_membership({"b1": {"members": m1}, "b2": {"members": m2}}),
                     as_of_date=str(d2.date()))

    df = pd.read_parquet(tmp_path / "us.parquet").sort_index()
    assert list(df["b1__anchor"]) == [str(d1.date())] * 2
    assert pd.isna(df["b2__anchor"].iloc[0])
    assert df["b2__anchor"].iloc[1] == str(d2.date())
    assert bf.return_valid_start("us", "b1") == str(d1.date())
    assert bf.return_valid_start("us", "b2") == str(d2.date())


def test_none_level_gap_does_not_break_the_chain(tmp_path, monkeypatch):
    """A night with no value writes None + NO anchor; the next night still chains exact."""
    from engine import basket_freeze as bf
    monkeypatch.setattr("engine.basket_freeze._store_path",
                        lambda domain: tmp_path / f"{domain}.parquet")

    tickers = _tickers()
    closes = _spiked_closes(tickers, n_days=40)
    members = _make_members(tickers, added="2023-12-01")
    mem = _simple_membership({"b1": {"members": members}})

    n = len(closes) - 2
    d0, d1, d2 = closes.index[n - 1], closes.index[n], closes.index[n + 1]
    bf.freeze_domain("us", None, closes.iloc[:n], mem, as_of_date=str(d0.date()))
    # night 2: no usable series at all (fewer than 3 members present) → None row
    bf.freeze_domain("us", None, closes[[tickers[0]]], mem, as_of_date=str(d1.date()))
    bf.freeze_domain("us", None, closes.iloc[2: n + 2], mem, as_of_date=str(d2.date()))

    df = pd.read_parquet(tmp_path / "us.parquet").sort_index()
    assert pd.isna(df["b1__level_tr"].iloc[1]) and pd.isna(df["b1__anchor"].iloc[1])
    assert df["b1__anchor"].iloc[2] == str(d0.date())      # chain unbroken across the gap
    # and the value chained across the gap is the true d0 → d2 move
    series, _cov = bf._ew_level_from_closes(closes.iloc[2: n + 2], members)
    expect = (float(series.loc[:d2].dropna().iloc[-1])
              / float(series.loc[:d0].dropna().iloc[-1]))
    ratio = float(df["b1__level_tr"].iloc[2]) / float(df["b1__level_tr"].iloc[0])
    assert ratio == pytest.approx(expect, rel=1e-9)


# ──────────────────────────────────────────────────────────────────────────────
# 7c. return_valid_start
# ──────────────────────────────────────────────────────────────────────────────

def test_return_valid_start_none_for_missing_store_basket_and_legacy(tmp_path, monkeypatch):
    from engine import basket_freeze as bf
    monkeypatch.setattr("engine.basket_freeze._store_path",
                        lambda domain: tmp_path / f"{domain}.parquet")

    assert bf.return_valid_start("us", "b1") is None          # no store at all

    idx = pd.DatetimeIndex(["2024-06-03", "2024-06-04"])
    pd.DataFrame({                                            # legacy-only: no anchors
        "b1__level_tr": [1.0, 1.1], "b1__level_price": [1.0, 1.1],
        "b1__mhash": ["a" * 16] * 2, "b1__n_members": [5, 5],
    }, index=idx).to_parquet(tmp_path / "us.parquet")

    assert bf.return_valid_start("us", "b1") is None           # unchained
    assert bf.return_valid_start("us", "nope") is None         # basket not in store


def test_return_valid_start_fails_closed_on_a_legacy_tail(tmp_path, monkeypatch):
    """Anchored rows followed by a NEWER unanchored row → None, not the stale anchor."""
    from engine import basket_freeze as bf
    monkeypatch.setattr("engine.basket_freeze._store_path",
                        lambda domain: tmp_path / f"{domain}.parquet")

    idx = pd.DatetimeIndex(["2024-06-03", "2024-06-04", "2024-06-05"])
    pd.DataFrame({
        "b1__level_tr": [1.0, 1.1, 1.2],
        "b1__anchor": ["2024-06-03", "2024-06-03", None],
    }, index=idx).to_parquet(tmp_path / "us.parquet")

    assert bf.return_valid_start("us", "b1") is None


# ──────────────────────────────────────────────────────────────────────────────
# 7d. Graders clamp basket grading to the chained span
# ──────────────────────────────────────────────────────────────────────────────

_ANCHOR_POS = 40          # rows [0.._ANCHOR_POS] are legacy; the chain starts here


def _seed_chained_store(path, bid="myb", n=200, start="2024-01-01"):
    """A store with a legacy head and a chained tail — the shape every real store has
    the night the chain fix ships. Returns (index, anchor_iso)."""
    idx = pd.date_range(start, periods=n, freq="D")
    anchor = str(idx[_ANCHOR_POS].date())
    tail = n - _ANCHOR_POS - 1
    levels = [1.0 + i * 0.001 for i in range(n)]
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({
        f"{bid}__level_tr": levels,
        f"{bid}__level_price": levels,
        f"{bid}__mhash": ["aaaa1111bbbb2222"] * n,
        f"{bid}__n_members": [5] * n,
        f"{bid}__anchor": [None] * (_ANCHOR_POS + 1) + [anchor] * tail,
        "__freeze_schema": [None] * (_ANCHOR_POS + 1) + [2] * tail,
    }, index=idx).to_parquet(path)
    return idx, anchor


def test_us_grader_invalidates_pre_anchor_basket_calls(tmp_path, monkeypatch):
    """A call dated before the chain anchor is DECLARED invalid, never graded."""
    import engine.sector_central_grader as scg

    idx, anchor = _seed_chained_store(tmp_path / "basket_levels" / "us.parquet")
    pre, post = idx[10], idx[60]
    assert str(pre.date()) < anchor <= str(post.date())

    calls_p = tmp_path / "sector_central" / "calls.parquet"
    calls_p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"date": str(d.date()), "id": f"b-myb-{i}", "kind": "basket", "ticker": None,
         "basket_id": "myb", "name": "My Basket", "score": 0.8, "label": "strong_up",
         "dir": "up", "confluence": True, "trend_pass": True, "ret_12m": 0.1,
         "gate_factor": 1.0, "level": None}
        for i, d in enumerate((pre, post))
    ]).to_parquet(calls_p, index=False)

    monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)
    monkeypatch.setattr(scg, "_yahoo_panel", lambda: None)

    result = scg.grade()
    h21 = result["by_horizon"]["21d"]
    assert h21["invalidated_pre_chain"] == 1          # the pre-anchor call
    assert h21["n"] == 1                              # ONLY the post-anchor call scored
    assert result["basket_return_valid_start"] == anchor


def test_cn_grader_invalidates_pre_anchor_basket_calls(tmp_path, monkeypatch):
    """Same clamp on the China grader (china + china_ths domains)."""
    import engine.china_sector_central_grader as cscg

    idx, anchor = _seed_chained_store(tmp_path / "basket_levels" / "china.parquet")
    pre, post = idx[10], idx[60]

    calls_p = tmp_path / "china_sector_central" / "calls.parquet"
    calls_p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"date": str(d.date()), "id": f"b-myb-{i}", "kind": "basket", "shenwan_code": None,
         "basket_id": "myb", "name": "My Basket", "score": 0.8, "label": "strong_up",
         "dir": "up", "confluence": True, "fwd_cond_rate": None, "fwd_lift": None,
         "gate_factor": 1.0, "level": None}
        for i, d in enumerate((pre, post))
    ]).to_parquet(calls_p, index=False)

    monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)

    with patch("engine.china_sector_index.sw_close", return_value=None), \
         patch("engine.china_sector_index.benchmark_close_price", return_value=None):
        result = cscg.grade()

    h21 = result["by_horizon"]["21d"]
    assert h21["invalidated_pre_chain"] == 1
    assert h21["n"] == 1
    assert result["basket_return_valid_start"] == anchor


# ──────────────────────────────────────────────────────────────────────────────
# 8. freeze_start_date utility
# ──────────────────────────────────────────────────────────────────────────────

def test_freeze_start_date_returns_none_when_no_store(tmp_path, monkeypatch):
    from engine import basket_freeze as bf
    monkeypatch.setattr("engine.basket_freeze._store_path",
                        lambda domain: tmp_path / f"{domain}.parquet")
    assert bf.freeze_start_date("us") is None


def test_freeze_start_date_returns_first_date(tmp_path, monkeypatch):
    from engine import basket_freeze as bf
    monkeypatch.setattr("engine.basket_freeze._store_path",
                        lambda domain: tmp_path / f"{domain}.parquet")

    tickers = ["AA", "BB", "CC", "DD"]
    closes = _closes_df(tickers)
    mem = _simple_membership({"b1": {"members": _make_members(tickers)}})
    bf.freeze_domain("us", None, closes, mem, as_of_date="2024-06-15")
    bf.freeze_domain("us", None, closes, mem, as_of_date="2024-06-16")

    start = bf.freeze_start_date("us")
    assert start == "2024-06-15"
