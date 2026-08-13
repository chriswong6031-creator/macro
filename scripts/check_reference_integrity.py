"""scripts/check_reference_integrity.py — mechanical enforcement for the Reference Integrity Gate.

Law: ``research/REFERENCE_INTEGRITY_GATE_V1.md`` (RIG V1).  Registered in
``config/house_law_checks.yml`` as ``design.reference_integrity``.

WHAT THIS GATE IS FOR
    A redesign can be mechanically correct, design-system compliant, semantically
    consistent, responsive, bilingual, fully tested — and still make the product
    substantially worse.  The failure mode is *reference laundering*: a bad product
    decision becomes a reference, the reference becomes law, builders reproduce it
    faithfully, and the regression is institutionalized.

    CI cannot judge taste and this script does not pretend to.  It enforces that the
    product/taste judgment HAPPENED, in the right order, independently, and left
    auditable receipts.  Every finding is a missing receipt, a broken ordering, or an
    unadjudicated block — never an opinion about the design.

RULE LEVELS (RIG §8).  Each rule prints a STABLE finding code; tests pin the strings.
    L1  artifact completeness / schema      missing-artifact-file, invalid-schema,
                                            invalid-status, invalid-enum,
                                            missing-baseline-evidence,
                                            missing-verdict-question
    L2  capability ledger integrity (§5)    duplicate-capability-id, missing-disposition,
                                            dangling-disposition, invalid-disposition,
                                            remove-without-rationale,
                                            remove-without-user-job-impact,
                                            remove-without-superiority-case,
                                            remove-without-approval-ref,
                                            relocate-without-destination,
                                            relocate-without-reachability,
                                            retain-without-target,
                                            improve-without-rationale
    L3  blocked-data honesty (§1)           blocked-data-without-dependency,
                                            blocked-data-without-escalation,
                                            blocked-data-without-interim,
                                            blocked-data-as-removal
    L4  regression explicitness (§6)        missing-task-matrix, invalid-task-verdict,
                                            worse-core-task-unadjudicated,
                                            missing-authority-delta,
                                            unwarranted-authority-unadjudicated
    L5  review integrity (§6)               missing-review-receipt,
                                            reviewer-not-independent,
                                            missing-quarantine-attestation,
                                            second-pass-before-freeze,
                                            stale-review-receipt
    L6  approval integrity (§7)             approved-with-unresolved-block (a surviving
                                            blocker resolved only as ``upheld_revise`` is
                                            still unresolved FOR APPROVAL — §7 defines that
                                            resolution as driving REVISE/REJECT),
                                            approved-without-receipt,
                                            override-without-finding-id,
                                            override-without-justification,
                                            approved-with-wrong-verdict,
                                            lightweight-attestation-missing,
                                            lightweight-cites-unapproved-archetype
                                            superseded-without-successor
    L7  reference-namespace closure         unclaimed-reference-file,
                                            double-claimed-reference-file
    L8  migration-packet coupling           packet-without-rig-receipt,
                                            packet-cites-unapproved-reference
    L9  page-registry coupling              compliant-row-without-approved-reference,
                                            missing-registry-file

STATUS-SCALED VALIDATION (repo mode).  Mid-flight work is legal; a terminal state is not
allowed to be a claim with no record.
    draft | in_review  — whatever exists must PARSE and be internally valid (schemas,
                         enums, no duplicate/dangling ledger ids).  Completeness is NOT
                         required: a half-written proposal is a legal draft.
    revise | rejected  — the review receipts and the verdict packet are REQUIRED (a
                         terminal verdict with no recorded review is illegal), and the
                         record's own integrity is enforced (L5).  The ledger's
                         substantive findings legitimately stay unresolved-as-upheld —
                         that record IS the artifact — so L2/L3/L4/L6 do not fire.
    approved           — EVERYTHING holds: full L1-L6, approval.yml present, zero
                         unresolved blockers, receipts' artifact_sha == frozen_sha.
    superseded         — the manifest must name its successor_reference_id.
``--evaluate`` runs the full L1-L6 set regardless of status: "could this be approved
right now?"  Every reason it could not is printed as a code.

THE BLOCKED-DATA HEURISTIC AND ITS FALSE-POSITIVE POSTURE (RIG §1)
    ``blocked-data-as-removal`` fires when a ``REMOVE`` disposition's rationale reads as
    data-motivated: any of (case-insensitive) "coverage", "enrichment", "data availab",
    "missing data", "sparse", "incomplete", "rows (", "% of rows", a ``join`` word, or an
    N/M row fraction (``45/179``).  This is lexical and therefore approximate.

    It is enforcement, not noise.  By law a removal motivated by data insufficiency is
    DEFINITIONALLY a mis-filed ``BLOCKED_DATA``: "if only 25% of rows have chart
    enrichment, the legal output is BLOCKED_DATA — chart enrichment incomplete, escalated
    as a data-dependency — never 'therefore redesign the flagship card without a chart'."
    So a match means one of exactly two things, and both are correct outcomes:
      (a) the removal really is data-motivated  -> re-file it as BLOCKED_DATA with its
          dependency/escalation/interim.  The gate did its job.
      (b) the rationale merely MENTIONS data while the product reason is elsewhere ->
          rewrite the rationale to state the product reason, which is what a REMOVE's
          ``superiority_case`` is for anyway.  A removal whose stated reason cannot be
          told apart from a data excuse is not yet a documented product decision.
    There is deliberately no allowlist: an exemption file would re-open the exact laundering
    path (§1) this rule closes.

NO SUBPROCESS.  This guard reads the checkout with the filesystem and PyYAML only —
its scan roots (research/reference_integrity, research/migration_packets,
mockups/design_system, config+data/product_experience) are its scope.

ANNOTATIONS.  Every ``::error`` / ``::notice`` is emitted with a bare ``print(...,
flush=True)`` at line start — never through a logger, which would prefix the line and
make GitHub silently drop it (house annotation law; tests/test_gh_annotation_line_start.py).

Usage:
    python3 scripts/check_reference_integrity.py                  # repo mode  (exit 0/1)
    python3 scripts/check_reference_integrity.py --evaluate <id>  # gate mode  (exit 0/3)
    python3 scripts/check_reference_integrity.py --selftest       # hermetic   (exit 0/1)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent

# ── Repo-relative scan roots ──────────────────────────────────────────────────
RIG_ROOT = "research/reference_integrity"
PACKET_ROOT = "research/migration_packets"
DESIGN_SYSTEM_ROOT = "mockups/design_system"
REGISTRY_OVERRIDES = "config/product_experience/page_registry_overrides.yml"
REGISTRY_JSON = "data/product_experience/page_registry.json"

# Directories under RIG_ROOT that are not artifact sets.
NON_ARTIFACT_DIRS = frozenset({"templates"})

# RIG §8 L7: the closed pre-RIG reference list.  Wave-0 references commissioned before
# this law; they stay provisional until their artifact sets are backfilled, which their
# first consuming packet owns.  specimen.html is the design-system specimen, not a
# reference.
CLOSED_PRE_RIG_REFERENCES = frozenset({
    "macro_reference.html",
    "today_reference.html",
    "utility_reference.html",
})
NAMESPACE_EXEMPT = CLOSED_PRE_RIG_REFERENCES | {"specimen.html"}

# ── Vocabularies (RIG §1-§7).  Unknown ENUMS fail; unknown top-level KEYS are
# tolerated on purpose, so a later schema revision can add fields without a flag day. ──
SCHEMA_IDS = {
    "manifest": "mastermind.rig_manifest.v1",
    "baseline": "mastermind.rig_baseline.v1",
    "proposal": "mastermind.rig_proposal.v1",
    "review": "mastermind.rig_review.v1",
    "verdict": "mastermind.rig_verdict.v1",
    "approval": "mastermind.rig_approval.v1",
}
STATUSES = frozenset({"draft", "in_review", "approved", "revise", "rejected", "superseded"})
SCOPES = frozenset({"full", "lightweight"})
DISPOSITIONS = frozenset({"RETAIN", "IMPROVE", "RELOCATE", "REMOVE", "BLOCKED_DATA"})
IMPORTANCES = frozenset({"core", "supporting", "peripheral"})
TASK_VERDICTS = frozenset({"BETTER", "EQUIVALENT", "WORSE", "UNKNOWN"})
AUTHORITY_DIRECTIONS = frozenset({"stronger", "equal", "weaker"})
REVIEW_ROLES: tuple[str, ...] = ("product_regression", "visual_taste")
SEVERITIES = frozenset({"blocker", "major", "minor"})
REVIEW_VERDICTS = frozenset({"PASS", "PASS_WITH_CONDITIONS", "BLOCK"})
AMENDMENT_ACTIONS = frozenset({"upheld", "downgraded", "withdrawn"})
VERDICTS = frozenset({"APPROVE_REFERENCE", "APPROVE_WITH_CONDITIONS", "REVISE", "REJECT"})
APPROVING_VERDICTS = frozenset({"APPROVE_REFERENCE", "APPROVE_WITH_CONDITIONS"})
RESOLUTIONS = frozenset({"upheld_revise", "resolved_by_change", "overridden"})
# ...of which only these two are compatible with APPROVING the reference.  ``upheld_revise``
# is a validly RECORDED resolution, but RIG §7 defines it as the one that "drives
# REVISE/REJECT" — an approved status carrying an upheld blocker is a block that
# disappeared silently, which is exactly what §7 forbids.
APPROVAL_COMPATIBLE_RESOLUTIONS = frozenset({"resolved_by_change", "overridden"})

# RIG §7 — all eight verdict-packet answers are required, non-empty.
PACKET_KEYS: tuple[str, ...] = (
    "materially_improved",
    "materially_worsened",
    "disappeared",
    "behavior_harder",
    "stronger_claims",
    "intent_vs_convenience",
    "production_preferable_for",
    "strongest_argument_against",
)

# ── Rule groups, and which statuses arm them (see module docstring) ───────────
GROUP_SCHEMA = "schema"
GROUP_COMPLETENESS = "completeness"
GROUP_LEDGER = "ledger"
GROUP_REGRESSION = "regression"
GROUP_REVIEW = "review"
GROUP_APPROVAL = "approval"

ALL_GROUPS = frozenset({
    GROUP_SCHEMA, GROUP_COMPLETENESS, GROUP_LEDGER,
    GROUP_REGRESSION, GROUP_REVIEW, GROUP_APPROVAL,
})

STATUS_GROUPS: dict[str, frozenset[str]] = {
    "draft": frozenset({GROUP_SCHEMA}),
    "in_review": frozenset({GROUP_SCHEMA}),
    "superseded": frozenset({GROUP_SCHEMA}),
    "revise": frozenset({GROUP_SCHEMA, GROUP_COMPLETENESS, GROUP_REVIEW}),
    "rejected": frozenset({GROUP_SCHEMA, GROUP_COMPLETENESS, GROUP_REVIEW}),
    "approved": ALL_GROUPS,
}

# ── The blocked-data lexical heuristic (documented at length in the docstring) ─
_DATA_MOTIVE_SUBSTRINGS: tuple[str, ...] = (
    "coverage",
    "enrichment",
    "data availab",
    "missing data",
    "sparse",
    "incomplete",
    "rows (",
    "% of rows",
)
_DATA_MOTIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bjoin(s|ed|ing)?\b", re.IGNORECASE),   # "candidate-join enrichment"
    re.compile(r"\b\d+\s*/\s*\d+\b"),                     # "45/179 plan rows"
)

_RIG_RECEIPT_RE = re.compile(r"^RIG-RECEIPT:[ \t]*(\S+)", re.MULTILINE)


# ── Findings ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Finding:
    """One rule firing.  ``(code, subject)`` is the dedupe key — printed exactly once."""

    code: str
    subject: str
    message: str

    def annotation(self) -> str:
        return f"::error title=reference-integrity::{self.code}: {self.subject} — {self.message}"


def dedupe(findings: Iterable[Finding]) -> list[Finding]:
    """Stable-order dedupe on ``(code, subject)``."""
    seen: set[tuple[str, str]] = set()
    out: list[Finding] = []
    for f in findings:
        key = (f.code, f.subject)
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def emit(findings: Sequence[Finding]) -> None:
    """Print every finding as a line-start ``::error`` annotation."""
    for f in findings:
        print(f.annotation(), flush=True)


def notice(message: str) -> None:
    print(f"::notice title=reference-integrity::{message}", flush=True)


# ── Small helpers ─────────────────────────────────────────────────────────────

def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _text(value: Any) -> str:
    """Non-empty scalar text, or '' — a blank/None/whitespace field counts as absent."""
    if isinstance(value, str):
        return value.strip()
    if value is None or isinstance(value, (dict, list, bool)):
        return ""
    return str(value).strip()


def _has(mapping: Any, key: str) -> bool:
    return bool(_text(_as_dict(mapping).get(key)))


def _top_level_dir(rel_path: str) -> str:
    return rel_path.replace("\\", "/").split("/", 1)[0]


def looks_data_motivated(rationale: str) -> bool:
    """True when a REMOVE rationale reads as data-motivated (RIG §1; see docstring)."""
    if not rationale:
        return False
    low = rationale.lower()
    if any(token in low for token in _DATA_MOTIVE_SUBSTRINGS):
        return True
    return any(pattern.search(rationale) for pattern in _DATA_MOTIVE_PATTERNS)


# ── Artifact set loading ──────────────────────────────────────────────────────

@dataclass
class ArtifactSet:
    reference_id: str
    root: Path
    repo_root: Path
    manifest: dict[str, Any] | None = None
    baseline: dict[str, Any] | None = None
    proposal: dict[str, Any] | None = None
    reviews: dict[str, dict[str, Any] | None] = field(default_factory=dict)
    verdict: dict[str, Any] | None = None
    approval: dict[str, Any] | None = None
    parse_errors: list[Finding] = field(default_factory=list)

    @property
    def status(self) -> str:
        return _text(_as_dict(self.manifest).get("status"))

    @property
    def scope(self) -> str:
        return _text(_as_dict(self.manifest).get("scope"))

    @property
    def frozen_sha(self) -> str:
        return _text(_as_dict(_as_dict(self.proposal).get("proposed_artifact")).get("frozen_sha"))

    @property
    def author_identity(self) -> str:
        return _text(_as_dict(_as_dict(self.manifest).get("author")).get("identity"))

    def rel(self, path: Path) -> str:
        try:
            return path.relative_to(self.repo_root).as_posix()
        except ValueError:
            return path.as_posix()


def _load_yaml(path: Path, repo_root: Path, errors: list[Finding]) -> dict[str, Any] | None:
    """Parse a YAML document, recording a parse/shape failure as ``invalid-schema``."""
    if not path.exists():
        return None
    try:
        rel = path.relative_to(repo_root).as_posix()
    except ValueError:
        rel = path.as_posix()
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
        errors.append(Finding("invalid-schema", rel, f"does not parse as YAML: {exc}"))
        return None
    if loaded is None:
        errors.append(Finding("invalid-schema", rel, "is empty"))
        return None
    if not isinstance(loaded, dict):
        errors.append(Finding("invalid-schema", rel, f"top level must be a mapping, got {type(loaded).__name__}"))
        return None
    return loaded


def load_artifact_set(set_dir: Path, repo_root: Path) -> ArtifactSet:
    """Read every file of one ``research/reference_integrity/<id>/`` directory."""
    aset = ArtifactSet(reference_id=set_dir.name, root=set_dir, repo_root=repo_root)
    errors = aset.parse_errors

    aset.manifest = _load_yaml(set_dir / "manifest.yml", repo_root, errors)
    files = _as_dict(_as_dict(aset.manifest).get("files"))

    baseline_name = _text(files.get("baseline")) or "baseline.yml"
    proposal_name = _text(files.get("proposal")) or "proposal.yml"
    verdict_name = _text(files.get("verdict")) or "verdict.yml"
    approval_name = _text(files.get("approval")) or "approval.yml"
    review_names = _as_dict(files.get("reviews"))

    aset.baseline = _load_yaml(set_dir / baseline_name, repo_root, errors)
    aset.proposal = _load_yaml(set_dir / proposal_name, repo_root, errors)
    aset.verdict = _load_yaml(set_dir / verdict_name, repo_root, errors)
    aset.approval = _load_yaml(set_dir / approval_name, repo_root, errors)

    for role in REVIEW_ROLES:
        name = _text(review_names.get(role)) or f"reviews/{role}.yml"
        aset.reviews[role] = _load_yaml(set_dir / name, repo_root, errors)

    return aset


def discover_artifact_sets(repo_root: Path) -> list[ArtifactSet]:
    """Every ``research/reference_integrity/*/manifest.yml`` in the checkout."""
    rig_dir = repo_root / RIG_ROOT
    if not rig_dir.is_dir():
        return []
    out: list[ArtifactSet] = []
    for child in sorted(p for p in rig_dir.iterdir() if p.is_dir()):
        if child.name in NON_ARTIFACT_DIRS:
            continue
        if not (child / "manifest.yml").exists():
            continue
        out.append(load_artifact_set(child, repo_root))
    return out


# ── L1 — completeness, schema, enums, evidence, verdict packet ────────────────

def _required_files(aset: ArtifactSet, groups: frozenset[str]) -> list[tuple[str, Any]]:
    """(logical name, loaded doc) pairs whose ABSENCE is a completeness failure."""
    if GROUP_COMPLETENESS not in groups:
        return []
    required: list[tuple[str, Any]] = [
        ("baseline.yml", aset.baseline),
        ("proposal.yml", aset.proposal),
        ("verdict.yml", aset.verdict),
        ("reviews/product_regression.yml", aset.reviews.get("product_regression")),
        ("reviews/visual_taste.yml", aset.reviews.get("visual_taste")),
    ]
    if GROUP_APPROVAL in groups:
        required.append(("approval.yml", aset.approval))
    return required


def rule_l1(
    aset: ArtifactSet,
    groups: frozenset[str],
    *,
    enforce_evidence: bool = True,
    gate_mode: bool = False,
) -> list[Finding]:
    out: list[Finding] = []
    ref = aset.reference_id

    # -- schema ids -----------------------------------------------------------
    docs: list[tuple[str, dict[str, Any] | None, str]] = [
        ("manifest.yml", aset.manifest, SCHEMA_IDS["manifest"]),
        ("baseline.yml", aset.baseline, SCHEMA_IDS["baseline"]),
        ("proposal.yml", aset.proposal, SCHEMA_IDS["proposal"]),
        ("verdict.yml", aset.verdict, SCHEMA_IDS["verdict"]),
        ("approval.yml", aset.approval, SCHEMA_IDS["approval"]),
    ]
    for role in REVIEW_ROLES:
        docs.append((f"reviews/{role}.yml", aset.reviews.get(role), SCHEMA_IDS["review"]))
    for name, doc, expected in docs:
        if doc is None:
            continue
        actual = _text(doc.get("schema"))
        if actual != expected:
            out.append(Finding(
                "invalid-schema", f"{ref}/{name}",
                f"schema must be {expected!r}, got {actual or '<missing>'!r}",
            ))

    if aset.manifest is None:
        out.append(Finding("missing-artifact-file", f"{ref}/manifest.yml", "artifact set has no manifest"))
        return out

    # -- status / scope enums -------------------------------------------------
    status = aset.status
    if status not in STATUSES:
        out.append(Finding(
            "invalid-status", f"{ref}/manifest.yml",
            f"status {status or '<missing>'!r} not in {sorted(STATUSES)}",
        ))
    scope = aset.scope
    if scope not in SCOPES:
        out.append(Finding(
            "invalid-enum", f"{ref}/manifest.yml:scope",
            f"scope {scope or '<missing>'!r} not in {sorted(SCOPES)}",
        ))

    # -- completeness ---------------------------------------------------------
    why = (
        "required by the approval-shape rule set (--evaluate) (RIG §3)"
        if gate_mode else f"required for status {status!r} (RIG §3)"
    )
    for name, doc in _required_files(aset, groups):
        if doc is None:
            out.append(Finding("missing-artifact-file", f"{ref}/{name}", why))

    # -- baseline evidence ----------------------------------------------------
    if aset.baseline is not None:
        out.extend(_baseline_evidence_findings(aset, enforce_evidence=enforce_evidence))
        for cap in _as_list(aset.baseline.get("capabilities")):
            cap = _as_dict(cap)
            cid = _text(cap.get("id")) or "<unnamed>"
            importance = _text(cap.get("importance"))
            if importance and importance not in IMPORTANCES:
                out.append(Finding(
                    "invalid-enum", f"{ref}:{cid}",
                    f"capability importance {importance!r} not in {sorted(IMPORTANCES)}",
                ))

    # -- verdict packet: all eight answers, non-empty --------------------------
    if aset.verdict is not None:
        packet = _as_dict(aset.verdict.get("packet"))
        for key in PACKET_KEYS:
            if not _text(packet.get(key)):
                out.append(Finding(
                    "missing-verdict-question", f"{ref}:packet.{key}",
                    "the eight verdict-packet answers are all required, non-empty (RIG §7)",
                ))
        vd = _text(aset.verdict.get("verdict"))
        if vd and vd not in VERDICTS:
            out.append(Finding(
                "invalid-enum", f"{ref}/verdict.yml:verdict",
                f"verdict {vd!r} not in {sorted(VERDICTS)}",
            ))
        for row in _as_list(aset.verdict.get("blocking_findings")):
            row = _as_dict(row)
            res = _text(row.get("resolution"))
            fid = _text(row.get("finding")) or "<unnamed>"
            if res and res not in RESOLUTIONS:
                out.append(Finding(
                    "invalid-enum", f"{ref}:blocking_findings.{fid}",
                    f"resolution {res!r} not in {sorted(RESOLUTIONS)}",
                ))

    # -- superseded must name its successor -----------------------------------
    if status == "superseded" and not _text(aset.manifest.get("successor_reference_id")):
        out.append(Finding(
            "superseded-without-successor", f"{ref}/manifest.yml",
            "a superseded reference must name successor_reference_id (RIG §3)",
        ))

    return out


def _baseline_evidence_findings(aset: ArtifactSet, *, enforce_evidence: bool) -> list[Finding]:
    """Screenshots must exist on disk; an empty list is never honest (gaps are, RIG §4)."""
    out: list[Finding] = []
    ref = aset.reference_id
    evidence = _as_dict(_as_dict(aset.baseline).get("evidence"))
    shots = _as_list(evidence.get("screenshots"))
    if not shots:
        out.append(Finding(
            "missing-baseline-evidence", f"{ref}/baseline.yml",
            "evidence.screenshots is empty — missing axes are recorded as honest gaps, never silent absence (RIG §4)",
        ))
        return out
    if not enforce_evidence:
        return out

    skipped_roots: set[str] = set()
    for shot in shots:
        rel = _text(_as_dict(shot).get("path")) if isinstance(shot, dict) else _text(shot)
        if not rel:
            out.append(Finding(
                "missing-baseline-evidence", f"{ref}/baseline.yml",
                "an evidence.screenshots entry carries no path",
            ))
            continue
        root_name = _top_level_dir(rel)
        if not (aset.repo_root / root_name).exists():
            # Sparse agent checkout: the whole root is absent, so absence proves nothing.
            if root_name not in skipped_roots:
                skipped_roots.add(root_name)
                notice(
                    f"sparse checkout: {root_name}/ is not present, skipping screenshot "
                    f"existence for {ref} (enforced in CI, where the root exists)"
                )
            continue
        if not (aset.repo_root / rel).exists():
            out.append(Finding(
                "missing-baseline-evidence", rel,
                f"{ref}: baseline evidence screenshot is not committed",
            ))
    return out


# ── L2 / L3 — capability ledger + blocked-data honesty ────────────────────────

def rule_l2_l3(aset: ArtifactSet, groups: frozenset[str]) -> list[Finding]:
    """§5 ledger coverage/uniqueness and §1 per-disposition mandatory fields."""
    out: list[Finding] = []
    ref = aset.reference_id
    baseline_ids: list[str] = []
    for cap in _as_list(_as_dict(aset.baseline).get("capabilities")):
        cid = _text(_as_dict(cap).get("id"))
        if cid:
            baseline_ids.append(cid)

    dispositions = _as_list(_as_dict(aset.proposal).get("dispositions"))

    # Duplicates (structural — armed at every status).
    if GROUP_SCHEMA in groups:
        for pool, where in ((baseline_ids, "baseline.yml:capabilities"),
                            ([_text(_as_dict(d).get("id")) for d in dispositions], "proposal.yml:dispositions")):
            counts: dict[str, int] = {}
            for cid in pool:
                if cid:
                    counts[cid] = counts.get(cid, 0) + 1
            for cid, n in counts.items():
                if n > 1:
                    out.append(Finding(
                        "duplicate-capability-id", f"{ref}:{cid}",
                        f"appears {n}× in {where} — capability ids are unique and stable (RIG §5)",
                    ))

        # Dangling + enum (structural).
        known = set(baseline_ids)
        for row in dispositions:
            row = _as_dict(row)
            cid = _text(row.get("id"))
            if not cid:
                out.append(Finding(
                    "dangling-disposition", f"{ref}:<unnamed>",
                    "a disposition row carries no capability id",
                ))
                continue
            if known and cid not in known:
                out.append(Finding(
                    "dangling-disposition", f"{ref}:{cid}",
                    "disposition names a capability id absent from the baseline ledger (RIG §5)",
                ))
            disp = _text(row.get("disposition"))
            if disp not in DISPOSITIONS:
                out.append(Finding(
                    "invalid-disposition", f"{ref}:{cid}",
                    f"disposition {disp or '<missing>'!r} not in {sorted(DISPOSITIONS)}",
                ))

    if GROUP_LEDGER not in groups:
        return out

    # Coverage — every baseline capability id receives exactly one disposition.
    disposed = {_text(_as_dict(d).get("id")) for d in dispositions}
    for cid in baseline_ids:
        if cid not in disposed:
            out.append(Finding(
                "missing-disposition", f"{ref}:{cid}",
                "baseline capability has no disposition — there is no implicit deletion (RIG §1/§5)",
            ))

    # Mandatory fields per disposition (RIG §1 table).
    for row in dispositions:
        row = _as_dict(row)
        cid = _text(row.get("id")) or "<unnamed>"
        subject = f"{ref}:{cid}"
        disp = _text(row.get("disposition"))
        rationale = _text(row.get("rationale"))

        if disp in {"RETAIN", "IMPROVE"} and not _has(row, "target"):
            out.append(Finding("retain-without-target", subject,
                               f"{disp} requires target — where the capability lives in the proposal (RIG §1)"))
        if disp == "IMPROVE" and not rationale:
            out.append(Finding("improve-without-rationale", subject,
                               "IMPROVE requires rationale (RIG §1)"))

        if disp == "RELOCATE":
            if not _has(row, "destination"):
                out.append(Finding("relocate-without-destination", subject,
                                   "RELOCATE requires an exact destination (RIG §1)"))
            if not _has(row, "reachability"):
                out.append(Finding("relocate-without-reachability", subject,
                                   "RELOCATE requires reachability — proof the user can still reach it (RIG §1)"))

        if disp == "REMOVE":
            if not rationale:
                out.append(Finding("remove-without-rationale", subject,
                                   "REMOVE requires an explicit product rationale (RIG §1)"))
            if not _has(row, "user_job_impact"):
                out.append(Finding("remove-without-user-job-impact", subject,
                                   "REMOVE requires user_job_impact — what the user loses (RIG §1)"))
            if not _has(row, "superiority_case"):
                out.append(Finding("remove-without-superiority-case", subject,
                                   "REMOVE requires superiority_case — why removal beats retention/improvement (RIG §1)"))
            if not _has(row, "approval_ref"):
                out.append(Finding("remove-without-approval-ref", subject,
                                   "REMOVE requires approval_ref — the receipt authorizing the deletion (RIG §1)"))
            if looks_data_motivated(rationale):
                out.append(Finding(
                    "blocked-data-as-removal", subject,
                    "REMOVE rationale reads as data-motivated — a removal caused by data "
                    "insufficiency is definitionally a mis-filed BLOCKED_DATA; re-file it with "
                    "dependency/escalation/interim, or state the product reason (RIG §1)",
                ))

        if disp == "BLOCKED_DATA":
            if not _has(row, "dependency"):
                out.append(Finding("blocked-data-without-dependency", subject,
                                   "BLOCKED_DATA requires dependency — the insufficient contract, named (RIG §1)"))
            if not _has(row, "escalation"):
                out.append(Finding("blocked-data-without-escalation", subject,
                                   "BLOCKED_DATA requires escalation — program/owner/issue it was raised with (RIG §1)"))
            if not _has(row, "interim"):
                out.append(Finding("blocked-data-without-interim", subject,
                                   "BLOCKED_DATA requires interim — what the UI does meanwhile (RIG §1)"))

    return out


# ── L4 — regression explicitness ──────────────────────────────────────────────

def _verdict_adjudicates(verdict: dict[str, Any] | None, subject_id: str) -> bool:
    """True when the verdict packet explicitly names ``subject_id`` in its adjudication record.

    Scanned: ``blocking_findings`` (finding id + note), ``conditions`` (strings), and
    ``overrides`` (finding id + justification).  Deliberately NOT the eight packet
    prose answers — an incidental mention in narrative is not an adjudication.
    """
    if not verdict or not subject_id:
        return False
    haystack: list[str] = []
    for row in _as_list(verdict.get("blocking_findings")):
        row = _as_dict(row)
        haystack.append(_text(row.get("finding")))
        haystack.append(_text(row.get("note")))
    for row in _as_list(verdict.get("overrides")):
        row = _as_dict(row)
        haystack.append(_text(row.get("finding")))
        haystack.append(_text(row.get("justification")))
    for cond in _as_list(verdict.get("conditions")):
        haystack.append(_text(cond) if not isinstance(cond, dict) else json.dumps(cond, sort_keys=True))
    return any(subject_id in blob for blob in haystack if blob)


def rule_l4(aset: ArtifactSet, groups: frozenset[str]) -> list[Finding]:
    out: list[Finding] = []
    ref = aset.reference_id
    proposal = _as_dict(aset.proposal)
    tasks = _as_list(proposal.get("user_tasks"))

    if GROUP_SCHEMA in groups:
        for task in tasks:
            task = _as_dict(task)
            tid = _text(task.get("id")) or "<unnamed>"
            vd = _text(task.get("verdict"))
            if vd not in TASK_VERDICTS:
                out.append(Finding(
                    "invalid-task-verdict", f"{ref}:{tid}",
                    f"task verdict {vd or '<missing>'!r} not in {sorted(TASK_VERDICTS)}",
                ))
        for row in _as_list(proposal.get("authority_delta")):
            row = _as_dict(row)
            aid = _text(row.get("id")) or "<unnamed>"
            direction = _text(row.get("direction"))
            if direction not in AUTHORITY_DIRECTIONS:
                out.append(Finding(
                    "invalid-enum", f"{ref}:{aid}",
                    f"authority direction {direction or '<missing>'!r} not in {sorted(AUTHORITY_DIRECTIONS)}",
                ))

    if GROUP_REGRESSION not in groups:
        return out

    if aset.proposal is not None and not tasks:
        out.append(Finding(
            "missing-task-matrix", f"{ref}/proposal.yml",
            "user_tasks is required — references are judged against what the user can do (RIG §6)",
        ))

    for task in tasks:
        task = _as_dict(task)
        tid = _text(task.get("id")) or "<unnamed>"
        if _text(task.get("verdict")) == "WORSE" and task.get("critical") is True:
            if not _verdict_adjudicates(aset.verdict, tid):
                out.append(Finding(
                    "worse-core-task-unadjudicated", f"{ref}:{tid}",
                    "WORSE on a critical:true user task is review-blocking until explicitly "
                    "adjudicated in the verdict packet (RIG §6)",
                ))

    authority = _as_list(proposal.get("authority_delta"))
    if aset.proposal is not None and aset.scope == "full" and not authority:
        out.append(Finding(
            "missing-authority-delta", f"{ref}/proposal.yml",
            "a full-scope proposal must carry an authority_delta audit (RIG §6)",
        ))
    for row in authority:
        row = _as_dict(row)
        aid = _text(row.get("id")) or "<unnamed>"
        if _text(row.get("direction")) == "stronger" and row.get("warranted") is False:
            if not _verdict_adjudicates(aset.verdict, aid):
                out.append(Finding(
                    "unwarranted-authority-unadjudicated", f"{ref}:{aid}",
                    "an unwarranted 'stronger' authority claim is review-blocking until "
                    "resolved in the verdict packet (RIG §6)",
                ))
    return out


# ── L5 — review independence + ordering ───────────────────────────────────────

def _amended_action(review: dict[str, Any] | None, finding_id: str) -> str:
    """The second-pass action recorded for ``finding_id`` (upheld/downgraded/withdrawn), or ''."""
    second_pass = _as_dict(review).get("second_pass")
    for row in _as_list(_as_dict(second_pass).get("amendments")):
        row = _as_dict(row)
        if _text(row.get("finding")) == finding_id:
            return _text(row.get("action"))
    return ""


def rule_l5(aset: ArtifactSet, groups: frozenset[str]) -> list[Finding]:
    if GROUP_REVIEW not in groups:
        return []
    out: list[Finding] = []
    ref = aset.reference_id
    identities: dict[str, str] = {}

    for role in REVIEW_ROLES:
        review = aset.reviews.get(role)
        subject = f"{ref}/reviews/{role}.yml"
        if review is None:
            out.append(Finding(
                "missing-review-receipt", subject,
                f"the {role} critic receipt is required — a new reference cannot approve itself (RIG §6)",
            ))
            continue

        declared_role = _text(review.get("role"))
        if declared_role != role:
            out.append(Finding(
                "invalid-enum", f"{subject}:role",
                f"receipt role {declared_role or '<missing>'!r} does not match its slot {role!r}",
            ))

        reviewer = _as_dict(review.get("reviewer"))
        identity = _text(reviewer.get("identity"))
        identities[role] = identity
        if identity and aset.author_identity and identity == aset.author_identity:
            out.append(Finding(
                "reviewer-not-independent", f"{ref}:{role}",
                "reviewer identity equals the author identity — a reference cannot review itself (RIG §6)",
            ))
        if reviewer.get("independent_of_author") is False:
            out.append(Finding(
                "reviewer-not-independent", f"{ref}:{role}",
                "receipt attests independent_of_author: false (RIG §6)",
            ))

        quarantine = _as_dict(review.get("quarantine"))
        if quarantine.get("rationale_received_after_first_pass") is not True:
            out.append(Finding(
                "missing-quarantine-attestation", f"{ref}:{role}",
                "receipt must attest quarantine.rationale_received_after_first_pass: true — "
                "the critic judges the RESULT before the rationale (RIG §6)",
            ))

        first_pass = _as_dict(review.get("first_pass"))
        second_pass = review.get("second_pass")
        if second_pass is not None and not _text(first_pass.get("frozen_at")):
            out.append(Finding(
                "second-pass-before-freeze", f"{ref}:{role}",
                "a second pass exists but first_pass.frozen_at is missing — findings must be "
                "frozen before the rationale is revealed (RIG §6)",
            ))

        for key, doc in (("first_pass", first_pass), ("second_pass", _as_dict(second_pass))):
            vd = _text(doc.get("verdict"))
            if vd and vd not in REVIEW_VERDICTS:
                out.append(Finding(
                    "invalid-enum", f"{ref}:{role}.{key}",
                    f"review verdict {vd!r} not in {sorted(REVIEW_VERDICTS)}",
                ))
        for row in _as_list(first_pass.get("findings")):
            row = _as_dict(row)
            fid = _text(row.get("id")) or "<unnamed>"
            sev = _text(row.get("severity"))
            if sev not in SEVERITIES:
                out.append(Finding(
                    "invalid-enum", f"{ref}:{fid}",
                    f"finding severity {sev or '<missing>'!r} not in {sorted(SEVERITIES)}",
                ))
        for row in _as_list(_as_dict(second_pass).get("amendments")):
            row = _as_dict(row)
            action = _text(row.get("action"))
            fid = _text(row.get("finding")) or "<unnamed>"
            if action not in AMENDMENT_ACTIONS:
                out.append(Finding(
                    "invalid-enum", f"{ref}:{fid}.amendment",
                    f"amendment action {action or '<missing>'!r} not in {sorted(AMENDMENT_ACTIONS)}",
                ))

        # Receipts bind to bytes (RIG §3).
        receipt_sha = _text(review.get("artifact_sha"))
        if aset.proposal is not None and aset.frozen_sha and receipt_sha != aset.frozen_sha:
            out.append(Finding(
                "stale-review-receipt", f"{ref}:{role}",
                f"receipt judged artifact_sha {receipt_sha or '<missing>'!r} but the proposal's "
                f"frozen_sha is {aset.frozen_sha!r} — nobody approves v1 receipts and ships a v3 artifact (RIG §3)",
            ))

    present = [i for i in identities.values() if i]
    if len(present) == 2 and present[0] == present[1]:
        out.append(Finding(
            "reviewer-not-independent", f"{ref}:reviewers",
            "both critic receipts carry the same reviewer identity — the dual review is not independent (RIG §6)",
        ))
    return out


# ── L6 — approval integrity ───────────────────────────────────────────────────

def surviving_blockers(aset: ArtifactSet) -> list[tuple[str, str]]:
    """(role, finding id) for every blocker-severity finding not WITHDRAWN in the second pass."""
    out: list[tuple[str, str]] = []
    for role in REVIEW_ROLES:
        review = aset.reviews.get(role)
        if not review:
            continue
        for row in _as_list(_as_dict(review.get("first_pass")).get("findings")):
            row = _as_dict(row)
            if _text(row.get("severity")) != "blocker":
                continue
            fid = _text(row.get("id")) or "<unnamed>"
            if _amended_action(review, fid) == "withdrawn":
                continue
            out.append((role, fid))
    return out


def rule_l6(aset: ArtifactSet, groups: frozenset[str]) -> list[Finding]:
    if GROUP_APPROVAL not in groups:
        return []
    out: list[Finding] = []
    ref = aset.reference_id

    # A critic BLOCK cannot disappear silently (RIG §7).
    resolved: dict[str, str] = {}
    for row in _as_list(_as_dict(aset.verdict).get("blocking_findings")):
        row = _as_dict(row)
        fid = _text(row.get("finding"))
        if fid:
            resolved[fid] = _text(row.get("resolution"))
    for role, fid in surviving_blockers(aset):
        resolution = resolved.get(fid, "")
        if resolution in APPROVAL_COMPATIBLE_RESOLUTIONS:
            continue
        detail = (
            f"verdict.yml resolves it {resolution!r}, which RIG §7 defines as driving "
            f"REVISE/REJECT — it cannot also approve"
            if resolution in RESOLUTIONS
            else f"verdict.yml records no resolution for it ({sorted(RESOLUTIONS)})"
        )
        out.append(Finding(
            "approved-with-unresolved-block", f"{ref}:{fid}",
            f"{role} blocker survived its own second pass and {detail} — a critic BLOCK "
            f"cannot disappear silently (RIG §7)",
        ))

    if aset.approval is None:
        out.append(Finding(
            "approved-without-receipt", f"{ref}/approval.yml",
            "approval requires an approval receipt — a migration may treat a reference as "
            "canonical only if it carries one (RIG §7)",
        ))

    verdict_value = _text(_as_dict(aset.verdict).get("verdict"))
    if verdict_value not in APPROVING_VERDICTS:
        out.append(Finding(
            "approved-with-wrong-verdict", f"{ref}/verdict.yml",
            f"verdict {verdict_value or '<missing>'!r} is not in {sorted(APPROVING_VERDICTS)}",
        ))

    for source, doc in (("verdict.yml", aset.verdict), ("approval.yml", aset.approval)):
        for i, row in enumerate(_as_list(_as_dict(doc).get("overrides"))):
            row = _as_dict(row)
            fid = _text(row.get("finding"))
            if not fid:
                out.append(Finding(
                    "override-without-finding-id", f"{ref}/{source}:overrides[{i}]",
                    "an override must cite the critic finding id it overrides (RIG §7)",
                ))
            if not _text(row.get("justification")):
                out.append(Finding(
                    "override-without-justification", f"{ref}/{source}:overrides[{fid or i}]",
                    "an override must carry a justification — permanent record (RIG §7)",
                ))

    # Lightweight scope (RIG §2).
    if aset.scope == "lightweight":
        light = _as_dict(_as_dict(aset.manifest).get("lightweight"))
        if light.get("no_capability_change") is not True or light.get("no_hierarchy_change") is not True:
            out.append(Finding(
                "lightweight-attestation-missing", f"{ref}/manifest.yml",
                "lightweight scope requires lightweight.no_capability_change: true AND "
                "no_hierarchy_change: true — either false means Full RIG (RIG §2)",
            ))
    return out


def rule_lightweight_archetype(aset: ArtifactSet, approved_ids: set[str], groups: frozenset[str]) -> list[Finding]:
    """Cross-set half of §2: the cited archetype reference must itself be approved."""
    if GROUP_APPROVAL not in groups or aset.scope != "lightweight":
        return []
    light = _as_dict(_as_dict(aset.manifest).get("lightweight"))
    cited = _text(light.get("archetype_reference"))
    if cited and cited not in approved_ids:
        return [Finding(
            "lightweight-cites-unapproved-archetype", f"{aset.reference_id}:{cited}",
            "a lightweight reference may only follow an APPROVED archetype reference (RIG §2)",
        )]
    return []


# ── Per-set driver ────────────────────────────────────────────────────────────

def evaluate_set(
    aset: ArtifactSet,
    *,
    groups: frozenset[str] | None = None,
    approved_ids: set[str] | None = None,
    enforce_evidence: bool = True,
    gate_mode: bool = False,
) -> list[Finding]:
    """Run the rule groups armed for this artifact set.  ``groups=ALL_GROUPS`` = gate mode."""
    if groups is None:
        groups = STATUS_GROUPS.get(aset.status, ALL_GROUPS)
    findings: list[Finding] = list(aset.parse_errors)
    findings += rule_l1(aset, groups, enforce_evidence=enforce_evidence, gate_mode=gate_mode)
    findings += rule_l2_l3(aset, groups)
    findings += rule_l4(aset, groups)
    findings += rule_l5(aset, groups)
    findings += rule_l6(aset, groups)
    findings += rule_lightweight_archetype(aset, approved_ids or set(), groups)
    return dedupe(findings)


# ── L7 — reference-namespace closure ──────────────────────────────────────────

def rule_l7(repo_root: Path, sets: Sequence[ArtifactSet]) -> list[Finding]:
    ds_dir = repo_root / DESIGN_SYSTEM_ROOT
    if not ds_dir.is_dir():
        notice(
            f"sparse checkout: {DESIGN_SYSTEM_ROOT}/ is not present, skipping L7 "
            "reference-namespace closure (enforced in CI, where the root exists)"
        )
        return []
    claims: dict[str, list[str]] = {}
    for aset in sets:
        for row in _as_list(_as_dict(aset.manifest).get("reference_files")):
            path = _text(_as_dict(row).get("path")) if isinstance(row, dict) else _text(row)
            if path:
                claims.setdefault(path, []).append(aset.reference_id)

    out: list[Finding] = []
    for html in sorted(ds_dir.glob("*.html")):
        if html.name in NAMESPACE_EXEMPT:
            continue
        rel = html.relative_to(repo_root).as_posix()
        owners = claims.get(rel, [])
        if not owners:
            out.append(Finding(
                "unclaimed-reference-file", rel,
                "every non-specimen design-system reference must be claimed by exactly one "
                "RIG manifest's reference_files (RIG §8 L7)",
            ))
        elif len(owners) > 1:
            out.append(Finding(
                "double-claimed-reference-file", rel,
                f"claimed by {len(owners)} manifests ({', '.join(sorted(owners))}) — exactly one (RIG §8 L7)",
            ))
    return out


# ── L8 — migration-packet coupling ────────────────────────────────────────────

def rule_l8(repo_root: Path, status_by_id: dict[str, str]) -> list[Finding]:
    packet_dir = repo_root / PACKET_ROOT
    if not packet_dir.is_dir():
        return []
    out: list[Finding] = []
    for packet in sorted(packet_dir.glob("*.md")):
        rel = packet.relative_to(repo_root).as_posix()
        try:
            body = packet.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            out.append(Finding("packet-without-rig-receipt", rel, f"unreadable: {exc}"))
            continue
        cited = [m.group(1) for m in _RIG_RECEIPT_RE.finditer(body)]
        if not cited:
            out.append(Finding(
                "packet-without-rig-receipt", rel,
                "a migration packet must cite a 'RIG-RECEIPT: <reference-id>' line naming an "
                "APPROVED reference (RIG §8 L8)",
            ))
            continue
        for ref in cited:
            if status_by_id.get(ref) != "approved":
                out.append(Finding(
                    "packet-cites-unapproved-reference", f"{rel}:{ref}",
                    f"RIG-RECEIPT names reference {ref!r} with status "
                    f"{status_by_id.get(ref, '<missing>')!r} — only an approved reference is canonical (RIG §7/§8)",
                ))
    return out


# ── L9 — page-registry coupling ───────────────────────────────────────────────

def _surface_keys(manifest: dict[str, Any] | None) -> set[str]:
    surface = _as_dict(_as_dict(manifest).get("surface"))
    keys: set[str] = set()
    for value in (surface.get("route"), surface.get("registry_row")):
        text = _text(value)
        if not text:
            continue
        keys.add(text)
        if text.endswith(".html"):
            keys.add(text[:-5])
    return keys


def _row_keys(page_id: str, row: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for candidate in (page_id, row.get("page_id"), row.get("id"), row.get("slug"), row.get("route")):
        text = _text(candidate)
        if not text:
            continue
        keys.add(text)
        if ":" in text:
            keys.add(text.rsplit(":", 1)[-1])
        if text.endswith(".html"):
            keys.add(text[:-5])
        keys.add(text.rsplit("/", 1)[-1])
        if text.rsplit("/", 1)[-1].endswith(".html"):
            keys.add(text.rsplit("/", 1)[-1][:-5])
    return keys


def _compliant_rows(payload: Any) -> list[tuple[str, dict[str, Any]]]:
    """(page id, row) for every row asserting ``design_system.compliant: true``."""
    rows: list[tuple[str, dict[str, Any]]] = []
    if isinstance(payload, dict):
        pages = payload.get("pages")
        candidates: list[tuple[str, Any]]
        if isinstance(pages, dict):
            candidates = list(pages.items())
        elif isinstance(pages, list):
            candidates = [(_text(_as_dict(r).get("page_id") or _as_dict(r).get("id")), r) for r in pages]
        elif isinstance(payload.get("rows"), list):
            candidates = [(_text(_as_dict(r).get("page_id") or _as_dict(r).get("id")), r) for r in payload["rows"]]
        else:
            candidates = []
    elif isinstance(payload, list):
        candidates = [(_text(_as_dict(r).get("page_id") or _as_dict(r).get("id")), r) for r in payload]
    else:
        candidates = []

    for page_id, row in candidates:
        row_d = _as_dict(row)
        design_system = row_d.get("design_system")
        if isinstance(design_system, dict) and design_system.get("compliant") is True:
            rows.append((page_id, row_d))
    return rows


def rule_l9(repo_root: Path, sets: Sequence[ArtifactSet]) -> list[Finding]:
    approved_keys: set[str] = set()
    for aset in sets:
        if aset.status == "approved":
            approved_keys |= _surface_keys(aset.manifest)
            approved_keys.add(aset.reference_id)

    out: list[Finding] = []

    overrides_path = repo_root / REGISTRY_OVERRIDES
    sources: list[tuple[str, Any]] = []
    if overrides_path.exists():
        try:
            sources.append((REGISTRY_OVERRIDES, yaml.safe_load(overrides_path.read_text(encoding="utf-8"))))
        except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
            out.append(Finding("invalid-schema", REGISTRY_OVERRIDES, f"does not parse as YAML: {exc}"))

    json_path = repo_root / REGISTRY_JSON
    if json_path.exists():
        try:
            sources.append((REGISTRY_JSON, json.loads(json_path.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            out.append(Finding("invalid-schema", REGISTRY_JSON, f"does not parse as JSON: {exc}"))
    elif not (repo_root / _top_level_dir(REGISTRY_JSON)).exists():
        # Sparse agent checkout: the whole data/ root is absent, so absence proves nothing.
        notice(
            f"sparse checkout: {_top_level_dir(REGISTRY_JSON)}/ is not present, skipping the "
            f"compiled page registry (enforced in CI, where the root exists)"
        )
    else:
        out.append(Finding(
            "missing-registry-file", REGISTRY_JSON,
            "the compiled page registry is missing — its silent disappearance must not silently "
            "disarm the L9 coupling rule (RIG §8 L9)",
        ))

    for source, payload in sources:
        for page_id, row in _compliant_rows(payload):
            keys = _row_keys(page_id, row)
            if not (keys & approved_keys):
                out.append(Finding(
                    "compliant-row-without-approved-reference", f"{source}:{page_id or '<unnamed>'}",
                    "a registry row may not claim design_system.compliant: true without an "
                    "APPROVED RIG reference for that surface (RIG §7/§8 L9)",
                ))
    return out


# ── Modes ─────────────────────────────────────────────────────────────────────

def run_repo_mode(repo_root: Path) -> int:
    sets = discover_artifact_sets(repo_root)
    status_by_id = {a.reference_id: a.status for a in sets}
    approved_ids = {ref for ref, status in status_by_id.items() if status == "approved"}

    findings: list[Finding] = []
    for aset in sets:
        findings += evaluate_set(aset, approved_ids=approved_ids)
    findings += rule_l7(repo_root, sets)
    findings += rule_l8(repo_root, status_by_id)
    findings += rule_l9(repo_root, sets)

    findings = dedupe(findings)
    emit(findings)
    if findings:
        print(
            f"reference-integrity: {len(findings)} finding(s) across {len(sets)} artifact set(s)",
            flush=True,
        )
        return 1
    notice(
        f"reference-integrity clean — {len(sets)} artifact set(s), "
        f"{len(approved_ids)} approved"
    )
    return 0


def run_evaluate(repo_root: Path, reference_id: str) -> int:
    set_dir = repo_root / RIG_ROOT / reference_id
    if not (set_dir / "manifest.yml").exists():
        emit([Finding(
            "missing-artifact-file", f"{RIG_ROOT}/{reference_id}/manifest.yml",
            "no such reference artifact set",
        )])
        return 1

    sets = discover_artifact_sets(repo_root)
    approved_ids = {a.reference_id for a in sets if a.status == "approved"}
    aset = next((a for a in sets if a.reference_id == reference_id), None)
    if aset is None:
        aset = load_artifact_set(set_dir, repo_root)

    findings = evaluate_set(aset, groups=ALL_GROUPS, approved_ids=approved_ids, gate_mode=True)
    print(
        f"reference-integrity --evaluate {reference_id} "
        f"(status={aset.status or '<missing>'}, scope={aset.scope or '<missing>'}): "
        f"{len(findings)} finding(s)",
        flush=True,
    )
    emit(findings)
    if findings:
        print(f"reference-integrity: {reference_id} is BLOCKED — not approvable-shape", flush=True)
        return 3
    notice(f"{reference_id} is approvable-shape — every mechanical gate holds")
    return 0


# ── Selftest ──────────────────────────────────────────────────────────────────

_SYNTHETIC_SHA = "a" * 40


def _synthetic_docs(reference_id: str) -> dict[str, Any]:
    """A fully-valid APPROVED artifact set, as plain dicts, for the hermetic selftest."""
    return {
        "manifest.yml": {
            "schema": SCHEMA_IDS["manifest"],
            "reference_id": reference_id,
            "scope": "full",
            "status": "approved",
            "surface": {"route": "synthetic.html", "registry_row": "synthetic", "archetype": "board"},
            "author": {"identity": "author-session", "role": "designer"},
            "reference_files": [{"path": f"mockups/design_system/{reference_id}.html",
                                 "frozen_sha": _SYNTHETIC_SHA}],
            "files": {
                "baseline": "baseline.yml",
                "proposal": "proposal.yml",
                "reviews": {"product_regression": "reviews/product_regression.yml",
                            "visual_taste": "reviews/visual_taste.yml"},
                "verdict": "verdict.yml",
                "approval": "approval.yml",
            },
        },
        "baseline.yml": {
            "schema": SCHEMA_IDS["baseline"],
            "reference_id": reference_id,
            "production": {"route": "synthetic.html", "source_commit": _SYNTHETIC_SHA},
            "evidence": {
                "screenshots": [{"path": f"mockups/refs/reference_integrity/{reference_id}/prod-dark.png",
                                 "viewport": "desktop", "theme": "dark", "locale": "en"}],
                "gaps": [{"axis": "locale", "value": "zh", "reason": "surface is EN-only"}],
            },
            "user_job": "decide what to work on",
            "core_interactions": ["scan the grid"],
            "information_hierarchy": ["chart", "price"],
            "capabilities": [
                {"id": "card.chart", "user_job": "see price geometry", "evidence": "t.j2:1", "importance": "core"},
                {"id": "card.price", "user_job": "see price now", "evidence": "t.j2:2", "importance": "core"},
                {"id": "card.badge", "user_job": "see the lane", "evidence": "t.j2:3", "importance": "supporting"},
                {"id": "card.note", "user_job": "read the caveat", "evidence": "t.j2:4", "importance": "peripheral"},
            ],
        },
        "proposal.yml": {
            "schema": SCHEMA_IDS["proposal"],
            "reference_id": reference_id,
            "proposed_artifact": {"frozen_sha": _SYNTHETIC_SHA,
                                  "paths": [f"mockups/design_system/{reference_id}.html"]},
            "dispositions": [
                {"id": "card.chart", "disposition": "BLOCKED_DATA",
                 "dependency": "spark enrichment contract covers a quarter of rows",
                 "escalation": "escalated to the data program, issue #1",
                 "interim": "the card keeps its slot empty and says so"},
                {"id": "card.price", "disposition": "RETAIN", "target": "card head, unchanged"},
                {"id": "card.badge", "disposition": "RELOCATE", "destination": "row 2 lane chip",
                 "reachability": "still visible at rest, no hover required"},
                {"id": "card.note", "disposition": "REMOVE",
                 "rationale": "the caveat duplicated the stance word on every card",
                 "user_job_impact": "the caveat is no longer readable on the card",
                 "superiority_case": "the stance word already carries it; the duplicate cost a line",
                 "approval_ref": "VTC-002 / verdict.yml override"},
            ],
            "user_tasks": [
                {"id": "task.scan", "task": "scan the grid", "critical": True,
                 "production": "hue + shape", "proposal": "hue + shape", "verdict": "EQUIVALENT"},
                {"id": "task.price", "task": "read price now", "critical": True,
                 "production": "live quote", "proposal": "live quote, bigger", "verdict": "BETTER"},
                {"id": "task.caveat", "task": "read the caveat", "critical": False,
                 "production": "on card", "proposal": "on the detail page", "verdict": "WORSE"},
            ],
            "authority_delta": [
                {"id": "auth.zone", "production_claim": "a relevant range", "proposal_claim": "the same range",
                 "direction": "equal", "warranted": True, "evidence": "unchanged copy"},
            ],
            "information_economics": {
                "words_per_card": {"production": "18", "proposal": "16"},
                "findings": ["one duplicate line removed"],
                "preserved": ["the chart slot stays reserved"],
            },
        },
        "reviews/product_regression.yml": {
            "schema": SCHEMA_IDS["review"],
            "reference_id": reference_id,
            "role": "product_regression",
            "artifact_sha": _SYNTHETIC_SHA,
            "reviewer": {"identity": "critic-a", "model": "opus", "independent_of_author": True},
            "quarantine": {"rationale_received_after_first_pass": True},
            "first_pass": {"frozen_at": "2026-08-12T00:00:00Z", "verdict": "BLOCK",
                           "findings": [{"id": "PRC-001", "severity": "blocker", "capability": "card.chart",
                                         "finding": "the chart slot renders nothing"}],
                           "strengths": ["the price row got clearer"]},
            "second_pass": {"amended_at": "2026-08-12T01:00:00Z", "verdict": "PASS_WITH_CONDITIONS",
                            "amendments": [{"finding": "PRC-001", "action": "upheld",
                                            "note": "the data dependency is real but the slot is still empty"}]},
        },
        "reviews/visual_taste.yml": {
            "schema": SCHEMA_IDS["review"],
            "reference_id": reference_id,
            "role": "visual_taste",
            "artifact_sha": _SYNTHETIC_SHA,
            "reviewer": {"identity": "critic-b", "model": "opus", "independent_of_author": True},
            "quarantine": {"rationale_received_after_first_pass": True},
            "first_pass": {"frozen_at": "2026-08-12T00:00:00Z", "verdict": "PASS_WITH_CONDITIONS",
                           "findings": [{"id": "VTC-002", "severity": "minor",
                                         "finding": "the caveat line was visual noise"}],
                           "strengths": ["density improved"]},
            "second_pass": {"amended_at": "2026-08-12T01:00:00Z", "verdict": "PASS",
                            "amendments": [{"finding": "VTC-002", "action": "withdrawn",
                                            "note": "the removal is the cure"}]},
        },
        "verdict.yml": {
            "schema": SCHEMA_IDS["verdict"],
            "reference_id": reference_id,
            "authority": {"identity": "design-authority", "role": "design_authority"},
            "packet": {key: f"answer for {key}" for key in PACKET_KEYS},
            "blocking_findings": [{"finding": "PRC-001", "resolution": "resolved_by_change",
                                   "note": "the empty slot now states the dependency"}],
            "overrides": [],
            "verdict": "APPROVE_WITH_CONDITIONS",
            "conditions": ["re-review when the enrichment contract lands"],
            "preserved_strengths": ["price clarity", "density"],
        },
        "approval.yml": {
            "schema": SCHEMA_IDS["approval"],
            "reference_id": reference_id,
            "approved_at": "2026-08-12T02:00:00Z",
            "verdict": "APPROVE_WITH_CONDITIONS",
            "authority": {"identity": "design-authority", "role": "design_authority"},
            "reviewers": [{"identity": "critic-a", "role": "product_regression"},
                          {"identity": "critic-b", "role": "visual_taste"}],
            "author": {"identity": "author-session"},
            "overrides": [],
            "artifact_sha": _SYNTHETIC_SHA,
        },
    }


def _write_synthetic_set(repo_root: Path, reference_id: str, docs: dict[str, Any]) -> Path:
    set_dir = repo_root / RIG_ROOT / reference_id
    (set_dir / "reviews").mkdir(parents=True, exist_ok=True)
    for name, doc in docs.items():
        if doc is None:
            continue
        target = set_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    shot = repo_root / "mockups" / "refs" / "reference_integrity" / reference_id / "prod-dark.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    shot.write_bytes(b"\x89PNG\r\n\x1a\n")
    return set_dir


def _selftest_codes(repo_root: Path, reference_id: str, docs: dict[str, Any]) -> set[str]:
    _write_synthetic_set(repo_root, reference_id, docs)
    aset = load_artifact_set(repo_root / RIG_ROOT / reference_id, repo_root)
    approved = {reference_id} if aset.status == "approved" else set()
    return {f.code for f in evaluate_set(aset, approved_ids=approved)}


def run_selftest() -> int:
    """Hermetic proof that the gate can FAIL — the anti-vacuity half of RIG §8/§10.

    Every mutation below corrupts exactly one thing in an otherwise-valid approved set and
    asserts the matching code fires.  Demonstration output is prefixed with ``SELFTEST `` so
    a green run never emits a live ``::error`` annotation at line start.
    """
    failures: list[str] = []

    def check(label: str, condition: bool, detail: str = "") -> None:
        if condition:
            print(f"SELFTEST ok   {label}", flush=True)
        else:
            failures.append(f"{label}: {detail}")
            print(f"SELFTEST FAIL {label} {detail}", flush=True)

    with tempfile.TemporaryDirectory(prefix="rig_selftest_") as tmp:
        root = Path(tmp)

        # (i) a fully-valid approved synthetic set passes.
        clean_codes = _selftest_codes(root, "clean-ref", _synthetic_docs("clean-ref"))
        check("valid approved set passes", not clean_codes, f"unexpected codes {sorted(clean_codes)}")

        # (ii) each targeted corruption fires its own code.
        mutations: list[tuple[str, str, Any]] = []

        docs = _synthetic_docs("m-missing-disposition")
        docs["proposal.yml"]["dispositions"] = [
            d for d in docs["proposal.yml"]["dispositions"] if d["id"] != "card.price"
        ]
        mutations.append(("missing-disposition", "m-missing-disposition", docs))

        docs = _synthetic_docs("m-blocked-data-as-removal")
        docs["proposal.yml"]["dispositions"][0] = {
            "id": "card.chart", "disposition": "REMOVE",
            "rationale": "chart enrichment covers 45/179 rows (25%), so the hero is dropped",
            "user_job_impact": "price geometry is gone",
            "superiority_case": "a quarter-populated hero looked broken",
            "approval_ref": "n/a",
        }
        mutations.append(("blocked-data-as-removal", "m-blocked-data-as-removal", docs))

        docs = _synthetic_docs("m-unresolved-block")
        docs["verdict.yml"]["blocking_findings"] = []
        mutations.append(("approved-with-unresolved-block", "m-unresolved-block", docs))

        # An UPHELD blocker is recorded, but §7 says upheld_revise drives REVISE/REJECT —
        # it cannot also approve.
        docs = _synthetic_docs("m-upheld-block")
        docs["verdict.yml"]["blocking_findings"][0]["resolution"] = "upheld_revise"
        mutations.append(("approved-with-unresolved-block", "m-upheld-block", docs))

        docs = _synthetic_docs("m-not-independent")
        docs["reviews/product_regression.yml"]["reviewer"]["identity"] = "author-session"
        docs["reviews/visual_taste.yml"]["reviewer"]["identity"] = "author-session"
        mutations.append(("reviewer-not-independent", "m-not-independent", docs))

        docs = _synthetic_docs("m-missing-question")
        docs["verdict.yml"]["packet"].pop("strongest_argument_against")
        mutations.append(("missing-verdict-question", "m-missing-question", docs))

        docs = _synthetic_docs("m-stale-receipt")
        docs["reviews/visual_taste.yml"]["artifact_sha"] = "b" * 40
        mutations.append(("stale-review-receipt", "m-stale-receipt", docs))

        docs = _synthetic_docs("m-no-evidence")
        docs["baseline.yml"]["evidence"]["screenshots"] = []
        mutations.append(("missing-baseline-evidence", "m-no-evidence", docs))

        docs = _synthetic_docs("m-dangling")
        docs["proposal.yml"]["dispositions"][1]["id"] = "card.ghost"
        mutations.append(("dangling-disposition", "m-dangling", docs))

        docs = _synthetic_docs("m-duplicate")
        docs["baseline.yml"]["capabilities"].append(dict(docs["baseline.yml"]["capabilities"][0]))
        mutations.append(("duplicate-capability-id", "m-duplicate", docs))

        docs = _synthetic_docs("m-worse-core")
        docs["proposal.yml"]["user_tasks"][2]["critical"] = True
        mutations.append(("worse-core-task-unadjudicated", "m-worse-core", docs))

        docs = _synthetic_docs("m-remove-bare")
        docs["proposal.yml"]["dispositions"][3] = {"id": "card.note", "disposition": "REMOVE"}
        mutations.append(("remove-without-rationale", "m-remove-bare", docs))

        docs = _synthetic_docs("m-blocked-bare")
        docs["proposal.yml"]["dispositions"][0] = {"id": "card.chart", "disposition": "BLOCKED_DATA"}
        mutations.append(("blocked-data-without-dependency", "m-blocked-bare", docs))

        docs = _synthetic_docs("m-bad-enum")
        docs["proposal.yml"]["dispositions"][1]["disposition"] = "DELETE"
        mutations.append(("invalid-disposition", "m-bad-enum", docs))

        docs = _synthetic_docs("m-no-receipt")
        docs["reviews/visual_taste.yml"] = None
        mutations.append(("missing-review-receipt", "m-no-receipt", docs))

        docs = _synthetic_docs("m-no-quarantine")
        docs["reviews/product_regression.yml"]["quarantine"] = {"rationale_received_after_first_pass": False}
        mutations.append(("missing-quarantine-attestation", "m-no-quarantine", docs))

        docs = _synthetic_docs("m-second-first")
        docs["reviews/product_regression.yml"]["first_pass"].pop("frozen_at")
        mutations.append(("second-pass-before-freeze", "m-second-first", docs))

        docs = _synthetic_docs("m-no-approval")
        docs["approval.yml"] = None
        mutations.append(("approved-without-receipt", "m-no-approval", docs))

        docs = _synthetic_docs("m-wrong-verdict")
        docs["verdict.yml"]["verdict"] = "REVISE"
        mutations.append(("approved-with-wrong-verdict", "m-wrong-verdict", docs))

        docs = _synthetic_docs("m-bad-status")
        docs["manifest.yml"]["status"] = "blessed"
        mutations.append(("invalid-status", "m-bad-status", docs))

        for code, ref, docs in mutations:
            fired = _selftest_codes(root, ref, docs)
            check(f"{code} fires", code in fired, f"got {sorted(fired)}")

        # (iii) annotations start the line.
        sample = Finding("missing-disposition", "ref:card.x", "demo").annotation()
        check("annotation starts the line", sample.startswith("::error title="), repr(sample))

        # L7/L8/L9 fire against synthetic roots.
        (root / DESIGN_SYSTEM_ROOT).mkdir(parents=True, exist_ok=True)
        (root / DESIGN_SYSTEM_ROOT / "orphan_reference.html").write_text("<p>x</p>", encoding="utf-8")
        (root / DESIGN_SYSTEM_ROOT / "specimen.html").write_text("<p>x</p>", encoding="utf-8")
        sets = discover_artifact_sets(root)
        l7 = {f.code for f in rule_l7(root, sets)}
        check("unclaimed-reference-file fires", "unclaimed-reference-file" in l7, f"got {sorted(l7)}")

        (root / PACKET_ROOT).mkdir(parents=True, exist_ok=True)
        (root / PACKET_ROOT / "MP-001.md").write_text("# packet with no receipt\n", encoding="utf-8")
        l8 = {f.code for f in rule_l8(root, {a.reference_id: a.status for a in sets})}
        check("packet-without-rig-receipt fires", "packet-without-rig-receipt" in l8, f"got {sorted(l8)}")

        (root / "config" / "product_experience").mkdir(parents=True, exist_ok=True)
        (root / REGISTRY_OVERRIDES).write_text(
            yaml.safe_dump({"pages": {"macro:ghost": {"design_system": {"compliant": True}}}}, sort_keys=False),
            encoding="utf-8",
        )
        (root / "data" / "product_experience").mkdir(parents=True, exist_ok=True)
        (root / REGISTRY_JSON).write_text(json.dumps({"pages": []}), encoding="utf-8")
        l9 = {f.code for f in rule_l9(root, sets)}
        check("compliant-row-without-approved-reference fires",
              "compliant-row-without-approved-reference" in l9, f"got {sorted(l9)}")

    if failures:
        print(f"SELFTEST: {len(failures)} assertion(s) failed", flush=True)
        for line in failures:
            print(f"SELFTEST   {line}", flush=True)
        return 1
    notice("reference-integrity selftest passed — every rule fires on its targeted corruption")
    return 0


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_reference_integrity.py",
        description="Reference Integrity Gate (RIG V1) — mechanical enforcement.",
    )
    parser.add_argument("--root", default=str(_REPO_ROOT), help="repo root (default: this checkout)")
    parser.add_argument("--evaluate", metavar="REFERENCE_ID",
                        help="run the full L1-L6 rule set on one artifact set (exit 0 approvable, 3 blocked)")
    parser.add_argument("--selftest", action="store_true", help="hermetic anti-vacuity proof")
    args = parser.parse_args(argv)

    if args.selftest:
        return run_selftest()

    root = Path(args.root).resolve()
    if args.evaluate:
        return run_evaluate(root, args.evaluate)
    return run_repo_mode(root)


if __name__ == "__main__":
    sys.exit(main())
