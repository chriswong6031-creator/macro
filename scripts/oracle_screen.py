"""Oracle Research Factory — Tier-1 Screen Runner (W-B1).

Evaluates compounds against the historical panels, computes per-horizon
effect sizes and era-splits, appends trial_ledger rows, and flips compound
status exploratory→screened.

Usage
-----
  python scripts/oracle_screen.py --compound A1
  python scripts/oracle_screen.py --all-pending
  python scripts/oracle_screen.py --all-pending --data-dir /path/to/data

Output
------
  data/oracle/compounds/trial_ledger.jsonl   — append-only; keep-first by
                                               (compound_id, screener, params_hash)
  data/oracle/compounds/registry.jsonl       — status flipped exploratory→screened

EXPLORATORY DISCLAIMER
---------------------
Output rows carry "screened_by": "tier1_screen" and NO claim language.
Effect sizes here are EXPLORATORY — every row logged increments the search
width (Harvey-Liu-Zhu factor-zoo accounting).  Promotion requires the
separately-gated oracle_gauntlet runs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("oracle_screen")

# Era boundaries (1999-2014 / 2015-19 / 2020-22 / 2023-26)
_ERA_CUTS = [
    ("1999-2014", "1999-01-01", "2014-12-31"),
    ("2015-2019", "2015-01-01", "2019-12-31"),
    ("2020-2022", "2020-01-01", "2022-12-31"),
    ("2023-2026", "2023-01-01", "2099-12-31"),
]

_SCREENER_ID = "tier1_screen_v1"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_panel(data_dir: Path, tier: str) -> pd.DataFrame:
    p = data_dir / "oracle" / f"panel_{tier}.parquet"
    if not p.exists():
        raise FileNotFoundError(f"Panel not found: {p}")
    return pd.read_parquet(p)


def _load_episodes(data_dir: Path, tier: str) -> pd.DataFrame:
    p = data_dir / "oracle" / f"episodes_{tier}.parquet"
    if not p.exists():
        raise FileNotFoundError(f"Episodes not found: {p}")
    return pd.read_parquet(p)


def _load_spy(data_dir: Path) -> pd.Series | None:
    p = data_dir / "yahoo" / "SPY.parquet"
    if not p.exists():
        return None
    return pd.read_parquet(p)["close"].rename("spy")


def _load_rotation_groups(data_dir: Path) -> dict:
    p = data_dir / "oracle" / "rotation_groups.json"
    if not p.exists():
        return {"complexes": []}
    return json.loads(p.read_text())


# ---------------------------------------------------------------------------
# Effect computation
# ---------------------------------------------------------------------------

def _compute_forward_returns(
    entry_dates: dict[str, pd.DatetimeIndex],
    panel: pd.DataFrame,
    spy: pd.Series | None,
    horizons: list[int],
    tier: str,
) -> pd.DataFrame:
    """Compute forward excess returns for each entry across all horizons.

    Returns DataFrame with columns:
      node, entry_date, entry_exec_date, horizon_d,
      node_ret_{h}d, spy_ret_{h}d, excess_{h}d, era
    One row per (node, entry, horizon).

    Entry executes at NEXT close after the trigger date.
    Excess = node_ret − SPY_ret (tier s: vs SPY; tier m: vs cross-node median).
    """
    rows = []

    for node, dates in entry_dates.items():
        try:
            node_panel = panel.xs(node, level="node")
        except KeyError:
            continue

        # Get node level series (cumulative product of 1+ret)
        if "ret" not in node_panel.columns:
            continue

        ret_series = node_panel["ret"].sort_index()
        price_level = (1 + ret_series.fillna(0)).cumprod()
        price_level.name = "level"

        for entry_t in dates:
            # Entry executes at next available date after trigger
            future_dates = ret_series.index[ret_series.index > entry_t]
            if len(future_dates) == 0:
                continue
            exec_date = future_dates[0]

            # Era classification (use entry_t, not exec_date)
            era = _get_era(entry_t)

            for h in horizons:
                # Forward close: exec_date + h trading days
                exec_pos = ret_series.index.searchsorted(exec_date)
                exit_pos = exec_pos + h
                if exit_pos >= len(ret_series.index):
                    continue  # outcome window not mature — skip
                exit_date = ret_series.index[exit_pos]

                # Node return: compounded from exec_date close to exit_date close
                exec_price = price_level.get(exec_date, np.nan)
                exit_price = price_level.get(exit_date, np.nan)
                if np.isnan(exec_price) or np.isnan(exit_price) or exec_price == 0:
                    continue
                node_ret = exit_price / exec_price - 1

                # Benchmark return
                bench_ret = np.nan
                if tier == "s" and spy is not None:
                    spy_aligned = spy.reindex(ret_series.index)
                    spy_level = (1 + spy_aligned.pct_change(fill_method=None).fillna(0)).cumprod()
                    spy_exec = spy_level.get(exec_date, np.nan)
                    spy_exit = spy_level.get(exit_date, np.nan)
                    if not (np.isnan(spy_exec) or np.isnan(spy_exit) or spy_exec == 0):
                        bench_ret = spy_exit / spy_exec - 1
                else:
                    # Tier m: use cross-node median from rs column (already computed)
                    # Approximation: use the rs column's h-day sum as excess directly
                    rs_window = node_panel.loc[exec_date:exit_date, "rs"] if "rs" in node_panel.columns else pd.Series(dtype=float)
                    bench_ret = 0.0  # rs is already excess; we handle below

                excess = node_ret - bench_ret if not np.isnan(bench_ret) else np.nan

                # For tier m, recompute using rs as the return series
                if tier == "m":
                    if "rs" in node_panel.columns:
                        rs_s = node_panel["rs"].sort_index()
                        rs_level = (1 + rs_s.fillna(0)).cumprod()
                        rs_exec = rs_level.get(exec_date, np.nan)
                        rs_exit = rs_level.get(exit_date, np.nan)
                        if not (np.isnan(rs_exec) or np.isnan(rs_exit) or rs_exec == 0):
                            excess = rs_exit / rs_exec - 1
                        else:
                            excess = np.nan
                    else:
                        excess = np.nan

                rows.append({
                    "node": node,
                    "entry_date": entry_t,
                    "entry_exec_date": exec_date,
                    "horizon_d": h,
                    "node_ret": node_ret,
                    "bench_ret": bench_ret,
                    "excess": excess,
                    "era": era,
                })

    if not rows:
        return pd.DataFrame(columns=["node", "entry_date", "entry_exec_date",
                                      "horizon_d", "node_ret", "bench_ret", "excess", "era"])
    return pd.DataFrame(rows)


def _get_era(date: pd.Timestamp) -> str:
    for era_name, start, end in _ERA_CUTS:
        if pd.Timestamp(start) <= date <= pd.Timestamp(end):
            return era_name
    return "unknown"


def _compute_hit_rate(excess: pd.Series) -> float:
    """Fraction of entries where excess > 0."""
    valid = excess.dropna()
    if len(valid) == 0:
        return np.nan
    return float((valid > 0).mean())


def _era_direction(excess: pd.Series, era_col: pd.Series) -> dict[str, str]:
    """Per-era direction: 'pos' / 'neg' / 'mixed' / 'insufficient'."""
    out: dict[str, str] = {}
    for era_name, _, _ in _ERA_CUTS:
        mask = era_col == era_name
        sub = excess[mask].dropna()
        if len(sub) < 5:
            out[era_name] = "insufficient"
        elif sub.mean() > 0.002:
            out[era_name] = "pos"
        elif sub.mean() < -0.002:
            out[era_name] = "neg"
        else:
            out[era_name] = "mixed"
    return out


def _era_consistent_count(era_directions: dict[str, str], target_dir: str) -> int:
    """How many eras are consistent with target direction (pos or neg)."""
    return sum(1 for v in era_directions.values() if v == target_dir)


# ---------------------------------------------------------------------------
# Ledger management
# ---------------------------------------------------------------------------

def _params_hash(compound_id: str, screener: str, panel_tier: str, horizons: list[int]) -> str:
    payload = f"{compound_id}|{screener}|{panel_tier}|{sorted(horizons)}"
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def _load_trial_ledger(ledger_path: Path) -> list[dict]:
    if not ledger_path.exists():
        return []
    rows = []
    for line in ledger_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def _ledger_key(row: dict) -> tuple:
    return (row.get("compound_id"), row.get("screener"), row.get("params_hash"))


def _append_ledger_keep_first(ledger_path: Path, new_row: dict) -> bool:
    """Append row to trial_ledger.jsonl.  Keep-first: skip if key already exists.
    Returns True if appended, False if skipped (already exists).
    """
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_trial_ledger(ledger_path)
    existing_keys = {_ledger_key(r) for r in existing}
    key = _ledger_key(new_row)
    if key in existing_keys:
        log.info("trial_ledger: keep-first skip (key already exists): %s", key)
        return False
    with open(ledger_path, "a") as fh:
        fh.write(json.dumps(new_row, separators=(",", ":"), default=str) + "\n")
    return True


# ---------------------------------------------------------------------------
# Main screen function
# ---------------------------------------------------------------------------

def screen_compound(
    compound: dict,
    data_dir: Path,
    dry_run: bool = False,
    compounds_dir: Path | None = None,
) -> dict | None:
    """Screen one compound.  Returns the ledger row dict, or None on error.

    Appends to trial_ledger.jsonl and updates registry.jsonl status.

    compounds_dir: override path to the registry/ledger dir (default: data_dir/oracle/compounds)
    """
    from engine.oracle.compounds import (
        get_entry_dates, augment_panel_with_derived, update_compound_status,
        STATUS_SCREENED, STATUS_BLOCKED,
    )

    compound_id = compound.get("id", "?")
    t0 = time.time()
    log.info("Screening compound %s — %s", compound_id, compound.get("name"))

    universe = compound.get("universe", {})
    tier = universe.get("tier", "s")
    horizons = compound.get("horizons", [21, 63])

    # Resolve compounds directory (registry + ledger)
    _compounds_dir = compounds_dir or (data_dir / "oracle" / "compounds")

    # Load data
    try:
        panel = _load_panel(data_dir, tier)
        episodes = _load_episodes(data_dir, tier)
    except FileNotFoundError as e:
        log.error("screen_compound %s: data load failed: %s", compound_id, e)
        return None

    spy = _load_spy(data_dir) if tier == "s" else None
    rotation_groups = _load_rotation_groups(data_dir)

    # Augment panel with derived columns (D1 tlt_vol_*, etc.)
    panel = augment_panel_with_derived(panel)

    # Evaluate rule
    try:
        entry_dates = get_entry_dates(compound, panel, episodes, rotation_groups)
    except ValueError as e:
        log.error("screen_compound %s: rule validation error: %s", compound_id, e)
        return None

    # Check for missing column block
    if "__blocked__" in entry_dates:
        missing = entry_dates["__blocked__"]
        log.warning("Compound %s BLOCKED — missing columns: %s", compound_id, missing)
        if not dry_run:
            update_compound_status(
                _compounds_dir, compound_id, STATUS_BLOCKED,
                blocked_missing_columns=sorted(missing),
            )
        return {"compound_id": compound_id, "status": STATUS_BLOCKED,
                "blocked_missing_columns": sorted(missing)}

    total_entries = sum(len(v) for v in entry_dates.values())
    log.info("Compound %s: %d total entries across %d nodes",
             compound_id, total_entries, len(entry_dates))

    if total_entries == 0:
        log.warning("Compound %s: zero entries — no effect to compute", compound_id)
        ledger_row = _build_ledger_row(
            compound_id=compound_id,
            tier=tier,
            horizons=horizons,
            n=0,
            effects={},
            hits={},
            era_directions={},
            elapsed=time.time() - t0,
        )
    else:
        # Compute forward returns
        fwd = _compute_forward_returns(entry_dates, panel, spy, horizons, tier)

        effects: dict[str, float] = {}
        hits: dict[str, float] = {}
        era_dirs: dict[str, dict[str, str]] = {}

        for h in horizons:
            sub = fwd[fwd["horizon_d"] == h]["excess"].dropna()
            effects[f"effect_{h}d"] = float(sub.mean()) if len(sub) > 0 else np.nan
            hits[f"hit_{h}d"] = _compute_hit_rate(fwd[fwd["horizon_d"] == h]["excess"])
            era_dirs[f"era_direction_{h}d"] = _era_direction(
                fwd[fwd["horizon_d"] == h]["excess"],
                fwd[fwd["horizon_d"] == h]["era"],
            )

        n = len(fwd[fwd["horizon_d"] == horizons[0]]) if fwd.shape[0] > 0 else 0

        ledger_row = _build_ledger_row(
            compound_id=compound_id,
            tier=tier,
            horizons=horizons,
            n=n,
            effects=effects,
            hits=hits,
            era_directions=era_dirs,
            elapsed=time.time() - t0,
        )

    # Write ledger + update status
    if not dry_run:
        ledger_path = _compounds_dir / "trial_ledger.jsonl"
        appended = _append_ledger_keep_first(ledger_path, ledger_row)
        if appended:
            log.info("trial_ledger: appended row for %s", compound_id)
        # Flip status exploratory → screened
        current_status = compound.get("status", STATUS_SCREENED)
        if current_status == "exploratory":
            update_compound_status(_compounds_dir, compound_id, STATUS_SCREENED)
            log.info("Compound %s status: exploratory → screened", compound_id)

    log.info("Compound %s screen done in %.1fs — n=%d effect63d=%s hit63d=%s",
             compound_id, time.time() - t0,
             ledger_row.get("n", 0),
             ledger_row.get("effect_63d"),
             ledger_row.get("hit_63d"))

    return ledger_row


def _build_ledger_row(
    *,
    compound_id: str,
    tier: str,
    horizons: list[int],
    n: int,
    effects: dict[str, float],
    hits: dict[str, float],
    era_directions: dict[str, dict[str, str]],
    elapsed: float,
) -> dict:
    row: dict = {
        "compound_id": compound_id,
        "screener": _SCREENER_ID,
        "params_hash": _params_hash(compound_id, _SCREENER_ID, tier, horizons),
        "screened_at": datetime.now(timezone.utc).isoformat(),
        "tier": tier,
        "horizons": horizons,
        "n": n,
        "elapsed_s": round(elapsed, 2),
        "screened_by": "tier1_screen",
        "disclaimer": "EXPLORATORY — no claim language; counts toward search width",
    }
    row.update(effects)
    row.update(hits)
    row.update(era_directions)

    # Derived: era-consistent counts for the primary horizon (63d)
    if "era_direction_63d" in era_directions:
        ed63 = era_directions["era_direction_63d"]
        pos_count = _era_consistent_count(ed63, "pos")
        neg_count = _era_consistent_count(ed63, "neg")
        dominant = "pos" if pos_count > neg_count else "neg"
        row["era_consistent_63d"] = max(pos_count, neg_count)
        row["era_dominant_direction_63d"] = dominant

    return row


def _era_consistent_count(era_dirs: dict[str, str], direction: str) -> int:
    return sum(1 for v in era_dirs.values() if v == direction)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Oracle Tier-1 Screen Runner")
    p.add_argument("--compound", type=str, default=None, help="Compound id to screen")
    p.add_argument("--all-pending", action="store_true",
                   help="Screen all compounds with status 'exploratory'")
    p.add_argument("--data-dir", type=Path, default=None)
    p.add_argument("--compounds-dir", type=Path, default=None,
                   help="Override path to compounds registry/ledger dir "
                        "(default: <data-dir>/oracle/compounds)")
    p.add_argument("--dry-run", action="store_true", help="Compute but write no files")
    args = p.parse_args()

    from lib import config as _cfg
    data_dir = args.data_dir or _cfg.data_dir()

    from engine.oracle.compounds import load_registry
    compounds_dir = args.compounds_dir or (data_dir / "oracle" / "compounds")
    registry = load_registry(compounds_dir)

    if args.compound:
        target = [c for c in registry if c["id"] == args.compound]
        if not target:
            log.error("Compound '%s' not found in registry", args.compound)
            return 1
    elif args.all_pending:
        target = [c for c in registry if c.get("status") == "exploratory"]
        log.info("all-pending: found %d exploratory compounds", len(target))
    else:
        p.error("Provide --compound <id> or --all-pending")
        return 1

    failures = []
    for compound in target:
        try:
            result = screen_compound(compound, data_dir, dry_run=args.dry_run,
                                     compounds_dir=compounds_dir)
            if result is None:
                failures.append(compound["id"])
            else:
                print(f"\n=== {compound['id']} ===")
                print(f"  n={result.get('n', 0)}")
                print(f"  effect_21d={result.get('effect_21d'):.4f}" if result.get('effect_21d') is not None else "  effect_21d=None")
                print(f"  effect_63d={result.get('effect_63d'):.4f}" if result.get('effect_63d') is not None else "  effect_63d=None")
                print(f"  hit_63d={result.get('hit_63d'):.3f}" if result.get('hit_63d') is not None else "  hit_63d=None")
                print(f"  era_consistent_63d={result.get('era_consistent_63d')}")
                print(f"  status={result.get('status', 'screened')}")
        except Exception as e:  # noqa: BLE001
            log.error("screen_compound %s FAILED: %s", compound["id"], e)
            failures.append(compound["id"])

    if failures:
        log.error("Failures: %s", failures)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
