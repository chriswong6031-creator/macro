"""engine.group_linked_outsiders — filing-linked outsiders per US thematic basket (GR3).

WHAT THIS IS.  For every curated US basket (`data/baskets/membership.json`) this
module publishes the companies OUTSIDE the basket that a member has disclosed a
material agreement with in an 8-K, together with a plain description of how each
one is trading today relative to the basket.  It is the honest form of the
"outside confirmation" read: we publish the agreement type the filing actually
discloses and nothing more.  We never emit a Customer / Supplier / Partner /
Competitor role label, because an 8-K Item 1.01 does not ground one — knowing
that two companies signed a supply agreement does not tell you which side
supplies.  `RELATIONSHIPS` is a closed vocabulary and none of those four words
appears in it.

AUTHORITY.  Display/context tier (`authority: "context_only"`).  A `state` is a
description of TODAY'S TAPE, not a forecast, not an entry, not a rank, and not a
size or gate input.  No composite number is minted anywhere in this artifact.

--------------------------------------------------------------------------------
SOURCE (v1 is fetch-free — committed data only)
--------------------------------------------------------------------------------

`data/edgar/material_8k_events.parquet` (written by `collectors/edgar_8k.py`),
columns: ticker, cik, form, filing_date, items, accession, _first_seen,
amount_usd, counterparty, extraction_ok.  The `counterparty` column is a
best-effort registrant name extracted from the primary filing document by
`collectors.edgar_8k._parse_counterparty`.  This module is its first consumer and
adds no network fetching of its own.

MEASURED COVERAGE, 2026-08-08 (committed tree).  0 of 50,667 rows carry a
non-null `counterparty`, so this module admits ZERO edges today and every basket
publishes `outsiders: []` with a coverage warning.  The pipeline is not idle: the
enrichment lane in `scripts/build_theme_addons.py` has read 207 filings, and all
207 recorded `extraction_ok=False`.  The cause is upstream and structural —
`edgar_8k.enrich_contract_amounts` computes
`counterparty = _parse_counterparty(text) if ok else None`, so a counterparty is
only ever extracted from a filing whose primary document ALSO yielded a parseable
dollar amount ≥ $10k.  Material-agreement 8-Ks routinely put the dollar figure in
an EX-10 exhibit that the primary-document fetch never reads, so the dollar leg
gates the name leg to zero.  That is a collector defect, not a defect here; this
module reads whatever the column holds and reports the yield honestly rather than
inventing a looser reader.  The moment the column populates, this artifact fills
in with no change to the rules below.

--------------------------------------------------------------------------------
RULES (deterministic; every one of them disclosed on the artifact)
--------------------------------------------------------------------------------

EDGE ADMISSION.  An 8-K row is a CANDIDATE edge when all three hold:
  1. `items` names Item 1.01 or Item 2.03 (material definitive agreement /
     direct financial obligation),
  2. `filing_date` is within the trailing `EDGE_WINDOW_MONTHS` (24) months of
     `as_of`,
  3. `counterparty` is non-empty AND the filer ticker is an active member of at
     least one basket.
Both directions count: an outsider's own 8-K naming a member creates the same
edge whenever that filer itself resolves to a member, because the parquet spans
the whole collected filer universe.  Rows failing (3) are not candidates and are
counted in the coverage stats rather than written to the ledger.

RESOLVER (strict by design; no scorer exists here to loosen).  The extracted name
and every SEC registrant name are normalised through
`engine.government_revenue.issuer_graph_expansion.normalize_legal_name` and
`strip_legal_suffix`, and admitted only through that module's `name_match_tier`
— imported, never forked.  Registrant names come from the committed SEC
company_tickers snapshot at `data/symbol_directory/cik_map/<YYYY-MM-DD>.parquet`
(columns ticker, cik, title); the newest snapshot by filename date is used and
its path is reported by `resolution_report()`.  Candidates are bucketed by
suffix-stripped core, then filtered by `name_match_tier(...) is not None`, so
admission is exactly the govrev tiering: verbatim, or a one-sided legal-suffix
difference.  There is no substring match, no edit distance, and no abbreviation
guessing.  Outcomes:
  * exactly one distinct registrant ticker survives → ADMITTED
  * more than one survives                          → `ambiguous_tie`
  * none survives                                   → `no_registrant_match`
  * the survivor is the filer itself                → `self_reference`
KNOWN COST OF STRICTNESS: a dual-class registrant whose two tickers share one
title (GOOGL/GOOG → "Alphabet Inc.") rejects as `ambiguous_tie`.  Picking a share
class would be a heuristic, and this resolver has none.  Every rejection is
written to the edge ledger with its reason — a candidate is never silently
dropped.

RELATIONSHIP SUBTYPE.  Deterministic keyword rules over the row's agreement text,
which is the concatenation of whichever of `_TEXT_FIELDS` the parquet carries
(`agreement_title`, `title`, `description`, `snippet`, `item_text`,
`counterparty`).  The committed parquet today carries only the last of those, so
most rows fall through to the item-code rule; the keyword table lights up without
a code change if the collector later stores filing text.  Rules are evaluated in
this fixed order, first match wins:

    | order | trigger keywords                                          | relationship        |
    |-------|-----------------------------------------------------------|---------------------|
    | 1     | merger, acquisition, acquire, business combination,       | merger_related      |
    |       | share purchase agreement, tender offer, plan of merger    |                     |
    | 2     | credit agreement, loan, note(s), indenture, debenture,    | financing           |
    |       | facility, financing, revolver, term loan                  |                     |
    | 3     | license, licence, licensing, sublicense                   | license             |
    | 4     | collaboration, joint development, co-development,         | collaboration       |
    |       | joint venture, partnership, strategic alliance            |                     |
    | 5     | supply, supplier agreement, offtake, off-take,            | supply_agreement    |
    |       | manufacturing agreement                                   |                     |
    | 6     | purchase, procurement, order agreement                    | purchase_agreement  |
    | 7     | (no keyword) item 2.03 present and item 1.01 absent       | financing           |
    | 8     | otherwise                                                 | disclosed_agreement |

Order is load-bearing: a merger agreement mentions "purchase", a supply agreement
mentions "purchase", so the more specific construction is tested first.

OUTSIDER SET, per basket.  Resolved counterparties linked by ≥1 admitted edge to
≥1 ACTIVE member of that basket, minus that basket's own members.  Ordered by
(edge_n desc, last_filed_at desc, ticker asc) and capped at
`MAX_OUTSIDERS_PER_BASKET` (12).  When the cap binds, the pre-cap count is
disclosed in `coverage_warnings` — there is no silent truncation.

STATE (a description of today's tape).  `active` mirrors the GR0 group_pulse
member-activity rule (masterplan §4.2): |SPY-adjusted return| z ≥ `ACTIVITY_Z`
(1.5) against the ticker's own trailing `ACTIVITY_LOOKBACK_D` (63) sessions, OR
volume ≥ `ACTIVITY_VOLUME_RATIO` (1.5) × its own 63-session median volume; a
ticker with no volume column is judged on the return leg alone.  `engine.group_pulse`
is imported and its constants used when it is present in the tree; when it is not
(GR0 lands in a sibling PR) the constants above are used and
`tests/test_group_linked_outsiders.py` pins them to the masterplan literals so
the two can never drift apart silently.

Basket direction comes from `site/basketdata/pulse.json` (`direction.sign`),
written earlier in the same nightly run.  Given a basket sign:
  * `confirming`       — active AND sign(move_spy_adj) == basket sign AND the
                         basket sign is not "mixed"
  * `active_divergent` — active, but not confirming (this includes every active
                         outsider of a basket whose own sign is "mixed", because
                         a mixed basket has no direction to confirm)
  * `quiet`            — tape readable, not active
  * `unavailable`      — no usable trailing tape for that ticker, OR the basket
                         direction itself is unavailable
A tape whose newest joint bar with SPY is more than `MAX_TAPE_STALENESS_D` (7)
calendar days behind `as_of` is treated as absent, not as quiet: a delisted or
halted name must never publish an old session's move as though it were today's.
An outsider with no tape STAYS LISTED: the disclosed relationship is a fact
independent of whether the ticker prints today.  When `pulse.json` is missing or
carries no entry for a basket, every state degrades to `unavailable` and a
coverage warning says so; the tape figures that ARE readable are still printed,
because they are facts, and the warning names why no confirm/diverge call was
made.  A missing input never raises and never fabricates.

LEDGER.  `data/group_pulse/linked_outsider_edges.parquet`, append-only, advanced
only in the nightly lane (`engine.ledger_lane.nightly_advance_enabled`).  One row
per candidate edge, admitted or rejected.  Rows are facts and immutable once
written: a later run appends only accession-keyed rows it has never seen, and
never rewrites or reorders an existing row.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from importlib import import_module
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from engine import ledger_lane
from engine.government_revenue.issuer_graph_expansion import (
    name_match_tier,
    normalize_legal_name,
    strip_legal_suffix,
)

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Frozen contract constants
# --------------------------------------------------------------------------

SCHEMA = "group_linked_outsiders.v1"
AUTHORITY = "context_only"

#: Trailing window an 8-K must fall inside to yield an edge.
EDGE_WINDOW_MONTHS = 24

#: Published outsiders per basket.  The cap is disclosed whenever it binds.
MAX_OUTSIDERS_PER_BASKET = 12

#: 8-K items that disclose a material agreement / direct financial obligation.
MATERIAL_ITEMS: tuple[str, ...] = ("1.01", "2.03")

# Activity rule — mirrors group_pulse / masterplan §4.2.  Pinned by test.
ACTIVITY_Z = 1.5
ACTIVITY_VOLUME_RATIO = 1.5
ACTIVITY_LOOKBACK_D = 63

#: A state claims to describe TODAY'S tape.  A ticker whose newest joint bar is
#: older than this many calendar days (weekend + a holiday gap) is stale, not
#: quiet: it reads `unavailable` rather than publishing an old session's move as
#: though it were today's.  Delisted and halted names take this path.
MAX_TAPE_STALENESS_D = 7

#: Every reason a candidate edge was not admitted.  Recorded, never dropped.
REJECTION_REASONS = frozenset({
    "no_registrant_match",
    "ambiguous_tie",
    "self_reference",
})

#: Closed relationship vocabulary.  No role labels — see the module docstring.
RELATIONSHIPS: tuple[str, ...] = (
    "supply_agreement",
    "purchase_agreement",
    "collaboration",
    "license",
    "financing",
    "merger_related",
    "disclosed_agreement",
)

#: Role labels this module must never emit, at any tier, for any reason.
FORBIDDEN_ROLE_LABELS: tuple[str, ...] = ("customer", "supplier", "partner", "competitor")

STATES: tuple[str, ...] = ("confirming", "active_divergent", "quiet", "unavailable")

BASIS = (
    "counterparties disclosed in 8-K Item 1.01/2.03 material-agreement filings "
    "within 24 months, resolved by unique near-verbatim registrant-name match; "
    "states describe today's tape, not a forecast"
)

#: Exact key sets.  An unknown key is a contract violation, not a warning.
ARTIFACT_KEYS = frozenset({
    "schema", "authority", "generated_at", "basket_id", "as_of",
    "n_outsiders", "n_confirming", "n_with_tape", "edge_window_months",
    "outsiders", "basis", "coverage_warnings",
})
OUTSIDER_KEYS = frozenset({
    "ticker", "name", "linked_members", "edge_n", "last_filed_at",
    "state", "move_spy_adj", "active",
})
LINK_KEYS = frozenset({"member", "relationship", "filed_at", "accession", "form", "item"})

LEDGER_COLUMNS: tuple[str, ...] = (
    "member_ticker", "outsider_ticker", "relationship", "accession", "form",
    "item", "filed_at", "extracted_name_raw", "admitted", "reject_reason",
    "advanced_at",
)

#: Identity of a ledger row.  A row whose key was written before is never
#: re-written — that is what makes the store append-only in practice.
LEDGER_KEY: tuple[str, ...] = ("accession", "member_ticker", "extracted_name_raw", "item")

#: Row text fields consulted for the subtype rules, in order.  Absent fields are
#: skipped; the committed parquet today carries only `counterparty`.
_TEXT_FIELDS: tuple[str, ...] = (
    "agreement_title", "title", "description", "snippet", "item_text", "counterparty",
)

#: Subtype keyword table.  Order is load-bearing — see the docstring.
_SUBTYPE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("merger_related", (
        "merger", "acquisition", "acquire", "business combination",
        "share purchase agreement", "tender offer", "plan of merger",
    )),
    ("financing", (
        "credit agreement", "loan", "notes", "note purchase", "indenture",
        "debenture", "facility", "financing", "revolver", "term loan",
    )),
    ("license", ("license", "licence", "licensing", "sublicense")),
    ("collaboration", (
        "collaboration", "joint development", "co-development", "joint venture",
        "partnership", "strategic alliance",
    )),
    ("supply_agreement", (
        "supply", "supplier agreement", "offtake", "off-take", "manufacturing agreement",
    )),
    ("purchase_agreement", ("purchase", "procurement", "order agreement")),
)


class ContractError(ValueError):
    """Raised when an artifact does not satisfy `group_linked_outsiders.v1`."""


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _text(value: Any) -> str | None:
    """Trimmed string, or None for anything empty / null / the literal 'None'."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    rendered = str(value).strip()
    if not rendered or rendered.lower() in ("none", "nan", "null"):
        return None
    return rendered


def _data_root(data_root: Path | None) -> Path:
    if data_root is not None:
        return Path(data_root)
    from lib import config
    return config.data_dir()


def _site_root(site_root: Path | None) -> Path:
    if site_root is not None:
        return Path(site_root)
    from lib import config
    return config.ROOT / config.load()["storage"]["site_dir"]


def _as_of_date(as_of: str | date | None) -> date:
    if as_of is None:
        return datetime.now(timezone.utc).date()
    if isinstance(as_of, datetime):
        return as_of.date()
    if isinstance(as_of, date):
        return as_of
    return pd.Timestamp(str(as_of)).date()


def _activity_constants() -> tuple[float, float, int]:
    """Activity thresholds, sourced from `engine.group_pulse` when it exists.

    GR0 (group_pulse) and GR3 (this module) ship as sibling PRs, so the import
    is optional by construction.  When group_pulse is present its constants win,
    which makes drift between the two definitions impossible rather than merely
    unlikely; the test suite pins the fallbacks to the masterplan literals.
    """
    try:  # pragma: no cover - exercised once group_pulse lands
        _gp = import_module("engine.group_pulse")
    except ModuleNotFoundError as exc:
        # GR0 is still an independently reviewed sibling (#4995).  Only its
        # literal absence authorises the frozen masterplan fallback; a missing
        # dependency inside a present group_pulse must remain a real failure.
        if exc.name != "engine.group_pulse":
            raise
        return (ACTIVITY_Z, ACTIVITY_VOLUME_RATIO, ACTIVITY_LOOKBACK_D)
    else:
        return (
            float(getattr(_gp, "ACTIVITY_Z", ACTIVITY_Z)),
            float(getattr(_gp, "ACTIVITY_VOLUME_RATIO", ACTIVITY_VOLUME_RATIO)),
            int(getattr(_gp, "ACTIVITY_LOOKBACK_D", ACTIVITY_LOOKBACK_D)),
        )


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------


def load_membership(data_root: Path | None = None) -> dict[str, list[str]]:
    """basket_id → active member tickers, from the curated US membership file."""
    path = _data_root(data_root) / "baskets" / "membership.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001 — a broken input degrades, never crashes
        log.error("group_linked_outsiders: membership.json unreadable: %s", exc)
        return {}
    out: dict[str, list[str]] = {}
    for basket_id, basket in (payload.get("baskets") or {}).items():
        members: list[str] = []
        for member in (basket or {}).get("members") or []:
            if not isinstance(member, Mapping) or member.get("removed") is not None:
                continue
            ticker = _text(member.get("ticker"))
            if ticker:
                members.append(ticker.upper())
        out[str(basket_id)] = sorted(set(members))
    return out


def registry_path(data_root: Path | None = None) -> Path | None:
    """Newest committed SEC company_tickers snapshot, by filename date."""
    directory = _data_root(data_root) / "symbol_directory" / "cik_map"
    if not directory.exists():
        return None
    snapshots = sorted(directory.glob("*.parquet"), key=lambda p: p.name)
    return snapshots[-1] if snapshots else None


def load_registry(data_root: Path | None = None) -> tuple[dict[str, list[dict[str, Any]]], Path | None]:
    """Registrant index bucketed by suffix-stripped core name.

    Returns ``(core -> [{ticker, title}], snapshot_path)``.  Bucketing by core is
    what lets `name_match_tier` — the imported govrev admission rule — decide
    every candidate; the bucket is a lookup, never a match.
    """
    path = registry_path(data_root)
    if path is None:
        return {}, None
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        log.error("group_linked_outsiders: registry unreadable (%s): %s", path, exc)
        return {}, path
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in frame.to_dict("records"):
        title = _text(row.get("title"))
        ticker = _text(row.get("ticker"))
        if not title or not ticker:
            continue
        normalised = normalize_legal_name(title)
        if not normalised:
            continue
        core, _ = strip_legal_suffix(normalised)
        buckets.setdefault(core, []).append({"ticker": ticker.upper(), "title": title})
    return buckets, path


def load_events(data_root: Path | None = None) -> pd.DataFrame:
    """The committed 8-K material-event table, or an empty frame."""
    path = _data_root(data_root) / "edgar" / "material_8k_events.parquet"
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        log.error("group_linked_outsiders: material_8k_events unreadable: %s", exc)
        return pd.DataFrame()


def load_pulse(site_root: Path | None = None) -> dict[str, Any] | None:
    """`site/basketdata/pulse.json`, or None when the sibling wave has not run."""
    path = _site_root(site_root) / "basketdata" / "pulse.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.error("group_linked_outsiders: pulse.json unreadable: %s", exc)
        return None
    return payload if isinstance(payload, Mapping) else None


def pulse_session_date(pulse: Mapping[str, Any] | None) -> date | None:
    """The DATA SESSION `pulse.json` was built for, or None when it carries no stamp.

    The GR planes must agree on what "today" is.  `pulse.json` stamps the last session
    present in the member tape (`engine/group_pulse.py`: ``as_of = panel["index"].max()``)
    and `earnings_pulse.json` follows it, so a plane that stamped the WALL-CLOCK run date
    instead read a session ahead of the tape its outsider moves are joined to — three days
    ahead over a Monday run.  Audited 2026-08-10 (F-7 tail): pulse 08-07, this plane 08-10.
    """
    if not isinstance(pulse, Mapping):
        return None
    stamps: list[date] = []
    for entry in pulse.values():
        if not isinstance(entry, Mapping):
            continue
        raw = entry.get("as_of")
        if not raw:
            continue
        try:
            stamps.append(pd.Timestamp(str(raw)).date())
        except Exception:  # noqa: BLE001, PERF203
            continue
    return max(stamps) if stamps else None


def _resolve_stamp(as_of: str | date | None,
                   pulse: Mapping[str, Any] | None) -> date:
    """The session this run DESCRIBES: the caller's `as_of`, else the data session
    `pulse.json` was built for, else — disclosed, never silent — the run date."""
    if as_of is not None:
        return _as_of_date(as_of)
    session = pulse_session_date(pulse)
    if session is not None:
        return session
    print("::warning title=linked-outsiders-as-of::pulse.json carries no readable as_of; "
          "stamping this run with the wall-clock date, which can sit ahead of the tape "
          "these outsider reads are joined to", flush=True)
    return _as_of_date(None)


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------


def material_items(items: Any) -> tuple[str, ...]:
    """The Item 1.01 / 2.03 codes named by a row's `items` cell, in order."""
    raw = _text(items)
    if raw is None:
        return ()
    present = [code for code in MATERIAL_ITEMS if code in raw]
    return tuple(present)


def relationship_subtype(row: Mapping[str, Any]) -> str:
    """Deterministic agreement subtype for one 8-K row.  See the docstring table."""
    parts = [_text(row.get(field)) for field in _TEXT_FIELDS]
    blob = " ".join(part for part in parts if part).casefold()
    for relationship, keywords in _SUBTYPE_RULES:
        if any(keyword in blob for keyword in keywords):
            return relationship
    items = material_items(row.get("items"))
    if "2.03" in items and "1.01" not in items:
        return "financing"
    return "disclosed_agreement"


def resolve_counterparty(
    extracted_name: Any,
    registry: Mapping[str, list[dict[str, Any]]],
    filer_ticker: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Resolve an extracted name to exactly one SEC registrant.

    Returns ``(ticker, registrant_title, reject_reason)``.  Exactly one of
    ``ticker`` and ``reject_reason`` is non-None — a rejection is never a weaker
    accept, and never a silent drop.
    """
    normalised = normalize_legal_name(extracted_name)
    if not normalised:
        return None, None, "no_registrant_match"
    core, _ = strip_legal_suffix(normalised)
    candidates = registry.get(core) or []
    survivors: dict[str, str] = {}
    for candidate in candidates:
        if name_match_tier(extracted_name, candidate["title"]) is None:
            continue
        survivors.setdefault(candidate["ticker"], candidate["title"])
    if not survivors:
        return None, None, "no_registrant_match"
    if len(survivors) > 1:
        return None, None, "ambiguous_tie"
    ticker, title = next(iter(survivors.items()))
    if filer_ticker and ticker == str(filer_ticker).upper():
        return None, None, "self_reference"
    return ticker, title, None


def candidate_edges(
    events: pd.DataFrame,
    member_tickers: set[str],
    as_of: date,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Rows that clear edge admission, plus the coverage counts behind them."""
    counts = {
        "rows_total": int(len(events)),
        "rows_material_items": 0,
        "rows_material_in_window": 0,
        "rows_with_counterparty": 0,
        "rows_filer_not_member": 0,
        "candidates": 0,
    }
    if events.empty:
        return [], counts

    required = ("filing_date", "items", "ticker", "accession")
    absent = [column for column in required if column not in events.columns]
    if absent:
        log.error("group_linked_outsiders: events table missing columns %s", absent)
        return [], counts

    cutoff = pd.Timestamp(as_of) - pd.DateOffset(months=EDGE_WINDOW_MONTHS)
    filed = pd.to_datetime(events["filing_date"], errors="coerce")
    items_mask = events["items"].astype("string").str.contains(r"1\.01|2\.03", na=False, regex=True)
    counts["rows_material_items"] = int(items_mask.sum())
    window_mask = items_mask & filed.notna() & (filed >= cutoff) & (filed <= pd.Timestamp(as_of))
    counts["rows_material_in_window"] = int(window_mask.sum())

    scoped = events.loc[window_mask]
    out: list[dict[str, Any]] = []
    for row in scoped.to_dict("records"):
        extracted = _text(row.get("counterparty"))
        if extracted is None:
            continue
        counts["rows_with_counterparty"] += 1
        filer = (_text(row.get("ticker")) or "").upper()
        if filer not in member_tickers:
            counts["rows_filer_not_member"] += 1
            continue
        items = material_items(row.get("items"))
        out.append({
            "member_ticker": filer,
            "extracted_name_raw": extracted,
            "relationship": relationship_subtype(row),
            "accession": _text(row.get("accession")) or "",
            "form": _text(row.get("form")) or "8-K",
            "item": ",".join(items),
            "filed_at": pd.Timestamp(row.get("filing_date")).date().isoformat(),
        })
    counts["candidates"] = len(out)
    out.sort(key=lambda e: (e["filed_at"], e["accession"], e["member_ticker"], e["extracted_name_raw"]))
    return out, counts


def resolve_edges(
    candidates: Sequence[Mapping[str, Any]],
    registry: Mapping[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Attach a resolution outcome to every candidate.  Nothing is dropped."""
    resolved: list[dict[str, Any]] = []
    for edge in candidates:
        ticker, title, reason = resolve_counterparty(
            edge["extracted_name_raw"], registry, edge["member_ticker"],
        )
        row = dict(edge)
        row["outsider_ticker"] = ticker
        row["outsider_name"] = title
        row["admitted"] = reason is None
        row["reject_reason"] = reason
        resolved.append(row)
    return resolved


# --------------------------------------------------------------------------
# Tape
# --------------------------------------------------------------------------


def _load_prices(ticker: str, data_root: Path | None = None) -> pd.DataFrame | None:
    """Daily bars for one ticker.  Mirrors basket_turn_watch's store ladder."""
    root = _data_root(data_root)
    ladder = ("stocks", "yahoo") if ticker == "SPY" else ("stocks", "baskets/ohlcv")
    for sub in ladder:
        path = root / sub / f"{ticker}.parquet"
        if not path.exists():
            continue
        try:
            frame = pd.read_parquet(path)
            if "close" not in frame.columns or frame.empty:
                continue
            frame = frame.copy()
            frame.index = pd.to_datetime(frame.index)
            return frame.sort_index()
        except Exception as exc:  # noqa: BLE001
            log.debug("group_linked_outsiders: %s from %s/: %s", ticker, sub, exc)
            continue
    return None


def tape_read(
    ticker: str,
    as_of: date,
    spy_close: pd.Series | None,
    data_root: Path | None = None,
) -> tuple[float | None, bool | None]:
    """`(move_spy_adj, active)` for one ticker on `as_of`.

    Either element is None when the trailing tape cannot support it; a None is a
    refusal to describe, never a zero and never a False.
    """
    z_threshold, volume_ratio, lookback = _activity_constants()
    frame = _load_prices(ticker, data_root)
    if frame is None or spy_close is None or spy_close.empty:
        return None, None

    close = pd.to_numeric(frame["close"], errors="coerce").dropna()
    if len(close) < 2:
        return None, None
    close = close[close.index <= pd.Timestamp(as_of)]
    spy = spy_close[spy_close.index <= pd.Timestamp(as_of)]
    if len(close) < 2 or len(spy) < 2:
        return None, None

    adjusted = (close.pct_change() - spy.pct_change().reindex(close.index)).dropna()
    if adjusted.empty:
        return None, None
    stale_by = (pd.Timestamp(as_of) - pd.Timestamp(adjusted.index[-1])).days
    if stale_by > MAX_TAPE_STALENESS_D:
        return None, None
    move = float(adjusted.iloc[-1])

    active: bool | None = None
    window = adjusted.iloc[-lookback:]
    if len(window) >= lookback:
        deviation = float(window.std(ddof=0))
        if deviation > 0:
            active = abs((move - float(window.mean())) / deviation) >= z_threshold

    if "volume" in frame.columns:
        volumes = pd.to_numeric(frame["volume"], errors="coerce").dropna()
        volumes = volumes[volumes.index <= pd.Timestamp(as_of)]
        window_v = volumes.iloc[-lookback:]
        if len(window_v) >= lookback:
            median = float(window_v.median())
            if median > 0:
                hot = float(volumes.iloc[-1]) >= volume_ratio * median
                active = hot if active is None else (active or hot)
    return move, active


def _outsider_state(
    move: float | None,
    active: bool | None,
    basket_sign: str | None,
) -> str:
    if move is None or active is None:
        return "unavailable"
    if basket_sign is None:
        return "unavailable"
    if not active:
        return "quiet"
    if basket_sign in ("up", "down") and move != 0.0:
        move_sign = "up" if move > 0 else "down"
        if move_sign == basket_sign:
            return "confirming"
    return "active_divergent"


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------


def _basket_sign(pulse: Mapping[str, Any] | None, basket_id: str) -> str | None:
    if not pulse:
        return None
    entry = pulse.get(basket_id)
    if not isinstance(entry, Mapping):
        return None
    direction = entry.get("direction")
    if not isinstance(direction, Mapping):
        return None
    return _text(direction.get("sign"))


def compute(
    *,
    as_of: str | date | None = None,
    data_root: Path | None = None,
    site_root: Path | None = None,
    pulse: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Build one `group_linked_outsiders.v1` object per US basket."""
    generated = generated_at or datetime.now(timezone.utc).isoformat()
    membership = load_membership(data_root)
    registry, snapshot = load_registry(data_root)
    events = load_events(data_root)
    if pulse is None:
        pulse = load_pulse(site_root)
    # Pulse is loaded BEFORE the stamp: with no explicit as_of this plane takes its session
    # from the sibling artifact rather than the clock, so the whole GR plane stamps one day.
    stamp = _resolve_stamp(as_of, pulse)

    member_universe = {t for members in membership.values() for t in members}
    candidates, counts = candidate_edges(events, member_universe, stamp)
    edges = resolve_edges(candidates, registry)
    admitted = [e for e in edges if e["admitted"]]

    global_warnings: list[str] = []
    if counts["rows_with_counterparty"] == 0:
        global_warnings.append(
            f"source_counterparty_absent: 0 of {counts['rows_material_in_window']} "
            "in-window Item 1.01/2.03 filings carry an extracted counterparty name, "
            "so no relationship edge is admissible this run"
        )
    if snapshot is None:
        global_warnings.append(
            "registrant_snapshot_absent: no committed SEC company_tickers snapshot, "
            "so no counterparty name could be resolved"
        )
    if candidates and not admitted:
        # An empty list with no stated reason is a silent zero.  Name the census.
        reasons: dict[str, int] = {}
        for edge in edges:
            if edge["reject_reason"]:
                reasons[edge["reject_reason"]] = reasons.get(edge["reject_reason"], 0) + 1
        census = ", ".join(f"{reason}={n}" for reason, n in sorted(reasons.items()))
        global_warnings.append(
            f"no_edge_admitted: {len(candidates)} candidate counterparty names, none "
            f"resolved to exactly one SEC registrant ({census})"
        )
    if pulse is None:
        global_warnings.append(
            "basket_direction_unavailable: pulse.json absent, so no outsider is called "
            "confirming or divergent; tape figures are printed where they are readable"
        )

    spy_frame = _load_prices("SPY", data_root)
    spy_close = (
        pd.to_numeric(spy_frame["close"], errors="coerce").dropna()
        if spy_frame is not None and "close" in spy_frame.columns
        else None
    )

    # member -> [edges], so each basket only walks its own members' edges.
    by_member: dict[str, list[dict[str, Any]]] = {}
    for edge in admitted:
        by_member.setdefault(edge["member_ticker"], []).append(edge)

    tape_cache: dict[str, tuple[float | None, bool | None]] = {}
    out: dict[str, dict[str, Any]] = {}

    for basket_id, members in sorted(membership.items()):
        member_set = set(members)
        grouped: dict[str, list[dict[str, Any]]] = {}
        names: dict[str, str] = {}
        for member in members:
            for edge in by_member.get(member, []):
                outsider = edge["outsider_ticker"]
                if not outsider or outsider in member_set:
                    continue
                grouped.setdefault(outsider, []).append(edge)
                if edge.get("outsider_name"):
                    names.setdefault(outsider, edge["outsider_name"])

        # (edge_n desc, last_filed_at desc, ticker asc) — the disclosed order.
        ranked = sorted(
            grouped.items(),
            key=lambda kv: (
                -len(kv[1]),
                -pd.Timestamp(max(e["filed_at"] for e in kv[1])).toordinal(),
                kv[0],
            ),
        )
        warnings = list(global_warnings)
        if len(ranked) > MAX_OUTSIDERS_PER_BASKET:
            warnings.append(
                f"outsider_cap_applied: {len(ranked)} linked outsiders found, "
                f"{MAX_OUTSIDERS_PER_BASKET} published, ordered by edge count then "
                "most recent filing"
            )
            ranked = ranked[:MAX_OUTSIDERS_PER_BASKET]

        sign = _basket_sign(pulse, basket_id)
        outsiders: list[dict[str, Any]] = []
        n_with_tape = 0
        for ticker, ticker_edges in ranked:
            if ticker not in tape_cache:
                tape_cache[ticker] = tape_read(ticker, stamp, spy_close, data_root)
            move, active = tape_cache[ticker]
            if move is not None and active is not None:
                n_with_tape += 1
            links = sorted(
                (
                    {
                        "member": e["member_ticker"],
                        "relationship": e["relationship"],
                        "filed_at": e["filed_at"],
                        "accession": e["accession"],
                        "form": e["form"],
                        "item": e["item"],
                    }
                    for e in ticker_edges
                ),
                key=lambda link: (link["filed_at"], link["accession"], link["member"]),
                reverse=True,
            )
            outsiders.append({
                "ticker": ticker,
                "name": names.get(ticker),
                "linked_members": links,
                "edge_n": len(links),
                "last_filed_at": max(e["filed_at"] for e in ticker_edges),
                "state": _outsider_state(move, active, sign),
                "move_spy_adj": move,
                "active": active,
            })

        no_tape = len(outsiders) - n_with_tape
        if no_tape > 0:
            warnings.append(
                f"tape_unavailable: {no_tape} of {len(outsiders)} published outsiders "
                "have no usable trailing tape; the disclosed relationship still stands"
            )

        out[basket_id] = {
            "schema": SCHEMA,
            "authority": AUTHORITY,
            "generated_at": generated,
            "basket_id": basket_id,
            "as_of": stamp.isoformat(),
            "n_outsiders": len(outsiders),
            "n_confirming": sum(1 for o in outsiders if o["state"] == "confirming"),
            "n_with_tape": n_with_tape,
            "edge_window_months": EDGE_WINDOW_MONTHS,
            "outsiders": outsiders,
            "basis": BASIS,
            "coverage_warnings": warnings,
        }
    return out


def resolution_report(
    *,
    as_of: str | date | None = None,
    data_root: Path | None = None,
) -> dict[str, Any]:
    """Yield census for the smoke run: what the source held and what resolved."""
    stamp = _as_of_date(as_of)
    membership = load_membership(data_root)
    registry, snapshot = load_registry(data_root)
    events = load_events(data_root)
    member_universe = {t for members in membership.values() for t in members}
    candidates, counts = candidate_edges(events, member_universe, stamp)
    edges = resolve_edges(candidates, registry)
    reasons: dict[str, int] = {}
    for edge in edges:
        if edge["reject_reason"]:
            reasons[edge["reject_reason"]] = reasons.get(edge["reject_reason"], 0) + 1
    return {
        "as_of": stamp.isoformat(),
        "registry_snapshot": str(snapshot) if snapshot else None,
        "registry_names": sum(len(v) for v in registry.values()),
        "n_baskets": len(membership),
        "n_members": len(member_universe),
        **counts,
        "admitted": sum(1 for e in edges if e["admitted"]),
        "rejected": sum(1 for e in edges if not e["admitted"]),
        "reject_reasons": dict(sorted(reasons.items())),
    }


# --------------------------------------------------------------------------
# Contract validation
# --------------------------------------------------------------------------


def validate_artifact(obj: Any) -> None:
    """Raise `ContractError` unless `obj` is a valid `group_linked_outsiders.v1`."""
    if not isinstance(obj, Mapping):
        raise ContractError("artifact must be a mapping")
    keys = set(obj)
    unknown = keys - ARTIFACT_KEYS
    if unknown:
        raise ContractError(f"unknown artifact keys: {sorted(unknown)}")
    missing = ARTIFACT_KEYS - keys
    if missing:
        raise ContractError(f"missing artifact keys: {sorted(missing)}")
    if obj["schema"] != SCHEMA:
        raise ContractError(f"schema must be {SCHEMA!r}")
    if obj["authority"] != AUTHORITY:
        raise ContractError(f"authority must be {AUTHORITY!r}")
    if obj["edge_window_months"] != EDGE_WINDOW_MONTHS:
        raise ContractError("edge_window_months must be the disclosed window")
    if obj["basis"] != BASIS:
        raise ContractError("basis must be the frozen disclosure string")
    if not isinstance(obj["coverage_warnings"], list):
        raise ContractError("coverage_warnings must be a list")
    outsiders = obj["outsiders"]
    if not isinstance(outsiders, list):
        raise ContractError("outsiders must be a list")
    if obj["n_outsiders"] != len(outsiders):
        raise ContractError("n_outsiders must equal len(outsiders)")

    confirming = 0
    with_tape = 0
    for outsider in outsiders:
        if not isinstance(outsider, Mapping):
            raise ContractError("each outsider must be a mapping")
        unknown = set(outsider) - OUTSIDER_KEYS
        if unknown:
            raise ContractError(f"unknown outsider keys: {sorted(unknown)}")
        missing = OUTSIDER_KEYS - set(outsider)
        if missing:
            raise ContractError(f"missing outsider keys: {sorted(missing)}")
        if outsider["state"] not in STATES:
            raise ContractError(f"unknown state: {outsider['state']!r}")
        links = outsider["linked_members"]
        if not isinstance(links, list) or not links:
            raise ContractError("linked_members must be a non-empty list")
        if outsider["edge_n"] != len(links):
            raise ContractError("edge_n must equal len(linked_members)")
        for link in links:
            if not isinstance(link, Mapping):
                raise ContractError("each linked_member must be a mapping")
            unknown = set(link) - LINK_KEYS
            if unknown:
                raise ContractError(f"unknown linked_member keys: {sorted(unknown)}")
            missing = LINK_KEYS - set(link)
            if missing:
                raise ContractError(f"missing linked_member keys: {sorted(missing)}")
            if link["relationship"] not in RELATIONSHIPS:
                raise ContractError(f"unknown relationship: {link['relationship']!r}")
        if outsider["state"] == "confirming":
            confirming += 1
        if outsider["move_spy_adj"] is not None and outsider["active"] is not None:
            with_tape += 1
    if obj["n_confirming"] != confirming:
        raise ContractError("n_confirming must equal the confirming outsider count")
    if obj["n_with_tape"] != with_tape:
        raise ContractError("n_with_tape must equal the readable-tape outsider count")


# --------------------------------------------------------------------------
# Site artifact
# --------------------------------------------------------------------------


def write_site_artifact(result: Mapping[str, Any], site_root: Path | None = None) -> Path:
    """Write `site/basketdata/linked_outsiders.json`.  Returns the written path."""
    out_dir = _site_root(site_root) / "basketdata"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "linked_outsiders.json"
    out_path.write_text(
        json.dumps(result, separators=(",", ":"), default=str) + "\n",
        encoding="utf-8",
    )
    return out_path


# --------------------------------------------------------------------------
# Edge ledger — append-only, nightly-gated
# --------------------------------------------------------------------------


def ledger_path(data_root: Path | None = None) -> Path:
    return _data_root(data_root) / "group_pulse" / "linked_outsider_edges.parquet"


def _ledger_rows(edges: Sequence[Mapping[str, Any]], advanced_at: str) -> pd.DataFrame:
    rows = [
        {
            "member_ticker": e["member_ticker"],
            "outsider_ticker": e.get("outsider_ticker"),
            "relationship": e["relationship"],
            "accession": e["accession"],
            "form": e["form"],
            "item": e["item"],
            "filed_at": e["filed_at"],
            "extracted_name_raw": e["extracted_name_raw"],
            "admitted": bool(e["admitted"]),
            "reject_reason": e.get("reject_reason"),
            "advanced_at": advanced_at,
        }
        for e in edges
    ]
    return pd.DataFrame(rows, columns=list(LEDGER_COLUMNS))


def advance_edge_ledger(
    edges: Sequence[Mapping[str, Any]],
    data_root: Path | None = None,
    advanced_at: str | None = None,
) -> int:
    """Append never-seen candidate edges.  Returns the number of rows appended.

    Gated on the nightly lane: any other lane computes and discards, so an
    intraday run can never advance a forward ledger.  Existing rows are read,
    kept in their original order, and written back untouched — a re-run over
    identical inputs appends nothing and leaves the file byte-identical.
    """
    if not ledger_lane.nightly_advance_enabled():
        log.info("group_linked_outsiders: ledger advance gated — not the US nightly lane")
        return 0

    path = ledger_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = advanced_at or datetime.now(timezone.utc).isoformat()
    new = _ledger_rows(edges, stamp)

    prior = pd.DataFrame(columns=list(LEDGER_COLUMNS))
    if path.exists():
        try:
            prior = pd.read_parquet(path)
        except Exception as exc:  # noqa: BLE001
            print(
                "::warning title=linked-outsider-ledger::existing ledger unreadable "
                f"({exc}); refusing to advance rather than overwrite it",
                flush=True,
            )
            return 0

    if not new.empty:
        new = new.drop_duplicates(subset=list(LEDGER_KEY), keep="first")
    if not prior.empty and not new.empty:
        seen = set(map(tuple, prior[list(LEDGER_KEY)].astype("string").fillna("").to_numpy()))
        keys = list(map(tuple, new[list(LEDGER_KEY)].astype("string").fillna("").to_numpy()))
        new = new.loc[[key not in seen for key in keys]]
    if new.empty:
        # Nothing new is nothing written.  An empty ledger file is not created:
        # a store of zero facts would only publish an all-null dtype schema.
        return 0

    combined = pd.concat([prior, new], ignore_index=True) if not prior.empty else new
    combined.to_parquet(path, index=False)
    return int(len(new))


def run(
    *,
    as_of: str | date | None = None,
    data_root: Path | None = None,
    site_root: Path | None = None,
) -> dict[str, Any]:
    """Nightly entry point: compute, write the artifact, advance the ledger."""
    # One read of pulse.json, one stamp: the edge WINDOW and the artifact stamp are the
    # same session by construction, so they cannot drift apart the way F-7 found them.
    pulse = load_pulse(site_root)
    stamp = _resolve_stamp(as_of, pulse)
    membership = load_membership(data_root)
    registry, _ = load_registry(data_root)
    events = load_events(data_root)
    member_universe = {t for members in membership.values() for t in members}
    candidates, _ = candidate_edges(events, member_universe, stamp)
    edges = resolve_edges(candidates, registry)

    result = compute(as_of=stamp, data_root=data_root, site_root=site_root, pulse=pulse)
    path = write_site_artifact(result, site_root)
    appended = advance_edge_ledger(edges, data_root)
    return {
        "path": str(path),
        "baskets": len(result),
        "baskets_with_outsiders": sum(1 for v in result.values() if v["n_outsiders"]),
        "edges_appended": appended,
    }


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print(json.dumps(resolution_report(), indent=2))
