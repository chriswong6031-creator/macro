#!/usr/bin/env python3
"""Freeze the PSS-RH1 historical parity audit input grid.

One-time freeze utility.  The full-runtime parity audit in
tests/test_personality_relief_hazard.py replays the exact SR3 construction
through the runtime scanner and compares against the frozen events tape.  The
live ohlcv store is total-return adjusted, so every dividend retroactively
re-scales (and re-rounds, ~1e-5 relative) the full close/low/ATR history — a
live-store replay drifts with every nightly collection, and group labels
(count ratios thresholded at exactly 0.50) can flip with zero code drift.

This utility extracts the frozen-membership OHLC panels from the registered
freeze source commit — the vintage the SR3 tape was constructed from, whose
replay through the runtime scanner is bit-exact against the frozen events
parquet — into one parquet so the audit's inputs never move again.  The test
pins the artifact by sha256; a rebuild on a different environment may produce
different parquet bytes for identical data, so a rebuild requires re-verifying
bit-exact parity and updating the pinned hash in the same change.
"""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import personality_relief_hazard as prh  # noqa: E402

# The RH1 registration's freeze source (scripts/research/
# freeze_pss_rh1_relief_hazard.py SOURCE_COMMIT).  Its data/baskets/ohlcv tree
# (78b10aacdb12284e9b13b984f43c70fa027d61e9) is identical to the last daily
# collection before total-return adjustment first broke live parity
# (1c0727981a5, "data: daily collection 2026-07-27"; break documented in
# #3866).
SOURCE_COMMIT = "71ac1df412a9cf0b32b050ff05d40ed59c0ac27c"
MEMBERSHIP = ROOT / "data/personality_timing/relief_hazard_membership_v1.json"
AUDIT_GRID = ROOT / "data/personality_timing/relief_hazard_audit_grid_v1.parquet"
# The scanner's union index drops sessions before 2018-01-01 and the audit
# scans through 2026-07-27, so rows outside this span are unreachable.
GRID_START = pd.Timestamp("2018-01-01")
GRID_THROUGH = pd.Timestamp("2026-07-27")


def _vintage_frame(sym: str) -> pd.DataFrame | None:
    blob = subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "cat-file",
            "blob",
            f"{SOURCE_COMMIT}:data/baskets/ohlcv/{sym}.parquet",
        ],
        capture_output=True,
    )
    if blob.returncode != 0:
        return None
    frame = prh.clean_index(pd.read_parquet(io.BytesIO(blob.stdout)))
    frame = frame[["open", "high", "low", "close"]].astype(float)
    frame = frame.loc[(frame.index >= GRID_START) & (frame.index <= GRID_THROUGH)]
    return frame if not frame.empty else None


def main() -> int:
    membership = json.loads(MEMBERSHIP.read_text(encoding="utf-8"))
    syms = sorted(
        str(row["sym"])
        for row in membership["members"]
        if row.get("sector") in prh.SECTORS
    )
    pieces: list[pd.DataFrame] = []
    missing: list[str] = []
    for sym in syms:
        frame = _vintage_frame(sym)
        if frame is None:
            missing.append(sym)
            continue
        piece = frame.reset_index(names="date")
        piece.insert(0, "sym", sym)
        pieces.append(piece)
    grid = pd.concat(pieces, ignore_index=True).sort_values(
        ["sym", "date"], kind="stable"
    )
    grid = grid.reset_index(drop=True)
    grid.to_parquet(AUDIT_GRID, compression="zstd", index=False)
    digest = hashlib.sha256(AUDIT_GRID.read_bytes()).hexdigest()
    print(f"source_commit: {SOURCE_COMMIT}")
    print(f"members in scope: {len(syms)}; with vintage ohlcv: {len(pieces)}")
    print(f"missing at vintage: {len(missing)} {missing[:10]}")
    print(f"rows: {len(grid)}; span: {grid['date'].min()} .. {grid['date'].max()}")
    print(f"bytes: {AUDIT_GRID.stat().st_size}")
    print(f"sha256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
