"""Price Pressure lobe (DRL W1) — engine, ledger and artifact contracts.

Everything here runs on a SYNTHETIC panel built in a tmp_path.  CI has no
``data/massive_stock_day`` (20k vendor parquets, R2-homed), so a test that needed
the real store would be a test that never runs.

What each block pins, and why it is worth a test:

* **LSR parity** — the lobe must detect exactly what
  ``scripts/research_liquidity_shock_reversal`` detects, because the frozen base
  rates were measured there.  A re-typed copy of the residual math would drift
  silently; the parity test calls BOTH paths on one fixture and compares.
* **PIT fence** — the identity block is poisoned-forward-proof: rewriting t0+1
  bars must not move a single frozen field.
* **No early close** — a 100% retrace on day 3 must still grade at 21d and 60d
  (review BLOCKER: closing on the good news is upside-only path censoring).
* **Dead tape in the denominator** — a name that stops trading grades
  DELISTED_OR_HALTED inside the terminal shares instead of leaving the table.
* **Ordering** — every emitted list is recency-then-ticker.  Ordering by |z|
  would be the ranking the artifact's authority block says it cannot do.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.price_pressure import (  # noqa: E402
    ENGINE_VERSION,
    LEDGER_HORIZONS,
    TERMINAL_PRIMARY,
    TERMINAL_SECONDARY,
)
from engine.price_pressure import artifact as pp_artifact  # noqa: E402
from engine.price_pressure import base_rates as pp_base  # noqa: E402
from engine.price_pressure import completion as pp_completion  # noqa: E402
from engine.price_pressure import context as pp_context  # noqa: E402
from engine.price_pressure import detect as pp_detect  # noqa: E402
from engine.price_pressure import ledger as pp_ledger  # noqa: E402
from engine.price_pressure import pipeline as pp_pipeline  # noqa: E402

SESSIONS = 220
SHOCK_POS = 100
SECTOR_A = ["AAA", "AAB", "AAC", "AAD", "AAE"]
SECTOR_B = ["BBA", "BBB", "BBC", "BBD"]
UNLABELLED = ["ZZZ"]
ALL_TICKERS = SECTOR_A + SECTOR_B + UNLABELLED


# ---------------------------------------------------------------------------
# fixture
# ---------------------------------------------------------------------------

def _dates(n: int = SESSIONS) -> pd.DatetimeIndex:
    return pd.bdate_range("2023-01-02", periods=n)


def build_panel_frames(returns: dict[str, np.ndarray], *, volumes: dict | None = None,
                       price0: float = 100.0, n: int = SESSIONS,
                       dead_after: dict | None = None,
                       dates: pd.DatetimeIndex | None = None) -> dict[str, pd.DataFrame]:
    """A wide OHLCV panel in the shape ``build_panel`` caches.

    ``dead_after[ticker] = pos`` makes the bars stop after that session, which is
    how a delisting looks in this store: the rows simply end.
    """
    idx = pd.DatetimeIndex(dates) if dates is not None else _dates(n)
    n = len(idx)
    close = pd.DataFrame({
        t: price0 * np.cumprod(1.0 + np.asarray(r)[:n])
        for t, r in returns.items()
    },
                         index=idx)
    vol = pd.DataFrame({t: np.full(n, 1_000_000.0) for t in returns}, index=idx)
    if volumes:
        for t, spec in volumes.items():
            for pos, mult in spec.items():
                vol.iloc[pos, vol.columns.get_loc(t)] = 1_000_000.0 * mult
    for t, pos in (dead_after or {}).items():
        close.iloc[pos + 1:, close.columns.get_loc(t)] = np.nan
        vol.iloc[pos + 1:, vol.columns.get_loc(t)] = np.nan
    return {
        "open": close.shift(1).fillna(price0),
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": vol,
        "transactions": vol / 100.0,
        "split_day": pd.DataFrame(False, index=idx, columns=close.columns),
    }


def default_returns(seed: int = 11, *, shock: float = -0.20,
                    shock_pos: int = SHOCK_POS,
                    path: dict | None = None) -> dict[str, np.ndarray]:
    """Quiet peers, one engineered single-name shock, a controllable aftermath."""
    rng = np.random.default_rng(seed)
    out = {t: rng.normal(0.0, 0.004, SESSIONS) for t in ALL_TICKERS}
    out["AAA"][shock_pos] = shock
    for pos, val in (path or {}).items():
        out["AAA"][shock_pos + pos] = val
    return out


def write_stores(data_dir: Path, *, edgar_tickers: tuple[str, ...] = ("AAA", "AAB"),
                 earn_dates: dict | None = None, mat_dates: dict | None = None) -> None:
    """The two stores ``derive`` and ``news_flags`` insist on, and nothing else."""
    (data_dir / "breadth").mkdir(parents=True, exist_ok=True)
    (data_dir / "edgar").mkdir(parents=True, exist_ok=True)
    rows = [{"ticker": t, "sector": "SecA", "source": "test"} for t in SECTOR_A]
    rows += [{"ticker": t, "sector": "SecB", "source": "test"} for t in SECTOR_B]
    pd.DataFrame(rows).to_parquet(data_dir / "breadth" / "ticker_sectors.parquet")

    e_rows = [{"ticker": t, "filing_date": pd.Timestamp("2019-01-02")}
              for t in edgar_tickers]
    for t, ds in (earn_dates or {}).items():
        e_rows += [{"ticker": t, "filing_date": pd.Timestamp(d)} for d in ds]
    pd.DataFrame(e_rows).to_parquet(data_dir / "edgar" / "earnings_8k_dates.parquet")

    m_rows = [{"ticker": t, "filing_date": pd.Timestamp(d), "form": "8-K"}
              for t, ds in (mat_dates or {}).items() for d in ds]
    if not m_rows:
        m_rows = [{"ticker": "AAB", "filing_date": pd.Timestamp("2019-01-02"),
                   "form": "8-K"}]
    pd.DataFrame(m_rows).to_parquet(data_dir / "edgar" / "material_8k_events.parquet")


@pytest.fixture()
def fixture_env(tmp_path: Path):
    """A ready data_dir + panel with one −20% single-name shock at SHOCK_POS."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    write_stores(data_dir)
    panel = build_panel_frames(default_returns(),
                               volumes={"AAA": {SHOCK_POS: 5.0}})
    return {"data_dir": data_dir, "panel": panel, "dates": _dates()}


def prep_from(panel: dict, data_dir: Path) -> dict:
    """``pipeline.prepare`` without the 45s panel build (fixture supplies it)."""
    d = pp_detect.derive_frames(panel, data_dir)
    sectors = pp_pipeline.load_sectors(data_dir)
    sessions = d["sessions"]
    membership = pp_context.load_basket_membership(data_dir)
    return {
        "panel": panel, "d": d, "sessions": sessions, "sectors": sectors,
        "breadth": pp_detect.breadth_by_date(d),
        "peer_shocks": pp_detect.peer_shock_by_date(d, sectors),
        "peer_basis": pp_detect.peer_basis_mask(d, sectors),
        "spy_z": pp_context.spy_return_z(data_dir, sessions),
        "vix_pct": pp_context.vix_percentile(data_dir, sessions),
        "pos_frames": pp_context.position_frames(panel),
        "revisions_covered": pp_context.revisions_covered_set(data_dir),
        "membership": membership,
        "baskets": pp_context.basket_residual_frames(d["f"]["ret"], membership),
        "data_dir": data_dir,
        "timing_s": {"panel": 0.0, "derive": 0.0},
        "panel_names": int(panel["close"].shape[1]),
        "sector_covered_share": 9 / 10,
        "panel_span": (str(sessions[0].date()), str(sessions[-1].date())),
    }


# ---------------------------------------------------------------------------
# detection: fence + LSR parity
# ---------------------------------------------------------------------------

def test_fence_fires_once_on_the_engineered_shock(fixture_env):
    d = pp_detect.derive_frames(fixture_env["panel"], fixture_env["data_dir"])
    ev = pp_detect.harvest(d)
    assert len(ev) == 1
    row = ev.iloc[0]
    assert row["ticker"] == "AAA" and row["side"] == "down"
    assert row["date"] == fixture_env["dates"][SHOCK_POS]
    assert row["resid_z"] <= -3.0
    assert row["vol_multiple" if "vol_multiple" in ev.columns else "abn_volume"] >= 2.0


def test_fence_eligibility_price_adv_and_split_day(fixture_env):
    """Each leg of the LSR fence, removed one at a time, kills the event."""
    data_dir = fixture_env["data_dir"]

    # (a) split-day bars are stamped ineligible even though the move is huge.
    panel = build_panel_frames(default_returns(), volumes={"AAA": {SHOCK_POS: 5.0}})
    panel["split_day"].iloc[SHOCK_POS, panel["split_day"].columns.get_loc("AAA")] = True
    assert pp_detect.harvest(pp_detect.derive_frames(panel, data_dir)).empty

    # (b) sub-$5 close.
    panel = build_panel_frames(default_returns(), volumes={"AAA": {SHOCK_POS: 5.0}},
                               price0=2.0)
    assert pp_detect.harvest(pp_detect.derive_frames(panel, data_dir)).empty

    # (c) below the $5M ADV event floor.
    panel = build_panel_frames(default_returns(), volumes={"AAA": {SHOCK_POS: 5.0}})
    panel["volume"] = panel["volume"] / 1e4
    assert pp_detect.harvest(pp_detect.derive_frames(panel, data_dir)).empty

    # (d) no abnormal volume -> below the 2x trigger.
    panel = build_panel_frames(default_returns())
    assert pp_detect.harvest(pp_detect.derive_frames(panel, data_dir)).empty


def test_detection_parity_with_the_lsr_research_script(fixture_env):
    """Both paths, one fixture: the seam must not have been swapped for a copy."""
    import scripts.research_liquidity_shock_reversal as lsr

    panel, data_dir = fixture_env["panel"], fixture_env["data_dir"]
    lsr_d = lsr.derive(panel, data_dir)
    lsr_ev = lsr.harvest_events(lsr_d).sort_values(["date", "ticker", "side"])

    pp_ev = pp_detect.harvest(pp_detect.derive_frames(panel, data_dir))

    assert list(zip(lsr_ev["ticker"], lsr_ev["side"])) == \
        list(zip(pp_ev["ticker"], pp_ev["side"]))
    assert list(pd.to_datetime(lsr_ev["date"])) == list(pd.to_datetime(pp_ev["date"]))
    for col in ("resid", "resid_z", "ret", "clv", "gap", "amihud_rel"):
        np.testing.assert_allclose(lsr_ev[col].to_numpy(dtype=float),
                                   pp_ev[col].to_numpy(dtype=float), rtol=0, atol=0)
    # And the seam really is the research module, not a lookalike.
    assert pp_detect.derive is lsr.derive
    assert pp_detect.harvest_events is lsr.harvest_events


def test_peer_basis_mask_matches_the_lsr_helper_fallback(fixture_env):
    """Every 'market' cell must equal the whole-universe mean the helper fills in."""
    panel, data_dir = fixture_env["panel"], fixture_env["data_dir"]
    d = pp_detect.derive_frames(panel, data_dir)
    sectors = pp_pipeline.load_sectors(data_dir)
    mask = pp_detect.peer_basis_mask(d, sectors)

    ret = d["f"]["ret"]
    peer = pp_detect.sector_ex_self_peer(ret, sectors) if hasattr(pp_detect, "sector_ex_self_peer") \
        else pp_context.sector_ex_self_peer(ret, sectors)
    mkt = ret.mean(axis=1)
    market_cells = (~mask) & ret.notna()
    diff = peer.where(market_cells).sub(mkt, axis=0).abs()
    assert float(np.nanmax(diff.to_numpy())) < 1e-12
    # ZZZ carries no sector label, so it can never be sector-basis.
    assert not bool(mask["ZZZ"].any())
    assert bool(mask["AAA"].any())


# ---------------------------------------------------------------------------
# pure math
# ---------------------------------------------------------------------------

def test_retrace_fraction_both_sides_overshoot_and_guard():
    l0_down = float(np.log1p(-0.20))          # ≈ −0.2231
    # A full recovery of the log residual reads exactly 1.0.
    assert pp_ledger.retrace_fraction(-l0_down, -0.20, "down") == pytest.approx(1.0)
    # Half way back.
    assert pp_ledger.retrace_fraction(-l0_down / 2, -0.20, "down") == pytest.approx(0.5)
    # Continuation is NEGATIVE, not a small positive.
    assert pp_ledger.retrace_fraction(l0_down / 2, -0.20, "down") == pytest.approx(-0.5)
    # Overshoot past the pre-shock level is allowed to exceed 1.
    assert pp_ledger.retrace_fraction(-1.6 * l0_down, -0.20, "down") == pytest.approx(1.6)

    l0_up = float(np.log1p(0.20))
    assert pp_ledger.retrace_fraction(-l0_up, 0.20, "up") == pytest.approx(1.0)
    assert pp_ledger.retrace_fraction(l0_up, 0.20, "up") == pytest.approx(-1.0)

    # Near-zero denominator -> null, never an explosion.
    assert pp_ledger.retrace_fraction(0.5, 0.001, "down") is None
    assert pp_ledger.retrace_fraction(0.5, -0.001, "up") is None
    assert pp_ledger.retrace_fraction(None, -0.2, "down") is None
    assert pp_ledger.retrace_fraction(float("nan"), -0.2, "down") is None


def test_display_states_are_exhaustive_and_mirrored():
    for frac in (-5.0, -0.16, -0.15, -0.14, 0.0, 0.32, 0.33, 1.5):
        assert pp_ledger.classify_display(frac, "down") in pp_ledger.DOWN_STATES
        assert pp_ledger.classify_display(frac, "up") in pp_ledger.UP_STATES
    assert pp_ledger.classify_display(-0.20, "down") == "SLIDING"
    assert pp_ledger.classify_display(-0.20, "up") == "EXTENDING"
    assert pp_ledger.classify_display(0.0, "down") == "HOLDING"
    assert pp_ledger.classify_display(0.40, "down") == "RETRACING"
    assert pp_ledger.classify_display(0.40, "up") == "FADING"
    assert pp_ledger.classify_display(None, "down") is None


def test_terminal_grades_use_window_names_on_both_sides():
    assert pp_ledger.terminal_grade(0.9, "down", 21) == "RECOVERED_21D"
    assert pp_ledger.terminal_grade(0.5, "down", 21) == "PARTIAL_21D"
    assert pp_ledger.terminal_grade(0.1, "down", 21) == "ACCEPTED_LOWER_21D"
    assert pp_ledger.terminal_grade(0.9, "up", 60) == "GAVE_BACK_60D"
    assert pp_ledger.terminal_grade(0.1, "up", 60) == "KEPT_60D"


def test_debounce_needs_two_consecutive_closes_and_shows_pending():
    # One qualifying close is a PENDING badge, never a flip.
    state, pending, flip = pp_ledger.resolve_state(["SLIDING"])
    assert (state, pending, flip) == ("SHOCK", "SLIDING", None)
    # Two in a row flips, on the second close.
    state, pending, flip = pp_ledger.resolve_state(["SLIDING", "SLIDING"])
    assert (state, pending, flip) == ("SLIDING", None, 2)
    # An alternating tape never flips.
    state, pending, _ = pp_ledger.resolve_state(["SLIDING", "HOLDING", "SLIDING"])
    assert state == "SHOCK" and pending == "SLIDING"
    # A hole in the tape breaks the run: two closes must be CONSECUTIVE.
    state, _, _ = pp_ledger.resolve_state(["SLIDING", None, "SLIDING"])
    assert state == "SHOCK"
    # Once flipped, staying put clears the badge.
    state, pending, _ = pp_ledger.resolve_state(["SLIDING", "SLIDING", "SLIDING"])
    assert state == "SLIDING" and pending is None


def test_catchup_window_bounds():
    sessions = _dates(400)
    # Normal case: 5 sessions of overlap behind the ledger's own max.
    win = pp_ledger.catchup_window(sessions, sessions[380])
    assert win[0] == sessions[375] and win[-1] == sessions[-1]
    assert len(win) == 25
    # Floor: a ledger already at the store max still re-checks 15 sessions.
    win = pp_ledger.catchup_window(sessions, sessions[-1])
    assert len(win) == 15
    # Cap: a very stale ledger does not become the historical backfill.
    win = pp_ledger.catchup_window(sessions, sessions[0])
    assert len(win) == 90 and win[-1] == sessions[-1]
    # Empty ledger takes the cap tail, not the whole span.
    win = pp_ledger.catchup_window(sessions, None)
    assert len(win) == 90
    assert len(pp_ledger.catchup_window(pd.DatetimeIndex([]), None)) == 0


# ---------------------------------------------------------------------------
# ledger: grading, eras, PIT
# ---------------------------------------------------------------------------

def _advance(panel, data_dir, data_root, *, mode="backfill", **kw):
    prep = prep_from(panel, data_dir)
    return prep, pp_pipeline.advance(prep, data_root, mode=mode, write=True,
                                     require_nightly_lane=False, **kw)


def test_horizon_fields_are_null_until_the_window_fully_elapses(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    write_stores(data_dir)
    # Shock 5 sessions before the end of the panel: 1/3/5 elapse, 10/21/60 cannot.
    pos = SESSIONS - 6
    panel = build_panel_frames(default_returns(shock_pos=pos),
                               volumes={"AAA": {pos: 5.0}})
    _, res = _advance(panel, data_dir, tmp_path)
    row = res["ledger"].iloc[0]
    for h in (1, 3, 5):
        assert pd.notna(row[f"fwd{h}"]), h
    for h in (10, 21, 60):
        assert pd.isna(row[f"fwd{h}"]), h
        assert pd.isna(row[f"retrace_{h}"]), h
    assert row[f"terminal_state_{TERMINAL_PRIMARY}d"] is None
    assert not bool(row["closed"])
    assert row["sessions_elapsed"] == 5


def test_no_early_close_full_retrace_still_grades_both_windows(tmp_path):
    """A 100% retrace on day 3 is an OBSERVATION, not an exit (review BLOCKER)."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    write_stores(data_dir)
    # Down 20% at t0, all the way back on t+3, then quietly back down by t+21.
    path = {3: 0.25, 10: -0.20}
    panel = build_panel_frames(default_returns(path=path),
                               volumes={"AAA": {SHOCK_POS: 5.0}})
    _, res = _advance(panel, data_dir, tmp_path)
    row = res["ledger"].iloc[0]
    assert row["days_to_first_100pct_retrace"] == 3
    assert row["retrace_3"] > 1.0
    # The row did NOT stop at day 3.
    assert pd.notna(row[f"fwd{TERMINAL_PRIMARY}"])
    assert pd.notna(row[f"fwd{TERMINAL_SECONDARY}"])
    assert row[f"terminal_state_{TERMINAL_PRIMARY}d"] is not None
    assert bool(row["closed"])
    # And the later slide is visible in the terminal, not hidden by the day-3 pop.
    assert row[f"terminal_state_{TERMINAL_PRIMARY}d"] == "ACCEPTED_LOWER_21D"


def test_dead_tape_grades_delisted_inside_the_denominator(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    write_stores(data_dir)
    panel = build_panel_frames(default_returns(), volumes={"AAA": {SHOCK_POS: 5.0}},
                               dead_after={"AAA": SHOCK_POS + 4})
    _, res = _advance(panel, data_dir, tmp_path)
    row = res["ledger"].iloc[0]
    assert bool(row["dead_tape"]) and bool(row["truncated"])
    assert row[f"terminal_state_{TERMINAL_PRIMARY}d"] == pp_ledger.DELISTED
    assert row[f"terminal_state_{TERMINAL_SECONDARY}d"] == pp_ledger.DELISTED
    assert bool(row["closed"])
    # It is IN the table, not dropped from it.
    tab = pp_base.tables(res["ledger"])["down"][str(TERMINAL_PRIMARY)]["ALL"]
    assert tab["share_delisted_or_halted"] == 1.0
    assert tab["n_terminal_graded"] == 1


def test_identity_block_is_immune_to_poisoned_forward_bars(tmp_path):
    """Rewrite every bar after t0 — not one frozen field may move."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    write_stores(data_dir)
    panel = build_panel_frames(default_returns(), volumes={"AAA": {SHOCK_POS: 5.0}})
    prep = prep_from(panel, data_dir)
    clean = pp_pipeline.harvest_rows(prep, prep["sessions"], era="backfill",
                                     harvested_asof="2023-01-02")

    poisoned = {k: v.copy() for k, v in panel.items()}
    rng = np.random.default_rng(99)
    for col in ("open", "high", "low", "close", "volume", "transactions"):
        block = poisoned[col].iloc[SHOCK_POS + 1:]
        poisoned[col].iloc[SHOCK_POS + 1:] = block.to_numpy() * (
            1.0 + rng.normal(0.0, 0.25, block.shape))
    prep2 = prep_from(poisoned, data_dir)
    dirty = pp_pipeline.harvest_rows(prep2, prep2["sessions"], era="backfill",
                                     harvested_asof="2023-01-02")

    dirty = dirty[dirty["date"] == pd.Timestamp(_dates()[SHOCK_POS])]
    clean = clean[clean["date"] == pd.Timestamp(_dates()[SHOCK_POS])]
    assert len(clean) == len(dirty) == 1
    for col in pp_ledger.IDENTITY_COLUMNS:
        a, b = clean.iloc[0][col], dirty.iloc[0][col]
        if isinstance(a, float) and np.isnan(a):
            assert isinstance(b, float) and np.isnan(b), col
        else:
            assert a == b, col


def test_ledger_has_no_categorical_day_taxonomy_column():
    """DNR:KILL-PARALLEL-SHOCK-CLASSIFIER — numbers only, no day vocabulary."""
    assert "day_character" not in pp_ledger.LEDGER_COLUMNS
    for col in ("panel_shock_count", "panel_share_z2", "spy_ret_z"):
        assert col in pp_ledger.IDENTITY_COLUMNS
    assert not [c for c in pp_ledger.LEDGER_COLUMNS
                if "character" in c or "day_type" in c or "regime" in c]


def test_advance_is_idempotent_and_byte_stable(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    write_stores(data_dir)
    panel = build_panel_frames(default_returns(), volumes={"AAA": {SHOCK_POS: 5.0}})
    prep, first = _advance(panel, data_dir, tmp_path, mode="nightly", cap=SESSIONS)
    p = pp_ledger.ledger_path(tmp_path)
    b1 = p.read_bytes()
    n1 = len(first["ledger"])

    second = pp_pipeline.advance(prep, tmp_path, mode="nightly", write=True,
                                 require_nightly_lane=False, cap=SESSIONS)
    assert len(second["ledger"]) == n1
    assert second["stats"]["merge"]["appended"] == 0
    assert p.read_bytes() == b1


def test_era_rules_forward_gap_and_backfill_refusal(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    write_stores(data_dir)
    # Two shocks: one on the newest session (forward), one well behind it (gap).
    rets = default_returns()
    rets["AAA"][SESSIONS - 1] = -0.20
    panel = build_panel_frames(rets, volumes={"AAA": {SHOCK_POS: 5.0,
                                                     SESSIONS - 1: 5.0}})
    prep, res = _advance(panel, data_dir, tmp_path, mode="nightly", cap=SESSIONS)
    led = res["ledger"]
    assert set(led["era"]) == {"forward", "gap"}
    newest = led[led["date"] == prep["sessions"][-1]]
    assert list(newest["era"]) == ["forward"]
    older = led[led["date"] == prep["sessions"][SHOCK_POS]]
    assert list(older["era"]) == ["gap"]

    # A later backfill must refuse to touch either of them.
    after = pp_pipeline.advance(prep, tmp_path, mode="backfill", write=True,
                                require_nightly_lane=False)
    assert after["stats"]["merge"]["protected"] == 2
    assert after["stats"]["merge"]["refreshed"] == 0
    assert set(after["ledger"]["era"]) == {"forward", "gap"}


def test_ledger_write_is_gated_on_the_nightly_lane(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    write_stores(data_dir)
    panel = build_panel_frames(default_returns(), volumes={"AAA": {SHOCK_POS: 5.0}})
    prep = prep_from(panel, data_dir)

    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    res = pp_pipeline.advance(prep, tmp_path, mode="nightly", write=True,
                              require_nightly_lane=True, cap=SESSIONS)
    assert res["stats"]["write"] == {"written": False, "reason": "off_nightly_lane",
                                     "rows": len(res["ledger"])}
    assert not pp_ledger.ledger_path(tmp_path).exists()

    monkeypatch.setenv("COLLECT_LANE", "nightly")
    res = pp_pipeline.advance(prep, tmp_path, mode="nightly", write=True,
                              require_nightly_lane=True, cap=SESSIONS)
    assert res["stats"]["write"]["written"] is True
    assert pp_ledger.ledger_path(tmp_path).exists()


def test_episodes_collapse_a_cluster_and_first_in_h_is_per_horizon(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    write_stores(data_dir)
    rets = default_returns()
    rets["AAA"][SHOCK_POS + 3] = -0.20     # inside the 5-session join window
    rets["AAA"][SHOCK_POS + 40] = -0.20    # a separate episode
    panel = build_panel_frames(rets, volumes={"AAA": {SHOCK_POS: 5.0,
                                                     SHOCK_POS + 3: 5.0,
                                                     SHOCK_POS + 40: 5.0}})
    _, res = _advance(panel, data_dir, tmp_path)
    led = res["ledger"].sort_values("date").reset_index(drop=True)
    assert len(led) == 3
    assert led.loc[0, "episode_id"] == led.loc[1, "episode_id"]
    assert led.loc[2, "episode_id"] != led.loc[0, "episode_id"]
    assert list(led["first_of_episode"]) == [True, False, True]
    assert list(led["followup_shock"]) == [False, True, False]
    # The +3 row is not fresh at ANY horizon; the +40 row is fresh at 5 but not 60.
    assert not bool(led.loc[1, "first_in_5"])
    assert bool(led.loc[2, "first_in_5"])
    assert not bool(led.loc[2, "first_in_60"])


def test_families_are_coverage_gated():
    assert pp_context.family_of(True, False, True) == "earnings-filing"
    assert pp_context.family_of(False, True, True) == "other-filing"
    assert pp_context.family_of(False, False, True) == "no-filing"
    # NOT covered by EDGAR: we did not look, so we cannot say "no filing".
    assert pp_context.family_of(False, False, False) == "filing-coverage-unknown"
    assert pp_context.family_of(True, True, False) == "filing-coverage-unknown"
    assert pp_context.FAMILY_LABELS["filing-coverage-unknown"] == \
        "filings not tracked for this name"


def test_family_lands_on_the_row_and_respects_coverage(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    shock_day = _dates()[SHOCK_POS]
    write_stores(data_dir, edgar_tickers=("AAB",),
                 earn_dates={"AAA": [shock_day]})
    panel = build_panel_frames(default_returns(), volumes={"AAA": {SHOCK_POS: 5.0}})
    _, res = _advance(panel, data_dir, tmp_path)
    row = res["ledger"].iloc[0]
    # AAA now HAS an earnings filing on the day and is therefore covered.
    assert bool(row["edgar_covered"])
    assert row["family"] == "earnings-filing"

    # Same shock, no EDGAR coverage at all -> the unknown family, never no-filing.
    data_dir2 = tmp_path / "data2"
    data_dir2.mkdir()
    write_stores(data_dir2, edgar_tickers=("AAB",))
    _, res2 = _advance(panel, data_dir2, tmp_path / "root2")
    assert res2["ledger"].iloc[0]["family"] == "filing-coverage-unknown"


# ---------------------------------------------------------------------------
# §10.1 VIXCLS stamp completion
#
# The prereg's measured problem: the FRED store trails the tape by one session
# at the 22:30Z harvest, so a forward row stamps vix_pctile=NULL through no
# property of its own — and excluding nulls forever starved BOTH evidence arms
# to zero.  Every test below runs the real two-night shape: night 1 harvests
# against a store that is missing t0, night 2 finds t0 in the store.
# ---------------------------------------------------------------------------

def _vix_values(n: int = SESSIONS, seed: int = 5) -> np.ndarray:
    """A VIXCLS path whose PREFIX is stable — the extended store must agree with
    the lagging one on every shared date, or the two nights are two series."""
    rng = np.random.default_rng(seed)
    return (12.0 + np.abs(rng.normal(0.0, 4.0, SESSIONS)))[:n]


def _completion_dates(n: int = SESSIONS) -> pd.DatetimeIndex:
    """The prospective fixture begins exactly on §10.6's eligibility boundary."""
    return pd.bdate_range(pp_completion.EVIDENCE_ELIGIBLE_FROM, periods=n)


COMPLETION_T0_POS = SESSIONS - 2
COMPLETION_FIRST_N = SESSIONS - 1


def write_vix(data_dir: Path, *, through: int = SESSIONS,
              values: np.ndarray | None = None) -> Path:
    """A FRED VIXCLS store covering the panel's first ``through`` sessions.

    ``through = SESSIONS - 1`` is the lag the prereg measured: the tape has
    traded today, the store's newest observation is yesterday.
    """
    idx = pd.DatetimeIndex(_completion_dates(through), name="date")
    vals = _vix_values(through) if values is None else np.asarray(values)[:through]
    (data_dir / "fred").mkdir(parents=True, exist_ok=True)
    p = data_dir / "fred" / "VIXCLS.parquet"
    pd.DataFrame({"vix_close": vals}, index=idx).to_parquet(p)
    return p


def _last_session_shock(data_dir: Path) -> dict:
    """One shock on the panel's NEWEST session — the row the lag actually bites."""
    write_stores(data_dir)
    rets = default_returns(shock_pos=COMPLETION_T0_POS)
    return build_panel_frames(
        rets, n=COMPLETION_FIRST_N,
        volumes={"AAA": {COMPLETION_T0_POS: 5.0}},
        dates=_completion_dates(COMPLETION_FIRST_N),
    )


def _next_session_after_shock() -> dict:
    """The following producer's panel: same history, exactly one newer session."""
    rets = default_returns(shock_pos=COMPLETION_T0_POS)
    return build_panel_frames(
        rets, volumes={"AAA": {COMPLETION_T0_POS: 5.0}},
        dates=_completion_dates(),
    )


def _receipt_lines(data_root: Path) -> list[str]:
    p = pp_completion.receipts_path(data_root)
    return p.read_text(encoding="utf-8").splitlines() if p.exists() else []


def test_lag_completion_fills_the_null_stamp_and_files_a_receipt(tmp_path, capsys):
    """(a) null stamp + t0 present + immature -> completed, receipt with the
    SHA-256 of the exact VIXCLS bytes the value was computed from."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    panel = _last_session_shock(data_dir)
    next_panel = _next_session_after_shock()
    t0 = _completion_dates()[COMPLETION_T0_POS]

    # Night 1: the store stops one session short, so the row stamps NULL.
    write_vix(data_dir, through=COMPLETION_T0_POS)
    _, first = _advance(panel, data_dir, tmp_path, mode="nightly", cap=SESSIONS)
    assert len(first["ledger"]) == 1
    assert pd.isna(first["ledger"].iloc[0]["vix_pctile"])
    assert first["stats"]["completion"]["skipped_not_subsequent"] == 1
    assert not pp_completion.receipts_path(tmp_path).exists()

    # Night 2: FRED has published t0's close.
    store = write_vix(data_dir, through=COMPLETION_FIRST_N)
    _, second = _advance(next_panel, data_dir, tmp_path, mode="nightly", cap=SESSIONS)
    row = second["ledger"].iloc[0]
    cstats = second["stats"]["completion"]
    assert cstats["candidates"] == 1 and cstats["completed"] == 1
    assert cstats["receipts"] == 1

    # The completed value is t0's OWN close percentile under the shipped §3
    # transform — not a forward-fill of the prior session.
    expected = float(pp_context.vix_percentile(data_dir, pd.DatetimeIndex([t0])).iloc[0])
    assert np.isfinite(expected)
    assert float(row["vix_pctile"]) == pytest.approx(expected, abs=0.0, rel=0.0)
    prior = float(pp_context.vix_percentile(
        data_dir, pd.DatetimeIndex([_completion_dates()[COMPLETION_T0_POS - 1]])).iloc[0])
    assert float(row["vix_pctile"]) != pytest.approx(prior)

    lines = _receipt_lines(tmp_path)
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert list(rec) == list(pp_completion.RECEIPT_FIELDS)
    assert rec["ticker"] == "AAA" and rec["side"] == "down"
    assert rec["date"] == str(t0.date())
    assert rec["vix_pctile"] == pytest.approx(expected, abs=0.0, rel=0.0)
    assert rec["engine_version"] == ENGINE_VERSION
    assert rec["vixcls_sha256"] == hashlib.sha256(store.read_bytes()).hexdigest()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", rec["observed_at"])
    assert lines[0] == lines[0].rstrip()

    # The counts reach the Actions log through a bare print at line start.
    out = capsys.readouterr().out.splitlines()
    hit = [ln for ln in out if ln.startswith("price_pressure: vix stamp completion")]
    assert hit and "completed=1" in hit[-1] and "receipts_appended=1" in hit[-1]

    # The persisted ledger carries the completion, not just the in-memory frame.
    assert float(pp_ledger.read_ledger(tmp_path).iloc[0]["vix_pctile"]) == \
        pytest.approx(expected, abs=0.0, rel=0.0)


def test_completion_never_revises_a_non_null_stamp(tmp_path):
    """(b) a stamp that disagrees with tonight's recompute is STILL immutable."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    panel = _last_session_shock(data_dir)
    next_panel = _next_session_after_shock()
    t0 = _completion_dates()[COMPLETION_T0_POS]

    write_vix(data_dir, through=COMPLETION_FIRST_N)
    _, first = _advance(panel, data_dir, tmp_path, mode="nightly", cap=SESSIONS)
    stamped = float(first["ledger"].iloc[0]["vix_pctile"])
    assert np.isfinite(stamped)

    # Rewrite the store so a recompute would land somewhere else entirely.
    write_vix(
        data_dir, through=COMPLETION_FIRST_N,
        values=np.linspace(80.0, 5.0, SESSIONS),
    )
    recomputed = float(pp_context.vix_percentile(data_dir, pd.DatetimeIndex([t0])).iloc[0])
    assert recomputed != pytest.approx(stamped)

    _, second = _advance(next_panel, data_dir, tmp_path, mode="nightly", cap=SESSIONS)
    assert float(second["ledger"].iloc[0]["vix_pctile"]) == pytest.approx(stamped)
    assert second["stats"]["completion"]["candidates"] == 0
    assert not pp_completion.receipts_path(tmp_path).exists()


def test_t0_absent_from_the_store_is_counted_not_completed(tmp_path):
    """(c) the store cannot answer yet — the row waits inside its window."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    panel = _last_session_shock(data_dir)
    next_panel = _next_session_after_shock()
    write_vix(data_dir, through=COMPLETION_T0_POS)

    _advance(panel, data_dir, tmp_path, mode="nightly", cap=SESSIONS)
    _, res = _advance(next_panel, data_dir, tmp_path, mode="nightly", cap=SESSIONS)
    cstats = res["stats"]["completion"]
    assert cstats == {"candidates": 1, "completed": 0, "skipped_ineligible": 0,
                      "skipped_not_subsequent": 0, "skipped_matured": 0,
                      "skipped_no_vix": 1,
                      "skipped_receipted": 0, "receipts": 0}
    assert pd.isna(res["ledger"].iloc[0]["vix_pctile"])
    assert not pp_completion.receipts_path(tmp_path).exists()


def test_a_row_that_missed_its_window_is_never_completed(tmp_path):
    """(d) the producer grades fwd5 before completion, then leaves NULL forever."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    write_stores(data_dir)
    first_n = SESSIONS - 5
    shock_pos = first_n - 1
    rets = default_returns(shock_pos=shock_pos)
    first_panel = build_panel_frames(
        rets, n=first_n, volumes={"AAA": {shock_pos: 5.0}},
        dates=_completion_dates(first_n),
    )

    # Night 1: t0 is the newest session, so the row is genuinely forward.
    write_vix(data_dir, through=first_n - 1)
    _, first = _advance(first_panel, data_dir, tmp_path, mode="nightly", cap=SESSIONS)
    assert pd.isna(first["ledger"].iloc[0]["vix_pctile"])
    assert first["ledger"].iloc[0]["era"] == "forward"
    assert pd.isna(first["ledger"].iloc[0]["fwd5"])

    # Five new sessions arrive with t0's VIX close. grade() runs first, so fwd5
    # matures and the completion exception is already closed on this producer.
    full_panel = build_panel_frames(
        rets, volumes={"AAA": {shock_pos: 5.0}}, dates=_completion_dates(),
    )
    write_vix(data_dir, through=first_n)
    _, second = _advance(full_panel, data_dir, tmp_path, mode="nightly", cap=SESSIONS)
    cstats = second["stats"]["completion"]
    assert cstats["candidates"] == 1 and cstats["completed"] == 0
    assert cstats["skipped_matured"] == 1 and cstats["skipped_no_vix"] == 0
    assert np.isfinite(second["ledger"].iloc[0]["fwd5"])
    assert pd.isna(second["ledger"].iloc[0]["vix_pctile"])
    assert not pp_completion.receipts_path(tmp_path).exists()


def test_completion_window_closes_at_the_fwd5_endpoint_even_if_price_is_missing():
    """At t0+5 the endpoint has matured; a torn tape cannot extend the exception."""
    dates = _completion_dates(6)
    df = pd.DataFrame({
        "ticker": ["HALT"], "date": [dates[0]], "side": ["down"],
        "era": ["forward"], "vix_pctile": [np.nan], "fwd5": [np.nan],
    })
    vix = pd.Series([0.9], index=pd.DatetimeIndex([dates[0]]))
    plan, stats = pp_completion.plan_completions(
        df, vix_pct=vix, sessions=dates, asof=dates[-1],
    )
    assert plan == []
    assert stats["skipped_matured"] == 1
    assert stats["completed"] == 0


def test_dead_tape_row_is_closed_by_the_session_gate_not_by_fwd5(tmp_path):
    """(d, second leg) fwd5 stays NULL forever on a halted name — the belt-and-
    braces session distance is the only thing that closes that window."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    write_stores(data_dir)
    shock_pos = SESSIONS - 20
    first_n = shock_pos + 1
    rets = default_returns(shock_pos=shock_pos)
    first_panel = build_panel_frames(
        rets, n=first_n, volumes={"AAA": {shock_pos: 5.0}},
        dates=_completion_dates(first_n),
    )
    write_vix(data_dir, through=first_n - 1)
    _, first = _advance(first_panel, data_dir, tmp_path, mode="nightly", cap=SESSIONS)
    assert pd.isna(first["ledger"].iloc[0]["fwd5"])          # never matures
    assert first["ledger"].iloc[0]["era"] == "forward"

    full_panel = build_panel_frames(
        rets, volumes={"AAA": {shock_pos: 5.0}},
        dead_after={"AAA": shock_pos + 2}, dates=_completion_dates(),
    )
    write_vix(data_dir, through=first_n)
    _, second = _advance(full_panel, data_dir, tmp_path, mode="nightly", cap=SESSIONS)
    cstats = second["stats"]["completion"]
    assert cstats["candidates"] == 1 and cstats["completed"] == 0
    assert cstats["skipped_matured"] == 1
    assert pd.isna(second["ledger"].iloc[0]["vix_pctile"])
    assert pd.isna(second["ledger"].iloc[0]["fwd5"])
    assert bool(second["ledger"].iloc[0]["dead_tape"])


def test_completion_is_fenced_to_eligible_forward_rows_only():
    """§10.6: no gap/backfill or pre-2026-08-11 identity row is repairable."""
    dates = pd.bdate_range("2026-08-10", periods=3)
    df = pd.DataFrame({
        "ticker": ["OLD", "GAP", "OK", "SAME"],
        "date": [dates[0], dates[1], dates[1], dates[2]],
        "side": ["down", "down", "down", "down"],
        "era": ["forward", "gap", "forward", "forward"],
        "vix_pctile": [np.nan, np.nan, np.nan, np.nan],
        "fwd5": [np.nan, np.nan, np.nan, np.nan],
    })
    vix = pd.Series([0.2, 0.4, 0.6], index=dates)
    plan, stats = pp_completion.plan_completions(
        df, vix_pct=vix, sessions=dates, asof=dates[-1],
    )

    assert [(row["ticker"], row["date"]) for row in plan] == [
        ("OK", "2026-08-11"),
    ]
    assert stats["candidates"] == 4
    assert stats["completed"] == 1
    assert stats["skipped_ineligible"] == 2
    assert stats["skipped_not_subsequent"] == 1


def test_completion_is_idempotent_and_leaves_the_ledger_byte_stable(tmp_path):
    """(e) a second run on the same inputs files nothing and moves nothing."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    panel = _last_session_shock(data_dir)
    next_panel = _next_session_after_shock()
    write_vix(data_dir, through=COMPLETION_T0_POS)
    _advance(panel, data_dir, tmp_path, mode="nightly", cap=SESSIONS)
    write_vix(data_dir, through=COMPLETION_FIRST_N)
    prep, _ = _advance(next_panel, data_dir, tmp_path, mode="nightly", cap=SESSIONS)

    ledger_bytes = pp_ledger.ledger_path(tmp_path).read_bytes()
    receipt_bytes = pp_completion.receipts_path(tmp_path).read_bytes()

    again = pp_pipeline.advance(prep, tmp_path, mode="nightly", write=True,
                                require_nightly_lane=False, cap=SESSIONS)
    assert again["stats"]["completion"]["completed"] == 0
    assert again["stats"]["completion"]["candidates"] == 0
    assert pp_ledger.ledger_path(tmp_path).read_bytes() == ledger_bytes
    assert pp_completion.receipts_path(tmp_path).read_bytes() == receipt_bytes


def test_existing_receipt_lines_survive_a_later_append_byte_for_byte(tmp_path):
    """(f) the file is append-only: earlier lines are never rewritten or moved,
    and a file missing its final newline is not fused onto."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    panel = _last_session_shock(data_dir)
    next_panel = _next_session_after_shock()

    sentinel = json.dumps({k: v for k, v in zip(
        pp_completion.RECEIPT_FIELDS,
        ["ZZZ", "2026-08-11", "down", 0.5, "2026-08-12T22:31:00Z", "0" * 64,
         ENGINE_VERSION])}, ensure_ascii=False)
    p = pp_completion.receipts_path(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(sentinel, encoding="utf-8")          # deliberately no newline
    before = p.read_bytes()

    write_vix(data_dir, through=COMPLETION_T0_POS)
    _advance(panel, data_dir, tmp_path, mode="nightly", cap=SESSIONS)
    write_vix(data_dir, through=COMPLETION_FIRST_N)
    _advance(next_panel, data_dir, tmp_path, mode="nightly", cap=SESSIONS)

    after = p.read_bytes()
    assert after.startswith(before)
    lines = _receipt_lines(tmp_path)
    assert len(lines) == 2
    assert lines[0] == sentinel
    assert json.loads(lines[1])["ticker"] == "AAA"


def test_completion_moves_no_column_other_than_vix_pctile(tmp_path):
    """(g) equal second-night producers differ only in the completion field.

    The second session legitimately grades fwd1, so comparing night 1 with
    night 2 would conflate the immutable completion exception with ordinary
    maturity.  Instead compare two identical night-2 ledgers: one while FRED
    still lacks t0, and one after the exact t0 close arrives.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    panel = _last_session_shock(data_dir)
    next_panel = _next_session_after_shock()
    waiting_root = tmp_path / "waiting"
    completed_root = tmp_path / "completed"
    write_vix(data_dir, through=COMPLETION_T0_POS)
    _advance(panel, data_dir, waiting_root, mode="nightly", cap=SESSIONS)
    _advance(panel, data_dir, completed_root, mode="nightly", cap=SESSIONS)

    _, waiting = _advance(
        next_panel, data_dir, waiting_root, mode="nightly", cap=SESSIONS,
    )

    write_vix(data_dir, through=COMPLETION_FIRST_N)
    _, completed = _advance(
        next_panel, data_dir, completed_root, mode="nightly", cap=SESSIONS,
    )
    before = waiting["ledger"]
    after = completed["ledger"]

    assert len(before) == len(after) == 1
    others = [c for c in pp_ledger.LEDGER_COLUMNS if c != "vix_pctile"]
    pd.testing.assert_frame_equal(before[others], after[others])
    assert pd.isna(before.iloc[0]["vix_pctile"])
    assert np.isfinite(after.iloc[0]["vix_pctile"])


def test_complete_vix_stamps_refuses_anything_but_a_null_stamp(tmp_path):
    """The seam is structural, not conventional: it raises rather than drift."""
    rows = []
    for i, tic in enumerate(("AAA", "BBB")):
        r = {c: None for c in pp_ledger.LEDGER_COLUMNS}
        r.update({"date": pd.Timestamp("2026-08-11"), "ticker": tic, "side": "down",
                  "era": "forward", "vix_pctile": None if i == 0 else 0.42})
        rows.append(r)
    df = pp_ledger._coerce(pd.DataFrame(rows))

    ok = [{"pos": 0, "ticker": "AAA", "date": "2026-08-11", "side": "down",
           "vix_pctile": 0.87}]
    out = pp_ledger.complete_vix_stamps(df, ok)
    assert float(out.iloc[0]["vix_pctile"]) == pytest.approx(0.87)
    assert float(out.iloc[1]["vix_pctile"]) == pytest.approx(0.42)
    others = [c for c in pp_ledger.LEDGER_COLUMNS if c != "vix_pctile"]
    pd.testing.assert_frame_equal(df[others], out[others])

    # A non-null stamp is immutable — even when the plan names it explicitly.
    with pytest.raises(AssertionError, match="immutable"):
        pp_ledger.complete_vix_stamps(df, [{"pos": 1, "ticker": "BBB",
                                            "date": "2026-08-11", "side": "down",
                                            "vix_pctile": 0.9}])
    # A stale plan pointing at the wrong row raises rather than stamping it.
    with pytest.raises(AssertionError, match="plan says"):
        pp_ledger.complete_vix_stamps(df, [{"pos": 0, "ticker": "BBB",
                                            "date": "2026-08-11", "side": "down",
                                            "vix_pctile": 0.9}])
    with pytest.raises(AssertionError, match="outside the ledger"):
        pp_ledger.complete_vix_stamps(df, [{"pos": 9, "ticker": "AAA",
                                            "date": "2026-08-11", "side": "down",
                                            "vix_pctile": 0.9}])
    # And the caller's frame was never mutated in place.
    assert pd.isna(df.iloc[0]["vix_pctile"])


def test_completion_reuses_the_shipped_vix_transform_not_a_copy(tmp_path):
    """One construction: the completing percentile IS the stamping percentile."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    write_vix(data_dir, through=SESSIONS)
    pct, sha = pp_completion.read_vix(data_dir)
    idx = pd.DatetimeIndex(_completion_dates()[SESSIONS - 30:SESSIONS])
    shipped = pp_context.vix_percentile(data_dir, idx)
    np.testing.assert_allclose(pct.reindex(idx).to_numpy(dtype="float64"),
                               shipped.to_numpy(dtype="float64"), rtol=0, atol=0)
    assert sha == hashlib.sha256(
        (data_dir / "fred" / "VIXCLS.parquet").read_bytes()).hexdigest()

    # A missing store is a gap, not a crash — and it plans nothing.
    empty_pct, empty_sha = pp_completion.read_vix(tmp_path / "nowhere")
    assert empty_pct.empty and empty_sha is None


def test_backfill_mode_never_completes_stamps(tmp_path):
    """The prereg names the NIGHTLY producer; a historical seed is not it."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    panel = _last_session_shock(data_dir)
    write_vix(data_dir, through=COMPLETION_T0_POS)
    _, first = _advance(panel, data_dir, tmp_path, mode="backfill")
    assert pd.isna(first["ledger"].iloc[0]["vix_pctile"])
    assert first["stats"]["completion"] == {}

    write_vix(data_dir, through=COMPLETION_FIRST_N)
    _, second = _advance(panel, data_dir, tmp_path, mode="backfill")
    assert second["stats"]["completion"] == {}
    assert not pp_completion.receipts_path(tmp_path).exists()


def test_receipts_are_withheld_when_the_ledger_write_is_skipped(tmp_path, monkeypatch):
    """A receipt filed against a skipped write would fence the row out of its
    own window forever — the one way this pass could destroy evidence."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    panel = _last_session_shock(data_dir)
    next_panel = _next_session_after_shock()
    write_vix(data_dir, through=COMPLETION_T0_POS)
    _advance(panel, data_dir, tmp_path, mode="nightly", cap=SESSIONS)

    write_vix(data_dir, through=COMPLETION_FIRST_N)
    prep = prep_from(next_panel, data_dir)
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    res = pp_pipeline.advance(prep, tmp_path, mode="nightly", write=True,
                              require_nightly_lane=True, cap=SESSIONS)
    assert res["stats"]["write"]["written"] is False
    assert res["stats"]["completion"] == {}  # not the sanctioned producer
    assert not pp_completion.receipts_path(tmp_path).exists()
    # The stored row is untouched, so a later nightly still completes it.
    assert pd.isna(pp_ledger.read_ledger(tmp_path).iloc[0]["vix_pctile"])


def test_a_receipted_row_is_fenced_off_from_a_second_completion(tmp_path):
    """Belt and braces on top of the null-stamp gate."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    panel = _last_session_shock(data_dir)
    next_panel = _next_session_after_shock()
    write_vix(data_dir, through=COMPLETION_T0_POS)
    _advance(panel, data_dir, tmp_path, mode="nightly", cap=SESSIONS)

    t0 = _completion_dates()[COMPLETION_T0_POS]
    pp_completion.append_receipts(tmp_path, [{
        "ticker": "AAA", "date": str(t0.date()), "side": "down",
        "vix_pctile": 0.31, "observed_at": "2026-08-12T22:31:00Z",
        "vixcls_sha256": "0" * 64, "engine_version": ENGINE_VERSION}])

    write_vix(data_dir, through=COMPLETION_FIRST_N)
    _, res = _advance(next_panel, data_dir, tmp_path, mode="nightly", cap=SESSIONS)
    cstats = res["stats"]["completion"]
    assert cstats["candidates"] == 1 and cstats["skipped_receipted"] == 1
    assert cstats["completed"] == 0
    assert pd.isna(res["ledger"].iloc[0]["vix_pctile"])
    assert len(_receipt_lines(tmp_path)) == 1


def test_malformed_or_duplicate_receipt_evidence_fails_closed(tmp_path):
    p = pp_completion.receipts_path(tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text('{"ticker":"AAA"}\n', encoding="utf-8")
    with pytest.raises(pp_completion.CompletionReceiptError, match="fields/order"):
        pp_completion.read_receipts(tmp_path)

    p.unlink()
    rec = {
        "ticker": "AAA", "date": "2026-08-11", "side": "down",
        "vix_pctile": 0.31, "observed_at": "2026-08-12T22:31:00Z",
        "vixcls_sha256": "0" * 64, "engine_version": ENGINE_VERSION,
    }
    assert pp_completion.append_receipts(tmp_path, [rec]) == 1
    before = p.read_bytes()
    with pytest.raises(pp_completion.CompletionReceiptError, match="duplicate"):
        pp_completion.append_receipts(tmp_path, [rec])
    assert p.read_bytes() == before


def test_receipt_append_failure_rolls_back_the_completed_ledger(tmp_path, monkeypatch):
    """The broad nightly commit must never see a stamp without its receipt."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    panel = _last_session_shock(data_dir)
    next_panel = _next_session_after_shock()
    write_vix(data_dir, through=COMPLETION_T0_POS)
    _advance(panel, data_dir, tmp_path, mode="nightly", cap=SESSIONS)
    before = pp_ledger.ledger_path(tmp_path).read_bytes()

    write_vix(data_dir, through=COMPLETION_FIRST_N)
    prep = prep_from(next_panel, data_dir)
    monkeypatch.setattr(
        pp_completion, "append_receipts",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )
    with pytest.raises(OSError, match="disk full"):
        pp_pipeline.advance(
            prep, tmp_path, mode="nightly", write=True,
            require_nightly_lane=False, cap=SESSIONS,
        )

    assert pp_ledger.ledger_path(tmp_path).read_bytes() == before
    assert pd.isna(pp_ledger.read_ledger(tmp_path).iloc[0]["vix_pctile"])
    assert not pp_completion.receipts_path(tmp_path).exists()


# ---------------------------------------------------------------------------
# ordering, artifact, base rates
# ---------------------------------------------------------------------------

def test_display_order_is_recency_then_ticker_never_magnitude():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-05"]),
        "ticker": ["ZZZ", "MMM", "AAA"],
        "side": ["down"] * 3,
        "resid_z": [-9.9, -3.1, -8.8],
    })
    out = pp_ledger.display_order(df)
    assert list(out["ticker"]) == ["AAA", "MMM", "ZZZ"]
    # The biggest |z| is NOT first — that would be a ranking.
    assert out.iloc[0]["resid_z"] != df["resid_z"].min()


def test_artifact_shape_authority_and_ordering(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    write_stores(data_dir)
    rets = default_returns()
    for t in ("AAB", "AAC"):
        rets[t][SESSIONS - 1] = -0.18
    rets["AAA"][SESSIONS - 1] = -0.22
    panel = build_panel_frames(rets, volumes={t: {SESSIONS - 1: 5.0}
                                              for t in ("AAA", "AAB", "AAC")}
                               | {"AAA": {SHOCK_POS: 5.0, SESSIONS - 1: 5.0}})
    prep, res = _advance(panel, data_dir, tmp_path, mode="nightly", cap=SESSIONS)

    payload = pp_artifact.build(res["ledger"], root=tmp_path,
                                panel_names=prep["panel_names"],
                                panel_span=prep["panel_span"],
                                design=pp_detect.constants(),
                                base_rates=None,
                                sector_covered_share=prep["sector_covered_share"],
                                allow_live_drivers=False)
    assert payload["schema"] == "price_pressure.v1"
    assert payload["asof"] == str(prep["sessions"][-1].date())
    assert payload["display_only"] is True
    assert payload["authority"] == {"can_rank": False, "can_size": False,
                                    "can_gate": False, "can_originate_signal": False,
                                    "can_escalate": False}
    assert all(v is False for v in payload["authority"].values())
    assert isinstance(payload["gaps"], list)
    assert "base_rates: frozen tables absent — run the backfill" in payload["gaps"]

    cov = payload["coverage"]
    for key in ("panel_names", "panel_span", "sector_covered_share",
                "edgar_covered_share", "peer_basis_shares", "era_counts"):
        assert key in cov

    down = [e for e in payload["open_events"] if e["side"] == "down"]
    assert down, payload["open_events"]
    assert [e["ticker"] for e in down] == sorted(e["ticker"] for e in down)
    for e in down:
        for key in ("ticker", "side", "date", "ret", "resid", "resid_z",
                    "vol_multiple", "peer_basis", "peer_ret", "basket",
                    "basket_en", "basket_zh", "basket_ret", "family", "state",
                    "state_pending", "retrace_frac", "days_open"):
            assert key in e, key
        assert e["family"] in pp_context.FAMILIES
        # peer_ret is present on every row; peer_basis decides how it may be
        # SPOKEN, and "peers" is never the word on a market-basis row.
        assert e["comparison"] == ("sector peers" if e["peer_basis"] == "sector"
                                   else "the market")

    txt = json.dumps(payload, ensure_ascii=False).lower()
    assert "validated" not in txt
    for banned in ("bounce", "dead-cat", "giveback", "manipulat"):
        assert banned not in txt

    p = pp_artifact.write(payload, tmp_path)
    assert json.loads(p.read_text(encoding="utf-8"))["schema"] == "price_pressure.v1"


def test_artifact_events_cap_and_more_counter(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    write_stores(data_dir)
    df = pp_ledger.empty_ledger()
    rows = []
    for i in range(15):
        r = {c: None for c in pp_ledger.LEDGER_COLUMNS}
        r.update({"date": pd.Timestamp("2026-01-05"), "ticker": f"T{i:02d}",
                  "side": "down", "era": "forward", "family": "no-filing",
                  "peer_basis": "sector", "resid_z": -3.0 - i, "state": "HOLDING",
                  "edgar_covered": True, "closed": False, "truncated": False,
                  "first_of_episode": True})
        rows.append(r)
    df = pp_ledger._coerce(pd.DataFrame(rows))
    payload = pp_artifact.build(df, root=tmp_path, panel_names=10,
                                panel_span=("2023-01-02", "2026-01-05"),
                                design={}, base_rates=None,
                                allow_live_drivers=False)
    ev = payload["open_events"]
    meta = payload["open_events_meta"]
    assert len(ev) == 12 and meta["total"]["down"] == 15 and meta["more"]["down"] == 3
    # Alphabetical within the day, so the 12 kept are T00..T11 — not the biggest z.
    assert [e["ticker"] for e in ev] == [f"T{i:02d}" for i in range(12)]


def test_stale_day_never_borrows_a_today_banner(tmp_path):
    """Historical breadth remains a fact, but it must not speak as "today"."""
    ledger = pd.DataFrame({
        "date": [pd.Timestamp("2020-01-02")],
        "side": ["down"],
        "panel_shock_count": [12.0],
        "panel_share_z2": [0.20],
        "spy_ret_z": [-2.0],
    })
    gaps = []
    day = pp_artifact._day_block(
        ledger,
        tmp_path,
        {"day_facts": {"panel_shock_count_p90": 3.0}},
        gaps,
        allow_live_drivers=False,
    )
    assert day["broad_selloff"] is True
    assert day["banner"] is None
    assert day["character"] is None
    assert any("not the current day" in gap for gap in gaps)


def test_base_rates_cells_carry_ci_episode_n_and_dates(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    write_stores(data_dir)
    rets = default_returns()
    for t, pos in (("AAB", 60), ("AAC", 80), ("AAD", 120), ("BBA", 140)):
        rets[t][pos] = -0.20
    panel = build_panel_frames(rets, volumes={"AAA": {SHOCK_POS: 5.0},
                                              "AAB": {60: 5.0}, "AAC": {80: 5.0},
                                              "AAD": {120: 5.0}, "BBA": {140: 5.0}})
    prep, res = _advance(panel, data_dir, tmp_path)
    payload = pp_base.build(res["ledger"], panel_names=prep["panel_names"],
                            span=prep["panel_span"], design=pp_detect.constants())
    assert payload["schema"] == "price_pressure.base_rates.v1"
    assert payload["authority"] == pp_base.AUTHORITY
    assert "0/10 contrasts" in payload["null_contrast_statement"]
    assert "KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER" in payload["null_contrast_statement"]
    assert payload["headline_horizons"] == [5, 21]

    cellall = payload["tables"]["down"]["21"]["ALL"]
    for key in ("n_events", "episode_n", "n_dates", "retrace_frac",
                "share_retraced_33pct", "share_still_lower", "terminal_shares",
                "n_open", "share_truncated", "share_delisted_or_halted"):
        assert key in cellall, key
    assert set(payload["tables"]["down"]["21"]) >= set(pp_context.FAMILIES)
    # No day-taxonomy split survived into the tables (masterplan §12 / finding 9).
    assert "systemic" not in json.dumps(payload["tables"])
    assert "broad_selloff" not in json.dumps(payload["tables"])
    # The published span is stamped and called out as span-bound.
    assert payload["coverage"]["panel_span"] == list(prep["panel_span"])
    assert "span-bound" in payload["coverage"]["span_note"]
    assert "validated" not in json.dumps(payload).lower()


def test_base_rate_honest_n_is_per_horizon(tmp_path):
    """A 5d table and a 21d table do not have the same independence problem."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    write_stores(data_dir)
    rets = default_returns()
    rets["AAA"][SHOCK_POS + 10] = -0.20       # fresh at 5d, not at 21d
    panel = build_panel_frames(rets, volumes={"AAA": {SHOCK_POS: 5.0,
                                                     SHOCK_POS + 10: 5.0}})
    _, res = _advance(panel, data_dir, tmp_path)
    led = res["ledger"]
    assert len(led) == 2
    c5 = pp_base.cell(led[led["side"] == "down"], 5)
    c21 = pp_base.cell(led[led["side"] == "down"], 21)
    assert c5["n_events"] == c21["n_events"] == 2
    assert c5["episode_n"] == 2
    assert c21["episode_n"] == 1


# ---------------------------------------------------------------------------
# script entry
# ---------------------------------------------------------------------------

def test_missing_store_annotates_at_line_start_and_exits_zero(tmp_path):
    """House annotation law: bare print, '::' first on the line, exit 0."""
    data_dir = tmp_path / "data"
    (data_dir / "massive_stock_day").mkdir(parents=True)
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.build_price_pressure",
         "--data-root", str(data_dir)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT), "TZ": "UTC",
             "HOME": str(tmp_path)},
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    hits = [ln for ln in proc.stdout.splitlines()
            if ln.startswith("::warning title=price-pressure-store-stale::")]
    assert hits, proc.stdout
    assert not pp_ledger.ledger_path(data_dir).exists()
    assert not pp_artifact.artifact_path(data_dir).exists()


# ---------------------------------------------------------------------------
# ledger restore gate (events.parquet is R2-canonical since 2026-08-11)
# ---------------------------------------------------------------------------
#
# The parquet is gitignored and restored by `fetch_r2 --dirs price_pressure`
# before the builder runs, so "the restore came up empty" and "the restore
# returned last month's copy" are live failure modes that git used to make
# impossible.  Unguarded they are SILENT: read_ledger answers an absent or torn
# parquet with an empty typed frame, so the nightly would harvest its catch-up
# window against nothing, write a few hundred rows over the 35k-row history, and
# publish that back as the new canonical ledger.  The gate compares the restored
# parquet's newest event date against the git-TRACKED latest.json asof, which the
# same run writes from `ledger["date"].max()`.

def _synthetic_bar_store(data_dir: Path, tickers: tuple[str, ...] = ("AAA", "AAB")) -> Path:
    """A `massive_stock_day` tree just real enough to clear the BAR-store gate.

    That gate is ``store.glob("*.parquet")`` plus an optional ``_manifest.json``
    staleness read — writing no manifest means no staleness measure, which is what
    carries these tests past it and onto the ledger gate under test.
    """
    store = data_dir / "massive_stock_day"
    store.mkdir(parents=True, exist_ok=True)
    idx = _dates(30)
    for t in tickers:
        pd.DataFrame({"date": idx, "open": 100.0, "high": 101.0, "low": 99.0,
                      "close": 100.0, "volume": 1e6}).to_parquet(
                          store / f"{t}.parquet", index=False)
    return store


def _tracked_artifact(data_dir: Path, asof: str) -> Path:
    """The git-tracked sidecar the gate treats as truth."""
    d = data_dir / "price_pressure"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "latest.json"
    p.write_text(json.dumps({"schema": "price_pressure.v1", "asof": asof}),
                 encoding="utf-8")
    return p


def _restored_ledger(data_dir: Path, max_date: str) -> Path:
    """A restored events.parquet whose newest row lands on ``max_date``."""
    df = pd.DataFrame({"date": pd.to_datetime([max_date]), "ticker": ["AAA"],
                       "side": ["down"], "era": ["forward"]})
    pp_ledger.write_ledger(df, data_dir, require_nightly_lane=False)
    return pp_ledger.ledger_path(data_dir)


def _run_builder(data_dir: Path, tmp_path: Path):
    return subprocess.run(
        [sys.executable, "-m", "scripts.build_price_pressure",
         "--data-root", str(data_dir)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT), "TZ": "UTC",
             "HOME": str(tmp_path)},
    )


def test_absent_restored_ledger_refuses_and_leaves_artifacts_untouched(tmp_path):
    """(a) No events.parquet — the failed-restore shape.  Refuse, do not re-fork."""
    data_dir = tmp_path / "data"
    _synthetic_bar_store(data_dir)
    artifact = _tracked_artifact(data_dir, "2026-07-02")
    before = artifact.read_bytes()

    proc = _run_builder(data_dir, tmp_path)

    assert proc.returncode == 0, proc.stderr[-2000:]
    hits = [ln for ln in proc.stdout.splitlines()
            if ln.startswith("::warning title=price-pressure-ledger-stale::")]
    assert hits, proc.stdout
    # The annotation must NAME both dates — a warning that says "stale" without the
    # numbers cannot be triaged from the Actions summary alone.
    assert "none" in hits[0] and "2026-07-02" in hits[0], hits[0]
    # Artifacts untouched: no ledger conjured from nothing, sidecar byte-identical.
    assert not pp_ledger.ledger_path(data_dir).exists()
    assert artifact.read_bytes() == before


def test_restored_ledger_older_than_the_tracked_asof_refuses(tmp_path):
    """(b) A stale/partial restore: last month's parquet under this month's asof."""
    data_dir = tmp_path / "data"
    _synthetic_bar_store(data_dir)
    artifact = _tracked_artifact(data_dir, "2026-07-02")
    ledger = _restored_ledger(data_dir, "2026-06-01")
    art_before, led_before = artifact.read_bytes(), ledger.read_bytes()

    proc = _run_builder(data_dir, tmp_path)

    assert proc.returncode == 0, proc.stderr[-2000:]
    hits = [ln for ln in proc.stdout.splitlines()
            if ln.startswith("::warning title=price-pressure-ledger-stale::")]
    assert hits, proc.stdout
    assert "2026-06-01" in hits[0] and "2026-07-02" in hits[0], hits[0]
    assert artifact.read_bytes() == art_before
    assert ledger.read_bytes() == led_before


def test_restored_ledger_at_or_past_the_tracked_asof_proceeds(tmp_path):
    """(c) A healthy restore must NOT be refused — at the asof, or past it."""
    for max_date in ("2026-07-02", "2026-07-31"):
        data_dir = tmp_path / max_date / "data"
        _tracked_artifact(data_dir, "2026-07-02")
        _restored_ledger(data_dir, max_date)
        st = pp_ledger.restore_status(data_dir)
        assert st["ok"], (max_date, st)
        assert st["reason"] is None
        assert st["ledger_max"] == max_date
        assert st["artifact_asof"] == "2026-07-02"

    # …and the builder actually gets past the gate on that state.  The synthetic
    # bar store cannot carry the run to completion, which is fine and deliberate:
    # the contract under test is that NEITHER refuse-to-run gate fired.  Asserting
    # on both is what stops this from going vacuous — a test that only checked the
    # ledger annotation would still pass if the bar gate started refusing first,
    # and would then be pinning nothing at all.
    data_dir = tmp_path / "wired" / "data"
    _synthetic_bar_store(data_dir)
    _tracked_artifact(data_dir, "2026-07-02")
    _restored_ledger(data_dir, "2026-07-02")
    proc = _run_builder(data_dir, tmp_path)
    refusals = [ln for ln in proc.stdout.splitlines()
                if ln.startswith("::warning title=price-pressure-store-stale::")
                or ln.startswith("::warning title=price-pressure-ledger-stale::")]
    assert not refusals, proc.stdout


def test_restore_status_refuses_a_zero_row_ledger(tmp_path):
    """An empty-but-present parquet is the other half of a failed restore."""
    data_dir = tmp_path / "data"
    _tracked_artifact(data_dir, "2026-07-02")
    pp_ledger.write_ledger(pp_ledger.empty_ledger(), data_dir,
                           require_nightly_lane=False)
    st = pp_ledger.restore_status(data_dir)
    assert not st["ok"]
    assert st["rows"] == 0
    assert "no dated rows" in st["reason"]


def test_restore_status_is_tolerant_only_where_there_is_nothing_to_compare(tmp_path):
    """No tracked asof = the genuine pre-seed state, not evidence of staleness."""
    data_dir = tmp_path / "data"
    _restored_ledger(data_dir, "2026-07-02")
    st = pp_ledger.restore_status(data_dir)     # no latest.json at all
    assert st["ok"] and st["artifact_asof"] is None

    (data_dir / "price_pressure" / "latest.json").write_text(
        json.dumps({"schema": "price_pressure.v1", "asof": None}), encoding="utf-8")
    assert pp_ledger.restore_status(data_dir)["ok"]

    # …but a MISSING parquet is refused even with no artifact to compare to: the
    # tolerance is about the comparison, never about the ledger existing.
    pp_ledger.ledger_path(data_dir).unlink()
    (data_dir / "price_pressure" / "latest.json").unlink()
    assert not pp_ledger.restore_status(data_dir)["ok"]


def test_ledger_is_registered_as_an_r2_data_dir_store(tmp_path):
    """The parquet is gitignored, so the R2 registry IS its delivery path.

    fetch_r2 imports this same registry (`from scripts.publish_r2 import _DATA_DIRS`),
    so one entry wires both legs.  The floors are what stop a bare checkout — the two
    tracked sidecars, no parquet — from being published over the canonical store.
    """
    from scripts import publish_r2

    assert "price_pressure" in publish_r2._DATA_DIRS
    assert "price_pressure" not in publish_r2.DEFAULT_DIRS   # gated nightly lane only
    assert "price_pressure" not in publish_r2._APPEND_ONLY_DIRS  # legitimate whole rewrite

    sidecars_only = publish_r2._data_dir_syncable("price_pressure", 2, 73_000)
    assert not sidecars_only[0], sidecars_only
    # The count alone stops being sharp once completion_receipts.jsonl is committed;
    # the bytes floor is what still refuses that tree.
    with_receipts = publish_r2._data_dir_syncable("price_pressure", 3, 80_000)
    assert not with_receipts[0], with_receipts
    assert publish_r2._data_dir_syncable("price_pressure", 3, 11_400_000)[0]


def test_backfill_requires_an_explicit_panel_cache(tmp_path):
    from scripts import build_price_pressure as mod

    rc = mod.main(["--backfill", "--data-root", str(tmp_path)])
    assert rc == 1


def test_artifact_emits_the_surface_parity_schema(tmp_path):
    """PR #5266's loader reads these exact names — pin them, they are a contract."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    write_stores(data_dir)
    panel = build_panel_frames(default_returns(), volumes={"AAA": {SHOCK_POS: 5.0}})
    prep, res = _advance(panel, data_dir, tmp_path)
    frozen = pp_base.build(res["ledger"], panel_names=prep["panel_names"],
                           span=prep["panel_span"], design=pp_detect.constants(),
                           day_facts={"panel_shock_count_p90": 3.0})
    payload = pp_artifact.build(res["ledger"], root=tmp_path,
                                panel_names=prep["panel_names"],
                                panel_span=prep["panel_span"],
                                design=pp_detect.constants(), base_rates=frozen,
                                sector_covered_share=prep["sector_covered_share"],
                                allow_live_drivers=False)
    for key in ("schema", "asof", "authority", "gaps", "open_events",
                "recently_resolved", "base_rates", "coverage", "day", "provenance"):
        assert key in payload, key
    assert payload["schema"] == "price_pressure.v1"
    for key in ("panel_names", "sector_basis_share", "edgar_covered_share"):
        assert key in payload["coverage"], key
    for key in ("banner", "panel_shock_count"):
        assert key in payload["day"], key
    br = payload["base_rates"]
    for key in ("span", "note_en", "note_zh", "down", "up"):
        assert key in br, key
    for side in ("down", "up"):
        for key in ("n_events", "h5_median_retrace", "h21_share_recovered",
                    "h21_share_partial", "h21_share_accepted_lower",
                    "h21_share_delisted"):
            assert key in br[side], (side, key)
    assert br["note_zh"] and any("\u4e00" <= c <= "\u9fff" for c in br["note_zh"])
    assert payload["provenance"]["study"].endswith("liquidity-shock-reversal-phase0.md")
    assert "study_title" in payload["provenance"]

    for row in payload["recently_resolved"]:
        for key in ("ticker", "side", "date", f"terminal_state_{TERMINAL_PRIMARY}d",
                    "ret", "resid", "family"):
            assert key in row, key


def test_up_side_terminal_slots_are_mirrored_not_renamed(tmp_path):
    """The same measurement under mirrored names: ≥80% back / <33% back."""
    labels = pp_base._TERMINAL_SLOTS
    assert labels["down"]["recovered"] == "RECOVERED"
    assert labels["up"]["recovered"] == "GAVE_BACK"
    assert labels["down"]["accepted_lower"] == "ACCEPTED_LOWER"
    assert labels["up"]["accepted_lower"] == "KEPT"
