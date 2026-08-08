"""tests/test_prophet_arena.py — the Prophet Arena shadow harness.

Everything here is SYNTHETIC: a crafted 20-row standouts fixture, hand-built price
series, and temporary roots.  No committed artifact is pinned (a test that asserts on
tonight's board grades the tape, not the code) and no fixture is anchored to the wall
clock (both the artifact date and the run's asof are supplied by the test, so nothing
here can date-bomb).

Run: .venv/bin/python -m pytest tests/test_prophet_arena.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from engine import prophet_arena as pa
from engine import prophet_bridge as pb

ROOT = Path(__file__).resolve().parent.parent

FIXTURE_ASOF = "2026-05-01"
FIXTURE_STAMP = "20260501"


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #
def _row(
    ticker: str,
    score: float,
    act_level: int,
    *,
    stage: str = "live",
    band: str = "high",
    status: str = "buy_now",
    conviction: float = 70.0,
    spot: float = 100.0,
    direction: str = "up",
) -> dict:
    """One buy-lane row shaped like a us_standouts entry."""
    return {
        "ticker": ticker,
        "dir": direction,
        "stage": stage,
        "prophet": {"version": "us_prophet_v1", "score": score},
        "conviction": {"score": conviction, "band": band},
        "entry_signal": {
            "act_level": act_level,
            "status": status,
            "spot": spot,
            "atr_pct": 5.0,     # entry 100 - 2*5 = 90 invalidation, R=10, T1=115, T2=130
            "chase_above": None,
        },
        "hold": {},
    }


@pytest.fixture()
def standouts() -> dict:
    """20 buy rows engineered so every policy resolves to a DIFFERENT, exact set.

    Admission with gate_go=True is ``act_level >= 2 AND band != 'low'``.

      A01..A14  admitted; scores 90 down to 25 in steps of 5; act_level alternates
                3, 2, 3, 2, ... so C1's "act_level==2 first" re-order is unambiguous.
      X03       admitted, lowest score (10) — the row the cap keeps cutting.
      R01       stage 'ran', status 'hold' — ANTICIPATION A1 (2026-08-08) admits it
                into the champion pool on its status; it used to sit outside on
                act_level 1.  Left as-is deliberately: a stage-ran patience row
                entering on its own is exactly what A1 was built to do.
      R02..R03  stage 'ran', statuses the class refuses ('extended' / 'topping');
                R03 is also band 'low'.  The champion cannot admit them, and neither
                can C2's widening (see the C2 test for why the widening is now inert).
      X01       band 'low' with the highest score of all — a hard exclusion no
                policy may ever reach.
      X02       status 'buy_soon', band high — a hard exclusion under the STATUS
                CLASS (A1), and NOT stage-ran, so C2's widening must not rescue it
                either.  It was act_level 1 before A1 and excluded by the act gate;
                the row keeps act_level 1 so C1's ordering leg is unaffected.
    """
    buy: list[dict] = []
    score = 90.0
    for i in range(1, 15):
        buy.append(_row(f"A{i:02d}", score, 3 if i % 2 else 2))
        score -= 5.0
    buy.append(_row("R01", 88.0, 1, stage="ran", band="neutral", status="hold"))
    buy.append(_row("R02", 62.0, 0, stage="ran", band="neutral", status="extended"))
    buy.append(_row("R03", 41.0, 1, stage="ran", band="low", status="topping"))
    buy.append(_row("X01", 95.0, 3, band="low"))
    buy.append(_row("X02", 92.0, 1, status="buy_soon"))
    buy.append(_row("X03", 10.0, 2))
    return {"as_of": FIXTURE_ASOF, "gate_go": True, "buy": buy}


class FakePrices:
    """PriceCache stand-in: an explicit {ticker: Series|None} map, nothing on disk."""

    def __init__(self, series: dict[str, "pd.Series | None"] | None = None) -> None:
        self._series = series or {}

    def get(self, ticker: str):
        return self._series.get(str(ticker))


def _closes(values: list[float], start: str = "2026-05-02") -> pd.Series:
    """A daily close series on consecutive CALENDAR days from ``start``."""
    idx = pd.date_range(start=start, periods=len(values), freq="D")
    return pd.Series([float(v) for v in values], index=idx)


def _plan(**over) -> dict:
    """A shadow plan with the fixture's clean geometry: 100 / 90 / 115 / 130 / 45d."""
    base = {
        "id": "A01-BULL-20260501",
        "asset": "A01",
        "direction": "BULL",
        "entry": 100.0,
        "invalidation": 90.0,
        "targets": [115.0, 130.0],
        "horizon_days": 45,
        "signal_date": FIXTURE_ASOF,
    }
    base.update(over)
    return base


def _tickers(rows: list[dict]) -> list[str]:
    return [str(r["ticker"]) for r in rows]


# --------------------------------------------------------------------------- #
# 1. Policy determinism — exact selections on the fixture.                     #
# --------------------------------------------------------------------------- #
#: The champion's admitted pool on the fixture, in champion order.  R01 (score 88,
#: status `hold`) sits between A01 (90) and A02 (85) since ANTICIPATION A1 admitted
#: the patience class — see the fixture docstring.
_POOL = ["A01", "R01"] + [f"A{i:02d}" for i in range(2, 15)] + ["X03"]


class TestPolicyDeterminism:
    def test_admitted_pool_is_the_champion_filter_uncapped(self, standouts):
        pool = pa.admitted_pool(standouts)
        assert _tickers(pool) == _POOL

    def test_c0_exact(self, standouts):
        rows, rec = pa.select_for_policy("C0_champion_mirror", standouts, cap=12)
        assert _tickers(rows) == _POOL[:12]
        assert rec["admitted"] == 16

    def test_c1_lifts_act_level_two_then_champion_order(self, standouts):
        rows, rec = pa.select_for_policy("C1_buy_soon_first", standouts, cap=12)
        assert _tickers(rows) == [
            "A02", "A04", "A06", "A08", "A10", "A12", "A14", "X03",
            "A01", "R01", "A03", "A05",
        ]
        assert rec["act_level_2"] == 8
        assert rec["lifted"] == 8

    def test_c2_widening_is_INERT_since_the_act_level_gate_was_removed(
            self, standouts):
        """C2's pool-widening lifts `act_level` to 2 — an input the champion no
        longer reads (ANTICIPATION A1, 2026-08-08), so the widening can no longer
        admit anything and C2 degenerates to a re-ordering policy.

        Pinned as a DELIBERATE non-repair: `engine/prophet_arena.py` is owned by the
        Arena lane, not by A1, and re-basing C2's widening onto the status class is
        that lane's call.  This test FAILS THE MOMENT the widening starts working
        again, which is when the expectations below should be rewritten rather than
        re-pointed.  R01 needs no widening any more — the champion admits it on its
        `hold` status directly, which is the outcome A1 was built for.
        """
        rows, rec = pa.select_for_policy("C2_stage_ran_preferred", standouts, cap=12)
        assert rec["stage_ran_admitted_by_widening"] == 0, (
            "the widening lifts act_level, which is no longer an admission input")
        assert _tickers(rows) == ["R01"] + [
            t for t in _POOL[:12] if t != "R01"]
        assert rec["stage_ran_in_champion_pool"] == 1
        assert rec["stage_ran_selected"] == 1

    def test_c4_and_c6_selections(self, standouts):
        six, _ = pa.select_for_policy(
            "C4_dispersion_cap", standouts, cap=12, dispersion_cap=6
        )
        assert _tickers(six) == _POOL[:6]
        c6, rec = pa.select_for_policy("C6_time_stop_21", standouts, cap=12)
        c0, _ = pa.select_for_policy("C0_champion_mirror", standouts, cap=12)
        assert _tickers(c6) == _tickers(c0)
        assert "identical to C0" in rec["selection_basis"]

    def test_selection_is_deterministic_across_calls(self, standouts):
        for key in pa.POLICY_KEYS:
            if key == "C5_align2_gate":
                continue
            first, _ = pa.select_for_policy(key, standouts, cap=12, door_rows=[])
            second, _ = pa.select_for_policy(key, standouts, cap=12, door_rows=[])
            assert _tickers(first) == _tickers(second), key

    def test_unknown_policy_raises(self, standouts):
        with pytest.raises(ValueError):
            pa.select_for_policy("C9_nope", standouts)

    def test_hard_exclusions_are_unreachable_by_every_policy(self, standouts):
        """A band-'low' row and a refused-status row must never appear anywhere."""
        for key in pa.POLICY_KEYS:
            if key == "C5_align2_gate":
                continue
            rows, _ = pa.select_for_policy(key, standouts, cap=12, door_rows=[])
            assert "X01" not in _tickers(rows), key   # band low
            assert "X02" not in _tickers(rows), key   # buy_soon, not stage-ran
            assert "R02" not in _tickers(rows), key   # stage-ran but 'extended'
            assert "R03" not in _tickers(rows), key   # stage-ran but band low


# --------------------------------------------------------------------------- #
# 2. C0 mirror equality — the harness-validity pin.                            #
# --------------------------------------------------------------------------- #
class TestC0Mirror:
    def test_c0_equals_a_direct_select_candidates_call(self, standouts):
        direct = pb.select_candidates(standouts, n=pb.N_CANDIDATES)
        mirror, _ = pa.select_for_policy(
            "C0_champion_mirror", standouts, cap=pb.N_CANDIDATES
        )
        assert _tickers(mirror) == _tickers(direct)

    def test_c0_equality_survives_a_reordered_artifact(self, standouts):
        """The mirror must track the champion's own order-invariance, not the file's."""
        shuffled = dict(standouts)
        shuffled["buy"] = list(reversed(standouts["buy"]))
        direct = pb.select_candidates(shuffled, n=pb.N_CANDIDATES)
        mirror, _ = pa.select_for_policy(
            "C0_champion_mirror", shuffled, cap=pb.N_CANDIDATES
        )
        assert _tickers(mirror) == _tickers(direct)

    def test_c0_plan_ids_match_a_bridge_id_for_each_pick(self, standouts):
        rows, _ = pa.select_for_policy("C0_champion_mirror", standouts, cap=12)
        plans, _ = pa.originate_shadow_plans(
            "C0_champion_mirror", rows,
            asof=FIXTURE_ASOF, standouts_asof=FIXTURE_ASOF,
            existing_ids=set(), active_keys=None, prices=FakePrices(),
        )
        assert [p["id"] for p in plans] == [
            pb._make_id(t, "BULL", FIXTURE_ASOF) for t in _tickers(rows)
        ]
        assert plans[0]["id"] == f"A01-BULL-{FIXTURE_STAMP}"

    def test_mirror_reports_mismatch_when_the_live_run_differed(self, standouts, tmp_path):
        board = pa.build_scoreboard(
            asof=FIXTURE_ASOF, root=tmp_path,
            validity={"c0_mismatch_count": 2, "missing_from_mirror": ["Z-BULL-1"]},
        )
        assert board["harness_validity"]["harness_ok"] is False
        assert "suspect" in board["harness_validity"]["meaning"]

    def test_mirror_reports_ok_when_ids_matched(self, tmp_path):
        board = pa.build_scoreboard(
            asof=FIXTURE_ASOF, root=tmp_path, validity={"c0_mismatch_count": 0}
        )
        assert board["harness_validity"]["harness_ok"] is True


# --------------------------------------------------------------------------- #
# 3. Origination — suppression ladder, geometry reuse.                         #
# --------------------------------------------------------------------------- #
class TestOrigination:
    def test_geometry_comes_from_the_bridge(self, standouts):
        rows, _ = pa.select_for_policy("C0_champion_mirror", standouts, cap=2)
        plans, _ = pa.originate_shadow_plans(
            "C0_champion_mirror", rows,
            asof=FIXTURE_ASOF, standouts_asof=FIXTURE_ASOF,
            existing_ids=set(), active_keys=None, prices=FakePrices(),
        )
        assert plans[0]["invalidation"] == 90.0
        assert plans[0]["targets"] == [115.0, 130.0]
        assert plans[0]["horizon_days"] == pb.HORIZON_DAYS_DEFAULT

    def test_existing_id_and_open_key_suppression(self, standouts):
        rows, _ = pa.select_for_policy("C0_champion_mirror", standouts, cap=3)
        plans, rec = pa.originate_shadow_plans(
            "C0_champion_mirror", rows,
            asof=FIXTURE_ASOF, standouts_asof=FIXTURE_ASOF,
            existing_ids={f"A01-BULL-{FIXTURE_STAMP}"},
            active_keys={pb.plan_key("A02", "BULL")},
            prices=FakePrices(),
        )
        # cap=3 takes A01, R01, A02 off the pool; A01 is a duplicate id and A02 has
        # an open plan, so R01 is the only survivor.
        assert [p["asset"] for p in plans] == ["R01"]
        assert rec["skipped_duplicate_id"] == 1
        assert rec["skipped_open_plan"] == 1

    def test_missing_spot_is_skipped_and_counted(self):
        row = _row("NOSPOT", 50.0, 3)
        row["entry_signal"]["spot"] = None
        plans, rec = pa.originate_shadow_plans(
            "C0_champion_mirror", [row],
            asof=FIXTURE_ASOF, standouts_asof=FIXTURE_ASOF,
            existing_ids=set(), active_keys=None, prices=FakePrices(),
        )
        assert plans == []
        assert rec["skipped_no_spot"] == 1


# --------------------------------------------------------------------------- #
# 4. C3 — union dedupe and skip counting.                                      #
# --------------------------------------------------------------------------- #
def _door_row(ticker: str, depth: float, spot: float = 100.0) -> dict:
    return {
        "ticker": ticker,
        "dir": "up",
        "entry_signal": {
            "act_level": 2, "spot": spot, "atr_pct": None,
            "status": "door_w", "chase_above": None,
        },
        "conviction": {"score": None, "band": None},
        "hold": {},
        "_arena_source": "door_w",
        "_arena_door_w": {"depth_sort_key": depth, "weeks_since_cross": 1},
    }


class TestC3Union:
    def test_reserved_slots_and_champion_head(self, standouts):
        doors = [_door_row(f"D{i:02d}", float(i)) for i in range(1, 6)]
        rows, rec = pa.select_for_policy(
            "C3_door_w_union", standouts, cap=12, door_rows=doors
        )
        # 12-cap = champion's top 8 + the 4 deepest Door W names.
        assert _tickers(rows) == _POOL[:8] + ["D01", "D02", "D03", "D04"]
        assert rec["door_w_reserved_slots"] == pa.DOOR_W_RESERVED_SLOTS
        assert rec["door_w_selected"] == 4

    def test_a_name_in_both_pools_originates_exactly_one_plan(self, standouts):
        """Union dedupe: the champion's row wins and no second plan is built."""
        doors = [_door_row("A03", 0.5), _door_row("D01", 1.0)]
        rows, rec = pa.select_for_policy(
            "C3_door_w_union", standouts, cap=12, door_rows=doors
        )
        assert _tickers(rows).count("A03") == 1
        assert rec["door_w_already_in_champion_pool"] == 1
        # And the surviving A03 is the CHAMPION's row, not the synthesized one.
        a03 = next(r for r in rows if r["ticker"] == "A03")
        assert a03.get("_arena_source") is None

        plans, _ = pa.originate_shadow_plans(
            "C3_door_w_union", rows,
            asof=FIXTURE_ASOF, standouts_asof=FIXTURE_ASOF,
            existing_ids=set(), active_keys=None, prices=FakePrices(),
        )
        ids = [p["id"] for p in plans]
        assert len(ids) == len(set(ids))
        assert ids.count(pb._make_id("A03", "BULL", FIXTURE_ASOF)) == 1

    def test_door_w_row_without_geometry_is_skipped_and_counted(self, standouts):
        """A Door W row has no ATR, so with no price history it has no invalidation."""
        doors = [_door_row("D01", 1.0)]
        rows, _ = pa.select_for_policy(
            "C3_door_w_union", standouts, cap=12, door_rows=doors
        )
        plans, rec = pa.originate_shadow_plans(
            "C3_door_w_union", rows,
            asof=FIXTURE_ASOF, standouts_asof=FIXTURE_ASOF,
            existing_ids=set(), active_keys=None,
            prices=FakePrices({"D01": None}),
        )
        assert rec["skipped_door_w_no_geometry"] == 1
        assert rec["skipped_door_w_tickers"] == ["D01"]
        assert "D01" not in [p["asset"] for p in plans]

    def test_door_w_row_with_history_gets_swing_low_geometry(self, standouts):
        doors = [_door_row("D01", 1.0)]
        rows, _ = pa.select_for_policy(
            "C3_door_w_union", standouts, cap=12, door_rows=doors
        )
        history = _closes([80.0] * 25, start="2026-04-01")
        plans, rec = pa.originate_shadow_plans(
            "C3_door_w_union", rows,
            asof=FIXTURE_ASOF, standouts_asof=FIXTURE_ASOF,
            existing_ids=set(), active_keys=None,
            prices=FakePrices({"D01": history}),
        )
        assert rec["skipped_door_w_no_geometry"] == 0
        d01 = next(p for p in plans if p["asset"] == "D01")
        assert d01["invalidation"] == 80.0        # the 20-day swing low
        assert d01["_arena_source"] == "door_w"

    def test_door_w_reader_counts_names_with_no_prices(self, monkeypatch):
        def fake_candidates(root=None):
            return {
                "candidates": [(1.0, "GOOD", {"weeks_since_cross": 1}),
                               (2.0, "NOPRICE", {"weeks_since_cross": 2})],
                "disclosure": {"ok": True},
            }

        monkeypatch.setattr(
            "engine.prophet_doors.door_w_candidates", fake_candidates, raising=True
        )
        rows, disc = pa.door_w_rows(
            FakePrices({"GOOD": _closes([50.0] * 30), "NOPRICE": None})
        )
        assert [r["ticker"] for r in rows] == ["GOOD"]
        assert disc["candidates"] == 2
        assert disc["skipped_no_prices"] == 1
        assert disc["skipped_tickers"] == ["NOPRICE"]

    def test_door_w_unavailable_degrades_to_champion_only(self, monkeypatch, capsys):
        def boom(root=None):
            raise RuntimeError("organ down")

        monkeypatch.setattr(
            "engine.prophet_doors.door_w_candidates", boom, raising=True
        )
        rows, disc = pa.door_w_rows(FakePrices())
        assert rows == []
        assert disc["ok"] is False
        out = capsys.readouterr().out
        assert any(line.startswith("::warning") for line in out.splitlines())


# --------------------------------------------------------------------------- #
# 5. C4 — regime branch and fail-open.                                         #
# --------------------------------------------------------------------------- #
def _write_regime(root: Path, payload: dict) -> None:
    d = root / "data" / "dispersion"
    d.mkdir(parents=True, exist_ok=True)
    (d / "regime.json").write_text(json.dumps(payload), encoding="utf-8")


class TestC4DispersionCap:
    def test_lean_in_keeps_the_champion_cap(self, tmp_path):
        _write_regime(tmp_path, {"as_of": "2026-05-01", "state": "lean_in"})
        cap, rec = pa.read_dispersion_state("2026-05-01", tmp_path)
        assert cap == pa.DISPERSION_CAP_LEAN_IN == pb.N_CANDIDATES == 16
        assert rec["mode"] == "lean_in"

    def test_other_state_halves_the_cap(self, tmp_path):
        _write_regime(tmp_path, {"as_of": "2026-05-01", "state": "spread_out"})
        cap, rec = pa.read_dispersion_state("2026-05-01", tmp_path)
        assert cap == pa.DISPERSION_CAP_OTHERWISE == 6
        assert rec["mode"] == "not_lean_in"

    def test_absent_artifact_fails_open_to_the_champion_cap(self, tmp_path):
        cap, rec = pa.read_dispersion_state("2026-05-01", tmp_path)
        assert cap == pa.DISPERSION_CAP_LEAN_IN
        assert rec["mode"] == "fail_open_absent"

    def test_stale_artifact_fails_open_and_records_the_staleness(self, tmp_path):
        # 2026-05-01 -> 2026-05-29 is 20 business days, well past the 5-session bar.
        _write_regime(tmp_path, {"as_of": "2026-05-01", "state": "spread_out"})
        cap, rec = pa.read_dispersion_state("2026-05-29", tmp_path)
        assert cap == pa.DISPERSION_CAP_LEAN_IN
        assert rec["mode"] == "fail_open_stale"
        assert rec["stale_sessions"] > pa.DISPERSION_MAX_STALE_SESSIONS

    def test_a_state_inside_the_freshness_bar_still_fires(self, tmp_path):
        # 2026-05-01 (Fri) -> 2026-05-06 (Wed) is 3 business days: fresh.
        _write_regime(tmp_path, {"as_of": "2026-05-01", "state": "spread_out"})
        cap, rec = pa.read_dispersion_state("2026-05-06", tmp_path)
        assert cap == pa.DISPERSION_CAP_OTHERWISE
        assert rec["mode"] == "not_lean_in"
        assert rec["stale_sessions"] <= pa.DISPERSION_MAX_STALE_SESSIONS

    def test_null_state_fails_open(self, tmp_path):
        _write_regime(tmp_path, {"as_of": "2026-05-01", "state": None})
        cap, rec = pa.read_dispersion_state("2026-05-01", tmp_path)
        assert cap == pa.DISPERSION_CAP_LEAN_IN
        assert rec["mode"] == "fail_open_null_state"

    def test_unreadable_artifact_fails_open(self, tmp_path):
        d = tmp_path / "data" / "dispersion"
        d.mkdir(parents=True, exist_ok=True)
        (d / "regime.json").write_text("{not json", encoding="utf-8")
        cap, rec = pa.read_dispersion_state("2026-05-01", tmp_path)
        assert cap == pa.DISPERSION_CAP_LEAN_IN
        assert rec["mode"] == "fail_open_unreadable"

    def test_the_mode_is_always_recorded(self, tmp_path):
        """'cap was 12' must never be ambiguous between lean_in and a missing dial."""
        _, rec = pa.read_dispersion_state("2026-05-01", tmp_path)
        assert rec["mode"] is not None


# --------------------------------------------------------------------------- #
# 6. C5 — alignment gate exclusion counting.                                   #
# --------------------------------------------------------------------------- #
class StubGate:
    def __init__(self, admitted: set[str]) -> None:
        self._admitted = admitted
        self.counts = {"admitted": 0, "excluded_misaligned": 0}

    def admits(self, ticker: str) -> bool:
        ok = ticker in self._admitted
        self.counts["admitted" if ok else "excluded_misaligned"] += 1
        return ok

    def receipt(self) -> dict:
        return dict(self.counts)


class TestC5AlignGate:
    def test_gate_restricts_and_can_reach_past_the_champion_cap(self, standouts):
        """A restriction frees cap slots, so C5 reaches rows C0's cap cut."""
        allowed = {"A01", "A02", "A13", "A14", "X03"}
        rows, rec = pa.select_for_policy(
            "C5_align2_gate", standouts, cap=12, atlas=StubGate(allowed)
        )
        assert _tickers(rows) == ["A01", "A02", "A13", "A14", "X03"]
        assert rec["passed_gate"] == 5
        assert rec["excluded"] == 11

    def test_exclusion_counts_are_reported(self, standouts):
        gate = StubGate({"A01"})
        _rows, rec = pa.select_for_policy(
            "C5_align2_gate", standouts, cap=12, atlas=gate
        )
        assert rec["align_gate"]["admitted"] == 1
        assert rec["align_gate"]["excluded_misaligned"] == 15

    def test_unreadable_atlas_excludes_and_counts_separately(self, monkeypatch):
        gate = pa.AtlasGate()
        monkeypatch.setattr(
            pa.AtlasGate, "_evaluate", lambda self, t: (False, "unreadable")
        )
        assert gate.admits("ANY") is False
        assert gate.counts["excluded_unreadable"] == 1
        assert gate.counts["excluded_misaligned"] == 0

    def test_misaligned_and_fallback_admissions_are_counted_apart(self, monkeypatch):
        verdicts = {
            "OK": (True, "weekly_align_class"),
            "PROXY": (True, "fallback_align_now"),
            "BAD": (False, "weekly_align_class"),
        }
        monkeypatch.setattr(
            pa.AtlasGate, "_evaluate", lambda self, t: verdicts[t]
        )
        gate = pa.AtlasGate()
        for t in ("OK", "PROXY", "BAD"):
            gate.admits(t)
        assert gate.counts["admitted"] == 2
        assert gate.counts["admitted_via_fallback"] == 1
        assert gate.counts["excluded_misaligned"] == 1
        assert "excluded" in gate.receipt()["basis"]

    def test_gate_result_is_cached_per_name(self, monkeypatch):
        calls: list[str] = []

        def counting(self, ticker):
            calls.append(ticker)
            return True, "weekly_align_class"

        monkeypatch.setattr(pa.AtlasGate, "_evaluate", counting)
        gate = pa.AtlasGate()
        gate.admits("A")
        gate.admits("A")
        assert calls == ["A"]


# --------------------------------------------------------------------------- #
# 7. The ruler — closure replay.                                               #
# --------------------------------------------------------------------------- #
class TestClosureReplay:
    def test_still_open_returns_none(self):
        assert pa.replay_closure(_plan(), _closes([101.0, 102.0, 103.0])) is None

    def test_t1_hit(self):
        v = pa.replay_closure(_plan(), _closes([101.0, 110.0, 116.0, 120.0]))
        assert v["outcome"] == "T1_HIT"
        assert v["close_price"] == 116.0
        assert v["stock_result_pct"] == 16.0
        assert v["sessions_held"] == 3

    def test_t2_hit_only_when_a_single_close_clears_it(self):
        v = pa.replay_closure(_plan(), _closes([101.0, 135.0]))
        assert v["outcome"] == "T2_HIT"
        assert v["stock_result_pct"] == 35.0

    def test_first_trigger_closes_t1_before_a_later_t2(self):
        v = pa.replay_closure(_plan(), _closes([116.0, 140.0]))
        assert v["outcome"] == "T1_HIT"

    def test_invalidation(self):
        v = pa.replay_closure(_plan(), _closes([99.0, 95.0, 89.0]))
        assert v["outcome"] == "INVALIDATED"
        assert v["stock_result_pct"] == -11.0

    def test_expiry_marks_at_the_horizon_close(self):
        v = pa.replay_closure(_plan(), _closes([100.5] * 60))
        assert v["outcome"] == "EXPIRED"
        # signal 2026-05-01, first bar 2026-05-02 -> the 45th calendar day is 2026-06-15.
        assert v["days_held"] == 45
        assert v["close_date"] == "2026-06-15"

    def test_a_short_frame_leaves_the_plan_open(self):
        """PIN 8: a frame ending before the horizon is not a missed expiry."""
        assert pa.replay_closure(_plan(), _closes([100.5] * 10)) is None

    def test_same_day_precedence_is_worst_case_first(self):
        """A bar below invalidation AND above T2 records INVALIDATED, never T2_HIT."""
        wide = _plan(invalidation=120.0, targets=[115.0, 118.0])
        v = pa.replay_closure(wide, _closes([119.0]))
        assert v["outcome"] == "INVALIDATED"

    def test_signal_day_close_is_excluded(self):
        """PIN 2: the plan was not live on its own signal day."""
        series = _closes([89.0], start=FIXTURE_ASOF)      # the signal day itself
        assert pa.replay_closure(_plan(), series) is None

    def test_bear_direction_mirrors(self):
        bear = _plan(direction="BEAR", invalidation=110.0, targets=[85.0, 70.0])
        assert pa.replay_closure(bear, _closes([111.0]))["outcome"] == "INVALIDATED"
        assert pa.replay_closure(bear, _closes([84.0]))["outcome"] == "T1_HIT"

    def test_missing_entry_or_signal_date_returns_none(self):
        assert pa.replay_closure(_plan(entry=None), _closes([116.0])) is None
        assert pa.replay_closure(_plan(signal_date=None), _closes([116.0])) is None
        assert pa.replay_closure(_plan(), None) is None

    def test_non_finite_closes_are_skipped_not_fatal(self):
        v = pa.replay_closure(_plan(), _closes([float("nan"), 116.0]))
        assert v["outcome"] == "T1_HIT"


class TestC6TimeStop:
    def test_fires_at_the_21st_session_when_below_entry(self):
        v = pa.replay_closure(
            _plan(), _closes([95.0] * 30), time_stop_sessions=pa.TIME_STOP_SESSIONS
        )
        assert v["outcome"] == pa.OUTCOME_TIME_STOPPED
        assert v["sessions_held"] == 21
        assert v["stock_result_pct"] == -5.0

    def test_does_not_fire_before_the_21st_session(self):
        v = pa.replay_closure(
            _plan(), _closes([95.0] * 20), time_stop_sessions=pa.TIME_STOP_SESSIONS
        )
        assert v is None

    def test_does_not_fire_when_the_plan_is_above_entry(self):
        v = pa.replay_closure(
            _plan(), _closes([105.0] * 30), time_stop_sessions=pa.TIME_STOP_SESSIONS
        )
        assert v is None

    def test_price_triggers_still_outrank_the_time_stop(self):
        """PIN 9: the time stop is evaluated AFTER the three champion triggers."""
        series = _closes([95.0] * 20 + [89.0])
        v = pa.replay_closure(
            _plan(), series, time_stop_sessions=pa.TIME_STOP_SESSIONS
        )
        assert v["outcome"] == "INVALIDATED"

    def test_time_stop_outranks_calendar_expiry_on_a_colliding_bar(self):
        """PIN 9: with a 5-day horizon the 21st session is also past expiry."""
        short = _plan(horizon_days=5)
        v = pa.replay_closure(
            short, _closes([95.0] * 30), time_stop_sessions=pa.TIME_STOP_SESSIONS
        )
        # Expiry fires first here because it is reached at session 5, long before 21 —
        # the champion's rule is untouched by the knob until the knob's bar arrives.
        assert v["outcome"] == "EXPIRED"

    def test_none_reproduces_the_champion_exactly(self):
        series = _closes([95.0] * 60)
        champion = pa.replay_closure(_plan(), series)
        assert champion["outcome"] == "EXPIRED"
        assert pa.OUTCOME_TIME_STOPPED not in pa.CHAMPION_OUTCOMES

    def test_c6_and_c0_close_the_same_plan_at_different_exits(self):
        """The paired comparison is only meaningful if the entries are identical."""
        series = _closes([95.0] * 60)
        plan = _plan()
        c0 = pa.replay_closure(plan, series)
        c6 = pa.replay_closure(plan, series, time_stop_sessions=pa.TIME_STOP_SESSIONS)
        assert c0["outcome"] == "EXPIRED" and c6["outcome"] == pa.OUTCOME_TIME_STOPPED
        assert c6["days_held"] < c0["days_held"]


# --------------------------------------------------------------------------- #
# 8. Ledgers — lane gate, keep-first, idempotency.                             #
# --------------------------------------------------------------------------- #
@pytest.fixture()
def nightly(monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    return True


def _open(pid: str, night: str = "2026-05-01", **over) -> dict:
    row = {
        "schema": pa.LEDGER_SCHEMA, "kind": "open", "policy": "C0_champion_mirror",
        "id": pid, "asset": pid.split("-")[0], "direction": "BULL",
        "signal_date": FIXTURE_ASOF, "arena_night": night,
        "entry": 100.0, "invalidation": 90.0, "targets": [115.0, 130.0],
        "horizon_days": 45,
    }
    row.update(over)
    return row


class TestLedgerLaneGate:
    def test_non_nightly_writes_nothing(self, tmp_path, monkeypatch):
        monkeypatch.delenv("COLLECT_LANE", raising=False)
        monkeypatch.delenv("US_LANE", raising=False)
        assert pa.append_rows("C0_champion_mirror", [_open("A-BULL-1")], tmp_path) == 0
        assert not pa.ledger_path("C0_champion_mirror", tmp_path).exists()

    def test_nightly_appends(self, tmp_path, nightly):
        assert pa.append_rows("C0_champion_mirror", [_open("A-BULL-1")], tmp_path) == 1
        assert pa.ledger_path("C0_champion_mirror", tmp_path).exists()

    def test_force_is_available_to_tests_only(self, tmp_path, monkeypatch):
        monkeypatch.delenv("COLLECT_LANE", raising=False)
        monkeypatch.delenv("US_LANE", raising=False)
        assert pa.append_rows(
            "C0_champion_mirror", [_open("A-BULL-1")], tmp_path, force=True
        ) == 1

    def test_idempotent_across_runs(self, tmp_path, nightly):
        rows = [_open("A-BULL-1"), _open("B-BULL-1")]
        assert pa.append_rows("C0_champion_mirror", rows, tmp_path) == 2
        assert pa.append_rows("C0_champion_mirror", rows, tmp_path) == 0
        assert len(pa.read_ledger("C0_champion_mirror", tmp_path)) == 2

    def test_keep_first_on_policy_id_kind(self, tmp_path, nightly):
        pa.append_rows("C0_champion_mirror", [_open("A-BULL-1", entry=100.0)], tmp_path)
        # A hand-appended duplicate must not supersede the first row.
        with pa.ledger_path("C0_champion_mirror", tmp_path).open("a") as fh:
            fh.write(json.dumps(_open("A-BULL-1", entry=999.0)) + "\n")
        rows = pa.read_ledger("C0_champion_mirror", tmp_path)
        assert len(rows) == 1 and rows[0]["entry"] == 100.0

    def test_open_and_close_coexist_for_one_plan(self, tmp_path, nightly):
        pa.append_rows("C0_champion_mirror", [_open("A-BULL-1")], tmp_path)
        close = pa.close_row(
            "C0_champion_mirror", {"id": "A-BULL-1", "asset": "A"},
            {"outcome": "T1_HIT", "stock_result_pct": 16.0,
             "close_date": "2026-05-10", "days_held": 9, "sessions_held": 9},
            asof="2026-05-10",
        )
        assert pa.append_rows("C0_champion_mirror", [close], tmp_path) == 1
        state = pa.ledger_state("C0_champion_mirror", tmp_path)
        assert state["A-BULL-1"]["open"] is not None
        assert state["A-BULL-1"]["close"]["outcome"] == "T1_HIT"

    def test_a_corrupt_line_never_kills_the_file(self, tmp_path, nightly):
        pa.append_rows("C0_champion_mirror", [_open("A-BULL-1")], tmp_path)
        with pa.ledger_path("C0_champion_mirror", tmp_path).open("a") as fh:
            fh.write("{ not json\n")
        assert len(pa.read_ledger("C0_champion_mirror", tmp_path)) == 1

    def test_absent_ledger_reads_empty(self, tmp_path):
        assert pa.read_ledger("C0_champion_mirror", tmp_path) == []

    def test_grading_closes_an_open_shadow_plan(self, tmp_path, nightly):
        pa.append_rows("C0_champion_mirror", [_open("A01-BULL-20260501")], tmp_path)
        state = pa.ledger_state("C0_champion_mirror", tmp_path)
        policy = pa._POLICY_BY_KEY["C0_champion_mirror"]
        closes = pa.grade_open_plans(
            policy, state, asof="2026-06-30",
            prices=FakePrices({"A01": _closes([116.0] * 5)}),
        )
        assert len(closes) == 1 and closes[0]["outcome"] == "T1_HIT"

    def test_grading_skips_a_plan_already_closed(self, tmp_path, nightly):
        pa.append_rows("C0_champion_mirror", [_open("A01-BULL-20260501")], tmp_path)
        pa.append_rows("C0_champion_mirror", [pa.close_row(
            "C0_champion_mirror", {"id": "A01-BULL-20260501", "asset": "A01"},
            {"outcome": "EXPIRED", "stock_result_pct": -1.0,
             "close_date": "2026-06-15", "days_held": 45, "sessions_held": 45},
            asof="2026-06-15")], tmp_path)
        state = pa.ledger_state("C0_champion_mirror", tmp_path)
        policy = pa._POLICY_BY_KEY["C0_champion_mirror"]
        assert pa.grade_open_plans(
            policy, state, asof="2026-06-30",
            prices=FakePrices({"A01": _closes([116.0] * 5)}),
        ) == []


# --------------------------------------------------------------------------- #
# 9. Scoreboard — schema, authority, validity, plain words.                    #
# --------------------------------------------------------------------------- #
def _seed_closed(root: Path, policy: str, results: list[float], night="2026-05-01"):
    rows = []
    for i, r in enumerate(results):
        pid = f"S{i:03d}-BULL-20260501"
        rows.append(_open(pid, night=night, policy=policy))
        rows.append({
            "schema": pa.LEDGER_SCHEMA, "kind": "close", "policy": policy, "id": pid,
            "asset": f"S{i:03d}", "signal_date": FIXTURE_ASOF,
            "close_date": "2026-06-15",
            "outcome": "T1_HIT" if r > 0 else "EXPIRED",
            "stock_result_pct": r, "option_result_pct": None,
            "days_held": 45, "sessions_held": 30, "asof": "2026-06-15",
        })
    pa.append_rows(policy, rows, root, force=True)


class TestScoreboard:
    def test_schema_and_authority(self, tmp_path):
        board = pa.build_scoreboard(asof=FIXTURE_ASOF, root=tmp_path)
        assert board["schema"] == pa.SCOREBOARD_SCHEMA
        assert board["tier"] == "display"
        auth = board["authority"]
        assert auth["tier"] == "display"
        for key in ("may_rank", "may_gate", "may_size", "may_escalate"):
            assert auth[key] is False, key

    def test_every_policy_has_a_block(self, tmp_path):
        board = pa.build_scoreboard(asof=FIXTURE_ASOF, root=tmp_path)
        assert [b["policy"] for b in board["policies"]] == list(pa.POLICY_KEYS)

    def test_empty_ledgers_print_nulls_not_zeros(self, tmp_path):
        board = pa.build_scoreboard(asof=FIXTURE_ASOF, root=tmp_path)
        block = board["policies"][0]
        assert block["n_closed"] == 0
        assert block["win_rate_pct"] is None
        assert block["avg_pct"] is None
        assert block["readable"] is False

    def test_stats_and_expired_share(self, tmp_path):
        _seed_closed(tmp_path, "C0_champion_mirror", [10.0, -5.0, -5.0, -10.0])
        board = pa.build_scoreboard(asof=FIXTURE_ASOF, root=tmp_path)
        block = next(b for b in board["policies"] if b["policy"] == "C0_champion_mirror")
        assert block["n_closed"] == 4
        assert block["win_rate_pct"] == 25.0
        assert block["avg_pct"] == -2.5
        assert block["expired_share_pct"] == 75.0

    def test_headline_is_withheld_until_enough_closed(self, tmp_path):
        _seed_closed(tmp_path, "C0_champion_mirror", [1.0] * (pa.HEADLINE_MIN_CLOSED - 1))
        board = pa.build_scoreboard(asof=FIXTURE_ASOF, root=tmp_path)
        block = next(b for b in board["policies"] if b["policy"] == "C0_champion_mirror")
        assert block["readable"] is False
        assert "too early to read" in block["reading"]

    def test_headline_opens_at_the_threshold(self, tmp_path):
        _seed_closed(tmp_path, "C0_champion_mirror", [1.0] * pa.HEADLINE_MIN_CLOSED)
        board = pa.build_scoreboard(asof=FIXTURE_ASOF, root=tmp_path)
        block = next(b for b in board["policies"] if b["policy"] == "C0_champion_mirror")
        assert block["readable"] is True

    def test_selection_policy_uses_same_cohort_comparison(self, tmp_path):
        _seed_closed(tmp_path, "C0_champion_mirror", [-10.0, -10.0])
        _seed_closed(tmp_path, "C1_buy_soon_first", [0.0, 10.0])
        board = pa.build_scoreboard(asof=FIXTURE_ASOF, root=tmp_path)
        block = next(b for b in board["policies"] if b["policy"] == "C1_buy_soon_first")
        assert "same-cohort" in block["vs_champion_basis"]
        assert block["vs_champion"]["shared_nights"] == 1
        assert block["vs_champion"]["diff_pp"] == 15.0

    def test_a_policy_with_no_shared_nights_reports_nulls(self, tmp_path):
        _seed_closed(tmp_path, "C0_champion_mirror", [-10.0], night="2026-05-01")
        _seed_closed(tmp_path, "C1_buy_soon_first", [5.0], night="2026-07-01")
        board = pa.build_scoreboard(asof=FIXTURE_ASOF, root=tmp_path)
        block = next(b for b in board["policies"] if b["policy"] == "C1_buy_soon_first")
        assert block["vs_champion"]["shared_nights"] == 0
        assert block["vs_champion"]["diff_pp"] is None

    def test_closure_policy_uses_paired_comparison(self, tmp_path):
        """C6 shares plan ids with C0, so the comparison must difference each plan."""
        _seed_closed(tmp_path, "C0_champion_mirror", [-10.0, -6.0])
        _seed_closed(tmp_path, "C6_time_stop_21", [-4.0, -6.0])
        board = pa.build_scoreboard(asof=FIXTURE_ASOF, root=tmp_path)
        block = next(b for b in board["policies"] if b["policy"] == "C6_time_stop_21")
        assert "per-plan paired" in block["vs_champion_basis"]
        assert block["vs_champion"]["n_paired"] == 2
        assert block["vs_champion"]["avg_diff_pp"] == 3.0
        assert block["vs_champion"]["better"] == 1
        assert block["vs_champion"]["same"] == 1

    def test_champion_block_has_no_self_comparison(self, tmp_path):
        board = pa.build_scoreboard(asof=FIXTURE_ASOF, root=tmp_path)
        block = next(b for b in board["policies"] if b["policy"] == pa.CHAMPION_KEY)
        assert "vs_champion" not in block

    def test_standing_line_and_registration_are_present(self, tmp_path):
        board = pa.build_scoreboard(asof=FIXTURE_ASOF, root=tmp_path)
        assert board["standing_line"] == pa.STANDING_LINE_EN
        assert "operator ratification" in board["standing_line"]
        assert board["registration"] == pa.REGISTRATION_DOC

    def test_no_banned_vocabulary_anywhere_in_the_payload(self, tmp_path):
        _seed_closed(tmp_path, "C0_champion_mirror", [1.0, -1.0])
        board = pa.build_scoreboard(asof=FIXTURE_ASOF, root=tmp_path)
        blob = json.dumps(board, ensure_ascii=False).lower()
        for banned in ("validated", "已验证", "falsifier", "refuted", "证伪"):
            assert banned not in blob, banned

    def test_payload_is_json_serialisable(self, tmp_path):
        board = pa.build_scoreboard(asof=FIXTURE_ASOF, root=tmp_path)
        json.dumps(board, allow_nan=False)


# --------------------------------------------------------------------------- #
# 10. Fences — nothing in the pick chain may read Arena output.                #
# --------------------------------------------------------------------------- #
PICK_CHAIN = (
    "engine/prophet_bridge.py",
    "engine/us_board_rank.py",
    "scripts/build_prophet.py",
)

#: Reading any of these from the pick chain would let a shadow result reach a live plan.
ARENA_OUTPUT_TOKENS = (
    "prophet_arena.json",
    "data/prophet_arena",
    "arena_dir",
    "ledger_path",
    "scoreboard_path",
    "read_ledger",
    "ledger_state",
    "build_scoreboard",
    "replay_closure",
)


class TestImportFence:
    def test_bridge_and_rank_never_mention_the_arena(self):
        for rel in ("engine/prophet_bridge.py", "engine/us_board_rank.py"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            assert "prophet_arena" not in text, rel

    def test_build_prophet_imports_only_the_hook(self):
        """The one permitted coupling: build_prophet CALLS run_arena and nothing else.

        AST, not grep: importing ``read_ledger`` or ``build_scoreboard`` here would be the
        actual defect, and a name check catches it where a text search over a file that
        legitimately DISCUSSES the arena in comments cannot.
        """
        import ast

        tree = ast.parse((ROOT / "scripts" / "build_prophet.py").read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").endswith(
                "prophet_arena"
            ):
                imported.update(alias.name for alias in node.names)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.endswith("prophet_arena"), (
                        "build_prophet must import the hook by name, not the whole module"
                    )
        assert imported == {"run_arena"}, imported

    def test_no_pick_chain_module_names_arena_output_in_runtime_code(self):
        """No pick-chain module may carry an Arena output path as a runtime string.

        Comments are absent from the AST entirely, so a comment explaining the hook is
        fine — building a path to an Arena ledger or scoreboard is not.
        """
        import ast

        for rel in PICK_CHAIN:
            tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
            docstrings = {
                id(node.body[0].value)
                for node in ast.walk(tree)
                if isinstance(
                    node,
                    (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
                )
                and node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            }
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and id(node) not in docstrings
                ):
                    for token in ARENA_OUTPUT_TOKENS:
                        assert token not in node.value, f"{rel} names {token!r}"

    def test_no_pick_chain_module_calls_an_arena_reader(self):
        """Attribute-level fence: not even ``pa.read_ledger(...)`` may appear."""
        import ast

        readers = {"read_ledger", "ledger_state", "build_scoreboard", "scoreboard_path",
                   "arena_dir", "replay_closure"}
        for rel in PICK_CHAIN:
            tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute):
                    assert node.attr not in readers, f"{rel} calls {node.attr}"
                if isinstance(node, ast.Name):
                    assert node.id not in readers, f"{rel} references {node.id}"

    def test_the_arena_never_names_a_live_plan_path_in_EXECUTABLE_code(self):
        """A live path may be DISCUSSED in a docstring but must never be a runtime string.

        Grepping the raw text would fail on the module's own prose (it cites
        data/prophet/ledger.jsonl as the record that motivates the harness), so this walks
        the AST and inspects only string constants that are NOT docstrings.
        """
        import ast

        source = (ROOT / "engine" / "prophet_arena.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(
                node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            )
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        }
        # Paths, not provenance labels: "us_standouts_buy_lane" is a source_engines tag on
        # a shadow plan and is fine — reading the ARTIFACT (us_standouts.json) is not, since
        # the Arena must grade the in-memory dict the live path used, never a re-read file.
        forbidden = ("site/prophet", "data/prophet/", "us_standouts.json")
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
            ):
                for token in forbidden:
                    assert token not in node.value, f"runtime string names {token!r}"

    def test_a_nightly_run_creates_no_file_outside_the_arena_paths(
        self, standouts, tmp_path, monkeypatch
    ):
        """The behavioural half of the fence: what the Arena actually touches on disk."""
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        monkeypatch.setattr(
            "engine.prophet_doors.door_w_candidates",
            lambda root=None: {"candidates": [], "disclosure": {}},
            raising=True,
        )
        monkeypatch.setattr(
            pa.AtlasGate, "_evaluate", lambda self, t: (True, "weekly_align_class")
        )
        pa.run_arena(
            standouts, asof=FIXTURE_ASOF, existing_ids=set(),
            repo_root=tmp_path, write=True, tilt_inputs=None,
        )
        written = sorted(
            p.relative_to(tmp_path).as_posix()
            for p in tmp_path.rglob("*") if p.is_file()
        )
        assert written, "the run wrote nothing at all"
        for rel in written:
            assert rel.startswith("data/prophet_arena/") or rel == (
                "site/stockdata/prophet_arena.json"
            ), rel

    def test_every_policy_is_frozen_and_unique(self):
        assert len(pa.POLICY_KEYS) == len(set(pa.POLICY_KEYS))
        assert pa.CHAMPION_KEY in pa.POLICY_KEYS
        for policy in pa.POLICIES:
            assert policy.rationale.strip(), policy.key
            assert policy.grain in ("selection", "closure"), policy.key

    def test_only_the_closure_policy_carries_a_closure_knob(self):
        for policy in pa.POLICIES:
            if policy.grain == "selection":
                assert policy.time_stop_sessions is None, policy.key
            else:
                assert policy.time_stop_sessions == pa.TIME_STOP_SESSIONS, policy.key

    def test_registration_document_exists_and_freezes_the_same_policies(self):
        doc = (ROOT / "research" / "PROPHET_ARENA_REGISTRATION.md").read_text(
            encoding="utf-8"
        )
        for key in pa.POLICY_KEYS:
            assert key in doc, key


# --------------------------------------------------------------------------- #
# 11. End-to-end, on a temporary root.                                         #
# --------------------------------------------------------------------------- #
class TestRunArena:
    def test_dry_run_writes_nothing(self, standouts, tmp_path, monkeypatch):
        monkeypatch.delenv("COLLECT_LANE", raising=False)
        monkeypatch.setattr(
            "engine.prophet_doors.door_w_candidates",
            lambda root=None: {"candidates": [], "disclosure": {}},
            raising=True,
        )
        board = pa.run_arena(
            standouts, asof=FIXTURE_ASOF, existing_ids=set(),
            repo_root=tmp_path, write=False, tilt_inputs=None,
        )
        assert board["schema"] == pa.SCOREBOARD_SCHEMA
        assert not pa.arena_dir(tmp_path).exists()

    def test_nightly_run_stamps_every_policy_and_flags_a_mismatch(
        self, standouts, tmp_path, monkeypatch, nightly
    ):
        monkeypatch.setattr(
            "engine.prophet_doors.door_w_candidates",
            lambda root=None: {"candidates": [], "disclosure": {}},
            raising=True,
        )
        monkeypatch.setattr(
            pa.AtlasGate, "_evaluate", lambda self, t: (True, "weekly_align_class")
        )
        board = pa.run_arena(
            standouts, asof=FIXTURE_ASOF, existing_ids=set(),
            live_plan_ids={"NOT-THE-SAME-PLAN"},
            repo_root=tmp_path, write=True, tilt_inputs=None,
        )
        assert board["harness_validity"]["harness_ok"] is False
        assert board["harness_validity"]["c0_mismatch_count"] > 0
        for key in pa.POLICY_KEYS:
            assert pa.ledger_path(key, tmp_path).exists(), key
        assert pa.scoreboard_path(tmp_path).exists()
        assert (tmp_path / "site" / "stockdata" / "prophet_arena.json").exists()

    def test_a_second_nightly_run_appends_nothing_new(
        self, standouts, tmp_path, monkeypatch, nightly
    ):
        monkeypatch.setattr(
            "engine.prophet_doors.door_w_candidates",
            lambda root=None: {"candidates": [], "disclosure": {}},
            raising=True,
        )
        monkeypatch.setattr(
            pa.AtlasGate, "_evaluate", lambda self, t: (True, "weekly_align_class")
        )
        kw = dict(
            asof=FIXTURE_ASOF, existing_ids=set(), repo_root=tmp_path,
            write=True, tilt_inputs=None,
        )
        pa.run_arena(standouts, **kw)
        before = pa.ledger_path(pa.CHAMPION_KEY, tmp_path).read_text(encoding="utf-8")
        board = pa.run_arena(standouts, **kw)
        after = pa.ledger_path(pa.CHAMPION_KEY, tmp_path).read_text(encoding="utf-8")
        assert before == after
        assert board["tonight"]["policies"][pa.CHAMPION_KEY]["ledger_rows_appended"] == 0

    def test_c0_matching_live_ids_reports_a_clean_harness(
        self, standouts, tmp_path, monkeypatch, nightly
    ):
        monkeypatch.setattr(
            "engine.prophet_doors.door_w_candidates",
            lambda root=None: {"candidates": [], "disclosure": {}},
            raising=True,
        )
        # run_arena caps at pb.N_CANDIDATES, so the "live" set this mirror is checked
        # against must use the SAME cap — a hardcoded 12 here silently asserted a
        # mismatch the moment the champion cap moved (A1: 12 -> 16).
        rows, _ = pa.select_for_policy(
            "C0_champion_mirror", standouts, cap=pb.N_CANDIDATES)
        live = {pb._make_id(t, "BULL", FIXTURE_ASOF) for t in _tickers(rows)}
        board = pa.run_arena(
            standouts, asof=FIXTURE_ASOF, existing_ids=set(), live_plan_ids=live,
            repo_root=tmp_path, write=True, tilt_inputs=None,
        )
        assert board["harness_validity"]["harness_ok"] is True
        assert board["harness_validity"]["missing_from_mirror"] == []
        assert board["harness_validity"]["extra_in_mirror"] == []
