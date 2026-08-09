"""tests/test_prophet_anticipation_intake.py — ANTICIPATION A1 + §6.9 R3 acceptance.

WHAT THIS PINS
--------------
The two halves of the US Prophet intake change, each named for the case it was
chartered by:

  A1  status-class admission (the patience cohort can originate a plan at all), the
      recorded down-direction refusal, the era + admission-class stamps, the frozen
      legacy shadow ledger and its production-call-path lane gate, and the
      publication-lag property.
  R3  structure-anchored entry zones on every plan — the NVDA wait_reset acceptance,
      the ADAM reset-band acceptance, and the V-bottom zone-with-expiry-to-starter
      conversion — plus the EARLY-TURN starter tier's context conditioning.

FIXTURE DISCIPLINE
------------------
Nothing here is anchored to the wall clock: every artifact date and run asof is
supplied by the test, so no case can date-bomb (the #5065 pattern).  The synthetic
price series are shaped for the property under test and named for the shape.  The
one exception is the committed-artifact disposition test, which is explicitly a read
of tonight's board and SKIPS when the artifact is absent.

Run: .venv/bin/python -m pytest tests/test_prophet_anticipation_intake.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import prophet_bridge as pb  # noqa: E402
from engine import us_early_turn as et  # noqa: E402
from engine import us_leader_pullback as lp  # noqa: E402
import scripts.build_prophet as bp  # noqa: E402

ASOF = "2026-07-02"           # a Thursday NYSE session
COMMITTED = ROOT / "site" / "factordata" / "us_standouts.json"


# --------------------------------------------------------------------------- #
# Fixture builders                                                             #
# --------------------------------------------------------------------------- #
def _buy(
    ticker: str,
    *,
    status: str = "partial",
    dir_: str = "up",
    band: str = "neutral",
    act_level: int = 3,
    score: int = 70,
    priority: float = 80.0,
    spot: float = 100.0,
    zone_low: float | None = None,
    zone_high: float | None = None,
    chase_above: float | None = None,
    lane: str = "continuation",
    tier: str | None = "T2",
    anchor: str | None = ASOF,
    opens_hi: int | None = None,
) -> dict:
    """One ``us_standouts.json["buy"]`` row, shaped like the live artifact."""
    row: dict = {
        "ticker": ticker,
        "dir": dir_,
        "lane": lane,
        "prophet": {"version": "us_prophet_v1", "score": priority},
        "conviction": {"score": score, "band": band, "drivers": ["momentum"],
                       "cautions": ["macro risk"], "trust_tier": {"en": "tier-2"}},
        "entry_signal": {
            "act_level": act_level,
            "status": status,
            "spot": spot,
            "atr_pct": 2.0,
            "entry_grade": "solid",
            "buy_zone": {
                "low": zone_low if zone_low is not None else spot * 0.97,
                "high": zone_high if zone_high is not None else spot,
                "pct_from_spot": -1.5,
            },
            "chase_above": chase_above if chase_above is not None else spot * 1.01,
            "timing": {"opens_in_days_lo": 0, "opens_in_days_hi": opens_hi},
        },
        "hold": {"state": "HOLD", "anchor": anchor, "invalidation": spot * 0.9},
        "signal_asof": ASOF,
    }
    if tier is not None:
        row["signal"] = {"tier_cascade": tier}
    return row


def _standouts(buys: list[dict], *, gate_go: bool = False, as_of: str = ASOF,
               price_through: str | None = None) -> dict:
    return {
        "as_of": as_of,
        "staleness": {
            "price_through": price_through or as_of,
            "delayed": False, "unknown": False, "basis": "panel_majority",
            "inputs": {"panel": {"mixed_vintage": False}},
        },
        "gate_go": gate_go,
        "buy": buys,
    }


def _write(tmp_path: Path, standouts: dict) -> Path:
    path = tmp_path / "us_standouts.json"
    path.write_text(json.dumps(standouts), encoding="utf-8")
    return path


def _originate(tmp_path: Path, standouts: dict, *, asof: str = ASOF,
               stats: dict | None = None) -> list[dict]:
    return pb.originate_plans(
        standouts_path=_write(tmp_path, standouts),
        asof=asof,
        existing_ids=set(),
        thetadata_store=None,
        active_keys=set(),
        intake_stats=stats if stats is not None else {},
    )


def _tickers(rows: list[dict]) -> list[str]:
    return [str(r.get("ticker") or r.get("asset")) for r in rows]


# --------------------------------------------------------------------------- #
# Price-series shapes, each named for the property it carries                  #
# --------------------------------------------------------------------------- #
def _bars(closes: list[float], end: str = ASOF) -> pd.DataFrame:
    """An OHLCV frame whose LAST bar is ``end`` — so a PIT slice at the run's asof
    keeps the whole series and the shape under test is the shape that is read."""
    idx = pd.bdate_range(end=end, periods=len(closes))
    close = pd.Series(closes, index=idx, dtype="float64")
    return pd.DataFrame({
        "open": close, "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": 1_000_000.0,
    }, index=idx)


def _noise(n: int, seed: int, amp: float = 0.008) -> np.ndarray:
    """Deterministic multiplicative wiggle.

    LOAD-BEARING, not decoration: StochRSI is a stochastic OF RSI, and a perfectly
    smooth exponential has a constant RSI, so its 14-bar high and low coincide and
    every %K/%D reading is NaN.  A frictionless fixture measures nothing.
    """
    return np.exp(np.random.default_rng(seed).normal(0.0, amp, n))


def _stretched_series(n: int = 300, impulse: int = 8, seed: int = 11) -> pd.DataFrame:
    """A noisy uptrend ending in a vertical impulse — %K pinned high on daily AND 3D."""
    base = n - impulse
    trend = np.array([50.0 * (1.003 ** i) for i in range(base)])
    closes = list(trend * _noise(base, seed))
    top = closes[-1]
    closes += [top * (1.02 ** i) for i in range(1, impulse + 1)]
    return _bars(closes)


def _reset_series(n: int = 300, seed: int = 13) -> pd.DataFrame:
    """A leader that ran to 118 and is 6 bars into a controlled ~8% retrace."""
    pull = (0.985, 0.972, 0.962, 0.955, 0.951, 0.949)
    base = n - len(pull)
    trend = np.array([1.0 * (1.004 ** i) for i in range(base)])
    closes = list(trend * _noise(base, seed))
    closes = [c * 118.0 / closes[-1] for c in closes]      # the pullback HIGH is 118
    top = closes[-1]
    closes += [top * f for f in pull]
    return _bars(closes)


def _v_bottom_series(n: int = 300, seed: int = 19) -> pd.DataFrame:
    """A washout then a vertical recovery that never revisits the band."""
    half = n // 2
    down = np.array([100.0 * (0.992 ** i) for i in range(half)])
    closes = list(down * _noise(half, seed))
    low = closes[-1]
    closes += [low * (1.02 ** i) for i in range(1, n - half + 1)]
    return _bars(closes)


def _turning_series(n_down: int = 200, n_up: int = 2, seed: int = 17) -> pd.DataFrame:
    """A washed-out decline followed by a fresh upturn: %K crosses up from a low
    reading while the RSI-MACD histogram is still curling."""
    down = np.array([100.0 * (0.99 ** i) for i in range(n_down)])
    closes = list(down * _noise(n_down, seed, 0.010))
    low = closes[-1]
    closes += [low * (1.015 ** i) for i in range(1, n_up + 1)]
    return _bars(closes)


def _leader_reset_series(n: int = 320, seed: int = 13) -> pd.DataFrame:
    """ONE series that is BOTH halves of the leader-pullback admission.

    A high-RS leader that ran to 118, took a controlled ~7% retrace over ten sessions
    with the 200dMA intact, and turned up on the last two — so ``engine.us_leader_pullback``
    grades it RESET_TURN (an OPEN episode) while the EARLY-TURN dot signature fires on
    the daily and 2D grids.  Two fixtures glued together would prove the wiring; one
    series proves the CASE, which is what §6.9 R4 is about.
    """
    pull = (0.985, 0.972, 0.960, 0.950, 0.941, 0.933, 0.928, 0.924, 0.921, 0.919)
    up = (1.010, 1.014)
    base = n - len(pull) - len(up)
    trend = np.array([1.0 * (1.004 ** i) for i in range(base)])
    closes = list(trend * _noise(base, seed))
    closes = [c * 118.0 / closes[-1] for c in closes]      # the pullback HIGH is 118
    top = closes[-1]
    closes += [top * f for f in pull]
    low = closes[-1]
    closes += [low * f for f in up]
    return _bars(closes)


# =========================================================================== #
# 1. A1 — status-class admission                                              #
# =========================================================================== #
class TestStatusClassAdmission:
    def test_bounce_wait_on_caution_tone_is_admitted(self, tmp_path):
        """THE CASE THIS CHANGE EXISTS FOR.

        Every ``bounce_wait`` row on the live board carries ``dir="caution"`` (the
        COUNTERTREND BOUNCE state emits that tone), and its ``act_level`` is 0.  Under
        the pre-A1 rule the literal ``dir == "up"`` filter admitted ZERO of them and
        the act gate would have refused them anyway, so the US board was mechanically
        incapable of planning the patience cohort.
        """
        rows = [_buy("BOUNCE", status="bounce_wait", dir_="caution", act_level=0)]
        stats: dict = {}
        admitted = pb.select_candidates(_standouts(rows), n=None, stats=stats)
        assert _tickers(admitted) == ["BOUNCE"]
        assert stats["admitted_by_class"] == {"patience": 1, "confirmation": 0}

        # And the OLD gate — still frozen, still running for the shadow ledger —
        # must continue to refuse it, or the comparison contract compares nothing.
        assert pb.legacy_admitted(_standouts(rows)) == []

    @pytest.mark.parametrize("status", sorted(pb.PATIENCE_STATUSES))
    def test_every_patience_status_admits_at_act_level_zero(self, status):
        rows = [_buy("T", status=status, dir_="caution", act_level=0)]
        assert len(pb.select_candidates(_standouts(rows), n=None)) == 1

    @pytest.mark.parametrize("status", ["extended", "topping", "buy_soon",
                                        "await_confluence", "watch", "blocked"])
    def test_refused_statuses_stay_refused_on_any_tone(self, status):
        """`extended`/`topping` are the anti-chase guard; `buy_soon` graded worst.

        The tone widening to `caution` is only safe BECAUSE the status gate refuses
        these — `caution` is shared with TOP WATCH, the chase-risk cohort.
        """
        for tone in ("up", "caution"):
            rows = [_buy("T", status=status, dir_=tone, act_level=3)]
            stats: dict = {}
            assert pb.select_candidates(_standouts(rows), n=None, stats=stats) == []
            assert stats["refused_status"] == {status: 1}

    def test_down_direction_is_refused_and_the_refusal_is_disclosed(self, tmp_path):
        """BOTTOM WATCH is arguably the earliest patience state of all, and it is
        REFUSED for plans by recorded ruling (§6.7) — a real widening that belongs to
        a ruling, not to this change.  What the ruling requires is that the refusal be
        VISIBLE rather than silent."""
        rows = [
            _buy("DOWNER", status="bounce_wait", dir_="down", act_level=0),
            _buy("KEEPER", status="bounce_wait", dir_="caution", act_level=0),
        ]
        stats: dict = {}
        plans = _originate(tmp_path, _standouts(rows), stats=stats)
        assert _tickers(plans) == ["KEEPER"]
        assert stats["refused_direction"] == {"down": 1}
        assert "down" not in pb.ADMITTED_DIRECTIONS
        assert "down" in pb.REFUSED_DIRECTIONS

    def test_an_unknown_status_word_is_refused_and_NAMED(self):
        """A board that renamed a status must not empty the intake silently."""
        rows = [_buy("T", status="teleporting")]
        stats: dict = {}
        assert pb.select_candidates(_standouts(rows), n=None, stats=stats) == []
        assert stats["unknown_status"] == 1
        assert stats["unknown_status_values"] == ["teleporting"]

    def test_the_disposition_is_lossless(self, tmp_path):
        """Every buy row lands in exactly one bucket — admitted or a named refusal."""
        rows = [
            _buy("A", status="buy_now"),
            _buy("B", status="bounce_wait", dir_="caution"),
            _buy("C", status="buy_soon"),
            _buy("D", status="partial", dir_="down"),
            _buy("E", status="partial", band="low"),
            _buy("F", status="partial", tier="T4"),
            _buy("G", status="partial"),
        ]
        rows[6]["entry_signal"] = None
        stats: dict = {}
        admitted = pb.select_candidates(_standouts(rows), n=None, stats=stats)
        accounted = (
            len(admitted)
            + sum(stats["refused_status"].values())
            + sum(stats["refused_direction"].values())
            + sum(stats["refused_tier"].values())
            + stats["refused_band_low"]
            + stats["refused_no_entry_signal"]
        )
        assert accounted == stats["buy_rows"] == len(rows)


# =========================================================================== #
# 2. A1 — era and class stamps                                                #
# =========================================================================== #
class TestEraAndClassStamps:
    def test_every_plan_carries_the_era_and_its_admission_class(self, tmp_path):
        rows = [
            _buy("PAT", status="bounce_wait", dir_="caution", act_level=0, priority=90),
            _buy("CONF", status="buy_now", priority=80),
        ]
        plans = _originate(tmp_path, _standouts(rows))
        assert len(plans) == 2
        for plan in plans:
            assert plan["selection_era"] == pb.SELECTION_ERA
            assert plan["admission_class"] in (
                pb.ADMISSION_CLASS_PATIENCE, pb.ADMISSION_CLASS_CONFIRMATION,
                pb.ADMISSION_CLASS_EARLY_TURN)
            assert plan["entry_status"]
        by_ticker = {p["asset"]: p for p in plans}
        assert by_ticker["PAT"]["admission_class"] == pb.ADMISSION_CLASS_PATIENCE
        assert by_ticker["CONF"]["admission_class"] == pb.ADMISSION_CLASS_CONFIRMATION

    def test_the_era_literal_is_the_chartered_one(self):
        """CHARTERED, not generated: §6.2 fixed this string and the §6.6 measurement
        lane filters on it.  Re-dating it to a build date silently orphans every
        measurement written against the old value."""
        assert pb.SELECTION_ERA == "anticipation-v1-2026-08-08"


# =========================================================================== #
# 3. A1 — the publication-lag property                                        #
# =========================================================================== #
class TestPublicationLagGuard:
    def test_the_clock_contract_makes_a_stale_price_basis_unreachable(self, tmp_path):
        """FIRST FENCE (#5071): a board whose ranked-price vintage trails the run is
        refused OUTRIGHT — every candidate lands in validation_failures with a clock
        reason, and not one plan is published at that price.

        This is why the A1 re-derive branch is not ported: there is nothing to
        re-derive FROM.  The property the forensic asked for is delivered by refusal.
        """
        rows = [_buy("STALE", status="buy_now")]
        stats: dict = {}
        plans = _originate(
            tmp_path,
            _standouts(rows, price_through="2026-05-01"),   # 40+ sessions behind
            stats=stats,
        )
        assert plans == []
        assert stats["validation_failed"] == 1
        assert stats["validation_failures"][0]["stage"] == "clock_provenance"
        assert stats["lossless"] is True

    def test_a_fresh_run_discloses_a_zero_lag_basis_on_every_plan(self, tmp_path):
        rows = [_buy("FRESH", status="buy_now")]
        plans = _originate(tmp_path, _standouts(rows))
        basis = plans[0]["entry_basis"]
        assert basis["state"] == "current"
        assert basis["basis_date"] == ASOF
        assert basis["basis_source"] == "staleness_price_through"
        assert basis["lag"] == 0
        assert basis["max_lag"] == pb.STALE_BASIS_MAX_SESSIONS
        assert basis["era"] == pb.SELECTION_ERA

    def test_the_second_fence_refuses_a_stale_basis_if_the_clock_gate_is_loosened(
            self, tmp_path, monkeypatch):
        """SECOND FENCE, mutation-verified.  With the clock contract neutralised the
        stale-basis refusal must still fire — otherwise this whole property lives in
        one function and a future loosening of that function publishes stale prices
        with nothing to catch it."""
        monkeypatch.setattr(
            pb, "_resolve_origination_clocks",
            lambda **kw: ("2026-07-02", "2026-05-01", []),
        )
        rows = [_buy("STALE", status="buy_now")]
        stats: dict = {}
        plans = _originate(tmp_path, _standouts(rows), stats=stats)
        assert plans == []
        assert len(stats["stale_basis_skipped"]) == 1
        ticker, _, lag = stats["stale_basis_skipped"][0].partition(":")
        assert ticker == "STALE"
        assert int(lag) > pb.STALE_BASIS_MAX_SESSIONS
        assert stats["validation_failures"][0]["stage"] == "stale_entry_basis"

    def test_the_stale_refusal_prints_a_line_start_annotation(
            self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(
            pb, "_resolve_origination_clocks",
            lambda **kw: ("2026-07-02", "2026-05-01", []),
        )
        _originate(tmp_path, _standouts([_buy("STALE", status="buy_now")]))
        lines = [ln for ln in capsys.readouterr().out.splitlines()
                 if "prophet-stale-entry-basis" in ln]
        assert lines, "the stale-basis refusal emitted no annotation"
        # House law: GitHub drops a `::` that does not START the line, which is how
        # five separate alarms shipped dead before #3587.
        assert all(ln.startswith("::warning title=") for ln in lines)


# =========================================================================== #
# 4. R3 — NVDA wait_reset acceptance                                          #
# =========================================================================== #
class TestWaitResetAcceptance:
    def test_nvda_shape_both_extended_yields_a_wait_reset_zone_and_no_chase(
            self, tmp_path, monkeypatch):
        """NVDA ACCEPTANCE (§6.9 R3): when the 3-day signal AND the daily stochastic
        are BOTH stretched, the plan admits only as a wait_reset ZONE plan — the band
        sits below the last print, the chase line never sits above it, and the copy
        carries no market-chase instruction.

        The row is a `buy_now` confirmation deliberately: the board's own status word
        is not enough, because a daily-cycle read can call the window open while both
        stochastics sit at 99.
        """
        prices = _stretched_series()
        state = et.extension_state(prices, ASOF)
        assert state["both_extended"] is True, (
            "the fixture no longer reads as stretched on both timeframes — it cannot "
            "exercise the acceptance")

        monkeypatch.setattr(pb, "_load_price_history", lambda t: prices)
        spot = float(prices["close"].iloc[-1])
        rows = [_buy("NVDA", status="buy_now", spot=spot,
                     zone_low=spot * 0.99, zone_high=spot,
                     chase_above=spot * 1.02)]
        stats: dict = {}
        plans = _originate(tmp_path, _standouts(rows), stats=stats)

        assert len(plans) == 1
        zone = plans[0]["entry_zone"]
        assert zone["zone_class"] == pb.ZONE_CLASS_WAIT_RESET
        assert zone["stance"] == pb.ZONE_STANCE_WAIT
        assert zone["high"] < spot, "a wait_reset band must sit BELOW the last print"
        # Compared against the PLAN's entry, not the raw float: both are rounded to
        # 4dp on the way out, so a raw-float comparison would trip on the rounding.
        assert zone["chase_above"] <= plans[0]["entry"], (
            "wait_reset may never chase above the last print")
        assert plans[0]["trigger"] <= plans[0]["entry"]
        assert stats["wait_reset"] == ["NVDA"]
        assert stats["zone_class_counts"][pb.ZONE_CLASS_WAIT_RESET] == 1

        joined = " ".join(plans[0]["what_to_do_now"]).lower()
        assert "wait for a pullback" in joined
        assert "stretched" in joined
        assert "no entry at" in joined
        assert plans[0]["what_to_do_now_zh"], "the ZH half must never be empty"
        assert "等待价格回落" in "".join(plans[0]["what_to_do_now_zh"])

    def test_the_disclosed_entry_is_still_the_point_in_time_close(
            self, tmp_path, monkeypatch):
        """A zone plan WAITS at the band; it does not pretend it filled there.

        The plan's `entry` stays the price_basis close — inventing a fill at the band
        would fabricate a track record the tape never gave us.
        """
        prices = _stretched_series()
        monkeypatch.setattr(pb, "_load_price_history", lambda t: prices)
        spot = float(prices["close"].iloc[-1])
        plans = _originate(tmp_path, _standouts(
            [_buy("NVDA", status="buy_now", spot=spot)]))
        assert plans[0]["entry"] == round(spot, 4)
        assert plans[0]["entry_zone"]["high"] < plans[0]["entry"]
        assert plans[0]["price_basis_date"] == ASOF


# =========================================================================== #
# 5. R3 — ADAM reset-band acceptance (the leader-pullback zone law)            #
# =========================================================================== #
def _organ_row(prices: pd.DataFrame, *, rs: float = 0.95) -> dict:
    """A REAL ``engine.us_leader_pullback`` row for ``prices`` — never a hand dict.

    The organ needs a PIT CROSS-SECTIONAL ``rs_pct`` it refuses to fetch itself, so the
    test supplies one; every other field (``state``, ``asof``, ``pullback_high``,
    ``null_reason``, ``construction_era``) is the organ's own output.  Feeding the seam
    a hand-written contract is exactly how the pre-#5007 stand-in passed for the wrong
    reason — this fixture cannot drift from the organ, because it IS the organ.
    """
    close = prices["close"]
    return lp.latest(close, rs_pct=pd.Series(rs, index=close.index),
                     volume=prices["volume"])


def _coverage(**rows: dict) -> dict[str, dict]:
    """A published leader-pullback coverage map, keyed the way the loader keys it."""
    return {ticker.upper(): row for ticker, row in rows.items()}


class TestLeaderPullbackContextBackend:
    """§6.9 R4 — the leader-pullback CONTEXT backend (#5007 consumed as-is)."""

    def test_the_context_states_are_the_ORGANS_own_vocabulary(self):
        """The predicate is "uptrend intact + controlled reset", spelled in the organ's
        words: an OPEN pullback episode, before the resumption print.

        RESUMED is excluded for the reason CONFIRMED is excluded from the washout half
        — price already left the top of the entry zone, so the starter window is the
        thing that already opened.  LEADER is excluded because an intact uptrend with
        NO pullback in progress is a chase licence, not a starter licence.
        """
        assert et.LEADER_PULLBACK_CONTEXT_STATES == {
            lp.STATE_PULLBACK, lp.STATE_RESET_TURN}
        assert et.LEADER_PULLBACK_CONTEXT_STATES <= set(lp.STATES)
        for excluded in (lp.STATE_LEADER, lp.STATE_RESUMED, lp.STATE_NONE):
            assert excluded not in et.LEADER_PULLBACK_CONTEXT_STATES

    def test_an_open_controlled_pullback_IS_leader_context(self):
        """The ADAM shape, graded by the organ itself: a leader 6 bars into a ~5%
        retrace with the 200dMA intact reads PULLBACK, and PULLBACK is context."""
        row = _organ_row(_reset_series())
        assert row["state"] == lp.STATE_PULLBACK, (
            "the fixture no longer produces an open episode — the case is gone")
        ctx = et.leader_pullback_context("ADAM", states=_coverage(ADAM=row))
        assert ctx["leader_pullback"] is True
        assert ctx["state"] == lp.STATE_PULLBACK
        assert ctx["source"] == "us_leader_pullback"
        assert ctx["pullback_high"] == pytest.approx(118.0)
        assert ctx["construction_era"] == lp.CONSTRUCTION_ERA

    def test_a_stretched_leader_with_no_retrace_is_NOT_context(self):
        """The anti-chase half, graded by the organ: a name running vertically reads
        LEADER, and LEADER never licenses a starter."""
        row = _organ_row(_stretched_series())
        assert row["state"] == lp.STATE_LEADER
        ctx = et.leader_pullback_context("NVDA", states=_coverage(NVDA=row))
        assert ctx["leader_pullback"] is False
        assert ctx["source"] == "us_leader_pullback"      # an honest FALSE, not a null
        assert "not an open controlled pullback" in ctx["reason"]

    @pytest.mark.parametrize("state", [lp.STATE_RESUMED, lp.STATE_NONE])
    def test_the_states_after_and_outside_an_episode_never_license(self, state):
        row = dict(_organ_row(_reset_series()), state=state)
        ctx = et.leader_pullback_context("ADAM", states=_coverage(ADAM=row))
        assert ctx["leader_pullback"] is False
        assert ctx["state"] == state

    def test_the_reset_turn_state_licenses_too(self):
        """RESET_TURN graded a NULL as a STANDALONE signal and was retained as a
        CONFLUENCE input — which is this role.  Refusing it here would perversely
        withhold the licence at the exact bar the organ agrees with the signature."""
        row = dict(_organ_row(_reset_series()), state=lp.STATE_RESET_TURN)
        ctx = et.leader_pullback_context("ADAM", states=_coverage(ADAM=row))
        assert ctx["leader_pullback"] is True

    def test_no_published_coverage_is_a_NAMED_null_and_fails_CLOSED(self):
        """A licence that cannot be resolved is not granted — and the absence must be
        VISIBLE, or a monkeypatch of a path nobody walks passes for the wrong reason."""
        ctx = et.leader_pullback_context("ADAM", states={})
        assert ctx["leader_pullback"] is False
        assert ctx["source"] == "unavailable"
        assert "no coverage" in (ctx["reason"] or "")

    def test_a_name_OUTSIDE_the_organs_universe_is_not_leader_context(self):
        """Fail closed on absence: coverage for other names is not coverage for this
        one, and 'the organ never looked' must not read as 'the organ said no'."""
        ctx = et.leader_pullback_context(
            "ADAM", states=_coverage(NVDA=_organ_row(_stretched_series())))
        assert ctx["leader_pullback"] is False
        assert ctx["source"] == "unavailable"
        assert "outside the leader-pullback organ's universe" in (ctx["reason"] or "")

    def test_a_row_the_organ_ITSELF_nulled_is_a_named_null(self):
        """A starved organ read and an honest 'not a leader' must never be the same
        answer — the #4979 ext_z blackout in miniature."""
        row = _organ_row(_turning_series())          # 202 bars, under the 260 floor
        assert row["state"] is None and row["null_reason"]
        ctx = et.leader_pullback_context("TURNER", states=_coverage(TURNER=row))
        assert ctx["leader_pullback"] is False
        assert ctx["source"] == "unavailable"
        assert "needs 260 daily bars" in (ctx["reason"] or "")

    def test_a_state_dated_AFTER_the_price_basis_is_refused_as_a_lookahead(self):
        """PIT law: a context computed on bars the plan could not see is a lookahead no
        downstream test would catch, so the guard lives at the seam."""
        row = _organ_row(_reset_series())
        ctx = et.leader_pullback_context("ADAM", asof="2026-07-01",
                                         states=_coverage(ADAM=row))
        assert ctx["leader_pullback"] is False
        assert ctx["source"] == "unavailable"
        assert "lookahead" in (ctx["reason"] or "")
        # Same row, evaluated ON its own session, is honoured.
        assert et.leader_pullback_context(
            "ADAM", asof=row["asof"], states=_coverage(ADAM=row))["leader_pullback"]

    def test_the_loader_fails_closed_on_absence_and_on_a_foreign_schema(self, tmp_path):
        assert et.load_leader_pullback_states(site_root=tmp_path) == {}
        target = tmp_path / "anticipationdata"
        target.mkdir()
        artifact = target / "us_leader_pullback.json"
        artifact.write_text(json.dumps(
            {"schema": "some_other_organ.v1", "states": {"ADAM": {"state": "PULLBACK"}}}),
            encoding="utf-8")
        assert et.load_leader_pullback_states(site_root=tmp_path) == {}
        artifact.write_text(json.dumps(
            {"schema": lp.SCHEMA, "states": {"adam": {"state": lp.STATE_PULLBACK}}}),
            encoding="utf-8")
        loaded = et.load_leader_pullback_states(site_root=tmp_path)
        assert loaded == {"ADAM": {"state": lp.STATE_PULLBACK}}

    def test_no_publisher_writes_the_artifact_yet_so_a_live_read_is_empty(self):
        """The honest state of the wiring: the organ writes no file, nothing publishes
        the per-run coverage yet, and the loader says so by returning {} rather than
        pretending.  When a publisher lands this becomes a coverage assertion."""
        assert et.load_leader_pullback_states() == {}


class TestLeaderPullbackZoneLaw:
    def test_adam_shape_a_controlled_pullback_zones_at_the_RESET_band(
            self, tmp_path, monkeypatch):
        """ADAM ACCEPTANCE (§6.8(b) zone law, receipt 2026-07-27→08-05): a leader in a
        controlled pullback zones at the RESET BAND with the chase line at the pullback
        high — NEVER the post-pop range.

        The live defect this pins: the board printed ADAM's zone as 9.61-9.82 while
        price was 9.82, i.e. the zone WAS the top of the pop; the constructive entry
        was the 8.40-8.70 reset the dot had marked.  The state and the pullback high
        now come from the real organ (#5007), not from a stand-in.
        """
        prices = _reset_series()
        monkeypatch.setattr(et, "load_leader_pullback_states",
                            lambda *a, **k: _coverage(ADAM=_organ_row(prices)))
        monkeypatch.setattr(pb, "_load_price_history", lambda t: prices)
        spot = float(prices["close"].iloc[-1])

        # The board's own zone is the POST-POP range: low == high == spot.
        rows = [_buy("ADAM", status="buy_now", spot=spot,
                     zone_low=spot, zone_high=spot, chase_above=spot * 1.01)]
        plans = _originate(tmp_path, _standouts(rows))

        zone = plans[0]["entry_zone"]
        assert zone["zone_class"] == pb.ZONE_CLASS_RESET_BAND
        assert zone["stance"] == pb.ZONE_STANCE_WAIT
        assert zone["high"] < spot, (
            "the zone is still the post-pop range — the ADAM defect is unfixed")
        assert zone["chase_above"] == 118.0, "the chase line is the pullback high"
        assert "leader pullback" in zone["basis"]
        assert zone["leader_pullback"]["state"] == lp.STATE_PULLBACK

    def test_without_organ_coverage_the_same_row_keeps_the_board_zone(
            self, tmp_path, monkeypatch):
        """The mutation half: with no published coverage the zone law cannot apply, and
        the plan must say so rather than silently claiming a reset band."""
        prices = _reset_series()
        monkeypatch.setattr(et, "load_leader_pullback_states", lambda *a, **k: {})
        monkeypatch.setattr(pb, "_load_price_history", lambda t: prices)
        spot = float(prices["close"].iloc[-1])
        rows = [_buy("ADAM", status="buy_now", spot=spot,
                     zone_low=spot, zone_high=spot)]
        stats: dict = {}
        plans = _originate(tmp_path, _standouts(rows), stats=stats)
        zone = plans[0]["entry_zone"]
        assert zone["zone_class"] == pb.ZONE_CLASS_ACCUMULATE
        assert stats["leader_pullback_source"] == ["unavailable"]


# =========================================================================== #
# 6. R3 — zone with expiry converts to a starter on a V-bottom                 #
# =========================================================================== #
class TestZoneExpiryToStarter:
    def _plan_with_zone(self, *, conversion_class: str, high: float,
                        expiry: str) -> dict:
        return {
            "id": "T-BULL-20260702", "asset": "T", "price_basis_date": ASOF,
            "entry_zone": {
                "schema": pb.ZONE_SCHEMA, "low": high * 0.98, "high": high,
                "chase_above": high, "zone_class": pb.ZONE_CLASS_RESET_BAND,
                "stance": pb.ZONE_STANCE_WAIT, "price_basis_date": ASOF,
                "expiry_sessions": 10, "expiry_date": expiry,
                "conversion_class": conversion_class,
                "converts_on_expiry": conversion_class == pb.ZONE_CONVERSION_WASHOUT,
            },
        }

    def test_a_washout_class_zone_that_never_filled_CONVERTS_to_a_starter(self):
        """BABA / NVDA V-BOTTOM ACCEPTANCE: a V-shaped washout recovery never
        revisits its band, so letting the zone die would mean the plan misses the
        entire move it correctly anticipated."""
        prices = _v_bottom_series()
        band_top = float(prices["low"].min()) * 1.01     # only the very low touched it
        recovery = prices[prices.index > prices["close"].idxmin()]
        assert float(recovery["low"].min()) > band_top, (
            "the fixture revisits the band — it cannot exercise the V case")

        plan = self._plan_with_zone(
            conversion_class=pb.ZONE_CONVERSION_WASHOUT,
            high=band_top,
            expiry=str(recovery.index[5].date()),
        )
        state = pb.evaluate_entry_zone(plan, recovery, str(recovery.index[-1].date()))
        assert state["state"] == "converted"
        assert state["converted"] is True
        assert state["filled"] is False
        assert state["stance"] == pb.ZONE_STANCE_STARTER

    def test_a_pullback_class_zone_that_never_filled_EXPIRES(self):
        """The class conditioning, from the other side: in an intact uptrend "the
        reset never came" is the premise failing, not a V to chase."""
        prices = _v_bottom_series()
        band_top = float(prices["low"].min()) * 1.01
        recovery = prices[prices.index > prices["close"].idxmin()]
        plan = self._plan_with_zone(
            conversion_class=pb.ZONE_CONVERSION_PULLBACK,
            high=band_top,
            expiry=str(recovery.index[5].date()),
        )
        state = pb.evaluate_entry_zone(plan, recovery, str(recovery.index[-1].date()))
        assert state["state"] == "expired"
        assert state["converted"] is False
        assert state["stance"] == pb.ZONE_STANCE_WAIT

    def test_a_zone_the_tape_traded_into_is_FILLED_not_expired(self):
        prices = _reset_series()
        band_top = float(prices["low"].iloc[-1]) * 1.02
        plan = self._plan_with_zone(
            conversion_class=pb.ZONE_CONVERSION_WASHOUT, high=band_top,
            expiry="2026-01-05",   # long past, so only `filled` can win
        )
        plan["price_basis_date"] = str(prices.index[0].date())
        plan["entry_zone"]["price_basis_date"] = plan["price_basis_date"]
        state = pb.evaluate_entry_zone(plan, prices, str(prices.index[-1].date()))
        assert state["state"] == "filled"
        assert state["filled_date"]

    def test_a_pre_R3_plan_with_no_zone_is_a_named_null(self):
        state = pb.evaluate_entry_zone({"id": "old"}, _reset_series(), ASOF)
        assert state["state"] == "none"
        assert "no entry zone" in state["reason"]

    def test_the_converted_copy_is_starter_vocabulary_in_BOTH_languages(self):
        zone = {"low": 90.0, "high": 95.0, "chase_above": 95.0,
                "zone_class": pb.ZONE_CLASS_RESET_BAND,
                "stance": pb.ZONE_STANCE_WAIT}
        state = {"state": "converted"}
        en = pb._build_what_to_do_now(
            "pre_trigger", 100.0, 100.0, 85.0, 115.0, 130.0,
            entry_zone=zone, zone_state=state)
        zh = pb._build_what_to_do_now_zh(
            "pre_trigger", 100.0, 100.0, 85.0, 115.0, 130.0,
            entry_zone=zone, zone_state=state)
        assert len(en) == len(zh) == 2
        assert "starter-size window" in " ".join(en)
        assert "试探性小仓位" in "".join(zh)
        # VOICE LAW: falsifier/refutation language never reaches a user surface.
        blob = " ".join(en) + "".join(zh)
        for banned in ("falsif", "refut", "证伪", "validated", "已验证"):
            assert banned not in blob.lower()

    def test_zone_copy_is_absent_for_a_plan_with_no_zone(self):
        """Every pre-R3 plan keeps the exact copy it had."""
        assert pb._zone_lines_en(None, None, 100.0, 90.0, 115.0) is None
        assert pb._zone_lines_zh(None, None, 100.0, 90.0, 115.0) is None


# =========================================================================== #
# 7. R3 — the conversion CLASS is conditioned, not universal                   #
# =========================================================================== #
class TestConversionClassConditioning:
    def test_a_bottoming_lane_row_is_washout_class(self):
        klass, evidence = pb.zone_conversion_class(_buy("T", lane="bottoming"))
        assert klass == pb.ZONE_CONVERSION_WASHOUT
        assert "lane=bottoming" in evidence

    def test_a_continuation_lane_row_is_pullback_class(self):
        klass, evidence = pb.zone_conversion_class(_buy("T", lane="continuation"))
        assert klass == pb.ZONE_CONVERSION_PULLBACK

    def test_the_organ_state_overrides_the_lane(self):
        klass, evidence = pb.zone_conversion_class(
            _buy("T", lane="continuation"), washout_context=True)
        assert klass == pb.ZONE_CONVERSION_WASHOUT
        assert "us_basket_turn" in evidence

    def test_the_near_constant_board_flag_is_NOT_an_input(self):
        """MEASURED: `coiled.washout_ctx` is true on 71 of 79 live buy rows.  Reading
        it would make 46 of 47 plans convert — a conversion rule with no class in it.
        """
        row = _buy("T", lane="continuation")
        row["coiled"] = {"washout_ctx": True}
        klass, _ = pb.zone_conversion_class(row)
        assert klass == pb.ZONE_CONVERSION_PULLBACK


# =========================================================================== #
# 8. R3 — EARLY-TURN starter tier                                              #
# =========================================================================== #
class TestEarlyTurnStarterTier:
    def test_the_signature_fires_on_a_cross_up_from_washed_with_a_curling_histogram(
            self):
        sig = et.turn_signature(_turning_series(), timeframe=et.TF_DAILY)
        assert sig["from_washed"] is True
        assert sig["washed_low"] <= et.STOCH_WASHED_MAX
        assert sig["stoch_cross_up"] is True
        assert sig["hist_curling"] is True
        assert sig["fired"] is True

    def test_a_naked_signature_NEVER_admits_without_a_licensing_context(self):
        """§6.8(b) was explicit: four anecdotes do not carry the promotion, only the
        conditional table would.  So the unconditioned variant is not shipped even as
        a display chip."""
        out = et.assess_early_turn("NOBASKET", _turning_series(),
                                   asof=None, membership={}, leader_states={})
        assert out["signature_fired"] is True
        assert out["context_fired"] is False
        assert out["context_sources"] == []
        assert out["fired"] is False
        assert "no licensing context" in out["reason"]

    def test_washout_mature_membership_licenses_the_starter_class(self, tmp_path,
                                                                  monkeypatch):
        membership = {"TURNER": {"state": "TURNING", "basket_id": "b",
                                 "basket_name": "B", "data_session": ASOF}}
        out = et.assess_early_turn("TURNER", _turning_series(), asof=None,
                                   membership=membership, leader_states={})
        assert out["fired"] is True
        assert out["washout"]["washout_mature"] is True
        assert out["context_sources"] == [et.CONTEXT_WASHOUT]

        prices = _turning_series()
        monkeypatch.setattr(pb, "_load_price_history", lambda t: prices)
        monkeypatch.setattr(
            "engine.us_early_turn.load_basket_turn_membership",
            lambda *a, **k: membership)
        monkeypatch.setattr(et, "load_leader_pullback_states", lambda *a, **k: {})
        spot = float(prices["close"].iloc[-1])
        stats: dict = {}
        plans = _originate(
            tmp_path,
            _standouts([_buy("TURNER", status="bounce_wait", dir_="caution",
                             act_level=0, spot=spot, lane="bottoming")]),
            stats=stats,
        )
        assert plans[0]["admission_class"] == pb.ADMISSION_CLASS_EARLY_TURN
        assert plans[0]["entry_zone"]["stance"] == pb.ZONE_STANCE_STARTER
        assert stats["early_turn_starters"] == ["TURNER"]
        assert stats["originated_by_class"]["early_turn_starter"] == 1

    def test_a_confirmed_basket_is_NOT_washout_mature(self):
        """By the time a basket has held TURNING for three sessions the starter window
        is the thing that already opened; admitting CONFIRMED would quietly turn the
        starter tier into a momentum tier."""
        assert "CONFIRMED" not in et.WASHOUT_MATURE_STATES
        assert "CONFIRMED" in et.WASHOUT_CONTEXT_STATES
        ctx = et.basket_turn_context(
            "T", {"T": {"state": "CONFIRMED", "basket_id": "b"}})
        assert ctx["washout_mature"] is False
        assert ctx["washout_context"] is True

    def test_leader_pullback_context_licenses_the_starter_class_on_its_own(
            self, tmp_path, monkeypatch):
        """§6.9 R4: the admission condition is washout-mature OR leader-pullback.

        THE CASE THIS EXISTS FOR — the NVDA/AVGO/ADAM population never washes out, so a
        washout-only context made it structurally unadmittable no matter how clean the
        dot was.  This name is in NO basket; the organ's own state is the whole licence.
        """
        prices = _leader_reset_series()
        coverage = _coverage(LEADR=_organ_row(prices))
        assert coverage["LEADR"]["state"] == lp.STATE_RESET_TURN

        out = et.assess_early_turn("LEADR", prices, asof=None, membership={},
                                   leader_states=coverage)
        assert out["signature_fired"] is True
        assert out["washout"]["washout_mature"] is False, (
            "the case is only meaningful on a name the washout lane cannot see")
        assert out["fired"] is True
        assert out["context_sources"] == [et.CONTEXT_LEADER_PULLBACK]
        assert "leader pullback" in out["reason"]

        monkeypatch.setattr(pb, "_load_price_history", lambda t: prices)
        monkeypatch.setattr(et, "load_basket_turn_membership", lambda *a, **k: {})
        monkeypatch.setattr(et, "load_leader_pullback_states", lambda *a, **k: coverage)
        spot = float(prices["close"].iloc[-1])
        stats: dict = {}
        plans = _originate(
            tmp_path,
            _standouts([_buy("LEADR", status="buy_now", spot=spot)]),
            stats=stats,
        )
        assert plans[0]["admission_class"] == pb.ADMISSION_CLASS_EARLY_TURN
        assert stats["early_turn_starters"] == ["LEADR"]
        assert stats["leader_pullback_source"] == ["us_leader_pullback"]

    def test_the_same_name_without_organ_coverage_admits_NOTHING(self):
        """The mutation half of the case above: strip the coverage and the identical
        price history stops admitting.  Without this the test passes on the signature
        alone and the context leg could be deleted unnoticed."""
        prices = _leader_reset_series()
        out = et.assess_early_turn("LEADR", prices, asof=None, membership={},
                                   leader_states={})
        assert out["signature_fired"] is True
        assert out["fired"] is False
        assert out["context_sources"] == []

    def test_the_context_disclosure_is_exhaustive_and_names_BOTH_when_both_fire(self):
        """The row must say WHICH context licensed it, and both names must survive when
        both did — "washout" alone would hide the second read, and a row that fired with
        no source at all would be an unattributable admission."""
        prices = _leader_reset_series()
        coverage = _coverage(BOTH=_organ_row(prices))
        membership = {"BOTH": {"state": "TURNING", "basket_id": "b"}}
        out = et.assess_early_turn("BOTH", prices, asof=None, membership=membership,
                                   leader_states=coverage)
        assert out["fired"] is True
        assert out["context_sources"] == [et.CONTEXT_WASHOUT,
                                          et.CONTEXT_LEADER_PULLBACK]
        assert out["reason"] == "signature + washout-mature basket + leader pullback"

        # Exhaustive: every disclosure any of these rows can carry is drawn from the
        # published vocabulary, ordered by it, and non-empty exactly when the row fired.
        assert et.CONTEXT_SOURCES == ("washout", "leader_pullback")
        cases = [
            et.assess_early_turn("BOTH", prices, membership=membership,
                                 leader_states=coverage),
            et.assess_early_turn("WASH", prices, membership={
                "WASH": {"state": "BASING", "basket_id": "b"}}, leader_states={}),
            et.assess_early_turn("LEADR", prices, membership={},
                                 leader_states=_coverage(LEADR=_organ_row(prices))),
            et.assess_early_turn("NEITHER", prices, membership={}, leader_states={}),
        ]
        for row in cases:
            sources = row["context_sources"]
            assert set(sources) <= set(et.CONTEXT_SOURCES), sources
            assert sources == [s for s in et.CONTEXT_SOURCES if s in sources], (
                "the disclosure must be ordered by CONTEXT_SOURCES, not by luck")
            assert bool(sources) is row["context_fired"]
            assert row["fired"] is (row["signature_fired"] and row["context_fired"])
        assert [len(r["context_sources"]) for r in cases] == [2, 1, 1, 0]

    def test_a_starved_price_store_is_a_NAMED_null_not_a_false(self):
        """The #4979 ext_z blackout in miniature: a read that cannot be made and a
        read that came back negative must never be indistinguishable."""
        thin = _bars([10.0] * 20)
        state = et.extension_state(thin, ASOF)
        assert state["source"] == "unavailable"
        assert state["daily_extended"] is None
        assert state["both_extended"] is False       # fails OPEN, and says so
        assert "fewer than" in state["reason"]

    def test_the_indicators_come_from_the_house_machinery(self):
        """A second implementation is a second answer.  This pins the import rather
        than the arithmetic: a local re-derivation would break it immediately."""
        source = (ROOT / "engine" / "us_early_turn.py").read_text(encoding="utf-8")
        assert "from engine.confluence_tiers import" in source
        for name in ("_rsi_macd", "_stoch_rsi_kd", "_tf_bars", "_to_daily", "_xup"):
            assert name in source
        assert "def rsi(" not in source and "def _macd(" not in source


# =========================================================================== #
# 9. §6.5 — the legacy shadow ledger                                           #
# =========================================================================== #
class TestLegacyShadowLedger:
    def _rows(self) -> list[dict]:
        return pb.legacy_shadow_rows(
            _standouts([
                _buy("OLDGATE", status="buy_now", act_level=3, priority=90),
                _buy("NEWONLY", status="bounce_wait", dir_="caution", act_level=0,
                     priority=80),
            ]),
            asof=ASOF,
        )

    def test_the_shadow_grades_the_OLD_gate_not_the_new_one(self):
        rows = self._rows()
        assert [r["ticker"] for r in rows] == ["OLDGATE"], (
            "the shadow ledger is following the live admission — it grades nothing")
        assert rows[0]["would_have_planned"] is True
        assert rows[0]["cap"] == pb.LEGACY_N_CANDIDATES
        assert rows[0]["authority"] == "none"
        assert rows[0]["selection_era"] == pb.SELECTION_ERA

    def test_the_cap_and_the_skips_are_replayed_not_just_the_gate(self):
        buys = [_buy(f"T{i:02d}", status="buy_now", priority=float(99 - i))
                for i in range(20)]
        rows = pb.legacy_shadow_rows(_standouts(buys), asof=ASOF)
        assert len(rows) == 20
        assert sum(1 for r in rows if r["would_have_planned"]) == pb.LEGACY_N_CANDIDATES
        assert {r["skip_reason"] for r in rows if not r["would_have_planned"]} == {
            "below_cap"}

    def test_append_is_idempotent_on_a_second_run_of_the_same_night(
            self, tmp_path, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        rows = self._rows()
        first = pb.append_legacy_shadow(rows, ASOF, store_dir=tmp_path,
                                        lane_nightly=True)
        second = pb.append_legacy_shadow(rows, ASOF, store_dir=tmp_path,
                                         lane_nightly=True)
        assert first == second == len(rows)
        frame = pb.load_legacy_shadow(store_dir=tmp_path)
        assert len(frame) == len(rows)
        assert (tmp_path / ASOF[:7] / f"{ASOF}.parquet").exists()

    def test_the_lane_argument_has_no_default(self):
        """A guard whose caller can forget it is a guard only the test suite runs
        (the #5000 shape).  Omitting the lane is a TypeError, not a permissive
        branch."""
        with pytest.raises(TypeError):
            pb.append_legacy_shadow([{"date": ASOF, "ticker": "T"}], ASOF,
                                    store_dir=Path("/nonexistent"))

    @pytest.mark.parametrize("lane_arg,env,expected", [
        (False, "nightly", 0),      # caller says no  -> nothing
        (True, "intraday", 0),      # process says no -> nothing
        (True, "nightly", 1),       # both agree      -> written
    ])
    def test_the_gate_is_two_sided(self, tmp_path, monkeypatch, lane_arg, env,
                                   expected):
        monkeypatch.setenv("COLLECT_LANE", env)
        monkeypatch.delenv("US_LANE", raising=False)
        written = pb.append_legacy_shadow(
            [{"date": ASOF, "ticker": "T"}], ASOF, store_dir=tmp_path,
            lane_nightly=lane_arg)
        assert written == expected
        assert (tmp_path / ASOF[:7]).exists() is bool(expected)


# =========================================================================== #
# 10. The PRODUCTION call path — build_prophet.main()                          #
# =========================================================================== #
def _run_main(tmp_path: Path, buys: list[dict], *, asof: str = ASOF) -> dict:
    """Drive build_prophet.main() against tmp_path and return the written index.

    This is the whole point of the test below: the lane gate is exercised through the
    REAL caller, not through a hand-fed argument.  A test that calls the writer
    directly proves the writer; only this proves the wiring.
    """
    standouts_path = _write(tmp_path, _standouts(buys, as_of=asof))
    saved = {name: getattr(bp, name) for name in
             ("STANDOUTS_PATH", "SITE_PROPHET", "PLANS_DIR", "STATES_DIR",
              "INDEX_PATH", "LEDGER_PATH", "LEDGER_DIR", "write_showcase")}
    try:
        bp.STANDOUTS_PATH = standouts_path
        bp.SITE_PROPHET = tmp_path / "site" / "prophet"
        bp.PLANS_DIR = bp.SITE_PROPHET / "plans"
        bp.STATES_DIR = bp.SITE_PROPHET / "states"
        bp.INDEX_PATH = bp.SITE_PROPHET / "index.json"
        bp.LEDGER_DIR = tmp_path / "data" / "prophet"
        bp.LEDGER_PATH = bp.LEDGER_DIR / "ledger.jsonl"
        # write_showcase binds its out_path default at def time, so the module
        # constant cannot redirect it — it would write the REAL showcase.json.
        bp.write_showcase = lambda: None
        bp.PLANS_DIR.mkdir(parents=True, exist_ok=True)

        prices = pd.DataFrame(
            {"close": [100.0 + i for i in range(40)],
             "high": [100.0 + i for i in range(40)],
             "low": [100.0 + i for i in range(40)]},
            index=pd.bdate_range("2026-05-08", periods=40),
        )
        with patch.object(sys, "argv", ["build_prophet", "--date", asof]), \
             patch("scripts.build_prophet._load_price_history_for_management",
                   return_value=prices):
            bp.main()
        return json.loads(bp.INDEX_PATH.read_text(encoding="utf-8"))
    finally:
        for name, value in saved.items():
            setattr(bp, name, value)


BUYS = [
    _buy("PAT", status="bounce_wait", dir_="caution", act_level=0, priority=90),
    _buy("CONF", status="buy_now", act_level=3, priority=80),
]


@pytest.fixture(scope="module")
def nightly_run(tmp_path_factory) -> tuple[dict, Path]:
    """ONE nightly ``bp.main()`` run, shared by every test that only READS it.

    Each run of the real publisher costs ~18s, and three of the cases below assert on
    the same artifact.  `monkeypatch` is function-scoped, so the lane is armed here
    with an explicit restore rather than through the fixture.
    """
    import os
    tmp_path = tmp_path_factory.mktemp("nightly")
    saved = (os.environ.get("COLLECT_LANE"), os.environ.get("US_LANE"))
    os.environ["COLLECT_LANE"] = "nightly"
    os.environ.pop("US_LANE", None)
    try:
        index = _run_main(tmp_path, BUYS)
    finally:
        for name, value in zip(("COLLECT_LANE", "US_LANE"), saved):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    return index, tmp_path


class TestProductionCallPath:
    BUYS = BUYS

    def test_the_nightly_lane_writes_the_shadow_store(self, nightly_run):
        index, tmp_path = nightly_run
        store = tmp_path / "data" / "prophet" / "legacy_shadow"
        assert store.exists(), "the nightly lane wrote no shadow part"
        assert list(store.glob("*/*.parquet"))
        assert index["intake"]["legacy_shadow"]["rows_in_part"] >= 1
        assert index["intake"]["legacy_shadow"]["authority"] == "none"

    def test_a_NON_nightly_lane_writes_NOTHING_through_the_real_caller(
            self, tmp_path, monkeypatch):
        """THE LANE GATE, at the production call site.

        `tests/conftest.py` arms COLLECT_LANE=nightly for every test, so this case
        only exists if a test explicitly disarms it — which is exactly why the dead
        guard in #5000 survived review.
        """
        monkeypatch.setenv("COLLECT_LANE", "intraday")
        monkeypatch.delenv("US_LANE", raising=False)
        index = _run_main(tmp_path, self.BUYS)
        store = tmp_path / "data" / "prophet" / "legacy_shadow"
        assert not store.exists(), (
            "an intraday lane wrote the forward shadow store — nightly is the sole "
            "advancer of forward stores")
        assert index["intake"]["legacy_shadow"]["rows_in_part"] == 0
        # The rows were still COMPUTED — only the append is gated.
        assert index["intake"]["legacy_shadow"]["admitted"] >= 1

    @pytest.mark.parametrize("lane,expected", [("nightly", True),
                                               ("intraday", False)])
    def test_the_CALLER_passes_the_resolved_lane_not_a_literal(
            self, tmp_path, monkeypatch, lane, expected):
        """THE WIRING, pinned directly — and this is not redundant with the store
        checks above.

        Mutation-verified 2026-08-09: hardcoding ``lane_nightly=True`` at the call
        site leaves every store assertion GREEN, because the writer's own env check
        catches it.  The store tests therefore prove the WRITER; only a spy on the
        call site proves the CALLER.  That gap is exactly the #5000 shape — a gate
        whose production caller never actually decides anything.
        """
        monkeypatch.setenv("COLLECT_LANE", lane)
        monkeypatch.delenv("US_LANE", raising=False)
        seen: list[object] = []

        def _spy(rows, asof, root=None, store_dir=None, *, lane_nightly):
            seen.append(lane_nightly)
            return 0

        monkeypatch.setattr(bp, "append_legacy_shadow", _spy)
        _run_main(tmp_path, self.BUYS)
        assert seen == [expected], (
            "the nightly caller is not passing the lane it resolved — the gate is "
            "decided by a literal, not by the process's actual lane")

    def test_the_index_carries_the_era_and_the_full_disposition(self, nightly_run):
        index, _ = nightly_run
        assert index["selection_era"] == pb.SELECTION_ERA
        intake = index["intake"]
        assert intake["selection_era"] == pb.SELECTION_ERA
        assert intake["admitted_statuses"] == sorted(pb.ADMITTED_STATUSES)
        assert intake["admitted_by_class"]["patience"] == 1
        assert intake["originated_by_class"]["patience"] == 1
        assert intake["lossless"] is True
        for row in index["plans"]:
            assert row["selection_era"] == pb.SELECTION_ERA
            assert row["admission_class"]
            assert row["entry_zone"]["schema"] == pb.ZONE_SCHEMA
            assert row["entry_zone_state"]["state"] in (
                "live", "filled", "expired", "converted", "none")
            assert row["entry_basis"]["state"] == "current"

    def test_the_nightly_copy_reflects_the_zone(self, nightly_run):
        index, _ = nightly_run
        for row in index["plans"]:
            if row["phase"] != "pre_trigger":
                continue
            en, zh = row["what_to_do_now"], row["what_to_do_now_zh"]
            assert en and zh and len(en) == len(zh)
            assert any("zone" in line for line in en)
            assert any("区间" in line for line in zh)


# =========================================================================== #
# 11. The committed board — the operator's actual review surface               #
# =========================================================================== #
class TestCommittedArtifactDisposition:
    """A READ of tonight's board, not a pin on it: the numbers move nightly, so the
    assertions are on PROPERTIES (every row accounted for, the patience cohort
    non-empty) rather than on counts."""

    @pytest.fixture(scope="class")
    @classmethod
    def board(cls) -> dict:
        if not COMMITTED.exists():
            pytest.skip("committed us_standouts.json absent")
        return json.loads(COMMITTED.read_text(encoding="utf-8"))

    def test_the_patience_cohort_is_actually_reachable_on_the_live_board(self, board):
        stats: dict = {}
        admitted = pb.select_candidates(board, n=None, stats=stats)
        assert stats["admitted_by_class"]["patience"] > 0, (
            "the inversion is inert on the live board — no patience row is admitted")
        assert len(admitted) > len(pb.legacy_admitted(board)), (
            "the new gate admits no more than the old one; nothing was inverted")

    def test_every_live_buy_row_has_exactly_one_disposition(self, board):
        stats: dict = {}
        admitted = pb.select_candidates(board, n=None, stats=stats)
        accounted = (
            len(admitted)
            + sum(stats["refused_status"].values())
            + sum(stats["refused_direction"].values())
            + sum(stats["refused_tier"].values())
            + stats["refused_band_low"]
            + stats["refused_no_entry_signal"]
        )
        assert accounted == stats["buy_rows"]

    def test_the_order_is_the_champion_order_within_the_admitted_set(self, board):
        """A1 moved ADMISSION, never ORDER (DNR:KILL-PROPHET-POP-MERGE)."""
        admitted = pb.select_candidates(board, n=None)
        keys = [pb._selection_sort_key(row) for row in admitted]
        assert keys == sorted(keys)
