# STOCK IDENTITY — W1 / PR-1 REGISTRATION: IDENTITY ATLAS v0

**Wave:** W1 (masterplan §14 PR-1 row, executed under the §16.9 authorization after #5583 merged 2026-08-14T10:02Z, merge `29d89724c8`).
**Binding contract:** `research/STOCK_IDENTITY_EXPERT_ROUTING_MASTERPLAN_BY_FABLE.md` (frozen; §16 rulings ratified). This document REGISTERS the W1 design: partitions, frozen constants, the fingerprint enumeration, the state tagger, the episode catalog, and the coverage census — descriptive/measurement-first.
**Hard exclusion (§16.9):** no expert-fit result, ranking, or expert-conditioned table exists anywhere in W1. Every artifact ships `authority: {can_rank, can_size, can_gate, can_originate_signal, can_escalate} = all false`.
**Radar revalidation (PR-0 handoff obligation):** Live Entry Radar PR-0 (#5578) re-checked at W1 start — still OPEN/unmerged. Per ruling §16.5 nothing here blocks on it; `mastermind.entry_event.v1` remains a proposed seam; no Radar coupling in W1.

---

## §1. Universe enumeration (v0 evaluated universe)

- Universe = union of the two allowed TR-adjusted planes (§9.7): `data/stocks/*.parquet` ∪ `data/baskets/ohlcv/*.parquet`, deduped by symbol. Per-symbol **primary plane** = `stocks` if present there else `baskets` (deeper curated store wins). `price_plane_id ∈ {stocks_tr_v1, baskets_ohlcv_v1}` recorded on every downstream row (§4 law vi).
- Identity is **instrument-level** (§16.8/§3): the symbol names the traded listing on its plane; no issuer merging; cross-listings are distinct instruments.
- No name is removed for being delisted/truncated (censored-never-dropped, §9.5). Hygiene annotations (§9.6) mark rows; they do not delete them.
- Snapshot artifact: `data/stock_identity/partition/universe_snapshot_v1.parquet` — symbol, primary plane, first_date, last_date, n_rows, hygiene flags — plus `universe_sha256` = SHA256 over the canonical sorted `symbol,plane` CSV. All draws below are functions of (this snapshot, the seeds below) and nothing else.
- **asof** for all W1 snapshots/ranks: the last trading date common to both planes at build time (recorded in the snapshot manifest).

## §2. Pilot cohort (design-touched; excluded from blind arm AND calibration partition)

Fixed §13 membership plus the two PR-1 choices, chosen by rule:

- Operator core: KRUS MCK NVDA REGN YELP KO WMT MCD BABA.
- Miner probe: NEM GOLD AEM PAAS WPM AG.
- Disagreement set: UEC HL (NEM already present).
- Stressors: MSFT (steady-trender control), META (known epoch-changer), plus
  - **Recent IPO** (chosen at PR-1 by rule): the baskets-plane name with the most recent first_date having ≥60 and <252 sessions and no hygiene flags. → **CBRS**, first print 2026-05-14, 63 sessions, `open` available, no hygiene flags, first-print sanity `OK` (within 0d of the Nasdaq deal calendar's priced date). Pool = 52 qualifying names; runners-up by first_date: AVLN (2026-04-30, 73), SBMT (2026-04-30, 73), ELMT (2026-04-23, 78). At 63 sessions CBRS is below the 252-session fingerprint floor, so it is coverage-masked on **every** metric-block feature and catalogues **0** episodes — which is precisely the warm-up/abstention path this stressor was added to exercise, not a defect. Receipt: partition manifest `pilot.receipts.recent_ipo`.
  - **Secular decliner beyond YELP** (chosen at PR-1 by rule): among ceased-tape names (§13-dead-pool below) with ≥1,000 sessions, the one with the deepest close-to-close max drawdown over its final 1,260 sessions (damaged-cohort rule; membership choice is design-touched and never evidence). → **FFAI** (Faraday Future), max drawdown over its final 1,260 sessions = **−99.99992%**; 1,476 sessions, baskets plane, 23 episodes. **Logged substitution:** the ceased-tape pool this clause names is empty (see the dead-names row below), so the pick was taken from the **damaged** half of masterplan §13's own "delisted/**damaged** cohort … subject to data" disjunction, under the identical depth rule and over a 2,532-name pool. Runners-up: TNXP (−99.9985%), GDC (−99.990%), HURA (−99.987%) — the near-ties are all reverse-split-adjusted collapses, so the pick is a coin-flip among a damaged class rather than a distinctive finding, and nothing about it is evidence. Receipt: partition manifest `pilot.receipts.secular_decliner`.
- **Dead names (≥5, §13) — MEASURED IMPOSSIBLE on the allowed planes; W1 ships survivor-only (adjudicated at W1, operator decision requested):** the masterplan draws these from `config/delisted_symbols.yml`, but that ledger holds exactly **2 rows** (CTRA, TPH — both acquired, Form 25-NSE), and **neither has a price file on either allowed plane** (verified directly). The registered substitution rule (baskets-plane names whose tape ended ≥126td before asof with ≥756 sessions) returned **ZERO candidates**: the largest tape-end lag anywhere in the 2,781-name universe is **32 sessions** (a shared refresh artifact on names like CRTO/NIO/SONY, not deaths) — the allowed planes structurally do not retain ceased tapes. No substitute was invented ("a live name relabeled 'dead' would corrupt every survivorship read this cohort exists to enable" — builder receipt, adopted). Consequences, binding on W1 artifacts: (i) every cohort-level statement in this wave is **survivor-only and stamped so** (census header + dossiers); (ii) the S&P1500 PIT-membership survivorship stratification substrate is unaffected and still used; (iii) supplying dead names needs an **operator decision at the §16.9 return** — extend `config/delisted_symbols.yml`, or admit a close-only plane for *census-only* dead-name rows under a fresh registration (the §9.7 plane law bars it from catalogs/fingerprints: no high/low → no A0/ATR). Receipt: partition manifest `pilot.receipts.dead_names`.
- §9.6 ticker-identity hygiene is run on EVERY pilot name (reused_ticker_acks / ticker_key_migrations / breadth.ticker_fixups / delisted_symbols cross-check + first-print sanity vs listing history); results per name in §9 below.

## §3. Blind evaluation arm (drawn FIRST; untouched thereafter)

- Eligible pool: universe − pilot − names with unresolved reused-ticker splice flags − names with <504 sessions.
- Strata: cap bucket × sector × trailing-252d realized-vol tercile (vol computed at asof from the primary plane; metadata source per §10; names with missing metadata land in an `UNKNOWN` stratum rather than being dropped).
- Draw: for every non-empty stratum, a seeded full shuffle; the **provisional arm = first 3 names per stratum in draw order**. The full per-stratum draw ORDER is persisted.
- **Provisionality (binding):** final blind-arm size is set by the §8.5 power simulation at PR-5, which may only (a) **prefix-shrink** — take the first k ≤ 3 per stratum in the frozen recorded order — or (b) **extend from the clean pool** (universe − pilot − calibration − current blind), which is legitimately untouched by construction, using the same stratified seeded procedure with the documented continuation seed. Names are never swapped or hand-picked.
- **Blind hygiene in W1:** blind names participate ONLY as anonymous members of cross-sectional rank denominators (§5). No per-name blind row appears in any W1 artifact; the W1 census excludes the blind arm entirely (count of excluded names stated in the census header). Blind episode catalogs are not persisted in W1.
- Seed: `seed_blind = int(sha256(b"stock-identity-blind-arm-v1").hexdigest()[:16], 16)`. Membership list + `blind_sha256` in the partition manifest.

## §4. Sealed calibration partition — **SI-SEALED-CAL-P1** (§9.3, §16.2)

- Drawn AFTER the blind arm, BEFORE any constant is chosen. Pool = universe − pilot − blind. Simple seeded random draw of ⌊30%⌋ of the pool.
- Seed: `seed_cal = int(sha256(b"stock-identity-sealed-calibration-partition-v1").hexdigest()[:16], 16)`.
- **Partition object (the §16.2-consistent reading, registered here):** usable constant-setting material = (i) the drawn names' history, and (ii) pre-FIT/TEST-boundary history of pool names not drawn. Pilot/exemplar and blind names contribute NOTHING to calibration under any clause (§16.2: exemplars are excluded from both calibration and blind evidence). W1's receipts in fact use only component (i) — using less than the permitted material is strictly conservative and recorded.
- **Recent-history guard (stricter than required):** constant-setting receipts read calibration data only through `asof − 126 trading days`, so the §9.2 untouched-holdout window (most recent months) is not even descriptively consumed by constant-setting.
- **FIT/TEST boundary declaration: 2020-01-01.** Precedent checked: PTT's declared split was fit 2014-01→2020-06-30 / test 2020-07-01→ (`research/PERSONALITY_TIMING_TAILORING_HANDOFF_FOR_FABLE.md:104`, DT-R16 era discipline). This program **deviates deliberately, by six months**: PTT's boundary places the 2020-03 COVID cluster on the FIT side, which for an episode-anchored program would let constant-setting consume the single largest tier-1 episode cluster of the modern era. Declaring 2020-01-01 keeps BOTH the 2020-03 and 2022 clusters on the TEST side for later confirmatory reads (cluster placement is the currency of §9.2's own holdout language). The deviation is declared before any constant was computed. Era-law stratum (2010 break, `DNR:LAW-ERA-SPLIT`) remains an independent analysis stratum.
- **Sealing:** the partition is **named** (SI-SEALED-CAL-P1) **and hashed** (`calibration_sha256` over the sorted drawn-name list; plus `partition_procedure_sha256` over this section's text). It may set/freeze constants **exactly once per constant family** (W1: catalog/state/tier/zone constants; PR-3: ruler composite constants — per §14's own sequencing) and is thereafter excluded from confirmatory Q1 grading (§9.2). Constants never change after sealing; any revision voids the affected preregs (§4 law v).
- Hashes → partition manifest `data/stock_identity/partition/partition_manifest_v1.json` AND the PR body.
- **Untouched-holdout floor declaration (§9.2, declared at PR-1):** N = 10 tier-1 episodes across M = 4 distinct calendar months; the holdout window is the later of (a) the most recent 6 months of replayable history or (b) the most recent window satisfying (N, M) — evaluated at PR-5 grading time, never consumed here.

## §5. Fingerprint v0 (frozen enumeration; `fingerprint_spec_hash`)

- Form per §4 of the masterplan: flat, unit-free, per (ticker, epoch), each feature at ≥2 windows, cross-sectionally PIT-percentile-ranked vs the contemporaneous universe at asof, nullable with a coverage mask; `unstable` flag where adjacent windows disagree beyond the declared tolerance (quartile-jump rule).
- **Epoch provisionality:** no detector exists until PR-4 (§14); W1 fingerprints key `(ticker, epoch_0)` where `epoch_0` = listing-to-date, stamped `epoch_detector: none/provisional` in every artifact.
- **Metric block** (the only block any future distance/map may read): F1 trend grammar (Kaufman ER 63/126/252; log-price R² 126/252; %days>50/200DMA 252; new-high cadence 252/756), F2 drawdown grammar (median/P90 peak-to-trough 756; resets/yr ≥15%/≥30%; time-under-water median 756; Ulcer 126/252), F3 recovery velocity (post-trough 63d return in ATR; time-to-50%-retrace median — from the episode catalog, so computed for catalog'd names only, masked elsewhere), F4 mean reversion (AR(1) daily/weekly; variance-ratio k∈{5,20}; MR half-life ≤252d cap; oscillator-extreme dwell 252), F5 volatility (realized vol 21/63/252 level + vol-of-vol; ACF(|r|) 252; NATR regime spread), F7 MA relations (mean ATR-distance to 20/50/200DMA 252; crossing frequency 252; dwell-above shares; 50DMA bounce rate 756), F8 cyclicality (detrended ACF peak in 126-756d band + peak sharpness, window 1260; PTT swing-period stat), F9 factor/idio (β and 1−R² vs the **declared universal factor panel v0 = [UNIV_EW]**, the equal-weight mean daily return of the evaluated universe — on-plane, identical for every name; **no commodity factor in v0**, keeping the §10 miner-emergence test non-tautological), F10 liquidity (dollar-ADV 63/252; turnover proxy; Amihud 252; Corwin-Schultz spread 252).
- **Diagnostic block** (never in any distance/map; census + Q2-baseline use only): sector, industry, cap bucket, primary plane id, listing venue class, F6 gap family where the plane carries `open` (overnight-gap share of variance; gap-fill rate), close-jump event-response stats on the stocks plane, plus any label-like F10 member (cap bucket).
- **F6 law applied (§4 law vi):** `data/stocks` has no `open` (archaeology §6.1) → F6 is structurally unavailable on the primary plane for ~240 curated names and fails the ≥95% availability bar → **excluded from the metric block entirely**; shipped as diagnostic-block features where available.
- Substrate reuse (§14 PR-1 row): `engine/path_personality.py` (`features()`/`feature_series()` and its internal stats), `engine/path_risk_signals.py` (Ulcer/NATR/HVR), `engine/entry_primitives.py` (Amihud, Corwin-Schultz), canon MA math — wrapped, never reimplemented, in `engine/stock_identity/fingerprint.py`.
- All features causal/PIT at their stamp (truncation-invariance tested); no minute data; volume descriptors display-tier only (`KILL-VOLUME-FINGERPRINTS`).
- `fingerprint_spec_hash` = SHA256 over the canonical spec JSON (ordered feature names, windows, block assignment, version) — recorded in constants file, every artifact, and the PR body. → **`0e3457b11f41452e1c3efac3858196f5f42b573d1961b798ea581e1590b33187`** (52 metric-block + 11 diagnostic-block features; spec at `data/stock_identity/fingerprints/fingerprint_spec.json`).
- **Builder-pinned windows, recorded (not a widening of the enumeration).** §5 above names the window for most members; where it names a statistic without one, the window is pinned in the spec JSON — which is what the hash covers — rather than left to the implementation. Pinned this way: F4 AR(1) daily 252 / weekly 756, variance ratio k∈{5,20} at 756, MR half-life 252 (cap 252), oscillator dwell 252; F5 vol-of-vol 252, ACF(|r|) 252, nATR spread 252; F7 crossing frequency 252, dwell-run 252, 50DMA bounce rate 756; F9 β and 1−R² at 252 and 756; F10 turnover proxy 252. **F8's swing-period stat is pinned at BOTH 756 and 1260** so the family carries ≥2 windows (§4's form law) and the pair doubles as a plateau check on cycle length; the F8 ACF-peak members stay at §5's declared 1260.
- **The ">=2 windows" law is read at FAMILY level**, which is the reading under which §5's own enumeration (several single-window members, e.g. time-under-water 756, Amihud 252, Corwin-Schultz 252) is internally consistent with masterplan §4. The reading is recorded in the spec JSON as `window_law_reading` rather than left implicit. F3 is the one family with no window: it is derived from the episode catalog, so it is masked for names with no catalogued episode.
- **F7's "dwell-above shares" is implemented as a mean RUN LENGTH**, not a share, because §5 already carries the share form in F1 (`%days>50/200DMA 252`) and two identical columns under different names would be a fake second measurement.

## §6. State tagger v0 (frozen at PR-1; §7.1)

Eight mutually-exclusive states from daily bars only. Variables: `d200 = close/SMA200 − 1`; `dd = close/max(close, 252d) − 1`; `volp` = percentile of 21d realized vol within the name's own trailing 756d; gap proxy `gap_atr` = |open_t − close_{t−1}|/ATR14 on the baskets plane, |close_t − close_{t−1}|/ATR14 on the (open-less) stocks plane — plane asymmetry recorded on every row; **never an earnings calendar** (§7.1).

Precedence (first match wins; thresholds g, θ_dw, θ_bd, θ_pb, θ_up, vol bands set on SI-SEALED-CAL-P1 and frozen in `si_constants_v1.json`):
1. `post_event_dislocation` — a gap_atr > g day within the trailing E sessions.
2. `deep_washout` — dd ≤ −θ_dw.
3. `breakdown` — d200 ≤ −θ_bd and SMA200 slope ≤ 0.
4. `recovery_reclaim` — d200 ≥ 0 after a deep_washout/breakdown state within the trailing R sessions.
5. `controlled_pullback` — d200 > 0 and −θ_dw < dd ≤ −θ_pb.
6. `structural_uptrend` — d200 ≥ +θ_up and dd > −θ_pb.
7. `vol_transition` — volp band-jump ≥ J percentile points over the trailing V sessions.
8. `range` — residual.
Totality + mutual exclusivity are test-enforced. State is a covariate, not a fit-cell key (§7.1).

## §7. Episode catalog v0 (frozen at PR-1; §7.2) + W1-frozen ruler-zone constants

- **Reset/decline:** leg where price falls ≥ X·ATR AND ≥ Y% from the rolling 126d high; ends at a **durable low** (no lower low for ≥ N sessions AND rebound ≥ k·ATR AND ≥ z%) or truncation (censored, `terminated_reason` where known — LER convention).
- **Reclaim:** first sustained recapture of the 200DMA after a breakdown state; resolution held/failed within M sessions.
- **Failed breakdown:** close below the 60d low that recovers the level within m sessions.
- **Tiers:** tier-1 depth ≥35% with duration ≥ D1 sessions; tier-2 ≥20%, ≥ D2; tier-3 = remaining catalog floor. Depth is context, never a bonus.
- Constants X, Y, N, k, z, M, m, D1, D2 set on SI-SEALED-CAL-P1 via the written per-constant selection rules in `scripts/stock_identity_calibrate.py` (rule declared in code/doc BEFORE the value is computed from partition data), frozen in `si_constants_v1.json`, spec-hashed. Sensitivity grid (±20%, diagnostic-only) registered in the TrialLedger BEFORE running (G-7) and never used to re-pick.
- **W1 also freezes (per §7.3's "frozen at PR-1" clauses, values from the same partition):** useful-zone `w` (sessions) and `δ` (×A0), false-start `θ` (×A0), and the fire→episode **attribution window** (a fire attributes to episode E if its known_ts ∈ [leg_start − P_pre, resolution]; P_pre frozen). No fire data exists in W1; these constants freeze geometry only, ahead of PR-2/PR-3 use. A0 basis = Wilder ATR(14) at prior confirmed close (`atr_basis` recorded).
- Resolution labels use future data by design — research-time labeling instrument only (§7.2); no live surface ships them; nothing here is a signal.

## §8. Coverage census v0 (§8.2 start) + calendar clusters

- Scope: universe **minus blind arm** (blind excluded from any published census until PR-3; excluded-name count stated). Pilot rows at full detail.
- Columns per (ticker × episode_type × tier): n_episodes, n_censored, first/last anchor, **distinct calendar clusters** — v0 cluster rule (frozen): pooled cross-name anchor dates, single-linkage connected components under "anchors within 126 sessions"; global cluster ids; the P90-episode-duration-linkage refinement is a named PR-3 candidate, not silently swapped — plus share of episodes in the 3 largest clusters, and feature-availability × plane cross-tabs.
- Fires-per-name-year / attribution-rate columns are PR-2/PR-3 additions (no expert data exists in W1 by law).

## §9. Pilot data gates (§13 / §14 PR-1 row) — results

**Pilot cohort as built (n = 21).** Episode counts are at the frozen constants; hygiene flags resolve below the table.

| name | role | plane | first | last | rows | `open` | hygiene flags | first-print sanity | episodes |
|---|---|---|---|---|---:|:--:|---|---|---:|
| **AEM** | miner neighborhood probe | `baskets_ohlcv_v1` | 2014-01-02 | 2026-08-13 | 3172 | Y | — | `PREDATES_CALENDAR` | 49 |
| **AG** | miner neighborhood probe | `baskets_ohlcv_v1` | 2014-01-02 | 2026-08-13 | 3172 | Y | — | `PREDATES_CALENDAR` | 65 |
| **BABA** | operator core | `stock_identity_ohlcv_v1` | 2014-09-19 | 2026-08-13 | 2992 | Y | — | `PREDATES_CALENDAR` | 49 |
| **CBRS** | stressor — recent IPO (rule-chosen at PR-1) | `baskets_ohlcv_v1` | 2026-05-14 | 2026-08-13 | 63 | Y | — | `OK` | 0 |
| **FFAI** | stressor — secular decliner (rule-chosen at PR-1, damaged cohort) | `baskets_ohlcv_v1` | 2020-09-02 | 2026-07-21 | 1476 | Y | — | `PREDATES_CALENDAR` | 23 |
| **GOLD** | miner neighborhood probe | `baskets_ohlcv_v1` | 2014-03-17 | 2026-08-13 | 3122 | Y | `symbol_history_note` | `PREDATES_CALENDAR` | 59 |
| **HL** | disagreement set | `baskets_ohlcv_v1` | 2014-01-02 | 2026-08-13 | 3172 | Y | — | `PREDATES_CALENDAR` | 61 |
| **KO** | operator core | `stocks_tr_v1` | 1962-01-02 | 2026-08-13 | 16262 | N | — | `PREDATES_CALENDAR` | 208 |
| **KRUS** | operator core | `baskets_ohlcv_v1` | 2019-08-01 | 2026-08-13 | 1768 | Y | — | `PREDATES_CALENDAR` | 33 |
| **MCD** | operator core | `stocks_tr_v1` | 1966-07-05 | 2026-08-13 | 15127 | N | — | `PREDATES_CALENDAR` | 192 |
| **MCK** | operator core | `stocks_tr_v1` | 1994-11-10 | 2026-08-13 | 7991 | N | — | `PREDATES_CALENDAR` | 105 |
| **META** | stressor — known epoch-changer | `stocks_tr_v1` | 2012-05-18 | 2026-08-13 | 3579 | N | — | `PREDATES_CALENDAR` | 55 |
| **MSFT** | stressor — steady-trender control | `stocks_tr_v1` | 1986-03-13 | 2026-08-13 | 10183 | N | — | `PREDATES_CALENDAR` | 143 |
| **NEM** | miner neighborhood probe + disagreement set | `stocks_tr_v1` | 1980-03-17 | 2026-08-13 | 11697 | N | — | `PREDATES_CALENDAR` | 238 |
| **NVDA** | operator core | `stocks_tr_v1` | 1999-01-22 | 2026-08-13 | 6932 | N | — | `PREDATES_CALENDAR` | 112 |
| **PAAS** | miner neighborhood probe | `baskets_ohlcv_v1` | 2014-01-02 | 2026-08-13 | 3172 | Y | — | `PREDATES_CALENDAR` | 68 |
| **REGN** | operator core | `stocks_tr_v1` | 1991-04-02 | 2026-08-13 | 8906 | N | — | `PREDATES_CALENDAR` | 183 |
| **UEC** | disagreement set | `baskets_ohlcv_v1` | 2014-01-02 | 2026-08-13 | 3172 | Y | — | `PREDATES_CALENDAR` | 56 |
| **WMT** | operator core | `stocks_tr_v1` | 1972-08-25 | 2026-08-13 | 13603 | N | — | `PREDATES_CALENDAR` | 180 |
| **WPM** | miner neighborhood probe | `stock_identity_ohlcv_v1` | 2005-07-06 | 2026-08-13 | 5310 | Y | — | `PREDATES_CALENDAR` | 93 |
| **YELP** | operator core | `baskets_ohlcv_v1` | 2014-01-02 | 2026-08-13 | 3172 | Y | — | `PREDATES_CALENDAR` | 52 |

**Hygiene resolutions.** Only one pilot name carries a flag. **GOLD → `symbol_history_note` (informational, not blocking):** `GOLD.parquet` is Barrick's continuous history under its *current* symbol — the pre-2018 rows are the ABX era restated, i.e. instrument-level continuity via rename, not a splice, so it is legitimate to read. A **separate** `data/baskets/ohlcv/ABX.parquet` (2020-09-14 →, 1,486 rows) exists in the universe and is a **different instrument on Barrick's retired symbol**; that reuse appears in **none** of `quality.reused_ticker_acks`, `quality.ticker_key_migrations`, or `breadth.ticker_fixups`, so it is **unacknowledged in config** — a W1 discovery, flagged upstream for the config owners, and ABX is excluded from every computation this program performs (it still appears in the universe snapshot: censored-never-dropped). No other pilot name matched a reused-ticker, rename, fixup, or delisting record.

**First-print sanity.** CBRS is the only pilot name inside the Nasdaq deal calendar's coverage (earliest priced date 2024-12-03) and it verifies `OK` at 0 days. The other 20 return `PREDATES_CALENDAR` — an out-of-range reading, **not** a pass and **not** a failure; the deal reference simply does not reach back to a 1962 or 2014 first print.

**Plane split.** 10 names on `stocks_tr_v1` (no `open` → close-to-close gap basis), 9 on `baskets_ohlcv_v1`, 2 (BABA, WPM) on the program-owned `stock_identity_ohlcv_v1`. Both open-carrying planes use the overnight gap basis; the asymmetry is recorded on every state row.

Gate verdicts established at W1 adjudication (main-loop probe, 2026-08-14), all confirmed by the build:
- **BABA / AEM / PAAS / WPM / AG deep TR-adjusted presence** (archaeology §6.2 left unverified): **BABA ABSENT from both planes; WPM ABSENT from both planes** → the §13-permitted collection step runs for exactly these two (into the program-owned store, §11). **AEM, PAAS, AG present** on the baskets plane (2014-01-02 → asof, ~3,170 rows each, `open` available) — present, so no collection per the contract's "if absent" clause; the baskets plane's 2014 inception bounds miner history and is recorded in the census (a PR-2+ deepening decision if the miner-emergence test needs the 2011-2015 gold bear, named here, not silently done).
- **Archaeology correction (recorded):** GOLD sits on the **baskets plane only** (2014-03-17→asof), not in `data/stocks` as archaeology §6.2 stated; NEM is in `data/stocks` (1980→). The archaeology's as-of predates this checkout; the census carries the corrected fact.
- **KRUS depth check: PASSES** — full IPO-era history on the baskets plane (2019-08-01 → asof, 1,768 rows, `open` available).
- **Earnings backfill build-or-defer (§14 PR-1 row): DEFER.** Grounds: F6 is excluded from the metric block by the plane law regardless of any backfill; the state tagger is bars-only by §7.1's own design (review finding 9); earnings-anchored features are diagnostic-block-only in v0. Revisit trigger: PR-4 epoch-detector face-validity or PR-5 diagnostic needs; the deep-OHLC collection template + `data/earnings/earnings.parquet` (forward + ~4 trailing quarters) remain the substrate for a later off-path backfill. No backfill is built in W1.

## §10. Metadata sources (stratification + diagnostic block)

Resolved at W1 adjudication (the stock library's `site/stockdata/` output is a generated, untracked artifact — unavailable to a clean checkout — and `scripts/build_stock_library.py` is G-8-protected, neither modified nor executed):
- **Sector stratum:** GICS-style sector from `data/breadth/ticker_sectors.parquet` (1,515 names; `ticker, sector, source ∈ {gics_sp500, gics_sp400, gics_sp600, sic_mapped}`; display-tier, built by the non-protected `scripts/build_sector_map.py`); names outside it land in the `UNKNOWN` sector stratum — never dropped. (`data/breadth/constituents.parquet` at 503 names was the first candidate; superseded by the wider map at W1 adjudication.)
- **Cap stratum:** no per-name market-cap store is tracked → **cap proxied by trailing-252d dollar-ADV tercile** (computed on-plane; the §4 F10 house proxy), documented as a proxy on every stratified artifact.
- **Vol stratum:** trailing-252d realized-vol tercile at asof, on-plane.
- **Diagnostic-only:** basket membership (`data/baskets/membership.json`, PIT windows via `data/baskets/membership_history.parquet` / `engine/basket_index.py`); S&P1500 PIT membership (`data/breadth/sp1500_pit_membership.parquet`: ticker/start/end/src) — survivorship stratification substrate; finviz screener caps (`data/finviz_screener/idx_ndx.json` + `idx_rut.json`, `market_cap_b` — mixed coverage, recorded where present, never a stratifier); none of these is ever a fingerprint metric-block input (G-1).
- **First-print sanity source (§9.6):** `data/ipo/calendar.parquet` (Nasdaq deal-reference table); names predating its coverage are recorded as "predates calendar coverage", not failed.

## §11. Storage + compute law applied (§16.3)

- In-repo (small): partition manifest + universe snapshot, `si_constants_v1.json`, pilot fingerprints, pilot episode catalog + per-name episode JSONs, census artifact, dossiers (md + svg), this registration.
- NOT in-repo: any large full-universe matrix. The universe cross-section used for percentile ranks is computed in-session (store-host pattern, off every render path) and only the pilot rows + aggregate rank context are persisted; if any artifact exceeds ~20 MB it ships to R2 via `scripts/publish_r2.py` with a small committed manifest.
- The §9-gated collection (BABA, WPM) follows the house one-off backfill pattern (deep, adjusted, provenance-stamped — the CN/HK deep-OHLC template's essence): `yfinance` `period='max', auto_adjust=True` (the curated plane's own adjustment convention, archaeology §6.1), full OHLCV **including `open`**, landing in `data/stock_identity/ohlcv/<SYM>.parquet` (program-owned store, `price_plane_id = stock_identity_ohlcv_v1`) with a committed provenance manifest (fetch ts, source, adjustment mode, rows, first/last date) — recorded on every downstream row per §4 law vi; flagged in the PR body for operator review. No writes into `data/stocks/` or `data/baskets/` (those planes belong to their own machinery).
- Nothing enters `site/`; no render-lane coupling; heavy compute stays in this session (Mac-Studio store host), never in `daily.yml`/`render.yml`/`engine-render.yml`.

## §12. Registered look budget (G-7)

The calibration sensitivity grid and any exploratory sweep register BEFORE running, labeled exploratory/diagnostic; no confirmatory question is registered or graded in W1 (Q1's prereg is a PR-5 act on the §8.5 power gate).

**Registered (the only W1 look-budget entry):**

| field | value |
|---|---|
| family | `stock_identity_w1_calibration` |
| ledger | `data/trial_ledger.jsonl` (the shared house ledger) |
| registration mechanism | `@register_trials(family, budget=13, basis="itemized", reason=…)` on `scripts/stock_identity_calibrate.py::main`, plus `TrialLedger.log_grid` of the itemized configs |
| declared budget | 13 = 1 base + 2 directions × 6 perturbed constants |
| grid sha256 | `ba2b29b445c50c674775c8c0a24a319dbb4e033dd8fb8a402cef553471353c32` |
| effective_n | 13 |
| perturbed constants | X, N, k, z, θ_dw, g at ±20% |
| label | exploratory / diagnostic — **never used to re-pick a value** |
| info_cutoff stamped | 2026-02-11 (the calibration history cutoff) |

The registration is **idempotent**: a re-run of the calibrator logs 0 newly-distinct configs (dedup by content hash), so re-deriving the same constants from the same sealed partition does not inflate the budget. The grid sha256 and `effective_n` are copied into `si_constants_v1.json` under `sensitivity_grid`.

**Sensitivity result (diagnostic).** Over a seeded 40-name calibration subsample: episode counts move −59 to +26 against a 1,920-episode base (worst case ~3%), and the largest state-share shift is 0.061 (θ_dw −20%). X and θ_dw carry essentially all of the sensitivity; k and z move nothing at these values, because at k = 0.5·A0 and z = 3% the durable-low gate is dominated by the N-session survival requirement rather than by the rebound size. This is a plateau, not a needle — reported, and not acted on.

## §13. W1 exclusion self-audit (§16.9 mechanical)

- No artifact schema in `data/stock_identity/**` contains any expert identifier, fit metric, ranking, or "best" field; a repo test (`tests/test_stock_identity_atlas.py`) greps the artifact tree and the engine package for the banned tokens (`best_expert`, `fit_score`, `expert_rank`, per-expert columns) and asserts the authority block is all-false in every JSON artifact.
- `engine/stock_identity/**` imports none of the G-8 protected modules (test-enforced).
- `git diff --stat` on the G-8 paths printed clean in the PR body.

## §14. Hashes (PR-body copies)

| hash | value |
|---|---|
| `universe_sha256` | `841ed5461c159c2c9964da1f3b2ce99edb3176b037fc8d07d7c03d0e13f8c659` |
| `blind_sha256` | `88e2b0d86eaa2e031841de28a10bdae4f4c798395dd1726f39e3feb3773291bd` |
| `calibration_sha256` | `77e111c11672524c826948455a8c2ea5b812cdddb3f0d9dac1807b253604e9d0` |
| `partition_procedure_sha256` | `a546c64983431f0afca01cfd9aacc230ef3bed875520c44898090520cf98164a` |
| `fingerprint_spec_hash` | `0e3457b11f41452e1c3efac3858196f5f42b573d1961b798ea581e1590b33187` |
| `si_constants_spec_hash` | `9c27994aa757a39ae3e2e7b2ec781ff94365581d60e827354662a8347a761d03` |

**asof = 2026-08-13** (the last trading date common to all three planes). Universe 2,781 names · pilot 21 · blind arm 229 across 87 non-empty strata (94 strata total; 1,573 names in the `UNKNOWN` sector stratum) · sealed calibration partition **SI-SEALED-CAL-P1** 759 names drawn from a 2,531-name pool, 758 readable (ABX skipped on hygiene, see §9), calibration history cutoff **2026-02-11**.

Every hash above is reproducible from the committed universe snapshot plus the three verbatim seed strings — `tests/test_stock_identity_partition.py` re-runs both draws and demands identical member lists **and** identical hashes, and re-derives `universe_sha256` and `partition_procedure_sha256` from their sources. `si_constants_spec_hash` covers the frozen decisions (version, values, rule text) and deliberately **not** the receipts, whose sample counts would otherwise move the hash without any constant moving.

---

## Amendment A1 — GOLD wrong-issuer disclosure and B miner-probe addendum

**Amendment id:** `SI-W1-A1-GOLD-WRONG-ISSUER`
**Registered:** 2026-08-14, before the only artifact-producing A1 run. The read-only
implementation exposure in A1.0 happened before this text was committed and is disclosed
in full; this amendment does not pretend otherwise.
**Authority:** descriptive only; the standing all-false authority block remains binding.
**Prerequisite gate:** the pinned source heads identify the reviewed PR tips. Because
both prerequisites were squash-merged, those source heads are not asserted to be
ancestors of `main`. PR #5613 reviewed source head
`b8601a0dc318c20ebf0b3ace198c9b3b1a735624` landed as squash commit
`666a2efd7aa69881b7d56e2712cc283638ef7b98`; PR #5632 reviewed source head
`e93ad5343606bda152fd00902f2a6651acffa5d5` landed as squash commit
`6d04e9b3100af7afaf834ceb2c9c307a48808f0b`. The builder verifies those exact
GitHub PR source-head/merge pairs and requires only the squash commits to be ancestors
of `origin/main`. A PR body, label, merge ref, or green intention is not a merge receipt.

`initial_registration_commit=adb6ae2ed744e2f76574cb89b0e106ea402e576a`
identifies the first post-rebase committed A1 registration. The result receipt separately
records as `registration_commit` the clean, pushed A1 PR head that authorizes the
artifact-producing run; that runtime head is intentionally not self-hashed in its source.
The governing review object is draft PR #5660 in
`mastermindx-market-intelligence/macro`, base `main`, head
`codex/stock-identity-gold-w1-amendment-20260814`. Before reading B for the registered
run, the builder requires GitHub to report that exact open draft PR and requires its
live `headRefOid` to equal the clean pushed local `HEAD`; the receipt preserves that
PR context and head OID.

### A1.0 Procedural-deviation ledger — pre-registration implementation exposure

The A1 remedy, source plane, roster overlay, output allowlist, frozen-reference method,
and no-blocklist ruling below were fixed from the registration/masterplan audit **before**
this exposure. During a delegated API-signature audit, an implementation agent went beyond
the assigned read-only source inspection and exercised the frozen W1 functions on the
proposed B input in memory. No repository file was written; independent parent-agent proof
immediately afterward was a clean `git status --short` and empty `git diff --stat` in the
task worktree. One failed chart attempt created at most an empty operating-system temporary
directory and stopped at `ModuleNotFoundError: matplotlib` before rendering.

The exact exposure was:

1. The PR #5632 B parquet was streamed from git and inspected: 3,172 OHLCV rows,
   2014-01-02 through 2026-08-13, with `open/high/low/close/volume`. The first two and
   last two prints were displayed.
2. The committed W1 constants plus frozen `UNIV_EW` checkpoint were used in memory with
   `state.tag_states`, `episodes.build_catalog`, `episodes.catalog_f3_stats`,
   `fingerprint.compute_raw`, `fingerprint.cross_sectional_percentiles`, and
   `fingerprint.unstable_flags`. The console exposed 3,172 state rows, 66 catalog rows,
   the state/type/resolution counts, both F3 summaries, 57 non-null percentile fields,
   two instability flags, and sample raw/percentile pairs for F1/F2/F3/F5/F9/F10/F6.
3. A previously existing, unmerged W2 branch's **different** program-plane B dossier was
   read. It used the prohibited duplicate 1985-start plane and is walled off completely.

This is a preregistration procedural deviation, not clean-room evidence. Its consequence is
binding: B is permanently design-touched, excluded from the blind arm, sealed calibration
partition, every future blind extension, and every confirmatory grade. No observed count,
metric, percentile, instability flag, chart size, or W2 value may choose an A1 output,
threshold, constant, acceptance rule, or interpretation. There is no success criterion for
the descriptive B row. The artifact-producing run below remains single-shot and registered;
the result receipt repeats this deviation and records the registration commit.

### A1.1 Verified identity discovery

- NYSE `GOLD` has been **Gold.com, Inc.**, fka A-Mark Precious Metals, since
  2025-12-02 (EDGAR CIK **1591588**). Every US store under that key is A-Mark/Gold.com's
  continuous dealer tape from 2014-03-17; it contains no Barrick rows.
- **Barrick Mining Corporation** trades as NYSE `B` since 2025-05-09 (EDGAR CIK
  **756894**). PR #5632 supplies the permitted curated
  `data/baskets/ohlcv/B.parquet` tape.
- Therefore W1's sealed `GOLD` measurements are measurements of a bullion dealer. The
  measurements remain valid for that instrument; the role and miner-neighborhood
  interpretation are wrong. Symbol lineage did not establish tape identity.

### A1.2 Remedy and cohort semantics

The lawful remedy is **(a) plus (b), not (c)**:

- Preserve the sealed historical W1 miner recipe exactly as
  `NEM GOLD AEM PAAS WPM AG`. PR #5612 remains the historical W1 receipt.
- Add a conspicuous, reversible post-seal annotation to `GOLD.md`. Every byte outside
  the marked annotation stays unchanged; `GOLD.svg`, GOLD's episode JSON, all combined
  pilot parquets, the census, universe snapshot, partition manifest, and constants stay
  byte-identical. The frozen false role/hygiene rows remain visible as superseded
  historical output, never current fact.
- Overlay the **effective analytical miner probe** as
  `NEM AEM PAAS WPM AG B`. This is an append-only amendment, not a retroactive pilot
  substitution and not a partition redraw.
- B is design-touched and permanently ineligible for blind/calibration/confirmatory
  evidence. B is absent from the frozen W1 universe snapshot, pilot manifest, blind arm,
  and `SI-SEALED-CAL-P1`; A1 does not insert it into any of them.
- Do **not** add GOLD to `COMPUTE_BLOCKLIST`. Its dealer tape is readable and continuous;
  the defect is the frozen miner role. An acknowledged reused symbol is blind-ineligible,
  but that is not a reason to mislabel a valid tape `reused_ticker_unacked` or to suppress
  its instrument-level descriptive history.

### A1.3 Frozen inputs and ranking context

The only permitted A1 price input is `data/baskets/ohlcv/B.parquet`,
`price_plane_id=baskets_ohlcv_v1`, truncated at the frozen W1 asof
**2026-08-13**. PR #5632 seeded its parquet container at SHA256
`dc126c36c6fa07b37ca212051d2a194758725330bfed9c5b6112701b12be6b5f`; that is a
historical seed receipt, not a durable equality pin, because normal membership
collection advances the curated file. The governing input is the normalized 3,172-row
OHLCV prefix from 2014-01-02 through 2026-08-13, whose versioned logical digest is
`6d8988fc8ec3990d3a5c2a6d5f4bb31d94b3ab46ac49978d21fb3770482ae8db`. The digest serializes an algorithm-version header, the fixed
`Date/open/high/low/close/volume` schema, each ISO date, and each normalized float64
value via Python's exact hexadecimal representation. ~~Post-asof appends may not move it;
any historical revision must.~~ (superseded 2026-08-18 — see A1.3a.) A program-owned B
plane and the close-only Yahoo B file are prohibited.

#### A1.3a Frozen prefix snapshot and the live-plane revision tripwire (2026-08-18)

**The struck sentence above is architecturally false for this file, and the digest was
enforced against the live plane on that false premise.** Post-asof appends are not the
only nightly mutation: `scripts/fetch_basket_ohlcv.py` re-downloads the **full**
auto-adjusted history every collection night (`yf.download(start=2014-01-01,
auto_adjust=True)`) and lets the new vendor frame win the merge, so the already-elapsed
2014-01-02..asof prefix is re-derived — and re-rounded — every night. Measured on
2026-08-18, two collection commits **21 minutes apart** moved 2,214 then 2,341 of the
3,172 prefix rows and produced two different digests (`2f4d9467…`, `a77fdc41…`). An
exact-equality digest over the live plane therefore reds the whole fleet on every
collection night by construction; that is what happened from 04:02Z on 2026-08-18.

The registered digest is **not restamped** — restamping would only re-red the next
night. Instead the prefix the A1 result was actually computed from is frozen as an
immutable, program-owned snapshot, and the digest now anchors to it:

| path | SHA256 | logical prefix digest |
|---|---|---|
| `data/stock_identity/sources/w1a1_b_ohlcv_prefix_v0.parquet` | `ba200fe4eb0b881eec4f7a2962c949dea4450d0ffbc1713ab465f440b008d878` | `6d8988fc8ec3990d3a5c2a6d5f4bb31d94b3ab46ac49978d21fb3770482ae8db` (unchanged) |

The snapshot is the #5632 seed container (commit `6d04e9b3`, container SHA256
`dc126c36…`) under the `plane.load_symbol` normalization, truncated at the asof; it
reproduces the registered digest exactly, so every sealed A1 receipt naming
`6d8988fc…` — including `data/stock_identity/episodes/amendments/B.json` and
`data/stock_identity/amendments/w1a1_gold_wrong_issuer.json` — remains true
byte-for-byte and was not edited. Reproduce with:

```
git show 6d04e9b3:data/baskets/ohlcv/B.parquet
```

normalized by `engine.stock_identity.plane.load_symbol` and truncated at 2026-08-13.

A1 math now reads the snapshot rather than the live plane, which also restores a
property the drift had quietly broken: a sealed result whose inputs move nightly cannot
reproduce its own sealed outputs.

**The live curated plane is still checked — by a revision tripwire rather than by
equality.** The distinction it draws is measured, not assumed. Seed→live over the
3,172-row prefix:

- `open/high/low/close` move by a **single per-row multiplicative factor**, coherent
  across the four columns to `4.4e-16` (machine epsilon) — the signature of adjustment
  arithmetic, not of a restated print.
- normalized by the window-wide median factor, that per-row factor stays within
  `8.63e-07` of uniform (worst row 2014; `8.8e-08` by 2026) and does **not**
  accumulate — seed→mid and mid→live were each ~`8.5e-07`, seed→live `8.63e-07`.
- `volume` is byte-identical on all 3,171 settled rows across three collections
  spanning four days. Only the asof row itself moved (10,621,100 → 10,625,700,
  `4.33e-04`): the final session's consolidated tape was still settling when the seed
  was cut.

**The band is on the UNIFORMITY of the rescale, not on its level — and that choice is
load-bearing.** `auto_adjust=True` rescales the entire elapsed history on every future
dividend: a routine ~$0.10 Barrick quarterly on a ~$41 tape is a `~2.4e-3` coherent
shift, ~240× any plausible noise band. A tripwire banding the *level* would therefore
fire on the next ordinary dividend and re-red the fleet within weeks — reproducing, on
a slower clock, the exact defect this section repairs. It would also be measuring the
wrong thing: a uniform rescale leaves every return, drawdown and percentage gap
identical, so it cannot move an A1 conclusion. What can is a change in **relative**
prices. Splits remain covered because split adjustment rescales share counts as well,
and settled volume must match exactly.

Enforced checks (`scripts/stock_identity_build_w1a1.py`):

| check | band | worst observed | fires on |
|---|---|---|---|
| O/H/L/C per-row factor coherence | `1e-12` | `4.4e-16` | a single restated print, however small |
| per-row factor residual vs window median | `1e-5` | `8.63e-07` | any change in relative prices |
| gross window rescale (sanity only) | `[0.2, 5.0]` | `1.000000` | a broken vendor frame |
| settled-session volume | exact | 0 rows | splits; any vendor volume restatement |
| asof-session volume | `1e-2` | `4.33e-04` | more than late tape consolidation |

The residual band sits ~11× above measured re-adjustment noise while remaining blind to
return-preserving rescales of any size, which are recorded in the receipt as
`gross_window_rescale` rather than treated as revisions. `tests/test_stock_identity_atlas.py`
proves both directions: re-adjustment noise, a routine quarterly dividend and a deep
0.85× re-adjustment all pass, while a 2:1 split, a single-print restatement, a segment
restatement, a settled-volume restatement, an asof-volume blowout, a dropped session
and a broken vendor frame each fire.

Existing committed W1 artifacts are pinned before and after the run:

| path | SHA256 |
|---|---|
| `data/stock_identity/partition/partition_manifest_v1.json` | `b1f82f842350e39ac7a73214fd8ebd58b175b52fdf42b3a0fb5a2d03143a5d48` |
| `data/stock_identity/partition/universe_snapshot_v1.parquet` | `9f22807e7cb6ba570f1963de945b7be77461a1788608754e25db6235f4fe3730` |
| `data/stock_identity/constants/si_constants_v1.json` | `276d4ad267ab8711942943e306e844bfdff1f17a051bd17a9d460c1e428fc648` |
| `data/stock_identity/fingerprints/fingerprint_spec.json` | `bbefcd5b72915435acb8714d7892b79e010cb49d394b3222d89575c7b022dee0` |
| `data/stock_identity/fingerprints/pilot_fingerprint_v0.parquet` | `2bdef8763b0c73a6df3f27e8307246887b7b9dc982f66331ba4d96ff09d72ba3` |
| `data/stock_identity/state/pilot_state_daily.parquet` | `e2c43f8761431c62506311e61fa387c70433f82bde8143b564fdf87da7ee485e` |
| `data/stock_identity/episodes/pilot_episode_catalog_v0.parquet` | `3216f6cbbf539584dba31caf30e09b6e76e0297ca34698fcb0235cf6e0d6bc0f` |
| `data/stock_identity/episodes/pilot/GOLD.json` | `be8a1d053c6fc9f639017abb4cf7f3063e7bde8229d9a1622dedd38a02ff16d1` |
| `data/stock_identity/census/coverage_census_v0.parquet` | `d64d37c0ab8e0729aa732f2a68a183dd08e0ca3336e9a4a71975772f28c0b4cd` |
| `data/stock_identity/census/coverage_census_v0.md` | `cf1a818749802bf6143656cfc06efa8ad95d3e87570a011726766c461bf371bb` |
| `research/stock_identity/dossiers/GOLD.md` (before annotation) | `2675b5be60cc09a37324e697bb62c20679b8f21cfe4d268f5082ce0730861558` |
| `research/stock_identity/dossiers/GOLD.svg` | `e4e6466f2b4535b97d2fae4eb3eb7e39c1a40600343d955f0e0fe843d7df49db` |

The universe-scale raw matrix remains a store-host checkpoint, never a new committed W1
artifact. A1 requires an explicit checkpoint directory and pins:

- `raw_all.parquet`: SHA256
  `ca9c5e5ac78c9a1913a145f8763a2bea84cd80a4a10d6fd2f4d095377f021a08`,
  2,780 unique computed-name rows, GOLD present, B absent.
- `univ_ew.parquet`: SHA256
  `80f5ab3c80aa44da26e17ca58d8a14db930e5d3c03e45031c4c9505c3edba70a`.
- `strata.parquet`: SHA256
  `67ae54370dfd2279583f99a16475865796542b786cd983a1e94da27edb33f769`,
  GOLD present, B absent.

B's percentile fields are a **B-only hypothetical insertion** into the frozen 2,780-row
raw reference, using pandas average-tie empirical ranks and per-field non-null
denominators. Only B's row is persisted. No W1 percentile is recomputed or rewritten.
F9 reuses the frozen `UNIV_EW` series byte-for-byte. That factor and the reference ranks
include the GOLD dealer as one small universe component; A1 preserves that context for
comparability and explicitly forbids interpreting it as miner evidence.

### A1.4 Registered outputs and run law

The additive output allowlist is exact:

- `data/stock_identity/amendments/w1a1_gold_wrong_issuer.json`
- `data/stock_identity/fingerprints/amendments/w1a1_b_fingerprint_v0.parquet`
- `data/stock_identity/state/amendments/w1a1_b_state_daily.parquet`
- `data/stock_identity/episodes/amendments/w1a1_b_episode_catalog_v0.parquet`
- `data/stock_identity/episodes/amendments/B.json`
- `research/stock_identity/dossiers/B.md`
- `research/stock_identity/dossiers/B.svg`

The only existing path A1 may change is
`research/stock_identity/dossiers/GOLD.md`, and only by inserting the registered marker
envelope after the standing authority paragraph. Removing that envelope must reconstruct
the pinned original hash. `B.svg` must carry a visible 2014-01-02 curated-tape-floor
watermark; if the renderer cannot produce the registered SVG within the existing size
limit, the run fails without publishing rather than silently choosing another format.

The builder validates all gates without writing under `--validate-only`, computes once
into an operating-system temporary directory, validates schemas and all-false authority,
rechecks frozen hashes, then publishes only the allowlist and the annotation. The governing
JSON receipt is written last and records the pushed registration commit, prerequisite merge
commits, input/output hashes, original/effective rosters, the procedural deviation,
`measured_rows_mutated: false`, and `authority` all false.

No TrialLedger registration is required: A1 has one deterministic descriptive
configuration, no parameter sweep, no outcome attachment, no graded question, and no
choice among results. The pre-registration exposure does not create a look-selection
right; its observations are quarantined as stated in A1.0.

The B dossier must watermark the curated history floor: 2014-01-02 is not Barrick's issuer
or listing birth, and this tape cannot cover the pre-2014 portion of the 2011-2015 gold bear.

### A1.5 Post-registration execution log

The first registered builder invocation ran at pushed draft-PR head
`f25f53dd02c65f01d2d007edafede2acd26fb582` after every preflight passed. It computed
only inside the operating-system staging directory, then stopped before publication
with `B dossier Identity boundary is ambiguous`: the implementation matched the prefix
`## Identity`, which also matched the later `## Identity-episode catalog` heading. No B
metric or count was printed, no registered output existed afterward, `git status --short`
was clean, and the pinned GOLD markdown/SVG hashes remained exact. The retry changes only
that syntactic insertion boundary to the complete `## Identity\n` heading. It changes no
source, cohort, constant, rank method, output path, acceptance rule, or interpretation;
this log is committed and pushed before the retry.

That retry ran at pushed draft-PR head
`2bcf6c988ce1e97625233e973254431b25ed5804` and stopped at the second, independent
insertion guard: `GOLD.md standing authority/Identity boundary is ambiguous`. The GOLD
annotator used the same incomplete heading prefix and therefore also saw
`## Identity-episode catalog`. Again no registered output existed afterward, the
worktree was clean, both pinned GOLD hashes were exact, and no B metric or count was
printed. The next retry applies the already-registered complete-heading rule to both
inserters and adds a direct reversible GOLD-annotation regression before execution;
no analytical or publication choice changes.
