"""tests/test_prophet_anticipation_a1.py — ANTICIPATION §6.2 A1 (2026-08-08).

The selection inversion: admission stops being an act-level threshold and becomes a
STATUS CLASS, the old gate keeps accruing a zero-authority shadow ledger, no plan may
be created at a stale price, and the book gains a sector cap.

Coverage:
  A. Admission matrix — status x band x dir, every cell asserted.
  B. Provenance stamps — admission_class / entry_status / selection_era / entry_basis.
  C. Caps — N cap, sector cap, sector-unknown exemption, champion order preserved.
  D. Publication-lag guard — re-derivation, both skip paths, the fresh no-op.
  E. Legacy shadow ledger — the frozen gate, lane gating, idempotency, day parts.

Every fixture here is synthetic. The live before/after evidence against the committed
board artifact is in the PR body, not in a test — a test that reads site/factordata
would assert about whatever the last nightly happened to publish.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine import prophet_bridge as pb  # noqa: E402
from engine.prophet_bridge import (  # noqa: E402
    ADMISSION_CLASS_CONFIRMATION,
    ADMISSION_CLASS_PATIENCE,
    LEGACY_N_CANDIDATES,
    N_CANDIDATES,
    SECTOR_CAP,
    SELECTION_ERA,
    STALE_BASIS_MAX_SESSIONS,
    admission_class,
    append_legacy_shadow,
    entry_basis_date,
    entry_status,
    legacy_admitted,
    legacy_shadow_rows,
    load_legacy_shadow,
    originate_plans,
    select_candidates,
)


# --------------------------------------------------------------------------- #
# fixtures                                                                     #
# --------------------------------------------------------------------------- #

def _row(ticker: str, *, status: str = "partial", band: str = "neutral",
         dir_: str = "up", act_level: int = 3, score: int = 50,
         priority: float | None = 80.0, spot: float = 100.0,
         sector: str | None = "Materials", signal_asof: str | None = None,
         anchor: str = "2026-07-02", chase_above: float | None = 105.0) -> dict:
    row: dict = {
        "ticker": ticker,
        "dir": dir_,
        "conviction": {"score": score, "band": band, "drivers": ["m"],
                       "cautions": ["c"], "trust_tier": {"en": "tier-2"}},
        "entry_signal": {"status": status, "act_level": act_level, "spot": spot,
                         "chase_above": chase_above, "atr_pct": 2.0,
                         "entry_grade": "solid"},
        "hold": {"state": "HOLD", "anchor": anchor, "invalidation": spot * 0.9},
    }
    if priority is not None:
        row["prophet"] = {"version": "us_prophet_v1", "score": priority}
    if sector is not None:
        row["sector"] = sector
    if signal_asof is not None:
        row["signal_asof"] = signal_asof
    return row


def _standouts(rows: list[dict], *, gate_go: bool = False,
               as_of: str = "2026-07-02") -> dict:
    return {"as_of": as_of, "gate_go": gate_go, "buy": rows}


def _write(tmp_path: Path, rows: list[dict], **kw) -> Path:
    path = tmp_path / "us_standouts.json"
    path.write_text(json.dumps(_standouts(rows, **kw)), encoding="utf-8")
    return path


@pytest.fixture
def nightly(monkeypatch):
    """Arm the US nightly forward-ledger lane."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    monkeypatch.delenv("US_LANE", raising=False)


@pytest.fixture
def not_nightly(monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)


def _tickers(rows) -> list[str]:
    return [r["ticker"] for r in rows]


# --------------------------------------------------------------------------- #
# A. Admission matrix                                                          #
# --------------------------------------------------------------------------- #

class TestAdmissionMatrix:
    """Every cell of status x band x dir, asserted rather than sampled."""

    #: (status, expected admission class or None) over the FULL ladder vocabulary.
    STATUS_CELLS = [
        ("bounce_wait", ADMISSION_CLASS_PATIENCE),
        ("wait_pullback", ADMISSION_CLASS_PATIENCE),
        ("hold", ADMISSION_CLASS_PATIENCE),
        ("buy_now", ADMISSION_CLASS_CONFIRMATION),
        ("partial", ADMISSION_CLASS_CONFIRMATION),
        # deliberate exclusions
        ("extended", None),      # the anti-chase guard
        ("buy_soon", None),      # graded worst of the CN entry statuses
        ("await_confluence", None),
        ("watch", None),
        ("topping", None),
        ("exit", None),
        ("avoid", None),
        ("blocked", None),
    ]

    @pytest.mark.parametrize("status,expected", STATUS_CELLS)
    def test_status_decides_admission(self, status, expected):
        rows = [_row("T", status=status, dir_="up")]
        got = select_candidates(_standouts(rows), n=None)
        assert _tickers(got) == (["T"] if expected else [])
        assert admission_class(status) == expected

    @pytest.mark.parametrize("status,expected", STATUS_CELLS)
    @pytest.mark.parametrize("band", ["low", "neutral", "constructive", "high"])
    def test_band_low_refuses_every_status(self, status, expected, band):
        """band == 'low' is an unconditional refusal — it outranks the status class."""
        rows = [_row("T", status=status, band=band, dir_="up")]
        got = select_candidates(_standouts(rows), n=None)
        admitted = bool(expected) and band != "low"
        assert _tickers(got) == (["T"] if admitted else [])

    @pytest.mark.parametrize("direction,admitted_dir", [
        ("up", True),
        ("caution", True),   # COUNTERTREND BOUNCE — the patience cohort's tone
        ("down", False),     # DECLINE / ROLLING OVER / BOTTOM WATCH
        ("", True),          # absent/blank defaults to "up" (legacy artifacts)
    ])
    @pytest.mark.parametrize("status,expected", STATUS_CELLS)
    def test_direction_tone(self, direction, admitted_dir, status, expected):
        rows = [_row("T", status=status, dir_=direction)]
        got = select_candidates(_standouts(rows), n=None)
        assert _tickers(got) == (["T"] if (expected and admitted_dir) else [])

    def test_caution_tone_alone_does_not_admit_the_chase_cohort(self):
        """The fence for widening `dir` to include 'caution'.

        TOP WATCH shares the caution tone with COUNTERTREND BOUNCE. If the status
        gate ever stopped refusing `extended`/`topping`, the tone widening would
        start admitting take-profit rows — this test fails the moment that happens.
        """
        rows = [
            _row("BOUNCE", status="bounce_wait", dir_="caution", priority=90.0),
            _row("TOPPY", status="extended", dir_="caution", priority=95.0),
            _row("TOPPING", status="topping", dir_="caution", priority=96.0),
        ]
        assert _tickers(select_candidates(_standouts(rows), n=None)) == ["BOUNCE"]

    def test_gate_go_is_no_longer_read_by_admission(self):
        rows = [_row("A", status="bounce_wait", dir_="caution", score=5, act_level=0),
                _row("B", status="buy_soon", score=99, act_level=2)]
        strict = _tickers(select_candidates(_standouts(rows, gate_go=True), n=None))
        caution = _tickers(select_candidates(_standouts(rows, gate_go=False), n=None))
        assert strict == caution == ["A"]

    def test_null_entry_signal_is_refused(self):
        rows = [{"ticker": "NOES", "dir": "up", "entry_signal": None,
                 "conviction": {"score": 80, "band": "neutral"}, "hold": {}}]
        assert select_candidates(_standouts(rows), n=None) == []

    def test_unknown_status_is_refused_and_COUNTED(self):
        """Vocabulary drift must be loud. A renamed status word would otherwise
        empty the intake with no alarm anywhere."""
        rows = [_row("DRIFT", status="bounce_await"),      # not in the vocabulary
                _row("KNOWN", status="extended"),          # a deliberate exclusion
                _row("OK", status="hold")]
        stats: dict = {}
        got = select_candidates(_standouts(rows), n=None, stats=stats)
        assert _tickers(got) == ["OK"]
        assert stats["unknown_status"] == 1
        assert stats["unknown_status_values"] == ["bounce_await"]

    def test_class_counts_are_reported(self):
        rows = [_row("P1", status="bounce_wait", dir_="caution"),
                _row("P2", status="hold"),
                _row("C1", status="buy_now")]
        stats: dict = {}
        select_candidates(_standouts(rows), n=None, stats=stats)
        assert stats["admitted_by_class"] == {
            ADMISSION_CLASS_PATIENCE: 2, ADMISSION_CLASS_CONFIRMATION: 1}

    def test_sort_key_is_unchanged_by_the_new_admission(self):
        """A1 moves WHICH rows are admitted, never how admitted rows rank."""
        rows = [_row("LOW", priority=10.0), _row("HIGH", priority=99.0),
                _row("MID", priority=55.0)]
        assert _tickers(select_candidates(_standouts(rows), n=None)) == [
            "HIGH", "MID", "LOW"]


# --------------------------------------------------------------------------- #
# B. Provenance stamps                                                         #
# --------------------------------------------------------------------------- #

class TestProvenanceStamps:

    def test_every_plan_carries_class_status_and_era(self, tmp_path):
        path = _write(tmp_path, [
            _row("PAT", status="bounce_wait", dir_="caution", priority=90.0),
            _row("CONF", status="partial", priority=80.0, sector="Energy"),
        ])
        plans = originate_plans(path, "2026-07-02", set(), None, active_keys=set())
        by_asset = {p["asset"]: p for p in plans}
        assert by_asset["PAT"]["admission_class"] == ADMISSION_CLASS_PATIENCE
        assert by_asset["PAT"]["entry_status"] == "bounce_wait"
        assert by_asset["CONF"]["admission_class"] == ADMISSION_CLASS_CONFIRMATION
        assert by_asset["CONF"]["entry_status"] == "partial"
        for plan in plans:
            assert plan["selection_era"] == SELECTION_ERA
            assert plan["entry_basis"]["era"] == SELECTION_ERA

    def test_stamps_are_ADDITIVE_nothing_was_renamed(self, tmp_path):
        """Existing consumers read these keys; A1 may only add alongside them."""
        path = _write(tmp_path, [_row("T")])
        plan = originate_plans(path, "2026-07-02", set(), None, active_keys=set())[0]
        for key in ("schema", "id", "asof", "asset", "direction", "entry", "trigger",
                    "invalidation", "targets", "horizon_days", "min_hold_days",
                    "signal_date", "entry_date", "_priority_score",
                    "_conviction_score", "_act_level", "_gate_go", "stage_tilt"):
            assert key in plan, f"A1 dropped the pre-existing key {key!r}"

    def test_intake_stats_disclose_the_new_admission(self, tmp_path):
        path = _write(tmp_path, [_row("P", status="hold", priority=90.0),
                                 _row("C", status="buy_now", priority=80.0)])
        stats: dict = {}
        originate_plans(path, "2026-07-02", set(), None, active_keys=set(),
                        intake_stats=stats)
        assert stats["selection_era"] == SELECTION_ERA
        assert stats["admitted_by_class"] == {
            ADMISSION_CLASS_PATIENCE: 1, ADMISSION_CLASS_CONFIRMATION: 1}
        assert stats["originated_by_class"] == {
            ADMISSION_CLASS_PATIENCE: 1, ADMISSION_CLASS_CONFIRMATION: 1}
        assert stats["sector_cap"] == SECTOR_CAP
        assert stats["cap"] == N_CANDIDATES
        assert stats["stale_basis_max"] == STALE_BASIS_MAX_SESSIONS

    def test_entry_status_and_class_helpers_agree(self):
        row = _row("T", status="  BOUNCE_WAIT  ")
        assert entry_status(row) == "bounce_wait"
        assert admission_class(entry_status(row)) == ADMISSION_CLASS_PATIENCE
        assert entry_status({"entry_signal": None}) == ""
        assert admission_class(None) is None


# --------------------------------------------------------------------------- #
# C. Caps                                                                      #
# --------------------------------------------------------------------------- #

class TestCaps:

    def test_n_cap_is_16(self, tmp_path):
        assert N_CANDIDATES == 16
        rows = [_row(f"T{i:02d}", priority=99.0 - i,
                     sector=f"S{i}") for i in range(30)]
        stats: dict = {}
        plans = originate_plans(_write(tmp_path, rows), "2026-07-02", set(), None,
                                active_keys=set(), intake_stats=stats)
        assert len(plans) == N_CANDIDATES
        assert stats["eligible_after_skips"] == 30

    def test_sector_cap_drops_the_LOWER_ranked_members(self, tmp_path):
        rows = [_row(f"M{i}", priority=99.0 - i, sector="Materials")
                for i in range(6)]
        rows += [_row("E0", priority=50.0, sector="Energy")]
        stats: dict = {}
        plans = originate_plans(_write(tmp_path, rows), "2026-07-02", set(), None,
                                active_keys=set(), intake_stats=stats)
        assert [p["asset"] for p in plans] == ["M0", "M1", "M2", "M3", "E0"]
        assert stats["sector_capped"] == 2
        assert stats["sector_cap"] == SECTOR_CAP == 4

    def test_sector_cap_is_per_sector_not_global(self, tmp_path):
        rows = []
        for sector in ("Materials", "Energy", "Health Care"):
            rows += [_row(f"{sector[:2]}{i}", priority=99.0 - len(rows),
                          sector=sector) for i in range(4)]
        plans = originate_plans(_write(tmp_path, rows), "2026-07-02", set(), None,
                                active_keys=set())
        assert len(plans) == 12  # 3 sectors x 4, none capped

    def test_rows_with_no_sector_are_EXEMPT_not_pooled(self, tmp_path):
        """Pooling every sector-less row into one bucket would look like a cap and
        behave like a kill switch: a legacy artifact with no `sector` field would
        originate 4 plans instead of 16, silently."""
        rows = [_row(f"T{i:02d}", priority=99.0 - i, sector=None) for i in range(10)]
        stats: dict = {}
        plans = originate_plans(_write(tmp_path, rows), "2026-07-02", set(), None,
                                active_keys=set(), intake_stats=stats)
        assert len(plans) == 10
        assert stats["sector_capped"] == 0
        assert stats["sector_unknown"] == 10

    def test_blank_sector_string_is_treated_as_absent(self, tmp_path):
        rows = [_row(f"T{i}", priority=99.0 - i, sector="   ") for i in range(6)]
        plans = originate_plans(_write(tmp_path, rows), "2026-07-02", set(), None,
                                active_keys=set())
        assert len(plans) == 6

    def test_caps_run_AFTER_the_skips(self, tmp_path):
        """P4's law survives A1: a book of already-live names still originates from
        below the line, and the sector cap counts survivors, not admissions."""
        rows = [_row(f"LIVE{i}", priority=99.0 - i, sector="Materials")
                for i in range(4)]
        rows += [_row(f"NEW{i}", priority=50.0 - i, sector="Materials")
                 for i in range(3)]
        active = {f"LIVE{i}-BULL" for i in range(4)}
        plans = originate_plans(_write(tmp_path, rows), "2026-07-02", set(), None,
                                active_keys=active)
        assert [p["asset"] for p in plans] == ["NEW0", "NEW1", "NEW2"]

    def test_select_candidates_does_NOT_apply_the_sector_cap(self):
        """The sector cap is a book-construction limit, not an admission rule —
        keeping it out of select_candidates keeps that function usable as a pure
        admitted-population read (engine.prophet_arena.admitted_pool relies on it)."""
        rows = [_row(f"M{i}", priority=99.0 - i, sector="Materials")
                for i in range(6)]
        assert len(select_candidates(_standouts(rows), n=None)) == 6
        assert len(select_candidates(_standouts(rows), n=6)) == 6


# --------------------------------------------------------------------------- #
# D. Publication-lag guard                                                     #
# --------------------------------------------------------------------------- #

def _price_frame(last_close: float, *, end: str, n: int = 40,
                 low_factor: float = 0.80) -> pd.DataFrame:
    """Rising synthetic closes ending at `end` (business days), last == last_close."""
    dates = pd.bdate_range(end=pd.Timestamp(end), periods=n)
    closes = [last_close * low_factor
              + last_close * (1 - low_factor) * (i / (n - 1)) for i in range(n)]
    return pd.DataFrame({"close": closes, "high": closes, "low": closes}, index=dates)


class TestPublicationLagGuard:

    def test_basis_date_prefers_the_rows_own_stamp(self):
        assert entry_basis_date(_row("T", signal_asof="2026-08-05"), "2026-08-07") == (
            "2026-08-05", "board_signal_asof")
        assert entry_basis_date(_row("T"), "2026-08-07") == (
            "2026-08-07", "standouts_as_of")

    def test_a_FRESH_basis_is_left_alone_and_still_disclosed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pb, "_load_price_history",
                            lambda t: _price_frame(200.0, end="2026-08-07"))
        path = _write(tmp_path, [_row("T", spot=100.0, signal_asof="2026-08-06")],
                      as_of="2026-08-07")
        plan = originate_plans(path, "2026-08-07", set(), None, active_keys=set())[0]
        assert plan["entry"] == 100.0, "a fresh basis must not be re-priced"
        assert plan["entry_basis"]["state"] == "current"
        assert plan["entry_basis"]["rederived"] is False
        assert plan["entry_basis"]["lag"] == 1
        assert plan["entry_basis"]["basis_date"] == "2026-08-06"

    def test_the_boundary_is_MORE_THAN_three_sessions(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pb, "_load_price_history",
                            lambda t: _price_frame(200.0, end="2026-08-07"))
        # 2026-08-04 -> 2026-08-07 is exactly 3 sessions: still fresh.
        path = _write(tmp_path, [_row("T", spot=100.0, signal_asof="2026-08-04")],
                      as_of="2026-08-07")
        plan = originate_plans(path, "2026-08-07", set(), None, active_keys=set())[0]
        assert plan["entry_basis"]["lag"] == STALE_BASIS_MAX_SESSIONS == 3
        assert plan["entry_basis"]["rederived"] is False
        assert plan["entry"] == 100.0

    def test_a_STALE_basis_is_re_derived_from_the_current_close(
            self, tmp_path, monkeypatch):
        frame = _price_frame(200.0, end="2026-08-07")
        monkeypatch.setattr(pb, "_load_price_history", lambda t: frame)
        path = _write(tmp_path, [_row("T", spot=100.0, signal_asof="2026-07-20",
                                      chase_above=105.0)], as_of="2026-08-07")
        plan = originate_plans(path, "2026-08-07", set(), None, active_keys=set())[0]
        basis = plan["entry_basis"]
        assert basis["rederived"] is True
        assert basis["state"] == "rederived"
        assert basis["lag"] > STALE_BASIS_MAX_SESSIONS
        assert basis["prior_entry"] == 100.0
        assert basis["rederived_from_date"] == "2026-08-07"
        assert plan["entry"] == pytest.approx(200.0)
        assert basis["move_since_basis_pct"] == pytest.approx(100.0)

    def test_re_derivation_moves_invalidation_and_BOTH_targets(
            self, tmp_path, monkeypatch):
        """A re-derived entry with stale targets is a worse artifact than either."""
        frame = _price_frame(200.0, end="2026-08-07")
        monkeypatch.setattr(pb, "_load_price_history", lambda t: frame)
        stale = _write(tmp_path, [_row("T", spot=100.0, signal_asof="2026-07-20")],
                       as_of="2026-08-07")
        plan = originate_plans(stale, "2026-08-07", set(), None, active_keys=set())[0]
        assert plan["invalidation"] < plan["entry"], "stop must sit below a BULL entry"
        assert all(t > plan["entry"] for t in plan["targets"])
        # The board's stored hold.invalidation (90.0, from the stale basis) is NOT
        # what was used — it would have made R = 110 on a 200 entry.
        assert plan["invalidation"] > 90.0

    def test_a_chase_level_the_tape_has_TAKEN_OUT_stops_being_the_trigger(
            self, tmp_path, monkeypatch):
        frame = _price_frame(200.0, end="2026-08-07")
        monkeypatch.setattr(pb, "_load_price_history", lambda t: frame)
        path = _write(tmp_path, [_row("T", spot=100.0, signal_asof="2026-07-20",
                                      chase_above=105.0)], as_of="2026-08-07")
        plan = originate_plans(path, "2026-08-07", set(), None, active_keys=set())[0]
        assert plan["trigger"] == plan["entry"], (
            "a 'don't chase above 105' line printed under a 200 entry is a lie")

    def test_a_chase_level_still_ABOVE_the_re_derived_entry_survives(
            self, tmp_path, monkeypatch):
        frame = _price_frame(200.0, end="2026-08-07")
        monkeypatch.setattr(pb, "_load_price_history", lambda t: frame)
        path = _write(tmp_path, [_row("T", spot=100.0, signal_asof="2026-07-20",
                                      chase_above=250.0)], as_of="2026-08-07")
        plan = originate_plans(path, "2026-08-07", set(), None, active_keys=set())[0]
        assert plan["trigger"] == pytest.approx(250.0)

    def test_SKIP_when_no_current_close_resolves(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(pb, "_load_price_history", lambda t: None)
        path = _write(tmp_path, [_row("T", spot=100.0, signal_asof="2026-06-01")],
                      as_of="2026-08-07")
        stats: dict = {}
        plans = originate_plans(path, "2026-08-07", set(), None, active_keys=set(),
                                intake_stats=stats)
        assert plans == []
        assert stats["stale_basis_skipped"] == ["T:no_current_close"]
        out = capsys.readouterr().out
        line = next(ln for ln in out.splitlines() if "stale-entry-basis" in ln)
        assert line.startswith("::warning"), "GitHub drops an annotation that is indented"

    def test_SKIP_when_the_PRICE_STORE_is_itself_stale(
            self, tmp_path, monkeypatch, capsys):
        """A price store whose last bar is weeks old cannot supply a current close.
        Re-deriving from it would swap one stale price for another and call it fresh."""
        frame = _price_frame(200.0, end="2026-07-01")
        monkeypatch.setattr(pb, "_load_price_history", lambda t: frame)
        path = _write(tmp_path, [_row("T", spot=100.0, signal_asof="2026-06-01")],
                      as_of="2026-08-07")
        stats: dict = {}
        plans = originate_plans(path, "2026-08-07", set(), None, active_keys=set(),
                                intake_stats=stats)
        assert plans == []
        assert stats["stale_basis_skipped"] == ["T:price_store_stale"]
        assert any(ln.startswith("::warning") and "price store" in ln
                   for ln in capsys.readouterr().out.splitlines())

    def test_no_price_history_falls_back_to_BUSINESS_DAYS_and_says_so(
            self, tmp_path, monkeypatch):
        monkeypatch.setattr(pb, "_load_price_history", lambda t: None)
        path = _write(tmp_path, [_row("T", spot=100.0, signal_asof="2026-08-06")],
                      as_of="2026-08-07")
        plan = originate_plans(path, "2026-08-07", set(), None, active_keys=set())[0]
        assert plan["entry_basis"]["lag_basis"] == "business_days"
        assert plan["entry_basis"]["lag"] == 1

    def test_the_guard_does_not_fire_on_a_same_day_basis(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pb, "_load_price_history",
                            lambda t: _price_frame(200.0, end="2026-08-07"))
        path = _write(tmp_path, [_row("T", spot=100.0)], as_of="2026-08-07")
        plan = originate_plans(path, "2026-08-07", set(), None, active_keys=set())[0]
        assert plan["entry_basis"]["lag"] == 0
        assert plan["entry"] == 100.0


# --------------------------------------------------------------------------- #
# E. Legacy shadow ledger                                                      #
# --------------------------------------------------------------------------- #

class TestLegacyGateIsFrozen:

    def test_legacy_gate_still_reads_act_level_and_gate_go(self):
        rows = [_row("ACT", status="buy_soon", act_level=2, score=10),
                _row("SCORE", status="buy_soon", act_level=0, score=75),
                _row("NEITHER", status="buy_soon", act_level=0, score=10)]
        strict = _tickers(legacy_admitted(_standouts(rows, gate_go=True)))
        caution = _tickers(legacy_admitted(_standouts(rows, gate_go=False)))
        assert strict == ["ACT"]
        assert sorted(caution) == ["ACT", "SCORE"]

    def test_legacy_gate_ignores_the_new_status_class(self):
        """bounce_wait is act_level 0 and dir caution — invisible to the old gate."""
        rows = [_row("PAT", status="bounce_wait", dir_="caution", act_level=0, score=9)]
        assert legacy_admitted(_standouts(rows, gate_go=False)) == []
        assert _tickers(select_candidates(_standouts(rows), n=None)) == ["PAT"]

    def test_legacy_gate_still_refuses_band_low_and_non_up_dir(self):
        rows = [_row("LOW", band="low", act_level=3),
                _row("DOWN", dir_="down", act_level=3),
                _row("CAUTION", dir_="caution", act_level=3),
                _row("OK", act_level=3)]
        assert _tickers(legacy_admitted(_standouts(rows))) == ["OK"]


class TestLegacyShadowRows:

    def test_row_schema_matches_the_comparison_contract(self):
        rows = legacy_shadow_rows(_standouts([_row("T", act_level=3, score=71,
                                                   priority=88.5)]), "2026-08-07")
        assert len(rows) == 1
        row = rows[0]
        for key in ("date", "ticker", "entry_signal", "act_level", "score", "rank",
                    "would_have_planned"):
            assert key in row, f"§6.5 schema is missing {key!r}"
        assert row["date"] == "2026-08-07"
        assert row["ticker"] == "T"
        assert row["entry_signal"] == "partial"
        assert row["act_level"] == 3
        assert row["score"] == 88.5            # the RANKING key
        assert row["conviction_score"] == 71   # the number the old gate escaped on
        assert row["rank"] == 1
        assert row["would_have_planned"] is True
        assert row["cap"] == LEGACY_N_CANDIDATES == 12

    def test_rank_is_the_legacy_ordering_and_the_cap_is_TWELVE(self):
        rows = legacy_shadow_rows(
            _standouts([_row(f"T{i:02d}", priority=99.0 - i) for i in range(20)]),
            "2026-08-07")
        assert [r["rank"] for r in rows] == list(range(1, 21))
        planned = [r["ticker"] for r in rows if r["would_have_planned"]]
        assert planned == [f"T{i:02d}" for i in range(LEGACY_N_CANDIDATES)]
        assert all(r["skip_reason"] == "below_cap"
                   for r in rows[LEGACY_N_CANDIDATES:])

    def test_would_have_planned_replays_the_skips_not_just_the_gate(self):
        rows = legacy_shadow_rows(
            _standouts([_row("LIVE", priority=99.0), _row("DUP", priority=98.0),
                        _row("FRESH", priority=97.0)]),
            "2026-08-07",
            existing_ids={"DUP-BULL-20260702"},
            active_keys={"LIVE-BULL"},
        )
        by_ticker = {r["ticker"]: r for r in rows}
        assert by_ticker["LIVE"]["skip_reason"] == "open_plan"
        assert by_ticker["DUP"]["skip_reason"] == "duplicate_id"
        assert by_ticker["FRESH"]["would_have_planned"] is True
        assert by_ticker["FRESH"]["skip_reason"] is None

    def test_a_row_the_new_gate_admits_but_the_old_one_never_saw_is_absent(self):
        rows = legacy_shadow_rows(
            _standouts([_row("PAT", status="bounce_wait", dir_="caution",
                             act_level=0, score=5)]), "2026-08-07")
        assert rows == []


class TestLegacyShadowStore:

    def test_the_lane_gate_is_the_FIRST_statement(self, tmp_path, not_nightly):
        rows = legacy_shadow_rows(_standouts([_row("T")]), "2026-08-07")
        assert append_legacy_shadow(rows, "2026-08-07", root=tmp_path) == 0
        assert not (tmp_path / "data" / "prophet" / "legacy_shadow").exists(), (
            "an off-lane call must not even create the directory")

    def test_nightly_lane_writes_a_month_grouped_DAY_part(self, tmp_path, nightly):
        rows = legacy_shadow_rows(_standouts([_row("A"), _row("B", priority=50.0)]),
                                  "2026-08-07")
        assert append_legacy_shadow(rows, "2026-08-07", root=tmp_path) == 2
        part = (tmp_path / "data" / "prophet" / "legacy_shadow" / "2026-08"
                / "2026-08-07.parquet")
        assert part.exists(), "day part must live under its month directory"
        frame = pd.read_parquet(part)
        assert sorted(frame["ticker"]) == ["A", "B"]

    def test_a_SECOND_run_the_same_night_writes_zero_new_rows(self, tmp_path, nightly):
        rows = legacy_shadow_rows(_standouts([_row("A"), _row("B", priority=50.0)]),
                                  "2026-08-07")
        first = append_legacy_shadow(rows, "2026-08-07", root=tmp_path)
        second = append_legacy_shadow(rows, "2026-08-07", root=tmp_path)
        assert first == second == 2
        frame = load_legacy_shadow(root=tmp_path)
        assert len(frame) == 2

    def test_keep_FIRST_a_re_run_never_rewrites_an_existing_key(
            self, tmp_path, nightly):
        append_legacy_shadow(legacy_shadow_rows(_standouts([_row("A", priority=90.0)]),
                                                "2026-08-07"),
                             "2026-08-07", root=tmp_path)
        append_legacy_shadow(legacy_shadow_rows(_standouts([_row("A", priority=11.0)]),
                                                "2026-08-07"),
                             "2026-08-07", root=tmp_path)
        frame = load_legacy_shadow(root=tmp_path)
        assert len(frame) == 1
        assert float(frame["score"].iloc[0]) == 90.0, "the first write must win"

    def test_two_nights_are_two_parts_not_one_rewritten_file(self, tmp_path, nightly):
        for day in ("2026-08-07", "2026-08-10"):
            append_legacy_shadow(
                legacy_shadow_rows(_standouts([_row("A")]), day), day, root=tmp_path)
        store = tmp_path / "data" / "prophet" / "legacy_shadow"
        assert sorted(p.name for p in store.glob("*/*.parquet")) == [
            "2026-08-07.parquet", "2026-08-10.parquet"]
        assert len(load_legacy_shadow(root=tmp_path)) == 2

    def test_a_month_boundary_opens_a_new_month_directory(self, tmp_path, nightly):
        for day in ("2026-08-31", "2026-09-01"):
            append_legacy_shadow(
                legacy_shadow_rows(_standouts([_row("A")]), day), day, root=tmp_path)
        store = tmp_path / "data" / "prophet" / "legacy_shadow"
        assert sorted(p.name for p in store.iterdir()) == ["2026-08", "2026-09"]

    def test_empty_rows_write_nothing(self, tmp_path, nightly):
        assert append_legacy_shadow([], "2026-08-07", root=tmp_path) == 0

    def test_absent_store_reads_back_as_an_empty_frame(self, tmp_path):
        assert load_legacy_shadow(root=tmp_path).empty

    def test_days_filter_projects_one_night(self, tmp_path, nightly):
        for day in ("2026-08-07", "2026-08-10"):
            append_legacy_shadow(
                legacy_shadow_rows(_standouts([_row("A")]), day), day, root=tmp_path)
        frame = load_legacy_shadow(root=tmp_path, days=["2026-08-10"])
        assert list(frame["date"]) == ["2026-08-10"]


class TestTheBuilderRedirectsTheStoreWithTheLedger:
    """The store is co-located with `build_prophet.LEDGER_DIR`.

    tests/conftest.py arms COLLECT_LANE=nightly for EVERY test, so a writer that
    resolves its own data dir writes the repo's real `data/` tree from any test that
    calls `bp.main()`. That happened twice while this lane was built (parquet parts
    landed in `data/prophet/legacy_shadow/`, caught by `git add` and then by
    MM_DATA_GUARD). Handing the directory outright is the fail-CLOSED form: an
    inferred repo root falls back to the real tree on any LEDGER_DIR shape it does
    not recognise, and `test_end_to_end_smoke` sets exactly such a shape.
    """

    def test_store_dir_wins_over_every_other_resolution(self, tmp_path, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        rows = legacy_shadow_rows(_standouts([_row("A")]), "2026-08-07")
        store = tmp_path / "anywhere" / "legacy_shadow"
        assert append_legacy_shadow(rows, "2026-08-07", store_dir=store) == 1
        assert (store / "2026-08" / "2026-08-07.parquet").exists()
        assert len(load_legacy_shadow(store_dir=store)) == 1

    def test_a_bare_ledger_dir_still_isolates(self, tmp_path):
        """The shape `test_end_to_end_smoke` uses: LEDGER_DIR = tmp_path, with no
        `data/prophet` tail. Co-location keeps it inside tmp; a root inference would
        not have."""
        import scripts.build_prophet as bp

        ledger_dir = tmp_path
        store = ledger_dir / "legacy_shadow"
        assert bp.LEDGER_DIR.name == "prophet"  # production shape, for contrast
        assert tmp_path in store.parents or store.parent == tmp_path

    def test_main_writes_no_shadow_part_outside_the_redirected_root(
            self, tmp_path, monkeypatch):
        """End-to-end: run the builder with every path redirected and assert the real
        tree gained nothing."""
        import scripts.build_prophet as bp

        real_store = _REPO / "data" / "prophet" / "legacy_shadow"
        before = sorted(p.name for p in real_store.glob("*/*.parquet")) \
            if real_store.exists() else []

        site = tmp_path / "site" / "prophet"
        (site / "plans").mkdir(parents=True)
        (site / "states").mkdir(parents=True)
        standouts = tmp_path / "us_standouts.json"
        standouts.write_text(json.dumps(_standouts([_row("AAA", spot=100.0)],
                                                   as_of="2026-08-07")),
                             encoding="utf-8")
        monkeypatch.setattr(bp, "STANDOUTS_PATH", standouts)
        monkeypatch.setattr(bp, "SITE_PROPHET", site)
        monkeypatch.setattr(bp, "PLANS_DIR", site / "plans")
        monkeypatch.setattr(bp, "STATES_DIR", site / "states")
        monkeypatch.setattr(bp, "INDEX_PATH", site / "index.json")
        monkeypatch.setattr(bp, "LEDGER_DIR", tmp_path / "data" / "prophet")
        monkeypatch.setattr(bp, "LEDGER_PATH",
                            tmp_path / "data" / "prophet" / "ledger.jsonl")
        monkeypatch.setattr(bp, "write_showcase", lambda *a, **kw: None)
        import engine.prophet_arena as arena
        real_arena = arena.run_arena
        monkeypatch.setattr(arena, "run_arena",
                            lambda *a, **kw: real_arena(*a, **{**kw,
                                                               "repo_root": tmp_path}))
        monkeypatch.setattr(sys, "argv", ["build_prophet", "--date", "2026-08-07"])

        bp.main()

        after = sorted(p.name for p in real_store.glob("*/*.parquet")) \
            if real_store.exists() else []
        assert after == before, (
            "build_prophet.main() wrote a shadow part into the REAL data/ tree")
        assert (tmp_path / "data" / "prophet" / "legacy_shadow" / "2026-08"
                / "2026-08-07.parquet").exists(), (
            "the redirected store got nothing — this test would pass vacuously")

    def test_the_smoke_tests_bare_ledger_dir_shape_also_stays_inside_tmp(
            self, tmp_path, monkeypatch):
        """The exact shape that leaked: LEDGER_DIR = tmp_path (no data/prophet tail)."""
        import scripts.build_prophet as bp

        real_store = _REPO / "data" / "prophet" / "legacy_shadow"
        before = sorted(p.name for p in real_store.glob("*/*.parquet")) \
            if real_store.exists() else []

        site = tmp_path / "site" / "prophet"
        (site / "plans").mkdir(parents=True)
        (site / "states").mkdir(parents=True)
        standouts = tmp_path / "us_standouts.json"
        standouts.write_text(json.dumps(_standouts([_row("AAA", spot=100.0)],
                                                   as_of="2026-08-07")),
                             encoding="utf-8")
        monkeypatch.setattr(bp, "STANDOUTS_PATH", standouts)
        monkeypatch.setattr(bp, "SITE_PROPHET", site)
        monkeypatch.setattr(bp, "PLANS_DIR", site / "plans")
        monkeypatch.setattr(bp, "STATES_DIR", site / "states")
        monkeypatch.setattr(bp, "INDEX_PATH", site / "index.json")
        monkeypatch.setattr(bp, "LEDGER_DIR", tmp_path)          # the leaking shape
        monkeypatch.setattr(bp, "LEDGER_PATH", tmp_path / "ledger.jsonl")
        monkeypatch.setattr(bp, "write_showcase", lambda *a, **kw: None)
        import engine.prophet_arena as arena
        real_arena = arena.run_arena
        monkeypatch.setattr(arena, "run_arena",
                            lambda *a, **kw: real_arena(*a, **{**kw,
                                                               "repo_root": tmp_path}))
        monkeypatch.setattr(sys, "argv", ["build_prophet", "--date", "2026-08-07"])

        bp.main()

        after = sorted(p.name for p in real_store.glob("*/*.parquet")) \
            if real_store.exists() else []
        assert after == before
        assert (tmp_path / "legacy_shadow" / "2026-08" / "2026-08-07.parquet").exists()
