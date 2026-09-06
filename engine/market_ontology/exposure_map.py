"""GMI exposure composer: pure shock -> theme -> company projection (A-F04-W2-1).

Authority ceiling: ``research_display_only``. This module originates no score, rank,
confidence, weight, ordering-by-magnitude, gate, size or trade semantic. It is a
read-only projection of edges the theme graph already holds, at a caller-supplied
as-of date, rights-filtered through the owner's own gate
(``engine.theme_graph.rights``). Nothing in the scoring path imports it, and it
imports nothing from the scoring core (test 13 enforces both directions).

Three laws, restated from the frozen spec:

* L1 — owner-side reads only: GMI is reached ONLY through
  ``engine.theme_graph.store.read_edges`` / ``read_identity_resolution``.
* L2 — nothing new in the graph: no new node kind, no new edge type, no new store,
  no generic ``RELATED`` traversal, no causal DAG, no opportunity scalar.
* L3 — no value may order anything (G0.11): every list here is ordered by node id
  (or ``(code, subject_id)`` for typed-null lists), never by a magnitude.

The shock -> theme link is CALLER-SUPPLIED (``ShockSpec``), never derived: this module
does not and may never infer which themes a macro shock hits — that is a causal claim.

No clock, no network, no LLM, no ``data/`` write. A loader exception, an unknown shock,
a rights refusal and an unresolved identifier are all TYPED NULLS in the return value —
this module never raises for a data-availability reason.
"""
from __future__ import annotations

import dataclasses
import datetime
import re
import typing
from collections.abc import Callable, Mapping, Sequence
from typing import Any

SCHEMA_ID = "market_ontology.exposure_map/v1"
ENGINE_VERSION = "market_ontology.exposure_map.v1"
AUTHORITY_CEILING = "research_display_only"

_EDGE_READER = "engine.theme_graph.store.read_edges(latest_belief=True)"
_IDENTITY_READER = "engine.theme_graph.store.read_identity_resolution(latest=True)"
_CHAIN_READER = "engine.transmission_chains.load_chains()"

# --- §3.1 id grammars (closed allowlist) -----------------------------------------

_COMPANY_ID_RE = re.compile(r"^co:(us|cn|hk|ca|intl):[A-Za-z0-9.\-]+(#[0-9]+)?$")
_LOCAL_THEME_ID_RE = re.compile(r"^ltheme:(finviz|ths):[A-Za-z0-9_.\-]+$")


def _is_company_id(node_id: str) -> bool:
    return bool(_COMPANY_ID_RE.match(node_id))


def _is_local_theme_id(node_id: str) -> bool:
    return bool(_LOCAL_THEME_ID_RE.match(node_id))


def _is_canonical_theme_id(node_id: str) -> bool:
    return node_id.startswith("theme:")


def _is_known_theme_grammar(node_id: str) -> bool:
    return _is_local_theme_id(node_id) or _is_canonical_theme_id(node_id)


def _market_scope_of_company(node_id: str) -> str | None:
    m = _COMPANY_ID_RE.match(node_id)
    return m.group(1) if m else None


# --- copied verbatim from engine/intelligence_workspace/adapters/theme.py --------
# (this packet must not create a dependency between two consumer planes; the source
# module is a different consumer with its own contract, so these three tiny helpers
# are duplicated rather than imported.)

def _records(value: Any) -> list[Mapping[str, Any]]:
    if value is None:
        raise TypeError("owner view is absent")
    if hasattr(value, "to_dict"):
        rows = value.to_dict("records")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        rows = list(value)
    else:
        raise TypeError("owner view is not tabular")
    if any(not isinstance(row, Mapping) for row in rows):
        raise TypeError("owner view contains a non-record row")
    return rows


def _is_null(value: Any) -> bool:
    if value is None:
        return True
    try:
        import pandas as pd

        return bool(pd.isna(value))
    except (ImportError, TypeError, ValueError):
        return False


def _date(value: Any) -> datetime.date | None:
    if _is_null(value):
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value).strip())


def _date_str(value: Any) -> str | None:
    d = _date(value)
    return d.isoformat() if d is not None else None


def _str_or_none(value: Any) -> str | None:
    return None if _is_null(value) else str(value)


# --- typed nulls (§4.5 / §4.6) ---------------------------------------------------

_REASONS: dict[str, tuple[str, str]] = {
    "SHOCK_UNKNOWN": (
        "This shock is not in the transmission library yet, so we cannot map it.",
        "该冲击尚未收录在传导链知识库中，暂时无法绘制其影响路径。",
    ),
    "NO_THEMES_DECLARED": (
        "No themes have been linked to this shock yet.",
        "尚未为该冲击关联任何主题。",
    ),
    "NO_THEME_EDGES": (
        "We have no links recorded for this theme as of this date.",
        "截至该日期，我们尚未记录该主题的任何关联。",
    ),
    "NO_MEMBERSHIP_YET": (
        "We know this theme, but its company list has not been recorded yet.",
        "我们已知晓该主题，但其公司名单尚未被记录。",
    ),
    "RIGHTS_SUPPRESSED": (
        "The source of this theme's company list cannot be shown here.",
        "该主题公司名单的来源在此处不可展示。",
    ),
    "IDENTITY_UNRESOLVED": (
        "We could not recognise this identifier.",
        "我们无法识别该标识符。",
    ),
    "STORE_UNAVAILABLE": (
        "The theme graph is not available right now.",
        "主题图谱目前不可用。",
    ),
    "NO_ETF_EDGES": (
        "No fund is recorded as tracking this group yet.",
        "尚无基金被记录为跟踪该组别。",
    ),
    "BELIEF_AFTER_ASOF": (
        "A later update to this link exists but is not used for this date.",
        "该关联存在更晚的更新，但未用于此日期。",
    ),
    "IDENTITY_COLLISION": (
        "Two different identifiers resolved to the same security here.",
        "此处两个不同的标识符指向了同一证券。",
    ),
}


def _unavailable(code: str, *, subject_id: str | None = None,
                  detail: str | None = None) -> dict[str, Any]:
    en, zh = _REASONS[code]
    return {
        "code": code,
        "reason": {"en": en, "zh": zh},
        "subject_id": subject_id,
        "detail": detail,
    }


# --- public dataclasses -----------------------------------------------------------

@dataclasses.dataclass(frozen=True, slots=True)
class ShockSpec:
    """A named TXI chain plus the theme node ids a CALLER declares it touches.

    The shock->theme link is an INPUT, never a derivation: this module does not and
    may never infer which themes a macro shock hits (that is a causal claim; DNR
    no-causal-DAG). ``shock_id`` must be a chain id present in
    knowledge/transmission/*.yaml. ``theme_node_ids`` must satisfy the GMI id
    grammar (engine/theme_graph/identity.py).
    """

    shock_id: str
    theme_node_ids: tuple[str, ...]
    declared_by: str
    note: str | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class Shock:
    shock_id: str
    vocabulary: str
    title: Mapping[str, str | None]
    tier: str | None
    declared_by: str
    note: str | None


@dataclasses.dataclass(frozen=True, slots=True)
class ThemeExposure:
    theme_node_id: str
    theme_plane: str | None
    rights_family: str | None
    name: Mapping[str, str | None]
    state: str
    unavailable: Mapping[str, Any] | None
    companies: tuple[Mapping[str, Any], ...] | None
    company_count: int | None
    distinct_security_count: int | None
    etf_proxies: tuple[Mapping[str, Any], ...] | None
    abstentions: tuple[Mapping[str, Any], ...]


@dataclasses.dataclass(frozen=True, slots=True)
class ExposureMap:
    schema: str
    asof: datetime.date
    shock: Shock
    themes: tuple[ThemeExposure, ...]
    unavailable: Mapping[str, Any] | None
    provenance: Mapping[str, Any]


class StoreView(typing.Protocol):
    """The read-only slice of engine.theme_graph.store this module is allowed to see."""

    def read_edges(self) -> Any: ...

    def read_identity_resolution(self) -> Any: ...

    def read_meta(self) -> Mapping[str, Any]: ...

    def read_nodes(self) -> Any: ...  # OPTIONAL: for name_en/name_zh only


class _DefaultStoreView:
    """Production view. Imports engine.theme_graph.store lazily, inside each call."""

    def read_edges(self) -> Any:
        from engine.theme_graph.store import read_edges

        return read_edges(latest_belief=True)

    def read_identity_resolution(self) -> Any:
        from engine.theme_graph.store import read_identity_resolution

        return read_identity_resolution(latest=True)

    def read_meta(self) -> Mapping[str, Any]:
        from engine.theme_graph.store import read_meta

        return read_meta()

    def read_nodes(self) -> Any:
        from engine.theme_graph.store import read_nodes

        return read_nodes(current=True)


def default_store_view() -> StoreView:
    """The production ``StoreView``. See ``_DefaultStoreView`` for the exact bindings."""
    return _DefaultStoreView()


def _default_chain_loader() -> Mapping[str, Mapping[str, Any]]:
    from engine.transmission_chains import load_chains

    out: dict[str, Mapping[str, Any]] = {}
    for chain in load_chains():
        cid = chain.get("chain")
        if isinstance(cid, str):
            out[cid] = chain
    return out


def _default_family_resolver(node_id: object) -> str | None:
    from engine.theme_graph import rights

    return rights.family_for_node_id(node_id)


def _default_assert_allowed(family: str) -> None:
    from engine.theme_graph import rights

    rights.assert_public_emission_allowed(family)


# --- as-of parsing -----------------------------------------------------------------

def _parse_asof(asof: datetime.date | str) -> datetime.date:
    if isinstance(asof, datetime.datetime):
        return asof.date()
    if isinstance(asof, datetime.date):
        return asof
    return datetime.date.fromisoformat(str(asof).strip())


# --- edge normalisation + belief collapse (§3.4) -----------------------------------

_EDGE_FIELDS = (
    "edge_id", "type", "src", "dst", "valid_from", "valid_to", "evidence_time",
    "belief_time", "era", "source_class", "date_provenance", "evidence_refs",
    "confidence_basis", "computed_at", "engine_version",
)


def _normalise_edge(row: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field in _EDGE_FIELDS:
        value = row.get(field)
        if field in ("valid_from", "valid_to", "evidence_time", "belief_time"):
            out[field] = _date_str(value)
        elif field == "evidence_refs":
            if _is_null(value):
                out[field] = []
            elif isinstance(value, (list, tuple)):
                out[field] = list(value)
            else:
                out[field] = [value]
        else:
            out[field] = _str_or_none(value)
    return out


def _collapse_and_filter_edges(
    raw_rows: list[Mapping[str, Any]], asof: datetime.date,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Group raw edge rows by edge_id, collapse to the belief in view at ``asof``,
    then apply the point-in-time filter (§3.4). Returns (in_view_by_edge_id,
    clock_mismatch_abstentions)."""
    by_id: dict[str, list[Mapping[str, Any]]] = {}
    for row in raw_rows:
        eid = row.get("edge_id")
        if eid is None:
            continue
        by_id.setdefault(str(eid), []).append(row)

    in_view: dict[str, dict[str, Any]] = {}
    abstentions: list[dict[str, Any]] = []

    for eid, rows in by_id.items():
        eligible: list[Mapping[str, Any]] = []
        future: list[Mapping[str, Any]] = []
        for row in rows:
            belief = _date(row.get("belief_time"))
            if belief is not None and belief > asof:
                future.append(row)
            else:
                eligible.append(row)
        if not eligible:
            if future:
                dst = str(future[0].get("dst") or "")
                entry = _unavailable("BELIEF_AFTER_ASOF", subject_id=eid)
                entry["_dst"] = dst
                abstentions.append(entry)
            continue

        def _sort_key(row: Mapping[str, Any]) -> tuple[Any, Any]:
            belief = _date(row.get("belief_time")) or datetime.date.min
            computed = row.get("computed_at") or ""
            return (belief, str(computed))

        selected = sorted(eligible, key=_sort_key)[-1]

        valid_from = _date(selected.get("valid_from"))
        valid_to = _date(selected.get("valid_to"))
        if valid_from is not None and valid_from > asof:
            continue
        if valid_to is not None and valid_to <= asof:
            continue

        in_view[eid] = _normalise_edge(selected)

    return in_view, sorted(abstentions, key=lambda a: (a["code"], a["subject_id"] or ""))


# --- the walk (§3.3) ----------------------------------------------------------------

@dataclasses.dataclass
class _PathHit:
    company_node_id: str
    path_kind: str
    hops: int
    via_node_id: str | None
    edge_ids: tuple[str, ...]


def _index_by_dst(edges: dict[str, dict[str, Any]], edge_type: str) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for edge in edges.values():
        if edge["type"] == edge_type:
            out.setdefault(edge["dst"], []).append(edge)
    return out


def _walk_theme(
    theme_id: str,
    *,
    member_of_by_dst: dict[str, list[dict[str, Any]]],
    expresses_by_dst: dict[str, list[dict[str, Any]]],
    family_resolver: Callable[[object], str | None],
    assert_allowed: Callable[[str], None],
) -> tuple[list[_PathHit], list[dict[str, Any]], set[str]]:
    """Returns (hits, abstentions, baskets_used_on_allowed_bridges)."""
    hits: list[_PathHit] = []
    abstentions: list[dict[str, Any]] = []
    baskets_used: set[str] = set()

    # Path A — direct_membership (1 hop).
    for edge in member_of_by_dst.get(theme_id, []):
        if _is_company_id(edge["src"]):
            hits.append(_PathHit(edge["src"], "direct_membership", 1, None, (edge["edge_id"],)))

    # Path B — basket_bridge (2 hops).
    for edge in expresses_by_dst.get(theme_id, []):
        basket = edge["src"]
        if not basket.startswith("basket:"):
            continue
        family = family_resolver(basket)
        if family is not None:
            try:
                assert_allowed(family)
            except Exception:
                abstentions.append(_unavailable("RIGHTS_SUPPRESSED", subject_id=basket, detail=family))
                continue
        baskets_used.add(basket)
        for member_edge in member_of_by_dst.get(basket, []):
            if _is_company_id(member_edge["src"]):
                hits.append(_PathHit(
                    member_edge["src"], "basket_bridge", 2, basket,
                    (edge["edge_id"], member_edge["edge_id"]),
                ))

    # Path C — local_theme_bridge (2 hops), only for canonical theme:* ids.
    if _is_canonical_theme_id(theme_id):
        for edge in expresses_by_dst.get(theme_id, []):
            ltheme = edge["src"]
            if not _is_local_theme_id(ltheme):
                continue
            family = family_resolver(ltheme)
            if family is not None:
                try:
                    assert_allowed(family)
                except Exception:
                    abstentions.append(_unavailable("RIGHTS_SUPPRESSED", subject_id=ltheme, detail=family))
                    continue
            for member_edge in member_of_by_dst.get(ltheme, []):
                if _is_company_id(member_edge["src"]):
                    hits.append(_PathHit(
                        member_edge["src"], "local_theme_bridge", 2, ltheme,
                        (edge["edge_id"], member_edge["edge_id"]),
                    ))

    return hits, abstentions, baskets_used


# --- identity (§3.6) -----------------------------------------------------------------

def _identity_for(node_id: str, identity_rows: dict[str, Mapping[str, Any]]) -> dict[str, Any]:
    row = identity_rows.get(node_id)
    if row is None:
        return {
            "state": "NO_RESOLUTION_ROW", "security_id": None, "listing_key": None,
            "issuer_id": None, "resolution_asof": None, "refusal_reason": None,
            "collision_group": None,
        }
    state = _str_or_none(row.get("resolution_state")) or "NO_RESOLUTION_ROW"
    if state != "RESOLVED":
        return {
            "state": state, "security_id": None, "listing_key": None, "issuer_id": None,
            "resolution_asof": _date_str(row.get("resolution_asof")),
            "refusal_reason": _str_or_none(row.get("refusal_reason")),
            "collision_group": None,
        }
    return {
        "state": state,
        "security_id": _str_or_none(row.get("security_id")),
        "listing_key": _str_or_none(row.get("listing_key")),
        "issuer_id": _str_or_none(row.get("issuer_id")),
        "resolution_asof": _date_str(row.get("resolution_asof")),
        "refusal_reason": _str_or_none(row.get("refusal_reason")),
        "collision_group": None,
    }


# --- one theme's full row -------------------------------------------------------------

def _compose_theme(
    theme_id: str,
    *,
    edges_by_id: dict[str, dict[str, Any]],
    member_of_by_dst: dict[str, list[dict[str, Any]]],
    expresses_by_dst: dict[str, list[dict[str, Any]]],
    tracks_by_dst: dict[str, list[dict[str, Any]]],
    identity_rows: dict[str, Mapping[str, Any]],
    family_resolver: Callable[[object], str | None],
    assert_allowed: Callable[[str], None],
) -> dict[str, Any]:
    if not _is_known_theme_grammar(theme_id):
        return {
            "theme_node_id": theme_id, "theme_plane": None, "rights_family": None,
            "name": {"en": None, "zh": None}, "state": "IDENTITY_UNRESOLVED",
            "unavailable": _unavailable("IDENTITY_UNRESOLVED", subject_id=theme_id),
            "companies": None, "company_count": None, "distinct_security_count": None,
            "etf_proxies": None, "abstentions": [],
        }

    theme_plane = "local_theme" if _is_local_theme_id(theme_id) else "canonical_theme"
    theme_family = family_resolver(theme_id)

    base = {
        "theme_node_id": theme_id, "theme_plane": theme_plane,
        "rights_family": theme_family, "name": {"en": None, "zh": None},
    }

    if theme_family is not None:
        try:
            assert_allowed(theme_family)
        except Exception:
            return {
                **base, "state": "RIGHTS_SUPPRESSED",
                "unavailable": _unavailable("RIGHTS_SUPPRESSED", subject_id=theme_id, detail=theme_family),
                "companies": None, "company_count": None, "distinct_security_count": None,
                "etf_proxies": None, "abstentions": [],
            }

    has_any_edge = bool(member_of_by_dst.get(theme_id)) or bool(expresses_by_dst.get(theme_id)) or any(
        e["src"] == theme_id or e["dst"] == theme_id for e in edges_by_id.values()
    )
    if not has_any_edge:
        return {
            **base, "state": "NO_THEME_EDGES",
            "unavailable": _unavailable("NO_THEME_EDGES", subject_id=theme_id),
            "companies": None, "company_count": None, "distinct_security_count": None,
            "etf_proxies": None, "abstentions": [],
        }

    hits, path_abstentions, baskets_used = _walk_theme(
        theme_id, member_of_by_dst=member_of_by_dst, expresses_by_dst=expresses_by_dst,
        family_resolver=family_resolver, assert_allowed=assert_allowed,
    )

    if not hits:
        abstentions = sorted(path_abstentions, key=lambda a: (a["code"], a["subject_id"] or ""))
        return {
            **base, "state": "NO_MEMBERSHIP_YET",
            "unavailable": _unavailable("NO_MEMBERSHIP_YET", subject_id=theme_id),
            "companies": None, "company_count": None, "distinct_security_count": None,
            "etf_proxies": None, "abstentions": abstentions,
        }

    # Group hits by company -> paths (double-count law: one row per company, N paths).
    by_company: dict[str, list[_PathHit]] = {}
    for hit in hits:
        by_company.setdefault(hit.company_node_id, []).append(hit)

    company_rows: list[dict[str, Any]] = []
    for company_id in sorted(by_company):
        company_hits = by_company[company_id]
        paths: list[dict[str, Any]] = []
        for hit in company_hits:
            edge_objs = sorted(
                (edges_by_id[eid] for eid in hit.edge_ids if eid in edges_by_id),
                key=lambda e: e["edge_id"],
            )
            paths.append({
                "path_kind": hit.path_kind, "hops": hit.hops,
                "via_node_id": hit.via_node_id, "edges": edge_objs,
            })
        paths.sort(key=lambda p: (p["edges"][0]["edge_id"] if p["edges"] else ""))
        identity = _identity_for(company_id, identity_rows)
        company_rows.append({
            "company_node_id": company_id,
            "market_scope": _market_scope_of_company(company_id),
            "rights_family": family_resolver(company_id),
            "identity": identity,
            "paths": paths,
        })

    # Identity collision (§3.6).
    by_security: dict[str, list[str]] = {}
    for row in company_rows:
        sec = row["identity"]["security_id"]
        if sec is not None:
            by_security.setdefault(sec, []).append(row["company_node_id"])
    collision_abstentions: list[dict[str, Any]] = []
    for sec, members in by_security.items():
        if len(members) > 1:
            for row in company_rows:
                if row["identity"]["security_id"] == sec:
                    row["identity"]["collision_group"] = sec
            collision_abstentions.append(
                _unavailable("IDENTITY_COLLISION", subject_id=sec, detail=",".join(sorted(members)))
            )

    company_count = len(company_rows)
    distinct_security_count = len({r["identity"]["security_id"] for r in company_rows
                                    if r["identity"]["security_id"] is not None})

    # etf_proxies (§4.4b).
    etf_proxies: list[dict[str, Any]] | None = None
    etf_abstentions: list[dict[str, Any]] = []
    if baskets_used:
        found: list[dict[str, Any]] = []
        any_tracks = False
        for basket in sorted(baskets_used):
            for tedge in tracks_by_dst.get(basket, []):
                etf_id = tedge["src"]
                any_tracks = True
                found.append({
                    "etf_node_id": etf_id, "via_basket_node_id": basket,
                    "rights_family": family_resolver(etf_id), "edges": [tedge],
                })
        if not any_tracks:
            etf_abstentions.append(_unavailable("NO_ETF_EDGES", subject_id=theme_id))
        else:
            found.sort(key=lambda p: p["etf_node_id"])
            etf_proxies = found

    all_abstentions = sorted(
        path_abstentions + collision_abstentions + etf_abstentions,
        key=lambda a: (a["code"], a["subject_id"] or ""),
    )

    return {
        **base, "state": "OK", "unavailable": None,
        "companies": company_rows, "company_count": company_count,
        "distinct_security_count": distinct_security_count,
        "etf_proxies": etf_proxies, "abstentions": all_abstentions,
    }


# --- top-level composition -------------------------------------------------------------

def compose_exposure_map(
    store: StoreView,
    shock_spec: ShockSpec,
    *,
    asof: datetime.date | str,
    chain_loader: Callable[[], Mapping[str, Mapping[str, Any]]] | None = None,
    family_resolver: Callable[[object], str | None] | None = None,
    assert_allowed: Callable[[str], None] | None = None,
) -> ExposureMap:
    """Pure projection. No clock, no network, no LLM, no write. Never raises for a
    data reason — an absent store, an unknown shock, a rights refusal and an
    unresolved id are all TYPED NULLS in the returned value."""
    asof_date = _parse_asof(asof)
    chain_loader = chain_loader or _default_chain_loader
    family_resolver = family_resolver or _default_family_resolver
    assert_allowed = assert_allowed or _default_assert_allowed

    try:
        chains = chain_loader()
    except Exception:
        chains = {}

    chain = chains.get(shock_spec.shock_id)
    provenance = {
        "edge_reader": _EDGE_READER,
        "identity_reader": _IDENTITY_READER,
        "chain_reader": _CHAIN_READER,
        "store_meta": None,
        "engine_version": ENGINE_VERSION,
        "belief_collapse": "max belief_time <= asof per edge_id; ties on computed_at then edge_id",
    }

    if chain is None:
        shock = Shock(
            shock_id=shock_spec.shock_id,
            vocabulary="knowledge/transmission/*.yaml (TXI chain library)",
            title={"en": None, "zh": None}, tier=None,
            declared_by=shock_spec.declared_by, note=shock_spec.note,
        )
        return ExposureMap(
            schema=SCHEMA_ID, asof=asof_date, shock=shock, themes=(),
            unavailable=_unavailable("SHOCK_UNKNOWN", subject_id=shock_spec.shock_id),
            provenance=provenance,
        )

    title = chain.get("title") if isinstance(chain.get("title"), Mapping) else {}
    shock = Shock(
        shock_id=shock_spec.shock_id,
        vocabulary="knowledge/transmission/*.yaml (TXI chain library)",
        title={"en": title.get("en"), "zh": title.get("zh")},
        tier=chain.get("tier"),
        declared_by=shock_spec.declared_by, note=shock_spec.note,
    )

    if not shock_spec.theme_node_ids:
        return ExposureMap(
            schema=SCHEMA_ID, asof=asof_date, shock=shock, themes=(),
            unavailable=_unavailable("NO_THEMES_DECLARED"),
            provenance=provenance,
        )

    try:
        raw_edges = _records(store.read_edges())
        raw_identity = _records(store.read_identity_resolution())
        try:
            meta = store.read_meta()
        except Exception:
            meta = None
        provenance = {**provenance, "store_meta": meta}
    except Exception:
        return ExposureMap(
            schema=SCHEMA_ID, asof=asof_date, shock=shock, themes=(),
            unavailable=_unavailable("STORE_UNAVAILABLE"),
            provenance=provenance,
        )

    edges_by_id, clock_abstentions = _collapse_and_filter_edges(raw_edges, asof_date)
    member_of_by_dst = _index_by_dst(edges_by_id, "MEMBER_OF")
    expresses_by_dst = _index_by_dst(edges_by_id, "EXPRESSES")
    tracks_by_dst = _index_by_dst(edges_by_id, "TRACKS")

    identity_rows: dict[str, Mapping[str, Any]] = {}
    for row in raw_identity:
        node_id = row.get("node_id")
        if node_id is not None:
            identity_rows[str(node_id)] = row

    theme_rows: list[dict[str, Any]] = []
    for theme_id in sorted(set(shock_spec.theme_node_ids)):
        row = _compose_theme(
            theme_id, edges_by_id=edges_by_id, member_of_by_dst=member_of_by_dst,
            expresses_by_dst=expresses_by_dst, tracks_by_dst=tracks_by_dst,
            identity_rows=identity_rows, family_resolver=family_resolver,
            assert_allowed=assert_allowed,
        )
        # Attach clock-mismatch abstentions whose excluded edge terminated directly
        # at this theme node — the surface can then show why that edge is absent.
        own_clock = [
            {k: v for k, v in a.items() if k != "_dst"}
            for a in clock_abstentions if a.get("_dst") == theme_id
        ]
        if own_clock:
            row["abstentions"] = sorted(
                list(row["abstentions"]) + own_clock,
                key=lambda a: (a["code"], a["subject_id"] or ""),
            )
        theme_rows.append(row)

    themes = tuple(
        ThemeExposure(
            theme_node_id=r["theme_node_id"], theme_plane=r["theme_plane"],
            rights_family=r["rights_family"], name=r["name"], state=r["state"],
            unavailable=r["unavailable"], companies=r["companies"],
            company_count=r["company_count"],
            distinct_security_count=r["distinct_security_count"],
            etf_proxies=r["etf_proxies"], abstentions=tuple(r["abstentions"]),
        )
        for r in theme_rows
    )

    return ExposureMap(
        schema=SCHEMA_ID, asof=asof_date, shock=shock, themes=themes,
        unavailable=None, provenance=provenance,
    )


def _shock_json(shock: Shock) -> dict[str, Any]:
    return {
        "shock_id": shock.shock_id, "vocabulary": shock.vocabulary,
        "title": dict(shock.title), "tier": shock.tier,
        "declared_by": shock.declared_by, "note": shock.note,
    }


def _theme_json(theme: ThemeExposure) -> dict[str, Any]:
    return {
        "theme_node_id": theme.theme_node_id, "theme_plane": theme.theme_plane,
        "rights_family": theme.rights_family, "name": dict(theme.name),
        "state": theme.state, "unavailable": theme.unavailable,
        "companies": list(theme.companies) if theme.companies is not None else None,
        "company_count": theme.company_count,
        "distinct_security_count": theme.distinct_security_count,
        "etf_proxies": list(theme.etf_proxies) if theme.etf_proxies is not None else None,
        "abstentions": list(theme.abstentions),
    }


def to_json(exposure_map: ExposureMap) -> dict[str, Any]:
    """The exposure_map.v1 payload as plain JSON-serializable types. Pure and total."""
    return {
        "schema": exposure_map.schema,
        "asof": exposure_map.asof.isoformat(),
        "authority_ceiling": AUTHORITY_CEILING,
        "display_only": True,
        "shock": _shock_json(exposure_map.shock),
        "themes": [_theme_json(t) for t in exposure_map.themes],
        "unavailable": exposure_map.unavailable,
        "provenance": dict(exposure_map.provenance),
    }
