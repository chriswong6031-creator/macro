"""Build nodes / edges / evidence from the live membership documents (masterplan §4.1).

INPUTS — all of them artifacts an owner already publishes; GMI assembles, never scores:

* ``data/{baskets,baskets_china,baskets_china_ths,baskets_hk,baskets_canada,baskets_intl}/membership.json``
* ``config/theme_crosswalk.yml`` (v3 — the TIL vocabulary, extended in place, never forked)
* ``data/baskets_china_ths/concept_map.json`` (同花顺 board → concept code)
* the newest RAW 同花顺 snapshot, passed in by the caller as ``(date, doc)``

EDGES BUILT HERE, and only these:

* ``MEMBER_OF``  company → basket, interval [added, removed)
* ``EXPRESSES``  basket  → theme, from the crosswalk's ``basket_ids`` (US),
  ``cn_basket_ids`` (curated CN) and the deterministic THS join
  (basket.ths_concept → concept_map code ∈ row.ths_concept_ids)
* ``TRACKS``     etf     → basket, where the basket declares an ``etf_proxy``

There is deliberately NO derived company → theme edge. Composing "A is in basket B"
with "basket B expresses theme T" into "A expresses T" would assert a fact no receipt
supports — the evidence grain is membership and expression, and the composition is the
consumer's join, made against evidence it can see.

HONESTY (directive §2C, gate G0.2). A backfill writes every row ``era="reconstruction"``
with ``belief_time`` = the run's own date: the graph never claims to have known these
memberships when they took effect. ``date_provenance`` separates a real dated
changelog entry from the seed CONSTANT every membership document uses for its first-run
members — that constant is where a series begins, not when a company joined a theme.
Nightly runs append only what actually changed, ``era="observed"``.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from lib import config

from . import identity
from .store import ENGINE_VERSION, RESERVED_EDGE_FIELDS

log = logging.getLogger(__name__)

SUITES: tuple[str, ...] = (
    "baskets", "baskets_china", "baskets_china_ths", "baskets_hk",
    "baskets_canada", "baskets_intl",
)
US_SUITE = "baskets"
CN_CURATED_SUITE = "baskets_china"
THS_SUITE = "baskets_china_ths"

#: Member rows are keyed by ``ticker`` in every family today; ``symbol`` is accepted
#: because the US suite's own history used it and a family that switches back must not
#: silently produce zero members. Detected per family from the data, never assumed.
MEMBER_SYMBOL_KEYS: tuple[str, ...] = ("symbol", "ticker")

#: W1b's only confidence basis: the edge is exactly as good as the membership document
#: it came from. A bare number without a basis is forbidden (§4.1).
CONFIDENCE_BASIS = "membership_doc.v1"

#: (internal_ok, display_ok, redistribution_ok)
LICENSE_HOUSE = (True, True, True)
LICENSE_VENDOR = (True, True, False)

#: Suites whose membership document is machine-maintained from a vendor scrape.
VENDOR_SUITES: frozenset[str] = frozenset({THS_SUITE})

#: Edge fields compared when deciding whether tonight's view differs from the stored
#: belief. src/dst/type/valid_from are already inside edge_id, so a change in any of
#: them mints a different edge rather than updating this one.
MATERIAL_EDGE_FIELDS: tuple[str, ...] = (
    "valid_to", "evidence_time", "era", "source_class", "date_provenance",
    "evidence_refs", "confidence_basis",
)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def utc_now_stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _text(v: object) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _is_date(v: object) -> bool:
    s = _text(v)
    if not s:
        return False
    try:
        date.fromisoformat(s)
    except ValueError:
        return False
    return True


def evidence_id_for(kind: str, source_ref: str, published_at: str) -> str:
    digest = hashlib.sha1(f"{kind}|{source_ref}|{published_at}".encode()).hexdigest()
    return "ev:" + digest[:16]


def edge_id_for(edge_type: str, src: str, dst: str, valid_from: str) -> str:
    return f"{edge_type.lower()}:{src}->{dst}@{valid_from}"


def _etf_proxies(value: object) -> list[str]:
    """The ETF symbols a basket declares as its proxy — one, several, or none.

    ``etf_proxy`` is a bare string on 75 of the 76 baskets that carry one, and a LIST
    on ``defensives`` (['XLP','XLU']). A str()-and-hope reading turns that list into the
    literal symbol "['XLP', 'XLU']", which then fails the id grammar — and, before this
    was handled per-item, took the whole US family's 49 baskets and 1,038 members down
    with it. Both shapes are real; both are read.
    """
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple)) else [value]
    return [s for s in (_text(v) for v in items) if s]


def _doc_published_at(doc: dict) -> str | None:
    """The membership document's own date: ``version`` when date-shaped, else
    ``curated``, else ``seed_date``. Never today — the document's date is evidence
    time, and stamping it with the run date would erase the difference."""
    for key in ("version", "curated", "seed_date"):
        if _is_date(doc.get(key)):
            return str(doc[key]).strip()
    return None


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class Materialization:
    """One computed view of the graph: rows, plus what the run learned about coverage."""

    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    per_suite: dict[str, dict] = field(default_factory=dict)
    unknown_ths_codes: list[str] = field(default_factory=list)
    ths_unmapped_concept_count: int = 0
    skipped_suites: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class _Builder:
    def __init__(self, *, data_dir: Path, crosswalk_path: Path, era: str,
                 belief_time: str, computed_at: str,
                 raw_snapshot: tuple[str, dict] | None) -> None:
        self.data_dir = data_dir
        self.crosswalk_path = crosswalk_path
        self.era = era
        self.belief_time = belief_time
        self.computed_at = computed_at
        self.raw_snapshot = raw_snapshot
        self.breaks = identity.load_breaks()
        self.out = Materialization()
        self._nodes: dict[str, dict] = {}
        self._edges: dict[str, dict] = {}
        self._evidence: dict[str, dict] = {}

    # -- emitters ----------------------------------------------------------

    def _node(self, node_id: str, *, kind: str, market_scope: str, provenance: str,
              name_en: str | None = None, name_zh: str | None = None,
              tier: str | None = None, external_ids: dict | None = None,
              identity_epoch: int = 1) -> str:
        prior = self._nodes.get(node_id)
        if prior is not None:
            # First writer wins, except that a later sighting may FILL a missing name:
            # the THS document has 中文 names the curated CN document does not, and a
            # node that appears in both should carry both.
            if prior.get("name_en") is None and name_en:
                prior["name_en"] = name_en
            if prior.get("name_zh") is None and name_zh:
                prior["name_zh"] = name_zh
            return node_id
        self._nodes[node_id] = {
            "node_id": node_id, "kind": kind,
            "name_en": _text(name_en), "name_zh": _text(name_zh),
            "market_scope": market_scope, "tier": tier,
            "status": "canonical", "merged_into": None,
            "birth_date": None, "retire_date": None,
            "identity_epoch": int(identity_epoch),
            "external_ids": json.dumps(external_ids or {}, ensure_ascii=False,
                                       sort_keys=True),
            "provenance": provenance,
            "computed_at": self.computed_at, "engine_version": ENGINE_VERSION,
        }
        return node_id

    def _evidence_ref(self, *, kind: str, source_ref: str, published_at: str,
                      licensing: tuple[bool, bool, bool],
                      effective_at: str | None = None,
                      retention: str | None = None) -> str:
        eid = evidence_id_for(kind, source_ref, published_at)
        if eid not in self._evidence:
            internal, display, redistribution = licensing
            self._evidence[eid] = {
                "evidence_id": eid, "kind": kind, "published_at": published_at,
                "effective_at": effective_at, "source_ref": source_ref,
                "licensing_internal_ok": bool(internal),
                "licensing_display_ok": bool(display),
                "licensing_redistribution_ok": bool(redistribution),
                "retention": retention, "computed_at": self.computed_at,
            }
        return eid

    def _edge(self, *, edge_type: str, src: str, dst: str, valid_from: str,
              valid_to: str | None, evidence_time: str, source_class: str,
              date_provenance: str, evidence_refs: list[str]) -> None:
        eid = edge_id_for(edge_type, src, dst, valid_from)
        if eid in self._edges:
            return
        row = {
            "edge_id": eid, "type": edge_type, "src": src, "dst": dst,
            "valid_from": valid_from, "valid_to": valid_to,
            "evidence_time": evidence_time, "belief_time": self.belief_time,
            "era": self.era, "source_class": source_class,
            "date_provenance": date_provenance,
            "evidence_refs": list(evidence_refs),
            "confidence_basis": CONFIDENCE_BASIS,
            "computed_at": self.computed_at, "engine_version": ENGINE_VERSION,
        }
        # The exposure axes are W2's measurement; declared null here so the columns
        # exist and nobody reads an absent column as a zero.
        for f in RESERVED_EDGE_FIELDS:
            row[f] = None
        self._edges[eid] = row

    # -- inputs ------------------------------------------------------------

    def _membership(self, suite: str) -> dict | None:
        p = self.data_dir / suite / "membership.json"
        if not p.exists():
            self.out.skipped_suites[suite] = "membership.json missing"
            return None
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            self.out.skipped_suites[suite] = f"unreadable: {exc}"
            log.warning("theme_graph: %s membership.json unreadable (%s)", suite, exc)
            return None
        if not isinstance(doc, dict) or not isinstance(doc.get("baskets"), dict):
            self.out.skipped_suites[suite] = "no baskets object"
            return None
        return doc

    @staticmethod
    def _symbol_key(suite: str, baskets: dict) -> str:
        """Which key member rows carry their symbol under — DETECTED, not assumed.

        A family carrying neither is refused rather than silently yielding zero
        members: a suite that quietly contributes nothing looks exactly like a suite
        that is genuinely empty.
        """
        for basket in baskets.values():
            for member in basket.get("members") or []:
                for key in MEMBER_SYMBOL_KEYS:
                    if key in member:
                        return key
        raise ValueError(
            f"membership family {suite!r}: member rows carry none of "
            f"{list(MEMBER_SYMBOL_KEYS)} — refusing to build zero edges from it")

    # -- families ----------------------------------------------------------

    def build_family(self, suite: str) -> None:
        doc = self._membership(suite)
        if doc is None:
            return
        baskets = doc["baskets"]
        market = identity.market_for_suite(suite)
        seed_date = _text(doc.get("seed_date"))
        published_at = _doc_published_at(doc)
        if not published_at:
            self.out.skipped_suites[suite] = "membership.json carries no usable date"
            log.warning("theme_graph: %s has no date field — skipped (an undated "
                        "receipt is not evidence)", suite)
            return
        symbol_key = self._symbol_key(suite, baskets)
        vendor = suite in VENDOR_SUITES
        doc_ev = self._evidence_ref(
            kind="scrape" if vendor else "operator_curation",
            source_ref=f"data/{suite}/membership.json",
            published_at=published_at,
            licensing=LICENSE_VENDOR if vendor else LICENSE_HOUSE)
        source_class = "scrape" if vendor else "curated"

        raw_board_members = self._raw_board_index() if suite == THS_SUITE else {}
        raw_ev = self._raw_snapshot_evidence() if suite == THS_SUITE else None

        n_companies, n_member_edges, n_tracks = set(), 0, 0
        for bid, basket in baskets.items():
            b_node = identity.basket_node_id(suite, bid)
            ths_concept = _text(basket.get("ths_concept"))
            ext = {"suite": suite, "basket_id": str(bid)}
            code = self._ths_code(ths_concept) if ths_concept else None
            if code:
                ext["ths_code"] = code
            self._node(b_node, kind="basket", market_scope=market,
                       provenance=f"membership_doc:{suite}",
                       name_en=basket.get("name"), name_zh=basket.get("name_zh"),
                       external_ids=ext)

            # TRACKS — an ETF proxy is a tracking relationship, not membership.
            created = _text(basket.get("created")) or seed_date
            for etf in _etf_proxies(basket.get("etf_proxy")):
                if not _is_date(created):
                    break
                try:
                    e_id = identity.etf_node_id(etf)
                except ValueError as exc:
                    log.warning("theme_graph: %s/%s etf_proxy skipped (%s)",
                                suite, bid, exc)
                    continue
                # No name_en: the document carries an etf_proxy_note, which is a
                # note about the proxy, not the fund's name. G0.9 — a node without
                # a real name from a real vocabulary carries none.
                e_node = self._node(e_id, kind="etf", market_scope=market,
                                    provenance=f"membership_doc:{suite}",
                                    external_ids={"symbol": etf.upper()})
                self._edge(edge_type="TRACKS", src=e_node, dst=b_node,
                           valid_from=created, valid_to=None,
                           evidence_time=published_at, source_class=source_class,
                           date_provenance=("seed_constant" if created == seed_date
                                            else "curated_changelog"),
                           evidence_refs=[doc_ev])
                n_tracks += 1

            board_members = raw_board_members.get(ths_concept or "", frozenset())
            for member in basket.get("members") or []:
                symbol = member.get(symbol_key)
                added = _text(member.get("added"))
                if not symbol or not _is_date(added):
                    continue
                try:
                    c_node = identity.company_node_id(suite, symbol, breaks=self.breaks)
                except ValueError as exc:
                    log.warning("theme_graph: %s/%s member skipped (%s)", suite, bid, exc)
                    continue
                self._node(c_node, kind="company", market_scope=market,
                           provenance=f"membership_doc:{suite}",
                           name_en=member.get("name"), name_zh=member.get("name_zh"),
                           external_ids={"symbol": str(symbol).strip().upper()},
                           identity_epoch=identity.identity_epoch(
                               market, symbol, breaks=self.breaks))
                n_companies.add(c_node)

                refs = [doc_ev]
                # CORROBORATION, not replacement: a member the raw vendor dump also
                # shows gets a SECOND receipt. Nothing nets — the two rows coexist and
                # date_provenance still describes where valid_from came from.
                if raw_ev and str(symbol) in board_members:
                    refs.append(raw_ev)
                removed = _text(member.get("removed"))
                self._edge(
                    edge_type="MEMBER_OF", src=c_node, dst=b_node,
                    valid_from=added,
                    valid_to=removed if _is_date(removed) else None,
                    evidence_time=published_at, source_class=source_class,
                    date_provenance=("seed_constant" if seed_date and added == seed_date
                                     else "curated_changelog"),
                    evidence_refs=refs)
                n_member_edges += 1

        self.out.per_suite[suite] = {
            "baskets": len(baskets), "companies": len(n_companies),
            "member_edges": n_member_edges, "tracks_edges": n_tracks,
            "membership_published_at": published_at,
            "seed_constant": seed_date,
        }

    # -- THS concept map + raw snapshot ------------------------------------

    def _concept_map(self) -> dict[str, str]:
        if not hasattr(self, "_cmap"):
            p = self.data_dir / THS_SUITE / "concept_map.json"
            doc = {}
            if p.exists():
                try:
                    doc = json.loads(p.read_text(encoding="utf-8"))
                except Exception as exc:  # noqa: BLE001
                    log.warning("theme_graph: concept_map.json unreadable (%s)", exc)
            self._cmap = {str(k): str(v) for k, v in (doc.get("map") or {}).items()}
            self._cmap_asof = _text(doc.get("asof"))
        return self._cmap

    def _ths_code(self, concept: str | None) -> str | None:
        return self._concept_map().get(concept or "") if concept else None

    def _raw_board_index(self) -> dict[str, frozenset[str]]:
        """{board_zh_name: {ticker, …}} from the newest raw 同花顺 dump."""
        if self.raw_snapshot is None:
            return {}
        _snap_date, doc = self.raw_snapshot
        out: dict[str, frozenset[str]] = {}
        for board, members in (doc or {}).items():
            if isinstance(members, list):
                out[str(board)] = frozenset(
                    str(m.get("ticker")) for m in members
                    if isinstance(m, dict) and m.get("ticker"))
        return out

    def _raw_snapshot_evidence(self) -> str | None:
        if self.raw_snapshot is None:
            return None
        snap_date, _doc = self.raw_snapshot
        return self._evidence_ref(
            kind="scrape",
            source_ref=f"data/{THS_SUITE}/snapshots/{snap_date}.json",
            published_at=snap_date, licensing=LICENSE_VENDOR)

    # -- crosswalk ---------------------------------------------------------

    def build_crosswalk(self) -> None:
        doc = yaml.safe_load(self.crosswalk_path.read_text(encoding="utf-8")) or {}
        rows = doc.get("themes") or []
        xwalk_date = _text(doc.get("date")) or _text(doc.get("updated"))
        if not _is_date(xwalk_date):
            log.warning("theme_graph: crosswalk carries no usable date — EXPRESSES "
                        "edges skipped (an undated mapping is not dated evidence)")
            return
        # Repo-relative source_ref (not the resolved path): the receipt names the
        # artifact, so evidence_ids stay stable across checkouts and fixtures.
        xwalk_ev = self._evidence_ref(
            kind="operator_curation", source_ref="config/theme_crosswalk.yml",
            published_at=xwalk_date, licensing=LICENSE_HOUSE)
        cmap = self._concept_map()
        cmap_ev = None
        if self._cmap_asof:
            cmap_ev = self._evidence_ref(
                kind="scrape", source_ref=f"data/{THS_SUITE}/concept_map.json",
                published_at=self._cmap_asof, licensing=LICENSE_VENDOR)
        known_codes = set(cmap.values())
        # basket node id → the THS code it carries, for the deterministic join below.
        ths_code_by_node: dict[str, str] = {}
        for node_id, node in self._nodes.items():
            if node["kind"] != "basket":
                continue
            ext = json.loads(node["external_ids"])
            if ext.get("ths_code"):
                ths_code_by_node[node_id] = ext["ths_code"]

        mapped_codes: set[str] = set()
        unknown: set[str] = set()
        n_expresses = 0
        for row in rows:
            theme_id = _text(row.get("id"))
            if not theme_id:
                continue
            t_node = _text(row.get("theme_node_id")) or identity.theme_node_id(theme_id)
            self._node(t_node, kind="theme", market_scope="global", tier="theme",
                       provenance="crosswalk:config/theme_crosswalk.yml",
                       name_en=row.get("name_en"), name_zh=row.get("name_zh"),
                       external_ids={"foresight_id": _text(row.get("foresight_id")) or theme_id})

            pairs: list[tuple[str, list[str]]] = [
                (US_SUITE, [str(b) for b in (row.get("basket_ids") or [])]),
                (CN_CURATED_SUITE, [str(b) for b in (row.get("cn_basket_ids") or [])]),
            ]
            for suite, basket_ids in pairs:
                for bid in basket_ids:
                    b_node = identity.basket_node_id(suite, bid)
                    if b_node not in self._nodes:
                        # The crosswalk names a basket this family does not carry (a
                        # sparse checkout, or a basket retired since the mapping was
                        # written). Skipping is honest; minting the node would invent a
                        # basket out of a mapping.
                        continue
                    self._edge(edge_type="EXPRESSES", src=b_node, dst=t_node,
                               valid_from=xwalk_date, valid_to=None,
                               evidence_time=xwalk_date, source_class="curated",
                               date_provenance="crosswalk", evidence_refs=[xwalk_ev])
                    n_expresses += 1

            codes = [str(c) for c in (row.get("ths_concept_ids") or [])]
            for code in codes:
                if code not in known_codes:
                    # Weekly concept drift: the board was renamed, merged or retired
                    # since the mapping was adjudicated. Collected and reported in
                    # _meta.json, edge skipped, NEVER fatal.
                    unknown.add(code)
                    continue
                mapped_codes.add(code)
            wanted = set(codes)
            for b_node, code in ths_code_by_node.items():
                if code not in wanted:
                    continue
                refs = [xwalk_ev] + ([cmap_ev] if cmap_ev else [])
                self._edge(edge_type="EXPRESSES", src=b_node, dst=t_node,
                           valid_from=xwalk_date, valid_to=None,
                           evidence_time=xwalk_date, source_class="curated",
                           date_provenance="crosswalk", evidence_refs=refs)
                n_expresses += 1

        self.out.unknown_ths_codes = sorted(unknown)
        self.out.ths_unmapped_concept_count = sum(
            1 for code in cmap.values() if code not in mapped_codes)
        self.out.per_suite["crosswalk"] = {
            "themes": len(rows), "expresses_edges": n_expresses,
            "published_at": xwalk_date,
            "ths_codes_mapped": len(mapped_codes),
            "ths_codes_unknown": len(unknown),
        }

    # -- drive -------------------------------------------------------------

    def run(self) -> Materialization:
        for suite in SUITES:
            try:
                self.build_family(suite)
            except ValueError as exc:
                self.out.skipped_suites[suite] = str(exc)
                log.warning("theme_graph: %s skipped (%s)", suite, exc)
        self.build_crosswalk()
        self.out.nodes = [self._nodes[k] for k in sorted(self._nodes)]
        self.out.edges = [self._edges[k] for k in sorted(self._edges)]
        self.out.evidence = [self._evidence[k] for k in sorted(self._evidence)]
        return self.out


def build(*, era: str, belief_time: str | None = None,
          computed_at: str | None = None,
          data_dir: Path | None = None,
          crosswalk_path: Path | None = None,
          raw_snapshot: tuple[str, dict] | None = None) -> Materialization:
    """Compute the whole graph view. Pure: reads inputs, writes nothing."""
    if era not in ("reconstruction", "observed"):
        raise ValueError(f"era must be reconstruction|observed, got {era!r}")
    root = Path(__file__).resolve().parent.parent.parent
    return _Builder(
        data_dir=data_dir or config.data_dir(),
        crosswalk_path=crosswalk_path or (root / "config" / "theme_crosswalk.yml"),
        era=era,
        belief_time=belief_time or utc_today(),
        computed_at=computed_at or utc_now_stamp(),
        raw_snapshot=raw_snapshot,
    ).run()


# ---------------------------------------------------------------------------
# Nightly diff
# ---------------------------------------------------------------------------

def _material(row: dict) -> tuple:
    out = []
    for f in MATERIAL_EDGE_FIELDS:
        v = row.get(f)
        if f == "evidence_refs":
            v = tuple(sorted(str(x) for x in (list(v) if v is not None else [])))
        elif v is not None and not isinstance(v, (str, bool, int, float)):
            v = str(v)
        out.append(v)
    return tuple(out)


def changed_edges(computed: list[dict], stored: pd.DataFrame) -> list[dict]:
    """The computed rows that are NEW or that differ materially from the stored belief.

    An edge present in the store but absent from tonight's computation is deliberately
    NOT closed here: a membership document records a removal as a dated ``removed``
    field, which re-computes as the SAME edge_id with ``valid_to`` set and lands through
    the diff below. An edge vanishing from the input entirely means the input lost it —
    a truncated scrape, a sparse checkout — and fabricating an exit from an absence is
    exactly the failure the seeder's shrink guard exists to prevent.
    """
    if stored is None or stored.empty:
        return list(computed)
    prior = {str(r["edge_id"]): _material(r) for r in stored.to_dict("records")}
    return [row for row in computed
            if prior.get(str(row["edge_id"])) != _material(row)]
