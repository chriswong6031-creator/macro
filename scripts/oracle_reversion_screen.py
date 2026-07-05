"""Oracle Reversion-Capture + Drawdown-Asymmetry Screener.

Standalone analysis tool — read-only by default (prints a report; writes
nothing unless --write-csv is passed).  Zero overlap with the existing
scripts/oracle_screen.py tier-1 pipeline; does NOT touch trial_ledger or
registry.

METRIC DEFINITION (per entry, window W sessions, time-exit E sessions)
-----------------------------------------------------------------------
From exec date (= next close after trigger t):

  MFE   = max(lvl[s] / lvl[exec] - 1)  over next W sessions   (up-bounce)
  MAE   = min(lvl[s] / lvl[exec] - 1)  over next W sessions   (worst dd)
  ret_exit = lvl[exec+E] / lvl[exec] - 1  (absolute time-exit return)

Regime tag (from node's panel row at trigger date t):
  risk_off if spy_above_200d == 0 OR vix_pctile >= 0.70
  else risk_on

Per-compound aggregates
-----------------------
  n               total mature entries
  mean_ret_exit   mean absolute time-exit return
  WR              win-rate = frac(ret_exit > 0)
  mean_MFE        mean maximum-favourable-excursion
  mean_MAE        mean maximum-adverse-excursion  (negative number)
  asym            mean_MFE / |mean_MAE|  (higher is better; upside vs downside)

All six metrics also reported split by regime (risk_on / risk_off).

USAGE
-----
  # Single compound from registry
  python -m scripts.oracle_reversion_screen --compound A1 \\
      --data-dir /path/to/data

  # All compounds in registry
  python -m scripts.oracle_reversion_screen --all-pending \\
      --data-dir /path/to/data --window 25 --exit 21

  # Inline rule (JSON) — no registry entry needed
  python -m scripts.oracle_reversion_screen \\
      --inline-rule '{"col":"washout_w","op":"gt","value":0}' \\
      --inline-id bare_washout \\
      --data-dir /path/to/data

INLINE FALLBACK COMPOUNDS (A15, bare_washout)
---------------------------------------------
If the requested compound id is not in the registry, the tool defines it
inline:
  A15 = {"all":[{"col":"washout_w","op":"gt","value":0},
                {"episode_event":{"direction":"out","tier":"onset",
                                  "complex_scope":"opposite",
                                  "within_sessions":20,"min_count":2}}]}
  bare_washout = {"col":"washout_w","op":"gt","value":0}
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
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
log = logging.getLogger("oracle_reversion_screen")

# ---------------------------------------------------------------------------
# Inline fallback compounds (used when id absent from registry)
# ---------------------------------------------------------------------------

_INLINE_COMPOUNDS: dict[str, dict] = {
    "A15": {
        "id": "A15",
        "name": "Washout + opposite-complex cascade (A15)",
        "universe": {"tier": "s"},
        "entry_rule": {
            "all": [
                {"col": "washout_w", "op": "gt", "value": 0},
                {
                    "episode_event": {
                        "direction": "out",
                        "tier": "onset",
                        "complex_scope": "opposite",
                        "within_sessions": 20,
                        "min_count": 2,
                    }
                },
            ]
        },
    },
    "bare_washout": {
        "id": "bare_washout",
        "name": "Bare washout (washout_w > 0)",
        "universe": {"tier": "s"},
        "entry_rule": {"col": "washout_w", "op": "gt", "value": 0},
    },
}


# ---------------------------------------------------------------------------
# Data loading (reuse oracle_screen's functions)
# ---------------------------------------------------------------------------

def _load_panel(data_dir: Path, tier: str) -> pd.DataFrame:
    from scripts.oracle_screen import _load_panel as _lp
    return _lp(data_dir, tier)


def _load_episodes(data_dir: Path, tier: str) -> pd.DataFrame:
    from scripts.oracle_screen import _load_episodes as _le
    return _le(data_dir, tier)


def _load_spy(data_dir: Path) -> pd.Series | None:
    from scripts.oracle_screen import _load_spy as _ls
    return _ls(data_dir)


def _load_rotation_groups(data_dir: Path) -> dict:
    from scripts.oracle_screen import _load_rotation_groups as _lrg
    return _lrg(data_dir)


# ---------------------------------------------------------------------------
# Regime tag helper
# ---------------------------------------------------------------------------

def _regime_at(row: pd.Series) -> str:
    """Return 'risk_off' or 'risk_on' from a panel row at trigger date t."""
    spy_above = row.get("spy_above_200d", np.nan)
    vix_pct = row.get("vix_pctile", np.nan)
    if not np.isnan(spy_above) and spy_above == 0:
        return "risk_off"
    if not np.isnan(vix_pct) and vix_pct >= 0.70:
        return "risk_off"
    return "risk_on"


# ---------------------------------------------------------------------------
# Core metric computation (per entry)
# ---------------------------------------------------------------------------

def _compute_entry_metrics(
    entry_dates: dict[str, pd.DatetimeIndex],
    panel: pd.DataFrame,
    window: int,
    exit_sessions: int,
) -> pd.DataFrame:
    """Compute MFE / MAE / ret_exit / regime for each entry across all nodes.

    Returns a DataFrame with columns:
      node, trigger_date, exec_date, MFE, MAE, ret_exit, regime

    Entries whose outcome window (exec_date + window) is beyond the data end
    are dropped (not mature).
    """
    rows: list[dict] = []

    for node, dates in entry_dates.items():
        try:
            npn = panel.xs(node, level="node")
        except KeyError:
            continue

        if "ret" not in npn.columns:
            continue

        ret_series = npn["ret"].sort_index()
        lvl = (1 + ret_series.fillna(0)).cumprod()
        all_dates = ret_series.index  # sorted DatetimeIndex

        for trigger_t in dates:
            # Execution: next close after trigger
            future = all_dates[all_dates > trigger_t]
            if len(future) == 0:
                continue
            exec_date = future[0]
            exec_pos = all_dates.searchsorted(exec_date, side="left")

            # Outcome window: exec_pos + 1 .. exec_pos + window (inclusive)
            end_pos = exec_pos + window
            if end_pos >= len(all_dates):
                continue  # not mature

            exec_price = lvl.iat[exec_pos]
            if exec_price == 0 or np.isnan(exec_price):
                continue

            window_prices = lvl.iloc[exec_pos + 1 : exec_pos + window + 1]
            window_rets = window_prices / exec_price - 1

            mfe = float(window_rets.max())
            mae = float(window_rets.min())

            # Time-exit: exec_pos + exit_sessions
            exit_pos = exec_pos + exit_sessions
            if exit_pos >= len(all_dates):
                continue  # exit not yet reached
            exit_price = lvl.iat[exit_pos]
            if exit_price == 0 or np.isnan(exit_price):
                continue
            ret_exit = float(exit_price / exec_price - 1)

            # Regime: read from trigger row (t, not exec)
            if trigger_t in npn.index:
                regime = _regime_at(npn.loc[trigger_t])
            else:
                # Use nearest preceding row
                preceding = npn.index[npn.index <= trigger_t]
                if len(preceding) == 0:
                    regime = "unknown"
                else:
                    regime = _regime_at(npn.loc[preceding[-1]])

            rows.append(
                {
                    "node": node,
                    "trigger_date": trigger_t,
                    "exec_date": exec_date,
                    "MFE": mfe,
                    "MAE": mae,
                    "ret_exit": ret_exit,
                    "regime": regime,
                }
            )

    if not rows:
        return pd.DataFrame(
            columns=["node", "trigger_date", "exec_date",
                     "MFE", "MAE", "ret_exit", "regime"]
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Aggregate stats
# ---------------------------------------------------------------------------

def _agg_stats(df: pd.DataFrame) -> dict[str, Any]:
    """Aggregate MFE/MAE/ret_exit/WR/asym from an entries dataframe."""
    if df.empty:
        return {
            "n": 0, "mean_ret_exit": np.nan, "WR": np.nan,
            "mean_MFE": np.nan, "mean_MAE": np.nan, "asym": np.nan,
        }
    n = len(df)
    mean_ret_exit = float(df["ret_exit"].mean())
    wr = float((df["ret_exit"] > 0).mean())
    mean_mfe = float(df["MFE"].mean())
    mean_mae = float(df["MAE"].mean())
    abs_mae = abs(mean_mae)
    asym = float(mean_mfe / abs_mae) if abs_mae > 1e-9 else np.nan
    return {
        "n": n,
        "mean_ret_exit": mean_ret_exit,
        "WR": wr,
        "mean_MFE": mean_mfe,
        "mean_MAE": mean_mae,
        "asym": asym,
    }


# ---------------------------------------------------------------------------
# Print report
# ---------------------------------------------------------------------------

def _pct(v: float | None) -> str:
    if v is None or np.isnan(v):
        return "n/a"
    return f"{v*100:+.2f}%"


def _fmt(v: float | None, decimals: int = 2) -> str:
    if v is None or np.isnan(v):
        return "n/a"
    return f"{v:.{decimals}f}"


def _print_compound_report(
    compound_id: str,
    name: str,
    all_stats: dict,
    risk_on_stats: dict,
    risk_off_stats: dict,
    window: int,
    exit_sessions: int,
) -> None:
    w = 58
    print()
    print("=" * w)
    print(f"  {compound_id}  {name}")
    print(f"  window={window} sessions, exit={exit_sessions} sessions (absolute returns)")
    print("=" * w)

    def _row(label: str, s: dict) -> None:
        print(
            f"  {label:<12}  "
            f"n={s['n']:<6}  "
            f"ret_exit={_pct(s['mean_ret_exit'])}  "
            f"WR={_fmt(s['WR'], 3)}  "
            f"MFE={_pct(s['mean_MFE'])}  "
            f"MAE={_pct(s['mean_MAE'])}  "
            f"asym={_fmt(s['asym'])}"
        )

    _row("all-regime", all_stats)
    _row("risk_on", risk_on_stats)
    _row("risk_off", risk_off_stats)
    print()


# ---------------------------------------------------------------------------
# Main screen function
# ---------------------------------------------------------------------------

def screen_compound(
    compound: dict,
    data_dir: Path,
    window: int = 25,
    exit_sessions: int = 21,
) -> dict | None:
    """Screen a single compound.  Returns dict of stats or None on error."""
    from engine.oracle.compounds import (
        get_entry_dates,
        augment_panel_with_derived,
    )

    compound_id = compound.get("id", "?")
    name = compound.get("name", "")
    universe = compound.get("universe", {})
    tier = universe.get("tier", "s")

    log.info("Screening %s (tier=%s, W=%d, E=%d)", compound_id, tier, window, exit_sessions)

    try:
        panel = _load_panel(data_dir, tier)
        episodes = _load_episodes(data_dir, tier)
    except FileNotFoundError as exc:
        log.error("Data load failed for %s: %s", compound_id, exc)
        return None

    rotation_groups = _load_rotation_groups(data_dir)
    panel = augment_panel_with_derived(panel)

    try:
        entry_dates = get_entry_dates(compound, panel, episodes, rotation_groups)
    except ValueError as exc:
        log.error("Rule validation error for %s: %s", compound_id, exc)
        return None

    if "__blocked__" in entry_dates:
        log.warning("%s BLOCKED — missing columns: %s", compound_id, entry_dates["__blocked__"])
        return None

    total = sum(len(v) for v in entry_dates.values())
    log.info("%s: %d total triggers across %d nodes", compound_id, total, len(entry_dates))

    entries_df = _compute_entry_metrics(entry_dates, panel, window, exit_sessions)

    if entries_df.empty:
        log.warning("%s: no mature entries (all outside data range)", compound_id)
        all_stats = _agg_stats(entries_df)
        risk_on_stats = _agg_stats(pd.DataFrame())
        risk_off_stats = _agg_stats(pd.DataFrame())
    else:
        all_stats = _agg_stats(entries_df)
        risk_on_stats = _agg_stats(entries_df[entries_df["regime"] == "risk_on"])
        risk_off_stats = _agg_stats(entries_df[entries_df["regime"] == "risk_off"])

    _print_compound_report(
        compound_id, name, all_stats, risk_on_stats, risk_off_stats,
        window, exit_sessions,
    )

    return {
        "compound_id": compound_id,
        "name": name,
        "tier": tier,
        "window": window,
        "exit_sessions": exit_sessions,
        "all": all_stats,
        "risk_on": risk_on_stats,
        "risk_off": risk_off_stats,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _resolve_compound(
    compound_id: str,
    registry: list[dict],
    inline_rule_json: str | None = None,
    inline_id: str | None = None,
) -> dict | None:
    """Resolve a compound definition: registry first, then inline fallbacks."""
    # Try registry
    for c in registry:
        if c.get("id") == compound_id:
            return c

    # Try built-in inline fallbacks
    if compound_id in _INLINE_COMPOUNDS:
        log.info("%s not in registry — using built-in inline definition", compound_id)
        return _INLINE_COMPOUNDS[compound_id]

    # Try user-supplied inline rule
    if inline_rule_json and inline_id == compound_id:
        try:
            rule = json.loads(inline_rule_json)
        except json.JSONDecodeError as exc:
            log.error("--inline-rule JSON parse error: %s", exc)
            return None
        return {
            "id": compound_id,
            "name": f"Inline: {compound_id}",
            "universe": {"tier": "s"},
            "entry_rule": rule,
        }

    log.error("Compound '%s' not found in registry or inline fallbacks", compound_id)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Oracle reversion-capture + drawdown-asymmetry screener (read-only)"
    )
    ap.add_argument("--compound", type=str, default=None,
                    help="Compound id to screen (registry or inline fallback)")
    ap.add_argument("--all-pending", action="store_true",
                    help="Screen all compounds in the registry")
    ap.add_argument("--inline-rule", type=str, default=None,
                    help="JSON string for an ad-hoc entry_rule (requires --inline-id)")
    ap.add_argument("--inline-id", type=str, default=None,
                    help="Id to assign to --inline-rule compound")
    ap.add_argument("--data-dir", type=Path, default=None,
                    help="Path to data directory")
    ap.add_argument("--compounds-dir", type=Path, default=None,
                    help="Override path to registry dir (default: <data-dir>/oracle/compounds)")
    ap.add_argument("--window", type=int, default=25,
                    help="MFE/MAE window in sessions (default: 25)")
    ap.add_argument("--exit", dest="exit_sessions", type=int, default=21,
                    help="Time-exit sessions (default: 21)")
    ap.add_argument("--dry-run", action="store_true",
                    help="No-op flag for interface parity with oracle_screen; this tool is read-only by default")
    args = ap.parse_args()

    # Resolve data directory
    if args.data_dir:
        data_dir = args.data_dir
    else:
        try:
            from lib import config as _cfg
            data_dir = _cfg.data_dir()
        except Exception:
            ap.error("--data-dir is required (lib.config unavailable)")
            return 1

    compounds_dir = args.compounds_dir or (data_dir / "oracle" / "compounds")

    from engine.oracle.compounds import load_registry
    registry = load_registry(compounds_dir)

    # Build target list
    targets: list[dict] = []

    if args.inline_rule and args.inline_id:
        # Ad-hoc inline compound
        try:
            rule = json.loads(args.inline_rule)
        except json.JSONDecodeError as exc:
            log.error("--inline-rule JSON parse error: %s", exc)
            return 1
        targets.append(
            {
                "id": args.inline_id,
                "name": f"Inline: {args.inline_id}",
                "universe": {"tier": "s"},
                "entry_rule": rule,
            }
        )
    elif args.compound:
        c = _resolve_compound(args.compound, registry, args.inline_rule, args.inline_id)
        if c is None:
            return 1
        targets.append(c)
    elif args.all_pending:
        targets = list(registry)
        log.info("all-pending: %d compounds in registry", len(targets))
    else:
        ap.error("Provide --compound <id>, --all-pending, or --inline-rule + --inline-id")
        return 1

    failures: list[str] = []
    for compound in targets:
        try:
            result = screen_compound(
                compound,
                data_dir,
                window=args.window,
                exit_sessions=args.exit_sessions,
            )
            if result is None:
                failures.append(compound.get("id", "?"))
        except Exception as exc:  # noqa: BLE001
            log.error("screen_compound %s FAILED: %s", compound.get("id"), exc)
            failures.append(compound.get("id", "?"))

    if failures:
        log.error("Failures: %s", failures)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
