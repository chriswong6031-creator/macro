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

D. **Revision continuity (RIG §13 / L10, V1.1).**  The seam BETWEEN cycles.  Its anchor case
   is the real r2→r3 failure: a successor that fixed everything its own rationale discussed
   and silently dropped four items the predecessor had already upheld.  The suite's spine is
   that the omission must be caught at status ``in_review`` with **no critic receipts in
   existence** — continuity is an admission gate, not a judgment gate, so it fires before the
   fleet spends two independent Opus critics re-deriving the gap.  Fixture builders here are
   again independent of the checker's own ``--selftest`` fixtures.

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


# ══════════════════════════════════════════════════════════════════════════════
# Suite D — revision continuity closure (RIG §13 / L10, V1.1)
# ══════════════════════════════════════════════════════════════════════════════

# The four items the REAL r3 silently dropped: card→detail navigation, the degraded-freshness
# disclosure, the anonymous-gate copy contract, and whole-book reachability.  Two of them were
# by then in their THIRD consecutive revision, and nothing mechanical noticed.
THE_FOUR_OMISSIONS = ["COND-CARD-LINK", "COND-STALENESS", "COND-ANON-COPY", "COND-REACHABILITY"]

# ...plus one upheld blocker the successor genuinely did fix.  The predecessor ALSO carries a
# blocker it resolved itself, which must never be demanded of the successor.
PREDECESSOR_CONDITIONS = [
    ("COND-CARD-LINK", "the card links to the name's detail surface"),
    ("COND-STALENESS", "the board-level degraded-freshness state returns"),
    ("COND-ANON-COPY", "the anon gate stops promising levels no card renders"),
    ("COND-REACHABILITY", "the whole book stays reachable, not the first 40 rows"),
]


def predecessor_docs(reference_id: str, *, bare_conditions: bool = False) -> dict[str, Any]:
    """A REVISE predecessor: one upheld blocker, one self-resolved blocker, four conditions."""
    docs = valid_docs(reference_id)
    docs["manifest.yml"]["status"] = "revise"
    docs["verdict.yml"]["verdict"] = "REVISE"
    docs["verdict.yml"]["blocking_findings"] = [
        {"finding": "PRC-201", "resolution": "upheld_revise",
         "note": "the counted risk carrier is gone from the card"},
        {"finding": "PRC-202", "resolution": "resolved_by_change",
         "note": "closed in the predecessor's own cycle"},
    ]
    docs["verdict.yml"]["overrides"] = []
    docs["verdict.yml"]["conditions"] = (
        [text for _cid, text in PREDECESSOR_CONDITIONS] if bare_conditions
        else [{"id": cid, "text": text} for cid, text in PREDECESSOR_CONDITIONS]
    )
    docs["approval.yml"] = None
    return docs


def full_closure() -> list[dict[str, Any]]:
    """An honest, complete closure of the predecessor's five open items."""
    rows: list[dict[str, Any]] = [
        {"id": "PRC-201", "kind": "blocker", "disposition": "RESOLVED_BY_CHANGE",
         "evidence": "the counted risk pill is back in the marks row with its popover",
         "changed_files": ["mockups/design_system/board.js"]},
    ]
    for cid, text in PREDECESSOR_CONDITIONS:
        rows.append({"id": cid, "kind": "condition", "disposition": "CARRIED_BLOCK",
                     "note": f"not moved this cycle: {text}"})
    return rows


def successor_docs(
    reference_id: str,
    predecessors: list[str],
    closure: list[dict[str, Any]] | None,
    *,
    status: str = "in_review",
    closes: str | None = None,
    source: str = "on_disk",
    source_ref: str = "",
    with_receipts: bool = False,
    revision_mandate: list[str] | None = None,
) -> dict[str, Any]:
    """A successor declaring ``predecessors`` (ordered oldest → nearest).

    Receipts are absent by default ON PURPOSE: RIG §13.4 requires the gate to fire at
    ``in_review``, before any critic has been dispatched.
    """
    docs = valid_docs(reference_id)
    docs["manifest.yml"]["status"] = status
    docs["manifest.yml"]["lineage"] = {"predecessors": list(predecessors)}
    if status != "approved":
        docs["approval.yml"] = None
    if not with_receipts:
        docs["reviews/product_regression.yml"] = None
        docs["reviews/visual_taste.yml"] = None
    if revision_mandate is not None:
        docs["proposal.yml"]["revision_mandate"] = revision_mandate
    if closure is not None:
        block: dict[str, Any] = {
            "reference_id": closes or (predecessors[-1] if predecessors else ""),
            "verdict": "REVISE", "source": source, "closure": closure,
        }
        if source_ref:
            block["source_ref"] = source_ref
        docs["continuity.yml"] = {
            "schema": "mastermind.rig_continuity.v1",
            "reference_id": reference_id,
            "predecessors": [block],
        }
    return docs


def continuity_case(
    root: Path,
    tag: str,
    closure: list[dict[str, Any]] | None,
    *,
    bare_conditions: bool = False,
    **kwargs: Any,
) -> list[Any]:
    """Materialize a predecessor + a successor declaring it; return the successor's findings."""
    pred, succ = f"{tag}-pred", f"{tag}-succ"
    write_set(root, pred, predecessor_docs(pred, bare_conditions=bare_conditions))
    write_set(root, succ, successor_docs(succ, [pred], closure, **kwargs))
    return findings(root, succ)


def continuity_codes(root: Path, tag: str, closure: list[dict[str, Any]] | None, **kwargs: Any) -> set[str]:
    return {f.code for f in continuity_case(root, tag, closure, **kwargs)}


def missing_items(found: list[Any]) -> set[str]:
    return {f.subject.rsplit(":", 1)[-1] for f in found if f.code == "continuity-item-missing"}


# ── The anchor case: the actual r2→r3 failure ─────────────────────────────────

def test_the_dropped_items_fire_before_a_single_critic_has_run(tmp_path):
    """RIG §13.6 — the anti-vacuity case, reconstructed from the real failure.

    A successor declares its predecessor, fixes the blocker its own rationale discussed, and
    omits the four items the predecessor had already upheld.  The gate must catch that at
    ``in_review``, with NO critic receipts in existence: continuity is an ADMISSION gate.
    """
    kept = [row for row in full_closure() if row["id"] == "PRC-201"]
    found = continuity_case(tmp_path, "r3", kept)
    fired = {f.code for f in found}

    succ_dir = tmp_path / "research" / "reference_integrity" / "r3-succ"
    assert yaml.safe_load((succ_dir / "manifest.yml").read_text())["status"] == "in_review"
    for role in RIG.REVIEW_ROLES:
        assert not (succ_dir / "reviews" / f"{role}.yml").exists(), \
            "the case is only meaningful with zero critic receipts on disk"
    assert "missing-review-receipt" not in fired, \
        "no critic has been dispatched — the continuity failure must not need one"
    assert "stale-review-receipt" not in fired

    assert missing_items(found) == set(THE_FOUR_OMISSIONS), sorted(fired)
    assert len([f for f in found if f.code == "continuity-item-missing"]) == 4


def test_adding_the_four_rows_back_clears_the_finding(tmp_path):
    fired = continuity_codes(tmp_path, "r3-complete", full_closure())
    assert fired == set(), sorted(fired)


def test_a_predecessor_row_it_resolved_itself_is_never_demanded(tmp_path):
    """Anti-over-firing: ``resolved_by_change`` / ``overridden`` closed IN the predecessor."""
    found = continuity_case(tmp_path, "r3-selfclosed", full_closure())
    assert "PRC-202" not in missing_items(found)


def test_a_resolved_by_change_row_without_changed_files_fires(tmp_path):
    rows = full_closure()
    rows[0].pop("changed_files")
    fired = continuity_codes(tmp_path, "r3-no-files", rows)
    assert "continuity-resolved-without-evidence" in fired, sorted(fired)


def test_a_resolved_by_change_row_without_evidence_fires(tmp_path):
    rows = full_closure()
    rows[0]["evidence"] = "   "
    fired = continuity_codes(tmp_path, "r3-no-evidence", rows)
    assert "continuity-resolved-without-evidence" in fired, sorted(fired)


def test_a_carried_block_row_blocks_approved(tmp_path):
    """§13.1: CARRIED_BLOCK is legal and honest — and it cannot coexist with ``approved``."""
    fired = continuity_codes(tmp_path, "r3-approved", full_closure(),
                             status="approved", with_receipts=True)
    assert "continuity-carried-block-approved" in fired, sorted(fired)


def test_a_fully_resolved_closure_does_not_block_approved(tmp_path):
    """Anti-over-firing: approval is blocked by the carried debt, not by having a record."""
    rows = full_closure()
    for row in rows:
        row.update({"disposition": "RESOLVED_BY_CHANGE",
                    "evidence": "closed in the new SHA",
                    "changed_files": ["mockups/design_system/board.js"]})
        row.pop("note", None)
    fired = continuity_codes(tmp_path, "r3-all-fixed", rows,
                             status="approved", with_receipts=True)
    assert "continuity-carried-block-approved" not in fired, sorted(fired)
    assert "continuity-item-missing" not in fired, sorted(fired)


# ── The record must exist, and be internally coherent ─────────────────────────

def test_a_successor_of_a_revise_with_no_continuity_file_fires(tmp_path):
    fired = continuity_codes(tmp_path, "r3-none", None)
    assert "continuity-missing" in fired, sorted(fired)


def test_a_successor_of_an_APPROVED_predecessor_needs_no_continuity_file(tmp_path):
    """Anti-over-firing: §13 binds a cycle that follows a REVISE/REJECT, not every lineage."""
    write_set(tmp_path, "ok-pred", valid_docs("ok-pred"))            # status approved
    write_set(tmp_path, "ok-succ", successor_docs("ok-succ", ["ok-pred"], None))
    fired = codes(tmp_path, "ok-succ")
    assert "continuity-missing" not in fired, sorted(fired)


def test_a_set_declaring_no_predecessor_is_untouched_by_l10(tmp_path):
    write_set(tmp_path, "solo-ref", valid_docs("solo-ref"))
    fired = codes(tmp_path, "solo-ref")
    assert not {c for c in fired if c.startswith("continuity-")}, sorted(fired)


def test_the_same_predecessor_id_in_two_rows_fires(tmp_path):
    rows = full_closure()
    rows.append(copy.deepcopy(rows[1]))
    fired = continuity_codes(tmp_path, "r3-dup", rows)
    assert "continuity-item-duplicated" in fired, sorted(fired)


@pytest.mark.parametrize("disposition", ["FIXED", "", "resolved_by_change"])
def test_a_disposition_outside_the_four_value_enum_fires(tmp_path, disposition):
    rows = full_closure()
    rows[1]["disposition"] = disposition
    fired = continuity_codes(tmp_path, f"r3-enum-{disposition or 'blank'}", rows)
    assert "continuity-invalid-disposition" in fired, sorted(fired)


def test_a_closure_id_the_predecessor_never_minted_fires_renamed_without_linkage(tmp_path):
    rows = full_closure()
    rows.append({"id": "PRC-999", "kind": "blocker", "disposition": "CARRIED_BLOCK",
                 "note": "an id that exists nowhere in the predecessor record"})
    fired = continuity_codes(tmp_path, "r3-renamed", rows)
    assert "continuity-renamed-without-linkage" in fired, sorted(fired)


def test_a_rename_carrying_predecessor_ref_is_accepted_and_closes_the_item(tmp_path):
    """Anti-over-firing: a renamed item is legal when it names what it closes."""
    rows = full_closure()
    rows[1] = {"id": "PRC-301", "kind": "condition", "disposition": "CARRIED_BLOCK",
               "predecessor_ref": "COND-CARD-LINK",
               "note": "re-raised at r3 under a new id — third consecutive revision"}
    found = continuity_case(tmp_path, "r3-linked", rows)
    fired = {f.code for f in found}
    assert "continuity-renamed-without-linkage" not in fired, sorted(fired)
    assert "COND-CARD-LINK" not in missing_items(found), sorted(fired)


def test_superseded_without_superseded_by_or_linkage_fires(tmp_path):
    rows = full_closure()
    rows[1] = {"id": "COND-CARD-LINK", "kind": "condition", "disposition": "SUPERSEDED"}
    fired = continuity_codes(tmp_path, "r3-superseded", rows)
    assert "continuity-superseded-without-linkage" in fired, sorted(fired)


def test_a_complete_superseded_row_passes(tmp_path):
    rows = full_closure()
    rows[1] = {"id": "COND-CARD-LINK", "kind": "condition", "disposition": "SUPERSEDED",
               "superseded_by": "PRC-311",
               "linkage": "PRC-311 requires the same navigation on a wider surface"}
    fired = continuity_codes(tmp_path, "r3-superseded-ok", rows)
    assert "continuity-superseded-without-linkage" not in fired, sorted(fired)


@pytest.mark.parametrize("dropped", ["authority", "rationale", "finding"])
def test_an_override_missing_any_of_its_three_fields_fires(tmp_path, dropped):
    rows = full_closure()
    row = {"id": "COND-CARD-LINK", "kind": "condition", "disposition": "OVERRIDDEN",
           "authority": "design-authority-main-loop",
           "rationale": "navigation belongs to the paid detail tier",
           "finding": "COND-CARD-LINK"}
    row.pop(dropped)
    rows[1] = row
    fired = continuity_codes(tmp_path, f"r3-override-{dropped}", rows)
    assert "continuity-overridden-without-authority" in fired, sorted(fired)


def test_a_complete_override_row_passes(tmp_path):
    rows = full_closure()
    rows[1] = {"id": "COND-CARD-LINK", "kind": "condition", "disposition": "OVERRIDDEN",
               "authority": "design-authority-main-loop",
               "rationale": "navigation belongs to the paid detail tier",
               "finding": "COND-CARD-LINK"}
    fired = continuity_codes(tmp_path, "r3-override-ok", rows)
    assert "continuity-overridden-without-authority" not in fired, sorted(fired)


# ── Snapshot form: a predecessor whose PR is still open ───────────────────────

def test_a_snapshot_predecessor_without_a_source_ref_fires(tmp_path):
    fired = continuity_codes(tmp_path, "r3-snap", full_closure(), source="snapshot")
    assert "continuity-snapshot-without-source" in fired, sorted(fired)


def test_a_snapshot_predecessor_with_a_source_ref_passes(tmp_path):
    fired = continuity_codes(tmp_path, "r3-snap-ok", full_closure(), source="snapshot",
                             source_ref="PR #5533 head f717aab2 — set not in this checkout")
    assert "continuity-snapshot-without-source" not in fired, sorted(fired)


def test_a_predecessor_absent_from_the_checkout_must_use_the_snapshot_form(tmp_path):
    """``source: on_disk`` for a set that is NOT on disk is an unprovable claim."""
    docs = successor_docs("ghost-succ", ["ghost-pred"], full_closure())
    write_set(tmp_path, "ghost-succ", docs)
    fired = codes(tmp_path, "ghost-succ")
    assert "continuity-snapshot-without-source" in fired, sorted(fired)


def test_an_unresolvable_predecessor_cannot_prove_it_approved(tmp_path):
    """Fail-closed: no continuity.yml + an unreadable predecessor is still ``continuity-missing``."""
    write_set(tmp_path, "ghost2-succ", successor_docs("ghost2-succ", ["ghost2-pred"], None))
    fired = codes(tmp_path, "ghost2-succ")
    assert "continuity-missing" in fired, sorted(fired)


# ── Nearest-predecessor scoping (RIG §13.2) ───────────────────────────────────

def test_only_the_nearest_predecessors_items_are_demanded(tmp_path):
    """A chain is closed link by link — re-closing the older ancestor would rubber-stamp."""
    write_set(tmp_path, "chain-old", predecessor_docs("chain-old"))
    recent = predecessor_docs("chain-recent")
    recent["verdict.yml"]["blocking_findings"] = [
        {"finding": "PRC-401", "resolution": "upheld_revise", "note": "the newer open item"},
    ]
    recent["verdict.yml"]["conditions"] = [{"id": "COND-NEW", "text": "the newer condition"}]
    recent["manifest.yml"]["lineage"] = {"predecessors": ["chain-old"]}
    write_set(tmp_path, "chain-recent", recent)
    write_set(tmp_path, "chain-succ", successor_docs(
        "chain-succ", ["chain-old", "chain-recent"],
        [{"id": "PRC-401", "kind": "blocker", "disposition": "CARRIED_BLOCK", "note": "not moved"},
         {"id": "COND-NEW", "kind": "condition", "disposition": "CARRIED_BLOCK", "note": "not moved"}],
    ))
    found = findings(tmp_path, "chain-succ")
    assert missing_items(found) == set(), [f.annotation() for f in found]


# ── The mandate must cover what the closure carries (RIG §13.5) ───────────────

def test_a_revision_mandate_short_of_the_closure_set_fires(tmp_path):
    fired = continuity_codes(tmp_path, "r3-mandate", full_closure(),
                             revision_mandate=["PRC-201", "COND-CARD-LINK"])
    assert "mandate-incomplete" in fired, sorted(fired)


def test_a_complete_revision_mandate_passes(tmp_path):
    fired = continuity_codes(tmp_path, "r3-mandate-ok", full_closure(),
                             revision_mandate=["PRC-201"] + THE_FOUR_OMISSIONS)
    assert "mandate-incomplete" not in fired, sorted(fired)


def test_no_revision_mandate_at_all_is_inert(tmp_path):
    """continuity.yml IS the record; the mandate is an optional restatement of it."""
    fired = continuity_codes(tmp_path, "r3-mandate-absent", full_closure())
    assert "mandate-incomplete" not in fired, sorted(fired)


# ── Conditions must be citable — forward-binding, never retroactive (§13.3) ───

def test_a_bare_string_condition_fires_once_a_successor_must_cite_it(tmp_path):
    kept = [row for row in full_closure() if row["id"] == "PRC-201"]
    fired = continuity_codes(tmp_path, "legacy", kept, bare_conditions=True)
    assert "condition-without-id" in fired, sorted(fired)


def test_a_legacy_verdict_nobody_has_succeeded_is_never_punished(tmp_path):
    """The other direction: the SAME verdict, with no successor, is clean."""
    write_set(tmp_path, "legacy-alone", predecessor_docs("legacy-alone", bare_conditions=True))
    fired = codes(tmp_path, "legacy-alone")
    assert "condition-without-id" not in fired, sorted(fired)
    assert fired == set(), sorted(fired)


def test_a_provenance_only_ancestor_keeps_its_legacy_conditions(tmp_path):
    """The §10 founding fixture's shape: named as provenance, never the nearest.

    Nothing has to cite its conditions, so a rule written afterwards must not churn it.
    """
    write_set(tmp_path, "prov-old", predecessor_docs("prov-old", bare_conditions=True))
    recent = predecessor_docs("prov-recent")
    recent["manifest.yml"]["lineage"] = {"predecessors": ["prov-old"]}
    write_set(tmp_path, "prov-recent", recent)
    write_set(tmp_path, "prov-succ", successor_docs(
        "prov-succ", ["prov-old", "prov-recent"], full_closure(), closes="prov-recent"))
    fired = codes(tmp_path, "prov-succ")
    assert "condition-without-id" not in fired, sorted(fired)


def test_the_founding_fixture_keeps_its_legacy_conditions_on_main(capsys):
    """The real §10 fixture: bare-string conditions, nothing succeeds it, repo mode is clean."""
    doc = yaml.safe_load((FOUNDING_DIR / "verdict.yml").read_text(encoding="utf-8"))
    assert any(not isinstance(c, dict) for c in doc["conditions"]), \
        "this test is only meaningful while the fixture is legacy-form"
    assert RIG.main(["--root", str(ROOT)]) == 0
    out = capsys.readouterr().out
    assert "condition-without-id" not in out, out


# ── undeclared-predecessor — the anti-escape half (repo-wide, §13.2) ──────────

def repo_l10(root: Path) -> list[Any]:
    return RIG.rule_l10_repo(root, RIG.discover_artifact_sets(root))


def test_declaring_a_conveniently_old_ancestor_does_not_satisfy_the_law(tmp_path):
    """The loophole the nearest-only obligation would otherwise open.

    A successor on the same route as a newer non-approved set, declaring only the OLD one,
    must fire — otherwise the closure obligation could be pointed at a stale ancestor with
    nothing left open.
    """
    write_set(tmp_path, "route-old", predecessor_docs("route-old"))
    write_set(tmp_path, "route-recent", predecessor_docs("route-recent"))
    write_set(tmp_path, "route-succ",
              successor_docs("route-succ", ["route-old"], full_closure(), closes="route-old"))
    found = repo_l10(tmp_path)
    assert ("undeclared-predecessor", "route-succ:route-recent") in {(f.code, f.subject) for f in found}, \
        [f.annotation() for f in found]


def test_declaring_every_non_approved_set_on_the_route_passes(tmp_path):
    write_set(tmp_path, "route2-old", predecessor_docs("route2-old"))
    write_set(tmp_path, "route2-recent", predecessor_docs("route2-recent"))
    write_set(tmp_path, "route2-succ", successor_docs(
        "route2-succ", ["route2-old", "route2-recent"], full_closure()))
    assert [f.code for f in repo_l10(tmp_path)] == []


def test_a_predecessor_reached_through_the_declared_chain_counts_as_declared(tmp_path):
    """Declaring the nearest, whose own lineage names the older one, is complete provenance."""
    write_set(tmp_path, "chain2-old", predecessor_docs("chain2-old"))
    recent = predecessor_docs("chain2-recent")
    recent["manifest.yml"]["lineage"] = {"predecessors": ["chain2-old"]}
    write_set(tmp_path, "chain2-recent", recent)
    write_set(tmp_path, "chain2-succ",
              successor_docs("chain2-succ", ["chain2-recent"], full_closure()))
    assert [f.code for f in repo_l10(tmp_path)] == []


def test_an_approved_set_on_the_route_is_not_an_undeclared_predecessor(tmp_path):
    write_set(tmp_path, "appr-ref", valid_docs("appr-ref"))          # approved, route board.html
    write_set(tmp_path, "appr-pred", predecessor_docs("appr-pred"))
    write_set(tmp_path, "appr-succ",
              successor_docs("appr-succ", ["appr-pred"], full_closure()))
    fired = {(f.code, f.subject) for f in repo_l10(tmp_path)}
    assert ("undeclared-predecessor", "appr-succ:appr-ref") not in fired, sorted(fired)


def test_a_historical_record_is_not_made_to_declare_its_own_siblings(tmp_path):
    """Non-retroactive: two terminal sets that claim no lineage are records, not successors."""
    write_set(tmp_path, "hist-a", predecessor_docs("hist-a"))
    write_set(tmp_path, "hist-b", predecessor_docs("hist-b"))
    assert [f.code for f in repo_l10(tmp_path)] == []


def test_a_set_on_a_different_route_is_not_a_predecessor(tmp_path):
    other = predecessor_docs("other-route")
    other["manifest.yml"]["surface"]["route"] = "macro.html"
    write_set(tmp_path, "other-route", other)
    write_set(tmp_path, "route3-succ", successor_docs("route3-succ", [], None, status="draft"))
    assert [f.code for f in repo_l10(tmp_path)] == []


# ── Arming (RIG §13.4) ────────────────────────────────────────────────────────

def test_the_continuity_group_is_armed_at_every_status_but_superseded():
    for status in ("draft", "in_review", "revise", "rejected", "approved"):
        assert RIG.GROUP_CONTINUITY in RIG.STATUS_GROUPS[status], status
    assert RIG.GROUP_CONTINUITY not in RIG.STATUS_GROUPS["superseded"]
    assert RIG.GROUP_CONTINUITY in RIG.ALL_GROUPS


@pytest.mark.parametrize("status", ["draft", "in_review", "revise", "rejected"])
def test_a_dropped_item_fires_at_every_pre_approval_status(tmp_path, status):
    kept = [row for row in full_closure() if row["id"] == "PRC-201"]
    fired = continuity_codes(tmp_path, f"arm-{status}", kept, status=status,
                             with_receipts=status in {"revise", "rejected"})
    assert "continuity-item-missing" in fired, sorted(fired)


def test_the_completeness_group_still_waits_for_a_terminal_status(tmp_path):
    """The asymmetry is the point: continuity admits, completeness judges."""
    fired = continuity_codes(tmp_path, "arm-draft-complete", full_closure(), status="draft")
    assert "missing-artifact-file" not in fired, sorted(fired)
    assert "missing-review-receipt" not in fired, sorted(fired)


# ── Partial / stray directories must not crash the walk ───────────────────────

def test_a_directory_holding_only_a_continuity_file_is_skipped(tmp_path, capsys):
    """The r3 half-set on main today: continuity.yml lands with the gate, manifest with #5552."""
    write_set(tmp_path, "synthetic-ref", valid_docs("synthetic-ref"))
    stray = tmp_path / "research" / "reference_integrity" / "half-landed"
    stray.mkdir(parents=True)
    (stray / "continuity.yml").write_text(
        yaml.safe_dump({"schema": "mastermind.rig_continuity.v1",
                        "reference_id": "half-landed",
                        "predecessors": [{"reference_id": "nowhere", "verdict": "REVISE",
                                          "source": "snapshot", "source_ref": "PR #5533",
                                          "closure": []}]}),
        encoding="utf-8",
    )
    assert [a.reference_id for a in RIG.discover_artifact_sets(tmp_path)] == ["synthetic-ref"]
    assert RIG.main(["--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "::error" not in out, out


def test_the_real_half_landed_r3_directory_does_not_break_repo_mode(capsys):
    """Belt and braces on the checkout itself: repo mode over ROOT stays green."""
    assert RIG.main(["--root", str(ROOT)]) == 0, capsys.readouterr().out


# ── --mandate: derived, not hand-written (RIG §13.5) ──────────────────────────

def test_mandate_derives_every_open_item_from_the_predecessor_record(tmp_path, capsys):
    write_set(tmp_path, "md-pred", predecessor_docs("md-pred"))
    write_set(tmp_path, "md-succ", successor_docs("md-succ", ["md-pred"], None))
    exit_code = RIG.main(["--root", str(tmp_path), "--mandate", "md-succ"])
    out = capsys.readouterr().out
    assert exit_code == 0, out

    derived = yaml.safe_load(out)
    assert derived["schema"] == "mastermind.rig_continuity.v1"
    assert derived["reference_id"] == "md-succ"
    block = derived["predecessors"][0]
    assert block["reference_id"] == "md-pred"
    assert block["source"] == "on_disk"
    rows = block["closure"]
    assert {row["id"] for row in rows} == {"PRC-201", *THE_FOUR_OMISSIONS}
    assert {row["disposition"] for row in rows} == {"<REQUIRED>"}
    assert all(row.get("predecessor_note") for row in rows), \
        "the predecessor's own note is the context a builder needs"
    assert "PRC-202" not in {row["id"] for row in rows}, "already closed in the predecessor"


def test_the_derived_skeleton_is_not_itself_a_passing_artifact(tmp_path, capsys):
    """``<REQUIRED>`` must fail the enum — an unfilled mandate is a work order, not a record."""
    write_set(tmp_path, "md2-pred", predecessor_docs("md2-pred"))
    write_set(tmp_path, "md2-succ", successor_docs("md2-succ", ["md2-pred"], None))
    RIG.main(["--root", str(tmp_path), "--mandate", "md2-succ"])
    derived = yaml.safe_load(capsys.readouterr().out)
    docs = successor_docs("md2-succ", ["md2-pred"], derived["predecessors"][0]["closure"])
    write_set(tmp_path, "md2-succ", docs)
    fired = codes(tmp_path, "md2-succ")
    assert "continuity-invalid-disposition" in fired, sorted(fired)
    assert "continuity-item-missing" not in fired, "the skeleton is complete, just unfilled"


def test_mandate_exits_four_when_the_predecessor_is_not_on_disk(tmp_path, capsys):
    write_set(tmp_path, "md3-succ", successor_docs("md3-succ", ["md3-not-here"], None))
    exit_code = RIG.main(["--root", str(tmp_path), "--mandate", "md3-succ"])
    out = capsys.readouterr().out
    assert exit_code == 4, out
    assert "Traceback" not in out
    annotations = [line for line in out.splitlines() if line.startswith("::")]
    assert annotations, out
    assert "continuity-snapshot-without-source" in annotations[0]
    assert "snapshot" in out


def test_mandate_on_an_unknown_reference_id_exits_one(tmp_path, capsys):
    assert RIG.main(["--root", str(tmp_path), "--mandate", "no-such-ref"]) == 1
    assert "missing-artifact-file" in capsys.readouterr().out


def test_every_mandate_annotation_starts_its_line(tmp_path, capsys):
    write_set(tmp_path, "md4-succ", successor_docs("md4-succ", ["md4-not-here"], None))
    RIG.main(["--root", str(tmp_path), "--mandate", "md4-succ"])
    for line in capsys.readouterr().out.splitlines():
        if "::error" in line or "::notice" in line:
            assert line.startswith("::"), f"annotation does not start its line: {line!r}"


def test_continuity_annotations_start_their_line(tmp_path, capsys):
    kept = [row for row in full_closure() if row["id"] == "PRC-201"]
    write_set(tmp_path, "line-pred", predecessor_docs("line-pred", bare_conditions=True))
    write_set(tmp_path, "line-succ", successor_docs("line-succ", ["line-pred"], kept))
    RIG.main(["--root", str(tmp_path)])
    lines = capsys.readouterr().out.splitlines()
    marked = [line for line in lines if "::error" in line or "::notice" in line]
    assert marked
    for line in marked:
        assert line.startswith("::"), f"annotation does not start its line: {line!r}"


def test_a_continuity_file_with_the_wrong_schema_id_fires(tmp_path):
    docs = successor_docs("schema-succ", ["schema-pred"], full_closure(),
                          source="snapshot", source_ref="PR #1")
    docs["continuity.yml"]["schema"] = "mastermind.rig_continuity.v2"
    write_set(tmp_path, "schema-pred", predecessor_docs("schema-pred"))
    write_set(tmp_path, "schema-succ", docs)
    fired = codes(tmp_path, "schema-succ")
    assert "invalid-schema" in fired, sorted(fired)
