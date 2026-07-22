# Commodity strategies — Redesign Masterplan (DRAFT)

> AI-drafted (opus) + adversarially reviewed (opus). PENDING operator ratification. Not authority. Any promotion follows the gauntlet.

All claims verified. The "validated" word in `commodity_carry_context.py:1,7,19,32` is a live CI-law concern (`scripts/check_validated_claims.py`), and section 2 (line 58) of DO_NOT_REBUILD is the correct home for the xsec-mom kill row. I have everything needed.

---

# MASTERPLAN — Commodity Strategies Surface Redesign

*Author: senior quant strategist · 2026-07-22 · adversarially-reviewed draft*
*Scope: `commodities.html` (`scripts/build_commodities.py`), `commodity_strategies.html` (`scripts/build_commodity_strategies.py`), engines `active_commodity.py`, `commodity_carry_context.py`*

## 1. HONEST REFRAME

The evidence says this surface has **two genuinely distinct assets and one imposter**, and the current page framing blurs them.

**What is real (risk/DD decision-support + one vol-timing sleeve):**
- The vol-targeted **active gold model** is the only forward-looking construction that survives: DSR 0.9584, robust n12..n100 (`reports/active-commodity-lev-phase0.md`). That is a real risk-adjusted-return sleeve, and it earns alpha language.
- The **carry context engine** is deliberately an *anti-signal* — 63d IC −0.16, t_HAC −4.585, DSR 0.0015; backwardation predicts spot mean-reversion, not upside (`engine/commodity_carry_context.py:33-38`, `research/COMMODITY_CARRY_PHASE0.md`). Its objective is epistemic: *stop the reader buying backwardation.* This is decision-support, not alpha, and the caveat copy already says so.
- The **oil trend read is inverted** and the page hard-codes it as such: "12-month down-trend preceded +11%/126d… Read as contrarian" (`build_commodities.py:85-89`). Structurally intentional, but it is a reversion warning, **not** a timing signal.

**What is imposter alpha (must lose the alpha framing):**
- **Copper active** is on the scorecard with copy claiming *"genuine timing alpha, not just leverage"* and *"ROBUST"* (`build_commodity_strategies.py:52-56`) — but DSR 0.7454 FAIL + LOCO weak (`reports/active-commodity-lev-phase0.md`). This copy directly contradicts its own evidence file. It is the single most important honesty fix on the page.
- The whole `commodity_strategies.html` page is stamped "Experimental" (`build_commodity_strategies.py:51 _ACTIVE_CAV`) but the per-strategy copy asserts robustness. The blanket disclaimer does not license per-card alpha claims.

**Reframe law for the redesign:** the page's true objective is *"which commodity sleeves have earned a vol-timing tilt, which are context-only, and where does carry/trend warn you NOT to chase."* Gold = earned tilt. Silver = marginal tilt (disclosed). Copper, TSMOM, carry, oil-trend = **context/confirmer tier, not scored rankers.** Per the Design doctrine's Glance law, every panel must answer "so what do I do" — and for most of this page the honest answer is *"watch the driver/positioning; don't chase the print."*

## 2. STRUCTURAL FIXES (ship-now tier)

All fixes below are demotion / relabel / bugfix / promotion of **existing** keys — no new score is originated (A7_ORIGINATE safe).

**F1 — Demote copper active from "ROBUST timing alpha" to context tier. [JUDGMENT]**
`scripts/build_commodity_strategies.py:52-56`. Replace the `cm_copper_active` copy asserting *"genuine timing alpha"* with a plain-word context label ("Copper timing tilt is **not** robust — fails the promotion bar (DSR 0.75, weak leave-one-commodity-out); shown as context, read China credit / IP instead"). Gate the card visually to context tier (no scorecard rank, no green pass badge). Closes: *"copper active shown despite failing DSR+LOCO."* Effect: removes a false alpha claim that will not survive adversarial review. JUDGMENT because it is user-facing stance copy (opus/designer, not sonnet).

**F2 — Fix the CI-law "validated" word in the carry engine. [MECHANICAL]**
`engine/commodity_carry_context.py:1,7,19,32` use "validated"/"Validated" in shipped-adjacent strings; `scripts/check_validated_claims.py` CI-enforces this word in user-facing text. The `CARRY_CAVEAT` dict is *surfaced verbatim* (comment line 31), so line 32's "Validated caveat" and the module-doc "validated honesty layer" are exposure risk. Change to "phase-0-tested" / "evidence-backed." Closes: latent CI red / house-law violation. Effect: removes a landmine before the redesign PR trips it.

**F3 — Relabel the oil trend read from an interpretation to an explicit anti-signal chip. [JUDGMENT]**
`scripts/build_commodities.py:82-89` (`TREND_INTERP["oil"]`) already says "INVERTED… Read as contrarian," but it sits in a `TREND_INTERP` map alongside gold's *"12-month trend works."* Structurally, present oil in a separate **"reversion warning"** visual lane, not the same "trend works" lane, so a glance reader cannot misread inversion as confirmation. Closes: *"oil trend is INVERTED… fragile."* Effect: prevents the highest-traffic misread on the core page. JUDGMENT (stance/layout).

**F4 — Register the cross-sectional-momentum kill in DO_NOT_REBUILD. [MECHANICAL]**
Append an adjudication row to **section 2** (`research/DO_NOT_REBUILD.md:58`, "Killed/refuted signal families") — *not* elsewhere; rows outside sections 1–4 hard-fail CI per house law. Row: "Commodity cross-sectional momentum (L/S terciles/quintiles across the 19-name commodity universe) — KILLED. L/S Sharpe −0.23, DSR 0.0025, refuted across all 30 grid configs, both supercycle eras, lookahead-clean (`reports/commodity-xsec-mom-phase0.md` + `_refute.md`)." Then regenerate blocklists: `python3 scripts/check_blocklist_drift.py --fix` and **commit the compiled outputs in the same PR** (PostToolUse hook auto-regens; verify). Closes: the flagged house-law gap. Fully specified → MECHANICAL.

**F5 — Promote nothing silently; add the silver marginal-DSR disclosure. [MECHANICAL]**
`build_commodity_strategies.py` silver copy. Silver active is DSR 0.9188 **MARGINAL** with maxDD −64.6% (`reports/active-commodity-lev-phase0.md`). Keep it shown, but the card must print the drawdown and the "marginal, below the 0.95 BTC-class bar / above the 0.90 floor" status as a plain-word null-disclosure Tier-2 receipt (Design doctrine "nulls printed" form). Closes: undisclosed −64.6% DD on a levered sleeve. Effect: honest risk framing on the one marginal pass.

Priority order: **F1 > F4 > F2 > F5 > F3** (F1/F4 are the false-claim and house-law-gap; F2 is a CI landmine).

## 3. NEW PREREG RESEARCH BETS (staged tier)

Each is a hypothesis + frozen construction + gate + falsifier for **nightly/a human** to run — I originate no live score.

**B1 — Oil→XEG transmission chip, promotion re-test at power. [ACCRUE→gauntlet]**
*Hypothesis:* oil-trend direction leads Canadian energy equity (XEG) at a horizon where the channel is real but currently underpowered (t +2.75, DSR 0.541, `reports/c1-commodity-sector-phase0.md`). *Construction:* freeze the existing C1 construction from `C1_COMMODITY_SECTOR_PREREG.md`; extend the estimation window / add the C1b bear-protective leg (t −1.78, needs ≤−2.0) as a paired family; BH-FDR across {C1 long, C1b bear}. *Gate:* DSR ≥ 0.90, t ≥ 2.0 per leg, OOS holdout across the 2010 regime break, circular-shift timing placebo (2000 draws). *Data:* already collected (XEG + oil), **not data-blocked.** *Falsifier:* DSR stays < 0.90 after the paired family + FDR → **remain a context chip forever, never a scored ranker.** *DISTINCT from kills:* this is a *directional transmission channel* (oil→sector equity), not cross-sectional commodity momentum (KILLED, F4) and not carry (which is an anti-signal) — different predictor, different target, different sign.

**B2 — Multi-year cross-sectional carry, pending a real vendor. [DATA-BLOCKED, prereg-only]**
*Hypothesis:* dated-contract roll-yield carry ranks the commodity cross-section (the *cross-sectional* form, distinct from the *time-series* carry that was killed). *Construction:* freeze the `commodity-xsec-carry-phase0` grid; require ≥15y of clean dated-contract data. *Gate:* L/S Sharpe > EW-long + DSR ≥ 0.90, era split across 2010. *Data:* **BLOCKED — Yahoo 404s on expired contracts; needs CME/Stevens vendor** (`research/COMMODITY_DATA_AUDIT.md`, current L/S Sharpe −1.53 on ~3.1y is uninterpretable). *Falsifier:* with real data, L/S Sharpe ≤ EW-long → kill. *DISTINCT from kills:* time-series WTI carry was killed as a *timing anti-signal* (net Sharpe −0.21); this is a *cross-sectional ranker* across many commodities — a different construction the WTI kill does not close. **Ship as a prereg doc only; state the data block loudly; do not run OOS until vendor lands.**

**B3 — Commodity bottom/top confluence, unblock the bridge. [PRE-REGISTERED, awaiting data seam]**
*Hypothesis:* the pre-registered `COMMODITY_BOTTOM_TOP_PREREG.md` confluence (silver-washout + gold-persist + oil-reversion agreeing) marks turning points. *Construction:* already frozen; needs the `cycle_positions.json` bridge to run. *Gate:* per the prereg (hit-rate + n + DSR ≥ 0.90). *Data:* blocked on the bridge, not on market data. *Falsifier:* per prereg. *DISTINCT:* it is a *confluence of already-calibrated context keys* (permitted — "retained as a confluence input"), not a new standalone signal; distinct from xsec-mom (cross-section) and carry (single-series anti-signal).

## 4. PROMOTE / DEMOTE LEDGER

| Key | Evidence | Action |
|---|---|---|
| Gold active (`active_commodity.py`) | DSR 0.9584 PASS, robust n12..n100 | **Keep authority** — earns alpha copy; the one scored tilt |
| Silver active | DSR 0.9188 MARGINAL, maxDD −64.6% | **Keep, disclose** (F5) — marginal, DD printed, no BTC-class rank |
| Copper active | DSR 0.7454 FAIL + LOCO weak | **DEMOTE to context** (F1) — strip "robust/timing alpha" copy |
| TSMOM 5-leg book | DSR 0.6842 FAIL | **DEMOTE to confirmer** — display/confluence, never scored ranker |
| Carry context | DSR 0.0015, IC −0.16 | **Keep as anti-signal**; fix "validated" word (F2) |
| Oil trend | inverted, fragile | **Relabel** to reversion-warning lane (F3) |
| Xsec momentum | Sharpe −0.23, DSR 0.0025 | **KILL + register** (F4) — remove entirely, blocklist row |
| C1 oil→XEG | t +2.75, DSR 0.541 | **Hold as context chip**; re-test via B1 |

## 5. SEQUENCING

1. **F4** register xsec-mom kill + regen blocklists — **S**, no deps, **no sign-off** (house-law heal). *Do first — it is an open compliance gap.*
2. **F2** fix "validated" word — **S**, no deps, no sign-off (CI heal).
3. **F1** demote copper copy — **M**, depends on operator ratifying the demotion stance, **needs operator sign-off** (it reverses a shipped "robust" claim).
4. **F5** silver DD disclosure — **S**, no deps, designer review.
5. **F3** oil reversion-lane relabel — **M**, designer/opus (layout), review-gate.
6. **B1** write C1/C1b paired prereg + queue gauntlet — **M**, nightly-lane run, sign-off on the prereg freeze.
7. **B2** prereg doc only — **S**, blocked; **B3** — **S**, blocked on bridge.

Design steps (F1, F3, F5) route to `designer`/main-loop per §Model-routing Design lane; F2/F4 are fully-specified → sonnet `builder`. Template/site-copy pairing: if `commodities.html`/`commodity_strategies.html` ship as paired plain-copy assets, run `python -m scripts.check_template_site_sync --fix` in the same PR.

## 6. RISKS / OPEN QUESTIONS

- **Copper demotion is a public reversal.** The current page tells users copper timing is "genuine alpha." Removing it is correct but visible — operator should ratify the stance before F1 ships.
- **Silver −64.6% maxDD on a levered sleeve** is marginal-pass but ugly. Operator call: keep it live with disclosure, or gate it behind a "high-DD" warning tier?
- **B2 is fully data-blocked.** Do not let anyone run its OOS on the 3.1y Yahoo scraps — that would be a wrong-ruler violation. Vendor (CME/Stevens) is a real spend decision.
- **Oil inversion is structurally fragile.** It works as a contrarian read historically, but a single supply-shock regime could invert the inversion. It must stay context-tier and never gain a scored rank.
- **Does the operator want the whole `commodity_strategies.html` "Experimental" stamp kept** once gold is a clean PASS, or does gold graduate to a non-experimental "earned tilt" card while the rest stays experimental? That is a framing call above my pay grade.

*Every structural fix is a demote/relabel/bugfix/register of an existing key; every research bet is a frozen prereg with a falsifier and an explicit distinctness argument against the xsec-mom and carry kills. No new live score is originated.*

---

**Key files cited:** `scripts/build_commodities.py:82-89`, `scripts/build_commodity_strategies.py:51-56`, `engine/active_commodity.py:34`, `engine/commodity_carry_context.py:1,7,19,32-38`, `research/DO_NOT_REBUILD.md:58`, `reports/active-commodity-lev-phase0.md`, `reports/commodity-tsmom-phase0.md`, `reports/commodity-xsec-mom-phase0.md` + `_refute.md`, `reports/c1-commodity-sector-phase0.md`, `research/COMMODITY_CARRY_PHASE0.md`, `research/COMMODITY_DATA_AUDIT.md`, `research/COMMODITY_BOTTOM_TOP_PREREG.md`, `research/C1_COMMODITY_SECTOR_PREREG.md`.

**Two live findings surfaced during verification:** (1) copper scorecard copy asserts "ROBUST… genuine timing alpha" (`build_commodity_strategies.py:52-56`) contradicting its own DSR-FAIL evidence file; (2) the carry engine uses the CI-enforced word "validated" in shipped-verbatim strings (`commodity_carry_context.py:1,7,19,32`), a latent `check_validated_claims.py` red.

---

## ADVERSARIAL REVIEW

Verification complete. The refute file is `reports/commodity-xsec-mom-refute.md` (masterplan cited `_refute.md`), the c1b bear leg n=32, t=−1.78 checks out. I have everything needed for the review.

---

# ADVERSARIAL REVIEW — Commodity Strategies Masterplan

**1. A7_ORIGINATE — PASS (all six fixes clean).**
Every structural fix is demote/relabel/bugfix/register of an existing calibrated key. F1 demotes copper (existing `cm_copper_active`), F3 relabels the existing `TREND_INTERP["oil"]` inverted read, F4 registers a kill, F5 discloses an existing DSR. No fix wires a new live score. B1–B3 are framed as prereg bets for nightly/human to run, not scores the author wires in. **No A7 violation.**

**2. KILL COLLISION — PASS, with one demand for rigor.**
No fix or bet re-proposes a killed construction. The author correctly distinguishes B1 (directional oil→sector transmission) from xsec-mom (KILLED), and B2 (cross-sectional carry ranker) from the time-series WTI carry anti-signal — these are genuinely distinct predictors/targets. **However:** the carry kill in `COMMODITY_CARRY_PHASE0.md` and the engine docstring itself (lines 13-17) note "cross-sectional carry harvesting works but single-asset directional timing sees the reversal" — B2 leans on exactly that opening. That is legitimate, but B2's prereg MUST cite this line as its founding rationale so a future reviewer sees it is the *sanctioned* residual, not a backdoor revival. FLAG-MINOR: add that citation to B2.

**3. GAUNTLET RIGOR — FLAG (B3 gate underspecified; B1 solid).**
B1 is properly falsifiable: DSR≥0.90, t≥2.0/leg, OOS across 2010, circular-shift placebo (2000 draws), BH-FDR across the paired family, not data-blocked. Good. B2 is honestly data-blocked and correctly refuses to run OOS on 3.1y scraps. **B3 fails the "pre-registered gate (effect/hit/n/DSR)" bar** — it says "per the prereg (hit-rate + n + DSR≥0.90)" but never states the *numbers*. I verified `COMMODITY_BOTTOM_TOP_PREREG.md` exists but the masterplan does not extract its n or hit floor. A bet that defers its entire gate to an unquoted file is hand-wavy. FLAG: quote B3's pre-registered n and hit-rate floor inline, or mark it "gate TBD pending prereg read."

**4. WRONG-RULER / OVERFIT — PASS.**
B1's horizon matches the calibrated C1 channel (126d/quarterly transmission, not a mismatched daily ruler). The author explicitly guards against the wrong-ruler trap in R3 (do not run B2 OOS on 3.1y Yahoo). B1's paired-family BH-FDR pre-empts the multiple-testing death. C1b's n=32/t−1.78 (verified `c1-commodity-sector-phase0.md:105`) is thin but the bet correctly treats it as needing to *reach* ≤−2.0, not asserting it passed. No overfit smuggling.

**5. CLAIM→WEAKNESS — FLAG on F2 (factually wrong), rest PASS.**
F1, F3, F4, F5 correctly map to their documented weaknesses with right file/function (F1 `build_commodity_strategies.py:52-56` verified — copper copy literally says "genuine timing alpha"; F4 section 2 at `DO_NOT_REBUILD.md:58` verified as the correct home). **F2 is WRONG.** I verified `scripts/check_validated_claims.py` scans only `templates/` (`.j2`,`.js`), `site/` (`.js`,`.html`), and `site/prophet/plans/` — **NOT `engine/*.py`.** The four "validated" hits the masterplan flags are in the module docstring (lines 1,7,19) and a code comment (line 32) — none reach a scanned surface. The *surfaced* `CARRY_CAVEAT` dict (lines 33-40), which IS rendered verbatim, contains **zero** "validated"/"已验证" tokens. `grep` of `site/commodities.html` + `site/commodity_strategies.html` for "validated" returns nothing (exit 1). **F2 closes a weakness that does not exist** — it is not a CI landmine, and the "Two live findings" footer repeats this false claim. The docstring cleanup is fine hygiene but must be re-tagged as cosmetic, NOT a CI-red heal, and demoted from the priority list.

**6. MISSED — one real gap.**
The promote/demote ledger correctly demotes copper and TSMOM but **leaves the xsec-carry INCONCLUSIVE status (`commodity-xsec-carry-phase0.md`, L/S Sharpe −1.53 on 3.1y) undemoted on any surface** — if that number is displayed anywhere it is a wrong-ruler exposure the ledger ignores. The masterplan also does not address whether the *carry context anti-signal* itself is correctly labeled on the live page vs. the doctrine's "so what do I do" law (the caveat is epistemic but the panel's action verb is unstated). Minor: F5's silver maxDD −64.6% disclosure is right, but the ledger should also note silver's DSR 0.9188 is below the 0.90… no, above — the copy must not imply it *cleared* the BTC-class 0.95 bar (author handles this correctly).

---

**OVERALL VERDICT = NEEDS-REVISION** (minor, single-item). The epistemics are sound — A7-clean, no kill collisions, B1 is a genuinely rigorous prereg, F1/F4 are the correct high-value honesty fixes. But **F2 rests on a verifiably false premise**: the "validated" tokens live in engine docstring/comment lines that `check_validated_claims.py` does not scan, and the actually-surfaced caveat is token-free.

**Highest-priority correction:** Strike F2's "latent CI red / house-law violation" framing and both "Two live findings" claim (2). Re-tag the docstring/comment "validated" cleanup as optional cosmetic hygiene, remove it from the F2>F5>F3 priority ordering, and reallocate that slot — the real ship-now landmine is F1 (copper's shipped "genuine timing alpha" claim contradicting its DSR-0.7454-FAIL evidence file), which should be the unambiguous #1 alongside F4's house-law-gap registration.
