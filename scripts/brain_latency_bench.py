#!/usr/bin/env python3
"""Measure Mastermind brain latency end-to-end against a running gateway.

WHY THIS EXISTS
    "Mastermind feels slow" was an argument until the competitive teardown measured it:
    headers in 0.5-0.8s, then 48-73 seconds of blocking tool rounds before the first
    answer byte, against a competitor's 2.14s on a one-line price question
    (research/DEEPVUE_COMPETITIVE_TEARDOWN_AND_MASTERMIND_BUILD_DOCKET_2026-08-01.md
    §6.3 and §6.7). This script is how that measurement is re-run — same prompts, same
    surface, one table.

WHAT IT MEASURES (per probe, client-side, wall clock from the request going out)
    headers_ms       response headers back (the network + auth + quota preamble)
    first_status_ms  first `status` SSE event (the widget's first sign of life)
    ttfv_ms          first `delta` event — time to first VISIBLE answer byte
    done_ms          the `done` event
    n_deltas         how many delta events carried the answer
    n_tool_events    tool rounds the turn spent
    route            'instant' | 'deep', read from done.usage.latency.route

    A server without the W5 latency work simply has no route/latency keys; those
    columns print "-" and every timing above still works.

NO LEDGER WRITES. This is a probe, not a pipeline: results go to stdout, and to a
JSONL file only when --out names one. Nothing under data/ is ever touched (house law:
nightly is the sole advancer of forward ledgers).

USAGE
    python3 scripts/brain_latency_bench.py --cookie "$MM_AID" --label cold
    python3 scripts/brain_latency_bench.py --bearer "$SUPABASE_ACCESS_TOKEN" --runs 3 --label warm
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import statistics
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# The docket's benchmark prompts
# ---------------------------------------------------------------------------
# Reproduced from
# research/DEEPVUE_COMPETITIVE_TEARDOWN_AND_MASTERMIND_BUILD_DOCKET_2026-08-01.md §6.3
# ("Prompt class" / "Prompt" columns), which is also the set the live A/B in §6.7 sent.
# Keep the wording stable — the recorded 27.33s / 9.81s / 2.14s competitor numbers and
# the 56.68s / 52.12s Mastermind numbers are only comparable against these asks.
#
# The fourth entry is NOT from the docket. The docket's "simple current fact" prompt
# carries three extra instructions (one sentence, source, exact as-of), and the W5
# instant router deliberately refuses anything that elaborate — it is biased hard
# towards falling through to the deep loop. This bare form is the shape the instant
# lane actually claims, so the table can show both sides of the same question.
DOCKET_PROMPTS: tuple[tuple[str, str], ...] = (
    ("broad",
     "Give me situational awareness of the market right now: the regime, which themes "
     "are working, breadth, rates and liquidity, the catalysts ahead and the main "
     "risks. Cite your sources and timestamp every read."),
    ("native",
     "For AAPL give me relative strength over 1 month, 3 months and 12 months, its "
     "industry rank, its Stage, the next earnings date and the latest reported EPS "
     "growth. Give the as-of for each field and cite the source."),
    ("simple",
     "What is AAPL's current price? One sentence, with the source and the exact as-of."),
    ("instant",
     "What's AAPL trading at?"),
)

_COLUMNS = ("probe", "run", "headers_ms", "first_status_ms", "ttfv_ms", "done_ms",
            "n_deltas", "n_tool_events", "route")

# W0-B keeps the legacy four strings above byte-for-byte. The permanent corpus adds
# private prompts through --manifest rather than committing product/account-specific
# wording. The IDs and classes below are the public, stable contract; a private
# manifest supplies text needed to execute non-legacy rows and proves it with SHA-256.
W0B_MANIFEST_SCHEMA = "ai_benchmark_prompt_manifest.v1"
W0B_CORPUS_VERSION = "w0b.v1"
AI_BENCHMARK_RECEIPT_SCHEMA = "ai_benchmark_receipt.v1"
AI_BENCHMARK_SCORECARD_SCHEMA = "ai_benchmark_scorecard.v1"
W0B_RUBRIC_VERSION = "deepvue-w0b-quality.v1"
W0B_FROZEN_RUBRIC = {
    "score_domains": {
        "field_correctness": (
            "Binary 1 only when every requested factual field or analytical task is correctly "
            "answered; a degraded non-answer is 0."
        ),
        "missingness_honesty": (
            "Binary 1 when unavailable, stale, rights-blocked, or degraded state is stated "
            "without a fabricated replacement fact; otherwise 0."
        ),
        "numeric_correctness": (
            "Binary 1 only when every requested number, date, unit, and deterministic calculation "
            "is correct and traceable; a degraded non-answer is 0."
        ),
        "source_as_of_correctness": (
            "Binary 1 only when every current factual read carries the correct owner and as-of, "
            "including source quality and recency; a degraded non-answer is 0."
        ),
        "source_span_correctness": (
            "Binary 1 only when citations or typed receipts cover the exact factual claims they "
            "support; a degraded non-answer is 0."
        ),
        "unsupported_claim_count": (
            "Non-negative integer count of visible factual claims unsupported by an identified "
            "source, evidence span, or typed receipt."
        ),
    },
    "class_criteria": {
        "current-market": (
            "Judge regime, breadth, themes, liquidity, source quality, timestamp coverage, and "
            "unsupported claims."
        ),
        "native-multi-field": (
            "Judge explicit context use, exact field provenance, units, per-field as-of, and "
            "missingness honesty for RS, Stage, industry, and earnings facts."
        ),
        "simple-fact": (
            "Judge freshness, numeric accuracy, exact as-of, and source coverage of the requested "
            "single fact."
        ),
        "instant-fact": (
            "Judge the same single-fact law as simple-fact and require that latency never excuses "
            "wrong identity, value, freshness, or provenance."
        ),
        "context-collision": (
            "Judge explicit requested-entity precedence over conflicting ambient context, plus "
            "the correctness and provenance of the resulting fact."
        ),
        "screener-compilation": (
            "Judge condition-by-condition AST fidelity and correctness of the executable result; "
            "prose similarity is insufficient."
        ),
        "calculation": (
            "Judge deterministic arithmetic, declared units, explicit inputs, and reproducibility."
        ),
        "filing-event": (
            "Judge primary-source quality, claim-to-source-span correctness, dates, and unsupported "
            "claims in the reported-quarter explanation."
        ),
        "deep-synthesis": (
            "Judge tool selection, contradiction handling, authority discipline, source coverage, "
            "and unsupported claims across Neural Web and Prophet evidence."
        ),
    },
    "automatic_receipt_metrics": [
        "cache_label_and_basis",
        "headers_first_status_ttfv_completion_ms",
        "context_and_output_bytes",
        "route_and_tool_count_duration",
        "explicit_context_and_effective_entity",
        "degraded_and_error_state",
    ],
}
W0B_RUBRIC_DIGEST = "3f6b87f4754e2d57ea75beaf20340e42c94ff4fbb0f64ecc83770c880b65f70f"

_NATIVE_FIELD_IDS = frozenset({
    "market.price.last",
    "market.return.1m",
    "market.return.3m",
    "market.return.12m",
    "stage.current",
    "stage.weeks_in_stage",
    "industry.rank.percentile",
    "security.industry_member.rs_percentile",
    "earnings.next_date",
    "earnings.latest.eps_growth_pct",
    "earnings.latest.revenue_growth_pct",
    "theme.local.memberships",
})
_NATIVE_STATUSES = frozenset({
    "available", "unknown", "unavailable", "stale", "not_applicable", "rights_blocked",
})
_NATIVE_RELATIONSHIP_STATUSES = frozenset({
    "available", "unknown", "unavailable", "stale", "not_applicable",
})
_NATIVE_REASON_CODES = frozenset({
    "owner_missing", "owner_unavailable", "owner_degraded", "owner_stale",
    "value_missing", "history_not_supported", "not_applicable", "rights_blocked",
    "retired_entity", "superseded_entity",
})
_NATIVE_FIELD_UNITS = {
    "market.price.last": "currency",
    "market.return.1m": "percent",
    "market.return.3m": "percent",
    "market.return.12m": "percent",
    "stage.current": "stage_code",
    "stage.weeks_in_stage": "weeks",
    "industry.rank.percentile": "percentile",
    "security.industry_member.rs_percentile": "percentile",
    "earnings.next_date": "iso_date",
    "earnings.latest.eps_growth_pct": "percent",
    "earnings.latest.revenue_growth_pct": "percent",
    "theme.local.memberships": "entity_refs",
}
_NATIVE_PRECEDENCE_REASONS = frozenset({
    "explicit_request", "explicit_entity_wins", "ambient_context",
})
_NATIVE_FRESHNESS_STATES = frozenset({"fresh", "stale", "unknown", "not_applicable"})
_NATIVE_RECEIPT_KINDS = frozenset({
    "typed_fact", "owner_relationship", "resolution_failure",
})
_NATIVE_RECEIPT_REFERENCES = frozenset({
    "relationship_receipt", "rank_resolution_failure",
})
_NATIVE_RANK_FAILURES = frozenset({
    "relationship_resolver_unavailable", "industry_rank_resolver_unavailable",
})
_NATIVE_FAILURE_REASONS = frozenset({
    "identity_unavailable", "resolver_unavailable", "subscriber_projection_invalid",
})
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
_SECURITY_ID_RE = re.compile(r"^SEC:[A-Z0-9][A-Z0-9:._-]{2,157}$")
_CLAUSE_ID_RE = re.compile(r"^c[1-9][0-9]*$")
_PROOF_CLOCK_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))?$"
)
_PATH_LIKE_RE = re.compile(
    r"(?:^|[\\/])(?:Users|home|private|tmp|var|etc)(?:[\\/]|$)|"
    r"(?:^|[\\/])\.\.(?:[\\/]|$)|^~[\\/]|^[A-Za-z]:[\\/]|^file://",
    re.IGNORECASE,
)
_RECEIPT_ERROR_CODES = frozenset({
    "connection_unavailable",
    "stream_broken",
    "native_proof_missing_or_malformed",
    "native_degraded_proof_mismatch",
    "probe_error",
})
_HEALTH_ERROR_CODES = frozenset({
    "health_unavailable",
    "health_response_not_object",
    "health_identity_missing",
})

_LEGACY_W0B_META: dict[str, tuple[str, str, str]] = {
    # legacy label: (prompt_id, prompt_version, prompt_class)
    "broad": ("legacy.broad.v1", "legacy.v1", "current-market"),
    "native": ("legacy.native.v1", "legacy.v1", "native-multi-field"),
    "simple": ("legacy.simple.v1", "legacy.v1", "simple-fact"),
    "instant": ("legacy.instant.v1", "legacy.v1", "instant-fact"),
}

# These names deliberately carry no prompt text or prompt hashes. A W0-B operator
# provides private text and its matching hash at execution time in an external manifest.
W0B_CORPUS_V1: tuple[tuple[str, str], ...] = (
    ("legacy.broad.v1", "current-market"),
    ("legacy.native.v1", "native-multi-field"),
    ("legacy.simple.v1", "simple-fact"),
    ("legacy.instant.v1", "instant-fact"),
    ("w0b.context-collision.v1", "context-collision"),
    ("w0b.screener-compilation.v1", "screener-compilation"),
    ("w0b.calculation.v1", "calculation"),
    ("w0b.filing-event.v1", "filing-event"),
    ("w0b.deep-synthesis.v1", "deep-synthesis"),
)

RECEIPT_REQUIRED_FIELDS = frozenset({
    "schema", "system", "environment", "deployed_commit", "deployed_checkout",
    "prompt_id", "prompt_version", "prompt_class", "prompt_text_hash", "manifest_digest",
    "explicit_context", "ambient_context", "expected_effective_entity",
    "expected_precedence_reason", "actual_effective_entity",
    "actual_precedence_reason", "ambient_used", "precedence_match",
    "native_fact_receipt", "cache_label", "cache_basis", "route",
    "headers_ms", "first_status_ms", "ttfv_ms", "done_ms", "n_tool_events",
    "server_tool_count", "server_tool_durations_ms", "context_bytes", "output_bytes",
    "field_correctness", "numeric_correctness", "source_span_correctness",
    "source_as_of_correctness",
    "unsupported_claim_count", "missingness_honesty", "degraded", "error",
    "reviewer", "rubric_version", "rubric_digest", "recorded_at",
})
RECEIPT_ALLOWED_FIELDS = RECEIPT_REQUIRED_FIELDS | frozenset({
    "probe", "label", "base_url", "ts", "health_error", "lane", "run",
    "n_deltas", "server_timing", "server_latency", "answer_chars",
})


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json_bytes(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":")).encode("utf-8"))


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _receipt_error_code(value: Any) -> str | None:
    """Project display-oriented probe errors onto a closed, text-free code set."""
    if value is None:
        return None
    if isinstance(value, str):
        match = re.match(r"^HTTP (\d{3})(?:\b|$)", value)
        if match:
            return f"http_{match.group(1)}"
        if value.startswith("cannot reach "):
            return "connection_unavailable"
        if value.startswith("stream broke after headers"):
            return "stream_broken"
        if value == "native route omitted or malformed proof receipt":
            return "native_proof_missing_or_malformed"
        if value == "native route degraded flag disagrees with proof receipt":
            return "native_degraded_proof_mismatch"
    return "probe_error"


def _health_error_code(value: Any) -> str | None:
    """Project health diagnostics onto a closed receipt code set."""
    if value is None:
        return None
    if isinstance(value, str):
        if value.startswith("health unavailable"):
            return "health_unavailable"
        if value == "health response was not an object":
            return "health_response_not_object"
        if value == "health response lacked commit/checkout identity":
            return "health_identity_missing"
    return "health_unavailable"


_PRIVATE_CONTEXT_KEY_MARKERS = ("account", "auth", "bearer", "cookie", "email", "secret",
                                "token", "user_id")


def _safe_context_metadata(value: Any) -> Any:
    """Project only the public benchmark context vocabulary.

    Arbitrary JSON is not evidence: values can carry credentials or local paths
    even when their keys look harmless. W0-B needs only entity/entities, page,
    and symbol, so reject everything else before it reaches either a request or
    a text-free receipt.
    """
    if not isinstance(value, dict):
        raise ValueError("context metadata must be an object")
    out: dict[str, Any] = {}
    entity_re = re.compile(r"^[A-Z][A-Z0-9.-]{0,15}$")
    page_re = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
    for key, child in value.items():
        if not isinstance(key, str) or any(marker in key.lower()
                                           for marker in _PRIVATE_CONTEXT_KEY_MARKERS):
            raise ValueError("context metadata may not contain credentials or account identifiers")
        if key in {"entity", "symbol"}:
            if not isinstance(child, str) or not entity_re.fullmatch(child):
                raise ValueError(f"context {key} must be a public ticker identity")
            out[key] = child
        elif key == "entities":
            if (not isinstance(child, list) or not child or len(child) > 20
                    or any(not isinstance(item, str) or not entity_re.fullmatch(item)
                           for item in child)):
                raise ValueError("context entities must be public ticker identities")
            out[key] = list(child)
        elif key == "page":
            if not isinstance(child, str) or not page_re.fullmatch(child):
                raise ValueError("context page must be a public route token")
            out[key] = child
        else:
            raise ValueError(f"context metadata key is not allowed: {key}")
    return out


def _safe_base_url(value: str) -> str:
    """Project an operator URL onto a credential-free origin."""
    parts = urlsplit(value)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, "", "", ""))


def _legacy_prompt_specs(*, page: str = "", symbol: str = "") -> list[dict]:
    """Make receipt-safe specs for the immutable legacy prompt tuple."""
    ambient = _safe_context_metadata(
        {k: v for k, v in (("page", page), ("symbol", symbol)) if v}
    )
    specs = []
    for label, message in DOCKET_PROMPTS:
        prompt_id, prompt_version, prompt_class = _LEGACY_W0B_META[label]
        specs.append({
            "label": label,
            "prompt_id": prompt_id,
            "prompt_version": prompt_version,
            "prompt_class": prompt_class,
            "message": message,
            "prompt_text_hash": _sha256_text(message),
            "explicit_context": {},
            "ambient_context": dict(ambient),
            "expected_effective_entity": None,
            "expected_precedence_reason": None,
        })
    digest = _corpus_manifest_digest(specs)
    return [{**spec, "manifest_digest": digest} for spec in specs]


def _corpus_manifest_digest(specs: list[dict]) -> str:
    """Bind private prompt hashes and context law without retaining prompt text."""
    canonical = {
        "schema": W0B_MANIFEST_SCHEMA,
        "version": W0B_CORPUS_VERSION,
        "prompts": [{
            "prompt_id": spec["prompt_id"],
            "prompt_class": spec["prompt_class"],
            "prompt_text_hash": spec["prompt_text_hash"],
            "explicit_context": spec.get("explicit_context") or {},
            "ambient_context": spec.get("ambient_context") or {},
            "expected_effective_entity": spec.get("expected_effective_entity"),
            "expected_precedence_reason": spec.get("expected_precedence_reason"),
        } for spec in specs],
    }
    return hashlib.sha256(json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()


def load_private_manifest(path: str) -> tuple[str, str, list[dict]]:
    """Load a text-bearing W0-B manifest kept outside this repository."""
    try:
        manifest_path = _assert_private_output_path(path, kind="manifest")
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot load private manifest: {type(exc).__name__}") from exc
    if (not isinstance(raw, dict) or set(raw) != {"schema", "version", "prompts"}
            or raw.get("schema") != W0B_MANIFEST_SCHEMA):
        raise ValueError(f"manifest schema must be {W0B_MANIFEST_SCHEMA}")
    version = raw.get("version")
    prompts = raw.get("prompts")
    if version != W0B_CORPUS_VERSION or not isinstance(prompts, list) or not prompts:
        raise ValueError(f"manifest version must be {W0B_CORPUS_VERSION} with complete prompts")

    seen: set[str] = set()
    specs: list[dict] = []
    allowed = dict(W0B_CORPUS_V1)
    allowed_item_keys = {
        "prompt_id", "prompt_class", "prompt_text", "prompt_text_hash",
        "explicit_context", "ambient_context", "expected_effective_entity",
        "expected_precedence_reason",
    }
    legacy_text = {
        _LEGACY_W0B_META[label][0]: message for label, message in DOCKET_PROMPTS
    }
    for item in prompts:
        if not isinstance(item, dict) or set(item) - allowed_item_keys:
            raise ValueError("manifest prompts must be objects")
        prompt_id = item.get("prompt_id")
        prompt_class = item.get("prompt_class")
        message = item.get("prompt_text")
        declared_hash = item.get("prompt_text_hash")
        if (not isinstance(prompt_id, str) or prompt_id not in allowed or prompt_id in seen
                or not isinstance(prompt_class, str) or allowed[prompt_id] != prompt_class
                or not isinstance(message, str) or not message
                or not isinstance(declared_hash, str)):
            raise ValueError("manifest prompt has invalid id, class, text, or hash")
        actual_hash = _sha256_text(message)
        if declared_hash != actual_hash:
            raise ValueError(f"manifest prompt hash mismatch for {prompt_id}")
        if prompt_id in legacy_text and message != legacy_text[prompt_id]:
            raise ValueError(f"legacy docket prompt text drift for {prompt_id}")
        explicit = item.get("explicit_context") or {}
        ambient = item.get("ambient_context") or {}
        if not isinstance(explicit, dict) or not isinstance(ambient, dict):
            raise ValueError(f"manifest context must be objects for {prompt_id}")
        explicit = _safe_context_metadata(explicit)
        ambient = _safe_context_metadata(ambient)
        expected_entity = item.get("expected_effective_entity")
        expected_reason = item.get("expected_precedence_reason")
        if prompt_class == "context-collision" and (
                not isinstance(expected_entity, str) or not expected_entity
                or expected_reason != "explicit_entity_wins"
                or explicit.get("entity") != expected_entity
                or not isinstance(ambient.get("symbol"), str)
                or ambient["symbol"] == expected_entity
                or re.search(
                    rf"(?<![A-Z0-9.-])\$?{re.escape(expected_entity)}(?![A-Z0-9.-])",
                    message,
                    re.IGNORECASE,
                ) is None):
            raise ValueError("context-collision requires expected entity and precedence reason")
        if prompt_class != "context-collision" and (
                expected_entity is not None or expected_reason is not None):
            raise ValueError("only context-collision may declare expected precedence")
        seen.add(prompt_id)
        specs.append({
            "label": prompt_id,
            "prompt_id": prompt_id,
            "prompt_version": version,
            "prompt_class": prompt_class,
            "message": message,
            "prompt_text_hash": actual_hash,
            "explicit_context": explicit,
            "ambient_context": ambient,
            "expected_effective_entity": expected_entity,
            "expected_precedence_reason": expected_reason,
        })
    if tuple(spec["prompt_id"] for spec in specs) != tuple(allowed):
        raise ValueError("manifest must contain the complete ordered W0-B corpus")
    manifest_digest = _corpus_manifest_digest(specs)
    return version, manifest_digest, [
        {**spec, "manifest_digest": manifest_digest} for spec in specs
    ]


# ---------------------------------------------------------------------------
# SSE parsing
# ---------------------------------------------------------------------------

class SSEParser:
    """Incremental ``text/event-stream`` parser: feed one decoded line, get 0+ events.

    Only the pieces this endpoint uses are implemented: ``data:`` fields (joined with
    newlines across a multi-line event), a blank line as the dispatch boundary, and
    ``:`` comment lines — which matter, because the brain's run pump injects
    ``: keepalive`` comments through the dead air of a blocking tool turn and a parser
    that mistook one for an event would report a phantom first byte.

    A ``data:`` payload that is not JSON is dropped rather than raised on: this is a
    measuring instrument, and it must survive a degraded server well enough to report
    what it saw.
    """

    def __init__(self) -> None:
        self._data: list[str] = []

    def feed(self, line: str) -> list[dict]:
        line = line.rstrip("\n").rstrip("\r")
        if line.startswith(":"):
            return []                      # comment / keepalive
        if line == "":
            return self._dispatch()
        field, _, value = line.partition(":")
        if field == "data":
            self._data.append(value[1:] if value.startswith(" ") else value)
        return []                          # event:/id:/retry: are not used here

    def close(self) -> list[dict]:
        """Flush an event left pending by a stream that ended without a blank line."""
        return self._dispatch()

    def _dispatch(self) -> list[dict]:
        if not self._data:
            return []
        payload = "\n".join(self._data)
        self._data = []
        try:
            obj = json.loads(payload)
        except (ValueError, TypeError):
            return []
        return [obj] if isinstance(obj, dict) else []


def read_events(lines: Iterable[str], clock=time.monotonic) -> list[tuple[dict, float]]:
    """Parse a whole SSE line stream into (event, arrival_clock) pairs."""
    parser = SSEParser()
    out: list[tuple[dict, float]] = []
    for line in lines:
        for ev in parser.feed(line):
            out.append((ev, clock()))
    for ev in parser.close():
        out.append((ev, clock()))
    return out


def _safe_native_fact_receipt(value: Any) -> dict | None:
    """Keep proof-bearing native metadata while excluding values, text, and paths."""
    if (
        not isinstance(value, dict)
        or value.get("schema") != "brain.native_fact_receipt.v1"
        or value.get("route") != "instant/native-fact"
        or value.get("planner_version") != "w1b.native_fact_planner.v1"
    ):
        return None

    def enum(raw: Any, allowed: frozenset[str], *, optional: bool = False) -> str | None:
        if raw is None and optional:
            return None
        if not isinstance(raw, str) or raw not in allowed:
            raise ValueError("native proof enum is invalid")
        return raw

    def hex64(raw: Any, *, optional: bool = False) -> str | None:
        if raw is None and optional:
            return None
        if not isinstance(raw, str) or not _HEX64_RE.fullmatch(raw):
            raise ValueError("native proof digest is invalid")
        return raw

    def safe_token(raw: Any, pattern: re.Pattern[str], *, optional: bool = False) -> str | None:
        if raw is None and optional:
            return None
        if (not isinstance(raw, str) or _PATH_LIKE_RE.search(raw)
                or not pattern.fullmatch(raw)):
            raise ValueError("native proof token is invalid")
        return raw

    def safe_clock(raw: Any) -> str | None:
        return safe_token(raw, _PROOF_CLOCK_RE, optional=True)

    def safe_unit(field_id: str, raw: Any) -> str:
        expected = _NATIVE_FIELD_UNITS[field_id]
        if raw == expected:
            return raw
        # W1-A freezes market.price.last as owner_currency_code: an available
        # price carries the owner's concrete ISO 4217 code (for example USD),
        # not the registry's abstract ``currency`` unit.  Keep that dynamic
        # surface closed to exactly three uppercase ASCII letters and bind it
        # to the sole dynamic-unit field.
        if (field_id == "market.price.last" and isinstance(raw, str)
                and re.fullmatch(r"[A-Z]{3}", raw)):
            return raw
        raise ValueError("native proof unit is invalid")

    def safe_industry_id(raw: Any) -> str:
        if (not isinstance(raw, str) or not raw or len(raw) > 160
                or _PATH_LIKE_RE.search(raw) or any(ord(char) < 32 for char in raw)
                or "/" in raw or "\\" in raw):
            raise ValueError("native proof industry identity is invalid")
        return raw

    def safe_entity(raw: Any) -> dict[str, str]:
        if not isinstance(raw, dict):
            raise ValueError("native proof entity is invalid")
        entity_type = raw.get("type")
        if entity_type == "security":
            entity_id = safe_token(raw.get("id"), _SECURITY_ID_RE)
        elif entity_type == "industry":
            entity_id = safe_industry_id(raw.get("id"))
        else:
            raise ValueError("native proof entity type is invalid")
        return {"type": entity_type, "id": entity_id}

    effective = value.get("effective_context")
    effective = effective if isinstance(effective, dict) else {}
    try:
        symbol = safe_token(effective.get("symbol"), re.compile(r"^[A-Z]{1,5}$"))
        precedence = enum(effective.get("precedence_reason"), _NATIVE_PRECEDENCE_REASONS)
        ambient_used = effective.get("ambient_used")
        if not isinstance(ambient_used, bool):
            raise ValueError("native ambient-use proof is invalid")
        digest = hex64(value.get("registry_digest"), optional=True)

        canonical_raw = value.get("canonical_entity")
        canonical = None
        identity_raw = value.get("identity_admission")
        identity_admission = None
        if identity_raw is not None:
            if not isinstance(identity_raw, dict) or set(identity_raw) != {
                "requested_symbol", "alias_interpretation", "canonical_security_id",
            }:
                raise ValueError("native identity admission proof is invalid")
            identity_admission = {
                "requested_symbol": safe_token(
                    identity_raw.get("requested_symbol"), re.compile(r"^[A-Z]{1,5}$")
                ),
                "alias_interpretation": enum(
                    identity_raw.get("alias_interpretation"), frozenset({"current_alias_only"})
                ),
                "canonical_security_id": safe_token(
                    identity_raw.get("canonical_security_id"), _SECURITY_ID_RE
                ),
            }
            if identity_admission["requested_symbol"] != symbol:
                raise ValueError("native identity admission differs from effective symbol")
        if canonical_raw is not None:
            if not isinstance(canonical_raw, dict) or canonical_raw.get("type") != "security":
                raise ValueError("native canonical entity is invalid")
            canonical = safe_entity(canonical_raw)
            if digest is None:
                raise ValueError("native canonical proof lacks registry digest")
            if (identity_admission is None
                    or identity_admission["canonical_security_id"] != canonical["id"]):
                raise ValueError("native identity admission differs from canonical security")

        raw_facts = value.get("facts") or []
        if not isinstance(raw_facts, list):
            raise ValueError("native facts proof is invalid")
        facts = []
        for fact in raw_facts:
            if not isinstance(fact, dict):
                raise ValueError("native fact proof is invalid")
            field_id = enum(fact.get("field_id"), _NATIVE_FIELD_IDS)
            source = fact.get("source")
            freshness = fact.get("freshness")
            display_order = fact.get("display_order")
            if (not isinstance(source, dict) or not isinstance(freshness, dict)
                    or not isinstance(display_order, int) or isinstance(display_order, bool)
                    or display_order < 0):
                raise ValueError("native fact metadata is invalid")
            facts.append({
                "clause_id": safe_token(fact.get("clause_id"), _CLAUSE_ID_RE),
                "display_order": display_order,
                "field_id": field_id,
                "entity": safe_entity(fact.get("entity")),
                "fact_fingerprint": hex64(fact.get("fact_fingerprint")),
                "status": enum(fact.get("status"), _NATIVE_STATUSES),
                "reason_code": enum(
                    fact.get("reason_code"), _NATIVE_REASON_CODES, optional=True
                ),
                "unit": safe_unit(field_id, fact.get("unit")),
                "source_id": safe_token(source.get("source_id"), _SOURCE_ID_RE),
                "as_of": safe_clock(fact.get("as_of")),
                "freshness": enum(
                    freshness.get("state"), _NATIVE_FRESHNESS_STATES
                ),
            })

        raw_clauses = value.get("clauses") or []
        if not isinstance(raw_clauses, list):
            raise ValueError("native clauses proof is invalid")
        clauses = []
        for clause in raw_clauses:
            if not isinstance(clause, dict):
                raise ValueError("native clause proof is invalid")
            display_order = clause.get("display_order")
            if (not isinstance(display_order, int) or isinstance(display_order, bool)
                    or display_order < 0):
                raise ValueError("native clause order is invalid")
            kind = enum(clause.get("receipt_kind"), _NATIVE_RECEIPT_KINDS)
            field_id = enum(clause.get("field_id"), _NATIVE_FIELD_IDS, optional=True)
            requested_field_id = enum(
                clause.get("requested_field_id"), _NATIVE_FIELD_IDS, optional=True
            )
            fingerprint = hex64(clause.get("fact_fingerprint"), optional=True)
            reference = enum(
                clause.get("receipt_reference"), _NATIVE_RECEIPT_REFERENCES, optional=True
            )
            if kind == "typed_fact" and (field_id is None or fingerprint is None):
                raise ValueError("typed native clause lacks field proof")
            if kind == "typed_fact" and (requested_field_id is not None or reference is not None):
                raise ValueError("typed native clause carries unrelated resolution proof")
            if kind != "typed_fact" and (
                requested_field_id is None or reference is None
                or field_id is not None or fingerprint is not None
            ):
                raise ValueError("unavailable native clause lacks isolated resolution proof")
            clauses.append({
                "clause_id": safe_token(clause.get("clause_id"), _CLAUSE_ID_RE),
                "display_order": display_order,
                "field_id": field_id,
                "requested_field_id": requested_field_id,
                "fact_fingerprint": fingerprint,
                "status": enum(clause.get("status"), _NATIVE_STATUSES),
                "receipt_kind": kind,
                "receipt_reference": reference,
            })

        relationship_raw = value.get("relationship_receipt")
        relationship = None
        if relationship_raw is not None:
            if not isinstance(relationship_raw, dict):
                raise ValueError("native relationship proof is invalid")
            relationship_from = safe_entity(relationship_raw.get("from"))
            if relationship_from.get("type") != "security":
                raise ValueError("native relationship source entity is invalid")
            relationship_to = relationship_raw.get("to")
            industry_id = None
            if relationship_to is not None:
                if (not isinstance(relationship_to, dict)
                        or relationship_to.get("type") != "industry"):
                    raise ValueError("native relationship target is invalid")
                industry_id = safe_industry_id(relationship_to.get("id"))
            relationship_source = relationship_raw.get("source")
            if not isinstance(relationship_source, dict):
                raise ValueError("native relationship source is invalid")
            relationship_status = enum(
                relationship_raw.get("status"), _NATIVE_RELATIONSHIP_STATUSES
            )
            relationship_reason = enum(
                relationship_raw.get("reason_code"), _NATIVE_REASON_CODES, optional=True
            )
            if relationship_status == "available":
                if industry_id is None or relationship_reason is not None:
                    raise ValueError("available native relationship lacks a clean target")
            elif industry_id is not None or relationship_reason is None:
                raise ValueError("non-available native relationship carries a target")
            relationship = {
                "status": relationship_status,
                "reason_code": relationship_reason,
                "from_security_id": relationship_from["id"],
                "industry_id": industry_id,
                "relationship_fingerprint": hex64(
                    relationship_raw.get("relationship_fingerprint")
                ),
                "source_id": safe_token(
                    relationship_source.get("source_id"), _SOURCE_ID_RE
                ),
                "as_of": safe_clock(relationship_raw.get("as_of")),
            }

        rank_failure = enum(
            value.get("rank_resolution_failure"), _NATIVE_RANK_FAILURES, optional=True
        )
        failure_raw = value.get("failure")
        failure = None
        if failure_raw is not None:
            if not isinstance(failure_raw, dict) or failure_raw.get("status") != "unavailable":
                raise ValueError("native failure proof is invalid")
            failure = {
                "status": "unavailable",
                "reason_code": enum(
                    failure_raw.get("reason_code"), _NATIVE_FAILURE_REASONS
                ),
            }

        clause_ids = [clause["clause_id"] for clause in clauses]
        clause_orders = [clause["display_order"] for clause in clauses]
        if len(set(clause_ids)) != len(clause_ids) or len(set(clause_orders)) != len(clause_orders):
            raise ValueError("native clause identity/order is not unique")

        if failure is not None:
            if (canonical is not None or facts or clauses or relationship is not None
                    or rank_failure is not None or identity_admission is not None):
                raise ValueError("native failure receipt carries successful proof")
        else:
            if digest is None or canonical is None or identity_admission is None or not clauses:
                raise ValueError("native success receipt lacks typed proof")
            if relationship is not None and relationship["from_security_id"] != canonical["id"]:
                raise ValueError("native relationship origin differs from canonical security")
            typed_clauses = {
                clause["clause_id"]: clause
                for clause in clauses if clause["receipt_kind"] == "typed_fact"
            }
            if len(typed_clauses) != len(facts):
                raise ValueError("native typed fact/clause cardinality differs")
            for fact in facts:
                clause = typed_clauses.get(fact["clause_id"])
                if clause is None or any(
                    fact[key] != clause[key]
                    for key in (
                        "display_order", "field_id", "fact_fingerprint", "status",
                    )
                ):
                    raise ValueError("native typed fact/clause proof differs")
                if fact["field_id"] == "industry.rank.percentile":
                    expected_entity = (
                        {"type": "industry", "id": relationship["industry_id"]}
                        if relationship is not None and relationship["status"] == "available"
                        else None
                    )
                    if expected_entity is None or fact["entity"] != expected_entity:
                        raise ValueError("native industry-rank fact differs from relationship")
                elif fact["entity"] != canonical:
                    raise ValueError("native security fact differs from canonical security")
            for clause in clauses:
                kind = clause["receipt_kind"]
                reference = clause["receipt_reference"]
                if kind == "owner_relationship" and (
                    reference != "relationship_receipt" or relationship is None
                ):
                    raise ValueError("native relationship clause lacks referenced proof")
                if kind == "resolution_failure" and (
                    reference != "rank_resolution_failure" or rank_failure is None
                ):
                    raise ValueError("native resolution clause lacks referenced proof")
        return {
            "route": "instant/native-fact",
            "planner_version": "w1b.native_fact_planner.v1",
            "registry_digest": digest,
            "actual_effective_entity": symbol,
            "actual_precedence_reason": precedence,
            "ambient_used": ambient_used,
            "canonical_entity": canonical,
            "identity_admission": identity_admission,
            "facts": facts,
            "clauses": clauses,
            "relationship": relationship,
            "rank_resolution_failure": rank_failure,
            "failure": failure,
        }
    except (TypeError, ValueError):
        return None


def _is_safe_native_fact_projection(value: Any) -> bool:
    """Reinflate and re-project a stored native proof to prove its closed shape.

    ``_safe_native_fact_receipt`` consumes the richer SSE receipt and deliberately
    removes its schema wrapper plus nested value-bearing containers. Scoring sees
    that stored projection, not the raw SSE object. Re-running the raw sanitizer on
    the projection would reject every real native row, so reconstruct only the
    allowed raw proof shape and require exact idempotence after projection.
    """
    if not isinstance(value, dict):
        return False
    try:
        facts = [{
            "clause_id": fact["clause_id"],
            "display_order": fact["display_order"],
            "field_id": fact["field_id"],
            "entity": fact["entity"],
            "fact_fingerprint": fact["fact_fingerprint"],
            "status": fact["status"],
            "reason_code": fact["reason_code"],
            "unit": fact["unit"],
            "source": {"source_id": fact["source_id"]},
            "as_of": fact["as_of"],
            "freshness": {"state": fact["freshness"]},
        } for fact in value["facts"]]
        relationship = value["relationship"]
        raw_relationship = None
        if relationship is not None:
            raw_relationship = {
                "status": relationship["status"],
                "reason_code": relationship["reason_code"],
                "from": {
                    "type": "security", "id": relationship["from_security_id"],
                },
                "to": ({"type": "industry", "id": relationship["industry_id"]}
                       if relationship["industry_id"] is not None else None),
                "relationship_fingerprint": relationship["relationship_fingerprint"],
                "source": {"source_id": relationship["source_id"]},
                "as_of": relationship["as_of"],
            }
        raw = {
            "schema": "brain.native_fact_receipt.v1",
            "route": value["route"],
            "planner_version": value["planner_version"],
            "registry_digest": value["registry_digest"],
            "effective_context": {
                "symbol": value["actual_effective_entity"],
                "precedence_reason": value["actual_precedence_reason"],
                "ambient_used": value["ambient_used"],
            },
            "canonical_entity": value["canonical_entity"],
            "identity_admission": value["identity_admission"],
            "facts": facts,
            "clauses": value["clauses"],
            "relationship_receipt": raw_relationship,
            "rank_resolution_failure": value["rank_resolution_failure"],
            "failure": value["failure"],
        }
    except (KeyError, TypeError):
        return False
    return _safe_native_fact_receipt(raw) == value


def summarize(events: list[tuple[dict, float]], t0: float, headers_ms: int | None) -> dict:
    """Fold parsed events into one probe row. Missing keys stay None → printed as '-'."""
    row: dict[str, Any] = {
        "headers_ms": headers_ms,
        "first_status_ms": None,
        "ttfv_ms": None,
        "done_ms": None,
        "n_deltas": 0,
        "n_tool_events": 0,
        "route": None,
        "server_latency": None,
        "native_fact_receipt": None,
        "answer_chars": 0,
        "output_bytes": 0,
        "degraded": None,
        "error": None,
    }
    for ev, at in events:
        kind = ev.get("type")
        ms = int((at - t0) * 1000)
        if kind == "status" and row["first_status_ms"] is None:
            row["first_status_ms"] = ms
        elif kind == "tool":
            row["n_tool_events"] += 1
        elif kind == "delta":
            if row["ttfv_ms"] is None:
                row["ttfv_ms"] = ms
            row["n_deltas"] += 1
            text = str(ev.get("text") or "")
            row["answer_chars"] += len(text)
            row["output_bytes"] += len(text.encode("utf-8"))
        elif kind == "done":
            row["done_ms"] = ms
            row["degraded"] = bool(ev.get("degraded"))
            latency = (ev.get("usage") or {}).get("latency")
            if isinstance(latency, dict):
                row["server_latency"] = latency
                row["route"] = latency.get("route") or row["route"]
            if not row["route"] and ev.get("route"):
                row["route"] = ev.get("route")
            row["native_fact_receipt"] = _safe_native_fact_receipt(
                ev.get("native_fact_receipt")
            )
            if row["route"] == "instant/native-fact" and row["native_fact_receipt"] is None:
                row["degraded"] = True
                row["error"] = "native route omitted or malformed proof receipt"
            elif row["route"] == "instant/native-fact" and (
                bool(row["native_fact_receipt"].get("failure")) != bool(ev.get("degraded"))
            ):
                row["degraded"] = True
                row["error"] = "native route degraded flag disagrees with proof receipt"
    return row


def _server_tool_metrics(server_latency: Any) -> tuple[int | None, list[int] | None]:
    """Return only durable tool timing aggregates from the optional server record."""
    if not isinstance(server_latency, dict):
        return None, None
    count = 0
    durations: list[int] = []
    for round_ in server_latency.get("rounds") or []:
        if not isinstance(round_, dict):
            continue
        for tool in round_.get("tools") or []:
            if not isinstance(tool, dict):
                continue
            count += 1
            value = tool.get("ms")
            if (isinstance(value, (int, float)) and not isinstance(value, bool)
                    and math.isfinite(value) and value >= 0):
                durations.append(int(value))
    return count, durations


def _safe_server_timing(server_latency: Any) -> dict | None:
    """Project untrusted SSE timing onto the receipt's timing-only contract."""
    if not isinstance(server_latency, dict):
        return None
    def numeric(value: Any) -> int | float | None:
        return value if (
            isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value >= 0
        ) else None

    route = server_latency.get("route")
    out: dict[str, Any] = {
        "route": route if isinstance(route, str)
        and route in {"instant", "instant/native-fact", "deep"} else None,
        "ttfv_ms": numeric(server_latency.get("ttfv_ms")),
        "synthesis_ms": numeric(server_latency.get("synthesis_ms")),
        "total_ms": numeric(server_latency.get("total_ms")),
        "rounds": [],
    }
    for key in (
        "route_decision_ms", "context_assembly_ms", "registry_context_assembly_ms",
        "resolver_ms", "render_ms",
    ):
        out[key] = numeric(server_latency.get(key))
    for round_ in server_latency.get("rounds") or []:
        if not isinstance(round_, dict):
            continue
        tools = []
        for tool in round_.get("tools") or []:
            if isinstance(tool, dict) and numeric(tool.get("ms")) is not None:
                tools.append({"ms": numeric(tool["ms"])})
        out["rounds"].append({
            "model_ms": numeric(round_.get("model_ms")),
            "tools": tools,
        })
    return out


def _answer_text(events: list[tuple[dict, float]]) -> str:
    """Join only visible delta text for an explicitly requested private capture."""
    return "".join(str(event.get("text") or "") for event, _ in events
                   if event.get("type") == "delta")


def capture_health(health_url: str, *, timeout: float = 20.0) -> dict:
    """Read public deployment identity without credentials or a Brain turn."""
    if not health_url:
        return {"commit": None, "checkout": None, "error": None}
    try:
        request = urllib.request.Request(health_url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 -- operator URL
            payload = json.loads(response.read().decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001 -- health observation must not hide probe evidence
        return {"commit": None, "checkout": None, "error": f"health unavailable: {type(exc).__name__}"}
    if not isinstance(payload, dict):
        return {"commit": None, "checkout": None, "error": "health response was not an object"}
    commit = payload.get("commit")
    checkout = payload.get("checkout")
    safe_commit = commit if isinstance(commit, str) and re.fullmatch(r"[0-9a-fA-F]{7,64}", commit) else None
    safe_checkout = (checkout if isinstance(checkout, str)
                     and re.fullmatch(r"[0-9a-fA-F]{7,64}", checkout) else None)
    return {
        "commit": safe_commit,
        "checkout": safe_checkout,
        "error": None if safe_commit is not None or safe_checkout is not None
        else "health response lacked commit/checkout identity",
    }


def _sha_prefix_matches(observed: str | None, expected: str | None) -> bool:
    """Compare a public short deployment SHA with its expected full Git identity."""
    if not isinstance(observed, str) or not isinstance(expected, str):
        return False
    observed = observed.lower()
    expected = expected.lower()
    if (not re.fullmatch(r"[0-9a-f]{7,64}", observed)
            or not re.fullmatch(r"[0-9a-f]{7,64}", expected)):
        return False
    return observed.startswith(expected) or expected.startswith(observed)


# ---------------------------------------------------------------------------
# Probe
# ---------------------------------------------------------------------------

def probe(base_url: str, message: str, *, cookie: str = "", bearer: str = "",
          lane: str = "fast", page: str = "", symbol: str = "", context: dict | None = None,
          timeout: float = 180.0, capture_answer: bool = False) -> dict:
    """Send ONE prompt to POST /api/brain/stream and return its measured row."""
    url = base_url.rstrip("/") + "/api/brain/stream"
    body: dict[str, Any] = {"message": message, "lane": lane}
    request_context: dict[str, Any] = dict(context or {})
    if page:
        request_context["page"] = page
    if symbol:
        request_context["symbol"] = symbol
    if request_context:
        body["context"] = request_context

    headers = {"Content-Type": "application/json", "Accept": "text/event-stream",
               "User-Agent": "brain-latency-bench/1.0"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    if cookie:
        headers["Cookie"] = f"mm_aid={cookie}"

    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers=headers, method="POST")
    t0 = time.monotonic()
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)  # noqa: S310 — operator-supplied URL
    except urllib.error.HTTPError as exc:
        hint = ""
        if exc.code in (401, 403):
            hint = " — pass --cookie (mm_aid) or --bearer; an unauthenticated probe is unmeterable"
        elif exc.code == 402:
            hint = " — quota exhausted for this principal"
        elif exc.code == 429:
            hint = " — burst throttle; slow the run down"
        # Response bodies may reflect a prompt or private account state. A status code
        # is enough to classify a benchmark failure, so never print or receipt the body.
        return {"error": f"HTTP {exc.code}{hint}".strip(),
                "headers_ms": int((time.monotonic() - t0) * 1000)}
    except urllib.error.URLError as exc:
        return {"error": f"cannot reach {_safe_base_url(url)}: {type(exc).__name__}"}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"cannot reach {_safe_base_url(url)}: {type(exc).__name__}"}

    headers_ms = int((time.monotonic() - t0) * 1000)
    try:
        with resp:
            events = read_events((raw.decode("utf-8", "replace") for raw in resp))
    except Exception as exc:  # noqa: BLE001
        return {"error": f"stream broke after headers: {type(exc).__name__}",
                "headers_ms": headers_ms}
    row = summarize(events, t0, headers_ms)
    if capture_answer:
        row["_raw_answer"] = _answer_text(events)
    return row


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _cell(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(value)


def print_table(rows: list[dict]) -> None:
    """Fixed-width table on stdout. Rows carrying an `error` print it under the row."""
    printable = [[_cell(r.get(c)) for c in _COLUMNS] for r in rows]
    widths = [max(len(_COLUMNS[i]), *(len(r[i]) for r in printable)) if printable
              else len(_COLUMNS[i]) for i in range(len(_COLUMNS))]
    header = "  ".join(h.ljust(widths[i]) for i, h in enumerate(_COLUMNS))
    print(header)
    print("  ".join("-" * w for w in widths))
    for row, cells in zip(rows, printable):
        print("  ".join(c.ljust(widths[i]) for i, c in enumerate(cells)))
        if row.get("error"):
            print(f"    ! {row['error']}")


def print_medians(rows: list[dict]) -> None:
    """Per-probe medians — the number to quote when --runs > 1."""
    by_probe: dict[str, list[dict]] = {}
    for row in rows:
        if row.get("error"):
            continue
        by_probe.setdefault(str(row.get("probe")), []).append(row)
    if not any(len(v) > 1 for v in by_probe.values()):
        return
    print("\nmedians")
    for name, group in by_probe.items():
        parts = []
        for key in ("headers_ms", "ttfv_ms", "done_ms"):
            vals = [r[key] for r in group if isinstance(r.get(key), int)]
            parts.append(f"{key}={int(statistics.median(vals))}" if vals else f"{key}=-")
        print(f"  {name}: " + "  ".join(parts) + f"  (n={len(group)})")


def _nearest_rank_percentile(values: list[int], percentile: float) -> int | None:
    """Nearest-rank percentile, the fail-simple convention used by W1-B receipts."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, int((percentile * len(ordered) + 0.999999999)))
    return ordered[min(rank, len(ordered)) - 1]


def print_p95(rows: list[dict]) -> None:
    """Per-probe p95 for repeated runs; never relabel a single observation as p95."""
    by_probe: dict[str, list[dict]] = {}
    for row in rows:
        if not row.get("error"):
            by_probe.setdefault(str(row.get("probe")), []).append(row)
    repeated = {name: group for name, group in by_probe.items() if len(group) >= 2}
    if not repeated:
        return
    print("\np95 (nearest-rank)")
    for name, group in repeated.items():
        parts = []
        for key in ("headers_ms", "ttfv_ms", "done_ms"):
            values = [row[key] for row in group
                      if isinstance(row.get(key), int) and not isinstance(row.get(key), bool)]
            value = _nearest_rank_percentile(values, 0.95)
            parts.append(f"{key}={value if value is not None else '-'}")
        print(f"  {name}: " + "  ".join(parts) + f"  (n={len(group)})")


def build_receipt_row(row: dict, spec: dict, *, run: int, lane: str, system: str,
                      environment: str, cache_label: str, cache_basis: str,
                      health: dict, reviewer: str, rubric_version: str) -> dict:
    """Build a text-free ``ai_benchmark_receipt.v1`` row around one probe result."""
    server_timing = _safe_server_timing(row.get("server_latency"))
    server_tool_count, server_tool_durations = _server_tool_metrics(server_timing)
    ambient = dict(spec.get("ambient_context") or {})
    native_receipt = row.get("native_fact_receipt")
    native_receipt = native_receipt if isinstance(native_receipt, dict) else None
    actual_effective_entity = (
        native_receipt.get("actual_effective_entity") if native_receipt else None
    )
    actual_precedence_reason = (
        native_receipt.get("actual_precedence_reason") if native_receipt else None
    )
    expected_entity = spec.get("expected_effective_entity")
    expected_precedence = spec.get("expected_precedence_reason")
    precedence_match = None
    if expected_entity is not None or expected_precedence is not None:
        precedence_match = bool(
            expected_entity == actual_effective_entity
            and expected_precedence == actual_precedence_reason
        )
    receipt = {
        "schema": AI_BENCHMARK_RECEIPT_SCHEMA,
        # Retained legacy row keys keep existing JSONL consumers working.
        "probe": row.get("probe"),
        "label": row.get("label"),
        "base_url": row.get("base_url"),
        "ts": row.get("ts"),
        "system": system,
        "environment": environment,
        "deployed_commit": health.get("commit"),
        "deployed_checkout": health.get("checkout"),
        "health_error": _health_error_code(health.get("error")),
        "prompt_id": spec["prompt_id"],
        "prompt_version": spec["prompt_version"],
        "prompt_class": spec["prompt_class"],
        "prompt_text_hash": spec["prompt_text_hash"],
        "manifest_digest": spec.get("manifest_digest"),
        "explicit_context": dict(spec.get("explicit_context") or {}),
        "ambient_context": ambient,
        "expected_effective_entity": expected_entity,
        "expected_precedence_reason": expected_precedence,
        "actual_effective_entity": actual_effective_entity,
        "actual_precedence_reason": actual_precedence_reason,
        "ambient_used": native_receipt.get("ambient_used") if native_receipt else None,
        "precedence_match": precedence_match,
        "native_fact_receipt": native_receipt,
        "cache_label": cache_label,
        "cache_basis": cache_basis,
        "lane": lane,
        "run": run,
        "route": row.get("route"),
        "headers_ms": row.get("headers_ms"),
        "first_status_ms": row.get("first_status_ms"),
        "ttfv_ms": row.get("ttfv_ms"),
        "done_ms": row.get("done_ms"),
        "n_deltas": row.get("n_deltas"),
        "n_tool_events": row.get("n_tool_events"),
        "server_tool_count": server_tool_count,
        "server_tool_durations_ms": server_tool_durations,
        "server_timing": server_timing,
        "server_latency": server_timing,
        "answer_chars": row.get("answer_chars"),
        "context_bytes": _json_bytes(ambient),
        "output_bytes": row.get("output_bytes"),
        # These are reviewer score slots, not self-awarded scores. A frozen rubric
        # fills them after the private run without changing measured timings.
        "field_correctness": None,
        "numeric_correctness": None,
        "source_span_correctness": None,
        "source_as_of_correctness": None,
        "unsupported_claim_count": None,
        "missingness_honesty": None,
        "degraded": row.get("degraded"),
        "error": _receipt_error_code(row.get("error")),
        "reviewer": reviewer or None,
        "rubric_version": rubric_version or None,
        "rubric_digest": W0B_RUBRIC_DIGEST if rubric_version == W0B_RUBRIC_VERSION else None,
        "recorded_at": _utc_now(),
    }
    missing = RECEIPT_REQUIRED_FIELDS - set(receipt)
    if missing:  # pragma: no cover - defensive contract tripwire
        raise RuntimeError(f"receipt missing required fields: {sorted(missing)}")
    return receipt


def _assert_private_output_path(path: str, *, kind: str = "raw-answer") -> Path:
    """Reject private prompt/answer/receipt paths inside the repo, including data/site."""
    # Keep the caller's final path component intact for append_jsonl's
    # O_NOFOLLOW check. Resolution is only the repository-boundary proof; using
    # its return value for the write would turn a symlink into its target before
    # the no-follow open ever saw it.
    original = Path(os.path.abspath(Path(path).expanduser()))
    resolved = original.resolve()
    repo_root = Path(__file__).resolve().parent.parent
    try:
        resolved.relative_to(repo_root)
    except ValueError:
        return original
    raise ValueError(f"private {kind} path must be outside the repository")


def append_jsonl(path: str | Path, rows: Iterable[dict], *, exclusive: bool = False) -> None:
    """Append private JSONL through a no-symlink, owner-only file descriptor."""
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    if exclusive:
        flags |= os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise OSError("private benchmark target must be a regular file")
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as fh:
            fd = -1
            for row in rows:
                fh.write(json.dumps(row, default=str) + "\n")
    finally:
        if fd >= 0:
            os.close(fd)


_SCORE_FIELDS = (
    "field_correctness",
    "numeric_correctness",
    "source_span_correctness",
    "source_as_of_correctness",
    "unsupported_claim_count",
    "missingness_honesty",
)


def _valid_optional_nonnegative_number(value: Any) -> bool:
    return value is None or (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def _validate_receipt_row(row: Any) -> dict[str, Any]:
    """Validate one closed, text-free W0-B receipt before manual scoring."""
    if not isinstance(row, dict) or set(row) != RECEIPT_ALLOWED_FIELDS:
        raise ValueError("score input receipt fields are not the closed v1 schema")
    if row.get("schema") != AI_BENCHMARK_RECEIPT_SCHEMA:
        raise ValueError("score input must contain ai_benchmark_receipt.v1 rows")
    allowed_prompts = dict(W0B_CORPUS_V1)
    prompt_id = row.get("prompt_id")
    if (not isinstance(prompt_id, str) or prompt_id not in allowed_prompts
            or row.get("prompt_class") != allowed_prompts[prompt_id]
            or row.get("prompt_version") != W0B_CORPUS_VERSION
            or not isinstance(row.get("prompt_text_hash"), str)
            or not _HEX64_RE.fullmatch(row["prompt_text_hash"])
            or not isinstance(row.get("manifest_digest"), str)
            or not _HEX64_RE.fullmatch(row["manifest_digest"])):
        raise ValueError("score input receipt prompt identity is invalid")
    run = row.get("run")
    if (row.get("probe") != prompt_id or not isinstance(run, int)
            or isinstance(run, bool) or run < 1):
        raise ValueError("score input receipt run identity is invalid")
    for context_key in ("explicit_context", "ambient_context"):
        value = row.get(context_key)
        if _safe_context_metadata(value) != value:
            raise ValueError("score input receipt context projection is invalid")
    token_re = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
    for key in ("system", "environment", "cache_basis", "reviewer"):
        if not isinstance(row.get(key), str) or not token_re.fullmatch(row[key]):
            raise ValueError(f"score input receipt {key} is invalid")
    if (not isinstance(row.get("label"), str) or row.get("label") not in {"cold", "warm"}
            or not isinstance(row.get("cache_label"), str)
            or row.get("cache_label") not in {"cold", "warm"}
            or row.get("label") != row.get("cache_label")
            or not isinstance(row.get("lane"), str) or row.get("lane") not in {"fast", "pro"}):
        raise ValueError("score input receipt lane/cache labels are invalid")
    if row.get("rubric_version") != W0B_RUBRIC_VERSION \
            or row.get("rubric_digest") != W0B_RUBRIC_DIGEST:
        raise ValueError("score input receipt is not bound to the frozen W0-B rubric")
    for key in ("deployed_commit", "deployed_checkout"):
        if row.get(key) is not None and (
                not isinstance(row[key], str)
                or not re.fullmatch(r"[0-9a-fA-F]{7,64}", row[key])):
            raise ValueError("score input receipt deployment identity is invalid")
    if not isinstance(row.get("base_url"), str) \
            or _safe_base_url(row["base_url"]) != row["base_url"] \
            or urlsplit(row["base_url"]).scheme not in {"http", "https"} \
            or not urlsplit(row["base_url"]).hostname:
        raise ValueError("score input receipt base URL is invalid")
    if row.get("route") is not None and (
            not isinstance(row.get("route"), str)
            or row.get("route") not in {"deep", "instant", "instant/quote", "instant/native-fact"}):
        raise ValueError("score input receipt route is invalid")
    for key in (
        "headers_ms", "first_status_ms", "ttfv_ms", "done_ms", "context_bytes",
        "output_bytes", "answer_chars", "server_tool_count",
    ):
        if not _valid_optional_nonnegative_number(row.get(key)):
            raise ValueError("score input receipt timing/count is invalid")
    if row.get("context_bytes") != _json_bytes(row["ambient_context"]):
        raise ValueError("score input receipt context byte count is invalid")
    has_error = isinstance(row.get("error"), str) and bool(row["error"])
    for key in ("n_deltas", "n_tool_events"):
        value = row.get(key)
        if value is None and has_error:
            continue
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError("score input receipt event counts are invalid")
    durations = row.get("server_tool_durations_ms")
    tool_count = row.get("server_tool_count")
    if durations is None:
        if tool_count is not None:
            raise ValueError("score input receipt tool durations are invalid")
    elif not isinstance(durations, list) or any(
            not _valid_optional_nonnegative_number(value) or value is None for value in durations):
        raise ValueError("score input receipt tool durations are invalid")
    if (row.get("server_timing") != row.get("server_latency")
            or not isinstance(row.get("server_timing"), (dict, type(None)))
            or _safe_server_timing(row.get("server_timing")) != row.get("server_timing")):
        raise ValueError("score input receipt server timing is invalid")
    server_timing = row.get("server_timing")
    if server_timing is not None:
        if server_timing.get("route") != row.get("route"):
            raise ValueError("score input receipt route differs from server timing")
        expected_tool_count, expected_tool_durations = _server_tool_metrics(server_timing)
        if (row.get("server_tool_count"), row.get("server_tool_durations_ms")) != (
                expected_tool_count, expected_tool_durations):
            raise ValueError("score input receipt tool aggregates differ from server timing")
    elif row.get("server_tool_count") is not None or row.get("server_tool_durations_ms") is not None:
        raise ValueError("score input receipt tool aggregates lack server timing")
    degraded = row.get("degraded")
    if (degraded is None and not has_error) \
            or (degraded is not None and not isinstance(degraded, bool)) \
            or not isinstance(row.get("error"), (str, type(None))) \
            or not isinstance(row.get("health_error"), (str, type(None))):
        raise ValueError("score input receipt status is invalid")
    if row.get("error") is not None and (
            row["error"] not in _RECEIPT_ERROR_CODES
            and not re.fullmatch(r"http_\d{3}", row["error"])):
        raise ValueError("score input receipt error code is invalid")
    if row.get("health_error") is not None and row["health_error"] not in _HEALTH_ERROR_CODES:
        raise ValueError("score input receipt health code is invalid")
    if (row.get("ambient_used") is not None and not isinstance(row.get("ambient_used"), bool)) \
            or (row.get("precedence_match") is not None
                and not isinstance(row.get("precedence_match"), bool)):
        raise ValueError("score input receipt precedence state is invalid")
    entity_re = re.compile(r"^[A-Z][A-Z0-9.-]{0,15}$")
    for key in ("expected_effective_entity", "actual_effective_entity"):
        if row.get(key) is not None and (
                not isinstance(row[key], str) or not entity_re.fullmatch(row[key])):
            raise ValueError("score input receipt entity identity is invalid")
    for key in ("expected_precedence_reason", "actual_precedence_reason"):
        if row.get(key) is not None and (
                not isinstance(row[key], str) or row[key] not in _NATIVE_PRECEDENCE_REASONS):
            raise ValueError("score input receipt precedence reason is invalid")
    if row.get("prompt_class") == "context-collision":
        if (row.get("expected_precedence_reason") != "explicit_entity_wins"
                or row.get("precedence_match") != (
                    row.get("expected_effective_entity") == row.get("actual_effective_entity")
                    and row.get("expected_precedence_reason")
                    == row.get("actual_precedence_reason")
                )):
            raise ValueError("score input context-collision precedence proof is invalid")
    elif (row.get("expected_effective_entity") is not None
          or row.get("expected_precedence_reason") is not None
          or row.get("precedence_match") is not None):
        raise ValueError("score input non-collision receipt carries expected precedence")
    native = row.get("native_fact_receipt")
    if native is not None and not _is_safe_native_fact_projection(native):
        raise ValueError("score input native proof is invalid")
    if row.get("route") == "instant/native-fact" and native is None:
        raise ValueError("score input native route lacks typed proof")
    if native is not None:
        if row.get("route") != "instant/native-fact" or any(
                row.get(key) != native.get(key) for key in (
                    "actual_effective_entity", "actual_precedence_reason", "ambient_used",
                )) or degraded is not bool(native.get("failure")):
            raise ValueError("score input native proof differs from top-level identity")
    elif any(row.get(key) is not None for key in (
            "actual_effective_entity", "actual_precedence_reason", "ambient_used")):
        raise ValueError("score input non-native receipt carries native identity")
    if any(row.get(field) is not None for field in _SCORE_FIELDS):
        raise ValueError("score input receipt must be unscored")
    if (not isinstance(row.get("recorded_at"), str)
            or not _PROOF_CLOCK_RE.fullmatch(row["recorded_at"])
            or not isinstance(row.get("ts"), str)
            or not _PROOF_CLOCK_RE.fullmatch(row["ts"])):
        raise ValueError("score input receipt clock is invalid")
    if row.get("environment").lower().startswith("production") and (
            row.get("deployed_commit") is None or row.get("deployed_checkout") is None
            or row.get("health_error") is not None):
        raise ValueError("production score input lacks verified deployment identity")
    return row


def load_scorecard(path: str) -> dict[tuple[str, int], dict[str, Any]]:
    """Load a private, frozen manual adjudication keyed by prompt ID and run."""
    score_path = _assert_private_output_path(path, kind="scorecard")
    try:
        raw = json.loads(score_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot load private scorecard: {type(exc).__name__}") from exc
    if (not isinstance(raw, dict)
            or set(raw) != {
                "schema", "rubric_version", "reviewer", "rubric", "manifest_digest", "scores",
            }
            or raw.get("schema") != AI_BENCHMARK_SCORECARD_SCHEMA):
        raise ValueError(f"scorecard schema must be {AI_BENCHMARK_SCORECARD_SCHEMA}")
    rubric = raw.get("rubric_version")
    reviewer = raw.get("reviewer")
    scores = raw.get("scores")
    manifest_digest = raw.get("manifest_digest")
    rubric_body = raw.get("rubric")
    rubric_digest = hashlib.sha256(json.dumps(
        rubric_body, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest() if isinstance(rubric_body, dict) else None
    if (rubric != W0B_RUBRIC_VERSION or rubric_body != W0B_FROZEN_RUBRIC
            or rubric_digest != W0B_RUBRIC_DIGEST
            or not isinstance(manifest_digest, str) or not _HEX64_RE.fullmatch(manifest_digest)
            or not isinstance(reviewer, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}", reviewer)):
        raise ValueError("scorecard must bind the frozen W0-B rubric and reviewer")
    if not isinstance(scores, list) or not scores:
        raise ValueError("scorecard requires non-empty scores")
    result: dict[tuple[str, int], dict[str, Any]] = {}
    for item in scores:
        if not isinstance(item, dict):
            raise ValueError("scorecard scores must be objects")
        prompt_id = item.get("prompt_id")
        run = item.get("run")
        if (not isinstance(prompt_id, str) or prompt_id not in dict(W0B_CORPUS_V1)
                or not isinstance(run, int)
                or isinstance(run, bool) or run < 1):
            raise ValueError("scorecard score requires prompt_id and positive run")
        key = (prompt_id, run)
        if key in result:
            raise ValueError(f"duplicate scorecard row: {prompt_id}/{run}")
        unknown = set(item) - {"prompt_id", "run", *_SCORE_FIELDS}
        if unknown or any(field not in item for field in _SCORE_FIELDS):
            raise ValueError(f"scorecard fields invalid for {prompt_id}/{run}")
        scored: dict[str, Any] = {
            "reviewer": reviewer,
            "rubric_version": rubric,
            "rubric_digest": W0B_RUBRIC_DIGEST,
            "manifest_digest": manifest_digest,
        }
        for field in _SCORE_FIELDS:
            value = item[field]
            if field == "unsupported_claim_count":
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    raise ValueError(f"{field} must be a non-negative integer")
            elif (not isinstance(value, (int, float, bool)) or isinstance(value, str)
                  or not math.isfinite(float(value)) or value not in (0, 1)):
                raise ValueError(f"{field} must be a finite binary 0/1 score")
            scored[field] = value
        result[key] = scored
    return result


def apply_scorecard(receipts: list[dict], scores: dict[tuple[str, int], dict[str, Any]]) -> list[dict]:
    """Bind every receipt one-to-one to a frozen manual score; fail on omissions."""
    identities: list[tuple[str, int]] = []
    for row in receipts:
        if (not isinstance(row, dict) or not isinstance(row.get("prompt_id"), str)
                or not isinstance(row.get("run"), int) or isinstance(row.get("run"), bool)
                or row["run"] < 1):
            raise ValueError("receipt prompt_id/run identity is invalid")
        identities.append((row["prompt_id"], row["run"]))
    observed = set(identities)
    if len(observed) != len(receipts):
        raise ValueError("duplicate receipt prompt_id/run rows are forbidden")
    runs = {run for _, run in observed}
    if runs != set(range(1, max(runs, default=0) + 1)):
        raise ValueError("receipt run identities must be contiguous from 1")
    expected = {(prompt_id, run) for run in runs for prompt_id, _ in W0B_CORPUS_V1}
    if observed != expected:
        raise ValueError("receipts must contain the complete W0-B corpus for every run")
    for run in runs:
        by_prompt = {row["prompt_id"]: row for row in receipts if row["run"] == run}
        ordered = [by_prompt[prompt_id] for prompt_id, _ in W0B_CORPUS_V1]
        computed_digest = _corpus_manifest_digest(ordered)
        if any(row.get("manifest_digest") != computed_digest for row in ordered):
            raise ValueError("receipt manifest digest does not bind its prompt/context corpus")
    if observed != set(scores):
        raise ValueError("scorecard keys must exactly match receipt prompt_id/run keys")
    receipt_digests = {row.get("manifest_digest") for row in receipts}
    score_digests = {score.get("manifest_digest") for score in scores.values()}
    if len(receipt_digests) != 1 or receipt_digests != score_digests:
        raise ValueError("scorecard manifest digest must match every receipt")
    invocation_keys = (
        "system", "environment", "base_url", "deployed_commit", "deployed_checkout",
        "health_error", "lane", "label", "cache_label", "cache_basis", "reviewer",
        "rubric_version", "rubric_digest", "manifest_digest",
    )
    invocation_fingerprints = {
        tuple(row.get(key) for key in invocation_keys) for row in receipts
    }
    if len(invocation_fingerprints) != 1:
        raise ValueError("receipts must share one immutable benchmark invocation identity")
    receipt_reviewers = {row.get("reviewer") for row in receipts}
    score_reviewers = {score.get("reviewer") for score in scores.values()}
    if len(receipt_reviewers) != 1 or receipt_reviewers != score_reviewers:
        raise ValueError("scorecard reviewer must match the receipt reviewer")
    return [{
        **row,
        **{
            field: scores[(str(row["prompt_id"]), int(row["run"]))][field]
            for field in _SCORE_FIELDS
        },
    } for row in receipts]


def score_receipt_file(receipt_path: str, scorecard_path: str, out_path: str) -> int:
    """Score an already-recorded immutable run without replaying production traffic."""
    try:
        source = _assert_private_output_path(receipt_path, kind="receipt")
        target = _assert_private_output_path(out_path, kind="scored receipt")
        rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()
                if line.strip()]
        if not rows:
            raise ValueError("score input must contain ai_benchmark_receipt.v1 rows")
        rows = [_validate_receipt_row(row) for row in rows]
        scored = apply_scorecard(rows, load_scorecard(scorecard_path))
        append_jsonl(target, scored, exclusive=True)
    except (OSError, TypeError, ValueError) as exc:
        print(f"private benchmark scoring failed: {type(exc).__name__}", file=sys.stderr)
        return 2
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="brain_latency_bench",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--base-url", default="http://127.0.0.1:8000",
                   help="gateway origin (default: %(default)s)")
    p.add_argument("--cookie", default="",
                   help="mm_aid cookie value, sent as `Cookie: mm_aid=<value>`. The brain "
                        "routes authenticate as a verified user (--bearer) or, when guest "
                        "access is enabled, as a guest keyed on this cookie. WITHOUT either, "
                        "the request is refused 401: an anonymous probe has no principal to "
                        "meter, and an unmeterable turn is not the turn users get.")
    p.add_argument("--bearer", default="",
                   help="Supabase access token for a SIGNED-IN probe (the docket's §6.7 A/B "
                        "was authenticated). Wins over --cookie when both are given.")
    p.add_argument("--runs", type=int, default=1, help="repeats per prompt (default: 1)")
    p.add_argument("--label", default="cold", choices=("cold", "warm"),
                   help="tag for the run, recorded in --out rows (default: %(default)s). "
                        "'cold' = first probe after a restart (empty digest/packet caches); "
                        "'warm' = caches primed by a prior run.")
    p.add_argument("--lane", default="fast", choices=("fast", "pro"),
                   help="brain lane (default: %(default)s)")
    p.add_argument("--page", default="",
                   help="context.page to send, e.g. 'terminal' (default: none)")
    p.add_argument("--symbol", default="",
                   help="context.symbol chip to send (default: none)")
    p.add_argument("--only", default="", metavar="LABEL",
                   help="run a single probe by label: " + ", ".join(n for n, _ in DOCKET_PROMPTS))
    p.add_argument("--timeout", type=float, default=180.0,
                   help="per-probe socket timeout in seconds (default: %(default)s)")
    p.add_argument("--out", default="",
                   help="write one JSON object per probe to this path (JSONL). W0-B manifest "
                        "runs require a new path outside this repository and never append.")
    p.add_argument("--manifest", default="", metavar="PATH",
                   help="private ai_benchmark_prompt_manifest.v1; supplies W0-B prompt text, "
                        "verified hashes, and context metadata")
    p.add_argument("--expected-manifest-digest", default="", metavar="SHA256",
                   help="canonical digest pinned independently of the private manifest; required "
                        "for every W0-B manifest run")
    p.add_argument("--health-url", default="", metavar="URL",
                   help="public health URL that identifies the running process commit and the "
                        "possibly-later checkout; required for production acceptance")
    p.add_argument("--expected-deployed-commit", default="", metavar="SHA",
                   help="accepted candidate SHA; production health commit must prefix-match it")
    p.add_argument("--expected-deployed-checkout", default="", metavar="SHA",
                   help="optional expected checkout SHA; use when the deployment checkout is "
                        "required to remain exact during the run")
    p.add_argument("--system", default="mastermind",
                   help="receipt system name (default: %(default)s)")
    p.add_argument("--environment", default="unspecified",
                   help="receipt environment, e.g. production (default: %(default)s)")
    p.add_argument("--cache-basis", default="caller_label",
                   help="how the cold/warm label was established (default: %(default)s)")
    p.add_argument("--reviewer", default="", help="private receipt reviewer identifier")
    p.add_argument("--rubric-version", default="",
                   help=f"frozen scoring rubric (W0-B requires {W0B_RUBRIC_VERSION})")
    p.add_argument("--raw-answer-out", default="", metavar="PATH",
                   help="opt-in private raw-answer JSONL; path must be outside this repository")
    p.add_argument("--score-receipt", default="", metavar="PATH",
                   help="score an existing private receipt instead of running probes")
    p.add_argument("--scorecard", default="", metavar="PATH",
                   help="private ai_benchmark_scorecard.v1 for --score-receipt")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.score_receipt:
        if not args.scorecard or not args.out:
            print("--score-receipt requires --scorecard and --out", file=sys.stderr)
            return 2
        return score_receipt_file(args.score_receipt, args.scorecard, args.out)
    if args.runs < 1:
        print("--runs must be a positive integer", file=sys.stderr)
        return 2
    production = args.environment.strip().lower().startswith("production")
    token_re = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
    if any(not token_re.fullmatch(value) for value in (
            args.system, args.environment, args.cache_basis)):
        print("benchmark receipt identifiers must be bounded public tokens", file=sys.stderr)
        return 2
    if args.manifest and args.only:
        print("W0-B manifest runs must execute the complete corpus; use legacy mode for --only",
              file=sys.stderr)
        return 2
    if args.manifest and (
            not args.out or not token_re.fullmatch(args.reviewer)
            or args.rubric_version != W0B_RUBRIC_VERSION
            or not re.fullmatch(r"[0-9a-f]{64}", args.expected_manifest_digest)):
        print("W0-B manifest runs require --out, a reviewer token, the frozen rubric, and "
              "an independently pinned manifest digest",
              file=sys.stderr)
        return 2
    if production and (
            not args.manifest or not args.out or not args.health_url
            or not args.expected_deployed_commit or not (args.cookie or args.bearer)
            or args.cache_basis == "caller_label"):
        print("production acceptance requires the complete W0-B manifest, private output, "
              "health identity, accepted commit, authenticated principal, and observed cache basis",
              file=sys.stderr)
        return 2
    if production and (
            not re.fullmatch(r"[0-9a-fA-F]{7,64}", args.expected_deployed_commit)
            or (args.expected_deployed_checkout and not re.fullmatch(
                r"[0-9a-fA-F]{7,64}", args.expected_deployed_checkout))):
        print("production expected deployment identities must be Git SHAs", file=sys.stderr)
        return 2
    try:
        if args.manifest:
            _manifest_version, manifest_digest, specs = load_private_manifest(args.manifest)
        else:
            _manifest_version = W0B_CORPUS_VERSION
            specs = _legacy_prompt_specs(page=args.page, symbol=args.symbol)
            manifest_digest = specs[0]["manifest_digest"]
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.manifest and manifest_digest != args.expected_manifest_digest:
        print("private manifest digest differs from the independently pinned corpus",
              file=sys.stderr)
        return 2
    selected = [s for s in specs if not args.only
                or args.only in (s["label"], s["prompt_id"])]
    if not selected:
        print(f"no probe named {args.only!r}; known: "
              + ", ".join(s["label"] for s in specs), file=sys.stderr)
        return 2
    raw_path: Path | None = None
    if args.raw_answer_out:
        try:
            raw_path = _assert_private_output_path(args.raw_answer_out)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if os.path.lexists(raw_path):
            print("private raw-answer output must be a new path", file=sys.stderr)
            return 2
    receipt_path: Path | str = args.out
    if args.manifest:
        try:
            receipt_path = _assert_private_output_path(args.out, kind="receipt")
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if os.path.lexists(receipt_path):
            print("private receipt output must be a new path", file=sys.stderr)
            return 2
    if not (args.cookie or args.bearer):
        print("note: no --cookie / --bearer given; expect HTTP 401 unless guest access "
              "is enabled and the server does not require the mm_aid cookie.",
              file=sys.stderr)

    health = capture_health(args.health_url, timeout=args.timeout) if args.health_url else {
        "commit": None, "checkout": None, "error": None,
    }
    if production and (
            health.get("error") is not None or health.get("commit") is None
            or health.get("checkout") is None):
        print("production health identity is unavailable; no probes were sent", file=sys.stderr)
        return 2
    if production and not _sha_prefix_matches(
            health.get("commit"), args.expected_deployed_commit):
        print("production process commit does not match the accepted candidate; no probes were sent",
              file=sys.stderr)
        return 2
    if production and args.expected_deployed_checkout and not _sha_prefix_matches(
            health.get("checkout"), args.expected_deployed_checkout):
        print("production checkout does not match the required checkout; no probes were sent",
              file=sys.stderr)
        return 2
    rows: list[dict] = []
    receipts: list[dict] = []
    raw_answers: list[dict] = []
    for run in range(1, args.runs + 1):
        for spec in selected:
            row = probe(args.base_url, spec["message"], cookie=args.cookie, bearer=args.bearer,
                        lane=args.lane, context=spec["ambient_context"], timeout=args.timeout,
                        capture_answer=raw_path is not None)
            raw_answer = row.pop("_raw_answer", None)
            row.update({"probe": spec["label"], "run": run, "label": args.label,
                        "lane": args.lane, "base_url": _safe_base_url(args.base_url),
                        "ts": _utc_now()})
            rows.append(row)
            receipt = build_receipt_row(
                row, spec, run=run, lane=args.lane, system=args.system,
                environment=args.environment, cache_label=args.label,
                cache_basis=args.cache_basis, health=health, reviewer=args.reviewer,
                rubric_version=args.rubric_version,
            )
            if args.manifest:
                try:
                    _validate_receipt_row(receipt)
                except (TypeError, ValueError):
                    print("benchmark receipt validation failed", file=sys.stderr)
                    return 2
            receipts.append(receipt)
            if raw_path is not None:
                raw_answers.append({"prompt_id": spec["prompt_id"], "run": run,
                                    "answer": raw_answer or ""})

    if production:
        post_health = capture_health(args.health_url, timeout=args.timeout)
        if (post_health.get("error") is not None or post_health.get("commit") is None
                or post_health.get("checkout") is None
                or not _sha_prefix_matches(post_health.get("commit"), args.expected_deployed_commit)
                or not _sha_prefix_matches(post_health.get("commit"), health.get("commit"))):
            print("production process identity changed during the corpus; no acceptance output written",
                  file=sys.stderr)
            return 2
        if not _sha_prefix_matches(post_health.get("checkout"), health.get("checkout")):
            print("production deployment checkout changed during the corpus; "
                  "no acceptance output written", file=sys.stderr)
            return 2
        if args.expected_deployed_checkout and not _sha_prefix_matches(
                post_health.get("checkout"), args.expected_deployed_checkout):
            print("production checkout changed during the exact-checkout corpus; "
                  "no acceptance output written", file=sys.stderr)
            return 2

    print_table(rows)
    print_medians(rows)
    print_p95(rows)

    if args.out:
        try:
            append_jsonl(receipt_path, receipts, exclusive=bool(args.manifest))
        except OSError:
            print("private benchmark receipt write failed", file=sys.stderr)
            return 1
    if raw_path is not None:
        try:
            append_jsonl(raw_path, raw_answers, exclusive=True)
        except OSError:
            print("private benchmark raw-answer write failed", file=sys.stderr)
            return 1
    precedence_failed = any(receipt.get("precedence_match") is False for receipt in receipts)
    return 1 if any(r.get("error") for r in rows) or precedence_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
