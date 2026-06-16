# Unified Stock Conviction Profile — Design Spec (v2)

Status: APPROVED-FOR-BUILD. v2 incorporates a 3-lens adversarial critique
(statistical rigor · architecture/feasibility · product honesty). Supersedes v1.

## 0. What changed from v1 (why v2)

The critique surfaced one fatal flaw and a cluster of honesty/feasibility fixes:

- **Local data has no power to validate a *shipped rank*.** Only the 313-day
  shallow cache is present; the deep survivorship + PIT-membership panel that
  `top_picks_phase0` needs is absent (regenerated in CI only). So a local Phase-0
  cannot honestly gate a rank — it would rubber-stamp noise.
- **The composite was effectively already tested** (`top_picks_phase0`
  CONVICTION_LEGS) → **NEUTRAL**; the US residual-alpha baseline itself fails
  FDR/DSR (21d IC +0.010, HAC t 0.82, L/S Sharpe −0.16). Realistic prior: the
  Conviction composite will NOT beat the baseline. Plan for context-only.
- **HK has a formally KILLED stock-selection edge** (research/CHINA_HK_STOCK_SIGNALS
  Phase-3: "KILL the residual-alpha leg… HK lacks idiosyncratic stock-specific
  signal"). A ranked HK "conviction BUY board" is a culture violation.
- **Cross-market identical 0–100 chrome is dishonest** (a "Conviction 82" means
  a weak-edge thing in the US and a no-edge thing in HK).
- **"Same JSON block" stops *literal* disagreement but not the *semantic* one** —
  it would just move "BUY vs EXIT" into one card.

⇒ The system is reframed from a **score** to a **Profile** (transparent 4-axis
decomposition), the shipped **rank stays each market's validated baseline** unless
a deep-CI gate says otherwise, HK is an **exposure/RS screen (never picks)**, and
the cycle state becomes a **verb modifier**, not a side note.

## 1. Goal (restated honestly)

ONE engine (`engine/stock_score.py`) that, per ticker per market, emits a
**Conviction Profile**: 4 transparent sub-axes + a roll-up score + an honest
verdict verb + provenance. It:

1. Lifts each market's **Standout** bench to a real **80–120 names** — via a
   *wider universe ranked by the validated leg*, not a new unproven score (§3).
2. Is the **single block** both the dashboard card AND the detail-page hero read,
   with cycle state as a **hard verb-modifier** so the two never contradict (§6).
3. Decomposes into the user's mental model: *go-higher · entry · tailwind ·
   business quality* (§2), shown as a radar/bars (impressive **because**
   transparent, not because of fake precision).
4. Fills the dead `Master verdict → Phase 4` placeholder on the US stock page and
   the same role on CN/HK/CA detail pages (implements `STOCK_FUNDAMENTALS_PLAN.md`
   §6–§7 dual-axis verdict), and fixes the obsolete `Next earnings → Phase 2`
   chip (wire to real `d.earnings`).
5. Is backtested by the validated harness (deep-CI), **default display-only**,
   with a pre-committed non-monotone contingency (§7).

## 2. The four axes (a Profile, not a single number)

Each axis is computed as a **sector-neutral winsor-z** (reuse
`top_picks_phase0._sn_z`) then mapped to 0–100 for DISPLAY only. The **ranking +
validation always operate in z / percentile space** — the 0–100 logistic is a
monotone display skin computed *after* the rank is fixed, never fed into IC /
Sharpe / calibration, and never compared across markets as if equal.

**Leakage is handled at the composite level, not per axis.** Axes A/B/C all touch
price momentum/reversal (rs* derive from the same returns as `alpha`; the `entry`
tag is a function of `alpha`+`rev_pctile`; CN reversal = the same 21d return as
B's pullback, opposite sign). So: build every sub-leg as an `_sn_z` column,
assemble ONE matrix, run `engine.factor_orthogonal.orthogonalize` across **all**
axis inputs, report `overlap_diagnostics` (VIF, mean|corr| raw vs orth) in the
Phase-0 report, set any decision weight on the **orthogonal** blend, map back for
the display radar.

### Axis A — Selection / "will it go higher"
- US/CA: `residual_alpha.alpha` (sector-neutral residual momentum) — the validated
  context leg + the SHIPPED rank key.
- CN: **reversal context** (`china_reversal.rev_z`) — but note the validated CN
  edge is the *unconfirmed deepest dip*; the Profile shows reversal as context and
  the CN board keeps ranking by its existing validated reversal-setup, NOT a
  4-axis blend that would down-rank the deep-dip names (critique product #5).
- HK: plain total-return RS only, labeled "screen, not a validated pick."
- rs3m/6m/12m are NOT separate inputs (they derive from `alpha`) — display only.

### Axis B — Entry / "how good is the entry" (and the cycle MODIFIER)
- `cycles.analyze` `entry.urgency` (now/imminent good; exit/avoid bad) + `state`.
- `residual_alpha._entry` pullback(+)/extended(−); `off_52w_high_pct` hump (mild
  pullback = sweet spot; deep crash and brand-new-high both penalized);
  `rsi14` band; `extension.grade` — **`parabolic` (ext_z>2) is a PENALTY only,
  never a positive contributor** (validated radioactive cohort).
- **HARD MODIFIER:** if `ladder.state` ∈ {downtrend/exit/avoid} (or grade
  parabolic), Axis B is CAPPED (≤35) and the verdict verb cannot read Buy/Add
  (§6.3). Missing extension history ⇒ no silent pass; flag coverage.

### Axis C — Tailwind / "how much higher"
- host **sector RS** + 252d pctile (`engine/sectors.py`); **thematic basket** 20d
  rel-vs-benchmark (`engine/baskets_region.py` membership → per name).
- Axis C is SECTOR-LEVEL. Because A/D are within-sector, C is carved out as a
  declared **tilt** (small weight, labeled), not blended as if within-sector
  (critique stat blind-spot: sector-neutrality must be explicit).

### Axis D — Quality / "how good is the business" (split validated vs context)
- **Validated sub-legs:** `sue` (PEAD) + insider `net_mcap_bps` — both FDR
  survivors. Shown distinctly as "Earnings/insider (validated)".
- **Context sub-legs:** `factor_orthogonal.orthogonal_composite`
  (value/quality/profitability/low-vol — NOT the naive EW mean) + ex-US
  Piotroski/Altman/valuation priors. Labeled "Valuation/quality (context)".
- `accounting_quality` clean/watch/warn = a hard **CAP**, never a positive add.
- Preserves the existing on-page disclaimer ("context, not a validated quality
  verdict") instead of laundering unvalidated factors into a headline.

## 3. Count expansion (floor-based; via validated leg + wider universe)

Target 80–120 is a **consequence of a fixed conviction/score floor**, not a padded
fixed-N. Show the **real eligible count** (some days 60, some 140). The increase
comes from a WIDER universe ranked by the VALIDATED leg — not the unproven blend.

| Market | Today | Fix | Source of the bigger bench |
|---|---|---|---|
| US | ETF-top-10 (~110) gated to decisive urgency → ~24–33 | rank the FULL S&P-1500 cross-section by validated `alpha` | **reuse precomputed `alpha.json` + `factors.json` + `insider_signals.json`** — do NOT re-run `analyze()` on 1500 (CI-timeout risk); keep `build_sector_pages`/`action_board` per-sector urgency board AS-IS as a separate strip |
| CN | n_buy=60 of 774 | lift n_buy → ~110, keep validated reversal-setup rank | existing china pipeline |
| HK | 60 of 73 (=82%, meaningless) | **expand universe** (curate ~80–120 more liquid .HK names in `config.yaml` hk sectors — the existing hand-curated pattern, yfinance-validated; NO free holdings feed exists) and frame as **RS/exposure SCREEN** (trust-tier "no selection edge"), NOT a buy board; protect the validated 73-name `hk_global_beta` panel + breadth gauges (compute beta/breadth on a declared set, don't silently dilute) | curation + yfinance reachability |
| CA | 60 of 220 | lift n_buy → ~100, validated alpha rank, surface gate count | existing canada pipeline |

Default-visible stays 12 (`data-showmore="12"`). Apply the same min-history / ADV
screen to any newly-added HK mid-caps so they don't inject illiquid noise.

## 4. The composite & weights (equal-weight-over-survivors)

No 16 hand-tuned knobs. Default **equal decision weight on the axes/legs that
individually clear that market's Phase-0, ZERO on those that don't**; the 0–100
roll-up for display uses a fixed transparent blend labeled uncalibrated. A
non-equal blend may ship ONLY if the deep panel shows it beats equal-weight
out-of-fold (weights then set by a single pre-registered rule, e.g. ∝ OOS IC-IR —
never tuned by peeking at the final IC). CN/HK/CA weight vectors are labeled
**PRIOR — unvalidated** (CA has no Phase-0 at all today).

## 5. Calibration (out-of-sample, with a pre-committed contingency)

- Per-band forward-return hit-rates via **purged** out-of-sample folds
  (`engine.validation.purged_folds` + `brier_reliability`/`platt_fit`), NOT
  in-sample peeking, written to `<mkt>stockdata/calibration.json`, shown on page.
- **PRE-COMMITTED CONTINGENCY (decided now, not after seeing the result):** if the
  band table is non-monotone (the 80+ band does not beat the 50 band on hit-rate
  AND avg excess at the primary horizon with adequate n) — the LIKELY outcome
  given the negative baseline L/S — the Profile ships as a **display-only ordering
  aid**, the board ranks by the per-market validated leg, and the page says so
  (mirrors the setup-score-phase0 NEUTRAL downgrade). Conviction is never shown as
  a probability unless Platt supports it.

## 6. Headline unification + the verb (the real mismatch fix)

### 6.1 JSON contract
`build_*_library` writes a `conviction` block on every per-stock JSON:
`{score, band, trust_tier, verdict, verdict_zh, axes:{selection,entry,tailwind,
quality} (each {z, pct, display, coverage}), drivers[], cautions[], rank,
sector_rank, provenance:{present[], missing[], as_of{}}}`. Missing legs are
recorded in `provenance.missing`, NEVER silently read as neutral.

### 6.2 Both surfaces read the same block
Dashboard card headline = the `conviction.verdict` + score; detail-page hero =
the SAME block (renderVerdict in `stock.html.j2`, `render()` in
china/hk/canada lookup read `d.conviction` with a graceful fallback to
`d.ladder`). Cycle state stays visible as the labeled timing sub-read.

### 6.3 Cycle state is a HARD VERB MODIFIER (not a parallel note)
The dual-axis (`STOCK_FUNDAMENTALS_PLAN.md` §6) is the backbone: TRADE axis =
calibrated `ladder.score` × entry (× earnings/GEX gate); INVESTMENT axis =
quality × regime-fit × archetype. The single headline verb is produced by an
explicit, **unit-tested EN/中文 disagreement table** in `stock_score.verdict()`:
- ladder downtrend/exit/avoid ⇒ verb ∈ {"Watch — strong name, wrong tape", …},
  NEVER Buy/Add, regardless of the composite number.
- high selection + bad entry ⇒ "Leader · poor entry — wait for a base".
- high selection + accounting warn ⇒ "Leader · accounting watch".
- parabolic grade ⇒ never "add here".
- all-agree ⇒ "High-conviction". HK ⇒ never "Buy" (screen language only).

### 6.4 Trust tier (cross-market honesty)
A per-market `trust_tier` badge bound to the Phase-0 verdict renders beside the
score: US/CA "Ranked edge: weak / context", CN "Reversal — validated, high
variance", HK "No stock-selection edge — exposure/RS screen". The number's
*meaning* visibly changes per market.

### 6.5 Macro-context asymmetry — DESCOPED to liquidity-only for ex-US
ex-US `regime/latest.json` exposes ONLY `liquidity_overlay` (no `macro_risk`,
no `sector_macro_beta`, no vix_ctx — verified). So thread `liquidity` into the
CN/HK/CA `analyze()` calls (build_*_library currently pass none) and DROP
macro_drag/vix for ex-US, labeled "liquidity-conditioned only" (not US-parity).
Per-market macro_risk + sector-beta is a separate future epic.

## 7. Validation (two-tier gate; deep-CI decides the rank)

- **TIER-1 (deep CI only) decides any rank flip.** Clone `top_picks_phase0.py` →
  add each axis as an `_sn_z` column + the orthogonal composite; reuse
  `evaluate()` (rank-IC + NW-HAC t + split-half + quintile L/S Sharpe + DSR +
  BH-FDR) at a **pre-registered primary horizon 63d** (21/126 secondary), with a
  **family-wide DSR** (`n_trials` = composites × markets × horizons actually
  tried) and positive split-half. A market's board ranks by Conviction ONLY if
  `reports/stock-conviction-phase0.md` persists `gate: GO` for it.
- **TIER-2 (local/shallow) NEVER flips a rank** — it only sanity-checks sign and
  populates display. `setups.rank_by="conviction"` reads the persisted GO flag and
  falls back to the validated leg when absent/unavailable. **Machine-enforced
  invariant**, not a prose promise. US-only deep harness is authoritative; CN/HK/CA
  get lighter shallow IC, explicitly labeled non-comparable.
- Realistic expectation: **NEUTRAL → boards rank by the validated leg; Profile
  ships as context.** That is a success, not a failure — it's the honest answer.

## 8. Robustness
Persist `site/factordata/<mkt>_standouts.json` (incl. US) so a transient failure
leaves a stale-but-present artifact with an `as_of` (fixes HK silent-vanish);
graceful empty-state; staleness banner if `as_of` is old; log
enriched/gate-fail/coverage counts. **Freshness:** compute the conviction board
EARLY in `build_site.main()` (right after `build_alpha_data` writes alpha.json,
before the dashboard render) and pass it as a render kwarg — persistence alone
does NOT fix the one-build staleness (the ranking step currently runs last).

## 9. File-by-file plan
- NEW `engine/stock_score.py` — pure: axis sub-scores (sector-neutral z),
  orthogonal assembly, `conviction_profile(rec, market, ctx)` → §6.1 block,
  `verdict()` disagreement table (EN/中文), trust-tier map. Heavily unit-tested.
- NEW `scripts/stock_conviction_phase0.py` — `top_picks_phase0` clone; writes
  `reports/stock-conviction-phase0.md` + the per-market `gate` flag.
- `engine/setups.py` — add `rank_by="conviction"` reading the GO flag, with a
  conviction-aware buy/laggard split + dedupe; keep alpha/setup defaults.
- `scripts/build_stock_library.py` + `build_site.py` — compute the US conviction
  board EARLY from `alpha.json`/`factors.json`/`insider_signals.json`; write the
  `conviction` block + `us_standouts.json`; widen the bench; keep action_board.
- `scripts/build_china_library.py` / `build_hk_library.py` /
  `build_canada_library.py` — wire the Profile, lift n_buy, thread `liquidity`
  into `analyze()`, persist standouts, HK universe curation + screen framing.
- `config.yaml` — expanded HK universe; conviction floor / counts as knobs.
- Templates: `dashboard.html.j2`, `china.html.j2`, `hk.html.j2`, `canada.html.j2`
  (card headline = verdict + radar); `stock.html.j2`, `china_lookup.html.j2`,
  `hk_lookup.html.j2`, `canada_stock.html.j2` (hero reads `d.conviction`; fill the
  Master-verdict chip + provenance; fix the obsolete Next-earnings chip).
- Tests (engine + build + a card/detail render); bilingual EN/中文 throughout.
