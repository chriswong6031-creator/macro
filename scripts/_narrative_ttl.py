"""W3.4 — Narrative TTL/staleness metadata loader.

Enriches the NARR map (produced by _narrative_epoch.resolve_narratives) with:
  - staleness_days: calendar days since as_of
  - stale_amber   : bool (age > ttl_days)
  - stale_red     : bool (age > 2 × ttl_days)
  - archetype_check_state: one of "pass"|"fail"|"missing"|"manual"|"none"
  - archetype_check_fired_on: ISO date string when the check first failed, or null
  - revision_note : str | null  — "revised {date}: {summary}" if prev_revision populated

Usage (from a builder):
    from scripts._narrative_ttl import enrich_narr_ttl
    narr = _load_narratives(root)
    narr = enrich_narr_ttl(narr, asof=date.today())

The returned map is a shallow copy: original entries are augmented with
``_ttl`` metadata sub-dicts; all curated content (now, legs…) is untouched.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger("narrative_ttl")

# ── archetype check evaluator (reuses W3.3 falsifier_tripwires) ──────────────

_FALSIFIERS_CACHE: dict[str, dict] | None = None


def _falsifier_by_id(fid: str) -> dict | None:
    """Load falsifiers.json and return entry for fid (cached)."""
    global _FALSIFIERS_CACHE  # noqa: PLW0603
    if _FALSIFIERS_CACHE is None:
        try:
            from lib import config
            fp = config.ROOT / "data" / "cycle_ontology" / "falsifiers.json"
            if fp.exists():
                _FALSIFIERS_CACHE = {e["id"]: e for e in json.loads(fp.read_text(encoding="utf-8"))}
            else:
                _FALSIFIERS_CACHE = {}
        except Exception as exc:  # noqa: BLE001
            log.warning("falsifiers.json unavailable: %s", exc)
            _FALSIFIERS_CACHE = {}
    return _FALSIFIERS_CACHE.get(fid)


def _eval_archetype_check(
    fid: str,
    asof: date,
) -> tuple[str, str | None]:
    """Evaluate a falsifier DSL against collected data.

    Returns (state, fired_on):
        state    : "pass" | "fail" | "missing" | "manual" | "none"
        fired_on : ISO date string if state=="fail", else None
    """
    entry = _falsifier_by_id(fid)
    if entry is None:
        return "none", None

    coverage = entry.get("coverage", "none")
    dsl = entry.get("dsl")

    if coverage == "none" or dsl is None:
        return "manual", None

    try:
        import pandas as pd
        from engine.falsifier_tripwires import _eval_expr  # type: ignore[import]
        ts = pd.Timestamp(asof.isoformat())
        result, legs = _eval_expr(dsl, ts)
        if result is None:
            return "missing", None
        if result:
            # DSL is TRUE → condition met → falsifier fires → mechanism check FAIL
            return "fail", asof.isoformat()
        return "pass", None
    except Exception as exc:  # noqa: BLE001
        log.debug("archetype_check eval failed for %s: %s", fid, exc)
        return "missing", None


# ── state cache (persisted in tripwire_state.json under archetype_checks key) ──

_STATE_KEY = "archetype_checks"


def _load_check_state(root: Path) -> dict[str, Any]:
    """Load persisted archetype_check states (sub-key of tripwire_state.json)."""
    p = root / "data" / "cycle_ontology" / "tripwire_state.json"
    if not p.exists():
        return {}
    try:
        s = json.loads(p.read_text(encoding="utf-8"))
        return s.get(_STATE_KEY, {})
    except Exception:  # noqa: BLE001
        return {}


def _save_check_state(root: Path, checks: dict[str, Any]) -> None:
    """Persist archetype_check states (merges into tripwire_state.json)."""
    p = root / "data" / "cycle_ontology" / "tripwire_state.json"
    try:
        if p.exists():
            state = json.loads(p.read_text(encoding="utf-8"))
        else:
            state = {}
        state[_STATE_KEY] = checks
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(p)
    except Exception as exc:  # noqa: BLE001
        log.warning("could not persist archetype_check state: %s", exc)


# ── main enrichment ───────────────────────────────────────────────────────────

def enrich_narr_ttl(
    narr_map: dict[str, Any],
    *,
    asof: date | None = None,
    persist_state: bool = True,
) -> dict[str, Any]:
    """Enrich every NARR entry with ``_ttl`` metadata.

    Parameters
    ----------
    narr_map      : the flattened {series_id: rec} map from resolve_narratives
    asof          : reference date (defaults to today)
    persist_state : if True, latch archetype_check fired_on into tripwire_state.json

    Returns the same dict with ``_ttl`` sub-dicts added (no curated content touched).
    """
    if asof is None:
        asof = date.today()

    root: Path | None = None
    if persist_state:
        try:
            from lib import config
            root = config.ROOT
        except Exception:  # noqa: BLE001
            persist_state = False

    check_state: dict[str, Any] = {}
    if persist_state and root:
        check_state = _load_check_state(root)

    state_changed = False

    # Keys that are file-level metadata, not narrative entries.  The flattened NARR
    # map from _flatten_doc contains sectors + basket values only, but defensive guard
    # in case a caller passes an unflattened doc or a map with metadata keys.
    _META_KEYS = frozenset({"_rekey_stats", "_ttl", "note", "version", "epoch",
                             "prev_epoch", "rekeyed_from", "detector_version"})

    for sid, entry in narr_map.items():
        if sid in _META_KEYS or not isinstance(entry, dict):
            continue
        # A narrative entry has a 'now' or 'legs' key; skip metadata dicts that lack both.
        if "now" not in entry and "legs" not in entry:
            continue

        # ── staleness ─────────────────────────────────────────────────────────
        as_of_str = entry.get("as_of")
        ttl_days = int(entry.get("ttl_days") or 90)
        staleness_days: int | None = None
        stale_amber = False
        stale_red = False

        if as_of_str:
            try:
                ao = date.fromisoformat(as_of_str)
                staleness_days = (asof - ao).days
                stale_amber = staleness_days > ttl_days
                stale_red = staleness_days > 2 * ttl_days
            except ValueError:
                pass

        # ── archetype check ───────────────────────────────────────────────────
        fid = entry.get("archetype_check")
        arch_state = "none"
        arch_fired_on: str | None = None

        if fid:
            # check if we have a latched fired_on in state
            prev = check_state.get(f"{sid}:{fid}", {})
            prev_fired_on = prev.get("fired_on")

            live_state, live_fired = _eval_archetype_check(fid, asof)

            if live_state == "fail":
                # use earliest known fired date (latch)
                arch_fired_on = prev_fired_on or live_fired
                arch_state = "fail"
                if not prev_fired_on:
                    check_state[f"{sid}:{fid}"] = {"fired_on": arch_fired_on}
                    state_changed = True
            elif live_state == "pass":
                arch_state = "pass"
                # clear latch if condition recovered
                if prev_fired_on:
                    check_state.pop(f"{sid}:{fid}", None)
                    state_changed = True
            else:
                # missing / manual — keep previous latch if any
                arch_state = live_state
                if prev_fired_on:
                    arch_fired_on = prev_fired_on
                    arch_state = "fail"  # still in fail, data just missing now

        # ── revision note ─────────────────────────────────────────────────────
        revision_note: str | None = None
        prev_rev = entry.get("prev_revision")
        if isinstance(prev_rev, dict):
            rev_date = prev_rev.get("as_of") or prev_rev.get("date", "")
            rev_summary = prev_rev.get("summary_of_change") or prev_rev.get("summary", "")
            if rev_date and rev_summary:
                revision_note = f"revised {rev_date}: {rev_summary}"
            elif rev_date:
                revision_note = f"revised {rev_date}"

        # ── attach metadata ───────────────────────────────────────────────────
        entry["_ttl"] = {
            "as_of":              as_of_str,
            "ttl_days":           ttl_days,
            "staleness_days":     staleness_days,
            "stale_amber":        stale_amber,
            "stale_red":          stale_red,
            "archetype_check_id": fid,
            "arch_state":         arch_state,
            "arch_fired_on":      arch_fired_on,
            "revision_note":      revision_note,
        }

    if persist_state and root and state_changed:
        _save_check_state(root, check_state)

    return narr_map
