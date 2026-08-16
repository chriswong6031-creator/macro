"""Stock Identity W2 — the leak fixtures, on synthetic frames (registration §7).

Two halves, and the second is the load-bearing one:

**A. The real families pass.** Every recomputed family is run through the fixture set on a
deterministic synthetic tape, so the property is exercised in CI whether or not
``data/stock_identity`` is checked out. No network, no plotting stack, no collector import.

**B. The fixtures can FAIL.** A guard that has never rejected anything is not evidence
(``receipt-written-from-the-same-variable-cannot-fail``). Each fixture is therefore run
against a deliberately broken detector built to violate exactly that fixture's property —
a look-ahead detector for truncation invariance, a window-anchored one for the start
audit, a provisional-bar reader for the forming-bar audit, and a pre-knowability emitter
for feed truncation — and is required to reject it. A fixture that passes a leaky detector
would have shipped the leak.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest

from engine.stock_identity.replay import events as ev
from engine.stock_identity.replay import leak as leak_mod
from engine.stock_identity.replay import (
    bottom_watch as bw_mod,
    confirmed_buy as cb_mod,
    grey_dot as gd_mod,
    naive as naive_mod,
    starter as starter_mod,
    tiers as tier_mod,
    washout_turn as wt_mod,
)

PLANE = "stocks_tr_v1"
SYMBOL = "SYN"


def _synthetic_frame(n: int = 2600, seed: int = 20260814) -> pd.DataFrame:
    """A deterministic tape with real cycles, so the detectors actually fire.

    A pure random walk barely triggers oversold-cross families; a walk with a slow
    sinusoidal drift plus fat-tailed noise produces the washouts and reclaims these
    detectors are shaped for, which is what makes the fixtures non-vacuous.
    """
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2010-01-04", periods=n)
    t = np.arange(n)
    trend = 0.00025 * t
    cycle = 0.35 * np.sin(2 * np.pi * t / 240.0) + 0.18 * np.sin(2 * np.pi * t / 61.0)
    shock = rng.standard_t(df=4, size=n) * 0.012
    logp = np.log(50.0) + trend + cycle + np.cumsum(shock) * 0.35
    close = np.exp(logp)
    span = np.abs(rng.normal(0.0, 0.008, size=n)) + 0.002
    df = pd.DataFrame(
        {
            "open": close * (1.0 + rng.normal(0.0, 0.003, size=n)),
            "high": close * (1.0 + span),
            "low": close * (1.0 - span),
            "close": close,
            "volume": rng.integers(1_000_000, 9_000_000, size=n).astype(float),
        },
        index=idx,
    )
    df.index.name = "Date"
    return df


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    return _synthetic_frame()


# ---------------------------------------------------------------------------
# A. the real families
# ---------------------------------------------------------------------------
def _grey(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows, _ = gd_mod.macro_fires(
        df, symbol=SYMBOL, price_plane_id=PLANE,
        spec_hash=ev.spec_hash(gd_mod.macro_constants()), family_first_available=None)
    return rows


def _terminal(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows, _ = gd_mod.terminal_fires(
        df, symbol=SYMBOL, price_plane_id=PLANE,
        spec_hash=ev.spec_hash(gd_mod.terminal_constants()), family_first_available=None)
    return rows


def _cb(df: pd.DataFrame) -> list[dict[str, Any]]:
    return cb_mod.recompute_fires(
        df, symbol=SYMBOL, price_plane_id=PLANE,
        spec_hash=ev.spec_hash(cb_mod.constants()), family_first_available=None,
        ledger_first_date=None)


def _tiers(df: pd.DataFrame) -> list[dict[str, Any]]:
    return tier_mod.fires(
        df, symbol=SYMBOL, price_plane_id=PLANE,
        spec_hash=ev.spec_hash(tier_mod.constants()), family_first_available=None)


def _bottom(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows, _ = bw_mod.fires(
        df, symbol=SYMBOL, price_plane_id=PLANE,
        spec_hash=ev.spec_hash(bw_mod.constants()), family_first_available=None)
    return rows


def _starter(df: pd.DataFrame) -> list[dict[str, Any]]:
    return starter_mod.signature_fires(
        df, symbol=SYMBOL, price_plane_id=PLANE,
        spec_hash=ev.spec_hash(starter_mod.constants()), family_first_available=None)


def _naive(df: pd.DataFrame) -> list[dict[str, Any]]:
    return naive_mod.fires(
        df, symbol=SYMBOL, price_plane_id=PLANE,
        spec_hashes={k: ev.spec_hash(naive_mod.constants(k)) for k in naive_mod.FAMILY_KEYS},
        family_first_available={k: None for k in naive_mod.FAMILY_KEYS})


def _washout(df: pd.DataFrame) -> list[dict[str, Any]]:
    """The organ's shipped replay: ``step=1``, the truncated-frame walk exactly as run.

    A stride was tried and rejected: sampling every k-th weekly bar makes the fixture cheap
    but changes WHICH bars are read, so dropping leading sessions re-samples a different
    subset and the start audit fails for a reason that has nothing to do with the organ
    (measured: 10 differences on 4 events at ``step=8``). A fixture that exercises a
    configuration the pipeline never runs is not evidence about the pipeline, so this runs
    the real thing on a shorter tape instead.
    """
    return wt_mod.recompute_fires(
        df, symbol=SYMBOL, price_plane_id=PLANE,
        spec_hash=ev.spec_hash(wt_mod.constants()), family_first_available=None, step=1)


#: The one declared exemption, mirrored from the pilot CLI so the test and the pipeline
#: cannot disagree about what was excused.
WASHOUT_EXEMPTIONS = {
    "shift_audit_start_invariance": (
        "NOT APPLICABLE, mechanism named: engine.washout_turn's depth percentile is a "
        "declared WHOLE-SAMPLE statistic, so its reference distribution depends on how "
        "much history exists. Past-data window dependence, not future leakage."
    )
}

FAMILIES = {
    "grey_dot_macro": _grey,
    "grey_dot_terminal": _terminal,
    "confirmed_buy_recompute": _cb,
    "tier_cascade": _tiers,
    "bottom_watch_terminal": _bottom,
    "starter_signature": _starter,
    "naive_comparators": _naive,
}


class TestEveryRecomputedFamilyPassesItsFixtures:
    @pytest.mark.parametrize("name", sorted(FAMILIES))
    def test_fixtures_are_green(self, name, frame):
        results = leak_mod.run_recompute_fixtures(FAMILIES[name], frame)
        failed = [r for r in results if not r["passed"]]
        assert not failed, f"{name}: " + "; ".join(
            f"{r['name']} — {r['detail']}" for r in failed)

    @pytest.mark.parametrize("name", sorted(FAMILIES))
    def test_the_family_actually_fires_on_this_tape(self, name, frame):
        # A fixture that passes because nothing fired proves nothing.
        assert FAMILIES[name](frame), (
            f"{name} produced no events on the synthetic tape, so its fixtures are vacuous"
        )

    def test_the_weekly_organ_passes_its_applicable_fixtures(self):
        # Its replay is a truncated-frame walk (quadratic in weekly bars), so it gets a
        # shorter tape rather than a strided walk — see :func:`_washout`. Its start audit
        # is a DECLARED EXEMPTION with the mechanism named, not a pass.
        frame = _synthetic_frame(n=1800, seed=20260815)
        results = leak_mod.run_recompute_fixtures(
            _washout, frame, exemptions=WASHOUT_EXEMPTIONS)
        failed = [r for r in results if r["applicable"] and not r["passed"]]
        assert not failed, "; ".join(f"{r['name']} — {r['detail']}" for r in failed)
        exempt = [r for r in results if not r["applicable"]]
        assert len(exempt) == 1
        assert "WHOLE-SAMPLE" in exempt[0]["detail"], (
            "an exemption without its mechanism named is a loosened ceiling wearing a "
            "different hat"
        )

    def test_the_organs_start_dependence_is_real_and_the_check_sees_it(self):
        # The exemption is only honest if the unexempted check actually fails — otherwise
        # the family is being excused from a bar it would have cleared.
        frame = _synthetic_frame(n=1800, seed=20260815)
        r = leak_mod.shift_audit_start_invariance(_washout, frame)
        assert not r["passed"], (
            "the weekly organ now passes the start audit — retire the exemption rather "
            "than carrying a stale one"
        )


# ---------------------------------------------------------------------------
# B. the fixtures can fail — one deliberately broken detector per property
# ---------------------------------------------------------------------------
def _event_at(ts, known, subtype="s") -> dict[str, Any]:
    return ev.make_event(
        family_key="broken", producer="p", family="f", subtype=subtype, stage="S",
        symbol=SYMBOL, price_plane_id=PLANE, grain="1D",
        signal_ts=ts, signal_known_ts=known, known_basis="daily_close",
        signal_era="e", detector_spec_hash="h", source_hash="h",
        field_origin="replay_recomputed", provenance_class="R",
        family_first_available=None,
    )


class TestTheFixturesRejectABrokenDetector:
    def test_truncation_invariance_rejects_a_look_ahead_detector(self, frame):
        def leaky(df: pd.DataFrame) -> list[dict[str, Any]]:
            # Fires where the close is the minimum of ALL REMAINING sessions — the
            # hindsight bottom-picker. Its look-ahead is unbounded, so shortening the
            # future rewrites the past far inside the fixture's settling margin.
            c = df["close"].astype(float)
            running_future_min = c[::-1].cummin()[::-1]
            hits = c.index[(c <= running_future_min).to_numpy()]
            return [_event_at(t, t) for t in hits]

        r = leak_mod.truncation_invariance(leaky, frame)
        assert not r["passed"], "a look-ahead detector passed truncation invariance"

    def test_start_invariance_rejects_a_window_anchored_detector(self, frame):
        def window_anchored(df: pd.DataFrame) -> list[dict[str, Any]]:
            # Buckets by POSITION IN THE CALLER'S WINDOW — the retired 3B defect. Every
            # event moves when the caller hands in a different amount of leading history.
            idx = pd.DatetimeIndex(df.index)
            # 40 is coprime to the fixture's 37-row drop, so the phase genuinely moves.
            sel = np.arange(len(idx)) % 40 == 0
            return [_event_at(t, t) for t in idx[sel]]

        r = leak_mod.shift_audit_start_invariance(window_anchored, frame)
        assert not r["passed"], "a window-anchored detector passed the start audit"

    def test_forming_bar_audit_rejects_a_provisional_bar_reader(self, frame):
        def reads_the_forming_bar(df: pd.DataFrame) -> list[dict[str, Any]]:
            # Qualifies EVERY past bar against the frame's final close, so the
            # still-forming last bar rewrites which historical bars fired — the
            # provisional-basis defect, in its purest form.
            c = df["close"].astype(float)
            idx = pd.DatetimeIndex(df.index)
            hits = idx[(c < float(c.iloc[-1])).to_numpy()]
            return [_event_at(t, t) for t in hits]

        r = leak_mod.shift_audit_forming_bar(reads_the_forming_bar, frame)
        assert not r["passed"], "a provisional-bar reader passed the forming-bar audit"

    def test_feed_truncation_rejects_an_event_knowable_before_its_known_ts(self, frame):
        def premature(df: pd.DataFrame) -> list[dict[str, Any]]:
            # Claims a known_ts two sessions out but computes purely from the signal bar,
            # so truncating the feed at signal_ts leaves the event standing — the exact
            # pre-#392 bug.
            c = df["close"].astype(float)
            idx = pd.DatetimeIndex(df.index)
            ret = (c / c.shift(1) - 1.0).fillna(0.0).to_numpy()
            rows: list[dict[str, Any]] = []
            for i in np.flatnonzero(ret > 0.03):
                j = min(int(i) + 2, len(idx) - 1)
                rows.append(_event_at(idx[int(i)], idx[j]))
            return rows

        r = leak_mod.feed_truncation(premature, frame)
        assert not r["passed"], "an event that survives feed truncation was accepted"

    def test_append_only_conformance_rejects_an_invented_row(self):
        store = pd.DataFrame({
            "ticker": ["AAA", "AAA"],
            "date": pd.to_datetime(["2026-01-05", "2026-01-06"]),
            "type": ["buy", "rebuy"],
        })
        emitted = [_event_at("2026-01-05", "2026-01-05"),
                   _event_at("2020-07-07", "2020-07-07")]   # not in the store
        for r in emitted:
            r["symbol"] = "AAA"
        res = leak_mod.append_only_conformance(
            emitted, store, store_key=("ticker", "date", "type"),
            date_column="date", symbol_column="ticker")
        assert not res["passed"], "an invented ledger row passed append-only conformance"

    def test_append_only_conformance_accepts_a_pure_filter(self):
        store = pd.DataFrame({
            "ticker": ["AAA", "AAA"],
            "date": pd.to_datetime(["2026-01-05", "2026-01-06"]),
            "type": ["buy", "rebuy"],
        })
        emitted = [_event_at("2026-01-05", "2026-01-05")]
        emitted[0]["symbol"] = "AAA"
        res = leak_mod.append_only_conformance(
            emitted, store, store_key=("ticker", "date", "type"),
            date_column="date", symbol_column="ticker")
        assert res["passed"], res["detail"]


class TestFixtureVerdictShape:
    def test_a_result_reports_its_name_and_detail(self, frame):
        r = leak_mod.truncation_invariance(_grey, frame)
        assert set(r) == {"name", "passed", "applicable", "detail"}
        assert r["applicable"] is True
        assert r["name"] == "truncation_invariance"
        assert r["detail"], "a verdict with no detail cannot be audited"

    def test_the_start_audit_always_reports_its_measured_rate(self, frame):
        r = leak_mod.shift_audit_start_invariance(_grey, frame)
        assert "%" in r["detail"], (
            "the measured flip rate must be printed whether the check passes or fails, "
            "so an upward drift is visible before it crosses the ceiling"
        )
