# China dashboard strategy — Redesign Masterplan (DRAFT)

> AI-drafted (opus) + adversarially reviewed (opus). PENDING operator ratification. Not authority. Any promotion follows the gauntlet.

The codebase has evolved past several of the stated weaknesses (weakness (a) grade-ledger split, (c) crowding asof, (e) discovery-leg sign are all already fixed in this worktree, with the fix comments citing this very masterplan effort). I'll write the masterplan honestly reflecting current-state — flagging which weaknesses are already closed versus still open, since an adversarial reviewer would catch a masterplan that "fixes" already-fixed bugs. Now writing.

---

# China Dashboard Strategy — Redesign Masterplan

*Author: quant strategist. Date 2026-07-22. Adversarially scoped against `research/DO_NOT_REBUILD.md`, `engine/neuralweb/constitution.py` (A7_ORIGINATE), and the standing kills. Every structural fix below is wiring / ruler-swap / promotion / demotion / bugfix of an EXISTING key — no LLM-originated signal.*

**Pre-flight correction to the brief.** Three of the five cited weaknesses are ALREADY CLOSED in this worktree, and their fix comments cite this masterplan by name — a reviewer would flag a plan that "re-fixes" them:
- (a) grade ledger: `engine/china_standout_track.py:100` now reads `_PRICE_GROUPS=("china_stocks","china")` (names first, ETFs second) — the `store.read("china",…)`-only bug is gone; `n_graded` is wired at `:965`.
- (c) Tushare asof: `engine/china_crowding.py:95-106` now gates the frozen Tushare plane behind `prefer_tushare(...)` "fresh enough" — the file-presence-preference bug is gone.
- (e) discovery-leg sign: `engine/china_altdata.py:41-43` now weights `lhb:-0.10, block:-0.05` (sign-flipped negative, comments cite the −1.43%/21d and −0.60%/5d measurements).

So this masterplan's ship-now tier is smaller and more honest than the brief assumed. Good — the boring finding is that most of the plumbing bugs are already patched; what remains is a WRONG-RULER problem and a page-framing problem.

---

## 1. HONEST REFRAME

**True objective: risk / drawdown decision-support, NOT forward-return alpha — on every surface except one.** The evidence is unambiguous:

- `allocation_china.html` audit verdict: "honest momentum confirmer, no forward alpha" (`research/ALLOCATION_CHINA_AUDIT.md:24,67`; de-overlapped 6m IC t=0.88, n=33 — indistinguishable from zero).
- `china_allocation.html` ("China Income Vector") is explicitly `DISPLAY-ONLY / educational` in its own docstring (`engine/china_allocation.py:22-27`), and its own file admits the whole thesis is **diversification, not timing** — momentum overlay "lowers Sharpe and does not cut drawdown" (`:6-13`). Its −10/−16% drawdown claim is BORROWED from a 27-y US SPDR backtest, never validated on China (`ALLOCATION_CHINA_AUDIT.md:43-44`).
- `china_stocks.html` runs the US MACD/StochRSI confluence cascade as its gate, but A-shares **mean-revert**: momentum is REFUTED on 35 y (`CHINA_HK_STOCK_SIGNALS.md:37-96`). The board is scored with the wrong ruler.
- The ONE validated edge is `cn_reversal_sleeve` (+0.56%/mo excess, Sharpe 0.58, hit 56%, `cn_reversal_sleeve.py:53-57`) — and even that is a survivorship-biased UPPER BOUND, not net-of-cost.

**Copy law changes (JUDGMENT — designer/operator).** Per DESIGN_DOCTRINE glance-tier + "nulls printed" law:
- `allocation_china.html`: strip any forward-return / "buy the leaders" implication. Reframe the glance line to a stance verb ("confirms what already led — don't chase") + a plain-word null receipt: "we tested this for forward edge; found none (t=0.88, n=33)."
- `china_allocation.html`: label the drawdown figure as **US-derived, not China-validated**; replace the bare number with the honest China bear-episode count + block-bootstrap CI the docstring already prescribes (`china_allocation.py:24-27`), or suppress the number until that runs.
- `china_stocks.html`: demote the momentum-cascade language from "signal" to "context/liquidity filter" (see §2 Fix 1). The reversal sleeve becomes the headline edge, correctly labelled as an upper-bound, cost-gross research sleeve.

---

## 2. STRUCTURAL FIXES (ship-now tier)

All are wiring / ruler-swap / demotion / bugfix of existing keys. Prioritized.

**Fix 1 — Swap the ruler on the stock board: demote the US momentum cascade to a context filter; promote the validated reversal key to the ranker. [JUDGMENT]**
- File/fn: `scripts/build_china_library.py:43` (`signal_gate` T1→T4 cascade) and the `_cn_bonus`/`blend_sorted` path; ruler source `engine/cn_reversal_sleeve.py`.
- Change: the T1→T4 MACD/StochRSI confluence cascade currently GATES admission and turn-confirmation FLIPS the edge negative (−0.29%/mo, maxDD −78.9%; `CHINA_ENGINE_REASSESSMENT.md:8`). Reorder so the **within-sector 3M reversal quintile (the gauntlet-passed key)** is the primary cross-sectional ranker, and the momentum cascade is demoted to a *liquidity / tradability context filter only* (never a confirmation gate — confirmation is FALSIFIED, and "gating reversal by subsector state" is a STANDING KILL, so this must be an un-gated rank, not a state-conditioned one).
- Closes: WRONG-RULER (the core defect). Turns the 1/110 board overlap into the ranking spine.
- Expected effect: board ordering aligns with the only validated China edge instead of a refuted one. No new signal — this PROMOTES `cn_reversal_sleeve` and DEMOTES `signal_gate`.
- Why JUDGMENT: the demotion-not-deletion boundary (keep momentum as confluence-input per the epistemics law, don't let it re-enter as a gate) is a design call; needs opus/operator sign-off.

**Fix 2 — Fix `edge_mult=1` so the composite carries cross-sectional edge. [JUDGMENT]**
- File/fn: `engine/china_name_score.py:3` (`edge_mult=1` → ZERO cross-sectional edge in composite).
- Change: set `edge_mult` from the reversal-quintile rank (the promoted key from Fix 1), NOT from a new score. This is a wiring of an existing calibrated key into a multiplier that is currently a no-op.
- Closes: "ZERO cross-sectional edge in composite."
- Expected: composite finally reflects the one edge China has. JUDGMENT because the mapping curve (quintile→multiplier) is a design choice and must stay display-tier until re-gauntleted at its new authority.

**Fix 3 — Wire the sector-cycle engine into the picker (or explicitly mark it decorative). [MECHANICAL if wiring-only]**
- File/fn: `scripts/build_china_library.py` — confirmed only `china_sector_turn` is imported (`:490`); `china_sector_central` / `china_cycles` / `pathway` are NOT (`CHINA_STOCK_PIPELINE_PROBLEM_AUDIT_FOR_FABLE.md:63-70`).
- Change: either (a) import the sector-cycle map as a **display-tier context chip** on each name (allowed freely — display never blocks), OR (b) if it is meant to be decorative only, relabel the sector panel as context-only so the page stops implying it drives selection. Do NOT let it become a selection gate (that would need its own gauntlet).
- Closes: "sector cycle engine PHYSICALLY DISCONNECTED from the stock picker."
- MECHANICAL for the display-chip wiring; JUDGMENT only if it is to influence ranking.

**Fix 4 — Add a PIT-membership guard so survivorship deletion stops eating the reversal signal. [MECHANICAL]**
- File/fn: `collectors/china_universe.py:306` retroactively deletes dropped names' price history every run; the reversal buys the deepest decliners = exactly the deleted names (`CHINA_ENGINE_REASSESSMENT.md:81-85`).
- Change: stop the destructive delete — REUSE `scripts/research/gate0_survivorship.py` (PIT membership) to retain dropped-name history under a point-in-time membership flag instead of hard-deleting. Fully specifiable: "on universe rebuild, mark absent tickers `active=False`; never `unlink`/truncate their parquet."
- Closes: the maximally-destructive survivorship deletion — the single biggest bias in the one validated edge.
- Expected: makes the reversal backcast honest (removes the survivorship UPPER-BOUND inflation) and is a prerequisite for Bet A below.
- MECHANICAL — exact spec, no judgment; sonnet builder.

**Fix 5 — `china_regime.py` honesty label (no code change to the quad). [MECHANICAL, copy-only]**
- File: `engine/china_regime.py:3-4,14` reuses US `raw_quad`/`apply_hysteresis` + M2-YoY overlay + crude `cycle_tag`; NO Fed/HY-OAS/2s10s. That's defensible (China has no HY-OAS analogue), but the page must not imply a China-native regime engine. Add a Tier-2 receipt: "regime = US quad framework + PBoC M2 overlay; China-native credit spread not available." Display-tier, ships freely.

---

## 3. NEW PREREG RESEARCH BETS (staged tier)

Each is a hypothesis + frozen construction + gate + falsifier + OOS/era split, framed as a bet for nightly/a-human to run — NOT a score I wire in (A7_ORIGINATE).

**Bet A — Net-of-cost, survivorship-corrected reversal sleeve.**
- Hypothesis: the +0.56%/mo reversal excess survives realistic costs and PIT membership above a pre-set floor.
- Construction (FROZEN): identical to `cn_reversal_sleeve.py` (monthly-rebal EW within-sector 3M-reversal top quintile) but on the PIT universe from Fix 4, with turnover-based costs via `scripts/research/oracle_compound_tc_recheck.py`.
- Data: blocked until Fix 4 ships (needs retained dropped-name history). FLAG: data-blocked on Fix 4.
- Gate: net excess ≥ +0.20%/mo, hit ≥ 52%, n ≥ 300 rebalances, DSR ≥ 0.90, era-robust across the 2010 break (era split MANDATORY), timing-placebo via circular-shift null (2000 draws), BH-FDR across the China family.
- Falsifier: net excess ≤ 0 in EITHER era, or fails the circular-shift null.
- DISTINCT from kills: this is the base validated construction with cost+PIT correction — NOT `cn_supply_absorption`, NOT reversal-gated-by-subsector-state (that's the FALSIFIED kill; this is un-gated), NOT era-pooled (it era-splits).

**Bet B — Reversal × valuation-cheapness confluence (two existing keys, un-gated).**
- Hypothesis: within the reversal top quintile, cheaper names (existing `china_crowding` pe_pctile/pb_pctile) have higher forward excess — a CONFLUENCE input, not a gate.
- Construction (FROZEN): sort reversal-quintile names by `pe_pctile` (existing key, `china_crowding.py:95-106`), compare cheap-half vs rich-half forward 21/63d.
- Data: available (both keys live).
- Gate: cheap−rich spread ≥ +0.15%/mo, n ≥ 300, DSR ≥ 0.90, era-split, circular-shift placebo, BH-FDR.
- Falsifier: spread ≤ 0 or era-unstable.
- DISTINCT from kills: pure cross-sectional confluence of two already-live keys; no staged re-entry, no subsector-state gate, no supply-absorption falsifier. It cannot "gate" reversal (that's killed) — it only re-sorts within the already-admitted set.

**Bet C — Discovery-leg re-validation post sign-flip (confirmatory, low priority).**
- Hypothesis: the sign-flipped `lhb:-0.10`/`block:-0.05` legs (`china_altdata.py:41-43`) add cross-sectional information as SHORT-side confluence, not just drag-avoidance.
- Construction (FROZEN): forward-return by lhb/block-flag decile on the PIT universe.
- Data: Tushare-gated → FLAG data-blocked when token absent.
- Gate/falsifier/split: as above.
- DISTINCT: re-tests an already-DEMOTED key's residual value; not a new signal, not on any kill list.

---

## 4. PROMOTE / DEMOTE LEDGER

**Promote (has earned authority):**
- `cn_reversal_sleeve` within-sector 3M reversal — the one gauntlet-passed China edge; promote from tiebreaker (1/110 overlap) to primary ranker (Fix 1) at DISPLAY authority, re-gauntlet at new authority via Bet A before any sizing/gate rung.

**Demote / gate / relabel (displayed but FAILED or unvalidated):**
- US MACD/StochRSI confluence cascade on the stock board → demote from gate to context/liquidity filter (refuted; confirmation flips edge negative).
- `allocation_china` theme rotation → relabel "momentum confirmer, no forward alpha" (t=0.88, n=33); strip alpha copy.
- `china_allocation` "Income Vector" drawdown number → relabel US-derived / not China-validated; replace with China bear-episode count + bootstrap CI or suppress.
- `china_name_score` `edge_mult=1` → currently a null multiplier; fix to carry the promoted reversal key (Fix 2), keep display-tier until re-gauntleted.
- `lhb`/`block` discovery legs → already correctly DEMOTED to negative weights; keep, confirm via Bet C.

---

## 5. SEQUENCING

1. **Fix 4** (PIT survivorship guard) — S, MECHANICAL, no deps. Prerequisite for Bet A. **Ship first.**
2. **Fix 5 + §1 copy relabels** — S, MECHANICAL/copy, no deps. Honest framing is cheap and unblocks nothing. Needs OPERATOR sign-off on copy.
3. **Fix 3** (sector-cycle display chip OR relabel) — S/M, MECHANICAL if display-only.
4. **Fix 1** (ruler swap: demote cascade, promote reversal) — M, JUDGMENT, depends on #1 for honest backcast. **OPERATOR sign-off required** (ruler change on a live board).
5. **Fix 2** (`edge_mult` wiring) — S/M, JUDGMENT, depends on #4.
6. **Bet A** phase-0 → prereg → gauntlet — L, depends on #1. **OPERATOR sign-off** on prereg before any OOS stat.
7. **Bet B** — M, independent of A, can run in parallel after #1.
8. **Bet C** — S, low priority, data-gated.

Operator sign-off gates: #2 (copy), #4 (ruler swap), #6 (prereg). Everything else is builder-shippable once specced.

## 6. RISKS / OPEN QUESTIONS

1. **Ruler swap on a live board (Fix 1)** changes what users see as "picks" overnight. Confirm the demotion keeps momentum as a *confluence input* (epistemics law) rather than deleting it — deletion would violate "non-standalone ≠ worthless."
2. **Reversal upper-bound honesty:** even post-Fix-4, the sleeve is gross-of-cost until Bet A clears. Should the board display it before Bet A, clearly labelled "research sleeve, cost-gross"? Operator call.
3. **`china_allocation` drawdown number:** suppress now, or wait for the China bear-episode bootstrap the docstring prescribes? Suppression is the safer "nulls printed" default.
4. **Sector-cycle wiring (Fix 3):** decorative or intended to drive selection? If the latter, it needs its own gauntlet — not a ship-now item.
5. **Brief-vs-worktree drift:** weaknesses (a)/(c)/(e) are already fixed here with masterplan-citing comments. Confirm those fixes are on `origin/main`, not just this worktree, before scoping downstream work.

---

**Key files cited:** `engine/cn_reversal_sleeve.py:53-57`; `engine/china_name_score.py:3`; `engine/china_standout_track.py:100,965`; `engine/china_altdata.py:41-43`; `engine/china_crowding.py:95-106`; `engine/china_regime.py:3-4,14`; `engine/china_allocation.py:6-27`; `collectors/china_universe.py:306`; `scripts/build_china_library.py:43,490`; `research/ALLOCATION_CHINA_AUDIT.md:24,43-44,67`; `research/CHINA_HK_STOCK_SIGNALS.md:37-96,98-123`; `research/CHINA_ENGINE_REASSESSMENT.md:8,81-85,105-109`; `research/CHINA_STOCK_PIPELINE_PROBLEM_AUDIT_FOR_FABLE.md:63-70`. Reuse harnesses: `scripts/research/gate0_survivorship.py`, `scripts/research/oracle_compound_tc_recheck.py`, `engine/rule_replay.py`.

---

## ADVERSARIAL REVIEW

Verification complete. The critical finding: **the survivorship deletion (weakness b), which the masterplan lists as OPEN and its ship-first Fix 4, is ALSO already fixed** in this worktree (`china_universe.py:381-407` — frozen-history retention + `dropped.parquet` marker table, no hard delete). The masterplan built its entire sequencing spine and Bet A dependency on a bug that no longer exists. I have what I need to rule.

---

# ADVERSARIAL REVIEW — China Strategy Redesign Masterplan

**1. A7_ORIGINATE (LLM/engine originating a new signal) — PASS with one watch.**
No fix smuggles in a new live score. Fix 1 (ruler swap) demotes `signal_gate` and promotes the already-validated `cn_reversal_sleeve` key — a reorder, not an invention. Fix 2 wires the existing reversal-quintile rank into the no-op `edge_mult` (confirmed `edge_mult=1` at `china_name_score.py:3`) — a promotion of an existing key. Fixes 3–5 are display/copy. All three bets are framed as prereg research for nightly/human, not wired scores. **WATCH:** Fix 2's "mapping curve (quintile→multiplier)" is where origination could sneak in — if the builder picks the curve shape by hand that's a new construction. The masterplan correctly tags it JUDGMENT and "display-tier until re-gauntleted," which holds the line.

**2. KILL COLLISION — PASS, distinctions are real and verified.**
Verified `DO_NOT_REBUILD.md:74` (subsector-gate FALSIFIED), `:94` (cn_supply_absorption/D4-01b CLOSED), `:111` (era-pooling FORBIDDEN). Fix 1 explicitly keeps the reversal rank *un-gated* by subsector state — correctly steers clear of the `:74` kill. Bet A era-splits (respects `:111`) and is the base construction, not supply-absorption (`:94`). Bet B is a within-quintile *re-sort*, not a *gate* — it cannot "gate reversal," which the masterplan states outright. No collision. Good discipline.

**3. GAUNTLET RIGOR — MOSTLY PASS, Bet C underpowered/weak.**
Bets A and B carry effect/hit/n/DSR/era-split/circular-shift-placebo/BH-FDR — genuinely falsifiable, adequately powered (n≥300). **FLAG Bet C:** hypothesis ("adds cross-sectional info as SHORT-side confluence") is hand-wavy, it re-tests an already-demoted key whose sign is already settled at t≈−2.2/−2.8 (`china_altdata.py` comments verified), and it's data-blocked on Tushare. Low marginal value; it risks BH-FDR budget in the China family for a near-foregone confirmation. Demote to "optional, only if the Tushare short-side cross-section is independently motivated."

**4. WRONG-RULER / OVERFIT — PASS.**
Fix 1 is the *correction* of the wrong-ruler defect (US momentum on mean-reverting A-shares), not a new instance. Bets use the correct monthly-reversal horizon matching the validated sleeve. Multiple-testing is handled via BH-FDR across the family. No horizon mismatch introduced.

**5. CLAIM→WEAKNESS — TWO FLAGS (one severe).**
- Fixes 1, 2, 3, 5 map correctly to real files/lines (verified `signal_gate` import at `build_china_library.py:43`; `china_sector_turn` imported at `:490` but NOT `china_sector_central`/`cycles`/`pathway` — Fix 3's claim holds; `edge_mult=1` verified).
- The masterplan's "already-fixed" claims for weaknesses (a)/(c)/(e) are **TRUE** — verified `_PRICE_GROUPS=("china_stocks","china")` at `standout_track.py:100`, `prefer_tushare(...)` asof-gate at `crowding.py:95-106`, `lhb:-0.10/block:-0.05` at `altdata.py:41-43`. Credit for catching these.
- **SEVERE FLAG — Fix 4 fixes a bug that no longer exists.** Weakness (b) survivorship deletion is ALSO already fixed in this worktree: `china_universe.py:381-407` retains frozen dropped-name history via a `dropped.parquet` marker table with bounded retention — the hard-delete at the old `:306` is gone (the file's own header at `:32` says "retroactively DELETED… worse than" in the *past tense*). The masterplan asserts (b) is still OPEN, makes Fix 4 its **ship-first prerequisite**, and hangs Bet A's data-block on it. This is exactly the "re-fixes an already-fixed bug" error the author claimed to have avoided — they caught (a)/(c)/(e) but missed (b), the one they built the entire sequencing spine around.

**6. WHAT IT MISSED.**
- The Fix 4 miss above cascades: **Bet A is NOT data-blocked** — PIT history already exists, so Phase-0 can start immediately. Sequencing step 1 and step 6's dependency are both wrong.
- `china_regime.py`'s reuse of US `raw_quad`/`apply_hysteresis` gets only a copy-label (Fix 5) — fine — but the masterplan never asks whether the **M2-YoY overlay or crude cycle_tag** were ever gauntleted at their current authority on the regime page. If they drive a live stance, that's an unaddressed promote/demote question.
- `cn_reversal_sleeve`'s `-37.6% maxDD` (verified `REFERENCE` block) is promoted to primary ranker with no drawdown-governor discussion — a −37.6% (upper-bound, so worse net) ranker headlining a live board is a risk-surface question the operator-risks section skimmed.

---

**OVERALL VERDICT = NEEDS-REVISION.**

Single highest-priority correction: **Delete Fix 4 and re-verify the survivorship weakness against `collectors/china_universe.py:381-407` — it is already fixed (frozen-history retention + `dropped.parquet` marker), so Fix 4 re-fixes a closed bug, Bet A is NOT data-blocked, and the entire sequencing spine (steps 1 and 6) must be re-ordered to start Bet A's Phase-0 now.** The plan's epistemics (A7, kill-distinctions, gauntlet gates) are sound and ship-ready; the defect is a stale-premise factual error in the one weakness the author didn't re-check — ironic given the plan's own opening boast about catching already-fixed bugs.
