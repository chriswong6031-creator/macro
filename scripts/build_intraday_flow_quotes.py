"""Publish the Intraday Flow board's quotes from the VPS full snapshot.

This is a transport filter, not a second quote engine: the snapshot lane has
already fetched the vendor data into ``quotes_full.json``.  The public board
gets only the symbols already disclosed by its nightly ``base.json``.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _has_price(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    try:
        return math.isfinite(float(value.get("price")))
    except (TypeError, ValueError):
        return False


def build_payload(base: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    leaders = base.get("leaders") or []
    symbols = sorted(
        {
            str(row.get("ticker") or "").strip().upper()
            for row in leaders
            if isinstance(row, dict) and row.get("ticker")
        }
    )
    if not symbols:
        raise ValueError("Intraday Flow base contains no leader symbols")
    source_quotes = snapshot.get("quotes") or {}
    if not isinstance(source_quotes, dict):
        raise ValueError("full quote snapshot has no quote map")
    quotes = {
        symbol: source_quotes[symbol]
        for symbol in symbols
        if symbol in source_quotes and _has_price(source_quotes[symbol])
    }
    now = datetime.now(timezone.utc)
    upstream_meta = snapshot.get("meta") or {}
    return {
        "ts": snapshot.get("ts") or int(now.timestamp() * 1000),
        "asof": snapshot.get("asof") or now.isoformat(),
        "source": "snapshot:intraday_flow",
        "quotes": quotes,
        "meta": {
            "requested": len(symbols),
            "resolved": len(quotes),
            "coverage": round(len(quotes) / len(symbols), 6),
            "upstream_asof": snapshot.get("asof"),
            "upstream_source": snapshot.get("source"),
            "upstream_requested": upstream_meta.get("requested"),
            "upstream_resolved": upstream_meta.get("resolved"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--quotes", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    payload = build_payload(
        json.loads(args.base.read_text(encoding="utf-8")),
        json.loads(args.quotes.read_text(encoding="utf-8")),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
