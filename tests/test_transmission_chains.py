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
    for c in state["chains"]:
        assert c["state"] in {"dormant", "arming", "propagating", "expressed", "failed", "expired"}
        assert c["display_only"] is True
        # nulls printed honestly, not hidden; W3 base rates untested
        assert c["base_rates"] is None
        assert c["blast"] == []          # no substrate sweep → W1 default

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
