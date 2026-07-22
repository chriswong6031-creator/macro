# Bitcoin strategies (allocation + trend) — Redesign Masterplan (DRAFT)

> AI-drafted (opus) + adversarially reviewed (opus). PENDING operator ratification. Not authority. Any promotion follows the gauntlet.

Citations verified. The key facts hold: `btc_regime.py:1-20` confirms DISPLAY-ONLY + "does NOT beat hand-tuned OOS"; `cycle_clock` at `btc_signals.py:940` is a display tilt with `cycle_len_d` hardcoded; `ath_invalidation_confirmed` exists at `btc_overrides.py:111`; `recommend.py:102` confirms MVRV-Z<0 as the calibrated [BOTTOM] leg with 72% hit. Now producing the masterplan.

---

# MASTERPLAN — Bitcoin Vector (Allocation + Trend) Redesign

*Author: quant strategist lane · adversarially reviewed against `engine/neuralweb/constitution.py` (A7_ORIGINATE) + `research/DO_NOT_REBUILD.md`*

## 1. HONEST REFRAME

The evidence is unambiguous and must drive the copy. `scripts/btc_vector_optimal_phase0.py` / `reports/btc-vector-optimal-phase0.md:42` say it plainly: the surface **survives on drawdown/Sharpe payoff only** (Sharpe 1.43, MaxDD −41.2% vs HODL −83.8% = 2.03× DD cut, DSR 0.9960 at n=50), while **direction is a coin-flip** — P(7d up)=0.578 vs base 0.545. `engine/btc_regime.py:14` independently confirms the macro composite "does NOT beat the hand-tuned allocator OOS." `recommend.py:107` already encodes the honest posture in its docstring: *"Directional conviction only at measured extremes; otherwise drawdown-managed sizing of a long-only BTC sleeve."*

**The TRUE objective of vector_allocation.html and strategy_btc_trend.html is risk/drawdown decision-support for a long-only BTC sleeve — NOT forward-return alpha.** The page must stop implying edge it lacks:

- **Rename the value proposition.** Hero copy must lead with the *earned* claim: "cuts drawdown ~2× versus buy-and-hold" — not "signal," "conviction," or "forecast." The verified deliverable is **survival, not selection.**
- **Demote directional language.** Only the two calibrated legs (MVRV-Z<0 [BOTTOM], reserve_risk>0.02 / mayer>2.4 [TOP], `recommend.py:120-121`) may carry a directional verb. Everything else is **sizing/exposure-band** language. `btc_signals.py:940`'s `cycle_clock` is explicitly "a soft PRIOR… used to tilt, never to trigger" — the copy must match.
- **Kill the alpha halo on btc_strategy.html.** It is a *historical comparison of two rule systems* — frame it as **evidence/education**, not a live edge, with the DSR and per-cycle attribution (`reports/btc-gate-attribution.md`: 2014 gate LOST −4.2%) shown honestly.

This reframe is itself constitution-compliant: it *de-escalates and relabels* (permitted), originates nothing.

## 2. STRUCTURAL FIXES (ship-now tier)

Every fix below is wiring / ruler-choice / promotion / demotion / bugfix of an **existing** key. No new scores.

**F1 — Fix the missing-nav-wrapper menu bug on strategy_btc_trend.html.** `[MECHANICAL]`. `engine/strategies.py` (the `_sc_trend` → 4-band page generated via `scripts/build_strategies.py`) emits the nav without the wrapper other pages use. Copy the byte-identical nav-wrapper markup from a compliant sibling page builder. Closes a live rendering defect. Effect: menu works; zero logic change.

**F2 — Wire the ATH-invalidation falsifier into an allocation path (close W2).** `[JUDGMENT]`. `ath_invalidation_confirmed` (`btc_overrides.py:111`) is computed and *partially* consumed, but `cycle_phase_clock` ATH-invalidation at `btc_signals.py:940-948` is still **DISPLAY-ONLY** — no allocation path reads it (the documented W2 weakness). The fix is pure plumbing: route the already-computed `close`-series falsifier through `apply()`'s existing `ctx["close"]` seam (`btc_overrides.py:340`) so a confirmed structural invalidation can **release the gate** via the Override-Registry — NOT via a human gate in `allocation()` (that pattern is a STANDING KILL). This promotes an existing, overfit-hawk-approved EVENT (`btc_overrides.py:118`, "masterplan §4 N2") from display to a registry release rule. Effect: the gate becomes falsifiable/releasable by structure, not just the calendar. Needs operator sign-off because it changes when real capital re-enters.

**F3 — De-hardcode the cycle clock; anchor to observed halving drift (close W5).** `[JUDGMENT]`. `config.yml:3567` freezes `cycle_len_d`/`up_days=1064`/`down_days=364` while observed halving gaps trend 1319→1402→1440d. This is a **ruler-choice bugfix**, not a new signal: `cycle_clock` (`btc_signals.py:940`) already reads `cfg["halving_dates"]` and `cfg["cycle_len_d"]` — replace the static scalar with the **trailing observed inter-halving median** computed from those same dates (deterministic, zero forward-fit, stays a soft tilt). Closes W5's "static clock vs lengthening cycle" and the "anchored to US election, not halving" defect. Effect: the time-tilt tracks reality; the W4 calendar spine loses its election-calendar contamination.

**F4 — Un-gate the engine's best-validated bottom-buyer from the binary calendar mask (close W3).** `[JUDGMENT]`. W3's binary calendar mask unconditionally zeroes MVRV-Z<0 — the engine's own calibrated [BOTTOM] leg (`recommend.py:120`, "+40%/90d, 72% hit"). The already-built accelerator token `CAUSE_ACCEL_MVRV = "accel_mvrv_z_lt0"` (`btc_overrides.py:97`) exists precisely to let this **pre-committed** signal override the blackout through the Registry. Wire `ctx["mvrv_z"]` (seam already declared, `btc_overrides.py:311`) so a genuine MVRV-Z<0 print accelerates re-entry rather than being masked. Promotion of an existing calibrated key via existing token — no origination. Operator sign-off required (changes capital deployment during blackout).

**F5 — Demote the 11-factor macro regime to a labeled context chip (close a mislabel).** `[MECHANICAL]`. `btc_regime.py:14` already says it failed the kill-test OOS. Ensure NO sizing path reads `regime.exposure` and the page renders it with an explicit "context only — did not beat the allocator OOS" tag. Pure demotion/relabel. Effect: removes any implied authority.

## 3. NEW PREREG RESEARCH BETS (staged tier)

Each is a frozen hypothesis for **nightly/a human to run** — I originate no live score.

**B1 — MVRV-Z<0 as a *sizing multiplier*, not a timer.** *Hypothesis:* the calibrated [BOTTOM] leg improves the drawdown/Sharpe payoff when used to *upsize* an already-long sleeve, even though it fails as a direction timer. *Construction:* frozen — when `mvrv_z<0`, scale `alloc_optimal_raw` by a pre-committed factor k∈{1.25,1.5}; replay via `engine/rule_replay.py` + `scripts/lab_backtest.py`. *Gate:* Sharpe uplift ≥0.15 AND MaxDD not worse, OOS holdout + 2010-break era split + circular-shift null (2000 draws, `oracle_compound_tc_recheck.py`), DSR ≥0.95 (BTC-class), BH-FDR across the family. *Falsifier:* no DD/Sharpe uplift, or uplift dies post-2010-break. *DISTINCT from kills:* this is a *sizing multiplier on an already-calibrated key*, not the REFUTED "election cycle as standalone signal" nor a human-override in `allocation()`.

**B2 — Halving-drift clock as a *confluence confirmer* for the bottom-buyer.** *Hypothesis:* the observed-drift cycle clock (F3) *confirms* MVRV-Z<0 entries (later-cycle bottoms hold better) — a confluence input, never standalone. *Construction:* frozen — flag entries where `days_since_halving` is in the observed-drift trough band AND `mvrv_z<0`; compare hold-180d hit vs MVRV-Z<0 alone. *Data:* in-repo (deterministic clock + CoinMetrics MVRV). *Gate:* hit_180d uplift ≥5pp, n≥4 co-occurrences, DSR ≥0.90. *Falsifier:* clock adds no lift over MVRV-Z alone (then it stays a pure display tilt). *DISTINCT from kills:* the cycle clock is used as a **confluence confirmer**, explicitly the retained role the constitution permits for a non-standalone factor — NOT the killed standalone election/midterm signal.

**B3 — ETH sleeve as its OWN gauntlet subject (repair W4).** *Hypothesis:* post-decontamination ETH has an independent drawdown edge. *Construction:* re-run `eth_vector_phase0.py` with the BTC-gate contamination removed (the DSR 0.9965→0.5345 collapse is the *contaminated* number). *Data:* in-repo. *Gate:* ETH-native DSR ≥0.95 on its own OOS+era split, or it stays display-only. *Falsifier:* DSR <0.95 decontaminated → ETH sleeve is NOT promoted (honest null). *DISTINCT from kills:* not a re-proposal; it's completing an in-flight gauntlet subject with the contamination fixed.

## 4. PROMOTE / DEMOTE LEDGER

**PROMOTE (earned authority, one rung):**
- **Overall allocation sleeve → "drawdown-management, authority-tier"** on the DD/Sharpe claim only (DSR 0.9960, 2.03× DD cut). NOT for direction.
- **MVRV-Z<0 [BOTTOM] leg → registry accelerator** (F4) — already calibrated (72% hit), gauntlet-passed as a bottom marker.
- **ath_invalidation_confirmed → release-rule tier** (F2) — overfit-hawk approved, promote from display to Registry consumer.

**DEMOTE / GATE / RELABEL:**
- **11-factor macro regime → context chip** (F5): failed OOS kill-test (`btc_regime.py:14`).
- **Direction/P(7d up) framing → removed**: 0.578 vs 0.545 base is a coin-flip (`btc-vector-optimal-phase0.md:42`).
- **On-chain DD gate → CONFIRMER-candidate only** (`reports/btc-onchain-dd-phase0.md`, DSR 0.9109 < 0.95 BTC bar) — display + shadow, no standalone authority.
- **U1 SOPR impulse → suppressed** (n=14, auto-zeroed insufficient_n) — keep null printed.
- **Static election-calendar spine → demoted** to a weak US-only Risk-Radar modulator (already the standing-kill disposition).

## 5. SEQUENCING

| Step | Effort | Depends on | Operator sign-off? |
|---|---|---|---|
| F1 nav-wrapper bugfix | S | — | No |
| F5 regime demote/relabel | S | — | No |
| §1 copy reframe (page + hero) | M | designer (opus) | No (design gate) |
| F3 de-hardcode cycle clock | M | — | **Yes** (changes tilt) |
| F2 wire ATH falsifier release | M | F3 | **Yes** (releases gate) |
| F4 un-gate MVRV-Z accelerator | M | F2 seam | **Yes** (capital during blackout) |
| B1/B2/B3 prereg docs (`research/*_PREREG.md`) | M | freeze before any OOS stat | **Yes** (each prereg) |
| B1/B2/B3 gauntlet runs | L | prereg frozen; nightly lane | Yes (promotion) |

Ship F1/F5/copy immediately (no capital impact). F2/F3/F4 are the W2/W3/W5 closures and **must** go through operator sign-off because they change when/how much real capital re-enters during the active midterm blackout override. Prereg docs freeze BEFORE any OOS number is looked at (gauntlet law).

## 6. RISKS / OPEN QUESTIONS

1. **Blackout collision.** F2/F4 create structural release paths that can fire *inside* the active midterm blackout (0% through 2026 election, `btc_overrides.py` W4 spine). Operator must rule: do structural/on-chain releases *override* the calendar blackout, or only *stage* re-entry within it? This is the crux and needs an explicit ruling.
2. **DSR inflation (W6) is unresolved and taints every gate here.** `validation.py:263` treats T=4182 daily returns as independent (~46 effective 90d windows) with no BH-FDR across the 32-family search. Until W6 is fixed, **all** DSR figures (including the 0.9960 headline) may be optimistic — the reframe should say "drawdown edge" cautiously, and B1–B3 gates must apply FDR. Should W6 be a blocking prerequisite before *any* promotion in §4?
3. **n is tiny for the cycle work** (n=3 completed halving cycles). B2's confluence gate needs n≥4 co-occurrences — likely data-blocked until more cycles or intra-cycle bootstrapping is agreed. Flag: **data-blocked**.
4. **F3 changes historical replays.** De-hardcoding `cycle_len_d` shifts the backtest baseline; confirm the operator wants the observed-drift median (vs a frozen "current best estimate") so we don't re-fit the ruler to recent data.

**Key files:** `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/wizardly-poitras-3579e4/engine/btc_signals.py:940` · `engine/btc_overrides.py:97,111,311,340` · `engine/btc_regime.py:14` · `engine/btc_recommend.py:120` · `engine/strategies.py` · `config.yml:3567` · `reports/btc-vector-optimal-phase0.md:42`.

---

## ADVERSARIAL REVIEW

Verified enough. The key tokens (`CAUSE_ACCEL_MVRV`, `TOKEN_CLASS1`, `ath_invalidation_confirmed`), the ctx seams (`mvrv_z`, `close`), the display-only regime honesty block, the `cycle_clock` "tilt never trigger" contract, and the MVRV-Z<0 [BOTTOM] 72% calibration all exist as the masterplan claims. Now the adversarial review.

---

# ADVERSARIAL REVIEW — BTC Vector Redesign Masterplan

**1. A7_ORIGINATE (LLM/engine originating a new score)**

- F1 nav bugfix — **PASS.** Pure markup, no signal.
- F2 wire ATH falsifier — **PASS.** Routes existing `ath_invalidation_confirmed` (`btc_overrides.py:111`, "overfit-hawk approved") through the existing `ctx["close"]` seam (`:340`) into the Registry. Plumbing of a pre-committed event, not origination.
- F3 de-hardcode cycle clock — **FLAG (borderline).** Replacing a frozen `cycle_len_d` with "trailing observed inter-halving median" is a *ruler change on live-consumed config*, and `cycle_clock` currently DOES tilt sizing. Recomputing the anchor from recent data each night is a data-dependent re-fit — exactly the "originate by choosing a moving ruler" failure mode. The masterplan half-sees this (Risk #4) but still tags it a ship-now structural fix. It must ship as **display-only until B2 gauntlets it**, or as a *frozen* "current best estimate" scalar (operator-set, not auto-recomputed). As written it smuggles a self-updating live tilt. Downgrade to display or freeze the value.
- F4 un-gate MVRV-Z — **PASS.** Wires existing `CAUSE_ACCEL_MVRV` token (`:97`) + existing `ctx["mvrv_z"]` seam (`:311`) for an already-calibrated [BOTTOM] leg (`recommend.py:120`). Promotion, not origination.
- F5 demote regime — **PASS.** Relabel/demote, permitted.

**2. KILL COLLISION**

- All F-fixes — **PASS.** None reintroduces the election-cycle-as-standalone or human-gate-in-`allocation()` kills; F2/F4 explicitly route through the Registry (the sanctioned home).
- F3 — **FLAG.** The halving clock is orthogonal to the election kill (good), BUT the *current* gate spine is anchored to the US election calendar. F3 claims to remove that contamination — verify it doesn't leave a residual election anchor. Directionally compliant, needs confirmation in impl.
- B1 (MVRV-Z sizing multiplier) — **PASS.** Sizing multiplier on a calibrated key ≠ standalone timer. Distinct.
- B2 (halving-drift confluence confirmer) — **PASS on framing.** Confluence-confirmer role is the explicitly-permitted retained use for a non-standalone factor. But see #3.
- B3 (ETH own gauntlet) — **PASS.** Completing an in-flight subject post-decontamination, not a re-proposal.

**3. GAUNTLET RIGOR / POWER**

- B1 — **PASS.** Effect (Sharpe ≥0.15, DD-not-worse), OOS, 2010-break era split, circular-shift null via `oracle_compound_tc_recheck.py`, DSR ≥0.95, BH-FDR. Genuinely falsifiable and reuses the mandated tooling.
- B2 — **FLAG (underpowered, self-admitted).** n≥4 co-occurrences of (`days_since_halving` in trough band ∧ `mvrv_z<0`) across **n=3 completed cycles** is not achievable — the masterplan admits "data-blocked" in Risk #3. A gate that cannot be met is not a bet; it's a deferred hypothesis. Acceptable ONLY if explicitly parked as data-blocked-until-cycle-4, which it partially is — but it should NOT sit in the "staged tier / ship" column implying near-term runnability. Also the `cycle_clock` docstring itself says "only n=3 completed cycles" — the confirmer inherits that fragility.
- B3 — **PASS.** Clean binary gate (DSR ≥0.95 decontaminated or stays display), honest null.

**4. WRONG-RULER / OVERFIT**

- **FLAG — the W6 DSR-inflation problem taints B1's own gate.** The masterplan correctly surfaces W6 (`validation.py:263`, T=4182 treated independent, ~46 effective 90d windows, no FDR over the 32-family search) as Risk #2 — but then sets B1's bar at "DSR ≥0.95 (BTC-class)" using the *same inflated estimator*. You cannot gauntlet a new bet on a ruler you've flagged as broken. **W6 must be a hard prerequisite** for any DSR-gated promotion (B1, B3, and the §4 "authority-tier" promotion of the sleeve). The masterplan asks this as an open question rather than ruling it — that's the central rigor gap.
- F3 — **FLAG** (see #1): moving-median ruler is the classic recent-data overfit; will not survive timing-placebo if it's silently absorbing post-2020 cycle lengthening.

**5. CLAIM→WEAKNESS mapping**

- F1→nav bug — **PASS** (matches the stated defect on `strategy_btc_trend.html`).
- F2→W2 — **PASS.** W2 is precisely "falsifier computed but no allocation path consumes it" (`btc_signals.py:940-948`); routing through `apply()` closes it. Correct file/function.
- F3→W5 — **PARTIAL.** Closes the "static clock" defect but introduces the re-fit hazard; net it does address W5's substance if frozen.
- F4→W3 — **PASS.** W3 = binary mask zeroes the calibrated bottom-buyer; `CAUSE_ACCEL_MVRV` is the built accelerator for exactly this. Correct.
- F5→regime mislabel — **PASS.**

**6. WHAT IT MISSED**

- **W6 is diagnosed but left unfixed** — no structural fix targets `validation.py:263` (add FDR / block-bootstrap for autocorrelation / effective-sample correction). Given W6 taints every DSR in the plan, a ship-now **[MECHANICAL/JUDGMENT] fix to the estimator** belongs in §2, not just Risk #2. This is the single biggest omission.
- **`btc_master.py:220` (20 weighted-tanh axes)** and the **8-node tree at `recommend.py:102`** are never audited for whether any *directional* node survives the coin-flip finding. If direction is a coin-flip (P=0.578 vs 0.545), the directional legs of the recommend tree — beyond the two calibrated extremes — should be explicitly demoted in the §4 ledger. Missed.
- **D2 DVOL impulse (p=.0015) and D3 SOPR (p<.01)** from `btc_impulse_radar_backtest` pass their bars but appear nowhere in the promote ledger — a documented survivor left unpromoted while weaker items are discussed.
- **The blackout-collision ruling (Risk #1) is the actual gating decision** and is correctly flagged, but F2/F4 are sequenced to ship *before* that ruling exists — a sequencing inversion.

---

**OVERALL VERDICT = NEEDS-REVISION.**

The reframe (§1), F1/F2/F4/F5, and B1/B3 are constitution-clean and evidence-honest — the plan correctly identifies this as a drawdown tool, not an alpha tool. But it is not ship-ready as staged.

**Single highest-priority correction:** Make the **W6 DSR-estimator fix (`validation.py:263` — FDR across the 32-family search + autocorrelation-corrected effective sample) a blocking prerequisite in §2**, ahead of any DSR-gated promotion. Every headline number in the plan (the 0.9960 sleeve DSR, B1's ≥0.95 bar, B3's decontaminated DSR) rides on an estimator the plan itself flags as inflated — you cannot promote on a ruler you've declared broken. Secondarily, freeze F3's cycle-length scalar (no nightly auto-recompute) until B2 clears, to avoid smuggling a self-updating live tilt past A7.
