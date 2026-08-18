"""Reproduce research/prophet_v4/d1/identity_join_audit.json from a fresh repo checkout.

Loads the frozen narrative snapshot (build/_inputs/identity_join_audit.snapshot.json -- the
post-adversarial-review artifact), re-derives its load-bearing numeric facts from live
source data via _common.load(), ASSERTS no drift, then re-writes the real artifact with a
refreshed computed_at_utc. Run:
    python3 research/prophet_v4/d1/build/02_build_identity_join_audit.py
"""
from __future__ import annotations
import json

from _common import REPO, OUTDIR, PIN, load, build_memberships, build_cohorts

COMPUTED_AT = "2026-08-18T03:25:00Z"
REPRODUCE = ["python3 research/prophet_v4/d1/build/02_build_identity_join_audit.py"]


def main():
    d = load()
    TEMPLATE = json.load(open(OUTDIR / "build/_inputs/identity_join_audit.snapshot.json"))
    live_member = d["tg_edges"][(d["tg_edges"]["type"] == "MEMBER_OF") & (d["tg_edges"]["valid_to"].isna())]
    def live_dsts(tk):
        return sorted(live_member[live_member["src"] == f"co:us:{tk}"]["dst"].tolist())
    for h in TEMPLATE["hostile_cases_found"]:
        tk = h["raw_member"]
        assert live_dsts(tk) == h["chain"]["memberships_live"], f"{tk} live memberships drifted from template"
    finviz_receipt = d["tg_meta"]["local_plane"]["finviz"]["company_resolution"]
    attempted = finviz_receipt["minted_new"] + finviz_receipt["resolved_existing"] + len(finviz_receipt["refused"])
    assert attempted == TEMPLATE["finviz_vintage_resolution_receipt"]["members_attempted"], "finviz attempted count drifted"
    gm_live = d["baskets_membership"]["baskets"]["gold_miners"]
    assert "GOLD" not in [m["ticker"] for m in gm_live["members"]], "H2 regression: GOLD reappeared in live gold_miners members"
    assert any("GOLD" in o for o in gm_live.get("omitted", [])), "H2 regression: GOLD omitted-list note missing"
    hist = d["baskets_history"]
    gm_hist = hist[hist["basket_id"] == "gold_miners"]
    assert "GOLD" in gm_hist["ticker"].values, "H2 regression: membership_history.parquet no longer stale on GOLD (re-verify H2 note still accurate)"
    TEMPLATE["computed_at_utc"] = COMPUTED_AT
    TEMPLATE["reproduce"] = REPRODUCE
    json.dump(TEMPLATE, open(OUTDIR / "identity_join_audit.json", "w"), indent=2, default=str)
    print("identity_join_audit.json reproduced + verified against live source data.")


if __name__ == "__main__":
    main()
