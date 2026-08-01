"""Publish the claim-bounded biopharma seasonality methodology manifest.

This first build intentionally publishes no synthetic forecasts or placeholder
market data.  It exposes the live contracts and authority ceiling while the
point-in-time data graph and forward ledgers are being commissioned.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from engine.seasonality.foundation import build_methodology_manifest


def build(*, root: Path, as_of: date | None = None) -> Path:
    output = root / "site" / "seasonalitydata" / "methodology.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = build_methodology_manifest(as_of=as_of)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--as-of", type=date.fromisoformat)
    args = parser.parse_args()
    output = build(root=args.root, as_of=args.as_of)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
