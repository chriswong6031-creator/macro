"""W8b macro-prior delta printer — ratification evidence for FT-R7 prereg.

Runs theme scoring twice on the CURRENT committed price store (which need not be
today's data — the comparison is purely structural):

  BEFORE: patching _MACRO_PRIOR and _SECTOR_PROXY to the pre-W8b state (dropping the
          five AI-capex entries added in this wave).
  AFTER:  the current module state (W8b entries present).

Prints a per-basket table: basket | score_before | score_after | delta |
reco_before | reco_after | changed.

Include ALL US baskets — not just AI-capex ones — so the operator can see that the
change is narrow and limited to baskets that previously had no macro leg.

Usage:
    python -m scripts.research.w8b_macro_prior_deltas
"""
from __future__ import annotations

import sys
import types

import engine.theme_scoring as ts


# W8b-ADDED baskets (the five new entries) — used to annotate the table.
W8B_BASKETS = {
    "ai_semiconductors", "semicap_equipment", "memory_storage",
    "data_center_power", "nuclear_power",
}

# Pre-W8b snapshot of _MACRO_PRIOR and _SECTOR_PROXY (everything BEFORE this wave).
_PRE_MACRO_PRIOR = {
    "mag7":             {"growth": 0.5, "rates": 0.3, "inflation": -0.1, "riskon": 0.7},
    "ai_infra":         {"growth": 0.7, "rates": 0.2, "inflation": 0.0,  "riskon": 0.8},
    "ai_software":      {"growth": 0.5, "rates": 0.5, "inflation": -0.2, "riskon": 0.7},
    "defense":          {"growth": 0.0, "rates": 0.0, "inflation": 0.3,  "riskon": -0.1},
    "power_grid":       {"growth": 0.3, "rates": 0.4, "inflation": 0.2,  "riskon": 0.1},
    "reshoring":        {"growth": 0.6, "rates": 0.1, "inflation": 0.4,  "riskon": 0.2},
    "regional_banks":   {"growth": 0.5, "rates": -0.3, "inflation": 0.2, "riskon": 0.4},
    "managed_care":     {"growth": -0.3, "rates": 0.1, "inflation": -0.2, "riskon": -0.3},
    "housing":          {"growth": 0.4, "rates": 0.8, "inflation": -0.2, "riskon": 0.3},
    "payments_fintech": {"growth": 0.6, "rates": 0.2, "inflation": -0.1, "riskon": 0.6},
    "energy_complex":   {"growth": 0.3, "rates": -0.1, "inflation": 0.8, "riskon": 0.1},
    "defensives":       {"growth": -0.6, "rates": 0.3, "inflation": -0.1, "riskon": -0.6},
    "travel":           {"growth": 0.7, "rates": 0.1, "inflation": -0.2, "riskon": 0.5},
    "retail":           {"growth": 0.6, "rates": 0.3, "inflation": -0.3, "riskon": 0.5},
    "crypto":           {"growth": 0.3, "rates": 0.4, "inflation": 0.1,  "riskon": 1.0},
}

_PRE_SECTOR_PROXY = {
    "mag7": "XLK", "ai_infra": "SMH", "ai_software": "XLK", "defense": "XLI",
    "power_grid": "XLU", "reshoring": "XLI", "regional_banks": "XLF",
    "managed_care": "XLV", "housing": "XLY", "payments_fintech": "XLF",
    "energy_complex": "XLE", "defensives": "XLP", "travel": "XLY", "retail": "XLY",
}


def _score_with_maps(macro_prior: dict, sector_proxy: dict) -> dict[str, dict] | None:
    """Temporarily patch the module maps and run compute_theme_intel (US only).
    Returns {basket_id: {score, reco}} or None if data unavailable."""
    orig_prior = ts._MACRO_PRIOR
    orig_proxy = ts._SECTOR_PROXY
    # Clear the cache so each run scores fresh with the patched maps.
    ts._SIG_CACHE.clear()
    try:
        ts._MACRO_PRIOR = macro_prior       # type: ignore[attr-defined]
        ts._SECTOR_PROXY = sector_proxy     # type: ignore[attr-defined]
        result = ts.compute_theme_intel(region="us")
    finally:
        ts._MACRO_PRIOR = orig_prior        # type: ignore[attr-defined]
        ts._SECTOR_PROXY = orig_proxy       # type: ignore[attr-defined]
        ts._SIG_CACHE.clear()
    if result is None:
        return None
    return {th["id"]: {"score": th["score"], "reco": th["reco"]} for th in result["themes"]}


def main() -> None:
    print("W8b macro-prior delta table — ratification evidence (FT-R7 prereg)")
    print("=" * 78)
    print()

    before = _score_with_maps(_PRE_MACRO_PRIOR, _PRE_SECTOR_PROXY)
    if before is None:
        print("ERROR: compute_theme_intel returned None — price store unavailable.")
        print("Run this script on a machine with the live data store.")
        sys.exit(1)

    after = _score_with_maps(ts._MACRO_PRIOR, ts._SECTOR_PROXY)
    if after is None:
        print("ERROR: after-state compute_theme_intel returned None.")
        sys.exit(1)

    all_baskets = sorted(set(before) | set(after))

    # Header
    w8b_note = "(*) = W8b new entry"
    col_w = 26
    print(f"{'basket':<{col_w}}  {'score_b':>7}  {'score_a':>7}  {'delta':>6}  "
          f"{'reco_before':<12}  {'reco_after':<12}  {'changed':>7}  {'w8b':>4}")
    print("-" * 100)

    n_changed = 0
    rows = []
    for bid in all_baskets:
        b = before.get(bid)
        a = after.get(bid)
        sb = b["score"] if b else None
        sa = a["score"] if a else None
        rb = b["reco"] if b else "—"
        ra = a["reco"] if a else "—"
        delta = (sa - sb) if (sa is not None and sb is not None) else None
        changed = rb != ra
        if changed:
            n_changed += 1
        is_w8b = bid in W8B_BASKETS
        delta_str = f"{delta:+d}" if delta is not None else "n/a"
        sb_str = str(sb) if sb is not None else "n/a"
        sa_str = str(sa) if sa is not None else "n/a"
        rows.append((bid, sb_str, sa_str, delta_str, rb, ra,
                     "YES" if changed else "no", "*" if is_w8b else ""))
        print(f"{bid:<{col_w}}  {sb_str:>7}  {sa_str:>7}  {delta_str:>6}  "
              f"{rb:<12}  {ra:<12}  {'YES' if changed else 'no':>7}  {'*' if is_w8b else '':>4}")

    print("-" * 100)
    print(f"Baskets scored: {len(all_baskets)}  |  Reco changes: {n_changed}  |  {w8b_note}")
    print()
    print("NOTES:")
    print("  * W8b entries previously had NO macro leg (renormalised out of the composite).")
    print("  * Score deltas arise solely from the macro leg being added (weight 0.18),")
    print("    renormalised over available legs.")
    print("  * Reco changes (if any) reflect the macro gate in _reco() crossing its threshold.")
    print("  * Baskets not in W8B_BASKETS should show delta=0, changed=no (invariance check).")


if __name__ == "__main__":
    main()
