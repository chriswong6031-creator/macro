"""Build the bottom-sensor envelope for the US board.

Amendment 1, Lane B0, PR-1.  Display-only.  Runs AFTER library builds
(build_site.py → build_stock_library.py).  Writes:
  - data/neuralweb/bottom_sensors.parquet
  - site/neuralwebdata/bottom_sensors.json

Both paths are git-tracked (data/neuralweb/ and site/neuralwebdata/ are in git;
the nightly "git add data/ site/" commit step covers them without a force-add).
Sentinel staging determination: both output paths sit under already-tracked
directories (data/neuralweb/ is tracked — see git ls-files data/neuralweb/;
site/neuralwebdata/ is tracked — see git ls-files site/neuralwebdata/).
No new explicit git-add line in daily.yml is required.

Render-budget benchmark: 2.29s on the full US universe (~1722 names, 2026-07-06).
Wired into daily.yml (feat/nw-bottom-sensors-wiring, 2026-07-06) between the
'build world state (neural-web W1)' and 'build mastermind context (NW bridge)'
steps.  Fail-soft — missing optional inputs degrade gracefully.

Usage:
    python -m scripts.build_bottom_sensors [--root /path/to/repo] [--benchmark]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

# Make sure repo root is on sys.path when run as a script
_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pandas as pd  # noqa: E402

from engine.neuralweb.bottom_sensors import assemble  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("build_bottom_sensors")


def _json_safe(obj):
    """Convert numpy/pandas types to JSON-serialisable equivalents."""
    if isinstance(obj, float):
        if obj != obj:  # NaN
            return None
        return obj
    if isinstance(obj, (int,)):
        return obj
    return str(obj)


def build(root: Path) -> int:
    """Build and write bottom_sensors artifacts.  Returns exit code (0=ok, 1=error)."""
    t0 = time.perf_counter()

    df = assemble(root=root)
    if df.empty:
        log.error("assemble() returned empty DataFrame — aborting write")
        return 1

    elapsed = time.perf_counter() - t0
    log.info("assemble() took %.2fs for %d rows", elapsed, len(df))
    print(f"[bottom_sensors benchmark] {elapsed:.2f}s for {len(df)} tickers", flush=True)

    as_of = df.attrs.get("as_of", "")
    labels_version = df.attrs.get("labels_version", "labels_v1")

    # ── Write parquet ────────────────────────────────────────────────────────
    parquet_dir = root / "data" / "neuralweb"
    parquet_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = parquet_dir / "bottom_sensors.parquet"

    df_write = df.reset_index()  # symbol becomes a column
    df_write.to_parquet(parquet_path, index=False)
    log.info("wrote %s (%d rows)", parquet_path, len(df_write))

    # ── Write JSON (display/debug) ────────────────────────────────────────────
    json_dir = root / "site" / "neuralwebdata"
    json_dir.mkdir(parents=True, exist_ok=True)
    json_path = json_dir / "bottom_sensors.json"

    # Convert df to list-of-dicts with JSON-safe types
    records = df_write.to_dict(orient="records")
    # Replace NaN/None with None in nested values
    clean_records: list[dict] = []
    for rec in records:
        clean: dict = {}
        for k, v in rec.items():
            if v is None or (isinstance(v, float) and v != v):
                clean[k] = None
            elif isinstance(v, (bool, int, str)):
                clean[k] = v
            elif isinstance(v, float):
                clean[k] = v
            else:
                clean[k] = str(v)
        clean_records.append(clean)

    payload = {
        "as_of": as_of,
        "labels_version": labels_version,
        "is_display_only": True,
        "n_rows": len(clean_records),
        "rows": clean_records,
    }
    json_path.write_text(
        json.dumps(payload, separators=(",", ":"), allow_nan=False, default=_json_safe)
    )
    log.info("wrote %s (%d rows)", json_path, len(clean_records))

    # ── Label distribution summary ────────────────────────────────────────────
    if "bottom_state" in df.columns:
        dist = df["bottom_state"].value_counts().to_dict()
        log.info("label distribution: %s", dist)
        print(f"[bottom_sensors label distribution] {dist}", flush=True)

    total = time.perf_counter() - t0
    print(f"[bottom_sensors total] {total:.2f}s including I/O", flush=True)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Build bottom_sensors envelope")
    parser.add_argument(
        "--root", default=None,
        help="Repo root path (default: inferred from script location)"
    )
    parser.add_argument(
        "--benchmark", action="store_true",
        help="Print timing and exit (same as default — timing always printed)"
    )
    args = parser.parse_args()

    root = Path(args.root) if args.root else _REPO_ROOT
    code = build(root)
    sys.exit(code)


if __name__ == "__main__":
    main()
