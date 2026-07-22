# Strategy-redesign drafts × existing programs — reconciliation

**Purpose:** the 4 opus masterplan drafts in this folder were authored from censuses that did not know `research/ENGINE_FIX_MASTERPLAN.md` (53KB, ~2026-07-22) already exists and is executing. This note maps each surface so we **adopt the existing program, contribute only the genuine delta, and never duplicate or collide.** Two of the drafts' "bugs" were already fixed when checked (see §Verify-first). Treat the drafts as idea-generators, not build specs.

## Rule 0 — verify every fix live before building
Census audit docs predate recent fixes. **2 of 2** items spot-checked were already closed:
- China survivorship-deletion → **already append-only** (`collectors/china_universe.py`, `ENGINE_FIX_MASTERPLAN.md §W6-CN`).
- Cross-sectional-momentum kill → **already registered** (`DO_NOT_REBUILD.md:104`).
So: before any structural fix, `grep`/read the live code, and reconcile against `ENGINE_FIX_MASTERPLAN.md` + `docs/ACTIVE_BUILD_MAP.md`.

## US — ADOPT `ENGINE_FIX_MASTERPLAN.md §W6-US` ("Buy Board 2.0"). Delta ≈ 0.
W6-US already specifies the US draft's core moves:
- Draft F1 (stop ranking by negative-IC `bottoming-alignment`) → W6-US "two lanes, variable width; no `entry_open_first` terminal sort, no `potential_score` overwrite, no `ALIGN_MIN_KEEP` backfill."
- Draft F2 (gate the BUY verb) → W6-US "timing gates and badges, never sorts."
- Draft F3 (concentration) / F5 (freshness discriminator) / F6 (regime consolidation) → W6-US hierarchical borrow-strength + Regime One (`§W2`).
- Draft B1 (insider FDR-survivor promotion) → W6-US Q4 "event-stack sparse signals via OR/max (insider / PEAD / 8-K) as a bonus layer."
**Action:** do not open a parallel US lane. If contributing, do it as W6-US tasks (the draft adds no mechanism W6-US lacks). The one thing to carry over: W1c's mandate to **re-issue the −23.7%→−15.5% drawdown claim on the corrected panel**.

## China — ADOPT `ENGINE_FIX_MASTERPLAN.md §W6-CN` ("match product units to validated edges"). Delta ≈ 0.
W6-CN already specifies the China draft's moves: reversal-sleeve as the product unit, grader/ledger truth pass (CN-1), validated-edge wiring + sign flips (CN-3), leakage/data-plane integrity (CN-2), and the standing caution that **subsector-state gates HURT A-share reversal** (the draft's ruler point). Survivorship already fixed (§W6-CN). **Action:** contribute as W6-CN tasks; the draft's Fix-4 (survivorship) is closed — drop it.

## BTC — NOT in `ENGINE_FIX`. Reconcile against its OWN lineage before any build.
BTC has a separate program: `BTC_VECTOR_FIX_MASTERPLAN.md` + `BTC_VECTOR_PROBLEM_AUDIT_FOR_FABLE.md` + the Override-Registry W-work (W1/W2 partly shipped — `ath_invalidation_confirmed` in `btc_overrides.py:111`). The draft's items (W6 DSR-independence must precede promotion; W5 cycle-clock → halving-drift, frozen scalar to stay A7-clean; honest "sizing not direction" reframe) are from that audit. **Action:** verify what's already shipped there; the likely genuine-open, low-risk delta = the **honest display reframe** of `vector_allocation.html` copy ("sizing/drawdown tool, not a direction call") — a display-tier fix, not an engine change.

## Commodities — NOT in `ENGINE_FIX`. This is the genuine open lane = where redesign work lands.
No existing masterplan covers it. Contributions this session:
- **[#3206] honest active-model verdicts** — copper (DSR 0.745 FAIL) / silver (0.919 MARGINAL) no longer claim "genuine alpha". MERGED.
- **stale caveat fix** — "full Phase-0 a fast-follow" → Phase-0 complete (this PR).
- **`COMMODITY_C1R2_OIL_XEG_PREREG.md`** — the new-alpha bet: oil→XEG as a single confirmatory prereg (n_trials=1, OOS), correcting R1's finding that *multiplicity, not sample size,* binds. Interim = display-tier context chip.
- **Flagged for OPERATOR (LLM may not escalate):** gold active passed its gauntlet (DSR 0.958 ≥ 0.95) and is still shown "experimental" — a promotion candidate, but that escalation is an operator/nightly action, not an LLM edit.

## Net
US/China → feed `ENGINE_FIX_MASTERPLAN.md`; BTC → feed its own program (display reframe likely the open delta); **Commodities → the active independent lane.** Every item verified live first.
