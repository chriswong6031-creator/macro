# Phase-1 synthesis + critic pass (Fable, 2026-07-03)

*The workflow's dedicated critic agent died on a session-limit; this document is the orchestrator's
own critic pass + cross-report synthesis. Reports: 10/10 landed. Supplementary probes (mtf-machinery,
narrative-confluence, board-history) pending re-run after the 09:30 limit reset.*

---

## A. The cross-exemplar signature (the owner's playbook, measured)

| | **300725** (PharmaBlock) | **603129** (CFMOTO) | **688306** (PIA Automation) |
|---|---|---|---|
| on board 07-02? | **#3**/110 | **#2**/110 | **NO** — dropped 07-02; was T2 06-22→07-01 |
| path shape | washout→base→early recovery | washout→base→**running** | washout→dead-cat bounce→**faltering** |
| rev_z (the "validated edge") | ~mid | **−0.66** (leader — edge dislikes it) | **−0.35** (rank 1129/1471) |
| washout_2w | ✓ (matches owner's "2W washout") | ✓ but fired **06-29, after +14.6%** | absent |
| COILED | ✓ | ✓ — fired **06-18 at the base low** | ✗ (EXPANSION, bbwp 78) |
| first *rankable* flag | T2 06-24 → captured **21%** of bounce | T2 06-24 → missed first **9.5%** | cascade 06-22, **after** the +24.6% thrust |
| theme heat | SynBio **+18.9%** rel20 — **TWD axis "no data"** | **zero THS membership** | Solid-State Battery **+35.6%** — unwired |
| displayed score / entry | 43 "Watch" / "Hold — don't add" | 26 "Watch" / "Hold — don't add" | (off board) |
| rank driver | T1(pending-promo) + washout .5 + coiled .25 | bonus stack **+0.736** (setup only 0.61) | n/a |

**Findings that fall straight out of the table:**

1. **The archetype the owner picks — and the board actually surfaces — is washout→base→fresh-turn,
   NOT the validated quarterly within-sector reversal.** rev_z is negative on 2 of 3 owner picks.
   The page's stated edge ("reversal") and its de-facto product diverge; the owner's playbook sides
   with the de-facto product. (603129 §5: 002555 with 2.5× higher setup ranks BELOW 603129 purely
   for lacking washout+coiled bonuses — bonuses, not the advertised edge, are the product.)
2. **Signal earliness is inverted vs rank weight.** Empirical firing order: COILED (at/near the
   base low) → cascade T2 (mid-run) → T1 → washout_2w (LAST, post +14%). Rank bonuses: washout
   +0.50 > COILED +0.25 > FIRE 0. **The latest signal carries the biggest bonus; the earliest
   carries half of it; the freshest re-trigger carries none.**
3. **Capture rates are poor and structural:** 21% (300725), ~42% (603129), ≤0% (688306). The
   2D/3D cascade is a *confirmation* instrument being asked to do *anticipation* work.
4. **Theme heat is real, present in data, and reaches zero cards** (TWD "no data" on a name inside
   a +18.9% theme; 603129 has no THS membership at all — coverage hole, not just a join bug).
5. **688306 — honest split.** By every lens we compute (rev_z, COILED, cascade timing, entry gauge)
   it is the weakest of the three and the 07-02 drop was mechanically correct. The owner's case
   rests on exactly the two layers we do NOT compute: the 2W-MACD projected cross and narrative
   heat (16 THS baskets, robotics). **688306 is therefore the perfect test fixture for the W-tier
   + narrative layers** — if those validate, this archetype gets a home; if not, the drop stands.
6. **Where computable, the owner's reads reproduce**: 300725 washout_2w ✓ + coiled/basing ✓;
   603129 "already ran / late / risky now" ✓ (fuel 0.192, HOLD, rolled off eligibility 07-02).
   The system *sees* what the owner sees — it just ranks and renders it incoherently.

## B. Verified system facts (non-exemplar readers)

- **rev_z coverage is FIXED** — `rev_z_all` covers 1,478 names; 110/110 board rows carry it
  (old top-16 path would have left 108/110 on the alpha fallback). Audit [verify] V1 resolved.
- **Rank formula reproduced exactly:** `0.30·tier_wn + 0.70·setup_pct + (0.5·washout_2w +
  coiled(≤0.25) + 0.15·star − 0.5·ext_score)`. Spearman(rank, displayed score) = **−0.189**;
  vs setup −0.619. **77/110 cards wear an "extended" entry chip; 85/110 are band-low** — the wall
  of contradictions is the normal state, not an edge case.
- **Freshness cliff:** board `as_of 07-02` ships `signal.asof 07-01`; 603129 was surfaced on its
  LAST eligible bar and is already ineligible on live recompute. Separately, per-stock JSONs
  (`chinastockdata/`, feeds china_lookup) run on a slower cadence (06-26): click-through shows
  score 77/"constructive" vs card 26/"Watch" for the same name.
- **Data goldmine (inventory):** the "close-only" doctrine is **FALSE** — full per-name OHLCV
  **incl. volume** for ~1,506 names (raw + adjusted planes) to 2011; **volume is used by zero
  signals**. Tushare 6 live cross-sectional stores (turnover_rate on 5,589 names, moneyflow,
  chips/筹码, broker, forecast). ZT-pool + LHB live but rolling-window only (LHB ~21k-event
  backfill available via `stock_lhb_jgmmtj_em`). THS concept daily history NOT stored (2 rows) —
  reconstructable from member OHLCV. No Shenwan crosswalk. ETF flows 20d. QVIX live (5d lag).
- **Rotation machinery:** the fast layer already exists and is unwired —
  `china_sector_cycles/forward_log.parquet` carries daily phase+osc_slope for 31 sectors + 22
  baskets; the "Trough + osc_slope>0" first-tick-up filter flags **Agriculture and Pharma today**
  (independently corroborating the owner's healthcare read for 300725). `compute_china_ths_confluence`
  (T3/T4 on THS concept indices) is fully implemented and called by nothing. **gate_factor is stuck
  at 0.2 on all 212 sector_central calls → the Accumulate tier (≥72) is unreachable (max 60)** —
  the sector page structurally cannot recommend. Slow layer (ZigZag 25%) confirms turns 21–130d late.
- **Port recipes complete** (us-port-mechanics): HOLD insertion points mapped both sides;
  `china_standout_track.append_board` already logs `tier` per row but `grade()` never stratifies
  by it; CN board ledger accruing since 06-30 (21d matures ~07-29); CN grader is already CSI300-
  relative + fill-realistic (T+1, limit-lock exclusion) — better bones than expected.
- **Phase-0 ledger (sober):** reversal Sharpe 0.58 is an *unreproducible upper bound* (closes_deep
  absent, retroactive universe deletions, total-return closes); every refinement falsified
  (turn-confirm Sharpe −0.29; subsector gate #754 drains); basket TS momentum 0/36 FDR. Four
  validated non-selection findings with **zero board consumers**: drawdown radar 2.07× lift,
  AI-semis→CPO t=3.27, low-vol tilt, washout signature.
- **Signal research:** top new candidate = **abnormal turnover** (documented negative predictor in
  A-share literature; directly buildable from our unused volume plane). Full 35KB report on disk.

## C. Cross-report contradictions (critic function) — reconciled

1. *closes.parquet staleness* (rotation agent: 06-26 vs sectors 07-01) — **RESOLVED**: agent
   measured the stale main checkout; the worktree panel is fresh to 07-02 (verified this session).
   Not a pipeline bug.
2. *COILED CN validation* (phase0-verdicts: "only a US squeeze phase-0 found, no lift" vs build
   comment "CN gate clean15 +7.33pp, n=10,784") — **both true on different axes**: COILED was
   validated on the durable-bottom constitution (clean-liftoff/stop-out/dead-money), NOT forward
   returns. Masterplan must cite the wave-3 report and keep grading it on those axes.
3. *tier_stream says T1 / scalar cascade says T2 for 688306's window* — display-path discrepancy;
   wave-level nit, does not affect ranking.
4. *688306 owner-vs-system* — not resolvable by argument; resolved by the pending 2W/narrative
   probes + forward data. Held as the program's test fixture.

## D. Gaps still open before the masterplan is final

1. **[probe pending]** Owner-read reproduction on 2W/1W lenses (mtf-machinery) — decides the
   W-tier design. Re-run after 09:30 reset.
2. **[probe pending]** Board git-history timeliness (first-appearance dates; confirm 688306 was on
   the 06-22→07-01 renders the owner reviewed).
3. **[probe pending]** Narrative-heat feasibility (per-name THS heat; global-healthcare read-through).
4. **[read pending]** Full `ashare-signal-research.md` (35KB) — summary was thin; read before
   masterplan; re-run the agent only if the report is as thin as its summary.
5. Freshness contract: is `as_of` one session ahead of `signal.asof` intended? (Wave-0 diagnosis.)
6. gate_factor=0.2 stuck: bug vs genuine perma-risk-off read of `china_masterminds.regime_state`.
   (Wave-0 diagnosis; it decides whether sector_central is broken or honest.)

## E. Firm rulings already supportable (pre-masterplan)

- **R1 — Rename the product to its true archetype.** The board surfaces washout→base→turn names;
  rev_z/reversal is a *different* validated product (quarterly, basket-unit) and must become a
  separate lens/sub-board, not the headline claim. (Fixes `template-describes-dead-screen` in the
  honest direction — the copy should describe the *actual* screen, which is ALSO the owner's playbook.)
- **R2 — Fix the earliness inversion.** COILED (earliest, validated on liftoff axes) must not carry
  half the bonus of washout_2w (latest). Washout's bonus should decay by bars-since-fire. Exact
  weights come from tier-stratified forward grading (which R3 stands up) — recalibrate with
  evidence, not by fiat.
- **R3 — W0 repair wave needs no research and ships now:** HOLD port (recipe ready) · tier-
  stratified grading (extend `append_board`/`grade`) · sector_state on rows · gate_factor diagnosis
  · TWD/THS theme-heat join fix (+ THS membership coverage check — 603129 has none) · per-stock
  JSON cadence sync or click-through freshness banner · as_of/signal.asof contract · wire the
  3-line "Trough + osc_slope>0" sector chip from forward_log.
- **R4 — One lifecycle stage per card as THE loud field** (SETUP / ENTRY / RAN-LATE), rank-consistent
  by construction, plus a "why ranked here" chip rendering the actual blend terms (now that the
  formula is reproduced, this is honest and cheap). Everything else goes quiet.
- **R5 — Volume program.** The unused OHLCV plane is the single biggest data asset: phase-0
  abnormal-turnover + turnover-shape (guarded against the already-falsified refinement list).
- **R6 — Log-first discipline confirmed.** Every new rank input enters as ledger+chip first; gate
  power is earned. The CN ledger's fill-realism (T+1, limit-lock) is already correct — extend, don't
  rebuild.
