# CN LIMIT-MOVE ALPHA — program masterplan (Fable orchestration)

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

## §5 Blinded brainstorm (ore-law §1.4)

Spawned this session (Fable, orchestrator gate, blinded to §4 and to all `research/` docs; given
charter + inventory + v0 summary only). Construction list lands here at adjudication, attributed
and unioned — convergence is evidence, divergence is ore.

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

## §7 Forward-ledger law (from Wave 1, standing)

Every probability the system emits is stamped (feature_date, predict_date, model_version, era
retro|live) and graded on outcome (binary: limit-up close at predict date; realized return and
near-limit recorded alongside, never blended into the grade). Append-only; **nightly is the sole
advancer**; fillability noted per row (P is for a CLOSE; entry requires a fillable open — the
rider lane owns that arithmetic). The calibration curve is the product's spine. Era-stamp
everything; Wave-2 wires the nightly advancer at the hook point L3 identifies.

## §8 Wave map (forward)

- **W2 MERGE WAVE:** regime × rider × onset crosses (the dial sizes the book); blinded-list
  constructions triaged in; theme-relay v1 if THS mapping lands; nightly ledger advancer wired;
  grading report v1.
- **W2/W3 COLLECTORS** (operator pre-authorized, per L0's field inventory): persist 封单/炸板
  history (extend existing scrape — cheapest, ranked #1 by v0 Stage 4), closing-auction
  imbalance, first-touch/seal-break times, THS concept membership snapshots.
- **W3+:** zt_pool-universe expansion (the 打板 game lives in the omitted small/ST names —
  labels exist market-wide even where OHLCV doesn't), cross-market rerate oracle (S5),
  display-tier site surface (designer lane, glance-tier language, "windows not certainties"),
  gauntlet promotion only when the forward ledger has ≥10 graded sessions.

## §9 Session-chain protocol

One wave per session; durable state lives HERE and in the continuation handoff
(`research/CN_LIMIT_ALPHA_CONTINUATION_HANDOFF_<date>.md`). Next session: read handoff →
masterplan → newest receipts; verify armed PRs merged; advance the wave map. Orchestrator stays
lean (builders grind; targeted reads only); the ONE blinded brainstormer per program has now been
spent — future fresh-eyes spawns require a new operator order.
