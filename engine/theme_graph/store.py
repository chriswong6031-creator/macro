"""Append-only bitemporal stores for the theme graph (masterplan §4.1).

Three parquets under ``data/theme_graph/`` plus a ``_meta.json`` side-car. All three
are APPEND-ONLY and keep-FIRST on their key: a row that is already there is never
rewritten, so what the system believed on any past date stays recoverable. Closing an
edge interval APPENDS a row carrying ``valid_to`` at a later ``belief_time``; the row
that opened it survives. The current view is the max-``belief_time`` row per
``edge_id`` — :func:`read_edges` with ``latest_belief=True``, which every consumer
should use rather than reading the parquet raw (see contracts/theme_graph/README.md).

Deliberately NOT ``lib.store.upsert``: that helper's ``combine_first`` semantics fill
missing cells from the prior frame, which is exactly wrong here — a new belief that
sets ``valid_to`` back to null (a member re-added) must be able to overwrite in the
VIEW while both rows survive on DISK. The writer is modelled on
``engine/basket_membership_pit.py`` instead: keep-first on an explicit key, written to
a temp file and renamed into place so a killed process never leaves a half parquet.

Lane gate: ledger writes require ``COLLECT_LANE=nightly``, resolved FAIL-CLOSED by a
defaultless resolver (the W1a idiom in ``scripts/build_baskets.py``). A permissive
``os.environ.get("COLLECT_LANE", "nightly")`` would make the gate dead — every render,
closing-bell and hand-run context arrives claiming to BE the nightly lane. The one-shot
backfill bypasses the gate only through an explicit ``allow_backfill=True`` argument,
never through an environment default.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

#: Bumped when the row semantics change. Stamped on every node and edge row.
ENGINE_VERSION = "theme_graph.v1"

#: The only lane permitted to advance these ledgers (nightly is the sole advancer of
#: forward ledgers, house law).
WRITE_LANE = "nightly"

STORE_DIRNAME = "theme_graph"

NODE_COLUMNS: tuple[str, ...] = (
    "node_id", "kind", "name_en", "name_zh", "market_scope", "tier", "status",
    "merged_into", "birth_date", "retire_date", "identity_epoch", "external_ids",
    "provenance", "computed_at", "engine_version",
    # W3A, additive: the source-local plane's own metadata (JSON string, null for every
    # node minted before it). Appended at the END on purpose — v1 is additive-only, and a
    # column inserted mid-tuple would re-order every stored row's contract for no gain.
    "source_meta",
)

EDGE_COLUMNS: tuple[str, ...] = (
    "edge_id", "type", "src", "dst", "valid_from", "valid_to", "evidence_time",
    "belief_time", "era", "source_class", "date_provenance", "evidence_refs",
    "confidence_basis",
    "economic_share", "trading_beta", "attention_share",
    "economic_share_formula_id", "trading_beta_formula_id", "attention_share_formula_id",
    "economic_share_display", "trading_beta_display", "attention_share_display",
    "computed_at", "engine_version",
)

EVIDENCE_COLUMNS: tuple[str, ...] = (
    "evidence_id", "kind", "published_at", "effective_at", "source_ref",
    "licensing_internal_ok", "licensing_display_ok", "licensing_redistribution_ok",
    "retention", "computed_at",
    # W3A, additive: the corroboration class. A third party's CLASSIFICATION of a name is
    # a different kind of claim from a membership document, and it says who made it
    # (provider) and what kind of claim it is (claim_type). Ships empty.
    "provider", "claim_type",
)

#: Capability classification (W3A §9.3) — a re-derived SIDE-CAR, never a node column.
#: Node rows are keep-first write-once, so a capability stored on the row would be a
#: one-way ratchet: the first night's verdict would outlive every substrate improvement
#: that came after it. Here the current view is the max ``computed_at`` per node, so a
#: node whose price coverage improves is re-derived UP on the next build with no
#: migration and no rewrite.
CAPABILITY_COLUMNS: tuple[str, ...] = (
    "node_id", "capability", "capability_basis", "computed_at", "engine_version",
)

#: GMI -> Data OS identity resolution bridge (V4-D2A) — a re-derived SIDE-CAR, never a
#: node column, for exactly the same reason as CAPABILITY_COLUMNS above: node rows are
#: keep-first write-once, and a resolution written once would be a one-way ratchet the
#: master's own coverage growth could never repair. One row per company-kind node, per
#: materialized graph generation. See ``engine/theme_graph/identity_resolution.py`` and
#: ``research/prophet_v4/d2/D2A_FROZEN_CONTRACT_2026-08-18.md``.
IDENTITY_RESOLUTION_COLUMNS: tuple[str, ...] = (
    "schema", "node_id", "graph_kind", "market_scope", "graph_identity_epoch",
    "source_native_symbol", "resolution_asof", "resolution_state",
    "issuer_id", "security_id", "listing_key", "join_method",
    "master_generated_at", "master_symbol_directory_snapshot", "master_code_version",
    "refusal_reason", "source_receipts", "computed_at", "engine_version",
)

#: Keep-first keys. Edges key on (edge_id, belief_time): a NEW belief about the same
#: edge is a new row, a same-day re-run is a no-op.
NODE_KEY: tuple[str, ...] = ("node_id",)
EDGE_KEY: tuple[str, ...] = ("edge_id", "belief_time")
EVIDENCE_KEY: tuple[str, ...] = ("evidence_id",)
CAPABILITY_KEY: tuple[str, ...] = ("node_id", "computed_at")
IDENTITY_RESOLUTION_KEY: tuple[str, ...] = ("node_id", "computed_at")

#: The three exposure axes are measured in W2; W1b writes them as declared nulls so the
#: columns exist (and the contract can pin them) without anyone mistaking a null for a
#: measurement of zero.
RESERVED_EDGE_FIELDS: tuple[str, ...] = (
    "economic_share", "trading_beta", "attention_share",
    "economic_share_formula_id", "trading_beta_formula_id", "attention_share_formula_id",
    "economic_share_display", "trading_beta_display", "attention_share_display",
)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def store_dir() -> Path:
    return config.data_dir() / STORE_DIRNAME


def nodes_path() -> Path:
    return store_dir() / "nodes.parquet"


def edges_path() -> Path:
    return store_dir() / "edges.parquet"


def evidence_path() -> Path:
    return store_dir() / "evidence.parquet"


def capability_path() -> Path:
    return store_dir() / "capability.parquet"


def identity_resolution_path() -> Path:
    return store_dir() / "identity_resolution.parquet"


def probation_path() -> Path:
    """The probation queue — proposals awaiting a curated ratification act.

    A sidecar under the store, deliberately NOT one of the three ledgers: nothing here is
    production vocabulary, and the graph build ignores every row that has not been
    ratified.
    """
    return store_dir() / "probation" / "proposals.jsonl"


def meta_path() -> Path:
    return store_dir() / "_meta.json"


# ---------------------------------------------------------------------------
# Lane gate
# ---------------------------------------------------------------------------

def collect_lane() -> str | None:
    """This process's collection lane, resolved FAIL-CLOSED from the environment.

    Defaultless on purpose: see the module docstring. ``US_LANE`` is accepted as the
    legacy alias, matching ``engine.ledger_lane`` and ``scripts.build_baskets``.
    """
    val = os.environ.get("COLLECT_LANE") or os.environ.get("US_LANE") or ""
    return val.strip().lower() or None


def lane_ok(lane: str | None, what: str, *, allow_backfill: bool = False) -> bool:
    """True when this write may proceed. Everything unnamed is refused."""
    if allow_backfill:
        log.info("theme_graph: %s permitted as an explicit one-shot backfill "
                 "(lane=%r bypassed by argument, never by an env default)", what, lane)
        return True
    if lane == WRITE_LANE:
        return True
    log.info("theme_graph: %s REFUSED (lane=%r) — these ledgers are advanced only by "
             "the %r lane; every other context computes and discards",
             what, lane, WRITE_LANE)
    return False


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------

def _read(path: Path, columns: tuple[str, ...]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=list(columns))
    try:
        return pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001 — an unreadable store is empty, not fatal
        log.warning("theme_graph: %s unreadable (%s)", path.name, exc)
        return pd.DataFrame(columns=list(columns))


def read_nodes() -> pd.DataFrame:
    return _read(nodes_path(), NODE_COLUMNS)


def read_evidence() -> pd.DataFrame:
    return _read(evidence_path(), EVIDENCE_COLUMNS)


def read_edges(*, latest_belief: bool = True) -> pd.DataFrame:
    """Edges. ``latest_belief`` collapses the history to the current view.

    The collapse is max ``belief_time`` per ``edge_id``, breaking ties on the later
    ``computed_at`` and then on ``edge_id`` — deterministic, and never on a magnitude
    (G0.11: nothing in this store may be ordered by a value).
    """
    df = _read(edges_path(), EDGE_COLUMNS)
    if df.empty or not latest_belief:
        return df
    ordered = df.sort_values(["edge_id", "belief_time", "computed_at"], kind="stable")
    latest = ordered.drop_duplicates(subset=["edge_id"], keep="last")
    return latest.sort_values("edge_id", kind="stable").reset_index(drop=True)


def read_capability(*, latest: bool = True) -> pd.DataFrame:
    """Capability rows. ``latest`` collapses to the current view (max ``computed_at``).

    Ties break on ``node_id`` — deterministic, and never on the capability VALUE, which
    would quietly turn a tie into a ratchet in whichever direction sorted higher.
    """
    df = _read(capability_path(), CAPABILITY_COLUMNS)
    if df.empty or not latest:
        return df
    ordered = df.sort_values(["node_id", "computed_at"], kind="stable")
    return (ordered.drop_duplicates(subset=["node_id"], keep="last")
                   .sort_values("node_id", kind="stable").reset_index(drop=True))


def read_identity_resolution(*, latest: bool = True) -> pd.DataFrame:
    """GMI -> Data OS identity resolution rows (V4-D2A). ``latest`` collapses to the
    current view (max ``computed_at`` per node_id).

    Ties break on ``node_id`` — deterministic, never on the resolved id or state, which
    would quietly turn a tie into a ratchet in whichever direction sorted higher (same
    discipline as :func:`read_capability`, G0.11).
    """
    df = _read(identity_resolution_path(), IDENTITY_RESOLUTION_COLUMNS)
    if df.empty or not latest:
        return df
    ordered = df.sort_values(["node_id", "computed_at"], kind="stable")
    return (ordered.drop_duplicates(subset=["node_id"], keep="last")
                   .sort_values("node_id", kind="stable").reset_index(drop=True))


def read_meta() -> dict:
    p = meta_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("theme_graph: _meta.json unreadable (%s)", exc)
        return {}


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

def _atomic_write_parquet(df: pd.DataFrame, path: Path) -> None:
    """Write via a temp file in the same directory, then rename over the target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def append_rows(path: Path, rows: list[dict], columns: tuple[str, ...],
                key: tuple[str, ...]) -> int:
    """Append ``rows`` keep-FIRST on ``key``. Returns rows actually added.

    Unknown columns are dropped and missing ones filled with None, so a caller cannot
    widen the store by accident — the column set is the contract.
    """
    if not rows:
        return 0
    new = pd.DataFrame(rows).reindex(columns=list(columns))
    prior = _read(path, columns)
    before = len(prior)
    if before:
        combined = pd.concat([prior.reindex(columns=list(columns)), new],
                             ignore_index=True)
    else:
        combined = new
    combined = (combined.drop_duplicates(subset=list(key), keep="first")
                        .sort_values(list(key), kind="stable")
                        .reset_index(drop=True))
    _atomic_write_parquet(combined, path)
    return int(len(combined) - before)


def write_nodes(rows: list[dict], *, lane: str | None = None,
                allow_backfill: bool = False) -> int:
    if not lane_ok(lane, "nodes append", allow_backfill=allow_backfill):
        return 0
    return append_rows(nodes_path(), rows, NODE_COLUMNS, NODE_KEY)


def write_edges(rows: list[dict], *, lane: str | None = None,
                allow_backfill: bool = False) -> int:
    if not lane_ok(lane, "edges append", allow_backfill=allow_backfill):
        return 0
    return append_rows(edges_path(), rows, EDGE_COLUMNS, EDGE_KEY)


def write_evidence(rows: list[dict], *, lane: str | None = None,
                   allow_backfill: bool = False) -> int:
    if not lane_ok(lane, "evidence append", allow_backfill=allow_backfill):
        return 0
    return append_rows(evidence_path(), rows, EVIDENCE_COLUMNS, EVIDENCE_KEY)


def write_capability(rows: list[dict], *, lane: str | None = None,
                     allow_backfill: bool = False) -> int:
    """Append tonight's capability derivation. Same lane gate as the ledgers."""
    if not lane_ok(lane, "capability append", allow_backfill=allow_backfill):
        return 0
    return append_rows(capability_path(), rows, CAPABILITY_COLUMNS, CAPABILITY_KEY)


def write_identity_resolution(rows: list[dict], *, lane: str | None = None,
                              allow_backfill: bool = False) -> int:
    """Append tonight's GMI -> Data OS identity resolution derivation. Same lane gate
    as the ledgers and the capability side-car."""
    if not lane_ok(lane, "identity_resolution append", allow_backfill=allow_backfill):
        return 0
    return append_rows(identity_resolution_path(), rows, IDENTITY_RESOLUTION_COLUMNS,
                       IDENTITY_RESOLUTION_KEY)


def write_meta(meta: dict, *, lane: str | None = None,
               allow_backfill: bool = False) -> bool:
    """Write ``_meta.json`` atomically. Same gate as the ledgers it describes."""
    if not lane_ok(lane, "_meta.json write", allow_backfill=allow_backfill):
        return False
    p = meta_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    os.replace(tmp, p)
    return True
