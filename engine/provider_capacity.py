"""Strict secret-free ``mastermind.provider_capacity.v1`` projection.

This module is a deterministic read-only boundary over the existing Shared AI
Provider Control owners.  It does not dispatch, probe a provider, persist a
snapshot, open an auth file, read credential values, or implement Executive
placement.  Source owners return only typed secret-free observations; this
module validates, canonicalizes and hashes them.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA = "mastermind.provider_capacity.v1"
PRODUCER_REPOSITORY = "mastermindx-market-intelligence/macro"
PRODUCER_PROGRAM = "shared-ai-provider-control"
IMPLEMENTATION_ID = "provider-capacity-v1"
IMPLEMENTATION_VERSION = 2
HOST_REF = "local-unbound"

HEALTH_FRESHNESS_SECONDS = 10 * 60
QUOTA_FRESHNESS_SECONDS = 10 * 60

# Static, reviewed, file-granular semantic source census.  Dynamic provider
# state is evidence, not implementation identity.  The CLI wrapper is excluded:
# it serializes the already-built contract and cannot alter a projected field.
MATERIAL_SOURCE_PATHS = (
    "config/capability_manifest.yml",
    "config/metabolism_budget.yml",
    "engine/codex_lane/runner.py",
    "engine/codex_provider.py",
    "engine/llm_auth.py",
    "engine/metabolism/budget_gate.py",
    "engine/neuralweb/key_pool.py",
    "engine/provider_capacity.py",
    "engine/provider_health.py",
    "lib/ai_costs.py",
)


@dataclass(frozen=True)
class SlotDefinition:
    capability_id: str
    provider: str
    billing_mode: str
    credential_kind: str
    execution_surface: str
    source_rung: str


SUPPORTED_SLOTS = (
    SlotDefinition("alibaba_subscription", "alibaba", "subscription", "unconfigured", "unconfigured", "unconfigured"),
    SlotDefinition("claude_code_oauth", "claude", "subscription", "oauth", "api", "oauth"),
    *(
        SlotDefinition(
            f"claude_code_oauth_{index}",
            "claude",
            "subscription",
            "oauth",
            "api",
            "oauth",
        )
        for index in range(1, 8)
    ),
    SlotDefinition("codex_account", "codex", "subscription", "attached_login", "native_cli", "codex"),
    SlotDefinition("codex_account_2", "codex", "subscription", "attached_login", "native_cli", "codex"),
    SlotDefinition("codex_account_3", "codex", "subscription", "attached_login", "native_cli", "codex"),
    SlotDefinition("cursor_subscription", "cursor", "subscription", "unconfigured", "unconfigured", "unconfigured"),
    SlotDefinition("deepseek_api_key", "deepseek", "metered_api", "api_key", "api", "deepseek"),
    SlotDefinition("glm_subscription", "glm", "subscription", "unconfigured", "unconfigured", "unconfigured"),
    SlotDefinition("grok_subscription", "grok", "subscription", "unconfigured", "unconfigured", "unconfigured"),
    SlotDefinition("openrouter_api_key", "openrouter", "metered_api", "unconfigured", "unconfigured", "unconfigured"),
)

UNCONFIGURED_SLOT_IDS = frozenset({
    "alibaba_subscription",
    "cursor_subscription",
    "glm_subscription",
    "grok_subscription",
    "openrouter_api_key",
})
NO_QUOTA_SLOT_IDS = frozenset({"deepseek_api_key", *UNCONFIGURED_SLOT_IDS})

DEGRADED_CODES = {
    "PRODUCER_SOURCE_UNGROUNDED",
    "PROVIDER_PRESENCE_UNKNOWN",
    "PROVIDER_ENABLEMENT_UNKNOWN",
    "PROVIDER_COOLING_UNKNOWN",
    "PROVIDER_BUDGET_UNKNOWN",
    "PROVIDER_CONFIGURATION_UNCONFIGURED",
    "PROVIDER_HEALTH_UNKNOWN",
    "PROVIDER_INVENTORY_UNKNOWN",
    "PROVIDER_OUTCOME_UNKNOWN",
    "SOURCE_CORRUPT",
    "SOURCE_UNREADABLE",
}
HEALTH_STATES = {"available", "degraded", "unavailable", "unknown"}
ERROR_CLASSES = {
    None,
    "auth",
    "usage_limit",
    "timeout",
    "not_installed",
    "unsupported",
    "transport",
    "error",
}
EVIDENCE = {"exact", "provider_reported", "estimated", "unknown"}
HEALTH_SOURCE_KINDS = {
    "local_observation",
    "provider_attempt",
    "provider_api",
    "local_ledger",
    "config",
    "error_signal",
    "unknown",
}
COOLING_KINDS = {None, "window", "weekly", "monthly", "concurrency", "auth", "provider", "unknown"}
QUOTA_HORIZONS = {"five_hour", "weekly", "monthly", "billing_cycle", "credits", "concurrency", "custom"}
QUOTA_METRICS = {"provider_allocation", "requests", "tokens", "credits", "currency", "concurrent_sessions", "custom"}
WINDOW_TYPES = {"rolling", "fixed", "billing_cycle", "instant", "unknown"}
QUOTA_SOURCE_KINDS = {"provider_api", "response_headers", "local_ledger", "config", "error_signal", "unknown"}
FRESHNESS = {"fresh", "stale", "unknown"}
OUTCOME_CLASSES = {
    "success", "auth", "usage_limit", "timeout", "not_installed",
    "unsupported", "transport", "error", "unknown",
}
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_HORIZON_ORDER = {
    "five_hour": 0,
    "weekly": 1,
    "monthly": 2,
    "billing_cycle": 3,
    "credits": 4,
    "concurrency": 5,
    "custom": 6,
}


class ProviderCapacityError(ValueError):
    """Safe bounded refusal from contract/source validation."""


@dataclass(frozen=True)
class MaterialSourceReceipt:
    material_source_digest: str
    repository_commit: str
    material_sources_match_commit: bool


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProviderCapacityError("NON_CANONICAL_JSON") from exc


def _parse_time(value: Any, *, nullable: bool = False) -> datetime | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value:
        raise ProviderCapacityError("INVALID_TIMESTAMP")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ProviderCapacityError("INVALID_TIMESTAMP") from exc
    if parsed.tzinfo is None:
        raise ProviderCapacityError("INVALID_TIMESTAMP")
    return parsed.astimezone(timezone.utc)


def _format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _closed(value: Mapping[str, Any], expected: set[str], code: str) -> None:
    if set(value) != expected:
        raise ProviderCapacityError(code)


def _finite_number(value: Any, *, nullable: bool = True) -> int | float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProviderCapacityError("INVALID_NUMBER")
    if not math.isfinite(float(value)) or float(value) < 0:
        raise ProviderCapacityError("INVALID_NUMBER")
    return value


def _degraded(code: str, scope: str, observed_at: str | None = None) -> dict[str, Any]:
    if code not in DEGRADED_CODES:
        raise ProviderCapacityError("UNKNOWN_DEGRADED_CODE")
    if observed_at is not None:
        _parse_time(observed_at)
    return {"code": code, "scope": scope, "observed_at": observed_at}


def _dedupe_degraded(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ProviderCapacityError("INVALID_DEGRADED_ROW")
        normalized = {
            "code": str(row.get("code") or ""),
            "scope": str(row.get("scope") or ""),
            "observed_at": row.get("observed_at"),
        }
        _closed(normalized, {"code", "scope", "observed_at"}, "INVALID_DEGRADED_ROW")
        if normalized["code"] not in DEGRADED_CODES or not normalized["scope"]:
            raise ProviderCapacityError("INVALID_DEGRADED_ROW")
        if normalized["observed_at"] is not None:
            _parse_time(normalized["observed_at"])
        key = (
            normalized["code"],
            normalized["scope"],
            str(normalized["observed_at"] or ""),
        )
        unique[key] = normalized
    return [unique[key] for key in sorted(unique)]


def _material_rows(
    repo_root: Path,
    paths: Sequence[str],
) -> tuple[list[dict[str, str]], dict[str, str]]:
    if not paths or len(paths) != len(set(paths)) or tuple(paths) != tuple(sorted(paths)):
        raise ProviderCapacityError("MATERIAL_SOURCE_ALLOWLIST_INVALID")
    root = repo_root.resolve(strict=True)
    rows: list[dict[str, str]] = []
    blob_oids: dict[str, str] = {}
    for raw_path in paths:
        relative = Path(raw_path)
        if relative.is_absolute() or ".." in relative.parts or str(relative) != raw_path:
            raise ProviderCapacityError("MATERIAL_SOURCE_PATH_ESCAPE")
        candidate = root / relative
        if candidate.is_symlink():
            raise ProviderCapacityError("MATERIAL_SOURCE_SYMLINK")
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ProviderCapacityError("MATERIAL_SOURCE_MISSING") from exc
        if root not in resolved.parents or not resolved.is_file():
            raise ProviderCapacityError("MATERIAL_SOURCE_NON_REGULAR")
        try:
            data = resolved.read_bytes()
        except OSError as exc:
            raise ProviderCapacityError("MATERIAL_SOURCE_UNREADABLE") from exc
        rows.append({"path": raw_path, "sha256": hashlib.sha256(data).hexdigest()})
        # This repository's 40-character commit contract is SHA-1.  Comparing
        # local blob identities with the commit tree proves the same raw bytes
        # without asking a blobless clone to fetch every committed blob.
        blob_header = f"blob {len(data)}\0".encode("ascii")
        blob_oids[raw_path] = hashlib.sha1(blob_header + data).hexdigest()
    return rows, blob_oids


def _git_bytes(repo_root: Path, *args: str) -> bytes:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProviderCapacityError("REPOSITORY_IDENTITY_UNAVAILABLE") from exc
    return proc.stdout


def _committed_material_oids(
    repo_root: Path,
    commit: str,
    paths: Sequence[str],
) -> dict[str, str]:
    """Read all material blob identities from one bounded tree query."""
    raw = _git_bytes(
        repo_root,
        "ls-tree",
        "-rz",
        "--full-tree",
        commit,
        "--",
        *paths,
    )
    result: dict[str, str] = {}
    try:
        for record in raw.split(b"\0"):
            if not record:
                continue
            metadata, separator, raw_path = record.partition(b"\t")
            mode, object_type, object_id = metadata.split(b" ")
            path = raw_path.decode("utf-8", "strict")
            if (
                not separator
                or object_type != b"blob"
                or mode == b"120000"
                or path not in paths
                or path in result
                or not re.fullmatch(rb"[0-9a-f]{40}", object_id)
            ):
                return {}
            result[path] = object_id.decode("ascii")
    except (UnicodeDecodeError, ValueError):
        return {}
    return result


def material_source_receipt(repo_root: Path | None = None) -> MaterialSourceReceipt:
    """Compute executed-byte identity and exact-HEAD grounding.

    The source allowlist, reported commit and match bit are not caller supplied.
    """
    root = (repo_root or _repo_root()).resolve(strict=True)
    rows, local_blob_oids = _material_rows(root, MATERIAL_SOURCE_PATHS)
    digest = hashlib.sha256(_canonical_bytes(rows)).hexdigest()
    commit = _git_bytes(root, "rev-parse", "HEAD").decode("ascii", "strict").strip()
    if not _SHA_RE.fullmatch(commit):
        raise ProviderCapacityError("REPOSITORY_IDENTITY_UNAVAILABLE")

    committed_blob_oids = _committed_material_oids(root, commit, MATERIAL_SOURCE_PATHS)
    matches = (
        set(committed_blob_oids) == set(MATERIAL_SOURCE_PATHS)
        and committed_blob_oids == local_blob_oids
    )
    return MaterialSourceReceipt(digest, commit, matches)


def _unknown_health() -> dict[str, Any]:
    return {
        "state": "unknown",
        "error_class": None,
        "observed_at": None,
        "stale_after": None,
        "evidence": "unknown",
        "source_kind": "unknown",
        "freshness": "unknown",
    }


def _unknown_cooling() -> dict[str, Any]:
    return {
        "active": None,
        "kind": None,
        "reset_at": None,
        "evidence": "unknown",
        "observed_at": None,
    }


def _unknown_quota(horizon: str, duration_seconds: int) -> dict[str, Any]:
    return {
        "horizon": horizon,
        "metric": "provider_allocation",
        "window_type": "rolling",
        "duration_seconds": duration_seconds,
        "limit": None,
        "used": None,
        "remaining": None,
        "used_percent": None,
        "reset_at": None,
        "observed_at": None,
        "stale_after": None,
        "evidence": "unknown",
        "source_kind": "unknown",
        "freshness": "unknown",
    }


def _unconfigured_observation(definition: SlotDefinition) -> dict[str, Any]:
    if definition.capability_id not in UNCONFIGURED_SLOT_IDS:
        raise ProviderCapacityError("SLOT_IS_CONFIGURED")
    return {
        "capability_id": definition.capability_id,
        "present": False,
        "enabled": False,
        "health": _unknown_health(),
        "cooling": _unknown_cooling(),
        "quota_horizons": [],
        "last_outcome": {"class": "unknown", "observed_at": None},
        "degraded_codes": [
            "PROVIDER_BUDGET_UNKNOWN",
            "PROVIDER_CONFIGURATION_UNCONFIGURED",
            "PROVIDER_COOLING_UNKNOWN",
            "PROVIDER_HEALTH_UNKNOWN",
            "PROVIDER_OUTCOME_UNKNOWN",
        ],
    }


def _freshness(observed_at: str, stale_after: str, generated_at: datetime) -> str:
    observed = _parse_time(observed_at)
    stale = _parse_time(stale_after)
    if observed is None or stale is None or stale < observed:
        raise ProviderCapacityError("INVALID_FRESHNESS_WINDOW")
    return "stale" if generated_at >= stale else "fresh"


def _health_from_sources(
    definition: SlotDefinition,
    health_source: Mapping[str, Any],
    generated_at: datetime,
    executable_present: bool | None = None,
) -> tuple[dict[str, Any], list[str]]:
    if definition.provider == "codex" and executable_present is False:
        observed = _format_time(generated_at)
        stale = _format_time(generated_at + timedelta(seconds=HEALTH_FRESHNESS_SECONDS))
        return ({
            "state": "unavailable",
            "error_class": "not_installed",
            "observed_at": observed,
            "stale_after": stale,
            "evidence": "exact",
            "source_kind": "local_observation",
            "freshness": "fresh",
        }, [])
    if health_source.get("quality") != "ok":
        return _unknown_health(), ["PROVIDER_HEALTH_UNKNOWN"] + [
            code for code in health_source.get("codes", []) if code in DEGRADED_CODES
        ]

    candidates: list[tuple[datetime, Mapping[str, Any]]] = []
    for row in health_source.get("rows", []):
        if not isinstance(row, Mapping):
            continue
        cap_id = row.get("cap_id")
        rung = str(row.get("rung") or "")
        matches = cap_id == definition.capability_id
        if not cap_id and definition.capability_id in {"claude_code_oauth", "deepseek_api_key"}:
            matches = rung == definition.source_rung
        if not matches:
            continue
        try:
            candidates.append((_parse_time(row.get("ts")), row))  # type: ignore[arg-type]
        except ProviderCapacityError:
            return _unknown_health(), ["SOURCE_CORRUPT", "PROVIDER_HEALTH_UNKNOWN"]
    if not candidates:
        return _unknown_health(), ["PROVIDER_HEALTH_UNKNOWN"]

    observed_dt, latest = max(candidates, key=lambda item: item[0])
    if observed_dt is None:
        return _unknown_health(), ["SOURCE_CORRUPT", "PROVIDER_HEALTH_UNKNOWN"]
    observed = _format_time(observed_dt)
    stale = _format_time(observed_dt + timedelta(seconds=HEALTH_FRESHNESS_SECONDS))
    if bool(latest.get("ok")):
        state = "available"
        error_class = None
    else:
        raw_error = str(latest.get("error_class") or "error")
        error_class = raw_error if raw_error in ERROR_CLASSES else "error"
        state = "unavailable" if error_class in {"auth", "usage_limit", "not_installed", "unsupported"} else "degraded"
    return ({
        "state": state,
        "error_class": error_class,
        "observed_at": observed,
        "stale_after": stale,
        "evidence": "provider_reported",
        "source_kind": "provider_attempt",
        "freshness": _freshness(observed, stale, generated_at),
    }, [])


def _reported_quota(
    base: dict[str, Any],
    used_percent: Any,
    reset_at: Any,
    observed_at: Any,
    generated_at: datetime,
    *,
    source_kind: str = "response_headers",
) -> dict[str, Any] | None:
    try:
        percent = _finite_number(float(str(used_percent).strip().rstrip("%")), nullable=False)
        if percent is None or float(percent) > 100:
            raise ProviderCapacityError("INVALID_PERCENTAGE")
        observed_dt = _parse_time(observed_at)
        if observed_dt is None:
            raise ProviderCapacityError("INVALID_TIMESTAMP")
        observed = _format_time(observed_dt)
        stale = _format_time(observed_dt + timedelta(seconds=QUOTA_FRESHNESS_SECONDS))
        row = dict(base)
        row.update({
            "used_percent": float(percent),
            "reset_at": _format_time(_parse_time(reset_at)) if reset_at else None,  # type: ignore[arg-type]
            "observed_at": observed,
            "stale_after": stale,
            "evidence": "provider_reported",
            "source_kind": source_kind,
            "freshness": _freshness(observed, stale, generated_at),
        })
        return row
    except (ProviderCapacityError, TypeError, ValueError):
        return None


def _estimated_quota(
    base: dict[str, Any],
    used: Any,
    limit: Any,
    observed_at: str | None,
    generated_at: datetime,
) -> dict[str, Any] | None:
    if used is None or limit is None or observed_at is None:
        return None
    try:
        used_value = float(_finite_number(used, nullable=False))
        limit_value = float(_finite_number(limit, nullable=False))
        if limit_value <= 0 or used_value > limit_value:
            raise ProviderCapacityError("INVALID_ESTIMATE")
        observed_dt = _parse_time(observed_at)
        if observed_dt is None:
            raise ProviderCapacityError("INVALID_TIMESTAMP")
        observed = _format_time(observed_dt)
        stale = _format_time(observed_dt + timedelta(seconds=QUOTA_FRESHNESS_SECONDS))
        row = dict(base)
        row.update({
            "limit": limit_value,
            "used": used_value,
            "remaining": limit_value - used_value,
            "used_percent": 100.0 * used_value / limit_value,
            "observed_at": observed,
            "stale_after": stale,
            "evidence": "estimated",
            "source_kind": "local_ledger",
            "freshness": _freshness(observed, stale, generated_at),
        })
        return row
    except (ProviderCapacityError, TypeError, ValueError):
        return None


def _quota_from_sources(
    definition: SlotDefinition,
    source: Mapping[str, Any],
    budget_config: Mapping[str, Any],
    generated_at: datetime,
) -> tuple[list[dict[str, Any]], list[str]]:
    if definition.capability_id in NO_QUOTA_SLOT_IDS:
        return [], ["PROVIDER_BUDGET_UNKNOWN"]

    five = _unknown_quota("five_hour", 5 * 3600)
    weekly = _unknown_quota("weekly", 7 * 24 * 3600)
    rows = [five, weekly]
    codes: list[str] = []
    budget = source.get("budget") if isinstance(source.get("budget"), Mapping) else {}
    headers = budget.get("headers") if isinstance(budget.get("headers"), Mapping) else {}
    headers_ts = budget.get("headers_ts")

    if headers:
        if definition.provider == "codex":
            recognized = False
            mapping = (
                (five, "primary"),
                (weekly, "secondary"),
            )
            for base, label in mapping:
                percent = headers.get(f"codex-ratelimit-{label}-used-percent")
                reset = headers.get(f"codex-ratelimit-{label}-resets-at")
                if percent is not None:
                    recognized = True
                    parsed = _reported_quota(base, percent, reset, headers_ts, generated_at)
                    if parsed is None:
                        codes.extend(["SOURCE_CORRUPT", "PROVIDER_BUDGET_UNKNOWN"])
                    else:
                        rows[0 if label == "primary" else 1] = parsed
            if not recognized:
                codes.extend(["SOURCE_CORRUPT", "PROVIDER_BUDGET_UNKNOWN"])
        else:
            from engine.metabolism.budget_gate import _parse_headers  # noqa: PLC0415

            parsed_headers = _parse_headers(dict(headers))
            if not any(value is not None for value in parsed_headers.values()):
                codes.extend(["SOURCE_CORRUPT", "PROVIDER_BUDGET_UNKNOWN"])
            for index, (base, percent_key, reset_key) in enumerate((
                (five, "pct_5h", "reset_5h"),
                (weekly, "pct_weekly", "reset_weekly"),
            )):
                if parsed_headers.get(percent_key) is not None:
                    parsed = _reported_quota(
                        base,
                        parsed_headers[percent_key],
                        parsed_headers.get(reset_key),
                        headers_ts,
                        generated_at,
                    )
                    if parsed is None:
                        codes.extend(["SOURCE_CORRUPT", "PROVIDER_BUDGET_UNKNOWN"])
                    else:
                        rows[index] = parsed

    # A specific active 429 may establish only the evidenced horizon.
    cooling = source.get("cooling") if isinstance(source.get("cooling"), Mapping) else {}
    if cooling.get("active") is True and cooling.get("kind") in {"window", "weekly"}:
        index = 0 if cooling.get("kind") == "window" else 1
        if rows[index]["evidence"] == "unknown" and cooling.get("observed_at"):
            observed = cooling["observed_at"]
            try:
                observed_dt = _parse_time(observed)
                stale = _format_time((observed_dt or generated_at) + timedelta(seconds=QUOTA_FRESHNESS_SECONDS))
                rows[index].update({
                    "used_percent": 100.0,
                    "reset_at": cooling.get("reset_at"),
                    "observed_at": observed,
                    "stale_after": stale,
                    "evidence": "provider_reported",
                    "source_kind": "error_signal",
                    "freshness": _freshness(observed, stale, generated_at),
                })
            except ProviderCapacityError:
                codes.extend(["SOURCE_CORRUPT", "PROVIDER_BUDGET_UNKNOWN"])

    # Configured estimates fill only horizons still without reported evidence.
    if budget_config.get("quality") == "ok":
        last = source.get("last_outcome") if isinstance(source.get("last_outcome"), Mapping) else {}
        observation_time = last.get("observed_at")
        estimates = (
            (0, budget.get("est_5h_tokens"), budget_config.get("est_budget_5h_tokens")),
            (1, budget.get("est_weekly_tokens"), budget_config.get("est_budget_weekly_tokens")),
        )
        for index, used, limit in estimates:
            if rows[index]["evidence"] != "unknown":
                continue
            estimated = _estimated_quota(rows[index], used, limit, observation_time, generated_at)
            if estimated is not None:
                rows[index] = estimated

    if any(row["evidence"] == "unknown" for row in rows):
        codes.append("PROVIDER_BUDGET_UNKNOWN")
    return rows, sorted(set(codes))


def _outcome_from_source(source: Mapping[str, Any]) -> dict[str, Any]:
    raw = source.get("last_outcome") if isinstance(source.get("last_outcome"), Mapping) else {}
    mapping = {
        "ok": "success",
        "success": "success",
        "auth_failed": "auth",
        "rate_limited": "usage_limit",
        "usage_limit": "usage_limit",
        "timeout": "timeout",
        "not_installed": "not_installed",
        "unsupported": "unsupported",
        "transport": "transport",
        "error": "error",
        "launched": "unknown",
        "unknown": "unknown",
    }
    outcome = mapping.get(str(raw.get("class") or "unknown"), "unknown")
    observed_at = raw.get("observed_at")
    if observed_at is not None:
        try:
            observed_at = _format_time(_parse_time(observed_at))  # type: ignore[arg-type]
        except ProviderCapacityError:
            outcome = "unknown"
            observed_at = None
    if outcome == "unknown" and observed_at is None:
        return {"class": "unknown", "observed_at": None}
    return {"class": outcome, "observed_at": observed_at}


def collect_current_observations(
    *,
    repo_root: Path | None = None,
    generated_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """Collect current secret-free observations through source-owned seams."""
    root = (repo_root or _repo_root()).resolve(strict=True)
    now = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)

    from engine import codex_provider, provider_health
    from engine.metabolism import budget_gate
    from engine.neuralweb import key_pool

    key_source = key_pool.capacity_key_observations(root, observed_at=now)
    codex_source = codex_provider.capacity_account_observations()
    health_source = provider_health.capacity_health_observations()
    budget_config = budget_gate.capacity_budget_config(root)

    key_by_id = {
        str(row.get("capability_id")): row
        for row in key_source.get("slots", [])
        if isinstance(row, Mapping)
    }
    codex_by_id = {
        str(row.get("capability_id")): row
        for row in codex_source.get("slots", [])
        if isinstance(row, Mapping)
    }
    observations: list[dict[str, Any]] = []
    for definition in SUPPORTED_SLOTS:
        if definition.capability_id in UNCONFIGURED_SLOT_IDS:
            observations.append(_unconfigured_observation(definition))
            continue
        if definition.provider == "codex":
            source = dict(codex_by_id.get(definition.capability_id, {}))
            source["enabled"] = codex_source.get("enabled")
            source["budget"] = {
                "headers": {},
                "headers_ts": None,
                "est_5h_tokens": None,
                "est_weekly_tokens": None,
            }
            source["cooling"] = _unknown_cooling()
            source["last_outcome"] = {"class": "unknown", "observed_at": None}
            source["codes"] = (
                list(codex_source.get("codes", []))
                + list(source.get("codes", []))
                + list(key_source.get("codes", []))
            )
            # Reuse per-account header/cooling/outcome evidence from key-pool
            # ledgers without reusing its combined presence/enablement fields.
            ledger_source = key_by_id.get(definition.capability_id)
            if ledger_source:
                source["budget"] = ledger_source.get("budget", source["budget"])
                source["cooling"] = ledger_source.get("cooling", source["cooling"])
                source["last_outcome"] = ledger_source.get("last_outcome", source["last_outcome"])
                source["codes"].extend(
                    code for code in ledger_source.get("codes", [])
                    if code not in {
                        "PROVIDER_PRESENCE_UNKNOWN",
                        "PROVIDER_ENABLEMENT_UNKNOWN",
                    }
                )
            executable = codex_source.get("executable_present")
        else:
            source = dict(key_by_id.get(definition.capability_id, {}))
            source["codes"] = (
                list(source.get("codes", []))
                + list(key_source.get("codes", []))
            )
            executable = None

        health, health_codes = _health_from_sources(
            definition,
            health_source,
            now,
            executable_present=executable,
        )
        quota_horizons, quota_codes = _quota_from_sources(
            definition,
            source,
            budget_config,
            now,
        )
        codes = [
            code for code in (
                list(source.get("codes", []))
                + health_codes
                + quota_codes
            ) if code in DEGRADED_CODES
        ]
        if source.get("present") is None:
            codes.append("PROVIDER_PRESENCE_UNKNOWN")
        if source.get("enabled") is None:
            codes.append("PROVIDER_ENABLEMENT_UNKNOWN")
        cooling_source = source.get("cooling") if isinstance(source.get("cooling"), Mapping) else {}
        if cooling_source.get("active") is None:
            cooling = _unknown_cooling()
            codes.append("PROVIDER_COOLING_UNKNOWN")
        else:
            cooling = {
                "active": cooling_source.get("active"),
                "kind": cooling_source.get("kind"),
                "reset_at": cooling_source.get("reset_at"),
                "evidence": cooling_source.get("evidence"),
                "observed_at": cooling_source.get("observed_at"),
            }
        outcome = _outcome_from_source(source)
        if outcome["class"] == "unknown":
            codes.append("PROVIDER_OUTCOME_UNKNOWN")
        observations.append({
            "capability_id": definition.capability_id,
            "present": source.get("present"),
            "enabled": source.get("enabled"),
            "health": health,
            "cooling": cooling,
            "quota_horizons": quota_horizons,
            "last_outcome": outcome,
            "degraded_codes": sorted(set(codes)),
        })
    return observations


def _normalize_health(value: Mapping[str, Any], generated_at: datetime) -> dict[str, Any]:
    expected = {"state", "error_class", "observed_at", "stale_after", "evidence", "source_kind", "freshness"}
    _closed(value, expected, "HEALTH_SCHEMA_INVALID")
    out = dict(value)
    if out["state"] not in HEALTH_STATES or out["error_class"] not in ERROR_CLASSES:
        raise ProviderCapacityError("HEALTH_SCHEMA_INVALID")
    if (
        out["evidence"] not in EVIDENCE
        or out["source_kind"] not in HEALTH_SOURCE_KINDS
        or out["freshness"] not in FRESHNESS
    ):
        raise ProviderCapacityError("HEALTH_SCHEMA_INVALID")
    if out["state"] == "unknown" and out["observed_at"] is None:
        if out != _unknown_health():
            raise ProviderCapacityError("HEALTH_UNKNOWN_INVALID")
        return out
    if out["observed_at"] is None:
        raise ProviderCapacityError("HEALTH_TIMESTAMP_MISSING")
    _parse_time(out["observed_at"])
    if out["stale_after"] is None:
        if out["freshness"] != "unknown":
            raise ProviderCapacityError("HEALTH_FRESHNESS_INVALID")
    else:
        expected_freshness = _freshness(out["observed_at"], out["stale_after"], generated_at)
        if out["freshness"] != expected_freshness:
            raise ProviderCapacityError("HEALTH_FRESHNESS_INVALID")
    if out["state"] == "available" and out["error_class"] is not None:
        raise ProviderCapacityError("HEALTH_ERROR_CLASS_INVALID")
    return out


def _normalize_cooling(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {"active", "kind", "reset_at", "evidence", "observed_at"}
    _closed(value, expected, "COOLING_SCHEMA_INVALID")
    out = dict(value)
    if out["active"] not in {True, False, None} or out["kind"] not in COOLING_KINDS or out["evidence"] not in EVIDENCE:
        raise ProviderCapacityError("COOLING_SCHEMA_INVALID")
    if out["active"] is None:
        if out != _unknown_cooling():
            raise ProviderCapacityError("COOLING_UNKNOWN_INVALID")
        return out
    if out["active"] is False and (out["kind"] is not None or out["reset_at"] is not None):
        raise ProviderCapacityError("COOLING_FALSE_INVALID")
    if out["active"] is False and out["evidence"] == "unknown":
        raise ProviderCapacityError("COOLING_FALSE_INVALID")
    if out["active"] is True and (out["kind"] is None or out["reset_at"] is None or out["observed_at"] is None):
        raise ProviderCapacityError("COOLING_ACTIVE_INVALID")
    if out["reset_at"] is not None:
        _parse_time(out["reset_at"])
    if out["observed_at"] is not None:
        _parse_time(out["observed_at"])
    return out


def _normalize_quota(value: Mapping[str, Any], generated_at: datetime) -> dict[str, Any]:
    expected = {
        "horizon", "metric", "window_type", "duration_seconds", "limit", "used",
        "remaining", "used_percent", "reset_at", "observed_at", "stale_after",
        "evidence", "source_kind", "freshness",
    }
    _closed(value, expected, "QUOTA_SCHEMA_INVALID")
    out = dict(value)
    if (
        out["horizon"] not in QUOTA_HORIZONS
        or out["metric"] not in QUOTA_METRICS
        or out["window_type"] not in WINDOW_TYPES
    ):
        raise ProviderCapacityError("QUOTA_SCHEMA_INVALID")
    for key in ("duration_seconds", "limit", "used", "remaining", "used_percent"):
        out[key] = _finite_number(out[key])
    if out["used_percent"] is not None and float(out["used_percent"]) > 100:
        raise ProviderCapacityError("INVALID_PERCENTAGE")
    if out["remaining"] is not None and out["limit"] is None:
        raise ProviderCapacityError("ABSOLUTE_REMAINING_WITHOUT_LIMIT")
    if out["limit"] is not None and out["used"] is not None and float(out["used"]) > float(out["limit"]):
        raise ProviderCapacityError("IMPOSSIBLE_QUOTA_RELATION")
    if out["limit"] is not None and out["used"] is not None and out["remaining"] is not None:
        if not math.isclose(
            float(out["limit"]),
            float(out["used"]) + float(out["remaining"]),
            rel_tol=0,
            abs_tol=1e-8,
        ):
            raise ProviderCapacityError("IMPOSSIBLE_QUOTA_RELATION")
    if (
        out["evidence"] not in EVIDENCE
        or out["source_kind"] not in QUOTA_SOURCE_KINDS
        or out["freshness"] not in FRESHNESS
    ):
        raise ProviderCapacityError("QUOTA_SCHEMA_INVALID")
    if out["evidence"] == "unknown":
        dynamic = ("limit", "used", "remaining", "used_percent", "reset_at", "observed_at", "stale_after")
        if (
            any(out[key] is not None for key in dynamic)
            or out["source_kind"] != "unknown"
            or out["freshness"] != "unknown"
        ):
            raise ProviderCapacityError("QUOTA_UNKNOWN_INVALID")
    else:
        if out["observed_at"] is None:
            raise ProviderCapacityError("QUOTA_TIMESTAMP_MISSING")
        _parse_time(out["observed_at"])
        if out["stale_after"] is not None:
            expected_freshness = _freshness(out["observed_at"], out["stale_after"], generated_at)
            if out["freshness"] != expected_freshness:
                raise ProviderCapacityError("QUOTA_FRESHNESS_INVALID")
        elif out["freshness"] != "unknown":
            raise ProviderCapacityError("QUOTA_FRESHNESS_INVALID")
    if out["reset_at"] is not None:
        _parse_time(out["reset_at"])
    return out


def _normalize_outcome(value: Mapping[str, Any]) -> dict[str, Any]:
    _closed(value, {"class", "observed_at"}, "OUTCOME_SCHEMA_INVALID")
    out = dict(value)
    if out["class"] not in OUTCOME_CLASSES:
        raise ProviderCapacityError("OUTCOME_SCHEMA_INVALID")
    if out["observed_at"] is not None:
        _parse_time(out["observed_at"])
    if out["class"] == "unknown" and out["observed_at"] is None:
        return out
    if out["observed_at"] is None:
        raise ProviderCapacityError("OUTCOME_TIMESTAMP_MISSING")
    return out


def _normalize_slot(
    definition: SlotDefinition,
    observation: Mapping[str, Any],
    generated_at: datetime,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    expected = {
        "capability_id", "present", "enabled", "health", "cooling",
        "quota_horizons", "last_outcome", "degraded_codes",
    }
    _closed(observation, expected, "OBSERVATION_SCHEMA_INVALID")
    if observation["capability_id"] != definition.capability_id:
        raise ProviderCapacityError("OBSERVATION_IDENTITY_INVALID")
    if observation["present"] not in {True, False, None} or observation["enabled"] not in {True, False, None}:
        raise ProviderCapacityError("NULLABLE_BOOLEAN_INVALID")
    if not isinstance(observation["health"], Mapping) or not isinstance(observation["cooling"], Mapping):
        raise ProviderCapacityError("OBSERVATION_SCHEMA_INVALID")
    if (
        not isinstance(observation["quota_horizons"], Sequence)
        or isinstance(observation["quota_horizons"], (str, bytes))
    ):
        raise ProviderCapacityError("OBSERVATION_SCHEMA_INVALID")
    if not isinstance(observation["last_outcome"], Mapping):
        raise ProviderCapacityError("OBSERVATION_SCHEMA_INVALID")

    quotas = [
        _normalize_quota(row, generated_at)
        for row in observation["quota_horizons"]
        if isinstance(row, Mapping)
    ]
    if len(quotas) != len(observation["quota_horizons"]):
        raise ProviderCapacityError("QUOTA_SCHEMA_INVALID")
    quotas.sort(key=lambda row: (_HORIZON_ORDER[row["horizon"]], row["metric"]))
    quota_ids = [(row["horizon"], row["metric"]) for row in quotas]
    if len(quota_ids) != len(set(quota_ids)):
        raise ProviderCapacityError("DUPLICATE_QUOTA_HORIZON")

    degraded_rows = [
        _degraded(str(code), definition.capability_id)
        for code in observation["degraded_codes"]
    ]
    slot = {
        "capability_id": definition.capability_id,
        "provider": definition.provider,
        "account_label": definition.capability_id,
        "host_ref": HOST_REF,
        "billing_mode": definition.billing_mode,
        "credential_kind": definition.credential_kind,
        "execution_surface": definition.execution_surface,
        "present": observation["present"],
        "enabled": observation["enabled"],
        "health": _normalize_health(observation["health"], generated_at),
        "cooling": _normalize_cooling(observation["cooling"]),
        "quota_horizons": quotas,
        "last_outcome": _normalize_outcome(observation["last_outcome"]),
    }
    return slot, degraded_rows


def _semantic_snapshot_hash(document: Mapping[str, Any]) -> str:
    semantic = copy.deepcopy(dict(document))
    for key in ("generated_at", "snapshot_hash", "audit"):
        semantic.pop(key, None)
    return hashlib.sha256(_canonical_bytes(semantic)).hexdigest()


def snapshot_hash(document: Mapping[str, Any]) -> str:
    """Return semantic identity only after strict contract validation."""
    validate_snapshot(document, check_hash=False)
    return _semantic_snapshot_hash(document)


def _build_snapshot_from_observations(
    *,
    repo_root: Path,
    generated_at: datetime,
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Assemble a snapshot from source observations (private test seam)."""
    root = repo_root.resolve(strict=True)
    now = generated_at.astimezone(timezone.utc).replace(microsecond=0)
    receipt = material_source_receipt(root)
    source_observations = list(observations)

    by_id: dict[str, Mapping[str, Any]] = {}
    for observation in source_observations:
        capability_id = str(observation.get("capability_id") or "")
        if capability_id in by_id:
            raise ProviderCapacityError("DUPLICATE_SLOT_IDENTITY")
        by_id[capability_id] = observation

    supported_ids = {definition.capability_id for definition in SUPPORTED_SLOTS}
    degraded_rows: list[dict[str, Any]] = []
    if set(by_id) - supported_ids:
        degraded_rows.append(_degraded("PROVIDER_INVENTORY_UNKNOWN", "producer"))

    slots: list[dict[str, Any]] = []
    for definition in SUPPORTED_SLOTS:
        observation = by_id.get(definition.capability_id)
        if observation is None:
            if definition.capability_id in UNCONFIGURED_SLOT_IDS:
                observation = _unconfigured_observation(definition)
            else:
                observation = {
                    "capability_id": definition.capability_id,
                    "present": None,
                    "enabled": None,
                    "health": _unknown_health(),
                    "cooling": _unknown_cooling(),
                    "quota_horizons": [] if definition.capability_id in NO_QUOTA_SLOT_IDS else [
                        _unknown_quota("five_hour", 5 * 3600),
                        _unknown_quota("weekly", 7 * 24 * 3600),
                    ],
                    "last_outcome": {"class": "unknown", "observed_at": None},
                    "degraded_codes": [
                        "PROVIDER_INVENTORY_UNKNOWN",
                        "PROVIDER_PRESENCE_UNKNOWN",
                        "PROVIDER_ENABLEMENT_UNKNOWN",
                        "PROVIDER_COOLING_UNKNOWN",
                        "PROVIDER_HEALTH_UNKNOWN",
                        "PROVIDER_BUDGET_UNKNOWN",
                        "PROVIDER_OUTCOME_UNKNOWN",
                    ],
                }
        slot, slot_degraded = _normalize_slot(definition, observation, now)
        slots.append(slot)
        degraded_rows.extend(slot_degraded)

    slots.sort(key=lambda row: (row["host_ref"], row["provider"], row["capability_id"]))
    slot_ids = [(row["host_ref"], row["capability_id"]) for row in slots]
    if len(slot_ids) != len(set(slot_ids)):
        raise ProviderCapacityError("DUPLICATE_SLOT_IDENTITY")

    if not receipt.material_sources_match_commit:
        degraded_rows.append(_degraded("PRODUCER_SOURCE_UNGROUNDED", "producer"))

    document: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at": _format_time(now),
        "producer": {
            "repository": PRODUCER_REPOSITORY,
            "program": PRODUCER_PROGRAM,
            "implementation_id": IMPLEMENTATION_ID,
            "implementation_version": IMPLEMENTATION_VERSION,
            "material_source_digest": receipt.material_source_digest,
        },
        "audit": {
            "repository_commit": receipt.repository_commit,
            "material_sources_match_commit": receipt.material_sources_match_commit,
        },
        "snapshot_hash": "0" * 64,
        "slots": slots,
        "degraded": _dedupe_degraded(degraded_rows),
    }
    validate_snapshot(document, check_hash=False)
    document["snapshot_hash"] = _semantic_snapshot_hash(document)
    validate_snapshot(document)
    return document


def build_snapshot(*, repo_root: Path | None = None) -> dict[str, Any]:
    """Build one source-owned strict snapshot without writes or provider calls.

    Current observations, generation time, source census, commit and grounding
    are all producer-owned.  Callers may select only the repository root.
    """
    root = (repo_root or _repo_root()).resolve(strict=True)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    observations = collect_current_observations(repo_root=root, generated_at=now)
    return _build_snapshot_from_observations(
        repo_root=root,
        generated_at=now,
        observations=observations,
    )


def validate_snapshot(document: Mapping[str, Any], *, check_hash: bool = True) -> None:
    """Fail closed unless ``document`` is the complete strict v1 contract."""
    _closed(
        document,
        {"schema", "generated_at", "producer", "audit", "snapshot_hash", "slots", "degraded"},
        "TOP_LEVEL_SCHEMA_INVALID",
    )
    if document["schema"] != SCHEMA:
        raise ProviderCapacityError("SCHEMA_INVALID")
    generated_at = _parse_time(document["generated_at"])
    if generated_at is None:
        raise ProviderCapacityError("INVALID_TIMESTAMP")

    producer = document["producer"]
    audit = document["audit"]
    if not isinstance(producer, Mapping) or not isinstance(audit, Mapping):
        raise ProviderCapacityError("PRODUCER_SCHEMA_INVALID")
    _closed(
        producer,
        {"repository", "program", "implementation_id", "implementation_version", "material_source_digest"},
        "PRODUCER_SCHEMA_INVALID",
    )
    if (
        producer["repository"] != PRODUCER_REPOSITORY
        or producer["program"] != PRODUCER_PROGRAM
        or producer["implementation_id"] != IMPLEMENTATION_ID
    ):
        raise ProviderCapacityError("PRODUCER_IDENTITY_INVALID")
    if (
        isinstance(producer["implementation_version"], bool)
        or not isinstance(producer["implementation_version"], int)
        or producer["implementation_version"] < 1
    ):
        raise ProviderCapacityError("PRODUCER_VERSION_INVALID")
    if (
        not isinstance(producer["material_source_digest"], str)
        or not _DIGEST_RE.fullmatch(producer["material_source_digest"])
    ):
        raise ProviderCapacityError("MATERIAL_SOURCE_DIGEST_INVALID")

    _closed(audit, {"repository_commit", "material_sources_match_commit"}, "AUDIT_SCHEMA_INVALID")
    if not isinstance(audit["repository_commit"], str) or not _SHA_RE.fullmatch(audit["repository_commit"]):
        raise ProviderCapacityError("AUDIT_COMMIT_INVALID")
    if not isinstance(audit["material_sources_match_commit"], bool):
        raise ProviderCapacityError("AUDIT_GROUNDING_INVALID")

    if not isinstance(document["snapshot_hash"], str) or not _DIGEST_RE.fullmatch(document["snapshot_hash"]):
        raise ProviderCapacityError("SNAPSHOT_HASH_INVALID")
    if not isinstance(document["slots"], list) or not isinstance(document["degraded"], list):
        raise ProviderCapacityError("COLLECTION_SCHEMA_INVALID")
    if document["degraded"] != _dedupe_degraded(document["degraded"]):
        raise ProviderCapacityError("DEGRADED_ORDER_INVALID")
    degraded_scopes = {
        (str(row["code"]), str(row["scope"]))
        for row in document["degraded"]
    }

    definitions = {definition.capability_id: definition for definition in SUPPORTED_SLOTS}
    seen: set[tuple[str, str]] = set()
    normalized_slots: list[dict[str, Any]] = []
    for slot in document["slots"]:
        if not isinstance(slot, Mapping):
            raise ProviderCapacityError("SLOT_SCHEMA_INVALID")
        expected = {
            "capability_id", "provider", "account_label", "host_ref", "billing_mode",
            "credential_kind", "execution_surface", "present", "enabled", "health",
            "cooling", "quota_horizons", "last_outcome",
        }
        _closed(slot, expected, "SLOT_SCHEMA_INVALID")
        definition = definitions.get(str(slot["capability_id"]))
        if definition is None:
            raise ProviderCapacityError("UNDECLARED_SLOT")
        static_values = (
            slot["provider"], slot["account_label"], slot["host_ref"], slot["billing_mode"],
            slot["credential_kind"], slot["execution_surface"],
        )
        expected_values = (
            definition.provider, definition.capability_id, HOST_REF, definition.billing_mode,
            definition.credential_kind, definition.execution_surface,
        )
        if (
            static_values != expected_values
            or slot["present"] not in {True, False, None}
            or slot["enabled"] not in {True, False, None}
        ):
            raise ProviderCapacityError("SLOT_IDENTITY_INVALID")
        identity = (str(slot["host_ref"]), str(slot["capability_id"]))
        if identity in seen:
            raise ProviderCapacityError("DUPLICATE_SLOT_IDENTITY")
        seen.add(identity)
        if (
            not isinstance(slot["health"], Mapping)
            or not isinstance(slot["cooling"], Mapping)
            or not isinstance(slot["last_outcome"], Mapping)
            or not isinstance(slot["quota_horizons"], list)
            or not all(isinstance(row, Mapping) for row in slot["quota_horizons"])
        ):
            raise ProviderCapacityError("SLOT_SCHEMA_INVALID")
        health = _normalize_health(slot["health"], generated_at)
        cooling = _normalize_cooling(slot["cooling"])
        quotas = [
            _normalize_quota(row, generated_at)
            for row in slot["quota_horizons"]
        ]
        if quotas != sorted(quotas, key=lambda row: (_HORIZON_ORDER[row["horizon"]], row["metric"])):
            raise ProviderCapacityError("QUOTA_ORDER_INVALID")
        expected_quota_ids = [] if definition.capability_id in NO_QUOTA_SLOT_IDS else [
            ("five_hour", "provider_allocation"),
            ("weekly", "provider_allocation"),
        ]
        if [(row["horizon"], row["metric"]) for row in quotas] != expected_quota_ids:
            raise ProviderCapacityError("QUOTA_INVENTORY_INVALID")
        outcome = _normalize_outcome(slot["last_outcome"])
        if definition.capability_id in UNCONFIGURED_SLOT_IDS and (
            slot["present"] is not False
            or slot["enabled"] is not False
            or health != _unknown_health()
            or cooling != _unknown_cooling()
            or quotas
            or outcome != {"class": "unknown", "observed_at": None}
        ):
            raise ProviderCapacityError("UNCONFIGURED_SLOT_STATE_INVALID")
        required_degradations: list[str] = []
        if definition.capability_id in UNCONFIGURED_SLOT_IDS:
            required_degradations.append("PROVIDER_CONFIGURATION_UNCONFIGURED")
        if slot["present"] is None:
            required_degradations.append("PROVIDER_PRESENCE_UNKNOWN")
        if slot["enabled"] is None:
            required_degradations.append("PROVIDER_ENABLEMENT_UNKNOWN")
        if cooling["active"] is None:
            required_degradations.append("PROVIDER_COOLING_UNKNOWN")
        if health["state"] == "unknown":
            required_degradations.append("PROVIDER_HEALTH_UNKNOWN")
        if not quotas or any(row["evidence"] == "unknown" for row in quotas):
            required_degradations.append("PROVIDER_BUDGET_UNKNOWN")
        if outcome["class"] == "unknown":
            required_degradations.append("PROVIDER_OUTCOME_UNKNOWN")
        for code in required_degradations:
            if (code, definition.capability_id) not in degraded_scopes:
                raise ProviderCapacityError("REQUIRED_DEGRADATION_MISSING")
        normalized_slots.append(dict(slot))
    if set(definitions) != {slot["capability_id"] for slot in normalized_slots}:
        raise ProviderCapacityError("SLOT_INVENTORY_INCOMPLETE")
    if normalized_slots != sorted(
        normalized_slots,
        key=lambda row: (row["host_ref"], row["provider"], row["capability_id"]),
    ):
        raise ProviderCapacityError("SLOT_ORDER_INVALID")
    if not audit["material_sources_match_commit"] and not any(
        row["code"] == "PRODUCER_SOURCE_UNGROUNDED" for row in document["degraded"]
    ):
        raise ProviderCapacityError("UNGROUNDED_DEGRADATION_MISSING")
    if check_hash and document["snapshot_hash"] != _semantic_snapshot_hash(document):
        raise ProviderCapacityError("SNAPSHOT_HASH_MISMATCH")


def canonical_json(document: Mapping[str, Any], *, pretty: bool = False) -> str:
    validate_snapshot(document)
    if pretty:
        return json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    return _canonical_bytes(document).decode("utf-8") + "\n"
