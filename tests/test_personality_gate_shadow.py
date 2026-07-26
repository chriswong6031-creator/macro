"""PSS-W3 — Prophet tailored-gate shadow (pure accrual, never a gate).

Synthetic-store tests mirroring test_mag7_washout_shadow's root=tmp convention.
The nightly-sole-advancer sentinel is exercised via COLLECT_LANE (ledger_lane).

Fixture strategy: a wobbly-down tape (down-down-up steps) prints Stoch-RSI<20
crosses repeatedly; truncating the DAILY series to end exactly on a chosen rung's
fire bar-date makes that rung fire on its LATEST bar — the condition the nightly
lane logs. seed=0 yields a stable 3D fire and a stable 2W fire at deterministic
lengths, so the four disagreement classes are all reproducible without mocking the
derived K/D. Both gates reuse the pinned engine stoch (bars_for + tool_dates(·,"S")
→ engine.mag7_washout.stoch_rsi/cross_up); nothing is re-implemented here.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from engine import personality_gate_shadow as pgs
from engine.personality_gate_shadow import LEDGER_SCHEMA, STATE_SCHEMA, UNIFORM_RUNG
from scripts.research.ptt_w1_persistence_of_fit import bars_for, tool_dates


# ── fixtures ────────────────────────────────────────────────────────────────
def _wobbly(n: int = 600, seed: int = 0) -> pd.Series:
    """down-down-up sawtooth into oversold — S-family Stoch-RSI crosses print
    repeatedly, so a fire can be landed on any rung's terminal bar by truncation."""
    rng = np.random.default_rng(seed)
    px = [100.0]
    for _ in range(1, n):
        px.append(px[-1] * (1 + rng.choice([-0.03, -0.03, 0.025])))
    return pd.Series(px, index=pd.bdate_range("2019-01-01", periods=n))


def _trunc_to_fire(s: pd.Series, rung: str, min_fwd: int = 0) -> pd.Series | None:
    """Trim `s` so its last DAILY bar == a `rung` fire bar-date. With min_fwd>0,
    choose a fire that still leaves ≥min_fwd daily bars ahead in the full tape (for
    the maturity/grading tests)."""
    bars = bars_for(s, rung)
    dates = tool_dates(bars, "S")
    if not dates:
        return None
    if min_fwd <= 0:
        return s[s.index <= dates[-1]]
    for cand in dates[::-1]:
        if int((s.index > cand).sum()) >= min_fwd:
            return s[s.index <= cand]
    return None


def _write_close(root: Path, sym: str, ser: pd.Series) -> None:
    d = root / "baskets" / "ohlcv"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"open": ser, "high": ser * 1.01, "low": ser * 0.99,
                  "close": ser, "volume": 1e6}).to_parquet(d / f"{sym}.parquet")


def _write_codex(root: Path, rows: list[dict], as_of: str = "2026-07-25") -> None:
    d = root / "personality_timing"
    d.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([{"as_of": as_of, **r} for r in rows])
    df.to_parquet(d / "codex.parquet")


def _nightly(monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")


def _ledger_rows(root: Path) -> list[dict]:
    p = root / "personality_timing" / "gate_shadow.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if not l.startswith("#")]


# ── disagreement classification ─────────────────────────────────────────────
def test_four_disagreement_classes(tmp_path, monkeypatch):
    """All four classes populate; only fires are stored; 'neither' is census-only."""
    _nightly(monkeypatch)
    tail3d = _trunc_to_fire(_wobbly(), "3D")     # 3D fires, 2W does not on its terminal
    uni2w = _trunc_to_fire(_wobbly(), "2W")      # 2W fires; a 3D-rung name → uniform_only
    flat = pd.Series(100.0 + np.zeros(400),
                     index=pd.bdate_range("2019-01-01", periods=400))  # never fires
    assert tail3d is not None and uni2w is not None

    _write_close(tmp_path, "TAIL3D", tail3d)     # rung 3D → fired_tailored_only
    _write_close(tmp_path, "UNI2W", uni2w)       # rung 3D → fired_uniform_only
    _write_close(tmp_path, "AGREE2W", uni2w)     # rung 2W → both (agree_by_construction)
    _write_close(tmp_path, "QUIET", flat)        # rung 1W → neither
    _write_codex(tmp_path, [
        {"sym": "TAIL3D", "rung_derived": "3D"},
        {"sym": "UNI2W", "rung_derived": "3D"},
        {"sym": "AGREE2W", "rung_derived": "2W"},
        {"sym": "QUIET", "rung_derived": "1W"},
    ])

    st = pgs.update(root=tmp_path, as_of="2026-07-25")
    assert st is not None and st["schema"] == STATE_SCHEMA
    c = st["coverage_census"]
    assert c["codex_names"] == 4 and c["covered"] == 4
    assert c["classes"] == {"both": 1, "fired_uniform_only": 1,
                            "fired_tailored_only": 1, "neither": 1}
    assert c["disagreements"] == 2          # the two *_only classes
    assert c["agree_by_construction"] == 1  # AGREE2W (rung == uniform 2W)

    rows = {r["sym"]: r for r in _ledger_rows(tmp_path)}
    assert set(rows) == {"TAIL3D", "UNI2W", "AGREE2W"}   # QUIET (neither) not stored
    assert rows["TAIL3D"]["disagreement_class"] == "fired_tailored_only"
    assert rows["TAIL3D"]["fired_tailored"] and not rows["TAIL3D"]["fired_uniform"]
    assert rows["UNI2W"]["disagreement_class"] == "fired_uniform_only"
    assert rows["UNI2W"]["fired_uniform"] and not rows["UNI2W"]["fired_tailored"]
    assert rows["AGREE2W"]["disagreement_class"] == "both"
    assert rows["AGREE2W"]["agree_by_construction"] is True
    for r in rows.values():
        assert r["schema"] == LEDGER_SCHEMA
        assert r["uniform_rung"] == UNIFORM_RUNG == "2W"
        assert r["graded"] is False          # fire on terminal bar — no forward tape yet


# ── ledger append idempotency (same-day rerun) ──────────────────────────────
def test_same_day_rerun_appends_nothing(tmp_path, monkeypatch):
    _nightly(monkeypatch)
    s = _trunc_to_fire(_wobbly(), "3D")
    _write_close(tmp_path, "TAIL3D", s)
    _write_codex(tmp_path, [{"sym": "TAIL3D", "rung_derived": "3D"}])

    st1 = pgs.update(root=tmp_path, as_of="2026-07-25")
    n1 = len(_ledger_rows(tmp_path))
    assert n1 == 1 and st1["ledger"]["appended_today"] == 1

    st2 = pgs.update(root=tmp_path, as_of="2026-07-25")   # same as_of key
    assert len(_ledger_rows(tmp_path)) == n1              # no duplicate row
    assert st2["ledger"]["appended_today"] == 0
    assert st2["ledger"]["fire_rows"] == 1


# ── nightly-sole-advancer sentinel ──────────────────────────────────────────
def test_sentinel_off_appends_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    s = _trunc_to_fire(_wobbly(), "3D")
    _write_close(tmp_path, "TAIL3D", s)
    _write_codex(tmp_path, [{"sym": "TAIL3D", "rung_derived": "3D"}])

    st = pgs.update(root=tmp_path, as_of="2026-07-25")
    assert st is not None and st["gate_open"] is False
    # census still computed (measurement runs any lane); ledger append is gated off
    assert st["coverage_census"]["classes"]["fired_tailored_only"] == 1
    assert not (tmp_path / "personality_timing" / "gate_shadow.jsonl").exists()


# ── PIT rung join (the tailored rung comes from the codex, not re-derived) ───
def test_pit_rung_join_from_codex(tmp_path, monkeypatch):
    """The tailored gate fires on the rung the CODEX assigns the name. Same tape,
    two codex rungs → different tailored-gate outcomes; the join is PIT (the codex
    as_of is carried onto the fire row)."""
    _nightly(monkeypatch)
    s3 = _trunc_to_fire(_wobbly(), "3D")   # 3D fires on terminal, 2W does not
    _write_close(tmp_path, "NAME3D", s3)
    _write_close(tmp_path, "NAME2W", s3)   # identical tape…
    _write_codex(tmp_path, [
        {"sym": "NAME3D", "rung_derived": "3D"},   # …but codex says 3D → tailored fires
        {"sym": "NAME2W", "rung_derived": "2W"},   # …codex says 2W → tailored is the 2W read
    ], as_of="2026-07-25")

    pgs.update(root=tmp_path, as_of="2026-07-25")
    rows = {r["sym"]: r for r in _ledger_rows(tmp_path)}
    assert rows["NAME3D"]["tailored_rung"] == "3D"
    assert rows["NAME3D"]["fired_tailored"] is True
    assert rows["NAME3D"]["codex_asof"] == "2026-07-25"   # PIT stamp carried
    # NAME2W: tailored rung == uniform rung → agree_by_construction; on this tape the
    # 2W terminal bar is NOT a fire, so it lands in 'neither' and is not stored.
    assert "NAME2W" not in rows
    assert pgs.update(root=tmp_path, as_of="2026-07-25")  # idempotent, no crash


def test_bad_rung_and_missing_prices_are_census_dropped(tmp_path, monkeypatch):
    _nightly(monkeypatch)
    s = _trunc_to_fire(_wobbly(), "3D")
    _write_close(tmp_path, "GOOD", s)
    # BADRUNG has an unknown rung; NOPRICE has a codex row but no ohlcv file
    _write_codex(tmp_path, [
        {"sym": "GOOD", "rung_derived": "3D"},
        {"sym": "BADRUNG", "rung_derived": "1M"},
        {"sym": "NOPRICE", "rung_derived": "1W"},
    ])
    st = pgs.update(root=tmp_path, as_of="2026-07-25")
    c = st["coverage_census"]
    assert c["codex_names"] == 3
    assert c["covered"] == 1          # only GOOD
    assert c["bad_rung"] == 1         # BADRUNG
    assert c["no_prices"] == 1        # NOPRICE


# ── deferred DUAL-ruler grading (frozen-until-matured, nightly-gated) ────────
def test_dual_ruler_grade_defers_then_advances(tmp_path, monkeypatch):
    """A fire on the terminal bar stays ungraded (no forward tape); once ≥63td of
    forward tape accrues the grade advances under BOTH rulers, then is idempotent."""
    _nightly(monkeypatch)
    full = _wobbly(600, 0)
    s = _trunc_to_fire(full, "3D", min_fwd=70)   # fire with ≥70 daily bars ahead in `full`
    assert s is not None
    _write_close(tmp_path, "TAIL3D", s)
    _write_codex(tmp_path, [{"sym": "TAIL3D", "rung_derived": "3D"}])

    st1 = pgs.update(root=tmp_path, as_of="2026-07-25")
    assert st1["ledger"]["graded"] == 0          # deferred — frozen until matured
    r1 = _ledger_rows(tmp_path)[0]
    assert r1["tailored_grade"] is None and r1["graded"] is False

    # forward tape accrues (store grows to the full series)
    _write_close(tmp_path, "TAIL3D", full)
    st2 = pgs.update(root=tmp_path, as_of="2026-08-01")
    assert st2["ledger"]["grades_advanced_today"] == 1
    assert st2["ledger"]["graded"] == 1
    r2 = _ledger_rows(tmp_path)[0]
    g = r2["tailored_grade"]
    assert g is not None
    assert set(g) == {"fwd63", "mae63", "prox", "td_to_trough", "timing_label"}
    assert isinstance(g["fwd63"], float)         # legacy ruler
    assert g["mae63"] <= 0                        # timing ruler: adverse excursion ≤0
    assert g["prox"] >= 0                         # entry premium over the ±31td low
    assert g["timing_label"] in ("confirmed_reset", "called_low", "early")
    assert r2["graded"] is True and r2["graded_asof"] == "2026-08-01"

    # idempotent: a later nightly does not re-advance an already-graded fire
    st3 = pgs.update(root=tmp_path, as_of="2026-08-02")
    assert st3["ledger"]["grades_advanced_today"] == 0


def test_grade_gated_off_non_nightly(tmp_path, monkeypatch):
    """Grades never advance outside the nightly lane (sentinel off)."""
    _nightly(monkeypatch)
    full = _wobbly(600, 0)
    s = _trunc_to_fire(full, "3D", min_fwd=70)
    _write_close(tmp_path, "TAIL3D", s)
    _write_codex(tmp_path, [{"sym": "TAIL3D", "rung_derived": "3D"}])
    pgs.update(root=tmp_path, as_of="2026-07-25")     # nightly: fire appended, ungraded
    _write_close(tmp_path, "TAIL3D", full)            # forward tape now exists

    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    st = pgs.update(root=tmp_path, as_of="2026-08-01")  # non-nightly
    assert st["gate_open"] is False
    assert st["ledger"]["grades_advanced_today"] == 0
    assert _ledger_rows(tmp_path)[0]["graded"] is False


# ── flat-RSI NaN edge (reuse engine stoch — must not crash) ──────────────────
def test_flat_rsi_window_does_not_crash(tmp_path, monkeypatch):
    """A long flat-RSI stretch (hi==lo → NaN, not pd.NA) must not crash the scan.
    Reuses the shared engine stoch machinery via bars_for/tool_dates — the same
    NaN-not-crash guard as test_stoch_rsi_flat_rsi_window_is_nan_not_crash."""
    _nightly(monkeypatch)
    n = 240
    vals = [100.0 + (i % 2) for i in range(40)] + [100.5] * (n - 40)  # flat-RSI vector
    px = pd.Series(vals, index=pd.bdate_range("2019-01-01", periods=n))
    _write_close(tmp_path, "FLAT", px)
    _write_codex(tmp_path, [{"sym": "FLAT", "rung_derived": "1W"}])

    st = pgs.update(root=tmp_path, as_of="2026-07-25")   # must not raise
    assert st is not None
    assert st["coverage_census"]["covered"] == 1
    # flat RSI → no S-cross → 'neither'; nothing stored, no crash
    assert st["coverage_census"]["classes"]["neither"] == 1
    assert _ledger_rows(tmp_path) == []


# ── W-FRI tail edge: a 1W bar-date past the last daily close is not a fire ────
def test_wfri_tail_bar_never_stored_with_null_entry(tmp_path, monkeypatch):
    """The 1W (W-FRI) resample can label the last bar with a Friday that is past the
    last daily close (a Thursday-anchored week tail). Such a bar must NOT be reported
    as a fire — mirroring sig_metrics' `i >= len(idx): continue` — so no fire row is
    ever stored with an unresolvable (null) entry. Verified structurally: the scan
    completes and any stored fire carries a resolvable, in-bounds entry."""
    _nightly(monkeypatch)
    s = _trunc_to_fire(_wobbly(), "1W")
    assert s is not None
    # trim off the final Friday so the last 1W label lands past the last daily bar
    while s.index[-1].weekday() == 4:  # Friday
        s = s.iloc[:-1]
    _write_close(tmp_path, "WK", s)
    _write_codex(tmp_path, [{"sym": "WK", "rung_derived": "1W"}])

    st = pgs.update(root=tmp_path, as_of="2026-07-25")   # must not raise
    assert st is not None
    for r in _ledger_rows(tmp_path):
        for side in ("uniform", "tailored"):
            entry = r.get(f"{side}_entry")
            if entry is not None:  # every stored entry is resolvable + in-bounds
                assert isinstance(entry["entry_idx"], int)
                assert entry["entry_idx"] < len(s)


# ── fail-open without stores ─────────────────────────────────────────────────
def test_fail_open_without_codex(tmp_path, monkeypatch):
    _nightly(monkeypatch)
    st = pgs.update(root=tmp_path, as_of="2026-07-25")
    assert st is not None
    assert st["coverage_census"]["codex_names"] == 0
    assert st["ledger"]["fire_rows"] == 0
    assert st["display_only"] is True and st["is_context_only"] is True
