"""One-off migration: stamp board_definition="legacy" on pre-version CN board rows.

Why this exists: cn_prophet_v2 (#4029) began stamping `board_definition` on new
data/china_standout_track/board.parquet rows, and emit_cn_track_ledger filters the
published ledger to the current definition. Every pre-2026-07-30 row carried NaN,
so 1,082 of 1,097 rows — the entire pre-version history, including matured winners
like 600547.SS (+7.44% vs CSI300, "beat") — silently fell out of
site/factordata/cn_track_ledger.json (563 rows → 9). The definition gate's intent
is "never publish a pre-version ledger under a new board label"; the honest reading
of that is LABEL the old cohort, not delete it. This stamps the NaN rows "legacy"
so the emitter can publish them as their own clearly-separated cohort.

Safe by construction:
  * `_latest_definition_frame` (engine/china_standout_track.py) picks the definition
    from the NEWEST board date — 2026-07-31 is pure cn_prophet_v2, so grade() /
    interim_grade() / calibration_hub still score the v2 cohort only.
  * Row order is preserved (consumers that take "last stamped row" keep reading v2).
  * Idempotent: already-stamped rows are untouched; a rerun is a no-op.
  * tmp + os.replace write — never an in-place truncation (house law).

Usage:  python -m scripts.backfill_cn_board_definition_legacy
"""
from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import china_standout_track as cst  # noqa: E402

log = logging.getLogger(__name__)

LEGACY_LABEL = "legacy"
# The same "unstamped" spellings _latest_definition_frame treats as missing.
_MISSING = ("", "nan", "None", "NaT")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    path = cst._store_path()  # noqa: SLF001 — the one canonical board store
    if not path.exists():
        log.error("no board store at %s — nothing to migrate", path)
        return 1
    df = pd.read_parquet(path)
    if "board_definition" not in df.columns:
        df["board_definition"] = None
    col = df["board_definition"]
    mask = col.isna() | col.astype(str).isin(_MISSING)
    n = int(mask.sum())
    if n == 0:
        log.info("board.parquet: all %d rows already stamped — no-op", len(df))
        return 0
    df.loc[mask, "board_definition"] = LEGACY_LABEL
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".parquet.tmp")
    os.close(fd)
    try:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    counts = df["board_definition"].value_counts(dropna=False).to_dict()
    log.info("board.parquet: stamped %d unstamped rows as %r — now %s",
             n, LEGACY_LABEL, counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
