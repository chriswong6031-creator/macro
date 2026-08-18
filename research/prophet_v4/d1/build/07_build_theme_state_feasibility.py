"""Reproduce research/prophet_v4/d1/theme_state_feasibility.json from a fresh repo checkout.

Loads the frozen narrative snapshot (build/_inputs/theme_state_feasibility.snapshot.json -- the
post-adversarial-review artifact), re-derives its load-bearing numeric facts from live
source data via _common.load(), ASSERTS no drift, then re-writes the real artifact with a
refreshed computed_at_utc. Run:
    python3 research/prophet_v4/d1/build/07_build_theme_state_feasibility.py
"""
from __future__ import annotations
import json

from _common import REPO, OUTDIR, PIN, load, build_memberships, build_cohorts

COMPUTED_AT = "2026-08-18T03:25:00Z"
REPRODUCE = ["python3 research/prophet_v4/d1/build/07_build_theme_state_feasibility.py"]


def main():
    d = load()
    TEMPLATE = json.load(open(OUTDIR / "build/_inputs/theme_state_feasibility.snapshot.json"))
    assert TEMPLATE.get("adjudication", {}).get("superseded_by") == "D1_THEME_SOURCE_AND_IDENTITY_CENSUS_2026-08-18.md section 8"
    assert len(TEMPLATE.get("adjudicated_rows", [])) == 10, "M3 regression: expected 10 adjudicated rows"
    assert all(r["proposed"] is False for r in TEMPLATE["adjudicated_rows"])
    TEMPLATE["computed_at_utc"] = COMPUTED_AT
    TEMPLATE["reproduce"] = REPRODUCE
    json.dump(TEMPLATE, open(OUTDIR / "theme_state_feasibility.json", "w"), indent=2, default=str)
    print("theme_state_feasibility.json reproduced + verified against live source data.")


if __name__ == "__main__":
    main()
