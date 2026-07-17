"""End-of-collection coverage audit for FRED config groups.

For every group under ``config fred.series``, counts how many of its configured
series have a parquet in ``data/fred/`` fresher than ``STALE_DAYS`` (default 45).
Emits a per-group report (group, n_present/n_total, missing ids) and exits
non-zero ONLY if any group falls below ``MIN_PRESENT_PCT`` (default 50 %).

This guard makes the class of failure described in
research/FORESIGHT_DESK_UPGRADE_BY_FABLE.md §1 Q1 — "configured but never
landed" — impossible to repeat silently. The bottleneck + power groups are the
keystone case: when they fall below 50 % present the entire T1 physical desk
collapses to AWAITING_DATA for all themes.

Run as a module:  ``python -m scripts.audit_fred_groups``
Importable as:     ``from scripts import audit_fred_groups``
Writes:           ``data/quality/fred_groups_audit.json``
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import date, timedelta
from pathlib import Path

from lib import config

log = logging.getLogger("audit.fred_groups")

# A parquet older than this is treated as absent (stale = effectively dark for the engine).
STALE_DAYS: int = 45

# Gate: a group with fewer than this fraction of its configured series present and fresh
# is DARK — the audit exits non-zero to warn CI/local collect.
MIN_PRESENT_PCT: float = 50.0


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _fred_dir(data_dir: Path) -> Path:
    return data_dir / "fred"


def _is_fresh(path: Path, asof: date, stale_days: int) -> bool:
    """True when the parquet exists AND its newest OBSERVATION date is recent.

    Freshness is judged from the data's own newest index date — never file
    mtime. On CI runners a checkout rewrites files with mtime = checkout time,
    so a frozen series always looked freshly collected and this audit was
    blind to exactly the configured-but-dark class it exists to catch (the
    polygon-universe frozen-cache class, #2690; same blindness as the ^GSPC
    never-collected incident, #2659).

    Slow-cadence series get their natural release lag: the threshold is
    stale_days + 2× the series' own median observation spacing (daily
    ≈ stale_days, monthly ≈ +60d, quarterly ≈ +180d). Unreadable or undated
    parquets ⇒ stale.
    """
    if not path.exists():
        return False
    try:
        import pandas as pd  # noqa: PLC0415 — heavy; audit-only path
        idx = pd.to_datetime(pd.read_parquet(path, columns=[]).index,
                             errors="coerce").dropna()
        if len(idx) == 0:
            return False
        last = idx.max().date()
        cadence_days = 0.0
        if len(idx) >= 3:
            deltas = idx.sort_values().to_series().diff().dropna()
            cadence_days = float(deltas.tail(6).median().days)
        return (asof - last).days <= stale_days + 2 * cadence_days
    except Exception as e:  # noqa: BLE001
        log.warning("[fred_groups] cannot read content date from %s (%s) — treating stale",
                    path.name, e)
        return False


def audit_groups(
    cfg: dict | None = None,
    data_dir: Path | None = None,
    asof: date | None = None,
    stale_days: int = STALE_DAYS,
    min_present_pct: float = MIN_PRESENT_PCT,
    out_dir: Path | None = None,
) -> dict:
    """Audit FRED config groups for parquet coverage. Never raises for data issues.

    Returns the audit document dict (also written to data/quality/fred_groups_audit.json).
    Exits non-zero via the returned ``any_dark`` flag; callers (collect.py) check it.
    """
    cfg = cfg or config.load()
    asof = asof or date.today()
    fred_dir = _fred_dir(data_dir or config.data_dir())
    out_dir = out_dir or (config.data_dir() / "quality")
    out_dir.mkdir(parents=True, exist_ok=True)

    groups_cfg: dict = (cfg.get("fred") or {}).get("series") or {}

    groups: list[dict] = []
    any_dark = False

    for group_name, series_map in groups_cfg.items():
        if not isinstance(series_map, dict):
            continue  # skip non-dict entries (e.g. scalar overrides)
        total = len(series_map)
        if total == 0:
            continue

        missing: list[str] = []
        present_count = 0
        for sid in series_map:
            path = fred_dir / f"{sid}.parquet"
            if _is_fresh(path, asof, stale_days):
                present_count += 1
            else:
                missing.append(sid)

        pct = 100.0 * present_count / total
        dark = pct < min_present_pct
        if dark:
            any_dark = True
            log.warning(
                "[fred_groups] group %s DARK: %d/%d present (%.0f%% < %.0f%% threshold); "
                "missing: %s",
                group_name, present_count, total, pct, min_present_pct,
                ", ".join(missing),
            )
        else:
            log.info(
                "[fred_groups] group %s OK: %d/%d present (%.0f%%); missing: %s",
                group_name, present_count, total, pct,
                ", ".join(missing) if missing else "none",
            )

        groups.append({
            "group": group_name,
            "n_present": present_count,
            "n_total": total,
            "pct_present": round(pct, 1),
            "dark": dark,
            "missing": missing,
        })

    doc = {
        "asof": asof.isoformat(),
        "audit": "fred_groups",
        "stale_days": stale_days,
        "min_present_pct": min_present_pct,
        "any_dark": any_dark,
        "groups": groups,
    }
    (out_dir / "fred_groups_audit.json").write_text(json.dumps(doc, indent=1))
    return doc


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default=None, help="override data/ root")
    ap.add_argument("--out-dir", default=None, help="override data/quality output dir")
    ap.add_argument("--asof", default=None, help="override as-of date (YYYY-MM-DD)")
    ap.add_argument("--stale-days", type=int, default=STALE_DAYS,
                    help=f"days after which a parquet counts as absent (default {STALE_DAYS})")
    ap.add_argument("--min-present-pct", type=float, default=MIN_PRESENT_PCT,
                    help=f"group is DARK below this %% coverage (default {MIN_PRESENT_PCT})")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    doc = audit_groups(
        data_dir=Path(args.data_dir) if args.data_dir else None,
        out_dir=Path(args.out_dir) if args.out_dir else None,
        asof=date.fromisoformat(args.asof) if args.asof else None,
        stale_days=args.stale_days,
        min_present_pct=args.min_present_pct,
    )

    # Human-readable summary to stdout
    w = max((len(g["group"]) for g in doc["groups"]), default=10)
    header = f"{'GROUP':<{w}}  {'PRESENT':>7}  {'TOTAL':>5}  {'PCT':>6}  {'STATUS':<6}  MISSING"
    print(header)
    print("-" * len(header))
    for g in doc["groups"]:
        status = "DARK" if g["dark"] else "OK"
        missing_str = ", ".join(g["missing"]) if g["missing"] else "-"
        print(f"{g['group']:<{w}}  {g['n_present']:>7}  {g['n_total']:>5}  "
              f"{g['pct_present']:>5.0f}%  {status:<6}  {missing_str}")

    if doc["any_dark"]:
        dark_groups = [g["group"] for g in doc["groups"] if g["dark"]]
        log.warning("[fred_groups] GATE FAIL — dark groups: %s", ", ".join(dark_groups))
        return 1

    log.info("[fred_groups] gate passed — all groups ≥ %.0f%% present", args.min_present_pct)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
