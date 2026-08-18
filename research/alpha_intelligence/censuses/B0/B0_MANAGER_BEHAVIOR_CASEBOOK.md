# B0 — Manager-behavior casebook

**Lane:** GROK-B0 · **Date:** 2026-08-18 · **Pin:** `3d12412e561e`
**Purpose:** ≥40 *examples of behavior classes* a later intent model must be able to label. This is a sensor catalog, not a track record and not a buy list.
**Rule:** no share counts, returns, or "edge" numbers appear unless they were verified this session or are quoted from a house document with its tag. LLM memory of a famous trade is **INFERRED** at most.

Behavior classes requested: initiation · accumulation · within-theme rotation · trim · exit · create/redeem false positive · price-weight false positive · same-manager multi-fund duplication.

---

## How to use

Each row is a **label the ontology + ΔQ formula must not smash**. Several rows are *mechanism* examples (no single date) because that is what F11–F20 need. A later wave should replace INFERRED rows with accession-level receipts from the census store.

---

## A. Initiation (new name appears in a discretionary book)

| ID | Complex / vehicle | Why it is this class | Source / tag | Trap if unlabeled |
|---|---|---|---|---|
| I1 | Featured desk 13F `new` | `active_changes_dir(include_lifecycle=True)` already defines brand-new as `is_new` with undefined % | CODE VERIFIED holdings.py | Scoring % change on a new name is NaN-to-zero |
| I2 | Pershing Square (Ackman) — concentrated new 13F name | Class 1: a new line *can* be the thesis. 13D, if any, is the faster clock | INFERRED pattern + CODE VERIFIED style=`activist` | Treating it like an index add |
| I3 | Baker Bros — new biotech in a specialist book | Class 3 initiation is *within-sector*, not "we discovered healthcare" | CODE VERIFIED `sector_healthcare` | Cross-sector consensus with Akre buying a bank |
| I4 | ARK daily file — ticker present today, absent on t−1 | True initiation *or* a custom-basket create (F2) | CODE VERIFIED collector + INFERRED trap | Create/redeem false positive |
| I5 | 13F confidential position later revealed | Looks like initiation; was held earlier | CODE VERIFIED `exclude_confidential_omissions` | False initiation |
| I6 | 13D first filing (post-2024 5-day window) | Beneficial-ownership initiation, not 13F | CODE VERIFIED INTELLIGENCE_HUB_V2 + OWNERSHIP review | Pre-2024 event studies overstate capturable drift |
| I7 | Scion (Burry) `status: closed` | A new line on a closed filer is a history object, not a live initiation | CODE VERIFIED config | Survivorship / zombie roster |

## B. Accumulation (same name, rising Q or rising book rank)

| ID | Complex / vehicle | Why | Source / tag | Trap |
|---|---|---|---|---|
| A1 | Desk `add` with `add_streak` in conviction weights | House already treats multi-quarter adds as a *descriptive* component (`w_add_streak: 20`) | CODE VERIFIED config.yml | That weight is desk-display, not a lawful score |
| A2 | Berkshire Hathaway — long-horizon add in a low-turnover book | Class 1; 13F lag still ~45d | CODE VERIFIED style + history_quarters 12 | Copying the add the day the 13F prints |
| A3 | Appaloosa — event/distressed add | 13F misses the credit sleeve; equity add may hedge or pair | CODE VERIFIED `event_distressed` | Reading the equity line as the whole idea |
| A4 | ARK multi-day share increases after SO-proxy | Possible accumulation *or* cash-create then deploy (F3) | CODE VERIFIED formula | See C/R section |
| A5 | Census public summary `action_share_change_threshold_pct: 5` | House already refuses to call <5% an "action" on the public census | CODE VERIFIED config | Noise vs accumulation |
| A6 | JPM 13G on Sibanye (SBSW) rising through 5% | **Not accumulation-as-conviction.** Custodian/ordinary-course 13G | CODE VERIFIED `OWNERSHIP_SIGNALS_CASE_STUDY_REVIEW.md` (EDGAR accessions quoted there) | `DNR:KILL-OWNERSHIP-BREAKAWAY` |

## C. Within-theme rotation

| ID | Complex / vehicle | Why | Source / tag | Trap |
|---|---|---|---|---|
| R1 | Featured pair Appaloosa vs Pershing (config: "Tepper's semis rotation vs Ackman's Mag-7 concentration") | House already treats this as the marquee *rotation vs concentration* contrast | CODE VERIFIED `tracker.featured_pair` | Do not average them into one "smart money" |
| R2 | Baker Bros / RA / Perceptive / RTW / Casdin rotating names inside biotech | Class 3: exit of one biotech + initiation of another is rotation, not de-risking healthcare | CODE VERIFIED five `sector_healthcare` slugs | Sector-level 13F "healthcare outflow" |
| R3 | Global X / VanEck thematic index reconstitution | Class 5: names enter/leave because the *rule* changed | CODE VERIFIED etf_holdings design + ETF_DATA_SOURCES | Labeled as active manager rotation |
| R4 | Coatue / Altimeter / Whale Rock in the same tech theme | Same-theme peers; overlapping books are not independent votes | CODE VERIFIED `tiger_crossover` cluster | Consensus `min_funds: 2` counts them as two |
| R5 | Kimmeridge energy specialist vs Basswood financials | Two class-3 books; a name appearing in both is *not* "energy-financials consensus" | CODE VERIFIED styles | Cross-mandate coincidence |
| R6 | China public-fund + southbound + LHB all "rotating" a name | Different clocks, different actors; CN prior art for *not* fusing | #5822 + collectors list CODE VERIFIED | Porting a fused CN "main force" number to US |

## D. Trim

| ID | Complex / vehicle | Why | Source / tag | Trap |
|---|---|---|---|---|
| T1 | Desk `trim` ≥ `min_conviction_pct: 1.0` of book | Small lots are filtered from best/worst boards | CODE VERIFIED tracker config | Rounding lots as trims |
| T2 | Low-turnover superinvestor trim | Often tax / sizing / option expiry, not thesis death | INFERRED; style=`superinvestor_value` CODE VERIFIED | Treating every trim as an exit precursor |
| T3 | ETF SO-proxy residual negative on one name, flat on the basket | Possible trim *or* custom redeem (F2) | CODE VERIFIED formula | C/R false positive |
| T4 | 13F value down, shares flat | Price move, not a trim | CODE VERIFIED (share diffs are the desk object) | Price-weight false positive |
| T5 | Amendment 13F-HR/A reducing a line | Correction, not a new decision | CODE VERIFIED amendments/ isolation | Double-counting original + amendment as a trim |

## E. Exit

| ID | Complex / vehicle | Why | Source / tag | Trap |
|---|---|---|---|---|
| X1 | Desk `exit` only after the *same* manager files the new quarter without the name | Autonomous-13F contract: missing ≠ exit | CODE VERIFIED SMART_MONEY_AUTONOMOUS_13F_SYSTEM | The exact false positive this law exists to kill |
| X2 | 13F-NT (notice) | Transition state; never a zero book | CODE VERIFIED `notice_is_zero_portfolio: false` | NT → "liquidated" |
| X3 | Lifecycle `is_exit` on daily ETF snapshots | Name in t−window, absent today | CODE VERIFIED holdings.py | Ticker rename / CUSIP change (F17) |
| X4 | Closed / stale filer (Melvin dropped; avenue/silverpoint stale >18m) | Roster exit ≠ portfolio exit | CODE VERIFIED comments | Survivorship in any "smart money sold" tape |
| X5 | Fundsmith | UK-domiciled, **no 13F obligation** | CODE VERIFIED exclusion comment | "Fundsmith exited the US" because the form does not exist |
| X6 | 13G drop below 5% (JPM SBSW 6.5% → 4.7% in the reviewed accessions) | Reporting-threshold exit, not necessarily an economic exit | CODE VERIFIED review doc (accessions 0000019617-25-001005 and 0000019617-26-000028) | Scoring a bank 13G drop as a specialist sell |

## F. Creation / redemption false positive

| ID | Vehicle | Mechanism | Source / tag |
|---|---|---|---|
| C1 | Any ETF | In-kind create scales every name; raw ΔQ looks like a basket buy | CODE VERIFIED holdings.py docstring (this is why the formula exists) |
| C2 | ARKK/ARKW | Custom / cash basket: a subset of names move with S (F2/F3) | INFERRED mechanism; ARK is the house's explicit active-ETF watchlist |
| C3 | Global X dated files | Sum-ratio proxy S moves if one mega-cap is a large add (F1) | CODE VERIFIED proxy definition |
| C4 | Median-ratio fallback when `< flow_min_scale_n: 5` continuing names | Thin thematic funds flip to the worse proxy | CODE VERIFIED config |
| C5 | Roundhill master file `Date` ≠ URL date | Wrong t pairing → fake create | CODE VERIFIED ETF_DATA_SOURCES |
| C6 | ProShares levered (not in universe) | Daily reset + create looks like enormous ΔQ | CODE VERIFIED recon "mostly leveraged/swap" |
| C7 | N-PORT monthly create/redeem vs daily snapshot | Official flow is monthly; daily residual still noisy | CODE VERIFIED holdings.py N-PORT comment |

## G. Price-weight false positive

| ID | Vehicle | Mechanism | Source / tag |
|---|---|---|---|
| W1 | Sector-SPDR top-10 residual | Weight change after price move is reconstitution/float on a **passive** fund, not conviction | CODE VERIFIED holdings_signals comment |
| W2 | 13F `$ value` QoQ without share check | Post-2022 unit change + price move | CODE VERIFIED `_DOLLARS_FROM` |
| W3 | Cap-weight index (SPY/QQQ) | House **excluded** them from etf_holdings universe for this reason | CODE VERIFIED config comment |
| W4 | "Accumulation Watch" on one snapshot | Config itself says thresholds UNCALIBRATED until weeks of daily snapshots exist | CODE VERIFIED holdings_signals |
| W5 | GOOG/GOOGL or dual-class weight split | Two lines, one economic name | INFERRED; desk has `share_class_equiv.yml` |
| W6 | Currency-shaped equity tickers dropped as FX (COP, PEN, EUR AU) | Measured 130 rows / 6 issuers erased at write time (2026-08-12) | CODE VERIFIED holdings.py comment |

## H. Same-manager multi-fund duplication

| ID | Complex | Mechanism | Source / tag |
|---|---|---|---|
| D1 | ARK Investment Management vs ARKK vs ARKW | Same PM decisions appear in the adviser 13F *and* in each ETF. Cross-ETF consensus counts two vehicles as two votes | CODE VERIFIED two-collector split + consensus_min_funds 2 |
| D2 | 13F OTHERMANAGER / included_managers combination report | Two CIKs, one book | CODE VERIFIED sec_sources.py relationships |
| D3 | Tiger-crossover cluster (Coatue, D1, Altimeter, …) | Not the same complex, but **not independent** either (shared diaspora, shared prime, shared theme) | CODE VERIFIED style cluster; independence is UNKNOWN |
| D4 | Gates Foundation Trust vs Berkshire | Overlap can be the same economic exposure (e.g. historically shared large-cap names) without being one complex | INFERRED; both are featured `superinvestor_value` |
| D5 | Census research bench vs featured desk | Same CIK in both tiers would double-publish if a consumer unioned them | CODE VERIFIED "must be separate" autonomous-13F doc |
| D6 | Quiver `sec13f_changes` (if ever wired) vs house 13F | Second tape of the same filing | CODE VERIFIED OWNERSHIP review (Quiver path flagged as look-ahead risk) — **do not add** |

## I. Extra mechanism rows so the casebook stays honest (still in the eight classes)

| ID | Class | Example | Tag |
|---|---|---|---|
| M1 | Exit / trim | Quant/MM 13F (Citadel, Jane Street, …) "exits" are inventory | CODE VERIFIED SM2-R6 exclusion |
| M2 | Initiation | Class 7 option-income fund "initiates" the equity because the overlay needs a new sleeve | CODE VERIFIED Roundhill skip list |
| M3 | C/R FP | First Trust HTML parser historically wrote **zero** snapshots (SKYY/CIBR/FDN/GRID) — a gap is not an exit | CODE VERIFIED ETF_DATA_SOURCES revival |
| M4 | Price-weight FP | 13F put/call included in equity actions | CODE VERIFIED `exclude_put_call_from_equity_actions: true` |
| M5 | Duplication | China hub raw opportunity including board-derived fields — circular "who owns this" | #5822 PRIMARY-to-PR (proposal, not merged) |
| M6 | Accumulation | Southbound HK holdings rise — official daily holder tape, different law than 13F | CODE VERIFIED collector exists; not a US 13F analogue |
| M7 | Initiation | Special-sits SC 13D → Activist; 13G skipped-but-watch-for-flip | CODE VERIFIED OWNERSHIP review |
| M8 | Trim | `min_position_pct: 0.20` / `min_conviction_pp: 0.05` drop tiny doubles that are % huge and conviction-zero | CODE VERIFIED etf_holdings config |

---

## Counts

| Class | IDs | n |
|---|---|---|
| Initiation | I1–I7, M2, M7 | 9 |
| Accumulation | A1–A6, M6 | 7 |
| Within-theme rotation | R1–R6 | 6 |
| Trim | T1–T5, M8 | 6 |
| Exit | X1–X6, M1 | 7 |
| Create/redeem FP | C1–C7, M3 | 8 |
| Price-weight FP | W1–W6, M4 | 7 |
| Same-manager duplication | D1–D6, M5 | 7 |
| **Total labeled rows** | | **57** |

Rows with **PRIMARY SOURCE VERIFIED** facts this session: A6/X6 (EDGAR accessions as quoted in the house review), ARK trade-notification page, SEC 13F dataset existence. All share/return figures from the JPM/SBSW review remain **that document's problem** (the review itself distrusts the trade math). Do not promote them.

---

## What a later casebook wave must add (not done here)

Accession-level receipts from `engine/institutional_census` for 8–10 *specific* featured-desk new/add/trim/exit pairs, with `accepted_at` and paired-reporter coverage. That requires the evidence store (R2 / data/) this sparse worktree does not materialize. Until then, do not invent the numbers.
