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
_NATIVE_UNITS = frozenset({
    "currency", "percent", "stage_code", "weeks", "percentile", "iso_date",
    "entity_refs",
})
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
    "prompt_id", "prompt_version", "prompt_class", "prompt_text_hash",
    "explicit_context", "ambient_context", "expected_effective_entity",
    "expected_precedence_reason", "actual_effective_entity",
    "actual_precedence_reason", "ambient_used", "precedence_match",
    "native_fact_receipt", "cache_label", "cache_basis", "route",
    "headers_ms", "first_status_ms", "ttfv_ms", "done_ms", "n_tool_events",
    "server_tool_count", "server_tool_durations_ms", "context_bytes", "output_bytes",
    "field_correctness", "numeric_correctness", "source_span_correctness",
    "source_as_of_correctness",
    "unsupported_claim_count", "missingness_honesty", "degraded", "error",
    "reviewer", "rubric_version", "recorded_at",
})


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json_bytes(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":")).encode("utf-8"))


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


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
    """Keep the legacy base-url field while stripping query credentials and userinfo."""
    parts = urlsplit(value)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


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
    return specs


def load_private_manifest(path: str) -> tuple[str, list[dict]]:
    """Load a text-bearing W0-B manifest kept outside this repository."""
    try:
        manifest_path = _assert_private_output_path(path, kind="manifest")
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot load private manifest: {type(exc).__name__}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != W0B_MANIFEST_SCHEMA:
        raise ValueError(f"manifest schema must be {W0B_MANIFEST_SCHEMA}")
    version = raw.get("version")
    prompts = raw.get("prompts")
    if not isinstance(version, str) or not version or not isinstance(prompts, list) or not prompts:
        raise ValueError("manifest requires non-empty version and prompts")

    seen: set[str] = set()
    specs: list[dict] = []
    allowed = dict(W0B_CORPUS_V1)
    for item in prompts:
        if not isinstance(item, dict):
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
                or not isinstance(expected_reason, str) or not expected_reason):
            raise ValueError("context-collision requires expected entity and precedence reason")
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
    return version, specs


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

    def safe_industry_id(raw: Any) -> str:
        if (not isinstance(raw, str) or not raw or len(raw) > 160
                or _PATH_LIKE_RE.search(raw) or any(ord(char) < 32 for char in raw)
                or "/" in raw or "\\" in raw):
            raise ValueError("native proof industry identity is invalid")
        return raw

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
        if canonical_raw is not None:
            if not isinstance(canonical_raw, dict) or canonical_raw.get("type") != "security":
                raise ValueError("native canonical entity is invalid")
            canonical = {
                "type": "security",
                "id": safe_token(canonical_raw.get("id"), _SECURITY_ID_RE),
            }
            if digest is None:
                raise ValueError("native canonical proof lacks registry digest")

        raw_facts = value.get("facts") or []
        if not isinstance(raw_facts, list):
            raise ValueError("native facts proof is invalid")
        facts = []
        for fact in raw_facts:
            if not isinstance(fact, dict):
                raise ValueError("native fact proof is invalid")
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
                "field_id": enum(fact.get("field_id"), _NATIVE_FIELD_IDS),
                "fact_fingerprint": hex64(fact.get("fact_fingerprint")),
                "status": enum(fact.get("status"), _NATIVE_STATUSES),
                "reason_code": enum(
                    fact.get("reason_code"), _NATIVE_REASON_CODES, optional=True
                ),
                "unit": enum(fact.get("unit"), _NATIVE_UNITS, optional=True),
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
                    or rank_failure is not None):
                raise ValueError("native failure receipt carries successful proof")
        else:
            if digest is None or canonical is None or not clauses:
                raise ValueError("native success receipt lacks typed proof")
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
            "facts": facts,
            "clauses": clauses,
            "relationship": relationship,
            "rank_resolution_failure": rank_failure,
            "failure": failure,
        }
    except ValueError:
        return None


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
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                durations.append(int(value))
    return count, durations


def _safe_server_timing(server_latency: Any) -> dict | None:
    """Project untrusted SSE timing onto the receipt's timing-only contract."""
    if not isinstance(server_latency, dict):
        return None
    def numeric(value: Any) -> int | float | None:
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    route = server_latency.get("route")
    out: dict[str, Any] = {
        "route": route if route in {"instant", "instant/native-fact", "deep"} else None,
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
            if isinstance(tool, dict) and isinstance(tool.get("ms"), int):
                tools.append({"ms": tool["ms"]})
        out["rounds"].append({
            "model_ms": round_.get("model_ms") if isinstance(round_.get("model_ms"), int) else None,
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
        "health_error": health.get("error"),
        "prompt_id": spec["prompt_id"],
        "prompt_version": spec["prompt_version"],
        "prompt_class": spec["prompt_class"],
        "prompt_text_hash": spec["prompt_text_hash"],
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
        "error": row.get("error"),
        "reviewer": reviewer or None,
        "rubric_version": rubric_version or None,
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


def load_scorecard(path: str) -> dict[tuple[str, int], dict[str, Any]]:
    """Load a private, frozen manual adjudication keyed by prompt ID and run."""
    score_path = _assert_private_output_path(path, kind="scorecard")
    try:
        raw = json.loads(score_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot load private scorecard: {type(exc).__name__}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != AI_BENCHMARK_SCORECARD_SCHEMA:
        raise ValueError(f"scorecard schema must be {AI_BENCHMARK_SCORECARD_SCHEMA}")
    rubric = raw.get("rubric_version")
    reviewer = raw.get("reviewer")
    scores = raw.get("scores")
    if not isinstance(rubric, str) or not rubric or not isinstance(reviewer, str) or not reviewer:
        raise ValueError("scorecard requires rubric_version and reviewer")
    if not isinstance(scores, list) or not scores:
        raise ValueError("scorecard requires non-empty scores")
    result: dict[tuple[str, int], dict[str, Any]] = {}
    for item in scores:
        if not isinstance(item, dict):
            raise ValueError("scorecard scores must be objects")
        prompt_id = item.get("prompt_id")
        run = item.get("run")
        if not isinstance(prompt_id, str) or not prompt_id or not isinstance(run, int) or run < 1:
            raise ValueError("scorecard score requires prompt_id and positive run")
        key = (prompt_id, run)
        if key in result:
            raise ValueError(f"duplicate scorecard row: {prompt_id}/{run}")
        unknown = set(item) - {"prompt_id", "run", *_SCORE_FIELDS}
        if unknown or any(field not in item for field in _SCORE_FIELDS):
            raise ValueError(f"scorecard fields invalid for {prompt_id}/{run}")
        scored: dict[str, Any] = {"reviewer": reviewer, "rubric_version": rubric}
        for field in _SCORE_FIELDS:
            value = item[field]
            if field == "unsupported_claim_count":
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    raise ValueError(f"{field} must be a non-negative integer")
            elif not isinstance(value, (int, float, bool)) or isinstance(value, str):
                raise ValueError(f"{field} must be a numeric or boolean score")
            scored[field] = value
        result[key] = scored
    return result


def apply_scorecard(receipts: list[dict], scores: dict[tuple[str, int], dict[str, Any]]) -> list[dict]:
    """Bind every receipt one-to-one to a frozen manual score; fail on omissions."""
    observed = {(str(row.get("prompt_id") or ""), int(row.get("run") or 0)) for row in receipts}
    if observed != set(scores):
        raise ValueError("scorecard keys must exactly match receipt prompt_id/run keys")
    return [{**row, **scores[(str(row["prompt_id"]), int(row["run"]))]}
            for row in receipts]


def score_receipt_file(receipt_path: str, scorecard_path: str, out_path: str) -> int:
    """Score an already-recorded immutable run without replaying production traffic."""
    try:
        source = _assert_private_output_path(receipt_path, kind="receipt")
        target = _assert_private_output_path(out_path, kind="scored receipt")
        rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()
                if line.strip()]
        if not rows or any(not isinstance(row, dict)
                           or row.get("schema") != AI_BENCHMARK_RECEIPT_SCHEMA for row in rows):
            raise ValueError("score input must contain ai_benchmark_receipt.v1 rows")
        scored = apply_scorecard(rows, load_scorecard(scorecard_path))
        append_jsonl(target, scored, exclusive=True)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
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
                   help="append one JSON object per probe to this path (JSONL). W0-B manifest "
                        "runs require a path outside this repository.")
    p.add_argument("--manifest", default="", metavar="PATH",
                   help="private ai_benchmark_prompt_manifest.v1; supplies W0-B prompt text, "
                        "verified hashes, and context metadata")
    p.add_argument("--health-url", default="", metavar="URL",
                   help="public health URL to record deployment commit/checkout; omitted keeps "
                        "those receipt fields null")
    p.add_argument("--system", default="mastermind",
                   help="receipt system name (default: %(default)s)")
    p.add_argument("--environment", default="unspecified",
                   help="receipt environment, e.g. production (default: %(default)s)")
    p.add_argument("--cache-basis", default="caller_label",
                   help="how the cold/warm label was established (default: %(default)s)")
    p.add_argument("--reviewer", default="", help="private receipt reviewer identifier")
    p.add_argument("--rubric-version", default="", help="frozen private scoring-rubric version")
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
    try:
        _manifest_version, specs = (load_private_manifest(args.manifest) if args.manifest
                                    else (W0B_CORPUS_VERSION,
                                          _legacy_prompt_specs(page=args.page, symbol=args.symbol)))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
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
    if args.manifest and args.out:
        try:
            _assert_private_output_path(args.out, kind="receipt")
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    if not (args.cookie or args.bearer):
        print("note: no --cookie / --bearer given; expect HTTP 401 unless guest access "
              "is enabled and the server does not require the mm_aid cookie.",
              file=sys.stderr)

    health = capture_health(args.health_url, timeout=args.timeout) if args.health_url else {
        "commit": None, "checkout": None, "error": None,
    }
    rows: list[dict] = []
    receipts: list[dict] = []
    raw_answers: list[dict] = []
    for run in range(1, max(1, args.runs) + 1):
        for spec in selected:
            row = probe(args.base_url, spec["message"], cookie=args.cookie, bearer=args.bearer,
                        lane=args.lane, context=spec["ambient_context"], timeout=args.timeout,
                        capture_answer=raw_path is not None)
            raw_answer = row.pop("_raw_answer", None)
            row.update({"probe": spec["label"], "run": run, "label": args.label,
                        "lane": args.lane, "base_url": _safe_base_url(args.base_url),
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
            rows.append(row)
            receipts.append(build_receipt_row(
                row, spec, run=run, lane=args.lane, system=args.system,
                environment=args.environment, cache_label=args.label,
                cache_basis=args.cache_basis, health=health, reviewer=args.reviewer,
                rubric_version=args.rubric_version,
            ))
            if raw_path is not None:
                raw_answers.append({"prompt_id": spec["prompt_id"], "run": run,
                                    "answer": raw_answer or ""})

    print_table(rows)
    print_medians(rows)
    print_p95(rows)

    if args.out:
        try:
            append_jsonl(args.out, receipts)
        except OSError as exc:
            print(f"could not write {args.out}: {exc}", file=sys.stderr)
            return 1
    if raw_path is not None:
        try:
            append_jsonl(raw_path, raw_answers)
        except OSError as exc:
            print(f"could not write raw answers: {exc}", file=sys.stderr)
            return 1
    precedence_failed = any(receipt.get("precedence_match") is False for receipt in receipts)
    return 1 if any(r.get("error") for r in rows) or precedence_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
