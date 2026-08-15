"""Source-family rights for the theme graph (W3A §4, review amendment §9.4).

THE SINGLE AUTHORITY IS THE REGISTRY. ``config/theme_sources.yml`` says what may be
emitted from each source family, and nothing else does. The per-row licensing booleans
on an evidence row are MINT-TIME SNAPSHOTS with zero enforcement power: the evidence
store is append-only, so a row minted while a family was ``derived_display_ok`` keeps
saying so forever, and a rights decision that moved after the fact can never reach it.
Enforcement therefore reads the registry at call time — :func:`rights_class` — and the
guard only emits a designed ::notice when a stored snapshot disagrees with the
family's current class,
because history is a record, not a mistake to be edited.

Two directions matter and they are not symmetric:

* an UNKNOWN family fails CLOSED — :func:`rights_class` raises, and the guard treats a
  stored node whose ``rights_family`` has no registry row as a breach. A family nobody
  wrote down is a family nobody reviewed.
* an unresolved-but-registered family is simply refused at the emission gate. That is
  the steady state for both vendor families in W3A, and it is a decision pending, not
  an error.

LABEL vs STRUCTURE (F19). A vendor's own subtheme NAME is already-public vocabulary and
rides ``name_en``/``name_zh`` lawfully; what rights govern is the subtheme→member
STRUCTURE as a dataset. Reading a class as "the words are forbidden" over-reads it; the
gate is about emitting the mapping, not about naming the concept.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

REGISTRY_FILE = "config/theme_sources.yml"

#: The four classes a family may carry. Emission is permitted for exactly two of them.
RIGHTS_CLASSES: frozenset[str] = frozenset(
    {"internal_only", "derived_display_ok", "direct_display_ok", "unresolved"})

#: Classes that permit a GMI public emission. ``unresolved`` is NOT one of them:
#: "we have not decided" refuses, it does not default open.
EMISSION_OK: frozenset[str] = frozenset({"derived_display_ok", "direct_display_ok"})

#: Node-id prefix → source family. The local-theme plane's id grammar carries the
#: family in the id itself, so this table is a restatement of the grammar rather than a
#: second opinion about it.
NODE_PREFIX_FAMILY: tuple[tuple[str, str], ...] = (
    ("ltheme:finviz:", "finviz_themes"),
    ("ltheme:ths:", "ths_concepts"),
    ("basket:baskets_china_ths:", "ths_concepts"),
    ("basket:baskets:", "mastermind_curated"),
    ("basket:baskets_china:", "mastermind_curated"),
    ("basket:baskets_hk:", "mastermind_curated"),
    ("basket:baskets_canada:", "mastermind_curated"),
    ("basket:baskets_intl:", "mastermind_curated"),
)

#: Evidence ``source_ref`` prefix → source family, for the guard's snapshot-vs-current
#: comparison. Deliberately a prefix table and not a parse of the registry's
#: ``source_route`` prose: a warning derived from prose would drift silently the first
#: time somebody rewords a note.
SOURCE_PREFIX_FAMILY: tuple[tuple[str, str], ...] = (
    ("finviz_themes/", "finviz_themes"),
    ("data/themes_heatmap/", "finviz_themes"),
    ("data/baskets_china_ths/", "ths_concepts"),
    ("data/baskets/", "mastermind_curated"),
    ("data/baskets_china/", "mastermind_curated"),
    ("data/baskets_hk/", "mastermind_curated"),
    ("data/baskets_canada/", "mastermind_curated"),
    ("data/baskets_intl/", "mastermind_curated"),
    ("config/theme_crosswalk.yml", "mastermind_curated"),
)


class RightsRefusal(RuntimeError):
    """A public emission was attempted from a family that does not permit one."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def registry_path() -> Path:
    return _repo_root() / REGISTRY_FILE


@lru_cache(maxsize=8)
def _load(path: str) -> dict[str, dict]:
    p = Path(path)
    if not p.exists():
        # Fail-closed by emptiness: with no registry, every family is unknown and
        # rights_class raises. A missing registry must never read as "all clear".
        log.warning("theme_graph.rights: %s missing — every family is unknown and every "
                    "emission gate will refuse", p)
        return {}
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    out: dict[str, dict] = {}
    for name, row in (doc.get("families") or {}).items():
        if isinstance(row, dict):
            out[str(name)] = row
    return out


def load_registry(path: str | Path | None = None) -> dict[str, dict]:
    """The rights registry as {family: row}. Cached per path."""
    return _load(str(Path(path) if path is not None else registry_path()))


def known_families(path: str | Path | None = None) -> frozenset[str]:
    return frozenset(load_registry(path))


def rights_class(family: str, *, path: str | Path | None = None) -> str:
    """The family's CURRENT rights class. Unknown family or unknown class → refuse.

    Fail-closed on both axes: a family with no row is not "probably fine", and a row
    carrying a class outside the enum is a typo that must not silently read as a
    permission.
    """
    row = load_registry(path).get(str(family or "").strip())
    if row is None:
        raise RightsRefusal(
            f"source family {family!r} has no row in {REGISTRY_FILE} — rights are STATED, "
            f"never assumed; add a reviewed row before emitting anything from it")
    cls = str(row.get("rights_class", "")).strip()
    if cls not in RIGHTS_CLASSES:
        raise RightsRefusal(
            f"source family {family!r} carries rights_class {cls!r}, outside "
            f"{sorted(RIGHTS_CLASSES)} — an unreadable class refuses rather than defaults")
    return cls


def auth_class(family: str, *, path: str | Path | None = None) -> str | None:
    row = load_registry(path).get(str(family or "").strip()) or {}
    v = str(row.get("auth_class", "")).strip()
    return v or None


def emission_allowed(family: str, *, path: str | Path | None = None) -> bool:
    """True when this family's material may be emitted publicly. Never raises for a
    known family — use it where a caller wants to branch rather than fail."""
    try:
        return rights_class(family, path=path) in EMISSION_OK
    except RightsRefusal:
        return False


def assert_public_emission_allowed(family: str, *,
                                   path: str | Path | None = None) -> None:
    """Raise :class:`RightsRefusal` unless ``family`` permits a public emission.

    The gate every GMI surface calls before putting source-derived structure in front of
    a user. ``unresolved`` and ``internal_only`` both refuse; the difference between them
    is what a program report says next, not what the caller may do.
    """
    cls = rights_class(family, path=path)
    if cls not in EMISSION_OK:
        raise RightsRefusal(
            f"public emission refused for source family {family!r}: rights_class={cls!r} "
            f"(permitted: {sorted(EMISSION_OK)}). Internal computation is unaffected — "
            f"this gate governs what leaves the house, and 'unresolved' means the "
            f"question is open, not that the answer is yes")


def licensing_for_family(family: str, *,
                         path: str | Path | None = None) -> tuple[bool, bool, bool]:
    """``(internal_ok, display_ok, redistribution_ok)`` DERIVED from the registry.

    The mint-time snapshot an evidence row carries is computed here, so a new receipt can
    never claim a permission the registry does not currently grant (§9.4). An unknown
    family mints the most restrictive readable tuple — internal-only — rather than
    refusing the whole build: the row still has to exist for the edge to cite it, and the
    guard's fail-closed family check is what escalates the unknown family itself.

    Redistribution follows ``auth_class: house``: only content this house authored may be
    republished as a dataset, whatever the display class says.
    """
    try:
        cls = rights_class(family, path=path)
    except RightsRefusal:
        return (True, False, False)
    display = cls in EMISSION_OK
    redistribution = display and auth_class(family, path=path) == "house"
    return (True, display, redistribution)


def family_for_node_id(node_id: object) -> str | None:
    """The source family a node id belongs to, or None when it names no family."""
    nid = str(node_id or "")
    for prefix, family in NODE_PREFIX_FAMILY:
        if nid.startswith(prefix):
            return family
    return None


def family_for_source_ref(source_ref: object) -> str | None:
    """The source family an evidence ``source_ref`` came from, or None when unmapped.

    None means "no opinion" — the guard warns on a DISAGREEMENT, and inventing a family
    for an unmapped ref would manufacture disagreements out of ignorance.
    """
    ref = str(source_ref or "").strip()
    for prefix, family in SOURCE_PREFIX_FAMILY:
        if ref.startswith(prefix):
            return family
    return None
