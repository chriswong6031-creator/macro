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
    dominant_member_archetypes:  [(key, share), ...]   top 3 by share
    dominant_chart_labels:       [(key, share), ...]   top 3 by share
    tinderbox_share:             float   share of covered members with
                                         ownership_habitat containing
                                         "short_interest_tinderbox"
    event_override_share:        float   share of covered members with
                                         current_mode containing "event_override"
    member_coverage:             float   fraction of node members that resolved
                                         to ≥1 ticker with personality data
    confidence_class:            "descriptive"
    lineage:                     str (anchor to this masterplan)
  }

DESIGN CONSTRAINTS (R-SP19 + oracle contract)
---------------------------------------------
- confidence_class ALWAYS "descriptive" — no edge claim.
- Field names avoid banned substrings: forecast, predicted, target, expected_return.
- Fail-open at every level: missing aggregate ⇒ no field emitted on any complex.
- Never modifies the complex dict in-place before producing the result dict;
  callers append the result additively.
- This module does NOT own writing oracle_state.json — live.py owns that.

Join path
---------
oracle node (rotation_groups.json) → ticker (member_context.json themes) →
personality data (stock_personality.json per_ticker).

Coverage is partial (~35/83 oracle nodes have theme membership in member_context).
``member_coverage`` in each complex's personality_context reflects true coverage.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_LINEAGE = (
    "research/STOCK_PERSONALITY_MASTERPLAN_BY_FABLE.md R-SP19 — "
    "member-level stock personality roll-up; descriptive/display tier only."
)


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

    Returns
    -------
    dict with personality_context fields, or None if no coverage.
    """
    node_members: list[str] = list(complex_def.get("members") or [])
    if not node_members:
        return None

    # Collect tickers for this complex by joining through theme_ticker_map
    resolved_tickers: set[str] = set()
    for node in node_members:
        for ticker in theme_ticker_map.get(node, []):
            if ticker in per_ticker:
                resolved_tickers.add(ticker)

    n_nodes_total = len(node_members)
    n_nodes_with_data = sum(
        1 for node in node_members
        if any(t in per_ticker for t in theme_ticker_map.get(node, []))
    )
    member_coverage = round(n_nodes_with_data / n_nodes_total, 4) if n_nodes_total else 0.0

    if not resolved_tickers:
        # No coverage — return a coverage-zero block so the consumer can see the gap
        return {
            "dominant_member_archetypes": [],
            "dominant_chart_labels": [],
            "tinderbox_share": None,
            "event_override_share": None,
            "member_coverage": 0.0,
            "confidence_class": "descriptive",
            "lineage": _LINEAGE,
        }

    archetype_ctr: Counter = Counter()
    chart_ctr: Counter = Counter()
    n_tinderbox = 0
    n_event_override = 0
    n_covered = 0

    for ticker in resolved_tickers:
        rec = per_ticker.get(ticker)
        if not isinstance(rec, dict):
            continue
        n_covered += 1

        # archetype (single key, may be None)
        arch = rec.get("arch")
        if arch and isinstance(arch, str):
            archetype_ctr[arch] += 1

        # chart_personality (list of labels)
        for label in (rec.get("chart") or []):
            if label and isinstance(label, str):
                chart_ctr[label] += 1

        # ownership_habitat — tinderbox flag
        own = rec.get("own") or []
        if "short_interest_tinderbox" in own:
            n_tinderbox += 1

        # current_mode — event_override flag
        modes = rec.get("modes") or []
        if "event_override" in modes:
            n_event_override += 1

    tinderbox_share = round(n_tinderbox / n_covered, 4) if n_covered else None
    event_override_share = round(n_event_override / n_covered, 4) if n_covered else None

    return {
        "dominant_member_archetypes": _top3_shares(archetype_ctr),
        "dominant_chart_labels": _top3_shares(chart_ctr),
        "tinderbox_share": tinderbox_share,
        "event_override_share": event_override_share,
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
                cdef, per_ticker, theme_ticker_map
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
