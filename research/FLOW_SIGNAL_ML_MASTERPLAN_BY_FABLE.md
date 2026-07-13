# FLOW SIGNAL ML MASTERPLAN — outcome-labeled options-flow scoring (by Fable)

_Authored by Fable, 2026-07-12. Instigated by the operator's ask to learn from a competitor's
ML flow-scoring launch and integrate options flow deeper into the signal process and the
standout-stocks process. Grounded in a 7-lane research run tonight: 4 codebase censuses
(flow stack, Terminal, standout/spine seams, house-law constraints), 2 web-research lanes
(competitor decode, ML methodology), 1 Opus adversarial teardown of the competitor's claims.
This doc is the plan of record; lane outputs are summarized inline._

---

## §0 In plain English

A competitor (MomoEdge — identified with near-certainty; we hold their archived front-end
source in the sibling checkout `../momoedge_source_archive/`, OUTSIDE this repo — provenance:
operator-collected archive, Supabase backend refs intact) announced an ML engine that scores each options-flow print by
how historically similar flow actually performed, routed into separate models per days-to-
expiration, presented as a calibrated 0–100 score. Strip the marketing and the machine is:
**a fixed event detector → an append-only outcome ledger → DTE-bucketed supervised models →
calibration presented as the product → shadow testing before promotion.** That is sound
engineering, and it is *exactly the shape our house laws already prescribe* (display → shadow
→ gauntlet → promotion). Their headline numbers do not survive review (§1.2), but their
architecture does.

The decisive finding of the census: **we already produce a live flow-event feed** (per-print
premium, 252-day z-scores, sweep/repeat flags, vol>OI, DTE/moneyness buckets — the Terminal
Options Hub renders it daily) **but we never persist those events or grade their outcomes.**
`live_flow/feed_current.json` is a rolling snapshot. The competitor's moat is not their model —
it is their 126k-row outcome ledger, which only forward time can build. Ours starts accruing
the day we add one collector, and per-event history older than the R2 `live_flow/archive/`
48-hour prune window is permanently lost (same law as OI snapshots, doctrine §2.4 of
OPTIONS_ALPHA — which already cost this pipeline 12 accrual days in June: secrets outage
2026-06-21→07-03, OPTIONS_ALPHA §1 F1/§8). FS-0 therefore ships first and immediately.

Meanwhile we hold assets the competitor lacks: a 15-year EOD options store (OI 2012→, greeks
2017→), an entitled per-trade tape with bulk access (2 requests/root-day), a 26,693-fire
outcome-graded stock ledger, a 57,640-fire pre-gate pool, and an in-house approved ML pattern
(`engine/meta_label.py`: gradient boosting, purged/embargoed CV, calibration, default-off).
The program below builds the honest version of their product on our data — and a second,
faster lane they cannot copy: meta-labeling our *own stock fires* with flow features.

---

## §1 What the competitor actually built

### §1.1 Decode (from their archived source + public info)

- **Two systems share the "Oracle" name** (no relation to our internal Oracle program):
  swing-trade idea management (9-factor live confidence), and **per-print flow scoring** —
  versioned `score_v2…score_v6`, computed server-side at ingest, with new versions run in
  parallel columns before promotion (their "shadow testing" = our shadow tier).
- **Signal-logging gates** (what becomes a tracked "flow signal"): display score ≥68, premium
  floor (lowered for repeat-hit/ascending-fill clusters), size/OI ≥ 0.15, DTE ≥ 5 (0DTE
  excluded from signals), hedge/spread classifications excluded, static ticker exclusions.
- **Features**: execution type vs NBBO (at-ask/near-ask/sweep), sweep/golden-sweep/multileg
  flags, OTM% buckets, DTE, relative premium, IV pinned at ingest, cluster type
  (REPEATED_HITS, ASCENDING_FILL), **crowdedness** (`bull_premium_share_14d`,
  `signal_count_7d`), market tape (2/3/5-day net-premium cascade), MACD overlay,
  GEX-structure proximity (gamma flip / call wall / put support) in their structural engine.
- **Calibration table** (`score_expectations`): direction × score band → empirical outcome
  rates, minimum n=10 to surface. The announcement's "37% / 87.5% reached +50%" numbers are
  this table. The ML upgrade replaces stacked heuristics with DTE-routed models trained on
  the accumulated `flow_signals` + outcomes.

### §1.2 Adversarial teardown (Opus lane) — what to copy, what to refuse

| Claim | Verdict |
|---|---|
| Score by "how historically similar flow performed" | **Sound — copy.** Outcome-grounded scoring beats "how strong it looks." |
| DTE-routed models; "a 90 means the same everywhere" | **Sound — copy** (with per-bucket OOS calibration + reported n; the parity claim is earned, not declared). |
| Shadow scoring in parallel before promotion | **Sound mechanism — copy; refuse the 1-week duration.** One week spans no OPEX cycle and one vol regime. Our shadow window is gate-governed (n floors), not calendar-flattering. |
| "+50% reached: 37% (<60) vs 87.5% (90+)" | **Ruler artifact.** A 37% base rate in the *worst* bucket reveals a premium-touch MFE ruler ("ever reached +50%") — near-trivially achievable on convex long options; inflates every bucket. 87.5% ≈ 7/8 smells like a tiny-n bucket; no n, no CI, no OOS split stated. |
| "≈10× improvement" | **Unitless marketing.** No metric named. Never reproduce. |
| "History back to 2007; 120k+ signals" | **Reconstruction laundering.** Usable per-trade OPRA history to 2007 is implausible for a shop this size; early "signals" are almost certainly EOD-reconstructed pseudo-events — a train/serve mismatch dressed as long history. |
| "126k tracked outcomes updating daily" | Outcome *restatement* on a ratchet-only touch ruler (an outcome can only ever flip to success). ~1:1 with signals ⇒ single ruler, no horizon ladder. |

The honest version we can build and they cannot honestly claim: cohort-labeled history
(tape cohort vs EOD-proxy cohort, never mixed), verdicts on underlying-move rulers with n +
Wilson CI + per-era OOS, calibration as the product with the conditioning stated, and a
shadow period measured in accrued n across regimes, not weeks.

---

## §2 State of play, 2026-07-12 (evidence-linked)

**F1 — The live flow-event feed exists and is rich; per-event persistence beyond 48h does not.**
Producers: `scripts/live_flow_poller.py` + enricher (`com.mastermind.liveflow` /
`com.mastermind.flowenrich` launchd agents) write the R2 `live_flow/` blobs; the VPS `:8000`
flow service and Terminal's Options Hub (6 tabs: Tape/Tide/Tickers/Screener/Vol/GEX + PRISM)
are *consumers* via `/api/flow` with R2 fallback. Per-event schema already carries: `premium`,
`premium_z` (vs 252d baselines, `data/live_flow_baselines/`), `side` (~soft),
`signing_source:tape`, `swept`, `repeated`, `n_prints`, `vol_gt_oi`, `zerodte`, `dte_bucket`
(0d/1_7d/8_30d/31_90d/90p), `mny_bucket`, and a stable dedup key
(`_event_id(session_date,root,exp,strike,right,seq_max)`, `engine/live_flow.py`).
Retention reality (verified in code): `feed_current.json` is capped at the 2,000 newest
events; an hourly `live_flow/archive/{ts}.json` exists but is PRUNED AT 48H; an optional
`LIVE_FLOW_DAILY_SUMMARY` flag (default OFF) writes per-name *daily aggregates* (not events)
to `data/live_flow_daily/` + permanent R2. **No per-event table persists beyond the 48h
archive window; no outcome grading exists anywhere** (Terminal census: Supabase = user-data
only; retention delegated to the blob producer).

**F2 — EOD signed tape features shipped (T2a).** `engine/tape_flow.py` +
`scripts/build_tape_flow_daily.py` (#1358/#1431/#2253): per root-day net signed premium,
signed volume, DTE/moneyness buckets, vol>OI share, z252 columns; 375/375 roots on the
production runner as of 2026-07-10. Local store is a 1-root probe artifact; production truth
is runner-local + R2.

**F3 — Tape signing sub-gate is SUSPENDED.** `signing_gate.json` (asof 2026-07-04):
3 multi-session extension sessions ALL FAILED the 0.75/0.75 bar (agreements 0.67–0.72 on
2024-12-16 / 2025-01-14 / 2025-04-07); `production_ready:false`. Bar-source root gate remains
permanently `direction_reliable:false`. Consequences: net-direction *tone* stays soft (`~`)
everywhere; tick-rule-derived direction is not a hard feature. **Distinct and unaffected:**
the tape's own per-trade NBBO enables *quote-rule* execution classification (at-ask /
at-bid / sweep aggressiveness) directly — that is measurement, not tick-rule inference.
FS-0b carries a verification checkpoint (FS-C1) before relying on it.

**F4 — The 15-year history store lives off this box's main checkout.** The main checkout's
`data/thetadata_eod/_manifest.json` reads 0 roots — a *location* artifact, not absence: the
W-E0 backfill runs in the ops lane (`~/theta-ops-wt`; 88 roots / 87 complete at 15y as of
07-05 per OPTIONS_NW_ENTRY_INTELLIGENCE_MASTERPLAN §6 status 2026-07-05; the OVC robustness
study ran against a 174-root store on 07-06 per OPTIONS_ALPHA §8 2026-07-06). Current root
count TBD — re-verified at the FS-1 store-location step. R8 still binds: no
gate harness reads the store until its manifest marks complete. FS-1 carries a
store-location + manifest verification step (memory: untracked stores don't ride into
worktrees; local snapshots ≠ production).

**F5 — The stock-fire outcome ledgers are big and already graded.**
`data/signal_archive/track_record.parquet`: 26,761 fires, 26,693 with `fwd_mfe_21` +
`terminal_state_clean8_21` (CLEAN 31% / STOPPED 28% / DEAD_MONEY 24% / CUSHIONED 16%).
`data/replay/replay_boarded.parquet` (runner-local): 961,656 rows / 57,640 fires / 25,783
episodes, 2022-06-30→2026-07-02, with rejection taxonomy — the PRE-GATE standout pool.
Options stamps on `retro_grades.parquet` are young (47/950 GEX-stamped; skew/ivspread stamps
accruing since W-C; `opt_iv_rank_252` structurally null until backfill).

**F6 — The ML machinery is in-house and approved.** `engine/meta_label.py`
(HistGradientBoostingClassifier; purged/embargoed CV; deflated Sharpe; Platt; DEFAULT-OFF;
degrade-without-sklearn), `engine/hazard_score.py` (logistic + isotonic, live in cycle
hazard), `engine/validation.py` (`purged_folds`, `deflated_sharpe`, `brier_reliability`,
`platt_fit`), `scripts/oracle_onset_quality_w1.py` (sklearn logistic in a research lane).
**No house law bans trained statistical models.** The LLM origination ban is LLM-specific.
The binding constraints are: pre-registration, era partitions, FDR family accounting, A10
primitives as gate currency, purged CV, no sklearn on the nightly render path, display-only
until gate pass, Opus stats review before verdicts.

**F7 — Registered accruing constructions this program must compose with, not duplicate:**
S-VOI/S-VOI2 (vol>OI), S-IVSPREAD-F, S-SKEW_DECEL (skeptical prior), S-TOP_RISK, S-PIN_RISK,
S-VANNA-RELIEF, S-FRONT-CHARM, S-IVR, S-DOI, S-WALL, S-GEXR, S-CWIV, S-XZZ (family = 28
tests *as of the OVC amendment* — a living count that grows under the mandatory
amend-on-add + re-check clause, BH-FDR α=0.10). E1 verdicts binding on feature design: GEXR
sign is ERA-DEPENDENT (never a fixed-sign feature; era interaction mandatory); CWIV Era3 5d
alive (best-evidenced feature); DOI: the DO_NOT_REBUILD §2 "DOI family DEAD" row's scope is
the W-E1 construction tested — sector-level ΔOI persistence (0/12) — while the single-name
S-DOI registration stands in OPTIONS_ALPHA §4 and keeps accruing (no anchored weight either
way); skew-decel bullish premise unsupported (skeptical prior). Separately, DO_NOT_REBUILD
§4 holds **"Theta tape | SUSPENDED (Final3-lobes, 2026-07-06)"** — production consumption of
tape-SIGNED features stays gated on the failed multi-session extension (F3); FS-R6 scopes
precisely what this program may and may not take from the tape.

**F8 — Integration seams exist and are gated, mapped in census lane C:** stock_score entry
tilt (`_gex_confirm_tilt`, bounded ±0.5, keyed on gate.json `scored`), ivspread display chip
(gate-keyed), Oracle tilt (config-dark; W-F PARKED with its own unblock), NW Article-3
earn-in (n≥25 clusters + Wilson lift >1.25 → confirmer), EI Lane-A study charter
(LIVE_FLOW P4.3, not yet run), 4 live display-only confluence edges, and two zero-friction
Terminal seams (R2 `options_hub/tickers_ctx/*.json` field; `intel/v1` `tape.*` block via
`pull_macro_intel.py`).

---

## §3 First-principles design

**The product is a calibration table, not a model.** Everything else is scaffolding to make
one honest sentence per event: *"Of the N historically similar flow events (same DTE band,
same construction), X% preceded a ≥Y% move in the stock within H days (CI a–b%)."* From that
frame, the build order falls out:

1. **The detector defines the population** — freeze it, version it (selection effects poison
   labels when thresholds drift; detector version is a training-data artifact).
2. **The ledger is the moat** — append-only, PIT, keep-first, graded by forward time. Starts
   accruing on merge day; backfilled honestly by cohort (tape windows; EOD proxies) without
   ever mixing cohorts.
3. **Labels are underlying-move rulers** — triple-barrier on the *stock* at DTE-anchored
   horizons. Premium-touch (+50% MFE) exists only as a labeled display column for product
   parity; it is never verdict currency (§1.2).
4. **The model is a meta-labeler** — it filters/de-escalates events the detector already
   fired; it never originates direction. This is simultaneously the modern-ML best practice
   (meta-labeling) and the exact shape Signal Commons R3 permits ("survivors become
   de-escalation / conditioning gates").
5. **Calibration is the product** — DTE-routed models, isotonic on a temporal holdout,
   ECE<0.05 go/no-go, quarterly refits, reliability curves published with n.
6. **Promotion is a gauntlet, not a launch date** — display → shadow stamps on fires →
   pre-registered gate at n floors → survivors enter the named seams (F8).

Two lanes, matching the operator's two asks:

- **Lane FS (signal process): score the flow events themselves** — the MomoEdge-shape
  product, honest version, on our feed + tape + 15y store.
- **Lane FM (standout stocks): score our own fires with flow features** — meta-label the
  26k-graded-fire ledger / 57k pre-gate pool. Faster to statistical power than Lane FS
  because the outcome ledger already exists; blocked mainly on options-stamp coverage depth
  and the EI Lane-A charter, both already in motion.

---

## §4 Rulings (FS-R1…FS-R12 — binding until amended)

- **FS-R1 — The flow-event ledger is the spine; ship it first.** New collector persists every
  qualifying live flow event to `data/flow_signals/ledger.parquet` (append-only, keep-first
  PIT, single writer, `detector_version` + `signing_source` + full event schema from F1).
  Nightly grader computes DTE-anchored underlying outcomes as they mature. Display-tier
  freely (context-accrual law: a null never blocks building). Register producer in
  `run_status.json` + audit tripwire (silent accrual loss must page, doctrine §2.4).
- **FS-R2 — Outcome-ruler law.** Verdict currency = underlying-move rulers registered at
  prereg (FS-3): triple-barrier on the stock, horizons anchored per DTE bucket (0–7d events:
  5d; 8–90d: 21d; 90d+: 63d primary + 126d secondary — the long bucket's thesis window can
  exceed 63d, so the 126d ruler rides alongside, matching the A10 grid
  `fwd_ret/fwd_mfe_{5,21,63}` + `terminal_state_clean15_126` + house yardstick), absolute
  AND excess-vs-SPY reported. **One-grader law:** the FS-0 grader imports the shared
  primitives from `engine/grading.py` (forward metrics, barrier/terminal-state constants,
  fill conventions) rather than reimplementing triple-barrier; any divergence from the
  fire-ledger convention is documented in the grader header, else the FS-5 promotion seams
  inherit a silent grader mismatch. Option-premium touch columns (`prem_touch_50/100`) are
  display-only, labeled "path max, not P&L," never gate currency, never marketed without
  n + CI.
- **FS-R3 — Meta-labeling shape is mandatory.** The ML score filters/de-escalates
  detector-fired events; it never originates direction, trades, or escalation the detector
  didn't produce. Pre-gate, the score may not touch rank/size/gate on ANY surface (Signal
  Commons R3, RO-2); it ships as a labeled display probability with its conditioning stated.
  Post-gate, survivors act through the existing bounded seams (F8) — starting as
  caution-only/de-escalation per doctrine §2.1, symmetric escalation only via its own
  registered gate.
- **FS-R4 — Cohort law.** `(detector_version, source)` defines a training cohort: `live_feed`,
  `tape_recon` (per-trade tape windows), `eod_proxy` (EOD-reconstructed pseudo-events).
  Cohorts are never pooled in one training set (train/serve mismatch, §1.2); `eod_proxy`
  may pre-train / provide priors but calibration and OOS verdicts come only from cohorts
  matching the serving distribution (`live_feed`/`tape_recon`). Era partitions per the
  ratified amendment (greeks-dependent: 2017–19 / 2020–22 / 2023→; OI-only: 2012–15 /
  2016–19 / 2020–22 / 2023→); per-era OOS reporting mandatory; a claim alive only pre-2016
  is dead.
- **FS-R5 — DTE routing adopted.** Buckets 0–7d / 8–90d / 90d+; separate models at the
  extremes, single model with DTE interaction in the 8–90 middle band (volume-weighted
  pragmatism per the methodology lane); per-bucket isotonic calibration on a *temporal*
  holdout; ECE < 0.05 per bucket as go/no-go; no cross-bucket "90 = 90" parity claim until
  every bucket independently clears its registered OOS n floor.
- **FS-R6 — Signing authority restated per-source + scoped ruling on the Theta-tape
  suspension.** DO_NOT_REBUILD §4 row "Theta tape | SUSPENDED | Final3-lobes (2026-07-06)"
  stands and is NOT revived here: production consumption of tape-SIGNED direction features
  remains gated on the ≥5-passing-session extension (currently 0/3 passed, F3), and this
  program adds no such consumer. This ruling scopes what the row does NOT cover, per the
  kill-scope law (a suspension binds the construction suspended): (a) **quote-rule execution
  classification** (fill vs prevailing NBBO carried in the tape itself: at-ask/at-bid/
  aggression, sweep detection) is *measurement*, not tick-rule inference, and is legal on
  tape-sourced artifacts (RO-9); (b) **unsigned magnitude features** (premium, volume,
  vol>OI, DTE/moneyness structure) were never suspended; (c) **off-render research
  reconstruction** (FS-1) is not production consumption. Tick-rule net-direction stays soft
  everywhere: direction *tone* stays `~`; the model may consume soft direction only as a
  feature labeled with its measured error, never as a label. FS-C1 (checkpoint): verify bulk
  `trade_quote` carries usable per-print quote fields as the FIRST ops-lane action — if it
  does not, (a) collapses to unsigned features only.
- **FS-R7 — ML statute (first of its kind, mirroring the LLM law).** Trained statistical
  models may only **filter, rank within, or de-escalate** pre-registered detector/signal
  populations; they may not originate signals or act on any scored surface pre-gate.
  Mandatory: purged+embargoed CV (embargo ≥ label horizon; group folds by underlying AND
  time), uniqueness sample-weights for overlapping events, era-stratified OOS, registered
  trial count + deflated stats, isotonic/Platt on temporal holdout, frozen-detector cohorts
  (FS-R4), model artifacts versioned + hashed off-git (R2/gitignored per A4), inference off
  the render path (no sklearn in nightly engine modules — precompute artifact, render reads).
- **FS-R8 — Registration before computation; ownership boundaries respected.** The score is
  registered in OPTIONS_ALPHA_MASTERPLAN §4 as its own construction(s) (per DTE bucket ×
  primary ruler) BEFORE the trainer runs (era-amendment precedent). Per RO-12, §4 and ALL
  fire-ledger stamp columns belong to the options-alpha program: this program DRAFTS the §4
  amendment and the shadow-stamp cross-registration; they merge through the options-alpha
  boundary with Fable ratification, and every fire-ledger stamp write goes through the named
  A9 single writer `scripts/stamp_options_state.py` — no new writer. The FS-3 prereg must
  state the NEW total FDR family arithmetic explicitly (DTE buckets × era cells × rulers
  enumerated — a large multiplicative enlargement of the 28-test family, not a footnote),
  and re-check prior registered p-values at the new threshold per the W-C amend-on-add
  clause (currently vacuous — all prior buckets are `building_history` — but stated). N
  floors: ≥30 per condition bucket; ≥20 per era cell else ERA-SPARSE. Kill closes the
  construction tested, not the search space. Opus stats review mandatory before any verdict
  prints; Fable adjudicates promotion.
- **FS-R9 — Feature-legality inheritance.** Model inputs come only from PIT-clean stores with
  honest coverage windows; features tied to killed constructions obey the kill's precise
  scope (DOI per F7: sector-level construction dead; no anchored weight on the
  still-accruing single-name bucket either; skew-decel: skeptical prior; GEXR: era
  interaction mandatory, vol-conditioning not direction). Crowdedness features
  (`signal_count_7d`, `bull_premium_share_14d`-style) are adopted into detector v1 — cheap,
  high-value, computable from our own ledger (§1.1); adjacency note per RUL-2: these count
  *our own logged events*, mechanistically distinct from the killed ΔOI-persistence
  construction, documented as such in the FS-3 prereg.
- **FS-R10 — Terminal + site surfaces ride existing seams, display-tier.** PRIMARY seam =
  `intel/v1 tape.flow_score` via the Dashboard-owned stockdata → `pull_macro_intel.py`
  bridge (~5 lines, fully in our control). SECONDARY seam = the R2
  `options_hub/tickers_ctx/{ROOT}.json` field — zero Terminal code but its producer is the
  VPS `:8000` flow service outside this repo, so it ships only with an explicitly chartered
  VPS coordination step. Site surfaces (flow_desk / options screener / stock cards) show the
  glance-tier plain-word form per DESIGN_DOCTRINE (state + stance word + "based on N similar
  events" receipt on hover; banned-vocab list applies; EN/ZH; no `title=` translations;
  "validated" CI-guard respected). Debrand law: no competitor names on any user surface.
- **FS-R11 — Shadow is gate-governed, not calendar-governed.** Live shadow = the ledger
  scoring every new event + nightly realized-vs-predicted calibration monitor (decay
  sentinel, Oracle W-B4 pattern) + shadow stamp columns on the fire ledger via the A9 single
  writer. Promotion eligibility begins when registered n floors clear per bucket per era —
  not after a week.
- **FS-R12 — Zero new spend.** The program runs on entitled data (live feed, tape bulk, EOD
  store, massive aggregates). Procurement table of OPTIONS_ALPHA §6 stands; any new-data ask
  returns to its triggers. Heavy compute (tape reconstruction, training) runs in the ops
  lane / off render path with artifacts to R2 (render budget is law).

---

## §5 Waves

_Routing per CLAUDE.md: Sonnet builds, Opus reviews/stats, Fable adjudicates/merges. One wave
= one branch off fresh origin/main = one PR = same-day squash-merge. Grep ACTIVE_BUILD_MAP +
open PRs before dispatch (hot-program duplication law)._

| Wave | Scope | Acceptance gate | Owner |
|---|---|---|---|
| **FS-0 — Event ledger + grader (SHIP FIRST)** | `collectors/flow_signals.py`: persist qualifying events into `data/flow_signals/ledger.parquet` (append-only, keep-first on the existing `_event_id` key, detector_version stamped, single writer, all timestamps normalized to aware-UTC at parse). SOURCE PINNED: the local poller/enricher output is primary; R2 `live_flow/archive/{ts}.json` (48h prune window) is the only per-event backfill and is harvested at first run — history beyond 48h is gone, say so in the ledger README. Reconcile (not collide) with the flag-gated `data/live_flow_daily/` aggregate path. Nightly outcome grader per FS-R2 (one-grader law: import `engine/grading.py` primitives) with a **split-seam guard** on the price-store join (event→horizon window must be free of unrepaired split seams, or use the repaired series); premium-touch display cols where EOD option closes exist. `run_status.json` + audit tripwire; R2 plane if size demands (A4); print events/day so accrual ETAs become arithmetic. Tests added to the ci.yml pytest whitelist (they ride green otherwise) incl. tz-normalization + PIT leak-injection. | Ledger accrues from day 1; grader fills as horizons mature; PIT no-lookahead test (leak-injection pattern from W1.3); split-seam guard tested; zero render-path cost; nulls never fake-neutral. | Sonnet build, Opus PIT review |
| **FS-0b — Detector v1 freeze** | Codify qualification gates as versioned config (`config/flow_detector.yml` v1): premium floor, size/OI, DTE bands, hedge/spread heuristics, cluster/repeat windows, crowdedness counters (FS-R9); document each threshold's rationale; FS-C1 tape quote-field verification; detector_version rides every ledger row. | Detector deterministic + versioned; changing it = new version + full re-label law stated in the config header. | Sonnet |
| **FS-1 — Historical cohorts (ops lane, off-render)** | FS-C1 quote-field verification FIRST (FS-R6; the Theta-tape SUSPENDED row is honored — measurement-class features only, no tape-signed direction consumption). `tape_recon`: apply detector v1 to bulk per-trade tape over the R6 priority ladder (episode windows 2022→, ETF history 2017→, single names opportunistic; store-location + manifest verification per F4/R8 first); `eod_proxy`: pseudo-events (vol>OI bursts, premium bursts) from thetadata_eod after manifest-complete, era-partitioned, with the PIT leak-injection test extended to this cohort explicitly (OI is T+1 — a same-day vol>OI proxy can peek; base on prior-day OI). Both graded by the FS-0 grader; cohort-tagged per FS-R4. | FS-C1 result recorded; cohort sizes + coverage printed; no mixed-cohort table exists anywhere; R8 respected; eod_proxy PIT test green; 8-concurrent/window-stall law in ops lane. | Sonnet (ops) + Opus spot-review |
| **FS-2 — Field guide (before any ruler)** | Descriptive atlas over the ledger + cohorts: event taxonomy × DTE × moneyness × cluster × era base rates with n + Wilson CIs; institutional-practice writeup (who trades these prints and why); per-type playbook. Display-tier pages allowed (plain-word). The backtest rulers of FS-3 derive FROM this playbook (understanding-before-backtest law). | No effect-size claims below n floors; every table carries n + CI; ZH strings via Write/Edit only. | Sonnet draft, Opus review, Fable reads |
| **FS-3 — ML gauntlet prereg** | OPTIONS_ALPHA §4 amendment registering the score constructions (per DTE bucket × primary ruler), enlarged-family BH-FDR arithmetic, era specs, CV geometry (purged+embargo, group-by-ticker, CPCV for selection), calibration criteria (ECE<0.05, Brier vs base rate, reliability curves), trial count for deflated stats, kill criteria (e.g. per-bucket OOS AUC ≤0.55 in Era3, or calibration monotonicity broken, or all ruler CIs include 0), shadow n floors. | Merged BEFORE trainer code exists; Fable ratifies. | Opus draft → Fable ratify |
| **FS-4 — Trainer + calibrated scorer + surfaces** | Off-path trainer (LightGBM/HistGB per FS-R5/R7; uniqueness weights; monotone constraints only where mechanism-known: aggression, vol/OI); isotonic calibration; versioned artifact to R2; nightly off-path inference writes score field into ledger + `intel/v1 tape.flow_score` (primary seam per FS-R10; `tickers_ctx` only after the chartered VPS coordination); site glance-tier surfaces per DESIGN_DOCTRINE (EN/ZH via Write/Edit only); calibration decay monitor + `gate.json scored:false`. Shadow stamp column on the fire ledger: drafted here, cross-registered in OPTIONS_ALPHA, written ONLY by `scripts/stamp_options_state.py` (A9), and date-gated behind that writer's own coordination window (no qledger writes before the QI co-sign ~2026-08-29). New tests → ci.yml pytest whitelist. | Score visible nowhere as rank/size/gate input (grep-verified); UI carries "building history — N events, since DATE"; ECE + reliability in the gate.json evidence; kill-switch flag per P3.6 pattern. | Sonnet build, Opus review (incl. downstream suites law) |
| **FS-5 — Gauntlet + promotion** | At registered n floors: run the gate per FS-3; Opus stats review; Fable adjudication. Survivors wire per seam: stock_score entry tilt (±0.5 bounded, gate-keyed), evidence-stack vote, NW Article-3 earn-in path, Terminal tone upgrade. Failures: permanent display/confirmer, documented, construction-specific. | A10-aligned rulers only; BH-FDR family cleared; per-era survival stated; no "validated" without gate flip. | Opus stats → Fable |
| **FM-1 — EI Lane-A execution (parallel lane, standout stocks)** | Execute the chartered LIVE_FLOW P4.3 study: options/flow features (state.parquet + tape_flow z-cols as coverage matures) × the pre-gate pool (`replay_boarded.parquet`, 57,640 fires, 2022→) on A10 primitives. The FDR family entry belongs to the EI program: drafted here, ratified through EI ownership before the run; era 2022→ declared. POWER CAVEAT stated in the prereg: `state.parquet` holds only 3 as_of dates today — the feature join deepens as nightly accrual grows; the study runs when join coverage clears its pre-declared floor, not before. | Prereg first (EI-ratified); A10 currency; join-coverage floor met; survivors → chip-eligibility → promotion-prereg only. | Opus |
| **FM-2 — Fire meta-labeler (after FM-1 reads)** | If Lane-A shows cross-sectional content: register + train P(clean_liftoff / no-breach \| fire, flow features) on the graded fire ledger per FS-R7 — the de-escalation filter for the standout board ("this fire faces flow headwinds"). HARD PRECONDITION (measurement-lens law — do not spend an FDR trial on an unidentifiable construct): ≥60% opt_*/flow-feature non-null coverage on the graded fire universe per era cell before the trial is registered as spendable (today: 47/950 GEX-stamped ≈ 5% — null-by-construction territory). Composes with S-TOP_RISK/S-PIN_RISK rather than duplicating them (adjacency documented per RUL-2). | Coverage floor verified; registered post-Lane-A with its own FDR entry; caution-only until its gate. | Opus design, Sonnet build, Fable ratify |

Honest sequencing: FS-0/FS-0b are days. FS-1 tape cohort is the n accelerator (tens of
thousands of events without waiting years — labeled as reconstruction, per-source). FS-2/FS-3
run inside ~1–2 weeks. FS-4 ships display as soon as cohorts support a calibration table.
FS-5 promotion is gate-governed — realistic first verdicts where cohorts are deep (tape_recon
2022→) within a quarter; live-feed-cohort verdicts accrue behind them. FM-1 can start as soon
as its prereg merges (the pool already exists).

## §6 What NOT to build

1. No premium-touch (+50% MFE) ruler as verdict currency, ever (FS-R2) — display-only, labeled.
2. No unitless improvement multipliers ("10×") or bucket rates without n + CI + OOS flag.
3. No mixed-cohort training tables (FS-R4); no "back to 2007"-style depth claims from proxies.
4. No pre-gate score coupling to rank/size/gate on any surface (R3/RO-2); no fused pre-gate
   composite lift; no kernel conditioning before the NW clocks (R1/RO-11).
5. No hard direction tone while the signing extension is failed (F3); no signed-direction
   labels from tick-rule.
6. No unversioned detector changes (poisons labels); no calendar-declared "shadow passed."
7. No new data spend (FS-R12); no competitor naming on user surfaces (debrand law).
8. No duplication of registered S-* buckets — this program composes with them; adjacencies
   documented per RUL-2.
9. No sklearn on the nightly render path; no ledger writes except through registered single
   writers (A9).

## §7 Risks

- **Accrual fragility** — the ledger inherits the flow pipeline's outage history (12 accrual
  days lost 2026-06-21→07-03 to the malformed-secret outage, OPTIONS_ALPHA §1 F1/§8).
  Mitigation: FS-0 tripwires + run_status registration on day one.
- **Selection drift** — live feed thresholds upstream (poller/enricher) changing silently
  re-conditions the population. Mitigation: detector_version + upstream-config hash stamped
  per row; drift sentinel in the calibration monitor.
- **Tiny-n bucket theater** — the exact failure we red-teamed. Mitigation: n floors + Wilson
  CIs are rendering requirements, not just gate requirements.
- **Era fragility** — 0DTE/zero-commission regime is young and fast-moving; the 0–7d bucket
  retrains most often and is most at risk of decay. Mitigation: quarterly recalibration law +
  decay sentinel with a demotion path (W-B4 pattern).
- **Compute** — tape reconstruction and training are heavy; both are chartered ops-lane/
  off-path with R2 artifacts (render budget is law; RAM-freeze memory: never load the full
  EOD store into pandas on this box).
- **Program collision** — options-alpha owns §4 and stamp columns; Oracle owns rotation
  surfaces; EI owns the pre-gate pool studies. This program owns the flow-event ledger +
  detector + scorer. Cross-registrations named in each wave; serialize merges through main.

## §8 Status log

| Date | Event |
|---|---|
| 2026-07-12 | Masterplan authored (Fable). Research run: 4 census lanes + 2 web lanes + 1 Opus red-team (7 agents). Competitor identified as MomoEdge (archived source decoded); their headline claims teardown on record (§1.2). Key census finding: live flow-event feed exists with rich schema but no per-event persistence beyond a 48h archive prune — FS-0 chartered as the immediate ship. Rulings FS-R1…FS-R12 adopted, including the house's first trained-statistical-model statute (FS-R7). |
| 2026-07-12 | Two-critic adversarial review (Opus ×2: epistemics/law + architecture/feasibility), both SHIP_WITH_FIXES; all findings folded: source citations for ops-lane store counts + June outage; FDR family restated as living count with mandatory FS-3 enlargement arithmetic; Theta-tape SUSPENDED row cited + FS-R6 scoped ruling (measurement-class tape use only, no signed-direction revival); DOI kill scope reconciled (sector construction dead, single-name S-DOI accruing); §4/stamp ownership routed through options-alpha + named A9 writer; one-grader law added (FS-0 imports engine/grading.py); 90d+ bucket gains 126d ruler; OI-only eras enumerated; FS-0 source pinned (poller output + 48h R2 archive backfill bound, `_event_id` keep-first key, live_flow_daily reconciliation, split-seam guard, tz-aware-UTC, ci.yml whitelist); eod_proxy PIT leak test; FM-1 EI-family ownership + join-power caveat; FM-2 ≥60% coverage-floor precondition; Terminal seam primary = intel/v1 (Dashboard-owned), tctx behind chartered VPS coordination. |
| 2026-07-13 | **FS-C1 RESOLVED (positive), ahead of FS-1:** the local raw tape sample (`data/options_tape_signed/_sample_V_2026-07-02.json`, captured live from the build session with ThetaTerminal up) carries per-print `price`/`bid`/`ask`, and the existing signing builder already classifies `side=BUY: price>=ask / SELL: price<=bid` — quote-rule execution classification per FS-R6(a) is confirmed buildable. The Theta-tape SUSPENDED row remains honored (no signed-direction consumption). |
| 2026-07-13 | **FS-0 + FS-0b SHIPPED** (this PR): `collectors/flow_signals.py` (R2 48h-archive + feed harvest, keep-first on `event_id`, fail-CLOSED on unreadable ledger + dedup backstop), `engine/flow_signals_grade.py` (one-grader law: imports `engine/grading.py` fill/forward/terminal primitives; DTE-anchored horizons with partial-grade semantics so the 90p bucket's 126d secondary ruler fills at maturity; split-seam guard = split-shaped-AND-persistent signature on the adjusted basis — genuine large gaps pass through; PIT `today` truncation), `config/flow_detector.yml` (detector v1 freeze + re-label law), `scripts/build_flow_signals.py` (nightly: harvest → grade → gate.json `scored:false` → run_status + staleness tripwire), daily.yml step in the engine job (commit step's `git add data/` covers the store), ci.yml `flow-signals-ledger` job. 32 tests + 88 downstream green. Opus PIT review: SHIP_WITH_FIXES — B1 (126d ruler never fills), M2 (seam guard false-positived genuine >40% gaps on the adjusted series), M3 (fail-open re-ingest duplication), N5/N6/N7/N8 — all folded pre-merge. Accrual begins with the first nightly; per-event history before it is gone (48h archive prune). |
