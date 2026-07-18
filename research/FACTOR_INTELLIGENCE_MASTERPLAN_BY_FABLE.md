# Factor Intelligence Masterplan — by Fable

**Program:** Factor Intelligence — build a nightly per-name factor panel as a de-escalation and conditioning instrument inside Neural Web. Factors are NOT a selection engine in this house.
**Status:** ACTIVE. Adjudicated 2026-07-04. P0 (this masterplan + pre-registration) dispatched same day.
**Owner:** Fable (main loop). Subagents: Sonnet (build), Opus (review/audit), Haiku (mechanical sweeps).
**Companion:** `research/factor_intelligence/PREREGISTRATION.md` — locked at merge. Gate numbers live there; this document cross-references them but does not duplicate them.
**Relationship to other programs:** Joins Entry Intelligence (EI #1302) via (ticker, signal_date) against PR #1312 schema. Reads Neural Web kernel/metabolism/constitution without modifying them. Does not touch Oracle, qledger origination, or board_ordering in P1–P3.

---

## §0 Charter

The standout board knows what a name is doing (momentum + washout + RS inflection). It does not know what a name *is*. A name that just lost its rate-sensitivity tailwind looks identical to one that gained it. A quality-growth name printing a washout entry looks identical to a spec that will stop out in three sessions.

Factor Intelligence closes that gap. The panel outputs — attribution betas, DNA class, style-regime coordinate, synthetic twin residual — are coordinates that help the organism understand its own signals, not signals in their own right. The value proposition is: fewer mirage entries, shallower stops, and better self-knowledge. Not a new alpha source.

Three independent evidence lines converged on this charter before any new study ran. They are stated in §1. Roughly half the registered trial family (H1–H5) is expected to print nulls. Nulls are printed, not buried.

---

## §1 Verdict & Thesis

### 1.1 Three-way convergence

**Line 1 — Constitution Article 1.** The constitution (`engine/neuralweb/constitution.py`, `AuthorityLevel.A7_ORIGINATE`) permanently bans origination of signals, scores, or escalations by any LLM or automated engine. Factors as a selection/escalation engine violate Article 1 at the implementation level. De-escalation (veto, downsize, withhold) is legal from day 1 under A3. Earned escalation via deterministic features entering kernel cells and surviving shadow ledgers is legal under A5 — after the constitutional promotion path.

**Line 2 — US anticipation Phase-0.** `research/ANTICIPATION_PHASE0.md` settled direction versus drawdown. Direction-side Brier skill at short horizon: **−0.006** (base up-rate 0.531, cell spread 1.0 pp). At medium horizon: **−0.0** (base 0.606, spread 2.2 pp). Both are coin-flips — no factor-conditional direction edge found. Drawdown side: four legs survived GO with cluster-aware halves stability:

| Leg | Rank-IC (drawdown) | Both halves |
|---|---|---|
| `vol_pct` | **−0.0582** | −0.0436 / −0.0722 |
| `confluence` | −0.0356 | −0.0266 / −0.0440 |
| `neg_trend_vel` | −0.0275 | −0.0121 / −0.0426 |
| `rvar_vel` | −0.0151 | −0.0158 / −0.0139 |

`acc_res` (acceleration): sign-unstable IC +0.0074 / halves +0.0216 / −0.0069, fails both-halves and CV — **KILLED, display-only.**

**Line 3 — China drawdown edge.** `research/china_alpha/phase1/phase0-verdicts.md` (master synthesis `research/CHINA_ENGINE_REASSESSMENT.md`): external-driver forward-drawdown radar shows composite ≥10%/42d drawdown lift **2.07× (p=0.01)**, 2016+ **2.53×**. A-share cross-sectional momentum (12-1, all frames, total and residual): IC **−0.009 / −0.005**, long-short net Sharpe **−0.37 / −0.11**, nothing clears BH-FDR. Selection dead; drawdown conditioning live.

The convergence ruling: factors are a de-escalation and conditioning instrument. That is the program thesis. It is not revisable by red-team in this cycle — only the parameters of implementation are open.

### 1.2 Two-lane law

**FAST lane — de-escalation:** veto, downsize, withhold on existing per-name clamp mechanisms (engine/altdata_brain.py ACCUMULATE→WATCH and engine/narrative_brain.py ENTER→MONITOR `_reconcile` clamps; standout-board display chip lane). Legal from day 1 under A3. Teeth attach only after the relevant hypothesis passes its PREREG gate, followed by the per-hypothesis would-have-fired shadow-log step specified in the prereg (§4 governs).

**SLOW lane — earned escalation:** deterministic features enter kernel cells (new `style_regime` shadow coordinate), survive pre-registered shadow ledgers, flip Article-2 surfaces only via the constitutional promotion path (DISPLAY → SHADOW → CONFIRMER → SCORED, one rung at a time, Wilson-gated). The style_regime classifier is a coordinate, not a prior — it carries no folk theory about what works in each state; the kernel measures that.

### 1.3 Honest EV

The expected value of this program is: fewer mirage entries when factor headwinds are severe; shallower stop-outs when DNA class predicts fast-stop cohorts; better organism self-knowledge via the committee surfaces. It is NOT: new alpha, a ranking upgrade, or a selection engine. The registered family is five primary hypotheses (H1–H5). Based on the priors in §2.2, roughly half are expected to null out. Nulls are printed under the program name, added to the standing null registry, and count as scientific output.

---

## §2 Source Adjudication of the External Factor Handoff

*Reference: "the external factor handoff (Downloads, 2026-07)" — adjudicated, not adopted.*

### 2.1 Adjudication table

| Idea from handoff | Verdict | Grounds |
|---|---|---|
| Interpreter-not-trigger: factors explain entries, they don't generate them | **ADOPT** | Convergent with constitution Article 1; "interpreter" framing is the precise legal form here |
| Attribution over picking: what drove the return matters more than which factor fired | **ADOPT** | Real gap in current stack; Block-A attribution (D-2/D-3) addresses it directly |
| Upgrade/size-up spine: factor score → escalate board position or increase size | **ADOPT-INVERTED** | Illegal as written (A7_ORIGINATE, A5 requires shadow period); becomes: surviving factor feature enters shadow kernel cell after PREREG, never directly sizes up |
| Alpha-purity as rank booster: high-residual names rank higher | **KILLED** | Circular — `composite_rank` in `engine/equity_factors.py` already IC-weights FDR survivors; a second factor-purity booster added to the rank key would be a compound of the existing key plus noise; no causal path from purity to forward edge not already captured |
| Factor rotation velocity as a timing signal | **KILLED** | `acc_res` (acceleration) is anti-predictive per `research/ANTICIPATION_PHASE0.md` (sign-unstable IC, fails both-halves and CV); the `_rotation()` function in `engine/factor_series.py` is descriptive only and its confirmed-leader debounce does not rescue the timing claim |
| Factor-adjusted technicals: tech signal quality conditional on factor regime | **ADOPT** | Hypothesis H1 (PREREG); S7-adjacent (RS-before-price); tests whether entry-oscillator signal quality varies by DNA class — a different object from the selection claim |
| Factor decay exits: trim or exit when factor exposure decays | **ADOPT** | Hypothesis H5 (PREREG); note that the EMA8 tail-flag NO-GO ruling (`research/signal_engine_exit_rule_verdict`) is a different formulation (price-side), not a prior against a factor-decay exit study |
| Factor weather: regime-conditional factor leadership as a market coordinate | **ADOPT** | As coordinate, not prior; style_regime classifier (D-6) implements this; the classifier carries no folk-theory about what works in each state — the kernel measures that |
| Synthetic twin: compare name to its factor-matched peer cluster | **ADOPT** | Risk oracle only (D-4); twin_rel_20d and twin_bleed_flag feed H3/H4 de-escalation hypotheses; not a selection input |
| Crowding X-ray: factor concentration risk overlay | **ALREADY-BUILT** | Six modules: `engine/theme_crowding.py` (Lou-Polk comomentum, COMOVE_WIN=126, CROWDED_Z=1.0), `engine/factor_exposure.py` (portfolio risk_contribution, concentrated≥0.50), `engine/crowding.py` (three-leg fragility: crowded + shorted + extended, all ≥80th percentile), `engine/froth_fragility.py`, `engine/fund_crowding.py`, `scripts/fund_crowding_phase0.py` (DISPLAY-ONLY verdict, split-half fail on excess-return leg) |
| DNA fingerprint: classify name into factor archetype | **ALREADY-BUILT** | 17 species in `data/species/registry.json`; D-5 formalizes as a deterministic threshold cascade using existing `engine/equity_factors.py` Block-B legs; no new factor formulas |
| Claims with LLM-assigned confidence numbers | **KILLED** | Fake precision; house law: "No LLM-authored confidence numbers anywhere — claims carry calibrated Wilson bounds from graded history or no number" (D-7); LLMs may only de-escalate calibrated keys |
| Factor freshness / factor timing as a signal | **DEFERRED** | Distinct from the killed `acc_res` (which tested return-series acceleration); factor-timing prior is a separate hypothesis requiring its own PREREG and separate trial budget; deferred to v2 review given the 5-hypothesis budget cap and thin trial count |

### 2.2 Numeric priors block

These are the priors any study in this program must condition on. Interim runs that contradict them without meeting the program's own PREREG standards are labeled PRE-FDR INTERIM and are non-binding.

**Equity factors IC scorecard** (`data/edgar/ic_scorecard.json`): horizon 63d, span 2011-03-31 to 2025-12-31, 60 rebalances, median universe 1,154 names. Point-in-time EDGAR; survivorship-biased (optimistic bound — delisted names absent).

| Factor | mean_IC | IC-IR ann | t_HAC | q_FDR | FDR |
|---|---|---|---|---|---|
| payout | 0.0247 | 0.596 | 2.723 | 0.0715 | **SURVIVES** |
| value | 0.0184 | 0.446 | 2.006 | 0.247 | no |
| profitability | 0.0141 | 0.240 | 0.820 | 0.931 | no |
| quality | 0.0042 | 0.146 | 0.564 | 0.931 | no |
| accruals | 0.0070 | 0.198 | 0.729 | 0.931 | no |
| sue | 0.0006 | 0.017 | 0.065 | 0.948 | no |
| composite | −0.0072 | −0.097 | −0.396 | 0.946 | no |
| investment | −0.0029 | −0.072 | −0.288 | 0.946 | no |
| low_vol | −0.0209 | −0.186 | −0.742 | 0.931 | no |
| low_beta | −0.0151 | −0.127 | −0.535 | 0.931 | no |

Sole BH-FDR survivor: **payout** (q=0.0715). The scorecard note: "factors that survived on ~2.5y (notably SUE) weaken on deep history."

**Residual alpha momentum** (`research/RESIDUAL_ALPHA_MOMENTUM.md`): PIT de-biased 2002–2026 — `mom_tot` IC collapses to 0.0008 (t=0.08), de-contaminated L/S Sharpe −0.05. `mom_res` IC 0.0124 but L/S Sharpe −0.29. Nothing survives BH-FDR (best q ≈ 0.40). The shipped framing: "a modest, regime-decayed edge — context, not a buy list."

**Crowding split-half fail** (`reports/fund-crowding-phase0.md`): FRAGILE 21d forward excess return: full +0.10 pp, H1 −0.12, H2 +0.32, t=+0.20 — sign flips between halves. Sole |t|>2 result (63d drawdown, t=−2.32) also fails both-halves robustness. DISPLAY-ONLY verdict stands.

**BASED-chip canonical mirage** (`research/SETUP_SPECIES_MASTERPLAN_BY_FABLE.md` §1.6 graveyard; `data/species/registry.json` S1.adjacent_falsified): "BASED state is byte-identical to survival-to-day-j; zero selection content; C2 uses an active trigger event, not a passive survival predicate." The house's canonical precedent for a technical setup that looked like selection but was purely a survivorship / passive-survival predicate. Any factor-conditional setup must pass the BASED-chip test: does it have an active trigger, or is it a relabeled survival predicate?

---

## §3 factor_model_v1 — Frozen Spec

All parameters in this section are frozen. Definition changes require v2, never in-place mutation. Every panel row carries `factor_model: "v1"`. "TBD" does not appear in this section.

### 3.1 Block A — Return-stream attribution (D-2, D-3)

**Purpose:** decompose each name's realized return into factor-stream contributions. The output per (ticker, date) is attribution shares, not a score.

**Streams (ordered by orthogonalization priority, max 8):**

| Priority | Key | Proxy | Source |
|---|---|---|---|
| 1 | `mkt` | SPY close pct_change | `engine/residual_alpha.py` line 77 convention |
| 2 | `sector` | GICS SPDR ETF (see map below), orthogonalized to mkt | see §3.1 GICS map |
| 3 | `size` | IWM, orthogonalized to mkt + sector | `engine/factor_exposure.py` line 80 convention |
| 4 | `growth` | QQQ, orthogonalized to mkt + sector + size | NEW panel proxy (not a factor_exposure.py convention; factor_exposure.py's actual factors are market/size/rates/usd/oil/china/btc/gold). Legal: no new signal formula; orthogonalized panel stream. |
| 5 | `rates` | TLT, orthogonalized to prior streams | `engine/factor_exposure.py` line 80 convention |
| 6 | `dollar` | DX-Y.NYB, orthogonalized to prior streams | `engine/factor_exposure.py` line 87 |
| 7 | `ai_theme` | basket id `ai_infra` EW daily return, orthogonalized to prior streams | NEW panel proxy (same legal basis as `growth`). Return series from `site/basketdata/baskets.json["chart"]["baskets"]["ai_infra"]`; builder adapts if key path differs. |
| 8 | `china` | FXI close pct_change, orthogonalized to prior streams | ADR/China-exposed names only; omitted for others |

**Note:** `factor_exposure.py`'s actual factor list is market/size/rates/usd/oil/china/btc/gold. The Block-A stream set adds `growth` (QQQ) and `ai_theme` (ai_infra basket) as orthogonalized proxies. These are legal because they introduce no new signal formulas; they are return series of existing instruments.

**GICS sector → SPDR ETF map** (from `scripts/grade_us_board.py` lines 111–117):

| GICS Sector | ETF |
|---|---|
| Energy | XLE |
| Information Technology | XLK |
| Technology | XLK |
| Financials | XLF |
| Health Care | XLV |
| Industrials | XLI |
| Consumer Discretionary | XLY |
| Consumer Staples | XLP |
| Utilities | XLU |
| Materials | XLB |
| Real Estate | XLRE |
| Communication Services | XLC |
| Communications | XLC |
| (no sector match) | SPY — fallback |

**Estimation conventions** (copy `engine/residual_alpha.py` exactly where they exist):
- Rolling window: **252 trading days** (`beta_win: 252`, config.yml line 637)
- Min periods: **126** (max(252//2, 15))
- Beta lag: **1 day** (`.shift(1)` before rolling — causal, uses [t-252, t-1] data only)
- Vasicek shrinkage weight: **w=0.66** (config.yml line 640); `beta_shrunk = beta_raw × 0.66 + cross_sectional_mean(beta_raw) × 0.34`; target = cross-sectional mean that day; if w≥1, no-op
- Winsorization: `_winsor_z(s, cap=3.0)` per `engine/equity_factors.py` lines 333–338 — `((s − μ) / σ).clip(−3.0, 3.0)` applied to the sector-neutral deviation
- Orthogonalization: sequential univariate residualization in the priority order above (Gram-Schmidt), matching `engine/factor_exposure.py` lines 181–200
- China stream: included only if the name's sector or a manual flag marks it ADR/China-exposed; omitted otherwise (stream count may be 7 for non-China names)

**Attribution outputs per (ticker, date), three windows (5d, 20d, 60d):**

For window W in {5, 20, 60}:
- `contrib_{stream}_W` — contribution share: `beta_stream × realized_stream_return_W / abs(realized_return_W)` (signed; sums to 1 + noise from residual); clipped to [−2, +2]
- `alibi_share_W` — `Σ|contrib_W| / (Σ|contrib_W| + |resid_ret_W|)`, bounded [0,1] by construction, no clipping. `contrib_W` = beta×stream-return contributions per Block-A stream over window W; `resid_ret_W` = the residual return. The formula is bounded [0,1] algebraically; no separate clip is applied. It is scale-invariant (identical whether computed from raw contributions or normalized shares). Under the zero-return guard (below), `alibi_share_W` is also None.
- `resid_ret_W` — the residual return itself (realized return minus sum of factor contributions), in raw return units
- `resid_ret_1d` — the Block-A residual return for the single trading day (daily one-day residual return). Used by study harnesses to cumulate a residual price series PIT for H1's `resid_led` feature. Note: H1's transformed-series oscillator crosses (sector-ratio series, residual series) are computed AT STUDY TIME by the P3 harness from panel columns + price data using engine/cycles.py functions; they require NOTHING from the replay artifact beyond the (ticker, signal_date) join keys.

The P1-A run log prints the alibi_share distribution (p5/p25/p50/p75/p95) per window (5d, 20d, 60d).

**`alpha_z_house` panel column (required for PREREG H2):** in addition to Block-A attribution outputs, the panel carries `alpha_z_house` — the sector-neutral residual-momentum z from `engine/residual_alpha.py`, copied PIT from the nightly residual_alpha computation at date t (data ≤ t only). This is the stratification variable for the H2 second gate clause (§2.5 in PREREGISTRATION.md). It is carried as a read-through from the existing residual_alpha nightly output, not recomputed inside the factor panel builder.

**Zero-return guard:** if `abs(realized_return_W) < 1e-6`, all contribution shares are set to `None` for that window (division guard; do not impute zero).

### 3.2 Block B — Cross-sectional DNA percentiles (D-2)

Block B reads existing outputs from `engine/equity_factors.py` legs as they exist. No new factor formulas are invented in v1.

**Legs included (Block-B uses the following subset of `engine/equity_factors.py` FACTOR_LABELS):**

The full FACTOR_LABELS = value, profitability, quality, investment, payout, low_vol, low_beta, short_interest, accruals, sue. Block B uses the subset: value, profitability, quality, payout, low_vol.

| Leg | Formula sketch | Notes |
|---|---|---|
| `value` | EW mean of _winsor_z(EY, B/P, S/P, CFO/mktcap) | 4 sub-legs, all yields |
| `profitability` | _winsor_z(gross_profit / assets) | Novy-Marx |
| `quality` | mean of [_winsor_z(ROE), −_winsor_z(accruals), −_winsor_z(leverage)] | ROE + neg accruals + neg leverage |
| `payout` | _winsor_z((dividends + repurchases) / mktcap) | net shareholder yield; sole FDR survivor |
| `low_vol` | −_winsor_z(d['vol']) where d['vol'] = rets.tail(win).std()·√252 (equity_factors.py:393,443); the panel freezes win at whatever value the nightly equity_factors run uses (config-owned), recorded in the panel run log | negative IC in scorecard; negative mean_IC = −0.021 |

Block-B values are cross-sectional percentiles (1–99) at the time of panel build, not regression betas. They carry no predictive claim standalone — they are coordinates for DNA class assignment (§3.3) and committee display.

**`size_pct` — coordinate derivation (v1-stamped):** `size_pct` is a v1 COORDINATE DERIVATION, not a factor leg: `size_pct = cross-sectional percentile of mktcap (already computed in equity_factors.py, d['mktcap'])`; a coordinate like sector, not a signal; v1-stamped. It is used in the DNA cascade (§3.3) for size filtering but is NOT a Block-B percentile column in the panel.

### 3.3 DNA class (D-5)

DNA class is a deterministic priority-ordered threshold cascade over Block-B percentiles and Block-A betas. It is computed once per (ticker, date) and stored as a single string. `mixed` is the honest default when thresholds do not yield a unique class. PIT is enforced: percentiles are computed on the cross-section available at that date.

**Class definitions (priority order — first match wins):**

| Class | Trigger conditions |
|---|---|
| `quality_growth` | quality pct ≥ 70 AND value pct < 60 AND beta_growth > 0.3 |
| `high_beta_liquidity` | beta_mkt > 1.3 AND beta_growth > 0.4 AND low_vol pct < 35 |
| `cyclical_value` | value pct ≥ 65 AND own GICS sector ∈ {Energy, Industrials, Materials} AND beta_sector > 0.2 |
| `defensive_quality` | quality pct ≥ 65 AND low_vol pct ≥ 60 AND beta_mkt < 0.85 |
| `rate_duration_sensitive` | abs(beta_rates) > 0.25 AND (payout pct ≥ 55 OR low_vol pct ≥ 55) |
| `china_crypto_proxy` | beta_china > 0.30 (requires china stream present) OR (beta_mkt > 1.1 AND sector in {Information Technology, Communication Services} AND value pct < 30) |
| `small_spec` | `size_pct` < 30 AND low_vol pct < 40 AND quality pct < 45 |
| `mixed` | none of the above triggered, OR two classes tied at equal priority |

Threshold values are set here and frozen for v1. The drafter (Sonnet) must implement these exactly and include a unit test asserting that `mixed` is the output when all conditions are false. Any threshold adjustment requires a v2 version stamp. The `mixed` class is never treated as a failure — it is the honest classification for names that do not fit a clean archetype.

### 3.4 Style-regime classifier (D-6)

**States (closed set):** `{growth_momentum, quality_defense, value_cyclical, junk_rally, mixed}`

**Inputs (deterministic only — no LLM, no soft scores):**

| Input | Source |
|---|---|
| Factor L/S 20d + 60d returns | `site/factordata/factor_series.json` — per-factor compounded returns for the trailing windows |
| ETF pulse ratios | computed from ETF close caches (`data/yahoo/`) per RULING-D — `etf_pulse.json` artifact does not exist (citation corrected 2026-07-05) |
| Confirmed factor series leader | `engine/factor_series._rotation()` — `leader` field (3-session debounce) |

**Classification thresholds:**

| State | Conditions |
|---|---|
| `growth_momentum` | QQQ/SPY 20d ratio > +0.03 AND factor_series growth or profitability is confirmed leader AND IWF/IWD 20d ratio > 0 |
| `quality_defense` | IWF/IWD 20d ratio < −0.02 AND factor_series quality or low_vol is confirmed leader AND QQQ/SPY 20d ratio < 0 |
| `value_cyclical` | IWF/IWD 20d ratio < −0.02 AND factor_series value or payout is confirmed leader AND IWM/SPY 20d ratio > 0 |
| `junk_rally` | IWM/SPY 20d ratio > +0.04 AND factor_series confirmed leader has negative IC in scorecard (low_vol or investment) AND QQQ/SPY 20d ratio < +0.01 |
| `mixed` | No state's conditions fully met, OR two states tie |

**Hysteresis rule:** a state change requires **2 consecutive daily confirmations**. On the first day a new state's conditions are met, the state is recorded as `pending_{new_state}`; the flip is confirmed on the second consecutive match. Reversions to `mixed` are immediate (1 day) — failing conditions = immediate mixed. This prevents rapid oscillation without adding arbitrary delay. The panel stores the CONFIRMED state in `style_regime` and the tentative state in a separate `style_regime_pending` column. Kernel cells and studies key on `style_regime` only; `style_regime_pending` is display-diagnostic only.

**Emitted as:** a `world_state` lobe (§5.4) and a column in the factor panel. Display tier at birth. The classifier is a coordinate — it carries no folk theory about what works in each state; the kernel measures that (§5.1).

### 3.5 Twin (D-4)

**Definition:** for each (ticker, date), the synthetic twin is an equal-weight basket of the top-12 peers by 252d residual-return correlation (residuals from Block A), filtered to the same GICS industry and within ±1 size tercile of the name, self-excluded, refreshed on the first trading day of each month.

**Correlation window:** ends at t−1 (PIT; no look-ahead). The 252d window is [t-253, t-1].

**Minimum peers:** 8. If fewer than 8 peers survive the GICS + size + correlation filter, fall back to the industry equal-weight basket (all names in the same GICS industry, equal-weight, self-excluded).

**Membership freeze:** the twin basket composition is frozen for the calendar month. It does not update daily. The freeze date is the first trading day of the month. This is the PIT enforcement: the twin was not knowable intramonth beyond what was computable on the freeze date.

**Outputs per (ticker, date):**
- `twin_rel_20d` — the name's 20d realized return minus the twin basket's 20d realized return (signed; positive = outperformed twin)
- `twin_bleed_flag` — boolean: True if the twin 20d return is negative AND the twin is below its own 20d high by more than its trailing median pullback (computed from the prior 60d of twin basket daily returns, using the rolling 20d drawdown from 20d high distribution). The drafter must implement the trailing-median-pullback computation deterministically and include a unit test. *(corrected 2026-07-05 to match locked PREREG H4; drift caught in P1-B — original text said "prior 252d")*

**Purpose:** `twin_bleed_flag` is H4's feature (de-escalation validity when the twin basket is bleeding at entry). `twin_rel_20d` is a display/context output and an input to H5's decay context.

### 3.6 Panel data plane (D-1)

**Artifact location:** `data/factordata/panel/` — partitioned by month (`YYYY-MM/panel.parquet`).

**Schema:** parquet, columnar, snappy-compressed. Every row carries:
- `ticker` (str) + `date` (str, "YYYY-MM-DD") — primary keys
- `factor_model` (str, always `"v1"`) — version stamp
- All Block-A attribution columns (§3.1), including `resid_ret_1d` (float) — the single-day Block-A residual return
- All Block-B percentiles (§3.2)
- `dna_class` (str, §3.3)
- `style_regime` (str, §3.4) — the day's confirmed classifier state
- `style_regime_pending` (str, nullable, §3.4) — the tentative next state during hysteresis; display-diagnostic only; null when no flip is pending
- Twin outputs (§3.5): `twin_rel_20d`, `twin_bleed_flag`, `twin_n_peers`, `twin_fallback` (bool, True if fell back to industry EW)
- `alpha_z_house` (float) — the sector-neutral residual-momentum z from `engine/residual_alpha.py`, copied from the nightly residual_alpha computation at date t (PIT: computed from data ≤ t); required as stratification variable for PREREG H2's second gate clause

**R2 rule:** if the panel exceeds the git-heaviness norm (assessed at first build: if any monthly partition exceeds ~5 MB or the trailing-12-month panel exceeds ~50 MB), it rides R2 per the r2-data-plane law. The builder must measure and report partition sizes in its first run log.

**Build placement:** off the render path. A standalone nightly step (`scripts/build_factor_panel.py`) runs before `build_site.py` in CI, writing to `data/factordata/panel/`. The render path reads the pre-computed panel; it does not recompute factor betas inline. This matches the pattern of `scripts/build_factor_series.py` (which runs before `build_site` per the render path summary in R2).

**Join contract:** studies in this program join the panel against replay rows (PR #1312) and board-ledger rows on `(ticker, date)` where `date` matches `signal_date`. No other program may write to `data/factordata/panel/`; no panel column may be added without a v2 stamp.

---

## §4 Governance & Constitution Mapping (D-7)

### 4.1 Authority table

| Output | Authority level | Tier at birth | Promotion path |
|---|---|---|---|
| Block-A attribution shares (narration) | A1 — narrate on any surface | DISPLAY | None — A1 is permanent; attribution is explanation, not a claim |
| Block-B DNA percentiles (display) | A1 | DISPLAY | None |
| DNA class (display chip) | A1 | DISPLAY | None — deterministic classification, not a signal |
| style_regime coordinate (world_state lobe) | A1 | DISPLAY | A5 promotion via kernel shadow ledger after PREREG gate (§5.1) |
| De-escalation (veto/downsize) — FAST lane | A3 — requires hypothesis gate | DISPLAY (log-only) | Gate per relevant PREREG (H1–H4); teeth attach only after gate passes + per-prereg shadow-log step |
| Twin bleed flag (display) | A1 | DISPLAY | None |
| H5 factor-decay attention items | A2 — rank what deserves operator attention | DISPLAY → SHADOW | After P3 ledger n≥25 cluster floor (§7) |
| Any new board_ordering influence | A5 (min) | SHADOW | Full constitutional promotion path; Article 2 shadow period |
| Any new claim origination | A7 — BANNED | — | Grant refused unconditionally, no evidence overrides |

### 4.2 Claim shapes for P2 registration

When studies pass their PREREG gates, machine-registered hypotheses are filed in `data/neuralweb/machine_registry.jsonl` via `engine/neuralweb/metabolism.register_hypothesis()`. Budget: 3 per ISO week. The four valid `claim_shape` values are `lead_lag`, `conditional_regime`, `entry_quality`, `sector_conditional` (`engine/neuralweb/metabolism.py` lines 85–91).

| Study | Claim shape | Falsifier (pre-committed) |
|---|---|---|
| H1 (factor-adjusted confluence annotation) | `entry_quality` | Δ P(CUSHIONED ∪ CLEAN_LIFTOFF, 21d) on factor_annotated=True vs False; horizon_d=21 |
| H2 (borrowed-strength/alibi veto) | `conditional_regime` | Δ P(CUSHIONED ∪ CLEAN_LIFTOFF, 21d) on high_alibi_flag=True vs False; alibi_share_20d 20d window only; horizon_d=21 |
| H3 (DNA × style_regime drawdown discrimination) | `conditional_regime` | P(STOPPED,21d) between-cell heterogeneity across qualifying cells; horizon_d=21 |
| H4 (twin-bleed veto) | `entry_quality` | Δ P(STOPPED,21d) on twin_bleed_flag=True vs False; horizon_d=21 |
| H5 (thesis-decay exits) | `lead_lag` | Δ P(−5% within 21d of flag) on decay_flag=True vs False; horizon_d=21 |

All registrations must follow metabolism's actual contract: `min_n` clamped up to 25 (`_HOUSE_MIN_N`), no `registered_at` field supplied by caller, no `cortex_attention` or `reflex.cortex_attention` in `spine_query`. The BUDGET_PER_WEEK=3 enforcement means P2 registrations are spread across weeks — plan for 2 weeks minimum to file all 5.

### 4.3 Article-2 untouched list (P1–P3)

The following money-path surfaces are untouched in P1–P3 of this program (all five Article-2 surfaces enumerated in `config/synapse.yml`):
- `alert_triage` — the alert priority queue; named Article-2 surface in `config/synapse.yml`
- `board_ordering` — the standout board rank key; named Article-2 surface in `config/synapse.yml`
- `top_setups` — named Article-2 surface in `config/synapse.yml`
- `attention_queue` — named Article-2 surface in `config/synapse.yml`; factor attention items are context-only/display-tier and never raise attention_queue priority; cortex flags remain under the cortex's existing constraints
- `push_floor` — named Article-2 surface in `config/synapse.yml`
- Any `qledger` claim origination (A7-banned)
- Any escalation path (banner, alert, headline)

P4 may propose `board_ordering` influence only after the relevant hypothesis has completed SHADOW with a pre-registered flip criterion (R6 from EI masterplan applies here too).

### 4.4 No-LLM-confidence rule

No LLM-authored confidence numbers appear in any Factor Intelligence output. Claims carry calibrated Wilson lower bounds from graded history (z=1.645, 90% one-sided) or carry no number. The style_regime classifier emits a state label, not a probability. The DNA class emits a class string, not a score. Attribution shares are arithmetic decompositions of realized returns — they are not predictions.

### 4.4a Calibration degeneracy ruling (FIX-7, 2026-07-05)

**FABLE RULING:** Calibration degeneracies (DNA mixed 52%, style mixed 89%) are PRINTED, not patched. §3.3/§3.4 thresholds remain frozen v1. A v2 recalibration is deferred to the pre-H3 clean window: after real fire-population distributions exist and before any H3 outcome data is analyzed. mixed is the honest default, not a failure (§3.3).

Calibration re-run outputs (verbatim, run 2026-07-05 against snapshot date 2026-07-02 + trailing 3y):

**DNA class distribution (snapshot 2026-07-02, n_total=1503, n_evaluable=982):**
```
nan                           :  521  ( 53.1% of evaluable)
mixed                         :  511  ( 52.0% of evaluable)
rate_duration_sensitive       :  162  ( 16.5% of evaluable)
quality_growth                :   92  (  9.4% of evaluable)
cyclical_value                :   77  (  7.8% of evaluable)
high_beta_liquidity           :   55  (  5.6% of evaluable)
defensive_quality             :   47  (  4.8% of evaluable)
small_spec                    :   22  (  2.2% of evaluable)
china_crypto_proxy            :   16  (  1.6% of evaluable)
CALIBRATION DEGENERACY — dna_class 'mixed' is 52.0% of evaluable (target: no class >50%).
CALIBRATION DEGENERACY — 'mixed' is 52.0% of evaluable (target: mixed <40%).
Thresholds FROZEN. Degeneracy reported verbatim.
```

**style_regime timeline (n_days=784, 2023-07-03 to 2026-07-02, trailing 3y):**
```
mixed               :  703 days ( 89.7%)
quality_defense     :   23 days (  2.9%)
junk_rally          :   23 days (  2.9%)
value_cyclical      :   21 days (  2.7%)
growth_momentum     :   14 days (  1.8%)
CALIBRATION DEGENERACY — style_regime 'mixed' is 89.7% of days (target: no state >70%).
Thresholds FROZEN. Degeneracy reported verbatim.
total state flips: 52
```

### 4.5 Two-lane rendering rule

Committee surfaces (committee.html factor panel, per-name DNA card) display two lanes:
- **Diagnostic lane:** always shown. Carries attribution shares, DNA class, style_regime coordinate, twin relative performance. No gate required — these are descriptions of realized returns and deterministic classifications.
- **Predictive lane:** shows DISPLAY-ONLY or `gauntlet-passed` status. Before any hypothesis passes its gate, the predictive lane shows `n={n}, PRE-FDR INTERIM` (house convention per PR #1339). After a gate passes, the predictive lane shows the Wilson lower bound and cluster-n. The word "validated" never appears per CI-enforced check (`scripts/check_validated_claims.py`).

---

## §5 Neural Web Fusion Design

### 5.1 Kernel shadow coordinate for style_regime

The kernel cell key is `"{engine}:{regime}:{horizon}"` (`engine/neuralweb/kernel.py` line 182–183). The current `regime` bucket is derived from `quad_hard_label` (the four quad labels or `__unstamped__`). Adding `style_regime` as a second regime dimension requires a choice:

**Decision: parallel shadow table** (option b from the kernel spec). A new parquet artifact `data/neuralweb/kernel_style_regime_shadow.parquet` with keys `(engine, quad_regime, style_regime, horizon)` is built by a new function `build_style_estimates()` in a new module `engine/neuralweb/kernel_style.py`. This does not modify the existing `kernel_estimates.parquet` schema or any existing `build_estimates()` logic. The existing kernel's `__all__` marginal continues to aggregate over both dimensions.

The shadow table starts accruing at the `style_regime` classifier's first daily emit. It is DISPLAY-ONLY until the kernel-FDR clock (2026-10 sweep) evaluates the enriched cells. The cortex may read it via a new `_tool_read_style_kernel()` function; no behavioral consumer reads it before the FDR sweep.

Cell population note: splitting by `(quad_regime × style_regime)` creates up to 4×5=20 cells per (engine, horizon). At typical n-per-cell, most cells will be sparse at P3 launch. The shrinkage pooling from `engine/pooling.pooled_edges()` applies within each `engine` family across regime combinations — this is the primary defense against sparse cells.

### 5.2 New contradiction type: borrowed_strength

**Pair G — borrowed_strength** is implemented in a DEDICATED per-name detector: `engine/neuralweb/factor_contradictions.py` (P2 deliverable), writing `data/neuralweb/factor_contradictions.jsonl`. It is NOT merged into `detect_contradictions`' macro list. It is surfaced only on per-name panels + the committee factor section; the macro top-5 priority surface is untouched. Cardinality expectation: 0–20 records/day among fired names.

Pair G fires when a name's entry signal is strong (fires as T1 or T2) but `high_alibi_flag` is True (`alibi_share_20d` ≥ trailing-252d Q80 — the same flag defined in §3.1 and PREREG H2; no separate threshold) — meaning most of the recent move is explained by factor streams, not the name's own residual. This raises the question of whether the signal is genuine stock selection or factor-stream attribution laundered through the technicals.

The record shape mirrors the contradictions.py `_record()` convention (pair_id, a_artifact, a_reading, b_artifact, b_reading, kind='label-tension', severity='note', as_of, note) but is written by the dedicated module.

`display_only` is hardcoded True by `_record()` (contradictions.py:178); the assertion enforces severity ∈ {note, tension}.

`severity` starts at `"note"` unconditionally. It can only be promoted to `"tension"` after H2 passes its PREREG gate (the empirical check that high alibi_share correlates with worse entry outcomes). The dedicated detector must fail open (never raise; gaps list maintained).

### 5.3 Cortex A2 curriculum — factor contradictions as attention items

Factor-derived attention operates in two lanes:

**Lane 1 (deterministic factor engine):** the factor engine files into its OWN reflex: name `factor_attention`, own firings.jsonl under `data/reflexes/factor_attention/`, own grader run, own probation record. It NEVER writes to `cortex_attention`. The claim_family is auto-stamped by `record_firing` — no hand-set claim_family. The grader grades `direction=-1; hit = name underperforms SPY at horizon_d=21`.

The `_SELF_REF_FORBIDDEN` frozenset (metabolism.py ~252–255) and enforcement block (~299–311) ensure `cortex_attention` cannot appear in `spine_query`.

`grade_cortex_attention._grade_realized_move` loads the symbol close and computes `engine.grading.forward_metrics` excess-vs-SPY at grade time; it does NOT read `spine_index.parquet`.

The falsifier for Lane 1 items: `direction=-1; hit = name underperforms SPY at horizon_d=21 (graded by _grade_realized_move)`. The stop-out-rate claim lives only in H2's metabolism gate (which uses a different metric). The attention item and H2 gate accrue on different criteria by design.

**Lane 2 (cortex deliberation):** the cortex MAY, during deliberation, select items from the `factor_contradictions` artifact (`data/neuralweb/factor_contradictions.jsonl`) and flag them via its existing `_tool_flag_attention`. Those items accrue to CORTEX probation — the cortex's SELECTION JUDGMENT is what A2 grades. These do not double-count with Lane 1.

The self-ref ban (`_SELF_REF_FORBIDDEN` in metabolism.py ~252–255, enforcement block ~299–311) forbids `cortex_attention` or `reflex.cortex_attention` in `spine_query`. Factor attention items satisfy this ban.

The A2 earn-in floors from constitution.py apply: `min_n=25`, `min_events=8`, Wilson z=1.645, lift threshold 1.25 vs base_rate=0.5, freshness ≤120d.

### 5.4 World-state factor-weather lobe

A new `_compose_factor_weather()` function is added to `engine/neuralweb/world_state.py` (following the existing sub-block pattern in world_state.py line 315+) and wired as:

```python
"factor_weather": _compose_factor_weather(factor_panel_latest, factor_series_json),
```

Sub-block contents:
- `style_regime`: the current confirmed state string and pending state if different
- `style_regime_hold_days`: how many consecutive days the current state has been confirmed
- `factor_leader`: confirmed leader from `factor_series._rotation()` with held days
- `factor_leader_ic`: the leader's mean_IC from ic_scorecard.json (calibrated prior; printed even if negative)
- `etf_pulse_summary`: 20d IWF/IWD, QQQ/SPY, IWM/SPY ratios (computed from ETF close caches in `data/yahoo/` per RULING-D — `etf_pulse.json` artifact does not exist, citation corrected 2026-07-05)
- `display_only`: True — this lobe is A1/display; no behavioral consumer reads it before the kernel-FDR sweep

The `qi` slot in world_state.json is currently null and flagged as pending the W7 joint border ruling (world_state.py line 29). The `factor_weather` lobe does NOT occupy the `qi` slot — it is a separate named key. The `qi` ruling is out of scope for this program.

### 5.5 Regime-conditional engine report cards (P4 committee surface)

In P4, the committee.html factor panel is extended with a regime-conditional report card: for each engine in kernel_estimates.parquet, the regime cells that include `style_regime` as a conditioning coordinate are shown side-by-side with the `__all__` marginal. The display shows cell n, Wilson lower bound, and `PRE-FDR INTERIM` label until the 2026-10 kernel-FDR sweep decides.

---

## §6 EI #1302 Handshake

### 6.1 JOIN architecture (D-1)

The factor panel joins against PR #1312's replay artifact on `(ticker, signal_date)` — the two fields present on every row of `data/replay/standout_replay.parquet` (per the full schema in R1). The join is performed at study time, not at build time:

1. Nightly: `scripts/build_factor_panel.py` writes `data/factordata/panel/YYYY-MM/panel.parquet` keyed `(ticker, date)`.
2. Study time: a study script loads `data/replay/standout_replay.parquet`, loads the factor panel, and joins on `(ticker, signal_date == date)`.

No changes are made to `scripts/replay_standout_pipeline.py` or the replay schema. No new columns are added to any PR #1312 artifact. The panel is a standalone artifact; the join is the caller's responsibility.

### 6.2 Sequencing

The factor panel can be built independently of PR #1312 — it reads only the name universe (breadth close caches) and the factor machinery already on the render path. Studies H1–H4 require both the replay artifact AND the factor panel to exist before they run. H5 reads the board ledger (held names) and the factor panel — it does not require the replay artifact for its primary substrate.

### 6.3 Collision status

No in-flight work collides with the factor panel. The five open PRs on main as of 2026-07-04 (#1350, #1342, #1341, #1339, #1312) do not write to `data/factordata/panel/` or use `(ticker, signal_date)` as a compound key. The four existing factor research docs (`QUANT_FACTOR_EXPANSION.md`, `VECTOR_FACTOR_ROADMAP_2026.md`, `VECTOR_NEW_FACTORS.md`, `INSIDER_FACTOR.md`) all target macro regime or BTC Vector — none builds a per-name replay panel or joins to signal-gate verdicts. Collision-free.

**Shared engine files:** the EI program owns `_compose_board_summary` (Factor Intelligence only READS that lobe). This program adds only `_compose_factor_weather` to `engine/neuralweb/world_state.py` (single-function PR discipline). `factor_weather` is a NEW top-level world_state key; the null `qi` slot stays reserved for the W7 ruling — do not occupy it.

---

## §7 Phases P1–P4

### P1 — Factor panel foundation (gated on this masterplan merge)

**Exit gate:** panel builder green in CI + PIT audit clean + style_regime first emit + world_state factor_weather lobe live.

**P1-C exit gate PIT guards:** (a) `style_regime[t]` is a pure function of data ≤ t, stored once, never rewritten on re-render (idempotence assertion in P1 test suite); (b) every percentile/quintile breakpoint used for cohort assignment (incl. alibi Q80, DNA percentiles) is computed on a trailing 252d cross-sectional window as of t, never panel-global.

**Calibration sanity check (build sanity, NOT gauntlet gate):** run both classifiers over the trailing 3 years; run log prints: (a) DNA class distribution (build-sanity targets: no class >50%, mixed <40%); (b) style_regime state timeline (every state must fire at least once; no state >70% of days). These are build sanity checks only — they do not gate the PR.

**PR granularity (4 PRs, Sonnet builds, Opus reviews each, Fable merges):**

| PR | Deliverable |
|---|---|
| P1-A | `scripts/build_factor_panel.py` — Block-A attribution engine + Block-B DNA percentile reader; PIT audit by Opus; render-path exclusion verified; partition sizes reported |
| P1-B | Twin computation (`twin_rel_20d`, `twin_bleed_flag`); unit tests for trailing-median-pullback and GICS+size filter; twin fallback logic |
| P1-C | style_regime classifier + world_state `_compose_factor_weather()` + factor_weather lobe wiring; DNA class threshold cascade + unit test for all-false → `mixed` |
| P1-D | Pair G detector `engine/neuralweb/factor_contradictions.py` (dedicated module, §5.2) + `factor_attention` reflex writer (Lane 1, §5.3); display-only graded-log pipeline |

**Model routing:** Sonnet builds all four PRs. Opus reviews each (PIT audit focus on P1-A, threshold correctness on P1-C). Fable merges after Opus sign-off.

**Dependencies:** none (panel builder reads existing caches on main).

### P2 — Hypothesis registration + interim substrates (gated on P1 green)

**Exit gate:** machine registrations filed for H1–H5 in metabolism (≥2 ISO weeks for budget); PRE-FDR INTERIM runs reported with survivorship stamps. (The PREREGISTRATION.md companion locked at P0 merge; P2 files the machine registrations against it.)

**Deliverables:** per-hypothesis interim study notebooks; borrowed_strength severity stays `"note"` until H2 GATE-PASSED (§5.2) — an interim directional signal does NOT promote it.

**Model routing:** Sonnet builds study scaffolding; Opus reviews interim results + flags methodological issues; Fable approves PREREGs.

**Dependencies:** P1 green; replay artifact from PR #1312 must exist for H1–H4 interim runs (H5 uses board ledger, interim-capable immediately after P1).

### P3 — Gauntlet runs (gated on #1312 merge + n≥25 cluster floor)

**Exit gate:** H1–H5 run on full replay/ledger substrate; BH-FDR within the 5-hypothesis family; verdicts printed for each per the prereg's pre-bound vocabulary (GATE-PASSED / DISPLAY-WITH-EDGE / NULL); kernel shadow coordinate `kernel_style_regime_shadow.parquet` accruing.

**Deliverables:**
- `research/factor_intelligence/H{1-5}_VERDICT.md` — one verdict memo per hypothesis, Opus-authored, Fable-approved
- `engine/neuralweb/kernel_style.py` — `build_style_estimates()` function; shadow table first build
- De-escalation path for GATE-PASSED hypotheses: H2/H4 → would-have-fired shadow ledger, then the relevant per-name `_reconcile` clamp wiring (A3; no board_ordering touch); H1 → logged annotation field only; H3 → cell-discrimination observation added to the factor_weather lobe descriptive text

**H1–H4 dependency:** PR #1312 must be merged. Studies join replay artifact on `(ticker, signal_date)`. Do not run H1–H4 before merge.
**H5 dependency:** board ledger (held names with entry dates) + factor panel. No replay requirement. Interim-capable in P2.

**Inference:** month-block bootstrap (calendar-month resampling unit, ≥2000 resamples; see PREREGISTRATION.md §2.2). Fixed n-floors per hypothesis: H1/H2: ≥10 contributing months AND ≥150 deduped fires per arm; H3: ≥12 contributing months AND ≥8 qualifying cells; H4: ≥10 months AND ≥60 flagged fires; H5: ≥10 months AND ≥40 flagged names. These floors are fixed ex ante and do not change based on observed data.

**CI-compliance:** any scripts/ harness matching `validate_*/*_phase0/*_phase1.py` that calls `deflated_sharpe` must register via the TrialLedger (`register_trials` / `log_declared_budget` / `ledger=` param). These harnesses do not call `deflated_sharpe`; they nonetheless register for auditability: `from engine.trial_ledger import TrialLedger` + `ledger.log_declared_budget(5, family="factor_intelligence_v1", reason="factor_intelligence_v1 5-test family")` (positional n first). Harness names: `scripts/validate_factor_h1.py`, `scripts/validate_factor_h2.py`, `scripts/validate_factor_h3.py`, `scripts/validate_factor_h4.py`, `scripts/validate_factor_h5.py` for the five primary tests; `scripts/validate_factor_family.py` for the pre-committed BH runner. BH across the five primary p-values is computed ONLY by `scripts/validate_factor_family.py`; hand-computed BH is an audit finding. This obligation is separate from metabolism registration (`metabolism.register_hypothesis`), which is also required.

**Model routing:** Sonnet runs study code; Opus reviews statistical methodology + month-block bootstrap inference; Fable adjudicates GO/NO-GO.

### P4 — Earned escalation + committee surfaces (gated on kernel-FDR 2026-10 clock + A2 earn-in)

**Exit gate:** kernel-FDR 2026-10 sweep evaluates style_regime shadow cells; A2 earn-in floors met (n≥25 attention items, ≥8 hits, Wilson lb/0.5 > 1.25, freshness ≤120d); committee.html factor panel live with regime-conditional report cards.

**Deliverables:**
- committee.html factor panel extension (§5.5) — regime-conditional report cards with PRE-FDR INTERIM labels until sweep
- `_compose_board_summary()` in world_state.py (§5 of EI masterplan — stock-level lobe carrying per-stock DNA + style_regime coordinate; reads `site/factordata/us_standouts.json`)
- Any Article-2 surface influence (board_ordering) ONLY after a specific hypothesis passes both P3 GATE-PASSED and the A5 shadow period — explicit Fable ruling required before any PR touches board_ordering

**Dependencies:** kernel-FDR clock (2026-10 scheduled sweep); A2 earn-in from cortex grading loop (accrues from P1-D launch); EI program P4.4 (board summary as stock-level lobe is joint — coordinate with EI program owner).

**Model routing:** Sonnet builds committee surfaces; Opus reviews; Fable merges P4 PRs only after explicit kernel-FDR ruling.

---

## §8 Standing Kill List

The following are permanently killed in this program. No subagent PR may include them. If a PR is found to contain any of the following, it is rejected without review and the subagent is re-scoped.

1. **Predictive factor velocity/acceleration:** `acc_res` is anti-predictive (sign-unstable IC, fails both-halves, ANTICIPATION_PHASE0 ruling). The `_rotation()` function in factor_series.py is descriptive; its leader signal is NOT a timing input.
2. **Any weighted mega-score:** a composite factor score used to rank names or weight positions. The `composite_rank` in equity_factors.py already IC-weights FDR survivors; a second composite is redundant and compounds circularity.
3. **LLM confidence numbers:** any numerical "probability" or "confidence" emitted by an LLM or heuristic that has not been calibrated against graded history with Wilson bounds. The word "validated" also falls under CI enforcement.
4. **No new SIGNAL formulas in v1:** Block-B uses only existing `engine/equity_factors.py` legs; coordinate derivations (percentiles of already-computed descriptors, e.g. `size_pct` from `d['mktcap']`) are permitted with a version stamp. No new factor leg may be added to v1 without a v2 stamp.
5. **Fast-lane escalation of any kind:** the FAST lane is de-escalation only. Any PR that wires a factor signal to an escalation path (alert, banner, board rank-up) before the relevant PREREG gate passes is a constitutional violation.
6. **Hand-coded folk regime priors in reflexes:** the style_regime classifier is a coordinate. No reflex rule may encode beliefs like "growth_momentum → buy tech" or "value_cyclical → avoid growth." The kernel measures those relationships; it does not pre-load them.
7. **Modifications to replay_standout_pipeline.py or the replay schema:** the JOIN architecture is collision-dissolving precisely because the factor panel is a standalone artifact. Any edit to the replay script or its schema requires explicit Fable approval and is not in scope for this program.

---

## §9 Risks & Mitigations

| Risk | Mitigation |
|---|---|
| **n-fragmentation:** style_regime × quad cells may be sparse at P3, especially for rare quad states | Shrinkage via `engine/pooling.pooled_edges()` pools across regime combinations within each engine family; n is printed on every display surface; sparse cells show Wilson CI width explicitly |
| **H1 circularity vs the residual rank key:** `alibi_share` is defined relative to Block-A betas, which partially overlap with residual_alpha.py's computation | H1 tests entry-oscillator cross quality (terminal state) conditional on `alibi_share_20d`; the independent variable is the entry trigger (2D MACD × 3D StochRSI cross), not the alpha score; the PREREG mandates an ablation vs `alpha_z` as a co-variate to isolate the alibi_share effect |
| **Render budget:** the factor panel adds a new nightly computation | Off-render-path builder (`scripts/build_factor_panel.py`); measured runtime reported in first run log; if it exceeds 5 minutes it must be optimized before merging P1-A |
| **Schema drift vs #1312:** if #1312 schema changes post-merge, study joins break | JOIN-only architecture; no shared files; the factor panel reads only `(ticker, date)` from replay — if the column names change, only the join key needs updating; the panel itself is independent |
| **Factor soup:** 8 Block-A streams + 5 Block-B legs might encourage ad hoc composite construction | Block-A is capped at 8 streams (D-2), Block-B uses only existing legs; the kill list bans new factor formulas and mega-scores; the DNA class is the only composite construct, and it is deterministic not scored |
| **PIT holes in twin membership:** correlation window could see future composition changes | Twin membership frozen monthly on the first trading day; correlation window ends at t−1; both enforced at build time; the unit test for P1-B must assert that no future data enters the window |
| **Survivorship in interim substrates:** close caches contain currently-listed names only | All interim runs labeled PRE-FDR INTERIM; the survivorship stamp follows the EI program's convention from R1 (pre-2015 rows carry survivor-bias stamp); the scorecard's "optimistic bound" disclaimer is carried into every interim report |
| **ACC_RES anti-predictive ghost:** the kill list bans factor velocity, but it could re-enter via a new name | The kill list is standing and enforced by Fable review; any PR adding a momentum-of-factor-return input triggers automatic rejection |

---

## §10 Consumers & Lateral Payoffs

### Entry pipeline de-escalation chips (P2 → P3)

When hypotheses reach GATE-PASSED, consequences attach per the prereg's unlock clauses:
- H1 GATE-PASSED: `factor_annotated=True` → logged annotation field on every fire for the thesis-decay track (H5); no behavioral consequence at day 1
- H2 GATE-PASSED: `high_alibi_flag=True` (`alibi_share_20d ≥ Q80`) → after the would-have-fired shadow-log step, the altdata/narrative `_reconcile` clamp (`engine/altdata_brain.py` ACCUMULATE→WATCH, `engine/narrative_brain.py` ENTER→MONITOR) is flagged with a 'borrowed-strength entry' context chip; operator sees chip and may choose to pass or downsize
- H4 GATE-PASSED: `twin_bleed_flag=True` → after the shadow-log step, adds a "twin bleeding" de-escalation annotation to the board entry
- H3 GATE-PASSED: the DNA × style_regime discrimination observation is added to the factor_weather lobe descriptive text (no per-name chip)

These are annotation-and-ceiling adjustments, not board rank changes. They route through A3, not A5.

### Committee.html factor weather + per-name DNA panels

The committee surface gains a new factor tab in P4: style_regime state + hold days, factor leader + scorecard IC, per-name DNA class (derived from Block-B percentiles). The tab is diagnostic-lane-only until P4 committee surface launch. Per-name DNA panels display the Block-B percentile spider chart and Block-A attribution waterfall for the trailing 20d and 60d windows.

### Mastermind Brain-book X-ray (out of scope here)

`engine/factor_exposure.py` already computes portfolio-level betas and risk_contribution per the watchlist. The mastermind-fix program is the consumer of portfolio-level factor X-rays (the Brain's book composition analysis). That program will read `site/factor_betas.json` directly. Factor Intelligence does not need to produce a separate portfolio artifact; the existing `factor_betas.json` (540 KB, rendered nightly) already serves that consumer. Out of scope for this program — noted here to prevent duplication.

### International ports (CN/HK/CA) — v2 explicit

The factor panel in v1 covers the US name universe (S&P 1500 breadth close caches, matching `engine/equity_factors.py`'s universe). CN/HK/CA ports require:
- Separate close caches (already partially built for CN/HK)
- Separate GICS maps (Shenwan L1 for A-shares)
- The China stream (FXI orthogonalized) is already included in Block-A for ADR/China-exposed US names

International ports are explicitly deferred to v2. No v1 PR may target CN/HK/CA names or claim cross-market generalization. The China drawdown edge (§1.1 Line 3) is a market-level signal, not a name-level factor panel — it informs the program thesis but does not require a CN panel in v1.

---

## §11 Status Log (append-only)

- 2026-07-04 — Program adjudicated; masterplan written; P0 dispatched. Companion PREREGISTRATION.md to be locked at merge of this file. — Fable
- 2026-07-18 — **FWS display wave adjudicated (Fable): Factor Weather & Seasonality Surfacing.** Trigger: the July 2026 momentum/semis miss — the French momentum July headwind (trailing-10y mean −0.64%, 30% hit, last 5 Julys all negative) was invisible because (a) `engine/factor_seasonality.py` computes only full-sample + trailing-30y windows (30y July momentum = +0.53%, masking the regime read), (b) `site/seasonality.html` is a nav-orphan and `factor_seasonality.json` had zero consumers, (c) no momentum factor exists on any live surface. Ruling (display-tier only, all A1, Article-2 untouched, kill list §8 unmodified): (1) `factor_seasonality.v2` adds a trailing-10y window + a deterministic current-month spotlight (`now` block, versioned display rule; UNSCORED and definition-mismatch disclosures retained — seasonality stays out of every calibrated score); (2) factors.html doctrine revamp folds the factor calendar into the nav-promised surface; seasonality.html becomes the linked Tier-3 deep dive; the NW status panel demotes to page bottom with a plain-word lead; (3) momentum surfaces as DISPLAY ONLY — French `mom` climate rows + MTUM/SPY pulse + a 12-1 top-decile concentration X-ray in a new `engine/momentum_display.py` (`momentum_display.v1`, unscored, reads existing close caches; NOT a Block-B leg — no v2 panel stamp consumed; momentum selection/timing stay dead per §2.1 and the RESIDUAL_ALPHA_MOMENTUM null); (4) `world_state.factor_weather` gains `seasonal_climate` keys (canonical read of the committed seasonality artifact, fail-open) and page-level month-climate context chips attach to us_stocks/baskets headers (contagion-chip precedent, display-only). No new lobe (NWC-U2 cap respected), no new hypothesis, no scoring path. — Fable
- 2026-07-06 — **NW integration wave shipped same-day** (Codex docket verified 9-lane + red-teamed, adjudicated in `research/factor_intelligence/NW_INTEGRATION_ADJUDICATION_BY_FABLE.md`, RUL-NW1..14): #1583 committed `factor_intelligence_state.json` + long-term factor pool (`factor_state_history.jsonl`, `fire_coordinates.jsonl`, committed Pair-G ledger, committed reflex firings) + factor_panel narrow sole-advancer; #1589 `world_state.factor_weather` canonical-read with `factor_state_as_of` (review caught + fixed a circular-staleness freeze between builder and lobe); #1595 cortex `read_factor_state`/`list_factor_contradictions`/`explain_factor_context` + Ask-the-Brain factor routing + zh directional-verb guard; #1593 factors.html NW status panel (BH-WITHHELD chip mandatory) + admin Factor Intelligence section E; #1598 dark A3 shadow-ledger scaffold (RUL-NW6 floor: ≥25 episode-clustered events, ≥3 months, then Fable ruling) + `check_factor_boundaries.py` CI guard. `register_h45` dispatched and registered (H4/H5, come-back 2026-08-03) — all five hypotheses machine-registered, PENDING verification that dispatch-written registry rows persist to main (cross-job visibility). Committee per-ticker predictive lane deferred to P4 per RUL-NW8. — Fable
