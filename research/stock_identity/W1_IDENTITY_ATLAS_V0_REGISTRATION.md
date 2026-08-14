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
  - **Recent IPO** (chosen at PR-1 by rule): the baskets-plane name with the most recent first_date having ≥60 and <252 sessions and no hygiene flags. → `TODO-BUILDER: name + receipt`.
  - **Secular decliner beyond YELP** (chosen at PR-1 by rule): among ceased-tape names (§13-dead-pool below) with ≥1,000 sessions, the one with the deepest close-to-close max drawdown over its final 1,260 sessions (damaged-cohort rule; membership choice is design-touched and never evidence). → `TODO-BUILDER: name + receipt`.
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
- `fingerprint_spec_hash` = SHA256 over the canonical spec JSON (ordered feature names, windows, block assignment, version) — recorded in constants file, every artifact, and the PR body. → `TODO-BUILDER: hash`.

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

→ `TODO-BUILDER: fill per-name table` — for each pilot name: primary plane, first/last date, n_rows, `open` availability, hygiene flags + resolutions, first-print sanity result. Gate verdicts established at W1 adjudication (main-loop probe, 2026-08-14):
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

→ `TODO-BUILDER: TrialLedger registration ids` — the calibration sensitivity grid and any exploratory sweep register BEFORE running, labeled exploratory/diagnostic; no confirmatory question is registered or graded in W1 (Q1's prereg is a PR-5 act on the §8.5 power gate).

## §13. W1 exclusion self-audit (§16.9 mechanical)

- No artifact schema in `data/stock_identity/**` contains any expert identifier, fit metric, ranking, or "best" field; a repo test (`tests/test_stock_identity_atlas.py`) greps the artifact tree and the engine package for the banned tokens (`best_expert`, `fit_score`, `expert_rank`, per-expert columns) and asserts the authority block is all-false in every JSON artifact.
- `engine/stock_identity/**` imports none of the G-8 protected modules (test-enforced).
- `git diff --stat` on the G-8 paths printed clean in the PR body.

## §14. Hashes (PR-body copies)

→ `TODO-BUILDER: universe_sha256, blind_sha256, calibration_sha256, partition_procedure_sha256, fingerprint_spec_hash, si_constants_spec_hash`.
