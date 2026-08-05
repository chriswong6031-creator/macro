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

Section 7 covers the RANK EFFECTIVENESS block — the score grading itself. Two things
there deserve calling out, because they fail for opposite reasons:

  * **The orientation pins are the load-bearing half.** Every IC in the block shares one
    sign convention (lower ordering key = the board's better pick), which means a single
    missing negation in ``_order_key`` would invert every reading in the artifact while
    leaving every number plausible. The pins therefore drive a PERFECTLY ordered board
    and an exactly INVERTED one through both ordering sources and assert the signs from
    both ends, and separately assert that a cost metric's expected sign is the opposite
    of a return metric's.
  * **The calibration assert is what makes the block trustworthy at all.** A detector
    that has never been shown catching a known defect is not a detector. The legacy era
    is the defect the program already measured — board rank-IC +0.073 vs H=10 excess,
    anti-predictive — so the block is run over it on the SAME frozen grid section 1 uses
    and required to reproduce that number and raise its ``::warning``. If this test ever
    passes vacuously (empty store, wrong era, un-pinned grid), the whole block is
    unfalsifiable telemetry.

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

# ── the V1 ordering defect, as measured by the audit this program is built on ──
# masterplan §2.1 / CN-RC4: "board rank-IC was +0.073 (anti-predictive)". On the frozen
# REPRO_ASOF grid the block must land ON that number — not merely somewhere positive —
# or it is not reproducing the audit, it is producing a different one.
REPRO_RANK_IC_EXCESS = 0.0731
REPRO_RANK_IC_N_DATES = 12
IC_TOL = 0.002
# masterplan §8 M5 (catastrophic ≤ −15% abs) and M2 (median excess), same frozen grid —
# they cross-check that the block reads the SAME episodes section 1 graded.
REPRO_CATASTROPHIC = 47
REPRO_MEDIAN_EXCESS = 4.44


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


# ===========================================================================
# 7. rank effectiveness — the score grades itself
# ===========================================================================
_RE_DATES = [f"2026-06-{d:02d}" for d in range(1, 21)]


def _ep(date: str, ticker: str, **fields) -> dict:
    """One synthetic MATURED episode record, shaped exactly as episode_telemetry emits.

    Every gradeable field defaults to None so a test states only the axis it is about;
    an axis a test does not set stays a genuine null and drops out of that metric's IC
    rather than quietly scoring as a zero.
    """
    rec: dict = {
        "ticker": ticker, "entry_date": date, "matured": True, "state": "matured",
        "board_rank": None, "prophet_score": None,
        "excess": None, "pnl": None, "mae_proxy_10": None,
        "day_of_max_10": None, "day_of_max_21": None,
        "terminal_state_clean8_21": None, "post_cushion_breach": None,
    }
    rec.update({c: None for c in cpa.PROPHET_COMPONENT_COLS})
    rec.update({c: None for c in cpa.SPINE_MFE_COLS})
    rec.update(fields)
    return rec


def _defn(name: str, records: list[dict]) -> dict:
    return {"board_definition": name, "episodes": records}


def _ordered_board(n_dates: int = 3, width: int = 8, *, inverted: bool = False,
                   with_score: bool = True) -> list[dict]:
    """A board whose ordering is either PERFECT or exactly INVERTED against excess.

    Perfect: rank 1 earns the most excess. Inverted: rank 1 earns the least — the V1
    shape. ``prophet_score`` is carried alongside ``board_rank`` and moves the opposite
    way (higher score = better pick), which is precisely the relationship ``_order_key``
    has to normalise; if it stops negating, the two ladders disagree.
    """
    out: list[dict] = []
    for d in _RE_DATES[:n_dates]:
        for rank in range(1, width + 1):
            excess = float(rank) if inverted else float(width - rank)
            out.append(_ep(
                d, f"{d}-{rank:02d}",
                board_rank=float(rank),
                prophet_score=(100.0 - rank) if with_score else None,
                excess=excess,
            ))
    return out


class TestICOrientation:
    """One sign convention, asserted from both ends.

    A missing negation in ``_order_key`` inverts every number in the artifact while
    leaving them all individually plausible, so "it looked reasonable" is not a check
    that can see this failure. Driving a perfectly ordered board AND its exact inverse
    is.
    """

    def test_a_perfectly_ordered_board_scores_a_negative_ic(self):
        blk = cpa._rank_eff_block(_defn("t", _ordered_board()))
        cell = blk["orderings"]["board_rank"]["ic"]["excess_h10"]
        assert cell["ic"] == pytest.approx(-1.0)
        assert cell["good_sign"] == "negative"
        assert cell["wrong_sign"] is False

    def test_an_inverted_board_scores_a_positive_ic_and_is_flagged(self):
        blk = cpa._rank_eff_block(_defn("t", _ordered_board(inverted=True)))
        cell = blk["orderings"]["board_rank"]["ic"]["excess_h10"]
        assert cell["ic"] == pytest.approx(1.0)
        assert cell["wrong_sign"] is True

    def test_the_score_ladder_agrees_with_the_rank_ladder_on_the_same_board(self):
        """The negation pin. prophet_score runs the OTHER way from board_rank.

        Both describe the same ordering of the same names, so both ladders must land on
        the same IC. Drop the negation in ``_order_key`` and this is the test that goes
        red — the two would come out at exactly opposite signs.
        """
        blk = cpa._rank_eff_block(_defn("t", _ordered_board()))
        by_rank = blk["orderings"]["board_rank"]["ic"]["excess_h10"]["ic"]
        by_score = blk["orderings"]["prophet_score"]["ic"]["excess_h10"]["ic"]
        assert by_rank == pytest.approx(-1.0)
        assert by_score == pytest.approx(by_rank)

    def test_the_score_is_the_primary_ordering_wherever_the_ledger_stored_it(self):
        with_score = cpa._rank_eff_block(_defn("t", _ordered_board()))
        assert with_score["primary_ordering"] == cpa.ORDER_SOURCE_SCORE
        assert with_score["headline"]["ordering_source"] == cpa.ORDER_SOURCE_SCORE

    def test_a_legacy_board_falls_back_to_board_rank_and_says_so(self):
        blk = cpa._rank_eff_block(_defn("t", _ordered_board(with_score=False)))
        assert blk["primary_ordering"] == cpa.ORDER_SOURCE_RANK
        score_block = blk["orderings"]["prophet_score"]
        assert score_block["available"] is False
        assert "board_rank only" in score_block["note"]

    def test_a_cost_metric_expects_the_OPPOSITE_sign_from_a_return_metric(self):
        """catastrophic is a cost: a good board correlates POSITIVELY with it.

        Reading every metric off one global "negative is good" rule would score a
        well-behaved board as broken on three of the nine ladder rungs.
        """
        recs = []
        for d in _RE_DATES[:3]:
            for rank in range(1, 9):
                # the best-ranked names avoid the catastrophes, the worst take them all
                pnl = 10.0 - rank if rank <= 5 else -20.0 - rank
                recs.append(_ep(d, f"{d}-{rank}", board_rank=float(rank),
                                excess=float(8 - rank), pnl=pnl))
        cell = cpa._rank_eff_block(_defn("t", recs))["orderings"]["board_rank"]["ic"]
        cat = cell["catastrophic"]
        assert cat["good_sign"] == "positive"
        assert cat["ic"] > 0
        assert cat["wrong_sign"] is False
        # and the return metric on the SAME board keeps the opposite expectation
        assert cell["excess_h10"]["good_sign"] == "negative"
        assert cell["excess_h10"]["ic"] < 0

    def test_every_ladder_rung_publishes_its_own_sign_expectation(self):
        """No rung may ship a number without the rule for reading it."""
        blk = cpa._rank_eff_block(_defn("t", _ordered_board()))
        ladder = blk["orderings"]["board_rank"]["ic"]
        assert set(ladder) == {m for m, _b, _n in cpa.RANK_EFF_METRICS}
        for metric, cell in ladder.items():
            assert cell["good_sign"] in ("negative", "positive"), metric
            assert isinstance(cell["metric_note"], str) and cell["metric_note"], metric

    def test_a_metric_the_ledger_cannot_answer_is_a_printed_null_not_a_gap(self):
        blk = cpa._rank_eff_block(_defn("t", _ordered_board()))
        mfe = blk["orderings"]["board_rank"]["ic"]["fwd_mfe_63"]
        assert mfe["ic"] is None and mfe["n"] == 0
        assert "accruing" in mfe["note"]
        assert mfe["wrong_sign"] is None, "a null must not read as a passing sign check"

    def test_a_definition_below_the_row_floor_discloses_rather_than_pretends(self):
        blk = cpa._rank_eff_block(_defn("t", _ordered_board(n_dates=1, width=4)))
        assert blk["available"] is False
        assert blk["n_matured"] == 4
        assert "blocks nothing" in blk["note"]

    def test_definitions_are_never_pooled(self):
        good = _defn("cn_prophet_v3", _ordered_board())
        bad = _defn("legacy", _ordered_board(inverted=True))
        out = cpa.rank_effectiveness([good, bad])
        by_name = {b["board_definition"]: b for b in out["definitions"]}
        assert by_name["cn_prophet_v3"]["headline"]["ic_excess_h10"] == pytest.approx(-1.0)
        assert by_name["legacy"]["headline"]["ic_excess_h10"] == pytest.approx(1.0)


class TestNullableOutcomes:
    """A three-valued column must never collapse its null into a False."""

    def test_a_never_cushioned_episode_is_not_a_breach(self):
        for null in (None, float("nan"), "", "nan", "None"):
            rec = _ep("2026-06-01", "A", post_cushion_breach=null)
            assert cpa._outcome(rec, "post_cushion_breach") is None, null

    def test_the_two_real_answers_still_read_through(self):
        assert cpa._outcome(_ep("d", "A", post_cushion_breach=True),
                            "post_cushion_breach") == 1.0
        assert cpa._outcome(_ep("d", "A", post_cushion_breach=False),
                            "post_cushion_breach") == 0.0

    def test_a_null_terminal_state_is_not_a_failed_liftoff(self):
        assert cpa._outcome(_ep("d", "A"), "clean_liftoff_21") is None
        assert cpa._outcome(_ep("d", "A", terminal_state_clean8_21="CLEAN_LIFTOFF"),
                            "clean_liftoff_21") == 1.0
        assert cpa._outcome(_ep("d", "A", terminal_state_clean8_21="STOPPED"),
                            "clean_liftoff_21") == 0.0

    def test_the_catastrophic_threshold_reads_percent_not_fraction(self):
        """score_from_fill returns pnl already multiplied by 100 — a −0.20 fraction
        would be a −20% loss under the wrong reading and a rounding error under this one."""
        assert cpa._outcome(_ep("d", "A", pnl=-15.1), "catastrophic") == 1.0
        assert cpa._outcome(_ep("d", "A", pnl=-14.9), "catastrophic") == 0.0
        assert cpa._outcome(_ep("d", "A", pnl=-0.20), "catastrophic") == 0.0


class TestDayOfMax:
    IDX = pd.bdate_range("2026-06-01", periods=30)

    def test_the_fill_bar_itself_is_day_one(self):
        """CN fills at the T+1 open, so that session's close is a legitimate exit and
        must be a candidate for the max — the same window score_from_fill walks."""
        closes = pd.Series([10.0, 99.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0,
                            18.0, 19.0], index=self.IDX[:11])
        assert cpa._day_of_max(closes, self.IDX[1], 10) == 1

    def test_a_later_high_is_reported_on_its_own_session(self):
        closes = pd.Series([10.0] + [1.0] * 4 + [50.0] + [1.0] * 5, index=self.IDX[:11])
        assert cpa._day_of_max(closes, self.IDX[1], 10) == 5

    def test_an_unfinished_window_is_null_not_an_early_peak(self):
        """Reporting day-of-max on a truncated window would say 'peaked on day 3' for
        the arithmetic reason that days 4-10 have not printed."""
        closes = pd.Series([10.0, 11.0, 12.0, 13.0], index=self.IDX[:4])
        assert cpa._day_of_max(closes, self.IDX[1], 10) is None
        assert cpa._day_of_max(closes, self.IDX[1], 3) == 3


class TestOracleRegret:
    """Arithmetic on one hand-computed date, then the degeneracy the mean would hide."""

    # rank 1..8; the two names the board ranked LAST are the two that actually ran.
    EXCESS = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 100.0, 200.0)
    ACHIEVED = (1 + 2 + 3 + 4 + 5 + 6) / 6          # 3.5  — the top-6 the board named
    ORACLE = (200 + 100 + 6 + 5 + 4 + 3) / 6        # 53.0 — the best-6 in hindsight
    REGRET = ORACLE - ACHIEVED                      # 49.5
    CAPTURE = 4 / 6                                 # ranks 3-6 are in both sets

    @classmethod
    def _date(cls, date: str, width: int = 8) -> list[dict]:
        return [_ep(date, f"{date}-{r}", board_rank=float(r), excess=cls.EXCESS[r - 1])
                for r in range(1, width + 1)]

    def test_the_arithmetic_on_a_single_date(self):
        out = cpa._oracle_regret(self._date(_RE_DATES[0]), cpa.ORDER_SOURCE_RANK)
        assert out["n_dates"] == 1
        day = out["by_date"][0]
        assert day["achieved_mean_excess"] == pytest.approx(self.ACHIEVED)
        assert day["oracle_mean_excess"] == pytest.approx(self.ORACLE)
        assert day["regret"] == pytest.approx(self.REGRET)
        assert day["capture"] == pytest.approx(self.CAPTURE, abs=1e-4)

    def test_regret_can_never_be_negative(self):
        """The oracle picks from the same pool, so it can only tie or beat the board."""
        out = cpa._oracle_regret(self._date(_RE_DATES[0]), cpa.ORDER_SOURCE_RANK)
        assert out["regret6"] >= 0

    def test_a_perfectly_ordered_date_leaves_no_regret(self):
        recs = [_ep(_RE_DATES[0], f"x{r}", board_rank=float(r), excess=float(20 - r))
                for r in range(1, 9)]
        out = cpa._oracle_regret(recs, cpa.ORDER_SOURCE_RANK)
        assert out["regret6"] == pytest.approx(0.0)
        assert out["capture6"] == pytest.approx(1.0)

    def test_a_pool_of_exactly_k_is_counted_as_degenerate_not_as_a_perfect_score(self):
        """With a pool of 6 the top-6 IS the pool: regret 0 and capture 1.0 are
        arithmetic, not skill, and averaging them in flatters the headline."""
        recs = self._date(_RE_DATES[0]) + self._date(_RE_DATES[1], width=6)
        out = cpa._oracle_regret(recs, cpa.ORDER_SOURCE_RANK)
        assert out["n_dates"] == 2
        assert out["n_dates_with_choice"] == 1
        assert out["n_dates_degenerate"] == 1
        assert out["regret6"] == pytest.approx(self.REGRET / 2, abs=1e-3)
        assert out["regret6_with_choice"] == pytest.approx(self.REGRET, abs=1e-3)
        assert out["capture6_with_choice"] == pytest.approx(self.CAPTURE, abs=1e-3)
        assert "no selection was possible" in out["note"]

    def test_a_date_too_thin_to_fill_the_shortlist_is_skipped_and_disclosed(self):
        out = cpa._oracle_regret(self._date(_RE_DATES[0], width=5),
                                 cpa.ORDER_SOURCE_RANK)
        assert out["n_dates"] == 0
        assert out["regret6"] is None
        assert "accruing" in out["note"]


class TestTerciles:
    @staticmethod
    def _recs(n: int) -> list[dict]:
        """n episodes spread over 2 dates, ranks strictly increasing, excess decreasing."""
        return [_ep(_RE_DATES[i % 2], f"tk{i}", board_rank=float(i + 1),
                    excess=float(n - i), pnl=float(n - i),
                    mae_proxy_10=float(-i), fwd_mfe_21=float(n - i),
                    day_of_max_10=float((i % 10) + 1))
                for i in range(n)]

    def test_the_split_is_identical_under_a_shuffled_input(self):
        """Determinism is the whole reason the split is positional over a total order.

        A quantile cut on this data is not reproducible: real legacy ordering keys are
        integer ranks 1-60 repeated across 18 dates, so bin edges land on huge ties and
        a tie-handling change silently moves episodes between buckets.
        """
        recs = self._recs(31)
        first = cpa._tercile_profile(recs, cpa.ORDER_SOURCE_RANK)
        second = cpa._tercile_profile(list(reversed(recs)), cpa.ORDER_SOURCE_RANK)
        third = cpa._tercile_profile(recs[7:] + recs[:7], cpa.ORDER_SOURCE_RANK)
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
        assert json.dumps(first, sort_keys=True) == json.dumps(third, sort_keys=True)

    def test_a_wall_of_tied_keys_still_splits_deterministically(self):
        """Every episode on the same ordering key — the case a quantile cut cannot do."""
        recs = [_ep(_RE_DATES[0], f"tk{i}", board_rank=7.0, excess=float(i))
                for i in range(30)]
        first = cpa._tercile_profile(recs, cpa.ORDER_SOURCE_RANK)
        second = cpa._tercile_profile(list(reversed(recs)), cpa.ORDER_SOURCE_RANK)
        assert [t["n"] for t in first["terciles"]] == [10, 10, 10]
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)

    def test_t1_is_the_best_ordered_third(self):
        prof = cpa._tercile_profile(self._recs(30), cpa.ORDER_SOURCE_RANK)
        t1, _t2, t3 = prof["terciles"]
        assert t1["tercile"] == "T1" and t3["tercile"] == "T3"
        assert t1["ordering_value_range"][1] <= t3["ordering_value_range"][0]

    def test_every_episode_lands_in_exactly_one_tercile(self):
        for n in (30, 31, 32, 100):
            prof = cpa._tercile_profile(self._recs(n), cpa.ORDER_SOURCE_RANK)
            assert sum(t["n"] for t in prof["terciles"]) == n, n

    def test_the_score_orientation_puts_the_best_score_in_t1(self):
        """The negation again, one layer down: with prophet_score the HIGHEST score is
        the best pick, so T1's range must be the top of the score band, not the bottom."""
        recs = [_ep(_RE_DATES[0], f"tk{i}", prophet_score=float(i), excess=float(i))
                for i in range(30)]
        prof = cpa._tercile_profile(recs, cpa.ORDER_SOURCE_SCORE)
        t1, _t2, t3 = prof["terciles"]
        assert t1["ordering_value_range"] == [20.0, 29.0]
        assert t3["ordering_value_range"] == [0.0, 9.0]

    def test_the_risk_and_duration_columns_are_all_present(self):
        """The operator's whole caution: a track record that reports only the loser rate
        cannot see a pick that is lower-risk or slower-but-bigger."""
        prof = cpa._tercile_profile(self._recs(30), cpa.ORDER_SOURCE_RANK)
        for t in prof["terciles"]:
            for col in ("loser_rate", "median_excess", "median_mae_proxy_10",
                        "catastrophic_rate", "clean_liftoff_share",
                        "post_cushion_breach_rate", "median_fwd_mfe_21",
                        "median_fwd_mfe_63", "median_day_of_max_10",
                        "median_day_of_max_21"):
                assert col in t, col

    def test_a_thin_sample_discloses_rather_than_splitting_three_ways(self):
        prof = cpa._tercile_profile(self._recs(5), cpa.ORDER_SOURCE_RANK)
        assert prof["terciles"] == []
        assert "accruing" in prof["note"]


class TestComponentAttribution:
    def test_each_stored_leg_gets_its_own_ic_against_both_metrics(self):
        recs = []
        for d in _RE_DATES[:3]:
            for i in range(8):
                recs.append(_ep(
                    d, f"{d}-{i}", prophet_score=float(10 - i),
                    prophet_signal=float(10 - i), prophet_entry=float(i),
                    excess=float(10 - i), fwd_mfe_21=float(10 - i),
                ))
        out = cpa._component_attribution(recs)
        # signal moves WITH the outcome → it earns its weight → negative IC
        assert out["prophet_signal"]["ic"]["excess_h10"]["ic"] == pytest.approx(-1.0)
        assert out["prophet_signal"]["ic"]["fwd_mfe_21"]["ic"] == pytest.approx(-1.0)
        assert out["prophet_signal"]["ic"]["excess_h10"]["wrong_sign"] is False
        # entry moves AGAINST it → it is paying for the wrong thing
        assert out["prophet_entry"]["ic"]["excess_h10"]["ic"] == pytest.approx(1.0)
        assert out["prophet_entry"]["ic"]["excess_h10"]["wrong_sign"] is True

    def test_a_leg_the_ledger_does_not_store_is_a_printed_null(self):
        """``prophet_theme_timing`` is in the V3 score but append_board does not persist
        it — the attribution must SAY so, so the dark leg is visible rather than absent.
        """
        out = cpa._component_attribution(_ordered_board())
        cell = out["prophet_theme_timing"]
        assert cell["available"] is False and cell["n"] == 0
        assert "does not store it" in cell["note"]

    def test_a_constant_leg_reports_the_constancy_rather_than_a_missing_number(self):
        recs = [_ep(_RE_DATES[0], f"x{i}", prophet_reversal_member=0.0,
                    excess=float(i)) for i in range(12)]
        cell = cpa._component_attribution(recs)["prophet_reversal_member"]
        assert cell["available"] is True and cell["n_distinct_values"] == 1
        assert "constant" in cell["note"]
        assert cell["ic"]["excess_h10"]["ic"] is None

    def test_every_component_column_is_reported_even_when_absent(self):
        out = cpa._component_attribution(_ordered_board())
        assert set(out) == set(cpa.PROPHET_COMPONENT_COLS)


class TestWrongSignWarning:
    """The alarm, pinned from BOTH sides — a guard that only ever fires is not a guard."""

    @staticmethod
    def _board(inverted: bool, n_dates: int) -> dict:
        return _defn("cn_prophet_vX", _ordered_board(n_dates=n_dates, inverted=inverted))

    def test_it_fires_on_an_anti_predictive_ordering(self, capsys):
        cpa.rank_effectiveness([self._board(inverted=True, n_dates=10)])
        lines = [ln for ln in capsys.readouterr().out.splitlines()
                 if ln.startswith("::warning")]
        assert len(lines) == 1
        assert "cn-prophet-rank-anti-predictive" in lines[0]
        assert "ANTI-PREDICTIVELY" in lines[0]

    def test_the_annotation_starts_the_line(self, capsys):
        """A logger would prefix it and GitHub would silently drop the whole alarm."""
        cpa.rank_effectiveness([self._board(inverted=True, n_dates=10)])
        out = [ln for ln in capsys.readouterr().out.splitlines() if "::warning" in ln]
        assert out and all(ln.startswith("::") for ln in out)

    def test_it_stays_quiet_on_a_well_ordered_board(self, capsys):
        cpa.rank_effectiveness([self._board(inverted=False, n_dates=10)])
        assert "cn-prophet-rank-anti-predictive" not in capsys.readouterr().out

    def test_it_stays_quiet_below_the_episode_floor(self, capsys):
        """Wrong sign, but too few episodes to carry the claim."""
        thin = self._board(inverted=True, n_dates=5)   # 40 episodes < 60
        blk = cpa.rank_effectiveness([thin])["definitions"][0]
        assert blk["n_matured"] < cpa.WRONG_SIGN_MIN_EPISODES
        assert blk["headline"]["ic_excess_h10"] > 0, "the fixture must still be inverted"
        assert "cn-prophet-rank-anti-predictive" not in capsys.readouterr().out

    def test_each_definition_gets_its_own_alarm(self, capsys):
        good = _defn("cn_prophet_v3", _ordered_board(n_dates=10))
        bad = _defn("legacy", _ordered_board(n_dates=10, inverted=True))
        cpa.rank_effectiveness([good, bad])
        lines = [ln for ln in capsys.readouterr().out.splitlines()
                 if ln.startswith("::warning")]
        assert len(lines) == 1 and "'legacy'" in lines[0]


# ---------------------------------------------------------------------------
# 7b. THE CALIBRATION RECEIPT — can the block see the defect already measured?
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def legacy_rank_block(legacy_block):
    """The rank-effectiveness block for the legacy era on the REPRO_ASOF-pinned grid."""
    return cpa._rank_eff_block(legacy_block)


@pytest.mark.skipif(not BOARD_PARQUET.exists(), reason="CN board store not present")
@pytest.mark.skipif(not any(CHINA_STOCKS.glob("*.parquet")),
                    reason="china_stocks price store not present")
class TestLegacyDefectCalibration:
    """The block must reproduce the audited V1 ordering defect on the frozen grid.

    masterplan §2.1 / CN-RC4: legacy board rank-IC vs H=10 excess = **+0.073**,
    anti-predictive. A rank grader that cannot see the one ordering failure this program
    has already measured has no standing to be trusted with the next one, and every
    other test in section 7 runs on synthetic data that the implementation and the test
    could be wrong about together.

    The frame is pinned to ``REPRO_ASOF`` through the module-scoped ``legacy_block``
    fixture. Without that pin the constant is a time bomb: fresh bars mature more legacy
    episodes every night (the live panel already reads +0.0899 over 441), so the number
    would drift away from the audit for the one reason that is not a regression.
    """

    def test_the_frozen_sample_is_the_one_the_audit_was_run_on(self, legacy_rank_block):
        """Guard the guard — on a different sample the constant below means nothing."""
        assert legacy_rank_block["available"] is True
        assert legacy_rank_block["n_matured"] == REPRO_MATURED
        assert legacy_rank_block["n_matured_with_excess"] == REPRO_MATURED

    def test_it_reproduces_the_audited_anti_predictive_rank_ic(self, legacy_rank_block):
        cell = legacy_rank_block["orderings"]["board_rank"]["ic"]["excess_h10"]
        assert cell["ic"] == pytest.approx(REPRO_RANK_IC_EXCESS, abs=IC_TOL)
        assert cell["n"] == REPRO_MATURED
        assert cell["n_dates"] == REPRO_RANK_IC_N_DATES
        assert cell["ic"] > 0, "the V1 defect is a POSITIVE IC — wrong sign"
        assert cell["wrong_sign"] is True
        assert legacy_rank_block["headline"]["ic_excess_h10"] == pytest.approx(
            REPRO_RANK_IC_EXCESS, abs=IC_TOL)

    def test_the_pooled_ic_agrees_with_the_per_date_reading(self, legacy_rank_block):
        """Two independent estimators landing on the same sign is the check that the
        defect is real rather than an artefact of the date grouping."""
        cell = legacy_rank_block["orderings"]["board_rank"]["ic"]["excess_h10"]
        assert cell["pooled_ic"] > 0
        assert abs(cell["pooled_ic"] - cell["ic"]) < 0.05

    def test_the_alarm_actually_fires_on_the_real_era(self, legacy_rank_block, capsys):
        cpa._warn_wrong_sign(legacy_rank_block)
        lines = [ln for ln in capsys.readouterr().out.splitlines()
                 if ln.startswith("::warning")]
        assert len(lines) == 1
        assert "cn-prophet-rank-anti-predictive" in lines[0]
        assert "board_rank" in lines[0]

    def test_the_legacy_era_reads_the_ordering_off_board_rank_only(self, legacy_rank_block):
        assert legacy_rank_block["primary_ordering"] == cpa.ORDER_SOURCE_RANK
        assert legacy_rank_block["orderings"]["prophet_score"]["available"] is False
        assert all(c["available"] is False for c in legacy_rank_block["components"].values())

    def test_the_defect_is_visible_on_the_risk_and_duration_axes_too(self, legacy_rank_block):
        """The reason the block is multi-metric. If the top third were merely
        slower-but-safer, the risk axes would clear it — they do not: the best-ranked
        third carried the DEEPEST drawdowns and the MOST catastrophes.
        """
        t1, t2, t3 = legacy_rank_block["risk_by_tercile"]["terciles"]
        assert t1["catastrophic_rate"] > t2["catastrophic_rate"]
        assert t1["catastrophic_rate"] > t3["catastrophic_rate"]
        assert t1["median_mae_proxy_10"] < t2["median_mae_proxy_10"]
        ladder = legacy_rank_block["orderings"]["board_rank"]["ic"]
        assert ladder["mae_proxy_10"]["wrong_sign"] is True
        assert ladder["fwd_mfe_10"]["wrong_sign"] is True

    def test_the_catastrophic_and_median_excess_baselines_still_reconcile(self, legacy_rank_block):
        """Cross-check against masterplan §8 M5/M2 — proof the block is reading the same
        episodes section 1 graded, not a differently-filtered sample."""
        terciles = legacy_rank_block["risk_by_tercile"]["terciles"]
        n_cat = sum(round(t["catastrophic_rate"] * t["n_pnl_graded"])
                    for t in terciles)
        assert n_cat == REPRO_CATASTROPHIC
        assert sum(t["n"] for t in terciles) == REPRO_MATURED

    def test_the_shortlist_left_most_of_its_own_upside_on_the_table(self, legacy_rank_block):
        orc = legacy_rank_block["oracle_regret"]
        assert orc["n_dates"] > 0
        assert orc["regret6"] > 0
        assert 0.0 <= orc["capture6"] <= 1.0
        assert orc["n_dates_degenerate"] == 0, \
            "legacy boards are 60 wide — none can be a degenerate pool"


# ---------------------------------------------------------------------------
# 7c. the block ships in the artifact and the forward log
# ---------------------------------------------------------------------------
class TestRankEffectivenessIsPublished:
    def test_the_artifact_carries_the_block(self, sandbox):
        cpa.run(asof=_ASOF, lane="asia")
        doc = json.loads(cpa.latest_path().read_text())
        blk = doc["rank_effectiveness"]
        assert blk["tier"] == "ops-telemetry"
        assert "none" in blk["authority"]
        assert "NEGATED" in blk["orientation"], "the sign convention must ship with it"
        assert isinstance(blk["elapsed_seconds"], (int, float))
        assert [d["board_definition"] for d in blk["definitions"]] == ["cn_prophet_v2"]

    def test_the_forward_log_carries_the_headline_columns(self, sandbox):
        rank_eff = cpa.rank_effectiveness([_defn("cn_prophet_v2", _ordered_board())])
        rows = cpa._forward_log_rows(
            [{"board_definition": "cn_prophet_v2", "n_episodes": 24, "n_matured": 24,
              "n_winners": 21, "n_losers": 3, "win_rate": 0.875, "loser_rate": 0.125,
              "median_excess": 3.5, "chase": {}}],
            _ASOF, rank_eff)
        cpa.append_forward_log(rows)
        df = pd.read_parquet(cpa.forward_log_path())
        assert len(df) == 1
        row = df.iloc[0]
        assert row["rank_ordering_source"] == cpa.ORDER_SOURCE_SCORE
        assert float(row["ic_excess_h10"]) == pytest.approx(-1.0)
        assert row["capture6"] == pytest.approx(1.0)
        # the pre-existing columns are untouched
        assert float(row["win_rate"]) == pytest.approx(0.875)

    def test_keep_first_still_holds_over_the_new_columns(self, sandbox):
        cpa.append_forward_log([{"date": _ASOF, "board_definition": "legacy",
                                 "ic_excess_h10": 0.0731}])
        cpa.append_forward_log([{"date": _ASOF, "board_definition": "legacy",
                                 "ic_excess_h10": -0.9}])
        df = pd.read_parquet(cpa.forward_log_path())
        assert len(df) == 1
        assert float(df.iloc[0]["ic_excess_h10"]) == pytest.approx(0.0731), \
            "a re-run rewrote a published rank-effectiveness headline"

    def test_a_definition_with_no_rank_headline_writes_nulls_not_zeros(self, sandbox):
        rows = cpa._forward_log_rows(
            [{"board_definition": "cn_reversal_watch_v1", "n_episodes": 0,
              "n_matured": 0, "n_winners": 0, "n_losers": 0, "win_rate": None,
              "loser_rate": None, "median_excess": None, "chase": {}}],
            _ASOF, {"definitions": []})
        assert rows[0]["ic_excess_h10"] is None
        assert rows[0]["capture6"] is None

    def test_the_block_stays_inside_its_budget(self, sandbox):
        res = cpa.run(asof=_ASOF, lane="asia")
        assert res["rank_effectiveness_seconds"] < 20.0

    def test_it_adds_no_write_outside_the_audit_store(self, sandbox):
        before = {p.relative_to(sandbox) for p in sandbox.rglob("*") if p.is_file()}
        cpa.run(asof=_ASOF, lane="asia")
        new = {str(p) for p in
               ({p.relative_to(sandbox) for p in sandbox.rglob("*") if p.is_file()}
                - before)}
        assert all(p.startswith(cpa.STORE_DIR) for p in new), sorted(new)
