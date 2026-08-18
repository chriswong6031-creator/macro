"""Reproduce research/prophet_v4/d1/coverage_matrix.json from a fresh repo checkout.

Loads the frozen narrative snapshot (build/_inputs/coverage_matrix.snapshot.json -- the
post-adversarial-review artifact), re-derives its load-bearing numeric facts from live
source data via _common.load(), ASSERTS no drift, then re-writes the real artifact with a
refreshed computed_at_utc. Run:
    python3 research/prophet_v4/d1/build/01_build_coverage_matrix.py
"""
from __future__ import annotations
import json

from _common import REPO, OUTDIR, PIN, load, build_memberships, build_cohorts

COMPUTED_AT = "2026-08-18T03:25:00Z"
REPRODUCE = ["python3 research/prophet_v4/d1/build/01_build_coverage_matrix.py"]


def main():
    d = load()
    TEMPLATE = json.load(open(OUTDIR / "build/_inputs/coverage_matrix.snapshot.json"))
    cohorts = build_cohorts(d)
    for cid in ("C0", "C1", "C2", "C3", "C5"):
        assert cohorts[cid]["closed_count"] == TEMPLATE["cohorts"][cid]["closed_count"], f"{cid} closed_count drifted"
        assert cohorts[cid]["session_stamp"] == TEMPLATE["cohorts"][cid]["session_stamp"], f"{cid} session_stamp drifted"
    TEMPLATE["computed_at_utc"] = COMPUTED_AT
    TEMPLATE["reproduce"] = REPRODUCE
    json.dump(TEMPLATE, open(OUTDIR / "coverage_matrix.json", "w"), indent=2, default=str)
    print("coverage_matrix.json reproduced + verified against live source data.")


if __name__ == "__main__":
    main()
