"""Snapshot the LIVE stock score into the forward shadow book (engine/shadow_book).

Reads the just-built standouts board (site/factordata/us_standouts.json) and freezes
(date, ticker, score, percentile, regime) per name, append-only. Called once per nightly
build (also wired additively in build_stock_library); safe to run standalone. The book is
graded later by scripts/mature_shadow_book.py once horizons elapse — never here (no peeking).

Run: .venv/bin/python -m scripts.snapshot_shadow_book
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from engine import shadow_book as SB  # noqa: E402

BOARD = "site/factordata/us_standouts.json"


def rows_from_board(board: dict):
    asof = board.get("as_of")
    out = []
    for bucket in ("buy", "watch", "laggards"):
        for r in board.get(bucket, []) or []:
            conv = r.get("conviction") or {}
            score = conv.get("score")
            if r.get("ticker") is None or score is None:
                continue
            reg = (conv.get("regime") or {}).get("state") if isinstance(conv.get("regime"), dict) else None
            out.append({"ticker": r["ticker"], "score": score,
                        "percentile": score, "regime": reg})
    return asof, out


def main() -> int:
    if not os.path.exists(BOARD):
        print(f"[shadow] {BOARD} absent — run the stock library build first; nothing snapshotted.")
        return 0
    board = json.load(open(BOARD))
    asof, recs = rows_from_board(board)
    if not asof or not recs:
        print("[shadow] no as_of/scored rows on the board; nothing snapshotted.")
        return 0
    n = SB.snapshot(asof, recs)
    print(f"[shadow] snapshotted {n} new rows for {asof} → {SB.BOOK_PATH} "
          f"(book now {len(SB.load_book())} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
