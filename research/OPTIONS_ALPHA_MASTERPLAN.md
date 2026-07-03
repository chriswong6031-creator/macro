# OPTIONS ALPHA MASTERPLAN — from EOD positioning data to validated entry-quality edge

_Authored by Fable (orchestrator), 2026-07-03. Instigated by an external (ChatGPT) recommendation
doc; grounded in a 6-dimension investigation of the live codebase + an adversarial critique pass.
Canonical doc for the program. Status log at §8._

---

## §0 Mission

Turn the options stack from **display-only positioning maps** into a **validated entry-quality
edge** for asymmetric 1–20D swing picks. The thesis, sharpened from the external doc:

> EOD options data answers "where does pressure sit" (positioning/structure). We cannot buy
> "what pressure is arriving now" (flow direction) at acceptable cost — and we have **proven
> empirically** that bar-level signing is worse than a coin flip. So the program routes ALL
> alpha claims through the signals that are reliable by construction — **ΔOI, walls, IV level/rank,
> volume magnitude** — and validates them against the one claim that matters for this desk:
> **does options context reduce stop-outs / dead money and improve clean-liftoff rates on entries
> the price thesis already likes?**

What this program is NOT: a flow-direction desk, a 0DTE desk, a live-tape product. Those are
dead ends on current data and stay dead until a validated use-case funds the tape (§6).

---

## §1 State of play (investigated 2026-07-03, evidence-linked)

**F1 — [FIXED 2026-07-03] Flow accrual never ran in CI.** `MASSIVE_S3_ENDPOINT` GitHub secret
was malformed since creation (2026-06-21) — botocore "Invalid endpoint" on every daily run;
`build_options_flow` no-op'd in ~1s. `site/flow/` was never written; `data/options_flow/` holds
only `signing_gate.json`. **All four `MASSIVE_S3_*` secrets re-set from known-good local `.env`
values on 2026-07-03 (no trailing newline).** First verifying run = next daily.yml. Every missed
day was a permanently lost accrual day.

**F2 — Render lanes have no S3 creds.** `engine-render.yml`/`render.yml` run the flow step with
zero `MASSIVE_S3_*` env → silent no-op on push renders. Ruling A7: flow accrual stays on
daily.yml ONLY; render lanes must merely not destroy committed `site/flow/` artifacts.

**F3 — validate_gex.py reads the wrong store.** It globs `data/cboe/gex*.parquet` (10 equities
+ SPX, 18 rows each, degenerate regime splits: AAPL/AMD 18L/0S, IWM 0/18) and writes
`data/gex/gate.json` (`scripts/validate_gex.py:126` — producer confirmed). The 384-name
`data/polygon_gex/summary_*.parquet` store (4,348 rows, `gamma_regime` + `spot` present) is
invisible to the verdict. Repoint = W0.3.

**F4 — Validation timelines (honest):**
- GEX regime→forward-vol gate: needs 30 obs/bucket/name; cboe path ~Sept 2026 best case
  (QQQ 9L/9S). Repointed to 384 names, first verdicts realistically still ~Sept 2026 but across
  a far wider candidate set.
- Skew (XZZ) / IV-spread (CW) cross-sectional gates: need 120 dates × ≥15 names. Breadth met
  since 2026-06-21; dates are binding → **~Dec 2026**. NOT rescuable by IV backfill (they need
  OI-weighted point-in-time chains; OI is non-backfillable, F6).
- ΔOI persistence IC: 60 dates from 2026-06-15 → **~mid-Sept 2026**.
- Entry-quality harness verdicts: gated on optionable board-ledger fires accruing → **~Q4 2026**
  for n≥30 per condition bucket.

**F5 — IV BACKFILL IS FEASIBLE AND FREE (the program's single biggest unlock).**
massive.com flat-files entitle us to `us_options_opra/day_aggs_v1` **2024-07-02 → present**
(rolling 2-yr window; 502 trading days; ~1.63 GB compressed; 8 cols: OHLCV+transactions per
contract, **NO OI**). Underlying = `data/massive_stock_day/` — **already live, R2-backed,
12,664 tickers, raw closes** (do NOT use Yahoo `close`: dividend-adjusted = wrong price space
vs strikes). BS-invert per-contract closes → per-name ATM-IV30 / skew-shape / term-slope
history, 502 days, 384 names, $0. Caveats are real and ruled in A5 (American exercise, q,
validation design).

**F6 — OI backfill is blocked on massive.** No OI in any flat-file schema; REST snapshots are
point-in-time from 2026-06-15 only. Procurement options exist (§6) but are NOT funded until
the harness proves OI-conditioned signals matter (W4 gate).

**F7 — Flow DIRECTION is permanently soft on current data.** `signing_gate.json`:
`direction_reliable=false` (minute net-sign recovery 0.41 vs Databento NBBO truth; delta-adjust
tested & rejected — see `research/OPTIONS_FLOW_DATA.md`). Magnitude / ΔOI / walls / IV are the
reliable family. No wave may depend on flow direction.

**F8 — The integration lattice is already built and waiting.** `gex_confirm.assess()` runs in
`build_stock_library`; W3 evidence-stack GEX-OPTIONS badge is one vote in k-of-n on
us_standouts buy rows; `stock_score.py` GEX + IV-spread tilts exist but are gated
(`data/gex/gate.json` scored=false, ivspread gate scored=false). Mastermind `_flow_row` lens is
wired and dead pending F1 data. Nothing is scored today — correct per doctrine.

**F9 — The US fire ledger EXISTS as of 2026-07-03** (critique's blocker is stale):
`data/us_board_ledger/retro_grades.parquet` (Stage B-b `grade_us_board`, macro#1142) — one row
per (as_of, lane, ticker, horizon), nightly in daily.yml with a PIT regime-stamp mechanism
designed for exactly this kind of context join. **Schema authority is the SCRIPT
(`scripts/grade_us_board.py:508-520`), NOT any on-disk parquet** — pre-#1142 snapshots in stale
worktrees lack the 20 spine cols (`fwd_mfe_{5,10,21,63}`, `terminal_state_clean15_126` [126d
horizon], `terminal_state_clean8_21` [21d], `post_cushion_breach` [21d], `mae_close_excess_spy/
sector` [EXCESS-vs-benchmark close-path — understates absolute drawdown]). Spine cols populate
from the first post-#1142 nightly grade onward. The entry-quality harness (W1.3) joins/stamps
HERE — no new persistence layer. Note: the ledger has NO absolute-price MAE and NO 5d clean/stop
label — gate criteria in §4 use only real primitives.

**F10 — Storage plane.** `data/polygon_gex/` is **git-tracked, 59 MB after 18 days (~3.3 MB/day
≈ 800 MB/yr)**. Not in the R2 .gitignore block. Any backfill output must obey ruling A4.

**F11 — Universe & coverage.** 384 cumulative names in summaries; ~355 per daily snapshot.
Sector coverage vs the 11 US sector baskets is uneven: Tech 69%, Energy 86% … Health 24%,
Comm 13%, Materials 8%, **Real Estate 0%**. Sector aggregates must suppress <40%-coverage
sectors until W3.2 expansion. Collector does ~14K REST requests/day (355 × ≤40 pages, no
throttle/backoff code) — headroom vs plan ceiling UNKNOWN → probe before growing (W1.4).

**F12 — UI honesty debt.** gex.html `iv_rank` renders rich/cheap bands for 637 names with
`low_confidence:true` (18 < 20-day floor) and no visual caveat; the flow card renders empty
silently on 404. Fix in W0.7.

---

## §2 Doctrine (binding on every wave)

1. **Validate-before-score.** No options signal touches rank/score/sizing until its
   pre-registered gate passes (repo-wide law; see `data/gex/gate.json` pattern). Until then:
   display / confirmer / ledger-seed only. Confirmers may only LOWER confidence.
2. **Claims the system must never make** (live gates forbid):
   - Regime-caution sizing improves returns (`basket_overlay_gate.json`:
     `live_overlay_helps=false`, `beats_brake=false`) — display-only shadow, never a lever.
   - Hard bullish/bearish flow-direction claims (`signing_gate.json`) — tone stays neutral/`~`.
3. **Effect sizes come from literature until our accrual clears the gate.** 18 days = zero
   degrees of freedom. Any "backtest" on sub-30-date options history is noise and is banned.
4. **OI is point-in-time and sacred.** Every missed snapshot day is permanent. Accrual health
   must be circuit-breaker-visible (W0.4).
5. **Dealer-sign assumption is fragile for single names** (covered-call ETFs, retail call
   walls). Single-name GEX = market-structure context, never a directional pick by itself.
6. **Storage:** raw vendor pulls (day/minute aggs) are NEVER git-committed — local cache +
   R2 (`publish_r2 --dirs` + `_manifest.json` + audit_r2 tripwire). Compact derived
   per-name/day summaries (≤ ~30 MB) may live in git.
7. **UI text:** every new user-facing string ships EN+ZH; NO translated text in `title=`/attrs
   (use the `data-tip-en/zh` popover mechanism; `check_title_i18n` CI guard); zh up/down color
   token flip applies; jinja templates guard new keys with `is not none` (missing-key crashes).

---

## §3 Rulings (orchestrator adjudications, 2026-07-03)

- **A1 — gate.json producer:** `data/gex/gate.json` is written by `scripts/validate_gex.py`
  (line 126) off the cboe store. W0.3 repoints the validator to ALSO evaluate
  `polygon_gex/summary_*.parquet` per-name; cboe series retained as corroboration.
- **A2 — Backfill scope:** IV backfill (W1.1) serves the IV-level family only — ATM-IV30
  series, IV-rank/percentile, term slope, skew SHAPE from recomputed per-strike IV. The
  OI-weighted cross-sectional validators (skew XZZ, ivspread CW) remain accrual-gated to
  ~Dec 2026; backfill cannot rescue them.
- **A3 — Provisional "light verdicts" REJECTED.** No 60-date half-gates. Gates stay at
  pre-registered thresholds; the IV family gets real history via backfill instead, the OI
  family waits. A verdict that can flip at full history is embarrassment risk with no offsetting
  decision value.
- **A4 — Storage plane:** backfill raw cache → `data/massive_options_day/` (gitignored, R2-published
  w/ manifest). Derived IV history → compact per-name parquet in git (~10–20 MB total budget).
  Forward `polygon_gex/chains/` stays git-tracked for now; **tripwire: move to R2 before
  `data/polygon_gex/` AS A WHOLE (chains + growing summaries) crosses 200 MB (~late Aug 2026)**
  — registered as a chip.
- **A5 — IV recompute correctness rules:** European BS inversion restricted to **OTM/near-ATM
  contracts only** (early-exercise premium ≈ 0 there); ATM-IV30 built from the OTM-call/OTM-put
  blend around spot; q from trailing-12M dividend yield where cheap, else q=0 flagged.
  **Validation is NOT "match vendor IV30"** (vendor IVs are American-priced; they differ by
  construction). Acceptance: (a) put-call parity residual distribution sane, (b) term-structure
  smoothness, (c) **cross-sectional Spearman rank-corr ≥ 0.90** of recomputed ATM-IV30 vs vendor
  iv30 — computed PER DAY across the ~355 names (n≈355 per test, statistically sound), averaged
  over the 18 overlap days. This is a cross-NAME test, not an 18-point time series — it does not
  violate doctrine §2.3. Kill: mean rank-corr < 0.80 → restrict universe/label approximate; do
  not ship rank off a series that fails this.
- **A6 — Entry-quality harness joins the board ledger** (`data/us_board_ledger/retro_grades.parquet`),
  reusing the Stage B PIT-stamp pattern. **Stamp sources are pinned:** per-name
  `data/polygon_gex/summary_{SYM}.parquet` keyed by date supplies `gamma_regime`,
  `dist_to_flip_pct`, `magnet_up/down` (wall levels), `iv30`, `put_call_oi_ratio` (columns
  verified present); `data/polygon_gex/chains/{date}.parquet` supplies per-contract `oi` for
  ΔOI slopes (columns: K, T, iv, oi, gamma, delta, volume, spot, asof). Backfill stamps cover
  the 2026-06-15+ window. No new fire-persistence layer. Verdicts accrue forward; the harness
  ships NOW so no fire goes unstamped.
- **A7 — Flow stays on daily.yml.** Do not add S3 pulls to push-render lanes (render is ~67-min
  CPU-bound; cold flat-file downloads don't belong there). Render must not delete committed
  `site/flow/` artifacts — verify, don't assume.
- **A8 — Canonical paths:** stock day-aggs = `data/massive_stock_day/` (live, R2). Options
  day-aggs cache = `data/massive_options_day/` (new). `data/massive_flat/` + `data/massive_flatfiles/`
  are dead strays — do not write to them; W0 may delete the empty dirs.
- **A9 — Ledger write ownership (race prevention):** W1.3 owns ALL new stamp columns on
  `retro_grades.parquet` (creates `iv_rank_252` as always-null placeholder). W1.1/W1.2 NEVER
  touch the ledger. A separate post-merge PR backfills `iv_rank_252` values once both are on
  main. Setup-Species Stage B owns grading logic; stamps use the same nullable schema-union
  pattern and must not alter grading columns. Concurrent writers to the ledger schema are
  forbidden — serialize merges through main.
- **A10 — Ledger primitives are the ONLY gate currency.** Gate criteria may reference:
  `fwd_ret_{5,10,21,63}`, `fwd_mfe_{5,10,21,63}`, `post_cushion_breach` (21d stop-out proxy),
  `terminal_state_clean8_21` (21d clean), `terminal_state_clean15_126` (126d clean),
  `mae_close_excess_spy/sector`. There is NO `stop5`/`clean15@5d`/absolute-MAE primitive. The
  wall study (S-WALL) computes absolute-price wall touches directly from `data/massive_stock_day/`
  raw closes vs stamped wall levels (close-path — understates intraday touches; documented).

---

## §4 Signal & gate registry

_All entry-quality gates speak ONLY in ledger primitives per A10: `post_cushion_breach` (21d
stop-out proxy), `terminal_state_clean8_21` (21d clean), `fwd_ret_{h}` / `fwd_mfe_{h}`.
"Bucket test" = pre-registered conditioned-vs-unconditioned delta with bootstrap CI, n≥30
fires per condition bucket._

| ID | Signal (claim) | Basis | Gate (pre-registered) | Verdict ETA | Kill criterion |
|---|---|---|---|---|---|
| S-IVR | IV-rank as entry filter ("cheap convexity at coil") | Vol-risk-premium lit | harness bucket test (W1.3) on backfilled 252d rank: `post_cushion_breach` + `terminal_state_clean8_21` + `fwd_mfe_21` deltas | fires n≥30/bucket ~Q4-26 | all three CIs include 0 |
| S-DOI | ΔOI 5d persistence (informed accumulation) | Garleanu-Pedersen-Poteshman | cross-sectional rank-IC vs `fwd_ret_5/10`, HAC t>2 @60 dates + harness bucket | ~mid-Sept-26 (IC) | IC ≈ 0 at 60 dates |
| S-WALL | put-wall/magnet-down stop placement | dealer-hedging levels | stop@wall vs fixed −5%: wall-touch rate + `fwd_mfe_21` retention, computed from raw closes vs stamped walls (A10) | n≥100 fires (long tail) | no stop-out reduction @100 |
| S-VOI | Vol>OI fresh-positioning burst + volume z | pre-event volume lit | fastest read: `fwd_ret_5`/`fwd_mfe_5` bucket deltas (mature 5d post-fire); full read `terminal_state_clean8_21` @21d. NO event cross-ref in gate (per-name earnings source doesn't exist in-repo — optional W4 enhancement) | fires n≥30/bucket ~Q4-26 | no `fwd_ret_5`/`fwd_mfe_5` delta @n≥30 |
| S-GEXR | gamma regime → forward realized vol | dealer-gamma lit | existing `validate_gex` MIN_PER_BUCKET=30 (repointed W0.3) | ~Sept-26 | CI includes 0 → display forever |
| S-CWIV | CW call−put IV spread cross-sectional | Cremers-Weinbaum 2010 | existing gate: 120 dates ×15 names, HAC t>2 | ~Dec-26 | not significant → display forever |
| S-XZZ | XZZ skew cross-sectional | Xing-Zhang-Zhao 2010 | existing gate, same shape | ~Dec-26 | same |
| S-COIL2 | price-COILED × gex COILED_UP intersection | mechanism-coherent, untested | forward ledger grade (`terminal_state_clean8_21`, `fwd_mfe_21`) vs COILED-alone | n≥60 joint fires | no incremental grade @60 |
| S-SQZ | squeeze precondition (call-OI concentration × short-gamma × short interest) | squeeze case studies | harness bucket on `fwd_mfe_{10,21}` fatness; SI staleness fixed first (W2.5) | ~Q4-26 | no MFE fatness delta |

Every gate emits a machine-readable `gate.json` in its data dir (`scored:false` until pass),
mirroring `data/gex/gate.json`. Score wiring happens ONLY in W5 and only for passed gates.

---

## §5 Waves

_Model tiers per standing routing: Sonnet builds, Opus designs/reviews, Fable orchestrates.
Each wave = fresh branch off origin/main, PR, squash-merge same-day (conflict-prevention rule)._

### W0 — Stop the bleeding (pipeline repair) — dispatch NOW, 1 Sonnet agent, 1 PR
- **W0.1** ✅ DONE inline 2026-07-03 (orchestrator): all 4 `MASSIVE_S3_*` secrets re-set from
  local `.env`. Agent verifies: trigger/watch next daily run → `site/flow/*.json` +
  `data/options_flow/summary_*.parquet` appear; flow card populates.
- **W0.2** Verify render lanes don't clobber `site/flow/` (A7). If they do, make the no-op
  non-destructive. Do NOT add S3 creds to render lanes.
- **W0.3** Repoint `validate_gex.py` to also evaluate `polygon_gex/summary_*.parquet` per-name
  (384 names) alongside cboe; gate schema unchanged; evidence lines name the store.
- **W0.4** Register polygon_gex + options_flow accrual in `run_status.json` (circuit-breaker
  visibility) + audit tripwire: chains/ freshness ≤ 1 trading day, else collect-gate warning.
- **W0.5** Run `build_options_flow` locally once (creds in `.env`) → commit first
  `site/flow/` payloads incl. `mastermind.json` (un-deadens Mastermind `_flow_row`).
- **W0.6** Storage hygiene: gitignore `data/massive_options_day/`; delete empty stray dirs
  (`data/massive_flat/`, `data/massive_flatfiles/`); chip for chains→R2 at 200 MB.
- **W0.7** UI honesty: `low_confidence` iv_rank gets a visible "n=XXd — building history" caveat
  chip on gex.html; flow-card 404 renders "flow accruing since YYYY-MM-DD", not blank.

### W1 — The two unlocks — dispatch NOW in parallel (2 Opus agents, isolated worktrees)
- **W1.1 IV backfill engine** (Opus — quant-trap-dense): `collectors/massive_options_day.py`
  (S3 day-aggs 2024-07-02→present, universe-filtered via OCC ticker parse, cache per A4/A8) +
  `engine/iv_history.py` (vectorized European-BS inversion per A5, OTM/near-ATM band, EFFR r,
  q handling) + `scripts/backfill_iv_history.py` → `data/iv_history/{SYM}.parquet` (compact:
  date, atm_iv30, iv_rank_252, term_slope, skew_25d, n_contracts, quality flags; total git
  budget ≤ ~20 MB, else move to R2 per A4). **OCC symbology: contract ticker =
  `O:{ROOT}{YYMMDD}{C|P}{strike×1000, 8-digit zero-padded}`; DROP adjusted/non-standard
  contracts (roots with numeric suffix, e.g. `AAPL1` — corporate-action-adjusted deliverables)
  rather than mis-parse them.** NEVER writes `retro_grades.parquet` (A9). Acceptance per A5
  (parity residuals, smoothness, per-day cross-sectional rank-corr ≥ 0.90 averaged over the
  overlap). Include a nightly incremental step in daily.yml.
- **W1.2 IV-rank consumer swap** (same agent, same PR or stacked): `gex_model.iv_rank` reads
  the backfilled 252d series when present (low_confidence path only as fallback); gex.html
  IVR chip gains real percentile; sector/desk consumers pick it up automatically.
- **W1.3 Entry-quality harness** (Opus): `scripts/validate_options_entry.py` + nightly
  options-state stamping onto `retro_grades.parquet` per A6/A9/A10 (new nullable stamp columns:
  `opt_gamma_regime`, `opt_dist_to_flip_pct`, `opt_wall_up`, `opt_wall_down`, `opt_iv30`,
  `opt_iv_rank_252` [always-null until post-W1.1 backfill PR, per A9], `opt_doi_slope_5d`,
  `opt_voi_flag`; sources pinned in A6). Pre-registered claims per §4 in ledger primitives ONLY
  (A10). **daily.yml placement: new step in the render job AFTER the "US Buy Board ledger"
  step (grade_us_board, ~L614), so stamps land on freshly-graded rows; write path
  `data/us_board_ledger/` is already covered by the commit step's `git add data/` — VERIFY
  this before merging (sentinel staging-gap gotcha: a new tracked write path outside the
  commit step's git add ⇒ rebase exit 128).** Backfill stamps for the 2026-06-15+ window from
  chains/summary history. Emits `data/options_entry/gate.json` scored=false. NO verdict claims
  until n clears — the deliverable is the machine, not a result.
- **W1.4 Probe & budget note** (cheap, folded into W0 agent): measure current REST req/day vs
  plan ceiling, `build_polygon_gex` wall-time, day-agg pull time; write numbers into §8.

### W2 — Reliable-signal engines (after W0/W1 merge; Sonnet, 2 PRs)
- **W2.1** ΔOI persistence: `doi_slope_5d` (normalized) per name nightly into summaries +
  cross-sectional rank + IC accrual harness (S-DOI gate).
- **W2.2** Vol>OI burst + volume-z screener with event_calendar cross-ref (S-VOI gate);
  fastest-validating signal in the program.
- **W2.3** Wall-stop study (S-WALL): wall levels at fire date already stamped by W1.3;
  wall-touch and stop-out comparisons computed from `data/massive_stock_day/` raw closes vs
  stamped `opt_wall_down` (per A10 — the ledger's excess-MAE cannot decide wall touches);
  comparator = fixed −5%; close-path limitation documented in output.
- **W2.4** COILED × COILED_UP intersection chip + ledger stamp (S-COIL2). Display + grade only.
- **W2.5** Refresh FINRA short-interest collector (30+ days stale) → S-SQZ precondition screen
  (display-board only until harness verdict).

### W3 — Surfaces & fusion (Sonnet, after W2)
- **W3.1** Sector options aggregation: `site/marketdata/sector_options_agg.json` from
  summaries × basket membership (net-GEX, median IV30, median IV-rank [post-W1.1], P/C OI,
  ΔOI net) + subsectors.js sectorStrip badges (i18n per doctrine §2.7). Suppress
  <40%-coverage sectors. Mapping table: `data/reference/sector_label_map.json` —
  `{"Financial": "us_sector_financials", "Healthcare": "us_sector_health", ...}` (Finviz/
  confluence label → basket id; both spellings verified against membership.json keys).
- **W3.2** Universe expansion (+~120 liquid names: Real Estate/Comm/Materials/Health) — ONLY
  after W1.4 confirms REST headroom; then sector suppression thresholds re-evaluated.
- **W3.3** gex_confirm verdict into the setups strip: CAUTION tag on T3 rows (display-only,
  lower-confidence-only doctrine); wire `rec['gex_confirm']` through rank_setups payload.
- **W3.4** Daily Options Positioning Score composite (external doc's Phase-1 ask): shipped as
  a LABELED DISPLAY composite on gex.html/stock cards only; every component links its gate
  status; composite itself pre-registered as a harness bucket, never scored until it passes.

### W4 — Conditional procurement (gated on W1.3/W2 verdicts)
- **W4.1** OI history (OptionsDX ~$50–100 or Databento statistics schema, est. <$50 for
  2yr×384) — fund ONLY if an OI-conditioned signal shows harness signal.
- **W4.2** Minute-agg historical pull (8–16 GB, R2-planed) for flow-intensity reconstruction —
  fund ONLY if magnitude signals validate and need intraday texture.
- **W4.3** Databento NBBO direction re-calibration — parked; requires a validated use-case that
  specifically needs direction. (Known: tick-rule on bars is 0.41 — dead without tape.)

### W5 — Score integration (gated)
Passed gates → stock_score tilts / species-program registration (options-context species needs
its own pre-registered species entry per the Setup-Species constitution — no shortcut through
the back door). Failed gates → permanent display/confirmer status, documented in §8.

---

## §6 Procurement table (decision-ready, not funded)

| Need | Vendor | Cost | Buys | Trigger |
|---|---|---|---|---|
| OI history 2yr | OptionsDX | ~$50–100 | EOD OI+greeks 2012→ | W1.3 shows OI-signal matters |
| OI history 2yr | Databento statistics | est. <$50 one-off | official OPRA stats | same; confirm quote first |
| Trade+NBBO tape | Databento tcbbo | ~$1.60/20min slice (measured) | direction truth, calibration | validated direction use-case only |
| Real-time flow | Massive Advanced/ThetaData | ~$80–160/mo | latency | product goes live-intraday (not now) |

---

## §7 Risks

- **Overfit at tiny n** — doctrine §2.3 bans sub-30-date backtests; harness buckets carry n and CI.
- **IV recompute bias** (American exercise, q) — bounded by A5 band-restriction + rank-only use +
  parity/smoothness acceptance. The backfilled series is an *approximation product*; labeled as such.
- **Silent accrual loss** — W0.4 makes it circuit-breaker-visible; secrets fixed 2026-07-03.
- **Repo bloat** — A4 storage rules; chains→R2 chip at 200 MB.
- **REST ceiling unknown** — W1.4 probe before any universe growth.
- **Sector aggregates on thin coverage** — suppression below 40% until W3.2.
- **Program collision** — Setup-Species Stage B owns `retro_grades.parquet` schema; W1.3 adds
  nullable stamp columns via the same schema-union pattern (§F9) and must not touch grading
  logic. Coordinate through the species Status log if schema evolves.

---

## §8 Status log

| Date | Event |
|---|---|
| 2026-07-03 | Masterplan authored (Fable). Investigation: 6 dimensions, 8 agents; critique pass applied (10 corrections). |
| 2026-07-03 | **W0.1 DONE**: all 4 MASSIVE_S3_* secrets re-set from local .env (root cause: malformed endpoint since 2026-06-21; 12 days of flow accrual permanently lost). |
| 2026-07-03 | W0 (Sonnet) + W1.1/W1.2 (Opus) + W1.3 (Opus) dispatched in parallel on isolated worktrees. |
| 2026-07-03 | **W0 SHIPPED** (PR w0-options/pipeline-repair): W0.2 verified non-destructive (no-op exits before mkdir; confirmed); W0.3 validate_gex repointed to polygon_gex 384-name store + cboe corroboration (740 building-history evidence lines, scored=false); W0.4 polygon_gex + options_flow_creds in run_status.json + audit_options_accrual.py tripwire; W0.5 flow smoke-run: 353 names built, site/flow/ + data/options_flow/ committed; W0.6 data/massive_options_day/ gitignored + data/massive_flatfiles/ stray dir documented; W0.7 IVR n=XXd building-history chip + flow-card accruing state (EN+ZH, check_title_i18n OK). W1.4 probe: ~993 REST req/day (355 names × avg 1.69 chain pages + 1 spot call; max_pages=40 cap), well below 14K ceiling estimate in F11; chain parquet 4.1 MB/day; summary parquets 12 KB/name avg. W0.1 verification: 2026-07-03 scheduled run (pre-secrets-fix) still showed "Invalid endpoint" → next daily run is first verifying run. |
