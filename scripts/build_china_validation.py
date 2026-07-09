"""Run China predictive-validation scorecard → data/china_validation/scorecard.json.

Thin runner for engine.china_validation.validate_all(). Extracted from the
build_china.py inline importlib chain (CN-SYS W5a) so per-step timing is visible
in asia-close.yml and the validation scorecard always lands even if the main
china dashboard render fails.

CONTEXT-ONLY · non-fatal · no edge promotion here.
See research/CHINA_INTEL_POWERHOUSE.md §1.1 and the masterplan §4 CN-SYS-R1.
"""
from __future__ import annotations

import logging


def build() -> dict | None:
    """Run validate_all() and return the scorecard dict. Never raises."""
    try:
        from engine import china_validation
        return china_validation.validate_all()
    except Exception as e:  # noqa: BLE001 — display-tier, additive
        logging.getLogger(__name__).error("china_validation.validate_all failed (%s); skipping", e)
        return None


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
