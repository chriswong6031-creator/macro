"""Capability classification for local-theme nodes — rule ``capability.v1`` (W3A §4, §9.3).

WHAT THE RULE ASKS, AND WHAT IT DOES NOT. ``capability`` answers one definitional
question: *could this concept be measured as a cross-sectional aggregate at all?* Three
priced members is the minimum for an aggregate to BE an aggregate — it is arithmetic,
not an eligibility judgment, and it is deliberately not a quality bar. W3B's
preregistered gates re-test every candidate against real evidence and may demote any of
them freely; nothing here promotes anything.

  ``measurement_candidate``  >= 3 live members resolve to a price artifact.
  ``semantic_only``          everything else — including every unseeded concept, which
                             has no membership substrate at all.
  ``measurable``             UNREACHABLE in W3A. It is minted by W3B, after measurement.

WHY IT IS A SIDE-CAR AND NOT A NODE COLUMN (§9.3). Node rows are keep-first write-once,
so a capability written onto the row would be a one-way ratchet: the first night's
verdict would outlive every substrate improvement after it, and a concept whose members
became priced next month would stay ``semantic_only`` forever with no way to notice.
Rows are re-derived on every build into ``data/theme_graph/capability.parquet`` and the
current view is the max ``computed_at`` per node — so the classification can move in
BOTH directions, which is the property that makes it a measurement rather than a label.

``capability_basis`` names the substrate that satisfied the rule and the counts behind
it, so a reader never has to re-derive why a node was classified the way it was.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

RULE_ID = "capability.v1"

#: The definitional minimum for a cross-sectional aggregate.
MIN_LIVE_MEMBERS = 3

CAPABILITIES: tuple[str, ...] = ("semantic_only", "measurement_candidate", "measurable")

#: US per-ticker price stores, in the order the rule reports them. The union is what
#: counts — a member priced in any of them resolves (§9.10).
US_SUBSTRATE_DIRS: tuple[str, ...] = (
    "baskets/ohlcv",       # the basket lane's own OHLCV cache
    "stocks",              # the engine's core per-name store
    "massive_stock_day",   # whole-market daily store, present only on hosts that hold it
)

#: The CN panel. VERIFIED, not assumed: ``engine/cn_global_beta`` is a pure compute
#: module — it takes a closes frame from its caller and reads no store itself. Its
#: caller is ``scripts/c1_cn_global_beta.py::_panel()``, which reads the wide panel
#: below (dates × tickers, columns are ``600519.SS``-style symbols). Recorded here
#: because the plan asked for the path to be verified rather than repeated (§9.10).
CN_SUBSTRATE_PANEL: str = "china_search/closes.parquet"
CN_SUBSTRATE_OWNER: str = "scripts/c1_cn_global_beta.py::_panel() (feeds engine/cn_global_beta)"


# ---------------------------------------------------------------------------
# Substrate
# ---------------------------------------------------------------------------

@dataclass
class Substrate:
    """Which symbols have a price artifact, resolved once per build.

    Cheap on purpose: the US side lists directory entries (no parquet is opened) and the
    CN side reads the panel's SCHEMA, not its rows — a 13 MB frame is not worth loading
    to ask which columns exist.
    """

    data_dir: Path
    _us: dict[str, frozenset[str]] = field(default_factory=dict, repr=False)
    _cn: frozenset[str] | None = field(default=None, repr=False)
    present_us_dirs: tuple[str, ...] = ()
    cn_panel_present: bool = False

    def __post_init__(self) -> None:
        present: list[str] = []
        for rel in US_SUBSTRATE_DIRS:
            d = self.data_dir / rel
            if not d.is_dir():
                continue
            symbols = frozenset(p.stem.upper() for p in d.glob("*.parquet"))
            if not symbols:
                # Present but empty: gitignored whole-market stores land here on hosts
                # that do not carry them. An empty store contributes nothing and is not
                # reported as a substrate — saying otherwise would credit coverage the
                # host does not have.
                continue
            self._us[rel] = symbols
            present.append(rel)
        self.present_us_dirs = tuple(present)

        panel = self.data_dir / CN_SUBSTRATE_PANEL
        if panel.exists():
            self._cn = frozenset(_panel_columns(panel))
            self.cn_panel_present = bool(self._cn)

    def resolve_us(self, symbol: str) -> str | None:
        """The substrate that prices ``symbol``, or None. Dot/dash variants both tried —
        the vendor writes ``BRK-B`` where a store may hold ``BRK.B``."""
        candidates = {symbol.upper(), symbol.upper().replace(".", "-"),
                      symbol.upper().replace("-", ".")}
        for rel in self.present_us_dirs:
            known = self._us.get(rel, frozenset())
            if candidates & known:
                return rel
        return None

    def resolve_cn(self, symbol: str) -> str | None:
        if not self._cn:
            return None
        return CN_SUBSTRATE_PANEL if symbol.upper() in self._cn else None

    def resolve(self, symbol: str, market: str) -> str | None:
        return self.resolve_cn(symbol) if market == "cn" else self.resolve_us(symbol)

    def describe(self) -> str:
        us = " ∪ ".join(f"data/{d}/" for d in self.present_us_dirs) or "none present"
        cn = f"data/{CN_SUBSTRATE_PANEL}" if self.cn_panel_present else "none present"
        return f"US: {us}; CN: {cn}"


def _panel_columns(path: Path) -> list[str]:
    try:
        import pyarrow.parquet as pq  # noqa: PLC0415

        return [str(c).upper() for c in pq.ParquetFile(path).schema.names]
    except Exception as exc:  # noqa: BLE001 — a missing substrate is not a build failure
        log.warning("theme_graph.capability: %s schema unreadable (%s)", path.name, exc)
        return []


def load_substrate(data_dir: Path) -> Substrate:
    return Substrate(data_dir=Path(data_dir))


# ---------------------------------------------------------------------------
# Membership resolution
# ---------------------------------------------------------------------------

def symbol_of_company_id(node_id: str) -> str | None:
    """``co:us:BRK-B#2`` → ``BRK-B``. Anything else → None."""
    parts = str(node_id or "").split(":")
    if len(parts) < 3 or parts[0] != "co":
        return None
    return parts[2].split("#")[0].upper() or None


def _live(edge: dict) -> bool:
    v = edge.get("valid_to")
    return v is None or (isinstance(v, float) and v != v) or str(v).strip() == ""


def live_members(node_id: str, edges: list[dict]) -> tuple[set[str], str]:
    """``({company_node_id}, how)`` for a local-theme node.

    Two membership paths exist and they are NOT interchangeable — the basis says which
    one answered, because "4 members" via a basket join and "4 members" from the source's
    own claim are different facts.
    """
    direct = {str(e["src"]) for e in edges
              if e.get("type") == "MEMBER_OF" and str(e.get("dst")) == node_id
              and str(e.get("src", "")).startswith("co:") and _live(e)}
    if direct:
        return direct, "direct company memberships"

    baskets = {str(e["src"]) for e in edges
               if e.get("type") == "EXPRESSES" and str(e.get("dst")) == node_id
               and str(e.get("src", "")).startswith("basket:") and _live(e)}
    if not baskets:
        return set(), "no membership path"
    members = {str(e["src"]) for e in edges
               if e.get("type") == "MEMBER_OF" and str(e.get("dst")) in baskets
               and str(e.get("src", "")).startswith("co:") and _live(e)}
    return members, f"basket join via {len(baskets)} basket(s)"


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------

def classify(node_id: str, market: str, member_ids: set[str], how: str,
             substrate: Substrate) -> tuple[str, str]:
    """``(capability, capability_basis)`` for one node under ``capability.v1``."""
    if not member_ids:
        return ("semantic_only",
                f"{RULE_ID}: 0 live members ({how}) — no membership substrate, so no "
                f"aggregate is definable; not an eligibility judgment")

    hits: dict[str, int] = {}
    for cid in member_ids:
        sym = symbol_of_company_id(cid)
        if not sym:
            continue
        where = substrate.resolve(sym, market)
        if where:
            hits[where] = hits.get(where, 0) + 1
    priced = sum(hits.values())
    where_txt = " ∪ ".join(f"data/{k}{'' if k.endswith('.parquet') else '/'} ({v})"
                           for k, v in sorted(hits.items())) or "no substrate"
    if priced >= MIN_LIVE_MEMBERS:
        return ("measurement_candidate",
                f"{RULE_ID}: {priced}/{len(member_ids)} live members priced in "
                f"{where_txt} via {how} (>= {MIN_LIVE_MEMBERS} required)")
    return ("semantic_only",
            f"{RULE_ID}: {priced}/{len(member_ids)} live members priced in {where_txt} "
            f"via {how} (< {MIN_LIVE_MEMBERS} required)")


def derive_rows(nodes: list[dict], edges: list[dict], *, substrate: Substrate,
                computed_at: str, engine_version: str,
                kinds: tuple[str, ...] = ("local_theme",)) -> list[dict]:
    """One capability row per node of ``kinds``, re-derived from scratch.

    Re-derived, never carried forward: this function reads the CURRENT edges and the
    CURRENT substrate and has no idea what last night decided. That is the anti-ratchet.
    """
    rows: list[dict] = []
    for node in nodes:
        if str(node.get("kind")) not in kinds:
            continue
        node_id = str(node.get("node_id"))
        market = str(node.get("market_scope") or "")
        members, how = live_members(node_id, edges)
        capability, basis = classify(node_id, market, members, how, substrate)
        rows.append({"node_id": node_id, "capability": capability,
                     "capability_basis": basis, "computed_at": computed_at,
                     "engine_version": engine_version})
    rows.sort(key=lambda r: r["node_id"])
    return rows
