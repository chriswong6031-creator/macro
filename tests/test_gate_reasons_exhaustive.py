"""A block reason names EVERY leg that refused, and only legs that actually ran.

Two audits found the same defect from opposite sides of `engine.signal_quality`'s buy filter,
and this file pins both fixes plus the one thing neither may cost: admission.

  1. FIRST-MATCH MASKING (``CN_DIVERGENCE_VETO_AUDIT.md``).  The filter returns on the first
     leg that refuses, so `reason` is a label, not an account.  湖南黄金 002155.SZ shipped
     ``buy blocked by filter: veto: bearish divergence`` on every stamped board date while
     ALSO failing the hold, and 575 of 743 vetoed CN fires (77%) were blocked by another leg
     anyway.  Fix: `_buy_filter_full` reports every failing leg as `reasons`, the verdict
     carries it, and the CN PIT store records it as `gate_reasons`.

  2. STRINGS NAMING TESTS THAT NEVER RAN (``CN_RECLAIM_HOLD_AUDIT.md`` §10/§11).  The main
     branch resolves on `held` alone yet emitted ``failed reclaim-and-hold`` — 1,094 blocks
     naming a reclaim nothing evaluated, on 002155.SZ which sat 5.2% ABOVE its 200-day mean.
     The counter-trend branch collapsed three failure shapes into one string, so only 40.2%
     of rows reading "no 200-reclaim" were relieved by dropping the reclaim rule.  Fix: each
     failure names the leg that refused; the legacy string survives only where both legs
     genuinely ran and both failed.

The risk in (1) is that "evaluate the remaining legs" quietly becomes "let one of them
speak"; the risk in (2) is a rename that drags a branch with it.  So the load-bearing tests
are differential:

  * ``TestAdmissionIsByteIdentical`` freezes a verbatim copy of the pre-change `_buy_filter`
    and replays it against production over a fixture universe — every buy bar, both
    ``reclaim_veto`` policies.  `take` must be identical UNCONDITIONALLY; a reason may differ
    only via the enumerated `_CORRECTED_REASONS` map, so an unlisted string change fails as
    drift.  It then patches the account out of production and asserts the full
    ``signal_gate.gate`` verdict (eligibility, tier, cascade, weight, reason, …) is equal
    key-for-key with and without it.

  * ``TestAccountIsExhaustive`` pins the point of (1): a bar that fails the divergence veto
    AND a confirmation leg lists BOTH, in evaluation order.  A universe producing no such bar
    would make this vacuous, so it asserts the fixture bites before it checks anything.

  * ``TestBoundedCost`` pins the cost story: the extra legs are evaluated ONCE per vetoed buy
    bar and never for an unvetoed one.  Measured on 191 real CN names the added work is 62 ms
    against a ~133 s pass (see the PR body); a wall-clock assert would be flaky in CI, so the
    invariant pinned here is the call count that produces it.

Run: python3 -m pytest tests/test_gate_reasons_exhaustive.py -q
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import signal_gate  # noqa: E402
from engine import signal_quality as sq  # noqa: E402

N_NAMES = 200          # the "~200 names" cost/behaviour fixture the brief asks for
N_BARS = 900           # ≥ 90 3B bars after the resample, so signal_frame is never empty
# A full `gate()` costs ~0.1s (analyze + the weighted cascade), so the whole-verdict
# comparisons run on a SUBSET while the per-bar differential — the rigorous half — replays
# every buy bar of all N_NAMES off cached frames.  Each subset assertion carries its own
# not-vacuous guard, so shrinking this further fails loudly instead of quietly proving less.
GATE_N = 100


# --------------------------------------------------------------------------- #
# the frozen pre-change filter — the differential baseline
# --------------------------------------------------------------------------- #
def legacy_buy_filter(i, sig, bear, n, *, reclaim_veto: bool = True):
    """VERBATIM copy of `_buy_filter` as it stood before `gate_reasons` (main @ ed15bca).

    Frozen on purpose: it is the only thing that can still fail if a future edit "simplifies"
    the split between `_confirm_legs` and `_buy_filter_full` into a behaviour change.  Do not
    refactor it to share code with production — that would make the comparison vacuous."""
    c, a = sig["close"], sig["above200"]
    if bear:
        return False, "veto: bearish divergence"
    if i + 1 >= n:
        return None, "pending confirmation"
    held = bool(c.iloc[i + 1] > c.iloc[i])
    below, wkdn = (not bool(a.iloc[i])), (not bool(sig["w_bull"].iloc[i]))
    if below and wkdn:
        if reclaim_veto:
            if i + 2 >= n:
                return None, "pending confirmation"
            reclaim = bool(a.iloc[i + 1]) or bool(a.iloc[i + 2])
            ok = held and reclaim
            return ok, ("reclaimed 200 & held" if ok else "counter-trend, no 200-reclaim/hold")
        return held, ("held confirmation (counter-trend)" if held else "failed next-bar hold")
    return held, ("held confirmation" if held else "failed reclaim-and-hold")


# --------------------------------------------------------------------------- #
# fixture universe — deterministic, no network, no data store
# --------------------------------------------------------------------------- #
def _series(seed: int) -> pd.Series:
    """One synthetic daily close: a drifting random walk with a regime flip partway through.

    The flip is what makes the fixture useful — a pure walk rarely prints the higher-price /
    lower-MACD swing pair the divergence veto needs, and a fixture with no vetoed bars would
    make every assertion below vacuous.  TestAccountIsExhaustive asserts the fixture bites."""
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.0006, 0.018, N_BARS)
    # a slow up-leg, a sharp drawdown, then a choppy recovery: prints swing highs on both
    # sides of the 200-day line and both weekly regimes.
    steps[: N_BARS // 3] += 0.0022
    steps[N_BARS // 3: N_BARS // 2] -= 0.0055
    steps[N_BARS // 2:] += 0.0012 * np.sin(np.arange(N_BARS - N_BARS // 2) / 11.0)
    close = 20.0 * np.exp(np.cumsum(steps))
    idx = pd.bdate_range("2019-01-01", periods=N_BARS, freq="B")
    return pd.Series(close, index=idx, name="close")


@pytest.fixture(scope="module")
def universe() -> list[tuple[str, pd.Series]]:
    return [(f"T{i:04d}.TEST", _series(1000 + i)) for i in range(N_NAMES)]


@pytest.fixture(scope="module")
def buy_bars(universe):
    """Every (ticker, frame, bar index, bear) the production filter is asked about.

    Built exactly the way `analyze` builds it — same frame, same dropna, same swing highs —
    so the differential replay below drives the filter with production's own inputs."""
    out = []
    for ticker, close in universe:
        sig = sq.signal_frame(close)
        if sig.empty:
            continue
        sig = sig.dropna(subset=["macd", "sig", "k", "d", "rsi14"])
        if len(sig) < 5:
            continue
        hi = sq._swing_highs(sig["high"])
        macd, n = sig["macd"], len(sig)
        bars = []
        for i in range(n):
            if bool(sig["CB"].iloc[i]) or bool(sig["revBuy"].iloc[i]):
                bars.append((i, bool(sq._bear_div(i, sig["high"], macd, hi))))
        if bars:
            out.append((ticker, sig, n, bars))
    return out


# The reason-string corrections, ENUMERATED (CN_RECLAIM_HOLD_AUDIT.md §10/§11).  A legacy
# string maps to the set of strings the corrected emitter may return in its place; anything
# outside this map is unintended drift, not a correction.  `take` is deliberately absent —
# admission is asserted identical unconditionally.
_CORRECTED_REASONS = {
    # main branch: tests `held` alone, so it may not name a reclaim
    "failed reclaim-and-hold": {"failed next-bar hold"},
    # counter-trend branch: tests BOTH legs, so it must say which one refused
    "counter-trend, no 200-reclaim/hold": {
        "counter-trend, no 200-reclaim/hold",             # both failed — legacy, earned
        "counter-trend, held but no 200-reclaim",
        "counter-trend, reclaimed 200 but no next-bar hold",
    },
}


def _first_match_only(i, sig, bear, n, *, reclaim_veto=True, waiver=None):
    """`_buy_filter_full` with the exhaustive account removed — production's own first-match
    path, so patching it in isolates EXACTLY the `reasons` addition.  (The separate question,
    whether production's first match still matches the pre-change engine, is what the frozen
    `legacy_buy_filter` differential answers; mixing the two would blur which claim failed.)

    ``waiver`` MUST be accepted and MUST be forwarded (`us_prophet_v2`, 2026-08-10).  A stub
    that drops a keyword the production function grew does not "ignore" it — `analyze` calls
    this with `waiver=`, the call raises TypeError, `gate()` swallows it into `res = None`,
    and all three byte-identity tests above then compare real verdicts against a wall of
    'insufficient history'.  Forwarding (rather than merely absorbing) is the load-bearing
    half: this stub is the BASE of a differential that must isolate `reasons` alone, so it
    has to make the same admission decisions production makes."""
    take, reason = sq._buy_filter(i, sig, bear, n, reclaim_veto=reclaim_veto, waiver=waiver)
    return take, reason, [reason]


def _gate_all(universe, *, reclaim_veto=True):
    return [signal_gate.gate(t, s, reclaim_veto=reclaim_veto) for t, s in universe]


@pytest.fixture(scope="module")
def paired_gates(universe):
    """(live, base) verdicts over the same names — production, and production with the
    exhaustive account patched back out.  Computed ONCE: a `gate()` pass is the expensive
    thing in this file, and three tests need exactly this pair."""
    names = universe[:GATE_N]
    live = _gate_all(names)
    with patch.object(sq, "_buy_filter_full", _first_match_only):
        assert sq._buy_filter_full is _first_match_only        # the patch actually took
        base = _gate_all(names)
    return names, live, base


class TestFixtureIsLoadBearing:
    def test_the_universe_actually_fires_buys(self, buy_bars):
        n_bars = sum(len(bars) for _, _, _, bars in buy_bars)
        assert len(buy_bars) >= N_NAMES // 2, (
            f"only {len(buy_bars)} of {N_NAMES} fixture names produced a usable signal frame — "
            "the differential proof below would be running on almost nothing"
        )
        assert n_bars >= 500, (
            f"fixture produced {n_bars} buy bars; too few to prove admission is unchanged"
        )


# --------------------------------------------------------------------------- #
# 1. admission is byte-identical
# --------------------------------------------------------------------------- #
class TestAdmissionIsByteIdentical:
    @pytest.mark.parametrize("reclaim_veto", [True, False])
    def test_admission_matches_the_frozen_pre_change_filter(self, buy_bars, reclaim_veto):
        """`take` from production == `take` from the frozen legacy body, on every buy bar of
        every fixture name under both policies.  The reason STRING may differ only where the
        enumerated correction applies — a string the legacy path could never emit, or a
        legacy string surviving where it is still earned, both fail."""
        checked = 0
        corrections = 0
        for ticker, sig, n, bars in buy_bars:
            for i, bear in bars:
                want_take, want_reason = legacy_buy_filter(i, sig, bear, n,
                                                           reclaim_veto=reclaim_veto)
                take, reason = sq._buy_filter(i, sig, bear, n, reclaim_veto=reclaim_veto)
                assert take == want_take, (
                    f"{ticker} bar {i}: ADMISSION moved — {take!r} != {want_take!r}. "
                    "Nothing in this change may touch the verdict."
                )
                if reason != want_reason:
                    allowed = _CORRECTED_REASONS.get(want_reason, set())
                    assert reason in allowed, (
                        f"{ticker} bar {i}: {want_reason!r} became {reason!r}, which is not "
                        f"one of the enumerated corrections {sorted(allowed)}"
                    )
                    corrections += 1
                full = sq._buy_filter_full(i, sig, bear, n, reclaim_veto=reclaim_veto)
                assert full[:2] == (take, reason), (
                    f"{ticker} bar {i}: the exhaustive path changed the VERDICT — "
                    f"{full[:2]!r} != {(take, reason)!r}. gate_reasons is diagnostic only."
                )
                assert full[2][0] == full[1], (
                    f"{ticker} bar {i}: reasons[0] {full[2][0]!r} is not reason {full[1]!r}"
                )
                checked += 1
        assert checked >= 500
        assert corrections > 0, (
            "no corrected reason string appeared in the whole fixture — the enumerated map "
            "would then be pinning nothing"
        )

    def test_the_retired_string_is_gone_and_the_hold_string_took_its_place(self, buy_bars):
        """The §11 defect, stated positively: no bar may still claim a reclaim that its
        branch never evaluated."""
        seen = set()
        for _ticker, sig, n, bars in buy_bars:
            for i, bear in bars:
                seen.add(sq._buy_filter(i, sig, bear, n)[1])
                seen.add(sq._buy_filter(i, sig, bear, n, reclaim_veto=False)[1])
        assert "failed reclaim-and-hold" not in seen, (
            "the main branch is again naming a reclaim it never tests"
        )
        assert sq.HOLD_FAIL in seen, "no hold-only block in the fixture — assertion is vacuous"

    def test_gate_verdicts_are_equal_with_and_without_the_account(self, paired_gates):
        """Compare every verdict key of the production gate against the same gate with the
        exhaustive account patched back out.  `reasons` is the only permitted difference —
        including inside the §7 marker payload the chart and the ledgers read."""
        names, live, base = paired_gates
        multi = 0
        for (ticker, _), a, b in zip(names, live, base):
            assert set(a) == set(b), f"{ticker}: verdict grew/lost a key"
            for key in a:
                if key in ("reasons", "result", "last"):
                    continue          # `result`/`last` are compared marker-wise below
                assert a[key] == b[key] or (
                    a[key] != a[key] and b[key] != b[key]      # NaN == NaN
                ), f"{ticker}: verdict[{key!r}] changed — {a[key]!r} != {b[key]!r}"
            ma = ((a.get("result") or {}).get("markers")) or []
            mb = ((b.get("result") or {}).get("markers")) or []
            assert len(ma) == len(mb), f"{ticker}: marker count changed"
            for x, y in zip(ma, mb):
                assert {k: v for k, v in x.items() if k != "reasons"} == y, (
                    f"{ticker}: a marker changed beyond the additive `reasons` key"
                )
                multi += "reasons" in x
        assert multi > 0, (
            "the patched and unpatched runs produced no `reasons` delta at all — this "
            "comparison would pass on an engine where nothing was added"
        )

    def test_eligibility_and_tier_counts_are_unmoved(self, paired_gates):
        """The headline outcome, stated the way a board consumes it: how many names are
        eligible, how many buyable, how many on each cascade tier."""
        def tally(gates):
            out = {"eligible": 0, "buyable": 0}
            for v in gates:
                out["eligible"] += bool(v.get("eligible"))
                out["buyable"] += bool(signal_gate.is_buyable(v))
                key = f"tier:{v.get('tier_cascade')}/{v.get('tier')}/{v.get('sub')}"
                out[key] = out.get(key, 0) + 1
            return out

        _, live, base = paired_gates
        assert tally(live) == tally(base), (
            "admission/tier outcomes moved — this change must be diagnostic only"
        )

    def test_hk_policy_admission_is_unmoved_too(self, universe):
        """HK runs the same filter with `reclaim_veto=False`; the account must be as inert
        there.  A smaller slice — the per-bar differential above already replays every buy
        bar of all names under this policy."""
        names = universe[:30]
        live = _gate_all(names, reclaim_veto=False)
        with patch.object(sq, "_buy_filter_full", _first_match_only):
            base = _gate_all(names, reclaim_veto=False)
        for (ticker, _), a, b in zip(names, live, base):
            assert set(a) == set(b), f"{ticker}: HK-policy verdict grew/lost a key"
            for key in a:
                if key in ("reasons", "result", "last"):
                    continue
                assert a[key] == b[key] or (a[key] != a[key] and b[key] != b[key]), (
                    f"{ticker}: HK-policy verdict[{key!r}] changed — {a[key]!r} != {b[key]!r}"
                )


# --------------------------------------------------------------------------- #
# 2. the account is exhaustive — the actual point of the change
# --------------------------------------------------------------------------- #
class TestAccountIsExhaustive:
    def test_an_over_determined_block_lists_every_failing_leg(self, buy_bars):
        over_determined = 0
        single = 0
        for ticker, sig, n, bars in buy_bars:
            for i, bear in bars:
                _take, reason, reasons = sq._buy_filter_full(i, sig, bear, n)
                assert reasons[0] == reason
                if not bear:
                    assert reasons == [reason], (
                        f"{ticker} bar {i}: an unvetoed bar must have nothing to add"
                    )
                    continue
                # a vetoed bar: the confirmation legs still get evaluated and reported
                rest = sq._confirm_legs(i, sig, n)
                if rest[0] is True:
                    assert reasons == [sq.BEAR_DIV_REASON], (
                        f"{ticker} bar {i}: the only failing leg was the veto; nothing to add"
                    )
                    single += 1
                else:
                    assert reasons == [sq.BEAR_DIV_REASON, rest[1]], (
                        f"{ticker} bar {i}: vetoed AND {rest[1]!r}, but reasons={reasons!r}"
                    )
                    over_determined += 1
        assert over_determined > 0, (
            "no over-determined block in the fixture universe — this test would pass on a "
            "no-op implementation. Fix the fixture, not the assertion."
        )
        assert single + over_determined > 0

    def test_marker_carries_reasons_exactly_when_it_adds_information(self, universe):
        """`reasons` on a §7 marker is emitted ONLY when len > 1, so the rendered file is
        byte-identical for every unambiguous name and a reader's [reason] fallback is exact."""
        seen_multi = False
        for ticker, close in universe[:60]:
            res = sq.analyze(ticker, close)
            if not res:
                continue
            for m in res["markers"]:
                if m["type"] not in ("buy", "rebuy"):
                    assert "reason" not in m and "reasons" not in m
                    continue
                if "reasons" in m:
                    seen_multi = True
                    assert len(m["reasons"]) > 1, (
                        f"{ticker}: a single-element `reasons` adds nothing and must be omitted"
                    )
                    assert m["reasons"][0] == m["reason"]
                    assert m["quality"] == "block", (
                        f"{ticker}: only a BLOCK can be over-determined, got {m['quality']}"
                    )
        assert seen_multi, "fixture printed no over-determined marker — assertion is vacuous"

    def test_verdict_reasons_open_on_the_verdict_reason(self, paired_gates):
        """The one invariant every downstream reader relies on, over every fixture verdict."""
        names, live, _ = paired_gates
        for (ticker, _), v in zip(names, live):
            assert isinstance(v.get("reasons"), list) and v["reasons"], f"{ticker}: no reasons"
            assert v["reasons"][0] == v["reason"], (
                f"{ticker}: reasons[0] {v['reasons'][0]!r} != reason {v['reason']!r}"
            )
            assert all(isinstance(r, str) and r for r in v["reasons"])
            c = signal_gate.compact(v)
            assert c["reasons"] == v["reasons"], "compact() dropped the account"

    def test_a_blocked_buy_verdict_names_both_legs(self):
        """The 002155-shaped case, driven end-to-end through verdict() on a hand-built marker."""
        marker = {"date": "2026-06-17", "type": "buy", "quality": "block",
                  "reason": "veto: bearish divergence",
                  "reasons": ["veto: bearish divergence", "failed next-bar hold"]}
        v = signal_gate.verdict({"markers": [marker], "early_now": False, "state": "mixed",
                                 "above200": False, "weekly_bull": False, "asof": "2026-08-03"})
        assert v["eligible"] is False
        assert v["reason"] == "buy blocked by filter: veto: bearish divergence"
        assert v["reasons"] == ["buy blocked by filter: veto: bearish divergence",
                                "buy blocked by filter: failed next-bar hold"]

    def test_a_stale_or_malformed_marker_account_is_ignored_not_trusted(self):
        """A `reasons` that does not open on the marker's own `reason` is out of sync with the
        label; trusting it would ship a verdict whose account contradicts its headline."""
        for bad in ([], ["something else", "x"], "not a list", None, [""]):
            marker = {"date": "2026-06-17", "type": "buy", "quality": "block",
                      "reason": "veto: bearish divergence", "reasons": bad}
            v = signal_gate.verdict({"markers": [marker], "early_now": False})
            assert v["reasons"] == ["buy blocked by filter: veto: bearish divergence"], (
                f"malformed marker account {bad!r} leaked into the verdict"
            )

    def test_reason_rewrites_never_leave_a_stale_account_behind(self, paired_gates):
        """`gate()` overwrites `reason` after `verdict()` (stale/topped demotions, the `tier T*`
        extension). Every one of those paths must take the account with it."""
        names, live, _ = paired_gates
        rewritten = 0
        for (ticker, _), v in zip(names, live):
            r = v["reason"]
            if r.startswith(("held but ", "forming master ", "tier ")):
                rewritten += 1
                assert v["reasons"] == [r], (
                    f"{ticker}: {r!r} kept a stale account {v['reasons']!r}"
                )
        assert rewritten > 0, "no verdict took a late reason rewrite — assertion is vacuous"


# --------------------------------------------------------------------------- #
# 3. bounded cost
# --------------------------------------------------------------------------- #
class TestEveryEmittedReasonStaysBilingual:
    """`site/chart.js` translates a marker's raw `reason` through a literal-keyed map, and
    `lxReason()` falls back to the ENGLISH string on a miss — so a key the engine emits but the
    map lacks is an invisible regression: the chart renders, nothing errors, and a Chinese
    reader silently gets English. Renaming `failed reclaim-and-hold` to `failed next-bar hold`
    would have done exactly that on the single most common block reason, because the new
    literal had no row. CLAUDE.md makes the UI bilingual; this is the guard that keeps the
    engine and that map from drifting again."""

    @staticmethod
    def _chart_reason_keys() -> set[str]:
        src = (ROOT / "site" / "chart.js").read_text()
        start = src.index("var REASON_ZH = {")
        body = src[start:src.index("};", start)]
        return set(re.findall(r"'([^']+)':", body))

    @staticmethod
    def _every_reason_the_engine_emits() -> set[str]:
        """Drive the filter down every branch and collect what it RETURNS — never a source
        grep. (tests/test_hk_v2_reason_copy_and_ran_lane.py documents why: the docstring is
        triple-quoted, so a quote-pairing regex over the source returns an empty set and every
        assertion built on it passes vacuously.)"""
        def frame(above200, w_bull, closes, flip=False):
            n = len(closes)
            a = [False] + [True] * (n - 1) if flip else [above200] * n
            return pd.DataFrame({"close": pd.Series(closes, dtype=float),
                                 "above200": pd.Series(a, dtype=bool),
                                 "w_bull": pd.Series([w_bull] * n, dtype=bool)})

        up, down = [100.0, 101.0, 101.5, 102.0], [100.0, 99.0, 99.5, 100.5]
        out = set()
        for a200 in (True, False):
            for wb in (True, False):
                for closes in (up, down):
                    f = frame(a200, wb, closes)
                    for veto in (True, False):
                        out.add(sq._buy_filter(0, f, False, 4, reclaim_veto=veto)[1])
                    out.add(sq._buy_filter(0, f, True, 4)[1])
                    out.add(sq._buy_filter(0, f, False, 1)[1])          # pending: i+1 >= n
                    out.add(sq._buy_filter(0, f, False, 2)[1])          # pending: i+2 >= n
        for closes in (up, down):                                      # reclaim actually happens
            out.add(sq._buy_filter(0, frame(False, False, closes, flip=True), False, 4)[1])
        # The ratified reclaim waiver (`us_prophet_v2`, 2026-08-10) emits a reason that no
        # other call above can reach: it needs a resolved waiver, which production only
        # builds from the nightly washout artifact.  Driving it with a hand-made receipt is
        # what keeps this inventory EXHAUSTIVE — otherwise the newest user-facing string in
        # the filter would be the one string this guard cannot see, and a zh reader would
        # get raw English on it with nothing reporting the gap.
        _w = sq.ReclaimWaiver("gold_miners", "basket", -0.27, "2026-08-07", "20", 1)
        for closes in (up, down):
            for a200 in (True, False):
                for wb in (True, False):
                    out.add(sq._buy_filter(0, frame(a200, wb, closes), False, 4, waiver=_w)[1])
        return out

    def test_the_inventory_is_not_vacuous(self):
        reasons = self._every_reason_the_engine_emits()
        assert len(reasons) >= 8, sorted(reasons)
        assert sq.HOLD_FAIL in reasons and sq.CT_HOLD_FAIL in reasons
        assert sq.RECLAIM_WAIVED in reasons, (
            "the waiver branch is no longer reachable from this inventory — the guard below "
            "would stop covering the reason it was extended for")

    def test_every_reason_the_engine_emits_has_a_chinese_row(self):
        missing = sorted(self._every_reason_the_engine_emits() - self._chart_reason_keys())
        assert not missing, (
            f"site/chart.js REASON_ZH has no row for {missing} — a zh reader gets the raw "
            "English string, and nothing in the page reports it"
        )


class TestBoundedCost:
    def test_the_extra_legs_run_once_per_vetoed_bar_and_never_otherwise(self, monkeypatch):
        """The divergence veto is the ONLY short-circuiting leg, so the added work is one
        `_confirm_legs` call on the bars that were already ambiguous — never a second pass
        over the universe, never anything on a clean bar."""
        calls = {"n": 0}
        real = sq._confirm_legs

        def counted(*a, **kw):
            calls["n"] += 1
            return real(*a, **kw)

        monkeypatch.setattr(sq, "_confirm_legs", counted)

        close = _series(4242)
        sig = sq.signal_frame(close).dropna(subset=["macd", "sig", "k", "d", "rsi14"])
        n = len(sig)
        hi = sq._swing_highs(sig["high"])
        bars = [(i, bool(sq._bear_div(i, sig["high"], sig["macd"], hi)))
                for i in range(n)
                if bool(sig["CB"].iloc[i]) or bool(sig["revBuy"].iloc[i])]
        assert bars, "fixture printed no buy bar"

        calls["n"] = 0
        for i, bear in bars:
            before = calls["n"]
            sq._buy_filter_full(i, sig, bear, n)
            spent = calls["n"] - before
            assert spent == 1, (
                f"bar {i} (bear={bear}) evaluated the confirmation legs {spent}x — the "
                "exhaustive account must cost at most one extra evaluation, and a bar with "
                "no veto must cost exactly what it always did"
            )
