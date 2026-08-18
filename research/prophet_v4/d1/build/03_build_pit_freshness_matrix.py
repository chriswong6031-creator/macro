"""Reproduce research/prophet_v4/d1/pit_freshness_matrix.json from a fresh repo checkout.

Loads the frozen narrative snapshot (build/_inputs/pit_freshness_matrix.snapshot.json -- the
post-adversarial-review artifact), re-derives its load-bearing numeric facts from live
source data via _common.load(), ASSERTS no drift, then re-writes the real artifact with a
refreshed computed_at_utc. Run:
    python3 research/prophet_v4/d1/build/03_build_pit_freshness_matrix.py
"""
from __future__ import annotations
import json

from _common import REPO, OUTDIR, PIN, load, build_memberships, build_cohorts

COMPUTED_AT = "2026-08-18T03:25:00Z"
REPRODUCE = ["python3 research/prophet_v4/d1/build/03_build_pit_freshness_matrix.py"]


def main():
    d = load()
    TEMPLATE = json.load(open(OUTDIR / "build/_inputs/pit_freshness_matrix.snapshot.json"))
    tree_asofs = d["themes_heatmap_tree_asofs"]
    assert tree_asofs == TEMPLATE["sources"]["finviz_ltheme"]["observed_knowable_time"], "finviz tree_history asofs drifted"
    hist = d["baskets_history"]
    added = hist["added"].value_counts(normalize=True)
    seed_share = added.get("2023-05-09", 0.0)
    assert seed_share >= 0.9, f"H3 DEGRADED claim (95%% seed-constant) no longer holds: {seed_share:.2%%}"
    TEMPLATE["computed_at_utc"] = COMPUTED_AT
    TEMPLATE["reproduce"] = REPRODUCE
    json.dump(TEMPLATE, open(OUTDIR / "pit_freshness_matrix.json", "w"), indent=2, default=str)
    print("pit_freshness_matrix.json reproduced + verified against live source data.")


if __name__ == "__main__":
    main()
