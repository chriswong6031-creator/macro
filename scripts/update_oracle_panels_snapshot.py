"""Update data/oracle/oracle_panels_snapshot.json from live oracle parquets.

PR-B3 — bottom_sensors v2 sponsorship un-starvation.

Reads data/oracle/panel_s.parquet and data/oracle/panel_m.parquet (R2-stored,
Mac-local only), extracts the latest-row vel_1m/accel per node, and writes a
compact committed JSON snapshot (~41 KB) that bottom_sensors.py uses as a
fallback when the full parquets are absent (CI runners / worktrees).

The snapshot format (schema='oracle_panels_snapshot_v1') is forward-stable:
the _load_oracle_panel_snapshot() function in bottom_sensors.py reads only
vel_1m, accel, and as_of per node.

Usage
-----
    python -m scripts.update_oracle_panels_snapshot [--root PATH] [--dry-run]

    --root PATH    repo root (default: inferred from script location)
    --dry-run      print what would be written; do not write

Run on the Mac after the nightly oracle build step (oracle_nightly.py step 1b)
when panels have been refreshed.  Commit the updated snapshot with a note like:
    'data: refresh oracle_panels_snapshot.json (YYYY-MM-DD)'
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("update_oracle_panels_snapshot")

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent

_SNAPSHOT_FILENAME = "oracle_panels_snapshot.json"


def _extract_snapshot(panel: pd.DataFrame) -> dict:
    """Extract latest vel_1m/accel per node from a full oracle panel."""
    result: dict[str, dict] = {}
    nodes = panel.index.get_level_values("node").unique()
    for node in nodes:
        try:
            node_rows = panel.xs(node, level="node")
        except KeyError:
            continue
        if node_rows.empty:
            continue
        latest_date = node_rows.index.max()
        latest = node_rows.loc[latest_date]
        vel_1m = latest.get("vel_1m") if isinstance(latest, pd.Series) else None
        accel = latest.get("accel") if isinstance(latest, pd.Series) else None
        result[str(node)] = {
            "as_of": latest_date.isoformat()[:10],
            "vel_1m": round(float(vel_1m), 6) if (vel_1m is not None and pd.notna(vel_1m)) else None,
            "accel": round(float(accel), 6) if (accel is not None and pd.notna(accel)) else None,
        }
    return result


def update_snapshot(root: Path, dry_run: bool = False) -> int:
    """Read full oracle parquets; write compact snapshot.  Returns 0 on success."""
    oracle_dir = root / "data" / "oracle"
    out_path = oracle_dir / _SNAPSHOT_FILENAME

    panel_s_path = oracle_dir / "panel_s.parquet"
    panel_m_path = oracle_dir / "panel_m.parquet"

    # Load panels
    panel_s_data: dict = {}
    panel_m_data: dict = {}

    if panel_s_path.exists():
        try:
            df = pd.read_parquet(panel_s_path)
            if "date" in df.index.names:
                new_levels = []
                for i, name in enumerate(df.index.names):
                    if name == "date":
                        new_levels.append(pd.to_datetime(df.index.get_level_values(i)))
                    else:
                        new_levels.append(df.index.get_level_values(i))
                df.index = pd.MultiIndex.from_arrays(new_levels, names=df.index.names)
            panel_s_data = _extract_snapshot(df)
            log.info("panel_s: %d nodes extracted", len(panel_s_data))
        except Exception as exc:  # noqa: BLE001
            log.error("Failed to load panel_s.parquet: %s", exc)
            return 1
    else:
        log.error("panel_s.parquet not found at %s", panel_s_path)
        return 1

    if panel_m_path.exists():
        try:
            df = pd.read_parquet(panel_m_path)
            if "date" in df.index.names:
                new_levels = []
                for i, name in enumerate(df.index.names):
                    if name == "date":
                        new_levels.append(pd.to_datetime(df.index.get_level_values(i)))
                    else:
                        new_levels.append(df.index.get_level_values(i))
                df.index = pd.MultiIndex.from_arrays(new_levels, names=df.index.names)
            panel_m_data = _extract_snapshot(df)
            log.info("panel_m: %d nodes extracted", len(panel_m_data))
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to load panel_m.parquet: %s — subsector nodes will be absent", exc)
    else:
        log.warning("panel_m.parquet not found at %s — subsector nodes will be absent", panel_m_path)

    # Build payload
    payload = {
        "schema": "oracle_panels_snapshot_v1",
        "description": (
            "Compact snapshot of oracle panel latest-row vel_1m/accel per node. "
            "Committed fallback for CI runners where panel_s.parquet/panel_m.parquet "
            "are unavailable (R2-stored). Updated by scripts/update_oracle_panels_snapshot.py "
            "on the Mac-local write path."
        ),
        "panel_s": panel_s_data,
        "panel_m": panel_m_data,
    }

    snap_json = json.dumps(payload, indent=2, separators=(",", ": "))
    size_kb = len(snap_json.encode()) / 1024

    log.info(
        "snapshot: panel_s=%d nodes, panel_m=%d nodes, size=%.1f KB",
        len(panel_s_data), len(panel_m_data), size_kb,
    )

    if dry_run:
        log.info("[dry-run] would write %s (%.1f KB)", out_path, size_kb)
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(snap_json)
    log.info("written: %s (%.1f KB)", out_path, size_kb)
    print(
        f"[update_oracle_panels_snapshot] wrote {out_path} "
        f"({len(panel_s_data)}+{len(panel_m_data)} nodes, {size_kb:.1f} KB)",
        flush=True,
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update oracle_panels_snapshot.json from live parquets"
    )
    parser.add_argument("--root", default=None, help="Repo root path")
    parser.add_argument("--dry-run", action="store_true", help="Print plan; write nothing")
    args = parser.parse_args()

    root = Path(args.root) if args.root else _REPO_ROOT
    sys.exit(update_snapshot(root, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
