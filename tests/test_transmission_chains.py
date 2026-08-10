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
    # resolve_blast_radius=False keeps this a pure STATE-MACHINE smoke (W1 contract): blast
    # stays the W1 empty-list default when no substrate is swept. (The W2 substrate smoke is
    # test_real_substrate_blast_smoke below.)
    state = tc.run(write=False, resolve_blast_radius=False)
    assert state["schema"] == tc.SCHEMA_ID
    slugs = {c["chain"] for c in state["chains"]}
    assert {"oil_inflation_duration_derate", "dollar_spike_em_multinational",
            "credit_spreads_refinancing", "vol_regime_deleveraging"} <= slugs
    calib_present = (REPO_ROOT / "data" / "transmission" / "chain_calibration.json").exists()
    for c in state["chains"]:
        assert c["state"] in {"dormant", "arming", "propagating", "expressed", "failed", "expired"}
        assert c["display_only"] is True
        # base_rates era-honest: None (no calibration mined for this chain — the null printed,
        # never hidden) OR the W3 merge dict once chain_calibration.json exists. Hard-pinning
        # None was correct only in the pre-calibration era (first mine: 2026-08-05).
        assert c["base_rates"] is None or isinstance(c["base_rates"], dict)
        assert c["blast"] == []          # no substrate sweep → W1 default
    if calib_present:
        # the W3 merge must actually light up: at least one chain carries mined rates
        assert any(isinstance(c["base_rates"], dict) and c["base_rates"] for c in state["chains"])

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
    """The dry-run (write=False) path must not create chain_state/chain_episodes, even with
    the W2 substrate sweep enabled."""
    before_cs = (REPO_ROOT / "data" / "transmission" / "chain_state.json").exists()
    before_le = (REPO_ROOT / "data" / "transmission" / "chain_episodes.jsonl").exists()
    tc.run(write=False)
    after_cs = (REPO_ROOT / "data" / "transmission" / "chain_state.json").exists()
    after_le = (REPO_ROOT / "data" / "transmission" / "chain_episodes.jsonl").exists()
    assert after_cs == before_cs and after_le == before_le


# =========================================================================== #
# W2 — BLAST-RADIUS RESOLVER (structured exposure screens + universe sweep)
# =========================================================================== #

def _substrate(docs: dict) -> tc.SubstrateStore:
    """A SubstrateStore over an in-memory {ticker: doc} map, with radar-list normalization
    applied (mirrors from_dir so factors.radar_<key>_z synthetic paths resolve)."""
    for d in docs.values():
        tc._normalize_substrate_doc(d)
    return tc.SubstrateStore(docs)


# --------------------------------------------------------------------------- #
# W2.1 — the expression evaluator: every op, incl. pctile cuts, on a synthetic universe;
#         a malformed clause skips the channel with a note (never crashes).
# --------------------------------------------------------------------------- #
def test_screen_ops_scalar_comparators():
    store = _substrate({})
    doc = {"x": 5, "s": "long", "lst": ["Materials"], "flag": True}
    ev = lambda clause: tc._eval_screen_clause(clause, doc, store, {})
    assert ev({"path": "x", "op": ">", "value": 3}) is True
    assert ev({"path": "x", "op": ">", "value": 10}) is False
    assert ev({"path": "x", "op": "<", "value": 10}) is True
    assert ev({"path": "x", "op": ">=", "value": 5}) is True
    assert ev({"path": "x", "op": "<=", "value": 5}) is True
    assert ev({"path": "s", "op": "==", "value": "long"}) is True
    assert ev({"path": "s", "op": "!=", "value": "short"}) is True
    assert ev({"path": "s", "op": "in", "value": ["long", "neutral"]}) is True
    assert ev({"path": "lst", "op": "in", "value": ["Materials", "Energy"]}) is False  # 'in' is scalar-in-list, not list∩
    assert ev({"path": "x", "op": "exists"}) is True
    assert ev({"path": "absent", "op": "exists"}) is False


def test_screen_op_missing_and_null_are_unevaluable():
    store = _substrate({})
    # a missing field → None (unevaluable), NOT False
    assert tc._eval_screen_clause({"path": "nope", "op": ">", "value": 0}, {"x": 1}, store, {}) is None
    # a present-but-null field → None (null ≠ 0)
    assert tc._eval_screen_clause({"path": "x", "op": "<", "value": 0}, {"x": None}, store, {}) is None
    # `exists` means "has a usable (non-null) value": a null field reads False (not present for
    # screening purposes), an absent field reads False, a present non-null value reads True.
    assert tc._eval_screen_clause({"path": "x", "op": "exists"}, {"x": None}, store, {}) is False
    assert tc._eval_screen_clause({"path": "x", "op": "exists"}, {"x": 0}, store, {}) is True
    assert tc._eval_screen_clause({"path": "x", "op": "exists"}, {"y": 1}, store, {}) is False


def test_screen_pctile_cut_and_receipt():
    # a 10-name universe of forward_pe → the 80th-pctile (nearest-rank) numeric cut is printed,
    # and it is the numeric cut a full resolve stores in `blast[flag]['cuts']` (the receipt).
    docs = {f"T{i}": {"valuation": {"forward_pe": float(v)}}
            for i, v in enumerate([5, 8, 10, 12, 15, 20, 25, 30, 40, 60])}
    store = _substrate(docs)
    cut = store.pctile_cut("valuation.forward_pe", 0.80)
    assert cut == 40.0, cut                      # nearest-rank: index int(0.8*10)=8 → sorted[8]=40
    # membership decided by the printed cut (value >= 40): T8(40), T9(60) only.
    screen = {"any": [{"path": "valuation.forward_pe", "op": "pctile_gte", "value": 0.80}]}
    hits = {t for t, d in docs.items()
            if tc._eval_screen(screen, d, store, {"valuation.forward_pe": cut})}
    assert hits == {"T8", "T9"}, hits
    # the receipt lands in the emit: a full resolve prints the numeric cut in blast[flag]['cuts']
    chain = {"chain": "c", "exposure_screens": {"rich": {"label": {"en": "R", "zh": "R"}, **screen}}}
    blast = tc.resolve_blast(chain, {"state": "arming"}, store)
    assert blast["rich"]["cuts"] == {"valuation.forward_pe": 40.0}
    assert set(blast["rich"]["names"]) == {"T8", "T9"}


def test_screen_pctile_lte():
    docs = {f"T{i}": {"v": float(v)} for i, v in enumerate([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])}
    store = _substrate(docs)
    cut = store.pctile_cut("v", 0.20)            # sorted[int(0.2*10)=2] = 3
    assert cut == 3.0, cut
    screen = {"any": [{"path": "v", "op": "pctile_lte", "value": 0.20}]}
    hits = {t for t, d in docs.items() if tc._eval_screen(screen, d, store, {"v": cut})}
    assert hits == {"T0", "T1", "T2"}            # value <= cut 3 → 1, 2, 3
    assert "T9" not in hits


def test_screen_pctile_no_universe_is_unevaluable():
    """pctile on a field with no numeric values anywhere → cut None → clause unevaluable."""
    store = _substrate({"A": {"other": 1}})
    assert store.pctile_cut("valuation.forward_pe", 0.8) is None
    screen = {"any": [{"path": "valuation.forward_pe", "op": "pctile_gte", "value": 0.8}]}
    assert tc._eval_screen(screen, {"valuation": {"forward_pe": 99.0}}, store, {}) is None


def test_all_semantics_unevaluable_on_any_missing_clause():
    store = _substrate({})
    sc = {"all": [{"path": "a", "op": ">", "value": 3}, {"path": "b", "op": ">", "value": 3}]}
    assert tc._eval_screen(sc, {"a": 5, "b": 5}, store, {}) is True
    assert tc._eval_screen(sc, {"a": 5, "b": 1}, store, {}) is False   # both evaluable, one False
    assert tc._eval_screen(sc, {"a": 5}, store, {}) is None            # b missing → unevaluable


def test_any_semantics_unevaluable_when_a_missing_clause_could_flip():
    store = _substrate({})
    sc = {"any": [{"path": "a", "op": ">", "value": 3}, {"path": "b", "op": ">", "value": 100}]}
    assert tc._eval_screen(sc, {"a": 5, "b": 1}, store, {}) is True    # a fires
    assert tc._eval_screen(sc, {"a": 1, "b": 1}, store, {}) is False   # both evaluable-False
    assert tc._eval_screen(sc, {"a": 1}, store, {}) is None            # a False, b missing → could flip


def test_malformed_screen_clause_skips_channel_never_crashes():
    """A clause that slips past load validation (here: a pctile value out of [0,1] fed straight
    to resolve, bypassing validate_chain) must skip THAT channel with a resolved:false note —
    the other channels still resolve and the sweep never raises."""
    chain = {
        "chain": "x", "exposure_screens": {
            "good": {"label": {"en": "G", "zh": "G"}, "any": [{"path": "v", "op": ">", "value": 0}]},
            # a clause whose op will explode inside _resolve_channel: pctile with a str value
            "bad": {"label": {"en": "B", "zh": "B"}, "any": [{"path": "v", "op": "pctile_gte", "value": "oops"}]},
        }}
    store = _substrate({"A": {"v": 5}, "B": {"v": -1}})
    blast = tc.resolve_blast(chain, {"state": "arming"}, store)
    assert blast["good"]["resolved"] is True and blast["good"]["n"] == 1   # 'A' fires
    assert blast["bad"]["resolved"] is False                              # skipped with a note
    assert blast["bad"]["note"] is not None


# --------------------------------------------------------------------------- #
# W2.2 — fixture-substrate resolution: a tmp dir of synthetic ticker JSONs → known blast
#         membership per channel; unevaluable counting; dormant chain → empty blast.
# --------------------------------------------------------------------------- #
def _write_ticker(dir_: Path, ticker: str, doc: dict) -> None:
    doc = {"ticker": ticker, "asof": "2026-07-01", **doc}
    (dir_ / f"{ticker}.json").write_text(json.dumps(doc))


def _fixture_substrate_dir(tmp_path: Path) -> Path:
    """8 synthetic tickers with hand-set fields → deterministic per-channel membership."""
    d = tmp_path / "stockdata"
    d.mkdir()
    # index.json MUST be ignored by the loader
    (d / "index.json").write_text(json.dumps({"tickers": ["BURN1"]}))
    # BURN1/BURN2: negative FCF → fcf_burner members
    _write_ticker(d, "BURN1", {"financials": {"fcf_margin": -12.0, "debt_to_assets": 55.0}})
    _write_ticker(d, "BURN2", {"financials": {"fcf_margin": -3.0}})
    # LEV1/LEV2: high leverage → refinancing_channel members
    _write_ticker(d, "LEV1", {"financials": {"fcf_margin": 20.0, "debt_to_assets": 80.0}})
    _write_ticker(d, "LEV2", {"financials": {"fcf_margin": 10.0, "debt_to_assets": 70.0}})
    # HEALTHY1/2: positive FCF, low leverage → members of nothing
    _write_ticker(d, "HEALTHY1", {"financials": {"fcf_margin": 30.0, "debt_to_assets": 5.0}})
    _write_ticker(d, "HEALTHY2", {"financials": {"fcf_margin": 25.0, "debt_to_assets": 8.0}})
    # NOFIN: no financials block at all → UNEVALUABLE for every financials screen
    _write_ticker(d, "NOFIN", {"tech": {"hv20": 40.0}})
    # NULLFCF: financials present but fcf_margin null → unevaluable for fcf screens
    _write_ticker(d, "NULLFCF", {"financials": {"fcf_margin": None, "debt_to_assets": None}})
    return d


def _fcf_chain() -> dict:
    return {"chain": "fcf_test", "exposure_screens": {
        "fcf_burner": {"label": {"en": "FCF burner", "zh": "现金流消耗"},
                       "all": [{"path": "financials.fcf_margin", "op": "<", "value": 0}]},
        "refinancing_channel": {"label": {"en": "Refi", "zh": "再融资"},
                                "all": [{"path": "financials.debt_to_assets", "op": "pctile_gte", "value": 0.60}]},
    }}


def test_fixture_substrate_membership_and_unevaluable(tmp_path):
    store = tc.SubstrateStore.from_dir(_fixture_substrate_dir(tmp_path))
    assert len(store.docs) == 8                    # index.json excluded
    assert "index" not in store.docs
    blast = tc.resolve_blast(_fcf_chain(), {"state": "propagating"}, store)
    fcf = blast["fcf_burner"]
    assert set(fcf["names"]) == {"BURN1", "BURN2"}, fcf["names"]
    # NOFIN (no financials) + NULLFCF (null fcf_margin) are unevaluable, NOT counted as members
    assert fcf["unevaluable"] == 2, fcf                # NOFIN + NULLFCF
    assert fcf["n"] == 2
    # counts always account for the whole universe: members + unevaluable + clean-negatives
    clean_neg = len(store.docs) - fcf["n"] - fcf["unevaluable"]
    assert clean_neg == 4                              # LEV1, LEV2, HEALTHY1, HEALTHY2


def test_fixture_pctile_membership(tmp_path):
    store = tc.SubstrateStore.from_dir(_fixture_substrate_dir(tmp_path))
    blast = tc.resolve_blast(_fcf_chain(), {"state": "arming"}, store)
    refi = blast["refinancing_channel"]
    # debt_to_assets universe (nonnull) = [5, 8, 55, 80, 70] → sorted [5,8,55,70,80].
    # pctile_gte(0.60) numeric cut = nearest-rank sorted[int(0.6*5)=3] = 70 (printed in emit).
    # MEMBERSHIP is decided by the printed cut (value >= 70) so a client can reproduce the set:
    # 80, 70 pass; 55 (BURN1) does NOT. This is the client-reproducibility contract.
    assert refi["cuts"]["financials.debt_to_assets"] == 70.0, refi["cuts"]
    assert set(refi["names"]) == {"LEV1", "LEV2"}, refi["names"]   # 80 and 70 (>= cut 70)
    assert refi["unevaluable"] == 3                 # BURN2 (no d/a), NOFIN, NULLFCF


def test_dormant_chain_empty_blast(tmp_path):
    store = tc.SubstrateStore.from_dir(_fixture_substrate_dir(tmp_path))
    # a DORMANT chain resolves to {} — no sweep, no members (masterplan §scoping.4)
    assert tc.resolve_blast(_fcf_chain(), {"state": "dormant"}, store) == {}
    assert tc.resolve_blast(_fcf_chain(), {"state": "expired"}, store) == {}
    assert tc.resolve_blast(_fcf_chain(), {"state": "failed"}, store) == {}
    # armed states DO resolve
    for st in ("arming", "propagating", "expressed"):
        assert tc.resolve_blast(_fcf_chain(), {"state": st}, store) != {}


def test_dropped_channel_emits_honest_marker(tmp_path):
    store = tc.SubstrateStore.from_dir(_fixture_substrate_dir(tmp_path))
    chain = {"chain": "x", "exposure_screens": {
        "no_field": {"label": {"en": "No field", "zh": "无字段"},
                     "note": {"en": "DROPPED — no field", "zh": "已弃用——无字段"}},  # prose-only, no all/any
    }}
    blast = tc.resolve_blast(chain, {"state": "arming"}, store)
    ch = blast["no_field"]
    assert ch["resolved"] is False
    assert ch["n"] == 0 and ch["names"] == []
    assert ch["unevaluable"] == len(store.docs)     # whole universe unevaluable
    assert ch["note"]["en"].startswith("DROPPED")


def test_radar_list_lifted_to_synthetic_path(tmp_path):
    """factors.radar [{key,z}] → factors.radar_<key>_z scalar (so screens address it)."""
    d = tmp_path / "stockdata"
    d.mkdir()
    _write_ticker(d, "CAPEX", {"factors": {"radar": [{"key": "investment", "z": -2.0},
                                                      {"key": "value", "z": 0.5},
                                                      {"key": "payout", "z": None}]},
                               "financials": {"fcf_margin": -5.0}})
    _write_ticker(d, "SAFE", {"factors": {"radar": [{"key": "investment", "z": 0.1}]},
                              "financials": {"fcf_margin": 10.0}})
    store = tc.SubstrateStore.from_dir(d)
    assert store.docs["CAPEX"]["factors"]["radar_investment_z"] == -2.0
    assert "radar_payout_z" not in store.docs["CAPEX"]["factors"]   # null z dropped
    chain = {"chain": "x", "exposure_screens": {
        "capex_borrower": {"label": {"en": "Capex", "zh": "资本"},
                           "all": [{"path": "factors.radar_investment_z", "op": "<", "value": -1.5},
                                   {"path": "financials.fcf_margin", "op": "<", "value": 0}]}}}
    blast = tc.resolve_blast(chain, {"state": "arming"}, store)
    assert blast["capex_borrower"]["names"] == ["CAPEX"]


def test_substrate_asof_stamp_ignores_bad_dates(tmp_path):
    d = tmp_path / "stockdata"
    d.mkdir()
    _write_ticker(d, "A", {"asof": "2026-06-01"})   # _write_ticker sets asof; override below
    (d / "A.json").write_text(json.dumps({"ticker": "A", "asof": "2026-06-01"}))
    (d / "B.json").write_text(json.dumps({"ticker": "B", "asof": "2026-07-15"}))
    (d / "C.json").write_text(json.dumps({"ticker": "C", "asof": "NaT"}))      # bad
    (d / "D.json").write_text(json.dumps({"ticker": "D", "asof": None}))       # bad
    store = tc.SubstrateStore.from_dir(d)
    assert store.docs and set(store.docs) == {"A", "B", "C", "D"}   # all loaded
    assert store.substrate_asof() == {"min": "2026-06-01", "max": "2026-07-15"}   # NaT/None ignored


def test_from_dir_skips_non_ticker_and_unreadable(tmp_path):
    d = tmp_path / "stockdata"
    d.mkdir()
    (d / "GOOD.json").write_text(json.dumps({"ticker": "GOOD"}))
    (d / "broken.json").write_text("{not json")                    # unreadable → skipped
    (d / "arr.json").write_text(json.dumps([1, 2, 3]))             # not a dict → skipped
    (d / "noticker.json").write_text(json.dumps({"foo": 1}))       # no ticker → uses stem 'noticker'
    store = tc.SubstrateStore.from_dir(d)
    assert "GOOD" in store.docs
    assert "noticker" in store.docs        # falls back to filename stem
    assert len(store.docs) == 2            # broken + arr excluded


def test_build_chain_state_merges_blast_and_substrate_stamp(tmp_path):
    """build_chain_state with a substrate store merges each armed chain's blast + a top-level
    substrate stamp; a chain that stays dormant keeps blast:{}."""
    _seed_min_artifacts(tmp_path, oil_ret=+40.0)   # arms the oil chain's node 0
    # give the oil chain something to resolve in the substrate
    sd = tmp_path / "stockdata"
    sd.mkdir()
    _write_ticker(sd, "BURN", {"financials": {"fcf_margin": -9.0}})
    _write_ticker(sd, "SAFE", {"financials": {"fcf_margin": 12.0}})
    chains = tc.load_chains(tmp_path, strict=True)
    adapters = tc.build_adapters(tmp_path / "data")
    store = tc.SubstrateStore.from_dir(sd)
    state, _ = tc.build_chain_state(chains, adapters, "2026-03-01", [], substrate=store)
    assert state["substrate"]["universe"] == 2
    assert state["substrate"]["substrate_asof"]["max"] == "2026-07-01"
    oil = next(c for c in state["chains"] if c["chain"] == "oil_inflation_duration_derate")
    # oil node0 armed → blast is a dict (resolved). fcf_burner should catch BURN.
    assert isinstance(oil["blast"], dict)
    if oil["state"] in tc._ARMED_STATES:
        assert oil["blast"]["fcf_burner"]["names"] == ["BURN"]


# --------------------------------------------------------------------------- #
# W2.4 — guarded real-substrate smoke: sweep runs end-to-end over the real per-ticker
#         universe, emits schema-valid blast blocks, wall-time printed.
# --------------------------------------------------------------------------- #
def _real_substrate_present() -> bool:
    sd = REPO_ROOT / "site" / "stockdata"
    return sd.exists() and any(sd.glob("*.json"))


@pytest.mark.skipif(not (_real_artifacts_present() and _real_substrate_present()),
                    reason="real state artifacts or per-ticker substrate absent")
def test_real_substrate_blast_smoke(capsys):
    import time
    t0 = time.perf_counter()
    state = tc.run(write=False)     # substrate swept by default; write=False → no data/ touch
    wall = time.perf_counter() - t0
    # wall-time budget: the sweep is one pass over ~1.6k files — must be well under the nightly
    # budget. Printed so the PR body can cite it; asserted generously to avoid CI-host flake.
    print(f"[W2 smoke] full run + blast sweep over "
          f"{state.get('substrate', {}).get('universe')} names: {wall:.2f}s")
    assert wall < 60.0, f"blast sweep took {wall:.1f}s (>60s budget)"

    assert "substrate" in state and state["substrate"]["universe"] > 0
    aso = state["substrate"]["substrate_asof"]
    assert aso["min"] and aso["max"] and aso["max"] != "NaT"   # bad-date guard held

    for c in state["chains"]:
        blast = c["blast"]
        if c["state"] not in tc._ARMED_STATES:
            assert blast == {}, f"{c['chain']} dormant but blast non-empty"
            continue
        assert isinstance(blast, dict) and blast, f"{c['chain']} armed but blast empty"
        for flag, b in blast.items():
            # schema-valid blast block per channel
            assert set(b) >= {"label", "n", "cuts", "unevaluable", "names", "resolved"}
            assert isinstance(b["names"], list)
            assert b["n"] == len(b["names"])
            assert b["n"] + b["unevaluable"] <= state["substrate"]["universe"]
            if not b["resolved"]:
                assert b["n"] == 0 and b["names"] == []      # dropped/proxy → honest zero
            # counts never negative; unevaluable always present (missing-field bucket)
            assert b["unevaluable"] >= 0


# =========================================================================== #
# rev-1 — the `off_high_bp` exhaustion metric, the ARMING VETO, the optional `stall:`
# turn-watch annotation, and the de-escalated `failed` label. Every test in this section
# FAILS on rev-0 semantics (the metric does not exist, a falsified chain still arms, no
# turn_watch key is ever emitted, and the label still reads the refutation register).
# =========================================================================== #
def _write_level_series(root: Path, group: str, name: str, values) -> Path:
    """Write a level-series parquet under <root>/data/<group>/ (the _SeriesAdapter layout)."""
    import pandas as pd
    idx = pd.date_range("2026-01-01", periods=len(values), freq="D")
    safe = name.replace("=", "_").replace("^", "_").replace("/", "_")
    p = root / "data" / group / f"{safe}.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"close": [float(v) for v in values]}, index=idx).to_parquet(p)
    return p


def _pressing_series(n: int = 90) -> list[float]:
    """A level series climbing ~+5bp/bar whose LAST bar is its 10-bar high (off_high_bp = 0
    — 'still pressing highs')."""
    return [2.00 + 0.005 * i for i in range(n)]


def _plateau_series(n: int = 90) -> list[float]:
    """The same quarter-long climb, then a fade that leaves the last bar ~6bp BELOW its
    10-bar high (off_high_bp >= 4 — the shape the rev-1 gate is built to silence)."""
    ramp = _pressing_series(n - 5)
    top = ramp[-1]
    return ramp + [top, top - 0.02, top - 0.05, top - 0.06, top - 0.06]


# --------------------------------------------------------------------------- #
# rev-1.1 — off_high_bp: value semantics, point-vs-vectorized parity, short history
# --------------------------------------------------------------------------- #
def test_off_high_bp_is_zero_at_the_window_high(tmp_path):
    _write_level_series(tmp_path, "fred", "LVL", [2.00, 2.10, 2.50, 2.30, 2.50])
    ad = tc._SeriesAdapter(tmp_path / "data", "fred")
    val, receipt = tc._series_metric(ad, {"series": "LVL", "metric": "off_high_bp", "window": 5})
    assert val == pytest.approx(0.0), "a series AT its window high is 0bp off the high"
    assert receipt == {"series": "LVL", "metric": "off_high_bp", "window": 5, "value": 0.0}


def test_off_high_bp_measures_bp_below_the_window_high_only(tmp_path):
    """N bp below a high INSIDE the window reads N — and a higher bar just OUTSIDE the
    window is ignored (pins the window boundary: a window+1 read would print 47bp here)."""
    _write_level_series(tmp_path, "fred", "OFF", [2.90, 2.47, 2.30, 2.43])
    ad = tc._SeriesAdapter(tmp_path / "data", "fred")
    val, receipt = tc._series_metric(ad, {"series": "OFF", "metric": "off_high_bp", "window": 3})
    assert val == pytest.approx(4.0), f"expected 4bp off the 3-bar high (2.47), got {val}"
    assert receipt["value"] == 4.0
    assert val >= 0.0, "off_high_bp is a distance below a maximum — never negative"


def test_off_high_bp_point_matches_vectorized_at_the_last_bar(tmp_path):
    """The W3 shared-surface law: `_series_metric` at the last bar and
    `series_metric_timeseries().iloc[-1]` are the SAME number by construction (exact)."""
    vals = [2.00, 2.90, 2.47, 2.30, 2.43, 2.41, 2.55, 2.20, 2.31, 2.33]
    _write_level_series(tmp_path, "fred", "PAR", vals)
    ad = tc._SeriesAdapter(tmp_path / "data", "fred")
    t = {"series": "PAR", "metric": "off_high_bp", "window": 4, "op": "lt", "value": 4}
    pit, _ = tc._series_metric(ad, t)
    vec = tc.series_metric_timeseries(ad.series, t)
    assert vec.iloc[-1] == pit, "point-in-time and vectorized must be identical, not merely close"
    assert len(vec) == len(vals) - 4 + 1          # NaN only where the window has no lookback
    assert (vec >= 0).all(), "every bar is a non-negative distance below its window high"
    # the boolean history goes through the same comparator surface the miner uses
    hist = tc.series_test_timeseries(ad.series, t)
    assert hist.iloc[-1] == (pit < 4)


def test_off_high_bp_needs_window_observations_not_window_plus_one(tmp_path):
    """max-vs-last needs exactly `window` observations — one fewer than the shifted metrics.
    Fewer than that is UNRESOLVABLE (never silently False)."""
    _write_level_series(tmp_path, "fred", "SHORT", [2.0, 2.1, 2.2])
    ad = tc._SeriesAdapter(tmp_path / "data", "fred")
    val, _ = tc._series_metric(ad, {"series": "SHORT", "metric": "off_high_bp", "window": 3})
    assert val == pytest.approx(0.0)              # exactly `window` bars resolves
    with pytest.raises(tc._Unresolvable):
        tc._series_metric(ad, {"series": "SHORT", "metric": "off_high_bp", "window": 4})


def test_schema_accepts_off_high_bp_and_still_rejects_an_unknown_metric(tmp_path):
    kdir = tmp_path / "knowledge" / "transmission"
    kdir.mkdir(parents=True)
    body = (
        "chain: offhigh\nrev: 1\ntier: hypothesis\n"
        "title: {en: O, zh: O}\n"
        "nodes:\n"
        "  a: {src: fred, test: {series: DFII10, metric: %s, window: 10, op: lt, value: 4}}\n"
        "  b: {src: yahoo, test: {series: SPY, metric: ret, window: 5, op: gt, value: 0}}\n"
        "hops:\n  - {from: a, to: b, lag_d: [0, 10]}\n")
    (kdir / "offhigh.yaml").write_text(body % "off_high_bp")
    assert [c["chain"] for c in tc.load_chains(tmp_path, strict=True)] == ["offhigh"]
    (kdir / "offhigh.yaml").write_text(body % "off_high_pct")     # not in the whitelist
    with pytest.raises(tc.ChainSchemaError, match="metric"):
        tc.load_chains(tmp_path, strict=True)


# --------------------------------------------------------------------------- #
# rev-1.2 — `stall:` block schema
# --------------------------------------------------------------------------- #
def _stall_chain(stall) -> dict:
    c = _synth_chain(n_hops=1)
    c["stall"] = stall
    return c


def test_stall_schema_valid_block_passes():
    tc.validate_chain(_stall_chain({
        "when": {"all": [{"path": "slow", "op": "is_true"},
                         {"path": "off", "op": "is_true"}]},
        "src": "synth",
        "label": {"en": "Momentum fading", "zh": "动能减弱"}}), "synth_chain.yaml")


def test_stall_without_when_raises():
    with pytest.raises(tc.ChainSchemaError, match="stall"):
        tc.validate_chain(_stall_chain({"label": {"en": "x", "zh": "x"}}), "synth_chain.yaml")


def test_stall_with_a_bad_inner_test_raises():
    with pytest.raises(tc.ChainSchemaError, match="stall.when"):
        tc.validate_chain(_stall_chain({"when": {"path": "slow", "op": "nope"}}),
                          "synth_chain.yaml")
    # a series leaf missing its window is caught by the SAME grammar the nodes use
    with pytest.raises(tc.ChainSchemaError, match="stall.when"):
        tc.validate_chain(_stall_chain(
            {"when": {"series": "LVL", "metric": "off_high_bp", "op": "gte", "value": 4}}),
            "synth_chain.yaml")


def test_stall_non_mapping_or_bad_label_raises():
    with pytest.raises(tc.ChainSchemaError, match="stall"):
        tc.validate_chain(_stall_chain("watching for the turn"), "synth_chain.yaml")
    with pytest.raises(tc.ChainSchemaError, match="label"):
        tc.validate_chain(_stall_chain({"when": {"path": "s", "op": "is_true"},
                                        "label": "Momentum fading"}), "synth_chain.yaml")


# --------------------------------------------------------------------------- #
# rev-1.3 — ARMING VETO: a chain whose falsifier is already true never opens an episode
# --------------------------------------------------------------------------- #
def test_arming_veto_keeps_an_already_falsified_chain_dormant():
    chain = _synth_chain(n_hops=2, lag_hi=60)          # hop 0 lag_d = [0, 60] → lag_lo 0
    doc = {"n0": True, "n1": False, "n2": False, "kill": True}
    pc, ledger = _advance(chain, doc, "2026-01-01", [])
    assert pc["state"] == "dormant", "node 0 true but the falsifier is already firing"
    assert ledger == [], "a vetoed arm must append NO ledger transition"
    assert pc["episode_id"] is None
    assert pc["falsifier_fired"] is None, "nothing failed — no episode ever opened"
    assert pc["arm_veto"]["index"] == 0
    assert pc["arm_veto"]["note"] == "kill flag set"
    assert pc["arm_veto"]["receipts"], "the veto must carry its receipts, never a bare state"


def test_arming_veto_respects_the_hop0_minimum_lag():
    """lag gating is preserved EXACTLY: a chain whose hop 0 has lag_lo > 0 could not have
    been falsified on its arming day under rev 0 either, so it still arms."""
    chain = _synth_chain(n_hops=2, lag_hi=60)
    chain["hops"][0]["lag_d"] = [5, 60]
    doc = {"n0": True, "n1": False, "n2": False, "kill": True}
    pc, ledger = _advance(chain, doc, "2026-01-01", [])
    assert pc["state"] == "arming"
    assert "arm_veto" not in pc
    assert [r["transition"] for r in ledger] == ["arming"]


def test_veto_does_not_reproduce_the_rev0_same_asof_arm_then_fail_churn():
    """REGRESSION on the rev-0 shape: a first evaluation appended `arming`, a second at the
    SAME asof read that row back and appended `failed` (both peak chains, ledger 2026-08-07)
    — an episode opened only to be closed by a condition that was already true. A vetoed arm
    produces NEITHER row, on any number of same-asof passes."""
    chain = _synth_chain(n_hops=2, lag_hi=60)
    doc = {"n0": True, "n1": False, "n2": False, "kill": True}
    pc1, ledger = _advance(chain, doc, "2026-01-01", [])
    pc2, ledger = _advance(chain, doc, "2026-01-01", ledger)      # same asof, re-read
    pc3, ledger = _advance(chain, doc, "2026-01-01", ledger)
    assert [pc1["state"], pc2["state"], pc3["state"]] == ["dormant"] * 3
    assert [r["transition"] for r in ledger] == [], "no arm row, and therefore no failed row"


def test_veto_lifts_once_the_falsifier_stops_firing():
    """The veto is a per-asof gate, not a kill: the chain arms normally the day the
    falsifier stops firing."""
    chain = _synth_chain(n_hops=2, lag_hi=60)
    pc, ledger = _advance(chain, {"n0": True, "n1": False, "n2": False, "kill": True},
                          "2026-01-01", [])
    assert pc["state"] == "dormant" and ledger == []
    pc, ledger = _advance(chain, {"n0": True, "n1": False, "n2": False, "kill": False},
                          "2026-01-02", ledger)
    assert pc["state"] == "arming"
    assert [r["transition"] for r in ledger] == ["arming"]
    assert pc["episode_id"].endswith("2026-01-02")


# --------------------------------------------------------------------------- #
# rev-1.4 — the GATED falsifier keeps an armed episode alive until the gate opens
# --------------------------------------------------------------------------- #
def _gated_chain() -> dict:
    """A 1-hop chain carrying the rev-1 gated falsifier shape: `all[63d push, off_high < 4]`
    — 'still climbing AND still pressing its highs'."""
    c = _synth_chain(n_hops=1, lag_hi=120)
    c["falsifiers"] = [{
        "when": {"all": [
            {"series": "LVL", "metric": "ret_bp", "window": 63, "op": "gt", "value": 15},
            {"series": "LVL", "metric": "off_high_bp", "window": 10, "op": "lt", "value": 4},
        ]},
        "src": "fred",
        "note": "still pressing its highs while armed — restriction still building",
    }]
    return c


def _mixed_adapters(doc: dict, data_dir: Path) -> dict:
    return {"synth": _FakeStateAdapter(doc), "fred": tc._SeriesAdapter(data_dir, "fred")}


def _advance_mixed(chain, doc, data_dir, asof, prior):
    res = tc.evaluate_chain(chain, _mixed_adapters(doc, data_dir), asof, prior=prior)
    return res["per_chain"], prior + res["transitions"]


def test_off_high_gate_keeps_an_armed_episode_alive_until_the_series_presses_new_highs(tmp_path):
    """The rev-1 gate's whole purpose: a trailing 63d window stays red for weeks after a
    true peak. With the plateau shape the bare push leg is TRUE and the episode must SURVIVE;
    only when the series presses new highs again does the falsifier fire."""
    chain = _gated_chain()
    data_dir = tmp_path / "data"
    _write_level_series(tmp_path, "fred", "LVL", _plateau_series())
    ad = tc._SeriesAdapter(data_dir, "fred")
    # fixture self-check: the 63d push leg IS true, and the gate leg is what blocks
    push, _ = tc._series_metric(ad, {"series": "LVL", "metric": "ret_bp", "window": 63})
    off, _ = tc._series_metric(ad, {"series": "LVL", "metric": "off_high_bp", "window": 10})
    assert push > 15, push
    assert off >= 4, off

    doc = {"n0": True, "n1": False}
    pc, ledger = _advance_mixed(chain, doc, data_dir, "2026-05-01", [])
    assert pc["state"] == "arming", "the gate blocks the falsifier, so the chain may arm"
    pc, ledger = _advance_mixed(chain, doc, data_dir, "2026-05-08", ledger)
    assert pc["state"] == "arming", "off the highs → the falsifier stays gated, episode alive"
    assert pc["falsifier_fired"] is None
    assert [r["transition"] for r in ledger] == ["arming"], "no failed row while gated"

    # flip the tape: the series presses new highs again → off_high_bp = 0 → the gate opens
    _write_level_series(tmp_path, "fred", "LVL", _pressing_series())
    assert tc._series_metric(tc._SeriesAdapter(data_dir, "fred"),
                             {"series": "LVL", "metric": "off_high_bp", "window": 10})[0] == 0.0
    pc, ledger = _advance_mixed(chain, doc, data_dir, "2026-05-15", ledger)
    assert pc["state"] == "failed"
    assert pc["falsifier_fired"]["index"] == 0
    assert ledger[-1]["transition"] == "failed"


# --------------------------------------------------------------------------- #
# rev-1.5 — `turn_watch`: display-only annotation on an OPEN episode
# --------------------------------------------------------------------------- #
_STALL_LABEL = {"en": "At the extreme, momentum fading — watching for the turn",
                "zh": "处于极值、动能减弱——观察拐点"}


def _stall_series_chain(series: str = "LVL") -> dict:
    c = _synth_chain(n_hops=1, lag_hi=90)
    c["falsifiers"] = []
    c["stall"] = {"when": {"series": series, "metric": "off_high_bp", "window": 10,
                           "op": "gte", "value": 4},
                  "src": "fred", "label": _STALL_LABEL}
    return c


def test_turn_watch_stalling_true_carries_label_and_receipts(tmp_path):
    chain = _stall_series_chain()
    data_dir = tmp_path / "data"
    _write_level_series(tmp_path, "fred", "LVL", _plateau_series())
    pc, _ = _advance_mixed(chain, {"n0": True, "n1": False}, data_dir, "2026-05-01", [])
    assert pc["state"] == "arming"
    tw = pc["turn_watch"]
    assert tw["stalling"] is True
    assert tw["label"] == _STALL_LABEL
    assert tw["receipts"] and tw["receipts"][0]["metric"] == "off_high_bp"
    assert tw["receipts"][0]["passed"] is True


def test_turn_watch_stalling_false_carries_no_label(tmp_path):
    chain = _stall_series_chain()
    data_dir = tmp_path / "data"
    _write_level_series(tmp_path, "fred", "LVL", _pressing_series())   # at its high → 0bp off
    pc, _ = _advance_mixed(chain, {"n0": True, "n1": False}, data_dir, "2026-05-01", [])
    assert pc["state"] == "arming"
    assert pc["turn_watch"]["stalling"] is False
    assert "label" not in pc["turn_watch"], "copy is carried only while the shape holds"
    assert pc["turn_watch"]["receipts"]


def test_turn_watch_absent_on_terminal_and_dormant_states(tmp_path):
    chain = _stall_series_chain()
    data_dir = tmp_path / "data"
    _write_level_series(tmp_path, "fred", "LVL", _plateau_series())
    # dormant (node 0 false) → no annotation at all
    pc, ledger = _advance_mixed(chain, {"n0": False, "n1": False}, data_dir, "2026-05-01", [])
    assert pc["state"] == "dormant" and "turn_watch" not in pc
    # arm, then let the 90d window close unconfirmed → expired (terminal) → annotation gone
    pc, ledger = _advance_mixed(chain, {"n0": True, "n1": False}, data_dir, "2026-05-02", ledger)
    assert pc["state"] == "arming" and "turn_watch" in pc
    pc, ledger = _advance_mixed(chain, {"n0": True, "n1": False}, data_dir, "2026-09-30", ledger)
    assert pc["state"] == "expired"
    assert "turn_watch" not in pc, "a closed episode has no turn to watch"


def test_turn_watch_absent_when_no_stall_declared():
    chain = _synth_chain(n_hops=1)
    pc, _ = _advance(chain, {"n0": True, "n1": False, "kill": False}, "2026-05-01", [])
    assert pc["state"] == "arming"
    assert "turn_watch" not in pc


def test_turn_watch_fails_open_on_an_unresolvable_stall_test(tmp_path):
    """An unevaluable stall test prints stalling:False + the reason — it never flips a state,
    appends a row, or crashes (same fail-open contract as a falsifier)."""
    chain = _stall_series_chain(series="MISSING")
    data_dir = tmp_path / "data"
    _write_level_series(tmp_path, "fred", "LVL", _plateau_series())
    pc, ledger = _advance_mixed(chain, {"n0": True, "n1": False}, data_dir, "2026-05-01", [])
    assert pc["state"] == "arming"
    assert pc["turn_watch"]["stalling"] is False
    assert "MISSING" in pc["turn_watch"]["unresolved"]
    assert "receipts" not in pc["turn_watch"]
    assert [r["transition"] for r in ledger] == ["arming"]


# --------------------------------------------------------------------------- #
# rev-1.6 — front-facing vocabulary: no refutation register on a chain state
# --------------------------------------------------------------------------- #
def test_failed_state_label_is_de_escalated():
    """Operator ruling 2026-07-27 (#3821): falsifier/refutation language is never
    front-facing. The chain-state label reads 'Halted', not the refutation register."""
    assert tc.STATE_LABELS["failed"] == {"en": "Halted", "zh": "已中止"}
    src = (REPO_ROOT / "engine" / "transmission_chains.py").read_text(encoding="utf-8")
    assert "已证伪" not in src, "the refutation register must not appear in this module"
    assert "证伪" not in src


# --------------------------------------------------------------------------- #
# rev-1.7 — the committed rev-1 peak chains load + validate with the new grammar
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("slug", ["real_rate_peak_gold_rerate", "real_rate_peak_crypto_rerate"])
def test_rev1_peak_chains_load_and_validate(slug):
    chains = tc.load_chains(REPO_ROOT, strict=True)
    chain = next(c for c in chains if c["chain"] == slug)
    tc.validate_chain(chain, f"{slug}.yaml")          # explicit re-validate (no raise)
    assert chain["rev"] == 1
    # the gated falsifier + the stall block are both compiled, not prose
    gate = chain["falsifiers"][0]["when"]["all"]
    assert {leg["metric"] for leg in gate} == {"ret_bp", "off_high_bp"}
    assert chain["stall"]["src"] == "fred"
    assert chain["stall"]["label"]["en"] and chain["stall"]["label"]["zh"]
    assert {leg["metric"] for leg in chain["stall"]["when"]["all"]} == {"ret_bp", "off_high_bp"}
    # the peak falsifier judges the ARM (scope 0); every post-rolldown falsifier is scoped
    # to hop 1, so none of them can veto arming or fail a merely-armed episode
    assert chain["falsifiers"][0].get("from_hop", 0) == 0
    assert [fx.get("from_hop", 0) for fx in chain["falsifiers"][1:]] == \
           [1] * (len(chain["falsifiers"]) - 1), chain["falsifiers"]


# =========================================================================== #
# rev-1.8 — HOP-SCOPED falsifiers (`from_hop`). A falsifier whose prose presupposes a hop
# is silent until that hop has CONFIRMED. Without the scope the loop's first-hit
# short-circuit hides the defect: gating an earlier falsifier un-masks a terminal one that
# then judges a leg the episode never reached (measured 2026-08-07 — the gold chain's
# `GC=F 63d < 0` vetoed ARMING on gold's trailing quarter).
# =========================================================================== #
def _scoped_chain(from_hop, *, n_hops: int = 2) -> dict:
    """A chain whose ONLY falsifier is scoped to `from_hop` and keys on the `kill` flag."""
    c = _synth_chain(n_hops=n_hops, lag_hi=60)
    c["falsifiers"] = [{"when": {"path": "kill", "op": "is_true"}, "src": "synth",
                        "from_hop": from_hop, "note": "terminal leg not transmitting"}]
    return c


def test_from_hop_validation_rejects_bad_scopes():
    """Non-int, negative, and out-of-range scopes are rejected, and the message NAMES the
    falsifier index (a library edit must point at the offending entry)."""
    for bad in ("1", 1.5, True, -1, 2, 99):
        chain = _scoped_chain(bad, n_hops=2)          # 2 hops → valid range is [0, 1]
        with pytest.raises(tc.ChainSchemaError, match=r"falsifier\[0\] 'from_hop'"):
            tc.validate_chain(chain, "synth_chain.yaml")


def test_from_hop_validation_accepts_the_valid_range_and_the_default():
    for good in (0, 1):
        tc.validate_chain(_scoped_chain(good, n_hops=2), "synth_chain.yaml")
    # absent from_hop is the default-0 scope and stays valid (back-compat with every
    # pre-rev-1 chain file in the library)
    plain = _synth_chain(n_hops=2)
    assert "from_hop" not in plain["falsifiers"][0]
    tc.validate_chain(plain, "synth_chain.yaml")


def test_scoped_falsifier_does_not_veto_arming():
    """from_hop:1 + a TRUE `when` on the arming day: no veto, no failure — the chain arms.
    This is the gold-chain defect, reduced to a fixture."""
    chain = _scoped_chain(1)
    doc = {"n0": True, "n1": False, "n2": False, "kill": True}
    pc, ledger = _advance(chain, doc, "2026-01-01", [])
    assert pc["state"] == "arming", "a post-rolldown falsifier must not judge the arm"
    assert "arm_veto" not in pc
    assert pc["falsifier_fired"] is None
    assert [r["transition"] for r in ledger] == ["arming"]
    # ...and it stays silent on later days while the episode is still only ARMED (hop 0)
    pc, ledger = _advance(chain, doc, "2026-01-08", ledger)
    assert pc["state"] == "arming"
    assert pc["falsifier_fired"] is None
    assert [r["transition"] for r in ledger] == ["arming"], "no failed row while out of scope"


def test_scoped_falsifier_fires_once_its_hop_confirms():
    """The same falsifier IS live once hop 1 has confirmed — scoping delays it, never
    disables it."""
    chain = _scoped_chain(1)
    ledger: list[dict] = []
    pc, ledger = _advance(chain, {"n0": True, "n1": False, "n2": False, "kill": False},
                          "2026-01-01", ledger)
    assert pc["state"] == "arming"
    # hop 1 confirms → propagating(1): last_hop is now 1, so from_hop:1 comes into scope
    pc, ledger = _advance(chain, {"n0": True, "n1": True, "n2": False, "kill": False},
                          "2026-01-10", ledger)
    assert pc["state"] == "propagating" and pc["hop"] == 1
    pc, ledger = _advance(chain, {"n0": True, "n1": True, "n2": False, "kill": True},
                          "2026-01-15", ledger)
    assert pc["state"] == "failed"
    assert pc["falsifier_fired"]["index"] == 0
    assert ledger[-1]["transition"] == "failed"


def test_unscoped_falsifier_still_vetoes_the_arm():
    """Control: the SAME fixture with the default scope (0) still vetoes — the scope is what
    changes the outcome, not the veto going soft."""
    chain = _scoped_chain(0)
    doc = {"n0": True, "n1": False, "n2": False, "kill": True}
    pc, ledger = _advance(chain, doc, "2026-01-01", [])
    assert pc["state"] == "dormant"
    assert pc["arm_veto"]["index"] == 0
    assert ledger == []


def test_scoping_does_not_mask_an_in_scope_sibling():
    """First-hit short-circuit honesty: an OUT-of-scope falsifier is skipped, not treated as
    a miss that ends the sweep — an in-scope sibling later in the list still fires, and the
    reported index is the one that actually fired."""
    chain = _synth_chain(n_hops=2, lag_hi=60)
    chain["falsifiers"] = [
        {"when": {"path": "terminal_dead", "op": "is_true"}, "src": "synth",
         "from_hop": 1, "note": "terminal leg (out of scope while merely armed)"},
        {"when": {"path": "kill", "op": "is_true"}, "src": "synth",
         "note": "peak refuted (in scope from the arming day)"},
    ]
    doc = {"n0": True, "n1": False, "n2": False, "terminal_dead": True, "kill": True}
    pc, ledger = _advance(chain, doc, "2026-01-01", [])
    assert pc["state"] == "dormant"
    assert pc["arm_veto"]["index"] == 1, "the in-scope falsifier must be the one reported"
    assert ledger == []
