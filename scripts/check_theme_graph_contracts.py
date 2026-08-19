"""Guard: the theme graph's edge contract holds (law_id ``theme_graph.edge_contract``).

WHAT IT PROTECTS. The graph is the substrate every later GMI wave reads, and its
failure modes are all quiet ones — a column that drifted, an evidence ref pointing at
nothing, a closed interval that stopped resolving, an identity epoch nobody ratified.
None of those raise; they just make the answers wrong. So they are checked structurally,
against the committed contracts in ``contracts/theme_graph/``.

CHECKS
  1. Exact column set AND order on all three stores, plus dtype families.
  2. jsonschema on an evenly-spaced sample (<=200 rows per store) — the schemas are the
     contract, not a hand-copied field list — plus a VECTORIZED full-scan for every enum
     and for the company-id grammar, so a bad row outside the sample cannot hide.
  3. Semantic leakage, general form (masterplan §4.4): every edge carries >=1
     evidence_ref, and every ref resolves to an evidence row with a parseable dated
     ``published_at``. Undatable evidence is knowledge from nowhere.
  4. ``source_class=llm_proposed_ratified`` with no dated evidence is refused. Zero such
     rows exist today; the check is structural on purpose — the point is that the first
     one cannot land quietly.
  5. ``identity_epoch >= 2`` requires a matching ratified row in
     ``config/theme_graph_identity_breaks.yml``. A builder may not decide on its own
     that two listings are different companies.
  6. Closed-edge survivorship: every edge_id that appears anywhere in the FULL history
     carrying a ``valid_to`` still resolves in the latest-belief view. A closed
     membership must be findable, not merely absent.
  7. Local-theme plane (W3A): the ``ltheme:`` id grammar; the src/dst KIND pairing every
     edge type is allowed to connect; no ``basket:finviz_themes:*`` id exists at all (the
     suite is registered for company identity only, so a basket there is a category
     error, closed structurally rather than by convention).
  8. Rights, fail-closed: every non-null ``source_meta.rights_family`` has a row in
     ``config/theme_sources.yml``. A family nobody wrote down is a family nobody
     reviewed. Evidence rows whose MINT-TIME licensing booleans disagree with their
     family's current class produce a titled ::notice, never a breach — the store is append-only
     and history is a record, not a mistake to be edited (§9.4).
  9. Join law: the canonical expression path is ONE hop (basket→theme). ``ltheme→theme``
     is vocabulary resolution, not a second expression path, so over the crosswalk rows
     the two SHARE the two paths must agree in both directions — a basket that expresses
     a theme through its concept, and a concept that resolves to a theme, cannot disagree
     about which theme that is.
  10. Capability side-car (when present): columns, schema, enum, and that every classified
     node resolves to a node row. ``measurable`` is unreachable before W3B measures.

MIGRATION. v1 is additive-only, so a store written before the W3A columns existed is not
drift: a store missing ONLY columns from ``ADDITIVE_SINCE_W3A``, in the right order
otherwise, is reported as a ``::notice`` naming the rebuild command, never as a breach.
Anything else — a missing core column, an unexpected column, a re-ordering — stays a
breach exactly as before.

VERDICTS. A missing store is INDETERMINATE (``::notice``, rc 0) — a sparse checkout
carries no ``data/``, and the state before the first run is not a breach. A breach
prints one ``::warning`` and returns 0 by default (advisory, so a nightly collect lane
is never taken down by a display-tier plane); ``--strict`` turns breaches into rc 1 for
CI. ``--selftest`` rebuilds each incident as a fixture and proves the guard still sees it.

Run: python -m scripts.check_theme_graph_contracts [--strict] [--selftest]
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.theme_graph import identity, rights, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("check_theme_graph_contracts")

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = ROOT / "contracts" / "theme_graph"
SAMPLE_MAX = 200

#: column -> dtype family. "str"/"int"/"bool" are enforced on NON-NULL values only, so
#: an all-null reserved column (the W2 exposure axes) is not forced into a type it will
#: only acquire when it is measured.
NODE_DTYPES: dict[str, str] = {
    "node_id": "str", "kind": "str", "name_en": "str", "name_zh": "str",
    "market_scope": "str", "tier": "str", "status": "str", "merged_into": "str",
    "birth_date": "str", "retire_date": "str", "identity_epoch": "int",
    "external_ids": "str", "provenance": "str", "computed_at": "str",
    "engine_version": "str", "source_meta": "str",
}

#: Columns v1 gained in W3A. A store written before them is PRE-MIGRATION, not drifted:
#: additive-only means the old shape was contract-valid when it was written, and a guard
#: that reds the whole fleet between a code merge and the next nightly rebuild is a
#: scheduled red, not a finding. Every other column-set difference stays a breach.
ADDITIVE_SINCE_W3A: dict[str, frozenset[str]] = {
    "nodes": frozenset({"source_meta"}),
    "edges": frozenset(),
    "evidence": frozenset({"provider", "claim_type"}),
}
EDGE_DTYPES: dict[str, str] = {
    "edge_id": "str", "type": "str", "src": "str", "dst": "str", "valid_from": "str",
    "valid_to": "str", "evidence_time": "str", "belief_time": "str", "era": "str",
    "source_class": "str", "date_provenance": "str", "evidence_refs": "list",
    "confidence_basis": "str",
    "economic_share": "num", "trading_beta": "num", "attention_share": "num",
    "economic_share_formula_id": "str", "trading_beta_formula_id": "str",
    "attention_share_formula_id": "str", "economic_share_display": "str",
    "trading_beta_display": "str", "attention_share_display": "str",
    "computed_at": "str", "engine_version": "str",
}
EVIDENCE_DTYPES: dict[str, str] = {
    "evidence_id": "str", "kind": "str", "published_at": "str", "effective_at": "str",
    "source_ref": "str", "licensing_internal_ok": "bool",
    "licensing_display_ok": "bool", "licensing_redistribution_ok": "bool",
    "retention": "str", "computed_at": "str", "provider": "str", "claim_type": "str",
}
CAPABILITY_DTYPES: dict[str, str] = {
    "node_id": "str", "capability": "str", "capability_basis": "str",
    "computed_at": "str", "engine_version": "str",
}
#: V4-D2A — the GMI -> Data OS identity resolution bridge side-car.
IDENTITY_RESOLUTION_DTYPES: dict[str, str] = {
    "schema": "str", "node_id": "str", "graph_kind": "str", "market_scope": "str",
    "graph_identity_epoch": "int", "source_native_symbol": "str", "resolution_asof": "str",
    "resolution_state": "str", "issuer_id": "str", "security_id": "str",
    "listing_key": "str", "join_method": "str", "master_generated_at": "str",
    "master_symbol_directory_snapshot": "str", "master_code_version": "str",
    "refusal_reason": "str", "source_receipts": "str", "computed_at": "str",
    "engine_version": "str",
}

#: Enum columns scanned in FULL (the sample proves shape, the scan proves values).
NODE_ENUMS: dict[str, set[str]] = {
    "kind": {"theme", "company", "etf", "catalyst", "policy_program", "commodity",
             "participant_class", "market", "basket", "local_theme"},
    "status": {"candidate", "canonical", "retired", "merged"},
}
EDGE_ENUMS: dict[str, set[str]] = {
    "type": {"MEMBER_OF", "EXPRESSES", "SAME_AS", "TRANSLATES_TO", "PARENT_OF",
             "RELATED", "SUPPLIES", "ENABLES", "BOTTLENECK_OF", "BENEFITS_FROM",
             "CATALYST_OF", "TRACKS", "HEDGES"},
    "era": {"reconstruction", "observed"},
    "source_class": {"curated", "scrape", "filing", "co_movement",
                     "llm_proposed_ratified"},
    "date_provenance": {"curated_changelog", "seed_constant", "raw_snapshot",
                        "crosswalk"},
    "economic_share_display": {"none", "weak", "core"},
    "trading_beta_display": {"none", "weak", "core"},
    "attention_share_display": {"none", "weak", "core"},
}
EVIDENCE_ENUMS: dict[str, set[str]] = {
    "kind": {"filing", "xbrl", "8k_counterparty", "scrape_receipt", "scrape",
             "news_item", "operator_curation", "comovement_stat",
             "external_classification"},
    "claim_type": {"membership", "exposure", "ecosystem_role", "description"},
}
CAPABILITY_ENUMS: dict[str, set[str]] = {
    # measurable is deliberately INSIDE the enum and OUTSIDE what W3A may mint: the
    # column has to be able to hold W3B's verdict, and the "nothing minted it yet" check
    # below is what keeps this wave from minting it early.
    "capability": {"semantic_only", "measurement_candidate", "measurable"},
}
IDENTITY_RESOLUTION_ENUMS: dict[str, set[str]] = {
    "market_scope": {"us", "cn", "hk", "ca", "intl"},
    "resolution_state": {"RESOLVED", "INVALID_SOURCE_ID", "UNSUPPORTED_MARKET",
                         "DEFERRED_IDENTITY_EXCEPTION", "ENTITY_TYPE_CONFLICT",
                         "AMBIGUOUS", "NOT_IN_MASTER"},
    "join_method": {"master_inception_exact", "vendor_alias", "refused"},
}

#: Which node kinds each edge type may connect. The pairing table is the structural
#: answer to "did somebody quietly compose a new path": a MEMBER_OF from a company to a
#: canonical theme, or an EXPRESSES from a local theme to a basket, would be a new
#: semantics smuggled in as data.
EDGE_PAIRING: dict[str, set[tuple[str, str]]] = {
    "MEMBER_OF": {("company", "basket"), ("company", "local_theme")},
    "EXPRESSES": {("basket", "theme"), ("basket", "local_theme"),
                  ("local_theme", "theme")},
    "TRACKS": {("etf", "basket")},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_null(v: object) -> bool:
    if v is None:
        return True
    if isinstance(v, (list, tuple, set)) or hasattr(v, "__len__") and not isinstance(v, str):
        return False
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):  # pragma: no cover — exotic scalars
        return False


def _jsonable(row: dict) -> dict:
    """A parquet row as plain JSON types, so jsonschema sees what the contract describes."""
    out: dict = {}
    for k, v in row.items():
        if hasattr(v, "tolist") and not isinstance(v, str):
            v = v.tolist()
        if isinstance(v, (list, tuple)):
            out[k] = [None if x is None else str(x) for x in v]
        elif _is_null(v):
            out[k] = None
        elif isinstance(v, bool):
            out[k] = bool(v)
        elif hasattr(v, "item") and not isinstance(v, str):
            out[k] = v.item()
        else:
            out[k] = v
    return out


def _sample(df: pd.DataFrame, n: int = SAMPLE_MAX) -> pd.DataFrame:
    """Evenly-spaced rows — deterministic, so a failure reproduces on the next run."""
    if len(df) <= n:
        return df
    step = max(1, len(df) // n)
    return df.iloc[::step].head(n)


def _dated(v: object) -> bool:
    if _is_null(v):
        return False
    try:
        date.fromisoformat(str(v).strip()[:10])
    except ValueError:
        return False
    return True


def _check_columns(df: pd.DataFrame, expected: tuple[str, ...],
                   label: str) -> tuple[list[str], list[str]]:
    """``(breaches, notices)``. A pre-migration store is a notice, drift is a breach."""
    got = tuple(df.columns)
    if got == expected:
        return [], []
    missing = [c for c in expected if c not in got]
    extra = [c for c in got if c not in expected]
    if missing and not extra:
        additive = ADDITIVE_SINCE_W3A.get(label, frozenset())
        if set(missing) <= additive and got == tuple(c for c in expected if c in set(got)):
            return [], [
                f"[additive columns pending rebuild] {label}: store predates the W3A additive column(s) {missing} — v1 is "
                f"additive-only, so this shape was valid when it was written. It is "
                f"filled by the next build (python -m scripts.build_theme_graph), not "
                f"by a migration"]
    if missing or extra:
        return [f"{label}: column set drift — missing {missing}, unexpected {extra}"], []
    return [f"{label}: column ORDER drift — the writer's column tuple is the contract "
            f"(got {list(got)})"], []


def _check_dtypes(df: pd.DataFrame, families: dict[str, str], label: str) -> list[str]:
    out: list[str] = []
    for col, fam in families.items():
        if col not in df.columns:
            continue
        values = [v for v in df[col].tolist() if not _is_null(v)]
        if not values:
            continue
        if fam == "str":
            bad = [v for v in values if not isinstance(v, str)]
        elif fam == "int":
            bad = [v for v in values if isinstance(v, bool) or not float(v).is_integer()]
        elif fam == "bool":
            bad = [v for v in values if not isinstance(v, (bool,))]
        elif fam == "num":
            bad = [v for v in values if isinstance(v, (str, bytes))]
        elif fam == "list":
            bad = [v for v in values if isinstance(v, (str, bytes))
                   or not hasattr(v, "__len__")]
        else:  # pragma: no cover — unknown family is a coding error
            bad = []
        if bad:
            out.append(f"{label}.{col}: {len(bad)} value(s) are not {fam} "
                       f"(first: {bad[0]!r})")
    return out


def _check_enums(df: pd.DataFrame, enums: dict[str, set[str]], label: str) -> list[str]:
    out: list[str] = []
    for col, allowed in enums.items():
        if col not in df.columns:
            continue
        seen = {str(v) for v in df[col].tolist() if not _is_null(v)}
        bad = sorted(seen - allowed)
        if bad:
            out.append(f"{label}.{col}: values outside the contract enum: {bad}")
    return out


def _check_schema(df: pd.DataFrame, schema_name: str, label: str) -> list[str]:
    path = CONTRACTS / f"{schema_name}.v1.schema.json"
    if not path.exists():
        return [f"{label}: contract {path.name} is missing — the schema IS the contract"]
    try:
        import jsonschema  # noqa: PLC0415
    except ImportError:  # pragma: no cover — CI installs it
        return []
    schema = json.loads(path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    out: list[str] = []
    for rec in _sample(df).to_dict("records"):
        errs = sorted(validator.iter_errors(_jsonable(rec)), key=lambda e: e.path)
        if errs:
            out.append(f"{label}: row {rec.get(df.columns[0])!r} violates "
                       f"{path.name}: {errs[0].message}")
            if len(out) >= 5:
                break
    return out


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

def audit(store_dir: Path, breaks_file: Path) -> tuple[list[str], list[str]]:
    """(breaches, notices) for the store rooted at ``store_dir``."""
    breaches: list[str] = []
    notices: list[str] = []

    paths = {"nodes": store_dir / "nodes.parquet",
             "edges": store_dir / "edges.parquet",
             "evidence": store_dir / "evidence.parquet"}
    missing = [k for k, p in paths.items() if not p.exists()]
    if missing:
        notices.append(
            f"theme graph store incomplete at {store_dir} (missing: {', '.join(missing)})"
            " — pre-first-run and sparse checkouts are INDETERMINATE, never a breach")
        return breaches, notices

    frames: dict[str, pd.DataFrame] = {}
    for key, p in paths.items():
        try:
            frames[key] = pd.read_parquet(p)
        except Exception as exc:  # noqa: BLE001
            breaches.append(f"{key}.parquet unreadable: {exc}")
    if breaches:
        return breaches, notices
    nodes, edges, evidence = frames["nodes"], frames["edges"], frames["evidence"]

    for frame, columns, label in ((nodes, store.NODE_COLUMNS, "nodes"),
                                  (edges, store.EDGE_COLUMNS, "edges"),
                                  (evidence, store.EVIDENCE_COLUMNS, "evidence")):
        col_breaches, col_notices = _check_columns(frame, columns, label)
        breaches += col_breaches
        notices += col_notices
    breaches += _check_dtypes(nodes, NODE_DTYPES, "nodes")
    breaches += _check_dtypes(edges, EDGE_DTYPES, "edges")
    breaches += _check_dtypes(evidence, EVIDENCE_DTYPES, "evidence")
    breaches += _check_enums(nodes, NODE_ENUMS, "nodes")
    breaches += _check_enums(edges, EDGE_ENUMS, "edges")
    breaches += _check_enums(evidence, EVIDENCE_ENUMS, "evidence")
    breaches += _check_schema(nodes, "nodes", "nodes")
    breaches += _check_schema(edges, "edges", "edges")
    breaches += _check_schema(evidence, "evidence", "evidence")

    # --- company id grammar, full scan --------------------------------------
    if "kind" in nodes.columns and "node_id" in nodes.columns:
        co = nodes[nodes["kind"].astype(str) == "company"]["node_id"].astype(str)
        bad = sorted(co[~co.str.match(identity.COMPANY_ID_RE)].tolist())
        if bad:
            breaches.append(
                f"{len(bad)} company node id(s) outside the permanent-identity grammar "
                f"{identity.COMPANY_ID_RE.pattern} (first: {bad[0]!r})")

    # --- local-theme grammar + the suite that has no baskets -----------------
    kinds = {}
    if {"kind", "node_id"} <= set(nodes.columns):
        kinds = {str(n): str(k) for n, k in zip(nodes["node_id"], nodes["kind"])}
        lt = nodes[nodes["kind"].astype(str) == "local_theme"]["node_id"].astype(str)
        bad = sorted(lt[~lt.str.match(identity.LOCAL_THEME_ID_RE)].tolist())
        if bad:
            breaches.append(
                f"{len(bad)} local_theme node id(s) outside the grammar "
                f"{identity.LOCAL_THEME_ID_RE.pattern} (first: {bad[0]!r}) — source keys "
                f"that cannot be expressed are resolved to a stable code BEFORE they "
                f"reach an id, never squeezed into one")
        stray = sorted(n for n in kinds if n.startswith("basket:finviz_themes:"))
        if stray:
            breaches.append(
                f"{len(stray)} basket id(s) in the finviz_themes namespace (first: "
                f"{stray[0]!r}) — that suite is registered for COMPANY identity only. Its "
                f"concepts are local_theme nodes; a basket there gives one source two "
                f"vocabularies for the same thing")

    # --- edge pairing: which kinds an edge type may connect -------------------
    if kinds and {"type", "src", "dst"} <= set(edges.columns):
        seen_pairs: dict[str, set[tuple[str, str]]] = {}
        example: dict[tuple[str, str, str], str] = {}
        for row in edges.to_dict("records"):
            etype = str(row.get("type"))
            pair = (kinds.get(str(row.get("src")), "?"),
                    kinds.get(str(row.get("dst")), "?"))
            seen_pairs.setdefault(etype, set()).add(pair)
            example.setdefault((etype, *pair), str(row.get("edge_id")))
        for etype, pairs in sorted(seen_pairs.items()):
            allowed = EDGE_PAIRING.get(etype)
            if allowed is None:
                continue
            for pair in sorted(pairs - allowed):
                if "?" in pair:
                    breaches.append(
                        f"{etype} edge {example[(etype, *pair)]!r} points at a node id "
                        f"that has no node row — an edge between things the store does "
                        f"not contain cannot be joined by anyone")
                    continue
                breaches.append(
                    f"{etype} edge {example[(etype, *pair)]!r} connects {pair[0]}→"
                    f"{pair[1]}, which is not a pairing this type may carry "
                    f"({sorted(allowed)}) — a new semantics may not arrive as data")

    # --- rights: fail closed on an unregistered family ------------------------
    if "source_meta" in nodes.columns and "node_id" in nodes.columns:
        known = rights.known_families()
        unregistered: dict[str, str] = {}
        for nid, meta in zip(nodes["node_id"], nodes["source_meta"]):
            if _is_null(meta):
                continue  # pre-existing node: exempt by construction, never by opinion
            try:
                family = str((json.loads(str(meta)) or {}).get("rights_family") or "")
            except Exception:  # noqa: BLE001
                breaches.append(f"node {str(nid)!r}: source_meta is not readable JSON")
                continue
            if family and family not in known:
                unregistered.setdefault(family, str(nid))
        for family, nid in sorted(unregistered.items()):
            breaches.append(
                f"source family {family!r} (e.g. node {nid!r}) has no row in "
                f"{rights.REGISTRY_FILE} — rights are STATED, never assumed; an "
                f"unreviewed family fails CLOSED rather than defaulting to permitted")

    # --- rights: a mint-time snapshot that disagrees with today ---------------
    if {"source_ref", "licensing_display_ok"} <= set(evidence.columns):
        stale: list[str] = []
        for row in evidence.to_dict("records"):
            family = rights.family_for_source_ref(row.get("source_ref"))
            if not family:
                continue
            expected = rights.licensing_for_family(family)
            got = (bool(row.get("licensing_internal_ok")),
                   bool(row.get("licensing_display_ok")),
                   bool(row.get("licensing_redistribution_ok")))
            if got != expected:
                stale.append(f"{row.get('evidence_id')} ({family}: {got} vs {expected})")
        if stale:
            # A titled ::notice, never a breach: the store is append-only, so a row minted under
            # last month's class cannot be rewritten and should not be. The registry is
            # what any live emission consults.
            notices.append(
                f"[licensing snapshots — designed] {len(stale)} evidence row(s) carry mint-time licensing that disagrees "
                f"with their family's CURRENT rights class (first: {stale[0]}) — "
                f"historical snapshots, not breaches. The registry "
                f"({rights.REGISTRY_FILE}) is the sole authority at emission time")

    # --- join law: one canonical hop, and the two paths agree -----------------
    if {"type", "src", "dst", "belief_time"} <= set(edges.columns):
        # The LATEST-BELIEF view, and only LIVE rows. Against the full history a mapping
        # that legitimately MOVED (theme A, later theme B) would read as a disagreement
        # with itself — the store keeps both rows on purpose, and a check that forgets
        # that manufactures a breach out of a correct history.
        ordered = edges.sort_values(["edge_id", "belief_time", "computed_at"],
                                    kind="stable")
        current = ordered.drop_duplicates(subset=["edge_id"], keep="last")
        live = current[(current["type"].astype(str) == "EXPRESSES")
                       & (current["valid_to"].map(_is_null))]
        # Multi-valued on purpose (diff-review F5): a basket expressing more than one
        # local theme must have EVERY mapping adjudicated — last-write-wins silently
        # exempted the extras from the agreement check the moment W3B/W4 adds one.
        basket_ltheme: dict[str, set[str]] = {}
        basket_theme: dict[str, set[str]] = {}
        ltheme_theme: dict[str, set[str]] = {}
        for row in live.to_dict("records"):
            src, dst = str(row.get("src")), str(row.get("dst"))
            if src.startswith("basket:") and dst.startswith("ltheme:"):
                basket_ltheme.setdefault(src, set()).add(dst)
            elif src.startswith("basket:") and dst.startswith("theme:"):
                basket_theme.setdefault(src, set()).add(dst)
            elif src.startswith("ltheme:") and dst.startswith("theme:"):
                ltheme_theme.setdefault(src, set()).add(dst)
        disagreements: list[str] = []
        for basket, lthemes in sorted(basket_ltheme.items()):
            via_local = set().union(*(ltheme_theme.get(lt, set()) for lt in lthemes)) \
                if lthemes else set()
            direct = basket_theme.get(basket, set())
            if not via_local or not direct:
                continue  # only the SHARED rows are in scope; absence is not conflict
            if via_local != direct:
                disagreements.append(
                    f"{basket} → {sorted(direct)} directly, but its concept(s) "
                    f"{sorted(lthemes)} resolve to {sorted(via_local)}")
        if disagreements:
            breaches.append(
                f"{len(disagreements)} crosswalk row(s) where the one-hop canonical "
                f"expression and the concept's vocabulary resolution disagree (first: "
                f"{disagreements[0]}) — ltheme→theme is vocabulary resolution, never a "
                f"second expression path, so the two cannot name different themes")

    # --- semantic leakage: every edge cites dated evidence -------------------
    dated_ids: set[str] = set()
    if {"evidence_id", "published_at"} <= set(evidence.columns):
        for eid, pub in zip(evidence["evidence_id"], evidence["published_at"]):
            if _dated(pub):
                dated_ids.add(str(eid))
    known_ids = {str(v) for v in evidence.get("evidence_id", pd.Series(dtype=object))}

    no_refs, orphan, undated, llm_bad = [], [], [], []
    for row in edges.to_dict("records"):
        refs = row.get("evidence_refs")
        refs = list(refs) if refs is not None and not _is_null(refs) else []
        refs = [str(r) for r in refs]
        eid = str(row.get("edge_id"))
        if not refs:
            no_refs.append(eid)
            continue
        if not any(r in known_ids for r in refs):
            orphan.append(eid)
            continue
        if not any(r in dated_ids for r in refs):
            undated.append(eid)
        if str(row.get("source_class")) == "llm_proposed_ratified" \
                and not any(r in dated_ids for r in refs):
            llm_bad.append(eid)
    for label, bad in (("carry no evidence_ref at all", no_refs),
                       ("cite an evidence_id that resolves to no evidence row", orphan),
                       ("cite no evidence row with a parseable dated published_at", undated)):
        if bad:
            breaches.append(f"{len(bad)} edge(s) {label} (first: {bad[0]!r}) — "
                            f"an edge whose evidence cannot be dated is knowledge from "
                            f"nowhere (semantic-leakage law, §4.4)")
    if llm_bad:
        breaches.append(
            f"{len(llm_bad)} llm_proposed_ratified edge(s) with no dated evidence "
            f"(first: {llm_bad[0]!r}) — an LLM-assisted edge may cite only dated "
            f"documents (G0.6)")

    # --- identity epochs are ratified, not minted ---------------------------
    ratified: set[tuple[str, str]] = set()
    if breaks_file.exists():
        doc = yaml.safe_load(breaks_file.read_text(encoding="utf-8")) or {}
        for r in doc.get("breaks") or []:
            ratified.add((str(r.get("market", "")).strip().lower(),
                          str(r.get("symbol", "")).strip().upper(),))
    if {"identity_epoch", "node_id"} <= set(nodes.columns):
        for row in nodes.to_dict("records"):
            try:
                epoch = int(row.get("identity_epoch") or 1)
            except (TypeError, ValueError):
                breaches.append(f"node {row.get('node_id')!r}: unreadable identity_epoch")
                continue
            if epoch < 2:
                continue
            nid = str(row.get("node_id"))
            parts = nid.split(":")
            market = parts[1] if len(parts) > 2 else ""
            symbol = parts[2].split("#")[0].upper() if len(parts) > 2 else ""
            if (market, symbol) not in ratified:
                breaches.append(
                    f"node {nid!r} claims identity_epoch {epoch} with no ratified row in "
                    f"{breaks_file.name} — an identity break is a curated act, never a "
                    f"builder's decision")

    # --- capability side-car (optional; absent is pre-first-run) --------------
    cap_path = store_dir / "capability.parquet"
    if cap_path.exists():
        try:
            cap = pd.read_parquet(cap_path)
        except Exception as exc:  # noqa: BLE001
            breaches.append(f"capability.parquet unreadable: {exc}")
            cap = None
        if cap is not None:
            cap_breaches, cap_notices = _check_columns(
                cap, store.CAPABILITY_COLUMNS, "capability")
            breaches += cap_breaches
            notices += cap_notices
            breaches += _check_dtypes(cap, CAPABILITY_DTYPES, "capability")
            breaches += _check_enums(cap, CAPABILITY_ENUMS, "capability")
            breaches += _check_schema(cap, "capability", "capability")
            if "node_id" in cap.columns and kinds:
                orphan = sorted({str(n) for n in cap["node_id"]} - set(kinds))
                if orphan:
                    breaches.append(
                        f"{len(orphan)} capability row(s) classify a node that has no "
                        f"node row (first: {orphan[0]!r}) — a classification of nothing")
            if "capability_basis" in cap.columns:
                blank = [str(n) for n, b in zip(cap.get("node_id", []),
                                                cap["capability_basis"])
                         if _is_null(b) or not str(b).strip()]
                if blank:
                    breaches.append(
                        f"{len(blank)} capability row(s) carry no basis (first: "
                        f"{blank[0]!r}) — a classification whose rule is not named is a "
                        f"label, and W3B has to be able to re-derive it")
            if "capability" in cap.columns:
                minted = {str(v) for v in cap["capability"]}
                if "measurable" in minted:
                    notices.append(
                        "[capability promoted itself] capability=measurable is present — that verdict is minted only "
                        "after a preregistered measurement (W3B). If this is W3A's own "
                        "output, the rule promoted itself")
    elif "local_theme" in set(kinds.values()):
        # Silent when there is nothing to classify. Loud once local themes exist and
        # nothing has classified them: that is a build that stopped half way, not a
        # store that predates the side-car.
        notices.append(
            "[capability side-car MISSING — half-finished build] local_theme nodes exist but capability.parquet does not — the side-car is "
            "re-derived by every build (python -m scripts.build_theme_graph); its "
            "absence means nothing has classified them yet")

    # --- V4-D2A: identity resolution side-car (optional; absent is pre-first-run) ---
    idres_path = store_dir / "identity_resolution.parquet"
    if idres_path.exists():
        try:
            idres = pd.read_parquet(idres_path)
        except Exception as exc:  # noqa: BLE001
            breaches.append(f"identity_resolution.parquet unreadable: {exc}")
            idres = None
        if idres is not None:
            idr_breaches, idr_notices = _check_columns(
                idres, store.IDENTITY_RESOLUTION_COLUMNS, "identity_resolution")
            breaches += idr_breaches
            notices += idr_notices
            breaches += _check_dtypes(idres, IDENTITY_RESOLUTION_DTYPES, "identity_resolution")
            breaches += _check_enums(idres, IDENTITY_RESOLUTION_ENUMS, "identity_resolution")
            breaches += _check_schema(idres, "identity_resolution", "identity_resolution")

            # Current view: max computed_at per node_id — same collapse as
            # store.read_identity_resolution(latest=True).
            if {"node_id", "computed_at"} <= set(idres.columns):
                ordered = idres.sort_values(["node_id", "computed_at"], kind="stable")
                latest_idr = ordered.drop_duplicates(subset=["node_id"], keep="last")
            else:
                latest_idr = idres

            company_ids = {n for n, k in kinds.items() if k == "company"} if kinds else set()

            # (b) orphan rows — a resolution of a node the store has no row for.
            if "node_id" in latest_idr.columns and kinds:
                orphan = sorted({str(n) for n in latest_idr["node_id"]} - set(kinds))
                if orphan:
                    breaches.append(
                        f"{len(orphan)} identity_resolution row(s) classify a node that "
                        f"has no node row (first: {orphan[0]!r}) — a resolution of nothing")

            # (c) sidecar present + a company-kind node with no CURRENT row = breach
            # (Sol attack 17). NOT_IN_MASTER is the honest refusal state; an ABSENT row
            # is not.
            if company_ids and "node_id" in latest_idr.columns:
                covered = {str(n) for n in latest_idr["node_id"]}
                missing = sorted(company_ids - covered)
                if missing:
                    breaches.append(
                        f"{len(missing)} company node(s) have no current "
                        f"identity_resolution row (first: {missing[0]!r}) — the side-car "
                        f"is present, so every company node must have been resolved (even "
                        f"to a refusal)")

            # V4-D2B1: issuer_id is now nullable on a RESOLVED row too (the master's
            # own issuer_state can be NO_ISSUER_EVIDENCE with no legacy value). Load
            # security_master's issuer_state ONCE, read-only, so the biconditional
            # (f) and the master-membership check (g) can both consult it. Absent /
            # unreadable master degrades gracefully for (f) (falls back to requiring
            # issuer_id present, the pre-D2B1 law) and is a breach for (g) exactly as
            # before it was, unchanged.
            master_path = store_dir.parent / "reference" / "security_master.parquet"
            issuer_state_by_security: dict[str, str] | None = None
            if master_path.exists():
                try:
                    master_ids_states = pd.read_parquet(
                        master_path, columns=["security_id", "issuer_state"])
                    issuer_state_by_security = dict(
                        zip(master_ids_states["security_id"].astype(str),
                            master_ids_states["issuer_state"].astype(str)))
                except Exception:  # noqa: BLE001 — degrade to strict-issuer_id below
                    issuer_state_by_security = None

            # (f) F3a — state<->ids biconditional, amended for the D2B1 issuer axis:
            # RESOLVED must carry security_id+listing_key ALWAYS and no refusal_reason;
            # issuer_id is required UNLESS the master's own issuer_state for that
            # security is NO_ISSUER_EVIDENCE (an unevidenced legacy/new row — the master
            # itself says so, this is not a bridge defect). Every non-RESOLVED state
            # must carry NONE of the ids and a refusal_reason. The derivation code
            # cannot produce a violation, but a hand-edited or truncated artifact could
            # — this catches artifact corruption the earlier checks are blind to.
            if {"resolution_state", "issuer_id", "security_id", "listing_key",
                "refusal_reason", "node_id"} <= set(latest_idr.columns):
                bad_biconditional: list[str] = []
                for nid, st, iss, sec, lk, reason in zip(
                        latest_idr["node_id"], latest_idr["resolution_state"],
                        latest_idr["issuer_id"], latest_idr["security_id"],
                        latest_idr["listing_key"], latest_idr["refusal_reason"]):
                    reason_present = not _is_null(reason)
                    if str(st) == "RESOLVED":
                        sec_lk_present = not _is_null(sec) and not _is_null(lk)
                        issuer_ok = not _is_null(iss)
                        if not issuer_ok and issuer_state_by_security is not None:
                            issuer_ok = (
                                issuer_state_by_security.get(str(sec))
                                == "NO_ISSUER_EVIDENCE"
                            )
                        ok = sec_lk_present and issuer_ok and not reason_present
                    else:
                        ids_present = (not _is_null(iss) and not _is_null(sec)
                                       and not _is_null(lk))
                        ok = not ids_present and reason_present
                    if not ok:
                        bad_biconditional.append(str(nid))
                if bad_biconditional:
                    breaches.append(
                        f"{len(bad_biconditional)} identity_resolution row(s) violate the "
                        f"state<->ids biconditional (first: {bad_biconditional[0]!r}) — "
                        "RESOLVED must carry security_id+listing_key and no refusal_reason "
                        "(issuer_id required UNLESS the master's issuer_state for that "
                        "security is NO_ISSUER_EVIDENCE); every other state must carry "
                        "none of the ids and a refusal_reason (F3a, artifact-corruption "
                        "guard, D2B1-amended)")

            # (g) F3a — master membership: every RESOLVED security_id must exist in the
            # committed data/reference/security_master.parquet, loaded read-only here.
            # Absent master = skipped, never a breach (sparse checkout / pre-DOS-1.1
            # fixtures carry no data/reference/ at all).
            if master_path.exists() and {"resolution_state", "security_id", "node_id"} \
                    <= set(latest_idr.columns):
                try:
                    known_security_ids: set[str] | None = set(
                        pd.read_parquet(master_path, columns=["security_id"])
                          ["security_id"].astype(str))
                except Exception as exc:  # noqa: BLE001 — unreadable master is a breach
                    breaches.append(
                        "security_master.parquet unreadable for the identity_resolution "
                        f"master-membership check: {exc}")
                    known_security_ids = None
                if known_security_ids is not None:
                    orphan_security: list[str] = []
                    for nid, st, sec in zip(latest_idr["node_id"],
                                            latest_idr["resolution_state"],
                                            latest_idr["security_id"]):
                        if str(st) == "RESOLVED" and not _is_null(sec) \
                                and str(sec) not in known_security_ids:
                            orphan_security.append(str(nid))
                    if orphan_security:
                        breaches.append(
                            f"{len(orphan_security)} RESOLVED identity_resolution row(s) "
                            "reference a security_id absent from the committed security "
                            f"master (first: {orphan_security[0]!r}) — artifact corruption "
                            "(F3a, master-membership guard)")

            # (e) census — printed every run, never a breach. Node-sets resolving to the
            # same security_id are the machine-visible duplicates the bridge exists to
            # expose (SATS/ECHO, FI/FISV).
            state_counts: dict[str, int] = {}
            if "resolution_state" in latest_idr.columns:
                for v in latest_idr["resolution_state"].tolist():
                    key = str(v)
                    state_counts[key] = state_counts.get(key, 0) + 1
            entity_conflicts = state_counts.get("ENTITY_TYPE_CONFLICT", 0)
            dup_groups: dict[str, list[str]] = {}
            if {"security_id", "node_id"} <= set(latest_idr.columns):
                by_sec: dict[str, list[str]] = {}
                for nid, sec in zip(latest_idr["node_id"], latest_idr["security_id"]):
                    if _is_null(sec):
                        continue
                    by_sec.setdefault(str(sec), []).append(str(nid))
                dup_groups = {sec: sorted(ns) for sec, ns in by_sec.items() if len(ns) > 1}
            notices.append(
                "[identity resolution census] "
                f"company nodes={len(company_ids)}, projection rows={len(latest_idr)}, "
                f"by state={json.dumps(state_counts, sort_keys=True)}, "
                f"entity_type_conflicts={entity_conflicts}, "
                f"same-security node-sets={json.dumps(dup_groups, sort_keys=True)}")
    elif kinds and "company" in set(kinds.values()):
        # (d) absent sidecar with company nodes present: a build that stopped half way,
        # not a store that predates the side-car — same posture as the capability block.
        notices.append(
            "[identity resolution side-car MISSING — half-finished build] company nodes "
            "exist but identity_resolution.parquet does not — the side-car is re-derived "
            "by every build (python -m scripts.build_theme_graph); its absence means "
            "nothing has resolved them yet")

    # --- closed-edge survivorship -------------------------------------------
    if {"edge_id", "valid_to", "belief_time"} <= set(edges.columns):
        closed = {str(e) for e, v in zip(edges["edge_id"], edges["valid_to"])
                  if not _is_null(v)}
        if closed:
            ordered = edges.sort_values(["edge_id", "belief_time", "computed_at"],
                                        kind="stable")
            latest = ordered.drop_duplicates(subset=["edge_id"], keep="last")
            resolvable = {str(e) for e in latest["edge_id"]}
            vanished = sorted(closed - resolvable)
            if vanished:
                breaches.append(
                    f"{len(vanished)} closed edge(s) do not resolve in the latest-belief "
                    f"view (first: {vanished[0]!r}) — a closed membership must stay "
                    f"findable; dead members never leave the denominator")

    return breaches, notices


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def run(*, strict: bool, store_dir: Path | None = None,
        breaks_file: Path | None = None) -> int:
    sdir = store_dir or store.store_dir()
    bfile = breaks_file or identity.breaks_path()
    breaches, notices = audit(sdir, bfile)
    for n in notices:
        # Bare print, line-start, flushed: a logger prefixes the line and GitHub
        # silently drops the annotation (tests/test_gh_annotation_line_start.py).
        # Distinct titles per class (diff-review F4): the DESIGNED licensing notice
        # must never visually mask a half-finished build or a self-promoted verdict.
        m = re.match(r"^\[([^\]]+)\]\s*(.*)$", n, flags=re.DOTALL)
        if m:
            print(f"::notice title=theme graph — {m.group(1)}::{m.group(2)}", flush=True)
        else:
            print(f"::notice title=theme graph indeterminate::{n}", flush=True)
    if not breaches:
        if not notices:
            print("theme graph contracts OK — columns, schemas, enums, evidence "
                  "resolution, identity epochs and closed-edge survivorship all hold")
        return 0
    print("::warning title=theme graph contract breach::"
          + "; ".join(breaches[:8])
          + (f" (+{len(breaches) - 8} more)" if len(breaches) > 8 else "")
          + ". The graph is display-tier, so nothing decides on it — but every one of "
            "these is a QUIET failure: a drifted column, an evidence ref pointing at "
            "nothing, or a closed membership that stopped resolving does not raise, it "
            "just makes the answers wrong.", flush=True)
    return 1 if strict else 0


# ---------------------------------------------------------------------------
# Selftest — each incident rebuilt as a fixture
# ---------------------------------------------------------------------------

def _write_idres(tmp: Path, rows: list[dict]) -> None:
    """Write ``identity_resolution.parquet`` beside an existing fixture store dir."""
    pd.DataFrame(rows).reindex(columns=list(store.IDENTITY_RESOLUTION_COLUMNS)).to_parquet(
        tmp / "identity_resolution.parquet", index=False)


def _clean_idres_row(*, node_id: str = "co:us:AAA", market_scope: str = "us",
                     symbol: str = "AAA", state: str = "NOT_IN_MASTER") -> dict:
    stamp = "2024-01-02T00:00:00Z"
    return {
        "schema": "gmi.identity_resolution/v1", "node_id": node_id, "graph_kind": "company",
        "market_scope": market_scope, "graph_identity_epoch": 1,
        "source_native_symbol": symbol, "resolution_asof": "2024-01-01",
        "resolution_state": state, "issuer_id": None, "security_id": None,
        "listing_key": None, "join_method": "refused", "master_generated_at": None,
        "master_symbol_directory_snapshot": None, "master_code_version": None,
        "refusal_reason": "fixture: no master row", "source_receipts": "{}",
        "computed_at": stamp, "engine_version": store.ENGINE_VERSION,
    }


def _fixture(tmp: Path, *, nodes: list[dict], edges: list[dict],
             evidence: list[dict]) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(nodes).reindex(columns=list(store.NODE_COLUMNS)).to_parquet(
        tmp / "nodes.parquet", index=False)
    pd.DataFrame(edges).reindex(columns=list(store.EDGE_COLUMNS)).to_parquet(
        tmp / "edges.parquet", index=False)
    pd.DataFrame(evidence).reindex(columns=list(store.EVIDENCE_COLUMNS)).to_parquet(
        tmp / "evidence.parquet", index=False)
    return tmp


def _clean_rows() -> tuple[list[dict], list[dict], list[dict]]:
    """A minimal, contract-clean store. Dates are FIXTURE constants with no relation to
    the wall clock — a guard that drifts red on a calendar boundary is a scheduled red."""
    stamp = "2024-01-02T00:00:00Z"
    ev = [{"evidence_id": "ev:0000000000000001", "kind": "operator_curation",
           "published_at": "2024-01-01", "effective_at": None,
           "source_ref": "fixture://membership.json",
           "licensing_internal_ok": True, "licensing_display_ok": True,
           "licensing_redistribution_ok": True, "retention": None,
           "computed_at": stamp}]
    nodes = [
        {"node_id": "co:us:AAA", "kind": "company", "name_en": "AAA", "name_zh": None,
         "market_scope": "us", "tier": None, "status": "canonical", "merged_into": None,
         "birth_date": None, "retire_date": None, "identity_epoch": 1,
         "external_ids": "{}", "provenance": "fixture", "computed_at": stamp,
         "engine_version": store.ENGINE_VERSION},
        {"node_id": "basket:baskets:demo", "kind": "basket", "name_en": "Demo",
         "name_zh": None, "market_scope": "us", "tier": None, "status": "canonical",
         "merged_into": None, "birth_date": None, "retire_date": None,
         "identity_epoch": 1, "external_ids": "{}", "provenance": "fixture",
         "computed_at": stamp, "engine_version": store.ENGINE_VERSION},
    ]
    edge = {"edge_id": "member_of:co:us:AAA->basket:baskets:demo@2024-01-01",
            "type": "MEMBER_OF", "src": "co:us:AAA", "dst": "basket:baskets:demo",
            "valid_from": "2024-01-01", "valid_to": None, "evidence_time": "2024-01-01",
            "belief_time": "2024-01-02", "era": "reconstruction",
            "source_class": "curated", "date_provenance": "curated_changelog",
            "evidence_refs": ["ev:0000000000000001"],
            "confidence_basis": "membership_doc.v1",
            "computed_at": stamp, "engine_version": store.ENGINE_VERSION}
    for f in store.RESERVED_EDGE_FIELDS:
        edge[f] = None
    return nodes, [edge], ev


def selftest(tmp_root: Path | None = None) -> int:
    import tempfile  # noqa: PLC0415

    tmp_root = tmp_root or Path(tempfile.mkdtemp(prefix="theme_graph_selftest_"))
    tmp_root.mkdir(parents=True, exist_ok=True)
    empty_breaks = tmp_root / "no_breaks.yml"
    empty_breaks.write_text("breaks: []\n", encoding="utf-8")
    checks: list[tuple[bool, str]] = []

    nodes, edges, ev = _clean_rows()
    clean = _fixture(tmp_root / "clean", nodes=nodes, edges=edges, evidence=ev)
    _write_idres(clean, [_clean_idres_row()])  # keeps the fully-clean store fully clean
    b, n = audit(clean, empty_breaks)
    # The identity-resolution CENSUS is a designed, always-on notice (§7e — printed
    # every run, never an incident), so it is the one notice a "fully clean" store may
    # still carry.
    n_incidents = [x for x in n if "identity resolution census" not in x]
    checks.append((not b and not n_incidents,
                   f"a contract-clean store must pass cleanly: {b or n_incidents}"))

    b, n = audit(tmp_root / "absent", empty_breaks)
    checks.append((not b and bool(n),
                   "a missing store is INDETERMINATE, never a breach"))

    nodes, edges, ev = _clean_rows()
    edges[0]["evidence_refs"] = ["ev:doesnotexist0000"]
    d = _fixture(tmp_root / "orphan", nodes=nodes, edges=edges, evidence=ev)
    checks.append((any("resolves to no evidence row" in x for x in audit(d, empty_breaks)[0]),
                   "an evidence ref pointing at nothing must breach"))

    nodes, edges, ev = _clean_rows()
    ev[0]["published_at"] = "not-a-date"
    edges[0]["source_class"] = "llm_proposed_ratified"
    d = _fixture(tmp_root / "llm", nodes=nodes, edges=edges, evidence=ev)
    breaches = audit(d, empty_breaks)[0]
    checks.append((any("llm_proposed_ratified" in x for x in breaches),
                   "an LLM-ratified edge with undated evidence must breach"))
    checks.append((any("dated published_at" in x for x in breaches),
                   "undated evidence must breach for ANY source_class, not only LLM ones"))

    nodes, edges, ev = _clean_rows()
    nodes[0]["identity_epoch"] = 2
    nodes[0]["node_id"] = "co:us:AAA#2"
    edges[0]["src"] = "co:us:AAA#2"
    edges[0]["edge_id"] = "member_of:co:us:AAA#2->basket:baskets:demo@2024-01-01"
    d = _fixture(tmp_root / "epoch", nodes=nodes, edges=edges, evidence=ev)
    checks.append((any("no ratified row" in x for x in audit(d, empty_breaks)[0]),
                   "identity_epoch 2 without a ratified break row must breach"))

    # A closed edge that no longer resolves: a LATER belief re-opened the same edge_id,
    # so the closure exists in history but not in the view any consumer reads.
    nodes, edges, ev = _clean_rows()
    closed = dict(edges[0])
    closed["valid_to"] = "2024-02-01"
    closed["belief_time"] = "2024-02-02"
    closed["edge_id"] = "member_of:co:us:AAA->basket:baskets:demo@2024-01-02"
    d = _fixture(tmp_root / "vanished", nodes=nodes, edges=[*edges, closed], evidence=ev)
    before = audit(d, empty_breaks)[0]
    checks.append((not before, f"the two-row control must be clean: {before}"))
    dropped = pd.read_parquet(d / "edges.parquet")
    dropped = dropped[dropped["valid_to"].isna()]
    survivor = dict(closed)
    survivor["valid_to"] = None
    survivor["belief_time"] = "2024-03-03"
    d2 = _fixture(tmp_root / "vanished2", nodes=nodes,
                  edges=[*dropped.to_dict("records"), closed], evidence=ev)
    pd.DataFrame([*dropped.to_dict("records"), closed, survivor]).reindex(
        columns=list(store.EDGE_COLUMNS)).to_parquet(d2 / "edges.parquet", index=False)
    checks.append((not audit(d2, empty_breaks)[0],
                   "a re-opened edge is legal — the closure row survives on disk"))

    # --- W3A: the local plane ------------------------------------------------
    nodes, edges, ev = _clean_rows()
    nodes.append({**nodes[0], "node_id": "ltheme:finviz:aicompute", "kind": "local_theme",
                  "source_meta": json.dumps({"rights_family": "family_nobody_reviewed"})})
    d = _fixture(tmp_root / "rights", nodes=nodes, edges=edges, evidence=ev)
    checks.append((any("fails CLOSED" in x for x in audit(d, empty_breaks)[0]),
                   "a source family with no registry row must fail CLOSED"))

    nodes, edges, ev = _clean_rows()
    nodes.append({**nodes[0], "node_id": "basket:finviz_themes:aicompute",
                  "kind": "basket"})
    d = _fixture(tmp_root / "finviz_basket", nodes=nodes, edges=edges, evidence=ev)
    checks.append((any("finviz_themes namespace" in x for x in audit(d, empty_breaks)[0]),
                   "a basket id in the company-identity-only suite must breach"))

    nodes, edges, ev = _clean_rows()
    nodes.append({**nodes[0], "node_id": "ltheme:finviz:BAD KEY", "kind": "local_theme"})
    d = _fixture(tmp_root / "ltheme_grammar", nodes=nodes, edges=edges, evidence=ev)
    checks.append((any("outside the grammar" in x for x in audit(d, empty_breaks)[0]),
                   "a local-theme id outside the grammar must breach"))

    nodes, edges, ev = _clean_rows()
    nodes.append({**nodes[0], "node_id": "theme:solar", "kind": "theme"})
    smuggled = {**edges[0], "dst": "theme:solar",
                "edge_id": "member_of:co:us:AAA->theme:solar@2024-01-01"}
    d = _fixture(tmp_root / "pairing", nodes=nodes, edges=[*edges, smuggled], evidence=ev)
    checks.append((any("not a pairing this type may carry" in x
                       for x in audit(d, empty_breaks)[0]),
                   "a company→theme MEMBER_OF is the refused derived edge and must breach"))

    # A store written before the additive columns existed: a NOTICE, never a breach —
    # v1 is additive-only, so that shape was valid when it was written.
    nodes, edges, ev = _clean_rows()
    d = _fixture(tmp_root / "premigration", nodes=nodes, edges=edges, evidence=ev)
    pd.read_parquet(d / "nodes.parquet").drop(columns=["source_meta"]).to_parquet(
        d / "nodes.parquet", index=False)
    b, n = audit(d, empty_breaks)
    checks.append((not b and any("predates the W3A additive column" in x for x in n),
                   f"a pre-migration store is INDETERMINATE, never a breach: {b}"))

    # --- V4-D2A: identity resolution side-car ---------------------------------
    nodes, edges, ev = _clean_rows()
    d = _fixture(tmp_root / "idres_clean", nodes=nodes, edges=edges, evidence=ev)
    _write_idres(d, [_clean_idres_row()])
    b, n = audit(d, empty_breaks)
    checks.append((not b, f"a company node with a current identity_resolution row must "
                          f"pass cleanly: {b}"))
    checks.append((any("identity resolution census" in x for x in n),
                   "the identity-resolution census must be printed every run"))

    nodes, edges, ev = _clean_rows()
    d = _fixture(tmp_root / "idres_absent", nodes=nodes, edges=edges, evidence=ev)
    b, n = audit(d, empty_breaks)
    checks.append((not b and any("half-finished build" in x for x in n),
                   "company nodes with no identity_resolution.parquet must be a NOTICE, "
                   "never a breach"))

    nodes, edges, ev = _clean_rows()
    d = _fixture(tmp_root / "idres_missing_row", nodes=nodes, edges=edges, evidence=ev)
    _write_idres(d, [])
    b, n = audit(d, empty_breaks)
    checks.append((any("no current identity_resolution row" in x for x in b),
                   "a sidecar present with a company node uncovered must breach (Sol "
                   "attack 17)"))

    nodes, edges, ev = _clean_rows()
    d = _fixture(tmp_root / "idres_orphan", nodes=nodes, edges=edges, evidence=ev)
    _write_idres(d, [_clean_idres_row(),
                     _clean_idres_row(node_id="co:us:GHOST", symbol="GHOST")])
    b, n = audit(d, empty_breaks)
    checks.append((any("resolution of nothing" in x for x in b),
                   "an identity_resolution row for a node with no node row must breach"))

    nodes, edges, ev = _clean_rows()
    d = _fixture(tmp_root / "idres_notinmaster_ok", nodes=nodes, edges=edges, evidence=ev)
    _write_idres(d, [_clean_idres_row(state="NOT_IN_MASTER")])
    b, n = audit(d, empty_breaks)
    checks.append((not b, f"NOT_IN_MASTER is a required honest state, never a guard "
                          f"failure: {b}"))

    # --- F3a (post-adversarial-review): artifact-corruption breach classes ---------
    # A RESOLVED row corrupted to carry no ids (and a stray refusal_reason) breaches
    # the state<->ids biconditional — the derivation code cannot produce this, but a
    # hand-edited or truncated parquet could.
    nodes, edges, ev = _clean_rows()
    d = _fixture(tmp_root / "idres_biconditional", nodes=nodes, edges=edges, evidence=ev)
    _write_idres(d, [_clean_idres_row(state="RESOLVED")])
    b, n = audit(d, empty_breaks)
    checks.append((any("state<->ids biconditional" in x for x in b),
                   f"a RESOLVED row missing its ids (or carrying a refusal_reason) must "
                   f"breach the state<->ids biconditional (F3a): {b}"))

    # A RESOLVED row whose security_id has no row in the committed security master —
    # the master-membership guard, loaded read-only from data/reference/.
    nodes, edges, ev = _clean_rows()
    d = _fixture(tmp_root / "idres_master_membership", nodes=nodes, edges=edges, evidence=ev)
    corrupt = _clean_idres_row(state="RESOLVED")
    corrupt.update({
        "issuer_id": "ISS:US-XNYS-GHOST", "security_id": "SEC:US-XNYS-GHOST",
        "listing_key": "US-XNYS-GHOST", "join_method": "master_inception_exact",
        "refusal_reason": None,
        "source_receipts": '{"security_id":"SEC:US-XNYS-GHOST"}',
    })
    _write_idres(d, [corrupt])
    ref = tmp_root / "reference"
    ref.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{
        "security_id": "SEC:US-XNYS-REAL", "issuer_id": "ISS:US-XNYS-REAL",
        "listing_key": "US-XNYS-REAL", "country": "US", "mic": "XNYS",
        "inception_code": "REAL",
    }]).to_parquet(ref / "security_master.parquet", index=False)
    b, n = audit(d, empty_breaks)
    checks.append((any("absent from the committed security master" in x for x in b),
                   f"a RESOLVED security_id absent from the committed security master "
                   f"must breach (F3a, master-membership): {b}"))

    bad = [m for ok, m in checks if not ok]
    for m in bad:
        print(f"selftest FAIL: {m}")
    print("check_theme_graph_contracts selftest: "
          + ("OK" if not bad else f"{len(bad)} failure(s)"))
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--strict", action="store_true",
                    help="return 1 on a breach (CI); default is advisory rc 0")
    ap.add_argument("--selftest", action="store_true",
                    help="rebuild each incident as a fixture and prove the guard sees it")
    a = ap.parse_args(argv)
    return selftest() if a.selftest else run(strict=a.strict)


if __name__ == "__main__":
    raise SystemExit(main())
