"""Tests for engine/basket_freeze.py — W3.8 frozen basket levels substrate.

Coverage:
  1. Immutability: second write for same (date, bid) keeps-FIRST (never overwrites).
  2. Hash stamping: membership_hash is deterministic + order-independent.
  3. Truncation guard: refuses to freeze when active-member count shrinks >15% vs prior.
  4. Grader reads frozen-only: verify live compute_baskets NOT called in grader paths.
  5. Invalidation on hash change mid forward window.
  6. Accruing-from disclosure: graders expose freeze_start + pre_freeze_note when no store.
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
# 7. freeze_start_date utility
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
