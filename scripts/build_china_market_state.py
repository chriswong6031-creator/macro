"""W6 — China Market State spine builder.

Assembles per-lobe artifacts (W1-W4) into the sovereign spine packet
``china_market_state.v1`` and writes it to two locations:

  data/china_state/market_state.json   — data plane (committed)
  site/chinastatedata/market_state.json — site plane (committed)

Both files are byte-identical.  Lobe blocks are nullable; missing lobes
degrade to null + a data_gaps entry (CN-SYS-R11).  No lobe build is
triggered here — this script only reads already-built lobe artifacts.

Run
---
  python -m scripts.build_china_market_state [--smoke]

Flags
-----
  --smoke     Validate the written JSON and exit 0 (for CI / local verify).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("build_china_market_state")

_ROOT = Path(__file__).resolve().parent.parent
_DATA_OUT = _ROOT / "data" / "china_state" / "market_state.json"
_SITE_OUT = _ROOT / "site" / "chinastatedata" / "market_state.json"

_REQUIRED_TOP_KEYS = {
    "schema", "as_of", "generated_utc", "authority",
    "phase", "participation", "microstructure", "policy",
    "rotation", "macro", "external", "allocation",
    "evidence", "contradictions", "falsifiers", "data_gaps",
}


def _validate(packet: dict) -> list[str]:
    """Return list of validation failures (empty = OK)."""
    failures: list[str] = []

    missing = _REQUIRED_TOP_KEYS - set(packet.keys())
    if missing:
        failures.append(f"Missing top-level keys: {sorted(missing)}")

    schema = packet.get("schema")
    if schema != "china_market_state.v1":
        failures.append(f"Wrong schema: {schema!r} (expected 'china_market_state.v1')")

    auth = packet.get("authority") or {}
    if auth.get("tier") != "context_only":
        failures.append(f"authority.tier must be 'context_only', got {auth.get('tier')!r}")
    if "rank" not in (auth.get("cannot_do") or []):
        failures.append("authority.cannot_do must include 'rank'")

    for key in ("evidence", "contradictions", "falsifiers", "data_gaps"):
        if not isinstance(packet.get(key), list):
            failures.append(f"{key} must be a list, got {type(packet.get(key))}")

    return failures


def _write(packet: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(packet, fh, indent=2, ensure_ascii=False, default=str)
    log.info("Wrote %s", path)


def main(smoke: bool = False) -> int:
    from engine.china_market_state import build

    log.info("Assembling china_market_state.v1 spine…")
    try:
        packet = build(_ROOT)
    except Exception as exc:
        log.error("build() raised unexpectedly: %s", exc, exc_info=True)
        return 1

    failures = _validate(packet)
    if failures:
        for f in failures:
            log.error("VALIDATION FAIL: %s", f)
        return 1

    _write(packet, _DATA_OUT)
    _write(packet, _SITE_OUT)

    # Summary
    lobes_present = sum(
        1 for k in ["phase", "participation", "microstructure", "policy",
                     "rotation", "macro", "external", "allocation"]
        if packet.get(k) is not None
    )
    log.info(
        "Done: schema=%s as_of=%s lobes_present=%d/8 "
        "contradictions=%d data_gaps=%d",
        packet.get("schema"),
        packet.get("as_of"),
        lobes_present,
        len(packet.get("contradictions", [])),
        len(packet.get("data_gaps", [])),
    )

    if smoke:
        log.info("--smoke: validation passed, exiting 0")
        return 0
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build China market state spine")
    parser.add_argument("--smoke", action="store_true",
                        help="Validate output and exit 0 (for CI)")
    args = parser.parse_args()
    sys.exit(main(smoke=args.smoke))
