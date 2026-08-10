# CN LIMIT-MOVE ALPHA — program masterplan (Fable orchestration)

Status: **superseded; STOP-SHIP (2026-08-10)**

Authority: `none_research_display_only`

**DO NOT EXECUTE THE HISTORICAL WAVE MAP OR CITE ITS NUMBERS.** The adjusted-price
construction beneath the Wave-1 through Wave-3 measurements was withdrawn by
`research/CN_LIMIT_ALPHA_SOL_ADJUSTED_PRICE_STOP_SHIP_2026-08-09.md`. The numeric
results, receipts, recovery commands, grading directions, and promotion queue below are
retained only as historical context; they are not evidence and cannot seed a new ledger.
`DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT` and the amended reconciliation ledger govern on
conflict. Qualitative construction ideas may inform a fresh preregistration only after an
authorized unadjusted TuShare `daily` plus same-key `stk_limit` exact-cent substrate and
point-in-time completeness proof exist.

**Program home.** Commissioned by operator order 2026-08-08; chartered in
`research/CN_LIMIT_ALPHA_FABLE_HANDOFF_2026-08-08.md` (PR #4972). Orchestration: Fable main
loop plans/adjudicates; Opus `builder` lanes measure in isolated worktrees; ONE blinded Fable
brainstormer per ore-law §1.4. Model routing law binds every spawn.

---

## §0 ACCEPTANCE GATES (program-wide, every wave, phrased "not done unless")

A wave receipt is not done unless:
1. **ORE LEDGER present** — an explicit `UNTESTED VARIANTS` section. A null on one construction
   NEVER closes a hypothesis; a kill names exactly what was and was NOT tested.
2. **No pooling across boards** (main ±10% / ChiNext ±20% / STAR ±20% are separate populations);
   ChiNext never pooled across 2020-08-24. Era tables mandatory (2015 = 18.6% of main limit-ups;
   first→second swings 7.93%→24.18% by year).
3. **Fillability honesty** — every backtested entry/exit priced at a fillable moment (a locked
   board cannot be bought; a locked-down open cannot be sold). Expectancy on unfillable fills is
   fiction and does not ship.
4. **Coverage receipt** restating the universe caveat (curated 1,842 of ~5,400 names; 29% of
   zt_pool names present; survivors-only; 1/100 ST names).
5. **Wilson 95% on rates, THIN label at n<20, nulls PRINTED** — never hidden, never averaged away.
6. **Deterministic instrument** (`TZ=UTC python3 …` from repo root), frozen JSON beside the MD.
7. **Display/audit tier language** — nothing ranks/sizes/gates/admits; "validated" never appears
   (CI-enforced); the gauntlet applies only at authority promotion, which no Wave-1 artifact seeks.
8. Ship loop: commit → push → PR → review by the commissioning session → armed merge-on-green.

## §1 Operator charter (distilled; the contract)

Capped daily bands stretch a one-session US-style repricing into 3-4 days of 连板; T+1, weekends
and after-hours 发酵 make forced spectators and invite crowding; the game is mainstream enough
that TongHuaShun ships the limit-up board as a product feature. Even 5-10% true onset probability
is a PORTFOLIO edge when spread across the daily candidate set; continuation matters as much as
onset (enter DURING the first board day; ride rerating windows — 6% one day, 8% the next, a board
here and there — not 10%-every-day rigidity). The operator believes footprints exist before onset
and before continuation, and ordered aggressive first-principles + second/third-order exploration.
Verbatim intent honored throughout: *"intuition and dense contextual local state is the value
that I can bring to the table… I would like it to be completely unraveled and tested so we don't
throw away the ore half refined."*

## §2 THE ORE LAW (standing, binding on every verdict)

An operator hypothesis is ORE, not a claim. (1) Construction-space map BEFORE any verdict —
enumerate variants/relaxations/adjacent mechanisms/rulers/horizons/regimes, test the strongest
few, not the first one. (2) Ore ledger in every receipt. (3) Exploration tier ≠ promotion tier:
generous constructions, printed nulls, fast iteration; pre-registration discipline WITHIN a
construction, never ACROSS the space; holdout/forward ledger keeps promotion honest. (4)
Fresh-eyes rule: one independent Fable brainstormer, blinded to the commissioning taxonomy,
merged at adjudication (anchoring is an ore-loss mechanism).

## §3 Established base (v0 instrument, PR #4999 — read its receipt before touching anything)

`research/cn_prophet_audit/LIMIT_MOVE_FOOTPRINT_V0_2026-08-08.{md,json}` + script. Trustworthy
event catalog: 60,298 limit-up closes / 15.6y / 1,836 names; detector pinned 100% against
`engine.china_microstructure._detect_limit_events` at 99.85% precision; tolerant definition
(0.2% cushion) adjudicated PRIMARY on evidence (median marginal event = exactly 100.000% of
band; 99.79% 连板 agreement with the independent vendor pool vs 91.1% strict). Headlines:
P(next-bar board | 连板 N) main 16.50%→72.78% (N=1→6), ChiNext to 78.83% (N=5); unconditional
~1.27% ⇒ the state alone is a 13× lift, 3.4× stronger than the best feature. Six sign-stable
features (holdout top-bucket lift, main): f3 run-up-5d 3.93× · f7 52w-low-dist 3.27× · f6 gap
3.07× · f1 vol-z 2.58× · f4 sector-heat 2.39× · f8 consec-up 2.33× (max top-bucket Jaccard
0.216 — different information). f5 near-limit-prev printed UNSTABLE; f2 turnover printed NULL
(no share counts anywhere in CN stores). Magnitudes compress in the ChiNext era control;
**direction is the finding, magnitude is not.**

**Data planes** (all git-tracked): `data/china_stocks_raw` (1,842 × daily nominal OHLCV — the
adjusted twin fabricates limit misses, never use it); `data/china_zt_pool/pool.parquet` (vendor
limit-up pool, market-wide, 47 dates 2026-06-15→, ALL dates carry `seal_fund_yi` 封单,
`failed_seals` 炸板, `turnover_pct`, `consec_boards` — plus a date-semantics defect: Saturday
rows exist, L0 diagnoses); `data/china_microstructure/limit_events.parquet` (house tape; KNOWN
34-name pre-2026-07 hole with a lying `backfill=True` flag, L0 heals);
`data/china_search/members.parquet` (sector map, CURRENT membership applied to history);
`data/china_pick_lab/fires.jsonl` (fillability idiom: `limit_state`, `fillable`,
`t_plus_one_risk`). Machinery for Wave 2+: `engine/china_basket_turn.py` (washout lifecycle),
`china_board_rank.py` (species/reversal cohorts), `subsector_confluence.py` CN half (THS 题材
mapping).

## §4 Construction-space map (commissioning session)

**Mechanism taxonomy — different physics ⇒ different footprints ⇒ separate models:**
- **(a) NEWS/RERATING boards** — repricing too big for the band (the 300363 class). Footprints:
  pre-event accumulation (vol-z, run-up), washout-maturity of the launch base, sector heat.
  Continuation physics: distance-to-fair-value; where a cross-listed/sector-parallel uncapped
  market exists (US/HK), its instant repricing is an oracle for boards-remaining (S5, novel).
- **(b) THEME/CASCADE boards (题材接力)** — leaders seal, followers chase in relay tiers.
  Footprints: sector/concept limit-heat (f4 already 2.39×), leader board count, follower rank in
  concept. Second-order: relay exhausts as follower quality degrades — a measurable
  quality-gradient clock. Needs THS concept mapping (Wave 2).
- **(c) MOMENTUM/GAME boards (打板 ecology)** — reflexive, driven by the board ecology itself.
  Regime instruments computable TODAY: daily first-board count, max active ladder (高标 height),
  realized next-day continuation rate, 炸板 proxy (intraday touch-fail from daily high). Third
  order: ladder-leader failure de-rates the whole ladder next session (退潮) — measurable.
- **(d) SQUEEZE/SEAL mechanics** — 封单 is a commitment signal; daily bars see its shadows. The
  **T+1 OPEN GAP is the overnight-demand read on seal strength** (the 9:25 auction reveals what
  the lock hid): P(board T+1 | board T, gap decile) is decidable at auction, tradable at open —
  the single most tradable construction on daily data alone.

**Cross-cutting structure:** T+1 forced holding makes the morning auction the crowd's P&L clock;
weekend boards ferment (operator observation — DOW conditioning is a first-class test);
fillability is the strategy's SPINE (tradable set = pre-seal entries, 开板 re-entries, next-open
entries — most retail 打板 backtests lie exactly here); portfolio math = Kelly-fractional
spreading of lottery-like onset plays + continuation riders at boards 1-3 where probability
16-52% still meets fillability + a regime dial sizing the whole book (the 3× era swing dominates
any per-name feature).

**Strategy shapes seeded:** S1 next-open continuation rider (most feasible today — Wave 1 L1) ·
S2 onset portfolio on calibrated P (Wave 1 L3 builds the calibration) · S3 theme relay via THS
concepts (Wave 2) · S4 regime gate over everything (Wave 1 L2 builds the dials) · S5 cross-market
rerate oracle (Wave 2+, measure before believing).

## §5 Blinded brainstorm (ore-law §1.4) — RETURNED 2026-08-08, merged

Full verbatim list: `research/CN_LIMIT_ALPHA_BLINDED_BRAINSTORM_2026-08-08.md` (7 mechanisms ·
10 second/third-order structures · 18 constructions C1-C18 · 9 collectors P1-P9 · 6 strategy
shapes · 7 space-level falsifiers F1-F7). Union verdict vs the §4 commissioning map:

**Convergences (independent derivation = evidence):** the day+1 open auction as THE tradable
moment (its C2 "fillability frontier" ≡ §4(d)/S1 — both name the gap the price of admission and
demand open-anchored, censored accounting); regime dial instrument list (C7 ≡ S4/L2, near
field-for-field); leader-death contagion (C8 ≡ L2's cascade test); weekend fermentation (C14);
seal-quality-from-daily-shape (C1 species ≡ §4(d) shadows); theme relay with degrading follower
quality (C6 ≡ §4(b), sharpened to a two-sided prediction — onset UP and continuation DOWN for
laggards, making it a mechanism test not just a signal).

**Divergences (= ore the commissioning map lacked):** M2 promoter-campaign lifecycle with
mechanism-dependent VOLUME SIGN FLIPS (M1 news-truncation starts volumeless, M2 campaigns start
heavy; M4 lockup makes mid-run volume contraction bullish — pooled volume stats are therefore
mechanism-blind); C12 near-miss attention discontinuity (the zt-pool visibility cliff as a
natural experiment); C15 cross-band theme telemetry (ChiNext ±20% names as shadow-price oracles
for main-board ±10% siblings — a WITHIN-CN, testable-today form of §4's S5); C10 龙回头 dip book
(guaranteed fills, inverted adverse selection — a third book beside rider+onset); C11 一字
queue-depth proxy (falling locked-volume = lengthening queue); §2.5 打开空间 height psychology
(one name's new cycle-max re-rates the whole market's risk budget); §2.7 regulatory metagame
(特停/inquiry/减持 as run-killers; LHB-absence as signal); the quant-T+0 era covariate; the
F1-F7 falsifier frame (F1 "the auction prices everything" is the sharpest kill condition over
W1-L1; F3 "the ladder is a data artifact" binds W2's zt_pool backfill).

**Data discoveries (verified by this session before commit):** `limit_events.parquet` already
carries failed_up_seal ×13,871 with `close_off_limit_pct` (炸板 cohort computable TODAY, strict
basis, pending L0 heal); `limit_tape.parquet` is a daily aggregate regime series 2011→ (L2's
independent build = its cross-check); `china_holder_counts` carries `total_a_shares` at
disclosure cadence (v0's f2 turnover NULL is PARTIALLY repairable — W2 audit P4); raw bars carry
NO `amount` column (VWAP proxies impossible until the P2 collector lands); volume units
(shares vs 手) unverified — prerequisite check before any volume-normalized construction ships.

## §6 WAVE 1 (2026-08-08 session) — lanes and gates

| Lane | Branch | Deliverable |
|---|---|---|
| L0 data heals | `claude/cn-limit-w1-dataheal` | limit_events 34-name backfill + honest flag + tests; zt_pool date-semantics heal + append-only tape + tests; vendor field inventory (封单 collector is pre-authorized #1) |
| L1 rider | `claude/cn-limit-w1-rider` | Open-gap-conditioned continuation (the §4(d) construction): P(board T+1 | N, gap band) + fillability-honest entry book (E1/E2/E3 exits, locked-exit rolls) + 一字 fillability tax + DOW/fermentation + gap-continuous curve |
| L2 regime | `claude/cn-limit-w1-regime` | Board-ecology daily series (first-board count, 高标 height, 炸板 proxy, realized continuation) + regime-conditional continuation + leader-cascade test + zt_pool cross-validation (curated-universe undercount factor) |
| L3 onset | `claude/cn-limit-w1-onset` | Calibrated P(board T+1) — logistic+isotonic vs ladder-only benchmark vs bucket model; reliability curves; Brier skill; top-K portfolio tables; parsimony probe; **forward-ledger seed** (retro + live stamps, grading spec) |

Wave-1 acceptance = §0 gates per lane + this session's adjudication appended below.
**Success definition (program, from charter §5):** calibrated P(board)/P(continuation) beating
the base-rate ladder on holdout AND a fillability-honest paper book with a graded forward ledger
≥10 sessions, plus the regime gate. Authority promotion (any surface claiming action) goes
through the gauntlet; display-tier ships freely.

### §6.1 WAVE-1 ADJUDICATION (Fable, 2026-08-09)

**Lane verdicts.** L0 #5059 APPROVED — the limit_events hole was **9× v0's estimate** (314
holed / 264 fully absent; mechanism: the raw store grew 1,592→1,842 names on 2026-08-05 while
history is built once and appended over a ~20-session window; v0's crosscheck intersected with
the tape's ticker set, so fully-absent names were structurally invisible to it). zt_pool's "47
dates" were **36** — Eastmoney's endpoint CLAMPS non-session requests to the last published
session and the collector stamped the asked date, minting 11 phantom weekend/holiday dates of
byte-identical rows. Healed both, with the honest residual printed (74/60, of which 60 have
zero detectable events). **Free-field discovery:** 首次封板时间 (first-seal time) is served by
the call we already make — Stage-4 collector #3 drops to near-zero cost; 涨停原因 is NOT on
this endpoint (theme mapping stays a THS-side item). L1 #5061 APPROVED — the wave's landmark
(below). L3 #5055 APPROVED as an **honest null with attributed cause**: B1 logistic+isotonic
misses the pre-registered Brier-skill bar (main −0.17%, chinext −11.69%) because a frozen
calibration slice imports its era's base rate (chinext slice ran 2.06× hotter than holdout);
discrimination is strong (AUC 0.775 vs ladder 0.592; log-loss skill +4.61%) — the miss is
LEVEL, not ORDER. B2 (f3×f6×N empirical buckets) is the only positive-skill six-feature object
(+0.32% main, best ECE, best top-10); **f3+N alone beats everything at +0.71%** — and f3's
coefficient flips sign as ladder dummies enter: v0's flagship 3.93× run-up lift is
substantially **the 连板 ladder wearing a feature's clothes**. Forward ledger seeded (2,000
retro + 100 live rows; live = 2026-08-07 features → 2026-08-10). L2 #5078 APPROVED
(salvaged): the original lane's triple-gated phantom detection (weekend + payload-hash-dupe +
trading-calendar) meant L0's heal moved ZERO published numbers (series parquet SHA-identical) —
receipt self-protection is now the house standard. Findings: **i5 realized-continuation-ma5 is
THE regime dial** (holdout top-vs-bottom quintile 26.73% vs 12.61% = 2.121×, rho 1.0,
era-neutral 12/16 years — Wave-2 §8.1's calibration conditioner); **raw 涨停家数 breadth
INVERTS within-year** (era artifact, use within-series ranks); 高标断板 marks a bad day,
barely a bad tomorrow (same-day 0.759× → next-day 0.911×, sign flips positive at H≥5);
vendor-pool undercount median 2.748× and UNSTABLE (IQR/median 0.53) — curated-universe dials
must never ship as absolute counts.

**The synthesis — the mechanism is real; the naive monetization is dead; both sharpen the
program:**
1. **The probability structure is extraordinary and forecastable.** Open-gap conditioning
   inside the N=1 cohort spans 3.19%→41.57% (holdout, 13× spread), reproduces its fit value
   to 0.32 pp on 1,251 fresh observations, and never leaves 19.7%+ in 16 years. The gap curve
   is monotone (no exhaustion hump). The ladder, the gap, and the six features all order
   events correctly.
2. **The T+1 auction prices the public conditioners almost exactly.** Every fillability-honest
   naive next-open book loses on holdout (E1 −0.384% / E3 −0.209% gross, worse after 15 bp),
   and expectancy is ANTI-monotone in the probability conditioner: the 41.57% cell has the
   worst open→close (−1.009%); the crowd pays the fair gap. **46.7% of realized main-board
   next-day boards open unbuyable** (N≥3: 75.0%; ChiNext N≥3: 83.1%) — the published ladder's
   most impressive cells are the least buyable (58.51% → 28.06% conditional on a fillable
   open). The blinded lane's F1 falsifier ("the auction prices everything") is CONFIRMED for
   the constructions tested — and per the ore law, ONLY for them (§ORE LEDGERs in both
   receipts name what remains open).
3. **Where the edge must live, if it lives** (Wave-2 charter §8, re-ranked): (a) SELECTION
   beyond public conditioners — L3 proves order-information exists (AUC 0.775) and lacks only
   regime-conditional calibration, whose cause is measured; (b) **entries the crowd cannot or
   will not take** — weakness entries (龙回头 C10, 回封 C3 — the 13,871-event failed-seal
   cohort is catalog-ready post-heal), where fills are guaranteed and adverse selection
   inverts; (c) the regime dial deciding when the game pays at all (L2's instruments; the 3×
   era swing dwarfs per-name features); (d) intraday moments daily bars cannot see — L1's g4
   cell has mean −1.009% against **median +0.372%**: a left-tail shape that intraday pullback
   entries could in principle cut, and the two collectors that see it (first-seal time,
   auction snapshot) are now respectively free and small.
4. **Risk architecture is now quantified, and it is severe.** Main N≥3 gapping below −3%:
   **50.0% close at the DOWN limit the same day** (n=142, survivors-only so worse in truth).
   Locked-down exits roll at up to 9.98% frequency (N≥3) costing −2.14% mean / −20.96% worst;
   one naive −17.3% mark was really −32.3%. The confirmed ladder (N≥2 entry) is a WORSE
   trade than N=1 (fillable subset adversely selected). Weekend fermentation is real in
   probability (+4.48 pp holdout, Wilson-disjoint) and **fully mediated by the gap** — it
   ferments into the auction price, not into post-gap drift.
5. **Data-plane truths this wave established:** `china_stocks_raw` is **BACK-ADJUSTED, not
   nominal** (on-tick share 36.4%→96.6% by year; 609/1,836 names on-tick throughout) — v0's
   header is wrong, its tolerance adjudication SURVIVES (p99 tick error 0.15% < 0.2% cushion;
   returns unaffected); v0's committed JSON still carries pre-reversal "strict is primary"
   prose contradicting its own MD — both need a small v0-corrections PR once #4999 merges.

**Program ore ledger (wave-level; lane ledgers in receipts):** UNTESTED at wave close —
intraday pullback/half-way (半路) entries; seal-break (开板) re-entries; 回封 conditioning
(C3); 龙回头 battery (C10); near-miss discontinuity (C12); cross-band telemetry (C15); 一字
queue-depth (C11); regime × anything crosses; zt_pool-universe replication of EVERY number
(F3 hangs over the whole wave: curated-slice survivorship could inflate the ladder itself);
onset book open-anchored accounting (L1 treated continuation only; L3's top-K cells never got
the fillability treatment); H>1 horizons; soft near-limit labels; theme/题材-resolved
anything (blocked on THS mapping). A null this wave closes ONLY: naive next-open gap-chasing
riders (E1/E2/E3, all bands, main+chinext, fit+holdout) and B1-as-specified.

### §6.2 WAVE-2 ADJUDICATION (Fable, 2026-08-09 — same session, post-operator-update)

**W2-B #5091 APPROVED CONDITIONALLY — the weakness families null cleanly; the null survived
adversarial review; several framing claims did not and are being amended.** 210 pre-registered
cohorts (final, post-amendment): **125 of 126 close-anchored cohorts negative** (the 126th —
a thin ChiNext volz cell, n=222, fit mean +0.023%, dc-t 1.17 — clears no stability floor) and
**0/42** 龙回头, and across ALL 210 cohorts the maximum date-clustered t is **1.86** (nothing
at ≥2) — that t-census, not any survivor count, is the null's statement.
(The receipt's original "23 vs ~52 coin flips ⇒ below chance" inference was REFUTED by review:
all 23 survivors sit in the one 84-cohort T+1-open family whose coin-flip expectation is ~21 —
at chance, not below — and the survivors are demoted by clustering, not by counting.) 龙回头
is unambiguous (holdout −1.37% net, date-clustered t −6.87) despite a real probability
structure — though per review the quoted "24.6% re-board ≤5 sessions" is a ROW-rate, not an
episode probability (day-1-per-episode holdout rate is 40.3%; episode-denominator Wilson is
2.6× wider) — Wave 1's auction-pricing null REPRODUCED in a second family. The close-entry
premise inverted: break-day closes LOSE ~1.07pp vs next-open on identical trades, and the
review made the mechanism claim STRONGER — on the correct paired population the overnight gap
is **−1.0745%** (holdout), closing the arithmetic to 0.6bp (the receipt's original −0.952%
included unfillable opens whose +9.99% mean gap diluted it). Only 0.48% of break days are
unfillable at the open — "guaranteed fill" buys nothing. Structural findings entering the
permanent record: **breaking the seal destroys ~80% of the ladder's edge** (回封 rate 3-4% vs
16.5% held first board — the seal IS the signal); trapdoor asymmetry (deep >3% breaks double
next-day limit-down to 2.73%); ONE lore item contradicted (no 3-6d 龙回头 sweet spot — hazard
falls from day 1; the second claimed contradiction — "declining pullback volume is worse" —
was itself refuted by review as day-in-window confounding and is DEMOTED to unstable); the
house tape's `lianban_count` is **hardcoded 0 on failed_up_seal rows** (silent-null trap;
panel-derive N); strict/tolerant event overlap is only 42.7% of union, and tolerant SEALS are
~28% of the shallow break band (a §9 survivor cohort is partly not a weakness cohort at all).
Review provenance: the builder's commissioned adversarial reviewer appeared dead (scratch
cleanup broke its rebuild) and the builder ran the checklist itself; the reviewer then
RETURNED with 8 defects (3 headline-framing MAJORs above, a pooled-basis volz-tercile cut, and
4 minors) — none moving the verdict, all being amended on the PR before it re-arms. Its
verification also independently CONFIRMED the regime dial's target-date indexing (the
builder's "mechanical" lookahead check proved less than claimed; the conclusion holds by the
reviewer's producer-level verification). Both the corruption-experiment standard AND
late-reviewer reconciliation are adopted house practice.

**W2-A #5093 APPROVED — the causal fix failed for a measured reason, and the simple object
won.** R2 (regime-conditioned isotonic) made things WORSE on both boards because the dial's
ordering INVERTS inside L3's 397-date calibration slice (0.773× vs 1.56-1.98× in fit/holdout)
— slice-fragility is the disease and the per-stratum fix re-caught it. **R0 — the 15-cell
连板 × i5-tercile lookup — posts the program's first positive Wave-2 skill on main (+0.061%
vs B0) and fixes the ChiNext over-prediction (2.577× → 1.118×)**; P2 (f3+N logistic, L3's)
remains the overall skill benchmark (+0.707%). Rulings: R0 = calibration-trusted display
object for main; chinext ships B0 unchanged; STAR stays THIN-SKIP (137 fit-core positives vs
the 150 floor — floor NOT lowered after seeing it; discipline held). **Two structural
findings re-rank Wave 3:** the dial is a **LEVEL instrument, never a RANKER** (constant
within-date ⇒ R0's top-K identical to B0's — regime tells you WHEN to trust and how much,
never WHICH name), and the dial is strongest on the **N=1 rung (1.670×)** — so the largest
expected effect in the program is the **L1 continuation-side regime merge**, not the onset
side. ChiNext coverage degeneracy printed (54.6% of fit sessions print no boards — curated-
universe thinness, F3's shadow again).

**Wave-2 synthesis.** Three entry families are now cleanly priced at daily resolution on this
universe: next-open strength (L1), break-day weakness (W2-B 回封), and pullback weakness
(W2-B 龙回头) — while the probability structure stays real and well-ordered everywhere it is
measured. What survives, in evidence order: (1) the **continuation-side regime merge** (dial's
largest measured effect + W2-B's broken-board T+1-open lead: +0.15pp over the sealed cohort,
sign-stable cells demoted only by the clustering judgment — not a zero); (2) the **intraday
battery** the operator's minute-bar purchase unlocks (L1's median-vs-mean left-tail shape);
(3) the **F3 full-universe re-run** (every W1/W2 number is a 1,842-name-curated,
survivors-only statistic; ChiNext's degeneracy shows the bias mid-measurement); (4) selection
depth via P2/B2-class models graded by the forward ledger. A kill this wave closes ONLY the
constructions named above; the ore ledgers in #5091/#5093 carry 24 untested variants between
them.

### §6.3 W3-A ADJUDICATION (Fable, 2026-08-09) — the daily-resolution chapter closes

**W3-A #5099 APPROVED** (full review cycle: 3 blockers + 9 fixes reconciled; peak-control
built so nothing remains untested; reviewer's predictions reproduced exactly). **Verdict: the
T+1 auction prices the WINDOW, not just the board.** 99 pre-registered cells, 10 clear the
bar, **2 survive the drift control and both are `peak_best` — the foresight upper bound**; no
implementable signal×horizon survives. The flagship cell (S3 big-day · ChiNext-20% · H=10)
clears the pre-registered bar in both windows (deq t 2.65/2.62) and **dies at the
matched-censoring, matched-date excess (t 1.75/1.98, median negative both windows) — "the
cell is not a finding," its own receipt's words.** Structural findings: **the big-day class
is ANTI-board** — the 连板 ladder multiplies P(board) 3.9× monotone while ranking P(big day)
DOWN (7.47→3.62%), and board-predicting features carry ~nothing for big days (f6 3.96× vs
0.73×) — a big up-day short of the limit is a different physical object from a board, so
soft-label onset modeling at daily resolution is closed; **the near-miss is BEARISH relative
to a matched seal** (C12: 0.38×/0.31× on next-day board, ~0.5× on windows) — sealing is
load-bearing, almost-sealing is not attention-positive; **half to 60% of threshold-touching
windows give the touch back before any scheduled exit** (O3−O2). **The foresight premium is
the program's bridge number: peak_best excess +2.03%/t 3.55 (H=10 holdout) is the measured
size of what lives inside the window that daily-scheduled exits cannot collect — the
intraday battery's target once minute bars land.** Defect archaeology worth keeping: v0's
10-day pair rule reused as a forward-chain rule truncated windows market-wide across
CNY/National-Day closures (the truncated tail averaged +11.03% net, 100% force-closed — the
whole first-draft flagship illusion); frozen quantile cuts are not their nominal quantiles
out of sample (0.000% ties — distribution shift, not ties); a `None`-coerced check predicate
could not fail (S7 class: verify checks can SEE failure).

**FOUR families now measured and priced at daily resolution on this universe** (next-open
strength · break-day weakness · pullback weakness · window targets), all through full
adversarial review cycles, all with the probability structure REAL and well-ordered
throughout. What stands per the ore law: the intraday battery (the foresight premium is its
sized target), the L1 continuation-side regime merge, the F3 full-universe re-run, the
forward ledger's live grading, and the collectors. Nothing in the exploration space is
closed beyond the constructions named in the four receipts' ore ledgers.

### §6.4 W3-B + W3-C ADJUDICATION (Fable, 2026-08-09, second session) — the regime axis
joins the priced family; the paper edge is measured against the buyable book

**W3-B #5142 APPROVED (amended).** The L1 continuation-side regime merge — the program's
largest measured remaining daily-resolution effect — returns a **structured null**: 0/78
pre-registered cells make the fillable next-open rider net-positive (the 21 THIN-clearing
cells: max dc-t **−0.17**, 21/21 net-negative in both windows), and the declared headline
cell (main·N=1·top dial tercile·E3) loses MORE when the dial is hot (holdout −0.961%,
dc-t −2.54). The dial's probability claim is confirmed at ORDERING level: fillable share
falls monotonically in the dial on 6/6 main rung×window cells (ordering violated 0/200
global-permutation draws, 1/200 era-preserving draws) while the P(next board) hot−cold
spread survives clustering (+9.50/+8.76 pp, clu-t 2.61/2.62, both windows). **The mechanism
is access rationing: the auction prices the regime by removing the fills** (main N=1 holdout
fillable 96.2→79.5% cold→hot; fillability tax 20.6→52.3%). The adversarial cycle (two
MAJORs: a single-draw permutation null quoted to 2dp against a 5-pp null SD; an S7-class
lookahead predicate keyed to a series that could not move) demoted all but 3/12 affirmative
magnitudes to DIRECTION-ONLY — era composition dominates the −16.74 pp flagship (within-year
permutation p 0.070; session bootstrap widens IID CIs ~6×, clustered t −1.64). The
broken-board T+1-open lead concentrates dial-hot (E3 holdout +0.999 pp, t 2.70) but is a
smaller loss, never a gain (own-book: 0 cells clear; E1/E2 sign-flip across windows, E3
alone sign-stable). Ore ledger: 15 constructions open.

**W3-C #5144 APPROVED (amended).** The onset fillability re-statement completes the
program's fillability-honesty debt: **all 90 main-board implementable cells are net-negative
in both windows, and every one of the 52 fit-positive paper cells flips under open-anchored
accounting** (exemplar B1·K=1·E1: paper +0.528% → implementable −0.405%, dc-t −2.72; the
sharpest single cell, 2014: paper +3.476% at 75.1% fillability → −0.190% implementable).
Rate survival 0.698–0.819 (median 0.748), capture survival median 0.704; ChiNext is nearly
untaxed (0.929) because its book barely selects boards. **Mechanism attributed: the 连板
ladder, not the six features, drives unfillability** — B0's rungs run fillable
99.91→93.00→83.44→71.21% with 一字 0.022→13.53% (−28.7 pp), near-monotone in P̂ for every
ranker (B1 reverses once at K=1→3, B2 at two decile boundaries; direction and magnitude
unaffected). The survivor book is a clean null — 0/180 (board×cell×exit) at dc-t ≥ 2 in both
windows, and the era tables show all 8 both-window-positive combos are positive **only in
2025**: the sign agreement is one ChiNext year, not a pattern. Review MAJOR (contained,
fixed two-sided): U2 paper books scored 2,697 trades on 停牌 placeholder bars —
`china_stocks_raw` encodes suspensions as zero-volume STALE-PRICE placeholder rows, not
missing rows (133,781 in-window); the `& y_ok` mask landed, max paper move 0.055 pp, U1
untouched, and the implementable books are proven placeholder-free (0 of 18,777 L1-parity
trades on non-live bars). All 11 gates now carry the exit code. Ore ledger: 19.

**Wave synthesis — the daily-resolution book closes end-to-end.** FIVE families measured
and priced (next-open strength · break-day weakness · pullback weakness · window targets ·
the regime axis), and the paper-vs-buyable gap is now a measured curve rather than a
caveat: model confidence and regime heat both price themselves through the T+1 auction
primarily by REMOVING THE FILLS — the two access-rationing findings (dial-hot availability
collapse; ladder-driven 一字 share) are precisely the objects the intraday battery's minute
bars can watch forming in real time, which sharpens (not merely survives) the case for it.
Nothing new is promoted; nothing new is killed beyond the constructions named in the two
receipts. **New house standard from this wave (binding on every future receipt): a
null-headline receipt must hold its affirmative asides to the same inference standard as
its nulls** — date-cluster or session-bootstrap every affirmative share/spread, permutation-
null every magnitude with an era-preserving arm beside the global one, and key every verify
predicate to a series that CAN move (S7-class defects surfaced in three consecutive waves;
the class is now a named check in review briefs).

## §7 Forward-ledger law (from Wave 1, standing)

Every probability the system emits is stamped (feature_date, predict_date, model_version, era
retro|live) and graded on outcome (binary: limit-up close at predict date; realized return and
near-limit recorded alongside, never blended into the grade). Append-only; **nightly is the sole
advancer**; fillability noted per row (P is for a CLOSE; entry requires a fillable open — the
rider lane owns that arithmetic). The calibration curve is the product's spine. Era-stamp
everything; Wave-2 wires the nightly advancer at the hook point L3 identifies.

## §8 Wave map (forward) — re-ranked at Wave-1 adjudication (2026-08-09)

- **W2 (next session), in priority order:**
  1. **Regime-conditional calibration** — L2 instruments as B1 covariates AND calibration-map
     conditioners (the measured cause of L3's miss); re-run the frozen-holdout evaluation once,
     pre-registered.
  2. **The weakness-entry battery** — 回封 (C3, on the healed 13,871-event failed-seal cohort)
     + 龙回头 (C10): the fillable-by-construction entries L1's null leaves standing. Open-
     anchored, locked-exit-honest, regime-conditioned from day one.
  3. **Onset book fillability re-statement** — L3's B2/top-K cells put through L1's open-
     anchored accounting (the onset side never got the fillability treatment).
     **DONE 2026-08-09 — #5144, adjudicated §6.4 (every positive paper cell flips).**
  4. **Cheap catalog constructions:** near-miss discontinuity (C12), 一字 queue-depth (C11),
     cross-band telemetry pilot (C15, post-2020 era).
  5. **Collectors (operator pre-authorized):** extend the zt_pool scrape with 首次封板时间 +
     涨停统计 (both on the current call — near-free); START the 9:25 auction snapshot (P5 — no
     history exists anywhere; every uncollected day is lost); probe vendor backfill depth
     (--backfill for the 3 missing sessions 06-29/07-09/07-22 + how far back it serves).
  6. **Nightly ledger advancer** wired at L3's identified hook (asia-close.yml after the CN
     Pick Lab step) — NOTE its commit step must learn to add the ledger's path (it adds
     `data/` and `site/`, not `research/`; either relocate the ledger to
     `data/cn_limit_lab/` or extend the add — decide at wiring, era-stamp the move).
  7. **v0 corrections PR** (post-#4999-merge): header basis → back-adjusted (with L1's
     tick-share evidence), JSON `definitions`/`why_strict_is_primary` prose → the MD's actual
     verdict, tape_crosscheck intersection-blindness note (L0's 9× finding).
- **W3 (opened early, 2026-08-09):** **W3-A WINDOW-TARGET BATTERY — SPAWNED** (branch
  `claude/cn-limit-w3-window`), operator-prompted: re-target the outcome from "board
  tomorrow" to the charter's rerating WINDOW (cumulative/peak ≥ {0.8w, 1.5w, 2.5w} over
  H ∈ {3,5,10}) and the big-day-short-of-limit class ([0.6w, limit)). Decision question:
  Waves 1-2 proved the auction prices tomorrow's BOARD — does it price the WINDOW? Boards
  are a window's unfillable spikes; the 6-8% days are its buyable flesh. Includes the C12
  near-miss matched comparison. Then: **L1 continuation-side regime merge** (W2-A's largest
  measured effect) — **DONE 2026-08-09, #5142, adjudicated §6.4 (structured null; access
  rationing measured)** — minute-bar intraday battery (post-Codex wiring), F3 full-universe
  re-run (post-expansion).
- **Event-taxonomy ruling (operator question, 2026-08-09 — recorded so no session re-litigates
  it):** on a 10% board the catalog decomposes as: close ≥ ~+9.78% (limit price × 0.998) =
  LIMIT-UP CLOSE (tolerant primary; the 0.2% is a feed-noise cushion, adjudicated, strict
  column parallel — a +9.9% pullback close already counts); touched limit intraday but closed
  below threshold = FAILED SEAL (13,871-event cohort, W2-B's battery, depth-banded — "up 10%
  at peak, closed 9%" lives here and is the seal-destroys-80%-of-the-edge finding); closed in
  [+9.5%, +9.78%) without touching = NEAR-LIMIT (2,017 events, rare — the distribution cliffs
  at the limit; f5 UNSTABLE); big up-day below 0.95w = feature-only until W3-A makes it an
  outcome class.
- **W3+/W4:** zt_pool-universe expansion (F3 is the standing threat: the ladder itself must be
  re-measured market-wide — labels exist in the vendor pool even where OHLCV doesn't),
  theme-relay v1 (blocked on THS concept mapping — 涨停原因 is NOT on the pool endpoint),
  cross-market rerate oracle (S5), LHB per-seat history (P3), display-tier site surface
  (designer lane, glance-tier language, "windows not certainties"), gauntlet promotion only
  when the forward ledger has ≥10 graded sessions.

## §9 DUAL-LANE PROTOCOL + DATA HORIZON (operator update, 2026-08-09)

**AMENDED BY OPERATOR ORDER, 2026-08-09 (second session), TWICE — FINAL STATE: the Codex
lane is ENDED ENTIRELY and this (Claude) lane is the MASTER SESSION for everything
limit-move.** First order: the Tushare wiring transferred here (Codex wiring failed) —
authority + plane architecture in `research/TUSHARE_WIRING_TAKEOVER_2026-08-09.md`. Second
order: integrate the full Codex handoff — the dual-lane protocol, including clause 1's
analytic blindness, is DISSOLVED; the reconciliation clause 4 reserved for the operator has
now HAPPENED. The reconciliation event, preservation receipts (five Codex branches pushed,
dirty range-shard campaign wip-committed), construction-by-construction verdicts
(convergent kills on daily riders + onset books across two independent stacks), the
two-tapes ruling, the universe-truth upgrade of F3, the exact-cent taxonomy adoption, the
two-ledger Monday grading, and the re-ranked master queue all live in
**`research/CN_LIMIT_ALPHA_RECONCILIATION_LEDGER_2026-08-09.md`** — read it with this
section; on conflict the reconciliation ledger wins over the paragraphs below.

**Two independent lanes now work this mechanism by operator design.** A Codex session runs the
SAME project in parallel — deliberately, for cross-comparison and reconciliation later ("fresh
eyes... different conclusions and perhaps different strategies"). Binding consequences for
every future session in THIS (Claude) lane:
1. **Independence is the product.** Do NOT read the Codex lane's strategy conclusions,
   adjudications, or receipts mid-program; do NOT converge designs deliberately. Convergence
   discovered AT reconciliation is evidence; convergence engineered before it is contamination.
   (Same logic as the §1.4 blinded brainstorm, now at program scale.)
2. **Infrastructure is SHARED; conclusions are not.** The Codex lane owns the data-plane
   build-out (below). Once its stores land on main, this lane consumes them freely — data is
   common ground; blindness applies to analysis artifacts only.
3. **Collision boundary:** this lane does not touch Tushare wiring, the universe-expansion
   surface, or collectors the Codex lane is building. Measurement scripts + receipts under
   `research/cn_prophet_audit/` with `cn-limit-w*` branches remain this lane's surface.
4. **Reconciliation is an operator-triggered event**, not a session's own initiative.

**Data horizon (operator purchases, 2026-08-09 — Tushare plan → 10,000-point tier +
add-ons):** A股历史分钟 (historical minute bars — unlocks first-touch/seal-stability/intraday
pullback constructions, v0 Stage-4 #3 and L1's top ore item), 盘前股本 (pre-market share
capital — unlocks the true turnover ratio, v0's f2 NULL, and float-normalized walls),
集合竞价成交 (auction matched volume — unlocks the 9:25 fill model and collector #2), the
打板 endpoint family, ST/risk-warning HISTORY (correct 5% band widths for the ST cohort —
currently excluded wholesale), and ~200k daily calls for modeled chip feeds (筹码分布/胜率 —
the M2/M4 chip-concentration footprints). The Codex lane is expanding `china_stocks_raw`
from 1,842 to the full ~5,400-name universe including ST + DELISTED — which directly services
falsifier F3 (survivorship/curation) and the §8 W3 re-measurement. **Until those land: Wave-2
receipts must stamp their store vintage (1,842-name era) so post-expansion re-runs are
comparable. After they land: the W3 priority is re-running the ladder + gap + fillability
core on the full universe (F3), then the minute-bar/auction constructions.**

## §10 Session-chain protocol

One wave per session; durable state lives HERE and in the continuation handoff
(`research/CN_LIMIT_ALPHA_CONTINUATION_HANDOFF_<date>.md`). Next session: read handoff →
masterplan → newest receipts; verify armed PRs merged; advance the wave map. Orchestrator stays
lean (builders grind; targeted reads only); the ONE blinded brainstormer per program has now been
spent — future fresh-eyes spawns require a new operator order.

## §10 THE PROPHET SCORING-LAYER OBJECTIVE (operator directive, 2026-08-09 night — the
program's named consumer)

**Operator's framing, distilled and binding:** the end goal is NOT a standalone limit-up
trading rule. It is to reverse-engineer the light, small signals around limit-up candidates
(sector, technical, washout maturity, earnings, chip structure, board ecology) and feed them
into the **Golden Influence / Prophet pick system's SCORING mechanism** — so that Prophet's
already-washed-out, already-high-quality picks get re-ranked by limit/blast-off propensity.
Prophet supplies the quality floor (loss-reduction); the propensity layer supplies the
winner-surfacing (upside-selection). Genesis case: Prophet ranked **300363.SZ #1 the day
BEFORE its 20% board** (2026-08-07); our ledger independently carries it at 25.5% vs 13.0%
ladder baseline on {vol-z20 3.31, run-up-5 +31.5%, sector-heat 7} — two systems seeing the
same object through different windows, before and after ignition.

**Why the program's nulls do NOT block this objective (and partly enable it):** every kill
so far is an ENTRY-family kill — the T+1 auction prices the PURCHASE of yesterday's public
information (access rationing, §6.4). Prophet's use case inverts the geometry: entries
happen pre-ignition at washed-out bases, so the holder OWNS the name when it boards — the
fillability tax and the auction-pricing null do not bind a position already held. What the
program has proven survives as exactly what a scorer needs: real order-information (AUC
0.775), sign-stable features, the regime dial (LEVEL instrument — trust-weighting, never
ranking), and the ecology instruments. Per the epistemics law, non-standalone factors are
retained as confluence inputs — this section names their consumer.

**Chartered lanes (evidence-ranked; display-tier freely, gauntlet only at promotion into
Prophet's live scorer):**
1. **P-A: Prophet-conditional limit study.** Assemble the historical CN Prophet pick/score
   panel (product artifacts — coordinate with the Terminal/charting-app data contracts; the
   Golden Oracle state stream, Re-entry/grey-dot events and regime blocks, is a candidate
   feature plane and needs a cross-repo read contract). Measure: P(board / big-day / window
   outcomes | Prophet pick, features) vs unconditional — does washout conditioning change
   WHICH features carry? Then the uplift battery: rank Prophet picks by candidate propensity
   scores, day-weighted top-K precision/lift, era tables, clustered t, holdout per the
   reconciliation §7 split. Deliverable: the feature shortlist with measured uplift on the
   PICK universe (not the market universe).
2. **P-B: 300363-class case decomposition.** The genesis case plus every Prophet pick that
   boarded within H∈{1,3,5} sessions of its pick date: full footprint decomposition (our
   f-battery + dial + ecology + chip/auction/minute planes as they land) vs matched
   non-boarding Prophet picks. Small-n honesty mandatory (Wilson, THIN labels); this is a
   hypothesis-generation lane feeding P-A's battery, never a promotion lane.
3. **P-C (after minute/auction backfills):** intraday confirmation features for the scorer —
   first-seal time, auction demand reads, wall shadows — the §8 intraday battery re-targeted
   at scoring Prophet picks rather than standalone entry.

**Target-class discipline (W3-A binding):** boards and big-days-short-of-limit are DIFFERENT
physical objects at daily resolution (ladder ranks big-days DOWN; feature carry differs
0.73×–3.96×). The Prophet scorer's outcome class must be pre-registered per board: on
ChiNext/STAR a 20% board IS the blast-off; on main the scorer likely wants the WINDOW class
(W3-A's rerating windows), not the board bit alone. Never pool them.

**Promotion path:** propensity features ship display-tier into research surfaces freely;
integration into Prophet's LIVE scoring passes the gauntlet (pre-registered gates on the
pick universe, both forward ledgers' live grading, and the standing law that the LLM/scorer
may only de-escalate calibrated keys — signals originate from measured artifacts only).

### §10.1 CONSTRUCTION SHARPENED (operator, 2026-08-10 — the thesis stated in full; this
subsection outranks §10's lane list where they differ)

**The operator's clarification, binding:** continuation is NOT the thesis — riding an
active ladder is the RETAIL side of the trade (limit-down reversal risk; "Russian
roulette"), and the program's own §6.1/§6.4 numbers are the measurement of that fleecing
(anti-monotone expectancy; hot regimes lose more). The ledger keeps accruing as a
calibration scoreboard — display-tier, zero marginal cost, never a promotion candidate.

**The thesis construction — pre-first-board onset from washout/basing states:**
- **Outcome class:** the FIRST board (ladder N: 0→1), and beside it the blast-off WINDOW
  class (W3-A rerating windows) — per board, never pooled (W3-A target-class law).
- **Conditioning states (the ore map; "sky is the limit" exploratory latitude applies):**
  (i) Golden-Oracle-style momentum confluence — MACD-RSI + Stoch-RSI on 2D/3D bars, using
  the Terminal repo's OWN indicator definitions (extract from charting-app; never reinvent
  — testing THEIR construction is the point); variants and relaxations explicitly in scope;
  (ii) washout states — drawdown depth/duration from rolling highs, sessions under the
  200MA, base length, SECTOR-WIDE washout breadth; (iii) washout-maturity per the existing
  `engine/china_basket_turn.py` lifecycle machinery; (iv) **accumulation footprints** —
  vol-z during the base, cyq_perf win-rate trajectory, and (as history accrues) the
  cyq_chips 筹码分布 concentration shifts — the direct instrument for the operator's
  insider-accumulation mechanism; (v) combinations (confluence × washout depth ×
  accumulation), because the mechanism story is conjunctive.
- **Mechanism hypothesis recorded (two-fold, operator's words distilled):** (a) sector-wide
  washout reversion; (b) deliberate hammer-down during negative sentiment → insider/
  institutional accumulation below intrinsic value → news release → rapid repricing. The
  accumulation phase leaves footprints in volume/momentum/chip structure BEFORE the board —
  finding those footprints IS the program.
- **The Prophet-shaped deliverable:** among names IN a conditioning state, which features
  rank the eventual boarders (day-weighted top-K precision on the state universe) — the
  scorer-uplift preview that P-A then re-measures on the actual Prophet pick panel.
- **Status honesty (recorded so no session re-litigates):** as of 2026-08-10 this study has
  NEVER been run and NEVER failed — every prior kill was an ENTRY family on post-ignition
  cohorts; the shipped onset model is ladder-conditioned (N≥1). W-P0 (washout/confluence-
  conditional first-board study) is the program's #1 measurement item, ahead of every
  continuation refinement.
