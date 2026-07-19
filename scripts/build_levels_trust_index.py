#!/usr/bin/env python3
"""scripts/build_levels_trust_index.py — publish the per-ticker Trust Index.

Voltick Gamma-Levels program, WP-C2. Reads the WP-C1 grades ledger
(data/levels/grades.parquet), reduces it to one board-level record per (root, session_date),
and ranks every ticker by how reliably its named levels described what price did next. Worst
names shown; tickers with too few graded sessions are held out until they have a real base.

DISPLAY-TIER: descriptive historical reliability — not a prediction, not a win rate, never a
buy/sell ranking. Positioning, not prophecy.

Usage:
    python -m scripts.build_levels_trust_index                 # local
    python -m scripts.build_levels_trust_index --publish       # + R2
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib.config import data_dir  # noqa: E402
from engine.levels_trust_index import compute_trust_index, MIN_SESSIONS  # noqa: E402

try:
    from engine.grading_stats import wilson_ci as _wilson_ci  # noqa: E402
except Exception:  # noqa: BLE001
    _wilson_ci = None

log = logging.getLogger("build_levels_trust_index")

_LEVELS_DIR = Path(data_dir()) / "levels"
_GRADES = _LEVELS_DIR / "grades.parquet"
_OUT = _LEVELS_DIR / "trust_index.json"
R2_KEY = "levels_trust_index.json"

_BOARD_COLS = ["board_id", "root", "session_date", "reason",
               "wall_contained", "band_contained", "anchor_drew"]


def _board_records(grades: pd.DataFrame) -> list[dict]:
    """Reduce the per-node grades frame to one record per graded board."""
    cols = [c for c in _BOARD_COLS if c in grades.columns]
    boards = grades[cols].drop_duplicates(subset=["board_id"], keep="last")
    boards = boards[boards.get("reason") == "ok"] if "reason" in boards.columns else boards
    recs = []
    for _, r in boards.iterrows():
        recs.append({
            "root": r.get("root"),
            "session_date": r.get("session_date"),
            "wall_contained": _tri(r.get("wall_contained")),
            "band_contained": _tri(r.get("band_contained")),
            "anchor_drew": _tri(r.get("anchor_drew")),
        })
    return recs


def _tri(v):
    """Coerce parquet's object/None bools to True/False/None."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return bool(v)


def _publish_r2(local: Path, key: str) -> bool:
    ak = os.environ.get("R2_ACCESS_KEY_ID"); sk = os.environ.get("R2_SECRET_ACCESS_KEY")
    ep = os.environ.get("R2_ENDPOINT"); bucket = os.environ.get("R2_BUCKET", "mastermindx")
    if not (ak and sk and ep):
        log.warning("R2 creds absent — skipping publish")
        return False
    try:
        import boto3  # noqa: PLC0415
        s3 = boto3.client("s3", endpoint_url=ep, aws_access_key_id=ak,
                          aws_secret_access_key=sk, region_name="auto")
        s3.upload_file(str(local), bucket, key, ExtraArgs={"ContentType": "application/json"})
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("R2 publish failed for %s — %s", key, e)
        return False


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="Publish the per-ticker levels Trust Index.")
    ap.add_argument("--grades", default=str(_GRADES))
    ap.add_argument("--out", default=str(_OUT))
    ap.add_argument("--min-sessions", type=int, default=MIN_SESSIONS)
    ap.add_argument("--publish", action="store_true")
    args = ap.parse_args(argv)

    gp = Path(args.grades)
    if not gp.exists():
        log.error("no grades ledger at %s — run build_levels_track_record first", gp)
        return 2
    try:
        grades = pd.read_parquet(gp)
    except Exception as e:  # noqa: BLE001
        log.error("grades ledger unreadable: %s", e)
        return 3

    recs = _board_records(grades)
    payload = compute_trust_index(recs, ci_fn=_wilson_ci, min_sessions=args.min_sessions)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, separators=(",", ":")))
    if args.publish:
        _publish_r2(out, R2_KEY)

    log.info("trust index: %d ranked, %d still banking (< %d sessions) → %s",
             payload["n_ranked"], payload["n_banking"], args.min_sessions, out)
    for e in payload["ranked"][:10]:
        log.info("  #%-2d %-6s %s  (%s, %d sessions)", e["rank"], e["root"],
                 f"{e['composite']:.0%}" if e["composite"] is not None else "—",
                 e["read"], e["sessions"])
    if payload["least_reliable"]:
        lr = payload["least_reliable"]
        log.info("  least reliable: %s %s (%d sessions) — shown, so the record stays honest",
                 lr["root"], f"{lr['composite']:.0%}" if lr["composite"] is not None else "—",
                 lr["sessions"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
