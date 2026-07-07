"""Oracle R-SP19 — Per-complex member-level stock personality roll-up.

ADDITIVE WAVE (Oracle Additive Extension Protocol)
---------------------------------------------------
This module adds ``personality_context`` to each complex dict in oracle_state.json
as a MINOR-VERSION additive field.  Nothing is renamed, removed, or restructured.
Consumers that do not recognise this field must silently ignore it (tolerant-reader
rule, contract.py §TOLERANT-READER RULE).

WHAT IT COMPUTES
----------------
Given:
  - ``complexes_def``  — list of complex dicts from rotation_groups.json (each has
    ``id`` and ``members`` = oracle node IDs).  REUSED from the pipeline's existing
    mapping (engine/oracle/live.py _load_rotation_groups).
  - ``site_aggregate`` — dict loaded from site/factordata/stock_personality.json
    (fail-open: absent/stale ⇒ the field is OMITTED from the complex dict,
    not set to null — ensures tolerant consumers see no field rather than a
    misleading null).
  - ``theme_ticker_map`` — dict mapping oracle node ID → list of stock tickers,
    derived from site/basketdata/member_context.json (fail-open: absent ⇒
    coverage will be 0 / field omitted).

Per complex, computes:
  personality_context: {
    personality_as_of:           str (ISO date from aggregate.as_of — staleness visibility;
                                      mirrors the per-block as_of discipline of sibling B1
                                      fields and the masterplan convention)
    dominant_member_archetypes:  [(key, share), ...]   top 3 by share
                                      share = count(ticker) / total covered TICKERS
    dominant_chart_labels:       [(key, share), ...]   top 3 by share
                                      share = count(label-emission) / total label-EMISSIONS
                                      (a single ticker may emit multiple chart labels)
    tinderbox_share:             float   share of covered TICKERS with
                                         ownership_habitat containing
                                         "short_interest_tinderbox"
                                         (denominator = covered tickers, not nodes)
    event_override_share:        float   share of covered TICKERS with
                                         current_mode containing "event_override"
                                         (denominator = covered tickers, not nodes)
    share_denominators:          {"archetypes_and_flags": "covered_tickers",
                                   "chart_labels": "label_emissions"}
                                      honesty field: archetypes/tinderbox/event_override
                                      shares are per covered TICKER; dominant_chart_labels
                                      shares are per label-EMISSION (multi-label per ticker).
    member_coverage:             float   fraction of node members that resolved
                                         to ≥1 ticker with a USABLE (dict) personality record
    confidence_class:            "descriptive"
    lineage:                     str (anchor to this masterplan)
  }

STALENESS GATE (R-SP19)
-----------------------
If the aggregate's ``as_of`` date is more than MAX_PERSONALITY_TRADING_DAYS=2 trading
days behind the oracle run date, the personality_context field is OMITTED entirely
(docstring promise: absent/stale ⇒ omit).  Trading-day-aware check reuses the same
pandas.bdate_range idiom as contract.py (engine/oracle/contract.py:206-208).

SHARE DENOMINATORS (honesty contract)
---------------------------------------
- ``dominant_member_archetypes``, ``tinderbox_share``, ``event_override_share``:
  denominator = number of covered TICKERS (tickers with a usable dict record).
- ``dominant_chart_labels``:
  denominator = total label EMISSIONS (a ticker with 2 chart labels contributes 2 to
  the denominator — not 1).  This means a ticker with many labels can dominate.
  The ``share_denominators`` field makes this explicit.

DESIGN CONSTRAINTS (R-SP19 + oracle contract)
---------------------------------------------
- confidence_class ALWAYS "descriptive" — no edge claim.
- Field names avoid banned substrings: forecast, predicted, target, expected_return.
- Fail-open at every level: missing aggregate ⇒ no field emitted on any complex.
- Stale aggregate (>2 trading days) ⇒ no field emitted on any complex.
- Never modifies the complex dict in-place before producing the result dict;
  callers append the result additively.
- This module does NOT own writing oracle_state.json — live.py owns that.

Join path
---------
oracle node (rotation_groups.json) → ticker (member_context.json themes) →
personality data (stock_personality.json per_ticker).

Coverage is partial (~35/83 oracle nodes have theme membership in member_context).
``member_coverage`` in each complex's personality_context reflects true coverage.
A node is counted as "covered" only if ≥1 of its tickers resolves to a USABLE (dict)
per_ticker record — a non-dict record does NOT count as covered.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_LINEAGE = (
    "research/STOCK_PERSONALITY_MASTERPLAN_BY_FABLE.md R-SP19 — "
    "member-level stock personality roll-up; descriptive/display tier only."
)

# Staleness gate: same trading-day threshold as the oracle contract.
# Reuses the pandas.bdate_range idiom from engine/oracle/contract.py:206-208.
# MAX_TRADING_DAYS=2 matches contract.MAX_TRADING_DAYS exactly.
_MAX_PERSONALITY_TRADING_DAYS: int = 2


def _is_aggregate_stale(as_of_str: str | None, run_date: datetime | None = None) -> bool:
    """Return True if *as_of_str* is stale relative to *run_date*.

    Staleness is TRADING-DAY-AWARE — uses the same pandas.bdate_range idiom as
    engine/oracle/contract.py (lines 206-208): count business days between
    as_of and run_date (bdate_range includes both endpoints; subtract 1 for
    the as_of day itself).

    A None/unparseable as_of is treated as stale (fail-closed on bad data).
    """
    if not as_of_str:
        return True
    try:
        asof_dt = datetime.fromisoformat(as_of_str).replace(tzinfo=timezone.utc)
        now = run_date if run_date is not None else datetime.now(timezone.utc)
        import pandas as _pd  # noqa: PLC0415 — late import mirrors contract.py pattern
        bdays_behind = max(0, len(_pd.bdate_range(asof_dt.date(), now.date())) - 1)
        return bdays_behind > _MAX_PERSONALITY_TRADING_DAYS
    except Exception:  # noqa: BLE001
        return True  # unparseable ⇒ treat as stale


# ---------------------------------------------------------------------------
# Loader helpers (all fail-open)
# ---------------------------------------------------------------------------

def _read_json(p: Path) -> dict | None:
    """Read and parse JSON from *p*; return None on any failure."""
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("personality_context: unreadable %s — %s", p, exc)
        return None


def load_site_aggregate(repo: Path | str) -> dict | None:
    """Load site/factordata/stock_personality.json (fail-open).

    Returns the parsed dict on success, None if absent/unreadable.
    Callers MUST check for None — absent aggregate ⇒ omit personality_context.
    """
    p = Path(repo) / "site" / "factordata" / "stock_personality.json"
    if not p.exists():
        log.info("personality_context: site aggregate absent (%s) — omitting", p)
        return None
    d = _read_json(p)
    if not isinstance(d, dict):
        log.warning("personality_context: site aggregate unreadable — omitting")
        return None
    return d


def load_theme_ticker_map(repo: Path | str) -> dict[str, list[str]]:
    """Load oracle-node → [ticker, ...] map from site/basketdata/member_context.json.

    Returns {} on any failure (fail-open).

    Join path: oracle complex → oracle node members (rotation_groups.json) →
    tickers (member_context.json themes[].members[].ticker).
    """
    p = Path(repo) / "site" / "basketdata" / "member_context.json"
    if not p.exists():
        log.info("personality_context: member_context.json absent — coverage=0")
        return {}
    d = _read_json(p)
    if not isinstance(d, dict):
        return {}
    mapping: dict[str, list[str]] = {}
    for theme in (d.get("themes") or []):
        if not isinstance(theme, dict):
            continue
        node_id = theme.get("id")
        if not node_id:
            continue
        tickers = [
            m["ticker"]
            for m in (theme.get("members") or [])
            if isinstance(m, dict) and m.get("ticker")
        ]
        if tickers:
            mapping[str(node_id)] = tickers
    return mapping


# ---------------------------------------------------------------------------
# Core roll-up
# ---------------------------------------------------------------------------

def _top3_shares(counter: Counter) -> list[tuple[str, float]]:
    """Return [(key, share), ...] top-3 by count; share = count / total."""
    total = sum(counter.values())
    if total == 0:
        return []
    top = counter.most_common(3)
    return [(k, round(v / total, 4)) for k, v in top]


def compute_personality_context_for_complex(
    complex_def: dict,
    per_ticker: dict[str, dict],
    theme_ticker_map: dict[str, list[str]],
    *,
    personality_as_of: str | None = None,
) -> dict[str, Any] | None:
    """Compute personality_context for a single complex.

    Parameters
    ----------
    complex_def:
        One entry from rotation_groups.json (has ``id``, ``members``).
    per_ticker:
        The ``per_ticker`` dict from stock_personality.json slim aggregate.
        Each value: {arch, dna, chart (list), own (list), micro (list), modes (list)}.
    theme_ticker_map:
        oracle node ID → [ticker, ...] from member_context.json.
    personality_as_of:
        ISO date string from the aggregate's ``as_of`` field.  Passed through
        to the emitted block as ``personality_as_of`` (staleness visibility).

    Returns
    -------
    dict with personality_context fields, or None if no coverage.

    Coverage honesty (finding 6):
        A node counts as "covered" (toward member_coverage) ONLY if ≥1 of its
        tickers resolves to a USABLE per_ticker record (isinstance(rec, dict)).
        A ticker present in per_ticker but carrying a non-dict value does NOT
        count as covered.  This prevents coverage=1.0 with empty shares when
        per_ticker entries are non-dict (e.g. null/string).
    """
    node_members: list[str] = list(complex_def.get("members") or [])
    if not node_members:
        return None

    # Collect tickers for this complex by joining through theme_ticker_map.
    # Only tickers whose per_ticker record is a USABLE dict count as resolved.
    resolved_tickers: set[str] = set()
    for node in node_members:
        for ticker in theme_ticker_map.get(node, []):
            rec = per_ticker.get(ticker)
            if isinstance(rec, dict):  # USABLE record only
                resolved_tickers.add(ticker)

    n_nodes_total = len(node_members)
    # A node is "covered" only if ≥1 ticker resolves to a USABLE (dict) record.
    n_nodes_with_data = sum(
        1 for node in node_members
        if any(
            isinstance(per_ticker.get(t), dict)
            for t in theme_ticker_map.get(node, [])
        )
    )
    member_coverage = round(n_nodes_with_data / n_nodes_total, 4) if n_nodes_total else 0.0

    if not resolved_tickers:
        # No coverage — return a coverage-zero block so the consumer can see the gap
        return {
            "personality_as_of": personality_as_of,
            "dominant_member_archetypes": [],
            "dominant_chart_labels": [],
            "tinderbox_share": None,
            "event_override_share": None,
            "share_denominators": {
                "archetypes_and_flags": "covered_tickers",
                "chart_labels": "label_emissions",
            },
            "member_coverage": 0.0,
            "confidence_class": "descriptive",
            "lineage": _LINEAGE,
        }

    archetype_ctr: Counter = Counter()
    chart_ctr: Counter = Counter()
    n_tinderbox = 0
    n_event_override = 0
    n_covered = 0  # count of tickers with usable dict records (already filtered above)

    for ticker in resolved_tickers:
        rec = per_ticker.get(ticker)
        # resolved_tickers already filtered to isinstance(rec, dict) — no re-check needed
        n_covered += 1

        # archetype (single key, may be None) — denominator: covered tickers
        arch = rec.get("arch")
        if arch and isinstance(arch, str):
            archetype_ctr[arch] += 1

        # chart_personality (list of labels) — denominator: label EMISSIONS (not tickers)
        for label in (rec.get("chart") or []):
            if label and isinstance(label, str):
                chart_ctr[label] += 1

        # ownership_habitat — tinderbox flag — denominator: covered tickers
        own = rec.get("own") or []
        if "short_interest_tinderbox" in own:
            n_tinderbox += 1

        # current_mode — event_override flag — denominator: covered tickers
        modes = rec.get("modes") or []
        if "event_override" in modes:
            n_event_override += 1

    tinderbox_share = round(n_tinderbox / n_covered, 4) if n_covered else None
    event_override_share = round(n_event_override / n_covered, 4) if n_covered else None

    return {
        "personality_as_of": personality_as_of,
        "dominant_member_archetypes": _top3_shares(archetype_ctr),
        "dominant_chart_labels": _top3_shares(chart_ctr),
        "tinderbox_share": tinderbox_share,
        "event_override_share": event_override_share,
        # Honesty field: makes explicit that archetype/flag shares use covered-ticker
        # denominator, while chart_label shares use label-emission denominator.
        "share_denominators": {
            "archetypes_and_flags": "covered_tickers",
            "chart_labels": "label_emissions",
        },
        "member_coverage": member_coverage,
        "confidence_class": "descriptive",
        "lineage": _LINEAGE,
    }


# ---------------------------------------------------------------------------
# Public API — additive wave entry point
# ---------------------------------------------------------------------------

_SENTINEL = object()  # sentinel for "not provided" default argument


def append_personality_context(
    complexes: list[dict],
    complexes_def: list[dict],
    repo: Path | str | None = None,
    *,
    site_aggregate: Any = _SENTINEL,
    theme_ticker_map: dict[str, list[str]] | None = None,
) -> list[dict]:
    """Append ``personality_context`` additively to each complex dict.

    Called from oracle_nightly (Step 3b area) AFTER personality + BEFORE state write.
    Also callable from live.py if integrated there.

    Parameters
    ----------
    complexes:
        The list of complex dicts already assembled by live.py
        (each has id, name, name_zh, state, tier, ...).
    complexes_def:
        Raw rotation_groups.json complex entries (each has id + members list).
        Used to look up node membership.
    repo:
        Repo root (for loading site aggregate + theme map).
        If None, infers from this file's location.
    site_aggregate:
        Override the loaded site aggregate (for tests). Pass None explicitly
        to force "absent" behaviour; omit entirely to auto-load.
    theme_ticker_map:
        Override the theme→ticker map (for tests).

    Returns
    -------
    The SAME list with personality_context appended to each dict (additive).
    Dicts that already have personality_context are left unchanged.
    """
    # Resolve repo root
    if repo is None:
        repo = Path(__file__).resolve().parent.parent.parent

    # Auto-load data unless overridden
    if site_aggregate is _SENTINEL:
        site_aggregate = load_site_aggregate(repo)
    if theme_ticker_map is None:
        theme_ticker_map = load_theme_ticker_map(repo)

    # Absent aggregate → omit the field entirely on ALL complexes (R-SP19)
    if site_aggregate is None:
        log.info("personality_context: site aggregate absent — omitting field on all complexes")
        return complexes

    # Staleness gate (R-SP19): if the aggregate's as_of is > _MAX_PERSONALITY_TRADING_DAYS
    # trading days behind the oracle run date, omit the field entirely.
    # Uses same pandas.bdate_range idiom as engine/oracle/contract.py:206-208.
    agg_as_of: str | None = site_aggregate.get("as_of")
    if _is_aggregate_stale(agg_as_of):
        log.warning(
            "personality_context: aggregate as_of=%r is stale (>%d trading days) "
            "— omitting field on all complexes",
            agg_as_of, _MAX_PERSONALITY_TRADING_DAYS,
        )
        return complexes

    per_ticker: dict[str, dict] = site_aggregate.get("per_ticker") or {}
    if not per_ticker:
        log.info("personality_context: per_ticker empty — omitting field on all complexes")
        return complexes

    # Build a map from complex_id → complex_def for O(1) lookup
    def_by_id: dict[str, dict] = {c.get("id", ""): c for c in complexes_def}

    n_appended = 0
    for c in complexes:
        if "personality_context" in c:
            continue  # already stamped; don't overwrite
        cid = c.get("id", "")
        cdef = def_by_id.get(cid)
        if cdef is None:
            # Complex in state but not in rotation_groups — skip silently
            continue
        try:
            ctx = compute_personality_context_for_complex(
                cdef, per_ticker, theme_ticker_map,
                personality_as_of=agg_as_of,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "personality_context: compute failed for complex %s — %s", cid, exc
            )
            ctx = None
        if ctx is not None:
            c["personality_context"] = ctx
            n_appended += 1

    log.info(
        "personality_context: appended to %d/%d complexes", n_appended, len(complexes)
    )
    return complexes
