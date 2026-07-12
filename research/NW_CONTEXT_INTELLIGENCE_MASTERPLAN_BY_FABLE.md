# NW Context Intelligence — Masterplan (by Fable)

Date: 2026-07-08
Status: ADJUDICATED — waves W0–W5 chartered
Owner program: `nw-context-intelligence`
Charter (operator, 2026-07-08): integrate the personality/context layer deeply into the
Neural Web; build the infrastructure that can assess and spot cross-sectional patterns
through categorization as context accrues; use category-based patterns to assess risk;
bridge chart personalities to the technical indicator lab; give NW the amassed context
of an advanced human trader — base layer first, learning layer on top.
Standing law: `context-accrual-fundamental-goal` — context/tagging/accrual/detection
infrastructure ships display-tier WITHOUT edge gauntlets; gauntlets bind only at
promotion to authority. Nothing in this program is auto-rejected for lacking an edge.
Census: wf_b0495513 (6 lanes: indicator lab, NW machinery, stamping, context join,
ruling constraints, accrual math), 2026-07-08.

---

## 0. The architecture in one picture

```
LAYER A — CONTEXT SPINE (base infrastructure: make context universal, stored, joinable)
  A1 context_api: context_snapshot(ticker, date) — PIT "everything we knew"
  A2 coordinate stamps: fix + universalize (fire_coordinates repair, qledger stamps,
     personality+regime coordinates on spine rows)
  A3 accrual integrity: personality panel/forward-ledger heartbeat + gap sensors

LAYER B — DETECTION (learning layer: patterns/confluences/risk EMERGE from accrued context)
  B1 context scanner: nightly cross-sectional screens over pre-declared template
     families → context_candidates.jsonl (printed nulls, budgets, dead-stays-dead)
  B2 risk lens: board/universe personality-exposure profile × regime matrices → live
     display risk read (works TODAY with real numbers)
  B3 cortex intake: candidates + risk lens become cortex-readable context; cortex may
     stake hypotheses (fdr_family='cortex', 3/wk) — the sanctioned machine-discovery path

LAYER C — INDICATOR × PERSONALITY (which tools work on which animal)
  C1 lab bridge: personality-stratified indicator characterization (descriptive maps)
  C2 protocol: how future sessions run cells, account trials, and promote claims
```

**In plain English:** first we make sure every event the system records carries its
full context (what kind of stock, what regime, what mode) — that's the memory an
experienced trader accumulates. Then we build the machinery that reads across that
memory nightly, prints candidate patterns and a risk read, and hands them to the
brain (cortex) and to humans as *candidates* — never as auto-truths. Separately, the
new indicator lab gets a personality dimension so we learn which tools fit which
animal. Truths are promoted only through pre-registration; but detection and accrual
are never blocked.

---

## 1. Rulings (R-CI series)

- **R-CI1 — Charter + tier.** Program ships at display/context tier end-to-end
  (`horizon_role: context`, `scored_path_surfaces: []`, `weights: none`), modeled on
  R-ORTH. Article 2 binds: outputs may ANNOTATE any surface; they may never rank,
  size, gate, or raise attention floors until a family individually earns
  SHADOW-with-track-record through pre-registration. Per the standing
  context-accrual directive, no wave of this program requires an edge to ship.
- **R-CI2 — Repair before build (red-team-corrected diagnoses).** W1 fixes the
  coordinate layer before any new tissue — a context layer that silently accrues
  nulls or leaks poisons every future study. The verified state:
  (a) `fire_coordinates.jsonl` has never been produced on host, and its
  `_CONTRIB_PREFIX = "contrib_20d_"` bug is CONFIRMED (real panel columns are
  `contrib_<stream>_20d`; the match set is always empty — silent-empty, not crash).
  Fix the prefix logic.
  (b) `dna_class`/`style_regime` ARE live frozen panel columns
  (`build_factor_panel.py:2245/2249`; the census stamping lane misdiagnosed this).
  If fire-coordinate values print null on host, W1 DIAGNOSES FIRST (suspects: the
  exact date+ticker panel-row match against monthly partitions; partitions
  predating the P1-C freeze) — the panel remains the source of truth; no
  re-sourcing.
  (c) qledger registration-time stamping WORKS (`_prepare_claim()` reaches
  `_regime_stamp_for_asof` on both register paths; 3,882 of 9,655 live claims now
  carry quads). The wall is source coverage: `data/regime/regime_vector.parquet`
  holds only ~3 rows (2026-07-01+), so older asofs stamp null. W1 runs the
  EXISTING `qledger.backfill_regime_stamps()` against
  `data/regime/regime_history.parquet` for historical claims — with the R-CI3
  provenance rule below — or prints the honest null for unstampable asofs.
- **R-CI3 — One stamp vocabulary, with provenance.** The universal coordinate set
  for event rows: `{quad_hard_label, vol_regime, risk_radar_state, rate_pressure,
  fused_risk_label, vector_asof}` — the SPINE-STORED subset of the producer stamp
  contract (producers keep the full 8-key `_REGIME_STAMP_KEYS` including
  `regime_vector_degraded` and `staleness_hours`; new producers must not drop
  them) — ∪ `{archetype, dna_class, chart_primary, micro_primary, modes}`
  (personality coordinates). Stamps are applied by the PRODUCING lane at write
  time where a producer exists, and by `build_index()`-time as-of joins for
  historical rows (the `_stamp_historical_quads` precedent, extended with
  `_stamp_personality()`).
  **Provenance law (red-team):** every backfilled/reconstructed stamp carries its
  basis. Backfilled qledger regime stamps are `regime_stamp_basis =
  'recomputed_history'` — NEVER `pit_live` (only claims stamped at true
  registration time, post-fix, earn `pit_live`; the default `regime=` filter
  population must not be polluted — query.py:1465). Personality coordinates carry
  `personality_basis ∈ {pit_labels, snapshot_not_pit, absent}`:
  the 223 PIT-deep names join at event date from the PIT labels parquet
  (`pit_labels`); ALL OTHER names are stamped ONLY when the row's as_of falls
  within the production snapshot's freshness window (≤5 trading days), marked
  `snapshot_not_pit` — historical rows for non-deep names stay `absent`. Today's
  snapshot is never silently applied to yesterday's events.
- **R-CI4 — context_api is read-only and honest.** `engine/neuralweb/context_api.py`
  exposes `context_snapshot(ticker, date=None)` and `context_frame(tickers, date)`:
  a PIT as-of join over the census-mapped dimensions (personality PIT labels +
  production aggregate; archetype history with asof-gate; regime history; sector→
  oracle node + episode state where derivable; factor panel 2025-06+; attention;
  insider filing-date-gated; SI; options stamps 2026-06+; spine signals). Every
  dimension returns value + as_of + coverage or an explicit absent-marker; missing
  host-only stores degrade to absent (CI-runner safe). It never computes new
  signals — it JOINS what exists. This is the "amassed context" substrate every
  future lobe, study, and cortex tool reads.
- **R-CI5 — Detection = pre-declared template families, not free mining.** The
  nightly context scanner (B1) runs ONLY registered screen templates, each a family
  with a declared trial budget (TrialLedger `log_declared_budget` BEFORE first run;
  new slug `context_scan` registered in `config/ruling_graph.yml
  meta.known_fdr_families` in the same PR). v1 templates (frozen):
  T1 *composition drift* — fire/board composition vs universe by personality cell
  (the field guide §5 measure, computed forward nightly);
  T2 *outcome heterogeneity* — graded spine rows split by personality × regime
  cells at the cells' pre-declared rulers, printed as percentile-vs-null;
  T3 *co-occurrence shift* — label co-occurrence and mode-transition frequencies vs
  their trailing baselines.
  Anti-mining hygiene binds every template: within-window nulls (contiguous-block
  resample ≥200 draws; percentile display, never raw thresholds), era splits,
  sample floor n≥50 (insufficient_n printed), calendar-time controls in any primary
  (DT-R14), duplicate collapse in the fixed order (oracle compounds → species →
  machine_registry → trial-ledger strings **→ the context_candidates archive
  itself**, so a decayed candidate re-derived later is collapsed as seen-before,
  never re-printed as novel), `adjacent_falsified` named before first compute,
  dead-stays-dead, respin cap 2, printed candidate counts every run.
- **R-CI6 — Candidates are context, promotion is prereg.** Scanner output goes to
  `data/neuralweb/context_candidates.jsonl` (display) and into cortex-readable
  context. Three legal exits for a candidate: (a) cortex stakes it as a hypothesis
  (metabolism, fdr_family='cortex', 3/week chokepoint, graded only on
  post-registration data); (b) a human charters a pre-registered study (rulers
  derived FROM the candidate's claim); (c) it decays (candidates unrefreshed for 60
  days are archived, printed — and remain in the scanner's dedupe corpus per
  R-CI5, so decayed ideas cannot silently re-emerge as new). The scanner itself NEVER escalates, scores, fuses
  (Signal-Commons R3: no composite of axes), or writes to any Article-2 surface.
  Labels-before-models law: no classifier/router over candidates until registered
  floors are met.
- **R-CI7 — The risk lens is display arithmetic, live now.** B2 computes the
  personality-exposure profile of the board/universe nightly: composition ratios vs
  universe, dispersion-weighted label-trust, weighted vol/beta/MaxDD/never-recover
  from the field-guide fingerprints, regime-conditional tail read (current quad ×
  liquidity row of the §3 matrices, only cells with adequate n), tinderbox /
  negative-gamma / event-window shares. Census worked example (2026-07-06 board):
  2.84× overweight `high_beta_momentum` (Q1 P10 −10.4%), 1.63× overweight
  `speculative_unprofitable` (label-trust lowest, dispersion 0.544), 
  underweight financial (0.60×), rate_sensitive (0.52×), cyclical (0.49×); weighted board P10(21d) ≈ −7.8% in
  the current Q1+expanding cell. All figures print with n and the survivorship
  watermark. No cell without adequate n renders a number.
- **R-CI8 — Kernel stays fenced.** Personality/context conditioning of kernel cells
  is BLOCKED until the 2026-10-01 kernel-FDR batch (Signal-Commons R1; ruling-graph
  lines 2450-2468). This program adds NO kernel cells and NO kernel consumers.
  Chartered clock: at the 2026-10 batch, evaluate personality-conditioned kernel
  cells as a batch entry — only if the forward ledgers carry adequate stamped n.
- **R-CI9 — Indicator-lab bridge waits for the lab's merge, then stratifies.** The
  lab is another session's open PR (#1840 + draft #1891, worktree tender-lamarr) —
  we do not touch their branch. On merge: C1 adds a personality dimension to the
  lab's characterization plane (join per-(ticker,date) signal fires to PIT labels;
  per-cell descriptive fire-metrics with era splits + null percentiles, mirroring
  `indicator_characterization.json`'s regime map), writing
  `data/lab/personality_cells.jsonl` + a `by_personality` block in tech_lab.json.
  Descriptive maps only (field-guide grade) — the 46-signal × 9-chart-label grid is
  a characterization plane, not 414 hypotheses; ANY cell promoted to a claim
  requires its own prereg with declared budget. Seeding doctrine (from playbook
  PB-L9): reversal-family indicators are expected at home on rubber_band +
  slow-MR-micro names, trend/breakout families on leaders/accumulators, event
  hygiene on gappers — the map measures whether the doctrine holds; it does not
  assume it.
- **R-CI10 — Accrual clocks are the program's spine.** From the census math: board
  buy-entry cells power (n≥50) in 2–82 days for most archetypes; T3 leader cells
  need pooling (a pre-declared `clean_uptrend` collapsed bucket =
  stair_step_leader ∪ smooth_compounder_grind for gate-tier studies); regime cells
  are usable now descriptively. Every wave registers its come-back in
  `data/experiments/registry_seed.json` (no bespoke clocks).
- **R-CI11 — Cortex context enrichment is additive and bounded.** Cortex gains
  read access to context candidates + the risk lens (new read tool or world_state
  sub-blocks), sized top-K (≤20 candidates), never per-ticker dumps. LLM law
  unchanged: cortex may summarize, flag attention, and stake hypotheses through
  metabolism; it never originates signals/scores (A7 ban).
- **R-CI12 — Verification of the accrual plumbing.** The personality forward
  ledger has zero rows because 2026-07-06/07 printed no buy/rebuy fires — plausible
  but UNVERIFIED plumbing. W1 adds a heartbeat: the NW health builder notes
  `personality_forward_ledger: {rows, last_append, fires_seen_since_wire}` and
  flags if fires occur without ledger appends. Same heartbeat for
  fire_coordinates after its repair. (Accrual that silently fails is the program's
  single biggest risk.)
  - *RESOLVED 2026-07-12 (come-back check):* the "no fires on 07-06/07" premise was
    an artifact of track_record's own append lag — buy/rebuy markers are held back
    while `quality == "pending"` (anti-repaint), so TTD's 07-06 fire only entered the
    parquet in the 07-10 commit and SBUX's 07-07 fire in the 07-12 commit. Both DID
    fire. The same lag made the W2b stamper's `date == build_date` filter a permanent
    no-op (a fire's row never exists in the parquet on its own date) — the ledger
    would have stayed empty forever. Fixed same day: 30-day lookback +
    (ticker, date, type) dedup + `stamped_on` column in
    `scripts/build_stock_library.py::_stamp_personality_forward_ledger`. R-CI12's
    feared failure mode ("accrual that silently fails") was REAL and is exactly what
    the heartbeat must watch: `fires_seen_since_wire` must count fires by row
    *presence* (any recent-dated buy/rebuy in track_record), not by same-day match.

---

## 2. What exists vs what this program builds (census ground truth)

| Piece | State today | This program |
|---|---|---|
| Personality tags | Live nightly (1,719 names; PIT labels 2.1M rows/223 deep names; forward ledger wired, 0 rows — no fires yet) | A3 heartbeat; coordinates onto other ledgers (A2) |
| fire_coordinates.jsonl | NEVER produced on host; contrib-prefix bug CONFIRMED; dna/style nulls need diagnosis (panel columns exist live) | W1 prefix fix + diagnosis-first + personality/regime enrichment |
| qledger regime stamps | Stamping WORKS (3,882/9,655 claims stamped); wall = regime_vector.parquet ~3-row coverage | W1: run existing backfill_regime_stamps from regime_history with basis='recomputed_history' |
| Spine context columns | Regime largely SOLVED in stored parquet (~98% quad coverage, basis stored); real gap = PERSONALITY coordinates on graded rows (archetype non-null only on 1,476 context rows) | A2 `_stamp_personality()` at build_index with R-CI3 provenance |
| context_snapshot API | Does not exist (closest: mastermind_context, snapshot-only) | A1 build |
| Cross-sectional detector | Does not exist (closest: confluence co-firing lift) | B1 build (template families) |
| Risk lens | Computable today (worked example in census) | B2 build (nightly artifact + UI) |
| Cortex intake | Works (3 hypotheses staked incl. personality-adjacent H3); inbox unused; research_queue not wired | B3 read tools + candidates flow |
| Indicator lab | Open PR #1840 (46 signals, canonical backtest seam, DARK NW rows) — not ours, not merged | C1 bridge AFTER merge; C2 protocol now |
| Kernel conditioning | Fenced until 2026-10 FDR batch | R-CI8 clock only |

---

## 3. Waves

| Wave | PR | Contents | Depends |
|---|---|---|---|
| W0 | PR-1 | This masterplan + `context_scan` fdr_family registration (ruling_graph meta) + registry_seed clock entries | — |
| W1 | PR-2 | Repairs: fire_coordinates 3 bugs + personality/regime coordinate enrichment (schema v2, additive); qledger stamp wiring fix; A3/R-CI12 heartbeats in NW health | — |
| W2 | PR-3 | `engine/neuralweb/context_api.py` (snapshot + frame, honest coverage) + tests + synapse registration + `_stamp_personality()` in query.build_index | W1 |
| W3 | PR-4 | Risk lens: `scripts/build_context_risk.py` (nightly, CORTEX JOB — engine band's timeout history forbids new post-band builders; all inputs git-tracked and present in the cortex checkout) → `data/neuralweb/context_risk.json` + `site/neuralwebdata/context_risk.json` + world_state sub-block + admin/committee panel hook | W2 |
| W4 | PR-5 | Context scanner: `scripts/build_context_candidates.py` (CORTEX JOB; T1/T2/T3 templates, declared budgets, nulls, dedupe incl. archive, decay) → context_candidates.jsonl + cortex read tool + inbox flow exercised | W2 |
| W5 | PR-6 | Indicator×personality bridge (AFTER #1840 merges): personality_cells characterization + tech_lab.json `by_personality` block + `research/INDICATOR_PERSONALITY_PROTOCOL.md` (protocol doc may ship earlier with PR-1) | lab merge |

Builders: Sonnet (`builder`), fresh worktrees off origin/main, same-day squash-merge.
Reviewers: Opus (`reviewer`) every PR — law conformance (Article 2, anti-mining,
null-calibration, LLM laws), correctness, budget. Fable adjudicates and merges.

## 4. Come-back clocks (all in registry_seed)

| Clock | When | What |
|---|---|---|
| forward-ledger first write | first fire day after 2026-07-08 | verify rows appear; else debug stamper |
| fire_coordinates accrual | 2026-07-15 | file exists on host, coordinates non-null |
| risk-lens stability | 2026-08-01 (20+ board snapshots) | exposure profile day-to-day variance readable |
| scanner first candidates review | 2026-08-05 | human triage of first month's candidates |
| board-cell studies powered | ~2026-09-07 (n≥50 most archetype cells) | charter first pre-registered board-context study |
| kernel-conditioning question | 2026-10-01 FDR batch | personality-conditioned cells as batch entries (R-CI8) |
| indicator×personality map v1 | after #1840 merge + 1 week | first characterization plane published |

## 5. Honesty block

The scanner will mostly print nothing interesting for months — that is the design:
detection machinery running on thin accrual emits few candidates above its nulls,
and the printed candidate counts + nulls ARE the output. The risk lens is honest
display arithmetic on measured fingerprints (survivorship-flagged, small-n cells
suppressed). No output of this program ranks, sizes, or gates anything; the paths
to authority run exclusively through cortex metabolism or human pre-registration,
with rulers derived from the claims the context surfaces. The word "validated"
appears nowhere in program surfaces.
