"""One-shot curated GMI identity correction lineage (V4-D2B3).

Frozen contract: ``research/prophet_v4/d2/D2B3_FROZEN_CONTRACT_2026-08-21.md`` (§2-§9,
AMENDMENT §1/§2). Performs, EXACTLY ONCE against the COMMITTED theme-graph store, the
two correction shapes the contract authorizes — both registry/structure-driven, with
NO ticker literal anywhere in this module's logic (a symbol this script acts on comes
either from ``config/theme_graph_identity_breaks.yml`` or from the committed store's
own company/etf symbol collision, never a hard-coded name):

  IDENTITY_BREAK shape (§3, GOLD)
      For every RATIFIED row in the breaks registry whose ``prior_node_retired_as``
      node EXISTS in ``nodes.parquet``: append a ``node_lifecycle`` retirement row
      (reason=identity_break, retire_date = the row's own ``break_date`` VERBATIM —
      §9 dates law) and TRUNCATE every open MEMBER_OF edge that node is the src of at
      that same break_date. A prior node ABSENT from ``nodes.parquet`` is a no-op —
      nothing is minted, nothing breaches (§5, the ABX generality control).

  ENTITY_TYPE_CONFLICT shape (§4, IBIT)
      For every company-kind node whose symbol ALSO exists as an etf-kind node in the
      committed store (the same same-generation structural test R-D2B3-4(a) uses at
      bake time, applied once here against the committed nodes.parquet): append a
      ``node_lifecycle`` retirement row (reason=entity_type_conflict, retire_date =
      this run's own execution date — there is no world-event break date, §4) and
      ANNUL every open MEMBER_OF edge that node is the src of (``valid_to :=
      valid_from`` — an empty interval, deliberately distinct from the identity_break
      TRUNCATION above).

Both shapes use ONLY the EXISTING append-only lineages (R-D2B3-1 node_lifecycle,
R-D2B3-3 edge belief lineage) — ``nodes.parquet`` is never written by this script
(NODE_KEY is write-once; a same-id append is silently dropped, and this script never
even tries).

DATA OS NON-INTERFERENCE (§8, commission OUT OF SCOPE). This module imports ONLY
``engine.theme_graph.identity`` and ``engine.theme_graph.store`` — never
``engine.theme_graph.materialize``/``identity_resolution`` (which transitively import
``lib.dataos.identity``) and never ``scripts.build_security_master``. Nothing here
reads or writes anything under ``data/reference/``; the IBIT conflict's evidence field
cites GMI's OWN already-computed ``data/theme_graph/identity_resolution.parquet``
sidecar receipts (if present) — a GMI artifact, not a Data OS one — never the Data OS
master directly. ``tests/test_theme_graph_lifecycle.py`` pins both invariants
by static source inspection.

IDEMPOTENT BY CONSTRUCTION. A node already carrying a ``retired``/``merged`` lifecycle
row is skipped (reported, never re-appended) — safe to re-run. ``append_rows`` is
itself keep-first on (node_id, computed_at) / (edge_id, belief_time), so even a
same-day double-invocation adds nothing twice.

Run ONCE, direct store appends via the same ``allow_backfill=True`` bypass the house
one-shot backfill uses (never an environment default — store.py's own law):

    python -m scripts.correct_gmi_identity_lineage [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.theme_graph import identity, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("correct_gmi_identity_lineage")

CONTRACT_DOC = "research/prophet_v4/d2/D2B3_FROZEN_CONTRACT_2026-08-21.md"

#: Duplicated from engine.theme_graph.materialize.evidence_id_for ON PURPOSE (same
#: algorithm, same output shape) rather than imported — importing materialize would
#: transitively pull in identity_resolution.py -> lib.dataos.identity, and this module
#: must import NOTHING that reads data/reference/ (§8, module docstring).
def _evidence_id_for(kind: str, source_ref: str, published_at: str) -> str:
    digest = hashlib.sha1(f"{kind}|{source_ref}|{published_at}".encode()).hexdigest()
    return "ev:" + digest[:16]


def _now() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    computed_at = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return today, computed_at


def _node_symbol(node: dict) -> str | None:
    try:
        ext = json.loads(node.get("external_ids") or "{}")
    except Exception:  # noqa: BLE001 — malformed external_ids is not fatal here
        return None
    sym = ext.get("symbol")
    return str(sym).strip().upper() if sym else None


def _load_breaks_rows(breaks_file: Path) -> list[dict]:
    if not breaks_file.exists():
        return []
    doc = yaml.safe_load(breaks_file.read_text(encoding="utf-8")) or {}
    return list(doc.get("breaks") or [])


# ---------------------------------------------------------------------------
# Targets — both shapes are STRUCTURAL/REGISTRY-DRIVEN, never a ticker literal
# ---------------------------------------------------------------------------

def identity_break_targets(nodes_df: pd.DataFrame, breaks_rows: list[dict]) -> list[dict]:
    """Ratified breaks whose prior node EXISTS in the committed store (§3; §5 ABX —
    an absent prior node is silently skipped, never fabricated)."""
    known = set(nodes_df["node_id"].astype(str)) if not nodes_df.empty else set()
    out: list[dict] = []
    for r in breaks_rows:
        prior = str(r.get("prior_node_retired_as") or "").strip()
        if not prior or prior not in known:
            continue
        out.append({
            "node_id": prior,
            "break_date": str(r.get("break_date") or "").strip() or None,
            "market": str(r.get("market", "")).strip().lower(),
            "symbol": str(r.get("symbol", "")).strip().upper(),
            "ratified_by": str(r.get("ratified_by") or "").strip() or "unknown",
            "ratified_at": str(r.get("ratified_at") or "").strip() or None,
        })
    return out


def entity_conflict_targets(nodes_df: pd.DataFrame) -> list[dict]:
    """Company-kind nodes whose symbol also exists as an etf-kind node in the
    committed store — the same structural test R-D2B3-4(a) uses at bake time, applied
    once here. No ticker literal: the collision is discovered from the data."""
    if nodes_df.empty:
        return []
    records = nodes_df.to_dict("records")
    etf_syms = {sym for n in records if str(n.get("kind")) == "etf"
                and (sym := _node_symbol(n))}
    out: list[dict] = []
    for n in records:
        if str(n.get("kind")) != "company":
            continue
        sym = _node_symbol(n)
        if sym and sym in etf_syms:
            out.append({"node_id": str(n["node_id"]), "symbol": sym})
    return out


def _conflict_evidence(node_id: str, symbol: str) -> str:
    """Machine-visible pointer for an entity_type_conflict row — the conflicting etf
    node id, plus whatever the D2A identity_resolution SIDE-CAR (a GMI artifact, never
    Data OS) already recorded for this node's ENTITY_TYPE_CONFLICT resolution."""
    payload: dict = {
        "conflicting_etf_node": f"etf:{symbol}",
        "detection": ("structural same-generation symbol collision (D2B3 R-D2B3-4(a) "
                      "rule, applied once against the committed store)"),
    }
    idres = store.read_identity_resolution(latest=True)
    if not idres.empty:
        hit = idres[idres["node_id"].astype(str) == node_id]
        if not hit.empty:
            receipts = hit.iloc[0].get("source_receipts")
            if receipts:
                payload["identity_resolution_source_receipts"] = str(receipts)
            state = hit.iloc[0].get("resolution_state")
            if state:
                payload["identity_resolution_state"] = str(state)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _open_member_of_edges(live_edges: pd.DataFrame, node_id: str) -> list[dict]:
    if live_edges.empty:
        return []
    mask = ((live_edges["type"].astype(str) == "MEMBER_OF")
            & (live_edges["src"].astype(str) == node_id)
            & (live_edges["valid_to"].isna()))
    return live_edges[mask].to_dict("records")


def _corrected_edge_row(prior: dict, *, valid_to: str, today: str, computed_at: str,
                        extra_evidence_id: str) -> dict:
    """A new belief row for the SAME edge_id (R-D2B3-3) — every other field carried
    over from the prior open row except valid_to/belief_time/computed_at, and the
    correction's own evidence NAMED alongside the original refs (nothing dropped)."""
    row = dict(prior)
    row["valid_to"] = valid_to
    row["belief_time"] = today
    row["computed_at"] = computed_at
    prior_refs = [str(r) for r in (prior.get("evidence_refs") or [])]
    row["evidence_refs"] = (prior_refs + [extra_evidence_id]
                            if extra_evidence_id not in prior_refs else prior_refs)
    row["engine_version"] = store.ENGINE_VERSION
    return row


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def compute_correction(*, nodes_df: pd.DataFrame, live_edges: pd.DataFrame,
                       breaks_rows: list[dict], already_retired: set[str],
                       today: str, computed_at: str
                       ) -> tuple[list[dict], list[dict], list[dict], dict]:
    """Pure: no store read/write beyond what the caller already loaded. Returns
    (lifecycle_rows, edge_rows, evidence_rows, receipt)."""
    lifecycle_rows: list[dict] = []
    edge_rows: list[dict] = []
    evidence_rows: list[dict] = []
    receipt: dict = {"identity_break": [], "entity_type_conflict": [],
                     "skipped_already_retired": []}

    for target in identity_break_targets(nodes_df, breaks_rows):
        node_id = target["node_id"]
        if node_id in already_retired:
            receipt["skipped_already_retired"].append(node_id)
            continue
        source_ref = f"{identity.BREAKS_FILE}#{target['market']}:{target['symbol']}"
        published_at = target["ratified_at"] or today
        ev_id = _evidence_id_for("operator_curation", source_ref, published_at)
        evidence_rows.append({
            "evidence_id": ev_id, "kind": "operator_curation",
            "published_at": published_at, "effective_at": target["break_date"],
            "source_ref": source_ref,
            "licensing_internal_ok": True, "licensing_display_ok": True,
            "licensing_redistribution_ok": True, "retention": None,
            "computed_at": computed_at, "provider": None, "claim_type": "membership",
        })
        lifecycle_rows.append({
            "schema": "gmi.node_lifecycle/v1", "node_id": node_id, "status": "retired",
            "retire_date": target["break_date"], "merged_into": None,
            "reason": "identity_break",
            "evidence": (f"{identity.BREAKS_FILE}: market={target['market']} "
                        f"symbol={target['symbol']} (ratified_at={target['ratified_at']})"),
            "ratified_by": target["ratified_by"],
            "computed_at": computed_at, "engine_version": store.ENGINE_VERSION,
        })
        truncated_ids: list[str] = []
        for e in _open_member_of_edges(live_edges, node_id):
            corrected = _corrected_edge_row(
                e, valid_to=target["break_date"], today=today, computed_at=computed_at,
                extra_evidence_id=ev_id)
            edge_rows.append(corrected)
            truncated_ids.append(str(corrected["edge_id"]))
        receipt["identity_break"].append({
            "node_id": node_id, "retire_date": target["break_date"],
            "edges_truncated": truncated_ids})

    for target in entity_conflict_targets(nodes_df):
        node_id, symbol = target["node_id"], target["symbol"]
        if node_id in already_retired:
            receipt["skipped_already_retired"].append(node_id)
            continue
        source_ref = f"gmi:entity_type_conflict:{node_id}"
        ev_id = _evidence_id_for("operator_curation", source_ref, today)
        evidence_rows.append({
            "evidence_id": ev_id, "kind": "operator_curation",
            "published_at": today, "effective_at": None, "source_ref": source_ref,
            "licensing_internal_ok": True, "licensing_display_ok": True,
            "licensing_redistribution_ok": True, "retention": None,
            "computed_at": computed_at, "provider": None, "claim_type": "membership",
        })
        lifecycle_rows.append({
            "schema": "gmi.node_lifecycle/v1", "node_id": node_id, "status": "retired",
            "retire_date": today, "merged_into": None, "reason": "entity_type_conflict",
            "evidence": _conflict_evidence(node_id, symbol),
            "ratified_by": (f"V4-D2B3 frozen contract (Sol commission 2026-08-21) — "
                            f"{CONTRACT_DOC} §4"),
            "computed_at": computed_at, "engine_version": store.ENGINE_VERSION,
        })
        annulled_ids: list[str] = []
        for e in _open_member_of_edges(live_edges, node_id):
            corrected = _corrected_edge_row(
                e, valid_to=e["valid_from"], today=today, computed_at=computed_at,
                extra_evidence_id=ev_id)
            edge_rows.append(corrected)
            annulled_ids.append(str(corrected["edge_id"]))
        receipt["entity_type_conflict"].append({
            "node_id": node_id, "retire_date": today, "edges_annulled": annulled_ids})

    return lifecycle_rows, edge_rows, evidence_rows, receipt


def run(*, dry_run: bool) -> int:
    today, computed_at = _now()
    breaks_file = identity.breaks_path()
    breaks_rows = _load_breaks_rows(breaks_file)
    nodes_df = store.read_nodes()               # raw, write-once — never written to
    live_edges = store.read_edges(latest_belief=True)

    existing_lifecycle = store.read_node_lifecycle(latest=True)
    already_retired: set[str] = set()
    if not existing_lifecycle.empty and "status" in existing_lifecycle.columns:
        already_retired = set(existing_lifecycle.loc[
            existing_lifecycle["status"].isin(store.RETIRED_LIKE_STATUSES),
            "node_id"].astype(str))

    lifecycle_rows, edge_rows, evidence_rows, receipt = compute_correction(
        nodes_df=nodes_df, live_edges=live_edges, breaks_rows=breaks_rows,
        already_retired=already_retired, today=today, computed_at=computed_at)

    summary = {
        "dry_run": dry_run, "today": today, "computed_at": computed_at,
        **receipt,
        "counts": {"node_lifecycle": len(lifecycle_rows), "edges": len(edge_rows),
                  "evidence": len(evidence_rows)},
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))

    if dry_run:
        log.info("dry-run: computed %d lifecycle / %d edge / %d evidence row(s); "
                 "nothing written", len(lifecycle_rows), len(edge_rows), len(evidence_rows))
        return 0

    if not lifecycle_rows and not edge_rows and not evidence_rows:
        log.info("nothing to correct — every target already retired or absent "
                 "(idempotent no-op)")
        return 0

    added_lc = store.write_node_lifecycle(lifecycle_rows, allow_backfill=True)
    added_ev = store.write_evidence(evidence_rows, allow_backfill=True)
    added_edges = store.write_edges(edge_rows, allow_backfill=True)

    meta = dict(store.read_meta())
    meta["counts"] = {
        **(meta.get("counts") or {}),
        "nodes": int(len(store.read_nodes())),
        "edges": int(len(store.read_edges(latest_belief=False))),
        "edges_latest_belief": int(len(store.read_edges())),
        "evidence": int(len(store.read_evidence())),
        "capability": int(len(store.read_capability())),
        "identity_resolution": int(len(store.read_identity_resolution())),
        "node_lifecycle": int(len(store.read_node_lifecycle())),
    }
    meta["correction_receipt"] = {
        "script": "scripts.correct_gmi_identity_lineage",
        "run_at": computed_at,
        "rows_appended": {"node_lifecycle": added_lc, "edges": added_edges,
                          "evidence": added_ev},
        **receipt,
    }
    store.write_meta(meta, allow_backfill=True)

    log.info("wrote %d node_lifecycle row(s), %d edge row(s), %d evidence row(s)",
             added_lc, added_edges, added_ev)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="compute and print the correction receipt; write nothing")
    a = ap.parse_args(argv)
    return run(dry_run=a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
