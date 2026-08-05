"""China Prophet loser + miss telemetry (W0) and CN ledger hygiene (W1).

Three things are pinned here, and they fail for different reasons on purpose:

1. **THE FROZEN REPRODUCTION.** The whole W0 engine exists to answer "which of our
   picks lost, and did they share a shape". If the arithmetic behind that answer moves,
   every conclusion drawn from it moves with it. Section 1 recomputes the legacy era
   from the COMMITTED board store and the COMMITTED price stores and pins the audited
   numbers as inline constants: 584 episodes, 407 matured, 68.55% win, 128 losers, and
   a 31-episode chase cohort splitting 22 losers / 9 winners.

   The input grid is PINNED to ``REPRO_ASOF`` — every price series is truncated there
   before scoring. Without that the pin is a time bomb: 176 legacy episodes are still
   in flight, and each night of fresh bars matures more of them, so ``n_matured`` would
   climb away from 407 within days and the test would go red for the one reason that is
   not a regression. With the grid pinned, the only things that can move these numbers
   are a change to the scorer, a change to the chase definition, or a dividend
   re-adjustment that pushes a marginal episode across zero. The first two are exactly
   what this test is for; the third is rare, visible in the diff, and the correct
   response is to re-freeze the constants against a fresh audit — never to widen the
   tolerance until the test stops meaning anything.

2. **THE WRITE GATES.** The audit writes to ``data/`` from the nightly. Section 2 pins
   that it refuses on a non-asia lane and on a mid-session partial panel — the same two
   gates ``china_standout_track.append_board`` enforces — and that its forward log is
   keep-FIRST, so a re-run can never rewrite a headline a reader already saw.

3. **THE AUTHORITY BOUNDARY.** The audit is ops-telemetry with zero authority. Section
   3 pins that the board's buy rows survive the call byte-identical AND that the call
   site hands it nothing but ``asof``/``lane`` — the structural reason it cannot touch
   them. A behavioural check alone would pass vacuously if someone later handed the
   rows in and the mutation were subtle; the source pin is what makes it real.

Section 4 covers the W1 ledger hygiene: the skip counter that used to pool a genuine
survivorship hole with an in-flight episode, and the rank/tier lookup that labelled
every episode of a repeat ticker with its most recent appearance.

Run: python3 -m pytest tests/test_cn_prophet_audit.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import cn_prophet_audit as cpa  # noqa: E402
from scripts import build_china_library as bcl  # noqa: E402

BOARD_PARQUET = ROOT / "data" / "china_standout_track" / "board.parquet"
CHINA_STOCKS = ROOT / "data" / "china_stocks"

# ── the frozen audit (2026-08-03 panel) ────────────────────────────────────────
REPRO_ASOF = "2026-08-03"
REPRO_ERA = "legacy"
REPRO_EPISODES = 584
REPRO_MATURED = 407
REPRO_WIN_RATE = 0.6855
REPRO_LOSERS = 128
REPRO_CHASE_FLAGGED = 31
REPRO_CHASE_LOSERS = 22
REPRO_CHASE_WINNERS = 9
RATE_TOL = 0.002


# ===========================================================================
# 1. frozen reproduction — real committed stores, pinned input grid
# ===========================================================================
@pytest.fixture(scope="module")
def legacy_block():
    """The legacy era's telemetry block, scored on the price panel as of REPRO_ASOF."""
    from engine import china_standout_track as cst

    cut = pd.Timestamp(REPRO_ASOF)
    board = pd.read_parquet(BOARD_PARQUET)

    bench_full = cst._bench_close()
    bench = None if bench_full is None else bench_full[bench_full.index <= cut]

    memo: dict[str, pd.DataFrame | None] = {}

    def price_of(tk: str):
        if tk not in memo:
            df = cst._price_frame(tk)
            memo[tk] = None if df is None else df[df.index <= cut]
        return memo[tk]

    out = cpa.loser_telemetry(board, bench, price_of, {})
    blocks = {b["board_definition"]: b for b in out["definitions"]}
    assert REPRO_ERA in blocks, f"legacy era missing from {list(blocks)}"
    return blocks[REPRO_ERA]


@pytest.mark.skipif(not BOARD_PARQUET.exists(), reason="CN board store not present")
@pytest.mark.skipif(not any(CHINA_STOCKS.glob("*.parquet")),
                    reason="china_stocks price store not present")
class TestFrozenReproduction:
    def test_the_input_grid_the_constants_were_frozen_on_is_still_present(self):
        """Guard the guard: an empty/短 price store would make section 1 vacuous."""
        assert len(list(CHINA_STOCKS.glob("*.parquet"))) > 1000
        board = pd.read_parquet(BOARD_PARQUET)
        legacy = board[board["board_definition"].map(cpa.norm_definition) == REPRO_ERA]
        assert len(legacy) == 1082, "the legacy era's board rows moved — re-audit"
        assert legacy["date"].nunique() == 18
        assert legacy["date"].max() < REPRO_ASOF, \
            "a legacy board row landed after the freeze date — re-audit"

    def test_episode_and_maturity_counts(self, legacy_block):
        assert legacy_block["n_episodes"] == REPRO_EPISODES
        assert legacy_block["n_matured"] == REPRO_MATURED

    def test_win_rate_and_loser_count(self, legacy_block):
        assert legacy_block["n_losers"] == REPRO_LOSERS
        assert legacy_block["n_winners"] == REPRO_MATURED - REPRO_LOSERS
        assert abs(legacy_block["win_rate"] - REPRO_WIN_RATE) <= RATE_TOL
        assert abs(legacy_block["loser_rate"] - (1.0 - REPRO_WIN_RATE)) <= RATE_TOL

    def test_chase_cohort_split(self, legacy_block):
        chase = legacy_block["chase"]
        assert chase["n_flagged"] == REPRO_CHASE_FLAGGED
        assert chase["chase_n_losers"] == REPRO_CHASE_LOSERS
        assert chase["chase_n_winners"] == REPRO_CHASE_WINNERS
        assert chase["chase_n"] == REPRO_CHASE_FLAGGED

    def test_the_chase_cohort_loses_far_more_often_than_the_rest(self, legacy_block):
        """The finding itself, not just its arithmetic.

        A refactor that silently made the composite fire on everything (or nothing)
        would keep n_flagged plausible while erasing the separation that is the whole
        point of measuring it.
        """
        chase = legacy_block["chase"]
        assert chase["chase_loser_rate"] > chase["clean_loser_rate"]
        assert chase["chase_n"] + chase["clean_n"] == legacy_block["n_matured"]

    def test_the_eras_are_never_pooled(self, legacy_block):
        from engine import china_standout_track as cst

        cut = pd.Timestamp(REPRO_ASOF)
        board = pd.read_parquet(BOARD_PARQUET)
        out = cpa.loser_telemetry(board, None, lambda _t: None, {})
        stamps = [b["board_definition"] for b in out["definitions"]]
        assert len(stamps) == len(set(stamps)) >= 2
        assert cst  # keeps the import meaningful for the reader
        assert cut  # ditto
        total = sum(b["n_board_rows"] for b in out["definitions"])
        assert total == len(board), "a board row landed in NO definition block"


class TestChaseFields:
    """The chase legs, isolated — the composite must be reachable by EACH leg alone."""

    @staticmethod
    def _frame(closes, highs=None):
        idx = pd.bdate_range("2026-05-01", periods=len(closes))
        highs = highs if highs is not None else [c * 1.02 for c in closes]
        return pd.DataFrame({"high": highs, "low": [c * 0.98 for c in closes],
                             "close": list(closes)}, index=idx)

    def test_a_quiet_name_is_not_a_chase(self):
        pdf = self._frame([100.0 + i * 0.05 for i in range(40)])
        closes = pdf["close"]
        f = cpa.chase_fields(pdf, closes, closes.index[30], "600000.SS", 100.0)
        assert f["chase_composite"] is False
        assert f["limit_band"] == cpa.LIMIT_STD

    def test_close_at_the_high_on_a_limit_move_fires(self):
        vals = [100.0] * 39 + [110.0]
        pdf = self._frame(vals, highs=[v * 1.02 for v in vals[:-1]] + [110.0])
        closes = pdf["close"]
        f = cpa.chase_fields(pdf, closes, closes.index[-1], "600000.SS", 110.0)
        assert f["day0_at_high"] is True and f["limit_move"] is True
        assert f["chase_composite"] is True

    def test_the_pin_alone_is_not_a_chase(self):
        """Closing at the high on a quiet day is noise — the legs are a conjunction."""
        vals = [100.0] * 39 + [100.5]
        pdf = self._frame(vals, highs=[v * 1.02 for v in vals[:-1]] + [100.5])
        closes = pdf["close"]
        f = cpa.chase_fields(pdf, closes, closes.index[-1], "600000.SS", 100.5)
        assert f["day0_at_high"] is True and f["limit_move"] is False
        assert f["chase_composite"] is False

    def test_an_overnight_gap_alone_fires(self):
        pdf = self._frame([100.0] * 40)
        closes = pdf["close"]
        f = cpa.chase_fields(pdf, closes, closes.index[-1], "600000.SS", 104.0)
        assert f["t1_gap"] == pytest.approx(0.04)
        assert f["chase_composite"] is True

    def test_a_trailing_run_alone_fires(self):
        pdf = self._frame([100.0 + i * 2.0 for i in range(40)])
        closes = pdf["close"]
        f = cpa.chase_fields(pdf, closes, closes.index[-1], "600000.SS", 178.0)
        assert f["trail_21"] > cpa.CHASE_TRAIL_21
        assert f["chase_composite"] is True

    def test_the_wide_limit_band_applies_to_chinext_and_star(self):
        assert cpa.limit_for("300750.SZ") == cpa.LIMIT_WIDE
        assert cpa.limit_for("688981.SS") == cpa.LIMIT_WIDE
        assert cpa.limit_for("600519.SS") == cpa.LIMIT_STD
        assert cpa.limit_for("000001.SZ") == cpa.LIMIT_STD

    def test_a_missing_leg_never_blocks_another_from_firing(self):
        """Short history → trail_21 is null; the gap leg must still be able to fire."""
        pdf = self._frame([100.0] * 5)
        closes = pdf["close"]
        f = cpa.chase_fields(pdf, closes, closes.index[-1], "600000.SS", 105.0)
        assert f["trail_21"] is None
        assert f["chase_composite"] is True


# ===========================================================================
# 2. write gates + forward log
# ===========================================================================
_DATES = pd.bdate_range("2026-06-01", periods=40)
_ASOF = str(_DATES[20].date())


def _ohlc(closes):
    return pd.DataFrame(
        {"open": list(closes), "high": [c * 1.01 for c in closes],
         "low": [c * 0.99 for c in closes], "close": list(closes)},
        index=_DATES[:len(closes)],
    )


@pytest.fixture()
def sandbox(monkeypatch, tmp_path):
    """A tmp data dir with a minimal board store and synthetic prices."""
    from engine import china_standout_track as cst
    from lib import config

    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    (tmp_path / "china_standout_track").mkdir(parents=True)
    pd.DataFrame([
        {"date": str(_DATES[0].date()), "ticker": "600000.SS", "board_rank": 1,
         "tier": "T1", "lane": "featured", "entry_status": "buy_now",
         "narr_level": "HOT", "board_definition": "cn_prophet_v2"},
        {"date": str(_DATES[1].date()), "ticker": "600000.SS", "board_rank": 2,
         "tier": "T1", "lane": "featured", "entry_status": "buy_now",
         "narr_level": "HOT", "board_definition": "cn_prophet_v2"},
    ]).to_parquet(tmp_path / "china_standout_track" / "board.parquet", index=False)

    frames = {"600000.SS": _ohlc([100.0 + i for i in range(40)])}
    monkeypatch.setattr(cst, "_price_frame", lambda tk: frames.get(str(tk)))
    monkeypatch.setattr(cst, "_bench_close",
                        lambda: pd.Series([3000.0 + i for i in range(40)], index=_DATES))
    return tmp_path


class TestWriteGates:
    def test_the_asia_lane_gate_refuses_a_render_lane_without_writing(self, sandbox):
        res = cpa.run(asof=_ASOF, lane="render")
        assert res["written"] is False
        assert "not asia" in res["reason"]
        assert not cpa.latest_path().exists()
        assert not cpa.forward_log_path().exists()

    def test_the_legacy_none_lane_still_writes(self, sandbox):
        """lane=None is the historical asia-build call convention — never break it."""
        res = cpa.run(asof=_ASOF, lane=None)
        assert res["written"] is True
        assert cpa.latest_path().exists()

    def test_a_partial_session_panel_refuses_without_writing(self, sandbox, monkeypatch):
        """Same refusal append_board makes, through the SAME session_status call.

        The stamp is fed to the real ``session_status`` rather than stubbing its
        answer, so the test can see a regression in the 07:00-UTC settle rule itself
        and not merely in the branch that reads its verdict.
        """
        from engine import china_standout_track as cst
        from lib import store

        monkeypatch.setattr(store, "read_status", lambda: {
            "sources": {"china_stocks": {"checked_at": f"{_ASOF}T03:00:00Z",
                                         "last_date": _ASOF}}})
        assert cst.session_status(_ASOF)["partial_session"] is True
        res = cpa.run(asof=_ASOF, lane="asia")
        assert res["written"] is False
        assert "partial" in res["reason"]
        assert not cpa.latest_path().exists()

    def test_a_settled_panel_writes_both_artifacts(self, sandbox):
        res = cpa.run(asof=_ASOF, lane="asia")
        assert res["written"] is True
        doc = json.loads(cpa.latest_path().read_text())
        assert doc["schema"] == cpa.SCHEMA
        assert doc["tier"] == "ops-telemetry"
        assert "none" in doc["authority"]
        assert isinstance(doc["elapsed_seconds"], (int, float))
        assert "coverage_start" in doc
        assert cpa.forward_log_path().exists()

    def test_the_artifact_is_strict_valid_json(self, sandbox):
        cpa.run(asof=_ASOF, lane="asia")
        raw = cpa.latest_path().read_text()
        assert "NaN" not in raw and "Infinity" not in raw
        json.loads(raw)

    def test_the_run_never_raises_on_a_broken_store(self, sandbox, monkeypatch):
        from engine import china_standout_track as cst

        monkeypatch.setattr(cst, "_bench_close",
                            lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        res = cpa.run(asof=_ASOF, lane="asia")
        assert res["written"] is False
        assert "boom" in res["reason"]


class TestForwardLog:
    def test_keep_first_never_rewrites_a_published_headline(self, sandbox):
        cpa.append_forward_log([{"date": _ASOF, "board_definition": "cn_prophet_v2",
                                 "n_matured": 5, "win_rate": 0.6}])
        n = cpa.append_forward_log([{"date": _ASOF, "board_definition": "cn_prophet_v2",
                                     "n_matured": 99, "win_rate": 0.99}])
        df = pd.read_parquet(cpa.forward_log_path())
        assert n == len(df) == 1
        assert int(df.iloc[0]["n_matured"]) == 5, "a re-run rewrote a published number"

    def test_a_second_date_appends_rather_than_replaces(self, sandbox):
        cpa.append_forward_log([{"date": _ASOF, "board_definition": "cn_prophet_v2",
                                 "n_matured": 5}])
        cpa.append_forward_log([{"date": "2026-06-30", "board_definition": "cn_prophet_v2",
                                 "n_matured": 7}])
        df = pd.read_parquet(cpa.forward_log_path())
        assert len(df) == 2
        assert set(df["date"]) == {_ASOF, "2026-06-30"}

    def test_definitions_get_their_own_rows_on_the_same_date(self, sandbox):
        cpa.append_forward_log([
            {"date": _ASOF, "board_definition": "legacy", "n_matured": 407},
            {"date": _ASOF, "board_definition": "cn_prophet_v2", "n_matured": 0},
        ])
        df = pd.read_parquet(cpa.forward_log_path())
        assert len(df) == 2
        assert set(df["board_definition"]) == {"legacy", "cn_prophet_v2"}

    def test_a_write_failure_is_swallowed_not_raised(self, sandbox, monkeypatch):
        monkeypatch.setattr(cpa, "forward_log_path",
                            lambda: Path("/nonexistent-root/forward_log.parquet"))
        assert cpa.append_forward_log([{"date": _ASOF, "board_definition": "x"}]) == 0


# ===========================================================================
# 3. authority boundary — the buy rows are not the audit's business
# ===========================================================================
class TestZeroAuthority:
    def test_the_buy_rows_survive_the_call_byte_identical(self, sandbox):
        """The exact call-site sequence: append_board, then the audit."""
        from engine import china_standout_track as cst

        buy_rows = [
            {"ticker": "600000.SS", "price": 101.0, "setup": "reversal",
             "signal": {"tier_cascade": "T1"}, "prophet": {"score": 88.0}},
            {"ticker": "300750.SZ", "price": 55.5, "setup": "washout",
             "signal": {"tier_cascade": "T2"}, "prophet": {"score": 71.0}},
            {"ticker": "688981.SS", "price": 12.25, "setup": "coiled",
             "signal": {"tier_cascade": "T3"}, "prophet": {"score": 60.0}},
        ]
        before_json = json.dumps(buy_rows, sort_keys=True)
        before_order = [r["ticker"] for r in buy_rows]
        before_ids = [id(r) for r in buy_rows]

        cst.append_board(buy_rows, asof=_ASOF, lane="asia")
        cpa.run(asof=_ASOF, lane="asia")

        assert [r["ticker"] for r in buy_rows] == before_order
        assert json.dumps(buy_rows, sort_keys=True) == before_json
        assert [id(r) for r in buy_rows] == before_ids

    def test_the_call_site_hands_the_audit_nothing_but_asof_and_lane(self):
        """Structural half of the invariant — it cannot mutate what it never receives.

        The behavioural check above passes vacuously the moment someone starts handing
        the board rows in and mutates them somewhere subtler than the ticker order.
        This pins the call shape itself.
        """
        src = (ROOT / "scripts" / "build_china_library.py").read_text()
        assert "_cn_audit.run(asof=as_of, lane=_lane)" in src, \
            "the cn_prophet_audit call site changed shape — re-read the authority note"

    def test_the_audit_writes_nowhere_but_its_own_store(self, sandbox):
        before = {p.relative_to(sandbox) for p in sandbox.rglob("*") if p.is_file()}
        cpa.run(asof=_ASOF, lane="asia")
        after = {p.relative_to(sandbox) for p in sandbox.rglob("*") if p.is_file()}
        new = {str(p) for p in (after - before)}
        assert new, "the audit wrote nothing at all"
        assert all(p.startswith(cpa.STORE_DIR) for p in new), \
            f"the audit wrote outside its own store: {sorted(new)}"


# ===========================================================================
# 4. W1 ledger hygiene
# ===========================================================================
_L_DATES = pd.bdate_range("2026-06-01", periods=30)


def _ledger_frame(closes, n=None):
    idx = _L_DATES[:len(closes)] if n is None else _L_DATES[:n]
    return pd.DataFrame(
        {"open": list(closes), "high": [c * 1.01 for c in closes],
         "low": [c * 0.99 for c in closes], "close": list(closes)}, index=idx)


class _LedgerFixture:
    """Board history that reaches every skip path exactly once.

    AAA — full history, matures.
    BBB — no price frame at all → the ONLY genuine survivorship hole.
    CCC — a frame whose close column is all-NaN → the same hole, different shape.
    DDD — surfaces on the LAST board date, so no bar exists after it → awaiting T+1.
    """

    D0 = str(_L_DATES[0].date())
    LAST = str(_L_DATES[-1].date())

    @staticmethod
    def board() -> pd.DataFrame:
        return pd.DataFrame([
            {"date": _LedgerFixture.D0, "ticker": "AAA", "board_rank": 1, "tier": "T1"},
            {"date": _LedgerFixture.D0, "ticker": "BBB", "board_rank": 2, "tier": "T2"},
            {"date": _LedgerFixture.D0, "ticker": "CCC", "board_rank": 3, "tier": "T3"},
            {"date": _LedgerFixture.LAST, "ticker": "DDD", "board_rank": 1, "tier": "T1"},
        ])

    @staticmethod
    def price_frame(ticker: str):
        if ticker == "AAA":
            return _ledger_frame([100.0 + i for i in range(30)])
        if ticker == "CCC":
            return pd.DataFrame({"open": [np.nan] * 30, "high": [np.nan] * 30,
                                 "low": [np.nan] * 30, "close": [np.nan] * 30},
                                index=_L_DATES)
        if ticker == "DDD":
            return _ledger_frame([50.0 + i * 0.2 for i in range(30)])
        return None                                    # BBB — store miss

    @staticmethod
    def bench():
        return pd.Series([3000.0 + i for i in range(30)], index=_L_DATES)


@pytest.fixture()
def ledger_cst(monkeypatch):
    from engine import china_standout_track as cst

    monkeypatch.setattr(cst, "_price_frame", _LedgerFixture.price_frame)
    monkeypatch.setattr(cst, "_bench_close", _LedgerFixture.bench)
    return cst


class TestW11SkipSplit:
    def test_the_two_skip_paths_are_counted_separately(self, ledger_cst):
        rows, n_locked, scored, n_inflight, n_awaiting, n_no_price = bcl._cn_ledger_rows(
            _LedgerFixture.board(), _LedgerFixture.bench(), {}, ledger_cst)
        assert n_no_price == 2, "BBB (no frame) and CCC (empty closes) are store misses"
        assert n_awaiting == 1, "DDD has prices — its T+1 fill simply has not printed"
        assert {r["t"] for r in rows} == {"AAA"}
        assert n_locked == 0 and len(scored) == 1 and n_inflight == 0

    def test_an_empty_close_column_is_a_store_miss_not_an_awaiting_fill(self, ledger_cst):
        """CCC's frame can still synthesise an (H+L)/2 fill; the closes are the tell.

        Counting it before the fill probe is what keeps it out of the in-flight bucket.
        """
        board = _LedgerFixture.board()
        only_ccc = board[board["ticker"] == "CCC"]
        _r, _l, _s, _i, n_awaiting, n_no_price = bcl._cn_ledger_rows(
            only_ccc, _LedgerFixture.bench(), {}, ledger_cst)
        assert (n_no_price, n_awaiting) == (1, 0)

    def test_the_summary_alarm_now_counts_store_misses_only(self, ledger_cst):
        graded = bcl._cn_grade_era(_LedgerFixture.board(), _LedgerFixture.bench(),
                                   {}, ledger_cst)
        s = graded["summary"]
        assert s["n_skipped_no_price"] == 2, "the alarm must not include in-flight rows"
        assert s["n_skipped_awaiting_t1"] == 1
        assert s["n_skipped_total"] == 3
        assert graded["n_skipped"] == 3
        assert (graded["n_no_price"], graded["n_awaiting_t1"]) == (2, 1)

    def test_the_survivorship_block_carries_both_halves(self, ledger_cst, monkeypatch,
                                                       tmp_path):
        from lib import config

        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        store_dir = tmp_path / "china_standout_track"
        store_dir.mkdir(parents=True)
        _LedgerFixture.board().assign(board_definition="cn_prophet_v2") \
            .to_parquet(store_dir / "board.parquet", index=False)
        site = tmp_path / "site"
        (site / "factordata").mkdir(parents=True)

        assert bcl.emit_cn_track_ledger(site, None, [],
                                        board_definition="cn_prophet_v2",
                                        asof=_LedgerFixture.LAST) is True
        doc = json.loads((site / "factordata" / "cn_track_ledger.json").read_text())
        surv = doc["meta"]["survivorship"]
        assert surv["n_skipped_no_price"] == 2
        assert surv["n_skipped_awaiting_t1"] == 1
        assert surv["n_skipped_total"] == 3
        # the pre-existing key is still present and still an int — no consumer breaks.
        assert isinstance(surv["n_skipped_no_price"], int)


_W12_DATES = [str(d.date()) for d in _L_DATES[:5]]


class TestW12AdmissionRow:
    """rk/tr must come from the episode's OWN admission, not the ticker's last row."""

    DATES = _W12_DATES

    @staticmethod
    def _board() -> pd.DataFrame:
        """RPT is admitted at rank 1 / T1, leaves, and returns at rank 40 / T4.

        Day 2 is a REAL board day that RPT is absent from (OTH holds it open) — a date
        merely missing from the frame would not break the run, since build_episodes
        walks the board days it is given, not the calendar. That absence is what makes
        these two episodes rather than one, and what makes last-row-wins visibly wrong:
        under it BOTH episodes are labelled with the rank the name carried on its
        RETURN, including the one that opened and closed before the return happened.
        """
        d = TestW12AdmissionRow.DATES
        return pd.DataFrame([
            {"date": d[0], "ticker": "RPT", "board_rank": 1, "tier": "T1"},
            {"date": d[1], "ticker": "RPT", "board_rank": 1, "tier": "T1"},
            {"date": d[1], "ticker": "OTH", "board_rank": 9, "tier": "T2"},
            {"date": d[2], "ticker": "OTH", "board_rank": 9, "tier": "T2"},
            {"date": d[3], "ticker": "RPT", "board_rank": 40, "tier": "T4"},
            {"date": d[4], "ticker": "RPT", "board_rank": 40, "tier": "T4"},
        ])

    @staticmethod
    def _price(ticker: str):
        if ticker in ("RPT", "OTH"):
            return _ledger_frame([100.0 + i for i in range(30)])
        return None

    @pytest.fixture()
    def rows(self, monkeypatch):
        from engine import china_standout_track as cst

        monkeypatch.setattr(cst, "_price_frame", self._price)
        out, *_ = bcl._cn_ledger_rows(self._board(), _LedgerFixture.bench(), {}, cst)
        return {(r["t"], r["d"]): r for r in out}

    def test_the_fixture_actually_distinguishes_the_two_readings(self):
        """Without this the pin could pass on a frame where both readings agree."""
        b = self._board()
        last_wins = b[b["ticker"] == "RPT"].iloc[-1]
        admission = b[b["ticker"] == "RPT"].iloc[0]
        assert last_wins["board_rank"] != admission["board_rank"]
        assert last_wins["tier"] != admission["tier"]

    def test_two_episodes_are_built_for_the_repeat_ticker(self, rows):
        rpt = [k for k in rows if k[0] == "RPT"]
        assert len(rpt) == 2, "the gap must open a second episode"

    def test_the_first_episode_keeps_its_own_admission_rank_and_tier(self, rows):
        first = rows[("RPT", self.DATES[0])]
        assert first["rk"] == 1, "last-row-wins would have written 40 here"
        assert first["tr"] == "T1", "last-row-wins would have written T4 here"

    def test_the_second_episode_carries_the_rank_it_was_readmitted_at(self, rows):
        second = rows[("RPT", self.DATES[3])]
        assert second["rk"] == 40
        assert second["tr"] == "T4"

    def test_an_unrelated_ticker_is_unaffected(self, rows):
        assert rows[("OTH", self.DATES[1])]["rk"] == 9
        assert rows[("OTH", self.DATES[1])]["tr"] == "T2"


# ===========================================================================
# 5. miss funnel — PIT only, never backfilled
# ===========================================================================
class TestMissFunnel:
    def test_it_degrades_to_a_disclosed_null_without_a_candidate_store(
            self, monkeypatch, tmp_path):
        from lib import config

        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        out = cpa.miss_funnel()
        assert out["available"] is False
        assert out["coverage_start"] is None
        assert "absent" in out["note"]

    def test_coverage_starts_at_the_candidate_store_birth_and_is_never_backfilled(
            self, monkeypatch, tmp_path):
        from lib import config

        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        idx = pd.bdate_range("2025-01-01", periods=300)
        stocks = tmp_path / "china_stocks"
        stocks.mkdir(parents=True)
        for tk, slope in (("600000.SS", 1.0), ("300750.SZ", 0.1)):
            pd.DataFrame({"close": [100.0 + i * slope for i in range(300)]},
                         index=idx).to_parquet(stocks / f"{tk}.parquet")
        cand = tmp_path / "china_prophet_rank"
        cand.mkdir(parents=True)
        birth = str(idx[-1].date())
        pd.DataFrame([{"stamp_date": birth, "ticker": "600000.SS", "lane": "featured"}]) \
            .to_parquet(cand / "candidates.parquet", index=False)

        out = cpa.miss_funnel()
        assert out["available"] is True
        assert out["coverage_start"] == birth
        assert out["coverage_dates"] == [birth]
        day = out["by_date"][0]
        assert day["lanes"]["featured"] == 1
        # 300750.SZ was never scored that day → 'absent', never silently dropped.
        assert day["lanes"][cpa.FUNNEL_ABSENT] == 1
        assert sum(day["lanes"].values()) == day["n_runners"] == 2
        assert {m["ticker"] for m in day["top_missed"]} == {"300750.SZ"}

    def test_a_name_that_did_not_print_that_session_is_not_a_runner(
            self, monkeypatch, tmp_path):
        """A halted/delisted name's stale last close must never enter the ranking."""
        from lib import config

        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        idx = pd.bdate_range("2025-01-01", periods=300)
        stocks = tmp_path / "china_stocks"
        stocks.mkdir(parents=True)
        pd.DataFrame({"close": [100.0 + i for i in range(300)]},
                     index=idx).to_parquet(stocks / "600000.SS.parquet")
        # halted: its history stops 5 sessions before the session under test
        pd.DataFrame({"close": [100.0 + i * 5 for i in range(295)]},
                     index=idx[:295]).to_parquet(stocks / "600001.SS.parquet")
        cand = tmp_path / "china_prophet_rank"
        cand.mkdir(parents=True)
        pd.DataFrame([{"stamp_date": str(idx[-1].date()), "ticker": "600000.SS",
                       "lane": "featured"}]).to_parquet(
            cand / "candidates.parquet", index=False)

        day = cpa.miss_funnel()["by_date"][0]
        assert day["n_runners"] == 1

    def test_short_history_names_are_excluded_and_the_count_is_printed(
            self, monkeypatch, tmp_path):
        from lib import config

        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        stocks = tmp_path / "china_stocks"
        stocks.mkdir(parents=True)
        short_idx = pd.bdate_range("2026-01-01", periods=50)
        pd.DataFrame({"close": [10.0 + i for i in range(50)]},
                     index=short_idx).to_parquet(stocks / "301000.SZ.parquet")
        cand = tmp_path / "china_prophet_rank"
        cand.mkdir(parents=True)
        pd.DataFrame([{"stamp_date": str(short_idx[-1].date()), "ticker": "301000.SZ",
                       "lane": "forming"}]).to_parquet(
            cand / "candidates.parquet", index=False)

        out = cpa.miss_funnel()
        assert out["universe"]["n_short_history"] == 1
        assert out["universe"]["n_scanned"] == 0
        assert out["universe"]["min_bars"] == cpa.RUNNER_MIN_BARS


# ===========================================================================
# 6. definition normalisation
# ===========================================================================
class TestDefinitionNormalisation:
    def test_every_pre_version_spelling_is_the_legacy_era(self):
        for value in (None, float("nan"), "", "  ", "legacy", "None", "<NA>", "NaT"):
            assert cpa.norm_definition(value) == "legacy", value

    def test_a_real_stamp_is_left_alone(self):
        assert cpa.norm_definition("cn_prophet_v2") == "cn_prophet_v2"
        assert cpa.norm_definition("cn_reversal_watch_v1") == "cn_reversal_watch_v1"

    def test_a_null_stamp_does_not_open_a_phantom_definition_block(self):
        board = pd.DataFrame([
            {"date": "2026-06-01", "ticker": "AAA", "board_definition": None},
            {"date": "2026-06-01", "ticker": "BBB", "board_definition": "legacy"},
            {"date": "2026-06-02", "ticker": "CCC", "board_definition": "cn_prophet_v2"},
        ])
        out = cpa.loser_telemetry(board, None, lambda _t: None, {})
        stamps = {b["board_definition"] for b in out["definitions"]}
        assert stamps == {"legacy", "cn_prophet_v2"}
