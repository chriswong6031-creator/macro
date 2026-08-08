"""Earnings release binding — Wave 1B of the Company Event Intelligence suite.

Two jobs, both deterministic and both ``context_only``:

1. **Identity.** ``filing_key`` implements the frozen canonical filing key
   ``(cik, accession)`` (research/EARNINGS_WAVE1_CONTRACT_FREEZE_2026-08-06.md
   Q2) and the exact join between the two EDGAR readers that previously shared
   only ``ticker``.  The join has NO date tolerance, by construction.

2. **Binding.** ``binding`` turns a supplied Exhibit 99.1 body into an event
   document with byte-replayable span receipts, reusing
   ``engine.fundamental_forensics.disclosure_diff`` as the source-coordinate
   engine rather than writing a second filing parser.

Nothing here ranks, sizes, gates, escalates, or calls a model.  A number
without basis, units, period, and source is emitted as a **typed absence** —
never as a guess and never as a null that reads as zero.
"""
from __future__ import annotations

AUTHORITY = "context_only"

__all__ = ["AUTHORITY"]
