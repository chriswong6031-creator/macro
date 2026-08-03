"""tests/test_level_grades_summary.py — the live Level Report Card (MSC R2.4 v1).

The properties that fail silently: a Wilson interval that quietly becomes the
normal approximation (blows up at small n), a beats_null that reads the UPPER
bound, sticky=None rows counted as zeros instead of absent, and the synthetic
"_board" rows polluting role counts.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.build_level_grades_summary import (  # noqa: E402
    MIN_BOARDS,
    build_all,
    summarize,
    wilson_ci,
)


# ─── wilson_ci ────────────────────────────────────────────────────────────────


def test_wilson_matches_known_values():
    # canonical check: 8/10 → (0.4901, 0.9433) at z=1.96 (Wilson, not Wald)
    lo, hi = wilson_ci(8, 10)
    assert lo == pytest.approx(0.4902, abs=2e-3)
    assert hi == pytest.approx(0.9433, abs=2e-3)


def test_wilson_never_leaves_the_unit_interval():
    assert wilson_ci(0, 5)[0] == 0.0 or wilson_ci(0, 5)[0] > 0.0
    lo, hi = wilson_ci(5, 5)
    assert 0.0 <= lo <= hi <= 1.0
    lo0, hi0 = wilson_ci(0, 3)
    assert 0.0 <= lo0 <= hi0 <= 1.0


def test_wilson_declines_on_empty():
    assert wilson_ci(0, 0) is None


# ─── summarize ────────────────────────────────────────────────────────────────


def _frame(n_boards=40, held_true=18, held_false=6, sticky_none=4, root="AMD"):
    """n_boards boards; one call_wall node per board. First held_true+held_false
    nodes are touched+scored; next sticky_none are touched but UNSCORED (sticky
    undetermined → held None); the rest untouched."""
    rows = []
    for i in range(n_boards):
        date = f"2026-06-{(i % 28) + 1:02d}"
        board = f"b{i:03d}"
        touched = i < held_true + held_false + sticky_none
        scored = i < held_true + held_false
        rows.append({
            "board_id": board, "root": root, "session_date": date,
            "role": "call_wall", "level_id": f"n{i:03d}", "strike": 100.0 + i,
            "touched": touched,
            "held": (i < held_true) if scored else None,
            "broke": (held_true <= i < held_true + held_false) if scored else None,
            "post_touch_move_pct": None,
            "wall_contained": i % 2 == 0, "band_contained": True,
        })
        # one flip node per board, touched on even boards with a known move
        rows.append({
            "board_id": board, "root": root, "session_date": date,
            "role": "flip", "level_id": f"f{i:03d}", "strike": 99.0,
            "touched": i % 2 == 0, "held": None, "broke": None,
            "post_touch_move_pct": 1.5 if i % 2 == 0 else None,
            "wall_contained": i % 2 == 0, "band_contained": True,
        })
    return pd.DataFrame(rows)


def test_summarize_counts_scored_separately_from_touched():
    card = summarize(_frame(), "AMD")
    cw = card["roles"]["call_wall"]
    assert cw["nodes"] == 40
    assert cw["touched"] == 28         # 18 held + 6 broke + 4 unscored
    assert cw["scored"] == 24          # sticky=None rows are ABSENT, never zeros
    assert cw["held"] == 18
    assert cw["p_hold"] == pytest.approx(0.75)


def test_beats_null_reads_the_lower_bound():
    # 18/24 → Wilson lo ≈ 0.551 > 0.5 → beats; 13/24 (≈0.54) → lo < 0.5 → does not
    strong = summarize(_frame(held_true=18, held_false=6), "AMD")
    assert strong["roles"]["call_wall"]["beats_null"] is True
    weak = summarize(_frame(held_true=13, held_false=11), "AMD")
    assert weak["roles"]["call_wall"]["beats_null"] is False


def test_flip_reports_touch_count_and_mean_abs_move_not_a_hold_rate():
    card = summarize(_frame(), "AMD")
    assert "p_hold" not in card["flip"]
    assert card["flip"]["touched"] == 20
    assert card["flip"]["mean_abs_post_move_pct"] == pytest.approx(1.5)


def test_thin_roots_publish_nothing():
    assert summarize(_frame(n_boards=MIN_BOARDS - 1), "AMD") is None


def test_universe_card_carries_the_coverage_note_and_roots_do_not():
    df = _frame()
    uni = summarize(df, None)
    per = summarize(df, "AMD")
    assert uni["root"] == "_universe" and uni["coverage_note"]
    assert per["coverage_note"] is None


# ─── R2.4b: nulls + intraday variants ────────────────────────────────────────


def _frame_r24b(**kw):
    """The _frame fixture plus the R2.4b columns: every call_wall row carries a
    mirror-null verdict (weaker than the real one), pierce depth, and the board
    rows carry the intraday/prevday fields."""
    df = _frame(**kw)
    cw = df["role"] == "call_wall"
    # null: scored on the same rows the real level scored, holding at 50% exactly
    df.loc[cw, "null_touched"] = df.loc[cw, "touched"]
    scored = cw & df["held"].notna()
    idx = df.index[scored]
    df["null_held"] = None
    df.loc[idx, "null_held"] = [i % 2 == 0 for i in range(len(idx))]
    df.loc[cw & df["touched"], "pierce_pct"] = 0.8
    df["wall_range_contained"] = False
    df["band_close_contained"] = True
    df["pd_high_held"] = df["wall_contained"]
    df["pd_low_held"] = None
    df["pd_range_contained_close"] = True
    df["pd_range_contained_range"] = False
    return df


def test_null_fields_ride_the_card():
    card = summarize(_frame_r24b(), "AMD")
    cw = card["roles"]["call_wall"]
    ne = cw["null_equidistant"]
    assert ne["scored"] == 24 and ne["p_hold"] == pytest.approx(0.5)
    assert len(ne["ci95"]) == 2 and ne["ci95"][0] < 0.5 < ne["ci95"][1]
    # real 18/24 (Wilson lo ≈ .551) does NOT clear a 12/24 null's Wilson UPPER
    # (≈ .695) — at this n the two records are statistically indistinguishable,
    # and the interval-separation gate says so
    assert cw["beats_equidistant_null"] is False
    assert cw["median_pierce_pct"] == pytest.approx(0.8)
    b = card["boards"]
    assert b["wall_range_contained"] == {"rate": 0.0, "n": 40}
    assert b["band_close_contained"] == {"rate": 1.0, "n": 40}
    pdv = b["prevday_null"]
    assert pdv["range_contained_close"]["rate"] == 1.0
    assert "low_held" not in pdv  # all-None column → absent, never a fake 0%


def test_beats_equidistant_null_is_interval_separation():
    # The gate must ignore neither side's sampling error: a lucky SMALL null
    # sample must never hand out an edge (anti-conservative failure), while a
    # genuinely separated pair of records must still earn one.
    lo_real, _ = wilson_ci(18, 24)            # ≈ .551
    _, hi_small_null = wilson_ci(5, 20)       # 25% null but upper ≈ .455
    assert lo_real > hi_small_null            # sanity: separation CAN happen at small n

    # real 18/24 vs null 1/5: raw null rate .2 < real lo .551, but the null's
    # upper (≈ .624) straddles — the old raw-rate gate said True, this one must not
    df = _frame_r24b()
    idx = df.index[df["null_held"].notna()]
    df.loc[idx, "null_held"] = None
    df.loc[idx[:5], "null_held"] = [True, False, False, False, False]
    cw = summarize(df, "AMD")["roles"]["call_wall"]
    assert cw["null_equidistant"]["p_hold"] == pytest.approx(0.2)
    assert cw["beats_equidistant_null"] is False

    # and a null holding at 80% must obviously not be beaten either
    df2 = _frame_r24b()
    df2.loc[df2["null_held"].notna(), "null_held"] = [i % 5 != 0 for i in range(24)]
    cw2 = summarize(df2, "AMD")["roles"]["call_wall"]
    assert cw2["beats_equidistant_null"] is False


def test_beats_equidistant_null_true_when_records_truly_separate():
    # production-scale n: real 700/1000 (Wilson lo ≈ .671) vs null 500/1000
    # (upper ≈ .531) — separated intervals, the edge is earned
    rows = []
    for i in range(1000):
        rows.append({
            "board_id": f"b{i:04d}", "root": "AMD",
            "session_date": f"2026-{(i % 6) + 1:02d}-{(i % 28) + 1:02d}",
            "role": "call_wall", "level_id": f"n{i:04d}", "strike": 100.0,
            "touched": True, "held": i < 700, "broke": i >= 700,
            "post_touch_move_pct": None, "wall_contained": True, "band_contained": True,
            "null_touched": True, "null_held": i < 500, "pierce_pct": None,
        })
    card = summarize(pd.DataFrame(rows), "AMD")
    cw = card["roles"]["call_wall"]
    assert cw["p_hold"] == pytest.approx(0.7)
    assert cw["null_equidistant"]["p_hold"] == pytest.approx(0.5)
    assert cw["beats_equidistant_null"] is True


def test_pre_r24b_parquet_degrades_to_the_v1_card():
    # no new columns at all → no null/intraday keys, and nothing crashes
    card = summarize(_frame(), "AMD")
    cw = card["roles"]["call_wall"]
    assert "null_equidistant" not in cw and "median_pierce_pct" not in cw
    assert "wall_range_contained" not in card["boards"]
    assert "prevday_null" not in card["boards"]
    assert card["roles"]["call_wall"]["beats_null"] is True  # v1 gate untouched


def test_build_all_excludes_synthetic_board_rows(tmp_path):
    df = _frame()
    df = pd.concat([df, pd.DataFrame([{
        "board_id": "empty", "root": "AMD", "session_date": "2026-06-01",
        "role": "_board", "level_id": "e0", "strike": None,
        "touched": False, "held": None, "broke": None,
        "post_touch_move_pct": None, "wall_contained": None, "band_contained": None,
    }])], ignore_index=True)
    p = tmp_path / "grades.parquet"
    df.to_parquet(p)
    out = build_all(p)
    assert "_universe" in out and "AMD" in out
    assert all("_board" not in c["roles"] for c in out.values())
