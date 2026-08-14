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
- **G-6 (Honest N + coverage first).** Every conditional cell reports distinct-episode N (never fires/dates); a coverage/estimability census precedes any cell-conditioned design (`DNR:KILL-PER-SIGNAL-FAMILY-RELIABILITY` lesson); ABSTAIN is a first-class output.
- **G-7 (Look budget).** Every sweep registers into `engine/trial_ledger.py` before running; confirmatory questions are pre-registered with one primary metric each; everything else is labeled exploratory.
- **G-8 (Path partition).** This program never touches `engine/entry_signal.py`, `engine/signal_gate.py`, `engine/confluence_tiers.py`, `engine/signal_quality.py`, `engine/prophet_*.py`, `engine/washout_turn.py`, `engine/mtf_upturn.py`, Radar's `engine/entry_radar/**`, or Terminal repo internals. Every engine PR prints `git diff --stat` on those paths (clean) in the PR body. New code lives only in `engine/stock_identity/**`, `scripts/stock_identity_*.py`, `data/stock_identity/**`, `research/STOCK_IDENTITY_*`, `research/stock_identity/**`.
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

**Motivating exemplars are motivation, not evidence.** The operator's visual reads (KRUS deep-reset ↔ amber EARLY; MCK staircase ↔ STARTER/RE-ENTRY; NVDA violent-reset trend ↔ situational RE-ENTRY/grey; YELP secular-decline RE-ENTRY weakness vs deep-EARLY near the 2026 washout; KO vs WMT/MCD defensive-label divergence; the gold/silver-miner shared personality; BABA's recognizable grammar) are recorded exactly as Radar's A1.2.6 records them: a small-N visual read standing **against** a measured n=1,300 null on per-name selection persistence — the thing the program must test, never a result it may assume. They serve as the exemplar-coverage set (§9.6) and pilot core (§13).

---

## §2. LEGAL FOOTING — WHAT IS ALREADY KNOWN, AND THE METHOD LAW

### 2.1 The kill that binds (and its exact scope)

`DNR:KILL-OUTCOME-AUDITION` (PTT-W1a): per-name timing-tool selection by in-sample outcome ranking has **zero OOS persistence** at n=1,300 names / 109,974 signals — **under both** the fwd63 apparatus **and** the corrected bottom-picking/timing ruler (FIT-best in TEST top-2: 33.2% and 35.0% vs 33.3% chance). Per-name "home rungs" are ruler-dependent (5/7 defensives flip). Consequence for this program: *"which expert fits this name"* answered by the name's own outcome ranking is dead however the ruler is phrased. The kill row's recorded carve-out — *"structure-MEASUREMENT tailoring stays OPEN and is UPGRADED under the timing ruler"* — is this program's license.

### 2.2 The affirmative result this program continues

PTT-W1b (structure tailoring): deriving tool/rung mechanically from bars-only measured structure (swing period, mean-reversion half-life, trend persistence), with events validating (never selecting), was **the only arm above the random floor, CI-clean**: U_MAE +0.41pp [+0.13, +1.16]; proximity +5.87pp [+3.51, +6.43] vs random. And the class-altitude finding — vol×trend terciles and fundamentals archetype do NOT separate — leaves grouping **discovery** (never tested; repo-wide absence verified) as the open front.

### 2.3 The Method Law — three lawful evidence channels

All per-name expert conditioning flows through these channels, in this order of precedence; anything else is G-2 territory:

- **Channel A — structure-derived compatibility (global map).** A single cross-sectional mapping, estimated over ALL names at once, from fingerprint features to expert-fit metrics: `fit(expert, episode-type | fingerprint)`. A name receives its expert profile by *evaluating the global map at its own fingerprint* — per-name degrees of freedom ≈ 0. This is PTT-W1b generalized: the name never chooses its expert; its measured structure does, through a map whose form is fixed cross-sectionally.
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
| **Expert-response profile** | The vector of §8 fit metrics for (ticker, epoch, episode-type, expert), with honest-N and CIs | — |
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
| F9 Factor/idio | rolling β to SPY + sector ETF; R² (idio share); miners: β to gold | `engine/residual_alpha.py` sector-neutral machinery |
| F10 Liquidity/size | ADV, dollar-vol rank, turnover; cap bucket; spread estimate | `path_personality._dollar_adv_series`; `engine/entry_primitives.py` (Amihud, Corwin-Schultz); stock library fields |

**Laws:** (i) every feature PIT-computable from the daily store (no minute data required for the fingerprint); (ii) plateau requirement — a feature unstable across nearby windows for a name is flagged `unstable`, not averaged silently; (iii) features that are killed constructions (onset/volume fingerprints as *predictors*) enter only as descriptive coordinates, never as promoted predictive features without their own prereg; (iv) sector/industry membership may appear as candidate features (per G-1) but never as the pooling key; (v) the fingerprint is versioned (`fingerprint_spec_hash`) and every downstream fit table pins the version.

---

## §5. EXPERT LIBRARY v0 (deliverable 2)

The canonical census lives in archaeology §4 (producers, formulas, authority, replayability — both repos). The frozen v0 library for fit measurement, by replayability class:

**Class R (historically fit-measurable now):**
1. `grey_dot` — raw anticipation dot (Macro `signal_frame.early`; Terminal twin era-pinned separately; both replayable, era strings distinct).
2. `confirmed_buy` / `rebuy` — classic confluence BUY/REBUY (ledgered in `data/signal_archive/track_record.parquet` + recomputable).
3. `tier_cascade` T1–T4 states (recompute via `tier_stream()`).
4. `reclaim_waiver` ("block repair") — re-derivable with committed nightly state.
5. `weekly_washout_turn` — organ ledger + recompute.
6. `bottom_watch_terminal` — Terminal washout-context events (artifact + locked-spec fallback per Radar §3.4).
7. `sea_event_classes` — SEA's stored event store (389,799 events) as context experts.
8. Naive reference experts (§8.3 comparators): `rsi30_cross`, `low20d_bounce`, `stoch2w_cross` (the PSS incumbent gauge).

**Class P (prospective-only; accrue, never backfill):** `amber_early` (family born 2026-08-11), `door_r_rearm` (charter forbids backfill), `turn_watch_deck` fires, GC-v2 keeper/recipe scores, Radar `C1/C2` LIVE-state detectors (minute-reconstruction rule inherited), lobe-conditioned anything.

**Class C (conditional):** `starter_licensed` — signature replayable; the basket/leader licensing context needs PIT basket-state reconstruction (open item PR-2; if unresolvable, STARTER's *signature* is measured Class R and its *licensed* form accrues Class P).

**Laws:** family keys are minted from emitter receipts at instrumentation time (Radar A1.3 discipline), never invented; every family carries `family_first_available`/`family_era` and structural absence is never read as negative evidence; the Macro/Terminal grey-dot twins are measured as **two era-pinned experts** until a parity check collapses them (archaeology §4.5.2); `mastermind.entry_event.v1` becomes the ingestion path for prospective events once Radar PR-2 lands (§12.1) — this program never re-derives what that store records, and never writes into it.

---

## §6. IDENTITY EPOCHS (deliverable 4)

**Definition:** an epoch boundary is a persistent shift in the fingerprint process — not a market-cap threshold, not a hindsight chart annotation.

**Detector v0 (frozen intent; constants at PR-5 registration):**
1. Compute the fingerprint on rolling trailing windows (252d, stepped ~21d).
2. Candidate boundary at t when the standardized distance (Mahalanobis on a pinned feature subset with shrunk covariance) between the trailing-252d and preceding-252d fingerprint exceeds a threshold **and stays exceeded for ≥K consecutive steps** (persistence, so a single washout episode — which is an *episode*, not a new identity — cannot fragment epochs).
3. Confirmation lag is explicit: a boundary at t is *knowable* only at `t + K·21d`; all PIT uses honor the lag (G-4). Minimum epoch length ≈ 12 months.
4. Corroborating covariates (market-cap decade change, index add/drop, listing venue change, float events) are recorded as boundary *evidence annotations* — never sufficient nor necessary.
5. Output per ticker: epoch list (start, knowable-from, confidence, dominant shifted features) + a continuous **identity-drift indicator** (current-window distance from current-epoch centroid) that consumers read as "read being updated" long before a boundary confirms.

**Detector validation (before any epoch-conditioned fit claims):** (a) null calibration on stationary block-bootstrap simulations → false-boundary rate under control; (b) power on synthetic injected shifts; (c) face validity on known structural cases (NVDA pre/post datacenter era; BABA pre/post 2021; KRUS IPO maturation; META 2022) — reported as illustrations, not gates; (d) stability: detector output insensitive to ±20% threshold perturbation (plateau, not needle).

**Era interaction:** macro-era splits (`DNR:LAW-ERA-SPLIT`, 2010 break) remain analysis strata regardless of per-name epochs; an epoch spanning an era boundary is reported split.

---

## §7. STATE, EPISODE CATALOG, AND THE INDEPENDENT EPISODE RULER (deliverable 5)

### 7.1 State (small, mechanical, frozen at PR-1)

Eight mutually-exclusive path states from daily bars only: `structural_uptrend`, `controlled_pullback`, `range`, `breakdown`, `deep_washout`, `recovery_reclaim`, `post_event_dislocation`, `vol_transition`. Definitions are simple threshold rules on (distance to 200DMA, drawdown from 252d high, realized-vol percentile, days-since-earnings-gap). State is a **covariate** on episodes, not a fit-cell key in v0 (estimability first, G-6).

### 7.2 The episode catalog (expert-independent, path-anchored)

Built once per ticker from the daily store by a frozen mechanical segmentation — **no expert fires anywhere in its construction** (G-3):

- **Reset/decline episodes:** every leg where price falls ≥ X·ATR (and ≥ Y%) from a rolling 126d high, from leg start until either (a) a **durable low** — no lower low for ≥ N sessions AND rebound ≥ k·ATR (and ≥ z%) — or (b) truncation (delisting/data end; censored, never dropped — LER convention).
- **Reclaim episodes:** first sustained recapture of a pinned reference (e.g. 200DMA or prior range low) after a breakdown, with resolution labels (held / failed within M sessions).
- **Failed-breakdown episodes:** close below a 60d low that recovers the level within m sessions.
- Constants (X, Y, N, k, z, M, m) are frozen at PR-1 registration with a declared, look-counted sensitivity grid (diagnostic-only), mirroring LER §10's pattern.

**Labeling honesty:** episode **resolution labels use future data by design** — the catalog is a research-time labeling instrument, not a live signal; nothing downstream ships a label before its window matures. Expert events joined to episodes remain strictly PIT. Depth is context, never a bonus (`no zero-print requirement`, no deepest-drawdown ranking — inherited from Radar's do-not-build list).

**Meaningfulness tiers:** episodes are tiered by economic significance (e.g. ≥20%/≥35% depth, duration floors) so that recall metrics quote their tier explicitly.

### 7.3 The ruler (per expert fire × episode; primary object = localization, not return)

For each episode E with durable low L(T_L) and each expert fire F(t_F, known_ts) attributable to E (attribution window frozen at PR-1):

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

Secondary columns: forward return at H∈{5,10,21}, MFE/MAE (strictly-forward window, LER sign conventions), benchmark/sector excess. These are reported, never the primary fit criterion (G-3), and reversion-shaped experts are read on reversion-capture horizons per `DNR:LAW-REVERSION-RULER`.

**House precedent:** the incumbent 2W StochRSI gauge's −2td trough-timing figure and PTT §7's U_MAE/proximity/td_to_trough metrics are this ruler's direct ancestors; the ruler generalizes them to a catalog of path-defined episodes with recall/flooding added.

**Tops are out of scope.** The archaeology found no shared bottom/top substrate cheap enough to justify widening PR-0; a sibling program owns tops (§16.6).

---

## §8. EXPERT-FIT MEASUREMENT (deliverable 6)

### 8.1 The fit profile

For each (ticker, epoch, episode-tier, expert): the ruler-metric vector, distinct-episode honest-N, and CIs from an **episode-level, month-clustered bootstrap** (never ticker-only clustering — `DNR:LAW-TIME-CLUSTERED-CI`; market-wide washouts hit all names at once and must not be double-counted as independent evidence). Per-name-first aggregation everywhere (PSS E1 errata precedent).

### 8.2 Estimability census precedes design (G-6)

Before any fit table: a coverage census — episodes per (ticker × tier), fires per (expert × ticker), joint cell occupancy — published as its own artifact. Cells below pre-registered floors are marked `UNESTIMABLE` and never reported as nulls (`DNR:KILL-PER-SIGNAL-FAMILY-RELIABILITY`: most axes there died of coverage, not signal).

### 8.3 Null models and comparators (all mandatory in the primary read)

1. **Random-fire placement:** the expert's fire count redistributed uniformly (and dwell-matched) inside the episode → does the expert localize better than chance *given how often it fires*? (PTT per-metric random-day null, generalized.)
2. **Naive comparators:** `rsi30_cross`, `low20d_bounce`, `stoch2w_cross` run through the identical ruler — an expert that cannot beat a trivial oscillator for a name earns no fit claim there.
3. **Global base rate:** the expert's cross-name fit distribution — a name's fit is only *distinctive* if it separates from the expert's base rate (this is what makes "KRUS is an EARLY name" a claim about KRUS rather than about EARLY).
4. **Proximity honesty:** washout-shaped experts sit near lows by construction; where a fit claim is "this expert marks THE low" the comparison is against other low-adjacent triggers at equal proximity (NC-2 spirit), not against far-from-low fires.

### 8.4 Robustness (plateau, not needle)

Where an expert is parameterized, fit must persist under ±20% perturbation of its thresholds and of the ruler's zone constants (declared grid, look-counted, diagnostic-only). Experts are otherwise run at **shipped parameters only** — no per-name tuning anywhere in PRs 1–6 (per-name calibration is a later, separately-gated stage, §14).

### 8.5 What a "fit" claim means (and the lawful channels)

A cell's fit estimate feeds Channel A's global map (fingerprint → fit), Channel B's neighborhoods, and Channel C's shrunk residual — §2.3. The program's **first registered confirmatory question** (PR-4) is the persistence question the audition failed:

> **Q1.** Does the Channel-A global map, fit on FIT-era episodes, predict OOS (TEST-era + held-out-episode) localization fit better than (a) the global expert base rate and (b) a sector-label map? *Primary metric: out-of-sample rank correlation between predicted and realized per-(name, expert) localization composite; success = beats both baselines at BH q=0.10.*

Secondary registered questions (frozen wording at PR-4 prereg): Q2 — do behavioral neighborhoods transfer fit better than sector groupings? Q3 — does per-name residual shrinkage (Channel C) add OOS value over A+B at printed n? Q4 — exemplar coverage: does the map's answer for KRUS/MCK/NVDA/REGN/YELP/KO/WMT/MCD/BABA/miners match or refute the operator's visual reads, case by case (reported both ways)?

---

## §9. HISTORICAL VALIDATION DESIGN (deliverable 7)

1. **Maximal legitimate history.** All replayable history is in scope (Class R experts; ≥2005 where the store reaches, era-split at the 2010 break). "Avoid overfitting" is implemented as search discipline, never as discarding history.
2. **Splits.** Era discipline per DT-R16: declared FIT/TEST split; full-sample-only effects disqualified. Within eras: leave-one-episode-out / leave-one-cycle-out rolling evaluation (episodes are the resampling unit). **Untouched holdout:** the most recent 6 months of replayable history at first replay, plus everything after the live-forward start.
3. **Mining controls.** TrialLedger registration before any sweep (G-7); pre-registered primary metrics (§8.5); BH-FDR q=0.10 on the confirmatory family; declared sensitivity grids counted in the look budget; no post-hoc metric additions without an amendment; `spec_hash` on catalog constants, fingerprint version, and ruler constants, verified before outcomes attach (LER's prereg-commit-hash mechanism reused).
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

- Neighborhoods are computed in fingerprint space; **sector/industry is never the grouping key** (G-1) but sector-label grouping is always run as the *comparison baseline* (Q2) — if GICS beats discovered neighborhoods, that is reported, not hidden.
- The miner test: if the gold/silver-miner cluster is real, it should **emerge** (miners mutually nearest in fingerprint space) and the neighborhood's within-group fit transfer should beat the sector-label grouping's. Reported either way.
- Every pooled estimate prints its blend weights and component n's (SEA receipt discipline).

---

## §11. ABSTENTION CONTRACT (deliverable 9)

`ABSTAIN — no reliable timing edge` is a first-class, product-visible answer at every level (cell, episode-type, whole name):

- **Triggers (pre-registered at PR-4):** honest-N below floor; no expert separates from the §8.3 nulls; fit unstable across epochs (drift indicator high); coverage mask too sparse; Channel A/B priors uninformative and Channel C n too small.
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
- `stock_identity.sif.v1` — the Stock Identity File: `ticker, current_epoch{start, knowable_from, confidence}, fingerprint_ref, current_state, drift_indicator, behavioral_neighbors[], expert_response_profile{by episode-tier}, abstain_conditions[], provenance`. Conceptual example (from the handoff, illustrative only): MCK/compounder-reset → RE-ENTRY strong, STARTER strong, EARLY weak; KRUS/deep-reset → EARLY dominant; KO → abstain on oscillator bottom timing. **These are hypotheses the pilot must test, not pre-authorized outputs.**
- Store home: `data/stock_identity/**`; site surfaces (if any, later) via the standard render lane; nothing enters `site/` in PRs 1–3.

### 12.3 Downstream (read-only seams; no writes from this program)
- `engine/stock_personality.py::setup_compatibility` — the house-named describe-side consumer; may read SIF in a later PR (its own change, its own review), never written by us.
- Prophet: **no interface** until the §12.4 promotion PR. Mastermind: none (its Prophet feed is unrelated; F-09 authority-boolean lesson noted — SIF consumers must read the authority block, and our artifacts publish it false).
- Radar: we consume; we never write; per A1.2.5 Radar records experts, this program learns trust — schema extension requests go through Radar's §18 amendment channel.

### 12.4 Promotion (far future, out of PR-0..N scope)
Any Prophet-consuming routing influence = a separate PR behind: qledger-registered accrual history, the full evaluation-standards ladder (holdout → walk-forward → shadow → live-forward), an explicit prereg in the R4 shape, Article-2 perimeter compliance, and by-name confrontation of `DNR:KILL-OUTCOME-AUDITION` + `DNR:KILL-WASHOUT-TURN`.

---

## §13. PILOT COHORT (deliverable 11)

**Operator core (hypothesis-generating, never confirmatory on their own):** KRUS, MCK, NVDA, REGN, YELP, KO, WMT, MCD, BABA.
**Miner neighborhood probe:** NEM, GOLD, AEM, PAAS, WPM, AG (emergence test, §10).
**Adversarial/controls:**
- **Blind stratified random sample (~12 names)** drawn at PR-1 registration by seeded RNG, stratified on (cap bucket × sector × realized-vol tercile), untouched by design discussion — the anti-selection-bias arm; confirmatory claims must generalize here (Q1/Q2 are evaluated on blind+pilot jointly, with pilot-only effects labeled as such).
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
| **PR-3** | **Ruler engine + estimability census**: §7.3 metrics computed; §8.2 coverage artifact; TrialLedger budget declared for the PR-4 read | Ruler constants pre-registered before any fit read; UNESTIMABLE cells marked; look budget logged |
| **PR-4** | **Fit read #1 (pilot)**: fit profiles + nulls + plateau checks; Q1–Q4 registered then answered; opus red-team; operator readout | Primary questions graded at declared metrics only; exemplar-coverage pass led with; honest-N everywhere; **GO/NO-GO ruling requested before PR-5** |
| **PR-5** | **Epoch detector v1** + fingerprint v1 (informed by PR-4), synthetic calibration, drift indicator | Detector null/power/plateau reports published; PIT lag honored in all joins |
| **PR-6** | **Pooling + neighborhoods + abstention + SIF v0** (display-tier artifacts; universe extension beyond pilot as compute allows) | Q2/Q3 incremental-value reads clean; blend weights printed; ABSTAIN triggers pre-registered and firing |
| **PR-7** | **Prospective shadow**: qledger registration; nightly accrual against live expert events (Radar feed when live); identity-drift monitors | Registration humility text (accruing, no backfill, no directional claim); single-advancer law |
| **PR-8+** | Per-name calibration experiments / ticker-specific expert candidates / promotion prereg — each a fresh gated construction | Own prereg each; §12.4 ladder |

Heavy replay compute runs off the render path (episode-windowed, one-off scripts, artifacts to `data/`/R2) — render budget untouched.

---

## §15. ADVERSARIAL REVIEW (deliverable 13)

*Review executed by an independent opus reviewer against the nine commissioned attack vectors (top-down leakage, hindsight epochs, parameter mining, taxonomy collapse, return-only ruler, correlation-vs-usefulness, lookahead, exemplar selection bias, premature strategy factory).*

<!-- REVIEW-FINDINGS -->

---

## §16. OPEN RULINGS REQUESTED FROM SOL / OPERATOR

1. **Ratify the Method Law (§2.3)** — in particular that per-name evidence enters only as shrinkage (Channel C), never argmax. This is the load-bearing legal interpretation of `DNR:KILL-OUTCOME-AUDITION`'s carve-out.
2. **Ratify the primary ruler orientation (§7.3)** — localization-first with returns secondary; and the durable-low parameterization being frozen at PR-1 rather than PR-0 (constants need one measurement pass to set sanely).
3. **Pilot compute/home** — approve the off-render one-off replay pattern and `data/stock_identity/**` as the store home.
4. **PR-4 GO/NO-GO checkpoint** — confirm the operator wants the explicit ruling gate after the first fit read (the alternative — rolling into PR-5/6 without a readout — is faster but spends build effort before the thesis's first OOS test).
5. **Radar coupling** — confirm this program should NOT block on Radar's merge (current design: Class R history proceeds independently; prospective feed attaches when Radar PR-2+ lands).
6. **Tops sibling** — confirm tops remain a separate future program (no shared-substrate case found).
7. **Registry row** — approve minting a `stock-identity` row in `config/mastermind_programs.yml` (subprogram of `market-timing-intelligence`) at PR-1, so the workstream's parent key stops borrowing the umbrella program.
8. **BABA/ADR + CN scope** — v0 is US-listed (incl. ADRs); CN-listed names deferred until the US pilot reads out.

---

## §17. RECORDS

- Workstream: `agentos/workstreams/WS-STOCK-IDENTITY.md` (this PR) — program `market-timing-intelligence`, p0 `US_PROPHET_ENTRY_TIMING`, owns_paths per G-8.
- Decision minted this PR: `DEC:SI-METHOD-LAW-CHANNELS` (the §2.3 interpretation and its alternatives).
- Handoff: `agentos/handoffs/STOCK-IDENTITY-<date>.md` per protocol.
- Citation keys used: `DNR:*` rows per archaeology §3; `WS:LIVE-ENTRY-RADAR` (unmerged, #5578); `DEC:LER-EXPERT-EVENT-FAMILIES-PRESERVED`; `DEC:GAUNTLET-GATES-PROMOTION-NOT-BUILD`; `DEC:CONCLUSIONS-NEED-A-COVERAGE-PASS`; `DEC:INSTRUMENT-VERDICT-IS-NOT-MARKET-VERDICT`.
