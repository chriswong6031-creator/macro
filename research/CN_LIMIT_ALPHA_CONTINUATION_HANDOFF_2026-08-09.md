# CN LIMIT ALPHA — continuation handoff — written 2026-08-09 (Wave-1 close)

**To the next session (Fable orchestration per the charter; one wave per session).** Read in
order: this file → `research/CN_LIMIT_ALPHA_MASTERPLAN_BY_FABLE.md` (§6.1 adjudication + §8
re-ranked wave map) → `research/CN_LIMIT_ALPHA_BLINDED_BRAINSTORM_2026-08-08.md` → the four
Wave-1 receipts under `research/cn_prophet_audit/` (CONTINUATION_RIDER_V1, ONSET_CALIBRATION_V1,
BOARD_ECOLOGY_REGIME_V1, CN_LIMIT_DATA_HEALS). The original operator charter is
`research/CN_LIMIT_ALPHA_FABLE_HANDOFF_2026-08-08.md` (lands with PR #4972).

## State at close

**Wave 1 delivered and adjudicated (masterplan §6.1).** One sentence: the probability
structure is real, era-stable, and forecastable; the T+1 auction prices the public
conditioners (naive next-open riders lose everywhere, anti-monotonically); the fillability tax
is measured (46.7% of main next-day boards unbuyable); the edge search therefore narrows to
selection (regime-conditional calibration), weakness entries (回封/龙回头), the regime dial,
and the two intraday collectors that are now cheap.

**PR map (verify merges before building):**
- MERGED: #5051 (masterplan + blinded brainstorm).
- Armed merge-on-green, awaiting the base-red heal swarm: #5055 (L3 onset), #5059 (L0 heals),
  #5061 (L1 rider), #5074 (w4_feed schema re-pin, this session's heal), and the Wave-1
  adjudication PR carrying this file.
- L2 (regime): SALVAGED AND APPROVED — #5078 (branch `claude/cn-limit-w1-regime-salvage`),
  armed. M5 verdict CLEAN (triple-gated phantom detection; healed-store re-run moved zero
  numbers). Key instruments for W2: i5_realized_continuation_ma5 (THE dial), raw breadth
  counts FORBIDDEN as absolutes (within-year sign inversion). The dead worktree
  `agent-a6c9b9c64bebd39bd` and its `claude/cn-limit-w1-regime` local branch are redundant —
  leave them to worktree GC.
- Upstream chain (sibling program, armed): #4972 (charter doc), #4999 (v0), #5000, #5007.
- Base-red heal swarm (NOT ours, do not duplicate — verify landed): #5064/#5065 (pack-0
  earnings-seasons date bomb), #5033/#5034/#5023/#5031/#5036 (packs 2/3: ETHA beta knife-edge,
  spvector None, signal-lab frozen quote, govrev states re-red), spvector re-pins #5049/#5062.
  If armed W1 PRs still sit `merge-blocked` when you start: re-census main's latest ci.yml run
  reds FIRST (the swarm may have landed and new debt formed — the armed-backlog-reforms
  pattern), then `gh workflow run ci.yml --ref main` after any heal lands to clear pins.

## Wave-2 charter = masterplan §8, verbatim priority order

Spawn shape that worked: Opus `builder` lanes in isolated worktrees, acceptance gates inline
(ore ledger · no board pooling · era tables · Wilson/THIN · fillability honesty · locked-exit
rolls · deterministic TZ=UTC instrument · frozen JSON · v0-parity pin where applicable · PR
with no merge label, commissioning session arms). Lane reports ≤15 lines. The blinded
brainstormer is SPENT (one per program by charter §1.4) — do not respawn one without a fresh
operator order.

## Traps this program has already paid for (do not re-pay)

1. `data/china_stocks_raw` is BACK-ADJUSTED (not nominal, despite v0's header); tolerance
   adjudication survives; returns unaffected. The adjusted twin `data/china_stocks` remains
   forbidden for limit detection.
2. zt_pool `date` semantics are healed (trade-date) ONLY from L0's PR forward — any analysis
   against a pre-heal vintage must drop non-session dates itself. Eastmoney CLAMPS non-session
   requests (serves last session, no 404).
3. `limit_events.parquet`/`limit_tape.parquet` moved under L0's heal (events 60,428→71,463;
   universe_n +186 median) — never compare pre/post-heal numbers without saying which vintage.
4. The 一字/fillability censor is load-bearing everywhere: quote NO continuation number
   without its fillable-conditional twin. Locked-down exits must roll (mean −2.14%, worst
   −20.96% observed).
5. Never pool boards; never pool ChiNext across 2020-08-24; era tables mandatory (2015 =
   18.6% of main limit-ups; first→second swings 7.93%→24.18%).
6. v0's committed JSON prose still says strict-is-primary (stale; MD is right) until the §8.7
   corrections PR lands — do not build from the JSON's `definitions` block.
7. Session-limit deaths mid-lane are recoverable: check the dead worktree's git INDEX before
   rebuilding anything (this wave's L2 was fully staged when it died).

## Forward ledger (LAW from charter §5 — grade it every session)

`research/cn_prophet_audit/onset_forward_ledger.jsonl` (rides #5055): 2,000 retro rows + 100
LIVE rows stamped feature_date 2026-08-07 → predict_date 2026-08-10 (Monday). **The 2026-08-10
outcome is gradeable from 2026-08-10's bars — grade it in Wave 2 and every session after**;
nightly advancer wiring is §8.6 (the asia-close.yml commit-step path caveat is recorded
there). Grading: binary limit-up close (tolerant primary), realized return + near-limit
recorded alongside, never blended. B1's known defects when reading grades: isotonic ceiling
ties the head at 27.03% (use the ladder's 45.80% for N≥3 rows); chinext over-predicts ~2.6×
(apply nothing — just read the calibration curve as measured).

## Operator-visible summary (they read daily)

Wave 1 proved the game is forecastable and that the obvious trade is already priced at the
open auction. That is not a defeat: it is the map. The remaining edge candidates are exactly
where practitioner lore says the skill lives — buying weakness in proven names (回封/龙回头),
knowing when the whole game is ON (regime dial), and the two intraday moments (first seal,
9:25 auction) whose data we can now collect nearly free. Wave 2 tests those in priority
order, with the forward ledger keeping every probability honest.
