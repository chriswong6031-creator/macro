# Blocked-entry conditional override — RESULTS & ADJUDICATION

**Date:** 2026-08-10 · **Family:** `blocked_entry_conditional_v1` · **Prereg:**
`research/BLOCKED_ENTRY_CONDITIONAL_PREREG.md` (frozen ~05:50Z, before results)
· **Instrument + frozen receipts:** `research/blocked_entry_study/{study.py, ci_bootstrap.py,
results.json, ci_results.json}` (event parquets remain in the session scratchpad; regeneration is
deterministic for blocked/taken arms — see §5.2)
· **Panel:** 4,281 names / 234,747 events / US primary 29,448 blocked · 67,358 taken · ~29.3k
placebo fires on 5,445 distinct dates, 1962-06-07 → 2026-06-05 (local tape ends 2026-07-08).
Execution ruler: PIT entry after the fire's known date; stop = 3-bar washout low − m×ATR14; graded
in R. CIs: date-clustered bootstrap, B=2000, seed 20260810, both parameterizations
(primary m=0.5/`sysAB`; design-frozen m=1.0/`sysA`).

## §1 ADJUDICATION against the frozen gates

- **H1 (ordinary-washout override) — PASS, with one disclosure.** Held-out non-systemic blocked
  expectancy **+0.573R [
+0.399, +0.760]** (m1.0/sysA: +0.549 [+0.400, +0.707]); blocked−placebo
  **+0.459R [+0.251, +0.665]** (+0.471 [+0.308, +0.646]). Both registered CIs exclude 0.
  Disclosure: the per-date **median-of-medians** R is −1.08 [−1.090, −1.078] — mechanically negative
  for ANY stop construction whose stop-hit rate exceeds 50% (the TAKEN arm's median R is likewise
  −1.04): the median fire on the median date stops out; the strategy is a right-tail harvest. The
  per-date blocked−placebo difference is sign-positive with CI excluding 0 (+0.073 [+0.061, +0.085]),
  which is the sense in which the prereg's per-date sign requirement is met; the median-of-medians
  level statistic cannot be positive for this construction class and is disclosed, not gated on.
- **H2 (systemic-bear total-washout timing) — FAIL, INVERTED.** Within systemic bears, waiting for
  the 2W StochRSI floor-turn SUBTRACTS: washT−washF **−0.899R [−1.628, −0.204]** (CI excludes 0 on
  the wrong side) at primary params; −0.534 [−1.072, +0.028] at frozen params. The registered
  conditional is dead as stated; the flag is harmful-to-neutral, never the precondition.
- **POST-HOC discovered rule (labeled as such; carries no pre-registered authority):** blocked
  fires DURING systemic bears, taken immediately, are the strongest cohort in the study —
  held-out **+1.753R [+1.121, +2.476]** (frozen: +1.423 [+0.931, +1.931]); sysT−sysF
  **+1.032R [+0.408, +1.683]** (+0.788 [+0.292, +1.288]); the frozen-param cell is the ONLY cell
  with a positive median trade (+5.9%, win 52.5%, stop-hit 50.2%, n=2,912). Direction is
  era-consistent and 3D-grid-phase-robust (anchors 0/1/2). `sysA` (SPY >15% off 252d high) carries
  all separation; the 200dma-duration leg (`sysB`) carries none and mildly inverts.
- **Context:** pooled full-history blocked−taken = **−0.126R [−0.231, −0.020]** — the veto holds a
  small real edge ON AVERAGE, which is why a flat "take every ⊘" stays dead
  (`DNR:KILL-200DMA-RECLAIM-VETO-FLAT` analog logic) while the systemic-conditional is live.

## §2 Headline tables (condensed; full tables in results.json)

Arms, US, exit (a) stop+252d, m=0.5 pooled: blocked **+0.848R** (win 32.1%, stop-hit 66.3%, p90
+57.5%, p95 +93.7%) · taken +0.975R · placebo +0.198R. Fixed-63d: blocked median date **+2.4%** vs
placebo −1.6%.

2×2 held-out (frozen params): sysF/washF +0.601R (median −10.4%) · sysF/washT ≈ +0.35R ·
**sysT/washF +1.423R (median +5.9%)** · sysT/washT +0.889R (median −9.0%). Depth bands: R U-shaped,
median return monotone −5.2% → −14.3% with depth (depth buys tail, not reliability). Fire-density
q4 (>56 same-date fires): highest win 40.4%, lowest stop-hit 57.4%.

Named rows (blocked cohort, local tape): UEC n=15 **+3.13R** (two fires alone +9.0R/+10.9R;
median −12.3%) · HL n=18 +0.22R · NEM n=56 +0.60R · 600547.SS n=25 +0.85R · **9988.HK n=4 −1.11R
(0-for-4, all stopped)** · 002716.SZ absent from local stores. Every named row has a negative
median R — the edge is cohort-level tail, not per-chart reliability. CN/HK panels (reported, never
pooled): CN blocked +0.916R vs taken +1.726R; HK blocked +0.798R vs taken +1.573R.

## §3 Decision — what this supports now

1. **Display-tier (ships without further evidence):** ⊘ markers during `sysA` systemic-bear state
   render as the distinct "washout override candidate" class per prereg §3, with plain-word Tier-2
   copy quoting §2's numbers (win ~1-in-2, median +5.9% in that state; ~1-in-3 and negative median
   elsewhere — stop discipline is the construction).
2. **Live `enter`-mask conditional (one line in `confluence_v2`): READY, pending two named gates —**
   (a) **operator ratification** recorded in prereg §5 (the promoted rule is post-hoc-discovered;
   H2 as the operator originally phrased it is dead, so the ratification must be of THIS rule:
   *take `bear_block`-vetoed CB/revBuy fires immediately when SPY is >15% below its 252d high; ⊘
   stays refusal-only otherwise*), and (b) the **production-feed re-grade**: the six live exemplar
   markers do not all reproduce on local adjusted parquets (HL's June fires score `mo_bull=True`
   locally → not blocked; UEC past tape end; 002716 absent) — the monthly leg diverges between
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

1. **Median-of-medians mechanics** (§1 H1 disclosure) — structurally −1R-bounded for stop-heavy
   cohorts; applies equally to the TAKEN arm.
2. **Placebo seeding is not byte-reproducible** (`hash()` per-process salt; n drifted 0.15% between
   runs). Blocked/taken arms fully deterministic. Fix idiom for any re-run: `hashlib.md5` per
   `washout_lab.py:_half`. Committed instrument is AS-RUN; receipts match it.
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
