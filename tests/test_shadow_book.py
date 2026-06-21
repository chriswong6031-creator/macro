"""Tests for the forward shadow book (engine/shadow_book.py).

The load-bearing invariant is the LEAK GUARD: a horizon must NEVER be graded before it has
fully elapsed (grading an open horizon would silently inflate the realized IC). Plus
append-only/idempotent snapshots and a grade() that recovers a known cross-sectional IC."""
import numpy as np
import pandas as pd
import pytest

from engine import shadow_book as SB


def _closes(n=200, tickers=("A", "B", "C", "D"), start="2024-01-01"):
    idx = pd.bdate_range(start, periods=n)
    rng = np.random.default_rng(0)
    return pd.DataFrame({t: 100 * np.cumprod(1 + rng.normal(0, 0.01, n)) for t in tickers}, index=idx)


def test_snapshot_append_only_idempotent(tmp_path):
    book = str(tmp_path / "book.jsonl")
    recs = [{"ticker": "A", "score": 80}, {"ticker": "B", "score": 40}]
    assert SB.snapshot("2024-03-01", recs, horizons=(5, 21), path=book) == 2
    assert SB.snapshot("2024-03-01", recs, horizons=(5, 21), path=book) == 0   # idempotent
    df = SB.load_book(book)
    assert len(df) == 2 and set(df["ticker"]) == {"A", "B"}


def test_maturation_leak_guard(tmp_path):
    """A horizon is matured ONLY once its h-th forward bar has elapsed (<= asof)."""
    book = str(tmp_path / "book.jsonl")
    closes = _closes()
    d0 = closes.index[50]
    SB.snapshot(d0, [{"ticker": t, "score": i} for i, t in enumerate(closes.columns)],
                horizons=(5, 21), path=book)
    # before any horizon elapses -> nothing matured
    assert SB.mature(closes.index[51], closes, path=book).empty
    # h=5 ends at index 55; asof just below -> still nothing
    assert SB.mature(closes.index[54], closes, path=book).empty
    # asof == index 55 -> ONLY the 5d horizon matures, never the 21d
    m = SB.mature(closes.index[55], closes, path=book)
    assert set(m["horizon"]) == {5}
    # asof past index 71 -> both horizons mature
    m2 = SB.mature(closes.index[80], closes, path=book)
    assert set(m2["horizon"]) == {5, 21}


def test_mature_forward_return_correct(tmp_path):
    book = str(tmp_path / "book.jsonl")
    closes = _closes()
    p0 = 50
    d0 = closes.index[p0]
    SB.snapshot(d0, [{"ticker": "A", "score": 1}], horizons=(5,), path=book)
    m = SB.mature(closes.index[80], closes, path=book)
    exp = closes.iloc[p0 + 5]["A"] / closes.iloc[p0]["A"] - 1.0
    assert m.iloc[0]["fwd_ret"] == pytest.approx(exp, rel=1e-9)


def test_grade_recovers_known_ic():
    """grade() on a synthetic matured book where score perfectly ranks forward return
    must report a mean IC ≈ +1 (and the reverse ≈ -1)."""
    rows = []
    for di in range(8):                       # >=6 dates so ic_summary computes
        for t in range(12):
            rows.append({"date": f"2024-0{1+di//4}-{10+di:02d}", "ticker": f"T{t}",
                         "horizon": 21, "score": float(t), "percentile": float(t),
                         "fwd_ret": float(t) * 0.001})   # forward return increases with score
    g = SB.grade(pd.DataFrame(rows))
    assert g["by_horizon"]["h21"]["ic"]["mean_ic"] == pytest.approx(1.0, abs=1e-6)
    # flip the score -> IC flips sign
    flipped = pd.DataFrame(rows).assign(score=lambda d: -d["score"])
    gf = SB.grade(flipped)
    assert gf["by_horizon"]["h21"]["ic"]["mean_ic"] == pytest.approx(-1.0, abs=1e-6)


def test_grade_empty_book():
    g = SB.grade(pd.DataFrame())
    assert g["n_matured"] == 0 and g["by_horizon"] == {}
