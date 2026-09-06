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

from . import capability as capability_rule
from . import identity, identity_resolution, local_sources, rights
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

#: W3A: the Finviz tree's own claim, at the tree's own grain and parser version.
FINVIZ_CONFIDENCE_BASIS = "finviz_tree.v1"

#: (internal_ok, display_ok, redistribution_ok). Kept as the historical constants the
#: W1b rows were minted from; NEW receipts derive their booleans from the rights
#: registry instead (§9.4) — see :func:`_licensing`. A tuple in code cannot know that a
#: rights review moved last week, and a receipt that claims display-ok because a constant
#: said so is exactly the drift the registry-as-single-authority rule closes.
LICENSE_HOUSE = (True, True, True)
LICENSE_VENDOR = (True, True, False)

#: Suites whose membership document is machine-maintained from a vendor scrape.
VENDOR_SUITES: frozenset[str] = frozenset({THS_SUITE})

#: Membership-suite → rights family, the join key into config/theme_sources.yml.
SUITE_RIGHTS_FAMILY: dict[str, str] = {
    "baskets": "mastermind_curated",
    "baskets_china": "mastermind_curated",
    "baskets_hk": "mastermind_curated",
    "baskets_canada": "mastermind_curated",
    "baskets_intl": "mastermind_curated",
    THS_SUITE: "ths_concepts",
}

#: Source families of the local-theme plane.
FINVIZ_FAMILY = "finviz_themes"
THS_FAMILY = "ths_concepts"

#: A nightly diff that would close more than this share of a source family's LIVE
#: memberships refuses. The SECOND wall, behind the refresh contract's own interlocks:
#: a hand-edited tree that never went through a refresh run reaches the store through
#: this path, and an append-only store makes a mass closure expensive to explain and
#: impossible to un-see. Passing --allow-source-shrink <family> is how a real vendor
#: restructure gets through — deliberately, with a name attached. 0.10 matches the
#: refresh contract's §9.2-derived wall EXACTLY, and for the same reason: the canonical
#: parser/hand-edit catastrophe (last-member-of-every-subtheme truncation) closes
#: 268/2,339 = 11.5% — a 25% wall promoted it silently (diff-review F2); observed
#: genuine churn is ~1.1% per 7 weeks, so 10% stays ≥4× any plausible gap's drift.
MAX_SOURCE_SHRINK = 0.10

#: Edge fields compared when deciding whether tonight's view differs from the stored
#: belief — the ASSERTION, and only the assertion. src/dst/type/valid_from are already
#: inside edge_id, so a change in any of them mints a different edge rather than
#: updating this one.
#:
#: `era` and `belief_time` are deliberately NOT here. They describe how and when the row
#: was produced, not what it claims about the world, and including `era` made the first
#: nightly after a backfill re-append the ENTIRE graph: every reconstruction row differed
#: from its observed recomputation on that label alone, so an unchanged night looked like
#: a total rewrite. A reconstruction row stays the current belief until the fact itself
#: moves — which is the whole point of storing beliefs rather than snapshots.
MATERIAL_EDGE_FIELDS: tuple[str, ...] = (
    "valid_to", "evidence_time", "source_class", "date_provenance",
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
    #: Capability side-car rows (re-derived every build, never a node column — §9.3).
    capability: list[dict] = field(default_factory=list)
    #: GMI -> Data OS identity resolution bridge rows (V4-D2A) — re-derived every
    #: build, one row per company-kind node, never a node column (same reasoning as
    #: capability: the master's coverage can only grow, and a write-once row would be
    #: a one-way ratchet).
    identity_resolution: list[dict] = field(default_factory=list)
    #: The local-theme plane's own report: ladder, counts, and the company-mint
    #: resolution table the receipt asserts against (§9.13).
    local_plane: dict[str, dict] = field(default_factory=dict)
    #: THS concept NAMES a membership document carries that the vendor's concept map no
    #: longer resolves to a code. Report-only, exactly like unknown_ths_codes: an edge is
    #: minted on resolution, never on a name we could not resolve.
    unknown_ths_concepts: list[str] = field(default_factory=list)
    #: V4-D2B3 (R-D2B3-4 / R-A1 / R-A6) — one typed refusal per structurally-suppressed
    #: company mint: an entity-kind conflict (a company symbol also minted as an
    #: etf-kind node in THIS SAME build) or a re-mint of a node whose latest lifecycle
    #: status is retired/merged. Never a raise (R-A6): the nightly bake must not become
    #: an outage weapon. Structural evidence only — no ticker literals anywhere in the
    #: logic that produces this list.
    company_mint_refusals: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def _licensing(family: str | None) -> tuple[bool, bool, bool]:
    """Mint-time licensing booleans DERIVED from the rights registry (§9.4).

    An unknown or unmapped family mints the most restrictive readable tuple. The receipt
    still exists — an edge must be able to cite it — but it claims nothing.
    """
    if not family:
        return (True, False, False)
    return rights.licensing_for_family(family)


class _Builder:
    def __init__(self, *, data_dir: Path, crosswalk_path: Path, era: str,
                 belief_time: str, computed_at: str,
                 raw_snapshot: tuple[str, dict] | None,
                 ths_history=None,
                 finviz_seed_path: Path | None = None,
                 finviz_history_path: Path | None = None,
                 finviz_live_tree_path: Path | None = None,
                 substrate_dir: Path | None = None,
                 retired_node_ids: frozenset[str] | None = None) -> None:
        self.data_dir = data_dir
        self.crosswalk_path = crosswalk_path
        self.era = era
        self.belief_time = belief_time
        self.computed_at = computed_at
        self.raw_snapshot = raw_snapshot
        # D2C: handed in by the owning membership-PIT reader.  Materialization
        # remains a pure consumer and never discovers or writes the owner store.
        self.ths_history = ths_history
        self.finviz_seed_path = finviz_seed_path
        self.finviz_history_path = finviz_history_path
        self.finviz_live_tree_path = finviz_live_tree_path
        self.substrate_dir = substrate_dir or data_dir
        self.breaks = identity.load_breaks()
        # V4-D2B3 (R-A6): materialize stays PURE — it reads no store. Lifecycle state
        # is read by the impure orchestrator (scripts/build_theme_graph.py) and handed
        # in here as a plain frozenset of node_ids whose latest lifecycle status is
        # retired/merged.
        self.retired_node_ids: frozenset[str] = retired_node_ids or frozenset()
        self.out = Materialization()
        self._nodes: dict[str, dict] = {}
        self._edges: dict[str, dict] = {}
        self._evidence: dict[str, dict] = {}

    # -- emitters ----------------------------------------------------------

    def _node(self, node_id: str, *, kind: str, market_scope: str, provenance: str,
              name_en: str | None = None, name_zh: str | None = None,
              tier: str | None = None, external_ids: dict | None = None,
              identity_epoch: int = 1, birth_date: str | None = None,
              source_meta: dict | None = None) -> str:
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
            "birth_date": _text(birth_date), "retire_date": None,
            "identity_epoch": int(identity_epoch),
            "external_ids": json.dumps(external_ids or {}, ensure_ascii=False,
                                       sort_keys=True),
            "provenance": provenance,
            "computed_at": self.computed_at, "engine_version": ENGINE_VERSION,
            # Null for every node that is not source-local. The column exists on all of
            # them because the column set IS the contract.
            "source_meta": (json.dumps(source_meta, ensure_ascii=False, sort_keys=True)
                            if source_meta else None),
        }
        return node_id

    def _evidence_ref(self, *, kind: str, source_ref: str, published_at: str,
                      licensing: tuple[bool, bool, bool],
                      effective_at: str | None = None,
                      retention: str | None = None,
                      provider: str | None = None,
                      claim_type: str | None = None) -> str:
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
                # The corroboration class ships EMPTY in W3A: no external classifier is
                # ingested, so these are null on every row the builder mints.
                "provider": provider, "claim_type": claim_type,
            }
        return eid

    def _era_for(self, observed_on: str | None) -> str:
        """``observed`` only when the source was observed on the build's own date.

        A snapshot source is ingested from DATED VINTAGES, and a vintage taken seven
        weeks ago is reconstructed history no matter which mode tonight's run is in.
        The override only ever downgrades observed→reconstruction — the direction that
        cannot make present knowledge look historically known (G0.2).
        """
        if self.era == "reconstruction":
            return "reconstruction"
        return "observed" if observed_on == self.belief_time else "reconstruction"

    def _edge(self, *, edge_type: str, src: str, dst: str, valid_from: str,
              valid_to: str | None, evidence_time: str, source_class: str,
              date_provenance: str, evidence_refs: list[str],
              confidence_basis: str = CONFIDENCE_BASIS,
              era: str | None = None) -> None:
        eid = edge_id_for(edge_type, src, dst, valid_from)
        if eid in self._edges:
            return
        row = {
            "edge_id": eid, "type": edge_type, "src": src, "dst": dst,
            "valid_from": valid_from, "valid_to": valid_to,
            "evidence_time": evidence_time, "belief_time": self.belief_time,
            "era": era or self.era, "source_class": source_class,
            "date_provenance": date_provenance,
            "evidence_refs": list(evidence_refs),
            "confidence_basis": confidence_basis,
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
            licensing=_licensing(SUITE_RIGHTS_FAMILY.get(suite)))
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

    def _ths_doc_coverage_fields(self) -> dict:
        """Coverage disclosures consumers already cite from ``per_suite.baskets_china_ths``.

        ``membership_published_at`` / ``seed_constant`` / ``tracks_edges`` remain
        readable from today's membership doc even though MEMBER_OF now comes from
        the PIT store — dropping them is a silent coverage-disclosure regression.
        TRACKS stay honestly 0: the THS doc carries no top-level ``etfs``.
        """
        doc = self._membership(THS_SUITE)
        if doc is None:
            return {
                "membership_published_at": None,
                "seed_constant": None,
                "tracks_edges": 0,
            }
        return {
            "membership_published_at": _doc_published_at(doc),
            "seed_constant": _text(doc.get("seed_date")),
            "tracks_edges": 0,
        }

    def _ths_per_suite(self, **fields) -> dict:
        """Full THS ``per_suite`` key set — both branches emit every key."""
        base = {
            "baskets": 0,
            "companies": 0,
            "member_edges": 0,
            "tracks_edges": 0,
            "membership_published_at": None,
            "seed_constant": None,
            "closed_member_edges": 0,
            "membership_pit_rows": 0,
            "excluded_source_shapes": [],
            "skipped_unidentifiable": [],
            "unlabelled_nodes": 0,
            "note": None,
        }
        base.update(self._ths_doc_coverage_fields())
        base.update(fields)
        return base

    def build_ths_membership_history(self) -> None:
        """Emit THS memberships solely from the owner PIT history.

        The owner store's ``ths_concept_dump`` rows deliberately do not enter the
        graph: their concept-to-basket resolution used the current map, so a dated
        graph edge would backdate a mapping we do not historically possess.  An empty
        history therefore means unavailable membership coverage, never a fallback to
        today's ``membership.json``.
        """
        # Names/labels are NOT owned by the PIT history (it carries no basket
        # name_en/name_zh) — mint basket + company nodes with their labels from
        # the current membership document FIRST (first-writer-wins via _node),
        # independently of whether the PIT history has any rows for them. This
        # keeps THS concept baskets and THS-only companies bilingual even though
        # build_family(THS_SUITE) is deliberately skipped for MEMBER_OF/TRACKS,
        # and keeps the basket nodes (and therefore the EXPRESSES plane +
        # crosswalk) alive when the PIT history is empty/absent.
        self._seed_ths_labels()

        history = self.ths_history
        rows = (history.to_dict("records") if hasattr(history, "to_dict")
                else list(history or ()))
        membership_rows = [row for row in rows
                           if _text(row.get("source_shape")) == "membership"]
        excluded_shapes = sorted({
            _text(row.get("source_shape")) or "unknown" for row in rows
            if _text(row.get("source_shape")) != "membership"
        })
        if not membership_rows:
            self.out.per_suite[THS_SUITE] = self._ths_per_suite(
                membership_pit_rows=0,
                excluded_source_shapes=excluded_shapes,
                note="no historically receipted membership-shape THS snapshots",
            )
            return

        # Shape filter lives inside ths_membership_intervals (default membership-only).
        intervals = local_sources.ths_membership_intervals(rows)
        basket_ids = sorted({iv.basket_id for iv in intervals})
        companies: set[str] = set()
        n_closed = 0
        n_edges = 0
        skipped_unidentifiable: list[str] = []
        for basket_id in basket_ids:
            self._node(
                identity.basket_node_id(THS_SUITE, basket_id),
                kind="basket", market_scope="cn",
                provenance=f"membership_history:{THS_SUITE}",
                external_ids={"suite": THS_SUITE, "basket_id": basket_id},
            )

        for iv in intervals:
            try:
                company = identity.company_node_id(THS_SUITE, iv.ticker, breaks=self.breaks)
            except ValueError as exc:
                log.warning("theme_graph: THS PIT %s/%s skipped (%s)",
                            iv.basket_id, iv.ticker, exc)
                skipped_unidentifiable.append(f"{iv.basket_id}/{iv.ticker}")
                continue
            self._node(
                company, kind="company", market_scope="cn",
                provenance=f"membership_history:{THS_SUITE}",
                external_ids={"symbol": iv.ticker.upper()},
                identity_epoch=identity.identity_epoch("cn", iv.ticker, breaks=self.breaks),
            )
            companies.add(company)
            opening = self._evidence_ref(
                kind="scrape",
                source_ref=(f"data/{THS_SUITE}/membership_history.parquet@"
                            f"{iv.valid_from}"),
                published_at=iv.valid_from, licensing=_licensing(THS_FAMILY),
            )
            refs = [opening]
            if iv.closed_by:
                refs.append(self._evidence_ref(
                    kind="scrape",
                    source_ref=(f"data/{THS_SUITE}/membership_history.parquet@"
                                f"{iv.closed_by}"),
                    published_at=iv.closed_by, licensing=_licensing(THS_FAMILY),
                ))
                n_closed += 1
            self._edge(
                edge_type="MEMBER_OF", src=company,
                dst=identity.basket_node_id(THS_SUITE, iv.basket_id),
                valid_from=iv.valid_from, valid_to=iv.valid_to,
                evidence_time=iv.closed_by or iv.valid_from,
                source_class="scrape", date_provenance="membership_pit",
                evidence_refs=refs, confidence_basis="membership_pit.ths.v1",
                era=self._era_for(iv.closed_by or iv.valid_from),
            )
            n_edges += 1

        # PIT carries no labels: a company/basket present only in history and absent
        # from today's membership.doc is minted without name_en/name_zh. Print the
        # gap rather than hide it (m4).
        unlabelled = 0
        for node_id in list(companies) + [
                identity.basket_node_id(THS_SUITE, bid) for bid in basket_ids]:
            node = self._nodes.get(node_id) or {}
            if not node.get("name_en") and not node.get("name_zh"):
                unlabelled += 1

        self.out.per_suite[THS_SUITE] = self._ths_per_suite(
            baskets=len(basket_ids), companies=len(companies),
            member_edges=n_edges, closed_member_edges=n_closed,
            membership_pit_rows=len(membership_rows),
            excluded_source_shapes=excluded_shapes,
            skipped_unidentifiable=skipped_unidentifiable,
            unlabelled_nodes=unlabelled,
        )

    def _seed_ths_labels(self) -> None:
        """Mint THS basket/company nodes with EN/ZH labels from membership.json.

        Label-only: no MEMBER_OF/TRACKS edges are emitted here (those stay owned
        solely by the PIT history per :meth:`build_ths_membership_history`'s own
        docstring) — this exists only so THS nodes carry the same bilingual
        labels ``build_family`` would have given them.
        """
        doc = self._membership(THS_SUITE)
        if doc is None:
            return
        baskets = doc.get("baskets") or {}
        if not baskets:
            return
        try:
            symbol_key = self._symbol_key(THS_SUITE, baskets)
        except ValueError:
            symbol_key = "symbol"
        for bid, basket in baskets.items():
            self._node(
                identity.basket_node_id(THS_SUITE, bid),
                kind="basket", market_scope="cn",
                provenance=f"membership_doc:{THS_SUITE}",
                name_en=basket.get("name"), name_zh=basket.get("name_zh"),
                external_ids={"suite": THS_SUITE, "basket_id": str(bid)},
            )
            for member in basket.get("members") or []:
                symbol = member.get(symbol_key)
                if not symbol:
                    continue
                try:
                    c_node = identity.company_node_id(THS_SUITE, symbol, breaks=self.breaks)
                except ValueError:
                    continue
                self._node(
                    c_node, kind="company", market_scope="cn",
                    provenance=f"membership_doc:{THS_SUITE}",
                    name_en=member.get("name"), name_zh=member.get("name_zh"),
                    external_ids={"symbol": str(symbol).strip().upper()},
                    identity_epoch=identity.identity_epoch(
                        "cn", symbol, breaks=self.breaks),
                )

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
            published_at=snap_date, licensing=_licensing(THS_FAMILY))

    # -- local-theme plane: Finviz subthemes --------------------------------

    def _finviz_paths(self) -> tuple[Path, Path, Path]:
        """Seed, tape and live tree — all resolved RELATIVE TO ``data_dir``.

        The seed lives beside the data directory rather than inside it (it is a repo
        artifact, committed once), so it resolves through ``data_dir.parent`` — which is
        the repo root in production and the fixture root under a tmp data dir. Anchoring
        it to the real repo root instead would make every fixture build silently ingest
        the live 268-subtheme tree, and a test that reads live data is not a fixture.
        """
        seed = self.finviz_seed_path or (
            self.data_dir.parent / local_sources.SEED_TREE_FILE)
        history = self.finviz_history_path or (
            self.data_dir / "themes_heatmap" / "tree_history.jsonl")
        live = self.finviz_live_tree_path or (
            self.data_dir / "themes_heatmap" / "themes_tree.json")
        return Path(seed), Path(history), Path(live)

    def build_finviz_plane(self) -> None:
        """Finviz subthemes as local_theme nodes + the source's own MEMBER_OF claims.

        This is NOT the derived company→theme edge W1b refused. That refusal is about
        COMPOSING membership with expression into a fact no receipt supports; here the
        source itself asserts "this ticker is in this subtheme", at its own grain, and the
        edge carries its provenance. The structural proof that no laundering happens: the
        Finviz plane mints ZERO ltheme→theme edges, so there is no path from a company to
        canonical vocabulary through it at all.
        """
        seed_path, history_path, live_path = self._finviz_paths()
        ladder = local_sources.load_finviz_ladder(
            seed_path=seed_path, history_path=history_path, live_tree_path=live_path)
        if not ladder.vintages:
            self.out.local_plane["finviz"] = {
                "vintages": [], "subthemes": 0, "member_edges": 0,
                "note": "no dated Finviz vintage available — plane skipped"}
            return

        vintage_ev = {
            v.source_ref: self._evidence_ref(
                kind="scrape", source_ref=v.source_ref, published_at=v.asof,
                licensing=_licensing(FINVIZ_FAMILY))
            for v in ladder.vintages}

        # The supergroup layer exists only in the refresh receipts (the committed tree
        # flattens it); the loader returns {} when no receipt carries it, and the
        # registry then stamps None — never a theme-ordinal guess (diff-review F1).
        supergroups = local_sources.load_supergroups(
            self.data_dir / "themes_heatmap" / "tree_refresh_receipts")
        registry = local_sources.subtheme_registry(ladder, supergroups)
        for key, meta in registry.items():
            try:
                lt_node = identity.local_theme_node_id(
                    local_sources.FINVIZ_LOCAL_FAMILY, key)
            except ValueError as exc:
                log.warning("theme_graph: finviz subtheme %r skipped (%s)", key, exc)
                continue
            self._node(
                lt_node, kind="local_theme", market_scope="us",
                provenance=f"{FINVIZ_CONFIDENCE_BASIS}:{local_sources.SEED_TREE_FILE}",
                # MINT-TIME label snapshot. The live tree is the label authority; a
                # displayName rename lands in the refresh receipt and changes no bytes
                # here (keep-first makes an in-place relabel impossible by design).
                name_en=meta.name, name_zh=None,
                birth_date=meta.first_seen,
                external_ids={"subtheme_key": key},
                source_meta={
                    "source_family": FINVIZ_FAMILY,
                    "source_local_id": key,
                    "market": "us",
                    "source_label": meta.name,
                    "source_description": meta.description,
                    "grain": "finviz_subtheme",
                    "parent_source_label": meta.parent_theme_label,
                    "parent_source_key": meta.parent_theme_key,
                    # The unlabelled layer above themes that the committed schema
                    # flattens: carried as METADATA, never resurrected as hierarchy
                    # (PARENT_OF edges are W4's).
                    "supergroup_index": meta.supergroup_index,
                    "key_aliases": [],
                    "rights_family": FINVIZ_FAMILY,
                })

        minted, exact, variants, refused = 0, 0, [], []
        n_edges, n_closed = 0, 0
        resolved: dict[str, str] = {}   # finviz symbol → node id, decided ONCE
        for iv in local_sources.membership_intervals(ladder):
            lt_node = f"ltheme:{local_sources.FINVIZ_LOCAL_FAMILY}:{iv.subtheme_key}"
            if lt_node not in self._nodes:
                continue
            c_node = resolved.get(iv.symbol)
            if c_node is None:
                try:
                    c_node, was_variant = identity.resolve_symbol_variant(
                        "finviz_themes", iv.symbol, self._nodes, breaks=self.breaks)
                except ValueError as exc:
                    refused.append(f"{iv.symbol}: {exc}")
                    continue
                # Counted per SYMBOL, not per membership: a name in nine subthemes is one
                # company, and counting it nine times is how a mint estimate goes wrong.
                if was_variant:
                    variants.append(f"{iv.symbol}->{c_node}")
                elif c_node in self._nodes:
                    exact += 1
                else:
                    minted += 1
                    self._node(
                        c_node, kind="company", market_scope="us",
                        provenance=(f"{FINVIZ_CONFIDENCE_BASIS}:"
                                    f"{local_sources.SEED_TREE_FILE}"),
                        external_ids={"symbol": iv.symbol},
                        identity_epoch=identity.identity_epoch(
                            "us", iv.symbol, breaks=self.breaks))
                resolved[iv.symbol] = c_node
            refs = [vintage_ev[iv.opened_by]]
            if iv.closed_by and vintage_ev.get(iv.closed_by) not in (None, refs[0]):
                # The CLOSING observation is its own receipt: the vintage that first
                # showed the member gone is what dates valid_to.
                refs.append(vintage_ev[iv.closed_by])
            observed_on = iv.valid_to or iv.valid_from
            self._edge(
                edge_type="MEMBER_OF", src=c_node, dst=lt_node,
                valid_from=iv.valid_from, valid_to=iv.valid_to,
                evidence_time=observed_on,
                source_class="scrape", date_provenance="raw_snapshot",
                evidence_refs=refs, confidence_basis=FINVIZ_CONFIDENCE_BASIS,
                era=self._era_for(observed_on))
            n_edges += 1
            n_closed += 1 if iv.valid_to else 0

        self.out.local_plane["finviz"] = {
            "vintages": ladder.asofs,
            "dropped_adjacent_duplicates": ladder.dropped_adjacent_duplicates,
            "notes": ladder.notes,
            "subthemes": len(registry),
            "member_edges": n_edges,
            "closed_member_edges": n_closed,
            # The resolution table the receipt asserts against (§9.13) — printed rather
            # than estimated, because the estimate has already been wrong once.
            "company_resolution": {
                "minted_new": minted,
                "resolved_existing": exact,
                "resolved_dot_dash_variant": len(variants),
                "variant_pairs": sorted(variants)[:50],
                "refused": refused[:20],
            },
        }
        log.info("theme_graph: finviz plane — %d vintages %s, %d subthemes, %d member "
                 "edges (%d closed); companies: %d new / %d existing / %d variant-resolved",
                 len(ladder.vintages), ladder.asofs, len(registry), n_edges, n_closed,
                 minted, exact, len(variants))

    # -- local-theme plane: 同花顺 concepts ----------------------------------

    def build_ths_plane(self) -> None:
        """同花顺 concepts as local_theme nodes + basket→concept expression edges.

        Membership is BASKET-MEDIATED this wave: the edge says "this curated basket is
        that vendor concept", which is the mechanical join the membership document itself
        already carries. Snapshot-direct memberships for the unseeded concepts are W3B's
        — inventing them here would mint company edges from a snapshot nobody dated.
        """
        cmap = self._concept_map()
        asof = getattr(self, "_cmap_asof", None)
        if not cmap or not _is_date(asof):
            self.out.local_plane["ths"] = {
                "concepts": 0, "expresses_edges": 0,
                "note": "no dated concept map — plane skipped"}
            return
        cmap_ev = self._evidence_ref(
            kind="scrape", source_ref=f"data/{THS_SUITE}/concept_map.json",
            published_at=asof, licensing=_licensing(THS_FAMILY))

        for zh_name, code in sorted(cmap.items(), key=lambda kv: kv[1]):
            try:
                lt_node = identity.local_theme_node_id("ths", code)
            except ValueError as exc:
                log.warning("theme_graph: ths concept %r skipped (%s)", code, exc)
                continue
            self._node(
                lt_node, kind="local_theme", market_scope="cn",
                provenance=f"concept_map:data/{THS_SUITE}/concept_map.json",
                # The source's label is 中文; there is no English one to invent.
                name_en=None, name_zh=zh_name, birth_date=asof,
                external_ids={"ths_code": code},
                source_meta={
                    "source_family": THS_FAMILY,
                    "source_local_id": code,
                    "market": "cn",
                    "source_label": zh_name,
                    "source_description": None,
                    "grain": "ths_concept",
                    "parent_source_label": None,
                    "parent_source_key": None,
                    "supergroup_index": None,
                    "key_aliases": [],
                    "rights_family": THS_FAMILY,
                })

        doc = self._membership(THS_SUITE)
        n_expresses, unresolved = 0, []
        self._ths_basket_concept_dates: dict[str, str] = {}
        if doc:
            published_at = _doc_published_at(doc)
            doc_ev = self._evidence_ref(
                kind="scrape", source_ref=f"data/{THS_SUITE}/membership.json",
                published_at=published_at or asof,
                licensing=_licensing(THS_FAMILY))
            for bid, basket in (doc.get("baskets") or {}).items():
                concept = _text(basket.get("ths_concept"))
                if not concept:
                    continue
                code = cmap.get(concept)
                if not code:
                    # Report-only, the `_meta` unknown-list idiom: a name the vendor's
                    # own map no longer resolves is a coverage fact, not an edge.
                    unresolved.append(concept)
                    continue
                b_node = identity.basket_node_id(THS_SUITE, bid)
                lt_node = f"ltheme:ths:{code}"
                if b_node not in self._nodes or lt_node not in self._nodes:
                    continue
                # This is a dated association in the membership document, not a
                # timeless property inferred from the current map.  Keep it for the
                # later crosswalk gate as well as the source-local expression.
                basket_node = self._nodes[b_node]
                basket_external = json.loads(basket_node["external_ids"])
                basket_external["ths_code"] = code
                basket_node["external_ids"] = json.dumps(
                    basket_external, ensure_ascii=False, sort_keys=True)
                # B2: the association is only as fresh as the LATEST of the two
                # owner receipts that produced it — a stale membership doc riding a
                # freshly reloaded concept map (or vice versa) must not certify a
                # canonical join dated earlier than either receipt actually landed.
                assoc_date = max(d for d in (published_at, asof) if d)
                self._ths_basket_concept_dates[b_node] = assoc_date
                self._edge(
                    edge_type="EXPRESSES", src=b_node, dst=lt_node,
                    valid_from=assoc_date, valid_to=None,
                    evidence_time=assoc_date, source_class="scrape",
                    date_provenance="raw_snapshot",
                    evidence_refs=[doc_ev, cmap_ev],
                    confidence_basis=CONFIDENCE_BASIS,
                    era=self._era_for(assoc_date))
                n_expresses += 1

        self.out.unknown_ths_concepts = sorted(set(unresolved))
        self.out.local_plane["ths"] = {
            "concepts": len(cmap), "concept_map_asof": asof,
            "expresses_edges": n_expresses,
            "unresolved_concept_names": len(self.out.unknown_ths_concepts),
        }
        log.info("theme_graph: ths plane — %d concepts (asof %s), %d basket expressions, "
                 "%d unresolved concept name(s)", len(cmap), asof, n_expresses,
                 len(self.out.unknown_ths_concepts))

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
            published_at=xwalk_date, licensing=_licensing("mastermind_curated"))
        cmap = self._concept_map()
        cmap_ev = None
        if self._cmap_asof:
            cmap_ev = self._evidence_ref(
                kind="scrape", source_ref=f"data/{THS_SUITE}/concept_map.json",
                published_at=self._cmap_asof, licensing=_licensing(THS_FAMILY))
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
        n_ltheme_expresses = 0
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
                association_date = getattr(self, "_ths_basket_concept_dates", {}).get(b_node)
                if not association_date or association_date > xwalk_date:
                    # A current basket→concept association cannot certify an older
                    # canonical join.  The local edge remains visible at its own
                    # observation date; the canonical edge declines honestly.
                    continue
                refs = [xwalk_ev] + ([cmap_ev] if cmap_ev else [])
                self._edge(edge_type="EXPRESSES", src=b_node, dst=t_node,
                           valid_from=xwalk_date, valid_to=None,
                           evidence_time=xwalk_date, source_class="curated",
                           date_provenance="crosswalk", evidence_refs=refs)
                n_expresses += 1

            # VOCABULARY RESOLUTION, not a second expression path (§9.12). The canonical
            # expression stays ONE hop — basket→theme, above. This edge says the vendor's
            # concept and our canonical theme name the same thing, which is what makes a
            # THS-native id readable in canonical terms without any consumer composing a
            # membership through it. Finviz gets ZERO of these: no concept-grain curation
            # exists for its subthemes, and a mechanical mapping would smear
            # application-tier subthemes onto infrastructure-tier canonical themes.
            for code in codes:
                lt_node = f"ltheme:ths:{code}"
                if lt_node not in self._nodes:
                    continue
                refs = [xwalk_ev] + ([cmap_ev] if cmap_ev else [])
                self._edge(edge_type="EXPRESSES", src=lt_node, dst=t_node,
                           valid_from=xwalk_date, valid_to=None,
                           evidence_time=xwalk_date, source_class="curated",
                           date_provenance="crosswalk", evidence_refs=refs)
                n_ltheme_expresses += 1

        self.out.unknown_ths_codes = sorted(unknown)
        self.out.ths_unmapped_concept_count = sum(
            1 for code in cmap.values() if code not in mapped_codes)
        self.out.per_suite["crosswalk"] = {
            "themes": len(rows), "expresses_edges": n_expresses,
            "local_theme_expresses_edges": n_ltheme_expresses,
            "published_at": xwalk_date,
            "ths_codes_mapped": len(mapped_codes),
            "ths_codes_unknown": len(unknown),
        }

    # -- drive -------------------------------------------------------------

    def run(self) -> Materialization:
        for suite in SUITES:
            # D2C gives THS a distinct producer below: its live document has no
            # historical membership authority.
            if suite == THS_SUITE:
                continue
            try:
                self.build_family(suite)
            except ValueError as exc:
                self.out.skipped_suites[suite] = str(exc)
                log.warning("theme_graph: %s skipped (%s)", suite, exc)
        # ORDER IS LOAD-BEARING. The suites mint the basket and company nodes the local
        # planes resolve against (a Finviz ticker already present must resolve to the
        # existing node, never to a twin), and the THS plane mints the concept nodes the
        # crosswalk's vocabulary-resolution edges point at.
        for build_plane in (self.build_ths_membership_history,
                            self.build_finviz_plane, self.build_ths_plane):
            try:
                build_plane()
            except Exception as exc:  # noqa: BLE001 — a local plane is additive
                log.warning("theme_graph: local plane %s failed (%s)",
                            build_plane.__name__, exc)
                self.out.local_plane[build_plane.__name__] = {"error": str(exc)}
        self.build_crosswalk()
        self.out.nodes = [self._nodes[k] for k in sorted(self._nodes)]
        self.out.edges = [self._edges[k] for k in sorted(self._edges)]
        self.out.evidence = [self._evidence[k] for k in sorted(self._evidence)]
        # V4-D2B3 (R-A1): a POST-PASS structural filter, run only once every suite and
        # local plane has contributed — the etf node set is complete ONLY here.
        # Resurrection-proofing: belief_time is the run date (R-A1), so write-side
        # keep-first protects nothing across days; the only durable fence is the bake
        # never COMPUTING the corrected node/edge in the first place.
        self.out.nodes, self.out.edges, self.out.company_mint_refusals = (
            _suppress_conflicts_and_retired(
                self.out.nodes, self.out.edges,
                retired_node_ids=self.retired_node_ids))
        self.out.capability = capability_rule.derive_rows(
            self.out.nodes, self.out.edges,
            substrate=capability_rule.load_substrate(self.substrate_dir),
            computed_at=self.computed_at, engine_version=ENGINE_VERSION)
        # V4-D2A: the GMI -> Data OS identity bridge, over the SAME (already-suppressed)
        # generation's node list (so the etf/company entity-type-conflict check — rule 4
        # — sees exactly this build's post-correction topology; a suppressed company
        # node is no longer in self.out.nodes at all, so it contributes zero rows here,
        # which is precisely R-A3's "the live conflict counter lawfully drops to 0").
        self.out.identity_resolution = identity_resolution.derive_rows(
            self.out.nodes, resolution_asof=self.belief_time,
            computed_at=self.computed_at, engine_version=ENGINE_VERSION,
            data_dir=self.data_dir)
        return self.out


def _node_symbol(node: dict) -> str | None:
    """A node's ``external_ids.symbol``, uppercased — the same field every builder path
    here sets (``_node(..., external_ids={"symbol": ...})``). None when absent/blank."""
    try:
        ext = json.loads(node.get("external_ids") or "{}")
    except Exception:  # noqa: BLE001 — malformed external_ids is not fatal here
        return None
    sym = ext.get("symbol")
    return str(sym).strip().upper() if sym else None


def _etf_symbol_set(nodes: list[dict]) -> frozenset[str]:
    """Every ``etf``-kind node's symbol, from THIS SAME generation's node list. Purely
    structural — no ticker literal, no name heuristic (matches the D2A rule-4 evidence
    identity_resolution._etf_symbols already uses over the same generation)."""
    return frozenset(
        sym for n in nodes
        if str(n.get("kind")) == "etf" and (sym := _node_symbol(n)))


def _suite_from_provenance(provenance: object) -> str | None:
    """Best-effort suite name for a refusal receipt — presentational only, never a
    routing decision. ``membership_doc:<suite>`` splits cleanly; the Finviz local plane
    mints companies under its own confidence-basis provenance string instead of a
    suite, so it is named ``finviz_themes`` (its market/suite namespace, identity.py's
    own SUITE_MARKET key) for readability."""
    p = str(provenance or "")
    if p.startswith("membership_doc:"):
        return p.split(":", 1)[1]
    if p.startswith(FINVIZ_CONFIDENCE_BASIS):
        return "finviz_themes"
    return None


def _suppress_conflicts_and_retired(
        nodes: list[dict], edges: list[dict], *,
        retired_node_ids: frozenset[str]) -> tuple[list[dict], list[dict], list[dict]]:
    """R-D2B3-4 / R-A1 / R-A6 — the resurrection-proof POST-PASS filter.

    Removes, from THIS build's own computed view (never from the committed store):

    (a) every company-kind node whose symbol also exists as an etf-kind node in the
        SAME generation's node set (entity-kind conflict — structural, same-generation
        evidence only, no ticker literal, no Data OS read);
    (b) every company-kind node whose node_id is in ``retired_node_ids`` (a re-mint of
        a node the lifecycle lineage says is retired/merged — defense-in-depth; for a
        RATIFIED identity-break symbol the live epoch law already routes new evidence
        to ``#<epoch>``, so the epoch-1 id is structurally unmintable and this branch is
        the backstop, never the primary fence).

    Every edge whose ``src`` is a removed node is removed with it (a company node is
    always MEMBER_OF's ``src``, never its ``dst`` — EDGE_PAIRING pins this). One typed
    refusal dict is emitted per removed node; never a raise (R-A6) — a raise inside the
    nightly bake would be an outage weapon, not a fence.
    """
    etf_syms = _etf_symbol_set(nodes)
    removed_ids: set[str] = set()
    refusals: list[dict] = []
    kept_nodes: list[dict] = []
    for n in nodes:
        if str(n.get("kind")) != "company":
            kept_nodes.append(n)
            continue
        node_id = str(n.get("node_id"))
        sym = _node_symbol(n)
        suite = _suite_from_provenance(n.get("provenance"))
        if sym and sym in etf_syms:
            removed_ids.add(node_id)
            refusals.append({
                "symbol": sym, "suite": suite, "reason": "etf_conflict",
                "conflicting_node": f"etf:{sym}",
            })
            continue
        if node_id in retired_node_ids:
            removed_ids.add(node_id)
            refusals.append({
                "symbol": sym, "suite": suite, "reason": "retired_remint",
                "conflicting_node": node_id,
            })
            continue
        kept_nodes.append(n)
    if not removed_ids:
        return nodes, edges, []
    kept_edges = [e for e in edges if str(e.get("src")) not in removed_ids]
    refusals.sort(key=lambda r: (str(r["reason"]), str(r["symbol"] or ""),
                                 str(r["conflicting_node"] or "")))
    return kept_nodes, kept_edges, refusals


def build(*, era: str, belief_time: str | None = None,
          computed_at: str | None = None,
          data_dir: Path | None = None,
          crosswalk_path: Path | None = None,
          raw_snapshot: tuple[str, dict] | None = None,
          ths_history=None,
          finviz_seed_path: Path | None = None,
          finviz_history_path: Path | None = None,
          finviz_live_tree_path: Path | None = None,
          substrate_dir: Path | None = None,
          retired_node_ids: frozenset[str] | None = None) -> Materialization:
    """Compute the whole graph view. Pure: reads inputs, writes nothing.

    ``retired_node_ids`` (V4-D2B3, R-A6): node_ids whose latest ``node_lifecycle``
    status is retired/merged, read by the caller (the impure orchestrator) and handed
    in as a plain frozenset — materialize itself never touches the store.
    """
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
        ths_history=ths_history,
        finviz_seed_path=finviz_seed_path,
        finviz_history_path=finviz_history_path,
        finviz_live_tree_path=finviz_live_tree_path,
        substrate_dir=substrate_dir,
        retired_node_ids=retired_node_ids,
    ).run()


# ---------------------------------------------------------------------------
# Source-family shrink wall (the SECOND wall — §2)
# ---------------------------------------------------------------------------

def source_family_of(node_id: object) -> str | None:
    """Which source family a membership's destination belongs to."""
    return rights.family_for_node_id(node_id)


def source_shrink_refusals(computed: list[dict], stored, *,
                           allow: frozenset[str] | set[str] | tuple[str, ...] = (),
                           max_shrink: float = MAX_SOURCE_SHRINK) -> list[str]:
    """Refusal messages for every family whose live memberships would shrink too far.

    Behind the refresh contract's own interlocks, and aimed at a different attacker: a
    hand-edited tree, a truncated hand-run, or a bad merge never passes through the
    refresh path at all, so the refresh walls never see it. This one sits where every
    write does. It measures CLOSURES against the stored live view, not row counts —
    an append-only store grows on every belief, so "fewer rows" is not a thing that
    happens here and counting rows would measure nothing.

    Returns messages, never raises: the caller decides whether a refusal stops a build
    or is waived with ``--allow-source-shrink <family>``.
    """
    if stored is None or len(stored) == 0:
        return []
    allow = {str(a) for a in allow}
    stored_rows = (stored.to_dict("records") if hasattr(stored, "to_dict")
                   else list(stored))
    live_by_family: dict[str, set[str]] = {}
    for row in stored_rows:
        if not _null(row.get("valid_to")):
            continue
        family = source_family_of(row.get("dst"))
        if family:
            live_by_family.setdefault(family, set()).add(str(row.get("edge_id")))
    if not live_by_family:
        return []

    closing_by_family: dict[str, int] = {}
    for row in computed:
        if _null(row.get("valid_to")):
            continue
        family = source_family_of(row.get("dst"))
        if family and str(row.get("edge_id")) in live_by_family.get(family, ()):
            closing_by_family[family] = closing_by_family.get(family, 0) + 1

    out: list[str] = []
    for family, live in sorted(live_by_family.items()):
        closing = closing_by_family.get(family, 0)
        share = closing / len(live) if live else 0.0
        if share > max_shrink and family not in allow:
            out.append(
                f"{family}: this build would close {closing} of {len(live)} live "
                f"memberships ({share:.1%} > {max_shrink:.0%}) — refusing. A source "
                f"genuinely restructuring is possible; a truncated or hand-edited input "
                f"is likelier, and in an append-only store the closures are permanent. "
                f"Pass --allow-source-shrink {family} to proceed deliberately")
    return out


# ---------------------------------------------------------------------------
# THS membership_doc → membership_pit generation cutover
# ---------------------------------------------------------------------------

THS_MEMBERSHIP_DOC_BASIS = CONFIDENCE_BASIS  # "membership_doc.v1"
THS_BASKET_DST_PREFIX = f"basket:{THS_SUITE}:"


def ths_membership_pit_birth(history) -> str | None:
    """Earliest membership-shape snapshot_date in the owner PIT history, or None."""
    rows = history.to_dict("records") if hasattr(history, "to_dict") else list(history or ())
    dates = sorted({
        str(row.get("snapshot_date") or "").strip()
        for row in rows
        if _text(row.get("source_shape")) == "membership"
        and _is_date(row.get("snapshot_date"))
    })
    return dates[0] if dates else None


def _normalize_evidence_refs(value: object) -> list[str]:
    if _null(value):
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return [value] if value.strip() else []
        value = parsed
    if isinstance(value, (list, tuple)):
        return [str(x) for x in value]
    return [str(value)]


def supersede_ths_membership_doc_edges(
    stored: pd.DataFrame,
    *,
    valid_to: str,
    belief_time: str,
    era: str,
    computed_at: str,
    pit_pairs: "set[tuple[str, str]] | None" = None,
) -> list[dict]:
    """Retract superseded-generation THS MEMBER_OF edges the PIT plane re-observed.

    The PIT cutover re-keys every THS membership (``edge_id`` embeds ``valid_from``),
    and ``changed_edges`` deliberately never closes a vanished edge. Without an
    explicit retracting row for each stored ``membership_doc.v1`` / ``@seed_constant``
    edge, both generations stay live. Retraction reuses the SAME ``edge_id`` with
    ``valid_from`` DEGENERATED to ``valid_to`` (the codebase's existing zero-width
    annulment convention — see ``test_r_a1_i_annulled_edge_stays_closed...``) so the
    latest-belief view asserts NO valid-time span for the un-observed 2021-onward
    era; end-dating with the original 2021 seed date would instead assert that
    backdated fiction as a TRUE membership up to the PIT birth date, which is
    exactly the exposure this cutover exists to remove (review BLOCKER 1).

    ``pit_pairs`` (MAJOR 1): only the (src, dst) pairs the PIT plane actually
    RE-OBSERVED get retracted here. A pair the PIT history never covers is left
    open (a disclosed coverage gap, not a fabricated exit) — closing every stored
    row regardless of PIT coverage would assert an exit for pairs no source ever
    observed ending, which ``changed_edges``'s own docstring forbids.
    """
    if stored is None or getattr(stored, "empty", True) or not _is_date(valid_to):
        return []
    out: list[dict] = []
    for row in stored.to_dict("records"):
        if str(row.get("type") or "") != "MEMBER_OF":
            continue
        if not str(row.get("dst") or "").startswith(THS_BASKET_DST_PREFIX):
            continue
        if str(row.get("confidence_basis") or "") != THS_MEMBERSHIP_DOC_BASIS:
            continue
        if not _null(row.get("valid_to")):
            continue
        src = str(row["src"])
        dst = str(row["dst"])
        if pit_pairs is not None and (src, dst) not in pit_pairs:
            continue
        closed = {col: row.get(col) for col in RESERVED_EDGE_FIELDS}
        closed.update({
            "edge_id": str(row["edge_id"]),
            "type": "MEMBER_OF",
            "src": src,
            "dst": dst,
            "valid_from": valid_to,
            "valid_to": valid_to,
            "evidence_time": str(row.get("evidence_time") or valid_to),
            "belief_time": belief_time,
            "era": era,
            "source_class": str(row.get("source_class") or "scrape"),
            "date_provenance": str(row.get("date_provenance") or "seed_constant"),
            "evidence_refs": _normalize_evidence_refs(row.get("evidence_refs")),
            "confidence_basis": THS_MEMBERSHIP_DOC_BASIS,
            "computed_at": computed_at,
            "engine_version": str(row.get("engine_version") or ENGINE_VERSION),
        })
        for f in RESERVED_EDGE_FIELDS:
            if f not in closed:
                closed[f] = None
        out.append(closed)
    out.sort(key=lambda r: r["edge_id"])
    return out


# ---------------------------------------------------------------------------
# Nightly diff
# ---------------------------------------------------------------------------

def _null(v: object) -> bool:
    """True for None and for pandas' own nulls.

    LOAD-BEARING. A parquet column that is entirely null reads back as object/None, but
    a MIXED one (valid_to: 18 closed intervals among 5,628 open ones) reads back with
    NaN in the empty cells. Comparing a computed None against a stored NaN made every
    open edge look changed, and the first nightly over the real committed store proposed
    re-appending 5,610 of 5,628 edges — while the fixture suite, whose valid_to column
    happened to be all-null, saw a clean no-op. Hence the mixed-column test beside the
    fixture one.
    """
    if v is None:
        return True
    if isinstance(v, str) or hasattr(v, "__len__"):
        return False
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):  # pragma: no cover — exotic scalars
        return False


def _material(row: dict) -> tuple:
    out = []
    for f in MATERIAL_EDGE_FIELDS:
        v = row.get(f)
        if f == "evidence_refs":
            items = [] if _null(v) else list(v)
            out.append(tuple(sorted(str(x) for x in items)))
        elif _null(v):
            out.append(None)
        elif isinstance(v, (str, bool, int, float)):
            out.append(v)
        else:
            out.append(str(v))
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
