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
