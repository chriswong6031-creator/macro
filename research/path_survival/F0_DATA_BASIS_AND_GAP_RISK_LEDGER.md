# F0 — Data Basis and Gap-Risk Ledger

**Commission:** MASTERMIND GROK-F0  
**As-of:** 2026-08-18  
**Checkout sampled:** `/Users/chriswong/Documents/Cluade/macro-main` and the F0 worktree (same objects).  
**Method:** parquet schema + date-span samples; collector/module docstrings. Missing files are reported as missing, never as zero coverage.

---

## 1. Daily equity planes (US)

| Store | n parquet (this checkout) | Columns | Adj basis | High/low | Open | First-passage usable? | Live-forward |
|---|---:|---|---|---|---|---|---|
| `data/stocks` | 240 | close, high, low, volume | TR (split+div); `grading.py` 32–40 **CODE VERIFIED** | yes | **no** | close + H/L yes; **gap-through no** | nightly |
| `data/yahoo` | 2574 | `close` (TR), `close_price` (split-only, div-unadj), volume | dual; Yahoo retro-readjusts **CODE VERIFIED** `collectors/yahoo.py` 7–16, 222–235 | **no** | **no** | **close-only**. Cannot do honest H/L first-passage | nightly |
| `data/baskets/ohlcv` | 2780 | open, high, low, close, volume | treated as adjusted sibling of Yahoo; survivor tape **PRIMARY SOURCE VERIFIED** `reports/pss_f2_overnight.md` | yes | yes | **best US first-passage plane**, but history typically starts **2014-01-02** | nightly |
| `data/stock_identity/ohlcv` | 2 (BABA, WPM) | full OHLCV | program overflow plane | yes | yes | only names absent from the two curated planes | research |
| `data/massive_stock_day` | 0 parquet; `_manifest.json` + `_backfill_state.json` only | (when restored) daily OHLCV | **unadjusted** vendor; R2 is canonical (~20k names, ~5y rolling) **CODE VERIFIED** `collectors/massive_stock_day.py` | yes when present | yes when present | **forbidden** for MA/DD/gap (`stock_identity/plane.py` 27–28) | R2 restore, not in git |

Sample spans **CODE VERIFIED** (one-row reads 2026-08-18):

- `data/stocks/AAPL.parquet`: 1980-12-12 → 2026-08-17, 11,511 rows, no open.
- `data/yahoo/AA.parquet`: 1962-01-02 → 2026-08-17, 16,264 rows, close only.
- `data/baskets/ohlcv/A.parquet`: 2014-01-02 → 2026-08-17, 3,174 rows, full OHLC.
- `data/stock_identity/ohlcv/WPM.parquet`: 2005-07-06 → 2026-08-13 (2 sessions staler than baskets/yahoo on this checkout).

**Coverage implication:** a universe-wide high/low first-passage study that needs `open` is bounded by the ~2,780-name baskets plane from 2014. A study that needs 20+ years of H/L without open is bounded by the 240 `data/stocks` names. A study that needs 2,500+ names before 2014 is **close-only** (`data/yahoo`).

---

## 2. Minute / intraday / auction

| Source | On disk here? | What it is | First-passage usable? |
|---|---|---|---|
| Durable US minute store | **no** `data/minutes` | — | no |
| `engine/entry_radar/vendor_minutes.py` | cache in evaluator state dir, not `data/` | Polygon `/v2/aggs` `adjusted=true`, episode-windowed, max 180 sessions, C3 4H only | LIVE day-0 / 4H detector input. **Not** a research minute plane. Retro-adjust invalidates cache unless `vintage` fingerprint matches **CODE VERIFIED** |
| `collectors/databento_tbbo.py` | no local store | OPRA options trade+NBBO, cost-capped, inert without key | options tape, not equity path |
| `collectors/thetadata.py` | inert without local terminal | options, not equity OHLCV | no |
| `collectors/databento_tbbo` / Theta | n/a | — | n/a |
| `collectors/tushare_minutes_plane.py` | `data/tushare_minutes` **absent** | CN `stk_mins`, nominal unadjusted, TP-0 gated | not available on this checkout |
| `collectors/tushare_addons.py` `stk_auction` | addon, not sampled | CN opening-auction snapshot 09:26–09:29 | CN only; not wired into `grading.py` |
| Radar `day0_samples` | declared on `EpisodeRef.extra`; **no in-tree producer** (grep = reader only) | last-trade prints after T on session D | **not actually attached in production replay** until a producer exists |

**Overnight vs RTH:** no store splits regular-session vs overnight contribution for US equities. Baskets `open` vs prior `close` is the only cheap overnight *gap* proxy, and it is contaminated by ex-div on TR-adjusted planes.

---

## 3. Candidate / episode / grade stores

| Store | This checkout | Schema (path-relevant) | Forward path rows? |
|---|---|---|---|
| `data/qledger/claims.jsonl` | 43 MB | claims | no path cols |
| `data/qledger/grades.jsonl` | 21 MB | `subject_ret`, `excess`, `hit`, `fill_convention` | no MFE/MAE |
| `data/entry_radar/ledger_state.json` | present | `entry_radar.w5_ledger_state/v1` | `forward_rows_total=0`, `state=WAITING_FOR_LIVE_SOURCE`, `live_forward_start=null` **PRODUCTION VERIFIED** 2026-08-18 |
| `data/entry_radar/forward.parquet` | **absent locally** | W5 nightly writer declared in `daily.yml` | UNKNOWN on VPS/R2 |
| `data/species/registry.json` | exists (not re-opened this session) | metadata | no |
| `data/stock_identity/` | ohlcv overflow only (2 names) | episode catalog lives in program artifacts | W1 census claimed 134,207 episodes historically (`WS-STOCK-IDENTITY`); **not re-counted here** |
| `data/signal_archive/track_record.parquet` | not sampled this session | spine cols per W0.1a | expected; UNKNOWN this session |
| Mastermind `data/brain/` | sister repo | theses + outcome labels | close triple-barrier |

---

## 4. Corporate-action and split hazards

| Hazard | Where it bites | What to do |
|---|---|---|
| Yahoo retro-adjusts TR *and* split-only on every fetch | `data/yahoo`, and any cache keyed by date only | `collectors/yahoo.py` already refetches `period=max` when basis moves. Path studies must stamp `asof` / file mtime / a close fingerprint |
| Interim dividends on TR close | spine `fwd_mdd` is one-directionally optimistic (~<1%/60d) **CODE VERIFIED** `grading.py` 32–40 | use `close_price` (`GradeBasis.PRICE`) when a price-only series exists; most names have only TR |
| `data/stocks` has H/L on the TR plane | H/L and close are jointly adjusted; ratios cancel | gap-through still impossible (no open) |
| Baskets OHLC + Yahoo TR mix | splicing Yahoo close to baskets high/low is a basis crime | one plane per episode; stamp `price_plane_id` (SI law) |
| Massive day aggs unadjusted | splits print as 2:1 cliffs | SI forbids this plane for MA/DD/gap; Path Survival inherits the ban |
| Polygon minutes `adjusted=true` | a split rescales the whole history; cached pre-event minutes + fresh post-event minutes fabricate a 4H turn | `vendor_minutes` vintage fingerprint; drop whole ticker cache on mismatch |
| CN `stk_mins` nominal | unadjusted prints | only reconcile to Tushare nominal daily; never to Yahoo-adjusted CN |
| Ex-div gaps on open | `open < stop` the morning after a large dividend looks like gap-through-stop on TR | Radar W5 prereg flags ex-div and excludes from primary false-start **PRIMARY SOURCE VERIFIED** `W5_FORWARD_EVIDENCE_PREREG.md` § mentions |
| Delisting / halt | series stops | spine `resolve_series` + 14-calendar-day `DELISTING_GAP_DAYS`; Radar censors (`no_further_trades`) |
| Survivorship | baskets/yahoo hold today's listings | `as_of_panel` + PIT membership; pre-2025 member *prices* only on the ~240 deep names |
| SI `data/stocks` no open | ~240 deepest names cannot do gap family | exclude the family, do not impute open |

---

## 5. Market-native fill vs data basis

| Market / desk | Fill | Required columns | Store that can support it |
|---|---|---|---|
| US spine / QLedger / Prophet | next-bar **close** | close | yahoo or stocks |
| US high/low first-passage (Radar / Path Survival target) | P0 then H/L | o/h/l/c preferred | baskets 2014+; stocks H/L no O; yahoo **cannot** |
| CN standout | T+1 HL2 (fallback documented), locked-limit exclusion | T+1 high, low, open, close | CN spine, **not** `grading.fill_index` |
| Radar LIVE day-0 | last trades after T (declared) | minutes | **producer missing** — attach will ignore day-0 unless injected |
| Mastermind thesis | last close ≤ `state_asof` | close | Macro yahoo via `equity_alloc.index_close`, Polygon fallback |

---

## 6. Completeness verdict for first-passage studies

| Study design | Feasible now? | Bound |
|---|---|---|
| Close-path spine (MFE/MAE/terminal_state) on US Prophet/board names | **yes** | yahoo/stocks close; next-bar; TR optimism on MAE |
| High/low first-passage, 2014–present, ~2.7k names | **yes** | `data/baskets/ohlcv` |
| High/low first-passage, pre-2014, deep history | **partial** | 240 `data/stocks` names, no gap-through |
| High/low first-passage, 2.5k names pre-2014 | **no** | yahoo is close-only |
| Minute first-passage / overnight vs RTH PnL | **no durable plane** | Radar LIVE day-0 only; C3 fetch is detector input |
| Opening-auction first print as P0 | **no US store** | Radar `first_trade_after_known_at` is a live/vendor event, not a historical auction tape |
| Whole-market unadjusted SIP day (massive) | bytes live on R2, **not** in this git checkout | restore required; still forbidden for adjusted-path math |
| CN minute first-passage | collector exists, store absent here | UNKNOWN whether VPS has partitions |

---

## 7. PIT risks specific to the data basis

- Retro-adjustment rewrites history under the same filename. A Path Survival row must carry `price_plane_id`, `basis` (`total_return`/`price_return`/`vendor_unadjusted`), and a substrate fingerprint if it will be re-read later.
- Mixing TR close with unadjusted high/low (or TR close with raw open) manufactures false first-passages on every split/div name.
- `as_of_panel` membership can be PIT while *prices* are still survivor-biased for names that died before the dead-name store. `grading.as_of_panel` already stamps this (`pit` note, lines 960–964).
- Radar W5 holdout is `decision_session > 2026-02-13`. Using post-boundary rows in a "discovery" Path Survival fit is leakage.
- SI episode `resolution` is labeled with future data. Joining Path Survival *trade* outcomes onto SI episodes is legal only after `resolution_known_date`.

---

## 8. Rights / vendor risks

- Massive rolling 5-year window: delay permanently loses days (`massive_stock_day.py` 29–32).
- Polygon minute fetch is rate-limited; `vendor_minutes` refuses windows > 180 sessions on purpose.
- Databento is card-linked and capped ($2/fetch); not an equity path source.
- Theta is options and stall-prone on long ranges.
- Tushare minute backfill is TP-0 gated and nominal.

No claim is made about contractual redistribution of any vendor tape.

---

## Search bounds

- `python3` parquet samples of stocks / yahoo / baskets / SI ohlcv / massive dir listing.
- Read: `collectors/yahoo.py`, `collectors/massive_stock_day.py`, `engine/entry_radar/vendor_minutes.py`, `collectors/tushare_minutes_plane.py`, `collectors/databento_tbbo.py`, `collectors/thetadata.py`, `engine/stock_identity/plane.py`, `engine/grading.py` dual-basis comments.
- `data/entry_radar/ledger_state.json` opened.
- Not done: R2 restore of `massive_stock_day`; VPS `forward.parquet`; full date-coverage histogram across 2,780 baskets names; CN/HK minute partitions on the Studio.
