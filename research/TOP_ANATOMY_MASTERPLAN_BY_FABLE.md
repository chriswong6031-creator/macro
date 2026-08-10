# TOP ANATOMY — Extended-Move Maturation & Top Recognition — Masterplan (by Fable)

**Chartered:** 2026-08-10, from the operator's commissioning study (`mastermind_top_recognition_context_study.md`, ChatGPT brainstorm handed to this session): *"use the entire historical record as a library of lived market experience, systematically reverse-engineer what was observable before historical tops, and convert those recurring precursors into a real-time recognition system."*
**Status:** ACTIVE — Wave 0 (truth engine + phase-0) and Wave 1 (display surface) building this session.
**Docket relationship:** this program is the **extended-move maturation arm of the Short-Side / Breakdown Intelligence lobe** (`research/SHORT_SIDE_MASTERPLAN_BY_FABLE.md`, docket L1). It absorbs species S1⁻ (Cohort Euphoria Distribution), S2⁻ (Donor Exhaustion) and S13⁻ (Within-Sector Leader Fade) at episode scale — those rows graduate here rather than getting parallel preregs. All L1 scope fences and evidence constraints are inherited (§3, §6).
**Family (phase-0):** `top_anatomy_p0` — prereg `research/top_anatomy/TOPA_PHASE0_PREREG.md`, frozen before any result is computed.

---

## §0 ACCEPTANCE GATES (not done unless)

- **G0.1 Freeze before results.** The prereg commit precedes the first harness run in git history. Any construction change after first results is a new, labeled arm — never an in-place edit.
- **G0.2 Survivorship honesty.** The Wide track's inclusion of dead names is *verified, not assumed*: the phase-0 report names ≥3 known 2022–2024 delistings found in the tape with bars through their final trading day. The Deep track's survivorship tilt is disclosed in every artifact and report section that uses it ("who is missing: names that topped and died before basket curation" — per house law `discovered-rule-must-cover-the-motivating-exemplars`).
- **G0.3 Honest N.** Every headline number carries episode-level N (distinct episodes, never fires/ticker-days), a month-block bootstrap CI, and BH-FDR correction within feature family. Nulls printed as counts ("k of 36 separate").
- **G0.4 Lead-time honesty.** Every claimed discriminator carries a lead-time profile. A feature separating only in the {peak..peak+5td} bucket is labeled **POST-TOP CONFIRMATION** and may never be described as detection (study doc §44; the distinction is explicit in the report's tables).
- **G0.5 Coverage gate.** The report LEADS with the discovered discriminators run against the motivating live exemplars and the current regime (2026-08 tape: the extended gold/PGM-miner cohort per `research/CASE_STUDY_GOLD_REAL_RATE_PEAK_2026_08.md`, and the extended AI leaders) — display-tier readout, no authority. A red-team pass by an Opus `reviewer` happens BEFORE results are presented (house adjudication coverage gate, operator 2026-08-10).
- **G0.6 Tier discipline.** Everything ships display-tier: no rank, gate, size, or escalation anywhere; no blended composite score on any ranked surface (constitution Article 2; Intel-Hub audit restatement). Promotion to any authority = a separate future prereg under the L1 ladder (§5 of the short-side masterplan). **No short calls ever** (`DNR:KILL-DIRECTIONAL-SHORTING`); **no exit rules ever** (L1 §7 graveyard: "drawdown control is an ENTRY problem" — our outputs are entry-side avoidance and trim-conviction *context*).
- **G0.7 Surface law.** The Wave-1 surface passes the `HOLD-IGNITION-SURFACES` checklist *by construction*: its display gate is declared in this doc §5 before the surface exists; it has an honest-null state ("nothing maturing — that is a finding"); it never force-ranks a dead tape; falsifier register never appears front-facing; "validated" never appears; EN/ZH parity; design doctrine + frontend-design skill before any markup.
- **G0.8 Ship loop.** Each wave lands commit → push → PR → CI → same-day squash-merge → live verification. No child-agent self-merge of the flagship surface.

## §1 Objective and thesis

The stack has strong bottom/entry perception (bottom radar, turn watch, ignition, reversal cohort) and index-level top perception (froth_fragility, risk radar). It has **nothing that watches a winner mature**. The operator's framing: most investors have systems for "what should I buy?" and almost nothing for **"when has my winner changed character?"**

Thesis (from the commissioning study, house-fitted):

1. Tops are **state transitions**, not chart patterns: healthy trend → extension → excess → weakening incremental demand → distribution → breakdown. The chain differs by episode; the states are recurring.
2. **Extension is a prerequisite for some tops, not proof of a top** (Greenwood-Shleifer-You: run-ups alone don't predict low returns; attributes of the run-up distinguish episodes that crash). Therefore the core scientific object is the **contrast**: extended-that-topped vs extended-that-continued — never "stocks that collapsed vs average stocks."
3. Hindsight is used **aggressively for labels** (episode discovery, peaks, outcomes) and **never for features** (point-in-time only, enforced by test).
4. Detecting danger early and timing an exit are different problems; we only claim the first, and only at the tier the evidence supports.

Primary economic questions (in order of product value): has this extended move entered a statistically abnormal fragility regime; what did historically similar episodes do next (analog memory, honest base rates); what is deteriorating right now, in plain words (maturation legs); and at cohort level, how much of a theme is maturing simultaneously (tomography — Wave 2, reading existing basket organs).

## §2 Ground truth — what the data can actually support

| Track | Store | Universe | Span | Volume | Adjustment | Survivorship |
|---|---|---|---|---|---|---|
| **W (Wide)** — registration track | `data/massive_stock_day/` (R2-canonical, ~20.5k parquets) | ~20,764 US names, everything that traded | 2021-07-06 → present | yes (+transactions) | UNADJUSTED → repair via `scripts/replay_standout_pipeline.split_adjust` (verified 0.00–0.14% vs Yahoo); dividends unadjusted (small stated drift) | honest by construction (whole-market pull; G0.2 verifies) |
| **D (Deep)** — era-stability track | `engine/price_ladder.py` adjusted rungs: `baskets_ohlcv` (~2.8k) ∪ `yahoo` (~1.1k) ∪ `data_stocks` (~240) | ~3k curated names | 1997 → present (per-name varies) | partial (rung-dependent; nulls printed with coverage counts) | split+div adjusted (yfinance) | **TILTED — curated-current universe; names that topped and died are underrepresented; topped-arm severity understated. Disclosed everywhere used.** |

- **W is the only track that can register a claim.** D exists to answer "does the W-era finding hold in 1999/2007/2015/2020?" for features computable there — confirmatory context, never standalone registration (its tilt is unfixable in-repo today; the ~18% dead-price recovery ceiling in `scripts/research/gate0_survivorship.py` is on file).
- **W's 5.1-year window is era-rich for this question**: it contains the 2021 speculative-top cohort (the densest modern blow-off sample), the 2022 bear, the 2023–24 AI run-up, and the 2025–26 regime.
- **CN is deferred** — the full-A TuShare spine is contract-only and authorization-gated (`research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md`); the curated `china_search` panel has append-only-retention caveats. A CN wave charters only when the spine is live.
- Non-price planes are out of phase-0 scope by data reality, not by choice: PIT revisions start 2026-06-16; PIT short interest ~2027+; options OI snapshots are non-backfillable; FINRA daily short volume is PIT-safe but thin. They enter at Wave 2+ as incremental-value tests over the OHLCV baseline (study doc Query 5), exactly the LSR/exit-crowding pattern.
- Heavy compute runs **locally, off the render path** (`python -m scripts.research_top_anatomy_phase0 --data-root <primary-checkout>/data`), caches under `<data-root>/research/top_anatomy_p0/` (gitignored), committed outputs are small vintage-stamped JSON + `reports/top-anatomy-phase0.md`.

## §3 Prior art and collision map (what we extend, what we must not touch)

| Asset | Scope | Relationship |
|---|---|---|
| `engine/froth_fragility.py` | INDEX/macro top-risk quadrant; owns "hidden distribution under a pinned index" (`DNR:KILL-IBD-DISTRIBUTION-DAYS`) | READ (via `latest["froth_fragility"]` — import-locked), never rebuild. TOPA is per-NAME; froth is the macro backdrop chip on our surface. |
| `engine/sector_signals.py` | Sector-ETF EXTENDED→TOPPING→SELL state machine, calibrated 1998–2026 | Benchmark + inherited law: **"topping is gated on 'extended', never on the bare down-cross"** (down-cross from non-extended = bounce trap, +0.29% vs −1.34%). Our state machine keeps this invariant at name scope. |
| `engine/cycles.py` LADDER (`TOP WATCH`/`ROLLING OVER`) | per-name short-cycle (daily-band) oscillator states feeding action_board avoid tags | **Namespace fence.** Different timescale (days, oscillator) vs ours (weeks-months, episode maturation). Our state keys use the `mat_*` prefix and never collide with LADDER vocabulary or keys. |
| `engine/roc_blowoff.py` | per-name blow-off (terminal velocity) risk chip, board display law `ZERO_SCORE_AUTHORITY` | READ + print as a leg where useful; TOPA adds the episode/maturation dimension it lacks (RS decay, effort-result, participation, analog memory). |
| `engine/theme_crowding.py`, `engine/basket_breadth_divergence.py`, `engine/basket_score.rollover_risk` | per-BASKET crowding/exhaustion/rollover | Wave-2 tomography READS these organs; TOPA never re-derives basket physics. |
| `engine/stage_analysis.py` (Stage 3) | per-name Weinstein stage context, display-only | Adjacent coarse vocabulary; our surface may print the stage chip; no logic shared. |
| Winners program W3/W4 (`research/winners/`) | onset-quality fingerprints — closed NULL twice | **Population fence:** W3/W4 condition on t0 = breakaway START; TOPA conditions on mid/late-life EXTENDED days. We reuse the **W4 matched-control estimator** (`research/winners/W4_CONTROLS_STUDY_SPEC.md` §4: matched-set Δ, month-block bootstrap, ticker-cluster robustness, gate-matching) and the harvest/case-library conventions — never the closed verdicts. |
| Short-side L1 (`SHORT_SIDE_MASTERPLAN_BY_FABLE.md`) | breakdown species, AVOID-not-SHORT | Parent docket. S1⁻/S2⁻/S13⁻ absorbed here. Inherited: RUL-P6 (asymmetry is a question), §6 evidence constraints (no PIT SI as evidence; FINRA daily short volume OK with depth stated; GEXR context-only; froth import-lock), §7 graveyard (EMA8 auto-sell dead; exit-rule routing NO-GO; SI-crowding display-only). `DNR:KILL-BD-ECON1` (avoid lens ≠ board fires) and `DNR:KILL-BD4-SPECIES` (sign-reversed, parked) stand. |
| `engine/us_turn_watch.py` | upturn deck, display-tier, recall-optimized, "operator is the second-stage filter" | **Design mirror for the Wave-1 surface** (same philosophy, opposite side): rows are context, not picks; most rows go nowhere by design; nulls printed beside plain-word reasons; own site root. |
| `engine/ignition_audit.py` | forward self-grading ledger pattern | Wave-1 forward log copies its mechanics: append-only JSONL, idempotent by (asof, key), nightly-lane-gated, TP definitions pre-registered inline before any grade matures. |
| `research/EXIT_CROWDING_PHASE0_PREREG.md` | options-tape exhaustion legs | Coordinate at Wave 2+ (their L1–L3 blocked on data); we do not duplicate their legs. |
| Prophet | graded board | **Hard fence:** `DNR:KILL-PROPHET-POP-MERGE` — nothing from TOPA touches the graded-board population; any future linkage is presentation-tier only. |

## §4 Definitions (shapes here; exact frozen numbers live in the prereg)

- **Extended day:** trailing 126d return above a hard floor AND price still near its 252d high (the "still extended, not already broken" invariant from sector_signals). Tradeability floors on price and median dollar volume. Two pre-declared sensitivity variants, report-only.
- **Episode:** contiguous extended days per name, short gaps merged. Episode-level N is the honest N everywhere.
- **Day-level race label:** from extended day d, which comes first within the horizon — drawdown of ≥X% from the post-d running peak (**TOPPED**) or a further ≥Y% gain over close_d (**CONTINUED**); else **CENSORED**. Asymmetric X/Y chosen on economics (giving back a fifth of the position vs missing moderate further upside).
- **Episode peak / terminal top:** the episode's maximum close (within episode + trailing buffer); the episode "topped" if price subsequently loses ≥X% from that peak within the sealing window without an intervening new high. `days_to_peak(d)` anchors all lead-time analysis.
- **The top ruler** (mirror of the PSS §7 bottom-timing ruler — MFE/peak-proximity, not MAE/trough): a warning's quality is measured on (i) **remaining upside** from warning day to episode peak (median, vs all-extended-days null), (ii) **peak proximity** (share of warnings within 5% of peak price), (iii) **time proximity** (share within ±10td of peak), (iv) **forward 63d excess** after warning vs extended-day base. Never fwd-return-only grading (wrong-ruler trap, `DNR:KILL-OUTCOME-AUDITION` lesson).
- **Feature library:** 36 point-in-time OHLCV features in 6 families (geometry, momentum/acceleration, volatility structure, volume/effort, relative strength, maturation/structure) — exact formulas in the prereg. PIT discipline is test-enforced (features at d use only ≤d data; cross-sectional medians use only same-day PIT universe).
- **Archetype tags (descriptive-only in phase-0):** verticality/turnover-based blow-off vs grind tags stored on episodes for stratified reads; a real taxonomy hardens in Wave 2 only if phase-0 shows archetype-dependent structure.

## §5 Waves

**W0 — Truth engine + phase-0 anatomy (this session).**
`engine/top_anatomy.py` (pure, importable: episode extraction, race labels, top ruler, feature library, matched-control assembly) + `tests/test_top_anatomy.py` (synthetic-bar tests incl. a PIT-leak guard and a race-label truth table) + `scripts/research_top_anatomy_phase0.py` (harness: tape build W+D, experiments E1–E4, today's-tape appendix) + committed summary JSON + `reports/top-anatomy-phase0.md`. Experiments: **E1** matched-pair per-feature separation (registration track W; D confirmatory), **E1b** pooled AUC increment over extension-alone baseline (episode-clustered CV + walk-forward on W), **E2** lead-time profiles with the EARLY/MID/LATE/CONFIRMATION taxonomy, **E3** precursor ordering (descriptive), **E4** era × cap-proxy stability. Verdict semantics are DISCOVERY (ORE-law compliant): a null closes constructions, not the search space; zero surviving features ⇒ Wave 1 ships descriptive-only copy and Wave 2 pivots to the cross-sectional plane.

**W1 — "Winner Health" display surface + nightly states (this session, after W0 results).**
Display gate (declared NOW, satisfying G0.7): the surface may ship immediately **because** it makes no predictive claim — every element is either (a) a present-tense descriptive fact (extension percentile, RS-peak lag, effort-result trend, states), (b) an episode-library base rate with honest N and track disclosure ("of N similar historical episodes, k topped within 63td — library, not forecast"), or (c) an explicit null ("nothing maturing today"). Any *predictive* claim (hazard %, calibrated warning) requires the Wave-2 gauntlet and does not exist in W1.
Components: `engine/top_maturation.py` (nightly per-name maturation states `mat_state ∈ {none, trend, extended, watch, thinning, breaking}` — computed deterministically from the W0 feature library; state names avoid LADDER vocabulary), analog-memory retrieval (nearest historical episodes from the W0 tape with outcomes), `scripts/build_top_maturation.py` (daily.yml parallel band + `config/dag.yml` parity), forward log `data/top_maturation_log/` (ignition_audit pattern — accrual starts day one so any future promotion has grades), page `templates/winner_health.html.j2` → own site root, EN/ZH, designer-lane build. Synapse registration `tier: display` + `external_consumers: [mastermind:context]` (auto-manifest lobe tier), `docs/SIGNAL_BUS.md` regenerated.

**W2+ — chartered, NOT this session:** cross-sectional tomography (reading theme_crowding/basket organs; propagation-order study — doc §34), options/short-volume incremental legs (with exit-crowding), hazard-model + promotion prereg (only if W0 finds lead-bearing structure), Prophet presentation-tier linkage, CN wave (spine-gated), rich-tier lobe summarizer + market_packet block, archetype taxonomy hardening, false-top analog UX ("what was different" pairs — doc §7 as a product feature).

## §6 Epistemics & standing-law compliance

- Display-tier ships freely; gauntlet applies at promotion only. Nulls never block building or accrual; a null factor is retained as confluence input.
- "Validated" never appears user-facing without allowlist backing (CI-guarded); falsifier register never front-facing (windows-not-certainties copy); ZH copy in templates AND builders; no translated `title=`.
- LLMs originate nothing here: every state, label, and base rate is deterministic math over bars (constitution Article 1 untouched; the payload carries its own standing-law string per house convention).
- Instrument verdicts are not market verdicts (operator 2026-08-09): a TOPPED race label is a statement about the declared X/Y/horizon race, and all copy scopes it that way ("no −20% event inside the window," never "the move is over").
- Trial budget: 36 features × 1 primary test, 2 sensitivity arms report-only, no grid search, no `deflated_sharpe` (no Sharpe claims in phase-0) — declared in the prereg; `check_trial_registration.py` not triggered.
- Kill-registry check at charter: no DNR row forbids per-name extended-move maturation research; adjacent rows honored as scoped in §3 (`KILL-DIRECTIONAL-SHORTING`, `KILL-IBD-DISTRIBUTION-DAYS`, `KILL-ONSET-FINGERPRINTS`, `KILL-VOLUME-FINGERPRINTS`, `KILL-STAGE-WIN-GATE`, `KILL-BD-ECON1`, `KILL-BD4-SPECIES`, `KILL-PROPHET-POP-MERGE`, `KILL-FORCED-CALLS`, `HOLD-IGNITION-SURFACES`).

## §7 Cost & latency budget

Phase-0 compute: local Mac Studio, off-lane (est. tens of minutes: ~20k-name parquet scan ≈ 50s cached per LSR precedent; feature panel ~20M rows × 36 features vectorized per-ticker). Render budget impact of W1: one builder in the daily parallel band (target <60s: ~2–5k active names × vectorized features over trailing 400d) + one page build; zero collectors; zero LLM. Forward log: one JSONL append per night. R2: none needed in W0 (caches are local-gitignored); episode tape mirrors to R2 only if it must travel.

## §8 Collision & dependency map (live lanes, 2026-08-10)

- #5196 (Prophet US reversal_member cohort, ANTICIPATION §6.9) — different files, no overlap; our surface is the DOWN-side mirror of its turn-watch deck.
- #5162 (tushare cyq_chips distribution plane) — CN data plane, no overlap until the CN wave.
- Sibling sessions on CI heals — we touch no pack-shared files beyond additive new modules + registry lines; rebase before push per house law.

## §9 Evaluation rubric (what would make each wave a success)

- **W0:** tape exists with ≥800 W-track episodes; G0.2–G0.5 satisfied; the E1/E2 tables answer "does anything PIT-observable separate topped from continued before the peak, beyond extension itself?" honestly in either direction. A confident, well-powered null is a success (it re-scopes W1 copy and Wave-2 priorities cheaply — the study doc's own Phase-I logic).
- **W1:** page live, bilingual, doctrine-clean; states computed nightly inside budget; forward log accruing; honest-null day renders correctly; operator can answer "which of my winners changed character?" in one glance with receipts on hover.
- **Program:** TOPA becomes the house's negative-space perception layer — the states/legs feed (as display context) the action board, theme health, and eventually — behind gauntlets — Prophet-adjacent veto families.

## §10 Explicitly rejected forms (standing kills honored; do not re-propose)

Directional shorting in any form (`DNR:KILL-DIRECTIONAL-SHORTING`); exit/auto-sell rules (L1 §7); a single blended "top score" ranking any surface (Article 2; Intel-Hub restatement); exact-peak-tick prediction as an objective (study doc §4 — top zones only); IBD distribution-day counting (`DNR:KILL-IBD-DISTRIBUTION-DAYS`); re-testing onset-quality fingerprints (`DNR:KILL-ONSET-FINGERPRINTS`, `KILL-VOLUME-FINGERPRINTS`); Stage-2/EC as win-rate gates (`DNR:KILL-STAGE-WIN-GATE`); operator-forced un-gauntleted directional calls on any TOPA surface (`DNR:KILL-FORCED-CALLS`); predictive claims sourced from the Deep track alone (survivorship tilt); surfacing ahead of the declared display gate (`HOLD-IGNITION-SURFACES` lesson).

---

*Execution records are appended per wave below this line.*

## §11 Execution record

- 2026-08-10: Chartered. W0 prereg frozen (`research/top_anatomy/TOPA_PHASE0_PREREG.md`) in the same PR, before any harness run.
