"""Regenerate the portfolio-brief golden files from the test fixtures.

Portfolio-Aware W1. The golden briefs at tests/golden/portfolio_brief/<book>.json are
the byte-exact expected output of compose_brief for the charter's 3 synthetic books,
with fixed today/generated_at. This script re-derives them from the SAME fixtures the
test uses (tests/test_portfolio_brief.py::_ctx + BOOKS), so a golden can never drift
from the fixture it is meant to lock. Run after an INTENTIONAL composer change:

    python scripts/_regen_portfolio_brief_goldens.py

Never run it to paper over an UNexpected diff — inspect the diff first.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.test_portfolio_brief import BOOKS, GOLDEN_DIR, _compose  # noqa: E402


def main() -> int:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    for book in sorted(BOOKS):
        brief = _compose(book)
        out = GOLDEN_DIR / f"{book}.json"
        # Pretty, sorted, trailing newline — readable in review; the test compares via a
        # canonical sort_keys dump so formatting here is cosmetic.
        out.write_text(
            json.dumps(brief, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8")
        print(f"wrote {out.relative_to(ROOT)} ({len(brief.get('sections', []))} sections)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
