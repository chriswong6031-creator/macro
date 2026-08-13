"""Mutation / anti-vacuity suite for the Reference Integrity Gate checker.

Law: ``research/REFERENCE_INTEGRITY_GATE_V1.md``.  Guard:
``scripts/check_reference_integrity.py``.

Three suites:

A. **Mutation / anti-vacuity.**  A gate that cannot fail is not a gate.  Every test starts
   from a fully-VALID approved synthetic artifact set (which must pass), corrupts exactly
   one thing, and asserts the matching STABLE finding code fires.  The valid-set builder
   here is deliberately INDEPENDENT of the checker's own ``--selftest`` fixtures: a shared
   builder would let one wrong assumption make both agree, which is the vacuity this suite
   exists to prevent.

B. **Founding case.**  The real committed fixture
   ``research/reference_integrity/prophet-board-5514-original/`` — the original Prophet
   Board mockup frozen at ``668e5954`` (RIG §10).  The checker must independently derive
   the mechanically-derivable defects from the fixture's honest ledgers, and a
   ``TEN_REGRESSIONS`` map pins which code catches which of the ten recorded regressions.

   ``TestFoundingReceipts`` asserts the receipt/verdict invariants — the files produced by
   the two independent critics and the design authority.  Those assertions are written to
   the LAW, not to whatever the receipts happen to say: if a receipt lands that does not
   satisfy them, the receipt is wrong.  Never satisfy this class by writing or editing the
   receipts from the guard's own session — a receipt written by the party being reviewed is
   the exact laundering RIG §6 exists to stop.

C. **Output shape.**  Every annotation must START its line, or GitHub silently drops it
   (house annotation law).  Pins the defect class, not the wording.

Run: python -m pytest tests/test_check_reference_integrity.py -q
"""
from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Callable

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "check_reference_integrity.py"
FOUNDING_ID = "prophet-board-5514-original"
FOUNDING_DIR = ROOT / "research" / "reference_integrity" / FOUNDING_ID


def _load_module():
    spec = importlib.util.spec_from_file_location("check_reference_integrity_under_test", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # ``dataclasses`` resolves ``cls.__module__`` through ``sys.modules``; a file-loaded
    # module absent from it raises on the first ``@dataclass``.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RIG = _load_module()

VALID_SHA = "0" * 40


# ── Independent valid-set builder ─────────────────────────────────────────────

def valid_docs(reference_id: str = "synthetic-ref") -> dict[str, Any]:
    """A fully-valid APPROVED artifact set.  Written from the LAW, not from the checker."""
    return {
        "manifest.yml": {
            "schema": "mastermind.rig_manifest.v1",
            "reference_id": reference_id,
            "scope": "full",
            "status": "approved",
            "surface": {"route": "board.html", "registry_row": "board", "archetype": "discovery_board"},
            "author": {"identity": "designer-session-7", "role": "designer"},
            "reference_files": [
                {"path": f"mockups/design_system/{reference_id}.html", "frozen_sha": VALID_SHA},
            ],
            "files": {
                "baseline": "baseline.yml",
                "proposal": "proposal.yml",
                "reviews": {
                    "product_regression": "reviews/product_regression.yml",
                    "visual_taste": "reviews/visual_taste.yml",
                },
                "verdict": "verdict.yml",
                "approval": "approval.yml",
            },
        },
        "baseline.yml": {
            "schema": "mastermind.rig_baseline.v1",
            "reference_id": reference_id,
            "captured_at": "2026-08-12",
            "production": {"route": "board.html", "source_commit": VALID_SHA,
                           "source_paths": ["templates/board.html.j2"]},
            "evidence": {
                "screenshots": [
                    {"path": f"mockups/refs/reference_integrity/{reference_id}/prod-desktop-dark-en.png",
                     "viewport": "desktop", "theme": "dark", "locale": "en"},
                ],
                "gaps": [{"axis": "locale", "value": "zh", "reason": "surface is EN-only today"}],
            },
            "user_job": "decide which setups to work on today",
            "core_interactions": ["scan the grid", "read the live price"],
            "information_hierarchy": ["stance verb", "chart", "price"],
            "design_lineage": {"rulings": [], "rejected_variants": [], "comments": []},
            "capabilities": [
                {"id": "card.chart_hero", "user_job": "see price geometry at a glance",
                 "evidence": "templates/board.html.j2:10", "importance": "core"},
                {"id": "card.live_price", "user_job": "know where price is now",
                 "evidence": "templates/board.html.j2:20", "importance": "core"},
                {"id": "card.lane_chip", "user_job": "see which lane the name is in",
                 "evidence": "templates/board.html.j2:30", "importance": "supporting"},
                {"id": "card.footnote", "user_job": "read the small-print caveat",
                 "evidence": "templates/board.html.j2:40", "importance": "peripheral"},
            ],
        },
        "proposal.yml": {
            "schema": "mastermind.rig_proposal.v1",
            "reference_id": reference_id,
            "proposed_artifact": {
                "frozen_sha": VALID_SHA,
                "paths": [f"mockups/design_system/{reference_id}.html"],
            },
            "dispositions": [
                {"id": "card.chart_hero", "disposition": "BLOCKED_DATA",
                 "dependency": "candidate spark contract does not populate every plan row",
                 "escalation": "raised with the plan-data program as issue PD-114",
                 "interim": "the card reserves the slot and names the gap in place"},
                {"id": "card.live_price", "disposition": "RETAIN",
                 "target": "card head, right of the stance verb"},
                {"id": "card.lane_chip", "disposition": "RELOCATE",
                 "destination": "second row, left of the sector chip",
                 "reachability": "still rendered at rest; no hover or drill-down required"},
                {"id": "card.footnote", "disposition": "REMOVE",
                 "rationale": "the footnote restated the stance verb on every single card",
                 "user_job_impact": "the caveat is no longer legible without opening the name",
                 "superiority_case": "the stance verb already carries the caveat; the duplicate "
                                     "cost a full line on a glance-tier card",
                 "approval_ref": "verdict.yml blocking_findings PRC-001"},
            ],
            "additions": [{"id": "add.lane_filter", "what": "a lane filter above the grid"}],
            "user_tasks": [
                {"id": "task.glance_scan", "task": "shortlist actionable names in seconds",
                 "critical": True, "production": "verb hue + chart shape",
                 "proposal": "verb hue + chart shape, unchanged", "verdict": "EQUIVALENT"},
                {"id": "task.price_now", "task": "know where price is now", "critical": True,
                 "production": "live quote on card", "proposal": "live quote, larger",
                 "verdict": "BETTER"},
                {"id": "task.read_caveat", "task": "read the small-print caveat", "critical": False,
                 "production": "on the card", "proposal": "on the detail page", "verdict": "WORSE"},
            ],
            "authority_delta": [
                {"id": "auth.zone", "production_claim": "a relevant price range",
                 "proposal_claim": "the same relevant price range", "direction": "equal",
                 "warranted": True, "evidence": "copy unchanged"},
            ],
            "information_economics": {
                "words_per_card": {"production": "18 (card-zoom crop)", "proposal": "16 (crop 01)"},
                "findings": ["one duplicated line removed"],
                "preserved": ["the chart slot stays reserved rather than reflowed away"],
            },
        },
        "reviews/product_regression.yml": {
            "schema": "mastermind.rig_review.v1",
            "reference_id": reference_id,
            "role": "product_regression",
            "artifact_sha": VALID_SHA,
            "reviewer": {"identity": "critic-a-session", "model": "opus", "independent_of_author": True},
            "quarantine": {
                "first_pass_inputs": ["user job", "production artifact", "proposed artifact", "ledger"],
                "rationale_received_after_first_pass": True,
            },
            "first_pass": {
                "frozen_at": "2026-08-12T10:00:00Z",
                "verdict": "BLOCK",
                "findings": [
                    {"id": "PRC-001", "severity": "blocker", "capability": "card.footnote",
                     "finding": "the caveat disappears with no destination named"},
                    {"id": "PRC-002", "severity": "minor", "capability": "card.lane_chip",
                     "finding": "the lane chip is a row lower than production"},
                ],
                "strengths": ["the price row is genuinely clearer"],
            },
            "second_pass": {
                "amended_at": "2026-08-12T11:00:00Z",
                "verdict": "PASS_WITH_CONDITIONS",
                "amendments": [
                    {"finding": "PRC-001", "action": "upheld",
                     "note": "the rationale explains the duplication but not the loss"},
                    {"finding": "PRC-002", "action": "downgraded", "note": "cosmetic"},
                ],
            },
        },
        "reviews/visual_taste.yml": {
            "schema": "mastermind.rig_review.v1",
            "reference_id": reference_id,
            "role": "visual_taste",
            "artifact_sha": VALID_SHA,
            "reviewer": {"identity": "critic-b-session", "model": "opus", "independent_of_author": True},
            "quarantine": {
                "first_pass_inputs": ["user job", "production artifact", "proposed artifact", "ledger"],
                "rationale_received_after_first_pass": True,
            },
            "first_pass": {
                "frozen_at": "2026-08-12T10:00:00Z",
                "verdict": "PASS_WITH_CONDITIONS",
                "findings": [
                    {"id": "VTC-001", "severity": "minor", "finding": "the footnote read as noise"},
                ],
                "strengths": ["density improved without losing the hue system"],
            },
            "second_pass": {
                "amended_at": "2026-08-12T11:00:00Z",
                "verdict": "PASS",
                "amendments": [{"finding": "VTC-001", "action": "withdrawn", "note": "the removal is the cure"}],
            },
        },
        "verdict.yml": {
            "schema": "mastermind.rig_verdict.v1",
            "reference_id": reference_id,
            "authority": {"identity": "design-authority-main-loop", "role": "design_authority"},
            "packet": {
                "materially_improved": "the price row and the lane filter",
                "materially_worsened": "the caveat moved off the card",
                "disappeared": "the card footnote",
                "behavior_harder": "reading the caveat now needs one click",
                "stronger_claims": "none — the zone wording is unchanged",
                "intent_vs_convenience": "the footnote removal is product intent; the reserved "
                                         "chart slot is a data constraint, recorded as BLOCKED_DATA",
                "production_preferable_for": "reading the caveat without leaving the grid",
                "strongest_argument_against": "a peripheral capability was removed for density "
                                              "rather than for a user-visible gain",
            },
            "blocking_findings": [
                {"finding": "PRC-001", "resolution": "overridden",
                 "note": "density on the glance tier outweighs an in-place caveat"},
            ],
            "overrides": [
                {"finding": "PRC-001",
                 "justification": "the stance verb carries the caveat; the duplicate cost a line "
                                  "on every card in a 40-card grid",
                 "authority": "design-authority-main-loop"},
            ],
            "verdict": "APPROVE_WITH_CONDITIONS",
            "conditions": ["re-review card.chart_hero when the spark contract populates every row"],
            "preserved_strengths": ["hue system intact", "price clarity", "lane filter",
                                    "reserved chart slot", "count reconciliation"],
        },
        "approval.yml": {
            "schema": "mastermind.rig_approval.v1",
            "reference_id": reference_id,
            "approved_at": "2026-08-12T12:00:00Z",
            "verdict": "APPROVE_WITH_CONDITIONS",
            "authority": {"identity": "design-authority-main-loop", "role": "design_authority"},
            "reviewers": [
                {"identity": "critic-a-session", "role": "product_regression"},
                {"identity": "critic-b-session", "role": "visual_taste"},
            ],
            "author": {"identity": "designer-session-7"},
            "overrides": [
                {"finding": "PRC-001", "justification": "see verdict.yml",
                 "authority": "design-authority-main-loop"},
            ],
            "artifact_sha": VALID_SHA,
        },
    }


def write_set(root: Path, reference_id: str, docs: dict[str, Any]) -> Path:
    """Materialize an artifact set (plus its evidence screenshot) under a tmp repo root."""
    set_dir = root / "research" / "reference_integrity" / reference_id
    (set_dir / "reviews").mkdir(parents=True, exist_ok=True)
    for name, doc in docs.items():
        if doc is None:          # None = "this file does not exist"
            continue
        target = set_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    shot = root / "mockups" / "refs" / "reference_integrity" / reference_id / "prod-desktop-dark-en.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    shot.write_bytes(b"\x89PNG\r\n\x1a\n")
    return set_dir


def codes(root: Path, reference_id: str = "synthetic-ref", *, gate: bool = False) -> set[str]:
    """Finding codes the checker derives for one artifact set under ``root``."""
    return {f.code for f in findings(root, reference_id, gate=gate)}


def findings(root: Path, reference_id: str = "synthetic-ref", *, gate: bool = False) -> list[Any]:
    set_dir = root / "research" / "reference_integrity" / reference_id
    aset = RIG.load_artifact_set(set_dir, root)
    approved = {reference_id} if aset.status == "approved" else set()
    return RIG.evaluate_set(
        aset,
        groups=RIG.ALL_GROUPS if gate else None,
        approved_ids=approved,
        gate_mode=gate,
    )


def mutated(root: Path, mutate: Callable[[dict[str, Any]], None], reference_id: str) -> set[str]:
    docs = valid_docs(reference_id)
    mutate(docs)
    write_set(root, reference_id, docs)
    return codes(root, reference_id)


# ══════════════════════════════════════════════════════════════════════════════
# Suite A — mutation / anti-vacuity
# ══════════════════════════════════════════════════════════════════════════════

def test_the_valid_approved_set_passes(tmp_path):
    """The baseline every mutation departs from.  If this reds, every mutation below is noise."""
    write_set(tmp_path, "synthetic-ref", valid_docs("synthetic-ref"))
    assert findings(tmp_path) == [], [f.annotation() for f in findings(tmp_path)]


def test_deleting_a_core_capability_disposition_fires_missing_disposition(tmp_path):
    def mutate(docs):
        docs["proposal.yml"]["dispositions"] = [
            d for d in docs["proposal.yml"]["dispositions"] if d["id"] != "card.live_price"
        ]
    fired = mutated(tmp_path, mutate, "m-missing-disposition")
    assert "missing-disposition" in fired, sorted(fired)


def test_remove_with_no_rationale_fires_remove_without_rationale(tmp_path):
    def mutate(docs):
        docs["proposal.yml"]["dispositions"][3] = {"id": "card.footnote", "disposition": "REMOVE"}
    fired = mutated(tmp_path, mutate, "m-remove-bare")
    assert "remove-without-rationale" in fired, sorted(fired)
    assert "remove-without-user-job-impact" in fired
    assert "remove-without-superiority-case" in fired
    assert "remove-without-approval-ref" in fired


def test_blocked_data_without_dependency_or_escalation_fires(tmp_path):
    def mutate(docs):
        docs["proposal.yml"]["dispositions"][0] = {
            "id": "card.chart_hero", "disposition": "BLOCKED_DATA",
            "interim": "the slot is reserved",
        }
    fired = mutated(tmp_path, mutate, "m-blocked-bare")
    assert "blocked-data-without-dependency" in fired, sorted(fired)
    assert "blocked-data-without-escalation" in fired, sorted(fired)
    assert "blocked-data-without-interim" not in fired, "interim was supplied"


def test_blocked_data_without_interim_fires(tmp_path):
    def mutate(docs):
        docs["proposal.yml"]["dispositions"][0].pop("interim")
    fired = mutated(tmp_path, mutate, "m-blocked-no-interim")
    assert "blocked-data-without-interim" in fired, sorted(fired)


def test_unresolved_critic_blocker_on_an_approved_set_fires(tmp_path):
    def mutate(docs):
        docs["verdict.yml"]["blocking_findings"] = []
        docs["verdict.yml"]["overrides"] = []
        docs["approval.yml"]["overrides"] = []
    fired = mutated(tmp_path, mutate, "m-unresolved-block")
    assert "approved-with-unresolved-block" in fired, sorted(fired)


def test_an_upheld_revise_blocker_cannot_also_approve(tmp_path):
    """RIG §7: ``upheld_revise`` is a RECORDED resolution that drives REVISE/REJECT.

    A recorded-but-upheld blocker on an ``approved`` status is a block that disappeared
    silently — the precise thing §7 forbids — so the resolution being present is not enough.
    """
    def mutate(docs):
        docs["verdict.yml"]["blocking_findings"][0]["resolution"] = "upheld_revise"
        docs["verdict.yml"]["overrides"] = []
        docs["approval.yml"]["overrides"] = []
    fired = mutated(tmp_path, mutate, "m-upheld-block")
    assert "approved-with-unresolved-block" in fired, sorted(fired)


def test_a_resolved_by_change_blocker_does_not_block(tmp_path):
    """Anti-over-firing: the two approval-compatible resolutions must actually clear."""
    def mutate(docs):
        docs["verdict.yml"]["blocking_findings"][0]["resolution"] = "resolved_by_change"
        docs["verdict.yml"]["overrides"] = []
        docs["approval.yml"]["overrides"] = []
    fired = mutated(tmp_path, mutate, "m-resolved-block")
    assert "approved-with-unresolved-block" not in fired, sorted(fired)


def test_a_withdrawn_blocker_does_not_block(tmp_path):
    """Anti-over-firing: the second pass is allowed to withdraw a finding (RIG §6)."""
    def mutate(docs):
        docs["reviews/product_regression.yml"]["second_pass"]["amendments"][0]["action"] = "withdrawn"
        docs["verdict.yml"]["blocking_findings"] = []
        docs["verdict.yml"]["overrides"] = []
        docs["approval.yml"]["overrides"] = []
    fired = mutated(tmp_path, mutate, "m-withdrawn-block")
    assert "approved-with-unresolved-block" not in fired, sorted(fired)


def test_stripping_baseline_screenshots_fires_missing_baseline_evidence(tmp_path):
    def mutate(docs):
        docs["baseline.yml"]["evidence"]["screenshots"] = []
    fired = mutated(tmp_path, mutate, "m-no-evidence")
    assert "missing-baseline-evidence" in fired, sorted(fired)


def test_an_uncommitted_screenshot_path_fires_missing_baseline_evidence(tmp_path):
    def mutate(docs):
        docs["baseline.yml"]["evidence"]["screenshots"][0]["path"] = \
            "mockups/refs/reference_integrity/m-ghost-shot/never-captured.png"
    fired = mutated(tmp_path, mutate, "m-ghost-shot")
    assert "missing-baseline-evidence" in fired, sorted(fired)


def test_author_identity_equal_to_both_reviewers_fires_reviewer_not_independent(tmp_path):
    def mutate(docs):
        author = docs["manifest.yml"]["author"]["identity"]
        docs["reviews/product_regression.yml"]["reviewer"]["identity"] = author
        docs["reviews/visual_taste.yml"]["reviewer"]["identity"] = author
    fired = mutated(tmp_path, mutate, "m-not-independent")
    assert "reviewer-not-independent" in fired, sorted(fired)


def test_two_receipts_sharing_one_reviewer_identity_fires(tmp_path):
    def mutate(docs):
        docs["reviews/visual_taste.yml"]["reviewer"]["identity"] = "critic-a-session"
    fired = mutated(tmp_path, mutate, "m-same-reviewer")
    assert "reviewer-not-independent" in fired, sorted(fired)


def test_dropping_strongest_argument_against_fires_missing_verdict_question(tmp_path):
    def mutate(docs):
        docs["verdict.yml"]["packet"].pop("strongest_argument_against")
    fired = mutated(tmp_path, mutate, "m-missing-question")
    assert "missing-verdict-question" in fired, sorted(fired)


@pytest.mark.parametrize("key", RIG.PACKET_KEYS)
def test_every_one_of_the_eight_packet_answers_is_required(tmp_path, key):
    def mutate(docs):
        docs["verdict.yml"]["packet"][key] = "   "
    fired = mutated(tmp_path, mutate, f"m-packet-{key.replace('_', '-')}")
    assert "missing-verdict-question" in fired, f"{key}: {sorted(fired)}"


def test_duplicate_capability_id_fires(tmp_path):
    def mutate(docs):
        docs["baseline.yml"]["capabilities"].append(copy.deepcopy(docs["baseline.yml"]["capabilities"][0]))
    fired = mutated(tmp_path, mutate, "m-duplicate")
    assert "duplicate-capability-id" in fired, sorted(fired)


def test_dangling_disposition_fires(tmp_path):
    def mutate(docs):
        docs["proposal.yml"]["dispositions"][1]["id"] = "card.does_not_exist"
    fired = mutated(tmp_path, mutate, "m-dangling")
    assert "dangling-disposition" in fired, sorted(fired)


def test_data_motivated_removal_fires_blocked_data_as_removal(tmp_path):
    """RIG §1: a removal caused by data insufficiency IS a mis-filed BLOCKED_DATA."""
    def mutate(docs):
        docs["proposal.yml"]["dispositions"][0] = {
            "id": "card.chart_hero", "disposition": "REMOVE",
            "rationale": "chart enrichment covers 45/179 rows (25%)",
            "user_job_impact": "price geometry is gone",
            "superiority_case": "a quarter-populated hero looked broken",
            "approval_ref": "none",
        }
    fired = mutated(tmp_path, mutate, "m-data-removal")
    assert "blocked-data-as-removal" in fired, sorted(fired)


def test_a_product_motivated_removal_does_not_fire_the_data_heuristic(tmp_path):
    """Anti-over-firing: the heuristic must not flag every REMOVE."""
    fired = mutated(tmp_path, lambda docs: None, "m-product-removal")
    assert "blocked-data-as-removal" not in fired, sorted(fired)


@pytest.mark.parametrize("rationale", [
    "the spark join covers a quarter of plan rows",
    "coverage of the enrichment table is partial",
    "data availability for the sparkline is incomplete",
    "only 45/179 rows carry the field",
    "sparse population of the candidate table",
])
def test_the_data_motivation_heuristic_matches_its_documented_vocabulary(rationale):
    assert RIG.looks_data_motivated(rationale), rationale


@pytest.mark.parametrize("rationale", [
    "the footnote restated the stance verb on every card",
    "the zone chip moved into the header for hierarchy reasons",
    "operator ruling 2026-08-03 killed guidance prose on dense cards",
])
def test_the_data_motivation_heuristic_leaves_product_reasons_alone(rationale):
    assert not RIG.looks_data_motivated(rationale), rationale


def test_stale_review_receipt_fires_when_artifact_sha_moves(tmp_path):
    def mutate(docs):
        docs["proposal.yml"]["proposed_artifact"]["frozen_sha"] = "f" * 40
    fired = mutated(tmp_path, mutate, "m-stale-receipt")
    assert "stale-review-receipt" in fired, sorted(fired)


def test_worse_verdict_on_a_critical_task_without_adjudication_fires(tmp_path):
    def mutate(docs):
        docs["proposal.yml"]["user_tasks"][2]["critical"] = True
    fired = mutated(tmp_path, mutate, "m-worse-core")
    assert "worse-core-task-unadjudicated" in fired, sorted(fired)


def test_a_worse_critical_task_named_in_the_verdict_is_adjudicated(tmp_path):
    """Anti-over-firing: naming the task id in the verdict packet clears the block (RIG §6)."""
    def mutate(docs):
        docs["proposal.yml"]["user_tasks"][2]["critical"] = True
        docs["verdict.yml"]["conditions"].append(
            "task.read_caveat is accepted WORSE: the caveat is peripheral and one click away"
        )
    fired = mutated(tmp_path, mutate, "m-worse-core-adjudicated")
    assert "worse-core-task-unadjudicated" not in fired, sorted(fired)


def test_unwarranted_stronger_authority_without_adjudication_fires(tmp_path):
    def mutate(docs):
        docs["proposal.yml"]["authority_delta"][0].update({"direction": "stronger", "warranted": False})
    fired = mutated(tmp_path, mutate, "m-authority")
    assert "unwarranted-authority-unadjudicated" in fired, sorted(fired)


def test_invalid_disposition_enum_fires(tmp_path):
    def mutate(docs):
        docs["proposal.yml"]["dispositions"][1]["disposition"] = "DELETE"
    fired = mutated(tmp_path, mutate, "m-bad-disposition")
    assert "invalid-disposition" in fired, sorted(fired)


def test_invalid_task_verdict_enum_fires(tmp_path):
    def mutate(docs):
        docs["proposal.yml"]["user_tasks"][0]["verdict"] = "FINE"
    fired = mutated(tmp_path, mutate, "m-bad-task-verdict")
    assert "invalid-task-verdict" in fired, sorted(fired)


def test_invalid_status_fires(tmp_path):
    def mutate(docs):
        docs["manifest.yml"]["status"] = "blessed"
    fired = mutated(tmp_path, mutate, "m-bad-status")
    assert "invalid-status" in fired, sorted(fired)


def test_invalid_schema_id_fires(tmp_path):
    def mutate(docs):
        docs["proposal.yml"]["schema"] = "mastermind.rig_proposal.v2"
    fired = mutated(tmp_path, mutate, "m-bad-schema")
    assert "invalid-schema" in fired, sorted(fired)


def test_unparseable_yaml_fires_invalid_schema(tmp_path):
    write_set(tmp_path, "m-broken-yaml", valid_docs("m-broken-yaml"))
    (tmp_path / "research" / "reference_integrity" / "m-broken-yaml" / "proposal.yml").write_text(
        "schema: [unclosed\n", encoding="utf-8"
    )
    assert "invalid-schema" in codes(tmp_path, "m-broken-yaml")


def test_relocate_without_reachability_or_destination_fires(tmp_path):
    def mutate(docs):
        docs["proposal.yml"]["dispositions"][2] = {"id": "card.lane_chip", "disposition": "RELOCATE"}
    fired = mutated(tmp_path, mutate, "m-relocate-bare")
    assert "relocate-without-destination" in fired, sorted(fired)
    assert "relocate-without-reachability" in fired, sorted(fired)


def test_retain_without_target_fires(tmp_path):
    def mutate(docs):
        docs["proposal.yml"]["dispositions"][1].pop("target")
    fired = mutated(tmp_path, mutate, "m-retain-bare")
    assert "retain-without-target" in fired, sorted(fired)


def test_missing_approval_receipt_on_an_approved_set_fires(tmp_path):
    def mutate(docs):
        docs["approval.yml"] = None
    fired = mutated(tmp_path, mutate, "m-no-approval")
    assert "approved-without-receipt" in fired, sorted(fired)


def test_approved_status_with_a_revise_verdict_fires(tmp_path):
    def mutate(docs):
        docs["verdict.yml"]["verdict"] = "REVISE"
    fired = mutated(tmp_path, mutate, "m-wrong-verdict")
    assert "approved-with-wrong-verdict" in fired, sorted(fired)


def test_override_without_finding_id_or_justification_fires(tmp_path):
    def mutate(docs):
        docs["verdict.yml"]["overrides"] = [{"authority": "design-authority-main-loop"}]
    fired = mutated(tmp_path, mutate, "m-bad-override")
    assert "override-without-finding-id" in fired, sorted(fired)
    assert "override-without-justification" in fired, sorted(fired)


def test_lightweight_scope_without_both_attestations_fires(tmp_path):
    def mutate(docs):
        docs["manifest.yml"]["scope"] = "lightweight"
        docs["manifest.yml"]["lightweight"] = {"no_capability_change": True}
    fired = mutated(tmp_path, mutate, "m-lightweight")
    assert "lightweight-attestation-missing" in fired, sorted(fired)


def test_lightweight_citing_an_unapproved_archetype_fires(tmp_path):
    docs = valid_docs("m-lightweight-cite")
    docs["manifest.yml"]["scope"] = "lightweight"
    docs["manifest.yml"]["lightweight"] = {
        "no_capability_change": True, "no_hierarchy_change": True,
        "archetype_reference": "some-draft-reference",
    }
    write_set(tmp_path, "m-lightweight-cite", docs)
    fired = codes(tmp_path, "m-lightweight-cite")
    assert "lightweight-cites-unapproved-archetype" in fired, sorted(fired)


def test_superseded_without_a_successor_fires(tmp_path):
    def mutate(docs):
        docs["manifest.yml"]["status"] = "superseded"
    fired = mutated(tmp_path, mutate, "m-superseded")
    assert "superseded-without-successor" in fired, sorted(fired)


def test_missing_review_receipt_fires(tmp_path):
    def mutate(docs):
        docs["reviews/visual_taste.yml"] = None
    fired = mutated(tmp_path, mutate, "m-no-receipt")
    assert "missing-review-receipt" in fired, sorted(fired)


def test_missing_quarantine_attestation_fires(tmp_path):
    def mutate(docs):
        docs["reviews/product_regression.yml"]["quarantine"]["rationale_received_after_first_pass"] = False
    fired = mutated(tmp_path, mutate, "m-no-quarantine")
    assert "missing-quarantine-attestation" in fired, sorted(fired)


def test_second_pass_without_a_frozen_first_pass_fires(tmp_path):
    def mutate(docs):
        docs["reviews/product_regression.yml"]["first_pass"].pop("frozen_at")
    fired = mutated(tmp_path, mutate, "m-second-first")
    assert "second-pass-before-freeze" in fired, sorted(fired)


def test_missing_task_matrix_and_authority_delta_fire(tmp_path):
    def mutate(docs):
        docs["proposal.yml"]["user_tasks"] = []
        docs["proposal.yml"]["authority_delta"] = []
    fired = mutated(tmp_path, mutate, "m-no-matrix")
    assert "missing-task-matrix" in fired, sorted(fired)
    assert "missing-authority-delta" in fired, sorted(fired)


# ── Status-scaled validation ──────────────────────────────────────────────────

def test_a_draft_may_be_incomplete_but_must_still_parse(tmp_path):
    """Mid-flight is legal (RIG §3): completeness is not required until a terminal status."""
    docs = valid_docs("m-draft")
    docs["manifest.yml"]["status"] = "draft"
    docs["verdict.yml"] = None
    docs["approval.yml"] = None
    docs["reviews/product_regression.yml"] = None
    docs["reviews/visual_taste.yml"] = None
    docs["proposal.yml"]["dispositions"] = [d for d in docs["proposal.yml"]["dispositions"][:1]]
    write_set(tmp_path, "m-draft", docs)
    assert codes(tmp_path, "m-draft") == set()


def test_a_draft_with_a_dangling_disposition_still_fails(tmp_path):
    """"Incomplete is legal" never means "incoherent is legal"."""
    docs = valid_docs("m-draft-dangling")
    docs["manifest.yml"]["status"] = "draft"
    docs["proposal.yml"]["dispositions"][0]["id"] = "card.nope"
    write_set(tmp_path, "m-draft-dangling", docs)
    assert "dangling-disposition" in codes(tmp_path, "m-draft-dangling")


def test_a_terminal_verdict_with_no_recorded_review_is_illegal(tmp_path):
    docs = valid_docs("m-revise-no-receipts")
    docs["manifest.yml"]["status"] = "revise"
    docs["verdict.yml"]["verdict"] = "REVISE"
    docs["approval.yml"] = None
    docs["reviews/product_regression.yml"] = None
    docs["reviews/visual_taste.yml"] = None
    write_set(tmp_path, "m-revise-no-receipts", docs)
    fired = codes(tmp_path, "m-revise-no-receipts")
    assert "missing-review-receipt" in fired, sorted(fired)
    assert "missing-artifact-file" in fired, sorted(fired)


def test_a_revise_set_keeps_its_upheld_findings_without_failing_ci(tmp_path):
    """A REVISE record legitimately carries unresolved ledger defects — that record IS the artifact."""
    docs = valid_docs("m-revise-complete")
    docs["manifest.yml"]["status"] = "revise"
    docs["verdict.yml"]["verdict"] = "REVISE"
    docs["verdict.yml"]["blocking_findings"] = [
        {"finding": "PRC-001", "resolution": "upheld_revise", "note": "the caveat must survive"}
    ]
    docs["verdict.yml"]["overrides"] = []
    docs["approval.yml"] = None
    docs["proposal.yml"]["dispositions"][3] = {
        "id": "card.footnote", "disposition": "REMOVE",
        "rationale": "removed without a receipt — exactly what the critics blocked",
    }
    write_set(tmp_path, "m-revise-complete", docs)
    assert codes(tmp_path, "m-revise-complete") == set()


# ── L7 / L8 / L9, driven through the CLI over a tmp root ──────────────────────

def _annotations(capsys) -> list[str]:
    return [line for line in capsys.readouterr().out.splitlines() if line.startswith("::")]


def _codes_from(lines: list[str]) -> set[str]:
    out = set()
    for line in lines:
        if not line.startswith("::error title=reference-integrity::"):
            continue
        out.add(line.split("::", 2)[2].split(":", 1)[1].strip().split(":", 1)[0].strip())
    return out


def _cli_codes(root: Path, capsys) -> set[str]:
    RIG.main(["--root", str(root)])
    return {
        line.split("reference-integrity::", 1)[1].split(":", 1)[0]
        for line in _annotations(capsys) if line.startswith("::error")
    }


def test_an_unclaimed_design_system_reference_fires(tmp_path, capsys):
    write_set(tmp_path, "synthetic-ref", valid_docs("synthetic-ref"))
    ds = tmp_path / "mockups" / "design_system"
    ds.mkdir(parents=True, exist_ok=True)
    (ds / "specimen.html").write_text("<p>specimen</p>", encoding="utf-8")
    (ds / "macro_reference.html").write_text("<p>pre-RIG</p>", encoding="utf-8")
    (ds / "brand_new_reference.html").write_text("<p>unclaimed</p>", encoding="utf-8")
    fired = _cli_codes(tmp_path, capsys)
    assert "unclaimed-reference-file" in fired, sorted(fired)


def test_the_closed_pre_rig_list_and_the_specimen_are_exempt(tmp_path, capsys):
    write_set(tmp_path, "synthetic-ref", valid_docs("synthetic-ref"))
    ds = tmp_path / "mockups" / "design_system"
    ds.mkdir(parents=True, exist_ok=True)
    for name in sorted(RIG.NAMESPACE_EXEMPT):
        (ds / name).write_text("<p>x</p>", encoding="utf-8")
    fired = _cli_codes(tmp_path, capsys)
    assert "unclaimed-reference-file" not in fired, sorted(fired)


def test_a_claimed_design_system_reference_passes(tmp_path, capsys):
    write_set(tmp_path, "synthetic-ref", valid_docs("synthetic-ref"))
    ds = tmp_path / "mockups" / "design_system"
    ds.mkdir(parents=True, exist_ok=True)
    (ds / "synthetic-ref.html").write_text("<p>claimed</p>", encoding="utf-8")
    fired = _cli_codes(tmp_path, capsys)
    assert "unclaimed-reference-file" not in fired, sorted(fired)


def test_a_packet_without_a_rig_receipt_fires(tmp_path, capsys):
    write_set(tmp_path, "synthetic-ref", valid_docs("synthetic-ref"))
    packets = tmp_path / "research" / "migration_packets"
    packets.mkdir(parents=True, exist_ok=True)
    (packets / "MP-001-board.md").write_text("# Migration packet\n\nNo receipt here.\n", encoding="utf-8")
    fired = _cli_codes(tmp_path, capsys)
    assert "packet-without-rig-receipt" in fired, sorted(fired)


def test_a_packet_citing_an_approved_reference_passes(tmp_path, capsys):
    write_set(tmp_path, "synthetic-ref", valid_docs("synthetic-ref"))
    packets = tmp_path / "research" / "migration_packets"
    packets.mkdir(parents=True, exist_ok=True)
    (packets / "MP-001-board.md").write_text(
        "# Migration packet\n\nRIG-RECEIPT: synthetic-ref\n", encoding="utf-8"
    )
    fired = _cli_codes(tmp_path, capsys)
    assert "packet-without-rig-receipt" not in fired, sorted(fired)
    assert "packet-cites-unapproved-reference" not in fired, sorted(fired)


def test_a_packet_citing_an_unapproved_reference_fires(tmp_path, capsys):
    docs = valid_docs("synthetic-ref")
    docs["manifest.yml"]["status"] = "in_review"
    docs["approval.yml"] = None
    write_set(tmp_path, "synthetic-ref", docs)
    packets = tmp_path / "research" / "migration_packets"
    packets.mkdir(parents=True, exist_ok=True)
    (packets / "MP-001-board.md").write_text("RIG-RECEIPT: synthetic-ref\n", encoding="utf-8")
    fired = _cli_codes(tmp_path, capsys)
    assert "packet-cites-unapproved-reference" in fired, sorted(fired)


def test_a_compliant_registry_row_without_an_approved_reference_fires(tmp_path, capsys):
    write_set(tmp_path, "synthetic-ref", valid_docs("synthetic-ref"))
    (tmp_path / "config" / "product_experience").mkdir(parents=True, exist_ok=True)
    (tmp_path / RIG.REGISTRY_OVERRIDES).write_text(
        yaml.safe_dump({"pages": {"macro:elsewhere": {"design_system": {"compliant": True}}}}),
        encoding="utf-8",
    )
    (tmp_path / "data" / "product_experience").mkdir(parents=True, exist_ok=True)
    (tmp_path / RIG.REGISTRY_JSON).write_text(json.dumps({"pages": []}), encoding="utf-8")
    fired = _cli_codes(tmp_path, capsys)
    assert "compliant-row-without-approved-reference" in fired, sorted(fired)


def test_a_compliant_row_backed_by_an_approved_reference_passes(tmp_path, capsys):
    write_set(tmp_path, "synthetic-ref", valid_docs("synthetic-ref"))
    (tmp_path / "config" / "product_experience").mkdir(parents=True, exist_ok=True)
    (tmp_path / RIG.REGISTRY_OVERRIDES).write_text(
        yaml.safe_dump({"pages": {"macro:board": {"design_system": {"compliant": True}}}}),
        encoding="utf-8",
    )
    (tmp_path / "data" / "product_experience").mkdir(parents=True, exist_ok=True)
    (tmp_path / RIG.REGISTRY_JSON).write_text(json.dumps({"pages": []}), encoding="utf-8")
    fired = _cli_codes(tmp_path, capsys)
    assert "compliant-row-without-approved-reference" not in fired, sorted(fired)


def test_a_vanished_compiled_registry_does_not_silently_disarm_l9(tmp_path, capsys):
    write_set(tmp_path, "synthetic-ref", valid_docs("synthetic-ref"))
    (tmp_path / "data" / "product_experience").mkdir(parents=True, exist_ok=True)   # root present, file gone
    fired = _cli_codes(tmp_path, capsys)
    assert "missing-registry-file" in fired, sorted(fired)


def test_the_selftest_exits_zero_and_emits_no_live_error(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["check_reference_integrity.py", "--selftest"])
    assert RIG.main() == 0
    out = capsys.readouterr().out
    assert not [line for line in out.splitlines() if line.startswith("::error")], out
    assert "::notice" in out


# ══════════════════════════════════════════════════════════════════════════════
# Suite B — the founding case (RIG §10), against the real committed fixture
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def founding_findings() -> list[Any]:
    aset = RIG.load_artifact_set(FOUNDING_DIR, ROOT)
    approved = {a.reference_id for a in RIG.discover_artifact_sets(ROOT) if a.status == "approved"}
    return RIG.evaluate_set(aset, groups=RIG.ALL_GROUPS, approved_ids=approved, gate_mode=True)


@pytest.fixture(scope="module")
def founding_pairs(founding_findings) -> set[tuple[str, str]]:
    return {(f.code, f.subject) for f in founding_findings}


def _pair(code: str, suffix: str) -> tuple[str, str]:
    return (code, f"{FOUNDING_ID}:{suffix}")


# The ten recorded regressions of RIG §10, mapped to the checker codes + the fixture
# evidence that catches each.  This map is the audit trail: it is what makes "the gate
# would have caught it" a checkable claim rather than a story.
TEN_REGRESSIONS: dict[str, dict[str, Any]] = {
    "chart hero removed": {
        "pairs": [_pair("blocked-data-as-removal", "card.chart_hero"),
                  _pair("remove-without-superiority-case", "card.chart_hero"),
                  _pair("remove-without-approval-ref", "card.chart_hero")],
        "evidence": "proposal.yml dispositions[card.chart_hero]: REMOVE with a coverage rationale "
                    "and no user_job_impact/superiority_case/approval_ref",
    },
    "live price removed": {
        "pairs": [_pair("missing-disposition", "card.live_quote"),
                  _pair("worse-core-task-unadjudicated", "task.price_now")],
        "evidence": "baseline.yml capabilities[card.live_quote] has NO disposition row; "
                    "user_tasks[task.price_now] critical:true verdict WORSE",
    },
    "live change removed": {
        "pairs": [_pair("missing-disposition", "card.live_change"),
                  _pair("worse-core-task-unadjudicated", "task.momentum_context")],
        "evidence": "baseline.yml capabilities[card.live_change] silently absent from the "
                    "proposal ledger; user_tasks[task.momentum_context] critical WORSE",
    },
    "Priority score removed": {
        "pairs": [_pair("missing-disposition", "card.priority_score"),
                  _pair("worse-core-task-unadjudicated", "task.readiness_rank")],
        "evidence": "priority survives only as invisible sort order (proposal.yml notes); "
                    "no disposition row; task.readiness_rank critical WORSE",
    },
    "compact Zone abstraction removed": {
        "pairs": [_pair("remove-without-superiority-case", "card.zone_chip"),
                  _pair("remove-without-approval-ref", "card.zone_chip")],
        "evidence": "dispositions[card.zone_chip]: REMOVE with a rationale but no receipt that "
                    "explicit execution levels beat the compact zone on a glance surface",
    },
    "what_to_do prose introduced": {
        "pairs": [_pair("unwarranted-authority-unadjudicated", "auth.prose_thesis")],
        "evidence": "authority_delta[auth.prose_thesis]: direction stronger, warranted false — "
                    "re-introduces the card prose the operator killed 2026-08-03",
    },
    "day-X-of-45 promoted": {
        "pairs": [_pair("unwarranted-authority-unadjudicated", "auth.window_position")],
        "evidence": "authority_delta[auth.window_position]: stronger/unwarranted — a holding-window "
                    "claim the engine does not stand behind on the glance tier",
    },
    "Entry/T1/Void geometry": {
        "pairs": [_pair("unwarranted-authority-unadjudicated", "auth.zone_to_levels"),
                  _pair("remove-without-approval-ref", "card.zone_chip")],
        "evidence": "authority_delta[auth.zone_to_levels]: stronger/unwarranted — labelled "
                    "execution levels replace a relevant range on every card",
    },
    "color identity removed": {
        "pairs": [_pair("remove-without-approval-ref", "card.verb_hue_identity"),
                  _pair("remove-without-superiority-case", "card.verb_hue_identity"),
                  _pair("worse-core-task-unadjudicated", "task.glance_scan")],
        "evidence": "dispositions[card.verb_hue_identity]: REMOVE extends a lifecycle-mark ruling "
                    "to the whole colour identity with no ruling that authorizes it",
    },
    "data-deficiency-as-deletion": {
        "pairs": [_pair("blocked-data-as-removal", "card.chart_hero")],
        "evidence": "RIG §1: 45/179 coverage is a BLOCKED_DATA dependency, never a REMOVE",
    },
}


def test_the_ten_regressions_map_is_populated():
    assert len(TEN_REGRESSIONS) == 10, sorted(TEN_REGRESSIONS)
    for name, entry in TEN_REGRESSIONS.items():
        assert entry["pairs"], f"{name}: no checker code claims to catch this regression"
        assert entry["evidence"].strip(), f"{name}: no fixture evidence recorded"


def test_the_founding_fixture_is_blocked_by_evaluate(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["check_reference_integrity.py", "--evaluate", FOUNDING_ID])
    assert RIG.main() == 3
    out = capsys.readouterr().out
    assert "BLOCKED" in out


@pytest.mark.parametrize("regression", sorted(TEN_REGRESSIONS))
def test_each_founding_regression_is_caught(regression, founding_pairs):
    for pair in TEN_REGRESSIONS[regression]["pairs"]:
        assert pair in founding_pairs, (
            f"{regression}: {pair[0]} did not fire for {pair[1]}\n"
            f"evidence: {TEN_REGRESSIONS[regression]['evidence']}"
        )


@pytest.mark.parametrize("capability", [
    "card.live_quote", "card.live_change", "card.priority_score",
    "card.compact_glance_geometry", "card.caution_popover",
])
def test_every_silently_dropped_capability_fires_missing_disposition(capability, founding_pairs):
    assert _pair("missing-disposition", capability) in founding_pairs


def test_the_chart_hero_removal_is_derived_as_a_misfiled_blocked_data(founding_pairs):
    assert _pair("blocked-data-as-removal", "card.chart_hero") in founding_pairs


@pytest.mark.parametrize("capability", ["card.zone_chip", "card.verb_hue_identity"])
def test_receiptless_removals_fire_remove_without_approval_ref(capability, founding_pairs):
    assert _pair("remove-without-approval-ref", capability) in founding_pairs


def test_the_stance_verb_relocation_has_no_reachability_proof(founding_pairs):
    assert _pair("relocate-without-reachability", "card.stance_verb") in founding_pairs


@pytest.mark.parametrize("task", [
    "task.glance_scan", "task.price_now", "task.momentum_context", "task.readiness_rank",
])
def test_every_worse_critical_task_is_unadjudicated(task, founding_pairs):
    assert _pair("worse-core-task-unadjudicated", task) in founding_pairs


@pytest.mark.parametrize("row", ["auth.zone_to_levels", "auth.window_position", "auth.prose_thesis"])
def test_every_unwarranted_authority_row_is_unadjudicated(row, founding_pairs):
    assert _pair("unwarranted-authority-unadjudicated", row) in founding_pairs


def test_the_fixture_keeps_its_good_changes_uncharged(founding_findings):
    """The gate holds both thoughts at once (RIG §10): it must not charge the good work."""
    charged = {f.subject for f in founding_findings}
    for good in ("board.triage_shelves", "board.track_record_strip", "card.stage_tracker"):
        assert _pair("missing-disposition", good) not in {(f.code, f.subject) for f in founding_findings}
        assert f"{FOUNDING_ID}:{good}" not in {s for s in charged if "remove-without" in s}


class TestFoundingReceipts:
    """Receipt-level invariants for the founding fixture (RIG §6/§7/§10).

    These pin the RECORD the independent critics and the design authority must leave, not
    the checker's own opinion of it.  Do NOT satisfy a failure here by writing or editing
    the receipts from this session: a receipt authored by the party being reviewed is not
    an independent review, and manufacturing one is the exact laundering RIG §6 stops.
    """

    def test_both_receipts_exist_with_correct_roles_and_quarantine(self):
        for role in RIG.REVIEW_ROLES:
            path = FOUNDING_DIR / "reviews" / f"{role}.yml"
            assert path.exists(), f"{path} has not landed yet"
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
            assert doc["schema"] == "mastermind.rig_review.v1"
            assert doc["role"] == role
            assert doc["quarantine"]["rationale_received_after_first_pass"] is True
            assert doc["first_pass"]["frozen_at"], "first-pass findings must be frozen"

    def test_product_regression_records_at_least_one_blocker(self):
        path = FOUNDING_DIR / "reviews" / "product_regression.yml"
        assert path.exists(), f"{path} has not landed yet"
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        blockers = [f for f in doc["first_pass"]["findings"] if f.get("severity") == "blocker"]
        assert blockers, "the founding case is a BLOCK — the product critic must record a blocker"

    def test_the_verdict_is_revise_with_all_eight_answers_and_recorded_strengths(self):
        path = FOUNDING_DIR / "verdict.yml"
        assert path.exists(), f"{path} has not landed yet"
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert doc["verdict"] == "REVISE"
        for key in RIG.PACKET_KEYS:
            assert str(doc["packet"].get(key) or "").strip(), f"packet.{key} is empty"
        assert len(doc.get("preserved_strengths") or []) >= 5, \
            "a BLOCK is never a strawman — the good architecture is recorded"

    def test_repo_mode_accepts_the_fixture_at_status_revise(self, capsys):
        exit_code = RIG.main(["--root", str(ROOT)])
        out = capsys.readouterr().out
        assert exit_code == 0, out

    def test_a_copy_flipped_to_approved_fails_on_unresolved_blockers(self, tmp_path):
        target = tmp_path / "research" / "reference_integrity" / FOUNDING_ID
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(FOUNDING_DIR, target)
        manifest_path = target / "manifest.yml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = "approved"
        manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True),
                                 encoding="utf-8")
        fired = codes(tmp_path, FOUNDING_ID)
        assert "approved-with-unresolved-block" in fired, sorted(fired)


# ══════════════════════════════════════════════════════════════════════════════
# Suite C — output shape (house annotation law)
# ══════════════════════════════════════════════════════════════════════════════

def test_every_annotation_starts_its_line(tmp_path, capsys):
    """GitHub only parses a workflow command when '::' is the first thing on the line."""
    docs = valid_docs("shape-ref")
    docs["proposal.yml"]["dispositions"] = []
    write_set(tmp_path, "shape-ref", docs)
    RIG.main(["--root", str(tmp_path)])
    lines = capsys.readouterr().out.splitlines()
    marked = [line for line in lines if "::error" in line or "::notice" in line]
    assert marked, "the run produced no annotation at all — the shape check would be vacuous"
    for line in marked:
        assert line.startswith("::"), f"annotation does not start its line: {line!r}"


def test_the_evaluate_mode_annotations_start_their_line(capsys):
    RIG.main(["--root", str(ROOT), "--evaluate", FOUNDING_ID])
    lines = capsys.readouterr().out.splitlines()
    marked = [line for line in lines if "::error" in line or "::notice" in line]
    assert marked
    for line in marked:
        assert line.startswith("::"), f"annotation does not start its line: {line!r}"


def test_findings_print_once_per_code_and_subject(tmp_path, capsys):
    docs = valid_docs("dedupe-ref")
    docs["proposal.yml"]["dispositions"] = []
    write_set(tmp_path, "dedupe-ref", docs)
    RIG.main(["--root", str(tmp_path)])
    errors = [line for line in capsys.readouterr().out.splitlines() if line.startswith("::error")]
    assert len(errors) == len(set(errors)), "a (code, subject) pair printed more than once"


def test_a_clean_repo_mode_run_exits_zero_and_says_so(tmp_path, capsys):
    write_set(tmp_path, "synthetic-ref", valid_docs("synthetic-ref"))
    assert RIG.main(["--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "::notice" in out
    assert "::error" not in out
