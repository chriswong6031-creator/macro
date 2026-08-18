"""GMI -> Data OS identity resolution bridge (V4-D2A frozen contract).

Contract: ``research/prophet_v4/d2/D2A_FROZEN_CONTRACT_2026-08-18.md``. Sol's D2A
ruling makes the Data OS identity spine (``data/reference/security_master.parquet`` +
``vendor_aliases.parquet``, read through ``lib.dataos.identity``) the estate's ONLY
exact issuer/security/listing identity authority. The GMI theme graph keeps its own
topology node ids (``co:<market>:<SYMBOL>[#epoch]`` — a graph-topology concern, never
recycled, per ``engine/theme_graph/identity.py``). This module is the BRIDGE between
the two: a re-derived side-car, ``data/theme_graph/identity_resolution.parquet``, that
answers "which Data OS security does this GMI company node name" — never a second
allocator, never a rewrite of either spine.

ONE ROW PER COMPANY-KIND NODE (``kind == "company"``), including refusals. `etf`/other
kinds carry no rows in v1. The row is re-derived on EVERY build (the capability-rule
pattern, never a node column — node rows are keep-first write-once, and an identity
resolution written once would be a one-way ratchet the master's own coverage growth
could never repair).

THE ALGORITHM (§4, ordered, first match wins) is deterministic and carries NO ticker
equality fallback: a symbol absent from the master AND every vendor alias space is
structurally incapable of becoming RESOLVED. Alias resolution goes ONLY through
``lib.dataos.identity.VendorAliasTable.from_records(...).resolve(vendor, symbol,
on=resolution_asof)``, queried across EVERY vendor space the committed alias table
carries — this module is the FIRST real consumer of that reader (Scout A finding 1).

``source_native_symbol`` is PARSE PROVENANCE ONLY — the symbol segment as split out of
the node id — and is NEVER a join key. The only sanctioned resolution path is this
module's reader API (``read_identity_resolution`` / ``resolve_graph_node_identity``);
nothing downstream may re-derive or re-match on ``source_native_symbol`` directly.

TWO READ PATHS (§5): ``read_identity_resolution()`` for the bulk latest-generation
view (the ``read_capability`` pattern — max ``computed_at`` per node), and
``resolve_graph_node_identity(node_id, asof=...)`` for one node, either from the
persisted sidecar (``asof=None``) or re-run PURELY over the committed inputs at an
explicit historical date (no store write, no second store). Both raise
``UnknownGraphNodeError`` for a node_id the graph itself does not carry — a known node
never returns an untyped/None resolution.

TWO-CLOCK LAW, CURRENT vs HISTORICAL mode (§4 amendment, post-adversarial-review
2026-08-18 — see D2A_FROZEN_CONTRACT_2026-08-18.md AMENDMENTS): the materialization
path (``derive_rows``, driven by a generation's ``belief_time``) resolves in CURRENT
mode — rule 6 may consult every vendor alias space, including the unconditionally-open
current-catalog rows (``store``/``yahoo_fetch``) that answer "what string do I use
TODAY for a bar of any date" (``AliasRow`` docstring, ``lib/dataos/identity.py``).
``resolve_graph_node_identity(node_id, asof=...)`` with an EXPLICIT ``asof`` instead
resolves in HISTORICAL mode: rule 6 may consult ONLY DATED alias rows (``valid_from``
or ``valid_to`` non-null) as historical-naming evidence — a current-catalog row is
never allowed to answer a historical-naming question, because it was never given one.
Rule 5 (exact inception-code match) is asof-invariant in BOTH modes: the master's
``inception_code`` is the security's own canonical symbol, minted once and stored, so
it never depends on the query date.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from lib import config
from lib.dataos.identity import VendorAliasTable

from . import identity as graph_identity
from . import store

log = logging.getLogger(__name__)

#: Contract id — the ``schema`` column's constant value.
SCHEMA_ID = "gmi.identity_resolution/v1"

#: Closed vocabulary, §4/§3.
RESOLUTION_STATES: tuple[str, ...] = (
    "RESOLVED", "INVALID_SOURCE_ID", "UNSUPPORTED_MARKET",
    "DEFERRED_IDENTITY_EXCEPTION", "ENTITY_TYPE_CONFLICT", "AMBIGUOUS", "NOT_IN_MASTER",
)
JOIN_METHODS: tuple[str, ...] = ("master_inception_exact", "vendor_alias", "refused")

#: Where the Data OS spine lives, relative to the theme graph's own ``data_dir``
#: (``lib.config.data_dir()`` in production; a fixture root in tests) — see
#: ``scripts/build_security_master.py`` for the producer.
REFERENCE_SUBDIR = "reference"
MASTER_FILE = "security_master.parquet"
ALIASES_FILE = "vendor_aliases.parquet"
RECEIPT_FILE = "_receipt.json"


class UnknownGraphNodeError(KeyError):
    """``node_id`` is not a node the theme graph carries at all.

    Deliberately NOT raised for a company node the sidecar has not yet resolved
    (that is a resolution_state, e.g. ``NOT_IN_MASTER``) — only for a node_id the
    graph's own ``nodes.parquet`` has no row for.
    """


# ---------------------------------------------------------------------------
# Master inputs — loaded once per materialization (§4)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MasterInputs:
    """The Data OS spine, read once and indexed for repeated per-node lookups."""

    master_by_code: dict[str, dict] = field(default_factory=dict)
    master_by_security: dict[str, dict] = field(default_factory=dict)
    alias_table: VendorAliasTable = field(default_factory=VendorAliasTable)
    vendors: frozenset[str] = frozenset()
    identity_exceptions: dict[str, dict] = field(default_factory=dict)
    generated_at: str | None = None
    symbol_directory_snapshot: str | None = None
    code_version: str | None = None


def _as_bound(value: object) -> date | None:
    """A stored alias valid_from/valid_to bound as a plain ``date``, or None (open).

    ``data/reference/vendor_aliases.parquet`` stores these as plain ``datetime.date``
    objects or None (verified against the committed artifact); this also tolerates a
    ``pandas.Timestamp``/NaT/NaN, which a re-read through a different pandas path can
    hand back, so the normalisation is defensive rather than assumed.
    """
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text or text.lower() in {"nat", "nan", "none", "<na>"}:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _as_date(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def load_master_inputs(data_dir: Path | None = None) -> MasterInputs | None:
    """Load the committed Data OS spine ONCE. None if ``data/reference/`` is absent
    or unreadable — a sparse checkout or a pre-DOS-1.1 state, never fatal (the theme
    graph is a display-tier plane; §9 of the module docstring)."""
    root = Path(data_dir) if data_dir is not None else config.data_dir()
    ref_dir = root / REFERENCE_SUBDIR
    master_path = ref_dir / MASTER_FILE
    aliases_path = ref_dir / ALIASES_FILE
    receipt_path = ref_dir / RECEIPT_FILE
    if not (master_path.exists() and aliases_path.exists() and receipt_path.exists()):
        return None
    try:
        master = pd.read_parquet(master_path)
        aliases = pd.read_parquet(aliases_path)
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — an unreadable master degrades, never fatal
        log.warning("identity_resolution: security master unreadable (%s)", exc)
        return None

    records = []
    for r in aliases.to_dict("records"):
        records.append({
            "vendor": str(r["vendor"]),
            "vendor_symbol": str(r["vendor_symbol"]),
            "security_id": str(r["security_id"]),
            "valid_from": _as_bound(r.get("valid_from")),
            "valid_to": _as_bound(r.get("valid_to")),
        })
    table = VendorAliasTable.from_records(records)

    master_by_code: dict[str, dict] = {}
    master_by_security: dict[str, dict] = {}
    for r in master.to_dict("records"):
        row = {
            "security_id": str(r["security_id"]),
            "issuer_id": str(r["issuer_id"]),
            "listing_key": str(r["listing_key"]),
        }
        code = str(r.get("inception_code") or "").strip().upper()
        if code:
            master_by_code[code] = row
        master_by_security[row["security_id"]] = row

    exceptions: dict[str, dict] = {}
    for exc_row in receipt.get("identity_exceptions") or []:
        key = str(exc_row.get("key") or "").strip().upper()
        if key:
            exceptions[key] = dict(exc_row)

    return MasterInputs(
        master_by_code=master_by_code,
        master_by_security=master_by_security,
        alias_table=table,
        vendors=frozenset(row.vendor for row in table.rows),
        identity_exceptions=exceptions,
        generated_at=receipt.get("generated_at"),
        symbol_directory_snapshot=receipt.get("symbol_directory_snapshot"),
        code_version=receipt.get("code_version"),
    )


def _master_meta(inputs: MasterInputs | None) -> dict:
    if inputs is None:
        return {"master_generated_at": None, "master_symbol_directory_snapshot": None,
                "master_code_version": None}
    return {
        "master_generated_at": inputs.generated_at,
        "master_symbol_directory_snapshot": inputs.symbol_directory_snapshot,
        "master_code_version": inputs.code_version,
    }


# ---------------------------------------------------------------------------
# ETF entity-type conflicts (§4 rule 4) — same-generation company/etf symbol clash
# ---------------------------------------------------------------------------

def _etf_symbols(nodes: list[dict]) -> frozenset[str]:
    """Every ``etf``-kind node's symbol, from the SAME generation's node list."""
    out: set[str] = set()
    for n in nodes:
        if str(n.get("kind")) != "etf":
            continue
        try:
            ext = json.loads(n.get("external_ids") or "{}")
        except Exception:  # noqa: BLE001 — malformed external_ids is not fatal here
            continue
        sym = ext.get("symbol")
        if sym:
            out.add(str(sym).strip().upper())
    return frozenset(out)


# ---------------------------------------------------------------------------
# Node-id parsing — ONE clean split (§3: no shared parser exists; do not copy the
# hand-rolled ones at check_theme_graph_contracts.py:542-544 / capability.py:144)
# ---------------------------------------------------------------------------

def _best_effort_market(node_id: str) -> str | None:
    parts = str(node_id or "").split(":")
    if len(parts) >= 2 and parts[1] in graph_identity.MARKETS:
        return parts[1]
    return None


def _best_effort_symbol(node_id: str) -> str | None:
    parts = str(node_id or "").split(":", 2)
    if len(parts) >= 3:
        sym = parts[2].split("#", 1)[0].strip().upper()
        return sym or None
    return None


# ---------------------------------------------------------------------------
# F1 (post-adversarial-review) — cross-market equality guard. A rule 5/6 hit is
# refused, never resolved or marked AMBIGUOUS, if the master row's own listing
# country disagrees with the node's market_scope: the master row is definitively
# another market's security, not a coincidental symbol collision.
# ---------------------------------------------------------------------------

_MARKET_SCOPE_TO_COUNTRY: dict[str, str] = {"us": "US", "cn": "CN", "hk": "HK", "ca": "CA"}


def _cross_market_mismatch_reason(market_scope: str, listing_key: str | None) -> str | None:
    """None if the master row's listing country agrees with ``market_scope``; else the
    refusal_reason text disclosing the collision."""
    expected = _MARKET_SCOPE_TO_COUNTRY.get(market_scope)
    if expected is None or not listing_key:
        return None
    country = str(listing_key).split("-", 1)[0]
    if country == expected:
        return None
    return (
        f"master row listing_key={listing_key!r} belongs to country {country!r}, which "
        f"disagrees with the node's market_scope={market_scope!r} (expected {expected!r}) "
        "— refusing a cross-market identity collision rather than resolving into another "
        "market's security (contract F1 amendment)")


# ---------------------------------------------------------------------------
# F2 (post-adversarial-review) — HISTORICAL-mode alias lookup, two-clock law. Only
# DATED alias rows (at least one of valid_from/valid_to non-null) are historical-naming
# evidence; a fully open row (both bounds null) is a CURRENT-CATALOG space answering
# "what string do I use today for a bar of any date" and is structurally excluded.
# ---------------------------------------------------------------------------

def _historical_alias_resolve(table: VendorAliasTable, vendor: str, vendor_symbol: str,
                              on: date) -> str | None:
    for r in table.rows:
        if r.vendor != vendor or r.vendor_symbol != vendor_symbol:
            continue
        if r.valid_from is None and r.valid_to is None:
            continue  # current-catalog row — not historical-naming evidence
        if r.covers(on):
            return r.security_id
    return None


# ---------------------------------------------------------------------------
# The algorithm (§4) — one node in, one row out. Deterministic, no fallback.
# ---------------------------------------------------------------------------

def _resolve_node_row(*, node_id: str, resolution_asof: str, inputs: MasterInputs | None,
                      etf_symbols: frozenset[str], computed_at: str,
                      engine_version: str, historical: bool = False) -> dict:
    base = {
        "schema": SCHEMA_ID, "node_id": node_id, "graph_kind": "company",
        "resolution_asof": resolution_asof, "computed_at": computed_at,
        "engine_version": engine_version,
    }
    meta = _master_meta(inputs)
    null_ids = {"issuer_id": None, "security_id": None, "listing_key": None}

    # rule 1 — the node id itself must satisfy the permanent-identity grammar.
    m = graph_identity.COMPANY_ID_RE.match(str(node_id))
    if not m:
        return {
            **base, **null_ids,
            "market_scope": _best_effort_market(node_id),
            "graph_identity_epoch": None,
            "source_native_symbol": _best_effort_symbol(node_id),
            "resolution_state": "INVALID_SOURCE_ID",
            "join_method": "refused",
            **meta,
            "refusal_reason": (
                f"node_id does not match {graph_identity.COMPANY_ID_RE.pattern!r}"),
            "source_receipts": json.dumps({"node_id": str(node_id)},
                                          ensure_ascii=False, sort_keys=True),
        }

    market_scope = m.group(1)
    tail = str(node_id).split(":", 2)[2]
    symbol_part, _, epoch_s = tail.partition("#")
    symbol = symbol_part.upper()
    epoch = int(epoch_s) if epoch_s else 1

    row = {**base, "market_scope": market_scope, "graph_identity_epoch": epoch,
          "source_native_symbol": symbol, **meta}

    # rule 2 — no country/MIC mapping exists for intl.
    if market_scope == "intl":
        return {**row, **null_ids, "resolution_state": "UNSUPPORTED_MARKET",
                "join_method": "refused",
                "refusal_reason": ("market_scope=intl has no country/MIC mapping in the "
                                   "Data OS spine (contract §4 rule 2)"),
                "source_receipts": json.dumps({"market_scope": market_scope},
                                              sort_keys=True)}

    # rule 3 — the master's own operator-ratified fail-closed identity exceptions.
    exc = (inputs.identity_exceptions if inputs else {}).get(symbol)
    if exc:
        status = exc.get("status", "")
        reason = exc.get("reason", "")
        return {**row, **null_ids, "resolution_state": "DEFERRED_IDENTITY_EXCEPTION",
                "join_method": "refused",
                "refusal_reason": f"{status}: {reason}",
                "source_receipts": json.dumps({"identity_exception": exc},
                                              ensure_ascii=False, sort_keys=True)}

    # rule 4 — an etf-kind node in the SAME generation with the same symbol.
    if symbol in etf_symbols:
        conflict_master = (inputs.master_by_code.get(symbol) if inputs else None)
        receipts: dict = {"conflicting_etf_node": f"etf:{symbol}"}
        if conflict_master is not None:
            receipts["master_row_would_otherwise_resolve_to"] = conflict_master["security_id"]
        return {**row, **null_ids, "resolution_state": "ENTITY_TYPE_CONFLICT",
                "join_method": "refused",
                "refusal_reason": (
                    f"etf:{symbol} coexists as an etf-kind node in the same generation "
                    "— machine-visible, no kind rewrite, no pick"),
                "source_receipts": json.dumps(receipts, ensure_ascii=False, sort_keys=True)}

    if inputs is None:
        return {**row, **null_ids, "resolution_state": "NOT_IN_MASTER",
                "join_method": "refused",
                "refusal_reason": ("data/reference/ security master is not present in "
                                   "this checkout"),
                "source_receipts": json.dumps({"master_present": False}, sort_keys=True)}

    # rule 5 — exact: source_native_symbol == inception_code in the master. Asof-
    # invariant in BOTH modes — the master's inception_code is the security's own
    # canonical symbol, minted once and stored (module docstring, two-clock law).
    exact = inputs.master_by_code.get(symbol)
    if exact is not None:
        mismatch = _cross_market_mismatch_reason(market_scope, exact["listing_key"])
        if mismatch is not None:
            return {**row, **null_ids, "resolution_state": "NOT_IN_MASTER",
                    "join_method": "refused", "refusal_reason": mismatch,
                    "source_receipts": json.dumps(
                        {"master_inception_code": symbol,
                         "would_resolve_to": exact["security_id"],
                         "cross_market_collision": True}, sort_keys=True)}
        return {**row, "resolution_state": "RESOLVED",
                "join_method": "master_inception_exact",
                "issuer_id": exact["issuer_id"], "security_id": exact["security_id"],
                "listing_key": exact["listing_key"], "refusal_reason": None,
                "source_receipts": json.dumps(
                    {"master_inception_code": symbol, "security_id": exact["security_id"]},
                    sort_keys=True)}

    # rule 6 — alias: query EVERY vendor present in the table, collect the SET of
    # distinct security_ids. Never a ticker-equality fallback — a symbol absent from
    # every vendor space here falls straight through to rule 7. HISTORICAL mode (an
    # explicit asof from resolve_graph_node_identity) restricts evidence to DATED alias
    # rows only (F2 amendment, two-clock law) — a current-catalog row can never answer a
    # historical-naming question.
    asof_date = _as_date(resolution_asof)
    matches: dict[str, set[str]] = {}
    for vendor in sorted(inputs.vendors):
        if historical:
            sec = _historical_alias_resolve(inputs.alias_table, vendor, symbol, asof_date)
        else:
            sec = inputs.alias_table.resolve(vendor, symbol, on=asof_date)
        if sec:
            matches.setdefault(sec, set()).add(vendor)

    if len(matches) == 1:
        [(sec_id, vendors_hit)] = matches.items()
        m_row = inputs.master_by_security.get(sec_id)
        mismatch = (_cross_market_mismatch_reason(market_scope, m_row["listing_key"])
                    if m_row else None)
        if mismatch is not None:
            return {**row, **null_ids, "resolution_state": "NOT_IN_MASTER",
                    "join_method": "refused", "refusal_reason": mismatch,
                    "source_receipts": json.dumps(
                        {"matched_vendors": sorted(vendors_hit),
                         "would_resolve_to": sec_id, "cross_market_collision": True},
                        sort_keys=True)}
        return {**row, "resolution_state": "RESOLVED", "join_method": "vendor_alias",
                "issuer_id": m_row["issuer_id"] if m_row else None,
                "security_id": sec_id,
                "listing_key": m_row["listing_key"] if m_row else None,
                "refusal_reason": None,
                "source_receipts": json.dumps(
                    {"matched_vendors": sorted(vendors_hit), "security_id": sec_id},
                    sort_keys=True)}
    if len(matches) > 1:
        return {**row, **null_ids, "resolution_state": "AMBIGUOUS", "join_method": "refused",
                "refusal_reason": (
                    f"{len(matches)} distinct security_ids returned by vendor alias "
                    "resolution — never picked by precedence/cap/name"),
                "source_receipts": json.dumps(
                    {"candidates": {k: sorted(v) for k, v in matches.items()}},
                    sort_keys=True)}

    # rule 7 — nothing matched. First-class honest state, never a guard failure. In
    # HISTORICAL mode, disclose separately when a current-catalog (fully open) row
    # WOULD have matched — that row exists but is not historical-naming evidence (F2
    # amendment); the two-clock law makes that a materially different "no" from a
    # symbol absent everywhere.
    refusal_reason = "no security-master or vendor-alias row resolves this symbol"
    receipts: dict = {"checked_vendors": sorted(inputs.vendors)}
    if historical:
        open_hit = any(
            inputs.alias_table.resolve(vendor, symbol, on=asof_date) is not None
            for vendor in inputs.vendors)
        if open_hit:
            refusal_reason = (
                "no dated alias evidence at asof; current-catalog rows exist but are "
                "not historical-naming evidence")
            receipts["current_catalog_rows_excluded_as_historical_evidence"] = True
    return {**row, **null_ids, "resolution_state": "NOT_IN_MASTER", "join_method": "refused",
            "refusal_reason": refusal_reason,
            "source_receipts": json.dumps(receipts, sort_keys=True)}


# ---------------------------------------------------------------------------
# Derivation — one row per company-kind node, every build (§2, §9.3-style side-car)
# ---------------------------------------------------------------------------

def derive_rows(nodes: list[dict], *, resolution_asof: str, computed_at: str,
                engine_version: str, data_dir: Path | None = None) -> list[dict]:
    """One ``identity_resolution`` row per company-kind node in ``nodes``.

    Re-derived from scratch every call, exactly like ``capability.derive_rows``: the
    master's own coverage can only grow (DOS-1.1/1.2 are still display_only authority),
    so a node ``NOT_IN_MASTER`` tonight may resolve tomorrow, and a write-once row would
    make that improvement invisible.
    """
    inputs = load_master_inputs(data_dir)
    etf_syms = _etf_symbols(nodes)
    rows: list[dict] = []
    for node in nodes:
        if str(node.get("kind")) != "company":
            continue
        rows.append(_resolve_node_row(
            node_id=str(node.get("node_id")), resolution_asof=resolution_asof,
            inputs=inputs, etf_symbols=etf_syms, computed_at=computed_at,
            engine_version=engine_version))
    rows.sort(key=lambda r: r["node_id"])
    return rows


# ---------------------------------------------------------------------------
# Reader API (§5)
# ---------------------------------------------------------------------------

def read_identity_resolution(*, latest: bool = True) -> pd.DataFrame:
    """Bulk read — the ``read_capability`` pattern, current view = max ``computed_at``
    per node_id."""
    return store.read_identity_resolution(latest=latest)


def _utc_now_stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")


def resolve_graph_node_identity(node_id: str, asof: str | date | None = None) -> dict:
    """One node's typed resolution row.

    ``asof=None`` — the node's row from the latest persisted sidecar generation
    (falling back to a live computation only if the graph carries the node but the
    sidecar has never resolved it yet, e.g. a pre-first-run checkout — a known node
    NEVER returns an untyped/None resolution). This is CURRENT mode, exactly like the
    materialization path: every vendor alias space is eligible evidence.

    An explicit ``asof`` re-runs the §4 algorithm as a PURE function over the
    committed Data OS inputs at that date — no store write, no second store — in
    HISTORICAL mode (two-clock law, F2 amendment): rule 6 may consult only DATED
    alias rows as historical-naming evidence; the unconditionally-open current-catalog
    rows (``store``/``yahoo_fetch``) are structurally excluded. Rule 5 is unaffected
    either way — it is asof-invariant.

    Raises :class:`UnknownGraphNodeError` only for a ``node_id`` absent from the graph
    itself (or present under a non-company kind — v1's row scope is company nodes
    only).
    """
    nid = str(node_id)
    nodes_df = store.read_nodes()
    hit = nodes_df[nodes_df["node_id"].astype(str) == nid] if not nodes_df.empty \
        else nodes_df
    if hit.empty:
        raise UnknownGraphNodeError(
            f"{nid!r} is not a node in the theme graph (nodes.parquet)")
    if str(hit.iloc[0].get("kind")) != "company":
        raise UnknownGraphNodeError(
            f"{nid!r} is kind={hit.iloc[0].get('kind')!r} — identity_resolution v1 "
            "covers company-kind nodes only")

    etf_syms = _etf_symbols(nodes_df.to_dict("records"))

    if asof is not None:
        asof_str = asof if isinstance(asof, str) else asof.isoformat()
        inputs = load_master_inputs()
        return _resolve_node_row(node_id=nid, resolution_asof=asof_str, inputs=inputs,
                                 etf_symbols=etf_syms, computed_at=_utc_now_stamp(),
                                 engine_version=store.ENGINE_VERSION, historical=True)

    cached = read_identity_resolution(latest=True)
    if not cached.empty:
        row = cached[cached["node_id"].astype(str) == nid]
        if not row.empty:
            return row.iloc[0].to_dict()

    # No persisted row yet (pre-first-run) but the node genuinely exists in the graph —
    # compute live rather than returning an untyped/None resolution for a known node.
    inputs = load_master_inputs()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return _resolve_node_row(node_id=nid, resolution_asof=today, inputs=inputs,
                             etf_symbols=etf_syms, computed_at=_utc_now_stamp(),
                             engine_version=store.ENGINE_VERSION)
