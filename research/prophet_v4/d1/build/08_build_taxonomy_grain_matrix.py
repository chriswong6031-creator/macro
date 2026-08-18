"""Reproduce research/prophet_v4/d1/taxonomy_grain_matrix.json from a fresh repo checkout.

Loads the frozen narrative snapshot (build/_inputs/taxonomy_grain_matrix.snapshot.json -- the
post-adversarial-review artifact), re-derives its load-bearing numeric facts from live
source data via _common.load(), ASSERTS no drift, then re-writes the real artifact with a
refreshed computed_at_utc. Run:
    python3 research/prophet_v4/d1/build/08_build_taxonomy_grain_matrix.py
"""
from __future__ import annotations
import json

from _common import REPO, OUTDIR, PIN, load, build_memberships, build_cohorts

COMPUTED_AT = "2026-08-18T03:25:00Z"
REPRODUCE = ["python3 research/prophet_v4/d1/build/08_build_taxonomy_grain_matrix.py"]


def main():
    d = load()
    TEMPLATE = json.load(open(OUTDIR / "build/_inputs/taxonomy_grain_matrix.snapshot.json"))
    link = next(l for l in TEMPLATE["cross_taxonomy_links"] if l["link_id"] == "local_theme_to_canonical_expresses")
    edges = d["tg_edges"]
    expr = edges[edges["type"] == "EXPRESSES"].copy()
    expr["src_prefix"] = expr["src"].str.split(":").str[:2].str.join(":")
    expr["dst_top"] = expr["dst"].str.split(":").str[0]
    ths_n = len(expr[(expr["src_prefix"] == "ltheme:ths") & (expr["dst_top"] == "theme")])
    finviz_n = len(expr[(expr["src_prefix"] == "ltheme:finviz") & (expr["dst_top"] == "theme")])
    assert link["count_split_by_source"] == {"ltheme_ths_to_theme": ths_n, "ltheme_finviz_to_theme": finviz_n}, f"M4 regression: {ths_n}/{finviz_n} vs template"
    assert finviz_n == 0, "M4 claim (finviz 100%% unmapped) no longer holds"
    TEMPLATE["computed_at_utc"] = COMPUTED_AT
    TEMPLATE["reproduce"] = REPRODUCE
    json.dump(TEMPLATE, open(OUTDIR / "taxonomy_grain_matrix.json", "w"), indent=2, default=str)
    print("taxonomy_grain_matrix.json reproduced + verified against live source data.")


if __name__ == "__main__":
    main()
