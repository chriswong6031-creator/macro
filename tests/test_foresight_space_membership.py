"""The Foresight Desk's `space_satellite` membership, and the turn-state map (W-D).

Charter: research/PROPHET_US_MISSED_IGNITIONS_MASTERPLAN_BY_FABLE.md §W-D.2-3
(defect D15 / D19).

D15: the desk's space theme was six defense primes — IRDM, GD, LHX, RTX, HWM,
BWXT — so a desk whose whole job is anticipating a theme before price moves was
structurally blind to new-space. RKLB/ASTS/LUNR/PL/RDW could load and re-rate
without the desk holding an opinion at all. Widening a membership is cheap; what
is NOT cheap is a leg that raises on a name it has no data for, because the desk
would then go dark for the whole theme rather than for the names it cannot see.
So the second test is the load-bearing one: coverage falls HONESTLY and every
stage-driving field is untouched.

D19: `_basket_turn_map` is the input to the caution dual-read. Its rule is quoted
from the cycle engine, not invented, and this pins the quote.
"""

from __future__ import annotations

import pandas as pd
import pytest

from lib import config

NEW_SPACE = ("RKLB", "ASTS", "LUNR", "PL", "RDW")
PRIMES = ("IRDM", "GD", "LHX", "RTX", "HWM", "BWXT")


def _space_theme() -> dict:
    themes = (config.load() or {}).get("themes") or {}
    assert "space_satellite" in themes, "the desk's space theme vanished from config"
    return themes["space_satellite"]


def test_the_desk_can_see_new_space():
    """The five names the Foresight Desk was blind to are in the theme."""
    tickers = _space_theme().get("tickers") or []
    missing = [t for t in NEW_SPACE if t not in tickers]
    assert missing == [], f"the desk is still blind to {missing}"


def test_the_primes_were_not_traded_away_for_them():
    """A widening, not a swap: the launch-and-constellation cohort is ADDED to
    the prime contractors, because both are the theme."""
    tickers = _space_theme().get("tickers") or []
    dropped = [t for t in PRIMES if t not in tickers]
    assert dropped == [], f"prime contractors dropped from the theme: {dropped}"
    assert len(tickers) == len(set(tickers)), "duplicate ticker in the theme"


def test_a_leg_degrades_to_null_for_a_name_it_cannot_see():
    """The whole risk of widening a membership, pinned on the real revisions leg.

    Names with no analyst coverage must fall out of the covered set and out of
    the numbers computed from it — they must NOT raise, and they must not drag a
    stage-driving field with them. `coverage` is the one figure that MOVES, and
    it moves in the honest direction: the desk now says it reads a smaller share
    of a bigger theme (2/6 → 2/11) instead of quietly implying it reads all of it.
    """
    from engine import theme_revisions

    latest = theme_revisions._latest()
    if latest is None:
        pytest.skip("revisions cache not collected in this checkout")
    hist = theme_revisions._history()

    old = theme_revisions.theme_revisions_for(
        "space_satellite", "Space & Satellites", list(PRIMES), latest, hist)
    new = theme_revisions.theme_revisions_for(
        "space_satellite", "Space & Satellites", list(PRIMES) + list(NEW_SPACE),
        latest, hist)
    if old is None or new is None:
        pytest.skip("no revisions rows for this theme in this checkout")

    # Nothing the stage machine reads may move on a membership widening alone.
    for field in ("breadth", "breadth_cov", "level_state", "broadening_state",
                  "est_drift_90d", "net_up_total"):
        assert old.get(field) == new.get(field), f"{field} moved on a membership widening"
    # The covered set is unchanged; only the denominator grew.
    assert ([m["ticker"] for m in (old.get("members") or [])]
            == [m["ticker"] for m in (new.get("members") or [])])
    assert new["n_members"] == old["n_members"] + len(NEW_SPACE)
    assert new["coverage"] < old["coverage"], (
        "coverage must FALL and say so — a widened theme the desk cannot see more "
        "of is exactly the disclosure this field exists to make")


def test_an_uncovered_name_is_filtered_out_rather_than_raising():
    """The same guarantee as above, with NO dependence on a collected cache.

    The test above reads the real revisions store and skips where a checkout has
    not collected one — CI packs install minimal deps, so a gate that exists only
    in that form is dark exactly where it most needs to be lit. This twin builds
    the frame itself, so the "a widened membership must not break a leg" contract
    is pinned unconditionally.
    """
    from engine import theme_revisions

    latest = pd.DataFrame(
        {"n_analysts": [13, 7], "breadth": [0.39, 0.43],
         "est_chg_90d": [-0.3, 0.5], "net_up_30d": [4.0, 4.0],
         "n_covering": [13, 15]},
        index=pd.Index(["LHX", "BWXT"], name="ticker"))

    old = theme_revisions.theme_revisions_for(
        "space_satellite", "Space & Satellites", list(PRIMES), latest, None)
    new = theme_revisions.theme_revisions_for(
        "space_satellite", "Space & Satellites", list(PRIMES) + list(NEW_SPACE),
        latest, None)
    assert old is not None and new is not None
    assert old["breadth"] == new["breadth"]
    assert ([m["ticker"] for m in old["members"]]
            == [m["ticker"] for m in new["members"]] == ["LHX", "BWXT"])
    assert (old["n_members"], new["n_members"]) == (6, 11)
    assert new["coverage"] < old["coverage"]


# ── the turn-state map (the caution dual-read's input) ──────────────────────
def _log(rows):
    return pd.DataFrame(rows, columns=["date", "id", "name", "phase", "pos", "osc_slope"])


def _turn_map(tmp_path, monkeypatch, rows):
    from scripts import build_stock_library as bsl

    d = tmp_path / "sector_cycles"
    d.mkdir(parents=True, exist_ok=True)
    _log(rows).to_parquet(d / "forward_log.parquet")
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    return bsl._basket_turn_map()


def test_the_turn_map_quotes_the_cycle_engines_own_bottoming_rule(tmp_path, monkeypatch):
    """`phase == "Trough" AND osc_slope > 0` — the CN bottoming_watch rule
    character for character (engine/china_act_now.py:352-359)."""
    out = _turn_map(tmp_path, monkeypatch, [
        ("2026-08-04", "b-gold_miners", "Gold Miners", "Trough", 2.0, 1.3),
        ("2026-08-04", "b-space_economy", "Space Economy", "Trough", 2.1, -33.4),
        ("2026-08-04", "b-travel", "Travel", "Downturn", 67.8, 21.7),
        ("2026-08-04", "b-flat", "Flat", "Trough", 5.0, 0.0),
    ])
    assert set(out) == {"gold_miners"}
    assert out["gold_miners"] == {"name": "Gold Miners", "pos": 2.0, "osc_slope": 1.3}


def test_a_still_falling_oscillator_is_not_a_turn(tmp_path, monkeypatch):
    """The ASTS case. `b-space_economy` sits at Trough pos 2.1 on 2026-08-04 —
    deep in the washout — but its oscillator slope is −33.4 and has been negative
    on EVERY date in the committed forward log. Being at a low is not turning."""
    out = _turn_map(tmp_path, monkeypatch, [
        ("2026-08-04", "b-space_economy", "Space Economy", "Trough", 2.1, -33.4)])
    assert out == {}


def test_only_the_latest_row_per_basket_decides(tmp_path, monkeypatch):
    """The log is append-only and point-in-time: a turn that has since rolled
    over must not keep printing off a stale row."""
    out = _turn_map(tmp_path, monkeypatch, [
        ("2026-07-28", "b-x", "X", "Trough", 3.0, 5.0),     # was turning
        ("2026-08-04", "b-x", "X", "Trough", 2.0, -4.0),    # no longer
    ])
    assert out == {}


def test_sector_etf_rows_are_not_basket_memberships(tmp_path, monkeypatch):
    """Only `b-` rows key a basket slug; a bare sector ETF id would collide with
    nothing and silently never match a membership anyway."""
    out = _turn_map(tmp_path, monkeypatch, [
        ("2026-08-04", "xlc", "Communication Services", "Trough", 6.3, 5.1)])
    assert out == {}


def test_a_missing_log_degrades_to_no_disclosure(tmp_path, monkeypatch):
    """Best-effort: the caution then reads exactly as it read before W-D.3."""
    from scripts import build_stock_library as bsl

    monkeypatch.setattr(config, "data_dir", lambda: tmp_path / "nope")
    assert bsl._basket_turn_map() == {}
