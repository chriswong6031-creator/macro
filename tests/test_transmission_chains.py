"""Tests for the Transmission Chains episode tracker (TXI W1).

Covers: the episode state machine lifecycle on synthetic series (arm → in-window hop
confirms → expressed; lag expiry → expired; falsifier → failed), idempotent same-day
re-runs, the validator (unresolvable node → chain flagged & never arms; malformed YAML →
skipped with log), and a guarded real-artifact smoke test over the four committed seeds.

No test writes the real data/ tree: synthetic tests use tmp roots (root=tmp_path), and the
real-artifact smoke uses write=False.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from engine import transmission_chains as tc

REPO_ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# A tiny in-memory adapter so lifecycle tests can drive node truth deterministically
# without touching lib.store. It mimics _StateAdapter's .get(dotted) interface.
# --------------------------------------------------------------------------- #
class _FakeStateAdapter:
    def __init__(self, doc: dict):
        self.doc = doc

    def get(self, dotted: str):
        cur = self.doc
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                raise tc._Unresolvable(f"path {dotted!r} missing")
            cur = cur[part]
        return cur


# a synthetic chain whose nodes are simple path-boolean tests against the fake adapter.
def _synth_chain(n_hops: int = 2, lag_hi: int = 30) -> dict:
    n_nodes = n_hops + 1
    nodes = {}
    node_ids = [f"n{i}" for i in range(n_nodes)]
    for nid in node_ids:
        nodes[nid] = {"src": "synth", "test": {"path": nid, "op": "is_true"}}
    hops = []
    for i in range(n_hops):
        hops.append({"from": node_ids[i], "to": node_ids[i + 1], "sign": "+",
                     "lag_d": [0, lag_hi], "mechanism": {"en": "x", "zh": "x"}})
    return {
        "chain": "synth_chain", "rev": 0, "tier": "hypothesis",
        "title": {"en": "Synthetic", "zh": "合成"},
        "nodes": nodes, "hops": hops,
        "falsifiers": [{"when": {"path": "kill", "op": "is_true"}, "src": "synth",
                        "note": "kill flag set"}],
        "exposure_screens": {},
    }


def _adapters(doc: dict) -> dict:
    return {"synth": _FakeStateAdapter(doc)}


def _advance(chain, doc, asof, prior):
    """One nightly advance → (per_chain, new prior list)."""
    res = tc.evaluate_chain(chain, _adapters(doc), asof, prior=prior)
    return res["per_chain"], prior + res["transitions"]


# --------------------------------------------------------------------------- #
# 1. Lifecycle — arm → in-window hop confirms → expressed
# --------------------------------------------------------------------------- #
def test_lifecycle_arm_to_expressed():
    chain = _synth_chain(n_hops=2, lag_hi=30)
    ledger: list[dict] = []
    # day 1: nothing true → dormant
    doc = {"n0": False, "n1": False, "n2": False}
    pc, ledger = _advance(chain, doc, "2026-01-01", ledger)
    assert pc["state"] == "dormant"
    assert ledger == []

    # day 2: node 0 true → arming
    doc = {"n0": True, "n1": False, "n2": False}
    pc, ledger = _advance(chain, doc, "2026-01-02", ledger)
    assert pc["state"] == "arming"
    assert pc["hop"] == 0
    assert [r["transition"] for r in ledger] == ["arming"]

    # day 12 (within 30d): node 1 true → propagating(1)
    doc = {"n0": True, "n1": True, "n2": False}
    pc, ledger = _advance(chain, doc, "2026-01-12", ledger)
    assert pc["state"] == "propagating"
    assert pc["hop"] == 1

    # day 30 (within 30d of the hop-1 confirm on 01-12): node 2 true → expressed
    doc = {"n0": True, "n1": True, "n2": True}
    pc, ledger = _advance(chain, doc, "2026-01-30", ledger)
    assert pc["state"] == "expressed"
    assert pc["hop"] == 2
    assert [r["transition"] for r in ledger] == ["arming", "propagating", "expressed"]


# --------------------------------------------------------------------------- #
# 2. Lifecycle — lag window closes unconfirmed → expired
# --------------------------------------------------------------------------- #
def test_lifecycle_lag_expiry():
    chain = _synth_chain(n_hops=2, lag_hi=30)
    ledger: list[dict] = []
    # arm
    doc = {"n0": True, "n1": False, "n2": False}
    pc, ledger = _advance(chain, doc, "2026-01-01", ledger)
    assert pc["state"] == "arming"
    # 40 days later, node 1 STILL false and window (30d) has closed → expired
    pc, ledger = _advance(chain, doc, "2026-02-10", ledger)
    assert pc["state"] == "expired"
    assert ledger[-1]["transition"] == "expired"
    # a stale confirm AFTER expiry does not resurrect the episode (terminal)
    doc2 = {"n0": True, "n1": True, "n2": True}
    pc, ledger = _advance(chain, doc2, "2026-02-11", ledger)
    # node 0 still true and the prior episode is terminal → a NEW episode arms
    assert pc["state"] == "arming"
    assert pc["episode_id"].endswith("2026-02-11")


def test_lifecycle_confirm_too_late_is_expired():
    """A hop target that only goes true AFTER the window closed reads expired, not confirmed."""
    chain = _synth_chain(n_hops=1, lag_hi=10)
    ledger: list[dict] = []
    pc, ledger = _advance(chain, {"n0": True, "n1": False}, "2026-01-01", ledger)
    assert pc["state"] == "arming"
    # node 1 goes true but 20 days later (> lag_hi 10) → expired, NOT expressed
    pc, ledger = _advance(chain, {"n0": True, "n1": True}, "2026-01-21", ledger)
    assert pc["state"] == "expired"


# --------------------------------------------------------------------------- #
# 3. Lifecycle — falsifier fires → failed
# --------------------------------------------------------------------------- #
def test_lifecycle_falsifier_failed():
    chain = _synth_chain(n_hops=2, lag_hi=60)
    ledger: list[dict] = []
    pc, ledger = _advance(chain, {"n0": True, "n1": False, "n2": False, "kill": False},
                          "2026-01-01", ledger)
    assert pc["state"] == "arming"
    # kill flag set while armed → failed
    pc, ledger = _advance(chain, {"n0": True, "n1": False, "n2": False, "kill": True},
                          "2026-01-05", ledger)
    assert pc["state"] == "failed"
    assert pc["falsifier_fired"] is not None
    assert ledger[-1]["transition"] == "failed"


# --------------------------------------------------------------------------- #
# 4. Idempotent same-asof re-run — no duplicate ledger lines, identical state
# --------------------------------------------------------------------------- #
def test_idempotent_same_asof_rerun(tmp_path):
    """Two full run() calls on the same asof append the ledger exactly once."""
    _seed_min_artifacts(tmp_path, oil_ret=+40.0)   # arm the oil chain (node0 true)
    # first run writes chain_state + one arming ledger row for the oil chain
    tc.run(root=tmp_path, write=True)
    led = tmp_path / "data" / "transmission" / "chain_episodes.jsonl"
    first = led.read_text().splitlines()
    assert first, "expected at least one ledger transition on first run"
    # second run at the SAME asof → no new rows (idempotent)
    tc.run(root=tmp_path, write=True)
    second = led.read_text().splitlines()
    assert second == first, "same-asof re-run must not duplicate ledger lines"


def test_idempotent_evaluate_pure():
    """evaluate_chain is pure over (chain, adapters, asof, prior): re-evaluating the same
    inputs yields the same state and the same (possibly empty) new-transition set."""
    chain = _synth_chain(n_hops=2)
    doc = {"n0": True, "n1": True, "n2": False}
    ledger = [{"chain": "synth_chain", "rev": 0, "episode_id": "synth_chain@r0:2026-01-01",
               "transition": "arming", "hop": 0, "asof": "2026-01-01", "receipts": {}}]
    r1 = tc.evaluate_chain(chain, _adapters(doc), "2026-01-05", prior=list(ledger))
    r2 = tc.evaluate_chain(chain, _adapters(doc), "2026-01-05", prior=list(ledger))
    assert r1["per_chain"]["state"] == r2["per_chain"]["state"]
    assert r1["transitions"] == r2["transitions"]


# --------------------------------------------------------------------------- #
# 5. Validator — unresolvable node → chain flagged, never arms
# --------------------------------------------------------------------------- #
def test_unresolvable_node_never_arms():
    chain = _synth_chain(n_hops=1)
    # doc is MISSING n1 → node 1's path is unresolvable
    doc = {"n0": True}
    pc, _ = _advance(chain, doc, "2026-01-01", [])
    assert pc["armable"] is False, "a chain with an unresolvable node must not be armable"
    assert pc["state"] == "dormant", "unarmable chain stays dormant even with node 0 true"
    assert any(u["id"] == "n1" for u in pc.get("unresolved_nodes", []))


# --------------------------------------------------------------------------- #
# 6. Validator — malformed / schema-invalid YAML → skipped with log (fail-open)
# --------------------------------------------------------------------------- #
def test_malformed_yaml_skipped_with_log(tmp_path, caplog):
    kdir = tmp_path / "knowledge" / "transmission"
    kdir.mkdir(parents=True)
    # one VALID chain (copied minimal) + one malformed file
    (kdir / "good_chain.yaml").write_text(
        "chain: good_chain\nrev: 0\ntier: hypothesis\n"
        "title: {en: G, zh: G}\n"
        "nodes:\n  a: {src: synth, test: {path: a, op: is_true}}\n"
        "  b: {src: synth, test: {path: b, op: is_true}}\n"
        "hops:\n  - {from: a, to: b, lag_d: [0, 10]}\n")
    (kdir / "bad_chain.yaml").write_text("chain: bad_chain\nrev: 0\n:\n  - broken: [unclosed\n")
    with caplog.at_level(logging.ERROR):
        chains = tc.load_chains(tmp_path)               # fail-OPEN default
    slugs = {c["chain"] for c in chains}
    assert slugs == {"good_chain"}, "malformed file must be skipped, valid one kept"
    assert any("bad_chain" in r.message for r in caplog.records), "skip must be logged"


def test_schema_violation_skipped_but_strict_raises(tmp_path):
    """A schema-VIOLATING (parseable) file is skipped in fail-open mode but RAISES in
    strict mode (the CI validator path)."""
    kdir = tmp_path / "knowledge" / "transmission"
    kdir.mkdir(parents=True)
    # slug != filename stem → schema violation
    (kdir / "mismatch.yaml").write_text(
        "chain: not_the_stem\nrev: 0\ntier: hypothesis\n"
        "nodes:\n  a: {src: synth, test: {path: a, op: is_true}}\n"
        "  b: {src: synth, test: {path: b, op: is_true}}\n"
        "hops:\n  - {from: a, to: b, lag_d: [0, 10]}\n")
    assert tc.load_chains(tmp_path) == []               # fail-open: skipped
    with pytest.raises(tc.ChainSchemaError):
        tc.load_chains(tmp_path, strict=True)           # strict: reds CI


def test_validator_rejects_stray_metric_companion(tmp_path):
    """metric:ret with a stray ratio: (the units bug this validator was hardened against)
    must be rejected in strict mode."""
    kdir = tmp_path / "knowledge" / "transmission"
    kdir.mkdir(parents=True)
    (kdir / "straykey.yaml").write_text(
        "chain: straykey\nrev: 0\ntier: hypothesis\n"
        "nodes:\n"
        "  a: {src: yahoo, test: {series: HYG, ratio: LQD, metric: ret, window: 22, op: lt, value: -2}}\n"
        "  b: {src: yahoo, test: {series: SPY, metric: ret, window: 5, op: gt, value: 0}}\n"
        "hops:\n  - {from: a, to: b, lag_d: [0, 10]}\n")
    with pytest.raises(tc.ChainSchemaError, match="ratio"):
        tc.load_chains(tmp_path, strict=True)


# --------------------------------------------------------------------------- #
# helpers for the artifact-backed tests
# --------------------------------------------------------------------------- #
def _seed_min_artifacts(root: Path, *, oil_ret: float) -> None:
    """Write the MINIMUM real chain library + a tmp yahoo store so run() advances the oil
    chain deterministically. Copies the committed seed YAMLs, and fabricates a CL=F series
    with the requested 60d return (to arm/not-arm node 0) plus the other series the seeds
    read, so no real data/ is touched."""
    import numpy as np
    import pandas as pd

    # 1. copy the real chain library into the tmp root
    src_k = REPO_ROOT / "knowledge" / "transmission"
    dst_k = root / "knowledge" / "transmission"
    dst_k.mkdir(parents=True)
    for y in src_k.glob("*.yaml"):
        (dst_k / y.name).write_text(y.read_text())

    # 2. fabricate the series the seeds read, into root/data/<group>/, via a redirected store
    data_dir = root / "data"
    (data_dir).mkdir(parents=True, exist_ok=True)
    idx = pd.date_range("2024-01-01", periods=400, freq="D")

    def _write(group, name, last_over_start):
        # a monotone ramp so ret_60d ≈ (last/60d-ago - 1); we set the last 61 points to
        # encode the desired 60d return, rest flat.
        vals = np.full(len(idx), 100.0)
        vals[-61:] = np.linspace(100.0, 100.0 * (1 + last_over_start / 100.0), 61)
        p = data_dir / group / f"{name.replace('=','_').replace('^','_').replace('/','_')}.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"close": vals}, index=idx).to_parquet(p)

    # CL=F encodes the oil 60d return; the rest are flat (no cohort derate, breakevens flat)
    _write("yahoo", "CL=F", oil_ret)
    for nm in ("QQQ", "SPY", "FXI", "HYG", "LQD", "IWM", "SPHB", "SPLV"):
        _write("yahoo", nm, 0.0)
    _write("fred", "T10YIE", 0.0)

    # 3. a minimal transmission/forex/regime latest.json so the state adapters resolve
    (data_dir / "transmission").mkdir(parents=True, exist_ok=True)
    (data_dir / "transmission" / "latest.json").write_text(json.dumps({
        "asof": "2026-03-01",
        "state": {"rates": {"direction": "stable", "real_10y_chg_63d_bp": 0}},
    }))
    (data_dir / "forex").mkdir(parents=True, exist_ok=True)
    (data_dir / "forex" / "latest.json").write_text(json.dumps({
        "asof": "2026-03-01",
        "dollar_desk": {"trend": "down", "usd_pos_pctile": 20.0},
        "transmission": {"usd_dir": "weakening", "headwind_for": []},
    }))
    (data_dir / "regime").mkdir(parents=True, exist_ok=True)
    (data_dir / "regime" / "latest.json").write_text(json.dumps({
        "asof": "2026-03-01",
        "vol_regime": {"regime": "normalizing", "vix": 15.0, "vol_target_scalar": 1.0},
        "froth_fragility": {"unwind_risk": False},
    }))


def test_seed_yamls_all_load_strict():
    """Every committed seed YAML passes strict validation (this is the CI-facing guard —
    a bad edit to the library reds here)."""
    chains = tc.load_chains(REPO_ROOT, strict=True)
    slugs = {c["chain"] for c in chains}
    assert {"oil_inflation_duration_derate", "dollar_spike_em_multinational",
            "credit_spreads_refinancing", "vol_regime_deleveraging"} <= slugs
    for c in chains:
        assert c["tier"] in tc._VALID_TIERS
        assert c["hops"], f"{c['chain']} has no hops"


# --------------------------------------------------------------------------- #
# 7. Real-artifact smoke — guarded on artifact presence. Loads the 4 seeds against the
#    repo's real data and asserts they EVALUATE WITHOUT ERROR. Asserts the oil chain
#    reaches >= propagating ONLY IF node 0 (oil shock) arms on the current tape — otherwise
#    only that it loads/evaluates (do NOT hard-pin market state; the wall-clock-flake class).
# --------------------------------------------------------------------------- #
def _real_artifacts_present() -> bool:
    d = REPO_ROOT / "data"
    return all((d / p).exists() for p in
               ("transmission/latest.json", "forex/latest.json", "regime/latest.json",
                "yahoo/CL_F.parquet"))


@pytest.mark.skipif(not _real_artifacts_present(),
                    reason="real transmission/forex/regime/yahoo artifacts absent")
def test_real_artifact_smoke():
    state = tc.run(write=False)   # write=False → never touches the real data/ tree
    assert state["schema"] == tc.SCHEMA_ID
    slugs = {c["chain"] for c in state["chains"]}
    assert {"oil_inflation_duration_derate", "dollar_spike_em_multinational",
            "credit_spreads_refinancing", "vol_regime_deleveraging"} <= slugs
    for c in state["chains"]:
        assert c["state"] in {"dormant", "arming", "propagating", "expressed", "failed", "expired"}
        assert c["display_only"] is True
        # nulls printed honestly, not hidden; W2/W3 fields declared
        assert c["base_rates"] is None
        assert c["blast"] == []

    oil = next(c for c in state["chains"] if c["chain"] == "oil_inflation_duration_derate")
    oil_node0 = oil["nodes"][0]
    if oil["armable"] and oil_node0["confirmed"]:
        # node 0 armed on the current tape → the chain is at least arming; if the real-10y
        # leg has also confirmed within window across the ledger it can be propagating.
        assert oil["state"] in {"arming", "propagating", "expressed"}
    else:
        # oil not shocking on the current tape → dormant is correct; the requirement is only
        # that it loaded + evaluated cleanly (asserted above). Never hard-pin propagating.
        assert oil["state"] in {"dormant", "arming", "propagating", "expressed", "failed", "expired"}


@pytest.mark.skipif(not _real_artifacts_present(),
                    reason="real artifacts absent")
def test_real_artifact_no_data_write():
    """The dry-run (write=False) path must not create chain_state/chain_episodes."""
    before_cs = (REPO_ROOT / "data" / "transmission" / "chain_state.json").exists()
    before_le = (REPO_ROOT / "data" / "transmission" / "chain_episodes.jsonl").exists()
    tc.run(write=False)
    after_cs = (REPO_ROOT / "data" / "transmission" / "chain_state.json").exists()
    after_le = (REPO_ROOT / "data" / "transmission" / "chain_episodes.jsonl").exists()
    assert after_cs == before_cs and after_le == before_le
