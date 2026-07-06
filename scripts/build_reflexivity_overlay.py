"""Build reflexivity overlay artifact — W4, Signal Commons.

Runs AFTER build_site.py has written site/factor_betas.json and AFTER
build_stock_board_v2.py has written site/factordata/us_standouts_v2.json.

Writes:
  site/factordata/reflexivity_overlay.json  (display-only, is_context_only=true)
  data/reflexivity/n_eff_history.json       (git-committed, single-writer, RUL-P10)

After writing the overlay, re-renders site/us_stocks_v2.html so the card chips
and board banner that consume the overlay fields are present in the preview page
(resolves the born-dead-field finding: the overlay must have template consumers).

PLACEMENT (R-A ruling): BOARD-level, held-agnostic overlay only.
The candidate-vs-HELD read is chartered to the Mastermind repo.
CN/HK names are out of scope in v1 (R-E ruling).

N_EFF HISTORY (W-D wave): data/reflexivity/n_eff_history.json is git-committed
and single-writer (this script). Follows the dispersion/regime.json pattern
(bounded history array, _HISTORY_LEN=252, dedup-by-as_of, tail-trim).
A degraded/empty overlay run PRESERVES existing history — explicit guard.

PER-LANE N_EFF (invariant-e fix): the overlay emits board_concentration for the
union AND n_eff_by_lane keyed by lane name (entry_open / setting_up), matching
the population that build_stock_board_v2._concentration() computes per lane.
check_board_contradictions invariant (e) now compares each lane's
n_eff_by_lane[lane] against the same-lane board effective_bets, making the
populations identical and eliminating false-trip / false-pass hazards.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("build_reflexivity_overlay")

ROOT = Path(__file__).resolve().parents[1]
_FACTOR_BETAS   = ROOT / "site" / "factor_betas.json"
_STANDOUTS_V2   = ROOT / "site" / "factordata" / "us_standouts_v2.json"
_MEMBERSHIP     = ROOT / "data" / "baskets" / "membership.json"
_OUT            = ROOT / "site" / "factordata" / "reflexivity_overlay.json"
_EARNINGS       = ROOT / "data" / "earnings" / "earnings.parquet"
_HISTORY_OUT    = ROOT / "data" / "reflexivity" / "n_eff_history.json"

# Rolling history length — mirrors build_dispersion_regime._HISTORY_LEN.
_HISTORY_LEN = 252


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        log.warning("reflexivity: missing %s — degraded", path.name)
        return None
    try:
        return json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("reflexivity: cannot parse %s: %s", path.name, e)
        return None


def _candidate_tickers(standouts: dict) -> tuple[list[str], dict[str, str]]:
    """Extract unique candidate tickers + sector mapping from us_standouts_v2.

    Combines both lanes (entry_open + setting_up) — these are the names we build
    the duplicate-exposure read over.  Returns (tickers, sector_by_ticker).
    """
    seen: dict[str, str] = {}  # ticker → sector (first seen wins)
    lanes = (standouts or {}).get("lanes") or {}
    for lane_rows in lanes.values():
        if not isinstance(lane_rows, list):
            continue
        for row in lane_rows:
            t = (row.get("ticker") or "").upper()
            if not t:
                continue
            if t not in seen:
                seen[t] = row.get("sector") or ""
    tickers = list(seen.keys())
    return tickers, seen


def _lane_tickers(standouts: dict, lane_name: str) -> list[str]:
    """Extract tickers for a single named lane (entry_open or setting_up).

    Returns tickers in lane order, deduplicated, matching the population that
    build_stock_board_v2._concentration() receives for the same lane.
    """
    rows = ((standouts or {}).get("lanes") or {}).get(lane_name) or []
    seen: list[str] = []
    seen_set: set[str] = set()
    for row in rows:
        t = (row.get("ticker") or "").upper()
        if t and t not in seen_set:
            seen.append(t)
            seen_set.add(t)
    return seen


def _as_of(standouts: dict, factor_betas: dict) -> str:
    """Best as_of from input artifacts."""
    s = (standouts or {}).get("as_of") or ""
    f = (factor_betas or {}).get("as_of") or ""
    return s or f or datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ── N_eff history helpers (W-D wave) ─────────────────────────────────────────
# Mirrors the dispersion/regime.json pattern verbatim:
# bounded array, dedup-by-as_of, tail-trim, read-prior-then-append.
# SINGLE WRITER: this script only (RUL-P10).

def _load_history(out_path: Path) -> list[dict]:
    """Load the existing history list from n_eff_history.json (if it exists)."""
    if not out_path.exists():
        return []
    try:
        existing = json.loads(out_path.read_text())
        return existing.get("history", [])
    except Exception:  # noqa: BLE001
        return []


def _update_history(history: list[dict], today_entry: dict) -> list[dict]:
    """Append today's entry and keep the last _HISTORY_LEN days.

    Deduplicates by as_of — if today's as_of already exists, the new entry
    replaces it (last-write-wins; handles re-runs within the same day).
    """
    as_of = today_entry.get("as_of")
    pruned = [h for h in history if h.get("as_of") != as_of]
    pruned.append(today_entry)
    return pruned[-_HISTORY_LEN:]


def _write_n_eff_history(artifact: dict, history_path: Path) -> None:
    """Append the current n_eff snapshot to the rolling history file.

    Guard: if artifact is an empty overlay (n=0 and no by_ticker) we still
    PRESERVE prior history — we just skip appending a new entry. This prevents
    degraded runs from silently resetting the accrual store.
    """
    n = (artifact.get("board_concentration") or {}).get("n", 0)
    by_ticker = artifact.get("by_ticker") or {}
    if n == 0 and not by_ticker:
        # Degraded/empty run — preserve history, do not append a null entry.
        log.debug("n_eff_history: empty overlay, preserving prior history")
        return

    as_of = artifact.get("as_of") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    n_eff_by_lane = artifact.get("n_eff_by_lane") or {}
    same_thesis_groups = artifact.get("same_thesis_groups") or []

    today_entry: dict = {
        "as_of": as_of,
        "n_eff_by_lane": n_eff_by_lane,
        "same_thesis_group_count": len(same_thesis_groups),
    }

    history_path.parent.mkdir(parents=True, exist_ok=True)
    history = _load_history(history_path)
    history = _update_history(history, today_entry)

    out = {
        "schema": "reflexivity_n_eff_history.v1",
        "as_of": as_of,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": (
            "Rolling N_eff history for the reflexivity overlay. "
            "Single-writer: scripts/build_reflexivity_overlay.py (RUL-P10). "
            "Accrual substrate for Codex BOOK-1 'N_eff by regime' (~2027 verdict)."
        ),
        "history": history,
    }
    try:
        history_path.write_text(json.dumps(out, indent=2))
        log.info("n_eff_history written: %d entries → %s", len(history), history_path)
    except Exception as e:  # noqa: BLE001
        log.warning("n_eff_history write failed (non-fatal): %s", e)


def _load_earnings() -> "pd.DataFrame | None":
    """Load data/earnings/earnings.parquet — fail-open on any error."""
    if not _EARNINGS.exists():
        log.debug("reflexivity: earnings.parquet not found — earnings leg skipped")
        return None
    try:
        import pandas as pd  # noqa: PLC0415
        df = pd.read_parquet(_EARNINGS)
        # Normalise index to upper-case for robust lookup
        df.index = df.index.str.upper()
        return df
    except Exception as e:  # noqa: BLE001
        log.warning("reflexivity: earnings.parquet unreadable (%s) — earnings leg skipped", e)
        return None


def compute(site: Path | None = None) -> dict:
    """Build the reflexivity overlay artifact. Degrades gracefully on missing inputs.

    The artifact includes both:
      board_concentration  — union of both lanes (n, n_eff, basis)
      n_eff_by_lane        — per-lane n_eff matching build_stock_board_v2._concentration()
                             populations so invariant (e) in check_board_contradictions
                             compares identical candidate sets.
    """
    site = site or (ROOT / "site")
    factor_betas_path = site / "factor_betas.json"
    standouts_path    = site / "factordata" / "us_standouts_v2.json"
    membership_path   = ROOT / "data" / "baskets" / "membership.json"

    factor_betas = _load_json(factor_betas_path)
    standouts    = _load_json(standouts_path)
    membership   = _load_json(membership_path)

    if not standouts:
        log.warning("reflexivity: us_standouts_v2.json absent — emitting empty overlay")
        return _empty_overlay("us_standouts_v2.json absent")

    tickers, sector_by_ticker = _candidate_tickers(standouts)

    if not tickers:
        log.warning("reflexivity: no candidates in us_standouts_v2 — emitting empty overlay")
        return _empty_overlay("no candidates in us_standouts_v2")

    betas_index: dict[str, dict] = {}
    if factor_betas and isinstance(factor_betas.get("betas"), dict):
        betas_index = factor_betas["betas"]
    else:
        log.warning("reflexivity: factor_betas.json absent or malformed — membership-only similarity")

    from engine.reflexivity import (  # noqa: PLC0415
        build_groups_index, pairwise_similarity, n_eff_participation_ratio,
        compute as _compute,
    )
    as_of = _as_of(standouts, factor_betas or {})
    earnings = _load_earnings()
    artifact = _compute(
        tickers=tickers,
        sector_by_ticker=sector_by_ticker,
        betas_index=betas_index,
        membership_data=membership,
        as_of=as_of,
        earnings_store=earnings,
    )

    # ── per-lane n_eff (invariant-e population fix) ────────────────────────────
    # build_stock_board_v2._concentration() is called PER LANE with only that
    # lane's rows.  The union n_eff above covers a different, larger population,
    # so comparing them in invariant (e) is not apples-to-apples.  Emit a
    # separate n_eff_by_lane dict keyed by lane name so the check can compare
    # same-population numbers.
    n_eff_by_lane: dict[str, float | None] = {}
    for lane_name in ("entry_open", "setting_up"):
        lane_tkrs = _lane_tickers(standouts, lane_name)
        if len(lane_tkrs) >= 2:
            try:
                _groups = build_groups_index(membership, lane_tkrs, sector_by_ticker)
                _S, _, _ = pairwise_similarity(lane_tkrs, _groups, betas_index)
                n_eff_by_lane[lane_name] = round(float(n_eff_participation_ratio(_S)), 1)
            except Exception as _e:  # noqa: BLE001
                log.debug("reflexivity: per-lane n_eff failed for %s (%s)", lane_name, _e)
                n_eff_by_lane[lane_name] = None
        elif len(lane_tkrs) == 1:
            n_eff_by_lane[lane_name] = 1.0
        else:
            n_eff_by_lane[lane_name] = None

    artifact["n_eff_by_lane"] = n_eff_by_lane

    # Passport for source coverage
    def _rel(p: Path) -> str:
        try:
            return str(p.relative_to(ROOT))
        except ValueError:
            return str(p)

    artifact["source_passport"] = {
        "factor_betas": {
            "path": _rel(factor_betas_path),
            "found": factor_betas is not None,
            "as_of": (factor_betas or {}).get("as_of"),
        },
        "us_standouts_v2": {
            "path": _rel(standouts_path),
            "found": True,
            "as_of": standouts.get("as_of"),
        },
        "membership": {
            "path": "data/baskets/membership.json",
            "found": membership is not None,
        },
    }
    return artifact


def _empty_overlay(reason: str) -> dict:
    return {
        "schema": "reflexivity_overlay.v1",
        "is_context_only": True,
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": f"Empty overlay: {reason}",
        "factor_caveat": (
            "Per-name secondary betas (oil/usd/btc/gold/china) are OOS-unstable and excluded."
        ),
        "board_concentration": {"n": 0, "n_eff": 0.0, "basis": "none"},
        "n_eff_by_lane": {"entry_open": None, "setting_up": None},
        "by_ticker": {},
        "pair_basis": {},
        "verdicts": {},
    }


def main() -> int:
    """Entry point for nightly pipeline. Returns 0 always (non-fatal, like build_stock_board_v2)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        artifact = compute()
        out_path = _OUT
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Ensure all values are JSON-serializable (numpy scalars → python native)
        out_text = json.dumps(artifact, indent=2, default=_json_default)
        out_path.write_text(out_text)

        n = artifact.get("board_concentration", {}).get("n", 0)
        neff = artifact.get("board_concentration", {}).get("n_eff", 0.0)
        thesis_groups = artifact.get("same_thesis_groups", [])
        earnings_cov = artifact.get("earnings_coverage_frac", 0.0)
        log.info(
            "reflexivity overlay written: %d candidates ≈ %.1f independent bets, "
            "%d thesis groups, earnings coverage %.0f%% → %s",
            n, neff, len(thesis_groups), earnings_cov * 100, out_path,
        )

        # W-D: write N_eff history (git-committed, single-writer, RUL-P10).
        # Guard inside _write_n_eff_history: degraded/empty run preserves prior history.
        _write_n_eff_history(artifact, _HISTORY_OUT)

        # Re-render the v2 preview page so the reflexivity chips and board banner
        # (which consume the overlay) are present in the deployed preview.
        # build_stock_board_v2.render() runs before the overlay exists; this second
        # pass wires the overlay into the page (resolves born-dead-field finding).
        _rerender_v2_preview(artifact)
        return 0
    except Exception as e:  # noqa: BLE001
        log.exception("reflexivity overlay failed (non-fatal): %s", e)
        return 0   # never break the render


def _rerender_v2_preview(overlay: dict) -> None:
    """Re-render site/us_stocks_v2.html with overlay data after the overlay is written.

    Imports build_stock_board_v2 lazily so import errors are non-fatal.
    """
    try:
        from scripts.build_stock_board_v2 import compute as _bv2_compute, render as _bv2_render  # noqa: PLC0415
        site = ROOT / "site"
        standouts_path = site / "factordata" / "us_standouts_v2.json"
        if not standouts_path.exists():
            log.debug("reflexivity re-render: us_standouts_v2.json absent, skip")
            return
        payload = _bv2_compute(site=site)
        _bv2_render(payload, site=site, overlay=overlay)
        log.info("reflexivity re-render: us_stocks_v2.html updated with overlay data")
    except Exception as e:  # noqa: BLE001
        log.warning("reflexivity re-render failed (non-fatal): %s", e)


def _json_default(obj):
    """Fallback for JSON serialization of numpy scalars."""
    import numpy as np  # noqa: PLC0415
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


if __name__ == "__main__":
    raise SystemExit(main())
