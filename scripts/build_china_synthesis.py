"""Build the China central-intelligence analysis emit (2nd/3rd-order cross-surface synthesis).

Thin runner for engine.china_intel_analysis.build() → site/china_intel_analysis/analysis.json.
MUST run AFTER the four surface builds and BEFORE build_china_intel (the bus fans this in).
CONTEXT-ONLY · never raises. See research/CHINA_INTEL_POWERHOUSE.md §1.2.
"""
from __future__ import annotations

import logging


def build():
    from engine import china_intel_analysis
    return china_intel_analysis.build()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
