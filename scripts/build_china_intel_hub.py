"""Build the China Intelligence Hub command apparatus.

Runs engine/china_intel_hub.build() → writes site/china_intel/command.json.
Called from scripts/build_china.py AFTER build_china_special_situations and
BEFORE build_china_intel (bus reads command.json same-session).

Standalone callable: python -m scripts.build_china_intel_hub
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from lib import config

log = logging.getLogger(__name__)


def _site_dir() -> Path:
    sd = Path(config.load()["storage"]["site_dir"])
    return sd if sd.is_absolute() else (config.ROOT / sd)


def build() -> dict | None:
    """Build command.json.  Never raises."""
    try:
        from engine import china_intel_hub
        cmd = china_intel_hub.load_and_build()

        out_dir = _site_dir() / "china_intel"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "command.json"
        out_path.write_text(
            json.dumps(cmd, ensure_ascii=False, separators=(",", ":"), default=str),
            encoding="utf-8",
        )
        n_cmd = len(cmd.get("command") or [])
        n_disc = len(cmd.get("discovery") or [])
        log.info(
            "china_intel_hub: wrote command.json — %d command, %d discovery, %d universe",
            n_cmd, n_disc, cmd.get("n_universe", 0),
        )
        return cmd
    except Exception as e:  # noqa: BLE001
        log.error("build_china_intel_hub: failed (%s)", e, exc_info=True)
        return None


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = build()
    if result is None:
        return 1
    # Print top-5 command rows for verification
    for d in (result.get("command") or [])[:5]:
        print(
            f"  {d.get('ticker'):15s} {d.get('stage'):12s} "
            f"opp={d.get('opportunity_score'):.1f} edge={d.get('edge_remaining'):.3f} "
            f"gap={d.get('leading_gap'):+d} {d.get('read','')[:60]}"
        )
    print(f"discovery lanes: {len(result.get('discovery', []))} candidates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
