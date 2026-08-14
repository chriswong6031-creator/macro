"""Tests for scripts/prophet_fusion_labels.py — the frozen §7 outcome frame.

WHAT THIS ENCODES.  The outcome definitions are frozen BEFORE any challenger exists
(masterplan §8.6), so the thing worth testing is not "does it compute a mean" — it is
that every way the frame could be quietly wrong is a typed refusal instead:

  empty store            -> StoreEmptyRefusal naming the store, never an empty frame
  percent-scaled input   -> LabelUnitsRefusal, because 0.10 == +10pp is load-bearing
  disclosed null era     -> rows EXCLUDED and COUNTED, never imputed, never silent
  two price_basis eras   -> PriceBasisPoolRefusal at the point of pooling (§9.4)
  a null outcome         -> pd.NA on every head, never False (#4485 null-never-false)
  a deferred head        -> reported as deferred, never proxied (§7 O4/O6)

Fixtures are frozen literals; no test reads a clock or opens a socket.

Run: python3 -m pytest tests/test_prophet_fusion_labels.py -q
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import prophet_fusion_labels as LABELS  # noqa: E402

REAL_LEDGER = ROOT / "data" / "us_board_ledger" / "retro_grades.parquet"

# Frozen literals: 2026-08-03..08-06 is the disclosed null era; 2026-07-30/31 and
# 2026-08-07 are ordinary graded dates on either side of it.
IN_ERA = ("2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06")
BEFORE_ERA = ("2026-07-30", "2026-07-31")
AFTER_ERA = ("2026-08-07", "2026-08-10")


def make_frame(dates=BEFORE_ERA + AFTER_ERA, *, tickers=("AAA", "BBB", "CCC"),
               horizons=(10, 21), excess=None, **extra) -> pd.DataFrame:
    """A minimal graded-store-shaped frame.  ``excess`` is a callable(i) or a scalar."""
    rows = []
    i = 0
    for date in dates:
        for ticker in tickers:
            for horizon in horizons:
                value = (excess(i) if callable(excess)
                         else (0.01 * (i % 7 - 3) if excess is None else excess))
                rows.append({"as_of": date, "ticker": ticker, "horizon": horizon,
                             "excess_spy": value,
                             "fwd_mfe": abs(value) + 0.01,
                             "fwd_mdd": -abs(value) - 0.01,
                             "price_basis": "adjusted", "rank_by": "confluence",
                             **{k: v for k, v in extra.items()}})
                i += 1
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# refusals
# --------------------------------------------------------------------------- #

def test_empty_caller_frame_refuses_naming_the_frame():
    with pytest.raises(LABELS.StoreEmptyRefusal) as exc:
        LABELS.build_labels(pd.DataFrame(), frame_name=LABELS.FRAME_BOARD_LEDGER)
    assert LABELS.FRAME_BOARD_LEDGER in str(exc.value)


def test_absent_board_ledger_parquet_refuses_naming_the_path(tmp_path):
    missing = tmp_path / "nope" / "retro_grades.parquet"
    with pytest.raises(LABELS.StoreEmptyRefusal) as exc:
        LABELS.load_board_ledger_frame(path=missing)
    assert str(missing) in str(exc.value)
    assert exc.value.store == str(missing)


def test_zero_row_parquet_refuses_rather_than_returning_it(tmp_path):
    target = tmp_path / "retro_grades.parquet"
    pd.DataFrame({"as_of": pd.Series(dtype="str")}).to_parquet(target)
    with pytest.raises(LABELS.StoreEmptyRefusal) as exc:
        LABELS.load_board_ledger_frame(path=target)
    assert "zero rows" in str(exc.value)


def test_empty_grades_store_refuses_by_name(monkeypatch):
    """The keystone store is empty TODAY (§4.0); an empty frame is not a population.

    ``load_grades`` is faked rather than read, so this test does not rot the day the
    store starts accruing — the contract under test is "empty in, refusal out".
    """
    import engine  # noqa: PLC0415 — package import only, no heavy submodule

    fake = types.ModuleType("engine.us_prophet_grades")
    fake.load_grades = lambda root=None: pd.DataFrame()
    monkeypatch.setattr(engine, "us_prophet_grades", fake, raising=False)
    monkeypatch.setitem(sys.modules, "engine.us_prophet_grades", fake)
    with pytest.raises(LABELS.StoreEmptyRefusal) as exc:
        LABELS.load_prophet_rank_frame()
    assert "us_prophet_rank/grades" in str(exc.value)
    assert "not a population" in str(exc.value)


def test_percent_scaled_excess_is_refused_not_silently_mis_thresholded():
    """A 100x unit error produces plausible output and meaningless tails."""
    frame = make_frame(excess=lambda i: float(i % 21 - 10))   # -10..+10 "percent"
    with pytest.raises(LABELS.LabelUnitsRefusal) as exc:
        LABELS.build_labels(frame)
    assert exc.value.column == "excess_spy"
    assert "fraction" in str(exc.value)


def test_frame_without_an_outcome_column_is_refused():
    frame = make_frame().drop(columns=["excess_spy"])
    with pytest.raises(LABELS.OutcomeColumnRefusal):
        LABELS.build_labels(frame)


def test_frame_without_a_date_column_is_refused():
    frame = make_frame().rename(columns={"as_of": "when"})
    with pytest.raises(LABELS.OutcomeColumnRefusal):
        LABELS.build_labels(frame)


# --------------------------------------------------------------------------- #
# era hygiene (§7, §9.4)
# --------------------------------------------------------------------------- #

def test_disclosed_null_era_rows_are_excluded_and_counted():
    frame = make_frame(dates=BEFORE_ERA + IN_ERA + AFTER_ERA)
    labels = LABELS.build_labels(frame)
    era = labels.receipt["era_hygiene"]
    assert era["rows_excluded"] == len(IN_ERA) * 3 * 2      # dates x tickers x horizons
    assert sorted(era["dates_excluded"]) == sorted(IN_ERA)
    assert not set(labels.dates) & set(IN_ERA)
    assert set(BEFORE_ERA + AFTER_ERA) <= set(labels.dates)
    assert era["source"].endswith("disclosed_gaps.json")


def test_era_exclusion_reads_the_committed_gap_file_not_a_hardcoded_window():
    eras, source = LABELS.disclosed_null_eras()
    assert source.endswith("disclosed_gaps.json")
    assert any(e.gap_id == "us-board-frozen-alpha-2026-08" for e in eras)
    assert all(e.covers(d) is False for e in eras for d in AFTER_ERA)
    assert any(e.covers("2026-08-04") for e in eras)


def test_missing_gap_file_falls_back_to_the_known_era_never_to_no_exclusion(tmp_path):
    eras, source = LABELS.disclosed_null_eras(tmp_path / "absent.json")
    assert source == "fallback_constant"
    assert any(e.covers("2026-08-04") for e in eras)


def test_a_gap_marked_gradeable_is_not_an_exclusion(tmp_path):
    doc = {"gaps": [{"id": "coverage-note", "market": "US", "gradeable": True,
                     "window": {"from": "2026-07-01", "to": "2026-07-02"},
                     "missing_trading_days": []}]}
    path = tmp_path / "gaps.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    eras, _ = LABELS.disclosed_null_eras(path)
    # no gradeable:false gap in the file -> the fallback stands in, and it does NOT
    # cover the gradeable window
    assert all(not e.covers("2026-07-01") for e in eras)


def test_price_basis_pooling_is_refused_without_the_explicit_flag():
    frame = make_frame()
    frame.loc[frame.index[: len(frame) // 2], "price_basis"] = "unverified_pre_20260806"
    labels = LABELS.build_labels(frame)
    assert labels.receipt["price_basis_pooled"] is False      # carried, not pooled
    with pytest.raises(LABELS.PriceBasisPoolRefusal) as exc:
        LABELS.assert_poolable(labels)
    assert "adjusted" in str(exc.value) and "unverified_pre_20260806" in str(exc.value)


def test_price_basis_pool_flag_tags_the_output_exploratory():
    frame = make_frame()
    frame.loc[frame.index[: len(frame) // 2], "price_basis"] = "unverified_pre_20260806"
    labels = LABELS.build_labels(frame)
    note = LABELS.assert_poolable(labels, allow_price_basis_pool=True)
    assert note["pooled"] is True and note["exploratory"] is True
    assert labels.receipt["exploratory"] is True
    assert "promotion-barred" in note["note"]


def test_single_price_basis_needs_no_flag():
    labels = LABELS.build_labels(make_frame())
    note = LABELS.assert_poolable(labels)
    assert note["status"] == "single_era" and note["exploratory"] is False


def test_scan_tier_rows_are_excluded_and_all_null_tier_is_not_called_curated():
    curated = make_frame(dates=BEFORE_ERA, universe_tier="curated")
    scan = make_frame(dates=BEFORE_ERA, tickers=("ZZZ",), universe_tier="scan")
    labels = LABELS.build_labels(pd.concat([curated, scan], ignore_index=True))
    assert labels.receipt["population"]["scan_rows_excluded"] == len(scan)
    assert "ZZZ" not in set(labels.frame["ticker"])

    unsplit = make_frame(dates=BEFORE_ERA, universe_tier=None)
    labels2 = LABELS.build_labels(unsplit)
    assert "not called curated" in labels2.receipt["population"]["universe_tier"]


# --------------------------------------------------------------------------- #
# the frozen heads (§7 O1/O2/O3/O5) and the deferred ones (O4/O6)
# --------------------------------------------------------------------------- #

def test_o1_and_o2_are_the_excess_and_its_sign():
    frame = make_frame(dates=BEFORE_ERA, tickers=("AAA",), horizons=(10,),
                       excess=lambda i: [0.05, -0.02][i % 2])
    labels = LABELS.build_labels(frame)
    got = labels.frame.sort_values("date")
    assert got["excess_spy"].tolist() == [0.05, -0.02]
    assert got["hit"].tolist() == [True, False]


def test_o3_tail_flags_use_the_frozen_ten_point_thresholds():
    frame = make_frame(dates=("2026-07-30",), tickers=("A", "B", "C"), horizons=(21,),
                       excess=lambda i: [0.12, -0.12, 0.03][i])
    labels = LABELS.build_labels(frame).frame.sort_values("ticker")
    assert labels["tail_win"].tolist() == [True, False, False]
    assert labels["tail_loss"].tolist() == [False, True, False]
    assert labels["tail_registered_read"].tolist() == [True, True, True]   # H=21
    assert LABELS.TAIL_WIN == 0.10 and LABELS.TAIL_LOSS == -0.10


def test_o3_mfe_and_mdd_are_carried_from_the_store_columns():
    frame = make_frame(dates=("2026-07-30",), tickers=("A",), horizons=(21,),
                       excess=0.05)
    labels = LABELS.build_labels(frame).frame
    assert labels["mfe"].iloc[0] == pytest.approx(0.06)
    assert labels["mdd"].iloc[0] == pytest.approx(-0.06)


def test_o3_reads_per_horizon_mfe_columns_when_that_is_the_store_shape():
    """retro_grades writes fwd_mfe_5/10/21; the grades store writes a flat fwd_mfe."""
    frame = make_frame(dates=("2026-07-30",), tickers=("A",), horizons=(10, 21),
                       excess=0.05).drop(columns=["fwd_mfe", "fwd_mdd"])
    frame["fwd_mfe_10"] = 0.11
    frame["fwd_mfe_21"] = 0.22
    frame["mae_close_excess_spy"] = -0.33
    labels = LABELS.build_labels(frame).frame.sort_values("horizon")
    assert labels["mfe"].tolist() == [0.11, 0.22]
    assert labels["mdd"].tolist() == [-0.33, -0.33]


def test_o5_fragility_threshold_is_per_horizon_and_null_where_unregistered():
    frame = make_frame(dates=("2026-07-30",), tickers=("A",), horizons=(5, 10, 21),
                       excess=-0.05)
    labels = LABELS.build_labels(frame).frame.sort_values("horizon")
    assert LABELS.FRAGILITY_BY_HORIZON == {10: -0.03, 21: -0.10}
    # H=5 has no registered threshold -> pd.NA, never the neighbour's number
    assert labels.loc[labels["horizon"] == 5, "fragile"].isna().all()
    assert bool(labels.loc[labels["horizon"] == 10, "fragile"].iloc[0]) is True   # -5<-3
    assert bool(labels.loc[labels["horizon"] == 21, "fragile"].iloc[0]) is False  # -5>-10
    assert labels.loc[labels["horizon"] == 10, "fragility_threshold"].iloc[0] == -0.03


def test_a_null_outcome_is_na_on_every_head_never_false():
    frame = make_frame(dates=("2026-07-30",), tickers=("A",), horizons=(10,),
                       excess=0.05)
    frame.loc[0, "excess_spy"] = np.nan
    row = LABELS.build_labels(frame).frame.iloc[0]
    for head in ("hit", "tail_win", "tail_loss", "fragile"):
        assert pd.isna(row[head]), f"{head} imputed a value onto an unmeasured row"


def test_deferred_heads_are_reported_and_never_proxied():
    labels = LABELS.build_labels(make_frame())
    assert list(labels.receipt["deferred_heads"]) == ["entry", "confidence"]
    assert set(labels.receipt["heads_built"]) == {"O1", "O2", "O3", "O5"}
    for head in ("entry", "confidence"):
        assert "No proxy." in labels.receipt["deferred_reason"][head]
    # nothing entry- or confidence-shaped snuck into the frame as a stand-in
    banned = ("entry", "false_start", "time_to_positive", "confidence", "calibr")
    for column in labels.frame.columns:
        assert not any(token in column.lower() for token in banned), column


def test_summary_prints_nulls_rather_than_hiding_a_head():
    frame = make_frame(dates=BEFORE_ERA, horizons=(5,))
    summary = LABELS.outcome_summary(LABELS.build_labels(frame))
    fragility = summary["by_horizon"]["5"]["O5_fragility"]
    assert fragility["threshold"] is None and fragility["rate"] is None
    assert "no registered fragility threshold" in fragility["note"]
    assert summary["by_horizon"]["5"]["O3_tails"]["registered_read"] is False


# --------------------------------------------------------------------------- #
# strata, dedupe, survivorship
# --------------------------------------------------------------------------- #

def test_strata_are_carried_and_absence_is_disclosed_not_filled():
    labels = LABELS.build_labels(make_frame())
    strata = labels.receipt["strata"]
    assert "price_basis" in strata["present"] and "rank_by" in strata["present"]
    assert "board_definition" in strata["absent"]        # retro_grades has no such column
    assert "board_definition" not in labels.frame.columns


def test_two_lanes_on_one_night_dedupe_to_one_outcome():
    frame = make_frame(dates=("2026-07-30",), tickers=("A",), horizons=(10,),
                       excess=0.05)
    doubled = pd.concat([frame.assign(lane="watch"), frame.assign(lane="leaders")],
                        ignore_index=True)
    labels = LABELS.build_labels(doubled)
    assert labels.receipt["duplicates_dropped"] == 1
    assert len(labels.frame) == 1


def test_survivorship_flag_is_pre_assigned_per_frame_and_rides_the_rows():
    labels = LABELS.build_labels(make_frame(), frame_name=LABELS.FRAME_BOARD_LEDGER)
    assert labels.receipt["survivorship_biased"] is True
    assert labels.frame["survivorship_biased"].all()


# --------------------------------------------------------------------------- #
# the committed frame (integration)
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(not REAL_LEDGER.exists(), reason="board ledger not committed here")
def test_the_committed_board_ledger_frame_builds_with_honest_depth():
    labels = LABELS.build_labels(frame_name=LABELS.FRAME_BOARD_LEDGER)
    receipt = labels.receipt
    assert receipt["rows_out"] > 0
    assert set(receipt["horizons"]) <= {5, 10, 21, 42, 63}
    # the disclosed era is already absent from this store — the exclusion is a
    # standing guard, and its own test asserts it FIRES on a frame that contains one
    assert receipt["era_hygiene"]["rows_excluded"] == 0
    assert receipt["n_dates"] < 60, (
        f"the graded frame now carries {receipt['n_dates']} dates — the §9.2 fold "
        f"survey and §8.7 power table must be re-read before this test is relaxed")
    assert receipt["survivorship_biased"] is True
    headline = str(min(receipt["horizons"]))
    assert LABELS.outcome_summary(labels)["by_horizon"][headline]["n"] > 0
