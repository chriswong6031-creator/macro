"""Tests for engine/us_basket_turn.py — W1-D US washout-lifecycle organ.

Covers:
  (1)  Full lifecycle walk on a FROZEN synthetic series: the ordered sequence
       WASHED_OUT -> TURNING -> CONFIRMED, chained exactly as the nightly chains it.
  (2)  CONFIRMED needs CONFIRMED_MIN_DAYS consecutive TURNING sessions.
  (3)  CONFIRMED is blocked while slope_20d < 0 — a 14-session TURNING run on the
       same fixture never confirms.
  (4)  Non-firing controls: a healthy uptrend and a shallow (-12%) pullback never
       enter the lifecycle at all.
  (5)  FALLING vetoes everything, including a fresh up-tick inside a collapse.
  (6)  PIT dated membership: a member added mid-series contributes nothing before
       its `added` date.
  (7)  The >= 3 readable-member floor: two members yield NO level series.
  (8)  Coverage disclosure (W-B law): a basket whose members are half-missing
       emits a bare `::warning` at column 0 and the organ STILL classifies it.
  (9)  Ledger lane gate (COLLECT_LANE=nightly), keep-first idempotency, and the
       data-plane session stamp (a frozen store re-derives its own session).
  (10) Prior ledger state drives CONFIRMED hysteresis across sessions.
  (11) Authority block is display-tier with every may_* false, and the module
       imports no scoring/board surface (zero authority wiring).
  (12) Disclosure cites DNR:KILL-WASHOUT-TURN, carries the "not a bottom call"
       sentence, and never uses the CI-guarded word "validated".
  (13) Thresholds are pinned to their frozen v1 literals.

Frozen-fixture law: every state assertion here runs on a synthetic series built
in-test. NOTHING in this file reads the live member store — a replay over live
data asserts about TODAY, and would rot the day the tape moves. The CN-parity
replay over the real US miner tape is PR-body evidence, not a test assertion.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine import us_basket_turn as UBT


# ---------------------------------------------------------------------------
# Fixture builders (frozen — no live store, no clock)
# ---------------------------------------------------------------------------

_FIXTURE_END = "2026-08-06"


def _levels(vals: list[float], end: str = _FIXTURE_END) -> pd.Series:
    idx = pd.date_range(end=end, periods=len(vals), freq="B")
    return pd.Series(vals, index=idx, dtype=float)


def _flat(v: float, n: int) -> list[float]:
    return [v] * n


def _ramp(a: float, b: float, n: int) -> list[float]:
    return list(np.linspace(a, b, n))


def _compound(start: float, r: float, n: int) -> list[float]:
    return [start * (1 + r) ** i for i in range(n)]


def _walk(series: pd.Series) -> list[dict]:
    """Session-by-session classification with prev_state/days chained as nightly does."""
    prev: str | None = None
    days = 0
    out: list[dict] = []
    for i in range(len(series)):
        r = UBT.classify_basket(series.iloc[: i + 1], prev_state=prev, days_in_state=days)
        out.append({"date": series.index[i], **r})
        prev, days = r["state"], r["days_in_state"]
    return out


# The canonical washout fixture: 120 sessions at the peak, a 240-session grind to
# -40%, a 25-session base, then a 25-session lift off the base.
_WASHOUT_VALS = (
    _flat(1.0, 120) + _ramp(1.0, 0.60, 240) + _flat(0.60, 25) + _ramp(0.60, 0.70, 25)
)


# ---------------------------------------------------------------------------
# (1) Full lifecycle walk
# ---------------------------------------------------------------------------

def test_lifecycle_walk_washout_to_turning_to_confirmed():
    states = [r["state"] for r in _walk(_levels(_WASHOUT_VALS))]

    assert "WASHED_OUT" in states, f"no WASHED_OUT in walk: {sorted(set(states))}"
    assert "TURNING" in states, f"no TURNING in walk: {sorted(set(states))}"
    assert "CONFIRMED" in states, f"no CONFIRMED in walk: {sorted(set(states))}"

    first_washed = states.index("WASHED_OUT")
    first_turning = states.index("TURNING")
    first_confirmed = states.index("CONFIRMED")

    assert first_washed < first_turning < first_confirmed, (
        "lifecycle order violated: "
        f"WASHED_OUT@{first_washed} TURNING@{first_turning} CONFIRMED@{first_confirmed}"
    )
    # The basket ends in the recovery leg, not in collapse.
    assert states[-1] == "CONFIRMED"


def test_lifecycle_depth_and_evidence_are_descriptive():
    walk = _walk(_levels(_WASHOUT_VALS))
    confirmed = [r for r in walk if r["state"] == "CONFIRMED"][0]
    assert confirmed["dd_252"] is not None
    assert confirmed["dd_252"] <= UBT.WASHOUT_DD_THRESH
    assert confirmed["slope_20d"] >= UBT.CONFIRMED_SLOPE_MIN
    # Evidence tags are descriptive: no forward verbs, no buy vocabulary.
    blob = " ".join(confirmed["evidence"]).lower()
    for banned in ("buy", "enter", "will ", "should", "target"):
        assert banned not in blob, f"forward/buy verb {banned!r} in evidence: {blob}"


# ---------------------------------------------------------------------------
# (2) CONFIRMED needs CONFIRMED_MIN_DAYS consecutive TURNING sessions
# ---------------------------------------------------------------------------

def test_confirmed_requires_min_days_in_turning():
    walk = _walk(_levels(_WASHOUT_VALS))
    idx = [i for i, r in enumerate(walk) if r["state"] == "CONFIRMED"][0]
    assert walk[idx]["days_in_state"] >= UBT.CONFIRMED_MIN_DAYS

    # The CONFIRMED_MIN_DAYS - 1 sessions immediately before it were TURNING.
    for back in range(1, UBT.CONFIRMED_MIN_DAYS):
        assert walk[idx - back]["state"] == "TURNING", (
            f"session -{back} before CONFIRMED was {walk[idx - back]['state']}"
        )


def test_confirmed_resets_when_prev_state_is_none():
    """A cold ledger cannot short-circuit the hysteresis into CONFIRMED."""
    lvl = _levels(_WASHOUT_VALS)
    cold = UBT.classify_basket(lvl, prev_state=None, days_in_state=0)
    assert cold["state"] == "TURNING"
    assert cold["days_in_state"] == 1


# ---------------------------------------------------------------------------
# (3) The slope gate blocks CONFIRMED while the 20d slope is still negative
# ---------------------------------------------------------------------------

def test_turning_run_does_not_confirm_while_slope_negative():
    walk = _walk(_levels(_WASHOUT_VALS))
    first_confirmed = [i for i, r in enumerate(walk) if r["state"] == "CONFIRMED"][0]

    long_negative_run = [
        r for r in walk[:first_confirmed]
        if r["state"] == "TURNING"
        and r["days_in_state"] >= UBT.CONFIRMED_MIN_DAYS
    ]
    assert long_negative_run, (
        "fixture no longer exercises the slope gate — expected a TURNING run of at "
        "least CONFIRMED_MIN_DAYS sessions before the first CONFIRMED"
    )
    for r in long_negative_run:
        assert r["slope_20d"] < UBT.CONFIRMED_SLOPE_MIN, (
            f"{r['date'].date()} held TURNING at days={r['days_in_state']} with "
            f"slope_20d={r['slope_20d']} >= {UBT.CONFIRMED_SLOPE_MIN} — should have confirmed"
        )


# ---------------------------------------------------------------------------
# (4) Non-firing controls
# ---------------------------------------------------------------------------

_LIFECYCLE_STATES = {"BASING", "WASHED_OUT", "TURNING", "CONFIRMED"}


def test_control_healthy_uptrend_never_enters_lifecycle():
    states = {r["state"] for r in _walk(_levels(_compound(1.0, 0.0015, 400)))}
    assert states == {"NONE"}, f"healthy uptrend produced {sorted(states)}"


def test_control_shallow_pullback_never_enters_lifecycle():
    """A -12% pullback is not a washout: depth never reaches WASHOUT_DD_THRESH."""
    base = _compound(1.0, 0.001, 300)
    vals = base + _ramp(base[-1], base[-1] * 0.88, 60)
    walk = _walk(_levels(vals))
    states = {r["state"] for r in walk}
    assert not (states & _LIFECYCLE_STATES), (
        f"shallow pullback entered the lifecycle: {sorted(states & _LIFECYCLE_STATES)}"
    )
    worst = min(r["dd_252"] for r in walk if r["dd_252"] is not None)
    assert worst > UBT.WASHOUT_DD_THRESH, f"control fixture drew down {worst}"


# ---------------------------------------------------------------------------
# (5) FALLING vetoes everything
# ---------------------------------------------------------------------------

def test_falling_vetoes_uptick_inside_a_collapse():
    """A fresh +10% day inside an active collapse is still FALLING."""
    vals = _flat(1.0, 120) + _ramp(1.0, 0.70, 200) + _compound(0.70, -0.05, 8)
    vals = vals + [vals[-1] * 1.10]
    r = UBT.classify_basket(_levels(vals))
    assert r["state"] == "FALLING", f"got {r['state']} ret_5d={r['ret_5d']}"
    assert r["ret_5d"] <= UBT.FALLING_RET_THRESH


def test_insufficient_history_returns_none_with_tag():
    r = UBT.classify_basket(_levels(_flat(1.0, 20)))
    assert r["state"] == "NONE"
    assert any("insufficient" in e for e in r["evidence"])


# ---------------------------------------------------------------------------
# (6)/(7) EW level construction — PIT membership + the >= 3 member floor
# ---------------------------------------------------------------------------

def _close_series(vals: list[float], end: str = _FIXTURE_END) -> pd.Series:
    return _levels(vals, end=end)


def test_ew_level_honours_point_in_time_added_date():
    """A member counts only from its `added` date — never before."""
    idx_end = _FIXTURE_END
    a = _close_series(_flat(100.0, 60), idx_end)
    b = _close_series(_flat(50.0, 60), idx_end)
    # c doubles on its very first session; if PIT is ignored that shock leaks in early.
    c_vals = _flat(10.0, 59) + [20.0]
    c = _close_series(c_vals, idx_end)
    closes = {"A": a, "B": b, "C": c}

    late_add = str(c.index[-1].date())
    members_late = [
        {"ticker": "A", "added": str(a.index[0].date())},
        {"ticker": "B", "added": str(b.index[0].date())},
        {"ticker": "C", "added": late_add},
    ]
    members_early = [
        {"ticker": "A", "added": str(a.index[0].date())},
        {"ticker": "B", "added": str(b.index[0].date())},
        {"ticker": "C", "added": str(c.index[0].date())},
    ]

    lvl_late = UBT.ew_level_from_closes(members_late, closes)
    lvl_early = UBT.ew_level_from_closes(members_early, closes)

    # A and B are flat, so a PIT-correct basket is flat until C is admitted.
    assert lvl_late.iloc[-2] == pytest.approx(1.0)
    # On the admission session C's +100% enters the EW mean (1/3 weight).
    assert lvl_late.iloc[-1] > lvl_late.iloc[-2]
    assert lvl_early.iloc[-1] == pytest.approx(lvl_late.iloc[-1])
    # ...and the shock is the ONLY difference — before it, both are flat.
    assert lvl_early.iloc[-2] == pytest.approx(lvl_late.iloc[-2])


def test_ew_level_requires_three_readable_members():
    closes = {
        "A": _close_series(_flat(100.0, 60)),
        "B": _close_series(_flat(50.0, 60)),
    }
    members = [
        {"ticker": "A", "added": "2020-01-01"},
        {"ticker": "B", "added": "2020-01-01"},
        {"ticker": "C", "added": "2020-01-01"},  # unreadable
    ]
    assert UBT.ew_level_from_closes(members, closes).empty
    assert UBT.MIN_MEMBERS_FOR_LEVEL == 3


# ---------------------------------------------------------------------------
# Synthetic data_root helpers for compute_all / ledger tests
# ---------------------------------------------------------------------------

def _write_store(root: Path, ticker: str, vals: list[float], end: str = _FIXTURE_END) -> None:
    d = root / "stocks"
    d.mkdir(parents=True, exist_ok=True)
    s = _close_series(vals, end)
    pd.DataFrame({"close": s.values}, index=s.index).to_parquet(d / f"{ticker}.parquet")


def _write_membership(root: Path, baskets: dict[str, list[str]],
                      added: str = "2020-01-01") -> None:
    d = root / "baskets"
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "baskets": {
            bid: {"members": [{"ticker": t, "added": added, "removed": None} for t in tks]}
            for bid, tks in baskets.items()
        }
    }
    (d / "membership.json").write_text(json.dumps(payload))


def _thin_universe(root: Path) -> None:
    """One well-covered basket + one basket whose members are half-missing."""
    for tk in ("AAA", "BBB", "CCC", "DDD"):
        _write_store(root, tk, _WASHOUT_VALS)
    # thin_basket declares 6 members; only 3 have a store file.
    _write_membership(root, {
        "covered_basket": ["AAA", "BBB", "CCC", "DDD"],
        "thin_basket": ["AAA", "BBB", "CCC", "MISS1", "MISS2", "MISS3"],
        "cn_should_be_filtered": ["AAA", "BBB", "CCC"],
    })


# ---------------------------------------------------------------------------
# (8) Coverage disclosure — the hole is PRINTED, and the organ still runs
# ---------------------------------------------------------------------------

def test_missing_member_prices_print_a_coverage_line_and_engine_still_runs(
    tmp_path, capsys
):
    _thin_universe(tmp_path)
    art = UBT.compute_all(data_root=tmp_path)

    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if "us-basket-turn-coverage" in ln]
    assert lines, f"no coverage annotation printed; stdout was:\n{out}"

    # GitHub only parses a workflow command when '::' STARTS the line — a logger
    # would prefix it (tests/test_gh_annotation_line_start.py).
    for ln in lines:
        assert ln.startswith("::"), f"annotation not at column 0: {ln!r}"
    assert any("thin_basket reads 3/6 members" in ln for ln in lines)

    # ...and the engine did NOT skip the thin basket: it still carries a state and
    # its coverage counts, because a printed hole is disclosure, not a gate.
    thin = art["baskets"]["thin_basket"]
    assert thin["members_read"] == 3
    assert thin["members_total"] == 6
    assert thin["state"] in {
        "NONE", "FALLING", "BASING", "WASHED_OUT", "TURNING", "CONFIRMED"
    }
    assert "thin_basket" in art["coverage"]["baskets_below_warn"]

    # A fully covered basket prints nothing and is not listed as a hole.
    assert art["baskets"]["covered_basket"]["members_read"] == 4
    assert "covered_basket" not in art["coverage"]["baskets_below_warn"]


def test_non_us_baskets_are_filtered_out(tmp_path):
    _thin_universe(tmp_path)
    art = UBT.compute_all(data_root=tmp_path)
    assert "cn_should_be_filtered" not in art["baskets"]
    assert set(art["baskets"]) == {"covered_basket", "thin_basket"}


def test_basket_below_member_floor_returns_none_with_tag(tmp_path):
    for tk in ("AAA", "BBB"):
        _write_store(tmp_path, tk, _WASHOUT_VALS)
    _write_membership(tmp_path, {"tiny": ["AAA", "BBB", "CCC", "DDD"]})
    art = UBT.compute_all(data_root=tmp_path)
    row = art["baskets"]["tiny"]
    assert row["state"] == "NONE"
    assert any("insufficient_members" in e for e in row["evidence"])
    assert row["members_read"] == 2


# ---------------------------------------------------------------------------
# (9) Ledger: lane gate, idempotency, data-plane stamp
# ---------------------------------------------------------------------------

def test_ledger_does_not_append_without_the_nightly_lane(tmp_path, monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    _thin_universe(tmp_path)
    art = UBT.compute_all(data_root=tmp_path)
    assert UBT.append_ledger(art, tmp_path) == 0
    assert not (tmp_path / "us_basket_turn" / "ledger.jsonl").exists()


def test_ledger_appends_on_the_nightly_lane(tmp_path, monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    _thin_universe(tmp_path)
    art = UBT.compute_all(data_root=tmp_path)
    n = UBT.append_ledger(art, tmp_path)
    assert n == len(art["baskets"]) == 2

    rows = [json.loads(ln) for ln in
            (tmp_path / "us_basket_turn" / "ledger.jsonl").read_text().splitlines() if ln.strip()]
    assert {r["basket_id"] for r in rows} == {"covered_basket", "thin_basket"}
    for r in rows:
        assert r["date"] == art["data_session"]
        assert r["as_of"] == art["data_session"]
        assert "state" in r and "dd_252" in r and "days_in_state" in r
        assert r["members_total"] >= r["members_read"]


def test_ledger_is_keep_first_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    _thin_universe(tmp_path)
    art = UBT.compute_all(data_root=tmp_path)
    first = UBT.append_ledger(art, tmp_path)
    second = UBT.append_ledger(art, tmp_path)
    assert first > 0
    assert second == 0, "re-run appended duplicate rows for the same (date, basket_id)"


def test_ledger_stamp_comes_from_the_data_plane_not_the_wall_clock(tmp_path, monkeypatch):
    """A frozen store re-derives the session it already logged (#4568 pattern)."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    frozen_end = "2026-07-31"
    for tk in ("AAA", "BBB", "CCC"):
        _write_store(tmp_path, tk, _WASHOUT_VALS, end=frozen_end)
    _write_membership(tmp_path, {"frozen": ["AAA", "BBB", "CCC"]})

    art = UBT.compute_all(data_root=tmp_path)
    assert art["data_session"] == frozen_end
    assert art["as_of"] == frozen_end

    assert UBT.append_ledger(art, tmp_path) == 1
    # Second nightly, same frozen store: the stamp is re-derived, not advanced.
    art2 = UBT.compute_all(data_root=tmp_path)
    assert art2["data_session"] == frozen_end
    assert UBT.append_ledger(art2, tmp_path) == 0


# ---------------------------------------------------------------------------
# (10) Prior ledger state drives the CONFIRMED hysteresis
# ---------------------------------------------------------------------------

def test_prior_ledger_state_carries_days_in_state_forward(tmp_path, monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    for tk in ("AAA", "BBB", "CCC"):
        _write_store(tmp_path, tk, _WASHOUT_VALS)
    _write_membership(tmp_path, {"b1": ["AAA", "BBB", "CCC"]})

    cold = UBT.compute_all(data_root=tmp_path)
    assert cold["baskets"]["b1"]["state"] == "TURNING"
    assert cold["baskets"]["b1"]["days_in_state"] == 1

    # Seed a prior session that already held TURNING for CONFIRMED_MIN_DAYS - 1.
    lp = tmp_path / "us_basket_turn" / "ledger.jsonl"
    lp.parent.mkdir(parents=True, exist_ok=True)
    lp.write_text(json.dumps({
        "date": "2026-08-05", "basket_id": "b1", "state": "TURNING",
        "days_in_state": UBT.CONFIRMED_MIN_DAYS - 1,
    }) + "\n")

    warm = UBT.compute_all(data_root=tmp_path)
    assert warm["baskets"]["b1"]["state"] == "CONFIRMED"
    assert warm["baskets"]["b1"]["days_in_state"] == UBT.CONFIRMED_MIN_DAYS


def test_prior_state_ignores_rows_at_or_after_the_current_session(tmp_path):
    for tk in ("AAA", "BBB", "CCC"):
        _write_store(tmp_path, tk, _WASHOUT_VALS)
    _write_membership(tmp_path, {"b1": ["AAA", "BBB", "CCC"]})
    art = UBT.compute_all(data_root=tmp_path)
    session = art["data_session"]

    lp = tmp_path / "us_basket_turn" / "ledger.jsonl"
    lp.parent.mkdir(parents=True, exist_ok=True)
    lp.write_text(json.dumps({
        "date": session, "basket_id": "b1", "state": "TURNING",
        "days_in_state": 99,
    }) + "\n")

    again = UBT.compute_all(data_root=tmp_path)
    assert again["baskets"]["b1"]["days_in_state"] == 1, (
        "a row stamped at the current session was read as prior state"
    )


# ---------------------------------------------------------------------------
# (11) Authority — display tier, zero scored authority, no surface wiring
# ---------------------------------------------------------------------------

def test_authority_block_is_display_tier_with_no_powers():
    assert UBT.AUTHORITY["tier"] == "display"
    assert UBT.AUTHORITY["horizon_role"] == "context"
    for key in ("may_rank", "may_gate", "may_size", "may_escalate"):
        assert UBT.AUTHORITY[key] is False, f"{key} is not False"


def test_artifact_carries_the_authority_block_and_schema(tmp_path):
    _thin_universe(tmp_path)
    art = UBT.compute_all(data_root=tmp_path)
    for key in ("schema", "as_of", "data_session", "disclosure",
                "authority", "coverage", "baskets"):
        assert key in art, f"artifact missing {key!r}"
    assert art["schema"] == "us_basket_turn.v1"
    assert art["authority"] == UBT.AUTHORITY


def test_module_imports_no_scoring_or_board_surface():
    """Zero authority wiring: the organ may not reach into a scored path."""
    src = Path(UBT.__file__).read_text()
    forbidden = (
        "us_act_now", "theme_scoring", "build_stock_library",
        "basket_turn_watch", "act_now", "build_site",
    )
    for name in forbidden:
        assert f"import {name}" not in src and f"from engine.{name}" not in src, (
            f"us_basket_turn imports {name} — this organ carries no scored authority"
        )


def test_write_artifact_lands_under_basketdata(tmp_path):
    art = {"schema": "us_basket_turn.v1", "baskets": {}}
    p = UBT.write_artifact(art, site_root=tmp_path)
    assert p == tmp_path / "basketdata" / "us_basket_turn.json"
    assert json.loads(p.read_text())["schema"] == "us_basket_turn.v1"


# ---------------------------------------------------------------------------
# (12) Disclosure
# ---------------------------------------------------------------------------

def test_disclosure_cites_the_kill_row_and_disclaims_a_bottom_call():
    d = UBT.DISCLOSURE
    assert "DNR:KILL-WASHOUT-TURN" in d
    assert "expected-NULL" in d
    assert "Not a revival claim." in d
    assert "never a bottom call" in d
    assert "Forward ledger starts at ship date" in d


def test_disclosure_never_uses_the_guarded_word_validated():
    assert "validated" not in UBT.DISCLOSURE.lower()


# ---------------------------------------------------------------------------
# (13) Frozen v1 thresholds
# ---------------------------------------------------------------------------

def test_thresholds_are_pinned_to_frozen_v1_literals():
    """Ported verbatim from china_basket_turn at ship (2026-08-07).

    Pinned to LITERALS, not to the CN module's attributes: the two organs are
    deliberately independent (CN remains the control), so a CN amendment must not
    silently move US states — nor red this lane. A deliberate change here is an
    amendment-log entry in the module docstring plus an edit to this test.
    """
    assert UBT.FALLING_RET_THRESH == -0.06
    assert UBT.WASHOUT_DD_THRESH == -0.25
    assert UBT.WASHOUT_HIST_ARREST == -0.005
    assert UBT.STOCH_RECLAIM_THRESH == 0.25
    assert UBT.TURNING_HIST_CROSS == 0.0
    assert UBT.CONFIRMED_MIN_DAYS == 3
    assert UBT.CONFIRMED_SLOPE_MIN == 0.0
    assert (UBT.MACD_FAST, UBT.MACD_SLOW, UBT.MACD_SIGNAL) == (12, 26, 9)
    assert UBT.STOCH_WINDOW == 14
    assert UBT.COVERAGE_WARN_FRACTION == 0.6
    assert UBT._MEMBER_STORES == ("stocks", "baskets/ohlcv")


# ---------------------------------------------------------------------------
# Replay is descriptive only — it must never touch the ledger
# ---------------------------------------------------------------------------

def test_replay_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    for tk in ("AAA", "BBB", "CCC"):
        _write_store(tmp_path, tk, _WASHOUT_VALS)
    _write_membership(tmp_path, {"b1": ["AAA", "BBB", "CCC"]})

    rows = UBT.replay("b1", "2026-07-01", _FIXTURE_END, data_root=tmp_path)
    assert rows, "replay produced no rows"
    assert all(r["basket_id"] == "b1" for r in rows)
    assert not (tmp_path / "us_basket_turn" / "ledger.jsonl").exists(), (
        "replay wrote to the forward ledger — replay is descriptive evidence only"
    )


def test_replay_of_an_unknown_basket_is_empty(tmp_path):
    _thin_universe(tmp_path)
    assert UBT.replay("no_such_basket", "2026-07-01", _FIXTURE_END,
                      data_root=tmp_path) == []
