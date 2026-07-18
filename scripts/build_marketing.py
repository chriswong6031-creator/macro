"""scripts/build_marketing.py — Thin orchestrator for the Marketing lobe governor.

Usage:
    python -m scripts.build_marketing

Mirrors the prophet builder shape; no R2 needed v1.
Never-raise: exits 0 with a warning message on error so the pipeline continues.
"""
from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    try:
        from engine.neuralweb.marketing_governor import build_and_write
        result = build_and_write()
    except Exception as exc:  # noqa: BLE001
        log.warning("build_marketing: governor import/run failed: %s", exc)
        print(f"marketing_governor: WARN (never-raise) — {exc}", file=sys.stderr)
        return 0

    if result.get("error"):
        print(
            f"marketing_governor: WARN (never-raise) — {result['error']}",
            file=sys.stderr,
        )
        return 0

    print(
        f"marketing_governor: ok — "
        f"state={result.get('state_path')} "
        f"lobe={result.get('lobe_path')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
