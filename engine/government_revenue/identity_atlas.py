"""D2 Identity Atlas — deterministic identity-path projector.

Connects the reviewed recipient entity graph
(``engine/government_revenue/entity_resolution.py``) to the Stock Identity
plane, per issuer, with every hop's evidence carried forward and every
unreviewed hop left visibly unresolved.

Frozen contract: ``research/defense_intelligence/D2_IDENTITY_ATLAS_EXECUTION_SPEC.md``.

Laws (spec §3/§7), enforced structurally in this module:

* **Exact-ID joins and graph traversal only.**  No name normalization is ever
  used to attach an identifier or an entity to an issuer — an entity's
  ``identifiers`` list is populated exclusively by walking
  ``ownership_edges``/``identifiers`` rows the reviewed graph itself declares
  reachable from that issuer's ``central:<TICKER>`` company row.  A
  same-spelled recipient name observed elsewhere is never joined; at most it
  becomes an ``unresolved_identifiers`` entry.
* **No LLM-originated values.**  Every fact in the output either comes from
  the reviewed graph, the Stock Identity snapshot, the mapping backlog, the
  dossier's own recipient observations, or the human-authored curated PIT
  file — never synthesized here.
* **No event/award references.**  The output schema carries identity paths
  only; it structurally cannot leak attribution onto an unlinked award or
  action, because it never reads one.
* **Write path limited to this artifact.**  This module never opens a
  ledger, workspace, or candidate file for writing — it is a pure function of
  its inputs, returning one dict.
* **Display/context only.**  ``authority`` in the output is the same
  all-``False`` block every other Government Revenue infrastructure artifact
  carries; nothing here ranks, sizes, or gates.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

from .entity_resolution import AUTHORITY, load_recipient_entity_graph

IDENTITY_ATLAS_CONTRACT = "government_revenue_identity_atlas.v1"
CONTRACT = IDENTITY_ATLAS_CONTRACT  # short alias used within this module
SCHEMA_VERSION = "1.0.0"
CONTENT_ID_PREFIX = "gria1-"

#: The acceptance surface named in the frozen spec.  Every other graph
#: company projects mechanically through the same code path; these six are
#: what the hostile tests and the entitled dossier hold to the letter.
PILOT_TICKERS = ("IRDM", "HII", "LMT", "GE", "BWXT", "SPR")

_DEFAULT_ATTRIBUTION_REASON = (
    "No reviewed exact recipient → legal entity path is admitted for this issuer."
)
_DEFAULT_ATTRIBUTION_REASON_ZH = "该发行人不存在已审核的“精确受益人 → 法律实体”路径。"
_DEFAULT_UNRESOLVED_REASON = (
    "No reviewed exact recipient → legal entity path covers this identifier."
)
_DEFAULT_UNRESOLVED_REASON_ZH = "该标识符不存在已审核的“精确受益人 → 法律实体”路径覆盖。"
_GAP_NO_REVIEWED_PATH = "no_reviewed_exact_path"
_GAP_UNRESOLVED_IDENTIFIERS_PRESENT = "unresolved_identifiers_present"


def _text(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _date_text(value: Any) -> str | None:
    """Render a date-like value (``pandas.Timestamp``, ``datetime``, str) as
    a clean ``YYYY-MM-DD`` string rather than ``str()``'s ``00:00:00`` tail."""
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        try:
            rendered = isoformat()
        except (TypeError, ValueError):
            rendered = None
        if isinstance(rendered, str) and rendered:
            return rendered.split("T", 1)[0]
    return _text(value)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def identity_atlas_content_id(payload: Mapping[str, Any]) -> str | None:
    """Return the immutable identity, excluding assembly timestamp and self-ID."""
    try:
        fingerprint = {
            key: value for key, value in payload.items() if key not in {"content_id", "generated_at"}
        }
        digest = hashlib.sha256(_canonical_json(fingerprint).encode("utf-8")).hexdigest()
        return CONTENT_ID_PREFIX + digest[:24]
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Graph traversal — exact-ID joins only
# ---------------------------------------------------------------------------


def _entities_by_id(loaded_graph: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row["entity_id"]: row
        for row in loaded_graph.get("entities", [])
        if isinstance(row, Mapping) and _text(row.get("entity_id"))
    }


def _companies_by_ticker(loaded_graph: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in loaded_graph.get("companies", []):
        ticker = _text(row.get("ticker")) if isinstance(row, Mapping) else None
        if ticker:
            out[ticker] = row
    return out


def _edges_by_parent_company(loaded_graph: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in loaded_graph.get("ownership_edges", []):
        parent = _text(edge.get("parent_company_id")) if isinstance(edge, Mapping) else None
        if parent:
            out[parent].append(edge)
    return out


def _edges_by_parent_entity(loaded_graph: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in loaded_graph.get("ownership_edges", []):
        parent = _text(edge.get("parent_entity_id")) if isinstance(edge, Mapping) else None
        if parent:
            out[parent].append(edge)
    return out


def _identifiers_by_entity(loaded_graph: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in loaded_graph.get("identifiers", []):
        entity_id = _text(row.get("entity_id")) if isinstance(row, Mapping) else None
        if entity_id:
            out[entity_id].append(row)
    return out


def _evidence_by_id(raw_graph: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Evidence receipts live only on the RAW graph; the normalized/loaded
    graph deliberately does not carry the evidence table forward."""
    if not isinstance(raw_graph, Mapping):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in raw_graph.get("evidence", []) or []:
        if isinstance(row, Mapping) and _text(row.get("evidence_id")):
            out[row["evidence_id"]] = row
    return out


def _evidence_summaries(
    evidence_index: Mapping[str, Mapping[str, Any]], refs: Iterable[Any]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ref in refs or []:
        source = evidence_index.get(_text(ref) or "")
        if source is None:
            continue
        out.append(
            {
                "evidence_id": source.get("evidence_id"),
                "publisher": source.get("publisher"),
                "url": source.get("url"),
                "content_sha256": source.get("content_sha256"),
            }
        )
    out.sort(key=lambda row: row.get("evidence_id") or "")
    return out


def _walk_reviewed_chain(
    *,
    company: Mapping[str, Any],
    edges_by_parent_company: Mapping[str, list[dict[str, Any]]],
    edges_by_parent_entity: Mapping[str, list[dict[str, Any]]],
    entities_by_id: Mapping[str, Mapping[str, Any]],
    identifiers_by_entity: Mapping[str, list[dict[str, Any]]],
    evidence_index: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], set[tuple[str, str]]]:
    """Walk every ``issuer_legal_entity`` edge from ``company`` outward.

    Returns ``(legal_issuer, entities, resolved_identifier_pairs)``.  This is
    the ONLY place identity flows from the graph into the Atlas: an entity or
    identifier reached any other way (a matching display name, a discovery
    ticker) never enters ``entities``.
    """
    company_id = _text(company.get("company_id")) or ""
    legal_issuer: dict[str, Any] | None = None
    entities: list[dict[str, Any]] = []
    resolved_pairs: set[tuple[str, str]] = set()
    visited: set[str] = set()

    def visit(entity_id: str, edge: Mapping[str, Any]) -> None:
        if entity_id in visited:
            return
        visited.add(entity_id)
        entity = entities_by_id.get(entity_id)
        if entity is None:
            return
        identifiers = []
        for ident in identifiers_by_entity.get(entity_id, []):
            namespace = _text(ident.get("namespace"))
            value = _text(ident.get("value"))
            if namespace and value:
                resolved_pairs.add((namespace, value))
            identifiers.append(
                {
                    "value": value,
                    "namespace": namespace,
                    "verification_state": ident.get("verification_state"),
                    "evidence": _evidence_summaries(evidence_index, ident.get("evidence_refs") or []),
                }
            )
        identifiers.sort(key=lambda row: (row.get("namespace") or "", row.get("value") or ""))
        entities.append(
            {
                "entity_id": entity_id,
                "canonical_name": entity.get("canonical_name"),
                "relationship": edge.get("relationship"),
                "economic_share": edge.get("economic_share"),
                "valid_from": edge.get("valid_from"),
                "valid_to": edge.get("valid_to"),
                "known_at": edge.get("known_at"),
                "verification_state": edge.get("verification_state"),
                "evidence": _evidence_summaries(evidence_index, edge.get("evidence_refs") or []),
                "identifiers": identifiers,
            }
        )
        for child_edge in edges_by_parent_entity.get(entity_id, []):
            child_id = _text(child_edge.get("child_entity_id"))
            if child_id:
                visit(child_id, child_edge)

    for issuer_edge in edges_by_parent_company.get(company_id, []):
        issuer_entity_id = _text(issuer_edge.get("child_entity_id"))
        if issuer_entity_id is None:
            continue
        issuer_entity = entities_by_id.get(issuer_entity_id)
        if issuer_entity is not None and legal_issuer is None:
            legal_issuer = {
                "state": "reviewed",
                "canonical_name": issuer_entity.get("canonical_name"),
                "review_state": issuer_entity.get("verification_state"),
            }
        visit(issuer_entity_id, issuer_edge)

    entities.sort(key=lambda row: row["entity_id"])
    return legal_issuer, entities, resolved_pairs


# ---------------------------------------------------------------------------
# Stock Identity, mapping backlog, dossier observations, curated overlay
# ---------------------------------------------------------------------------


def _si_rows_by_symbol(si_snapshot: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in si_snapshot or []:
        if not isinstance(row, Mapping):
            continue
        symbol = _text(row.get("symbol") or row.get("ticker"))
        if symbol:
            out[symbol] = row
    return out


def _backlog_by_ticker(mapping_backlog: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in mapping_backlog or []:
        if not isinstance(row, Mapping):
            continue
        ticker = _text(row.get("ticker"))
        if ticker:
            out[ticker] = row
    return out


def _observed_identifiers(
    dossier_awards: Iterable[Mapping[str, Any]], ticker: str
) -> dict[str, str | None]:
    """Recipient identifiers a discovery-scoped award observation carries for
    ``ticker``.  ``collection_scope_tickers`` is a discovery grouping only —
    never attribution — matching the house law this module inherits."""
    out: dict[str, str | None] = {}
    for award in dossier_awards or []:
        if not isinstance(award, Mapping):
            continue
        scope = award.get("collection_scope_tickers") or []
        if ticker not in scope:
            continue
        recipient = award.get("recipient")
        if not isinstance(recipient, Mapping):
            continue
        uei = _text(recipient.get("uei"))
        if uei is None:
            continue
        out.setdefault(uei.upper(), _text(recipient.get("name")))
    return out


def _curated_issuers(curated: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(curated, Mapping):
        return {}
    issuers = curated.get("issuers")
    if not isinstance(issuers, Mapping):
        return {}
    return {
        ticker: entry
        for ticker, entry in issuers.items()
        if isinstance(ticker, str) and isinstance(entry, Mapping)
    }


def _curated_unresolved_by_pair(
    curated_issuer: Mapping[str, Any] | None,
) -> dict[tuple[str, str], dict[str, Any]]:
    if not isinstance(curated_issuer, Mapping):
        return {}
    entries = curated_issuer.get("unresolved_identifiers")
    if not isinstance(entries, list):
        return {}
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        namespace = _text(entry.get("namespace")) or "sam_uei"
        value = _text(entry.get("value"))
        if value is None:
            continue
        out[(namespace, value.upper())] = entry
    return out


def _unresolved_identifiers(
    *,
    observed: Mapping[str, str | None],
    resolved_pairs: set[tuple[str, str]],
    curated_by_pair: Mapping[tuple[str, str], Mapping[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    covered: set[tuple[str, str]] = set()

    def _row(namespace: str, value: str, observed_name: str | None, curated: Mapping[str, Any] | None) -> dict[str, Any]:
        state = "mapping_needed"
        reason_en = _DEFAULT_UNRESOLVED_REASON
        reason_zh = _DEFAULT_UNRESOLVED_REASON_ZH
        evidence: list[Any] = []
        name = observed_name
        if curated is not None:
            state = _text(curated.get("state")) or state
            # Bare "reason" degrades to English-only when a curator has not
            # yet supplied a translation twin.
            reason_en = (
                _text(curated.get("reason_en")) or _text(curated.get("reason")) or reason_en
            )
            reason_zh = _text(curated.get("reason_zh")) or reason_zh
            raw_evidence = curated.get("evidence")
            if isinstance(raw_evidence, list):
                evidence = [row for row in raw_evidence if isinstance(row, Mapping)]
            curated_name = _text(curated.get("observed_name"))
            if curated_name:
                name = curated_name
        return {
            "namespace": namespace,
            "value": value,
            "observed_name": name,
            "state": state,
            "reason": reason_en,
            "reason_en": reason_en,
            "reason_zh": reason_zh,
            "evidence": evidence,
        }

    for value, name in observed.items():
        pair = ("sam_uei", value)
        if pair in resolved_pairs:
            continue
        covered.add(pair)
        out.append(_row("sam_uei", value, name, curated_by_pair.get(pair)))

    # A curated fact never vanishes just because it is outside the current
    # discovery sample -- evidence-bearing human review is durable, unlike a
    # bounded nightly collection window.
    for pair, curated in curated_by_pair.items():
        if pair in covered or pair in resolved_pairs:
            continue
        namespace, value = pair
        out.append(_row(namespace, value, _text(curated.get("observed_name")), curated))

    out.sort(key=lambda row: (row["namespace"], row["value"]))
    return out


def _public_security(
    *, ticker: str, si_row: Mapping[str, Any] | None, curated_state: str | None
) -> dict[str, Any]:
    if curated_state == "listing_terminated":
        return {"state": "listing_terminated", "first_date": None, "last_date": None, "asof": None}
    if si_row is not None:
        return {
            "state": "verified_live",
            "first_date": _date_text(si_row.get("first_date")),
            "last_date": _date_text(si_row.get("last_date")),
            "asof": _date_text(si_row.get("asof")),
        }
    if curated_state is not None:
        # A ticker absent from the Stock Identity universe can be described as
        # historical (curated evidence, e.g. an 8-K acquisition close) but
        # never as anything resembling a live state -- that is exactly the
        # fabrication this projector must fail closed against (spec hostile
        # test 1).
        raise ValueError(
            f"curated identity atlas claims public_security_state={curated_state!r} for "
            f"{ticker!r}, which is absent from the Stock Identity snapshot; only "
            "'listing_terminated' may be asserted for a ticker outside the SI universe"
        )
    return {"state": "not_in_si_universe", "first_date": None, "last_date": None, "asof": None}


def _curated_events(curated_issuer: Mapping[str, Any] | None, key: str) -> list[dict[str, Any]]:
    if not isinstance(curated_issuer, Mapping):
        return []
    events = curated_issuer.get(key)
    if not isinstance(events, list):
        return []
    out: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, Mapping):
            continue
        row = dict(event)
        headline_en = _text(row.get("headline_en")) or _text(row.get("headline")) or _text(row.get("note"))
        headline_zh = _text(row.get("headline_zh")) or headline_en
        row["headline_en"] = headline_en
        row["headline_zh"] = headline_zh
        row.pop("headline", None)
        row.pop("note", None)
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# Per-issuer assembly
# ---------------------------------------------------------------------------


def _build_issuer(
    ticker: str,
    *,
    companies_by_ticker: Mapping[str, Mapping[str, Any]],
    edges_by_parent_company: Mapping[str, list[dict[str, Any]]],
    edges_by_parent_entity: Mapping[str, list[dict[str, Any]]],
    entities_by_id: Mapping[str, Mapping[str, Any]],
    identifiers_by_entity: Mapping[str, list[dict[str, Any]]],
    evidence_index: Mapping[str, Mapping[str, Any]],
    si_by_symbol: Mapping[str, Mapping[str, Any]],
    backlog_by_ticker: Mapping[str, Mapping[str, Any]],
    dossier_awards: Iterable[Mapping[str, Any]],
    curated_issuers: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    company = companies_by_ticker.get(ticker)
    curated_issuer = curated_issuers.get(ticker)

    legal_issuer: dict[str, Any] | None = None
    entities: list[dict[str, Any]] = []
    resolved_pairs: set[tuple[str, str]] = set()
    if company is not None:
        legal_issuer, entities, resolved_pairs = _walk_reviewed_chain(
            company=company,
            edges_by_parent_company=edges_by_parent_company,
            edges_by_parent_entity=edges_by_parent_entity,
            entities_by_id=entities_by_id,
            identifiers_by_entity=identifiers_by_entity,
            evidence_index=evidence_index,
        )
    if legal_issuer is None:
        legal_issuer = {"state": "not_asserted", "canonical_name": None, "review_state": None}

    issuer_attribution = "reviewed" if entities else "not_asserted"
    attribution_reason = None
    attribution_reason_en = None
    attribution_reason_zh = None
    if issuer_attribution == "not_asserted":
        curated_reason_en = _text((curated_issuer or {}).get("attribution_reason_en"))
        curated_reason_bare = _text((curated_issuer or {}).get("attribution_reason"))
        attribution_reason_en = curated_reason_en or curated_reason_bare or _DEFAULT_ATTRIBUTION_REASON
        attribution_reason_zh = (
            _text((curated_issuer or {}).get("attribution_reason_zh")) or _DEFAULT_ATTRIBUTION_REASON_ZH
        )
        attribution_reason = attribution_reason_en

    curated_state = _text((curated_issuer or {}).get("public_security_state"))
    public_security = _public_security(
        ticker=ticker, si_row=si_by_symbol.get(ticker), curated_state=curated_state
    )

    observed = _observed_identifiers(dossier_awards, ticker)
    curated_by_pair = _curated_unresolved_by_pair(curated_issuer)
    unresolved_identifiers = _unresolved_identifiers(
        observed=observed, resolved_pairs=resolved_pairs, curated_by_pair=curated_by_pair
    )

    listing_events = _curated_events(curated_issuer, "listing_events")
    separation_events = _curated_events(curated_issuer, "separation_events")

    gaps: list[dict[str, str]] = []
    curated_gaps = (curated_issuer or {}).get("gaps") if curated_issuer else None
    if isinstance(curated_gaps, list):
        for item in curated_gaps:
            if isinstance(item, Mapping):
                code = _text(item.get("code")) or _GAP_NO_REVIEWED_PATH
                text_en = _text(item.get("text_en")) or _text(item.get("text"))
                text_zh = _text(item.get("text_zh"))
                if text_en:
                    gaps.append({"code": code, "text_en": text_en, "text_zh": text_zh or text_en})
            elif _text(item):
                # A bare curated string degrades to English-only.
                gaps.append({"code": _GAP_NO_REVIEWED_PATH, "text_en": str(item), "text_zh": str(item)})
    elif issuer_attribution == "not_asserted":
        gaps.append(
            {
                "code": _GAP_NO_REVIEWED_PATH,
                "text_en": f"No reviewed exact recipient → legal entity path for {ticker}.",
                "text_zh": f"发行人{ticker}不存在已审核的“精确受益人 → 法律实体”路径。",
            }
        )
    if unresolved_identifiers and issuer_attribution == "reviewed":
        gaps.append(
            {
                "code": _GAP_UNRESOLVED_IDENTIFIERS_PRESENT,
                "text_en": (
                    f"{len(unresolved_identifiers)} observed identifier(s) for {ticker} have no "
                    "reviewed ownership path and stay unresolved."
                ),
                "text_zh": (
                    f"发行人{ticker}有{len(unresolved_identifiers)}个已观测到的标识符尚无已审核的"
                    "所有权路径，保持未解决状态。"
                ),
            }
        )

    backlog_row = backlog_by_ticker.get(ticker)
    company_name = _text((curated_issuer or {}).get("company_name")) or (
        _text(backlog_row.get("company_name")) if backlog_row else None
    )

    return {
        "ticker": ticker,
        "company_name": company_name,
        "public_security": public_security,
        "legal_issuer": legal_issuer,
        "entities": entities,
        "unresolved_identifiers": unresolved_identifiers,
        "issuer_attribution": issuer_attribution,
        "attribution_reason": attribution_reason,
        "attribution_reason_en": attribution_reason_en,
        "attribution_reason_zh": attribution_reason_zh,
        "listing_events": listing_events,
        "separation_events": separation_events,
        "gaps": gaps,
    }


# ---------------------------------------------------------------------------
# Top-level projector
# ---------------------------------------------------------------------------


def build_identity_atlas(
    *,
    graph: Mapping[str, Any] | None,
    si_snapshot: Iterable[Mapping[str, Any]] = (),
    mapping_backlog: Iterable[Mapping[str, Any]] = (),
    dossier_awards: Iterable[Mapping[str, Any]] = (),
    curated: Mapping[str, Any] | None = None,
    generated_at: str,
    graph_as_of: str | None = None,
) -> dict[str, Any]:
    """Pure projector: reviewed graph + SI snapshot + backlog + dossier + curated -> Atlas.

    ``graph_as_of`` defaults to the graph's OWN ``graph_known_at`` rather than
    an external payload's ``as_of``.  A sibling artifact (``latest.json``)
    lags this graph by up to one nightly cycle; evaluating admission against
    an unrelated, possibly-stale external clock would make a freshly reviewed
    graph appear entirely unreviewed here until that sibling caught up, which
    is not what this projector is for. Callers replaying a historical
    ``as_of`` may still pass one explicitly.
    """
    raw_graph = graph if isinstance(graph, Mapping) else None
    as_of = graph_as_of if graph_as_of is not None else (
        raw_graph.get("graph_known_at") if raw_graph is not None else None
    )
    loaded = load_recipient_entity_graph(raw_graph, as_of=as_of)
    ready = loaded.get("status") == "ready"
    loaded_graph = loaded.get("graph") if ready else {}

    companies_by_ticker = _companies_by_ticker(loaded_graph) if ready else {}
    edges_by_parent_company = _edges_by_parent_company(loaded_graph) if ready else {}
    edges_by_parent_entity = _edges_by_parent_entity(loaded_graph) if ready else {}
    entities_by_id = _entities_by_id(loaded_graph) if ready else {}
    identifiers_by_entity = _identifiers_by_entity(loaded_graph) if ready else {}
    evidence_index = _evidence_by_id(raw_graph)

    si_by_symbol = _si_rows_by_symbol(si_snapshot)
    backlog_by_ticker = _backlog_by_ticker(mapping_backlog)
    dossier_awards = list(dossier_awards or [])
    curated_issuers = _curated_issuers(curated)

    tickers = sorted(
        set(backlog_by_ticker) | set(companies_by_ticker) | set(curated_issuers)
    )

    issuers = [
        _build_issuer(
            ticker,
            companies_by_ticker=companies_by_ticker,
            edges_by_parent_company=edges_by_parent_company,
            edges_by_parent_entity=edges_by_parent_entity,
            entities_by_id=entities_by_id,
            identifiers_by_entity=identifiers_by_entity,
            evidence_index=evidence_index,
            si_by_symbol=si_by_symbol,
            backlog_by_ticker=backlog_by_ticker,
            dossier_awards=dossier_awards,
            curated_issuers=curated_issuers,
        )
        for ticker in tickers
    ]

    si_asof_values = {_date_text(row.get("asof")) for row in si_by_symbol.values() if row.get("asof") is not None}
    si_asof_values.discard(None)
    si_asof = sorted(si_asof_values)[-1] if si_asof_values else None

    payload = {
        "contract": CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "graph_id": loaded.get("graph_id"),
        "graph_digest": loaded.get("graph_digest"),
        "graph_status": loaded.get("status"),
        "si_asof": si_asof,
        "authority": dict(AUTHORITY),
        "issuers": issuers,
    }
    payload["content_id"] = identity_atlas_content_id(payload)
    return payload


# ---------------------------------------------------------------------------
# Disk IO wrapper
# ---------------------------------------------------------------------------


def _default_root() -> Path:
    return Path(__file__).resolve().parents[2]


def build_identity_atlas_payload(
    *, root: Path | None = None, generated_at: str, graph_as_of: str | None = None
) -> dict[str, Any]:
    """Read the committed inputs from disk and build the Atlas payload.

    Read-only: opens no ledger, workspace, or candidate file for writing.
    """
    root = Path(root).resolve() if root is not None else _default_root()
    data_dir = root / "data" / "government_revenue"

    graph_path = data_dir / "recipient_entity_graph.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8")) if graph_path.exists() else None

    si_path = root / "data" / "stock_identity" / "partition" / "universe_snapshot_v1.parquet"
    si_snapshot: list[dict[str, Any]] = []
    if si_path.exists():
        import pandas as pd  # noqa: PLC0415 - optional heavy dep, only needed for the live build

        si_snapshot = pd.read_parquet(si_path).to_dict("records")

    backlog_path = data_dir / "candidate_queue.json"
    mapping_backlog: list[dict[str, Any]] = []
    if backlog_path.exists():
        queue = json.loads(backlog_path.read_text(encoding="utf-8"))
        rows = queue.get("mapping_backlog") if isinstance(queue, Mapping) else None
        if isinstance(rows, list):
            mapping_backlog = [row for row in rows if isinstance(row, Mapping)]

    dossiers_path = data_dir / "dossiers.json"
    dossier_awards: list[dict[str, Any]] = []
    if dossiers_path.exists():
        dossiers = json.loads(dossiers_path.read_text(encoding="utf-8"))
        rows = dossiers.get("awards") if isinstance(dossiers, Mapping) else None
        if isinstance(rows, list):
            dossier_awards = [row for row in rows if isinstance(row, Mapping)]

    curated_path = data_dir / "identity_atlas_curated.json"
    curated = None
    if curated_path.exists():
        curated = json.loads(curated_path.read_text(encoding="utf-8"))

    return build_identity_atlas(
        graph=graph,
        si_snapshot=si_snapshot,
        mapping_backlog=mapping_backlog,
        dossier_awards=dossier_awards,
        curated=curated,
        generated_at=generated_at,
        graph_as_of=graph_as_of,
    )


# ---------------------------------------------------------------------------
# Schema validator
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _validator() -> Any:
    from jsonschema import Draft202012Validator, FormatChecker

    path = (
        Path(__file__).resolve().parents[2]
        / "contracts"
        / "government_revenue"
        / "government_revenue_identity_atlas.v1.schema.json"
    )
    return Draft202012Validator(json.loads(path.read_text(encoding="utf-8")), format_checker=FormatChecker())


def is_valid_identity_atlas_payload(value: Any) -> bool:
    """Validate schema and the immutable content ID together."""
    if not isinstance(value, dict) or any(_validator().iter_errors(value)):
        return False
    return identity_atlas_content_id(value) == value.get("content_id")
