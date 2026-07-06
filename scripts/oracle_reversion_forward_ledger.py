"""Oracle Reversion Forward Ledger — nightly single-writer (P0).

Evaluates all registry compounds that have a ``reversion`` block (gauntlet PASS)
on the latest panel date and appends new fires to per-compound JSONL ledgers
at ``data/oracle/reversion_forward/<compound_id>.jsonl``.

On each run the grading pass fills ``ret_exit``, ``mfe``, ``mae`` and sets
``matured=true`` for rows whose ``exit_date <= latest panel date``.  Rows whose
horizon has not yet closed carry nulls and ``matured=false``.

PIT law (frozen in ORACLE_REVERSION_PROMOTION_PREREG.md)
---------------------------------------------------------
- A row is graded only once ``exit_date <= today`` (latest panel date).
- ``exec_date`` = next panel session after ``fire_date``.
- ``exit_date`` = ``exec_date + 21 sessions`` (``exit_sessions`` from the
  reversion block; default 21 per the prereg).
- Regime stamped at ``fire_date`` (not exec_date).
- ``_per_entry_rows`` from ``scripts.oracle_reversion_screen`` is reused
  VERBATIM for grading so live grading == backtest grading.

Ledger schema (frozen)
----------------------
Per row (append-only, one file per compound):
  compound_id, node, tier, fire_date, exec_date, exit_date,
  regime, ret_exit, mfe, mae, matured

Idempotency
-----------
Re-running never duplicates rows.  The dedup key is
``(compound_id, node, fire_date)``.  Grading is a rewrite pass over the
existing ledger file — never a new row.

Usage
-----
  python -m scripts.oracle_reversion_forward_ledger --data-dir /path/to/data
  python -m scripts.oracle_reversion_forward_ledger --data-dir /path/to/data --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("oracle_reversion_forward_ledger")

# Frozen constants (per ORACLE_REVERSION_PROMOTION_PREREG.md)
_DEFAULT_EXIT_SESSIONS: int = 21   # 21-session time-exit = ~1 trading month
_DEFAULT_WINDOW: int = 25           # MFE/MAE window in sessions (matches backtest)
_REGISTRY_PATH_REL = Path("oracle") / "compounds" / "registry.jsonl"
_FORWARD_DIR_REL = Path("oracle") / "reversion_forward"


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------

def _load_reversion_compounds(data_dir: Path) -> list[dict]:
    """Return all registry compounds that have a reversion block (gauntlet PASS)."""
    registry_path = data_dir / _REGISTRY_PATH_REL
    if not registry_path.exists():
        log.warning("registry not found: %s", registry_path)
        return []
    compounds = []
    for line in registry_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            c = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if "reversion" in c and c["reversion"].get("gauntlet") == "PASS":
            compounds.append(c)
    return compounds


# ---------------------------------------------------------------------------
# Panel / episode loading (mirrors oracle_nightly's cache pattern)
# ---------------------------------------------------------------------------

def _load_panel(data_dir: Path, tier: str) -> pd.DataFrame | None:
    p = data_dir / "oracle" / f"panel_{tier}.parquet"
    if not p.exists():
        log.warning("panel not found: %s", p)
        return None
    return pd.read_parquet(p)


def _load_episodes(data_dir: Path, tier: str) -> pd.DataFrame | None:
    p = data_dir / "oracle" / f"episodes_{tier}.parquet"
    if not p.exists():
        log.warning("episodes not found: %s", p)
        return None
    return pd.read_parquet(p)


def _load_rotation_groups(data_dir: Path) -> dict:
    p = data_dir / "oracle" / "rotation_groups.json"
    if not p.exists():
        return {"complexes": []}
    return json.loads(p.read_text())


# ---------------------------------------------------------------------------
# Ledger I/O helpers
# ---------------------------------------------------------------------------

def _ledger_path(data_dir: Path, compound_id: str) -> Path:
    return data_dir / _FORWARD_DIR_REL / f"{compound_id}.jsonl"


def _load_existing_keys(ledger_path: Path) -> set[str]:
    """Load set of (compound_id, node, fire_date) dedup keys from existing ledger."""
    if not ledger_path.exists():
        return set()
    keys: set[str] = set()
    for line in ledger_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
            k = _fire_key(r.get("compound_id", ""), r.get("node", ""), r.get("fire_date", ""))
            keys.add(k)
        except Exception:  # noqa: BLE001
            pass
    return keys


def _load_ledger_rows(ledger_path: Path) -> list[dict]:
    if not ledger_path.exists():
        return []
    rows = []
    for line in ledger_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:  # noqa: BLE001
            pass
    return rows


def _fire_key(compound_id: str, node: str, fire_date: str) -> str:
    """Dedup key for a (compound, node, fire_date) triple."""
    return f"{compound_id}::{node}::{fire_date}"


def _row_as_json(row: dict) -> str:
    return json.dumps(row, separators=(",", ":"), default=str)


# ---------------------------------------------------------------------------
# Regime helper (mirrors oracle_reversion_screen._regime_at)
# ---------------------------------------------------------------------------

def _regime_at(node_panel_row: pd.Series) -> str:
    spy_above = node_panel_row.get("spy_above_200d", np.nan)
    vix_pct = node_panel_row.get("vix_pctile", np.nan)
    if not np.isnan(float(spy_above) if spy_above is not None else np.nan) and spy_above == 0:
        return "risk_off"
    vp = float(vix_pct) if vix_pct is not None else np.nan
    if not np.isnan(vp) and vp >= 0.70:
        return "risk_off"
    return "risk_on"


# ---------------------------------------------------------------------------
# Fire detection: which nodes fired on the latest panel date?
# ---------------------------------------------------------------------------

def _detect_latest_fires(
    compound: dict,
    panel: pd.DataFrame,
    episodes_df: pd.DataFrame,
    rotation_groups: dict,
    latest_date: pd.Timestamp,
) -> list[dict[str, Any]]:
    """Return a list of fire dicts (one per node that fired on latest_date).

    Each dict has: node, fire_date(str ISO), exec_date(str ISO), exit_date(str ISO),
    regime, ret_exit(None), mfe(None), mae(None), matured(False).
    """
    from engine.oracle.compounds import get_entry_dates, augment_panel_with_derived

    cid = compound.get("id", "?")
    reversion = compound.get("reversion", {})
    exit_sessions = int(reversion.get("exit", _DEFAULT_EXIT_SESSIONS))
    tier = compound.get("universe", {}).get("tier", "s")

    panel_aug = augment_panel_with_derived(panel.copy())

    try:
        entry_dates = get_entry_dates(compound, panel_aug, episodes_df, rotation_groups)
    except ValueError as e:
        log.warning("%s: rule error: %s", cid, e)
        return []

    if not entry_dates or "__blocked__" in entry_dates:
        return []

    all_panel_dates = panel_aug.index.get_level_values("date").unique().sort_values()
    fires: list[dict[str, Any]] = []

    for node, dates in entry_dates.items():
        if latest_date not in dates:
            continue

        # exec_date = next session after latest_date
        future = all_panel_dates[all_panel_dates > latest_date]
        if len(future) == 0:
            # Latest date IS the last date — exec not yet reached; still record fire
            exec_date = None
            exit_date = None
        else:
            exec_date = future[0]
            # exit_date = exec_date + exit_sessions sessions
            exec_pos = all_panel_dates.searchsorted(exec_date, side="left")
            exit_pos = exec_pos + exit_sessions
            exit_date = all_panel_dates[exit_pos] if exit_pos < len(all_panel_dates) else None

        # Regime at fire_date (NOT exec_date)
        try:
            node_panel_node = panel_aug.xs(node, level="node")
            if latest_date in node_panel_node.index:
                regime = _regime_at(node_panel_node.loc[latest_date])
            else:
                preceding = node_panel_node.index[node_panel_node.index <= latest_date]
                regime = _regime_at(node_panel_node.loc[preceding[-1]]) if len(preceding) else "unknown"
        except KeyError:
            regime = "unknown"

        fires.append({
            "compound_id": cid,
            "node": node,
            "tier": tier,
            "fire_date": latest_date.isoformat(),
            "exec_date": exec_date.isoformat() if exec_date is not None else None,
            "exit_date": exit_date.isoformat() if exit_date is not None else None,
            "regime": regime,
            "ret_exit": None,
            "mfe": None,
            "mae": None,
            "matured": False,
        })

    return fires


# ---------------------------------------------------------------------------
# Grading pass: fill ret_exit/mfe/mae for matured rows
# ---------------------------------------------------------------------------

def _grade_rows(
    rows: list[dict],
    compound: dict,
    panel: pd.DataFrame,
    latest_date: pd.Timestamp,
) -> list[dict]:
    """Grade unmatured rows whose exit_date <= latest_date.

    Uses _per_entry_rows from oracle_reversion_screen VERBATIM so live grading
    equals backtest grading (PIT law from PREREG.md).
    """
    from scripts.oracle_reversion_screen import _per_entry_rows
    from engine.oracle.compounds import augment_panel_with_derived

    cid = compound.get("id", "?")
    reversion = compound.get("reversion", {})
    exit_sessions = int(reversion.get("exit", _DEFAULT_EXIT_SESSIONS))
    window = int(reversion.get("window", _DEFAULT_WINDOW))
    exit_mode = str(reversion.get("exit_mode", "time"))

    panel_aug = augment_panel_with_derived(panel.copy())
    all_panel_dates = panel_aug.index.get_level_values("date").unique().sort_values()

    # Separate mature-candidates from already-graded
    to_grade: list[int] = []
    for i, row in enumerate(rows):
        if row.get("matured") is True:
            continue
        exit_date_str = row.get("exit_date")
        if exit_date_str is None:
            # exec_date or exit_date not yet known — try to fill them now
            fire_date = pd.Timestamp(row["fire_date"])
            future = all_panel_dates[all_panel_dates > fire_date]
            if len(future) == 0:
                continue
            exec_date = future[0]
            exec_pos = all_panel_dates.searchsorted(exec_date, side="left")
            exit_pos = exec_pos + exit_sessions
            if exit_pos >= len(all_panel_dates):
                continue
            exit_date = all_panel_dates[exit_pos]
            # Update row
            rows[i]["exec_date"] = exec_date.isoformat()
            rows[i]["exit_date"] = exit_date.isoformat()
            exit_date_str = exit_date.isoformat()

        exit_ts = pd.Timestamp(exit_date_str)
        if exit_ts > latest_date:
            # PIT law: not yet mature
            continue
        to_grade.append(i)

    if not to_grade:
        return rows

    # Build per-node entry_dates from the to-grade rows and call _per_entry_rows
    # Group by node for efficiency
    node_to_fire_dates: dict[str, list[pd.Timestamp]] = {}
    idx_map: dict[str, list[int]] = {}  # node -> row indices

    for i in to_grade:
        row = rows[i]
        node = row["node"]
        fire_date = pd.Timestamp(row["fire_date"])
        node_to_fire_dates.setdefault(node, []).append(fire_date)
        idx_map.setdefault(node, []).append(i)

    entry_dates_for_grade = {
        node: pd.DatetimeIndex(sorted(dates))
        for node, dates in node_to_fire_dates.items()
    }

    try:
        per_entry = _per_entry_rows(
            entry_dates_for_grade,
            panel_aug,
            window=window,
            exit_sessions=exit_sessions,
            exit_mode=exit_mode,  # type: ignore[arg-type]
        )
    except Exception as e:  # noqa: BLE001
        log.warning("%s: _per_entry_rows failed during grading: %s", cid, e)
        return rows

    # Index grading results by (node, fire_date)
    grade_lookup: dict[tuple[str, str], dict] = {}
    for g in per_entry:
        key = (g["node"], pd.Timestamp(g["trigger_date"]).isoformat())
        grade_lookup[key] = g

    for i in to_grade:
        row = rows[i]
        key = (row["node"], pd.Timestamp(row["fire_date"]).isoformat())
        g = grade_lookup.get(key)
        if g is None:
            # _per_entry_rows dropped this entry (exit not yet in data or immature)
            continue
        rows[i]["ret_exit"] = float(g["ret_exit"]) if g.get("ret_exit") is not None else None
        rows[i]["mfe"] = float(g["MFE"]) if g.get("MFE") is not None else None
        rows[i]["mae"] = float(g["MAE"]) if g.get("MAE") is not None else None
        rows[i]["matured"] = True
        log.debug("%s node=%s fire=%s graded ret=%.3f",
                  cid, row["node"], row["fire_date"], rows[i]["ret_exit"] or 0)

    return rows


# ---------------------------------------------------------------------------
# Per-compound write pass
# ---------------------------------------------------------------------------

def _run_compound(
    compound: dict,
    panel: pd.DataFrame,
    episodes_df: pd.DataFrame,
    rotation_groups: dict,
    data_dir: Path,
    dry_run: bool,
) -> dict[str, int]:
    """Fire detection + grading for a single compound. Returns counters."""
    cid = compound.get("id", "?")
    lpath = _ledger_path(data_dir, cid)
    existing_keys = _load_existing_keys(lpath)

    all_panel_dates = panel.index.get_level_values("date").unique().sort_values()
    if all_panel_dates.empty:
        log.debug("%s: empty panel, skip", cid)
        return {"fired": 0, "graded": 0}

    latest_date = all_panel_dates[-1]

    # --- Fire detection ---
    new_fires = _detect_latest_fires(
        compound, panel, episodes_df, rotation_groups, latest_date
    )
    # Dedup
    novel_fires = []
    for f in new_fires:
        k = _fire_key(f["compound_id"], f["node"], f["fire_date"])
        if k not in existing_keys:
            novel_fires.append(f)
            existing_keys.add(k)

    # --- Grading pass ---
    # Load all existing rows + new fires together so grading can see them
    existing_rows = _load_ledger_rows(lpath)
    all_rows = existing_rows + novel_fires

    if not all_rows:
        return {"fired": 0, "graded": 0}

    graded_before = sum(1 for r in all_rows if r.get("matured") is True)
    all_rows = _grade_rows(all_rows, compound, panel, latest_date)
    graded_after = sum(1 for r in all_rows if r.get("matured") is True)
    newly_graded = graded_after - graded_before

    if not dry_run and (novel_fires or newly_graded > 0):
        lpath.parent.mkdir(parents=True, exist_ok=True)
        lpath.write_text("\n".join(_row_as_json(r) for r in all_rows) + "\n")
        if novel_fires:
            log.info("%s: %d new fires on %s", cid, len(novel_fires), latest_date.isoformat())
        if newly_graded > 0:
            log.info("%s: %d rows graded this run", cid, newly_graded)

    return {"fired": len(novel_fires), "graded": newly_graded}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_reversion_forward_ledger(data_dir: Path, dry_run: bool = False) -> dict[str, Any]:
    """Run the reversion forward ledger for all gauntlet-PASS compounds.

    Returns a summary dict.
    """
    compounds = _load_reversion_compounds(data_dir)
    if not compounds:
        log.info("reversion_forward_ledger: no reversion compounds in registry")
        return {"n_compounds": 0, "total_fired": 0, "total_graded": 0}

    rotation_groups = _load_rotation_groups(data_dir)

    # Cache panels / episodes by tier
    panels: dict[str, pd.DataFrame] = {}
    episodes_cache: dict[str, pd.DataFrame] = {}

    def _get_panel(tier: str) -> pd.DataFrame | None:
        if tier not in panels:
            p = _load_panel(data_dir, tier)
            if p is not None:
                panels[tier] = p
        return panels.get(tier)

    def _get_episodes(tier: str) -> pd.DataFrame | None:
        if tier not in episodes_cache:
            e = _load_episodes(data_dir, tier)
            if e is not None:
                episodes_cache[tier] = e
        return episodes_cache.get(tier)

    total_fired = 0
    total_graded = 0
    n_skip = 0

    for compound in compounds:
        cid = compound.get("id", "?")
        tier = compound.get("universe", {}).get("tier", "s")
        panel = _get_panel(tier)
        eps = _get_episodes(tier)
        if panel is None or eps is None:
            log.debug("reversion_forward_ledger: missing panel/episodes for tier=%s — skip %s", tier, cid)
            n_skip += 1
            continue
        try:
            counts = _run_compound(compound, panel, eps, rotation_groups, data_dir, dry_run)
            total_fired += counts["fired"]
            total_graded += counts["graded"]
        except Exception as e:  # noqa: BLE001
            log.warning("reversion_forward_ledger: %s failed: %s", cid, e)
            n_skip += 1

    log.info(
        "reversion_forward_ledger: %d compounds, %d new fires, %d graded, %d skipped",
        len(compounds), total_fired, total_graded, n_skip,
    )
    return {
        "n_compounds": len(compounds),
        "total_fired": total_fired,
        "total_graded": total_graded,
        "n_skipped": n_skip,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Oracle reversion forward ledger (nightly single-writer)")
    p.add_argument("--data-dir", type=Path, default=None)
    p.add_argument("--dry-run", action="store_true",
                   help="Run all logic but write no files")
    args = p.parse_args()

    from lib import config as _cfg
    data_dir = args.data_dir or _cfg.data_dir()

    log.info("oracle_reversion_forward_ledger: data_dir=%s dry_run=%s", data_dir, args.dry_run)
    summary = run_reversion_forward_ledger(data_dir, dry_run=args.dry_run)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
