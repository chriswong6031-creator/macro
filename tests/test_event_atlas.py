"""Tests for engine/event_atlas.py — Signal Episode Atlas W2 (sea.v1).

Covers:
- cell aggregation: matured-only n, n_names, n_distinct_years, win rates
- era split: every cell reports pooled AND post2010 (DT-R16 #1751)
- shrinkage math with the K literals PINNED IN THE TEST (a test that reads its
  own expected constant from the module cannot catch the constant moving)
- n=0 → the receipt falls back to the cohort posterior; large n → the name's own
- receipt carries every component n + the survivorship/clustering caveats
- era_note fires only on a POOLED-vs-POST2010 sign divergence
- live_state: latest event per grid, live-freshness, current alignment
- atlas JSON schema: display tier, masterplan citation, no per-name grain
- the notifier's alignment suffix clears the forbidden-words guard
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine import event_atlas as ea
from engine import stock_events as se

_SRC_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Synthetic library
# ---------------------------------------------------------------------------

def _ev(
    ticker: str,
    date: str,
    *,
    grid: str = "W",
    direction: str = "bull",
    depth_class: str = "washout",
    level: str = "below_zero",
    wlc: str = "medium",
    align: int = 2,
    archetype: str = "cyclical",
    sector: str = "us_sector_tech",
    fwd13: float | None = 0.05,
    fwd26: float | None = 0.10,
    exc13: float | None = 0.02,
    exc26: float | None = 0.04,
) -> dict:
    era = "pre2010" if pd.Timestamp(date) < se.ERA_BREAK else "post2010"
    return {
        "ticker": ticker, "grid": grid, "date": pd.Timestamp(date),
        "direction": direction, "era": era,
        "depth_pctile": 5.0, "depth_window_n": 520, "depth_class": depth_class,
        "level": level, "washout_len": 10, "washout_len_class": wlc,
        "align_class": align, "hist_vel3": 0.1, "stoch_k": 20.0, "stoch_d": 18.0,
        "drawdown_pct": -20.0, "close": 100.0, "line": -5.0, "sig": -5.1,
        "archetype_at_event": archetype, "sector": sector,
        "regime_vix_pctile": 0.4, "regime_spy_above_200d": True,
        "regime_bucket": "lo_vix_above200",
        "fwd_13w": fwd13, "fwd_26w": fwd26, "fwd_21s": None, "fwd_63s": None,
        "exc_13w": exc13, "exc_26w": exc26, "exc_21s": None, "exc_63s": None,
        "matured_short": fwd13 is not None, "matured": fwd26 is not None,
    }


def _library(rows: list[dict]) -> pd.DataFrame:
    return se.events_frame(rows)


CLASS = {"depth_class": "washout", "level": "below_zero",
         "washout_len_class": "medium", "align_class": 2}


@pytest.fixture(autouse=True)
def _no_cache_leak():
    ea.clear_cache()
    yield
    ea.clear_cache()


# ---------------------------------------------------------------------------
# 1 — cell statistics
# ---------------------------------------------------------------------------

def test_cell_stats_counts_only_matured_rows_and_prints_the_membership():
    df = _library([
        _ev("AAA", "2015-01-02", fwd13=0.10, fwd26=0.20),
        _ev("BBB", "2015-02-06", fwd13=-0.10, fwd26=None),
        _ev("AAA", "2016-03-04", fwd13=0.30, fwd26=0.40),
        _ev("CCC", "2017-04-07", fwd13=None, fwd26=None),
    ])
    c13 = ea.cell_stats(df, "13w")
    assert c13["n_events"] == 4, "membership includes still-open windows"
    assert c13["n"] == 3, "only matured rows are behind the statistics"
    assert c13["n_names"] == 3 - 1     # AAA counted once
    assert c13["n_distinct_years"] == 2, "2017 has no matured row behind it"
    assert c13["med"] == pytest.approx(10.0)
    assert c13["win"] == pytest.approx(66.7, abs=0.1)

    c26 = ea.cell_stats(df, "26w")
    assert c26["n"] == 2 and c26["n_events"] == 4
    assert c26["med"] == pytest.approx(30.0)


def test_cell_stats_on_an_empty_cell_is_a_printed_zero_not_a_crash():
    empty = ea.cell_stats(se.events_frame([]), "13w")
    assert empty["n"] == 0 and empty["med"] is None and empty["win"] is None


def test_excess_stats_carry_their_own_n():
    df = _library([
        _ev("AAA", "2015-01-02", fwd13=0.10, exc13=0.05),
        _ev("BBB", "2015-02-06", fwd13=0.20, exc13=None),
    ])
    c = ea.cell_stats(df, "13w")
    assert c["n"] == 2 and c["n_exc"] == 1, (
        "an excess cell may be thinner than its raw cell — it must say so"
    )
    assert c["med_exc"] == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# 2 — era split (DT-R16 #1751)
# ---------------------------------------------------------------------------

def test_every_cell_reports_pooled_and_post2010():
    df = _library([
        _ev("AAA", "2005-01-07", fwd13=0.40),
        _ev("AAA", "2006-01-06", fwd13=0.40),
        _ev("BBB", "2015-01-02", fwd13=0.10),
    ])
    cells = ea.aggregate(df, "global")
    assert cells
    split = list(cells.values())[0]["13w"]
    assert set(split) == {"pooled", "post2010"}
    assert split["pooled"]["n"] == 3
    assert split["post2010"]["n"] == 1
    assert split["pooled"]["med"] != split["post2010"]["med"], (
        "the fixture must actually differ across the break, or the split is untested"
    )


def test_receipt_carries_the_post2010_sub_cell_beside_the_pooled_read():
    df = _library([_ev(f"N{i}", f"200{i}-01-05", fwd13=0.5) for i in range(1, 8)]
                  + [_ev(f"M{i}", f"201{i}-01-05", fwd13=-0.2) for i in range(1, 8)])
    r = ea.receipt("N1", "W", "bull", CLASS, df=df)
    h = r["horizons"]["13w"]
    assert "post2010" in h
    assert h["n_global"] == 14
    assert h["post2010"]["n_global"] == 7
    assert h["global"]["med"] != h["post2010"]["global"]["med"]


def test_era_note_fires_only_on_a_sign_divergence():
    # pooled positive, post-2010 negative → a note
    df = _library([_ev(f"P{i}", f"200{i}-01-05", fwd13=0.9) for i in range(1, 9)]
                  + [_ev(f"Q{i}", f"201{i}-01-05", fwd13=-0.1) for i in range(1, 4)])
    r = ea.receipt("P1", "W", "bull", CLASS, df=df)
    note = r["horizons"]["13w"]["era_note"]
    assert note and note.startswith("post-2010 reads negative on n=")

    same = _library([_ev(f"P{i}", f"200{i}-01-05", fwd13=0.4) for i in range(1, 9)]
                    + [_ev(f"Q{i}", f"201{i}-01-05", fwd13=0.3) for i in range(1, 4)])
    r2 = ea.receipt("P1", "W", "bull", CLASS, df=same)
    assert r2["horizons"]["13w"]["era_note"] is None


# ---------------------------------------------------------------------------
# 3 — shrinkage
# ---------------------------------------------------------------------------

def test_shrinkage_constants_are_the_frozen_literals():
    # LITERALS, not module reads: a test that imports its own expectation moves
    # with the mutant it exists to catch.
    assert ea.K_NAME == 12
    assert ea.K_ARCH == 50


def test_blend_weight_is_n_over_n_plus_k_hand_computed():
    child = {"n": 4, "n_exc": 4, "med": 10.0, "mean": 10.0, "win": 100.0,
             "med_exc": 10.0, "mean_exc": 10.0, "win_exc": 100.0}
    parent = {"med": 0.0, "mean": 0.0, "win": 50.0,
              "med_exc": 0.0, "mean_exc": 0.0, "win_exc": 50.0}
    out = ea.blend_cell(child, parent, 12)
    assert out["w"] == pytest.approx(4 / 16)                 # 0.25
    assert out["med"] == pytest.approx(0.25 * 10.0 + 0.75 * 0.0)
    assert out["win"] == pytest.approx(0.25 * 100.0 + 0.75 * 50.0)
    assert out["n_child"] == 4 and out["k"] == 12


def test_a_name_with_no_history_inherits_the_cohort_posterior_exactly():
    df = _library([_ev(f"OTHER{i}", f"201{i%10}-0{i%9+1}-05", fwd13=0.2, fwd26=0.3)
                   for i in range(20)])
    r = ea.receipt("NEWNAME", "W", "bull", CLASS, df=df, archetype="cyclical",
                   sector="us_sector_tech")
    h = r["horizons"]["13w"]
    assert h["n_name"] == 0
    assert h["name_post"]["w"] == 0.0
    assert h["name_post"]["med"] == h["arch_post"]["med"], (
        "with no own history the posterior IS the cohort posterior"
    )


def test_a_name_with_large_n_dominates_its_own_posterior():
    own = [_ev("BIG", f"20{10 + i // 6:02d}-{i % 6 + 1:02d}-05", fwd13=0.50)
           for i in range(60)]
    others = [_ev(f"O{i}", f"20{12 + i // 6:02d}-{i % 6 + 1:02d}-05", fwd13=-0.50)
              for i in range(60)]
    df = _library(own + others)
    r = ea.receipt("BIG", "W", "bull", CLASS, df=df)
    h = r["horizons"]["13w"]
    assert h["n_name"] == 60
    assert h["name_post"]["w"] == pytest.approx(60 / 72, abs=1e-3)
    assert h["name_post"]["med"] > 0, "an n=60 name must pull its posterior positive"
    assert h["name_post"]["med"] < h["name"]["med"], "but never all the way to raw"


def test_two_stage_blend_shrinks_the_archetype_toward_global_first():
    """A THIN archetype cell must not masquerade as a strong prior for the name."""
    thin_arch = [_ev("A1", "2015-01-02", fwd13=1.0, archetype="rare_type")]
    big_global = [_ev(f"G{i}", f"20{12 + i // 6:02d}-{i % 6 + 1:02d}-05",
                      fwd13=0.0, archetype="cyclical") for i in range(60)]
    df = _library(thin_arch + big_global)
    r = ea.receipt("A1", "W", "bull", CLASS, df=df, archetype="rare_type")
    h = r["horizons"]["13w"]
    assert h["n_archetype"] == 1
    assert h["arch_post"]["w"] == pytest.approx(round(1 / 51, 3), abs=1e-6)
    assert abs(h["arch_post"]["med"]) < 10.0, (
        "an n=1 archetype must be shrunk almost entirely toward global"
    )


# ---------------------------------------------------------------------------
# 4 — the receipt is auditable
# ---------------------------------------------------------------------------

def test_receipt_prints_every_component_n_and_the_caveats_verbatim():
    df = _library([_ev(f"N{i}", f"201{i%10}-0{i%9+1}-05") for i in range(12)]
                  + [_ev("N0", "2018-05-04")])
    r = ea.receipt("N0", "W", "bull", CLASS, df=df)
    for key in ("ticker", "grid", "direction", "class_key", "archetype", "sector",
                "k_name", "k_arch", "horizons", "caveats", "taxonomy_version"):
        assert key in r, key
    h = r["horizons"]["13w"]
    for key in ("n_name", "n_archetype", "n_sector", "n_global",
                "name", "archetype", "sector", "global", "arch_post", "name_post"):
        assert key in h, key
    assert h["n_name"] >= 1 and h["n_global"] >= h["n_name"]

    assert r["caveats"]["survivorship"] == ea.CAVEAT_SURVIVORSHIP
    assert r["caveats"]["clustering"] == ea.CAVEAT_CLUSTERING
    assert "survivor" in r["caveats"]["survivorship"].lower()
    assert "n_distinct_years" in r["caveats"]["clustering"]
    assert "date-blocked bootstrap" in r["caveats"]["clustering"]
    assert r["authority"]["may_rank"] is False


def test_an_explicitly_passed_library_is_never_served_from_the_slice_cache():
    """REGRESSION: the slice cache is keyed on the memoised library fingerprint.

    A caller that hands in its own frame must not receive a slice built from a
    different one — the first version of this cache did, and a second receipt
    over a different library silently reported the FIRST library's numbers.
    """
    lib_a = _library([_ev(f"A{i}", f"201{i}-01-05", fwd13=0.9) for i in range(1, 9)])
    lib_b = _library([_ev(f"A{i}", f"201{i}-01-05", fwd13=-0.9) for i in range(1, 9)])
    ra = ea.receipt("A1", "W", "bull", CLASS, df=lib_a)
    rb = ea.receipt("A1", "W", "bull", CLASS, df=lib_b)
    assert ra["horizons"]["13w"]["global"]["med"] == pytest.approx(90.0)
    assert rb["horizons"]["13w"]["global"]["med"] == pytest.approx(-90.0)


def test_receipt_on_an_empty_library_names_its_null():
    r = ea.receipt("AAA", "W", "bull", CLASS, df=se.events_frame([]))
    assert r["reason"] == "no_event_library"
    assert r["caveats"]["survivorship"] == ea.CAVEAT_SURVIVORSHIP


def test_receipt_is_strictly_json_serialisable():
    """It is embedded in the per-stock JSON — a numpy scalar there is a build break."""
    df = _library([_ev("AAA", f"201{i}-01-05") for i in range(1, 9)])
    r = ea.receipt("AAA", "W", "bull", CLASS, df=df)
    json.dumps(r, allow_nan=False)


# ---------------------------------------------------------------------------
# 5 — live_state
# ---------------------------------------------------------------------------

def _wavy(n: int = 900, seed: int = 7) -> pd.Series:
    rs = np.random.RandomState(seed)
    t = np.arange(n, dtype=float)
    base = 100.0 * np.exp(0.0004 * t) * (
        1.0 + 0.10 * np.sin(2 * np.pi * t / 90.0) + 0.05 * np.sin(2 * np.pi * t / 21.0)
    )
    idx = pd.bdate_range("1996-01-05", periods=n, freq="B")
    return pd.Series(base * np.exp(np.cumsum(rs.normal(0, 0.002, n))), index=idx)


def test_live_state_reports_the_latest_event_per_grid_with_freshness():
    close = _wavy(900)
    df = _library(se.extract_symbol_events("AAA", close, ctx=se.ExtractContext()))
    st = ea.live_state("AAA", close=close, df=df)
    assert st["ticker"] == "AAA"
    assert st["as_of"] == str(close.index[-1].date())
    assert set(st["grids"]) <= set(se.GRIDS) and st["grids"]

    for g, block in st["grids"].items():
        rows = df[df["grid"] == g]
        assert block["date"] == str(pd.Timestamp(rows["date"].max()).date())
        assert block["bars_since"] is not None and block["bars_since"] >= 0
        assert block["live_fresh"] == (block["bars_since"] <= ea.LIVE_FRESH_BARS)
        assert 0 <= block["align_class"] <= 2
        assert "receipt" in block and block["receipt"]["grid"] == g
    assert 0 <= st["align_now"] <= 3
    json.dumps(st, allow_nan=False)


def test_live_freshness_uses_the_grid_bar_count_not_the_wall_clock():
    close = _wavy(900)
    df = _library(se.extract_symbol_events("AAA", close, ctx=se.ExtractContext()))
    # Drop every event from the last year → nothing can still be live-fresh.
    stale = df[df["date"] < df["date"].max() - pd.Timedelta(days=365)]
    st = ea.live_state("AAA", close=close, df=stale)
    for block in st["grids"].values():
        assert block["live_fresh"] is False
        assert block["bars_since"] > ea.LIVE_FRESH_BARS


def test_live_state_on_an_unknown_name_names_its_null():
    close = _wavy(900)
    st = ea.live_state("ZZZ", close=close, df=_library([_ev("AAA", "2015-01-02")]))
    assert st["grids"] == {}
    assert st["reason"] == "no_events_for_name"
    assert "align_now" in st, "the current alignment is readable even with no history"


def test_live_state_never_raises_on_a_broken_input():
    assert ea.live_state("AAA", close=pd.Series(dtype=float), df=se.events_frame([])) is None


# ---------------------------------------------------------------------------
# 6 — the site artifact
# ---------------------------------------------------------------------------

def test_atlas_schema_is_cohort_grain_display_tier_with_its_citation(tmp_path):
    df = _library(
        [_ev(f"N{i}", f"201{i%10}-0{i%9+1}-05", archetype="cyclical") for i in range(12)]
        + [_ev(f"M{i}", f"201{i%10}-0{i%9+1}-05", archetype="quality_compounder")
           for i in range(12)]
    )
    a = ea.build_atlas(df, min_n=1)
    assert a["schema"] == ea.SCHEMA
    assert a["tier"] == "display"
    assert a["authority"] == ea.AUTHORITY
    assert all(a["authority"][k] is False
               for k in ("may_rank", "may_gate", "may_size", "may_escalate"))
    assert a["masterplan"] == "research/SIGNAL_EPISODE_ATLAS_MASTERPLAN_BY_FABLE.md"
    assert a["taxonomy_version"] == se.TAXONOMY_VERSION
    assert a["universe_basis"] == se.UNIVERSE_BASIS
    assert a["shrinkage"] == {"k_name": 12, "k_arch": 50}
    assert set(a["cells"]) == {"global", "archetype"}, (
        "per-name cells are computed inline, never shipped in the artifact"
    )
    assert a["cells"]["global"] and a["cells"]["archetype"]
    for bucket in a["cells"].values():
        for cell in bucket.values():
            for horizon in cell.values():
                assert set(horizon) == {"pooled", "post2010", "era_note"}
    # no ticker may appear as a cell key (the size-control invariant)
    assert not any("N0" in k or "M0" in k for k in a["cells"]["global"])

    written = ea.write_site_artifact(a, tmp_path)
    assert written == tmp_path / "stockdata" / "event_atlas.json"
    reread = json.loads(written.read_text())
    assert reread["schema"] == ea.SCHEMA
    assert reread["caveats"]["survivorship"] == ea.CAVEAT_SURVIVORSHIP


def test_atlas_min_n_floor_is_disclosed_in_the_payload():
    df = _library([_ev("AAA", "2015-01-02"), _ev("BBB", "2015-02-06")]
                  + [_ev(f"C{i}", f"201{i}-03-05", depth_class="mid") for i in range(1, 9)])
    small = ea.build_atlas(df, min_n=1)
    big = ea.build_atlas(df, min_n=5)
    assert small["min_cell_events"] == 1 and big["min_cell_events"] == 5
    assert big["n_cells"] < small["n_cells"], "the floor must actually drop thin cells"


def test_atlas_on_an_empty_library_is_a_valid_empty_artifact():
    a = ea.build_atlas(se.events_frame([]))
    assert a["n_events"] == 0 and a["as_of"] is None
    assert a["cells"] == {"global": {}, "archetype": {}}
    json.dumps(a, allow_nan=False)


# ---------------------------------------------------------------------------
# 7 — guard rails
# ---------------------------------------------------------------------------

def test_authority_block_is_all_false_display_tier():
    assert ea.AUTHORITY["tier"] == "display"
    for key in ("may_rank", "may_gate", "may_size", "may_escalate"):
        assert ea.AUTHORITY[key] is False


def test_class_axes_are_the_frozen_taxonomy():
    assert ea.CLASS_AXES == ("depth_class", "level", "washout_len_class", "align_class")
    assert ea.GRID_HORIZONS == {"W": ("13w", "26w"), "2B": ("21s", "63s"),
                                "3B": ("21s", "63s")}


def test_module_never_reaches_into_the_pick_chain():
    src = (_SRC_ROOT / "engine/event_atlas.py").read_text(encoding="utf-8")
    for banned in ("engine.prophet", "us_board_rank", "engine.board", "name_score",
                   "stock_score", "entry_signal"):
        assert f"import {banned}" not in src


def test_docstring_states_the_no_per_name_selection_rule():
    src = " ".join((_SRC_ROOT / "engine/event_atlas.py").read_text(
        encoding="utf-8")[:4000].split())
    assert "never as per-name indicator selection" in src
    assert "DT-R16" in src and "#1751" in src


# ---------------------------------------------------------------------------
# 8 — the notifier's alignment suffix
# ---------------------------------------------------------------------------

def test_notifier_alignment_suffix_clears_the_forbidden_words_guard():
    import scripts.notify_turn_events as nte

    for k in (0, 1, 2):
        msg = nte._washout_turn_message("MCD", {"depth_pctile": 6.3}, "2026-07-31", align=k)
        nte._assert_no_forbidden_words(msg)          # raises on a violation
        assert f"grids aligned {k}/2" in msg
        assert "MCD" in msg and "6.3" in msg
    # unknown alignment is OMITTED, never printed as a placeholder
    plain = nte._washout_turn_message("MCD", {"depth_pctile": 6.3}, "2026-07-31", align=None)
    nte._assert_no_forbidden_words(plain)
    assert "grids aligned" not in plain
    assert "?" not in plain.split("|")[0]
    # an out-of-range value is dropped rather than printed
    assert "grids aligned" not in nte._washout_turn_message(
        "MCD", {"depth_pctile": 6.3}, "2026-07-31", align=9)


def test_notifier_alignment_lookup_fails_open(monkeypatch):
    import scripts.notify_turn_events as nte

    monkeypatch.setattr(ea, "live_state", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert nte._event_align("MCD") is None


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-x", "-q"])
