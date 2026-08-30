"""Validate and render the durable Mastermind semantic system map.

This builder deliberately sits above the operational registries.  The curated
``config/mastermind_programs.yml`` owns semantic intent and boundaries; Synapse
and lobe charters continue to own artifact- and organ-level truth.  The script
only reads those sources and writes one deterministic document.

Default validation is hermetic to this repository.  Sibling-repository paths
are syntax-checked but are only opened when ``--cross-repo`` is supplied or an
explicit ``--repo-root REPOSITORY=/path`` is provided.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

try:
    import yaml
    from yaml.constructor import ConstructorError
    from yaml.nodes import MappingNode
except ImportError as exc:  # pragma: no cover - environment failure, not logic
    raise SystemExit("PyYAML is required to build the Mastermind system map") from exc


SCHEMA = "mastermind_programs.v1"
PROJECT_REPOSITORIES = frozenset({"macro", "terminal", "mastermind"})
RELATION_MODES = frozenset(
    {"conceptual", "planned", "implemented", "contracted", "research_adapter"}
)
HIGH_AUTHORITY_CLASSES = frozenset(
    {"decision_bearing", "deterministic_control", "operational_control"}
)
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "config" / "mastermind_programs.yml"
DEFAULT_SYNAPSE = REPO_ROOT / "config" / "synapse.yml"
DEFAULT_LOBE_CHARTERS = REPO_ROOT / "config" / "lobe_charters.yml"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "MASTERMIND_SYSTEM_MAP.md"

REQUIRED_TOP_LEVEL = {
    "schema",
    "meta",
    "ontology",
    "categories",
    "repositories",
    "programs",
    "product_surfaces",
    "cross_repo_contracts",
    "repository_domain_coverage",
    "owner_program_dispositions",
}

EXPECTED_VOCABULARIES: dict[str, set[str]] = {
    "program_kinds": {
        "cognitive_system",
        "cognitive_service",
        "decision_engine",
        "intelligence_program",
        "semantic_rail",
        "data_plane",
        "research_program",
        "infrastructure",
        "project_infrastructure",
    },
    "lifecycle_states": {
        "operating",
        "building",
        "planned",
        "parked",
        "dormant",
        "deprecated",
    },
    "scopes": {"repository", "project"},
    "relationship_types": {
        "contains",
        "extends",
        "consumes_from",
        "feeds_context_to",
        "governs",
        "evaluates",
        "persists",
        "renders_through",
        "coordinates_with",
    },
    "relationship_modes": set(RELATION_MODES),
    "repository_roles": {
        "implementation_owner",
        "producer",
        "consumer",
        "adapter",
        "renderer",
        "publisher",
        "control_plane",
        "state_owner",
        "product_host",
    },
    "contract_flow_types": {
        "data",
        "context",
        "decision_receipt",
        "presentation",
        "publication",
        "authentication",
        "provider_capacity",
        "operational_control",
        "retrieval",
    },
    "owner_dispositions": {
        "mapped",
        "alias_of",
        "subprogram_of",
        "infrastructure_only",
        "unresolved_split",
        "unresolved",
        "dormant",
        "deprecated",
    },
    "authority_classes": {
        "advisory_only",
        "context_only",
        "display_only",
        "research_only",
        "decision_bearing",
        "deterministic_control",
        "presentation_only",
        "operational_control",
    },
    "domain_dispositions": {
        "mapped",
        "infrastructure_only",
        "proposal_only",
        "prototype_not_deployed",
        "unresolved",
    },
}

PROGRAM_REQUIRED_FIELDS = {
    "name",
    "category",
    "kind",
    "lifecycle_state",
    "scope",
    "purpose",
    "strategic_role",
    "owns",
    "does_not_own",
    "repo_bindings",
    "relationships",
    "canonical_docs",
    "implementation",
    "product_surfaces",
}
PROGRAM_OPTIONAL_FIELDS = {
    "decision_boundary",
    "registry_bindings",
    "notes",
    "aliases",
    "order",
    "books",
    "ontology_status",
}


class SystemMapError(Exception):
    """Base error for deterministic, user-actionable build failures."""


class DuplicateKeyError(SystemMapError):
    """Raised when a YAML mapping repeats a key."""


class ValidationError(SystemMapError):
    """Raised after collecting all registry validation errors."""

    def __init__(self, errors: Sequence[str]):
        self.errors = tuple(errors)
        super().__init__("\n".join(self.errors))


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate keys at every mapping depth."""

    reject_duplicate_keys = True

    def __init__(self, stream: Any) -> None:
        super().__init__(stream)
        self.duplicate_keys: list[str] = []


class _LegacyCompatLoader(_UniqueKeyLoader):
    """Last-value-compatible loader for pre-existing operational registries."""

    reject_duplicate_keys = False


def _construct_unique_mapping(
    loader: _UniqueKeyLoader, node: MappingNode, deep: bool = False
) -> dict[Any, Any]:
    if not isinstance(node, MappingNode):
        raise ConstructorError(None, None, "expected a mapping node", node.start_mark)
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            repeated = key in result
        except TypeError as exc:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if repeated:
            mark = key_node.start_mark
            message = (
                f"duplicate YAML key {key!r} at line {mark.line + 1}, "
                f"column {mark.column + 1}"
            )
            if loader.reject_duplicate_keys:
                raise DuplicateKeyError(message)
            loader.duplicate_keys.append(message)
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)
_LegacyCompatLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


@dataclass(frozen=True)
class LoadedYaml:
    path: Path
    data: Mapping[str, Any]
    sha256: str
    duplicate_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class RepoPathRef:
    repository: str
    path: str
    context: str


@dataclass(frozen=True)
class RelationshipEntry:
    target: str
    mode: str = "conceptual"
    note: str = ""
    contract: str = ""
    evidence_refs: tuple[str, ...] = ()
    authority_transfer: bool = False


@dataclass(frozen=True)
class DerivedProgramFacts:
    synapse_owners: tuple[str, ...]
    lobe_owners: tuple[str, ...]
    artifact_ids: tuple[str, ...]
    lobe_ids: tuple[str, ...]
    tier_counts: tuple[tuple[str, int], ...]
    information_domains: tuple[str, ...]


@dataclass(frozen=True)
class BuildModel:
    registry: Mapping[str, Any]
    synapse: Mapping[str, Any]
    lobe_charters: Mapping[str, Any]
    primary_repository: str
    repository_roots: Mapping[str, Path]
    validated_repositories: frozenset[str]
    source_hashes: tuple[tuple[str, str], ...]
    dispositions: Mapping[tuple[str, str], Mapping[str, Any]]
    derived: Mapping[str, DerivedProgramFacts]
    compatibility_notes: tuple[str, ...] = ()


class _Errors:
    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, context: str, message: str) -> None:
        self.items.append(f"{context}: {message}")

    def require(self, condition: bool, context: str, message: str) -> bool:
        if not condition:
            self.add(context, message)
            return False
        return True

    def raise_if_any(self) -> None:
        if self.items:
            raise ValidationError(sorted(set(self.items)))


def load_yaml(path: Path, *, reject_duplicates: bool = True) -> LoadedYaml:
    """Load YAML safely and hash exact bytes.

    The curated semantic registry uses strict duplicate rejection.  Existing
    operational registries may be loaded in compatibility mode because this
    renderer must not force unrelated authority-registry repairs into the same
    architecture change; compatibility duplicates are reported in provenance.
    """
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise SystemMapError(f"required source does not exist: {path}") from exc
    except OSError as exc:
        raise SystemMapError(f"could not read required source {path}: {exc}") from exc
    try:
        loader_class = _UniqueKeyLoader if reject_duplicates else _LegacyCompatLoader
        loader = loader_class(raw.decode("utf-8"))
        try:
            parsed = loader.get_single_data()
            duplicate_keys = tuple(loader.duplicate_keys)
        finally:
            loader.dispose()
    except DuplicateKeyError as exc:
        raise DuplicateKeyError(f"{path}: {exc}") from exc
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise SystemMapError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(parsed, Mapping):
        raise SystemMapError(f"{path}: top level must be a mapping")
    return LoadedYaml(
        path=path,
        data=parsed,
        sha256=hashlib.sha256(raw).hexdigest(),
        duplicate_keys=duplicate_keys,
    )


def _mapping(value: Any, errors: _Errors, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        errors.add(context, "must be a mapping")
        return {}
    return value


def _string(value: Any, errors: _Errors, context: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str):
        errors.add(context, "must be a string")
        return ""
    if nonempty and not value.strip():
        errors.add(context, "must not be empty")
    return value.strip()


def _string_list(
    value: Any, errors: _Errors, context: str, *, allow_empty: bool = True
) -> list[str]:
    if not isinstance(value, list):
        errors.add(context, "must be a list")
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        text = _string(item, errors, f"{context}[{index}]")
        if text:
            result.append(text)
    if not allow_empty and not result:
        errors.add(context, "must contain at least one item")
    duplicates = sorted(key for key, count in Counter(result).items() if count > 1)
    if duplicates:
        errors.add(context, f"contains duplicates: {', '.join(duplicates)}")
    return result


def _ordered_items(mapping: Mapping[str, Any]) -> list[tuple[str, Any]]:
    def key(item: tuple[str, Any]) -> tuple[float, str]:
        item_id, value = item
        order: float = float("inf")
        if isinstance(value, Mapping):
            raw_order = value.get("order")
            if isinstance(raw_order, (int, float)) and not isinstance(raw_order, bool):
                order = float(raw_order)
        return order, str(item_id)

    return sorted(((str(k), v) for k, v in mapping.items()), key=key)


def _display_name(item_id: str, value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, Mapping):
        name = value.get("name") or value.get("title")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return item_id


def _primary_repository(registry: Mapping[str, Any], repositories: Mapping[str, Any]) -> str:
    meta = registry.get("meta")
    if isinstance(meta, Mapping):
        candidate = meta.get("primary_repository", meta.get("canonical_home"))
        if isinstance(candidate, str) and candidate in repositories:
            return candidate
    if "macro-dashboard" in repositories:
        return "macro-dashboard"
    return min(str(key) for key in repositories) if repositories else "macro-dashboard"


def _configured_repository_root(record: Any) -> str | None:
    if not isinstance(record, Mapping):
        return None
    for key in ("local_root", "default_root", "workspace_root", "root", "path"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _parse_repo_root_args(values: Sequence[str]) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    for value in values:
        repository, separator, raw_path = value.partition("=")
        if not separator or not repository.strip() or not raw_path.strip():
            raise SystemMapError(
                f"invalid --repo-root {value!r}; expected REPOSITORY=/absolute/or/relative/path"
            )
        repository = repository.strip()
        if repository in roots:
            raise SystemMapError(f"duplicate --repo-root for {repository!r}")
        path = Path(raw_path.strip()).expanduser().resolve()
        if not path.is_dir():
            raise SystemMapError(f"--repo-root {repository} does not name a directory: {path}")
        roots[repository] = path
    return roots


def _resolve_repository_roots(
    repositories: Mapping[str, Any],
    primary_repository: str,
    explicit_roots: Mapping[str, Path],
    cross_repo: bool,
    errors: _Errors,
) -> tuple[dict[str, Path], frozenset[str]]:
    roots: dict[str, Path] = {primary_repository: REPO_ROOT.resolve()}
    validated = {primary_repository}
    for repository, path in explicit_roots.items():
        if repository not in repositories:
            errors.add("--repo-root", f"unknown repository {repository!r}")
            continue
        roots[repository] = path.resolve()
        validated.add(repository)
    if cross_repo:
        for repository, record in repositories.items():
            repository = str(repository)
            if repository in roots:
                continue
            configured = _configured_repository_root(record)
            if configured is None:
                errors.add(
                    f"repositories.{repository}",
                    "--cross-repo requires a local root; pass "
                    f"--repo-root {repository}=/path/to/checkout",
                )
                continue
            candidate = Path(configured).expanduser()
            if not candidate.is_absolute():
                candidate = REPO_ROOT / candidate
            candidate = candidate.resolve()
            if candidate.is_dir():
                roots[repository] = candidate
                validated.add(repository)
            else:
                errors.add(
                    f"repositories.{repository}",
                    f"configured sibling root does not exist: {candidate}; pass --repo-root",
                )
    return roots, frozenset(validated)


def _validate_repository_metadata(
    meta: Mapping[str, Any],
    repositories: Mapping[str, Any],
    errors: _Errors,
) -> Mapping[str, str]:
    if set(repositories) != PROJECT_REPOSITORIES:
        errors.add(
            "repositories",
            "must contain exactly macro, terminal, and mastermind",
        )

    baselines_raw = _mapping(
        meta.get("repository_baselines"), errors, "meta.repository_baselines"
    )
    if set(baselines_raw) != set(repositories):
        errors.add(
            "meta.repository_baselines",
            "must contain exactly one pin for every declared repository",
        )
    baselines: dict[str, str] = {}
    for repository_id in sorted(repositories):
        record = _mapping(
            repositories.get(repository_id),
            errors,
            f"repositories.{repository_id}",
        )
        for field in ("name", "github", "default_branch", "role"):
            _string(
                record.get(field),
                errors,
                f"repositories.{repository_id}.{field}",
            )
        _string_list(
            record.get("owns"),
            errors,
            f"repositories.{repository_id}.owns",
            allow_empty=False,
        )
        _string_list(
            record.get("does_not_own"),
            errors,
            f"repositories.{repository_id}.does_not_own",
            allow_empty=False,
        )

        baseline = baselines_raw.get(repository_id)
        if not isinstance(baseline, str) or len(baseline) != 40 or any(
            character not in "0123456789abcdef" for character in baseline
        ):
            errors.add(
                f"meta.repository_baselines.{repository_id}",
                "must be a full lowercase 40-hex commit SHA",
            )
        else:
            baselines[repository_id] = baseline
    return baselines


def _git_result(root: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _github_slug(remote_url: str) -> str | None:
    normalized = remote_url.strip().removesuffix(".git").rstrip("/")
    if normalized.startswith("git@github.com:"):
        return normalized.split(":", 1)[1]
    marker = "github.com/"
    if marker in normalized:
        return normalized.split(marker, 1)[1]
    return None


def _validate_repository_git_state(
    repositories: Mapping[str, Any],
    baselines: Mapping[str, str],
    roots: Mapping[str, Path],
    audit_repositories: Iterable[str],
    errors: _Errors,
) -> None:
    """Prove optional deep-audit roots, remotes, branches, and baseline ancestry."""
    for repository_id in sorted(set(audit_repositories)):
        root = roots.get(repository_id)
        record = repositories.get(repository_id)
        baseline = baselines.get(repository_id)
        context = f"repositories.{repository_id}.deep_audit"
        if root is None or not isinstance(record, Mapping) or baseline is None:
            errors.add(context, "cannot audit incomplete repository metadata")
            continue

        top = _git_result(root, "rev-parse", "--show-toplevel")
        if top is None or top.returncode != 0:
            errors.add(context, "root is not a readable Git worktree")
            continue
        try:
            discovered_root = Path(top.stdout.strip()).resolve()
        except OSError:
            discovered_root = Path(top.stdout.strip())
        if discovered_root != root.resolve():
            errors.add(context, f"root resolves to nested worktree {discovered_root}")

        remote = _git_result(root, "remote", "get-url", "origin")
        actual_slug = (
            _github_slug(remote.stdout)
            if remote is not None and remote.returncode == 0
            else None
        )
        expected_slug = str(record.get("github", ""))
        if actual_slug is None or actual_slug.lower() != expected_slug.lower():
            errors.add(
                context,
                f"origin must identify {expected_slug!r}; found {actual_slug!r}",
            )

        remote_head = _git_result(
            root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD"
        )
        expected_head = f"origin/{record.get('default_branch', '')}"
        actual_head = (
            remote_head.stdout.strip()
            if remote_head is not None and remote_head.returncode == 0
            else None
        )
        if actual_head != expected_head:
            errors.add(
                context,
                f"origin/HEAD must resolve to {expected_head!r}; found {actual_head!r}",
            )

        commit = _git_result(root, "cat-file", "-e", f"{baseline}^{{commit}}")
        if commit is None or commit.returncode != 0:
            errors.add(context, f"audited baseline commit is unavailable: {baseline}")
            continue
        ancestor = _git_result(root, "merge-base", "--is-ancestor", baseline, "HEAD")
        if ancestor is None or ancestor.returncode != 0:
            errors.add(
                context,
                f"audited baseline {baseline} is not an ancestor of checkout HEAD",
            )
        default_ancestor = _git_result(
            root,
            "merge-base",
            "--is-ancestor",
            baseline,
            expected_head,
        )
        if default_ancestor is None or default_ancestor.returncode != 0:
            errors.add(
                context,
                f"audited baseline {baseline} is not an ancestor of {expected_head}",
            )


def _safe_repo_path(path: str, errors: _Errors, context: str) -> str | None:
    if not isinstance(path, str) or not path.strip():
        errors.add(context, "path must be a non-empty string")
        return None
    path = path.strip()
    if "\\" in path:
        errors.add(context, "path must use repository-relative POSIX separators")
        return None
    raw_path = path.rstrip("/")
    if not raw_path:
        errors.add(context, "path must not resolve to the repository root")
        return None
    raw_parts = raw_path.split("/")
    pure = PurePosixPath(raw_path)
    if pure.is_absolute() or path.startswith("~"):
        errors.add(context, "path must be repository-relative, not absolute")
        return None
    if any(part in {"", ".", ".."} for part in raw_parts):
        errors.add(context, "path may not contain empty, '.' or '..' components")
        return None
    return pure.as_posix()


def _iter_repo_path_refs(
    value: Any,
    repositories: set[str],
    default_repository: str,
    context: str,
    errors: _Errors,
    forced_repository: str | None = None,
) -> Iterable[RepoPathRef]:
    """Yield refs from list form, ``{repo,path}``, or ``repo: [paths]`` form."""
    repository = forced_repository or default_repository
    if value is None:
        return
    if isinstance(value, str):
        safe = _safe_repo_path(value, errors, context)
        if safe is not None:
            yield RepoPathRef(repository, safe, context)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_repo_path_refs(
                item,
                repositories,
                default_repository,
                f"{context}[{index}]",
                errors,
                forced_repository,
            )
        return
    if not isinstance(value, Mapping):
        errors.add(context, "must be a path, path reference, list, or repository mapping")
        return

    explicit_repository = value.get("repository", value.get("repo", repository))
    if not isinstance(explicit_repository, str) or explicit_repository not in repositories:
        errors.add(context, f"references unknown repository {explicit_repository!r}")
        explicit_repository = repository
    if "path" in value:
        safe = _safe_repo_path(value.get("path"), errors, f"{context}.path")
        if safe is not None:
            yield RepoPathRef(explicit_repository, safe, context)
    roots_key = "paths" if "paths" in value else "roots" if "roots" in value else None
    if roots_key is not None:
        paths = value.get(roots_key)
        if not isinstance(paths, list):
            errors.add(f"{context}.{roots_key}", "must be a list")
        else:
            for index, item in enumerate(paths):
                yield from _iter_repo_path_refs(
                    item,
                    repositories,
                    default_repository,
                    f"{context}.{roots_key}[{index}]",
                    errors,
                    explicit_repository,
                )
    if "path" in value or roots_key is not None:
        return

    repository_keys = [str(key) for key in value if str(key) in repositories]
    if repository_keys:
        unknown_keys = {
            str(key)
            for key in value
            if str(key) not in repositories and str(key) not in {"notes", "description"}
        }
        if unknown_keys:
            errors.add(context, f"unknown repository/path keys: {', '.join(sorted(unknown_keys))}")
        for repo_id in sorted(repository_keys):
            yield from _iter_repo_path_refs(
                value[repo_id],
                repositories,
                default_repository,
                f"{context}.{repo_id}",
                errors,
                repo_id,
            )
        return
    errors.add(context, "path reference mapping must contain path, paths, or repository keys")


def _validate_path_refs(
    refs: Iterable[RepoPathRef],
    repository_roots: Mapping[str, Path],
    validated_repositories: set[str] | frozenset[str],
    errors: _Errors,
    allowed_missing: set[tuple[str, str]] | frozenset[tuple[str, str]] = frozenset(),
) -> list[RepoPathRef]:
    result: list[RepoPathRef] = []
    seen: set[tuple[str, str]] = set()
    for ref in refs:
        key = (ref.repository, ref.path)
        if key in seen:
            errors.add(ref.context, f"duplicates repository path {ref.repository}:{ref.path}")
            continue
        seen.add(key)
        result.append(ref)
        if ref.repository not in validated_repositories:
            continue
        root = repository_roots.get(ref.repository)
        if root is None:
            errors.add(ref.context, f"no validated root for repository {ref.repository!r}")
            continue
        candidate = root.joinpath(*PurePosixPath(ref.path).parts)
        try:
            resolved_root = root.resolve()
            resolved_candidate = candidate.resolve(strict=False)
            resolved_candidate.relative_to(resolved_root)
        except (OSError, ValueError):
            errors.add(ref.context, f"path escapes repository root: {ref.path}")
            continue
        if not candidate.exists() and key not in allowed_missing:
            errors.add(ref.context, f"referenced path does not exist: {ref.repository}:{ref.path}")
    return result


def _repo_binding_ids(
    value: Any, repositories: set[str], errors: _Errors, context: str
) -> set[str]:
    result: set[str] = set()
    if isinstance(value, str):
        if value in repositories:
            result.add(value)
        else:
            errors.add(context, f"unknown repository {value!r}")
        return result
    if isinstance(value, list):
        for index, item in enumerate(value):
            result.update(_repo_binding_ids(item, repositories, errors, f"{context}[{index}]"))
        return result
    if not isinstance(value, Mapping):
        errors.add(context, "must be a repository, list, or mapping")
        return result
    explicit = value.get("repository", value.get("repo"))
    if explicit is not None:
        if isinstance(explicit, str) and explicit in repositories:
            result.add(explicit)
        else:
            errors.add(context, f"unknown repository {explicit!r}")
    for key in value:
        if str(key) in repositories:
            result.add(str(key))
    if not result:
        errors.add(context, "does not bind any known repository")
    return result


def _relationship_entries(
    value: Any, errors: _Errors, context: str
) -> list[RelationshipEntry]:
    entries: list[RelationshipEntry] = []

    def visit(item: Any, item_context: str) -> None:
        if isinstance(item, str):
            entries.append(RelationshipEntry(target=item))
            return
        if isinstance(item, list):
            for index, nested in enumerate(item):
                visit(nested, f"{item_context}[{index}]")
            return
        if not isinstance(item, Mapping):
            errors.add(item_context, "must be a target, list, or target mapping")
            return

        explicit_fields = ("target", "program", "product_surface")
        target_fields = [field for field in explicit_fields if field in item]
        if target_fields:
            allowed = {
                *explicit_fields,
                "mode",
                "note",
                "description",
                "contract",
                "evidence_refs",
                "authority_transfer",
            }
            unknown = sorted(str(key) for key in item if str(key) not in allowed)
            if unknown:
                errors.add(item_context, f"unknown relationship fields: {', '.join(unknown)}")
            if len(target_fields) != 1:
                errors.add(item_context, "must declare exactly one target field")
                return
            target = _string(item.get(target_fields[0]), errors, f"{item_context}.target")
            mode = item.get("mode", "conceptual")
            if not isinstance(mode, str) or mode not in RELATION_MODES:
                errors.add(f"{item_context}.mode", f"unknown relationship mode {mode!r}")
                mode = "conceptual"
            note_value = item.get("note", item.get("description", ""))
            note = ""
            if note_value:
                note = _string(note_value, errors, f"{item_context}.note")
            contract_value = item.get("contract", "")
            contract = ""
            if contract_value:
                contract = _string(contract_value, errors, f"{item_context}.contract")
            evidence_value = item.get("evidence_refs", [])
            evidence_refs: list[str] = []
            if evidence_value:
                evidence_refs = _string_list(
                    evidence_value, errors, f"{item_context}.evidence_refs", allow_empty=False
                )
            authority_transfer = item.get("authority_transfer", False)
            if not isinstance(authority_transfer, bool):
                errors.add(f"{item_context}.authority_transfer", "must be a boolean")
                authority_transfer = False
            if mode == "planned" and not note:
                errors.add(item_context, "planned relationships require a note")
            if mode == "contracted" and not contract:
                errors.add(item_context, "contracted relationships require a contract")
            if contract and mode != "contracted":
                errors.add(
                    item_context,
                    "contract may only be declared by a contracted relationship",
                )
            if mode in {"implemented", "research_adapter"} and not evidence_refs:
                errors.add(item_context, f"{mode} relationships require evidence_refs")
            if evidence_refs and mode not in {"implemented", "research_adapter"}:
                errors.add(
                    item_context,
                    "evidence_refs may only be declared by implemented or "
                    "research_adapter relationships",
                )
            if authority_transfer and mode != "contracted":
                errors.add(
                    item_context,
                    "authority transfer may only be declared by a contracted relationship",
                )
            if target:
                entries.append(
                    RelationshipEntry(
                        target=target,
                        mode=mode,
                        note=note,
                        contract=contract,
                        evidence_refs=tuple(evidence_refs),
                        authority_transfer=authority_transfer,
                    )
                )
            return

        # Backward-compatible compact form: target-id: optional note or metadata.
        metadata_keys = {"notes", "note", "description"}
        target_keys = [str(key) for key in item if str(key) not in metadata_keys]
        for target in target_keys:
            nested = item[target]
            if isinstance(nested, Mapping):
                visit({"target": target, **nested}, f"{item_context}.{target}")
            else:
                note = nested if isinstance(nested, str) else ""
                visit({"target": target, "note": note}, f"{item_context}.{target}")

    visit(value, context)
    targets = [entry.target for entry in entries]
    duplicates = sorted(key for key, count in Counter(targets).items() if count > 1)
    if duplicates:
        errors.add(context, f"contains duplicate targets: {', '.join(duplicates)}")
    return entries


def _relationship_targets(value: Any, errors: _Errors, context: str) -> list[str]:
    return [entry.target for entry in _relationship_entries(value, errors, context)]


def _relationship_evidence_path_refs(
    entry: RelationshipEntry,
    repository_ids: set[str],
    context: str,
    errors: _Errors,
) -> list[RepoPathRef]:
    refs: list[RepoPathRef] = []
    for index, raw_ref in enumerate(entry.evidence_refs):
        ref_context = f"{context}.evidence_refs[{index}]"
        if ":" not in raw_ref:
            errors.add(ref_context, "must use REPOSITORY:path form")
            continue
        repository, raw_path = raw_ref.split(":", 1)
        if repository not in repository_ids:
            errors.add(ref_context, f"unknown repository {repository!r}")
            continue
        safe_path = _safe_repo_path(raw_path, errors, ref_context)
        if safe_path is not None:
            refs.append(RepoPathRef(repository, safe_path, ref_context))
    return refs


def _extract_registry_owner_bindings(value: Any) -> tuple[set[str], set[str]]:
    synapse: set[str] = set()
    lobes: set[str] = set()
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if key == "synapse_owner_programs" and isinstance(nested, list):
                synapse.update(str(item) for item in nested if isinstance(item, str))
            elif key == "lobe_owner_programs" and isinstance(nested, list):
                lobes.update(str(item) for item in nested if isinstance(item, str))
            else:
                child_synapse, child_lobes = _extract_registry_owner_bindings(nested)
                synapse.update(child_synapse)
                lobes.update(child_lobes)
    elif isinstance(value, list):
        for nested in value:
            child_synapse, child_lobes = _extract_registry_owner_bindings(nested)
            synapse.update(child_synapse)
            lobes.update(child_lobes)
    return synapse, lobes


def _flatten_dispositions(
    value: Mapping[str, Any], repositories: set[str], primary_repository: str, errors: _Errors
) -> dict[tuple[str, str], Mapping[str, Any]]:
    flattened: dict[tuple[str, str], Mapping[str, Any]] = {}

    def add_owner(repository: str, owner: str, record: Any, context: str) -> None:
        if not isinstance(record, Mapping):
            errors.add(context, "disposition must be a mapping")
            return
        if not owner:
            errors.add(context, "owner identity must not be empty")
            return
        flattened[(repository, owner)] = record

    for key, nested in value.items():
        key = str(key)
        if key in repositories and isinstance(nested, Mapping):
            owner_map: Any = nested.get("owners", nested.get("dispositions", nested))
            if not isinstance(owner_map, Mapping):
                errors.add(f"owner_program_dispositions.{key}", "must contain an owner mapping")
                continue
            for owner, record in owner_map.items():
                add_owner(key, str(owner), record, f"owner_program_dispositions.{key}.{owner}")
        else:
            add_owner(
                primary_repository,
                key,
                nested,
                f"owner_program_dispositions.{key}",
            )
    return flattened


def _disposition_kind(record: Mapping[str, Any]) -> str | None:
    value = record.get("disposition", record.get("status"))
    return value if isinstance(value, str) else None


def _disposition_target(record: Mapping[str, Any]) -> str | None:
    for key in (
        "program",
        "target_program",
        "maps_to",
        "alias_of",
        "parent_program",
        "subprogram_of",
    ):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _split_candidates(record: Mapping[str, Any]) -> list[str]:
    for key in (
        "candidates",
        "candidate_programs",
        "programs",
        "target_programs",
        "split_between",
    ):
        value = record.get(key)
        if isinstance(value, list):
            return [str(item) for item in value if isinstance(item, str)]
    return []


def _raw_owner_sets(
    synapse: Mapping[str, Any], lobe_charters: Mapping[str, Any], errors: _Errors
) -> tuple[set[str], set[str], Mapping[str, Any], Mapping[str, Any]]:
    artifacts = _mapping(synapse.get("artifacts"), errors, "synapse.artifacts")
    charters = _mapping(lobe_charters.get("charters"), errors, "lobe_charters.charters")
    synapse_owners: set[str] = set()
    lobe_owners: set[str] = set()
    for artifact_id, record in artifacts.items():
        if not isinstance(record, Mapping):
            errors.add(f"synapse.artifacts.{artifact_id}", "must be a mapping")
            continue
        owner = record.get("owner_program")
        if not isinstance(owner, str) or not owner:
            errors.add(f"synapse.artifacts.{artifact_id}.owner_program", "must be a string")
        else:
            synapse_owners.add(owner)
    for lobe_id, record in charters.items():
        if not isinstance(record, Mapping):
            errors.add(f"lobe_charters.charters.{lobe_id}", "must be a mapping")
            continue
        owner = record.get("owner_program")
        if not isinstance(owner, str) or not owner:
            errors.add(f"lobe_charters.charters.{lobe_id}.owner_program", "must be a string")
        else:
            lobe_owners.add(owner)
    return synapse_owners, lobe_owners, artifacts, charters


def _validate_programs(
    registry: Mapping[str, Any],
    repositories: Mapping[str, Any],
    categories: Mapping[str, Any],
    ontology: Mapping[str, Any],
    repository_roots: Mapping[str, Path],
    validated_repositories: frozenset[str],
    allow_generated_output_missing: bool,
    errors: _Errors,
) -> None:
    programs = _mapping(registry.get("programs"), errors, "programs")
    products = _mapping(registry.get("product_surfaces"), errors, "product_surfaces")
    contracts = _mapping(registry.get("cross_repo_contracts"), errors, "cross_repo_contracts")
    repo_ids = {str(key) for key in repositories}
    program_ids = {str(key) for key in programs}
    product_ids = {str(key) for key in products}
    contract_ids = {str(key) for key in contracts}
    kinds = set(ontology.get("program_kinds", []))
    lifecycles = set(ontology.get("lifecycle_states", []))
    scopes = set(ontology.get("scopes", []))
    relationship_types = set(ontology.get("relationship_types", []))
    repository_roles = set(ontology.get("repository_roles", []))
    authority_classes = set(ontology.get("authority_classes", []))
    primary_repository = _primary_repository(registry, repositories)
    allowed_missing: set[tuple[str, str]] = set()
    meta = registry.get("meta")
    if (
        allow_generated_output_missing
        and isinstance(meta, Mapping)
        and isinstance(meta.get("generated_output"), str)
    ):
        generated = _safe_repo_path(
            meta.get("generated_output"), errors, "meta.generated_output"
        )
        if generated:
            allowed_missing.add((primary_repository, generated))

    for program_id, raw_program in programs.items():
        context = f"programs.{program_id}"
        program = _mapping(raw_program, errors, context)
        missing = PROGRAM_REQUIRED_FIELDS - set(program)
        unknown = set(program) - PROGRAM_REQUIRED_FIELDS - PROGRAM_OPTIONAL_FIELDS
        if missing:
            errors.add(context, f"missing required fields: {', '.join(sorted(missing))}")
        if unknown:
            errors.add(context, f"unknown fields: {', '.join(sorted(unknown))}")
        for field in ("name", "purpose", "strategic_role"):
            _string(program.get(field), errors, f"{context}.{field}")
        category = _string(program.get("category"), errors, f"{context}.category")
        if category and category not in categories:
            errors.add(f"{context}.category", f"unknown category {category!r}")
        kind = _string(program.get("kind"), errors, f"{context}.kind")
        if kind and kind not in kinds:
            errors.add(f"{context}.kind", f"unknown kind {kind!r}")
        lifecycle = _string(
            program.get("lifecycle_state"), errors, f"{context}.lifecycle_state"
        )
        if lifecycle and lifecycle not in lifecycles:
            errors.add(f"{context}.lifecycle_state", f"unknown lifecycle {lifecycle!r}")
        scope = _string(program.get("scope"), errors, f"{context}.scope")
        if scope and scope not in scopes:
            errors.add(f"{context}.scope", f"unknown scope {scope!r}")
        _string_list(program.get("owns"), errors, f"{context}.owns")
        _string_list(program.get("does_not_own"), errors, f"{context}.does_not_own")

        bound_repos = _repo_binding_ids(
            program.get("repo_bindings"), repo_ids, errors, f"{context}.repo_bindings"
        )
        _validate_repository_roles(
            program.get("repo_bindings"), repository_roles, errors, f"{context}.repo_bindings"
        )
        default_repository = min(bound_repos) if len(bound_repos) == 1 else primary_repository
        for field in ("canonical_docs", "implementation"):
            refs = _iter_repo_path_refs(
                program.get(field),
                repo_ids,
                default_repository,
                f"{context}.{field}",
                errors,
            )
            _validate_path_refs(
                refs,
                repository_roots,
                validated_repositories,
                errors,
                allowed_missing,
            )

        relationships = _mapping(program.get("relationships"), errors, f"{context}.relationships")
        for relation, raw_targets in relationships.items():
            relation = str(relation)
            rel_context = f"{context}.relationships.{relation}"
            if relation not in relationship_types:
                errors.add(rel_context, f"unknown relationship type {relation!r}")
            for edge in _relationship_entries(raw_targets, errors, rel_context):
                target = edge.target
                valid_targets = program_ids | (product_ids if relation == "renders_through" else set())
                if target not in valid_targets:
                    errors.add(rel_context, f"unknown relationship target {target!r}")
                if target == str(program_id):
                    errors.add(rel_context, "program may not relate to itself")
                if edge.contract and edge.contract not in contract_ids:
                    errors.add(rel_context, f"unknown cross-repository contract {edge.contract!r}")
                evidence_refs = _relationship_evidence_path_refs(
                    edge, repo_ids, rel_context, errors
                )
                _validate_path_refs(
                    evidence_refs,
                    repository_roots,
                    validated_repositories,
                    errors,
                )
                if edge.mode == "contracted" and edge.contract in contracts:
                    contract = contracts[edge.contract]
                    if not isinstance(contract, Mapping):
                        errors.add(rel_context, "contract record must be a mapping")
                    else:
                        from_program = contract.get("from_program")
                        to_program = contract.get("to_program")
                        if from_program != str(program_id) or to_program != target:
                            errors.add(
                                rel_context,
                                f"contract {edge.contract!r} is not endpoint-bound to "
                                f"{program_id!r} -> {target!r}",
                            )
                        if edge.authority_transfer and contract.get("authority_transfer") is not True:
                            errors.add(
                                rel_context,
                                f"contract {edge.contract!r} does not declare authority_transfer=true",
                            )

        product_refs = _string_list(
            program.get("product_surfaces"), errors, f"{context}.product_surfaces"
        )
        for product_id in product_refs:
            if product_id not in product_ids:
                errors.add(f"{context}.product_surfaces", f"unknown product surface {product_id!r}")
        if "aliases" in program:
            _string_list(program.get("aliases"), errors, f"{context}.aliases")
        if "books" in program:
            _string_list(program.get("books"), errors, f"{context}.books")
        if "registry_bindings" in program and not isinstance(program.get("registry_bindings"), Mapping):
            errors.add(f"{context}.registry_bindings", "must be a mapping")
        if "ontology_status" in program:
            status_context = f"{context}.ontology_status"
            status = _mapping(program.get("ontology_status"), errors, status_context)
            status_unknown = set(status) - {
                "classification",
                "consumes_lobe_cap",
                "source",
                "conflict_note",
            }
            status_missing = {
                "classification",
                "consumes_lobe_cap",
                "source",
                "conflict_note",
            } - set(status)
            if status_unknown:
                errors.add(
                    status_context,
                    f"unknown fields: {', '.join(sorted(status_unknown))}",
                )
            if status_missing:
                errors.add(
                    status_context,
                    f"missing fields: {', '.join(sorted(status_missing))}",
                )
            if status.get("classification") != "program_not_lobe":
                errors.add(
                    f"{status_context}.classification",
                    "must equal 'program_not_lobe'",
                )
            if status.get("consumes_lobe_cap") is not False:
                errors.add(
                    f"{status_context}.consumes_lobe_cap",
                    "must be false for program_not_lobe",
                )
            _string(status.get("conflict_note"), errors, f"{status_context}.conflict_note")
            status_refs = list(
                _iter_repo_path_refs(
                    status.get("source"),
                    repo_ids,
                    default_repository,
                    f"{status_context}.source",
                    errors,
                )
            )
            if len(status_refs) != 1:
                errors.add(f"{status_context}.source", "must declare exactly one source")
            _validate_path_refs(
                status_refs,
                repository_roots,
                validated_repositories,
                errors,
            )
        if "decision_boundary" in program:
            boundary = program.get("decision_boundary")
            if isinstance(boundary, Mapping) and "authority_class" in boundary:
                boundary_unknown = set(boundary) - {
                    "authority_class",
                    "summary",
                    "authority_sources",
                }
                if boundary_unknown:
                    errors.add(
                        f"{context}.decision_boundary",
                        f"unknown fields: {', '.join(sorted(boundary_unknown))}",
                    )
                authority_class = boundary.get("authority_class")
                if not isinstance(authority_class, str) or authority_class not in authority_classes:
                    errors.add(
                        f"{context}.decision_boundary.authority_class",
                        f"unknown authority class {authority_class!r}",
                    )
                _string(
                    boundary.get("summary"),
                    errors,
                    f"{context}.decision_boundary.summary",
                )
                authority_refs: list[RepoPathRef] = []
                if "authority_sources" in boundary:
                    authority_refs = list(_iter_repo_path_refs(
                        boundary.get("authority_sources"),
                        repo_ids,
                        default_repository,
                        f"{context}.decision_boundary.authority_sources",
                        errors,
                    ))
                    _validate_path_refs(
                        authority_refs,
                        repository_roots,
                        validated_repositories,
                        errors,
                    )
                if authority_class in HIGH_AUTHORITY_CLASSES and not authority_refs:
                    errors.add(
                        f"{context}.decision_boundary.authority_sources",
                        f"{authority_class} posture requires explicit authority sources",
                    )
            elif not isinstance(boundary, (str, list, Mapping)):
                errors.add(
                    f"{context}.decision_boundary",
                    "must be a string, list, or mapping",
                )


def _validate_repository_roles(
    value: Any, vocabulary: set[str], errors: _Errors, context: str
) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if key in {"role", "roles"}:
                roles = [nested] if isinstance(nested, str) else nested
                if not isinstance(roles, list):
                    errors.add(f"{context}.{key}", "must be a string or list")
                    continue
                for role in roles:
                    if not isinstance(role, str) or role not in vocabulary:
                        errors.add(f"{context}.{key}", f"unknown repository role {role!r}")
            else:
                _validate_repository_roles(nested, vocabulary, errors, f"{context}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _validate_repository_roles(nested, vocabulary, errors, f"{context}[{index}]")


def _validate_products(
    registry: Mapping[str, Any],
    repositories: Mapping[str, Any],
    ontology: Mapping[str, Any],
    repository_roots: Mapping[str, Path],
    validated_repositories: frozenset[str],
    errors: _Errors,
) -> None:
    products = _mapping(registry.get("product_surfaces"), errors, "product_surfaces")
    programs = _mapping(registry.get("programs"), errors, "programs")
    repo_ids = {str(key) for key in repositories}
    program_ids = {str(key) for key in programs}
    repository_roles = set(ontology.get("repository_roles", []))
    primary_repository = _primary_repository(registry, repositories)
    required_fields = {"name", "purpose", "repo_bindings", "programs", "implementation"}
    optional_fields = {"canonical_docs", "canonical_refs", "notes", "order"}
    for product_id, raw_product in products.items():
        context = f"product_surfaces.{product_id}"
        product = _mapping(raw_product, errors, context)
        missing = required_fields - set(product)
        unknown = set(product) - required_fields - optional_fields
        if missing:
            errors.add(context, f"missing required fields: {', '.join(sorted(missing))}")
        if unknown:
            errors.add(context, f"unknown fields: {', '.join(sorted(unknown))}")
        if "name" in product:
            _string(product.get("name"), errors, f"{context}.name")
        else:
            errors.add(context, "missing required field: name")
        _string(product.get("purpose"), errors, f"{context}.purpose")
        bound_repos: set[str] = set()
        if "repo_bindings" in product:
            bound_repos = _repo_binding_ids(
                product.get("repo_bindings"),
                repo_ids,
                errors,
                f"{context}.repo_bindings",
            )
            _validate_repository_roles(
                product.get("repo_bindings"),
                repository_roles,
                errors,
                f"{context}.repo_bindings",
            )
        for field in ("repository", "repo", "host_repository"):
            if field in product:
                repo = product.get(field)
                if not isinstance(repo, str) or repo not in repo_ids:
                    errors.add(f"{context}.{field}", f"unknown repository {repo!r}")
        if "repositories" in product:
            for repo in _string_list(product.get("repositories"), errors, f"{context}.repositories"):
                if repo not in repo_ids:
                    errors.add(f"{context}.repositories", f"unknown repository {repo!r}")
        for field in ("program", "owner_program"):
            if field in product:
                target = product.get(field)
                if not isinstance(target, str) or target not in program_ids:
                    errors.add(f"{context}.{field}", f"unknown program {target!r}")
        for field in ("programs", "owner_programs"):
            if field in product:
                for target in _string_list(product.get(field), errors, f"{context}.{field}"):
                    if target not in program_ids:
                        errors.add(f"{context}.{field}", f"unknown program {target!r}")
        default_repository = min(bound_repos) if len(bound_repos) == 1 else primary_repository
        for field in ("canonical_docs", "canonical_refs", "implementation"):
            if field not in product:
                continue
            refs = _iter_repo_path_refs(
                product.get(field),
                repo_ids,
                default_repository,
                f"{context}.{field}",
                errors,
            )
            _validate_path_refs(refs, repository_roots, validated_repositories, errors)


def _walk_known_references(
    value: Any,
    context: str,
    repository_ids: set[str],
    program_ids: set[str],
    errors: _Errors,
) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            field = str(key)
            child_context = f"{context}.{field}"
            if field in {
                "repo",
                "repository",
                "from_repo",
                "to_repo",
                "producer_repo",
                "consumer_repo",
                "host_repository",
            }:
                if not isinstance(nested, str) or nested not in repository_ids:
                    errors.add(child_context, f"unknown repository {nested!r}")
            elif field in {
                "program",
                "owner_program",
                "producer_program",
                "consumer_program",
                "from_program",
                "to_program",
            }:
                if not isinstance(nested, str) or nested not in program_ids:
                    errors.add(child_context, f"unknown program {nested!r}")
            elif field in {"repositories", "repos"} and isinstance(nested, list):
                for repo in nested:
                    if not isinstance(repo, str) or repo not in repository_ids:
                        errors.add(child_context, f"unknown repository {repo!r}")
            elif field in {"programs", "owner_programs"} and isinstance(nested, list):
                for program in nested:
                    if not isinstance(program, str) or program not in program_ids:
                        errors.add(child_context, f"unknown program {program!r}")
            elif field in {"product_surface", "product_surfaces"}:
                # Product references are validated by the caller where the product
                # vocabulary is available; recurse here for repo/program fields.
                pass
            _walk_known_references(nested, child_context, repository_ids, program_ids, errors)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _walk_known_references(
                nested, f"{context}[{index}]", repository_ids, program_ids, errors
            )


def _validate_contracts_and_coverage(
    registry: Mapping[str, Any],
    repositories: Mapping[str, Any],
    ontology: Mapping[str, Any],
    repository_roots: Mapping[str, Path],
    validated_repositories: frozenset[str],
    errors: _Errors,
) -> None:
    contracts = _mapping(registry.get("cross_repo_contracts"), errors, "cross_repo_contracts")
    coverage = _mapping(
        registry.get("repository_domain_coverage"), errors, "repository_domain_coverage"
    )
    programs = _mapping(registry.get("programs"), errors, "programs")
    repository_ids = {str(key) for key in repositories}
    program_ids = {str(key) for key in programs}
    product_ids = {
        str(key)
        for key in _mapping(registry.get("product_surfaces"), errors, "product_surfaces")
    }
    flow_types = set(ontology.get("contract_flow_types", []))
    repository_roles = set(ontology.get("repository_roles", []))
    domain_dispositions = set(ontology.get("domain_dispositions", []))
    primary_repository = _primary_repository(registry, repositories)
    contract_required = {
        "name",
        "flow_type",
        "purpose",
        "participants",
        "authority_note",
        "canonical_refs",
        "implementation",
    }
    contract_optional = {
        "notes",
        "order",
        "from_program",
        "to_program",
        "authority_transfer",
    }
    for contract_id, raw_contract in contracts.items():
        context = f"cross_repo_contracts.{contract_id}"
        contract = _mapping(raw_contract, errors, context)
        missing = contract_required - set(contract)
        unknown = set(contract) - contract_required - contract_optional
        if missing:
            errors.add(context, f"missing required fields: {', '.join(sorted(missing))}")
        if unknown:
            errors.add(context, f"unknown fields: {', '.join(sorted(unknown))}")
        endpoint_fields = {"from_program", "to_program"} & set(contract)
        if endpoint_fields and endpoint_fields != {"from_program", "to_program"}:
            errors.add(
                context,
                "from_program and to_program must be declared together",
            )
        if "authority_transfer" in contract and not isinstance(
            contract.get("authority_transfer"), bool
        ):
            errors.add(f"{context}.authority_transfer", "must be a boolean")
        for field in ("name", "purpose", "authority_note"):
            _string(contract.get(field), errors, f"{context}.{field}")
        flow_type = contract.get("flow_type")
        if not isinstance(flow_type, str) or flow_type not in flow_types:
            errors.add(f"{context}.flow_type", f"unknown contract flow type {flow_type!r}")
        _walk_known_references(contract, context, repository_ids, program_ids, errors)
        if "participants" in contract:
            participants = contract.get("participants")
            if not isinstance(participants, list):
                errors.add(f"{context}.participants", "must be a list")
            else:
                for index, participant in enumerate(participants):
                    if not isinstance(participant, Mapping):
                        errors.add(f"{context}.participants[{index}]", "must be a mapping")
                        continue
                    role = participant.get("role")
                    if not isinstance(role, str) or role not in repository_roles:
                        errors.add(
                            f"{context}.participants[{index}].role",
                            f"unknown repository role {role!r}",
                        )
        for field in ("canonical_docs", "canonical_refs", "implementation"):
            if field not in contract:
                continue
            refs = _iter_repo_path_refs(
                contract.get(field),
                repository_ids,
                primary_repository,
                f"{context}.{field}",
                errors,
            )
            _validate_path_refs(refs, repository_roots, validated_repositories, errors)
    missing_coverage = repository_ids - {str(key) for key in coverage}
    if missing_coverage:
        errors.add(
            "repository_domain_coverage",
            "missing repositories: " + ", ".join(sorted(missing_coverage)),
        )
    coverage_required = {
        "domain",
        "roots",
        "disposition",
        "programs",
        "product_surfaces",
        "notes",
    }
    coverage_optional = {"order"}
    for repository, raw_record in coverage.items():
        if str(repository) not in repository_ids:
            errors.add(
                f"repository_domain_coverage.{repository}",
                f"unknown repository {repository!r}",
            )
        _walk_known_references(
            raw_record,
            f"repository_domain_coverage.{repository}",
            repository_ids,
            program_ids,
            errors,
        )
        records = raw_record if isinstance(raw_record, list) else [raw_record]
        seen_domains: set[str] = set()
        for index, record in enumerate(records):
            record_context = f"repository_domain_coverage.{repository}[{index}]"
            if not isinstance(record, Mapping):
                errors.add(record_context, "must be a mapping")
                continue
            missing = coverage_required - set(record)
            unknown = set(record) - coverage_required - coverage_optional
            if missing:
                errors.add(record_context, f"missing required fields: {', '.join(sorted(missing))}")
            if unknown:
                errors.add(record_context, f"unknown fields: {', '.join(sorted(unknown))}")
            domain = _string(record.get("domain"), errors, f"{record_context}.domain")
            if domain in seen_domains:
                errors.add(f"{record_context}.domain", f"duplicate domain {domain!r}")
            seen_domains.add(domain)
            _string(record.get("notes"), errors, f"{record_context}.notes")
            _string_list(record.get("programs"), errors, f"{record_context}.programs")
            _string_list(
                record.get("product_surfaces"),
                errors,
                f"{record_context}.product_surfaces",
            )
            disposition = record.get("disposition")
            if not isinstance(disposition, str) or disposition not in domain_dispositions:
                errors.add(
                    f"{record_context}.disposition",
                    f"unknown domain disposition {disposition!r}",
                )
            for product in record.get("product_surfaces", []):
                if not isinstance(product, str) or product not in product_ids:
                    errors.add(
                        f"{record_context}.product_surfaces",
                        f"unknown product surface {product!r}",
                    )
            if "roots" in record:
                refs = _iter_repo_path_refs(
                    {"repo": str(repository), "roots": record.get("roots")},
                    repository_ids,
                    str(repository),
                    f"{record_context}.roots",
                    errors,
                )
                _validate_path_refs(refs, repository_roots, validated_repositories, errors)


def _validate_global_repo_paths(
    registry: Mapping[str, Any],
    repositories: Mapping[str, Any],
    repository_roots: Mapping[str, Path],
    validated_repositories: frozenset[str],
    errors: _Errors,
) -> None:
    repository_ids = {str(key) for key in repositories}
    primary_repository = _primary_repository(registry, repositories)
    meta = registry.get("meta")
    if isinstance(meta, Mapping) and "source_registries" in meta:
        refs = _iter_repo_path_refs(
            meta.get("source_registries"),
            repository_ids,
            primary_repository,
            "meta.source_registries",
            errors,
        )
        _validate_path_refs(refs, repository_roots, validated_repositories, errors)
    for repository, record in repositories.items():
        if not isinstance(record, Mapping) or "canonical_orientation" not in record:
            continue
        refs = _iter_repo_path_refs(
            record.get("canonical_orientation"),
            repository_ids,
            str(repository),
            f"repositories.{repository}.canonical_orientation",
            errors,
        )
        _validate_path_refs(refs, repository_roots, validated_repositories, errors)


def _validate_dispositions(
    registry: Mapping[str, Any],
    repositories: Mapping[str, Any],
    ontology: Mapping[str, Any],
    primary_repository: str,
    synapse_owners: set[str],
    lobe_owners: set[str],
    errors: _Errors,
) -> dict[tuple[str, str], Mapping[str, Any]]:
    raw = _mapping(
        registry.get("owner_program_dispositions"), errors, "owner_program_dispositions"
    )
    repo_ids = {str(key) for key in repositories}
    program_ids = {str(key) for key in _mapping(registry.get("programs"), errors, "programs")}
    dispositions = _flatten_dispositions(raw, repo_ids, primary_repository, errors)
    vocabulary = set(ontology.get("owner_dispositions", []))
    for (repository, owner), record in dispositions.items():
        context = f"owner_program_dispositions.{repository}.{owner}"
        allowed_fields = {
            "disposition",
            "status",
            "program",
            "target_program",
            "maps_to",
            "alias_of",
            "parent_program",
            "subprogram_of",
            "candidates",
            "candidate_programs",
            "programs",
            "target_programs",
            "split_between",
            "note",
            "notes",
            "reason",
        }
        unknown_fields = set(record) - allowed_fields
        if unknown_fields:
            errors.add(context, f"unknown fields: {', '.join(sorted(unknown_fields))}")
        kind = _disposition_kind(record)
        if kind not in vocabulary:
            errors.add(context, f"unknown or missing disposition {kind!r}")
            continue
        target = _disposition_target(record)
        if kind in {"mapped", "alias_of", "subprogram_of"}:
            if target is None:
                errors.add(context, f"{kind} requires a target semantic program")
            elif target not in program_ids:
                errors.add(context, f"targets unknown semantic program {target!r}")
        elif target is not None and target not in program_ids:
            errors.add(context, f"targets unknown semantic program {target!r}")
        if kind == "unresolved_split":
            candidates = _split_candidates(record)
            if len(candidates) < 2:
                errors.add(context, "unresolved_split requires at least two candidate programs")
            for candidate in candidates:
                if candidate not in program_ids:
                    errors.add(context, f"split candidate is unknown program {candidate!r}")
        if kind in {"unresolved", "unresolved_split"} and not any(
            isinstance(record.get(field), str) and record.get(field).strip()
            for field in ("note", "notes", "reason")
        ):
            errors.add(context, f"{kind} requires an explanatory note")

    required_owners = synapse_owners | lobe_owners
    missing = sorted(
        owner for owner in required_owners if (primary_repository, owner) not in dispositions
    )
    if missing:
        errors.add(
            "owner_program_dispositions",
            "missing raw owner union coverage for: " + ", ".join(missing),
        )
    return dispositions


def _validate_registry_bindings(
    registry: Mapping[str, Any],
    primary_repository: str,
    synapse_owners: set[str],
    lobe_owners: set[str],
    dispositions: Mapping[tuple[str, str], Mapping[str, Any]],
    errors: _Errors,
) -> None:
    programs = _mapping(registry.get("programs"), errors, "programs")
    seen_synapse: dict[str, str] = {}
    seen_lobes: dict[str, str] = {}
    for program_id, program in programs.items():
        if not isinstance(program, Mapping):
            continue
        synapse_bound: set[str] = set()
        lobe_bound: set[str] = set()
        for field in ("repo_bindings", "registry_bindings"):
            found_synapse, found_lobes = _extract_registry_owner_bindings(program.get(field))
            synapse_bound.update(found_synapse)
            lobe_bound.update(found_lobes)
        for owner in synapse_bound:
            context = f"programs.{program_id}.registry_bindings.synapse_owner_programs"
            if owner not in synapse_owners:
                errors.add(context, f"owner {owner!r} does not exist in Synapse")
            if (primary_repository, owner) not in dispositions:
                errors.add(context, f"owner {owner!r} lacks a disposition")
            previous = seen_synapse.setdefault(owner, str(program_id))
            if previous != str(program_id):
                errors.add(context, f"owner {owner!r} is also bound to program {previous!r}")
        for owner in lobe_bound:
            context = f"programs.{program_id}.registry_bindings.lobe_owner_programs"
            if owner not in lobe_owners:
                errors.add(context, f"owner {owner!r} does not exist in lobe charters")
            if (primary_repository, owner) not in dispositions:
                errors.add(context, f"owner {owner!r} lacks a disposition")
            previous = seen_lobes.setdefault(owner, str(program_id))
            if previous != str(program_id):
                errors.add(context, f"owner {owner!r} is also bound to program {previous!r}")


def _derive_program_facts(
    registry: Mapping[str, Any],
    primary_repository: str,
    artifacts: Mapping[str, Any],
    charters: Mapping[str, Any],
    dispositions: Mapping[tuple[str, str], Mapping[str, Any]],
) -> dict[str, DerivedProgramFacts]:
    programs = registry["programs"]
    owner_targets: dict[str, set[str]] = defaultdict(set)
    for (repository, owner), record in dispositions.items():
        if repository != primary_repository:
            continue
        target = _disposition_target(record)
        if target in programs:
            owner_targets[target].add(owner)
    derived: dict[str, DerivedProgramFacts] = {}
    for program_id, program in programs.items():
        synapse_owners, lobe_owners = _extract_registry_owner_bindings(program)
        synapse_owners.update(owner_targets.get(program_id, set()))
        lobe_owners.update(owner_targets.get(program_id, set()))
        artifact_ids = sorted(
            str(artifact_id)
            for artifact_id, artifact in artifacts.items()
            if isinstance(artifact, Mapping)
            and artifact.get("owner_program") in synapse_owners
        )
        lobe_ids = sorted(
            str(lobe_id)
            for lobe_id, lobe in charters.items()
            if isinstance(lobe, Mapping) and lobe.get("owner_program") in lobe_owners
        )
        tier_counts = Counter(
            str(artifacts[artifact_id].get("tier", "unknown")) for artifact_id in artifact_ids
        )
        domains = sorted(
            {
                str(charters[lobe_id].get("information_domain"))
                for lobe_id in lobe_ids
                if charters[lobe_id].get("information_domain") not in {None, ""}
            }
            | {
                str(artifacts[artifact_id].get("information_domain"))
                for artifact_id in artifact_ids
                if artifacts[artifact_id].get("information_domain") not in {None, ""}
            }
        )
        derived[str(program_id)] = DerivedProgramFacts(
            synapse_owners=tuple(sorted(synapse_owners)),
            lobe_owners=tuple(sorted(lobe_owners)),
            artifact_ids=tuple(artifact_ids),
            lobe_ids=tuple(lobe_ids),
            tier_counts=tuple(sorted(tier_counts.items())),
            information_domains=tuple(domains),
        )
    return derived


def validate_and_build_model(
    registry_source: LoadedYaml,
    synapse_source: LoadedYaml,
    lobe_source: LoadedYaml,
    *,
    explicit_repo_roots: Mapping[str, Path] | None = None,
    cross_repo: bool = False,
    allow_generated_output_missing: bool = True,
) -> BuildModel:
    """Validate all semantic and operational inputs and return render-ready facts."""
    errors = _Errors()
    registry = registry_source.data
    actual_top = set(registry)
    missing_top = REQUIRED_TOP_LEVEL - actual_top
    unknown_top = actual_top - REQUIRED_TOP_LEVEL
    if missing_top:
        errors.add("registry", f"missing top-level keys: {', '.join(sorted(missing_top))}")
    if unknown_top:
        errors.add("registry", f"unknown top-level keys: {', '.join(sorted(unknown_top))}")
    if registry.get("schema") != SCHEMA:
        errors.add("schema", f"must equal {SCHEMA!r}")

    meta = _mapping(registry.get("meta"), errors, "meta")
    _string_list(
        meta.get("known_unresolveds"),
        errors,
        "meta.known_unresolveds",
        allow_empty=False,
    )
    ontology = _mapping(registry.get("ontology"), errors, "ontology")
    categories = _mapping(registry.get("categories"), errors, "categories")
    repositories = _mapping(registry.get("repositories"), errors, "repositories")
    if not categories:
        errors.add("categories", "must not be empty")
    if not repositories:
        errors.add("repositories", "must not be empty")
    baselines = _validate_repository_metadata(meta, repositories, errors)
    for category_id, category in categories.items():
        if not isinstance(category, (str, Mapping)):
            errors.add(f"categories.{category_id}", "must be a name string or mapping")
        elif isinstance(category, Mapping):
            missing = {"name", "description"} - set(category)
            unknown = set(category) - {"name", "description", "order"}
            if missing:
                errors.add(
                    f"categories.{category_id}",
                    f"missing required fields: {', '.join(sorted(missing))}",
                )
            if unknown:
                errors.add(
                    f"categories.{category_id}",
                    f"unknown fields: {', '.join(sorted(unknown))}",
                )
            _string(category.get("name"), errors, f"categories.{category_id}.name")
            _string(
                category.get("description"),
                errors,
                f"categories.{category_id}.description",
            )
    for repository_id, repository in repositories.items():
        if not isinstance(repository, (str, Mapping)):
            errors.add(f"repositories.{repository_id}", "must be a name string or mapping")

    if set(ontology) != set(EXPECTED_VOCABULARIES):
        missing = set(EXPECTED_VOCABULARIES) - set(ontology)
        unknown = set(ontology) - set(EXPECTED_VOCABULARIES)
        if missing:
            errors.add("ontology", f"missing vocabularies: {', '.join(sorted(missing))}")
        if unknown:
            errors.add("ontology", f"unknown vocabularies: {', '.join(sorted(unknown))}")
    for key, expected in EXPECTED_VOCABULARIES.items():
        values = _string_list(ontology.get(key), errors, f"ontology.{key}", allow_empty=False)
        actual = set(values)
        if actual != expected:
            missing = expected - actual
            unknown = actual - expected
            parts: list[str] = []
            if missing:
                parts.append("missing " + ", ".join(sorted(missing)))
            if unknown:
                parts.append("unknown " + ", ".join(sorted(unknown)))
            errors.add(f"ontology.{key}", "; ".join(parts))

    primary_repository = _primary_repository(registry, repositories)
    if primary_repository not in repositories:
        errors.add("meta.primary_repository", f"unknown repository {primary_repository!r}")
    explicit_roots = explicit_repo_roots or {}
    roots, validated_repositories = _resolve_repository_roots(
        repositories,
        primary_repository,
        explicit_roots,
        cross_repo,
        errors,
    )
    audit_repositories = (
        set(validated_repositories) if cross_repo else set(explicit_roots)
    )
    if audit_repositories:
        _validate_repository_git_state(
            repositories,
            baselines,
            roots,
            audit_repositories,
            errors,
        )

    _validate_programs(
        registry,
        repositories,
        categories,
        ontology,
        roots,
        validated_repositories,
        allow_generated_output_missing,
        errors,
    )
    _validate_products(
        registry,
        repositories,
        ontology,
        roots,
        validated_repositories,
        errors,
    )
    _validate_contracts_and_coverage(
        registry,
        repositories,
        ontology,
        roots,
        validated_repositories,
        errors,
    )
    _validate_global_repo_paths(
        registry,
        repositories,
        roots,
        validated_repositories,
        errors,
    )
    synapse_owners, lobe_owners, artifacts, charters = _raw_owner_sets(
        synapse_source.data, lobe_source.data, errors
    )
    dispositions = _validate_dispositions(
        registry,
        repositories,
        ontology,
        primary_repository,
        synapse_owners,
        lobe_owners,
        errors,
    )
    _validate_registry_bindings(
        registry,
        primary_repository,
        synapse_owners,
        lobe_owners,
        dispositions,
        errors,
    )
    errors.raise_if_any()

    derived = _derive_program_facts(
        registry, primary_repository, artifacts, charters, dispositions
    )
    source_hashes = (
        (_source_label(registry_source.path), registry_source.sha256),
        (_source_label(synapse_source.path), synapse_source.sha256),
        (_source_label(lobe_source.path), lobe_source.sha256),
    )
    compatibility_notes = tuple(
        f"{_source_label(source.path)}: {message}; compatibility load kept the last value"
        for source in (synapse_source, lobe_source)
        for message in source.duplicate_keys
    )
    return BuildModel(
        registry=registry,
        synapse=synapse_source.data,
        lobe_charters=lobe_source.data,
        primary_repository=primary_repository,
        repository_roots=roots,
        validated_repositories=validated_repositories,
        source_hashes=tuple(sorted(source_hashes)),
        dispositions=dispositions,
        derived=derived,
        compatibility_notes=compatibility_notes,
    )


def _source_label(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def _md_cell(value: Any) -> str:
    if value is None or value == "" or value == [] or value == {}:
        return "—"
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, Mapping):
        text = "; ".join(
            f"{key}: {_md_cell(nested)}" for key, nested in sorted(value.items(), key=lambda item: str(item[0]))
        )
    elif isinstance(value, list):
        text = ", ".join(_md_cell(item) for item in value)
    else:
        text = str(value)
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _append_text_block(lines: list[str], value: Any) -> None:
    if isinstance(value, str):
        lines.extend([value.strip(), ""])
    elif isinstance(value, list):
        for item in value:
            lines.append(f"- {_md_cell(item)}")
        lines.append("")
    elif isinstance(value, Mapping):
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
            lines.append(f"- **{key}:** {_md_cell(item)}")
        lines.append("")


def _repo_ref_strings(value: Any, repository_ids: set[str], default_repository: str) -> list[str]:
    errors = _Errors()
    refs = list(
        _iter_repo_path_refs(
            value,
            repository_ids,
            default_repository,
            "render",
            errors,
        )
    )
    # Validation has already run; rendering should not introduce a second error mode.
    return [f"`{ref.repository}:{ref.path}`" for ref in refs]


def _program_repository_ids(program: Mapping[str, Any], repository_ids: set[str]) -> list[str]:
    errors = _Errors()
    return sorted(_repo_binding_ids(program.get("repo_bindings"), repository_ids, errors, "render"))


def _repository_binding_labels(value: Any, repository_ids: set[str]) -> list[str]:
    bindings: dict[str, set[str]] = defaultdict(set)

    def visit(item: Any) -> None:
        if isinstance(item, str):
            if item in repository_ids:
                bindings[item]
            return
        if isinstance(item, list):
            for nested in item:
                visit(nested)
            return
        if not isinstance(item, Mapping):
            return
        repository = item.get("repo", item.get("repository"))
        if isinstance(repository, str) and repository in repository_ids:
            raw_roles = item.get("roles", item.get("role", []))
            roles = [raw_roles] if isinstance(raw_roles, str) else raw_roles
            if isinstance(roles, list):
                bindings[repository].update(
                    role for role in roles if isinstance(role, str) and role
                )
            else:
                bindings[repository]
            return
        for key, nested in item.items():
            if str(key) in repository_ids:
                bindings[str(key)]
            visit(nested)

    visit(value)
    labels: list[str] = []
    for repository in sorted(bindings):
        roles = sorted(bindings[repository])
        role_text = f" ({', '.join(f'`{role}`' for role in roles)})" if roles else ""
        labels.append(f"`{repository}`{role_text}")
    return labels


def render_markdown(model: BuildModel) -> str:
    """Render byte-stable Markdown from a validated build model."""
    registry = model.registry
    repositories: Mapping[str, Any] = registry["repositories"]
    categories: Mapping[str, Any] = registry["categories"]
    programs: Mapping[str, Any] = registry["programs"]
    products: Mapping[str, Any] = registry["product_surfaces"]
    contracts: Mapping[str, Any] = registry["cross_repo_contracts"]
    coverage: Mapping[str, Any] = registry["repository_domain_coverage"]
    baselines: Mapping[str, Any] = registry["meta"]["repository_baselines"]
    repository_ids = {str(key) for key in repositories}
    lines: list[str] = [
        "<!-- GENERATED — do not edit by hand. Run `python scripts/build_mastermind_system_map.py`. -->",
        "",
        "# Mastermind System Map",
        "",
        "This is durable semantic architecture. It explains what the organism means; it does not replace artifact wiring, lobe lifecycle, rulings, runtime contracts, or the Active Build Map.",
        "",
        "## Project Topology",
        "",
        "| Repository | Name | Scope | Roles | Audited baseline | Default validation |",
        "|---|---|---|---|---|---|",
    ]
    for repository_id, record in _ordered_items(repositories):
        scope = (record.get("scope") or "repository") if isinstance(record, Mapping) else "repository"
        roles: Any = "—"
        if isinstance(record, Mapping):
            roles = record.get("roles", record.get("role", "—"))
        # Deep cross-repository validation is an optional local audit mode.  Its
        # availability must never change the durable generated bytes.
        validation = (
            "paths validated"
            if repository_id == model.primary_repository
            else "metadata + path syntax; optional deep path audit"
        )
        lines.append(
            f"| `{repository_id}` | {_md_cell(_display_name(repository_id, record))} | "
            f"{_md_cell(scope)} | {_md_cell(roles)} | "
            f"`{str(baselines.get(repository_id, 'unknown'))[:12]}` | {validation} |"
        )
    lines.extend(
        [
            "",
            "## Truth Organization and Reasoning Sequence",
            "",
            "```text",
            "Constitution and rulings",
            "        ↓",
            "Semantic program map              ← durable purpose, ownership, boundaries",
            "        ↓",
            "Synapse + lobe charters           ← operational artifact and organ truth",
            "        ↓",
            "Implementation + tests            ← current behavior",
            "        ↓",
            "Product surfaces                  ← user-visible delivery",
            "```",
            "",
            "Reason in this order:",
            "",
            "1. Find the semantic program and read its ownership boundary.",
            "2. Follow typed program relationships and cross-repository contracts.",
            "3. Use Synapse and lobe charters for artifact, tier, domain, and runtime authority facts.",
            "4. Check rulings and `research/DO_NOT_REBUILD.md` before proposing a new owner or authority path.",
            "5. Confirm implementation and tests before treating prose as current behavior.",
            "6. Use `docs/PROJECT_ACTIVE_BUILD_MAP.md` for three-repository construction state and `docs/ACTIVE_BUILD_MAP.md` for Macro-local detail; never infer live work from this durable map.",
            "",
            "## Architecture Overview",
            "",
            "```text",
            "Mastermind",
        ]
    )
    category_order = [item_id for item_id, _ in _ordered_items(categories)]
    for category_id in category_order:
        category_programs = [
            (program_id, program)
            for program_id, program in _ordered_items(programs)
            if isinstance(program, Mapping) and program.get("category") == category_id
        ]
        lines.append(f"├─ {_display_name(category_id, categories[category_id])} [{category_id}]")
        for index, (program_id, program) in enumerate(category_programs):
            branch = "└─" if index == len(category_programs) - 1 else "├─"
            lines.append(
                f"│  {branch} {_display_name(program_id, program)} "
                f"({program.get('kind')}; {program.get('lifecycle_state')})"
            )
    lines.extend(["```", "", "## Program Cards", ""])

    for category_id in category_order:
        category_programs = [
            (program_id, program)
            for program_id, program in _ordered_items(programs)
            if isinstance(program, Mapping) and program.get("category") == category_id
        ]
        if not category_programs:
            continue
        lines.extend([f"### {_display_name(category_id, categories[category_id])}", ""])
        for program_id, program in category_programs:
            facts = model.derived[program_id]
            repo_ids = _program_repository_ids(program, repository_ids)
            default_repo = repo_ids[0] if len(repo_ids) == 1 else model.primary_repository
            lines.extend(
                [
                    f"#### {_display_name(program_id, program)} (`{program_id}`)",
                    "",
                    f"- **Kind:** `{program.get('kind')}`",
                    f"- **Lifecycle:** `{program.get('lifecycle_state')}`",
                    f"- **Scope:** `{program.get('scope')}`",
                    f"- **Repositories:** {', '.join(f'`{repo}`' for repo in repo_ids) or '—'}",
                    "",
                    str(program.get("purpose", "")).strip(),
                    "",
                    f"**Strategic role.** {str(program.get('strategic_role', '')).strip()}",
                    "",
                    "**Owns**",
                    "",
                ]
            )
            lines.extend(f"- {item}" for item in program.get("owns", []))
            if not program.get("owns"):
                lines.append("- —")
            lines.extend(["", "**Does not own**", ""])
            lines.extend(f"- {item}" for item in program.get("does_not_own", []))
            if not program.get("does_not_own"):
                lines.append("- —")
            tier_text = ", ".join(f"{tier}={count}" for tier, count in facts.tier_counts) or "none"
            ontology_status = program.get("ontology_status")
            if isinstance(ontology_status, Mapping):
                status_sources = _repo_ref_strings(
                    ontology_status.get("source"), repository_ids, default_repo
                )
                lines.extend(
                    [
                        "",
                        "**Ontology status**",
                        "",
                        f"- Classification: `{ontology_status.get('classification')}`",
                        "- Consumes lobe cap: **no**",
                        f"- Binding source: {', '.join(status_sources)}",
                        f"- Conflict: {_md_cell(ontology_status.get('conflict_note'))}",
                        "",
                        "**Operational registry footprint (contradiction-aware)**",
                        "",
                        f"- Synapse owners: {', '.join(f'`{owner}`' for owner in facts.synapse_owners) or 'none'}",
                        f"- Synapse artifacts: **{len(facts.artifact_ids)}**; tier mix: {tier_text}",
                        f"- Contradictory raw lobe-owner labels: {', '.join(f'`{owner}`' for owner in facts.lobe_owners) or 'none'}",
                        f"- Contradictory raw lobe-charter rows: **{len(facts.lobe_ids)}**; these rows do not make the program a lobe",
                        f"- Information domains: {', '.join(f'`{domain}`' for domain in facts.information_domains) or 'none declared'}",
                        "",
                    ]
                )
            else:
                lines.extend(
                    [
                        "",
                        "**Derived operational footprint**",
                        "",
                        f"- Synapse owners: {', '.join(f'`{owner}`' for owner in facts.synapse_owners) or 'none'}",
                        f"- Lobe owners: {', '.join(f'`{owner}`' for owner in facts.lobe_owners) or 'none'}",
                        f"- Synapse artifacts: **{len(facts.artifact_ids)}**; tier mix: {tier_text}",
                        f"- Lobe charters: **{len(facts.lobe_ids)}**",
                        f"- Information domains: {', '.join(f'`{domain}`' for domain in facts.information_domains) or 'none declared'}",
                        "",
                    ]
                )
            relationships = program.get("relationships", {})
            if relationships:
                lines.extend(["**Relationships**", ""])
                relation_order = registry["ontology"]["relationship_types"]
                for relation in relation_order:
                    if relation not in relationships:
                        continue
                    render_errors = _Errors()
                    edges = _relationship_entries(
                        relationships[relation], render_errors, "render"
                    )
                    for edge in edges:
                        detail = f"`{edge.mode}`; authority transfer: "
                        detail += "yes" if edge.authority_transfer else "none"
                        if edge.contract:
                            detail += f"; contract: `{edge.contract}`"
                        if edge.evidence_refs:
                            detail += "; evidence: " + ", ".join(
                                f"`{ref}`" for ref in edge.evidence_refs
                            )
                        suffix = f" — {edge.note}" if edge.note else ""
                        lines.append(
                            f"- `{relation}` → `{edge.target}` ({detail}){suffix}"
                        )
                lines.append("")
            docs = _repo_ref_strings(program.get("canonical_docs"), repository_ids, default_repo)
            implementation = _repo_ref_strings(
                program.get("implementation"), repository_ids, default_repo
            )
            lines.extend(
                [
                    f"**Canonical docs:** {', '.join(docs) or '—'}",
                    "",
                    f"**Implementation anchors:** {', '.join(implementation) or '—'}",
                    "",
                    "**Product surfaces:** "
                    + (
                        ", ".join(f"`{surface}`" for surface in program.get("product_surfaces", []))
                        or "—"
                    ),
                    "",
                ]
            )
            if program.get("notes"):
                lines.extend([f"**Notes.** {_md_cell(program.get('notes'))}", ""])
            if program.get("books"):
                lines.extend(
                    [
                        "**Books:** "
                        + ", ".join(f"`{book}`" for book in program.get("books", [])),
                        "",
                    ]
                )

    lines.extend(
        [
            "## Typed Relations",
            "",
            "A plain relationship is conceptual and makes no runtime or authority-transfer claim. Only an explicitly evidenced mode may claim implementation, and cross-repository authority remains governed by the named contract.",
            "",
            "| Source | Relationship | Mode | Target | Contract / evidence | Authority transfer | Note |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    relation_order = registry["ontology"]["relationship_types"]
    for program_id, program in _ordered_items(programs):
        relationships = program.get("relationships", {}) if isinstance(program, Mapping) else {}
        for relation in relation_order:
            if relation not in relationships:
                continue
            render_errors = _Errors()
            for edge in _relationship_entries(relationships[relation], render_errors, "render"):
                proof_parts: list[str] = []
                if edge.contract:
                    proof_parts.append(f"contract `{edge.contract}`")
                if edge.evidence_refs:
                    proof_parts.append(
                        "evidence " + ", ".join(f"`{ref}`" for ref in edge.evidence_refs)
                    )
                proof = "; ".join(proof_parts) or "—"
                authority = "yes" if edge.authority_transfer else "none"
                lines.append(
                    f"| `{program_id}` | `{relation}` | `{edge.mode}` | `{edge.target}` | "
                    f"{proof} | {authority} | {_md_cell(edge.note)} |"
                )
    if lines[-1] == "|---|---|---|---|---|---|---|":
        lines.append("| — | — | — | — | — | — | — |")

    lines.extend(
        [
            "",
            "## Decision Boundaries",
            "",
            "These are non-binding semantic posture summaries, not a second authority system. Binding machine authority remains in Synapse tier/flags, lobe charters, repository constitutions, and named runtime contracts.",
            "",
        ]
    )
    boundaries = [
        (program_id, program)
        for program_id, program in _ordered_items(programs)
        if isinstance(program, Mapping) and program.get("decision_boundary") is not None
    ]
    if not boundaries:
        lines.extend(["No program declares an additional decision boundary.", ""])
    for program_id, program in boundaries:
        boundary = program.get("decision_boundary")
        if not isinstance(boundary, Mapping):
            continue
        facts = model.derived[program_id]
        repo_ids = _program_repository_ids(program, repository_ids)
        default_repo = repo_ids[0] if len(repo_ids) == 1 else model.primary_repository
        explicit_sources = _repo_ref_strings(
            boundary.get("authority_sources", []), repository_ids, default_repo
        )
        registry_checks: list[str] = []
        if facts.synapse_owners:
            registry_checks.append("`macro:config/synapse.yml`")
        if facts.lobe_owners:
            registry_checks.append("`macro:config/lobe_charters.yml`")
        guardrails: list[str] = []
        for repo_id in repo_ids:
            if repo_id == "macro":
                guardrails.append("`macro:CLAUDE.md`")
            elif repo_id == "terminal":
                guardrails.append("`terminal:terminal/AGENTS.md`")
            elif repo_id == "mastermind":
                guardrails.extend(
                    ["`mastermind:AGENTS.md`", "`mastermind:config/authority_map.yml`"]
                )
        explicit_sources = list(dict.fromkeys(explicit_sources))
        registry_checks = list(dict.fromkeys(registry_checks))
        guardrails = list(dict.fromkeys(guardrails))
        registry_label = "Operational registry checks"
        if isinstance(program.get("ontology_status"), Mapping):
            registry_label = "Operational registry checks (includes declared contradiction)"
        lines.extend([f"### {_display_name(program_id, program)} (`{program_id}`)", ""])
        lines.extend(
            [
                f"- **Semantic posture:** `{boundary.get('authority_class')}`",
                f"- **Non-binding summary:** {_md_cell(boundary.get('summary'))}",
                "- **Explicit authority sources:** "
                + (", ".join(explicit_sources) or "none; this posture asserts no independent runtime authority"),
                f"- **{registry_label}:** "
                + (", ".join(registry_checks) or "none"),
                "- **Repository guardrails:** " + (", ".join(guardrails) or "none"),
                "",
            ]
        )

    lines.extend(
        [
            "## Product Map",
            "",
            "| Surface | Name | Purpose | Repository roles | Programs | Delivery |",
            "|---|---|---|---|---|---|",
        ]
    )
    reverse_products: dict[str, set[str]] = defaultdict(set)
    for program_id, program in programs.items():
        if isinstance(program, Mapping):
            for product_id in program.get("product_surfaces", []):
                reverse_products[str(product_id)].add(str(program_id))
    for product_id, product in _ordered_items(products):
        product_map = product if isinstance(product, Mapping) else {}
        repo_ids = sorted(
            _repo_binding_ids(product_map.get("repo_bindings"), repository_ids, _Errors(), "render")
        )
        repo_roles = _repository_binding_labels(
            product_map.get("repo_bindings"), repository_ids
        )
        declared_programs: set[str] = set(reverse_products.get(product_id, set()))
        for field in ("program", "owner_program"):
            if isinstance(product_map.get(field), str):
                declared_programs.add(product_map[field])
        for field in ("programs", "owner_programs"):
            if isinstance(product_map.get(field), list):
                declared_programs.update(str(item) for item in product_map[field])
        default_repo = repo_ids[0] if len(repo_ids) == 1 else model.primary_repository
        delivery_refs = _repo_ref_strings(
            product_map.get("implementation"), repository_ids, default_repo
        )
        delivery = ", ".join(delivery_refs) or "—"
        lines.append(
            f"| `{product_id}` | {_md_cell(_display_name(product_id, product))} | "
            f"{_md_cell(product_map.get('purpose'))} | {', '.join(repo_roles) or '—'} | "
            f"{', '.join(f'`{item}`' for item in sorted(declared_programs)) or '—'} | "
            f"{delivery} |"
        )
    if not products:
        lines.append("| — | — | — | — | — | — |")

    lines.extend(["", "## Cross-Repo Contracts", ""])
    if contracts:
        for contract_id, contract in _ordered_items(contracts):
            lines.extend([f"### {_display_name(contract_id, contract)} (`{contract_id}`)", ""])
            if isinstance(contract, Mapping):
                for key, value in sorted(contract.items(), key=lambda pair: str(pair[0])):
                    if key in {"name", "title", "order"}:
                        continue
                    lines.append(f"- **{key}:** {_md_cell(value)}")
                lines.append("")
    else:
        lines.extend(["No cross-repository contracts are declared.", ""])

    artifacts = model.synapse.get("artifacts", {})
    charters = model.lobe_charters.get("charters", {})
    synapse_counts = Counter(
        record.get("owner_program")
        for record in artifacts.values()
        if isinstance(record, Mapping)
    )
    lobe_counts = Counter(
        record.get("owner_program")
        for record in charters.values()
        if isinstance(record, Mapping)
    )
    lines.extend(
        [
            "## Raw Owner Coverage",
            "",
            "Every raw owner from the Synapse/lobe-charter union must have one explicit disposition. Zero-count rows are retained when the registry intentionally records sibling or historical identities.",
            "",
            "| Repository | Raw owner | Disposition | Semantic target | Synapse artifacts | Lobes |",
            "|---|---|---|---|---:|---:|",
        ]
    )
    for (repository, owner), record in sorted(model.dispositions.items()):
        target = _disposition_target(record)
        if _disposition_kind(record) == "unresolved_split":
            target = ", ".join(_split_candidates(record))
        lines.append(
            f"| `{repository}` | `{owner}` | `{_disposition_kind(record)}` | "
            f"{f'`{target}`' if target else '—'} | "
            f"{synapse_counts.get(owner, 0) if repository == model.primary_repository else 0} | "
            f"{lobe_counts.get(owner, 0) if repository == model.primary_repository else 0} |"
        )

    lines.extend(["", "## Sibling Repository Domain Coverage", ""])
    if coverage:
        for repository, record in _ordered_items(coverage):
            lines.extend([f"### {_display_name(repository, repositories.get(repository, {}))} (`{repository}`)", ""])
            _append_text_block(lines, record)
    else:
        lines.extend(["No repository domain coverage is declared.", ""])

    lines.extend(
        [
            "## Unresolved Items and Provenance",
            "",
            "### Known architecture and contract unresolveds",
            "",
        ]
    )
    known_unresolveds = registry.get("meta", {}).get("known_unresolveds", [])
    if known_unresolveds:
        lines.extend(f"- {_md_cell(item)}" for item in known_unresolveds)
    else:
        lines.append("- None.")
    lines.extend(["", "### Unresolved owner identities", ""])
    unresolved = [
        (repository, owner, record)
        for (repository, owner), record in sorted(model.dispositions.items())
        if _disposition_kind(record) in {"unresolved", "unresolved_split"}
    ]
    if unresolved:
        for repository, owner, record in unresolved:
            note = record.get(
                "reason", record.get("notes", record.get("note", "No reason recorded"))
            )
            lines.append(
                f"- `{repository}:{owner}` — `{_disposition_kind(record)}`: {_md_cell(note)}"
            )
    else:
        lines.append("- None.")
    lines.extend(["", "### Source SHA-256", "", "| Source | SHA-256 |", "|---|---|"])
    for source, digest in model.source_hashes:
        lines.append(f"| `{source}` | `{digest}` |")
    if model.compatibility_notes:
        lines.extend(
            [
                "",
                "### Legacy registry compatibility notes",
                "",
                "The curated semantic registry rejects duplicate keys. These pre-existing operational-registry duplicates are nonblocking here so this architecture build does not mutate an unrelated authority source:",
                "",
            ]
        )
        lines.extend(f"- {note}" for note in model.compatibility_notes)
    lines.extend(
        [
            "",
            "The renderer records no wall-clock timestamp. Identical source bytes produce byte-identical output.",
            "",
        ]
    )
    return "\n".join(lines)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
        ) as handle:
            temporary_name = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, 0o644)
        os.replace(temporary_name, path)
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--synapse", type=Path, default=DEFAULT_SYNAPSE)
    parser.add_argument("--lobe-charters", type=Path, default=DEFAULT_LOBE_CHARTERS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate and fail unless the existing output is byte-identical; never write",
    )
    parser.add_argument(
        "--cross-repo",
        action="store_true",
        help="validate configured sibling-repository roots without network access",
    )
    parser.add_argument(
        "--repo-root",
        action="append",
        default=[],
        metavar="REPOSITORY=PATH",
        help="validate one repository against an explicit local root; may be repeated",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        # Load the curated registry first.  If it does not exist, no output path is
        # inspected, created, or modified.
        registry_source = load_yaml(args.config)
        synapse_source = load_yaml(args.synapse, reject_duplicates=False)
        lobe_source = load_yaml(args.lobe_charters, reject_duplicates=False)
        explicit_roots = _parse_repo_root_args(args.repo_root)
        model = validate_and_build_model(
            registry_source,
            synapse_source,
            lobe_source,
            explicit_repo_roots=explicit_roots,
            cross_repo=args.cross_repo,
            allow_generated_output_missing=not args.check,
        )
        rendered = render_markdown(model)
        if args.check:
            try:
                existing = args.output.read_text(encoding="utf-8")
            except FileNotFoundError:
                print(f"ERROR: generated output is missing: {args.output}", file=sys.stderr)
                return 1
            if existing != rendered:
                print(
                    "ERROR: generated system map is stale; run "
                    "`python scripts/build_mastermind_system_map.py`",
                    file=sys.stderr,
                )
                return 1
            print(f"OK: {args.output} is current")
            return 0
        _atomic_write(args.output, rendered)
        print(f"Wrote {args.output}")
        return 0
    except ValidationError as exc:
        for error in exc.errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except SystemMapError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
