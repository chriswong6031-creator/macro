"""engine/conviction_delta.py — Per-ticker Conviction Delta (Codex docket B4).

Deterministic "what changed today" for the US standout board.  Compares the
previously committed us_standouts.json with today's computed rows and emits a
compact ``delta`` list showing WHICH dossier verdict and WHICH reason-codes changed.

STRICT composition rules (matching stock_dossier.py):
  - No scoring, ranking, sizing, or gating arithmetic.
  - No LLM calls; everything is deterministic from already-computed dossier keys.
  - No advice verbs ("buy", "sell", "wait", "avoid") in emitted strings.
  - Displayed strings are descriptive only (verb labels come from already-computed dossier).

Delta schema (one entry per changed ticker, capped at MAX_DELTA entries):
    {
      "ticker":         str,
      "prev_verb":      str | None,   # prior dossier action.verb (None if not on board)
      "cur_verb":       str | None,   # current dossier action.verb (None if not on board)
      "reasons_added":  [str, ...],   # no_buy_reasons codes that appeared today
      "reasons_removed":[str, ...],   # no_buy_reasons codes that disappeared today
      "entered_board":  bool,         # True when ticker not in prev artifact at all
      "left_board":     bool,         # True when ticker absent from cur build
    }

Top-level delta block written to us_standouts.json:
    {
      "prev_as_of": str | None,
      "cur_as_of":  str,
      "entries":    [...]             # sorted, capped list of delta entries
    }

Idempotence: if prev_as_of == cur_as_of (same-day re-render), the existing
delta block is carried forward unchanged.  This is handled in build_stock_library.py
at call time — this module always diffs whatever it is given.

Sort order (deterministic):
  1. Verb upgrades (prev_verb → cur_verb and the change is toward a stronger verb)
  2. Verb downgrades (verb changed but not an upgrade)
  3. Reason-only changes (verb unchanged, reasons changed)
  Within each group: alphabetical by ticker.

Verb strength ordering (for upgrade/downgrade classification):
  BUY > TRIM ONLY > WATCH > WAIT   (strings matched case-insensitively)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

MAX_DELTA = 30  # cap on entries (page-weight budget)

# Verb strength order: higher index = stronger.  TRIM ONLY sits between WAIT and WATCH.
_VERB_STRENGTH: dict[str, int] = {
    "wait":      0,
    "trim only": 1,
    "trim":      1,
    "watch":     2,
    "buy":       3,
}


def _verb_strength(verb: str | None) -> int:
    """Return numeric strength of a verb string (case-insensitive). Unknown = 0."""
    if verb is None:
        return -1  # absent = weaker than any verb
    return _VERB_STRENGTH.get(verb.lower().strip(), 0)


def _extract_row_state(row: dict) -> tuple[str | None, frozenset[str]]:
    """Extract (verb, no_buy_reasons_set) from a board row.

    Returns (None, frozenset()) when the dossier key is absent (pre-dossier artifact).
    """
    dos = row.get("dossier")
    if not isinstance(dos, dict):
        return None, frozenset()
    verb = (dos.get("action") or {}).get("verb")
    reasons = frozenset(dos.get("no_buy_reasons") or [])
    return verb, reasons


def _ticker_index(rows: list[dict]) -> dict[str, dict]:
    """Build {ticker: row} index from a list of board rows."""
    idx: dict[str, dict] = {}
    for r in rows:
        t = r.get("ticker")
        if t:
            idx[t] = r
    return idx


def _all_rows(standouts: dict) -> list[dict]:
    """Flatten buy + watch + laggards from a standouts document."""
    out: list[dict] = []
    for bucket in ("buy", "watch", "laggards"):
        bucket_rows = standouts.get(bucket)
        if isinstance(bucket_rows, list):
            out.extend(bucket_rows)
    return out


def _sort_key(entry: dict) -> tuple[int, str]:
    """Deterministic sort key: (group_rank, ticker).

    group_rank:
      0 = verb upgrade (cur stronger than prev)
      1 = verb downgrade (cur weaker than prev)
      2 = reason-only change (verb unchanged or absent)
    """
    ticker = entry.get("ticker") or ""
    prev_s = _verb_strength(entry.get("prev_verb"))
    cur_s  = _verb_strength(entry.get("cur_verb"))
    if entry.get("entered_board") or entry.get("left_board"):
        # Board enter/leave treated as a verb change
        if entry.get("entered_board"):
            group = 0  # entering is an upgrade (nothing → something)
        else:
            group = 1  # leaving is a downgrade
    elif prev_s < cur_s:
        group = 0  # verb upgrade
    elif prev_s > cur_s:
        group = 1  # verb downgrade
    else:
        group = 2  # reason-only
    return group, ticker


def diff_standouts(
    prev: dict | None,
    cur: dict,
) -> dict:
    """Compute the conviction delta between two us_standouts documents.

    Parameters
    ----------
    prev : dict | None
        The previously committed us_standouts document.  None or empty → all
        entered_board=True entries (but we emit nothing — first-run produces an
        empty delta because there is no baseline).
    cur : dict
        Today's newly computed us_standouts document.

    Returns
    -------
    dict
        {prev_as_of, cur_as_of, entries: [...]}
    """
    prev_as_of: str | None = (prev or {}).get("as_of") if prev else None
    cur_as_of: str | None = cur.get("as_of")

    # --- Fail-soft when prior artifact has no dossier keys at all -----------------
    # If prev exists but none of its rows have a "dossier" key, we cannot produce
    # meaningful deltas — return an empty entries list.
    prev_rows = _all_rows(prev) if prev else []
    cur_rows  = _all_rows(cur)

    # Check whether any prev row has a dossier
    prev_has_dossiers = any("dossier" in r for r in prev_rows)

    if not prev or not prev_rows or not prev_has_dossiers:
        # No baseline — return empty delta (real deltas start after two nightly renders)
        return {
            "prev_as_of": prev_as_of,
            "cur_as_of":  cur_as_of,
            "entries":    [],
        }

    # --- Build indexes -----------------------------------------------------------
    prev_idx = _ticker_index(prev_rows)
    cur_idx  = _ticker_index(cur_rows)

    prev_tickers = set(prev_idx.keys())
    cur_tickers  = set(cur_idx.keys())

    entries: list[dict] = []

    # --- Tickers present in both -------------------------------------------------
    for ticker in sorted(prev_tickers & cur_tickers):
        prev_verb, prev_reasons = _extract_row_state(prev_idx[ticker])
        cur_verb,  cur_reasons  = _extract_row_state(cur_idx[ticker])

        verb_changed    = prev_verb != cur_verb
        reasons_added   = sorted(cur_reasons - prev_reasons)
        reasons_removed = sorted(prev_reasons - cur_reasons)

        if not verb_changed and not reasons_added and not reasons_removed:
            continue  # no change for this ticker

        entries.append({
            "ticker":          ticker,
            "prev_verb":       prev_verb,
            "cur_verb":        cur_verb,
            "reasons_added":   reasons_added,
            "reasons_removed": reasons_removed,
            "entered_board":   False,
            "left_board":      False,
        })

    # --- Tickers that left the board (in prev, not in cur) -----------------------
    for ticker in sorted(prev_tickers - cur_tickers):
        prev_verb, prev_reasons = _extract_row_state(prev_idx[ticker])
        # Only emit if there was a dossier on the prev row
        if prev_verb is not None or prev_reasons:
            entries.append({
                "ticker":          ticker,
                "prev_verb":       prev_verb,
                "cur_verb":        None,
                "reasons_added":   [],
                "reasons_removed": sorted(prev_reasons),
                "entered_board":   False,
                "left_board":      True,
            })

    # --- Tickers that entered the board (in cur, not in prev) --------------------
    for ticker in sorted(cur_tickers - prev_tickers):
        cur_verb, cur_reasons = _extract_row_state(cur_idx[ticker])
        if cur_verb is not None or cur_reasons:
            entries.append({
                "ticker":          ticker,
                "prev_verb":       None,
                "cur_verb":        cur_verb,
                "reasons_added":   sorted(cur_reasons),
                "reasons_removed": [],
                "entered_board":   True,
                "left_board":      False,
            })

    # --- Sort and cap ------------------------------------------------------------
    entries.sort(key=_sort_key)
    entries = entries[:MAX_DELTA]

    return {
        "prev_as_of": prev_as_of,
        "cur_as_of":  cur_as_of,
        "entries":    entries,
    }


def load_prev_standouts(path: Path) -> dict | None:
    """Load the previously committed us_standouts.json.

    Returns None if the file does not exist or cannot be parsed.
    Never raises.
    """
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        log.debug("conviction_delta: could not load prev standouts (%s): %s", path, exc)
        return None
