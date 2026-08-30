"""The shadow book's `percentile` field must be a true cross-sectional percentile rank.

Both snapshot producers (scripts/snapshot_shadow_book.rows_from_board and the
build_stock_library call site that now reuses it) used to write the RAW conviction score
into `percentile` — the very field the pre-registration grades
(research/SHADOW_BOOK_PREREGISTRATION.md §1: "the live, build-time-frozen stock_score
percentile rank") and the one scripts/mature_shadow_book.py passes as grade(key=
"percentile"). Rank-IC is invariant to that monotone mislabeling, but the linear
Clark-West score→return map is not. History is append-only and never restated: post-fix
rows carry pct_basis="xs_rank"; legacy rows lack the stamp, so the grader can split eras.
"""
import numpy as np
import pandas as pd
import pytest

from engine import shadow_book as SB
from scripts.snapshot_shadow_book import rows_from_board


# --------------------------------------------------------------------------- #
# xs_percentile (the one definition of `percentile`)
# --------------------------------------------------------------------------- #
def test_xs_percentile_is_average_rank_over_n():
    assert SB.xs_percentile([10, 20, 40, 30]) == [0.25, 0.5, 1.0, 0.75]
    # ties share the average rank; the max is always 1.0
    assert SB.xs_percentile([1, 2, 2, 3]) == [0.25, 0.625, 0.625, 1.0]
    assert SB.xs_percentile([7]) == [1.0]


def test_xs_percentile_non_numeric_is_none():
    out = SB.xs_percentile([10, "junk", None, 20])
    assert out[1] is None and out[2] is None
    # the two numeric entries still rank within the 2-name numeric universe
    assert out[0] == 0.5 and out[3] == 1.0


# --------------------------------------------------------------------------- #
# rows_from_board — percentile is the cross-sectional rank, never the raw score
# --------------------------------------------------------------------------- #
def _board():
    def rec(t, score):
        return {"ticker": t, "conviction": {"score": score, "regime": {"state": "up"}}}
    return {"as_of": "2026-08-26",
            "buy": [rec("A", 88.0)],
            "watch": [rec("B", 55.0), {"ticker": None, "conviction": {"score": 99.0}},
                      {"ticker": "SKIP", "conviction": {}}],
            "laggards": [rec("C", 21.0)]}


def test_rows_from_board_percentile_is_xs_rank_not_raw_score():
    asof, rows = rows_from_board(_board())
    assert asof == "2026-08-26"
    by_t = {r["ticker"]: r for r in rows}
    # ranked ACROSS buckets (one name per bucket -> pooled ranks, not 1.0 each)
    assert by_t["C"]["percentile"] == pytest.approx(1 / 3)
    assert by_t["B"]["percentile"] == pytest.approx(2 / 3)
    assert by_t["A"]["percentile"] == pytest.approx(1.0)
    for r in rows:
        assert r["percentile"] != r["score"]          # the defect this file pins
        assert 0.0 < r["percentile"] <= 1.0
        assert r["pct_basis"] == "xs_rank"            # era stamp on every post-fix row


# --------------------------------------------------------------------------- #
# end to end: snapshot writes the rank + stamp; mature carries the stamp through
# --------------------------------------------------------------------------- #
def test_snapshot_and_mature_carry_rank_and_era_stamp(tmp_path):
    book = str(tmp_path / "book.jsonl")
    # a legacy-era row: percentile mislabeled as the raw score, no stamp
    SB.snapshot("2026-08-20", [{"ticker": "A", "score": 88.0, "percentile": 88.0}],
                horizons=(5,), path=book)
    idx = pd.bdate_range("2026-08-20", periods=30)
    rng = np.random.default_rng(0)
    closes = pd.DataFrame({t: 100 * np.cumprod(1 + rng.normal(0, 0.01, len(idx)))
                           for t in ("A", "B", "C")}, index=idx)
    asof, rows = rows_from_board(_board())
    assert SB.snapshot(asof, rows, horizons=(5,), path=book) == 3
    df = SB.load_book(book).set_index("ticker")
    assert df.loc["A", "percentile"].tolist() == [88.0, 1.0]     # history not restated
    assert df.loc["B", "percentile"] == pytest.approx(2 / 3)
    legacy, fixed = df.loc["A", "pct_basis"].tolist()
    assert pd.isna(legacy) and fixed == "xs_rank"                # era boundary visible
    m = SB.mature(idx[-1], closes, path=book)
    fresh = m[(m["date"] == asof) & (m["ticker"] == "B")].iloc[0]
    assert fresh["percentile"] == pytest.approx(2 / 3) and fresh["pct_basis"] == "xs_rank"


# --------------------------------------------------------------------------- #
# source pins: no producer may write the raw score into `percentile` again
# --------------------------------------------------------------------------- #
def test_producers_share_one_percentile_definition():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    bsl = (root / "scripts" / "build_stock_library.py").read_text()
    assert "rows_from_board" in bsl, "build_stock_library must reuse the shared rec builder"
    assert '"percentile": (r.get("conviction") or {}).get("score")' not in bsl
    ssb = (root / "scripts" / "snapshot_shadow_book.py").read_text()
    assert '"percentile": score' not in ssb
