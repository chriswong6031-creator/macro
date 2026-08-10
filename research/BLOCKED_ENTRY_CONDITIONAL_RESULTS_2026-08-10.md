# Blocked-entry conditional override — RESULTS & ADJUDICATION

**Date:** 2026-08-10 · **Family:** `blocked_entry_conditional_v1` · **Prereg:**
`research/BLOCKED_ENTRY_CONDITIONAL_PREREG.md` (commit `98fe6113af6`, 05:35:10Z, before results)
· **Instrument + frozen receipts:** `research/blocked_entry_study/{study.py, ci_bootstrap.py,
results.json, ci_results.json}` (event parquets remain in the session scratchpad; regeneration is
deterministic for all arms — see §5.2)
· **Panel:** 4,788 requested / 4,649 with events / 262,818 events · US primary 32,059 blocked ·
72,552 taken · 31,885 placebo, 1962-06-07 → 2026-07-09 (local tape ends 2026-07-08; the final
date is the next-session entry).
Execution ruler: PIT entry after the fire's known date; stop = 3-bar washout low − m×ATR14; graded
in R. CIs: date-clustered bootstrap, B=2000, seed 20260810, both parameterizations
(primary m=0.5/`sysAB`; design-frozen m=1.0/`sysA`).

## §1 ADJUDICATION against the frozen gates

- **H1 (ordinary-washout override) — PASS, context-only.** Held-out non-systemic blocked
  expectancy **+0.572R [+0.384, +0.785]** (m1.0/sysA: +0.539 [+0.371, +0.706]);
  blocked−placebo **+0.580R [+0.390, +0.777]** (+0.483 [+0.316, +0.658]). The preregistered
  equal-date-weighted read is also positive: blocked +0.492R [+0.284,+0.754] and
  blocked−placebo +0.419R [+0.154,+0.719] (frozen: +0.514 and +0.341, both CIs exclude 0).
  The descriptive per-date **median-of-medians** remains −1.08R: the median fire on the median
  date stops out, so this is a right-tail cohort result, not a typical-trade claim. That median
  diagnostic is not substituted for the preregistered equal-date expectancy.
- **H2 (systemic-bear total-washout timing) — FAIL, INVERTED.** Within systemic bears, waiting for
  the 2W StochRSI floor-turn SUBTRACTS: washT−washF **−1.003R [−1.729, −0.367]** (CI excludes 0 on
  the wrong side) at primary params; −0.624 [−1.133, −0.114] at frozen params. The equal-date
  read is −0.861 [−1.819,+0.051], which also does not satisfy the positive/excludes-zero gate.
  The registered conditional is dead as stated; the flag is harmful-to-neutral, never the
  precondition.
- **POST-HOC discovered rule (labeled as such; carries no pre-registered authority):** blocked
  fires DURING systemic bears, taken immediately, are the strongest cohort in the study —
  held-out **+1.790R [+1.147, +2.485]** (frozen: +1.447 [+0.919, +1.968]); sysT−sysF
  **+1.054R [+0.401, +1.726]** (+0.807 [+0.300, +1.332]); the frozen-param cell is the ONLY cell
  with a positive median trade (+4.3%, win 51.8%, stop-hit 43.9%, n=3,120). Direction is
  era-consistent in the committed anchor-0 receipt. `sysA` (SPY >15% off 252d high) carries all
  separation; the 200dma-duration leg (`sysB`) carries none and mildly inverts. No uncommitted
  anchor sensitivity is promoted to evidence here.
- **Context:** pooled full-history blocked−taken = **−0.148R [−0.258, −0.039]** — the veto holds a
  small real edge ON AVERAGE, which is why a flat "take every ⊘" stays dead
  (`DNR:KILL-200DMA-RECLAIM-VETO-FLAT` analog logic) while the systemic conditional remains a
  context-only, post-hoc candidate.

## §2 Headline tables (condensed; full tables in results.json)

Arms, US, exit (a) stop+252d, m=0.5 pooled: blocked **+0.827R** (win 31.3%, stop-hit 67.1%, p90
+57.8%, p95 +95.8%) · taken +0.975R · placebo +0.159R. Fixed-63d remains descriptive only.

2×2 held-out (frozen params): sysF/washF +0.591R (median −10.7%) · sysF/washT +0.333R ·
**sysT/washF +1.447R (median +4.3%)** · sysT/washT +0.823R (median −9.6%). Depth bands: R rises
while median return worsens −6.0% → −15.3% with depth (depth buys tail, not reliability).
Fire-density q4 (>59 same-date fires): highest win 38.9%, lowest stop-hit 59.0%.

Named rows (blocked cohort, local tape): UEC n=15 **+3.13R** (median −12.3%) · HL n=18 +0.22R ·
NEM n=56 +0.60R · 600547.SS n=26 +0.91R · 002716.SZ n=16 +1.04R · **9988.HK n=4 −1.12R
(0-for-4, all stopped)**. Every named row still has a negative median return — the edge is
cohort-level tail, not per-chart reliability. CN/HK panels (reported, never pooled): CN blocked
+0.888R vs taken +1.605R; HK blocked +0.799R vs taken +1.601R.

## §3 Decision — what this supports now

1. **Context-only result; no display promotion.** The study records that the `sysA` systemic-bear
   cohort is the post-hoc candidate. Per prereg §3, even a display-tier class remains queued behind
   explicit operator ratification, the production-feed re-grade, and the era fence. Nothing in
   this PR may rank, gate, size, enter, issue, or alter a reader-facing marker.
2. **Live `enter`-mask conditional: NOT READY; pending two named gates plus the era fence —**
   (a) **operator ratification** recorded in prereg §5 (the promoted rule is post-hoc-discovered;
   H2 as the operator originally phrased it is dead, so the ratification must be of THIS rule:
   *take `bear_block`-vetoed CB/revBuy fires immediately when SPY is >15% below its 252d high; ⊘
   stays refusal-only otherwise*), and (b) the **production-feed re-grade**: the six live exemplar
   markers do not all reproduce on local adjusted parquets (HL's June fires score `mo_bull=True`
   locally → not blocked; UEC/current 002716 marks are past tape end) — the monthly leg diverges between
   feeds, so the verdict-era pass re-runs on the VPS slice-basis OHLC before the flip, and the live
   conditional keys off production's own `bear_block` computation either way. Era fence per prereg
   §4 (signal_layer emission version bump; no pre/post pooling).
3. **Dead:** the 2W-StochRSI wait-for-turn precondition (H2), in this construction — closed
   construction-scoped (ore law: the elongated-stoch axis remains open under other constructions).

## §4 Six-name reconciliation with the operator's live screenshots

The live ⊘ marks (UEC 08-03, 9988 late-Jul, 600547 07-03, 002716 07-23, SI=F 08-05) post-date or
sit at the edge of local tape (ends 07-08) — none are graded rows here; §2's named rows are those
names' HISTORICAL blocked fires. The operator's realized outcomes on the current cluster are
consistent with the systemic-cell finding (metals complex in systemic washout), and 9988's 0-for-4
history is the counterweight exhibit: the rule pays as a portfolio of stop-bounded entries, not as
per-name conviction.

## §5 Limits (disclosed, none verdict-bearing)

1. **Median-of-medians mechanics** (§1 H1 disclosure) — structurally near −1R for stop-heavy
   cohorts; it is a tail-shape diagnostic, not the registered equal-date-weighted expectancy.
2. **Reproducibility repair before merge.** The draft instrument used Python's salted `hash()`
   for placebo seeds and accidentally resolved Macro data through the shared checkout. The merged
   receipt instead uses `md5(symbol)` for a stable seed, derives the Macro root from this worktree,
   pins the external `signal_layer/confluence.py` SHA-256 and chart-repo commit, and was regenerated
   after those repairs. The committed JSON matches the repaired instrument, not the draft run.
3. **Event parquets carry no exit columns** (dict fields stripped on write); `ci_bootstrap.py`
   regenerates events deterministically via `study.events_for_symbol` (17s).
4. **SPY store starts 1993** — pre-1993 design-era fires default `systemic=False`; the held-out era
   is the clean §3 read. **Local tape ends 2026-07-08**; 6.9% right-censored.
5. **No multiple-comparison correction beyond the prereg budget**; the systemic split is the only
   axis separating across eras AND grid phases; it is nonetheless post-hoc and gated on
   ratification, not on this document.
6. **Feed divergence** (§3.2b) — the one open verification before a live flip.

## §6 Reproduce

```
python3 research/blocked_entry_study/study.py --mode full --anchor 0   # ~90s/pass, writes results.json
python3 research/blocked_entry_study/ci_bootstrap.py                   # B=2000, writes ci_results.json
```
