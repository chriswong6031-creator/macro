# Mastermind Data OS — architecture

Status: PROPOSED architecture. Nothing in §§1–11 is shipped except where a subsystem is
named as already existing (see §12).
Authority: `context_only` — data/universe infrastructure. Nothing here ranks, gates, sizes,
or escalates. Promotion of any derived quantity still runs the gauntlet.
Scope: Macro Dashboard (`engine/`, `collectors/`, `scripts/`, `lib/`, `data/`), with the
declared cross-repo boundary to `charting-app` (Terminal) and `Mastermind` (bot).
Pinned decisions: `DESIGN_SPEC.md` D0–D12 (session scratchpad). This document implements
them; §0.2 records the four places census evidence forced a correction.
Companion docs: implementation plan, identity spec, temporal spec, price spec, contract
spec, quality/lineage spec (same wave).

**Verification convention.** `VERIFIED(here)` = a command was run against this worktree
(`/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/mastermind-data-os-arch-070441`,
HEAD `ff88ab548a9`) while writing this document, and the command is given.
`VERIFIED(census)` = a census lane or the adversarial verifier ran it, cited to the file
and line it opened. `INFERRED` = reasoned from cited facts, not measured. Standing
adjudications are cited by key (`DNR:KILL-…`), never by row number.

**One evidence caveat that bounds this whole document.** Every claim about the *contents*
of `data/` was measured against the materialized checkout at
`/Users/chriswong/Documents/Cluade/Macro Dashboard`, and the completeness critic found that
checkout in a broken git state: detached HEAD, an unmerged `config/dag.yml`, 4,560 dirty
entries, HEAD 1,119 commits / ~29 days behind `origin/main` (`git status --short`,
`git branch --show-current`, `git log -1` → `5c90bf15229`, 2026-07-14). Claims resting on
that checkout's **file mtimes or git log** are therefore labelled NEEDS-CORROBORATION and
must not be laundered into confident staleness statements. Claims resting on *parquet
column sets and cell values* are unaffected by the checkout's git state and stand.

---

## 0. The thesis

### 0.1 Mastermind does not lack point-in-time discipline. It has at least ten independent, locally-correct implementations of it that share no vocabulary, no registry, and no enforcement.

This is the whole finding. The repo does not need to be taught bitemporality, contracts,
provenance, or append-only revision chains — it has already built every one of them, well,
more than once, in isolation, by different sessions for different domains, and none of
them can see the others.

| # | Implementation | What it independently solved | Citation | Vocabulary it minted |
|---|---|---|---|---|
| 1 | Calcbench Wave-3A bitemporal engine | five-clock fact occurrence with ordering invariants (`accepted_at` may not postdate `recorded_at`; `computed_at` may not precede `recorded_at`/`mapping_available_at`) | `engine/fundamental_forensics/raw_ledger.py:933-946` | `accepted_at`, `recorded_at`, `mapping_available_at`, `computed_at`, `published_at` |
| 2 | ALFRED release-basis accessor | leak-free macro frame; as-of join on `realtime_start` for vintaged series, modelled release-lag shift for non-vintaged | `engine/pit.py:1-40`, `engine/pit.py:181-191` | `basis ∈ {reference, latest, release}`, `lag_bd`/`lag_bd_measured`/`lag_bd_learned` |
| 3 | CN TuShare full-A spine | generation-atomic PIT identity + lifecycle; unadjusted nominal as price authority, `stk_limit` as legal-band authority, integer CNY cents | `collectors/china_tushare_spine.py:44-52`; `research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md` | `CN-XSHG-600519`, `security_id`, `generation`, `source_ts_code` |
| 4 | Basket membership PIT | append-only content-deduped membership snapshots, per-suite write-lane ownership, explicit `pit=False` disclosure on fallback | `engine/basket_membership_pit.py:97-114`, `:623`, `:659-666` | `SUITE_LANE`, `members_asof`, `basis`, `pit` |
| 5 | `ColumnContract` | per-column liveness contract — exactly one of `max_dark_days` (live) or `retired` (upstream disclosure ended); a retired column that goes null is SILENT, a resurrected one raises | `collectors/base.py:42`, `:69-78`, `:281-307` | `dark`, `resurrected`, `max_dark_days`, `retired` |
| 6 | `engine/canon.py` | one implementation per cross-engine concept, pinned by golden vectors | `engine/canon.py:311` (`rma`), `:353` (`rsi`); `tests/golden/canon_vectors.json` | canon concept names |
| 7 | `qbus` event identity | cross-source event clustering (union-find on shared entity/theme + 3-day window + title-shingle Jaccard ≥ 0.6) **and** a trust-tier for the publication timestamp itself | `engine/qbus.py:38`, `:45`, `:176`, `:502` | `item_id`, `event_key`, `TIMESTAMP_QUALITY` |
| 8 | `engine/price_ladder.py` | a declared price-resolution contract with a per-row `adjusted` stamp and a deliberate fall-through rather than a name drop | `engine/price_ladder.py:60`, `:104-106`, `:129-131` | `ADJUSTED_SOURCES`, `LADDER`, `Resolved.adjusted` |
| 9 | `engine/source_registry.py` | claim-register-then-resolve lifecycle with a versioned Beta-Bernoulli credibility and an explicit authority ceiling | `engine/source_registry.py:54-60`, `:134` | `AUTHORITY{tier,may_rank,may_gate,may_size,may_escalate}` |
| 10 | Prophet clock quartet | formation/price-basis/entry/recorded clocks, append-only ledger, quarantine-not-delete for a diagnosed leak | `data/prophet/ledger_quarantine.json` (VERIFIED(census)); `engine/prophet_stage_inputs.py:200-218` | `formation_date`, `price_basis_date`, `entry_date`, `recorded_at` |
| 11 | `market_memory` feature registry | a frozen per-feature dependency + value contract with a `transform_version` and an availability-class vocabulary | `engine/neuralweb/market_memory.py:147-148`, `:151`, `:339` | `FeatureSpec`, `availability_classes`, `transform_version` |
| 12 | Sector-intelligence ownership registry | one-writer-required data ownership with declared failure behaviour | `config/sector_intelligence_ownership.yml:1-13` | `canonical_owner`, `writer`, `one_writer_required`, `duplicate_writer_behavior` |

Twelve, not six. Read the "vocabulary it minted" column: **twelve solutions, zero shared
words.** The same concept — "when did we learn this" — is called `recorded_at` (1),
`realtime_start` (2), `first_seen_utc` (7), `ingested_at` (census: 15 files), `asof`
(census: 932 files), `as_of` (census: 817 files), `known_at` (census: 64 files),
`observed_at` (92), `effective_at` (50), `valid_from` (24). Nothing joins them. Nothing
enumerates them. Nothing fails when a thirteenth is minted.

The three consequences follow mechanically:

1. **Correctness is per-module and globally unverifiable.** `engine/pit.py` is a correct
   leak-free accessor. `engine/inputs.py:137` defaults `pit_basis=None` (VERIFIED(here)),
   and the census enumerated ~20 call sites — `scripts/build_site.py:4664`,
   `engine/equity_alloc.py` (5 sites), `engine/strategies.py:72`, `engine/masterminds.py:196`,
   `scripts/build_bonds.py:1381`, `scripts/build_transmission.py:42`, the four
   `calibrate_spvector*` scripts and more — every one calling `build_features()` with zero
   arguments (VERIFIED(census)). The fix exists and is not consumed. That is not a capability gap; it is
   an *enforcement* gap, and no artifact in the repo can currently express "this dataset is
   PIT-capable but is being read non-PIT".
2. **A correct module can sit on an empty store and nobody can tell.**
   `engine/basket_membership_pit.py` is complete infrastructure with lane gates,
   content-dedup, and a `pit` disclosure flag — and `find data -iname '*membership_history*'`
   returns nothing for all three registered suites (VERIFIED(census)), so
   `members_asof()` falls through to `pit=False` (`engine/basket_membership_pit.py:666`)
   for every caller on every date, today. The docstring describes shipped behaviour; the
   store describes never-run.
3. **Every new session re-invents the wheel a thirteenth time.** The most direct evidence
   is that it happened *during this recon*: `lib/dataos/` (7 modules, 95,124 bytes) and
   `config/dataset_registry.yml` appeared in this worktree at 2026-08-12 13:43–13:55 while
   the census was running, untracked (`git status --porcelain` → `?? lib/dataos/`,
   `?? config/dataset_registry.yml`; `ls -la lib/dataos/` — VERIFIED(here)). See §0.3.

**Therefore: the Data OS is a convergence and enforcement spine over patterns the house
already proved. It is not a new stack.** Corollary that governs every recommendation
below: *the boring answer already exists in this repo.* Any proposal that is not an
extension of an in-repo pattern must name the specific requirement the in-repo pattern
fails. §12 is the per-subsystem list of what to extend.

### 0.2 Four corrections the adversarial verifier forced

These override the pre-census draft claims. Use these versions.

- **FOUR US daily price stores, not three, and adjustment VINTAGE is a fourth divergence
  axis.** `data/stocks` (229 files), `data/yahoo` (824), `data/baskets/ohlcv` (2,519),
  `data/massive_stock_day` (20,476). The best witness is HON 2025-09-25: `192.573517` /
  `192.419067` / `195.758713` / `201.964905` — four values for one (ticker, date), *three
  of them nominally in the same "adjusted" family* — all four converging to `227.800003`
  by 2026-06-29 (VERIFIED(census), pandas over the materialized checkout). Over the full
  86-ticker overlap of `data/stocks` and `data/yahoo`, 61/86 are bit-identical and 25/86
  diverge, worst HON 4.92%. So `adjusted` is not a boolean and not even a three-valued
  basis: it is a **(basis, as-of-vintage) pair**. §4 is written to that.
- **`data/stocks` has no `open` — universally — but opens ARE obtainable; the defect is
  undisclosed mixture, not absence.** The verifier read the pyarrow schema of all 229
  files: exactly one schema, 229/229 = `(close, high, low, volume, Date)`.
  `data/baskets/ohlcv` carries a real `open` for 2,519 names, and
  `engine/ohlc_reconstruct.py` synthesizes `open := prior close` with a documented
  conservative band (`engine/ohlc_reconstruct.py:1-20`). Reader count re-measured
  here: `grep -rl 'data/stocks' engine scripts collectors lib app | wc -l` → **135**
  (VERIFIED(here); census read 133; the draft said 132). The architectural defect is that
  a gap feature built from a `baskets/ohlcv` open against a `data/stocks` close crosses
  two adjustment vintages and **nothing stamps which open the caller got.**
- **`lib/ticker_aliases.py` is not the only identity seam — it is the narrowest of at
  least ten, and they demonstrably disagree.** It is 53 lines with two entries
  (`lib/ticker_aliases.py:36-40`, VERIFIED(here)). `engine/ledger_identity.py:1-34`
  documents SATS→ECHO (2026-06-24) causing a permanent double count in
  `data/signal_archive/track_record.parquet` and states in the same docstring that SATS is
  absent from the dead-name registry. `lib/ticker_aliases.py` does not know SATS/ECHO.
  Two rename registries that do not agree. §2 enumerates all ten.
- **`engine/canon.py` has NO `atr` and NO `realized_vol` at all**, so ~23 of the cited
  "duplicates" are canon GAPS, not violations of it. `grep -n '^def ' engine/canon.py`
  (VERIFIED(here)) yields exactly: `net_liquidity_bn`, `dollar_liquidity_roc`,
  `net_liquidity_bn_change`, `load_net_liquidity_components`, `_assert_billions_scale`,
  `credit_impulse_level`, `credit_impulse_accel`, `vix_term`, `vix_term_scalar`,
  `sector_macro_beta_blend`, `rma`, `ema`, `rsi`, `resample_sessions`, `crossover`,
  `crossunder`, `bars_since`, `rsi_macd`, `stoch_rsi_kd`, `confluence_signals`,
  `_resample_weekly`, `_as_series`. Corrected counts: 103 files import canon repo-wide,
  **55 in production trees** (`grep -rlE 'from engine(\.| import ).*canon|import engine\.canon|from \.canon' --include='*.py' engine scripts lib collectors app | wc -l`
  → 55, VERIFIED(here)); 56 production files define an rsi/atr/realized_vol-named
  function; only 6 do both. The verifier adjudicated 8 sampled definers and found **5 of 8
  compute a genuinely different quantity** (ConnorsRSI is a composite; `atr_proxy` is a
  deliberately-wide close-only proxy; `_atr_word` maps an ATR to a word). §10 does not
  call a legitimate difference a violation.

Two further evidence corrections that matter to specific sections:

- **Do not write a spec clause targeting `fillna(0)` as a class.** On a 15-site sample
  ~13% are genuine null-as-zero, 53% are semantically correct zeros (a count, a day-0
  return, an explicit "too thin → neutral"), and 20% are arithmetically inert because they
  sit one line above an availability-weighted denominator (`engine/china_conditions.py:334-336`,
  `engine/axes.py:78-79`). The high-yield target is one idiom:
  `(1 + <returns>.fillna(0)).cumprod()` — re-measured here at **22 sites**
  (`grep -rnE '\(1(\.0)? ?\+ ?[a-z_]*ret[a-z_]*\.fillna\((0|0\.0)\)\)\.cumprod\(\)' --include='*.py' engine scripts lib | wc -l`
  → 22, VERIFIED(here)), of which only 2 carry an aliveness guard on the same line
  (`engine/indicators.py:55`, `engine/oracle/timemachine.py:247`). §6 targets that plus the
  volume cluster.
- **Redis is not used anywhere.** `grep -rl 'import redis|redis.Redis(|REDIS_URL|from redis'
  --include='*.py' .` → 0 files (VERIFIED(census)); the earlier count was substring hits on
  `redistribution`. The masterplans reject it explicitly
  (`research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md:44`, "Boring wins"). §13 designs to that.

### 0.3 The implementation that already exists in this worktree, untracked

`lib/dataos/{__init__,identity,nulls,price,quality,registry,temporal}.py` (100,680 bytes
total) and `config/dataset_registry.yml` (14,757 bytes), plus six `tests/test_dataos_*.py`
files, exist on disk and are untracked (`git status --porcelain`, `ls -la lib/dataos/`,
`ls -la config/dataset_registry.yml` — VERIFIED(here), 2026-08-12). They were written at
13:43–13:55 by a concurrent lane and are one `git clean` from gone; while untracked their
tests can never run in CI.

Three consequences for this document, stated rather than hidden:

1. This document is written as the architecture those modules should implement, not as a
   greenfield design. Where a section says "PROPOSED", it means *not committed and not
   enforced* — which is true of `lib/dataos/` today regardless of what is on disk.
2. Any sentence of the form "nothing declares what a dataset is" would be false against
   the working tree and is not written here.
3. Ownership must be resolved before anything commits those paths (house law: check
   `git worktree list` before claiming a lane). This lane did not touch them.

---

## 1. Layers (D1)

Five layers. The layer is a property of the *dataset*, declared in the registry, not a
directory convention — `data/` today mixes all five and that is fine.

| Layer | Name | What it is | Retention rule |
|---|---|---|---|
| L0 | SOURCE | vendor payload + request receipt | **receipt mandatory, payload conditional.** Retain the payload only where replay is required — fundamentals, corporate actions, anything revisable. Full payload retention everywhere is rejected on cost. |
| L1 | NORMALIZED | vendor-shaped → house schema, still vendor-scoped (`data/yahoo`, `data/massive_stock_day`) | keyed by `(vendor, vendor_symbol, msec_id)` |
| L2 | CANONICAL | one authoritative representation per `(security, field, basis, vintage)` | the price-basis law (§4) lives here |
| L3 | DERIVED | indicators, features, factors | `engine/canon.py` is its seed (§10) |
| L4 | INTELLIGENCE | Prophet, ranks, scores, regimes | must carry identity + code version + data cutoff + expiry |

**Law: derived data must never masquerade as source.** The in-repo precedent that this is
a real and expensive failure is `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`, which stop-shipped
an entire CN limit-alpha program because a vendor-*adjusted* price was used where the
exchange's *raw print* was the only lawful input, and whose reopen path requires
"authorized unadjusted TuShare `daily` × same-key vendor `stk_limit`, integer-cent
equality". The spine already encodes the same law in code:
`collectors/china_tushare_spine.py:47-51` — "`daily` is unadjusted nominal price
authority… `stk_limit` is exact legal-band authority. Canonical event prices are integer
CNY cents."

**Two structural facts the layer model must accommodate, both measured:**

- **L2 does not have to live under `data/`.** The Wave-3A fundamentals substrate is
  R2-CAS-native by design: `collectors/sec_capital_structure_companyfacts.py` writes under
  a `capital_structure` group that does not exist anywhere in the materialized `data/`
  tree, and `engine/fundamental_forensics/attested_history_store.py:1-8` reads a dedicated
  R2 bucket via `FF_ATTESTED_R2_READONLY_*`, deliberately never importing
  `engine.research_vault.r2_store.build_store` (VERIFIED(census)). A catalog that assumes
  "parquet under `data/` is the store" is wrong for an entire wave. Registry `storage` is
  therefore a first-class field with `filesystem | r2 | supabase | site_artifact` values.
- **L4 can be sourced from a SITE artifact.** Prophet's candidate universe is
  `site/factordata/us_standouts.json`'s `buy[]` lane, read at
  `engine/prophet_bridge.py:1156`, a single file overwritten every render whose only
  point-in-time record is its git history (VERIFIED(census)). This is not a defect to
  outlaw by fiat — it is a dataset whose `storage: site_artifact` and whose
  `temporal_profile` obligations (§3) must be declared and met.

**Source-of-truth policy.** Exactly one dataset per `(security, field, basis, vintage)` is
`canonical: true`; everything else is `normalized` or `derived` and must declare
`derived_from`. Where two datasets genuinely disagree and the disagreement is *intended*,
the registry expresses that as a first-class `divergence` record (§10) — it does not pick a
winner. The one-writer principle is already law in one domain and should be generalized
rather than re-invented: `config/sector_intelligence_ownership.yml:6-13` sets
`one_writer_required: true`, `duplicate_writer_behavior: hard_fail`,
`unresolved_owner_behavior: block_or_degrade`, `user_state_owner: terminal_supabase`
(VERIFIED(here)).

---

## 2. Identity (D2)

Five distinct concepts, three id forms, one law: **a symbol is never an identity.**

| Concept | Id form | US | CN | HK |
|---|---|---|---|---|
| Issuer (economic entity) | `ISS:<inception listing key>` | `ISS:US-XNYS-MMC` | `ISS:CN-XSHG-600519` | `ISS:HK-XHKG-00700` |
| Security (legal instrument / share class) | `SEC:<inception listing key>` | `SEC:US-XNYS-MMC` | `SEC:CN-XSHG-600519` | `SEC:HK-XHKG-00700` |
| Listing (security on a venue) | `<CC>-<MIC>-<CODE>` (bare) | `US-XNYS-MMC` | `CN-XSHG-600519` | `HK-XHKG-00700` |
| Symbol | plain string, venue+time scoped | `MRSH` today, `MMC` before 2026-01-14 | `600519.SS` / `600519.SH` | `0700.HK` |
| Vendor id | alias row, never a key | yahoo `MRSH` | tushare `600519.SH` | |

Rationale, each point grounded:

- **Bare `<CC>-<MIC>-<CODE>` is already in production for CN.** The TuShare spine contract
  defines `CN-XSHG-600519` / `CN-XSHE-000001` / `CN-XBSE-920163` as the stable IDs with the
  vendor code retained in `source_ts_code`
  (`research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md`). Adopting it unchanged means
  **zero migration for the China estate.**
- **The two easily-conflated concepts carry a visible type prefix**, so a grep, a parquet
  dump, or a log line tells you which concept you are holding. Type-visibility is what makes
  misuse hard, which is the point of the project.
- **`<CODE>` is the code the listing carried at inception, never the current one.** This is
  what makes the id survive the exact event that motivates the project: Marsh McLennan stays
  `US-XNYS-MMC` after MMC→MRSH (`lib/ticker_aliases.py:36-40`), Fiserv stays `US-XNAS-FISV`
  after FISV→FI.
- **No allocator, no counter, no hash.** Two parallel sessions minting the same security
  independently produce the same id. This is not theoretical here: the repo routinely runs
  20+ concurrent worktrees, and a sequential counter is a permanent merge-conflict surface.
- **Ticker reuse on the same venue after a delisting** is the one collision case:
  disambiguate with an explicit `.2` suffix (`US-XNYS-MMC.2`). Rare, greppable, never silent.
- **Mint-once-and-store.** The derivation above is the *allocator*; the value written into
  the master is the *authority*. A later correction to inception facts appends an alias, it
  never re-mints. This mirrors the spine's generation-atomic pointer promotion and satisfies
  `DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY` — no run clock enters identity.

Derivative classes: option contract
`OPT:<underlying listing key>:<YYYYMMDD>:<C|P>:<strike×1000, 8 digits>`; future
`FUT:<MIC>:<root>:<YYYYMM>`; index `IDX:<provider>-<code>`; FX pair `FX:<base><quote>`.
OCC/OSI symbols and vendor contract ids are **aliases**. This matters specifically because
options identity is the worst case in the estate: four mutually-incompatible encodings in
simultaneous use with no crosswalk module — fixed-width OCC-21
(`engine/options_focused_quote.py:641-646`), Polygon's variable-root `O:` ticker persisted
as-is (`collectors/polygon_options.py`, verified on disk as `strike_ticker =
'O:SPY260710C00525000'`), a synthetic sha256 `contract_id`
(`engine/options_focused_quote.py:636-638`), and a bare `(root, strike, exp, right)` tuple
(`engine/options_structure.py:249-261`) — all VERIFIED(census).

### 2.1 The ten identity seams

The problem is not that one seam is too small. It is that ten seams exist with no shared
vocabulary, three incompatible id schemes, and demonstrable disagreement.

| # | Seam | Scope | Citation |
|---|---|---|---|
| 1 | `lib/ticker_aliases.py` | membership ticker → Yahoo *fetch* symbol; 2 rows; explicitly "not a display map" | `lib/ticker_aliases.py:36-40` (53 lines, VERIFIED(here)) |
| 2 | `lib/delisted_symbols.py` + `config/delisted_symbols.yml` | "the SECURITY STOPPED EXISTING — it is not a rename"; three consumers act differently on it | `lib/delisted_symbols.py` (108 lines, VERIFIED(here)) |
| 3 | `lib/symbol_directory_receipts.py` | prospective completion receipts; forbids synthesizing a receipt from filenames/mtimes/git | `lib/symbol_directory_receipts.py` (833 lines) |
| 4 | `engine/entity_resolver.py` | five-layer text→ticker ladder with its own alias sources incl. a CUSIP→ticker map | `engine/entity_resolver.py` (318 lines, VERIFIED(here)) |
| 5 | `engine/name_resolver.py` | company NAME → ticker via SEC `company_tickers` | `engine/name_resolver.py` (152 lines) |
| 6 | `engine/ledger_identity.py` | ticker-rename identity for append-only ledgers; knows SATS→ECHO | `engine/ledger_identity.py:1-34` (VERIFIED(here)) |
| 7 | `collectors/edgar_deadnames.py` | dead ticker → CIK bridge; documents that `edgar.py:423` drops delisted filers | `collectors/edgar_deadnames.py` |
| 8 | `config/theme_graph_identity_breaks.yml` | a THIRD id convention: `co:<market>:<SYMBOL>` retired and re-minted as `…#2` | `config/theme_graph_identity_breaks.yml` |
| 9 | `config/biocatalyst_sponsor_ticker_map.yml` | sponsor name → ticker, schema-backed | `contracts/biocatalyst/biocatalyst_sponsor_ticker_map.v1.schema.json` |
| 10 | `config/us_search_aliases_zh.json` | zh search aliases | `config/us_search_aliases_zh.json` |

Seams 1, 2, 4 and 6 were re-verified here (`wc -l`, and the file reads cited above); seams
3, 5 and 7–10 are VERIFIED(census) from the adversarial verifier's sweep
(`grep -rlEi 'ALIAS|_ALIASES|alias_map|SYMBOL_MAP|TICKER_MAP|RENAME' engine lib collectors
scripts config contracts` → 672 files, from which these ten were adjudicated as
independently-governed identity surfaces).

Three incompatible collision-suffix conventions coexist: `CN-XSHG-600519` (spine),
`co:<market>:<SYMBOL>#2` (theme graph), `US-XNYS-MMC.2` (this design). The disagreement is
demonstrable, not hypothetical: SATS/ECHO is known to seam 6 and unknown to seam 1.

**The alias table is the translation layer**, one row per
`(vendor, vendor_symbol, msec_id, valid_from, valid_to)`. It supersedes seam 1, whose own
docstring records the cost of fragmentation — MMC→MRSH was carried by
`scripts/fetch_basket_extras` but not by `scripts/fetch_basket_ohlcv`, so
`data/baskets/ohlcv/MMC.parquet` never existed and the `insurance` basket rendered 18/19
members for seven months (`lib/ticker_aliases.py` docstring, VERIFIED(census)).

**Three identity facts a migration plan must budget for:**

1. **26 `engine/*.py` China modules hardcode yfinance-suffix strings as first-class lookup
   keys** — e.g. `engine/china_market_drivers.py:263` computes
   `extra['semis_rs'] = f['512760.SS'] / f['510300.SS']`, and
   `engine/china_allocation.py:45-59` keys an entire allocation-role table off
   `510300.SS`/`510880.SS`/`518880.SS` (VERIFIED(census)). The stable-ID spine cannot become
   the real identity layer while these joins exist.
2. **China fundamentals do not join the spine.** `data/china_fundamentals/fundamentals.parquet`
   and `data/china_analyst/forecast.parquet` key on `000001.SZ` / `600519.SS`; their
   collectors are keyless akshare/Eastmoney paths independent of
   `collectors/china_tushare_spine.py` (VERIFIED(census)). "The spine exists" does not mean
   "everything joins to it" — the registry must enumerate each lane's native key format and
   its join path.
3. **Every user-owned plane keys on a bare ticker string with no market qualifier.**
   `watchlist_symbols.symbol`, `alerts.symbol`, `favorites.value`,
   `portfolio_positions.ticker` (VERIFIED(census), charting-app migrations). No repo uses
   Macro's identity seam outside Macro. Identity work that stops at the market-data plane
   leaves the user plane un-migrated.

---

## 3. Temporal model (D3)

Seven named times, but **no dataset is required to carry all of them.** Each dataset
declares a `temporal_profile` from a closed vocabulary; the profile determines which clocks
are mandatory. This is the design's answer to D11's rejection of full bitemporal modelling
for datasets that never revise — bars never revise, and forcing them into a bitemporal
table is pure cost.

| Clock | Meaning | Existing house name |
|---|---|---|
| `period_start` / `period_end` | the interval the observation *describes* — a bar, a fiscal quarter, a CPI month. An interval label, not a clock. | |
| `event_at` | instant the economic event occurred (trade, halt, announcement) | |
| `effective_at` | when the information becomes applicable (split effective date, index membership date) | `valid_from` (`engine/theme_graph/store.py:54`) |
| `published_at` | when the SOURCE made it knowable | `accepted_at` (`engine/fundamental_forensics/raw_ledger.py:942`), `seendate` (`engine/qbus.py`) |
| `ingested_at` | when Mastermind received it | `recorded_at` (`raw_ledger.py:941`), `first_seen_utc`, `_crawled_at` |
| `computed_at` | when our pipeline derived it | `computed_at` (`raw_ledger.py:944`), `belief_time` (`engine/theme_graph/store.py:55`) |
| `served_at` | when it became visible to a consumer | `published_at` (`raw_ledger.py:945`) |
| `revision_seq` / `supersedes` | append-only revision chain | `RESTATEMENT`/`AMENDMENT`/`COMPARATIVE_RECAST` event enum (`engine/fundamental_forensics/raw_ledger.py:117-122`) |

Note the collision the mapping exposes and the spec must resolve by decree: the Calcbench
engine's `published_at` means *served by us*, while everywhere else `published_at` means
*published by the source*. The existing names stay valid **where already deployed** — the
registry declares the mapping per dataset rather than forcing a rename that would move
published numbers.

| Profile | Mandatory clocks | Used by |
|---|---|---|
| `BARS` | `period_start`, `period_end`, `ingested_at` | OHLCV |
| `REVISABLE_RELEASE` | `period_end`, `published_at`, `ingested_at`, `revision_seq` | macro, fundamentals, earnings actuals |
| `SNAPSHOT_SERIES` | `effective_at`, `ingested_at`; append-only, content-deduped | memberships, classifications, universes |
| `EVENT` | `event_at`, `published_at`, `ingested_at` | news, corporate actions, filings |
| `DERIVED` | `computed_at`, `code_version`, input cutoffs | indicators, factors |
| `INTELLIGENCE` | `DERIVED` + `data_cutoff_at`, `served_at`, `expires_at` | Prophet, scores, ranks, regimes |

### 3.1 The PIT law

```
known_at := coalesce(published_at, ingested_at)      # the dataset declares which it has
```

A research or backtest read goes through an `as_of(t)` reader that filters `known_at <= t`.
**A dataset whose profile lacks the clock needed to answer `known_at` is FORBIDDEN from
point-in-time reads and must RAISE — never silently return the latest value.**

The current failure mode is exactly that silent latest-vintage return, and it is invisible.
Three measured instances:

- `engine/basket_membership_pit.py:666` sets `pit=False` and falls back to current
  membership when no snapshot exists — correct disclosure, but the store is empty for all
  three suites, so *every* caller gets the fallback and the flag is the only tell.
- Six fundamentals/earnings stores are one-row-per-ticker with a single mutable `asof`:
  `data/earnings/earnings.parquet` has **2 distinct `as_of` values across 1,364 rows**,
  with `eps_forecast` rebuilt wholesale each sweep (`collectors/equity_earnings.py:396-403`,
  VERIFIED(census)). Joining that to a past earnings date is pure look-ahead. The house
  already fixed this once — `data/edgar/fundamentals_panel.parquet` is the leak-free
  successor to `data/edgar/fundamentals.parquet` (`collectors/edgar.py:463-465`) — and
  never generalized the fix to estimates or to the non-US lanes.
- `data/baskets_nasdaq/membership.json` and `data/baskets_russell/membership.json` carry
  bare `{ticker, name}` members with no `added`/`removed` at all, while six sibling suites
  do (VERIFIED(census)). A uniform cross-suite reader gets full look-ahead on 2 of 8 suites
  with no error signal. This is the clearest unconditional look-ahead in the taxonomy layer.

### 3.2 Reproduce ≠ replay

Adopting the Calcbench ruling verbatim: running a 2022 filing through a rule written in
2026 is a current-rule recomputation, not a 2022 system replay. Two distinct guarantees:

- **Recomputable** — same inputs + same code version → same output. Required of L3.
- **Replayable** — what the system *actually emitted* at time `t`, retrieved from an
  append-only served-artifact log. Required of L4 only.

The house already has the replay primitive: `data/prophet_miss_audit/forward_log.jsonl` and
`data/prophet_scan_tier/forward_log.jsonl` (`engine/prophet_miss_audit.py:2245-2292`,
VERIFIED(census)). What it lacks is the *code version*. The census found that published
data artifacts carry a wall clock and no producing-code version: `data/massive_stock_day/_manifest.json`
is `{store, n_tickers, latest_date, updated_at, coverage{…}, anchor{…}}` with no git sha;
`data/index_gex_history/_manifest.json` names `"engine": "engine.gex_engine.compute_gex"`
and carries no version of it. Three subsystems are the exception and prove the house
already owns the right pattern: `engine/context_index/ingest.py:159,415-447` threads a
`git_sha` per document; `engine/capital_structure/share_count_r2_conformance.py:750,766-767`
*requires* a provenance block `{repository, workflow_ref, run_id, run_attempt, commit_sha,
event_name, actor}` validated against a 40-hex regex; and Prophet's origination receipts
pin `run.source_checkout` to a 40-hex SHA plus a sha256 of the exact input bytes — but only
3 receipt files exist in all of git history, all from one force-majeure backfill, covering
~25–39 of 162 live plans (VERIFIED(census)).

**The sharpest argument for the whole temporal section is a measured non-reproducibility:**
`scripts/backfill_prophet_outage.py:9-19` records that the 2026-08-10 evening re-render of
an *identical `as_of`* board swapped the ranker (`us_prophet_v1` → `us_prophet_v2`) and
flapped membership 78↔81 rows **by render-host timezone**, because a `+08:00` host past
local midnight read 2026-08-10 earnings as already past. Same nominal inputs, different
output, driven by the wall clock of the machine. No clock discipline that lives only in a
docstring survives that.

---

## 4. Price canonicalization (D4) — the flagship fix

**Naming law: no stored price column may be named `close`, `price`, or `value` without a
basis suffix.**

`{field}_{basis}`, field ∈ {open, high, low, close, last, vwap, settle, bid, ask, mid},
basis ∈:

| Basis | Meaning | Lawful use | Unlawful use |
|---|---|---|---|
| `_raw` | the price actually printed on the exchange, quote currency, unadjusted | limit-price / tick-size / exchange-rule work, execution simulation, accounting | multi-year return math |
| `_sadj` | split & share-count adjusted only | structure math, technical levels, chart continuity | performance attribution |
| `_tradj` | total-return adjusted (splits + distributions reinvested) | performance and return math only | anything compared to a printed price |

Today's measured state — one ticker, one date, four stores, four numbers, all called some
form of "close" (VERIFIED(census)):

| store / column | NVDA 2024-06-03 | HON 2025-09-25 | true basis |
|---|---|---|---|
| `data/stocks/*.parquet` `close` | 114.8013 | 192.573517 | `close_tradj`, vintage A |
| `data/yahoo/*.parquet` `close` | 114.8013 | 192.419067 | `close_tradj`, vintage B |
| `data/yahoo/*.parquet` `close_price` | 115.0000 | 195.758713 | `close_sadj` |
| `data/baskets/ohlcv/*.parquet` `close` | 114.9351 | 201.964905 | `close_tradj`, vintage C |
| `data/massive_stock_day/*.parquet` `close` | 1150.0000 | — | `close_raw` |

`collectors/yahoo.py:6-13` documents the dual-basis semantics correctly — but only in a
docstring, and the names invert intuition: `close` is the total-return series while
`close_price` is the traded basis, described in-repo as "the correct basis for all structure
math (ZigZag, detrended osc, DCL/failed-cycle, drawdown-from-ATH)" (VERIFIED(here)).
`data/stocks/*.parquet` carries only the `_tradj` series, so the basis the house itself
calls correct for structure math is **absent from the store 135 files read** (§0.2).

### 4.1 Adjusted prices are point-in-time quantities

A series adjusted today differs from the same series adjusted a year ago, because a
corporate action since then re-scaled all prior history. HON is the cleanest witness in the
estate: four values pre-event, all four converging to `227.800003` by 2026-06-29, with
`baskets/ohlcv` 4.96% *higher* pre-event (i.e. under-adjusted) — consistent with the
Solstice Advanced Materials spinoff, though the mechanism is INFERRED precisely because
there is no corporate-action store to check the ex-date and factor against. Therefore:

- every adjusted dataset carries `adjustment_asof`, and `adjusted` is modelled as a
  **(basis, as-of-vintage) pair, never a boolean**;
- the only fully reproducible storage is **`_raw` + a corporate-action factor table, with
  `_sadj`/`_tradj` derived on read.**

### 4.2 No corporate-action event store exists, and the absence is DECLARED

`contracts/market_memory/spy_daily_price_source_observation.v1.schema.json:246-249` pins,
as a required limitation, `"point_in_time_corporate_actions": {"const": false}` alongside
`"total_return": {"const": false}` (VERIFIED(here)). The repo's own contract asserts it.
`grep -rn 'adj_factor' --include='*.py' .` finds zero production sites; yfinance is called
with `auto_adjust=True|False` across 20+ collectors and never with `actions=True`
(VERIFIED(census)). CN is the same: the spine declares `daily` as unadjusted nominal
authority and lists `pro_bar` adjusted-price construction under `not_tested`.

The spec anchors on vocabulary that already exists rather than treating this as greenfield:
`contracts/capital_structure_event.schema.json` already carries a `corporate_action` value
in its family enum; `cn_tushare_minutes_manifest.v1.schema.json` already carries
`corporate_action_basis`; `spy_experience_*.v1.schema.json` already carries
`corporate_action_adjusted`; and CN has one derivable detector today —
`collectors/china_tushare_spine.py:4684` documents `pre_close` as the ex-rights adjusted
vendor field, so `pre_close != prior close` *is* a corporate-action tell whose only current
consumer is limit-band arithmetic (VERIFIED(census)).

### 4.3 The best prior art in the repo is also the most load-bearing bug

`engine/price_ladder.py` already *is* the de-facto price-resolution contract: an ordered
ladder, a per-row `adjusted` stamp, and a deliberate fall-through rather than a name drop —
"dropping an unpriced name deletes exactly the population a study exists to measure"
(`engine/price_ladder.py:60`, VERIFIED(here)). It exists because a cache re-base made
historical prices non-reproducible: PNC at 2026-06-22 read 234.71 in the 2026-07-01 commit
and 232.85 on 2026-08-06, and re-running `scripts/grade_us_board.py` against the shipped
ledger would have moved 75 already-published rows, 19 materially (worst −1.94pp)
(VERIFIED(census), same docstring).

Its central assumption is measurably false. `engine/price_ladder.py:104` declares
`ADJUSTED_SOURCES = ("baskets_ohlcv", "yahoo", "data_stocks", "baskets_extras")`
(VERIFIED(here)) and `is_adjusted()` returns `True` for all of them
(`engine/price_ladder.py:129-131`) — but on 2024-06-03, 31/223 tickers present in both
`data/stocks` and `data/baskets/ohlcv` disagree by >0.01%, 18 by >0.5%, max 4.877% (HON),
**with no consistent precedence**: for HON, yahoo == baskets and stocks is the outlier; for
PEP, stocks == yahoo and baskets is the outlier (VERIFIED(census)). A study whose universe
resolves some names via rung 1 and others via rung 3 mixes two vintages into one
cross-section and the ladder's own `adjusted` flag says `True` for both. The module measured
one pair (extras vs baskets/ohlcv, bit-identical) and never measured baskets vs stocks vs
yahoo.

**This is the single highest-value fix in the document: extend `price_ladder`'s `Resolved`
to carry `(basis, adjustment_asof, source)` instead of `adjusted: bool`.** That is a
one-module change to the seam every consumer already goes through.

Corroborating evidence that store choice is not an implementation detail:
`engine/washout_turn.py:55-72` (VERIFIED(here)) documents that its preferred store is the
*shortest* for long-listed names, that it therefore prepends a ratio-aligned splice from a
deeper store, that "recent-close disagreements between stores are real (split/dividend
adjustment epochs differ…)", and that the measured consequence is a published depth
percentile moving from 6.3 / n=36 to 8.6 / n=8 purely by store choice. A live module changed
a published number by picking a rung.

### 4.4 Session and venue are part of price identity

`session ∈ {pre, regular, post, overnight, auction_open, auction_close}` and
`venue_scope ∈ {primary, consolidated}`. A consolidated-tape last print is **not** the
official closing auction price, and today nothing in the schema distinguishes them. Nor can
a consumer ask whether a date was a half day: early closes are modelled four times and three
of the four models declare the concept out of scope — `lib/nyse_calendar.py:11-14` ("Early
closes (13:00 ET) are NOT modeled", VERIFIED(here)),
`engine/marketing/market_clock.py:77-78`, `engine/live_overlay.py` (advisory only), versus
`engine/session_digest.py:176,199,211` which does model it but "never gates, filters or
labels". `engine/live_overlay.py:129` additionally defines its own `_REGION_HOURS` table
in parallel with the canonical `lib/*_calendar.py` modules (VERIFIED(here)).

The blast radius of the calendar/session service is measured once, with one pattern, and
that number is what §12 and the implementation plan's acceptance gate are scoped against:

```
$ grep -rlE "09:30|16:00|time\(9, ?30\)|time\(16, ?0\)|11:30|15:00|13:00" \
    engine scripts lib collectors app --include='*.py' | wc -l
62
```

(VERIFIED(here).) §D12 pins the figure at 68 and a narrower census pattern
(`grep -rlE "09:30|16:00|9:30" engine scripts lib collectors`, no `app`, no `--include`)
returns 49. The spread is pattern choice, not a dispute about the estate: plan against
"≈60-70 files, re-measured with the exact grep the guard will run." **62 is the number used
throughout this document**; any earlier draft figure (notably an uncited "27") is withdrawn
— it does not reproduce under either published pattern and no census command was ever
attached to it.

Halts are worse: no halt store exists, and halted names are *inferred* as zero-variance and
then silently dropped from cross-sectional estimators
(`engine/theme_crowding.py:47`, `engine/group_flow.py:91`, `engine/synthetic_control.py:454`
— VERIFIED(census)). That is an unmeasured, daily-grain survivorship mechanism inside every
cross-sectional statistic the site publishes, and it is exactly the shape of the standing
trap "gap-refusal survivors are the dead entities".

### 4.5 Migration is staged, because the blast radius is 135 files

- **V1 — labels.** Registry declares each store's true `(basis, adjustment_asof)`; a reader
  shim exposes basis-suffixed names; a guard forbids a *new* unqualified `close`. Zero
  stored bytes move; zero published numbers move.
- **V2 — raw + factors.** Store `_raw` plus a corporate-action factor table and derive
  `_sadj`/`_tradj` on read.

**A constraint V1 must respect:** the raw-unadjusted plane — the only lawful basis for
exchange-limit and structure math per `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT` reasoning — is
the stalest and gappiest store in the estate. `data/massive_stock_day/_manifest.json` reports
`n_tickers: 19133` against 20,476 files on disk, `n_processed_days: 471` over a window of
roughly 1,255 sessions, `max_missing_run_weekdays: 832`, and a SPY anchor of `n_rows 454`
with `max_gap_calendar_days 1165` (VERIFIED(census)). Mandating the raw basis for structure
math **without** a freshness SLA and a gap contract would move every structure calculation
onto a ~37%-populated store. (The associated "4 sessions behind the adjusted planes" claim
rests on the materialized checkout's tips and is NEEDS-CORROBORATION per the header caveat.)

---

## 5. Data contracts (D5)

Extend the house's real contract primitive upward. That primitive is
`collectors/base.py:42` `ColumnContract` — per-column, requiring **exactly one** of
`max_dark_days` (a live column, with a maximum tolerated silence) or `retired` (upstream
disclosure ended), enforced in `__post_init__` (`collectors/base.py:69-78`), and emitting
two distinct violation kinds: `dark` (a live column exceeded its silence budget) and
`resurrected` (a retired column produced a value after its retirement date), with the
crucial property that **a retired column that is simply all-null is SILENT**
(`collectors/base.py:281-307`, VERIFIED(here)). It was born from `china_connect` hiding two
years of dead `net`/`buy`/`sell` columns behind a live `turnover`
(`collectors/china_connect.py:14-32`, VERIFIED(census)) — i.e. from the exact failure a
column-level contract prevents and a table-level freshness check cannot see.

`DatasetContract` is the same idea one level up, declared in one registry file:

```
dataset_id · layer · owner · producer · storage · format · status · wiring_state
grain (key columns) · identity (id column + id type) · temporal_profile
schema {column: {dtype, unit, currency, basis, adjustment_asof, nullable,
                 null_reasons, zero_is_meaningful, range}}
timezone · frequency · vendor + endpoint · rights
conflict_policy · freshness_sla · expected_cadence · quality_checks
inputs (dataset_ids — THE DAG) · code_consumers (function paths — prose)
version · supersedes · derived_from · divergences
```

`inputs` and `code_consumers` are split on purpose. §D5 named one field `consumers`, and
the seed registry proved that one name carries two incompatible answers: the reverse
lineage edge is DERIVED from `inputs` and answers in dataset_ids, while the functions
that read a store are hand-written code paths. Held under one name, a caller cannot tell
which of the two it is holding — and a code path sitting in the graph field is not an
edge, it is a lie the DAG walker will repeat.

Seven fields exist because the census found a specific defect each one prevents:

- **`status ∈ {PRODUCED, PROPOSED, RETIRED}` — three values, matching the implementation.**
  `lib/dataos/registry.py:82-89` `class DatasetStatus` already defines exactly
  `PRODUCED` / `PROPOSED` / `RETIRED` and nothing else (VERIFIED(here):
  `sed -n '82,89p' lib/dataos/registry.py`). An earlier draft of this section prescribed a
  five-value enum adding `DEPRECATED`, `WIRED_EMPTY`, and `UNWIRED`; that is withdrawn.
  `DEPRECATED` and `RETIRED` were two spellings of one state and collapse to **`RETIRED`**,
  the spelling the code uses. `status` answers one question only — *does this dataset
  exist?* — and the wiring question moves to its own field below. This matches the
  contract-plane document, which reaches the same three values from the same source
  (`research/MASTERMIND_DATA_CONTRACTS.md` §1.4); neither document may fork the enum.
  Five census dataset rows were written from filename inference rather than inspection —
  those enter the registry as `PROPOSED` or not at all. A registry listing a dataset that does
  not exist as described is worse than no registry.
- **`wiring_state`**, separate from `status`, because "the producer exists" and "something
  calls the producer" are independent facts and the filesystem shows neither.
  `data/finnhub/recommendation.parquet` is *wired to seven consumers and has never had a row
  written* (`collectors/finnhub_altdata.py:19-22`, `engine/analyst_revisions.py:28-30`
  returns `None` when absent — VERIFIED(here)).
  `collectors/china_block_tape.py:73-81` documents its own nightly wiring in a module
  docstring — a block headed `=== NIGHTLY WIRING (for consolidation) ===` instructing a
  future integrator to add the collector to `scripts/collect.py`, "Or via the adapter
  pattern: `Adapter("china_block_tape", refresh, hosts=["akshare"], serial=True)`" — and
  **that wiring was never applied**: `grep -n 'china_block_tape' scripts/collect.py` returns
  zero matches, and the module defines no Adapter subclass at all
  (`grep -n '^class ' collectors/china_block_tape.py` → none; the module is module-level
  functions only, `refresh` at `:577`, `backfill` at `:476`, `main` at `:609`) —
  VERIFIED(here). The producer exists; nothing calls it, and the only record of that is a
  docstring no tool reads. `data/thetadata_eod/` holds only two JSON sidecars and zero
  ticker parquets. From the filesystem, "coded but disconnected", "wired and silently
  broken", and "deliberately one-time" are indistinguishable today.
  `research/MASTERMIND_DATA_CONTRACTS.md` §1.4 identifies the same gap, declines to invent an
  enum for it, and defers it here ("the wiring state is carried by `producer` plus `notes`
  today; promoting it to its own enum is §5 work"). This section is that §5: the field is
  `wiring_state`, its values (`WIRED_EMPTY` / `UNWIRED` and their siblings) are settled here,
  and `status` is never widened to carry them. `lib/dataos/registry.py` does not yet
  implement `wiring_state`; adding it is a build task in the same wave, and until it lands
  the field is PROPOSED, not PRODUCED.
- **`rights`.** Redistribution is already modelled in three unconnected places with two
  competing key names in the same directory: `"redistribution_class"` + `"license_note"`
  (`collectors/sec_capital_structure_companyfacts.py:5393`) versus `"license_class"`
  (`collectors/biocatalyst/clinicaltrials_v2.py:925`) — VERIFIED(census). The spec picks one
  name. Note the exposure this makes queryable: no price or macro store carries a rights field
  at all, and `data/yahoo`, `data/stocks`, `data/baskets/ohlcv` are all yfinance-sourced
  (personal-use terms) while feeding a paid product.
- **`expected_cadence`** separate from `freshness_sla`, because `data/sec_ftd` is correctly
  ~37 days stale by design — `collectors/sec_ftd.py:5-16` documents a 30-day PIT publication
  lag on a semi-monthly file — and a naive "stalest N stores" report ranks it 4th-stalest
  (VERIFIED(census)).
- **`zero_is_meaningful`** per column (§6).
- **`divergences`** as a first-class state (§10).
- **`producer`** as an explicit field, because the census could not find the writer of the
  most-read US price store in a 60-second search and filed it as an open question; the answer
  is `collectors/sector_holdings.py:259 class StockPriceAdapter` with `group = "stocks"` at
  `:263` (VERIFIED(census)) — which also reveals that `data/stocks` and
  `data/stock_fundamentals` share one collector module.

Two integration points rather than new inventions: `contracts/` already holds 65 top-level
JSON Schemas and 239 including subdirectories (`ls contracts/*.json | wc -l` → 65;
`find contracts -name '*.json' | wc -l` → 239, VERIFIED(here)), all domain-siloed —
capital_structure, biocatalyst, marketing, cn_tushare manifests — **with no schema for
prices, bars, fundamentals, or options**; and
`config/sector_intelligence_ownership.yml` already holds the ownership half for four
domains. The `DatasetContract` registry is the index over both, not a replacement for either.

**Schema evolution has no runner and the spec must not pretend otherwise.** Three mechanisms
are in use: manual SQL apply with the repo file as a replay record
(`scripts/deploy/0007_support_email.sql:5-6` — "APPLIED MANUALLY via the Supabase SQL
editor… there is no migration runner on the render path"), a new schema file at `_vN` with
the old one retained live (six such pairs under `contracts/`), and a bespoke one-shot python
migration per store (`scripts/migrate_narrative_ttl.py` and four siblings) — all
VERIFIED(census). The registry's `version` + `supersedes` fields document evolution; they do
not execute it.

---

## 6. Null / zero / unknown (D6)

Closed vocabulary of missing-reasons, carried as a status sidecar or enum, never conflated
with `0`:

`OK · NOT_YET_AVAILABLE · NOT_APPLICABLE · NO_COVERAGE · VENDOR_FAILED ·
SUPPRESSED_LICENSE · HALTED · PRE_INCEPTION · POST_DELISTING`

Laws: `NaN` means "unknown, reason unrecorded" and is legal only where the contract permits
it. **`0` may never be written to mean absence.** Contracts declare `zero_is_meaningful` per
column.

**The validator targets two specific idioms, not `fillna(0)` as a class** (§0.2 — a 15-site
sample was ~13% genuine defect, 53% correct, 20% arithmetically inert):

1. **`(1 + <returns>.fillna(0)).cumprod()` — 22 sites, 20 unguarded** (VERIFIED(here)).
   A halted, suspended, not-yet-listed, or delisted session compounds as a flat day and the
   index continues through a period where the constituent did not trade. The two guarded
   sites show exactly what the guard looks like: `engine/indicators.py:55`
   (`.where(closes[cols].notna().any(axis=1))`) and `engine/oracle/timemachine.py:247`
   (`.where(alive)`). Unguarded sites include `engine/baskets_intl.py:100`,
   `engine/china_sector_index.py:98` and `:215`, `engine/momentum_crash_gate.py:108`,
   `scripts/oracle_nightly.py:763`, `scripts/oracle_reversion_screen.py:323` and `:668`. This
   is a mechanical detector with a known-good remedy already in the tree.
2. **The volume cluster** — `engine/stock_technicals.py:345` (`vol = volume.fillna(0.0)`),
   `:258` (`has_vol = bool((volume.fillna(0) > 0).sum() > 20)`),
   `engine/volume_signature.py:89`, `engine/leader_lifecycle.py:547`
   (`obv = signed_vol.fillna(0).cumsum()`), `engine/basket_tape.py:184` — VERIFIED(census).
   A missing-volume session becomes a zero-volume session, which is a **different market
   state** (no trades vs no data), and it flows straight into OBV/CMF/accumulation reads.
   Compounding this: `data/yahoo` stores volume as `int64` while `data/stocks` stores it as
   `float64`, so a missing bar cannot even be *represented* as null in the yahoo store.

`HALTED` is the vocabulary's load-bearing member, because it is the one state the estate can
neither record nor distinguish (§4.4).

---

## 7. Multi-vendor conflict (D7)

Per-dataset `conflict_policy ∈ {PRIMARY_ONLY, FALLBACK, DOMAIN_AUTHORITY, CROSS_VALIDATE,
COMPOSITE}`. Discrepancy states: `AGREE · WITHIN_TOLERANCE · DISCREPANT_MINOR ·
DISCREPANT_MAJOR · UNRESOLVED`. Escalation: `DISCREPANT_MAJOR` on a canonical field
**quarantines the value, serves last-good, and opens an incident** — it never silently picks
whichever API answered last.

No policy exists today. The one real resolver in the estate is
`engine/washout_turn.py:55-72`'s per-module ratio-aligned prepend splice, which documents the
adjustment-epoch conflict in prose and then *deliberately refuses to resolve it* for the
signal legs (§4.3). And nothing cross-checks the four US price stores against each other on
a schedule: the audits that exist (`scripts/audit_stocks_freshness.py`,
`scripts/check_price_store_freshness.py`) are per-store freshness checks, which cannot see a
basis disagreement (VERIFIED(census)).

The escalation half is not new either — the primitives exist and only need to be pointed at
data conflicts: a circuit breaker with half-open retry (`collectors/base.py:438-470`,
`:536-559`) and a quarantine-on-corruption idiom that writes
`{ROOT}/{date}.corrupt-{ts}.parquet` and surfaces it in `_meta.json "quarantined"`
(`scripts/chain_snapshot_poller.py:36-38`, VERIFIED(census)).

**What is genuinely missing is memory, not detection.** There is no queryable record of
"store X was wrong between date A and date B for reason R" — the five incidents the census
leaned on (china_connect's 2-year column death, the polygon_gex session-stamp corruption,
finnhub never-existed, the CTRA/TPH 3-month freeze, the MMC 7-month basket hole) survive
only as docstring prose in five different files. That is precisely what a consumer needs in
order to invalidate a cached backtest. The registry gets an append-only `incidents` lane
keyed by `dataset_id` + date range + reason; the postmortem prose stays where it is.

---

## 8. Quality (D8)

Nine check families × four severities.

Families: `completeness · freshness · uniqueness · validity · continuity · distribution ·
cross_source_reconciliation · referential_integrity · temporal_integrity`.

Severities: `INFO` (record) · `WARN` (annotate) · `DEGRADED` (serve with a user-visible
degradation state) · `BLOCK` (refuse to publish).

`DEGRADED` is not a new idea; it is `research/PERCEPTION_CONTRACTS.md` §1's existing law —
"wrong data DEGRADES, never sharpens" — promoted from a per-artifact convention to a
severity in the check taxonomy.

Three design constraints the census forces:

- **Referential integrity needs a per-dataset opt-out with a stated reason.** Three
  unconnected "declared member has no price series" checks exist
  (`scripts/fetch_basket_ohlcv.py:167`/`:296`, `engine/prophet_stage_fusion.py:1280`,
  `collectors/yahoo.py:167-169`) and each reports the same violation class differently; the
  high-traffic one raises only when coverage falls below 70%, tolerating a 30% silent loss,
  with a docstring recording why that threshold exists ("A warning that is always on is a
  warning nobody reads, which is how CTRA/TPH sat frozen for three months"). But
  `collectors/biocatalyst/drugs_at_fda.py:647,661` turns FKs **off** deliberately —
  "source-native orphans are facts to retain". A blanket FK law breaks that store. All
  VERIFIED(census).
- **Freshness must anchor on the deepest producer's own watermark, never on a downstream
  render's mtime.** `scripts/freshness_sentinel.py:33-42` records the re-stamp trap:
  `data/us_prophet_rank/candidates/2026-08.parquet` froze at `stamp_date 2026-08-05` while
  `us_stocks.html` kept re-baking daily, so two independent freshness checks stayed green
  through 0/7 green nightlies. Five freshness mechanisms exist with no shared constant:
  `app/main.py` per-artifact `age_min`, `admin/health.py:15` `_STALE_HOURS=96.0`,
  `scripts/freshness_sentinel.py`'s per-artifact budgets,
  `lib/project_runtime_state.py:69-79` `_CADENCE_SPECS`, and
  `engine/neuralweb/market_packet.py:173` `QUOTES_STALE_MIN=45.0` (VERIFIED(census)). One
  primitive, five callers.
- **The one freshness registry that exists cannot be the base of a new one.**
  `data/run_status.json` covers 149 of **329 top-level `data/` directories (332 entries
  including loose files such as `run_status.json`** — `ls -1d data/*/ | wc -l` → 329,
  `ls -1 data | wc -l` → 332, VERIFIED(here) against the materialized checkout; this is a
  live-tree count, not an mtime/git-log claim, so the broken-checkout caveat does not apply),
  and ~19 "additive, never
  fatal" bolt-on collector calls in `scripts/collect.py` bypass the Adapter-registry loop
  that populates it, so a new collector added the same way silently opts out of freshness
  tracking (VERIFIED(census)). The staleness of that file's own contents is
  NEEDS-CORROBORATION (mtime/git-log dependent); the **coverage gap is not** — it is a
  structural property of the write path. The spec's requirement is therefore: every
  collector, Adapter-registry or bolt-on, writes through one status-emission path.

**Emission follows the house law**: a bare `print("::warning title=<slug>::<msg>",
flush=True)` at line start, never through a logger (CI-guarded by
`tests/test_gh_annotation_line_start.py`; this shipped dead five times before #3587).
Modules that never run inside an Actions step are exempt and listed in that test.

---

## 9. Lineage (D9)

No lineage platform. Three pieces, two of which already exist.

1. **Static dependency DAG.** Every dataset has a stable `dataset_id` declaring
   `inputs: [dataset_id]`. Generated and queryable, zero runtime instrumentation.
2. **Receipts.** Every produced artifact writes a receipt carrying `dataset_id`,
   `code_version` (git sha), inputs with their vintages and hashes, row counts, and clocks.
   This is already the house idiom (`contracts/*_receipt.schema.json`), and the exact block
   to generalize already exists and is validated:
   `engine/capital_structure/share_count_r2_conformance.py:750,766-767` requires
   `{repository, workflow_ref, run_id, run_attempt, commit_sha, event_name, actor}` with a
   40-hex commit regex. Prophet's `data/prophet/origination_receipts/*.json` is the same
   pattern applied to an L4 artifact (`run.source_checkout`, `source.sha256`,
   per-pick `plan_sha256`).
3. **Lineage query = walk the registry DAG + read receipts. No new store.**

The measured gap this closes: for the ~135 Prophet plans originated before the receipt
mechanism existed, there is no way to recover which commit of `engine/prophet_bridge.py`
produced them, and for all 329 top-level `data/` directories (332 entries including loose
files) "the number changed" cannot be distinguished
from "the code changed" (VERIFIED(census)).

One cross-repo lineage seam must be named because the authoritative audit misses it:
`research/CROSS_REPO_CONTRACT_BOUNDARY_AUDIT_2026-08-11.md`'s 9-row bridge inventory has no
entry for the Terminal's `ingest/build_universe.py:49`
`MACRO = Path(os.environ.get('MACRO_REPO', '/Users/chriswong/Documents/Cluade/Macro Dashboard'))`
— a direct local-filesystem read of Macro's private `data/` tree, present in 17 Terminal
ingest files, which also writes results *back* into Macro's `data/tushare/`
(`ingest/collect_us_deep.py:37-39`) — all VERIFIED(census). The three repos are not
decoupled at the data layer for those paths; they are one filesystem tree wearing three repo
names. Any plan to make `data/` machine-portable breaks Terminal's chart seeding silently.

---

## 10. Feature store — the verdict is NO (D10)

We do not have a serving problem. Features are computed once nightly in one pipeline; the
serving tier is a thin read-through over pre-materialized JSON and does not query features
at request time (§13). A feature store solves online/offline serving skew, which is not the
measured defect.

The measured defect is **unregistered divergence**, and the answer is to extend
`engine/canon.py` plus a feature-definition registry plus a check that flags a *new* local
definition of a canonicalized concept. Three facts shape that:

- **Canon covers six concept families**, not the whole indicator surface: net fed liquidity,
  China credit impulse, VIX term, sector macro beta, and the confluence primitives
  (`rma`/`ema`/`rsi`/`resample_sessions`/`crossover`/`crossunder`/`bars_since`/`rsi_macd`/
  `stoch_rsi_kd`/`confluence_signals`) — the full `def` list is in §0.2, VERIFIED(here).
  ATR, realized_vol, drawdown, breadth, momentum, percentile_rank, correlation, general
  beta, trend, acceleration, and valuation have **no canonical home**. So the first work is
  filling canon gaps, not policing canon violations.
- **A canonical fix does not fix anything until it is consumed.** `engine/canon.py:228-236`
  labels its own `sector_macro_beta` work a "SHADOW artifact (wired, NOT consumed this
  wave)" and states that `playbook.py`'s heat penalty still reads a hand-pasted `config.yml`
  table with a physically impossible `XLC: 1.0`. Verified still live: `config.yml:2994`,
  read by `engine/conditions.py:1199-1211`, consumed by `engine/playbook.py:666` for every
  ticker's playbook card (VERIFIED(census)). The registry therefore tracks a canon entry's
  **consumption state**, not just its existence.
- **A canon module's docstring is not an inventory.** `engine/canon.py:171-179` claims the
  `credit_impulse` collision is closed as "two names, not one label" — while a *third*
  formula (12-month YoY of the trailing-12m sum) is independently implemented in
  `engine/china_internals.py:185-188`, `engine/china_sector_index.py:305-307`, and
  `engine/china_conditions.py:292-295`, the last of which feeds a weighted driver (1.4) into
  a regime score (VERIFIED(census)). The registry must re-derive its census from the
  codebase, never from canon's self-description.

**Registering a divergence is mandatory; resolving one is a product decision.**
`DNR:HOLD-FF-DETECTOR-PERIOD-BASIS` is the binding precedent: four detector ids implemented
three ways with different period bases and three different PIT gates, **deliberately HELD**,
pinned by `tests/test_forensic_detector_crosspin.py` §7, because unifying them silently
republishes a live user-facing surface. The registry must be able to express "these two are
knowingly different" as a first-class state with an owner and a rationale. Under that state,
five of eight sampled `rsi`/`atr` definers are not violations at all — ConnorsRSI is a
composite, `engine/ohlc_reconstruct.py:82`'s `atr_proxy` is a deliberately-wide close-only
proxy, `_atr_word` maps an ATR to a word.

**Where a feature-store vocabulary is genuinely needed, one already exists and should be
promoted rather than re-minted:** `engine/neuralweb/market_memory.py:147-148` pins
`FEATURE_REGISTRY_VERSION` / `SOURCE_REGISTRY_VERSION`; `:151` defines `FeatureSpec` as a
"Frozen dependency and value contract for one decision-time feature" carrying `domain`,
`unit`, `value_schema`, `required_source_roles`, `allowed_availability_classes`, and
`transform_version`; `:339` names `CANONICAL_FEATURE_REGISTRY` (VERIFIED(here)). Version
equality is enforced across receipt/packet boundaries at
`engine/neuralweb/market_memory_pit.py:1213,1387,1429-1430`. Its `availability_classes`
vocabulary (`intraday`, `session_close`, `scheduled_release`, `revision`) is the missing
piece the rest of the repo lacks. Scope it honestly: it governs the market-memory replay
subsystem, and its store is not under `data/`.

---

## 11. What NOT to build (D11)

Kafka. Snowflake. Databricks. "Data mesh" vocabulary. A lineage SaaS. Event sourcing. A
Redis tier (§0.2 — there is nothing to migrate, and the masterplans reject it by name). Full
bitemporal modelling of datasets that never revise — bars never revise, and forcing them
into a bitemporal table is pure cost, which is exactly why §3's profiles are per-dataset.
Rewriting any store. A second control plane or authority map: `duplicate_control_planes` is
a standing prohibition in Mastermind's `AGENTS.md`, and company strategic state lives in
`Mastermind/config/strategic_state.yml`, not here.

Two additions the census earns:

- **Do not build a second ownership registry.** `config/sector_intelligence_ownership.yml`
  exists, is tracked, is test-enforced, and is referenced by SHA from
  `config/biocatalyst_closed_beta_source_manifest.yml:17-18`. A duplicate would violate its
  own `duplicate_writer_behavior: hard_fail` spirit. Extend its scope to the price, macro,
  options, news, and CN domains — which is precisely the gap: none of those has a
  `canonical_owner` row today (VERIFIED(census)).
- **Do not build a vector/embedding store, and do not assume one exists.** "Vector" is a
  four-way naming collision across `data/vector`, `data/spvector`, `data/news_vector`,
  `data/china_news_vector`, none of which contains embeddings; `engine/news_vector.py:45-47`
  has LLM structured-extraction stubbed off (VERIFIED(census)). The naming convention
  should reserve `*vector*` for literal embedding stores so a future build does not collide.

---

## 12. WHAT ALREADY EXISTS AND MUST BE EXTENDED, NOT REPLACED

This is the most useful section in the document for a future session. Per subsystem: the
existing module, what it already does correctly, and the single extension that closes the
gap.

| Subsystem | Existing module — do not rebuild | What it already gets right | The extension |
|---|---|---|---|
| **Price resolution** | `engine/price_ladder.py` (499 lines) | ordered ladder, per-row provenance, fall-through over name-drop (`:60`), an explicit unadjusted rung (`:105`) | replace `Resolved.adjusted: bool` with `(basis, adjustment_asof, source)`; measure baskets-vs-stocks-vs-yahoo, which it never did (§4.3) |
| **Ingest store** | `lib/store.py` (192 lines): `read`/`upsert`/`last_date`/`_quarantine`/`basis_shifted`/`write_status` | one `(group, name)` path convention, outlier guard, quarantine, a basis-shift detector | make `write_status` mandatory for bolt-on collectors too (§8); carry a per-series status, not one global run file |
| **Column contracts** | `collectors/base.py:42` `ColumnContract` | per-column liveness, `dark` vs `resurrected`, silence-by-design for retired columns | lift to `DatasetContract` (§5); keep `ColumnContract` as the column-level leaf |
| **Collector plumbing** | `collectors/base.py:136-151` `http_get` (retry on 429/500/502/503/504, exponential backoff), `:438-470` circuit breaker | already centralized — the one cross-cutting concern that is | fold the three hand-rolled Polygon/Massive clients (`collectors/polygon_news.py:135-138`, `collectors/polygon_options.py:93-107`, `scripts/build_polygon_universe.py:153-171`) into it |
| **Macro PIT** | `engine/pit.py` — ALFRED as-of join, `basis ∈ {reference, latest, release}`, `_effective_lag_bd()` preferring learned > measured > prior (`:181-191`) | a complete, correct, leak-free accessor | promote `pit_basis='release'` into `engine/inputs.py:137`'s default — **after** fixing the vintage store, since 28 config-declared series are absent from `vintages.parquet` and would fall back to reference silently |
| **CN identity** | `collectors/china_tushare_spine.py` (~3,600 lines) + `research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md` | stable IDs, generation-atomic refresh, code-range board classifier with a runtime disagreement guard, integer-cent legal-band authority | it is **dormant** — the operational gate is false (`:44-45`) and its declared store root does not exist on disk (VERIFIED(census)). Cite as design authority, never as a live source |
| **Basket membership PIT** | `engine/basket_membership_pit.py` — lane ownership (`:111-114`), content-dedup, `pit` disclosure (`:659-666`) | complete infrastructure, correct disclosure semantics | backfill the store; it is empty for all three suites, so every call is `pit=False` today |
| **Event identity** | `engine/qbus.py` — `item_id` per article, `event_key` per cross-source cluster (`:176`), `TIMESTAMP_QUALITY` (`:45`), `echo_stats` (`:502`) | the only cross-source event identity in the repo, plus a trust-tier on the publication timestamp | fold `TIMESTAMP_QUALITY` into §3 as a per-clock trust attribute; note `event_id` (title+domain) does **not** cluster, by design (`engine/qkernel.py:193-204`) |
| **Derived-intelligence lifecycle** | `engine/source_registry.py` — `AUTHORITY{tier, may_rank, may_gate, may_size, may_escalate}` (`:54-60`), Beta-Bernoulli credibility (`:134`), register-then-resolve at D+20 NYSE days | the cleanest template in the repo for "accrues evidence, grades itself, may never act" | reuse the AUTHORITY block verbatim as the registry's authority field for every L4 dataset |
| **Bitemporal facts** | `engine/fundamental_forensics/` (~33k lines), `raw_ledger.py:933-946` `TemporalClocks`, `:117-122` typed revision events | five clocks with enforced ordering; restatement as an append-only event, not an overwrite | generalize the clock names into §3's vocabulary; do **not** port the engine — it is R2-CAS-native by design |
| **Feature contracts** | `engine/neuralweb/market_memory.py:147-151,339` `FeatureSpec` + `CANONICAL_FEATURE_REGISTRY` | `transform_version` per feature; an `availability_class` vocabulary nothing else has | promote the vocabulary; keep the registry scoped to market-memory replay |
| **Ownership** | `config/sector_intelligence_ownership.yml` (477 lines, `one_writer_required: true`) | tracked, test-enforced, SHA-referenced by a downstream manifest | extend coverage to price/macro/options/news/CN; never create a second file |
| **Concept canon** | `engine/canon.py` + `tests/golden/canon_vectors.json` | golden-vector pinning; the `rma` primitive that makes Wilder correct | add `atr`/`realized_vol` derived from `rma`; add a consumption-state field (§10) |
| **Theme identity** | `engine/theme_graph/store.py:54-59` — `valid_from`/`valid_to`/`evidence_time`/`belief_time`, keyed `(edge_id, belief_time)` so a new belief appends (`:69-72`) | the architecturally correct bitemporal membership schema, already written | it has **zero materialized rows**; cite as target schema for a build task, not as a source. Its three weight axes are W1b-stubbed nulls |
| **Machine contract plane** | `scripts/build_feeds.py:12-16` — "Copies are byte-verbatim — the source engine owns the schema; this script never reshapes what it copies" | exactly the producer-owns-schema discipline the contract plane needs | cite as the positive precedent; extend the `asof` normalization to carry `basis` |
| **Artifact conventions** | `research/PERCEPTION_CONTRACTS.md` §1 — `asof` = true data timestamp, `schema_version`, `degraded`/`degrade_reason`, one-source-of-truth-per-concept | already the house's published convention, born from a real trading incident | make it the registry's serialization contract rather than a per-artifact habit |
| **Calendars** | `lib/nyse_calendar.py`, `lib/cn_calendar.py`, `lib/hk_calendar.py` | rule-computed, zero data dependencies, explicit coverage-end constants | fold in `engine/live_overlay.py:129` `_REGION_HOURS` and the **62 files carrying hardcoded session-hour literals** (`grep -rlE "09:30\|16:00\|time\(9, ?30\)\|time\(16, ?0\)\|11:30\|15:00\|13:00" engine scripts lib collectors app --include='*.py' \| wc -l` → 62, VERIFIED(here)); add early-close and halt as first-class, since three of four models declare them out of scope |
| **Serving boundary** | `app/` + `admin/` read zero raw parquet — `grep -rc read_parquet app/*.py admin/*.py` returns 0 for all 87 files (VERIFIED(here)); `lib/store.py`'s importers are all in `collectors/`/`engine/`(ingest-side)/`scripts/`/`tests/`, none in `app/` or `admin/` (VERIFIED(census)) | a genuinely clean ingest/serve split | preserve it as a declared invariant with a guard, rather than assuming it holds as endpoints are added |

---

## 13. Storage verdict

**files + parquet + R2 + git is adequate and was deliberately chosen. Do not migrate.**

The choice is documented as a choice, not an accident:
`research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md:44` rejects "Postgres/TimescaleDB/Redis… a
decade of ops debt", and `research/BREATHING_PLATFORM_MASTERPLAN_BY_FABLE.md:151` records
"SQLite already in production for derived indices; no DuckDB/Postgres/Redis anywhere" — both
VERIFIED(census). The tiering is real and correct:

| Tier | Used for | Verdict |
|---|---|---|
| local parquet under `data/` | market data, per-ticker series, panels | **fine.** Read patterns are whole-file or per-ticker; nightly batch; one writer per store. A database buys nothing. |
| R2 (single bucket, prefix per store) | ~700MB of per-ticker JSON, `massive_stock_day` (R2 is its canonical home), the capital-structure CAS plane | **fine, and load-bearing.** `scripts/publish_r2.py` does md5-vs-ETag delta upload. |
| Supabase Postgres + RLS | user plane only — entitlements, billing, watchlists, positions | **fine and correctly separated.** `charting-app/supabase/migrations/0001_init.sql:2-4` states the boundary in prose: market data is "NOT stored here". |
| SQLite | derived indices, research vault, FDA drug store | **fine.** Single-writer, query-shaped, local. |
| git | small ledgers, memberships, receipts, configs | **fine for what it holds**, with one caveat below. |

**Where it is genuinely inadequate — four places, none of which is fixed by a database:**

1. **Caching has no shared tier and ~19 module-level engine caches have no invalidation.**
   `engine/ai_desk.py:186` memoizes on `(root, ticker)` with no as-of/date dimension and the
   module's own docstring says it is "safe in batch, fatal in a resident service"
   (VERIFIED(census)). This is fine *today* because every nightly run is a fresh process. It
   is a hard blocker for any resident/live tier, and the fix is a data-version dimension in
   the cache key, not Redis.
2. **Git is load-bearing for point-in-time recovery of at least one L4 input.** Prophet's
   candidate universe is recoverable only by walking 195 commits of one overwritten JSON
   path (`engine/prophet_bridge.py:1156`, VERIFIED(census)). A squash or history rewrite on
   that path is an unrecoverable reproducibility loss. Fix: write a dated artifact, keep git
   for code.
3. **A checkout is not a data plane.** The materialized `data/` view this census had to read
   from is in a broken git state (header caveat), and Prophet's ledger reads as *empty* there
   while `git show HEAD:data/prophet/ledger.jsonl` in a current worktree returns 28 rows
   (VERIFIED(census)). Any freshness or completeness answer that depends on a hand-maintained
   checkout being clean is not an answer. Fix: freshness comes from producer-written
   watermarks and receipts (§8, §9), never from file mtimes.
4. **Duplicate fetch, not duplicate storage, is the real cost.** `data/yahoo` (824 files) and
   `data/baskets/ohlcv` (2,519 files) are both yfinance-sourced by two independent code
   paths, and `scripts/collect.py:789-793` justifies the second by a *volume-column gap in
   the first* (VERIFIED(census)). That is one store per `(vendor, universe, missing-column)`
   — a schema gap solved by store proliferation. Fix: extend the schema, retire the second
   fetch. Storage is not the problem; the yfinance rate-limit budget and the two divergent
   adjustment vintages are.

Explicitly **not** recommended: moving `data/` into Postgres/DuckDB, adding Redis, adding a
message bus, or adding an object-versioning layer beyond R2's. None of the four inadequacies
above is a storage-engine problem.

---

## 14. The four Final Questions — architectural form

*(The commissioning brief's exact wording is not present in either input document; the four
questions are restated below in the form this architecture answers them. Detailed answers
live in the implementation plan.)*

**Q1 — What is the one canonical representation of a market fact, and how does a consumer
obtain the right one?** A canonical fact is keyed by `(msec_id, field, basis, vintage,
session, venue_scope)` and reached through a resolver, never through a file path. The
architectural form of the answer is that the resolver already exists —
`engine/price_ladder.py` — and its contract is one field short: it stamps `adjusted: bool`
where the estate demonstrably needs `(basis, adjustment_asof, source)`. Consumers do not
choose stores; they declare the basis they need and the resolver either supplies it or
raises. The staged migration (label first, re-derive later, §4.5) exists because 135 files
read one store and no published number may move as a side effect of adding a label.

**Q2 — How does a future session learn what a number means without reading its producer's
source?** From one registry file, not from docstrings. Today the answer to "what basis is
`data/stocks.close`?" lives in `collectors/yahoo.py`'s docstring for a *different* store,
and the answer to "who writes `data/stocks`?" required a code search the census failed and
the critic closed. The architectural form is a `DatasetContract` per dataset carrying
grain, identity, temporal profile, per-column unit/basis/null semantics, producer, rights,
cadence, `status` (`PRODUCED` / `PROPOSED` / `RETIRED`, per
`lib/dataos/registry.py:82-89`), and a separate `wiring_state` that can say the store is
wired-but-empty or coded-but-unwired — because the estate contains both and a filesystem
listing cannot distinguish either from healthy (field list owned by
`research/MASTERMIND_DATA_CONTRACTS.md` §1.4; see §5). The
registry indexes the two ownership and schema artifacts that already exist rather than
replacing them.

**Q3 — How is look-ahead prevented from re-entering the system?** By making `known_at`
answerable per dataset and making an unanswerable read *raise* rather than silently return
the latest value. The architectural form has three parts: a per-dataset `temporal_profile`
that declares which clocks exist (so bars are not forced into a bitemporal table they do not
need); the PIT law `known_at := coalesce(published_at, ingested_at)` with a fail-closed
`as_of(t)` reader; and a `code_version` on every produced artifact, because the measured
non-reproducibility in this estate was not a missing clock — it was an identical `as_of`
producing two different boards under two different ranker versions on two hosts. Enforcement
is a registry check, not discipline: the fix for the macro leak already exists in
`engine/pit.py` and has never been consumed, which is the whole thesis in one line.

**Q4 — What is built first, and what must never be built?** First, in blast-radius order,
not tidiness order: the registry and naming law (zero code movement, immediately useful to
every future session); then the identity spine, because everything joins on it and it is the
only defect class with a measured seven-month silent loss; then price-basis labelling plus
the reader shim, because it has the widest consumer count and it already produced a
stop-ship (`DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`); then the calendar/session service;
then contracts and validators on the top-ten datasets; then fail-closed PIT readers; then
lineage receipts everywhere. Never: a new storage engine, a second control plane, a second
ownership registry, a feature store, an embedding store presumed to exist, or a silent
unification of a divergence that a standing HOLD protects
(`DNR:HOLD-FF-DETECTOR-PERIOD-BASIS`).

---

## 15. Open questions and evidence that needs corroboration

- **Ownership of `lib/dataos/` and `config/dataset_registry.yml`** (§0.3) — written by a
  concurrent lane at 2026-08-12 13:43–13:55, untracked. Must be resolved before any commit
  touches those paths.
- **Everything mtime- or git-log-derived from the materialized checkout** — the four stores'
  tip dates, `data/run_status.json`'s freeze date, `data/fred_vintage/vintages.parquet`'s
  last write, and the "every US price store is weeks stale" claim. The *coverage* and
  *column-set* facts drawn from the same checkout stand; the *staleness* facts do not until
  re-measured against a clean tree or against producer watermarks.
- **Whether the self-hosted runner writes to a different live `data/` tree** than the
  checkout — which would explain mtimes newer than the checkout's last commit, and would
  change what "the canonical data plane" even refers to.
- **Whether `data/thetadata_eod` has any reader** in this repo; the store is two JSON
  sidecars and zero ticker parquets.
- **Whether Polygon's `adjusted=true` aggregates parameter is split-only** on this account's
  plan. The Terminal adjustment-drift finding (a symbol's own daily file switching convention
  mid-series) rests on vendor documentation, not on an in-repo assertion — INFERRED.
- **Whether `data/massive_options_day/_effr_dff.parquet`** (a rate series sitting inside the
  options store, next to a hardcoded `r=0.043`) is consumed anywhere, or vestigial.
- **Which of the ~1,100 keyword-matched indicator-shaped functions are distinct concepts** —
  the census's own estimate of 150–300 distinct concepts is explicitly an order of magnitude,
  not a count.
- **Six of twelve census lanes were absent from the completeness critic's payload**, so this
  document's coverage of the areas those lanes owned rests on the lane summaries rather than
  on a critiqued reading.

---

**Citation count.** This document contains **122 distinct `path:LINE` (or `path:LINE-LINE`)
citations** across 96 distinct files, plus 4 standing adjudications cited by key
(`DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`, `DNR:HOLD-FF-DETECTOR-PERIOD-BASIS`,
`DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY`, `duplicate_control_planes`). Every claim about the
repository carries exactly one provenance tag: **34 VERIFIED(here)** (a command run against
this worktree at HEAD `ff88ab548a9`, with the command given), **50 VERIFIED(census)** (the
file and line a census lane opened), **4 INFERRED**, and **4 NEEDS-CORROBORATION** (the
mtime/git-log claims bounded by the broken-checkout caveat in the header). A sentence
carrying no tag and no citation is a defect in this deliverable; §15 lists what is known to
be unresolved rather than leaving it implicit.
