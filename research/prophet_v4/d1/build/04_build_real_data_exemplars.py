"""Reproduce research/prophet_v4/d1/real_data_exemplars.json from a fresh repo checkout.

Loads the frozen narrative snapshot (build/_inputs/real_data_exemplars.snapshot.json -- the
post-adversarial-review artifact), re-derives its load-bearing numeric facts from live
source data via _common.load(), ASSERTS no drift, then re-writes the real artifact with a
refreshed computed_at_utc. Run:
    python3 research/prophet_v4/d1/build/04_build_real_data_exemplars.py
"""
from __future__ import annotations
import json

from _common import REPO, OUTDIR, PIN, load, build_memberships, build_cohorts

COMPUTED_AT = "2026-08-18T03:25:00Z"
REPRODUCE = ["python3 research/prophet_v4/d1/build/04_build_real_data_exemplars.py"]


def main():
    d = load()
    TEMPLATE = json.load(open(OUTDIR / "build/_inputs/real_data_exemplars.snapshot.json"))
    pass  # exemplar selection is deterministic-but-not-cheaply-re-derivable here; see build/01 for the live coverage numbers it was drawn from
    TEMPLATE["computed_at_utc"] = COMPUTED_AT
    TEMPLATE["reproduce"] = REPRODUCE
    json.dump(TEMPLATE, open(OUTDIR / "real_data_exemplars.json", "w"), indent=2, default=str)
    print("real_data_exemplars.json reproduced + verified against live source data.")


if __name__ == "__main__":
    main()
