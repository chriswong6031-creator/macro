"""Suite for the US entry-status re-measurement (PROPHET US ANTICIPATION §6.6).

The block revises the entry-value ladder's constants, so the things that must not drift are
its DEFINITIONS, not just its plumbing: what counts as a loser, when a cell is thin, that a
lane is never pooled, and that a null is printed rather than rendered as a zero.

Every test runs against a synthetic ledger written into a tmp root, so nothing here depends
on tonight's real record — a suite that only passes while the live ledger has a particular
shape is a suite that will start lying the night the shape changes.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pandas as pd
import pytest

from engine import prophet_miss_audit as pma
from engine import us_entry_status_remeasure as uesr


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #

def _write_ledger(root: Path, rows: list[dict]) -> Path:
    path = root / uesr.LEDGER_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def _row(*, as_of="2026-07-01", horizon=10, lane="buy", ticker="AAA",
         entry_status="bounce_wait", excess_spy=0.01) -> dict:
    return {"as_of": as_of, "horizon": horizon, "lane": lane, "ticker": ticker,
            "entry_status": entry_status, "excess_spy": excess_spy}


def _cell(block: dict, cohort: str, horizon: int, status: str) -> dict:
    return block["by_cohort"][cohort][f"{horizon}d"]["by_entry_status"][status]


@pytest.fixture()
def store(tmp_path: Path) -> Path:
    """A ledger with a KNOWN answer in every cell the assertions below read.

    buy/10d/bounce_wait: 21 marks, 5 of them <= 0  -> loser 5/21, not thin
    buy/10d/buy_now:      4 marks, 3 of them <= 0  -> loser 0.75, THIN
    watch/10d/bounce_wait: 2 marks, both > 0       -> loser 0.0, THIN (a second LANE)
    buy/21d/hold:         3 marks, all null excess -> printed null, not a zero
    """
    rows: list[dict] = []
    # 20 buy-lane bounce_wait marks: 15 winners at +2%, 5 losers (one of them EXACTLY flat,
    # which the CN convention counts as a loss).
    for i in range(15):
        rows.append(_row(ticker=f"W{i}", excess_spy=0.02))
    for i in range(4):
        rows.append(_row(ticker=f"L{i}", excess_spy=-0.03))
    rows.append(_row(ticker="FLAT", excess_spy=0.0))
    # 4 buy-lane buy_now marks -> thin
    for i, x in enumerate((-0.01, -0.02, -0.05, 0.04)):
        rows.append(_row(ticker=f"B{i}", entry_status="buy_now", excess_spy=x))
    # a second lane, so pooling would be visible
    for i in range(2):
        rows.append(_row(ticker=f"V{i}", lane="watch", excess_spy=0.10))
    # a cell whose marks are all missing
    for i in range(3):
        rows.append(_row(ticker=f"N{i}", horizon=21, entry_status="hold", excess_spy=None))
    # an episode with NO status at all — excluded from the table, counted in coverage
    rows.append(_row(ticker="NOSTAT", entry_status=None, excess_spy=0.5))
    # two stamp dates, so n_dates is a real count
    rows.append(_row(as_of="2026-07-02", ticker="D2", excess_spy=0.02))
    _write_ledger(tmp_path, rows)
    return tmp_path


# --------------------------------------------------------------------------- #
# grouping correctness
# --------------------------------------------------------------------------- #

class TestGrouping:
    def test_cells_are_keyed_cohort_then_horizon_then_status(self, store):
        block = uesr.scorecard(store)
        assert block["available"] is True
        assert set(block["by_cohort"]) == {"buy", "watch"}
        assert set(block["by_cohort"]["buy"]) == {"10d", "21d"}
        assert "bounce_wait" in block["by_cohort"]["buy"]["10d"]["by_entry_status"]

    def test_counts_and_rates_are_exact(self, store):
        leg = _cell(uesr.scorecard(store), "buy", 10, "bounce_wait")
        # 21 rows land in this cell (20 same-date + 1 on the second date)
        assert leg["n"] == 21
        assert leg["n_excess"] == 21
        # 5 non-positive marks of 21: four negatives and the exactly-flat one
        assert leg["loser_rate"] == pytest.approx(5 / 21, abs=1e-4)
        assert leg["win_rate"] == pytest.approx(16 / 21, abs=1e-4)
        assert leg["median_excess"] == pytest.approx(0.02, abs=1e-6)

    def test_a_flat_mark_counts_as_a_loss(self, tmp_path):
        """The CN §2.3 convention: ``excess <= 0``. A flat episode is not a half-win."""
        _write_ledger(tmp_path, [_row(ticker=f"F{i}", excess_spy=0.0) for i in range(4)])
        leg = _cell(uesr.scorecard(tmp_path), "buy", 10, "bounce_wait")
        assert leg["loser_rate"] == 1.0
        assert leg["win_rate"] == 0.0

    def test_loser_and_win_rate_are_exact_complements(self, store):
        for legs in uesr.scorecard(store)["by_cohort"].values():
            for cell in legs.values():
                for leg in (cell.get("by_entry_status") or {}).values():
                    if leg.get("loser_rate") is None:
                        continue
                    assert leg["loser_rate"] + leg["win_rate"] == pytest.approx(1.0,
                                                                               abs=1e-4)

    def test_lanes_are_never_pooled(self, store):
        """The watch-lane winners must not move the buy lane's loser rate."""
        block = uesr.scorecard(store)
        buy = _cell(block, "buy", 10, "bounce_wait")
        watch = _cell(block, "watch", 10, "bounce_wait")
        assert buy["n_excess"] == 21 and watch["n_excess"] == 2
        assert watch["loser_rate"] == 0.0
        assert buy["loser_rate"] > 0.0

    def test_an_episode_with_no_status_is_excluded_and_counted(self, store):
        block = uesr.scorecard(store)
        cell = block["by_cohort"]["buy"]["10d"]
        assert cell["n_status_missing"] == 1
        assert "status_missing_note" in cell
        # excluded from every status cell, but present in the horizon's episode count
        assert sum(leg["n"] for leg in cell["by_entry_status"].values()) == \
            cell["n_episodes"] - 1
        # and visible in coverage
        assert block["coverage"]["n_episodes"] == 31
        assert block["coverage"]["n_with_status"] == 30
        assert block["coverage"]["n_dates"] == 2

    def test_an_unlaned_episode_is_never_folded_into_buy(self, tmp_path):
        _write_ledger(tmp_path, [_row(lane=None, ticker="X"), _row(ticker="Y")])
        block = uesr.scorecard(tmp_path)
        assert set(block["by_cohort"]) == {"unlaned", "buy"}
        assert block["cohort_split"]["n_unlaned"] == 1


# --------------------------------------------------------------------------- #
# thin + null labelling
# --------------------------------------------------------------------------- #

class TestThinAndNullLabelling:
    def test_a_cell_below_the_floor_is_labelled_thin_with_a_reason(self, store):
        leg = _cell(uesr.scorecard(store), "buy", 10, "buy_now")
        assert leg["n_excess"] == 4 < uesr.THIN_MIN_N
        assert leg["thin"] is True
        assert "directional" in leg["thin_reason"].lower()
        # still PRINTED: a thin cell is the state of the record, not a hidden one
        assert leg["loser_rate"] == 0.75

    def test_a_cell_at_or_above_the_floor_is_not_thin(self, store):
        leg = _cell(uesr.scorecard(store), "buy", 10, "bounce_wait")
        assert leg["n_excess"] >= uesr.THIN_MIN_N
        assert leg["thin"] is False
        assert "thin_reason" not in leg

    def test_thin_statuses_are_listed_on_the_horizon(self, store):
        cell = uesr.scorecard(store)["by_cohort"]["buy"]["10d"]
        assert cell["thin_statuses"] == ["buy_now"]

    def test_a_cell_with_no_marks_is_a_printed_null_not_a_zero(self, store):
        leg = _cell(uesr.scorecard(store), "buy", 21, "hold")
        assert leg["n"] == 3 and leg["n_excess"] == 0
        assert leg["loser_rate"] is None and leg["win_rate"] is None
        assert leg["median_excess"] is None and leg["mean_excess"] is None
        assert "not computable" in leg["null_reason"]
        assert "0%" in leg["null_reason"]

    def test_a_horizon_with_no_statuses_at_all_says_so(self, tmp_path):
        _write_ledger(tmp_path, [_row(entry_status=None, ticker=f"Z{i}") for i in range(3)])
        cell = uesr.scorecard(tmp_path)["by_cohort"]["buy"]["10d"]
        assert cell["by_entry_status"] == {}
        assert "not a flat table" in cell["null_reason"]

    def test_an_absent_ledger_is_null_with_a_degraded_row(self, tmp_path):
        deg: list[dict] = []
        block = uesr.scorecard(tmp_path, deg)
        assert block["available"] is False
        assert "not a null result" in block["null_reason"]
        assert deg and deg[0]["input"] == uesr.LEDGER_REL

    def test_an_empty_but_schemad_ledger_is_null_not_a_flat_table(self, tmp_path):
        """The real day-one shape: the grader has created the file but graded nothing."""
        path = tmp_path / uesr.LEDGER_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=list(uesr.LEDGER_COLUMNS)).to_parquet(path, index=False)
        block = uesr.scorecard(tmp_path)
        assert block["available"] is False
        assert "not a flat table" in block["null_reason"]

    def test_a_columnless_file_degrades_rather_than_pretending_to_be_empty(self, tmp_path):
        """A file with no schema at all is UNREADABLE for this purpose, not empty."""
        _write_ledger(tmp_path, [])
        deg: list[dict] = []
        block = uesr.scorecard(tmp_path, deg)
        assert block["available"] is False
        assert deg and deg[0]["input"] == uesr.LEDGER_REL
        assert uesr.STATUS_COLUMN in deg[0]["reason"]

    def test_an_absent_optional_column_costs_only_the_read_that_used_it(self, tmp_path):
        """The ledger's writer is a live file — a renamed ``lane`` must not null the table."""
        rows = [{"as_of": "2026-07-01", "horizon": 10, "ticker": f"T{i}",
                 "entry_status": "bounce_wait", "excess_spy": 0.01 * (i - 1)}
                for i in range(4)]
        _write_ledger(tmp_path, rows)
        deg: list[dict] = []
        block = uesr.scorecard(tmp_path, deg)
        assert block["available"] is True
        assert set(block["by_cohort"]) == {"unlaned"}
        assert _cell(block, "unlaned", 10, "bounce_wait")["n"] == 4
        assert deg and uesr.COHORT_COLUMN in deg[0]["reason"]
        assert deg[0]["severity"] == "expected"

    def test_an_absent_required_column_is_named_and_nulls_the_table(self, tmp_path):
        rows = [{"as_of": "2026-07-01", "lane": "buy", "ticker": "T",
                 "entry_status": "hold", "excess_spy": 0.01}]      # no `horizon`
        _write_ledger(tmp_path, rows)
        deg: list[dict] = []
        block = uesr.scorecard(tmp_path, deg)
        assert block["available"] is False
        assert deg and "horizon" in deg[0]["reason"]

    def test_a_ledger_missing_the_status_column_names_the_missing_half(self, tmp_path):
        path = tmp_path / uesr.LEDGER_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([{"as_of": "2026-07-01", "horizon": 10, "lane": "buy",
                       "ticker": "AAA", "excess_spy": 0.01}]).to_parquet(path, index=False)
        deg: list[dict] = []
        block = uesr.scorecard(tmp_path, deg)
        assert block["available"] is False
        assert deg and uesr.STATUS_COLUMN in deg[0]["reason"]

    def test_definitions_are_stated_on_the_block(self, store):
        block = uesr.scorecard(store)
        assert "<= 0" in block["definitions"]["loser_and_win"]
        assert "0.01 = +1.00%" in block["definitions"]["excess_unit"]
        assert block["thin_min_n"] == uesr.THIN_MIN_N
        # the ruler is named, and named as REUSED
        assert "forward_metrics" in block["graded_by"]
        assert "Nothing is regraded here" in block["graded_by"]


# --------------------------------------------------------------------------- #
# no pooled top-level figure (W7 house style)
# --------------------------------------------------------------------------- #

class TestNoPooledFigure:
    OUTCOME_KEYS = {"loser_rate", "win_rate", "median_excess", "mean_excess"}

    def _walk(self, node, path=()):
        if isinstance(node, dict):
            for k, v in node.items():
                yield path, k, v
                yield from self._walk(v, path + (str(k),))
        elif isinstance(node, list):
            for item in node:
                yield from self._walk(item, path + ("[]",))

    def test_no_outcome_statistic_exists_outside_by_cohort(self, store):
        block = uesr.scorecard(store)
        offenders = [
            path + (key,)
            for path, key, _ in self._walk(block)
            if key in self.OUTCOME_KEYS and "by_cohort" not in path
        ]
        # NO EXEMPTION LIST on purpose. Every other key in the block — the definitions, the
        # CN restatement — is named so that it cannot collide with an outcome statistic, so
        # any hit here is a genuine pooled figure rather than a false positive to whitelist.
        assert not offenders, f"pooled outcome figure(s) leaked to the top level: {offenders}"

    def test_the_top_level_carries_counts_and_dates_only(self, store):
        cov = uesr.scorecard(store)["coverage"]
        assert set(cov) <= {"n_episodes", "n_with_status", "status_coverage_pct",
                            "n_excess", "n_dates", "as_of", "n_by_status", "note"}

    def test_the_block_says_why_there_is_no_pooled_figure(self, store):
        assert "lane mix" in uesr.scorecard(store)["no_pooled_figure"]

    def test_the_cn_reference_is_labelled_as_not_a_us_measurement(self, store):
        ref = uesr.scorecard(store)["cn_reference"]
        assert "NOT a US measurement" in ref["note"]
        assert ref["cn_loser_rate_by_status"]["bounce_wait"] == 0.069


# --------------------------------------------------------------------------- #
# idempotency + the write fence (this module has no writer, so it has no gate)
# --------------------------------------------------------------------------- #

class TestIdempotencyAndWriteFence:
    def _snapshot(self, root: Path) -> dict[str, float]:
        return {str(p): p.stat().st_mtime_ns for p in sorted(root.rglob("*")) if p.is_file()}

    def test_two_runs_return_the_same_block(self, store):
        assert uesr.scorecard(store) == uesr.scorecard(store)

    def test_a_run_writes_nothing_under_the_root(self, store):
        before = self._snapshot(store)
        uesr.scorecard(store)
        assert self._snapshot(store) == before

    def test_it_writes_nothing_off_the_nightly_lane_either(self, store, monkeypatch):
        """No writer means no lane gate to get wrong — pinned, not asserted in prose.

        The sibling forward ledgers gate on ``ledger_lane.nightly_advance_enabled()`` as
        their first statement.  This module has nothing to gate: it must behave identically
        on and off the nightly lane, and touch the tree on neither.
        """
        monkeypatch.delenv("COLLECT_LANE", raising=False)
        monkeypatch.delenv("US_LANE", raising=False)
        before = self._snapshot(store)
        off_lane = uesr.scorecard(store)
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        on_lane = uesr.scorecard(store)
        assert off_lane == on_lane
        assert self._snapshot(store) == before

    def test_the_module_contains_no_write_call(self):
        """A grep fence, because a docstring is not a guarantee."""
        src = inspect.getsource(uesr)
        for shape in ("to_parquet(", "to_csv(", "write_text(", "write_bytes(",
                      "os.replace(", "mkdir(", "json.dump("):
            assert shape not in src, f"{shape} — this module must stay a pure read"

    def test_the_block_is_strict_json(self, store):
        """A bare NaN would be invalid JSON and a strict reader rejects the whole nightly."""
        text = json.dumps(uesr.scorecard(store), allow_nan=False)
        assert "NaN" not in text and "Infinity" not in text

    def test_non_finite_marks_become_nulls_not_nans(self, tmp_path):
        _write_ledger(tmp_path, [_row(ticker="A", excess_spy=float("nan")),
                                 _row(ticker="B", excess_spy=float("inf"))])
        leg = _cell(uesr.scorecard(tmp_path), "buy", 10, "bounce_wait")
        # inf is a real (if absurd) mark; nan is a missing one. Neither may reach the JSON.
        assert json.dumps(leg, allow_nan=False)
        assert leg["mean_excess"] is None or isinstance(leg["mean_excess"], float)


# --------------------------------------------------------------------------- #
# flat forward-log row + summary
# --------------------------------------------------------------------------- #

class TestRowFieldsAndSummary:
    def test_the_flat_columns_do_not_depend_on_tonights_data(self, store, tmp_path):
        """A log whose columns move with the data is not a series anyone can plot."""
        rich = uesr.row_fields({"entry_status_scorecard": uesr.scorecard(store)})
        _write_ledger(tmp_path, [_row(entry_status="watch", ticker="Q")])
        thin = uesr.row_fields({"entry_status_scorecard": uesr.scorecard(tmp_path)})
        assert set(rich) == set(thin)
        expected = 4 + len(uesr.LOG_COHORTS) * len(uesr.HORIZONS) * len(
            uesr.LOG_STATUSES) * 3
        assert len(rich) == expected

    def test_the_flat_row_carries_the_headline_cells(self, store):
        row = uesr.row_fields({"entry_status_scorecard": uesr.scorecard(store)})
        assert row["entry_status_available"] is True
        assert row["entry_status_buy_bounce_wait_10d_n"] == 21
        assert row["entry_status_buy_buy_now_10d_loser_rate"] == 0.75
        # a horizon with no data is a null column, never a zero
        assert row["entry_status_buy_bounce_wait_63d_n"] is None

    def test_row_fields_is_null_safe_on_a_doc_with_no_block(self):
        row = uesr.row_fields({})
        assert row["entry_status_available"] is False
        assert row["entry_status_n_episodes"] is None

    def test_summary_lines_render_a_null_block_without_raising(self):
        lines = uesr.summary_lines({"available": False, "null_reason": "no ledger"})
        assert lines == ["  entry_status: null — no ledger"]
        assert uesr.summary_lines(None)

    def test_summary_lines_mark_thin_cells(self, store):
        text = "\n".join(uesr.summary_lines(uesr.scorecard(store)))
        assert "buy_now:n=4/lose=0.75*" in text
        assert "bounce_wait:n=21/lose=0.2381 " in text or \
               "bounce_wait:n=21/lose=0.2381\n" in text
        assert "* = thin" in text

    def test_horizons_print_in_ladder_order_not_lexical_order(self):
        keys = ["10d", "21d", "5d", "63d"]
        assert sorted(keys, key=uesr.cell_sort_key) == ["5d", "10d", "21d", "63d"]


# --------------------------------------------------------------------------- #
# miss-audit wiring
# --------------------------------------------------------------------------- #

class TestMissAuditWiring:
    def test_the_audit_exposes_the_block_through_its_own_wrapper(self, store):
        deg: list[dict] = []
        block = pma.entry_status_scorecard(store, deg)
        assert block["available"] is True
        assert block == uesr.scorecard(store)

    def test_the_wrapper_degrades_instead_of_raising(self, tmp_path):
        deg: list[dict] = []
        block = pma.entry_status_scorecard(tmp_path, deg)
        assert block["available"] is False
        assert deg

    def test_the_row_fields_wrapper_delegates(self, store):
        doc = {"entry_status_scorecard": uesr.scorecard(store)}
        assert pma.entry_status_row_fields(doc) == uesr.row_fields(doc)

    def test_the_block_is_wired_into_the_document_and_the_forward_log(self):
        """Pins the wiring itself — a block computed and then dropped is invisible."""
        assert '"entry_status_scorecard": entry_status' in inspect.getsource(pma.build_audit)
        assert "entry_status_row_fields(doc)" in inspect.getsource(pma.summary_row)
        assert "with_entry_status" in inspect.signature(pma.build_audit).parameters

    def test_the_ledger_path_constant_agrees_with_the_owning_module(self):
        assert pma.ENTRY_STATUS_LEDGER_REL == uesr.LEDGER_REL

    def test_the_w7_store_absence_is_disclosed_not_silent(self, store):
        """§6.6 named a store that cannot answer the question; the block must say so."""
        note = uesr.scorecard(store)["w7_priority_store"]
        assert "us_prophet_rank" in note
        assert "never been written" in note
        assert "non-injective" in note
