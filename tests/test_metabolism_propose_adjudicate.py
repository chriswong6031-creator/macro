"""tests/test_metabolism_propose_adjudicate.py — hermetic tests for A4 + A5.

COVERAGE
  A4 propose:
    - content_hash determinism + JSON extraction tolerance
    - build_docket: validation, T2-forbidden, in-cycle dedup, case-law dedup,
      cap to max_docket_size, verify-compatible fitness contract minted
    - register_contracts → trial_ledger (family metabolism_til)
    - propose() end-to-end with injected proposals (no network)
    - CLI kill-switch INERT no-op (AUTONOMY_PAUSED unset)
  A5 adjudicate:
    - deterministic case-law screen (kill / active / T2 / clean)
    - orchestrator grant/deny + R-AUT-1 de-escalation (screen deny beats LLM grant)
    - adversary veto + adversary ledger + fail-closed missing-opinion veto
    - idempotent re-run (no duplicate governance rows)
    - resolve_two_key matrix (T0 orch-only; T1/T2 both keys; fail-closed)
    - governance vocabulary carries the two new event types
    - CLI kill-switch INERT no-op

All tests are HERMETIC: tmp dirs, in-process, no real data / network / subprocess.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tmp_root() -> Path:
    d = Path(tempfile.mkdtemp())
    for sub in (
        "data/metabolism/journal", "data/metabolism/fitness",
        "data/metabolism/dockets", "data/neuralweb", "config", "docs", "research",
    ):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d


def _docket_path(root, cycle_id):
    from engine.metabolism.propose import docket_path
    return docket_path(cycle_id, root)


def _sample_proposal(title="Add unicode filename coverage test for the manifest scanner",
                     tier="T0", kind="test", sensor="live_leg_quality"):
    return {
        "title": title,
        "tier": tier,
        "kind": kind,
        "targets_sensor": sensor,
        "rationale": "improves coverage of the sensor's edge cases",
        "fitness_contract": {
            "sensor": sensor,
            "expected_sign": "+",
            "band": ">= +0.02 hit-rate",
            "check_by": "2026-10-15",
            "placebo_to_beat": "shadow placebo tape",
        },
    }


# ===========================================================================
# A4 — propose core
# ===========================================================================

class TestProposeCore:

    def test_content_hash_deterministic(self):
        from engine.metabolism.propose import content_hash
        a = content_hash("Fix the Foo Bar", "sensor_x", "test")
        b = content_hash("fix   the  foo-bar", "sensor_x", "test")
        assert a == b               # normalization-invariant
        assert len(a) == 12
        assert a != content_hash("Fix the Foo Bar", "sensor_y", "test")

    def test_extract_json_array_tolerance(self):
        from engine.metabolism.propose import _extract_json_array
        arr = '[{"title":"a"},{"title":"b"}]'
        assert len(_extract_json_array(arr)) == 2
        fenced = "```json\n" + arr + "\n```"
        assert len(_extract_json_array(fenced)) == 2
        wrapped = 'Here you go:\n' + arr + '\nDone.'
        assert len(_extract_json_array(wrapped)) == 2
        obj = '{"proposals":[{"title":"a"}]}'
        assert len(_extract_json_array(obj)) == 1
        assert _extract_json_array("not json") == []
        assert _extract_json_array("") == []

    def test_build_docket_validation_and_t2_forbidden(self):
        from engine.metabolism.propose import build_docket
        root = _tmp_root()
        raw = [
            _sample_proposal(),
            {"title": "", "tier": "T0", "fitness_contract": {"sensor": "x"}},  # no title
            {"title": "bad tier", "tier": "T9", "fitness_contract": {"sensor": "x"}},
            _sample_proposal(title="Promote skew signal to scored path", tier="T2"),  # forbidden
            {"title": "no contract", "tier": "T0"},  # missing fitness_contract
        ]
        d = build_docket("cycle-x", raw, root=root, max_docket_size=5)
        assert len(d["proposals"]) == 1
        assert len(d["rejected"]) == 4
        reasons = " ".join(r["reason"] for r in d["rejected"])
        assert "T2" in reasons and "title" in reasons and "tier" in reasons

    def test_build_docket_dedup_within_cycle_and_cap(self):
        from engine.metabolism.propose import build_docket
        root = _tmp_root()
        dup = _sample_proposal()
        raw = [dup, dict(dup), _sample_proposal(title="second distinct thing", sensor="front_run_lead")]
        d = build_docket("cycle-x", raw, root=root, max_docket_size=5)
        assert len(d["proposals"]) == 2  # duplicate collapsed
        # cap
        many = [_sample_proposal(title=f"distinct proposal number {i}", sensor=f"s{i}")
                for i in range(6)]
        d2 = build_docket("cycle-y", many, root=root, max_docket_size=3)
        assert len(d2["proposals"]) == 3
        assert any("over max_docket_size" in r["reason"] for r in d2["rejected"])

    def test_build_docket_case_law_dedup(self):
        from engine.metabolism.propose import build_docket
        root = _tmp_root()
        (root / "research" / "DO_NOT_REBUILD.md").write_text(
            "Killed: the vanna charm intensity narrative signal is dead (confound).")
        raw = [_sample_proposal(title="Revive the vanna charm intensity narrative signal",
                                sensor="x", kind="engine")]
        d = build_docket("cycle-z", raw, root=root, max_docket_size=5)
        assert len(d["proposals"]) == 0
        assert "DO_NOT_REBUILD" in d["rejected"][0]["reason"]

    def test_contract_is_verify_compatible(self):
        from engine.metabolism.propose import build_docket
        root = _tmp_root()
        d = build_docket("cycle-x", [_sample_proposal()], root=root, max_docket_size=5)
        fc = d["proposals"][0]["fitness_contract"]
        # exactly the keys engine.metabolism.verify.verify_proposal reads
        for k in ("proposal_id", "sensor", "expected_sign", "band", "check_by",
                  "placebo_to_beat", "falsifier_spec", "asof"):
            assert k in fc
        assert fc["expected_sign"] in ("+", "-")
        assert fc["check_by"] >= "2026-10-15"      # floored to first-real check_by
        assert isinstance(fc["falsifier_spec"], dict)
        assert fc["proposal_id"] == d["proposals"][0]["proposal_id"]

    def test_register_contracts_writes_trial_ledger(self):
        from engine.metabolism.propose import build_docket, register_contracts
        root = _tmp_root()
        d = build_docket("cycle-x", [_sample_proposal(),
                                     _sample_proposal(title="another one", sensor="front_run_lead")],
                         root=root, max_docket_size=5)
        n = register_contracts(d, root=root)
        assert n == 2
        led = (root / "data" / "trial_ledger.jsonl").read_text().splitlines()
        rows = [json.loads(x) for x in led if x.strip()]
        assert rows and all(r.get("family") == "metabolism_til" for r in rows)
        assert all(r.get("kind") == "declared_budget" for r in rows)

    def test_propose_end_to_end_injected(self):
        from engine.metabolism.propose import propose, docket_path
        root = _tmp_root()
        res = propose("cycle-e2e", root=root, max_docket_size=5,
                      today="2026-07-09",
                      injected_proposals=[_sample_proposal()])
        assert res["meta"]["n_proposals"] == 1
        assert res["meta"]["registered"] == 1
        p = docket_path("cycle-e2e", root)
        assert p.exists()
        on_disk = json.loads(p.read_text())
        assert on_disk["schema"] == "metabolism.docket.v1"
        assert on_disk["authority"]["is_context_only"] is True

    def test_propose_never_raises_on_garbage(self):
        from engine.metabolism.propose import propose
        root = _tmp_root()
        # None inside the list + a non-dict — must degrade, not raise.
        res = propose("cycle-g", root=root, injected_proposals=[None, 42, _sample_proposal()])
        assert res["meta"]["n_proposals"] == 1


# ===========================================================================
# A4 — CLI INERT kill-switch
# ===========================================================================

class TestProposeCLIInert:

    def test_cli_paused_is_noop(self, monkeypatch):
        monkeypatch.delenv("AUTONOMY_PAUSED", raising=False)  # unset → paused
        from scripts.metabolism_propose import main
        from scripts.metabolism_journal import load_journal
        from engine.metabolism.propose import docket_path

        # DISCRIMINATING GUARD (post-review): the pause gate must short-circuit
        # BEFORE preflight/LLM work. Booby-trap check_auth so that if the pause
        # gate is ever removed/reordered, execution reaches it and the test
        # ERRORS — the plain noop_paused-status assertion is shared with the
        # preflight-fail path and would pass even with the gate broken.
        import scripts.preflight_claude_auth as _pf

        def _boom(*a, **k):
            raise AssertionError("check_auth reached while AUTONOMY_PAUSED — pause gate bypassed")
        monkeypatch.setattr(_pf, "check_auth", _boom)

        root = _tmp_root()
        rc = main(["--cycle-id", "cycle-paused", "--root", str(root)])
        assert rc == 0
        j = load_journal("cycle-paused", root=root)
        stage = j["stages"]["propose"]
        assert stage["status"] == "noop_paused"
        # Pause-SPECIFIC signal (not the shared preflight-fail note):
        assert "preflight" not in (stage.get("note") or "").lower()
        # no docket written, no network, no contracts
        assert not docket_path("cycle-paused", root).exists()
        assert not (root / "data" / "trial_ledger.jsonl").exists()

    def test_cli_armed_but_no_provider_is_clean_noop(self, monkeypatch):
        # Armed, but preflight must fail-closed with no token / no claude CLI.
        monkeypatch.setenv("AUTONOMY_PAUSED", "false")
        monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
        from scripts.metabolism_propose import main
        from scripts.metabolism_journal import load_journal
        root = _tmp_root()
        # capability manifest absent in tmp root → broker denies → preflight fails.
        rc = main(["--cycle-id", "cycle-armed", "--root", str(root)])
        assert rc == 0
        j = load_journal("cycle-armed", root=root)
        assert j["stages"]["propose"]["status"] == "noop_paused"
        # pin the gate that fired: preflight fail-closed (not budget/breaker)
        assert "preflight" in (j["stages"]["propose"].get("note") or "").lower()


# ===========================================================================
# A5 — deterministic screen
# ===========================================================================

class TestScreen:

    def test_screen_kill_active_t2_clean(self):
        from engine.metabolism.adjudicate import _deterministic_screen
        cl = {"killed": "the vanna charm intensity narrative signal is dead",
              "active": "options hub v2 flow desk build in flight"}
        assert _deterministic_screen(
            {"title": "Revive vanna charm intensity narrative", "tier": "T1"}, cl)["allow"] is False
        assert _deterministic_screen(
            {"title": "Options hub v2 flow desk polish", "tier": "T1"}, cl)["allow"] is False
        assert _deterministic_screen(
            {"title": "Promote something", "tier": "T2"}, cl)["allow"] is False
        assert _deterministic_screen(
            {"title": "Add a brand new coverage test elsewhere", "tier": "T0"}, cl)["allow"] is True

    def test_screen_catches_kill_hidden_in_rationale(self):
        # A generic title but a rationale that revives a killed construction must
        # still be flagged (the broadened surface rule, absolute overlap >= 3).
        from engine.metabolism.adjudicate import _deterministic_screen
        cl = {"killed": "the vanna charm intensity narrative signal is dead", "active": ""}
        prop = {"title": "Improve a sensor", "tier": "T1",
                "rationale": "revive the vanna charm intensity narrative construction"}
        assert _deterministic_screen(prop, cl)["allow"] is False
        # a benign rationale with < 3 kill-token overlap is allowed
        benign = {"title": "Improve a sensor", "tier": "T1",
                  "rationale": "add a placebo tape coverage test for the join path"}
        assert _deterministic_screen(benign, cl)["allow"] is True


# ===========================================================================
# A5 — orchestrator + adversary rows
# ===========================================================================

def _docket_on_disk(root: Path, cycle_id: str, proposals) -> Path:
    from engine.metabolism.propose import build_docket, write_docket
    d = build_docket(cycle_id, proposals, root=root, max_docket_size=10)
    p = write_docket(d, root=root)
    return p


class TestAdjudicateRoles:

    def test_orchestrator_grant_and_deescalation(self):
        from engine.metabolism.adjudicate import adjudicate_role
        from engine.neuralweb.governance import load_events
        root = _tmp_root()
        clean = _sample_proposal(title="Add coverage for the placebo tape join")
        killed = _sample_proposal(title="Revive insider timing t2 factor", kind="engine", tier="T1")
        # Build the docket in a kill-free root so BOTH proposals land, then add the
        # kill file so the SCREEN (not the docket builder) rejects the killed one at
        # adjudication time — that is what exercises the R-AUT-1 de-escalation path.
        p = _docket_on_disk(root, "cyc1", [clean, killed])
        (root / "research" / "DO_NOT_REBUILD.md").write_text("insider timing t2 factor is dead")
        docket = json.loads(p.read_text())
        pids = [pr["proposal_id"] for pr in docket["proposals"]]
        # LLM grants BOTH; the screen must de-escalate the killed one to deny.
        injected = {pid: {"grant": True, "rationale": "looks good"} for pid in pids}
        res = adjudicate_role("orchestrator", "cyc1", p, run_id="r-orch",
                              root=root, injected=injected)
        by = {r["proposal_id"]: r for r in res}
        # clean → grant; killed-topic → deny despite LLM grant (R-AUT-1)
        assert by[pids[0]]["decision"] == "grant"
        assert by[pids[1]]["decision"] == "deny"
        evs = load_events(root=root, event_type="metabolism_adjudication")
        assert len(evs) == 2 and all(e["article"] is None for e in evs)

    def test_orchestrator_fail_closed_without_opinion(self):
        from engine.metabolism.adjudicate import adjudicate_role
        root = _tmp_root()
        p = _docket_on_disk(root, "cyc2", [_sample_proposal()])
        # empty judgments dict = ran but no opinion for this pid → deny
        res = adjudicate_role("orchestrator", "cyc2", p, run_id="r", root=root, injected={})
        assert res[0]["decision"] == "deny"

    def test_adversary_veto_and_ledger(self):
        from engine.metabolism.adjudicate import adjudicate_role
        root = _tmp_root()
        p = _docket_on_disk(root, "cyc3", [_sample_proposal()])
        pid = json.loads(p.read_text())["proposals"][0]["proposal_id"]
        injected = {pid: {"veto": True, "findings": ["contract band unrealistic"],
                          "tripwire_predictions": ["hit-rate will not move by 0.02"],
                          "rationale": "band too tight"}}
        res = adjudicate_role("adversary", "cyc3", p, run_id="r-adv", root=root, injected=injected)
        assert res[0]["veto"] is True
        led = (root / "data" / "metabolism" / "adversary_ledger.jsonl").read_text().splitlines()
        rows = [json.loads(x) for x in led if x.strip()]
        assert rows[0]["schema"] == "metabolism.adversary_ledger.v1"
        assert rows[0]["tripwire_predictions"] == ["hit-rate will not move by 0.02"]

    def test_adversary_fail_closed_missing_opinion_vetoes(self):
        from engine.metabolism.adjudicate import adjudicate_role
        root = _tmp_root()
        p = _docket_on_disk(root, "cyc4", [_sample_proposal()])
        res = adjudicate_role("adversary", "cyc4", p, run_id="r", root=root, injected={})
        assert res[0]["veto"] is True   # no opinion → fail-closed veto

    def test_idempotent_rerun_no_duplicate_rows(self):
        from engine.metabolism.adjudicate import adjudicate_role
        from engine.neuralweb.governance import load_events
        root = _tmp_root()
        p = _docket_on_disk(root, "cyc5", [_sample_proposal()])
        pid = json.loads(p.read_text())["proposals"][0]["proposal_id"]
        inj = {pid: {"grant": True, "rationale": "ok"}}
        adjudicate_role("orchestrator", "cyc5", p, run_id="r1", root=root, injected=inj)
        n1 = len(load_events(root=root, event_type="metabolism_adjudication"))
        adjudicate_role("orchestrator", "cyc5", p, run_id="r2", root=root, injected=inj)
        n2 = len(load_events(root=root, event_type="metabolism_adjudication"))
        assert n1 == n2 == 1   # resume-safe: no duplicate row


# ===========================================================================
# A5 — two-key resolution matrix
# ===========================================================================

class TestTwoKey:

    def _setup(self, root, tier, orch_grant, adv=None):
        """Write a docket + orchestrator (+optional adversary) rows, return (pid, path)."""
        from engine.metabolism.adjudicate import adjudicate_role
        prop = _sample_proposal(title=f"proposal for {tier}", tier=tier, sensor=f"s-{tier}-{orch_grant}-{adv}")
        p = _docket_on_disk(root, f"cyc-{tier}-{orch_grant}-{adv}", [prop])
        pid = json.loads(p.read_text())["proposals"][0]["proposal_id"]
        adjudicate_role("orchestrator", p.stem, p, run_id="ro", root=root,
                        injected={pid: {"grant": orch_grant, "rationale": "x"}})
        if adv is not None:
            adjudicate_role("adversary", p.stem, p, run_id="ra", root=root,
                            injected={pid: {"veto": (adv == "veto"), "findings": [],
                                            "tripwire_predictions": [], "rationale": "x"}})
        return pid, p

    def test_t0_orchestrator_only(self):
        from engine.metabolism.adjudicate import resolve_two_key
        root = _tmp_root()
        pid, p = self._setup(root, "T0", orch_grant=True)   # no adversary
        out = resolve_two_key(p.stem, p, root=root)
        assert out[pid]["authorized"] is True
        # deny path
        pid2, p2 = self._setup(root, "T0", orch_grant=False)
        assert resolve_two_key(p2.stem, p2, root=root)[pid2]["authorized"] is False

    def test_t1_needs_both_keys(self):
        from engine.metabolism.adjudicate import resolve_two_key
        root = _tmp_root()
        # grant + non-veto → authorized
        pid, p = self._setup(root, "T1", orch_grant=True, adv="nonveto")
        assert resolve_two_key(p.stem, p, root=root)[pid]["authorized"] is True
        # grant + veto → denied
        pid2, p2 = self._setup(root, "T1", orch_grant=True, adv="veto")
        assert resolve_two_key(p2.stem, p2, root=root)[pid2]["authorized"] is False
        # grant + adversary absent → fail-closed denied
        pid3, p3 = self._setup(root, "T1", orch_grant=True, adv=None)
        r3 = resolve_two_key(p3.stem, p3, root=root)[pid3]
        assert r3["authorized"] is False and r3["keys"]["adversary"] == "absent"

    def test_t2_always_denied_operator_only(self):
        # T2 can never be autonomously authorized: build_docket forbids it, and even
        # a hand-crafted T2 docket is denied by the adjudication screen (R-AUT-4).
        from engine.metabolism.adjudicate import adjudicate_role, resolve_two_key
        from engine.metabolism.propose import write_docket, AUTHORITY_BLOCK
        root = _tmp_root()
        pid = "deadbeef0001"
        hand = {
            "schema": "metabolism.docket.v1", "cycle_id": "cyc-t2", "lobe": "til",
            "authority": AUTHORITY_BLOCK,
            "proposals": [{
                "proposal_id": pid, "content_hash": pid,
                "title": "Promote skew signal to the scored path", "tier": "T2",
                "kind": "engine", "targets_sensor": "x", "rationale": "",
                "fitness_contract": {"sensor": "x", "expected_sign": "+", "band": "",
                                     "check_by": "2026-10-15", "placebo_to_beat": "",
                                     "falsifier_spec": {}, "asof": "2026-07-09",
                                     "proposal_id": pid},
            }],
        }
        p = write_docket(hand, root=root)
        # Even with an LLM grant + non-veto, the screen denies the T2 proposal.
        adjudicate_role("orchestrator", "cyc-t2", p, run_id="ro", root=root,
                        injected={pid: {"grant": True, "rationale": "x"}})
        adjudicate_role("adversary", "cyc-t2", p, run_id="ra", root=root,
                        injected={pid: {"veto": False, "findings": [],
                                        "tripwire_predictions": [], "rationale": "x"}})
        out = resolve_two_key("cyc-t2", p, root=root)[pid]
        assert out["authorized"] is False
        assert out["keys"]["orchestrator"] == "deny"

    def test_resolution_row_written(self):
        from engine.metabolism.adjudicate import resolve_two_key
        from engine.neuralweb.governance import load_events
        root = _tmp_root()
        pid, p = self._setup(root, "T0", orch_grant=True)
        resolve_two_key(p.stem, p, root=root)
        rows = [e for e in load_events(root=root, event_type="metabolism_adjudication")
                if (e.get("after") or {}).get("role") == "two_key"]
        assert len(rows) == 1 and rows[0]["after"]["authorized"] is True


# ===========================================================================
# Misc — vocabulary + adjudicate CLI inertness
# ===========================================================================

class TestMisc:

    def test_governance_vocab_has_new_types(self):
        from engine.neuralweb.governance import _VALID_EVENT_TYPES
        assert "metabolism_adjudication" in _VALID_EVENT_TYPES
        assert "metabolism_adversary_review" in _VALID_EVENT_TYPES

    def test_adjudicate_cli_paused_is_noop(self, monkeypatch):
        monkeypatch.delenv("AUTONOMY_PAUSED", raising=False)
        from scripts.metabolism_adjudicate import main
        from scripts.metabolism_journal import load_journal

        # DISCRIMINATING GUARD (post-review): booby-trap preflight so a removed/
        # reordered pause gate ERRORS instead of silently sharing the
        # noop_paused terminal status with the preflight-fail path.
        import scripts.preflight_claude_auth as _pf

        def _boom(*a, **k):
            raise AssertionError("check_auth reached while AUTONOMY_PAUSED — pause gate bypassed")
        monkeypatch.setattr(_pf, "check_auth", _boom)

        root = _tmp_root()
        p = _docket_on_disk(root, "cyc-cli", [_sample_proposal()])
        rc = main(["--cycle-id", "cyc-cli", "--role", "orchestrator",
                   "--docket-file", str(p), "--root", str(root)])
        assert rc == 0
        j = load_journal("cyc-cli", root=root)
        stage = j["stages"]["adjudicate_orchestrator"]
        assert stage["status"] == "noop_paused"
        assert "preflight" not in (stage.get("note") or "").lower()  # pause-specific
        # no governance rows written while paused
        assert not (root / "data" / "neuralweb" / "governance.jsonl").exists()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))


# ===========================================================================
# R-AUT-6 — two keys must come from DISTINCT run_ids (post-review hardening)
# ===========================================================================

class TestRunIdDistinctness:
    """A T1 must NOT authorize when the orchestrator and adversary rows carry
    the SAME run_id (one run playing both keys defeats the second key)."""

    def _plant_and_resolve(self, root, same_run: bool):
        import engine.metabolism.adjudicate as adj
        cycle_id = "cyc-runid"
        prop = dict(_sample_proposal(title="Add a T1 engine leg for run-id distinctness", kind="engine"))
        prop["tier"] = "T1"
        docket_p = _docket_on_disk(root, cycle_id, [prop])
        # build_docket derives the proposal_id (content-hash) — read the real one.
        d = json.loads(Path(docket_p).read_text())
        pid = d["proposals"][0]["proposal_id"]
        target = adj._target(cycle_id, pid)
        orch_run = "run-A"
        adv_run = "run-A" if same_run else "run-B"
        adj._append_governance(
            adj.EVT_ADJUDICATION, target, authored_by="test:orch",
            after={"role": adj.ROLE_ORCH, "decision": "grant", "run_id": orch_run},
            evidence=None, note="test orch grant", root=root)
        adj._append_governance(
            adj.EVT_ADVERSARY, target, authored_by="test:adv",
            after={"role": adj.ROLE_ADV, "veto": False, "run_id": adv_run},
            evidence=None, note="test adv non-veto", root=root)
        res = adj.resolve_two_key(cycle_id, docket_p, root=root, dry_run=True)
        return res[pid]

    def test_same_run_id_denies_t1(self, tmp_path):
        r = self._plant_and_resolve(tmp_path, same_run=True)
        assert r["authorized"] is False, "same run_id on both keys must DENY a T1"
        assert r["keys"].get("distinct_runs") is False

    def test_distinct_run_ids_authorize_t1(self, tmp_path):
        r = self._plant_and_resolve(tmp_path, same_run=False)
        assert r["authorized"] is True, "distinct run_ids + grant + non-veto must AUTHORIZE"
        assert r["keys"].get("distinct_runs") is True


class TestOpenLanesScoping:
    """The in-flight collision screen matches OPEN lanes only (2026-07-11 shadow
    finding): matching the whole ACTIVE_BUILD_MAP — which embeds ~500 merged-PR
    titles — let common engineering words satisfy the majority-token quorum and
    rejected essentially every proposal, which would paralyze armed PROPOSE."""

    _ABM = (
        "# Active Build Map\n\n"
        "## Open PRs\n\n"
        "| PR | Title |\n|----|-------|\n"
        "| #1 | feat(flow-leaders): unique openlane widget assembly |\n\n"
        "## Recently Merged (last 14 days)\n\n"
        "| PR | Title |\n|----|-------|\n"
        "| #2 | probe alpha plumbing check panel board signal tests fixes |\n"
    )

    def test_open_lanes_only_slices_open_section(self):
        from engine.metabolism.propose import _open_lanes_only
        sliced = _open_lanes_only(self._ABM)
        assert "openlane widget assembly" in sliced
        assert "Recently Merged" not in sliced
        assert "probe alpha plumbing" not in sliced

    def test_open_lanes_only_fail_closed_without_heading(self):
        from engine.metabolism.propose import _open_lanes_only
        text = "no headings here probe alpha plumbing check"
        assert _open_lanes_only(text) == text  # full text retained (over-rejects)

    def test_merged_title_tokens_do_not_reject(self, tmp_path):
        from engine.metabolism.propose import build_docket
        root = tmp_path
        (root / "docs").mkdir(parents=True, exist_ok=True)
        (root / "docs" / "ACTIVE_BUILD_MAP.md").write_text(self._ABM, encoding="utf-8")
        prop = {
            "title": "probe alpha plumbing check",
            "tier": "T0", "kind": "test", "targets_sensor": "front_run_lead",
            "rationale": "tokens exist ONLY in the merged section",
            "fitness_contract": {"sensor": "front_run_lead", "expected_sign": "+",
                                 "band": "accruing", "check_by": "2026-10-15",
                                 "placebo_to_beat": "shadow placebo tape"},
        }
        d = build_docket("cycle-openlane-a", [prop], root=root, max_docket_size=5)
        assert len(d["proposals"]) == 1, f"merged-only tokens must not reject: {d['rejected']}"

    def test_open_lane_title_tokens_still_reject(self, tmp_path):
        from engine.metabolism.propose import build_docket
        root = tmp_path
        (root / "docs").mkdir(parents=True, exist_ok=True)
        (root / "docs" / "ACTIVE_BUILD_MAP.md").write_text(self._ABM, encoding="utf-8")
        prop = {
            "title": "unique openlane widget assembly",
            "tier": "T0", "kind": "test", "targets_sensor": "front_run_lead",
            "rationale": "collides with the open-PR lane",
            "fitness_contract": {"sensor": "front_run_lead", "expected_sign": "+",
                                 "band": "accruing", "check_by": "2026-10-15",
                                 "placebo_to_beat": "shadow placebo tape"},
        }
        d = build_docket("cycle-openlane-b", [prop], root=root, max_docket_size=5)
        assert len(d["proposals"]) == 0
        assert "ACTIVE_BUILD_MAP" in d["rejected"][0]["reason"]

    def test_adjudicate_screen_scopes_abm_to_open_lanes(self, tmp_path):
        """adjudicate._load_case_law must carry the same open-lanes scoping as
        propose (both copies of the screen had the whole-file defect)."""
        from engine.metabolism import adjudicate as adj
        (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
        (tmp_path / "research").mkdir(parents=True, exist_ok=True)
        (tmp_path / "research" / "DO_NOT_REBUILD.md").write_text("# empty\n")
        (tmp_path / "docs" / "ACTIVE_BUILD_MAP.md").write_text(
            "# Active Build Map\n\n## Open PRs\n\n| #1 | unique openlane widget assembly |\n\n"
            "## Recently Merged (last 14 days)\n\n| #2 | probe alpha plumbing check |\n"
        )
        cl = adj._load_case_law(tmp_path)
        assert "openlane" in cl["active"]
        assert "plumbing" not in cl["active"], "merged-PR titles must not enter the screen corpus"


# ===========================================================================
# BUG 1 regression — lobe threading into contract and proposal dict
# ===========================================================================

class TestLobeThreading:
    """Regression: _mint_contract and build_docket must carry lobe into every proposal/contract."""

    def test_contract_carries_lobe_from_docket(self):
        """The fitness_contract['lobe'] must equal the docket-level lobe (BUG 1 fix)."""
        from engine.metabolism.propose import build_docket
        root = _tmp_root()
        d = build_docket("cycle-lobe-t1", [_sample_proposal()], root=root,
                         max_docket_size=5, lobe="til")
        assert len(d["proposals"]) == 1
        proposal = d["proposals"][0]
        # Proposal dict must carry lobe
        assert proposal.get("lobe") == "til", (
            f"proposal dict missing lobe; got {proposal.get('lobe')!r}"
        )
        # fitness_contract must also carry lobe
        fc = proposal["fitness_contract"]
        assert fc.get("lobe") == "til", (
            f"fitness_contract missing lobe; got {fc.get('lobe')!r}"
        )

    def test_contract_lobe_reaches_strategic_memory(self):
        """End-to-end: contract from build_docket → _append_strategic_memory_from_verify
        → build_strategic_memory_block(lobe=<that lobe>) must return the row.

        Exercises the full BUG 1 path without the shadow harness hardcode.
        """
        import tempfile, json  # noqa: PLC0415, E401
        from pathlib import Path  # noqa: PLC0415
        from engine.metabolism.propose import build_docket  # noqa: PLC0415
        from engine.metabolism.verify import _append_strategic_memory_from_verify  # noqa: PLC0415
        from engine.metabolism.mission import build_strategic_memory_block  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            lobe = "til"
            # Build a real docket (real propose path, not shadow)
            d = build_docket("cycle-lobe-e2e", [_sample_proposal()], root=root,
                             max_docket_size=5, lobe=lobe)
            contract = d["proposals"][0]["fitness_contract"]

            # Verify the contract carries the lobe
            assert contract.get("lobe") == lobe, (
                f"contract lobe missing after build_docket; got {contract.get('lobe')!r}"
            )

            # Simulate what verify does: append strategic memory from this contract
            fake_triage = {"classification": "overfit", "action": "revert_plan"}
            _append_strategic_memory_from_verify(
                cycle_id="cycle-lobe-e2e",
                contract=contract,
                triage=fake_triage,
                outcome="FALSIFIER_TRIPPED",
                root=root,
            )

            # Now build the strategic memory block filtering by lobe — must find the row
            block = build_strategic_memory_block(lobe=lobe, root=root, n_tail=20)
            assert "cycle-lobe-e2e" in block, (
                f"strategic memory block filtered out the row for lobe={lobe!r}. "
                f"Block was: {block!r}"
            )


# ===========================================================================
# R-V6-2 — applier stamps charter kind + carries fields
# ===========================================================================

def _sample_charter_item(
    domain_id="macro-credit",
    proposed_tier="display",
    proposed_lifecycle_state="proposed",
    extra=None,
):
    """Return a minimal charter_proposal.v1 dict as the scout would emit."""
    item = {
        "schema": "metabolism.charter_proposal.v1",
        "domain_id": domain_id,
        "label": "Macro Credit",
        "description": "Macro credit spreads intelligence",
        "proposed_tier": proposed_tier,
        "proposed_lifecycle_state": proposed_lifecycle_state,
        "uncovered_for_cycles": 4,
        "evidence_refs": ["insight-abc"],
        "roster_budget": {"current_active": 10, "max_active": 66},
        "rationale": f"Domain {domain_id} uncovered for 4 cycles",
        "generated_by": "metabolism_scout",
    }
    if extra:
        item.update(extra)
    return item


class TestApplierCharterKind:
    """R-V6-2: applier stamps kind='charter' and carries charter fields."""

    def test_charter_item_gets_charter_kind(self, tmp_path):
        from engine.metabolism.applier import _item_to_proposal
        item = _sample_charter_item()
        proposal = _item_to_proposal(item)
        assert proposal is not None
        assert proposal["kind"] == "charter", f"expected kind='charter', got {proposal['kind']!r}"

    def test_charter_fields_carried(self, tmp_path):
        from engine.metabolism.applier import _item_to_proposal
        item = _sample_charter_item(domain_id="fixed-income")
        proposal = _item_to_proposal(item)
        assert proposal is not None
        assert proposal["domain_id"] == "fixed-income"
        assert proposal["proposed_tier"] == "display"
        assert proposal["proposed_lifecycle_state"] == "proposed"
        assert proposal["uncovered_for_cycles"] == 4
        assert proposal["evidence_refs"] == ["insight-abc"]

    def test_lifecycle_docket_item_is_not_charter(self, tmp_path):
        from engine.metabolism.applier import _item_to_proposal
        item = {
            "schema": "metabolism.lifecycle_docket.v1",
            "lobe_id": "til",
            "from_state": "active",
            "to_state": "probation",
            "description": "TIL health degraded",
            "kind": "engine",
        }
        proposal = _item_to_proposal(item)
        assert proposal is not None
        assert proposal["kind"] != "charter", "lifecycle docket items must not get charter kind"

    def test_charter_liveness_sensor_defaulted(self, tmp_path):
        """Charter proposals without an explicit fitness_contract get liveness sensor."""
        from engine.metabolism.applier import _item_to_proposal
        item = _sample_charter_item()
        assert "fitness_contract" not in item
        proposal = _item_to_proposal(item)
        assert proposal is not None
        assert proposal["targets_sensor"] == "liveness"
        assert proposal["fitness_contract"]["contract_source"] == "applier_default_charter_liveness"

    def test_consume_charter_proposals_emits_charter_kind(self, tmp_path):
        """consume_charter_proposals() returns charter-kind proposal in shadow mode."""
        from engine.metabolism.applier import consume_charter_proposals
        cp_dir = tmp_path / "data" / "metabolism" / "charter_proposals"
        cp_dir.mkdir(parents=True, exist_ok=True)
        (cp_dir / "macro_credit.json").write_text(
            json.dumps(_sample_charter_item()), encoding="utf-8"
        )
        # shadow mode (dry_run=True) — no injection, but verifies _item_to_proposal runs
        result = consume_charter_proposals(root=tmp_path, dry_run=True)
        assert result == []  # shadow → not injected
        # armed mode
        result_armed = consume_charter_proposals(root=tmp_path, dry_run=False, armed=True)
        assert len(result_armed) == 1
        assert result_armed[0]["kind"] == "charter"


# ===========================================================================
# R-V6-2 — propose.py kind vocabulary contains "charter"
# ===========================================================================

class TestProposeKindVocabulary:

    def test_system_prompt_contains_charter_kind(self):
        import engine.metabolism.propose as propose
        # The template string must include "charter" in the kind vocabulary
        template = propose._SYSTEM_PROMPT_TEMPLATE
        assert '"charter"' in template or "'charter'" in template or "charter" in template, (
            "propose._SYSTEM_PROMPT_TEMPLATE does not mention charter kind"
        )

    def test_system_prompt_has_charter_guidance(self):
        import engine.metabolism.propose as propose
        template = propose._SYSTEM_PROMPT_TEMPLATE
        assert "scout" in template.lower() or "genesis" in template.lower(), (
            "propose._SYSTEM_PROMPT_TEMPLATE has no charter guidance text"
        )


# ===========================================================================
# R-V6-3 — genesis deterministic screen
# ===========================================================================

def _make_minimal_budget_yml(tmp_path: Path, max_active: int = 66,
                             max_probation: int = 5) -> None:
    """Write a minimal metabolism_budget.yml for genesis screen tests."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    content = (
        "schema: metabolism_budget.v1\n"
        f"max_active_nonscored_lobes: {max_active}\n"
        f"max_probation_lobes: {max_probation}\n"
        "genesis_accountability_days: 45\n"
    )
    (config_dir / "metabolism_budget.yml").write_text(content, encoding="utf-8")


def _make_lobe_charters(tmp_path: Path, n_active: int = 0, n_probation: int = 0) -> None:
    """Write lobe_charters.yml with n_active active + n_probation probation lobes."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    charters = {}
    for i in range(n_active):
        charters[f"lobe_{i:03d}"] = {
            "lobe_id": f"lobe_{i:03d}",
            "tier": "display",
            "lifecycle_state": "active",
        }
    for i in range(n_probation):
        charters[f"newborn_{i:03d}"] = {
            "lobe_id": f"newborn_{i:03d}",
            "tier": "display",
            "lifecycle_state": "probation",
        }
    data = {
        "schema": "lobe_charters.v1",
        "charters": charters,
    }
    try:
        import yaml
        (config_dir / "lobe_charters.yml").write_text(
            yaml.dump(data, default_flow_style=False), encoding="utf-8"
        )
    except ImportError:
        (config_dir / "lobe_charters.yml").write_text(
            json.dumps(data), encoding="utf-8"
        )


def _charter_proposal_dict(
    proposed_tier="display",
    proposed_lifecycle_state="proposed",
    title="New macro credit lobe",
    domain_id="macro-credit",
    rationale="uncovered domain needs a lobe",
):
    """Return a minimal charter proposal suitable for _genesis_screen input."""
    return {
        "kind": "charter",
        "title": title,
        "tier": "T0",
        "rationale": rationale,
        "proposed_tier": proposed_tier,
        "proposed_lifecycle_state": proposed_lifecycle_state,
        "domain_id": domain_id,
    }


def _empty_docket() -> dict:
    return {"proposals": []}


def _docket_with_demotion(lobe_id: str = "lobe_000") -> dict:
    """A docket with a co-pending demotion proposal targeting lobe_id.

    Default is 'lobe_000' which matches what _make_lobe_charters(n_active=N) creates.
    The lobe_id must appear in the title for _count_valid_swaps to find a valid swap
    (FIX M1: swap must target a named active lobe in lobe_charters.yml).
    """
    return {
        "proposals": [
            {
                "proposal_id": "demote-123",
                "kind": "lifecycle",
                "title": f"demote {lobe_id} from active to probation",
                "tier": "T0",
                "rationale": "health degraded",
            }
        ]
    }


class TestGenesisScreen:
    """R-V6-3: genesis deterministic screen correctness."""

    # (d) Triple tier fence

    def test_tier_fence_denies_non_display(self):
        from engine.metabolism.adjudicate import _genesis_screen
        prop = _charter_proposal_dict(proposed_tier="shadow", proposed_lifecycle_state="proposed")
        r = _genesis_screen(prop, cycle_id="c1", docket=_empty_docket(), root=None)
        assert r["allow"] is False
        assert "tier fence" in r["reason"]

    def test_tier_fence_denies_wrong_lifecycle_state(self):
        from engine.metabolism.adjudicate import _genesis_screen
        prop = _charter_proposal_dict(proposed_tier="display", proposed_lifecycle_state="confirmer")
        r = _genesis_screen(prop, cycle_id="c1", docket=_empty_docket(), root=None)
        assert r["allow"] is False
        assert "tier fence" in r["reason"]

    def test_tier_fence_allows_display_proposed(self, tmp_path):
        """display + proposed passes the tier fence (other screens may still deny)."""
        from engine.metabolism.adjudicate import _genesis_screen
        _make_minimal_budget_yml(tmp_path, max_active=66)
        _make_lobe_charters(tmp_path, n_active=0)
        prop = _charter_proposal_dict()
        r = _genesis_screen(prop, cycle_id="c1", docket=_empty_docket(), root=tmp_path)
        assert r["allow"] is True, f"Expected allow=True for clean charter; got: {r['reason']}"

    # (a) Roster cap

    def test_cap_deny_when_at_max(self, tmp_path):
        """R-V6-3a: deny when active_nonscored_count >= cap."""
        _make_minimal_budget_yml(tmp_path, max_active=3)
        _make_lobe_charters(tmp_path, n_active=3)  # exactly at cap
        from engine.metabolism.adjudicate import _genesis_screen
        prop = _charter_proposal_dict()
        r = _genesis_screen(prop, cycle_id="c1", docket=_empty_docket(), root=tmp_path)
        assert r["allow"] is False
        assert "roster cap" in r["reason"]
        assert "R-V6-3a" in r["reason"]

    def test_cap_deny_above_max(self, tmp_path):
        """Cap deny also fires when above max (regression guard)."""
        _make_minimal_budget_yml(tmp_path, max_active=3)
        _make_lobe_charters(tmp_path, n_active=5)
        from engine.metabolism.adjudicate import _genesis_screen
        prop = _charter_proposal_dict()
        r = _genesis_screen(prop, cycle_id="c1", docket=_empty_docket(), root=tmp_path)
        assert r["allow"] is False
        assert "roster cap" in r["reason"]

    def test_cap_allow_with_copending_demotion(self, tmp_path):
        """R-V6-3a swap: allow when cap is full but a demotion is co-pending."""
        _make_minimal_budget_yml(tmp_path, max_active=3)
        _make_lobe_charters(tmp_path, n_active=3)
        from engine.metabolism.adjudicate import _genesis_screen
        prop = _charter_proposal_dict()
        r = _genesis_screen(
            prop, cycle_id="c1", docket=_docket_with_demotion(), root=tmp_path
        )
        # The demotion swap means cap is not a blocker — other checks must pass too
        # (rate-limit check: no prior grants, passes; CHF: no token match, passes)
        assert r["allow"] is True, f"Expected allow=True with swap; got: {r['reason']}"

    def test_cap_below_max_allows(self, tmp_path):
        """Allow when well below the cap."""
        _make_minimal_budget_yml(tmp_path, max_active=66)
        _make_lobe_charters(tmp_path, n_active=10)
        from engine.metabolism.adjudicate import _genesis_screen
        prop = _charter_proposal_dict()
        r = _genesis_screen(prop, cycle_id="c1", docket=_empty_docket(), root=tmp_path)
        assert r["allow"] is True, f"Expected allow=True; got: {r['reason']}"

    # (b) Probation capacity (R-V6-3b REVISED: quality + capacity, never a count)

    def test_probation_slots_full_denies(self, tmp_path):
        """R-V6-3b: deny when unproven newborns already fill max_probation_lobes."""
        _make_minimal_budget_yml(tmp_path, max_active=66, max_probation=2)
        _make_lobe_charters(tmp_path, n_active=0, n_probation=2)
        from engine.metabolism.adjudicate import _genesis_screen
        prop = _charter_proposal_dict()
        r = _genesis_screen(prop, cycle_id="cyc-slots", docket=_empty_docket(), root=tmp_path)
        assert r["allow"] is False
        assert "probation slots full" in r["reason"]
        assert "R-V6-3b" in r["reason"]

    def test_same_cycle_grants_consume_slots(self, tmp_path):
        """Grants earlier in THIS cycle consume probation slots immediately —
        two charters in one cycle both pass ONLY while slots remain."""
        _make_minimal_budget_yml(tmp_path, max_active=66, max_probation=2)
        _make_lobe_charters(tmp_path, n_active=0, n_probation=1)
        (tmp_path / "data" / "neuralweb").mkdir(parents=True, exist_ok=True)
        gov_row = {
            "event_type": "metabolism_adjudication",
            "target": "metabolism_proposal:cyc-multi:pid-first",
            "after": {
                "role": "orchestrator",
                "decision": "grant",
                "kind": "charter",
                "tier": "T0",
            },
            "note": "orchestrator grant for T0 charter proposal",
        }
        gov_path = tmp_path / "data" / "neuralweb" / "governance.jsonl"
        gov_path.write_text(json.dumps(gov_row) + "\n", encoding="utf-8")
        from engine.metabolism.adjudicate import _genesis_screen
        prop = _charter_proposal_dict()
        # 1 probation + 1 grant this cycle >= 2 slots → deny
        r = _genesis_screen(prop, cycle_id="cyc-multi", docket=_empty_docket(), root=tmp_path)
        assert r["allow"] is False
        assert "probation slots full" in r["reason"]

    def test_multiple_charters_allowed_when_capacity(self, tmp_path):
        """NO per-cycle count cap: with open slots, a second charter in the
        same cycle passes (operator directive 2026-07-12 — quality-gated,
        not count-throttled)."""
        _make_minimal_budget_yml(tmp_path, max_active=66, max_probation=5)
        _make_lobe_charters(tmp_path, n_active=0, n_probation=1)
        (tmp_path / "data" / "neuralweb").mkdir(parents=True, exist_ok=True)
        gov_row = {
            "event_type": "metabolism_adjudication",
            "target": "metabolism_proposal:cyc-cap:pid-first",
            "after": {"role": "orchestrator", "decision": "grant",
                      "kind": "charter", "tier": "T0"},
            "note": "orchestrator grant for T0 charter proposal",
        }
        (tmp_path / "data" / "neuralweb" / "governance.jsonl").write_text(
            json.dumps(gov_row) + "\n", encoding="utf-8")
        from engine.metabolism.adjudicate import _genesis_screen
        prop = _charter_proposal_dict()
        # 1 probation + 1 grant = 2 < 5 slots → allow
        r = _genesis_screen(prop, cycle_id="cyc-cap", docket=_empty_docket(), root=tmp_path)
        assert r["allow"] is True, f"Expected allow with open slots; got: {r['reason']}"

    def test_unreadable_charters_fails_closed(self, tmp_path):
        """An unreadable roster must never admit a newborn."""
        _make_minimal_budget_yml(tmp_path, max_active=66, max_probation=5)
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "lobe_charters.yml").write_text("{{{not yaml", encoding="utf-8")
        from engine.metabolism.adjudicate import _genesis_screen
        prop = _charter_proposal_dict()
        r = _genesis_screen(prop, cycle_id="cyc-bad", docket=_empty_docket(), root=tmp_path)
        assert r["allow"] is False

    # (c) CHF-family deferral

    def test_chf_token_deny_before_deadline(self, tmp_path):
        """R-V6-3c: deny CHF-family token match when today < 2026-10-15."""
        _make_minimal_budget_yml(tmp_path, max_active=66)
        _make_lobe_charters(tmp_path, n_active=0)
        from engine.metabolism.adjudicate import _genesis_screen
        for token in ("causal", "chf", "hypothesis-factory", "machine-registration"):
            prop = _charter_proposal_dict(
                title=f"New {token} lobe for neural web",
                domain_id=token,
            )
            r = _genesis_screen(
                prop, cycle_id="c1", docket=_empty_docket(), root=tmp_path,
                _today_override="2026-09-01",
            )
            assert r["allow"] is False, (
                f"CHF token {token!r} should be denied before 2026-10-15; got allow=True"
            )
            assert "CHF" in r["reason"] or "chf" in r["reason"].lower() or token in r["reason"]
            assert "R-V6-3c" in r["reason"]

    def test_chf_token_always_denies_no_auto_lift(self, tmp_path):
        """R-V6-3c REVISED (TASK 5 m1): CHF deferral is unconditional — NO auto-lift.

        DO_NOT_REBUILD §4 says the 2026-10-15 clock is a PRECONDITION needing
        ≥8 matured candidates + fresh operator ruling, not an automatic lift.
        A CHF charter must be denied on/after 2026-10-15 just as before it.
        """
        _make_minimal_budget_yml(tmp_path, max_active=66)
        _make_lobe_charters(tmp_path, n_active=0)
        from engine.metabolism.adjudicate import _genesis_screen
        # Deny before, on, and after the old deadline date
        for today_str in ("2026-09-01", "2026-10-15", "2027-01-01"):
            prop = _charter_proposal_dict(title="New causal lobe", domain_id="causal")
            r = _genesis_screen(
                prop, cycle_id="c1", docket=_empty_docket(), root=tmp_path,
                _today_override=today_str,
            )
            assert r["allow"] is False, (
                f"CHF charter must be denied unconditionally (no auto-lift); "
                f"got allow=True for today={today_str!r}: {r['reason']}"
            )
            assert "R-V6-3c" in r["reason"]

    def test_non_chf_charter_allowed(self, tmp_path):
        """A clean, non-CHF charter proposal passes all genesis screens."""
        _make_minimal_budget_yml(tmp_path, max_active=66)
        _make_lobe_charters(tmp_path, n_active=0)
        from engine.metabolism.adjudicate import _genesis_screen
        prop = _charter_proposal_dict(
            title="New macro credit spread intelligence lobe",
            domain_id="macro-credit",
        )
        r = _genesis_screen(
            prop, cycle_id="c1", docket=_empty_docket(), root=tmp_path,
            _today_override="2026-09-01",
        )
        assert r["allow"] is True, f"Expected clean charter to pass; got: {r['reason']}"


# ===========================================================================
# R-V6-3 — genesis screen integration with adjudicate_role
# ===========================================================================

class TestGenesisScreenIntegration:
    """Charter-kind proposals go through the genesis screen in adjudicate_role."""

    def _write_minimal_infra(self, root: Path, max_active: int = 66) -> None:
        _make_minimal_budget_yml(root, max_active=max_active)
        _make_lobe_charters(root, n_active=0)
        # Required dirs for adjudicate_role
        for sub in ("data/metabolism/journal", "data/metabolism/fitness",
                    "data/metabolism/dockets", "data/neuralweb", "config", "docs", "research"):
            (root / sub).mkdir(parents=True, exist_ok=True)

    def _make_charter_docket(self, root: Path, cycle_id: str,
                              title="New macro credit lobe",
                              proposed_tier="display",
                              proposed_lifecycle_state="proposed"):
        """Write a docket with a single charter proposal."""
        from engine.metabolism.propose import write_docket, AUTHORITY_BLOCK
        import hashlib
        pid = hashlib.sha256(title.encode()).hexdigest()[:16]
        docket = {
            "schema": "metabolism.docket.v1",
            "cycle_id": cycle_id,
            "lobe": "til",
            "authority": AUTHORITY_BLOCK,
            "proposals": [{
                "proposal_id": pid,
                "content_hash": pid,
                "title": title,
                "tier": "T0",
                "kind": "charter",
                "targets_sensor": "liveness",
                "rationale": "uncovered domain for 4 cycles",
                "proposed_tier": proposed_tier,
                "proposed_lifecycle_state": proposed_lifecycle_state,
                "domain_id": "macro-credit",
                "fitness_contract": {
                    "sensor": "liveness",
                    "expected_sign": "+",
                    "band": "unspecified",
                    "check_by": "2026-10-15",
                    "placebo_to_beat": "shadow placebo tape",
                },
            }],
        }
        p = write_docket(docket, root=root)
        return p, pid

    def test_clean_charter_passes_genesis_screen(self, tmp_path):
        """A well-formed charter proposal passes the genesis screen and can be granted."""
        from engine.metabolism.adjudicate import adjudicate_role
        self._write_minimal_infra(tmp_path)
        p, pid = self._make_charter_docket(tmp_path, "cyc-clean")
        injected = {pid: {"grant": True, "rationale": "genesis looks legitimate"}}
        res = adjudicate_role("orchestrator", "cyc-clean", p, run_id="r1",
                              root=tmp_path, injected=injected)
        assert len(res) == 1
        result = res[0]
        assert result["decision"] == "grant", (
            f"Expected grant for clean charter; got deny. screen_allow={result.get('screen_allow')} "
            f"reason not available in result dict directly"
        )

    def test_tier_fence_deny_in_adjudicate_role(self, tmp_path):
        """Wrong tier/lifecycle in charter proposal is denied by genesis screen."""
        from engine.metabolism.adjudicate import adjudicate_role
        self._write_minimal_infra(tmp_path)
        p, pid = self._make_charter_docket(
            tmp_path, "cyc-tier",
            proposed_tier="shadow",  # wrong — must be 'display'
            proposed_lifecycle_state="proposed",
        )
        injected = {pid: {"grant": True, "rationale": "looks fine"}}
        res = adjudicate_role("orchestrator", "cyc-tier", p, run_id="r1",
                              root=tmp_path, injected=injected)
        assert res[0]["decision"] == "deny"
        assert res[0]["screen_allow"] is False

    def test_roster_cap_deny_in_adjudicate_role(self, tmp_path):
        """Roster cap exceeded → genesis screen denies the charter."""
        from engine.metabolism.adjudicate import adjudicate_role
        _make_minimal_budget_yml(tmp_path, max_active=2)
        _make_lobe_charters(tmp_path, n_active=2)  # at cap
        for sub in ("data/metabolism/journal", "data/metabolism/dockets",
                    "data/neuralweb", "docs", "research"):
            (tmp_path / sub).mkdir(parents=True, exist_ok=True)
        p, pid = self._make_charter_docket(tmp_path, "cyc-cap")
        injected = {pid: {"grant": True, "rationale": "new lobe"}}
        res = adjudicate_role("orchestrator", "cyc-cap", p, run_id="r1",
                              root=tmp_path, injected=injected)
        assert res[0]["decision"] == "deny"
        assert res[0]["screen_allow"] is False

    def test_non_charter_proposal_unaffected(self, tmp_path):
        """Non-charter proposals skip the genesis screen entirely."""
        from engine.metabolism.adjudicate import adjudicate_role
        self._write_minimal_infra(tmp_path)
        # Even with max_active=0 (everything at cap), a non-charter proposal passes
        # the genesis screen (it's not a charter kind)
        _make_minimal_budget_yml(tmp_path, max_active=0)  # would deny any charter
        _make_lobe_charters(tmp_path, n_active=100)
        p = _docket_on_disk(tmp_path, "cyc-nonchart", [_sample_proposal()])
        pid = json.loads(p.read_text())["proposals"][0]["proposal_id"]
        injected = {pid: {"grant": True, "rationale": "normal proposal"}}
        res = adjudicate_role("orchestrator", "cyc-nonchart", p, run_id="r1",
                              root=tmp_path, injected=injected)
        assert res[0]["decision"] == "grant"

    def test_governance_row_contains_kind_field(self, tmp_path):
        """Governance row written for a charter proposal carries kind='charter'."""
        from engine.metabolism.adjudicate import adjudicate_role
        from engine.neuralweb.governance import load_events
        self._write_minimal_infra(tmp_path)
        p, pid = self._make_charter_docket(tmp_path, "cyc-kind")
        injected = {pid: {"grant": True, "rationale": "ok"}}
        adjudicate_role("orchestrator", "cyc-kind", p, run_id="r1",
                        root=tmp_path, injected=injected)
        evs = load_events(root=tmp_path, event_type="metabolism_adjudication")
        orch_rows = [e for e in evs if (e.get("after") or {}).get("role") == "orchestrator"]
        assert orch_rows, "No orchestrator governance row written"
        assert (orch_rows[0].get("after") or {}).get("kind") == "charter"


# ===========================================================================
# R-V6-3e — adversary prompt contains charter case-law block
# ===========================================================================

class TestAdversaryChartercaseLaw:
    """R-V6-3e: adversary (and orchestrator) user prompt includes NARR-NWC + NEXT3-U5
    only when the docket contains charter-kind proposals."""

    def _make_charter_docket_dict(self, cycle_id="cyc-adv-charter"):
        import hashlib
        pid = hashlib.sha256(cycle_id.encode()).hexdigest()[:16]
        return {
            "schema": "metabolism.docket.v1",
            "cycle_id": cycle_id,
            "lobe": "til",
            "authority": {},
            "proposals": [{
                "proposal_id": pid,
                "kind": "charter",
                "title": "New macro credit lobe",
                "tier": "T0",
                "rationale": "uncovered domain",
            }],
        }

    def _make_engine_docket_dict(self, cycle_id="cyc-adv-engine"):
        import hashlib
        pid = hashlib.sha256(cycle_id.encode()).hexdigest()[:16]
        return {
            "schema": "metabolism.docket.v1",
            "cycle_id": cycle_id,
            "lobe": "til",
            "authority": {},
            "proposals": [{
                "proposal_id": pid,
                "kind": "engine",
                "title": "Add a new sensor collector",
                "tier": "T1",
                "rationale": "improve coverage",
            }],
        }

    def test_charter_docket_includes_caselaw_block(self):
        from engine.metabolism.adjudicate import _build_role_user, _CHARTER_CASE_LAW_BLOCK
        docket = self._make_charter_docket_dict()
        user = _build_role_user("adversary", docket, {"killed": "", "active": ""})
        assert "NARR-NWC" in user, "adversary prompt missing NARR-NWC for charter docket"
        assert "NEXT3-U5" in user, "adversary prompt missing NEXT3-U5 for charter docket"
        assert "Misfiling waves as lobes" in user, "adversary prompt missing sprawl-warning"
        assert "VETO" in user or "veto" in user.lower(), "adversary prompt missing veto instruction"

    def test_engine_docket_excludes_caselaw_block(self):
        from engine.metabolism.adjudicate import _build_role_user
        docket = self._make_engine_docket_dict()
        user = _build_role_user("adversary", docket, {"killed": "", "active": ""})
        assert "NARR-NWC" not in user, "non-charter docket should not include NARR-NWC"
        assert "NEXT3-U5" not in user, "non-charter docket should not include NEXT3-U5"

    def test_orchestrator_also_gets_caselaw_for_charter_docket(self):
        from engine.metabolism.adjudicate import _build_role_user
        docket = self._make_charter_docket_dict()
        user = _build_role_user("orchestrator", docket, {"killed": "", "active": ""})
        assert "NARR-NWC" in user


# ===========================================================================
# R-V6-3 — budget keys in metabolism_budget.yml
# ===========================================================================

class TestBudgetKeys:
    """Verify the new genesis budget keys are present and correctly typed."""

    def test_budget_has_no_per_cycle_genesis_cap(self, tmp_path):
        """R-V6-3b REVISED: genesis is capacity-gated (max_probation_lobes),
        never count-gated — the retired key must stay retired."""
        from engine.metabolism.adjudicate import _load_genesis_budget
        _make_minimal_budget_yml(tmp_path)
        budget = _load_genesis_budget(tmp_path)
        assert "max_genesis_per_cycle" not in budget
        assert int(budget["max_probation_lobes"]) == 5

    def test_budget_has_genesis_accountability_days(self, tmp_path):
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        content = (
            "schema: metabolism_budget.v1\n"
            "max_active_nonscored_lobes: 66\n"
            "max_probation_lobes: 5\n"
            "genesis_accountability_days: 45\n"
        )
        (config_dir / "metabolism_budget.yml").write_text(content, encoding="utf-8")
        from engine.metabolism.adjudicate import _load_genesis_budget
        budget = _load_genesis_budget(tmp_path)
        assert "genesis_accountability_days" in budget
        assert int(budget["genesis_accountability_days"]) == 45

    def test_real_budget_file_has_new_keys(self):
        """The actual committed config/metabolism_budget.yml contains the new keys."""
        import yaml
        root = Path(__file__).resolve().parent.parent
        path = root / "config" / "metabolism_budget.yml"
        assert path.exists(), "config/metabolism_budget.yml not found"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert "max_genesis_per_cycle" not in data, (
            "per-cycle genesis cap retired (R-V6-3b revised) — must stay retired"
        )
        assert "genesis_accountability_days" in data, (
            "config/metabolism_budget.yml missing genesis_accountability_days"
        )
        assert int(data["genesis_accountability_days"]) == 45
        assert int(data["max_probation_lobes"]) >= 1


# ===========================================================================
# FIX B1 — build_docket carries charter fields to _genesis_screen
# ===========================================================================

class TestBuildDocketCharterFieldCarry:
    """FIX B1: build_docket must pass charter fields (proposed_tier etc.) through
    so _genesis_screen's tier fence does not deny every charter unconditionally."""

    def test_charter_fields_survive_build_docket(self, tmp_path):
        """A charter-shaped proposal injected into build_docket must retain
        proposed_tier, proposed_lifecycle_state, domain_id, etc."""
        from engine.metabolism.propose import build_docket
        root = tmp_path
        (root / "config").mkdir(parents=True, exist_ok=True)
        (root / "docs").mkdir(parents=True, exist_ok=True)
        (root / "research").mkdir(parents=True, exist_ok=True)
        (root / "data" / "metabolism").mkdir(parents=True, exist_ok=True)

        charter_raw = {
            "title": "New macro credit intelligence lobe",
            "tier": "T0",
            "kind": "charter",
            "proposed_tier": "display",
            "proposed_lifecycle_state": "proposed",
            "domain_id": "macro-credit",
            "evidence_refs": ["insight-x"],
            "uncovered_for_cycles": 5,
            "roster_budget": {"current_active": 10, "max_active": 66},
            "targets_sensor": "liveness",
            "rationale": "macro credit domain uncovered",
            "fitness_contract": {
                "sensor": "liveness",
                "expected_sign": "+",
                "band": "unspecified",
                "check_by": "2026-10-15",
                "placebo_to_beat": "shadow placebo tape",
            },
        }
        d = build_docket("cycle-b1", [charter_raw], root=root, max_docket_size=5)
        assert len(d["proposals"]) == 1, f"Charter should pass validation; rejected: {d['rejected']}"
        proposal = d["proposals"][0]
        # Charter fields must survive the build_docket whitelist
        assert proposal.get("proposed_tier") == "display", (
            f"FIX B1: proposed_tier not carried; got {proposal.get('proposed_tier')!r}"
        )
        assert proposal.get("proposed_lifecycle_state") == "proposed", (
            f"FIX B1: proposed_lifecycle_state not carried; got {proposal.get('proposed_lifecycle_state')!r}"
        )
        assert proposal.get("domain_id") == "macro-credit"
        assert proposal.get("evidence_refs") == ["insight-x"]
        assert proposal.get("uncovered_for_cycles") == 5

    def test_charter_via_build_docket_passes_genesis_screen(self, tmp_path):
        """End-to-end B1 path: charter fields carried from build_docket reach
        _genesis_screen and the tier fence passes (not denied as missing tier)."""
        from engine.metabolism.propose import build_docket
        from engine.metabolism.adjudicate import _genesis_screen

        _make_minimal_budget_yml(tmp_path, max_active=66, max_probation=5)
        _make_lobe_charters(tmp_path, n_active=0, n_probation=0)
        (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
        (tmp_path / "research").mkdir(parents=True, exist_ok=True)
        (tmp_path / "data" / "metabolism").mkdir(parents=True, exist_ok=True)

        charter_raw = {
            "title": "New macro credit intelligence lobe for B1 path",
            "tier": "T0",
            "kind": "charter",
            "proposed_tier": "display",
            "proposed_lifecycle_state": "proposed",
            "domain_id": "macro-credit",
            "targets_sensor": "liveness",
            "rationale": "macro credit domain uncovered",
            "fitness_contract": {
                "sensor": "liveness",
                "expected_sign": "+",
                "band": "unspecified",
                "check_by": "2026-10-15",
                "placebo_to_beat": "shadow placebo tape",
            },
        }
        d = build_docket("cycle-b1-e2e", [charter_raw], root=tmp_path, max_docket_size=5)
        assert len(d["proposals"]) == 1, f"rejected: {d['rejected']}"
        proposal = d["proposals"][0]

        # The proposal with carried fields should pass _genesis_screen
        r = _genesis_screen(
            proposal, cycle_id="cycle-b1-e2e", docket=_empty_docket(), root=tmp_path
        )
        assert r["allow"] is True, (
            f"FIX B1: charter via build_docket should pass genesis screen; got: {r['reason']}"
        )


# ===========================================================================
# FIX M1 — _count_valid_swaps: swap-waiver exploit closed
# ===========================================================================

class TestValidSwaps:
    """FIX M1: _count_valid_swaps must reject invalid swap attempts."""

    def test_charter_own_demote_text_does_not_waive(self, tmp_path):
        """A charter whose own rationale says 'demote weak signals' must NOT
        waive the roster cap for itself (FIX M1 exploit closure)."""
        _make_minimal_budget_yml(tmp_path, max_active=2)
        _make_lobe_charters(tmp_path, n_active=2)  # at cap
        from engine.metabolism.adjudicate import _genesis_screen

        # Charter proposal with a rationale that mentions "demote" in its OWN text
        prop = _charter_proposal_dict(
            title="New intelligence lobe",
            rationale="we should demote weak signals before adding new ones",
        )
        # Docket is empty — the charter itself is the ONLY proposal
        # (the exploit: old code scanned ALL proposal text including the charter's own)
        r = _genesis_screen(prop, cycle_id="c1", docket=_empty_docket(), root=tmp_path)
        assert r["allow"] is False, (
            "FIX M1: charter's own 'demote' text must NOT waive the roster cap"
        )
        assert "roster cap" in r["reason"]

    def test_demotion_targeting_nonexistent_lobe_does_not_waive(self, tmp_path):
        """A demotion proposal naming a lobe that is NOT in lobe_charters.yml
        (or not active) must not count as a valid swap."""
        _make_minimal_budget_yml(tmp_path, max_active=2)
        _make_lobe_charters(tmp_path, n_active=2)  # active lobes: lobe_000, lobe_001
        from engine.metabolism.adjudicate import _genesis_screen

        # Docket has a demotion proposal targeting 'nonexistent_lobe' which isn't in charters
        nonexistent_demotion = {
            "proposals": [
                {
                    "proposal_id": "demote-ghost",
                    "kind": "lifecycle",
                    "title": "demote nonexistent_ghost_lobe from active",
                    "tier": "T0",
                    "rationale": "health degraded",
                }
            ]
        }
        prop = _charter_proposal_dict()
        r = _genesis_screen(prop, cycle_id="c1", docket=nonexistent_demotion, root=tmp_path)
        assert r["allow"] is False, (
            "FIX M1: demotion targeting nonexistent lobe must NOT waive the cap"
        )
        assert "roster cap" in r["reason"]

    def test_real_active_lobe_demotion_waives_one_slot(self, tmp_path):
        """A demotion targeting a REAL active lobe in lobe_charters.yml
        waives exactly one roster slot (valid swap for R-V6-3a)."""
        _make_minimal_budget_yml(tmp_path, max_active=2)
        _make_lobe_charters(tmp_path, n_active=2)  # active lobes: lobe_000, lobe_001
        from engine.metabolism.adjudicate import _genesis_screen

        # Demotion names lobe_000 which IS in charters with lifecycle_state='active'
        valid_demotion = {
            "proposals": [
                {
                    "proposal_id": "demote-lobe_000",
                    "kind": "lifecycle",
                    "title": "demote lobe_000 from active to probation",
                    "tier": "T0",
                    "rationale": "health degraded",
                }
            ]
        }
        prop = _charter_proposal_dict()
        r = _genesis_screen(prop, cycle_id="c1", docket=valid_demotion, root=tmp_path)
        assert r["allow"] is True, (
            f"FIX M1: valid active-lobe demotion must waive one slot; got: {r['reason']}"
        )

    def test_two_demotions_same_lobe_waive_only_one_slot(self, tmp_path):
        """#2339 re-review F1 vector 1: two demotion proposals naming the SAME
        active lobe must waive ONE slot, not two."""
        _make_minimal_budget_yml(tmp_path, max_active=2)
        _make_lobe_charters(tmp_path, n_active=2)  # lobe_000, lobe_001
        from engine.metabolism.adjudicate import _count_valid_swaps
        from engine.metabolism.lobe_registry import load as _load_registry
        charters = _load_registry(tmp_path)["charters"]
        docket = {"proposals": [
            {"proposal_id": "d1", "kind": "lifecycle",
             "title": "demote lobe_000 from active"},
            {"proposal_id": "d2", "kind": "lifecycle",
             "title": "retire lobe_000 entirely"},
        ]}
        n = _count_valid_swaps(docket, charters, _charter_proposal_dict())
        assert n == 1, f"two demotions of the same lobe must dedupe to 1 slot; got {n}"

    def test_one_demotion_does_not_waive_two_charters(self, tmp_path):
        """#2339 re-review F1 vector 2: at cap, one demotion + one already-granted
        charter this cycle must NOT admit a second charter (one freed slot, one
        charter already consuming it)."""
        _make_minimal_budget_yml(tmp_path, max_active=2)
        _make_lobe_charters(tmp_path, n_active=2)
        # A charter was already granted this cycle (consumes the freed slot)
        (tmp_path / "data" / "neuralweb").mkdir(parents=True, exist_ok=True)
        gov_row = {
            "event_type": "metabolism_adjudication",
            "target": "metabolism_proposal:c-swap:pid-first",
            "after": {"role": "orchestrator", "decision": "grant",
                      "kind": "charter", "tier": "T0"},
            "note": "orchestrator grant for T0 charter proposal",
        }
        (tmp_path / "data" / "neuralweb" / "governance.jsonl").write_text(
            json.dumps(gov_row) + "\n", encoding="utf-8")
        valid_demotion = {"proposals": [
            {"proposal_id": "demote-lobe_000", "kind": "lifecycle",
             "title": "demote lobe_000 from active to probation"},
        ]}
        from engine.metabolism.adjudicate import _genesis_screen
        # current_active(2) + grants(1) - swaps(1) = 2 >= max_active(2) → deny
        r = _genesis_screen(_charter_proposal_dict(), cycle_id="c-swap",
                            docket=valid_demotion, root=tmp_path)
        assert r["allow"] is False, (
            f"one demotion must not waive a second charter; got: {r.get('reason')}"
        )
        assert "roster cap" in r["reason"]

    def test_grants_counter_fails_closed_on_unreadable_governance(self, tmp_path, monkeypatch):
        """The charter-grant counter must fail CLOSED (inflate the sum → deny),
        since it is ADDED to the capacity gates."""
        from engine.metabolism import adjudicate as adj
        def boom(*a, **k):
            raise RuntimeError("governance log unreadable")
        monkeypatch.setattr(adj, "_events_for_target", boom)
        n = adj._count_charter_grants_this_cycle("c1", tmp_path)
        assert n >= 10_000, f"unreadable governance must fail closed (large sentinel); got {n}"


# ===========================================================================
# FIX M2 — roster cap fails closed on unreadable roster
# ===========================================================================

class TestRosterCapFailClosed:
    """FIX M2: the roster-cap path must deny when lobe_charters.yml is unreadable
    (independent of the probation-capacity fail-closed path tested elsewhere)."""

    def test_malformed_roster_denies_cap_path(self, tmp_path):
        """Malformed lobe_charters.yml → roster-cap path denies (FIX M2).

        active_nonscored_count returns 0 on load error (never raises), so without
        this fix the cap check would be 0 >= max_active = False → passes.
        The explicit readability check must catch this.
        """
        _make_minimal_budget_yml(tmp_path, max_active=66, max_probation=5)
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        # Write malformed YAML that triggers a parse error
        (config_dir / "lobe_charters.yml").write_text("charters: {{{malformed", encoding="utf-8")
        from engine.metabolism.adjudicate import _genesis_screen
        prop = _charter_proposal_dict()
        r = _genesis_screen(prop, cycle_id="cyc-m2", docket=_empty_docket(), root=tmp_path)
        assert r["allow"] is False, (
            "FIX M2: malformed lobe_charters.yml must deny via roster-cap path"
        )


# ===========================================================================
# TASK 5 m2 — CHF token set includes structure-learner constructs
# ===========================================================================

class TestCHFStructureLearnerTokens:
    """TASK 5 m2: _CHF_DENY_TOKENS extended with NOTEARS/DAG-GNN/LoRAM/CMIN etc."""

    def test_notears_discovery_lobe_denies(self, tmp_path):
        """DO_NOT_REBUILD §4 ~line 110: NOTEARS/DAG-GNN class lobes are killed."""
        _make_minimal_budget_yml(tmp_path, max_active=66, max_probation=5)
        _make_lobe_charters(tmp_path, n_active=0)
        from engine.metabolism.adjudicate import _genesis_screen
        prop = _charter_proposal_dict(
            title="NOTEARS discovery lobe for neural web",
            domain_id="structure-learning",
        )
        r = _genesis_screen(prop, cycle_id="c1", docket=_empty_docket(), root=tmp_path)
        assert r["allow"] is False, (
            "TASK 5 m2: NOTEARS discovery lobe must be denied (DO_NOT_REBUILD §4 ~110)"
        )
        assert "R-V6-3c" in r["reason"]

    def test_dag_gnn_denies(self, tmp_path):
        _make_minimal_budget_yml(tmp_path, max_active=66, max_probation=5)
        _make_lobe_charters(tmp_path, n_active=0)
        from engine.metabolism.adjudicate import _genesis_screen
        prop = _charter_proposal_dict(title="dag-gnn causal discovery lobe")
        r = _genesis_screen(prop, cycle_id="c1", docket=_empty_docket(), root=tmp_path)
        assert r["allow"] is False

    def test_structure_learner_phrase_denies(self, tmp_path):
        _make_minimal_budget_yml(tmp_path, max_active=66, max_probation=5)
        _make_lobe_charters(tmp_path, n_active=0)
        from engine.metabolism.adjudicate import _genesis_screen
        prop = _charter_proposal_dict(title="Structure learner for market microstructure")
        r = _genesis_screen(prop, cycle_id="c1", docket=_empty_docket(), root=tmp_path)
        assert r["allow"] is False
