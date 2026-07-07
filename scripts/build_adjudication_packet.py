"""
scripts/build_adjudication_packet.py — Generate an adjudication packet skeleton
and append it (idempotently) to the adjudication queue.

Purpose
-------
Implements the packet-generation side of the post-Fable adjudication bench
(RUL-SUCC-1..12, ratified 2026-07-06).  Given a title and decision class, the
script stamps the correct tier, fills allowed/blocked outcomes, optionally
autofills case-law ruling hits from the ruling index, and appends the packet
to the queue file.

Schema version: neuralweb.adjudication_packet.v1

Usage
-----
  python scripts/build_adjudication_packet.py
      --title TEXT             (required)
      --decision-class CLASS   (required; see DECISION_CLASS_TIER below)
      --requested-decision TEXT (required)
      --source-doc TEXT        (optional)
      --source-pr INT          (optional)
      --owner-program TEXT     (optional)
      --created-by ACTOR       (default: operator)
      --as-of DATE             (required; YYYY-MM-DD; used in packet_id)
      --keywords COMMA_LIST    (optional; grep ruling_index.json context lines)
      --touched-path PATH      (repeatable; populates scope.touched_paths)
      --queue PATH             (default: data/neuralweb/adjudication_queue.json)
      --dry-run                (print packet JSON; no write)
      --selftest               (run hermetic self-test; exit 0 on pass)

Exit codes
----------
  0 : Success.
  1 : Argument error, missing file, or selftest failure.

Decision class → tier mapping (built-in copy, source of truth: RUL-SUCC-1..12)
--------------------------------------------------------------------------------
  t0 (routine — no packet required; for reference only):
    rf_gate_clean_caselaw, doc_only_merge, display_only_change,
    taxonomy_with_precedent, send_to_review, return_for_evidence

  t1 (consequential — packet required; opus or operator decides):
    scoped_build, retire, new_fdr_family_within_program,
    comeback_clock_move_gt_90d, taxonomy_no_precedent,
    cross_program_ownership, ops_budget_within_render

  t2 (constitutional — packet + refute-panel >=2 + operator sign-off):
    new_lobe_charter, two_lobe_cap_exception,
    authority_promotion_above_A2, scored_path_behavior_change,
    fdr_family_cross_program, qledger_grading_semantics,
    held_book_fill_schema, public_private_boundary,
    public_write_endpoint, mastermind_trading_authority,
    cortex_budget_increase, article_2_3_amendment
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent

_DEFAULT_QUEUE_REL = "data/neuralweb/adjudication_queue.json"
_DEFAULT_INDEX_REL = "data/neuralweb/ruling_index.json"

# ---------------------------------------------------------------------------
# Decision class → tier mapping
# ---------------------------------------------------------------------------

_T0_CLASSES = frozenset({
    "rf_gate_clean_caselaw",
    "doc_only_merge",
    "display_only_change",
    "taxonomy_with_precedent",
    "send_to_review",
    "return_for_evidence",
})

_T1_CLASSES = frozenset({
    "scoped_build",
    "retire",
    "new_fdr_family_within_program",
    "comeback_clock_move_gt_90d",
    "taxonomy_no_precedent",
    "cross_program_ownership",
    "ops_budget_within_render",
})

_T2_CLASSES = frozenset({
    "new_lobe_charter",
    "two_lobe_cap_exception",
    "authority_promotion_above_A2",
    "scored_path_behavior_change",
    "fdr_family_cross_program",
    "qledger_grading_semantics",
    "held_book_fill_schema",
    "public_private_boundary",
    "public_write_endpoint",
    "mastermind_trading_authority",
    "cortex_budget_increase",
    "article_2_3_amendment",
})

_ALL_CLASSES = _T0_CLASSES | _T1_CLASSES | _T2_CLASSES

_MAX_KEYWORD_HITS = 15


def _tier_for_class(decision_class: str) -> int:
    """Return 0, 1, or 2 for the given decision class. Raises ValueError if unknown."""
    if decision_class in _T0_CLASSES:
        return 0
    if decision_class in _T1_CLASSES:
        return 1
    if decision_class in _T2_CLASSES:
        return 2
    raise ValueError(
        f"Unknown decision class {decision_class!r}. "
        f"Valid classes: {sorted(_ALL_CLASSES)}"
    )


# ---------------------------------------------------------------------------
# Slug helper
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    """Convert title text to a URL-safe slug (lowercase, hyphens, no specials)."""
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:60]  # cap length


# ---------------------------------------------------------------------------
# Keyword autofill from ruling index
# ---------------------------------------------------------------------------

def _autofill_rulings(
    keywords: list[str],
    index_path: Path,
) -> list[str]:
    """
    Grep ruling_index.json context lines case-insensitively for any keyword.
    Returns up to _MAX_KEYWORD_HITS sorted, distinct ruling IDs.
    """
    if not index_path.exists():
        return []

    try:
        with open(index_path, encoding="utf-8") as fh:
            idx = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return []

    kw_lower = [k.lower().strip() for k in keywords if k.strip()]
    if not kw_lower:
        return []

    hit_ids: set[str] = set()
    for ruling in idx.get("rulings", []):
        rid = ruling.get("id", "")
        if not rid:
            continue
        # Check each file's context line
        for file_entry in ruling.get("files", []):
            ctx = (file_entry.get("context") or "").lower()
            if any(kw in ctx for kw in kw_lower):
                hit_ids.add(rid)
                break
        # Also check the id itself
        rid_lower = rid.lower()
        if any(kw in rid_lower for kw in kw_lower):
            hit_ids.add(rid)

    return sorted(hit_ids)[:_MAX_KEYWORD_HITS]


# ---------------------------------------------------------------------------
# Packet builder
# ---------------------------------------------------------------------------

def _build_packet(
    *,
    title: str,
    decision_class: str,
    requested_decision: str,
    as_of: str,
    source_doc: str | None = None,
    source_pr: int | None = None,
    owner_program: str | None = None,
    created_by: str = "operator",
    keywords: list[str] | None = None,
    touched_paths: list[str] | None = None,
    index_path: Path | None = None,
) -> dict[str, Any]:
    """
    Build and return a packet dict (neuralweb.adjudication_packet.v1).
    Does not write anything.
    """
    tier = _tier_for_class(decision_class)
    slug = _slugify(title)
    packet_id = f"adj-{as_of}-{slug}"

    # Case-law autofill
    ruling_hits: list[str] = []
    if keywords and index_path:
        ruling_hits = _autofill_rulings(keywords, index_path)

    # Outcome rules by tier
    if tier == 2:
        allowed_outcomes = ["defer", "send_to_review"]
        blocked_outcomes = [requested_decision]
    elif tier == 1:
        # Deduplicate while preserving order (requested_decision may be "defer")
        seen: set[str] = set()
        allowed_outcomes = []
        for outcome in [requested_decision, "defer", "reject"]:
            if outcome not in seen:
                allowed_outcomes.append(outcome)
                seen.add(outcome)
        blocked_outcomes = []
    else:  # t0
        allowed_outcomes = [requested_decision]
        blocked_outcomes = []

    # Authority ceiling by tier
    ceiling_map = {0: "sonnet", 1: "opus", 2: "operator"}
    current_ceiling = ceiling_map[tier]

    packet: dict[str, Any] = {
        "schema": "neuralweb.adjudication_packet.v1",
        "packet_id": packet_id,
        "tier": tier,
        "created_at": f"{as_of}T00:00:00Z",
        "created_by": created_by,
        "request": {
            "title": title,
            "requested_decision": requested_decision,
            "decision_class": decision_class,
            "source_doc": source_doc,
            "source_pr": source_pr,
        },
        "scope": {
            "owner_program": owner_program,
            "proposed_classification": None,
            "touched_artifacts": [],
            "touched_paths": sorted(touched_paths) if touched_paths else [],
        },
        "case_law": {
            "ruling_hits": ruling_hits,
            "duplicate_risk": "low",
            "deferred_or_killed_hits": [],
        },
        "authority": {
            "current_ceiling": current_ceiling,
            "requested_ceiling": current_ceiling,
            "article2_surfaces_touched": [],
            "nondelegable": tier == 2,
            # HB-11 floor fields — fill when ceiling changes or article2 surfaces touched
            "article_citation": None,
            "article3_evidence": {
                "n": None,
                "hits": None,
                "wilson_lb": None,
                "staleness_days": None,
            },
        },
        "privacy": {
            "privacy_class": "public_research",
            "public_paths_touched": [],
            "private_fields": [],
            # HB-12 floor field — must be true when touching private data
            "mastermind_booleans_unchanged": None,
        },
        "statistics": {
            "fdr_family": None,
            "trial_budget_change": False,
            "evidence_floor_met": False,
            "outcome_data_seen": False,
            "preregistration_ref": None,
        },
        "clocks": {
            "come_back_on": None,
            "due_status": "not_clocked",
        },
        "build_collision": {
            "open_prs_touching_paths": [],
            "owner_conflicts": [],
        },
        "review": {
            "required_lenses": ["opus"] if tier >= 1 else [],
            "opus_findings": [],
            "panel": [],
        },
        "allowed_outcomes": allowed_outcomes,
        "blocked_outcomes": blocked_outcomes,
        "escalation": {
            "opened_on": as_of,
            "stale_after_days": 14,
            "escalated": False,
        },
        "decision": {
            "outcome": None,
            "decided_by": None,
            "actor_ref": None,
            "rationale": None,
            "decided_on": None,
        },
    }

    return packet


# ---------------------------------------------------------------------------
# Queue helpers
# ---------------------------------------------------------------------------

def _load_queue(queue_path: Path) -> dict[str, Any]:
    """Load existing queue or return a fresh skeleton."""
    if queue_path.exists():
        try:
            with open(queue_path, encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            pass

    return {
        "schema": "neuralweb.adjudication_queue.v1",
        "updated_at": "2026-07-06",
        "law": (
            "packets are the audit trail for tier>=1 decisions; "
            "check via scripts/check_adjudication_packet.py"
        ),
        "packets": [],
    }


def _append_to_queue(
    queue: dict[str, Any],
    packet: dict[str, Any],
    as_of: str,
) -> tuple[dict[str, Any], bool]:
    """
    Idempotently insert/replace packet in queue by packet_id.
    Returns (updated_queue, replaced: bool).
    """
    packet_id = packet["packet_id"]
    packets = queue.get("packets") or []

    replaced = False
    new_packets = []
    for existing in packets:
        if existing.get("packet_id") == packet_id:
            replaced = True
            new_packets.append(packet)
        else:
            new_packets.append(existing)

    if not replaced:
        new_packets.append(packet)

    queue = dict(queue)
    queue["packets"] = new_packets
    queue["updated_at"] = as_of
    return queue, replaced


# ---------------------------------------------------------------------------
# Selftest
# ---------------------------------------------------------------------------

def _run_selftest() -> int:
    """Hermetic self-test using temp directories. Returns 0 on pass, 1 on failure."""
    print("Running build_adjudication_packet selftest...")
    all_passed = True

    def _fail(msg: str) -> None:
        nonlocal all_passed
        all_passed = False
        print(f"  [FAIL] {msg}")

    def _pass(msg: str) -> None:
        print(f"  [PASS] {msg}")

    # --- Test 1: tier mapping ---
    for cls in _T1_CLASSES:
        assert _tier_for_class(cls) == 1, f"{cls} should be t1"
    for cls in _T2_CLASSES:
        assert _tier_for_class(cls) == 2, f"{cls} should be t2"
    _pass("tier mapping for all t1 and t2 classes")

    # --- Test 2: t1 packet shape ---
    p1 = _build_packet(
        title="Test t1 packet",
        decision_class="scoped_build",
        requested_decision="scoped_build",
        as_of="2026-07-06",
        owner_program="test-program",
    )
    if p1["tier"] != 1:
        _fail(f"t1 packet tier={p1['tier']} expected 1")
    else:
        _pass("t1 packet tier=1")
    if "scoped_build" not in p1["allowed_outcomes"]:
        _fail("t1: requested_decision not in allowed_outcomes")
    else:
        _pass("t1: requested_decision in allowed_outcomes")
    if p1["blocked_outcomes"]:
        _fail(f"t1: blocked_outcomes should be empty, got {p1['blocked_outcomes']}")
    else:
        _pass("t1: blocked_outcomes empty")
    if p1["schema"] != "neuralweb.adjudication_packet.v1":
        _fail("t1: wrong schema")
    else:
        _pass("t1: schema correct")

    # --- Test 3: t2 packet shape ---
    p2 = _build_packet(
        title="New lobe charter request",
        decision_class="new_lobe_charter",
        requested_decision="charter",
        as_of="2026-07-06",
    )
    if p2["tier"] != 2:
        _fail(f"t2 packet tier={p2['tier']} expected 2")
    else:
        _pass("t2 packet tier=2")
    if "charter" not in p2["blocked_outcomes"]:
        _fail("t2: requested_decision 'charter' not in blocked_outcomes")
    else:
        _pass("t2: requested_decision in blocked_outcomes")
    if set(p2["allowed_outcomes"]) != {"defer", "send_to_review"}:
        _fail(f"t2: allowed_outcomes={p2['allowed_outcomes']} expected [defer, send_to_review]")
    else:
        _pass("t2: allowed_outcomes correct")
    if p2["authority"]["nondelegable"] is not True:
        _fail("t2: nondelegable should be True")
    else:
        _pass("t2: nondelegable=True")

    # --- Test 4: idempotent queue append ---
    with tempfile.TemporaryDirectory() as tmpdir:
        qpath = Path(tmpdir) / "test_queue.json"

        q = _load_queue(qpath)
        packet_a = _build_packet(
            title="Idempotent test packet",
            decision_class="scoped_build",
            requested_decision="scoped_build",
            as_of="2026-07-06",
        )
        q, replaced = _append_to_queue(q, packet_a, "2026-07-06")
        if replaced:
            _fail("first insert should not replace")
        else:
            _pass("first insert: replaced=False")

        # Re-append same packet_id — should replace
        q, replaced = _append_to_queue(q, packet_a, "2026-07-06")
        if not replaced:
            _fail("second insert with same packet_id should replace")
        else:
            _pass("idempotent re-append: replaced=True")

        # Queue should still have exactly 1 packet
        if len(q["packets"]) != 1:
            _fail(f"queue should have 1 packet after idempotent re-append, got {len(q['packets'])}")
        else:
            _pass("queue length=1 after idempotent re-append")

    # --- Test 5: ruling index selftest via subprocess ---
    import subprocess
    repo_root = _REPO_ROOT
    ruling_script = repo_root / "scripts" / "build_ruling_index.py"
    if ruling_script.exists():
        result = subprocess.run(
            [sys.executable, str(ruling_script), "--as-of", "2026-07-06", "--selftest"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            _fail(f"build_ruling_index --selftest exited {result.returncode}:\n{result.stdout}\n{result.stderr}")
        else:
            _pass("build_ruling_index --selftest exit 0")
    else:
        _fail(f"build_ruling_index.py not found at {ruling_script}")

    # --- Test 6: keyword autofill against synthetic index ---
    with tempfile.TemporaryDirectory() as tmpdir:
        idx_path = Path(tmpdir) / "ruling_index.json"
        synthetic_index = {
            "schema": "neuralweb.ruling_index.v1",
            "built_from": "research/**/*.md",
            "as_of": "2026-07-06",
            "n_rulings": 3,
            "rulings": [
                {
                    "id": "RUL-SUCC-1",
                    "files": [{"path": "research/doc.md", "first_line_no": 1, "context": "macro context rail ownership"}],
                    "n_mentions": 1,
                    "truncated": False,
                },
                {
                    "id": "DT-R14",
                    "files": [{"path": "research/doc.md", "first_line_no": 5, "context": "era-split law ratified"}],
                    "n_mentions": 1,
                    "truncated": False,
                },
                {
                    "id": "LH-R11",
                    "files": [{"path": "research/doc.md", "first_line_no": 9, "context": "long hold thesis ratified"}],
                    "n_mentions": 1,
                    "truncated": False,
                },
            ],
        }
        with open(idx_path, "w", encoding="utf-8") as fh:
            json.dump(synthetic_index, fh)

        hits = _autofill_rulings(["macro", "context"], idx_path)
        if "RUL-SUCC-1" not in hits:
            _fail(f"keyword 'macro' should match RUL-SUCC-1, got {hits}")
        else:
            _pass(f"keyword autofill matched RUL-SUCC-1 (hits={hits})")

        # Keyword that matches nothing
        hits2 = _autofill_rulings(["xyznonexistent"], idx_path)
        if hits2:
            _fail(f"keyword 'xyznonexistent' should produce no hits, got {hits2}")
        else:
            _pass("keyword autofill returns empty list for non-matching keyword")

    print()
    if all_passed:
        print("selftest PASSED — all checks green")
        return 0
    else:
        print("selftest FAILED — one or more checks failed")
        return 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    # Pre-check for --selftest before argparse sees required args.
    # This mirrors the pattern in check_synapse_registry.py where --selftest
    # is a standalone mode that does not need the other required arguments.
    if "--selftest" in sys.argv:
        return _run_selftest()

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--title", required=True, help="Packet title (human-readable)")
    parser.add_argument(
        "--decision-class",
        required=True,
        dest="decision_class",
        choices=sorted(_ALL_CLASSES),
        help="Decision class (determines tier)",
    )
    parser.add_argument(
        "--requested-decision",
        required=True,
        dest="requested_decision",
        help="The decision being requested",
    )
    parser.add_argument("--source-doc", dest="source_doc", default=None)
    parser.add_argument("--source-pr", dest="source_pr", type=int, default=None)
    parser.add_argument("--owner-program", dest="owner_program", default=None)
    parser.add_argument("--created-by", dest="created_by", default="operator")
    parser.add_argument(
        "--as-of",
        required=True,
        dest="as_of",
        help="ISO date (YYYY-MM-DD); used in packet_id and escalation.opened_on",
    )
    parser.add_argument(
        "--keywords",
        default=None,
        help="Comma-separated keywords; grep ruling_index context lines for autofill",
    )
    parser.add_argument(
        "--touched-path",
        action="append",
        dest="touched_paths",
        default=[],
        metavar="PATH",
        help="Repo-relative path touched by this decision (repeatable)",
    )
    parser.add_argument(
        "--queue",
        type=Path,
        default=None,
        help=f"Queue file path (default: <root>/{_DEFAULT_QUEUE_REL})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Print packet JSON; do not write",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="Run selftest; exit 0 on pass",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=_REPO_ROOT,
        help="Repo root (default: parent of scripts/)",
    )
    args = parser.parse_args()

    if args.selftest:
        return _run_selftest()

    root = args.root.resolve()
    queue_path = args.queue if args.queue else root / _DEFAULT_QUEUE_REL
    index_path = root / _DEFAULT_INDEX_REL

    keywords = [k.strip() for k in args.keywords.split(",")] if args.keywords else []

    try:
        packet = _build_packet(
            title=args.title,
            decision_class=args.decision_class,
            requested_decision=args.requested_decision,
            as_of=args.as_of,
            source_doc=args.source_doc,
            source_pr=args.source_pr,
            owner_program=args.owner_program,
            created_by=args.created_by,
            keywords=keywords,
            touched_paths=args.touched_paths,
            index_path=index_path,
        )
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(json.dumps(packet, indent=2, ensure_ascii=False))
        return 0

    queue = _load_queue(queue_path)
    queue, replaced = _append_to_queue(queue, packet, args.as_of)

    if replaced:
        print(f"[NOTICE] packet {packet['packet_id']!r} already existed — replaced in queue")

    queue_path = Path(queue_path)
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with open(queue_path, "w", encoding="utf-8") as fh:
        json.dump(queue, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    action = "replaced" if replaced else "appended"
    print(
        f"packet {packet['packet_id']!r} {action} in queue "
        f"({queue_path}; tier={packet['tier']}, class={packet['request']['decision_class']!r})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
