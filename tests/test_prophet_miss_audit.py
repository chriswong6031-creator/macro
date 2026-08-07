"""Tests for the Prophet US miss-audit engine (W0 — ops telemetry, ZERO authority).

Covers (engine/prophet_miss_audit.py, masterplan
research/PROPHET_US_TREND_INTELLIGENCE_MASTERPLAN_BY_FABLE.md §W0):

* EXCLUDER ATTRIBUTION — the exact naming for every not-topped veto leg and every non-veto
  exclusion path, pinned as strings (they are the histogram keys the forward log carries, so a
  rename is a schema break, not a cosmetic edit). Both directions: a leg that is down must be
  named, and a leg that is UP must not appear in the string.
* CONVERSION JOIN — sighted denominator excludes never-measurable names, an empty denominator
  is None (not 0%), and the numerator is the plan-asset intersection.
* FORWARD-LOG APPEND GUARD — a non-nightly invocation appends NOTHING and writes no artifact;
  nightly appends exactly one row and is idempotent on price_through. Pinned at the engine
  entry point AND at the runner's flag parsing, because the guard is only as good as the flag
  that reaches it.
* ARTIFACT SCHEMA — the key set, the degraded disclosure, and determinism (two builds over the
  same synthetic caches are byte-identical: no wall clock anywhere).
* NAME_SCORE SCORECARD (roadmap §4.4 action 1) — the read-only mirror of the nightly
  name_score grader. Pinned as an ANTI-FORK contract: on one synthetic world the audit's
  block must reproduce ``name_score_grader.grade()`` field for field, so the caching adapter
  can never become a second opinion. Plus the null-disclosure shape (an unmatured horizon is
  a named reason, never a zero; an uncomputable P@k is None, never 50%).

Every store write in this file goes to tmp_path — the real data/ tree is never touched
(MM_DATA_GUARD; conftest sessionfinish guard).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import confluence_tiers as ct  # noqa: E402
from engine import grading  # noqa: E402
from engine import name_score_grader as NSG  # noqa: E402
from engine import prophet_miss_audit as PMA  # noqa: E402
import scripts.run_prophet_miss_audit as RUNNER  # noqa: E402


# ---------------------------------------------------------------------------
# synthetic frames
# ---------------------------------------------------------------------------
_N = 420          # > MIN_HISTORY (200) with room for a 63-session window


def _bdays(n: int = _N) -> pd.DatetimeIndex:
    return pd.bdate_range("2024-01-01", periods=n)


def _walk(seed: int, drift: float, n: int = _N, vol: float = 0.012) -> pd.Series:
    """A deterministic seeded random walk — a real price path for the tier math to chew on."""
    rng = np.random.RandomState(seed)
    steps = rng.normal(drift, vol, n)
    return pd.Series(100.0 * np.exp(np.cumsum(steps)), index=_bdays(n))


def _runner(seed: int, n: int = _N) -> pd.Series:
    """A strongly-trending noisy path — the shape a top-decile runner actually has."""
    return _walk(seed=seed, drift=0.004, n=n)


def _legs(**over) -> dict:
    """A leg snapshot with every leg constructive; override the ones under test."""
    base = {"stoch_ob": False, "stoch_bear": False, "macd_bear": False, "rsi_block": False,
            "k3": 40.0, "d3": 38.0, "rsi3d": 50.0,
            "t1_ticks": 0, "t2_ticks": 0, "t2raw_ticks": 0, "recent3": True}
    base.update(over)
    return base


def _patch_legs(monkeypatch, legs: dict) -> None:
    monkeypatch.setattr(PMA, "leg_snapshot", lambda close: legs)


# ---------------------------------------------------------------------------
# (a) excluder attribution — one pin per veto leg
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("fired,expected", [
    (["stoch_ob"], "not_topped_veto(stoch_ob)"),
    (["stoch_bear"], "not_topped_veto(stoch_bear)"),
    (["macd_bear"], "not_topped_veto(macd_bear)"),
    (["stoch_ob", "stoch_bear"], "not_topped_veto(stoch_ob+stoch_bear)"),
    (["stoch_bear", "macd_bear"], "not_topped_veto(stoch_bear+macd_bear)"),
    (["stoch_ob", "macd_bear"], "not_topped_veto(stoch_ob+macd_bear)"),
    (["stoch_ob", "stoch_bear", "macd_bear"],
     "not_topped_veto(stoch_ob+stoch_bear+macd_bear)"),
])
def test_veto_leg_naming(monkeypatch, fired, expected):
    """Each not-topped leg is named, in cascade's own evaluation order, and only when down."""
    _patch_legs(monkeypatch, _legs(**{leg: True for leg in fired}))
    out = PMA.attribute_excluder(pd.Series(dtype="float64"), eligible_today=False)
    assert out["excluder"] == expected
    assert out["excluder_family"] == "not_topped_veto"
    assert out["veto_legs"] == [leg for leg in PMA.VETO_LEGS if leg in fired]
    # inverse scan: a leg that is UP must never appear in the attribution string
    for quiet in set(PMA.VETO_LEGS) - set(fired):
        assert quiet not in out["excluder"], f"{quiet} is constructive but was named"


def test_non_veto_excluder_paths(monkeypatch):
    """The four non-veto exclusion names, in the cascade's evaluation order."""
    cases = [
        # RSI cap ate an otherwise-fresh 2D cross
        (_legs(rsi_block=True, rsi3d=71.0, t1_ticks=9, t2raw_ticks=1),
         PMA.EXC_RSI_CAP),
        # the cross happened, but it is stale on both families
        (_legs(t1_ticks=9, t2_ticks=9, t2raw_ticks=9), PMA.EXC_FRESHNESS),
        # no 3D stoch cross inside CONF_W and no datable 2D/3D cross at all
        (_legs(recent3=False, t1_ticks=None, t2_ticks=None, t2raw_ticks=None),
         PMA.EXC_NO_RECENT_3D),
        # legs constructive, window recent, but nothing crossed
        (_legs(t1_ticks=None, t2_ticks=None, t2raw_ticks=None), PMA.EXC_NO_CROSS),
    ]
    for legs, expected in cases:
        _patch_legs(monkeypatch, legs)
        out = PMA.attribute_excluder(pd.Series(dtype="float64"), eligible_today=False)
        assert out["excluder"] == expected, f"{legs} -> {out['excluder']}, want {expected}"
        assert out["excluder_family"] == expected


def test_eligible_short_circuits_every_leg(monkeypatch):
    """The production verdict wins: an eligible name is ELIGIBLE even with legs that look bad.

    attribute_excluder EXPLAINS the tier_stream verdict; it must never override it — otherwise
    the histogram and the eligibility counts in the same artifact could disagree.
    """
    _patch_legs(monkeypatch, _legs(stoch_ob=True, macd_bear=True, t1_ticks=99))
    out = PMA.attribute_excluder(pd.Series(dtype="float64"), eligible_today=True)
    assert out["excluder"] == PMA.EXC_ELIGIBLE
    assert out["excluder_family"] == PMA.EXC_ELIGIBLE
    assert out["veto_legs"] == ["stoch_ob", "macd_bear"]   # still reported, just not the label


def test_thin_history_is_named_not_guessed():
    """Below MIN_HISTORY there are no legs to read — say so rather than invent a reason."""
    thin = pd.Series(np.linspace(10, 20, 50), index=_bdays(50))
    out = PMA.attribute_excluder(thin, eligible_today=False)
    assert out["excluder"] == PMA.EXC_INSUFFICIENT
    assert out["veto_legs"] == []


@pytest.mark.parametrize("seed", range(1, 12))
def test_leg_snapshot_never_forks_from_the_cascade_veto(seed):
    """Anti-fork pin: the overlay's veto legs must reproduce cascade's own `not_topped`.

    ``leg_snapshot`` is a diagnostic overlay that names WHICH leg is down; if it ever drifts
    from ``confluence_tiers``, the artifact attributes an exclusion to a leg the board never
    evaluated. Checked in BOTH directions across a spread of seeded paths: any leg down <=>
    cascade says topped, no leg down <=> cascade says constructive.
    """
    s = _runner(seed)
    legs = PMA.leg_snapshot(s)
    assert legs, "expected a leg snapshot on a >MIN_HISTORY series"
    fired = [n for n in PMA.VETO_LEGS if legs[n]]
    casc = ct.cascade(s)
    assert bool(fired) is (not casc["not_topped"]), (
        f"seed {seed}: overlay fired {fired} but cascade not_topped={casc['not_topped']}")
    if fired:
        out = PMA.attribute_excluder(s, eligible_today=bool(casc["eligible"]))
        assert out["excluder"] == "not_topped_veto(" + "+".join(fired) + ")"


def test_leg_snapshot_pins_the_overbought_runner():
    """A concrete overbought runner: k3/d3 in the OB zone, named stoch_ob and nothing else."""
    s = _runner(3)
    legs = PMA.leg_snapshot(s)
    assert legs["stoch_ob"] is True, f"expected overbought, got k3={legs['k3']} d3={legs['d3']}"
    assert max(legs["k3"], legs["d3"]) >= ct.OB
    assert legs["stoch_bear"] is False and legs["macd_bear"] is False
    casc = ct.cascade(s)
    assert casc["not_topped"] is False and casc["eligible"] is False
    out = PMA.attribute_excluder(s, eligible_today=False)
    assert out["excluder"] == "not_topped_veto(stoch_ob)"


def test_eligibility_window_agrees_with_tier_stream():
    """eligible_today is the stream's own last row, and days_eligible counts the same object."""
    s = _walk(seed=11, drift=0.0006)
    win = PMA.eligibility_window(s, lookback=63)
    st = ct.tier_stream(s)
    assert not st.empty
    assert win["eligible_today"] == bool(st["eligible"].iloc[-1])
    assert win["days_eligible"] == int(st.tail(63)["eligible"].sum())
    assert 0 <= win["days_eligible"] <= 63
    if win["days_eligible"]:
        assert win["first_eligible"] is not None
        assert win["tiers_seen"]
    else:
        assert win["first_eligible"] is None


def test_eligibility_window_thin_history_is_null_not_zero():
    """A name we could never measure reports None days — not 0, which would read as a miss."""
    win = PMA.eligibility_window(pd.Series(np.linspace(1, 2, 40), index=_bdays(40)))
    assert win["days_eligible"] is None
    assert win["eligible_today"] is False


# ---------------------------------------------------------------------------
# (b) conversion join
# ---------------------------------------------------------------------------
def test_conversion_join_counts_and_denominator():
    rows = [
        {"ticker": "AAA", "days_eligible": 5},     # sighted, has a plan
        {"ticker": "BBB", "days_eligible": 1},     # sighted, no plan
        {"ticker": "CCC", "days_eligible": 0},     # seen zero days -> never sighted
        {"ticker": "DDD", "days_eligible": None},  # never measurable -> out of the denominator
        {"ticker": "EEE", "days_eligible": 12},    # sighted, has a plan
    ]
    out = PMA.conversion_join(rows, {"AAA", "EEE", "ZZZ"})
    assert out["sighted_n"] == 3                  # AAA, BBB, EEE (not CCC, not DDD)
    assert out["converted_n"] == 2
    assert out["converted"] == ["AAA", "EEE"]
    assert out["rate"] == pytest.approx(2 / 3, abs=1e-4)   # stored rounded to 4dp
    assert out["never_sighted_n"] == 1            # CCC only; DDD was never measurable
    assert out["unconverted_top"] == ["BBB"]
    assert out["plan_universe_n"] == 3


def test_conversion_join_empty_denominator_is_null_not_zero():
    """Nothing sighted is an ABSENCE of measurement, not a 0% conversion rate."""
    out = PMA.conversion_join([{"ticker": "AAA", "days_eligible": 0}], {"AAA"})
    assert out["sighted_n"] == 0
    assert out["converted_n"] == 0
    assert out["rate"] is None


def test_conversion_join_ignores_plans_for_unsighted_names():
    """A plan on a name the engine never sighted does not inflate the numerator."""
    out = PMA.conversion_join([{"ticker": "AAA", "days_eligible": 0}], {"AAA", "BBB"})
    assert out["converted_n"] == 0


# ---------------------------------------------------------------------------
# (c) forward-log append guard — nightly is the SOLE advancer
# ---------------------------------------------------------------------------
def _doc(price_through: str = "2026-07-31") -> dict:
    return {
        "schema": PMA.SCHEMA, "price_through": price_through,
        "summary": {"universe_n": 3, "eligible_today_n": 1, "top63_n": 2,
                    "top63_eligible_today_n": 1, "top63_never_eligible_n": 1,
                    "top63_never_eligible_pct": 0.5,
                    "top63_eligible_days": {"n": 2, "mean": 1.0, "p25": 0.5, "median": 1.0,
                                            "p75": 1.5, "min": 0.0, "max": 2.0},
                    "top21_n": 1, "top21_eligible_today_n": 0,
                    "conversion_rate": 0.5, "conversion_n": "1/2"},
        "top63_excluder_family_hist": {"not_topped_veto": 1, "ELIGIBLE": 1},
        "conversion": {"sighted_n": 2, "converted_n": 1, "rate": 0.5, "converted": ["AAA"],
                       "never_sighted_n": 1, "unconverted_top": ["BBB"], "plan_universe_n": 1},
        # the live shape on the night this schema shipped: 21d graded thin, 63d accruing
        "name_score_scorecard": {
            "tier": "ops_telemetry", "available": True,
            "forward_store": {"coverage_pct": 11.9},
            "by_horizon": {
                "21d": {"rank_ic": -0.0571, "n_ic_dates": 2, "thin": True},
                "63d": {"rank_ic": None, "n_ic_dates": 0, "thin": True,
                        "null_reason": "still accruing"},
            },
        },
        "degraded": [],
    }


def test_forward_log_not_advanced_without_nightly(tmp_path):
    log = tmp_path / "forward_log.jsonl"
    assert PMA.append_forward_log(_doc(), log, advance=False) is False
    assert not log.exists(), "a non-nightly invocation must append NOTHING"


def test_forward_log_nightly_appends_once_and_is_idempotent(tmp_path):
    log = tmp_path / "forward_log.jsonl"
    assert PMA.append_forward_log(_doc(), log, advance=True) is True
    assert PMA.append_forward_log(_doc(), log, advance=True) is False, \
        "a same-price_through re-run must not double-count the night"
    rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(rows) == 1
    assert rows[0]["price_through"] == "2026-07-31"
    assert rows[0]["converted_n"] == 1 and rows[0]["sighted_n"] == 2
    assert rows[0]["conversion_rate"] == 0.5
    # a NEW price date is a new night and does advance
    assert PMA.append_forward_log(_doc("2026-08-03"), log, advance=True) is True
    rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert [r["price_through"] for r in rows] == ["2026-07-31", "2026-08-03"]


def test_forward_log_row_carries_the_name_score_headline():
    """The scorecard's headline figures ride the forward log so the rank-IC is a SERIES,
    not a value you have to dig out of each night's artifact in git history.

    Shipped before the log's first row was ever written (the 08-02/08-03 nightlies failed),
    so this is a schema-before-first-row change rather than a migration across mixed-era
    rows — every row the log will ever hold carries these keys.
    """
    row = PMA.summary_row(_doc())
    assert row["name_score_available"] is True
    assert row["name_score_coverage_pct"] == 11.9
    assert row["name_score_rank_ic_21d"] == -0.0571
    assert row["name_score_ic_dates_21d"] == 2
    # the accruing horizon rides as a NULL with its date count, never as a 0.0 rank-IC
    assert row["name_score_rank_ic_63d"] is None
    assert row["name_score_ic_dates_63d"] == 0
    # both horizons the grader defines are present, so a later horizon change is visible
    for h in NSG._HORIZONS_D:
        assert f"name_score_rank_ic_{h}d" in row and f"name_score_ic_dates_{h}d" in row


def test_forward_log_row_is_null_safe_without_a_scorecard():
    """A night whose scorecard failed still writes its row: the fields go null and
    ``name_score_available`` False says WHICH kind of null this is (join failed, not
    accruing). The forward log must never be what takes the nightly down."""
    doc = _doc()
    doc.pop("name_score_scorecard")
    row = PMA.summary_row(doc)
    assert row["name_score_available"] is False
    assert row["name_score_coverage_pct"] is None
    assert row["name_score_rank_ic_21d"] is None and row["name_score_ic_dates_21d"] is None
    json.dumps(row)          # the row must still serialise to one JSONL line

    doc["name_score_scorecard"] = {"available": False, "null_reason": "ledger unreadable"}
    row = PMA.summary_row(doc)
    assert row["name_score_available"] is False
    assert row["name_score_rank_ic_21d"] is None


def test_forward_log_row_carries_no_wall_clock():
    """Determinism law: the row is keyed by price_through, with no run timestamp anywhere."""
    row = PMA.summary_row(_doc())
    blob = json.dumps(row).lower()
    for banned in ("generated", "timestamp", "utcnow", "run_at", "run_date"):
        assert banned not in blob, f"{banned} makes the forward log non-deterministic"


def test_run_writes_nothing_without_nightly(tmp_path, monkeypatch):
    """The engine entry point: default invocation writes neither artifact nor log."""
    monkeypatch.setattr(PMA, "build_audit", lambda root, **kw: _doc())
    PMA.run(advance=False, root=tmp_path, quiet=True)
    assert not (tmp_path / PMA.ARTIFACT_REL).exists()
    assert not (tmp_path / PMA.FORWARD_LOG_REL).exists()


def test_run_nightly_writes_artifact_and_log(tmp_path, monkeypatch):
    monkeypatch.setattr(PMA, "build_audit", lambda root, **kw: _doc())
    PMA.run(advance=True, root=tmp_path, quiet=True)
    art = tmp_path / PMA.ARTIFACT_REL
    log = tmp_path / PMA.FORWARD_LOG_REL
    assert art.exists() and log.exists()
    assert json.loads(art.read_text(encoding="utf-8"))["schema"] == PMA.SCHEMA
    assert len(log.read_text(encoding="utf-8").splitlines()) == 1


def test_runner_flag_maps_to_the_ledger_gate(monkeypatch):
    """The guard is only as good as the flag that reaches it — pin the runner's own mapping."""
    seen: list[dict] = []
    monkeypatch.setattr(PMA, "run", lambda **kw: seen.append(kw) or {})
    monkeypatch.setattr(RUNNER, "PMA", PMA)

    monkeypatch.setattr(sys, "argv", ["run_prophet_miss_audit"])
    RUNNER.main()
    assert seen[-1]["advance"] is False and seen[-1]["out_dir"] is None

    monkeypatch.setattr(sys, "argv", ["run_prophet_miss_audit", "--nightly"])
    RUNNER.main()
    assert seen[-1]["advance"] is True


def test_out_dir_never_touches_the_real_store(tmp_path, monkeypatch):
    """--out-dir runs the full write into a scratch dir; the root paths stay untouched."""
    monkeypatch.setattr(PMA, "build_audit", lambda root, **kw: _doc())
    out = tmp_path / "scratch"
    PMA.run(advance=False, root=tmp_path, out_dir=out, quiet=True)
    assert (out / "latest.json").exists() and (out / "forward_log.jsonl").exists()
    assert not (tmp_path / PMA.ARTIFACT_REL).exists()
    assert not (tmp_path / PMA.FORWARD_LOG_REL).exists()


# ---------------------------------------------------------------------------
# (d) artifact schema + degraded disclosure + determinism, over a synthetic repo
# ---------------------------------------------------------------------------
def _synth_root(tmp_path: Path, *, with_rotation: bool = True,
                with_standouts: bool = True, with_sectors: bool = True) -> Path:
    """A miniature repo tree: three close caches, a sector map, plans, board + rotation JSON."""
    tickers = [f"T{i:02d}" for i in range(24)]
    cols = {}
    for i, t in enumerate(tickers):
        cols[t] = _walk(seed=100 + i, drift=(0.002 - 0.0002 * i))
    wide = pd.DataFrame(cols)
    # split across the three cap-band caches the engine unions
    bands = {"breadth": tickers[:8], "midcap_breadth": tickers[8:16],
             "smallcap_breadth": tickers[16:]}
    for grp, names in bands.items():
        d = tmp_path / "data" / grp
        d.mkdir(parents=True, exist_ok=True)
        wide[names].to_parquet(d / "_closes_cache.parquet")
    if with_sectors:
        pd.DataFrame({"ticker": tickers,
                      "sector": ["Information Technology" if i % 2 else "Health Care"
                                 for i in range(len(tickers))]}) \
            .to_parquet(tmp_path / "data" / "breadth" / "ticker_sectors.parquet")

    plans = tmp_path / "site" / "prophet" / "plans"
    plans.mkdir(parents=True, exist_ok=True)
    for t in tickers[:3]:
        (plans / f"{t}-BULL-20260701.json").write_text(
            json.dumps({"id": f"{t}-BULL-20260701", "asset": t, "direction": "BULL"}),
            encoding="utf-8")

    if with_standouts:
        (tmp_path / "site" / "factordata").mkdir(parents=True, exist_ok=True)
        (tmp_path / "site" / "factordata" / "us_standouts.json").write_text(json.dumps({
            "as_of": "2026-07-31",
            "buy": [{"ticker": tickers[0]}], "ran": [{"ticker": tickers[1]}],
            "leaders": [{"ticker": tickers[2]}],
        }), encoding="utf-8")
    if with_rotation:
        (tmp_path / "site" / "marketdata").mkdir(parents=True, exist_ok=True)
        (tmp_path / "site" / "marketdata" / "subsector_rotation.json").write_text(json.dumps({
            "asof": "2026-08-02",
            "themes": [{"theme": "Alpha", "emerging_score": 3.2},
                       {"theme": "Beta", "emerging_score": 2.1},
                       {"theme": "Gamma", "emerging_score": 0.4}],
            "subsectors": [
                {"key": "a1", "name": "A1", "theme": "Alpha",
                 "members": [{"t": tickers[0]}, {"t": tickers[1]}, {"t": tickers[5]}]},
                {"key": "b1", "name": "B1", "theme": "Beta",
                 "members": [{"t": tickers[2]}, {"t": tickers[9]}]},
                {"key": "g1", "name": "G1", "theme": "Gamma", "members": [{"t": tickers[20]}]},
            ],
        }), encoding="utf-8")
    return tmp_path


_ARTIFACT_KEYS = {
    "schema", "price_through", "tier", "authority", "bases", "summary",
    "top63_excluder_hist", "top63_excluder_family_hist", "top21_excluder_hist",
    "veto_leg_hist", "runner_sector_hist", "eligible_today_sector_hist",
    "conversion", "themes", "basket_misses", "name_score_scorecard",
    "scan_tier",
    "priority_score_scorecard",
    "top63_runners", "top21_runners", "eligible_today", "degraded",
}
_SUMMARY_KEYS = {
    "universe_n", "eligible_today_n", "top63_n",
    "top63_eligible_today_n", "top63_never_eligible_n", "top63_never_eligible_pct",
    "top63_eligible_days", "top21_n", "top21_eligible_today_n", "conversion_rate",
    "conversion_n", "basket_misses_n", "basket_scored_n",
}


def test_artifact_schema_over_a_synthetic_universe(tmp_path):
    root = _synth_root(tmp_path)
    doc = PMA.build_audit(root, top63_n=10, top21_n=5, with_gate=False)
    assert set(doc) == _ARTIFACT_KEYS
    assert set(doc["summary"]) == _SUMMARY_KEYS
    assert doc["schema"] == PMA.SCHEMA
    assert doc["tier"] == "ops_telemetry"
    assert doc["authority"].startswith("none")
    assert doc["price_through"] == str(_bdays()[-1].date())
    assert doc["summary"]["universe_n"] == 24
    assert len(doc["top63_runners"]) == 10 and len(doc["top21_runners"]) == 5
    # every runner row carries the attribution + window contract
    for r in doc["top63_runners"]:
        assert {"ticker", "r63_pct", "sector", "excluder", "excluder_family", "veto_legs",
                "eligible_today", "days_eligible", "first_eligible"} <= set(r)
        assert r["excluder"], "every runner must carry a named excluder or ELIGIBLE"
    # the histogram totals the runner rows exactly (no name silently dropped)
    assert sum(doc["top63_excluder_hist"].values()) == len(doc["top63_runners"])
    assert sum(doc["top21_excluder_hist"].values()) == len(doc["top21_runners"])
    # runners are ordered by 63d return, descending
    rets = [r["r63_pct"] for r in doc["top63_runners"]]
    assert rets == sorted(rets, reverse=True)
    # the universe eligible-today set is the cascade basis, and it is a SUBSET of the stream
    # basis the runner rows use (cascade needs take_active for raw-3D-cross T1, the stream
    # takes it as a fallback) — pinning the direction stops the two bases being swapped
    casc = {e["ticker"] for e in doc["eligible_today"]}
    assert doc["summary"]["eligible_today_n"] == len(casc)
    assert sum(doc["eligible_today_sector_hist"].values()) == len(casc)
    runner_stream = {r["ticker"] for r in doc["top63_runners"] if r["eligible_today"]}
    assert casc & {r["ticker"] for r in doc["top63_runners"]} <= runner_stream, \
        "a cascade-eligible runner must also be stream-eligible (cascade is the stricter set)"


def test_summary_row_is_a_subset_of_the_artifact(tmp_path):
    root = _synth_root(tmp_path)
    doc = PMA.build_audit(root, top63_n=10, top21_n=5, with_gate=False)
    row = PMA.summary_row(doc)
    assert row["price_through"] == doc["price_through"]
    assert row["universe_n"] == doc["summary"]["universe_n"]
    assert row["converted_n"] == doc["conversion"]["converted_n"]
    assert row["excluder_family_hist"] == doc["top63_excluder_family_hist"]
    assert row["degraded_n"] == len(doc["degraded"])
    # the name_score headline is a SUBSET of the block, never a second computation.
    # This synthetic root ships no name_score ledger, so the block is the disclosed null —
    # which is exactly the case the row must carry as False + nulls rather than omit.
    ns = doc["name_score_scorecard"]
    assert row["name_score_available"] == ns["available"] is False
    for h in NSG._HORIZONS_D:
        assert row[f"name_score_rank_ic_{h}d"] == \
            (ns.get("by_horizon") or {}).get(f"{h}d", {}).get("rank_ic")


def test_build_is_deterministic(tmp_path):
    """Two builds over the same caches are byte-identical — no wall clock, keyed by asof."""
    root = _synth_root(tmp_path)
    a = PMA.build_audit(root, top63_n=10, top21_n=5, with_gate=False)
    b = PMA.build_audit(root, top63_n=10, top21_n=5, with_gate=False)
    assert json.dumps(a, sort_keys=True, default=str) == \
        json.dumps(b, sort_keys=True, default=str)


def test_missing_optional_stores_degrade_with_disclosure(tmp_path):
    """Fail-soft, never silent: every degraded input is named in `degraded`, values go null."""
    root = _synth_root(tmp_path, with_rotation=False, with_standouts=False,
                       with_sectors=False)
    doc = PMA.build_audit(root, top63_n=6, top21_n=3, with_gate=False)
    inputs = {d["input"] for d in doc["degraded"]}
    assert PMA.ROTATION_JSON in inputs
    assert PMA.STANDOUTS_JSON in inputs
    assert PMA.SECTORS_PARQUET in inputs
    assert all(d.get("reason") for d in doc["degraded"]), "a disclosure needs a reason"
    assert doc["themes"]["available"] is False and doc["themes"]["themes"] == []
    assert doc["runner_sector_hist"] == {"?": 6}, "sectors collapse to '?', not to a guess"
    # the audit still produced its measurement
    assert doc["summary"]["universe_n"] == 24


def test_theme_top5_latency_is_null_with_a_named_reason(tmp_path):
    """The PIT archive carries no theme-level rank — report null AND say why (never guess)."""
    root = _synth_root(tmp_path)
    doc = PMA.build_audit(root, top63_n=6, top21_n=3, with_gate=False)
    assert doc["themes"]["available"] is True
    assert [t["theme"] for t in doc["themes"]["themes"]] == ["Alpha", "Beta", "Gamma"]
    assert all(t["days_since_top5_entry"] is None for t in doc["themes"]["themes"])
    reasons = [d for d in doc["degraded"] if d["input"] == PMA.THEME_PIT_JSONL]
    assert reasons, "a null must be disclosed, not shipped bare"
    assert reasons[0]["severity"] == "structural"


def test_theme_member_lane_presence(tmp_path):
    """Theme members are the union over that theme's subsectors; lane counts join by ticker."""
    root = _synth_root(tmp_path)
    doc = PMA.build_audit(root, top63_n=6, top21_n=3, with_gate=False)
    alpha = doc["themes"]["themes"][0]
    assert alpha["theme"] == "Alpha" and alpha["n_members"] == 3   # T00, T01, T05
    assert alpha["present_counts"] == {"buy": 1, "ran": 1, "leaders": 0}
    assert alpha["represented_n"] == 2
    beta = doc["themes"]["themes"][1]
    assert beta["present_counts"] == {"buy": 0, "ran": 0, "leaders": 1}


# ---------------------------------------------------------------------------
# annotations — bare print at line start (repo law), and only when they should fire
# ---------------------------------------------------------------------------
def test_annotations_fire_at_line_start(capsys):
    doc = _doc()
    doc["conversion"].update(sighted_n=100, converted_n=2, rate=0.02)
    doc["summary"].update(top63_never_eligible_n=48, top63_n=150,
                          top63_never_eligible_pct=0.32)
    msgs = PMA.emit_annotations(doc)
    assert len(msgs) == 1, "only the conversion alarm should fire at 32% never-eligible"
    out = capsys.readouterr().out.splitlines()
    ann = [ln for ln in out if "prophet-miss-audit" in ln]
    assert ann and all(ln.startswith("::warning title=prophet-miss-audit::") for ln in ann), \
        "GitHub only parses '::' at column 0 — a prefixed line is silently dropped"


def test_never_eligible_annotation_fires_above_threshold(capsys):
    doc = _doc()
    doc["conversion"].update(sighted_n=100, converted_n=40, rate=0.40)   # conversion is fine
    doc["summary"].update(top63_never_eligible_n=70, top63_n=150,
                          top63_never_eligible_pct=0.47)
    msgs = PMA.emit_annotations(doc)
    assert len(msgs) == 1 and "never eligible" in msgs[0]
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::")]
    assert len(lines) == 1


def test_no_annotation_when_healthy(capsys):
    doc = _doc()
    doc["conversion"].update(sighted_n=100, converted_n=40, rate=0.40)
    doc["summary"].update(top63_never_eligible_n=10, top63_n=150,
                          top63_never_eligible_pct=0.07)
    assert PMA.emit_annotations(doc) == []
    assert [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::")] == []


def test_structural_degradation_does_not_page_but_unexpected_does(capsys):
    """A permanently-known gap must not cry wolf; a real missing input must."""
    doc = _doc()
    doc["conversion"].update(sighted_n=100, converted_n=40, rate=0.40)
    doc["summary"].update(top63_never_eligible_n=10, top63_n=150,
                          top63_never_eligible_pct=0.07)
    doc["degraded"] = [{"input": PMA.THEME_PIT_JSONL, "severity": "structural",
                        "reason": "no theme rank"}]
    assert PMA.emit_annotations(doc) == []
    capsys.readouterr()
    doc["degraded"].append({"input": PMA.STANDOUTS_JSON, "severity": "unexpected",
                            "reason": "gone"})
    msgs = PMA.emit_annotations(doc)
    assert len(msgs) == 1 and PMA.STANDOUTS_JSON in msgs[0]
    assert PMA.THEME_PIT_JSONL not in msgs[0]


# ---------------------------------------------------------------------------
# (f) basket-grain misses — "did a whole theme run with nobody on the board?"
# ---------------------------------------------------------------------------
_BK_N = 300          # bars per synthetic member: > BASKET_MIN_HISTORY + horizon


def _bk_days(n: int = _BK_N) -> pd.DatetimeIndex:
    return pd.bdate_range("2025-01-01", periods=n)


def _pop(n: int = _BK_N) -> pd.Series:
    """Flat, then a hard 10-day run. Today's 10d return is the unique maximum of the
    basket's own history, so its mid-rank percentile pins at ~1.0."""
    idx = _bk_days(n)
    values = np.full(n, 100.0)
    values[-10:] = 100.0 * np.cumprod(np.full(10, 1.02))
    return pd.Series(values, index=idx)


def _ramp_then_flat(n: int = _BK_N) -> pd.Series:
    """A history full of +2% ten-day windows, then a dead-flat fortnight. Today's 10d
    return is 0 and sits at the BOTTOM of its own history — the deliberate opposite of
    ``_pop`` on the same store."""
    idx = _bk_days(n)
    values = 100.0 * np.cumprod(np.full(n, 1.002))
    values[-20:] = values[-21]
    return pd.Series(values, index=idx)


def _flat(n: int = _BK_N) -> pd.Series:
    """A dead series — every 10d return is exactly 0.0, so every observation ties."""
    return pd.Series(np.full(n, 100.0), index=_bk_days(n))


def _basket_root(tmp_path: Path, specs: dict, *, board: dict | None = None,
                 skip_store: tuple = ()) -> Path:
    """A miniature baskets store. ``specs`` = {basket_id: {member: series}}; a member
    listed in ``skip_store`` gets a membership row but NO parquet."""
    ohlcv = tmp_path / "data" / "baskets" / "ohlcv"
    ohlcv.mkdir(parents=True, exist_ok=True)
    baskets, written = {}, set()
    for basket_id, members in specs.items():
        rows = []
        for ticker, series in members.items():
            rows.append({"ticker": ticker, "added": "2024-01-01", "removed": None}
                        if not isinstance(series, tuple) else
                        {"ticker": ticker, "added": series[1], "removed": series[2]})
            data = series[0] if isinstance(series, tuple) else series
            if ticker in skip_store or ticker in written:
                continue
            pd.DataFrame({"close": data}).to_parquet(ohlcv / f"{ticker}.parquet")
            written.add(ticker)
        baskets[basket_id] = {"name": basket_id.title(), "category": "Test",
                              "members": rows}
    (tmp_path / "data" / "baskets" / "membership.json").write_text(
        json.dumps({"version": "test", "baskets": baskets}), encoding="utf-8")
    (tmp_path / "site" / "factordata").mkdir(parents=True, exist_ok=True)
    (tmp_path / "site" / "factordata" / "us_standouts.json").write_text(
        json.dumps({"as_of": "2026-07-31", **{k: [{"ticker": t} for t in v]
                                              for k, v in (board or {}).items()}}),
        encoding="utf-8")
    return tmp_path


def _run_baskets(root: Path, board: dict | None = None):
    degraded: list[dict] = []
    standouts = json.loads(
        (root / "site" / "factordata" / "us_standouts.json").read_text())
    block = PMA.basket_misses(root, standouts, degraded)
    return block, degraded, {r["basket_id"]: r for r in block["baskets"]}


def _four_worlds(tmp_path: Path) -> Path:
    """The 2x2 the miss rule is defined over: {ignited, quiet} x {dark, represented}."""
    specs = {
        "hot_dark": {f"HD{i}": _pop() for i in range(3)},
        "hot_seen": {f"HS{i}": _pop() for i in range(3)},
        "quiet_dark": {f"QD{i}": _ramp_then_flat() for i in range(3)},
        "quiet_seen": {f"QS{i}": _ramp_then_flat() for i in range(3)},
    }
    return _basket_root(tmp_path, specs, board={"buy": ["HS0"], "watch": ["QS1"]})


def test_a_miss_needs_BOTH_the_top_decile_and_zero_representation(tmp_path):
    """The whole rule, on one store, in one assertion set.

    Each half is separately necessary: `hot_seen` has the identical price history to
    `hot_dark` and differs only by one board row; `quiet_dark` has the identical board
    state as `hot_dark` and differs only by price. A rule that had lost either
    conjunct would flag two of these four.
    """
    block, _deg, rows = _run_baskets(_four_worlds(tmp_path))

    assert rows["hot_dark"]["pctile"] >= PMA.BASKET_TOP_DECILE
    assert rows["hot_seen"]["pctile"] == rows["hot_dark"]["pctile"]
    assert rows["quiet_dark"]["pctile"] < PMA.BASKET_TOP_DECILE
    assert rows["hot_dark"]["n_members_on_board"] == 0
    assert rows["quiet_dark"]["n_members_on_board"] == 0
    assert rows["hot_seen"]["n_members_on_board"] == 1
    assert rows["quiet_seen"]["n_members_on_board"] == 1

    assert [r["basket_id"] for r in block["misses"]] == ["hot_dark"]
    assert {b: rows[b]["miss"] for b in rows} == {
        "hot_dark": True, "hot_seen": False,
        "quiet_dark": False, "quiet_seen": False}
    assert block["n_top_decile"] == 2 and block["n_unrepresented"] == 2
    assert block["n_misses"] == 1


def test_every_visible_lane_counts_as_representation(tmp_path):
    """A member on ANY of buy/watch/leaders/ran means the basket was surfaced."""
    for lane in PMA.BASKET_BOARD_LANES:
        root = _basket_root(
            tmp_path / lane, {"hot": {f"H{i}": _pop() for i in range(3)}},
            board={lane: ["H0"]})
        block, _deg, rows = _run_baskets(root)
        assert rows["hot"]["pctile"] >= PMA.BASKET_TOP_DECILE, lane
        assert block["misses"] == [], f"{lane} membership must clear the miss"
        assert rows["hot"]["present_counts"][lane] == 1


def test_laggards_is_not_representation(tmp_path):
    """The board's weak-names shelf is not the basket being surfaced as opportunity,
    so a name sitting there must not clear an otherwise-dark ignition."""
    root = _basket_root(tmp_path, {"hot": {f"H{i}": _pop() for i in range(3)}},
                        board={"laggards": ["H0"]})
    block, _deg, rows = _run_baskets(root)
    assert rows["hot"]["n_members_on_board"] == 0
    assert [r["basket_id"] for r in block["misses"]] == ["hot"]


def test_a_dead_series_is_not_an_ignition(tmp_path):
    """Mid-rank, not the weak inequality: a store that stopped updating ties with
    itself on every bar, and `(hist <= today).mean()` would read that as 1.00 — a
    perfect top-decile flag on a basket that has not moved in a year."""
    root = _basket_root(tmp_path, {"dead": {f"D{i}": _flat() for i in range(3)}})
    block, _deg, rows = _run_baskets(root)
    assert rows["dead"]["ew_10d"] == 0.0
    assert rows["dead"]["pctile"] == pytest.approx(0.5)
    assert rows["dead"]["n_members_on_board"] == 0, "dark, so only price can clear it"
    assert block["misses"] == []


def _vol_walk(scale: float, seed: int, tail_daily: float) -> pd.Series:
    """A seeded walk at a chosen vol with a fixed 10-day tail move — deterministic
    (numpy's PCG64 stream is stable) and the only way to separate ABSOLUTE size from
    own-history extremity."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0, scale, _BK_N)
    returns[-10:] = tail_daily
    return pd.Series(100.0 * np.cumprod(1.0 + returns), index=_bk_days())


def test_percentile_is_own_history_never_cross_basket(tmp_path):
    """The SMALLER absolute move is the more extreme one, and the rule must say so.

    `loud` runs +5.1% over ten days and `quiet` +1.0% — a 5x difference in size — but
    loud's history is full of moves that big while quiet has never done it. Ranked
    against each other, loud wins and this instrument would page about high-vol
    baskets every night regardless of what actually turned. Ranked against their own
    histories the order inverts, and only quiet clears the decile.
    """
    root = _basket_root(tmp_path, {
        "loud": {f"L{i}": _vol_walk(0.03, 7, 0.005) for i in range(3)},
        "quiet": {f"Q{i}": _vol_walk(0.002, 7, 0.001) for i in range(3)}})
    _block, _deg, rows = _run_baskets(root)

    assert rows["loud"]["ew_10d"] > 4 * rows["quiet"]["ew_10d"] > 0, (
        "fixture must keep loud's move much LARGER or the inversion proves nothing")
    assert rows["quiet"]["pctile"] > rows["loud"]["pctile"]
    assert rows["quiet"]["pctile"] >= PMA.BASKET_TOP_DECILE
    assert rows["loud"]["pctile"] < PMA.BASKET_TOP_DECILE


def test_dated_membership_is_point_in_time(tmp_path):
    """A member removed before the last bar is neither in the EW nor counted as
    representation — the `[added, removed)` window engine.baskets._ew_level uses."""
    gone = _bk_days()[-30]
    specs = {"b": {"A": _pop(), "B": _pop(), "C": _pop(),
                   "OLD": (_pop(), "2024-01-01", str(gone.date()))}}
    root = _basket_root(tmp_path, specs, board={"buy": ["OLD"]})
    _block, _deg, rows = _run_baskets(root)
    assert rows["b"]["n_members"] == 4
    assert rows["b"]["n_members_live"] == 3
    assert rows["b"]["n_members_on_board"] == 0, "a removed member is not on the board"
    assert rows["b"]["miss"] is True


def test_member_coverage_is_counted_and_disclosed(tmp_path):
    """D12/D13: the basket-turn organ read 1 of 12 gold_miners members and printed a
    number indistinguishable from a fully-read one. Coverage is a field, not a hope."""
    specs = {"b": {f"M{i}": _pop() for i in range(4)}}
    root = _basket_root(tmp_path, specs, skip_store=("M3",))
    _block, degraded, rows = _run_baskets(root)
    assert rows["b"]["n_members"] == 4
    assert rows["b"]["n_members_read"] == 3
    hit = [d for d in degraded if d["input"] == PMA.BASKET_OHLCV_DIR]
    assert hit and "b" in hit[0]["reason"], "a partial read must be disclosed"


def test_a_shallow_coverage_gap_discloses_but_a_starved_one_pages(tmp_path):
    """3 of 4 members is a standing fact; 3 of 8 is the D12 failure. An annotation
    that fires every night for one unfetched member is noise, and noise is how the
    real 1-of-12 read went unnoticed for a month — so the two get different severities
    and only the starved one reaches emit_annotations."""
    shallow = _basket_root(tmp_path / "shallow",
                           {"b": {f"M{i}": _pop() for i in range(4)}},
                           skip_store=("M3",))
    starved = _basket_root(tmp_path / "starved",
                           {"b": {f"M{i}": _pop() for i in range(8)}},
                           skip_store=("M3", "M4", "M5", "M6", "M7"))

    _b1, deg_shallow, rows_shallow = _run_baskets(shallow)
    _b2, deg_starved, rows_starved = _run_baskets(starved)

    assert rows_shallow["b"]["n_members_read"] == 3 and rows_shallow["b"]["n_members"] == 4
    assert rows_starved["b"]["n_members_read"] == 3 and rows_starved["b"]["n_members"] == 8
    assert [d["severity"] for d in deg_shallow] == ["structural"]
    assert [d["severity"] for d in deg_starved] == ["unexpected"]
    assert str(int(PMA.BASKET_COVERAGE_WARN * 100)) in deg_starved[0]["reason"]


def test_too_few_readable_members_is_a_named_null_not_a_number(tmp_path):
    specs = {"b": {f"M{i}": _pop() for i in range(3)}}
    root = _basket_root(tmp_path, specs, skip_store=("M1", "M2"))
    _block, _deg, rows = _run_baskets(root)
    assert rows["b"]["pctile"] is None and rows["b"]["ew_10d"] is None
    assert rows["b"]["miss"] is False, "an unmeasurable basket is not a miss"
    assert str(PMA.BASKET_MIN_MEMBERS) in rows["b"]["null_reason"]


def test_thin_history_is_a_named_null_not_a_top_decile(tmp_path):
    """40 bars is a real 10-day return with 29 observations to rank it against — the
    exact shape that would otherwise print `pctile 1.0` off a fortnight of data and
    page as an ignition. Below the floor it is a null with the count in the reason."""
    root = _basket_root(tmp_path, {"b": {f"M{i}": _pop(40) for i in range(3)}})
    _block, _deg, rows = _run_baskets(root)
    assert rows["b"]["ew_10d"] is not None, "the RETURN is computable; the RANK is not"
    assert rows["b"]["pctile"] is None
    assert 0 < rows["b"]["pctile_n"] < PMA.BASKET_MIN_HISTORY
    assert rows["b"]["miss"] is False
    assert str(PMA.BASKET_MIN_HISTORY) in rows["b"]["null_reason"]


def test_block_is_keyed_to_its_own_store_clock(tmp_path):
    """Calendar-asof trap: the basket block reports the BASKET store's last bar and
    says so when the breadth caches disagree, rather than inheriting a foreign clock."""
    root = _basket_root(tmp_path, {"b": {f"M{i}": _pop() for i in range(3)}})
    degraded: list[dict] = []
    standouts = json.loads(
        (root / "site" / "factordata" / "us_standouts.json").read_text())
    block = PMA.basket_misses(root, standouts, degraded, "2099-01-01")
    assert block["as_of"] == str(_bk_days()[-1].date()) != "2099-01-01"
    assert any("price_through" in d["reason"] for d in degraded)


def test_unreadable_membership_degrades_with_a_reason(tmp_path):
    degraded: list[dict] = []
    block = PMA.basket_misses(tmp_path, {}, degraded)
    assert block["available"] is False
    assert block["misses"] == [] and block["tier"] == "ops_telemetry"
    assert block["null_reason"]
    assert any(d["input"] == PMA.BASKET_MEMBERSHIP_JSON for d in degraded)


def test_basket_miss_annotation_names_the_basket_at_line_start(capsys):
    doc = _doc()
    doc["conversion"].update(sighted_n=100, converted_n=40, rate=0.40)
    doc["summary"].update(top63_never_eligible_n=10, top63_n=150,
                          top63_never_eligible_pct=0.07)
    doc["basket_misses"] = {
        "available": True, "as_of": "2026-07-31",
        "misses": [{"basket_id": "gold_miners", "ew_10d": 0.081, "pctile": 0.96,
                    "n_members_live": 12, "n_members_on_board": 0}]}
    msgs = PMA.emit_annotations(doc)
    assert len(msgs) == 1 and "gold_miners" in msgs[0]
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::")]
    assert lines == [f"::warning title=prophet-miss-audit::{msgs[0]}"]


def test_no_basket_annotation_when_every_ignition_was_represented(capsys):
    doc = _doc()
    doc["conversion"].update(sighted_n=100, converted_n=40, rate=0.40)
    doc["summary"].update(top63_never_eligible_n=10, top63_n=150,
                          top63_never_eligible_pct=0.07)
    doc["basket_misses"] = {"available": True, "as_of": "2026-07-31", "misses": []}
    assert PMA.emit_annotations(doc) == []
    assert [ln for ln in capsys.readouterr().out.splitlines()
            if ln.startswith("::")] == []


def test_forward_log_row_carries_the_basket_headline(tmp_path):
    doc = _doc()
    doc["summary"].update(basket_scored_n=47, basket_misses_n=1)
    doc["basket_misses"] = {"available": True,
                            "misses": [{"basket_id": "gold_miners"}]}
    row = PMA.summary_row(doc)
    assert row["basket_scored_n"] == 47
    assert row["basket_misses_n"] == 1
    assert row["basket_misses"] == ["gold_miners"]
    json.dumps(row, allow_nan=False)


def test_forward_log_row_is_null_safe_without_a_basket_block():
    """A doc predating this layer must still produce a writable row — and an absent
    block is None, never 0: "we did not measure" is not "nothing was missed"."""
    row = PMA.summary_row(_doc())
    assert row["basket_misses_n"] is None and row["basket_scored_n"] is None
    assert row["basket_misses"] == []


def test_basket_layer_writes_nothing(tmp_path):
    """The layer is a pure read: it must not create or touch one path under data/."""
    root = _four_worlds(tmp_path)
    before = sorted(p.relative_to(root) for p in root.rglob("*") if p.is_file())
    _run_baskets(root)
    after = sorted(p.relative_to(root) for p in root.rglob("*") if p.is_file())
    assert before == after


# ---------------------------------------------------------------------------
# (e) name_score scorecard — read-only mirror of the nightly grader (roadmap §4.4)
# ---------------------------------------------------------------------------
_NS_TICKERS = [f"N{i:02d}" for i in range(30)]
_NS_STAMP_POS = (260, 265, 270)      # bar offsets of the three synthetic stamp dates
_NS_BARS = 300                       # 21d matures for every stamp; 63d matures for none


def _ns_prices(n: int = _NS_BARS) -> dict[str, pd.Series]:
    """A deterministic synthetic close world: 30 names, a spread of drifts."""
    idx = pd.bdate_range("2025-01-01", periods=n)
    out: dict[str, pd.Series] = {}
    for i, t in enumerate(_NS_TICKERS):
        rng = np.random.RandomState(500 + i)
        steps = rng.normal(0.0006 * (i - 15) / 15.0, 0.011, n)
        out[t] = pd.Series(50.0 * np.exp(np.cumsum(steps)), index=idx)
    return out


def _ns_ledger(prices: dict[str, pd.Series]) -> pd.DataFrame:
    """The grader's own call-ledger shape: one row per (date, ticker) with a stamped score,
    tier and as-of level — three stamp dates over the same 30 names."""
    idx = prices[_NS_TICKERS[0]].index
    rows = []
    for di, pos in enumerate(_NS_STAMP_POS):
        d = str(idx[pos].date())
        for i, t in enumerate(_NS_TICKERS):
            score = int((7 * i + 13 * di) % 101)
            tier = ("primed" if score >= 80 else "setting_up" if score >= 60
                    else "watch" if score >= 30 else "no_setup")
            rows.append({"date": d, "ticker": t, "score": score, "tier": tier,
                         "fuel": 0.5, "trigger": 0.5, "level": float(prices[t].iloc[pos])})
    return pd.DataFrame(rows)


def _ns_world(tmp_path: Path, monkeypatch) -> tuple[Path, dict[str, pd.Series]]:
    """Point BOTH the grader and the audit at one synthetic world: the same ledger file and
    the same close store. No real data/ path is read on this route."""
    prices = _ns_prices()
    ledger = tmp_path / PMA.NAME_SCORE_LEDGER_REL
    ledger.parent.mkdir(parents=True, exist_ok=True)
    _ns_ledger(prices).to_parquet(ledger, index=False)

    def _read(group, name):
        s = prices.get(str(name))
        return None if s is None else pd.DataFrame({"close": s})

    monkeypatch.setattr(PMA.store, "read", _read)          # lib.store — shared by both
    monkeypatch.setattr(grading, "load_dead_prices", lambda *a, **k: {})
    monkeypatch.setattr(NSG, "_store_path", lambda market="CN": ledger)
    return tmp_path, prices


def test_scorecard_never_forks_from_the_grader(tmp_path, monkeypatch):
    """ANTI-FORK PIN — the audit's block must reproduce ``name_score_grader.grade()`` field
    for field on one synthetic world.

    The adapter exists for RUNTIME only: pre-memo, ``grade()`` resolved the close series
    inside a per-(row, horizon) loop (~145k parquet reads on the live 72k-row ledger,
    measured 5.6ms each — ~13 minutes, rising every night) while the audit read each of the
    ~3k tickers once; ``grade()`` now memoizes the same way (``NSG._series_reader``), and
    the two independent readers are additionally pinned series-for-series below. A cache
    that quietly answered differently would put two sets of rank-IC numbers in the repo
    under one name, so the equality is pinned here rather than asserted in a docstring.
    """
    root, _prices = _ns_world(tmp_path, monkeypatch)
    graded = NSG.grade("US")
    block = PMA.name_score_scorecard(root)

    assert graded["available"] is True and block["available"] is True
    assert block["n_calls"] == graded["n_calls"]
    assert block["n_frozen_echoes_excluded"] == graded["n_frozen_excluded"]
    assert block["n_stamp_dates"] == len(graded["dates"])
    assert block["stamp_dates"] == {"first": graded["dates"][0], "last": graded["dates"][-1]}

    for h in NSG._HORIZONS_D:
        key = f"{h}d"
        mine, theirs = block["by_horizon"][key], graded["by_horizon"][key]
        assert mine["n_graded"] == theirs["n"], f"{key}: graded n diverged"
        if theirs.get("note") == "accruing":       # the grader's own not-yet-matured shape
            assert mine["rank_ic"] is None and mine["null_reason"]
            continue
        assert mine["rank_ic"] == theirs["rank_ic"], f"{key}: rank_ic diverged"
        assert mine["n_ic_dates"] == theirs["n_ic_dates"]
        assert mine["ic_cross_section"] == theirs["ic_cross_section"]
        assert mine["buy_tier_hit_rate"] == theirs["buy_tier_hit_rate"]
        assert mine["by_tier"] == theirs["by_tier"]
    # the pin is only worth something if the matured horizon actually produced numbers
    assert block["by_horizon"]["21d"]["rank_ic"] is not None
    assert block["by_horizon"]["21d"]["n_ic_dates"] == len(_NS_STAMP_POS)


def test_grader_reader_is_memoized_and_never_forks_from_the_audits(tmp_path, monkeypatch):
    """The grader's own memo (``NSG._series_reader``) must (a) read each name ONCE per
    ``grade()`` — the point of the memo: store reads bounded by the universe, never by
    ledger depth — and (b) resolve series byte-identical to the audit's independent
    reader (``PMA.name_score_series_reader``). Two implementations, one truth: a fork
    fails HERE at the resolution layer with a per-ticker diff instead of surfacing as
    a mysterious rank-IC drift in the scorecard pin above."""
    _root, _prices = _ns_world(tmp_path, monkeypatch)
    inner = PMA.store.read
    seen: list[tuple[str, str]] = []

    def counting_read(group, name):
        seen.append((str(group), str(name)))
        return inner(group, name)

    monkeypatch.setattr(PMA.store, "read", counting_read)
    graded = NSG.grade("US")
    assert graded["available"] is True and graded["n_graded"] > 0
    # one store read per name for the ENTIRE grade() (the US ladder is one group);
    # pre-memo this was len(ledger rows) × len(horizons) = 90 × 2 = 180 reads.
    assert len(seen) == len(_NS_TICKERS)
    assert len(set(seen)) == len(_NS_TICKERS)
    # resolution-layer anti-fork: both readers agree on every name (+ one absent name).
    mine = NSG._series_reader("US")
    theirs = PMA.name_score_series_reader("US")
    for t in [*_NS_TICKERS, "GHOST-NO-STORE"]:
        a, b = mine(t), theirs(t)
        if a is None or b is None:
            assert a is None and b is None, f"{t}: one reader resolved, the other nulled"
        else:
            pd.testing.assert_series_equal(a, b, check_exact=True)


def test_scorecard_is_zero_authority_and_names_the_overwritten_key(tmp_path, monkeypatch):
    """The block declares its tier, its lack of authority, and WHICH number it grades — the
    board's displayed conviction.score is name_score's potential_score."""
    root, _ = _ns_world(tmp_path, monkeypatch)
    block = PMA.name_score_scorecard(root)
    assert block["tier"] == "ops_telemetry"
    assert block["authority"].startswith("none")
    assert "potential_score" in block["scored_field"]
    assert "conviction.score" in block["scored_field"]
    assert block["source"] == PMA.NAME_SCORE_LEDGER_REL


def test_unmatured_horizon_is_a_named_null_not_a_zero(tmp_path, monkeypatch):
    """63d has no matured call in this world: rank_ic/P@k are None WITH a plain reason.

    A silent 0.0 (or a 0.5 precision) would read as a measured result. The grader's own
    vocabulary for this state is 'accruing' — the block says so in words a reader can act on.
    """
    root, _ = _ns_world(tmp_path, monkeypatch)
    h63 = PMA.name_score_scorecard(root)["by_horizon"]["63d"]
    assert h63["n_graded"] == 0
    assert h63["rank_ic"] is None and h63["precision_at_k"] is None
    assert h63["buy_tier_hit_rate"] is None
    assert h63["thin"] is True
    assert "accruing" in h63["null_reason"]
    assert "63 sessions" in h63["null_reason"]


def test_precision_at_k_shape_and_denominator(tmp_path, monkeypatch):
    """P@k is measured against each date's OWN graded cohort, and every denominator is the
    MATURED cohort — never the subset that resolved to a winner."""
    root, _ = _ns_world(tmp_path, monkeypatch)
    pk = PMA.name_score_scorecard(root)["by_horizon"]["21d"]["precision_at_k"]
    assert pk["min_cross_section"] == PMA.PK_MIN_XS
    assert pk["n_dates_eligible"] == len(_NS_STAMP_POS)
    assert pk["n_dates_excluded_thin"] == 0
    assert pk["cross_section"] == {"min": 30, "median": 30, "max": 30}
    # base is MEASURED per cohort, not assumed: the median splits 30 names 15/15
    assert pk["base_rate"] == pytest.approx(0.5, abs=0.02)
    for k in PMA.PK_K:
        cell = pk["by_k"][f"p_at_{k}"]
        assert cell["n_dates"] == len(_NS_STAMP_POS)
        assert cell["n_picks"] == k * len(_NS_STAMP_POS), "every top-k pick must be counted"
        assert 0.0 <= cell["value"] <= 1.0
        assert cell["lift_vs_base"] == pytest.approx(cell["value"] - pk["base_rate"], abs=6e-3)


def test_precision_at_k_thin_cohorts_are_counted_not_dropped():
    """A date too thin to rank is EXCLUDED and COUNTED — a silent drop would let a
    resolution-conditioned denominator masquerade as a full sample."""
    g = pd.DataFrame([
        {"date": "2026-07-01", "ticker": f"T{i}", "score": 100 - i, "tier": "watch",
         "fwd": 0.01 * (i % 3)} for i in range(30)
    ] + [
        {"date": "2026-07-02", "ticker": f"T{i}", "score": 50 - i, "tier": "watch",
         "fwd": 0.01 * i} for i in range(6)
    ])
    pk = PMA.precision_at_k(g, ks=(1, 5), min_xs=20)
    assert pk["n_dates_eligible"] == 1
    assert pk["n_dates_excluded_thin"] == 1
    assert str(pk["min_cross_section"]) in pk["definition"], "the cut must be stated in words"
    assert pk["by_k"]["p_at_1"]["n_dates"] == 1


def test_precision_at_k_uncomputable_is_none_never_one_half():
    """No qualifying date is an ABSENCE of measurement. None, with a reason — not 0.5."""
    empty = pd.DataFrame(columns=["date", "ticker", "score", "tier", "fwd"])
    pk = PMA.precision_at_k(empty)
    assert all(v is None for v in pk["by_k"].values())
    assert pk["null_reason"] and "no graded calls" in pk["null_reason"]
    assert "base_rate" not in pk, "a base rate with no cohort would be an invented 50%"

    thin = pd.DataFrame([{"date": "2026-07-01", "ticker": f"T{i}", "score": i,
                          "tier": "watch", "fwd": 0.01 * i} for i in range(4)])
    pk = PMA.precision_at_k(thin, min_xs=20)
    assert all(v is None for v in pk["by_k"].values())
    assert "not computable" in pk["null_reason"] and "50%" in pk["null_reason"]


def test_thin_ic_sample_is_labelled_thin(tmp_path, monkeypatch):
    """Three IC dates is a sample, not a measurement — say so on the row itself."""
    root, _ = _ns_world(tmp_path, monkeypatch)
    h21 = PMA.name_score_scorecard(root)["by_horizon"]["21d"]
    assert h21["n_ic_dates"] < PMA.THIN_MIN_IC_DATES
    assert h21["thin"] is True
    assert str(PMA.THIN_MIN_IC_DATES) in h21["thin_reason"]


def test_forward_store_coverage_is_disclosed(tmp_path, monkeypatch):
    """A stamped name with no close store is ABSENT from the grade, not scored zero — and
    the share that resolved is printed, because that is the scorecard's real sample size."""
    prices = _ns_prices()
    ledger = tmp_path / PMA.NAME_SCORE_LEDGER_REL
    ledger.parent.mkdir(parents=True, exist_ok=True)
    _ns_ledger(prices).to_parquet(ledger, index=False)
    covered = set(_NS_TICKERS[:20])                    # 10 of the 30 names have no store

    def _read(group, name):
        s = prices.get(str(name)) if str(name) in covered else None
        return None if s is None else pd.DataFrame({"close": s})

    monkeypatch.setattr(PMA.store, "read", _read)
    monkeypatch.setattr(grading, "load_dead_prices", lambda *a, **k: {})
    cov = PMA.name_score_scorecard(tmp_path)["forward_store"]
    assert cov["n_names_stamped"] == 30
    assert cov["n_names_resolved"] == 20
    assert cov["coverage_pct"] == pytest.approx(66.7, abs=0.1)


def test_missing_ledger_degrades_with_a_named_reason(tmp_path):
    """Fail-soft, never silent: no ledger is a disclosed null, not an exception and not a 0."""
    deg: list[dict] = []
    block = PMA.name_score_scorecard(tmp_path, deg)
    assert block["available"] is False
    assert block["null_reason"]
    assert [d for d in deg if d["input"] == PMA.NAME_SCORE_LEDGER_REL]
    assert all(d.get("reason") for d in deg)


def test_build_audit_carries_the_scorecard_block(tmp_path):
    """The nightly artifact carries the block; a synthetic root with no ledger carries the
    disclosed null (and the missing input lands in `degraded`)."""
    root = _synth_root(tmp_path)
    doc = PMA.build_audit(root, top63_n=6, top21_n=3, with_gate=False)
    block = doc["name_score_scorecard"]
    assert block["tier"] == "ops_telemetry"
    assert block["available"] is False and block["null_reason"]
    assert PMA.NAME_SCORE_LEDGER_REL in {d["input"] for d in doc["degraded"]}


def test_scorecard_measurement_never_raises_an_alarm(capsys, tmp_path, monkeypatch):
    """ZERO AUTHORITY, in both directions: the block sets no threshold, so a negative rank-IC
    or a P@1 of zero must page NOTHING. Only a missing INPUT is an ops event."""
    root, _ = _ns_world(tmp_path, monkeypatch)
    doc = _doc()
    doc["conversion"].update(sighted_n=100, converted_n=40, rate=0.40)
    doc["summary"].update(top63_never_eligible_n=10, top63_n=150,
                          top63_never_eligible_pct=0.07)
    block = PMA.name_score_scorecard(root)
    block["by_horizon"]["21d"]["rank_ic"] = -0.42          # a bad measurement...
    block["by_horizon"]["21d"]["precision_at_k"]["by_k"]["p_at_1"]["value"] = 0.0
    doc["name_score_scorecard"] = block
    assert PMA.emit_annotations(doc) == [], "telemetry must never page on its own reading"
    assert [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::")] == []


# ---------------------------------------------------------------------------
# zero authority — nothing outside the runner + tests may import this
# ---------------------------------------------------------------------------
def test_no_module_outside_the_runner_imports_the_audit():
    """ZERO AUTHORITY (masterplan W0): no rank/gate/size path may read this instrument."""
    root = Path(__file__).resolve().parent.parent
    # The §4.5 scan lane is the SAME instrument over a wider seeing set, at the
    # same tier (ops telemetry, zero authority) — so its runner and test join the
    # allowlist rather than forking the excluder attribution into a second module.
    # The guard keeps its teeth: no engine scoring path, app, admin or collector
    # may still name this module.
    allowed = {"engine/prophet_miss_audit.py", "scripts/run_prophet_miss_audit.py",
               "tests/test_prophet_miss_audit.py",
               "scripts/run_us_scan_tier.py", "tests/test_us_scan_tier.py",
               # W7: the priority_score_scorecard block reads the full-population grade
               # store, and its tests live beside that store's suite (which is wired into a
               # CI pack) rather than here. A TEST importing the audit is not an authority
               # path — the fence is about production modules — so the allowance is scoped
               # to that one file, not widened to tests/*.
               "tests/test_us_prophet_grades.py",
               # 2026-08-06: the off-engine-lane suite names this module because the audit
               # is one of the four steps it pins into the us_prophet_ledgers job, and it
               # imports ARTIFACT_REL/FORWARD_LOG_REL so the commit step's `git add` list
               # is DERIVED from the writer rather than copied out of the workflow. Same
               # scoping as above: one named test file, no authority path.
               "tests/test_prophet_off_engine_lane.py",
               # 2026-08-07 (#4715): this one does not IMPORT the audit at all — it names
               # the module in a price-basis annotation table, as the value
               # "INHERITS: reads excess_spy from a ledger, does not compute it". The
               # check below is a substring sweep over the file, not an import graph, so
               # documenting that the audit derives rather than computes reads as an
               # authority path to it. That assertion is the fence's own claim, so the
               # allowance is the same one-named-file scoping as the entries above.
               "tests/test_price_basis_graders.py"}
    offenders = []
    for d in ("engine", "scripts", "app", "admin", "collectors", "lib", "tools", "tests"):
        for p in (root / d).rglob("*.py"):
            rel = p.relative_to(root).as_posix()
            if rel in allowed:
                continue
            try:
                blob = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if "prophet_miss_audit" in blob:
                offenders.append(rel)
    assert not offenders, (
        "prophet_miss_audit is ops telemetry with ZERO authority — it must not be imported "
        "by any other module:\n  " + "\n  ".join(sorted(offenders))
    )
