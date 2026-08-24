"""Bounded deterministic W1-B native-fact planning and rendering.

This module deliberately sits *above* the frozen W1-A read layer.  It has no
registry, value store, identity catalogue, rights policy, cache, model call, or
owner formula of its own.  It only translates a small, high-precision factual
grammar into W1-A requests and relays subscriber-projected envelopes.

The Brain gateway owns transport, quotas, SSE, persistence, and the decision to
fall through to the deep route.  This module is intentionally usable without a
gateway import so its authority boundary stays easy to audit.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
import re
from time import perf_counter
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
NATIVE_FACT_ROUTE = "instant/native-fact"
NATIVE_FACT_RECEIPT_SCHEMA = "brain.native_fact_receipt.v1"
NATIVE_FACT_PLANNER_VERSION = "w1b.native_fact_planner.v1"

# These are the entire frozen W1-A V1 surface, not an independently maintained
# product schema.  The exact IDs are kept here solely as the grammar allowlist.
ALLOWED_FIELD_IDS = frozenset(
    {
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
    }
)

_ANALYTICAL = re.compile(
    r"\b(?:why|explain|outlook|forecast|predict(?:ion)?|target|buy|sell|should|"
    r"advice|compare|comparison|versus|vs\.?|research|analyse|analyze|thesis|"
    r"recommend(?:ation)?|valuation)\b",
    re.IGNORECASE,
)
_HISTORICAL = re.compile(
    r"\b(?:histor(?:y|ical)|yesterday|ago|previous|prior|during|since|"
    r"last\s+(?:week|month|year|quarter)|in\s+\d{4}|as\s+of|on\s+"
    r"(?:\d{4}-\d{2}-\d{2}|\w+\s+\d{1,2})|at\s+the\s+(?:end|start)\s+of)\b",
    re.IGNORECASE,
)
# Qualified non-US/A-share symbols are intentionally left to the legacy quote
# route.  W1-A's frozen security universe is US equity only.
_NON_US_QUALIFIED = re.compile(
    r"(?:\b\d{4,5}\.HK\b|\b(?:SSE|SZSE):\d{6}\b|\b\d{6}\.(?:SS|SZ)\b)",
    re.IGNORECASE,
)

_SYMBOL_TOKEN = re.compile(r"(?<![A-Za-z0-9.])\$?([A-Za-z]{1,5})(?![A-Za-z0-9.])")

# Lexical filter only: identity is still admitted exclusively by W1-A.
_NON_SYMBOL_WORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "buy", "current", "date",
        "direct", "earnings", "eps", "for", "give", "growth", "how", "in", "industry",
        "asof", "cite", "cited", "citation", "each", "exact", "field", "fields",
        "is", "it", "its", "latest", "local", "me", "member", "memberships", "month", "months",
        "next", "of", "percentile", "price", "quote", "rank", "return", "returns", "revenue",
        "one", "over", "please", "report", "reported", "rs", "sentence", "show", "source",
        "stage", "strength", "tell", "the", "theme", "themes", "trading", "what", "weeks",
        "with", "within", "year", "years", "you", "your", "why", "target", "forecast",
        "compare", "versus", "today", "now", "much", "relative", "sales",
    }
)

_REQUEST_TOKEN = re.compile(r"[A-Za-z]+|\d+")
_REQUEST_GRAMMAR_WORDS = _NON_SYMBOL_WORDS | frozenset(
    {
        "fact", "facts", "m", "mo", "s", "stock", "ticker", "value", "values",
    }
)
# Upper-case tokens that are themselves consumed by the registered fact
# grammar do not look like suppressed identities. Other reserved upper-case
# tokens are ambiguous: they may be real tickers (IT, ARE, A, ...), so ambient
# context must not win merely because the lexical filter recognized a word.
_FIELD_GRAMMAR_WORDS = frozenset({
    "current", "date", "direct", "earnings", "eps", "growth", "industry",
    "latest", "local", "member", "memberships", "month", "months", "next",
    "percentile", "price", "quote", "rank", "relative", "report", "return",
    "returns", "revenue", "rs", "sales", "stage", "strength", "theme", "themes",
    "trading", "weeks", "within",
})
_UNSUPPORTED_REQUEST_WORDS = frozenset({
    "beta", "float", "high", "open", "pe", "volume", "yield",
})


def _has_unsupported_residue(message: str, explicit_symbols: tuple[str, ...]) -> bool:
    """Fail closed when a native clause is mixed with an unregistered request.

    The allowlist is intentionally lexical and small. W1-B would rather send an
    unfamiliar but factual-looking phrase to the deep lane than silently drop a
    second requested field (for example, answering price while ignoring volume).
    """
    symbols = {symbol.lower() for symbol in explicit_symbols}
    for token in _REQUEST_TOKEN.findall(message):
        lowered = token.lower()
        if lowered in symbols or lowered in _REQUEST_GRAMMAR_WORDS:
            continue
        if lowered in {"1", "3", "12"}:
            continue
        return True
    return False


@dataclass(frozen=True, slots=True)
class NativeFactPlan:
    """A bounded factual plan, or nothing when the request must go deep."""

    symbol: str
    field_ids: tuple[str, ...]
    explicit_entity: bool
    effective_context_reason: str
    ambient_symbol: str | None = None


@dataclass(frozen=True, slots=True)
class NativeFactExecution:
    """Deterministic answer plus its subscriber-safe field receipt."""

    answer: str
    receipt: dict[str, Any]
    clauses: tuple[dict[str, Any], ...]


def _symbol_candidates(message: str) -> tuple[tuple[tuple[str, int, int], ...], bool]:
    candidates: list[tuple[str, int, int]] = []
    suppressed_uppercase_ambiguity = False
    for match in _SYMBOL_TOKEN.finditer(message):
        token = match.group(1)
        # In ``AAPL's`` the trailing possessive is not a one-letter ticker.
        if match.start(1) > 0 and message[match.start(1) - 1] in "'’":
            continue
        raw = match.group(0)
        before = message[:match.start(0)].rstrip()
        after = message[match.end(0):]
        possessive = bool(re.match(r"^[\'’]s\b", after, re.IGNORECASE))
        suffix_slot = bool(re.match(
            r"^\s+(?:price|quote|stage|weeks?\s+(?:in|of)|1\s*(?:-\s*)?(?:m|mo|month)|"
            r"3\s*(?:-\s*)?(?:m|mo|month)|12\s*(?:-\s*)?(?:m|mo|month)|industry\s+rank|"
            r"within[-\s]+industry|member\s+rs|next\s+earnings|latest\s+(?:eps|revenue|sales)|"
            r"direct\s+(?:local\s+)?theme|trading\s+(?:at|now))",
            after,
            re.IGNORECASE,
        ))
        post_field_slot = bool(re.search(
            r"\b(?:price|quote|stage|industry\s+rank|next\s+earnings|"
            r"latest\s+(?:eps|revenue|sales)|direct\s+(?:local\s+)?theme)\s+"
            r"(?:of|for)\s*$",
            before,
            re.IGNORECASE,
        ))
        natural_price_prefix_slot = bool(re.search(
            r"\b(?:what(?:'s|\s+is)|how\s+much\s+is)\s*$",
            before,
            re.IGNORECASE,
        ))
        proven_slot = possessive or suffix_slot or post_field_slot or natural_price_prefix_slot
        # Dollar syntax is an explicit entity assertion regardless of whether
        # the letters also form request grammar; W1-A still proves identity.
        if raw.startswith("$"):
            candidates.append((token.upper(), match.start(1), match.end(1)))
            continue
        # In "What's PRICE?" / "How much is STAGE?" the token is the
        # registered field phrase itself, not an entity merely because it
        # follows a natural request prefix. Consume that grammar before the
        # ticker-slot exception. Dollar syntax above remains authoritative.
        if (natural_price_prefix_slot and not suffix_slot
                and token.lower() in _FIELD_GRAMMAR_WORDS):
            continue
        # Native routing is precision-first. A bare lower-case word ("beta")
        # or an upper-case unsupported field after "and" must never steal an
        # ambient ticker. Conversely, a genuinely explicit ticker can collide
        # lexically with ordinary grammar (IT, ARE, AS, AT, BE, AN, ME, A).
        # Once an upper-case token occupies an unambiguous ticker slot it must
        # go to W1-A identity proof, never disappear and let ambient context
        # win. Unsupported/reserved words are filtered only outside that slot.
        lowered = token.lower()
        # Consume connectors by their position between already-mentioned and
        # following registered fields, never by an identity-denial vocabulary.
        # The same token at the actual entity slot (for example, FOR price or
        # NOW price) must still go to W1-A identity proof.
        connector_between_fields = (
            lowered in {"and", "with"}
            and bool(re.search(
                r"\b(?:price|quote|stage|return|returns|earnings|growth|rank|"
                r"percentile|rs|strength|theme|themes|memberships)\b",
                before,
                re.IGNORECASE,
            ))
            and proven_slot
        )
        if connector_between_fields:
            continue
        # All-caps request prose such as THE/WHAT/SHOW STAGE and GIVE ME PRICE
        # is ambiguous with ticker syntax. Veto native routing instead of
        # silently selecting ambient context or maintaining a ticker denylist.
        request_prefix_ambiguity = (
            (lowered in {"the", "what", "show"} and not before.strip())
            or (lowered == "the" and natural_price_prefix_slot)
            or (lowered == "me" and bool(re.search(r"\b(?:give|tell)\s*$", before, re.IGNORECASE)))
        )
        if request_prefix_ambiguity:
            suppressed_uppercase_ambiguity = suppressed_uppercase_ambiguity or token.isupper()
            continue
        if (
            lowered in _NON_SYMBOL_WORDS or lowered in _UNSUPPORTED_REQUEST_WORDS
        ) and not (token.isupper() and proven_slot):
            if token.isupper() and lowered not in _FIELD_GRAMMAR_WORDS:
                suppressed_uppercase_ambiguity = True
            continue
        # Explicit identities require $ syntax or an upper-case token in an
        # unambiguous ticker slot; W1-A remains the final identity proof.
        if not token.isupper() or not proven_slot:
            continue
        candidates.append((token.upper(), match.start(1), match.end(1)))
    return tuple(candidates), suppressed_uppercase_ambiguity


def _without_explicit_entity_spans(
    message: str,
    candidates: tuple[tuple[str, int, int], ...],
    symbol: str,
) -> str:
    """Mask a selected entity token before registered-field extraction.

    A spelling can lawfully be both a current ticker and a field word. Once an
    occurrence wins an explicit ticker slot (``STAGE trading at``), that same
    occurrence cannot independently request the Stage field. Spaces preserve
    every remaining field's source order without introducing new grammar.
    """
    masked = list(message)
    for candidate, start, end in candidates:
        if candidate == symbol:
            masked[start:end] = " " * (end - start)
    return "".join(masked)


def _context_symbol(context: Mapping[str, Any] | None) -> str | None:
    if not isinstance(context, Mapping):
        return None
    candidate = context.get("symbol")
    if not isinstance(candidate, str):
        return None
    symbol = candidate.strip().upper()
    if not re.fullmatch(r"[A-Z]{1,5}", symbol):
        return None
    return symbol


def _field_hits(message: str) -> list[tuple[int, str]] | None:
    """Return exact W1-A IDs in user order, or None for semantic ambiguity."""
    lower = message.lower()
    hits: list[tuple[int, str]] = []

    def add(pattern: str, field_id: str, *, flags: int = re.IGNORECASE) -> None:
        match = re.search(pattern, message, flags)
        if match is not None:
            hits.append((match.start(), field_id))

    # Never infer an RS horizon from a return horizon.  The member fact needs
    # explicit within-industry/member semantics, and a bare "RS" is a deep
    # fallback by design.
    member_rs = re.search(
        r"\b(?:within[-\s]+industry|industry[-\s]+member|member[-\s]+within[-\s]+industry)"
        r"(?:[-\s]+(?:member\s+)?)?(?:rs|relative\s+strength|strength)(?:\s+percentile)?\b"
        r"|\bmember\s+rs(?:\s+percentile)?\b",
        message,
        re.IGNORECASE,
    )
    if re.search(r"\brs\b", message, re.IGNORECASE) and member_rs is None:
        return None
    if re.search(r"\brelative\s+strength\b", message, re.IGNORECASE) and member_rs is None:
        return None
    if member_rs is not None:
        hits.append((member_rs.start(), "security.industry_member.rs_percentile"))

    industry_rank = re.search(
        r"\bindustry\s+(?:rank(?:ing)?|percentile)\b|\bindustry[-\s]+rank\b",
        message,
        re.IGNORECASE,
    )
    if industry_rank is not None:
        hits.append((industry_rank.start(), "industry.rank.percentile"))

    return_horizon_spans: list[tuple[int, int]] = []
    for horizon, field_id in (
        ("1", "market.return.1m"),
        ("3", "market.return.3m"),
        ("12", "market.return.12m"),
    ):
        match = re.search(
            rf"\b{horizon}\s*(?:-\s*)?(?:m|mo|month|months)\b",
            message,
            re.IGNORECASE,
        )
        if match is not None:
            # A horizon is a return only when the request says return(s), not
            # relative strength, price history, or some unbounded metric.
            if not re.search(r"\breturns?\b", message, re.IGNORECASE):
                return None
            hits.append((match.start(), field_id))
            return_horizon_spans.append(match.span())

    week_match = re.search(r"\bweeks?\s+(?:in|of)\s+(?:the\s+)?stage\b", message, re.IGNORECASE)
    if week_match is not None:
        hits.append((week_match.start(), "stage.weeks_in_stage"))
    stage_without_weeks = re.sub(
        r"\bweeks?\s+(?:in|of)\s+(?:the\s+)?stage\b", "", lower, flags=re.IGNORECASE
    )
    stage_match = re.search(r"\bstage\b", stage_without_weeks, re.IGNORECASE)
    if stage_match is not None:
        # Position is only used for stable plan order; it does not represent a
        # semantic calculation.
        hits.append((lower.find("stage", stage_match.start()), "stage.current"))

    add(r"\bnext\s+earnings(?:\s+(?:date|report))?\b", "earnings.next_date")
    add(r"\b(?:latest\s+)?eps\s+growth\b", "earnings.latest.eps_growth_pct")
    add(r"\b(?:latest\s+)?(?:revenue|sales)\s+growth\b", "earnings.latest.revenue_growth_pct")
    add(r"\b(?:direct\s+)?(?:local\s+)?themes?\s+memberships?\b", "theme.local.memberships")
    add(r"\b(?:current\s+)?(?:price|quote)\b|\btrading\s+(?:at|now)\b|\bhow\s+much\s+is\b", "market.price.last")

    if not hits:
        return None
    hit_fields = {field_id for _, field_id in hits}
    # Remove only the exact spans that produced registered 1m/3m/12m return
    # facts, then reject any temporal language left over. A supported horizon
    # must not license an unrelated history clause that the native lane would
    # otherwise silently omit (for example, "1m return for one year").
    temporal_residue = list(message)
    for start, end in return_horizon_spans:
        temporal_residue[start:end] = " " * (end - start)
    if re.search(
        r"\b(?:month|months|year|years)\b",
        "".join(temporal_residue),
        re.IGNORECASE,
    ):
        return None
    completeness_checks = (
        (r"\beps\b", {"earnings.latest.eps_growth_pct"}),
        (r"\b(?:revenue|sales)\b", {"earnings.latest.revenue_growth_pct"}),
        (
            r"\bearnings\b",
            {
                "earnings.next_date", "earnings.latest.eps_growth_pct",
                "earnings.latest.revenue_growth_pct",
            },
        ),
        (
            r"\bindustry\b",
            {"industry.rank.percentile", "security.industry_member.rs_percentile"},
        ),
        (
            r"\b(?:rank(?:ing)?|percentile)\b",
            {"industry.rank.percentile", "security.industry_member.rs_percentile"},
        ),
        (
            r"\b(?:strength|member)\b",
            {"security.industry_member.rs_percentile"},
        ),
        (
            r"\breturns?\b",
            {"market.return.1m", "market.return.3m", "market.return.12m"},
        ),
        (
            r"\bgrowth\b",
            {"earnings.latest.eps_growth_pct", "earnings.latest.revenue_growth_pct"},
        ),
        (r"\bweeks?\b", {"stage.weeks_in_stage"}),
        (r"\bthemes?\b", {"theme.local.memberships"}),
        (r"\bmemberships?\b", {"theme.local.memberships"}),
    )
    for marker, satisfying_fields in completeness_checks:
        if re.search(marker, message, re.IGNORECASE) and not (hit_fields & satisfying_fields):
            return None
    ordered: list[str] = []
    for _, field_id in sorted(hits, key=lambda item: item[0]):
        if field_id not in ordered:
            ordered.append(field_id)
    return [(index, field_id) for index, field_id in enumerate(ordered)]


def plan_native_facts(message: str, context: Mapping[str, Any] | None = None) -> NativeFactPlan | None:
    """Plan only precise current native facts; otherwise return ``None``.

    ``None`` is a purposeful deep-route fallthrough, never an unavailable fact.
    Unknown identity is intentionally deferred to W1-A execution so it can be
    represented as an honest deterministic unavailable result.
    """
    if not isinstance(message, str) or not message.strip():
        return None
    if _ANALYTICAL.search(message) or _HISTORICAL.search(message) or _NON_US_QUALIFIED.search(message):
        return None
    candidate_spans, ambiguous_suppressed_symbol = _symbol_candidates(message)
    if ambiguous_suppressed_symbol:
        return None
    explicit = tuple(dict.fromkeys(candidate for candidate, _, _ in candidate_spans))
    if len(explicit) > 1:
        return None
    field_message = (
        _without_explicit_entity_spans(message, candidate_spans, explicit[0])
        if explicit else message
    )
    fields = _field_hits(field_message)
    if fields is None:
        return None
    if _has_unsupported_residue(message, explicit):
        return None
    ambient_symbol = _context_symbol(context)
    if explicit:
        symbol = explicit[0]
        explicit_entity = True
        reason = (
            "explicit_entity_wins"
            if ambient_symbol is not None and ambient_symbol != symbol
            else "explicit_request"
        )
    else:
        symbol = ambient_symbol
        if symbol is None:
            return None
        explicit_entity = False
        reason = "ambient_context"
    return NativeFactPlan(
        symbol=symbol,
        field_ids=tuple(field_id for _, field_id in fields),
        explicit_entity=explicit_entity,
        effective_context_reason=reason,
        ambient_symbol=ambient_symbol,
    )


def _relationship_receipt(
    resolver: Any,
    canonical_security: Any,
) -> tuple[str | None, dict[str, Any]]:
    """Consume the existing W1-A resolver's subscriber-projected relationship."""
    receipt = resolver.resolve_current_industry_relationship(canonical_security)
    target = receipt.get("to") if isinstance(receipt, Mapping) else None
    industry_id = target.get("id") if isinstance(target, Mapping) else None
    return (str(industry_id) if industry_id else None), receipt


def _unavailable_execution(
    plan: NativeFactPlan,
    *,
    registry_digest: str | None,
    started: float,
    reason: str,
    clock: Callable[[], float],
    route_decision_ms: float | None,
) -> NativeFactExecution:
    total_ms = round((clock() - started) * 1000, 3)
    receipt = {
        "schema": NATIVE_FACT_RECEIPT_SCHEMA,
        "route": NATIVE_FACT_ROUTE,
        "planner_version": NATIVE_FACT_PLANNER_VERSION,
        "registry_digest": registry_digest,
        "canonical_entity": None,
        "identity_admission": None,
        "effective_context": {
            "symbol": plan.symbol,
            "explicit_entity": plan.explicit_entity,
            "reason": plan.effective_context_reason,
            "precedence_reason": plan.effective_context_reason,
            "ambient_symbol": plan.ambient_symbol,
            "ambient_used": not plan.explicit_entity,
        },
        "relationship_receipt": None,
        "facts": [],
        "request_scoped_no_value_cache": True,
        "cache": {"label": "request_scoped_no_value_cache", "hit": False},
        "failure": {"status": "unavailable", "reason_code": reason},
        "timing": {
            "route_decision_ms": route_decision_ms,
            "context_assembly_ms": total_ms,
            "registry_context_assembly_ms": total_ms,
            "render_ms": 0.0,
            "total_ms": total_ms,
        },
    }
    return NativeFactExecution(
        answer=f"{plan.symbol}: native facts are unavailable ({reason}); no fact was asserted.",
        receipt=receipt,
        clauses=(),
    )


def _visible_value(envelope: Mapping[str, Any]) -> str:
    value = envelope.get("value")
    field_id = str(envelope.get("field_id") or "")
    unit = str(envelope.get("unit") or "")
    if field_id == "theme.local.memberships":
        return ", ".join(str(item) for item in value) if isinstance(value, list) and value else "none"
    if unit == "percent" and isinstance(value, (int, float)):
        return f"{value:g}%"
    if unit == "percentile" and isinstance(value, (int, float)):
        return f"{value:g} percentile"
    if len(unit) == 3 and unit.isupper() and isinstance(value, (int, float)):
        return f"{unit} {value:g}"
    return str(value)


def _render_fact(envelope: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    field_id = str(envelope["field_id"])
    source_id = str((envelope.get("source") or {}).get("source_id") or "unknown")
    as_of = envelope.get("as_of") or "unknown"
    freshness = str((envelope.get("freshness") or {}).get("state") or "unknown")
    status = str(envelope.get("status") or "unknown")
    label = {
        "market.price.last": "current price",
        "market.return.1m": "1m return",
        "market.return.3m": "3m return",
        "market.return.12m": "12m return",
        "stage.current": "Stage",
        "stage.weeks_in_stage": "weeks in Stage",
        "industry.rank.percentile": "industry rank percentile",
        "security.industry_member.rs_percentile": "within-industry member RS percentile",
        "earnings.next_date": "next earnings date",
        "earnings.latest.eps_growth_pct": "latest EPS growth",
        "earnings.latest.revenue_growth_pct": "latest revenue growth",
        "theme.local.memberships": "direct local theme memberships",
    }[field_id]
    if status == "available":
        payload = f"{label}: {_visible_value(envelope)}"
    else:
        payload = f"{label}: {status} ({envelope.get('reason_code') or 'unspecified'})"
    text = f"{payload} [{field_id}; source={source_id}; as_of={as_of}; freshness={freshness}]"
    clause = {
        "field_id": field_id,
        "fact_fingerprint": envelope.get("fact_fingerprint"),
        "status": status,
        "text": text,
    }
    return text, clause


def execute_native_fact_plan(
    plan: NativeFactPlan,
    *,
    runtime: Any | None = None,
    repo_root: str | Path | None = None,
    clock: Callable[[], float] = perf_counter,
    route_decision_ms: float | None = None,
) -> NativeFactExecution:
    """Resolve and render a plan through the frozen W1-A runtime only.

    Exceptions never turn into a deep-loop answer here: once a request is
    admitted as native fact, failure is an explicit no-fact receipt.  The
    gateway decides whether unplanned requests go deep before invoking this.
    """
    started = clock()
    context_started = started
    # Keep adapters, registry schema validation, and owner readers out of API
    # import time. Native planning itself remains pure.
    from engine.intelligence_workspace.consumers import build_brain_fact_packet
    from engine.intelligence_workspace.contracts import EntityRequest, ResolutionRequest
    from engine.intelligence_workspace.runtime import build_runtime

    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    try:
        resolver = runtime if runtime is not None else build_runtime(repo_root=root)
        registry_digest = str(resolver.registry.digest)
        # First prove the request edge through W1-A identity; no ticker is
        # trusted merely because the planner lexed it.
        canonical_security = resolver.identity_normalizer.normalize_many(
            (EntityRequest(type="security", symbol=plan.symbol, universe="us_equity"),)
        )[0]
        if canonical_security.alias_interpretation != "current_alias_only":
            raise ValueError("W1-A did not prove a current symbol alias")
    except Exception:
        return _unavailable_execution(
            plan, registry_digest=None, started=started, reason="identity_unavailable", clock=clock,
            route_decision_ms=route_decision_ms,
        )

    security_fields = tuple(field for field in plan.field_ids if field != "industry.rank.percentile")
    envelopes: list[dict[str, Any]] = []
    relationship: dict[str, Any] | None = None
    rank_resolution_failure: str | None = None
    if security_fields:
        try:
            envelopes.extend(
                resolver.resolve(
                    ResolutionRequest(
                        entities=(EntityRequest(type="security", id=canonical_security.id, universe="us_equity"),),
                        field_ids=security_fields,
                        audience="subscriber",
                        consumer_use="ai_fact",
                    )
                )
            )
        except Exception:
            return _unavailable_execution(
                plan, registry_digest=registry_digest, started=started,
                reason="resolver_unavailable", clock=clock,
                route_decision_ms=route_decision_ms,
            )
    if "industry.rank.percentile" in plan.field_ids:
        try:
            industry_id, relationship = _relationship_receipt(resolver, canonical_security)
        except Exception:
            industry_id = None
            rank_resolution_failure = "relationship_resolver_unavailable"
        if industry_id is not None:
            try:
                envelopes.extend(
                    resolver.resolve(
                        ResolutionRequest(
                            entities=(EntityRequest(type="industry", id=industry_id, universe="us_industry"),),
                            field_ids=("industry.rank.percentile",),
                            audience="subscriber",
                            consumer_use="ai_fact",
                        )
                    )
                )
            except Exception:
                rank_resolution_failure = "industry_rank_resolver_unavailable"

    # W1-A's consumer projection checks the subscriber-only surface and preserves
    # exact fact fingerprints.  It is deliberately not sent to a model.
    try:
        brain_packet = (
            build_brain_fact_packet(envelopes)
            if envelopes
            else {"schema": "intelligence_workspace.brain_fact_fixture.v1", "facts": []}
        )
    except Exception:
        return _unavailable_execution(
            plan, registry_digest=registry_digest, started=started, reason="subscriber_projection_invalid", clock=clock,
            route_decision_ms=route_decision_ms,
        )
    by_field = {str(envelope["field_id"]): envelope for envelope in envelopes}
    packet_by_field = {str(fact["field_id"]): fact for fact in brain_packet["facts"]}
    render_started = clock()
    rendered: list[str] = []
    clauses: list[dict[str, Any]] = []
    receipt_facts: list[dict[str, Any]] = []
    for display_order, field_id in enumerate(plan.field_ids):
        envelope = by_field.get(field_id)
        if envelope is None:
            # Only the industry relation may make a planned field unavailable
            # without a W1-A envelope.  Say so honestly with its own receipt.
            if field_id == "industry.rank.percentile" and (
                relationship is not None or rank_resolution_failure is not None
            ):
                source = relationship.get("source") if isinstance(relationship, Mapping) else None
                freshness_record = (
                    relationship.get("freshness") if isinstance(relationship, Mapping) else None
                )
                source_id = (
                    source.get("source_id") if isinstance(source, Mapping)
                    else "intelligence_workspace.resolver"
                )
                as_of = (
                    relationship.get("as_of") if isinstance(relationship, Mapping) else None
                ) or "unknown"
                freshness = (
                    freshness_record.get("state")
                    if isinstance(freshness_record, Mapping) else "unknown"
                )
                reason = rank_resolution_failure or relationship.get("reason_code")
                subject = (
                    "industry rank resolution"
                    if rank_resolution_failure else "current industry relationship"
                )
                text = (
                    f"{subject}: unavailable ({reason}); industry rank was not resolved "
                    f"[requested_field=industry.rank.percentile; source={source_id}; "
                    f"as_of={as_of}; freshness={freshness}]"
                )
                # W1-A did not have an industry entity to resolve. Do not forge
                # a typed envelope/fingerprint: this is evidenced only by the
                # owner-relationship receipt above.
                clause_id = f"c{display_order + 1}"
                rendered.append(text)
                clauses.append({
                    "clause_id": clause_id,
                    "display_order": display_order,
                    "field_id": None,
                    "requested_field_id": field_id,
                    "fact_fingerprint": None,
                    "status": "unavailable",
                    "receipt_kind": (
                        "resolution_failure" if rank_resolution_failure
                        else "owner_relationship"
                    ),
                    "receipt_reference": (
                        "rank_resolution_failure" if rank_resolution_failure
                        else "relationship_receipt"
                    ),
                    "text": text,
                })
            continue
        text, clause = _render_fact(envelope)
        clause_id = f"c{display_order + 1}"
        clause["clause_id"] = clause_id
        clause["display_order"] = display_order
        clause["receipt_kind"] = "typed_fact"
        rendered.append(text)
        clauses.append(clause)
        receipt_facts.append({
            **packet_by_field[field_id],
            "clause_id": clause_id,
            "display_order": display_order,
        })
    render_ms = round((clock() - render_started) * 1000, 3)
    context_ms = round((render_started - context_started) * 1000, 3)
    total_ms = round((clock() - started) * 1000, 3)
    answer = f"{plan.symbol} — " + "; ".join(rendered) if rendered else (
        f"{plan.symbol}: native facts are unavailable; no fact was asserted."
    )
    receipt = {
        "schema": NATIVE_FACT_RECEIPT_SCHEMA,
        "route": NATIVE_FACT_ROUTE,
        "planner_version": NATIVE_FACT_PLANNER_VERSION,
        "registry_digest": registry_digest,
        "canonical_entity": {"type": canonical_security.type, "id": canonical_security.id},
        "identity_admission": {
            "requested_symbol": plan.symbol,
            "alias_interpretation": canonical_security.alias_interpretation,
            "canonical_security_id": canonical_security.id,
        },
        "effective_context": {
            "symbol": plan.symbol,
            "explicit_entity": plan.explicit_entity,
            "reason": plan.effective_context_reason,
            "precedence_reason": plan.effective_context_reason,
            "ambient_symbol": plan.ambient_symbol,
            "ambient_used": not plan.explicit_entity,
        },
        "relationship_receipt": relationship,
        "rank_resolution_failure": rank_resolution_failure,
        "facts": receipt_facts,
        "clauses": [dict(clause) for clause in clauses],
        "brain_packet_schema": brain_packet["schema"],
        "request_scoped_no_value_cache": True,
        "cache": {"label": "request_scoped_no_value_cache", "hit": False},
        "timing": {
            "route_decision_ms": route_decision_ms,
            "context_assembly_ms": context_ms,
            "registry_context_assembly_ms": context_ms,
            "render_ms": render_ms,
            "total_ms": total_ms,
        },
    }
    return NativeFactExecution(answer=answer, receipt=receipt, clauses=tuple(clauses))


__all__ = [
    "ALLOWED_FIELD_IDS",
    "NATIVE_FACT_PLANNER_VERSION",
    "NATIVE_FACT_RECEIPT_SCHEMA",
    "NATIVE_FACT_ROUTE",
    "NativeFactExecution",
    "NativeFactPlan",
    "execute_native_fact_plan",
    "plan_native_facts",
]
