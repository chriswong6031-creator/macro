# CN LIMIT ALPHA — continuation handoff — written 2026-08-09 (second session; W3-B/W3-C close)

**To the next session (Fable orchestration per the charter; one wave per session).** Read in
order: this file → `research/CN_LIMIT_ALPHA_MASTERPLAN_BY_FABLE.md` (now ON MAIN with §6.1–6.4
adjudications + §8 wave map; §6.4 is this session's) → the predecessor handoff
`CN_LIMIT_ALPHA_CONTINUATION_HANDOFF_2026-08-09.md` (its §Traps list still binds — do not
re-pay traps 1–7) → the two new receipts under `research/cn_prophet_audit/`
(CONTINUATION_REGIME_MERGE_V1, ONSET_FILLABILITY_RESTATEMENT_V1, each on its PR branch until
merged).

## State at close

**W3-B and W3-C delivered, adversarially reviewed (AMEND-THEN-ARM both), amended, and
armed — masterplan §6.4 is the authority.** One sentence: FIVE families are now measured and
priced at daily resolution (next-open strength · break-day weakness · pullback weakness ·
window targets · the regime axis), and the paper-vs-buyable gap is a measured curve — model
confidence and regime heat both price themselves through the T+1 auction primarily by
REMOVING THE FILLS (dial-hot availability 96.2→79.5% with tax 20.6→52.3%; ladder rungs
fillable 99.91→71.21% with 一字 0.022→13.53%). The intraday battery's case is sharpened, not
merely survived: both access-rationing mechanisms are objects minute bars can watch forming.

**PR map (verify merges before building):**
- MERGED during this chain: #5077 (masterplan+handoff), #5093 (W2-A), #5099 (W3-A).
- ARMED by this session after full review cycles: **#5142** (W3-B regime merge, branch
  `claude/cn-limit-w3-regimemerge`, 2 commits — base + amendments), **#5144** (W3-C onset
  fillability, branch `claude/cn-limit-w3-onsetfill`, 2 commits).
- ARMED, still pinned from before: #5055 (L3 onset + ledger), #5059 (L0 heals), #5061 (L1
  rider), #5074 (w4_feed re-pin), #5078 (L2 regime), #5091 (W2-B weakness).
- Gating upstream: #4999 (v0) still open → v0-corrections PR stays gated.

**Infra state (read before touching CI):** the repo moved to the enterprise org 08-09; hosted
runners are throttled to ~7 effective of a nominal 180 (billing-endpoint artifact; a GitHub
support ticket is the fix — memory `hosted-runner-throttle-after-org-transfer`). Main
baseline dispatches were livelocking via ci.yml's per-ref cancel-in-progress dedup; #5136
fenced it and a dedicated session owns the residual wedge. **Do NOT `gh workflow run ci.yml
--ref main`** unless the fleet advisory changes — watch, never dispatch. The merge-on-green
sweeper drains the armed backlog automatically once a main proof concludes; expect SLOW CI
until support restores capacity. Arming on review remains correct regardless of CI speed.

## FIRST ACTIONS next session, in order

1. **GRADE THE FORWARD LEDGER — it is now gradeable.** `onset_forward_ledger.jsonl` (rides
   #5055; 2,000 retro + 100 live rows, all live rows predict_date 2026-08-10) was verified
   intact this session with zero graded rows — correct, because Monday's bars had not
   printed. The first post-Monday nightly delivers them. Grade per ONSET_CALIBRATION_V1:
   binary tolerant limit-up close (close ≥ limit×0.998) is the grade; realized return and
   near-limit recorded BESIDE it, never blended. Reading notes (B1's known defects): isotonic
   ceiling ties the head at 27.03% (use the ladder's 45.80% for N≥3 rows); chinext
   over-predicts ~2.6× (read the curve as measured, apply nothing). 2026-08-10 is a normal
   Monday session (predict_date_source was a calendar estimate — confirm against the actual
   trade calendar before grading; a holiday would shift the target bar, not void the row).
2. **Verify the armed eight merged.** If still pinned, re-census main's newest ci.yml reds
   FIRST (armed-backlog-reforms pattern), check the infra state above, and only then decide.
3. **Commission the nightly ledger advancer once #5055 is on main** (masterplan §8.6). The
   wiring adjudication is MADE (this session): relocate the ledger to
   `data/cn_limit_lab/onset_forward_ledger.jsonl` (git mv in the advancer PR; era-stamp the
   move in a receipt note) so the asia-close.yml engine-outputs commit step's existing
   `git add data/` covers it — do NOT extend the workflow's add to `research/`. Hook point:
   after the "CN Pick Lab — fire books + grade + render" step (~line 606). The advancer
   grades matured rows AND emits the next session's live rows (append-only; nightly is the
   sole advancer; §7 law). Point every reader at the new path in the same PR.

## Queue after that (evidence-ranked, §6.2/§6.4 synthesis)

1. **Intraday minute-bar battery** — still GATED: as of this session's close the Codex lane
   had landed the daily full-A TuShare spine (#5116) and a one-ticker add-ons PILOT (#5098,
   auction endpoints partly entitlement-blocked); NO minute-bar corpus exists on disk. Check
   `data/` for their stores landing on main before building; the foresight premium
   (+2.03%/t 3.55, H=10 holdout, peak_best) is the sized target; the two access-rationing
   mechanisms (§6.4) are the first things to look at in minute resolution.
2. **F3 full-universe re-run** — gated on the Codex universe expansion (1,842 → ~5,400 incl
   ST + delisted) landing.
3. **C11 (一字 queue-depth), C15 (cross-band telemetry pilot, post-2020 era)** — cheap
   catalog constructions, buildable now. C12 is DONE (folded into W3-A, §6.3).
4. **v0-corrections PR** — gated on #4999 merging (§8.7 list + the tape's
   lianban_count=0-on-failed_up_seal defect + W2-B's strict/tolerant overlap note).
5. Theme-relay v1 stays blocked on THS concept mapping; collectors stay with the Codex lane
   (§9 collision boundary — never build on their surfaces).

## Traps — NEW this session (predecessor's 1–7 still bind)

8. **`china_stocks_raw` encodes 停牌 as zero-volume STALE-PRICE placeholder bars, not
   missing rows** (133,781 in W3-C's window). Every entry/exit/outcome leg must demand a
   LIVE bar (volume > 0); suspension is an exclusion CAUSE to pin, never a scoreable row.
   Placeholder and 一字 are structurally disjoint (一字 requires a live bar). W3-C's U2
   paper book scored 2,697 phantom trades before the two-sided mask; implementable books
   were saved only because `_usable_next` independently demanded live.
9. **Null-headline receipts must hold affirmative asides to the null's standard** (now a
   binding house standard, §6.4): date-cluster/bootstrap every affirmative share, run
   permutation nulls with an ERA-PRESERVING arm beside the global one (era composition
   manufactured a p≈0.005 that was really p≈0.07), and key every verify predicate to a
   series that CAN move (S7-class defects surfaced three waves running — name the check in
   every review brief).
10. **K<10 heads of a book need their own pin**: L3 published no K<10 rows, so W3-C pins
    top-1/3/5 as prefixes of the externally-pinned K=10 ordering (26,105 groups, zero
    violations). Reuse `prefix_order_pin` when re-cutting any book finer than its source.

## Standing (unchanged)

Dual-lane §9: never read `research/cn_limit_alpha_sol/`; data is common ground once on main.
ORE LAW on every verdict; Opus builders in isolated worktrees grind, you orchestrate and
adjudicate; the blinded brainstormer is SPENT; display-tier ships freely, gauntlet only at
promotion; fillability honesty everywhere; work the ship loop (lane → PR → your review →
armed merge-on-green — reviews are AMEND-THEN-ARM by default now, budget for the cycle).

## Operator-visible summary (they read daily)

This session closed the daily-bar question completely: with the regime dial and the model's
own confidence now tested, every way of buying tomorrow's strength or weakness from daily
data is priced — and we measured HOW: the market prices information by taking away the
fills, not just by moving the open. The best names on the best days are precisely the ones
you cannot buy. That mechanism is visible at minute resolution, which is where the program
goes next the moment the purchased minute data lands. Monday's 100 live predictions get
graded against reality the night they resolve — the honesty ledger is running.
