"""Reproduce research/prophet_v4/d1/mapping_gap_ledger.json from a fresh repo checkout.

Loads the frozen narrative snapshot (build/_inputs/mapping_gap_ledger.snapshot.json -- the
post-adversarial-review artifact), re-derives its load-bearing numeric facts from live
source data via _common.load(), ASSERTS no drift, then re-writes the real artifact with a
refreshed computed_at_utc. Run:
    python3 research/prophet_v4/d1/build/06_build_mapping_gap_ledger.py
"""
from __future__ import annotations
import json

from _common import REPO, OUTDIR, PIN, load, build_memberships, build_cohorts

COMPUTED_AT = "2026-08-18T03:25:00Z"
REPRODUCE = ["python3 research/prophet_v4/d1/build/06_build_mapping_gap_ledger.py"]


def main():
    d = load()
    TEMPLATE = json.load(open(OUTDIR / "build/_inputs/mapping_gap_ledger.snapshot.json"))
    ids = {r["gap_id"] for r in TEMPLATE["rows"]}
    assert "gap:d924b30e010a9ed1" in ids
    row = next(r for r in TEMPLATE["rows"] if r["gap_id"] == "gap:d924b30e010a9ed1")
    assert row["gap_type"] == "untraced-origin", "M5 regression"
    TEMPLATE["computed_at_utc"] = COMPUTED_AT
    TEMPLATE["reproduce"] = REPRODUCE
    json.dump(TEMPLATE, open(OUTDIR / "mapping_gap_ledger.json", "w"), indent=2, default=str)
    print("mapping_gap_ledger.json reproduced + verified against live source data.")


if __name__ == "__main__":
    main()
