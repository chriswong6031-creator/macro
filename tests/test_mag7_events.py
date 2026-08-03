"""Tests for the Mag-7 event lens (F1) + its notification source (g).

Charter: research/POSTMORTEM_20260803_MAG7_RALLY_SILENCE_BY_FABLE.md §6.
The week MSFT printed +21.75% in five sessions — the 99.90th percentile of its
own 40-year history — every surface was silent, because the only cohort organ
still computing reads a cap-weighted composite that AAPL+NVDA dilution held at
`rolling_over` all week.  The event lens states the per-member fact instead.

Covers (synthetic parquet fixtures via tmp_path, no network):
  1. deep-history spike → tier "historic", pctile >= 99.5, record → no
     last_larger_date; a milder spike → "extreme"; <15y history caps at
     "extreme" no matter how extreme the percentile
  2. down-side mirror: a −25% week → "historic" with pctile <= 0.5
  3. cohort kinds: split / broad_up / null-when-quiet, and events.display
  4. ledger row carries events and stays idempotent by date
  5. the historic-tier GitHub annotation STARTS its line (house law) — asserted
     via capsys, never caplog
  6. notify source (g): historic entry fires once, dedups, ignores stale as_of
  7. fail-soft: a corrupt deep parquet degrades that member to the ohlcv span,
     and snapshot() still returns

DOCTRINE the tests pin (not just mechanics): the block is display-tier plain
data — no direction word, no forecast, and no rank/size/gate authority.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

MAG7 = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]

_TODAY = str(date.today())


# ---------------------------------------------------------------------------
# Fixtures — synthetic price series
# ---------------------------------------------------------------------------

def _bdays(n: int, end: str | None = None) -> pd.DatetimeIndex:
    return pd.bdate_range(end=end or _TODAY, periods=n)


def _data(tmp: Path) -> Path:
    d = tmp / "data"
    d.mkdir(exist_ok=True)
    return d


def _write_ohlcv(tmp: Path, sym: str, series: pd.Series) -> None:
    out = _data(tmp) / "baskets" / "ohlcv" / f"{sym}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"close": series})
    df.index.name = "Date"
    df.to_parquet(out)


def _write_deep(tmp: Path, sym: str, series: pd.Series) -> None:
    out = _data(tmp) / "stocks" / f"{sym}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"close": series})
    df.index.name = "Date"
    df.to_parquet(out)


def _write_spy(tmp: Path, series: pd.Series) -> None:
    out = _data(tmp) / "yahoo" / "SPY.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"close": series})
    df.index.name = "Date"
    df.to_parquet(out)


def _quiet_series(n: int, end: str | None = None, seed: int = 7) -> pd.Series:
    """Low-amplitude wiggle: no window is remarkable against its own history."""
    idx = _bdays(n, end)
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.0, 0.0015, size=n)
    return pd.Series(100.0 * np.exp(np.cumsum(steps)), index=idx, name="close")


def _spiked_series(
    n: int,
    spike: float,
    *,
    sessions: int = 5,
    quiet_tail: int = 0,
    end: str | None = None,
    seed: int = 7,
) -> pd.Series:
    """Quiet history + a *spike* total move over *sessions*, ending *quiet_tail*
    sessions before the last bar.

    quiet_tail lets a fixture move the 21-session window without moving the
    5-session one (the move is fully inside the longer window and fully behind
    the shorter one), which is how the two legs get tested independently.
    """
    s = _quiet_series(n, end=end, seed=seed).to_numpy(copy=True)
    step = (1.0 + spike) ** (1.0 / sessions)
    first = n - quiet_tail - sessions
    for i in range(sessions):
        s[first + i :] *= step
    return pd.Series(s, index=_bdays(n, end), name="close")


def _series_with_window_return(
    n: int,
    w: int,
    target: float,
    *,
    end: str | None = None,
    seed: int = 7,
) -> pd.Series:
    """Quiet history whose final *w*-session return is EXACTLY *target*.

    Used to place a move at a chosen percentile of the series' own history
    rather than guessing a spike size and hoping it lands in the band.
    """
    s = _quiet_series(n, end=end, seed=seed).to_numpy(copy=True)
    factor = (1.0 + target) / (s[-1] / s[-1 - w])
    step = factor ** (1.0 / w)
    for i in range(w):
        s[n - w + i :] *= step
    return pd.Series(s, index=_bdays(n, end), name="close")


_YEAR = 252


def _setup(
    tmp: Path,
    *,
    deep: dict[str, pd.Series] | None = None,
    ohlcv: dict[str, pd.Series] | None = None,
    ohlcv_n: int = 300,
) -> None:
    """Write the minimal snapshot fixture set; `deep`/`ohlcv` override per symbol."""
    for sym in MAG7:
        _write_ohlcv(tmp, sym, _quiet_series(ohlcv_n, seed=MAG7.index(sym)))
    for sym, series in (ohlcv or {}).items():
        _write_ohlcv(tmp, sym, series)
    for sym, series in (deep or {}).items():
        _write_deep(tmp, sym, series)
    _write_spy(tmp, _quiet_series(ohlcv_n, seed=42))


def _patch_store(monkeypatch, tmp: Path) -> None:
    import lib.store as store_mod

    original_read = store_mod.read

    def fake_read(source: str, name: str):
        if source == "yahoo" and name == "SPY":
            p = _data(tmp) / "yahoo" / f"{name}.parquet"
            return pd.read_parquet(p) if p.exists() else None
        return original_read(source, name)

    monkeypatch.setattr(store_mod, "read", fake_read)


def _snapshot(root: Path) -> dict:
    from engine.mag7_regime import snapshot

    return snapshot(root=root)


def _member(events: dict, sym: str) -> dict | None:
    for m in events.get("members", []):
        if m["sym"] == sym:
            return m
    return None


# ===========================================================================
# 1. Tiers and receipts
# ===========================================================================

class TestMemberTiers:

    def test_deep_spike_is_historic_and_a_record(self, tmp_path, monkeypatch):
        """16y of quiet history + a +25% week → historic, ~100th pctile, no prior."""
        _patch_store(monkeypatch, tmp_path)
        _setup(tmp_path, deep={"MSFT": _spiked_series(16 * _YEAR, 0.25)})
        events = _snapshot(tmp_path)["events"]

        m = _member(events, "MSFT")
        assert m is not None, f"MSFT missing from members: {events['members']}"
        assert m["tier"] == "historic"
        assert m["window"] == "5d"
        assert m["pctile"] >= 99.5
        assert m["source"] == "deep"
        assert m["hist_years"] >= 15
        assert m["ret"] > 0.20
        assert m["last_larger_date"] is None, "a record week has no prior larger window"
        assert m["n_windows"] > 3000
        assert events["display"] is True

    def test_milder_spike_is_extreme_not_historic(self, tmp_path, monkeypatch):
        """A move above the 98th but below the 99.5th percentile stays `extreme`."""
        _patch_store(monkeypatch, tmp_path)
        # Quiet history has a real spread; a 5-session move sized between the
        # 98th and 99.5th percentiles of it must not be promoted.
        base = _quiet_series(16 * _YEAR)
        r5 = (base / base.shift(5) - 1.0).dropna()
        target = float(np.quantile(r5, 0.987))
        _setup(tmp_path, deep={"MSFT": _series_with_window_return(16 * _YEAR, 5, target)})
        m = _member(_snapshot(tmp_path)["events"], "MSFT")
        assert m is not None
        assert m["tier"] == "extreme"
        assert 98.0 <= m["pctile"] < 99.5
        assert m["last_larger_date"] is not None, "not a record → a prior window exists"

    def test_short_history_caps_at_extreme(self, tmp_path, monkeypatch):
        """<15 years of history cannot say `historic`, however rare the window."""
        _patch_store(monkeypatch, tmp_path)
        _setup(tmp_path, deep={"MSFT": _spiked_series(8 * _YEAR, 0.25)})
        m = _member(_snapshot(tmp_path)["events"], "MSFT")
        assert m is not None
        assert m["pctile"] >= 99.5, "the window IS record-class…"
        assert m["hist_years"] < 15
        assert m["tier"] == "extreme", "…but the history is too short to call it historic"

    def test_downside_mirror_is_historic(self, tmp_path, monkeypatch):
        """A −25% week is as much an event as a +25% one (percentile <= 0.5)."""
        _patch_store(monkeypatch, tmp_path)
        _setup(tmp_path, deep={"META": _spiked_series(16 * _YEAR, -0.25)})
        m = _member(_snapshot(tmp_path)["events"], "META")
        assert m is not None
        assert m["tier"] == "historic"
        assert m["pctile"] <= 0.5
        assert m["ret"] < -0.20
        assert m["last_larger_date"] is None

    def test_21d_window_qualifies_on_its_own(self, tmp_path, monkeypatch):
        """A month-long move that already ended fires on the 21d leg, not the 5d."""
        _patch_store(monkeypatch, tmp_path)
        # +30% spread over 16 sessions, then five quiet ones: the 21-session
        # window contains the whole move, the 5-session window contains none.
        _setup(tmp_path, deep={
            "AMZN": _spiked_series(16 * _YEAR, 0.30, sessions=16, quiet_tail=5),
        })
        m = _member(_snapshot(tmp_path)["events"], "AMZN")
        assert m is not None
        assert m["window"] == "21d"
        assert m["tier"] in ("historic", "extreme")
        assert m["ret"] > 0.25

    def test_quiet_tape_emits_no_members(self, tmp_path, monkeypatch):
        """Ordinary week → empty members + display False (honest null, not a failure)."""
        _patch_store(monkeypatch, tmp_path)
        _setup(tmp_path, deep={sym: _quiet_series(16 * _YEAR, seed=i) for i, sym in enumerate(MAG7)})
        events = _snapshot(tmp_path)["events"]
        assert events["members"] == []
        assert events["display"] is False
        assert events["cohort"]["kind"] is None
        assert "no forecast" in events["window_note"]

    def test_percentile_denominator_matches_n_windows(self, tmp_path, monkeypatch):
        """pctile is a share of n_windows — recomputable from the receipts."""
        _patch_store(monkeypatch, tmp_path)
        series = _spiked_series(16 * _YEAR, 0.25)
        _setup(tmp_path, deep={"MSFT": series})
        m = _member(_snapshot(tmp_path)["events"], "MSFT")
        r = (series / series.shift(5) - 1.0).dropna()
        assert m["n_windows"] == len(r)
        expected = round(100.0 * float((r < r.iloc[-1]).sum()) / len(r), 2)
        assert m["pctile"] == expected

    def test_last_larger_date_points_at_a_real_prior_window(self, tmp_path, monkeypatch):
        """last_larger_date is the most recent PRIOR window end at least this big."""
        _patch_store(monkeypatch, tmp_path)
        n = 16 * _YEAR
        s = _quiet_series(n).to_numpy(copy=True)
        # an earlier +30% week, then a +25% week at the end
        s[n - 200 :] *= 1.30
        s[n - 5 :] *= 1.25
        series = pd.Series(s, index=_bdays(n), name="close")
        _setup(tmp_path, deep={"MSFT": series})
        m = _member(_snapshot(tmp_path)["events"], "MSFT")
        assert m is not None
        assert m["last_larger_date"] is not None
        assert m["last_larger_date"] < str(series.index[-1].date())


class TestNoAuthorityLeak:
    """DNR §2 / MLC-R2..R5: the block may describe, never rank or advise."""

    def test_no_score_rank_or_direction_keys(self, tmp_path, monkeypatch):
        _patch_store(monkeypatch, tmp_path)
        _setup(tmp_path, deep={"MSFT": _spiked_series(16 * _YEAR, 0.25)})
        events = _snapshot(tmp_path)["events"]
        blob = json.dumps(events).lower()
        for banned in ("score", "rank", "conviction", "reco", "gate",
                       "target", "entry", "buy", "sell", "bull", "bear"):
            assert banned not in blob, f"authority/direction token '{banned}' leaked: {blob[:200]}"

    def test_trend_state_and_generals_untouched(self, tmp_path, monkeypatch):
        """The event lens copies generals; it never recomputes or overrides it."""
        _patch_store(monkeypatch, tmp_path)
        _setup(tmp_path, deep={"MSFT": _spiked_series(16 * _YEAR, 0.25)})
        result = _snapshot(tmp_path)
        assert result["events"]["cohort"]["generals"] == result["generals"]
        assert result["trend_state"] in {
            "running_broad", "running_narrow", "turning_up",
            "cooling", "rolling_over", "down",
        }


# ===========================================================================
# 3. Cohort kinds
# ===========================================================================

class TestCohortKinds:

    def test_split_when_one_rips_and_one_slides(self, tmp_path, monkeypatch):
        """The July shape: MSFT-class rip + AAPL-class slide = `split`."""
        _patch_store(monkeypatch, tmp_path)
        deep = {sym: _quiet_series(16 * _YEAR, seed=i) for i, sym in enumerate(MAG7)}
        deep["MSFT"] = _spiked_series(16 * _YEAR, 0.25)
        deep["AAPL"] = _spiked_series(16 * _YEAR, -0.06)  # ret <= -5%, not a tail
        _setup(tmp_path, deep=deep)
        cohort = _snapshot(tmp_path)["events"]["cohort"]
        assert cohort["kind"] == "split"
        assert [c["sym"] for c in cohort["up"]] == ["MSFT"]
        assert [c["sym"] for c in cohort["down"]] == ["AAPL"]
        assert cohort["down"][0]["r5"] <= -0.05

    def test_broad_up_needs_four_members(self, tmp_path, monkeypatch):
        _patch_store(monkeypatch, tmp_path)
        deep = {sym: _quiet_series(16 * _YEAR, seed=i) for i, sym in enumerate(MAG7)}
        for sym in ("MSFT", "AMZN", "GOOGL", "META"):
            deep[sym] = _spiked_series(16 * _YEAR, 0.25, seed=MAG7.index(sym))
        _setup(tmp_path, deep=deep)
        cohort = _snapshot(tmp_path)["events"]["cohort"]
        assert cohort["kind"] == "broad_up"
        assert len(cohort["up"]) >= 4

    def test_broad_down_needs_four_members(self, tmp_path, monkeypatch):
        _patch_store(monkeypatch, tmp_path)
        deep = {sym: _quiet_series(16 * _YEAR, seed=i) for i, sym in enumerate(MAG7)}
        for sym in ("MSFT", "AMZN", "GOOGL", "META"):
            deep[sym] = _spiked_series(16 * _YEAR, -0.25, seed=MAG7.index(sym))
        _setup(tmp_path, deep=deep)
        cohort = _snapshot(tmp_path)["events"]["cohort"]
        assert cohort["kind"] == "broad_down"
        assert len(cohort["down"]) >= 4

    def test_three_up_one_down_is_still_split(self, tmp_path, monkeypatch):
        """Three is not `broad` — the threshold is 4 of 7."""
        _patch_store(monkeypatch, tmp_path)
        deep = {sym: _quiet_series(16 * _YEAR, seed=i) for i, sym in enumerate(MAG7)}
        for sym in ("MSFT", "AMZN", "GOOGL"):
            deep[sym] = _spiked_series(16 * _YEAR, 0.25, seed=MAG7.index(sym))
        deep["AAPL"] = _spiked_series(16 * _YEAR, -0.07)
        _setup(tmp_path, deep=deep)
        cohort = _snapshot(tmp_path)["events"]["cohort"]
        assert cohort["kind"] == "split"
        assert len(cohort["up"]) == 3

    def test_quiet_cohort_is_null_not_a_word(self, tmp_path, monkeypatch):
        _patch_store(monkeypatch, tmp_path)
        _setup(tmp_path, deep={sym: _quiet_series(16 * _YEAR, seed=i) for i, sym in enumerate(MAG7)})
        cohort = _snapshot(tmp_path)["events"]["cohort"]
        assert cohort["kind"] is None
        assert cohort["up"] == [] and cohort["down"] == []


# ===========================================================================
# 4. Artifact + ledger plumbing
# ===========================================================================

class TestArtifactsCarryEvents:

    def test_latest_json_and_ledger_carry_events(self, tmp_path, monkeypatch):
        _patch_store(monkeypatch, tmp_path)
        _setup(tmp_path, deep={"MSFT": _spiked_series(16 * _YEAR, 0.25)})
        result = _snapshot(tmp_path)

        latest = json.loads((_data(tmp_path) / "mag7_regime" / "latest.json").read_text())
        assert _member(latest["events"], "MSFT") is not None
        assert latest["events"] == result["events"]

        rows = [
            json.loads(line)
            for line in (_data(tmp_path) / "mag7_regime" / "ledger.jsonl").read_text().splitlines()
            if line.strip()
        ]
        assert len(rows) == 1
        assert _member(rows[0]["events"], "MSFT")["tier"] == "historic"
        # ledger vocabulary continuity — the original five fields survive
        for key in ("date", "trend_state", "structure_chip", "k7_trend", "cw_r10", "generals"):
            assert key in rows[0]

    def test_ledger_stays_idempotent_by_date(self, tmp_path, monkeypatch):
        """Re-running the same session must not duplicate the (now fatter) row."""
        _patch_store(monkeypatch, tmp_path)
        _setup(tmp_path, deep={"MSFT": _spiked_series(16 * _YEAR, 0.25)})
        _snapshot(tmp_path)
        _snapshot(tmp_path)
        rows = [
            json.loads(line)
            for line in (_data(tmp_path) / "mag7_regime" / "ledger.jsonl").read_text().splitlines()
            if line.strip()
        ]
        assert len(rows) == 1, f"expected one row per date, got {len(rows)}"


# ===========================================================================
# 5. The GitHub annotation (house law: must START the line)
# ===========================================================================

class TestHistoricAnnotation:

    def test_historic_tier_prints_a_line_starting_annotation(self, tmp_path, monkeypatch, capsys):
        """capsys, NOT caplog: a logger prefix would silently void the annotation."""
        _patch_store(monkeypatch, tmp_path)
        _setup(tmp_path, deep={"MSFT": _spiked_series(16 * _YEAR, 0.25)})
        _snapshot(tmp_path)

        out = capsys.readouterr().out
        hits = [ln for ln in out.splitlines() if ln.startswith("::notice title=mag7_event::")]
        assert hits, f"no line-starting mag7_event annotation in stdout:\n{out}"
        assert "MSFT" in hits[0]
        assert "in 5 sessions" in hits[0]
        assert "pctile of own history" in hits[0]

    def test_no_annotation_without_a_historic_member(self, tmp_path, monkeypatch, capsys):
        _patch_store(monkeypatch, tmp_path)
        _setup(tmp_path, deep={sym: _quiet_series(16 * _YEAR, seed=i) for i, sym in enumerate(MAG7)})
        _snapshot(tmp_path)
        assert "mag7_event" not in capsys.readouterr().out


# ===========================================================================
# 7. Fail-soft
# ===========================================================================

class TestFailSoft:

    def test_corrupt_deep_parquet_falls_back_to_ohlcv(self, tmp_path, monkeypatch):
        """An unreadable deep file degrades THAT member to its ohlcv span only."""
        _patch_store(monkeypatch, tmp_path)
        _setup(
            tmp_path,
            deep={"MSFT": _spiked_series(16 * _YEAR, 0.25)},
            ohlcv={"AAPL": _spiked_series(5 * _YEAR, 0.25)},
        )
        bad = _data(tmp_path) / "stocks" / "AAPL.parquet"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_bytes(b"not a parquet file")

        result = _snapshot(tmp_path)
        assert isinstance(result, dict) and result.get("as_of")
        assert _member(result["events"], "MSFT")["source"] == "deep", "neighbour unaffected"

        aapl = _member(result["events"], "AAPL")
        assert aapl is not None, "the member is served from ohlcv, not dropped"
        assert aapl["source"] == "ohlcv"
        assert aapl["hist_years"] < 15
        assert aapl["tier"] == "extreme", "a disclosed short span cannot say historic"

    def test_missing_deep_store_entirely_uses_ohlcv_span(self, tmp_path, monkeypatch):
        """With no data/stocks at all the lens still works, on the shorter span."""
        _patch_store(monkeypatch, tmp_path)
        for sym in MAG7:
            _write_ohlcv(tmp_path, sym, _quiet_series(5 * _YEAR, seed=MAG7.index(sym)))
        _write_ohlcv(tmp_path, "MSFT", _spiked_series(5 * _YEAR, 0.25))
        _write_spy(tmp_path, _quiet_series(5 * _YEAR, seed=42))
        assert not (_data(tmp_path) / "stocks").exists()

        result = _snapshot(tmp_path)
        m = _member(result["events"], "MSFT")
        assert m is not None
        assert m["source"] == "ohlcv"
        assert m["tier"] == "extreme"
        assert result["events"]["display"] is True

    def test_short_series_gets_no_tier(self, tmp_path, monkeypatch):
        """A percentile over a handful of windows is noise — no tier is assigned."""
        _patch_store(monkeypatch, tmp_path)
        _setup(tmp_path, deep={"MSFT": _spiked_series(120, 0.25)}, ohlcv_n=120)
        events = _snapshot(tmp_path)["events"]
        assert events["members"] == []
        assert events["display"] is False

    def test_event_lens_exception_degrades_to_null_block(self, tmp_path, monkeypatch):
        """A blown-up lens must not take snapshot() down with it."""
        import engine.mag7_regime as M

        _patch_store(monkeypatch, tmp_path)
        _setup(tmp_path, deep={"MSFT": _spiked_series(16 * _YEAR, 0.25)})

        def boom(*a, **k):
            raise RuntimeError("event lens exploded")

        monkeypatch.setattr(M, "_compute_events", boom)
        result = M.snapshot(root=tmp_path)
        assert result["events"]["display"] is False
        assert result["events"]["members"] == []
        assert result["trend_state"], "the rest of the organ is unaffected"

    def test_frozen_member_series_is_skipped_not_restamped(self, tmp_path, monkeypatch):
        """A member whose tape stopped updating may not wear today's as_of."""
        _patch_store(monkeypatch, tmp_path)
        stale_end = str((pd.Timestamp(_TODAY) - pd.offsets.BDay(20)).date())
        _setup(
            tmp_path,
            # both sources for NVDA froze 20 sessions ago, mid-spike
            deep={"NVDA": _spiked_series(16 * _YEAR, 0.25, end=stale_end)},
            ohlcv={"NVDA": _spiked_series(5 * _YEAR, 0.25, end=stale_end)},
        )
        events = _snapshot(tmp_path)["events"]
        assert _member(events, "NVDA") is None, "a frozen series must not be re-dated"
        assert events["display"] is False

    def test_stale_deep_store_is_not_preferred(self, tmp_path, monkeypatch):
        """A deep store lagging the ohlcv grid must not date-stamp an old window."""
        import engine.mag7_regime as M

        stale = _spiked_series(16 * _YEAR, 0.25, end=str(pd.Timestamp(_TODAY) - pd.offsets.BDay(20)))
        fresh = _quiet_series(300)
        series, source = M._event_series_for("MSFT", fresh, root=_data(tmp_path))
        assert source == "ohlcv"
        _write_deep(tmp_path, "MSFT", stale)
        series, source = M._event_series_for("MSFT", fresh, root=_data(tmp_path))
        assert source == "ohlcv", "stale deep history must lose to the current ohlcv series"
        assert series is fresh


# ===========================================================================
# 6. Notification source (g)
# ===========================================================================

_HISTORIC_ARTIFACT = {
    "as_of": "2026-07-31",
    "trend_state": "cooling",
    "events": {
        "as_of": "2026-07-31",
        "display": True,
        "window_note": "descriptive percentiles of realized 5- and 21-session returns "
                       "vs the member's own full trading history; no forecast",
        "members": [
            {
                "sym": "MSFT", "window": "5d", "ret": 0.217501, "pctile": 99.9,
                "tier": "historic", "n_windows": 10169, "hist_years": 40.4,
                "last_larger_date": "2000-10-24", "source": "deep",
            },
            {
                "sym": "GOOGL", "window": "5d", "ret": 0.113811, "pctile": 98.57,
                "tier": "extreme", "n_windows": 5517, "hist_years": 21.9,
                "last_larger_date": "2026-05-06", "source": "deep",
            },
        ],
        "cohort": {"kind": "split", "up": [], "down": [], "generals": {}},
    },
}


@pytest.fixture()
def _artifact(tmp_path, monkeypatch):
    """Point notify_turn_events at a synthetic mag7_regime artifact."""
    import scripts.notify_turn_events as NTE

    p = tmp_path / "mag7_regime_latest.json"

    def _write(payload: dict) -> Path:
        p.write_text(json.dumps(payload))
        monkeypatch.setattr(NTE, "_MAG7_REGIME_PATH", p)
        return p

    return _write


class TestNotifySourceG:

    def test_historic_entry_fires_once(self, _artifact):
        import scripts.notify_turn_events as NTE

        _artifact(_HISTORIC_ARTIFACT)
        state: dict = {}
        events = NTE._detect_m7_events(state, "2026-08-01")
        assert len(events) == 1, "only the historic tier notifies; extreme stays on-site"
        subject, msg = events[0]
        assert subject == "MSFT|5d|2026-07-31"
        assert "MSFT" in msg and "+21.8%" in msg
        assert "5 sessions" in msg
        assert "99.9th percentile" in msg
        assert "40-year" in msg
        assert "2000-10-24" in msg
        assert "as-of 2026-07-31" in msg

    def test_second_run_same_day_is_deduped(self, _artifact):
        import scripts.notify_turn_events as NTE

        _artifact(_HISTORIC_ARTIFACT)
        state: dict = {}
        (subject, _), = NTE._detect_m7_events(state, "2026-08-01")
        NTE._mark_fired(state, "m7_event", subject, "2026-07-31")
        assert NTE._detect_m7_events(state, "2026-08-01") == []

    def test_stale_artifact_is_ignored(self, _artifact):
        import scripts.notify_turn_events as NTE

        _artifact(_HISTORIC_ARTIFACT)
        assert NTE._detect_m7_events({}, "2026-08-10") == [], "as_of older than 5 days → silence"

    def test_future_dated_artifact_is_ignored(self, _artifact):
        import scripts.notify_turn_events as NTE

        _artifact(_HISTORIC_ARTIFACT)
        assert NTE._detect_m7_events({}, "2026-07-01") == []

    def test_quiet_artifact_says_nothing(self, _artifact):
        import scripts.notify_turn_events as NTE

        _artifact({
            "as_of": "2026-07-31",
            "events": {"as_of": "2026-07-31", "display": False, "members": [],
                       "cohort": {"kind": None, "up": [], "down": [], "generals": {}}},
        })
        assert NTE._detect_m7_events({}, "2026-08-01") == []

    def test_absent_and_malformed_artifacts_are_no_ops(self, tmp_path, monkeypatch):
        import scripts.notify_turn_events as NTE

        monkeypatch.setattr(NTE, "_MAG7_REGIME_PATH", tmp_path / "nope.json")
        assert NTE._detect_m7_events({}, "2026-08-01") == []

        bad = tmp_path / "bad.json"
        bad.write_text("{not json")
        monkeypatch.setattr(NTE, "_MAG7_REGIME_PATH", bad)
        assert NTE._detect_m7_events({}, "2026-08-01") == []

        legacy = tmp_path / "legacy.json"  # artifact written before F1 shipped
        legacy.write_text(json.dumps({"as_of": "2026-07-31", "trend_state": "cooling"}))
        monkeypatch.setattr(NTE, "_MAG7_REGIME_PATH", legacy)
        assert NTE._detect_m7_events({}, "2026-08-01") == []

    def test_message_copy_contract(self, _artifact):
        """No direction words; plain-word stance disclosure; no engine slugs."""
        import scripts.notify_turn_events as NTE

        _artifact(_HISTORIC_ARTIFACT)
        (_, msg), = NTE._detect_m7_events({}, "2026-08-01")
        NTE._assert_no_forbidden_words(msg)
        assert "not an entry signal" in msg.lower()
        for banned in ("historic", "tier", "pctile", "n_windows", "mag7_regime",
                       "display-tier", "deep", "IGNITION"):
            assert banned.lower() not in msg.lower(), f"internal token '{banned}' in: {msg}"

    def test_downside_record_reads_naturally(self):
        import scripts.notify_turn_events as NTE

        msg = NTE._m7_event_message(
            {"sym": "TSLA", "window": "21d", "ret": -0.31, "pctile": 0.3,
             "tier": "historic", "hist_years": 16.1, "last_larger_date": None},
            "2026-07-31",
        )
        NTE._assert_no_forbidden_words(msg)
        assert "-31.0%" in msg and "21 sessions" in msg
        assert "lower than all but 0.3%" in msg
        assert "no 21-session stretch this size" in msg

    def test_run_dispatches_and_dedups_end_to_end(self, tmp_path, monkeypatch):
        """The source is wired into run(), not merely defined."""
        import scripts.notify_turn_events as NTE

        artifact = tmp_path / "latest.json"
        artifact.write_text(json.dumps(_HISTORIC_ARTIFACT))
        monkeypatch.setattr(NTE, "_MAG7_REGIME_PATH", artifact)
        monkeypatch.setattr(NTE, "_NOTIFY_STATE_PATH", tmp_path / "notify_state.json")
        monkeypatch.setattr(NTE.config, "secret", lambda k: "https://example.invalid/webhook")

        sent: list[str] = []
        monkeypatch.setattr(NTE, "_send_discord", lambda msg, dry_run=False: sent.append(msg) or True)

        assert NTE.run(today_str="2026-08-01") == 1
        assert len(sent) == 1 and "MSFT" in sent[0]
        assert NTE.run(today_str="2026-08-01") == 0, "same day → deduped"
        assert len(sent) == 1
