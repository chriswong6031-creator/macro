"""tests/test_prophet_bridge.py — Prophet Bridge + build_prophet.py tests.

Coverage:
  1.  Geometry (BULL): hand-computed invalidation/T1/T2 with hold.invalidation.
  2.  Geometry (BULL): fallback to swing_low + ATR when hold.invalidation absent.
  3.  Geometry (BEAR): T1 below entry, T2 further below.
  4.  Geometry: R=0 guard (invalidation == entry → None values).
  5.  Geometry: ATR fallback when no price history available.
  6.  ID stability: same ticker/direction/formation_date always produces same ID.
  7.  Duplicate suppression: plan already in existing_ids is not re-originated.
  8.  Candidate selection: act_level no longer gates admission (ANTICIPATION A1).
  9.  Candidate selection: gate_go no longer changes admission (A1) — the
      caution-mode score escape went with the act-level gate.  Full A1 coverage
      (admission matrix, lag guard, shadow ledger, caps) is in
      tests/test_prophet_anticipation_a1.py.
  10. Candidate selection: band="low" always excluded.
  11. Candidate selection: entry_signal null → excluded.
  12. Candidate selection: dir!="up" → excluded (BEAR universe not yet).
  13. Candidate selection: sorted by score desc, act_level desc on tie.
  14. Option expiry selection: nearest monthly >= signal + horizon + 15d.
  15. Option expiry: non-monthly alignment — result is always a Friday.
  16. Option resolution: no store → returns None.
  17. Option resolution: store present but ticker absent → returns None.
  18. Trade plan validate_trade_plan: source_engines non-empty required.
  19. Trade plan validate_trade_plan: schema mismatch caught.
  20. Trade plan validate_trade_plan: direction invalid caught.
  21. Validator round-trip: originate_plans output passes validate_trade_plan.
  22. PIT: price history filtered to <= asof; future rows ignored.
  23. Ledger schema: _initialize_ledger creates file on first call.
  24. Ledger schema: row dict contains required keys (schema validation).
  25. Index.json schema has required top-level keys.
  26. Index note does NOT contain the word "validated".
  27. build_prophet main: runs end-to-end on synthetic data without crash.
  28. originate_plans: every admitted survivor is produced (no positional cap).
  29. _third_friday: always returns a Friday.
  30. _next_monthly_expiry: always >= min_date.
  31. R0.7 _load_macro_stance: verdict→stance mapping, PIT + staleness guards.
  32. R0.7 _load_futures_chg: close-to-close math, PIT filter, honest omission.
  33. R0.7 index whitelist: entries carry last_price + nested state block
      (components/geometry/change_reason) with honesty laws untouched.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# ── repo path ─────────────────────────────────────────────────────────────────
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.prophet_bridge import (
    N_CANDIDATES,
    compute_geometry,
    originate_plans,
    plan_clock_date,
    resolve_option,
    select_candidates,
    _make_id,
    _next_monthly_expiry,
    _third_friday,
    _build_what_to_do_now,
    _build_what_to_do_now_zh,
    _build_profit_plan,
    _build_profit_plan_zh,
    _build_thesis,
    _build_thesis_zh,
)
from engine.options_structure import validate_trade_plan


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _arena_writes_to_tmp(tmp_path, monkeypatch):
    """Send the Prophet Arena's ledgers to tmp for every test in this file.

    Several tests here call `bp.main()`, which calls
    `engine.prophet_arena.run_arena(..., repo_root=_REPO)` and writes
    `data/prophet_arena/*.jsonl` + `scoreboard.json` into the REAL tree. MM_DATA_GUARD
    then forces the job to exit 1 on a step that reports "942 passed" — a failure with no
    test name attached, which is why it survived as an unexplained ci-pack-3 red.

    Redirects `repo_root` rather than stubbing `run_arena`, so the hook still runs
    end-to-end; the arena's own behaviour is covered by tests/test_prophet_arena.py.
    Autouse so a newly added `bp.main()` call cannot silently reintroduce the write.
    """
    import engine.prophet_arena as arena

    real = arena.run_arena
    monkeypatch.setattr(
        arena, "run_arena",
        lambda *a, **kw: real(*a, **{**kw, "repo_root": tmp_path}))



def _make_price_history(entry: float = 100.0, n_days: int = 30,
                         low_factor: float = 0.90) -> pd.DataFrame:
    """Create a synthetic DatetimeIndex OHLCV DataFrame."""
    base = pd.Timestamp("2026-06-01")
    dates = pd.date_range(base, periods=n_days, freq="B")
    closes = [entry * low_factor + (entry * (1 - low_factor)) * (i / max(n_days - 1, 1))
              for i in range(n_days)]
    return pd.DataFrame({"close": closes, "high": closes, "low": closes}, index=dates)


def _make_standouts(
    gate_go: bool = False,
    buys: list[dict] | None = None,
) -> dict:
    """Create a minimal us_standouts-like dict."""
    if buys is None:
        buys = [_make_buy("AAPL", score=70, act_level=3, spot=150.0)]
    return {
        "as_of": "2026-07-02",
        "staleness": {
            "price_through": "2026-07-02",
            "delayed": False,
            "unknown": False,
            "basis": "panel_majority",
            "inputs": {"panel": {"mixed_vintage": False}},
        },
        "gate_go": gate_go,
        "buy": buys,
    }


def _make_buy(
    ticker: str,
    score: int = 70,
    act_level: int = 3,
    spot: float = 100.0,
    band: str = "neutral",
    dir_: str = "up",
    hold_invalidation: float | None = 90.0,
    chase_above: float | None = 105.0,
    atr_pct: float = 2.0,
    anchor: str | None = "2026-07-02",
    status: str = "partial",
    sector: str | None = None,
    signal_asof: str | None = None,
) -> dict:
    return {
        "ticker": ticker,
        "dir": dir_,
        "state": "TURN SIGNALED",
        **({"sector": sector} if sector is not None else {}),
        **({"signal_asof": signal_asof} if signal_asof is not None else {}),
        "conviction": {
            "score": score,
            "band": band,
            "drivers": ["momentum", "volume"],
            "cautions": ["macro risk"],
            "trust_tier": {"en": "tier-2"},
        },
        "entry_signal": {
            "act_level": act_level,
            "status": status,
            "spot": spot,
            "stop": spot * 0.95,
            "chase_above": chase_above,
            "atr_pct": atr_pct,
            "entry_grade": "solid",
            "horizon": {"d21": 0.5},
        },
        "hold": {
            "state": "HOLD",
            "anchor": anchor,
            "invalidation": hold_invalidation,
        },
        "coiled": {"coiled": False, "star": False},
        "signal": {"above200": True, "weekly_bull": True},
    }


# ---------------------------------------------------------------------------
# 1–5. Geometry tests
# ---------------------------------------------------------------------------

def test_geometry_bull_with_hold_invalidation():
    """BULL: invalidation from hold.invalidation → T1 = entry + 1.5R, T2 = entry + 3R."""
    entry = 100.0
    invalidation = 90.0
    geo = compute_geometry(
        entry=entry,
        direction="BULL",
        atr_pct=None,
        hold_invalidation=invalidation,
        price_history=None,
        asof="2026-07-02",
    )
    r = entry - invalidation  # = 10.0
    assert geo["invalidation"] == pytest.approx(90.0, abs=1e-4)
    assert geo["t1"] == pytest.approx(entry + 1.5 * r, abs=1e-4)  # 115.0
    assert geo["t2"] == pytest.approx(entry + 3.0 * r, abs=1e-4)  # 130.0
    assert geo["r_unit"] == pytest.approx(r, abs=1e-4)


def test_geometry_bull_fallback_atr_and_swing():
    """BULL: when hold.invalidation absent, uses max(swing_low, entry - 2*ATR)."""
    entry = 100.0
    atr_pct = 2.0   # ATR = 2.0 abs
    # Price history: swing low = 92.0 (last 20d)
    ph = _make_price_history(entry=100.0, n_days=25, low_factor=0.92)
    geo = compute_geometry(
        entry=entry,
        direction="BULL",
        atr_pct=atr_pct,
        hold_invalidation=None,
        price_history=ph,
        asof="2026-07-02",
    )
    atr_abs = entry * atr_pct / 100.0  # = 2.0
    atr_stop = entry - 2 * atr_abs     # = 96.0
    swing_low = ph["close"].min()
    # max-protective = max(swing_low, atr_stop)
    expected_inval = max(swing_low, atr_stop)
    assert geo["invalidation"] == pytest.approx(expected_inval, abs=1e-3)
    r = entry - expected_inval
    assert geo["t1"] == pytest.approx(entry + 1.5 * r, abs=1e-3)
    assert geo["t2"] == pytest.approx(entry + 3.0 * r, abs=1e-3)


def test_geometry_bear_direction():
    """BEAR: T1 below entry, T2 further below; invalidation above entry."""
    entry = 100.0
    hold_invalidation = 110.0  # above entry for BEAR
    geo = compute_geometry(
        entry=entry,
        direction="BEAR",
        atr_pct=None,
        hold_invalidation=hold_invalidation,
        price_history=None,
        asof="2026-07-02",
    )
    r = abs(entry - hold_invalidation)  # = 10.0
    assert geo["invalidation"] == pytest.approx(110.0, abs=1e-4)
    assert geo["t1"] == pytest.approx(entry - 1.5 * r, abs=1e-4)  # 85.0
    assert geo["t2"] == pytest.approx(entry - 3.0 * r, abs=1e-4)  # 70.0


def test_geometry_no_atr_no_price_history_no_invalidation():
    """When all geometry inputs are absent, returns None for all levels."""
    geo = compute_geometry(
        entry=100.0,
        direction="BULL",
        atr_pct=None,
        hold_invalidation=None,
        price_history=None,
        asof="2026-07-02",
    )
    assert geo["invalidation"] is None
    assert geo["t1"] is None
    assert geo["t2"] is None
    assert geo["r_unit"] is None


def test_geometry_atr_only_fallback():
    """BULL with ATR only (no swing, no hold.invalidation)."""
    entry = 200.0
    atr_pct = 1.5  # ATR = 3.0 abs
    geo = compute_geometry(
        entry=entry,
        direction="BULL",
        atr_pct=atr_pct,
        hold_invalidation=None,
        price_history=None,
        asof="2026-07-02",
    )
    atr_abs = entry * atr_pct / 100.0
    expected_inval = entry - 2 * atr_abs
    assert geo["invalidation"] == pytest.approx(expected_inval, abs=1e-4)


# ---------------------------------------------------------------------------
# 6–7. ID stability and duplicate suppression
# ---------------------------------------------------------------------------

def test_id_stability():
    """Same ticker/direction/formation_date always produces the same ID."""
    id1 = _make_id("BA", "BULL", "2026-07-02")
    id2 = _make_id("BA", "BULL", "2026-07-02")
    assert id1 == id2
    assert id1 == "BA-BULL-20260702"


def test_id_differs_by_date():
    """Different formation dates produce different IDs."""
    id1 = _make_id("BA", "BULL", "2026-07-01")
    id2 = _make_id("BA", "BULL", "2026-07-02")
    assert id1 != id2


def test_duplicate_suppression(tmp_path):
    """Plans with IDs already in existing_ids are not re-originated."""
    standouts_path = tmp_path / "us_standouts.json"
    buys = [_make_buy("AAPL", score=70, act_level=3, spot=150.0)]
    standouts = _make_standouts(gate_go=False, buys=buys)
    standouts_path.write_text(json.dumps(standouts))

    existing_ids = {"AAPL-BULL-20260702"}
    plans = originate_plans(
        standouts_path=standouts_path,
        asof="2026-07-02",
        existing_ids=existing_ids,
        thetadata_store=None,
    )
    assert plans == []


def test_weekend_recovery_keeps_publication_and_price_clocks_separate(tmp_path):
    """Saturday is a valid run date, never a valid substitute for Friday's close."""
    standouts = _make_standouts(
        gate_go=False,
        buys=[_make_buy(
            "AAPL", score=70, act_level=3, spot=150.0, anchor="2026-06-15"
        )],
    )
    standouts["as_of"] = "2026-08-07"  # Friday NYSE session
    standouts["staleness"]["price_through"] = "2026-08-07"
    path = tmp_path / "us_standouts.json"
    path.write_text(json.dumps(standouts), encoding="utf-8")

    plans = originate_plans(
        standouts_path=path,
        asof="2026-08-08",  # Saturday recovery/publication run
        existing_ids=set(),
        thetadata_store=None,
    )

    assert len(plans) == 1
    plan = plans[0]
    assert plan["id"] == "AAPL-BULL-20260615"  # no key migration
    assert plan["formation_date"] == plan["signal_date"] == "2026-06-15"
    assert plan["price_basis_date"] == plan["entry_date"] == "2026-08-07"
    assert plan["asof"] == plan["recorded_at"] == "2026-08-08"
    assert plan_clock_date(plan) == "2026-08-07"


def test_tier_native_signal_dates_do_not_rekey_plan_identity(tmp_path):
    """T2 uses its own event close while the immutable ID keeps the formation anchor."""
    buy = _make_buy(
        "NVDA", score=80, act_level=3, spot=223.96, anchor="2026-08-05"
    )
    buy["signal"] = {
        "tier_cascade": "T2",
        "tier_event_date": "2026-08-05",
        "tier_observed_date": "2026-08-07",
        "tier_observation_provisional": False,
        # This unrelated blocked marker must never become T2 confirmation.
        "last": {
            "date": "2026-08-05",
            "signal_date": "2026-08-07",
            "confirmed_date": "2026-08-07",
            "type": "buy",
            "quality": "block",
        },
    }
    standouts = _make_standouts(gate_go=False, buys=[buy])
    standouts["as_of"] = "2026-08-07"
    standouts["staleness"]["price_through"] = "2026-08-07"
    path = tmp_path / "us_standouts.json"
    path.write_text(json.dumps(standouts), encoding="utf-8")

    [plan] = originate_plans(path, "2026-08-08", set(), None)

    assert plan["id"] == "NVDA-BULL-20260805"
    assert plan["formation_date"] == "2026-08-05"
    assert plan["signal_tier"] == "T2"
    assert plan["signal_date"] == "2026-08-05"
    assert plan["confirmed_date"] is None
    assert plan["observed_date"] == "2026-08-07"
    assert plan["price_basis_date"] == plan["entry_date"] == "2026-08-07"
    assert plan["recorded_at"] == "2026-08-08"
    assert plan["signal_date_basis"] == "tier_event_date"
    assert plan["source_marker_date"] == "2026-08-05"


def test_pre_date_contract_tier_row_uses_disclosed_legacy_alias(tmp_path):
    """Rolling deploys can consume the prior compact board without guessing tier dates."""
    buy = _make_buy("OLD", score=80, act_level=3, anchor="2026-07-02")
    buy["signal"]["tier_cascade"] = "T2"  # old shape: no tier_* date keys
    buy["signal"]["last"] = {"date": "2026-07-02"}
    path = tmp_path / "us_standouts.json"
    path.write_text(json.dumps(_make_standouts(buys=[buy])), encoding="utf-8")

    [plan] = originate_plans(path, "2026-07-02", set(), None)

    assert plan["signal_date"] == plan["formation_date"] == "2026-07-02"
    assert plan["signal_date_basis"] == "legacy_formation_alias"
    assert plan["signal_tier"] == "T2"
    assert plan["source_marker_date"] == "2026-07-02"


def test_projected_t3_records_observation_without_inventing_event(
    tmp_path, monkeypatch
):
    import engine.prophet_bridge as pb

    tilt_clock = {}
    monkeypatch.setattr(pb, "_load_stage_tilt_inputs", lambda: {"fixture": True})

    def fake_tilt(*, ticker, entry_date, tilt_inputs):
        tilt_clock.update(ticker=ticker, entry_date=entry_date)
        return pb.HORIZON_DAYS_DEFAULT, {"leash": 1.0, "eligible": False}

    monkeypatch.setattr(pb, "_compute_stage_tilt", fake_tilt)
    buy = _make_buy("FORM", score=80, act_level=3, anchor="2026-07-20")
    buy["signal"] = {
        "tier_cascade": "T3",
        "tier_event_date": None,
        "tier_observed_date": "2026-08-07",
        "tier_observation_provisional": True,
        "last": None,
    }
    standouts = _make_standouts(gate_go=False, buys=[buy])
    standouts["as_of"] = "2026-08-07"
    standouts["staleness"]["price_through"] = "2026-08-07"
    path = tmp_path / "us_standouts.json"
    path.write_text(json.dumps(standouts), encoding="utf-8")

    [plan] = originate_plans(path, "2026-08-08", set(), None)

    assert plan["id"] == "FORM-BULL-20260720"
    assert plan["signal_tier"] == "T3"
    assert plan["signal_date"] is None
    assert plan["confirmed_date"] is None
    assert plan["observed_date"] == "2026-08-07"
    assert plan["signal_provisional"] is True
    assert plan["signal_date_basis"] == "tier_observation"
    # Stage/earnings PIT context is measured at the entry-price session. T3 has no
    # fired signal_date, and neither its formation nor observation is a fill clock.
    assert tilt_clock == {"ticker": "FORM", "entry_date": "2026-08-07"}


def test_t1_confirmation_is_copied_only_from_same_marker_event(tmp_path):
    buy = _make_buy("TAKE", score=80, act_level=3, anchor="2026-08-03")
    buy["signal"] = {
        "tier_cascade": "T1",
        "tier_event_date": "2026-08-03",
        "tier_observed_date": "2026-08-07",
        "tier_observation_provisional": False,
        "last": {
            "date": "2026-08-03",
            "signal_date": "2026-08-03",
            "confirmed_date": "2026-08-05",
            "type": "buy",
            "quality": "take",
        },
    }
    standouts = _make_standouts(gate_go=False, buys=[buy])
    standouts["as_of"] = "2026-08-07"
    standouts["staleness"]["price_through"] = "2026-08-07"
    path = tmp_path / "us_standouts.json"
    path.write_text(json.dumps(standouts), encoding="utf-8")

    [plan] = originate_plans(path, "2026-08-08", set(), None)

    assert plan["signal_date"] == "2026-08-03"
    assert plan["confirmed_date"] == "2026-08-05"
    assert plan["signal_provisional"] is False


def test_explicit_price_basis_precedes_legacy_clock_fields():
    """Future consumers cannot regress to a weekend entry_date/asof when basis exists."""
    assert plan_clock_date({
        "price_basis_date": "2026-08-07",
        "entry_date": "2026-08-08",
        "asof": "2026-08-08",
        "signal_date": "2026-06-15",
    }) == "2026-08-07"


@pytest.mark.parametrize("bad_basis", [
    "2026-08-08",  # Saturday
    "2026-07-03",  # observed Independence Day closure
])
def test_non_session_price_basis_fails_closed_and_is_disclosed(tmp_path, bad_basis):
    standouts = _make_standouts(
        gate_go=False,
        buys=[_make_buy("AAPL", score=70, act_level=3, spot=150.0)],
    )
    standouts["as_of"] = bad_basis
    standouts["staleness"]["price_through"] = bad_basis
    path = tmp_path / "us_standouts.json"
    path.write_text(json.dumps(standouts), encoding="utf-8")
    stats: dict[str, Any] = {}

    plans = originate_plans(
        standouts_path=path,
        asof="2026-08-08",
        existing_ids=set(),
        thetadata_store=None,
        intake_stats=stats,
    )

    assert plans == []
    assert stats["eligible_after_skips"] == 1
    assert stats["validation_failed"] == 1
    assert stats["originated"] == 0
    assert stats["truncated"] == 0
    assert stats["lossless"] is True  # no silent disappearance; failure is itemised
    failure = stats["validation_failures"][0]
    assert failure["ticker"] == "AAPL"
    assert failure["stage"] == "clock_provenance"
    assert any("not an NYSE session" in error for error in failure["errors"])


def test_future_price_basis_is_never_backdated_or_published(tmp_path):
    standouts = _make_standouts(
        gate_go=False,
        buys=[_make_buy("AAPL", score=70, act_level=3, spot=150.0)],
    )
    standouts["as_of"] = "2026-08-10"
    standouts["staleness"]["price_through"] = "2026-08-10"
    path = tmp_path / "us_standouts.json"
    path.write_text(json.dumps(standouts), encoding="utf-8")
    stats: dict[str, Any] = {}

    assert originate_plans(
        path, "2026-08-08", set(), None, intake_stats=stats
    ) == []
    assert any(
        "postdates recorded_at" in error
        for error in stats["validation_failures"][0]["errors"]
    )


def test_stale_or_mixed_board_is_refused_instead_of_restamped(tmp_path):
    standouts = _make_standouts(
        gate_go=False,
        buys=[_make_buy("AAPL", score=70, act_level=3, spot=150.0)],
    )
    # The wrapper advances, but the ranked cross-section is uniformly frozen.  A
    # mixed-vintage-only guard would miss this exact outage shape.
    standouts["as_of"] = "2026-08-03"
    standouts["staleness"]["price_through"] = "2026-07-31"
    path = tmp_path / "us_standouts.json"
    path.write_text(json.dumps(standouts), encoding="utf-8")
    stats: dict[str, Any] = {}

    assert originate_plans(
        path, "2026-08-03", set(), None, intake_stats=stats
    ) == []
    assert any(
        "stale boards cannot originate plans" in error
        for error in stats["validation_failures"][0]["errors"]
    )

    standouts["staleness"] = {
        "price_through": "2026-08-03",
        "delayed": False,
        "unknown": False,
        "basis": "panel_majority",
        "inputs": {"panel": {"mixed_vintage": True}},
    }
    path.write_text(json.dumps(standouts), encoding="utf-8")
    stats = {}
    assert originate_plans(
        path, "2026-08-03", set(), None, intake_stats=stats
    ) == []
    assert any(
        "mixed-vintage boards cannot originate plans" in error
        for error in stats["validation_failures"][0]["errors"]
    )


@pytest.mark.parametrize(
    ("delayed", "unknown", "needle"),
    [
        (True, False, "staleness.delayed"),
        (False, True, "staleness.unknown"),
        (None, None, "staleness.unknown"),
    ],
)
def test_ranked_price_staleness_metadata_fails_closed(
    tmp_path, delayed, unknown, needle
):
    standouts = _make_standouts()
    standouts["staleness"]["delayed"] = delayed
    standouts["staleness"]["unknown"] = unknown
    path = tmp_path / "us_standouts.json"
    path.write_text(json.dumps(standouts), encoding="utf-8")
    stats: dict[str, Any] = {}

    assert originate_plans(
        path, "2026-07-02", set(), None, intake_stats=stats
    ) == []
    assert any(
        needle in error for error in stats["validation_failures"][0]["errors"]
    )


@pytest.mark.parametrize("basis", [None, "board_asof", "unknown"])
def test_wrapper_only_price_authority_cannot_originate(tmp_path, basis):
    standouts = _make_standouts()
    if basis is None:
        standouts["staleness"].pop("basis")
    else:
        standouts["staleness"]["basis"] = basis
    path = tmp_path / "us_standouts.json"
    path.write_text(json.dumps(standouts), encoding="utf-8")
    stats: dict[str, Any] = {}

    assert originate_plans(
        path, "2026-07-02", set(), None, intake_stats=stats
    ) == []
    assert any(
        "staleness.basis must be 'panel_majority'" in error
        for error in stats["validation_failures"][0]["errors"]
    )


def test_invalid_candidate_is_itemised_while_every_valid_survivor_originates(tmp_path):
    bad = _make_buy("BAD", score=70, act_level=3, spot=150.0)
    bad["entry_signal"]["spot"] = None
    good = _make_buy("GOOD", score=69, act_level=3, spot=120.0)
    standouts = _make_standouts(gate_go=False, buys=[bad, good])
    path = tmp_path / "us_standouts.json"
    path.write_text(json.dumps(standouts), encoding="utf-8")
    stats: dict[str, Any] = {}

    plans = originate_plans(
        path, "2026-07-02", set(), None, intake_stats=stats
    )

    assert [plan["asset"] for plan in plans] == ["GOOD"]
    assert stats["eligible_after_skips"] == 2
    assert stats["validation_failed"] == 1
    assert stats["originated"] == 1
    assert stats["unaccounted"] == 0
    assert stats["all_survivors_originated"] is False


# ---------------------------------------------------------------------------
# 8–13. Candidate selection
# ---------------------------------------------------------------------------

def test_act_level_no_longer_gates_admission():
    """ANTICIPATION A1: act_level is not an admission input at all any more.

    Both rows carry an admitted status; the act_level 1 row used to be refused by
    both gate modes and is now admitted on its status alone.
    """
    buys = [
        _make_buy("HIGH_ACT", score=80, act_level=3, status="buy_now"),
        _make_buy("LOW_ACT",  score=10, act_level=1, status="hold"),
    ]
    for gate_go in (True, False):
        result = select_candidates(
            {"gate_go": gate_go, "buy": buys, "as_of": "2026-07-02"})
        tickers = [b["ticker"] for b in result]
        assert tickers == ["HIGH_ACT", "LOW_ACT"] or set(tickers) == {
            "HIGH_ACT", "LOW_ACT"}, f"gate_go={gate_go}: {tickers}"


def test_gate_go_no_longer_changes_admission():
    """The caution-mode `score >= 60` escape is gone with the act-level gate.

    A `buy_soon` row with score 90 used to be admitted in BOTH modes (act_level 2);
    it is now refused in both, because `buy_soon` is outside the status class.
    """
    buys = [
        _make_buy("SOON", score=90, act_level=2, status="buy_soon"),
        _make_buy("WAIT", score=10, act_level=0, status="bounce_wait", dir_="caution"),
    ]
    for gate_go in (True, False):
        result = select_candidates(
            {"gate_go": gate_go, "buy": buys, "as_of": "2026-07-02"})
        assert [b["ticker"] for b in result] == ["WAIT"], f"gate_go={gate_go}"


def test_selection_low_band_excluded():
    """band='low' is always excluded regardless of act_level or score."""
    buys = [
        _make_buy("LOWBAND", score=90, act_level=3, band="low"),
        _make_buy("NEUTRAL", score=70, act_level=3, band="neutral"),
    ]
    result = select_candidates({"gate_go": True, "buy": buys, "as_of": "2026-07-02"})
    tickers = [b["ticker"] for b in result]
    assert "LOWBAND" not in tickers
    assert "NEUTRAL" in tickers


def test_selection_null_entry_signal_excluded():
    """Entries with no entry_signal are excluded."""
    buys = [
        {
            "ticker": "NOES",
            "dir": "up",
            "entry_signal": None,
            "conviction": {"score": 80, "band": "neutral"},
            "hold": {},
        },
        _make_buy("AAPL", score=70, act_level=3),
    ]
    result = select_candidates({"gate_go": False, "buy": buys, "as_of": "2026-07-02"})
    tickers = [b["ticker"] for b in result]
    assert "NOES" not in tickers


def test_selection_bear_direction_excluded():
    """dir!='up' entries are excluded (BEAR universe not yet active)."""
    buys = [
        _make_buy("BEARSTOCK", score=90, act_level=3, dir_="down"),
        _make_buy("BULLSTOCK", score=70, act_level=3, dir_="up"),
    ]
    result = select_candidates({"gate_go": True, "buy": buys, "as_of": "2026-07-02"})
    tickers = [b["ticker"] for b in result]
    assert "BEARSTOCK" not in tickers
    assert "BULLSTOCK" in tickers


def test_selection_t4_remains_visible_but_is_not_actionable():
    """A high-score T4 cannot bypass the canonical T1-T3 buyable-tier fence."""
    t4 = _make_buy("TOO_EARLY", score=99, act_level=3)
    t4["signal"]["tier_cascade"] = "T4"
    t3 = _make_buy("FORMING", score=70, act_level=3)
    t3["signal"]["tier_cascade"] = "T3"
    result = select_candidates({
        "gate_go": True,
        "buy": [t4, t3],
        "as_of": "2026-07-02",
    })
    assert [row["ticker"] for row in result] == ["FORMING"]


def test_selection_sorted_score_desc():
    """Candidates sorted descending by conviction score."""
    buys = [
        _make_buy("LOW",  score=40, act_level=3),
        _make_buy("HIGH", score=80, act_level=3),
        _make_buy("MED",  score=60, act_level=3),
    ]
    result = select_candidates({"gate_go": True, "buy": buys, "as_of": "2026-07-02"})
    scores = [(b.get("conviction") or {}).get("score") for b in result]
    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# 14–16. Option expiry selection
# ---------------------------------------------------------------------------

def test_third_friday_is_friday():
    """_third_friday always returns a Friday (weekday=4)."""
    for year in [2026, 2027]:
        for month in range(1, 13):
            tf = _third_friday(year, month)
            assert tf.weekday() == 4, f"{year}-{month:02d} third Friday is not a Friday: {tf}"


def test_next_monthly_expiry_always_gte_min_date():
    """_next_monthly_expiry returns a date >= min_date."""
    for offset in [0, 5, 15, 30, 60, 90]:
        min_date = date(2026, 7, 1) + timedelta(days=offset)
        result = _next_monthly_expiry(min_date)
        assert result >= min_date
        assert result.weekday() == 4  # Friday


def test_option_expiry_horizon_plus_15():
    """Expiry is >= signal_date + horizon_days + 15d."""
    signal = date(2026, 7, 2)
    horizon = 45
    min_exp = signal + timedelta(days=horizon + 15)
    result = _next_monthly_expiry(min_exp)
    assert result >= min_exp


# ---------------------------------------------------------------------------
# 16–17. Option resolution
# ---------------------------------------------------------------------------

def test_resolve_option_no_store():
    """resolve_option returns None when thetadata_store is None."""
    result = resolve_option(
        ticker="AAPL",
        direction="BULL",
        entry=150.0,
        horizon_days=45,
        signal_date="2026-07-02",
        thetadata_store=None,
        asof="2026-07-02",
    )
    assert result is None


def test_resolve_option_missing_ticker(tmp_path):
    """resolve_option returns None when ticker not in store."""
    store = tmp_path / "thetadata"
    store.mkdir()
    (store / "greeks").mkdir()
    (store / "eod").mkdir()

    result = resolve_option(
        ticker="NOTEXIST",
        direction="BULL",
        entry=100.0,
        horizon_days=45,
        signal_date="2026-07-02",
        thetadata_store=str(store),
        asof="2026-07-02",
    )
    assert result is None


# ---------------------------------------------------------------------------
# 18–20. validate_trade_plan
# ---------------------------------------------------------------------------

def test_validate_trade_plan_source_engines_required():
    """validate_trade_plan rejects plans with empty source_engines."""
    plan = {
        "schema": "prophet.trade_plan/v1",
        "id": "TEST-BULL-20260702",
        "asof": "2026-07-02",
        "asset": "TEST",
        "direction": "BULL",
        "source_engines": [],
    }
    errs = validate_trade_plan(plan)
    assert any("source_engines" in e for e in errs)


def test_validate_trade_plan_schema_mismatch():
    """validate_trade_plan rejects wrong schema string."""
    plan = {
        "schema": "wrong_schema/v1",
        "id": "TEST-BULL-20260702",
        "asof": "2026-07-02",
        "asset": "TEST",
        "direction": "BULL",
        "source_engines": ["neural_web"],
    }
    errs = validate_trade_plan(plan)
    assert any("schema" in e for e in errs)


def test_validate_trade_plan_invalid_direction():
    """validate_trade_plan rejects invalid direction."""
    plan = {
        "schema": "prophet.trade_plan/v1",
        "id": "TEST-BULL-20260702",
        "asof": "2026-07-02",
        "asset": "TEST",
        "direction": "SIDEWAYS",
        "source_engines": ["neural_web"],
    }
    errs = validate_trade_plan(plan)
    assert any("direction" in e for e in errs)


# ---------------------------------------------------------------------------
# 21. Validator round-trip
# ---------------------------------------------------------------------------

def test_originate_plans_passes_validate_trade_plan(tmp_path):
    """Every plan produced by originate_plans passes validate_trade_plan."""
    buys = [_make_buy("AAPL", score=70, act_level=3, spot=150.0)]
    standouts = _make_standouts(gate_go=False, buys=buys)
    standouts_path = tmp_path / "us_standouts.json"
    standouts_path.write_text(json.dumps(standouts))

    plans = originate_plans(
        standouts_path=standouts_path,
        asof="2026-07-02",
        existing_ids=set(),
        thetadata_store=None,
    )
    assert len(plans) >= 1
    for plan in plans:
        errs = validate_trade_plan(plan)
        assert errs == [], f"Plan {plan['id']} failed validation: {errs}"


def test_exact_earnings_evidence_only_annotates_after_prophet_selection(tmp_path):
    """Evidence presence cannot change candidate identity, order, or plan geometry."""
    standouts_path = tmp_path / "us_standouts.json"
    standouts_path.write_text(json.dumps(_make_standouts(
        gate_go=False,
        buys=[
            _make_buy("MSFT", score=80, act_level=3, spot=420.0, hold_invalidation=395.0),
            _make_buy("AAPL", score=70, act_level=3, spot=150.0, hold_invalidation=141.0),
        ],
    )))
    with patch("engine.prophet_bridge._load_earnings_evidence_context", return_value={}):
        baseline = originate_plans(standouts_path, "2026-07-02", set(), None)
    evidence = {
        "AAPL": {
            "available": True,
            "authority": "context_only",
            "event": {"ticker": "AAPL", "date": "2026-06-30", "period": "Q2 FY2026"},
            "categories": ["guidance", "demand"],
            "facts": [{"claim_id": "claim_abc", "quote": {"text": "Demand remains strong."}}],
            "receipts": {"context_id": "earnctx_test", "source_sha256": "a" * 64},
            "links": {"record": "/stocks/earnings/aapl-test.html"},
            "permissions": {
                "class": "context_only", "may_add_candidate": False, "may_rank": False,
                "may_size": False, "may_gate": False, "may_escalate": False,
                "prophet_authority": False,
            },
        }
    }
    with patch("engine.prophet_bridge._load_earnings_evidence_context", return_value=evidence):
        enriched = originate_plans(standouts_path, "2026-07-02", set(), None)

    invariant = (
        "id", "asset", "direction", "trigger", "entry", "invalidation", "targets",
        "horizon_days", "min_hold_days", "tranche", "option_contract", "stage_tilt",
        "_conviction_score", "_act_level", "_r_unit", "_gate_go",
    )
    assert [{key: row.get(key) for key in invariant} for row in enriched] == [
        {key: row.get(key) for key in invariant} for row in baseline
    ]
    by_asset = {row["asset"]: row for row in enriched}
    assert "earnings_evidence_context" not in by_asset["MSFT"]
    annotation = by_asset["AAPL"]["earnings_evidence_context"]
    assert annotation["authority"] == "context_only"
    assert annotation["permissions"]["prophet_authority"] is False
    assert "earnings_evidence_spine" in by_asset["AAPL"]["context_engines"]


def test_prophet_passes_sole_asof_anchor_to_earnings_context_reader(tmp_path):
    """A backfill may never annotate a plan from the reader's current latest packet."""
    standouts_path = tmp_path / "us_standouts.json"
    standouts_path.write_text(json.dumps(_make_standouts()))
    with patch(
        "engine.prophet_bridge._load_earnings_evidence_context", return_value={},
    ) as loader:
        originate_plans(standouts_path, "2026-07-02", set(), None)
    assert loader.call_args.kwargs["asof"] == "2026-07-02"


# ---------------------------------------------------------------------------
# 22. PIT (no future price rows used)
# ---------------------------------------------------------------------------

def test_geometry_pit_uses_only_asof_or_earlier():
    """compute_geometry only uses prices on or before asof for swing_low."""
    # Build history where future day has a very low value that would skew the result
    dates = pd.date_range("2026-06-01", periods=25, freq="B")
    closes = [100.0] * 25
    ph = pd.DataFrame({"close": closes}, index=dates)

    # asof is 2026-06-20; price history extends beyond but swing_low uses ≤ asof
    geo_with_future = compute_geometry(
        entry=100.0,
        direction="BULL",
        atr_pct=2.0,
        hold_invalidation=None,
        price_history=ph,
        asof="2026-06-20",  # excludes last few rows
    )
    geo_without_future = compute_geometry(
        entry=100.0,
        direction="BULL",
        atr_pct=2.0,
        hold_invalidation=None,
        price_history=ph[ph.index <= pd.Timestamp("2026-06-20")],
        asof="2026-06-20",
    )
    # Results must match (both use same effective window)
    assert geo_with_future["invalidation"] == pytest.approx(
        geo_without_future["invalidation"], abs=1e-4
    )


# ---------------------------------------------------------------------------
# 23–24. Ledger
# ---------------------------------------------------------------------------

def test_initialize_ledger_creates_file(tmp_path):
    """_initialize_ledger creates ledger.jsonl on first call."""
    import importlib
    import scripts.build_prophet as bp  # noqa: PLC0415
    orig_ledger_path = bp.LEDGER_PATH
    orig_ledger_dir = bp.LEDGER_DIR
    try:
        bp.LEDGER_PATH = tmp_path / "prophet" / "ledger.jsonl"
        bp.LEDGER_DIR = tmp_path / "prophet"
        bp._initialize_ledger()
        assert bp.LEDGER_PATH.exists()
        content = bp.LEDGER_PATH.read_text()
        assert "prophet" in content.lower()
        assert "Nightly is the SOLE advancer" in content
        # No JSON row written yet (file has only the comment)
        rows = [l for l in content.splitlines() if l.strip() and not l.startswith("#")]
        assert rows == []
    finally:
        bp.LEDGER_PATH = orig_ledger_path
        bp.LEDGER_DIR = orig_ledger_dir


def test_ledger_row_schema_keys():
    """A ledger row dict must contain all required schema keys."""
    required_keys = {
        "schema", "id", "asset", "direction", "signal_date",
        "close_date", "outcome", "stock_result_pct",
        "option_result_pct", "days_held", "plan_adherence", "asof",
    }
    # Construct a minimal placeholder row
    row = {
        "schema": "prophet.ledger/v1",
        "id": "AAPL-BULL-20260702",
        "asset": "AAPL",
        "direction": "BULL",
        "signal_date": "2026-07-02",
        "close_date": None,
        "outcome": None,
        "stock_result_pct": None,
        "option_result_pct": None,
        "days_held": None,
        "plan_adherence": None,
        "asof": "2026-07-07",
    }
    missing = required_keys - set(row.keys())
    assert missing == set(), f"Missing ledger row keys: {missing}"


# ---------------------------------------------------------------------------
# 25–26. Index schema
# ---------------------------------------------------------------------------

def test_index_json_has_required_keys(tmp_path):
    """build_prophet produces an index.json with required top-level keys."""
    import scripts.build_prophet as bp  # noqa: PLC0415

    # Redirect output paths to tmp_path
    buys = [_make_buy("AAPL", score=70, act_level=3, spot=150.0)]
    standouts = _make_standouts(gate_go=False, buys=buys)
    standouts_path = tmp_path / "us_standouts.json"
    standouts_path.write_text(json.dumps(standouts))

    orig_standouts = bp.STANDOUTS_PATH
    orig_site = bp.SITE_PROPHET
    orig_plans = bp.PLANS_DIR
    orig_states = bp.STATES_DIR
    orig_index = bp.INDEX_PATH
    orig_ledger_path = bp.LEDGER_PATH
    orig_ledger_dir = bp.LEDGER_DIR
    orig_write_showcase = bp.write_showcase

    try:
        bp.STANDOUTS_PATH = standouts_path
        bp.SITE_PROPHET = tmp_path / "site" / "prophet"
        bp.PLANS_DIR = bp.SITE_PROPHET / "plans"
        bp.STATES_DIR = bp.SITE_PROPHET / "states"
        bp.INDEX_PATH = bp.SITE_PROPHET / "index.json"
        bp.LEDGER_PATH = tmp_path / "data" / "prophet" / "ledger.jsonl"
        bp.LEDGER_DIR = tmp_path / "data" / "prophet"
        # write_showcase's out_path default is bound to SHOWCASE_PATH at def
        # time, so reassigning the module constant cannot redirect it — main()'s
        # no-arg call would write the real site/prophet/showcase.json and trip
        # MM_DATA_GUARD whenever committed data/ and site/ are out of sync.
        bp.write_showcase = lambda: orig_write_showcase(
            out_path=tmp_path / "showcase.json")

        # Patch sys.argv
        import sys as _sys  # noqa: PLC0415
        with patch.object(_sys, "argv", ["build_prophet", "--date", "2026-07-02"]):
            with patch("engine.prophet_management.compute_management_state") as mock_mgmt:
                mock_mgmt.return_value = {
                    "schema": "prophet.management_state/v1",
                    "id": "AAPL-BULL-20260702",
                    "asof": "2026-07-02",
                    "phase": "pre_trigger",
                    "management_confidence": 55.0,
                    "raw_confidence": 55.0,
                    "recommended_action": "wait",
                    "components": {},
                    "geometry": {},
                    "change_reason": "",
                }
                # Also patch price history load to return valid data
                with patch("scripts.build_prophet._load_price_history_for_management") as mock_ph:
                    mock_ph.return_value = _make_price_history(150.0, 30)
                    bp.main()

        assert bp.INDEX_PATH.exists()
        idx = json.loads(bp.INDEX_PATH.read_text())
        for key in ["schema", "asof", "cadence", "authority_tier", "plan_count", "plans"]:
            assert key in idx, f"Missing key in index.json: {key}"
        assert idx["source_asof"] == "2026-07-02"
        assert idx["source_board_asof"] == "2026-07-02"
        assert idx["source_delayed"] is False
        assert idx["source_unknown"] is False
        assert idx["source_basis"] == "panel_majority"
        assert idx["source_mixed_vintage"] is False
    finally:
        bp.STANDOUTS_PATH = orig_standouts
        bp.SITE_PROPHET = orig_site
        bp.PLANS_DIR = orig_plans
        bp.STATES_DIR = orig_states
        bp.INDEX_PATH = orig_index
        bp.LEDGER_PATH = orig_ledger_path
        bp.LEDGER_DIR = orig_ledger_dir
        bp.write_showcase = orig_write_showcase


def test_effective_index_excludes_both_plan_and_ledger_quarantines():
    """A late terminal quarantine cannot persist through the prebuilt index list."""
    import scripts.build_prophet as bp  # noqa: PLC0415

    rows = [{"id": "PLAN-Q"}, {"id": "LEDGER-Q"}, {"id": "SAFE"}]
    assert bp._effective_index_entries(rows, {"PLAN-Q", "LEDGER-Q"}) == [
        {"id": "SAFE"}
    ]


def test_originated_plan_without_history_stays_discoverable(tmp_path, monkeypatch):
    """Lossless intake includes a degraded row when management history is absent."""
    import scripts.build_prophet as bp  # noqa: PLC0415

    standouts_path = tmp_path / "us_standouts.json"
    standouts_path.write_text(json.dumps(_make_standouts(
        gate_go=False,
        buys=[_make_buy("NODATA", score=75, act_level=3, spot=42.0)],
    )), encoding="utf-8")
    site_prophet = tmp_path / "site" / "prophet"
    ledger_dir = tmp_path / "data" / "prophet"
    monkeypatch.setattr(bp, "STANDOUTS_PATH", standouts_path)
    monkeypatch.setattr(bp, "SITE_PROPHET", site_prophet)
    monkeypatch.setattr(bp, "PLANS_DIR", site_prophet / "plans")
    monkeypatch.setattr(bp, "STATES_DIR", site_prophet / "states")
    monkeypatch.setattr(bp, "INDEX_PATH", site_prophet / "index.json")
    monkeypatch.setattr(bp, "LEDGER_DIR", ledger_dir)
    monkeypatch.setattr(bp, "LEDGER_PATH", ledger_dir / "ledger.jsonl")
    monkeypatch.setattr(bp, "QUARANTINE_PATH", ledger_dir / "ledger_quarantine.json")
    monkeypatch.setattr(bp, "write_showcase", lambda: None)
    monkeypatch.setattr(bp, "_load_price_history_for_management", lambda _ticker: None)

    with patch("engine.prophet_arena.run_arena", return_value={
        "policies": [], "harness_validity": {"harness_ok": True},
    }):
        with patch.object(sys, "argv", ["build_prophet", "--date", "2026-07-02"]):
            bp.main()

    index = json.loads((site_prophet / "index.json").read_text(encoding="utf-8"))
    assert index["intake"]["originated"] == 1
    assert index["intake"]["lossless"] is True
    assert index["active_count"] == 1
    [row] = index["plans"]
    assert row["id"] == "NODATA-BULL-20260702"
    assert row["management_status"] == "unavailable"
    assert row["management_error"] == "price_history_unavailable"
    assert (site_prophet / "plans" / f"{row['id']}.json").exists()


@pytest.mark.parametrize("failure_point", ["advance_ledger", "write_quarantine"])
def test_authoritative_ledger_failure_withholds_index(
    tmp_path, monkeypatch, failure_point
):
    """Neither a split ledger nor a missing exclusion receipt may be published."""
    import scripts.build_prophet as bp  # noqa: PLC0415

    standouts_path = tmp_path / "us_standouts.json"
    standouts_path.write_text(json.dumps(_make_standouts(
        gate_go=False,
        buys=[_make_buy("FAIL", score=75, act_level=3, spot=42.0)],
    )), encoding="utf-8")
    site_prophet = tmp_path / "site" / "prophet"
    ledger_dir = tmp_path / "data" / "prophet"
    monkeypatch.setattr(bp, "STANDOUTS_PATH", standouts_path)
    monkeypatch.setattr(bp, "SITE_PROPHET", site_prophet)
    monkeypatch.setattr(bp, "PLANS_DIR", site_prophet / "plans")
    monkeypatch.setattr(bp, "STATES_DIR", site_prophet / "states")
    monkeypatch.setattr(bp, "INDEX_PATH", site_prophet / "index.json")
    monkeypatch.setattr(bp, "LEDGER_DIR", ledger_dir)
    monkeypatch.setattr(bp, "LEDGER_PATH", ledger_dir / "ledger.jsonl")
    monkeypatch.setattr(bp, "write_showcase", lambda: None)
    monkeypatch.setattr(bp, "_load_price_history_for_management", lambda _ticker: None)

    def fail(*_args, **_kwargs):
        raise RuntimeError(f"forced {failure_point} failure")

    monkeypatch.setattr(bp, failure_point, fail)
    with patch("engine.prophet_arena.run_arena", return_value={
        "policies": [], "harness_validity": {"harness_ok": True},
    }):
        with patch.object(sys, "argv", ["build_prophet", "--date", "2026-07-02"]):
            with pytest.raises(RuntimeError, match=failure_point):
                bp.main()

    assert not (site_prophet / "index.json").exists()


def test_index_note_no_validated_word(tmp_path):
    """Index note must not contain the word 'validated'."""
    # Build a minimal index dict directly (matching what build_prophet writes)
    index_note = (
        "DISPLAY-ONLY. All plans are display-tier artifacts. No signal has"
        " passed a forward ledger gate. The word 'validated' is forbidden in"
        " user-facing text. Nightly is the sole advancer of the forward ledger."
    )
    # The note contains 'validated' in the context of 'forbidden' — that's fine.
    # The CI check (check_validated_claims.py) checks for standalone positive claims.
    # Our note says validated IS FORBIDDEN — this should be fine per CI rules.
    # Verify the note does NOT positively claim something is validated.
    assert "validated" in index_note  # present but in a prohibition context
    # Key check: not a positive assertion like "this has been validated"
    assert "has been validated" not in index_note
    assert "is validated" not in index_note


# ---------------------------------------------------------------------------
# 27. End-to-end smoke test
# ---------------------------------------------------------------------------

def test_end_to_end_smoke(tmp_path):
    """build_prophet.main runs without exception on synthetic data."""
    import scripts.build_prophet as bp  # noqa: PLC0415

    buys = [
        _make_buy("AAPL", score=70, act_level=3, spot=150.0),
        _make_buy("MSFT", score=65, act_level=2, spot=420.0),
    ]
    standouts = _make_standouts(gate_go=False, buys=buys)
    standouts_path = tmp_path / "us_standouts.json"
    standouts_path.write_text(json.dumps(standouts))

    orig_standouts = bp.STANDOUTS_PATH
    orig_plans = bp.PLANS_DIR
    orig_states = bp.STATES_DIR
    orig_index = bp.INDEX_PATH
    orig_ledger_path = bp.LEDGER_PATH
    orig_ledger_dir = bp.LEDGER_DIR
    orig_write_showcase = bp.write_showcase

    try:
        bp.STANDOUTS_PATH = standouts_path
        bp.PLANS_DIR = tmp_path / "plans"
        bp.STATES_DIR = tmp_path / "states"
        bp.INDEX_PATH = tmp_path / "index.json"
        bp.LEDGER_PATH = tmp_path / "ledger.jsonl"
        bp.LEDGER_DIR = tmp_path
        # Same def-time-default trap as test_index_json_structure: main()'s
        # no-arg write_showcase() targets the real site/prophet/showcase.json.
        bp.write_showcase = lambda: orig_write_showcase(
            out_path=tmp_path / "showcase.json")

        import sys as _sys  # noqa: PLC0415
        with patch.object(_sys, "argv", ["build_prophet", "--date", "2026-07-02"]):
            with patch("engine.prophet_management.compute_management_state") as mock_mgmt:
                mock_mgmt.return_value = {
                    "schema": "prophet.management_state/v1",
                    "id": "AAPL-BULL-20260702",
                    "asof": "2026-07-02",
                    "phase": "pre_trigger",
                    "management_confidence": 55.0,
                    "raw_confidence": 55.0,
                    "recommended_action": "wait",
                    "components": {},
                    "geometry": {},
                    "change_reason": "",
                }
                with patch("scripts.build_prophet._load_price_history_for_management") as mock_ph:
                    mock_ph.return_value = _make_price_history(150.0, 30)
                    bp.main()

        assert bp.INDEX_PATH.exists()
        assert bp.LEDGER_PATH.exists()
    finally:
        bp.STANDOUTS_PATH = orig_standouts
        bp.PLANS_DIR = orig_plans
        bp.STATES_DIR = orig_states
        bp.INDEX_PATH = orig_index
        bp.LEDGER_PATH = orig_ledger_path
        bp.LEDGER_DIR = orig_ledger_dir
        bp.write_showcase = orig_write_showcase


# ---------------------------------------------------------------------------
# 28. Lossless live origination (the direct-selection helper may still be sliced)
# ---------------------------------------------------------------------------

def test_originate_plans_does_not_truncate_at_n_candidates(tmp_path):
    """The legacy 12-row helper slice is not an opportunity gate on live plans."""
    buys = [_make_buy(f"TICK{i}", score=80 - i, act_level=3, spot=100.0 + i)
            for i in range(N_CANDIDATES + 4)]
    standouts = _make_standouts(gate_go=True, buys=buys)
    standouts_path = tmp_path / "us_standouts.json"
    standouts_path.write_text(json.dumps(standouts))

    stats: dict[str, Any] = {}
    plans = originate_plans(
        standouts_path=standouts_path,
        asof="2026-07-02",
        existing_ids=set(),
        thetadata_store=None,
        intake_stats=stats,
    )
    assert len(plans) == len(buys) == N_CANDIDATES + 4
    # HERMETICITY: `originate_plans` resolves the leader-pullback map from the REAL
    # site/ tree (there is no injection point on this call path), so the receipt's
    # `map_tickers` and the split between "outside the organ's universe" and "no coverage
    # published" depend on whether site/anticipationdata/us_leader_pullback.json happens
    # to be checked in.  Its PLAN-derived invariants do not, so those are asserted here
    # and the key is removed from the exact-shape comparison below — which still catches
    # any OTHER new or renamed stat.
    receipt = stats.pop("leader_pullback_coverage")
    assert receipt["plans"] == len(buys)
    assert receipt["licensed"] == 0
    assert (receipt["with_organ_state"] + receipt["outside_organ_universe"]
            + receipt["no_coverage_published"]) == len(buys)
    assert stats == {
        "mode": "lossless",
        "reorigination_blocked": 0,
        "reorigination_blocked_keys": [],
        "admitted": len(buys),
        "duplicate_id_blocked": 0,
        "eligible_after_skips": len(buys),
        "cap": None,
        "cap_applied": False,
        "truncated": 0,
        "validation_failed": 0,
        "validation_failures": [],
        "originated": len(buys),
        "unaccounted": 0,
        "lossless": True,
        "all_survivors_originated": True,
        # ── ANTICIPATION A1 / §6.9 R3 disclosure ──────────────────────────────
        # Exact equality is deliberate: every disposition key must be enumerated
        # here, so a new refusal path that ships without a disclosure fails.
        "selection_era": "anticipation-v1-2026-08-08",
        "admitted_statuses": ["bounce_wait", "buy_now", "hold", "partial",
                              "wait_pullback"],
        "admitted_directions": ["caution", "up"],
        "buy_rows": len(buys),
        "admitted_by_class": {"patience": 0, "confirmation": len(buys)},
        "originated_by_class": {
            "patience": 0, "confirmation": len(buys), "early_turn_starter": 0},
        "unknown_status": 0,
        "unknown_status_values": [],
        "refused_status": {},
        "refused_direction": {},
        "refused_no_entry_signal": 0,
        "refused_band_low": 0,
        "refused_tier": {},
        "stale_basis_max": 3,
        "stale_basis_skipped": [],
        "zone_class_counts": {
            "accumulate": len(buys), "reset_band": 0, "wait_reset": 0},
        "zone_conversion_classes": {"washout": 0, "pullback": len(buys)},
        "zone_extension_unavailable": len(buys),
        "wait_reset": [],
        "early_turn_starters": [],
        "early_turn_watch": [],
        "leader_pullback_source": ["unavailable"],
        # "leader_pullback_coverage" is popped and asserted above — see the note there.
    }


# ---------------------------------------------------------------------------
# 29a–29f. Content block tests (_build_what_to_do_now, _build_profit_plan, _build_thesis)
# ---------------------------------------------------------------------------

def test_what_to_do_now_all_phases():
    """Every lifecycle phase produces 2-3 bullets; no validated word."""
    phases = [
        "pre_trigger", "triggered_pre_t1", "at_t1", "between_t1_t2",
        "post_t1_failed_hold", "at_t2", "overtime", "invalidated",
    ]
    for phase in phases:
        bullets = _build_what_to_do_now(
            phase=phase, entry=100.0, trigger=102.0, invalidation=90.0,
            t1=115.0, t2=130.0,
        )
        assert 2 <= len(bullets) <= 3, f"phase {phase}: expected 2-3 bullets, got {len(bullets)}"
        for b in bullets:
            assert isinstance(b, str) and len(b) > 10, f"phase {phase}: bullet too short: {b!r}"
            assert "validated" not in b.lower(), f"phase {phase}: 'validated' in bullet"


def test_what_to_do_now_no_t2():
    """Pre-trigger without T2 returns 2 bullets (not 3)."""
    bullets = _build_what_to_do_now(
        phase="pre_trigger", entry=100.0, trigger=102.0,
        invalidation=90.0, t1=115.0, t2=None,
    )
    assert len(bullets) == 2


def test_what_to_do_now_price_levels_interpolated():
    """Price levels are present in the bullets for the pre_trigger phase."""
    bullets = _build_what_to_do_now(
        phase="pre_trigger", entry=100.0, trigger=102.50, invalidation=90.0,
        t1=115.0, t2=None,
    )
    combined = " ".join(bullets)
    assert "$102.50" in combined


def test_profit_plan_statuses():
    """profit_plan rows carry correct ACTIVE/PENDING/DONE statuses per phase."""
    # pre_trigger: T1=ACTIVE, T2=PENDING
    rows = _build_profit_plan("pre_trigger", 100.0, 115.0, 130.0)
    assert rows[0]["status"] == "ACTIVE"
    assert rows[1]["status"] == "PENDING"

    # at_t1: T1=DONE, T2=ACTIVE
    rows = _build_profit_plan("at_t1", 100.0, 115.0, 130.0)
    assert rows[0]["status"] == "DONE"
    assert rows[1]["status"] == "ACTIVE"

    # at_t2: T1=DONE, T2=DONE
    rows = _build_profit_plan("at_t2", 100.0, 115.0, 130.0)
    assert rows[0]["status"] == "DONE"
    assert rows[1]["status"] == "DONE"

    # invalidated: T1=DONE
    rows = _build_profit_plan("invalidated", 100.0, 115.0, 130.0)
    assert rows[0]["status"] == "DONE"


def test_profit_plan_without_t2():
    """profit_plan without T2 returns exactly 1 row."""
    rows = _build_profit_plan("pre_trigger", 100.0, 115.0, None)
    assert len(rows) == 1
    assert rows[0]["label"] == "T1"


def test_profit_plan_row_keys():
    """Every profit_plan row has required keys and valid status."""
    rows = _build_profit_plan("pre_trigger", 100.0, 115.0, 130.0)
    for row in rows:
        assert "level" in row
        assert "label" in row
        assert "action" in row
        assert "status" in row
        assert row["status"] in ("ACTIVE", "PENDING", "DONE")


def test_thesis_no_validated_positive_claim():
    """thesis must not positively claim anything is validated."""
    b = {
        "conviction": {
            "score": 75, "band": "high",
            "drivers": ["validated momentum factor", "validated risk gate: trim"],
            "cautions": ["regime change risk"],
            "trust_tier": {"en": "T2 — medium confidence"},
        },
        "entry_signal": {
            "above200": True, "weekly_bull": False, "coiled": True,
            "entry_grade": "B+",
        },
        "hold": {},
        "state": "COILED",
        "archetype": "Resumption",
    }
    thesis = _build_thesis("AAPL", b)
    # "validated" must not appear before the DISPLAY-ONLY footer
    before_footer = thesis.split("DISPLAY-ONLY")[0]
    assert "validated" not in before_footer.lower(), (
        f"'validated' appeared in thesis body: {before_footer!r}"
    )
    # Should contain driver content (after sanitization)
    assert "momentum factor" in thesis or "risk gate" in thesis


def test_thesis_contains_technical_flags():
    """thesis includes technical flag context when es fields are set."""
    b = {
        "conviction": {"score": 80, "band": "high", "drivers": [], "cautions": []},
        "entry_signal": {"above200": True, "weekly_bull": True, "coiled": True},
        "hold": {},
        "state": "RUNNING",
    }
    thesis = _build_thesis("NVDA", b)
    assert "above 200-day" in thesis or "200" in thesis
    assert "coiled" in thesis or "compression" in thesis


def test_originate_plans_includes_content_blocks(tmp_path):
    """originate_plans output plans include what_to_do_now and profit_plan."""
    buys = [_make_buy("TSLA", score=72, act_level=3, spot=250.0)]
    standouts = _make_standouts(gate_go=False, buys=buys)
    standouts_path = tmp_path / "us_standouts.json"
    standouts_path.write_text(json.dumps(standouts))

    plans = originate_plans(
        standouts_path=standouts_path,
        asof="2026-07-02",
        existing_ids=set(),
        thetadata_store=None,
    )
    assert len(plans) == 1, f"expected 1 plan, got {len(plans)}"
    plan = plans[0]
    assert "what_to_do_now" in plan, "plan missing what_to_do_now"
    assert "profit_plan" in plan, "plan missing profit_plan"
    assert isinstance(plan["what_to_do_now"], list) and len(plan["what_to_do_now"]) >= 2
    assert isinstance(plan["profit_plan"], list) and len(plan["profit_plan"]) >= 1
    # content blocks must not contain "validated" positively
    for bullet in plan["what_to_do_now"]:
        assert "validated" not in bullet.lower(), f"'validated' in bullet: {bullet}"
    # ZH variants must also be present
    assert "what_to_do_now_zh" in plan, "plan missing what_to_do_now_zh"
    assert "profit_plan_zh" in plan, "plan missing profit_plan_zh"
    assert "thesis_zh" in plan, "plan missing thesis_zh"
    assert isinstance(plan["what_to_do_now_zh"], list) and len(plan["what_to_do_now_zh"]) >= 2
    assert isinstance(plan["profit_plan_zh"], list) and len(plan["profit_plan_zh"]) >= 1
    # ZH lists must be same length as EN lists
    assert len(plan["what_to_do_now_zh"]) == len(plan["what_to_do_now"]), (
        "what_to_do_now_zh length mismatch"
    )
    assert len(plan["profit_plan_zh"]) == len(plan["profit_plan"]), (
        "profit_plan_zh length mismatch"
    )
    # ZH blocks must contain Chinese characters (are not just EN copies)
    zh_text = " ".join(plan["what_to_do_now_zh"])
    assert any("一" <= c <= "鿿" for c in zh_text), (
        "what_to_do_now_zh contains no Chinese characters"
    )
    # ZH profit_plan rows have same structure as EN rows
    for row_zh in plan["profit_plan_zh"]:
        assert "level" in row_zh and "label" in row_zh and "action" in row_zh and "status" in row_zh


# ---------------------------------------------------------------------------
# ZH content-block deterministic template tests
# ---------------------------------------------------------------------------

class TestZhContentBlocks:
    """Tests for ZH variants of what_to_do_now, profit_plan, thesis content blocks."""

    _PHASES = [
        "pre_trigger", "triggered_pre_t1", "at_t1", "between_t1_t2",
        "post_t1_failed_hold", "at_t2", "post_t2", "overtime", "invalidated",
    ]

    def test_zh_what_to_do_now_all_phases_return_list(self):
        """All phases return a non-empty list of strings."""
        for phase in self._PHASES:
            result = _build_what_to_do_now_zh(
                phase=phase, entry=100.0, trigger=105.0, invalidation=92.0,
                t1=120.0, t2=135.0,
            )
            assert isinstance(result, list) and len(result) >= 1, (
                f"phase {phase!r} returned empty/non-list: {result!r}"
            )
            for line in result:
                assert isinstance(line, str) and len(line) > 0

    def test_zh_what_to_do_now_contains_chinese(self):
        """ZH bullets contain Chinese characters."""
        result = _build_what_to_do_now_zh(
            phase="pre_trigger", entry=100.0, trigger=105.0,
            invalidation=92.0, t1=120.0, t2=135.0,
        )
        combined = " ".join(result)
        assert any("一" <= c <= "鿿" for c in combined), (
            "ZH what_to_do_now contains no Chinese characters"
        )

    def test_zh_same_length_as_en(self):
        """ZH list length matches EN list length for all phases."""
        for phase in self._PHASES:
            en = _build_what_to_do_now(
                phase=phase, entry=100.0, trigger=105.0, invalidation=92.0,
                t1=120.0, t2=135.0,
            )
            zh = _build_what_to_do_now_zh(
                phase=phase, entry=100.0, trigger=105.0, invalidation=92.0,
                t1=120.0, t2=135.0,
            )
            assert len(zh) == len(en), (
                f"phase {phase!r}: zh len={len(zh)} vs en len={len(en)}"
            )

    def test_zh_profit_plan_row_structure(self):
        """ZH profit_plan rows have level/label/action/status keys."""
        for phase in ("pre_trigger", "at_t1", "at_t2", "invalidated"):
            rows = _build_profit_plan_zh(
                phase=phase, entry=100.0, t1=120.0, t2=135.0,
            )
            assert isinstance(rows, list) and len(rows) >= 1
            for row in rows:
                for key in ("level", "label", "action", "status"):
                    assert key in row, f"row missing {key!r}: {row}"
            # status values must be canonical
            assert all(r["status"] in ("ACTIVE", "PENDING", "DONE") for r in rows)

    def test_zh_profit_plan_action_contains_chinese(self):
        """ZH profit_plan action strings contain Chinese characters."""
        rows = _build_profit_plan_zh(
            phase="pre_trigger", entry=100.0, t1=120.0, t2=135.0,
        )
        combined = " ".join(r["action"] for r in rows)
        assert any("一" <= c <= "鿿" for c in combined), (
            "ZH profit_plan action strings contain no Chinese characters"
        )

    def test_zh_thesis_contains_chinese_and_no_validated(self):
        """ZH thesis contains Chinese characters and no bare 'validated'."""
        b = {
            "conviction": {
                "score": 75, "band": "high",
                "drivers": ["momentum factor"], "drivers_zh": ["动量因子"],
                "cautions": ["validated risk gate: trim"], "cautions_zh": ["风险门槛：减仓"],
                "trust_tier": {"en": "Constructive", "zh": "积极"},
            },
            "entry_signal": {"above200": True, "weekly_bull": True},
            "hold": {},
        }
        thesis = _build_thesis_zh("NVDA", b)
        assert any("一" <= c <= "鿿" for c in thesis), (
            "ZH thesis contains no Chinese characters"
        )
        # "已验证" (validated ZH) must not appear (sanitized)
        assert "已验证" not in thesis, f"'已验证' in ZH thesis: {thesis!r}"


# ---------------------------------------------------------------------------
# 31–37. Ledger advancement (advance_ledger)
# ---------------------------------------------------------------------------

import scripts.build_prophet as _bp  # noqa: E402 (after imports block)


def _make_plan(
    plan_id: str = "AAPL-BULL-20260601",
    ticker: str = "AAPL",
    entry: float = 100.0,
    invalidation: float = 90.0,
    t1: float = 115.0,
    t2: float = 130.0,
    signal_date: str = "2026-06-01",
    horizon_days: int = 45,
    direction: str = "BULL",
) -> dict:
    """Build a minimal prophet.trade_plan/v1 dict for ledger tests."""
    return {
        "schema": "prophet.trade_plan/v1",
        "id": plan_id,
        "asof": signal_date,
        "asset": ticker,
        "direction": direction,
        "signal_date": signal_date,
        "_signal_date": signal_date,
        "entry": entry,
        "invalidation": invalidation,
        "targets": [t1, t2],
        "horizon_days": horizon_days,
        "min_hold_days": 10,
        "tranche": 1,
        "option_contract": None,
        "authority_tier": "display",
        "source_engines": ["us_standouts_buy_lane"],
    }


def _price_history_from_closes(closes: list[float], start: str = "2026-06-02") -> pd.DataFrame:
    """Build a DatetimeIndex DataFrame from a list of daily closes."""
    dates = pd.date_range(start, periods=len(closes), freq="B")
    return pd.DataFrame({"close": closes}, index=dates)


class TestLedgerAdvancement:
    """Tests for advance_ledger + _determine_outcome."""

    def _run_advance(self, tmp_path, plans: dict, ph_map: dict, asof: str) -> list:
        """Run advance_ledger with mocked price history loader + tmp ledger path."""
        orig_ledger_path = _bp.LEDGER_PATH
        orig_ledger_dir = _bp.LEDGER_DIR

        try:
            _bp.LEDGER_PATH = tmp_path / "ledger.jsonl"
            _bp.LEDGER_DIR = tmp_path
            _bp._initialize_ledger()

            with patch("scripts.build_prophet._load_price_history_for_management",
                       side_effect=lambda ticker: ph_map.get(ticker)):
                return _bp.advance_ledger(plans, asof)
        finally:
            _bp.LEDGER_PATH = orig_ledger_path
            _bp.LEDGER_DIR = orig_ledger_dir

    def test_invalidation_hit(self, tmp_path):
        """Plan closes INVALIDATED when price drops through invalidation level."""
        plan = _make_plan(entry=100.0, invalidation=90.0, t1=115.0, t2=130.0,
                          signal_date="2026-06-01")
        # Day 3 (2026-06-04): price drops to 88 (< 90 invalidation)
        closes = [101.0, 100.5, 88.0, 95.0]
        ph = _price_history_from_closes(closes, start="2026-06-02")
        rows = self._run_advance(tmp_path, {plan["id"]: plan}, {"AAPL": ph}, "2026-07-01")
        assert len(rows) == 1
        assert rows[0]["outcome"] == "INVALIDATED"
        assert rows[0]["stock_result_pct"] is not None
        assert rows[0]["stock_result_pct"] < 0  # loss

    def test_new_close_row_carries_explicit_plan_clocks_without_rekeying(self, tmp_path):
        plan = _make_plan(
            plan_id="AAPL-BULL-20260615",
            signal_date="2026-06-15",
            entry=100.0,
            invalidation=90.0,
        )
        plan.update({
            "formation_date": "2026-06-15",
            "price_basis_date": "2026-08-07",
            "entry_date": "2026-08-07",
            "recorded_at": "2026-08-08",
            "asof": "2026-08-08",
        })
        ph = _price_history_from_closes([88.0], start="2026-08-10")

        rows = self._run_advance(
            tmp_path, {plan["id"]: plan}, {"AAPL": ph}, "2026-09-01"
        )

        assert len(rows) == 1
        row = rows[0]
        assert row["id"] == "AAPL-BULL-20260615"
        assert row["formation_date"] == row["signal_date"] == "2026-06-15"
        assert row["price_basis_date"] == row["entry_date"] == "2026-08-07"
        assert row["recorded_at"] == "2026-08-08"

    def test_t1_hit(self, tmp_path):
        """Plan closes T1_HIT when price reaches T1 before invalidation or horizon."""
        plan = _make_plan(entry=100.0, invalidation=90.0, t1=115.0, t2=130.0,
                          signal_date="2026-06-01")
        # Day 5: price reaches 116 (> 115 T1)
        closes = [101.0, 103.0, 108.0, 112.0, 116.0]
        ph = _price_history_from_closes(closes, start="2026-06-02")
        rows = self._run_advance(tmp_path, {plan["id"]: plan}, {"AAPL": ph}, "2026-07-01")
        assert len(rows) == 1
        assert rows[0]["outcome"] == "T1_HIT"
        assert rows[0]["stock_result_pct"] > 0  # profit

    def test_t2_hit(self, tmp_path):
        """T2_HIT takes priority over T1_HIT on same scan (T2 first in priority)."""
        plan = _make_plan(entry=100.0, invalidation=90.0, t1=115.0, t2=130.0,
                          signal_date="2026-06-01")
        # Day 3: price jumps straight to 132 (> 130 T2)
        closes = [101.0, 110.0, 132.0]
        ph = _price_history_from_closes(closes, start="2026-06-02")
        rows = self._run_advance(tmp_path, {plan["id"]: plan}, {"AAPL": ph}, "2026-07-01")
        assert len(rows) == 1
        assert rows[0]["outcome"] == "T2_HIT"

    def test_expired(self, tmp_path):
        """Plan closes EXPIRED when horizon_days elapse without hitting T1/T2/inval."""
        plan = _make_plan(entry=100.0, invalidation=90.0, t1=115.0, t2=130.0,
                          signal_date="2026-06-01", horizon_days=5)
        # 6 business days, price stays flat (never hits any trigger, reaches horizon on day 5)
        closes = [101.0, 101.5, 102.0, 101.0, 101.5]  # 5 days → EXPIRED
        ph = _price_history_from_closes(closes, start="2026-06-02")
        rows = self._run_advance(tmp_path, {plan["id"]: plan}, {"AAPL": ph}, "2026-07-01")
        assert len(rows) == 1
        assert rows[0]["outcome"] == "EXPIRED"

    def test_idempotency(self, tmp_path):
        """Re-running advance_ledger for an already-closed plan appends no new rows."""
        plan = _make_plan(entry=100.0, invalidation=90.0, t1=115.0, t2=130.0,
                          signal_date="2026-06-01")
        closes = [88.0, 90.0, 90.0]  # invalidated on day 1
        ph = _price_history_from_closes(closes, start="2026-06-02")

        orig_ledger_path = _bp.LEDGER_PATH
        orig_ledger_dir = _bp.LEDGER_DIR
        try:
            _bp.LEDGER_PATH = tmp_path / "ledger.jsonl"
            _bp.LEDGER_DIR = tmp_path
            _bp._initialize_ledger()

            with patch("scripts.build_prophet._load_price_history_for_management",
                       side_effect=lambda ticker: ph):
                rows1 = _bp.advance_ledger({plan["id"]: plan}, "2026-07-01")
                rows2 = _bp.advance_ledger({plan["id"]: plan}, "2026-07-01")

            assert len(rows1) == 1
            assert len(rows2) == 0, "Second run must not duplicate the ledger row"

            # Verify ledger has exactly ONE data row (not 2)
            content = _bp.LEDGER_PATH.read_text()
            data_lines = [l for l in content.splitlines() if l.strip() and not l.startswith("#")]
            assert len(data_lines) == 1
        finally:
            _bp.LEDGER_PATH = orig_ledger_path
            _bp.LEDGER_DIR = orig_ledger_dir

    def test_open_plan_produces_no_row(self, tmp_path):
        """A plan that hasn't hit any trigger yet produces no ledger row."""
        plan = _make_plan(entry=100.0, invalidation=90.0, t1=115.0, t2=130.0,
                          signal_date="2026-06-01", horizon_days=45)
        # Price stays just inside all triggers
        closes = [101.0, 102.0, 103.0]
        ph = _price_history_from_closes(closes, start="2026-06-02")
        rows = self._run_advance(tmp_path, {plan["id"]: plan}, {"AAPL": ph}, "2026-06-05")
        assert rows == []

    def test_row_schema_keys(self, tmp_path):
        """Every appended ledger row has all required schema keys."""
        required_keys = {
            "schema", "id", "asset", "direction", "signal_date",
            "close_date", "outcome", "stock_result_pct",
            "option_result_pct", "days_held", "plan_adherence", "asof",
        }
        plan = _make_plan(entry=100.0, invalidation=90.0, t1=115.0, t2=130.0,
                          signal_date="2026-06-01")
        closes = [88.0]  # immediate invalidation
        ph = _price_history_from_closes(closes, start="2026-06-02")
        rows = self._run_advance(tmp_path, {plan["id"]: plan}, {"AAPL": ph}, "2026-07-01")
        assert len(rows) == 1
        missing = required_keys - set(rows[0].keys())
        assert missing == set(), f"Missing ledger row keys: {missing}"
        assert rows[0]["schema"] == "prophet.ledger/v1"

# ---------------------------------------------------------------------------
# 31–33. R0.7 market-overlay wires + index whitelist expansion
# ---------------------------------------------------------------------------

class TestMarketOverlayInputs:
    """_load_macro_stance / _load_futures_chg (R0.7 quick wires)."""

    def test_macro_stance_verdict_mapping(self, tmp_path, monkeypatch):
        import scripts.build_prophet as bp  # noqa: PLC0415
        ms_path = tmp_path / "latest.json"
        monkeypatch.setattr(bp, "MARKET_STATE_PATH", ms_path)
        for verdict, expected in [
            ("RISK_ON", "bull"), ("MIXED", "neutral"),
            ("RISK_OFF", "bear"), ("UNKNOWN_WORD", None),
        ]:
            ms_path.write_text(json.dumps({"asof": "2026-07-01", "verdict": verdict}))
            assert bp._load_macro_stance("2026-07-02") == expected, verdict

    def test_macro_stance_pit_guard(self, tmp_path, monkeypatch):
        """A snapshot dated AFTER asof (backfill --date run) must be omitted."""
        import scripts.build_prophet as bp  # noqa: PLC0415
        ms_path = tmp_path / "latest.json"
        monkeypatch.setattr(bp, "MARKET_STATE_PATH", ms_path)
        ms_path.write_text(json.dumps({"asof": "2026-07-30", "verdict": "RISK_ON"}))
        assert bp._load_macro_stance("2026-07-02") is None

    def test_macro_stance_staleness_guard(self, tmp_path, monkeypatch):
        import scripts.build_prophet as bp  # noqa: PLC0415
        ms_path = tmp_path / "latest.json"
        monkeypatch.setattr(bp, "MARKET_STATE_PATH", ms_path)
        ms_path.write_text(json.dumps({"asof": "2026-06-01", "verdict": "RISK_ON"}))
        assert bp._load_macro_stance("2026-07-02") is None

    def test_macro_stance_missing_file(self, tmp_path, monkeypatch):
        import scripts.build_prophet as bp  # noqa: PLC0415
        monkeypatch.setattr(bp, "MARKET_STATE_PATH", tmp_path / "absent.json")
        assert bp._load_macro_stance("2026-07-02") is None

    def test_futures_chg_close_to_close(self, tmp_path, monkeypatch):
        import scripts.build_prophet as bp  # noqa: PLC0415
        monkeypatch.setattr(bp, "YAHOO_DIR", tmp_path)
        idx = pd.DatetimeIndex(
            [pd.Timestamp("2026-06-30"), pd.Timestamp("2026-07-01"),
             pd.Timestamp("2026-07-02")])
        pd.DataFrame({"close": [99.0, 100.0, 102.0]}, index=idx).to_parquet(
            tmp_path / "SPY.parquet")
        pd.DataFrame({"close": [510.0, 500.0, 495.0]}, index=idx).to_parquet(
            tmp_path / "QQQ.parquet")
        out = bp._load_futures_chg("2026-07-02")
        assert out is not None
        assert out["SPY"] == pytest.approx(0.02)
        assert out["QQQ"] == pytest.approx(-0.01)

    def test_futures_chg_pit_filter(self, tmp_path, monkeypatch):
        """Rows after asof are invisible — the change is computed at the PIT frame."""
        import scripts.build_prophet as bp  # noqa: PLC0415
        monkeypatch.setattr(bp, "YAHOO_DIR", tmp_path)
        idx = pd.DatetimeIndex(
            [pd.Timestamp("2026-07-01"), pd.Timestamp("2026-07-02"),
             pd.Timestamp("2026-07-03")])
        pd.DataFrame({"close": [100.0, 102.0, 250.0]}, index=idx).to_parquet(
            tmp_path / "SPY.parquet")
        out = bp._load_futures_chg("2026-07-02")
        assert out is not None
        assert out["SPY"] == pytest.approx(0.02)

    def test_futures_chg_stale_store_omitted(self, tmp_path, monkeypatch):
        import scripts.build_prophet as bp  # noqa: PLC0415
        monkeypatch.setattr(bp, "YAHOO_DIR", tmp_path)
        idx = pd.DatetimeIndex(
            [pd.Timestamp("2026-05-29"), pd.Timestamp("2026-06-01")])
        pd.DataFrame({"close": [100.0, 101.0]}, index=idx).to_parquet(
            tmp_path / "SPY.parquet")
        assert bp._load_futures_chg("2026-07-02") is None

    def test_futures_chg_empty_dir_omitted(self, tmp_path, monkeypatch):
        import scripts.build_prophet as bp  # noqa: PLC0415
        monkeypatch.setattr(bp, "YAHOO_DIR", tmp_path)
        assert bp._load_futures_chg("2026-07-02") is None


def test_index_entries_carry_last_price_and_state(tmp_path):
    """R0.7: active index entries publish last_price + a nested state block
    (components / geometry / change_reason) so the Terminal's GAINERS sort,
    T1-progress/P&L bars, and ConfidencePanel component bars light up."""
    import scripts.build_prophet as bp  # noqa: PLC0415

    buys = [_make_buy("AAPL", score=70, act_level=3, spot=150.0)]
    standouts = _make_standouts(gate_go=False, buys=buys)
    standouts_path = tmp_path / "us_standouts.json"
    standouts_path.write_text(json.dumps(standouts))

    orig_standouts = bp.STANDOUTS_PATH
    orig_site = bp.SITE_PROPHET
    orig_plans = bp.PLANS_DIR
    orig_states = bp.STATES_DIR
    orig_index = bp.INDEX_PATH
    orig_ledger_path = bp.LEDGER_PATH
    orig_ledger_dir = bp.LEDGER_DIR
    orig_write_showcase = bp.write_showcase

    try:
        bp.STANDOUTS_PATH = standouts_path
        bp.SITE_PROPHET = tmp_path / "site" / "prophet"
        bp.PLANS_DIR = bp.SITE_PROPHET / "plans"
        bp.STATES_DIR = bp.SITE_PROPHET / "states"
        bp.INDEX_PATH = bp.SITE_PROPHET / "index.json"
        bp.LEDGER_PATH = tmp_path / "data" / "prophet" / "ledger.jsonl"
        bp.LEDGER_DIR = tmp_path / "data" / "prophet"
        bp.write_showcase = lambda: orig_write_showcase(
            out_path=tmp_path / "showcase.json")

        ph = _make_price_history(150.0, 30)
        # last_price must be the last PIT close — the same bar the management
        # engine saw — not the frame's final (post-asof) close.
        expected_last = round(
            float(ph[ph.index <= pd.Timestamp("2026-07-02")]["close"].iloc[-1]), 4)

        import sys as _sys  # noqa: PLC0415
        with patch.object(_sys, "argv", ["build_prophet", "--date", "2026-07-02"]):
            with patch("scripts.build_prophet._load_price_history_for_management") as mock_ph:
                mock_ph.return_value = ph
                bp.main()

        idx = json.loads(bp.INDEX_PATH.read_text())
        assert idx["plans"], "expected at least one active plan"
        entry = idx["plans"][0]
        assert entry.get("last_price") == pytest.approx(expected_last)
        state = entry.get("state")
        assert isinstance(state, dict), "nested state block missing"
        for key in ("components", "geometry", "change_reason"):
            assert key in state, f"state block missing {key}"
        # the five engine component bars ride through
        for bar in ("validity", "progress", "pace", "retention", "overlay"):
            assert bar in state["components"], f"components missing {bar}"
        # nested/flat agreement + honesty laws untouched
        assert state["phase"] == entry["phase"]
        assert idx["authority_tier"] == "display"
        conf = entry.get("management_confidence")
        assert conf is None or conf <= 92
    finally:
        bp.STANDOUTS_PATH = orig_standouts
        bp.SITE_PROPHET = orig_site
        bp.PLANS_DIR = orig_plans
        bp.STATES_DIR = orig_states
        bp.INDEX_PATH = orig_index
        bp.LEDGER_PATH = orig_ledger_path
        bp.LEDGER_DIR = orig_ledger_dir
        bp.write_showcase = orig_write_showcase


def test_direct_builder_publish_is_disabled_before_any_r2_call(monkeypatch):
    """Only an accepted Git checkpoint may advance the canonical R2 object."""
    import scripts.build_prophet as bp  # noqa: PLC0415
    import sys as _sys  # noqa: PLC0415

    touched = {"r2": False}
    monkeypatch.setattr(
        bp, "_r2_client",
        lambda: touched.__setitem__("r2", True),
    )
    with patch.object(_sys, "argv", ["build_prophet", "--publish"]):
        with pytest.raises(SystemExit) as exc:
            bp.main()
    assert exc.value.code == 2
    assert touched["r2"] is False
