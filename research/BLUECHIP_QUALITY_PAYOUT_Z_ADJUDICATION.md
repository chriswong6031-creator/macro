# Blue-chip quality/payout z adjudication — why MCD reads −2.246 and KO's dividends read $0

**Status: FILED FOR RATIFICATION — no engine change ships with this doc.**
Trigger: PR #4677 observation (MCD quality z −2.246 with book equity −$1.79B; KO quality
−1.291 with equity +$32.2B; SBUX payout −1.024; MCD payout −0.071 despite decades of
dividends+buybacks) → archetype v2 labels MCD `cyclical`, and the Signal Episode Atlas
conditions per-name signal base rates on those cohorts. Audit chip `task_321eb6b9`.
Evidence + repro: `research/factor_leg_audit/` (exact-replication sim, EDGAR frame probes,
before/after panels). All numbers below are measured on the live caches
(`data/edgar/fundamentals.parquet` fy2025, factors as_of 2026-07-31); the BEFORE panel
reproduces shipped `site/factordata/factors.json` to the third decimal.

---

## §0 Decisions for the operator

| # | Decision | Recommendation | Moves ranked surfaces? |
|---|---|---|---|
| D1 | **Input repair** — XBRL fallback ladder in `collectors/edgar.py` (dividends → `PaymentsOfDividends` → `DividendsCommonStockCash`; debt_lt → `LongTermDebt`; equity → incl-NCI variant) | **RATIFY.** Pure measurement repair, construction untouched. Recovers true dividends for 397 names incl. KO/SBUX/PG/AAPL/JNJ/BAC. | YES — payout/quality z feed `composite_rank` (audit #25). Ratifying D1 = ratifying that movement as a data correction. Queue the deep-panel backfill + IC scorecard re-run in the same lane. |
| D2 | **Construction repair** — variant AB2: ratio-level winsorization [p1,p99] before z on quality/payout legs; ROE leg → ROA (`ni/assets`); quality composite requires ≥2 legs | **RATIFY AS PROMOTION CANDIDATE**, gated: pre-registered scorecard re-run under the new construction before the rank composite consumes it. AB1 (guarded ROE) is the fallback variant if ROA is rejected. | YES — same gate as D1, stricter (definitions change, measured ICs invalidated until re-run). |
| D3 | **Archetype gate calibration** — `dividend_defensive` needs pay z ≥ 0.5 vs the broad 1,500-name universe; only 7–9 of the top-100 caps clear it under ANY panel. Even after D1+D2, MCD stays `cyclical`. | **OPEN — options in §6, no recommendation shipped.** Changing gates relabels tens of S&P100 names; needs its own ratification. | Indirect (labels → Atlas cohorts). |
| D4 | **Atlas cohort hygiene** — rebuild `data/archetypes/history.parquet` + refresh cohort caveats once D1/D2 land; stamp the construction era on rebuilt rows | RATIFY (mechanical, display/analysis tier). | No. |

DNR check (2026-08-06): no registry row kills or constrains this construction
(`DNR:KILL-SHOCK-SHELTER-MAP` is about a shock→archetype *shelter map* feed, not the
classifier; `DNR:LAW-FAMILY-CLOSURE` is respected — nothing here closes a factor family;
`DNR:LAW-REVERSION-RULER` n/a). No new kill/law rows minted — this is a repair proposal,
not a kill. No open PR lane touches `engine/equity_factors.py` or the collector FLOW map
(checked `docs/ACTIVE_BUILD_MAP.md` 2026-08-06; #4532 wires archetype into ledger columns,
#4640 is SEC submission-grammar — no collision).

---

## §1 As-built construction (what the z's actually are)

`engine/equity_factors.py` (live path, broad S&P-1500 universe, winsor cap 3.0):

- **quality** = mean of available legs among
  `ROE = ni / equity·1{equity>0}` , `−accruals = −(ni−cfo)/avg_assets` ,
  `−leverage = −debt_lt/assets` — each `_winsor_z`'d (z on the raw ratio, THEN clip ±3),
  then the composite is **re-z'd cross-sectionally** (second pass, `equity_factors.py:570`).
- **payout** = `(dividends.fillna(0) + repurchases.fillna(0)) / mktcap`, NaN only when
  BOTH legs are NaN, `_winsor_z`'d twice (same second pass).
- Inputs are single XBRL concepts (`collectors/edgar.py:34-53`):
  `dividends ← PaymentsOfDividendsCommonStock`, `debt_lt ← LongTermDebtNoncurrent`,
  `equity ← StockholdersEquity`.
- Consumers: factors.html table/leaderboards + stock-page radar (display); the
  **rank-facing `composite_rank`** = IC-weighted mean of scorecard-passing legs
  `['value','quality','profitability','payout']` (audit #25; deep scorecard ICs 0.0184 /
  0.0042 / 0.0141 / **0.0247 — payout is the lone FDR survivor**); the **archetype v2
  cascade** (`engine/stock_fundamentals.py:1394`) gates `cyclical` on
  `not(pay≥0.5 ∧ low_vol≥0.3) ∧ not(q≥0.6)`, `dividend_defensive` on `pay≥0.5`,
  `quality_compounder` on `q≥0.5`; archetype keys are stamped onto every track-record row
  and aggregated into Atlas cohort priors (`data/archetypes/history.parquet`).

## §2 Measured mechanisms

**M1 — The dividends tag misses 61% of the universe, and `fillna(0)` silently zeroes
them.** `PaymentsOfDividendsCommonStock` covers 605/1,551 names. 946 are NaN; **659 of
those have repurchases present, so the pair-guard passes and their dividends enter the
yield as literal zero.** Measured truths (EDGAR frames, CY2025): KO pays **$8.779B**
(recorded 0 → yield 0.198% vs true 2.53%), SBUX **$2.771B** (recorded 0 → 0.00% vs
2.32%), PG **$9.872B**, AAPL **$15.421B**, BAC also zeroed; JNJ pays **$11.8B** but tags
it ONLY as `DividendsCommonStockCash` (declared, equity-statement concept — no
payments-of-dividends fact at all). Direct z damage: KO payout −0.974, SBUX −1.024,
JNJ −0.778 — the largest dividend payers in America recorded as paying ~nothing, on the
exact factor whose deep-scorecard seat is the lone FDR survivor.

**M2 — Negative book equity deletes the ROE leg, and the mean-of-available-legs silently
redefines quality.** `equity.where(equity>0)` NaNs ROE for 65 names — precisely the
buyback champions (MCD equity −$1.79B, SBUX −$8.39B, plus MO/PM/ABBV-class balance
sheets). MCD's quality then = mean(−accr −0.19, −lev −2.10) = −1.147 raw; the second-pass
re-z divides by the composite's sd 0.504 → **−2.246. MCD's "quality" is arithmetically its
leverage z doubled**, with the leg that would carry its 46% operating margin deleted.
108 names ship a **1-leg** "composite"; 39 more ship 0-leg NaN.

**M3 — The ROE z-scale is destroyed by tiny-equity survivors.** Raw ROE cross-section:
p10 −0.026, p50 0.114, p90 0.338 — but sd **1.164** (near-zero-equity names print ROE in
the hundreds of percent before the z-clip; `_winsor_z` clips AFTER computing mean/sd on
the raw ratio, so the outliers inflate sd ~6× and THEN get clipped). Result: KO's genuine
40.7% ROE scores z **+0.20** — statistically indistinguishable from mediocrity. This is
the core statistical defect: winsorize-the-z is not winsorize-the-ratio.

**M4 — The leverage leg is a single-tag lottery.** `LongTermDebtNoncurrent` is missing
for 792/1,551 (51%): half the universe **skips the leverage penalty entirely**. HD carries
$49.4B of LT debt under the sibling tag `LongTermDebt` → no penalty, quality +0.44; MCD
files the exact tag → −2.10 leg. Same economic position, opposite factor treatment,
decided by tag choice. (KO's LT debt is invisible under BOTH tags — dimensioned facts
don't reach the frames API — so KO additionally skips the leg.)

**M5 — Second-pass amplification.** The raw quality composite has sd 0.504 (mean of 2–3
unit-variance legs), so the re-z roughly doubles whatever survives leg deletion. For 2-leg
names dominated by one extreme leg (M2), that extreme is amplified, not diluted.

**M6 — Payout tail pollution (secondary, separate root cause).** The payout z denominator
distribution (mean 4.17%, sd 5.38%) is fattened by small caps repurchasing large fractions
of collapsed market caps — topped by **BKNG at "105.4%" which is a mktcap bug, not a
yield**: `data/sp500_heatmap/reference.parquet` has shares non-null for **0/503** rows, so
`_reconcile_shares` is a dead guard and BKNG ships pre-25:1-split EDGAR shares (mktcap
$6.1bn vs ~$180bn). Filed separately as chip `task_814c0c73`. Against this inflated scale,
MCD's genuine 3.73% net yield sits at the 45.6th percentile of the universe (63rd of the
top-100) → **z −0.071 is an honest relative read of a correct ratio** — the "implausible"
MCD payout z is expectation-vs-universe, not a data hole (MCD is one of the few watch
names whose dividends tag actually works).

**M7 — KO's accruals leg is real, not broken.** (ni−cfo)/avg_assets = +5.6% = 89.6th
percentile worst, driven by the fairlife earnout + tax-litigation deposits flowing through
FY2025 CFO. That is the Sloan construction working as designed on a one-off year; no
remedy proposed. Post-repair KO quality lands ≈ −0.5, not +1 — and that is the honest
answer.

## §3 Blast radius by tier

| Surface | Tier | Effect of D1/D2 |
|---|---|---|
| factors.html table, leaderboards, stock-page radar | display | z's move; caveat copy already admits sparse dividends/buybacks — should be updated to name the repair |
| `composite_rank` (board ordering, audit #25) | **authority** | payout (IC 0.0247, FDR seat) and quality (0.0042) re-weight through changed z's → **rank movement; the reason this doc files instead of ships** |
| deep IC scorecard (`data/edgar/ic_scorecard.json`) | authority-input | measured on the SAME single-tag PIT panel → same holes historically; ICs are stale the moment inputs change → re-run required (offline, off render path) |
| archetype v2 label | display/analysis | gates re-evaluate; see §5 for what actually flips |
| Atlas cohort priors (track-record archetype stamps, `archetypes/history.parquet`) | analysis (cohort priors only, never training labels) | contaminated cells (`cyclical` ∋ defensives; compounder cohorts under-populated) persist until D1/D2 + D4 rebuild |

## §4 Remedies + before/after evidence (S&P100 = top-100 mktcap; full panels in `research/factor_leg_audit/evidence.json`)

**A — input repair (D1).** Fallback ladder, filling NaN only (never overriding the
primary tag): dividends `PaymentsOfDividendsCommonStock → PaymentsOfDividends (+363
names) → DividendsCommonStockCash (+34; declared≈paid for stable payers — semantic caveat
documented)`; debt_lt `→ LongTermDebt (+314; includes current maturities for some filers —
acceptable and arguably more correct for a leverage ratio)`; equity `→
StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest (+71 of 72
missing)`. Cost: ~6 extra frame calls in the weekly cached collector — nothing on the
render budget.

**AB1 — guards (D2 fallback variant).** A + winsorize each RAW ratio at [p1,p99] before
z; ROE denominator guard (`equity ≥ 2% of assets`, else leg NaN); quality needs ≥2 legs.

**AB2 — substitution (D2 recommended variant).** As AB1 but the ROE leg is **replaced by
ROA** (`ni/assets`). Rationale: the quality composite already carries a separate
−leverage leg, so ROE double-counts capital structure with inconsistent sign (rewards
leverage in ROE, penalizes it in −lev — HD gets +1.0 of ROE flattery then dodges the debt
penalty via M4); ROA + −leverage is a clean profitability/balance-sheet decomposition, is
defined for negative-equity names structurally (no threshold to tune), and its raw
distribution needs no pathological-denominator repair.

Watch names (quality z | payout z), BEFORE → A → AB1 → AB2:

| | quality | payout |
|---|---|---|
| MCD | −2.25 → −2.23 → −2.20 → **−0.64** | −0.07 → −0.17 → −0.17 → −0.17 |
| KO | −1.29 → −1.34 → **−0.50** → −0.66 | −0.97 → **−0.47** → −0.49 → −0.49 |
| SBUX | −0.28 → −0.25 → −0.21 → −0.10 | −1.02 → **−0.52** → −0.55 → −0.55 |
| JNJ | −0.21 → −0.24 → +0.15 → **+0.31** | −0.78 → **−0.36** → −0.37 → −0.37 |
| PG | −0.08 → +0.01 → +0.35 → **+0.50** | −0.53 → **+0.11** → +0.14 → +0.14 |
| AAPL | +0.42 → +0.42 → +1.59 → **+1.49** | −0.51 → −0.52 → −0.54 → −0.54 |
| HD | +0.44 → −0.36 → +0.94 → **−0.21** | −0.32 → −0.41 → −0.43 → −0.43 |

Leg receipts for the headline case: MCD BEFORE = {ROE NaN, −accr −0.19, −lev −2.10,
2 legs} → q −2.246; MCD AB2 = {ROA z +1.34, −accr −0.23, −lev −2.15, 3 legs} → q −0.641.
The −1.6σ repair is entirely the restored profitability leg; the leverage penalty stays —
MCD genuinely runs debt_lt/assets 0.672 vs universe median 0.247.

S&P100 distribution (quality): BEFORE mean −0.03/sd 0.81/min −2.25 → AB2 mean +0.19/sd
0.85/min −2.00. Payout: BEFORE mean −0.39 → −0.35 (the megacap payout z stays
structurally below the broad-universe mean — see D3). Coverage (full universe): payout
1,159 → 1,258 names; 1-leg quality composites 108 → 69, and those 69 now ship NaN
instead of a renamed single leg (min-2-legs).

Archetype-gate crossings on the S&P100 (AB2 vs BEFORE): q≥0.5: 22 → 32 (16 gained — MO,
PM, PLTR, ANET, GOOGL, NVDA, VRTX, ISRG, AAPL class — 6 lost, ABBV −2.08 the largest
demotion: $3B book equity carrying $135B assets, ROA ~4%, heavy debt — the substitution
reads it correctly); q≥0.6: 20 → 28; pay≥0.5: 7 → 9. Sanity: the movers are exactly the
negative/thin-equity + zeroed-dividend names the mechanisms predict.

## §5 What the repair does NOT do (honest nulls)

- **MCD remains `cyclical` under every panel** (sector bucket: q −0.64 < 0.6, pay −0.17
  < 0.5). The z repair removes the false −2.25 but a broad-universe cross-sectional gate
  still cannot see a leveraged franchise compounder whose book assets understate the
  economics. Fixing the SCORE ≠ fixing the LABEL → D3.
- KO stays `mixed` (accruals genuinely bad this FY — M7). SBUX stays `cyclical` (sector;
  quality ≈ −0.1, ROA depressed by FY2025 restructuring — honest).
- AAPL and PG DO flip to `quality_compounder` under AB1/AB2 (PG only under AB2); HD's
  BEFORE `cyclical` label was accidentally right and stays (its +0.44 quality was M4 tag
  luck; AB2 reads the debt).
- The payout small-cap tail is only partially tamed by [p1,p99] (BKNG's fake 105% is a
  mktcap bug → chip `task_814c0c73`); megacap payout z's stay below the broad-universe
  mean because the universe's tail is real.

## §6 D3 — gate options (filed, not recommended)

The factor-z buckets 9–13 are the ORIGINAL v1 cross-sectional buckets, deliberately
preserved under v2. Under ANY honest z panel, `dividend_defensive` (pay≥0.5 ∧ lv≥0.4 ∧
lb≥0.3) admits ≤9 of the top-100 caps, and the `cyclical` guard (pay≥0.5 ∧ lv≥0.3) is
nearly unreachable for megacaps — so Atlas "cyclical" cohorts will keep absorbing
defensive compounders. Options, all requiring their own ratification + archetype-history
era stamp: (a) accept as-is (cohort semantics = "cyclical-sector, not extreme on broad-z
overlays"); (b) percentile-rank gates (pay ≥ p70 of universe) — robust to tails, still
universe-relative; (c) **anchored absolute thresholds** (e.g. defensive overlay = total
yield ≥ 2.5% ∧ β < 0.8), matching the v2 doctrine that anchored buckets never gate on
cross-sectional z; (d) size-segment-relative z (S&P500-only cross-section for megacap
pages). (c) is the doctrine-consistent shape but changes the most labels; measure before
choosing.

## §7 Sequencing per the epistemics law (promotion gauntlet)

1. **Phase 1 (on D1 ratification):** ship the collector fallback ladder + snapshot
   rebuild; update the factors-page caveat copy; kick the **offline** PIT-panel backfill
   (`fetch_panel` gains the same ladder; full re-pull off render path) and re-run
   `scripts/factor_ic_scorecard.py --deep` so audit-#25 weights are re-derived on
   repaired inputs. Until that re-run lands, the live rank composite runs old weights on
   repaired z's — ratifying D1 accepts that transient explicitly.
2. **Phase 2 (on D2 ratification):** flip the construction to AB2 in ONE PR that also
   commits the re-run scorecard under the new definitions (pre-registered here: ratio
   winsor [p1,p99]; ROA leg; min-2-legs; payout unchanged except input repair + ratio
   winsor). If any current rank seat loses its positive-IC/FDR status under the honest
   re-measurement, the seat drops per the existing audit-#25 firewall — that is the
   gauntlet doing its job, not a regression.
3. **Phase 3 (D4):** rebuild `data/archetypes/history.parquet` via
   `scripts/build_archetype_history.py` with a construction-era stamp on rebuilt rows
   (`basis` gains a suffix or a new `factor_construction` column — pick at build time);
   refresh the Atlas cohort caveat (memory `archetype-coverage-for-atlas-cohorts`) and
   re-read cohort cells that mixed defensives into `cyclical`.
4. D3 runs as its own adjudication if taken up.

## §8 Repro

- `research/factor_leg_audit/sim_fixes.py` — exact-replication sim (BEFORE validates
  against shipped factors.json before simulating; asserts on MCD/KO/SBUX).
- `research/factor_leg_audit/tag_probe.json` — frame coverage probe results.
- `research/factor_leg_audit/fallback_frames_2026-08-06.json` — frozen CY2025 fallback
  frames (per-CIK values) used by the sim.
- `research/factor_leg_audit/evidence.json` — full S&P100 before/after z panels + watch
  bucket outcomes.
