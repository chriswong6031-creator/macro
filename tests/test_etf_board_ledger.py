"""ETF consensus board forward ledger — engine/etf_board_ledger.py (masterplan §3 W3).

The four properties that make this ledger trustworthy, each pinned by a test that
fails if the property is removed:

  1. LANE GATE — an off-lane run writes NOTHING and creates NO file. Nightly is the
     sole advancer of forward ledgers; a render or an intraday lane that could append
     would duplicate rows into an append-only store, which is unrecoverable.
  2. IDEMPOTENCE — a second run on the same board date appends zero rows and leaves
     the file byte-identical. The nightly step sits behind `set +e` and may be re-run.
  3. FREEZE — re-grading never rewrites the price-derived columns of a row that is
     already graded, even when the underlying price series has moved.
  4. SCHEMA TOLERANCE — a consensus row that lacks the newest engine fields still
     serializes, and heavy nested fields never reach the fire log.

Everything here runs against fixtures in tmp_path; no test touches data/ or site/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from engine import etf_board_ledger as ebl  # noqa: E402


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def _row(ticker: str = "NVDA", **over) -> dict:
    """A consensus_favored-shaped row, W1 fields included."""
    row = {
        "ticker": ticker,
        "name": "Nvidia Corp",
        "sector": "Information Technology",
        "n_accum": 4, "n_trim": 1, "n_new": 1, "n_exit": 0,
        "net_conviction_pp": 1.8412, "gross_conviction_pp": 2.9,
        "direction": "accumulating", "contested": True,
        "total_usd": 41_200_000.0, "flow_usd": 30_100_000.0,
        "selection_usd": 11_100_000.0,
        "net_flow_pp": 1.1, "net_selection_pp": 0.74,
        "n_funds_any": 5, "n_funds_flow": 3, "n_funds_selection": 2,
        "n_funds_usd": 5, "usd_complete": True, "breadth": 3, "max_streak": 4,
        "accel_pct_per_day": 0.31, "contested_components": False,
        "is_active_any": True,
        "ladder": {"state": "RALLY ON", "urgency": "soon", "score": 61.2},
        "funds": [
            {"fund": "SMH", "conviction_pp": 0.9, "driver": "flow",
             "total_usd": 20_000_000.0, "streak": 3},
            {"fund": "AIQ", "conviction_pp": 0.5, "driver": "selection",
             "total_usd": 9_000_000.0, "streak": 1},
        ],
    }
    row.update(over)
    return row


@pytest.fixture
def off_lane(monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)


@pytest.fixture
def on_lane(monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    monkeypatch.delenv("US_LANE", raising=False)


# --------------------------------------------------------------------------- #
# 1. lane gate
# --------------------------------------------------------------------------- #
class TestLaneGate:
    def test_off_lane_append_writes_nothing(self, tmp_path, off_lane):
        n = ebl.append_snapshot([_row()], "2026-08-12", base_dir=tmp_path)
        assert n == 0, "off-lane append must refuse"
        assert not ebl.snapshots_path(tmp_path).exists(), (
            "off-lane append must not create the fire log — an empty file is still a write"
        )
        assert not ebl.ledger_dir(tmp_path).exists(), (
            "off-lane append must not even create the ledger directory"
        )

    def test_render_lane_sentinel_is_off_lane(self, tmp_path, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "render")
        assert ebl.lane_open() is False
        assert ebl.append_snapshot([_row()], "2026-08-12", base_dir=tmp_path) == 0
        assert not ebl.snapshots_path(tmp_path).exists()

    def test_on_lane_append_writes(self, tmp_path, on_lane):
        n = ebl.append_snapshot([_row("NVDA"), _row("TSM")], "2026-08-12",
                                base_dir=tmp_path)
        assert n == 2
        assert ebl.snapshots_path(tmp_path).exists()

    def test_off_lane_merge_does_not_create_the_parquet(self, tmp_path, off_lane):
        fresh = pd.DataFrame([{"as_of": "2026-08-12", "ticker": "NVDA", "horizon": 5,
                               "ret": 0.02, "excess_bench": 0.01}])
        out = ebl.merge_grades(fresh, base_dir=tmp_path)
        assert not ebl.retro_path(tmp_path).exists(), (
            "off-lane merge must not create retro_grades.parquet"
        )
        assert len(out) == 1, "the in-memory projection is still returned for display"

    def test_lane_gate_fails_closed_when_the_gate_is_unimportable(self, monkeypatch):
        """A broken import must read as SHUT, never as open."""
        import builtins
        real_import = builtins.__import__

        def boom(name, *a, **k):
            if name == "engine.ledger_lane":
                raise ImportError("simulated")
            return real_import(name, *a, **k)

        monkeypatch.setenv("COLLECT_LANE", "nightly")
        monkeypatch.setattr(builtins, "__import__", boom)
        assert ebl.lane_open() is False


# --------------------------------------------------------------------------- #
# 2. idempotence — same-day re-run is a no-op, byte for byte
# --------------------------------------------------------------------------- #
class TestIdempotence:
    def test_second_same_day_run_appends_zero_rows_and_is_byte_stable(
            self, tmp_path, on_lane):
        rows = [_row("NVDA"), _row("TSM"), _row("AVGO")]
        assert ebl.append_snapshot(rows, "2026-08-12", base_dir=tmp_path) == 3
        before = ebl.snapshots_path(tmp_path).read_bytes()

        assert ebl.append_snapshot(rows, "2026-08-12", base_dir=tmp_path) == 0
        assert ebl.snapshots_path(tmp_path).read_bytes() == before, (
            "a same-day re-run must leave the append-only log byte-identical"
        )

    def test_keep_first_survives_a_changed_row(self, tmp_path, on_lane):
        """The fire log is point-in-time: a later recompute never rewrites the record."""
        ebl.append_snapshot([_row("NVDA", net_conviction_pp=1.0)], "2026-08-12",
                            base_dir=tmp_path)
        ebl.append_snapshot([_row("NVDA", net_conviction_pp=9.9)], "2026-08-12",
                            base_dir=tmp_path)
        recs = ebl.load_snapshots(tmp_path)
        assert len(recs) == 1
        assert recs[0]["net_conviction_pp"] == 1.0, "keep-FIRST was violated"

    def test_a_new_board_date_appends_beside_the_old_one(self, tmp_path, on_lane):
        ebl.append_snapshot([_row("NVDA")], "2026-08-12", base_dir=tmp_path)
        assert ebl.append_snapshot([_row("NVDA")], "2026-08-13", base_dir=tmp_path) == 1
        recs = ebl.load_snapshots(tmp_path)
        assert sorted(r["as_of"] for r in recs) == ["2026-08-12", "2026-08-13"]

    def test_top_n_caps_the_nightly_append(self, tmp_path, on_lane):
        rows = [_row(f"T{i}") for i in range(40)]
        assert ebl.append_snapshot(rows, "2026-08-12", base_dir=tmp_path, top_n=5) == 5
        recs = ebl.load_snapshots(tmp_path)
        assert [r["rank"] for r in recs] == [1, 2, 3, 4, 5]


# --------------------------------------------------------------------------- #
# 3. schema tolerance — the sibling waves keep adding fields
# --------------------------------------------------------------------------- #
class TestSchemaTolerance:
    def test_row_without_the_new_dollar_fields_still_serializes(self, tmp_path, on_lane):
        """A pre-W1 row (no flow/selection dollars at all) must still be logged."""
        legacy = {"ticker": "URA", "n_accum": 3, "n_trim": 0,
                  "net_conviction_pp": 0.72, "direction": "accumulating"}
        assert ebl.append_snapshot([legacy], "2026-08-12", base_dir=tmp_path) == 1
        rec = ebl.load_snapshots(tmp_path)[0]
        assert rec["ticker"] == "URA"
        assert rec["net_conviction_pp"] == 0.72
        assert "flow_usd" not in rec, "an absent field must stay absent, not become 0"

    def test_a_field_nobody_has_named_yet_is_persisted_automatically(self, tmp_path, on_lane):
        ebl.append_snapshot([_row("NVDA", some_future_field=7.5)], "2026-08-12",
                            base_dir=tmp_path)
        rec = ebl.load_snapshots(tmp_path)[0]
        assert rec["some_future_field"] == 7.5, (
            "serialization must iterate the row, not a hard-coded column list — "
            "a field a sibling wave adds must start accruing the night it ships"
        )

    def test_heavy_nested_fields_are_dropped(self, tmp_path, on_lane):
        row = _row("NVDA")
        row["trajectory"] = [{"date": f"2026-07-{d:02d}", "w": 1.0} for d in range(1, 29)]
        row["weight_trajectory"] = list(range(500))
        ebl.append_snapshot([row], "2026-08-12", base_dir=tmp_path)
        rec = ebl.load_snapshots(tmp_path)[0]
        assert "trajectory" not in rec and "weight_trajectory" not in rec, (
            "sparkline series must never enter the fire log — it is committed nightly "
            "for years and has to stay small"
        )
        assert rec["ladder"]["state"] == "RALLY ON", "small nested context is kept"
        assert len(rec["funds"]) == 2, "per-fund evidence is kept (capped)"

    def test_per_fund_detail_is_capped(self, tmp_path, on_lane):
        row = _row("NVDA")
        row["funds"] = [{"fund": f"F{i}", "conviction_pp": 0.1} for i in range(50)]
        ebl.append_snapshot([row], "2026-08-12", base_dir=tmp_path)
        rec = ebl.load_snapshots(tmp_path)[0]
        assert len(rec["funds"]) == ebl._MAX_FUNDS

    def test_a_row_without_a_ticker_is_skipped_not_fatal(self, tmp_path, on_lane):
        assert ebl.append_snapshot([{"n_accum": 2}, _row("NVDA")], "2026-08-12",
                                   base_dir=tmp_path) == 1

    def test_nan_never_ships_as_a_value(self, tmp_path, on_lane):
        ebl.append_snapshot([_row("NVDA", net_conviction_pp=float("nan"))],
                            "2026-08-12", base_dir=tmp_path)
        raw = ebl.snapshots_path(tmp_path).read_text()
        assert "NaN" not in raw, "NaN is not JSON and reads as a value downstream"
        assert json.loads(raw.splitlines()[0])["net_conviction_pp"] is None


# --------------------------------------------------------------------------- #
# 4. grading
# --------------------------------------------------------------------------- #
def _panel(dates: int = 90, start: str = "2026-05-01") -> pd.DataFrame:
    """A deterministic close panel: NVDA compounds +1%/bar, SPY +0.5%/bar."""
    idx = pd.bdate_range(start, periods=dates)
    nvda = [100.0 * (1.01 ** i) for i in range(dates)]
    spy = [400.0 * (1.005 ** i) for i in range(dates)]
    flat = [50.0] * dates
    return pd.DataFrame({"NVDA": nvda, "SPY": spy, "TSM": flat}, index=idx)


class TestGrading:
    def test_next_bar_fill_and_excess_vs_bench(self):
        panel = _panel()
        as_of = str(panel.index[10].date())
        recs = [{"as_of": as_of, "ticker": "NVDA", "rank": 1, "n_accum": 3,
                 "net_conviction_pp": 1.0}]
        df = ebl.grade_snapshots(recs, panel=panel, price_source={"NVDA": "yahoo",
                                                                 "SPY": "yahoo"})
        h5 = df[df["horizon"] == 5].iloc[0]
        # entry is the bar STRICTLY AFTER the board date (next-bar fill)
        assert h5["entry_date"] == str(panel.index[11].date())
        assert h5["ret"] == pytest.approx(1.01 ** 5 - 1, rel=1e-9)
        assert h5["bench_ret"] == pytest.approx(1.005 ** 5 - 1, rel=1e-9)
        assert h5["excess_bench"] == pytest.approx(
            (1.01 ** 5 - 1) - (1.005 ** 5 - 1), abs=1e-6)
        assert h5["price_source"] == "yahoo"

    def test_unmatured_horizon_is_pending_not_zero(self):
        panel = _panel()
        as_of = str(panel.index[-3].date())          # only 2 forward bars exist
        df = ebl.grade_snapshots([{"as_of": as_of, "ticker": "NVDA", "rank": 1}],
                                 panel=panel, price_source={})
        assert df["ret"].isna().all(), (
            "an unmatured window must stay null — a 0 would read as 'flat', which is "
            "a measurement nobody made"
        )
        assert set(df["horizon"]) == set(ebl.HORIZONS)

    def test_a_name_with_no_price_keeps_its_rows_ungraded(self):
        panel = _panel()
        as_of = str(panel.index[10].date())
        df = ebl.grade_snapshots([{"as_of": as_of, "ticker": "GHOST", "rank": 1}],
                                 panel=panel, price_source={})
        assert len(df) == len(ebl.HORIZONS), (
            "a board name with no price series must remain in the ledger as an "
            "ungraded row — dropping it is survivorship"
        )
        assert df["ret"].isna().all()
        assert df["price_source"].isna().all()

    def test_empty_records_grade_to_an_empty_frame(self):
        assert ebl.grade_snapshots([]).empty


# --------------------------------------------------------------------------- #
# 5. freeze — a graded row is a published claim
# --------------------------------------------------------------------------- #
class TestFreeze:
    def test_regrade_does_not_rewrite_a_frozen_price(self, tmp_path, on_lane):
        panel = _panel()
        as_of = str(panel.index[10].date())
        recs = [{"as_of": as_of, "ticker": "NVDA", "rank": 1}]

        first = ebl.grade_snapshots(recs, panel=panel, price_source={"NVDA": "yahoo"})
        stored = ebl.merge_grades(first, base_dir=tmp_path)
        published = float(stored[stored["horizon"] == 5].iloc[0]["ret"])

        # the ladder re-bases underneath us: every close now reads 3% higher
        moved = panel * 1.03
        moved["TSM"] = panel["TSM"]
        second = ebl.grade_snapshots(recs, panel=moved, price_source={"NVDA": "yahoo"})
        assert float(second[second["horizon"] == 5].iloc[0]["ret"]) == pytest.approx(
            published, rel=1e-9), "sanity: a proportional re-base leaves the ratio alone"

        # ...and a ladder change that DOES move the number must not restate the row.
        # index[16] is the h5 exit bar for a board dated index[10] (next-bar fill at
        # index[11], five forward bars), so moving it moves the published return.
        bumped = panel.copy()
        bumped.loc[bumped.index[16], "NVDA"] = 999.0
        third = ebl.grade_snapshots(recs, panel=bumped, price_source={"NVDA": "yahoo"})
        assert float(third[third["horizon"] == 5].iloc[0]["ret"]) != pytest.approx(
            published, rel=1e-6), "fixture check: the re-grade really did move"

        merged = ebl.merge_grades(third, base_dir=tmp_path)
        assert float(merged[merged["horizon"] == 5].iloc[0]["ret"]) == pytest.approx(
            published, rel=1e-12), (
            "a row that was already graded is a point-in-time claim — the merge must "
            "restore the stored price columns, never restate the published number"
        )

    def test_an_open_row_still_takes_the_fresh_grade(self, tmp_path, on_lane):
        """Freezing must not freeze a row that has not matured — that is the whole
        point of running the grader every night."""
        panel = _panel()
        as_of = str(panel.index[-3].date())
        recs = [{"as_of": as_of, "ticker": "NVDA", "rank": 1}]
        ebl.merge_grades(ebl.grade_snapshots(recs, panel=panel, price_source={}),
                         base_dir=tmp_path)

        longer = _panel(dates=120)
        merged = ebl.merge_grades(
            ebl.grade_snapshots(recs, panel=longer, price_source={}), base_dir=tmp_path)
        h5 = merged[merged["horizon"] == 5].iloc[0]
        assert pd.notna(h5["ret"]), "a matured window must fill in on the next run"

    def test_a_bench_leg_that_was_null_can_still_fill_in(self, tmp_path, on_lane):
        """m11. The two legs mature independently. A row that graded on the NAME
        while the benchmark window was unresolvable used to have the bench leg's
        nulls frozen in on the strength of the name's `ret` — so it sat graded and
        permanently uncomparable, quietly shrinking the "x of y ahead of SPY"
        denominator with nothing on the surface saying why."""
        panel = _panel()
        as_of = str(panel.index[10].date())
        recs = [{"as_of": as_of, "ticker": "NVDA", "rank": 1}]

        # night 1: the name grades, the benchmark leg does not resolve
        blind = panel.drop(columns=[ebl.BENCH])
        first = ebl.grade_snapshots(recs, panel=blind, price_source={"NVDA": "yahoo"})
        stored = ebl.merge_grades(first, base_dir=tmp_path)
        h5 = stored[stored["horizon"] == 5].iloc[0]
        published = float(h5["ret"])
        assert pd.notna(h5["ret"]) and pd.isna(h5["bench_ret"]), "fixture check"

        # night 2: SPY is back in the panel
        second = ebl.grade_snapshots(recs, panel=panel,
                                     price_source={"NVDA": "yahoo", ebl.BENCH: "yahoo"})
        merged = ebl.merge_grades(second, base_dir=tmp_path)
        row = merged[merged["horizon"] == 5].iloc[0]
        assert pd.notna(row["bench_ret"]), (
            "the benchmark leg must be allowed to fill in — it was never published"
        )
        assert float(row["ret"]) == pytest.approx(published, rel=1e-12), (
            "…while the NAME's published return stays frozen"
        )
        # abs, not rel: `excess_bench` is stored rounded to 6dp by design
        assert float(row["excess_bench"]) == pytest.approx(
            published - float(row["bench_ret"]), abs=1e-6), (
            "the printed difference must equal the two numbers printed beside it"
        )

    def test_a_published_bench_leg_is_still_frozen(self, tmp_path, on_lane):
        """The other half of m11: once BOTH legs are published the row is a claim
        and a moved ladder must not restate either of them."""
        panel = _panel()
        as_of = str(panel.index[10].date())
        recs = [{"as_of": as_of, "ticker": "NVDA", "rank": 1}]
        stored = ebl.merge_grades(
            ebl.grade_snapshots(recs, panel=panel, price_source={}), base_dir=tmp_path)
        h5 = stored[stored["horizon"] == 5].iloc[0]
        pub_ret, pub_bench = float(h5["ret"]), float(h5["bench_ret"])
        assert pd.notna(pub_bench), "fixture check: the bench leg did publish"

        bumped = panel.copy()
        bumped.loc[bumped.index[16], [ebl.BENCH, "NVDA"]] = 999.0
        merged = ebl.merge_grades(
            ebl.grade_snapshots(recs, panel=bumped, price_source={}), base_dir=tmp_path)
        row = merged[merged["horizon"] == 5].iloc[0]
        assert float(row["ret"]) == pytest.approx(pub_ret, rel=1e-12)
        assert float(row["bench_ret"]) == pytest.approx(pub_bench, rel=1e-12)
        assert float(row["excess_bench"]) == pytest.approx(pub_ret - pub_bench, abs=1e-6)

    def test_merge_returns_the_full_store_when_nothing_matures(self, tmp_path, on_lane):
        panel = _panel()
        as_of = str(panel.index[10].date())
        first = ebl.grade_snapshots([{"as_of": as_of, "ticker": "NVDA", "rank": 1}],
                                    panel=panel, price_source={})
        ebl.merge_grades(first, base_dir=tmp_path)
        out = ebl.merge_grades(pd.DataFrame(), base_dir=tmp_path)
        assert len(out) == len(first), (
            "an empty fresh frame must return the accumulated store, never an empty one "
            "— that is the empty:true regression the US board ledger already paid for"
        )


# --------------------------------------------------------------------------- #
# 6. display projection
# --------------------------------------------------------------------------- #
class TestTrackPayload:
    def test_zero_graded_rows_render_as_collecting(self):
        track = ebl.build_track([{"as_of": "2026-08-12", "ticker": "NVDA"}],
                                pd.DataFrame(), as_of="2026-08-12")
        assert track["collecting"] is True
        assert track["n_graded_total"] == 0
        for h in ebl.HORIZONS:
            blk = track["per_horizon"][f"h{h}"]
            assert blk["state"] == "collecting"
            assert blk["n_graded"] == 0
            assert blk["median_excess_bench"] is None, (
                "no window has closed — a number here would be an invention"
            )

    def test_graded_rows_produce_plain_counts(self):
        panel = _panel()
        as_of = str(panel.index[10].date())
        recs = [{"as_of": as_of, "ticker": "NVDA", "rank": 1, "n_accum": 3},
                {"as_of": as_of, "ticker": "TSM", "rank": 2, "n_accum": 2}]
        df = ebl.grade_snapshots(recs, panel=panel, price_source={})
        track = ebl.build_track(recs, df, as_of=as_of)
        h5 = track["per_horizon"]["h5"]
        assert h5["state"] == "open"
        assert h5["n_graded"] == 2
        assert h5["n_vs_bench"] == 2
        assert h5["n_ahead"] == 1, "NVDA beats SPY, the flat name does not"
        assert track["collecting"] is False
        assert track["benchmark"] == "SPY"

    def test_pending_rows_split_into_immature_and_unpriceable(self):
        """m10. One `n_pending` conflated "the window has not closed" with "this
        name has no price series anywhere". The first resolves itself on a known
        date; the second never will — it is a delisting or an unresolvable ticker,
        i.e. exactly the survivorship this ledger is here to keep visible. Summed
        into one number, a growing pile of dead names reads as patience."""
        panel = _panel()
        young = str(panel.index[-3].date())      # 2 forward bars — immature
        old = str(panel.index[10].date())
        recs = [{"as_of": young, "ticker": "NVDA", "rank": 1},
                {"as_of": old, "ticker": "GHOST", "rank": 2}]   # no series at all
        df = ebl.grade_snapshots(recs, panel=panel, price_source={"NVDA": "yahoo"})
        blk = ebl.build_track(recs, df)["per_horizon"]["h5"]
        assert blk["n_graded"] == 0
        assert blk["n_pending"] == 2, "the published total is unchanged"
        assert blk["n_immature"] == 1, "NVDA's window simply has not closed"
        assert blk["n_unpriceable"] == 1, "GHOST has no price series and never will"
        assert blk["n_immature"] + blk["n_unpriceable"] == blk["n_pending"]

    def test_the_pending_split_is_zero_zero_when_nothing_is_pending(self):
        panel = _panel()
        as_of = str(panel.index[10].date())
        recs = [{"as_of": as_of, "ticker": "NVDA", "rank": 1}]
        df = ebl.grade_snapshots(recs, panel=panel, price_source={"NVDA": "yahoo"})
        blk = ebl.build_track(recs, df)["per_horizon"]["h5"]
        assert blk["n_pending"] == blk["n_immature"] == blk["n_unpriceable"] == 0
        # …and the keys exist on the empty block too, so a reader never KeyErrors
        empty = ebl.build_track([], pd.DataFrame())["per_horizon"]["h5"]
        assert empty["n_immature"] == 0 and empty["n_unpriceable"] == 0

    def test_ahead_count_is_denominated_on_the_benchmark_leg(self):
        """n_ahead / n_vs_bench must not silently borrow the absolute-return count."""
        panel = _panel()
        as_of = str(panel.index[10].date())
        df = ebl.grade_snapshots([{"as_of": as_of, "ticker": "NVDA", "rank": 1}],
                                 panel=panel, price_source={})
        df.loc[df["horizon"] == 5, "excess_bench"] = None
        blk = ebl.build_track([], df)["per_horizon"]["h5"]
        assert blk["n_graded"] == 1 and blk["n_vs_bench"] == 0
        assert blk["n_ahead"] is None

    def test_rows_are_capped_and_the_artifact_stays_small(self, tmp_path):
        panel = _panel()
        as_of = str(panel.index[10].date())
        recs = [{"as_of": as_of, "ticker": t, "rank": i, "n_accum": 2}
                for i, t in enumerate(["NVDA", "TSM"] * 60, start=1)]
        df = ebl.grade_snapshots(recs, panel=panel, price_source={})
        track = ebl.build_track(recs, df, as_of=as_of, rows_cap=10)
        assert len(track["rows"]) == 10
        p = ebl.write_track(track, tmp_path / "etf_board_track.json")
        assert p.stat().st_size < 100_000, "display artifact must stay under 100KB"
        assert json.loads(p.read_text())["schema"] == ebl.SCHEMA

    def test_write_track_is_not_lane_gated(self, tmp_path, off_lane):
        """The projection re-describes committed state; it can never advance it."""
        p = ebl.write_track(ebl.build_track([], pd.DataFrame()),
                            tmp_path / "t.json")
        assert p.exists()


# --------------------------------------------------------------------------- #
# 7. as-of is a DATA date
# --------------------------------------------------------------------------- #
class TestBoardAsOf:
    def test_asof_is_the_newest_snapshot_stem(self, tmp_path):
        root = tmp_path / "etf_holdings"
        for fund, dates in {"URA": ["2026-08-10", "2026-08-11"],
                            "SMH": ["2026-08-12"]}.items():
            (root / fund).mkdir(parents=True)
            for d in dates:
                (root / fund / f"{d}.parquet").write_bytes(b"")
        assert ebl.board_asof(roots=[root]) == "2026-08-12"

    def test_no_snapshots_anywhere_is_none_not_today(self, tmp_path):
        assert ebl.board_asof(roots=[tmp_path / "nope"]) is None, (
            "stamping a wall-clock date onto a store with no snapshot would log a "
            "board that was never published"
        )
