"""TXI-W5 Loop-C closure — proposal pack + ingest + gate + Article-1/2 tests.

These exercise the autonomous-chain-proposal pathway end to end WITHOUT writing into the
real repo: the ingest/runner write-path constants (_PROPOSED_DIR, _REJECTS_LEDGER, _RUN_LOG)
are monkeypatched to a tmp dir, and the gate configs are monkeypatched to controlled dicts.
Node RESOLUTION runs against the real on-disk series (so a valid chain actually resolves);
DEDUP is tested with an injected existing-signature set.

Guards the #3357 vacuous-green trap: this file is BOTH declared in ci.yml paths AND run as a
pytest step inside the transmission-chains ci-pack job (see ci.yml).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import engine.transmission_chains as tc
import scripts.ingest_transmission_chains as ingest_mod
import scripts.propose_transmission_chains as pack_mod
import scripts.run_transmission_proposals as run_mod

REPO_ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

def _valid_candidate(slug: str = "test_oil_hy_probe") -> dict:
    """A structurally valid chain whose nodes bind to series present on disk (CL=F, HYG, LQD)."""
    return {
        "chain": slug,
        "title": {"en": "Oil shock -> HY credit stress", "zh": "油价冲击 -> 高收益信用压力"},
        "nodes": {
            "oil_shock": {
                "src": "yahoo",
                "test": {"series": "CL=F", "metric": "ret", "window": 60, "op": "gt", "value": 25},
            },
            "hy_stress": {
                "src": "yahoo",
                "test": {"series": "HYG", "ratio": "LQD", "metric": "ratio_ret",
                         "window": 22, "op": "lt", "value": -2.0},
            },
        },
        "hops": [
            {"from": "oil_shock", "to": "hy_stress", "sign": "-", "lag_d": [5, 60],
             "condition": {"en": "supply-driven shock", "zh": "供给驱动"},
             "mechanism": {"en": "energy cost squeezes leveraged issuers", "zh": "能源成本挤压"},
             "prior": "theory (cost-push)"},
        ],
        "falsifiers": [
            {"when": {"series": "HYG", "ratio": "LQD", "metric": "ratio_ret",
                      "window": 60, "op": "gt", "value": 0},
             "note": "HY outperforming IG despite oil shock"},
        ],
        "null_model": "does conditioning on oil beat unconditional HY momentum?",
        "exposure_screens": {},
        "provenance": {"theory": ["cost-push"], "episodes": ["2015-16"], "added_by": "chf_proposal"},
    }


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Redirect the ingest/runner write paths into tmp_path so tests never touch the repo."""
    proposed = tmp_path / "knowledge" / "transmission" / "proposed"
    rejects = tmp_path / "data" / "transmission" / "proposal_rejects.jsonl"
    runlog = tmp_path / "data" / "transmission" / "proposal_runs.jsonl"
    monkeypatch.setattr(ingest_mod, "_PROPOSED_DIR", proposed)
    monkeypatch.setattr(ingest_mod, "_REJECTS_LEDGER", rejects)
    monkeypatch.setattr(run_mod, "_RUN_LOG", runlog)
    return {"root": tmp_path, "proposed": proposed, "rejects": rejects, "runlog": runlog}


def _write_inbox(tmp_path: Path, candidates: list) -> Path:
    inbox = tmp_path / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "replies.json").write_text(json.dumps(candidates), encoding="utf-8")
    return inbox


# --------------------------------------------------------------------------- #
# A. Pack generator
# --------------------------------------------------------------------------- #

def test_pack_is_well_formed():
    """The pack renders every load-bearing section from live artifacts, no crash."""
    pack = pack_mod.build_pack(n_requested=8, asof="2026-07-25")
    assert isinstance(pack, str) and len(pack) > 500
    for marker in (
        "TRANSMISSION-CHAIN PROPOSAL PACK",
        "RESOLVABLE SOURCE ADAPTERS",
        "NODE-TEST GRAMMAR",
        "DO-NOT-REPROPOSE",
        "OUTPUT FORMAT",
    ):
        assert marker in pack, f"pack missing section: {marker}"
    # The pack pulls the adapter/op inventory from the engine (single source of truth).
    for adapter in ("yahoo", "transmission_state", "forex_state"):
        assert adapter in pack
    for op in tc._VALID_OPS:
        assert op in pack


def test_pack_lists_existing_library_for_dedup():
    """Existing chains are rendered as DO-NOT-REPROPOSE so the LLM proposes something new."""
    pack = pack_mod.build_pack(n_requested=4, asof="2026-07-25")
    existing = {c["chain"] for c in tc.load_chains(REPO_ROOT)}
    assert existing, "expected some seed chains in the library"
    # at least one real seed slug must appear in the do-not-repropose section
    assert any(slug in pack for slug in existing)


def test_pack_meta_carries_proposed_at_without_clock(tmp_path):
    """proposed_at flows from asof (a data date), not a fresh clock read on the chain."""
    meta = pack_mod.build_meta(6, "2026-07-25", "2026-07-26T00:00:00+00:00")
    assert meta["proposed_at"] == "2026-07-25"
    assert meta["iso_week"] == "2026-W30"
    assert meta["pack_id"].startswith("txi-")


# --------------------------------------------------------------------------- #
# B. Ingest — accept / reject routing
# --------------------------------------------------------------------------- #

def test_valid_proposal_becomes_hypothesis_tier_yaml(sandbox, tmp_path):
    inbox = _write_inbox(tmp_path, [_valid_candidate("test_oil_hy_probe")])
    stats = ingest_mod.ingest(inbox, proposed_at="2026-07-25", write=True)
    assert stats["accepted"] == 1 and stats["rejected"] == 0
    yaml_path = sandbox["proposed"] / "test_oil_hy_probe.yaml"
    assert yaml_path.exists(), "valid proposal must be written to proposed/"
    import yaml
    written = yaml.safe_load(yaml_path.read_text())
    assert written["tier"] == "hypothesis"
    assert written["rev"] == 0
    assert written["source"] == "chf_proposal"
    assert written["proposed_at"] == "2026-07-25"


def test_malformed_proposal_rejected_never_written(sandbox, tmp_path):
    """Unknown test op → schema_invalid → rejects ledger, no YAML."""
    bad = _valid_candidate("test_bad_op")
    bad["nodes"]["oil_shock"]["test"]["op"] = "BOGUS_OP"
    inbox = _write_inbox(tmp_path, [bad])
    stats = ingest_mod.ingest(inbox, proposed_at="2026-07-25", write=True)
    assert stats["accepted"] == 0 and stats["rejected"] == 1
    assert not (sandbox["proposed"] / "test_bad_op.yaml").exists()
    lines = sandbox["rejects"].read_text().splitlines()
    rec = json.loads(lines[-1])
    assert rec["slug"] == "test_bad_op"
    assert rec["reason"] == "schema_invalid"


def test_unresolvable_node_rejected_never_written(sandbox, tmp_path):
    """A node bound to a series NOT on disk → unresolvable_node → rejected, no faked chain."""
    bad = _valid_candidate("test_fake_series")
    bad["nodes"]["oil_shock"]["test"]["series"] = "NOT_A_REAL_TICKER_9999"
    inbox = _write_inbox(tmp_path, [bad])
    stats = ingest_mod.ingest(inbox, proposed_at="2026-07-25", write=True)
    assert stats["accepted"] == 0 and stats["rejected"] == 1
    assert not (sandbox["proposed"] / "test_fake_series.yaml").exists()
    rec = json.loads(sandbox["rejects"].read_text().splitlines()[-1])
    assert rec["reason"] == "unresolvable_node"
    assert "NOT_A_REAL_TICKER_9999" in rec["detail"]


def test_duplicate_node_set_rejected(sandbox, tmp_path, monkeypatch):
    """A proposal whose node-set matches an existing chain is dropped as a duplicate."""
    cand = _valid_candidate("test_dup_probe")
    dup_sig = pack_mod._node_signature(cand)
    # Inject an existing library that already contains this exact node-set.
    monkeypatch.setattr(ingest_mod, "_existing_signatures", lambda: {dup_sig})
    inbox = _write_inbox(tmp_path, [cand])
    stats = ingest_mod.ingest(inbox, proposed_at="2026-07-25", write=True)
    assert stats["accepted"] == 0 and stats["dup"] == 1
    assert not (sandbox["proposed"] / "test_dup_probe.yaml").exists()
    rec = json.loads(sandbox["rejects"].read_text().splitlines()[-1])
    assert rec["reason"] == "duplicate_node_set"


def test_dry_run_writes_nothing(sandbox, tmp_path):
    inbox = _write_inbox(tmp_path, [_valid_candidate("test_dryrun")])
    stats = ingest_mod.ingest(inbox, proposed_at="2026-07-25", write=False)
    assert stats["accepted"] == 1  # accounted, but...
    assert stats["dry_run"] is True
    assert not (sandbox["proposed"] / "test_dryrun.yaml").exists()
    assert not sandbox["rejects"].exists()


def test_ingested_chain_round_trips_through_w1(sandbox, tmp_path, monkeypatch):
    """A written proposal must be loadable + validatable by W1 from proposed/ (auto-compile)."""
    # Point the engine loader at the sandbox root so load_chains reads OUR proposed/ dir.
    inbox = _write_inbox(tmp_path, [_valid_candidate("test_roundtrip")])
    ingest_mod.ingest(inbox, proposed_at="2026-07-25", write=True)
    chains = {c["chain"]: c for c in tc.load_chains(sandbox["root"], strict=True)}
    assert "test_roundtrip" in chains
    c = chains["test_roundtrip"]
    assert c.get("_proposed") is True
    assert c["_filename"] == "proposed/test_roundtrip.yaml"
    assert c["tier"] == "hypothesis"


# --------------------------------------------------------------------------- #
# C. Gate — default OFF no-ops
# --------------------------------------------------------------------------- #

def _patch_gate(monkeypatch, *, auto_loop: bool, enabled: bool):
    def fake_load(path):
        if path == run_mod._CHF_CONFIG:
            return {"auto_loop": auto_loop}
        if path == run_mod._LANE_CONFIG:
            return {"enabled": enabled, "n_requested": 6, "reply_inbox": None}
        return {}
    monkeypatch.setattr(run_mod, "_load_yaml", fake_load)


def test_gate_off_by_default_lane_flag(sandbox, monkeypatch):
    """Lane sub-flag OFF (auto_loop ON) → scheduled run no-ops, writes nothing."""
    _patch_gate(monkeypatch, auto_loop=True, enabled=False)
    rc = run_mod.run("scheduled", asof="2026-07-25", write=True)
    assert rc == 0
    assert not sandbox["runlog"].exists(), "gate-off run must write no run log"


def test_gate_off_chf_auto_loop(sandbox, monkeypatch):
    """CHF auto_loop OFF → scheduled run no-ops even if the lane flag is on (rides CHF gate)."""
    _patch_gate(monkeypatch, auto_loop=False, enabled=True)
    rc = run_mod.run("scheduled", asof="2026-07-25", write=True)
    assert rc == 0
    assert not sandbox["runlog"].exists()


def test_gate_state_reports_both_flags(monkeypatch):
    _patch_gate(monkeypatch, auto_loop=True, enabled=False)
    auto_loop, lane_enabled, blocked = run_mod._gate_state()
    assert auto_loop is True and lane_enabled is False
    assert "transmission_proposals.enabled is OFF" in blocked


def test_both_gates_open_emits_and_ingests(sandbox, tmp_path, monkeypatch):
    """Both gates on + a reply inbox present → the full cycle runs and writes a run log."""
    inbox = _write_inbox(tmp_path, [_valid_candidate("test_gate_cycle")])

    def fake_load(path):
        if path == run_mod._CHF_CONFIG:
            return {"auto_loop": True}
        if path == run_mod._LANE_CONFIG:
            return {"enabled": True, "n_requested": 6, "reply_inbox": str(inbox)}
        return {}
    monkeypatch.setattr(run_mod, "_load_yaml", fake_load)

    rc = run_mod.run("scheduled", asof="2026-07-25", write=True)
    assert rc == 0
    assert (sandbox["proposed"] / "test_gate_cycle.yaml").exists()
    assert sandbox["runlog"].exists()
    row = json.loads(sandbox["runlog"].read_text().splitlines()[-1])
    assert row["gate"] == {"auto_loop": True, "lane_enabled": True}
    assert row["ingest"]["accepted"] == 1


# --------------------------------------------------------------------------- #
# D. Article 1/2 — a proposed chain never emits authority
# --------------------------------------------------------------------------- #

def test_ingested_chain_carries_no_authority_field(sandbox, tmp_path):
    """The materialized chain is hypothesis-tier and carries NO scoring/authority field."""
    inbox = _write_inbox(tmp_path, [_valid_candidate("test_no_authority")])
    ingest_mod.ingest(inbox, proposed_at="2026-07-25", write=True)
    import yaml
    written = yaml.safe_load((sandbox["proposed"] / "test_no_authority.yaml").read_text())
    assert written["tier"] == "hypothesis"
    forbidden = ingest_mod._FORBIDDEN_AUTHORITY_KEYS
    # no forbidden key anywhere in the written chain
    assert not ingest_mod._find_forbidden_keys(written)
    for k in written:
        assert k not in forbidden


def test_authority_field_in_proposal_is_rejected(sandbox, tmp_path):
    """A candidate trying to smuggle an authority field (alpha/score/rank) is dropped."""
    bad = _valid_candidate("test_authority_grab")
    bad["nodes"]["oil_shock"]["alpha"] = 0.9  # authority field
    inbox = _write_inbox(tmp_path, [bad])
    stats = ingest_mod.ingest(inbox, proposed_at="2026-07-25", write=True)
    assert stats["accepted"] == 0 and stats["rejected"] == 1
    assert not (sandbox["proposed"] / "test_authority_grab.yaml").exists()
    rec = json.loads(sandbox["rejects"].read_text().splitlines()[-1])
    assert rec["reason"] == "authority_field_forbidden"


def test_stamped_fields_cannot_be_smuggled(sandbox, tmp_path):
    """A candidate that pre-sets tier=calibrated is overridden to hypothesis by the ingest."""
    bad = _valid_candidate("test_tier_smuggle")
    bad["tier"] = "calibrated"   # try to grant itself authority tier
    bad["rev"] = 99
    inbox = _write_inbox(tmp_path, [bad])
    stats = ingest_mod.ingest(inbox, proposed_at="2026-07-25", write=True)
    assert stats["accepted"] == 1
    import yaml
    written = yaml.safe_load((sandbox["proposed"] / "test_tier_smuggle.yaml").read_text())
    assert written["tier"] == "hypothesis"  # STAMPED over the smuggled value
    assert written["rev"] == 0
