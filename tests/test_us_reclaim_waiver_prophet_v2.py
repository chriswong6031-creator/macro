"""The RATIFIED counter-trend reclaim waiver — Arm P, `us_prophet_v2`.

WHAT THIS PINS.  `engine.signal_quality` now waives ONE leg of the buy filter — the 2-bar
200-day RECLAIM required of a name that is both below its 200-day average and weekly-down —
for a US name whose basket peers are themselves washed out at the ratified notch.  Authority:
`research/RECLAIM_VETO_CONDITIONAL_PREREG.md` (family `reclaim_veto_conditional_v1`) §4 Arm P,
adjudicated and ratified §5 on 2026-08-10, notch moved to 20% family-wide by the operator in
the same log; the era fence `us_prophet_v1 -> us_prophet_v2` was pre-specified by
`research/prophet_us_audit/RECLAIM_VETO_PACKET_2026-08-05.md` §7.  It is the ONE revival path
§9 left open for this leg, so `DNR:KILL-200DMA-RECLAIM-VETO-FLAT` is complied with, not
worked around: a flat drop stays killed.

THE BOUNDARY IS THE POINT.  Only the PURE reclaim failure — the hold leg PASSED, the reclaim
leg refused — may convert.  `CT_HOLD_FAIL` and `CT_BOTH_FAIL` are byte-identical to v1 under
every state, because §5 named that boundary explicitly when it ruled the motivating exemplar
HL 2026-06-16 out of reach ("the basket state admits it but this construction cannot" — a
hold-leg relaxation is a different construction owing its own prereg).  Half of the tests
below exist to make widening that branch fail loudly.

HERMETIC BY CONSTRUCTION.  Every case writes its own artifact to `tmp_path` and points the
loader at it.  Reading the COMMITTED `site/factordata/basket_washout_state.json` would be a
scheduled red: the waiver's PIT window is five sessions wide around a stamp that moves every
night, so a test riding the live artifact passes this week and fails next week for a reason
that has nothing to do with the code.

Siblings: `tests/test_us_reclaim_veto_packet.py` (the frozen v1 isolation the study measured
against — it must keep passing UNCHANGED, and does, because the waiver defaults to absent at
`_buy_filter`), `tests/test_hk_reclaim_veto_policy.py` (the flag HK drops flat).

Run: python3 -m pytest tests/test_us_reclaim_waiver_prophet_v2.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from engine import signal_gate, signal_quality as sq  # noqa: E402
from engine import us_board_rank as ubr  # noqa: E402


# --------------------------------------------------------------------------- #
# fixtures — a hand-built frame per branch, and a hand-built artifact per case
# --------------------------------------------------------------------------- #
def _frame(closes, above200_by_bar) -> pd.DataFrame:
    """The minimal signal-frame stand-in `_buy_filter` reads (same shape as the packet
    sibling's).  `w_bull` False throughout, so `above200[i] is False` puts every case on the
    counter-trend branch — the only branch the reclaim leg governs."""
    return pd.DataFrame({
        "close": pd.Series(closes, dtype=float),
        "above200": pd.Series(above200_by_bar, dtype=bool),
        "w_bull": pd.Series([False] * len(closes), dtype=bool),
    })


#: held (close rises at i+1), never reclaims -> the PURE reclaim failure.  The one branch.
PURE_RECLAIM_FAIL = _frame([100.0, 101.0, 101.5, 102.0], [False, False, False, False])
#: reclaimed at i+1 but the close FELL -> hold failure.  Never waivable.
HOLD_FAIL_ONLY = _frame([100.0, 99.0, 99.5, 100.5], [False, True, True, True])
#: neither leg passed.  Never waivable.
BOTH_FAIL = _frame([100.0, 99.0, 99.5, 100.5], [False, False, False, False])

#: A daily calendar the staleness arithmetic can count on.  Business days, so "5 sessions
#: after 2026-08-07" is a fact of this index rather than of a calendar-day subtraction.
SESSIONS = pd.bdate_range("2026-06-01", "2026-09-30", freq="B")

AS_OF = "2026-08-07"
#: One session after AS_OF — the healthy-night distance (see WASHOUT_MAX_STALE_SESSIONS:
#: `basket_washout` builds AFTER every US consumer in daily.yml, so the state a US board
#: reads is always the prior night's).
KNOWN_NEXT = "2026-08-10"


def _artifact(tmp_path: Path, *, as_of: str = AS_OF, peer_dd: float = -0.2721,
              ticker: str = "NEM", schema: str = "basket_washout_state.v1",
              body: str | None = None) -> Path:
    """Write a one-name washout artifact.  `qualifies` is computed the way the PRODUCER
    computes it (`scripts/build_basket_washout_state._qualifies`) rather than hand-set, so a
    fixture can never assert a flag the builder would not have published."""
    p = tmp_path / "basket_washout_state.json"
    if body is not None:
        p.write_text(body)
        return p
    q = {str(t): bool(peer_dd <= -t / 100.0) for t in (20, 25, 30)}
    p.write_text(json.dumps({
        "schema": schema, "as_of": as_of, "thresholds": [20, 25, 30], "baskets": {},
        "names": {ticker: {"basis": "basket", "group_id": "gold_miners",
                           "peer_dd": peer_dd, "qualifies": q}},
    }))
    return p


@pytest.fixture
def state(tmp_path, monkeypatch):
    """Point the loader at a fixture artifact and hand back a builder for it.

    The parsed-artifact cache is cleared on BOTH sides: a stale parse leaking into this test
    would make it pass for the wrong reason, and a fixture artifact leaking OUT of it would
    contaminate every later test in the session."""
    sq.reset_washout_state_cache()

    def build(**kw):
        p = _artifact(tmp_path, **kw)
        monkeypatch.setattr(sq, "_washout_state_file", lambda: p)
        sq.reset_washout_state_cache()
        return p

    yield build
    sq.reset_washout_state_cache()


def _waiver(ticker="NEM", known=KNOWN_NEXT):
    """The production resolution path, end to end: name lookup then PIT check."""
    return sq.reclaim_waiver_for(sq.washout_qualifier(ticker), known, SESSIONS)


def _verdict(frame, waiver, *, i=0, bear=False):
    return sq._buy_filter(i, frame, bear, len(frame), waiver=waiver)


# --------------------------------------------------------------------------- #
# 1. the waiver does what was ratified — and ONLY that
# --------------------------------------------------------------------------- #
class TestTheOneBranchThatConverts:
    def test_a_qualifying_pure_reclaim_failure_becomes_a_take(self, state):
        state()
        w = _waiver()
        assert w is not None, "the ratified fixture must qualify — otherwise this is vacuous"
        assert _verdict(PURE_RECLAIM_FAIL, w) == (True, sq.RECLAIM_WAIVED)

    def test_the_same_bar_without_the_waiver_is_the_v1_refusal(self):
        """The counterfactual, stated on the identical frame: this is the row the study
        measured, and v1 refuses it."""
        assert _verdict(PURE_RECLAIM_FAIL, None) == (False, sq.CT_RECLAIM_FAIL)

    def test_a_name_the_state_does_not_qualify_is_byte_identical_to_v1(self, state):
        """−18% peers: deeper than nothing, shallower than the notch.  Nothing may move."""
        state(peer_dd=-0.18)
        assert sq.washout_qualifier("NEM") is None
        assert _waiver() is None
        assert _verdict(PURE_RECLAIM_FAIL, _waiver()) == (False, sq.CT_RECLAIM_FAIL)

    def test_the_dial_sits_at_20_not_25(self, state):
        """The operator moved the family notch 25 -> 20 on 2026-08-10 (prereg §5, "NOTCH
        MOVED TO 20% FAMILY-WIDE").  −22% peers qualify at 20 and at NO higher notch, so this
        case can only pass on the shipped dial — it is the whole difference between the
        adjudication's recommendation and what was ratified."""
        state(peer_dd=-0.22)
        rec = sq.washout_qualifier("NEM")
        assert rec is not None and rec["peer_dd"] == -0.22
        assert sq.WASHOUT_NOTCH == "20"
        assert _verdict(PURE_RECLAIM_FAIL, _waiver()) == (True, sq.RECLAIM_WAIVED)

    def test_the_flag_is_read_from_the_artifact_not_re_derived(self, state):
        """`_qualifies` is computed by the producer from the PUBLISHED rounded number,
        precisely so a consumer cannot disagree with it on a boundary name.  A payload whose
        flag says False whatever the depth must be obeyed."""
        state()
        p = sq._washout_state_file()
        doc = json.loads(p.read_text())
        doc["names"]["NEM"]["qualifies"] = {"20": False, "25": False, "30": False}
        p.write_text(json.dumps(doc))
        sq.reset_washout_state_cache()
        assert sq.washout_qualifier("NEM") is None
        assert _verdict(PURE_RECLAIM_FAIL, _waiver()) == (False, sq.CT_RECLAIM_FAIL)


class TestTheHoldLegIsNeverWaived:
    """§5 drew this boundary and named the exemplar it costs (HL 2026-06-16).  Widening the
    waiver to a hold failure would be a DIFFERENT construction with no prereg and no gates."""

    def test_a_hold_failure_is_refused_with_a_qualifying_state(self, state):
        state()
        w = _waiver()
        assert w is not None
        assert _verdict(HOLD_FAIL_ONLY, w) == (False, sq.CT_HOLD_FAIL)
        assert _verdict(HOLD_FAIL_ONLY, w) == _verdict(HOLD_FAIL_ONLY, None)

    def test_a_double_failure_is_refused_with_a_qualifying_state(self, state):
        state()
        w = _waiver()
        assert _verdict(BOTH_FAIL, w) == (False, sq.CT_BOTH_FAIL)
        assert _verdict(BOTH_FAIL, w) == _verdict(BOTH_FAIL, None)

    def test_the_divergence_veto_is_refused_with_a_qualifying_state(self, state):
        """The bear veto short-circuits above every confirmation leg and is not in this
        family at all."""
        state()
        w = _waiver()
        assert _verdict(PURE_RECLAIM_FAIL, w, bear=True) == (False, sq.BEAR_DIV_REASON)

    def test_a_vetoed_bar_loses_the_reclaim_from_its_EXHAUSTIVE_account_only(self, state):
        """`_buy_filter_full`'s second leg no longer refuses, so the account shortens — the
        verdict does not move."""
        state()
        w = _waiver()
        n = len(PURE_RECLAIM_FAIL)
        take, reason, reasons = sq._buy_filter_full(0, PURE_RECLAIM_FAIL, True, n, waiver=w)
        assert (take, reason) == (False, sq.BEAR_DIV_REASON)
        assert reasons == [sq.BEAR_DIV_REASON]
        _, _, v1_reasons = sq._buy_filter_full(0, PURE_RECLAIM_FAIL, True, n)
        assert v1_reasons == [sq.BEAR_DIV_REASON, sq.CT_RECLAIM_FAIL]


# --------------------------------------------------------------------------- #
# 2. PIT — the state may never reach a label it postdates, nor one it has aged out of
# --------------------------------------------------------------------------- #
class TestPointInTime:
    def test_a_state_published_after_the_label_was_knowable_cannot_relieve_it(self, state):
        """The anchor is the marker's `confirmed_date` — the first close at which the label
        existed (prereg §2's "fire's known date").  Tonight's washout may not reach back and
        relieve a fire that was decided a month ago; if it could, every rebuild of history
        would produce a different marker stream."""
        state()
        assert _waiver(known="2026-07-01") is None

    def test_the_same_session_is_allowed(self, state):
        """`as_of == known_date` is same-night freshness, not future information."""
        assert state() and _waiver(known=AS_OF) is not None

    def test_the_healthy_night_distance_is_one_session(self, state):
        state()
        w = _waiver(known=KNOWN_NEXT)
        assert w is not None and w.stale_sessions == 1

    def test_the_staleness_ceiling_holds_at_its_boundary(self, state):
        """Open at the ceiling, closed past it — and both sides asserted, so a fixture that
        stopped exercising the boundary fails instead of quietly proving one side."""
        state()
        at_ceiling = SESSIONS[SESSIONS.searchsorted(pd.Timestamp(AS_OF), "right")
                              + sq.WASHOUT_MAX_STALE_SESSIONS - 1]
        past = SESSIONS[SESSIONS.searchsorted(pd.Timestamp(AS_OF), "right")
                        + sq.WASHOUT_MAX_STALE_SESSIONS]
        w = _waiver(known=str(at_ceiling.date()))
        assert w is not None and w.stale_sessions == sq.WASHOUT_MAX_STALE_SESSIONS
        assert _waiver(known=str(past.date())) is None

    def test_a_stale_state_reverts_the_leg_to_v1(self, state):
        state()
        stale_known = str(SESSIONS[SESSIONS.searchsorted(pd.Timestamp(AS_OF), "right")
                                   + sq.WASHOUT_MAX_STALE_SESSIONS + 3].date())
        assert _verdict(PURE_RECLAIM_FAIL, _waiver(known=stale_known)) == (
            False, sq.CT_RECLAIM_FAIL)

    def test_a_missing_knowable_date_is_a_refusal(self, state):
        """A marker still inside its confirmation window publishes `confirmed_date: null`.
        There is no date to judge the state against, so there is no waiver."""
        state()
        assert _waiver(known=None) is None

    def test_the_receipt_carries_the_states_own_as_of(self, state):
        """Requirement of the ratification: a waived row must be able to name the state that
        relieved it.  `as_of` is what makes the committed artifact re-readable from git."""
        state()
        w = _waiver()
        assert (w.as_of, w.notch, w.group_id, w.basis) == (
            AS_OF, "20", "gold_miners", "basket")
        assert w.peer_dd == -0.2721


# --------------------------------------------------------------------------- #
# 3. fallback — every doubt lands on v1, never on a default
# --------------------------------------------------------------------------- #
class TestFallsBackToV1:
    def test_an_absent_artifact_leaves_the_veto_intact(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sq, "_washout_state_file", lambda: tmp_path / "nope.json")
        sq.reset_washout_state_cache()
        assert sq.washout_state() is None
        assert _verdict(PURE_RECLAIM_FAIL, _waiver()) == (False, sq.CT_RECLAIM_FAIL)
        sq.reset_washout_state_cache()

    def test_an_unparseable_artifact_leaves_the_veto_intact(self, state):
        state(body="{not json at all")
        assert sq.washout_state() is None
        assert _verdict(PURE_RECLAIM_FAIL, _waiver()) == (False, sq.CT_RECLAIM_FAIL)

    def test_a_foreign_schema_leaves_the_veto_intact(self, state):
        """A future `basket_washout_state.v2` may redefine `qualifies` or `peer_dd`.  Until a
        reader is written for it, an unknown schema is an unknown quantity — refuse."""
        state(schema="basket_washout_state.v2")
        assert sq.washout_state() is None
        assert _verdict(PURE_RECLAIM_FAIL, _waiver()) == (False, sq.CT_RECLAIM_FAIL)

    def test_a_name_absent_from_the_map_leaves_the_veto_intact(self, state):
        """Names in neither the basket nor the sector mapping are OMITTED by the producer,
        never defaulted to a neutral value.  The consumer must read the omission the same
        way."""
        state(ticker="AEM")
        assert sq.washout_qualifier("NEM") is None
        assert _verdict(PURE_RECLAIM_FAIL, _waiver()) == (False, sq.CT_RECLAIM_FAIL)

    def test_the_era_stamp_does_NOT_fall_back(self):
        """Deliberate, and the reason the fence is honest: `BOARD_DEFINITION` marks the
        POLICY era, not per-day behaviour.  On a night when the artifact is missing the board
        admits exactly as v1 did — and still stamps `us_prophet_v2`, because the rule in
        force is the v2 rule and the ledger must not silently re-file that night under the
        old product.  A stamp that flickered with data availability would fence nothing."""
        assert ubr.BOARD_DEFINITION == "us_prophet_v2"


# --------------------------------------------------------------------------- #
# 4. blast radius — who must NOT see this
# --------------------------------------------------------------------------- #
class TestBlastRadius:
    @pytest.mark.parametrize("ticker", ["600547.SS", "002716.SZ", "0700.HK", "9988.HK"])
    def test_cn_and_hk_names_are_out_of_scope_even_if_the_map_claims_them(
            self, state, ticker):
        """Prereg §1 puts CN/HK out of scope outright — no CN/HK basket-washout state exists
        and their arms require their own construction.  The US `names` map would not claim
        these symbols, so this fixture deliberately makes it claim them anyway: the market
        fence, not the absence of a row, is what must refuse."""
        state(ticker=ticker)
        assert sq.washout_qualifier(ticker) is None

    def test_hk_policy_is_untouched(self, state):
        """HK dropped the leg FLAT (`reclaim_veto=False`, `hk_prophet_v2`).  There is no
        reclaim test left there to waive, and the two policies must not compound."""
        state()
        w = _waiver()
        assert sq._buy_filter(0, PURE_RECLAIM_FAIL, False, 4,
                              reclaim_veto=False, waiver=w) == (
            True, "held confirmation (counter-trend)")

    def test_the_take_reason_is_not_enrolled_in_the_CT_block_family(self):
        """`CT_*` is a load-bearing prefix, not a style.  `engine.china_continuation_watch`
        selects its entire cohort from the counter-trend BLOCK family, and
        `tests/test_china_continuation_watch.py` asserts set-equality between every `CT_*`
        constant here and the three strings the filter's block branches emit — so naming an
        ADMISSION `CT_RECLAIM_WAIVED` silently enrols a take in a block sweep.  It did,
        during this build; this is the pin that keeps it from happening again."""
        ct = {k for k, v in vars(sq).items()
              if k.startswith("CT_") and v == sq.RECLAIM_WAIVED}
        assert not ct, f"the waiver take is enrolled in the CT_ block family as {ct}"

    def test_the_default_reclaim_veto_is_still_True_at_every_entry_point(self):
        """The waiver lives INSIDE the leg; it did not loosen the flag that governs it."""
        import inspect
        for fn in (sq._confirm_legs, sq._buy_filter, sq._buy_filter_full, sq.analyze,
                   signal_gate.gate):
            assert inspect.signature(fn).parameters["reclaim_veto"].default is True, fn

    def test_the_waiver_defaults_to_absent_at_the_filter(self):
        """Which is why `tests/test_us_reclaim_veto_packet.py` — the frozen v1 isolation the
        study measured against — passes UNCHANGED: it calls `_buy_filter` positionally with
        `reclaim_veto=` only, and gets v1."""
        import inspect
        for fn in (sq._confirm_legs, sq._buy_filter, sq._buy_filter_full):
            assert inspect.signature(fn).parameters["waiver"].default is None, fn


# --------------------------------------------------------------------------- #
# 5. end to end — analyze(), the gate verdict, and the receipt
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def series() -> pd.Series:
    """A synthetic tape that actually reaches the branch under test.

    A plain bleed does NOT: on the first shape tried here every buy resolved on the MAIN
    branch ("failed next-bar hold"), because a name can be far below its 200-day average and
    still be weekly-BULL at the bar its buy fires — and the counter-trend branch needs BOTH.
    So the shape is an up-leg (which builds a high 200-day line) followed by a long bleed
    beneath it, and the seed is the one that prints four pure-reclaim refusals with the LAST
    marker among them.  `TestEndToEnd` asserts that census before it asserts anything else,
    so a fixture that stopped biting fails loudly instead of proving nothing."""
    rng = __import__("numpy").random.default_rng(17)
    n = 760
    steps = rng.normal(-0.0009, 0.019, n)
    steps[: n // 4] += 0.0030          # the up-leg that puts the 200-day line overhead
    steps[n // 4:] -= 0.0016           # then the bleed underneath it
    import numpy as np
    return pd.Series(100 * np.exp(np.cumsum(steps)),
                     index=pd.bdate_range("2023-01-01", periods=n, freq="B"), name="close")


class TestEndToEnd:
    @staticmethod
    def _refusals(series):
        off = sq.analyze("NEM", series, washout_waiver=False)
        assert off and off["markers"], "fixture produced no markers at all"
        blocked = [m for m in off["markers"]
                   if m.get("reason") == sq.CT_RECLAIM_FAIL and m.get("confirmed_date")]
        assert len(blocked) >= 2, (
            f"fixture printed {len(blocked)} pure-reclaim refusals — it needs several for "
            "the PIT window to have anything to exclude")
        assert off["markers"][-1] is blocked[-1], (
            "the LAST marker must be a pure-reclaim refusal, or the gate-verdict test below "
            "cannot reach the waiver (the gate reads the last marker only)")
        return off, blocked

    def test_analyze_flips_only_the_pit_eligible_marker(self, series, tmp_path, monkeypatch):
        """Drive the REAL `analyze` twice over one series — waiver on, waiver off — with the
        artifact stamped on the LAST refusal's knowable date.  Two claims at once: every flip
        is a `CT_RECLAIM_FAIL` -> `RECLAIM_WAIVED` conversion with the rest of the marker
        untouched, and the three OLDER refusals do NOT flip, because a state published today
        may not reach back and relieve a label that was knowable last year."""
        off, blocked = self._refusals(series)
        p = _artifact(tmp_path, as_of=blocked[-1]["confirmed_date"])
        monkeypatch.setattr(sq, "_washout_state_file", lambda: p)
        sq.reset_washout_state_cache()
        try:
            on = sq.analyze("NEM", series)
            assert len(on["markers"]) == len(off["markers"])
            flipped = 0
            for a, b in zip(on["markers"], off["markers"]):
                if a == b:
                    continue
                flipped += 1
                assert (b["reason"], b["quality"]) == (sq.CT_RECLAIM_FAIL, "block")
                assert (a["reason"], a["quality"]) == (sq.RECLAIM_WAIVED, "take")
                assert {k: v for k, v in a.items() if k not in ("reason", "quality")} == \
                       {k: v for k, v in b.items() if k not in ("reason", "quality")}
            assert flipped == 1, (
                f"expected exactly the one PIT-eligible marker to flip, got {flipped} of "
                f"{len(blocked)} refusals — the as_of <= known_date rule is not holding")
        finally:
            sq.reset_washout_state_cache()

    def test_the_gate_verdict_carries_the_receipt(self, series, tmp_path, monkeypatch):
        """`engine.signal_gate.gate()` re-derives the receipt (the §7 marker schema is closed
        and cross-repo, so it is not carried on the marker).  A verdict the waiver decided
        must be able to name the state that decided it — `as_of` above all, since that is
        what makes the committed artifact re-readable from git for any historical row.

        THE WAIVER DECIDES THE BUY-FILTER LEG, NOT THE GATE'S FINAL ANSWER.  On this fixture
        the waived take is then demoted by a LATER, unrelated leg — the cascade's
        topped/rolled-over judgment, which rewrites `reason` wholesale (the same late rewrite
        `tests/test_gate_reasons_exhaustive.py` pins) — so `v["reason"]` is asserted on the
        MARKER, where the buy filter's own answer lives.  The receipt is still emitted,
        deliberately: it records what the admission leg decided, and a row demoted for
        staleness is exactly the row an audit needs to be able to take apart."""
        _off, blocked = self._refusals(series)
        p = _artifact(tmp_path, as_of=blocked[-1]["confirmed_date"])
        monkeypatch.setattr(sq, "_washout_state_file", lambda: p)
        sq.reset_washout_state_cache()
        try:
            v = signal_gate.gate("NEM", series)
            assert v["last"]["reason"] == sq.RECLAIM_WAIVED
            assert v["last"]["quality"] == "take"
            assert v["waiver"] == {"rule": "reclaim", "notch": "20",
                                   "group_id": "gold_miners", "basis": "basket",
                                   "peer_dd": -0.2721,
                                   "as_of": blocked[-1]["confirmed_date"],
                                   "stale_sessions": 0, "era": "us_prophet_v2"}
        finally:
            sq.reset_washout_state_cache()

    def test_the_same_tape_is_refused_without_the_waiver(self, series):
        """The counterfactual for the row above, and the proof the flip is the waiver's doing
        rather than the fixture's: no artifact in play, so the marker must carry the v1 block
        AND the verdict must serialize exactly as it did pre-change (no `waiver` key)."""
        sq.reset_washout_state_cache()
        v = signal_gate.gate("NEM", series, washout_waiver=False)
        assert v["last"]["reason"] == sq.CT_RECLAIM_FAIL
        assert v["last"]["quality"] == "block"
        assert v["eligible"] is False
        assert "waiver" not in v

    def test_the_marker_contract_is_unwidened(self, series, tmp_path, monkeypatch):
        """`research/signal_engine/SCHEMA.json` closes `$defs/marker` with
        `additionalProperties: false`, and it is exported cross-repo as `golden_signals`.
        The waiver must not have quietly added a key to it."""
        _off, blocked = self._refusals(series)
        p = _artifact(tmp_path, as_of=blocked[-1]["confirmed_date"])
        monkeypatch.setattr(sq, "_washout_state_file", lambda: p)
        sq.reset_washout_state_cache()
        try:
            res = sq.analyze("NEM", series)
            assert any(m.get("reason") == sq.RECLAIM_WAIVED for m in res["markers"]), (
                "no waived marker in the stream — this contract check would be vacuous")
            allowed = set(json.loads(
                (REPO / "research" / "signal_engine" / "SCHEMA.json").read_text()
            )["$defs"]["marker"]["properties"])
            for m in res["markers"]:
                assert set(m) <= allowed, f"marker grew a key outside the §7 contract: {m}"
        finally:
            sq.reset_washout_state_cache()


# --------------------------------------------------------------------------- #
# 6. the declarations that make this legible from outside the engine
# --------------------------------------------------------------------------- #
class TestDeclarations:
    def test_the_new_reason_has_a_chinese_row(self):
        """`site/chart.js`'s REASON_ZH is exact-keyed and `lxReason()` falls back to the raw
        ENGLISH string on a miss, so an untranslated reason is an invisible regression rather
        than an error.  `tests/test_gate_reasons_exhaustive.py` owns the general guard; this
        asserts the specific row, because that guard's inventory is built by DRIVING the
        filter and the waiver branch needs a waiver to reach it."""
        src = (REPO / "site" / "chart.js").read_text()
        assert f"'{sq.RECLAIM_WAIVED}':" in src, (
            f"site/chart.js REASON_ZH has no row for {sq.RECLAIM_WAIVED!r}")

    def test_the_reason_reads_plain_word(self):
        """Glance/hover copy law (docs/DESIGN_DOCTRINE.md): no internal study or era names,
        no raw slugs, no untranslated stats, and none of the falsifier vocabulary the
        operator ruled off user-facing surfaces (#3821)."""
        r = sq.RECLAIM_WAIVED
        for banned in ("us_prophet", "prereg", "validated", "falsifier", "证伪",
                       "gc_v2", "arm_p", "qualifies", "peer_dd", "_"):
            assert banned not in r.lower(), f"{banned!r} must not appear in rendered copy"

    def test_the_artifact_read_is_declared_in_the_synapse_registry(self):
        """`scripts/check_synapse_reads.py` is a LITERAL-PATH scan, so the declaration and
        the literal must agree exactly or the guard silently stops seeing this read."""
        import yaml
        reg = yaml.safe_load((REPO / "config" / "synapse.yml").read_text())
        art = reg["artifacts"]["site-basket-washout-state"]
        assert art["path"] == sq.WASHOUT_STATE_PATH
        assert "engine/signal_quality.py" in art["consumers"]
        assert art["tier"] == "scored", (
            "the artifact now gates an ADMISSION decision — a display-tier declaration "
            "would be an untrue entry in the registry")
