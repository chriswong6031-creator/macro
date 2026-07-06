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
| S-VOI | Vol>OI fresh-positioning burst + volume z | pre-event volume lit | fastest read: `fwd_ret_5`/`fwd_mfe_5` bucket deltas (mature 5d post-fire); full read `terminal_state_clean8_21` @21d. NO event cross-ref in gate (per-name earnings source doesn't exist in-repo — optional W4 enhancement). **DOCUMENTED DEGENERATE**: current live-accrual snapshot n_cond=42/n_base=4 (the base=4 bucket has no power; gate is building_history). Registration stands untouched; counts printed honestly by the harness. | fires n≥30/bucket ~Q4-26 | no `fwd_ret_5`/`fwd_mfe_5` delta @n≥30 |
| S-GEXR | gamma regime → forward realized vol | dealer-gamma lit | existing `validate_gex` MIN_PER_BUCKET=30 (repointed W0.3) | ~Sept-26 | CI includes 0 → display forever |
| S-CWIV | CW call−put IV spread cross-sectional | Cremers-Weinbaum 2010 | existing gate: 120 dates ×15 names, HAC t>2 | ~Dec-26 | not significant → display forever |
| S-XZZ | XZZ skew cross-sectional | Xing-Zhang-Zhao 2010 | existing gate, same shape | ~Dec-26 | same |
| S-COIL2 | price-COILED × gex COILED_UP intersection | mechanism-coherent, untested | forward ledger grade (`terminal_state_clean8_21`, `fwd_mfe_21`) vs COILED-alone | n≥60 joint fires | no incremental grade @60 |
| S-SQZ | squeeze precondition (call-OI concentration × short-gamma × short interest) | squeeze case studies | harness bucket on `fwd_mfe_{10,21}` fatness; SI staleness fixed first (W2.5) | ~Q4-26 | no MFE fatness delta |

### W-C additions (registered 2026-07-05, per NW masterplan RO-3/RO-4/RO-12)

> **ERA NOTE (fire-conditioned buckets):** all five buckets below accrue from live fires only
> (2026-07→). No historical fire-date reconstruction exists; until it does, these are
> **single-era live-accrual gates** (era label: 2026→). Era-partition splits per the
> OPTIONS_ALPHA_ERA_PARTITION_AMENDMENT will apply once a second era is defined from
> reconstructed historical fires.

> **H4 ADJACENCY (RUL-2 citation, entry-stack law):** S-VOI2 uses options vol>OI (a fresh
> near-money options contract volume burst). This is **mechanistically distinct** from the equity
> volume-signature H4 that was pre-registered in the durable-bottom framework
> (`research/signal_engine/DURABLE_BOTTOM_FRAMEWORK.md §8 H4 row`, tested 2026-07-01) and
> **FALSIFIED**: H4 volume-dry-up sign-stable NEGATIVE (−4.3pp base 3d), updown_good NEGATIVE
> on fast triggers, obv_div/capit_spike noise — all three H4 sub-hypotheses killed. S-VOI2 is
> not a rescue or variant of H4; it tests *options market* fresh-positioning pressure against
> entry outcomes, not equity volume accumulation. The adjacency is documented here per RUL-2
> so no future agent can claim S-VOI2 as an untested variant of H4.

| ID | Signal (claim) | Basis | Gate (pre-registered) | Verdict ETA | Kill criterion |
|---|---|---|---|---|---|
| S-IVSPREAD-F | Fire-conditioned call−put IV spread: `opt_ivspread_rel>0` vs `<=0` at fire | CW 2010 (fire-conditioned variant); positive ivspread_rel = calls richening vs puts, a bullish-tilt signal at entry | bucket test: condition `opt_ivspread_rel > 0` vs `opt_ivspread_rel <= 0` at fire; A10 primitives: `post_cushion_breach` delta, `terminal_state_clean8_21` rate delta, `fwd_mfe_21` delta; bootstrap 95%-CI; n≥30 per bucket | fires n≥30/bucket ~Q4-26 | all three primitive CIs include 0 |
| S-SKEW_DECEL | Skew high but falling at fire: top cross-sectional tercile AND `opt_skew_5d_chg<0` vs rest | XZZ 2010 extension: high skew = puts rich = bearish tilt; falling skew at fire = tilt fading = de-escalation family | bucket test: condition `opt_skew in top tercile (by date) AND opt_skew_5d_chg < 0` vs all other stamped fires; A10 primitives same shape as S-IVSPREAD-F; tercile computed cross-sectionally per as_of date over the stamped fire universe | fires n≥30/bucket ~Q4-26 | all three primitive CIs include 0 |
| S-TOP_RISK | De-escalation family (caution-only, per RO-3 — MAY ONLY LOWER confidence, never short): `opt_skew_5d_chg > 0 OR opt_ivspread_rel < 0` at fire | puts-richening or spread turning bearish = structural headwind; graded on whether flagged fires show WORSE `post_cushion_breach` + WORSE `terminal_state_clean8_21` rates vs unflagged fires (correct identification of bad entries). **CAUTION-ONLY doctrine**: a positive verdict means the flag correctly de-escalates; it NEVER initiates a negative position. NO single-name negative-gamma leg (gamma_regime structurally_constant per name, audit #29, dropped per RO-3). | bucket test: condition `opt_skew_5d_chg > 0 OR opt_ivspread_rel < 0` vs neither; beneficial direction = HIGHER breach rate in flagged bucket (flag correctly identifies bad entries) + LOWER clean rate in flagged bucket; bootstrap 95%-CI same shape | fires n≥30/bucket ~Q4-26 | flagged bucket does NOT show elevated breach or lower clean @n≥30 (flag useless as caution) |
| S-PIN_RISK | OPEX proximity pin-risk: `opt_opex_days <= 5 AND opt_gamma_regime = 'long' AND min(opt_wall_dist_up_pct, abs(opt_wall_dist_down_pct)) <= 2%` at fire | OPEX pin mechanics: near expiry + long-gamma dealer + price near wall = charm/vanna flows pin price and suppress liftoff; graded on lower `terminal_state_clean8_21` (lower clean liftoff) and lower `fwd_mfe_21` (lower follow-through) in flagged fires | bucket test: condition = pin-risk flag True vs False; beneficial direction for flag = LOWER clean rate + LOWER mfe21 in flagged bucket (flag correctly identifies suppressed entries); bootstrap 95%-CI same shape | fires n≥30/bucket ~Q4-26 | flagged bucket shows no suppression of clean/mfe21 @n≥30 |
| S-VOI2 | Stricter vol>OI burst: near-money contract fresh premium z-score ≥ 2.0 with ≥ 2 qualifying contracts | Stricter threshold over degenerate S-VOI (n_cond=42/n_base=4 means base bucket has 4 non-voi-flag fires — architecturally degenerate). S-VOI2 requires BOTH a volume z-score threshold AND a contract-count floor to filter noise. Exact cut: `opt_voi2_flag = True` iff ≥ 2 near-money contracts each have `today_vol / prior_oi_per_contract >= z_thresh` where `z_thresh` is set such that the expected daily fire rate on the current board universe is 5–15%; document chosen z_thresh in gate.json evidence. S-VOI original registration stands; S-VOI2 is a distinct, non-overlapping registration. | bucket test: condition `opt_voi2_flag True vs False`; A10 primitives `fwd_ret_5`/`fwd_mfe_5` (fast read) + `terminal_state_clean8_21` (full); bootstrap 95%-CI same shape; n≥30 per bucket | fires n≥30/bucket ~Q4-26 | no `fwd_ret_5`/`fwd_mfe_5` delta @n≥30 |

### Enlarged-family BH-FDR statement (W-C, 2026-07-05)

> **Family definition:** all fire-conditioned bucket tests × A10 primitives × the single
> live-accrual era (2026→). Family members as of this registration:
>
> S-IVSPREAD-F × {breach, clean, mfe21} = 3 tests
> S-SKEW_DECEL × {breach, clean, mfe21} = 3 tests
> S-TOP_RISK × {breach, clean} = 2 tests (mfe21 not primary for de-escalation family)
> S-PIN_RISK × {clean, mfe21} = 2 tests (breach is secondary for pin-risk)
> S-VOI2 × {fwd_ret_5, fwd_mfe_5, clean} = 3 tests
> S-IVR × {breach, clean, mfe21} = 3 tests (pre-existing)
> S-DOI × {breach, clean, mfe21} = 3 tests (pre-existing)
> S-VOI × {fwd_ret_5, fwd_mfe_5, clean} = 3 tests (pre-existing; degenerate but registration stands)
>
> **Total family size = 22 tests.** Under Benjamini-Hochberg (BH-FDR) at **α = 0.10**: the
> adjusted significance threshold for the k-th ranked p-value (ranked ascending) is
> p_k ≤ (k/22) × 0.10. At this family size, the effective single-test threshold for the
> most-significant finding is 0.10/22 ≈ 0.0045 (approximately Bonferroni), relaxing to
> 0.10 for the 22nd. **No bucket verdict claims significance without clearing BH-FDR at
> α=0.10 over this full family.** When new buckets are added, the family size increases,
> the statement is amended, and prior registered p-values are re-checked at the new
> threshold. Era splits (once historical fire reconstruction exists) create sub-families
> per era; within each era the same α=0.10 BH-FDR applies over that era's test count.

### OPEX/vanna/charm additions (registered 2026-07-06, Fable adjudication of Codex study)

> Provenance: Codex OPEX/vanna/charm study adjudicated in
> `research/OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md` (Opus adversarial review + Fable
> robustness addendum: vol/size-residualized partial ICs + real ETF slice). Only families that
> survived adjudication are registered here. Killed at adjudication, for the record
> (RUL-OVC-2/4/5/6 + §7 kill list): signed_charm_pressure (vol proxy, partial IC ≈ 0),
> Greek-intensity narratives (charm_intensity sign-flips under control), S-POST-OPEX-RELEASE
> (Era3-only, ~4 roots/date), S-QUAD-ROLL (sign-unstable across eras), S-INDEX-PIN (ETF pin
> suppression real but NOT OPEX-specific — non-OPEX placebo ≥ pin; folds into S-PIN_RISK
> grading as a root-class stratification note, not a new bucket), air-pocket state (F-16,
> 1 weak era).

> **ERA NOTE:** live-accrual single era (2026→), same as the W-C additions. The historical
> evidence base (2017–2026 ThetaData panel, three eras, all same sign) is *basis*, not gate
> history — the gate accrues from live fires only.

> **SIGN NOTE (audit #29):** the flag's construction uses signed net vanna under the
> long-call/short-put dealer convention. The convention is an assumption; the historical
> association is a measured property of the state *as constructed* and held in all three eras.
> Interpretation ("dealer relief flow") inherits the assumption; the gate tests the flag, not
> the narrative.

| ID | Signal (claim) | Basis | Gate (pre-registered) | Verdict ETA | Kill criterion |
|---|---|---|---|---|---|
| S-VANNA-RELIEF | Vanna-relief vol compression at fire: `opt_vanna_relief = (iv30_5d_chg < 0) AND (vanna_hedge_5d in top cross-sectional tercile per as_of)`, where `vanna_hedge_5d = −net_vex × iv30_5d_chg`; claim = flagged fires are more holdable (vol compresses post-fire) | Codex study Family C, adjudicated 2026-07-06: 5d-RV spread −2.4/−4.3/−3.8pp across Era1/2/3, t = −7.3..−7.7, 27k–40k cond-obs, PIT-clean; **strengthened by robustness addendum** (partial IC stronger than raw in all eras: −0.053/−0.049/−0.069; re-confirmed inside ETF slice); honest null on rel-ret (holdability state, NOT entry alpha). Interpretation caveat on record: ETF slice shows the opposite-sign drag state also compresses — operative variable may be \|vanna\|×\|dIV\| magnitude; gate tests the flag as constructed | bucket test: `opt_vanna_relief` True vs False; A10 primitives: **primary** `post_cushion_breach` delta (beneficial = LOWER breach in flagged bucket); **secondary** `terminal_state_clean8_21` + `fwd_mfe_21` deltas reported honestly (compression may trim both tails — no pre-judged direction); bootstrap 95%-CI; n≥30/bucket. Stamp col `opt_vanna_relief` pending W-OVC harness build (same registered-before-stamped pattern as S-PIN_RISK at W-C) | fires n≥30/bucket, earliest ~Q1-27 (stamp ships in W-OVC first) | breach-delta CI includes 0 @n≥30 (flag carries no holdability information) |
| S-FRONT-CHARM | Front-expiry charm concentration = expiry-clock vol-risk caution at fire: `opt_front7_charm_share in top cross-sectional tercile per as_of` flags fires facing elevated near-term realized vol (wider stops / worse holdability) | Codex study Family A, adjudicated 2026-07-06 **with vol/size-residualized robustness**: partial IC vs fwd 5d RV = +0.059/+0.077/+0.130 by era (t up to 17.8) after controlling trailing 20d RV + log OI notional — sign-stable all eras, BH-clean; ~⅔ of raw headline IC (0.335) was vol-persistence confound and is NOT claimed. Root-class caveat mandatory (ETF-slice sign instability by era); board fires are single-name-dominated | bucket test: `opt_front7_charm_share` top tercile (by as_of over stamped fire universe) vs rest; A10 primitives: **primary** `post_cushion_breach` delta (beneficial = HIGHER breach in flagged bucket → flag correctly identifies vol-exposed entries; caution-only per RO-3, may only lower conviction); **secondary** `terminal_state_clean8_21` + `fwd_mfe_21` deltas reported honestly; bootstrap 95%-CI; n≥30/bucket. Stamp col `opt_front7_charm_share` pending W-OVC; `opt_root_class` stamped alongside and reported per-class once n allows | fires n≥30/bucket, earliest ~Q1-27 (stamp ships in W-OVC first) | breach-delta CI includes 0 @n≥30 (flag carries no vol-exposure information at fire) |

### Amended-family BH-FDR statement (OVC, 2026-07-06)

> S-VANNA-RELIEF × {breach, clean, mfe21} = 3 tests and S-FRONT-CHARM × {breach, clean, mfe21}
> = 3 tests added to the W-C family of 22.
> **Total family size = 28 tests**; BH-FDR α = 0.10 thresholds now p_k ≤ (k/28) × 0.10
> (most-significant single-test threshold ≈ 0.0036). Per the W-C statement's amendment clause,
> prior registered p-values were re-checked: **all existing buckets are `building_history`
> with no claimed p-values, so no re-checks are triggered** by this enlargement.

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
| 2026-07-04 | **P0.5 era-partition amendment RATIFIED by Fable** (drafted + adjudicated same-day): see `research/OPTIONS_ALPHA_ERA_PARTITION_AMENDMENT.md` — registers FIRST era partitions per roadmap R2 (verified §4 had none): S-CWIV/S-XZZ/S-GEXR (greeks-dependent) = 2017-19 / 2020-22 / 2023→; S-DOI (OI-only) = 2012-15 / 2016-19 / 2020-22 / 2023→ (greeks boundary = vendor F-A, greeks rows=0 for SPY 2012-2016). Registers a first partition BEFORE any gate harness runs (does not revise a registered one). Per-era results + post-publication-decay commentary mandatory; a claim alive only pre-2016 is dead. |
| 2026-07-03 | **W1.3 SHIPPED** (entry-quality harness — the MACHINE, not a result): `engine/options_stamp.py` (PIT options-state stamp, 8 nullable `opt_*` cols; `opt_iv_rank_252` always-null per A9), `scripts/stamp_options_state.py` (nightly + backfill pass mirroring `_backfill_regime_stamps` schema-union / no-overwrite), `scripts/validate_options_entry.py` → `data/options_entry/gate.json` (`scored:false`; S-IVR/S-DOI/S-WALL/S-VOI in ledger primitives only, A10; bootstrap-CI bucket deltas; n≥30 before any verdict). Wired into daily.yml after the "US Buy Board ledger" step (`git add data/` covers both write paths). Backfilled the 2026-06-15+ window: **47/950 ledger rows stamped** (only ~384 names have polygon_gex coverage; the rest stamp null and retry as coverage grows). Bucket-n snapshot (per doctrine §2.3 — counts only, NO effect-size claim): S-IVR n_cond=0/n_base=0 (awaits post-W1.1 iv_rank backfill PR); S-DOI n_cond=0/n_base=0 (fires' names have chain-coverage gaps in their 6-day ΔOI window → null slope, PIT-honest); S-VOI n_cond=42/n_base=4; S-VOI-fast n_cond=42/n_base=4; S-WALL 45 eligible fires (0 priced locally — `massive_stock_day` is R2-backed, present in CI). Every bucket < 30 → status `building_history`, no verdict. 11 new tests incl. adversarial PIT no-lookahead (future-OI-spike leak test; discrimination proven: correct=0.0 vs leaked=0.81) + synthetic n≥30 → verdict. |
| 2026-07-05 | **W-C SHIPPED** (prereg + harness extension, per NW-Entry masterplan W-C row): §4 registry amended with S-IVSPREAD-F, S-SKEW_DECEL, S-TOP_RISK, S-PIN_RISK, S-VOI2 (five new buckets, registered BEFORE harness runs them per era-partition-amendment precedent); S-VOI documented degenerate (n_cond=42/n_base=4); H4 adjacency citation (RUL-2 law; S-VOI2 is mechanistically distinct from FALSIFIED equity H4); enlarged-family BH-FDR α=0.10 statement (family=22 tests, arithmetic explicit); era note (single-era live-accrual 2026→ until historical fire reconstruction exists). `engine/options_stamp.py` + `scripts/stamp_options_state.py` extended with 7 new stamp cols (opt_ivspread_rel, opt_skew, opt_skew_5d_chg, opt_opex_days, opt_pin_risk, opt_wall_dist_up_pct, opt_wall_dist_down_pct); PIT-disciplined readers from `data/options_skew/snapshots.parquet` + `data/options_ivspread/snapshots.parquet` + `engine/opex.py`; coverage: skew 13d/~356 tickers, ivspread 6d/~344 tickers. `scripts/validate_options_entry.py` extended with 5 new buckets (all `building_history`, n<30); gate.json per-family status + FDR statement + coverage percentages added. `data/experiments/registry_seed.json` 2 new accrual entries (options-entry-gate-maturation come_back 2026-10-15; skew-ivspread-validation-clock come_back 2026-12-15). Tests: PIT no-lookahead for skew/ivspread stamps (mirror existing future-OI-spike leak test pattern), schema-union non-destructiveness on ledger copy, synthetic n≥30 → new-bucket verdict machinery. *(Note: `engine/options_flow.py` R6 comment fix was already landed by a prior PR — not part of this wave's diff.)* |
| 2026-07-06 | **OVC ADJUDICATION** (Codex OPEX/vanna/charm study, 30 findings): ported 4 artifacts from ephemeral Codex worktree; Opus adversarial review found 2 fatal gaps (no vol/size control on headline ICs; F-15/16/17/20's "ETF-only slice" had NO artifact); Fable robustness addendum (`scripts/research/options_opex_vanna_charm_robustness.py`) run against the same 174-root ThetaData store: trailing-RV20 confound IC=0.50-0.59 (huge); front-week charm/gamma concentration SURVIVES residualization (partial IC 0.05-0.13, sign-stable all eras) → **S-FRONT-CHARM registered**; signed_charm_pressure REFUTED (partial ≈0); charm_intensity sign-FLIPS under control ("depth cushions" = size artifact); vanna-relief STRENGTHENED (partial > raw, ETF-slice re-confirmed) → **S-VANNA-RELIEF registered**; real ETF slice: pin suppression confirmed 3/3 eras BUT non-OPEX placebo ≥ pin (not an expiry mechanism; supportive prior for S-PIN_RISK root-class stratification); air-pocket dead. Family 22→28 tests. Full rulings RUL-OVC-1..8 + kill list + W-OVC build docket in `research/OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md`; experiments-tracker come-back 2026-07-20 (W-OVC dispatch check). |
| 2026-07-05 | **W-C FIX-ROUND** (adversarial review findings addressed): (1) BLOCKER retry-gate: `STAMP_COVERAGE_COLS` introduced in `engine/options_stamp.py` (excludes `opt_opex_days`); `stamp_ledger` retry gate now keys on `STAMP_COVERAGE_COLS` so calendar-only rows remain retryable when GEX/skew/ivspread coverage arrives; the committed parquet needed NO regeneration — the code change alone makes the pre-existing 903 opex-only rows retryable again (they fill on a future nightly once GEX/skew/ivspread coverage arrives; verified 903 retryable / 0 of 47 GEX-stamped rows misclassified). (2) MAJOR pre-reg mismatch: `_verdict_for_caution_test` split into `_verdict_for_top_risk` (primitives {breach, clean}) and `_verdict_for_pin_risk` (primitives {clean, mfe21}; breach excluded per §4 S-PIN_RISK registration). (3) MINOR AND vs OR: both caution-verdict functions now require both conditions (conjunction) matching §4 registration wording. (4) MINOR docs: W-C status log corrected (options_flow.py fix was upstream, not this PR). |
