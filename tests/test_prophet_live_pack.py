"""tests/test_prophet_live_pack.py — Prophet Live P0 gate G0.1: PARITY OR NOTHING.

The whole program rests on one identity: the interval the nightly pack publishes must
answer the same question the nightly gate answers. If it does not, the intraday lane
tells a user a price level that does not exist — and it does so silently, because both
sides look internally consistent. So this file re-runs the REAL
:func:`engine.signal_gate.gate` against the published pack from three directions:

  * ``test_parity_at_as_of_close`` — the G0.1 statement itself: fed the actual close,
    the interval reproduces tonight's verdict for every probed name.
  * ``test_parity_over_the_probe_grid`` — the property sweep: EVERY price the probe
    evaluated must agree with the interval. This is what catches a representation bug
    (an edge stored on the wrong side, an unbounded side dropped).
  * ``test_reported_edges_are_buyable_prices`` — a published threshold is a price the
    gate really accepts, never one it rejects by a rounding step.

FIXTURES ARE ENGINEERED TO SIT NEAR TIER FLIPS, not sampled and hoped over: the
seeded walks below are chosen because the real cascade puts three of them inside a
buyable tier and three within a few percent of one (``ARMED_FIXTURE``'s trigger sits
just above its own close). ``test_fixtures_are_not_vacuous`` fails if that ever stops being true, so
a future engine change cannot turn this file into a suite that passes by testing
nothing.

...BUT THE SEEDED WALKS ARE VACUOUS ON THE PROBE-SEMANTICS AXIS, measured: every one
of them returns the same verdict whether the candidate REPLACES the last bar or is
APPENDED as the next session's, so the whole file passed unchanged when the pack was
answering the wrong question. That is what ``append_flip_close.csv`` is for — a frozen
real close series that a fresh cross makes buyable under the old replace-probe and
that tonight's gate rejects once the bar advances (``test_replace_and_append_disagree``
and its neighbours below).

NO DATE-LITERAL CLOCK. Every fixture pins its own index and every payload is built
with an explicit ``now``; nothing here reads the wall clock, so no scheduled red can
arrive from the calendar (the fixture-date + wall-clock-gate bomb). The frozen CSV is
part of that contract: the flip is pinned to committed prices, never to whatever the
store holds tonight.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import signal_gate  # noqa: E402
from engine.prophet_live import armed_pack as AP  # noqa: E402
# The stdlib-only contract module, imported directly rather than through armed_pack's
# re-export: `probe_floor` is read by the pandas-free */5 lane, and a test that could
# only reach it through the pandas module would not be testing that.
from engine.prophet_live import interval as IV  # noqa: E402
from engine.prophet_live.r2io import PACK_KEY as AP_R2_PACK_KEY  # noqa: E402

# A fixed business-day index: no wall-clock date arithmetic anywhere in this file.
IDX = pd.bdate_range("2022-01-03", periods=520)

#: Seeds kept for what the REAL cascade does with them. RE-MEASURED TWICE: under the
#: cascade's absolute session anchor (era abs-session-2026-08-06), and again under the
#: §7 stream's own anchor (era sq-abs-session-2026-08-06) — each re-phasing moves which
#: seed sits in which state; the ENGINEERED property (some buyable, one of them armed,
#: some near a flip, some dormant) is what the file needs and it still holds:
#:   18  buyable, armed with a fade edge      7  buyable, no edge in band at all
#:   0, 2, 21, 22  near, armed with a lower edge   (0 was "buyable" pre-sq-anchor)
#:   1, 5, 9, 13  dormant across the whole band    (9 was "near" pre-anchor)
#: Ten series is ~150 real gate calls (~13s), which is the honest cost of testing
#: parity against the actual engine instead of a stub.
SEEDS = (0, 1, 2, 5, 7, 9, 13, 18, 21, 22)

NOW = datetime(2026, 7, 29, 22, 30, tzinfo=timezone.utc)

#: The seed used wherever a test needs a name that is ARMED (a published lower edge). Named
#: once, and pinned by test_the_armed_fixture_is_actually_armed, so a future re-phase reds
#: THAT test with a clear message instead of silently making four refusal tests vacuous.
ARMED_FIXTURE = "S21"


def _walk(seed: int, n: int = 520, start: float = 100.0,
          vol: float = 0.018, drift: float = 0.0002) -> pd.Series:
    """A deterministic lognormal walk — same series on every machine and run."""
    rng = np.random.default_rng(seed)
    return pd.Series(start * np.exp(np.cumsum(rng.normal(drift, vol, n))), index=IDX[:n])


@pytest.fixture(scope="module")
def series() -> dict[str, pd.Series]:
    return {f"S{s:02d}": _walk(s) for s in SEEDS}


@pytest.fixture(scope="module")
def pack(series) -> dict:
    return AP.build_pack(sorted(series.items()), now=NOW,
                         cfg={"max_probe": 50, "max_seconds": 3600})


@pytest.fixture(scope="module")
def cfg() -> dict:
    return AP.pack_cfg({"prophet_live": {"max_probe": 50, "max_seconds": 3600}})


# ─────────────────────────────────────────────────────────────────────────────
# G0.1 — parity or nothing
# ─────────────────────────────────────────────────────────────────────────────

def test_fixtures_are_not_vacuous(pack):
    """A parity suite over nothing-but-dormant names proves nothing."""
    states = pack["meta"]["states"]
    assert pack["meta"]["probed_n"] == len(SEEDS)
    assert states.get("buyable", 0) >= 2, states
    assert states.get("near", 0) >= 2, states
    assert pack["meta"]["armed_n"] >= 4, pack["meta"]
    lowers = [AP.lower_edge(e) for e in pack["names"].values()]
    assert sum(1 for x in lowers if x is not None) >= 4
    assert any(e.get("fade_hi_px") is not None for e in pack["names"].values())


def test_the_armed_fixture_is_actually_armed(series):
    """``ARMED_FIXTURE`` is the seed four REFUSAL tests build a one-name pack from. If an
    engine change re-phases it into `dormant`, those tests stop exercising a refusal and go
    quietly vacuous — the pack they build has nothing to refuse. Red HERE instead, with the
    remedy: re-measure the seeds and repoint ARMED_FIXTURE (that is what the absolute session
    anchor, era abs-session-2026-08-06, required when S09 went dormant)."""
    p = AP.build_pack([(ARMED_FIXTURE, series[ARMED_FIXTURE])], now=NOW)
    assert p["meta"]["armed_n"] >= 1, (
        f"{ARMED_FIXTURE} is no longer armed ({p['meta']}) — repoint ARMED_FIXTURE at a seed "
        f"that is, or the refusal tests below prove nothing")
    assert AP.lower_edge(p["names"][ARMED_FIXTURE]) is not None


def test_parity_at_as_of_close(pack, series):
    """G0.1: interval membership at the as-of close == the gate's verdict THERE.

    "The gate's verdict there" is the gate run on the probe's OWN construction — the
    as-of close appended as the next session's bar — because that is the construction
    every published edge was measured on. ``center_buyable`` is the other reading
    (tonight's board membership, on the store as it stands) and is asserted separately
    against the raw series. The two agree on these seeds; a name where they do NOT is
    the frozen CSV fixture further down, and the pack publishes both so no consumer has
    to guess which one it is holding.
    """
    checked = 0
    for tkr, entry in sorted(pack["names"].items()):
        if not entry.get("probed") or entry["state"] == "irregular":
            continue
        as_of = entry["as_of_close"]
        anchor = signal_gate.is_buyable(
            signal_gate.gate(tkr, AP.probe_series(series[tkr], as_of)))
        got = AP.interval_contains(entry, as_of)
        assert got == anchor, f"{tkr}: interval says {got}, real gate says {anchor} ({entry})"
        assert bool(entry["probe_center_buyable"]) == anchor, tkr
        assert AP.membership_anchor(entry) == (anchor, "probe_center_buyable"), tkr
        # ...and the BOARD verdict is still the raw as-of one, unmoved by any of this.
        assert bool(entry["center_buyable"]) == signal_gate.is_buyable(
            signal_gate.gate(tkr, series[tkr])), tkr
        checked += 1
    assert checked == len(SEEDS)


def test_self_check_agrees_with_the_real_gate(pack):
    """The membership invariant holds — but see the tautology test below: it is NOT
    the fail-closed gate and must not be described as one."""
    assert AP.self_check(pack["names"]) == []


# ─────────────────────────────────────────────────────────────────────────────
# B1 — the INDEPENDENT edge check, and why the membership check is not enough
# ─────────────────────────────────────────────────────────────────────────────

def test_the_membership_check_cannot_fail_on_an_assembled_pack():
    """Names the defect: ``self_check`` reads the numbers the assembly just wrote.

    Fuzzing synthetic gates never produces a membership mismatch, because nothing in
    the assembly path can create one. That is exactly why it was wrong to advertise it
    as fail-closed parity — the real gate is :func:`AP.edge_checks` /
    :func:`AP.verify_edges`, which re-run the ENGINE at the published prices.
    """
    import random
    rng = random.Random(4)
    for _ in range(60):
        lo, hi = sorted(rng.uniform(50.0, 150.0) for _ in range(2))
        last = rng.uniform(lo - 20.0, hi + 20.0)
        p = AP.build_pack([("F", _flat(last))], now=NOW, gate_fn=_synth_gate(lo, hi))
        assert AP.self_check(p["names"]) == []


def test_the_edge_check_runs_and_is_not_vacuous(pack):
    m = pack["meta"]
    assert m["armed_n"] >= 4
    # Two prices per located edge: the edge itself and the bisection's measured
    # false-side bound.
    assert m["edges_checked"] >= 2 * m["armed_n"]
    assert m["edge_mismatches"] == []
    assert m["gate_calls"] > m["edges_checked"]


def test_the_edge_check_catches_a_price_the_gate_rejects(series):
    """It must be able to FAIL — the whole point of replacing the tautology."""
    tkr = ARMED_FIXTURE
    s = series[tkr]
    rec = AP.centre_record(tkr, s, cfg=AP.pack_cfg(None))
    probe = AP.probe_name(tkr, s, rec, cfg=AP.pack_cfg(None))
    entry = AP.name_entry(rec, probe)
    assert entry.get("trigger_px")

    clean, n = AP.verify_edges(tkr, s, AP.edge_checks(entry, probe))
    assert clean == [] and n >= 2

    # Move the published trigger a full percent below the real boundary: the gate now
    # disagrees with the pack at a price the pack tells the evaluator to act on.
    doctored = dict(entry)
    doctored["trigger_px"] = float(entry["trigger_px"]) * 0.99
    bad, _ = AP.verify_edges(tkr, s, AP.edge_checks(doctored, probe))
    assert bad and "buyable=False" in bad[0] and tkr in bad[0]


def test_the_false_side_price_comes_from_the_bisection_not_a_guess():
    """A "one tick below" guess lands INSIDE the final bracket, where the verdict is
    unknown by construction, and the check would be flaky instead of strict."""
    s = _flat(95.0)
    rec = AP.centre_record("G", s, cfg=AP.pack_cfg(None), gate_fn=_synth_gate(100.0, 105.0))
    probe = AP.probe_name("G", s, rec, cfg=AP.pack_cfg(None),
                          gate_fn=_synth_gate(100.0, 105.0))
    assert probe["lower_false"] is not None and probe["lower_edge"] is not None
    assert probe["lower_false"] < probe["lower_edge"]
    assert probe["upper_false"] > probe["upper_edge"]
    checks = AP.edge_checks(AP.name_entry(rec, probe), probe)
    assert sorted(exp for _px, exp in checks) == [False, False, True, True]


def test_an_unverified_armed_pack_is_refused(monkeypatch, capsys, series):
    """Unproven is not clean: armed levels with zero re-verified prices must not ship."""
    import scripts.build_prophet_live_pack as B
    p = AP.build_pack([(ARMED_FIXTURE, series[ARMED_FIXTURE])], now=NOW)
    assert p["meta"]["armed_n"] >= 1
    p["meta"]["edges_checked"] = 0
    p["meta"]["edge_mismatches"] = []
    published: list[str] = []
    monkeypatch.setattr(B, "build", lambda **kw: p)
    monkeypatch.setattr(B.r2io, "put_json", lambda k, v, **kw: published.append(k))
    assert B.main(["--publish"]) == 1
    assert published == []
    err = [ln for ln in capsys.readouterr().out.splitlines() if "::error" in ln]
    assert err and err[0].startswith("::error title=prophet-live-pack-parity::")
    assert "re-verified" in err[0]


def test_an_edge_mismatch_withholds_that_name_not_the_pack(monkeypatch, capsys, series):
    """N3: mismatches are withheld per name; the pack still ships for everyone else.

    Refusing the whole pack over one boundary case darks every other name for the rest of
    the session, which is a worse outcome than publishing a pack that is missing one
    name's levels. The wrong price does not reach a user on either path.
    """
    import scripts.build_prophet_live_pack as B
    p = AP.build_pack([(ARMED_FIXTURE, series[ARMED_FIXTURE])], now=NOW)
    p["meta"]["edge_mismatches"] = [f"{ARMED_FIXTURE}: gate says buyable=False at published price 1.0"]
    published: list[str] = []
    monkeypatch.setattr(B, "build", lambda **kw: p)
    monkeypatch.setattr(B.r2io, "put_json", lambda k, v, **kw: published.append(k) or True)
    assert B.main(["--publish"]) == 0
    assert published == [AP_R2_PACK_KEY]
    out = capsys.readouterr().out
    assert "levels withheld" in out
    warn = [ln for ln in out.splitlines() if "::warning title=prophet-live-pack-parity" in ln]
    assert warn and warn[0].startswith("::warning")


def test_a_residual_membership_mismatch_still_refuses_the_pack(monkeypatch, series):
    """The belt: anything that survives the withholding is structural and blocks."""
    import scripts.build_prophet_live_pack as B
    p = AP.build_pack([(ARMED_FIXTURE, series[ARMED_FIXTURE])], now=NOW)
    victim = next(t for t, e in p["names"].items() if e.get("trigger_px") is not None)
    p["names"][victim]["trigger_px"] = p["names"][victim]["as_of_close"] * 0.5
    published: list[str] = []
    monkeypatch.setattr(B, "build", lambda **kw: p)
    monkeypatch.setattr(B.r2io, "put_json", lambda k, v, **kw: published.append(k))
    assert B.main(["--publish"]) == 1
    assert published == []


def test_a_membership_mismatch_is_withheld_inside_build(monkeypatch, series):
    """The withholding happens where the probes are, so the entry loses its levels."""
    import scripts.build_prophet_live_pack as B
    # bisect_iters high enough that a boundary can land within one 4-dp step of the
    # close is the config-reachable route; drive the withholding directly instead of
    # hunting a fixture that triggers it, and assert the entry shape it produces.
    rec = AP.centre_record(ARMED_FIXTURE, series[ARMED_FIXTURE], cfg=AP.pack_cfg(None))
    probe = AP.probe_name(ARMED_FIXTURE, series[ARMED_FIXTURE], rec, cfg=AP.pack_cfg(None))
    entry = AP.name_entry(rec, probe)
    assert entry.get("trigger_px") is not None
    rec["skip"] = "membership_mismatch"
    rec["wants_probe"] = False
    withheld = AP.name_entry(rec, None)
    assert withheld.get("trigger_px") is None and withheld.get("fade_px") is None
    assert withheld["probed"] is False and withheld["skip"] == "membership_mismatch"
    assert AP.interval_contains(withheld, withheld["as_of_close"]) is None


def test_rounding_never_crosses_the_as_of_close():
    """The clamp that guaranteed self_check passing is gone; this replaces it.

    The rule is one comparison: the published edge sits on the same side of the close
    as the bisected value. When a 1/100-cent rounding step would move it across, the
    full-precision value ships instead — the boundary really is that near the print,
    and that is information rather than noise.
    """
    close = 100.00005
    # A lower edge just BELOW the close: rounding up would carry it above.
    px, unrounded = AP._side_safe_round(100.00003, close, up=True)
    assert unrounded is True and px == 100.00003
    # An upper edge just ABOVE the close: rounding down would carry it below.
    px, unrounded = AP._side_safe_round(100.00007, close, up=False)
    assert unrounded is True and px == 100.00007
    # A comfortable edge rounds normally, on both sides.
    px, unrounded = AP._side_safe_round(95.123456, close, up=True)
    assert unrounded is False and px == 95.1235
    px, unrounded = AP._side_safe_round(105.987654, close, up=False)
    assert unrounded is False and px == 105.9876
    assert AP._side_safe_round(None, close, up=True) == (None, False)


def test_an_unrounded_edge_is_disclosed_in_meta(pack):
    """Whatever the rounding rule declines to do must be visible, not silent."""
    assert "unrounded_edges" in pack["meta"]
    assert isinstance(pack["meta"]["unrounded_edges"], int)


def test_parity_over_the_probe_grid(pack, series, cfg):
    """Property sweep: every price the probe evaluated agrees with the interval."""
    swept = 0
    for tkr, entry in sorted(pack["names"].items()):
        if not entry.get("probed") or entry["state"] == "irregular":
            continue
        span = AP.probe_span(entry["as_of_close"], entry["center_buyable"], cfg["band_pct"])
        for px in AP.probe_grid(span, cfg["grid_points"]):
            want = signal_gate.is_buyable(
                signal_gate.gate(tkr, AP.probe_series(series[tkr], px)))
            got = AP.interval_contains(entry, px)
            assert got == want, (
                f"{tkr} @ {px:.6f}: interval says {got}, real gate says {want} ({entry})")
            swept += 1
    assert swept >= len(SEEDS) * cfg["grid_points"]


def test_reported_edges_are_buyable_prices(pack, series):
    """A published threshold is a price the gate ACCEPTS — the true-side invariant."""
    seen = 0
    for tkr, entry in sorted(pack["names"].items()):
        for field in ("trigger_px", "fade_px", "fade_hi_px"):
            px = entry.get(field)
            if px is None:
                continue
            assert signal_gate.is_buyable(
                signal_gate.gate(tkr, AP.probe_series(series[tkr], float(px)))), \
                f"{tkr}.{field}={px} is not a buyable price"
            seen += 1
    assert seen >= 4


def test_a_trigger_really_is_a_flip(pack, series, cfg):
    """The grid cell below a trigger is NOT buyable — the level marks a real boundary."""
    checked = 0
    for tkr, entry in sorted(pack["names"].items()):
        lo = AP.lower_edge(entry)
        if lo is None:
            continue
        span = AP.probe_span(entry["as_of_close"], entry["center_buyable"], cfg["band_pct"])
        grid = AP.probe_grid(span, cfg["grid_points"])
        below = [p for p in grid if p < lo]
        if not below:
            continue
        px = max(below)
        assert not signal_gate.is_buyable(
            signal_gate.gate(tkr, AP.probe_series(series[tkr], px))), \
            f"{tkr}: gate is buyable at {px} which is BELOW the reported edge {lo}"
        checked += 1
    assert checked >= 3


# ─────────────────────────────────────────────────────────────────────────────
# W-L0 gate 1 — the probe answers TONIGHT's question: the candidate is APPENDED
# ─────────────────────────────────────────────────────────────────────────────

def test_probe_series_appends_a_next_session_bar(series):
    """One bar longer, landing on the next SESSION — never a replaced last bar.

    Tonight's nightly adds a session to the store; it does not restate the last one.
    A probe that replaced the bar froze the series length, the session-anchor bucket
    positions and the freshness ticks at yesterday's, and never supplied the next bar
    that a ``pending`` buy's reclaim-and-hold resolves on.
    """
    s = series["S00"]
    out = AP.probe_series(s, 123.5)
    assert len(out) == len(s) + 1
    assert out.index[-1] > s.index[-1]
    assert out.iloc[-1] == 123.5
    # Everything before the new bar travels untouched — the as-of close is still the
    # as-of close (check_freq=False: concat drops bdate_range's freq, which no gate reads).
    pd.testing.assert_series_equal(out.iloc[:-1], s, check_freq=False)
    # Feeding the as-of close back is NO LONGER the identity it was under replace.
    same_px = AP.probe_series(s, float(s.iloc[-1]))
    assert len(same_px) == len(s) + 1 and not same_px.index.equals(s.index)


@pytest.mark.parametrize("last,expect,naive", [
    # Fri -> Mon (the plain weekend step).
    ("2026-08-07", "2026-08-10", "2026-08-10"),
    # Christmas Eve -> the 26th. A business-day step lands ON Christmas.
    ("2025-12-24", "2025-12-26", "2025-12-25"),
    # 2026-07-04 falls on a Saturday, so Independence Day is OBSERVED on Friday the
    # 3rd: a business-day step lands on a closed market.
    ("2026-07-02", "2026-07-06", "2026-07-03"),
    # Thanksgiving 2026 (Thu 11-26) -> the half session on Friday still counts.
    ("2026-11-25", "2026-11-27", "2026-11-26"),
    # A Saturday tip is not itself a session and must still resolve forward.
    ("2026-08-08", "2026-08-10", "2026-08-10"),
])
def test_the_appended_bar_lands_on_an_nyse_session(last, expect, naive):
    """The label comes from the repo calendar, never from weekday arithmetic.

    A fabricated holiday bar is not a harmless off-by-one: every 2D/3D leg the gate
    reads is a POSITION in the session calendar (engine.session_anchor), so one extra
    session re-phases the whole cascade for that name.
    """
    got = AP.next_session_stamp(pd.Timestamp(last))
    assert str(got.date()) == expect
    if naive != expect:
        assert str((pd.Timestamp(last) + pd.tseries.offsets.BDay(1)).date()) == naive, (
            "the naive business-day step this case exists to refuse has moved")


def test_the_appended_bar_is_where_the_probe_puts_it(series):
    s = series["S00"]
    assert AP.probe_series(s, 1.0).index[-1] == AP.next_session_stamp(s.index[-1])


# ─────────────────────────────────────────────────────────────────────────────
# ...and WHY it matters: two frozen real series where the two constructions give
# OPPOSITE verdicts at the same price. Both are US names off the 2026-08-08 store,
# last 520 closes, committed — the test reads no store and no clock.
# ─────────────────────────────────────────────────────────────────────────────

FLIP_DIR = ROOT / "tests" / "fixtures" / "prophet_live"


def _frozen(kind: str) -> pd.Series:
    """A committed close series. ``float_precision="round_trip"`` is load-bearing: the
    default C parser is not correctly-rounded and shifted 57 of these 520 values in the
    last bits, which is not a difference this file may leave to luck."""
    df = pd.read_csv(FLIP_DIR / f"append_flip_{kind}_close.csv", parse_dates=["date"],
                     float_precision="round_trip")
    return pd.Series(df["close"].astype(float).values,
                     index=pd.DatetimeIndex(df["date"]))


def _replace_probe(close: pd.Series, candidate: float) -> pd.Series:
    """The OLD probe_series, written out here rather than imported — this file has to
    be able to state the defect after the defect is gone."""
    out = close.copy()
    out.iloc[-1] = float(candidate)
    return out


def test_replace_and_append_disagree_when_freshness_advances():
    """THE DEFECT, on a frozen real series (TILE, closes through 2026-08-07).

    Replacing the last bar freezes the cascade's tick count at yesterday's, so a cross
    that is 2 ticks old stays inside the just-crossed window forever. Tonight's nightly
    APPENDS a bar, the arrow ages to 3 ticks, and the freshness gate drops the name —
    the pack was publishing "buyable at this price" for a price at which tonight's gate
    says no. The assertion is on VERDICTS and the tick count, never on reason wording.
    """
    s = _frozen("freshness")
    assert len(s) == 520 and str(s.index[-1].date()) == "2026-08-07"
    px = float(s.iloc[-1])

    old = signal_gate.gate("TILE", _replace_probe(s, px))
    new = signal_gate.gate("TILE", AP.probe_series(s, px))
    assert signal_gate.is_buyable(old) is True, (
        "the replace-probe no longer reads buyable here — re-measure the flip set and "
        "refreeze the fixture, or this test proves nothing")
    assert signal_gate.is_buyable(new) is False, (
        "the appended bar no longer flips this name — refreeze the fixture from a name "
        "that still exercises the freshness advance")
    # The MECHANISM, not the message: the appended session aged the arrow past the
    # just-crossed window the gate admits on.
    assert new["ticks"] > old["ticks"]
    assert new.get("near_miss_reason") == "freshness_expired"
    assert old.get("tier_cascade") and new.get("tier_cascade") is None


def test_a_pending_buy_needs_the_next_bar_the_replace_probe_never_supplied():
    """The other half of the defect (SKY, same store date): reclaim-and-hold.

    signal_quality grades a just-fired buy ``pending`` until the NEXT bar confirms the
    hold. A replace-series never supplies one, so the name stayed eligible-as-pending at
    every probed price — a permanent "confirmation pending" that tonight's gate resolves
    the moment the bar exists. Here it resolves against the name.
    """
    s = _frozen("pending")
    assert len(s) == 520 and str(s.index[-1].date()) == "2026-08-07"
    px = float(s.iloc[-1])

    old = signal_gate.gate("SKY", _replace_probe(s, px))
    new = signal_gate.gate("SKY", AP.probe_series(s, px))
    assert old.get("sub") == "pending" and signal_gate.is_buyable(old) is True, (
        "the fixture is no longer a pending buy under replace — refreeze it")
    # The forward confirmation is no longer pending: the bar it waits for is there.
    assert new.get("sub") != "pending"
    assert signal_gate.is_buyable(new) is False


def test_the_pack_publishes_the_flip_instead_of_withholding_the_name():
    """The withholding decision, re-checked under append semantics (W-L0 gate 1).

    The membership check compares the published interval against the verdict AT the
    as-of close. Anchored on ``center_buyable`` — tonight's BOARD verdict — every one of
    these flipped names reads as a mismatch and has its levels withheld, which would
    have quietly deleted the armed board on the very night the fix started telling the
    truth. Anchored on the probe's own measurement it is consistent, and the name ships
    its honest levels.
    """
    s = _frozen("freshness")
    p = AP.build_pack([("TILE", s)], now=NOW, cfg={"max_probe": 50, "max_seconds": 3600})
    e = p["names"]["TILE"]
    assert e["center_buyable"] is True          # on tonight's board, unchanged
    assert e["probe_center_buyable"] is False   # ...but not at that price tonight
    assert AP.interval_contains(e, e["as_of_close"]) is False
    assert AP.membership_anchor(e) == (False, "probe_center_buyable")
    assert AP.self_check(p["names"]) == []
    assert p["meta"]["probe_center_flips"] == 1
    # The old anchor is what a pack WITHOUT the field falls back to — and it would have
    # withheld this name. This is the whole reason the field is published.
    legacy = {t: {k: v for k, v in row.items() if k != "probe_center_buyable"}
              for t, row in p["names"].items()}
    assert AP.membership_anchor(legacy["TILE"]) == (True, "center_buyable")
    assert AP.self_check(legacy), "the legacy anchor would not have flagged it — this " \
        "test is no longer showing why the anchor moved"


def test_a_flipped_board_name_keeps_the_levels_it_measured():
    """The same decision on a synthetic gate, so it cannot go vacuous on a re-phase.

    Shape taken from the real 2026-08-08 pack (ADAM/ALK/ANET): admitted at today's close
    on the store as it stands, but with tomorrow's bar appended the gate only admits the
    name over a DIFFERENT range — here one that sits ABOVE the close. The published
    ``fade_px`` above the as-of close is not a representation bug; it is the honest
    reading, and it must survive to the payload rather than being withheld.
    """
    p = AP.build_pack([("FLIP", _flat(100.0))], now=NOW,
                      gate_fn=_flips_on_append_gate(95.0, 105.0, 101.0, 104.0, 300))
    e = p["names"]["FLIP"]
    assert e["center_buyable"] is True and e["probe_center_buyable"] is False
    assert e["state"] == "buyable"
    assert e["fade_px"] is not None and e["fade_px"] > e["as_of_close"]
    assert e["fade_hi_px"] == pytest.approx(104.0, abs=0.05)
    assert AP.interval_contains(e, e["as_of_close"]) is False
    assert AP.self_check(p["names"]) == []                  # NOT withheld
    assert p["meta"]["edge_mismatches"] == []               # the real edge check agrees
    assert p["meta"]["probe_center_flips"] == 1


def test_an_anchor_that_comes_back_buyable_moves_the_band_floor_off_zero():
    """The other replace-assumption in the interval derivation, fail-closed.

    A name that is NOT on tonight's board gets an UP-ONLY sweep, and its band floor is 0
    because "below the close the centre verdict already says no". The replace probe made
    that true by construction — its centre call WAS the census call. With the bar
    appended it is a measurement, and it comes back TRUE for a few names (3 of 108
    cross-class names on the 2026-08-08 store). Such a name has no lower edge inside its
    span, so a 0 floor let ``interval_contains`` answer True at every price down to zero
    — none of which was probed. The floor is the span low instead, and the evaluator
    darks below it.
    """
    p = AP.build_pack([("UPFLIP", _flat(100.0))], now=NOW,
                      gate_fn=_flips_on_append_gate(200.0, 300.0, 90.0, 110.0, 300))
    e = p["names"]["UPFLIP"]
    assert e["center_buyable"] is False and e["probe_center_buyable"] is True
    assert e.get("trigger_px") is None and e["buyable_in_band"] is True
    assert e["band_lo_px"] == pytest.approx(100.0, abs=1e-3)
    assert AP.in_probed_band(e, 100.0) and not AP.in_probed_band(e, 99.0)
    assert AP.interval_contains(e, 100.0) is True
    assert AP.self_check(p["names"]) == []
    # An ordinary cross candidate — anchor False — keeps the 0 floor, because down there
    # the anchor really does answer the question.
    q = AP.build_pack([("PLAIN", _flat(95.0))], now=NOW,
                      gate_fn=_synth_gate(100.0, 105.0))
    assert q["names"]["PLAIN"]["band_lo_px"] == 0.0
    assert q["names"]["PLAIN"]["probe_center_buyable"] is False


def test_membership_anchor_falls_back_for_a_pack_without_the_field():
    """A pack built before the field existed had the two readings equal by construction,
    so ``center_buyable`` is the right answer there — and a wrong one nowhere."""
    assert AP.membership_anchor({"center_buyable": True}) == (True, "center_buyable")
    assert AP.membership_anchor({"center_buyable": False}) == (False, "center_buyable")
    assert AP.membership_anchor(
        {"center_buyable": True, "probe_center_buyable": False}) == (
            False, "probe_center_buyable")
    assert AP.membership_anchor({}) == (False, "center_buyable")


# ─────────────────────────────────────────────────────────────────────────────
# The interval contract
# ─────────────────────────────────────────────────────────────────────────────

def test_interval_contains_is_none_when_the_pack_cannot_say():
    """Unprobed and irregular names answer None so the evaluator darks them."""
    assert AP.interval_contains({"state": "dormant", "probed": False}, 10.0) is None
    assert AP.interval_contains({"state": "irregular", "probed": True}, 10.0) is None
    assert AP.interval_contains({}, 10.0) is None
    assert AP.interval_contains(
        {"state": "near", "probed": True, "buyable_in_band": None}, 10.0) is None


def test_interval_contains_bounds():
    e = {"state": "near", "probed": True, "buyable_in_band": True,
         "trigger_px": 100.0, "fade_hi_px": 110.0}
    assert AP.interval_contains(e, 99.99) is False
    assert AP.interval_contains(e, 100.0) is True
    assert AP.interval_contains(e, 110.0) is True
    assert AP.interval_contains(e, 110.01) is False
    unbounded = {"state": "near", "probed": True, "buyable_in_band": True,
                 "trigger_px": 100.0, "fade_hi_px": None}
    assert AP.interval_contains(unbounded, 10_000.0) is True
    empty = {"state": "dormant", "probed": True, "buyable_in_band": False}
    assert AP.interval_contains(empty, 100.0) is False


def test_lower_edge_prefers_fade_over_trigger():
    assert AP.lower_edge({"fade_px": 9.0, "trigger_px": 11.0}) == 9.0
    assert AP.lower_edge({"trigger_px": 11.0}) == 11.0
    assert AP.lower_edge({}) is None


def test_the_cross_class_probe_measures_nothing_below_the_as_of_close(pack, cfg):
    """The fact W-L0 gate 5 rests on: a cross-class span STARTS at the as-of close.

    No gate calls — this is the arithmetic of the span and the grid, asserted so that a
    future change which probes downward reds here and takes :func:`probe_floor` with it,
    instead of leaving the floor silently overstating what was measured.
    """
    cross = [e for e in pack["names"].values()
             if e.get("probed") and not e.get("center_buyable")]
    assert cross, "a floor test over no cross-class names proves nothing"
    for entry in cross:
        close = float(entry["as_of_close"])
        span = AP.probe_span(close, False, pack["band_pct"])
        grid = AP.probe_grid(span, pack["grid_points"])
        assert min(grid) == pytest.approx(close, rel=1e-9)
        assert span[1] > close


def test_probe_floor_is_the_measured_low_not_the_published_sentinel(pack):
    """W-L0 gate 5: ``band_lo_px`` is 0 for a cross-class name and that 0 is a sentinel.

    ``in_probed_band`` answers off the PUBLISHED band, so it keeps saying "in band" all
    the way to zero; ``probe_floor`` answers off what was swept. The two deliberately
    disagree, and the evaluator has to consult the second one or it reports a verdict
    over a region the pack never evaluated.
    """
    seen_cross = seen_board = False
    for entry in pack["names"].values():
        if not entry.get("probed"):
            continue
        floor = IV.probe_floor(entry)
        close = float(entry["as_of_close"])
        assert floor is not None and floor > 0.0
        if entry.get("center_buyable"):
            seen_board = True
            # A two-sided span: the published floor IS the measured one.
            assert floor == pytest.approx(float(entry["band_lo_px"]), rel=1e-9)
            assert floor < close
        else:
            seen_cross = True
            assert float(entry["band_lo_px"]) == 0.0          # the sentinel
            assert floor == pytest.approx(close, rel=1e-9)
            # The published band still answers below the floor. That gap is the whole
            # unprobed down-region, and it is why `unknown` exists.
            assert IV.in_probed_band(entry, close * 0.9) is True
    assert seen_cross and seen_board, "both classes must be exercised"


def test_probe_floor_refuses_to_invent_one_on_a_pre_band_pack(pack):
    """No span published ⇒ no floor. Fabricating one would declare a whole universe
    unmeasured on a schema skew, which is the failure in_probed_band's fallback exists
    to avoid."""
    entry = next(dict(e) for e in pack["names"].values() if e.get("probed"))
    entry.pop("band_lo_px", None)
    entry.pop("band_hi_px", None)
    assert IV.probe_floor(entry) is None


def test_self_check_catches_a_corrupted_interval(pack):
    """Fail-closed: a doctored level must be reported, not tolerated."""
    names = {t: dict(e) for t, e in pack["names"].items()}
    victim = next(t for t, e in names.items() if e.get("fade_px") is not None)
    names[victim]["fade_px"] = names[victim]["as_of_close"] * 1.5   # excludes tonight's close
    bad = AP.self_check(names)
    assert len(bad) == 1 and victim in bad[0]

    names2 = {t: dict(e) for t, e in pack["names"].items()}
    other = next(t for t, e in names2.items() if e.get("trigger_px") is not None)
    names2[other]["trigger_px"] = names2[other]["as_of_close"] * 0.5  # includes it wrongly
    assert any(other in line for line in AP.self_check(names2))


# ─────────────────────────────────────────────────────────────────────────────
# Structure, honesty and disclosure
# ─────────────────────────────────────────────────────────────────────────────

def _flat(last: float, n: int = 300) -> pd.Series:
    v = np.linspace(90.0, 95.0, n)
    v[-1] = last
    return pd.Series(v, index=IDX[:n])


def _synth_gate(lo: float, hi: float):
    """A stub gate buyable exactly on [lo, hi] — for the structure cases the real
    engine will not produce on demand."""
    def g(ticker, s):
        ok = lo <= float(s.iloc[-1]) <= hi
        return {"eligible": ok, "tier_cascade": "T2" if ok else None, "bars_to_cross": 1}
    return g


def _flips_on_append_gate(now_lo: float, now_hi: float, next_lo: float, next_hi: float,
                          n_raw: int):
    """A stub whose admitted range MOVES once the series gains a bar.

    The one property a price-only stub cannot express, and the one the whole W-L0 fix
    turns on: the census (the store as it stands, ``n_raw`` bars) and the probe (one
    appended bar) are different questions. Length is the tell here; in the engine it is
    the freshness tick count and the reclaim-and-hold confirmation.
    """
    def g(ticker, s):
        lo, hi = (now_lo, now_hi) if len(s) <= n_raw else (next_lo, next_hi)
        ok = lo <= float(s.iloc[-1]) <= hi
        return {"eligible": ok, "tier_cascade": "T2" if ok else None, "bars_to_cross": 1}
    return g


def test_oscillating_structure_is_irregular_not_a_threshold():
    def osc(ticker, s):
        ok = int(float(s.iloc[-1]) * 2) % 2 == 0
        return {"eligible": ok, "tier_cascade": "T2" if ok else None}
    p = AP.build_pack([("OSC", _flat(95.0))], now=NOW, gate_fn=osc)
    e = p["names"]["OSC"]
    assert e["state"] == "irregular"
    assert "trigger_px" not in e and "fade_px" not in e
    assert p["meta"]["skipped"]["irregular"] == 1
    assert AP.interval_contains(e, 95.0) is None
    assert AP.self_check(p["names"]) == []      # irregular names are skipped, not failed


@pytest.mark.parametrize(
    "label,last,lo,hi,state,has_trigger,has_fade,has_hi",
    [("NEAR", 95.0, 100.0, 105.0, "near", True, False, True),
     ("BUYABLE", 100.0, 95.0, 105.0, "buyable", False, True, True),
     ("DORMANT", 95.0, 500.0, 600.0, "dormant", False, False, False),
     ("OPEN_UP", 95.0, 100.0, 1e9, "near", True, False, False)])
def test_state_and_field_shapes(label, last, lo, hi, state, has_trigger, has_fade, has_hi):
    p = AP.build_pack([(label, _flat(last))], now=NOW, gate_fn=_synth_gate(lo, hi))
    e = p["names"][label]
    assert e["state"] == state
    assert (e.get("trigger_px") is not None) is has_trigger
    assert (e.get("fade_px") is not None) is has_fade
    assert (e.get("fade_hi_px") is not None) is has_hi
    assert AP.self_check(p["names"]) == []


# ─────────────────────────────────────────────────────────────────────────────
# The class-split probe budget (operator ruling 2026-07-29)
# ─────────────────────────────────────────────────────────────────────────────

def test_the_cross_class_floor_holds_however_long_the_board_takes():
    """THE INVARIANT. Ordering alone could not fund both classes.

    Every board name outranks every cross candidate in probe_priority, so a saturating
    board population consumed the whole budget: 106 fade levels armed against 4
    triggers, on a program whose core evidence is the cross ledger. The floor cannot
    depend on how the board slice went, because a running gate call is not interruptible
    and the board slice can overshoot its window by up to one call.
    """
    budget, share = 200.0, 0.4
    board_win, floor = AP.class_windows(budget, share)
    assert board_win == pytest.approx(80.0)
    assert floor == pytest.approx(120.0)
    # Board finishes early -> the cross class inherits the slack.
    assert AP.cross_window(budget, share, 10.0) == pytest.approx(190.0)
    # Board spends exactly its window -> the cross class gets precisely its floor.
    assert AP.cross_window(budget, share, board_win) == pytest.approx(120.0)
    # Board OVERRUNS, even absurdly -> the floor still holds. This is the invariant.
    for overrun in (100.0, 200.0, 5_000.0):
        assert AP.cross_window(budget, share, overrun) == pytest.approx(floor)


@pytest.mark.parametrize("share,board,cross", [(0.0, 0.0, 100.0), (1.0, 100.0, 0.0),
                                               (0.5, 50.0, 50.0),
                                               (-1.0, 0.0, 100.0), (9.0, 100.0, 0.0)])
def test_class_windows_clamps_a_nonsense_share(share, board, cross):
    assert AP.class_windows(100.0, share) == (pytest.approx(board), pytest.approx(cross))


def test_the_name_cap_is_split_on_the_same_share_as_the_clock():
    """Capping names globally would leave the hole the split exists to close: the board
    class takes every slot and the cross class has wall clock but nothing to spend it on.
    """
    recs = {}
    for i in range(40):
        recs[f"B{i:02d}"] = {"ticker": f"B{i:02d}", "wants_probe": True,
                             "center_buyable": True, "center_verdict": {"bars_to_cross": 1}}
    for i in range(40):
        recs[f"C{i:02d}"] = {"ticker": f"C{i:02d}", "wants_probe": True,
                             "center_buyable": False, "center_verdict": {"bars_to_cross": 1}}
    skipped: dict[str, int] = {}
    split = AP.split_probes(recs, AP.pack_cfg({"prophet_live": {"max_probe": 10,
                                                               "board_probe_share": 0.4}}),
                            skipped)
    assert len(split["board"]) == 4 and len(split["cross"]) == 6
    assert all(t.startswith("B") for t in split["board"])
    assert all(t.startswith("C") for t in split["cross"])
    # Both cuts are disclosed, per class.
    assert skipped == {"probe_cap_board": 36, "probe_cap_cross": 34}
    # order_probes spends board first, then cross.
    flat = AP.order_probes(recs, AP.pack_cfg({"prophet_live": {"max_probe": 10,
                                                              "board_probe_share": 0.4}}),
                           {})
    assert [t[0] for t in flat] == ["B"] * 4 + ["C"] * 6


def test_a_saturating_board_population_still_leaves_cross_names_queued():
    """The end-to-end shape of the ruling: crosses are never starved to zero."""
    recs = {f"B{i:03d}": {"ticker": f"B{i:03d}", "wants_probe": True,
                          "center_buyable": True, "center_verdict": {}}
            for i in range(500)}
    recs["C1"] = {"ticker": "C1", "wants_probe": True, "center_buyable": False,
                  "center_verdict": {}}
    split = AP.split_probes(recs, AP.pack_cfg(None), {})
    assert split["cross"] == ["C1"]
    assert len(split["board"]) == round(180 * 0.4)


def test_per_class_counts_land_in_meta(pack):
    """A single armed_n cannot show the split working — 106+4 and 55+55 both read 110."""
    by = pack["meta"]["by_class"]
    assert set(by) == {"board", "cross"}
    for cls, cc in by.items():
        for key in ("candidates_n", "probed_n", "armed_n", "probe_seconds"):
            assert key in cc, (cls, key)
        assert cc["probed_n"] <= cc["candidates_n"]
        assert cc["armed_n"] <= cc["probed_n"]
    assert sum(cc["candidates_n"] for cc in by.values()) == pack["meta"]["universe_n"]
    assert sum(cc["armed_n"] for cc in by.values()) == pack["meta"]["armed_n"]
    assert sum(cc["probed_n"] for cc in by.values()) == pack["meta"]["probed_n"]
    assert pack["meta"]["board_probe_share"] == 0.4
    # The seeded fixtures carry both classes, so neither column is vacuous.
    assert by["board"]["armed_n"] >= 1 and by["cross"]["armed_n"] >= 1


def test_probe_cap_is_disclosed_not_silent():
    """Pinned change: the cap key is now PER CLASS (``probe_cap_board`` /
    ``probe_cap_cross``), because the name cap is split on the same share as the wall
    clock — a single global key could not say which class was cut."""
    entries = [(f"N{i:02d}", _flat(95.0)) for i in range(6)]
    p = AP.build_pack(entries, now=NOW, cfg={"max_probe": 4, "board_probe_share": 0.5},
                      gate_fn=_synth_gate(100.0, 105.0))
    # All six are cross candidates (not buyable at 95), so only the cross slice binds:
    # cap 4 x 0.5 = 2 names, 4 cut.
    assert p["meta"]["skipped"]["probe_cap_cross"] == 4
    assert "probe_cap_board" not in p["meta"]["skipped"]
    assert p["meta"]["wanted_probe_n"] == 6
    assert p["meta"]["probed_n"] == 2
    assert p["meta"]["by_class"]["cross"]["probed_n"] == 2
    unprobed = [e for e in p["names"].values() if not e["probed"]]
    assert len(unprobed) == 4
    # An unprobed name carries NO threshold and answers None — never "dormant" as a
    # claim the pack cannot support.
    for e in unprobed:
        assert e.get("trigger_px") is None and e.get("fade_px") is None
        assert AP.interval_contains(e, 95.0) is None


def test_stale_series_is_not_probed_against_a_stale_close():
    """Mixed-asof law: a name whose bar trails the tip ships unprobed and marked.

    Its state is ``stale``, NOT ``dormant`` (m1): no gate ran for it, so counting it as
    an affirmative "nothing forming here" in meta.states was a quiet honesty bug with a
    1,500-name denominator.
    """
    fresh = _flat(95.0)
    stale = pd.Series(np.linspace(90.0, 95.0, 300), index=IDX[:300] - pd.Timedelta(days=30))
    p = AP.build_pack([("FRESH", fresh), ("STALE", stale)], now=NOW,
                      gate_fn=_synth_gate(100.0, 105.0))
    assert p["as_of"] == str(fresh.index[-1].date())
    e = p["names"]["STALE"]
    assert e["probed"] is False and e["skip"] == "stale_series"
    assert e["state"] == "stale" and "stale" in AP.STATES
    assert e["stale_sessions"] >= 4
    assert p["meta"]["skipped"]["stale_series"] == 1
    assert p["meta"]["states"].get("dormant", 0) == 0     # never a verdict
    assert p["names"]["FRESH"]["probed"] is True


# ─────────────────────────────────────────────────────────────────────────────
# B2 — the probed band is published so the evaluator never extrapolates
# ─────────────────────────────────────────────────────────────────────────────

def test_every_probed_entry_publishes_the_band_it_actually_swept(pack, cfg):
    for tkr, e in pack["names"].items():
        if not e.get("probed"):
            continue
        assert e["band_hi_px"] >= e["as_of_close"], tkr
        if e["center_buyable"]:
            # Two-sided sweep: the floor is the real span low, so a deep gap darks.
            assert 0.0 < e["band_lo_px"] <= e["as_of_close"], tkr
            expect = e["as_of_close"] * (1 - cfg["band_pct"] / 100.0)
            assert e["band_lo_px"] == pytest.approx(expect, abs=1e-3), tkr
        else:
            # Up-only sweep: below the close the centre verdict already answers.
            assert e["band_lo_px"] == 0.0, tkr
        expect_hi = e["as_of_close"] * (1 + cfg["band_pct"] / 100.0)
        assert e["band_hi_px"] == pytest.approx(expect_hi, abs=1e-3), tkr


def test_the_band_is_rounded_outward_so_a_probed_price_is_never_darked(pack, cfg):
    """Inward rounding would dark prices the probe genuinely evaluated."""
    for tkr, e in pack["names"].items():
        if not e.get("probed"):
            continue
        span = AP.probe_span(e["as_of_close"], e["center_buyable"], cfg["band_pct"])
        for px in AP.probe_grid(span, cfg["grid_points"]):
            assert AP.in_probed_band(e, px), f"{tkr} darks its own grid point {px}"


def test_in_probed_band_rejects_prices_the_pack_never_saw():
    buy = {"probed": True, "center_buyable": True, "band_lo_px": 85.0, "band_hi_px": 115.0}
    assert AP.in_probed_band(buy, 85.0) and AP.in_probed_band(buy, 115.0)
    assert not AP.in_probed_band(buy, 84.99)
    assert not AP.in_probed_band(buy, 115.01)
    up_only = {"probed": True, "center_buyable": False, "band_lo_px": 0.0,
               "band_hi_px": 109.25}
    assert AP.in_probed_band(up_only, 1.0)      # downward is knowledge, not guesswork
    assert not AP.in_probed_band(up_only, 109.26)
    # A pack predating the fields must not dark a whole universe.
    assert AP.in_probed_band({"probed": True}, 1e9)


def test_as_of_is_the_store_tip_not_the_wall_clock(series):
    """The pack says what it is armed on. A wall date would lie on a stale-store night."""
    p = AP.build_pack([("S00", series["S00"])], now=NOW, gate_fn=_synth_gate(0.0, 1e9))
    assert p["as_of"] == str(IDX[519].date())
    assert p["as_of"] != NOW.date().isoformat()
    assert p["built_at"] == "2026-07-29T22:30:00Z"


def test_nan_tail_is_dropped_before_probing():
    """A wide breadth cache leaves NaN tails; replacing one would invent a bar."""
    s = _flat(95.0)
    padded = pd.concat([s, pd.Series([np.nan] * 5,
                                     index=pd.bdate_range(s.index[-1], periods=6)[1:])])
    cleaned = AP.clean_closes(padded)
    assert len(cleaned) == len(s) and cleaned.iloc[-1] == 95.0
    assert AP.clean_closes(pd.Series([np.nan, np.nan])) is None
    p = AP.build_pack([("PAD", padded)], now=NOW, gate_fn=_synth_gate(100.0, 105.0))
    assert p["names"]["PAD"]["bar_date"] == str(s.index[-1].date())


def test_meta_discloses_scope_and_coverage(pack):
    m = pack["meta"]
    assert m["probe_scope"] == "two_sided_for_buyable__up_only_for_rest"
    assert m["probe_order"]
    for k in ("universe_n", "probed_n", "armed_n", "wanted_probe_n", "gate_calls",
              "build_seconds", "states", "skipped"):
        assert k in m, k
    assert pack["schema"] == "prophet_live.armed/v1"
    assert pack["band_pct"] and pack["grid_points"] and pack["bisect_iters"]


def test_payload_is_json_safe_without_nan(pack):
    """R2 gets allow_nan=False JSON; a NaN anywhere would make the pack unpublishable."""
    json.dumps(pack, allow_nan=False)


def test_probe_priority_puts_board_names_first():
    buy = {"ticker": "B", "center_buyable": True, "center_verdict": {"bars_to_cross": 9}}
    elig = {"ticker": "E", "eligible": True, "center_verdict": {"bars_to_cross": 1}}
    near = {"ticker": "N", "center_verdict": {"bars_to_cross": 1}}
    far = {"ticker": "F", "center_verdict": {"bars_to_cross": 8}}
    hist = {"ticker": "H", "center_verdict": {"hist_d2": -0.2}}
    blind = {"ticker": "Z", "center_verdict": {}}
    order = sorted([blind, far, hist, near, elig, buy], key=AP.probe_priority)
    assert [r["ticker"] for r in order] == ["B", "E", "N", "F", "H", "Z"]


# ─────────────────────────────────────────────────────────────────────────────
# The CLI contract
# ─────────────────────────────────────────────────────────────────────────────

def test_pack_config_resolves_from_config_yml():
    """The knobs the budget depends on must actually come from config.yml."""
    import yaml
    conf = yaml.safe_load((ROOT / "config.yml").read_text(encoding="utf-8"))
    block = conf["prophet_live"]
    resolved = AP.pack_cfg(conf)
    for key in ("band_pct", "grid_points", "bisect_iters", "max_probe", "max_seconds",
                "max_lag_sessions"):
        assert key in block, f"config.yml prophet_live is missing {key}"
        assert resolved[key] == block[key], key
    # A grid cell refined by bisect_iters halvings must land inside ~1 bp, which is
    # the precision the published thresholds claim.
    cell = block["band_pct"] / (block["grid_points"] - 1)
    assert cell / (2 ** block["bisect_iters"]) < 0.01, "edge precision is worse than 1 bp"


def test_the_nightly_wiring_exists_and_is_ordered(tmp_path):
    """A builder with no workflow caller is a dead wire; the repo has shipped several.

    Ordering is load-bearing too: the reconciler treats tonight's pack as tonight's
    verdict set, so it MUST run after the arming pass.
    """
    import yaml
    daily = yaml.safe_load((ROOT / ".github" / "workflows" / "daily.yml").read_text(
        encoding="utf-8"))
    steps = [s for job in daily["jobs"].values() for s in (job.get("steps") or [])]
    runs = [str(s.get("run") or "") for s in steps]
    pack_at = next(i for i, r in enumerate(runs) if "scripts.build_prophet_live_pack" in r)
    rec_at = next(i for i, r in enumerate(runs) if "scripts.reconcile_prophet_live" in r)
    assert pack_at < rec_at, "the reconciler must run AFTER the arming pass"
    # Both must be non-fatal: neither may ever abort the nightly deploy.
    for i in (pack_at, rec_at):
        assert steps[i].get("continue-on-error") is True
    assert "--publish" in runs[pack_at]
    assert "--nightly" in runs[rec_at]
    # The reconciler reads the pack the same run just built, not last night's R2 copy.
    assert "--pack" in runs[rec_at] and "RUNNER_TEMP" in runs[rec_at]
    # ... and the pack's local copy goes to RUNNER_TEMP, never a data/ path.
    assert "--out \"$RUNNER_TEMP" in runs[pack_at]
    assert "data/" not in runs[pack_at]


def test_cli_rejects_an_unparseable_now():
    """--now is the injectable clock; a bad value must fail loudly, not default to now."""
    r = subprocess.run([sys.executable, "-m", "scripts.build_prophet_live_pack",
                        "--now", "not-a-timestamp", "--limit", "1"],
                       cwd=ROOT, capture_output=True, text=True, timeout=180)
    assert r.returncode == 2
    line = next(ln for ln in r.stdout.splitlines() if "unparseable" in ln)
    assert line.startswith("::error title=prophet-live-pack::")


def test_parity_error_annotation_is_a_bare_line_start_print(monkeypatch, capsys, series):
    """A parity failure must reach the Actions summary — and must NOT publish.

    ``log.warning("::error ...")`` emits ``WARNING ::error ...`` and GitHub silently
    drops it; that has shipped dead five times. The structural sweep lives in
    tests/test_gh_annotation_line_start.py (AST, whole repo); this asserts the
    behaviour of the one annotation the program's fail-closed gate depends on.
    """
    import scripts.build_prophet_live_pack as B

    # S18 is the buyable board name whose published interval is fade-defined — the
    # doctored fade below must therefore break parity (a near name's fade is not
    # load-bearing, so S00 stopped working here when the sq-anchor moved it to near).
    good = AP.build_pack([("S18", series["S18"])], now=NOW,
                         cfg={"max_probe": 50, "max_seconds": 3600})
    victim = next(t for t, e in good["names"].items() if AP.lower_edge(e) is not None)
    good["names"][victim]["fade_px"] = good["names"][victim]["as_of_close"] * 1.5
    good["names"][victim]["trigger_px"] = None

    published: list[str] = []
    monkeypatch.setattr(B, "build", lambda **kw: good)
    monkeypatch.setattr(B.r2io, "put_json", lambda key, payload, **kw: published.append(key))
    rc = B.main(["--publish"])

    assert rc == 1
    assert published == [], "a pack that failed parity must NEVER be published"
    err = [ln for ln in capsys.readouterr().out.splitlines() if "::error" in ln]
    assert err, "the parity failure produced no annotation at all"
    assert err[0].startswith("::error title=prophet-live-pack-parity::"), err[0]
