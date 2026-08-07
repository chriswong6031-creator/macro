"""Fail-closed owner module for the BioCatalyst product acceptance manifest v2.

The v1 manifest (``config/biocatalyst_product_acceptance.yml``) is const-locked at the
schema level: ``state`` is a const, both ``supersedes_*`` fields are const null, and all
six ``authorizes_*`` flags are const false. It therefore cannot be edited into any
non-draft state, and this module never touches it. v2 is a *new* contract id with a new
schema; v1 remains exactly as committed.

What this module adds on top of generic JSON-Schema validation:

* the predecessor binding is checked against the committed v1 manifest's own identity
  and content digest, so v2 cannot claim a predecessor it does not actually supersede;
* the named design ruling is bound by path and byte hash;
* the ruling's gate parameters must AGREE with the constants owned by
  ``scripts/biocatalyst_browser_verifier.py``. The verifier is the authority; a manifest
  that disagrees with its verifier is rejected, never the other way round;
* the browser matrix cell identifiers must equal the ones the verifier derives itself;
* design acceptance requires a receipt whose bytes the verifier wrote. Until that file
  exists on disk and hashes to the bound digest, this manifest fails closed.

Authority boundary: this module reads committed declarations. It originates no
probability, ranking, signal, score, sizing, or escalation; it activates no source,
starts no process, opens no network, and mutates no production pointer. Recording a
design ruling is not a release authorization -- every ``authorizes_*`` flag stays false.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any, Mapping

import yaml

from engine.sector_intelligence.contracts import (
    ContractError,
    ContractRegistry,
    ContractValidationError,
    ValidationIssue,
    canonical_json_sha256,
)


PRODUCT_ACCEPTANCE_V2_CONTRACT_ID = "biocatalyst_product_acceptance_manifest.v2"
PRODUCT_ACCEPTANCE_V2_CONFIG_REF = "config/biocatalyst_product_acceptance_v2.yml"
PRODUCT_ACCEPTANCE_V1_CONFIG_REF = "config/biocatalyst_product_acceptance.yml"
BROWSER_VERIFIER_MODULE_REF = "scripts/biocatalyst_browser_verifier.py"
DESIGN_ADJUDICATION_REF = "research/BIOCATALYST_D0A_DESIGN_ADJUDICATION_2026-08-06.md"
MANIFEST_ID_PREFIX = "biocatalyst_product_acceptance_v2_"

_VERIFIER_MODULE_CACHE: dict[str, ModuleType] = {}


def _issue(path: str, code: str, message: str) -> ValidationIssue:
    return ValidationIssue(path, code, message)


def _repo_root(repo_root: Path | str | None) -> Path:
    if repo_root is not None:
        return Path(repo_root).resolve()
    return Path(__file__).resolve().parents[2]


def _repo_file(root: Path, relative: Any) -> Path | None:
    """Resolve a manifest-owned path without accepting traversal or a symlink."""

    if not isinstance(relative, str) or not relative or "\\" in relative:
        return None
    candidate = root / relative
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    cursor = candidate
    while cursor != root:
        if cursor.is_symlink():
            return None
        cursor = cursor.parent
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_browser_verifier(repo_root: Path | str | None = None) -> ModuleType:
    """Import the independent verifier module for its owned gate constants.

    The verifier never imports a browser at module scope, so this is safe in CI and in
    a plain unit-test process. It raises when the module is missing: an acceptance
    contract with no verifier on disk must fail, not silently relax.
    """

    root = _repo_root(repo_root)
    target = _repo_file(root, BROWSER_VERIFIER_MODULE_REF)
    if target is None or not target.is_file():
        raise FileNotFoundError(BROWSER_VERIFIER_MODULE_REF)
    key = f"{target}:{_sha256(target)}"
    cached = _VERIFIER_MODULE_CACHE.get(key)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(
        f"biocatalyst_browser_verifier_{hashlib.sha256(key.encode('utf-8')).hexdigest()[:12]}",
        target,
    )
    if spec is None or spec.loader is None:
        raise ImportError(BROWSER_VERIFIER_MODULE_REF)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _VERIFIER_MODULE_CACHE[key] = module
    return module


def expected_gate_parameters(repo_root: Path | str | None = None) -> dict[str, Any]:
    """The gate parameters a compliant manifest must declare, taken from the verifier."""

    verifier = load_browser_verifier(repo_root)
    return {
        "bilingual_gate": {
            "ruling_section": "3.3",
            "check_name": "bilingual_gate",
            "applies_to_locales": ["zh"],
            "zh_tier1_latin_whitelist": list(verifier.ZH_TIER1_LATIN_WHITELIST),
        },
        "decision_sentence": {
            "ruling_section": "3.1",
            "check_name": "decision_sentence_budget",
            "separator": verifier.DECISION_SENTENCE_SEPARATOR,
            "max_words_en": verifier.DECISION_SENTENCE_MAX_WORDS_EN,
            "max_characters_zh": verifier.DECISION_SENTENCE_MAX_CHARACTERS_ZH,
            "research_stances_en": list(verifier.RESEARCH_STANCES["en"]),
            "research_stances_zh": list(verifier.RESEARCH_STANCES["zh"]),
        },
        "temporal_braid_accessibility": {
            "ruling_section": "3.2",
            "check_names": [
                "temporal_braid_two_clock_text_equivalent",
                "no_hover_only_meaning",
                "visible_keyboard_focus",
                "reduced_motion_information_parity",
            ],
            "two_clock_labels_en": list(verifier.TWO_CLOCK_LABELS["en"]),
            "two_clock_labels_zh": list(verifier.TWO_CLOCK_LABELS["zh"]),
        },
    }


def expected_cell_ids(state_codes: Any, repo_root: Path | str | None = None) -> list[str]:
    """Derive the 24 matrix identifiers in the verifier, not in the document."""

    verifier = load_browser_verifier(repo_root)
    return [cell.cell_id for cell in verifier.matrix_from_axes(state_codes)]


def _file_binding_issues(
    binding: Any, *, path: str, expected_path: str, root: Path
) -> list[ValidationIssue]:
    if not isinstance(binding, Mapping):
        return [_issue(path, "product_acceptance_v2.binding_missing", "a bound artifact must be a path/sha256/purpose object")]
    issues: list[ValidationIssue] = []
    if binding.get("path") != expected_path:
        issues.append(
            _issue(
                f"{path}.path",
                "product_acceptance_v2.binding_path",
                "this manifest version must bind its declared artifact kind, not another committed file",
            )
        )
    target = _repo_file(root, binding.get("path"))
    if target is None or not target.is_file():
        issues.append(
            _issue(
                f"{path}.path",
                "product_acceptance_v2.file_unavailable",
                "a bound artifact must be a committed regular file below the repository root",
            )
        )
    elif binding.get("sha256") != _sha256(target):
        issues.append(
            _issue(
                f"{path}.sha256",
                "product_acceptance_v2.file_hash",
                "a bound artifact SHA-256 must match the exact committed bytes",
            )
        )
    return issues


def _predecessor_issues(document: Mapping[str, Any], root: Path) -> list[ValidationIssue]:
    predecessor = _repo_file(root, PRODUCT_ACCEPTANCE_V1_CONFIG_REF)
    if predecessor is None or not predecessor.is_file():
        return [
            _issue(
                "$.supersedes_manifest_ref",
                "product_acceptance_v2.predecessor_unavailable",
                "the superseded v1 manifest must be a committed regular file",
            )
        ]
    try:
        loaded = yaml.safe_load(predecessor.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        loaded = None
    if not isinstance(loaded, Mapping):
        return [
            _issue(
                "$.supersedes_manifest_ref",
                "product_acceptance_v2.predecessor_unreadable",
                "the superseded v1 manifest must parse as a mapping",
            )
        ]
    if (
        document.get("supersedes_manifest_id") != loaded.get("manifest_id")
        or document.get("supersedes_manifest_content_sha256") != loaded.get("content_sha256")
    ):
        return [
            _issue(
                "$.supersedes_manifest_id",
                "product_acceptance_v2.supersession_binding",
                "the predecessor identity and content digest must match the committed v1 manifest exactly",
            )
        ]
    return []


def _design_adjudication_issues(document: Mapping[str, Any], root: Path) -> list[ValidationIssue]:
    target = _repo_file(root, document.get("design_adjudication_ref"))
    if target is None or not target.is_file():
        return [
            _issue(
                "$.design_adjudication_ref",
                "product_acceptance_v2.design_adjudication_pending_base",
                "the named design ruling is not present on this base yet; the bound path must exist before acceptance",
            )
        ]
    if document.get("design_adjudication_sha256") != _sha256(target):
        return [
            _issue(
                "$.design_adjudication_sha256",
                "product_acceptance_v2.design_adjudication_hash",
                "the named design ruling SHA-256 must match the exact committed bytes",
            )
        ]
    return []


def _verifier_issues(document: Mapping[str, Any], root: Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    block = document.get("trusted_verifier")
    if not isinstance(block, Mapping):
        return [_issue("$.trusted_verifier", "product_acceptance_v2.verifier_block_missing", "a trusted verifier block is required")]

    module_path = _repo_file(root, block.get("module_path"))
    if module_path is None or not module_path.is_file():
        return issues + [
            _issue(
                "$.trusted_verifier.module_path",
                "product_acceptance_v2.verifier_module_unavailable",
                "the independent verifier module must be a committed regular file",
            )
        ]
    module_digest = _sha256(module_path)
    if block.get("module_sha256") != module_digest:
        issues.append(
            _issue(
                "$.trusted_verifier.module_sha256",
                "product_acceptance_v2.verifier_module_hash",
                "the verifier module SHA-256 must match the exact committed bytes",
            )
        )

    try:
        verifier = load_browser_verifier(root)
    except (FileNotFoundError, ImportError, SyntaxError) as exc:
        return issues + [
            _issue(
                "$.trusted_verifier.module_path",
                "product_acceptance_v2.verifier_module_unavailable",
                f"the independent verifier module could not be loaded: {type(exc).__name__}",
            )
        ]

    if list(block.get("required_checks") or ()) != list(verifier.REQUIRED_CHECKS):
        issues.append(
            _issue(
                "$.trusted_verifier.required_checks",
                "product_acceptance_v2.required_checks_disagree_with_verifier",
                "required_checks must be exactly the named checks the verifier reports on, in its order",
            )
        )
    if block.get("verifier_version") != verifier.VERIFIER_VERSION:
        issues.append(
            _issue(
                "$.trusted_verifier.verifier_version",
                "product_acceptance_v2.verifier_version_disagreement",
                "the bound verifier version must match the committed verifier module",
            )
        )
    if block.get("receipt_artifact_id") != verifier.RECEIPT_ARTIFACT_ID:
        issues.append(
            _issue(
                "$.trusted_verifier.receipt_artifact_id",
                "product_acceptance_v2.receipt_artifact_disagreement",
                "the bound receipt artifact id must match the artifact the verifier writes",
            )
        )

    capture_state = block.get("capture_state")
    if capture_state == "not_run":
        issues.append(
            _issue(
                "$.trusted_verifier.capture_state",
                "product_acceptance_v2.trusted_browser_capture_pending",
                "design acceptance is pending capture: the independent verifier has not written a receipt for this matrix yet",
            )
        )
        return issues

    issues.extend(_receipt_issues(document, block, root, module_digest, verifier))
    return issues


def _receipt_issues(
    document: Mapping[str, Any],
    block: Mapping[str, Any],
    root: Path,
    module_digest: str,
    verifier: ModuleType,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    receipt_file = _repo_file(root, block.get("receipt_path"))
    if receipt_file is None or not receipt_file.is_file():
        return [
            _issue(
                "$.trusted_verifier.receipt_path",
                "product_acceptance_v2.verifier_receipt_unavailable",
                "a capture claim requires the receipt file the verifier wrote to be present",
            )
        ]
    raw = receipt_file.read_bytes()
    if block.get("receipt_sha256") != hashlib.sha256(raw).hexdigest():
        return [
            _issue(
                "$.trusted_verifier.receipt_sha256",
                "product_acceptance_v2.verifier_receipt_digest_mismatch",
                "the bound receipt digest must be the SHA-256 of the exact bytes the verifier wrote",
            )
        ]
    try:
        receipt = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return [
            _issue(
                "$.trusted_verifier.receipt_path",
                "product_acceptance_v2.verifier_receipt_unreadable",
                "the bound receipt must be the JSON document the verifier wrote",
            )
        ]
    if not isinstance(receipt, Mapping):
        return [
            _issue(
                "$.trusted_verifier.receipt_path",
                "product_acceptance_v2.verifier_receipt_unreadable",
                "the bound receipt must be the JSON document the verifier wrote",
            )
        ]

    if (
        receipt.get("artifact") != verifier.RECEIPT_ARTIFACT_ID
        or receipt.get("verifier_module_ref") != block.get("module_path")
        or receipt.get("verifier_module_sha256") != module_digest
    ):
        issues.append(
            _issue(
                "$.trusted_verifier.receipt_path",
                "product_acceptance_v2.receipt_not_produced_by_trusted_verifier",
                "the receipt must name the bound verifier module and its exact committed bytes as its producer",
            )
        )
    if list(receipt.get("required_checks") or ()) != list(verifier.REQUIRED_CHECKS):
        issues.append(
            _issue(
                "$.trusted_verifier.receipt_path",
                "product_acceptance_v2.receipt_checks_incomplete",
                "the receipt must report on every named check the contract requires",
            )
        )
    if receipt.get("gate_parameters") != verifier.gate_parameters():
        issues.append(
            _issue(
                "$.trusted_verifier.receipt_path",
                "product_acceptance_v2.receipt_gate_parameters_disagreement",
                "the receipt gate parameters must be the constants the verifier owns",
            )
        )

    matrix = document.get("matrix")
    declared_ids = list(matrix.get("cell_ids") or ()) if isinstance(matrix, Mapping) else []
    receipt_cells = receipt.get("cells")
    receipt_ids = (
        [
            cell.get("cell", {}).get("cell_id")
            for cell in receipt_cells
            if isinstance(cell, Mapping) and isinstance(cell.get("cell"), Mapping)
        ]
        if isinstance(receipt_cells, list)
        else []
    )
    if receipt_ids != declared_ids:
        issues.append(
            _issue(
                "$.trusted_verifier.receipt_path",
                "product_acceptance_v2.receipt_matrix_mismatch",
                "the receipt must cover exactly the declared capture matrix, in order",
            )
        )
    if receipt.get("state") != verifier.RUN_STATE_PASSED:
        issues.append(
            _issue(
                "$.trusted_verifier.capture_state",
                "product_acceptance_v2.verifier_reported_failure",
                "the independent verifier did not report a passing capture for this matrix",
            )
        )
    elif block.get("capture_state") != "passed":
        issues.append(
            _issue(
                "$.trusted_verifier.capture_state",
                "product_acceptance_v2.capture_state_disagreement",
                "the bound capture state must match the state the verifier recorded",
            )
        )
    return issues


def product_acceptance_v2_semantic_issues(
    document: Mapping[str, Any], *, repo_root: Path | str | None = None
) -> list[ValidationIssue]:
    """Return every deterministic semantic failure for one v2 manifest document."""

    if not isinstance(document, Mapping):
        return [_issue("$", "product_acceptance_v2.document", "a product acceptance manifest must be a JSON object")]
    root = _repo_root(repo_root)
    issues: list[ValidationIssue] = []

    payload = {key: value for key, value in document.items() if key not in {"manifest_id", "content_sha256"}}
    try:
        digest = canonical_json_sha256(payload)
    except ContractError:
        return [_issue("$", "product_acceptance_v2.canonical_payload", "a product acceptance manifest must be canonicalizable finite JSON")]
    if document.get("content_sha256") != digest:
        issues.append(
            _issue(
                "$.content_sha256",
                "product_acceptance_v2.hash",
                "content_sha256 must bind the canonical payload excluding manifest_id and content_sha256",
            )
        )
    if document.get("manifest_id") != f"{MANIFEST_ID_PREFIX}{digest[:24]}":
        issues.append(
            _issue(
                "$.manifest_id",
                "product_acceptance_v2.identity",
                "manifest_id must derive from the canonical content SHA-256",
            )
        )

    issues.extend(_predecessor_issues(document, root))
    issues.extend(_design_adjudication_issues(document, root))

    design_spec = _repo_file(root, document.get("design_spec_ref"))
    if design_spec is None or not design_spec.is_file():
        issues.append(_issue("$.design_spec_ref", "product_acceptance_v2.file_unavailable", "the design spec must be a committed regular file"))
    elif document.get("design_spec_sha256") != _sha256(design_spec):
        issues.append(_issue("$.design_spec_sha256", "product_acceptance_v2.file_hash", "the design spec SHA-256 must match the exact committed bytes"))

    for field_name, expected_path in (
        ("reference_fixture", "data/biocatalyst/fixtures/biocatalyst_d0a_reference_fixture.v1.json"),
        ("benchmark_corpus", "data/biocatalyst/fixtures/biocatalyst_d0a_benchmark_corpus.v1.json"),
    ):
        issues.extend(
            _file_binding_issues(
                document.get(field_name), path=f"$.{field_name}", expected_path=expected_path, root=root
            )
        )

    authority = document.get("authority")
    if isinstance(authority, Mapping) and any(bool(value) for value in authority.values()):
        issues.append(
            _issue(
                "$.authority",
                "product_acceptance_v2.authority_must_not_authorize",
                "a design acceptance manifest authorizes nothing; every authority flag must stay false",
            )
        )

    approval = document.get("approval")
    if isinstance(approval, Mapping):
        recorded = approval.get("status") in {"approved", "approved_with_amendments", "rejected"}
        if recorded and not (
            isinstance(approval.get("named_reviewer"), str)
            and approval["named_reviewer"].strip()
            and isinstance(approval.get("recorded_at"), str)
            and approval["recorded_at"].strip()
            and approval.get("reviewer_role") == "fable_or_opus_design_owner"
        ):
            issues.append(
                _issue(
                    "$.approval",
                    "product_acceptance_v2.approval_incomplete",
                    "a recorded ruling requires a named reviewer, the design-owner role, and a recorded_at stamp",
                )
            )
        if approval.get("status") == "pending" and approval.get("ruling") != "pending":
            issues.append(
                _issue(
                    "$.approval.ruling",
                    "product_acceptance_v2.approval_ruling_disagreement",
                    "a pending approval cannot carry a decided ruling",
                )
            )

    try:
        expected_gates = expected_gate_parameters(root)
    except (FileNotFoundError, ImportError, SyntaxError, AttributeError):
        expected_gates = None
    if expected_gates is not None and document.get("gates") != expected_gates:
        issues.append(
            _issue(
                "$.gates",
                "product_acceptance_v2.gate_parameters_disagree_with_verifier",
                "the declared gate parameters must equal the constants the independent verifier owns",
            )
        )

    matrix = document.get("matrix")
    if isinstance(matrix, Mapping):
        try:
            derived = expected_cell_ids(matrix.get("required_state_codes"), root)
        except (FileNotFoundError, ImportError, SyntaxError, AttributeError, ValueError, TypeError):
            derived = None
        if derived is not None and list(matrix.get("cell_ids") or ()) != derived:
            issues.append(
                _issue(
                    "$.matrix.cell_ids",
                    "product_acceptance_v2.matrix_cell_ids",
                    "the capture matrix identifiers must be the ones the verifier derives from the frozen axes",
                )
            )

    issues.extend(_verifier_issues(document, root))

    state = document.get("state")
    verifier_block = document.get("trusted_verifier")
    capture_state = verifier_block.get("capture_state") if isinstance(verifier_block, Mapping) else None
    if state == "design_accepted_capture_complete" and capture_state != "passed":
        issues.append(
            _issue(
                "$.state",
                "product_acceptance_v2.state_capture_disagreement",
                "design acceptance requires a passing independent capture",
            )
        )
    return sorted(set(issues))


def validate_biocatalyst_product_acceptance_manifest_v2(
    document: Any, *, repo_root: Path | str | None = None
) -> None:
    """Fail closed unless schema and v2 acceptance controls both hold.

    This -- not generic ``validate_contract`` -- is the acceptance gate. Generic
    registry validation is schema shape only and reads no bound file.
    """

    root = _repo_root(repo_root)
    registry = ContractRegistry(root)
    schema_issues = list(registry.issues(PRODUCT_ACCEPTANCE_V2_CONTRACT_ID, document))
    if isinstance(document, Mapping):
        semantic_issues = product_acceptance_v2_semantic_issues(document, repo_root=root)
    else:
        semantic_issues = [_issue("$", "product_acceptance_v2.document", "a product acceptance manifest must be a JSON object")]
    issues = tuple(sorted(set(schema_issues + semantic_issues)))
    if issues:
        raise ContractValidationError(PRODUCT_ACCEPTANCE_V2_CONTRACT_ID, issues)


def load_product_acceptance_v2_manifest(repo_root: Path | str | None = None) -> dict[str, Any]:
    """Read the committed v2 manifest instance without validating it."""

    root = _repo_root(repo_root)
    target = _repo_file(root, PRODUCT_ACCEPTANCE_V2_CONFIG_REF)
    if target is None or not target.is_file():
        raise FileNotFoundError(PRODUCT_ACCEPTANCE_V2_CONFIG_REF)
    loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("the v2 product acceptance manifest must be a mapping")
    return loaded
