# Experiments audit — 2026-08-26 (72 ready results tested and adjudicated)

Seven review lanes (6 Opus analysts + 1 Sonnet researcher, orchestrated by Fable)
re-derived every "ready" experiment's real state from its artifacts and evaluated it
against its pre-registered maturation criteria. Predecessor: the 2026-08-03 audit
(PR #4358, 29 results). Registry set: `site/marketdata/experiments.json` as of
2026-08-26 — 272 tracked, 72 flagged ready (24 Pick Lab US, 20 Pick Lab CN, 6 cortex
hypotheses, 22 individual track-records/calibration/gates/infra).

**Outcome: 66 seed entries updated** (verified `state` lines stamped
`state_as_of: 2026-08-26`, evidence-gated come-backs, corrected statuses/storage/
maturation), **3 superseding rows appended** to the cortex machine registry
(append-only; silently-terminal `insufficient-n` rows retired), **3 registry-mechanics
code fixes**, and the **follow-up defect docket** below. Post-audit ready count: 72 → 1
(the H5 cortex pass, deliberately left flagged — see §3). No promotions, no demotions,
no DNR kills: every read below is display-tier, and per house law these are
instrument-window verdicts, never market verdicts.

## 0. Registry-mechanics defects fixed in this PR

1. **`no_go` missing from both `_DONE` sets** — `engine/experiments_registry.py:40`
   and `admin/experiments.py`. A concluded-negative entry re-flagged ready every day
   forever (the H2/H3 cortex hypotheses). Both sets now `{validated, proven,
   gate_open, no_go}` and pinned together by
   `tests/test_experiments_registry.py::test_panel_done_set_stays_in_step_with_the_engine`.
2. **Terminal track-record verdicts flagged ready forever** — `_refresh_track_record`
   set `ready=True` whenever the artifact verdict was terminal, so index-leadership sat
   "ready" indefinitely after its read. Now a seed whose `status` records the verdict
   has acknowledged it (no flag); a verdict that *changes* re-flags. Test:
   `test_track_record_ready_clears_once_seed_acknowledges_the_verdict`.
3. **`insufficient-n` is a silent terminal state** in the cortex metabolism
   (`come_back` written once at registration; `load_due` only selects `registered`) —
   presented as forever-accruing/overdue. The three affected rows (H1, H4, Q1) are
   retired by appended superseding rows with `retired_note`s naming the re-arm
   condition; the structural fix belongs to the evaluator-repair item in §3.

`macro-tx-phase0` was the fourth mechanism case: `status: complete` is deliberately
NOT in `_DONE` (a complete study with a future come-back is a legitimate nudge), so
its truly-closed entry has `come_back_on: null` instead.

## 1. Pick Lab US (24 books) — live, none scoreable; 6 books measure nothing

All 24 advancing on the production scoreboard (`site/labdata/pick_lab.json`,
authority `display_only`); **every book ACCRUING** against the floor (n≥25 fires,
≥3 months, ≥6 distinct fire dates; earliest clear ~2026-10-13). Every matured 21d
observation comes from **7 fire dates in 9 calendar days (07-13..07-24)** — effective
independent episodes ~1–2 — inside a +2.75% SPY window where the random control's own
median excess was **−1.79%**: read nothing against zero, only date-matched lift vs
`plab_random_ctrl`.

- Provisional standouts (below floor, no verdicts): `quality_pullback` (+4.19pp lift,
  only positive median excess), `flagship_t3t4` (+2.02pp). Laggards: `edge_pure`
  (−5.79pp, the designed ungated ablation), `1d_sectorheat` (−1.30pp).
  `topping_avoid`'s inverse read: +2.9pp avoid-accuracy, inside noise.
- **6 books have never fired**: `sector_trough` (`sector_phase` 100% null →
  blocked), `revision_accel` (`implied_upside_pct` 100% null → blocked),
  `flow_leader`/`flow_washout` (upstream `site/flowleaders/leaders.json` stale since
  08-12 with `fire_a`/`fire_b` = 0 on every row → blocked), `otr_pullback` and
  `beta_squeeze` (gates individually satisfiable, intersection empty — unexplained,
  triage by 09-16). `leader_precipice` is near-dead (no fire in 28 days).
- Seed metadata corrected across the lane: real storage layout (monthly partitions +
  shared `fires.jsonl`/`grades.jsonl`; the seeded per-book parquets never existed),
  real first-fire date (07-13, not 06-15 — every prior maturation date was ~4 weeks
  optimistic), real metric names (`h21_wr_exc`/`h21_capture`/`vs_random_lift`; the
  seeded `hit_quality`/`upside_capture`/`coverage_health` exist only in the
  Standout-Accountability configs), real rulers (5 books are MFE/MAE-path or
  avoid-accuracy books, not `21d_spy_excess`).
- Snapshot cadence ~69% (22 of 32 sessions; a 4-session outage 08-03→08-06). Grader
  itself is healthy (grades through 08-26). No h63/path63 rows exist yet for any book.

## 2. Pick Lab CN (20 books) — advancing daily; the control is the headline

Same shape: **no CN book can leave ACCRUING before ~2026-10-10** (CNPL-R4 3-month
floor; `months_span` 1.54 everywhere), matured obs span 6 fire dates 07-10..07-27
(~1 independent episode).

- **`cnlab_random_ctrl` beat CSI300 by +5.18pp** mean 21d excess while the benchmark
  fell 3.7% — the ruler is currently measuring a breadth/size factor, not selection.
  Raw hit rates (rev_pure 91.7%) are dominated by it.
- **Two degenerate pairs** in the matured window: `1d_pure`≡`1d_phase` (70/70
  identical picks) and `rev_pure`≡`flagship_nogate` (24/24) — four rows, two results.
- **7 of 20 books produced zero evidence in 7 weeks**: 3 hard data gaps
  (`block_discount_recent`, `lhb_inst_seats_5d`, `archetype` all 0/42,598 non-null —
  blocked), 1 unit/threshold bug (`theme_laggard`: gate needs `theme_breadth_pct ≥ 80`
  but the breadth computation counts members with `ret_20d > 1.0` — wrong scale, max
  observed 16.67; blocked), 3 genuine regime nulls (`policy_put`,
  `capitulation_beta`, `1d_participation` — the last needs a vocabulary check).
- **`data_gap` reporting is inverted on total outage**: it derives from *fires*
  (`scripts/build_china_pick_lab.py:778`), so a fully-null feature → zero fires →
  `data_gap:false`. The three blocked books all report false.
- Provisional lifts (1 episode, no verdicts): `1d_pure` +2.06pp, `rev_coiled`
  +1.87pp; `star_20cm` −7.89pp, `1d_blastoff` −3.50pp.

## 3. Cortex hypotheses (6) — all evaluated; the instrument, not the data, is the finding

All six ran. But the evaluator has five wiring defects that make most verdicts
uninformative about their hypotheses:

- **W1 — the quarterly cortex FDR batch does not exist.** `scripts/quarterly_cortex_fdr.py`
  appears only in a docstring and a dag note. Zero batches ever; H5's "queued for FDR"
  has no consumer. (H5 is the one entry left flagged ready — an unconsumed pass — with
  the caveat that its "pass" is an absolute-floor base-rate artifact, not evidence.)
- **W2 — Path A never applies `feature:` conditions** — H2 and H3 returned
  byte-identical n/hits/metric for different features (no contrast group at all).
- **W3 — gate-semantics mismatch**: thresholds minted as differences/ratios are graded
  against absolute `hit_rate`, producing structurally unpassable gates (H2 ≤ −0.05,
  H3 ≥ 1.01) and trivially passable ones (H5 ≥ 0.05). The 08-05/08-11
  re-registrations carry the same gates and will fail identically.
- **W5 — Path B (walk-forward) is dead**: both entry-quality hypotheses returned
  `wf_n_names: 0` (price-panel join matches nothing) — H1/H4's `insufficient-n` was an
  instrument failure with ample n. Q1's null is real but a coverage null (its
  `spine_query` resolves 2 rows).
- **W4 — governance ledger clobber**: Q1's article3_review was committed 2026-08-18
  and removed 22 minutes later by a stale-working-copy rewrite of `governance.jsonl`
  (`f66a44bde106`). One confirmed instance; systematicity unaudited.

Registry handling: H2/H3 stop re-flagging via the `_DONE` fix; H1/H4/Q1 retired via
appended rows (re-arm conditions in their `retired_note`s); H5 left flagged.
**`rf-batch-b-cortex-watch`'s trigger has fired** (verdicts exist) but its next_step
now says: fix the evaluator BEFORE ingesting Batch B — the current verdicts are
instrument artifacts.

## 4. Core track-records (4)

- **index-leadership** — ledger ALIVE again (442 calls/14 dates; the dead-appender era
  is over; all three seeded wiring defects cleared in August). `verdict=validated` is
  the code correctly applying its pre-registered gate at h5 (running_ic +0.130, HAC-t
  3.30, 12 IC dates) — but honest episode-N is ~3 non-overlapping 5-bar windows, the
  IC is a within-group *rank* signal (RUNNING itself was flat vs SPY, mean_fwd_rel
  −0.0014), and h21 (4 IC dates) is null. Ledger still skips ~30% of weekdays. Re-read
  09-29.
- **shadow-book** — first h21 read exists (mean_ic +0.150, 618 obs / 23 dates) but
  **`scripts/mature_shadow_book` is wired into no workflow** (its sibling is at
  `daily.yml:4907`; `site/shadow/audit.json` has never been produced), the t=4.04 uses
  `hac_lags=6` against a 21-bar overlap (`engine/validation.py:721` documents exactly
  this inflation), the 23 dates are ~1–2 episodes in one rising tape, and `grade()`
  emits no Clark-West despite its docstring. Status → measuring; re-read 09-21 (h63
  matures ~09-17).
- **sector-central-grader** — substrate part-fixed (chain anchor + lane gates DONE;
  flat-denominator hit, kind-blind IC, weekend `as_of` stamps still present). The live
  21d scorecard (n=220, rank_IC −0.174) is **100% sector, 0 baskets** and ~1 episode
  with a 70%-bearish book in a rising tape — regime artifact, not measured anti-skill;
  flat-dropped honest hit is 0.253, not the published 0.168. **New blocker:
  `data/basket_levels/us.parquet` frozen at 2026-08-06** — baskets can never mature
  until the freeze lane is diagnosed. Stays blocked; 09-14.
- **ai-desk-tracker** — low-conviction n=48: hit .938 (vs desk's own placebo null
  .8922 → +4.6pp, below the 5pp bar), direction decayed .778→.667 (last 21 calls .524
  vs constant-bearish .625 on the same cohort). Conviction ladder cannot fill:
  132/132 theses are `low`, and **`theses.jsonl` has appended nothing since 08-10**
  (blocker). Id-collision fix landed (73 legacy duplicate rows remain unrecovered —
  recorded, not hidden). 09-14.

## 5. Calibration set (6)

- **calibration-hub** — the come-back question ("does the placebo pair cleanly on a
  fresh desk?") answered **NO**: Alt-Data 93/94 pairable kills promotion by
  construction; Stock Desk improved .33→.929 but 10/141 rows still unpairable. Board:
  0 calibrated / 1 unproven (AI Desk, +5pp, `p_dir_holm=.0197`, blocks 3/10) /
  3 inverted / 5 cold. `_conviction_read` still ranks raw hit-rate — Stock Desk's
  "medium ≥ low" is p=0.43 under the desk's own null. 09-17 (radar conviction cohort
  matures; radar has 177 open calls, all untiered — tier them or the ladder arrives
  untestable).
- **market-state-tune** — 19/20 graded; the first tune (~08-27) is a **deterministic
  "hold"**: the graded window contains zero 5% drawdown events (base rate 0.000),
  per-corroborator lift is empty (max firings 7 < MIN_SAMPLES 8), backtest 0/0/0 with
  all-false-positive risk calls, and `_backtest` returns recall 0.0 on an empty
  denominator (honest-nulls defect). Do not read the first tune as a verdict. 09-30.
- **froth-fragility-scorecard** — 0 of 35 rows graded because row 1's h42 maturity
  lands exactly on the 08-26 close (off by one bar — arithmetic, not breakage; the
  grader IS wired and lane-gated). The alert fires 25/35 (71%) purely on
  `narrowing_top` — non-discriminating. Comparator (vs ~0.512 base) still unbuilt;
  hook still `static`. First cohort peek 09-08 (~1 independent 42d block — a peek,
  not a verdict).
- **guidance-gap-ledger** — 3 rows in 4 months, all RAISING (no contrast arm), and
  **no resolver exists**: the forward-grading half is unbuilt, not unmatured. Re-scoped
  expectation; 11-30. Either build the T4-breadth resolver or stop promising a
  scorecard.
- **signal-sanity** — the registry entry described a firing-density forward experiment
  that **does not exist**; `engine/signal_sanity.py` is a ground-truth-free
  correctness tripwire (healthy: 261 baseline rows / 50 run-dates, ok=true). Re-scoped
  `kind` → `infrastructure_check`; a firing-density hypothesis needs a new experiment
  with its own forward log.
- **oracle-ratio-lens** — first ledger-health read DONE and healthy (346 rows / 37
  dates / all 15 pairs; 69 transitions; 277 one-sided days = 50% fire rate; prior seed
  state was 47 days stale). But RL-R9's pre-registered 21d/63d forward-outcome leg is
  **declared and unwired** — nothing forward accrues, so the 10-15 review cannot be a
  gauntlet read either.

## 6. Gates (5)

- **qledger-w6-radar** — gate **CLOSED on the merits**: 21d Wilson CI-low 0.3104 ≤ 0.5
  → auto-demote pinned 2026-08-26; duel lost 4.07% vs placebo 6.63% (like-for-like,
  n=39) and the duel has no conclusion protocol in code. Control leg still absent
  (0/11,378 claims), `fallback_no_ticker` placebo arm dead (0.0 on 120/120), no
  block-bootstrap, prereg criteria 3–4 unimplemented. **The 2026-07-28 readiness alert
  was un-fired (dedupe key deleted 08-04), not retracted — a written retraction is
  owed.** Status → blocked; 09-30 is repair latency, not accrual.
- **hkca-board-forward-ledger** — sub-wave 1b **COMPLETE** (HK
  `build_hk_library.py:1919`; CA `build_canada.py:751` — note: not
  `build_canada_library.py` as seeded). Gate now waits on 21d maturity **inside the
  current board-definition eras** (HK era from 08-04, CA from 08-19 — the era stamp
  reset the IC clock, `metrics_scope="current_definition"`). HK short-horizon in-era
  IC: 5d 0.207/10 dates, 10d 0.261/6. 09-15 (CA can't reach 5 IC dates before ~09-24).
- **ca-confluence-gate-calibration** — re-adjudication **cannot run**: the ledger
  persists no `tier_cascade` column (the flag's own variable), the analysis script was
  never regenerated, and the current era has 0 matured 21d rows (2 matured `take` rows
  ever, vs effN≥30). Unblocking is an instrumentation wave. Blocked; 10-31.
- **china-intel-hub-command** — **matured and the IC check has run**: 45 snapshot
  dates (gate ≥25 cleared); 21d pooled IC 0.391, daily mean 0.266, HAC t 2.806
  p 0.005 over 23 days (n=385); 5d/10d null; 63d 0 matured (first read 10-06).
  Coverage `below_floor` at every horizon (~15–16%) — defend or repair the denominator
  before any gauntlet step; `veto_blind` is not persisted so the pre-registered
  priced-only sub-read is not computable. Context-only stands.
- **macro-tx-phase0** — **CLOSED.** The docket action was done in the merging PR
  itself (`NW_FUTURE_LOBES_DOCKET_BY_FABLE.md:79`, commit `c61a83062767`, #1693,
  2026-07-06; conditions C1–C4; two-lobe cap binding) — the seed's "no evidence" was
  refuted by live read. `come_back_on` nulled; re-opened ≠ chartered.

## 7. Infra re-checks (7)

- **next3-analogue-library** — nothing built (`research/options/` absent); W-E0
  completeness needs a fresh check before the prereg. 09-30.
- **next3-reason-codes-after-c4** — still undispatched 23 days after the 08-03 audit
  found the same. Dispatch the 6-U3 additive PR or retire the item. 09-30.
- **rf-batch-b-cortex-watch** — trigger FIRED (15 registry rows; verdicts exist), but
  gated behind the §3 evaluator repairs. 09-09.
- **nwci-scanner-first-review** — `context_candidates.jsonl` has been 0 bytes for 7
  weeks of wired nightly runs (budget present). Targeted log check, not a triage
  session — distinguish "99th-percentile bar never crossed" from a silently swallowed
  step failure. 09-23.
- **nwci-indicator-personality-map** — blocker cleared 39+ days ago (#1891 merged);
  C1 simply never dispatched; target grid now ~242 signals. 09-16.
- **chf-first-edge-batch** — exactly ONE weekly edge batch ever (2026-W28, 35 edges,
  11 honest nulls); nightly frontier bookkeeping alive but the weekly scan stalled
  ~6.5 weeks. Needs ≥2 batches to mature. Diagnose cadence; 09-16.
- **china-native-w2-stores** — funding/CB/issuance legs stable and current;
  `etf_shares` full-universe width (≥1,607 funds) has held only since 08-17 (~6
  trading days of ~14 needed). Hold W8 ~one more week. 09-08.

## 8. Follow-up build-defect docket (NOT this PR — commission separately)

Ordered by leverage; each names its evidence site.

1. **Cortex evaluator repairs** (§3 W1–W5: apply `feature:` conditions; fix gate
   semantics; fix Path B's price-panel join; build or descope the FDR batch; audit the
   governance-ledger clobber) — until then every cortex verdict is an instrument
   artifact, and Batch B ingestion is gated on it.
2. **Flow-leaders lane staleness** — `site/flowleaders/leaders.json` `stale:true`
   since 08-12 with `fire_a`/`fire_b`=0 on every row; blocks two US pick-lab books and
   possibly the two Leader Radar books.
3. **`data/basket_levels/us.parquet` freeze (08-06)** — blocks all sector-central
   basket grading; same date/commit as the breadth `_closes_cache` incident
   (plausibly one event, unverified).
4. **Shadow-book**: wire `mature_shadow_book` into daily.yml; `hac_lags=21` at the
   grade() call; Clark-West (implement or drop the docstring claim).
5. **CN pick-lab**: fix `data_gap` derivation (inverts on total outage); fix
   `theme_breadth_pct` scale; wire the three null feature feeds (block discount, LHB
   seats, archetype) or retire their books; check the participation classifier's
   label vocabulary.
6. **US pick-lab**: trace `otr_pullback`/`beta_squeeze` eliminating clauses in
   `candidates.py`; snapshot cadence (~69%; 4-session outage 08-03→08-06).
7. **ai-desk theses append stall (08-10)** — the brief lane stopped feeding the desk;
   ladder cannot fill.
8. **qledger radar**: written retraction of the 07-28 alert; control leg; dead placebo
   arm; block-bootstrap.
9. **market-state `_backtest`**: recall must emit null (not 0.0) at `dd_days=0`.
10. **froth-fragility**: wire `hook='track_record'`; base-rate comparator before any
    hit-rate ships.
11. **guidance-gap**: build the T4-breadth resolver or formally descope.
12. **oracle-ratio-lens**: wire the RL-R9 forward-outcome leg or record the gap.
13. **HAC-lag sweep**: two lag conventions coexist (`index_leadership_track` correct,
    `mature_shadow_book` default) — sweep `ic_summary` callers per
    `engine/validation.py:721`.
14. **nwci scanner**: log check for the 7-week zero-candidate run.
15. **chf weekly edge-batch cadence** — stalled since W28.

## 9. Method note

Same playbook as 2026-08-03: lane workers re-derive state from artifacts only (seed
prose never trusted — `state_live`/`state_as_of` is the tell), run read-only
recomputes where the artifact's own numbers need checking, and propose; the
orchestrating session adjudicates, spot-verifies lane numbers against the artifacts
(six spot-checks, all agreed), and writes the seed. Statuses stay within the registry
vocabulary; every updated entry carries `state_as_of: 2026-08-26`; the top-level
`audited` stamp stays 2026-06-30 because only 66 of 257 seed entries were re-grounded.
