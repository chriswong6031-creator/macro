# Oracle Tier-M — Modern-Regime Evaluation Gate (PRE-REGISTRATION)

**Date frozen:** 2026-07-05 · **Status:** pre-registered BEFORE any Tier-M
compound screening. Thresholds below are FROZEN; changing them after seeing
Tier-M results is p-hacking and is prohibited.

## Why a separate gate

Tier-M (268 subsectors + 40 themes + 46 baskets = 354 nodes) has data only from
**2021** onward (constituent/member-derived; watermarked, NOT survivorship-clean).
The Tier-S promotion gate requires era-consistency across 4 eras anchored on
1999-2014 — **structurally unreachable on Tier-M** (everything falls in the last
~1.5 eras). Without a modern-regime gate, nothing on Tier-M can ever promote.
This gate is the Tier-M analogue: consistency across MODERN sub-periods + a
within-modern out-of-sample split.

## Frozen thresholds (Tier-M promotion / gauntlet PASS)

A Tier-M compound PASSES only if ALL hold on the 63-session horizon:

1. **Coverage:** n >= 100 total entries.
2. **Modern sub-bucket consistency:** same-sign effect_63d in **>= 4 of 5**
   annual buckets — **2021, 2022, 2023, 2024, 2025-26** (2026 partial folded
   into 2025). Buckets with n < 20 are "insufficient" and count as NOT
   consistent (do not get a free pass).
3. **Within-modern OOS:** split at **2023-12-31**. dev = 2021-2023, holdout =
   2024-2026. Holdout effect_63d SAME SIGN as dev, holdout hit_63d >= 0.52,
   holdout n >= 100.
4. **Effect / hit:** |effect_63d| >= 1% OR hit_63d >= 55% (unchanged from Tier-S).
5. **Timing placebo:** real mean_63d > 95th pctile of 500 random-timing draws
   (one-sided p < 0.05), same construction as the Tier-S compound gauntlet.

PASS = (1) ^ (2) ^ (3) ^ (4) ^ (5).

## Standing caveats (do NOT relax)

- Tier-M is **watermarked / not survivorship-clean** (per-member cohesion/breadth/
  turnover legs carry label-survivorship + labels-applied-backward biases; see
  panel manifest `sector_label_caveat`). Any Tier-M PASS is **display-only** and
  carries the watermark caveat — it does NOT license a "validated" claim and is
  a weaker result than a Tier-S full-history pass by construction.
- 2021+-only columns (breadth_50/cohesion/cohesion_chg/turnover_z/cohesion_rebuild)
  are the NATIVE Tier-M signal here (Tier-M is all post-2021), so unlike Tier-S
  they are usable as triggers — but the modern gate's OOS + sub-bucket
  consistency is what guards against overfitting to the short sample.
- A modern-only edge is a BET that the post-2021 microstructure persists; size
  accordingly. This gate establishes it survived within-modern OOS, not that it
  is regime-proof.

## Harness

`scripts/oracle_gauntlet_compound.py --tier m` (tier param + modern-bucket gate
added in Phase 0). Reuses the screener's look-ahead-safe get_entry_dates /
_compute_forward_returns with tier="m".
