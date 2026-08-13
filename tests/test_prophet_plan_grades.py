"""engine/prophet_plan_grades.py — the Prophet plan-ledger benchmark SIDECAR.

What this suite pins, in the order the traps bite:

1. DIRECTION SIGNING. The excess columns are signed by the plan's ``direction`` at
   write time.  The ledger is 100% BULL today, so the short case is SYNTHETIC and
   deliberately so: a sign flip in ``grade_plan`` would be invisible against live data
   forever, and this is the one defect (``qledger``'s unsigned ``excess``,
   ``engine/qledger_validity.py`` V1) the house has already had to declare once.
2. ONE PRICE BASIS OR NO ROW.  A name with no adjusted series is REFUSED with a
   reason, never priced off the raw cache and differenced against an adjusted SPY.
3. SURVIVORSHIP.  A plan we could not price still produces a ROW.  A missing row and
   a plan that never existed are indistinguishable, which is how a record flatters
   itself.
4. LEDGER LAW G0.2.  The writer gates on the nightly lane as its first statement, and
   it opens the sidecar — never ``ledger.jsonl``.
5. HONEST EXCURSION LABELS.  Every excursion column carries ``close`` in its name and
   the header says close-only under-states intraday.
6. THE COMMITTED ARTIFACT itself: every closed plan is accounted for, and every priced
   row names its basis.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from engine import prophet_plan_grades as ppg

REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / "data" / "prophet" / "ledger.jsonl"
SIDECAR = REPO / "data" / "prophet" / "plan_grades.jsonl"


# --------------------------------------------------------------------------- #
# fixtures — a tiny synthetic price store shaped exactly like data/yahoo/<T>.parquet
# --------------------------------------------------------------------------- #

def _write_prices(data_dir: Path, ticker: str, closes: list[float],
                  start: str = "2026-01-05") -> None:
    index = pd.bdate_range(start, periods=len(closes))
    frame = pd.DataFrame({"close": closes}, index=index)
    (data_dir / "yahoo").mkdir(parents=True, exist_ok=True)
    frame.to_parquet(data_dir / "yahoo" / f"{ticker}.parquet")


@pytest.fixture()
def store(tmp_path: Path) -> Path:
    """NAME falls 20% while SPY rises 10% over the window — the case where a long and
    a short plan MUST grade with opposite signs."""
    data_dir = tmp_path / "data"
    _write_prices(data_dir, "FALLER", [100.0, 100.0, 95.0, 90.0, 85.0, 80.0])
    _write_prices(data_dir, "SPY", [100.0, 100.0, 102.5, 105.0, 107.5, 110.0])
    _write_prices(data_dir, "XLF", [100.0, 100.0, 101.0, 102.0, 103.0, 104.0])
    return data_dir


def _plan(direction: str, asset: str = "FALLER") -> dict:
    return {
        "schema": "prophet.ledger/v1",
        "id": f"{asset}-{direction}-20260105",
        "asset": asset,
        "direction": direction,
        "signal_date": "2026-01-05",
        "close_date": "2026-01-12",
        "outcome": "EXPIRED",
        "stock_result_pct": -20.0,
    }


def _graded(plan: dict, store_dir: Path) -> dict:
    rows = ppg.grade_plan(
        plan, data_dir=str(store_dir), dead_prices={},
        sectors={plan["asset"]: "Financials"}, graded_at="2026-01-20")
    realized = [r for r in rows if r["horizon"] == ppg.REALIZED]
    assert len(realized) == 1
    return realized[0]


# --------------------------------------------------------------------------- #
# 1. direction signing
# --------------------------------------------------------------------------- #

class TestDirectionSigning:
    def test_sign_map(self):
        assert ppg.direction_sign("BULL") == 1
        assert ppg.direction_sign("long") == 1
        assert ppg.direction_sign("BEAR") == -1
        assert ppg.direction_sign("short") == -1
        # unrecognised is a REFUSAL, never a silent 0 or a silent long
        assert ppg.direction_sign("SIDEWAYS") is None
        assert ppg.direction_sign(None) is None

    def test_short_plan_that_wins_has_positive_excess(self, store):
        """SYNTHETIC SHORT — the live ledger is 100% BULL, so nothing else can catch a
        sign flip here.  Name −20%, SPY +10%: the short was RIGHT, so excess is +30."""
        row = _graded(_plan("BEAR"), store)
        assert row["direction_sign"] == -1
        assert row["name_ret_pct"] == pytest.approx(-20.0, abs=1e-6)
        assert row["bench_ret_pct"] == pytest.approx(10.0, abs=1e-6)
        assert row["excess_vs_bench_pct"] == pytest.approx(30.0, abs=1e-6)
        assert row["excess_vs_sector_pct"] == pytest.approx(24.0, abs=1e-6)

    def test_long_plan_on_the_same_tape_has_the_opposite_sign(self, store):
        """The mutation this pins: drop the ``sign *`` and both rows read −30, so the
        two assertions can only pass together if the sign is actually applied."""
        short_row = _graded(_plan("BEAR"), store)
        long_row = _graded(_plan("BULL"), store)
        assert long_row["excess_vs_bench_pct"] == pytest.approx(-30.0, abs=1e-6)
        assert short_row["excess_vs_bench_pct"] == -long_row["excess_vs_bench_pct"]
        # the RAW tape legs are identical and UNSIGNED — only excess carries direction
        assert short_row["name_ret_pct"] == long_row["name_ret_pct"]
        assert short_row["bench_ret_pct"] == long_row["bench_ret_pct"]

    def test_unreadable_direction_refuses_rather_than_grading_long(self, store):
        plan = _plan("BULL")
        plan["direction"] = "???"
        rows = ppg.grade_plan(plan, data_dir=str(store), dead_prices={},
                              sectors={}, graded_at="2026-01-20")
        assert len(rows) == 1
        assert rows[0]["price_basis"] is None
        assert "direction" in rows[0]["refusal_reason"]


# --------------------------------------------------------------------------- #
# 2 + 3. one basis or no row; the refused plan is still NAMED
# --------------------------------------------------------------------------- #

class TestBasisAndSurvivorship:
    def test_name_with_no_adjusted_series_is_refused_not_mixed(self, store):
        plan = _plan("BULL", asset="NOPRICE")
        rows = ppg.grade_plan(plan, data_dir=str(store), dead_prices={},
                              sectors={}, graded_at="2026-01-20")
        assert len(rows) == 1
        row = rows[0]
        assert row["price_basis"] is None
        assert row["price_source"] is None
        assert row["name_ret_pct"] is None
        assert row["excess_vs_bench_pct"] is None
        # TRAP 5: the plan is still IN the output, with its id and a stated reason
        assert row["id"] == plan["id"]
        assert row["asset"] == "NOPRICE"
        assert "adjusted" in row["refusal_reason"].lower()

    def test_priced_rows_are_all_adjusted(self, store):
        rows = ppg.grade_plan(_plan("BULL"), data_dir=str(store), dead_prices={},
                              sectors={"FALLER": "Financials"}, graded_at="2026-01-20")
        assert rows
        for row in rows:
            assert row["price_basis"] == "adjusted"
            assert row["price_source"] == "yahoo"

    def test_missing_sector_costs_only_the_sector_leg(self, store):
        """U (Unity) has no GICS sector on record.  The SPY leg must survive that."""
        row = ppg.grade_plan(_plan("BULL"), data_dir=str(store), dead_prices={},
                             sectors={}, graded_at="2026-01-20")[0]
        assert row["sector_symbol"] is None
        assert row["excess_vs_sector_pct"] is None
        assert row["excess_vs_bench_pct"] is not None
        assert "sector" in row["refusal_reason"]
        assert row["price_basis"] == "adjusted"   # still a PRICED row


# --------------------------------------------------------------------------- #
# 4. ledger law G0.2
# --------------------------------------------------------------------------- #

class TestLedgerLaw:
    def test_append_is_gated_on_the_nightly_lane(self, tmp_path, monkeypatch):
        monkeypatch.delenv("COLLECT_LANE", raising=False)
        monkeypatch.delenv("US_LANE", raising=False)
        target = tmp_path / "plan_grades.jsonl"
        written = ppg.append_plan_grades([_plan("BULL")], path=target)
        assert written == 0
        assert not target.exists(), "an intraday lane must not create the sidecar"

    def test_nightly_lane_writes_a_headed_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        target = tmp_path / "plan_grades.jsonl"
        row = {"id": "X-BULL-1", "horizon": "realized", "price_basis": "adjusted"}
        assert ppg.append_plan_grades([row], path=target) == 1
        assert target.read_text(encoding="utf-8").startswith("#")
        assert ppg.read_jsonl(target) == [row]

    def test_a_priced_grade_is_frozen_but_a_refusal_may_be_upgraded(
            self, tmp_path, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        target = tmp_path / "plan_grades.jsonl"
        ppg.append_plan_grades(
            [{"id": "A", "horizon": "realized", "price_basis": "adjusted",
              "excess_vs_bench_pct": 1.0},
             {"id": "B", "horizon": "realized", "price_basis": None,
              "refusal_reason": "no adjusted series"}],
            path=target)
        rewritten = ppg.append_plan_grades(
            [{"id": "A", "horizon": "realized", "price_basis": "adjusted",
              "excess_vs_bench_pct": 999.0},
             {"id": "B", "horizon": "realized", "price_basis": "adjusted",
              "excess_vs_bench_pct": 2.0}],
            path=target)
        assert rewritten == 1
        rows = {r["id"]: r for r in ppg.read_jsonl(target)}
        assert rows["A"]["excess_vs_bench_pct"] == 1.0, "a priced grade is FROZEN"
        assert rows["B"]["excess_vs_bench_pct"] == 2.0, "a refusal is upgradable"
        assert len(ppg.read_jsonl(target)) == 2

    def test_the_intraday_evaluator_still_writes_nothing_under_data(self):
        """G0.2 as a STATIC fact about the 80×-a-session lane, not a claim in a docstring."""
        source = (REPO / "scripts" / "prophet_live_evaluator.py").read_text(encoding="utf-8")
        assert "prophet_plan_grades" not in source
        for token in ('open("data/', "open('data/", 'to_parquet("data/', "DATA_DIR"):
            assert token not in source, f"{token} appeared in the intraday lane"

    def test_the_nightly_closer_is_the_only_caller(self):
        callers = sorted(
            p.name for p in (*(REPO / "scripts").glob("*.py"),
                             *(REPO / "engine").glob("*.py"))
            if "prophet_plan_grades" in p.read_text(encoding="utf-8")
            and p.name != "prophet_plan_grades.py")
        assert callers == ["build_prophet.py"], callers


# --------------------------------------------------------------------------- #
# 5. excursion honesty
# --------------------------------------------------------------------------- #

class TestExcursionHonesty:
    def test_every_excursion_field_says_close(self, store):
        row = _graded(_plan("BULL"), store)
        excursions = [k for k in row if "mfe" in k or "mae" in k]
        assert excursions
        for key in excursions:
            assert "close" in key, f"{key} does not disclose that it is close-only"

    def test_header_labels_close_only_and_the_signing_convention(self):
        header = ppg.SIDECAR_HEADER
        assert "CLOSE-ONLY" in header
        assert "UNDER-state" in header
        assert "NOT a drawdown" in header
        assert "DIRECTION-SIGNING CONVENTION" in header
        assert "direction_sign * (name_ret_pct - bench_ret_pct)" in header
        assert "+7.0, NOT -7.0" in header

    def test_mfe_is_non_negative_and_mae_non_positive(self, store):
        for direction in ("BULL", "BEAR"):
            row = _graded(_plan(direction), store)
            assert row["mfe_close_pct"] >= 0
            assert row["mae_close_pct"] <= 0
            assert row["mfe_close_excess_vs_bench_pct"] >= 0
            assert row["mae_close_excess_vs_bench_pct"] <= 0

    def test_excursions_are_direction_signed_too(self, store):
        """Name falls monotonically: the LONG plan's worst close is −20 and its best is
        0; the SHORT plan's are mirrored."""
        long_row = _graded(_plan("BULL"), store)
        short_row = _graded(_plan("BEAR"), store)
        assert long_row["mae_close_pct"] == pytest.approx(-20.0, abs=1e-6)
        assert long_row["mfe_close_pct"] == pytest.approx(0.0, abs=1e-6)
        assert short_row["mfe_close_pct"] == pytest.approx(20.0, abs=1e-6)
        assert short_row["mae_close_pct"] == pytest.approx(0.0, abs=1e-6)


# --------------------------------------------------------------------------- #
# 6. the committed artifact
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(not SIDECAR.exists() or not LEDGER.exists(),
                    reason="prophet stores not materialised in this checkout")
class TestCommittedSidecar:
    @staticmethod
    def _rows():
        return ppg.read_jsonl(SIDECAR)

    def test_every_closed_plan_is_accounted_for(self):
        ledger_ids = {str(r["id"]) for r in ppg.read_jsonl(LEDGER) if r.get("id")}
        graded_ids = {str(r["id"]) for r in self._rows()}
        assert ledger_ids and ledger_ids <= graded_ids, sorted(ledger_ids - graded_ids)

    def test_no_row_mixes_a_basis(self):
        for row in self._rows():
            if row.get("price_basis") is None:
                assert row.get("refusal_reason"), row["id"]
                assert row.get("excess_vs_bench_pct") is None
                assert row.get("name_ret_pct") is None
            else:
                assert row["price_basis"] == "adjusted", row["id"]
                assert row.get("price_source"), row["id"]

    def test_signed_excess_reconstructs_from_the_raw_legs(self):
        for row in self._rows():
            if row.get("excess_vs_bench_pct") is None:
                continue
            expected = row["direction_sign"] * (row["name_ret_pct"] - row["bench_ret_pct"])
            assert row["excess_vs_bench_pct"] == pytest.approx(expected, abs=5e-4), row["id"]

    def test_the_file_leads_with_its_schema_header(self):
        head = SIDECAR.read_text(encoding="utf-8").splitlines()
        assert head[0].startswith("# prophet plan-grade SIDECAR")
        body = "\n".join(line for line in head if line.startswith("#"))
        for required in ("DIRECTION-SIGNING CONVENTION", "CLOSE-ONLY",
                         "ONE PRICE BASIS OR NO ROW", "NIGHTLY IS THE SOLE ADVANCER"):
            assert required in body

    def test_the_forward_record_carries_no_grade_columns(self):
        """The whole point of the sidecar: ledger.jsonl gained NOTHING."""
        for row in ppg.read_jsonl(LEDGER):
            for forbidden in ("bench_ret_pct", "excess_vs_bench_pct",
                              "sector_ret_pct", "mfe_close_pct", "price_basis"):
                assert forbidden not in row, f"{row.get('id')} grew {forbidden}"


def test_json_serialisable(store):
    """Every emitted row must survive json.dumps with allow_nan=False — a NaN here
    would write literal ``NaN`` and make the store unparseable by strict readers."""
    for direction in ("BULL", "BEAR"):
        for row in ppg.grade_plan(_plan(direction), data_dir=str(store), dead_prices={},
                                  sectors={"FALLER": "Financials"},
                                  graded_at="2026-01-20"):
            json.dumps(row, allow_nan=False)
