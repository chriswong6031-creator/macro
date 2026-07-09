"""TIL producer stub — unblocks the synapse-registry gate after PR #1993.

PR #1993 (TIL PR-0) pre-registered foresight-earliness-grades,
theme-placebo-tape, and qledger-falsifier-evaluations with this script as
producer before the producer lanes landed (its own pull_request CI was
suppressed by the conflicting-PR failure mode, so the missing-producer
violation reached main and hard-fails check_synapse_registry for every PR).

This stub keeps the registry honest (the declared producer path exists) and
does nothing. The real implementation lands in the TIL W1/W2/W3/W6 producer
lanes and replaces this file wholesale.
"""
from __future__ import annotations

import sys


def main() -> int:
    print("grade_thematic: stub producer (TIL PR-0 pre-registration) — no-op; "
          "real implementation lands in the TIL producer lanes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
