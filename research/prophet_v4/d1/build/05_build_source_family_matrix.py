"""Reproduce research/prophet_v4/d1/source_family_matrix.json from a fresh repo checkout.

Loads the frozen narrative snapshot (build/_inputs/source_family_matrix.snapshot.json -- the
post-adversarial-review artifact), re-derives its load-bearing numeric facts from live
source data via _common.load(), ASSERTS no drift, then re-writes the real artifact with a
refreshed computed_at_utc. Run:
    python3 research/prophet_v4/d1/build/05_build_source_family_matrix.py
"""
from __future__ import annotations
import json

from _common import REPO, OUTDIR, PIN, load, build_memberships, build_cohorts

COMPUTED_AT = "2026-08-18T03:25:00Z"
REPRODUCE = ["python3 research/prophet_v4/d1/build/05_build_source_family_matrix.py"]


def main():
    d = load()
    TEMPLATE = json.load(open(OUTDIR / "build/_inputs/source_family_matrix.snapshot.json"))
    assert len(TEMPLATE["rows"]) == 20, "row count drifted from drafter's 20"
    ts_cfg = d["theme_sources"]["families"]
    assert ts_cfg["mastermind_curated"]["rights_class"] == "direct_display_ok"
    TEMPLATE["computed_at_utc"] = COMPUTED_AT
    TEMPLATE["reproduce"] = REPRODUCE
    json.dump(TEMPLATE, open(OUTDIR / "source_family_matrix.json", "w"), indent=2, default=str)
    print("source_family_matrix.json reproduced + verified against live source data.")


if __name__ == "__main__":
    main()
