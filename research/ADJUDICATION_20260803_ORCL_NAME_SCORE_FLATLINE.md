# Adjudication 2026-08-03 — the ORCL name-score flatline (us_calls chip)

Status: ADJUDICATED (Fable main loop, 2026-08-03; adversarial Opus review applied).
Chip source: `POSTMORTEM_20260803_MAG7_RALLY_SILENCE_BY_FABLE.md` §2, us_calls row —
"ORCL flat score-0 for 32 consecutive days (separate observation, chipped)". Chip
hypothesis: stuck-input or ticker-mapping defect in the name_score scoring lane
(`engine/name_score.py` → `scripts/build_stock_library.py` →
`engine/name_score_grader.append_name_calls` → `data/name_score/us_calls.parquet`).

## §0. Verdict

**ORCL: premise false — no defect.** The flat row
(`score=0, tier=no_setup, fuel=1.000, trigger=0.000`, 29 ledger stamps = 23 trading
sessions 2026-06-29 → 07-30; the chip's "32" counted calendar stamps) is the
engine's designed deep-washout saturation zone with a **live, daily-moving input
feed**, not a frozen one.

**The chip's feared defect class is real — at scale — on other tickers.** A
run-length census of the ledger finds **216 frozen-feed echo rows across 17
tickers** (17 of them buy-tier): names whose price store stopped printing while
the nightly scan kept stamping "calls" daily. Worst specimen: **QCOM, stamped
`setting_up` score 54–75 every day since 2026-07-14 off a store dead since
07-10** — a live-looking, *varying* score (non-price inputs still move) on a
24-day-dead price feed. Fixed with a feed-staleness admission gate + a
measurement-side quarantine + tests (this PR). This is the
[[re-measure-a-brief-before-building-its-fix]] law in action twice over: the
brief's named ticker was innocent, and the real defect was bigger than the brief.

## §1. Why ORCL's constant is saturation, not a freeze (receipts)

From `data/stocks/ORCL.parquet` (fresh through 2026-07-31, 10,175 rows):

| asof | close | 52w high | off-high | 200dma | vs 200dma |
|---|---:|---:|---:|---:|---:|
| 2026-06-29 | 147.25 | 325.76 (2025-09-10) | **−54.8%** | 201.36 | **−26.9%** |
| 2026-07-15 | 132.49 | 325.76 | −59.3% | 192.35 | −31.1% |
| 2026-07-30 | 127.56 | 325.76 | −60.8% | 183.37 | −30.4% |

- **fuel = 1.000 exactly** because BOTH legs clip at their caps
  (`engine/name_score.py` `_HIGH_FULL=35`, `_MA_FULL=20`): −55%…−61% off-high and
  −27%…−31% vs-200dma saturate `0.6·nh + 0.4·nm` at 1.0. Constant-at-cap is the
  designed reading for a crashed name; it cannot vary until the drawdown shallows
  out of the cap zone.
- **trigger = 0.000 exactly** because the 148→115 waterfall held the cycle ladder
  in DECLINE, and `_TRIGGER["DECLINE"] = 0.00` — the anti-knife gate ("a
  still-declining knife gates to ~0", the design's founding rule). Score
  `= 100·trigger·(…)` is therefore 0 for as long as the decline persists. 23 flat
  sessions = 23 sessions of falling knife, which is the gate doing its job.
- **The inputs moved every stamp**: ORCL's `level` column prints 18 distinct
  values across the 29 stamps, tracking the store bar-for-bar (stamp date D
  carries the last close strictly before D; weekend stamps repeat Friday's).
- **The score responded the session the input regime changed**: the 2026-07-31
  stamp flipped to `score 13, trigger 0.15` = COUNTERTREND BOUNCE (0.30) ×
  entry `bounce_wait` (0.50) — the designed "bounce inside a downtrend — suspect"
  read on the +12.9% earnings-week bounce.
- **Cohort receipt (kills the mapping hypothesis)**: over the window, **54 names**
  print `fuel=1.0, score=0` on every row they appear, and 4 of them (LAC, NNE,
  OKLO, ORCL) held the fully-pinned constant across all 29 stamps with moving
  levels — the crashed-cohort saturation regime is populated, internally
  consistent, and price-tracking. A symbol-mapping or stuck-input defect cannot
  produce that cross-section. (Per-stamp universe in the window: 1,662–2,966
  names; 2,989 distinct tickers ever — the oscillation itself is chipped below.)

The postmortem's own §2 framing stands: "scan coverage was never the problem;
admission gates were doing their designed job." ORCL after a −55% collapse is
*hyperscaler-adjacent by name only* — as a chart it was a falling knife, and the
score is a buy-readiness screen, not a volatility meter.

## §2. The real defect: dead feeds re-stamped daily (fixed here)

Census rule (same as the shipped quarantine): a row is a frozen-feed echo iff it
sits more than 7 calendar days deep in a consecutive run of byte-identical
`level` values for one ticker (weekend/holiday stamps legitimately repeat a close
for ≤ ~4 calendar days). Result: **216 rows, 17 tickers, 17 buy-tier rows** —
two sub-classes:

- **Still-dead feeds** (store last bar → today's lag): SATS 2026-06-18 (46d;
  the chip-adjacent specimen — 33 echo rows at level 109.17), QCOM and HOOD
  07-10 (24d), MRVL 07-13, CVNA and HON 07-17, WDC 07-24; CTRA, CWEN-A, TCNNF,
  TPH have **no local store parquet at all** yet kept accruing rows. QCOM/HON/
  HOOD/MRVL/CVNA/WDC are live large caps — these are **collector-lane staleness
  defects, not delistings** (chipped below).
- **Healed windows** (store later backfilled): BLD, JCI, JHG, MMM, STX, WSR.
  Receipt — JCI: 13 stamps pinned at level 142.76 (07-16 → 07-30) while the
  backfilled store shows **11 distinct real closes** inside that window. Those
  13 "calls" were scored off a frozen snapshot that no longer exists.

Why it matters beyond hygiene: `grade()`'s forward-return join resolves each
call's ticker against the (current, healed) store — so a healed window's
fabricated calls grade against **real forward returns today**, feeding
`buy_tier_hit_rate` and `rank_ic` (`_BUY_TIERS = ("primed","setting_up")`), and
`engine/grading.resolve_series` extends delisted US names by their dead-name
terminal close, so even a never-healing dead feed is only *luckily* inert (SATS
is absent from the 419-entry dead-name store — today its echoes grade to None).

**Fix (this PR):**
- **Admission gate** — `scripts/build_stock_library.py` passes each name's own
  last-bar date (`rec["asof"]`, via the new testable `_collect_potential_calls`
  helper) as `bar_asof`; `append_name_calls` refuses a call whose `bar_asof`
  lags the ledger stamp by more than `_MAX_BAR_LAG_DAYS = 7` calendar days, with
  a `log.warning` naming the refused tickers. 7 is exactly the worst structural
  lag on the 2000–2026 NYSE calendar (post-9/11-class closure; strict `>` keeps
  it admissible; since 2015 the max is 4). A resumed halt re-opens the gate the
  day a new bar prints. Accepted residual: a >7-day market-wide closure would
  refuse one reopen-day stamp universe-wide (warned, self-heals next session).
- **Never silently dark** — a present-but-unusable `bar_asof` (NaT, unparseable,
  clock anomaly) keeps the call fail-open but emits a "gate DARK" warning: a
  format drift may never quietly delete ledger coverage OR quietly disarm the
  gate. `bar_asof` is admission input only — never persisted; ledger schema
  unchanged. Callers that pass no `bar_asof` (CN/HK/CA/INTL builders) are
  byte-identical in behavior; adopting the gate there is a one-line change per
  builder once each rec's own-asof field is verified.
- **Measurement quarantine (retroactive, mutation-free)** — `grade()` now drops
  frozen-echo rows (the census rule above, `_drop_frozen_echoes`) before
  scoring and **prints the count** as `n_frozen_excluded` — nulls printed, not
  hidden. The PIT ledger itself is never mutated; the 216 existing echoes stay
  as historical record but can no longer contaminate hit-rates, including via
  future store heals.
- **Tests** (`tests/test_name_score.py`): the ORCL saturation zone AND its exit
  response; gate refusal + the 7-day boundary + legacy-caller pass-through +
  schema unchanged; dark-gate warning on NaT/garbage/future `bar_asof`; the
  producer helper emits `bar_asof` (mutation-proofing the one-token emitter
  change); quarantine run-length semantics incl. weekend-repeat immunity and
  NaN-level immunity; `grade()` disclosure count end-to-end.

## §3. Boundaries honored, and what is deliberately NOT here

- **No ledger mutation.** The store is append-only PIT; repair-by-rewrite from a
  fix PR is a worse defect class than quarantine-at-measurement (and R2 is truth
  for `data/` — a repo-side purge would not survive the heal). Exclusion happens
  at grading, disclosed by count.
- **Display surfaces untouched.** `DO_NOT_REBUILD.md` (CSP ruling): staleness is
  handled by disclosure, never fail-dark. Stale names keep rendering their pages
  with their own `asof`; the disclosure obligation is met at the measurement
  layer (`n_frozen_excluded`) and in the nightly log (refused/dark warnings). A
  `stale` ledger column was considered and declined: schema stability, and the
  ledger records market observations — scanner state belongs in logs and the
  grade() output.
- **Chipped upstream, out of scope here:** (1) the US price collector let six+
  live large caps (QCOM, HOOD, MRVL, CVNA, HON, WDC) go 10–24 days stale —
  that is the load-bearing upstream defect; (2) us_calls ledger integrity —
  per-stamp universe oscillates 1,662 ↔ 2,966 across adjacent stamps, stamps
  2026-07-13/23/24 are missing entirely, and CTRA/CWEN-A/TCNNF/TPH accrue rows
  with no local store.
