"""International bridge harness (scripts/intl_phase0.py + engine/intl_claims.py) — W1.

The harness COMPOSES the anti-overfit stack (trial_ledger + promotion_gate + validation)
and adds the intl-specific gates (orthogonality, crisis-count N, crisis-independent ES,
lead-lag kernel, freshness). These tests guard:

  * the ledger SCHEMA round-trips (the sibling engine/intl_feed.py reads this exact shape),
  * gate composition on synthetic data — a known-GOOD de-risk leg → CONFIRMED, a known-JUNK
    leg → not CONFIRMED,
  * backfill DETERMINISM (same bytes every run — the registry starts truthful, reproducibly),
  * --declare IDEMPOTENCY (the trial ledger dedups, so re-runs do NOT inflate N).
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from engine import intl_claims  # noqa: E402
from engine.trial_ledger import TrialLedger  # noqa: E402
import scripts.intl_phase0 as H  # noqa: E402


# --------------------------------------------------------------------------- #
# fixtures — synthetic causal builders
# --------------------------------------------------------------------------- #
def _dates(n):
    # span 2000→ so the synthetic sample covers dotcom/gfc/eurozone/covid/rate (≥3 crises)
    return pd.date_range("2000-01-01", periods=n, freq="B")


def _good_builder(claim):
    """A known-GOOD de-risk leg: a signal that (i) is orthogonal to the basis and predicts
    forward drawdown, (ii) rests on multiple crises, (iii) reduces tail ES, (iv) has a
    positive, high-DSR strategy return, split-half consistent."""
    rng = np.random.default_rng(7)
    n = 6600
    idx = _dates(n)
    # bench: a broad equity path with fat left-tail crises
    bench = pd.Series(rng.normal(0.0003, 0.011, n), index=idx)
    # a signal that leads drawdowns: high when a crash is coming
    fwd_dd = bench.rolling(21).apply(lambda x: (1 + x).cumprod().min() - 1, raw=True).shift(-21)
    signal = (-fwd_dd).fillna(0) + rng.normal(0, 0.002, n)      # correlated with future DD, noisy
    signal = pd.Series(signal.values, index=idx)
    # a de-risk strategy: flat when the signal is high → cuts the tail, positive net edge
    pos = 1.0 - (signal > signal.quantile(0.85)).astype(float)
    strat = pos.shift(1).fillna(1.0) * bench + rng.normal(0.0004, 0.001, n)
    basis = [pd.Series(rng.normal(0, 1, n), index=idx) for _ in range(3)]   # unrelated legs
    target_dd = fwd_dd.fillna(0)
    return {"signal": signal, "strat_ret": strat, "bench_ret": bench, "target_dd": target_dd,
            "basis": basis, "ic": 0.08, "split_half_same_sign": True}


def _junk_builder(claim):
    """A known-JUNK leg: pure noise. No orthogonal DD content, no crisis structure, a
    coin-flip strategy return, split-half sign-unstable."""
    rng = np.random.default_rng(11)
    n = 6600
    idx = _dates(n)
    bench = pd.Series(rng.normal(0.0003, 0.011, n), index=idx)
    signal = pd.Series(rng.normal(0, 1, n), index=idx)
    strat = pd.Series(rng.normal(0, 0.011, n), index=idx)       # no edge
    basis = [pd.Series(rng.normal(0, 1, n), index=idx) for _ in range(3)]
    return {"signal": signal, "strat_ret": strat, "bench_ret": bench,
            "target_dd": pd.Series(rng.normal(0, 0.05, n), index=idx),
            "basis": basis, "ic": 0.0, "split_half_same_sign": False}


def _claim():
    return dict(intl_claims.CLAIMS[1])   # c2_intl_macro_sleeve — a de-risk claim


# --------------------------------------------------------------------------- #
# 1. declared grid + claim declaration integrity
# --------------------------------------------------------------------------- #
def test_declared_grid_covers_every_claim_and_horizon():
    grid = intl_claims.declared_grid()
    # one config per (claim, horizon); no claim is silently dropped
    expect = sum(len(c["horizons"]) for c in intl_claims.CLAIMS)
    assert len(grid) == expect
    ids = {g["claim"] for g in grid}
    assert ids == {c["id"] for c in intl_claims.CLAIMS}
    for g in grid:
        assert g["channel"].startswith("C") and g["direction"] in ("de-risk", "add-tilt")
        assert isinstance(g["horizon"], int)


def test_every_claim_declares_the_contract_fields():
    for c in intl_claims.CLAIMS:
        for k in ("id", "channel", "hypothesis", "direction", "target", "horizons",
                  "source_series", "freshness_sla_days"):
            assert k in c, f"{c.get('id')} missing {k}"
        assert c["direction"] in ("de-risk", "add-tilt")
        assert c["id"].islower() and " " not in c["id"]     # snake_case


# --------------------------------------------------------------------------- #
# 2. --declare idempotency (trial_ledger dedup → re-runs don't inflate N)
# --------------------------------------------------------------------------- #
def test_declare_is_idempotent():
    led = TrialLedger(Path(tempfile.mkdtemp()) / "led.jsonl")
    first = H.declare(led)
    n1 = led.effective_n(H.FAMILY)
    second = H.declare(led)                                  # re-declare
    n2 = led.effective_n(H.FAMILY)
    grid = intl_claims.declared_grid()
    assert first == len(grid)          # first declare logs the whole grid
    assert second == 0                 # nothing newly-distinct on re-run
    assert n1 == n2 == len(grid)       # N does not grow (dedup by content hash)


def test_declare_survives_process_restart():
    p = Path(tempfile.mkdtemp()) / "led.jsonl"
    H.declare(TrialLedger(p))
    reloaded = TrialLedger(p)                                # fresh handle rebuilds from disk
    assert reloaded.effective_n(H.FAMILY) == len(intl_claims.declared_grid())


# --------------------------------------------------------------------------- #
# 3. gate composition on synthetic data (good → CONFIRMED, junk → not)
# --------------------------------------------------------------------------- #
def test_good_leg_grades_confirmed_with_bounded_cap():
    led = TrialLedger(Path(tempfile.mkdtemp()) / "led.jsonl")
    led.log_grid([{"i": i} for i in range(12)], family=H.FAMILY)   # a few honest trials
    row = H.grade_claim(_claim(), led, asof=date(2004, 1, 1), builder=_good_builder)
    assert row["verdict"] in ("CONFIRMED", "DIRECTIONAL"), row["notes"]
    # a de-risk leg's cap is bounded and never exceeds the hard max
    assert 0.0 < row["weight_cap"] <= H.MAX_WEIGHT_CAP
    assert row["metrics"]["dsr"] is not None
    assert row["gates"]["crisis_count"] is True


def test_junk_leg_is_not_confirmed_and_not_sized():
    led = TrialLedger(Path(tempfile.mkdtemp()) / "led.jsonl")
    led.log_grid([{"i": i} for i in range(12)], family=H.FAMILY)
    row = H.grade_claim(_claim(), led, asof=date(2004, 1, 1), builder=_junk_builder)
    assert row["verdict"] in ("CONTEXT", "INVERTED", "PENDING")
    assert row["weight_cap"] == 0.0                          # never sized


def test_no_builder_grades_pending_but_declares():
    """The W1 default: a claim with no builder DECLARES its budget but grades PENDING —
    the honest empty-but-declared state, never a silent pass."""
    led = TrialLedger(Path(tempfile.mkdtemp()) / "led.jsonl")
    row = H.grade_claim(_claim(), led, asof=date(2004, 1, 1), builder=None)
    assert row["verdict"] == "PENDING" and row["weight_cap"] == 0.0


# --------------------------------------------------------------------------- #
# 4. freshness gate — fail-closed on a stale on-disk series
# --------------------------------------------------------------------------- #
def test_freshness_gate_fails_closed_on_stale(monkeypatch):
    claim = {"source_series": [("g", "s")], "freshness_sla_days": 3}
    # a print 13 days old vs a 3-day SLA must trip the gate
    monkeypatch.setattr(H.store, "last_date", lambda g, n: date(2026, 1, 1))
    g = H.freshness_gate(claim, asof=date(2026, 1, 14))
    assert g["pass"] is False and "g/s" in g["stale"]
    # and a fresh print passes
    monkeypatch.setattr(H.store, "last_date", lambda g, n: date(2026, 1, 13))
    assert H.freshness_gate(claim, asof=date(2026, 1, 14))["pass"] is True


def test_stale_source_forces_pending_verdict(monkeypatch):
    """A stale critical series zeroes the leg regardless of a good builder (§4.2 gate 6)."""
    monkeypatch.setattr(H.store, "last_date", lambda g, n: date(2000, 1, 1))   # ancient
    led = TrialLedger(Path(tempfile.mkdtemp()) / "led.jsonl")
    row = H.grade_claim(_claim(), led, asof=date(2026, 1, 1), builder=_good_builder)
    assert row["verdict"] == "PENDING" and row["weight_cap"] == 0.0


# --------------------------------------------------------------------------- #
# 5. backfill — schema round-trip + determinism
# --------------------------------------------------------------------------- #
_LEDGER_KEYS = {"id", "channel", "hypothesis", "direction", "verdict", "weight_cap",
                "metrics", "gates", "source_series", "freshness_sla_days",
                "validation_ref", "kill", "notes"}
_METRIC_KEYS = {"ic", "dsr", "split_half_same_sign", "effective_n_crises",
                "es_ex_top3", "orthogonal_partial"}


def _read_ledger():
    return json.loads(H._ledger_path().read_text())


def test_backfill_writes_schema_conformant_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(H.config, "data_dir", lambda: tmp_path)
    H.backfill()
    payload = _read_ledger()
    assert payload["family"] == "intl_bridge"
    assert set(payload.keys()) == {"asof", "family", "features"}
    assert len(payload["features"]) == len(intl_claims.BACKFILL)
    for f in payload["features"]:
        assert set(f.keys()) == _LEDGER_KEYS, f"feature {f.get('id')} keys drift"
        assert set(f["metrics"].keys()) == _METRIC_KEYS
        assert f["verdict"] in ("CONFIRMED", "DIRECTIONAL", "CONTEXT", "INVERTED", "PENDING")
        assert 0.0 <= f["weight_cap"] <= 1.0
        assert f["validation_ref"], "every entry must quote its report"
        assert isinstance(f["kill"], bool)


def test_backfill_is_deterministic(tmp_path, monkeypatch):
    monkeypatch.setattr(H.config, "data_dir", lambda: tmp_path)
    H.backfill()
    a = H._ledger_path().read_text()
    H.backfill()
    b = H._ledger_path().read_text()
    # the evidence rows are byte-identical across runs (asof is the only date field, same day)
    ja, jb = json.loads(a), json.loads(b)
    assert ja["features"] == jb["features"]


def test_backfill_encodes_the_expected_verdicts(tmp_path, monkeypatch):
    monkeypatch.setattr(H.config, "data_dir", lambda: tmp_path)
    H.backfill()
    by_id = {f["id"]: f for f in _read_ledger()["features"]}
    # W2 (C2): graded against the US-book target → CONTEXT (DSR 0.83 < the 0.90 door;
    # residual DD-content vs the 5 US MRS legs marginal). Was PENDING in W1.
    assert by_id["c2_intl_macro_sleeve"]["verdict"] == "CONTEXT"
    assert by_id["c2_intl_macro_sleeve"]["kill"] is True
    assert by_id["intl_trend_overlay"]["verdict"] == "CONTEXT"
    assert by_id["intl_tr_trend"]["verdict"] == "CONTEXT"
    assert by_id["forex_per_pair_conviction"]["verdict"] == "CONTEXT"
    assert by_id["c4_reer_value"]["verdict"] == "PENDING"
    assert by_id["crossmarket_leadlag"]["verdict"] == "CONTEXT"
    assert by_id["cn_external_radar"]["verdict"] == "CONTEXT"
    # W2-C3 update: c3_global_etf_breadth is CONFIRMED (live run 2026-07-02) with non-zero cap;
    # all OTHER backfill entries remain un-sized (not wired into any scorer)
    assert by_id["c3_global_etf_breadth"]["verdict"] == "CONFIRMED"
    assert by_id["c3_global_etf_breadth"]["weight_cap"] > 0.0
    non_c3 = [f for f in by_id.values() if f["id"] != "c3_global_etf_breadth"]
    assert all(f["weight_cap"] == 0.0 for f in non_c3), (
        "all non-C3 backfill entries must remain un-sized until their own gates run")
    # the strongest prior quotes its exact report path
    assert "intl-macro-sleeve-phase0.md" in by_id["c2_intl_macro_sleeve"]["validation_ref"]


# --------------------------------------------------------------------------- #
# 6. run() — dotted-path builder resolution + merge-preserves-graveyard (W2)
# --------------------------------------------------------------------------- #
def test_run_with_no_builders_grades_every_claim_pending(tmp_path, monkeypatch):
    """With data_dir at an empty tmp (no source parquets → freshness fail-closed) and no
    explicit builders, every CLAIM grades PENDING — the honest declared-but-unmeasured state."""
    monkeypatch.setattr(H.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(H, "TrialLedger", lambda *a, **k: TrialLedger(tmp_path / "led.jsonl"))
    H.run(builders={})
    by_id = {f["id"]: f for f in _read_ledger()["features"]}
    assert by_id["c1_china_global_beta"]["verdict"] == "PENDING"
    assert by_id["c2_intl_macro_sleeve"]["verdict"] == "PENDING"    # no data on the empty tmp
    assert all(f["weight_cap"] == 0.0 for f in by_id.values())      # nothing wired


def test_run_merge_preserves_graveyard_only_rows(tmp_path, monkeypatch):
    """merge=True overlays freshly-graded CLAIM rows onto the EXISTING ledger, so graveyard-
    only evidence rows (not in CLAIMS — e.g. crossmarket_leadlag) are never clobbered. This
    guards the 'never regress a known verdict' contract across re-runs."""
    monkeypatch.setattr(H.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(H, "TrialLedger", lambda *a, **k: TrialLedger(tmp_path / "led.jsonl"))
    # seed an existing ledger with a graveyard-only row + a stale CLAIM row
    H.backfill()   # writes the BACKFILL evidence (incl. crossmarket_leadlag, not a CLAIM)
    H.run(builders={})   # regrade the CLAIMS; graveyard-only rows must survive the merge
    by_id = {f["id"]: f for f in _read_ledger()["features"]}
    assert "crossmarket_leadlag" in by_id, "graveyard-only backfill row was clobbered"
    assert by_id["crossmarket_leadlag"]["verdict"] == "CONTEXT"
    assert all(f["weight_cap"] == 0.0 for f in by_id.values())


def test_run_only_scopes_the_regrade(tmp_path, monkeypatch):
    """`only=` restricts the regrade to the named claim ids; the rest keep their ledger rows."""
    monkeypatch.setattr(H.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(H, "TrialLedger", lambda *a, **k: TrialLedger(tmp_path / "led.jsonl"))
    H.backfill()
    before = {f["id"]: f for f in _read_ledger()["features"]}
    H.run(builders={}, only={"c1_china_global_beta"})
    after = {f["id"]: f for f in _read_ledger()["features"]}
    # the un-scoped c4_reer_value row is untouched (kept from the existing ledger)
    assert after["c4_reer_value"] == before["c4_reer_value"]


# --------------------------------------------------------------------------- #
# 7. lead-lag kernel — HAC-t + BH-FDR + split-half (the cross-market gate)
# --------------------------------------------------------------------------- #
def test_leadlag_kernel_flags_a_real_link_and_rejects_noise():
    idx = _dates(2000)
    rng = np.random.default_rng(3)
    real = pd.Series(rng.normal(0.05, 0.5, 2000), index=idx)      # persistently positive product
    noise = pd.Series(rng.normal(0.0, 1.0, 2000), index=idx)      # zero-mean noise
    out = H.leadlag_kernel({"real": real, "noise": noise}, hac_lags=10, split="2015-01-01")
    assert out["fdr"]["real"]["reject"] is True
    assert out["fdr"]["noise"]["reject"] is False
