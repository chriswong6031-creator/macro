"""Tests for the W4 staged auto re-entry (engine/btc_overrides.py) — masterplan
N5 as REDESIGNED after the W1 trigger eval (research/BTC_REENTRY_TRIGGER_EVAL.md
failed all evidence triggers → the calendar spine holds authority; evidence only
ACCELERATES fills).

Covers: the schedule spine replacing the election-day release, accelerator pulls
(fresh MVRV-Z<0 / fresh BP>=0.45 crosses), the owner halt switch, Class-1
composition (both orderings, not haltable), legacy fallback, the re-entry event
ledger, DAT staleness, gate_state W4-awareness, and — when the local stores are
present — the 2018-12 / 2022-11 replay acceptance plus the 2026 dry-run arming.

Run: python -m pytest tests/test_btc_reentry.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import btc_overrides as OV  # noqa: E402

IDX = pd.date_range("2025-01-01", "2027-06-30", freq="D")
TOP = pd.Timestamp("2025-10-06")           # recorded cycle top (config cycle_phase_clock)
WS = pd.Timestamp("2026-10-01")            # TOP + 360d (btc_cycle_thesis.WIN_LEAD_D)
T2D = pd.Timestamp("2026-10-31")           # WS + 30d (schedule_offsets_d)
T3D = pd.Timestamp("2026-11-30")           # WS + 60d
WE = pd.Timestamp("2026-12-10")            # TOP + 430d (WIN_TRAIL_D)
ELECTION = pd.Timestamp("2026-11-03")      # 2026 US midterm election day


def _pure(idx=IDX) -> pd.DataFrame:
    return pd.DataFrame({"alloc_optimal": 1.0}, index=idx)


def _declining_close(idx=IDX) -> pd.Series:
    """Peaks 126k at TOP then grinds down — never prints a new ATH."""
    up = np.linspace(60_000, 126_000, (TOP - idx[0]).days + 1)
    down = np.linspace(126_000, 50_000, len(idx) - len(up))
    return pd.Series(np.concatenate([up, down]), index=idx)


def _registry(class1: bool = True, reentry: bool = True) -> list:
    rules = []
    if class1:
        rules.append({"kind": "structural_invalidation", "signal": "new_ath_close",
                      "confirm_days": 5})
    if reentry:
        rules.append({"kind": "staged_reentry",
                      "params_ref": "vector.allocation.midterm_gate.reentry"})
    return [{"id": "midterm_blackout", "dof_cost": 6, "release_rules": rules}]


def _cfg(halt_from=None, accel=True, tranches=(0.40, 0.30, 0.30)) -> dict:
    return {"midterm_gate": {
        "enabled": True, "buy_lead_days": 0,
        "reentry": {
            "enabled": True,
            "tranches": list(tranches),
            "schedule_offsets_d": [0, 30, 60],
            "halt_from": halt_from,
            "ledger_from": "2026-01-01",
            "accelerator": {
                "enabled": accel,
                "mvrv_z_fresh_cross": {"level": 0.0, "min_days_above": 90},
                "bottom_pressure_fresh_cross": {"level": 0.45, "min_days_below": 20},
            },
        },
    }}


def _ctx(close, mvrv_z=None, bp=None, tops=(TOP,), overrides=None) -> dict:
    return {"close": close, "mvrv_z": mvrv_z, "bottom_pressure": bp,
            "overrides": _registry() if overrides is None else overrides,
            "vector_cfg": {"cycle_phase_clock": {"tops": [str(t)[:10] for t in tops]}}}


def _mvrv(neg_from: str | None, idx=IDX) -> pd.Series:
    """>= 0 everywhere, printing < 0 from `neg_from` (a fresh cross by
    construction — >= 90 prior days at 1.0)."""
    z = pd.Series(1.0, index=idx)
    if neg_from:
        z.loc[pd.Timestamp(neg_from):] = -0.5
    return z


def _bp(cross_at: str | None, idx=IDX) -> pd.Series:
    """Below 0.45 everywhere, crossing to 0.9 from `cross_at` (fresh by
    construction — >= 20 prior days below)."""
    b = pd.Series(0.10, index=idx)
    if cross_at:
        b.loc[pd.Timestamp(cross_at):] = 0.90
    return b


# --------------------------------------------------------------------------- #
# 1. the calendar spine replaces the election-day release
# --------------------------------------------------------------------------- #
def test_schedule_spine_replaces_election_release() -> None:
    """No accelerator evidence → tranches fill EXACTLY on schedule (window open,
    +30d, +60d); the gate holds partial THROUGH election day."""
    res = OV.apply(_pure(), _cfg(), ctx=_ctx(_declining_close()))
    frac = res["override_release_frac"]

    assert frac.loc["2026-06-01"] == 0.0
    assert frac.loc[WS - pd.Timedelta(days=1)] == 0.0
    assert frac.loc[WS] == pytest.approx(0.40), "T1 must fill at window open"
    assert frac.loc[T2D] == pytest.approx(0.70), "T2 must fill at +30d"
    # the old mechanism fully released here; W4 must still be partial
    assert frac.loc[ELECTION + pd.Timedelta(days=1)] == pytest.approx(0.70), \
        "election day must no longer fully release the gate"
    assert frac.loc[T3D] == 1.0, "T3 must complete the release at +60d"
    assert res.loc[WS, "reentry_trigger"] == "t1:schedule"
    assert res.loc[T2D, "reentry_trigger"] == "t2:schedule"
    assert res.loc[T3D, "reentry_trigger"] == "t3:schedule"
    # sizing against RAW: final = raw × frac on partial bars, raw after
    assert res.loc[T2D, "alloc_optimal"] == pytest.approx(0.70)
    assert (res.loc[T3D:, "alloc_optimal"] == res.loc[T3D:, "alloc_optimal_raw"]).all()
    assert (res.loc["2026-01-01":WS - pd.Timedelta(days=1), "alloc_optimal"] == 0).all()
    # active semantics: partial fills stay active; released after T3
    assert res.loc[ELECTION, "override_active"] == 1
    assert res.loc[ELECTION, "override_id"] == "midterm_blackout"
    assert res.loc[T3D, "override_active"] == 0
    # non-midterm years untouched
    assert (res.loc["2025", "override_release_frac"] == 1.0).all()
    assert not res.loc["2025", "override_active"].astype(bool).any()
    assert (res.loc["2027-01-01":, "override_release_frac"] == 1.0).all()


# --------------------------------------------------------------------------- #
# 2. evidence accelerators pull scheduled fills EARLIER (never block)
# --------------------------------------------------------------------------- #
def test_accel_mvrv_fresh_cross_pulls_next_tranche() -> None:
    d = pd.Timestamp("2026-10-15")
    res = OV.apply(_pure(), _cfg(),
                   ctx=_ctx(_declining_close(), mvrv_z=_mvrv("2026-10-15")))
    frac = res["override_release_frac"]
    assert frac.loc[WS] == pytest.approx(0.40)
    assert frac.loc[d] == pytest.approx(0.70), "fresh MVRV cross must pull T2 forward"
    assert res.loc[d, "reentry_trigger"] == "t2:accel_mvrv_z_lt0"
    assert frac.loc[T2D] == pytest.approx(0.70), "T2 already filled — no double fill"
    assert frac.loc[T3D] == 1.0, "T3 stays on schedule (one event = one pull)"


def test_accel_bp_fresh_cross_pulls_next_tranche() -> None:
    d = pd.Timestamp("2026-11-05")
    res = OV.apply(_pure(), _cfg(),
                   ctx=_ctx(_declining_close(), bp=_bp("2026-11-05")))
    frac = res["override_release_frac"]
    assert frac.loc[T2D] == pytest.approx(0.70)  # T2 filled on schedule (event later)
    assert frac.loc[d] == 1.0, "BP cross after T2 must pull T3 forward"
    assert res.loc[d, "reentry_trigger"] == "t3:accel_bottom_pressure"


def test_two_events_pull_successive_tranches() -> None:
    res = OV.apply(_pure(), _cfg(),
                   ctx=_ctx(_declining_close(), mvrv_z=_mvrv("2026-10-10"),
                            bp=_bp("2026-10-12")))
    frac = res["override_release_frac"]
    assert frac.loc[pd.Timestamp("2026-10-10")] == pytest.approx(0.70)
    assert frac.loc[pd.Timestamp("2026-10-12")] == 1.0, \
        "second fresh event must pull T3 too — fully invested before election day"
    assert res.loc[pd.Timestamp("2026-10-12"), "reentry_trigger"] == \
        "t3:accel_bottom_pressure"


def test_stale_pre_window_evidence_never_pulls() -> None:
    """MVRV-Z crossing < 0 BEFORE the window (D5 territory: owner alert only)
    must not accelerate anything — the spine fills on pure schedule."""
    res = OV.apply(_pure(), _cfg(),
                   ctx=_ctx(_declining_close(), mvrv_z=_mvrv("2026-08-01")))
    frac = res["override_release_frac"]
    assert frac.loc[WS] == pytest.approx(0.40)
    assert frac.loc[T2D - pd.Timedelta(days=1)] == pytest.approx(0.40), \
        "no in-window fresh cross → no pull"
    assert frac.loc[T2D] == pytest.approx(0.70)
    assert frac.loc[T3D] == 1.0


def test_accelerator_disabled_pure_schedule() -> None:
    res = OV.apply(_pure(), _cfg(accel=False),
                   ctx=_ctx(_declining_close(), mvrv_z=_mvrv("2026-10-15"),
                            bp=_bp("2026-10-16")))
    fills = res.loc[res["reentry_trigger"] != ""]
    assert list(fills.index) == [WS, T2D, T3D]
    assert all(":schedule" in t for t in fills["reentry_trigger"])


# --------------------------------------------------------------------------- #
# 3. owner halt switch (freezes spine + accelerators; NOT Class-1)
# --------------------------------------------------------------------------- #
def test_halt_freezes_future_fills() -> None:
    res = OV.apply(_pure(), _cfg(halt_from="2026-10-20"),
                   ctx=_ctx(_declining_close(), bp=_bp("2026-11-05")))
    frac = res["override_release_frac"]
    assert frac.loc[WS] == pytest.approx(0.40), "T1 (pre-halt) stays filled"
    frozen = frac.loc["2026-10-20":"2027-06-30"]
    assert frozen.sub(0.40).abs().lt(1e-12).all(), \
        "halt must freeze the schedule AND the accelerator pulls"


def test_halt_before_window_freezes_everything() -> None:
    res = OV.apply(_pure(), _cfg(halt_from="2026-09-01"),
                   ctx=_ctx(_declining_close()))
    assert (res.loc["2026-01-01":"2027-06-30", "override_release_frac"] == 0.0).all()


def _ath_breakout_close(breakout: str, n_days: int = 5, idx=IDX) -> pd.Series:
    """Declining path that breaks to a NEW ATH for n_days consecutive closes."""
    c = _declining_close(idx)
    d = pd.Timestamp(breakout)
    c.loc[d:d + pd.Timedelta(days=n_days - 1)] = 130_000.0  # prior ATH = 126k
    c.loc[d + pd.Timedelta(days=n_days):] = 124_000.0       # back below afterwards
    return c


def test_class1_not_haltable() -> None:
    """D1 is its own governance instrument — the owner halt must not stop it."""
    res = OV.apply(_pure(), _cfg(halt_from="2026-06-01"),
                   ctx=_ctx(_ath_breakout_close("2026-07-01")))
    confirm = pd.Timestamp("2026-07-05")  # 5th consecutive close above the prior ATH
    assert res.loc[confirm, "override_release_frac"] == 1.0
    assert OV.TOKEN_CLASS1 in res.loc[confirm, "reentry_trigger"]


# --------------------------------------------------------------------------- #
# 4. Class-1 composition — earliest full release wins (both orderings)
# --------------------------------------------------------------------------- #
def test_class1_before_window_wins_ordering_a() -> None:
    res = OV.apply(_pure(), _cfg(), ctx=_ctx(_ath_breakout_close("2026-07-01")))
    frac = res["override_release_frac"]
    confirm = pd.Timestamp("2026-07-05")
    assert frac.loc[confirm - pd.Timedelta(days=1)] == 0.0
    assert frac.loc[confirm] == 1.0
    assert res.loc[confirm, "override_released"] == 1
    later = res.loc[confirm + pd.Timedelta(days=1):, "reentry_trigger"]
    assert (later == "").all(), "class-1 release must moot the whole schedule"
    assert (res.loc[confirm:, "alloc_optimal"]
            == res.loc[confirm:, "alloc_optimal_raw"]).all()


def test_class1_mid_schedule_wins_ordering_b() -> None:
    res = OV.apply(_pure(), _cfg(), ctx=_ctx(_ath_breakout_close("2026-11-10")))
    frac = res["override_release_frac"]
    confirm = pd.Timestamp("2026-11-14")
    assert frac.loc[WS] == pytest.approx(0.40)
    assert frac.loc[T2D] == pytest.approx(0.70)
    assert frac.loc[confirm - pd.Timedelta(days=1)] == pytest.approx(0.70)
    assert frac.loc[confirm] == 1.0, "class-1 confirming before T3 releases everything"
    assert OV.TOKEN_CLASS1 in res.loc[confirm, "reentry_trigger"]
    assert res.loc[T3D, "reentry_trigger"] == "", "mooted T3 must not re-fire"


def test_class1_four_closes_do_not_release() -> None:
    res = OV.apply(_pure(), _cfg(), ctx=_ctx(_ath_breakout_close("2026-07-01", n_days=4)))
    assert (res.loc["2026-07-01":"2026-09-30", "override_release_frac"] == 0.0).all()


# --------------------------------------------------------------------------- #
# 5. fallbacks — bit-parity with the W0/W2 legacy paths
# --------------------------------------------------------------------------- #
def test_legacy_fallback_without_recorded_top() -> None:
    ctx = _ctx(_declining_close(), tops=())
    res = OV.apply(_pure(), _cfg(), ctx=ctx)
    frac = res["override_release_frac"]
    assert frac.loc[ELECTION - pd.Timedelta(days=1)] == 0.0
    assert frac.loc[ELECTION] == 1.0, "no window → legacy election-day release"
    assert (res["reentry_trigger"] == "").all()


def test_no_vector_cfg_reproduces_w2_behavior() -> None:
    ctx = {"close": _declining_close(), "overrides": _registry()}
    res = OV.apply(_pure(), _cfg(), ctx=ctx)
    frac = res["override_release_frac"]
    assert frac.loc[ELECTION - pd.Timedelta(days=1)] == 0.0
    assert frac.loc[ELECTION] == 1.0
    assert set(frac.unique()) <= {0.0, 1.0}, "without vector_cfg the gate stays binary"


def test_undeclared_reentry_rule_stays_legacy() -> None:
    ctx = _ctx(_declining_close(), overrides=_registry(reentry=False))
    res = OV.apply(_pure(), _cfg(), ctx=ctx)
    assert res.loc[ELECTION, "override_release_frac"] == 1.0
    assert res.loc[ELECTION - pd.Timedelta(days=1), "override_release_frac"] == 0.0


# --------------------------------------------------------------------------- #
# 6. re-entry event ledger
# --------------------------------------------------------------------------- #
def _sig_frame() -> pd.DataFrame:
    close = _declining_close()
    mvrv = _mvrv("2026-10-15")
    res = OV.apply(_pure(), _cfg(), ctx=_ctx(close, mvrv_z=mvrv))
    res["close"], res["mvrv_z"], res["bottom_pressure"] = close, mvrv, 0.2
    return res


def _vcfg() -> dict:
    return {"allocation": _cfg(),
            "cycle_phase_clock": {"tops": [str(TOP)[:10]]}}


def test_ledger_events_and_idempotent_sync(tmp_path) -> None:
    sig = _sig_frame()
    events = OV.ledger_events(sig, _vcfg())
    assert len(events) == 3  # T1 schedule + T2 accelerated + T3 schedule
    assert [e["tranche_idx"] for e in events] == [0, 1, 2]
    assert events[0]["trigger"] == "schedule" and events[0]["accelerated"] is False
    assert events[0]["cum_release_frac"] == pytest.approx(0.40)
    assert events[1]["trigger"] == "accel_mvrv_z_lt0" and events[1]["accelerated"]
    assert events[1]["ts"] == "2026-10-15"
    assert events[1]["evidence"]["mvrv_z"] == pytest.approx(-0.5)
    assert events[2]["trigger"] == "schedule"
    assert events[2]["cum_release_frac"] == pytest.approx(1.0)

    path = tmp_path / "reentry_ledger.jsonl"
    assert OV.sync_ledger(sig, _vcfg(), path) == 3
    assert OV.sync_ledger(sig, _vcfg(), path) == 0, "second sync must append nothing"
    rows = [json.loads(x) for x in path.read_text().splitlines()]
    assert len(rows) == 3 and all(r["override_id"] == "midterm_blackout" for r in rows)


# --------------------------------------------------------------------------- #
# 7. owner status + D5 pre-window alert + DAT advisory chip
# --------------------------------------------------------------------------- #
def test_build_status_arming_schedule_and_dat() -> None:
    sig = _sig_frame().loc[:"2026-09-15"]
    dat = {"ok": True, "forced_sell_distance_pct": 42.0, "asof": "2026-06-20",
           "stale": True, "age_days": 30}
    st = OV.build_status(sig, _vcfg(), dat=dat)
    assert st["state"] == "armed_pending_window"
    assert st["window_start"] == "2026-10-01" and st["window_end"] == "2026-12-10"
    assert st["release_frac"] == 0.0
    assert [s["scheduled"] for s in st["schedule"]] == \
        ["2026-10-01", "2026-10-31", "2026-11-30"]
    assert all(s["filled"] is False for s in st["schedule"])
    assert st["accelerator"]["enabled"] is True
    assert st["dat_advisory"]["advisory_only"] is True
    assert st["dat_advisory"]["stale"] is True


def test_build_status_pre_window_mvrv_owner_alert() -> None:
    """D5: a fresh MVRV-Z<0 print BEFORE the window opens = owner alert field
    only — the schedule/frac must be untouched (covered above)."""
    close = _declining_close()
    mvrv = _mvrv("2026-08-01")
    res = OV.apply(_pure(), _cfg(), ctx=_ctx(close, mvrv_z=mvrv))
    res["close"], res["mvrv_z"], res["bottom_pressure"] = close, mvrv, 0.2
    st = OV.build_status(res.loc[:"2026-09-15"], _vcfg())
    assert st["pre_window_mvrv_fire"] == "2026-08-01"


def test_dat_staleness_flag(tmp_path) -> None:
    from engine import btc_dat
    old = {"asof": (pd.Timestamp.now() - pd.Timedelta(days=30)).strftime("%Y-%m-%d"),
           "btc_held": 226500, "shares_out": 263000000, "avg_cost_usd": 36798.0,
           "price_usd": 59000.0}
    p = tmp_path / "dat.json"
    p.write_text(json.dumps(old))
    out = btc_dat.compute(holdings_path=str(p))
    assert out["ok"] and out["stale"] is True and out["age_days"] >= 29
    fresh = {**old, "asof": pd.Timestamp.now().strftime("%Y-%m-%d")}
    p.write_text(json.dumps(fresh))
    out = btc_dat.compute(holdings_path=str(p))
    assert out["ok"] and out["stale"] is False


# --------------------------------------------------------------------------- #
# 8. gate_state (W3's stamped flag) must track the re-entry, not the calendar
# --------------------------------------------------------------------------- #
def test_gate_state_reentry_aware() -> None:
    from engine import btc_signals as S
    cfg = _cfg()["midterm_gate"]
    vcfg = {"cycle_phase_clock": {"tops": [str(TOP)[:10]]}}
    sig = OV.apply(_pure(), {"midterm_gate": cfg}, ctx=_ctx(_declining_close()))

    # sig truth: post-election, T2 filled, T3 pending → STILL active, frac 0.7
    g = S.gate_state("2026-11-15", cfg, sig=sig, vector_cfg=vcfg)
    assert g["active"] is True, "partial fills must keep the stamped gate active"
    assert g["release_frac"] == pytest.approx(0.70)
    assert g["release"] == "2026-10-01" and g["window_end"] == "2026-12-10"

    # sig truth: after T3 → released
    g = S.gate_state("2026-12-01", cfg, sig=sig, vector_cfg=vcfg)
    assert g["active"] is False and g["release_frac"] == pytest.approx(1.0)

    # calendar-only fallback (no sig): conservative through the last scheduled fill
    g = S.gate_state("2026-11-15", cfg, vector_cfg=vcfg)
    assert g["active"] is True, \
        "without sig the flag must stay active past election day (fills unknowable)"
    g = S.gate_state("2026-12-05", cfg, vector_cfg=vcfg)
    assert g["active"] is False

    # legacy cfg without reentry: unchanged W2/W3 behavior
    legacy = {"enabled": True, "buy_lead_days": 0}
    assert S.gate_state("2026-11-03", legacy)["active"] is False
    assert S.gate_state("2026-07-01", legacy)["active"] is True


# --------------------------------------------------------------------------- #
# 9. ACCEPTANCE — historical replays + 2026 dry-run on the real stores
# --------------------------------------------------------------------------- #
_SIG_PATH = Path(__file__).resolve().parent.parent / "data" / "vector" / "signals.parquet"


@pytest.fixture(scope="module")
def real_replay():
    if not _SIG_PATH.exists():
        pytest.skip("local data/vector/signals.parquet not present")
    from lib import config
    sig = pd.read_parquet(_SIG_PATH)
    sig.index = pd.to_datetime(sig.index)
    vcfg = config.load()["vector"]
    acfg = vcfg["allocation"]
    assert acfg.get("midterm_gate", {}).get("reentry", {}).get("enabled"), \
        "live config must ship the W4 re-entry enabled"
    pure = pd.DataFrame({"alloc_optimal": 1.0}, index=sig.index)
    ctx = {"close": sig["close"], "mvrv_z": sig.get("mvrv_z"),
           "bottom_pressure": sig.get("bottom_pressure"),
           "overrides": vcfg.get("overrides"), "vector_cfg": vcfg}
    return OV.apply(pure, acfg, ctx=ctx), vcfg


def test_replay_2018_schedule_fills_inside_window(real_replay) -> None:
    """2017-12-16 top → window 2018-12-11 → 2019-02-19 (bottom printed 2018-12-15).
    No in-window accelerator events (the fresh MVRV cross was 2018-11-19,
    pre-window) → pure schedule: 12-11 / 01-10 / 02-09, all inside the window."""
    res, _ = real_replay
    frac = res["override_release_frac"]
    assert frac.loc[pd.Timestamp("2018-11-07")] == 0.0, \
        "the 2018 election-day release must be replaced by the window spine"
    assert res.loc[pd.Timestamp("2018-12-11"), "reentry_trigger"] == "t1:schedule"
    assert frac.loc[pd.Timestamp("2018-12-11")] == pytest.approx(0.40)
    assert res.loc[pd.Timestamp("2019-01-10"), "reentry_trigger"] == "t2:schedule"
    assert res.loc[pd.Timestamp("2019-02-09"), "reentry_trigger"] == "t3:schedule"
    assert frac.loc[pd.Timestamp("2019-02-09")] == 1.0
    fills = res.loc[(res["reentry_trigger"] != "") &
                    (res.index >= "2018-01-01") & (res.index <= "2019-12-31")]
    ws, we = pd.Timestamp("2018-12-11"), pd.Timestamp("2019-02-19")
    assert ((fills.index >= ws) & (fills.index <= we)).all(), \
        "every 2018-cycle fill must land inside the projected window"


def test_replay_2022_ftx_acceleration(real_replay) -> None:
    """2021-11-08 top → window 2022-11-03 → 2023-01-12 (bottom printed 2022-11-21).
    T1 on schedule at the open; the fresh BP>=0.45 cross on 2022-11-09 — the FTX
    capitulation — pulls T2 forward 24 days; T3 completes on schedule."""
    res, _ = real_replay
    frac = res["override_release_frac"]
    assert res.loc[pd.Timestamp("2022-11-03"), "reentry_trigger"] == "t1:schedule"
    assert frac.loc[pd.Timestamp("2022-11-03")] == pytest.approx(0.40)
    assert res.loc[pd.Timestamp("2022-11-09"), "reentry_trigger"] == \
        "t2:accel_bottom_pressure", "the FTX washout must accelerate T2"
    assert frac.loc[pd.Timestamp("2022-11-09")] == pytest.approx(0.70)
    assert res.loc[pd.Timestamp("2023-01-02"), "reentry_trigger"] == "t3:schedule"
    assert frac.loc[pd.Timestamp("2023-01-02")] == 1.0
    fills = res.loc[(res["reentry_trigger"] != "") &
                    (res.index >= "2022-01-01") & (res.index <= "2023-12-31")]
    ws, we = pd.Timestamp("2022-11-03"), pd.Timestamp("2023-01-12")
    assert ((fills.index >= ws) & (fills.index <= we)).all()


def test_replay_2014_uses_legacy_release(real_replay) -> None:
    """No recorded top precedes 2014 → legacy election-day release. Skipped when
    the store's history starts after 2014 (the synthetic
    test_legacy_fallback_without_recorded_top covers the same path)."""
    res, _ = real_replay
    frac = res["override_release_frac"]
    e14 = pd.Timestamp("2014-11-04")
    y2014 = frac.loc["2014-01-01":"2014-12-31"]
    if y2014.empty:
        pytest.skip("signals store history starts after 2014")
    assert (y2014[y2014.index < e14] == 0.0).all()
    assert (y2014[y2014.index >= e14] == 1.0).all(), \
        "no recorded top before 2014 → legacy election-day release"


def test_2026_dry_run_arms_correctly(real_replay) -> None:
    res, vcfg = real_replay
    last = res.index[-1]
    assert pd.Timestamp("2026-07-01") <= last < pd.Timestamp("2026-10-01"), \
        "dry-run assertion is written for the pre-window period"
    assert res.loc[last, "override_release_frac"] == 0.0
    assert res.loc[last, "override_active"] == 1
    assert (res.loc["2026-01-01":last, "reentry_trigger"] == "").all()
    st = OV.build_status(res, vcfg)
    assert st["state"] == "armed_pending_window"
    assert st["window_start"] == "2026-10-01" and st["window_end"] == "2026-12-10"
    assert [s["scheduled"] for s in st["schedule"]] == \
        ["2026-10-01", "2026-10-31", "2026-11-30"]
    assert st["enabled"] is True and st["halt_from"] is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
