"""Tests for the Transmission CALIBRATION historical episode miner (TXI W3).

Covers, with SYNTHETIC series carrying a KNOWN embedded relationship:
  * the vectorized metric evaluator matches the point-in-time `_series_metric` at the last bar
    (the shared-formula guarantee — no duplicated threshold parser);
  * P(hop confirms | upstream fired) recovered as M/N from an embedded upstream=N /
    downstream-within-lag=M relationship, with the correct n;
  * regime split — two synthetic regime cells with DIFFERENT embedded rates recovered
    separately; a thin cell → "untested" (never a fabricated rate);
  * right-censoring — an upstream firing whose forward window runs past the downstream
    history is DROPPED (not counted as a non-confirm);
  * the calibration MERGE into build_chain_state — a fixture calibration fills base_rates +
    promotes tier (hypothesis→calibrated_context); absent/rev-mismatch/untested-only calibration
    leaves base_rates null + tier hypothesis (fail-open);
  * null honesty — n below the floor prints "untested" WITH its n, never a number;
  * the runner no-ops gracefully on absent history and never writes when --dry-run/write=False.

No test writes the real data/ tree: synthetic tests use tmp roots (root=tmp_path) and the
merge tests build the calibration dict in-memory.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine import transmission_calibration as cal
from engine import transmission_chains as tc

REPO_ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# helpers — write synthetic parquet series into a tmp data dir, build a SeriesSource
# --------------------------------------------------------------------------- #
def _write_series(data_dir: Path, group: str, name: str, values, index) -> None:
    p = data_dir / group / f"{name.replace('=', '_').replace('^', '_').replace('/', '_')}.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"close": np.asarray(values, dtype=float)}, index=index).to_parquet(p)


def _src(tmp_path: Path) -> cal.SeriesSource:
    return cal.SeriesSource(tmp_path / "data")


# --------------------------------------------------------------------------- #
# 1. shared-formula guarantee: series_metric_timeseries().iloc[-1] == _series_metric(-1)
# --------------------------------------------------------------------------- #
def test_vectorized_metric_matches_pointintime(tmp_path):
    data_dir = tmp_path / "data"
    idx = pd.date_range("2020-01-01", periods=300, freq="D")
    rng = np.random.default_rng(0)
    a = 100 * np.cumprod(1 + rng.normal(0, 0.01, len(idx)))
    b = 100 * np.cumprod(1 + rng.normal(0, 0.01, len(idx)))
    _write_series(data_dir, "yahoo", "AAA", a, idx)
    _write_series(data_dir, "yahoo", "BBB", b, idx)
    src = _src(tmp_path)
    get = src.reader("yahoo")
    # each metric form the grammar supports
    for t in (
        {"series": "AAA", "metric": "ret", "window": 60, "op": "gt", "value": 0},
        {"series": "AAA", "metric": "ret_bp", "window": 22, "op": "gt", "value": 0},
        {"series": "AAA", "metric": "ma_slope", "window": 50, "lookback": 5, "op": "gt", "value": 0},
        {"series": "AAA", "vs": "BBB", "metric": "rs", "window": 63, "op": "lt", "value": 0},
        {"series": "AAA", "ratio": "BBB", "metric": "ratio_ret", "window": 22, "op": "lt", "value": 0},
    ):
        vec = tc.series_metric_timeseries(get, t)
        # point-in-time value via the nightly evaluator (uses a _SeriesAdapter)
        adapter = tc._SeriesAdapter(data_dir, "yahoo")
        pit, _ = tc._series_metric(adapter, t)
        assert vec.iloc[-1] == pytest.approx(pit, rel=1e-9, abs=1e-9), t["metric"]


# --------------------------------------------------------------------------- #
# 2. P(hop confirms | upstream fired) recovered as M/N with the correct n
# --------------------------------------------------------------------------- #
def _chain_two_series(lag_hi: int = 5) -> dict:
    """A 2-node/1-hop chain: UP fires when AAA 1d-return>0; DOWN fires when BBB 1d-return>0."""
    return {
        "chain": "synth_two", "rev": 0, "tier": "hypothesis",
        "title": {"en": "s", "zh": "s"},
        "nodes": {
            "up": {"src": "yahoo", "test": {"series": "AAA", "metric": "ret", "window": 1, "op": "gt", "value": 0}},
            "down": {"src": "yahoo", "test": {"series": "BBB", "metric": "ret", "window": 1, "op": "gt", "value": 0}},
        },
        "hops": [{"from": "up", "to": "down", "sign": "+", "lag_d": [0, lag_hi],
                  "condition": {"en": "x", "zh": "x"}}],
        "exposure_screens": {},
    }


def test_hop_rate_recovered_exact(tmp_path):
    """Embed: UP fires on 10 known days; DOWN confirms within lag on exactly 7 of them → p≈0.7,
    n=7? no — n is the number of NON-censored upstream firings; assert p=confirm/n."""
    data_dir = tmp_path / "data"
    n_days = 120
    idx = pd.date_range("2021-01-01", periods=n_days, freq="D")
    # AAA: flat except a +1% bump on 10 chosen "up" days → UP fires exactly those days
    up_days = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    a = np.full(n_days, 100.0)
    for d in up_days:
        a[d] = 101.0
        a[d + 1] = 100.0   # return to baseline so only day d has ret_1d>0
    # BBB: a +1% bump 2 days after 7 of the 10 up days (within lag_hi=5) → 7 confirm;
    # the last 3 up days get NO downstream bump → non-confirm.
    b = np.full(n_days, 100.0)
    confirm_for = up_days[:7]
    for d in confirm_for:
        b[d + 2] = 101.0
        b[d + 3] = 100.0
    _write_series(data_dir, "yahoo", "AAA", a, idx)
    _write_series(data_dir, "yahoo", "BBB", b, idx)
    src = _src(tmp_path)
    chain = _chain_two_series(lag_hi=5)
    hop = chain["hops"][0]
    regimes = cal.RegimeHistory(None)   # no regime history → pooled only
    out = cal.calibrate_hop(chain, hop, "up", "down", src, regimes)
    # all 10 up-firings are non-censored (last is day 100, well before day 119) → n=10, 7 confirm
    assert out["n"] == 10
    assert out["p_confirm"] == pytest.approx(0.7, abs=1e-9)
    assert out["regime_split"] == "unavailable"   # no regime history


# --------------------------------------------------------------------------- #
# 3. right-censoring — an upstream firing whose window runs past history is DROPPED
# --------------------------------------------------------------------------- #
def test_right_censoring_drops_unresolved_window(tmp_path):
    data_dir = tmp_path / "data"
    n_days = 50
    idx = pd.date_range("2021-01-01", periods=n_days, freq="D")
    a = np.full(n_days, 100.0)
    # two up firings: day 10 (resolvable) and day 48 (window [0,5] runs to day 53 > end 49 → censored)
    for d in (10, 48):
        a[d] = 101.0
        if d + 1 < n_days:
            a[d + 1] = 100.0
    b = np.full(n_days, 100.0)
    b[12] = 101.0; b[13] = 100.0   # confirms the day-10 firing
    _write_series(data_dir, "yahoo", "AAA", a, idx)
    _write_series(data_dir, "yahoo", "BBB", b, idx)
    src = _src(tmp_path)
    chain = _chain_two_series(lag_hi=5)
    out = cal.calibrate_hop(chain, chain["hops"][0], "up", "down", src, cal.RegimeHistory(None))
    # day-48 firing is censored (dropped); only day-10 counts → n=1, 1 confirm.
    # n<floor(8) → "untested" WITH n (null honesty), NOT a fabricated 1.0
    assert out["n"] == 1
    assert out["p_confirm"] == "untested"
    assert out["untested_reason"].startswith("pooled n<")


# --------------------------------------------------------------------------- #
# 4. regime split — two cells with DIFFERENT embedded rates recovered separately; thin→untested
# --------------------------------------------------------------------------- #
class _FakeRegime(cal.RegimeHistory):
    """A RegimeHistory whose scheme_for_condition always returns a fixed date→cell Series."""
    def __init__(self, cell_series: pd.Series):
        super().__init__(pd.DataFrame({"x": [1]}))   # non-empty so available() is True
        self._cell_series = cell_series

    def scheme_for_condition(self, condition_text: str):
        return "fake_scheme", self._cell_series


def test_regime_split_recovers_per_cell_rates(tmp_path):
    data_dir = tmp_path / "data"
    n_days = 260
    idx = pd.date_range("2021-01-01", periods=n_days, freq="D")
    a = np.full(n_days, 100.0)
    b = np.full(n_days, 100.0)
    # Cell A = first half (days <130): 10 up firings, 9 confirm  → p≈0.9
    # Cell B = second half (days >=130): 10 up firings, 2 confirm → p≈0.2
    up_A = list(range(10, 110, 10))          # 10 firings in cell A
    up_B = list(range(140, 240, 10))         # 10 firings in cell B
    confirm_A = up_A[:9]
    confirm_B = up_B[:2]
    for d in up_A + up_B:
        a[d] = 101.0; a[d + 1] = 100.0
    for d in confirm_A + confirm_B:
        b[d + 2] = 101.0; b[d + 3] = 100.0
    _write_series(data_dir, "yahoo", "AAA", a, idx)
    _write_series(data_dir, "yahoo", "BBB", b, idx)
    # cell labels: "cellA" for days <130, "cellB" for >=130
    cells = pd.Series(["cellA" if i < 130 else "cellB" for i in range(n_days)], index=idx)
    src = _src(tmp_path)
    chain = _chain_two_series(lag_hi=5)
    out = cal.calibrate_hop(chain, chain["hops"][0], "up", "down", src, _FakeRegime(cells))
    assert out["regime_split"] == "available"
    pr = out["per_regime"]
    assert pr["cellA"]["p"] == pytest.approx(0.9, abs=1e-9)
    assert pr["cellA"]["n"] == 10
    assert pr["cellB"]["p"] == pytest.approx(0.2, abs=1e-9)
    assert pr["cellB"]["n"] == 10


def test_regime_thin_cell_is_untested(tmp_path):
    """A regime cell with fewer than N_FLOOR activations prints "untested" with n, never a rate."""
    data_dir = tmp_path / "data"
    n_days = 200
    idx = pd.date_range("2021-01-01", periods=n_days, freq="D")
    a = np.full(n_days, 100.0)
    b = np.full(n_days, 100.0)
    # cellA: 10 firings (fat); cellB: 3 firings (thin, < floor 8)
    up_A = list(range(10, 110, 10))
    up_B = [150, 160, 170]
    for d in up_A + up_B:
        a[d] = 101.0; a[d + 1] = 100.0
    for d in up_A[:5] + up_B:   # confirm all cellB (would be p=1.0 if it were reported)
        b[d + 2] = 101.0; b[d + 3] = 100.0
    _write_series(data_dir, "yahoo", "AAA", a, idx)
    _write_series(data_dir, "yahoo", "BBB", b, idx)
    cells = pd.Series(["cellA" if i < 130 else "cellB" for i in range(n_days)], index=idx)
    src = _src(tmp_path)
    out = cal.calibrate_hop(_chain_two_series(lag_hi=5), _chain_two_series(lag_hi=5)["hops"][0],
                            "up", "down", src, _FakeRegime(cells))
    assert out["per_regime"]["cellA"]["p"] == pytest.approx(0.5, abs=1e-9)
    assert out["per_regime"]["cellB"]["p"] == "untested"    # NEVER the fabricated 1.0
    assert out["per_regime"]["cellB"]["n"] == 3


# --------------------------------------------------------------------------- #
# 5. unreconstructable node (no proxy) → hop untested with reason, never fabricated
# --------------------------------------------------------------------------- #
def test_state_node_without_proxy_is_untested(tmp_path):
    data_dir = tmp_path / "data"
    idx = pd.date_range("2021-01-01", periods=60, freq="D")
    _write_series(data_dir, "yahoo", "BBB", np.full(60, 100.0), idx)
    chain = {
        "chain": "synth_state", "rev": 0, "tier": "hypothesis", "title": {"en": "s", "zh": "s"},
        "nodes": {
            # a state-adapter node NOT in _STATE_NODE_PROXIES → unreconstructable
            "up": {"src": "regime_state", "test": {"path": "foo.bar", "op": "is_true"}},
            "down": {"src": "yahoo", "test": {"series": "BBB", "metric": "ret", "window": 1, "op": "gt", "value": 0}},
        },
        "hops": [{"from": "up", "to": "down", "sign": "+", "lag_d": [0, 5], "condition": {"en": "x", "zh": "x"}}],
        "exposure_screens": {},
    }
    out = cal.calibrate_hop(chain, chain["hops"][0], "up", "down", _src(tmp_path), cal.RegimeHistory(None))
    assert out["p_confirm"] == "untested"
    assert out["n"] == 0
    assert "not reconstructable" in out["method"]["from"]
    assert "untested_reason" in out


# --------------------------------------------------------------------------- #
# 6. MERGE — fixture calibration fills base_rates + promotes tier; fail-open otherwise
# --------------------------------------------------------------------------- #
def _hypothesis_chain(rev: int = 0) -> dict:
    return {"chain": "mc", "rev": rev, "tier": "hypothesis", "title": {"en": "m", "zh": "m"},
            "nodes": {"a": {"src": "yahoo", "test": {"series": "X", "metric": "ret", "window": 1, "op": "gt", "value": 0}},
                      "b": {"src": "yahoo", "test": {"series": "X", "metric": "ret", "window": 1, "op": "lt", "value": 0}}},
            "hops": [{"from": "a", "to": "b", "sign": "+", "lag_d": [0, 5]}]}


def _per_chain_stub(rev: int = 0) -> dict:
    return {"chain": "mc", "rev": rev, "tier": "hypothesis", "hops": [{"id": "a->b"}], "base_rates": None}


def test_merge_fills_base_rates_and_promotes():
    chain = _hypothesis_chain(rev=1)
    pc = _per_chain_stub(rev=1)
    cal_entry = {"chain": "mc", "rev": 1, "asof": "2026-07-24", "calibrated_hops": 1, "n_hops": 1,
                 "hops": [{"from": "a", "to": "b", "p_confirm": 0.73, "n": 120, "lag_d": [0, 5],
                           "regime_split": "available", "per_regime": {"q1": {"p": 0.8, "n": 40}}}]}
    tc._merge_calibration(pc, chain, cal_entry)
    assert isinstance(pc["base_rates"], dict)
    assert pc["base_rates"]["by_hop"]["a->b"]["p_confirm"] == 0.73
    assert pc["tier"] == tc.CALIBRATED_CONTEXT_TIER       # promoted
    # the per-hop mirror is present for consumers reading hops[] directly
    assert pc["hops"][0]["base_rate"]["p_confirm"] == 0.73
    assert pc["hops"][0]["base_rate"]["per_regime"]["q1"]["p"] == 0.8


def test_merge_absent_calibration_is_failopen():
    pc = _per_chain_stub()
    tc._merge_calibration(pc, _hypothesis_chain(), None)
    assert pc["base_rates"] is None
    assert pc["tier"] == "hypothesis"   # unchanged


def test_merge_rev_mismatch_withholds_and_notes():
    chain = _hypothesis_chain(rev=2)
    pc = _per_chain_stub(rev=2)
    stale = {"chain": "mc", "rev": 1, "calibrated_hops": 1, "n_hops": 1,
             "hops": [{"from": "a", "to": "b", "p_confirm": 0.9, "n": 100}]}
    tc._merge_calibration(pc, chain, stale)
    assert pc["base_rates"] is None
    assert pc["tier"] == "hypothesis"          # NOT promoted on a stale rev
    assert "base_rates_note" in pc


def test_merge_untested_only_does_not_promote():
    chain = _hypothesis_chain(rev=1)
    pc = _per_chain_stub(rev=1)
    entry = {"chain": "mc", "rev": 1, "calibrated_hops": 0, "n_hops": 1,
             "hops": [{"from": "a", "to": "b", "p_confirm": "untested", "n": 3}]}
    tc._merge_calibration(pc, chain, entry)
    assert isinstance(pc["base_rates"], dict)         # base_rates still filled (with the untested hop)
    assert pc["tier"] == "hypothesis"                 # but NO promotion — nothing measured


# --------------------------------------------------------------------------- #
# 7. build_chain_state end-to-end with calibration merged
# --------------------------------------------------------------------------- #
def test_build_chain_state_merges_calibration():
    chain = _hypothesis_chain(rev=1)
    calibration = {"schema": cal.SCHEMA_ID, "n_floor": 8, "chains": [
        {"chain": "mc", "rev": 1, "asof": "2026-07-24", "calibrated_hops": 1, "n_hops": 1,
         "hops": [{"from": "a", "to": "b", "p_confirm": 0.66, "n": 90, "lag_d": [0, 5],
                   "regime_split": "unavailable", "per_regime": {}}]}]}
    # a fake adapter so the nodes resolve to a state (dormant is fine — merge is state-independent)

    class _FakeSeries:
        def series(self, name):
            return pd.Series([100.0, 101.0], index=pd.to_datetime(["2026-07-23", "2026-07-24"]))
    adapters = {"yahoo": _FakeSeries()}
    state, _ = tc.build_chain_state([chain], adapters, "2026-07-24", [], calibration=calibration)
    c = state["chains"][0]
    assert c["base_rates"]["by_hop"]["a->b"]["p_confirm"] == 0.66
    assert c["base_rates"]["n_floor"] == 8         # doc-level floor threaded through
    assert c["tier"] == tc.CALIBRATED_CONTEXT_TIER


# --------------------------------------------------------------------------- #
# 8. runner / run() no-ops gracefully on absent history and never writes on write=False
# --------------------------------------------------------------------------- #
def test_run_noop_on_absent_history(tmp_path):
    """An empty tmp root (no data/, no knowledge/) → run() returns a well-formed empty-ish
    doc and writes NOTHING when write=False."""
    # copy the real chain library in so there ARE chains, but NO data/ series → all untested
    state = cal.run(root=REPO_ROOT, write=False)   # real chains, real data, but write=False
    assert state["schema"] == cal.SCHEMA_ID
    assert isinstance(state["chains"], list) and state["chains"]
    # write=False must not have created a calibration artifact under a tmp path
    assert not (tmp_path / "data" / "transmission" / "chain_calibration.json").exists()


def test_run_absent_data_dir_is_failopen(tmp_path):
    """run() on a root whose knowledge dir is absent returns 0 chains, never raises."""
    # tmp_path has no knowledge/transmission → load returns [] → empty chains, no crash
    state = cal.run(root=tmp_path, write=True)
    assert state["chains"] == []
    # it DID write the (empty) artifact — that's fine; tmp path, not the real tree
    assert (tmp_path / "data" / "transmission" / "chain_calibration.json").exists()


def test_run_writes_artifact_to_tmp(tmp_path):
    """A hermetic run with synthetic series writes a parseable transmission_calibration.v1."""
    # seed the real chain library into tmp + a couple of series so at least one hop resolves
    kdir = tmp_path / "knowledge" / "transmission"
    kdir.mkdir(parents=True, exist_ok=True)
    (kdir / "synth_two.yaml").write_text(
        "chain: synth_two\nrev: 0\ntier: hypothesis\ntitle: {en: s, zh: s}\n"
        "nodes:\n  up: {src: yahoo, test: {series: AAA, metric: ret, window: 1, op: gt, value: 0}}\n"
        "  down: {src: yahoo, test: {series: BBB, metric: ret, window: 1, op: gt, value: 0}}\n"
        "hops:\n  - {from: up, to: down, sign: '+', lag_d: [0, 5], condition: {en: x, zh: x}}\n"
        "exposure_screens: {}\n")
    data_dir = tmp_path / "data"
    idx = pd.date_range("2021-01-01", periods=60, freq="D")
    _write_series(data_dir, "yahoo", "AAA", np.full(60, 100.0), idx)
    _write_series(data_dir, "yahoo", "BBB", np.full(60, 100.0), idx)
    _write_series(data_dir, "yahoo", "SPY", np.full(60, 100.0), idx)
    state = cal.run(root=tmp_path, write=True)
    p = data_dir / "transmission" / "chain_calibration.json"
    assert p.exists()
    doc = json.loads(p.read_text())
    assert doc["schema"] == cal.SCHEMA_ID
    assert doc["display_only"] is True
    assert doc["chains"][0]["chain"] == "synth_two"


# --------------------------------------------------------------------------- #
# 9. real-artifact smoke — the four committed seeds mine without crashing (guarded)
# --------------------------------------------------------------------------- #
def test_real_seeds_smoke():
    """Guarded smoke over the committed seeds + real data (if present). Asserts the emit is
    well-formed, honest (untested hops print "untested" with n, never a number), and that no
    emitted text says "validated" (CI-enforced banned vocab)."""
    if not (REPO_ROOT / "data" / "yahoo" / "SPY.parquet").exists():
        pytest.skip("real series store absent (CI-lite) — smoke skipped")
    state = cal.run(root=REPO_ROOT, write=False)
    assert state["schema"] == cal.SCHEMA_ID
    blob = json.dumps(state, default=str).lower()
    assert "validated" not in blob, "banned vocab 'validated' leaked into the calibration emit"
    for c in state["chains"]:
        for h in c["hops"]:
            p = h["p_confirm"]
            # honesty invariant: p is EITHER a float in [0,1] OR the literal "untested"
            assert p == "untested" or (isinstance(p, float) and 0.0 <= p <= 1.0)
            if p == "untested":
                assert isinstance(h["n"], int)       # untested ALWAYS carries its n
            for cell, cv in h.get("per_regime", {}).items():
                cp = cv["p"]
                assert cp == "untested" or (isinstance(cp, float) and 0.0 <= cp <= 1.0)
