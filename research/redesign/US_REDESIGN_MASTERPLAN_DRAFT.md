# US dashboard strategy — Redesign Masterplan (DRAFT)

> AI-drafted (opus) + adversarially reviewed (opus). PENDING operator ratification. Not authority. Any promotion follows the gauntlet.

All claims verified against source. I have what I need. Writing the masterplan now.

---

# US Dashboard Strategy Redesign — MASTERPLAN

*Author: quant strategist. Adversarial-review posture: every structural fix is wiring/ruler/promotion/demotion/bugfix of an existing key; every research bet is a frozen pre-registration distinct from a standing kill. Cited to file:line.*

## 1. HONEST REFRAME

The evidence is unambiguous and the surface's own code already says it. On the deep+PIT survivorship-clean panel (2008–2025, 210 rebalances, ~419 names) **every composite FAILS the DSR haircut at 63d** — the best (regime·PEAD) is IC +0.021, Sharpe 0.07, DSR far under 0.90; the shipped baseline `selection` is IC +0.0086, Sharpe **−0.16** (`reports/stock-conviction-phase0.md`, PRIMARY table). Only insider net-buying is a borderline FDR survivor (`stock_score.py:88-93`), and it is present on ~2 of 34 live buy rows. The confluence gate is explicitly a **drawdown tool**, not alpha: it cut avg maxDD −23.7%→−15.5% across 110 held-out names (`signal_quality.py:5-7`, `signal_gate.py:10-11`).

So the TRUE objective of the US board is **entry-quality / drawdown decision-support** — "if you are going to hold this name, is now a low-drawdown moment, and is the tape hostile?" — NOT forward-return stock selection. This is the one thing the machinery has out-of-sample evidence for.

The framing must change to stop implying alpha it lacks:
- **Retire the fixed-width "34 BUYs — act now" imperative board.** It is the root cause: it forces `rank_by="bottoming-alignment"` (the only key loose enough to fill 34 slots, `build_stock_library.py:1594`) and the `potential_score` overwrite of the honest edge percentile (`US_STOCKS_ENGINE_PROBLEMS_FOR_FABLE.md:20-27`). Width and label strength must be **functions of measured edge**, with abstention allowed.
- **Reserve the word "BUY" for the FDR-surviving subset** (insider-present names). Everything else is a **watch/entry-quality** card: "strong name, hostile tape" / "basing" / "no clear edge."
- **Copy law (per DESIGN_DOCTRINE + glance tier):** the headline states *stance* ("Watch — don't chase", "Lower-drawdown entry window") not a fabricated conviction verb. The macro_context footer already models the honest disclosure — "No label on this page has been calibrated for forward return" (`macro_context.html.j2:1287`); the stock board needs the same Tier-2 receipt.

Plainly: **there is no cross-sectional alpha here. Make it the best risk / entry-quality tool it can be, and stop it from printing "BUY" on 34 coin-flips.**

## 2. STRUCTURAL FIXES (ship-now tier)

All are wiring/ruler/demotion of existing keys. Prioritized by leverage.

**F1 — Rank the board by the surviving leg, not the negative-IC timing key. [JUDGMENT]**
`build_stock_library.py:1594` ranks by `bottoming-alignment`; live `corr(board_position, alpha)=+0.266` (higher-alpha names sit LOWER) and `potential_score` corr −0.31 (`US_STOCKS_ENGINE_PROBLEMS_FOR_FABLE.md:13-27`). The sibling `setups.json` already ranks by `alpha` (its L1519). **Change:** switch the board rank key to the same insider→revisions→SUE edge ordering the engine validated (`stock_score.py:88` `_EDGE_W`), and stop overwriting the honest `rank_pctile` with `potential_score` in the displayed score field. Closes W1. Effect: displayed order stops inverting the one positive-IC leg. JUDGMENT because it changes the product's central promise and needs operator sign-off on abstention.

**F2 — Make the BUY headline a function of the gate, not a static dict lookup. [MECHANICAL]**
The `state/label/urgency` fields come from a static cycle-dict (`cycles.py:429-435`) that no confirmer can downgrade: 34/34 rows are `neutral_ic`, 15/34 signal-quality=block, yet all print "FRESH BUY / now" (`US_STOCKS_ENGINE_PROBLEMS_FOR_FABLE.md:28-33`). **Change:** wire the existing `signal_gate.gate` verdict as a hard arbiter over the headline verb — if `tier != take` OR `validation_status==neutral_ic`, the verb cannot read "BUY/Add" (the `stock_score.py:24-25` "strong name, wrong tape" path already exists; wire it into the row label emitter). Closes W2. Fully specifiable spec → MECHANICAL.

**F3 — Move the per-sector cap to the board strip. [MECHANICAL]**
56% of buys are Utilities+Industrials, effective N≈2-3 (`US_STOCKS_ENGINE_PROBLEMS_FOR_FABLE.md`, problem 4). The cap exists but is wired to the wrong strip. **Change:** apply the existing per-sector cap (12, disclosed) to the `us_standouts.json` board build path in `build_stock_library.py`, not just `setups.json`. Closes W3 concentration. MECHANICAL.

**F4 — Wire the three LEADING signals into the risk gauges as display-tier leading context. [JUDGMENT]**
GEX/`market_gamma`, cross-asset absorption (97th pctile, `cross_asset.verdict="concentrated"`), and breadth divergence are all computed but firewalled from the five gauges, which fire only after VIX>30 / dd<−10% (`RISK_FLIP_2026-06-22.md:80-109`). **Change:** these are ALREADY-CALIBRATED keys (Kritzman-Page absorption has its own evidence string); PROMOTE them to a *display-tier leading-risk row* alongside the coincident gauges, clearly labeled "leading, not gauntleted for magnitude." Add the `asof`-age stamp `latest.json` lacked (`RISK_FLIP:100-108`). Closes W4. JUDGMENT: gauge redesign is user-facing design; must not fuse them into one score (that is the FORBIDDEN FUSION kill — see §6).

**F5 — Wire the price-extension discriminator into the freshness gate. [MECHANICAL]**
`FRESH_TICKS=2` (`confluence_tiers.py:44`) can't tell "based-and-coiled-late" from "blasted-off-late"; the discriminator (realized price extension since the cross + overbought state) is measurable but unwired (`BASING_...AUDIT_FOR_FABLE.md:14-27`). **Change:** allow >2-tick names back into eligibility ONLY when extension-since-cross is below a frozen threshold AND `not_topped` holds — a bug/ruler fix, not a new signal (extension is already computed for the topped-veto). Closes W5. MECHANICAL given a frozen threshold from operator; ship as display-tier "still-basing" chip, gauntlet later (see B2).

**F6 — Retire the dead first-gen regime engine driving the sector gate; use one PIT-causal read. [JUDGMENT]**
Five forked region engines + non-causal HMM smoothing + a dead first-gen engine still gate sector conviction (`REGIME_V2_PIT_DIVERGENCE_AUDIT.md:9-16`, `ENGINE_PROBLEM_AUDIT.md:19-29`). **Change:** delete the dead engine, route the sector gate to the single PIT-causal `regime.py` read, remove look-ahead smoothing. Bugfix/consolidation. Closes W6. JUDGMENT: touches the regime state machine feeding multiple surfaces.

## 3. NEW PREREG RESEARCH BETS

**B1 — Insider-cluster conviction leg (the lone survivor, promoted correctly).**
*Hypothesis:* cross-sectional insider net-buying intensity, restricted to open-market cluster buys, ranks 63d forward returns with positive IC that survives OOS + FDR. *Construction:* frozen z of insider net-buy value/float, cluster≥2 insiders, 63d horizon, sector-neutral; reuse `scripts/backtest_strategies.py` + `gate0_survivorship.py` (PIT membership). *Data:* insider feed already in-engine. *Gate:* IC≥+0.02, L/S Sharpe≥0.3, DSR≥0.90, BH-FDR across the axis family, split-half same-sign. *Falsifier:* DSR<0.90 or sign flip across the 2010 break → stays display-only. *OOS/era:* pre-2010 vs post-2010 + circular-shift null (2000 draws) via `oracle_compound_tc_recheck.py`. **DISTINCT from kills:** insider is NOT any of DOI/signed-charm/washout/margin — it is the one leg the Phase-0 report flags as borderline-FDR-surviving (`stock_score.py:88`); this promotes an existing key through the gauntlet, not a new construction.

**B2 — Post-confluence basing continuation (drawdown, not alpha).**
*Hypothesis:* names 3–6 ticks past a confluence cross with LOW price extension have entry-quality (lower forward maxDD) comparable to fresh crosses. *Construction:* frozen extension threshold, `not_topped`, measure forward maxDD not return; reuse `signal_quality.analyze` + `rule_replay.py`. *Data:* available. *Gate:* maxDD reduction ≥ the −23.7→−15.5 baseline delta, n≥80 held-out, DSR≥0.90 on the drawdown metric. *Falsifier:* basing bucket maxDD ≥ topped bucket → keep FRESH_TICKS=2. *OOS/era:* US-only, 2010 split. **DISTINCT from kills:** this is a *drawdown* discriminator inside an already-validated risk gate, NOT the KILLED Stage-2 win-rate gate and NOT the DON'T-TEST rotation×cycle entry-confluence — it never claims forward alpha.

**B3 — Leading-risk composite as a DISPLAY early-warning (not an allocation surface).**
*Hypothesis:* GEX + absorption-pctile + breadth-divergence, as an ordinal display flag (not a fused score, not an ETF weight), leads the coincident gauges by ≥3 sessions into drawdowns. *Construction:* each leg frozen, combined only as "how many of 3 are lit" ordinal; validate lead-time via `risk_radar_backtest.py`. *Data:* all three computed live. *Gate:* median lead ≥3 sessions, hit-rate on ≥−5% SPY events ≥0.6, n≥15 events, timing placebo passes. *Falsifier:* lead ≤0 or placebo-indistinguishable → stays a plain display row. **DISTINCT from FORBIDDEN FUSION MSP-R2:** that kill forbids fusing gamma/vol/flow/breadth into an *ETF allocation surface with a single composite score*. B3 produces NO allocation, NO single score, NO weights — an ordinal count-of-lit-flags display flag validated only for *lead-time on a risk event*. If review still reads it as fusion, ship the three legs as separate rows (F4) and drop the ordinal.

## 4. PROMOTE / DEMOTE LEDGER

**Promote (earned or gauntlet-candidate):**
- Insider net-buying → board rank key + BUY-reservation gate (borderline FDR survivor; gauntlet via B1 before authority above display).
- Confluence gate → confirmed as the board's PRIMARY *entry-quality/risk* authority (already OOS-validated for drawdown, `signal_quality.py:5-7`) — promote its verdict to arbiter of the headline verb (F2).

**Demote / gate / relabel:**
- `bottoming-alignment` as the board RANK key → DEMOTE to display badge (negative/zero forward IC, `build_stock_library.py:1594`; W1). Kept as a display confluence, never the sort.
- `potential_score` as the displayed SCORE → DEMOTE; restore honest `rank_pctile` (corr −0.31 with the one edge leg).
- Static cycle-dict "FRESH BUY" headline → GATE behind F2 (immune-to-confirmers, W2).
- Tailwind axis → already correctly 0.0 for US (`stock_score.py:207`, W9-B demote); keep display-only.
- `gate_go` DSR≥0.90 badge on large-cap L/S → RELABEL: it is mathematically unreachable on this asset class and prints a constant `neutral_ic`, discriminating nothing (`US_STOCKS...:33`). Re-scope the trust badge to the *drawdown* metric the gate can actually earn.

## 5. SEQUENCING

1. **F2 (S, MECHANICAL)** — headline-verb gate. No dependency. Ship first: stops the most dangerous dishonesty (BUY on blocked names).
2. **F3 (S, MECHANICAL)** — sector cap to board strip. Independent.
3. **F1 (M, JUDGMENT)** — rank-key switch + abstention. **Needs operator sign-off** (kills fixed-width board). Depends on F2 landing (verb gate must exist before variable-width labels).
4. **F5 (M, MECHANICAL)** — basing discriminator, display-tier. Needs a frozen threshold from operator/B2.
5. **F4 (M, JUDGMENT, designer)** — leading-risk display row + asof stamp. User-facing → `designer`. Depends on nothing but must NOT fuse.
6. **F6 (L, JUDGMENT)** — regime engine consolidation. Largest blast radius; schedule last, verify each downstream surface.
7. **B1/B2/B3 (research, nightly lane)** — pre-register (`research/*_PREREG.md`) BEFORE any OOS stat; forward ledgers advance only in nightly. B1 first (highest-value promotion).

Operator sign-off gates: F1 (product promise), F4/F6 (design + regime), and all three PREREG freezes.

## 6. RISKS / OPEN QUESTIONS

- **F1 is a product-identity change.** A variable-width, abstention-allowed board that sometimes says "no clean US entries today" is honest but commercially quieter than "34 BUYs." Operator call.
- **B3 vs FORBIDDEN FUSION.** I have framed it as an ordinal display flag with no score/allocation, but this is the highest adversarial-risk bet. If review rejects it, F4 (three separate rows) still delivers the leading-risk value without any composite. Recommend shipping F4 regardless and treating B3 as optional.
- **`gate_go` unreachability.** If DSR≥0.90 on large-cap monthly L/S is genuinely unreachable (the report says the honest steady state is NEUTRAL), should the surface ever carry a "validated" alpha badge at all? My recommendation: no — retire the alpha-validated badge, keep only the drawdown-validated one. Confirm.
- **F5 threshold origin.** Extension threshold must come from B2's frozen prereg, not be hand-tuned into the live gate (A7_ORIGINATE ban). Until B2 clears, F5 ships display-only.
- **`check_validated_claims.py`** will (correctly) block any copy that says "validated" on the alpha framing — plan copy around it.

---

**Key files:** `engine/stock_score.py:88,207` (weights/demote); `engine/signal_gate.py:10-11`, `engine/signal_quality.py:5-7` (drawdown-tool framing); `engine/cycles.py:429-435` (static headline, W2); `engine/confluence_tiers.py:44` (freshness, W5); `scripts/build_stock_library.py:1594` (board rank key, W1/W3); `reports/stock-conviction-phase0.md` (all-fail-DSR backtest); `research/US_STOCKS_ENGINE_PROBLEMS_FOR_FABLE.md:13-33`, `research/RISK_FLIP_2026-06-22.md:80-109`, `research/BASING_AFTER_CONFLUENCE_PROBLEM_AUDIT_FOR_FABLE.md:14-27`, `research/REGIME_V2_PIT_DIVERGENCE_AUDIT.md:9-16`.

---

## ADVERSARIAL REVIEW

All key claims verify against source. The masterplan is faithfully cited. I have what I need for the review.

---

# ADVERSARIAL REVIEW — US Dashboard Strategy Redesign Masterplan

**1. A7_ORIGINATE (new-signal smuggling)**
- F1 rank-key switch → **PASS.** Reuses existing `_EDGE_W` ordering (`stock_score.py:93`, verified); reordering by an existing key, no origination.
- F2 headline-verb gate → **PASS.** Wires existing `signal_gate.gate` verdict as arbiter; the "strong name, wrong tape" path already exists.
- F3 sector cap → **PASS.** Applies an existing cap to a second strip. Pure plumbing.
- F4 leading-risk row → **FLAG (soft).** GEX/absorption/breadth are computed keys, but the masterplan calls absorption "already-calibrated" — it is calibrated for *literature lead-time* (Kritzman-Page), NOT gauntleted on THIS surface. Promoting to a labeled *display* row is legal (display ships freely); the wording "ALREADY-CALIBRATED" overstates. Keep display-tier + "not gauntleted for magnitude" label as written — then it passes.
- F5 extension discriminator → **PASS, conditional.** Extension is already computed for the topped-veto; re-using it as an eligibility ruler is a bugfix. BUT the threshold must not be hand-tuned (masterplan concedes this in §6/F5). As long as the threshold comes from B2's freeze, PASS.
- F6 regime consolidation → **PASS.** Deletion/routing bugfix.

**2. KILL COLLISION**
- F4 / B3 vs **FORBIDDEN FUSION MSP-R2** → **FLAG (highest risk, correctly self-flagged).** The kill forbids fusing gamma/vol/flow/breadth into an allocation surface with a composite score. B3's "count-of-lit-flags ordinal" is a weak composite. The masterplan's escape hatch (ship F4 as three separate rows, drop the ordinal if challenged) is the right call — **but an ordinal count IS a fused score for the purpose of the kill.** Recommendation stands: ship F4 (separate rows), treat B3 ordinal as rejected-by-default. Do not let the ordinal reach an allocation/weight — it never does here, so the kill is respected only if B3 stays a *risk-event lead-time* flag and never touches ETF weights.
- B1 insider vs kills → **PASS.** Insider net-buying is not DOI/signed-charm/washout/margin; it is the lone FDR survivor (`stock_score.py:88`, verified). Distinct.
- B2 basing vs **Stage-2 win-rate KILL** and **rotation×cycle DON'T-TEST** → **PASS.** B2 measures forward *maxDD* inside an already-validated risk gate, not win-rate or forward return. Genuinely distinct.
- F1 abstention/variable-width board → **PASS.** No collision; it retires a product shape, proposes no killed construction.

**3. GAUNTLET RIGOR**
- B1 → **PASS.** Effect (IC≥.02, Sharpe≥.3), DSR≥.90, BH-FDR, split-half, 2010 era split, circular-shift null all present. Falsifiable.
- B2 → **FLAG (underpowered risk).** Gate "n≥80 held-out" for a maxDD-reduction bet is thin once you subset to "3–6 ticks past cross AND low extension AND not_topped" — that intersection could collapse to n<30. Add a minimum-n *per era* pre-registration or state data-blocked. As written it risks dying underpowered.
- B3 → **FLAG (underpowered + wrong).** "n≥15 events" of ≥−5% SPY drawdowns is borderline; "median lead ≥3 sessions" on 15 events is fragile to one or two events. This is the classic timing-placebo casualty. Plus the fusion concern (item 2). Downgrade B3 to optional as the masterplan already recommends.

**4. WRONG-RULER / OVERFIT**
- B1 uses the right ruler (63d forward, sector-neutral, insider-restricted) → **PASS.**
- B2 correctly uses maxDD not return (matches the gate's validated metric) → **PASS on ruler**, FLAG on power (above).
- B3 → **FLAG.** Lead-time on rare tail events is exactly the construction that dies on the circular-shift null. The masterplan names the risk but does not size it away.

**5. CLAIM→WEAKNESS closure**
- F1→W1: **PASS.** `build_stock_library.py:1594` is the board rank key; setups already ranks alpha. Correct target.
- F2→W2: **PASS.** But NOTE: the audit says the static headline lives in the *cycle-dict + a HWM/TIMING code path running parallel to the EDGE path* (`build_stock_library.py`, "two code paths never reconcile"), not solely `cycles.py:429-435`. F2 must gate the *emitter that merges both paths*, not just `cycles.py`. **FLAG: cite the reconciliation site, not only the dict.**
- F3→W3: **PASS.** Cap exists, wired to wrong strip (verified audit problem 4).
- F4→W4: **PASS.** Firewall confirmed (`RISK_FLIP:88-95`).
- F5→W5: **PASS.**
- F6→W6: **PASS.**

**6. WHAT THE MASTERPLAN MISSED**
- **`entry_open_first` #1-float hack (`build_stock_library.py:1616`)** — the audit names it as a distinct pathology ("something must be #1"). F1 kills width but does not explicitly retire the float-to-#1 override. Add a demotion line.
- **`potential_score` overwrite site is `:1457-1459`**, not just the rank line — the masterplan's demote ledger says "restore `rank_pctile`" but gives no file:line for the overwrite. Cite it so a builder can find it.
- **Staleness / asof-age (`RISK_FLIP §3`)**: F4 mentions the asof stamp, but the *build cadence* blind window (stale Thursday read as live Monday) is a separate fix — surface a freshness guard on `latest.json`, not just a display stamp.

**OVERALL VERDICT = NEEDS-REVISION** (minor; structurally sound, honest reframe is correct and evidence-backed).

**Highest-priority correction:** F2's target citation is incomplete — the "BUY-headline-immune-to-gates" bug lives in the **two parallel TIMING vs EDGE code paths that never reconcile in the row emitter** (`build_stock_library.py`), not only the `cycles.py:429-435` dict. A builder handed the current spec will gate the dict and leave the HWM/`entry_open_first` path still floating "BUY/now" onto blocked names. Re-scope F2 to gate the reconciliation/emit site, and add the `entry_open_first` (`:1616`) and `potential_score` overwrite (`:1457-1459`) demotions explicitly to the ledger.
