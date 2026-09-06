"""Source-local theme inputs and the vintage ladder they form (W3A §2, §9.5).

WHAT THIS IS. The Finviz theme tree is a SNAPSHOT source: each observation says which
tickers sit in which subtheme *today*, and says nothing about when any of it started.
A bitemporal store cannot ingest that as-is, so the observations are laid out as a
LADDER of dated vintages and the intervals are read off the ladder:

* a membership present in vintages i..j opens at ``asof(i)``;
* it closes at ``asof(j+1)`` — the first date the source was observed WITHOUT it, never
  an invented mid-window date, and never the date somebody guesses it "really" left;
* a membership that reappears after a gap opens a SECOND interval. It is not the same
  fact resumed, it is a new observation, and the store carries both.

Two properties are load-bearing and easy to get wrong:

``valid_from`` means FIRST OBSERVED. Under a manual refresh cadence the closing date is
INTERVAL-CENSORED — bounded by the gap between refreshes — so a consumer may read it as
"gone by then", never as "left on that day" (§9.6).

Dedupe is ADJACENT-ONLY. Collapsing every content-identical vintage would erase an
A→B→A revert into a single unbroken interval, which is exactly the history the ladder
exists to keep. Two identical snapshots taken back-to-back are one observation; the same
content re-appearing after something else is a new one.

VINTAGE 1 IS A DECLARED SEED. ``finviz_themes/finviz_themes_map.json`` (asof 2026-06-27)
predates the history tape and is named as the seed in code rather than back-dated into
the tape — the tape records promotions, and writing a pre-tape observation into it would
fabricate a promotion that never happened.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

#: The declared seed: the first dated Finviz structure observation this repo holds.
SEED_TREE_FILE = "finviz_themes/finviz_themes_map.json"
#: The owner's PIT tape. Every promotion from W3A on appends a dated row here.
TREE_HISTORY_FILE = "data/themes_heatmap/tree_history.jsonl"
#: The owner's live tree. Read for a CONSISTENCY note only — it carries no date of its
#: own, and an undated observation cannot enter a dated ladder.
LIVE_TREE_FILE = "data/themes_heatmap/themes_tree.json"

FINVIZ_FAMILY = "finviz_themes"
FINVIZ_LOCAL_FAMILY = "finviz"


# ---------------------------------------------------------------------------
# Vintages
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Vintage:
    """One dated observation of the whole source structure."""

    asof: str
    source_ref: str
    themes: tuple = ()

    @property
    def content_hash(self) -> str:
        return tree_hash(self.themes)


@dataclass
class SubthemeMeta:
    """The source's own description of a subtheme, as observed at mint time."""

    key: str
    name: str | None = None
    description: str | None = None
    parent_theme_key: str | None = None
    parent_theme_label: str | None = None
    supergroup_index: int | None = None
    first_seen: str | None = None


@dataclass
class Ladder:
    """The ordered vintages plus everything derivable from them."""

    vintages: list[Vintage] = field(default_factory=list)
    dropped_adjacent_duplicates: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def asofs(self) -> list[str]:
        return [v.asof for v in self.vintages]


def tree_hash(themes: object) -> str:
    """Content hash of a tree, order-insensitive within the JSON structure."""
    payload = json.dumps(themes, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_date(v: object) -> bool:
    try:
        date.fromisoformat(str(v).strip()[:10])
    except (TypeError, ValueError):
        return False
    return True


def _read_json(path: Path) -> object | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — a corrupt input is missing input
        log.warning("theme_graph.local_sources: %s unreadable (%s)", path.name, exc)
        return None


def _themes_of(doc: object) -> tuple:
    """The theme list out of either shape: a bare list, or {..., 'themes': [...]}."""
    if isinstance(doc, list):
        return tuple(doc)
    if isinstance(doc, dict):
        for key in ("themes", "tree"):
            v = doc.get(key)
            if isinstance(v, list):
                return tuple(v)
    return ()


def load_finviz_ladder(*, seed_path: Path, history_path: Path,
                       live_tree_path: Path | None = None) -> Ladder:
    """Build the dated vintage ladder from the declared seed plus the history tape."""
    out = Ladder()
    raw: list[Vintage] = []

    seed_doc = _read_json(seed_path)
    if isinstance(seed_doc, dict) and _is_date(seed_doc.get("asof")):
        themes = _themes_of(seed_doc)
        if themes:
            raw.append(Vintage(asof=str(seed_doc["asof"]).strip()[:10],
                               source_ref=SEED_TREE_FILE, themes=themes))
    elif seed_doc is not None:
        out.notes.append("seed present but carries no usable asof — skipped "
                         "(an undated observation cannot enter a dated ladder)")

    if history_path.exists():
        for lineno, line in enumerate(
                history_path.read_text(encoding="utf-8").splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:  # noqa: BLE001
                out.notes.append(f"tree_history line {lineno} unparseable — skipped")
                continue
            asof = str(row.get("asof", "")).strip()[:10]
            themes = _themes_of(row)
            if not _is_date(asof) or not themes:
                out.notes.append(f"tree_history line {lineno} carries no asof/tree — skipped")
                continue
            raw.append(Vintage(asof=asof,
                               source_ref=f"{TREE_HISTORY_FILE}@{asof}", themes=themes))

    # Strictly by asof; ties keep insertion order (seed first), which is the only
    # order that makes a same-day seed+promotion reproducible.
    raw.sort(key=lambda v: v.asof)

    for v in raw:
        if out.vintages and out.vintages[-1].content_hash == v.content_hash:
            # ADJACENT-identical only. A re-appearance after a different vintage is a
            # new observation and stays.
            out.dropped_adjacent_duplicates.append(v.asof)
            continue
        out.vintages.append(v)

    if live_tree_path is not None:
        live = _themes_of(_read_json(live_tree_path))
        if live and out.vintages and tree_hash(live) != out.vintages[-1].content_hash:
            # Report-only: the live tree is the owner's serving artifact, the tape is the
            # dating authority. A divergence means a promotion did not append — worth
            # saying out loud, never worth inventing a date for.
            out.notes.append(
                "live tree content differs from the newest taped vintage — the ladder "
                "follows the TAPE (dated); an untaped tree cannot be dated")
    return out


# ---------------------------------------------------------------------------
# Reading a vintage
# ---------------------------------------------------------------------------

def load_supergroups(receipts_dir: Path) -> dict[str, int]:
    """{theme name or key: 0-based supergroup index} from the NEWEST refresh receipt.

    The source's unlabelled layer above themes (6 groups, 10/10/8/7/3/2 as of 2026-08)
    is flattened out of the committed tree by the schema and survives only in the
    refresh receipts (``supergroups: [{group, themes: [names]}]``). This is the ONLY
    lawful source for the index: deriving it from theme ordinals mints 40 singleton
    groups and writes them into write-once node metadata (the diff-review finding that
    forced this loader). No receipt, or a receipt without the layer → empty map, and
    the caller stamps ``supergroup_index=None`` — an honest unknown, never a guess.
    """
    try:
        newest = max(receipts_dir.glob("*.json"))
    except ValueError:
        return {}
    try:
        doc = json.loads(newest.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — a torn receipt must not kill the build
        return {}
    out: dict[str, int] = {}
    for idx, row in enumerate(doc.get("supergroups") or []):
        if not isinstance(row, dict):
            continue
        for name in row.get("themes") or []:
            label = str(name).strip()
            if label:
                out[label] = idx
    return out


def subthemes_of(vintage: Vintage,
                 supergroups: dict[str, int] | None = None) -> dict[str, SubthemeMeta]:
    """{subtheme_key: metadata} for one vintage, in source order.

    ``supergroup_index`` is the unlabelled layer above themes that the committed schema
    flattens; it rides metadata and is NOT resurrected as hierarchy (W4 owns that).
    The index comes ONLY from ``load_supergroups`` (refresh receipts) — a theme absent
    from the map carries None, never its enumeration ordinal.
    """
    sg_map = supergroups or {}
    out: dict[str, SubthemeMeta] = {}
    for theme in vintage.themes:
        if not isinstance(theme, dict):
            continue
        parent_key = str(theme.get("key") or theme.get("theme") or "").strip() or None
        parent_label = str(theme.get("theme") or theme.get("key") or "").strip() or None
        sg_idx = None
        for probe in (parent_label, parent_key):
            if probe is not None and probe in sg_map:
                sg_idx = int(sg_map[probe])
                break
        for sub in theme.get("subsectors") or []:
            if not isinstance(sub, dict):
                continue
            key = str(sub.get("key") or "").strip()
            if not key or key in out:
                continue
            out[key] = SubthemeMeta(
                key=key,
                name=(str(sub.get("name")).strip() if sub.get("name") else None),
                description=(str(sub.get("description")).strip()
                             if sub.get("description") else None),
                parent_theme_key=parent_key,
                parent_theme_label=parent_label,
                supergroup_index=sg_idx,
                first_seen=vintage.asof,
            )
    return out


def memberships_of(vintage: Vintage) -> set[tuple[str, str]]:
    """{(subtheme_key, SYMBOL)} for one vintage."""
    out: set[tuple[str, str]] = set()
    for theme in vintage.themes:
        if not isinstance(theme, dict):
            continue
        for sub in theme.get("subsectors") or []:
            if not isinstance(sub, dict):
                continue
            key = str(sub.get("key") or "").strip()
            if not key:
                continue
            for member in sub.get("members") or []:
                sym = str(member or "").strip().upper()
                if sym:
                    out.add((key, sym))
    return out


# ---------------------------------------------------------------------------
# Intervals
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Interval:
    """One membership's observed interval, with the vintages that witnessed it."""

    subtheme_key: str
    symbol: str
    valid_from: str
    valid_to: str | None
    opened_by: str          # source_ref of the vintage that first showed it
    closed_by: str | None   # source_ref of the vintage that first showed it GONE


@dataclass(frozen=True)
class THSInterval:
    """One owner-history THS membership interval, bounded by observed snapshots."""

    basket_id: str
    ticker: str
    valid_from: str
    valid_to: str | None
    source_shape: str
    closed_by: str | None = None


def membership_intervals(ladder: Ladder) -> list[Interval]:
    """Every observed interval across the ladder, oldest first.

    A pair present in a run of consecutive vintages yields ONE interval; a pair that
    disappears and comes back yields two, because that is two observations and the store
    is a record of observations.
    """
    if not ladder.vintages:
        return []
    per_vintage = [memberships_of(v) for v in ladder.vintages]
    all_pairs = sorted(set().union(*per_vintage)) if per_vintage else []
    out: list[Interval] = []
    for key, sym in all_pairs:
        run_start: int | None = None
        for i, present in enumerate(
                [(key, sym) in members for members in per_vintage] + [False]):
            if present and run_start is None:
                run_start = i
            elif not present and run_start is not None:
                closed = i < len(ladder.vintages)
                out.append(Interval(
                    subtheme_key=key, symbol=sym,
                    valid_from=ladder.vintages[run_start].asof,
                    valid_to=ladder.vintages[i].asof if closed else None,
                    opened_by=ladder.vintages[run_start].source_ref,
                    closed_by=ladder.vintages[i].source_ref if closed else None))
                run_start = None
    out.sort(key=lambda iv: (iv.valid_from, iv.subtheme_key, iv.symbol))
    return out


def ths_membership_intervals(history) -> list[THSInterval]:
    """Turn the canonical THS owner history into observed membership intervals.

    ``history`` is intentionally duck-typed: the graph remains a pure consumer of
    the owner parquet and never inherits its writer or append semantics.  A member
    opens only at the first snapshot that contains it; the first later snapshot
    where it is absent closes the interval; a reappearance opens a new interval.
    """
    rows = history.to_dict("records") if hasattr(history, "to_dict") else list(history)
    snapshots: dict[str, dict[tuple[str, str], str]] = {}
    for row in rows:
        date = str(row.get("snapshot_date") or "").strip()
        basket = str(row.get("basket_id") or "").strip()
        ticker = str(row.get("ticker") or "").strip()
        if not date or not basket or not ticker:
            continue
        snapshots.setdefault(date, {}).setdefault(
            (basket, ticker), str(row.get("source_shape") or "unknown"))
    pairs = sorted({pair for entries in snapshots.values() for pair in entries})
    # The presence axis MUST be the dates on which THAT basket was actually
    # collected, never the global set of snapshot dates. A multi-basket THS
    # store is collected per-basket and staggered: a date on which basket A
    # was observed but basket B was not must read as a GAP for B, never as
    # an absence that closes/reopens B's interval (see local_sources tests
    # for a staggered-collection regression).
    basket_dates: dict[str, list[str]] = {}
    for date, entries in snapshots.items():
        for basket, _ticker in entries:
            basket_dates.setdefault(basket, set()).add(date)  # type: ignore[union-attr]
    basket_dates = {basket: sorted(dates) for basket, dates in basket_dates.items()}
    out: list[THSInterval] = []
    for basket, ticker in pairs:
        dates = basket_dates.get(basket, [])
        opened: int | None = None
        shape = "unknown"
        for index, present in enumerate(
                [(basket, ticker) in snapshots[date] for date in dates] + [False]):
            if present and opened is None:
                opened = index
                shape = snapshots[dates[index]][(basket, ticker)]
            elif not present and opened is not None:
                out.append(THSInterval(
                    basket_id=basket, ticker=ticker, valid_from=dates[opened],
                    valid_to=dates[index] if index < len(dates) else None,
                    source_shape=shape,
                    closed_by=dates[index] if index < len(dates) else None))
                opened = None
    return sorted(out, key=lambda iv: (iv.valid_from, iv.basket_id, iv.ticker))


def subtheme_registry(ladder: Ladder,
                      supergroups: dict[str, int] | None = None) -> dict[str, SubthemeMeta]:
    """{key: metadata} across the whole ladder, keep-FIRST.

    Keep-first matches the node store: labels are MINT-TIME snapshots. The graph is a
    join spine, not the display-label authority — a renamed subtheme keeps its node, its
    id and its minted label, and the current label resolves from the live tree.
    ``supergroups`` comes from :func:`load_supergroups`; absent → indexes stamp None.
    """
    out: dict[str, SubthemeMeta] = {}
    for v in ladder.vintages:
        for key, meta in subthemes_of(v, supergroups).items():
            out.setdefault(key, meta)
    return out


# ---------------------------------------------------------------------------
# 同花顺 concepts
# ---------------------------------------------------------------------------

def load_ths_concepts(concept_map_path: Path) -> tuple[str | None, dict[str, str]]:
    """``(asof, {zh_name: code})`` from the vendor concept map."""
    doc = _read_json(concept_map_path)
    if not isinstance(doc, dict):
        return None, {}
    asof = str(doc.get("asof", "")).strip()[:10]
    mapping = {str(k): str(v).strip() for k, v in (doc.get("map") or {}).items()
               if str(v).strip()}
    return (asof if _is_date(asof) else None), mapping
