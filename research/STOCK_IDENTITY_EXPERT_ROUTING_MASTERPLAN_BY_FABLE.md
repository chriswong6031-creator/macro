# STOCK IDENTITY / EXPERT ROUTING — PR-0 FROZEN RESEARCH CONTRACT

**Program:** Bottom-Up Stock Identity & Expert Routing ("Stock Identity" — the name Live Entry Radar's §18 A1 reserves for this program).
**Commissioned:** operator/Sol handoff 2026-08-13. **Parent program key:** `market-timing-intelligence` (Radar precedent; a dedicated registry row is a PR-1 open item, §16.7).
**Evidence base:** `research/STOCK_IDENTITY_PR0_ARCHAEOLOGY.md` (same PR).
**PR-0 scope:** research architecture + archaeology only. Zero engine/scripts/site changes; zero Prophet/Radar/Terminal behavior change. **Stop condition honored: no build wave launches from this session.**

---

## §0. CHARTER, ACCEPTANCE GATES, NON-GOALS

**The conceptual standard (from the commissioning handoff, binding):** the program succeeds when the system can eventually answer — *"I know this security's behavioral history, I know whether its identity has changed, I know what kind of episode it is in, and I know which of my entry experts have historically been informative in situations like this"* — and fails if it degenerates into *"this is a defensive stock, so use the defensive-stock strategy"* or *"grey dot is our best universal bottom indicator."*

**Program-level acceptance gates (binding on every later PR):**

- **G-1 (No top-down ontology).** No sector/factor/archetype/hand-named category is ever an input to expert selection or a grouping key for pooling. Pre-existing labels may appear only as (a) diagnostic comparisons and (b) candidate *features* competing inside the fingerprint. Categories may **emerge** from measured fingerprints (behavioral neighborhoods); they are labels-on-top, recomputed, never inputs.
- **G-2 (No outcome audition).** Nothing anywhere in this program selects an expert for a name by ranking the name's own historical outcomes over a menu (`DNR:KILL-OUTCOME-AUDITION` — killed two-ruler, so a localization ruler does NOT by itself escape this row; see §2). Per-name adaptation flows only through the three lawful channels of §2.3.
- **G-3 (Independent ruler).** Expert-fit is measured against a path-anchored episode catalog built without reference to any expert's fires (§7). Generic fixed-horizon forward return is never the primary object; it is retained as a secondary column.
- **G-4 (PIT/replay honesty).** Every historically-measured expert event is either read from a stored ledger or reconstructed by an era-pinned, leak-tested replay; families with no legitimate history (§5.3) accrue prospectively only and are never backfilled. Epoch assignments used at date D are those knowable at D.
- **G-5 (Display-tier until gauntleted).** Every artifact ships `authority: {can_rank, can_size, can_gate, can_originate_signal, can_escalate} = false` (DRL convention). Promotion into anything Prophet-consuming is a separate future PR behind its own prereg (§12.4), confronting `DNR:KILL-OUTCOME-AUDITION` and `DNR:KILL-WASHOUT-TURN` by name.
- **G-6 (Honest N + coverage first).** Every conditional cell reports honest-N as the **pair (distinct episodes, distinct calendar clusters)** — never fires/dates; a coverage/estimability census precedes any cell-conditioned design (`DNR:KILL-PER-SIGNAL-FAMILY-RELIABILITY` lesson); ABSTAIN is a first-class output.
- **G-7 (Look budget).** Every sweep registers into `engine/trial_ledger.py` before running; confirmatory questions are pre-registered with one primary metric each; everything else is labeled exploratory.
- **G-8 (Path partition).** This program never touches `engine/entry_signal.py`, `engine/signal_gate.py`, `engine/confluence_tiers.py`, `engine/signal_quality.py`, `engine/prophet_*.py`, `engine/washout_turn.py`, `engine/mtf_upturn.py`, **`engine/stock_personality.py`, `engine/oracle/personality_context.py`, `scripts/build_stock_library.py`** (the reach-the-gate-chain hole named by review finding 19), Radar's `engine/entry_radar/**`, or Terminal repo internals. Every engine PR prints `git diff --stat` on those paths (clean) in the PR body. New code lives only in `engine/stock_identity/**`, `scripts/stock_identity_*.py`, `data/stock_identity/**`, `research/STOCK_IDENTITY_*`, `research/stock_identity/**`.
- **G-9 (Language law).** No user-facing "validated"; no front-facing falsifier/refutation language; LLMs originate nothing (constitution Article 1); plain-word abstention disclosure is the compliant surface form.

**Explicit non-goals (PR-0 and the whole first arc):** no production Prophet scoring/gating changes; no Golden Oracle replacement; no manually named stock taxonomy; no permanent single personality per security; no universal winning signal; no mass per-ticker bespoke indicator optimization; no declaring operator screenshots validated evidence; no waiting-for-years posture — historical episodes are the evidence source; no re-running killed research without naming the hypothesis difference (the archaeology map §1–§3 is that naming).

---

## §1. THESIS AND THE INVERSION

A security's useful trading grammar is a property of the **security's own path process**, not of its sector/factor labels. The program models each security bottom-up:

1. **Identity** — slow structural behavior (trend persistence, drawdown grammar, recovery velocity, mean-reversion strength, vol level/clustering, gap behavior, MA relations, cyclicality, breakout-vs-pullback disposition, event response, factor dependence and residual share, liquidity).
2. **Identity epochs** — a ticker is not one identity forever; behavioral process changes (not market-cap bucket changes) bound epochs: `ticker → epoch_1 → … → current_epoch`.
3. **Current state** — the fast-moving path condition (structural uptrend / controlled pullback / deep washout / range / breakdown / recovery).
4. **Episode** — the specific opportunity window being evaluated (cyclical reset, washout, pullback, reclaim, failed breakdown, earnings dislocation…).

Expert utility is conditional on `ticker × epoch × state × episode`, and the program's order of operations is the inversion the handoff demands:

```
individual → fingerprint → expert-response profile → neighbors/species (emergent)
```

never `sector/archetype → presumed behavior`.

**Motivating exemplars are motivation, not evidence.** The operator's visual reads (KRUS deep-reset ↔ amber EARLY; MCK staircase ↔ STARTER/RE-ENTRY; NVDA violent-reset trend ↔ situational RE-ENTRY/grey; YELP secular-decline RE-ENTRY weakness vs deep-EARLY near the 2026 washout; KO vs WMT/MCD defensive-label divergence; the gold/silver-miner shared personality; BABA's recognizable grammar) are recorded exactly as the Radar contract's §18 A1.2 item 6 records them: a small-N visual read standing **against** a measured n=1,300 null on per-name selection persistence — the thing the program must test, never a result it may assume. They serve as the exemplar-coverage set (§9.8) and pilot core (§13).

---

## §2. LEGAL FOOTING — WHAT IS ALREADY KNOWN, AND THE METHOD LAW

### 2.1 The kill that binds (and its exact scope)

`DNR:KILL-OUTCOME-AUDITION` (PTT-W1a): per-name timing-tool selection by in-sample outcome ranking has **zero OOS persistence** at n=1,300 names / 109,974 signals — **under both** the fwd63 apparatus **and** the corrected bottom-picking/timing ruler (FIT-best in TEST top-2: 33.2% and 35.0% vs 33.3% chance). Per-name "home rungs" are ruler-dependent (5/7 defensives flip). Consequence for this program: *"which expert fits this name"* answered by the name's own outcome ranking is dead however the ruler is phrased. The kill row's recorded carve-out — *"structure-MEASUREMENT tailoring stays OPEN and is UPGRADED under the timing ruler"* — is this program's license. **The row's final clause binds equally and is quoted in full: "and W4 per-class gate profiles are UNLICENSED under both rulers."** The unlicensing is unconditional in the source (PTT `:218` "(per-class gate profiles) is UNLICENSED"; `:344` "W4 stays unlicensed" after the ruler swap). §2.3 addresses this head-on.

### 2.2 The affirmative result this program continues

PTT-W1b (structure tailoring): deriving tool/rung mechanically from bars-only measured structure (swing period, mean-reversion half-life, trend persistence), with events validating (never selecting), cleared the random floor CI-clean on the timing ruler: U_MAE +0.41pp [+0.13, +1.16]; proximity +5.87pp [+3.51, +6.43] vs random (two structure arms cleared — W1b-pure and W1b-hybrid +0.33pp [+0.15, +0.74]). **Source caveats carried in full (they matter to a localization program):** the source discloses that part of the proximity edge is rung **SPEED** — "a 2W bar stamps up to 10td after the turn," so a faster-cadence instrument mechanically stamps closer to the trough — and **FAMILY**-specific (M-family at the same derived rungs loses the edge); the deliverable construction was specifically S-family at the structure-derived rung. Under fwd63 every W1b CI included 0 and the source concluded "the engine seat is NOT yet earned." A proximity ruler rewards exactly this cadence artifact, so §7.3 makes grain a measured stratum and §8.3 adds a grain-null. And the class-altitude finding — vol×trend terciles and fundamentals archetype do NOT separate — leaves grouping **discovery** (never tested; repo-wide absence verified) as the open front.

### 2.3 The Method Law — three lawful evidence channels

All per-name expert conditioning flows through these channels, in this order of precedence; anything else is G-2 territory:

- **Channel A — structure-derived compatibility (global map).** A single cross-sectional mapping, estimated over ALL names at once, from fingerprint features to expert-fit metrics: `fit(expert, episode-type | fingerprint)`. A name receives its expert profile by *evaluating the global map at its own fingerprint*. This is PTT-W1b generalized: the name never chooses its expert; its measured structure does, through a map whose form is fixed cross-sectionally. **"Low per-name degrees of freedom" is an obligation, not an assertion (review finding 2)** — with ~70 fingerprint columns the fingerprint is nearly a unique key per name, and an unbounded map is the audition through a hash function. Three binding controls make the claim real: (i) **capacity budget** — the map's effective parameter count is declared before fitting and must satisfy `p_eff ≤ N_names/10`; the functional form is fixed at PR-3 (additive/monotone in a declared feature subset unless a richer form is separately pre-registered); (ii) **name-disjoint OOS** — Q1 is evaluated on held-out NAMES (name-blocked K-fold / leave-names-out primary; era/episode splits secondary); (iii) **name-permutation null** (§8.3 null #5) — fingerprints permuted across names within (cap × vol) strata and the map refit; retained predictive rank correlation under permutation means the map is memorizing time structure, and Q1 fails.
  **W4 confrontation (review finding 22):** Channel A is a per-class gate profile in PTT-W4's sense, and the kill row leaves W4 UNLICENSED under both rulers. This contract does not claim W4 is licensed. It claims: (i) W4 was unlicensed because no *pre-defined* grouping variable separated; (ii) discovered grouping is untested (archaeology §2.3); (iii) Channel A therefore requires its own affirmative demonstration — Q1, under the three controls above — before any per-class profile is used for anything. If Q1 fails, W4 stays closed and this program does not re-open it (§14.1 consequence matrix).
- **Channel B — behavioral-neighbor pooling.** Fit estimates for a name borrow strength from its k nearest neighbors in fingerprint space (§10). The neighborhood is computed from fingerprints (never sector labels); the borrowing weight is precision-based and printed.
- **Channel C — per-name residual shrinkage.** After A and B, a name's own episode history may shift its profile only as an empirical-Bayes posterior with printed component n (`w = n/(n+k)`, SEA precedent), never as an argmax. With small honest-N the posterior collapses to the A/B prior — by construction, a name cannot "select" its expert out of its own noise.

**Ticker-specific experts** (the BABA clause) sit above all three channels: permitted only after the fit engine shows a stable, plateau-robust, epoch-stable residual pattern that channels A–C cannot express, and only via a fresh pre-registered construction with its own gate (`DNR:KILL-SLOT-PRERESERVATION`: this contract reserves no slot for them).

### 2.4 Understanding before backtest

Operator precedent on this exact program family (memory `understanding-before-backtest`): descriptive understanding precedes fit grading. The PR sequence (§14) therefore ships the **identity atlas** (fingerprints, episode catalogs, per-name dossiers the operator can eyeball against their own visual reads) before any expert-fit table exists.

---

## §3. OBJECTS AND VOCABULARY (frozen)

| Term | Definition | Collision note (see archaeology §7) |
|---|---|---|
| **Fingerprint** | The continuous per-(ticker, epoch) vector of path-behavior measurements (§4) | replaces "personality" (three prior senses; avoided) |
| **Identity epoch** | A maximal interval over which a ticker's fingerprint is statistically stationary per the §6 detector | new term, no collisions |
| **State** | Coarse mechanical path condition at a date (§7.1) | distinct from Radar detector lifecycle states |
| **Identity episode** | A path-anchored opportunity window from the §7 catalog (decline/reset/reclaim structures), labeled with its eventual resolution | qualified always; distinct from options episodes, Red-Queen `engine/oracle/episodes.py`, and Radar's detector-anchored `live_entry_episode` |
| **Expert** | A recorded entry-event family with preserved provenance (Radar A1.2 sense): producer, family, subtype, stage, era, authority | adopted verbatim from `mastermind.entry_event.v1` |
| **Expert-response profile** | The vector of §8 fit metrics for the canonical cell key **(ticker, epoch, episode_type, episode_tier, expert)** — the single key every statistical claim uses (review finding 24); §8.5 states which margins each question aggregates over | — |
| **Behavioral neighborhood** | k-NN of a name in fingerprint space; emergent, recomputed, display-only | replaces "species" (taken by Setup-Species = signal taxonomy) |
| **Stock Identity File (SIF)** | The per-ticker artifact aggregating all of the above (§12.2) | — |

---

## §4. IDENTITY REPRESENTATION — THE FINGERPRINT (deliverable 3)

**Form:** a flat vector of interpretable, unit-free path statistics per (ticker, epoch-to-date), each computed at ≥2 window lengths, cross-sectionally ranked (PIT percentile vs the contemporaneous universe), nullable with a coverage mask. **Not** a classifier output; no discrete labels inside the representation.

**Feature families (v0 candidates — final enumeration frozen at PR-1 registration, reusing shipped measurement organs before inventing):**

| Family | Candidate features | Existing substrate to reuse |
|---|---|---|
| F1 Trend grammar | Kaufman efficiency ratio (63/126/252d); R² of log-price on time; %sessions above 50/200DMA; new-high cadence ("staircase-ness") | **`engine/path_personality.py`** (`_trend_persist_*`, `_slope_stability_126` — causal/PIT-safe by construction, 2.1M ticker-day backfill store); PTT trend-persistence; `engine/canon.py` MAs |
| F2 Drawdown grammar | drawdown depth distribution (median/P90 peak-to-trough); resets/year ≥15%/≥30%; time-under-water distribution; drawdown *quality* (Ulcer family) | Bottom-Confidence primitives; SEA depth classes; `engine/path_risk_signals.py` (Ulcer/NATR/HVR); `path_personality._pullback_stats` |
| F3 Recovery velocity | post-trough 63d return in ATR units; time-to-50%-retrace (V-vs-U); rebound slope | episode catalog (§7) once built |
| F4 Mean reversion | AR(1) of daily/weekly returns; variance ratio k∈{5,20}; MR half-life; oscillator-extreme dwell times | PTT MR half-life; PSS codex descriptors (retained-as-features per their kill rows) |
| F5 Volatility | realized vol level + vol-of-vol; ACF(|r|) clustering; ATR% regime spread | PSS codex |
| F6 Gap/event response | overnight-gap share of variance; earnings-day |move|/ATR; post-earnings drift persistence; gap-fill rate | `path_personality._gap_share_series`/`_event_gap_contrib`; **caveat: no deep historical earnings-date archive exists** (current store = forward calendar + ~4 trailing quarters) — earnings-anchored features need an off-path backfill (PR-1 decides build-or-defer); gap-anchored proxies ship first. `KILL-VOLUME-FINGERPRINTS`: volume descriptors are display-tier features only |
| F7 MA relations | mean distance to 20/50/200DMA in ATR; crossing frequency; dwell above/below; bounce rate after 50DMA tags in uptrend | canon MAs |
| F8 Cyclicality | detrended ACF/spectral peak in 6–36mo band; peak sharpness (regularity); swing amplitude; PTT swing period | PTT swing-period measurement |
| F9 Factor/idio | rolling β and residual R² (idio share) against a **fixed, pre-declared factor panel identical for every name** (declared at PR-1; commodity factors included only if declared for the whole universe — a name-specific factor choice is a hand label deciding features, review finding 7) | `engine/residual_alpha.py` sector-neutral machinery |
| F10 Liquidity/size | ADV, dollar-vol rank, turnover; cap bucket; spread estimate | `path_personality._dollar_adv_series`; `engine/entry_primitives.py` (Amihud, Corwin-Schultz); stock library fields |

**Laws:** (i) every feature PIT-computable from the daily store (no minute data required for the fingerprint); (ii) plateau requirement — a feature unstable across nearby windows for a name is flagged `unstable`, not averaged silently; (iii) features that are killed constructions (onset/volume fingerprints as *predictors*) enter only as descriptive coordinates, never as promoted predictive features without their own prereg; (iv) **block partition (review finding 6)** — the fingerprint splits into a **metric block** (continuous, label-free; the only block the §10 neighborhood distance and the Channel-A map may read) and a **diagnostic block** (sector, industry, cap bucket, archetype, plane identity; usable for Q2 baselines and reporting, never in the distance or the map); `fingerprint_spec_hash` records the partition, and moving a feature from diagnostic to metric requires a fresh registration; (v) the fingerprint is versioned (`fingerprint_spec_hash`) and every downstream fit table pins the version — **and any change to the enumeration, window set, or block partition after a registered question has been graded voids that question's prereg for all downstream questions** (re-grading requires a fresh registration and look-budget entry, review finding 11); (vi) **plane-availability law (review finding 8)** — a feature family structurally unavailable on a name's price plane (e.g. F6 gap features need `open`, which `data/stocks` lacks while `data/baskets/ohlcv` has it) is **excluded from the metric block entirely** unless available for ≥95% of the evaluated universe; `price_plane_id` is recorded on every fingerprint and the §8.2 census cross-tabulates feature availability by plane, so neighborhoods can never partition by data plane before they partition by behavior.

---

## §5. EXPERT LIBRARY v0 (deliverable 2)

The canonical census lives in archaeology §4 (producers, formulas, authority, replayability — both repos). The frozen v0 library for fit measurement, by replayability class:

**Class R (historically fit-measurable now):**
1. `grey_dot` — raw anticipation dot (Macro `signal_frame.early`; recomputable, era-pinned). **Era-carve-out honesty (review finding 13b):** because `amber_early` was carved out of this family on 2026-08-11, historical grey-dot fit is reported **both** as-recorded and as-restated (fires today's promotion rule would reclassify, removed), and the pair is presented together.
2. `confirmed_buy` / `rebuy` — classic confluence BUY/REBUY (ledgered in `data/signal_archive/track_record.parquet` + recomputable).
3. `reclaim_waiver` ("block repair") — re-derivable with committed nightly state.
4. `weekly_washout_turn` — organ ledger + recompute.
5. `bottom_watch_terminal` — Terminal washout-context events (artifact + locked-spec fallback per the Radar contract §3.2; C5 formula at its §3.4).
6. `sea_event_classes` — SEA's stored event store (389,799 events) as context experts.
7. Naive reference experts (§8.3 comparators): `rsi30_cross`, `low20d_bounce`, `stoch2w_cross` (the PSS incumbent gauge).

**Class B (locked-spec backcast — review finding 13):** a family whose only available specification postdates the measured history. Permitted for measurement, stamped `spec_postdates_history: true` on every row, and **never cited as evidence that the family as it then existed localized anything**.
- `tier_cascade` T1–T4 (recompute via `tier_stream()` under `ANCHOR_ERA="abs-session-2026-08-06"`; T2–T4 have no persisted history).
- `grey_dot_terminal` — the Terminal twin has no store (per-request computation) and G-8 forbids running Terminal internals; it is measured only via a Macro-side locked-spec port with a declared parity fixture (the Radar §3.2 fallback pattern), Class B by construction.

**Class P (prospective-only; accrue, never backfill):** `amber_early` (family born 2026-08-11), `door_r_rearm` (charter forbids backfill), `turn_watch_deck` fires, GC-v2 keeper/recipe scores, Radar `C1/C2` LIVE-state detectors (minute-reconstruction rule inherited), lobe-conditioned anything.

**Class C (conditional) — STARTER, preserved unmerged (review finding 12):** three distinct families, never collapsed — `starter_pending`, `starter_failed`, `starter_converted` (the zone lifecycle: unfilled washout-class zones **convert**; a failed STARTER is a labeled false start, the single most informative event for a localization ruler). Signatures are replayable; the basket/leader licensing context needs PIT basket-state reconstruction (open item PR-2). If PR-2 cannot separate a non-collapsible pair, **both members reclassify to Class P** rather than merging.

**Laws:** family keys are minted from emitter receipts at instrumentation time (Radar A1.3 discipline), never invented; every family carries `family_first_available`/`family_era` and structural absence is never read as negative evidence; the Radar contract's three non-collapsible pairs (`raw grey` vs `washout-promoted EARLY`; `STARTER pending` vs `STARTER failed`; `RE-ENTRY trend-reclaim` vs `RE-ENTRY block-repair`) are enumerated here by name and survive every transformation in this program; the Macro/Terminal grey-dot twins are measured as **two era-pinned experts** until a parity check collapses them (archaeology §4.5.2); `mastermind.entry_event.v1` becomes the ingestion path for prospective events once Radar PR-2 lands (§12.1) — this program never re-derives what that store records, and never writes into it.

---

## §6. IDENTITY EPOCHS (deliverable 4)

**Definition:** an epoch boundary is a persistent shift in the fingerprint process — not a market-cap threshold, not a hindsight chart annotation.

**Detector v0 (frozen intent; constants at PR-5 registration):**
1. Compute the fingerprint on rolling trailing windows (252d, stepped ~21d).
2. Candidate boundary at t when the standardized distance (Mahalanobis on a pinned feature subset with shrunk covariance) between the trailing-252d and preceding-252d fingerprint exceeds a threshold **and stays exceeded for ≥K consecutive steps** (persistence, so a single washout episode — which is an *episode*, not a new identity — cannot fragment epochs).
3. Confirmation lag is explicit: a boundary at t is *knowable* only at `t + K·21d`; all PIT uses honor the lag (G-4). Minimum epoch length ≈ 12 months.
4. Corroborating covariates (market-cap decade change, index add/drop, listing venue change, float events) are recorded as boundary *evidence annotations* — never sufficient nor necessary.
5. Output per ticker: epoch list (start, knowable-from, confidence, dominant shifted features) + a continuous **identity-drift indicator** (current-window distance from current-epoch centroid) that consumers read as "read being updated" long before a boundary confirms.
6. **PIT-vs-final duality (review finding 10):** every epoch-conditioned fit estimate is computed **twice** — on `epoch_pit` (the assignment knowable at each episode's start via `knowable_from`) and on `epoch_final` (retro-detected). `epoch_pit` is the primary; `epoch_final` is diagnostic only; divergence between them is a first-class reported result; **no claim in Q1–Q4 is ever graded on `epoch_final`.** Epochs are a conditioning variable detected from the same price process that generates episodes — hindsight here is more damaging than in a target label, hence the duality is mandatory, not optional.

**Detector validation (before any epoch-conditioned fit claims):** (a) null calibration on stationary block-bootstrap simulations → false-boundary rate under control; (b) power on synthetic injected shifts; (c) face validity on known structural cases (NVDA pre/post datacenter era; BABA pre/post 2021; KRUS IPO maturation; META 2022) — reported as illustrations, not gates; (d) stability: detector output insensitive to ±20% threshold perturbation (plateau, not needle).

**Era interaction:** macro-era splits (`DNR:LAW-ERA-SPLIT`, 2010 break) remain analysis strata regardless of per-name epochs; an epoch spanning an era boundary is reported split.

---

## §7. STATE, EPISODE CATALOG, AND THE INDEPENDENT EPISODE RULER (deliverable 5)

### 7.1 State (small, mechanical, frozen at PR-1)

Eight mutually-exclusive path states from daily bars only: `structural_uptrend`, `controlled_pullback`, `range`, `breakdown`, `deep_washout`, `recovery_reclaim`, `post_event_dislocation`, `vol_transition`. Definitions are simple threshold rules on **three bars-only variables** (distance to 200DMA, drawdown from 252d high, realized-vol percentile) plus a **bars-only event proxy** — an unexplained gap exceeding g·ATR — never an earnings calendar (review finding 9: no deep historical earnings-date archive exists, so a calendar-keyed state would be unbuildable over §9.1's history). `post_event_dislocation` is defined by the gap proxy; its divergence from true earnings dates is measured on the forward-calendar window only, and reported. State is a **covariate** on episodes, not a fit-cell key in v0 (estimability first, G-6).

### 7.2 The episode catalog (expert-independent, path-anchored)

Built once per ticker from the daily store by a frozen mechanical segmentation — **no expert fires anywhere in its construction** (G-3):

- **Reset/decline episodes:** every leg where price falls ≥ X·ATR (and ≥ Y%) from a rolling 126d high, from leg start until either (a) a **durable low** — no lower low for ≥ N sessions AND rebound ≥ k·ATR (and ≥ z%) — or (b) truncation (delisting/data end; censored, never dropped — LER convention).
- **Reclaim episodes:** first sustained recapture of a pinned reference (e.g. 200DMA or prior range low) after a breakdown, with resolution labels (held / failed within M sessions).
- **Failed-breakdown episodes:** close below a 60d low that recovers the level within m sessions.
- Constants (X, Y, N, k, z, M, m) are frozen at PR-1 registration with a declared, look-counted sensitivity grid (diagnostic-only), mirroring LER §10's pattern.

**Labeling honesty:** episode **resolution labels use future data by design** — the catalog is a research-time labeling instrument, not a live signal; nothing downstream ships a label before its window matures. Expert events joined to episodes remain strictly PIT. Depth is context, never a bonus (`no zero-print requirement`, no deepest-drawdown ranking — inherited from Radar's do-not-build list).

**Meaningfulness tiers:** episodes are tiered by economic significance (e.g. ≥20%/≥35% depth, duration floors) so that recall metrics quote their tier explicitly.

### 7.3 The ruler (per expert fire × episode; primary object = localization, not return)

**Per-type anchors (review finding 25):** the ruler's anchor is defined per episode type — reset/decline → the durable low `L(T_L)`; reclaim → the recapture confirmation bar; failed-breakdown → the breakdown low. Metrics are never pooled across types without the type reported. **Censored/unresolved episodes** (truncated, or YELP-class declines that never print a durable low) have no anchor: they contribute to `flooding` and to the unconditional block below, and to nothing else — and the share of episodes so excluded is printed beside every recall figure (otherwise `recall@tier` is a survivorship filter inside the ruler itself).

For each anchored episode E and each expert fire F(t_F, known_ts) attributable to E (attribution window frozen at PR-1):

| Metric | Definition |
|---|---|
| `lead_lag` | `known_ts(F) − T_L` in sessions (negative = anticipates the low) |
| `price_dist` | `(P_F − P_L)/P_L`, and ATR-normalized (`A0` = Wilder ATR(14) at prior confirmed close — LER convention, `atr_basis` recorded) |
| `mae_after` | max adverse excursion after F before episode resolution, ATR units (MAE ≤ 0 sign convention) |
| `capture` | rebound magnitude from P_F to the episode's first major retrace peak before a subsequent lower low |
| `false_start` | F followed by a lower low beyond θ·A0 within the episode (θ frozen at PR-1; LER §10's false-start form reused where the expert is fire-shaped) |
| `flooding` | fires per episode; spacing distribution; duplicate suppression honesty (promotion/dedup edges preserved) |
| `recall@tier` | share of tier-T episodes with ≥1 fire inside the useful zone (within w sessions AND δ·A0 of the low; w, δ frozen at PR-1) |
| `zone_precision` | share of the expert's fires landing in useful zones |
| `relative_order` | lead/lag vs sibling experts on the same episode (who fires first, at what cost) |
| `consistency` | dispersion of the above across distinct episodes, across cycles, and across epochs |

**Unconditional block (review finding 3 — mandatory beside every conditional metric):** every metric above is conditioned on episode attribution, so on its own it contains no false-positive rate — an expert firing 500 times a year with 5 fires inside episodes would score perfect localization while being worthless live (the `KILL-VOLUME-FINGERPRINTS` selection-gate artifact, applied to our own ruler). Therefore, per (name, expert): `fires_per_name_year` (all fires, any context); `episode_attribution_rate` (share of ALL the expert's fires on this name attributable to any tier-T episode); and a matched-control comparison in the NC-2 shape (non-episode dates matched on the expert's own trigger conditions; episode rate at those fires reported). **No fit claim is ever presented without `episode_attribution_rate` alongside it; episode-conditioned statistics are labeled conditional in every table.**

**Grain stratification (review finding 21):** every ruler metric is reported grain-stratified; experts of different bar-grains (1D dot vs 3D tiers vs weekly organ) are never rank-compared on `lead_lag`/`price_dist` without a grain-matched control — a 2W bar stamps up to 10td after the turn, and a proximity ruler rewards cadence mechanically (the PTT-W1b SPEED disclosure, §2.2).

**The localization composite (review finding 1 — frozen forms, no third allowed):** exactly two pre-registered candidate composites are graded and reported, both published as executable code with `spec_hash` before PR-3 produces any ruler number; their combining constants are set on the §9 constant-setting partition (blind), and a composite outside this pair may be reported only as exploratory:
- `C-LOC-R` (recognition-weighted): `recall@tier × zone_precision − λ_fs · false_start_rate`, per (name, expert, type, tier), λ_fs set blind.
- `C-LOC-D` (distance-weighted): rank-normalized median ATR-distance-to-anchor of in-zone fires (sign: closer = better), gated by a recall floor and penalized by `false_start_rate` at the same λ_fs.
Both composites inherit the unconditional block: a composite is only quotable with `episode_attribution_rate` printed beside it.

Secondary columns: forward return at H∈{5,10,21}, MFE/MAE (strictly-forward window, LER sign conventions), benchmark/sector excess. These are reported, never the primary fit criterion (G-3), and reversion-shaped experts are read on reversion-capture horizons per `DNR:LAW-REVERSION-RULER`.

**House precedent:** the incumbent 2W StochRSI gauge's −2td trough-timing figure and PTT §7's U_MAE/proximity/td_to_trough metrics are this ruler's direct ancestors; the ruler generalizes them to a catalog of path-defined episodes with recall/flooding added.

**Tops are out of scope.** The archaeology found no shared bottom/top substrate cheap enough to justify widening PR-0; a sibling program owns tops (§16.6).

---

## §8. EXPERT-FIT MEASUREMENT (deliverable 6)

### 8.1 The fit profile

For each canonical cell (§3 key): the ruler-metric vector, honest-N pair, and CIs from a **calendar-block bootstrap with block length ≥ the 90th-percentile episode duration** — resampling blocks of calendar time and carrying every episode overlapping a block; episodes attribute to blocks by anchor date, with sensitivity to start-date attribution reported; a two-way (name × calendar-block) cluster-robust variance is reported alongside. (Review finding 14: month clusters are not a valid partition — a reset episode routinely spans 6–24 months, so month-keyed resampling treats overlapping episodes as independent, anti-conservative in exactly the direction `DNR:LAW-TIME-CLUSTERED-CI` — "effective N = months" — was written to prevent. Post-2010, tier-1 depth episodes concentrate in a single-digit number of market clusters (2011, 2015-16, 2018Q4, 2020-03, 2022) — that is the honest headline N for market-wide episodes and it is stated wherever cohort claims are made.) Per-name-first aggregation everywhere (PSS E1 errata precedent); never ticker-only clustering.

### 8.2 Estimability census precedes design (G-6)

Before any fit table: a coverage census — episodes per (ticker × type × tier), fires per (expert × ticker), joint cell occupancy, **distinct calendar-blocks per cell, the share of each cell's episodes in its largest 3 calendar clusters, `fires_per_name_year` and `episode_attribution_rate` per (name, expert), and feature availability cross-tabulated by price plane** — published as its own artifact. Cells below pre-registered floors — including a floor on distinct calendar clusters, regardless of raw episode count — are marked `UNESTIMABLE` and never reported as nulls (`DNR:KILL-PER-SIGNAL-FAMILY-RELIABILITY`: most axes there died of coverage, not signal).

### 8.3 Null models and comparators (all mandatory in the primary read)

1. **Random-fire placement:** the expert's fire count redistributed uniformly (and dwell-matched) inside the episode → does the expert localize better than chance *given how often it fires*? (PTT per-metric random-day null, generalized.)
2. **Naive comparators:** `rsi30_cross`, `low20d_bounce`, `stoch2w_cross` run through the identical ruler — an expert that cannot beat a trivial oscillator for a name earns no fit claim there.
3. **Global base rate:** the expert's cross-name fit distribution — a name's fit is only *distinctive* if it separates from the expert's base rate (this is what makes "KRUS is an EARLY name" a claim about KRUS rather than about EARLY).
4. **Proximity honesty:** washout-shaped experts sit near lows by construction; **every** fit comparison between low-adjacent experts is made at equal proximity (NC-2 spirit), not against far-from-low fires.
5. **Name-permutation null (review finding 2):** fingerprints permuted across names within (cap × vol) strata, the Channel-A map refit; retained predictive rank correlation means memorized time structure — Q1 fails. This is what makes G-2 enforceable rather than merely asserted.
6. **Grain-null (review finding 21):** for each expert, fires placed at its own bar cadence's mechanical stamp lag — separating "this expert recognizes the turn" from "this expert's clock ticks faster."

### 8.4 Robustness (plateau, not needle)

Where an expert is parameterized, fit must persist under ±20% perturbation of its thresholds and of the ruler's zone constants (declared grid, look-counted, diagnostic-only). Experts are otherwise run at **shipped parameters only** — no per-name tuning anywhere in PRs 1–6 (per-name calibration is a later, separately-gated stage, §14).

### 8.5 What a "fit" claim means (and the lawful channels)

A cell's fit estimate feeds Channel A's global map (fingerprint → fit), Channel B's neighborhoods, and Channel C's shrunk residual — §2.3. The program's **first registered confirmatory question** (the fit read) is the persistence question the audition failed:

> **Q1 (rewritten per review finding 15).** Does the Channel-A global map — under the §2.3 capacity budget — predict localization fit on **held-out names**? *Primary metric: **within-expert, across-name** Spearman rank correlation between predicted and realized localization composite (both frozen §7.3 composites graded), on name-blocked K-fold held-out names, averaged over experts with per-expert n printed. Success = an **intersection–union test**: the maximum of the two one-sided p-values — vs the sector-label map, and vs the name-shuffled Channel-A map (§8.3 null 5) — is below α=0.05, no BH adjustment applied to the conjunction, **evaluated separately on the blind arm** (review finding 18: a result that holds on pilot+blind jointly but not on the blind arm alone is labeled exemplar-scoped and licenses no pooling work). The global constant base rate is reported as a reference point, not a passable baseline. Q1's margins: epoch collapsed to `epoch_pit` current-era cells; types/tiers aggregated per-name-first with weights fixed in the prereg.*

**Confirmatory family (enumerated, fixed):** Q1 (one IUT, as above); Q2 — do fingerprint-space neighborhoods transfer fit to held-out names better than sector groupings (one contrast); Q3 — does Channel C add OOS value over A+B at printed n (one contrast). BH q=0.10 applies over the {Q2, Q3} pair only. **Q4 is descriptive, never graded:** the exemplar-coverage case-by-case read (KRUS/MCK/NVDA/REGN/YELP/KO/WMT/MCD/BABA/miners vs the operator's visual reads, reported both ways). Everything else is exploratory and labeled so.

**Power gate (review finding 16):** before the fit read, a power simulation is published — under a planted Channel-A signal of declared effect size and the *observed* per-cell episode counts from §8.2, the fraction of runs Q1 would detect. If power at the pre-declared MDE is below 0.5, **Q1 is not run**; the read is deferred until coverage supports it, and the deferral is the reported result (an underpowered confirmatory question ABSTAINS, §11 — it does not return an uninterpretable null).

---

## §9. HISTORICAL VALIDATION DESIGN (deliverable 7)

1. **Maximal legitimate history.** All replayable history is in scope (Class R experts; ≥2005 where the store reaches, era-split at the 2010 break). "Avoid overfitting" is implemented as search discipline, never as discarding history.
2. **Splits.** Primary OOS = **held-out names** (name-blocked K-fold; review finding 2). Era discipline per DT-R16 stays as the secondary stratum: declared FIT/TEST split; full-sample-only effects disqualified; leave-one-episode-out / leave-one-cycle-out within eras. **Untouched holdout:** the later of (a) the most recent 6 months of replayable history or (b) the most recent window containing ≥N tier-1 episodes across ≥M distinct calendar months (N, M declared at PR-1 — review finding 4: six calendar months of ~35 names can hold a handful of episodes in one or two clusters), plus everything after the live-forward start.
3. **Mining controls.** TrialLedger registration before any sweep (G-7); pre-registered primary metrics (§8.5); the enumerated confirmatory family (§8.5 — IUT for Q1's conjunction, BH q=0.10 over {Q2, Q3} only); declared sensitivity grids counted in the look budget; no post-hoc metric additions **and no post-hoc fingerprint/representation revisions** without an amendment that voids affected preregs (§4 law v); `spec_hash` on catalog constants, fingerprint version, and ruler constants, verified before outcomes attach (LER's prereg-commit-hash mechanism reused). **Constant-setting partition (review finding 4 — the blind initialization):** all free constants (catalog X/Y/N/k/z/M/m, ruler w/δ/θ/λ_fs, state thresholds, detector thresholds, ABSTAIN floors) are set on a partition drawn at PR-1 **before any constant is chosen** — a randomly drawn 30% of names **excluding every §13 exemplar and the entire blind arm**, plus all history before the FIT/TEST boundary — named and hashed at PR-1. Constants never change after the partition seals; a revision voids the prereg and requires a new registered question.
4. **Leakage.** Known-ts discipline on every joined event (Radar §5 availability states where its store is the source); shift-audit + truncation-invariance fixtures on every replay primitive (RUL-31 instruments, existing test shapes reused); the F6-style feed-truncation test on any recomputed expert.
5. **Survivorship.** Concrete substrate honesty (archaeology §6): dead-name price coverage is 415/1,083 (38.3%), post-2021-07 only, stamped UPPER BOUND; 199 further delisted names exist close-only to 1962; PIT S&P1500 membership with real join/leave dates exists (`data/breadth/sp1500_pit_membership.parquet`) and stratifies every cohort read. Every replay artifact carries the R1 **vintage-stamp schema** (`price_plane_id, adjustment_mode, universe_as_of, survivorship_biased, coverage_frac, dead_name_coverage_pct, era_law_cohort`). Names that stop trading are censored with `terminated_reason`, never dropped; cohort-level claims name who is missing (AGENTS §Adjudication coverage gate clause 3); index-exit ≠ death (172/1,083 "dead" names still trade). Secular decliners (YELP-class) are deliberately in the pilot so the catalog contains episodes that *never* resolve into durable lows.
6. **Ticker-identity hygiene.** Reused tickers splice a *different company's* history "born clean" (ECHO/SATS class; TRAP_FAMILIES "Ticker identity"). Every per-ticker history join cross-checks `config.yml quality.reused_ticker_acks`/`ticker_key_migrations`/`breadth.ticker_fixups` and `config/delisted_symbols.yml`, and the catalog builder sanity-checks each name's first-print date against the IPO calendar before fingerprinting.
7. **Price-plane law.** Fingerprints and catalogs compute only on TR-adjusted deep planes (`data/stocks`, `data/baskets/ohlcv`); the raw, split-uncorrected `massive_stock_day` plane is prohibited for any MA/drawdown/gap math until its downstream adjustment transform is traced (archaeology §6.1).
8. **Exemplar-coverage gate.** Before any presentation: run the conclusion against the motivating exemplars AND the current regime and lead with that answer (`DEC:CONCLUSIONS-NEED-A-COVERAGE-PASS`); report episode honest-N and whether today's tape is in-sample of the winning cell; red-team via an opus reviewer before operator presentation.

---

## §10. POOLING HIERARCHY (deliverable 8)

Precision-weighted ladder, each rung earning its keep with a registered incremental-value read before it is used:

```
global expert base rate
  → Channel A: structure-conditioned global map (fingerprint → fit)
    → Channel B: behavioral-neighborhood pool (k-NN in fingerprint space)
      → Channel C: per-name EB residual (w = n/(n+k), printed n)
        → [gated, future] ticker-specific experts (fresh prereg each)
```

- Neighborhoods are computed over the **metric block only** (§4 law iv); **sector/industry is never the grouping key** (G-1) but sector-label grouping is always run as the *comparison baseline* (Q2) — if GICS beats discovered neighborhoods, that is reported, not hidden.
- The miner test: if the gold/silver-miner cluster is real, it should **emerge** (miners mutually nearest in metric-block space) and the neighborhood's within-group fit transfer should beat the sector-label grouping's. Reported either way. **Tautology guard (review finding 7):** the emergence test is valid only if no metric-block feature is commodity- or sector-specific; if a commodity factor sits in the metric block (universally declared, §4 F9), the emergence result is reported as tautological.
- **Calendar-disjoint pooling (review finding 17):** a neighbor's episode contributes to a target's pooled estimate only if calendar-disjoint from the target episode being predicted (no overlap of [leg start, resolution]) — otherwise March-2020 "borrowing" is re-counting the target's own market event through a different ticker, the same double-count §8.1 forbids in the variance. The share of neighbor evidence discarded by this rule is printed beside the blend weights; a name is never its own neighbor; no single neighbor carries more than a declared maximum share of pooled weight.
- Every pooled estimate prints its blend weights and component n's (SEA receipt discipline).

---

## §11. ABSTENTION CONTRACT (deliverable 9)

`ABSTAIN — no reliable timing edge` is a first-class, product-visible answer at every level (cell, episode-type, whole name):

- **Triggers (pre-registered at the fit read):** honest-N (episodes or calendar clusters) below floor; no expert separates from the §8.3 nulls; fit unstable across epochs (drift indicator high); coverage mask too sparse; Channel A/B priors uninformative and Channel C n too small; **an underpowered registered question (power < 0.5 at the declared MDE) abstains rather than returning a null** (review finding 16).
- **Consumers must treat ABSTAIN as "no adjustment"** — never as a negative signal, never as a veto (the null-is-not-a-veto house law).
- The KO hypothesis ("oscillator bottom timing reliability: low") is exactly an abstention-shaped claim, and the contract makes it *testable*: KO abstaining while WMT/MCD produce fit profiles is a legitimate, publishable asymmetry.
- Surfacing follows the design doctrine: plain-word null disclosure ("we don't have a reliable timing read for this name — here's what we're watching") + Tier-2 receipt.

---

## §12. INTERFACES (deliverable 10)

### 12.1 Inputs
- Daily TR-adjusted price planes: `data/stocks/<SYM>.parquet` (229 curated, deep — KO→1962) and `data/baskets/ohlcv/` (2,519 names, PIT basket membership) + universe/sector/cap/IPO/PIT-index-membership stores (stock library machinery — reused, never rebuilt). The raw `massive_stock_day` plane is out of v0 scope (§9.7).
- Stored expert ledgers (§5 Class R sources) + era-pinned replay. **Harness law:** the existing R1 Rule-Replay rail (`engine/rule_replay.py`, prereg-gated, fire-tape backed) is evaluated first at PR-2; this program extends it where its fire-tape scope fits, and any parallel harness under `engine/stock_identity/replay*` must carry an explicit written justification of why R1's scope cannot serve (never silent duplication). The R1 vintage-stamp schema is adopted either way.
- **`mastermind.entry_event.v1`** (post-Radar-PR-2): the prospective expert-event feed, consumed read-only with `field_origin`/`family_first_available` honesty. Radar PR-0 (#5578) is **unmerged** — PR-1 revalidates this dependency's state and proceeds with Class R replay regardless (no hard dependency on Radar's merge for historical work).
- SEA event store (`data/stock_events/*`) as both an expert family and a cross-check.

### 12.2 Outputs (all display-tier, authority-false)
- `stock_identity.fingerprint.v1` — per (ticker, epoch) fingerprint + coverage mask + spec hash.
- `stock_identity.episode_catalog.v1` — the path-anchored catalog with resolution labels + maturity stamps.
- `stock_identity.fit.v1` — fit profiles with honest-N, CIs, null comparisons, ABSTAIN flags.
- `stock_identity.sif.v1` — the Stock Identity File: `ticker, current_epoch{start, knowable_from, confidence}, fingerprint_ref, current_state, drift_indicator, behavioral_neighbors[], expert_response_profile{by episode_type × tier}, abstain_conditions[], provenance`. **SIF publishes no live episode-type (review finding 20):** a live name's current episode has no anchor yet, so the catalog's definitional object does not exist in real time. The live surface carries `current_state` (§7.1, bars-only, PIT) and the **conditional** profile — "if this resolves as a tier-2 reset, these experts historically localized it on this name" — never an assertion that the name *is* in a tier-2 reset. A live episode-type classifier would be a separate, separately-gated construction with its own leakage surface; it is out of PR-0..N scope. Conceptual example (from the handoff, illustrative only): MCK/compounder-reset → RE-ENTRY strong, STARTER strong, EARLY weak; KRUS/deep-reset → EARLY dominant; KO → abstain on oscillator bottom timing. **These are hypotheses the pilot must test, not pre-authorized outputs.**
- Store home: `data/stock_identity/**`; site surfaces (if any, later) via the standard render lane; nothing enters `site/` in PRs 1–3.

### 12.3 Downstream (read-only seams; no writes from this program)
- `engine/stock_personality.py::setup_compatibility` — the house-named describe-side consumer; may read SIF in a later PR (its own change, its own review), never written by us. **Gate-chain firewall (review finding 19):** no artifact of this program is read by any module reachable from `scripts/build_stock_library.py` before the §12.4 promotion PR — `stock_personality` is read by the stock library, which feeds the gate chain, so the G-8 clean-diff proof covers `engine/stock_personality.py`, `engine/oracle/personality_context.py`, and `scripts/build_stock_library.py` in every PR body. Any eventual SIF consumer must assert on the authority block and fail closed when it is missing (the F-09 lesson made mechanical).
- Prophet: **no interface** until the §12.4 promotion PR. Mastermind: none (its Prophet feed is unrelated).
- Radar: we consume; we never write; per the Radar contract's §18 A1.2 item 5 (positional — the contract carries no literal "A1.2.5" anchor, review finding 23c), Radar records experts and this program learns trust — schema extension requests go through Radar's §18 amendment channel.

### 12.4 Promotion (far future, out of PR-0..N scope)
Any Prophet-consuming routing influence = a separate PR behind: qledger-registered accrual history, the full evaluation-standards ladder (holdout → walk-forward → shadow → live-forward), an explicit prereg in the R4 shape, Article-2 perimeter compliance, and by-name confrontation of `DNR:KILL-OUTCOME-AUDITION` + `DNR:KILL-WASHOUT-TURN`.

---

## §13. PILOT COHORT (deliverable 11)

**Operator core (hypothesis-generating, never confirmatory on their own):** KRUS, MCK, NVDA, REGN, YELP, KO, WMT, MCD, BABA.
**Miner neighborhood probe:** NEM, GOLD, AEM, PAAS, WPM, AG (emergence test, §10).
**Adversarial/controls:**
- **Blind stratified random sample** drawn at PR-1 registration by seeded RNG, stratified on (cap bucket × sector × realized-vol tercile), untouched by design discussion — the anti-selection-bias arm, **sized by the §8.5 power simulation, not by a round number** (review finding 18). Q1 succeeds only if its criterion holds **on the blind arm evaluated separately** (§8.5); joint-only results are exemplar-scoped.
- **Dead names (review finding 18):** at least 5 names that ceased trading, drawn from `config/delisted_symbols.yml` with `terminated_reason` recorded — so every cohort-level statement can name who is missing instead of averaging survivors.
- **Disagreement names:** UEC, HL, NEM (the Golden-Oracle forensic set where Terminal and Macro engines disagreed at bottoms) — stress the era-pinned twin-expert handling.
- **Structure stressors:** one recent IPO (<252 sessions; exercises warm-up/abstention), one collapsed-growth secular decliner beyond YELP (chosen from the delisted/damaged cohort at PR-1 subject to data), one mega-cap steady trender (MSFT) as the "abstain-or-not" control, one known epoch-changer (META, 2022 break) for the §6 detector.
**Membership facts already established (archaeology §6.2):** MCK, NVDA, REGN, KO, WMT, MCD, GOLD, NEM sit in the deep curated store; KRUS and YELP live in the basket OHLCV plane; **BABA, AEM, PAAS, WPM, AG are named in `config.yml extra_tickers` (incl. the Gold-Miners/Silver sleeves) but their deep TR-adjusted store presence is unverified — a PR-1 data gate** (a small permitted collection step if absent, following the CN/HK deep-OHLC template). Remaining verification (history depth, reused-ticker hygiene, delisting status) is a PR-1 gate; any missing name is replaced by its stratum twin with the substitution logged.

---

## §14. PR SEQUENCE (deliverable 12 — proposed, awaiting Sol/operator ratification)

| PR | Scope | Not done unless |
|---|---|---|
| **PR-0** | This contract + archaeology + workstream records. Docs only | All 13 handoff deliverables present; adversarial review §15 filled; records validate (`scripts/agentos.py validate`) |
| **PR-1** | **Identity Atlas v0 (descriptive)**: fingerprint v0 (reusing `path_personality`/`path_risk_signals` substrate) + state tagger + episode catalog over the pilot cohort; per-name dossiers (episode maps the operator can eyeball); catalog/fingerprint constants frozen + registered; blind cohort drawn; coverage census; pilot data gates resolved (BABA/miners adjusted history; KRUS depth; earnings-backfill build-or-defer decision) | Understanding-before-backtest honored (no fit tables yet); constants spec-hashed; dossiers reviewed by operator; zero authority; clean diff on G-8 paths; heavy compute off-path (`backfill.yml` pattern / store-host runs → R2) |
| **PR-2** | **Expert replay + provenance**: era-pinned replay/extraction for Class R experts over the pilot; event↔episode attribution join; leak fixtures (truncation, shift-audit); STARTER-context resolution (or Class C → P reclassification); entry_event.v1 adapter if Radar has merged | Every replayed family carries era + spec hash + leak fixtures green; family keys minted from receipts; no synthetic history for Class P families |
| **PR-3** | **Ruler engine + estimability census**: §7.3 metrics + composites (executable, spec-hashed); §8.2 coverage artifact; TrialLedger budget declared for the fit read | Ruler constants set on the sealed constant partition before any fit read; UNESTIMABLE cells marked; look budget logged |
| **PR-4** | **Epoch detector v1** (synthetic calibration, PIT/final duality, drift indicator) — **before the fit read** (review finding 11: the fit cell keys on epoch, so the detector cannot postdate the read) | Detector null/power/plateau reports published; `knowable_from` lag honored in all joins; no fingerprint revision without voiding affected preregs (§4 law v) |
| **PR-5** | **Fit read #1 (pilot + blind)**: §8.5 power gate → Q1–Q3 graded (IUT / BH as enumerated) + Q4 descriptive; nulls incl. name-permutation + grain-null; plateau checks; opus red-team; operator readout | Primary questions graded at declared metrics only; exemplar-coverage pass led with; honest-N pairs everywhere; **§14.1 consequence matrix applies mechanically** |
| **PR-6** | **Pooling + neighborhoods + abstention + SIF v0** (display-tier artifacts; universe extension beyond pilot as compute allows) — only as licensed by §14.1 | Q2/Q3 incremental-value reads clean; calendar-disjoint pooling enforced; blend weights printed; ABSTAIN triggers pre-registered and firing |
| **PR-7** | **Prospective shadow**: qledger registration; nightly accrual against live expert events (Radar feed when live); identity-drift monitors | Registration humility text (accruing, no backfill, no directional claim); single-advancer law |
| **PR-8+** | Per-name calibration experiments / ticker-specific expert candidates / promotion prereg — each a fresh gated construction | Own prereg each; §12.4 ladder |

### §14.1 Consequence matrix (binding — review finding 5; the program's self-kill condition)

| Q1 outcome (blind arm decisive) | Consequence |
|---|---|
| Fails vs both baselines | **Program STOPS at the fit read.** A `KILL-…` row naming the Channel-A construction is appended to `research/DO_NOT_REBUILD.md` §1–2 with compiled blocklists regenerated in the same PR; descriptive atlas artifacts (fingerprints, catalogs, dossiers) remain display-tier; W4 stays closed. |
| Beats the reference base rate but not the sector-label map | **Channel A is closed.** Only Channel C (SEA-precedent shrinkage) may proceed, display-tier; neighborhoods (Channel B) require a fresh registered question. |
| Passes on pilot+blind jointly but not on the blind arm alone | Result labeled **exemplar-scoped**; PR-6 limited to descriptive artifacts; no pooling claims; a widened blind arm is the only path to re-grading. |
| Passes on the blind arm | **GO** — PR-6 proceeds as scoped. |

The operator ratifies these **criteria** (§16.4) — not whether a gate exists. The gate is unconditional.

Heavy replay compute runs off the render path (episode-windowed, one-off scripts, artifacts to `data/`/R2) — render budget untouched.

---

## §15. ADVERSARIAL REVIEW (deliverable 13)

*Review executed 2026-08-13 by an independent opus reviewer against the nine commissioned attack vectors plus citation spot-checks, internal consistency, statistical design, and a steelman of the kill-escape argument. All load-bearing citations were verified against sources. Reviewer's verdict, verbatim: "unusually strong on governance … weak on measurement specification, and the weakness is concentrated in exactly the places that decide whether G-2 is enforceable … §2.3's differentiation from `DNR:KILL-OUTCOME-AUDITION` is thinner than the contract claims … The escape is available — a low-capacity map, name-disjoint OOS, and a name-permutation null would make it real and testable." All must-land findings were folded into this contract before freeze; the remainder are named obligations binding on PR-1 registration.*

**Blockers (all landed in this revision):**
1. Primary metric undefined ("localization composite") → two frozen composite forms `C-LOC-R`/`C-LOC-D`, executable + spec-hashed before PR-3, constants set blind, no third allowed (§7.3).
2. Channel A indistinguishable from the audition (no capacity bound, no name-holdout, fingerprint ≈ unique name key) → capacity budget `p_eff ≤ N_names/10`, name-blocked K-fold as primary OOS, name-permutation null as §8.3 null 5 (§2.3, §8.3, §9.2). *The single highest-value change in the review.*
3. Ruler had no unconditional false-positive rate (episode-conditioned throughout; the `KILL-VOLUME-FINGERPRINTS` selection-gate artifact applied to our own instrument) → mandatory unconditional block: `fires_per_name_year`, `episode_attribution_rate`, NC-2-shaped matched-control comparison; no fit claim without attribution rate alongside (§7.3, §8.2).
4. ~110–120 free constants in a "frozen" contract, with §16.2 requesting a data-informed initialization on the grading data → blind constant-setting partition (30% of names, exemplars + blind arm excluded, pre-boundary history), named+hashed at PR-1, sealed thereafter; holdout re-based on episode floors, not calendar months (§9.3, §9.2, §16.2).
5. GO/NO-GO had no criterion, no consequence, and was itself optional → §14.1 binding consequence matrix incl. the program's self-kill condition; operator ratifies criteria, not gate existence (§14.1, §16.4).
6. (F15) "Beats both baselines at BH q=0.10" was a category error for a conjunction → intersection–union test at α=0.05 with the family enumerated (Q1 IUT; BH q=0.10 over {Q2,Q3} only; Q4 descriptive); Q1's correlation margin specified within-expert/across-name (§8.5).
7. (F22) The kill row was quoted one clause short of "W4 per-class gate profiles are UNLICENSED under both rulers," and the archaeology glossed an unconditional unlicensing as conditional → clause restored verbatim; Channel-A-is-W4-shaped confronted head-on; archaeology corrected (§2.1, §2.3; archaeology §1.1).

**Majors landed in this revision:** metric/diagnostic fingerprint block split (F6, §4); miner β-gold removed, universal factor panel, emergence-tautology guard (F7, §4/§10); plane-availability law — F6-gap family excluded rather than masked, plane recorded (F8, §4); bars-only state tagger, gap proxy for `post_event_dislocation` (F9, §7.1); `epoch_pit`/`epoch_final` duality, PIT primary (F10, §6); epoch detector re-sequenced before the fit read + representation-revision voiding law (F11, §14/§4); STARTER split into pending/failed/converted, non-collapsible pairs enumerated (F12, §5); Class B locked-spec backcast minted — `tier_cascade` and the Terminal grey-dot twin moved there, grey-dot as-recorded/as-restated dual report (F13, §5); calendar-block bootstrap ≥ P90 episode duration + two-way cluster variance + cluster-count census columns + honest-N pair (F14, §8.1/§8.2/G-6); power gate with deferral-as-result + underpowered-ABSTAIN (F16, §8.5/§11); calendar-disjoint neighbor pooling with discard share printed (F17, §10); blind arm sized by power sim + evaluated separately + ≥5 dead names from `config/delisted_symbols.yml` (F18, §13/§8.5); G-8 extended over `stock_personality`/`personality_context`/`build_stock_library` + gate-chain firewall + F-09 fail-closed consumer law (F19, §0/§12.3); SIF publishes no live episode-type — conditional profile only (F20, §12.2); PTT-W1b SPEED/FAMILY caveats carried verbatim + grain stratification + grain-null (F21, §2.2/§7.3/§8.3); per-type ruler anchors + censored-episode rule (F25, §7.3); canonical cell key fixed (F24, §3); citation/cross-reference corrections (F23, throughout + archaeology).

**Defended (per the reviewer):** TrialLedger/look-budget wiring; `path_personality` citations (all resolve); the estimator-law citations; the `entry_event.v1` field list; shipped-parameters-only (the strongest audition side-door closure); the fire-count-matched random-fire null; equal-proximity comparison (scope widened per F26's note); Channel C as genuinely-not-argmax; hindsight-labeling disclosure; ticker-identity hygiene; `massive_stock_day` prohibition; era-pinned grey-dot twins; family preservation for the other two non-collapsible pairs.

---

## §16. OPEN RULINGS REQUESTED FROM SOL / OPERATOR

1. **Ratify the Method Law (§2.3)** — in particular that per-name evidence enters only as shrinkage (Channel C), never argmax. This is the load-bearing legal interpretation of `DNR:KILL-OUTCOME-AUDITION`'s carve-out.
2. **Ratify the primary ruler orientation (§7.3)** — localization-first with returns secondary — **and the constant-setting data** (re-put per review finding 4): all free constants are set at PR-1 on the sealed blind partition of §9.3 (30% of names, exemplars and blind arm excluded, pre-boundary history only) — the question is not *when* constants are set but *on what data*; an initialization pass on the grading data is the uncounted look the review refused.
3. **Pilot compute/home** — approve the off-render one-off replay pattern and `data/stock_identity/**` as the store home.
4. **Ratify the §14.1 consequence-matrix criteria** (reworded per review finding 5) — the GO/NO-GO gate after the fit read is unconditional; what needs the operator's ruling is the criteria themselves, including the self-kill row (Q1 fails both baselines → program stops and a KILL row is minted).
5. **Radar coupling** — confirm this program should NOT block on Radar's merge (current design: Class R history proceeds independently; prospective feed attaches when Radar PR-2+ lands).
6. **Tops sibling** — confirm tops remain a separate future program (no shared-substrate case found).
7. **Registry row** — approve minting a `stock-identity` row in `config/mastermind_programs.yml` (subprogram of `market-timing-intelligence`) at PR-1, so the workstream's parent key stops borrowing the umbrella program.
8. **BABA/ADR + CN scope** — v0 is US-listed (incl. ADRs); CN-listed names deferred until the US pilot reads out.

---

## §17. RECORDS

- Workstream: `agentos/workstreams/WS-STOCK-IDENTITY.md` (this PR) — program `market-timing-intelligence`, p0 `US_PROPHET_ENTRY_TIMING`, owns_paths per G-8.
- Decision minted this PR: `DEC:SI-METHOD-LAW-CHANNELS` (the §2.3 interpretation and its alternatives).
- Handoff: `agentos/handoffs/STOCK-IDENTITY-<date>.md` per protocol.
- Citation keys used: `DNR:*` rows per archaeology §3; `WS:LIVE-ENTRY-RADAR` (unmerged, #5578); `DEC:LER-EXPERT-EVENT-FAMILIES-PRESERVED` and `DEC:LER-ROUTING-LAW-NOT-OUTCOME-AUDITION` (**both pending** — they exist only in the unmerged Radar branch and do not resolve on main until #5578 merges; `agentos validate` passes because joins fail open); `DEC:GAUNTLET-GATES-PROMOTION-NOT-BUILD`; `DEC:CONCLUSIONS-NEED-A-COVERAGE-PASS`; `DEC:INSTRUMENT-VERDICT-IS-NOT-MARKET-VERDICT`.
- Handoff-deliverable map (deliverable 1 labeled per review finding 23f): 1 = archaeology map (companion doc §1–§3); 2 = §5 + archaeology §4; 3 = §4; 4 = §6; 5 = §7; 6 = §8; 7 = §9; 8 = §10; 9 = §11; 10 = §12; 11 = §13; 12 = §14; 13 = §15.
