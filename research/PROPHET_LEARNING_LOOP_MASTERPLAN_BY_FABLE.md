# Prophet Learning Loop — postmortem forensics, exit-policy measurement, ledger continuity (masterplan by Fable)

Date: 2026-08-02 · Status: CHARTERED — operator-directed (2026-08-02 session, second directive:
"analyze BOTH our winners and losers… reverse engineer the exact root mistakes… build the
infrastructure for this to be regularly done… let your winners run and cut your losers short…
optimize for longer term capital returns… China track record wiped 7/30 — get our history back").
Program id: `prophet_learning_loop`. Sibling: `research/PROPHET_BOARD_PRIORITY_ENGINE_MASTERPLAN_BY_FABLE.md`
(same session, same PR). Evidence anchors: `engine/track_scoring.py` (#3664 three rules),
`research/US_BOARD_MEASUREMENT.md`, memory `backtest-horizon-swing-2-4-weeks` (horizon-ladder
STANDING rule), memory `us-board-definition-change-2026-06-25` (era-pooling trap).

---

## §0 ACCEPTANCE GATES (binding)

- **G1 — Postmortem engine produces root-cause rows for the operator's loser cohort.** Running
  `python -m scripts.prophet_postmortem` over the committed ledgers yields, for each of
  OLN 07-21 / AMKR 07-17 / IPGP 07-15 / STAA 07-15 / PSKY 07-01 / FN 07-21 / CDNS 07-09 /
  IPGP 07-10 / UNIT 07-21 / HL 07-01 / BG 07-17 (the 2026-07-31 track-record worst rows): a
  deterministic failure taxonomy, entry-time context (theme/sector state AT ENTRY from git
  history of `data/baskets/latest.json` + sector stage artifacts), visible-at-entry flags, and
  an anomalous-vs-systemic aggregation. A fixture test pins ≥ the IPGP double-admission
  detection — same ticker re-admitted ≤ 10 sessions after a prior episode that REALIZED a
  ≥ 8% loss (`prior_episode_loss`). That is the leg IPGP actually fires on, and it is
  HINDSIGHT: the first position was +3.04% green on the night the board bought the name
  back. The sibling leg `open_drawdown_at_readmit` (prior position already ≥ 8% under
  water AT the re-admission) is the buildable one and fires 0 times on the 2026-07-31
  window; both are costed, separately labelled, in the veto table.
- **G2 — Taxonomy is deterministic.** Every classification is a feature-threshold rule
  (documented in-module); no LLM anywhere in the classification path (A7: LLMs never originate
  signals). Multi-label allowed; every label carries its trigger values.
- **G3 — Exit-policy horse race is date-blocked and decomposed.** Same-entry-cohort comparison
  on matured US episodes: fixed H=10 (incumbent) vs H=21 vs trailing-stop family (ATR-k) vs
  target/stop (Prophet plan geometry), reporting per policy: expectancy, win rate, avg
  win/loss, MAE/MFE capture, and the **winners-kept vs losers-cut decomposition** (how much of
  the policy delta comes from extending winners vs truncating losers). Date-blocked CIs
  (engine/track_scoring date_block_ci or equivalent); overlapping-window caveat printed.
  Verdict language: DESCRIPTIVE ONLY — "policy X shows…", no "validated", no product change.
- **G4 — Track-scoring core untouched.** The three #3664 rules (forced verdict, symmetric
  maturity, date-blocked CIs) stay intact in `engine/track_scoring.py`; the horse race is a
  SEPARATE study reading the same episodes. The public track record's headline stays the
  incumbent rule until any change passes promotion.
- **G5 — CN ledger continuity restored.** `cn_track_ledger.json` (or a sibling artifact)
  carries the PRIOR-definition record (2026-06-30..07-29 cohort, ~1,082 board.parquet rows)
  graded under the same scoring core, clearly labeled as the previous board definition, NEVER
  pooled with the cn_prophet_v2 record (era-pooling trap, memory `us-board-definition-change`).
  The China dialog shows both: "current definition (accruing since 07-30)" + "previous
  definition (Jun 30 – Jul 29)". History visible again; honesty preserved.
- **G6 — The loop is institutionalized.** A recurring review protocol exists as a checked-in
  doc (`docs/PROPHET_POSTMORTEM_PROTOCOL.md`): when it runs (weekly + after any ≥3-loser
  cluster), what the artifact provides, what a Fable session does with it (adjudicate systemic
  vs anomalous; register candidate fixes via prereg; NEVER hot-patch score weights from one
  week's losers), and where verdicts are recorded. The admin surface points at the artifact.
- **G7 — No new authority claims.** Everything here is measurement/display tier. Any gate/veto
  born from forensics (e.g. "sector-headwind demotion") is registered as a candidate with its
  own prereg — explicitly NOT shipped in this program.

## §1 The reconciliation (fixed-horizon record vs "let winners run")

Two different jobs, two instruments — never one blended number:
1. **The track record** measures SIGNAL QUALITY: comparable, forced-verdict, fixed-H episodes
   (H=10 empirical; H=5 showed no edge). It must stay policy-free so eras and desks compare.
   It grows a **horizon LADDER** (10/21 now, 63 as records mature — descriptive columns beside
   the verdict horizon, per the standing ladder rule) so "does the edge extend?" becomes a
   printed fact instead of a debate.
2. **The exit-policy horse race (G3)** measures TRADE MANAGEMENT: on identical entries, what a
   holder-with-rules captures. This is where "let winners run / cut losers short" is tested —
   including the operator's hypothesis that impulse moves sometimes extend for months when a
   sector enters a larger bull move (the trailing-stop family is exactly the instrument that
   captures those without predicting them).
3. **Longer-term pick quality** enters selection only through evidence: the ladder + postmortem
   cohorts (e.g. theme-tailwind at entry vs 63d outcome) feed candidate features into the
   promotion pipeline (pick-lab books / preregs), never directly into live weights.

## §2 Postmortem engine design (`scripts/prophet_postmortem.py` + `engine/postmortem.py`)

- **Inputs:** `data/us_board_ledger/retro_grades.parquet` + `snapshots.jsonl` (entry rows,
  matured outcomes), closes caches (path context), git history of `data/baskets/latest.json`
  (theme state at entry date — 31 commits available), sector stage from the entry-date board
  row itself (spotlight/sector fields), signal fields captured in snapshots.
- **Per-episode output row:** ticker, entry_date, horizon, excess/abs return, MAE/MFE, and:
  - `entry_context`: theme id + reco + label + bull_days AT ENTRY; sector spotlight stage;
    extension state; tier; alpha; conviction band; days_since_signal.
  - `failure_labels` (matured losers ≤ −8% abs or ≤ −5% excess): each with trigger values —
    `sector_headwind` (theme/sector reco ∈ {avoid, trim} at entry — VISIBLE-AT-ENTRY),
    `bought_extended` (ext evidence at entry), `thesis_break` (base-broken flag date from
    hold-state history when reconstructable; else close crossed entry-row stop level),
    `gap_event` (≥8% single-session gap against the position — earnings/news class),
    `market_beta` (excess loss < 40% of absolute loss — the tape, not the pick),
    `re_admission` (same ticker re-admitted ≤10 sessions after a prior episode that was
    already ≥8% under water — `open_drawdown_at_readmit`, BUILDABLE — or that realized a
    ≥8% loss — `prior_episode_loss`, HINDSIGHT, the IPGP case),
    `idiosyncratic` (none of the above fired).
  - `visible_at_entry`: bool per label (could the engine have known?). A label whose legs
    disagree is NOT visible-at-entry as a label — `re_admission` is excluded on exactly
    that ground — and is costed one row per leg instead, each stamped `buildable` or
    `hindsight_upper_bound`. The per-ROW flag stays leg-specific.
- **Aggregations artifact** (`data/prophet_postmortem/summary.json` + a rendered
  `reports/prophet_postmortem_<asof>.md`): label frequencies, loss contribution per label,
  cohort splits (headwind-at-entry vs tailwind-at-entry loss rates + the SYMMETRIC winners
  split — what a headwind veto would have cost in missed winners: the operator's "don't weed
  out real winners" requirement is a first-class column, not a footnote), repeat-offender
  table, systemic-vs-anomalous read (label concentration across independent dates).
- **Admin surface:** the existing rudimentary admin Prophet panel gains a link/table reading
  summary.json (smallest possible admin change; the artifact is the product).
- **Winners get the same treatment** (≥ +8%): what did the big winners share at entry? Same
  labels, opposite sign — the learning loop reads both tails.

## §3 CN continuity design (G5)

`build_china_library.emit_cn_track_ledger` currently filters episodes to the live
`board_definition` (cn_prophet_v2 → 15 stamped rows → record reset on 07-30). Change: grade
the full parquet in TWO cohorts split on definition stamp (null/legacy = "cn_standout_v1
(pre-2026-07-30)"), emit `prior_record` block alongside the current one (same scorer, same
rules, separate n/summary), template renders both with era labels. Parquet is untouched
(append-only store; verified intact 2026-08-02: 1,097 rows, 06-30..07-31).

## §4 Build lanes (this session; new files — no collision with the priority-engine lanes)

- **M1 (builder/Opus):** §2 postmortem engine + §3 CN emitter continuity + G6 protocol doc +
  tests (fixture: the 11-loser cohort; IPGP re-admission pin; era-split emit).
- **M2 (builder/Opus):** G3 exit-policy horse race script + report + ladder columns where
  maturity allows; touches NO shipping engine besides reading; report committed.
- CN dialog template half of G5 → folded into the CN board UI lane (same file ownership).

## §5 What this program does NOT do

No score-weight changes from forensics findings; no new vetoes; no pooling of eras; no
"validated" language; no LLM classification; no admin rebuild (link + table only); no HK/CA
extension yet. Each candidate fix graduating from the loop gets its own prereg + verdict.
